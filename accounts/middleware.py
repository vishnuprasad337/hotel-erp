from django.shortcuts import redirect
from django.contrib.auth import logout
from django.db import connection

class TenantSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.user.is_superuser:
            user_hotel = getattr(request.user, 'hotel', None)
            current_tenant = connection.tenant

            if user_hotel is not None:
                
                if user_hotel.schema_name != current_tenant.schema_name:
                    logout(request)
                    return redirect('hotel_login')

        return self.get_response(request)