from __future__ import annotations

from dataclasses import dataclass

from netbox_power_plant.choices import PowerValidationRunKindChoices
from netbox_power_plant.services.findings import (
    PersistedFindingResult,
    run_and_persist_capacity_findings,
    run_and_persist_layout_findings,
    run_and_persist_physical_plant_findings,
    run_and_persist_scenario_findings,
    run_and_persist_topology_findings,
)


@dataclass(frozen=True)
class ValidationAction:
    run_kind: str
    label: str
    description: str


VALIDATION_ACTIONS = (
    ValidationAction(
        run_kind=PowerValidationRunKindChoices.KIND_TOPOLOGY,
        label='Run topology validation',
        description='Check active graph connectivity, orphan terminals, cycles, and handoff path redundancy.',
    ),
    ValidationAction(
        run_kind=PowerValidationRunKindChoices.KIND_LAYOUT,
        label='Run layout validation',
        description='Check spatial placement coverage and visible redundancy gaps.',
    ),
    ValidationAction(
        run_kind=PowerValidationRunKindChoices.KIND_CAPACITY,
        label='Run capacity validation',
        description='Check power-port load rollups against modeled node, segment, and bus capacity.',
    ),
    ValidationAction(
        run_kind=PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT,
        label='Run physical plant validation',
        description='Check blueprint-derived spaces, placements, bindings, elevation, and provenance coverage.',
    ),
)


def run_validation_action(power_system, run_kind: str, *, scenario=None, name: str | None = None) -> PersistedFindingResult:
    if run_kind == PowerValidationRunKindChoices.KIND_TOPOLOGY:
        return run_and_persist_topology_findings(power_system, name=name)
    if run_kind == PowerValidationRunKindChoices.KIND_LAYOUT:
        return run_and_persist_layout_findings(power_system, name=name)
    if run_kind == PowerValidationRunKindChoices.KIND_CAPACITY:
        return run_and_persist_capacity_findings(power_system, name=name)
    if run_kind == PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT:
        return run_and_persist_physical_plant_findings(power_system, name=name)
    if run_kind == PowerValidationRunKindChoices.KIND_SCENARIO:
        if scenario is None:
            raise ValueError('scenario is required for scenario validation.')
        return run_and_persist_scenario_findings(power_system, scenario, name=name)
    raise ValueError(f'Unsupported validation run kind: {run_kind}')


def validation_action_for_kind(run_kind: str) -> ValidationAction | None:
    return next((action for action in VALIDATION_ACTIONS if action.run_kind == run_kind), None)
