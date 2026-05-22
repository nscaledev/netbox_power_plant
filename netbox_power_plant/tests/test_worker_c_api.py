from django.urls import reverse
from utilities.testing import APITestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Rack, Site
from tenancy.models import Tenant

from netbox_power_plant.choices import (
    CapacityReservationStatusChoices,
    NodeKindChoices,
    PowerFindingSeverityChoices,
    PowerFindingStatusChoices,
    PowerValidationRunKindChoices,
    PowerValidationRunStatusChoices,
    RedundancyTopologyChoices,
    SegmentKindChoices,
    SupplyTypeChoices,
    TerminalDirectionChoices,
    TopologyStateChoices,
)
from netbox_power_plant.models import (
    CapacityReservation,
    ElectricalNode,
    ElectricalSegment,
    ElectricalTerminal,
    InstantiationRun,
    PowerArchitectureTemplate,
    PowerDomain,
    PowerFinding,
    PowerHandoffPoint,
    PowerSystem,
    PowerValidationRun,
    RedundancyGroup,
    TemplateNode,
)
from netbox_power_plant.services.cross_plugin import correlate_power_and_fabric_risk


class WorkerCOperationalAPITestCase(APITestCase):
    view_namespace = 'plugins-api:netbox_power_plant'

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
        cls.domain_a = PowerDomain.objects.create(
            name='Domain A',
            slug='domain-a',
            power_system=cls.power_system,
            code='A',
        )
        cls.domain_b = PowerDomain.objects.create(
            name='Domain B',
            slug='domain-b',
            power_system=cls.power_system,
            code='B',
        )
        cls.redundancy_group = RedundancyGroup.objects.create(
            name='Rack A/B Contract',
            slug='rack-a-b-contract',
            power_system=cls.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        cls.redundancy_group.power_domains.set([cls.domain_a, cls.domain_b])

        cls.source_a = cls._create_node('UPS A', 'ups-a', NodeKindChoices.KIND_UPS)
        cls.source_b = cls._create_node('UPS B', 'ups-b', NodeKindChoices.KIND_UPS)
        cls.rack_node = cls._create_node(
            'Rack A1 Boundary',
            'rack-a1-boundary',
            NodeKindChoices.KIND_RACK_CIRCUIT_TERMINATOR,
            usable_capacity_kw='5.00',
        )
        cls.sink_terminal = cls._create_terminal(
            cls.rack_node,
            'Rack Input A',
            'rack-input-a',
            TerminalDirectionChoices.DIRECTION_SINK,
        )
        cls.segment_a = cls._create_segment(
            cls._create_terminal(cls.source_a, 'UPS A Output', 'ups-a-output', TerminalDirectionChoices.DIRECTION_SOURCE),
            cls.sink_terminal,
            'UPS A to Rack A1',
            'ups-a-to-rack-a1',
            cls.domain_a,
        )
        cls.segment_b = cls._create_segment(
            cls._create_terminal(cls.source_b, 'UPS B Output', 'ups-b-output', TerminalDirectionChoices.DIRECTION_SOURCE),
            cls.sink_terminal,
            'UPS B to Rack A1',
            'ups-b-to-rack-a1',
            cls.domain_b,
        )

        cls.rack = Rack.objects.create(name='Rack A1', site=cls.site, location=cls.location)
        cls.tenant = Tenant.objects.create(name='GPU Tenant', slug='gpu-tenant')
        manufacturer = Manufacturer.objects.create(name='Test Manufacturer', slug='test-manufacturer')
        device_type = DeviceType.objects.create(model='Scenario Device', slug='scenario-device', manufacturer=manufacturer)
        device_role = DeviceRole.objects.create(name='Scenario Role', slug='scenario-role', color='ff0000')
        cls.device = Device.objects.create(
            name='Rack A1 Server',
            device_type=device_type,
            role=device_role,
            site=cls.site,
            location=cls.location,
            rack=cls.rack,
        )
        cls.power_port = PowerPort.objects.create(device=cls.device, name='PSU A', allocated_draw=800)
        cls.handoff = PowerHandoffPoint.objects.create(
            name='Rack A1 Handoff A',
            slug='rack-a1-handoff-a',
            power_system=cls.power_system,
            electrical_node=cls.rack_node,
            electrical_terminal=cls.sink_terminal,
            power_port=cls.power_port,
            expected_redundancy_group=cls.redundancy_group,
        )
        cls.validation_run = PowerValidationRun.objects.create(
            name='Topology Run',
            slug='topology-run',
            power_system=cls.power_system,
            run_kind=PowerValidationRunKindChoices.KIND_TOPOLOGY,
            status=PowerValidationRunStatusChoices.STATUS_COMPLETED,
        )
        cls.finding = PowerFinding.objects.create(
            name='Open Finding',
            slug='open-finding',
            run=cls.validation_run,
            power_system=cls.power_system,
            fingerprint='worker-c-finding',
            finding_type='test_finding',
            severity=PowerFindingSeverityChoices.SEVERITY_WARNING,
            status=PowerFindingStatusChoices.STATUS_OPEN,
            message='Needs operator review.',
        )
        cls.template = PowerArchitectureTemplate.objects.create(
            name='Single Node Template',
            slug='single-node-template',
            version='1',
        )
        TemplateNode.objects.create(
            name='Template Source',
            slug='template-source',
            template=cls.template,
            key='source',
            node_kind=NodeKindChoices.KIND_UPS,
        )

    @classmethod
    def _create_node(cls, name, slug, node_kind, **extra):
        return ElectricalNode.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=node_kind,
            topology_state=TopologyStateChoices.STATE_ACTIVE,
            **extra,
        )

    @classmethod
    def _create_terminal(cls, node, name, slug, direction):
        return ElectricalTerminal.objects.create(
            name=name,
            slug=slug,
            node=node,
            direction=direction,
            supply_type=SupplyTypeChoices.SUPPLY_AC,
        )

    @classmethod
    def _create_segment(cls, source_terminal, destination_terminal, name, slug, power_domain):
        return ElectricalSegment.objects.create(
            name=name,
            slug=slug,
            power_system=cls.power_system,
            from_terminal=source_terminal,
            to_terminal=destination_terminal,
            segment_kind=SegmentKindChoices.KIND_FEEDER,
            path_state=TopologyStateChoices.STATE_ACTIVE,
            power_domain=power_domain,
        )

    def test_capacity_rollup_reports_node_summary(self):
        CapacityReservation.objects.create(
            name='Rack A1 reserved capacity',
            slug='rack-a1-reserved-capacity-worker-c',
            node=self.rack_node,
            tenant=self.tenant,
            rack=self.rack,
            reserved_kw='0.50',
            status=CapacityReservationStatusChoices.STATUS_ACTIVE,
        )
        self.add_permissions('netbox_power_plant.view_electricalnode')
        response = self.client.get(
            reverse('plugins-api:netbox_power_plant-api:capacity-rollup'),
            {'node_id': self.rack_node.pk},
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['node']['id'], self.rack_node.pk)
        self.assertEqual(str(response.data['available_kw']), '3.700')
        self.assertEqual(response.data['first_bottleneck']['node']['id'], self.rack_node.pk)
        self.assertEqual(str(response.data['system_summary']['total_load_kw']), '0.800')
        self.assertEqual(str(response.data['system_summary']['total_reserved_kw']), '0.50')
        self.assertEqual(str(response.data['first_bottleneck']['total_load_kw']), '0.800')
        self.assertEqual(str(response.data['first_bottleneck']['total_reserved_kw']), '0.50')
        self.assertEqual(response.data['first_bottleneck']['load_breakdown'][0]['power_port']['id'], self.power_port.pk)
        self.assertEqual(
            response.data['first_bottleneck']['reservation_breakdown'][0]['tenant']['id'],
            self.tenant.pk,
        )

    def test_impact_node_and_domain_endpoints_return_rack_severity(self):
        self.add_permissions('netbox_power_plant.view_electricalnode', 'netbox_power_plant.view_powerdomain')
        node_response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:impact-node-offline'),
            {'power_system': self.power_system.pk, 'node': self.source_a.pk},
            format='json',
            **self.header,
        )
        domain_response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:impact-domain-lost'),
            {'power_system': self.power_system.pk, 'domain': self.domain_a.pk},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(node_response, 200)
        self.assertHttpStatus(domain_response, 200)
        self.assertEqual(node_response.data['racks'][0]['severity'], 'degraded')
        self.assertEqual(domain_response.data['racks'][0]['severity'], 'degraded')
        handoff = domain_response.data['racks'][0]['handoffs'][0]
        self.assertEqual(handoff['lost_domains'][0]['id'], self.domain_a.pk)
        self.assertEqual(handoff['remaining_domains'][0]['id'], self.domain_b.pk)
        self.assertFalse(handoff['redundancy']['compliant'])
        self.assertIn('domain_isolation_not_met', handoff['redundancy']['finding_types'])

    def test_validation_run_creation_posts_to_router_list(self):
        self.add_permissions('netbox_power_plant.add_powervalidationrun')
        response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:powervalidationrun-list'),
            {'power_system': self.power_system.pk, 'run_kind': PowerValidationRunKindChoices.KIND_TOPOLOGY},
            format='json',
            HTTP_IDEMPOTENCY_KEY='worker-c-validation-1',
            **self.header,
        )

        self.assertHttpStatus(response, 201)
        self.assertEqual(response.data['meta']['request_id'], 'worker-c-validation-1')
        self.assertFalse(response.data['meta']['idempotency_persisted'])
        self.assertEqual(response.data['run']['run_kind']['value'], PowerValidationRunKindChoices.KIND_TOPOLOGY)

    def test_validation_run_creation_rejects_scenario_without_scenario_payload(self):
        self.add_permissions('netbox_power_plant.add_powervalidationrun')
        response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:powervalidationrun-list'),
            {'power_system': self.power_system.pk, 'run_kind': PowerValidationRunKindChoices.KIND_SCENARIO},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 400)
        self.assertIn('Scenario validation requires', str(response.data['run_kind'][0]))

    def test_finding_acknowledge_suppress_and_resolve_actions(self):
        self.add_permissions('netbox_power_plant.change_powerfinding')
        acknowledge_response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:powerfinding-acknowledge', kwargs={'pk': self.finding.pk}),
            {'note': 'Reviewed during maintenance planning.'},
            format='json',
            **self.header,
        )
        suppress_response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:powerfinding-suppress', kwargs={'pk': self.finding.pk}),
            {'reason': 'Covered by approved work order.'},
            format='json',
            **self.header,
        )
        resolve_response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:powerfinding-resolve', kwargs={'pk': self.finding.pk}),
            {'reason': 'Corrected.'},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(acknowledge_response, 200)
        self.assertHttpStatus(suppress_response, 200)
        self.assertHttpStatus(resolve_response, 200)
        self.finding.refresh_from_db()
        self.assertIn('acknowledged_at', self.finding.details)
        self.assertEqual(self.finding.status, PowerFindingStatusChoices.STATUS_RESOLVED)
        self.assertIsNotNone(self.finding.resolved_at)

    def test_instantiation_run_create_and_apply(self):
        self.add_permissions(
            'netbox_power_plant.add_instantiationrun',
            'netbox_power_plant.change_instantiationrun',
        )
        create_response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:instantiationrun-list'),
            {'power_system': self.power_system.pk, 'template': self.template.pk, 'context': {'row': 'A'}},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(create_response, 201)
        self.assertIn('meta', create_response.data)
        self.assertTrue(create_response.data['run']['dry_run'])
        self.assertEqual(create_response.data['artifact_count'], 1)

        apply_response = self.client.post(
            reverse(
                'plugins-api:netbox_power_plant-api:instantiationrun-apply',
                kwargs={'pk': create_response.data['run']['id']},
            ),
            {},
            format='json',
            **self.header,
        )

        self.assertHttpStatus(apply_response, 200)
        self.assertFalse(apply_response.data['run']['dry_run'])
        self.assertGreaterEqual(InstantiationRun.objects.count(), 1)
        self.assertEqual(apply_response.data['run']['status'], 'applied')

    def test_cross_plugin_risk_degrades_when_fabric_plugin_is_absent(self):
        power_report = {
            'power_system': {'id': self.power_system.pk},
            'scenario_type': 'node_offline',
            'target': {'id': self.source_a.pk},
            'summary': {'critical_rack_count': 0, 'degraded_rack_count': 1},
            'racks': (),
        }

        result = correlate_power_and_fabric_risk(power_report)

        self.assertFalse(result.plugin_available)
        self.assertEqual(result.reason, 'netbox_plant_graph_not_installed')
        self.assertEqual(result.summary['joint_rack_count'], 0)

    def test_neocloud_cockpit_endpoint_returns_cross_plugin_operator_workflow(self):
        self.add_permissions(
            'netbox_power_plant.view_powersystem',
            'netbox_power_plant.view_powerdomain',
        )
        response = self.client.post(
            reverse('plugins-api:netbox_power_plant-api:neocloud-cockpit'),
            {
                'power_system': self.power_system.pk,
                'scenario_type': 'domain_lost',
                'target_id': self.domain_a.pk,
            },
            format='json',
            **self.header,
        )

        self.assertHttpStatus(response, 200)
        self.assertEqual(response.data['operator_summary']['degraded_rack_count'], 1)
        self.assertFalse(response.data['cross_plugin_risk']['plugin_available'])
        self.assertEqual(response.data['capacity_rollups'][0]['node_id'], self.rack_node.pk)
