from django.shortcuts import redirect
from django.contrib.auth import logout
from django.urls import resolve

class TenantSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            user_hotel = getattr(request.user, 'hotel', None)
            
            if user_hotel and user_hotel != request.tenant:
                logout(request)
                return redirect('hotel_login')

        response = self.get_response(request)
        return response

class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)