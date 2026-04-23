from django.shortcuts import render,redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import uuid
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
from django.utils import timezone  
def frontoffice_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    hotel = staff.hotel

    # ── Rooms (no hotel field, load all active) ──
    rooms = Room.objects.filter(is_active=True)
    room_list = []

    for room in rooms:
        units_qs = room.units.all().order_by("room_number")
        total_units = units_qs.count()
        available_units = units_qs.filter(status="Available").count()

        units_list = [
            {
                "id": unit.id,
                "number": unit.room_number,
                "status": unit.status,
            }
            for unit in units_qs
        ]

        price = (
            getattr(room, "base_price", None)
            or getattr(room, "price", None)
            or getattr(room, "rate", None)
            or 0
        )

        room_list.append({
            "id": room.id,
            "room_type": getattr(room, "room_type", "Unknown"),
            "total_rooms": total_units,
            "available_rooms": available_units,
            "price": price,
            "description": getattr(room, "description", "") or "",
            "units": units_list,
        })

    rooms_json = json.dumps([
        {**r, "price": float(r["price"]) if r["price"] else 0}
        for r in room_list
    ])

    # ── Staff filtered by hotel + sorted by department then name ──
    hotel_staff = Staff.objects.filter(
        hotel=hotel
    ).select_related("department").order_by("department__name", "name")

    housekeeping_staff = hotel_staff.filter(
        department__name__icontains="housekeeping",
        is_available=True,
    )

    today = timezone.now().date()

    # ── Bookings ──
    base_bookings = Booking.objects.select_related("guest", "room", "room_unit")

    total_bookings = base_bookings.count()
    arrivals = base_bookings.filter(check_in=today, status="confirmed")
    departures = base_bookings.filter(check_out=today, status="checked_in")
    occupied_rooms = base_bookings.filter(status="checked_in").count()
    bookings = base_bookings.order_by("-created_at")
    recent_bookings = bookings[:5]

    # ── Tasks ──
    recent_tasks = Task.objects.select_related(
        "staff", "room_unit", "room"
    ).order_by("-created_at")[:5]

    recent_activity = sorted(
        list(recent_bookings) + list(recent_tasks),
        key=lambda x: x.created_at,
        reverse=True,
    )[:10]

   
    room_units = RoomUnit.objects.select_related("room").all()

   
    present_days = 0
    late_days = 0
    absent_days = 0
    overtime_hours = "0.0"
    attendance_records = []
    leave_requests = []
    used_leave_days = 0
    pending_leaves = 0

    return render(request, "frontoffice.html", {
        "hotel": hotel,
        "hotel_staff": hotel_staff,
        "rooms": room_list,
        "rooms_json": rooms_json,
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
        "present_days": present_days,
        "late_days": late_days,
        "absent_days": absent_days,
        "overtime_hours": overtime_hours,
        "attendance_records": attendance_records,
        "leave_requests": leave_requests,
        "used_leave_days": used_leave_days,
        "pending_leaves": pending_leaves,
    })
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .serializers import BookingSerializer
from django.db.models import Count



from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json
from datetime import datetime
@csrf_exempt
@require_http_methods(["POST"])
def create_booking(request):
    try:
        data = json.loads(request.body)

        def clean(val):
            return val.strip() if isinstance(val, str) else None

        
        room_id = data.get("room")
        room_unit_id = data.get("room_unit")
        check_in = data.get("check_in")
        check_out = data.get("check_out")
        adults = int(data.get("adults", 1))
        children = int(data.get("children", 0))
        source = clean(data.get("source")) or "walk-in"
        special_requests = clean(data.get("special_requests"))

        
        full_name = clean(data.get("full_name")) or ""
        phone = clean(data.get("phone")) or ""
        email = clean(data.get("email"))
        nationality = clean(data.get("nationality"))
        id_type = clean(data.get("id_type"))
        id_number = clean(data.get("id_number"))

        
        errors = {}
        if not room_id:
            errors["room"] = "Room ID is required"
        if not room_unit_id:
            errors["room_unit"] = "Room unit ID is required"
        if not check_in:
            errors["check_in"] = "Check-in date is required"
        if not check_out:
            errors["check_out"] = "Check-out date is required"
        if not full_name:
            errors["full_name"] = "Guest full name is required"
        if not phone:
            errors["phone"] = "Guest phone number is required"

        if errors:
            return JsonResponse({"errors": errors}, status=400)

        
        try:
            check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
            check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        if check_out_date <= check_in_date:
            return JsonResponse({"error": "Check-out must be after check-in"}, status=400)

        nights = (check_out_date - check_in_date).days

        
        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return JsonResponse({"error": f"Room with ID {room_id} not found"}, status=404)

        try:
            room_unit = RoomUnit.objects.get(id=room_unit_id)
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": f"Room unit with ID {room_unit_id} not found"}, status=404)

        if room_unit.status != "Available":
            return JsonResponse({
                "error": f"Room unit {room_unit.room_number} is not available. Current status: {room_unit.status}"
            }, status=400)

        
        guest, created = Guest.objects.get_or_create(
            phone=phone,
            defaults={
                "full_name": full_name,
                "email": email,
                "nationality": nationality,
                "id_type": id_type,
                "id_number": id_number,
            }
        )

        if not created:
            updated = False
            if full_name and guest.full_name != full_name:
                guest.full_name = full_name
                updated = True
            if email is not None and guest.email != email:
                guest.email = email
                updated = True
            if nationality is not None and guest.nationality != nationality:
                guest.nationality = nationality
                updated = True
            if id_type is not None and guest.id_type != id_type:
                guest.id_type = id_type
                updated = True
            if id_number is not None and guest.id_number != id_number:
                guest.id_number = id_number
                updated = True
            if updated:
                guest.save()

        
        room_charges = float(room.base_price) * nights
        tax = room_charges * 0.18
        total_amount = room_charges + tax

        
        booking = Booking.objects.create(
            guest=guest,
            room=room,
            room_unit=room_unit,
            check_in=check_in_date,
            check_out=check_out_date,
            adults=adults,
            children=children,
            guests_count=adults + children,
            special_requests=special_requests,
            source=source,
            base_price=room.base_price,
            tax=round(tax, 2),
            total_amount=round(total_amount, 2),
            status="confirmed",
        )

        
        Payment.objects.create(
            booking=booking,
            room_charges=round(room_charges, 2),
            tax=round(tax, 2),
            total_amount=round(total_amount, 2),
            payment_status="pending",
        )

        
        room_unit.status = "Reserved"
        room_unit.save()

        return JsonResponse({
            "success": True,
            "booking_id": booking.id,
            "booking_code": f"BK{booking.id:06d}",
            "guest_id": guest.id,
            "guest_created": created,
            "room_number": room_unit.room_number,
            "nights": nights,
            "total_amount": round(total_amount, 2),
            "message": "Booking created successfully",
        }, status=201)

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

        if not guest:
            guest = Guest.objects.create(
                full_name=data.get("full_name", "Walk-in Guest"),
                phone=data.get("phone", "")
            )
            booking.guest = guest

        guest.id_type = data.get("id_type")
        guest.id_number = data.get("id_number")
        guest.nationality = data.get("nationality")
        guest.save()

        booking.status = "checked_in"
        booking.actual_check_in = timezone.now()
        booking.save()


        unit = booking.room_unit
        if unit:
            unit.status = "Occupied"
            unit.save()
        send_guest_portal_email(request, booking)

        return JsonResponse({"success": True})
@csrf_exempt
def check_out(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        data = json.loads(request.body)
    except:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    booking = Booking.objects.filter(
        id=data.get("booking_id"),
        status="checked_in"
    ).first()

    if not booking:
        return JsonResponse({"error": "Booking not found or not checked-in"}, status=404)

    booking.status = "checked_out"
    booking.actual_check_out = timezone.now()
    booking.save()

    if booking.room_unit:
        booking.room_unit.status = "Dirty"
        booking.room_unit.save()

    payment = Payment.objects.filter(booking=booking).first()

    if payment:
        payment.payment_method = data.get("method", payment.payment_method)
        payment.payment_status = "paid"
        payment.paid_at = timezone.now()
        payment.save()

    return JsonResponse({
        "success": True,
        "message": "Check-out completed successfully"
    })
from datetime import date as date_type

def get_bill(request):
    booking_id = request.GET.get("booking_id")

    if not booking_id:
        return JsonResponse({"error": "booking_id required"}, status=400)

    booking = Booking.objects.select_related(
        "guest", "room", "room_unit", "payment"
    ).filter(id=booking_id).first()

    if not booking:
        return JsonResponse({"error": "Booking not found"}, status=404)

    try:
        payment = booking.payment
        room_charges = float(payment.room_charges)
        tax = float(payment.tax)
        total_amount = float(payment.total_amount)
        payment_status = payment.payment_status
    except Exception:
        nights = (booking.check_out - booking.check_in).days if booking.check_in and booking.check_out else 1
        room_charges = float(booking.base_price or 0) * nights
        tax = round(room_charges * 0.18, 2)
        total_amount = round(room_charges + tax, 2)
        payment_status = "pending"

    nights = (booking.check_out - booking.check_in).days if booking.check_in and booking.check_out else 1

    return JsonResponse({
        "booking_id": booking.id,
        "booking_code": booking.booking_code or f"BK{booking.id:06d}",
        "guest": booking.guest.full_name if booking.guest else "N/A",
        "room_type": booking.room.room_type if booking.room else "N/A",
        "room_number": booking.room_unit.room_number if booking.room_unit else "N/A",
        "check_in": booking.check_in.isoformat() if booking.check_in else None,
        "check_out": booking.check_out.isoformat() if booking.check_out else None,
        "nights": nights,
        "room_charges": room_charges,
        "tax": tax,
        "total_amount": total_amount,
        "payment_status": payment_status,
        "status": booking.status,
    })

@csrf_exempt
def assign_housekeeping_task(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            staff_id = data.get("staff_id")
            room_unit_id = data.get("room_unit_id")
            
            
            print(f"Assigning Staff: {staff_id} to Room Unit: {room_unit_id}")

            staff = Staff.objects.get(id=staff_id)
            room_unit = RoomUnit.objects.get(id=room_unit_id) 
            
            
            task = Task.objects.create(
                staff=staff,
                room=room_unit.room, 
                room_unit=room_unit, 
                title=data.get("task_type", "Cleaning"),
                description=data.get("notes", ""),
                status="Pending"
            )

            
            room_unit.status = "Cleaning"
            room_unit.save()

            return JsonResponse({"success": True, "task_id": task.id})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
def get_guests(request):
    guests = Guest.objects.annotate(
        booking_count=Count("booking")
    ).order_by("-created_at")

    data = [
        {
            "id": g.id,
            "full_name": g.full_name,
            "phone": g.phone,
            "email": g.email or "",
            "nationality": g.nationality or "",
            "id_type": g.id_type or "",
            "id_number": g.id_number or "",
            "booking_count": g.booking_count,        
        }
        for g in guests
    ]

    return JsonResponse(data, safe=False)

def get_bookings(request):
    bookings = Booking.objects.select_related(
        "guest", "room", "room_unit", "payment"  
    ).order_by("-created_at")

    data = []
    for b in bookings:
        try:
            total = float(b.payment.total_amount)
            payment_status = b.payment.payment_status
        except Payment.DoesNotExist:
            total = 0.0
            payment_status = "no_payment"

        data.append({
            "id": b.id,
            "booking_code": b.booking_code or f"BK{b.id:06d}",
            "guest": b.guest.full_name if b.guest else "N/A",
            "guest_id": b.guest.id if b.guest else None,
            "phone": b.guest.phone if b.guest else "",
            "room_type": b.room.room_type if b.room else "N/A",
            "room_no": b.room_unit.room_number if b.room_unit else "N/A",
            "check_in": b.check_in.isoformat(),
            "check_out": b.check_out.isoformat(),
            "adults": b.adults,
            "children": b.children,
            "status": b.status,
            "source": b.source or "",
            "total": total,
            "payment_status": payment_status,
            "created_at": b.created_at.isoformat(),
        })

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
from django.db import connection
from django_tenants.utils import schema_context
def send_guest_portal_email(request, booking):
    from django.core.mail import send_mail
    from django.conf import settings
 
    guest = booking.guest
    if not guest or not guest.email:
        return
 
    if not booking.guest_token:
        booking.guest_token = str(uuid.uuid4())
        booking.save()
 
    schema = connection.schema_name
    link = f"http://localhost:8000/guest-portal/{schema}/{booking.guest_token}/"
 
    send_mail(
        subject="Welcome to Our Hotel",
        message=f"Hi {guest.full_name},\n\nYour check-in is successful.\n\nAccess your guest portal:\n{link}\n\nThank you!",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[guest.email],
        fail_silently=False,
    )
 
 
def guest_portal(request, schema, token):
    with schema_context(schema):
        booking = Booking.objects.select_related(
            "guest", "room", "room_unit"
        ).filter(guest_token=token).first()
 
        if not booking:
            return JsonResponse({"error": "Invalid link"}, status=404)
 
        return render(request, "guest_portal.html", {
            "booking": booking,
            "guest":   booking.guest,
            "room":    booking.room_unit,
            "token":   token,
        })
 