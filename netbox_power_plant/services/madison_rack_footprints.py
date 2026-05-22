from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from dcim.models import Rack, Site

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PlantDisciplineChoices,
    PlantExtractionMethodChoices,
    PlantSourceLayerKindChoices,
    PlantSourceTypeChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
    SpatialPlacementKindChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_cad_materialization import madison_cad_object_slug
from netbox_power_plant.services.madison_space_decomposition import (
    MADISON_DETAILED_SPACE_APPROVED_STATE,
    MADISON_DETAILED_SPACE_REVIEW_STATE,
    build_madison_detailed_space_decomposition_summary,
)


MADISON_RACK_FOOTPRINT_PREFIX = "madison-rack-footprint"
MADISON_RACK_FOOTPRINT_TYPE_KEY = "madison-rack-footprint-type"
MADISON_RACK_LAYOUT_SOURCE_KEY = "madison-rack-cabinet-layout-source"
MADISON_RACK_LAYOUT_SHEET_KEY = "madison-rack-cabinet-layout-sheet"
MADISON_RACK_LAYOUT_LAYER_KEY = "madison-rack-cabinet-layout-layer"
MADISON_RACK_FOOTPRINT_REVIEW_STATE = "operator_review_required"
MADISON_RACK_FOOTPRINT_APPROVED_STATE = "approved"
ROW_ID_TAG_PREFIX = "nscale-row-id-"

DEFAULT_RACK_MANIFEST_PATHS = (
    Path("/opt/netbox/local-plugins/netbox_multiplanar_fabrics/local-netbox-dev/data/generated/madison_workbook_rack_manifest.csv"),
    Path("/Users/mencken/github-repos/netbox_multiplanar_fabrics/local-netbox-dev/data/generated/madison_workbook_rack_manifest.csv"),
)
DEFAULT_CABINET_SCHEDULE_PATHS = (
    Path("/opt/netbox/local-plugins/netbox_multiplanar_fabrics/local-netbox-dev/data/electrical/enovum_mad1_cabinet_circuit_schedule.csv"),
    Path("/Users/mencken/Documents/netbox-site-staging-multiplanar-roce/electrical/enovum_mad1_cabinet_circuit_schedule.csv"),
)

DIRECT_WORKBOOK_SLOT_PATTERN = re.compile(r"^(?P<row>[A-X])(?P<slot>[1-9]|1\d|2[0-6])$")
COMPUTE_RACK_PATTERN = re.compile(
    r"^(?P<family>GB300|BE|FE)-P(?P<group>\d+)-R(?P<row>\d+)-C(?P<cabinet>\d+)$"
)
NETWORK_RACK_PATTERN = re.compile(
    r"^NW-P(?P<hall_section>[12][AB])-R(?P<row>\d+)-C(?P<cabinet>\d+)$"
)

GB300_SLOT_NUMBERS = tuple(range(1, 9)) + tuple(range(19, 27))
FE_SLOT_NUMBERS = (13, 14)
COMPUTE_GROUP_ROWS = {
    1: ("Q", "R"),
    2: ("U", "V"),
    3: ("S", "T"),
    4: ("W", "X"),
    5: ("A", "B"),
    6: ("E", "F"),
    7: ("C", "D"),
    8: ("G", "H"),
}
NETWORK_GROUP_ROWS = {
    "1A": ("M", "N"),
    "1B": ("O", "P"),
    "2A": ("I", "J"),
    "2B": ("K", "L"),
}
BE_SLOT_MAP = {
    1: {1: (0, 9), 2: (0, 17), 3: (1, 9), 4: (1, 17)},
    2: {1: (0, 10), 2: (0, 18), 3: (1, 10), 4: (1, 18)},
}

SPACE_ROW_PAIRS = {
    "b1209-data-hall-2a": (("A", "B"), ("E", "F"), ("I", "J")),
    "b1211-data-hall-2b": (("C", "D"), ("G", "H"), ("K", "L")),
    "b1109-data-hall-1a": (("M", "N"), ("Q", "R"), ("U", "V")),
    "b1111-data-hall-1b": (("O", "P"), ("S", "T"), ("W", "X")),
}
ROW_SPACE_KEY = {
    row: space_key
    for space_key, row_pairs in SPACE_ROW_PAIRS.items()
    for row_pair in row_pairs
    for row in row_pair
}
ROW_PAIR_INDEX = {
    row: pair_index
    for space_key, row_pairs in SPACE_ROW_PAIRS.items()
    for pair_index, row_pair in enumerate(row_pairs)
    for row in row_pair
}
ROW_LANE_INDEX = {
    row: lane_index
    for row_pairs in SPACE_ROW_PAIRS.values()
    for row_pair in row_pairs
    for lane_index, row in enumerate(row_pair)
}


@dataclass(frozen=True)
class MadisonRackSourceRecord:
    physical_slot: str
    source_label: str
    role_slug: str
    role_name: str
    data_hall: str
    dimensions: str
    source: str
    source_ref: str
    metadata: dict


@dataclass(frozen=True)
class MadisonRackFootprintCandidate:
    source_record: MadisonRackSourceRecord
    slug: str
    name: str
    boundary_geometry: dict
    row_letter: str
    slot_number: int
    physical_space: PhysicalSpace | None
    rack: Rack | None
    electrical_rack_ids: tuple[str, ...] = ()
    element: PhysicalElement | None = None
    placement: SpatialPlacement | None = None
    binding: PhysicalObjectBinding | None = None

    @property
    def materialized(self):
        return self.element is not None

    @property
    def placed(self):
        return self.placement is not None

    @property
    def bound(self):
        return self.binding is not None

    @property
    def matched(self):
        return self.rack is not None

    @property
    def review_state(self):
        if self.binding is not None:
            return (self.binding.metadata or {}).get("review_state", "")
        if self.element is not None:
            return (self.element.metadata or {}).get("review_state", "")
        return "not_materialized"

    @property
    def status_label(self):
        if not self.materialized:
            return "Candidate"
        if not self.matched:
            return "Unmatched"
        if self.review_state == MADISON_RACK_FOOTPRINT_APPROVED_STATE:
            return "Approved"
        return "Needs review"


@dataclass(frozen=True)
class MadisonRackFootprintSummary:
    site: Site | None
    source_document: PlantSourceDocument | None
    source_manifest_path: str = ""
    source_schedule_path: str = ""
    blocked_reasons: tuple[str, ...] = ()
    candidates: tuple[MadisonRackFootprintCandidate, ...] = ()
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    approved_count: int = 0

    @property
    def ready(self):
        return not self.blocked_reasons

    @property
    def candidate_count(self):
        return len(self.candidates)

    @property
    def materialized_count(self):
        return len([candidate for candidate in self.candidates if candidate.materialized])

    @property
    def placed_count(self):
        return len([candidate for candidate in self.candidates if candidate.placed])

    @property
    def matched_count(self):
        return len([candidate for candidate in self.candidates if candidate.matched])

    @property
    def bound_count(self):
        return len([candidate for candidate in self.candidates if candidate.bound])

    @property
    def unmatched_count(self):
        return len([candidate for candidate in self.candidates if not candidate.matched])

    @property
    def pending_review_count(self):
        return len(
            [
                candidate
                for candidate in self.candidates
                if candidate.bound and candidate.review_state == MADISON_RACK_FOOTPRINT_REVIEW_STATE
            ]
        )

    @property
    def ready_for_approval(self):
        return self.ready and self.bound_count > 0 and self.pending_review_count > 0


def build_madison_rack_footprint_summary(
    site,
    *,
    manifest_path=None,
    schedule_path=None,
) -> MadisonRackFootprintSummary:
    resolved_site = _resolve_site(site)
    if resolved_site is None:
        return MadisonRackFootprintSummary(
            site=None,
            source_document=None,
            blocked_reasons=(f"No site found for slug '{site}'.",),
        )

    spaces, blocked = _approved_data_hall_spaces(resolved_site)
    if blocked:
        return MadisonRackFootprintSummary(
            site=resolved_site,
            source_document=_layout_source_document(resolved_site),
            blocked_reasons=blocked,
        )

    manifest = _first_existing_path(manifest_path, DEFAULT_RACK_MANIFEST_PATHS)
    schedule = _first_existing_path(schedule_path, DEFAULT_CABINET_SCHEDULE_PATHS)
    electrical_ids_by_slot = _electrical_ids_by_slot(schedule)
    records = _source_records_from_manifest(manifest) if manifest is not None else ()
    source_name = "workbook_manifest" if records else "netbox_racks"
    if not records:
        records = _source_records_from_netbox_racks(resolved_site)
    records = tuple(record for record in records if _slot_parts(record.physical_slot) is not None)
    if not records:
        return MadisonRackFootprintSummary(
            site=resolved_site,
            source_document=_layout_source_document(resolved_site),
            source_manifest_path=str(manifest or ""),
            source_schedule_path=str(schedule or ""),
            blocked_reasons=("No Madison rack source records were found from a rack manifest or NetBox rack row-id tags.",),
        )

    existing = _existing_objects(resolved_site)
    candidates = tuple(
        _candidate_from_record(
            resolved_site,
            record,
            spaces=spaces,
            rack_by_slot=existing["rack_by_slot"],
            electrical_ids=tuple(electrical_ids_by_slot.get(record.physical_slot, ())),
            existing=existing,
        )
        for record in sorted(records, key=lambda record: _slot_sort_key(record.physical_slot))
    )
    source_document = _layout_source_document(resolved_site)
    if source_document is None and source_name == "netbox_racks":
        source_document = None
    return MadisonRackFootprintSummary(
        site=resolved_site,
        source_document=source_document,
        source_manifest_path=str(manifest or ""),
        source_schedule_path=str(schedule or ""),
        candidates=candidates,
        approved_count=len(
            [
                candidate
                for candidate in candidates
                if candidate.review_state == MADISON_RACK_FOOTPRINT_APPROVED_STATE
            ]
        ),
    )


def apply_madison_rack_footprint_candidates(
    site,
    *,
    manifest_path=None,
    schedule_path=None,
    reviewer=None,
) -> MadisonRackFootprintSummary:
    resolved_site = _resolve_site(site)
    if resolved_site is None:
        raise ValueError(f"No site found for slug '{site}'.")

    summary = build_madison_rack_footprint_summary(
        resolved_site,
        manifest_path=manifest_path,
        schedule_path=schedule_path,
    )
    if not summary.ready:
        raise ValueError("Madison rack footprints are not ready for materialization: " + "; ".join(summary.blocked_reasons))

    reviewer_name = _reviewer_name(reviewer)
    reviewed_at = timezone.now()
    created = updated = unchanged = 0
    with transaction.atomic():
        source_document, source_sheet, source_layer = _ensure_layout_source(
            resolved_site,
            manifest_path=summary.source_manifest_path,
            schedule_path=summary.source_schedule_path,
        )
        element_type = _ensure_rack_footprint_type(resolved_site)
        for candidate in summary.candidates:
            element, element_action = _upsert_element(
                candidate,
                element_type=element_type,
                reviewed_at=reviewed_at,
                reviewer_name=reviewer_name,
            )
            placement, placement_action = _upsert_placement(
                candidate,
                element=element,
                reviewed_at=reviewed_at,
                reviewer_name=reviewer_name,
            )
            binding = None
            binding_action = "unchanged"
            if candidate.rack is not None:
                binding, binding_action = _upsert_binding(
                    candidate,
                    element=element,
                    placement=placement,
                    reviewed_at=reviewed_at,
                    reviewer_name=reviewer_name,
                )
            provenance_actions = _upsert_provenance(
                candidate,
                element=element,
                placement=placement,
                binding=binding,
                source_document=source_document,
                source_sheet=source_sheet,
                source_layer=source_layer,
                extracted_at=reviewed_at,
            )
            actions = (element_action, placement_action, binding_action, *provenance_actions)
            if "created" in actions:
                created += 1
            elif "updated" in actions:
                updated += 1
            else:
                unchanged += 1

    return replace(
        build_madison_rack_footprint_summary(
            resolved_site,
            manifest_path=manifest_path,
            schedule_path=schedule_path,
        ),
        created_count=created,
        updated_count=updated,
        unchanged_count=unchanged,
    )


def approve_madison_rack_footprint_bindings(
    site,
    *,
    reviewer=None,
    notes="",
) -> MadisonRackFootprintSummary:
    resolved_site = _resolve_site(site)
    if resolved_site is None:
        raise ValueError(f"No site found for slug '{site}'.")

    summary = build_madison_rack_footprint_summary(resolved_site)
    if not summary.ready:
        raise ValueError("Madison rack footprints are not ready for approval: " + "; ".join(summary.blocked_reasons))
    if not summary.ready_for_approval:
        raise ValueError("No matched Madison rack footprint bindings are pending operator approval.")

    reviewer_name = _reviewer_name(reviewer)
    approved_at = timezone.now()
    review_notes = str(notes or "").strip()
    updated = unchanged = 0
    with transaction.atomic():
        for candidate in summary.candidates:
            if candidate.binding is None or candidate.review_state != MADISON_RACK_FOOTPRINT_REVIEW_STATE:
                continue
            changed = _approve_candidate(
                candidate.binding,
                reviewer_name=reviewer_name,
                approved_at=approved_at,
                notes=review_notes,
            )
            if changed:
                updated += 1
            else:
                unchanged += 1

    return replace(
        build_madison_rack_footprint_summary(resolved_site),
        updated_count=updated,
        unchanged_count=unchanged,
    )


def slot_for_electrical_rack_id(name):
    if DIRECT_WORKBOOK_SLOT_PATTERN.fullmatch(str(name or "")):
        return str(name)

    match = COMPUTE_RACK_PATTERN.fullmatch(str(name or ""))
    if match:
        family = match.group("family")
        group = int(match.group("group"))
        row = int(match.group("row"))
        cabinet = int(match.group("cabinet"))
        physical_rows = COMPUTE_GROUP_ROWS.get(group)
        if not physical_rows:
            return None

        if family == "GB300":
            if row not in (1, 2) or not 1 <= cabinet <= len(GB300_SLOT_NUMBERS):
                return None
            return f"{physical_rows[row - 1]}{GB300_SLOT_NUMBERS[cabinet - 1]}"

        if family == "FE":
            if row not in (1, 2) or not 1 <= cabinet <= len(FE_SLOT_NUMBERS):
                return None
            return f"{physical_rows[row - 1]}{FE_SLOT_NUMBERS[cabinet - 1]}"

        if family == "BE":
            row_index_and_slot = BE_SLOT_MAP.get(row, {}).get(cabinet)
            if not row_index_and_slot:
                return None
            row_index, slot_number = row_index_and_slot
            return f"{physical_rows[row_index]}{slot_number}"

    match = NETWORK_RACK_PATTERN.fullmatch(str(name or ""))
    if match:
        physical_rows = NETWORK_GROUP_ROWS.get(match.group("hall_section"))
        row = int(match.group("row"))
        cabinet = int(match.group("cabinet"))
        if not physical_rows or row not in (1, 2) or not 1 <= cabinet <= 7:
            return None
        return f"{physical_rows[row - 1]}{cabinet}"

    return None


def _approved_data_hall_spaces(site):
    decomposition = build_madison_detailed_space_decomposition_summary(site)
    if not decomposition.ready:
        return {}, decomposition.blocked_reasons
    if decomposition.materialized_count == 0:
        return {}, ("Apply Madison detailed spaces before rack/cabinet footprint extraction.",)

    spaces = {}
    for candidate in decomposition.candidates:
        if candidate.space is None:
            continue
        key = candidate.spec.key
        if key not in SPACE_ROW_PAIRS:
            continue
        geometry = candidate.space.boundary_geometry or {}
        if not _rect_is_usable(geometry):
            return {}, (f"Detailed data hall space {candidate.space.name} has no usable rectangular boundary.",)
        spaces[key] = candidate.space
    missing_keys = [key for key in SPACE_ROW_PAIRS if key not in spaces]
    if missing_keys:
        return {}, ("Materialize all Madison data hall spaces before rack/cabinet footprint extraction.",)
    return spaces, ()


def _source_records_from_manifest(path):
    if path is None:
        return ()
    records = []
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("role_slug") == "empty-or-spacer":
                continue
            physical_slot = (row.get("physical_slot") or "").strip().upper()
            if not physical_slot:
                continue
            records.append(
                MadisonRackSourceRecord(
                    physical_slot=physical_slot,
                    source_label=(row.get("source_label") or "").strip(),
                    role_slug=(row.get("role_slug") or "").strip(),
                    role_name=(row.get("role_name") or "").strip(),
                    data_hall=(row.get("location") or "").strip(),
                    dimensions=(row.get("dimensions") or "").strip(),
                    source="workbook_manifest",
                    source_ref=(row.get("workbook_cell") or physical_slot).strip(),
                    metadata=dict(row),
                )
            )
    return tuple(records)


def _source_records_from_netbox_racks(site):
    records = []
    for rack in Rack.objects.filter(site=site).select_related("role", "location").prefetch_related("tags").order_by("name"):
        slot = _slot_for_rack(rack)
        if slot is None:
            continue
        dimensions = ""
        if rack.outer_width and rack.outer_depth:
            dimensions = f"{rack.outer_width}x{rack.outer_depth}"
        records.append(
            MadisonRackSourceRecord(
                physical_slot=slot,
                source_label=rack.name,
                role_slug=getattr(rack.role, "slug", "") or "netbox-rack",
                role_name=getattr(rack.role, "name", "") or "",
                data_hall=getattr(rack.location, "name", "") or _data_hall_for_slot(slot),
                dimensions=dimensions,
                source="netbox_rack_inventory",
                source_ref=f"dcim.rack:{rack.pk}",
                metadata={"rack_id": rack.pk, "rack_name": rack.name},
            )
        )
    return tuple(_dedupe_records(records))


def _dedupe_records(records):
    by_slot = {}
    for record in records:
        by_slot.setdefault(record.physical_slot, record)
    return tuple(by_slot[slot] for slot in sorted(by_slot, key=_slot_sort_key))


def _electrical_ids_by_slot(path):
    by_slot = defaultdict(set)
    if path is None:
        return by_slot
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            rack_id = (row.get("rack_id") or "").strip()
            slot = slot_for_electrical_rack_id(rack_id)
            if slot:
                by_slot[slot].add(rack_id)
    return {slot: tuple(sorted(values)) for slot, values in by_slot.items()}


def _candidate_from_record(site, record, *, spaces, rack_by_slot, electrical_ids, existing):
    row_letter, slot_number = _slot_parts(record.physical_slot)
    space_key = ROW_SPACE_KEY[row_letter]
    space = spaces[space_key]
    geometry = _rack_boundary_for_slot(space, record.physical_slot)
    slug = madison_cad_object_slug(site, f"{MADISON_RACK_FOOTPRINT_PREFIX}-{record.physical_slot.lower()}")
    rack = rack_by_slot.get(record.physical_slot)
    element = existing["elements"].get(slug)
    placement = existing["placements"].get(f"{slug}-placement"[:100])
    binding = existing["bindings"].get(slug)
    return MadisonRackFootprintCandidate(
        source_record=record,
        slug=slug,
        name=_name(f"{site.name} Rack {record.physical_slot} Footprint"),
        boundary_geometry=geometry,
        row_letter=row_letter,
        slot_number=slot_number,
        physical_space=space,
        rack=rack,
        electrical_rack_ids=electrical_ids,
        element=element,
        placement=placement,
        binding=binding,
    )


def _existing_objects(site):
    elements = {
        element.slug: element
        for element in PhysicalElement.objects.filter(
            site=site,
            slug__startswith=madison_cad_object_slug(site, MADISON_RACK_FOOTPRINT_PREFIX),
        )
        .select_related("element_type", "physical_space")
        .order_by("slug")
    }
    element_type = ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False)
    placements = {
        placement.slug: placement
        for placement in SpatialPlacement.objects.filter(
            spatial_frame__site=site,
            assigned_object_type=element_type,
            assigned_object_id__in=[element.pk for element in elements.values()],
        ).order_by("slug")
    }
    bindings = {
        binding.physical_element.slug: binding
        for binding in PhysicalObjectBinding.objects.filter(
            physical_element_id__in=[element.pk for element in elements.values()],
            assigned_object_type=ContentType.objects.get_for_model(Rack, for_concrete_model=False),
        )
        .select_related("physical_element", "spatial_placement", "assigned_object_type")
        .order_by("physical_element__slug", "pk")
        if binding.physical_element_id
    }
    return {
        "elements": elements,
        "placements": placements,
        "bindings": bindings,
        "rack_by_slot": _rack_by_slot(site),
    }


def _rack_by_slot(site):
    by_slot = {}
    for rack in Rack.objects.filter(site=site).prefetch_related("tags").order_by("name"):
        slot = _slot_for_rack(rack)
        if slot is not None:
            by_slot.setdefault(slot, rack)
        if DIRECT_WORKBOOK_SLOT_PATTERN.fullmatch(rack.name):
            by_slot.setdefault(rack.name, rack)
    return by_slot


def _slot_for_rack(rack):
    if DIRECT_WORKBOOK_SLOT_PATTERN.fullmatch(rack.name):
        return rack.name
    mapped = slot_for_electrical_rack_id(rack.name)
    if mapped:
        return mapped
    for tag in rack.tags.all():
        slug = getattr(tag, "slug", "")
        if slug.startswith(ROW_ID_TAG_PREFIX):
            slot = slug[len(ROW_ID_TAG_PREFIX):].upper()
            if DIRECT_WORKBOOK_SLOT_PATTERN.fullmatch(slot):
                return slot
    return None


def _rack_boundary_for_slot(space, physical_slot):
    row_letter, slot_number = _slot_parts(physical_slot)
    geometry = space.boundary_geometry or {}
    space_x = _decimal(geometry["x"])
    space_y = _decimal(geometry["y"])
    space_width = _decimal(geometry["width"])
    space_depth = _decimal(geometry.get("depth") or geometry.get("height"))

    margin_x = space_width * Decimal("0.030")
    margin_y = space_depth * Decimal("0.080")
    usable_width = max_decimal(space_width - (margin_x * 2), Decimal("1.000"))
    usable_depth = max_decimal(space_depth - (margin_y * 2), Decimal("1.000"))
    slot_pitch = usable_width / Decimal("26")
    pair_depth = usable_depth / Decimal("3")
    lane_depth = pair_depth / Decimal("2")
    rack_width = min_decimal(max_decimal(slot_pitch * Decimal("0.52"), Decimal("1.500")), slot_pitch * Decimal("0.86"))
    rack_depth = min_decimal(max_decimal(lane_depth * Decimal("0.72"), Decimal("2.000")), lane_depth * Decimal("0.92"))
    x = space_x + margin_x + (slot_pitch * Decimal(slot_number - 1)) + ((slot_pitch - rack_width) / Decimal("2"))
    y = (
        space_y
        + margin_y
        + (pair_depth * Decimal(ROW_PAIR_INDEX[row_letter]))
        + (lane_depth * Decimal(ROW_LANE_INDEX[row_letter]))
        + ((lane_depth - rack_depth) / Decimal("2"))
    )
    return _rectangle_boundary(
        _quantize(x),
        _quantize(y),
        _quantize(rack_width),
        _quantize(rack_depth),
        coordinate_source="madison_rack_cabinet_layout",
    )


def _ensure_layout_source(site, *, manifest_path="", schedule_path=""):
    document, _ = _upsert(
        PlantSourceDocument,
        madison_cad_object_slug(site, MADISON_RACK_LAYOUT_SOURCE_KEY),
        {
            "name": _name(f"{site.name} Madison Rack And Cabinet Layout Source"),
            "site": site,
            "location": None,
            "source_type": PlantSourceTypeChoices.TYPE_WORKBOOK if manifest_path else PlantSourceTypeChoices.TYPE_OTHER,
            "discipline": PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            "document_id": "MAD1-RACK-CABINET-LAYOUT",
            "revision": "",
            "source_uri": manifest_path or schedule_path or "",
            "metadata": {
                "source_system": "madison_rack_cabinet_layout",
                "manifest_path": manifest_path,
                "cabinet_schedule_path": schedule_path,
                "review_state": MADISON_RACK_FOOTPRINT_REVIEW_STATE,
            },
        },
    )
    sheet, _ = _upsert(
        PlantSourceSheet,
        madison_cad_object_slug(site, MADISON_RACK_LAYOUT_SHEET_KEY),
        {
            "name": _name(f"{site.name} Madison Rack Cabinet Layout Sheet"),
            "source_document": document,
            "sheet_number": "MAD1-RACK-CABINET-LAYOUT",
            "title": "Madison rack/cabinet footprint source",
            "scale": "",
            "page_index": 1,
            "metadata": {
                "source_system": "madison_rack_cabinet_layout",
                "manifest_path": manifest_path,
                "cabinet_schedule_path": schedule_path,
            },
        },
    )
    layer, _ = _upsert(
        PlantSourceLayer,
        madison_cad_object_slug(site, MADISON_RACK_LAYOUT_LAYER_KEY),
        {
            "name": _name(f"{site.name} Madison Rack Footprint Layout Layer"),
            "source_sheet": sheet,
            "layer_name": "MADISON_RACK_FOOTPRINTS",
            "layer_kind": PlantSourceLayerKindChoices.KIND_RACK_LAYOUT,
            "discipline": PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            "is_visible": True,
            "metadata": {
                "source_system": "madison_rack_cabinet_layout",
                "review_state": MADISON_RACK_FOOTPRINT_REVIEW_STATE,
            },
        },
    )
    return document, sheet, layer


def _layout_source_document(site):
    return PlantSourceDocument.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_RACK_LAYOUT_SOURCE_KEY),
    ).first()


def _ensure_rack_footprint_type(site):
    element_type, _ = _upsert(
        PhysicalElementType,
        madison_cad_object_slug(site, MADISON_RACK_FOOTPRINT_TYPE_KEY),
        {
            "name": _name(f"{site.name} Rack Footprint"),
            "discipline": PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            "element_kind": PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
            "default_width": None,
            "default_depth": None,
            "default_height": None,
            "default_color": "20c997",
            "symbol_key": "rack-footprint",
            "is_pathway": False,
            "is_supporting_structure": False,
            "metadata": {
                "source_system": "madison_rack_cabinet_layout",
            },
        },
    )
    return element_type


def _upsert_element(candidate, *, element_type, reviewed_at, reviewer_name):
    record = candidate.source_record
    existing = candidate.element
    created = existing is None
    element = existing or PhysicalElement(slug=candidate.slug)
    metadata = dict((existing.metadata if existing is not None else {}) or {})
    approval_valid = (
        existing is not None
        and existing.confidence == SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
        and metadata.get("review_state") == MADISON_RACK_FOOTPRINT_APPROVED_STATE
        and existing.physical_space_id == candidate.physical_space.pk
    )
    metadata.update(
        {
            "source_system": "madison_rack_cabinet_layout",
            "physical_slot": record.physical_slot,
            "source_label": record.source_label,
            "source_role_slug": record.role_slug,
            "source_role_name": record.role_name,
            "source_record": record.metadata,
            "electrical_rack_ids": list(candidate.electrical_rack_ids),
            "matched_netbox_rack_id": candidate.rack.pk if candidate.rack is not None else None,
            "matched_netbox_rack_name": candidate.rack.name if candidate.rack is not None else "",
            "footprint_status": (
                MADISON_RACK_FOOTPRINT_APPROVED_STATE
                if approval_valid
                else MADISON_RACK_FOOTPRINT_REVIEW_STATE
            ),
            "review_state": (
                MADISON_RACK_FOOTPRINT_APPROVED_STATE
                if approval_valid
                else MADISON_RACK_FOOTPRINT_REVIEW_STATE
            ),
            "review_requested_by": reviewer_name,
            "review_requested_at": reviewed_at.isoformat(),
        }
    )
    defaults = {
        "name": candidate.name,
        "element_type": element_type,
        "site": candidate.physical_space.site,
        "location": candidate.physical_space.location,
        "physical_space": candidate.physical_space,
        "label": record.physical_slot,
        "role": "rack_footprint",
        "source_label": record.source_label or record.physical_slot,
        "confidence": (
            SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
            if approval_valid
            else SpatialConfidenceChoices.CONFIDENCE_DERIVED
        ),
        "metadata": metadata,
    }
    return _save_changed(element, defaults, created=created)


def _upsert_placement(candidate, *, element, reviewed_at, reviewer_name):
    created = candidate.placement is None
    placement = candidate.placement or SpatialPlacement(slug=f"{candidate.slug}-placement"[:100])
    geometry = candidate.boundary_geometry
    metadata = dict((candidate.placement.metadata if candidate.placement is not None else {}) or {})
    approval_valid = (
        candidate.placement is not None
        and candidate.placement.confidence == SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
        and metadata.get("review_state") == MADISON_RACK_FOOTPRINT_APPROVED_STATE
    )
    metadata.update(
        {
            "source_system": "madison_rack_cabinet_layout",
            "physical_slot": candidate.source_record.physical_slot,
            "review_state": (
                MADISON_RACK_FOOTPRINT_APPROVED_STATE
                if approval_valid
                else MADISON_RACK_FOOTPRINT_REVIEW_STATE
            ),
            "review_requested_by": reviewer_name,
            "review_requested_at": reviewed_at.isoformat(),
        }
    )
    defaults = {
        "name": _name(f"{candidate.physical_space.site.name} Rack {candidate.source_record.physical_slot} Placement"),
        "spatial_frame": candidate.physical_space.spatial_frame,
        "assigned_object_type": ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False),
        "assigned_object_id": element.pk,
        "x": _decimal(geometry["x"]),
        "y": _decimal(geometry["y"]),
        "z": None,
        "width": _decimal(geometry["width"]),
        "depth": _decimal(geometry["depth"]),
        "height": None,
        "rotation_degrees": Decimal("0.00"),
        "anchor": SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
        "placement_kind": SpatialPlacementKindChoices.KIND_INFERRED,
        "confidence": (
            SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
            if approval_valid
            else SpatialConfidenceChoices.CONFIDENCE_DERIVED
        ),
        "source_document": "Madison rack/cabinet layout",
        "source_ref": f"madison:rack-footprint:{candidate.source_record.physical_slot.lower()}",
        "metadata": metadata,
    }
    return _save_changed(placement, defaults, created=created)


def _upsert_binding(candidate, *, element, placement, reviewed_at, reviewer_name):
    created = candidate.binding is None
    binding = candidate.binding or PhysicalObjectBinding(slug=f"{candidate.slug}-netbox-rack-binding"[:100])
    metadata = dict((candidate.binding.metadata if candidate.binding is not None else {}) or {})
    approval_valid = (
        candidate.binding is not None
        and candidate.binding.confidence == SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
        and metadata.get("review_state") == MADISON_RACK_FOOTPRINT_APPROVED_STATE
    )
    metadata.update(
        {
            "source_system": "madison_rack_cabinet_layout",
            "physical_slot": candidate.source_record.physical_slot,
            "source_label": candidate.source_record.source_label,
            "electrical_rack_ids": list(candidate.electrical_rack_ids),
            "review_state": (
                MADISON_RACK_FOOTPRINT_APPROVED_STATE
                if approval_valid
                else MADISON_RACK_FOOTPRINT_REVIEW_STATE
            ),
            "binding_status": (
                MADISON_RACK_FOOTPRINT_APPROVED_STATE
                if approval_valid
                else MADISON_RACK_FOOTPRINT_REVIEW_STATE
            ),
            "review_requested_by": reviewer_name,
            "review_requested_at": reviewed_at.isoformat(),
        }
    )
    defaults = {
        "name": _name(f"{candidate.source_record.physical_slot} NetBox Rack Binding"),
        "physical_element": element,
        "spatial_placement": placement,
        "assigned_object_type": ContentType.objects.get_for_model(Rack, for_concrete_model=False),
        "assigned_object_id": candidate.rack.pk,
        "binding_role": PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
        "confidence": (
            SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
            if approval_valid
            else SpatialConfidenceChoices.CONFIDENCE_DERIVED
        ),
        "is_primary": approval_valid,
        "metadata": metadata,
    }
    return _save_changed(binding, defaults, created=created)


def _upsert_provenance(
    candidate,
    *,
    element,
    placement,
    binding,
    source_document,
    source_sheet,
    source_layer,
    extracted_at,
):
    actions = []
    for assigned_object in (element, placement, binding):
        if assigned_object is None:
            continue
        object_type = ContentType.objects.get_for_model(type(assigned_object), for_concrete_model=False)
        source_ref = f"madison:rack-footprint:{candidate.source_record.physical_slot.lower()}"
        slug = stable_slug(assigned_object.slug, "madison-rack-footprint-provenance")
        metadata = {
            "source_system": "madison_rack_cabinet_layout",
            "physical_slot": candidate.source_record.physical_slot,
            "source_label": candidate.source_record.source_label,
            "source_role_slug": candidate.source_record.role_slug,
            "electrical_rack_ids": list(candidate.electrical_rack_ids),
            "review_state": (getattr(assigned_object, "metadata", {}) or {}).get(
                "review_state",
                MADISON_RACK_FOOTPRINT_REVIEW_STATE,
            ),
        }
        is_approved = metadata["review_state"] == MADISON_RACK_FOOTPRINT_APPROVED_STATE
        provenance = PlantProvenance.objects.filter(slug=slug).first()
        created = provenance is None
        provenance = provenance or PlantProvenance(slug=slug)
        _, action = _save_changed(
            provenance,
            {
                "name": _name(f"{assigned_object.name} Madison Rack Footprint Provenance"),
                "assigned_object_type": object_type,
                "assigned_object_id": assigned_object.pk,
                "source_document": source_document,
                "source_sheet": source_sheet,
                "source_layer": source_layer,
                "extraction_method": PlantExtractionMethodChoices.METHOD_RECONCILIATION,
                "source_ref": source_ref,
                "confidence": (
                    SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE
                    if is_approved
                    else SpatialConfidenceChoices.CONFIDENCE_DERIVED
                ),
                "is_authoritative": is_approved,
                "extracted_at": extracted_at,
                "metadata": metadata,
            },
            created=created,
        )
        actions.append(action)
    return tuple(actions)


def _approve_candidate(binding, *, reviewer_name, approved_at, notes):
    changed = False
    objects = [binding]
    if binding.physical_element_id:
        objects.append(binding.physical_element)
    if binding.spatial_placement_id:
        objects.append(binding.spatial_placement)
    for obj in objects:
        metadata = dict(obj.metadata or {})
        metadata.update(
            {
                "review_state": MADISON_RACK_FOOTPRINT_APPROVED_STATE,
                "binding_status": MADISON_RACK_FOOTPRINT_APPROVED_STATE,
                "approved_by": reviewer_name,
                "approved_at": approved_at.isoformat(),
                "approval_notes": notes,
            }
        )
        defaults = {
            "confidence": SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            "metadata": metadata,
        }
        if isinstance(obj, PhysicalObjectBinding):
            defaults["is_primary"] = True
        if _assign_changed(obj, defaults, created=False):
            obj.full_clean()
            obj.save()
            changed = True

    for provenance in PlantProvenance.objects.filter(
        source_ref=f"madison:rack-footprint:{(binding.metadata or {}).get('physical_slot', '').lower()}",
    ):
        metadata = dict(provenance.metadata or {})
        metadata.update(
            {
                "review_state": MADISON_RACK_FOOTPRINT_APPROVED_STATE,
                "approved_by": reviewer_name,
                "approved_at": approved_at.isoformat(),
                "approval_notes": notes,
            }
        )
        defaults = {
            "confidence": SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
            "is_authoritative": True,
            "metadata": metadata,
        }
        if _assign_changed(provenance, defaults, created=False):
            provenance.full_clean()
            provenance.save()
            changed = True
    return changed


def _upsert(model, slug, defaults):
    instance = model.objects.filter(slug=slug).order_by("pk").first()
    created = instance is None
    instance = instance or model(slug=slug)
    return _save_changed(instance, defaults, created=created)


def _save_changed(instance, defaults, *, created):
    changed = _assign_changed(instance, defaults, created=created)
    if changed:
        instance.full_clean()
        instance.save()
    if created:
        return instance, "created"
    if changed:
        return instance, "updated"
    return instance, "unchanged"


def _assign_changed(instance, defaults, *, created):
    changed = created
    for field_name, value in defaults.items():
        if created:
            setattr(instance, field_name, value)
            continue
        if getattr(instance, field_name) != value:
            setattr(instance, field_name, value)
            changed = True
    return changed


def _resolve_site(site):
    if isinstance(site, Site):
        return site
    return Site.objects.filter(slug=str(site)).first()


def _first_existing_path(explicit_path, fallback_paths):
    if explicit_path:
        path = Path(explicit_path).expanduser()
        return path if path.exists() else None
    for path in fallback_paths:
        if path.exists():
            return path
    return None


def _slot_parts(physical_slot):
    match = DIRECT_WORKBOOK_SLOT_PATTERN.fullmatch(str(physical_slot or "").upper())
    if not match:
        return None
    return match.group("row"), int(match.group("slot"))


def _slot_sort_key(physical_slot):
    parts = _slot_parts(physical_slot)
    if parts is None:
        return ("Z", 999)
    return parts


def _data_hall_for_slot(slot):
    row_letter, _ = _slot_parts(slot)
    return "Data Hall 2" if row_letter < "M" else "Data Hall 1"


def _rect_is_usable(geometry):
    try:
        return (
            geometry.get("type") == "rectangle"
            and _decimal(geometry.get("width")) > 0
            and _decimal(geometry.get("depth") or geometry.get("height")) > 0
        )
    except Exception:
        return False


def _rectangle_boundary(x, y, width, depth, *, coordinate_source):
    return {
        "type": "rectangle",
        "anchor": SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
        "x": _decimal_string(x),
        "y": _decimal_string(y),
        "width": _decimal_string(width),
        "depth": _decimal_string(depth),
        "x_min": _decimal_string(x),
        "x_max": _decimal_string(x + width),
        "y_min": _decimal_string(y),
        "y_max": _decimal_string(y + depth),
        "coordinate_source": coordinate_source,
    }


def _decimal(value):
    if value in (None, ""):
        return Decimal("0.000")
    return Decimal(str(value)).quantize(Decimal("0.001"))


def _quantize(value):
    return Decimal(value).quantize(Decimal("0.001"))


def _decimal_string(value):
    return f"{_quantize(value):.3f}"


def max_decimal(first, second):
    return first if first >= second else second


def min_decimal(first, second):
    return first if first <= second else second


def _reviewer_name(reviewer):
    if reviewer is None:
        return ""
    if isinstance(reviewer, str):
        return reviewer
    return getattr(reviewer, "get_username", lambda: str(reviewer))()


def _name(value):
    return str(value)[:100]


def stable_slug(*parts, max_length=100):
    raw = "-".join(str(part) for part in parts if part not in (None, ""))
    base = slugify(raw) or "object"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:8]
    suffix = f"-{digest}"
    return f"{base[: max_length - len(suffix)]}{suffix}"
