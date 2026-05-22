from netbox_power_plant.models import InstantiationRun, PowerArchitectureTemplate
from netbox_power_plant.services.reference_templates import REFERENCE_TEMPLATE_SLUGS, seed_reference_templates
from netbox_power_plant.services.templates import apply_existing_instantiation_run, instantiate_template


def list_reference_templates(*, seed_missing=False, active_only=True):
    """
    Return the built-in operator templates in their documented order.

    This is intentionally permission-neutral service code. Views and API endpoints
    can do authorization before calling it.
    """
    if seed_missing:
        seed_reference_templates_if_missing()

    queryset = PowerArchitectureTemplate.objects.filter(slug__in=REFERENCE_TEMPLATE_SLUGS)
    if active_only:
        queryset = queryset.filter(is_active=True)

    templates_by_slug = {template.slug: template for template in queryset}
    return tuple(templates_by_slug[slug] for slug in REFERENCE_TEMPLATE_SLUGS if slug in templates_by_slug)


def seed_reference_templates_if_missing():
    existing_slugs = set(
        PowerArchitectureTemplate.objects.filter(slug__in=REFERENCE_TEMPLATE_SLUGS).values_list("slug", flat=True)
    )
    if existing_slugs == set(REFERENCE_TEMPLATE_SLUGS):
        return list_reference_templates()
    return seed_reference_templates()


def build_template_dry_run_preview(power_system, template, *, context=None):
    template = _resolve_template(template)
    return instantiate_template(power_system, template, context=context, apply=False)


def apply_reviewed_instantiation_run(run):
    run = _resolve_run(run)
    return apply_existing_instantiation_run(run)


def build_and_apply_template(power_system, template, *, context=None):
    template = _resolve_template(template)
    return instantiate_template(power_system, template, context=context, apply=True)


def build_instantiation_result_payload(result):
    return {
        "run": {
            "id": result.run.pk,
            "name": result.run.name,
            "slug": result.run.slug,
            "status": result.run.status,
            "dry_run": result.run.dry_run,
            "power_system_id": result.run.power_system_id,
            "template_id": result.run.template_id,
            "artifact_count": result.run.artifact_count,
            "context": result.run.context,
        },
        "summary": result.summary,
        "artifacts": result.artifact_summaries,
    }


def _resolve_template(template):
    if isinstance(template, PowerArchitectureTemplate):
        return template
    lookup = {"pk": template} if isinstance(template, int) else {"slug": template}
    return PowerArchitectureTemplate.objects.get(**lookup)


def _resolve_run(run):
    if isinstance(run, InstantiationRun):
        return run
    return InstantiationRun.objects.get(pk=run)
