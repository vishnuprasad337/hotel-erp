from django.shortcuts import render, redirect
from .models import Hotel,Amenity,Room,Department,Staff,Task,Shift,RoomUnit,InventoryItem,Attendance,LeaveRequest,Payroll
from django.http import JsonResponse
from pms.models import Booking,Payment
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate ,login
from django.contrib.auth.decorators import login_required
import json
from django.contrib.auth.models import User
from accounts.models import Department,HotelModule,Staff
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from datetime import timedelta
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404
def index(request):
    return render(request, "index.html")
##----------------------Superadmin Authentication----------------------






 


##----------------------STAFF MODULE----------------------
def staff_page(request):
    hotel = request.tenant 
    
    today = timezone.now().date()
    section = request.GET.get("section", "dashboard")
    filter_type = request.GET.get("filter", "today")
    sel_date_str = request.GET.get("date", str(today))
    sel_dept_id = request.GET.get("department")
    sel_shift = request.GET.get("shift")

    try:
        report_date = datetime.strptime(sel_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        report_date = today

    if filter_type == "week":
        start_date = today - timedelta(days=7)
    elif filter_type == "month":
        start_date = today.replace(day=1)
    else:
        start_date = today

    departments = Department.objects.annotate(staff_count=Count("staff"))

    staff_members = Staff.objects.select_related("department").all()
    if sel_dept_id:
        staff_members = staff_members.filter(department_id=sel_dept_id)

    total_staff = staff_members.count()

    attendance_qs = Attendance.objects.filter(date=today).select_related("staff__department")

    stats = attendance_qs.aggregate(
        present=Count("id", filter=Q(status__in=["Present", "Late", "Half Day"])),
        late=Count("id", filter=Q(status="Late")),
        half_day=Count("id", filter=Q(status="Half Day"))
    )

    attendance_records = []
    for att in attendance_qs:
        hours = 0
        overtime = 0
        if att.check_in and att.check_out:
            diff = att.check_out - att.check_in
            hours = round(diff.total_seconds() / 3600, 2)
            overtime = round(max(hours - 8, 0), 2)

        attendance_records.append({
            "staff_name": att.staff.name,
            "department": att.staff.department.name if att.staff and att.staff.department else "N/A",
            "date": att.date,
            "check_in": att.check_in,
            "check_out": att.check_out,
            "hours": hours,
            "overtime": overtime,
            "status": att.status
        })

    monthly_summary = Attendance.objects.filter(
        date__month=today.month,
        date__year=today.year
    ).values(
        "staff__id", "staff__name", "staff__department__name"
    ).annotate(
        present=Count("id", filter=Q(status="Present")),
        late=Count("id", filter=Q(status="Late")),
        half_day=Count("id", filter=Q(status="Half Day")),
        absent=Count("id", filter=Q(status="Absent")),
        overtime=Sum("overtime_hours")
    ).order_by("staff__name")

    shift_assignments = Shift.objects.filter(date__gte=start_date).select_related("staff", "department")
    if sel_shift:
        shift_assignments = shift_assignments.filter(shift=sel_shift)

    shift_counts = Shift.objects.filter(date=today).aggregate(
        morning=Count("id", filter=Q(shift="Morning")),
        evening=Count("id", filter=Q(shift="Evening")),
        night=Count("id", filter=Q(shift="Night"))
    )

    leave_requests = LeaveRequest.objects.select_related("staff").order_by("-applied_at")
    
    payrolls = Payroll.objects.filter(month=today.month, year=today.year).select_related("staff")
    payroll_stats = payrolls.aggregate(
        paid=Count("id", filter=Q(paid_status=True)),
        unpaid=Count("id", filter=Q(paid_status=False)),
        total_amount=Sum("net_salary")
    )

    tasks = Task.objects.filter(created_at__date__gte=start_date).select_related("staff", "room_unit")
    bookings = Booking.objects.filter(created_at__date__gte=start_date).select_related("guest", "room")
    
    revenue = Payment.objects.filter(
        booking__created_at__date__gte=start_date
    ).aggregate(total=Sum("total_amount"))["total"] or 0

    context = {
        "hotel": hotel,
        "today": today,
        "section": section,
        "filter": filter_type,
        "report_date": report_date,
        "departments": departments,
        "staff_members": staff_members,
        "total_staff": total_staff,
        "present_count": stats["present"],
        "late_count": stats["late"],
        "half_day_count": stats["half_day"],
        "absent_count": total_staff - (stats["present"] or 0),
        "attendance_records": attendance_records,
        "monthly_summary": monthly_summary,
        "shift_assignments": shift_assignments,
        "morning_count": shift_counts["morning"],
        "evening_count": shift_counts["evening"],
        "night_count": shift_counts["night"],
        "leave_requests": leave_requests,
        "pending_leaves": leave_requests.filter(status="Pending").count(),
        "approved_leaves": leave_requests.filter(status="Approved", from_date__lte=today, to_date__gte=today).count(),
        "payrolls": payrolls,
        "payroll_paid": payroll_stats["paid"],
        "payroll_unpaid": payroll_stats["unpaid"],
        "total_payroll": payroll_stats["total_amount"] or 0,
        "tasks": tasks[:10],
        "pending_tasks": tasks.filter(status="Pending").count(),
        "completed_tasks": tasks.filter(status="Completed").count(),
        "bookings": bookings[:10],
        "total_bookings": bookings.count(),
        "revenue": revenue,
        "inventory": InventoryItem.objects.all().order_by("-id")
    }

    return render(request, "staff.html", context)

def gets_inventory(request):
    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse({"error": "Not logged in"}, status=401)

    staff = Staff.objects.get(id=staff_id)
    hotel = staff.hotel

    items = InventoryItem.objects.filter(
        hotel=hotel
    ).select_related(
        "room", "updated_by", "assigned_by"   
    ).order_by("-updated_at")

    data = [
        {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "quantity": item.quantity,
            "unit": item.unit,
            "room_number": item.room.room_number if item.room else "N/A",

            "updated_by": item.updated_by.name if item.updated_by else "N/A",
            "assigned_by": item.assigned_by.name if item.assigned_by else "N/A",
            "description": item.description,
        }
        for item in items
    ]

    return JsonResponse(data, safe=False)


def assign_task(request):
    if request.method == "POST":
        staff_id = request.POST.get("staff")
        title = request.POST.get("title")
        description = request.POST.get("description")

        Task.objects.create(
            staff_id=staff_id,
            title=title,
            description=description
        )

        return redirect("staff_page")

def get_tasks(request):
    hotel_id = request.session.get("hotel_id")
    tasks = Task.objects.filter(staff__hotel_id=hotel_id).select_related("staff")
    
    task_list = []
    for t in tasks:
        task_list.append({
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "staff": t.staff.name,
            "staff_id": t.staff.id, 
            "status": t.status,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(t, 'created_at') else None
        })
    
    return JsonResponse({"tasks": task_list, "count": tasks.count()})
from datetime import datetime
from django.http import JsonResponse

def get_shifts(request):
    hotel_id = request.session.get("hotel_id")
    date_str = request.GET.get("date")

    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    shifts = Shift.objects.filter(hotel_id=hotel_id)

    if date_str:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            shifts = shifts.filter(date=date_obj)
        except ValueError:
            return JsonResponse({"error": "Invalid date format"}, status=400)

    shifts = shifts.select_related("staff", "department")

    data = [{
        "id": s.id,
        "staff": s.staff.name,
        "staff_id": s.staff.id,
        "department": s.department.name,
        "shift": s.shift,
        "date": s.date.strftime("%Y-%m-%d")
    } for s in shifts]

    return JsonResponse(data, safe=False)
from datetime import datetime

from datetime import datetime, timedelta
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

@require_POST
def assign_shift(request):
    try:
        hotel_id = request.session.get("hotel_id")
        staff_id = request.POST.get("staff")
        department_id = request.POST.get("department")
        shift_value = request.POST.get("shift")
        from_date = request.POST.get("from_date")
        to_date = request.POST.get("to_date")

        if not hotel_id:
            return JsonResponse({"error": "Login required"}, status=401)

        if not all([staff_id, shift_value, from_date, to_date]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(to_date, "%Y-%m-%d").date()

        if start_date > end_date:
            return JsonResponse({"error": "Invalid date range"}, status=400)

        if not department_id:
            staff = get_object_or_404(Staff, id=staff_id)
            department_id = staff.department_id

        if not department_id:
            return JsonResponse({"error": "Department is required"}, status=400)

        current_date = start_date
        created_count = 0
        updated_count = 0

        while current_date <= end_date:
            _, created = Shift.objects.update_or_create(
                hotel_id=hotel_id,
                staff_id=staff_id,
                date=current_date,
                defaults={
                    "department_id": department_id,
                    "shift": shift_value
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            current_date += timedelta(days=1)

        return JsonResponse({
            "success": True,
            "message": f"{created_count} shifts created, {updated_count} updated"
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def weekly_schedule(request):
    staff_id = request.session.get("staff_id")
    hotel_id = request.session.get("hotel_id")
    start_date = request.GET.get("start_date")

    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    # Ensure hotel_id exists
    if not hotel_id:
        try:
            current = Staff.objects.select_related("hotel").get(id=staff_id)
            hotel_id = current.hotel_id
            request.session["hotel_id"] = hotel_id
        except Staff.DoesNotExist:
            return JsonResponse({"error": "Staff not found"}, status=404)

    # Default to today if not provided
    if not start_date:
        start_date_obj = datetime.today().date()
    else:
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Invalid start_date"}, status=400)

    end_date = start_date_obj + timedelta(days=6)

    # Fetch shifts
    shifts = Shift.objects.filter(
        hotel_id=hotel_id,
        date__range=[start_date_obj, end_date]
    ).select_related("staff", "department")

    # Prepare empty week structure
    data = {
        (start_date_obj + timedelta(days=i)).strftime("%Y-%m-%d"): []
        for i in range(7)
    }

    for s in shifts:
        day = s.date.strftime("%Y-%m-%d")
        data[day].append({
            "staff": s.staff.name if s.staff else "N/A",
            "shift": s.shift,
            "department": s.department.name if s.department else "N/A",
        })

    return JsonResponse({
        "schedule": data,
        "debug": {
            "hotel_id": hotel_id,
            "total_shifts": shifts.count()
        }
    })
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

@require_GET
def get_weekly_schedule(request):
    staff_id = request.session.get("staff_id")
    start_date = request.GET.get("start_date")

    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    # Validate staff — ensure the session staff_id matches a real staff record
    try:
        staff = Staff.objects.select_related("hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    # Handle start date
    if not start_date:
        start_date_obj = datetime.today().date()
    else:
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Invalid start_date format. Use YYYY-MM-DD"}, status=400)

    end_date = start_date_obj + timedelta(days=6)

    # ✅ Strictly filter shifts assigned to the logged-in staff only
    shifts = Shift.objects.filter(
        staff=staff,           # use the object, not raw ID — prevents ID spoofing via GET params
        date__range=[start_date_obj, end_date]
    ).select_related("department").order_by("date", "shift")

    # Prepare week structure
    schedule = {
        (start_date_obj + timedelta(days=i)).strftime("%Y-%m-%d"): []
        for i in range(7)
    }

    for s in shifts:
        day = s.date.strftime("%Y-%m-%d")
        schedule[day].append({
            "shift": s.shift,
            "department": s.department.name if s.department else "N/A",
        })

    return JsonResponse({
        "staff_id": staff.id,
        "staff": staff.name,
        "week_start": start_date_obj.strftime("%Y-%m-%d"),
        "week_end": end_date.strftime("%Y-%m-%d"),
        "schedule": schedule,
        "total_shifts": shifts.count()
    })
def update_shift(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    hotel_id = request.session.get("hotel_id")
    shift_id = request.POST.get("shift_id")
    new_shift = request.POST.get("shift")

    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    try:
        shift = Shift.objects.get(id=shift_id, hotel_id=hotel_id)
        shift.shift = new_shift
        shift.save()
        return JsonResponse({"success": True})
    except Shift.DoesNotExist:
        return JsonResponse({"error": "Shift not found"}, status=404)


def staff_by_shift(request):
    hotel_id = request.session.get("hotel_id")
    shift = request.GET.get("shift")
    date_str = request.GET.get("date")

    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    if not all([shift, date_str]):
        return JsonResponse({"error": "Missing parameters"}, status=400)

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"error": "Invalid date format"}, status=400)

    staff = Shift.objects.filter(
        hotel_id=hotel_id,
        shift=shift,
        date=date_obj
    ).select_related("staff")

    data = [{
        "name": s.staff.name,
        "role": s.staff.role
    } for s in staff]

    return JsonResponse(data, safe=False)
#----------------------STAFF MODULE----------------------
from django.contrib.auth.hashers import check_password, make_password

@require_POST
def update_staff_profile(request):
    try:
        staff_id = request.session.get("staff_id")

        if not staff_id:
            return JsonResponse({"error": "Login required"}, status=401)

        staff = get_object_or_404(Staff, id=staff_id)

        
        staff.name = request.POST.get("name", staff.name)
        staff.phone = request.POST.get("phone", staff.phone)

        
        user = staff.user
        user.email = request.POST.get("email", user.email)

        current_password = request.POST.get("current_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if new_password:
            if not check_password(current_password, user.password):
                return JsonResponse({"error": "Current password is incorrect"}, status=400)

            if new_password != confirm_password:
                return JsonResponse({"error": "Passwords do not match"}, status=400)

            user.password = make_password(new_password)

        if request.FILES.get("photo"):
            staff.photo = request.FILES["photo"]

        user.save()
        staff.save()

        return JsonResponse({
            "success": True,
            "name": staff.name,
            "email": user.email,
            "photo": staff.photo.url if staff.photo else None,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
#----------------------HOUSEKEEPING MODULE----------------------
from django.shortcuts import render, redirect
from django.utils import timezone

def housekeeping_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")
 
    staff = Staff.objects.select_related("department").get(id=staff_id)
 
    # Only show rooms where a task is assigned to THIS staff member
    my_tasks = Task.objects.filter(
        staff=staff
    ).select_related("room_unit", "room_unit__room")
 
    # Get unique room units from my tasks
    seen_ids = set()
    rooms = []
    for task in my_tasks:
        unit = task.room_unit
        if unit and unit.id not in seen_ids:
            seen_ids.add(unit.id)
            rooms.append({
                "id": unit.id,
                "number": unit.room_number,
                "status": unit.status.lower(),  # CSS data-status needs lowercase
                "room_type": unit.room.room_type if unit.room else "Standard",
                "has_task": True,  # always True here since we got it from a task
            })
 
    # All units still needed for stats counts
    all_units = RoomUnit.objects.all()
 
    tasks = my_tasks.filter(status="Pending")
    all_tasks = my_tasks
 
    context = {
        "staff": staff,
        "rooms": rooms,
        "tasks": tasks,
        "all_tasks": all_tasks,
        "clean_rooms": all_units.filter(status="Available").count(),
        "dirty_rooms": all_units.filter(status="Dirty").count(),
        "cleaning_rooms": all_units.filter(status="Cleaning").count(),
        "pending_tasks": tasks.count(),
    }
 
    return render(request, "housekeeping.html", context)
 
@csrf_exempt
def start_cleaning(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            room_unit_id = data.get("room_unit_id")
 
            room_unit = RoomUnit.objects.get(id=room_unit_id)
            old_status = room_unit.status
 
            if old_status == "Dirty":
                room_unit.status = "Cleaning"
                room_unit.save()
 
                task = Task.objects.create(
                    staff_id=request.session.get("staff_id"),
                    room_unit=room_unit,
                    room=room_unit.room,
                    title=f"Clean Room {room_unit.room_number}",
                    description="Room cleaning in progress",
                    status="Pending"
                )
 
                return JsonResponse({
                    "success": True,
                    "message": f"Started cleaning Room {room_unit.room_number}",
                    "new_status": "Cleaning",
                    "task_id": task.id
                })
            else:
                return JsonResponse({
                    "error": f"Room status is {old_status}, cannot start cleaning"
                }, status=400)
 
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": "Room not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
 
    return JsonResponse({"error": "Method not allowed"}, status=405)
 
 
@csrf_exempt
def complete_cleaning(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            room_unit_id = data.get("room_unit_id")
            task_id = data.get("task_id")
 
            room_unit = RoomUnit.objects.get(id=room_unit_id)
 
            if room_unit.status == "Cleaning":
                room_unit.status = "Available"
                room_unit.save()
 
                # Update task to completed if task_id provided
                if task_id:
                    try:
                        task = Task.objects.get(id=task_id)
                        task.status = "Completed"
                        task.save()
                    except Task.DoesNotExist:
                        pass
 
                # Also mark any other pending tasks for this room as completed
                Task.objects.filter(
                    room_unit=room_unit,
                    status__in=["Pending", "In Progress"]
                ).update(status="Completed")
 
                return JsonResponse({
                    "success": True,
                    "message": f"Room {room_unit.room_number} is now clean and available",
                    "new_status": "Available"
                })
            else:
                return JsonResponse({
                    "error": f"Room status is {room_unit.status}, cannot complete cleaning"
                }, status=400)
 
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": "Room not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
 
    return JsonResponse({"error": "Method not allowed"}, status=405)
 
@csrf_exempt
def add_inventory(request):
    if request.method == "POST":
        try:
            staff = Staff.objects.get(id=request.session.get("staff_id"))
            hotel = staff.hotel
            
            name = request.POST.get("name")
            category = request.POST.get("category")
            quantity = int(request.POST.get("quantity", 0))
            unit = request.POST.get("unit", "pieces")
            reorder_level = int(request.POST.get("reorder_level", 10))
            description = request.POST.get("description", "")
            room_id = request.POST.get("room_id")
            
            if not name:
                return JsonResponse({"error": "Item name is required"}, status=400)
            
            if not room_id:
                return JsonResponse({"error": "Please select a room"}, status=400)
            
            room = RoomUnit.objects.get(id=room_id)
            
            inventory_item = InventoryItem.objects.create(
                hotel=hotel,
                room=room,
                name=name,
                category=category,
                quantity=quantity,
                unit=unit,
                reorder_level=reorder_level,
                description=description,
                assigned_by=staff
            )
            
            return JsonResponse({"success": True, "id": inventory_item.id})
        except RoomUnit.DoesNotExist:
            return JsonResponse({"error": "Room not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)
def get_inventory(request):
    try:
        staff = Staff.objects.get(id=request.session.get("staff_id"))
        hotel = staff.hotel

        items = InventoryItem.objects.filter(hotel=hotel).select_related("room")

        data = []
        for item in items:
            data.append({
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "quantity": item.quantity,
                "unit": item.unit,
                "room_number": item.room.room_number, 
                "description": item.description
            })

        return JsonResponse({"items": data})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def update_inventory(request, item_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        
        hotel_id = request.session.get("hotel_id")
        staff_id = request.session.get("staff_id")

        if not hotel_id:
            return JsonResponse({"error": "Hotel not found in session"}, status=400)

       
        item = get_object_or_404(InventoryItem, id=item_id, hotel_id=hotel_id)

       
        staff = None
        if staff_id:
            staff = Staff.objects.filter(id=staff_id, hotel_id=hotel_id).first()

       
        name = request.POST.get("name")
        category = request.POST.get("category")
        quantity = request.POST.get("quantity")
        unit = request.POST.get("unit")
        reorder_level = request.POST.get("reorder_level")
        description = request.POST.get("description")
        room_id = request.POST.get("room_id")

        
        if name:
            item.name = name

        if category:
            item.category = category

        if quantity:
            try:
                item.quantity = int(quantity)
            except ValueError:
                return JsonResponse({"error": "Invalid quantity"}, status=400)

        if unit:
            item.unit = unit

        if reorder_level:
            try:
                item.reorder_level = int(reorder_level)
            except ValueError:
                return JsonResponse({"error": "Invalid reorder level"}, status=400)

        if description is not None:
            item.description = description

        if room_id:
            room = RoomUnit.objects.filter(id=room_id, hotel_id=hotel_id).first()
            if not room:
                return JsonResponse({"error": "Invalid room"}, status=400)
            item.room = room

        
        if staff:
            item.updated_by = staff

        item.save()

        return JsonResponse({
            "success": True,
            "message": "Inventory updated successfully"
        })

    except Exception as e:
        return JsonResponse({
            "error": str(e)
        }, status=500)
@csrf_exempt
def delete_inventory(request, item_id):
    if request.method == "DELETE":
        try:
            item = InventoryItem.objects.get(id=item_id)
            item.delete()
            return JsonResponse({"success": True})
        except InventoryItem.DoesNotExist:
            return JsonResponse({"error": "Inventory item not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Method not allowed"}, status=405)
import json
from django.shortcuts import render, redirect
from django.utils import timezone

import json
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Prefetch, Count
def hr_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("hotel", "department").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    hotel = staff.hotel
    today = timezone.now().date()

    hotel_staff_ids = Staff.objects.filter(hotel=hotel).values_list("id", flat=True)

    bookings = Booking.objects.filter(
        created_by_id__in=hotel_staff_ids
    ).select_related("guest", "room", "room_unit").order_by("-id")

    if not bookings.exists():
        bookings = Booking.objects.all().select_related(
            "guest", "room", "room_unit"
        ).order_by("-id")

    arrivals = bookings.filter(check_in=today, status="confirmed")
    departures = bookings.filter(check_out=today, status="checked_in")

    rooms_qs = Room.objects.filter(is_active=True).prefetch_related("units")

    rooms_json = json.dumps([
        {
            "id": r.id,
            "room_type": r.room_type,
            "price": float(r.base_price or 0),
            "max_adults": r.max_adults,
            "max_children": r.max_children,
            "description": r.description or "",
            "units": [
                {
                    "id": u.id,
                    "room_number": u.room_number,
                    "number": u.room_number,
                    "status": u.status,
                }
                for u in r.units.all()
            ],
            "images": [],
        }
        for r in rooms_qs
    ])

    room_units = RoomUnit.objects.select_related("room").order_by("room_number")

    hk_dept = Department.objects.filter(
        hotel=hotel, name__icontains="housekeeping"
    ).first()

    if hk_dept:
        housekeeping_staff = Staff.objects.filter(
            hotel=hotel, department=hk_dept
        ).select_related("department")
    else:
        housekeeping_staff = Staff.objects.filter(
            hotel=hotel
        ).select_related("department")

    hotel_staff = Staff.objects.filter(hotel=hotel).select_related("department")

    departments = Department.objects.filter(hotel=hotel).prefetch_related(
        Prefetch(
            "staff_set",
            queryset=Staff.objects.filter(hotel=hotel).select_related("department"),
            to_attr="employees"
        )
    ).annotate(staff_count=Count("staff"))

    recent_tasks = (
        Task.objects.filter(staff__hotel=hotel)
        .select_related("staff", "room_unit", "room_unit__room")
        .order_by("-created_at")[:30]
    )

    shifts = Shift.objects.filter(
        hotel=hotel
    ).select_related("staff", "department")

    total_bookings = bookings.count()
    arrivals_count = arrivals.count()
    departures_count = departures.count()
    occupied_rooms = bookings.filter(status="checked_in").count()
    total_staff = hotel_staff.count()
    total_departments = departments.count()

    schema = getattr(hotel, "schema_name", "") or getattr(hotel, "slug", "") or str(hotel.id)

    return render(request, "hr.html", {
        "staff":              staff,
        "hotel":              hotel,
        "bookings":           bookings,
        "arrivals":           arrivals,
        "departures":         departures,
        "arrivals_count":     arrivals_count,
        "departures_count":   departures_count,
        "total_bookings":     total_bookings,
        "occupied_rooms":     occupied_rooms,
        "rooms":              rooms_qs,
        "rooms_json":         rooms_json,
        "room_units":         room_units,
        "housekeeping_staff": housekeeping_staff,
        "hotel_staff":        hotel_staff,
        "departments":        departments,
        "recent_tasks":       recent_tasks,
        "shifts":             shifts,
        "total_staff":        total_staff,
        "total_departments":  total_departments,
        "schema":             schema,
        "token":              "",
    })
from datetime import time

SHIFT_TIMINGS = {
    "Morning": (time(9, 0), time(17, 0)),
    "Evening": (time(14, 0), time(22, 0)),
    "Night": (time(22, 0), time(6, 0)),
}


@require_POST
def mark_attendance(request):
    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    try:
        staff = Staff.objects.get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    now = timezone.now()
    today = now.date()

    attendance, created = Attendance.objects.get_or_create(
        staff=staff,
        hotel=staff.hotel,
        date=today
    )

    shift_obj = Shift.objects.filter(staff=staff, date=today).first()
    shift_name = shift_obj.shift if shift_obj else None

    shift_start, shift_end = None, None

    if shift_name in SHIFT_TIMINGS:
        shift_start, shift_end = SHIFT_TIMINGS[shift_name]

    if attendance.check_in is None:
        attendance.check_in = now

        if shift_start and now.time() > shift_start:
            attendance.status = "Late"
        else:
            attendance.status = "Present"

        attendance.save()

        return JsonResponse({
            "success": True,
            "type": "checkin",
            "shift": shift_name,
            "check_in": attendance.check_in.isoformat(),
            "status": attendance.status
        })

    elif attendance.check_out is None:
        attendance.check_out = now

        working_hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600
        overtime = 0

        if shift_start and shift_end:
            tz = timezone.get_current_timezone()

            shift_start_dt = timezone.make_aware(datetime.combine(today, shift_start), tz)
            shift_end_dt = timezone.make_aware(datetime.combine(today, shift_end), tz)

            if shift_end < shift_start:
                shift_end_dt += timedelta(days=1)

            if attendance.check_out > shift_end_dt:
                overtime = (attendance.check_out - shift_end_dt).total_seconds() / 3600

            shift_duration = (shift_end_dt - shift_start_dt).total_seconds() / 3600

            if working_hours < (shift_duration / 2):
                attendance.status = "Half Day"
            elif attendance.status != "Late":
                attendance.status = "Present"

        attendance.overtime_hours = round(overtime, 2)
        attendance.save()

        return JsonResponse({
            "success": True,
            "type": "checkout",
            "shift": shift_name,
            "check_out": attendance.check_out.isoformat(),
            "working_hours": round(working_hours, 2),
            "overtime": attendance.overtime_hours,
            "status": attendance.status
        })

    return JsonResponse({
        "success": False,
        "message": "Attendance already completed"
    })
    
def live_attendance(request):
    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    today = timezone.now().date()

    records = Attendance.objects.filter(
        hotel_id=hotel_id,
        date=today
    ).select_related("staff").order_by("-check_in")

    data = []
    for r in records:
        if r.check_in and not r.check_out:
            status = "Working"
        elif r.check_in and r.check_out:
            status = "Left"
        else:
            status = "Absent"

        data.append({
            "name": r.staff.name,
            "check_in": r.check_in.isoformat() if r.check_in else None,
            "check_out": r.check_out.isoformat() if r.check_out else None,
            "overtime_hours": float(r.overtime_hours or 0),
            "status": status
        })

    return JsonResponse(data, safe=False)

def daily_report(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    date_str = request.GET.get("date")
    if not date_str:
        return JsonResponse({"error": "Date parameter required"}, status=400)

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"error": "Invalid date format"}, status=400)

    shift_staff_ids = Shift.objects.filter(
        hotel_id=hotel_id,
        date=date_obj
    ).values_list("staff_id", flat=True)

    all_staff = Staff.objects.filter(
        hotel_id=hotel_id,
        id__in=shift_staff_ids
    ).select_related("department")

    att_map = {
        a.staff_id: a
        for a in Attendance.objects.filter(hotel_id=hotel_id, date=date_obj)
    }

    data = []
    for s in all_staff:
        a = att_map.get(s.id)
        data.append({
            "name": s.name,
            "department": s.department.name if s.department else "—",
            "date": date_str,
            "check_in": a.check_in.isoformat() if a and a.check_in else None,
            "check_out": a.check_out.isoformat() if a and a.check_out else None,
            "status": a.status if a else "Absent",
            "overtime": float(a.overtime_hours or 0) if a else 0.0
        })

    return JsonResponse(data, safe=False)
def monthly_report(request):
    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    today = timezone.now()
    month = today.month
    year = today.year

    records = Attendance.objects.filter(
        hotel_id=hotel_id,
        date__month=month,
        date__year=year
    ).values("staff__name").annotate(
        present=Count("id", filter=Q(status="Present")),
        absent=Count("id", filter=Q(status="Absent")),
        late=Count("id", filter=Q(status="Late")),
        overtime=Sum("overtime_hours")       
    ).order_by("staff__name")

    data = []
    for r in records:
        data.append({
            "staff__name": r["staff__name"],
            "present": r["present"],
            "absent": r["absent"],
            "late": r["late"],
            "overtime": round(float(r["overtime"] or 0), 2)
        })
    return JsonResponse(data, safe=False)
@csrf_exempt
def apply_leave(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    staff_id = request.session.get("staff_id")
    tenant = request.tenant

    if not staff_id:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    staff = Staff.objects.filter(id=staff_id).first()
    if not staff:
        return JsonResponse({"error": "Invalid staff"}, status=401)

    from_date = request.POST.get("from_date")
    to_date = request.POST.get("to_date")
    reason = request.POST.get("reason", "")
    leave_type = request.POST.get("leave_type", "casual")

    try:
        from_date = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_date = datetime.strptime(to_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid date format"}, status=400)

    LeaveRequest.objects.create(
        staff=staff,
        tenant=tenant,
        from_date=from_date,
        to_date=to_date,
        reason=reason,
        status="Pending"
    )

    return JsonResponse({"success": True})


def leave_requests(request):
    tenant = request.tenant
    staff_id = request.session.get("staff_id")

    # Determine if current user is HR/admin
    is_admin = False
    if staff_id:
        try:
            current_staff = Staff.objects.get(id=staff_id)
            role = (getattr(current_staff, 'role', '') or '').lower()
            dept_name = (current_staff.department.name if current_staff.department else '').lower()
            is_admin = any(k in role or k in dept_name for k in ['hr', 'admin', 'manager', 'owner'])
        except Staff.DoesNotExist:
            pass

    # Optional month/year filter
    month = request.GET.get("month")
    year = request.GET.get("year")

    if is_admin:
        leaves = LeaveRequest.objects.filter(tenant=tenant).select_related("staff").order_by("-applied_at")
    else:
        leaves = LeaveRequest.objects.filter(
            tenant=tenant,
            staff_id=staff_id
        ).select_related("staff").order_by("-applied_at")

    if month:
        leaves = leaves.filter(from_date__month=month)
    if year:
        leaves = leaves.filter(from_date__year=year)

    data = []
    for l in leaves:
        data.append({
            "id": l.id,
            "staff": getattr(l.staff, "name", "Deleted Staff"),
            "staff_id": l.staff_id,
            "from_date": l.from_date.strftime("%Y-%m-%d") if l.from_date else None,
            "to_date": l.to_date.strftime("%Y-%m-%d") if l.to_date else None,
            "reason": l.reason or "",
            "leave_type": l.reason or "",   # adjust if you have a leave_type field
            "applied_at": l.applied_at.strftime("%Y-%m-%d") if getattr(l, "applied_at", None) else None,
            "status": l.status,
            "is_admin_view": is_admin,
        })

    return JsonResponse(data, safe=False)
@require_POST
def update_leave_status(request, leave_id):
    tenant = request.tenant
    staff_id = request.session.get("staff_id")

    action = request.POST.get("action")

    leave = LeaveRequest.objects.filter(
        id=leave_id,
        tenant=tenant  
    ).first()

    if not leave:
        return JsonResponse({"error": "Leave not found"}, status=404)

    if action == "approve":
        leave.status = "Approved"
    elif action == "reject":
        leave.status = "Rejected"
    else:
        return JsonResponse({"error": "Invalid action"}, status=400)

    leave.action_by_id = staff_id
    leave.action_at = timezone.now()
    leave.save()

    return JsonResponse({"success": True})
from decimal import Decimal

def calculate_payroll(staff, month, year):
    attendances = Attendance.objects.filter(
        staff=staff,
        date__month=month,
        date__year=year
    )

    total_days = attendances.count()
    absent_days = attendances.filter(status="Absent").count()

    overtime_hours = sum(
        (a.overtime_hours or 0) for a in attendances
    )

    basic_salary = Decimal(staff.salary or 0)

    per_day_salary = basic_salary / Decimal("30")

    deduction = Decimal(absent_days) * per_day_salary

    overtime_amount = Decimal(overtime_hours) * Decimal("100")

    net_salary = basic_salary - deduction + overtime_amount

    return {
        "basic": round(basic_salary, 2),
        "deduction": round(deduction, 2),
        "overtime": round(overtime_amount, 2),
        "net": round(net_salary, 2)
    }
def generate_payroll(request):
    if request.method == "POST":
        hotel_id = request.session.get("hotel_id")
        month = int(request.POST.get("month"))
        year = int(request.POST.get("year"))

        staffs = Staff.objects.filter(hotel_id=hotel_id)

        for staff in staffs:
            data = calculate_payroll(staff, month, year)

            Payroll.objects.update_or_create(
                staff=staff,
                hotel_id=hotel_id,
                month=month,
                year=year,
                defaults={
                    "basic_salary": data["basic"],
                    "overtime_amount": data["overtime"],
                    "deductions": data["deduction"],
                    "net_salary": data["net"]
                }
            )

        return JsonResponse({"success": True, "message": "Payroll generated"})
def payroll_dashboard(request):
    hotel_id = request.session.get("hotel_id")
    
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)
    
    payrolls = Payroll.objects.filter(hotel_id=hotel_id).select_related("staff")
    
    data = []
    for p in payrolls:
        data.append({
            "id": p.id,  # ← ADD THIS LINE - it's missing!
            "staff": p.staff.name,
            "staff_id": p.staff.id,
            "month": p.month,
            "year": p.year,
            "basic_salary": str(p.basic_salary),
            "overtime_amount": str(p.overtime_amount),
            "deductions": str(p.deductions),
            "net_salary": str(p.net_salary),
            "paid_status": p.paid_status,
            "paid": p.paid_status == "Paid"
        })
    
    return JsonResponse(data, safe=False)
def payslip(request, payroll_id):
    try:
        p = Payroll.objects.select_related("staff").get(id=payroll_id)
        
        data = {
            "id": p.id,
            "staff": p.staff.name,
            "employee_id": p.staff.employee_id if p.staff.employee_id else f"EMP{p.staff.id}",
            "month": p.month,
            "year": p.year,
            "basic_salary": float(p.basic_salary),
            "overtime": float(p.overtime_amount),
            "deductions": float(p.deductions),
            "net_salary": float(p.net_salary),
            "paid_status": p.paid_status
        }
        return JsonResponse(data)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payslip not found"}, status=404)
def accountant_dashboard(request):
    return render(request, "accountant.html")
#----------------------FRONTDESK MODULE----------------------

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from accounts.models import Staff
from hotel.models import Task
from pms.models import Booking
from django.db.models import Q

@login_required
def staff_tasks(request):
    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse({"error": "Not logged in"}, status=401)

    try:
        staff = Staff.objects.get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    tasks = Task.objects.filter(staff=staff).select_related(
        "room_unit", "room"
    ).order_by("-created_at")

    data = []

    for t in tasks:
        guest_name = "N/A"
        booking_id = None

        if t.room_unit:
            booking = Booking.objects.filter(
                room_unit=t.room_unit
            ).filter(
                Q(status="checked_in") | Q(status="confirmed")
            ).select_related("guest").order_by("-created_at").first()

            if booking and booking.guest:
                guest_name = booking.guest.full_name
                booking_id = booking.id

        data.append({
            "id": t.id,
            "room_number": t.room_unit.room_number if t.room_unit else "N/A",
            "room_type": t.room.room_type if t.room else "N/A",
            "guest_name": guest_name,
            "booking_id": booking_id,
            "task": t.title,
            "description": t.description or "",
            "status": t.status,
            "created_at": t.created_at.isoformat(),
        })

    return JsonResponse({
        "success": True,
        "tasks": data
    })
@login_required
def update_task_status(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"error": "Not logged in"}, status=401)

    task_id = request.POST.get("task_id")
    new_status = request.POST.get("status")
    note = request.POST.get("note", "")

    valid_statuses = ["Pending", "In Progress", "Completed"]
    if new_status not in valid_statuses:
        return JsonResponse({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}, status=400)

    try:
        task = Task.objects.get(id=task_id, staff__id=staff_id)
    except Task.DoesNotExist:
        return JsonResponse({"error": "Task not found or not assigned to you"}, status=404)

    task.status = new_status
    
    task.save()

    return JsonResponse({
        "success": True,
        "task_id": task.id,
        "new_status": task.status,
    })







FRONT_DESK_KEYWORDS  = ["front desk", "front office", "reception", "fd"]
HOUSEKEEPING_KEYWORDS = ["housekeeping", "hk", "cleaning"]


def _dept_type(staff):
   
    dept = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, "role", "") or "").lower()
    combined = dept + " " + role

    if any(k in combined for k in FRONT_DESK_KEYWORDS):
        return "frontdesk"
    if any(k in combined for k in HOUSEKEEPING_KEYWORDS):
        return "housekeeping"
    
    return "general"


def _attendance_for(staff, date_obj):
    att = Attendance.objects.filter(staff=staff, date=date_obj).first()
    if not att:
        return None
    working_hours = 0.0
    if att.check_in and att.check_out:
        working_hours = round(
            (att.check_out - att.check_in).total_seconds() / 3600, 2
        )
    return {
        "check_in":  att.check_in.strftime("%H:%M") if att.check_in  else None,
        "check_out": att.check_out.strftime("%H:%M") if att.check_out else None,
        "status":    att.status,
        "working_hours": working_hours,
        "overtime_hours": float(att.overtime_hours or 0),
    }


def _shift_for(staff, date_obj):
    shift = Shift.objects.filter(staff=staff, date=date_obj).first()
    return shift.shift if shift else None



def _frontdesk_report(staff, date_obj):
    
    checkins = Booking.objects.filter(
        actual_check_in__date=date_obj,
        status__in=["checked_in", "checked_out"]
    ).select_related("guest", "room", "room_unit")

   
    checkouts = Booking.objects.filter(
        actual_check_out__date=date_obj,
        status="checked_out"
    ).select_related("guest", "room", "room_unit")

    # New bookings created on this date
    new_bookings = Booking.objects.filter(
        created_at__date=date_obj
    ).select_related("guest", "room", "room_unit")

    def serialize_booking(b, event_type):
        try:
            total = float(b.payment.total_amount)
            payment_status = b.payment.payment_status
        except Exception:
            total = 0.0
            payment_status = "unknown"
        return {
            "booking_id":     b.id,
            "booking_code":   getattr(b, "booking_code", None) or f"BK{b.id:06d}",
            "event":          event_type,
            "guest_name":     b.guest.full_name if b.guest else "N/A",
            "guest_phone":    b.guest.phone     if b.guest else "",
            "room_type":      b.room.room_type  if b.room  else "N/A",
            "room_number":    b.room_unit.room_number if b.room_unit else "N/A",
            "check_in":       b.check_in.isoformat()  if b.check_in  else None,
            "check_out":      b.check_out.isoformat() if b.check_out else None,
            "nights":         getattr(b, "nights", None),
            "adults":         b.adults,
            "children":       b.children,
            "source":         b.source or "",
            "status":         b.status,
            "total_amount":   total,
            "payment_status": payment_status,
        }

    activity = []
    seen_ids = set()

    for b in checkins:
        if b.id not in seen_ids:
            activity.append(serialize_booking(b, "check_in"))
            seen_ids.add(b.id)

    for b in checkouts:
        if b.id not in seen_ids:
            activity.append(serialize_booking(b, "check_out"))
            seen_ids.add(b.id)

    for b in new_bookings:
        if b.id not in seen_ids:
            activity.append(serialize_booking(b, "new_booking"))
            seen_ids.add(b.id)

    revenue_today = sum(
        item["total_amount"] for item in activity if item["payment_status"] == "paid"
    )

    return {
        "type": "frontdesk",
        "summary": {
            "check_ins":    checkins.count(),
            "check_outs":   checkouts.count(),
            "new_bookings": new_bookings.count(),
            "total_actions": len(activity),
            "revenue_collected": round(revenue_today, 2),
        },
        "activity": activity,
    }


def _housekeeping_report(staff, date_obj):
    
    tasks = Task.objects.filter(
        staff=staff,
        created_at__date=date_obj
    ).select_related("room_unit", "room").order_by("created_at")

    task_list = []
    for t in tasks:
       
        guest_name = "N/A"
        if t.room_unit:
            booking = Booking.objects.filter(
                room_unit=t.room_unit,
                status__in=["checked_in", "checked_out"]
            ).select_related("guest").order_by("-actual_check_in").first()
            if booking and booking.guest:
                guest_name = booking.guest.full_name

        task_list.append({
            "task_id":      t.id,
            "title":        t.title,
            "description":  t.description or "",
            "status":       t.status,
            "room_number":  t.room_unit.room_number if t.room_unit else "N/A",
            "room_status":  t.room_unit.status      if t.room_unit else "N/A",
            "room_type":    t.room.room_type         if t.room     else "N/A",
            "guest_name":   guest_name,
            "created_at":   t.created_at.strftime("%H:%M"),
        })

    status_counts = {
        "Pending":     sum(1 for t in task_list if t["status"] == "Pending"),
        "In Progress": sum(1 for t in task_list if t["status"] == "In Progress"),
        "Completed":   sum(1 for t in task_list if t["status"] == "Completed"),
    }

    # Rooms cleaned (task completed → room became Available)
    rooms_cleaned = [t for t in task_list if t["status"] == "Completed"]

    return {
        "type": "housekeeping",
        "summary": {
            "total_tasks":     len(task_list),
            "pending":         status_counts["Pending"],
            "in_progress":     status_counts["In Progress"],
            "completed":       status_counts["Completed"],
            "rooms_cleaned":   len(rooms_cleaned),
        },
        "activity": task_list,
    }


def _general_report(staff, date_obj):
  
    tasks = Task.objects.filter(
        staff=staff,
        created_at__date=date_obj
    ).select_related("room_unit", "room")

    task_list = [{
        "task_id":     t.id,
        "title":       t.title,
        "description": t.description or "",
        "status":      t.status,
        "room_number": t.room_unit.room_number if t.room_unit else "N/A",
        "created_at":  t.created_at.strftime("%H:%M"),
    } for t in tasks]

    return {
        "type": "general",
        "summary": {
            "total_tasks": len(task_list),
            "completed":   sum(1 for t in task_list if t["status"] == "Completed"),
        },
        "activity": task_list,
    }



def work_report(request):
   
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    staff_id = request.GET.get("staff_id")
    date_str  = request.GET.get("date", timezone.now().date().isoformat())

    if not staff_id:
        return JsonResponse({"error": "staff_id is required"}, status=400)

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

    try:
        staff = Staff.objects.select_related("department", "hotel").get(
            id=staff_id, hotel_id=hotel_id
        )
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    dept_type  = _dept_type(staff)
    attendance = _attendance_for(staff, date_obj)
    shift      = _shift_for(staff, date_obj)

   
    if dept_type == "frontdesk":
        dept_report = _frontdesk_report(staff, date_obj)
    elif dept_type == "housekeeping":
        dept_report = _housekeeping_report(staff, date_obj)
    else:
        dept_report = _general_report(staff, date_obj)

    return JsonResponse({
        "success": True,
        "staff": {
            "id":         staff.id,
            "name":       staff.name,
            "employee_id": getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
            "department": staff.department.name if staff.department else "N/A",
            "role":       getattr(staff, "role", "Staff") or "Staff",
            "dept_type":  dept_type,
        },
        "date":       date_str,
        "shift":      shift,
        "attendance": attendance,
        "report":     dept_report,
    })



def work_report_all(request):
  
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    date_str = request.GET.get("date", timezone.now().date().isoformat())
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"error": "Invalid date format"}, status=400)

    dept_filter = request.GET.get("department", "")  # optional filter

    staffs_qs = Staff.objects.filter(hotel_id=hotel_id).select_related("department")
    if dept_filter:
        staffs_qs = staffs_qs.filter(department__name__icontains=dept_filter)

    results = []
    for staff in staffs_qs:
        dept_type  = _dept_type(staff)
        attendance = _attendance_for(staff, date_obj)
        shift      = _shift_for(staff, date_obj)

        if dept_type == "frontdesk":
            rep = _frontdesk_report(staff, date_obj)
        elif dept_type == "housekeeping":
            rep = _housekeeping_report(staff, date_obj)
        else:
            rep = _general_report(staff, date_obj)

        results.append({
            "staff_id":    staff.id,
            "name":        staff.name,
            "employee_id": getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
            "department":  staff.department.name if staff.department else "N/A",
            "dept_type":   dept_type,
            "shift":       shift,
            "attendance":  attendance,
            "summary":     rep["summary"],
            "dept_type_label": {
                "frontdesk":    "Front Desk",
                "housekeeping": "Housekeeping",
                "hr":           "HR",
                "restaurant":   "Restaurant",
                "general":      "General",
            }.get(dept_type, dept_type.title()),
        })

    return JsonResponse({
        "success": True,
        "date":    date_str,
        "count":   len(results),
        "staff":   results,
    })