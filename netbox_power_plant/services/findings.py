from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.text import slugify

from netbox_power_plant.choices import (
    PowerFindingSeverityChoices,
    PowerFindingStatusChoices,
    PowerValidationRunKindChoices,
    PowerValidationRunStatusChoices,
)
from netbox_power_plant.models import PowerFinding, PowerValidationRun
from netbox_power_plant.services.capacity import build_capacity_findings
from netbox_power_plant.services.layout_validation import run_layout_checks
from netbox_power_plant.services.physical_validation import run_physical_plant_checks
from netbox_power_plant.services.scenarios import build_scenario_findings
from netbox_power_plant.services.validation import run_topology_checks


@dataclass(frozen=True)
class PersistedFindingResult:
    run: PowerValidationRun
    open_count: int
    resolved_count: int


def create_validation_run(power_system, *, run_kind, name=None, slug=None, status=None) -> PowerValidationRun:
    now = timezone.now()
    label = name or f'{power_system.name} {run_kind.title()} Validation {now:%Y-%m-%d %H:%M:%S}'
    return PowerValidationRun.objects.create(
        name=label,
        slug=slug or _unique_run_slug(power_system, run_kind, now),
        power_system=power_system,
        run_kind=run_kind,
        status=status or PowerValidationRunStatusChoices.STATUS_RUNNING,
        started_at=now,
    )


def run_and_persist_topology_findings(power_system, *, name=None) -> PersistedFindingResult:
    run = create_validation_run(
        power_system,
        run_kind=PowerValidationRunKindChoices.KIND_TOPOLOGY,
        name=name,
    )
    output = run_topology_checks(power_system)
    return persist_findings_for_run(run, output.get('findings', ()))


def run_and_persist_layout_findings(power_system, *, name=None) -> PersistedFindingResult:
    run = create_validation_run(
        power_system,
        run_kind=PowerValidationRunKindChoices.KIND_LAYOUT,
        name=name,
    )
    return persist_findings_for_run(run, run_layout_checks(power_system))


def run_and_persist_physical_plant_findings(power_system, *, name=None) -> PersistedFindingResult:
    run = create_validation_run(
        power_system,
        run_kind=PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT,
        name=name,
    )
    return persist_findings_for_run(run, run_physical_plant_checks(power_system=power_system))


def run_and_persist_capacity_findings(power_system, *, name=None) -> PersistedFindingResult:
    run = create_validation_run(
        power_system,
        run_kind=PowerValidationRunKindChoices.KIND_CAPACITY,
        name=name,
    )
    return persist_findings_for_run(run, build_capacity_findings(power_system))


def run_and_persist_scenario_findings(power_system, scenario, *, name=None) -> PersistedFindingResult:
    run = create_validation_run(
        power_system,
        run_kind=PowerValidationRunKindChoices.KIND_SCENARIO,
        name=name,
    )
    return persist_findings_for_run(run, build_scenario_findings(power_system, scenario))


def persist_findings_for_run(run: PowerValidationRun, findings) -> PersistedFindingResult:
    now = timezone.now()
    seen_fingerprints = set()

    for raw_finding in findings:
        normalized = normalize_finding(raw_finding, run=run)
        seen_fingerprints.add(normalized['fingerprint'])
        defaults = {
            'name': normalized['name'],
            'slug': _finding_slug(run, normalized['fingerprint']),
            'power_system': run.power_system,
            'finding_type': normalized['finding_type'],
            'severity': normalized['severity'],
            'status': PowerFindingStatusChoices.STATUS_OPEN,
            'message': normalized['message'],
            'assigned_object_type': normalized['assigned_object_type'],
            'assigned_object_id': normalized['assigned_object_id'],
            'last_seen': now,
            'details': normalized['details'],
        }
        finding, created = PowerFinding.objects.update_or_create(
            run=run,
            fingerprint=normalized['fingerprint'],
            defaults=defaults,
        )
        if created:
            finding.first_seen = now
            finding.save(update_fields=('first_seen',))

    resolved_count = close_stale_findings(run, seen_fingerprints, resolved_at=now)
    run.finding_count = len(seen_fingerprints)
    run.status = PowerValidationRunStatusChoices.STATUS_COMPLETED
    run.completed_at = now
    run.save(update_fields=('finding_count', 'status', 'completed_at'))

    return PersistedFindingResult(
        run=run,
        open_count=len(seen_fingerprints),
        resolved_count=resolved_count,
    )


def close_stale_findings(run: PowerValidationRun, active_fingerprints, *, resolved_at=None) -> int:
    resolved_at = resolved_at or timezone.now()
    stale_findings = run.findings.exclude(
        fingerprint__in=set(active_fingerprints),
    ).exclude(
        status=PowerFindingStatusChoices.STATUS_RESOLVED,
    )
    return stale_findings.update(
        status=PowerFindingStatusChoices.STATUS_RESOLVED,
        resolved_at=resolved_at,
    )


def normalize_finding(raw_finding, *, run: PowerValidationRun) -> dict:
    if isinstance(raw_finding, dict):
        finding_type = raw_finding.get('finding_type') or 'unknown'
        message = str(raw_finding.get('message') or finding_type)
        assigned_object = raw_finding.get('object')
        related_object = raw_finding.get('related_object')
        severity = raw_finding.get('severity') or _default_severity(run.run_kind)
        details = _json_ready_details(raw_finding, exclude={'object', 'related_object', 'message'})
    else:
        finding_type = getattr(raw_finding, 'finding_type', 'unknown')
        message = str(getattr(raw_finding, 'message', finding_type))
        assigned_object = getattr(raw_finding, 'object', None)
        related_object = getattr(raw_finding, 'related_object', None)
        severity = getattr(raw_finding, 'severity', None) or _default_severity(run.run_kind)
        details = _json_ready_details(getattr(raw_finding, '__dict__', {}), exclude={'object', 'related_object', 'message'})

    assigned_object_type = None
    assigned_object_id = None
    if _is_persisted_object(assigned_object):
        assigned_object_type = ContentType.objects.get_for_model(assigned_object, for_concrete_model=False)
        assigned_object_id = assigned_object.pk

    fingerprint = build_fingerprint(
        run_kind=run.run_kind,
        finding_type=finding_type,
        assigned_object=assigned_object,
        related_object=related_object,
        details=details,
    )
    return {
        'name': _finding_name(finding_type, assigned_object, fingerprint, run=run),
        'fingerprint': fingerprint,
        'finding_type': finding_type,
        'severity': severity,
        'message': message,
        'assigned_object_type': assigned_object_type,
        'assigned_object_id': assigned_object_id,
        'details': details,
    }


def build_fingerprint(*, run_kind, finding_type, assigned_object=None, related_object=None, details=None) -> str:
    payload = {
        'run_kind': run_kind,
        'finding_type': finding_type,
        'assigned_object': _object_identity(assigned_object),
        'related_object': _object_identity(related_object),
        'details': details or {},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _unique_run_slug(power_system, run_kind, now):
    base = slugify(f'{power_system.slug}-{run_kind}-validation-{now:%Y%m%d%H%M%S}')[:90]
    slug = base
    index = 2
    while PowerValidationRun.objects.filter(slug=slug).exists():
        suffix = f'-{index}'
        slug = f'{base[:100 - len(suffix)]}{suffix}'
        index += 1
    return slug


def _finding_slug(run, fingerprint):
    return f'finding-{run.pk}-{fingerprint[:16]}'


def _finding_name(finding_type, assigned_object, fingerprint, *, run):
    label = finding_type.replace('_', ' ').title()
    if assigned_object is not None:
        label = f'{label}: {assigned_object}'
    suffix = f' [{run.pk}:{fingerprint[:8]}]'
    return f'{label[:100 - len(suffix)]}{suffix}' or f'Finding {run.pk}:{fingerprint[:12]}'


def _default_severity(run_kind):
    if run_kind == PowerValidationRunKindChoices.KIND_TOPOLOGY:
        return PowerFindingSeverityChoices.SEVERITY_ERROR
    return PowerFindingSeverityChoices.SEVERITY_WARNING


def _json_ready_details(raw, *, exclude):
    details = {}
    for key, value in dict(raw).items():
        if key in exclude:
            continue
        if _is_persisted_object(value):
            details[key] = _object_identity(value)
        elif isinstance(value, (list, tuple, set)):
            details[key] = [_json_ready_value(item) for item in value]
        elif isinstance(value, dict):
            details[key] = {str(k): _json_ready_value(v) for k, v in value.items()}
        else:
            details[key] = _json_ready_value(value)
    return details


def _json_ready_value(value):
    if _is_persisted_object(value):
        return _object_identity(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _object_identity(obj):
    if not _is_persisted_object(obj):
        return None
    meta = obj._meta
    return {
        'app_label': meta.app_label,
        'model': meta.model_name,
        'id': obj.pk,
    }


def _is_persisted_object(obj):
    return getattr(obj, '_meta', None) is not None and getattr(obj, 'pk', None) is not None
