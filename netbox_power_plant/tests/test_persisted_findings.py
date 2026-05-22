from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Site

from netbox_power_plant.choices import (
    PowerFindingStatusChoices,
    PowerValidationRunKindChoices,
    PowerValidationRunStatusChoices,
)
from netbox_power_plant.models import PowerFinding, PowerSystem
from netbox_power_plant.services.findings import (
    build_fingerprint,
    create_validation_run,
    persist_findings_for_run,
)


class PersistedFindingServiceTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
        )

    def test_persist_findings_creates_open_findings_with_stable_fingerprint(self):
        run = create_validation_run(
            self.power_system,
            run_kind=PowerValidationRunKindChoices.KIND_TOPOLOGY,
            name='Topology Run',
            slug='topology-run',
        )

        result = persist_findings_for_run(run, (
            {
                'finding_type': 'missing_terminal',
                'message': 'Active nodes must expose at least one terminal.',
                'object': self.power_system,
            },
        ))

        finding = PowerFinding.objects.get(run=run)
        self.assertEqual(result.open_count, 1)
        self.assertEqual(result.run.status, PowerValidationRunStatusChoices.STATUS_COMPLETED)
        self.assertEqual(finding.status, PowerFindingStatusChoices.STATUS_OPEN)
        self.assertEqual(finding.assigned_object_type, ContentType.objects.get_for_model(self.power_system))
        self.assertEqual(finding.assigned_object_id, self.power_system.pk)
        self.assertEqual(
            finding.fingerprint,
            build_fingerprint(
                run_kind=PowerValidationRunKindChoices.KIND_TOPOLOGY,
                finding_type='missing_terminal',
                assigned_object=self.power_system,
                details={'finding_type': 'missing_terminal'},
            ),
        )

    def test_persist_findings_closes_stale_findings_for_run(self):
        run = create_validation_run(
            self.power_system,
            run_kind=PowerValidationRunKindChoices.KIND_LAYOUT,
            name='Layout Run',
            slug='layout-run',
        )
        persist_findings_for_run(run, (
            {
                'finding_type': 'unmapped_delivery_handoff',
                'message': 'Missing placement.',
                'object': self.power_system,
            },
        ))

        result = persist_findings_for_run(run, ())

        finding = PowerFinding.objects.get(run=run)
        self.assertEqual(result.open_count, 0)
        self.assertEqual(result.resolved_count, 1)
        self.assertEqual(finding.status, PowerFindingStatusChoices.STATUS_RESOLVED)
        self.assertIsNotNone(finding.resolved_at)
