from django.db import models
from django.utils import timezone
from accounts.models import Hotel
from accounts.models import Department,Staff
from django.contrib.auth import get_user_model
from pms.models import Room,RoomUnit

User = get_user_model()


class Amenity(models.Model):
    AMENITY_TYPE = (
        ("default", "Default"),
        ("premium", "Premium"),
    )

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    amenity_type = models.CharField(max_length=10, choices=AMENITY_TYPE, default="default")

    def __str__(self):
        return self.name





class Task(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="tasks")
    room = models.ForeignKey(Room, on_delete=models.CASCADE, null=True, blank=True)
    room_unit = models.ForeignKey(RoomUnit, on_delete=models.CASCADE, null=True, blank=True)

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    status = models.CharField(max_length=50, default="Pending")

    def __str__(self):
        return f"{self.title} - {self.staff.name}"


class Shift(models.Model):
    SHIFT_CHOICES = [
        ("Morning", "Morning"),
        ("Evening", "Evening"),
        ("Night", "Night"),
    ]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)

    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES)
    date = models.DateField()

    class Meta:
        unique_together = ('staff', 'date')

    def __str__(self):
        return f"{self.staff.name} - {self.shift}"





class InventoryItem(models.Model):
    CATEGORY_CHOICES = [
        ('cleaning', 'Cleaning Supplies'),
        ('linen', 'Linen & Towels'),
        ('amenities', 'Guest Amenities'),
        ('equipment', 'Equipment'),
    ]

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='inventory_items')
    room = models.ForeignKey(RoomUnit, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_items')

    updated_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_updated"
    )

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='cleaning')
    quantity = models.IntegerField(default=0)
    unit = models.CharField(max_length=50, default='pieces')
    reorder_level = models.IntegerField(default=10)

    description = models.TextField(blank=True, null=True)

    assigned_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_inventory'
    )

    assigned_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        room_info = f" - Room {self.room.room_number}" if self.room else ""
        return f"{self.name} - {self.quantity} {self.unit}{room_info}"


class Attendance(models.Model):
    STATUS_CHOICES = [
        ("Present", "Present"),
        ("Absent", "Absent"),
        ("Late", "Late"),
        ("Half Day", "Half Day"),
    ]

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)

    date = models.DateField()

    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Present")

    overtime_hours = models.FloatField(default=0)

    is_corrected = models.BooleanField(default=False)
    correction_note = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("staff", "date")


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)

    from_date = models.DateField()
    to_date = models.DateField()

    reason = models.TextField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")

    applied_at = models.DateTimeField(auto_now_add=True)

    action_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leave_actions"
    )

    action_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.staff.name} - {self.status}"


class Payroll(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)

    month = models.IntegerField()
    year = models.IntegerField()

    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    overtime_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    net_salary = models.DecimalField(max_digits=10, decimal_places=2)

    generated_at = models.DateTimeField(auto_now_add=True)
    paid_status = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.staff.name} - {self.month}/{self.year}"