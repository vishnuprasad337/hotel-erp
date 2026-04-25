from django.urls import path
from . import views

urlpatterns = [
    path("inventory/categories/", views.list_categories),
    path("inventory/add-category/", views.add_category),

    path("inventory/vendors/", views.list_vendors),
    path("inventory/add-vendor/", views.add_vendor),

    path("inventory/items/", views.list_inventory),
    path("inventory/add-item/", views.add_inventory_item),
    path("inventory/stock-adjust/", views.stock_adjust),

    path("purchase/create/", views.create_purchase_order),
    path("purchase/list/", views.list_purchase_orders),

    path("laundry/services/", views.list_laundry_services),
    path("laundry/add-service/", views.add_laundry_service),

    path("laundry/orders/", views.list_laundry_orders),
    path("laundry/create-order/", views.create_laundry_order),
    path("laundry/update-status/<int:pk>/", views.update_laundry_status),
]