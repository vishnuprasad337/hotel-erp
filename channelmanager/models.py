from django.db import models
from django.utils import timezone
import uuid


class WebsiteChannel(models.Model):
    STATUS = [
        ("pending",  "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    hotel                 = models.OneToOneField("accounts.Hotel", on_delete=models.CASCADE, related_name="website_channel")
    site_name             = models.CharField(max_length=200)
    base_url              = models.URLField()
    # Key we send to them; they use it when POSTing bookings to our webhook
    inbound_api_key       = models.CharField(max_length=64, unique=True, blank=True)
    # Their callback URL + key (for pushing confirmation back to them)
    callback_url          = models.URLField(blank=True)
    outbound_api_key      = models.CharField(max_length=128, blank=True)
    sync_availability     = models.BooleanField(default=True)
    sync_interval_minutes = models.PositiveIntegerField(default=15)
    is_active             = models.BooleanField(default=False)   # True only after approved
    status                = models.CharField(max_length=20, choices=STATUS, default="pending")
    last_sync             = models.DateTimeField(null=True, blank=True)
    sync_error            = models.TextField(blank=True)
    created_at            = models.DateTimeField(auto_now_add=True)
    updated_at            = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Auto-generate inbound_api_key on first save
        if not self.inbound_api_key:
            self.inbound_api_key = uuid.uuid4().hex
        super().save(*args, **kwargs)

    def rotate_inbound_key(self):
        """Generate a new inbound API key (e.g. after a security breach)."""
        self.inbound_api_key = uuid.uuid4().hex
        self.save(update_fields=["inbound_api_key", "updated_at"])
        return self.inbound_api_key

    def __str__(self):
        return f"{self.site_name} — {self.hotel.hotel_name} [{self.status}]"


class OTAChannel(models.Model):
    CHANNEL_TYPE = [
        ("booking_com", "Booking.com"),
        ("airbnb",      "Airbnb"),
        ("expedia",     "Expedia"),
        ("ical",        "iCal Generic"),
        ("agoda",       "Agoda"),
        ("mmt",         "MakeMyTrip"),
        ("goibibo",     "Goibibo"),
        ("other",       "Other"),
    ]

    AUTH_METHOD = [
        ("api_key", "API Key / Secret"),
        ("oauth2",  "OAuth 2.0"),
        ("ical",    "iCal (no auth)"),
        ("webhook", "Webhook Only"),
    ]

    hotel = models.ForeignKey(
        "accounts.Hotel",
        on_delete=models.CASCADE,
        related_name="ota_channels",
        null=True,
        blank=True,
    )
    name                = models.CharField(max_length=100)
    channel_type        = models.CharField(max_length=30, choices=CHANNEL_TYPE)
    auth_method         = models.CharField(max_length=20, choices=AUTH_METHOD, default="api_key")
    api_key             = models.CharField(max_length=512, blank=True)
    api_secret          = models.CharField(max_length=512, blank=True)
    oauth_access_token  = models.TextField(blank=True)
    oauth_refresh_token = models.TextField(blank=True)
    oauth_expires_at    = models.DateTimeField(null=True, blank=True)
    hotel_id_on_ota     = models.CharField(max_length=100, blank=True)
    property_code       = models.CharField(max_length=100, blank=True)
    ical_url            = models.URLField(blank=True)
    ical_push_url       = models.URLField(blank=True)
    webhook_secret      = models.CharField(max_length=256, blank=True)
    push_rates          = models.BooleanField(default=True)
    push_availability   = models.BooleanField(default=True)
    pull_bookings       = models.BooleanField(default=True)
    sync_days_ahead     = models.PositiveIntegerField(default=90)
    is_active           = models.BooleanField(default=True)
    last_sync           = models.DateTimeField(null=True, blank=True)
    sync_error          = models.TextField(blank=True)
    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["hotel", "channel_type", "hotel_id_on_ota"]
        verbose_name    = "OTA Channel"

    def __str__(self):
        return f"{self.name} ({self.get_channel_type_display()}) — {self.hotel.hotel_name}"

    @property
    def is_ical(self):
        return self.channel_type == "ical" or self.auth_method == "ical"

    @property
    def oauth_is_expired(self):
        if not self.oauth_expires_at:
            return False
        return timezone.now() >= self.oauth_expires_at


class ChannelRate(models.Model):
    ota_channel     = models.ForeignKey(OTAChannel,     on_delete=models.CASCADE, null=True, blank=True, related_name="rates")
    website_channel = models.ForeignKey(WebsiteChannel, on_delete=models.CASCADE, null=True, blank=True, related_name="rates")
    room_type       = models.ForeignKey("pms.Room", on_delete=models.CASCADE, related_name="channel_rates")
    date            = models.DateField()
    rate            = models.DecimalField(max_digits=10, decimal_places=2)
    min_stay        = models.PositiveIntegerField(default=1)
    max_stay        = models.PositiveIntegerField(default=30)
    available_rooms = models.PositiveIntegerField(default=0)
    stop_sell       = models.BooleanField(default=False)
    last_pushed     = models.DateTimeField(null=True, blank=True)
    push_error      = models.TextField(blank=True)

    class Meta:
        unique_together = ["ota_channel", "website_channel", "room_type", "date"]
        indexes         = [models.Index(fields=["date", "room_type"])]

    def __str__(self):
        channel = self.ota_channel or self.website_channel
        return f"{channel} | {self.room_type} | {self.date} | {self.available_rooms} rooms @ {self.rate}"


class SyncLog(models.Model):
    DIRECTION = [("push", "Push (ERP → Channel)"), ("pull", "Pull (Channel → ERP)")]
    OUTCOME   = [("success", "Success"), ("partial", "Partial"), ("failed", "Failed")]
    ENTITY    = [("rate", "Rate/Availability"), ("booking", "Booking"), ("cancellation", "Cancellation")]

    ota_channel     = models.ForeignKey(OTAChannel,     on_delete=models.CASCADE, null=True, blank=True, related_name="sync_logs")
    website_channel = models.ForeignKey(WebsiteChannel, on_delete=models.CASCADE, null=True, blank=True, related_name="sync_logs")
    direction       = models.CharField(max_length=10, choices=DIRECTION)
    entity          = models.CharField(max_length=20, choices=ENTITY)
    outcome         = models.CharField(max_length=10, choices=OUTCOME)
    records_sent    = models.PositiveIntegerField(default=0)
    records_failed  = models.PositiveIntegerField(default=0)
    duration_ms     = models.PositiveIntegerField(default=0)
    detail          = models.TextField(blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        channel = self.ota_channel or self.website_channel
        return f"{self.direction} {self.entity} → {channel} [{self.outcome}] @ {self.created_at:%Y-%m-%d %H:%M}"


class WebhookEvent(models.Model):
    STATUS = [
        ("pending",    "Pending"),
        ("processing", "Processing"),
        ("done",       "Done"),
        ("failed",     "Failed"),
        ("ignored",    "Ignored"),
    ]

    ota_channel     = models.ForeignKey(OTAChannel,     on_delete=models.CASCADE, null=True, blank=True, related_name="webhook_events")
    website_channel = models.ForeignKey(WebsiteChannel, on_delete=models.CASCADE, null=True, blank=True, related_name="webhook_events")
    event_type      = models.CharField(max_length=100, blank=True)
    headers         = models.JSONField(default=dict)
    payload         = models.JSONField(default=dict)
    raw_body        = models.TextField(blank=True)
    status          = models.CharField(max_length=20, choices=STATUS, default="pending")
    attempts        = models.PositiveSmallIntegerField(default=0)
    last_error      = models.TextField(blank=True)
    booking         = models.ForeignKey(
        "pms.Booking", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="webhook_events",
    )
    received_at     = models.DateTimeField(auto_now_add=True)
    processed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]
        indexes  = [models.Index(fields=["status"])]

    def __str__(self):
        return f"{self.event_type} [{self.status}] @ {self.received_at:%Y-%m-%d %H:%M}"