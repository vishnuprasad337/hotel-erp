from django.db import connection
from customers.models import Client

class PathTenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info.lstrip('/')
        parts = path.split('/')
        first_segment = parts[0] if parts else ''

        public_routes = [
            'admin-login', 'register', 'admin',
            'static', 'media', 'superadmin',
            'approve', 'reject', 'amenities',
            'add-amenity', 'delete-amenity',
            'get-amenities', ''
        ]

        if first_segment in public_routes:
            connection.set_schema_to_public()
            request.tenant = None
            request.schema_name = 'public'
        else:
            try:
                client = Client.objects.get(schema_name=first_segment)
                connection.set_tenant(client)
                request.tenant = client
                request.schema_name = first_segment
                # Strip schema prefix from path
                # /test1/dashboard/ → /dashboard/
                new_path = '/' + '/'.join(parts[1:])
                if not new_path.endswith('/'):
                    new_path += '/'
                request.path_info = new_path
                request.path = new_path
            except Client.DoesNotExist:
                connection.set_schema_to_public()
                request.tenant = None
                request.schema_name = 'public'

        response = self.get_response(request)
        return response