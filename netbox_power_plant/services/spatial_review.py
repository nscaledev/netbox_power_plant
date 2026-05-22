from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from dcim.models import Site

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalSpaceKindChoices,
    SpatialAnchorChoices,
    SpatialPlacementKindChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PhysicalSpace,
    SpatialFrame,
    SpatialPlacement,
)


STATUS_APPROVED = 'approved'
STATUS_OPERATOR_CORRECTED = 'operator_corrected'
STATUS_OPERATOR_REVIEW_REQUIRED = 'operator_review_required'
STATUS_UNKNOWN = 'unknown'

STATUS_LABELS = {
    STATUS_APPROVED: 'Approved',
    STATUS_OPERATOR_CORRECTED: 'Corrected, needs approval',
    STATUS_OPERATOR_REVIEW_REQUIRED: 'Needs review',
    STATUS_UNKNOWN: 'Unknown',
}

@dataclass(frozen=True)
class SpatialReviewSpacePrimitive:
    id: int
    label: str
    kind: str
    x: float
    y: float
    width: float
    depth: float
    confidence: str
    review_state: str
    boundary_status: str
    status: str
    status_label: str
    object_url: str | None = None
    source_document: str = ''
    source_ref: str = ''
    provenance_url: str | None = None
    coordinate_source: str = ''
    geometry_review_state: str = ''
    geometry_review_method: str = ''

    @property
    def kind_label(self) -> str:
        return _choice_label(PhysicalSpaceKindChoices.CHOICES, self.kind)

    @property
    def status_class(self) -> str:
        return self.status.replace('_', '-')


@dataclass(frozen=True)
class SpatialReviewElementSummary:
    id: int
    label: str
    kind: str
    role: str
    confidence: str
    object_url: str | None = None
    binding_count: int = 0
    primary_binding_label: str | None = None

    @property
    def kind_label(self) -> str:
        return _choice_label(PhysicalElementKindChoices.CHOICES, self.kind)


@dataclass(frozen=True)
class SpatialReviewPlacementPrimitive:
    id: int
    label: str
    object_type: str
    object_id: int
    object_label: str
    shape: str
    x: float
    y: float
    geometry_x: float
    geometry_y: float
    width: float | None = None
    depth: float | None = None
    rotation_degrees: float = 0
    placement_kind: str = ''
    confidence: str = ''
    review_state: str = ''
    status: str = 'placed'
    status_label_text: str = 'Placed'
    binding_label: str = ''
    binding_status: str = ''
    object_url: str | None = None
    placement_url: str | None = None

    @property
    def kind_label(self) -> str:
        return _choice_label(SpatialPlacementKindChoices.CHOICES, self.placement_kind)

    @property
    def status_label(self) -> str:
        return self.status_label_text

    @property
    def status_class(self) -> str:
        return self.status.replace('_', '-')


@dataclass(frozen=True)
class SpatialReviewBindingSummary:
    id: int
    label: str
    role: str
    confidence: str
    is_primary: bool
    physical_element_id: int | None
    spatial_placement_id: int | None
    assigned_object_type: str
    assigned_object_id: int
    assigned_object_label: str
    object_url: str | None = None
    binding_url: str | None = None


@dataclass(frozen=True)
class SpatialReviewMap:
    width: float
    height: float
    view_box: str
    unit_label: str
    spaces: tuple[SpatialReviewSpacePrimitive, ...] = ()
    elements: tuple[SpatialReviewElementSummary, ...] = ()
    placements: tuple[SpatialReviewPlacementPrimitive, ...] = ()
    bindings: tuple[SpatialReviewBindingSummary, ...] = ()
    status_counts: dict[str, int] = field(default_factory=dict)
    binding_counts: dict[str, int] = field(default_factory=dict)
    site_id: int | None = None
    site_slug: str | None = None
    frame_id: int | None = None
    frame_label: str = ''
    frame_url: str | None = None
    available_reason: str = ''

    @property
    def is_available(self) -> bool:
        return self.frame_id is not None and self.width > 0 and self.height > 0

    @property
    def unavailable_reason(self) -> str:
        return self.available_reason


def build_spatial_review_map(site_or_slug, *, frame=None, include_unreviewed=True) -> SpatialReviewMap:
    site = _resolve_site(site_or_slug)
    if site is None:
        return _empty_map('Site was not found.')

    spatial_frame = _resolve_frame(site, frame)
    if spatial_frame is None:
        return _empty_map('Spatial frame was not found.', site=site)

    width = _coerce_float(spatial_frame.width) or 0
    height = _coerce_float(spatial_frame.height) or 0
    if width <= 0 or height <= 0:
        return _empty_map('Spatial frame has no usable width or height.', site=site, frame=spatial_frame)

    spaces = _build_space_primitives(spatial_frame, include_unreviewed=include_unreviewed)
    placements = _build_placement_primitives(spatial_frame)
    elements = _collect_elements(site, spatial_frame, placements)
    bindings = _build_binding_summaries(elements, placements)
    elements = _with_binding_counts(elements, bindings)

    return SpatialReviewMap(
        width=width,
        height=height,
        view_box=f'0 0 {_format_number(width)} {_format_number(height)}',
        unit_label=spatial_frame.units or '',
        spaces=spaces,
        elements=elements,
        placements=placements,
        bindings=bindings,
        status_counts=_status_counts(spaces),
        binding_counts=_binding_counts(bindings),
        site_id=site.pk,
        site_slug=site.slug,
        frame_id=spatial_frame.pk,
        frame_label=str(spatial_frame),
        frame_url=_safe_absolute_url(spatial_frame),
    )


def _empty_map(reason, *, site=None, frame=None) -> SpatialReviewMap:
    return SpatialReviewMap(
        width=0,
        height=0,
        view_box='0 0 0 0',
        unit_label=getattr(frame, 'units', '') or '',
        status_counts={
            STATUS_APPROVED: 0,
            STATUS_OPERATOR_REVIEW_REQUIRED: 0,
            STATUS_UNKNOWN: 0,
        },
        binding_counts={},
        site_id=getattr(site, 'pk', None),
        site_slug=getattr(site, 'slug', None),
        frame_id=getattr(frame, 'pk', None),
        frame_label=str(frame) if frame is not None else '',
        frame_url=_safe_absolute_url(frame),
        available_reason=reason,
    )


def _resolve_site(site_or_slug):
    if isinstance(site_or_slug, Site):
        return site_or_slug
    if hasattr(site_or_slug, 'pk') and hasattr(site_or_slug, 'slug'):
        return site_or_slug
    if not site_or_slug:
        return None
    try:
        return Site.objects.get(slug=site_or_slug)
    except Site.DoesNotExist:
        return None


def _resolve_frame(site, frame):
    if isinstance(frame, SpatialFrame):
        return frame if frame.site_id == site.pk else None
    if frame:
        queryset = SpatialFrame.objects.filter(site=site)
        return queryset.filter(Q(slug=frame) | Q(name=frame)).order_by('pk').first()
    return SpatialFrame.objects.filter(site=site).order_by('location_id', 'pk').first()


def _build_space_primitives(spatial_frame, *, include_unreviewed):
    spaces = []
    queryset = (
        PhysicalSpace.objects
        .filter(site=spatial_frame.site, spatial_frame=spatial_frame)
        .order_by('parent_space_id', 'space_kind', 'name', 'pk')
    )

    for space in queryset:
        geometry = space.boundary_geometry or {}
        x = _coerce_float(geometry.get('x'))
        y = _coerce_float(geometry.get('y'))
        width = _coerce_float(geometry.get('width'))
        depth = _coerce_float(geometry.get('depth') or geometry.get('height'))
        if x is None or y is None or width is None or depth is None:
            continue

        metadata = space.metadata or {}
        review_state = metadata.get('review_state') or ''
        boundary_status = metadata.get('boundary_status') or ''
        geometry_review_state = metadata.get('geometry_review_state') or ''
        status = _review_status(review_state, boundary_status, geometry_review_state)
        if not include_unreviewed and status != STATUS_APPROVED:
            continue

        spaces.append(
            SpatialReviewSpacePrimitive(
                id=space.pk,
                label=space.name,
                kind=space.space_kind,
                x=x,
                y=y,
                width=width,
                depth=depth,
                confidence=space.confidence,
                review_state=review_state,
                boundary_status=boundary_status,
                status=status,
                status_label=STATUS_LABELS[status],
                object_url=_safe_absolute_url(space),
                source_document=space.source_document or '',
                source_ref=space.source_ref or '',
                provenance_url=_metadata_url(metadata),
                coordinate_source=geometry.get('coordinate_source', ''),
                geometry_review_state=geometry_review_state,
                geometry_review_method=metadata.get('geometry_review_method') or '',
            )
        )

    spaces.sort(key=lambda space: (space.width * space.depth, space.id), reverse=True)
    return tuple(spaces)


def _build_placement_primitives(spatial_frame):
    physical_element_type = ContentType.objects.get_for_model(PhysicalElement)
    placements = []
    queryset = (
        SpatialPlacement.objects
        .filter(spatial_frame=spatial_frame, assigned_object_type=physical_element_type)
        .order_by('placement_kind', 'name', 'pk')
    )

    for placement in queryset:
        x = _coerce_float(placement.x)
        y = _coerce_float(placement.y)
        if x is None or y is None or placement.assigned_object is None:
            continue

        width = _coerce_float(placement.width)
        depth = _coerce_float(placement.depth)
        geometry_x, geometry_y = _placement_geometry_origin(
            x=x,
            y=y,
            width=width,
            depth=depth,
            anchor=placement.anchor,
        )
        shape = 'rect' if width is not None and depth is not None and width > 0 and depth > 0 else 'point'
        obj = placement.assigned_object
        metadata = placement.metadata or {}
        review_state = metadata.get('review_state') or ''
        status, status_label = _placement_status(review_state)
        placements.append(
            SpatialReviewPlacementPrimitive(
                id=placement.pk,
                label=placement.name,
                object_type=placement.assigned_object_type.model,
                object_id=placement.assigned_object_id,
                object_label=_object_label(obj),
                shape=shape,
                x=x,
                y=y,
                geometry_x=geometry_x,
                geometry_y=geometry_y,
                width=width if shape == 'rect' else None,
                depth=depth if shape == 'rect' else None,
                rotation_degrees=_coerce_float(placement.rotation_degrees) or 0,
                placement_kind=placement.placement_kind,
                confidence=placement.confidence,
                review_state=review_state,
                status=status,
                status_label_text=status_label,
                binding_label=metadata.get('matched_netbox_rack_name') or metadata.get('physical_slot') or '',
                binding_status=metadata.get('binding_status') or '',
                object_url=_safe_absolute_url(obj),
                placement_url=_safe_absolute_url(placement),
            )
        )

    return tuple(placements)


def _placement_status(review_state):
    if review_state == STATUS_APPROVED:
        return STATUS_APPROVED, STATUS_LABELS[STATUS_APPROVED]
    if review_state == STATUS_OPERATOR_REVIEW_REQUIRED:
        return STATUS_OPERATOR_REVIEW_REQUIRED, STATUS_LABELS[STATUS_OPERATOR_REVIEW_REQUIRED]
    return 'placed', 'Placed'


def _placement_geometry_origin(*, x, y, width, depth, anchor):
    if width is None or depth is None or width <= 0 or depth <= 0:
        return x, y

    if anchor == SpatialAnchorChoices.ANCHOR_CENTER:
        source_left = x - (width / 2)
        source_bottom = y - (depth / 2)
    elif anchor == SpatialAnchorChoices.ANCHOR_LOWER_RIGHT:
        source_left = x - width
        source_bottom = y
    elif anchor == SpatialAnchorChoices.ANCHOR_UPPER_LEFT:
        source_left = x
        source_bottom = y - depth
    elif anchor == SpatialAnchorChoices.ANCHOR_UPPER_RIGHT:
        source_left = x - width
        source_bottom = y - depth
    else:
        source_left = x
        source_bottom = y

    return source_left, source_bottom


def _collect_elements(site, spatial_frame, placements):
    placement_element_ids = {placement.object_id for placement in placements}
    queryset = PhysicalElement.objects.filter(site=site).filter(
        Q(location=spatial_frame.location)
        | Q(physical_space__spatial_frame=spatial_frame)
        | Q(pk__in=placement_element_ids)
    ).select_related('element_type').distinct().order_by('element_type__element_kind', 'name', 'pk')

    return tuple(
        SpatialReviewElementSummary(
            id=element.pk,
            label=element.label or element.name,
            kind=element.element_type.element_kind,
            role=element.role,
            confidence=element.confidence,
            object_url=_safe_absolute_url(element),
        )
        for element in queryset
    )


def _build_binding_summaries(elements, placements):
    element_ids = {element.id for element in elements}
    placement_ids = {placement.id for placement in placements}
    if not element_ids and not placement_ids:
        return ()

    queryset = (
        PhysicalObjectBinding.objects
        .filter(Q(physical_element_id__in=element_ids) | Q(spatial_placement_id__in=placement_ids))
        .select_related('assigned_object_type')
        .order_by('-is_primary', 'binding_role', 'name', 'pk')
    )
    summaries = []
    for binding in queryset:
        assigned_object = binding.assigned_object
        summaries.append(
            SpatialReviewBindingSummary(
                id=binding.pk,
                label=binding.name,
                role=binding.binding_role,
                confidence=binding.confidence,
                is_primary=binding.is_primary,
                physical_element_id=binding.physical_element_id,
                spatial_placement_id=binding.spatial_placement_id,
                assigned_object_type=binding.assigned_object_type.model,
                assigned_object_id=binding.assigned_object_id,
                assigned_object_label=_object_label(assigned_object),
                object_url=_safe_absolute_url(assigned_object),
                binding_url=_safe_absolute_url(binding),
            )
        )
    return tuple(summaries)


def _with_binding_counts(elements, bindings):
    binding_counts = {}
    primary_labels = {}
    for binding in bindings:
        if binding.physical_element_id is None:
            continue
        binding_counts[binding.physical_element_id] = binding_counts.get(binding.physical_element_id, 0) + 1
        if binding.is_primary and binding.physical_element_id not in primary_labels:
            primary_labels[binding.physical_element_id] = binding.assigned_object_label

    return tuple(
        SpatialReviewElementSummary(
            id=element.id,
            label=element.label,
            kind=element.kind,
            role=element.role,
            confidence=element.confidence,
            object_url=element.object_url,
            binding_count=binding_counts.get(element.id, 0),
            primary_binding_label=primary_labels.get(element.id),
        )
        for element in elements
    )


def _status_counts(spaces):
    counts = {
        STATUS_APPROVED: 0,
        STATUS_OPERATOR_CORRECTED: 0,
        STATUS_OPERATOR_REVIEW_REQUIRED: 0,
        STATUS_UNKNOWN: 0,
    }
    for space in spaces:
        counts[space.status] = counts.get(space.status, 0) + 1
    return counts


def _binding_counts(bindings):
    counts = {'total': len(bindings), 'primary': 0}
    for binding in bindings:
        counts[binding.role] = counts.get(binding.role, 0) + 1
        if binding.is_primary:
            counts['primary'] += 1
    return counts


def _review_status(review_state, boundary_status, geometry_review_state=''):
    if geometry_review_state == STATUS_OPERATOR_CORRECTED:
        return STATUS_OPERATOR_CORRECTED
    values = {review_state, boundary_status}
    if STATUS_OPERATOR_REVIEW_REQUIRED in values:
        return STATUS_OPERATOR_REVIEW_REQUIRED
    if STATUS_APPROVED in values:
        return STATUS_APPROVED
    return STATUS_UNKNOWN


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value):
    return f'{value:g}'


def _object_label(obj):
    if obj is None:
        return ''
    return getattr(obj, 'label', None) or str(obj)


def _choice_label(choices, value):
    return dict(choices).get(value, _humanize(value))


def _humanize(value):
    return str(value or '').replace('_', ' ').replace('-', ' ').title()


def _metadata_url(metadata):
    return (
        metadata.get('provenance_url')
        or metadata.get('source_url')
        or metadata.get('review_url')
        or None
    )


def _safe_absolute_url(obj):
    if obj is None:
        return None
    try:
        return obj.get_absolute_url()
    except Exception:
        return None
