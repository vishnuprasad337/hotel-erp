import json
from decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import MenuCategory, MenuItem, Table, RestaurantOrder, OrderItem
from pms.models import Room, Booking


# ── MENU CATEGORIES ─────────────────────────────────────────

@csrf_exempt
def add_menu_category(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        category = MenuCategory.objects.create(
            name=data.get('name'),
            order=data.get('order', 0)
        )
        return JsonResponse({'success': True, 'id': category.id, 'name': category.name})
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


@csrf_exempt
def add_menu_item(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        category = get_object_or_404(MenuCategory, pk=data.get('category_id'))
        item = MenuItem.objects.create(
            category=category,
            name=data.get('name'),
            description=data.get('description', ''),
            price=data.get('price'),
            tax_percent=data.get('tax_percent', 5),
            is_available=data.get('is_available', True),
            is_veg=data.get('is_veg', True),
            image=request.FILES.get('image')
        )
        return JsonResponse({'success': True, 'id': item.id, 'name': item.name,'image': item.image.url if item.image else None})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def update_menu_item(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    item = get_object_or_404(MenuItem, pk=pk)
    try:
        data = json.loads(request.body)
        item.name = data.get('name', item.name)
        item.description = data.get('description', item.description)
        item.price = data.get('price', item.price)
        item.tax_percent = data.get('tax_percent', item.tax_percent)
        item.is_available = data.get('is_available', item.is_available)
        item.is_veg = data.get('is_veg', item.is_veg)
        item.save()
        return JsonResponse({'success': True})
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




@csrf_exempt
def add_table(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        table = Table.objects.create(
            number=data.get('number'),
            capacity=data.get('capacity', 4)
        )
        return JsonResponse({'success': True, 'id': table.id, 'number': table.number})
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
        {
            'id': t.id,
            'number': t.number,
            'capacity': t.capacity,
            'is_occupied': t.is_occupied,
        }
        for t in tables
    ]
    return JsonResponse({'tables': data})



@login_required
def order_list(request):
    orders = RestaurantOrder.objects.prefetch_related(
        'items__item'
    ).select_related(
        'table',
        'room',
        'served_by',
        'booking__guest',
        'reservation'
    ).order_by('-created_at')

    data = []

    for o in orders:
        room_display = None
        guest_name = None
        booking_id = None

        staff_name = (
    o.served_by.get_full_name() or o.served_by.username
    if o.served_by else "Admin"
)
        if o.booking:
            booking_id = o.booking.id

            if o.booking.room_unit:
                room_display = f"{o.booking.room_unit.room_number} - {o.booking.room.room_type}"

            if o.booking.guest:
                guest_name = o.booking.guest.full_name

        elif o.reservation:
            room_display = f"Table {o.reservation.table.number}"
            guest_name = o.reservation.guest_name

        elif o.room:
            room_display = o.room.room_type

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
            'total': float(o.total_amount),
            'tax': float(o.tax_amount),
            'created_at': o.created_at.isoformat(),
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
    ).filter(
        status__in=['pending', 'preparing']
    ).order_by('-created_at')

    data = []
    for o in orders:
        data.append({
            'id': o.id,
            'order_number': o.order_number,
            'type': o.order_type,
            'status': o.status,
            'table': o.table.number if o.table else None,
            'room': o.room.room_number if o.room else None,
            'total': float(o.total_amount),
            'tax': float(o.tax_amount),
            'created_at': o.created_at.isoformat(),
            'items': [
                {
                    'name': oi.item.name,
                    'qty': oi.quantity,
                    'subtotal': float(oi.subtotal),
                }
                for oi in o.items.all()
            ],
        })
    return JsonResponse({'orders': data})


def restaurant_stats(request):
    
    from django.utils import timezone
    from django.db.models import Sum

    today = timezone.now().date()
    all_orders = RestaurantOrder.objects.all()
    today_orders = all_orders.filter(created_at__date=today)

    revenue = today_orders.filter(
        status='served'
    ).aggregate(
        total=Sum('total_amount')
    )['total'] or 0

    return JsonResponse({
        'today_revenue': float(revenue),
        'total_orders': all_orders.count(),
        'pending': all_orders.filter(status__in=['pending', 'preparing']).count(),
        'served_today': today_orders.filter(status='served').count(),
    })# at the top, import BillingPayment
from billing.models import GuestFolio, FolioCharge, BillingPayment

@login_required
@csrf_exempt
@transaction.atomic
def create_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        staff          = getattr(request.user, 'staff_profile', None)
        user           = request.user
        data           = json.loads(request.body)

        order_type     = data.get('order_type', 'dine_in')
        table_id       = data.get('table_id')
        room_id        = data.get('room_id')
        reservation_id = data.get('reservation_id')
        charge_to_room = data.get('charge_to_room', False)
        items          = data.get('items', [])
        payment_method = data.get('payment_method')  # ← from frontend for takeaway

        if not items:
            return JsonResponse({'error': 'No items selected'}, status=400)

        room_obj    = None
        unit        = None
        booking     = None
        reservation = None

        # ── room service ──
        if order_type == 'room_service' and room_id:
            from pms.models import Room, RoomUnit
            room_obj = Room.objects.filter(id=room_id).first()
            if not room_obj:
                unit = RoomUnit.objects.filter(id=room_id).select_related('room').first()
                if unit:
                    room_obj = unit.room
            if not room_obj:
                return JsonResponse({'error': 'Invalid room selected'}, status=400)
            if unit:
                booking = Booking.objects.filter(room_unit=unit, status='checked_in').select_related('guest').first()
            else:
                booking = Booking.objects.filter(room=room_obj, status='checked_in').select_related('guest').first()
            if not booking:
                return JsonResponse({'error': 'No active booking for this room'}, status=400)

        # ── dine-in reservation ──
        if order_type == 'dine_in' and reservation_id:
            from .models import TableReservation
            reservation = TableReservation.objects.filter(id=reservation_id).first()
            if not reservation:
                return JsonResponse({'error': 'Invalid reservation'}, status=400)
            table_id = reservation.table_id

        # ── create order ──
        order = RestaurantOrder.objects.create(
            order_type=order_type,
            table_id=table_id if table_id else None,
            room=room_obj,
            booking=booking,
            reservation=reservation,
            charge_to_room=charge_to_room,
            served_by=user,
        )

        total     = Decimal('0')
        tax_total = Decimal('0')

        for i in items:
            menu_item = get_object_or_404(MenuItem, pk=i['id'])
            qty       = int(i['qty'])
            subtotal  = menu_item.price * qty
            tax       = subtotal * menu_item.tax_percent / 100
            OrderItem.objects.create(
                order=order,
                item=menu_item,
                quantity=qty,
                unit_price=menu_item.price,
                note=i.get('note', ''),
            )
            total     += subtotal
            tax_total += tax

        order.total_amount = total
        order.tax_amount   = tax_total
        order.save()

        # ── dine-in: mark table occupied ──
        if order_type == 'dine_in' and table_id:
            Table.objects.filter(pk=table_id).update(is_occupied=True)

        # ── TAKEAWAY: create BillingPayment directly (no folio needed) ──
        if order_type == 'takeaway':
            BillingPayment.objects.create(
                order=order,
                folio=None,
                amount=total,
                tax_amount=tax_total,
                total_amount=total + tax_total,
                method=payment_method,
                payment_status="pending",
                received_by=staff,
            )

        # ── room service: post to folio ──
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
                        added_by=staff if staff else None
                    )
            except Exception as e:
                return JsonResponse({
                    'success': True,
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'warning': f'Billing failed: {str(e)}',
                })

        return JsonResponse({
            'success':        True,
            'order_id':       order.id,
            'order_number':   order.order_number,
            'booking_id':     booking.id if booking else None,
            'reservation_id': reservation.id if reservation else None,
            'total':          float(total),
            'tax':            float(tax_total),
            'grand_total':    float(total + tax_total),
            'payment_status': 'pending' if order_type == 'takeaway' else None,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
def mark_order_paid(request, order_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    from billing.models import BillingPayment
    from django.utils import timezone

    try:
        data    = json.loads(request.body)
        payment = BillingPayment.objects.get(order__id=order_id)
    except BillingPayment.DoesNotExist:
        return JsonResponse({'error': 'Payment record not found'}, status=404)

    if payment.payment_status == 'paid':
        return JsonResponse({'error': 'Already marked as paid'}, status=400)

    payment.method           = data.get('method', payment.method)
    payment.payment_status   = 'paid'
    payment.paid_at          = timezone.now()
    payment.reference_number = data.get('reference_number', '')
    payment.save()

    payment.order.status = 'served'
    payment.order.save()

    return JsonResponse({
        'success':  True,
        'order_id': payment.order.id,
        'paid_at':  payment.paid_at.isoformat(),
        'method':   payment.method,
        'total':    float(payment.total_amount),
    })
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
    if status not in ['pending', 'preparing', 'served', 'cancelled']:
        return JsonResponse({'error': 'Invalid status'}, status=400)

    order.status = status
    order.save()

    
    if status in ['served', 'cancelled']:
        if order.table:
            order.table.is_occupied = False
            order.table.save()

    return JsonResponse({'success': True, 'status': status})



def occupied_rooms(request):
   
    bookings = Booking.objects.filter(
        status='checked_in',
        room_unit__isnull=False
    ).select_related('room_unit', 'room')

    data = [
        {
            'id': b.room_unit.id,
            'room_number': b.room_unit.room_number, 
            'room_type': b.room.room_type,
        }
        for b in bookings
    ]

    return JsonResponse({'rooms': data})
def update_table_status(table):
   

    has_active_order = table.restaurantorder_set.filter(
        status__in=["pending", "preparing"]
    ).exists()

    has_active_reservation = table.tablereservation_set.filter(
        status__in=["reserved", "seated"]
    ).exists()

    table.is_occupied = has_active_order
    table.save()

    return {
        "occupied": has_active_order,
        "reservation": has_active_reservation
    }
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime

from .models import TableReservation, Table

import json
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.dateparse import parse_datetime

from .models import TableReservation, Table


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
            "reservation_time": reservation.reservation_time,
            "status": reservation.status
        })

    except Table.DoesNotExist:
        return JsonResponse({"error": "Table not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
from django.views.decorators.http import require_GET
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.http import JsonResponse

@require_GET
def list_reservations(request):

    reservations = TableReservation.objects.select_related('table')\
        .all().order_by('-created_at')

    data = []

    for r in reservations:
        data.append({
            "id": r.id,
            "guest_name": r.guest_name,
            "phone": r.phone,
            "table": r.table.number if r.table else None,
            "guests_count": r.guests_count,
            "status": r.status,

           
            "reservation_time": r.reservation_time.strftime("%Y-%m-%d %H:%M"),
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    return JsonResponse({
        "count": len(data),
        "reservations": data
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

        update_table_status(table)

        return JsonResponse({
            "message": "Reservation deleted successfully"
        })

    except TableReservation.DoesNotExist:
        return JsonResponse({"error": "Reservation not found"}, status=404)





from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import ExtractHour

from accounts.models import Staff
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import ExtractHour
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required

from accounts.models import Staff, Department
from hotel.models import Task, Shift, Attendance, LeaveRequest, RoomUnit
from pms.models import Booking, Room
from .models import (
    RestaurantOrder, Table, TableReservation,
    MenuCategory, MenuItem
)
from django.db.models import Sum, Count, Q, F
from accounts.decorators import staff_login_required
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

    RESTAURANT_KEYWORDS = ['restaurant', 'kitchen', 'dining', 'food', 'bar',
                           'manager', 'owner', 'admin', 'hotel']
    dept_name = (staff.department.name.lower() if staff.department else "")
    role      = (getattr(staff, 'role', '') or '').lower()
    combined  = dept_name + " " + role

    if not any(k in combined for k in RESTAURANT_KEYWORDS):
        return redirect("staff_login")

    hotel = staff.hotel
    today = timezone.now().date()
    month = today.month
    year  = today.year

    hotel_staff = Staff.objects.filter(
        hotel=hotel
    ).select_related("department").order_by("department__name", "name")

    departments = Department.objects.filter(hotel=hotel)

    occupied_bookings = Booking.objects.filter(
        status="checked_in",
        room_unit__isnull=False
    ).select_related("guest", "room_unit", "room")

    occupied_rooms = occupied_bookings.count()

    rooms_qs   = Room.objects.filter(is_active=True).prefetch_related("units")
    room_units = RoomUnit.objects.select_related("room").all()

    room_list = []
    for room in rooms_qs:
        units_qs        = room.units.all().order_by("room_number")
        available_units = units_qs.filter(status="Available").count()
        price = (
            getattr(room, "base_price", None)
            or getattr(room, "price", None)
            or 0
        )
        room_list.append({
            "id":              room.id,
            "room_type":       getattr(room, "room_type", "Unknown"),
            "total_rooms":     units_qs.count(),
            "available_rooms": available_units,
            "price":           float(price) if price else 0,
            "description":     getattr(room, "description", "") or "",
            "units": [
                {"id": u.id, "number": u.room_number, "status": u.status}
                for u in units_qs
            ],
        })

    rooms_json = json.dumps(room_list)

    recent_tasks = Task.objects.select_related(
        "staff", "room_unit", "room"
    ).order_by("-created_at")[:10]

    my_tasks = Task.objects.filter(staff=staff).order_by("-created_at")

    shifts = Shift.objects.filter(
        hotel=hotel
    ).select_related("staff", "department").order_by("date", "shift")

    my_shift_today = Shift.objects.filter(staff=staff, date=today).first()

    attendance_qs = Attendance.objects.filter(
        staff=staff, date__month=month, date__year=year
    )
    present_days   = attendance_qs.filter(status="Present").count()
    late_days      = attendance_qs.filter(status="Late").count()
    absent_days    = attendance_qs.filter(status="Absent").count()
    overtime_hours = attendance_qs.aggregate(
        total=Sum("overtime_hours")
    )["total"] or 0
    attendance_records = attendance_qs.order_by("-date")

    today_attendance = Attendance.objects.filter(
        hotel=hotel, date=today
    ).select_related("staff").order_by("-check_in")

    leave_requests  = LeaveRequest.objects.filter(staff=staff).order_by("-applied_at")
    used_leave_days = leave_requests.filter(status="Approved").count()
    pending_leaves  = leave_requests.filter(status="Pending").count()

    all_leave_requests = LeaveRequest.objects.filter(
        staff__hotel=hotel
    ).select_related("staff").order_by("-applied_at")

    all_orders = RestaurantOrder.objects.select_related("table", "room", "booking__guest")
    today_orders = all_orders.filter(created_at__date=today)
    pending_orders = all_orders.filter(
        status__in=["pending", "preparing"]
    ).prefetch_related("items__item").select_related("table")

    today_revenue = today_orders.filter(
        status="served"
    ).aggregate(total=Sum("total_amount"))["total"] or 0

    total_revenue = all_orders.filter(
        status="served"
    ).aggregate(total=Sum("total_amount"))["total"] or 0

    order_status_counts = all_orders.aggregate(
        pending   = Count("id", filter=Q(status="pending")),
        preparing = Count("id", filter=Q(status="preparing")),
        served    = Count("id", filter=Q(status="served")),
        cancelled = Count("id", filter=Q(status="cancelled")),
    )

    recent_orders = all_orders.order_by("-created_at")[:20]

    tables_qs        = Table.objects.all()
    tables_occupied  = tables_qs.filter(is_occupied=True).count()
    tables_available = tables_qs.count() - tables_occupied

    tables = [
        {
            "id":          t.id,
            "number":      t.number,
            "capacity":    t.capacity,
            "is_occupied": t.is_occupied,
        }
        for t in tables_qs
    ]

    reservations_today = TableReservation.objects.filter(
        reservation_time__date=today
    ).select_related("table").order_by("reservation_time")

    all_reservations = TableReservation.objects.select_related(
        "table"
    ).order_by("-created_at")[:50]

    reservations = [
        {
            "id":               r.id,
            "guest_name":       r.guest_name,
            "phone":            r.phone,
            "table":            r.table.number if r.table else None,
            "table_id":         r.table.id     if r.table else None,
            "guests_count":     r.guests_count,
            "status":           r.status,
            "reservation_time": r.reservation_time.strftime("%Y-%m-%d %H:%M"),
            "created_at":       r.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for r in all_reservations
    ]

    menu_categories      = MenuCategory.objects.prefetch_related("items").all()
    total_menu_items     = MenuItem.objects.count()
    available_menu_items = MenuItem.objects.filter(is_available=True).count()

    hourly_orders = (
        today_orders
        .annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("hour")
    )
    hours_map     = {c["hour"]: {"count": c["count"], "revenue": float(c["revenue"] or 0)} for c in hourly_orders}
    chart_labels  = [f"{h}:00" for h in range(24)]
    chart_counts  = [hours_map.get(h, {}).get("count",   0) for h in range(24)]
    chart_revenue = [hours_map.get(h, {}).get("revenue", 0) for h in range(24)]

    recent_orders_list       = list(all_orders.order_by("-created_at")[:5])
    recent_reservations_list = list(reservations_today[:5])
    recent_tasks_list        = list(recent_tasks[:5])

    combined_activity = sorted(
        recent_orders_list + recent_reservations_list + recent_tasks_list,
        key=lambda x: x.created_at if hasattr(x, "created_at") else x.reservation_time,
        reverse=True,
    )[:15]

    recent_activity_data = []
    for item in combined_activity:
        if isinstance(item, RestaurantOrder):
            recent_activity_data.append({
                "type":   "order",
                "id":     item.id,
                "label":  f"Order #{item.order_number}",
                "status": item.status,
                "amount": float(item.total_amount),
                "time":   item.created_at.strftime("%H:%M"),
            })
        elif isinstance(item, TableReservation):
            recent_activity_data.append({
                "type":   "reservation",
                "id":     item.id,
                "label":  f"Reservation — {item.guest_name}",
                "status": item.status,
                "amount": 0,
                "time":   item.reservation_time.strftime("%H:%M"),
            })
        elif isinstance(item, Task):
            recent_activity_data.append({
                "type":   "task",
                "id":     item.id,
                "label":  item.title,
                "status": item.status,
                "amount": 0,
                "time":   item.created_at.strftime("%H:%M"),
            })

    active_orders_data = [
        {
            "id":           o.id,
            "order_number": o.order_number,
            "status":       o.status,
            "order_type":   o.order_type,
            "table":        o.table.number if o.table else None,
            "room":         o.room.room_type if o.room else None,
            "guest":        o.booking.guest.full_name if o.booking and o.booking.guest else None,
            "total":        float(o.total_amount),
            "tax":          float(o.tax_amount),
            "created_at":   o.created_at.strftime("%H:%M"),
            "items": [
                {
                    "name":       oi.item.name,
                    "qty":        oi.quantity,
                    "unit_price": float(oi.unit_price),
                    "subtotal":   float(oi.subtotal),
                }
                for oi in o.items.all()
            ],
        }
        for o in pending_orders
    ]

    from inventory.models import InventoryItem

    restaurant_stock = InventoryItem.objects.filter(
        Q(department__name__icontains='restaurant') |
        Q(department__name__icontains='kitchen')    |
        Q(department__name__icontains='dining')
    ).select_related(
        "category", "vendor", "department"
    ).order_by(
        "department__name", "name"
    ).distinct()

    low_stock_items = restaurant_stock.filter(
        current_stock__lte=F("minimum_stock")
    )

    restaurant_stock_value = restaurant_stock.aggregate(
        total=Sum(F("current_stock") * F("cost_per_unit"))
    )["total"] or 0

    restaurant_stock_data = [
        {
            "id":            item.id,
            "name":          item.name,
            "category":      item.category.name if item.category else "—",
            "department":    item.department.name if item.department else "—",
            "current_stock": float(item.current_stock),
            "minimum_stock": float(item.minimum_stock),
            "unit":          item.get_unit_display(),
            "is_low_stock":  item.is_low_stock,
            "cost_per_unit": float(item.cost_per_unit),
            "stock_value":   float(item.stock_value),
            "vendor":        item.vendor.name if item.vendor else "—",
        }
        for item in restaurant_stock
    ]

    low_stock_data = [
        {
            "id":            item.id,
            "name":          item.name,
            "category":      item.category.name if item.category else "—",
            "department":    item.department.name if item.department else "—",
            "current_stock": float(item.current_stock),
            "minimum_stock": float(item.minimum_stock),
            "unit":          item.get_unit_display(),
            "vendor":        item.vendor.name if item.vendor else "—",
        }
        for item in low_stock_items
    ]

    from hotel.models import Payroll

    MONTH_NAMES = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]

    payroll = Payroll.objects.filter(
        staff=staff,
        month=month,
        year=year,
    ).prefetch_related("line_items").first()

    payroll_history = Payroll.objects.filter(
        staff=staff
    ).order_by("-year", "-month")

    payroll_history_list = []
    for p in payroll_history:
        earnings = float(
            p.line_items.filter(line_type="earning")
            .aggregate(t=Sum("amount"))["t"] or 0
        )
        deductions = float(
            p.line_items.filter(line_type="deduction")
            .aggregate(t=Sum("amount"))["t"] or 0
        )
        payroll_history_list.append({
            "id":              p.id,
            "month":           p.month,
            "year":            p.year,
            "month_label":     MONTH_NAMES[p.month],
            "basic_salary":    float(p.basic_salary),
            "overtime_amount": float(p.overtime_amount or 0),
            "bonus":           float(p.bonus or 0),
            "incentive":       float(p.incentive or 0),
            "pf_amount":       float(p.pf_amount or 0),
            "esi_amount":      float(p.esi_amount or 0),
            "loan_deduction":  float(p.loan_deduction or 0),
            "tax_deduction":   float(p.tax_deduction or 0),
            "gross_salary":    earnings,
            "deductions":      deductions,
            "net_salary":      float(p.net_salary),
            "paid_status":     p.paid_status,
            "paid_at":         p.paid_at.strftime("%d %b %Y") if p.paid_at else None,
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
            "id":               payroll.id,
            "month_label":      MONTH_NAMES[payroll.month],
            "year":             payroll.year,
            "basic_salary":     float(payroll.basic_salary),
            "overtime_amount":  float(payroll.overtime_amount),
            "bonus":            float(payroll.bonus),
            "incentive":        float(payroll.incentive),
            "pf_amount":        float(payroll.pf_amount),
            "esi_amount":       float(payroll.esi_amount),
            "loan_deduction":   float(payroll.loan_deduction),
            "tax_deduction":    float(payroll.tax_deduction),
            "deductions":       float(payroll.deductions),
            "net_salary":       float(payroll.net_salary),
            "paid_status":      payroll.paid_status,
            "paid_at":          payroll.paid_at.strftime("%d %b %Y, %I:%M %p") if payroll.paid_at else None,
            "earnings_items":   earnings_items,
            "deductions_items": deductions_items,
        }
    else:
        current_payroll = None

    stats = {
        "today_revenue":          float(today_revenue),
        "total_revenue":          float(total_revenue),
        "total_orders":           all_orders.count(),
        "pending_orders":         order_status_counts["pending"] + order_status_counts["preparing"],
        "completed_orders":       order_status_counts["served"],
        "cancelled_orders":       order_status_counts["cancelled"],
        "served_today":           today_orders.filter(status="served").count(),
        "tables_total":           tables_qs.count(),
        "tables_occupied":        tables_occupied,
        "tables_available":       tables_available,
        "reservations_today":     reservations_today.count(),
        "total_menu_items":       total_menu_items,
        "available_menu_items":   available_menu_items,
        "occupied_rooms":         occupied_rooms,
        "total_staff":            hotel_staff.count(),
        "total_departments":      departments.count(),
        "present_days":           present_days,
        "late_days":              late_days,
        "absent_days":            absent_days,
        "overtime_hours":         float(overtime_hours),
        "pending_leaves":         pending_leaves,
        "used_leave_days":        used_leave_days,
        "restaurant_stock_items": restaurant_stock.count(),
        "low_stock_count":        low_stock_items.count(),
        "restaurant_stock_value": float(restaurant_stock_value),
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "stats":            stats,
            "active_orders":    active_orders_data,
            "tables":           tables,
            "reservations":     reservations,
            "recent_activity":  recent_activity_data,
            "restaurant_stock": restaurant_stock_data,
            "low_stock_items":  low_stock_data,
            "chart": {
                "labels":  chart_labels,
                "counts":  chart_counts,
                "revenue": chart_revenue,
            },
        })

    return render(request, "pos.html", {
        "staff":                  staff,
        "hotel":                  hotel,
        "hotel_staff":            hotel_staff,
        "departments":            departments,
        "occupied_bookings":      occupied_bookings,
        "occupied_rooms":         occupied_rooms,
        "rooms":                  room_list,
        "rooms_json":             rooms_json,
        "room_units":             room_units,
        "recent_tasks":           recent_tasks,
        "my_tasks":               my_tasks,
        "shifts":                 shifts,
        "my_shift_today":         my_shift_today,
        "attendance_records":     attendance_records,
        "today_attendance":       today_attendance,
        "present_days":           present_days,
        "late_days":              late_days,
        "absent_days":            absent_days,
        "overtime_hours":         overtime_hours,
        "leave_requests":         leave_requests,
        "all_leave_requests":     all_leave_requests,
        "used_leave_days":        used_leave_days,
        "pending_leaves":         pending_leaves,
        "stats":                  stats,
        "active_orders":          active_orders_data,
        "pending_orders":         pending_orders,
        "recent_orders":          recent_orders,
        "tables":                 tables,
        "tables_qs":              tables_qs,
        "reservations":           reservations,
        "reservations_today":     reservations_today,
        "menu_categories":        menu_categories,
        "recent_activity":        recent_activity_data,
        "chart_labels":           json.dumps(chart_labels),
        "chart_counts":           json.dumps(chart_counts),
        "chart_revenue":          json.dumps(chart_revenue),
        "today":                  today,
        "restaurant_stock":       restaurant_stock,
        "restaurant_stock_data":  json.dumps(restaurant_stock_data),
        "low_stock_items":        low_stock_items,
        "low_stock_data":         json.dumps(low_stock_data),
        "restaurant_stock_value": restaurant_stock_value,
        "current_payroll":        current_payroll,
        "payroll_history":        payroll_history_list,
        "payroll_month_label":    MONTH_NAMES[month],
        "payroll_year":           year,
    })