from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views
from .api_views import (
    RoomListAPIView,
    RoomDetailAPIView,
    RoomUnitStatusAPIView,
    GuestListAPIView,
    GuestDetailAPIView,
    GuestPhotosAPIView,
    BookingListAPIView,
    BookingFullDetailAPIView,
    CheckInAPIView,
    CheckOutAPIView,
    BillAPIView,
    BookingFullListAPIView,
    RoomWithBookingsAPIView
)
urlpatterns =[
    
   
   
    
   path('rooms/', room_page, name='room_page'),
    path('api/add-room/', add_room, name='add_room'),
    path('api/room/<int:room_id>/', get_room, name='get_room'),
    path('api/rooms/', get_rooms, name='get_rooms'),
    path("frontoffice/", frontoffice_dashboard, name="frontoffice_dashboard"),
    path('rooms-status/', room_status, name='room_status'),
    path('room-status-all/', room_status, name='room_status_alt'),
    # FROND END DASHBOARDS
      path("api/create-booking/", create_booking, name="create_booking"),

    # 🔹 Check-In / Check-Out
    path('api/room-price/', get_price_for_dates, name='get_price_for_dates'),
    path("api/check-in/", check_in, name="check_in"),
    path("api/check-out/", check_out, name="check_out"),
    path('api/seasonal-rates/',                    get_seasonal_rates,    name='get_seasonal_rates'),
     path('api/seasonal-rates/add/',                add_seasonal_rate,     name='add_seasonal_rate'),
    path('api/seasonal-rates/<int:rate_id>/delete/', delete_seasonal_rate, name='delete_seasonal_rate'),
    path("api/record-payment/",record_payment,name="record_payment"),
    path('api/room-types/', get_room_types, name='get_room_types'),
    path("api/assign-housekeeping-task/", assign_housekeeping_task, name="assign_housekeeping_task"),
    path("api/get-bill/", get_bill, name="get_bill"),
    path("get-bookings/", get_bookings, name="get_bookings"),
     path("add-guest/", add_guest, name="add_guest"),
    path("get-guests/", get_guests, name="get_guests"),
    path('guest-portal/<str:schema>/<str:token>/', guest_portal),
    path('guest/<str:schema>/<str:token>/order/', guest_place_order, name='guest_place_order'),
     path('guest/<str:schema>/<str:token>/orders/',guest_orders, name='guest_orders'),
       path('guest/<str:schema>/<str:token>/order/<int:order_id>/cancel/', guest_cancel_order, name='guest_cancel_order'),
     path('guest/<str:schema>/<uuid:token>/laundry/',
    guest_create_laundry_order, name='guest_create_laundry_order' ),
   path("guest/requests/<str:schema>/<str:token>/", guest_view_requests, name="guest_view_requests"),
  path("guest/request/<str:schema>/<str:token>/", guest_create_request, name="guest_create_request"),
path("fd/requests/", fd_view_requests, name="fd_view_requests"),
path("fd/requests/update/", fd_update_request, name="fd_update_request"),
path("api/update-room-status/", update_room_status),
path('api/guest/<int:guest_id>/photos/', get_guest_photos, name='guest_photos'),
path('guest/<str:schema>/<str:token>/tables/available/', guest_available_tables, name='guest_available_tables'),
path('guest/<str:schema>/<str:token>/tables/book/', guest_book_table, name='guest_book_table'),
path('guest/<str:schema>/<str:token>/tables/<int:reservation_id>/cancel/', guest_cancel_table_reservation, name='guest_cancel_table_reservation'),
path("guest/<str:schema>/<str:token>/tables/", guest_list_table_reservations, name="guest_list_table_reservations"),
path("guest-portal/<str:schema>/<str:token>/self-check-in/", guest_self_check_in, name="guest_self_check_in"),
path('guest-portal/<str:schema>/<str:token>/checkout-summary/', guest_checkout_summary, name='guest_checkout_summary'),
path('guest-portal/<str:schema>/<str:token>/self-check-out/',guest_self_check_out, name='guest_self_check_out'),
path('pms/rooms/edit/', edit_room, name='edit_room'),
path('pms/rooms/<int:room_id>/delete/', delete_room, name='delete_room'),
path('bookings/new/', new_booking, name='new_booking'),
path('bookings/', get_bookings_page, name='get_bookings_page'),
path("api/billing/delete-payment/<int:payment_id>/", delete_payment, name="billing_delete_payment"),
path('api/housekeeping-staff/', get_housekeeping_staff, name='get_housekeeping_staff'),
path("pms/rooms/",                        RoomListAPIView.as_view(),           name="api-room-list"),
path("pms/rooms/<int:pk>/",               RoomDetailAPIView.as_view(),         name="api-room-detail"),
path("pms/rooms/unit/status/",            RoomUnitStatusAPIView.as_view(),     name="api-room-unit-status"),

path("pms/guests/",                       GuestListAPIView.as_view(),          name="api-guest-list"),
path("pms/guests/<int:pk>/",              GuestDetailAPIView.as_view(),        name="api-guest-detail"),
path("pms/guests/<int:guest_id>/photos/", GuestPhotosAPIView.as_view(),        name="api-guest-photos"),

path("pms/bookings/",                     BookingListAPIView.as_view(),        name="api-booking-list"),
path("pms/bookings/<int:pk>/full/",       BookingFullDetailAPIView.as_view(),  name="api-booking-full-detail"),
path("pms/bookings/check-in/",            CheckInAPIView.as_view(),            name="api-check-in"),
path("pms/bookings/check-out/",           CheckOutAPIView.as_view(),           name="api-check-out"),
path("pms/bookings/bill/",                BillAPIView.as_view(),               name="api-bill"),
path(
    "pms/bookings/full/",
    BookingFullListAPIView.as_view(),
    name="api-booking-full-list"
),
path(
    "pms/rooms/bookings/",
    RoomWithBookingsAPIView.as_view(),
    name="api-room-bookings",
),
]
    
    
