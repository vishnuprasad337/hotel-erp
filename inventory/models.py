from django.db import models

from django.utils import timezone



class ItemCategory(models.Model):
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name




class Vendor(models.Model):
    name           = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    phone          = models.CharField(max_length=20)
    email          = models.EmailField(blank=True)
    address        = models.TextField(blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name




class InventoryItem(models.Model):
    UNIT_CHOICES = [
        ('piece',  'Piece'),
        ('kg',     'Kilogram'),
        ('litre',  'Litre'),
        ('box',    'Box'),
        ('roll',   'Roll'),
        ('set',    'Set'),
        ('bottle', 'Bottle'),
        ('bag',    'Bag'),
        ('metre',  'Metre'),
    ]

    category      = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True)

    
    department    = models.ForeignKey(
        'accounts.Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inventory_items'
    )

    name          = models.CharField(max_length=200)
    unit          = models.CharField(max_length=30, choices=UNIT_CHOICES, default='piece')
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    vendor        = models.ForeignKey(Vendor, on_delete=models.SET_NULL, null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock

    @property
    def stock_value(self):
        return self.current_stock * self.cost_per_unit



class StockAdjustment(models.Model):
    TYPE = [
        ('in',     'Stock In'),
        ('out',    'Stock Out'),
        ('adjust', 'Adjustment'),
    ]

    item            = models.ForeignKey(
        InventoryItem, on_delete=models.CASCADE, related_name='adjustments'
    )
    adjustment_type = models.CharField(max_length=10, choices=TYPE)
    quantity        = models.DecimalField(max_digits=10, decimal_places=2)
    note            = models.CharField(max_length=200, blank=True)
    adjusted_by     = models.ForeignKey(
        'accounts.Staff', on_delete=models.SET_NULL, null=True
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.adjustment_type} | {self.item.name} | {self.quantity}"



class PurchaseOrder(models.Model):
    STATUS = [
        ('pending',   'Pending'),
        ('approved',  'Approved'),
        ('received',  'Received'),
        ('cancelled', 'Cancelled'),
    ]

    vendor       = models.ForeignKey(Vendor, on_delete=models.CASCADE)

   
    department   = models.ForeignKey(
        'accounts.Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='purchase_orders'
    )

    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status       = models.CharField(max_length=20, choices=STATUS, default='pending')
    note         = models.TextField(blank=True)
    ordered_by   = models.ForeignKey(
        'accounts.Staff', on_delete=models.SET_NULL,
        null=True, related_name='purchase_orders'
    )
    approved_by  = models.ForeignKey(
        'accounts.Staff', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_pos'
    )
    ordered_at   = models.DateTimeField(auto_now_add=True)
    received_at  = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"PO-{self.pk} ({self.vendor.name})"


class PurchaseItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name='items'
    )
    item      = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity  = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price




class ExpenseCategory(models.Model):
   
    name   = models.CharField(max_length=100, unique=True)
    budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text="Monthly budget cap for this category"
    )

    def __str__(self):
        return self.name


class Expense(models.Model):
    
    SOURCE = [
        ('purchase_order', 'Purchase Order'),
        ('direct',         'Direct Purchase'),
        ('manual',         'Manual Entry'),
         ('laundry',        'Laundry Payment'),
    ]

    department       = models.ForeignKey(
        'accounts.Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='expenses'
    )
    maintenance_log = models.OneToOneField(
    'MaintenanceLog',
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    related_name='expense'
)
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    purchase_order   = models.OneToOneField(
        PurchaseOrder, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='expense'
    )
    inventory_item   = models.ForeignKey(
        InventoryItem, on_delete=models.SET_NULL, null=True, blank=True
    )
    
    source           = models.CharField(max_length=20, choices=SOURCE, default='manual')
    amount           = models.DecimalField(max_digits=12, decimal_places=2)
    description      = models.CharField(max_length=255, blank=True)
    expense_date     = models.DateField(default=timezone.now)
    recorded_by      = models.ForeignKey(
        'accounts.Staff', on_delete=models.SET_NULL, null=True
    )
    created_at       = models.DateTimeField(auto_now_add=True)
   
    linen_batch = models.ForeignKey(
    'inventory.HotelLinenBatch', 
    on_delete=models.SET_NULL,
    null=True, blank=True,
    related_name='expenses',
)

    def __str__(self):
        return f"{self.department} | {self.expense_category} | {self.amount}"







from django.db import models
from django.utils import timezone

from inventory.models import Vendor         
from pms.models import Room, RoomUnit      

class AssetCategory(models.Model):
    
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class HotelAsset(models.Model):

    STATUS = [
        ('active',      'Active'),
        ('maintenance', 'Under Maintenance'),
        ('inactive',     'Inactive'),  
        ('disposed',    'Disposed'),  
    ]

    
    name           = models.CharField(max_length=200)
    asset_category = models.ForeignKey(
        AssetCategory, on_delete=models.SET_NULL, null=True
    )
    serial_number  = models.CharField(max_length=100, blank=True)

   

    room_unit = models.ForeignKey(
        RoomUnit,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assets',
        help_text="Specific room unit the asset is installed in (e.g. Room 101)"
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assets',
        help_text="Room type when the asset is shared across a type, not a single unit"
    )
    area = models.CharField(
        max_length=200, blank=True,
        help_text="Non-room location: Lobby, Pool House, Laundry Room, Parking Lot …"
    )

   
    department = models.ForeignKey(
        'accounts.Department',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assets'
    )

   
    status = models.CharField(max_length=20, choices=STATUS, default='active')

   
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vendor        = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True
    )

    
    warranty_end     = models.DateField(null=True, blank=True)
    next_maintenance = models.DateField(null=True, blank=True)

   
    assigned_to = models.ForeignKey(
        'accounts.Staff',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_assets'
    )

    notes      = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

 

    @property
    def location_display(self):
       
        if self.room_unit_id:
            return f"Room {self.room_unit.room_number}"
        if self.room_id:
            return f"{self.room.room_type} (no specific unit)"
        return self.area or "—"

    @property
    def is_warranty_active(self):
        if not self.warranty_end:
            return False
        return self.warranty_end >= timezone.now().date()

    @property
    def maintenance_due(self):
        if not self.next_maintenance:
            return False
        return self.next_maintenance <= timezone.now().date()

    def __str__(self):
        return f"{self.name} ({self.location_display})"

    class Meta:
        ordering = ['name']


class MaintenanceLog(models.Model):

    TYPE = [
        ('scheduled', 'Scheduled'),
        ('reactive', 'Reactive / Breakdown'),
        ('preventive', 'Preventive'),
        ('inspection', 'Inspection'),
        ('deep_service', 'Deep Service'),
        ('calibration', 'Calibration'),
        ('cleaning', 'Cleaning'),
        ('replacement', 'Part Replacement'),
    ]

    PRIORITY = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('critical', 'Critical'),
    ]

    STATUS = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    asset = models.ForeignKey(
        HotelAsset,
        on_delete=models.CASCADE,
        related_name='maintenance_logs',
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        'accounts.Department',   
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='maintenance_logs'
    )

    custom_asset = models.CharField(max_length=255, blank=True)

    location = models.CharField(max_length=255, blank=True)

    maintenance_type = models.CharField(
        max_length=30,
        choices=TYPE,
        default='scheduled'
    )

    priority = models.CharField(
        max_length=20,
        choices=PRIORITY,
        default='low'
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS,
        default='completed'
    )

    description = models.TextField()

    performed_by = models.CharField(max_length=200, blank=True)

    performed_at = models.DateTimeField(default=timezone.now)

    duration = models.CharField(max_length=100, blank=True)

    labour_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    parts_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    next_due = models.DateField(null=True, blank=True)

    parts_replaced = models.TextField(blank=True)

    notes = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        'accounts.Staff',
        on_delete=models.SET_NULL,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_asset()

    def _sync_asset(self):

        if not self.asset_id:
            return

        asset_updates = {}

        if self.next_due:
            asset_updates['next_maintenance'] = self.next_due

        if self.maintenance_type == 'reactive':
            asset_updates['status'] = 'maintenance'

        elif self.next_due:
            asset_updates['status'] = 'active'

        if asset_updates:
            HotelAsset.objects.filter(
                pk=self.asset_id
            ).update(**asset_updates)

        asset = HotelAsset.objects.filter(
            pk=self.asset_id
        ).only('room_unit_id').first()

        if not (asset and asset.room_unit_id):
            return

        if self.maintenance_type == 'reactive':

            RoomUnit.objects.filter(
                pk=asset.room_unit_id
            ).update(status='Maintenance')

        elif asset_updates.get('status') == 'active':

            RoomUnit.objects.filter(
                pk=asset.room_unit_id,
                status='Maintenance'
            ).update(status='Available')

    def __str__(self):
        return f"{self.asset.name if self.asset else self.custom_asset} | {self.maintenance_type} | {self.performed_at.date()}"

    class Meta:
        ordering = ['-performed_at']
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
from pms.models import Booking

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
    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    order_type = models.CharField(
        max_length=20,
        choices=ORDER_TYPE,
        default='room_linen'
    )

    guest_name = models.CharField(max_length=200, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS, default='received')

    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    delivered_by = models.ForeignKey(
        'accounts.Staff',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='delivered_orders')
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

class LinenMissingReason(models.Model):
    label      = models.CharField(max_length=100, unique=True)
    is_active  = models.BooleanField(default=True)
    order      = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'label']

    def __str__(self):
        return self.label

from decimal import Decimal
class HotelLinenBatch(models.Model):
    STATUS = [
        ('dispatched', 'Dispatched'),
        ('partial',    'Partially Received'),
        ('received',   'Received'),
    ]

    dispatched_by   = models.ForeignKey(
                        'accounts.Staff',
                        on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='linen_dispatched'
                      )
    sent_to_laundry = models.CharField(max_length=200, blank=True)
    laundry_contact = models.CharField(max_length=100, blank=True)
    laundry_phone   = models.CharField(max_length=20,  blank=True)
    note            = models.TextField(blank=True)
    status          = models.CharField(max_length=20, choices=STATUS, default='dispatched')
    received_by     = models.ForeignKey(
                        'accounts.Staff',
                        on_delete=models.SET_NULL,
                        null=True, blank=True,
                        related_name='linen_received'
                      )
    dispatched_at   = models.DateTimeField(auto_now_add=True)
    received_at     = models.DateTimeField(null=True, blank=True)
    expected_return_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-dispatched_at']

    def __str__(self):
        return f"Batch LB{str(self.id).zfill(3)} — {self.sent_to_laundry or 'Unknown'}"

    @property
    def total_pieces(self):
        return sum(i.quantity for i in self.items.all())

    @property
    def received_pieces(self):
        return sum(i.received_quantity for i in self.items.all())

    @property
    def missing_cost(self):
        return sum(i.missing_cost for i in self.items.all())
    
    @property
    def total_cost(self):
        return sum(i.quantity * i.item_price for i in self.items.all())

    @property
    def missing_cost(self):
        return sum(i.missing_cost for i in self.items.all())

    @property
    def payable_amount(self):
        missing = self.missing_cost
        if missing == 0:
         return self.total_cost
        return self.total_cost - missing

class HotelLinenBatchItem(models.Model):
    batch             = models.ForeignKey(HotelLinenBatch, on_delete=models.CASCADE, related_name='items')
    item_label        = models.CharField(max_length=100)
    quantity          = models.PositiveIntegerField(default=1)
    item_price        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    received_at       = models.DateTimeField(null=True, blank=True)
    damaged_quantity  = models.PositiveIntegerField(default=0)
    missing_quantity  = models.PositiveIntegerField(default=0)
    missing_reason    = models.ForeignKey(
                            LinenMissingReason,
                            on_delete=models.SET_NULL,
                            null=True, blank=True,
                            related_name='items'
                        )
    missing_note      = models.TextField(blank=True)
    received_quantity = models.PositiveIntegerField(default=0)

    @property
    def received(self):
        return self.received_quantity >= self.quantity

    @property
    def is_partial(self):
        return 0 < self.received_quantity < self.quantity

    @property
    def missing(self):
        return self.quantity - self.received_quantity

    @property
    def missing_cost(self):
        return Decimal(str(self.missing)) * self.item_price

    def __str__(self):
        return f"{self.item_label} x{self.quantity}"