from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import NodeKindChoices
from netbox_power_plant.models import ElectricalNode, PowerSystem, SpatialFrame, SpatialPlacement


class SpatialModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.other_site = Site.objects.create(name='Other Site', slug='other-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.other_location = Location.objects.create(site=cls.other_site, name='Electrical Room B', slug='electrical-room-b')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.other_power_system = PowerSystem.objects.create(
            name='Other Hall Power',
            slug='other-hall-power',
            site=cls.other_site,
            location=cls.other_location,
        )
        cls.node = ElectricalNode.objects.create(
            name='Row PDU A',
            slug='row-pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.other_node = ElectricalNode.objects.create(
            name='Foreign PDU',
            slug='foreign-pdu',
            power_system=cls.other_power_system,
            site=cls.other_site,
            location=cls.other_location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.node_type = ContentType.objects.get_for_model(ElectricalNode)

    def test_spatial_frame_rejects_location_from_another_site(self):
        frame = SpatialFrame(
            name='Wrong Site Frame',
            slug='wrong-site-frame',
            site=self.site,
            location=self.other_location,
        )

        with self.assertRaises(ValidationError):
            frame.full_clean()

    def test_spatial_frame_accepts_parent_from_same_site(self):
        parent = SpatialFrame.objects.create(name='Parent Frame', slug='parent-frame', site=self.site)
        child = SpatialFrame(
            name='Child Frame',
            slug='child-frame',
            site=self.site,
            parent_frame=parent,
            origin_x_in_parent='10.000',
            origin_y_in_parent='20.000',
        )

        child.full_clean()

    def test_spatial_placement_accepts_assigned_object_in_same_frame_scope(self):
        frame = SpatialFrame.objects.create(
            name='Room Frame',
            slug='room-frame',
            site=self.site,
            location=self.location,
        )
        placement = SpatialPlacement(
            name='Node Placement',
            slug='node-placement',
            spatial_frame=frame,
            assigned_object_type=self.node_type,
            assigned_object_id=self.node.pk,
            x='10.000',
            y='20.000',
        )

        placement.full_clean()

    def test_spatial_placement_rejects_assigned_object_from_another_site(self):
        frame = SpatialFrame.objects.create(name='Primary Frame', slug='primary-frame', site=self.site)
        placement = SpatialPlacement(
            name='Foreign Node Placement',
            slug='foreign-node-placement',
            spatial_frame=frame,
            assigned_object_type=self.node_type,
            assigned_object_id=self.other_node.pk,
            x='10.000',
            y='20.000',
        )

        with self.assertRaises(ValidationError):
            placement.full_clean()
