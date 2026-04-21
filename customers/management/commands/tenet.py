from django.core.management.base import BaseCommand
from customers.models import Client, Domain

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        domain_name = "eerp.onrender.com"

        tenant = Client.objects.get(schema_name="public")

        domain, created = Domain.objects.get_or_create(
            domain=domain_name,
            tenant=tenant,
            defaults={"is_primary": True}
        )

        if not created:
            domain.tenant = tenant
            domain.is_primary = True
            domain.save()

        self.stdout.write(self.style.SUCCESS("Public domain configured successfully"))