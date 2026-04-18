from django.core.management.base import BaseCommand
from customers.models import Client  

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        tenant = Client.objects.create(
            schema_name='public',
            name='Public',
            domain_url='hotel-erp-10.onrender.com'
        )
        self.stdout.write("Tenant created successfully")