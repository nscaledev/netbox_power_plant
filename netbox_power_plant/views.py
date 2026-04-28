from types import SimpleNamespace
from django.views.generic import TemplateView
from django_tables2 import RequestConfig

from netbox.views import generic

from . import filtersets, forms, tables
from .models import (
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    PowerDomain,
    PowerSystem,
    RackDeliveryPoint,
    RedundancyGroup,
)
from .services.layout import build_power_system_layout_view
from .services.layout_validation import build_layout_health_summary
from .services.rack_delivery import build_rack_delivery_summary
from .services.workflow_urls import (
    build_delivery_add_url,
    build_delivery_edit_url,
    build_layout_url,
    build_placement_edit_url,
    build_rack_delivery_url,
    build_workflow_urls,
)


class HomeView(TemplateView):
    template_name = 'netbox_power_plant/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        systems = PowerSystem.objects.prefetch_related('power_domains', 'redundancy_groups').order_by('site__name', 'name')[:10]
        systems_table = tables.PowerSystemSummaryTable(systems)
        systems_table.configure(self.request)
        context.update({
            'power_system_count': PowerSystem.objects.count(),
            'power_domain_count': PowerDomain.objects.count(),
            'redundancy_group_count': RedundancyGroup.objects.count(),
            'systems': systems,
            'systems_table': systems_table,
        })
        return context


class PowerSystemListView(generic.ObjectListView):
    queryset = PowerSystem.objects.all()
    filterset = filtersets.PowerSystemFilterSet
    filterset_form = forms.PowerSystemFilterForm
    table = tables.PowerSystemTable


class PowerSystemView(generic.ObjectView):
    queryset = PowerSystem.objects.all()
    template_name = 'netbox_power_plant/powersystem.html'

    def get_extra_context(self, request, instance):
        layout_url = build_layout_url(instance)
        rack_delivery_url = build_rack_delivery_url(instance)
        workflow_urls = build_workflow_urls(
            instance,
            placement_return_url=layout_url,
            delivery_return_url=rack_delivery_url,
        )
        if not request.user.has_perm('netbox_power_plant.add_electricalnodeplacement'):
            workflow_urls['placement_add'] = None
        if not request.user.has_perm('netbox_power_plant.add_rackdeliverypoint'):
            workflow_urls['delivery_add'] = None
        return {
            'layout_health': build_layout_health_summary(instance),
            'workflow_urls': workflow_urls,
        }


class PowerSystemRackDeliveryView(generic.ObjectView):
    queryset = PowerSystem.objects.prefetch_related('power_domains', 'redundancy_groups__power_domains')
    template_name = 'netbox_power_plant/powersystem_rack_delivery.html'

    def get_extra_context(self, request, instance):
        return_url = request.get_full_path()
        can_add_placement = request.user.has_perm('netbox_power_plant.add_electricalnodeplacement')
        can_add_delivery = request.user.has_perm('netbox_power_plant.add_rackdeliverypoint')
        can_edit_delivery = request.user.has_perm('netbox_power_plant.change_rackdeliverypoint')
        workflow_urls = build_workflow_urls(
            instance,
            placement_return_url=return_url,
            delivery_return_url=return_url,
        )
        if not can_add_placement:
            workflow_urls['placement_add'] = None
        if not can_add_delivery:
            workflow_urls['delivery_add'] = None
        delivery_summary = build_rack_delivery_summary(instance)
        delivery_table = tables.RackDeliverySummaryTable(
            delivery_summary.rows,
            power_system=instance,
            return_url=return_url,
            can_add_delivery=can_add_delivery,
            can_edit_delivery=can_edit_delivery,
        )
        RequestConfig(request).configure(delivery_table)
        return {
            'delivery_summary': delivery_summary,
            'delivery_table': delivery_table,
            'workflow_urls': workflow_urls,
        }


class PowerSystemLayoutView(generic.ObjectView):
    queryset = PowerSystem.objects.prefetch_related(
        'power_domains',
        'redundancy_groups__power_domains',
        'rack_delivery_points',
        'electrical_node_placements',
    )
    template_name = 'netbox_power_plant/powersystem_layout.html'

    def get_extra_context(self, request, instance):
        return_url = request.get_full_path()
        layout = build_power_system_layout_view(instance)
        can_add_placement = request.user.has_perm('netbox_power_plant.add_electricalnodeplacement')
        can_add_delivery = request.user.has_perm('netbox_power_plant.add_rackdeliverypoint')
        can_edit_placement = request.user.has_perm('netbox_power_plant.change_electricalnodeplacement')
        can_edit_delivery = request.user.has_perm('netbox_power_plant.change_rackdeliverypoint')
        workflow_urls = build_workflow_urls(
            instance,
            placement_return_url=return_url,
            delivery_return_url=return_url,
        )
        if not can_add_placement:
            workflow_urls['placement_add'] = None
        if not can_add_delivery:
            workflow_urls['delivery_add'] = None
        return {
            'layout': layout,
            'workflow_urls': workflow_urls,
            'inferred_delivery_actions': tuple(
                SimpleNamespace(
                    row=row,
                    create_url=(
                        build_delivery_add_url(
                            instance,
                            return_url=return_url,
                            electrical_node_id=row.node.pk if row.node else None,
                            electrical_terminal_id=row.terminal.pk if row.terminal else None,
                        )
                        if can_add_delivery else None
                    ),
                )
                for row in layout.inferred_only_rows
            ),
            'placement_actions': tuple(
                SimpleNamespace(
                    item=item,
                    edit_url=(build_placement_edit_url(item.placement, return_url=return_url) if can_edit_placement else None),
                )
                for item in layout.placements
            ),
            'delivery_overlay_actions': tuple(
                SimpleNamespace(
                    item=item,
                    edit_url=(build_delivery_edit_url(item.delivery_point, return_url=return_url) if can_edit_delivery else None),
                )
                for item in layout.delivery_overlays
            ),
        }


class PowerSystemEditView(generic.ObjectEditView):
    queryset = PowerSystem.objects.all()
    form = forms.PowerSystemForm


class PowerSystemDeleteView(generic.ObjectDeleteView):
    queryset = PowerSystem.objects.all()


class PowerDomainListView(generic.ObjectListView):
    queryset = PowerDomain.objects.select_related('power_system')
    filterset = filtersets.PowerDomainFilterSet
    filterset_form = forms.PowerDomainFilterForm
    table = tables.PowerDomainTable


class PowerDomainView(generic.ObjectView):
    queryset = PowerDomain.objects.select_related('power_system')
    template_name = 'netbox_power_plant/powerdomain.html'


class PowerDomainEditView(generic.ObjectEditView):
    queryset = PowerDomain.objects.all()
    form = forms.PowerDomainForm


class PowerDomainDeleteView(generic.ObjectDeleteView):
    queryset = PowerDomain.objects.all()


class RedundancyGroupListView(generic.ObjectListView):
    queryset = RedundancyGroup.objects.select_related('power_system').prefetch_related('power_domains')
    filterset = filtersets.RedundancyGroupFilterSet
    filterset_form = forms.RedundancyGroupFilterForm
    table = tables.RedundancyGroupTable


class RedundancyGroupView(generic.ObjectView):
    queryset = RedundancyGroup.objects.select_related('power_system').prefetch_related('power_domains')
    template_name = 'netbox_power_plant/redundancygroup.html'


class RedundancyGroupEditView(generic.ObjectEditView):
    queryset = RedundancyGroup.objects.all()
    form = forms.RedundancyGroupForm


class RedundancyGroupDeleteView(generic.ObjectDeleteView):
    queryset = RedundancyGroup.objects.all()


class ElectricalNodeListView(generic.ObjectListView):
    queryset = ElectricalNode.objects.select_related('power_system', 'site', 'location', 'parent_node')
    filterset = filtersets.ElectricalNodeFilterSet
    filterset_form = forms.ElectricalNodeFilterForm
    table = tables.ElectricalNodeTable


class ElectricalNodeView(generic.ObjectView):
    queryset = ElectricalNode.objects.select_related('power_system', 'site', 'location', 'parent_node').prefetch_related('terminals')
    template_name = 'netbox_power_plant/electricalnode.html'


class ElectricalNodeEditView(generic.ObjectEditView):
    queryset = ElectricalNode.objects.all()
    form = forms.ElectricalNodeForm


class ElectricalNodeDeleteView(generic.ObjectDeleteView):
    queryset = ElectricalNode.objects.all()


class ElectricalTerminalListView(generic.ObjectListView):
    queryset = ElectricalTerminal.objects.select_related('node', 'node__power_system')
    filterset = filtersets.ElectricalTerminalFilterSet
    filterset_form = forms.ElectricalTerminalFilterForm
    table = tables.ElectricalTerminalTable


class ElectricalTerminalView(generic.ObjectView):
    queryset = ElectricalTerminal.objects.select_related('node', 'node__power_system').prefetch_related('outbound_segments', 'inbound_segments')
    template_name = 'netbox_power_plant/electricalterminal.html'


class ElectricalTerminalEditView(generic.ObjectEditView):
    queryset = ElectricalTerminal.objects.all()
    form = forms.ElectricalTerminalForm


class ElectricalTerminalDeleteView(generic.ObjectDeleteView):
    queryset = ElectricalTerminal.objects.all()


class ElectricalSegmentListView(generic.ObjectListView):
    queryset = ElectricalSegment.objects.select_related('power_system', 'power_domain', 'from_terminal__node', 'to_terminal__node')
    filterset = filtersets.ElectricalSegmentFilterSet
    filterset_form = forms.ElectricalSegmentFilterForm
    table = tables.ElectricalSegmentTable


class ElectricalSegmentView(generic.ObjectView):
    queryset = ElectricalSegment.objects.select_related('power_system', 'power_domain', 'from_terminal__node', 'to_terminal__node')
    template_name = 'netbox_power_plant/electricalsegment.html'


class ElectricalSegmentEditView(generic.ObjectEditView):
    queryset = ElectricalSegment.objects.all()
    form = forms.ElectricalSegmentForm


class ElectricalSegmentDeleteView(generic.ObjectDeleteView):
    queryset = ElectricalSegment.objects.all()


class RackDeliveryPointListView(generic.ObjectListView):
    queryset = RackDeliveryPoint.objects.select_related(
        'power_system', 'electrical_node', 'electrical_terminal', 'rack', 'device', 'expected_redundancy_group'
    )
    filterset = filtersets.RackDeliveryPointFilterSet
    filterset_form = forms.RackDeliveryPointFilterForm
    table = tables.RackDeliveryPointTable


class RackDeliveryPointView(generic.ObjectView):
    queryset = RackDeliveryPoint.objects.select_related(
        'power_system', 'electrical_node', 'electrical_terminal', 'rack', 'device', 'expected_redundancy_group'
    )
    template_name = 'netbox_power_plant/rackdeliverypoint.html'


class RackDeliveryPointEditView(generic.ObjectEditView):
    queryset = RackDeliveryPoint.objects.all()
    form = forms.RackDeliveryPointForm


class RackDeliveryPointDeleteView(generic.ObjectDeleteView):
    queryset = RackDeliveryPoint.objects.all()


class ElectricalNodePlacementListView(generic.ObjectListView):
    queryset = ElectricalNodePlacement.objects.select_related('power_system', 'electrical_node', 'site', 'location')
    filterset = filtersets.ElectricalNodePlacementFilterSet
    filterset_form = forms.ElectricalNodePlacementFilterForm
    table = tables.ElectricalNodePlacementTable


class ElectricalNodePlacementView(generic.ObjectView):
    queryset = ElectricalNodePlacement.objects.select_related('power_system', 'electrical_node', 'site', 'location')
    template_name = 'netbox_power_plant/electricalnodeplacement.html'


class ElectricalNodePlacementEditView(generic.ObjectEditView):
    queryset = ElectricalNodePlacement.objects.all()
    form = forms.ElectricalNodePlacementForm


class ElectricalNodePlacementDeleteView(generic.ObjectDeleteView):
    queryset = ElectricalNodePlacement.objects.all()
