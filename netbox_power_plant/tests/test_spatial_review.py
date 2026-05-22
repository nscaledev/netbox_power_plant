from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from dcim.models import Location, Site

from netbox_power_plant.choices import (
    NodeKindChoices,
    PhysicalElementKindChoices,
    PhysicalObjectBindingRoleChoices,
    PhysicalSpaceKindChoices,
    PlantDisciplineChoices,
    SpatialAnchorChoices,
    SpatialConfidenceChoices,
)
from netbox_power_plant.models import (
    ElectricalNode,
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PowerSystem,
    SpatialFrame,
    SpatialPlacement,
)
from netbox_power_plant.services.spatial_review import (
    STATUS_APPROVED,
    STATUS_OPERATOR_CORRECTED,
    STATUS_OPERATOR_REVIEW_REQUIRED,
    STATUS_UNKNOWN,
    build_spatial_review_map,
)


class SpatialReviewMapTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = Site.objects.create(name='Madison', slug='madison')
        cls.empty_site = Site.objects.create(name='Empty Site', slug='empty-site')
        cls.location = Location.objects.create(site=cls.site, name='First Floor', slug='first-floor')
        cls.frame = SpatialFrame.objects.create(
            name='MAD1 First Floor',
            slug='mad1-first-floor',
            site=cls.site,
            location=cls.location,
            width='200.000',
            height='100.000',
            units='mad1_svg_unit',
        )
        cls.building = PhysicalSpace.objects.create(
            name='Current Building',
            slug='current-building',
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.frame,
            space_kind=PhysicalSpaceKindChoices.KIND_BUILDING,
            boundary_geometry={'x': '0.000', 'y': '0.000', 'width': '200.000', 'depth': '100.000'},
            metadata={'review_state': 'approved', 'boundary_status': 'approved'},
            confidence=SpatialConfidenceChoices.CONFIDENCE_AUTHORITATIVE,
        )
        cls.floor = PhysicalSpace.objects.create(
            name='First Floor',
            slug='first-floor-space',
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.frame,
            parent_space=cls.building,
            space_kind=PhysicalSpaceKindChoices.KIND_FLOOR,
            floor_label='1',
            boundary_geometry={'x': '10.000', 'y': '10.000', 'width': '180.000', 'depth': '80.000'},
            metadata={'review_state': 'approved', 'boundary_status': 'approved'},
            confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
        )
        cls.data_hall = PhysicalSpace.objects.create(
            name='Data Hall 1A',
            slug='data-hall-1a',
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.frame,
            parent_space=cls.floor,
            space_kind=PhysicalSpaceKindChoices.KIND_DATA_HALL,
            floor_label='1',
            boundary_geometry={
                'x': '20.000',
                'y': '30.000',
                'width': '50.000',
                'depth': '20.000',
                'coordinate_source': 'madison_cad_detailed_space_decomposition',
            },
            metadata={
                'review_state': 'operator_review_required',
                'boundary_status': 'operator_review_required',
                'provenance_url': '/plugins/power-plant/provenance/1/',
            },
            confidence=SpatialConfidenceChoices.CONFIDENCE_PROVISIONAL,
        )
        cls.unknown_space = PhysicalSpace.objects.create(
            name='Unclassified Room',
            slug='unclassified-room',
            site=cls.site,
            location=cls.location,
            spatial_frame=cls.frame,
            parent_space=cls.floor,
            space_kind=PhysicalSpaceKindChoices.KIND_ROOM,
            boundary_geometry={'x': '80.000', 'y': '30.000', 'width': '20.000', 'depth': '10.000'},
            metadata={},
        )
        cls.element_type = PhysicalElementType.objects.create(
            name='Rack Footprint',
            slug='rack-footprint',
            discipline=PlantDisciplineChoices.DISCIPLINE_RACK_LAYOUT,
            element_kind=PhysicalElementKindChoices.KIND_RACK_FOOTPRINT,
        )
        cls.element = PhysicalElement.objects.create(
            name='Rack A01 Footprint',
            slug='rack-a01-footprint',
            label='Rack A01',
            element_type=cls.element_type,
            site=cls.site,
            location=cls.location,
            physical_space=cls.data_hall,
            confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
        )
        cls.power_system = PowerSystem.objects.create(
            name='Madison Power',
            slug='madison-power',
            site=cls.site,
            location=cls.location,
        )
        cls.node = ElectricalNode.objects.create(
            name='PDU A',
            slug='pdu-a',
            power_system=cls.power_system,
            site=cls.site,
            location=cls.location,
            node_kind=NodeKindChoices.KIND_PDU,
        )
        cls.placement = SpatialPlacement.objects.create(
            name='Rack A01 Placement',
            slug='rack-a01-placement',
            spatial_frame=cls.frame,
            assigned_object_type=ContentType.objects.get_for_model(PhysicalElement),
            assigned_object_id=cls.element.pk,
            x='40.000',
            y='35.000',
            width='4.000',
            depth='2.000',
            anchor=SpatialAnchorChoices.ANCHOR_LOWER_LEFT,
            confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
        )
        cls.binding = PhysicalObjectBinding.objects.create(
            name='PDU A Binding',
            slug='pdu-a-binding',
            physical_element=cls.element,
            spatial_placement=cls.placement,
            assigned_object_type=ContentType.objects.get_for_model(ElectricalNode),
            assigned_object_id=cls.node.pk,
            binding_role=PhysicalObjectBindingRoleChoices.ROLE_TOPOLOGY_NODE_FOR,
            confidence=SpatialConfidenceChoices.CONFIDENCE_DERIVED,
            is_primary=True,
        )

    def test_builds_canvas_ready_space_primitives_with_y_up_model_coordinates(self):
        review_map = build_spatial_review_map('madison', frame='mad1-first-floor')

        self.assertTrue(review_map.is_available)
        self.assertEqual(review_map.width, 200)
        self.assertEqual(review_map.height, 100)
        self.assertEqual(review_map.view_box, '0 0 200 100')
        self.assertEqual(review_map.unit_label, 'mad1_svg_unit')

        data_hall = next(space for space in review_map.spaces if space.label == 'Data Hall 1A')
        self.assertEqual(data_hall.x, 20)
        self.assertEqual(data_hall.y, 30)
        self.assertEqual(data_hall.width, 50)
        self.assertEqual(data_hall.depth, 20)
        self.assertEqual(data_hall.status, STATUS_OPERATOR_REVIEW_REQUIRED)
        self.assertEqual(data_hall.status_label, 'Needs review')
        self.assertEqual(data_hall.status_class, 'operator-review-required')
        self.assertEqual(data_hall.kind_label, 'Data hall')
        self.assertEqual(data_hall.provenance_url, '/plugins/power-plant/provenance/1/')
        self.assertEqual(data_hall.coordinate_source, 'madison_cad_detailed_space_decomposition')
        self.assertEqual(review_map.spaces[0].label, 'Current Building')
        self.assertEqual(review_map.spaces[-1].label, 'Unclassified Room')

    def test_marks_operator_corrected_spaces_as_distinct_review_targets(self):
        self.data_hall.metadata = {
            **self.data_hall.metadata,
            'geometry_review_state': 'operator_corrected',
            'geometry_review_method': 'visual_spatial_review',
        }
        self.data_hall.save()

        review_map = build_spatial_review_map(self.site, frame=self.frame)
        data_hall = next(space for space in review_map.spaces if space.label == 'Data Hall 1A')

        self.assertEqual(data_hall.status, STATUS_OPERATOR_CORRECTED)
        self.assertEqual(data_hall.status_label, 'Corrected, needs approval')
        self.assertEqual(data_hall.status_class, 'operator-corrected')
        self.assertEqual(data_hall.geometry_review_state, 'operator_corrected')
        self.assertEqual(review_map.status_counts[STATUS_OPERATOR_CORRECTED], 1)
        self.assertEqual(review_map.status_counts[STATUS_OPERATOR_REVIEW_REQUIRED], 0)

    def test_reports_status_counts_labels_placements_and_bindings(self):
        review_map = build_spatial_review_map(self.site, frame=self.frame)

        self.assertEqual(review_map.status_counts[STATUS_APPROVED], 2)
        self.assertEqual(review_map.status_counts[STATUS_OPERATOR_REVIEW_REQUIRED], 1)
        self.assertEqual(review_map.status_counts[STATUS_UNKNOWN], 1)

        self.assertEqual(len(review_map.placements), 1)
        placement = review_map.placements[0]
        self.assertEqual(placement.label, 'Rack A01 Placement')
        self.assertEqual(placement.object_label, 'Rack A01')
        self.assertEqual(placement.shape, 'rect')
        self.assertEqual(placement.geometry_x, 40)
        self.assertEqual(placement.geometry_y, 35)
        self.assertEqual(placement.width, 4)
        self.assertEqual(placement.depth, 2)

        self.assertEqual(len(review_map.bindings), 1)
        self.assertEqual(review_map.binding_counts['total'], 1)
        self.assertEqual(review_map.binding_counts['primary'], 1)
        self.assertEqual(review_map.binding_counts[PhysicalObjectBindingRoleChoices.ROLE_TOPOLOGY_NODE_FOR], 1)
        self.assertEqual(review_map.elements[0].binding_count, 1)
        self.assertEqual(review_map.elements[0].primary_binding_label, 'PDU A')

    def test_can_filter_unreviewed_boundaries(self):
        review_map = build_spatial_review_map(self.site, frame=self.frame, include_unreviewed=False)

        self.assertEqual({space.label for space in review_map.spaces}, {'Current Building', 'First Floor'})
        self.assertEqual(review_map.status_counts[STATUS_APPROVED], 2)
        self.assertEqual(review_map.status_counts[STATUS_OPERATOR_REVIEW_REQUIRED], 0)
        self.assertEqual(review_map.status_counts[STATUS_UNKNOWN], 0)

    def test_no_data_map_is_not_available(self):
        review_map = build_spatial_review_map('empty-site')

        self.assertFalse(review_map.is_available)
        self.assertEqual(review_map.width, 0)
        self.assertEqual(review_map.height, 0)
        self.assertEqual(review_map.view_box, '0 0 0 0')
        self.assertEqual(review_map.spaces, ())
        self.assertEqual(review_map.elements, ())
        self.assertEqual(review_map.placements, ())
        self.assertEqual(review_map.bindings, ())
        self.assertEqual(review_map.status_counts[STATUS_APPROVED], 0)
        self.assertIn('Spatial frame', review_map.available_reason)
