from django.urls import path
from . import views

urlpatterns = [

   
    path('api/restaurant/categories/',         views.list_menu_categories,    name='list_menu_categories'),
    path('api/restaurant/categories/add/',     views.add_menu_category,       name='add_menu_category'),
    path('api/restaurant/categories/<int:pk>/delete/', views.delete_menu_category, name='delete_menu_category'),

    
    path('api/restaurant/items/add/',          views.add_menu_item,           name='add_menu_item'),
    path('api/restaurant/items/<int:pk>/update/', views.update_menu_item,     name='update_menu_item'),
    path('api/restaurant/items/<int:pk>/delete/', views.delete_menu_item,     name='delete_menu_item'),
    path('api/restaurant/items/<int:pk>/toggle/', views.toggle_item_availability, name='toggle_item_availability'),

    
    path('api/restaurant/tables/',             views.list_tables,             name='list_tables'),
    path('api/restaurant/tables/add/',         views.add_table,               name='add_table'),
    path('api/restaurant/tables/<int:pk>/delete/', views.delete_table,        name='delete_table'),

   
    path('api/restaurant/orders/',             views.order_list,              name='restaurant_order_list'),
    path('api/restaurant/orders/active/',      views.active_orders,           name='active_orders'),
    path('api/restaurant/orders/create/',      views.create_order,            name='create_order'),
    path('api/restaurant/orders/<int:pk>/status/', views.update_order_status, name='update_order_status'),

    
    path('api/restaurant/stats/',              views.restaurant_stats,        name='restaurant_stats'),

    
    path('api/restaurant/occupied-rooms/',     views.occupied_rooms,          name='occupied_rooms'),
    path("api/reservation/create/", views.create_reservation, name="create_reservation"),
    path("api/reservations/", views.list_reservations, name="list_reservations"),
    path("api/reservations/<int:reservation_id>/update/", views.update_reservation, name="update_reservation"),
    path("api/reservations/<int:reservation_id>/delete/", views.delete_reservation, name="delete_reservation"),

]