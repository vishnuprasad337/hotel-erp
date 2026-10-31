"""
channelmanager/views.py — full updated file.

REQUIRED MODEL CHANGES (then makemigrations + migrate):
    OTAChannel.extranet_authorized = models.BooleanField(default=False)
    pms.Booking.external_ref       = models.CharField(max_length=100, blank=True, db_index=True)

REQUIRED SETTINGS:
    CMS_PUBLIC_URL            = "https://your-erp-domain"
    DEFAULT_TAX_RATE          = "0.18"
    BOOKING_COM_USER          = os.environ.get("BOOKING_COM_USER", "")      # provider-level
    BOOKING_COM_PASSWORD      = os.environ.get("BOOKING_COM_PASSWORD", "")  # provider-level

IMPORTANT: CSRF is no longer exempted on the logged-in channel APIs. Any page
that calls them (website_channels.html too) must send the X-CSRFToken header,
exactly as ota_channels.html already does.
"""
import hmac
import json
import logging
import secrets
from datetime import datetime as dt, timedelta
from decimal import Decimal
from functools import wraps

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from .models import (
    DeletedWebsiteChannelKey,
    OTAChannel,
    OTARoomMapping,
    SyncLog,
    WebhookEvent,
    WebsiteChannel,
)
from .tasks import push_availability_to_channel, push_booking_to_channel  # noqa: F401

log = logging.getLogger(__name__)

VALID_TYPES = {c[0] for c in OTAChannel.CHANNEL_TYPE}
VALID_AUTH = {c[0] for c in OTAChannel.AUTH_METHOD}
TAX_RATE = Decimal(str(getattr(settings, "DEFAULT_TAX_RATE", "0.18")))
ACTIVE_STATUSES = ["confirmed", "checked_in"]
SENSITIVE_HEADERS = {"x-webhook-secret", "x-api-key", "authorization", "cookie"}


# ═════════════════════════════════════════════════════════════
# Shared helpers
# ═════════════════════════════════════════════════════════════
def hotel_api(view):
    """JSON 401 (not an HTML redirect) unless a hotel user is logged in."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated or getattr(user, "hotel", None) is None:
            return JsonResponse({"error": "Authentication required."}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def _json_body(request):
    try:
        data = json.loads(request.body or "{}")
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_date(value):
    try:
        return dt.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _safe_headers(request):
    """Store request headers for debugging, minus anything secret."""
    return {k: v for k, v in request.headers.items() if k.lower() not in SENSITIVE_HEADERS}


def _d(value):
    return Decimal(str(value)) if value not in (None, "") else None


def _resync_inventory(hotel):
    """Push fresh availability to every live channel of this hotel."""
    try:
        from . import tasks
        for wc in WebsiteChannel.objects.filter(hotel=hotel, is_active=True):
            tasks.push_availability_to_channel(wc.pk)
        push_ota = getattr(tasks, "push_availability_to_ota", None)  # implement in your adapter
        if push_ota:
            for oc in OTAChannel.objects.filter(hotel=hotel, is_active=True, push_availability=True):
                push_ota(oc.pk)
    except Exception:  # noqa: BLE001
        log.exception("Inventory resync failed")


def _free_unit(room, check_in, check_out, exclude_booking_id=None):
    """First unit with no overlapping active booking. Caller must hold the room lock."""
    from pms.models import Booking, RoomUnit
    overlap = Booking.objects.filter(
        room_unit=OuterRef("pk"), status__in=ACTIVE_STATUSES,
        check_in__lt=check_out, check_out__gt=check_in,
    )
    if exclude_booking_id:
        overlap = overlap.exclude(pk=exclude_booking_id)
    return (
        RoomUnit.objects.filter(room=room)
        .exclude(status="Maintenance")
        .annotate(busy=Exists(overlap)).filter(busy=False)
        .order_by("room_number").first()
    )


# ═════════════════════════════════════════════════════════════
# Serialisers
# ═════════════════════════════════════════════════════════════
def channel_to_dict(ch):
    return {
        "id": ch.pk,
        "site_name": ch.site_name,
        "base_url": ch.base_url,
        "inbound_api_key": ch.inbound_api_key,
        "callback_url": ch.callback_url,
        "outbound_api_key": ch.outbound_api_key,
        "sync_availability": ch.sync_availability,
        "sync_interval_minutes": ch.sync_interval_minutes,
        "is_active": ch.is_active,
        "status": ch.status,
        "last_sync": ch.last_sync.isoformat() if ch.last_sync else None,
        "sync_error": ch.sync_error,
        "created_at": ch.created_at.isoformat(),
        "updated_at": ch.updated_at.isoformat(),
    }


def readiness(ch, mapping_count):
    """List what is still missing before an OTA channel may go live."""
    missing = []
    if ch.channel_type == "booking_com":
        if not ch.hotel_id_on_ota:
            missing.append("Booking.com Hotel ID")
        if not (getattr(settings, "BOOKING_COM_USER", "") and getattr(settings, "BOOKING_COM_PASSWORD", "")):
            missing.append("Provider credentials are not configured on the server")
        if not ch.extranet_authorized:
            missing.append("Authorize your provider in the Booking.com Extranet")
    elif ch.is_ical:
        if not ch.ical_url:
            missing.append("iCal URL")
    else:
        if not ch.hotel_id_on_ota:
            missing.append("Hotel ID on the OTA")
        if ch.auth_method == "api_key" and not ch.api_key:
            missing.append("API key")
        if ch.auth_method == "oauth2" and not ch.oauth_access_token:
            missing.append("OAuth authorization")
    if not ch.is_ical and mapping_count == 0:
        missing.append("Map at least one room type")
    return missing


def ota_to_dict(ch):
    mapping_count = getattr(ch, "mapping_count", None)
    if mapping_count is None:
        mapping_count = ch.room_mappings.filter(is_active=True).count()
    missing = readiness(ch, mapping_count)
    return {
        "id": ch.pk,
        "name": ch.name,
        "channel_type": ch.channel_type,
        "channel_type_display": ch.get_channel_type_display(),
        "auth_method": ch.auth_method,
        "protocol": ch.protocol,
        "hotel_id_on_ota": ch.hotel_id_on_ota,
        "property_code": ch.property_code,
        "ical_url": ch.ical_url,
        "has_credentials": bool(ch.api_key or ch.oauth_access_token),  # secrets never leave the server
        "extranet_authorized": ch.extranet_authorized,
        "supports_webhook": ch.supports_webhook,
        "sync_interval_minutes": ch.sync_interval_minutes,
        "push_rates": ch.push_rates,
        "push_availability": ch.push_availability,
        "pull_bookings": ch.pull_bookings,
        "sync_days_ahead": ch.sync_days_ahead,
        "is_active": ch.is_active,
        "last_sync": ch.last_sync.isoformat() if ch.last_sync else None,
        "sync_error": ch.sync_error,
        "is_ical": ch.is_ical,
        "oauth_is_expired": ch.oauth_is_expired,
        "mapped_rooms": mapping_count,
        "ready": not missing,
        "missing": missing,
        "inbound_webhook_url": f"{getattr(settings, 'CMS_PUBLIC_URL', '').rstrip('/')}/channels/webhook/ota/{ch.pk}/",
        "created_at": ch.created_at.isoformat(),
        "updated_at": ch.updated_at.isoformat(),
    }


def webhook_event_to_dict(ev):
    if ev.website_channel_id:
        channel_name, channel_kind = ev.website_channel.site_name, "website"
    elif ev.ota_channel_id:
        channel_name, channel_kind = ev.ota_channel.name, "ota"
    else:
        channel_name, channel_kind = "—", ""
    return {
        "id": ev.pk,
        "event_type": ev.event_type,
        "status": ev.status,
        "attempts": ev.attempts,
        "last_error": ev.last_error,
        "booking_id": ev.booking_id,
        "booking_code": f"BK{ev.booking_id:06d}" if ev.booking_id else None,
        "website_channel_id": ev.website_channel_id,
        "ota_channel_id": ev.ota_channel_id,
        "channel_name": channel_name,
        "channel_kind": channel_kind,
        "payload": ev.payload,
        "received_at": ev.received_at.isoformat(),
        "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
    }


def sync_log_to_dict(log_row):
    if log_row.website_channel_id:
        channel_name, channel_kind = log_row.website_channel.site_name, "website"
    elif log_row.ota_channel_id:
        channel_name, channel_kind = log_row.ota_channel.name, "ota"
    else:
        channel_name, channel_kind = "—", ""
    return {
        "id": log_row.pk,
        "direction": log_row.direction,
        "entity": log_row.entity,
        "outcome": log_row.outcome,
        "records_sent": log_row.records_sent,
        "records_failed": log_row.records_failed,
        "duration_ms": log_row.duration_ms,
        "detail": log_row.detail,
        "website_channel_id": log_row.website_channel_id,
        "ota_channel_id": log_row.ota_channel_id,
        "channel_name": channel_name,
        "channel_kind": channel_kind,
        "created_at": log_row.created_at.isoformat(),
    }


# ═════════════════════════════════════════════════════════════
# Website channel: outbound helpers
# ═════════════════════════════════════════════════════════════
def push_booking_to_website(channel, booking):
    payload = {
        "event": "booking_confirmed",
        "booking_id": booking.pk,
        "booking_code": f"BK{booking.pk:06d}",
        "room_type": booking.room.room_type,
        "room_number": booking.room_unit.room_number if booking.room_unit else None,
        "check_in": str(booking.check_in),
        "check_out": str(booking.check_out),
        "adults": booking.adults,
        "children": booking.children,
        "total_amount": str(booking.total_amount),
        "status": booking.status,
        "source": booking.source,
    }
    headers = {"Content-Type": "application/json", "X-Api-Key": channel.outbound_api_key}

    start = timezone.now()
    outcome, error_detail = "success", ""
    try:
        resp = requests.post(channel.callback_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        channel.last_sync = timezone.now()
        channel.sync_error = ""
        channel.save(update_fields=["last_sync", "sync_error", "updated_at"])
    except Exception as e:  # noqa: BLE001
        outcome, error_detail = "failed", str(e)
        channel.sync_error = error_detail
        channel.save(update_fields=["sync_error", "updated_at"])

    SyncLog.objects.create(
        website_channel=channel, direction="push", entity="booking", outcome=outcome,
        records_sent=1 if outcome == "success" else 0,
        records_failed=0 if outcome == "success" else 1,
        duration_ms=int((timezone.now() - start).total_seconds() * 1000),
        detail=error_detail,
    )


def _public_url():
    return getattr(settings, "CMS_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def send_connect_request(channel):
    hotel = channel.hotel
    erp_url = _public_url()
    webhook_url = f"{erp_url}/channels/webhook/{channel.inbound_api_key}/"

    try:
        requests.post(
            f"{channel.base_url}/api/update-webhook-key/",
            json={"hotel_name": hotel.hotel_name, "new_api_key": channel.inbound_api_key, "webhook_url": webhook_url},
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        log.warning("update-webhook-key call failed", exc_info=True)

    payload = {
        "hotel_name": hotel.hotel_name,
        "hotel_id": hotel.pk,
        "site_name": channel.site_name,
        "erp_url": erp_url,
        "schema_name": hotel.schema_name,
        "inbound_api_key": channel.inbound_api_key,
        "webhook_url": webhook_url,
    }

    channel.status, channel.is_active = "pending", False
    try:
        resp = requests.post(f"{channel.base_url}/connect-request/", json=payload, timeout=5)
        channel.sync_error = "" if resp.status_code in (200, 201) else f"Website returned {resp.status_code}"
    except Exception as e:  # noqa: BLE001
        channel.sync_error = f"Connect request error: {e}"

    channel.save(update_fields=["status", "is_active", "sync_error", "updated_at"])
    return channel.status


# ═════════════════════════════════════════════════════════════
# Website channel: CRUD
# ═════════════════════════════════════════════════════════════
@method_decorator(hotel_api, name="dispatch")
class WebsiteChannelListView(View):

    def get(self, request):
        channels = WebsiteChannel.objects.filter(hotel=request.user.hotel)
        return JsonResponse({"results": [channel_to_dict(c) for c in channels]})

    def post(self, request):
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        for field in ("site_name", "base_url", "outbound_api_key"):
            if not data.get(field):
                return JsonResponse({"error": f"{field} is required"}, status=400)

        if WebsiteChannel.objects.filter(hotel=request.user.hotel).exists():
            return JsonResponse({"error": "A website channel already exists for this hotel."}, status=409)

        preserved_key = (
            DeletedWebsiteChannelKey.objects.filter(hotel=request.user.hotel)
            .order_by("-deleted_at").values_list("inbound_api_key", flat=True).first()
        )

        channel = WebsiteChannel.objects.create(
            hotel=request.user.hotel,
            site_name=data["site_name"],
            base_url=data["base_url"].rstrip("/"),
            callback_url=data.get("callback_url", ""),
            outbound_api_key=data["outbound_api_key"],
            sync_availability=data.get("sync_availability", True),
            sync_interval_minutes=data.get("sync_interval_minutes", 15),
            status="pending",
            is_active=False,
            **({"inbound_api_key": preserved_key} if preserved_key else {}),
        )

        status = send_connect_request(channel)
        out = channel_to_dict(channel)
        out["connect_status"] = status
        return JsonResponse(out, status=201)


@method_decorator(hotel_api, name="dispatch")
class WebsiteChannelDetailView(View):

    def get_channel(self, request, pk):
        return get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)

    def get(self, request, pk):
        return JsonResponse(channel_to_dict(self.get_channel(request, pk)))

    def patch(self, request, pk):
        channel = self.get_channel(request, pk)
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        for field in ("site_name", "base_url", "callback_url", "outbound_api_key",
                      "sync_availability", "sync_interval_minutes", "is_active"):
            if field in data:
                setattr(channel, field, data[field])
        # A channel can only be switched on once the website approved it.
        if channel.is_active and channel.status != "approved":
            return JsonResponse({"error": "Channel is not approved by the website yet."}, status=400)
        channel.save()
        return JsonResponse(channel_to_dict(channel))

    def delete(self, request, pk):
        channel = self.get_channel(request, pk)
        DeletedWebsiteChannelKey.objects.update_or_create(
            hotel=request.user.hotel,
            defaults={"inbound_api_key": channel.inbound_api_key, "deleted_at": timezone.now()},
        )
        channel.delete()
        return JsonResponse({"deleted": True})


@method_decorator(hotel_api, name="dispatch")
class WebsiteChannelToggleView(View):

    def patch(self, request, pk):
        channel = get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)
        if not channel.is_active and channel.status != "approved":
            return JsonResponse({"error": "Channel is not approved by the website yet."}, status=400)
        channel.is_active = not channel.is_active
        channel.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"id": channel.pk, "is_active": channel.is_active})


@method_decorator(hotel_api, name="dispatch")
class WebsiteChannelSyncView(View):

    def post(self, request, pk):
        channel = get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)
        if not channel.is_active:
            return JsonResponse({"error": "Channel is inactive. Enable it before syncing."}, status=400)

        push_availability_to_channel(channel.pk)
        channel.refresh_from_db()
        return JsonResponse({
            "detail": "Sync triggered.",
            "last_sync": channel.last_sync.isoformat() if channel.last_sync else None,
        })


@method_decorator(hotel_api, name="dispatch")
class WebsiteChannelRotateKeyView(View):

    def post(self, request, pk):
        channel = get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)
        new_key = channel.rotate_inbound_key()

        if channel.base_url:
            try:
                requests.post(
                    f"{channel.base_url}/api/update-webhook-key/",
                    json={
                        "hotel_name": channel.hotel.hotel_name,
                        "new_api_key": new_key,
                        "webhook_url": f"{_public_url()}/channels/webhook/{new_key}/",
                    },
                    timeout=5,
                )
            except Exception:  # noqa: BLE001
                log.warning("Could not notify website of rotated key", exc_info=True)

        return JsonResponse({"id": channel.pk, "inbound_api_key": new_key})


@method_decorator(csrf_exempt, name="dispatch")
class WebsiteConnectResponseView(View):
    """Called BY the website (server-to-server) to accept/reject a connect request."""

    def post(self, request):
        from customers.models import Client
        from django_tenants.utils import schema_context

        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        api_key = data.get("inbound_api_key")
        if not api_key:
            return JsonResponse({"error": "inbound_api_key is required"}, status=400)

        target_schema = None
        for tenant in Client.objects.exclude(schema_name="public"):
            with schema_context(tenant.schema_name):
                if WebsiteChannel.objects.filter(inbound_api_key=api_key).exists():
                    target_schema = tenant.schema_name
                    break

        if not target_schema:
            return JsonResponse({"error": "No channel found for this API key."}, status=404)

        with schema_context(target_schema):
            channel = WebsiteChannel.objects.get(inbound_api_key=api_key)

            if data.get("accepted"):
                channel.status, channel.is_active, channel.sync_error = "approved", True, ""
                fields = ["status", "is_active", "sync_error", "updated_at"]
                if data.get("callback_url"):
                    channel.callback_url = data["callback_url"]
                    fields.append("callback_url")
                channel.save(update_fields=fields)
                try:
                    push_availability_to_channel(channel.pk)
                except Exception:  # noqa: BLE001
                    log.exception("Auto sync after approval failed")
                return JsonResponse({
                    "detail": "Connection approved. Ready to receive bookings.",
                    "is_active": channel.is_active,
                    "status": channel.status,
                    "callback_url": channel.callback_url,
                })

            channel.status, channel.is_active = "rejected", False
            channel.save(update_fields=["status", "is_active", "updated_at"])
            return JsonResponse({"detail": "Connection rejected."})


# ═════════════════════════════════════════════════════════════
# OTA channel: CRUD
# ═════════════════════════════════════════════════════════════
OTA_EDITABLE = [
    "name", "auth_method", "hotel_id_on_ota", "property_code", "ical_url",
    "ical_push_url", "push_rates", "push_availability", "pull_bookings",
    "sync_days_ahead", "sync_interval_minutes", "extranet_authorized",
]


def _validate_ota(data, creating):
    errors = {}
    if creating:
        if data.get("channel_type") not in VALID_TYPES:
            errors["channel_type"] = "Choose a valid channel."
        if not str(data.get("name", "")).strip():
            errors["name"] = "Channel name is required."
    if "auth_method" in data and data["auth_method"] not in VALID_AUTH:
        errors["auth_method"] = "Invalid auth method."
    if "sync_days_ahead" in data:
        try:
            if not 1 <= int(data["sync_days_ahead"]) <= 730:
                raise ValueError
        except (TypeError, ValueError):
            errors["sync_days_ahead"] = "Sync range must be between 1 and 730."
    if "sync_interval_minutes" in data:
        try:
            if not 5 <= int(data["sync_interval_minutes"]) <= 1440:
                raise ValueError
        except (TypeError, ValueError):
            errors["sync_interval_minutes"] = "Sync interval must be between 5 and 1440."
    return errors


@method_decorator(hotel_api, name="dispatch")
class OTAChannelListView(View):

    def get(self, request):
        qs = (
            OTAChannel.objects.filter(hotel=request.user.hotel)
            .annotate(mapping_count=Count("room_mappings", filter=Q(room_mappings__is_active=True)))
            .order_by("name")
        )
        return JsonResponse({"results": [ota_to_dict(c) for c in qs]})

    def post(self, request):
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        errors = _validate_ota(data, creating=True)
        if errors:
            return JsonResponse({"error": "; ".join(errors.values()), "errors": errors}, status=400)

        ctype = data["channel_type"]
        is_booking = ctype == "booking_com"
        auth = "ical" if ctype == "ical" else data.get("auth_method", "api_key")

        fields = {k: data[k] for k in OTA_EDITABLE if k in data}
        fields.update(name=data["name"].strip(), auth_method=auth)
        if not is_booking:  # Booking.com credentials belong to the provider, not the hotel
            fields["api_key"] = data.get("api_key", "")
            fields["api_secret"] = data.get("api_secret", "")

        webhook_secret = secrets.token_urlsafe(32) if (not is_booking and auth != "ical") else ""

        try:
            channel = OTAChannel.objects.create(
                hotel=request.user.hotel,
                channel_type=ctype,
                webhook_secret=webhook_secret,
                is_active=False,  # goes live only after the checklist passes
                **fields,
            )
        except IntegrityError:
            return JsonResponse({"error": "This channel and hotel ID already exist."}, status=409)

        out = ota_to_dict(channel)
        if webhook_secret:
            out["webhook_secret"] = webhook_secret  # shown ONCE
        return JsonResponse(out, status=201)


@method_decorator(hotel_api, name="dispatch")
class OTAChannelDetailView(View):

    def get_channel(self, request, pk):
        return get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)

    def get(self, request, pk):
        return JsonResponse(ota_to_dict(self.get_channel(request, pk)))

    def patch(self, request, pk):
        channel = self.get_channel(request, pk)
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        errors = _validate_ota(data, creating=False)
        if errors:
            return JsonResponse({"error": "; ".join(errors.values()), "errors": errors}, status=400)

        for f in OTA_EDITABLE:
            if f in data:
                setattr(channel, f, data[f])
        if channel.channel_type != "booking_com":
            if data.get("api_key"):
                channel.api_key = data["api_key"]
            if data.get("api_secret"):
                channel.api_secret = data["api_secret"]
        try:
            channel.save()
        except IntegrityError:
            return JsonResponse({"error": "This channel and hotel ID already exist."}, status=409)
        return JsonResponse(ota_to_dict(channel))

    def delete(self, request, pk):
        self.get_channel(request, pk).delete()
        return JsonResponse({"deleted": True})


@method_decorator(hotel_api, name="dispatch")
class OTAChannelToggleView(View):

    def patch(self, request, pk):
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        if not channel.is_active:
            missing = readiness(channel, channel.room_mappings.filter(is_active=True).count())
            if missing:
                return JsonResponse(
                    {"error": "Cannot enable yet: " + "; ".join(missing), "missing": missing}, status=400
                )
        channel.is_active = not channel.is_active
        channel.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"id": channel.pk, "is_active": channel.is_active})


@method_decorator(hotel_api, name="dispatch")
class OTAChannelCheckView(View):
    """Setup checklist. A live API test belongs in the adapter once it exists."""

    def get(self, request, pk):
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        missing = readiness(channel, channel.room_mappings.filter(is_active=True).count())
        return JsonResponse({"ready": not missing, "missing": missing})


# ═════════════════════════════════════════════════════════════
# OTA room mapping
# ═════════════════════════════════════════════════════════════
@method_decorator(hotel_api, name="dispatch")
class OTARoomMappingView(View):

    def get(self, request, pk):
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        rows = OTARoomMapping.objects.filter(ota_channel=channel).select_related("internal_room")
        return JsonResponse({"results": [{
            "id": m.pk,
            "internal_room_id": m.internal_room_id,
            "internal_room_name": str(m.internal_room),
            "ota_room_id": m.ota_room_id,
            "ota_room_name": m.ota_room_name,
            "ota_rate_plan_id": m.ota_rate_plan_id,
            "is_active": m.is_active,
        } for m in rows]})

    def post(self, request, pk):
        from pms.models import Room
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        data = _json_body(request)
        if data is None:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        for f in ("internal_room_id", "ota_room_id", "ota_room_name"):
            if not data.get(f):
                return JsonResponse({"error": f"{f} is required"}, status=400)

        room = get_object_or_404(Room, pk=data["internal_room_id"])
        mapping, created = OTARoomMapping.objects.update_or_create(
            ota_channel=channel, internal_room=room,
            defaults={
                "ota_room_id": str(data["ota_room_id"]),
                "ota_room_name": data["ota_room_name"],
                "ota_rate_plan_id": data.get("ota_rate_plan_id", ""),
                "is_active": data.get("is_active", True),
            },
        )
        return JsonResponse({
            "id": mapping.pk, "created": created,
            "internal_room_id": mapping.internal_room_id,
            "ota_room_id": mapping.ota_room_id,
            "ota_room_name": mapping.ota_room_name,
        }, status=201 if created else 200)


@method_decorator(hotel_api, name="dispatch")
class OTARoomMappingDeleteView(View):
    """DELETE by MAPPING id (the old code confused channel id and mapping id)."""

    def delete(self, request, pk):
        mapping = get_object_or_404(OTARoomMapping, pk=pk, ota_channel__hotel=request.user.hotel)
        mapping.delete()
        return JsonResponse({"deleted": True})


# ═════════════════════════════════════════════════════════════
# Webhook events + sync logs (lists)
# ═════════════════════════════════════════════════════════════
def _apply_channel_filter(qs, raw):
    if ":" in raw:
        kind, _, cid = raw.partition(":")
        if cid.isdigit():
            if kind == "website":
                return qs.filter(website_channel_id=int(cid))
            if kind == "ota":
                return qs.filter(ota_channel_id=int(cid))
    return qs


@method_decorator(hotel_api, name="dispatch")
class WebhookEventListView(View):

    def get(self, request):
        hotel = request.user.hotel
        qs = (
            WebhookEvent.objects
            .filter(Q(website_channel__hotel=hotel) | Q(ota_channel__hotel=hotel))
            .select_related("website_channel", "ota_channel", "booking")
            .order_by("-received_at")
        )
        qs = _apply_channel_filter(qs, request.GET.get("channel", ""))

        event_type = request.GET.get("event_type")
        if event_type:
            qs = qs.filter(event_type=event_type)

        date_from = _parse_date(request.GET.get("date_from"))
        date_to = _parse_date(request.GET.get("date_to"))
        if date_from:
            qs = qs.filter(received_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(received_at__date__lte=date_to)

        q = request.GET.get("q", "").strip()
        if q:
            filters = (
                Q(event_type__icontains=q)
                | Q(website_channel__site_name__icontains=q)
                | Q(ota_channel__name__icontains=q)
            )
            if q.isdigit():
                filters |= Q(id=int(q)) | Q(booking_id=int(q))
            qs = qs.filter(filters)

        # Stats ignore the status filter so the cards always show the full split
        s = qs.aggregate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            processing=Count("id", filter=Q(status="processing")),
            done=Count("id", filter=Q(status="done")),
            failed=Count("id", filter=Q(status="failed")),
            ignored=Count("id", filter=Q(status="ignored")),
        )
        stats = {
            "total": s["total"] or 0,
            "pending": (s["pending"] or 0) + (s["processing"] or 0),
            "processed": s["done"] or 0,
            "failed": s["failed"] or 0,
            "ignored": s["ignored"] or 0,
        }

        event_status = request.GET.get("status")
        if event_status:
            qs = qs.filter(status=event_status)

        return JsonResponse({"results": [webhook_event_to_dict(e) for e in qs[:200]], "stats": stats})


@method_decorator(hotel_api, name="dispatch")
class SyncLogListView(View):
    """
    GET /channels/sync-logs/
        ?direction=push|pull &outcome=success|failed|partial
        &channel=website:<id> | ota:<id> &date_from=YYYY-MM-DD &date_to=YYYY-MM-DD
        &q=<text in detail / entity>
    """

    def get(self, request):
        hotel = request.user.hotel
        qs = (
            SyncLog.objects
            .filter(Q(website_channel__hotel=hotel) | Q(ota_channel__hotel=hotel))
            .select_related("website_channel", "ota_channel")
            .order_by("-created_at")
        )

        direction = request.GET.get("direction")
        if direction:
            qs = qs.filter(direction=direction)
        qs = _apply_channel_filter(qs, request.GET.get("channel", ""))

        date_from = _parse_date(request.GET.get("date_from"))
        date_to = _parse_date(request.GET.get("date_to"))
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        q = request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(detail__icontains=q) | Q(entity__icontains=q))

        s = qs.aggregate(
            total=Count("id"),
            success=Count("id", filter=Q(outcome="success")),
            failed=Count("id", filter=Q(outcome="failed")),
            partial=Count("id", filter=Q(outcome="partial")),
            sent=Sum("records_sent"),
        )
        stats = {
            "total": s["total"] or 0,
            "success": s["success"] or 0,
            "failed": s["failed"] or 0,
            "partial": s["partial"] or 0,
            "records_sent": s["sent"] or 0,
        }

        outcome = request.GET.get("outcome")
        if outcome:
            qs = qs.filter(outcome=outcome)

        return JsonResponse({"results": [sync_log_to_dict(x) for x in qs[:500]], "stats": stats})


# ═════════════════════════════════════════════════════════════
# Website webhook (website → ERP booking)
# ═════════════════════════════════════════════════════════════
def _fail_event(event, channel_kwargs, exc):
    event.status = "failed"
    event.last_error = str(exc)
    event.processed_at = timezone.now()
    event.save(update_fields=["status", "last_error", "processed_at"])
    SyncLog.objects.create(
        direction="pull", entity="booking", outcome="failed",
        records_sent=0, records_failed=1, detail=str(exc), **channel_kwargs,
    )


@method_decorator(csrf_exempt, name="dispatch")
class WebhookReceiveView(View):

    def post(self, request, api_key):
        from customers.models import Client
        from django_tenants.utils import schema_context

        schema_from_header = request.headers.get("X-DTS-Schema", "").strip()
        target_schema = None

        if schema_from_header:
            with schema_context(schema_from_header):
                if WebsiteChannel.objects.filter(inbound_api_key=api_key, is_active=True).exists():
                    target_schema = schema_from_header

        if not target_schema:
            for tenant in Client.objects.exclude(schema_name="public"):
                with schema_context(tenant.schema_name):
                    if WebsiteChannel.objects.filter(inbound_api_key=api_key, is_active=True).exists():
                        target_schema = tenant.schema_name
                        break

        if not target_schema:
            return JsonResponse({"error": "Channel not found."}, status=404)

        with schema_context(target_schema):
            channel = get_object_or_404(WebsiteChannel, inbound_api_key=api_key, is_active=True)
            if channel.status != "approved":
                return JsonResponse({"error": "Channel not approved."}, status=403)

            payload = _json_body(request)
            if payload is None:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            event = WebhookEvent.objects.create(
                website_channel=channel,
                event_type=payload.get("event_type", "booking_created"),
                headers=_safe_headers(request),
                payload=payload,
                raw_body=request.body.decode("utf-8", errors="replace"),
                status="processing",
                attempts=1,
            )

            try:
                result = self._create_booking(channel, payload, event)
            except ValueError as exc:  # our own business-rule messages are safe to return
                _fail_event(event, {"website_channel": channel}, exc)
                return JsonResponse({"error": str(exc)}, status=409)
            except Exception as exc:  # noqa: BLE001
                log.exception("Website webhook failed")
                _fail_event(event, {"website_channel": channel}, exc)
                return JsonResponse({"error": "Could not process booking."}, status=500)

            # Notify the website and refresh inventory everywhere (outside the DB transaction)
            try:
                if channel.callback_url and channel.outbound_api_key:
                    push_booking_to_website(channel, result.pop("_booking"))
                else:
                    result.pop("_booking", None)
                _resync_inventory(channel.hotel)
            except Exception:  # noqa: BLE001
                log.exception("Post-booking sync failed")
            return JsonResponse(result, status=202)

    @staticmethod
    def _create_booking(channel, payload, event):
        from billing.models import BillingPayment, FolioCharge, GuestFolio
        from pms.models import Booking, Guest, Payment, Room, RoomUnit

        check_in = dt.strptime(payload["check_in"], "%Y-%m-%d").date()
        check_out = dt.strptime(payload["check_out"], "%Y-%m-%d").date()
        if check_out <= check_in:
            raise ValueError("check_out must be after check_in.")
        nights = (check_out - check_in).days

        room = Room.objects.prefetch_related("seasonal_rates").get(pk=payload["room_id"])
        seasonal = list(room.seasonal_rates.all())

        def price_for(d):
            for r in seasonal:
                if r.start_date <= d <= r.end_date:
                    return Decimal(str(r.price))
            return Decimal(str(room.base_price))

        room_charges = sum((price_for(check_in + timedelta(days=i)) for i in range(nights)), Decimal("0"))
        tax = (room_charges * TAX_RATE).quantize(Decimal("0.01"))
        total = room_charges + tax
        advance = min(_d(payload.get("advance_amount")) or Decimal("0"), total)
        advance_method = payload.get("advance_method") or "Online"
        pay_status = "pending" if advance <= 0 else ("paid" if advance >= total else "partial")

        phone = (payload.get("phone") or "").strip()
        email = (payload.get("email") or "").strip()
        full_name = (payload.get("full_name") or "").strip()
        adults, children = int(payload.get("adults", 1)), int(payload.get("children", 0))

        with transaction.atomic():
            Room.objects.select_for_update().get(pk=room.pk)  # serialise bookings per room type

            room_unit = RoomUnit.objects.get(pk=payload["room_unit_id"], room=room)
            # Same rule as the front desk: only Maintenance blocks; the rest is decided by dates.
            if room_unit.status == "Maintenance":
                raise ValueError(f"Room {room_unit.room_number} is under maintenance and cannot be booked.")
            if Booking.objects.filter(
                room_unit=room_unit, status__in=ACTIVE_STATUSES,
                check_in__lt=check_out, check_out__gt=check_in,
            ).exists():
                raise ValueError(f"Room {room_unit.room_number} is already booked for those dates.")

            if email:
                guest, created = Guest.objects.get_or_create(
                    email=email, defaults={"full_name": full_name, "phone": phone})
            elif phone:
                guest, created = Guest.objects.get_or_create(
                    phone=phone, defaults={"full_name": full_name, "email": email})
            else:
                guest, created = Guest.objects.create(full_name=full_name, email=email, phone=phone), True
            if not created and full_name:
                guest.full_name = full_name
                guest.save(update_fields=["full_name"])

            booking = Booking.objects.create(
                guest=guest, room=room, room_unit=room_unit,
                check_in=check_in, check_out=check_out,
                adults=adults, children=children, guests_count=adults + children,
                base_price=room.base_price, tax=tax, total_amount=total,
                status="confirmed", source=f"website:{channel.site_name}",
                special_requests=payload.get("special_requests", ""),
            )
            Payment.objects.create(
                booking=booking, room_charges=room_charges, tax=tax, total_amount=total,
                amount_paid=advance, payment_status=pay_status,
                payment_method=advance_method if advance > 0 else None,
                paid_at=timezone.now() if advance > 0 else None,
            )
            folio = GuestFolio.objects.create(booking=booking)
            FolioCharge.objects.create(
                folio=folio, charge_type="room",
                description=f"{room.room_type} Room Charge ({nights} night{'s' if nights > 1 else ''})",
                amount=room_charges, tax_amount=tax, date=check_in,
            )
            if advance > 0:
                BillingPayment.objects.create(
                    folio=folio, amount=advance, method=advance_method,
                    note=f"Advance payment via {channel.site_name}",
                )
            event.booking, event.status, event.processed_at = booking, "done", timezone.now()
            event.save(update_fields=["booking", "status", "processed_at"])

        SyncLog.objects.create(
            website_channel=channel, direction="pull", entity="booking", outcome="success",
            records_sent=1, detail=f"Booking BK{booking.pk:06d} created from {channel.site_name}",
        )
        return {
            "received": True,
            "event_id": event.pk,
            "booking_id": booking.pk,
            "booking_code": f"BK{booking.pk:06d}",
            "nights": nights,
            "room_charges": str(room_charges),
            "tax": str(tax),
            "total_amount": str(total),
            "advance_paid": str(advance),
            "balance_due": str(total - advance),
            "payment_status": pay_status,
            "_booking": booking,  # popped before the response is sent
        }


# ═════════════════════════════════════════════════════════════
# iCal feed (ERP → OTA). No guest names are exposed.
# ═════════════════════════════════════════════════════════════
@method_decorator(csrf_exempt, name="dispatch")
class ICalFeedView(View):

    def get(self, request, hotel_token):
        from accounts.models import Hotel
        from pms.models import Booking

        hotel = get_object_or_404(Hotel, ical_token=hotel_token)
        bookings = Booking.objects.filter(
            room_unit__room__hotel=hotel, status__in=ACTIVE_STATUSES,
        ).select_related("room_unit")

        stamp = dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0",
            f"PRODID:-//ERP//{hotel.hotel_name}//EN",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        ]
        for b in bookings:
            lines += [
                "BEGIN:VEVENT",
                f"UID:booking-{b.pk}@erp",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{b.check_in:%Y%m%d}",
                f"DTEND;VALUE=DATE:{b.check_out:%Y%m%d}",
                "SUMMARY:Reserved",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        lines.append("END:VCALENDAR")
        return HttpResponse("\r\n".join(lines), content_type="text/calendar; charset=utf-8")


# ═════════════════════════════════════════════════════════════
# OTA webhook (only for OTAs / channel managers that PUSH to you).
# Booking.com normally requires pull + acknowledge — build that as a
# scheduled task in your adapter rather than here.
# ═════════════════════════════════════════════════════════════
def _find_ota_schema(channel_id, header_schema):
    from customers.models import Client
    from django_tenants.utils import schema_context

    def has(schema):
        with schema_context(schema):
            return OTAChannel.objects.filter(pk=channel_id, is_active=True).exists()

    if header_schema and has(header_schema):
        return header_schema
    for tenant in Client.objects.exclude(schema_name="public"):
        if has(tenant.schema_name):
            return tenant.schema_name
    return None


@method_decorator(csrf_exempt, name="dispatch")
class OTAWebhookReceiveView(View):

    def post(self, request, channel_id):
        from django_tenants.utils import schema_context

        schema = _find_ota_schema(channel_id, request.headers.get("X-DTS-Schema", "").strip())
        if not schema:
            return JsonResponse({"error": "Not found."}, status=404)

        with schema_context(schema):
            channel = OTAChannel.objects.get(pk=channel_id, is_active=True)

            incoming = request.headers.get("X-Webhook-Secret", "")
            if not channel.webhook_secret or not hmac.compare_digest(
                incoming.encode(), channel.webhook_secret.encode()
            ):
                return JsonResponse({"error": "Forbidden."}, status=403)

            payload = _json_body(request)
            if payload is None:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            event_type = payload.get("event_type", "booking_created")
            event = WebhookEvent.objects.create(
                ota_channel=channel, event_type=event_type,
                headers=_safe_headers(request), payload=payload,
                raw_body=request.body.decode("utf-8", errors="replace"),
                status="processing", attempts=1,
            )

            handler = {
                "booking_created": _handle_ota_booking_created,
                "booking_cancelled": _handle_ota_booking_cancelled,
                "booking_modified": _handle_ota_booking_modified,
            }.get(event_type)
            if not handler:
                event.status = "ignored"
                event.save(update_fields=["status"])
                return JsonResponse({"received": True, "action": "ignored"})

            try:
                return JsonResponse(handler(channel, payload, event), status=202)
            except ValueError as exc:
                _fail_event(event, {"ota_channel": channel}, exc)
                return JsonResponse({"error": str(exc)}, status=422)
            except Exception as exc:  # noqa: BLE001
                log.exception("OTA webhook failed (channel=%s)", channel_id)
                _fail_event(event, {"ota_channel": channel}, exc)
                return JsonResponse({"error": "Could not process event."}, status=500)


def _ota_source(channel):
    return f"ota:{channel.channel_type}"


def _ota_ref(payload):
    ref = str(payload.get("ota_booking_ref") or "").strip()
    if not ref:
        raise ValueError("ota_booking_ref is required.")
    return ref


def _find_ota_booking(channel, ref):
    from pms.models import Booking
    return Booking.objects.filter(source=_ota_source(channel), external_ref=ref).first()


def _ota_price(room, nights, payload):
    """Prefer what the OTA charged; otherwise base price + default tax."""
    total = _d(payload.get("total_amount"))
    if total is not None:
        tax = _d(payload.get("tax_amount")) or Decimal("0")
        return total - tax, tax, total
    charges = Decimal(str(room.base_price)) * nights
    tax = (charges * TAX_RATE).quantize(Decimal("0.01"))
    return charges, tax, charges + tax


def _handle_ota_booking_created(channel, payload, event):
    from billing.models import BillingPayment, FolioCharge, GuestFolio
    from pms.models import Booking, Guest, Payment, Room

    ref = _ota_ref(payload)

    existing = _find_ota_booking(channel, ref)
    if existing:  # the OTA retried — stay idempotent
        event.booking, event.status, event.processed_at = existing, "ignored", timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])
        return {"received": True, "action": "duplicate", "booking_id": existing.pk}

    mapping = (
        OTARoomMapping.objects
        .filter(ota_channel=channel, ota_room_id=str(payload.get("ota_room_id", "")), is_active=True)
        .select_related("internal_room").first()
    )
    if not mapping:
        raise ValueError(f"OTA room {payload.get('ota_room_id')} is not mapped to an ERP room type.")
    room = mapping.internal_room

    check_in, check_out = _parse_date(payload.get("check_in")), _parse_date(payload.get("check_out"))
    if not check_in or not check_out or check_out <= check_in:
        raise ValueError("Valid check_in and check_out dates are required.")
    nights = (check_out - check_in).days
    adults, children = int(payload.get("adults", 1)), int(payload.get("children", 0))
    charges, tax, total = _ota_price(room, nights, payload)
    advance = min(_d(payload.get("advance_amount")) or Decimal("0"), total)
    pay_status = "paid" if advance >= total else ("partial" if advance > 0 else "pending")

    phone = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip()
    name = (payload.get("full_name") or "OTA Guest").strip()

    with transaction.atomic():
        Room.objects.select_for_update().get(pk=room.pk)  # serialise per room type
        unit = _free_unit(room, check_in, check_out)
        if not unit:
            raise ValueError(f"No availability for {room} on those dates (possible overbooking).")

        if email:
            guest, _ = Guest.objects.get_or_create(email=email, defaults={"full_name": name, "phone": phone})
        elif phone:
            guest, _ = Guest.objects.get_or_create(phone=phone, defaults={"full_name": name, "email": ""})
        else:
            guest = Guest.objects.create(full_name=name, email="", phone="")

        booking = Booking.objects.create(
            guest=guest, room=room, room_unit=unit,
            check_in=check_in, check_out=check_out,
            adults=adults, children=children, guests_count=adults + children,
            base_price=room.base_price, tax=tax, total_amount=total,
            status="confirmed", source=_ota_source(channel), external_ref=ref,
            special_requests=payload.get("special_requests", ""),
        )
        Payment.objects.create(
            booking=booking, room_charges=charges, tax=tax, total_amount=total,
            amount_paid=advance, payment_status=pay_status,
            payment_method=payload.get("advance_method") if advance > 0 else None,
            paid_at=timezone.now() if advance > 0 else None,
        )
        folio = GuestFolio.objects.create(booking=booking)
        FolioCharge.objects.create(
            folio=folio, charge_type="room",
            description=f"{room.room_type} Room Charge ({nights} night{'s' if nights != 1 else ''})",
            amount=charges, tax_amount=tax, date=check_in,
        )
        if advance > 0:
            BillingPayment.objects.create(
                folio=folio, amount=advance,
                method=payload.get("advance_method", "OTA"),
                note=f"Prepaid via {channel.name}",
            )
        event.booking, event.status, event.processed_at = booking, "done", timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])

    SyncLog.objects.create(
        ota_channel=channel, direction="pull", entity="booking", outcome="success",
        records_sent=1, detail=f"BK{booking.pk:06d} created from {channel.name} (ref {ref})",
    )
    _resync_inventory(channel.hotel)

    return {
        "received": True, "event_id": event.pk, "booking_id": booking.pk,
        "booking_code": f"BK{booking.pk:06d}", "total_amount": str(total),
        "payment_status": pay_status,
    }


def _handle_ota_booking_cancelled(channel, payload, event):
    ref = _ota_ref(payload)
    booking = _find_ota_booking(channel, ref)
    if not booking:
        raise ValueError(f"No booking with reference {ref}.")

    if booking.status == "cancelled":
        event.booking, event.status, event.processed_at = booking, "ignored", timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])
        return {"received": True, "action": "already_cancelled", "booking_id": booking.pk}

    with transaction.atomic():
        booking.status = "cancelled"
        booking.save(update_fields=["status"])
        event.booking, event.status, event.processed_at = booking, "done", timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])

    SyncLog.objects.create(
        ota_channel=channel, direction="pull", entity="cancellation", outcome="success",
        records_sent=1, detail=f"BK{booking.pk:06d} cancelled from {channel.name} (ref {ref})",
    )
    _resync_inventory(channel.hotel)
    return {"received": True, "action": "cancelled", "booking_id": booking.pk}


def _handle_ota_booking_modified(channel, payload, event):
    from pms.models import Booking, Room

    ref = _ota_ref(payload)
    booking = _find_ota_booking(channel, ref)
    if not booking:
        raise ValueError(f"No booking with reference {ref}.")
    if booking.status == "cancelled":
        raise ValueError("Booking is cancelled and cannot be modified.")

    with transaction.atomic():
        Room.objects.select_for_update().get(pk=booking.room_id)

        check_in = _parse_date(payload.get("check_in")) or booking.check_in
        check_out = _parse_date(payload.get("check_out")) or booking.check_out
        if check_out <= check_in:
            raise ValueError("check_out must be after check_in.")

        if (check_in, check_out) != (booking.check_in, booking.check_out):
            free_unit = _free_unit(booking.room, check_in, check_out, exclude_booking_id=booking.pk)
            if not free_unit:
                raise ValueError("The new dates are not available.")
            clash = Booking.objects.filter(
                room_unit=booking.room_unit, status__in=ACTIVE_STATUSES,
                check_in__lt=check_out, check_out__gt=check_in,
            ).exclude(pk=booking.pk).exists()
            if clash:  # keep the current unit if still free, otherwise move
                booking.room_unit = free_unit
            booking.check_in, booking.check_out = check_in, check_out

        if payload.get("adults"):
            booking.adults = int(payload["adults"])
        if payload.get("children") is not None:
            booking.children = int(payload["children"])
        booking.guests_count = booking.adults + booking.children
        if payload.get("special_requests"):
            booking.special_requests = payload["special_requests"]

        nights = (booking.check_out - booking.check_in).days
        _, tax, total = _ota_price(booking.room, nights, payload)
        booking.tax, booking.total_amount = tax, total
        booking.save()

        event.booking, event.status, event.processed_at = booking, "done", timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])

    # NOTE: also update the folio room charge and pms.Payment totals here if
    # you want the bill to follow date changes.
    SyncLog.objects.create(
        ota_channel=channel, direction="pull", entity="booking", outcome="success",
        records_sent=1, detail=f"BK{booking.pk:06d} modified from {channel.name} (ref {ref})",
    )
    _resync_inventory(channel.hotel)
    return {"received": True, "action": "modified", "booking_id": booking.pk}


# ═════════════════════════════════════════════════════════════
# Page views (HTML shells; data loads in the browser from the JSON APIs)
# ═════════════════════════════════════════════════════════════
@never_cache
@login_required
def channel_manager_page(request):
    hotel = getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")

    return render(request, "hotel/channel_manager.html", {
        "hotel": hotel,
        "today": timezone.now().date(),
        "ota_types": OTAChannel._meta.get_field("channel_type").choices,
        # Set to a real URL, e.g. reverse("your-rates-page"), to show the
        # "View Rate & Inventory" quick action. Empty string hides it.
        "rates_url": "",
    })


@never_cache
@login_required
def website_channels_page(request):
    hotel = getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")
    return render(request, "hotel/website_channels.html", {"hotel": hotel})


@never_cache
@login_required
def ota_channels_page(request):
    hotel = getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")
    return render(request, "hotel/ota_channels.html", {"hotel": hotel})


@never_cache
@login_required
def sync_logs_page(request):
    hotel = getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")

    today = timezone.now().date()
    return render(request, "hotel/sync_logs.html", {
        "hotel": hotel,
        "website_channels": WebsiteChannel.objects.filter(hotel=hotel),
        "ota_channels": OTAChannel.objects.filter(hotel=hotel),
        "default_from": (today - timedelta(days=6)).isoformat(),
        "default_to": today.isoformat(),
    })


@never_cache  # the "@" was missing in the old file, so this decorator never ran
@login_required
def webhook_events_page(request):
    hotel = getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")

    today = timezone.now().date()
    return render(request, "hotel/webhook_events.html", {
        "hotel": hotel,
        "website_channels": WebsiteChannel.objects.filter(hotel=hotel),
        "ota_channels": OTAChannel.objects.filter(hotel=hotel),
        "default_from": (today - timedelta(days=6)).isoformat(),
        "default_to": today.isoformat(),
    })


