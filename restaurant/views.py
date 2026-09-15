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
def order_list(request):
    orders = RestaurantOrder.objects.prefetch_related(
        'items__item'
    ).select_related(
        'table', 'room', 'served_by', 'booking__guest', 'reservation',
        'preparing_by', 'served_status_by'
    ).order_by('-created_at')

    order_ids = [o.id for o in orders]
    payments_by_order = {
        p.order_id: p
        for p in BillingPayment.objects.filter(order_id__in=order_ids)
    }

    data = []
    for o in orders:
        room_display = None
        guest_name = None
        booking_id = None

        staff_name = (
            (o.served_by.get_full_name() or o.served_by.username)
            if o.served_by else "Admin"
        )

        if o.booking:
            booking_id = o.booking.id
            if o.booking.room_unit:
                room_display = _room_display(o.booking.room_unit)
            if o.booking.guest:
                guest_name = o.booking.guest.full_name
        elif o.reservation:
            room_display = f"Table {o.reservation.table.number}"
            guest_name = o.reservation.guest_name
        elif o.room:
            room_display = o.room.room_type

        payment = payments_by_order.get(o.id)

        data.append({
            'id': o.id,
            'order_number': o.order_number,
            'type': o.order_type,
            'status': o.status,
            'table': o.table.number if o.table else None,
            'room': room_display,
            'guest': guest_name,
            'booking_id': booking_id,
            'served_by': staff_name,
            'preparing_by': o.preparing_by.name if o.preparing_by else None,
            'preparing_at': o.preparing_at.isoformat() if o.preparing_at else None,
            'served_status_by': o.served_status_by.name if o.served_status_by else None,
            'served_status_at': o.served_status_at.isoformat() if o.served_status_at else None,
            'total': float(o.total_amount),
            'tax': float(o.tax_amount),
            'created_at': o.created_at.isoformat(),
            'payment_status': payment.payment_status if payment else None,
            'payment_method': payment.method if payment else None,
            'paid_at': payment.paid_at.isoformat() if (payment and payment.paid_at) else None,
            'items': [
                {
                    'name': oi.item.name,
                    'qty': oi.quantity,
                    'unit_price': float(oi.unit_price),
                    'subtotal': float(oi.subtotal),
                }
                for oi in o.items.all()
            ],
        })

    return JsonResponse({'orders': data})


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

    staff = getattr(request.user, 'staff_profile', None)
    user = request.user

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

@csrf_exempt
def mark_order_paid(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    method = (data.get('method') or '').strip()
    if not method:
        return JsonResponse({'error': 'Payment method is required'}, status=400)

    try:
        payment = BillingPayment.objects.select_related('order', 'order__table').get(order__id=order_id)
    except BillingPayment.DoesNotExist:
        return JsonResponse({'error': 'Payment record not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    if payment.payment_status == 'paid':
        return JsonResponse({
            'error': 'Already marked as paid',
            'paid_at': payment.paid_at.isoformat() if payment.paid_at else None,
        }, status=400)

    try:
        with transaction.atomic():
            payment.method = method
            payment.payment_status = 'paid'
            payment.paid_at = timezone.now()
            payment.reference_number = data.get('reference_number', '')
            payment.save()

            payment.order.status = 'served'
            payment.order.save()

            # ✅ FIX: free the table here too — not just via update_order_status
            _free_table_if_needed(payment.order)

        return JsonResponse({
            'success': True,
            'order_id': payment.order.id,
            'order_number': payment.order.order_number,
            'paid_at': payment.paid_at.isoformat(),
            'method': payment.method,
            'total': float(payment.total_amount),
            'message': f'Payment of ₹{float(payment.total_amount)} received via {payment.method}',
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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


@require_GET
def list_reservations(request):
    reservations = TableReservation.objects.select_related('table').all().order_by('-created_at')

    data = [
        {
            "id": r.id,
            "guest_name": r.guest_name,
            "phone": r.phone,
            "table": r.table.number if r.table else None,
            "guests_count": r.guests_count,
            "status": r.status,
            "reservation_time": r.reservation_time.strftime("%Y-%m-%d %H:%M"),
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in reservations
    ]

    return JsonResponse({"count": len(data), "reservations": data})


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

    tables_qs = Table.objects.all()
    tables_occupied = tables_qs.filter(is_occupied=True).count()
    tables_available = tables_qs.count() - tables_occupied

    tables = [
        {"id": t.id, "number": t.number, "capacity": t.capacity, "is_occupied": t.is_occupied}
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
                    "subtotal": float(oi.subtotal),
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
        "tables_total": tables_qs.count(),
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

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        start, end, range_type = _get_dashboard_range(request)
        dash_stats = _build_dashboard_stats(start, end)

        # comparison period: same length window immediately before `start`
        span_days = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span_days - 1)
        prev_stats = _build_dashboard_stats(prev_start, prev_end)

        def pct_change(cur, prev):
            if not prev:
                return 100.0 if cur else 0.0
            return round(((cur - prev) / prev) * 100, 1)

        dash_stats['deltas'] = {
            'total_sales': pct_change(dash_stats['total_sales'], prev_stats['total_sales']),
            'order_count': pct_change(dash_stats['order_count'], prev_stats['order_count']),
            'avg_order_value': pct_change(dash_stats['avg_order_value'], prev_stats['avg_order_value']),
        }
        dash_stats['range_type'] = range_type
        dash_stats['range_from'] = start.isoformat()
        dash_stats['range_to'] = end.isoformat()
        dash_stats['tables_occupied'] = tables_occupied
        dash_stats['tables_total'] = tables_qs.count()
        dash_stats['tables_live'] = tables

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

    return render(request, "pos.html", {
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