from django.urls import path
from . import views
from .api_views import (
    ItemCategoryListAPIView, ItemCategoryDetailAPIView,
    VendorListAPIView, VendorDetailAPIView,
    InventoryItemListAPIView, InventoryItemDetailAPIView, InventoryByDepartmentAPIView,
    StockAdjustmentListAPIView,
    PurchaseOrderListAPIView, PurchaseOrderDetailAPIView, PurchaseOrderItemsAPIView,
    ExpenseCategoryListAPIView,
    ExpenseListAPIView, ExpenseDetailAPIView, ExpenseSummaryAPIView,
    AssetCategoryListAPIView,
    HotelAssetListAPIView, HotelAssetDetailAPIView,
    MaintenanceLogListAPIView, MaintenanceLogDetailAPIView,
    LaundryServiceListAPIView,
    LaundryOrderListAPIView, LaundryOrderDetailAPIView,
)

urlpatterns = [
    path("categories/",            views.list_categories,       name="list_categories"),
    path("categories/add/",        views.add_category,          name="add_category"),
 
    # ── Vendors ────────────────────────────────────────────────
    path("vendors/",               views.list_vendors,          name="list_vendors"),
    path("vendors/add/",           views.add_vendor,            name="add_vendor"),
 
    # ── Inventory Items ────────────────────────────────────────
    path("items/",                 views.list_inventory,        name="list_inventory"),
    path("items/add/",             views.add_inventory_item,    name="add_inventory_item"),
    path("items/by-department/",   views.inventory_by_department, name="inventory_by_department"),
 
    # ── Stock Adjustments ──────────────────────────────────────
    path("adjustments/",           views.list_stock_adjustments, name="list_stock_adjustments"),
    path("adjustments/add/",       views.stock_adjust,          name="stock_adjust"),
    path("departments/",       views.departments,          name="departments"),
 
    # ── Purchase Orders ────────────────────────────────────────
    path("po/",                    views.list_purchase_orders,  name="list_purchase_orders"),
    path("po/create/",             views.create_purchase_order, name="create_purchase_order"),
    path("po/<int:po_id>/status/", views.update_po_status,      name="update_po_status"),
    path('inventory/modal-data/', views.get_modal_data, name='inventory_modal_data'),
    path('inventory/meta/', views.inventory_meta, name='inventory_meta'),
    # ── Expense Categories ─────────────────────────────────────
    path("expense-categories/",      views.list_expense_categories, name="list_expense_categories"),
    path("expense-categories/add/",  views.add_expense_category,    name="add_expense_category"),
 
    # ── Expenses ───────────────────────────────────────────────
    path("expenses/",              views.list_expenses,         name="list_expenses"),
    path("expenses/add/",          views.add_expense,           name="add_expense"),
    path("expenses/summary/",      views.expense_summary,       name="expense_summary"),
 
    # ── Asset Categories ───────────────────────────────────────
    path("asset-categories/",      views.list_asset_categories, name="list_asset_categories"),
    path("asset-categories/add/",  views.add_asset_category,    name="add_asset_category"),
 
    # ── Hotel Assets ───────────────────────────────────────────
    path("assets/",                          views.list_assets,          name="list_assets"),
    path("assets/add/",                      views.add_asset,            name="add_asset"),
    path("assets/<int:asset_id>/status/",    views.update_asset_status,  name="update_asset_status"),
 
    # ── Maintenance Logs ───────────────────────────────────────
    path("maintenance/",           views.list_maintenance_logs, name="list_maintenance_logs"),
    path("maintenance/add/",       views.add_maintenance_log,   name="add_maintenance_log"),
    path(
    "maintenance/<int:log_id>/update-status/",
    views.update_maintenance_status,
    name="update_maintenance_status"
),

path(
    "maintenance/<int:log_id>/delete/",
    views.delete_maintenance_log,
    name="delete_maintenance_log"
),
    path("laundry/services/", views.list_laundry_services),
    path("laundry/add-service/", views.add_laundry_service),

    path("laundry/orders/", views.list_laundry_orders),
    path("laundry/create-order/", views.create_laundry_order),
   path('laundry/update-status/<int:order_id>/', views.update_laundry_status),
     path('inventory/items/<int:pk>/update/', views.update_inventory_item),
   path('inventory/items/<int:pk>/delete/', views.delete_inventory_item),
   
   path(
    "expenses/<int:expense_id>/delete/",
    views.delete_expense,
    name="delete_expense"
),
   
   # PO items
   path('inventory/po/<int:pk>/items/', views.get_po_items),
   
   # Assets
   
   # Asset categories
   path('inventory/asset-categories/add/', views.add_asset_category),
   
   # Maintenance
   
   # Expense categories
   path('inventory/expense-categories/add/', views.add_expense_category),
  
path(
    "maintenance/<int:log_id>/edit/",
    views.edit_maintenance_log,
    name="edit_maintenance_log"
),
 path("inv/categories/",                      ItemCategoryListAPIView.as_view(),       name="inv-category-list"),
    path("inv/categories/<int:pk>/",             ItemCategoryDetailAPIView.as_view(),     name="inv-category-detail"),

    path("api/vendors/",                         VendorListAPIView.as_view(),             name="inv-vendor-list"),
    path("inv/vendors/<int:pk>/",                VendorDetailAPIView.as_view(),           name="inv-vendor-detail"),

    path("inv/items/",                           InventoryItemListAPIView.as_view(),      name="inv-item-list"),
    path("inv/items/<int:pk>/",                  InventoryItemDetailAPIView.as_view(),    name="inv-item-detail"),
    path("inv/items/by-department/",             InventoryByDepartmentAPIView.as_view(),  name="inv-item-by-dept"),

    path("inv/adjustments/",                     StockAdjustmentListAPIView.as_view(),    name="inv-adjustment-list"),

    path("inv/po/",                              PurchaseOrderListAPIView.as_view(),      name="inv-po-list"),
    path("inv/po/<int:pk>/",                     PurchaseOrderDetailAPIView.as_view(),    name="inv-po-detail"),
    path("inv/po/<int:pk>/items/",               PurchaseOrderItemsAPIView.as_view(),     name="inv-po-items"),

    path("inv/expense-categories/",              ExpenseCategoryListAPIView.as_view(),    name="inv-expense-cat-list"),

    path("inv/expenses/",                        ExpenseListAPIView.as_view(),            name="inv-expense-list"),
    path("inv/expenses/<int:pk>/",               ExpenseDetailAPIView.as_view(),          name="inv-expense-detail"),
    path("inv/expenses/summary/",                ExpenseSummaryAPIView.as_view(),         name="inv-expense-summary"),

    path("inv/asset-categories/",               AssetCategoryListAPIView.as_view(),      name="inv-asset-cat-list"),

    path("inv/assets/",                          HotelAssetListAPIView.as_view(),         name="inv-asset-list"),
    path("inv/assets/<int:pk>/",                 HotelAssetDetailAPIView.as_view(),       name="inv-asset-detail"),

    path("inv/maintenance/",                     MaintenanceLogListAPIView.as_view(),     name="inv-maintenance-list"),
    path("inv/maintenance/<int:pk>/",            MaintenanceLogDetailAPIView.as_view(),   name="inv-maintenance-detail"),

    path("inv/laundry/services/",                LaundryServiceListAPIView.as_view(),     name="inv-laundry-service-list"),

    path("inv/laundry/orders/",                  LaundryOrderListAPIView.as_view(),       name="inv-laundry-order-list"),
    path("inv/laundry/orders/<int:pk>/",         LaundryOrderDetailAPIView.as_view(),     name="inv-laundry-order-detail"),  
]