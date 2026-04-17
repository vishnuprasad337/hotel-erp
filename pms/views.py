from django.shortcuts import render,redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from django.db import transaction
import json
from hotel.models import Task
from .models import Room, RoomUnit, Property, RoomImage,Booking,Guest,Payment
from accounts.models import Staff


# ---------------- ROOM PAGE ----------------
def room_page(request):

    if request.method == "POST":
        room_type = request.POST.get("room_type")
        base_price = request.POST.get("base_price")
        max_adults = request.POST.get("max_adults")
        max_children = request.POST.get("max_children")
        description = request.POST.get("description")
        total_units = int(request.POST.get("total_units", 1))

        amenities_ids = request.POST.getlist("amenities")

        with transaction.atomic():
            room = Room.objects.create(
                room_type=room_type,
                base_price=base_price,
                max_adults=max_adults,
                max_children=max_children,
                description=description,
            )

            if amenities_ids:
                room.amenities.set(amenities_ids)

            # Prefix logic
            prefix_map = {
                "Single": "S",
                "Double": "D",
                "Deluxe": "DL",
                "Suite": "SU"
            }
            prefix = prefix_map.get(room.room_type, "R")

            existing_numbers = set(
                RoomUnit.objects.values_list('room_number', flat=True)
            )

            units = []
            counter = 1

            while len(units) < total_units:
                number = f"{prefix}{counter}"
                if number not in existing_numbers:
                    units.append(RoomUnit(
                        room=room,
                        room_number=number
                    ))
                counter += 1

            RoomUnit.objects.bulk_create(units)

            # Images
            images = request.FILES.getlist("images")
            for i, img in enumerate(images):
                RoomImage.objects.create(
                    room=room,
                    image=img,
                    is_primary=(i == 0)
                )

    rooms = Room.objects.all()

    return render(request, "room.html", {
        "rooms": rooms,
        "amenities": Property.objects.all()
    })


# ---------------- ADD ROOM API ----------------
@csrf_exempt
def add_room(request):
    if request.method == "POST":
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
                files = None
            else:
                data = request.POST
                files = request.FILES

            with transaction.atomic():
                room = Room.objects.create(
                    room_type=data.get('room_type'),
                    base_price=data.get('base_price'),
                    max_adults=data.get('max_adults', 2),
                    max_children=data.get('max_children', 0),
                    description=data.get('description', ''),
                    extra_adult_price=data.get('extra_adult_price', 0),
                    extra_child_price=data.get('extra_child_price', 0),
                )

                amenities = data.get('amenities')
                if amenities:
                    if isinstance(amenities, str):
                        amenities = amenities.split(',')
                    room.amenities.set(amenities)

                total_units = int(data.get('total_units', 1))

                prefix_map = {
                    "Single": "S",
                    "Double": "D",
                    "Deluxe": "DL",
                    "Suite": "SU"
                }

                prefix = prefix_map.get(room.room_type, "R")

                existing_numbers = set(
                    RoomUnit.objects.values_list('room_number', flat=True)
                )

                units = []
                counter = 1

                while len(units) < total_units:
                    number = f"{prefix}{counter}"
                    if number not in existing_numbers:
                        units.append(RoomUnit(
                            room=room,
                            room_number=number
                        ))
                    counter += 1

                RoomUnit.objects.bulk_create(units)

                if files:
                    images = files.getlist("images")
                    for i, img in enumerate(images):
                        RoomImage.objects.create(
                            room=room,
                            image=img,
                            is_primary=(i == 0)
                        )

            return JsonResponse({"success": True, "room_id": room.id})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)


# ---------------- GET SINGLE ROOM ----------------
def get_room(request, room_id):
    try:
        room = Room.objects.filter(id=room_id).first()

        if not room:
            return JsonResponse({"error": "Room not found"}, status=404)

        return JsonResponse({
            "id": room.id,
            "room_type": room.room_type,
            "price": str(room.base_price),
            "max_adults": room.max_adults,
            "max_children": room.max_children,
            "total_units": room.total_units(),
            "available_units": room.available_units(),
            "description": room.description,
            "amenities": [a.name for a in room.amenities.all()],
            "images": [img.image.url for img in room.images.all()]
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# ---------------- GET ROOMS ----------------
def get_rooms(request):
    try:
        rooms = Room.objects.all()

        room_list = []

        for room in rooms:
            units = room.units.all().order_by('room_number')

            units_list = []
            for unit in units:
                color_map = {
                    "Available": "green",
                    "Occupied": "red",
                    "Dirty": "yellow",
                    "Reserved": "blue",
                    "Cleaning": "orange",
                    "Maintenance": "gray",
                }

                units_list.append({
                    "id": unit.id,
                    "number": unit.room_number,
                    "status": unit.status,
                    "color": color_map.get(unit.status, "gray")
                })

            room_list.append({
                "id": room.id,
                "room_type": room.room_type,
                "price": str(room.base_price),
                "total_units": room.total_units(),
                "available_units": room.available_units(),
                "max_adults": room.max_adults,
                "max_children": room.max_children,
                "amenities": [a.name for a in room.amenities.all()],
                "description": room.description,
                "images": [img.image.url for img in room.images.all()],
                "units": units_list
            })

        return JsonResponse({
            "success": True,
            "rooms": room_list
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

def frontoffice_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    staff = Staff.objects.select_related("department").get(id=staff_id)

    # ❌ REMOVE hotel reference
    # hotel = staff.hotel

    rooms = Room.objects.all()
    room_list = []

    for room in rooms:
        total_units = room.units.count()
        available_units = room.units.filter(status="Available").count()

        room_list.append({
            "room_type": room.room_type,
            "total_rooms": total_units,
            "available_rooms": available_units,
            "price": room.price,
            "id": room.id,
            "description": room.description or ""
        })

    housekeeping_staff = Staff.objects.filter(
        department__name__icontains="housekeeping",
        is_available=True,
    ).select_related("department")

    today = timezone.now().date()

    total_bookings = Booking.objects.count()

    arrivals = Booking.objects.filter(
        check_in=today,
        status="confirmed"
    ).select_related('guest', 'room', 'room_unit')

    departures = Booking.objects.filter(
        check_out=today,
        status="checked_in"
    ).select_related('guest', 'room', 'room_unit')

    occupied_rooms = Booking.objects.filter(
        status="checked_in"
    ).count()

    bookings = Booking.objects.all().select_related(
        'guest', 'room', 'room_unit'
    ).order_by('-created_at')

    recent_bookings = bookings[:5]

    recent_tasks = Task.objects.select_related(
        'staff', 'room_unit', 'room'
    ).order_by("-created_at")[:5]

    recent_activity = sorted(
        list(recent_bookings) + list(recent_tasks),
        key=lambda x: x.created_at,
        reverse=True
    )[:10]

    room_units = RoomUnit.objects.select_related('room').all()

    return render(request, "frontoffice.html", {
        "rooms": room_list,
        "staff": staff,
        "housekeeping_staff": housekeeping_staff,
        "total_bookings": total_bookings,
        "occupied_rooms": occupied_rooms,
        "arrivals_count": arrivals.count(),
        "departures_count": departures.count(),
        "arrivals": arrivals,
        "departures": departures,
        "bookings": bookings,
        "recent_activity": recent_activity,
        "recent_tasks": recent_tasks,
        "room_units": room_units,
    })
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import BookingSerializer

# views.py - Complete working create_booking function

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json
from datetime import datetime

@csrf_exempt
@require_http_methods(["POST"])
def create_booking(request):
    try:
        # Parse JSON data
        data = json.loads(request.body)
        
        print("Received data:", data)  # Debug log
        
        # Get required fields
        guest_id = data.get("guest")
        room_id = data.get("room")
        room_unit_id = data.get("room_unit")
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        adults = data.get("adults", 1)
        children = data.get("children", 0)
        source = data.get("source", "walk-in")
        special_requests = data.get("special_requests", "")
        
        # Validate required fields
        if not guest_id:
            return JsonResponse({"error": "Guest ID is required"}, status=400)
        if not room_id:
            return JsonResponse({"error": "Room ID is required"}, status=400)
        if not room_unit_id:
            return JsonResponse({"error": "Room unit ID is required"}, status=400)
        if not check_in:
            return JsonResponse({"error": "Check-in date is required"}, status=400)
        if not check_out:
            return JsonResponse({"error": "Check-out date is required"}, status=400)
        
        # Get objects
        try:
            guest = Guest.objects.get(id=guest_id)
        except Guest.DoesNotExist:
            return JsonResponse({"error": f"Guest with ID {guest_id} not found"}, status=404)
        
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return JsonResponse({"error": f"Room with ID {room_id} not found"}, status=404)
        
        try:
            room_unit = RoomUnit.objects.get(id=room_unit_id)
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": f"Room unit with ID {room_unit_id} not found"}, status=404)
        
        # Check if room unit is available
        if room_unit.status != "Available":
            return JsonResponse({"error": f"Room unit {room_unit.room_number} is not available. Current status: {room_unit.status}"}, status=400)
        
        # Calculate nights
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d')
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d')
        nights = (check_out_date - check_in_date).days
        if nights <= 0:
            nights = 1
        
        # Create booking
        booking = Booking.objects.create(
            guest=guest,
            room=room,
            room_unit=room_unit,
            check_in=check_in,
            check_out=check_out,
            guests_count=adults + children,
            special_requests=special_requests,
            status="confirmed"
        )
        
        # Calculate payment
        room_charges = float(room.base_price) * nights
        tax = room_charges * 0.18  # 18% tax
        total_amount = room_charges + tax
        
        # Create payment record
        Payment.objects.create(
            booking=booking,
            room_charges=room_charges,
            tax=tax,
            total_amount=total_amount,
            payment_status="pending"
        )
        
       
        room_unit.status = "Reserved"
        room_unit.save()
        
        return JsonResponse({
            "success": True,
            "booking_id": booking.id,
            "room_number": room_unit.room_number,
            "message": "Booking created successfully"
        })
        
    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"Invalid JSON: {str(e)}"}, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
from django.utils import timezone
@csrf_exempt
def check_in(request):
    if request.method == "POST":
        data = json.loads(request.body)

        booking = Booking.objects.get(id=data["booking_id"], status="confirmed")

        guest = booking.guest
        guest.id_type = data["id_type"]
        guest.id_number = data["id_number"]
        guest.save()

        booking.status = "checked_in"
        booking.actual_check_in = timezone.now()
        booking.save()

        unit = booking.room_unit
        unit.status = "Occupied"
        unit.save()

        room = booking.room
        room.available_rooms -= 1
        room.save()

        return JsonResponse({"success": True})
@csrf_exempt
def check_out(request):
    if request.method == "POST":
        data = json.loads(request.body)

        staff = Staff.objects.get(id=request.session.get("staff_id"))

        booking = Booking.objects.get(id=data["booking_id"], status="checked_in")

        booking.status = "checked_out"
        booking.actual_check_out = timezone.now()
        booking.save()

        unit = booking.room_unit
        unit.status = "Dirty"
        unit.save()

        # safer payment handling
        payment = Payment.objects.filter(booking=booking).first()

        if payment:
            payment.payment_method = data.get("method")
            payment.payment_status = "paid"
            payment.paid_at = timezone.now()
            payment.collected_by = staff
            payment.save()

        return JsonResponse({"success": True})

@csrf_exempt
def get_bill(request):
    booking_id = request.GET.get("booking_id")

    try:
        booking = Booking.objects.get(id=booking_id)

        payment = Payment.objects.filter(booking=booking).first()

        nights = (booking.check_out - booking.check_in).days or 1

        return JsonResponse({
            "room_type": booking.room.room_type,
            "room_number": booking.room_unit.room_number if booking.room_unit else None,
            "check_in": str(booking.check_in),
            "check_out": str(booking.check_out),
            "nights": nights,
            "room_charges": float(payment.amount if payment else 0),
            "tax": 0,
            "total_amount": float(payment.amount if payment else 0),
        })

    except Booking.DoesNotExist:
        return JsonResponse({"error": "Booking not found"}, status=404)

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
@csrf_exempt
def assign_housekeeping_task(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)

            staff_id = data.get("staff_id")
            room_unit_id = data.get("room_unit_id")
            task_type = data.get("task_type", "General Task")
            priority = data.get("priority", "Normal")
            duration = data.get("duration", "1 hour")
            notes = data.get("notes", "")

            if not staff_id:
                return JsonResponse({"error": "Staff ID is required"}, status=400)

            try:
                staff = Staff.objects.get(id=staff_id)
            except Staff.DoesNotExist:
                return JsonResponse({"error": "Staff not found"}, status=404)

            room_unit = None
            room = None
            
            if room_unit_id:
                try:
                    room_unit = RoomUnit.objects.get(id=room_unit_id)
                    room = room_unit.room  # Get the room from room_unit
                except RoomUnit.DoesNotExist:
                    pass  # Room unit optional

           
            task = Task.objects.create(
                staff=staff,
                room=room,
                room_unit=room_unit,  # Now this field exists
                title=task_type,
                description=f"Priority: {priority} | Duration: {duration} | Notes: {notes}".strip(" | "),
                status="Pending"
            )

            return JsonResponse({
                "success": True,
                "task_id": task.id,
                "message": f"Task '{task_type}' assigned to {staff.name}"
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)
def get_guests(request):
    guests = Guest.objects.all().order_by("-created_at")

    data = [
        {
            "id": g.id,
            "full_name": g.full_name,
            "phone": g.phone,
            "email": g.email or "",
            "nationality": g.nationality or "",
            "id_type": g.id_type or "",
            "id_number": g.id_number or "",
            "booking_count": g.booking_set.count(),
            "created_at": str(g.created_at) if hasattr(g, 'created_at') else ""
        }
        for g in guests
    ]

    return JsonResponse(data, safe=False)


def get_bookings(request):
    bookings = Booking.objects.select_related(
        "guest", "room", "room_unit"
    ).order_by("-created_at")

    data = [
        {
            "id": b.id,
            "booking_code": f"BK{b.id:06d}",
            "guest": b.guest.full_name if b.guest else "N/A",
            "phone": b.guest.phone if b.guest else "",
            "room_type": b.room.room_type if b.room else "N/A",
            "room_no": b.room_unit.room_number if b.room_unit else "N/A",
            "check_in": str(b.check_in),
            "check_out": str(b.check_out),
            "status": b.status,
            "total": float(b.payment.total_amount) if hasattr(b, 'payment') and b.payment else 0,
        }
        for b in bookings
    ]

    return JsonResponse(data, safe=False)


@csrf_exempt
def add_guest(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    data = request.POST
    
    full_name = data.get("full_name")
    if not full_name:
        return JsonResponse({"error": "Full name is required"}, status=400)
    
    guest = Guest.objects.create(
        full_name=full_name,
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        nationality=data.get("nationality", ""),
        id_type=data.get("id_type", ""),
        id_number=data.get("id_number", ""),
        id_photo=request.FILES.get("id_photo")
    )

    return JsonResponse({
        "success": True,
        "guest_id": guest.id,
        "message": "Guest added successfully"
    })