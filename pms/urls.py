from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
urlpatterns =[
    
   
   
    
   path('rooms/', room_page, name='room_page'),
    path('api/add-room/', add_room, name='add_room'),
    path('api/room/<int:room_id>/', get_room, name='get_room'),
    path('api/rooms/', get_rooms, name='get_rooms'),
    path("frontoffice/", frontoffice_dashboard, name="frontoffice_dashboard"),
    
    # FROND END DASHBOARDS
      path("api/create-booking/", create_booking, name="create_booking"),

    # 🔹 Check-In / Check-Out
    path("api/check-in/", check_in, name="check_in"),
    path("api/check-out/", check_out, name="check_out"),

    
    path("api/assign-housekeeping-task/", assign_housekeeping_task, name="assign_housekeeping_task"),
    path("api/get-bill/", get_bill, name="get_bill"),
    path("get-bookings/", get_bookings, name="get_bookings"),
     path("add-guest/", add_guest, name="add_guest"),
    path("get-guests/", get_guests, name="get_guests"),
    path('guest-portal/<str:schema>/<str:token>/', guest_portal),
    path('guest/<str:schema>/<str:token>/order/', guest_place_order, name='guest_place_order'),
     path('guest/<str:schema>/<str:token>/orders/',guest_orders, name='guest_orders'),
     path('guest/<str:schema>/<uuid:token>/laundry/',
    guest_create_laundry_order, name='guest_create_laundry_order' ),
   path("guest/requests/<str:schema>/<str:token>/", guest_view_requests, name="guest_view_requests"),
  path("guest/request/<str:schema>/<str:token>/", guest_create_request, name="guest_create_request"),
path("fd/requests/", fd_view_requests, name="fd_view_requests"),
path("fd/requests/update/", fd_update_request, name="fd_update_request"),
path("api/update-room-status/", update_room_status),
path('api/guests/<int:guest_id>/photos/', get_guest_photos),
]
    
    
