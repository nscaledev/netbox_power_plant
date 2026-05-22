from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha1

from django.db import transaction
from django.utils.text import slugify

from dcim.models import PowerPort

from netbox_power_plant.choices import (
    DesignStateChoices,
    NodeKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TerminalRoleChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import ElectricalNode, ElectricalTerminal, PowerDomain, PowerHandoffPoint, PowerSystem


STAGING_DESCRIPTION_PREFIX = 'Madison staged power endpoint'


@dataclass(frozen=True)
class StagedCircuitEndpoint:
    source_key: str
    source_name: str | None = None
    cabinet_label: str | None = None
    feed_label: str | None = None
    domain_code: str | None = None
    voltage_nominal: Decimal | int | str | None = None
    amperage_rating: Decimal | int | str | None = None
    power_kw: Decimal | int | str | None = None
    node_name: str | None = None
    terminal_name: str | None = None
    connector_type: str | None = None
    phase_designation: str | None = None


@dataclass(frozen=True)
class StagedCircuitEndpointResult:
    endpoint: StagedCircuitEndpoint
    node: ElectricalNode
    terminal: ElectricalTerminal
    power_domain: PowerDomain | None
    node_created: bool
    terminal_created: bool


@transaction.atomic
def stage_circuit_endpoint(
    power_system: PowerSystem,
    endpoint: StagedCircuitEndpoint | dict,
) -> StagedCircuitEndpointResult:
    """
    Create or update the plant-side boundary node and terminal for a schedule row.

    This intentionally does not create a PowerHandoffPoint. A staged circuit is
    not considered connected to NetBox device inventory until a concrete
    dcim.PowerPort is supplied to bind_handoff_to_power_port().
    """
    endpoint = _coerce_endpoint(endpoint)
    power_domain = _resolve_power_domain(power_system, endpoint.domain_code)
    node_slug = _stable_slug('madison-power-endpoint', endpoint.source_key, 'node')
    terminal_slug = _stable_slug('madison-power-endpoint', endpoint.source_key, 'terminal')

    node, node_created = ElectricalNode.objects.update_or_create(
        slug=node_slug,
        defaults={
            'name': _truncate(endpoint.node_name or _default_node_name(endpoint), 100),
            'power_system': power_system,
            'site': power_system.site,
            'location': power_system.location,
            'node_kind': NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            'equipment_role': 'staged_power_endpoint',
            'install_state': TopologyStateChoices.STATE_PLANNED,
            'topology_state': TopologyStateChoices.STATE_PLANNED,
            'rated_input_voltage_min': _decimal_or_none(endpoint.voltage_nominal),
            'rated_input_voltage_max': _decimal_or_none(endpoint.voltage_nominal),
            'usable_capacity_kw': _decimal_or_none(endpoint.power_kw),
            'description': _node_description(endpoint),
        },
    )

    terminal, terminal_created = ElectricalTerminal.objects.update_or_create(
        slug=terminal_slug,
        defaults={
            'name': _truncate(endpoint.terminal_name or _default_terminal_name(endpoint), 100),
            'node': node,
            'terminal_role': TerminalRoleChoices.ROLE_INPUT,
            'direction': TerminalDirectionChoices.DIRECTION_SINK,
            'supply_type': SupplyTypeChoices.SUPPLY_AC,
            'voltage_nominal': _decimal_or_none(endpoint.voltage_nominal),
            'amperage_rating': _decimal_or_none(endpoint.amperage_rating),
            'phase_designation': _truncate(endpoint.phase_designation or '', 32),
            'connector_type': _truncate(endpoint.connector_type or '', 64),
            'description': _terminal_description(endpoint, power_domain),
        },
    )

    return StagedCircuitEndpointResult(
        endpoint=endpoint,
        node=node,
        terminal=terminal,
        power_domain=power_domain,
        node_created=node_created,
        terminal_created=terminal_created,
    )


@transaction.atomic
def bind_handoff_to_power_port(
    power_system: PowerSystem,
    endpoint: StagedCircuitEndpoint | dict,
    power_port: PowerPort,
    *,
    delivery_role: str = 'staged-circuit-handoff',
    design_state: str = DesignStateChoices.STATE_PLANNED,
) -> PowerHandoffPoint:
    """
    Bind a staged endpoint to a real NetBox PowerPort.

    The resulting PowerHandoffPoint is idempotent by endpoint source key and
    always targets dcim.PowerPort.
    """
    if not isinstance(power_port, PowerPort):
        raise TypeError('power_port must be a dcim.models.PowerPort instance.')

    staged = stage_circuit_endpoint(power_system, endpoint)
    handoff_slug = _stable_slug('madison-power-endpoint', staged.endpoint.source_key, 'handoff')
    handoff = PowerHandoffPoint.objects.filter(slug=handoff_slug).first() or PowerHandoffPoint(slug=handoff_slug)
    handoff.name = _truncate(_default_handoff_name(staged.endpoint), 100)
    handoff.power_system = power_system
    handoff.electrical_node = staged.node
    handoff.electrical_terminal = staged.terminal
    handoff.power_port = power_port
    handoff.delivery_role = _truncate(delivery_role, 100)
    handoff.feed_label = _truncate(staged.endpoint.feed_label or '', 100)
    handoff.design_state = design_state
    handoff.description = _handoff_description(staged.endpoint, power_port)
    handoff.full_clean()
    handoff.save()
    return handoff


def _coerce_endpoint(endpoint: StagedCircuitEndpoint | dict) -> StagedCircuitEndpoint:
    if isinstance(endpoint, StagedCircuitEndpoint):
        _validate_endpoint(endpoint)
        return endpoint
    if isinstance(endpoint, dict):
        coerced = StagedCircuitEndpoint(**endpoint)
        _validate_endpoint(coerced)
        return coerced
    raise TypeError('endpoint must be a StagedCircuitEndpoint or dict.')


def _validate_endpoint(endpoint: StagedCircuitEndpoint) -> None:
    if not endpoint.source_key:
        raise ValueError('source_key is required.')


def _resolve_power_domain(power_system: PowerSystem, domain_code: str | None) -> PowerDomain | None:
    if not domain_code:
        return None
    return PowerDomain.objects.filter(power_system=power_system, code=domain_code).first()


def _default_node_name(endpoint: StagedCircuitEndpoint) -> str:
    parts = ['Staged power endpoint']
    if endpoint.cabinet_label:
        parts.append(endpoint.cabinet_label)
    if endpoint.feed_label:
        parts.append(endpoint.feed_label)
    parts.append(endpoint.source_key)
    return ' - '.join(parts)


def _default_terminal_name(endpoint: StagedCircuitEndpoint) -> str:
    parts = ['Staged power terminal']
    if endpoint.cabinet_label:
        parts.append(endpoint.cabinet_label)
    if endpoint.feed_label:
        parts.append(endpoint.feed_label)
    parts.append(endpoint.source_key)
    return ' - '.join(parts)


def _default_handoff_name(endpoint: StagedCircuitEndpoint) -> str:
    parts = ['Power handoff']
    if endpoint.cabinet_label:
        parts.append(endpoint.cabinet_label)
    if endpoint.feed_label:
        parts.append(endpoint.feed_label)
    parts.append(endpoint.source_key)
    return ' - '.join(parts)


def _node_description(endpoint: StagedCircuitEndpoint) -> str:
    return _description(endpoint, 'unresolved boundary node')


def _terminal_description(endpoint: StagedCircuitEndpoint, power_domain: PowerDomain | None) -> str:
    suffix = 'unresolved boundary terminal'
    if endpoint.domain_code:
        suffix = f'{suffix}; domain={endpoint.domain_code}'
        if power_domain is None:
            suffix = f'{suffix} unresolved'
    return _description(endpoint, suffix)


def _handoff_description(endpoint: StagedCircuitEndpoint, power_port: PowerPort) -> str:
    device = getattr(power_port, 'device', None)
    device_name = getattr(device, 'name', None) or str(device)
    return _truncate(f'{_description(endpoint, "bound handoff")} -> {device_name}:{power_port.name}', 200)


def _description(endpoint: StagedCircuitEndpoint, suffix: str) -> str:
    parts = [STAGING_DESCRIPTION_PREFIX, f'source={endpoint.source_key}', suffix]
    if endpoint.source_name:
        parts.insert(1, endpoint.source_name)
    if endpoint.cabinet_label:
        parts.append(f'cabinet={endpoint.cabinet_label}')
    if endpoint.feed_label:
        parts.append(f'feed={endpoint.feed_label}')
    return _truncate('; '.join(parts), 200)


def _stable_slug(*parts: str) -> str:
    raw_value = '-'.join(str(part) for part in parts if part)
    slug = slugify(raw_value) or 'staged-power-endpoint'
    if len(slug) <= 100:
        return slug
    digest = sha1(slug.encode('utf-8')).hexdigest()[:8]
    return f'{slug[:91].rstrip("-")}-{digest}'


def _decimal_or_none(value: Decimal | int | str | None) -> Decimal | None:
    if value in (None, ''):
        return None
    return Decimal(str(value))


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[:max_length]
