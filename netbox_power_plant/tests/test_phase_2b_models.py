from django.core.exceptions import ValidationError
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import NodeKindChoices, PlacementScopeChoices
from netbox_power_plant.models import ElectricalNode, ElectricalNodePlacement, PowerSystem


class Phase2BModelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Primary Site', slug='primary-site')
        cls.other_site = Site.objects.create(name='Other Site', slug='other-site')
        cls.location = Location.objects.create(site=cls.site, name='Electrical Room A', slug='electrical-room-a')
        cls.other_location = Location.objects.create(site=cls.other_site, name='Electrical Room B', slug='electrical-room-b')
        cls.same_site_other_location = Location.objects.create(site=cls.site, name='Electrical Room C', slug='electrical-room-c')
        cls.power_system = PowerSystem.objects.create(
            name='Primary Hall Power',
            slug='primary-hall-power',
            site=cls.site,
            location=cls.location,
        )
        cls.site_only_power_system = PowerSystem.objects.create(
            name='Campus Yard Power',
            slug='campus-yard-power',
            site=cls.site,
            location=None,
        )
        cls.other_power_system = PowerSystem.objects.create(
            name='Secondary Hall Power',
            slug='secondary-hall-power',
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
        cls.site_only_node = ElectricalNode.objects.create(
            name='Site Switchboard',
            slug='site-switchboard',
            power_system=cls.site_only_power_system,
            site=cls.site,
            location=None,
            node_kind=NodeKindChoices.KIND_LV_SWITCHBOARD,
        )
        cls.other_node = ElectricalNode.objects.create(
            name='Foreign PDU',
            slug='foreign-pdu',
            power_system=cls.other_power_system,
            site=cls.other_site,
            location=cls.other_location,
            node_kind=NodeKindChoices.KIND_PDU,
        )

    def test_rejects_node_from_another_power_system(self):
        placement = ElectricalNodePlacement(
            name='Foreign Placement',
            slug='foreign-placement',
            power_system=self.power_system,
            electrical_node=self.other_node,
            site=self.site,
            location=self.location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='10.00',
            y='20.00',
        )

        with self.assertRaises(ValidationError):
            placement.full_clean()

    def test_rejects_location_mismatch_for_resolved_spatial_scope(self):
        placement = ElectricalNodePlacement(
            name='Wrong Room Placement',
            slug='wrong-room-placement',
            power_system=self.power_system,
            electrical_node=self.node,
            site=self.site,
            location=self.same_site_other_location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='11.00',
            y='21.00',
        )

        with self.assertRaises(ValidationError):
            placement.full_clean()

    def test_rejects_duplicate_placement_for_same_node_scope(self):
        ElectricalNodePlacement.objects.create(
            name='Primary Placement',
            slug='primary-placement',
            power_system=self.power_system,
            electrical_node=self.node,
            site=self.site,
            location=self.location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='10.00',
            y='20.00',
        )
        duplicate = ElectricalNodePlacement(
            name='Duplicate Placement',
            slug='duplicate-placement',
            power_system=self.power_system,
            electrical_node=self.node,
            site=self.site,
            location=self.location,
            placement_scope_type=PlacementScopeChoices.SCOPE_LOCATION,
            x='30.00',
            y='40.00',
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_accepts_site_scoped_placement_when_power_system_has_no_location(self):
        placement = ElectricalNodePlacement(
            name='Site Placement',
            slug='site-placement',
            power_system=self.site_only_power_system,
            electrical_node=self.site_only_node,
            site=self.site,
            location=None,
            placement_scope_type=PlacementScopeChoices.SCOPE_SITE,
            x='15.00',
            y='25.00',
        )

        placement.full_clean()
