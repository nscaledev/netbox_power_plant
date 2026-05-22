from django.test import TestCase

from dcim.models import Device, DeviceRole, DeviceType, Location, Manufacturer, PowerPort, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    RedundancyTopologyChoices,
    SegmentKindChoices,
    TerminalDirectionChoices,
    TerminalRoleChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    InstantiationArtifact,
    InstantiationRun,
    PowerArchitectureTemplate,
    PowerHandoffPoint,
    RedundancyGroup,
    PowerSystem,
    TemplateNode,
    TemplatePlacementRule,
    TemplateSegment,
    TemplateTerminal,
)
from netbox_power_plant.services.reference_templates import REFERENCE_TEMPLATE_SLUGS, seed_reference_templates
from netbox_power_plant.services.templates import apply_existing_instantiation_run, instantiate_template
from netbox_power_plant.services.template_workflows import (
    apply_reviewed_instantiation_run,
    build_instantiation_result_payload,
    build_template_dry_run_preview,
    list_reference_templates,
)


class TemplateInstantiationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="Primary Site", slug="primary-site")
        cls.location = Location.objects.create(site=cls.site, name="Electrical Room A", slug="electrical-room-a")
        cls.power_system = PowerSystem.objects.create(
            name="Primary Hall Power",
            slug="primary-hall-power",
            site=cls.site,
            location=cls.location,
        )
        cls.template = PowerArchitectureTemplate.objects.create(
            name="Two Node Feed Template",
            slug="two-node-feed-template",
            version="1",
        )
        source = TemplateNode.objects.create(
            name="Template Source",
            slug="template-source",
            template=cls.template,
            key="source",
            node_kind=NodeKindChoices.KIND_UPS,
        )
        sink = TemplateNode.objects.create(
            name="Template Sink",
            slug="template-sink",
            template=cls.template,
            key="sink",
            parent_key="source",
            node_kind=NodeKindChoices.KIND_PDU,
        )
        TemplateTerminal.objects.create(
            name="Template Source Output",
            slug="template-source-output",
            template_node=source,
            key="output",
            terminal_role=TerminalRoleChoices.ROLE_OUTPUT,
            direction=TerminalDirectionChoices.DIRECTION_SOURCE,
            position_index=1,
        )
        TemplateTerminal.objects.create(
            name="Template Sink Input",
            slug="template-sink-input",
            template_node=sink,
            key="input",
            terminal_role=TerminalRoleChoices.ROLE_INPUT,
            direction=TerminalDirectionChoices.DIRECTION_SINK,
            position_index=1,
        )
        TemplateSegment.objects.create(
            name="Template Source to Sink",
            slug="template-source-to-sink",
            template=cls.template,
            key="source-to-sink",
            from_node_key="source",
            from_terminal_key="output",
            to_node_key="sink",
            to_terminal_key="input",
            segment_kind=SegmentKindChoices.KIND_FEEDER,
        )
        TemplatePlacementRule.objects.create(
            name="Template Sink Placement",
            slug="template-sink-placement",
            template_node=sink,
            x="12.00",
            y="24.00",
            width="4.00",
            height="2.00",
        )

    def test_dry_run_persists_proposed_artifacts_without_topology_writes(self):
        result = instantiate_template(self.power_system, self.template, context={"row": "A"})

        self.assertEqual(result.run.status, "dry-run")
        self.assertTrue(result.run.dry_run)
        self.assertEqual(result.run.artifact_count, 6)
        self.assertEqual(len(result.artifacts), 6)
        self.assertEqual(ElectricalNode.objects.count(), 0)
        self.assertEqual(ElectricalTerminal.objects.count(), 0)
        self.assertEqual(ElectricalSegment.objects.count(), 0)
        self.assertEqual(ElectricalNodePlacement.objects.count(), 0)
        self.assertEqual(InstantiationRun.objects.count(), 1)
        self.assertEqual(InstantiationArtifact.objects.filter(run=result.run, status="proposed").count(), 6)

    def test_apply_idempotently_creates_and_updates_template_artifacts(self):
        first_result = instantiate_template(self.power_system, self.template, apply=True)

        self.assertEqual(first_result.run.status, "applied")
        self.assertFalse(first_result.run.dry_run)
        self.assertEqual(first_result.created_count, 6)
        self.assertEqual(ElectricalNode.objects.count(), 2)
        self.assertEqual(ElectricalTerminal.objects.count(), 2)
        self.assertEqual(ElectricalSegment.objects.count(), 1)
        self.assertEqual(ElectricalNodePlacement.objects.count(), 1)

        source = ElectricalNode.objects.get(slug="primary-hall-power-two-node-feed-template-node-source")
        sink = ElectricalNode.objects.get(slug="primary-hall-power-two-node-feed-template-node-sink")
        self.assertEqual(sink.parent_node, source)
        self.assertTrue(
            InstantiationArtifact.objects.filter(
                run=first_result.run,
                status="applied",
                object_id=sink.pk,
                stable_slug=sink.slug,
            ).exists()
        )

        second_result = instantiate_template(self.power_system, self.template, apply=True)

        self.assertEqual(second_result.updated_count, 6)
        self.assertEqual(ElectricalNode.objects.count(), 2)
        self.assertEqual(ElectricalTerminal.objects.count(), 2)
        self.assertEqual(ElectricalSegment.objects.count(), 1)
        self.assertEqual(ElectricalNodePlacement.objects.count(), 1)
        self.power_system.refresh_from_db()
        self.assertTrue(self.power_system.is_template_derived)

    def test_apply_existing_dry_run_uses_stored_artifacts(self):
        dry_run = instantiate_template(self.power_system, self.template)
        artifact_ids = set(dry_run.run.artifacts.values_list("pk", flat=True))

        result = apply_existing_instantiation_run(dry_run.run)

        self.assertEqual(result.run.pk, dry_run.run.pk)
        self.assertEqual(result.run.status, "applied")
        self.assertFalse(result.run.dry_run)
        self.assertEqual(set(result.run.artifacts.values_list("pk", flat=True)), artifact_ids)
        self.assertEqual(result.run.artifacts.filter(status="applied", object_id__isnull=False).count(), 6)
        self.assertEqual(ElectricalNode.objects.count(), 2)
        self.assertEqual(ElectricalTerminal.objects.count(), 2)
        self.assertEqual(ElectricalSegment.objects.count(), 1)
        self.power_system.refresh_from_db()
        self.assertTrue(self.power_system.is_template_derived)

    def test_update_dry_run_includes_operator_readable_artifact_summaries(self):
        instantiate_template(self.power_system, self.template, apply=True)

        dry_run = instantiate_template(self.power_system, self.template)
        payload = build_instantiation_result_payload(dry_run)

        self.assertEqual(dry_run.summary["updated"], 6)
        self.assertEqual(payload["summary"]["updated"], 6)
        self.assertTrue(all(summary["action"] == "update" for summary in dry_run.artifact_summaries))
        self.assertTrue(all(summary["object_ref"] for summary in dry_run.artifact_summaries))
        self.assertIn("Update node", next(summary["operator_summary"] for summary in dry_run.artifact_summaries))

    def test_handoff_is_skipped_when_required_context_is_missing(self):
        sink = TemplateNode.objects.get(template=self.template, key="sink")
        sink.attributes = {
            "power_handoffs": [
                {
                    "key": "sink-handoff",
                    "terminal_key": "input",
                    "power_port_context_key": "sink_power_port_id",
                    "feed_label": "A-feed",
                    "delivery_role": "primary",
                },
            ],
        }
        sink.save(update_fields=("attributes",))

        result = instantiate_template(self.power_system, self.template)

        handoff = InstantiationArtifact.objects.get(run=result.run, artifact_type="power_handoff")
        self.assertEqual(handoff.action, "skip")
        self.assertEqual(handoff.status, "skipped")
        self.assertIn("sink_power_port_id", handoff.proposed_data["skip_reason"])
        self.assertEqual(PowerHandoffPoint.objects.count(), 0)

    def test_handoff_is_applied_when_power_port_id_is_supplied(self):
        power_port = self._create_power_port("Rack PDU A", "Input A")
        redundancy_group = RedundancyGroup.objects.create(
            name="Rack Feed 2N",
            slug="rack-feed-2n",
            power_system=self.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        sink = TemplateNode.objects.get(template=self.template, key="sink")
        sink.attributes = {
            "power_handoffs": [
                {
                    "key": "sink-handoff",
                    "terminal_key": "input",
                    "name_format": "{power_system} Rack Input A",
                    "slug_format": "{power_system_slug}-rack-input-a",
                    "power_port_context_key": "sink_power_port_id",
                    "expected_redundancy_group_context_key": "rack_redundancy_group_id",
                    "feed_label": "A-feed",
                    "delivery_role": "primary",
                },
            ],
        }
        sink.save(update_fields=("attributes",))

        result = instantiate_template(
            self.power_system,
            self.template,
            context={
                "sink_power_port_id": power_port.pk,
                "rack_redundancy_group_id": redundancy_group.pk,
            },
            apply=True,
        )

        handoff = PowerHandoffPoint.objects.get(slug="primary-hall-power-rack-input-a")
        self.assertEqual(handoff.power_port, power_port)
        self.assertEqual(handoff.electrical_terminal.node.slug, "primary-hall-power-two-node-feed-template-node-sink")
        self.assertEqual(handoff.expected_redundancy_group, redundancy_group)
        self.assertEqual(handoff.feed_label, "A-feed")
        self.assertTrue(
            InstantiationArtifact.objects.filter(
                run=result.run,
                artifact_type="power_handoff",
                status="applied",
                object_id=handoff.pk,
            ).exists()
        )

    def test_reference_template_seed_is_idempotent_and_repeatable(self):
        first = seed_reference_templates()
        counts = {
            "templates": PowerArchitectureTemplate.objects.filter(slug__in=REFERENCE_TEMPLATE_SLUGS).count(),
            "nodes": TemplateNode.objects.count(),
            "terminals": TemplateTerminal.objects.count(),
            "segments": TemplateSegment.objects.count(),
            "placements": TemplatePlacementRule.objects.count(),
        }
        second = seed_reference_templates()

        self.assertEqual(tuple(template.slug for template in first), REFERENCE_TEMPLATE_SLUGS)
        self.assertEqual(tuple(template.slug for template in second), REFERENCE_TEMPLATE_SLUGS)
        self.assertEqual(PowerArchitectureTemplate.objects.filter(slug__in=REFERENCE_TEMPLATE_SLUGS).count(), 3)
        self.assertEqual(TemplateNode.objects.count(), counts["nodes"])
        self.assertEqual(TemplateTerminal.objects.count(), counts["terminals"])
        self.assertEqual(TemplateSegment.objects.count(), counts["segments"])
        self.assertEqual(TemplatePlacementRule.objects.count(), counts["placements"])

        template = PowerArchitectureTemplate.objects.get(slug="ai-pod-2n-ups-busway")
        result = instantiate_template(self.power_system, template, context={"rack_feed_count": 2})
        node_keys = {artifact.template_key for artifact in result.artifacts if artifact.artifact_type == "node"}

        self.assertEqual(counts["templates"], 3)
        self.assertIn("rack-feed-a-1", node_keys)
        self.assertIn("rack-feed-b-2", node_keys)
        self.assertTrue(
            InstantiationArtifact.objects.filter(
                run=result.run,
                artifact_type="power_handoff",
                status="skipped",
            ).exists()
        )

    def test_reference_templates_match_full_neocloud_chains(self):
        seed_reference_templates()

        two_n = PowerArchitectureTemplate.objects.get(slug="ai-pod-2n-ups-busway")
        two_n_node_keys = set(two_n.nodes.values_list("key", flat=True))
        two_n_segment_keys = set(two_n.segments.values_list("key", flat=True))

        self.assertTrue(
            {
                "utility",
                "generator-a",
                "generator-b",
                "ats",
                "lv-switchboard-a",
                "lv-switchboard-b",
                "ups-bank-a",
                "ups-bank-b",
                "busway-a",
                "busway-b",
                "rack-feed-a",
                "rack-feed-b",
            }.issubset(two_n_node_keys)
        )
        self.assertTrue(
            {
                "utility-to-ats",
                "generator-a-to-ats",
                "generator-b-to-ats",
                "ats-to-lv-a",
                "ats-to-lv-b",
                "lv-a-to-ups-a",
                "lv-b-to-ups-b",
                "ups-a-to-busway-a",
                "ups-b-to-busway-b",
                "busway-a-to-rack-feed",
                "busway-b-to-rack-feed",
            }.issubset(two_n_segment_keys)
        )

        distributed = PowerArchitectureTemplate.objects.get(slug="ai-pod-distributed-redundant-ups")
        distributed_node_keys = set(distributed.nodes.values_list("key", flat=True))
        self.assertTrue(
            {
                "utility",
                "generator-a",
                "generator-b",
                "paralleling-gear",
                "transformer-a",
                "transformer-b",
                "lv-switchboard-a",
                "lv-switchboard-b",
                "ups-a",
                "ups-b",
                "busway-a",
                "busway-b",
                "rack-pdu",
            }.issubset(distributed_node_keys)
        )

        dc = PowerArchitectureTemplate.objects.get(slug="high-density-dc-48v")
        self.assertTrue(
            {"lv-switchboard", "rectifier", "dc-bus", "rack-dc-terminal"}.issubset(
                set(dc.nodes.values_list("key", flat=True))
            )
        )
        self.assertEqual(dc.nodes.get(key="rectifier").phase_mode, "mixed")
        self.assertEqual(
            dc.nodes.get(key="rack-dc-terminal").attributes["repeat"]["count_context_key"], "dc_feed_count"
        )

    def test_operator_workflow_applies_reviewed_reference_dry_run_in_place(self):
        seed_reference_templates()
        template = PowerArchitectureTemplate.objects.get(slug="ai-pod-2n-ups-busway")
        ports = {
            "rack_feed_a_power_port_1": self._create_power_port("Rack 1 PDU A", "Input A").pk,
            "rack_feed_b_power_port_1": self._create_power_port("Rack 1 PDU B", "Input B").pk,
            "rack_feed_a_power_port_2": self._create_power_port("Rack 2 PDU A", "Input A").pk,
            "rack_feed_b_power_port_2": self._create_power_port("Rack 2 PDU B", "Input B").pk,
        }
        redundancy_group = RedundancyGroup.objects.create(
            name="Reference Rack 2N",
            slug="reference-rack-2n",
            power_system=self.power_system,
            topology_type=RedundancyTopologyChoices.TOPOLOGY_2N,
            min_distinct_paths=2,
            requires_domain_isolation=True,
        )
        context = {
            "rack_feed_count": 2,
            "rack_feed_redundancy_group_id": redundancy_group.pk,
            **ports,
        }

        dry_run = build_template_dry_run_preview(self.power_system, template.slug, context=context)
        artifact_ids = set(dry_run.run.artifacts.values_list("pk", flat=True))
        applied = apply_reviewed_instantiation_run(dry_run.run.pk)

        self.assertEqual(applied.run.pk, dry_run.run.pk)
        self.assertEqual(set(applied.run.artifacts.values_list("pk", flat=True)), artifact_ids)
        self.assertEqual(applied.summary["skipped"], 0)
        self.assertEqual(ElectricalNode.objects.filter(slug__contains="ai-pod-2n-ups-busway-node-rack-feed").count(), 4)
        self.assertEqual(
            ElectricalSegment.objects.filter(segment_kind=SegmentKindChoices.KIND_TAP_CONNECTION).count(), 4
        )
        self.assertEqual(PowerHandoffPoint.objects.count(), 4)

        second_preview = build_template_dry_run_preview(self.power_system, template, context=context)
        self.assertGreater(second_preview.summary["updated"], 0)
        self.assertEqual(ElectricalNode.objects.filter(slug__contains="ai-pod-2n-ups-busway-node-rack-feed").count(), 4)

    def test_missing_reference_handoff_context_surfaces_skip_reasons(self):
        seed_reference_templates()
        template = PowerArchitectureTemplate.objects.get(slug="high-density-dc-48v")

        result = build_template_dry_run_preview(self.power_system, template, context={"dc_feed_count": 2})
        skipped = [artifact for artifact in result.artifacts if artifact.status == "skipped"]

        self.assertEqual(len(skipped), 2)
        self.assertEqual(result.summary["skipped"], 2)
        self.assertTrue(all("rack_dc_power_port_" in artifact.proposed_data["skip_reason"] for artifact in skipped))
        self.assertTrue(
            all("Skip power_handoff" in artifact.proposed_data["review"]["operator_summary"] for artifact in skipped)
        )

    def test_reference_template_listing_can_seed_missing_templates(self):
        templates = list_reference_templates(seed_missing=True)

        self.assertEqual(tuple(template.slug for template in templates), REFERENCE_TEMPLATE_SLUGS)

    def _create_power_port(self, device_name, port_name):
        manufacturer = Manufacturer.objects.create(
            name=f"{device_name} Manufacturer", slug=f'{device_name.lower().replace(" ", "-")}-mfg'
        )
        device_type = DeviceType.objects.create(
            manufacturer=manufacturer,
            model=f"{device_name} Type",
            slug=f'{device_name.lower().replace(" ", "-")}-type',
        )
        role = DeviceRole.objects.create(
            name=f"{device_name} Role",
            slug=f'{device_name.lower().replace(" ", "-")}-role',
            color="ff0000",
        )
        device = Device.objects.create(
            name=device_name,
            device_type=device_type,
            role=role,
            site=self.site,
            location=self.location,
        )
        return PowerPort.objects.create(device=device, name=port_name)
