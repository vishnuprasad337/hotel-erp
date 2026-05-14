from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta
class Hotel(models.Model):
    
    tenant = models.OneToOneField(
        "customers.Client",
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    schema_name = models.CharField(max_length=100, null=True, blank=True)
    hotel_name = models.CharField(max_length=100, unique=True)
    email = models.EmailField(null=True, blank=True)
    owner_name = models.CharField(max_length=100)
    address = models.TextField(max_length=200)
    city = models.CharField(max_length=100)
    property_type = models.CharField(max_length=50, default="Hotel")

    image = models.ImageField(upload_to="property_images/", null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    amenities = models.TextField(blank=True, null=True)

    is_approved = models.BooleanField(default=False)
    is_subscribed = models.BooleanField(default=False)
    is_setup_complete = models.BooleanField(default=False)
    logo = models.ImageField(upload_to='hotel_logos/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    subscription_plan = models.ForeignKey(
    'SubscriptionPlan',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='hotels'
)

    SUBSCRIPTION_STATUS = [
        ('inactive',  'Inactive'),
        ('trial',     'Trial'),
        ('active',    'Active'),
        ('expired',   'Expired'),
        ('suspended', 'Suspended'),
    ]
    subscription_status = models.CharField(
        max_length=20,
        choices=SUBSCRIPTION_STATUS,
        default='inactive'
    )
    subscription_expiry = models.DateField(null=True, blank=True)
    trial_eligible    = models.BooleanField(default=True)
    is_on_trial       = models.BooleanField(default=False)
    trial_start       = models.DateTimeField(null=True, blank=True)
    trial_end         = models.DateTimeField(null=True, blank=True)
    trial_days        = models.PositiveIntegerField(default=14)   
    trial_granted_by  = models.CharField(max_length=100, blank=True, null=True)
    @property
    def trial_is_active(self):
        
        return (
            self.is_on_trial
            and self.trial_end is not None
            and timezone.now() < self.trial_end
        )
 
    @property
    def trial_has_expired(self):
        return (
            self.is_on_trial
            and self.trial_end is not None
            and timezone.now() >= self.trial_end
        )
 
    def start_trial(self, granted_by="system", days=None):
       
        if not self.trial_eligible:
            raise ValueError("This hotel is not eligible for a trial.")
        if self.is_on_trial or self.subscription_status in ('active', 'trial'):
            raise ValueError("Hotel already has an active subscription or trial.")
 
        days = days or self.trial_days
        self.is_on_trial          = True
        self.trial_start          = timezone.now()
        self.trial_end            = timezone.now() + timedelta(days=days)
        self.trial_granted_by     = granted_by
        self.subscription_status  = 'trial'
        self.is_subscribed        = True
        self.save(update_fields=[
            'is_on_trial', 'trial_start', 'trial_end',
            'trial_granted_by', 'subscription_status', 'is_subscribed'
        ])
 
    def end_trial(self, reason="expired"):
       
        self.is_on_trial         = False
        self.subscription_status = 'expired'
        self.is_subscribed       = False
        self.save(update_fields=['is_on_trial', 'subscription_status', 'is_subscribed'])
 
    def __str__(self):
        return self.hotel_name

class Department(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name




class User(AbstractUser):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, null=True, blank=True)

    role = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)

    phone = models.CharField(max_length=15, blank=True, null=True)

    is_active_staff = models.BooleanField(default=True)

    def __str__(self):
        return self.username



class Permission(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    role = models.ForeignKey(Department, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)


class Amenity(models.Model):
    name        = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_core     = models.BooleanField(default=False)  

    def __str__(self):
        return self.name


class SubscriptionPlan(models.Model):
    name    = models.CharField(max_length=50, unique=True)
    price   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    modules = models.ManyToManyField(Amenity, blank=True, related_name='plans')
    is_trial_plan   = models.BooleanField(default=False)
    trial_days      = models.PositiveIntegerField(default=14)
    tagline       = models.CharField(max_length=200, blank=True, null=True) 
    def __str__(self):
        return self.name


class PlanPayment(models.Model):
    STATUS_CHOICES = (
        ('pending',   'Pending'),
        ('paid',      'Paid'),
        ('overdue',   'Overdue'),
        ('cancelled', 'Cancelled'),
    )
    hotel          = models.ForeignKey('Hotel', on_delete=models.CASCADE, related_name='payments')
    plan           = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    amount         = models.DecimalField(max_digits=10, decimal_places=2)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date       = models.DateField()
    paid_date      = models.DateField(null=True, blank=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    notes          = models.TextField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.hotel} — {self.plan} — {self.status}"


class HotelModule(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)
    module = models.ForeignKey(Amenity, on_delete=models.CASCADE)

    is_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.hotel.hotel_name} - {self.module.name}"


class Staff(models.Model):
    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="staffs"
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile"
    )

  
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, blank=True, null=True)

    
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    
    employee_id = models.CharField(max_length=20, blank=True, null=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    joining_date = models.DateField(default=timezone.now)

    is_active = models.BooleanField(default=True)
    is_available = models.BooleanField(default=True)

   
    photo = models.ImageField(upload_to="staff_photos/", null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('hotel', 'employee_id') 

    def save(self, *args, **kwargs):
        if not self.employee_id:
            last_staff = Staff.objects.filter(
                hotel=self.hotel
            ).order_by('id').last()

            if last_staff and last_staff.employee_id:
                try:
                    last_id = int(last_staff.employee_id.split('-')[-1])
                    new_id = last_id + 1
                except:
                    new_id = 1
            else:
                new_id = 1

            self.employee_id = f"EMP-{new_id:03d}"

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.employee_id})"