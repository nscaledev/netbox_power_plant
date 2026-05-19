from rest_framework.routers import APIRootView

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_power_plant import filtersets
from netbox_power_plant.api import serializers
from netbox_power_plant.models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    InternalPowerBus,
    InternalPowerBusAttachment,
    PowerDomain,
    PowerSystem,
    RackDeliveryPoint,
    RedundancyGroup,
)


class RootView(APIRootView):
    def get_view_name(self):
        return 'power-plant'


class PowerSystemViewSet(NetBoxModelViewSet):
    queryset = PowerSystem.objects.all()
    serializer_class = serializers.PowerSystemSerializer
    filterset_class = filtersets.PowerSystemFilterSet


class PowerDomainViewSet(NetBoxModelViewSet):
    queryset = PowerDomain.objects.all()
    serializer_class = serializers.PowerDomainSerializer
    filterset_class = filtersets.PowerDomainFilterSet


class RedundancyGroupViewSet(NetBoxModelViewSet):
    queryset = RedundancyGroup.objects.all()
    serializer_class = serializers.RedundancyGroupSerializer
    filterset_class = filtersets.RedundancyGroupFilterSet


class ElectricalNodeViewSet(NetBoxModelViewSet):
    queryset = ElectricalNode.objects.select_related('power_system', 'site', 'location', 'parent_node')
    serializer_class = serializers.ElectricalNodeSerializer
    filterset_class = filtersets.ElectricalNodeFilterSet


class ElectricalTerminalViewSet(NetBoxModelViewSet):
    queryset = ElectricalTerminal.objects.select_related('node', 'node__power_system')
    serializer_class = serializers.ElectricalTerminalSerializer
    filterset_class = filtersets.ElectricalTerminalFilterSet


class ElectricalSegmentViewSet(NetBoxModelViewSet):
    queryset = ElectricalSegment.objects.select_related('power_system', 'power_domain', 'from_terminal__node', 'to_terminal__node')
    serializer_class = serializers.ElectricalSegmentSerializer
    filterset_class = filtersets.ElectricalSegmentFilterSet


class RackDeliveryPointViewSet(NetBoxModelViewSet):
    queryset = RackDeliveryPoint.objects.select_related(
        'power_system', 'electrical_node', 'electrical_terminal', 'rack', 'device', 'power_port', 'power_port__device',
        'expected_redundancy_group'
    )
    serializer_class = serializers.RackDeliveryPointSerializer
    filterset_class = filtersets.RackDeliveryPointFilterSet


class InternalPowerBusViewSet(NetBoxModelViewSet):
    queryset = InternalPowerBus.objects.select_related('power_system', 'rack')
    serializer_class = serializers.InternalPowerBusSerializer
    filterset_class = filtersets.InternalPowerBusFilterSet


class InternalPowerBusAttachmentViewSet(NetBoxModelViewSet):
    queryset = InternalPowerBusAttachment.objects.select_related(
        'internal_power_bus', 'internal_power_bus__power_system', 'internal_power_bus__rack',
        'power_port', 'power_port__device'
    )
    serializer_class = serializers.InternalPowerBusAttachmentSerializer
    filterset_class = filtersets.InternalPowerBusAttachmentFilterSet


class ElectricalNodePlacementViewSet(NetBoxModelViewSet):
    queryset = ElectricalNodePlacement.objects.select_related('power_system', 'electrical_node', 'site', 'location')
    serializer_class = serializers.ElectricalNodePlacementSerializer
    filterset_class = filtersets.ElectricalNodePlacementFilterSet
