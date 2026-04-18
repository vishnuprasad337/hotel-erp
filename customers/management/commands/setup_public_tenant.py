from django.core.management.base import BaseCommand
from customers.models import Client, Domain
import os

class Command(BaseCommand):
    help = 'Creates the public tenant for the main domain'

    def handle(self, *args, **kwargs):
        domain_name = os.environ.get('PUBLIC_DOMAIN', 'hotel-erp-12.onrender.com')

        if Client.objects.filter(schema_name='public').exists():
            client = Client.objects.get(schema_name='public')
            self.stdout.write(f'Public tenant already exists.')
            # Update domain if changed
            Domain.objects.get_or_create(
                domain=domain_name,
                defaults={'tenant': client, 'is_primary': True}
            )
            self.stdout.write(f'Domain ensured: {domain_name}')
            return

        tenant = Client(schema_name='public', name='Public')
        tenant.save()

        Domain.objects.create(
            domain=domain_name,
            tenant=tenant,
            is_primary=True
        )
        self.stdout.write(f'Public tenant and domain created: {domain_name}')