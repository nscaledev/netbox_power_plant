from netbox.api.routers import NetBoxRouter

from .views import (
	ElectricalNodeViewSet,
	ElectricalNodePlacementViewSet,
	ElectricalSegmentViewSet,
	ElectricalTerminalViewSet,
	InternalPowerBusAttachmentViewSet,
	InternalPowerBusViewSet,
	PowerDomainViewSet,
	PowerSystemViewSet,
	RackDeliveryPointViewSet,
	RedundancyGroupViewSet,
	RootView,
)


app_name = 'netbox_power_plant'

router = NetBoxRouter()
router.APIRootView = RootView
router.register('power-systems', PowerSystemViewSet, basename='powersystem')
router.register('power-domains', PowerDomainViewSet, basename='powerdomain')
router.register('redundancy-groups', RedundancyGroupViewSet, basename='redundancygroup')
router.register('electrical-nodes', ElectricalNodeViewSet, basename='electricalnode')
router.register('electrical-terminals', ElectricalTerminalViewSet, basename='electricalterminal')
router.register('electrical-segments', ElectricalSegmentViewSet, basename='electricalsegment')
router.register('rack-delivery-points', RackDeliveryPointViewSet, basename='rackdeliverypoint')
router.register('internal-power-buses', InternalPowerBusViewSet, basename='internalpowerbus')
router.register(
    'internal-power-bus-attachments',
    InternalPowerBusAttachmentViewSet,
    basename='internalpowerbusattachment',
)
router.register('electrical-node-placements', ElectricalNodePlacementViewSet, basename='electricalnodeplacement')

urlpatterns = router.urls
