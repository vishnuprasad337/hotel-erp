import requests
from django.utils import timezone
from django.db.models import Q
from datetime import date
from .models import WebsiteChannel, SyncLog


def push_booking_to_channel(channel_pk, booking_pk):
    from pms.models import Booking
    try:
        channel = WebsiteChannel.objects.get(pk=channel_pk, is_active=True)
        booking = Booking.objects.select_related("guest", "room", "room_unit").get(pk=booking_pk)
    except Exception:
        return

    payload = {
        "event":        "booking_created",
        "booking_id":   booking.pk,
        "booking_code": f"BK{booking.pk:06d}",
        "room_type":    booking.room.room_type,
        "room_number":  booking.room_unit.room_number if booking.room_unit else None,
        "check_in":     str(booking.check_in),
        "check_out":    str(booking.check_out),
        "adults":       booking.adults,
        "children":     booking.children,
        "total_amount": str(booking.total_amount),
        "status":       booking.status,
        "source":       booking.source,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key":    channel.outbound_api_key,
    }

    start        = timezone.now()
    outcome      = "success"
    error_detail = ""

    try:
        resp = requests.post(channel.callback_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        channel.last_sync  = timezone.now()
        channel.sync_error = ""
        channel.save(update_fields=["last_sync", "sync_error", "updated_at"])
    except Exception as e:
        outcome      = "failed"
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


def push_availability_to_channel(channel_pk):
    from pms.models import Room, RoomUnit

    try:
        channel = WebsiteChannel.objects.get(pk=channel_pk, is_active=True)
    except WebsiteChannel.DoesNotExist:
        return

    if not channel.callback_url:
        SyncLog.objects.create(
            website_channel=channel,
            direction="push",
            entity="rate",
            outcome="failed",
            records_sent=0,
            records_failed=0,
            duration_ms=0,
            detail="callback_url is not set on channel",
        )
        return

    today = date.today()
    rooms = Room.objects.filter(is_active=True).prefetch_related("units")

    availability = []
    for room in rooms:
        total_units = room.units.count()
        if total_units == 0:
            continue

        occupied_units = RoomUnit.objects.filter(
            room=room,
        ).filter(
            Q(booking__status__in=["confirmed", "checked_in"]) &
            Q(booking__check_in__lte=today) &
            Q(booking__check_out__gt=today)
        ).distinct().count()

        unavailable_units = RoomUnit.objects.filter(
            room=room,
            status__in=["Maintenance", "Cleaning", "Dirty"]
        ).count()

        available = max(0, total_units - occupied_units - unavailable_units)

        availability.append({
            "room_id":         room.pk,
            "room_type":       room.room_type,
            "base_price":      str(room.base_price),
            "total_units":     total_units,
            "occupied_units":  occupied_units,
            "available_rooms": available,
        })

    if not availability:
        return

    payload = {
        "event":        "availability_sync",
        "synced_at":    timezone.now().isoformat(),
        "availability": availability,
    }

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key":    channel.outbound_api_key,
    }

    start        = timezone.now()
    outcome      = "success"
    error_detail = ""

    try:
        resp = requests.post(channel.callback_url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        channel.last_sync  = timezone.now()
        channel.sync_error = ""
        channel.save(update_fields=["last_sync", "sync_error", "updated_at"])
    except Exception as e:
        outcome      = "failed"
        error_detail = str(e)
        channel.sync_error = error_detail
        channel.save(update_fields=["sync_error", "updated_at"])

    duration_ms = int((timezone.now() - start).total_seconds() * 1000)
    SyncLog.objects.create(
        website_channel=channel,
        direction="push",
        entity="rate",
        outcome=outcome,
        records_sent=len(availability) if outcome == "success" else 0,
        records_failed=0 if outcome == "success" else len(availability),
        duration_ms=duration_ms,
        detail=error_detail,
    )