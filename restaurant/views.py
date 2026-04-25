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

        staff_name = o.served_by.name if o.served_by else "Admin"

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
    })
@login_required
@csrf_exempt
@transaction.atomic
def create_order(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        staff = getattr(request.user, 'staff_profile', None)
        data = json.loads(request.body)

        order_type = data.get('order_type', 'dine_in')
        table_id = data.get('table_id')
        room_id = data.get('room_id')
        reservation_id = data.get('reservation_id')
        charge_to_room = data.get('charge_to_room', False)
        items = data.get('items', [])

        if not items:
            return JsonResponse({'error': 'No items selected'}, status=400)

        room_obj = None
        unit = None
        booking = None
        reservation = None

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
                booking = Booking.objects.filter(
                    room_unit=unit,
                    status='checked_in'
                ).select_related('guest').first()
            else:
                booking = Booking.objects.filter(
                    room=room_obj,
                    status='checked_in'
                ).select_related('guest').first()

            if not booking:
                return JsonResponse({'error': 'No active booking for this room'}, status=400)

        if order_type == 'dine_in':
            if reservation_id:
                from .models import TableReservation
                reservation = TableReservation.objects.filter(id=reservation_id).first()

                if not reservation:
                    return JsonResponse({'error': 'Invalid reservation'}, status=400)

                table_id = reservation.table_id

        order = RestaurantOrder.objects.create(
            order_type=order_type,
            table_id=table_id if table_id else None,
            room=room_obj,
            booking=booking,
            reservation=reservation,
            charge_to_room=charge_to_room,
            served_by=staff,
        )

        total = Decimal('0')
        tax_total = Decimal('0')

        for i in items:
            menu_item = get_object_or_404(MenuItem, pk=i['id'])
            qty = int(i['qty'])

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

        if order_type == 'dine_in' and table_id:
            Table.objects.filter(pk=table_id).update(is_occupied=True)

        if order_type == 'room_service' and charge_to_room and booking:
            try:
                from billing.models import GuestFolio, FolioCharge

                folio, _ = GuestFolio.objects.get_or_create(booking=booking)

                if folio.status == "open":
                    FolioCharge.objects.create(
                        folio=folio,
                        charge_type='restaurant',
                        description=f'Restaurant Order #{order.order_number}',
                        amount=total,
                        tax_amount=tax_total,
                        added_by=staff
                    )

            except Exception as e:
                return JsonResponse({
                    'success': True,
                    'order_id': order.id,
                    'order_number': order.order_number,
                    'warning': f'Billing failed: {str(e)}',
                })

        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'order_number': order.order_number,
            'booking_id': booking.id if booking else None,
            'reservation_id': reservation.id if reservation else None,
            'total': float(total),
            'tax': float(tax_total),
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
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
@require_GET
def list_reservations(request):

    reservations = TableReservation.objects.select_related('table').all().order_by('-created_at')

    data = []

    for r in reservations:
        data.append({
            "id": r.id,
            "guest_name": r.guest_name,
            "phone": r.phone,
            "table": r.table.number if r.table else None,
            "reservation_time": r.reservation_time,
            "guests_count": r.guests_count,
            "status": r.status,
            "created_at": r.created_at,
        })

    return JsonResponse({"reservations": data})
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