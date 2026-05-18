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

class PayrollLineItem(models.Model):
    TYPE_CHOICES = [
        ('earning',   'Earning'),
        ('deduction', 'Deduction'),
    ]
    SOURCE_CHOICES = [
      
        ('basic',     'Basic Salary'),
        ('overtime',  'Overtime'),
        ('bonus',     'Bonus'),
        ('incentive', 'Incentive'),
        ('hra',       'HRA'),
        ('da',        'DA'),
        ('ta',        'Travel Allowance'),
        ('medical',   'Medical Allowance'),
        ('special',   'Special Allowance'),
        ('custom',    'Custom'),
       
        ('leave',     'Leave/Absent Deduction'),
        ('pf',        'PF (Employee)'),
        ('esi',       'ESI (Employee)'),
        ('pt',        'Professional Tax'),
        ('tax',       'Tax/TDS'),
        ('loan',      'Loan Deduction'),
        ('advance',   'Salary Advance'),
        ('uniform',   'Uniform Deduction'),
    ]

    payroll     = models.ForeignKey(
        Payroll, on_delete=models.CASCADE, related_name='line_items'
    )
    line_type   = models.CharField(max_length=10, choices=TYPE_CHOICES)   
    source      = models.CharField(max_length=30, choices=SOURCE_CHOICES) 
    label       = models.CharField(max_length=100)   
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    pct         = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)  
    pct_base    = models.CharField(max_length=20, blank=True, default='') 
    is_auto     = models.BooleanField(default=False)  
    note        = models.CharField(max_length=200, blank=True, default='')
    order       = models.PositiveSmallIntegerField(default=0)  

    class Meta:
        ordering = ['line_type', 'order', 'id']

    def __str__(self):
        sign = '+' if self.line_type == 'earning' else '-'
        return f"{sign}₹{self.amount} — {self.label} ({self.payroll.staff.name})"
class EmployeeFinancialAccount(models.Model):
    staff = models.OneToOneField(Staff, on_delete=models.CASCADE)

    pf_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    esi_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    loan_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    advance_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    gratuity_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    updated_at = models.DateTimeField(auto_now=True)
class FinalSettlement(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)

    last_working_day = models.DateField()

    pending_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    leave_encashment = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    gratuity = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    pf_payable = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    final_amount = models.DecimalField(max_digits=10, decimal_places=2)

    settled_at = models.DateTimeField(null=True, blank=True)
from django.db import models
from django.conf import settings
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Message Thread
# ─────────────────────────────────────────────────────────────────────────────

class MessageThread(models.Model):
    THREAD_TYPES = [
        ('direct',       'Direct Message'),
        ('group',        'Group Chat'),
        ('department',   'Department Channel'),
        ('announcement', 'Announcement Board'),
    ]

    hotel       = models.ForeignKey('accounts.Hotel', on_delete=models.CASCADE, related_name='message_threads')
    thread_type = models.CharField(max_length=15, choices=THREAD_TYPES, default='direct')
    name        = models.CharField(max_length=150, blank=True)
    description = models.CharField(max_length=300, blank=True)
    avatar      = models.ImageField(upload_to='thread_avatars/', null=True, blank=True)
    department  = models.ForeignKey('accounts.Department', on_delete=models.CASCADE, null=True, blank=True, related_name='message_channel')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, through='ThreadParticipant', related_name='message_threads')
    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_threads')
    is_archived = models.BooleanField(default=False)
    is_locked   = models.BooleanField(default=False)
    max_members = models.PositiveIntegerField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def last_message(self):
        return self.messages.filter(is_deleted=False).order_by('-created_at').first()

    def unread_count_for(self, user):
        from datetime import datetime, timezone as dt_timezone
        membership = self.memberships.filter(user=user).first()
        cursor = membership.last_read_at if membership else None
        if cursor is None:
            cursor = datetime.min.replace(tzinfo=dt_timezone.utc)
        return self.messages.filter(created_at__gt=cursor).exclude(sender=user).count()

    def display_name(self, for_user=None):
        if self.thread_type == 'department':
            return f"# {self.department.name}" if self.department else self.name
        if self.thread_type == 'announcement':
            return f" {self.name}"
        if self.thread_type == 'group':
            return self.name
        if self.thread_type == 'direct' and for_user:
            other = self.participants.exclude(id=for_user.id).first()
            return other.get_full_name() or other.username if other else '(empty)'
        return self.name or f"Thread {self.id}"

    def can_post(self, user):
        if self.is_locked or self.is_archived:
            return False
        if self.thread_type == 'announcement':
            return self.memberships.filter(user=user, is_admin=True).exists()
        return self.memberships.filter(user=user).exists()

    def __str__(self):
        return f"[{self.hotel.hotel_name}] {self.get_thread_type_display()}: {self.name or self.id}"
class ThreadParticipant(models.Model):
    
    thread        = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name='memberships')
    user          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_admin      = models.BooleanField(default=False)
    is_muted      = models.BooleanField(default=False)
    is_pinned_chat = models.BooleanField(default=False)
    last_read_at  = models.DateTimeField(null=True, blank=True)
    joined_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('thread', 'user')

    def mark_read(self):
        self.last_read_at = timezone.now()
        self.save(update_fields=['last_read_at'])

    def __str__(self):
        flags = []
        if self.is_admin:       flags.append('admin')
        if self.is_muted:       flags.append('muted')
        if self.is_pinned_chat: flags.append('pinned')
        tag = f" [{', '.join(flags)}]" if flags else ''
        return f"{self.user.username} in thread {self.thread_id}{tag}"


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Message
# ─────────────────────────────────────────────────────────────────────────────

class Message(models.Model):

    PRIORITY_CHOICES = [
        ('normal', 'Normal'),
        ('urgent', 'Urgent'),          
        ('info',   'Info'),           
    ]

    thread   = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name='messages')
    sender   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_messages'
    )

    # ── Content ────────────────────────────────────────────────────────────
    body        = models.TextField(blank=True)           # blank allowed if attachment present
    priority    = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')

    # Reply / forward
    reply_to    = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='replies'
    )
    forwarded_from = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='forwards'
    )

    # ── State flags ────────────────────────────────────────────────────────
    is_edited       = models.BooleanField(default=False)
    is_deleted      = models.BooleanField(default=False)   
    is_system_msg   = models.BooleanField(default=False)  

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def soft_delete(self):
        self.is_deleted     = True
        self.body           = ''
        self.save(update_fields=['is_deleted', 'body', 'updated_at'])
        self.attachments.all().delete()   # remove files when message is deleted

    def __str__(self):
        preview = self.body[:50] + ('…' if len(self.body) > 50 else '')
        return f"[T{self.thread_id}] {self.sender}: {preview}"



class MessageAttachment(models.Model):
    
    FILE_TYPES = [
        ('image',    'Image'),
        ('video',    'Video'),
        ('audio',    'Audio'),
        ('pdf',      'PDF'),
        ('document', 'Document'),
        ('other',    'Other'),
    ]

    IMAGE_EXTS    = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}
    VIDEO_EXTS    = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    AUDIO_EXTS    = {'.mp3', '.wav', '.ogg', '.m4a'}
    DOC_EXTS      = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv'}

    message   = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='attachments')
    file      = models.FileField(upload_to='message_attachments/%Y/%m/')
    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)   # bytes
    file_type = models.CharField(max_length=10, choices=FILE_TYPES, default='other')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        import os
        ext = os.path.splitext(self.file_name)[1].lower()
        if ext in self.IMAGE_EXTS:
            self.file_type = 'image'
        elif ext in self.VIDEO_EXTS:
            self.file_type = 'video'
        elif ext in self.AUDIO_EXTS:
            self.file_type = 'audio'
        elif ext == '.pdf':
            self.file_type = 'pdf'
        elif ext in self.DOC_EXTS:
            self.file_type = 'document'
        else:
            self.file_type = 'other'
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.file_name} ({self.file_type}) — msg {self.message_id}"



class MessageReadStatus(models.Model):
    
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_statuses')
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('message', 'user')

    def __str__(self):
        return f"{self.user.username} ✓ msg {self.message_id}"




class Reaction(models.Model):
    EMOJI_CHOICES = [
        ('👍', 'Thumbs Up'),
        ('❤️',  'Heart'),
        ('😂', 'Laugh'),
        ('😮', 'Wow'),
        ('😢', 'Sad'),
        ('🙏', 'Pray'),
        ('🔥', 'Fire'),
        ('✅', 'Check'),
    ]
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='reactions')
    user    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    emoji   = models.CharField(max_length=10, choices=EMOJI_CHOICES)

    class Meta:
        unique_together = ('message', 'user', 'emoji')

    def __str__(self):
        return f"{self.user.username} {self.emoji} → msg {self.message_id}"



class PinnedMessage(models.Model):
    
    thread     = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name='pinned_messages')
    message    = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='pins')
    pinned_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pinned_messages'
    )
    pinned_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('thread', 'message')
        ordering        = ['-pinned_at']

    def __str__(self):
        return f"Pinned msg {self.message_id} in thread {self.thread_id}"


class StarredMessage(models.Model):
    
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='starred_messages')
    message    = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='stars')
    starred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'message')
        ordering        = ['-starred_at']

    def __str__(self):
        return f"{self.user.username} ★ msg {self.message_id}"



class Mention(models.Model):
    
    message        = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='mentions')
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True,          # null = @all
        related_name='received_mentions'
    )
    is_all         = models.BooleanField(default=False)   # True for @all

    class Meta:
        unique_together = ('message', 'mentioned_user')

    def __str__(self):
        target = self.mentioned_user.username if self.mentioned_user else '@all'
        return f"@{target} in msg {self.message_id}"



class Poll(models.Model):
    
    message      = models.OneToOneField(Message, on_delete=models.CASCADE, related_name='poll')
    question     = models.CharField(max_length=300)
    is_anonymous = models.BooleanField(default=False)    # hide who voted for what
    allow_multi  = models.BooleanField(default=False)    # allow multiple option selection
    closes_at    = models.DateTimeField(null=True, blank=True)  # None = open forever
    created_at   = models.DateTimeField(auto_now_add=True)

    @property
    def is_open(self):
        return self.closes_at is None or timezone.now() < self.closes_at

    @property
    def total_votes(self):
        return PollVote.objects.filter(option__poll=self).count()

    def __str__(self):
        return f"Poll: {self.question[:60]}"


class PollOption(models.Model):
    poll  = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text  = models.CharField(max_length=200)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def vote_count(self):
        return self.votes.count()

    def percentage(self):
        total = self.poll.total_votes
        return round((self.votes.count() / total * 100), 1) if total else 0.0

    def __str__(self):
        return f"{self.text} (poll {self.poll_id})"


class PollVote(models.Model):
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        
        unique_together = ('option', 'user')

    def __str__(self):
        return f"{self.user.username} → option {self.option_id}"


class Notification(models.Model):
    
    NOTIF_TYPES = [
        ('message',  'New Message'),
        ('mention',  'Mention'),
        ('reaction', 'Reaction'),
        ('poll',     'Poll Update'),
        ('system',   'System'),
    ]

    recipient  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    notif_type = models.CharField(max_length=15, choices=NOTIF_TYPES)
    title      = models.CharField(max_length=200)
    body       = models.CharField(max_length=500, blank=True)

    
    thread     = models.ForeignKey(MessageThread, on_delete=models.SET_NULL, null=True, blank=True)
    message    = models.ForeignKey(Message,       on_delete=models.SET_NULL, null=True, blank=True)

    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def mark_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])

    def __str__(self):
        return f"[{self.notif_type}] → {self.recipient.username}: {self.title[:60]}"