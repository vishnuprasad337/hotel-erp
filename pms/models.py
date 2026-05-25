from django.db import models
from accounts.models import Staff,Hotel

class Property(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Room(models.Model):
    ROOM_TYPES = [
        ('Single', 'Single'),
        ('Double', 'Double'),
        ('Deluxe', 'Deluxe'),
        ('Suite', 'Suite'),
        ('Custom', 'Custom'),
    ]

    room_type = models.CharField(max_length=20, choices=ROOM_TYPES)
    custom_room_type = models.CharField(max_length=100, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)

    max_adults = models.IntegerField(default=2)
    max_children = models.IntegerField(default=0)

    description = models.TextField(blank=True)

    amenities = models.ManyToManyField(Property, blank=True)

    extra_adult_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    extra_child_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
   
    def display_type(self):
         return self.custom_room_type if self.custom_room_type else self.room_type

    def total_units(self):
        return self.units.count()

    def available_units(self):
        return self.units.filter(status="Available").count()

    def __str__(self):
        return self.room_type


class RoomUnit(models.Model):
    STATUS_CHOICES = [
        ("Available", "Available"),
        ("Occupied", "Occupied"),
        ("Dirty", "Dirty"),
        ("Reserved", "Reserved"),
        ("Cleaning", "Cleaning"),
        ("Maintenance", "Maintenance"),
    ]

    room = models.ForeignKey(Room, related_name="units", on_delete=models.CASCADE)
    room_number = models.CharField(max_length=20, unique=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Available")

    def __str__(self):
        return self.room_number


class RoomImage(models.Model):
    room = models.ForeignKey(Room, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="rooms/")
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.room.room_type} Image"

class Guest(models.Model):
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, db_index=True)

    email = models.EmailField(blank=True, null=True)
    nationality = models.CharField(max_length=50, blank=True, null=True)

    id_type = models.CharField(max_length=50, blank=True, null=True)
    id_photo = models.ImageField(upload_to="guest_ids/", blank=True, null=True)
    id_number = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name
class GuestIDPhoto(models.Model):
    guest = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,
        related_name="id_photos"
    )
    image = models.ImageField(upload_to="guest_ids/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.guest.full_name} - ID Photo"
class Booking(models.Model):

    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("checked_in", "Checked In"),
        ("checked_out", "Checked Out"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
    ]

   
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, null=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    room_unit = models.ForeignKey(RoomUnit, on_delete=models.SET_NULL, null=True, blank=True)

    created_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_created"
    )

   
    booking_code = models.CharField(max_length=20, unique=True, blank=True, null=True)
    guest_token = models.UUIDField(null=True, blank=True)

    check_in = models.DateField()
    check_out = models.DateField()
    checked_in_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_checked_in"
    )

    checked_out_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_checked_out"
    )
    actual_check_in = models.DateTimeField(null=True, blank=True)
    actual_check_out = models.DateTimeField(null=True, blank=True)

    guests_count = models.PositiveIntegerField(default=1)
    adults = models.PositiveIntegerField(default=1)
    children = models.PositiveIntegerField(default=0)

    special_requests = models.TextField(blank=True, null=True)

   
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="confirmed")

    # audit fields
    source = models.CharField(max_length=50, blank=True, null=True)  # walk-in / online / booking.com
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.guest.full_name} - {self.room.room_type}"
class Payment(models.Model):
    PAYMENT_METHODS = [
        ("Cash", "Cash"),
        ("Card", "Card"),
        ("UPI", "UPI"),
    ]

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE)

    room_charges = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, null=True, blank=True)
    payment_status = models.CharField(max_length=20, default="pending")

    paid_at = models.DateTimeField(null=True, blank=True)
    collected_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"Payment - {self.booking.id}"