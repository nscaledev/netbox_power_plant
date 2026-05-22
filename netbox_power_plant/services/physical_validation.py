from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q

from dcim.models import Rack

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PowerFindingSeverityChoices,
    SpatialAnchorChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    SpatialPlacement,
)
from netbox_power_plant.services.physical_plant import build_physical_scope_summary


@dataclass(frozen=True)
class PhysicalPlantValidationFinding:
    finding_type: str
    message: str
    object: object | None = None
    related_object: object | None = None
    severity: str = PowerFindingSeverityChoices.SEVERITY_WARNING
    details: dict | None = None


@dataclass(frozen=True)
class PhysicalPlantHealthSummary:
    power_system: object | None
    site: object | None
    location: object | None
    scope_summary: dict
    findings: tuple[PhysicalPlantValidationFinding, ...]
    finding_counts: dict[str, int]

    @property
    def finding_count(self):
        return len(self.findings)

    @property
    def is_healthy(self):
        return self.finding_count == 0

    @property
    def top_findings(self):
        return self.findings[:5]


def build_physical_plant_health_summary(power_system=None, *, site=None, location=None) -> PhysicalPlantHealthSummary:
    site, location = _resolve_scope(power_system, site=site, location=location)
    findings = run_physical_plant_checks(power_system=power_system, site=site, location=location)
    counts = Counter(finding.finding_type for finding in findings)
    return PhysicalPlantHealthSummary(
        power_system=power_system,
        site=site,
        location=location,
        scope_summary=build_physical_scope_summary(site=site, location=location),
        findings=findings,
        finding_counts=dict(counts),
    )


def run_physical_plant_checks(
    power_system=None,
    *,
    site=None,
    location=None,
) -> tuple[PhysicalPlantValidationFinding, ...]:
    site, location = _resolve_scope(power_system, site=site, location=location)
    findings = []

    elements = _scope_queryset(
        PhysicalElement.objects.select_related("element_type", "site", "location", "physical_space"),
        site=site,
        location=location,
    )
    placements = _placement_scope_queryset(
        SpatialPlacement.objects.select_related("spatial_frame", "assigned_object_type"),
        site=site,
        location=location,
    )
    bindings = _binding_scope_queryset(
        PhysicalObjectBinding.objects.select_related(
            "assigned_object_type",
            "physical_element",
            "physical_element__element_type",
            "physical_element__site",
            "physical_element__location",
            "spatial_placement",
            "spatial_placement__spatial_frame",
        ),
        site=site,
        location=location,
    )
    racks = _scope_queryset(Rack.objects.select_related("site", "location"), site=site, location=location)
    source_documents = _scope_queryset(
        PlantSourceDocument.objects.select_related("site", "location"),
        site=site,
        location=location,
    )

    findings.extend(_unbound_element_findings(elements))
    findings.extend(_unplaced_element_findings(elements))
    findings.extend(_placement_geometry_findings(placements))
    findings.extend(_binding_scope_findings(bindings))
    findings.extend(_duplicate_primary_binding_findings(bindings))
    findings.extend(_unbound_netbox_rack_findings(racks))
    findings.extend(_duplicate_rack_footprint_binding_findings(racks))
    findings.extend(_overlapping_rack_footprint_placement_findings(placements))
    findings.extend(_missing_provenance_findings(elements))
    findings.extend(_source_document_coverage_findings(source_documents))

    return tuple(findings)


def _resolve_scope(power_system=None, *, site=None, location=None):
    if power_system is not None:
        site = site or power_system.site
        location = location if location is not None else power_system.location
    return site, location


def _unbound_element_findings(elements):
    for element in elements.filter(object_bindings__isnull=True).distinct():
        yield PhysicalPlantValidationFinding(
            finding_type="unbound_physical_element",
            message=f"Physical element {element.name} is not bound to a NetBox or plugin object.",
            object=element,
            severity=PowerFindingSeverityChoices.SEVERITY_INFO,
        )


def _unplaced_element_findings(elements):
    element_type = ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False)
    for element in elements:
        if SpatialPlacement.objects.filter(
            assigned_object_type=element_type,
            assigned_object_id=element.pk,
        ).exists():
            continue
        if element.object_bindings.filter(spatial_placement__isnull=False).exists():
            continue
        yield PhysicalPlantValidationFinding(
            finding_type="unplaced_physical_element",
            message=f"Physical element {element.name} has no spatial placement.",
            object=element,
        )


def _placement_geometry_findings(placements):
    for placement in placements:
        yield from _frame_bounds_findings(placement)
        yield from _space_elevation_findings(placement)


def _frame_bounds_findings(placement):
    frame = placement.spatial_frame
    if frame.width is None or frame.height is None:
        return

    min_x, min_y, max_x, max_y = _placement_extent(placement)
    if min_x < 0 or min_y < 0 or max_x > frame.width or max_y > frame.height:
        yield PhysicalPlantValidationFinding(
            finding_type="placement_outside_frame_bounds",
            message=f"Spatial placement {placement.name} extends outside spatial frame {frame.name}.",
            object=placement,
            related_object=frame,
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            details={
                "extent": [str(min_x), str(min_y), str(max_x), str(max_y)],
                "frame_size": [str(frame.width), str(frame.height)],
            },
        )


def _space_elevation_findings(placement):
    element = _physical_element_for_placement(placement)
    if element is None or element.physical_space_id is None:
        return

    space = element.physical_space
    if space.z_min is None and space.z_max is None:
        return

    if placement.z is None:
        yield PhysicalPlantValidationFinding(
            finding_type="missing_z_coordinate",
            message=(
                f"Spatial placement {placement.name} is in elevation-bounded space {space.name} "
                "but has no z coordinate."
            ),
            object=placement,
            related_object=space,
        )
        return

    placement_top = placement.z + _placement_height(placement, element)
    if space.z_min is not None and placement.z < space.z_min:
        yield PhysicalPlantValidationFinding(
            finding_type="placement_outside_space_elevation",
            message=f"Spatial placement {placement.name} is below the elevation bounds for {space.name}.",
            object=placement,
            related_object=space,
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            details={"z": str(placement.z), "z_min": str(space.z_min)},
        )
    if space.z_max is not None and placement_top > space.z_max:
        yield PhysicalPlantValidationFinding(
            finding_type="placement_outside_space_elevation",
            message=f"Spatial placement {placement.name} is above the elevation bounds for {space.name}.",
            object=placement,
            related_object=space,
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            details={"z_top": str(placement_top), "z_max": str(space.z_max)},
        )


def _binding_scope_findings(bindings):
    for binding in bindings:
        if binding.physical_element is None or binding.assigned_object is None:
            continue

        assigned_site_id = _assigned_object_site_id(binding.assigned_object)
        if assigned_site_id and assigned_site_id != binding.physical_element.site_id:
            yield PhysicalPlantValidationFinding(
                finding_type="binding_site_mismatch",
                message=f"Physical binding {binding.name} links objects from different sites.",
                object=binding,
                related_object=binding.physical_element,
                severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            )
            continue

        assigned_location_id = _assigned_object_location_id(binding.assigned_object)
        if (
            assigned_location_id
            and binding.physical_element.location_id
            and assigned_location_id != binding.physical_element.location_id
        ):
            yield PhysicalPlantValidationFinding(
                finding_type="binding_location_mismatch",
                message=f"Physical binding {binding.name} links objects from different locations.",
                object=binding,
                related_object=binding.physical_element,
            )


def _duplicate_primary_binding_findings(bindings):
    duplicate_keys = bindings.filter(is_primary=True).values(
        "assigned_object_type",
        "assigned_object_id",
    ).annotate(
        binding_count=Count("pk"),
    ).filter(binding_count__gt=1)

    for duplicate in duplicate_keys:
        first_binding = bindings.filter(
            is_primary=True,
            assigned_object_type_id=duplicate["assigned_object_type"],
            assigned_object_id=duplicate["assigned_object_id"],
        ).order_by("pk").first()
        yield PhysicalPlantValidationFinding(
            finding_type="duplicate_primary_binding",
            message=f"Assigned object has {duplicate['binding_count']} primary physical bindings.",
            object=first_binding,
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            details={"binding_count": duplicate["binding_count"]},
        )


def _unbound_netbox_rack_findings(racks):
    rack_type = ContentType.objects.get_for_model(Rack, for_concrete_model=False)
    bound_rack_ids = PhysicalObjectBinding.objects.filter(
        assigned_object_type=rack_type,
        physical_element__element_type__element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
    ).values("assigned_object_id")

    for rack in racks.exclude(pk__in=bound_rack_ids):
        yield PhysicalPlantValidationFinding(
            finding_type="unbound_netbox_rack",
            message=f"NetBox rack {rack.name} has no physical rack footprint binding.",
            object=rack,
        )


def _duplicate_rack_footprint_binding_findings(racks):
    rack_type = ContentType.objects.get_for_model(Rack, for_concrete_model=False)
    footprint_bindings = PhysicalObjectBinding.objects.select_related(
        "assigned_object_type",
        "physical_element",
        "physical_element__element_type",
    ).filter(
        assigned_object_type=rack_type,
        assigned_object_id__in=racks.values("pk"),
        physical_element__element_type__element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
    )
    duplicate_keys = footprint_bindings.values("assigned_object_id").annotate(
        binding_count=Count("pk"),
        element_count=Count("physical_element", distinct=True),
    ).filter(element_count__gt=1)

    for duplicate in duplicate_keys:
        first_binding = footprint_bindings.filter(
            assigned_object_id=duplicate["assigned_object_id"],
        ).order_by("pk").first()
        yield PhysicalPlantValidationFinding(
            finding_type="duplicate_rack_footprint_binding",
            message=f"NetBox rack has {duplicate['element_count']} physical rack footprint elements bound to it.",
            object=first_binding,
            related_object=first_binding.assigned_object if first_binding is not None else None,
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            details={
                "assigned_object_id": duplicate["assigned_object_id"],
                "binding_count": duplicate["binding_count"],
                "element_count": duplicate["element_count"],
            },
        )


def _overlapping_rack_footprint_placement_findings(placements):
    placements_by_coordinate = {}
    for placement in placements.order_by("pk"):
        if not _is_rack_footprint_placement(placement):
            continue
        key = (placement.spatial_frame_id, placement.x, placement.y, placement.z)
        placements_by_coordinate.setdefault(key, []).append(placement)

    for (frame_id, x, y, z), matching_placements in placements_by_coordinate.items():
        if len(matching_placements) < 2:
            continue
        first_placement = matching_placements[0]
        yield PhysicalPlantValidationFinding(
            finding_type="overlapping_rack_footprint_placement",
            message=(
                f"{len(matching_placements)} rack footprint placements share the same frame and coordinates."
            ),
            object=first_placement,
            related_object=first_placement.spatial_frame,
            severity=PowerFindingSeverityChoices.SEVERITY_ERROR,
            details={
                "spatial_frame_id": frame_id,
                "x": str(x),
                "y": str(y),
                "z": str(z) if z is not None else None,
                "placement_count": len(matching_placements),
            },
        )


def _missing_provenance_findings(elements):
    element_type = ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False)
    for element in elements:
        if not _looks_blueprint_derived(element):
            continue
        if PlantProvenance.objects.filter(
            assigned_object_type=element_type,
            assigned_object_id=element.pk,
        ).exists():
            continue
        yield PhysicalPlantValidationFinding(
            finding_type="source_provenance_missing",
            message=f"Blueprint-derived physical element {element.name} has no provenance record.",
            object=element,
        )


def _source_document_coverage_findings(source_documents):
    for source_document in source_documents:
        provenance_records = _provenance_for_source_document(source_document)
        if not provenance_records.exists():
            yield PhysicalPlantValidationFinding(
                finding_type="source_document_without_provenance",
                message=f"Source document {source_document.name} has no modeled provenance records.",
                object=source_document,
            )
            continue

        if not _provenance_records_have_modeled_object(provenance_records):
            yield PhysicalPlantValidationFinding(
                finding_type="source_document_without_modeled_objects",
                message=f"Source document {source_document.name} has provenance but no modeled objects.",
                object=source_document,
            )


def _physical_element_for_placement(placement):
    if placement.assigned_object_type_id:
        model = placement.assigned_object_type.model_class()
        if model is PhysicalElement:
            return placement.assigned_object

    binding = placement.object_bindings.select_related(
        "physical_element",
        "physical_element__element_type",
        "physical_element__physical_space",
    ).first()
    return binding.physical_element if binding is not None else None


def _placement_extent(placement):
    width = placement.width or Decimal("0")
    depth = placement.depth or Decimal("0")
    x = placement.x
    y = placement.y

    if placement.anchor == SpatialAnchorChoices.ANCHOR_CENTER:
        half_width = width / 2
        half_depth = depth / 2
        return x - half_width, y - half_depth, x + half_width, y + half_depth
    if placement.anchor == SpatialAnchorChoices.ANCHOR_UPPER_LEFT:
        return x, y - depth, x + width, y
    if placement.anchor == SpatialAnchorChoices.ANCHOR_LOWER_RIGHT:
        return x - width, y, x, y + depth
    if placement.anchor == SpatialAnchorChoices.ANCHOR_UPPER_RIGHT:
        return x - width, y - depth, x, y
    return x, y, x + width, y + depth


def _placement_height(placement, element):
    return placement.height or element.element_type.default_height or Decimal("0")


def _is_rack_footprint_placement(placement):
    rack_type = ContentType.objects.get_for_model(Rack, for_concrete_model=False)
    if placement.assigned_object_type_id:
        model = placement.assigned_object_type.model_class()
        if model is Rack:
            return True
        if model is PhysicalElement:
            return _is_rack_footprint_element(placement.assigned_object)

    return placement.object_bindings.filter(
        Q(assigned_object_type=rack_type)
        | Q(physical_element__element_type__element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT)
    ).exists()


def _is_rack_footprint_element(element):
    if element is None:
        return False
    return element.element_type.element_kind == PhysicalElementKindChoices.KIND_RACK_FOOTPRINT


def _provenance_for_source_document(source_document):
    return PlantProvenance.objects.select_related("assigned_object_type").filter(
        Q(source_document=source_document)
        | Q(source_sheet__source_document=source_document)
        | Q(source_layer__source_sheet__source_document=source_document)
    ).distinct()


def _provenance_records_have_modeled_object(provenance_records):
    for record in provenance_records:
        if record.assigned_object is not None:
            return True
    return False


def _looks_blueprint_derived(element):
    return bool(
        element.source_label
        or element.metadata.get("source_key")
        or element.metadata.get("source_ref")
    )


def _scope_queryset(queryset, *, site=None, location=None):
    if site is not None:
        queryset = queryset.filter(site=site)
    if location is not None:
        queryset = queryset.filter(location=location)
    return queryset


def _placement_scope_queryset(queryset, *, site=None, location=None):
    if site is not None:
        queryset = queryset.filter(spatial_frame__site=site)
    if location is not None:
        queryset = queryset.filter(spatial_frame__location=location)
    return queryset


def _binding_scope_queryset(queryset, *, site=None, location=None):
    if site is None and location is None:
        return queryset

    element_scope = Q(physical_element__isnull=False)
    placement_scope = Q(spatial_placement__isnull=False)
    if site is not None:
        element_scope &= Q(physical_element__site=site)
        placement_scope &= Q(spatial_placement__spatial_frame__site=site)
    if location is not None:
        element_scope &= Q(physical_element__location=location)
        placement_scope &= Q(spatial_placement__spatial_frame__location=location)

    return queryset.filter(element_scope | placement_scope).distinct()


def _assigned_object_site_id(assigned_object):
    if hasattr(assigned_object, "site_id"):
        return assigned_object.site_id

    power_system = getattr(assigned_object, "power_system", None)
    if power_system is not None:
        return power_system.site_id

    node = getattr(assigned_object, "node", None)
    if node is not None:
        return node.site_id

    device = getattr(assigned_object, "device", None)
    if device is not None:
        return device.site_id

    rack = getattr(assigned_object, "rack", None)
    if rack is not None:
        return rack.site_id

    return None


def _assigned_object_location_id(assigned_object):
    if hasattr(assigned_object, "location_id"):
        return assigned_object.location_id

    power_system = getattr(assigned_object, "power_system", None)
    if power_system is not None:
        return power_system.location_id

    node = getattr(assigned_object, "node", None)
    if node is not None:
        return node.location_id

    device = getattr(assigned_object, "device", None)
    if device is not None:
        return device.location_id or (device.rack.location_id if device.rack_id else None)

    rack = getattr(assigned_object, "rack", None)
    if rack is not None:
        return rack.location_id

    return None
