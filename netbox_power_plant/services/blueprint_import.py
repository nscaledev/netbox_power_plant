from __future__ import annotations

import re
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from dcim.models import Location, Site

from netbox_power_plant.choices import (
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PlantDisciplineChoices,
    PlantExtractionMethodChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
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
    SpatialFrame,
    SpatialPlacement,
)


BLUEPRINT_ROW_FIELDS = {
    "source_key",
    "name",
    "slug",
    "label",
    "role",
    "source_label",
    "source_ref",
    "discipline",
    "element_kind",
    "element_type",
    "element_type_id",
    "element_type_slug",
    "element_type_name",
    "location",
    "location_id",
    "physical_space",
    "physical_space_id",
    "spatial_frame",
    "spatial_frame_id",
    "x",
    "y",
    "z",
    "width",
    "depth",
    "height",
    "rotation_degrees",
    "anchor",
    "placement_name",
    "placement_slug",
    "confidence",
    "source_document",
    "source_document_id",
    "source_sheet",
    "source_sheet_id",
    "source_layer",
    "source_layer_id",
    "assigned_object",
    "assigned_object_type",
    "assigned_object_type_id",
    "assigned_object_id",
    "binding_role",
    "metadata",
    "placement_metadata",
    "provenance_metadata",
}


@dataclass(frozen=True)
class BlueprintPhysicalElementImportRowResult:
    row_number: int
    source_key: str
    action: str
    physical_element: PhysicalElement | None = None
    element_type: PhysicalElementType | None = None
    spatial_placement: SpatialPlacement | None = None
    binding: PhysicalObjectBinding | None = None
    provenance_records: tuple[PlantProvenance, ...] = ()
    element_created: bool = False
    placement_created: bool = False
    binding_created: bool = False
    failure_reason: str = ""

    @property
    def blocked(self):
        return self.action == "blocked"

    @property
    def created(self):
        return self.action == "created"

    @property
    def updated(self):
        return self.action == "updated"


@dataclass(frozen=True)
class BlueprintPhysicalElementImportSummary:
    site: Site
    dry_run: bool
    rows: tuple[BlueprintPhysicalElementImportRowResult, ...]

    @property
    def total_count(self):
        return len(self.rows)

    @property
    def created_count(self):
        return len([row for row in self.rows if row.created])

    @property
    def updated_count(self):
        return len([row for row in self.rows if row.updated])

    @property
    def blocked_count(self):
        return len([row for row in self.rows if row.blocked])

    @property
    def placed_count(self):
        return len([row for row in self.rows if row.spatial_placement is not None])

    @property
    def bound_count(self):
        return len([row for row in self.rows if row.binding is not None])

    @property
    def failure_reasons(self):
        return tuple(row.failure_reason for row in self.rows if row.failure_reason)

    @property
    def succeeded(self):
        return self.blocked_count == 0


@dataclass(frozen=True)
class PhysicalElementReconciliationRowResult:
    physical_element: PhysicalElement
    match_key: str
    action: str
    matched_object: object | None = None
    binding: PhysicalObjectBinding | None = None
    failure_reason: str = ""

    @property
    def matched(self):
        return self.matched_object is not None

    @property
    def bound(self):
        return self.action == "bound"

    @property
    def would_bind(self):
        return self.action == "would_bind"


@dataclass(frozen=True)
class PhysicalElementReconciliationSummary:
    dry_run: bool
    rows: tuple[PhysicalElementReconciliationRowResult, ...]

    @property
    def total_count(self):
        return len(self.rows)

    @property
    def bound_count(self):
        return len([row for row in self.rows if row.bound])

    @property
    def would_bind_count(self):
        return len([row for row in self.rows if row.would_bind])

    @property
    def already_bound_count(self):
        return len([row for row in self.rows if row.action == "already_bound"])

    @property
    def unmatched_count(self):
        return len([row for row in self.rows if row.action == "unmatched"])

    @property
    def ambiguous_count(self):
        return len([row for row in self.rows if row.action == "ambiguous"])


class _DryRunRollback(Exception):
    pass


def import_blueprint_physical_elements(
    site,
    rows,
    *,
    apply=False,
    default_location=None,
    default_physical_space=None,
    default_spatial_frame=None,
    default_source_document=None,
    default_source_sheet=None,
    default_source_layer=None,
    default_discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
    default_element_kind=PhysicalElementKindChoices.KIND_CUSTOM,
    default_confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
) -> BlueprintPhysicalElementImportSummary:
    prepared_rows = tuple(_prepare_row(index, raw_row) for index, raw_row in enumerate(rows, start=1))
    duplicate_source_keys = _duplicate_source_keys(prepared_rows)

    if apply:
        return _process_blueprint_rows(
            site,
            prepared_rows,
            duplicate_source_keys,
            dry_run=False,
            default_location=default_location,
            default_physical_space=default_physical_space,
            default_spatial_frame=default_spatial_frame,
            default_source_document=default_source_document,
            default_source_sheet=default_source_sheet,
            default_source_layer=default_source_layer,
            default_discipline=default_discipline,
            default_element_kind=default_element_kind,
            default_confidence=default_confidence,
        )

    summary = None
    try:
        with transaction.atomic():
            summary = _process_blueprint_rows(
                site,
                prepared_rows,
                duplicate_source_keys,
                dry_run=True,
                default_location=default_location,
                default_physical_space=default_physical_space,
                default_spatial_frame=default_spatial_frame,
                default_source_document=default_source_document,
                default_source_sheet=default_source_sheet,
                default_source_layer=default_source_layer,
                default_discipline=default_discipline,
                default_element_kind=default_element_kind,
                default_confidence=default_confidence,
            )
            raise _DryRunRollback()
    except _DryRunRollback:
        return summary

    return summary


def reconcile_physical_elements_to_objects(
    physical_elements,
    object_queryset,
    *,
    apply=False,
    element_field="source_label",
    object_field="name",
    binding_role=PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS,
    confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
) -> PhysicalElementReconciliationSummary:
    object_index = _build_object_match_index(object_queryset, object_field)

    if apply:
        return _process_reconciliation(
            physical_elements,
            object_index,
            dry_run=False,
            element_field=element_field,
            binding_role=binding_role,
            confidence=confidence,
        )

    summary = None
    try:
        with transaction.atomic():
            summary = _process_reconciliation(
                physical_elements,
                object_index,
                dry_run=True,
                element_field=element_field,
                binding_role=binding_role,
                confidence=confidence,
            )
            raise _DryRunRollback()
    except _DryRunRollback:
        return summary

    return summary


def _prepare_row(row_number, raw_row):
    if not isinstance(raw_row, dict):
        return {
            "row_number": row_number,
            "data": {},
            "failure_reason": "blueprint row must be a dict.",
        }

    unexpected_fields = set(raw_row) - BLUEPRINT_ROW_FIELDS
    if unexpected_fields:
        field_list = ", ".join(sorted(unexpected_fields))
        return {
            "row_number": row_number,
            "data": {},
            "failure_reason": f"unexpected blueprint field(s): {field_list}.",
        }

    source_key = str(raw_row.get("source_key") or "").strip()
    if not source_key:
        return {
            "row_number": row_number,
            "data": raw_row,
            "failure_reason": "source_key is required.",
        }

    return {
        "row_number": row_number,
        "data": raw_row,
        "source_key": source_key,
        "failure_reason": "",
    }


def _duplicate_source_keys(prepared_rows):
    counts = {}
    for row in prepared_rows:
        source_key = row.get("source_key")
        if not source_key:
            continue
        counts[source_key] = counts.get(source_key, 0) + 1
    return frozenset(source_key for source_key, count in counts.items() if count > 1)


def _process_blueprint_rows(
    site,
    prepared_rows,
    duplicate_source_keys,
    *,
    dry_run,
    default_location,
    default_physical_space,
    default_spatial_frame,
    default_source_document,
    default_source_sheet,
    default_source_layer,
    default_discipline,
    default_element_kind,
    default_confidence,
):
    results = []
    for row in prepared_rows:
        results.append(_process_blueprint_row(
            site,
            row,
            duplicate_source_keys,
            default_location=default_location,
            default_physical_space=default_physical_space,
            default_spatial_frame=default_spatial_frame,
            default_source_document=default_source_document,
            default_source_sheet=default_source_sheet,
            default_source_layer=default_source_layer,
            default_discipline=default_discipline,
            default_element_kind=default_element_kind,
            default_confidence=default_confidence,
        ))
    return BlueprintPhysicalElementImportSummary(site=site, dry_run=dry_run, rows=tuple(results))


def _process_blueprint_row(site, row, duplicate_source_keys, **defaults):
    source_key = row.get("source_key", "")
    if row.get("failure_reason"):
        return _blocked_result(row, row["failure_reason"])

    if source_key in duplicate_source_keys:
        return _blocked_result(row, f"duplicate source_key in import batch: {source_key}.")

    try:
        with transaction.atomic():
            row_data = {**row["data"], "row_number": row["row_number"], "source_key": source_key}
            return _stamp_blueprint_row(site, row_data, source_key=source_key, **defaults)
    except Exception as exc:
        return _blocked_result(row, _failure_reason(exc))


def _stamp_blueprint_row(
    site,
    data,
    *,
    source_key,
    default_location,
    default_physical_space,
    default_spatial_frame,
    default_source_document,
    default_source_sheet,
    default_source_layer,
    default_discipline,
    default_element_kind,
    default_confidence,
):
    location = data.get("location") or _get_by_pk(data.get("location_id"), Location.objects)
    location = location or default_location
    physical_space = data.get("physical_space") or _get_by_pk(data.get("physical_space_id"), PhysicalSpace.objects)
    physical_space = physical_space or default_physical_space
    spatial_frame = data.get("spatial_frame") or _get_by_pk(data.get("spatial_frame_id"), SpatialFrame.objects)
    spatial_frame = spatial_frame or default_spatial_frame
    source_document = data.get("source_document") or _get_by_pk(data.get("source_document_id"), PlantSourceDocument.objects)
    source_sheet = data.get("source_sheet") or _get_by_pk(data.get("source_sheet_id"), PlantSourceSheet.objects)
    source_layer = data.get("source_layer") or _get_by_pk(data.get("source_layer_id"), PlantSourceLayer.objects)
    source_layer = source_layer or default_source_layer
    source_sheet = source_sheet or (source_layer.source_sheet if source_layer is not None else default_source_sheet)
    source_document = source_document or (source_sheet.source_document if source_sheet is not None else default_source_document)

    confidence = data.get("confidence") or default_confidence
    discipline = data.get("discipline") or default_discipline
    element_kind = data.get("element_kind") or default_element_kind
    element_type = _resolve_element_type(data, discipline=discipline, element_kind=element_kind)
    source_label = data.get("source_label") or source_key
    name = data.get("name") or data.get("label") or source_label
    slug = data.get("slug") or _unique_slug(PhysicalElement, name)
    metadata = dict(data.get("metadata") or {})
    metadata.setdefault("source_key", source_key)

    element = PhysicalElement.objects.filter(site=site, source_label=source_label).order_by("pk").first()
    element_created = element is None
    if element is None:
        element = PhysicalElement(name=name, slug=slug, site=site)

    element.name = name
    element.element_type = element_type
    element.location = location
    element.physical_space = physical_space
    element.label = data.get("label", element.label)
    element.role = data.get("role", element.role)
    element.source_label = source_label
    element.confidence = confidence
    element.metadata = metadata
    element.full_clean()
    element.save()

    placement, placement_created = _stamp_placement(
        element,
        data,
        spatial_frame=spatial_frame,
        confidence=confidence,
    )
    binding, binding_created = _stamp_binding(element, placement, data, confidence=confidence)
    provenance_records = _stamp_provenance(
        element,
        placement,
        data,
        source_document=source_document,
        source_sheet=source_sheet,
        source_layer=source_layer,
        confidence=confidence,
    )

    action = "created" if element_created or placement_created or binding_created else "updated"
    return BlueprintPhysicalElementImportRowResult(
        row_number=data.get("row_number", 0),
        source_key=source_key,
        action=action,
        physical_element=element,
        element_type=element_type,
        spatial_placement=placement,
        binding=binding,
        provenance_records=provenance_records,
        element_created=element_created,
        placement_created=placement_created,
        binding_created=binding_created,
    )


def _resolve_element_type(data, *, discipline, element_kind):
    element_type = data.get("element_type")
    if element_type is not None:
        return element_type

    element_type_id = data.get("element_type_id")
    if element_type_id:
        return PhysicalElementType.objects.get(pk=element_type_id)

    element_type_slug = data.get("element_type_slug")
    if element_type_slug:
        return PhysicalElementType.objects.get(slug=element_type_slug)

    type_name = data.get("element_type_name") or element_kind.replace("_", " ").title()
    type_slug = slugify(type_name)[:100] or "physical-element-type"
    element_type, _created = PhysicalElementType.objects.get_or_create(
        slug=type_slug,
        defaults={
            "name": type_name,
            "discipline": discipline,
            "element_kind": element_kind,
        },
    )
    return element_type


def _stamp_placement(element, data, *, spatial_frame, confidence):
    if data.get("x") in (None, "") or data.get("y") in (None, ""):
        return None, False
    if spatial_frame is None:
        raise ValueError("spatial_frame is required when x/y placement coordinates are provided.")

    content_type = ContentType.objects.get_for_model(element, for_concrete_model=False)
    placement = SpatialPlacement.objects.filter(
        spatial_frame=spatial_frame,
        assigned_object_type=content_type,
        assigned_object_id=element.pk,
    ).order_by("pk").first()
    placement_created = placement is None
    if placement is None:
        placement = SpatialPlacement(
            name=data.get("placement_name") or f"{element.name} Placement",
            slug=data.get("placement_slug") or _unique_slug(SpatialPlacement, f"{element.name} Placement"),
            spatial_frame=spatial_frame,
            assigned_object_type=content_type,
            assigned_object_id=element.pk,
        )

    placement.x = data["x"]
    placement.y = data["y"]
    placement.z = _blank_to_none(data.get("z"))
    placement.width = _blank_to_none(data.get("width"))
    placement.depth = _blank_to_none(data.get("depth"))
    placement.height = _blank_to_none(data.get("height"))
    placement.rotation_degrees = data.get("rotation_degrees", placement.rotation_degrees)
    placement.anchor = data.get("anchor") or SpatialAnchorChoices.ANCHOR_CENTER
    placement.confidence = confidence
    placement.source_ref = data.get("source_ref", placement.source_ref)
    placement.metadata = dict(data.get("placement_metadata") or placement.metadata or {})
    placement.metadata.setdefault("source_key", data.get("source_key", element.source_label))
    placement.full_clean()
    placement.save()
    return placement, placement_created


def _stamp_binding(element, placement, data, *, confidence):
    assigned_object = _resolve_assigned_object(data)
    if assigned_object is None:
        return None, False

    content_type = ContentType.objects.get_for_model(assigned_object, for_concrete_model=False)
    binding = PhysicalObjectBinding.objects.filter(
        physical_element=element,
        assigned_object_type=content_type,
        assigned_object_id=assigned_object.pk,
    ).order_by("pk").first()
    binding_created = binding is None
    if binding is None:
        binding = PhysicalObjectBinding(
            name=_unique_model_value(PhysicalObjectBinding, "name", f"{element.name} represents {assigned_object}"),
            slug=_unique_slug(PhysicalObjectBinding, f"{element.name} represents {assigned_object}"),
            physical_element=element,
            assigned_object_type=content_type,
            assigned_object_id=assigned_object.pk,
        )
    binding.spatial_placement = placement
    binding.binding_role = data.get("binding_role") or PhysicalObjectBindingRoleChoices.ROLE_REPRESENTS
    binding.confidence = confidence
    binding.metadata = {"source_key": data.get("source_key", element.source_label)}
    binding.full_clean()
    binding.save()
    return binding, binding_created


def _stamp_provenance(element, placement, data, *, source_document, source_sheet, source_layer, confidence):
    if source_document is None and source_sheet is None and source_layer is None and not data.get("source_ref"):
        return ()

    provenance_records = [
        _get_or_create_provenance(
            element,
            source_document=source_document,
            source_sheet=source_sheet,
            source_layer=source_layer,
            source_ref=data.get("source_ref") or data.get("source_key", ""),
            confidence=confidence,
            metadata=data.get("provenance_metadata") or {},
        )
    ]
    if placement is not None:
        provenance_records.append(_get_or_create_provenance(
            placement,
            source_document=source_document,
            source_sheet=source_sheet,
            source_layer=source_layer,
            source_ref=data.get("source_ref") or data.get("source_key", ""),
            confidence=confidence,
            metadata=data.get("provenance_metadata") or {},
        ))
    return tuple(provenance_records)


def _get_or_create_provenance(obj, *, source_document, source_sheet, source_layer, source_ref, confidence, metadata):
    content_type = ContentType.objects.get_for_model(obj, for_concrete_model=False)
    provenance = PlantProvenance.objects.filter(
        assigned_object_type=content_type,
        assigned_object_id=obj.pk,
        source_document=source_document,
        source_sheet=source_sheet,
        source_layer=source_layer,
        source_ref=source_ref,
    ).order_by("pk").first()
    if provenance is None:
        provenance = PlantProvenance(
            name=_unique_model_value(PlantProvenance, "name", f"Provenance for {obj} from {source_ref or 'source'}"),
            slug=_unique_slug(PlantProvenance, f"Provenance for {obj} from {source_ref or 'source'}"),
            assigned_object_type=content_type,
            assigned_object_id=obj.pk,
            source_document=source_document,
            source_sheet=source_sheet,
            source_layer=source_layer,
            source_ref=source_ref,
        )
    provenance.extraction_method = PlantExtractionMethodChoices.METHOD_PARSED_SVG
    provenance.confidence = confidence
    provenance.extracted_at = provenance.extracted_at or timezone.now()
    provenance.metadata = dict(metadata or {})
    provenance.full_clean()
    provenance.save()
    return provenance


def _resolve_assigned_object(data):
    assigned_object = data.get("assigned_object")
    if assigned_object is not None:
        return assigned_object

    object_id = data.get("assigned_object_id")
    if not object_id:
        return None

    content_type = data.get("assigned_object_type")
    if content_type is None:
        content_type_id = data.get("assigned_object_type_id")
        if not content_type_id:
            raise ValueError("assigned_object_type is required when assigned_object_id is provided.")
        content_type = ContentType.objects.get(pk=content_type_id)
    elif not isinstance(content_type, ContentType):
        content_type = ContentType.objects.get(pk=content_type)

    model = content_type.model_class()
    if model is None:
        raise ValueError("assigned_object_type does not resolve to an installed model.")
    return model.objects.get(pk=object_id)


def _process_reconciliation(physical_elements, object_index, *, dry_run, element_field, binding_role, confidence):
    rows = []
    for element in physical_elements:
        rows.append(_reconcile_one_element(
            element,
            object_index,
            dry_run=dry_run,
            element_field=element_field,
            binding_role=binding_role,
            confidence=confidence,
        ))
    return PhysicalElementReconciliationSummary(dry_run=dry_run, rows=tuple(rows))


def _reconcile_one_element(element, object_index, *, dry_run, element_field, binding_role, confidence):
    match_key = _match_key(getattr(element, element_field, ""))
    if not match_key:
        return PhysicalElementReconciliationRowResult(element, "", "unmatched", failure_reason="empty match key")

    candidates = object_index.get(match_key, ())
    if not candidates:
        return PhysicalElementReconciliationRowResult(element, match_key, "unmatched")
    if len(candidates) > 1:
        return PhysicalElementReconciliationRowResult(element, match_key, "ambiguous", failure_reason="multiple candidate objects")

    matched_object = candidates[0]
    content_type = ContentType.objects.get_for_model(matched_object, for_concrete_model=False)
    existing_binding = PhysicalObjectBinding.objects.filter(
        physical_element=element,
        assigned_object_type=content_type,
        assigned_object_id=matched_object.pk,
    ).order_by("pk").first()
    if existing_binding is not None:
        return PhysicalElementReconciliationRowResult(element, match_key, "already_bound", matched_object, existing_binding)
    if dry_run:
        return PhysicalElementReconciliationRowResult(element, match_key, "would_bind", matched_object)

    binding = PhysicalObjectBinding(
        name=_unique_model_value(PhysicalObjectBinding, "name", f"{element.name} represents {matched_object}"),
        slug=_unique_slug(PhysicalObjectBinding, f"{element.name} represents {matched_object}"),
        physical_element=element,
        assigned_object_type=content_type,
        assigned_object_id=matched_object.pk,
        binding_role=binding_role,
        confidence=confidence,
        is_primary=True,
        metadata={"matched_by": "blueprint_reconciliation", "match_key": match_key},
    )
    binding.full_clean()
    binding.save()
    return PhysicalElementReconciliationRowResult(element, match_key, "bound", matched_object, binding)


def _build_object_match_index(object_queryset, object_field):
    index = {}
    for obj in object_queryset:
        key = _match_key(getattr(obj, object_field, ""))
        if not key:
            continue
        index.setdefault(key, []).append(obj)
    return {key: tuple(objects) for key, objects in index.items()}


def _match_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _get_by_pk(pk, manager):
    if pk in (None, ""):
        return None
    return manager.get(pk=pk)


def _blank_to_none(value):
    return None if value == "" else value


def _blocked_result(row, failure_reason):
    return BlueprintPhysicalElementImportRowResult(
        row_number=row.get("row_number", 0),
        source_key=row.get("source_key", ""),
        action="blocked",
        failure_reason=failure_reason,
    )


def _failure_reason(exc):
    if hasattr(exc, "message_dict"):
        return str(exc.message_dict)
    return str(exc)


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
