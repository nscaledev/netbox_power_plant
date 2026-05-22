from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q

from dcim.models import Rack, Site

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalSpaceKindChoices,
    PowerFindingSeverityChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.madison_cad_materialization import (
    MADISON_CAD_CURRENT_BUILDING_PLACEMENT_KEY,
    MADISON_CAD_CURRENT_BUILDING_SPACE_KEY,
    MADISON_CAD_SITE_FRAME_KEY,
    MADISON_CAD_SITE_SPACE_KEY,
    MADISON_CAD_SOURCE_DOCUMENT_KEY,
    madison_cad_object_slug,
)
from netbox_power_plant.services.madison_space_decomposition import (
    MadisonDetailedSpaceDecompositionSummary,
    build_madison_detailed_space_decomposition_summary,
)
from netbox_power_plant.services.madison_rack_footprints import (
    MadisonRackFootprintSummary,
    build_madison_rack_footprint_summary,
)
from netbox_power_plant.services.physical_validation import run_physical_plant_checks


DEFAULT_MADISON_SITE_SLUG = "gs001"


@dataclass(frozen=True)
class MadisonCount:
    key: str
    label: str
    count: int


@dataclass(frozen=True)
class MadisonSourceDocumentSummary:
    document: PlantSourceDocument
    sheet_count: int
    layer_count: int


@dataclass(frozen=True)
class MadisonRackBindingSummary:
    binding: PhysicalObjectBinding
    rack: Rack | None
    physical_element: PhysicalElement | None
    spatial_placement: SpatialPlacement | None


@dataclass(frozen=True)
class MadisonCadUnderlayReviewSummary:
    source_document: PlantSourceDocument | None = None
    site_frame: SpatialFrame | None = None
    site_space: PhysicalSpace | None = None
    current_building_space: PhysicalSpace | None = None
    current_building_placement: SpatialPlacement | None = None
    calibration_status: str = ""
    review_state: str = ""
    source_units: str = ""
    rendered_underlay_image_uri: str = ""
    approved_by: str = ""
    approved_at: str = ""
    warnings: tuple[str, ...] = ()

    @property
    def materialized(self):
        return self.source_document is not None and self.site_frame is not None and self.site_space is not None

    @property
    def approved(self):
        return self.review_state == "approved"


@dataclass(frozen=True)
class MadisonUnderlayReviewSummary:
    site_slug: str
    site: Site | None = None
    source_document_count: int = 0
    source_sheet_count: int = 0
    source_layer_count: int = 0
    spatial_frame_count: int = 0
    physical_space_count: int = 0
    physical_element_count: int = 0
    rack_footprint_count: int = 0
    rack_binding_count: int = 0
    placed_element_count: int = 0
    unplaced_element_count: int = 0
    physical_validation_finding_count: int = 0
    source_documents: tuple[MadisonSourceDocumentSummary, ...] = ()
    spatial_frames: tuple[SpatialFrame, ...] = ()
    cad_underlay: MadisonCadUnderlayReviewSummary | None = None
    detailed_space_decomposition: MadisonDetailedSpaceDecompositionSummary | None = None
    rack_footprint_modeling: MadisonRackFootprintSummary | None = None
    physical_space_kind_counts: tuple[MadisonCount, ...] = ()
    rack_bindings: tuple[MadisonRackBindingSummary, ...] = ()
    validation_type_counts: tuple[MadisonCount, ...] = ()
    validation_severity_counts: tuple[MadisonCount, ...] = ()

    @property
    def site_found(self):
        return self.site is not None


def build_madison_underlay_review_summary(
    site_slug: str = DEFAULT_MADISON_SITE_SLUG,
) -> MadisonUnderlayReviewSummary:
    site = Site.objects.filter(slug=site_slug).first()
    if site is None:
        return MadisonUnderlayReviewSummary(site_slug=site_slug)

    source_documents = PlantSourceDocument.objects.filter(site=site)
    source_sheets = PlantSourceSheet.objects.filter(source_document__site=site)
    source_layers = PlantSourceLayer.objects.filter(source_sheet__source_document__site=site)
    spatial_frames = SpatialFrame.objects.filter(site=site).select_related("location", "parent_frame")
    physical_spaces = PhysicalSpace.objects.filter(site=site)
    physical_elements = PhysicalElement.objects.filter(site=site).select_related(
        "element_type",
        "location",
        "physical_space",
    )
    rack_footprints = physical_elements.filter(
        element_type__element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
    )
    rack_bindings = _rack_bindings_for_site(site)
    placed_element_ids = _placed_element_ids(physical_elements)
    findings = run_physical_plant_checks(site=site)

    return MadisonUnderlayReviewSummary(
        site_slug=site_slug,
        site=site,
        source_document_count=source_documents.count(),
        source_sheet_count=source_sheets.count(),
        source_layer_count=source_layers.count(),
        spatial_frame_count=spatial_frames.count(),
        physical_space_count=physical_spaces.count(),
        physical_element_count=physical_elements.count(),
        rack_footprint_count=rack_footprints.count(),
        rack_binding_count=rack_bindings.count(),
        placed_element_count=len(placed_element_ids),
        unplaced_element_count=physical_elements.exclude(pk__in=placed_element_ids).count(),
        physical_validation_finding_count=len(findings),
        source_documents=_source_document_rows(source_documents),
        spatial_frames=tuple(spatial_frames.order_by("location__name", "name", "pk")),
        cad_underlay=_cad_underlay_summary(site),
        detailed_space_decomposition=build_madison_detailed_space_decomposition_summary(site),
        rack_footprint_modeling=build_madison_rack_footprint_summary(site),
        physical_space_kind_counts=_physical_space_kind_counts(physical_spaces),
        rack_bindings=_rack_binding_rows(rack_bindings),
        validation_type_counts=_validation_type_counts(findings),
        validation_severity_counts=_validation_severity_counts(findings),
    )


def _cad_underlay_summary(site):
    source_document = PlantSourceDocument.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SOURCE_DOCUMENT_KEY),
    ).first()
    site_frame = SpatialFrame.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SITE_FRAME_KEY),
    ).first()
    site_space = PhysicalSpace.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_SITE_SPACE_KEY),
    ).first()
    current_building_space = PhysicalSpace.objects.filter(
        site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_SPACE_KEY),
    ).first()
    current_building_placement = SpatialPlacement.objects.filter(
        spatial_frame__site=site,
        slug=madison_cad_object_slug(site, MADISON_CAD_CURRENT_BUILDING_PLACEMENT_KEY),
    ).first()
    if not any((source_document, site_frame, site_space, current_building_space, current_building_placement)):
        return None
    metadata = source_document.metadata if source_document is not None else {}
    return MadisonCadUnderlayReviewSummary(
        source_document=source_document,
        site_frame=site_frame,
        site_space=site_space,
        current_building_space=current_building_space,
        current_building_placement=current_building_placement,
        calibration_status=metadata.get("calibration_status", ""),
        review_state=metadata.get("review_state", ""),
        source_units=metadata.get("source_units", ""),
        rendered_underlay_image_uri=metadata.get("rendered_underlay_image_uri", ""),
        approved_by=metadata.get("approved_by", ""),
        approved_at=metadata.get("approved_at", ""),
        warnings=tuple(metadata.get("warnings") or ()),
    )


def _source_document_rows(source_documents):
    return tuple(
        MadisonSourceDocumentSummary(
            document=document,
            sheet_count=document.sheet_count,
            layer_count=document.layer_count,
        )
        for document in source_documents.annotate(
            sheet_count=Count("sheets", distinct=True),
            layer_count=Count("sheets__layers", distinct=True),
        ).order_by("discipline", "name", "pk")
    )


def _physical_space_kind_counts(physical_spaces):
    choice_labels = dict(PhysicalSpaceKindChoices.CHOICES)
    return tuple(
        MadisonCount(
            key=row["space_kind"],
            label=choice_labels.get(row["space_kind"], _humanize(row["space_kind"])),
            count=row["count"],
        )
        for row in physical_spaces.values("space_kind").annotate(count=Count("pk")).order_by("space_kind")
    )


def _rack_bindings_for_site(site):
    rack_type = ContentType.objects.get_for_model(Rack, for_concrete_model=False)
    site_rack_ids = Rack.objects.filter(site=site).values("pk")
    return (
        PhysicalObjectBinding.objects.filter(assigned_object_type=rack_type)
        .filter(
            Q(assigned_object_id__in=site_rack_ids)
            | Q(physical_element__site=site)
            | Q(spatial_placement__spatial_frame__site=site)
        )
        .select_related(
            "assigned_object_type",
            "physical_element",
            "physical_element__element_type",
            "spatial_placement",
            "spatial_placement__spatial_frame",
        )
        .distinct()
        .order_by("physical_element__name", "spatial_placement__name", "assigned_object_id", "pk")
    )


def _rack_binding_rows(rack_bindings):
    bindings = tuple(rack_bindings)
    racks = Rack.objects.filter(
        pk__in={binding.assigned_object_id for binding in bindings},
    ).select_related("site", "location").in_bulk()
    return tuple(
        MadisonRackBindingSummary(
            binding=binding,
            rack=racks.get(binding.assigned_object_id),
            physical_element=binding.physical_element,
            spatial_placement=binding.spatial_placement,
        )
        for binding in bindings
    )


def _placed_element_ids(physical_elements):
    element_ids = tuple(physical_elements.values_list("pk", flat=True))
    if not element_ids:
        return set()

    element_type = ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False)
    directly_placed_ids = SpatialPlacement.objects.filter(
        assigned_object_type=element_type,
        assigned_object_id__in=element_ids,
    ).values_list("assigned_object_id", flat=True)
    binding_placed_ids = PhysicalObjectBinding.objects.filter(
        physical_element_id__in=element_ids,
        spatial_placement__isnull=False,
    ).values_list("physical_element_id", flat=True)
    return set(directly_placed_ids) | set(binding_placed_ids)


def _validation_type_counts(findings):
    counts = Counter(finding.finding_type for finding in findings)
    return tuple(
        MadisonCount(key=key, label=_humanize(key), count=count)
        for key, count in sorted(counts.items())
    )


def _validation_severity_counts(findings):
    counts = Counter(finding.severity for finding in findings)
    choice_labels = dict(PowerFindingSeverityChoices.CHOICES)
    severity_order = (
        PowerFindingSeverityChoices.SEVERITY_CRITICAL,
        PowerFindingSeverityChoices.SEVERITY_ERROR,
        PowerFindingSeverityChoices.SEVERITY_WARNING,
        PowerFindingSeverityChoices.SEVERITY_INFO,
    )
    return tuple(
        MadisonCount(
            key=severity,
            label=choice_labels.get(severity, _humanize(severity)),
            count=counts[severity],
        )
        for severity in severity_order
        if counts[severity]
    )


def _humanize(value):
    return str(value).replace("_", " ").strip().title()
