from django.core.management.base import BaseCommand

from netbox_power_plant.services.reference_templates import seed_reference_templates


class Command(BaseCommand):
    help = 'Create or update built-in NetBox Power Plant reference templates.'

    def handle(self, *args, **options):
        templates = seed_reference_templates()
        self.stdout.write(self.style.SUCCESS(f'Seeded {len(templates)} power reference templates.'))
