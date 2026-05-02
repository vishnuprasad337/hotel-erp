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
from django.http import JsonResponse
from django.utils import timezone

def get_rooms(request):
    try:
        today = timezone.now().date()
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

                active_booking = Booking.objects.filter(
                    room_unit=unit,
                    status="checked_in"
                ).select_related("guest").order_by("-actual_check_in").first()

                if not active_booking:
                    active_booking = Booking.objects.filter(
                        room_unit=unit,
                        status="confirmed",
                        check_in__lte=today,
                        check_out__gt=today,
                    ).select_related("guest").order_by("-check_in").first()

                upcoming_booking = Booking.objects.filter(
                    room_unit=unit,
                    status="confirmed",
                    check_in__gt=today,
                ).select_related("guest").order_by("check_in").first()

                if active_booking and upcoming_booking and active_booking.id == upcoming_booking.id:
                    upcoming_booking = None

                units_list.append({
                    "id": unit.id,
                    "number": unit.room_number,
                    "status": unit.status,
                    "color": color_map.get(unit.status, "gray"),
                    "current_guest": {
                        "booking_id": active_booking.id,
                        "guest_name": active_booking.guest.full_name if active_booking.guest else "N/A",
                        "phone": active_booking.guest.phone if active_booking.guest else "",
                        "check_in": active_booking.check_in.isoformat(),
                        "check_out": active_booking.check_out.isoformat(),
                        "status": active_booking.status,
                    } if active_booking else None,
                    "upcoming_guest": {
                        "booking_id": upcoming_booking.id,
                        "guest_name": upcoming_booking.guest.full_name if upcoming_booking.guest else "N/A",
                        "phone": upcoming_booking.guest.phone if upcoming_booking.guest else "",
                        "check_in": upcoming_booking.check_in.isoformat(),
                        "check_out": upcoming_booking.check_out.isoformat(),
                    } if upcoming_booking else None,
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

        return JsonResponse({"success": True, "rooms": room_list})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
from django.utils import timezone  
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q
from datetime import datetime
from hotel.models import Attendance,LeaveRequest



@never_cache
@login_required
def frontoffice_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    hotel = staff.hotel

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

    hotel_staff = Staff.objects.filter(
        hotel=hotel
    ).select_related("department").order_by("department__name", "name")

    housekeeping_staff = hotel_staff.filter(
        department__name__icontains="housekeeping",
        is_available=True,
    )

    today = timezone.now().date()

    base_bookings = Booking.objects.select_related("guest", "room", "room_unit")

    total_bookings = base_bookings.count()
    arrivals = base_bookings.filter(check_in=today, status="confirmed")
    departures = base_bookings.filter(check_out=today, status="checked_in")
    occupied_rooms = base_bookings.filter(status="checked_in").count()
    bookings = base_bookings.order_by("-created_at")
    recent_bookings = bookings[:5]

    recent_tasks = Task.objects.select_related(
        "staff", "room_unit", "room"
    ).order_by("-created_at")[:5]

    recent_activity = sorted(
        list(recent_bookings) + list(recent_tasks),
        key=lambda x: x.created_at,
        reverse=True,
    )[:10]

    room_units = RoomUnit.objects.select_related("room").all()

    month = today.month
    year = today.year

    attendance_qs = Attendance.objects.filter(
        staff=staff,
        date__month=month,
        date__year=year
    )

    present_days = attendance_qs.filter(status="Present").count()
    late_days = attendance_qs.filter(status="Late").count()
    absent_days = attendance_qs.filter(status="Absent").count()

    overtime_hours = attendance_qs.aggregate(
        total=Sum("overtime_hours")
    )["total"] or 0

    attendance_records = attendance_qs.order_by("-date")

    leave_requests = LeaveRequest.objects.filter(staff=staff).order_by("-applied_at")
    used_leave_days = leave_requests.filter(status="Approved").count()
    pending_leaves = leave_requests.filter(status="Pending").count()

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
from django.db.models import Count



from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
import json
from datetime import datetime
from billing.models import GuestFolio,FolioCharge
from datetime import date
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

        if check_in_date < date.today():
            return JsonResponse({"error": "Check-in cannot be in the past."}, status=400)

        if check_out_date <= check_in_date:
            return JsonResponse({"error": "Check-out must be after check-in."}, status=400)

        try:
            room = Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return JsonResponse({"error": f"Room with ID {room_id} not found"}, status=404)

        try:
            room_unit = RoomUnit.objects.get(id=room_unit_id)
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": f"Room unit with ID {room_unit_id} not found"}, status=404)

        if room_unit.status in ["Maintenance", "Cleaning", "Dirty"]:
            return JsonResponse({
                "error": f"Room {room_unit.room_number} is currently {room_unit.status} and cannot be booked."
            }, status=400)

        date_conflict = Booking.objects.filter(
            room_unit=room_unit,
            status__in=["confirmed", "checked_in"],
            check_in__lt=check_out_date,
            check_out__gt=check_in_date,
        ).exists()

        if date_conflict:
            return JsonResponse({
                "error": f"Room {room_unit.room_number} is already booked for the selected dates."
            }, status=400)

        nights = (check_out_date - check_in_date).days

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

        folio = GuestFolio.objects.create(booking=booking)

        FolioCharge.objects.create(
            folio=folio,
            charge_type="room",
            description=f"{room.room_type} Room Charge ({nights} night(s))",
            amount=round(room_charges, 2),
            tax_amount=round(tax, 2),
            date=check_in_date,
        )

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

from pms.models import Booking, GuestIDPhoto


@csrf_exempt
def check_in(request):
    if request.method != "POST":
        return JsonResponse({
            "success": False,
            "message": "Invalid method"
        }, status=405)

    booking_id = request.POST.get("booking_id")

    if not booking_id:
        return JsonResponse({
            "success": False,
            "message": "Booking ID is required"
        }, status=400)

    try:
        booking = Booking.objects.select_related("guest", "room_unit").get(
            id=booking_id,
            status="confirmed"
        )
    except Booking.DoesNotExist:
        return JsonResponse({
            "success": False,
            "message": "Booking not found or not confirmed"
        }, status=404)

    guest = booking.guest
    if not guest:
        return JsonResponse({
            "success": False,
            "message": "Guest data missing in booking"
        }, status=400)

    
    id_photos = request.FILES.getlist("id_photos")

    if not id_photos:
        return JsonResponse({
            "success": False,
            "message": "At least one ID photo is required"
        }, status=400)

   
    if booking.status == "checked_in":
        return JsonResponse({
            "success": False,
            "message": "Guest already checked in"
        }, status=400)

    try:
        with transaction.atomic():

            
            for photo in id_photos:
                if not photo.content_type.startswith("image/"):
                    return JsonResponse({
                        "success": False,
                        "message": "Only image files are allowed"
                    }, status=400)

                GuestIDPhoto.objects.create(
                    guest=guest,
                    image=photo
                )

           
            booking.status = "checked_in"
            booking.actual_check_in = timezone.now()
            booking.save()

           
            if booking.room_unit:
                booking.room_unit.status = "Occupied"
                booking.room_unit.save()

            send_guest_portal_email(request, booking)

    except Exception as e:
        return JsonResponse({
            "success": False,
            "message": f"Check-in failed: {str(e)}"
        }, status=500)

    return JsonResponse({
        "success": True,
        "message": "Check-in successful"
    })
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

    payment = Payment.objects.filter(booking=booking).first()

    if not payment:
        return JsonResponse({"error": "No payment record found for this booking."}, status=400)

    if payment.payment_status != "paid":
        return JsonResponse({
            "error": "Payment is pending. Please collect payment before checking out.",
            "payment_status": payment.payment_status,
            "total_amount": float(payment.total_amount),
        }, status=400)

    booking.status = "checked_out"
    booking.actual_check_out = timezone.now()
    booking.save()

    if booking.room_unit:
        booking.room_unit.status = "Dirty"
        booking.room_unit.save()

    payment.payment_method = data.get("method", payment.payment_method)
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
        "guest", "room", "room_unit", "folio"
    ).filter(id=booking_id).first()

    if not booking:
        return JsonResponse({"error": "Booking not found"}, status=404)

    folio = getattr(booking, "folio", None)

    if not folio:
        return JsonResponse({"error": "Folio not created yet"}, status=404)

    charges = folio.charges.all()

    charge_list = []
    for c in charges:
        charge_list.append({
            "charge_type": c.charge_type,
            "type": c.charge_type,
            "description": c.description,
            "amount": float(c.amount),
            "tax": float(c.tax_amount),
            "total": float(c.total),
        })

    payments = folio.payments.all()


    payment_list = [
        {
            "amount": float(p.amount),
            "method": p.method,
        }
        for p in payments
    ]

    return JsonResponse({
        "booking_id": booking.id,
        "guest": booking.guest.full_name if booking.guest else "N/A",
        "room": booking.room_unit.room_number if booking.room_unit else "N/A",

        "charges": charge_list,
        "payments": payment_list,

        "subtotal": float(folio.total_charges),
        "paid": float(folio.total_paid),
        "balance": float(folio.balance_due),
        "status": folio.status,
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
    link = f"http://{schema}.localhost:8000/guest-portal/{schema}/{booking.guest_token}/"
    send_mail(
        subject="Welcome to Our Hotel",
        message=f"Hi {guest.full_name},\n\nYour check-in is successful.\n\nAccess your guest portal:\n{link}\n\nThank you!",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[guest.email],
        fail_silently=False,
    )
from restaurant.models import MenuCategory,RestaurantOrder,MenuItem,OrderItem
from decimal import Decimal
from inventory.models import LaundryService, LaundryOrder,LaundryOrderItem

def guest_portal(request, schema, token):
    with schema_context(schema):
        booking = Booking.objects.select_related(
            "guest", "room", "room_unit"
        ).filter(guest_token=token).first()

        if not booking:
            return JsonResponse({"error": "Invalid link"}, status=404)

        
        categories = MenuCategory.objects.prefetch_related("items").all()
        menu_data = []
        for cat in categories:
            items = [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": float(item.price),
                    "tax_percent": float(item.tax_percent),
                    "veg": item.is_veg,
                    "available": item.is_available,
                    "image": item.image.url if item.image else None,
                }
                for item in cat.items.filter(is_available=True)
            ]
            if items:
                menu_data.append({"id": cat.id, "name": cat.name, "items": items})

      
        tasks = Task.objects.filter(
            room_unit=booking.room_unit
        ).order_by("-created_at")

       
        existing_orders = RestaurantOrder.objects.prefetch_related(
            "items__item"
        ).filter(booking=booking, order_type="room_service").order_by("-created_at")

        orders_data = []
        for o in existing_orders:
            orders_data.append({
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total": float(o.total_amount),
                "tax": float(o.tax_amount),
                "created_at": o.created_at.isoformat(),
                "items": [
                    {
                        "name": oi.item.name,
                        "qty": oi.quantity,
                        "unit_price": float(oi.unit_price),
                        "subtotal": float(oi.subtotal),
                    }
                    for oi in o.items.all()
                ],
            })

        # ── Laundry ──
        laundry_services = list(
            LaundryService.objects.values(
                "id", "name", "service_type", "price_per_unit", "turnaround_hours"
            )
        )
        laundry_orders = []
        for o in LaundryOrder.objects.filter(booking=booking).order_by("-created_at"):
            laundry_orders.append({
                "id": o.id,
                "status": o.status,
                "total": float(o.total_amount),
                "created_at": o.created_at.isoformat(),
            })

       
        from billing.models import GuestFolio, FolioCharge

        folio = None
        folio_charges = []
        folio_payments = []

        try:
            folio = GuestFolio.objects.get(booking=booking)
            folio_charges = folio.charges.all().order_by("charge_type", "date")
            # FolioPayment if your billing app has one; adjust model name as needed
            folio_payments = folio.payments.all() if hasattr(folio, "payments") else []
        except GuestFolio.DoesNotExist:
            pass  # Template will fall back to booking estimate

        return render(request, "guest_portal.html", {
            "booking": booking,
            "guest": booking.guest,
            "room": booking.room_unit,
            "token": token,
            "schema": schema,
            "menu": menu_data,
            "tasks": tasks,
            "existing_orders": orders_data,
            "laundry_services": laundry_services,
            "laundry_orders": laundry_orders,
            
            "folio": folio,
            "folio_charges": folio_charges,
            "folio_payments": folio_payments,
        })
@csrf_exempt
@transaction.atomic
def guest_place_order(request, schema, token):
    
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
 
    with schema_context(schema):
        booking = Booking.objects.select_related(
            "guest", "room", "room_unit"
        ).filter(guest_token=token).first()
 
        if not booking:
            return JsonResponse({"error": "Invalid or expired link"}, status=403)
 
        if booking.status != "checked_in":
            return JsonResponse({"error": "Booking is not active"}, status=400)
 
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
 
        items = data.get("items", [])
        if not items:
            return JsonResponse({"error": "No items in order"}, status=400)
 
        room_obj = booking.room
        unit = booking.room_unit
 
        order = RestaurantOrder.objects.create(
            order_type="room_service",
            room=room_obj,
            booking=booking,
            charge_to_room=True,
            served_by=None,  
        )
 
        total = Decimal("0")
        tax_total = Decimal("0")
 
        for i in items:
            try:
                menu_item = MenuItem.objects.get(pk=i["id"], is_available=True)
            except MenuItem.DoesNotExist:
                order.delete()
                return JsonResponse(
                    {"error": f"Item {i.get('id')} not found or unavailable"}, status=400
                )
 
            qty = max(1, int(i.get("qty", 1)))
            subtotal = menu_item.price * qty
            tax = subtotal * menu_item.tax_percent / 100
 
            OrderItem.objects.create(
                order=order,
                item=menu_item,
                quantity=qty,
                unit_price=menu_item.price,
                note=str(i.get("note", ""))[:200],
            )
 
            total += subtotal
            tax_total += tax
 
        order.total_amount = total
        order.tax_amount = tax_total
        order.save()
 
        
        try:
            from billing.models import GuestFolio, FolioCharge
 
            folio, _ = GuestFolio.objects.get_or_create(booking=booking)
            if folio.status == "open":
                FolioCharge.objects.create(
                    folio=folio,
                    charge_type="restaurant",
                    description=f"Room Service Order #{order.order_number}",
                    amount=total,
                    tax_amount=tax_total,
                    added_by=None,
                )
        except Exception as billing_err:
            
            return JsonResponse(
                {
                    "success": True,
                    "order_id": order.id,
                    "order_number": order.order_number,
                    "total": float(total),
                    "tax": float(tax_total),
                    "warning": f"Order placed but folio charge failed: {billing_err}",
                }
            )
 
        return JsonResponse(
            {
                "success": True,
                "order_id": order.id,
                "order_number": order.order_number,
                "total": float(total),
                "tax": float(tax_total),
            }
        )
 
 
# ── GUEST ORDERS LIST ────────────────────────────────────────
 
def guest_orders(request, schema, token):
  
    with schema_context(schema):
        booking = Booking.objects.filter(guest_token=token).first()
        if not booking:
            return JsonResponse({"error": "Invalid link"}, status=403)
 
        orders = RestaurantOrder.objects.prefetch_related(
            "items__item"
        ).filter(
            booking=booking,
            order_type="room_service",
        ).order_by("-created_at")
 
        data = []
        for o in orders:
            data.append({
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total": float(o.total_amount),
                "tax": float(o.tax_amount),
                "created_at": o.created_at.isoformat(),
                "items": [
                    {
                        "name": oi.item.name,
                        "qty": oi.quantity,
                        "unit_price": float(oi.unit_price),
                        "subtotal": float(oi.subtotal),
                    }
                    for oi in o.items.all()
                ],
            })
 
        return JsonResponse({"orders": data})
from django.shortcuts import get_object_or_404
@csrf_exempt
def guest_create_laundry_order(request, schema, token):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    with schema_context(schema):
        booking = get_object_or_404(Booking, guest_token=token)

        data = json.loads(request.body)

        guest_name = str(booking.guest)

        order = LaundryOrder.objects.create(
            room_number=booking.room_unit.room_number,
            guest_name=guest_name,
            booking=booking,
            order_type="guest_laundry"
        )

        total = Decimal("0")

        for i in data.get("items", []):
            service = get_object_or_404(LaundryService, id=i["service_id"])
            qty = Decimal(str(i["quantity"]))

            LaundryOrderItem.objects.create(
                order=order,
                service=service,
                item_name=i.get("item_name", service.name),
                quantity=qty,
                unit_price=service.price_per_unit
            )

            total += qty * service.price_per_unit

        order.total_amount = total
        order.save()

        folio, _ = GuestFolio.objects.get_or_create(booking=booking)

        if folio.status == "open":
            FolioCharge.objects.create(
                folio=folio,
                charge_type="laundry",
                description=f"Laundry Order #{order.id}",
                amount=total,
                tax_amount=Decimal("0"),
                added_by=None
            )

        return JsonResponse({
            "success": True,
            "order_id": order.id,
            "total": float(total)
        })
@csrf_exempt
def guest_create_request(request, schema, token):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    labels = {
        'water': 'Extra Water Bottles',
        'towel': 'Fresh Towels',
        'cleaning': 'Room Cleaning',
        'maintenance': 'Maintenance Assistance',
        'pillow': 'Extra Pillows',
        'dnd': 'Do Not Disturb',
        'custom': 'Custom Request',
    }

    with schema_context(schema):
        booking = get_object_or_404(Booking, guest_token=token)

        if booking.status != "checked_in":
            return JsonResponse({"error": "Booking not active"}, status=400)

        try:
            data = json.loads(request.body)
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        req_type = data.get("type")
        description = data.get("description", "").strip()

        if req_type not in labels:
            return JsonResponse({"error": "Invalid request type"}, status=400)

        if req_type == "custom" and not description:
            return JsonResponse({"error": "Custom request needs description"}, status=400)

      
        fallback_staff = Staff.objects.first()
        if not fallback_staff:
            return JsonResponse({"error": "No staff available to handle request"}, status=500)

        task = Task.objects.create(
            room=booking.room,
            room_unit=booking.room_unit,
            title=labels[req_type],
            description=description,
            status="Pending",
            staff=fallback_staff,
        )

        return JsonResponse({
            "success": True,
            "request_id": task.id,
            "title": labels[req_type],
        })


def guest_view_requests(request, schema, token):
    with schema_context(schema):
        booking = get_object_or_404(Booking, guest_token=token)

        tasks = Task.objects.filter(
            room_unit=booking.room_unit,
            created_at__gte=booking.actual_check_in
        ).select_related("staff").order_by("-created_at")

        data = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description or "",
                "status": t.status,
                "assigned_to": t.staff.name if t.staff else "Not assigned",
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]

        return JsonResponse({"success": True, "requests": data})


def fd_view_requests(request):
    GUEST_REQUEST_TITLES = [
        'Extra Water Bottles',
        'Fresh Towels',
        'Room Cleaning',
        'Maintenance Assistance',
        'Extra Pillows',
        'Do Not Disturb',
        'Custom Request',
    ]

    tasks = Task.objects.filter(
        title__in=GUEST_REQUEST_TITLES
    ).select_related("room_unit", "staff", "room").order_by("-created_at")

    data = []
    for t in tasks:
        guest_name = "N/A"
        if t.room_unit:
            active_booking = (
                Booking.objects.filter(
                    room_unit=t.room_unit,
                    status="checked_in"
                ).select_related("guest").first()
            )
            if active_booking and active_booking.guest:
                guest_name = active_booking.guest.full_name

        data.append({
            "id": t.id,
            "room_number": t.room_unit.room_number if t.room_unit else "N/A",
            "guest_name": guest_name,
            "title": t.title,
            "description": t.description or "",
            "status": t.status,
            "assigned_to": t.staff.name if t.staff else "Not assigned",
            "created_at": t.created_at.isoformat(),
        })

    return JsonResponse({"success": True, "requests": data})
@csrf_exempt
def fd_update_request(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    data = json.loads(request.body)
    task_id = data.get("task_id")
    status = data.get("status")
    staff_id = data.get("staff_id")

    try:
        task = Task.objects.get(id=task_id)
    except Task.DoesNotExist:
        return JsonResponse({"error": "Task not found"}, status=404)

    if status:
        task.status = status

    if staff_id:
        try:
            staff = Staff.objects.get(id=staff_id)
            task.staff = staff
        except Staff.DoesNotExist:
            return JsonResponse({"error": "Invalid staff"}, status=404)

    task.save()

    return JsonResponse({"success": True})
@csrf_exempt
def update_room_status(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body)

        room_unit_id = data.get("room_unit_id")
        new_status = data.get("status")

        if not room_unit_id or not new_status:
            return JsonResponse({"error": "Missing fields"}, status=400)

        try:
            room_unit = RoomUnit.objects.get(id=room_unit_id)
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": "Room unit not found"}, status=404)

        valid_statuses = [
            "Available",
            "Occupied",
            "Dirty",
            "Cleaning",
            "Maintenance",
            "Reserved"
        ]

        if new_status not in valid_statuses:
            return JsonResponse({"error": "Invalid status"}, status=400)

        if room_unit.status == "Occupied" and new_status != "Dirty":
            return JsonResponse({"error": "Cannot change occupied room unless checkout"}, status=400)

        room_unit.status = new_status
        room_unit.save()

        return JsonResponse({
            "success": True,
            "room_unit_id": room_unit.id,
            "new_status": room_unit.status
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
def get_guest_photos(request, guest_id):
    from pms.models import GuestIDPhoto
    try:
        photos = GuestIDPhoto.objects.filter(guest_id=guest_id).order_by('id')
        data = []
        for p in photos:
            
            uploaded = "ID Photo"
            for field in ['uploaded_at', 'created_at', 'timestamp']:
                val = getattr(p, field, None)
                if val:
                    uploaded = val.strftime("%d %b %Y, %H:%M")
                    break
            data.append({
                "url": request.build_absolute_uri(p.image.url),
                "uploaded_at": uploaded,
            })
        return JsonResponse({"photos": data})
    except Exception as e:
        import traceback
        return JsonResponse({"photos": [], "error": str(e), "trace": traceback.format_exc()})