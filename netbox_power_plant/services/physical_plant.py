from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.text import slugify

from netbox_power_plant.choices import (
    PhysicalObjectBindingRoleChoices,
    PlantExtractionMethodChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    PhysicalElement,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    SpatialPlacement,
)


def get_bindings_for_object(obj):
    content_type, object_id = _object_identity(obj)
    return (
        PhysicalObjectBinding.objects.filter(
            assigned_object_type=content_type,
            assigned_object_id=object_id,
        )
        .select_related(
            "assigned_object_type",
            "physical_element",
            "physical_element__element_type",
            "spatial_placement",
            "spatial_placement__spatial_frame",
        )
        .order_by("physical_element__name", "spatial_placement__name", "pk")
    )


def get_physical_elements_for_object(obj):
    content_type, object_id = _object_identity(obj)
    return (
        PhysicalElement.objects.filter(
            object_bindings__assigned_object_type=content_type,
            object_bindings__assigned_object_id=object_id,
        )
        .select_related("element_type", "site", "location", "physical_space")
        .distinct()
        .order_by("site__name", "location__name", "element_type__discipline", "name")
    )


def get_spatial_placements_for_object(obj):
    content_type, object_id = _object_identity(obj)
    return (
        SpatialPlacement.objects.filter(
            Q(assigned_object_type=content_type, assigned_object_id=object_id)
            | Q(
                object_bindings__assigned_object_type=content_type,
                object_bindings__assigned_object_id=object_id,
            )
        )
        .select_related("assigned_object_type", "spatial_frame", "spatial_frame__site", "spatial_frame__location")
        .distinct()
        .order_by("spatial_frame__site__name", "spatial_frame__name", "name")
    )


def bind_physical_element_to_object(
    physical_element,
    obj,
    *,
    spatial_placement=None,
    binding_role=PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
    confidence=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
    is_primary=False,
    metadata=None,
    name=None,
    slug=None,
):
    return _create_binding(
        physical_element=physical_element,
        spatial_placement=spatial_placement,
        obj=obj,
        binding_role=binding_role,
        confidence=confidence,
        is_primary=is_primary,
        metadata=metadata,
        name=name,
        slug=slug,
    )


def bind_spatial_placement_to_object(
    spatial_placement,
    obj,
    *,
    physical_element=None,
    binding_role=PhysicalObjectBindingRoleChoices.ROLE_PLACEMENT_FOR,
    confidence=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
    is_primary=False,
    metadata=None,
    name=None,
    slug=None,
):
    return _create_binding(
        physical_element=physical_element,
        spatial_placement=spatial_placement,
        obj=obj,
        binding_role=binding_role,
        confidence=confidence,
        is_primary=is_primary,
        metadata=metadata,
        name=name,
        slug=slug,
    )


def create_provenance_record(
    obj,
    *,
    source_document=None,
    source_sheet=None,
    source_layer=None,
    extraction_method=PlantExtractionMethodChoices.METHOD_UNKNOWN,
    source_ref="",
    confidence=SpatialConfidenceChoices.CONFIDENCE_UNKNOWN,
    is_authoritative=False,
    extracted_at=None,
    metadata=None,
    name=None,
    slug=None,
):
    content_type, object_id = _object_identity(obj)
    if source_layer is not None and source_sheet is None:
        source_sheet = source_layer.source_sheet
    if source_sheet is not None and source_document is None:
        source_document = source_sheet.source_document

    base_name = name or _provenance_name(obj, source_document, source_sheet, source_layer, source_ref)
    record = PlantProvenance(
        name=_unique_model_value(PlantProvenance, "name", base_name),
        slug=slug or _unique_slug(PlantProvenance, base_name),
        assigned_object_type=content_type,
        assigned_object_id=object_id,
        source_document=source_document,
        source_sheet=source_sheet,
        source_layer=source_layer,
        extraction_method=extraction_method,
        source_ref=source_ref,
        confidence=confidence,
        is_authoritative=is_authoritative,
        extracted_at=extracted_at,
        metadata=metadata or {},
    )
    record.full_clean()
    record.save()
    return record


def build_physical_scope_summary(site=None, location=None):
    spaces = _scope_queryset(PhysicalSpace.objects.all(), site=site, location=location)
    elements = _scope_queryset(PhysicalElement.objects.all(), site=site, location=location)
    placements = _placement_scope_queryset(SpatialPlacement.objects.all(), site=site, location=location)
    bindings = _binding_scope_queryset(PhysicalObjectBinding.objects.all(), site=site, location=location)

    return {
        "spaces": spaces.count(),
        "elements": elements.count(),
        "placements": placements.count(),
        "bindings": bindings.count(),
        "unbound_elements": elements.filter(object_bindings__isnull=True).count(),
        "unplaced_elements": _count_unplaced_elements(elements),
    }


def _create_binding(
    *,
    physical_element,
    spatial_placement,
    obj,
    binding_role,
    confidence,
    is_primary,
    metadata,
    name,
    slug,
):
    content_type, object_id = _object_identity(obj)
    base_name = name or _binding_name(physical_element, spatial_placement, obj, binding_role)
    binding = PhysicalObjectBinding(
        name=_unique_model_value(PhysicalObjectBinding, "name", base_name),
        slug=slug or _unique_slug(PhysicalObjectBinding, base_name),
        physical_element=physical_element,
        spatial_placement=spatial_placement,
        assigned_object_type=content_type,
        assigned_object_id=object_id,
        binding_role=binding_role,
        confidence=confidence,
        is_primary=is_primary,
        metadata=metadata or {},
    )
    binding.full_clean()
    binding.save()
    return binding


def _object_identity(obj):
    if obj is None or getattr(obj, "pk", None) is None:
        raise ValueError("A saved model instance is required.")
    return ContentType.objects.get_for_model(obj, for_concrete_model=False), obj.pk


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


def _count_unplaced_elements(elements):
    element_type = ContentType.objects.get_for_model(PhysicalElement, for_concrete_model=False)
    element_ids = elements.values("pk")
    directly_placed_element_ids = SpatialPlacement.objects.filter(
        assigned_object_type=element_type,
        assigned_object_id__in=element_ids,
    ).values("assigned_object_id")
    binding_placed_element_ids = PhysicalObjectBinding.objects.filter(
        physical_element_id__in=element_ids,
        spatial_placement__isnull=False,
    ).values("physical_element_id")

    return elements.exclude(pk__in=directly_placed_element_ids).exclude(pk__in=binding_placed_element_ids).count()


def _binding_name(physical_element, spatial_placement, obj, binding_role):
    targets = []
    if physical_element is not None:
        targets.append(str(physical_element))
    if spatial_placement is not None:
        targets.append(str(spatial_placement))
    target_label = " + ".join(targets) or "Physical binding"
    return f"{target_label} {binding_role} {obj}"


def _provenance_name(obj, source_document, source_sheet, source_layer, source_ref):
    source = source_ref or _first_source_label(source_layer, source_sheet, source_document) or "source"
    return f"Provenance for {obj} from {source}"


def _first_source_label(*sources):
    for source in sources:
        if source is not None:
            return str(source)
    return None


def _unique_slug(model, base):
    base_slug = slugify(base)[:90] or model._meta.model_name
    return _unique_model_value(model, "slug", base_slug, separator="-", max_length=100)


def _unique_model_value(model, field_name, base, *, separator=" ", max_length=100):
    base = str(base or model._meta.verbose_name).strip()[:max_length] or model._meta.model_name
    value = base
    index = 2
    while model.objects.filter(**{field_name: value}).exists():
        suffix = f"{separator}{index}"
        value = f"{base[:max_length - len(suffix)]}{suffix}"
        index += 1
    return value
