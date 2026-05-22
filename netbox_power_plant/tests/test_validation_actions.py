from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import PowerValidationRunKindChoices
from netbox_power_plant.models import PowerValidationRun, PowerSystem
from netbox_power_plant.services.validation_actions import (
    VALIDATION_ACTIONS,
    run_validation_action,
    validation_action_for_kind,
)


class ValidationActionServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )

    def test_exposes_operator_safe_validation_actions(self):
        self.assertEqual(
            tuple(action.run_kind for action in VALIDATION_ACTIONS),
            (
                PowerValidationRunKindChoices.KIND_TOPOLOGY,
                PowerValidationRunKindChoices.KIND_LAYOUT,
                PowerValidationRunKindChoices.KIND_CAPACITY,
                PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT,
            ),
        )
        action = validation_action_for_kind(PowerValidationRunKindChoices.KIND_TOPOLOGY)

        self.assertIsNotNone(action)
        self.assertEqual(action.label, 'Run topology validation')

        physical_action = validation_action_for_kind(PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT)

        self.assertIsNotNone(physical_action)
        self.assertEqual(physical_action.label, 'Run physical plant validation')

    def test_runs_and_persists_topology_validation(self):
        result = run_validation_action(
            self.power_system,
            PowerValidationRunKindChoices.KIND_TOPOLOGY,
            name='Manual Topology Check',
        )

        self.assertEqual(result.run.run_kind, PowerValidationRunKindChoices.KIND_TOPOLOGY)
        self.assertEqual(result.run.name, 'Manual Topology Check')
        self.assertEqual(PowerValidationRun.objects.count(), 1)

    def test_runs_and_persists_physical_plant_validation(self):
        result = run_validation_action(
            self.power_system,
            PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT,
            name='Manual Physical Plant Check',
        )

        self.assertEqual(result.run.run_kind, PowerValidationRunKindChoices.KIND_PHYSICAL_PLANT)
        self.assertEqual(result.run.name, 'Manual Physical Plant Check')
        self.assertEqual(PowerValidationRun.objects.count(), 1)

    def test_scenario_validation_requires_scenario(self):
        with self.assertRaisesMessage(ValueError, 'scenario is required'):
            run_validation_action(self.power_system, PowerValidationRunKindChoices.KIND_SCENARIO)
