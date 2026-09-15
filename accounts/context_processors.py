from django.db import connection
from django_tenants.utils import schema_context
from .models import Hotel, HotelModule

def hotel_globals(request):
    """Injects `hotel` and `active_module_names` into every template context."""
    if not hasattr(request, 'tenant'):
        return {}

    tenant = connection.tenant
    if tenant.schema_name == 'public':
        return {}

    try:
        with schema_context('public'):
            hotel = Hotel.objects.select_related('subscription_plan').get(
                schema_name=tenant.schema_name
            )
    except Hotel.DoesNotExist:
        return {}

    with schema_context(tenant.schema_name):
        modules = HotelModule.objects.select_related('module').filter(
            hotel=hotel, is_enabled=True
        )
        active_module_names = set()
        for m in modules:
            name = m.module.name.lower().strip()
            active_module_names.add(name)
            active_module_names.add(name.replace(' ', '_'))
            active_module_names.add(name.replace(' ', ''))
            active_module_names.add(name.replace('-', '_'))

    return {
        'hotel': hotel,
        'active_module_names': list(active_module_names),
    }