import uuid
from django.db import models
from django.utils import timezone
class GuestFolio(models.Model):
    STATUS_CHOICES = [
        ("open",   "Open"),
        ("closed", "Closed"),
    ]
 
    
    booking = models.OneToOneField(
        "pms.Booking",
        on_delete=models.CASCADE,
        related_name="folio",
    )
    status     = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes      = models.TextField(blank=True)
 
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Guest Folio"
 
    def __str__(self):
        return f"Folio #{self.pk} — {self.booking}"
 
    
    @property
    def total_charges(self):
        return sum(
            (c.amount + c.tax_amount) for c in self.charges.all()
        )
 
    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments.all())
 
    @property
    def balance_due(self):
        return self.total_charges - self.total_paid
 
    @property
    def is_settled(self):
        return self.balance_due <= 0
 
class FolioCharge(models.Model):
    CHARGE_TYPE_CHOICES = [
        ("room",        "Room"),
        ("restaurant",  "Restaurant"),
        ("laundry",     "Laundry"),
        ("spa",         "Spa"),
        ("minibar",     "Minibar"),
        ("transport",   "Transport"),
        ("extra",       "Extra / Miscellaneous"),
    ]
 
    folio       = models.ForeignKey(GuestFolio, on_delete=models.CASCADE, related_name="charges")
    charge_type = models.CharField(max_length=30, choices=CHARGE_TYPE_CHOICES, default="room")
    description = models.CharField(max_length=200)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount  = models.DecimalField(max_digits=8,  decimal_places=2, default=0)
    date        = models.DateField(default=timezone.now)
 
  
    added_by = models.ForeignKey(
        "accounts.Staff",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="posted_charges",
    )
 
    class Meta:
        ordering = ["date", "pk"]
        verbose_name = "Folio Charge"
 
    def __str__(self):
        return f"{self.get_charge_type_display()}: {self.description} — ₹{self.amount}"
 
    @property
    def total(self):
        return self.amount + self.tax_amount
class Invoice(models.Model):
    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("paid",     "Paid"),
        ("partial",  "Partially Paid"),
        ("refunded", "Refunded"),
    ]
 
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)
    folio          = models.OneToOneField(GuestFolio, on_delete=models.CASCADE, related_name="invoice")
 
    subtotal    = models.DecimalField(max_digits=12, decimal_places=2)
    tax_total   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount    = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2)
 
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    generated_by = models.ForeignKey(
        'accounts.Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_invoices'
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    notes        = models.TextField(blank=True)
 
    class Meta:
        ordering = ["-generated_at"]
        verbose_name = "Invoice"
 
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            year = timezone.now().year
            # Short unique suffix derived from UUID
            suffix = str(uuid.uuid4().int)[:5]
            self.invoice_number = f"INV-{year}-{suffix}"
        super().save(*args, **kwargs)
 
    def __str__(self):
        return self.invoice_number
class BillingPayment(models.Model):

    METHOD_CHOICES = [
        ("cash",     "Cash"),
        ("card",     "Credit / Debit Card"),
        ("upi",      "UPI"),
        ("online",   "Online Transfer"),
        ("ota",      "OTA Prepaid"),
        ("cheque",   "Cheque"),
        ("razorpay", "Razorpay"),
    ]

    STATUS_CHOICES = [
        ("pending",  "Pending"),
        ("paid",     "Paid"),
        ("refunded", "Refunded"),
    ]

    # ── payment source: one must be set, not both ──
    folio = models.ForeignKey(
        GuestFolio,
        on_delete=models.CASCADE,
        related_name="payments",
        null=True, blank=True       
    )
    order = models.OneToOneField(
        "restaurant.RestaurantOrder",
        on_delete=models.CASCADE,
        related_name="payment",
        null=True, blank=True       
    )

    amount           = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    method           = models.CharField(max_length=20, choices=METHOD_CHOICES, null=True, blank=True)
    payment_status   = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    reference_number = models.CharField(max_length=100, blank=True)
    note             = models.CharField(max_length=200, blank=True)
    received_at      = models.DateTimeField(default=timezone.now)
    paid_at          = models.DateTimeField(null=True, blank=True)

    received_by = models.ForeignKey(
        "accounts.Staff",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="received_payments",
    )

    class Meta:
        ordering = ["received_at"]
        verbose_name = "Billing Payment"

    def __str__(self):
        if self.folio:
            return f"{self.get_method_display()}: ₹{self.amount} (Folio #{self.folio.pk})"
        if self.order:
            return f"{self.get_method_display()}: ₹{self.amount} (Order #{self.order.order_number})"
        return f"{self.get_method_display()}: ₹{self.amount}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.folio and not self.order:
            raise ValidationError("Payment must be linked to either a folio or an order.")
        if self.folio and self.order:
            raise ValidationError("Payment cannot be linked to both a folio and an order.")