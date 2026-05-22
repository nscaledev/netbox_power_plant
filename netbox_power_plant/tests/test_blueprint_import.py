from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PlantDisciplineChoices,
    PlantSourceLayerKindChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    PowerSystem,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.blueprint_import import (
    BlueprintPhysicalElementImportSummary,
    PhysicalElementReconciliationSummary,
    import_blueprint_physical_elements,
    reconcile_physical_elements_to_objects,
)


class BlueprintPhysicalElementImportTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name="MAD-1", slug="mad-1")
        cls.location = Location.objects.create(site=cls.site, name="Electrical Room A", slug="electrical-room-a")
        cls.power_system = PowerSystem.objects.create(
            name="MAD-1 Power Plant",
            slug="mad-1-power-plant",
            site=cls.site,
            location=cls.location,
        )
        cls.node = ElectricalNode.objects.create(
            name="UPS-A",
            slug="ups-a",
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_UPS,
        )
        cls.frame = SpatialFrame.objects.create(
            name="Electrical Room A Frame",
            slug="electrical-room-a-frame",
            site=cls.site,
            location=cls.location,
            width="100.000",
            height="100.000",
        )
        cls.source_document = PlantSourceDocument.objects.create(
            name="Electrical Plan Set",
            slug="electrical-plan-set",
            site=cls.site,
            location=cls.location,
        )
        cls.source_sheet = PlantSourceSheet.objects.create(
            name="E-101",
            slug="e-101",
            source_document=cls.source_document,
            sheet_number="E-101",
        )
        cls.source_layer = PlantSourceLayer.objects.create(
            name="Equipment Layer",
            slug="equipment-layer",
            source_sheet=cls.source_sheet,
            layer_name="EQUIP",
            layer_kind=PlantSourceLayerKindChoices.KIND_EQUIPMENT,
            discipline=PlantDisciplineChoices.DISCIPLINE_ELECTRICAL,
        )

    def test_dry_run_reports_stamped_objects_without_persisting(self):
        summary = import_blueprint_physical_elements(
            self.site,
            (
                {
                    "source_key": "UPS-A",
                    "label": "UPS-A",
                    "element_kind": PhysicalElementKindChoices.KIND_UPS,
                    "x": "10.000",
                    "y": "20.000",
                },
            ),
            default_location=self.location,
            default_spatial_frame=self.frame,
            default_source_layer=self.source_layer,
        )

        self.assertIsInstance(summary, BlueprintPhysicalElementImportSummary)
        self.assertTrue(summary.dry_run)
        self.assertTrue(summary.succeeded)
        self.assertEqual(summary.created_count, 1)
        self.assertEqual(summary.placed_count, 1)
        self.assertEqual(PhysicalElement.objects.count(), 0)
        self.assertEqual(SpatialPlacement.objects.count(), 0)
        self.assertEqual(PlantProvenance.objects.count(), 0)

    def test_apply_idempotently_stamps_element_placement_provenance_and_binding(self):
        row = {
            "source_key": "UPS-A",
            "label": "UPS-A",
            "element_kind": PhysicalElementKindChoices.KIND_UPS,
            "x": "10.000",
            "y": "20.000",
            "z": "1.000",
            "width": "5.000",
            "depth": "6.000",
            "source_ref": "symbol:ups-a",
            "assigned_object": self.node,
            "binding_role": PhysicalObjectBindingRoleChoices.ROLE_TOPOLOGY_NODE_FOR,
        }

        first_summary = import_blueprint_physical_elements(
            self.site,
            (row,),
            apply=True,
            default_location=self.location,
            default_spatial_frame=self.frame,
            default_source_layer=self.source_layer,
        )

        self.assertFalse(first_summary.dry_run)
        self.assertEqual(first_summary.created_count, 1)
        self.assertEqual(first_summary.bound_count, 1)
        self.assertEqual(PhysicalElement.objects.count(), 1)
        element = PhysicalElement.objects.get()
        self.assertEqual(element.source_label, "UPS-A")
        self.assertEqual(element.element_type.element_kind, PhysicalElementKindChoices.KIND_UPS)
        placement = SpatialPlacement.objects.get()
        self.assertEqual(placement.assigned_object, element)
        self.assertEqual(placement.x, 10)
        binding = PhysicalObjectBinding.objects.get()
        self.assertEqual(binding.physical_element, element)
        self.assertEqual(binding.spatial_placement, placement)
        self.assertEqual(binding.assigned_object, self.node)
        self.assertEqual(PlantProvenance.objects.count(), 2)

        second_summary = import_blueprint_physical_elements(
            self.site,
            ({**row, "x": "12.000"},),
            apply=True,
            default_location=self.location,
            default_spatial_frame=self.frame,
            default_source_layer=self.source_layer,
        )

        self.assertEqual(second_summary.created_count, 0)
        self.assertEqual(second_summary.updated_count, 1)
        self.assertEqual(PhysicalElement.objects.count(), 1)
        self.assertEqual(SpatialPlacement.objects.count(), 1)
        self.assertEqual(PhysicalObjectBinding.objects.count(), 1)
        self.assertEqual(PlantProvenance.objects.count(), 2)
        placement.refresh_from_db()
        self.assertEqual(placement.x, 12)

    def test_duplicate_source_keys_are_blocked_before_stamping(self):
        summary = import_blueprint_physical_elements(
            self.site,
            (
                {"source_key": "UPS-A", "label": "UPS-A"},
                {"source_key": "UPS-A", "label": "UPS-A duplicate"},
            ),
            apply=True,
            default_location=self.location,
        )

        self.assertEqual(summary.blocked_count, 2)
        self.assertEqual(PhysicalElement.objects.count(), 0)
        self.assertIn("duplicate source_key", summary.failure_reasons[0])

    def test_reconciliation_dry_run_and_apply_bind_blueprint_elements_to_objects(self):
        element_type = PhysicalElementType.objects.create(
            name="UPS Footprint",
            slug="ups-footprint",
            element_kind=PhysicalElementKindChoices.KIND_UPS,
        )
        element = PhysicalElement.objects.create(
            name="UPS-A Blueprint Footprint",
            slug="ups-a-blueprint-footprint",
            site=self.site,
            location=self.location,
            element_type=element_type,
            source_label="UPS A",
        )

        dry_run_summary = reconcile_physical_elements_to_objects(
            PhysicalElement.objects.filter(pk=element.pk),
            ElectricalNode.objects.filter(power_system=self.power_system),
            apply=False,
            object_field="name",
        )

        self.assertIsInstance(dry_run_summary, PhysicalElementReconciliationSummary)
        self.assertEqual(dry_run_summary.would_bind_count, 1)
        self.assertEqual(PhysicalObjectBinding.objects.count(), 0)

        apply_summary = reconcile_physical_elements_to_objects(
            PhysicalElement.objects.filter(pk=element.pk),
            ElectricalNode.objects.filter(power_system=self.power_system),
            apply=True,
            object_field="name",
        )

        self.assertEqual(apply_summary.bound_count, 1)
        binding = PhysicalObjectBinding.objects.get()
        self.assertEqual(binding.physical_element, element)
        self.assertEqual(binding.assigned_object_type, ContentType.objects.get_for_model(self.node))
        self.assertEqual(binding.assigned_object_id, self.node.pk)
