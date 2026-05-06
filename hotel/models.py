from django.db import models
from django.utils import timezone
from accounts.models import Hotel
from accounts.models import Department,Staff
from django.contrib.auth import get_user_model
from pms.models import Room,RoomUnit
from customers.models import Client 

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




class ShiftTemplate(models.Model):
   
    SHIFT_NAME_CHOICES = [
        ("Morning", "Morning"),
        ("Evening", "Evening"),
        ("Night", "Night"),
        ("Custom", "Custom"),
    ]

    hotel       = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name='shift_templates')
    shift_name  = models.CharField(max_length=50, choices=SHIFT_NAME_CHOICES)
    start_time  = models.TimeField()
    end_time    = models.TimeField()
    color       = models.CharField(max_length=10, default='#1a65f5') 
    is_active   = models.BooleanField(default=True)

    class Meta:
        unique_together = ('hotel', 'shift_name')

    def __str__(self):
        return f"{self.hotel} - {self.shift_name} ({self.start_time}–{self.end_time})"


class Shift(models.Model):
    SHIFT_CHOICES = [
        ("Morning", "Morning"),
        ("Evening", "Evening"),
        ("Night", "Night"),
        ("Custom", "Custom"),
    ]

    hotel      = models.ForeignKey(Hotel, on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    staff      = models.ForeignKey(Staff, on_delete=models.CASCADE)

    shift        = models.CharField(max_length=20, choices=SHIFT_CHOICES)
    date         = models.DateField()

   
    custom_name  = models.CharField(max_length=50, blank=True, null=True)
    custom_start = models.TimeField(blank=True, null=True)
    custom_end   = models.TimeField(blank=True, null=True)
    custom_color = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        unique_together = ('staff', 'date')

    def __str__(self):
        return f"{self.staff.name} - {self.shift} on {self.date}"

    def get_start_time(self):
       
        if self.custom_start:
            return self.custom_start
        try:
            tpl = ShiftTemplate.objects.get(hotel=self.hotel, shift_name=self.shift)
            return tpl.start_time
        except ShiftTemplate.DoesNotExist:
            defaults = {
                'Morning': '06:00', 'Evening': '14:00', 'Night': '22:00'
            }
            from datetime import time
            t = defaults.get(self.shift, '00:00').split(':')
            return time(int(t[0]), int(t[1]))

    def get_end_time(self):
        
        if self.custom_end:
            return self.custom_end
        try:
            tpl = ShiftTemplate.objects.get(hotel=self.hotel, shift_name=self.shift)
            return tpl.end_time
        except ShiftTemplate.DoesNotExist:
            defaults = {
                'Morning': '14:00', 'Evening': '22:00', 'Night': '06:00'
            }
            from datetime import time
            t = defaults.get(self.shift, '00:00').split(':')
            return time(int(t[0]), int(t[1]))
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
    tenant = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True)
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

from django.db.models import JSONField

class Payroll(models.Model):
    PAID_STATUS_CHOICES = [
        ("Unpaid", "Unpaid"),
        ("Paid",   "Paid"),
        ("Hold",   "Hold"),
    ]

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)

    month = models.IntegerField()
    year  = models.IntegerField()

    basic_salary    = models.DecimalField(max_digits=10, decimal_places=2)
    overtime_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    bonus           = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    incentive       = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    deductions      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pf_amount       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    esi_amount      = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_deduction   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loan_deduction  = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    net_salary = models.DecimalField(max_digits=10, decimal_places=2)
    custom_earnings   = JSONField(default=list, blank=True)
    custom_deductions = JSONField(default=list, blank=True)
    notes        = models.TextField(blank=True, default="")
    generated_at = models.DateTimeField(auto_now_add=True)
    paid_status  = models.CharField(
        max_length=10,
        choices=PAID_STATUS_CHOICES,
        default="Unpaid"
    )
    paid_at      = models.DateTimeField(null=True, blank=True)
    paid_by      = models.ForeignKey(
        Staff, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="payrolls_processed"
    )

    class Meta:
        unique_together = ("staff", "month", "year")

    def __str__(self):
        return f"{self.staff.name} - {self.month}/{self.year}"

    def total_earnings(self):
        return (
            self.basic_salary
            + self.overtime_amount
            + self.bonus
            + self.incentive
        )

    def total_deductions(self):
        return (
            self.deductions
            + self.pf_amount
            + self.esi_amount
            + self.tax_deduction
            + self.loan_deduction
        )

    def computed_net(self):
        return self.total_earnings() - self.total_deductions()