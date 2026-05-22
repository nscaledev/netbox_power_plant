from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Count
from django.urls import reverse

from netbox_power_plant import models
from netbox_power_plant.choices import PowerFindingSeverityChoices, PowerFindingStatusChoices
from netbox_power_plant.models import PowerFinding, PowerSystem, PowerValidationRun
from netbox_power_plant.services.capacity import build_power_system_capacity_summary
from netbox_power_plant.services.layout_validation import build_layout_health_summary
from netbox_power_plant.services.workflow_urls import build_layout_url, build_power_handoff_summary_url


SEVERITY_ORDER = (
    PowerFindingSeverityChoices.SEVERITY_CRITICAL,
    PowerFindingSeverityChoices.SEVERITY_ERROR,
    PowerFindingSeverityChoices.SEVERITY_WARNING,
    PowerFindingSeverityChoices.SEVERITY_INFO,
)


@dataclass(frozen=True)
class SeverityCount:
    severity: str
    label: str
    count: int
    url: str
    badge_class: str


@dataclass(frozen=True)
class OperatorDashboardRow:
    power_system: PowerSystem
    total_load_kw: Decimal
    total_capacity_kw: Decimal | None
    headroom_kw: Decimal | None
    capacity_finding_count: int
    severity_counts: tuple[SeverityCount, ...]
    open_finding_count: int
    layout_health: object
    recent_validation_runs: tuple[PowerValidationRun, ...]
    recent_instantiation_runs: tuple[object, ...]
    links: dict[str, str]


@dataclass(frozen=True)
class OperatorDashboard:
    rows: tuple[OperatorDashboardRow, ...]
    system_count: int
    open_finding_count: int
    critical_finding_count: int
    layout_issue_count: int


def build_operator_dashboard(*, system_limit=None, recent_run_limit=3) -> OperatorDashboard:
    systems = PowerSystem.objects.select_related('site', 'location').order_by('site__name', 'name', 'pk')
    if system_limit is not None:
        systems = systems[:system_limit]

    rows = tuple(
        _build_operator_row(power_system, recent_run_limit=recent_run_limit)
        for power_system in systems
    )
    return OperatorDashboard(
        rows=rows,
        system_count=len(rows),
        open_finding_count=sum(row.open_finding_count for row in rows),
        critical_finding_count=sum(_severity_count(row, PowerFindingSeverityChoices.SEVERITY_CRITICAL) for row in rows),
        layout_issue_count=sum(row.layout_health.finding_count for row in rows),
    )


def _build_operator_row(power_system, *, recent_run_limit) -> OperatorDashboardRow:
    capacity_summary = build_power_system_capacity_summary(power_system)
    layout_health = build_layout_health_summary(power_system)
    severity_counts = _build_severity_counts(power_system)
    links = _build_links(power_system)

    return OperatorDashboardRow(
        power_system=power_system,
        total_load_kw=capacity_summary.total_load_kw,
        total_capacity_kw=capacity_summary.total_capacity_kw,
        headroom_kw=capacity_summary.headroom_kw,
        capacity_finding_count=capacity_summary.finding_count,
        severity_counts=severity_counts,
        open_finding_count=sum(item.count for item in severity_counts),
        layout_health=layout_health,
        recent_validation_runs=tuple(
            PowerValidationRun.objects.filter(power_system=power_system)
            .order_by('-started_at', '-created')[:recent_run_limit]
        ),
        recent_instantiation_runs=_recent_instantiation_runs(power_system, recent_run_limit),
        links=links,
    )


def _build_severity_counts(power_system) -> tuple[SeverityCount, ...]:
    counts = {
        row['severity']: row['count']
        for row in PowerFinding.objects.filter(
            power_system=power_system,
            status=PowerFindingStatusChoices.STATUS_OPEN,
        ).values('severity').annotate(count=Count('pk'))
    }
    return tuple(
        SeverityCount(
            severity=severity,
            label=_severity_label(severity),
            count=counts.get(severity, 0),
            url=_query_url(
                'plugins:netbox_power_plant:powerfinding_list',
                power_system_id=power_system.pk,
                status=PowerFindingStatusChoices.STATUS_OPEN,
                severity=severity,
            ),
            badge_class=_severity_badge_class(severity),
        )
        for severity in SEVERITY_ORDER
    )


def _build_links(power_system) -> dict[str, str]:
    return {
        'detail': reverse('plugins:netbox_power_plant:powersystem', kwargs={'pk': power_system.pk}),
        'layout': build_layout_url(power_system),
        'handoff': build_power_handoff_summary_url(power_system),
        'handoff_list': _query_url(
            'plugins:netbox_power_plant:powerhandoffpoint_list',
            power_system_id=power_system.pk,
        ),
        'findings': _query_url(
            'plugins:netbox_power_plant:powerfinding_list',
            power_system_id=power_system.pk,
            status=PowerFindingStatusChoices.STATUS_OPEN,
        ),
        'validation_runs': _query_url(
            'plugins:netbox_power_plant:powervalidationrun_list',
            power_system_id=power_system.pk,
        ),
    }


def _recent_instantiation_runs(power_system, limit) -> tuple[object, ...]:
    run_model = getattr(models, 'InstantiationRun', None)
    if run_model is None:
        return ()
    return tuple(
        run_model.objects.filter(power_system=power_system)
        .select_related('template')
        .order_by('-created', 'name')[:limit]
    )


def _severity_count(row, severity) -> int:
    return next((item.count for item in row.severity_counts if item.severity == severity), 0)


def _severity_label(severity) -> str:
    return dict(PowerFindingSeverityChoices.CHOICES).get(severity, severity.title())


def _severity_badge_class(severity) -> str:
    return {
        PowerFindingSeverityChoices.SEVERITY_CRITICAL: 'text-bg-danger',
        PowerFindingSeverityChoices.SEVERITY_ERROR: 'text-bg-warning',
        PowerFindingSeverityChoices.SEVERITY_WARNING: 'text-bg-secondary',
        PowerFindingSeverityChoices.SEVERITY_INFO: 'text-bg-light',
    }.get(severity, 'text-bg-light')


def _query_url(viewname, **params) -> str:
    base_url = reverse(viewname)
    query = urlencode({key: value for key, value in params.items() if value not in (None, '')})
    return f'{base_url}?{query}' if query else base_url
