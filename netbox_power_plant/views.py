from types import SimpleNamespace
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView
from django_tables2 import RequestConfig

from netbox.views import generic
from dcim.models import Site

from . import filtersets, forms, tables
from .models import (
    BESSDetail,
    BuswaySectionDetail,
    CapacityReservation,
    ElectricalNode,
    ElectricalNodePlacement,
    ElectricalSegment,
    ElectricalTerminal,
    GeneratorDetail,
    InstantiationArtifact,
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
from .services.layout import build_power_system_layout_view
from .services.layout_validation import build_layout_health_summary
from .services.cad_uploads import store_cad_upload_package
from .services.madison_cad_approval import approve_madison_cad_underlay
from .services.madison_cad_materialization import ingest_madison_cad_underlay
from .services.madison_review import DEFAULT_MADISON_SITE_SLUG, build_madison_underlay_review_summary
from .services.madison_space_decomposition import (
    apply_madison_detailed_space_decomposition,
    approve_madison_detailed_space_boundaries,
)
from .services.madison_rack_footprints import (
    apply_madison_rack_footprint_candidates,
    approve_madison_rack_footprint_bindings,
)
from .services.neocloud_cockpit import build_neocloud_cockpit_workflow
from .services.operator_dashboard import build_operator_dashboard
from .services.spatial_geometry_review import (
    approve_visual_geometry_correction,
    update_physical_space_geometry_from_visual_review,
)
from .services.spatial_review import build_spatial_review_map
from .services.capacity import build_power_system_capacity_summary
from .services.completeness import build_power_system_completeness_summary
from .services.operational_planning import build_capacity_planning_summary
from .services.rack_delivery import build_power_handoff_summary
from .services.template_workflows import (
    apply_reviewed_instantiation_run,
    build_instantiation_result_payload,
    build_template_dry_run_preview,
    list_reference_templates,
    seed_reference_templates_if_missing,
)
from .services.validation_actions import VALIDATION_ACTIONS, run_validation_action, validation_action_for_kind
from .services.visual_layout import build_visual_layout_map
from .services.workflow_urls import (
    build_delivery_add_url,
    build_delivery_edit_url,
    build_layout_url,
    build_placement_edit_url,
    build_power_handoff_summary_url,
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


class OperatorDashboardView(TemplateView):
    template_name = 'netbox_power_plant/operator_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dashboard'] = build_operator_dashboard()
        return context


class NeocloudCockpitView(PermissionRequiredMixin, TemplateView):
    permission_required = 'netbox_power_plant.view_powersystem'
    template_name = 'netbox_power_plant/neocloud_cockpit.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = kwargs.get('form') or forms.NeocloudCockpitForm()
        context['workflow'] = kwargs.get('workflow')
        return context

    def post(self, request, *args, **kwargs):
        form = forms.NeocloudCockpitForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        scenario_type = form.cleaned_data['scenario_type']
        if scenario_type == forms.NeocloudCockpitForm.SCENARIO_NODE_OFFLINE:
            required_permission = 'netbox_power_plant.view_electricalnode'
        elif scenario_type == forms.NeocloudCockpitForm.SCENARIO_SEGMENT_CUT:
            required_permission = 'netbox_power_plant.view_electricalsegment'
        else:
            required_permission = 'netbox_power_plant.view_powerdomain'
        if not request.user.has_perm(required_permission):
            raise PermissionDenied

        workflow = build_neocloud_cockpit_workflow(
            form.cleaned_data['power_system'],
            scenario_type=scenario_type,
            target_id=form.cleaned_data['target_id'],
        )
        messages.success(request, 'Neocloud operator workflow scenario evaluated.')
        return self.render_to_response(self.get_context_data(form=form, workflow=workflow))


class TemplateWorkflowView(PermissionRequiredMixin, TemplateView):
    permission_required = 'netbox_power_plant.view_powerarchitecturetemplate'
    template_name = 'netbox_power_plant/template_workflow.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reference_templates'] = list_reference_templates()
        context['dry_run_form'] = kwargs.get('dry_run_form') or forms.TemplateInstantiationDryRunForm()
        context['apply_form'] = kwargs.get('apply_form') or forms.TemplateInstantiationApplyForm()
        context['result'] = kwargs.get('result')
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'seed_reference_templates':
            if not (
                request.user.has_perm('netbox_power_plant.add_powerarchitecturetemplate')
                and request.user.has_perm('netbox_power_plant.change_powerarchitecturetemplate')
            ):
                raise PermissionDenied
            templates = seed_reference_templates_if_missing()
            messages.success(
                request,
                f'Reference templates are ready: {len(templates)} template'
                f'{"" if len(templates) == 1 else "s"} available.',
            )
            return redirect(reverse('plugins:netbox_power_plant:template_workflow'))

        if action == 'dry_run_template':
            if not request.user.has_perm('netbox_power_plant.add_instantiationrun'):
                raise PermissionDenied
            form = forms.TemplateInstantiationDryRunForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(dry_run_form=form))
            result = build_template_dry_run_preview(
                form.cleaned_data['power_system'],
                form.cleaned_data['template'],
                context=form.cleaned_data.get('context_json') or {},
            )
            messages.success(
                request,
                f'Dry run created with {result.run.artifact_count} proposed artifact'
                f'{"" if result.run.artifact_count == 1 else "s"}.',
            )
            return self.render_to_response(
                self.get_context_data(
                    dry_run_form=form,
                    result=build_instantiation_result_payload(result),
                )
            )

        if action == 'apply_instantiation_run':
            if not request.user.has_perm('netbox_power_plant.change_instantiationrun'):
                raise PermissionDenied
            form = forms.TemplateInstantiationApplyForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(apply_form=form))
            result = apply_reviewed_instantiation_run(form.cleaned_data['run'])
            messages.success(
                request,
                f'Applied template run: {result.created_count} created, {result.updated_count} updated.',
            )
            return self.render_to_response(
                self.get_context_data(
                    apply_form=form,
                    result=build_instantiation_result_payload(result),
                )
            )

        return HttpResponseNotAllowed(['GET', 'POST'])


class MadisonUnderlayReviewView(TemplateView):
    template_name = 'netbox_power_plant/madison_underlay_review.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        site_slug = self.request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = kwargs.get('summary') or build_madison_underlay_review_summary(site_slug)
        context['summary'] = summary
        context['spatial_review_map'] = self._spatial_review_map(summary)
        context['ingest_form'] = kwargs.get('ingest_form') or self._ingest_form(summary)
        context['approval_form'] = kwargs.get('approval_form') or self._approval_form(summary)
        context['space_decomposition_form'] = (
            kwargs.get('space_decomposition_form') or forms.MadisonDetailedSpaceDecompositionForm()
        )
        context['space_boundary_approval_form'] = (
            kwargs.get('space_boundary_approval_form') or forms.MadisonDetailedSpaceBoundaryApprovalForm()
        )
        context['rack_footprint_materialization_form'] = (
            kwargs.get('rack_footprint_materialization_form')
            or forms.MadisonRackFootprintMaterializationForm()
        )
        context['rack_footprint_approval_form'] = (
            kwargs.get('rack_footprint_approval_form')
            or forms.MadisonRackFootprintApprovalForm()
        )
        context['spatial_review_geometry_form'] = (
            kwargs.get('spatial_review_geometry_form') or forms.SpatialReviewSpaceGeometryForm()
        )
        context['spatial_review_geometry_approval_form'] = (
            kwargs.get('spatial_review_geometry_approval_form')
            or forms.SpatialReviewSpaceGeometryApprovalForm()
        )
        context['can_ingest_cad_underlay'] = (
            self.request.user.has_perm('netbox_power_plant.add_plantsourcedocument')
            and self.request.user.has_perm('netbox_power_plant.add_spatialframe')
        )
        context['can_approve_cad_underlay'] = self.request.user.has_perm('netbox_power_plant.change_spatialframe')
        context['can_apply_detailed_spaces'] = (
            self.request.user.has_perm('netbox_power_plant.add_physicalspace')
            and self.request.user.has_perm('netbox_power_plant.change_physicalspace')
            and self.request.user.has_perm('netbox_power_plant.add_plantprovenance')
        )
        context['can_approve_detailed_space_boundaries'] = (
            self.request.user.has_perm('netbox_power_plant.change_physicalspace')
            and self.request.user.has_perm('netbox_power_plant.change_plantprovenance')
        )
        context['can_apply_rack_footprints'] = (
            self.request.user.has_perm('netbox_power_plant.add_physicalelement')
            and self.request.user.has_perm('netbox_power_plant.change_physicalelement')
            and self.request.user.has_perm('netbox_power_plant.add_spatialplacement')
            and self.request.user.has_perm('netbox_power_plant.change_spatialplacement')
            and self.request.user.has_perm('netbox_power_plant.add_physicalobjectbinding')
            and self.request.user.has_perm('netbox_power_plant.add_plantprovenance')
        )
        context['can_approve_rack_footprints'] = (
            self.request.user.has_perm('netbox_power_plant.change_physicalelement')
            and self.request.user.has_perm('netbox_power_plant.change_spatialplacement')
            and self.request.user.has_perm('netbox_power_plant.change_physicalobjectbinding')
            and self.request.user.has_perm('netbox_power_plant.change_plantprovenance')
        )
        context['can_edit_spatial_review_geometry'] = (
            self.request.user.has_perm('netbox_power_plant.change_physicalspace')
            and self.request.user.has_perm('netbox_power_plant.add_plantprovenance')
            and self.request.user.has_perm('netbox_power_plant.change_plantprovenance')
        )
        context['can_approve_spatial_review_geometry'] = (
            self.request.user.has_perm('netbox_power_plant.change_physicalspace')
            and self.request.user.has_perm('netbox_power_plant.change_plantprovenance')
        )
        return context

    def _spatial_review_map(self, summary):
        if not summary.site_found:
            return build_spatial_review_map(None)

        frame = None
        cad_underlay = getattr(summary, 'cad_underlay', None)
        if cad_underlay is not None:
            frame = cad_underlay.site_frame

        return build_spatial_review_map(summary.site, frame=frame)

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'ingest_cad_underlay':
            return self._post_ingest(request)
        if action == 'apply_detailed_spaces':
            return self._post_apply_detailed_spaces(request)
        if action == 'approve_detailed_space_boundaries':
            return self._post_approve_detailed_space_boundaries(request)
        if action == 'apply_rack_footprints':
            return self._post_apply_rack_footprints(request)
        if action == 'approve_rack_footprint_bindings':
            return self._post_approve_rack_footprint_bindings(request)
        if action == 'update_space_geometry':
            return self._post_update_space_geometry(request)
        if action == 'approve_space_geometry':
            return self._post_approve_space_geometry(request)
        if action != 'approve_cad_underlay':
            return HttpResponseNotAllowed(['GET', 'POST'])
        if not request.user.has_perm('netbox_power_plant.change_spatialframe'):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.MadisonCadUnderlayApprovalForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(summary=summary, approval_form=form))

        try:
            result = approve_madison_cad_underlay(site_slug, overrides=form.to_overrides(), reviewer=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            (
                f"Approved Madison CAD underlay for {result.site.name}; "
                f"{len(result.decomposition_spaces)} decomposition spaces are ready for detailed boundary review."
            ),
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_apply_detailed_spaces(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.add_physicalspace')
            and request.user.has_perm('netbox_power_plant.change_physicalspace')
            and request.user.has_perm('netbox_power_plant.add_plantprovenance')
        ):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.MadisonDetailedSpaceDecompositionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(summary=summary, space_decomposition_form=form)
            )

        try:
            result = apply_madison_detailed_space_decomposition(site_slug, reviewer=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            (
                f"Applied Madison detailed space decomposition for {result.site.name}: "
                f"{result.created_count} created, {result.updated_count} updated, "
                f"{result.unchanged_count} unchanged; {result.pending_review_count} space"
                f"{'' if result.pending_review_count == 1 else 's'} ready for boundary review."
            ),
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_update_space_geometry(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.change_physicalspace')
            and request.user.has_perm('netbox_power_plant.add_plantprovenance')
            and request.user.has_perm('netbox_power_plant.change_plantprovenance')
        ):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.SpatialReviewSpaceGeometryForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(summary=summary, spatial_review_geometry_form=form)
            )

        frame = None
        cad_underlay = getattr(summary, 'cad_underlay', None)
        if cad_underlay is not None:
            frame = cad_underlay.site_frame

        try:
            result = update_physical_space_geometry_from_visual_review(
                form.cleaned_data['space_id'],
                x=form.cleaned_data['x'],
                y=form.cleaned_data['y'],
                width=form.cleaned_data['width'],
                depth=form.cleaned_data['depth'],
                reviewer=request.user,
                notes=form.cleaned_data.get('notes') or '',
                site=summary.site,
                spatial_frame=frame,
            )
        except (PhysicalSpace.DoesNotExist, ValueError) as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            (
                f"Updated visual geometry for {result.space.name}; "
                "the boundary now requires visual approval."
            ),
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_approve_space_geometry(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.change_physicalspace')
            and request.user.has_perm('netbox_power_plant.change_plantprovenance')
        ):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.SpatialReviewSpaceGeometryApprovalForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(summary=summary, spatial_review_geometry_approval_form=form)
            )

        frame = None
        cad_underlay = getattr(summary, 'cad_underlay', None)
        if cad_underlay is not None:
            frame = cad_underlay.site_frame

        try:
            result = approve_visual_geometry_correction(
                form.cleaned_data['space_id'],
                reviewer=request.user,
                notes=form.cleaned_data.get('notes') or '',
                site=summary.site,
                spatial_frame=frame,
            )
        except (PhysicalSpace.DoesNotExist, ValueError) as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            f"Approved corrected visual geometry for {result.space.name}.",
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_approve_detailed_space_boundaries(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.change_physicalspace')
            and request.user.has_perm('netbox_power_plant.change_plantprovenance')
        ):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.MadisonDetailedSpaceBoundaryApprovalForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(summary=summary, space_boundary_approval_form=form)
            )

        try:
            result = approve_madison_detailed_space_boundaries(
                site_slug,
                reviewer=request.user,
                notes=form.cleaned_data.get('notes') or '',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            (
                f"Approved Madison detailed space boundaries for {result.site.name}: "
                f"{result.approved_count} approved, {result.updated_count} updated, "
                f"{result.unchanged_count} already current."
            ),
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_apply_rack_footprints(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.add_physicalelement')
            and request.user.has_perm('netbox_power_plant.change_physicalelement')
            and request.user.has_perm('netbox_power_plant.add_spatialplacement')
            and request.user.has_perm('netbox_power_plant.change_spatialplacement')
            and request.user.has_perm('netbox_power_plant.add_physicalobjectbinding')
            and request.user.has_perm('netbox_power_plant.add_plantprovenance')
        ):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.MadisonRackFootprintMaterializationForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(summary=summary, rack_footprint_materialization_form=form)
            )

        try:
            result = apply_madison_rack_footprint_candidates(site_slug, reviewer=request.user)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            (
                f"Applied Madison rack/cabinet footprints for {result.site.name}: "
                f"{result.created_count} created, {result.updated_count} updated, "
                f"{result.unchanged_count} unchanged; {result.matched_count} matched to NetBox rack"
                f"{'' if result.matched_count == 1 else 's'}."
            ),
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_approve_rack_footprint_bindings(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.change_physicalelement')
            and request.user.has_perm('netbox_power_plant.change_spatialplacement')
            and request.user.has_perm('netbox_power_plant.change_physicalobjectbinding')
            and request.user.has_perm('netbox_power_plant.change_plantprovenance')
        ):
            raise PermissionDenied

        site_slug = request.POST.get('site') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        form = forms.MadisonRackFootprintApprovalForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(summary=summary, rack_footprint_approval_form=form)
            )

        try:
            result = approve_madison_rack_footprint_bindings(
                site_slug,
                reviewer=request.user,
                notes=form.cleaned_data.get('notes') or '',
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

        messages.success(
            request,
            (
                f"Approved Madison rack/cabinet footprint bindings for {result.site.name}: "
                f"{result.approved_count} approved."
            ),
        )
        return redirect(f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={site_slug}")

    def _post_ingest(self, request):
        if not (
            request.user.has_perm('netbox_power_plant.add_plantsourcedocument')
            and request.user.has_perm('netbox_power_plant.add_spatialframe')
        ):
            raise PermissionDenied

        form = forms.MadisonCadUnderlayIngestForm(request.POST, request.FILES)
        site_slug = request.POST.get('site_slug') or request.GET.get('site') or DEFAULT_MADISON_SITE_SLUG
        summary = build_madison_underlay_review_summary(site_slug)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(summary=summary, ingest_form=form))

        existing_site = Site.objects.filter(slug=form.cleaned_data['site_slug']).first()
        if existing_site is None and not request.user.has_perm('dcim.add_site'):
            raise PermissionDenied
        if (
            existing_site is not None
            and form.cleaned_data.get('site_name')
            and existing_site.name != form.cleaned_data['site_name']
            and not request.user.has_perm('dcim.change_site')
        ):
            raise PermissionDenied

        try:
            upload_package = store_cad_upload_package(
                site_slug=form.cleaned_data['site_slug'],
                uploaded_files=form.cleaned_data['cad_package'],
            )
            result = ingest_madison_cad_underlay(
                site_slug=form.cleaned_data['site_slug'],
                site_name=form.cleaned_data.get('site_name') or '',
                cad_dir=upload_package.root,
                source_units=form.cleaned_data.get('source_units') or 'inch',
                apply=True,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return self.render_to_response(self.get_context_data(summary=summary, ingest_form=form))

        messages.success(
            request,
            (
                f"Ingested Madison CAD package for {result.site.name}: "
                f"{result.materialization.sheet_count} sheet"
                f"{'' if result.materialization.sheet_count == 1 else 's'}, "
                f"{result.materialization.layer_count} geometry layer"
                f"{'' if result.materialization.layer_count == 1 else 's'} "
                f"from {upload_package.dwg_count} uploaded DWG"
                f"{'' if upload_package.dwg_count == 1 else 's'}."
            ),
        )
        return redirect(
            f"{reverse('plugins:netbox_power_plant:madison_underlay_review')}?site={result.site.slug}"
        )

    def _ingest_form(self, summary):
        initial = {
            'site_slug': summary.site_slug,
            'site_name': summary.site.name if summary.site is not None else '',
            'source_units': 'inch',
        }
        return forms.MadisonCadUnderlayIngestForm(initial=initial)

    def _approval_form(self, summary):
        cad_underlay = getattr(summary, 'cad_underlay', None)
        if cad_underlay is None:
            return forms.MadisonCadUnderlayApprovalForm()
        initial = {
            'source_units': cad_underlay.source_units,
        }
        if cad_underlay.site_frame is not None:
            initial.update(
                {
                    'site_width': cad_underlay.site_frame.width,
                    'site_height': cad_underlay.site_frame.height,
                }
            )
        if cad_underlay.current_building_placement is not None:
            initial.update(
                {
                    'building_origin_x': cad_underlay.current_building_placement.x,
                    'building_origin_y': cad_underlay.current_building_placement.y,
                    'building_width': cad_underlay.current_building_placement.width,
                    'building_height': cad_underlay.current_building_placement.depth,
                }
            )
        return forms.MadisonCadUnderlayApprovalForm(initial=initial)


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
        power_handoff_summary_url = build_power_handoff_summary_url(instance)
        workflow_urls = build_workflow_urls(
            instance,
            placement_return_url=layout_url,
            delivery_return_url=power_handoff_summary_url,
        )
        if not request.user.has_perm('netbox_power_plant.add_electricalnodeplacement'):
            workflow_urls['placement_add'] = None
        if not request.user.has_perm('netbox_power_plant.add_powerhandoffpoint'):
            workflow_urls['delivery_add'] = None
        capacity_summary = build_power_system_capacity_summary(instance)
        return {
            'capacity_summary': capacity_summary,
            'capacity_plan': build_capacity_planning_summary(instance),
            'completeness_summary': build_power_system_completeness_summary(instance),
            'layout_health': build_layout_health_summary(instance),
            'validation_actions': tuple(
                SimpleNamespace(
                    action=action,
                    url=reverse(
                        'plugins:netbox_power_plant:powersystem_validation_action',
                        kwargs={'pk': instance.pk, 'run_kind': action.run_kind},
                    ),
                )
                for action in VALIDATION_ACTIONS
            ),
            'workflow_urls': workflow_urls,
        }


class PowerSystemValidationActionView(PermissionRequiredMixin, View):
    permission_required = 'netbox_power_plant.add_powervalidationrun'

    def post(self, request, pk, run_kind):
        power_system = get_object_or_404(PowerSystem, pk=pk)
        action = validation_action_for_kind(run_kind)
        if action is None:
            messages.error(request, f'Unsupported validation run kind: {run_kind}')
            return redirect(power_system.get_absolute_url())

        result = run_validation_action(power_system, run_kind)
        messages.success(
            request,
            (
                f'{action.label} completed with {result.open_count} open '
                f'finding{"" if result.open_count == 1 else "s"}.'
            ),
        )
        return redirect(result.run.get_absolute_url())


class PowerSystemPowerHandoffSummaryView(generic.ObjectView):
    queryset = PowerSystem.objects.prefetch_related('power_domains', 'redundancy_groups__power_domains')
    template_name = 'netbox_power_plant/powersystem_rack_delivery.html'

    def get_extra_context(self, request, instance):
        return_url = request.get_full_path()
        can_add_placement = request.user.has_perm('netbox_power_plant.add_electricalnodeplacement')
        can_add_delivery = request.user.has_perm('netbox_power_plant.add_powerhandoffpoint')
        can_edit_delivery = request.user.has_perm('netbox_power_plant.change_powerhandoffpoint')
        workflow_urls = build_workflow_urls(
            instance,
            placement_return_url=return_url,
            delivery_return_url=return_url,
        )
        if not can_add_placement:
            workflow_urls['placement_add'] = None
        if not can_add_delivery:
            workflow_urls['delivery_add'] = None
        delivery_summary = build_power_handoff_summary(instance)
        delivery_table = tables.PowerHandoffSummaryTable(
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


PowerSystemRackDeliveryView = PowerSystemPowerHandoffSummaryView


class PowerSystemLayoutView(generic.ObjectView):
    queryset = PowerSystem.objects.prefetch_related(
        'power_domains',
        'redundancy_groups__power_domains',
        'power_handoff_points',
        'electrical_node_placements',
    )
    template_name = 'netbox_power_plant/powersystem_layout.html'

    def get_extra_context(self, request, instance):
        return_url = request.get_full_path()
        layout = build_power_system_layout_view(instance)
        can_add_placement = request.user.has_perm('netbox_power_plant.add_electricalnodeplacement')
        can_add_delivery = request.user.has_perm('netbox_power_plant.add_powerhandoffpoint')
        can_edit_placement = request.user.has_perm('netbox_power_plant.change_electricalnodeplacement')
        can_edit_delivery = request.user.has_perm('netbox_power_plant.change_powerhandoffpoint')
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
            'visual_map': build_visual_layout_map(layout),
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


class PowerValidationRunListView(generic.ObjectListView):
    queryset = PowerValidationRun.objects.select_related('power_system')
    filterset = filtersets.PowerValidationRunFilterSet
    filterset_form = forms.PowerValidationRunFilterForm
    table = tables.PowerValidationRunTable


class PowerValidationRunView(generic.ObjectView):
    queryset = PowerValidationRun.objects.select_related('power_system').prefetch_related('findings')
    template_name = 'netbox_power_plant/powervalidationrun.html'

    def get_extra_context(self, request, instance):
        findings_table = tables.PowerFindingTable(
            instance.findings.select_related('run', 'power_system', 'assigned_object_type', 'assigned_to')
        )
        RequestConfig(request).configure(findings_table)
        return {
            'findings_table': findings_table,
        }


class PowerValidationRunEditView(generic.ObjectEditView):
    queryset = PowerValidationRun.objects.all()
    form = forms.PowerValidationRunForm


class PowerValidationRunDeleteView(generic.ObjectDeleteView):
    queryset = PowerValidationRun.objects.all()


class PowerFindingListView(generic.ObjectListView):
    queryset = PowerFinding.objects.select_related('run', 'power_system', 'assigned_object_type', 'assigned_to')
    filterset = filtersets.PowerFindingFilterSet
    filterset_form = forms.PowerFindingFilterForm
    table = tables.PowerFindingTable


class PowerFindingView(generic.ObjectView):
    queryset = PowerFinding.objects.select_related('run', 'power_system', 'assigned_object_type', 'assigned_to')
    template_name = 'netbox_power_plant/powerfinding.html'


class PowerFindingEditView(generic.ObjectEditView):
    queryset = PowerFinding.objects.all()
    form = forms.PowerFindingForm


class PowerFindingDeleteView(generic.ObjectDeleteView):
    queryset = PowerFinding.objects.all()


class PowerArchitectureTemplateListView(generic.ObjectListView):
    queryset = PowerArchitectureTemplate.objects.all()
    filterset = filtersets.PowerArchitectureTemplateFilterSet
    filterset_form = forms.PowerArchitectureTemplateFilterForm
    table = tables.PowerArchitectureTemplateTable


class PowerArchitectureTemplateView(generic.ObjectView):
    queryset = PowerArchitectureTemplate.objects.prefetch_related('nodes', 'segments', 'instantiation_runs')
    template_name = 'netbox_power_plant/powerarchitecturetemplate.html'


class InstantiationRunListView(generic.ObjectListView):
    queryset = InstantiationRun.objects.select_related('power_system', 'template')
    filterset = filtersets.InstantiationRunFilterSet
    filterset_form = forms.InstantiationRunFilterForm
    table = tables.InstantiationRunTable


class InstantiationRunView(generic.ObjectView):
    queryset = InstantiationRun.objects.select_related('power_system', 'template').prefetch_related('artifacts')
    template_name = 'netbox_power_plant/instantiationrun.html'

    def get_extra_context(self, request, instance):
        artifact_table = tables.InstantiationArtifactTable(instance.artifacts.all())
        RequestConfig(request).configure(artifact_table)
        return {
            'artifact_table': artifact_table,
        }


class InstantiationArtifactListView(generic.ObjectListView):
    queryset = InstantiationArtifact.objects.select_related('run', 'run__power_system', 'run__template', 'object_type')
    filterset = filtersets.InstantiationArtifactFilterSet
    filterset_form = forms.InstantiationArtifactFilterForm
    table = tables.InstantiationArtifactTable


class InstantiationArtifactView(generic.ObjectView):
    queryset = InstantiationArtifact.objects.select_related('run', 'run__power_system', 'run__template', 'object_type')
    template_name = 'netbox_power_plant/instantiationartifact.html'


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


class PowerHandoffPointListView(generic.ObjectListView):
    queryset = PowerHandoffPoint.objects.select_related(
        'power_system', 'electrical_node', 'electrical_terminal', 'power_port', 'power_port__device',
        'expected_redundancy_group'
    )
    filterset = filtersets.PowerHandoffPointFilterSet
    filterset_form = forms.PowerHandoffPointFilterForm
    table = tables.PowerHandoffPointTable


class PowerHandoffPointView(generic.ObjectView):
    queryset = PowerHandoffPoint.objects.select_related(
        'power_system', 'electrical_node', 'electrical_terminal', 'power_port', 'power_port__device',
        'expected_redundancy_group'
    )
    template_name = 'netbox_power_plant/powerhandoffpoint.html'


class PowerHandoffPointEditView(generic.ObjectEditView):
    queryset = PowerHandoffPoint.objects.all()
    form = forms.PowerHandoffPointForm


class PowerHandoffPointDeleteView(generic.ObjectDeleteView):
    queryset = PowerHandoffPoint.objects.all()


class CapacityReservationListView(generic.ObjectListView):
    queryset = CapacityReservation.objects.select_related(
        'node', 'node__power_system', 'node__site', 'tenant', 'rack'
    )
    filterset = filtersets.CapacityReservationFilterSet
    filterset_form = forms.CapacityReservationFilterForm
    table = tables.CapacityReservationTable


class CapacityReservationView(generic.ObjectView):
    queryset = CapacityReservation.objects.select_related(
        'node', 'node__power_system', 'node__site', 'tenant', 'rack'
    )
    template_name = 'netbox_power_plant/capacityreservation.html'


class CapacityReservationEditView(generic.ObjectEditView):
    queryset = CapacityReservation.objects.all()
    form = forms.CapacityReservationForm


class CapacityReservationDeleteView(generic.ObjectDeleteView):
    queryset = CapacityReservation.objects.all()


class PlainPluginModelListView(PermissionRequiredMixin, TemplateView):
    template_name = 'netbox_power_plant/plain_model_list.html'
    model = None
    queryset = None
    filterset = None
    filterset_form = None
    table = None

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset.all()
        return self.model.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self.get_queryset()
        filterset = self.filterset(self.request.GET, queryset=queryset) if self.filterset else None
        object_list = filterset.qs if filterset is not None else queryset
        table = self.table(object_list)
        RequestConfig(self.request).configure(table)
        context.update({
            'model': self.model,
            'title': self.model._meta.verbose_name_plural.title(),
            'filterset': filterset,
            'filter_form': self.filterset_form(self.request.GET) if self.filterset_form else None,
            'table': table,
        })
        return context


class PlainPluginModelView(PermissionRequiredMixin, TemplateView):
    model = None
    queryset = None

    def get_queryset(self):
        if self.queryset is not None:
            return self.queryset.all()
        return self.model.objects.all()

    def get_object(self):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object'] = self.get_object()
        return context


class PlainPluginModelEditView(TemplateView):
    template_name = 'netbox_power_plant/plain_model_edit.html'
    model = None
    form = None
    list_url_name = None

    def dispatch(self, request, *args, **kwargs):
        action = 'change' if kwargs.get('pk') else 'add'
        if not request.user.has_perm(f'netbox_power_plant.{action}_{self.model._meta.model_name}'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):
        if self.kwargs.get('pk') is None:
            return None
        return get_object_or_404(self.model.objects.all(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.get_object()
        context['object'] = obj
        context['form'] = kwargs.get('form') or self.form(instance=obj)
        context['title'] = (
            f'Edit {self.model._meta.verbose_name.title()}'
            if obj is not None
            else f'Add {self.model._meta.verbose_name.title()}'
        )
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        form = self.form(request.POST, instance=obj)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        saved = form.save()
        messages.success(request, f'Saved {saved}.')
        return redirect(saved.get_absolute_url())


class PlainPluginModelDeleteView(TemplateView):
    template_name = 'netbox_power_plant/plain_model_delete.html'
    model = None
    list_url_name = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm(f'netbox_power_plant.delete_{self.model._meta.model_name}'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_object(self):
        return get_object_or_404(self.model.objects.all(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['object'] = self.get_object()
        context['list_url'] = reverse(f'plugins:netbox_power_plant:{self.list_url_name}')
        return context

    def post(self, request, *args, **kwargs):
        obj = self.get_object()
        display = str(obj)
        obj.delete()
        messages.success(request, f'Deleted {display}.')
        return redirect(reverse(f'plugins:netbox_power_plant:{self.list_url_name}'))


class UPSDetailListView(PlainPluginModelListView):
    permission_required = 'netbox_power_plant.view_upsdetail'
    model = UPSDetail
    queryset = UPSDetail.objects.select_related('node', 'node__power_system', 'node__site')
    filterset = filtersets.UPSDetailFilterSet
    filterset_form = forms.UPSDetailFilterForm
    table = tables.UPSDetailTable


class UPSDetailView(PlainPluginModelView):
    permission_required = 'netbox_power_plant.view_upsdetail'
    model = UPSDetail
    queryset = UPSDetail.objects.select_related('node', 'node__power_system', 'node__site')
    template_name = 'netbox_power_plant/upsdetail.html'


class UPSDetailEditView(PlainPluginModelEditView):
    model = UPSDetail
    form = forms.UPSDetailForm


class UPSDetailDeleteView(PlainPluginModelDeleteView):
    model = UPSDetail
    list_url_name = 'upsdetail_list'


class GeneratorDetailListView(PlainPluginModelListView):
    permission_required = 'netbox_power_plant.view_generatordetail'
    model = GeneratorDetail
    queryset = GeneratorDetail.objects.select_related('node', 'node__power_system', 'node__site')
    filterset = filtersets.GeneratorDetailFilterSet
    filterset_form = forms.GeneratorDetailFilterForm
    table = tables.GeneratorDetailTable


class GeneratorDetailView(PlainPluginModelView):
    permission_required = 'netbox_power_plant.view_generatordetail'
    model = GeneratorDetail
    queryset = GeneratorDetail.objects.select_related('node', 'node__power_system', 'node__site')
    template_name = 'netbox_power_plant/generatordetail.html'


class GeneratorDetailEditView(PlainPluginModelEditView):
    model = GeneratorDetail
    form = forms.GeneratorDetailForm


class GeneratorDetailDeleteView(PlainPluginModelDeleteView):
    model = GeneratorDetail
    list_url_name = 'generatordetail_list'


class TransformerDetailListView(PlainPluginModelListView):
    permission_required = 'netbox_power_plant.view_transformerdetail'
    model = TransformerDetail
    queryset = TransformerDetail.objects.select_related('node', 'node__power_system', 'node__site')
    filterset = filtersets.TransformerDetailFilterSet
    filterset_form = forms.TransformerDetailFilterForm
    table = tables.TransformerDetailTable


class TransformerDetailView(PlainPluginModelView):
    permission_required = 'netbox_power_plant.view_transformerdetail'
    model = TransformerDetail
    queryset = TransformerDetail.objects.select_related('node', 'node__power_system', 'node__site')
    template_name = 'netbox_power_plant/transformerdetail.html'


class TransformerDetailEditView(PlainPluginModelEditView):
    model = TransformerDetail
    form = forms.TransformerDetailForm


class TransformerDetailDeleteView(PlainPluginModelDeleteView):
    model = TransformerDetail
    list_url_name = 'transformerdetail_list'


class BESSDetailListView(PlainPluginModelListView):
    permission_required = 'netbox_power_plant.view_bessdetail'
    model = BESSDetail
    queryset = BESSDetail.objects.select_related('node', 'node__power_system', 'node__site')
    filterset = filtersets.BESSDetailFilterSet
    filterset_form = forms.BESSDetailFilterForm
    table = tables.BESSDetailTable


class BESSDetailView(PlainPluginModelView):
    permission_required = 'netbox_power_plant.view_bessdetail'
    model = BESSDetail
    queryset = BESSDetail.objects.select_related('node', 'node__power_system', 'node__site')
    template_name = 'netbox_power_plant/bessdetail.html'


class BESSDetailEditView(PlainPluginModelEditView):
    model = BESSDetail
    form = forms.BESSDetailForm


class BESSDetailDeleteView(PlainPluginModelDeleteView):
    model = BESSDetail
    list_url_name = 'bessdetail_list'


class BuswaySectionDetailListView(PlainPluginModelListView):
    permission_required = 'netbox_power_plant.view_buswaysectiondetail'
    model = BuswaySectionDetail
    queryset = BuswaySectionDetail.objects.select_related(
        'node', 'node__power_system', 'node__site', 'busway_system'
    )
    filterset = filtersets.BuswaySectionDetailFilterSet
    filterset_form = forms.BuswaySectionDetailFilterForm
    table = tables.BuswaySectionDetailTable


class BuswaySectionDetailView(PlainPluginModelView):
    permission_required = 'netbox_power_plant.view_buswaysectiondetail'
    model = BuswaySectionDetail
    queryset = BuswaySectionDetail.objects.select_related(
        'node', 'node__power_system', 'node__site', 'busway_system'
    )
    template_name = 'netbox_power_plant/buswaysectiondetail.html'


class BuswaySectionDetailEditView(PlainPluginModelEditView):
    model = BuswaySectionDetail
    form = forms.BuswaySectionDetailForm


class BuswaySectionDetailDeleteView(PlainPluginModelDeleteView):
    model = BuswaySectionDetail
    list_url_name = 'buswaysectiondetail_list'


class InternalPowerBusListView(generic.ObjectListView):
    queryset = InternalPowerBus.objects.select_related('power_system', 'rack')
    filterset = filtersets.InternalPowerBusFilterSet
    filterset_form = forms.InternalPowerBusFilterForm
    table = tables.InternalPowerBusTable


class InternalPowerBusView(generic.ObjectView):
    queryset = InternalPowerBus.objects.select_related('power_system', 'rack').prefetch_related(
        'attachments__power_port__device'
    )
    template_name = 'netbox_power_plant/internalpowerbus.html'


class InternalPowerBusEditView(generic.ObjectEditView):
    queryset = InternalPowerBus.objects.all()
    form = forms.InternalPowerBusForm


class InternalPowerBusDeleteView(generic.ObjectDeleteView):
    queryset = InternalPowerBus.objects.all()


class InternalPowerBusAttachmentListView(generic.ObjectListView):
    queryset = InternalPowerBusAttachment.objects.select_related(
        'internal_power_bus', 'internal_power_bus__power_system', 'internal_power_bus__rack',
        'power_port', 'power_port__device',
    )
    filterset = filtersets.InternalPowerBusAttachmentFilterSet
    filterset_form = forms.InternalPowerBusAttachmentFilterForm
    table = tables.InternalPowerBusAttachmentTable


class InternalPowerBusAttachmentView(generic.ObjectView):
    queryset = InternalPowerBusAttachment.objects.select_related(
        'internal_power_bus', 'internal_power_bus__power_system', 'internal_power_bus__rack',
        'power_port', 'power_port__device',
    )
    template_name = 'netbox_power_plant/internalpowerbusattachment.html'


class InternalPowerBusAttachmentEditView(generic.ObjectEditView):
    queryset = InternalPowerBusAttachment.objects.all()
    form = forms.InternalPowerBusAttachmentForm


class InternalPowerBusAttachmentDeleteView(generic.ObjectDeleteView):
    queryset = InternalPowerBusAttachment.objects.all()


class PlantSourceDocumentListView(generic.ObjectListView):
    queryset = PlantSourceDocument.objects.select_related('site', 'location')
    filterset = filtersets.PlantSourceDocumentFilterSet
    filterset_form = forms.PlantSourceDocumentFilterForm
    table = tables.PlantSourceDocumentTable


class PlantSourceDocumentView(generic.ObjectView):
    queryset = PlantSourceDocument.objects.select_related('site', 'location').prefetch_related(
        'sheets',
        'provenance_records',
    )
    template_name = 'netbox_power_plant/plantsourcedocument.html'


class PlantSourceDocumentEditView(generic.ObjectEditView):
    queryset = PlantSourceDocument.objects.all()
    form = forms.PlantSourceDocumentForm


class PlantSourceDocumentDeleteView(generic.ObjectDeleteView):
    queryset = PlantSourceDocument.objects.all()


class PlantSourceSheetListView(generic.ObjectListView):
    queryset = PlantSourceSheet.objects.select_related('source_document', 'source_document__site')
    filterset = filtersets.PlantSourceSheetFilterSet
    filterset_form = forms.PlantSourceSheetFilterForm
    table = tables.PlantSourceSheetTable


class PlantSourceSheetView(generic.ObjectView):
    queryset = PlantSourceSheet.objects.select_related('source_document', 'source_document__site').prefetch_related(
        'layers',
        'provenance_records',
    )
    template_name = 'netbox_power_plant/plantsourcesheet.html'


class PlantSourceSheetEditView(generic.ObjectEditView):
    queryset = PlantSourceSheet.objects.all()
    form = forms.PlantSourceSheetForm


class PlantSourceSheetDeleteView(generic.ObjectDeleteView):
    queryset = PlantSourceSheet.objects.all()


class PlantSourceLayerListView(generic.ObjectListView):
    queryset = PlantSourceLayer.objects.select_related(
        'source_sheet',
        'source_sheet__source_document',
    )
    filterset = filtersets.PlantSourceLayerFilterSet
    filterset_form = forms.PlantSourceLayerFilterForm
    table = tables.PlantSourceLayerTable


class PlantSourceLayerView(generic.ObjectView):
    queryset = PlantSourceLayer.objects.select_related(
        'source_sheet',
        'source_sheet__source_document',
    ).prefetch_related('provenance_records')
    template_name = 'netbox_power_plant/plantsourcelayer.html'


class PlantSourceLayerEditView(generic.ObjectEditView):
    queryset = PlantSourceLayer.objects.all()
    form = forms.PlantSourceLayerForm


class PlantSourceLayerDeleteView(generic.ObjectDeleteView):
    queryset = PlantSourceLayer.objects.all()


class PlantProvenanceListView(generic.ObjectListView):
    queryset = PlantProvenance.objects.select_related(
        'assigned_object_type',
        'source_document',
        'source_sheet',
        'source_layer',
    )
    filterset = filtersets.PlantProvenanceFilterSet
    filterset_form = forms.PlantProvenanceFilterForm
    table = tables.PlantProvenanceTable


class PlantProvenanceView(generic.ObjectView):
    queryset = PlantProvenance.objects.select_related(
        'assigned_object_type',
        'source_document',
        'source_sheet',
        'source_layer',
    )
    template_name = 'netbox_power_plant/plantprovenance.html'


class PlantProvenanceEditView(generic.ObjectEditView):
    queryset = PlantProvenance.objects.all()
    form = forms.PlantProvenanceForm


class PlantProvenanceDeleteView(generic.ObjectDeleteView):
    queryset = PlantProvenance.objects.all()


class PhysicalSpaceListView(generic.ObjectListView):
    queryset = PhysicalSpace.objects.select_related('site', 'location', 'spatial_frame', 'parent_space')
    filterset = filtersets.PhysicalSpaceFilterSet
    filterset_form = forms.PhysicalSpaceFilterForm
    table = tables.PhysicalSpaceTable


class PhysicalSpaceView(generic.ObjectView):
    queryset = PhysicalSpace.objects.select_related('site', 'location', 'spatial_frame', 'parent_space').prefetch_related(
        'child_spaces',
        'physical_elements',
    )
    template_name = 'netbox_power_plant/physicalspace.html'


class PhysicalSpaceEditView(generic.ObjectEditView):
    queryset = PhysicalSpace.objects.all()
    form = forms.PhysicalSpaceForm


class PhysicalSpaceDeleteView(generic.ObjectDeleteView):
    queryset = PhysicalSpace.objects.all()


class PhysicalElementTypeListView(generic.ObjectListView):
    queryset = PhysicalElementType.objects.all()
    filterset = filtersets.PhysicalElementTypeFilterSet
    filterset_form = forms.PhysicalElementTypeFilterForm
    table = tables.PhysicalElementTypeTable


class PhysicalElementTypeView(generic.ObjectView):
    queryset = PhysicalElementType.objects.prefetch_related('physical_elements')
    template_name = 'netbox_power_plant/physicalelementtype.html'


class PhysicalElementTypeEditView(generic.ObjectEditView):
    queryset = PhysicalElementType.objects.all()
    form = forms.PhysicalElementTypeForm


class PhysicalElementTypeDeleteView(generic.ObjectDeleteView):
    queryset = PhysicalElementType.objects.all()


class PhysicalElementListView(generic.ObjectListView):
    queryset = PhysicalElement.objects.select_related('element_type', 'site', 'location', 'physical_space')
    filterset = filtersets.PhysicalElementFilterSet
    filterset_form = forms.PhysicalElementFilterForm
    table = tables.PhysicalElementTable


class PhysicalElementView(generic.ObjectView):
    queryset = PhysicalElement.objects.select_related(
        'element_type',
        'site',
        'location',
        'physical_space',
    ).prefetch_related('object_bindings')
    template_name = 'netbox_power_plant/physicalelement.html'


class PhysicalElementEditView(generic.ObjectEditView):
    queryset = PhysicalElement.objects.all()
    form = forms.PhysicalElementForm


class PhysicalElementDeleteView(generic.ObjectDeleteView):
    queryset = PhysicalElement.objects.all()


class PhysicalObjectBindingListView(generic.ObjectListView):
    queryset = PhysicalObjectBinding.objects.select_related(
        'physical_element',
        'spatial_placement',
        'spatial_placement__spatial_frame',
        'assigned_object_type',
    )
    filterset = filtersets.PhysicalObjectBindingFilterSet
    filterset_form = forms.PhysicalObjectBindingFilterForm
    table = tables.PhysicalObjectBindingTable


class PhysicalObjectBindingView(generic.ObjectView):
    queryset = PhysicalObjectBinding.objects.select_related(
        'physical_element',
        'spatial_placement',
        'spatial_placement__spatial_frame',
        'assigned_object_type',
    )
    template_name = 'netbox_power_plant/physicalobjectbinding.html'


class PhysicalObjectBindingEditView(generic.ObjectEditView):
    queryset = PhysicalObjectBinding.objects.all()
    form = forms.PhysicalObjectBindingForm


class PhysicalObjectBindingDeleteView(generic.ObjectDeleteView):
    queryset = PhysicalObjectBinding.objects.all()


class SpatialFrameListView(generic.ObjectListView):
    queryset = SpatialFrame.objects.select_related('site', 'location', 'parent_frame')
    filterset = filtersets.SpatialFrameFilterSet
    filterset_form = forms.SpatialFrameFilterForm
    table = tables.SpatialFrameTable


class SpatialFrameView(generic.ObjectView):
    queryset = SpatialFrame.objects.select_related('site', 'location', 'parent_frame').prefetch_related('placements')
    template_name = 'netbox_power_plant/spatialframe.html'


class SpatialFrameEditView(generic.ObjectEditView):
    queryset = SpatialFrame.objects.all()
    form = forms.SpatialFrameForm


class SpatialFrameDeleteView(generic.ObjectDeleteView):
    queryset = SpatialFrame.objects.all()


class SpatialPlacementListView(generic.ObjectListView):
    queryset = SpatialPlacement.objects.select_related(
        'spatial_frame', 'spatial_frame__site', 'spatial_frame__location', 'assigned_object_type'
    )
    filterset = filtersets.SpatialPlacementFilterSet
    filterset_form = forms.SpatialPlacementFilterForm
    table = tables.SpatialPlacementTable


class SpatialPlacementView(generic.ObjectView):
    queryset = SpatialPlacement.objects.select_related(
        'spatial_frame', 'spatial_frame__site', 'spatial_frame__location', 'assigned_object_type'
    )
    template_name = 'netbox_power_plant/spatialplacement.html'


class SpatialPlacementEditView(generic.ObjectEditView):
    queryset = SpatialPlacement.objects.all()
    form = forms.SpatialPlacementForm


class SpatialPlacementDeleteView(generic.ObjectDeleteView):
    queryset = SpatialPlacement.objects.all()


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
