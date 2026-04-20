from django.core.management.base import BaseCommand
from customers.models import Client, Domain  
class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        tenant, _ = Client.objects.get_or_create(
            schema_name='public',
            defaults={'name': 'Public'}
        )
        Domain.objects.get_or_create(
            domain='hotel-erp-16.onrender.com',
            defaults={'tenant': tenant, 'is_primary': True}
        )
        self.stdout.write("Tenant created successfully!")