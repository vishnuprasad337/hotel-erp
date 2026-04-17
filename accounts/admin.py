
from django.contrib import admin

from django.contrib import admin
from django.shortcuts import redirect
from .models import Hotel

@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('hotel_name', 'email', 'city', 'is_approved')
    actions = ['approve_hotels']

    def approve_hotels(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, "Selected hotels approved successfully!")