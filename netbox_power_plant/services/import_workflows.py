from __future__ import annotations

from dataclasses import dataclass
from decimal import InvalidOperation
from typing import Iterable, Mapping

from django.core.exceptions import ValidationError
from django.db import transaction

from dcim.models import Device, PowerPort

from netbox_power_plant.choices import DesignStateChoices
from netbox_power_plant.models import PowerHandoffPoint, PowerSystem
from netbox_power_plant.services.staging import (
    StagedCircuitEndpoint,
    bind_handoff_to_power_port,
    stage_circuit_endpoint,
    _stable_slug as _staging_stable_slug,
)


DEFAULT_DELIVERY_ROLE = 'staged-circuit-handoff'
ENDPOINT_FIELD_NAMES = set(StagedCircuitEndpoint.__dataclass_fields__.keys())
BINDING_FIELD_NAMES = {
    'power_port',
    'power_port_id',
    'power_port_pk',
    'device',
    'device_id',
    'device_name',
    'power_port_name',
    'port_name',
    'delivery_role',
    'design_state',
}


@dataclass(frozen=True)
class PowerPortBinding:
    power_port: PowerPort
    delivery_role: str
    design_state: str


@dataclass(frozen=True)
class StagedCircuitEndpointImportRowResult:
    row_number: int
    source_key: str
    endpoint: StagedCircuitEndpoint | None
    action: str
    node: object = None
    terminal: object = None
    power_domain: object = None
    power_port: PowerPort | None = None
    power_handoff: PowerHandoffPoint | None = None
    node_created: bool = False
    terminal_created: bool = False
    handoff_created: bool = False
    binding_requested: bool = False
    failure_reason: str = ''

    @property
    def blocked(self):
        return self.action == 'blocked'

    @property
    def created(self):
        return self.action == 'created'

    @property
    def updated(self):
        return self.action == 'updated'


@dataclass(frozen=True)
class StagedCircuitEndpointImportSummary:
    power_system: PowerSystem
    dry_run: bool
    rows: tuple[StagedCircuitEndpointImportRowResult, ...]

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
    def staged_count(self):
        return len([row for row in self.rows if not row.blocked])

    @property
    def bound_count(self):
        return len([row for row in self.rows if row.power_handoff is not None])

    @property
    def node_created_count(self):
        return len([row for row in self.rows if row.node_created])

    @property
    def terminal_created_count(self):
        return len([row for row in self.rows if row.terminal_created])

    @property
    def handoff_created_count(self):
        return len([row for row in self.rows if row.handoff_created])

    @property
    def failure_reasons(self):
        return tuple(row.failure_reason for row in self.rows if row.failure_reason)

    @property
    def succeeded(self):
        return self.blocked_count == 0


@dataclass(frozen=True)
class _PreparedImportRow:
    row_number: int
    endpoint: StagedCircuitEndpoint | None
    binding_spec: object = None
    failure_reason: str = ''

    @property
    def source_key(self):
        return self.endpoint.source_key if self.endpoint is not None else ''


class _DryRunRollback(Exception):
    pass


def import_staged_circuit_endpoints(
    power_system: PowerSystem,
    endpoints: Iterable[StagedCircuitEndpoint | dict],
    *,
    apply: bool = False,
    power_port_bindings: Mapping[str, object] | None = None,
    delivery_role: str = DEFAULT_DELIVERY_ROLE,
    design_state: str = DesignStateChoices.STATE_PLANNED,
) -> StagedCircuitEndpointImportSummary:
    """
    Bulk-stamp staged circuit endpoints into a power system.

    In dry-run mode, this calls the same staging and binding services used by
    apply mode inside a transaction that is rolled back before returning.

    PowerPort bindings are optional and can be supplied inline on row dicts or
    through power_port_bindings keyed by endpoint source_key. Binding specs may
    be a PowerPort, a PowerPort pk, a "device-name:port-name" string, or a dict
    with power_port/power_port_id/device_name plus power_port_name.
    """
    prepared_rows = _prepare_rows(endpoints, power_port_bindings or {})
    duplicate_source_keys = _duplicate_source_keys(prepared_rows)

    if apply:
        return _process_import(
            power_system,
            prepared_rows,
            duplicate_source_keys,
            dry_run=False,
            delivery_role=delivery_role,
            design_state=design_state,
        )

    summary = None
    try:
        with transaction.atomic():
            summary = _process_import(
                power_system,
                prepared_rows,
                duplicate_source_keys,
                dry_run=True,
                delivery_role=delivery_role,
                design_state=design_state,
            )
            raise _DryRunRollback()
    except _DryRunRollback:
        return summary

    return summary


def _prepare_rows(endpoints, power_port_bindings):
    rows = []
    for row_number, raw_endpoint in enumerate(endpoints, start=1):
        try:
            endpoint, inline_binding = _coerce_endpoint_with_inline_binding(raw_endpoint)
            if endpoint.source_key in power_port_bindings:
                binding_spec = _merge_binding_specs(inline_binding, power_port_bindings[endpoint.source_key])
            else:
                binding_spec = inline_binding
            rows.append(_PreparedImportRow(
                row_number=row_number,
                endpoint=endpoint,
                binding_spec=binding_spec,
            ))
        except Exception as exc:
            rows.append(_PreparedImportRow(
                row_number=row_number,
                endpoint=None,
                failure_reason=_failure_reason(exc),
            ))
    return tuple(rows)


def _coerce_endpoint_with_inline_binding(raw_endpoint):
    if isinstance(raw_endpoint, StagedCircuitEndpoint):
        _validate_endpoint_source_key(raw_endpoint)
        return raw_endpoint, None

    if not isinstance(raw_endpoint, dict):
        raise TypeError('endpoint must be a StagedCircuitEndpoint or dict.')

    unexpected_fields = set(raw_endpoint) - ENDPOINT_FIELD_NAMES - BINDING_FIELD_NAMES
    if unexpected_fields:
        field_list = ', '.join(sorted(unexpected_fields))
        raise ValueError(f'unexpected endpoint field(s): {field_list}.')

    endpoint_data = {key: raw_endpoint[key] for key in ENDPOINT_FIELD_NAMES if key in raw_endpoint}
    binding_spec = {key: raw_endpoint[key] for key in BINDING_FIELD_NAMES if key in raw_endpoint}
    if not endpoint_data.get('source_key'):
        raise ValueError('source_key is required.')
    endpoint = StagedCircuitEndpoint(**endpoint_data)
    _validate_endpoint_source_key(endpoint)
    return endpoint, binding_spec or None


def _merge_binding_specs(inline_binding, mapped_binding):
    if inline_binding is None or mapped_binding is None:
        return mapped_binding
    if isinstance(inline_binding, dict) and isinstance(mapped_binding, dict):
        return {**inline_binding, **mapped_binding}
    if isinstance(inline_binding, dict):
        metadata = {
            key: inline_binding[key]
            for key in ('delivery_role', 'design_state')
            if key in inline_binding
        }
        return {**metadata, 'power_port': mapped_binding}
    return mapped_binding


def _validate_endpoint_source_key(endpoint):
    if not endpoint.source_key:
        raise ValueError('source_key is required.')


def _duplicate_source_keys(prepared_rows):
    counts = {}
    for row in prepared_rows:
        if not row.source_key:
            continue
        counts[row.source_key] = counts.get(row.source_key, 0) + 1
    return frozenset(source_key for source_key, count in counts.items() if count > 1)


def _process_import(
    power_system,
    prepared_rows,
    duplicate_source_keys,
    *,
    dry_run,
    delivery_role,
    design_state,
):
    results = []
    for row in prepared_rows:
        results.append(_process_row(
            power_system,
            row,
            duplicate_source_keys,
            default_delivery_role=delivery_role,
            default_design_state=design_state,
        ))
    return StagedCircuitEndpointImportSummary(
        power_system=power_system,
        dry_run=dry_run,
        rows=tuple(results),
    )


def _process_row(
    power_system,
    row,
    duplicate_source_keys,
    *,
    default_delivery_role,
    default_design_state,
):
    if row.failure_reason:
        return _blocked_result(row, row.failure_reason)

    if row.source_key in duplicate_source_keys:
        return _blocked_result(row, f'duplicate source_key in import batch: {row.source_key}.')

    try:
        binding = _resolve_power_port_binding(
            power_system,
            row.binding_spec,
            default_delivery_role=default_delivery_role,
            default_design_state=default_design_state,
        )
        with transaction.atomic():
            return _stamp_row(power_system, row, binding)
    except Exception as exc:
        return _blocked_result(row, _failure_reason(exc))


def _stamp_row(power_system, row, binding):
    staged = stage_circuit_endpoint(power_system, row.endpoint)
    power_handoff = None
    handoff_created = False
    power_port = None
    binding_requested = binding is not None

    if binding is not None:
        power_port = binding.power_port
        handoff_slug = _handoff_slug(row.endpoint)
        handoff_existed = PowerHandoffPoint.objects.filter(slug=handoff_slug).exists()
        power_handoff = bind_handoff_to_power_port(
            power_system,
            row.endpoint,
            power_port,
            delivery_role=binding.delivery_role,
            design_state=binding.design_state,
        )
        handoff_created = not handoff_existed

    action = 'created' if staged.node_created or staged.terminal_created or handoff_created else 'updated'
    return StagedCircuitEndpointImportRowResult(
        row_number=row.row_number,
        source_key=row.source_key,
        endpoint=staged.endpoint,
        action=action,
        node=staged.node,
        terminal=staged.terminal,
        power_domain=staged.power_domain,
        power_port=power_port,
        power_handoff=power_handoff,
        node_created=staged.node_created,
        terminal_created=staged.terminal_created,
        handoff_created=handoff_created,
        binding_requested=binding_requested,
    )


def _resolve_power_port_binding(
    power_system,
    binding_spec,
    *,
    default_delivery_role,
    default_design_state,
):
    binding_spec = _blank_to_none(binding_spec)
    if binding_spec is None:
        return None

    delivery_role = default_delivery_role
    design_state = default_design_state
    spec = binding_spec

    if isinstance(binding_spec, dict):
        cleaned = {key: value for key, value in binding_spec.items() if _blank_to_none(value) is not None}
        if not cleaned:
            return None
        delivery_role = cleaned.pop('delivery_role', delivery_role)
        design_state = cleaned.pop('design_state', design_state)
        spec = cleaned

    power_port = _resolve_power_port(power_system, spec)
    return PowerPortBinding(
        power_port=power_port,
        delivery_role=delivery_role,
        design_state=design_state,
    )


def _resolve_power_port(power_system, spec):
    if isinstance(spec, PowerPort):
        return spec

    if isinstance(spec, int):
        return _get_power_port_by_pk(spec)

    if isinstance(spec, str):
        spec = spec.strip()
        if spec.isdecimal():
            return _get_power_port_by_pk(int(spec))
        if ':' in spec:
            device_name, port_name = [part.strip() for part in spec.split(':', 1)]
            return _get_power_port_by_device_and_name(
                power_system,
                device_name=device_name,
                port_name=port_name,
            )
        raise ValueError('PowerPort binding string must be a pk or "device-name:port-name".')

    if isinstance(spec, dict):
        if 'power_port' in spec:
            return _resolve_power_port(power_system, spec['power_port'])
        if 'power_port_id' in spec:
            return _get_power_port_by_pk(spec['power_port_id'])
        if 'power_port_pk' in spec:
            return _get_power_port_by_pk(spec['power_port_pk'])

        port_name = spec.get('power_port_name') or spec.get('port_name')
        if 'device' in spec and port_name:
            return _get_power_port_by_device(spec['device'], port_name)
        if 'device_id' in spec and port_name:
            return _get_power_port_by_device_id(spec['device_id'], port_name)
        if 'device_name' in spec and port_name:
            return _get_power_port_by_device_and_name(
                power_system,
                device_name=spec['device_name'],
                port_name=port_name,
            )
        raise ValueError(
            'PowerPort binding requires power_port, power_port_id, or device_name plus power_port_name.'
        )

    raise TypeError('PowerPort binding must be a PowerPort, pk, lookup string, or dict.')


def _get_power_port_by_pk(pk):
    pk = _coerce_pk(pk, 'power_port_id')
    power_port = PowerPort.objects.filter(pk=pk).select_related('device').first()
    if power_port is None:
        raise ValueError(f'PowerPort not found for pk {pk}.')
    return power_port


def _get_power_port_by_device(device, port_name):
    if not isinstance(device, Device):
        raise TypeError('device must be a dcim.models.Device instance.')
    return _get_single_power_port(
        PowerPort.objects.filter(device=device, name=port_name).select_related('device'),
        f'device {device.name!r} port {port_name!r}',
    )


def _get_power_port_by_device_id(device_id, port_name):
    device_id = _coerce_pk(device_id, 'device_id')
    device = Device.objects.filter(pk=device_id).first()
    if device is None:
        raise ValueError(f'Device not found for pk {device_id}.')
    return _get_power_port_by_device(device, port_name)


def _get_power_port_by_device_and_name(power_system, *, device_name, port_name):
    return _get_single_power_port(
        PowerPort.objects.filter(
            device__site=power_system.site,
            device__name=device_name,
            name=port_name,
        ).select_related('device'),
        f'device {device_name!r} port {port_name!r} in site {power_system.site.name!r}',
    )


def _get_single_power_port(queryset, lookup_description):
    matches = list(queryset[:2])
    if not matches:
        raise ValueError(f'PowerPort not found for {lookup_description}.')
    if len(matches) > 1:
        raise ValueError(f'PowerPort lookup matched multiple ports for {lookup_description}.')
    return matches[0]


def _coerce_pk(value, field_name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field_name} must be an integer pk.')


def _blocked_result(row, reason):
    return StagedCircuitEndpointImportRowResult(
        row_number=row.row_number,
        source_key=row.source_key,
        endpoint=row.endpoint,
        action='blocked',
        binding_requested=row.binding_spec is not None,
        failure_reason=reason,
    )


def _failure_reason(exc):
    if isinstance(exc, ValidationError):
        if hasattr(exc, 'message_dict'):
            messages = []
            for field_name, field_messages in exc.message_dict.items():
                field_text = '; '.join(str(message) for message in field_messages)
                messages.append(f'{field_name}: {field_text}')
            return ' '.join(messages)
        return '; '.join(str(message) for message in exc.messages)
    if isinstance(exc, InvalidOperation):
        return 'invalid decimal value in endpoint.'
    return str(exc) or exc.__class__.__name__


def _blank_to_none(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == '':
        return None
    return value


def _handoff_slug(endpoint):
    return _staging_stable_slug('madison-power-endpoint', endpoint.source_key, 'handoff')


bulk_import_staged_circuit_endpoints = import_staged_circuit_endpoints
