from rest_framework.routers import APIRootView
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import DjangoModelPermissions, IsAuthenticated
from django.shortcuts import get_object_or_404
from django.urls import NoReverseMatch
from django.utils import timezone
from netbox.context import current_request

from netbox.api.viewsets import NetBoxModelViewSet

from netbox_power_plant import filtersets
from netbox_power_plant.api import serializers
from netbox_power_plant.models import (
    BESSDetail,
    BuswaySectionDetail,
    CapacityReservation,
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    InstantiationArtifact,
    GeneratorDetail,
    InstantiationRun,
    InternalPowerBus,
    InternalPowerBusAttachment,
    PhysicalElement,
    PhysicalElementType,
    PhysicalObjectBinding,
    PhysicalSpace,
    PlantProvenance,
    PlantSourceDocument,
    PlantSourceLayer,
    PlantSourceSheet,
    PowerArchitectureTemplate,
    PowerDomain,
    PowerFinding,
    PowerSystem,
    PowerHandoffPoint,
    PowerValidationRun,
    RedundancyGroup,
    SpatialFrame,
    SpatialPlacement,
    TransformerDetail,
    UPSDetail,
)
from netbox_power_plant.choices import PowerFindingStatusChoices
from netbox_power_plant.services.capacity import build_node_capacity_path_rollup
from netbox_power_plant.services.impact import domain_lost, node_offline, segment_cut
from netbox_power_plant.services.neocloud_cockpit import build_neocloud_cockpit_workflow
from netbox_power_plant.services.templates import instantiate_template
from netbox_power_plant.services.validation_actions import run_validation_action

try:
    from netbox_power_plant.services.templates import apply_existing_instantiation_run
except ImportError:
    apply_existing_instantiation_run = None


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


class PowerValidationRunViewSet(NetBoxModelViewSet):
    queryset = PowerValidationRun.objects.select_related('power_system')
    serializer_class = serializers.PowerValidationRunSerializer
    filterset_class = filtersets.PowerValidationRunFilterSet

    def create(self, request, *args, **kwargs):
        del args, kwargs
        _require_perm(request.user, 'netbox_power_plant.add_powervalidationrun')
        serializer = serializers.ValidationRunActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = run_validation_action(
                serializer.validated_data['power_system'],
                serializer.validated_data['run_kind'],
                name=serializer.validated_data.get('name') or None,
            )
        except ValueError as exc:
            raise serializers.ValidationError({'run_kind': str(exc)}) from exc
        return Response({
            'meta': _response_metadata(request, serializer),
            'run': serializers.PowerValidationRunSerializer(result.run, context={'request': request}).data,
            'open_count': result.open_count,
            'resolved_count': result.resolved_count,
        }, status=201)


class PowerFindingViewSet(NetBoxModelViewSet):
    queryset = PowerFinding.objects.select_related('run', 'power_system', 'assigned_object_type', 'assigned_to')
    serializer_class = serializers.PowerFindingSerializer
    filterset_class = filtersets.PowerFindingFilterSet


class PowerArchitectureTemplateViewSet(NetBoxModelViewSet):
    queryset = PowerArchitectureTemplate.objects.all()
    serializer_class = serializers.PowerArchitectureTemplateSerializer
    filterset_class = filtersets.PowerArchitectureTemplateFilterSet


class InstantiationRunViewSet(NetBoxModelViewSet):
    queryset = InstantiationRun.objects.select_related('power_system', 'template')
    serializer_class = serializers.InstantiationRunSerializer
    filterset_class = filtersets.InstantiationRunFilterSet


class InstantiationArtifactViewSet(NetBoxModelViewSet):
    queryset = InstantiationArtifact.objects.select_related('run', 'run__power_system', 'run__template', 'object_type')
    serializer_class = serializers.InstantiationArtifactSerializer
    filterset_class = filtersets.InstantiationArtifactFilterSet


class PlantSourceDocumentViewSet(NetBoxModelViewSet):
    queryset = PlantSourceDocument.objects.select_related('site', 'location')
    serializer_class = serializers.PlantSourceDocumentSerializer


class PlantSourceSheetViewSet(NetBoxModelViewSet):
    queryset = PlantSourceSheet.objects.select_related('source_document', 'source_document__site', 'source_document__location')
    serializer_class = serializers.PlantSourceSheetSerializer


class PlantSourceLayerViewSet(NetBoxModelViewSet):
    queryset = PlantSourceLayer.objects.select_related(
        'source_sheet',
        'source_sheet__source_document',
        'source_sheet__source_document__site',
        'source_sheet__source_document__location',
    )
    serializer_class = serializers.PlantSourceLayerSerializer


class PlantProvenanceViewSet(NetBoxModelViewSet):
    queryset = PlantProvenance.objects.select_related(
        'assigned_object_type',
        'source_document',
        'source_sheet',
        'source_sheet__source_document',
        'source_layer',
        'source_layer__source_sheet',
        'source_layer__source_sheet__source_document',
    )
    serializer_class = serializers.PlantProvenanceSerializer


class PhysicalSpaceViewSet(NetBoxModelViewSet):
    queryset = PhysicalSpace.objects.select_related('site', 'location', 'spatial_frame', 'parent_space')
    serializer_class = serializers.PhysicalSpaceSerializer


class PhysicalElementTypeViewSet(NetBoxModelViewSet):
    queryset = PhysicalElementType.objects.all()
    serializer_class = serializers.PhysicalElementTypeSerializer


class PhysicalElementViewSet(NetBoxModelViewSet):
    queryset = PhysicalElement.objects.select_related('element_type', 'site', 'location', 'physical_space')
    serializer_class = serializers.PhysicalElementSerializer


class PhysicalObjectBindingViewSet(NetBoxModelViewSet):
    queryset = PhysicalObjectBinding.objects.select_related(
        'physical_element',
        'physical_element__element_type',
        'physical_element__site',
        'physical_element__location',
        'physical_element__physical_space',
        'spatial_placement',
        'spatial_placement__spatial_frame',
        'assigned_object_type',
    )
    serializer_class = serializers.PhysicalObjectBindingSerializer


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


class PowerHandoffPointViewSet(NetBoxModelViewSet):
    queryset = PowerHandoffPoint.objects.select_related(
        'power_system', 'electrical_node', 'electrical_terminal', 'power_port', 'power_port__device',
        'expected_redundancy_group'
    )
    serializer_class = serializers.PowerHandoffPointSerializer
    filterset_class = filtersets.PowerHandoffPointFilterSet


class CapacityReservationViewSet(NetBoxModelViewSet):
    queryset = CapacityReservation.objects.select_related(
        'node', 'node__power_system', 'node__site', 'tenant', 'rack'
    )
    serializer_class = serializers.CapacityReservationSerializer
    filterset_class = filtersets.CapacityReservationFilterSet


class ElectricalNodeDetailViewSet(viewsets.ModelViewSet):
    permission_classes = (IsAuthenticated, DjangoModelPermissions)


class UPSDetailViewSet(ElectricalNodeDetailViewSet):
    queryset = UPSDetail.objects.select_related('node', 'node__power_system', 'node__site')
    serializer_class = serializers.UPSDetailSerializer
    filterset_class = filtersets.UPSDetailFilterSet


class GeneratorDetailViewSet(ElectricalNodeDetailViewSet):
    queryset = GeneratorDetail.objects.select_related('node', 'node__power_system', 'node__site')
    serializer_class = serializers.GeneratorDetailSerializer
    filterset_class = filtersets.GeneratorDetailFilterSet


class TransformerDetailViewSet(ElectricalNodeDetailViewSet):
    queryset = TransformerDetail.objects.select_related('node', 'node__power_system', 'node__site')
    serializer_class = serializers.TransformerDetailSerializer
    filterset_class = filtersets.TransformerDetailFilterSet


class BESSDetailViewSet(ElectricalNodeDetailViewSet):
    queryset = BESSDetail.objects.select_related('node', 'node__power_system', 'node__site')
    serializer_class = serializers.BESSDetailSerializer
    filterset_class = filtersets.BESSDetailFilterSet


class BuswaySectionDetailViewSet(ElectricalNodeDetailViewSet):
    queryset = BuswaySectionDetail.objects.select_related(
        'node', 'node__power_system', 'node__site', 'busway_system'
    )
    serializer_class = serializers.BuswaySectionDetailSerializer
    filterset_class = filtersets.BuswaySectionDetailFilterSet


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


class SpatialFrameViewSet(NetBoxModelViewSet):
    queryset = SpatialFrame.objects.select_related('site', 'location', 'parent_frame')
    serializer_class = serializers.SpatialFrameSerializer
    filterset_class = filtersets.SpatialFrameFilterSet


class SpatialPlacementViewSet(NetBoxModelViewSet):
    queryset = SpatialPlacement.objects.select_related('spatial_frame', 'spatial_frame__site', 'spatial_frame__location', 'assigned_object_type')
    serializer_class = serializers.SpatialPlacementSerializer
    filterset_class = filtersets.SpatialPlacementFilterSet


class ElectricalNodePlacementViewSet(NetBoxModelViewSet):
    queryset = ElectricalNodePlacement.objects.select_related('power_system', 'electrical_node', 'site', 'location')
    serializer_class = serializers.ElectricalNodePlacementSerializer
    filterset_class = filtersets.ElectricalNodePlacementFilterSet


class OperationalAPIView(APIView):
    permission_classes = (IsAuthenticated,)


class InstantiationRunCreateAPIView(OperationalAPIView):
    queryset = InstantiationRun.objects.all()

    def get(self, request):
        _require_perm(request.user, 'netbox_power_plant.view_instantiationrun')
        runs = InstantiationRun.objects.select_related('power_system', 'template').order_by('-created', 'name')[:100]
        return Response({
            'count': len(runs),
            'results': serializers.InstantiationRunSerializer(runs, many=True, context={'request': request}).data,
        })

    def post(self, request):
        _require_perm(request.user, 'netbox_power_plant.add_instantiationrun')
        serializer = serializers.InstantiationRunActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = _without_change_logging(
            instantiate_template,
            serializer.validated_data['power_system'],
            serializer.validated_data['template'],
            context=serializer.validated_data.get('context') or {},
            apply=serializer.validated_data.get('apply', False),
        )
        return Response(_instantiation_result_payload(result, meta=_response_metadata(request, serializer)), status=201)


class InstantiationRunDetailAPIView(OperationalAPIView):
    queryset = InstantiationRun.objects.all()

    def get(self, request, pk):
        _require_perm(request.user, 'netbox_power_plant.view_instantiationrun')
        run = get_object_or_404(
            InstantiationRun.objects.select_related('power_system', 'template'),
            pk=pk,
        )
        return Response(serializers.InstantiationRunSerializer(run, context={'request': request}).data)


class InstantiationRunApplyAPIView(OperationalAPIView):
    queryset = InstantiationRun.objects.all()

    def post(self, request, pk):
        _require_perm(request.user, 'netbox_power_plant.change_instantiationrun')
        run = get_object_or_404(
            InstantiationRun.objects.select_related('power_system', 'template'),
            pk=pk,
        )
        serializer = serializers.InstantiationRunApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        context = serializer.validated_data.get('context')
        if apply_existing_instantiation_run is not None and context is None:
            result = _without_change_logging(apply_existing_instantiation_run, run)
        else:
            result = _without_change_logging(
                instantiate_template,
                run.power_system,
                run.template,
                context=run.context if context is None else context,
                apply=True,
            )
        return Response(_instantiation_result_payload(result, meta=_response_metadata(request, serializer)), status=200)


class ValidationRunCreateAPIView(OperationalAPIView):
    queryset = PowerValidationRun.objects.all()

    def post(self, request):
        _require_perm(request.user, 'netbox_power_plant.add_powervalidationrun')
        serializer = serializers.ValidationRunActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = run_validation_action(
                serializer.validated_data['power_system'],
                serializer.validated_data['run_kind'],
                name=serializer.validated_data.get('name') or None,
            )
        except ValueError as exc:
            raise serializers.ValidationError({'run_kind': str(exc)}) from exc
        return Response({
            'meta': _response_metadata(request, serializer),
            'run': serializers.PowerValidationRunSerializer(result.run, context={'request': request}).data,
            'open_count': result.open_count,
            'resolved_count': result.resolved_count,
        }, status=201)


class PowerFindingAcknowledgeAPIView(OperationalAPIView):
    queryset = PowerFinding.objects.all()

    def post(self, request, pk):
        finding = _finding_for_action(request, pk)
        serializer = serializers.FindingAcknowledgeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        details = dict(finding.details or {})
        details['acknowledged_at'] = timezone.now().isoformat()
        details['acknowledged_by'] = request.user.username
        note = serializer.validated_data.get('note')
        if note:
            details['acknowledgement_note'] = note
        finding.details = details
        finding.save(update_fields=('details',))
        return Response(serializers.PowerFindingSerializer(finding, context={'request': request}).data)


class PowerFindingSuppressAPIView(OperationalAPIView):
    queryset = PowerFinding.objects.all()

    def post(self, request, pk):
        finding = _finding_for_action(request, pk)
        serializer = serializers.FindingSuppressActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        details = dict(finding.details or {})
        reason = serializer.validated_data.get('reason')
        if reason:
            details['suppression_reason'] = reason
        finding.details = details
        finding.status = PowerFindingStatusChoices.STATUS_SUPPRESSED
        finding.suppressed_until = serializer.validated_data.get('suppressed_until')
        finding.save(update_fields=('details', 'status', 'suppressed_until'))
        return Response(serializers.PowerFindingSerializer(finding, context={'request': request}).data)


class PowerFindingResolveAPIView(OperationalAPIView):
    queryset = PowerFinding.objects.all()

    def post(self, request, pk):
        finding = _finding_for_action(request, pk)
        serializer = serializers.FindingResolveActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        details = dict(finding.details or {})
        reason = serializer.validated_data.get('reason')
        if reason:
            details['resolution_reason'] = reason
        finding.details = details
        finding.status = PowerFindingStatusChoices.STATUS_RESOLVED
        finding.resolved_at = timezone.now()
        finding.save(update_fields=('details', 'status', 'resolved_at'))
        return Response(serializers.PowerFindingSerializer(finding, context={'request': request}).data)


class CapacityRollupAPIView(OperationalAPIView):
    queryset = ElectricalNode.objects.all()

    def get(self, request):
        _require_perm(request.user, 'netbox_power_plant.view_electricalnode')
        serializer = serializers.CapacityRollupQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        node = get_object_or_404(
            ElectricalNode.objects.select_related('power_system', 'site', 'location', 'parent_node'),
            pk=serializer.validated_data['node_id'],
        )
        rollup = build_node_capacity_path_rollup(node)
        return Response({
            'power_system': _object_ref(node.power_system),
            'node': _object_ref(node),
            'available_kw': rollup.available_kw,
            'system_summary': rollup.system_summary,
            'first_bottleneck': _capacity_hop_payload(rollup.first_bottleneck),
            'hops': tuple(_capacity_hop_payload(hop) for hop in rollup.hops),
        })


class ImpactNodeOfflineAPIView(OperationalAPIView):
    queryset = ElectricalNode.objects.all()

    def post(self, request):
        _require_perm(request.user, 'netbox_power_plant.view_electricalnode')
        serializer = serializers.ImpactNodeOfflineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(node_offline(serializer.validated_data['power_system'], serializer.validated_data['node']))


class ImpactSegmentCutAPIView(OperationalAPIView):
    queryset = ElectricalSegment.objects.all()

    def post(self, request):
        _require_perm(request.user, 'netbox_power_plant.view_electricalsegment')
        serializer = serializers.ImpactSegmentCutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(segment_cut(serializer.validated_data['power_system'], serializer.validated_data['segment']))


class ImpactDomainLostAPIView(OperationalAPIView):
    queryset = PowerDomain.objects.all()

    def post(self, request):
        _require_perm(request.user, 'netbox_power_plant.view_powerdomain')
        serializer = serializers.ImpactDomainLostSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(domain_lost(serializer.validated_data['power_system'], serializer.validated_data['domain']))


class NeocloudCockpitAPIView(OperationalAPIView):
    queryset = PowerSystem.objects.all()

    def post(self, request):
        _require_perm(request.user, 'netbox_power_plant.view_powersystem')
        serializer = serializers.NeocloudCockpitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scenario_type = serializer.validated_data['scenario_type']
        if scenario_type == 'node_offline':
            _require_perm(request.user, 'netbox_power_plant.view_electricalnode')
        elif scenario_type == 'segment_cut':
            _require_perm(request.user, 'netbox_power_plant.view_electricalsegment')
        elif scenario_type == 'domain_lost':
            _require_perm(request.user, 'netbox_power_plant.view_powerdomain')
        else:
            raise serializers.ValidationError({'scenario_type': 'Unsupported neocloud cockpit scenario.'})

        return Response(build_neocloud_cockpit_workflow(
            serializer.validated_data['power_system'],
            scenario_type=scenario_type,
            target_id=serializer.validated_data['target_id'],
        ))


def _require_perm(user, permission):
    if not user.has_perm(permission):
        raise PermissionDenied()


def _without_change_logging(func, *args, **kwargs):
    token = current_request.set(None)
    try:
        return func(*args, **kwargs)
    finally:
        current_request.reset(token)


def _response_metadata(request, serializer=None):
    request_id = (
        (serializer.validated_data.get('request_id') if serializer is not None else None)
        or request.headers.get('Idempotency-Key')
        or request.headers.get('X-Request-ID')
        or ''
    )
    return {
        'request_id': request_id,
        'idempotency_persisted': False,
        'idempotency_note': 'Request IDs are echoed for automation correlation; no durable de-duplication store is configured.',
    }


def _finding_for_action(request, pk):
    _require_perm(request.user, 'netbox_power_plant.change_powerfinding')
    return get_object_or_404(
        PowerFinding.objects.select_related('run', 'power_system', 'assigned_object_type', 'assigned_to'),
        pk=pk,
    )


def _instantiation_result_payload(result, *, meta=None):
    payload = {
        'run': _instantiation_run_ref(result.run),
        'created_count': result.created_count,
        'updated_count': result.updated_count,
        'artifact_count': len(result.artifacts),
        'artifacts': tuple(_artifact_payload(artifact) for artifact in result.artifacts),
    }
    if meta is not None:
        payload['meta'] = meta
    return payload


def _instantiation_run_ref(run):
    return {
        'id': run.pk,
        'display': str(run),
        'name': run.name,
        'slug': run.slug,
        'status': run.status,
        'dry_run': run.dry_run,
        'artifact_count': run.artifact_count,
        'power_system': _object_ref(run.power_system),
        'template': _object_ref(run.template),
    }


def _artifact_payload(artifact):
    return {
        'artifact_type': artifact.artifact_type,
        'action': artifact.action,
        'status': artifact.status,
        'template_key': artifact.template_key,
        'stable_slug': artifact.stable_slug,
        'object': _object_ref(artifact.object),
        'proposed_data': artifact.proposed_data,
    }


def _capacity_hop_payload(hop):
    if hop is None:
        return None
    return {
        'hop_index': hop.hop_index,
        'node': _object_ref(hop.node),
        'segment': _object_ref(hop.segment),
        'capacity_kw': hop.capacity_kw,
        'derated_capacity_kw': hop.derated_capacity_kw,
        'reserve_margin_kw': hop.reserve_margin_kw,
        'direct_load_kw': hop.direct_load_kw,
        'descendant_load_kw': hop.descendant_load_kw,
        'total_load_kw': hop.total_load_kw,
        'reserved_kw': hop.reserved_kw,
        'total_reserved_kw': hop.total_reserved_kw,
        'node_available_kw': hop.node_available_kw,
        'segment_capacity_kw': hop.segment_capacity_kw,
        'segment_load_kw': hop.segment_load_kw,
        'segment_available_kw': hop.segment_available_kw,
        'available_kw': hop.available_kw,
        'bottleneck_type': hop.bottleneck_type,
        'reservation_breakdown': hop.reservation_breakdown,
        'load_breakdown': hop.load_breakdown,
    }


def _object_ref(obj):
    if obj is None:
        return None
    url = None
    if hasattr(obj, 'get_absolute_url'):
        try:
            url = obj.get_absolute_url()
        except NoReverseMatch:
            url = None
    return {
        'id': obj.pk,
        'display': str(obj),
        'name': getattr(obj, 'name', str(obj)),
        'url': url,
    }
