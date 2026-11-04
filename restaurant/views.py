import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET
from django.db import transaction
from django.db.models import Q, F, Sum, Count
from django.db.models.functions import ExtractHour
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from datetime import timedelta

from .models import (
    MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem,
    TableReservation,
)
from pms.models import Room, RoomUnit, Booking
from billing.models import GuestFolio, FolioCharge, BillingPayment
from accounts.models import Staff, Department
from accounts.decorators import staff_login_required
from hotel.models import Task, Shift, Attendance, LeaveRequest, Payroll


VALID_ORDER_STATUSES = ['pending', 'preparing', 'served', 'cancelled']
TERMINAL_ORDER_STATUSES = ['served', 'cancelled']

def _is_admin(user):
    """Hotel admin = the account created at hotel registration:
    username == email == the hotel's registered email, and no Staff profile.
    Platform superusers are also treated as admins."""
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    # Staff accounts are never admins.
    if hasattr(user, "staff_profile"):
        return False

    email = (user.email or "").strip().lower()
    username = (user.username or "").strip().lower()

    if not email or username != email:
        return False

    hotel = getattr(user, "hotel", None)
    if hotel is not None:
        return (hotel.email or "").strip().lower() == email

    return True


def _get_staff_for_request(request):
    """Staff record for this request, or None (e.g. for admins)."""
    staff = getattr(request.user, "staff_profile", None)
    if staff is None:
        staff_id = request.session.get("staff_id")
        if staff_id:
            staff = Staff.objects.filter(pk=staff_id).first()
    return staff


def _actor_name(staff, user):
    if staff:
        return staff.name
    if user:
        return user.get_full_name() or user.username
    return None
# ════════════════════════════════════════════════════════════════
#  MENU CATEGORIES
# ════════════════════════════════════════════════════════════════

@csrf_exempt
def add_menu_category(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Category name required'}, status=400)
        category = MenuCategory.objects.create(name=name, order=data.get('order', 0))
        return JsonResponse({'success': True, 'id': category.id, 'name': category.name})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def delete_menu_category(request, pk):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    category = get_object_or_404(MenuCategory, pk=pk)
    category.delete()
    return JsonResponse({'success': True})


def list_menu_categories(request):
    categories = MenuCategory.objects.prefetch_related('items').all()
    data = []
    for cat in categories:
        data.append({
            'id': cat.id,
            'name': cat.name,
            'order': cat.order,
            'items': [
                {
                    'id': i.id,
                    'name': i.name,
                    'description': i.description,
                    'price': float(i.price),
                    'tax_percent': float(i.tax_percent),
                    'is_available': i.is_available,
                    'is_veg': i.is_veg,
                    'image': i.image.url if i.image else None,
                }
                for i in cat.items.all()
            ]
        })
    return JsonResponse({'categories': data})


# ════════════════════════════════════════════════════════════════
#  MENU ITEMS
# ════════════════════════════════════════════════════════════════

@csrf_exempt
def add_menu_item(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        category_id = request.POST.get('category_id')
        name = (request.POST.get('name') or '').strip()
        price = request.POST.get('price')

        if not category_id or not name or price is None:
            return JsonResponse({'error': 'category_id, name and price are required'}, status=400)

        category = get_object_or_404(MenuCategory, pk=category_id)

        try:
            price = Decimal(price)
            if price < 0:
                return JsonResponse({'error': 'Price must be positive'}, status=400)
        except Exception:
            return JsonResponse({'error': 'Invalid price format'}, status=400)

        item = MenuItem.objects.create(
            category=category,
            name=name,
            description=request.POST.get('description', ''),
            price=price,
            tax_percent=request.POST.get('tax_percent', 5),
            is_available=request.POST.get('is_available') in ('true', 'True', '1'),
            is_veg=request.POST.get('is_veg') in ('true', 'True', '1'),
            image=request.FILES.get('image')
        )
        return JsonResponse({
            'success': True,
            'id': item.id,
            'name': item.name,
            'image': item.image.url if item.image else None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def update_menu_item(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    item = get_object_or_404(MenuItem, pk=pk)
    try:
        item.name = request.POST.get('name', item.name)
        item.description = request.POST.get('description', item.description)
        item.price = request.POST.get('price', item.price)
        item.tax_percent = request.POST.get('tax_percent', item.tax_percent)
        item.is_available = request.POST.get('is_available') in ('true', 'True', '1')
        item.is_veg = request.POST.get('is_veg') in ('true', 'True', '1')
        if request.FILES.get('image'):
            item.image = request.FILES.get('image')
        item.save()
        return JsonResponse({'success': True, 'image': item.image.url if item.image else None})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def delete_menu_item(request, pk):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    item = get_object_or_404(MenuItem, pk=pk)
    item.delete()
    return JsonResponse({'success': True})


@csrf_exempt
def toggle_item_availability(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    item = get_object_or_404(MenuItem, pk=pk)
    item.is_available = not item.is_available
    item.save()
    return JsonResponse({'success': True, 'is_available': item.is_available})


# ════════════════════════════════════════════════════════════════
# 🪑 TABLES
# ════════════════════════════════════════════════════════════════

@csrf_exempt
def add_table(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        number = data.get('number')
        if not number:
            return JsonResponse({'error': 'Table number required'}, status=400)
        if Table.objects.filter(number=number).exists():
            return JsonResponse({'error': 'Table already exists'}, status=400)
        table = Table.objects.create(number=number, capacity=data.get('capacity', 4))
        return JsonResponse({'success': True, 'id': table.id, 'number': table.number})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def delete_table(request, pk):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)
    table = get_object_or_404(Table, pk=pk)
    table.delete()
    return JsonResponse({'success': True})


def list_tables(request):
    tables = Table.objects.all()
    data = [
        {'id': t.id, 'number': t.number, 'capacity': t.capacity, 'is_occupied': t.is_occupied}
        for t in tables
    ]
    return JsonResponse({'tables': data})


def _free_table_if_needed(order):
    """Release a dine-in table once its order reaches a terminal state,
    but only if no other active order is still using it."""
    if not order.table:
        return
    still_active = RestaurantOrder.objects.filter(
        table=order.table, status__in=['pending', 'preparing']
    ).exclude(pk=order.pk).exists()
    if not still_active:
        order.table.is_occupied = False
        order.table.save(update_fields=['is_occupied'])


def update_table_status(table):
    has_active_order = table.restaurantorder_set.filter(
        status__in=["pending", "preparing"]
    ).exists()
    has_active_reservation = table.tablereservation_set.filter(
        status__in=["reserved", "seated"]
    ).exists()
    table.is_occupied = has_active_order
    table.save()
    return {"occupied": has_active_order, "reservation": has_active_reservation}


# ════════════════════════════════════════════════════════════════
#  ORDER LISTS
# ════════════════════════════════════════════════════════════════

def _room_display(room_unit):
    """Room/RoomUnit doesn't carry a consistent 'room_number' field on Room
    itself - the number lives on RoomUnit. Handle both safely."""
    if room_unit is None:
        return None
    number = getattr(room_unit, 'room_number', None)
    room_type = getattr(getattr(room_unit, 'room', room_unit), 'room_type', None)
    if number and room_type:
        return f"{number} - {room_type}"
    return number or room_type


@login_required
@never_cache
def order_list(request):
    orders = list(
        RestaurantOrder.objects
        .select_related(
            "table",
            "room",
            "served_by",
            "booking__guest",
            "booking__room_unit__room",
            "reservation__table",
            "preparing_by",
            "served_status_by",
            "preparing_by_user",
            "served_status_by_user",
        )
        .prefetch_related("items__item")
        .order_by("-created_at", "-pk")
    )

    payments_by_order = {}

    payments = (
        BillingPayment.objects
        .filter(order_id__in=[order.pk for order in orders])
        .select_related("received_by", "received_by_user")
        .order_by("pk")
    )

    for payment in payments:
        payments_by_order.setdefault(payment.order_id, []).append(payment)

    data = []

    for order in orders:
        guest_name = None
        room_display = None

        if order.booking:
            if order.booking.guest:
                guest_name = order.booking.guest.full_name

            if order.booking.room_unit:
                room_display = _room_display(order.booking.room_unit)

        elif order.reservation:
            guest_name = order.reservation.guest_name

            if order.reservation.table:
                room_display = f"Table {order.reservation.table.number}"

        elif order.room:
            room_display = order.room.room_type

        taken_by = None

        # create_order stores request.user in served_by.
        # This identifies who entered the order, not who served it.
        if order.served_by:
            taken_by = (
                order.served_by.get_full_name()
                or order.served_by.username
            )

        payment_records = payments_by_order.get(order.pk, [])
        latest_payment = payment_records[-1] if payment_records else None

        data.append({
            "id": order.pk,
            "order_number": order.order_number,
            "type": order.order_type,
            "status": order.status,
            "table": order.table.number if order.table else None,
            "room": room_display,
            "guest": guest_name,
            "booking_id": order.booking_id,
            "reservation_id": order.reservation_id,
            "charge_to_room": order.charge_to_room,
            "created_at": order.created_at.isoformat(),

            "order_taken_by": taken_by,

            # Keep this existing API key for other pages.
            "served_by": taken_by,

            "preparing_by": _actor_name(order.preparing_by, order.preparing_by_user),
            "preparing_at": (
                order.preparing_at.isoformat() if order.preparing_at else None
            ),

            "served_status_by": _actor_name(order.served_status_by, order.served_status_by_user),
            "served_status_at": (
                order.served_status_at.isoformat() if order.served_status_at else None
            ),

            "total": float(order.total_amount),
            "tax": float(order.tax_amount),
            "note": getattr(order, "note", ""),

            # Preserve existing payment keys for other pages.
            "payment_status": (
                latest_payment.payment_status
                if latest_payment else None
            ),
            "payment_method": (
                latest_payment.method
                if latest_payment else None
            ),
            "paid_at": (
                latest_payment.paid_at.isoformat()
                if latest_payment and latest_payment.paid_at else None
            ),

            "payments": [
                {
                    "id": payment.pk,
                    "status": payment.payment_status,
                    "method": payment.method,
                    "amount": float(payment.total_amount),
                    "received_by": _actor_name(payment.received_by, payment.received_by_user),
                    "paid_at": (
                        payment.paid_at.isoformat()
                        if payment.paid_at else None
                    ),
                    "reference_number": payment.reference_number,
                }
                for payment in payment_records
            ],

            "items": [
                {
                    "name": item.item.name if item.item else "Deleted item",
                    "qty": item.quantity,
                    "unit_price": float(item.unit_price),
                    "subtotal": float(item.subtotal),
                    "note": getattr(item, "note", ""),
                }
                for item in order.items.all()
            ],
        })

    return JsonResponse({"orders": data})


def active_orders(request):
    orders = RestaurantOrder.objects.prefetch_related(
        'items__item'
    ).select_related(
        'table', 'room', 'served_by', 'booking__guest', 'reservation',
        'preparing_by', 'served_status_by'
    ).order_by('-created_at')

    data = []
    for o in orders:
        data.append({
            'id': o.id,
            'order_number': o.order_number,
            'type': o.order_type,
            'status': o.status,
            'table': o.table.number if o.table else None,
            'room': o.room.room_type if o.room else None,
            'total': float(o.total_amount),
            'tax': float(o.tax_amount),
            'created_at': o.created_at.isoformat(),
            'items': [
                {'name': oi.item.name, 'qty': oi.quantity, 'subtotal': float(oi.subtotal)}
                for oi in o.items.all()
            ],
        })
    return JsonResponse({'orders': data})


def restaurant_stats(request):
    today = timezone.now().date()
    all_orders = RestaurantOrder.objects.all()
    today_orders = all_orders.filter(created_at__date=today)

    revenue = today_orders.filter(status='served').aggregate(
        total=Sum('total_amount')
    )['total'] or 0

    return JsonResponse({
        'today_revenue': float(revenue),
        'total_orders': all_orders.count(),
        'pending': all_orders.filter(status__in=['pending', 'preparing']).count(),
        'served_today': today_orders.filter(status='served').count(),
    })


# ════════════════════════════════════════════════════════════════
#  ORDER CREATION
# ════════════════════════════════════════════════════════════════

@login_required
@csrf_exempt
@transaction.atomic
def create_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    staff = _get_staff_for_request(request)
    user = request.user

    # Staff or admin only.
    if staff is None and not _is_admin(user):
        return JsonResponse(
            {'error': 'A staff profile or admin access is required.'}, status=403
        )

    order_type = (data.get('order_type') or 'dine_in').lower()
    if order_type not in ['dine_in', 'room_service', 'takeaway']:
        return JsonResponse({'error': 'Invalid order type'}, status=400)

    table_id = data.get('table_id')
    room_id = data.get('room_id')
    reservation_id = data.get('reservation_id')
    charge_to_room = bool(data.get('charge_to_room', False))
    items = data.get('items', [])
    payment_method = data.get('payment_method')

    # ── validation ──
    if order_type == 'dine_in' and not table_id and not reservation_id:
        return JsonResponse({'error': 'Table selection required for dine-in'}, status=400)

    if order_type == 'room_service' and not room_id:
        return JsonResponse({'error': 'Room selection required for room service'}, status=400)

    if not items:
        return JsonResponse({'error': 'No items selected'}, status=400)

    room_obj = None
    unit = None
    booking = None
    reservation = None

    try:
        # ── room service ──
        if order_type == 'room_service':
            room_obj = Room.objects.filter(id=room_id).first()
            if not room_obj:
                unit = RoomUnit.objects.filter(id=room_id).select_related('room').first()
                if unit:
                    room_obj = unit.room
            if not room_obj:
                return JsonResponse({'error': 'Invalid room selected'}, status=400)

            if unit:
                booking = Booking.objects.filter(
                    room_unit=unit, status='checked_in'
                ).select_related('guest').first()
            else:
                booking = Booking.objects.filter(
                    room=room_obj, status='checked_in'
                ).select_related('guest').first()

            if not booking:
                return JsonResponse({'error': 'No active booking for this room'}, status=400)

        # ── dine-in reservation ──
        if order_type == 'dine_in' and reservation_id:
            reservation = TableReservation.objects.filter(id=reservation_id).first()
            if not reservation:
                return JsonResponse({'error': 'Invalid reservation'}, status=400)
            table_id = reservation.table_id

        if order_type == 'dine_in' and table_id and not Table.objects.filter(id=table_id).exists():
            return JsonResponse({'error': 'Table not found'}, status=400)

        # ── create order ──
        order = RestaurantOrder.objects.create(
            order_type=order_type,
            table_id=table_id if (order_type == 'dine_in' and table_id) else None,
            room=room_obj,
            booking=booking,
            reservation=reservation,
            charge_to_room=charge_to_room,
            served_by=user,
        )

        total = Decimal('0')
        tax_total = Decimal('0')

        for i in items:
            item_id = i.get('id')
            try:
                menu_item = MenuItem.objects.get(pk=item_id)
            except MenuItem.DoesNotExist:
                return JsonResponse({'error': f'Item {item_id} not found'}, status=400)

            try:
                qty = int(i.get('qty', 1))
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Invalid quantity'}, status=400)
            if qty < 1:
                qty = 1

            subtotal = menu_item.price * qty
            tax = subtotal * menu_item.tax_percent / 100

            OrderItem.objects.create(
                order=order,
                item=menu_item,
                quantity=qty,
                unit_price=menu_item.price,
                note=i.get('note', ''),
            )
            total += subtotal
            tax_total += tax

        order.total_amount = total
        order.tax_amount = tax_total
        order.save()

        # ── dine-in: mark table occupied ──
        if order_type == 'dine_in' and table_id:
            Table.objects.filter(pk=table_id).update(is_occupied=True)

        grand_total = total + tax_total
        payment_status = None
        folio_warning = None

        # ── room service charged to folio: no standalone bill, post as a folio charge ──
        if order_type == 'room_service' and charge_to_room and booking:
            try:
                folio, _ = GuestFolio.objects.get_or_create(booking=booking)
                if folio.status == "open":
                    FolioCharge.objects.create(
                        folio=folio,
                        charge_type='restaurant',
                        description=f'Restaurant Order #{order.order_number}',
                        amount=total,
                        tax_amount=tax_total,
                        added_by=staff if staff else None,
                    )
                else:
                    folio_warning = 'Folio is not open; charge was not posted.'
            except Exception as e:
                folio_warning = f'Billing failed: {str(e)}'

        # ── every other order type (takeaway, dine-in, room service not on the room bill)
        #     needs its own billing record so it can be marked paid ──
        else:
            BillingPayment.objects.create(
                order=order,
                folio=None,
                amount=total,
                tax_amount=tax_total,
                total_amount=grand_total,
                method=payment_method if order_type == 'takeaway' else '',
                payment_status='pending',
                received_by=staff,
                received_by_user=None if staff else user,
            )
            payment_status = 'pending'

        response = {
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'order_type': order.order_type,
            'booking_id': booking.id if booking else None,
            'reservation_id': reservation.id if reservation else None,
            'total': float(total),
            'tax': float(tax_total),
            'grand_total': float(grand_total),
            'payment_status': payment_status,
        }
        if folio_warning:
            response['warning'] = folio_warning

        return JsonResponse(response)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ════════════════════════════════════════════════════════════════
#  PAYMENTS
# ════════════════════════════════════════════════════════════════

@login_required
@csrf_exempt
def mark_order_paid(request, order_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"error": "JSON object required"}, status=400)

    method = data.get("method")
    reference = data.get("reference_number", "")

    if not isinstance(method, str) or not method.strip():
        return JsonResponse({"error": "Payment method is required"}, status=400)

    if not isinstance(reference, str):
        return JsonResponse({"error": "Reference number must be text"}, status=400)

    staff = _get_staff_for_request(request)

    # Staff or admin only.
    if staff is None and not _is_admin(request.user):
        return JsonResponse(
            {"error": "A staff profile or admin access is required to record payments."},
            status=403,
        )

    receiver_name = _actor_name(staff, request.user)

    try:
        with transaction.atomic():
            payment = (
                BillingPayment.objects
                .select_for_update()
                .get(order_id=order_id)
            )

            if payment.payment_status == "paid":
                return JsonResponse(
                    {
                        "error": "Already marked as paid",
                        "paid_at": (
                            payment.paid_at.isoformat()
                            if payment.paid_at else None
                        ),
                    },
                    status=400,
                )

            payment.method = method.strip()
            payment.payment_status = "paid"
            payment.paid_at = timezone.now()
            payment.reference_number = reference.strip()

            # Record who collected this payment: staff, or the admin user.
            payment.received_by = staff
            payment.received_by_user = None if staff else request.user
            payment.save()

            order = payment.order
            order.status = "served"
            order.save(update_fields=["status"])

            _free_table_if_needed(order)

        return JsonResponse({
            "success": True,
            "order_id": order.pk,
            "order_number": order.order_number,
            "paid_at": payment.paid_at.isoformat(),
            "method": payment.method,
            "total": float(payment.total_amount),
            "received_by": receiver_name,
            "message": (
                f"Payment of ₹{payment.total_amount} "
                f"received via {payment.method}"
            ),
        })

    except BillingPayment.DoesNotExist:
        return JsonResponse({"error": "Payment record not found"}, status=404)


@login_required
@csrf_exempt
def update_order_status(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    order = get_object_or_404(RestaurantOrder, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    status = data.get('status')
    if status not in VALID_ORDER_STATUSES:
        return JsonResponse({'error': f'Invalid status. Must be one of: {VALID_ORDER_STATUSES}'}, status=400)

    staff = getattr(request.user, 'staff_profile', None)

    order.status = status

    if status == 'preparing' and not order.preparing_at:
        order.preparing_by = staff
        order.preparing_at = timezone.now()
    elif status == 'served' and not order.served_status_at:
        order.served_status_by = staff
        order.served_status_at = timezone.now()

    order.save()

    if status in TERMINAL_ORDER_STATUSES:
        _free_table_if_needed(order)

    return JsonResponse({'success': True, 'status': status})
def occupied_rooms(request):
    bookings = Booking.objects.filter(
        status='checked_in', room_unit__isnull=False
    ).select_related('room_unit', 'room')

    data = [
        {'id': b.room_unit.id, 'room_number': b.room_unit.room_number, 'room_type': b.room.room_type}
        for b in bookings
    ]
    return JsonResponse({'rooms': data})


# ════════════════════════════════════════════════════════════════
# TABLE RESERVATIONS
# ════════════════════════════════════════════════════════════════

@csrf_exempt
def create_reservation(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    try:
        data = json.loads(request.body)

        table_id = data.get("table_id")
        guest_name = data.get("guest_name")
        phone = data.get("phone", "")
        reservation_time = data.get("reservation_time")
        guests_count = data.get("guests_count", 1)

        if not table_id or not guest_name or not reservation_time:
            return JsonResponse({"error": "Missing required fields"}, status=400)

        table = Table.objects.get(id=table_id)

        start_time = parse_datetime(reservation_time)
        if not start_time:
            return JsonResponse({"error": "Invalid datetime format"}, status=400)

        end_time = start_time + timedelta(hours=2)

        conflict = TableReservation.objects.filter(
            table=table,
            status__in=["reserved", "seated"],
            reservation_time__lt=end_time,
            reservation_time__gte=start_time - timedelta(hours=2)
        ).exists()

        if conflict:
            return JsonResponse({"error": "Table already booked in this time slot"}, status=400)

        reservation = TableReservation.objects.create(
            table=table,
            guest_name=guest_name,
            phone=phone,
            reservation_time=start_time,
            guests_count=guests_count,
            status="reserved"
        )

        return JsonResponse({
            "message": "Reservation created successfully",
            "reservation_id": reservation.id,
            "table": table.number,
            "reservation_time": reservation.reservation_time.isoformat(),
            "status": reservation.status
        })

    except Table.DoesNotExist:
        return JsonResponse({"error": "Table not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

@login_required
@require_GET
def list_reservations(request):
    reservations = (
        TableReservation.objects
        .select_related("table")
        .order_by("-created_at")
    )

    data = [
        {
            "id": reservation.id,
            "guest_name": reservation.guest_name,
            "phone": reservation.phone,
            "table_id": reservation.table_id,
            "table": (
                reservation.table.number
                if reservation.table else None
            ),
            "guests_count": reservation.guests_count,
            "status": reservation.status,
            "reservation_time": reservation.reservation_time.isoformat(),
            "created_at": reservation.created_at.isoformat(),
        }
        for reservation in reservations
    ]

    return JsonResponse({
        "count": len(data),
        "reservations": data,
    })

@csrf_exempt
def update_reservation(request, reservation_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST method required"}, status=405)

    try:
        reservation = TableReservation.objects.get(id=reservation_id)
        data = json.loads(request.body)

        if "guest_name" in data:
            reservation.guest_name = data["guest_name"]
        if "phone" in data:
            reservation.phone = data["phone"]
        if "guests_count" in data:
            reservation.guests_count = data["guests_count"]
        if "status" in data:
            reservation.status = data["status"]
        if "reservation_time" in data:
            dt = parse_datetime(data["reservation_time"])
            if dt:
                reservation.reservation_time = dt
        if "table_id" in data:
            reservation.table = Table.objects.get(id=data["table_id"])

        reservation.save()
        update_table_status(reservation.table)

        return JsonResponse({
            "message": "Reservation updated successfully",
            "id": reservation.id,
            "status": reservation.status
        })

    except TableReservation.DoesNotExist:
        return JsonResponse({"error": "Reservation not found"}, status=404)
    except Table.DoesNotExist:
        return JsonResponse({"error": "Table not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def delete_reservation(request, reservation_id):
    if request.method != "DELETE":
        return JsonResponse({"error": "DELETE method required"}, status=405)

    try:
        reservation = TableReservation.objects.get(id=reservation_id)
        table = reservation.table
        reservation.delete()
        if table:
            update_table_status(table)
        return JsonResponse({"message": "Reservation deleted successfully"})
    except TableReservation.DoesNotExist:
        return JsonResponse({"error": "Reservation not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ════════════════════════════════════════════════════════════════
#  RESTAURANT / STAFF DASHBOARD
# ════════════════════════════════════════════════════════════════

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

RESTAURANT_KEYWORDS = [
    'restaurant', 'kitchen', 'dining', 'food', 'bar',
    'manager', 'owner', 'admin', 'hotel',
]


def _get_dashboard_range(request):
    range_type = request.GET.get('range', 'today')
    today = timezone.now().date()
    if range_type == 'yesterday':
        start = end = today - timedelta(days=1)
    elif range_type == 'week':
        start = today - timedelta(days=today.weekday())
        end = today
    elif range_type == 'month':
        start = today.replace(day=1)
        end = today
    elif range_type == 'custom':
        try:
            start = timezone.datetime.strptime(request.GET.get('from', ''), '%Y-%m-%d').date()
            end = timezone.datetime.strptime(request.GET.get('to', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            start = end = today
    else:
        start = end = today
    return start, end, range_type


def _build_dashboard_stats(start, end):
    orders_qs = RestaurantOrder.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end
    ).exclude(status='cancelled')
    cancelled_qs = RestaurantOrder.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end, status='cancelled'
    )

    total_sales = orders_qs.aggregate(t=Sum(F('total_amount') + F('tax_amount')))['t'] or 0
    order_count = orders_qs.count()
    avg_order_value = (total_sales / order_count) if order_count else 0

    payment_qs = BillingPayment.objects.filter(
        order__in=orders_qs, payment_status='paid'
    ).values('method').annotate(total=Sum('total_amount'), count=Count('id'))
    payment_breakdown = [
        {'method': (p['method'] or 'other'), 'total': float(p['total'] or 0), 'count': p['count']}
        for p in payment_qs
    ]

    top_items_raw = (
        OrderItem.objects.filter(order__in=orders_qs)
        .values('item_id')
        .annotate(qty=Sum('quantity'), revenue=Sum(F('unit_price') * F('quantity')))
        .order_by('-qty')[:5]
    )
    item_ids = [t['item_id'] for t in top_items_raw]
    items_by_id = {m.id: m for m in MenuItem.objects.filter(id__in=item_ids)}

    top_items_data = []
    for t in top_items_raw:
        mi = items_by_id.get(t['item_id'])
        top_items_data.append({
            'id': t['item_id'],
            'name': mi.name if mi else '',
            'qty': t['qty'],
            'revenue': float(t['revenue'] or 0),
            'image': mi.image.url if (mi and mi.image) else None,
        })

    # NOTE: no dedicated Customer model exists yet — approximated from booking guests
    # attached to orders in this range. Swap this out if/when a real Customer model exists.
    guest_counts = {}
    for o in orders_qs.select_related('booking__guest'):
        if o.booking and o.booking.guest:
            name = o.booking.guest.full_name
            guest_counts[name] = guest_counts.get(name, 0) + 1
    total_customers = len(guest_counts)
    repeat_customers = sum(1 for c in guest_counts.values() if c > 1)

    hourly = (
        orders_qs.annotate(hour=ExtractHour('created_at'))
        .values('hour').annotate(count=Count('id'), revenue=Sum(F('total_amount') + F('tax_amount')))
        .order_by('hour')
    )
    hours_map = {h['hour']: float(h['revenue'] or 0) for h in hourly}
    hourly_revenue = [hours_map.get(h, 0) for h in range(24)]

    recent = list(orders_qs.select_related('table', 'room').order_by('-created_at')[:8])
    recent_data = [{
        'id': o.id,
        'order_number': o.order_number,
        'type': o.order_type,
        'table': o.table.number if o.table else None,
        'items_count': o.items.count(),
        'total': float(o.total_amount + o.tax_amount),
        'status': o.status,
        'created_at': o.created_at.isoformat(),
    } for o in recent]

    return {
        'total_sales': float(total_sales),
        'order_count': order_count,
        'avg_order_value': float(avg_order_value),
        'dine_in_count': orders_qs.filter(order_type='dine_in').count(),
        'takeaway_count': orders_qs.filter(order_type='takeaway').count(),
        'room_service_count': orders_qs.filter(order_type='room_service').count(),
        'cancelled_count': cancelled_qs.count(),
        'payment_breakdown': payment_breakdown,
        'top_items': top_items_data,
        'total_customers': total_customers,
        'repeat_customers': repeat_customers,
        'hourly_revenue': hourly_revenue,
        'recent_orders': recent_data,
        'expenses_today': 0.0,  # TODO: wire to a real Expense model when one exists
    }


# ═══════════════════════════════════════════════════════════════════
#  Restaurant dashboard – full updated code
#  Changes vs your original:
#    1. NEW helper  _build_extra_stats()
#    2. AJAX branch now adds  dash_stats["extra"] = _build_extra_stats(...)
#    3. render() uses "restaurant_dashboard.html" instead of "pos.html"
#  Everything else is unchanged.
# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════
#  Restaurant dashboard – full updated code
#  (replaces the dashboard section of restaurant/views.py)
#
#  Changes in this version:
#    1. Sales by Payment Method now reads BillingPayment (paid bills)
#       instead of a non-existent RestaurantOrder.payment_method field.
#    2. Active Tables = flagged occupied OR has an open order OR has a
#       seated reservation (shared helper, used by the list AND the
#       "x / y" count so they always agree).
#    3. _pct_change returns None when there is no previous period, so the
#       banner never shows a fake "100%".
#    4. Removed the now-unused customers/expenses delta calculation
#       (saves a full extra round of queries per request).
# ═══════════════════════════════════════════════════════════════════

import json
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldError
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

# ⚠️ These already exist at the top of your views.py – shown here only so
#    you know what this section relies on:
# from .models import MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem, TableReservation
# from pms.models import Room, RoomUnit, Booking
# from billing.models import BillingPayment
# from accounts.models import Staff, Department
# from accounts.decorators import staff_login_required
# from hotel.models import Task, Shift, Attendance, LeaveRequest, Payroll

# Template rendered for the full page (non-AJAX) request.
# Change this to the file where you saved the new dashboard template.
DASHBOARD_TEMPLATE = "pos/pos.html"


def _pct_change(cur, prev):
    """% change vs the previous period. None = no meaningful comparison."""
    cur = float(cur or 0)
    prev = float(prev or 0)
    if not prev:
        return None
    return round(((cur - prev) / prev) * 100, 1)


def _busy_table_ids():
    """IDs of tables that are in use right now:
    flagged occupied, has a pending/preparing order, or has a seated reservation."""
    ids = set(Table.objects.filter(is_occupied=True).values_list("id", flat=True))
    ids |= set(
        RestaurantOrder.objects
        .filter(status__in=["pending", "preparing"], table__isnull=False)
        .values_list("table_id", flat=True)
    )
    ids |= set(
        TableReservation.objects
        .filter(status="seated", table__isnull=False)
        .values_list("table_id", flat=True)
    )
    return ids


def _build_extra_stats(start, end, hotel):
    """Data for the payment chart, top items, summary, customers, expenses etc."""

    orders = RestaurantOrder.objects.filter(created_at__date__range=(start, end))
    valid = orders.exclude(status="cancelled")
    order_count = valid.count()

    # ── Sales overview chart: hourly for one day, daily for longer ranges ──
    if start == end:
        labels = [f"{h}:00" for h in range(24)]
        buckets = {h: 0.0 for h in range(24)}
        rows = valid.annotate(k=ExtractHour("created_at")).values("k").annotate(t=Sum("total_amount"))
        for r in rows:
            buckets[r["k"]] = float(r["t"] or 0)
        values = [buckets[h] for h in range(24)]
    else:
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        labels = [d.strftime("%d %b") for d in days]
        buckets = {d: 0.0 for d in days}
        rows = valid.annotate(k=TruncDate("created_at")).values("k").annotate(t=Sum("total_amount"))
        for r in rows:
            buckets[r["k"]] = float(r["t"] or 0)
        values = [buckets[d] for d in days]

    # ── Sales by payment method (paid bills for orders in range) ──
    # FIX: payments live in BillingPayment (method / payment_status /
    # total_amount), not on RestaurantOrder.
    pay_rows = list(
        BillingPayment.objects
        .filter(order__in=valid, payment_status="paid")
        .values("method")
        .annotate(t=Sum("total_amount"))
        .order_by("-t")
    )
    pay_total = sum(float(r["t"] or 0) for r in pay_rows)
    payments = [
        {
            "name": (r["method"] or "Other").replace("_", " ").title(),
            "amount": float(r["t"] or 0),
            "pct": round(float(r["t"] or 0) / pay_total * 100) if pay_total else 0,
        }
        for r in pay_rows
    ]

    # ── Top selling items ──
    # `subtotal` is a Python property, so aggregate quantity * unit_price.
    line_total = ExpressionWrapper(
        F("items__quantity") * F("items__unit_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    item_rows = list(
        valid.filter(items__isnull=False)
        .values("items__item_id", "items__item__name")
        .annotate(qty=Sum("items__quantity"), revenue=Sum(line_total))
        .order_by("-qty")[:5]
    )
    menu_map = {m.id: m for m in MenuItem.objects.filter(id__in=[r["items__item_id"] for r in item_rows])}
    top_items = []
    for r in item_rows:
        m = menu_map.get(r["items__item_id"])
        img = getattr(m, "image", None)
        try:
            img_url = img.url if img else ""
        except ValueError:  # ImageField with no file attached
            img_url = ""
        top_items.append({
            "name": r["items__item__name"],
            "image": img_url,
            "qty": r["qty"],
            "revenue": float(r["revenue"] or 0),
        })

    # ── Recent orders in range ──
    recent = [
        {
            "order_number": o.order_number,
            "type": (o.order_type or "").replace("_", " ").title(),
            "amount": float(o.total_amount),
            "status": o.status,
            "time": o.created_at.strftime("%I:%M %p").lstrip("0").lower(),
        }
        for o in orders.order_by("-created_at")[:5]
    ]

    # ── Tables, live ──
    # Occupied  = flagged occupied / open order / seated reservation.
    # Reserved  = has an upcoming (or just-started) "reserved" booking and
    #             isn't occupied yet.
    # Available = everything else.
    busy_ids = _busy_table_ids()
    reserved_ids = set(
        TableReservation.objects
        .filter(
            status="reserved",
            reservation_time__gte=timezone.now() - timedelta(hours=2),
            table__isnull=False,
        )
        .values_list("table_id", flat=True)
    ) - busy_ids

    def _table_status(t):
        if t.id in busy_ids:
            return "Occupied"
        if t.id in reserved_ids:
            return "Reserved"
        return "Available"

    # Occupied first, then Reserved, then Available (each group by table number)
    status_rank = {"Occupied": 0, "Reserved": 1, "Available": 2}
    active_tables = sorted(
        (
            {"number": t.number, "capacity": t.capacity, "status": _table_status(t)}
            for t in Table.objects.order_by("number")
        ),
        key=lambda r: status_rank[r["status"]],
    )[:8]

    # ── Orders summary ──
    def _n(q):
        n = valid.filter(q).count()
        return {"count": n, "pct": round(n / order_count * 100) if order_count else 0}

    all_in_range = orders.count()
    cancelled = orders.filter(status="cancelled").count()
    summary = {
        "total": order_count,
        "dine_in": _n(Q(order_type__icontains="dine")),
        "takeaway": _n(Q(order_type__icontains="take")),
        "room_service": _n(Q(order_type__icontains="room")),
        "cancelled": {
            "count": cancelled,
            "pct": round(cancelled / all_in_range * 100) if all_in_range else 0,
        },
    }

    # ── Customers (in-house guests attached to orders) ──
    guest_ids = set(
        valid.exclude(booking__guest__isnull=True).values_list("booking__guest_id", flat=True)
    )
    repeat = (
        RestaurantOrder.objects.filter(booking__guest_id__in=guest_ids)
        .values("booking__guest_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )

    # ── Expenses ── ⚠️ point this at your real Expense model (or leave 0)
    expenses = 0.0
    try:
        from accounts.models import Expense  # ← change app path / model name
        expenses = float(
            Expense.objects.filter(hotel=hotel, date__range=(start, end))
            .aggregate(t=Sum("amount"))["t"] or 0
        )
    except (ImportError, LookupError, FieldError):
        # Expense model/fields not found – expenses stay 0 (profit == sales)
        pass

    return {
        "sales_chart": {"labels": labels, "values": values},
        "payments": payments,
        "pay_total": pay_total,
        "top_items": top_items,
        "recent_orders": recent,
        "active_tables": active_tables,
        "summary": summary,
        "total_customers": len(guest_ids),
        "repeat_customers": repeat,
        "expenses": expenses,
    }
# ───────────────────────────────────────────────────────────────
#  Dashboard view (full)
# ───────────────────────────────────────────────────────────────
@staff_login_required
@never_cache
@login_required
def restaurant_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    dept_name = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, 'role', '') or '').lower()
    combined = dept_name + " " + role

    if not any(k in combined for k in RESTAURANT_KEYWORDS):
        return redirect("staff_login")

    hotel = staff.hotel
    today = timezone.now().date()
    month = today.month
    year = today.year

    hotel_staff = Staff.objects.filter(hotel=hotel).select_related("department").order_by("department__name", "name")
    departments = Department.objects.filter(hotel=hotel)

    occupied_bookings = Booking.objects.filter(
        status="checked_in", room_unit__isnull=False
    ).select_related("guest", "room_unit", "room")
    occupied_room_count = occupied_bookings.count()

    rooms_qs = Room.objects.filter(is_active=True).prefetch_related("units")
    room_units = RoomUnit.objects.select_related("room").all()

    room_list = []
    for room in rooms_qs:
        units_qs = room.units.all().order_by("room_number")
        available_units = units_qs.filter(status="Available").count()
        price = getattr(room, "base_price", None) or getattr(room, "price", None) or 0
        room_list.append({
            "id": room.id,
            "room_type": getattr(room, "room_type", "Unknown"),
            "total_rooms": units_qs.count(),
            "available_rooms": available_units,
            "price": float(price) if price else 0,
            "description": getattr(room, "description", "") or "",
            "units": [{"id": u.id, "number": u.room_number, "status": u.status} for u in units_qs],
        })
    rooms_json = json.dumps(room_list)

    recent_tasks = Task.objects.select_related("staff", "room_unit", "room").order_by("-created_at")[:10]
    my_tasks = Task.objects.filter(staff=staff).order_by("-created_at")

    shifts = Shift.objects.filter(hotel=hotel).select_related("staff", "department").order_by("date", "shift")
    my_shift_today = Shift.objects.filter(staff=staff, date=today).first()

    attendance_qs = Attendance.objects.filter(staff=staff, date__month=month, date__year=year)
    present_days = attendance_qs.filter(status="Present").count()
    late_days = attendance_qs.filter(status="Late").count()
    absent_days = attendance_qs.filter(status="Absent").count()
    overtime_hours = attendance_qs.aggregate(total=Sum("overtime_hours"))["total"] or 0
    attendance_records = attendance_qs.order_by("-date")

    today_attendance = Attendance.objects.filter(hotel=hotel, date=today).select_related("staff").order_by("-check_in")
    my_attendance_today = Attendance.objects.filter(staff=staff, date=today).first()
    my_attendance_working_hours = None
    if my_attendance_today and my_attendance_today.check_in and my_attendance_today.check_out:
        my_attendance_working_hours = round(
            (my_attendance_today.check_out - my_attendance_today.check_in).total_seconds() / 3600, 2
        )

    leave_requests = LeaveRequest.objects.filter(staff=staff).order_by("-applied_at")
    used_leave_days = leave_requests.filter(status="Approved").count()
    pending_leaves = leave_requests.filter(status="Pending").count()
    all_leave_requests = LeaveRequest.objects.filter(staff__hotel=hotel).select_related("staff").order_by("-applied_at")

    all_orders = RestaurantOrder.objects.select_related("table", "room", "booking__guest")
    today_orders = all_orders.filter(created_at__date=today)
    pending_orders = all_orders.filter(
        status__in=["pending", "preparing"]
    ).prefetch_related("items__item").select_related("table")

    today_revenue = today_orders.filter(status="served").aggregate(total=Sum("total_amount"))["total"] or 0
    total_revenue = all_orders.filter(status="served").aggregate(total=Sum("total_amount"))["total"] or 0

    order_status_counts = all_orders.aggregate(
        pending=Count("id", filter=Q(status="pending")),
        preparing=Count("id", filter=Q(status="preparing")),
        served=Count("id", filter=Q(status="served")),
        cancelled=Count("id", filter=Q(status="cancelled")),
    )

    recent_orders = all_orders.order_by("-created_at")[:20]

    # Tables: "occupied" now means flagged, has an open order, or seated reservation
    tables_qs = Table.objects.all()
    busy_table_ids = _busy_table_ids()
    tables_total = tables_qs.count()
    tables_occupied = len(busy_table_ids)
    tables_available = tables_total - tables_occupied

    tables = [
        {"id": t.id, "number": t.number, "capacity": t.capacity, "is_occupied": t.id in busy_table_ids}
        for t in tables_qs
    ]

    reservations_today = TableReservation.objects.filter(
        reservation_time__date=today
    ).select_related("table").order_by("reservation_time")

    all_reservations = TableReservation.objects.select_related("table").order_by("-created_at")[:50]

    reservations = [
        {
            "id": r.id,
            "guest_name": r.guest_name,
            "phone": r.phone,
            "table": r.table.number if r.table else None,
            "table_id": r.table.id if r.table else None,
            "guests_count": r.guests_count,
            "status": r.status,
            "reservation_time": r.reservation_time.strftime("%Y-%m-%d %H:%M"),
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in all_reservations
    ]

    menu_categories = MenuCategory.objects.prefetch_related("items").all()
    total_menu_items = MenuItem.objects.count()
    available_menu_items = MenuItem.objects.filter(is_available=True).count()

    hourly_orders = (
        today_orders
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("hour")
    )
    hours_map = {c["hour"]: {"count": c["count"], "revenue": float(c["revenue"] or 0)} for c in hourly_orders}
    chart_labels = [f"{h}:00" for h in range(24)]
    chart_counts = [hours_map.get(h, {}).get("count", 0) for h in range(24)]
    chart_revenue = [hours_map.get(h, {}).get("revenue", 0) for h in range(24)]

    recent_orders_list = list(all_orders.order_by("-created_at")[:5])
    recent_reservations_list = list(reservations_today[:5])
    recent_tasks_list = list(recent_tasks[:5])

    combined_activity = sorted(
        recent_orders_list + recent_reservations_list + recent_tasks_list,
        key=lambda x: x.created_at if hasattr(x, "created_at") else x.reservation_time,
        reverse=True,
    )[:15]

    recent_activity_data = []
    for item in combined_activity:
        if isinstance(item, RestaurantOrder):
            recent_activity_data.append({
                "type": "order",
                "id": item.id,
                "label": f"Order #{item.order_number}",
                "status": item.status,
                "amount": float(item.total_amount),
                "time": item.created_at.strftime("%H:%M"),
            })
        elif isinstance(item, TableReservation):
            recent_activity_data.append({
                "type": "reservation",
                "id": item.id,
                "label": f"Reservation — {item.guest_name}",
                "status": item.status,
                "amount": 0,
                "time": item.reservation_time.strftime("%H:%M"),
            })
        elif isinstance(item, Task):
            recent_activity_data.append({
                "type": "task",
                "id": item.id,
                "label": item.title,
                "status": item.status,
                "amount": 0,
                "time": item.created_at.strftime("%H:%M"),
            })

    active_orders_data = [
        {
            "id": o.id,
            "order_number": o.order_number,
            "status": o.status,
            "order_type": o.order_type,
            "table": o.table.number if o.table else None,
            "room": o.room.room_type if o.room else None,
            "guest": o.booking.guest.full_name if o.booking and o.booking.guest else None,
            "total": float(o.total_amount),
            "tax": float(o.tax_amount),
            "created_at": o.created_at.strftime("%H:%M"),
            "items": [
                {
                    "name": oi.item.name,
                    "qty": oi.quantity,
                    "unit_price": float(oi.unit_price),
                    "subtotal": float(oi.subtotal),  # fine here: Python property on a loaded instance
                }
                for oi in o.items.all()
            ],
        }
        for o in pending_orders
    ]

    from inventory.models import InventoryItem

    restaurant_stock = InventoryItem.objects.filter(
        Q(department__name__icontains='restaurant') |
        Q(department__name__icontains='kitchen') |
        Q(department__name__icontains='dining')
    ).select_related("category", "vendor", "department").order_by("department__name", "name").distinct()

    low_stock_items = restaurant_stock.filter(current_stock__lte=F("minimum_stock"))
    restaurant_stock_value = restaurant_stock.aggregate(
        total=Sum(F("current_stock") * F("cost_per_unit"))
    )["total"] or 0

    restaurant_stock_data = [
        {
            "id": item.id,
            "name": item.name,
            "category": item.category.name if item.category else "—",
            "department": item.department.name if item.department else "—",
            "current_stock": float(item.current_stock),
            "minimum_stock": float(item.minimum_stock),
            "unit": item.get_unit_display(),
            "is_low_stock": item.is_low_stock,
            "cost_per_unit": float(item.cost_per_unit),
            "stock_value": float(item.stock_value),
            "vendor": item.vendor.name if item.vendor else "—",
        }
        for item in restaurant_stock
    ]

    low_stock_data = [
        {
            "id": item.id,
            "name": item.name,
            "category": item.category.name if item.category else "—",
            "department": item.department.name if item.department else "—",
            "current_stock": float(item.current_stock),
            "minimum_stock": float(item.minimum_stock),
            "unit": item.get_unit_display(),
            "vendor": item.vendor.name if item.vendor else "—",
        }
        for item in low_stock_items
    ]

    payroll = Payroll.objects.filter(staff=staff, month=month, year=year).prefetch_related("line_items").first()
    payroll_history = Payroll.objects.filter(staff=staff).order_by("-year", "-month")

    payroll_history_list = []
    for p in payroll_history:
        earnings = float(p.line_items.filter(line_type="earning").aggregate(t=Sum("amount"))["t"] or 0)
        deductions = float(p.line_items.filter(line_type="deduction").aggregate(t=Sum("amount"))["t"] or 0)
        payroll_history_list.append({
            "id": p.id,
            "month": p.month,
            "year": p.year,
            "month_label": MONTH_NAMES[p.month],
            "basic_salary": float(p.basic_salary),
            "overtime_amount": float(p.overtime_amount or 0),
            "bonus": float(p.bonus or 0),
            "incentive": float(p.incentive or 0),
            "pf_amount": float(p.pf_amount or 0),
            "esi_amount": float(p.esi_amount or 0),
            "loan_deduction": float(p.loan_deduction or 0),
            "tax_deduction": float(p.tax_deduction or 0),
            "gross_salary": earnings,
            "deductions": deductions,
            "net_salary": float(p.net_salary),
            "paid_status": p.paid_status,
            "paid_at": p.paid_at.strftime("%d %b %Y") if p.paid_at else None,
        })

    if payroll:
        earnings_items = [
            {"label": item.label, "amount": float(item.amount)}
            for item in payroll.line_items.filter(line_type="earning").order_by("order")
        ]
        deductions_items = [
            {"label": item.label, "amount": float(item.amount)}
            for item in payroll.line_items.filter(line_type="deduction").order_by("order")
        ]
        current_payroll = {
            "id": payroll.id,
            "month_label": MONTH_NAMES[payroll.month],
            "year": payroll.year,
            "basic_salary": float(payroll.basic_salary),
            "overtime_amount": float(payroll.overtime_amount),
            "bonus": float(payroll.bonus),
            "incentive": float(payroll.incentive),
            "pf_amount": float(payroll.pf_amount),
            "esi_amount": float(payroll.esi_amount),
            "loan_deduction": float(payroll.loan_deduction),
            "tax_deduction": float(payroll.tax_deduction),
            "deductions": float(payroll.deductions),
            "net_salary": float(payroll.net_salary),
            "paid_status": payroll.paid_status,
            "paid_at": payroll.paid_at.strftime("%d %b %Y, %I:%M %p") if payroll.paid_at else None,
            "earnings_items": earnings_items,
            "deductions_items": deductions_items,
        }
    else:
        current_payroll = None

    stats = {
        "today_revenue": float(today_revenue),
        "total_revenue": float(total_revenue),
        "total_orders": all_orders.count(),
        "pending_orders": order_status_counts["pending"] + order_status_counts["preparing"],
        "completed_orders": order_status_counts["served"],
        "cancelled_orders": order_status_counts["cancelled"],
        "served_today": today_orders.filter(status="served").count(),
        "tables_total": tables_total,
        "tables_occupied": tables_occupied,
        "tables_available": tables_available,
        "reservations_today": reservations_today.count(),
        "total_menu_items": total_menu_items,
        "available_menu_items": available_menu_items,
        "occupied_rooms": occupied_room_count,
        "total_staff": hotel_staff.count(),
        "total_departments": departments.count(),
        "present_days": present_days,
        "late_days": late_days,
        "absent_days": absent_days,
        "overtime_hours": float(overtime_hours),
        "pending_leaves": pending_leaves,
        "used_leave_days": used_leave_days,
        "restaurant_stock_items": restaurant_stock.count(),
        "low_stock_count": low_stock_items.count(),
        "restaurant_stock_value": float(restaurant_stock_value),
    }

    # ═══════════════ AJAX (dashboard data) ═══════════════
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        start, end, range_type = _get_dashboard_range(request)
        dash_stats = _build_dashboard_stats(start, end)

        # comparison period: same length window immediately before `start`
        span_days = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span_days - 1)
        prev_stats = _build_dashboard_stats(prev_start, prev_end)

        # None when the previous period is empty (banner handles that)
        dash_stats['deltas'] = {
            'total_sales': _pct_change(dash_stats['total_sales'], prev_stats['total_sales']),
            'order_count': _pct_change(dash_stats['order_count'], prev_stats['order_count']),
            'avg_order_value': _pct_change(dash_stats['avg_order_value'], prev_stats['avg_order_value']),
        }
        dash_stats['range_type'] = range_type
        dash_stats['range_from'] = start.isoformat()
        dash_stats['range_to'] = end.isoformat()
        dash_stats['tables_occupied'] = tables_occupied
        dash_stats['tables_total'] = tables_total
        dash_stats['tables_live'] = tables

        # extra data used by the dashboard template
        dash_stats['extra'] = _build_extra_stats(start, end, hotel)

        return JsonResponse({
            "stats": stats,
            "dashboard": dash_stats,
            "active_orders": active_orders_data,
            "tables": tables,
            "reservations": reservations,
            "recent_activity": recent_activity_data,
            "restaurant_stock": restaurant_stock_data,
            "low_stock_items": low_stock_data,
            "chart": {"labels": chart_labels, "counts": chart_counts, "revenue": chart_revenue},
        })

    return render(request, "pos/pos.html", {
        "staff": staff,
        "hotel": hotel,
        "hotel_staff": hotel_staff,
        "departments": departments,
        "occupied_bookings": occupied_bookings,
        "occupied_rooms": occupied_room_count,
        "rooms": room_list,
        "rooms_json": rooms_json,
        "room_units": room_units,
        "recent_tasks": recent_tasks,
        "my_tasks": my_tasks,
        "shifts": shifts,
        "my_shift_today": my_shift_today,
        "attendance_records": attendance_records,
        "today_attendance": today_attendance,
        "attendance_today": my_attendance_today,
        "attendance_working_hours": my_attendance_working_hours,
        "present_days": present_days,
        "late_days": late_days,
        "absent_days": absent_days,
        "overtime_hours": overtime_hours,
        "leave_requests": leave_requests,
        "all_leave_requests": all_leave_requests,
        "used_leave_days": used_leave_days,
        "pending_leaves": pending_leaves,
        "stats": stats,
        "active_orders": active_orders_data,
        "pending_orders": pending_orders,
        "recent_orders": recent_orders,
        "tables": tables,
        "tables_qs": tables_qs,
        "reservations": reservations,
        "reservations_today": reservations_today,
        "menu_categories": menu_categories,
        "recent_activity": recent_activity_data,
        "chart_labels": json.dumps(chart_labels),
        "chart_counts": json.dumps(chart_counts),
        "chart_revenue": json.dumps(chart_revenue),
        "today": today,
        "restaurant_stock": restaurant_stock,
        "restaurant_stock_data": json.dumps(restaurant_stock_data),
        "low_stock_items": low_stock_items,
        "low_stock_data": json.dumps(low_stock_data),
        "restaurant_stock_value": restaurant_stock_value,
        "current_payroll": current_payroll,
        "payroll_history": payroll_history_list,
        "payroll_month_label": MONTH_NAMES[month],
        "payroll_year": year,
    })
from datetime import datetime, time, timedelta
from django.conf import settings
from django.db.models.functions import ExtractHour, TruncDate
@login_required
@never_cache
@require_GET
def restaurant_overview_page(request):
    """Sales use served orders, grouped by order creation time, excluding tax.

    Sales are not payment collections. Active orders and table occupancy are
    current snapshots, independent of the selected reporting period.
    """
    tz = timezone.get_current_timezone()
    now = timezone.now()
    today = timezone.localtime(now, tz).date() if settings.USE_TZ else now.date()
    period = request.GET.get('period', 'today')
    if period not in {'today', 'yesterday', 'week', 'month'}:
        period = 'today'
    end_date = today - timedelta(days=1) if period == 'yesterday' else today
    start_date = {
        'today': today,
        'yesterday': today - timedelta(days=1),
        'week': today - timedelta(days=6),
        'month': today.replace(day=1),
    }[period]

    def midnight(day):
        value = datetime.combine(day, time.min)
        return timezone.make_aware(value, tz) if settings.USE_TZ else value

    # Keep the same access scope as the existing restaurant APIs. If this app
    # has multiple restaurants, apply your existing tenant filter here and to
    # the Table queryset below.
    all_orders = RestaurantOrder.objects.all()
    orders = all_orders.filter(created_at__gte=midnight(start_date),
                               created_at__lt=midnight(end_date + timedelta(days=1)))
    served = orders.filter(status='served')
    summary = served.aggregate(sales=Sum('total_amount'), count=Count('pk'))
    sales = summary['sales'] or Decimal('0')
    served_count = summary['count']
    order_count = orders.count()
    active = all_orders.filter(status__in=['pending', 'preparing'])
    active_counts = {row['status']: row['count'] for row in
                     active.values('status').annotate(count=Count('pk')).order_by()}
    pending = active_counts.get('pending', 0)
    preparing = active_counts.get('preparing', 0)

    top_items = list(OrderItem.objects.filter(order__in=served)
        .values('item_id').annotate(units_sold=Sum('quantity'),
                                   revenue=Sum(F('unit_price') * F('quantity')))
        .order_by('-units_sold', 'item_id')[:5])
    for row in top_items:
        row['quantity'] = row['units_sold']
    menu = MenuItem.objects.in_bulk([row['item_id'] for row in top_items if row['item_id']])
    largest = max((row['quantity'] for row in top_items), default=1) or 1
    for row in top_items:
        item = menu.get(row['item_id'])
        row['name'] = item.name if item else 'Removed menu item'
        row['image'] = item.image.url if item and item.image else ''
        row['percent'] = round(row['quantity'] / largest * 100)

    single_day = start_date == end_date
    grouping = ExtractHour('created_at', tzinfo=tz if settings.USE_TZ else None) if single_day else TruncDate('created_at', tzinfo=tz if settings.USE_TZ else None)
    bucket_totals = {row['bucket']: row['value'] or Decimal('0') for row in
                     served.annotate(bucket=grouping).values('bucket')
                     .annotate(value=Sum('total_amount')).order_by('bucket')}
    keys = list(range(24)) if single_day else [start_date + timedelta(days=i)
                    for i in range((end_date - start_date).days + 1)]
    peak = max(bucket_totals.values(), default=Decimal('0')) or Decimal('1')
    chart = []
    for key in keys:
        value = bucket_totals.get(key, Decimal('0'))
        chart.append({'label': f'{key:02d}:00' if single_day else key.strftime('%d %b'),
                      'value': value, 'percent': round(value / peak * 100, 2)})

    # SVG coordinates are preformatted so localization cannot change decimals.
    graph_points = []
    label_step = max(1, (len(chart) + 5) // 6)
    for index, point in enumerate(chart):
        x = 92 + index * 640 / max(len(chart) - 1, 1)
        y = 224 - float(point['value'] / peak) * 192
        graph_points.append({
            'x': f'{x:.2f}', 'y': f'{y:.2f}',
            'label': point['label'], 'value': point['value'],
            'show_label': index % label_step == 0 or index == len(chart) - 1,
        })
    graph_line = ' '.join(f"{point['x']},{point['y']}" for point in graph_points)
    graph_area = f"92,224 {graph_line} 732,224"
    graph_ticks = [{'y': str(224 - i * 48), 'value': peak * i / 4}
                   for i in range(5)]

    type_counts = {row['order_type']: row['count'] for row in
                   orders.values('order_type').annotate(count=Count('pk')).order_by()}
    order_types = [{'name': name, 'count': type_counts.get(key, 0),
                    'percent': round(type_counts.get(key, 0) / order_count * 100) if order_count else 0}
                   for key, name in [('dine_in', 'Dine in'), ('room_service', 'Room service'), ('takeaway', 'Takeaway')]]
    tables = list(Table.objects.order_by('number'))
    occupied = sum(bool(table.is_occupied) for table in tables)
    recent_orders = list(orders.select_related('table').order_by('-created_at', '-pk')[:6])
    for order in recent_orders:
        order.overview_grand_total = order.total_amount + order.tax_amount
    return render(request, 'hotel/overview.html', {
        'period': period, 'start_date': start_date, 'end_date': end_date,
        'refreshed_at': now, 'sales': sales, 'order_count': order_count,
        'served_count': served_count, 'cancelled_count': orders.filter(status='cancelled').count(),
        'average_order': sales / served_count if served_count else Decimal('0'),
        'active_count': pending + preparing, 'pending_count': pending,
        'preparing_count': preparing, 'top_items': top_items, 'chart': chart,
        'graph_points': graph_points, 'graph_line': graph_line,
        'graph_area': graph_area, 'graph_ticks': graph_ticks,
        'single_day': single_day, 'order_types': order_types,
        'recent_orders': recent_orders,
        'tables': tables, 'table_count': len(tables),
        'occupied_count': occupied, 'available_count': len(tables) - occupied,
    })



# ════════════════════════════════════════════════════════════════
#  NEW ORDER — POS PAGE
#  Add this view to restaurant/views.py (it already has every import
#  it needs: json, render, MenuCategory, Table, Booking, TableReservation).
# ════════════════════════════════════════════════════════════════

@login_required
@never_cache
def new_order_page(request):
    """
    Renders the "New Order" POS screen inside the shared admin shell
    (base.html). Unlike restaurant_overview_page, this one loads its
    menu/tables/rooms/reservations server-side on first render so the
    page is usable immediately with no loading flash — after that,
    placing the order and creating a reservation both go through the
    existing create_order / create_reservation JSON endpoints.
    """
    categories = MenuCategory.objects.prefetch_related('items').order_by('order', 'name')
    menu_data = []
    for cat in categories:
        items = [
            {
                'id': i.id,
                'name': i.name,
                'description': i.description,
                'price': float(i.price),
                'tax_percent': float(i.tax_percent),
                'is_available': i.is_available,
                'is_veg': i.is_veg,
                'image': i.image.url if i.image else None,
                'category_id': cat.id,
            }
            for i in cat.items.all()
        ]
        menu_data.append({'id': cat.id, 'name': cat.name, 'items': items})

    tables = list(
        Table.objects.all().order_by('number')
        .values('id', 'number', 'capacity', 'is_occupied')
    )

    occupied_bookings = Booking.objects.filter(
        status='checked_in', room_unit__isnull=False
    ).select_related('room_unit', 'room', 'guest')
    rooms = [
        {
            'id': b.room_unit.id,
            'room_number': b.room_unit.room_number,
            'room_type': b.room.room_type,
            'guest': b.guest.full_name if b.guest else None,
        }
        for b in occupied_bookings
    ]

    reservations = list(
        TableReservation.objects.filter(status__in=['reserved', 'seated'])
        .select_related('table')
        .order_by('reservation_time')
        .values('id', 'guest_name', 'guests_count', 'reservation_time',
                 'table_id', 'table__number', 'status')
    )

    context = {
        'menu_categories_json': json.dumps(menu_data),
        'tables_json': json.dumps(tables, default=str),
        'rooms_json': json.dumps(rooms),
        'reservations_json': json.dumps(reservations, default=str),
        'has_menu': bool(menu_data),
        'has_tables': bool(tables),
    }
    return render(request, 'hotel/new_order.html', context)

@login_required
@never_cache
def order_summary_page(request):
    """
    Restaurant "Order Summary" page. Extends the shared admin shell.
    All data (stats + orders list) loads client-side via the existing
    restaurant_order_list JSON API, so this view stays cheap to render —
    same pattern as restaurant_overview_page.
    """
    return render(request, "hotel/order_summary.html", {})
@login_required
@never_cache
def menu_manager_page(request):
    return render(request, "hotel/menu_manager.html")

@login_required
@never_cache
def table_status_page(request):
    """
    Restaurant "Table Status" page. Extends the shared admin shell.
    All data (tables, reservations) loads client-side via the existing
    JSON APIs (list_tables, list_reservations, create_reservation,
    update_reservation, delete_reservation), so this view stays cheap
    to render — same pattern as order_summary_page / menu_manager_page.
    """
    return render(request, "hotel/table_status.html", {})

def _new_order_context():
    """Menu / tables / checked-in rooms / active reservations for the New Order
    screen. Used by BOTH the admin page and the staff (POS) page."""
    categories = MenuCategory.objects.prefetch_related('items').order_by('order', 'name')
    menu_data = []
    for cat in categories:
        items = [
            {
                'id': i.id,
                'name': i.name,
                'description': i.description,
                'price': float(i.price),
                'tax_percent': float(i.tax_percent),
                'is_available': i.is_available,
                'is_veg': i.is_veg,
                'image': i.image.url if i.image else None,
                'category_id': cat.id,
            }
            for i in cat.items.all()
        ]
        menu_data.append({'id': cat.id, 'name': cat.name, 'items': items})
 
    tables = list(
        Table.objects.all().order_by('number')
        .values('id', 'number', 'capacity', 'is_occupied')
    )
 
    occupied_bookings = Booking.objects.filter(
        status='checked_in', room_unit__isnull=False
    ).select_related('room_unit', 'room', 'guest')
    rooms = [
        {
            'id': b.room_unit.id,
            'room_number': b.room_unit.room_number,
            'room_type': b.room.room_type,
            'guest': b.guest.full_name if b.guest else None,
        }
        for b in occupied_bookings
    ]
 
    reservations = list(
        TableReservation.objects.filter(status__in=['reserved', 'seated'])
        .select_related('table')
        .order_by('reservation_time')
        .values('id', 'guest_name', 'guests_count', 'reservation_time',
                'table_id', 'table__number', 'status')
    )
 
    return {
        'menu_categories_json': json.dumps(menu_data),
        'tables_json': json.dumps(tables, default=str),
        'rooms_json': json.dumps(rooms),
        'reservations_json': json.dumps(reservations, default=str),
        'has_menu': bool(menu_data),
        'has_tables': bool(tables),
    }
 
 

 
 
# ── Staff (restaurant POS) version ──
@staff_login_required
@never_cache
@login_required
def new_order_pos(request):
    """New Order screen inside the staff POS shell (pos/base.html).
    Same access rules as restaurant_dashboard."""
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")
 
    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")
 
    dept_name = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, 'role', '') or '').lower()
    if not any(k in (dept_name + " " + role) for k in RESTAURANT_KEYWORDS):
        return redirect("staff_login")
 
    context = _new_order_context()
    context.update({
        "staff": staff,
        "hotel": staff.hotel,
    })
    return render(request, "pos/new_order.html", context)

@staff_login_required
@never_cache
@login_required
def order_summary_pos(request):
    """Order Summary inside the staff POS shell (pos/base.html).
    Same access rules as restaurant_dashboard / new_order_pos."""
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    dept_name = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, "role", "") or "").lower()
    if not any(k in (dept_name + " " + role) for k in RESTAURANT_KEYWORDS):
        return redirect("staff_login")

    return render(request, "pos/order_summary.html", {
        
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
    })
@staff_login_required
@never_cache
@login_required
def table_status_pos(request):
    """Table Status inside the staff POS shell (pos/base.html).
    Same access rules as restaurant_dashboard / new_order_pos."""
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    dept_name = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, "role", "") or "").lower()
    if not any(k in (dept_name + " " + role) for k in RESTAURANT_KEYWORDS):
        return redirect("staff_login")

    return render(request, "pos/table_status.html", {
        
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
    })

@staff_login_required
@never_cache
@login_required
def menu_manager_pos(request):
    """Menu Manager inside the staff POS shell (pos/base.html).
    Same access rules as restaurant_dashboard / new_order_pos."""
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    dept_name = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, "role", "") or "").lower()
    if not any(k in (dept_name + " " + role) for k in RESTAURANT_KEYWORDS):
        return redirect("staff_login")

    return render(request, "pos/menu_manager.html", {
        
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
    })


# ════════════════════════════════════════════════════════════════
#  USE STOCK — log inventory consumption (department-filtered)
# ════════════════════════════════════════════════════════════════

RESTAURANT_STOCK_KEYWORDS = ['restaurant', 'kitchen', 'dining']


def _department_stock_qs(keywords):
    """Inventory items whose department name matches any keyword.
    Reusable for other dashboards, e.g. _department_stock_qs(['housekeeping', 'laundry'])."""
    from inventory.models import InventoryItem
    q = Q()
    for kw in keywords:
        q |= Q(department__name__icontains=kw)
    return InventoryItem.objects.filter(q).select_related('category', 'department')


def _restaurant_stock_qs():
    return _department_stock_qs(RESTAURANT_STOCK_KEYWORDS)


def _stock_item_dict(item):
    stock = float(item.current_stock)
    minimum = float(item.minimum_stock)
    if stock <= 0:
        status = 'out'
    elif stock <= minimum:
        status = 'low'
    else:
        status = 'in'
    try:
        image = item.image.url if item.image else None
    except ValueError:
        image = None
    return {
        'id': item.id,
        'name': item.name,
        'category_id': item.category_id,
        'category': item.category.name if item.category else 'Uncategorised',
        'unit': item.get_unit_display(),
        'stock': stock,
        'minimum': minimum,
        'status': status,
        'image': image,
    }


def _usage_dict(adj):
    return {
        'id': adj.pk,
        'item': adj.item.name,
        'qty': float(adj.quantity),
        'unit': adj.item.get_unit_display(),
        'room': None,  # room reference is stored inside the note
        'notes': adj.note,
        'by': adj.adjusted_by.name if adj.adjusted_by else 'Admin',
        'at': (
            timezone.localtime(adj.created_at)
            if timezone.is_aware(adj.created_at)
            else adj.created_at
        ).strftime('%d %b, %I:%M %p'),
    }


def _get_restaurant_staff(request):
    """Staff record if this session belongs to a restaurant-side staff member, else None.
    Same access rule as restaurant_dashboard / new_order_pos."""
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return None
    staff = Staff.objects.select_related("department", "hotel").filter(id=staff_id).first()
    if not staff:
        return None
    dept_name = staff.department.name.lower() if staff.department else ""
    role = (getattr(staff, "role", "") or "").lower()
    if not any(k in (dept_name + " " + role) for k in RESTAURANT_KEYWORDS):
        return None
    return staff


@staff_login_required
@never_cache
@login_required
def use_stock_pos(request):
    """Use Stock screen inside the staff POS shell (pos/base.html)."""
    from inventory.models import StockAdjustment

    staff = _get_restaurant_staff(request)
    if staff is None:
        return redirect("staff_login")

    items = list(_restaurant_stock_qs().order_by('category__name', 'name'))

    recent = (
        StockAdjustment.objects
        .filter(item_id__in=[i.id for i in items], adjustment_type='out')
        .select_related('item', 'adjusted_by')
        .order_by('-created_at', '-pk')[:15]
    )

    return render(request, "pos/use_stock.html", {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
        "items_data": [_stock_item_dict(i) for i in items],
        "log_data": [_usage_dict(a) for a in recent],
        "rooms": RoomUnit.objects.select_related('room').order_by('room_number'),
    })


@login_required
@transaction.atomic
def use_stock_submit(request):
    """POST {items: [{id, qty}], room_id, notes} -> deducts stock and writes StockAdjustment 'out' rows."""
    from inventory.models import InventoryItem, StockAdjustment

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    staff = _get_staff_for_request(request)
    if staff is None and not _is_admin(request.user):
        return JsonResponse({'error': 'A staff profile or admin access is required.'}, status=403)

    # merge duplicate lines, validate quantities
    wanted = {}
    for line in data.get('items') or []:
        try:
            item_id = int(line.get('id'))
            qty = Decimal(str(line.get('qty')))
        except (TypeError, ValueError, ArithmeticError):
            return JsonResponse({'error': 'Invalid item or quantity'}, status=400)
        if qty <= 0:
            return JsonResponse({'error': 'Quantity must be greater than zero'}, status=400)
        wanted[item_id] = wanted.get(item_id, Decimal('0')) + qty

    if not wanted:
        return JsonResponse({'error': 'No items selected'}, status=400)

    # only this department's stock can be used from here
    allowed = set(_restaurant_stock_qs().values_list('pk', flat=True))
    if not set(wanted) <= allowed:
        return JsonResponse({'error': 'One or more items are not restaurant stock'}, status=403)

    # StockAdjustment.note is max 200 chars: "Room 101 | your notes"
    parts = []
    room_id = data.get('room_id')
    if room_id:
        room_unit = RoomUnit.objects.filter(pk=room_id).first()
        if room_unit is None:
            return JsonResponse({'error': 'Invalid room selected'}, status=400)
        parts.append(f"Room {room_unit.room_number}")
    notes = (data.get('notes') or '').strip()
    if notes:
        parts.append(notes)
    note = " | ".join(parts)[:200]

    locked = {
        i.pk: i for i in
        InventoryItem.objects.select_for_update().filter(pk__in=wanted.keys())
    }

    # check every line first so nothing is deducted if any item is short
    for item_id, qty in wanted.items():
        item = locked.get(item_id)
        if item is None:
            return JsonResponse({'error': f'Item {item_id} not found'}, status=400)
        if qty > item.current_stock:
            return JsonResponse(
                {'error': f'Not enough {item.name}: only {item.current_stock} available'},
                status=400,
            )

    entries = []
    for item_id, qty in wanted.items():
        item = locked[item_id]
        item.current_stock = item.current_stock - qty
        item.save(update_fields=['current_stock'])
        entries.append(StockAdjustment.objects.create(
            item=item,
            adjustment_type='out',
            quantity=qty,
            note=note,
            adjusted_by=staff,
        ))

    fresh = _restaurant_stock_qs().filter(pk__in=wanted.keys())
    return JsonResponse({
        'success': True,
        'message': f'Usage logged for {len(entries)} item(s).',
        'items': [_stock_item_dict(i) for i in fresh],
        'log': [_usage_dict(e) for e in entries],
    })
@staff_login_required
@never_cache
@login_required
def maintenance_pos(request):
    """Maintenance page inside the staff POS shell (pos/base.html).
    Data loads client-side from the existing inventory maintenance APIs."""
    from inventory.models import MaintenanceLog
 
    staff = _get_restaurant_staff(request)
    if staff is None:
        return redirect("staff_login")
 
    return render(request, "pos/maintenance.html", {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
        "room_units": RoomUnit.objects.select_related("room").order_by("room_number"),
        "staff_list": Staff.objects.filter(hotel=staff.hotel).order_by("name"),
        "types": MaintenanceLog.TYPE,
        "priorities": MaintenanceLog.PRIORITY,
        "statuses": MaintenanceLog.STATUS,
    })
from hotel.models import Task, Shift, Attendance, LeaveRequest, Payroll, ShiftTemplate
# ════════════════════════════════════════════════════════════════
#  ATTENDANCE (staff POS) - my attendance only, shift based,
#  works with USE_TZ True/False
# ════════════════════════════════════════════════════════════════
import math
import calendar
from datetime import datetime as dt_cls, date as date_cls, time as time_cls, timedelta
from django.conf import settings
from django.views.decorators.http import require_GET, require_POST

# ── Face matching ────────────────────────────────────────────────
# Lower distance = more similar faces.
#   same person      -> usually 0.20 - 0.40
#   different person -> usually 0.50 +
# 0.6 was far too lenient (strangers passed). 0.45 is a safe start;
# use 0.40 if wrong people still get through, 0.50 if real users get rejected.
FACE_MATCH_THRESHOLD = 0.45

# The live face must be closer to THIS staff member than to any other
# staff member in the hotel by at least this much. Blocks look-alikes.
FACE_MARGIN = 0.05

DEFAULT_SHIFT_START = time_cls(9, 0)   # used only when NO shift is assigned
LATE_GRACE_MINUTES = 15
STANDARD_WORK_HOURS = 8                # used only when NO shift is assigned
HALF_DAY_HOURS = 4                     # used only when NO shift is assigned

SHIFT_DEFAULTS = {                     # same defaults as get_shifts
    "Morning": (time_cls(6, 0),  time_cls(14, 0)),
    "Evening": (time_cls(14, 0), time_cls(22, 0)),
    "Night":   (time_cls(22, 0), time_cls(6, 0)),
}


def _local_today():
    """Today's date; safe whether USE_TZ is True or False."""
    return timezone.localdate() if settings.USE_TZ else timezone.now().date()


def _face_distance(a, b):
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _best_distance(live, stored):
    """Smallest distance between the live descriptor and any stored one.
    `stored` may be a single 128-list (old format) or a list of them (new)."""
    if not stored:
        return None
    if isinstance(stored[0], (int, float)):      # old single-descriptor format
        stored = [stored]
    dists = [
        _face_distance(live, d)
        for d in stored
        if isinstance(d, (list, tuple)) and len(d) == 128
    ]
    return min(dists) if dists else None


def _closer_to_someone_else(staff, descriptor, my_distance):
    """True if the live face is as close to (or closer than) another staff
    member of the same hotel than it is to `staff`.
    This is what stops a different person from clocking in as someone else."""
    others = (
        Staff.objects
        .filter(hotel=staff.hotel, is_active=True)
        .exclude(pk=staff.pk)
        .exclude(face_descriptor__isnull=True)
    )
    for other in others:
        if not other.face_descriptor:
            continue
        try:
            d_other = _best_distance(descriptor, other.face_descriptor)
        except (TypeError, ValueError):
            continue
        if d_other is not None and d_other <= my_distance + FACE_MARGIN:
            return True
    return False


def _clock_str(value):
    if not value:
        return None
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%I:%M %p").lstrip("0")


def _naive_local(v):
    """Aware datetime -> naive local datetime (so it can be compared with date+time)."""
    if v is not None and timezone.is_aware(v):
        v = timezone.localtime(v).replace(tzinfo=None)
    return v


# ── shift helpers ────────────────────────────────────────────────
def _templates_for(hotel_id):
    return {
        t.shift_name: t
        for t in ShiftTemplate.objects.filter(hotel_id=hotel_id, is_active=True)
    }


def _shift_window(shift, templates):
    """(start_time, end_time) of an assigned Shift, or (None, None)."""
    if shift is None:
        return None, None
    if shift.custom_start and shift.custom_end:
        return shift.custom_start, shift.custom_end
    tpl = templates.get(shift.shift)
    if tpl:
        return tpl.start_time, tpl.end_time
    return SHIFT_DEFAULTS.get(shift.shift, (None, None))


def _shift_hours(start, end):
    """Length of a shift in hours (handles overnight shifts)."""
    if not (start and end):
        return None
    s = start.hour * 60 + start.minute
    e = end.hour * 60 + end.minute
    if e <= s:
        e += 24 * 60
    return (e - s) / 60


def _my_today_state(staff):
    a = Attendance.objects.filter(staff=staff, date=_local_today()).first()
    if not a or not a.check_in:
        return {"state": "idle", "check_in": None, "check_out": None}
    if not a.check_out:
        return {"state": "in", "check_in": _clock_str(a.check_in), "check_out": None}
    return {
        "state": "done",
        "check_in": _clock_str(a.check_in),
        "check_out": _clock_str(a.check_out),
    }


@staff_login_required
@never_cache
@login_required
def attendance_pos(request):
    staff = _get_restaurant_staff(request)
    if staff is None:
        return redirect("staff_login")

    today = _local_today()
    return render(request, "pos/attendance.html", {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
        "face_enrolled": bool(staff.face_descriptor),
        "face_descriptor_json": json.dumps(staff.face_descriptor or []),
        "face_threshold": FACE_MATCH_THRESHOLD,
        "today": today,
        "current_month": today.strftime("%Y-%m"),
        "my_state": json.dumps(_my_today_state(staff)),
    })


def _face_rejected(distance):
    """Standard 'wrong face' response. The page shows the Wrong-face popup
    when it receives matched: false."""
    return JsonResponse(
        {
            "success": False,
            "matched": False,
            "distance": round(distance, 3),
            "error": "Face did not match. Try again.",
        },
        status=200,
    )


@login_required
@require_POST
def attendance_face_clock(request):
    """POST {action: 'in'|'out', descriptor: [128 floats]}
    Verifies the face against the logged-in staff's registered descriptor(s),
    then records clock-in or clock-out using the staff's assigned shift."""
    staff = _get_restaurant_staff(request)
    if staff is None:
        return JsonResponse({"success": False, "error": "Login required"}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    action = data.get("action")
    descriptor = data.get("descriptor")
    if action not in ("in", "out"):
        return JsonResponse({"success": False, "error": "Invalid action"}, status=400)
    if not staff.face_descriptor:
        return JsonResponse(
            {"success": False, "error": "No face registered. Ask HR to register your face."},
            status=400,
        )
    if not isinstance(descriptor, list) or len(descriptor) != 128:
        return JsonResponse({"success": False, "error": "Invalid face data"}, status=400)

    try:
        distance = _best_distance(descriptor, staff.face_descriptor)
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "Invalid face data"}, status=400)

    if distance is None:
        return JsonResponse(
            {"success": False, "error": "Invalid stored face data. Ask HR to re-register your face."},
            status=400,
        )

    # 1) must be close enough to my own registered face
    if distance > FACE_MATCH_THRESHOLD:
        return _face_rejected(distance)

    # 2) must not be equally close to (or closer to) another staff member
    if _closer_to_someone_else(staff, descriptor, distance):
        return _face_rejected(distance)

    now = timezone.now()          # naive when USE_TZ = False, aware when True
    today = _local_today()

    # the shift assigned to this staff for today (may be None)
    shift = Shift.objects.filter(staff=staff, date=today).first()
    start_t, end_t = _shift_window(shift, _templates_for(staff.hotel_id))
    shift_hrs = _shift_hours(start_t, end_t)

    with transaction.atomic():
        att = (
            Attendance.objects.select_for_update()
            .filter(staff=staff, date=today)
            .first()
        )

        if action == "in":
            if att and att.check_in:
                return JsonResponse(
                    {"success": False, "matched": True,
                     "error": "You have already clocked in today."},
                    status=400,
                )

            shift_start = dt_cls.combine(today, start_t or DEFAULT_SHIFT_START)
            if settings.USE_TZ:
                shift_start = timezone.make_aware(shift_start)
            is_late = now > shift_start + timedelta(minutes=LATE_GRACE_MINUTES)

            if att is None:
                att = Attendance(staff=staff, hotel=staff.hotel, date=today)
            att.check_in = now
            att.status = "Late" if is_late else "Present"
            att.save()

        else:  # action == "out"
            if not att or not att.check_in:
                return JsonResponse(
                    {"success": False, "matched": True,
                     "error": "You have not clocked in yet."},
                    status=400,
                )
            if att.check_out:
                return JsonResponse(
                    {"success": False, "matched": True,
                     "error": "You have already clocked out."},
                    status=400,
                )

            hours = (now - att.check_in).total_seconds() / 3600
            planned = shift_hrs or STANDARD_WORK_HOURS
            half_limit = (shift_hrs / 2) if shift_hrs else HALF_DAY_HOURS

            att.check_out = now
            att.overtime_hours = round(max(0, hours - planned), 2)
            if hours < half_limit:
                att.status = "Half Day"
            att.save()

    return JsonResponse({
        "success": True,
        "matched": True,
        "action": action,
        "distance": round(distance, 3),
        "status": att.status,
        "message": "Clocked in successfully" if action == "in" else "Clocked out successfully",
        "my_state": _my_today_state(staff),
    })


@login_required
@require_GET
def attendance_pos_data(request):
    """GET ?month=YYYY-MM
    Shift-based attendance for the logged-in staff member only.

    Rules:
      - A day is expected ONLY if a Shift is assigned to this staff that day.
      - Assigned shift, day finished, no check-in   -> Absent
      - Assigned shift, today, no check-in yet      -> Pending (not counted)
      - Assigned shift, future day                  -> Upcoming (not counted)
      - Clocked in on a day with NO shift           -> counted as Present, flagged "extra"
      - No shift and no clock-in                    -> day is not listed
      - Late     = check-in after shift start + LATE_GRACE_MINUTES
      - Half Day = clocked out and worked less than half the shift
                   (HALF_DAY_HOURS if there is no shift)
    """
    staff = _get_restaurant_staff(request)
    if staff is None:
        return JsonResponse({"error": "Login required"}, status=401)

    today = _local_today()

    try:
        year, month = (int(x) for x in (request.GET.get("month") or "").split("-"))
        month_start = date_cls(year, month, 1)
    except (ValueError, TypeError):
        month_start = today.replace(day=1)

    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=last_day)

    status_filter = (request.GET.get("status") or "").strip().lower().replace(" ", "")

    records = {
        a.date: a
        for a in Attendance.objects.filter(staff=staff, date__range=(month_start, month_end))
    }
    shifts = {
        s.date: s
        for s in Shift.objects.filter(staff=staff, date__range=(month_start, month_end))
    }
    templates = _templates_for(staff.hotel_id)

    rows = []
    d = month_start
    while d <= month_end:
        a = records.get(d)
        shift = shifts.get(d)
        has_checkin = bool(a and a.check_in)

        # not scheduled and never clocked in: nothing to show
        if shift is None and not has_checkin:
            d += timedelta(days=1)
            continue

        start_t, end_t = _shift_window(shift, templates)
        shift_hrs = _shift_hours(start_t, end_t)

        hours = None
        hours_label = None
        if a and a.check_in and a.check_out:
            secs = max((a.check_out - a.check_in).total_seconds(), 0)
            hours = round(secs / 3600, 2)
            hours_label = f"{int(secs // 3600)}h {int((secs % 3600) // 60):02d}m"

        extra = shift is None and has_checkin

        if d > today and not has_checkin:
            status = "Upcoming"                     # scheduled, not started yet
        elif has_checkin:
            status = "Present"

            # late = arrived after shift start + grace
            if start_t:
                start_dt = dt_cls.combine(d, start_t) + timedelta(minutes=LATE_GRACE_MINUTES)
                if _naive_local(a.check_in) > start_dt:
                    status = "Late"

            # half day = finished the day but worked less than half the shift
            limit = (shift_hrs / 2) if shift_hrs else HALF_DAY_HOURS
            if hours is not None and hours < limit:
                status = "Half Day"
        elif d == today:
            status = "Pending"                      # scheduled today, not clocked in yet
        else:
            status = "Absent"                       # scheduled, day finished, no check-in

        shift_label = None
        if shift:
            shift_label = shift.custom_name or shift.shift
            if start_t and end_t:
                shift_label += (
                    f" {start_t.strftime('%I:%M %p').lstrip('0')}"
                    f" - {end_t.strftime('%I:%M %p').lstrip('0')}"
                )

        rows.append({
            "date": d.isoformat(),
            "date_label": d.strftime("%d %b, %a"),
            "check_in": _clock_str(a.check_in) if a else None,
            "check_out": _clock_str(a.check_out) if a else None,
            "hours": hours,
            "hours_label": hours_label,
            "status": status,
            "shift": shift_label,
            "extra": extra,
            "overtime": float(a.overtime_hours or 0) if a else 0.0,
        })
        d += timedelta(days=1)

    # today and past days newest first, then upcoming days at the bottom
    past = sorted((r for r in rows if r["status"] != "Upcoming"),
                  key=lambda r: r["date"], reverse=True)
    upcoming = sorted((r for r in rows if r["status"] == "Upcoming"),
                      key=lambda r: r["date"])
    rows = past + upcoming

    # only finished / worked days are counted
    counted = [r for r in rows if r["status"] not in ("Upcoming", "Pending")]

    stats = {
        "present":    sum(r["status"] in ("Present", "Late") for r in counted),   # full days only
        "late":       sum(r["status"] == "Late" for r in counted),
        "half_day":   sum(r["status"] == "Half Day" for r in counted),
        "absent":     sum(r["status"] == "Absent" for r in counted),
        "extra_days": sum(bool(r["extra"]) for r in counted),
        "overtime":   round(sum(r["overtime"] for r in counted), 2),
    }

    listed = [r for r in rows
              if not status_filter or r["status"].lower().replace(" ", "") == status_filter]

    return JsonResponse({
        "month": month_start.strftime("%Y-%m"),
        "month_label": month_start.strftime("%B %Y"),
        "working_days": sum(1 for r in counted if not r["extra"]),   # finished scheduled days
        "stats": stats,
        "rows": listed,
    })


# ════════════════════════════════════════════════════════════════
#  MY SHIFTS (staff POS) - weekly schedule for the logged-in staff
# ════════════════════════════════════════════════════════════════

def _clock12(t):
    return t.strftime("%I:%M %p").lstrip("0") if t else None


@staff_login_required
@never_cache
@login_required
def my_shifts_pos(request):
    staff = _get_restaurant_staff(request)
    if staff is None:
        return redirect("staff_login")

    return render(request, "pos/my_shifts.html", {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
    })


def _shift_category(shift, start_t):
    """Morning / Evening / Night for any shift, including Custom ones (by start time)."""
    name = (shift.shift or "").strip().title()
    if name in ("Morning", "Evening", "Night"):
        return name
    if start_t is None:
        return None
    h = start_t.hour
    if 4 <= h < 12:
        return "Morning"
    if 12 <= h < 20:
        return "Evening"
    return "Night"


@login_required
@require_GET
def my_shifts_pos_data(request):
    """GET ?start=YYYY-MM-DD  ->  the Mon-Sun week containing that date."""
    staff = _get_restaurant_staff(request)
    if staff is None:
        return JsonResponse({"error": "Login required"}, status=401)

    today = _local_today()
    try:
        base = dt_cls.strptime(request.GET.get("start", ""), "%Y-%m-%d").date()
    except ValueError:
        base = today

    week_start = base - timedelta(days=base.weekday())      # Monday
    week_end = week_start + timedelta(days=6)

    shifts = {
        s.date: s
        for s in Shift.objects
        .filter(staff=staff, date__range=(week_start, week_end))
        .select_related("department")
    }
    templates = _templates_for(staff.hotel_id)

    cats = ("Morning", "Evening", "Night")
    counts = {c: 0 for c in cats}
    hours = {c: 0.0 for c in cats}
    days = {c: [] for c in cats}
    rows = []
    total_hours = 0.0

    for i in range(7):
        d = week_start + timedelta(days=i)
        s = shifts.get(d)

        row = {
            "date": d.isoformat(),
            "day_short": d.strftime("%a"),
            "day": d.strftime("%A"),
            "date_label": f"{d.strftime('%b')} {d.day}",
            "is_today": d == today,
            "shift": "Off",
            "shift_type": None,
            "category": None,
            "time": None,
            "hours": None,
            "department": None,
            "status": "Today" if d == today else "Day off",
        }

        if s:
            start_t, end_t = _shift_window(s, templates)
            hrs = _shift_hours(start_t, end_t)
            cat = _shift_category(s, start_t)

            row["shift"] = s.custom_name or s.shift
            row["shift_type"] = s.shift
            row["category"] = cat
            row["hours"] = round(hrs, 1) if hrs else None
            if start_t and end_t:
                row["time"] = f"{_clock12(start_t)} - {_clock12(end_t)}"
            row["department"] = s.department.name if s.department else None

            if d == today:
                row["status"] = "Today"
            elif d < today:
                row["status"] = "Completed"
            else:
                row["status"] = "Upcoming"

            if cat in counts:
                counts[cat] += 1
                days[cat].append(d.strftime("%a"))
                if hrs:
                    hours[cat] += hrs
            if hrs:
                total_hours += hrs

        rows.append(row)

    return JsonResponse({
        "week_start": week_start.isoformat(),
        "prev_start": (week_start - timedelta(days=7)).isoformat(),
        "next_start": (week_start + timedelta(days=7)).isoformat(),
        "range_label": f"{week_start.day} {week_start.strftime('%b')} - "
                       f"{week_end.day} {week_end.strftime('%b %Y')}",
        "counts": counts,
        "hours": {k: round(v, 1) for k, v in hours.items()},
        "days": days,
        "total_shifts": sum(counts.values()),
        "total_hours": round(total_hours, 1),
        "rows": rows,
    })

# ════════════════════════════════════════════════════════════════
#  LEAVE (staff POS) - apply for leave + track my requests
# ════════════════════════════════════════════════════════════════

LEAVE_TYPES = {
    "casual": "Casual Leave",
    "sick": "Sick Leave",
    "earned": "Earned Leave",
    "bereavement": "Bereavement Leave",
    "other": "Other",
}


def _leave_date(v):
    """date or datetime -> local date (safe with USE_TZ True/False)."""
    if v is None:
        return None
    if hasattr(v, "date"):
        if timezone.is_aware(v):
            v = timezone.localtime(v)
        return v.date()
    return v


def _leave_row(l):
    days = (l.to_date - l.from_date).days + 1
    applied = _leave_date(getattr(l, "applied_at", None))
    ltype = (getattr(l, "leave_type", "") or "other").lower()
    same_day = l.from_date == l.to_date
    return {
        "id": l.id,
        "applied": applied.strftime("%d %b %Y") if applied else "—",
        "from_date": l.from_date.isoformat(),
        "to_date": l.to_date.isoformat(),
        "period": (
            l.from_date.strftime("%d %b")
            if same_day else
            f"{l.from_date.strftime('%d %b')} - {l.to_date.strftime('%d %b %Y')}"
        ),
        "days": days,
        "type": ltype,
        "type_label": LEAVE_TYPES.get(ltype, ltype.title()),
        "reason": l.reason or "",
        "status": l.status,
    }


@staff_login_required
@never_cache
@login_required
def leave_pos(request):
    staff = _get_restaurant_staff(request)
    if staff is None:
        return redirect("staff_login")

    return render(request, "pos/leave.html", {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": staff.hotel,
        "leave_types": LEAVE_TYPES.items(),
        "current_year": _local_today().year,
    })


@login_required
@require_GET
def leave_pos_data(request):
    """GET ?year=YYYY&month=M  ->  my leave requests + summary counts."""
    staff = _get_restaurant_staff(request)
    if staff is None:
        return JsonResponse({"error": "Login required"}, status=401)

    qs = LeaveRequest.objects.filter(staff=staff).order_by("-applied_at", "-pk")

    year = request.GET.get("year", "")
    month = request.GET.get("month", "")
    if year.isdigit():
        qs = qs.filter(from_date__year=int(year))
    if month.isdigit() and 1 <= int(month) <= 12:
        qs = qs.filter(from_date__month=int(month))

    rows = [_leave_row(l) for l in qs]

    return JsonResponse({
        "summary": {
            "total": len(rows),
            "pending": sum(r["status"] == "Pending" for r in rows),
            "approved": sum(r["status"] == "Approved" for r in rows),
            "rejected": sum(r["status"] == "Rejected" for r in rows),
        },
        "rows": rows,
    })


@login_required
@require_POST
def leave_pos_apply(request):
    """POST from_date, to_date, leave_type, reason."""
    staff = _get_restaurant_staff(request)
    if staff is None:
        return JsonResponse({"success": False, "error": "Login required"}, status=401)

    try:
        from_date = dt_cls.strptime(request.POST.get("from_date", ""), "%Y-%m-%d").date()
        to_date = dt_cls.strptime(request.POST.get("to_date", ""), "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"success": False, "error": "Please choose valid dates."}, status=400)

    if to_date < from_date:
        return JsonResponse(
            {"success": False, "error": "End date cannot be before start date."}, status=400
        )
    if (to_date - from_date).days > 365:
        return JsonResponse({"success": False, "error": "Date range is too large."}, status=400)

    leave_type = (request.POST.get("leave_type") or "").strip().lower()
    if leave_type not in LEAVE_TYPES:
        return JsonResponse({"success": False, "error": "Please select a leave type."}, status=400)

    reason = (request.POST.get("reason") or "").strip()
    if not reason:
        return JsonResponse({"success": False, "error": "Please enter a reason."}, status=400)

    overlap = LeaveRequest.objects.filter(
        staff=staff,
        status__in=["Pending", "Approved"],
        from_date__lte=to_date,
        to_date__gte=from_date,
    ).exists()
    if overlap:
        return JsonResponse(
            {"success": False,
             "error": "You already have a pending or approved leave in these dates."},
            status=400,
        )

    leave = LeaveRequest.objects.create(
        staff=staff,
        tenant=getattr(request, "tenant", None),
        from_date=from_date,
        to_date=to_date,
        leave_type=leave_type,
        reason=reason,
        status="Pending",
    )

    return JsonResponse({"success": True, "leave": _leave_row(leave)}, status=201)


@login_required
@require_POST
def leave_pos_cancel(request, leave_id):
    """Withdraw one of MY requests, only while it is still Pending."""
    staff = _get_restaurant_staff(request)
    if staff is None:
        return JsonResponse({"success": False, "error": "Login required"}, status=401)

    leave = LeaveRequest.objects.filter(id=leave_id, staff=staff).first()
    if leave is None:
        return JsonResponse({"success": False, "error": "Request not found."}, status=404)
    if leave.status != "Pending":
        return JsonResponse(
            {"success": False, "error": f"A {leave.status.lower()} request cannot be cancelled."},
            status=400,
        )

    leave.delete()
    return JsonResponse({"success": True})

# ════════════════════════════════════════════════════════════════
#  PAYROLL HISTORY  →  restaurant/views.py  (replace old section)
#  Uses helpers already in that file:
#    _is_admin, _get_staff_for_request, MONTH_NAMES
#  This one view also feeds the "Monthly breakdown" card, so the
#  separate payroll_breakdown view is no longer needed.
# ════════════════════════════════════════════════════════════════
import csv
import json
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import (
    DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum, Value,
)
from django.db.models.functions import Coalesce
from django.http import HttpResponse

from hotel.models import Payroll, PayrollLineItem

PAYROLL_PAGE_SIZE = 10
AVATAR_TONES = 6          # .tone-0 … .tone-5 in the template CSS
ZERO = Decimal("0")


def _inr(value, decimals=0):
    """Indian digit grouping: 248750 -> '₹ 2,48,750'."""
    value = Decimal(value or 0)
    whole, _, frac = f"{abs(value):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    sign = "-" if value < 0 else ""
    return f"₹ {sign}{whole}" + (f".{frac}" if frac else "")


def _money(v):
    return _inr(v, 2)


def _initials(name):
    bits = (name or "?").split()
    return ((bits[0][0] + (bits[-1][0] if len(bits) > 1 else "")).upper()) or "?"


def _month_key(value):
    """'2025-10' -> 202510, or None if invalid."""
    try:
        y, m = value.split("-")
        y, m = int(y), int(m)
        return y * 100 + m if 1 <= m <= 12 else None
    except (AttributeError, ValueError):
        return None


def _payroll_lines(p):
    """Earning / deduction lines of one payroll (needs prefetch_related('line_items')).

    Line items are the source of truth (they include custom items).
    Payrolls created before line items existed fall back to the plain fields.
    Returns: earn_rows, ded_rows, earn_total, ded_total, mismatch
    """
    items = list(p.line_items.all())
    if items:
        earn = sorted((i for i in items if i.line_type == "earning"), key=lambda i: (i.order, i.id))
        ded = sorted((i for i in items if i.line_type == "deduction"), key=lambda i: (i.order, i.id))
        earn_rows = [(i.label, i.amount) for i in earn]
        ded_rows = [(i.label, i.amount) for i in ded]
    else:
        earn_rows = [(l, a) for l, a in (
            ("Basic salary", p.basic_salary), ("Overtime", p.overtime_amount),
            ("Bonus", p.bonus), ("Incentive", p.incentive)) if a]
        ded_rows = [(l, a) for l, a in (
            ("Leave / absent", p.deductions), ("PF", p.pf_amount), ("ESI", p.esi_amount),
            ("Loan", p.loan_deduction), ("Tax / TDS", p.tax_deduction)) if a]

    earn_total = sum((a for _, a in earn_rows), ZERO)
    ded_total = sum((a for _, a in ded_rows), ZERO)
    # net should equal earnings − deductions (never below 0); flag stale records
    mismatch = abs(max(earn_total - ded_total, ZERO) - (p.net_salary or ZERO)) > Decimal("0.01")
    return earn_rows, ded_rows, earn_total, ded_total, mismatch


def _detail_payload(p, s, earn_rows, ded_rows, earn_total, ded_total, mismatch):
    """JSON for the salary modal. Used by the records table AND the monthly breakdown."""
    return {
        "employee": s.name,
        "role": getattr(s, "role", "") or "",
        "department": s.department.name if s.department else "—",
        "period": f"{MONTH_NAMES[p.month]} {p.year}",
        "earnings": [[l, _money(a)] for l, a in earn_rows],
        "deductions": [[l, _money(a)] for l, a in ded_rows],
        "gross": _money(earn_total),
        "total_ded": _money(ded_total),
        "net": _money(p.net_salary),
        "mismatch": mismatch,
        "status": "Paid" if p.paid_status == "Paid" else "Pending",
        "paid_at": p.paid_at.strftime("%d %b %Y, %I:%M %p") if p.paid_at else "",
        "paid_by": p.paid_by.name if p.paid_by else "",
        "notes": (p.notes or "").strip(),
        "payslip_id": p.id,
        "staff_id": s.pk,
    }


@login_required
@never_cache
def my_payroll(request):
    """Payroll History page (pos/payroll_history.html).

    • Hotel admin  → every payroll record of the hotel
    • Staff member → only their own records
    Filters: ?q= &status=paid|pending &year=YYYY|all &from=YYYY-MM &to=YYYY-MM
             &page= &export=csv
    Monthly breakdown: ?emp=<staff id> (admin only) &export=breakdown
    """
    staff = _get_staff_for_request(request)
    is_admin = _is_admin(request.user)

    if staff is None and not is_admin:
        return redirect("staff_login")

    hotel = staff.hotel if staff else getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")

    today = timezone.localdate() if settings.USE_TZ else timezone.now().date()

    # ── base queryset ──
    dec = DecimalField(max_digits=14, decimal_places=2)
    gross_sq = (
        PayrollLineItem.objects
        .filter(payroll=OuterRef("pk"), line_type="earning")
        .values("payroll")
        .annotate(t=Sum("amount"))
        .values("t")
    )
    base_qs = Payroll.objects.filter(hotel=hotel)
    if not is_admin:
        base_qs = base_qs.filter(staff=staff)

    base_qs = (
        base_qs
        .select_related("staff", "staff__department", "paid_by")
        .annotate(
            gross=Coalesce(Subquery(gross_sq, output_field=dec), Value(Decimal("0")), output_field=dec),
            period=ExpressionWrapper(F("year") * 100 + F("month"), output_field=IntegerField()),
        )
    )

    # ── filters ──
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").lower()
    year = request.GET.get("year") or str(today.year)
    p_from = (request.GET.get("from") or "").strip()
    p_to = (request.GET.get("to") or "").strip()

    qs = base_qs
    if year != "all" and year.isdigit():
        qs = qs.filter(year=int(year))
    if status == "paid":
        qs = qs.filter(paid_status="Paid")
    elif status == "pending":
        qs = qs.exclude(paid_status="Paid")
    if _month_key(p_from):
        qs = qs.filter(period__gte=_month_key(p_from))
    if _month_key(p_to):
        qs = qs.filter(period__lte=_month_key(p_to))
    if q:
        cond = (
            Q(staff__name__icontains=q)
            | Q(staff__employee_id__icontains=q)
            | Q(staff__department__name__icontains=q)
            | Q(notes__icontains=q)                     # payment reference lives in notes
        )
        month_hits = [i for i, n in enumerate(MONTH_NAMES) if i and n.lower().startswith(q.lower())]
        if month_hits:
            cond |= Q(month__in=month_hits)
        qs = qs.filter(cond)

    qs = qs.order_by("-year", "-month", "staff__name")

    # ── CSV export of the records table (same filters) ──
    if request.GET.get("export") == "csv":
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="payroll_history.csv"'
        w = csv.writer(resp)
        w.writerow(["Paid on", "Month", "Year", "Employee", "Department", "Gross", "Net pay", "Status"])
        for p in qs:
            w.writerow([
                p.paid_at.strftime("%d %b %Y") if p.paid_at else "",
                MONTH_NAMES[p.month], p.year,
                p.staff.name,
                p.staff.department.name if p.staff.department else "",
                p.gross, p.net_salary,
                "Paid" if p.paid_status == "Paid" else "Pending",
            ])
        return resp

    # ── summary cards ──
    total_net = qs.aggregate(t=Sum("net_salary"))["t"] or 0
    paid_qs = qs.filter(paid_status="Paid")
    paid_employees = paid_qs.values("staff_id").distinct().count()
    pending_qs = qs.exclude(paid_status="Paid")
    pending_count = pending_qs.count()
    pending_amount = pending_qs.aggregate(t=Sum("net_salary"))["t"] or 0

    this_month_qs = Payroll.objects.filter(hotel=hotel, month=today.month, year=today.year)
    if not is_admin:
        this_month_qs = this_month_qs.filter(staff=staff)
    this_month_total = this_month_qs.aggregate(t=Sum("net_salary"))["t"] or 0

    # ── pagination + row shaping ──
    page = Paginator(qs.prefetch_related("line_items"), PAYROLL_PAGE_SIZE).get_page(request.GET.get("page"))
    rows = []
    for p in page.object_list:
        s = p.staff
        try:
            photo = s.photo.url if getattr(s, "photo", None) else ""
        except ValueError:
            photo = ""

        earn_rows, ded_rows, earn_total, ded_total, mismatch = _payroll_lines(p)
        is_paid = p.paid_status == "Paid"
        dept = s.department.name if s.department else "—"

        rows.append({
            "id": p.id,
            "date": p.paid_at.strftime("%d %b %Y") if p.paid_at else "—",
            "period": f"{MONTH_NAMES[p.month][:3]} {p.year}",
            "name": s.name,
            "role": getattr(s, "role", "") or "",
            "department": dept,
            "initials": _initials(s.name),
            "tone": s.pk % AVATAR_TONES,
            "photo": photo,
            "gross": _inr(earn_total),
            "net": _inr(p.net_salary),
            "is_paid": is_paid,
            "detail_json": json.dumps(
                _detail_payload(p, s, earn_rows, ded_rows, earn_total, ded_total, mismatch)
            ),
        })

    # ════════════ Monthly breakdown (one employee, month by month) ════════════
    bd_employees = None
    if is_admin:
        bd_employees = Staff.objects.filter(hotel=hotel).select_related("department").order_by("name")
        emp = request.GET.get("emp", "")
        bd_target = bd_employees.filter(pk=emp).first() if emp.isdigit() else None
        bd_target = bd_target or bd_employees.first()
    else:
        bd_target = staff

    bd_rows = []
    tot = dict(earn=ZERO, ded=ZERO, pf=ZERO, esi=ZERO, bonus=ZERO, ot=ZERO, net=ZERO, paid=ZERO, pending=ZERO)

    if bd_target is not None:
        bd_qs = Payroll.objects.filter(hotel=hotel, staff=bd_target)
        if year != "all" and year.isdigit():
            bd_qs = bd_qs.filter(year=int(year))
        payrolls = list(
            bd_qs.select_related("paid_by").prefetch_related("line_items").order_by("year", "month")
        )

        def dash(v):
            return _money(v) if v else "—"

        cumulative = ZERO
        for p in payrolls:                       # oldest → newest so the running total is right
            earn_rows, ded_rows, earnings, deductions, mismatch = _payroll_lines(p)
            net = p.net_salary or ZERO
            cumulative += net
            is_paid = p.paid_status == "Paid"

            tot["earn"] += earnings;  tot["ded"] += deductions
            tot["pf"] += p.pf_amount; tot["esi"] += p.esi_amount
            tot["bonus"] += p.bonus;  tot["ot"] += p.overtime_amount
            tot["net"] += net
            tot["paid" if is_paid else "pending"] += net

            bd_rows.append({
                "label": f"{MONTH_NAMES[p.month]} {p.year}",
                "earnings": _money(earnings),
                "pf": dash(p.pf_amount), "esi": dash(p.esi_amount),
                "bonus": dash(p.bonus), "overtime": dash(p.overtime_amount),
                "deductions": _money(deductions),
                "has_deductions": bool(deductions),
                "net": _money(net),
                "cumulative": _money(cumulative),
                "is_paid": is_paid,
                "mismatch": mismatch,
                # modal data for this exact month (clicking the row opens it)
                "detail_json": json.dumps(
                    _detail_payload(p, bd_target, earn_rows, ded_rows, earnings, deductions, mismatch)
                ),
            })

        # CSV of the breakdown
        if request.GET.get("export") == "breakdown":
            resp = HttpResponse(content_type="text/csv")
            safe = bd_target.name.replace(" ", "_")
            resp["Content-Disposition"] = f'attachment; filename="payroll_{safe}_{year}.csv"'
            w = csv.writer(resp)
            w.writerow(["Period", "Earnings", "PF", "ESI", "Bonus", "Overtime",
                        "Deductions", "Net", "Cumulative net", "Status"])
            for r in bd_rows:
                w.writerow([r["label"], r["earnings"], r["pf"], r["esi"], r["bonus"], r["overtime"],
                            r["deductions"], r["net"], r["cumulative"], "Paid" if r["is_paid"] else "Pending"])
            return resp

        bd_rows.reverse()                        # newest month first on screen

    # ── querystring for pager / export links ──
    keep = request.GET.copy()
    keep.pop("page", None)
    keep.pop("export", None)
    keep["year"] = year
    if is_admin and bd_target is not None:
        keep["emp"] = str(bd_target.pk)

    years = sorted(set(base_qs.values_list("year", flat=True)) | {today.year}, reverse=True)

    return render(request, "pos/payroll_history.html", {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": hotel,
        "own_staff_id": staff.pk if staff else "",
        "is_admin_view": is_admin,
        "rows": rows,
        "page": page,
        "total_count": page.paginator.count,
        "years": years,
        "filters": {"q": q, "status": status, "year": year, "from": p_from, "to": p_to},
        "querystring": keep.urlencode(),
        "cards": {
            "total": _inr(total_net),
            "paid_employees": paid_employees,
            "pending_count": pending_count,
            "pending_amount": _inr(pending_amount),
            "this_month": _inr(this_month_total),
            "this_month_label": f"{MONTH_NAMES[today.month]} {today.year}",
        },
        # monthly breakdown
        "bd_target": bd_target,
        "bd_employees": bd_employees,
        "bd_rows": bd_rows,
        "bd_count": len(bd_rows),
        "bd_dept": (bd_target.department.name if bd_target and bd_target.department else "—"),
        "bd_totals": {k: _money(v) for k, v in tot.items()},
    })


# ════════════════════════════════════════════════════════════════
#  MY PROFILE  (staff POS)  →  restaurant/views.py
#  Replace your whole "MY PROFILE" section with this file's content.
#
#  Uses things already defined earlier in views.py:
#    _is_admin, _get_staff_for_request, _inr, _initials, MONTH_NAMES,
#    _templates_for, _shift_window, _shift_hours, _clock_str, _naive_local,
#    LATE_GRACE_MINUTES, HALF_DAY_HOURS, Shift, Attendance, LeaveRequest, Payroll
#
#  If you already pasted _attendance_month_rows / _attendance_month_stats
#  above attendance_pos_data, delete the two copies below (keep only one).
# ════════════════════════════════════════════════════════════════
import calendar
from datetime import datetime as dt_cls, timedelta

from django.contrib.auth import update_session_auth_hash
from django.views.decorators.http import require_POST


# ─────────────────────────  shared attendance helpers  ─────────────────────────

def _attendance_month_rows(staff, month_start, today):
    """One row per relevant day of the month, using the staff's assigned shifts.

    Rules:
      - A day is expected ONLY if a Shift is assigned that day.
      - Shift day finished, no check-in     -> Absent
      - Shift today, no check-in yet        -> Pending (not counted)
      - Shift in the future                 -> Upcoming (not counted)
      - Clocked in on a day with no shift   -> Present, flagged extra
      - Late     = check-in after shift start + LATE_GRACE_MINUTES
      - Half Day = clocked out having worked less than half the shift
    """
    last_day = calendar.monthrange(month_start.year, month_start.month)[1]
    month_end = month_start.replace(day=last_day)

    records = {
        a.date: a
        for a in Attendance.objects.filter(staff=staff, date__range=(month_start, month_end))
    }
    shifts = {
        s.date: s
        for s in Shift.objects.filter(staff=staff, date__range=(month_start, month_end))
    }
    templates = _templates_for(staff.hotel_id)

    rows = []
    d = month_start
    while d <= month_end:
        a = records.get(d)
        shift = shifts.get(d)
        has_checkin = bool(a and a.check_in)

        # not scheduled and never clocked in: nothing to show
        if shift is None and not has_checkin:
            d += timedelta(days=1)
            continue

        start_t, end_t = _shift_window(shift, templates)
        shift_hrs = _shift_hours(start_t, end_t)

        hours = None
        hours_label = None
        if a and a.check_in and a.check_out:
            secs = max((a.check_out - a.check_in).total_seconds(), 0)
            hours = round(secs / 3600, 2)
            hours_label = f"{int(secs // 3600)}h {int((secs % 3600) // 60):02d}m"

        extra = shift is None and has_checkin

        if d > today and not has_checkin:
            status = "Upcoming"
        elif has_checkin:
            status = "Present"
            if start_t:
                start_dt = dt_cls.combine(d, start_t) + timedelta(minutes=LATE_GRACE_MINUTES)
                if _naive_local(a.check_in) > start_dt:
                    status = "Late"
            limit = (shift_hrs / 2) if shift_hrs else HALF_DAY_HOURS
            if hours is not None and hours < limit:
                status = "Half Day"
        elif d == today:
            status = "Pending"
        else:
            status = "Absent"

        shift_label = None
        if shift:
            shift_label = shift.custom_name or shift.shift
            if start_t and end_t:
                shift_label += (
                    f" {start_t.strftime('%I:%M %p').lstrip('0')}"
                    f" - {end_t.strftime('%I:%M %p').lstrip('0')}"
                )

        rows.append({
            "date": d.isoformat(),
            "date_label": d.strftime("%d %b, %a"),
            "check_in": _clock_str(a.check_in) if a else None,
            "check_out": _clock_str(a.check_out) if a else None,
            "hours": hours,
            "hours_label": hours_label,
            "status": status,
            "shift": shift_label,
            "extra": extra,
            "overtime": float(a.overtime_hours or 0) if a else 0.0,
        })
        d += timedelta(days=1)

    return rows


def _attendance_month_stats(rows):
    """Summary counts. Only finished / worked days are counted."""
    counted = [r for r in rows if r["status"] not in ("Upcoming", "Pending")]
    return {
        "present":    sum(r["status"] in ("Present", "Late") for r in counted),  # full days only
        "late":       sum(r["status"] == "Late" for r in counted),
        "half_day":   sum(r["status"] == "Half Day" for r in counted),
        "absent":     sum(r["status"] == "Absent" for r in counted),
        "extra_days": sum(bool(r["extra"]) for r in counted),
        "overtime":   round(sum(r["overtime"] for r in counted), 2),
        "scheduled":  sum(1 for r in counted if not r["extra"]),   # finished scheduled days
    }


# ─────────────────────────  profile helpers  ─────────────────────────

def _safe_file_url(f):
    try:
        return f.url if f and f.name else ""
    except Exception:
        return ""


def _fmt_d(v):
    return v.strftime("%d %b %Y") if hasattr(v, "strftime") and v else ""


def _mask_tail(v, keep=4):
    v = (str(v) if v else "").strip()
    if not v:
        return ""
    return ("•" * max(len(v) - keep, 0) + v[-keep:]) if len(v) > keep else v


def _tenure_label(joined, today):
    if not joined:
        return ""
    if hasattr(joined, "date"):
        joined = joined.date()
    months = (today.year - joined.year) * 12 + (today.month - joined.month)
    if today.day < joined.day:
        months -= 1
    months = max(months, 0)
    y, m = divmod(months, 12)
    bits = []
    if y:
        bits.append(f"{y} yr{'s' if y > 1 else ''}")
    if m or not bits:
        bits.append(f"{m} mo")
    return " ".join(bits)


# ─────────────────────────  profile page  ─────────────────────────

@login_required
@never_cache
def my_profile(request):
    """Profile page (pos/profile.html).
    Staff → own profile.   Hotel admin (no Staff record) → account + hotel info."""
    staff = _get_staff_for_request(request)
    is_admin = _is_admin(request.user)

    if staff is None and not is_admin:
        return redirect("staff_login")

    hotel = staff.hotel if staff else getattr(request.user, "hotel", None)
    if hotel is None:
        return redirect("staff_login")

    today = timezone.localdate() if settings.USE_TZ else timezone.now().date()
    user = request.user

    ctx = {
        "is_staff_pos": True,
        "staff": staff,
        "hotel": hotel,
        "is_admin_view": staff is None,
        "email": user.email or (staff.user.email if staff and staff.user else ""),
    }

    if staff is None:
        # Hotel admin account
        name = user.get_full_name() or getattr(hotel, "owner_name", "") or user.username
        ctx.update({
            "p_name": name,
            "p_initials": _initials(name),
            "p_photo": _safe_file_url(getattr(hotel, "logo", None)),
            "p_role": "Hotel Admin",
            "p_dept": getattr(hotel, "hotel_name", ""),
            "p_active": user.is_active,
            "sections": [
                ("Account", [
                    ("Owner", getattr(hotel, "owner_name", "") or "—"),
                    ("Email", user.email or "—"),
                    ("Hotel", getattr(hotel, "hotel_name", "") or "—"),
                    ("City", getattr(hotel, "city", "") or "—"),
                    ("Address", getattr(hotel, "address", "") or "—"),
                ]),
            ],
            "stats": [],
        })
        return render(request, "pos/profile.html", ctx)

    # ── Staff profile ──
    dept = staff.department.name if staff.department else "—"
    role = (getattr(staff, "role", "") or "").strip() or "Staff"
    joined = getattr(staff, "joining_date", None)

    def g(field):
        v = getattr(staff, field, "") or ""
        return v if v != "" else "—"

    def d(field):
        return _fmt_d(getattr(staff, field, None)) or "—"

    sections = [
        ("Personal information", [
            ("Full name", staff.name or "—"),
            ("Nickname", g("nickname")),
            ("Date of birth", d("dob")),
            ("Gender", str(g("gender")).title() if g("gender") != "—" else "—"),
            ("Phone", g("phone")),
            ("Email", ctx["email"] or "—"),
            ("Address", g("address")),
        ]),
        ("Employment", [
            ("Employee ID", g("employee_id")),
            ("Department", dept),
            ("Role", role),
            ("Employment type", str(g("employment_type")).replace("_", " ").title() if g("employment_type") != "—" else "—"),
            ("Joining date", _fmt_d(joined) or "—"),
            ("Time with us", _tenure_label(joined, today) or "—"),
            ("Monthly salary", _inr(staff.salary) if staff.salary else "—"),
        ]),
        ("Emergency contact", [
            ("Name", g("emergency_contact_name")),
            ("Phone", g("emergency_contact_phone")),
        ]),
        ("Bank & statutory", [
            ("Bank account", _mask_tail(getattr(staff, "bank_account", "")) or "—"),
            ("IFSC", g("ifsc")),
            ("PF number", g("pf_number")),
            ("ESI number", g("esi_number")),
        ]),
    ]

    # ── This month at a glance (same shift-based rules as the Attendance page) ──
    month_start = today.replace(day=1)
    att = _attendance_month_stats(_attendance_month_rows(staff, month_start, today))

    year_leaves = LeaveRequest.objects.filter(staff=staff, from_date__year=today.year)
    pending_leaves = year_leaves.filter(status="Pending").count()
    approved_leaves = year_leaves.filter(status="Approved").count()

    last_pay = Payroll.objects.filter(staff=staff).order_by("-year", "-month").first()

    month_label = f"{MONTH_NAMES[today.month]} {today.year}"
    stats = [
        {"label": "Days present", "value": att["present"],
         "sub": (f"of {att['scheduled']} scheduled days" if att["scheduled"] else month_label),
         "tone": "green", "icon": "icon-clock"},
        {"label": "Half day / Absent", "value": f'{att["half_day"]} / {att["absent"]}',
         "sub": "This month", "tone": "orange", "icon": "icon-triangle-alert"},
        {"label": "Overtime hours", "value": att["overtime"],
         "sub": "This month", "tone": "blue", "icon": "icon-clock"},
        {"label": "Leave requests", "value": year_leaves.count(),
         "sub": f"{pending_leaves} pending · {approved_leaves} approved this year",
         "tone": "violet", "icon": "icon-plane"},
    ]

    ctx.update({
        "p_name": staff.name,
        "p_initials": _initials(staff.name),
        "p_photo": _safe_file_url(getattr(staff, "photo", None)),
        "p_role": role,
        "p_dept": dept,
        "p_active": getattr(staff, "is_active", True),
        "p_tenure": _tenure_label(joined, today),
        "sections": sections,
        "stats": stats,
        "last_pay": ({
            "period": f"{MONTH_NAMES[last_pay.month]} {last_pay.year}",
            "net": _inr(last_pay.net_salary),
            "paid": last_pay.paid_status == "Paid",
        } if last_pay else None),
        # values for the edit form
        "f": {
            "name": staff.name or "",
            "nickname": getattr(staff, "nickname", "") or "",
            "phone": getattr(staff, "phone", "") or "",
            "address": getattr(staff, "address", "") or "",
            "ec_name": getattr(staff, "emergency_contact_name", "") or "",
            "ec_phone": getattr(staff, "emergency_contact_phone", "") or "",
        },
    })
    return render(request, "pos/profile.html", ctx)


@login_required
@require_POST
def profile_update(request):
    """AJAX. POST form_type=profile (staff details + photo) or form_type=password."""
    staff = _get_staff_for_request(request)
    is_admin = _is_admin(request.user)
    if staff is None and not is_admin:
        return JsonResponse({"success": False, "error": "Login required"}, status=401)

    form_type = request.POST.get("form_type")

    # ── change password (staff and admin) ──
    if form_type == "password":
        current = request.POST.get("current_password") or ""
        new = request.POST.get("new_password") or ""
        confirm = request.POST.get("confirm_password") or ""

        if not current:
            return JsonResponse({"success": False, "error": "Enter your current password."}, status=400)
        if not request.user.check_password(current):
            return JsonResponse({"success": False, "error": "Current password is incorrect."}, status=400)
        if len(new) < 8:
            return JsonResponse({"success": False, "error": "New password must be at least 8 characters."}, status=400)
        if new != confirm:
            return JsonResponse({"success": False, "error": "New password and confirmation do not match."}, status=400)
        if new == current:
            return JsonResponse({"success": False, "error": "New password must be different from the current one."}, status=400)

        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)      # stay logged in
        return JsonResponse({"success": True, "message": "Password changed."})

    # ── staff details ──
    if form_type == "profile":
        if staff is None:
            return JsonResponse({"success": False, "error": "Admin details are edited in Hotel details."}, status=400)

        name = (request.POST.get("name") or "").strip()
        if not name:
            return JsonResponse({"success": False, "error": "Name is required."}, status=400)

        phone = (request.POST.get("phone") or "").strip()
        if phone and (len(phone) > 20 or not all(c.isdigit() or c in "+-() " for c in phone)):
            return JsonResponse({"success": False, "error": "Enter a valid phone number."}, status=400)

        photo = request.FILES.get("photo")
        if photo:
            if not (photo.content_type or "").startswith("image/"):
                return JsonResponse({"success": False, "error": "Photo must be an image."}, status=400)
            if photo.size > 5 * 1024 * 1024:
                return JsonResponse({"success": False, "error": "Photo must be under 5 MB."}, status=400)

        staff.name = name
        staff.phone = phone
        staff.nickname = (request.POST.get("nickname") or "").strip()
        staff.address = (request.POST.get("address") or "").strip()
        staff.emergency_contact_name = (request.POST.get("emergency_contact_name") or "").strip()
        staff.emergency_contact_phone = (request.POST.get("emergency_contact_phone") or "").strip()
        if photo:
            staff.photo = photo
        staff.save()
        return JsonResponse({"success": True, "message": "Profile updated."})

    return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

# ════════════════════════════════════════════════════════════════
#  1) ADD TO restaurant/views.py  (paste at the bottom)
# ════════════════════════════════════════════════════════════════
import json
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, get_connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_MAX_RECIPIENTS = 100


def _email_directory(request):
    """Everyone the current user is allowed to email.

    Returns (hotel, staff_rows, admin_rows) or None when the user is
    neither a staff member nor the hotel admin.
    Only people from the SAME hotel are ever returned, and the sender
    is left out of the list.
    """
    staff = _get_staff_for_request(request)
    if staff is None and not _is_admin(request.user):
        return None

    hotel = staff.hotel if staff else getattr(request.user, "hotel", None)
    if hotel is None:
        return None

    me = (request.user.email or "").strip().lower()

    staff_rows = []
    qs = (
        Staff.objects.filter(hotel=hotel, is_active=True)
        .select_related("user", "department")
        .order_by("name")
    )
    for s in qs:
        email = (s.user.email if s.user else "") or ""
        email = email.strip()
        if not email or email.lower() == me:
            continue
        staff_rows.append({
            "name": s.name or email,
            "email": email,
            "department": s.department.name if s.department else "",
        })

    admin_rows = []
    admin_email = (getattr(hotel, "email", "") or "").strip()
    if admin_email and admin_email.lower() != me:
        admin_rows.append({
            "name": getattr(hotel, "owner_name", "") or getattr(hotel, "hotel_name", "") or "Hotel Admin",
            "email": admin_email,
            "department": "Hotel Admin",
        })

    return hotel, staff_rows, admin_rows


@login_required
@never_cache
@require_GET
def email_recipients(request):
    """JSON list of staff + hotel admin that can be picked in the Compose Email modal."""
    directory = _email_directory(request)
    if directory is None:
        return JsonResponse({"error": "Not allowed"}, status=403)

    _, staff_rows, admin_rows = directory
    return JsonResponse({"staff": staff_rows, "admin": admin_rows})


@login_required
@require_POST
def send_dashboard_email(request):
    """POST JSON {subject, message, recipients: [email, ...]}

    Each recipient gets their own copy (nobody sees the other addresses).
    Reply-To is set to the sender so replies reach them directly.
    """
    directory = _email_directory(request)
    if directory is None:
        return JsonResponse({"success": False, "error": "Not allowed"}, status=403)
    hotel, staff_rows, admin_rows = directory

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Invalid request."}, status=400)

    subject = (data.get("subject") or "").strip()
    message = (data.get("message") or "").strip()
    requested = data.get("recipients") or []

    if not subject:
        return JsonResponse({"success": False, "error": "Please enter a subject."}, status=400)
    if len(subject) > 200:
        return JsonResponse({"success": False, "error": "Subject is too long."}, status=400)
    if not message:
        return JsonResponse({"success": False, "error": "Please type a message."}, status=400)
    if len(message) > 5000:
        return JsonResponse({"success": False, "error": "Message is too long."}, status=400)
    if not isinstance(requested, list) or not requested:
        return JsonResponse({"success": False, "error": "Select at least one recipient."}, status=400)
    if len(requested) > EMAIL_MAX_RECIPIENTS:
        return JsonResponse(
            {"success": False, "error": f"You can email at most {EMAIL_MAX_RECIPIENTS} people at once."},
            status=400,
        )

    # Only addresses that belong to this hotel's directory are accepted
    allowed = {r["email"].lower(): r for r in staff_rows + admin_rows}
    targets, seen = [], set()
    for e in requested:
        key = str(e).strip().lower()
        if key in allowed and key not in seen and _EMAIL_RE.match(key):
            seen.add(key)
            targets.append(allowed[key])

    if not targets:
        return JsonResponse({"success": False, "error": "No valid recipients selected."}, status=400)

    staff = _get_staff_for_request(request)
    sender_name = _actor_name(staff, request.user) or "Management"
    sender_email = (request.user.email or "").strip()
    hotel_name = getattr(hotel, "hotel_name", "") or "Hotel"

    msgs = []
    for t in targets:
        body = (
            f"Hello {t['name']},\n\n"
            f"{message}\n\n"
            f"Regards,\n{sender_name}\n{hotel_name}"
        )
        msgs.append(EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[t["email"]],
            reply_to=[sender_email] if _EMAIL_RE.match(sender_email) else None,
        ))

    try:
        connection = get_connection(fail_silently=False)
        sent = connection.send_messages(msgs) or 0
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Email could not be sent: {e}"}, status=500)

    if sent == 0:
        return JsonResponse({"success": False, "error": "Email could not be sent."}, status=500)

    return JsonResponse({
        "success": True,
        "sent": sent,
        "message": f"Email sent to {sent} recipient{'s' if sent != 1 else ''}.",
    })


