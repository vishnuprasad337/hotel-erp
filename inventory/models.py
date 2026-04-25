from django.db import models

class ItemCategory(models.Model):
    name = models.CharField(max_length=100)
    def __str__(self): return self.name

class Vendor(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name

class InventoryItem(models.Model):
    category = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=30, default='piece')
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    cost_per_unit = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    vendor = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return self.name
    @property
    def is_low_stock(self): return self.current_stock <= self.minimum_stock
    @property
    def stock_value(self): return self.current_stock * self.cost_per_unit

class StockAdjustment(models.Model):
    TYPE = [('in','Stock In'),('out','Stock Out'),('adjust','Adjustment')]
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=10, choices=TYPE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    adjusted_by = models.ForeignKey('accounts.Staff', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class PurchaseOrder(models.Model):
    STATUS = [('pending','Pending'),('received','Received'),('cancelled','Cancelled')]
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    note = models.TextField(blank=True)
    ordered_by = models.ForeignKey('accounts.Staff', on_delete=models.SET_NULL, null=True)
    ordered_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return f"PO-{self.pk} ({self.vendor.name})"

class PurchaseItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    @property
    def subtotal(self): return self.quantity * self.unit_price
class LaundryService(models.Model):
    SERVICE_TYPE = [
        ('wash', 'Wash'),
        ('iron', 'Iron'),
        ('dry_clean', 'Dry Clean'),
        ('wash_iron', 'Wash + Iron'),
    ]

    name = models.CharField(max_length=100)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE)
    price_per_unit = models.DecimalField(max_digits=8, decimal_places=2)
    turnaround_hours = models.IntegerField(default=24)

    def __str__(self):
        return self.name
class LaundryOrder(models.Model):

    ORDER_TYPE = [
        ('guest_laundry', 'Guest Laundry'),
        ('room_linen', 'Room Linen Cleaning'),
        ('staff_uniform', 'Staff Uniform'),
    ]

    STATUS = [
        ('received', 'Received'),
        ('processing', 'Processing'),
        ('cleaning', 'Cleaning'),
        ('ready', 'Ready'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    room_number = models.CharField(max_length=20)
    
    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPE,
        default='room_linen'
    )

    guest_name = models.CharField(max_length=200, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS, default='received')

    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order_type} - {self.room_number}"
class LaundryOrderItem(models.Model):
    order = models.ForeignKey(LaundryOrder, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey(LaundryService, on_delete=models.CASCADE)

    item_name = models.CharField(max_length=200)  # shirt, bedsheet, towel etc
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    
    @property
    def subtotal(self):
        return self.quantity * self.unit_price
class LaundryStatusLog(models.Model):
    order = models.ForeignKey(LaundryOrder, on_delete=models.CASCADE, related_name='logs')
    status = models.CharField(max_length=20)
    note = models.CharField(max_length=255, blank=True)
    updated_by = models.ForeignKey('accounts.Staff', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)