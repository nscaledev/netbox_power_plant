from netbox.api.routers import NetBoxRouter
from django.urls import path

from .views import (
	BESSDetailViewSet,
	BuswaySectionDetailViewSet,
	CapacityReservationViewSet,
	CapacityRollupAPIView,
	ElectricalNodeViewSet,
	ElectricalNodePlacementViewSet,
	ElectricalSegmentViewSet,
	ElectricalTerminalViewSet,
	GeneratorDetailViewSet,
	ImpactDomainLostAPIView,
	ImpactNodeOfflineAPIView,
	ImpactSegmentCutAPIView,
	InstantiationArtifactViewSet,
	InstantiationRunApplyAPIView,
	InstantiationRunCreateAPIView,
	InstantiationRunDetailAPIView,
	InternalPowerBusAttachmentViewSet,
	InternalPowerBusViewSet,
	NeocloudCockpitAPIView,
	PhysicalElementTypeViewSet,
	PhysicalElementViewSet,
	PhysicalObjectBindingViewSet,
	PhysicalSpaceViewSet,
	PlantProvenanceViewSet,
	PlantSourceDocumentViewSet,
	PlantSourceLayerViewSet,
	PlantSourceSheetViewSet,
	PowerDomainViewSet,
	PowerFindingAcknowledgeAPIView,
	PowerFindingResolveAPIView,
	PowerFindingSuppressAPIView,
	PowerFindingViewSet,
	PowerArchitectureTemplateViewSet,
	PowerSystemViewSet,
	PowerHandoffPointViewSet,
	PowerValidationRunViewSet,
	RedundancyGroupViewSet,
	RootView,
	SpatialFrameViewSet,
	SpatialPlacementViewSet,
	TransformerDetailViewSet,
	UPSDetailViewSet,
)


app_name = 'netbox_power_plant'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('power-systems', PowerSystemViewSet, basename='powersystem')
router.register('power-domains', PowerDomainViewSet, basename='powerdomain')
router.register('validation-runs', PowerValidationRunViewSet, basename='powervalidationrun')
router.register('findings', PowerFindingViewSet, basename='powerfinding')
router.register('architecture-templates', PowerArchitectureTemplateViewSet, basename='powerarchitecturetemplate')
router.register('instantiation-artifacts', InstantiationArtifactViewSet, basename='instantiationartifact')
router.register('plant-source-documents', PlantSourceDocumentViewSet, basename='plantsourcedocument')
router.register('plant-source-sheets', PlantSourceSheetViewSet, basename='plantsourcesheet')
router.register('plant-source-layers', PlantSourceLayerViewSet, basename='plantsourcelayer')
router.register('plant-provenance-records', PlantProvenanceViewSet, basename='plantprovenance')
router.register('physical-spaces', PhysicalSpaceViewSet, basename='physicalspace')
router.register('physical-element-types', PhysicalElementTypeViewSet, basename='physicalelementtype')
router.register('physical-elements', PhysicalElementViewSet, basename='physicalelement')
router.register('physical-object-bindings', PhysicalObjectBindingViewSet, basename='physicalobjectbinding')
router.register('redundancy-groups', RedundancyGroupViewSet, basename='redundancygroup')
router.register('electrical-nodes', ElectricalNodeViewSet, basename='electricalnode')
router.register('electrical-terminals', ElectricalTerminalViewSet, basename='electricalterminal')
router.register('electrical-segments', ElectricalSegmentViewSet, basename='electricalsegment')
router.register('power-handoff-points', PowerHandoffPointViewSet, basename='powerhandoffpoint')
router.register('capacity-reservations', CapacityReservationViewSet, basename='capacityreservation')
router.register('ups-details', UPSDetailViewSet, basename='upsdetail')
router.register('generator-details', GeneratorDetailViewSet, basename='generatordetail')
router.register('transformer-details', TransformerDetailViewSet, basename='transformerdetail')
router.register('bess-details', BESSDetailViewSet, basename='bessdetail')
router.register('busway-section-details', BuswaySectionDetailViewSet, basename='buswaysectiondetail')
router.register('internal-power-buses', InternalPowerBusViewSet, basename='internalpowerbus')
router.register(
    'internal-power-bus-attachments',
    InternalPowerBusAttachmentViewSet,
    basename='internalpowerbusattachment',
)
router.register('spatial-frames', SpatialFrameViewSet, basename='spatialframe')
router.register('spatial-placements', SpatialPlacementViewSet, basename='spatialplacement')
router.register('electrical-node-placements', ElectricalNodePlacementViewSet, basename='electricalnodeplacement')

urlpatterns = [
    path('instantiation-runs/', InstantiationRunCreateAPIView.as_view(), name='instantiationrun-list'),
    path('instantiation-runs/<int:pk>/', InstantiationRunDetailAPIView.as_view(), name='instantiationrun-detail'),
    path('instantiation-runs/<int:pk>/apply/', InstantiationRunApplyAPIView.as_view(), name='instantiationrun-apply'),
    path('power-findings/<int:pk>/acknowledge/', PowerFindingAcknowledgeAPIView.as_view(), name='powerfinding-acknowledge'),
    path('power-findings/<int:pk>/suppress/', PowerFindingSuppressAPIView.as_view(), name='powerfinding-suppress'),
    path('power-findings/<int:pk>/resolve/', PowerFindingResolveAPIView.as_view(), name='powerfinding-resolve'),
    path('capacity/rollup/', CapacityRollupAPIView.as_view(), name='capacity-rollup'),
    path('impact/node-offline/', ImpactNodeOfflineAPIView.as_view(), name='impact-node-offline'),
    path('impact/segment-cut/', ImpactSegmentCutAPIView.as_view(), name='impact-segment-cut'),
    path('impact/domain-lost/', ImpactDomainLostAPIView.as_view(), name='impact-domain-lost'),
    path('neocloud/cockpit/', NeocloudCockpitAPIView.as_view(), name='neocloud-cockpit'),
] + router.urls
