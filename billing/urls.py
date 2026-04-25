from django.urls import path
from . import views

urlpatterns = [
    path("api/billing/folio/", views.get_or_create_folio, name="billing_folio"),
    path("api/billing/add-charge/", views.add_charge, name="billing_add_charge"),
    path("api/billing/delete-charge/<int:charge_id>/", views.delete_charge, name="billing_delete_charge"),

    path("api/billing/payments/", views.add_payment, name="billing_add_payment"),

    path("api/billing/invoice/generate/", views.generate_invoice, name="billing_generate_invoice"),
    path("api/billing/invoice/<int:invoice_id>/", views.get_invoice, name="billing_get_invoice"),
    path("api/billing/invoice/list/", views.list_invoices, name="billing_invoice_list"),
   
    path("api/billing/invoice/<int:invoice_id>/send-email/", views.send_invoice_email, name="billing_send_invoice_email"),

    path("api/billing/summary/", views.billing_summary, name="billing_summary"),
    
]