from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
import json
import requests

from .models import WebsiteChannel, OTAChannel, ChannelRate, SyncLog, WebhookEvent,DeletedWebsiteChannelKey



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


def ota_to_dict(ch):
    return {
        "id": ch.pk,
        "name": ch.name,
        "channel_type": ch.channel_type,
        "channel_type_display": ch.get_channel_type_display(),
        "auth_method": ch.auth_method,
        "protocol": ch.protocol,                              # NEW
        "hotel_id_on_ota": ch.hotel_id_on_ota,
        "property_code": ch.property_code,
        "ical_url": ch.ical_url,
        "webhook_url": ch.webhook_url,                        # NEW
        "supports_webhook": ch.supports_webhook,              # NEW
        "sync_interval_minutes": ch.sync_interval_minutes,   # NEW
        "push_rates": ch.push_rates,
        "push_availability": ch.push_availability,
        "pull_bookings": ch.pull_bookings,
        "sync_days_ahead": ch.sync_days_ahead,
        "is_active": ch.is_active,
        "last_sync": ch.last_sync.isoformat() if ch.last_sync else None,
        "sync_error": ch.sync_error,
        "is_ical": ch.is_ical,
        "oauth_is_expired": ch.oauth_is_expired,
        "created_at": ch.created_at.isoformat(),
        "updated_at": ch.updated_at.isoformat(),
    }

def webhook_event_to_dict(ev):
    return {
        "id": ev.pk,
        "event_type": ev.event_type,
        "status": ev.status,
        "attempts": ev.attempts,
        "last_error": ev.last_error,
        "booking_id": ev.booking_id,
        "website_channel_id": ev.website_channel_id,
        "ota_channel_id": ev.ota_channel_id,
        "payload": ev.payload,
        "received_at": ev.received_at.isoformat(),
        "processed_at": ev.processed_at.isoformat() if ev.processed_at else None,
    }


def sync_log_to_dict(log):
    return {
        "id": log.pk,
        "direction": log.direction,
        "entity": log.entity,
        "outcome": log.outcome,
        "records_sent": log.records_sent,
        "records_failed": log.records_failed,
        "duration_ms": log.duration_ms,
        "detail": log.detail,
        "website_channel_id": log.website_channel_id,
        "ota_channel_id": log.ota_channel_id,
        "created_at": log.created_at.isoformat(),
    }



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

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": channel.outbound_api_key,
    }

    start = timezone.now()
    outcome = "success"
    error_detail = ""

    try:
        resp = requests.post(channel.callback_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        channel.last_sync = timezone.now()
        channel.sync_error = ""
        channel.save(update_fields=["last_sync", "sync_error", "updated_at"])
    except Exception as e:
        outcome = "failed"
        error_detail = str(e)
        channel.sync_error = error_detail
        channel.save(update_fields=["sync_error", "updated_at"])

    duration_ms = int((timezone.now() - start).total_seconds() * 1000)
    SyncLog.objects.create(
        website_channel=channel,
        direction="push",
        entity="booking",
        outcome=outcome,
        records_sent=1 if outcome == "success" else 0,
        records_failed=0 if outcome == "success" else 1,
        duration_ms=duration_ms,
        detail=error_detail,
    )


def send_connect_request(channel):
    hotel = channel.hotel
    base_url = getattr(settings, "CMS_PUBLIC_URL", "http://localhost:8000")
    erp_url = base_url

    try:
        requests.post(
            f"{channel.base_url}/api/update-webhook-key/",
            json={
                "hotel_name":  hotel.hotel_name,
                "new_api_key": channel.inbound_api_key,
                "webhook_url": f"{erp_url}/channels/webhook/{channel.inbound_api_key}/",
            },
            timeout=5,
        )
    except Exception:
        pass

    payload = {
        "hotel_name":      hotel.hotel_name,
        "hotel_id":        hotel.pk,
        "site_name":       channel.site_name,
        "erp_url":         erp_url,
        "schema_name":     hotel.schema_name,
        "inbound_api_key": channel.inbound_api_key,
        "webhook_url":     f"{erp_url}/channels/webhook/{channel.inbound_api_key}/",
    }

    try:
        resp = requests.post(
            f"{channel.base_url}/connect-request/",
            json=payload,
            timeout=5,
        )
        if resp.status_code in [200, 201]:
            channel.status     = "pending"
            channel.is_active  = False
            channel.sync_error = ""
        else:
            channel.status     = "pending"
            channel.is_active  = False
            channel.sync_error = f"Website returned {resp.status_code}"
    except Exception as e:
        channel.status     = "pending"
        channel.is_active  = False
        channel.sync_error = f"Connect request error: {e}"

    channel.save(update_fields=["status", "is_active", "sync_error", "updated_at"])
    return channel.status
@method_decorator(csrf_exempt, name="dispatch")
class WebsiteChannelListView(View):

    def get(self, request):
        channels = WebsiteChannel.objects.filter(hotel=request.user.hotel)
        return JsonResponse({"results": [channel_to_dict(c) for c in channels]})

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        required = ["site_name", "base_url", "outbound_api_key"]
        for field in required:
            if not data.get(field):
                return JsonResponse({"error": f"{field} is required"}, status=400)

        if WebsiteChannel.objects.filter(hotel=request.user.hotel).exists():
            return JsonResponse(
                {"error": "A website channel already exists for this hotel."},
                status=409,
            )

        preserved_key = (
            DeletedWebsiteChannelKey.objects
            .filter(hotel=request.user.hotel)
            .order_by("-deleted_at")
            .values_list("inbound_api_key", flat=True)
            .first()
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

        response_data = channel_to_dict(channel)
        response_data["connect_status"] = status

        return JsonResponse(response_data, status=201)

@method_decorator(csrf_exempt, name="dispatch")
class WebsiteChannelDetailView(View):

    def get_channel(self, request, pk):
        return get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)

    def get(self, request, pk):
        return JsonResponse(channel_to_dict(self.get_channel(request, pk)))

    def patch(self, request, pk):
        channel = self.get_channel(request, pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        updatable = [
            "site_name", "base_url", "callback_url", "outbound_api_key",
            "sync_availability", "sync_interval_minutes", "is_active",
        ]
        for field in updatable:
            if field in data:
                setattr(channel, field, data[field])
        channel.save()
        return JsonResponse(channel_to_dict(channel))

    def delete(self, request, pk):
        channel = self.get_channel(request, pk)
        DeletedWebsiteChannelKey.objects.update_or_create(
        hotel=request.user.hotel,
        defaults={
            "inbound_api_key": channel.inbound_api_key,
            "deleted_at": timezone.now(),
        }
    )
        channel.delete()
        return JsonResponse({"deleted": True})


@method_decorator(csrf_exempt, name="dispatch")
class WebsiteChannelToggleView(View):

    def patch(self, request, pk):
        channel = get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)
        channel.is_active = not channel.is_active
        channel.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"id": channel.pk, "is_active": channel.is_active})

from .tasks import push_booking_to_channel, push_availability_to_channel
@method_decorator(csrf_exempt, name="dispatch")
class WebsiteChannelSyncView(View):

    def post(self, request, pk):
        channel = get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)
        if not channel.is_active:
            return JsonResponse(
                {"error": "Channel is inactive. Enable it before syncing."},
                status=400,
            )

        push_availability_to_channel(channel.pk)

        return JsonResponse({"detail": "Sync triggered.", "last_sync": channel.last_sync.isoformat()})
@method_decorator(csrf_exempt, name="dispatch")
class WebsiteChannelRotateKeyView(View):

    def post(self, request, pk):
        channel = get_object_or_404(WebsiteChannel, pk=pk, hotel=request.user.hotel)
        new_key = channel.rotate_inbound_key()

        # notify website about new key
        if channel.base_url:
            try:
                requests.post(
                    f"{channel.base_url}/api/update-webhook-key/",
                    json={
                        "hotel_name":  channel.hotel.hotel_name,
                        "new_api_key": new_key,
                        "webhook_url": f"http://127.0.0.1:8000/channels/webhook/{new_key}/",
                    },
                    timeout=5,
                )
            except Exception:
                pass

        return JsonResponse({"id": channel.pk, "inbound_api_key": new_key})


@method_decorator(csrf_exempt, name="dispatch")
class WebsiteConnectResponseView(View):

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        api_key = data.get("inbound_api_key")
        if not api_key:
            return JsonResponse({"error": "inbound_api_key is required"}, status=400)

        from django_tenants.utils import schema_context
        from customers.models import Client

        print(f"DEBUG ConnectResponse: api_key={api_key} accepted={data.get('accepted')}")

        target_schema = None
        for tenant in Client.objects.exclude(schema_name='public'):
            with schema_context(tenant.schema_name):
                if WebsiteChannel.objects.filter(inbound_api_key=api_key).exists():
                    target_schema = tenant.schema_name
                    print(f"DEBUG ConnectResponse: found in schema={target_schema}")
                    break

        if not target_schema:
            print(f"DEBUG ConnectResponse: no channel found for api_key={api_key}")
            return JsonResponse({"error": "No channel found for this API key."}, status=404)

        with schema_context(target_schema):
            channel = WebsiteChannel.objects.get(inbound_api_key=api_key)
            print(f"DEBUG ConnectResponse: channel={channel} current is_active={channel.is_active} status={channel.status}")

            if data.get("accepted"):
                channel.status     = "approved"
                channel.is_active  = True
                channel.sync_error = ""

                fields_to_update = ["status", "is_active", "sync_error", "updated_at"]
                if data.get("callback_url"):
                    channel.callback_url = data["callback_url"]
                    fields_to_update.append("callback_url")

                channel.save(update_fields=fields_to_update)
                try:
                    from .tasks import push_availability_to_channel
                    push_availability_to_channel(channel.pk)
                except Exception as e:
                    print(f"Auto sync failed: {e}")
                print(f"DEBUG ConnectResponse: approved! is_active={channel.is_active} callback_url={channel.callback_url}")
                return JsonResponse({
                    "detail":       "Connection approved. Ready to receive bookings.",
                    "is_active":    channel.is_active,
                    "status":       channel.status,
                    "callback_url": channel.callback_url,
                })
            else:
                channel.status    = "rejected"
                channel.is_active = False
                channel.save(update_fields=["status", "is_active", "updated_at"])

                print(f"DEBUG ConnectResponse: rejected")
                return JsonResponse({"detail": "Connection rejected."})
@method_decorator(csrf_exempt, name="dispatch")
class OTAChannelListView(View):

    def get(self, request):
        channels = OTAChannel.objects.filter(hotel=request.user.hotel)
        return JsonResponse({"results": [ota_to_dict(c) for c in channels]})

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if not data.get("name") or not data.get("channel_type"):
            return JsonResponse({"error": "name and channel_type are required"}, status=400)

        channel = OTAChannel.objects.create(
            hotel=request.user.hotel,
            name=data["name"],
            channel_type=data["channel_type"],
            auth_method=data.get("auth_method", "api_key"),
            api_key=data.get("api_key", ""),
            api_secret=data.get("api_secret", ""),
            hotel_id_on_ota=data.get("hotel_id_on_ota", ""),
            ical_url=data.get("ical_url", ""),
            push_rates=data.get("push_rates", True),
            push_availability=data.get("push_availability", True),
            pull_bookings=data.get("pull_bookings", True),
            sync_days_ahead=data.get("sync_days_ahead", 90),
        )
        return JsonResponse(ota_to_dict(channel), status=201)


@method_decorator(csrf_exempt, name="dispatch")
class OTAChannelDetailView(View):
 
    def get_channel(self, request, pk):
        return get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
 
    def get(self, request, pk):
        return JsonResponse(ota_to_dict(self.get_channel(request, pk)))
 
    def patch(self, request, pk):
        channel = self.get_channel(request, pk)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
 
        updatable = [
            "name", "api_key", "api_secret", "hotel_id_on_ota", "property_code",
            "ical_url", "ical_push_url", "push_rates", "push_availability",
            "pull_bookings", "sync_days_ahead", "is_active",
            # NEW fields
            "protocol", "webhook_url", "supports_webhook",
            "sync_interval_minutes", "oauth_token_endpoint",
        ]
        for field in updatable:
            if field in data:
                setattr(channel, field, data[field])
        channel.save()
        return JsonResponse(ota_to_dict(channel))
 
    def delete(self, request, pk):
        self.get_channel(request, pk).delete()
        return JsonResponse({"deleted": True})

@method_decorator(csrf_exempt, name="dispatch")
class OTAChannelToggleView(View):

    def patch(self, request, pk):
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        channel.is_active = not channel.is_active
        channel.save(update_fields=["is_active", "updated_at"])
        return JsonResponse({"id": channel.pk, "is_active": channel.is_active})




class WebhookEventListView(View):

    def get(self, request):
        qs = WebhookEvent.objects.filter(
            website_channel__hotel=request.user.hotel
        ).select_related("website_channel", "booking")

        channel_id   = request.GET.get("channel")
        event_status = request.GET.get("status")
        if channel_id:
            qs = qs.filter(website_channel_id=channel_id)
        if event_status:
            qs = qs.filter(status=event_status)

        return JsonResponse({"results": [webhook_event_to_dict(e) for e in qs[:100]]})

@method_decorator(csrf_exempt, name="dispatch")
class WebhookReceiveView(View):

    def post(self, request, api_key):
        from django_tenants.utils import schema_context
        from customers.models import Client

        schema_from_header = request.headers.get("X-DTS-Schema", "").strip()
        target_schema = None

        if schema_from_header:
            with schema_context(schema_from_header):
                if WebsiteChannel.objects.filter(inbound_api_key=api_key, is_active=True).exists():
                    target_schema = schema_from_header

        if not target_schema:
            for tenant in Client.objects.exclude(schema_name='public'):
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

            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)

            event = WebhookEvent.objects.create(
                website_channel=channel,
                event_type=payload.get("event_type", "booking_created"),
                headers=dict(request.headers),
                payload=payload,
                raw_body=request.body.decode("utf-8", errors="replace"),
                status="processing",
                attempts=1,
            )

            try:
                from pms.models import Room, RoomUnit, Guest, Booking
                from pms.models import Payment
                from billing.models import GuestFolio, FolioCharge, BillingPayment
                from datetime import datetime as dt
                from django.db import transaction

                check_in  = dt.strptime(payload["check_in"],  "%Y-%m-%d").date()
                check_out = dt.strptime(payload["check_out"], "%Y-%m-%d").date()
                room      = Room.objects.get(pk=payload["room_id"])
                room_unit = RoomUnit.objects.get(pk=payload["room_unit_id"])

                if room_unit.status in ["Maintenance", "Cleaning", "Dirty"]:
                    raise ValueError(f"Room {room_unit.room_number} is {room_unit.status} and cannot be booked.")

                conflict = Booking.objects.filter(
                    room_unit=room_unit,
                    status__in=["confirmed", "checked_in"],
                    check_in__lt=check_out,
                    check_out__gt=check_in,
                ).exists()
                if conflict:
                    raise ValueError(f"Room {room_unit.room_number} is already booked for those dates.")

                phone     = payload.get("phone", "").strip()
                email     = payload.get("email", "").strip()
                full_name = payload.get("full_name", "").strip()

                if email:
                    guest, created = Guest.objects.get_or_create(
                        email=email,
                        defaults={"full_name": full_name, "phone": phone},
                    )
                elif phone:
                    guest, created = Guest.objects.get_or_create(
                        phone=phone,
                        defaults={"full_name": full_name, "email": email},
                    )
                else:
                    guest   = Guest.objects.create(full_name=full_name, email=email, phone=phone)
                    created = True

                if not created and full_name:
                    guest.full_name = full_name
                    guest.save(update_fields=["full_name"])

                nights         = (check_out - check_in).days
                room_charges   = float(room.base_price) * nights
                tax            = round(room_charges * 0.18, 2)
                total          = round(room_charges + tax, 2)
                advance_amount = float(payload.get("advance_amount") or 0)
                advance_method = payload.get("advance_method") or "Online"

                if advance_amount > total:
                    advance_amount = total

                if advance_amount <= 0:
                    pay_status = "pending"
                elif advance_amount >= total:
                    pay_status = "paid"
                else:
                    pay_status = "partial"

                with transaction.atomic():
                    booking = Booking.objects.create(
                        guest            = guest,
                        room             = room,
                        room_unit        = room_unit,
                        check_in         = check_in,
                        check_out        = check_out,
                        adults           = int(payload.get("adults", 1)),
                        children         = int(payload.get("children", 0)),
                        guests_count     = int(payload.get("adults", 1)) + int(payload.get("children", 0)),
                        base_price       = room.base_price,
                        tax              = tax,
                        total_amount     = total,
                        status           = "confirmed",
                        source           = f"website:{channel.site_name}",
                        special_requests = payload.get("special_requests", ""),
                    )

                    Payment.objects.create(
                        booking        = booking,
                        room_charges   = round(room_charges, 2),
                        tax            = tax,
                        total_amount   = total,
                        amount_paid    = round(advance_amount, 2),
                        payment_status = pay_status,
                        payment_method = advance_method if advance_amount > 0 else None,
                        paid_at        = timezone.now() if advance_amount > 0 else None,
                    )

                    folio = GuestFolio.objects.create(booking=booking)

                    FolioCharge.objects.create(
                        folio       = folio,
                        charge_type = "room",
                        description = f"{room.room_type} Room Charge ({nights} night{'s' if nights > 1 else ''})",
                        amount      = round(room_charges, 2),
                        tax_amount  = tax,
                        date        = check_in,
                    )

                    if advance_amount > 0:
                        BillingPayment.objects.create(
                            folio  = folio,
                            amount = round(advance_amount, 2),
                            method = advance_method,
                            note   = f"Advance payment via {channel.site_name}",
                        )

                    event.booking      = booking
                    event.status       = "done"
                    event.processed_at = timezone.now()
                    event.save(update_fields=["booking", "status", "processed_at"])

                SyncLog.objects.create(
                    website_channel=channel,
                    direction="pull",
                    entity="booking",
                    outcome="success",
                    records_sent=1,
                    records_failed=0,
                    detail=f"Booking BK{booking.pk:06d} created from {channel.site_name}",
                )

                if channel.callback_url and channel.outbound_api_key:
                    from .tasks import push_booking_to_channel, push_availability_to_channel
                    push_booking_to_website(channel, booking)
                    push_availability_to_channel(channel.pk)

                return JsonResponse({
                    "received":        True,
                    "event_id":        event.pk,
                    "booking_id":      booking.pk,
                    "booking_code":    f"BK{booking.pk:06d}",
                    "nights":          nights,
                    "room_charges":    round(room_charges, 2),
                    "tax":             tax,
                    "total_amount":    total,
                    "advance_paid":    round(advance_amount, 2),
                    "balance_due":     round(total - advance_amount, 2),
                    "payment_status":  pay_status,
                }, status=202)

            except Exception as e:
                event.status       = "failed"
                event.last_error   = str(e)
                event.processed_at = timezone.now()
                event.save(update_fields=["status", "last_error", "processed_at"])

                SyncLog.objects.create(
                    website_channel=channel,
                    direction="pull",
                    entity="booking",
                    outcome="failed",
                    records_sent=0,
                    records_failed=1,
                    detail=str(e),
                )

                return JsonResponse({"error": str(e)}, status=500)
class SyncLogListView(View):

    def get(self, request):
        qs = SyncLog.objects.select_related("website_channel", "ota_channel")
        channel_id = request.GET.get("channel")
        if channel_id:
            qs = qs.filter(website_channel_id=channel_id)
        return JsonResponse({"results": [sync_log_to_dict(log) for log in qs[:100]]})

from .models import OTARoomMapping
 
@method_decorator(csrf_exempt, name="dispatch")
class OTARoomMappingView(View):
 
    def get(self, request, pk):
        
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        mappings = OTARoomMapping.objects.filter(ota_channel=channel).select_related("internal_room")
        return JsonResponse({
            "results": [
                {
                    "id": m.pk,
                    "internal_room_id": m.internal_room_id,
                    "internal_room_name": str(m.internal_room),
                    "ota_room_id": m.ota_room_id,
                    "ota_room_name": m.ota_room_name,
                    "ota_rate_plan_id": m.ota_rate_plan_id,
                    "is_active": m.is_active,
                }
                for m in mappings
            ]
        })
 
    def post(self, request, pk):
        """Create or update a room mapping."""
        channel = get_object_or_404(OTAChannel, pk=pk, hotel=request.user.hotel)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
 
        required = ["internal_room_id", "ota_room_id", "ota_room_name"]
        for field in required:
            if not data.get(field):
                return JsonResponse({"error": f"{field} is required"}, status=400)
 
        mapping, created = OTARoomMapping.objects.update_or_create(
            ota_channel=channel,
            internal_room_id=data["internal_room_id"],
            defaults={
                "ota_room_id":      data["ota_room_id"],
                "ota_room_name":    data["ota_room_name"],
                "ota_rate_plan_id": data.get("ota_rate_plan_id", ""),
                "is_active":        data.get("is_active", True),
            },
        )
        return JsonResponse({
            "id": mapping.pk,
            "created": created,
            "internal_room_id": mapping.internal_room_id,
            "ota_room_id": mapping.ota_room_id,
            "ota_room_name": mapping.ota_room_name,
        }, status=201 if created else 200)
 
    def delete(self, request, pk):
       
        mapping = get_object_or_404(OTARoomMapping, pk=pk, ota_channel__hotel=request.user.hotel)
        mapping.delete()
        return JsonResponse({"deleted": True})
 
 

from django.http import HttpResponse
from datetime import datetime as dt
 
@method_decorator(csrf_exempt, name="dispatch")
class ICalFeedView(View):
    
    def get(self, request, hotel_token):
        from accounts.models import Hotel
        from pms.models import Booking
 
        hotel = get_object_or_404(Hotel, ical_token=hotel_token)
        bookings = Booking.objects.filter(
            room_unit__room__hotel=hotel,
            status__in=["confirmed", "checked_in"],
        ).select_related("guest", "room_unit")
 
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:-//ERP//{hotel.hotel_name}//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
 
        for b in bookings:
            uid = f"booking-{b.pk}@erp"
            dtstart = b.check_in.strftime("%Y%m%d")
            dtend   = b.check_out.strftime("%Y%m%d")
            dtstamp = dt.utcnow().strftime("%Y%m%dT%H%M%SZ")
            summary = f"BLOCKED - {b.guest.full_name}"
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"DTEND;VALUE=DATE:{dtend}",
                f"SUMMARY:{summary}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
 
        lines.append("END:VCALENDAR")
        ical_content = "\r\n".join(lines)
        return HttpResponse(ical_content, content_type="text/calendar; charset=utf-8")
 
 

@method_decorator(csrf_exempt, name="dispatch")
class OTAWebhookReceiveView(View):
   
 
    def post(self, request, channel_id):
        from django_tenants.utils import schema_context
        from customers.models import Client
 
        # Resolve tenant by channel id across schemas
        target_schema = None
        for tenant in Client.objects.exclude(schema_name='public'):
            with schema_context(tenant.schema_name):
                if OTAChannel.objects.filter(pk=channel_id, is_active=True).exists():
                    target_schema = tenant.schema_name
                    break
 
        if not target_schema:
            return JsonResponse({"error": "Channel not found."}, status=404)
 
        with schema_context(target_schema):
            channel = get_object_or_404(OTAChannel, pk=channel_id, is_active=True)
 
           
            if channel.webhook_secret:
                incoming_secret = request.headers.get("X-Webhook-Secret", "")
                if incoming_secret != channel.webhook_secret:
                    return JsonResponse({"error": "Invalid webhook secret."}, status=403)
 
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)
 
            event_type = payload.get("event_type", "booking_created")
 
            event = WebhookEvent.objects.create(
                ota_channel=channel,
                event_type=event_type,
                headers=dict(request.headers),
                payload=payload,
                raw_body=request.body.decode("utf-8", errors="replace"),
                status="processing",
                attempts=1,
            )
 
            try:
                if event_type == "booking_created":
                    result = _handle_ota_booking_created(channel, payload, event)
                elif event_type == "booking_cancelled":
                    result = _handle_ota_booking_cancelled(channel, payload, event)
                elif event_type == "booking_modified":
                    result = _handle_ota_booking_modified(channel, payload, event)
                else:
                    event.status = "ignored"
                    event.save(update_fields=["status"])
                    return JsonResponse({"received": True, "event_type": event_type, "action": "ignored"})
 
                return JsonResponse(result, status=202)
 
            except Exception as e:
                event.status       = "failed"
                event.last_error   = str(e)
                event.processed_at = timezone.now()
                event.save(update_fields=["status", "last_error", "processed_at"])
 
                SyncLog.objects.create(
                    ota_channel=channel,
                    direction="pull",
                    entity="booking",
                    outcome="failed",
                    records_sent=0,
                    records_failed=1,
                    detail=str(e),
                )
                return JsonResponse({"error": str(e)}, status=500)
 
 
def _handle_ota_booking_created(channel, payload, event):
    
    from pms.models import Room, RoomUnit, Guest, Booking, Payment
    from billing.models import GuestFolio, FolioCharge, BillingPayment
    from datetime import datetime as dt
    from django.db import transaction
 
    
    ota_room_id = payload.get("ota_room_id") or payload.get("room_id")
    mapping = OTARoomMapping.objects.filter(
        ota_channel=channel, ota_room_id=str(ota_room_id), is_active=True
    ).select_related("internal_room").first()
 
    if mapping:
        room = mapping.internal_room
    else:
        
        room = Room.objects.get(pk=payload["room_id"])
 
    check_in  = dt.strptime(payload["check_in"],  "%Y-%m-%d").date()
    check_out = dt.strptime(payload["check_out"], "%Y-%m-%d").date()
 
    
    room_unit = RoomUnit.objects.filter(
        room=room, status="Clean"
    ).exclude(
        bookings__status__in=["confirmed", "checked_in"],
        bookings__check_in__lt=check_out,
        bookings__check_out__gt=check_in,
    ).first()
 
    if not room_unit:
        raise ValueError(f"No available room unit for {room.room_type} on requested dates.")
 
    guest, _ = Guest.objects.get_or_create(
        phone=payload.get("phone", "0000000000"),
        defaults={
            "full_name": payload.get("full_name", "OTA Guest"),
            "email":     payload.get("email", ""),
        },
    )
 
    nights       = (check_out - check_in).days
    room_charges = float(room.base_price) * nights
    tax          = round(room_charges * 0.18, 2)
    total        = round(room_charges + tax, 2)
    advance      = float(payload.get("advance_amount") or 0)
    advance      = min(advance, total)
    pay_status   = "paid" if advance >= total else ("partial" if advance > 0 else "pending")
 
    with transaction.atomic():
        booking = Booking.objects.create(
            guest            = guest,
            room             = room,
            room_unit        = room_unit,
            check_in         = check_in,
            check_out        = check_out,
            adults           = int(payload.get("adults", 1)),
            children         = int(payload.get("children", 0)),
            guests_count     = int(payload.get("adults", 1)) + int(payload.get("children", 0)),
            base_price       = room.base_price,
            tax              = tax,
            total_amount     = total,
            status           = "confirmed",
            source           = f"ota:{channel.channel_type}",
            special_requests = payload.get("special_requests", ""),
        )
 
        Payment.objects.create(
            booking        = booking,
            room_charges   = round(room_charges, 2),
            tax            = tax,
            total_amount   = total,
            amount_paid    = round(advance, 2),
            payment_status = pay_status,
            payment_method = payload.get("advance_method") if advance > 0 else None,
            paid_at        = timezone.now() if advance > 0 else None,
        )
 
        folio = GuestFolio.objects.create(booking=booking)
        FolioCharge.objects.create(
            folio       = folio,
            charge_type = "room",
            description = f"{room.room_type} Room Charge ({nights} night{'s' if nights != 1 else ''})",
            amount      = round(room_charges, 2),
            tax_amount  = tax,
            date        = check_in,
        )
 
        if advance > 0:
            BillingPayment.objects.create(
                folio  = folio,
                amount = round(advance, 2),
                method = payload.get("advance_method", "OTA"),
                note   = f"Advance via {channel.name}",
            )
 
        event.booking      = booking
        event.status       = "done"
        event.processed_at = timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])
 
    SyncLog.objects.create(
        ota_channel=channel,
        direction="pull",
        entity="booking",
        outcome="success",
        records_sent=1,
        records_failed=0,
        detail=f"Booking BK{booking.pk:06d} created from OTA {channel.name}",
    )
 
    return {
        "received":       True,
        "event_id":       event.pk,
        "booking_id":     booking.pk,
        "booking_code":   f"BK{booking.pk:06d}",
        "total_amount":   total,
        "advance_paid":   round(advance, 2),
        "balance_due":    round(total - advance, 2),
        "payment_status": pay_status,
    }
 
 
def _handle_ota_booking_cancelled(channel, payload, event):
    
    from pms.models import Booking
    from django.db import transaction
 
    ota_booking_ref = payload.get("ota_booking_ref") or payload.get("booking_id")
    if not ota_booking_ref:
        raise ValueError("ota_booking_ref or booking_id is required for cancellation.")
 
    # Try matching by source + ota ref, or direct booking_id
    booking = (
        Booking.objects.filter(source=f"ota:{channel.channel_type}", pk=ota_booking_ref).first()
        or Booking.objects.filter(pk=ota_booking_ref).first()
    )
 
    if not booking:
        raise ValueError(f"Booking {ota_booking_ref} not found for cancellation.")
 
    if booking.status == "cancelled":
        event.status       = "ignored"
        event.processed_at = timezone.now()
        event.save(update_fields=["status", "processed_at"])
        return {"received": True, "action": "already_cancelled", "booking_id": booking.pk}
 
    with transaction.atomic():
        booking.status = "cancelled"
        booking.save(update_fields=["status"])
 
        event.booking      = booking
        event.status       = "done"
        event.processed_at = timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])
 
    SyncLog.objects.create(
        ota_channel=channel,
        direction="pull",
        entity="cancellation",
        outcome="success",
        records_sent=1,
        records_failed=0,
        detail=f"Booking BK{booking.pk:06d} cancelled from OTA {channel.name}",
    )
 
    
    try:
        from .models import WebsiteChannel
        from .tasks import push_availability_to_channel
        wc = WebsiteChannel.objects.filter(hotel=channel.hotel, is_active=True).first()
        if wc:
            push_availability_to_channel(wc.pk)
    except Exception:
        pass
 
    return {"received": True, "action": "cancelled", "booking_id": booking.pk}
 
 
def _handle_ota_booking_modified(channel, payload, event):
    
    from pms.models import Booking
    from datetime import datetime as dt
    from django.db import transaction
 
    ota_booking_ref = payload.get("ota_booking_ref") or payload.get("booking_id")
    booking = Booking.objects.filter(pk=ota_booking_ref).first()
 
    if not booking:
        raise ValueError(f"Booking {ota_booking_ref} not found for modification.")
 
    with transaction.atomic():
        if payload.get("check_in"):
            booking.check_in  = dt.strptime(payload["check_in"],  "%Y-%m-%d").date()
        if payload.get("check_out"):
            booking.check_out = dt.strptime(payload["check_out"], "%Y-%m-%d").date()
        if payload.get("adults"):
            booking.adults = int(payload["adults"])
        if payload.get("children"):
            booking.children = int(payload["children"])
        if payload.get("special_requests"):
            booking.special_requests = payload["special_requests"]
 
        # Recalculate totals if dates changed
        nights       = (booking.check_out - booking.check_in).days
        room_charges = float(booking.base_price) * nights
        tax          = round(room_charges * 0.18, 2)
        booking.tax          = tax
        booking.total_amount = round(room_charges + tax, 2)
        booking.save()
 
        event.booking      = booking
        event.status       = "done"
        event.processed_at = timezone.now()
        event.save(update_fields=["booking", "status", "processed_at"])
 
    SyncLog.objects.create(
        ota_channel=channel,
        direction="pull",
        entity="booking",
        outcome="success",
        records_sent=1,
        records_failed=0,
        detail=f"Booking BK{booking.pk:06d} modified from OTA {channel.name}",
    )
 
    return {"received": True, "action": "modified", "booking_id": booking.pk}