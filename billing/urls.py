from django.urls import path
from . import views
from .api_views import (
    GuestFolioListAPIView, GuestFolioDetailAPIView,
    FolioChargeListAPIView, FolioChargeDetailAPIView,
    InvoiceListAPIView, InvoiceDetailAPIView,
    BillingPaymentListAPIView, BillingPaymentDetailAPIView,
    FolioByBookingAPIView,
)

urlpatterns = [
   
    path("api/billing/folio/",                               views.get_or_create_folio,   name="billing_folio"),
  
   
    path("api/billing/add-charge/",                          views.add_charge,             name="billing_add_charge"),
    path("api/billing/delete-charge/<int:charge_id>/",       views.delete_charge,          name="billing_delete_charge"),

    
    path("api/billing/payments/",                            views.add_payment,            name="billing_add_payment"),

   
    path("api/billing/invoice/generate/",                    views.generate_invoice,       name="billing_generate_invoice"),

  
    path("api/billing/invoice/list/",                        views.list_invoices,          name="billing_invoice_list"),

   
    path("api/billing/invoice/<int:invoice_id>/",            views.get_invoice,            name="get_invoice"),

    
    path("api/billing/invoice/<int:invoice_id>/send-email/", views.send_invoice_email,     name="billing_send_invoice_email"),

   
    path("api/billing/summary/",                             views.billing_summary,        name="billing_summary"),


    path("billing/folios/",                          GuestFolioListAPIView.as_view(),        name="billing-folio-list"),
    path("billing/folios/<int:pk>/",                 GuestFolioDetailAPIView.as_view(),      name="billing-folio-detail"),
    path("billing/folios/booking/<int:booking_id>/", FolioByBookingAPIView.as_view(),        name="billing-folio-by-booking"),

    path("billing/folios/<int:folio_id>/charges/",   FolioChargeListAPIView.as_view(),       name="billing-charge-list"),
    path("billing/charges/<int:pk>/",                FolioChargeDetailAPIView.as_view(),     name="billing-charge-detail"),

    path("billing/invoices/",                        InvoiceListAPIView.as_view(),           name="billing-invoice-list"),
    path("billing/invoices/<int:pk>/",               InvoiceDetailAPIView.as_view(),         name="billing-invoice-detail"),

    path("billing/payments/",                        BillingPaymentListAPIView.as_view(),    name="billing-payment-list"),
    path("billing/payments/<int:pk>/",               BillingPaymentDetailAPIView.as_view(),  name="billing-payment-detail"),
]