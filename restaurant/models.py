from django.db import models

class MenuCategory(models.Model):
    name = models.CharField(max_length=100)
    order = models.IntegerField(default=0)
    def __str__(self): return self.name
    class Meta: ordering = ['order']

class MenuItem(models.Model):
    category = models.ForeignKey(MenuCategory, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    tax_percent = models.DecimalField(max_digits=4, decimal_places=1, default=5.0)
    is_available = models.BooleanField(default=True)
    is_veg = models.BooleanField(default=True)
    image = models.ImageField(upload_to='menu/', null=True, blank=True)
    def __str__(self): return self.name

class Table(models.Model):
    number = models.CharField(max_length=10, unique=True)
    capacity = models.IntegerField(default=4)
    is_occupied = models.BooleanField(default=False)
    def __str__(self): return f"Table {self.number}"
class TableReservation(models.Model):
    STATUS = [
        ('reserved', 'Reserved'),
        ('seated', 'Seated'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    table = models.ForeignKey(Table, on_delete=models.CASCADE)
    guest_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)

    reservation_time = models.DateTimeField()
    guests_count = models.IntegerField(default=1)

    status = models.CharField(max_length=20, choices=STATUS, default='reserved')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.guest_name} - {self.table.number}"
    
class RestaurantOrder(models.Model):
    ORDER_TYPE = [('dine_in','Dine-In'),('room_service','Room Service'),('takeaway','Takeaway')]
    STATUS = [('pending','Pending'),('preparing','Preparing'),('served','Served'),('cancelled','Cancelled')]
    order_number = models.CharField(max_length=20, unique=True)
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE, default='dine_in')
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True)
    room = models.ForeignKey('pms.Room', on_delete=models.SET_NULL, null=True, blank=True)
    booking = models.ForeignKey(
    "pms.Booking",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="restaurant_orders"
)
    reservation = models.ForeignKey(
    TableReservation,
    on_delete=models.SET_NULL,
    null=True,
    blank=True
)
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    charge_to_room = models.BooleanField(default=False)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    served_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    staff = models.ForeignKey('accounts.Staff', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.order_number:
            import uuid
            self.order_number = f"ORD-{str(uuid.uuid4().int)[:6]}"
        super().save(*args, **kwargs)
    def __str__(self): return self.order_number

class OrderItem(models.Model):
    order = models.ForeignKey(RestaurantOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    note = models.CharField(max_length=100, blank=True)
    def __str__(self): return f"{self.quantity}x {self.item.name}"
    @property
    def subtotal(self): return self.unit_price * self.quantity
