from django.shortcuts import render, redirect
from .models import Hotel,Amenity,Room,Department,Staff,Task,Shift,RoomUnit,InventoryItem,Attendance,LeaveRequest,Payroll
from .models import ShiftTemplate
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
from datetime import timedelta,date
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

import json
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import get_object_or_404


def get_shift_templates(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    templates = ShiftTemplate.objects.filter(hotel_id=hotel_id, is_active=True)

    DEFAULTS = {
        "Morning": ("06:00", "14:00", "#d97706"),
        "Evening": ("14:00", "22:00", "#1a65f5"),
        "Night":   ("22:00", "06:00", "#7c3aed"),
    }

    data = {
        t.shift_name: {
            "id":         t.id,
            "shift_name": t.shift_name,
            "start_time": t.start_time.strftime("%H:%M"),
            "end_time":   t.end_time.strftime("%H:%M"),
            "color":      t.color,
        }
        for t in templates
    }

    for name, (start, end, color) in DEFAULTS.items():
        if name not in data:
            data[name] = {
                "id": None, "shift_name": name,
                "start_time": start, "end_time": end, "color": color,
            }

    return JsonResponse({"success": True, "templates": data})


@require_POST
def save_shift_template(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    try:
        body       = json.loads(request.body)
        shift_name = body.get("shift_name", "").strip()
        start_str  = body.get("start_time", "").strip()
        end_str    = body.get("end_time",   "").strip()
        color      = body.get("color", "#1a65f5").strip()

        if not (shift_name and start_str and end_str):
            return JsonResponse({"error": "shift_name, start_time and end_time are required"}, status=400)

        try:
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time   = datetime.strptime(end_str,   "%H:%M").time()
        except ValueError:
            return JsonResponse({"error": "Times must be HH:MM format"}, status=400)

        tpl, created = ShiftTemplate.objects.update_or_create(
            hotel_id=hotel_id,
            shift_name=shift_name,
            defaults={
                "start_time": start_time,
                "end_time":   end_time,
                "color":      color,
                "is_active":  True,
            },
        )

        return JsonResponse({
            "success": True,
            "created": created,
            "template": {
                "id":         tpl.id,
                "shift_name": tpl.shift_name,
                "start_time": tpl.start_time.strftime("%H:%M"),
                "end_time":   tpl.end_time.strftime("%H:%M"),
                "color":      tpl.color,
            },
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_POST
def delete_shift(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    shift_id = request.POST.get("shift_id")
    if not shift_id:
        try:
            shift_id = json.loads(request.body).get("shift_id")
        except (json.JSONDecodeError, AttributeError):
            pass

    if not shift_id:
        return JsonResponse({"error": "shift_id is required"}, status=400)

    try:
        shift_id = int(shift_id)
    except (ValueError, TypeError):
        return JsonResponse({"error": "shift_id must be an integer"}, status=400)

    deleted_count, _ = Shift.objects.filter(id=shift_id, hotel_id=hotel_id).delete()

    if deleted_count == 0:
        return JsonResponse({
            "error": f"Shift #{shift_id} not found for this hotel",
            "debug": {
                "shift_id_received": shift_id,
                "hotel_id":          hotel_id,
                "total_shifts":      Shift.objects.filter(hotel_id=hotel_id).count(),
            },
        }, status=404)

    return JsonResponse({"success": True, "message": f"Shift #{shift_id} deleted"})


def get_shifts(request):
    hotel_id = request.session.get("hotel_id")
    date_str = request.GET.get("date")

    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    shifts = Shift.objects.filter(hotel_id=hotel_id)

    if date_str:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            shifts   = shifts.filter(date=date_obj)
        except ValueError:
            return JsonResponse({"error": "Invalid date format"}, status=400)

    shifts = shifts.select_related("staff", "department")

    templates = {
        t.shift_name: t
        for t in ShiftTemplate.objects.filter(hotel_id=hotel_id, is_active=True)
    }
    DEFAULTS = {
        "Morning": ("06:00", "14:00"),
        "Evening": ("14:00", "22:00"),
        "Night":   ("22:00", "06:00"),
    }

    def resolve(s, which):
        val = s.custom_start if which == "start" else s.custom_end
        if val:
            return val.strftime("%H:%M")
        tpl = templates.get(s.shift)
        if tpl:
            return (tpl.start_time if which == "start" else tpl.end_time).strftime("%H:%M")
        d = DEFAULTS.get(s.shift, ("00:00", "00:00"))
        return d[0] if which == "start" else d[1]

    data = [{
        "id":           s.id,
        "staff":        s.staff.name,
        "staff_id":     s.staff.id,
        "department":   s.department.name,
        "shift":        s.shift,
        "custom_name":  s.custom_name  or "",
        "custom_start": s.custom_start.strftime("%H:%M") if s.custom_start else "",
        "custom_end":   s.custom_end.strftime("%H:%M")   if s.custom_end   else "",
        "custom_color": s.custom_color or "",
        "start_time":   resolve(s, "start"),
        "end_time":     resolve(s, "end"),
        "date":         s.date.strftime("%Y-%m-%d"),
    } for s in shifts]

    return JsonResponse(data, safe=False)


@require_POST
def assign_shift(request):
    try:
        hotel_id      = request.session.get("hotel_id")
        staff_id      = request.POST.get("staff")
        department_id = request.POST.get("department")
        shift_value   = request.POST.get("shift")
        from_date     = request.POST.get("from_date")
        to_date       = request.POST.get("to_date")
        custom_name   = request.POST.get("custom_name",  "").strip()
        custom_start  = request.POST.get("custom_start", "").strip()
        custom_end    = request.POST.get("custom_end",   "").strip()
        custom_color  = request.POST.get("custom_color", "").strip()

        if not hotel_id:
            return JsonResponse({"error": "Login required"}, status=401)

        if not all([staff_id, shift_value, from_date, to_date]):
            return JsonResponse({"error": "Missing required fields"}, status=400)

        start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
        end_date   = datetime.strptime(to_date,   "%Y-%m-%d").date()

        if start_date > end_date:
            return JsonResponse({"error": "Invalid date range"}, status=400)

        if not department_id:
            staff         = get_object_or_404(Staff, id=staff_id)
            department_id = staff.department_id

        if not department_id:
            return JsonResponse({"error": "Department is required"}, status=400)

        parsed_start = None
        parsed_end   = None

        if custom_start:
            try:
                parsed_start = datetime.strptime(custom_start, "%H:%M").time()
            except ValueError:
                return JsonResponse({"error": "custom_start must be HH:MM"}, status=400)

        if custom_end:
            try:
                parsed_end = datetime.strptime(custom_end, "%H:%M").time()
            except ValueError:
                return JsonResponse({"error": "custom_end must be HH:MM"}, status=400)

        if shift_value != "Custom" and not parsed_start:
            try:
                tpl          = ShiftTemplate.objects.get(hotel_id=hotel_id, shift_name=shift_value)
                parsed_start = tpl.start_time
                parsed_end   = tpl.end_time
            except ShiftTemplate.DoesNotExist:
                pass

        current_date  = start_date
        created_count = 0
        updated_count = 0

        while current_date <= end_date:
            _, created = Shift.objects.update_or_create(
                hotel_id=hotel_id,
                staff_id=staff_id,
                date=current_date,
                defaults={
                    "department_id": department_id,
                    "shift":         shift_value,
                    "custom_name":   custom_name  or None,
                    "custom_start":  parsed_start or None,
                    "custom_end":    parsed_end   or None,
                    "custom_color":  custom_color or None,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            current_date += timedelta(days=1)

        return JsonResponse({
            "success": True,
            "message": f"{created_count} shifts created, {updated_count} updated",
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def weekly_schedule(request):
    staff_id   = request.session.get("staff_id")
    hotel_id   = request.session.get("hotel_id")
    start_date = request.GET.get("start_date")

    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    if not hotel_id:
        try:
            current  = Staff.objects.select_related("hotel").get(id=staff_id)
            hotel_id = current.hotel_id
            request.session["hotel_id"] = hotel_id
        except Staff.DoesNotExist:
            return JsonResponse({"error": "Staff not found"}, status=404)

    if not start_date:
        start_date_obj = datetime.today().date()
    else:
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Invalid start_date"}, status=400)

    end_date = start_date_obj + timedelta(days=6)

    shifts = Shift.objects.filter(
        hotel_id=hotel_id,
        date__range=[start_date_obj, end_date]
    ).select_related("staff", "department")

    templates = {
        t.shift_name: t
        for t in ShiftTemplate.objects.filter(hotel_id=hotel_id, is_active=True)
    }
    DEFAULTS = {
        "Morning": ("06:00", "14:00", "#d97706"),
        "Evening": ("14:00", "22:00", "#1a65f5"),
        "Night":   ("22:00", "06:00", "#7c3aed"),
    }

    def get_times(s):
        if s.custom_start:
            return (
                s.custom_start.strftime("%H:%M"),
                s.custom_end.strftime("%H:%M") if s.custom_end else "",
                s.custom_color or "#0891b2",
            )
        tpl = templates.get(s.shift)
        if tpl:
            return tpl.start_time.strftime("%H:%M"), tpl.end_time.strftime("%H:%M"), tpl.color
        d = DEFAULTS.get(s.shift, ("00:00", "00:00", "#6b7280"))
        return d

    data = {
        (start_date_obj + timedelta(days=i)).strftime("%Y-%m-%d"): []
        for i in range(7)
    }

    for s in shifts:
        day        = s.date.strftime("%Y-%m-%d")
        st, et, color = get_times(s)
        data[day].append({
            "id":           s.id,
            "staff":        s.staff.name if s.staff else "N/A",
            "staff_id":     s.staff.id   if s.staff else None,
            "shift":        s.shift,
            "department":   s.department.name if s.department else "N/A",
            "custom_name":  s.custom_name  or "",
            "custom_start": s.custom_start.strftime("%H:%M") if s.custom_start else "",
            "custom_end":   s.custom_end.strftime("%H:%M")   if s.custom_end   else "",
            "custom_color": s.custom_color or "",
            "start_time":   st,
            "end_time":     et,
            "color":        color,
        })

    return JsonResponse({
        "schedule": data,
        "debug": {"hotel_id": hotel_id, "total_shifts": shifts.count()},
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
    shift    = request.GET.get("shift")
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

    data = [{"name": s.staff.name, "role": s.staff.role} for s in staff]

    return JsonResponse(data, safe=False)


@require_GET
def get_weekly_schedule(request):
    staff_id   = request.session.get("staff_id")
    start_date = request.GET.get("start_date")

    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    try:
        staff = Staff.objects.select_related("hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    if not start_date:
        start_date_obj = datetime.today().date()
    else:
        try:
            start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Invalid start_date format. Use YYYY-MM-DD"}, status=400)

    end_date = start_date_obj + timedelta(days=6)

    shifts = Shift.objects.filter(
        staff=staff,
        date__range=[start_date_obj, end_date]
    ).select_related("department").order_by("date", "shift")

    templates = {
        t.shift_name: t
        for t in ShiftTemplate.objects.filter(hotel_id=staff.hotel_id, is_active=True)
    }
    DEFAULTS = {
        "Morning": ("06:00", "14:00", "#d97706"),
        "Evening": ("14:00", "22:00", "#1a65f5"),
        "Night":   ("22:00", "06:00", "#7c3aed"),
    }

    def get_times(s):
        if s.custom_start:
            return (
                s.custom_start.strftime("%H:%M"),
                s.custom_end.strftime("%H:%M") if s.custom_end else "",
                s.custom_color or "#0891b2",
            )
        tpl = templates.get(s.shift)
        if tpl:
            return tpl.start_time.strftime("%H:%M"), tpl.end_time.strftime("%H:%M"), tpl.color
        d = DEFAULTS.get(s.shift, ("00:00", "00:00", "#6b7280"))
        return d

    schedule = {
        (start_date_obj + timedelta(days=i)).strftime("%Y-%m-%d"): []
        for i in range(7)
    }

    for s in shifts:
        day        = s.date.strftime("%Y-%m-%d")
        st, et, color = get_times(s)
        schedule[day].append({
            "id":           s.id,
            "shift":        s.shift,
            "department":   s.department.name if s.department else "N/A",
            "custom_name":  s.custom_name  or "",
            "custom_start": s.custom_start.strftime("%H:%M") if s.custom_start else "",
            "custom_end":   s.custom_end.strftime("%H:%M")   if s.custom_end   else "",
            "custom_color": s.custom_color or "",
            "start_time":   st,
            "end_time":     et,
            "color":        color,
        })

    return JsonResponse({
        "staff_id":     staff.id,
        "staff":        staff.name,
        "week_start":   start_date_obj.strftime("%Y-%m-%d"),
        "week_end":     end_date.strftime("%Y-%m-%d"),
        "schedule":     schedule,
        "total_shifts": shifts.count(),
    })
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
import json
import calendar
from decimal import Decimal
from io import BytesIO

from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

def _sf(v):
    try:
        return float(v) if v not in (None, '', 'None') else 0.0
    except (TypeError, ValueError):
        return 0.0


def _total_days_in_month(month, year):
    return calendar.monthrange(year, month)[1]


def _eligible_days(staff, month, year):
    total = _total_days_in_month(month, year)
    joining = getattr(staff, "joining_date", None) or getattr(staff, "date_joined", None)
    if joining is None:
        return total
    if hasattr(joining, "date"):
        joining = joining.date()
    if joining.year == year and joining.month == month:
        return max(1, total - joining.day + 1)
    return total


def _calculate_payroll(staff, month, year):
    from hotel.models import Attendance, LeaveRequest

    attendances = Attendance.objects.filter(staff=staff, date__month=month, date__year=year)

    absent_days    = attendances.filter(status="Absent").count()
    half_days      = attendances.filter(status="Half Day").count()
    present_days   = attendances.filter(status__in=["Present", "Late"]).count()
    late_days      = attendances.filter(status="Late").count()
    overtime_hours = sum(_sf(a.overtime_hours) for a in attendances)

    approved_leaves = LeaveRequest.objects.filter(
        staff=staff, status="Approved",
        from_date__month=month, from_date__year=year,
    ).count()

    total_days = _total_days_in_month(month, year)
    eligible   = _eligible_days(staff, month, year)
    is_pro_rated = eligible < total_days

    basic_salary = Decimal(str(_sf(staff.salary)))

    if is_pro_rated:
       
        pro_rated_basic = (basic_salary / Decimal(str(total_days))) * Decimal(str(eligible))
    else:
        pro_rated_basic = basic_salary

    
    per_day  = basic_salary / Decimal(str(total_days)) if total_days else Decimal("0")
    per_hour = per_day / Decimal("8")

    
    total_deduct_days  = absent_days + approved_leaves
    absent_deduction   = Decimal(str(total_deduct_days)) * per_day
    half_day_deduction = Decimal(str(half_days)) * (per_day / Decimal("2"))
    overtime_amount    = Decimal(str(overtime_hours)) * Decimal("100")

    return {
        "basic_salary":       basic_salary,
        "pro_rated_basic":    round(pro_rated_basic, 2),
        "total_days":         total_days,
        "eligible_days":      eligible,
        "is_pro_rated":       is_pro_rated,
        "present_days":       present_days,
        "absent_days":        absent_days,
        "half_days":          half_days,
        "late_days":          late_days,
        "overtime_hours":     round(overtime_hours, 2),
        "approved_leaves":    approved_leaves,
        "overtime_amount":    round(overtime_amount, 2),
        "absent_deduction":   round(absent_deduction, 2),
        "half_day_deduction": round(half_day_deduction, 2),
        "per_day_rate":       round(per_day, 2),
        "per_hour_rate":      round(per_hour, 2),
    }


MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def _ensure_payroll_records(hotel_id, month, year):
    from hotel.models import Payroll, Staff

    staffs  = Staff.objects.filter(hotel_id=hotel_id)
    results = []

    for staff in staffs:
        calc        = _calculate_payroll(staff, month, year)
        base_deduct = calc["absent_deduction"] + calc["half_day_deduction"]
        net         = max(calc["pro_rated_basic"] + calc["overtime_amount"] - base_deduct, Decimal("0"))

        p, created = Payroll.objects.get_or_create(
            staff=staff, hotel_id=hotel_id, month=month, year=year,
            defaults={
                "basic_salary":      calc["pro_rated_basic"],
                "overtime_amount":   calc["overtime_amount"],
                "deductions":        base_deduct,
                "net_salary":        net,
                "paid_status":       "Unpaid",
                "bonus":             Decimal("0"),
                "incentive":         Decimal("0"),
                "pf_amount":         Decimal("0"),
                "esi_amount":        Decimal("0"),
                "loan_deduction":    Decimal("0"),
                "tax_deduction":     Decimal("0"),
                "custom_earnings":   [],
                "custom_deductions": [],
            },
        )
        results.append((p, created))

    return results


@csrf_exempt
def generate_payroll(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    try:
        data  = json.loads(request.body)
        month = int(data["month"])
        year  = int(data["year"])
    except (KeyError, ValueError, TypeError) as e:
        return JsonResponse({"error": str(e)}, status=400)

    results       = _ensure_payroll_records(hotel_id, month, year)
    created_count = sum(1 for _, c in results if c)
    updated_count = len(results) - created_count

    return JsonResponse({
        "success": True,
        "message": f"Payroll ready: {created_count} new, {updated_count} already existed.",
        "month":   month,
        "year":    year,
        "total":   len(results),
    })


def payroll_dashboard(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    month = int(request.GET.get("month", timezone.now().month))
    year  = int(request.GET.get("year",  timezone.now().year))

    _ensure_payroll_records(hotel_id, month, year)

    from hotel.models import Payroll, Staff

    staffs   = Staff.objects.filter(hotel_id=hotel_id).select_related("department", "user")
    payrolls = Payroll.objects.filter(hotel_id=hotel_id, month=month, year=year)
    pmap     = {p.staff_id: p for p in payrolls}

    result = []
    for staff in staffs:
        p    = pmap.get(staff.id)
        calc = _calculate_payroll(staff, month, year)

        custom_earn_total   = sum(_sf(e.get("amount")) for e in (p.custom_earnings   or [])) if p else 0
        custom_deduct_total = sum(_sf(d.get("amount")) for d in (p.custom_deductions or [])) if p else 0

        result.append({
            "id":              p.id if p else None,
            "staff":           staff.name,
            "staff_id":        staff.id,
            "employee_id":     getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
            "department":      staff.department.name if staff.department else "—",
            "email":           staff.user.email if (p and staff.user) else "",
            "month":           month,
            "year":            year,
            "basic_salary":    _sf(p.basic_salary)    if p else float(calc["pro_rated_basic"]),
            "original_basic":  _sf(staff.salary),
            "is_pro_rated":    calc["is_pro_rated"],
            "eligible_days":   calc["eligible_days"],
            "total_days":      calc["total_days"],
            "per_day_rate":    float(calc["per_day_rate"]),
            "per_hour_rate":   float(calc["per_hour_rate"]),
            "overtime_amount": _sf(p.overtime_amount) if p else float(calc["overtime_amount"]),
            "bonus":           _sf(p.bonus)           if p else 0,
            "incentive":       _sf(p.incentive)       if p else 0,
            "pf_amount":       _sf(p.pf_amount)       if p else 0,
            "esi_amount":      _sf(p.esi_amount)       if p else 0,
            "loan_deduction":  _sf(p.loan_deduction)  if p else 0,
            "tax_deduction":   _sf(p.tax_deduction)   if p else 0,
            "leave_deduction": float(calc["absent_deduction"] + calc["half_day_deduction"]),
            "absent_deduction":   float(calc["absent_deduction"]),
            "half_day_deduction": float(calc["half_day_deduction"]),
            "deductions":      _sf(p.deductions)      if p else float(calc["absent_deduction"] + calc["half_day_deduction"]),
            "net_salary":      _sf(p.net_salary)      if p else 0,
            "paid_status":     p.paid_status if p else "Unpaid",
            "paid_at":         p.paid_at.strftime("%d %b %Y, %I:%M %p") if (p and p.paid_at) else None,
            "notes":           p.notes if p else "",
            "present_days":       calc["present_days"],
            "absent_days":        calc["absent_days"],
            "half_days":          calc["half_days"],
            "late_days":          calc["late_days"],
            "overtime_hours":     calc["overtime_hours"],
            "approved_leaves":    calc["approved_leaves"],
            "custom_earnings":    p.custom_earnings   if p else [],
            "custom_deductions":  p.custom_deductions if p else [],
        })

    return JsonResponse(result, safe=False)


@csrf_exempt
def update_payroll(request, payroll_id=None, pk=None):
    resolved_id = payroll_id or pk
    if not resolved_id:
        return JsonResponse({"error": "No payroll ID"}, status=400)
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll

    try:
        p = Payroll.objects.select_related("staff").get(id=resolved_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll not found"}, status=404)

    if p.paid_status == "Paid":
        return JsonResponse({"error": "Cannot edit a paid payroll"}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    def dec(key, fallback=Decimal("0")):
        val = data.get(key)
        try:
            return Decimal(str(_sf(val))) if val is not None else fallback
        except Exception:
            return fallback

    p.bonus          = dec("bonus")
    p.incentive      = dec("incentive")
    p.pf_amount      = dec("pf_amount")
    p.esi_amount     = dec("esi_amount")
    p.loan_deduction = dec("loan_deduction")
    p.tax_deduction  = dec("tax_deduction")

    if "leave_deduction" in data:
        p.deductions = max(Decimal("0"), Decimal(str(_sf(data["leave_deduction"]))))

    if "custom_earnings"   in data: p.custom_earnings   = data["custom_earnings"]
    if "custom_deductions" in data: p.custom_deductions = data["custom_deductions"]
    if "notes"             in data: p.notes             = data["notes"]

    custom_earn_total   = sum(_sf(e.get("amount")) for e in (p.custom_earnings   or []))
    custom_deduct_total = sum(_sf(d.get("amount")) for d in (p.custom_deductions or []))

    gross = (
        p.basic_salary + p.overtime_amount + p.bonus + p.incentive
        + Decimal(str(custom_earn_total))
    )
    total_deductions = (
        p.deductions + p.pf_amount + p.esi_amount
        + p.loan_deduction + p.tax_deduction
        + Decimal(str(custom_deduct_total))
    )
    p.net_salary = max(gross - total_deductions, Decimal("0"))
    p.save()

    return JsonResponse({
        "success":          True,
        "net_salary":       float(p.net_salary),
        "gross_salary":     float(gross),
        "total_deductions": float(total_deductions),
    })


@csrf_exempt
def mark_payroll_paid(request, payroll_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    hotel_id = request.session.get("hotel_id")
    staff_id = request.session.get("staff_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll
    from accounts.models import Staff, Hotel

    try:
        p = Payroll.objects.select_related("staff__user", "staff__department", "paid_by").get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll not found"}, status=404)

    if p.paid_status == "Paid":
        return JsonResponse({"error": "Already paid"}, status=400)

    try:
        data           = json.loads(request.body)
        payment_mode   = data.get("payment_mode", "Bank Transfer")
        reference      = data.get("reference", "")
        send_mail_flag = data.get("send_email", True)
    except Exception:
        payment_mode, reference, send_mail_flag = "Bank Transfer", "", True

    p.paid_status = "Paid"
    p.paid_at     = timezone.now()
    if staff_id:
        try:
            p.paid_by = Staff.objects.get(id=staff_id)
        except Staff.DoesNotExist:
            pass
    p.notes = (p.notes or "") + f"\nPaid via {payment_mode}" + (f" | Ref: {reference}" if reference else "")
    p.save()

    mail_sent  = False
    mail_error = None

    if not send_mail_flag:
        mail_error = "Email disabled"
    elif not getattr(p.staff, "user", None):
        mail_error = "Staff has no linked user account"
    elif not p.staff.user.email:
        mail_error = f"No email for {p.staff.name}"
    else:
        try:
            hotel = getattr(p.staff, "hotel", None)
            if hotel is None:
                hotel = Hotel.objects.get(id=hotel_id)
            pdf_bytes = _generate_payslip_pdf(p, hotel)
            _send_payslip_email(p, hotel, payment_mode, reference, pdf_bytes)
            mail_sent = True
        except Exception as e:
            import traceback
            traceback.print_exc()
            mail_error = str(e)

    return JsonResponse({
        "success":     True,
        "paid_status": "Paid",
        "paid_at":     p.paid_at.strftime("%d %b %Y, %I:%M %p"),
        "mail_sent":   mail_sent,
        "mail_error":  mail_error,
        "mail_to":     p.staff.user.email if (p.staff.user and p.staff.user.email) else None,
        "net_salary":  float(p.net_salary),
    })


def payslip(request, payroll_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll, Hotel

    try:
        p = Payroll.objects.select_related(
            "staff__user", "staff__department", "paid_by"
        ).get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll record not found.", "success": False}, status=404)

    calc = _calculate_payroll(p.staff, p.month, p.year)

    custom_earn_total   = sum(_sf(e.get("amount")) for e in (p.custom_earnings   or []))
    custom_deduct_total = sum(_sf(d.get("amount")) for d in (p.custom_deductions or []))

    gross = (
        p.basic_salary + p.overtime_amount + p.bonus + p.incentive
        + Decimal(str(custom_earn_total))
    )
    total_deductions = (
        p.deductions + p.pf_amount + p.esi_amount
        + p.loan_deduction + p.tax_deduction
        + Decimal(str(custom_deduct_total))
    )

    try:
        hotel          = Hotel.objects.get(id=hotel_id)
        hotel_name     = hotel.hotel_name
        hotel_logo_url = hotel.logo.url if hotel.logo else None
        hotel_address  = hotel.address or ""
        hotel_email    = hotel.email or ""
    except Exception:
        hotel_name, hotel_logo_url, hotel_address, hotel_email = "Hotel ERP", None, "", ""

    return JsonResponse({
        "success":            True,
        "id":                 p.id,
        "staff":              p.staff.name,
        "employee_id":        getattr(p.staff, "employee_id", f"EMP{p.staff.id:03d}"),
        "department":         p.staff.department.name if p.staff.department else "—",
        "email":              p.staff.user.email if p.staff.user else "",
        "month":              p.month,
        "year":               p.year,
        "month_label":        MONTH_NAMES[p.month],
        "hotel_name":         hotel_name,
        "hotel_logo_url":     hotel_logo_url,
        "hotel_address":      hotel_address,
        "hotel_email":        hotel_email,
        "basic_salary":       float(p.basic_salary),
        "original_basic":     _sf(p.staff.salary),
        "is_pro_rated":       calc["is_pro_rated"],
        "eligible_days":      calc["eligible_days"],
        "total_days":         calc["total_days"],
        "per_day_rate":       float(calc["per_day_rate"]),
        "per_hour_rate":      float(calc["per_hour_rate"]),
        "overtime_amount":    float(p.overtime_amount),
        "bonus":              float(p.bonus),
        "incentive":          float(p.incentive),
        "gross_salary":       float(gross),
        "custom_earnings":    p.custom_earnings or [],
        "present_days":       calc["present_days"],
        "absent_days":        calc["absent_days"],
        "half_days":          calc["half_days"],
        "late_days":          calc["late_days"],
        "overtime_hours":     calc["overtime_hours"],
        "approved_leaves":    calc["approved_leaves"],
        "leave_deduction":    float(p.deductions),
        "absent_deduction":   float(calc["absent_deduction"]),
        "half_day_deduction": float(calc["half_day_deduction"]),
        "pf_amount":          float(p.pf_amount),
        "esi_amount":         float(p.esi_amount),
        "loan_deduction":     float(p.loan_deduction),
        "tax_deduction":      float(p.tax_deduction),
        "custom_deductions":  p.custom_deductions or [],
        "total_deductions":   float(total_deductions),
        "net_salary":         float(p.net_salary),
        "paid_status":        p.paid_status,
        "paid_at":            p.paid_at.strftime("%d %b %Y, %I:%M %p") if p.paid_at else None,
        "paid_by":            p.paid_by.name if p.paid_by else "—",
        "notes":              p.notes or "",
    })


def download_payslip_pdf(request, payroll_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return HttpResponse("Login required", status=401)

    from hotel.models import Payroll, Hotel

    try:
        p = Payroll.objects.select_related(
            "staff__user", "staff__department", "paid_by"
        ).get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return HttpResponse("Not found", status=404)

    try:
        hotel = Hotel.objects.get(id=hotel_id)
    except Exception:
        hotel = None

    pdf_bytes   = _generate_payslip_pdf(p, hotel)
    month_label = MONTH_NAMES[p.month]
    filename    = f"Payslip_{p.staff.name.replace(' ', '_')}_{month_label}_{p.year}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _generate_payslip_pdf(payroll, hotel):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet
    from io import BytesIO
    from decimal import Decimal

    p = payroll
    styles = getSampleStyleSheet()
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20*mm,
        rightMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )

    month_label = MONTH_NAMES[p.month]
    hotel_name = hotel.hotel_name if hotel else "Hotel ERP"

    story = []
    header_data = []
    logo_img = None

    if hotel and hotel.logo:
        try:
            if hasattr(hotel.logo, "path"):
                logo_img = Image(hotel.logo.path, width=50, height=50)
        except Exception:
            pass

    title = Paragraph(f"<b>{hotel_name}</b>", styles["Title"])
    if logo_img:
        header_data.append([logo_img, title])
    else:
        header_data.append(["", title])

    header_table = Table(header_data, colWidths=[60, 400])
    story.append(header_table)
    story.append(Spacer(1, 5))
    story.append(Paragraph(f"Payslip - {month_label} {p.year}", styles["Heading2"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Employee: {p.staff.name}", styles["Normal"]))
    story.append(Paragraph(f"Employee ID: {getattr(p.staff, 'employee_id', f'EMP{p.staff.id:03d}')}", styles["Normal"]))
    story.append(Paragraph(f"Department: {p.staff.department.name if p.staff.department else '-'}", styles["Normal"]))
    story.append(Paragraph(f"Email: {p.staff.user.email if p.staff.user else '-'}", styles["Normal"]))
    story.append(Spacer(1, 12))

    custom_earnings   = p.custom_earnings   or []
    custom_deductions = p.custom_deductions or []
    custom_earn_total   = sum(_sf(e.get("amount")) for e in custom_earnings)
    custom_deduct_total = sum(_sf(d.get("amount")) for d in custom_deductions)

    gross = float(
        p.basic_salary + p.overtime_amount + p.bonus + p.incentive + Decimal(str(custom_earn_total))
    )
    total_deductions = float(
        p.deductions + p.pf_amount + p.esi_amount +
        p.loan_deduction + p.tax_deduction + Decimal(str(custom_deduct_total))
    )

    story.append(Paragraph("<b>Salary Details</b>", styles["Heading3"]))
    story.append(Spacer(1, 8))

    earnings_rows = [
        ["Basic Salary", f"{float(p.basic_salary):,.2f}"],
        ["Overtime",     f"{float(p.overtime_amount):,.2f}"],
        ["Bonus",        f"{float(p.bonus):,.2f}"],
        ["Incentive",    f"{float(p.incentive):,.2f}"],
    ]
    for e in custom_earnings:
        amt = _sf(e.get("amount"))
        if amt > 0:
            earnings_rows.append([e.get("label", "Allowance"), f"{amt:,.2f}"])
    earnings_rows.append(["Gross Salary", f"{gross:,.2f}"])

    deduction_rows = [
        ["Leave/Absent Deduction", f"{float(p.deductions):,.2f}"],
        ["PF",                     f"{float(p.pf_amount):,.2f}"],
        ["ESI",                    f"{float(p.esi_amount):,.2f}"],
        ["Loan",                   f"{float(p.loan_deduction):,.2f}"],
        ["Tax",                    f"{float(p.tax_deduction):,.2f}"],
    ]
    for d in custom_deductions:
        amt = _sf(d.get("amount"))
        if amt > 0:
            deduction_rows.append([d.get("label", "Deduction"), f"{amt:,.2f}"])
    deduction_rows.append(["Total Deduction", f"{total_deductions:,.2f}"])

    max_len = max(len(earnings_rows), len(deduction_rows))
    while len(earnings_rows)   < max_len: earnings_rows.append(["", ""])
    while len(deduction_rows)  < max_len: deduction_rows.append(["", ""])

    table_data = [["Earnings", "Amount", "Deductions", "Amount"]]
    for i in range(max_len):
        table_data.append([
            earnings_rows[i][0],  earnings_rows[i][1],
            deduction_rows[i][0], deduction_rows[i][1],
        ])

    main_table = Table(table_data, colWidths=[140, 80, 140, 80])
    main_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#ecfdf5")),
        ("BACKGROUND", (2, 1), (3, -1), colors.HexColor("#fef2f2")),
    ]))

    story.append(main_table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"<b>Net Salary: Rs. {float(p.net_salary):,.2f}</b>",
        styles["Heading2"]
    ))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def _send_payslip_email(payroll, hotel, payment_mode, reference, pdf_bytes):
    from django.core.mail import EmailMultiAlternatives
    from email.mime.base import MIMEBase
    from email import encoders
    from django.conf import settings

    p = payroll
    month_label = MONTH_NAMES[p.month]
    subject    = f"Salary Credited - {month_label} {p.year}"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email   = [p.staff.user.email]

    body = f"""Dear {p.staff.name},

Your salary for {month_label} {p.year} has been credited.

Amount: Rs. {float(p.net_salary):,.2f}
Mode: {payment_mode}

Regards,
HR"""

    msg      = EmailMultiAlternatives(subject, body, from_email, to_email)
    filename = f"Payslip_{p.staff.name}_{month_label}_{p.year}.pdf"
    part     = MIMEBase("application", "pdf")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)
    msg.send()
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







FRONT_DESK_KEYWORDS   = ["front desk", "front office", "reception", "fd"]
HOUSEKEEPING_KEYWORDS = ["housekeeping", "hk", "cleaning"]
RESTAURANT_KEYWORDS   = ["restaurant", "f&b", "food", "kitchen", "dining", "bar", "cafe", "fbservice"]


def _dept_type(staff):
    dept = (staff.department.name.lower() if staff.department else "")
    role = (getattr(staff, "role", "") or "").lower()
    combined = dept + " " + role

    if any(k in combined for k in FRONT_DESK_KEYWORDS):
        return "frontdesk"
    if any(k in combined for k in HOUSEKEEPING_KEYWORDS):
        return "housekeeping"
    if any(k in combined for k in RESTAURANT_KEYWORDS):
        return "restaurant"
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
        "check_in":      att.check_in.strftime("%H:%M") if att.check_in else None,
        "check_out":     att.check_out.strftime("%H:%M") if att.check_out else None,
        "status":        att.status,
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
            "check_ins":         checkins.count(),
            "check_outs":        checkouts.count(),
            "new_bookings":      new_bookings.count(),
            "total_actions":     len(activity),
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
            "task_id":     t.id,
            "title":       t.title,
            "description": t.description or "",
            "status":      t.status,
            "room_number": t.room_unit.room_number if t.room_unit else "N/A",
            "room_status": t.room_unit.status      if t.room_unit else "N/A",
            "room_type":   t.room.room_type        if t.room     else "N/A",
            "guest_name":  guest_name,
            "created_at":  t.created_at.strftime("%H:%M"),
        })

    status_counts = {
        "Pending":     sum(1 for t in task_list if t["status"] == "Pending"),
        "In Progress": sum(1 for t in task_list if t["status"] == "In Progress"),
        "Completed":   sum(1 for t in task_list if t["status"] == "Completed"),
    }

    return {
        "type": "housekeeping",
        "summary": {
            "total_tasks":   len(task_list),
            "pending":       status_counts["Pending"],
            "in_progress":   status_counts["In Progress"],
            "completed":     status_counts["Completed"],
            "rooms_cleaned": status_counts["Completed"],
        },
        "activity": task_list,
    }


def _restaurant_report(staff, date_obj):
    from django.db.models import Sum, Count
    from django.db.models.functions import ExtractHour
    from restaurant.models import RestaurantOrder, OrderItem

    EMPTY = {
        "type": "restaurant",
        "summary": {
            "total_orders":          0,
            "total_revenue":         0.0,
            "avg_order_value":       0.0,
            "covers_served":         0,
            "dine_in_orders":        0,
            "room_service_orders":   0,
            "takeaway_orders":       0,
            "dine_in_revenue":       0.0,
            "room_service_revenue":  0.0,
            "takeaway_revenue":      0.0,
            "completed_orders":      0,
            "pending_orders":        0,
            "cancelled_orders":      0,
        },
        "categories": [],
        "top_items":  [],
        "hourly":     [],
        "activity":   [],
    }

    # RestaurantOrder uses `staff` FK to accounts.Staff — filter by this staff
    orders_qs = RestaurantOrder.objects.filter(
        created_at__date=date_obj,
        staff=staff
    ).select_related(
        "table", "room", "booking", "booking__room_unit", "reservation"
    ).order_by("created_at")

    # fallback: show all orders for the date if staff has no direct assignment
    if not orders_qs.exists():
        orders_qs = RestaurantOrder.objects.filter(
            created_at__date=date_obj
        ).select_related(
            "table", "room", "booking", "booking__room_unit", "reservation"
        ).order_by("created_at")

    if not orders_qs.exists():
        return EMPTY

    # ── Totals ──────────────────────────────────────────────────────────
    total_orders    = orders_qs.count()
    total_revenue   = float(orders_qs.aggregate(s=Sum("total_amount"))["s"] or 0)
    avg_order_value = round(total_revenue / total_orders, 2) if total_orders else 0.0

    # covers = sum of reservation.guests_count where available, else table.capacity
    covers_served = 0
    for o in orders_qs:
        if o.reservation_id and o.reservation:
            covers_served += o.reservation.guests_count
        elif o.table_id and o.table:
            covers_served += o.table.capacity

    # ── By order_type ────────────────────────────────────────────────────
    dine_in_qs       = orders_qs.filter(order_type="dine_in")
    room_service_qs  = orders_qs.filter(order_type="room_service")
    takeaway_qs      = orders_qs.filter(order_type="takeaway")

    dine_in_count      = dine_in_qs.count()
    room_service_count = room_service_qs.count()
    takeaway_count     = takeaway_qs.count()

    dine_in_rev      = float(dine_in_qs.aggregate(s=Sum("total_amount"))["s"] or 0)
    room_service_rev = float(room_service_qs.aggregate(s=Sum("total_amount"))["s"] or 0)
    takeaway_rev     = float(takeaway_qs.aggregate(s=Sum("total_amount"))["s"] or 0)

    # ── By status ────────────────────────────────────────────────────────
    # RestaurantOrder.STATUS choices: pending, preparing, served, cancelled
    completed_orders = orders_qs.filter(status="served").count()
    pending_orders   = orders_qs.filter(status__in=["pending", "preparing"]).count()
    cancelled_orders = orders_qs.filter(status="cancelled").count()

    # ── Categories (order type breakdown) ────────────────────────────────
    TYPE_COLOR = {
        "dine_in":      "#1a65f5",
        "room_service": "#7c3aed",
        "takeaway":     "#0891b2",
    }
    TYPE_LABEL = {
        "dine_in":      "Dine-In",
        "room_service": "Room Service",
        "takeaway":     "Takeaway",
    }

    categories = []
    for ot, cnt, rev in [
        ("dine_in",      dine_in_count,      dine_in_rev),
        ("room_service", room_service_count,  room_service_rev),
        ("takeaway",     takeaway_count,      takeaway_rev),
    ]:
        if cnt:
            categories.append({
                "name":    TYPE_LABEL[ot],
                "orders":  cnt,
                "revenue": round(rev, 2),
                "color":   TYPE_COLOR[ot],
            })

    # ── Top items via OrderItem → item (MenuItem) ─────────────────────────
    # OrderItem fields: order, item (FK→MenuItem), quantity, unit_price, note
    # MenuItem fields: name, category (FK→MenuCategory), price, is_veg
    top_items = []
    try:
        item_rows = (
            OrderItem.objects
            .filter(order__in=orders_qs)
            .values("item__name", "item__category__name", "item__is_veg")
            .annotate(
                order_count=Count("id"),
                total_qty=Sum("quantity"),
                revenue=Sum("unit_price"),
            )
            .order_by("-total_qty")[:10]
        )
        for row in item_rows:
            top_items.append({
                "name":     row["item__name"] or "Unknown",
                "category": row["item__category__name"] or "",
                "is_veg":   row["item__is_veg"],
                "orders":   row["order_count"],
                "quantity": row["total_qty"],
                "revenue":  float(row["revenue"] or 0),
            })
    except Exception:
        pass

    # ── Hourly breakdown ─────────────────────────────────────────────────
    hourly = []
    try:
        hourly_rows = (
            orders_qs
            .annotate(hour=ExtractHour("created_at"))
            .values("hour")
            .annotate(orders=Count("id"), revenue=Sum("total_amount"))
            .order_by("hour")
        )
        for h in hourly_rows:
            hourly.append({
                "hour":    h["hour"],
                "orders":  h["orders"],
                "revenue": float(h["revenue"] or 0),
            })
    except Exception:
        pass

    # ── Activity list ────────────────────────────────────────────────────
    STATUS_DISPLAY = {
        "pending":   "Pending",
        "preparing": "Preparing",
        "served":    "Served",
        "cancelled": "Cancelled",
    }

    activity = []
    for o in orders_qs:
        table_ref = ""
        if o.order_type == "dine_in" and o.table:
            table_ref = f"Table {o.table.number}"
        elif o.order_type == "room_service":
            if o.booking and o.booking.room_unit:
                table_ref = f"Room {o.booking.room_unit.room_number}"
            elif o.room:
                table_ref = f"Room {getattr(o.room, 'room_number', str(o.room))}"
            else:
                table_ref = "Room Service"

        covers = 0
        if o.reservation_id and o.reservation:
            covers = o.reservation.guests_count
        elif o.table_id and o.table:
            covers = o.table.capacity

        activity.append({
            "order_id":       o.id,
            "order_number":   o.order_number,
            "type":           o.order_type,
            "typeLabel":      TYPE_LABEL.get(o.order_type, o.order_type.replace("_", " ").title()),
            "table_or_room":  table_ref,
            "covers":         covers,
            "amount":         float(o.total_amount or 0),
            "tax":            float(o.tax_amount or 0),
            "charge_to_room": o.charge_to_room,
            "status":         STATUS_DISPLAY.get(o.status, o.status.title()),
            "status_raw":     o.status,
            "time":           o.created_at.strftime("%H:%M"),
        })

    return {
        "type": "restaurant",
        "summary": {
            "total_orders":          total_orders,
            "total_revenue":         round(total_revenue, 2),
            "avg_order_value":       avg_order_value,
            "covers_served":         covers_served,
            "dine_in_orders":        dine_in_count,
            "room_service_orders":   room_service_count,
            "takeaway_orders":       takeaway_count,
            "dine_in_revenue":       round(dine_in_rev, 2),
            "room_service_revenue":  round(room_service_rev, 2),
            "takeaway_revenue":      round(takeaway_rev, 2),
            "completed_orders":      completed_orders,
            "pending_orders":        pending_orders,
            "cancelled_orders":      cancelled_orders,
        },
        "categories": categories,
        "top_items":  top_items,
        "hourly":     hourly,
        "activity":   activity,
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
    date_str = request.GET.get("date", timezone.now().date().isoformat())

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
    elif dept_type == "restaurant":
        dept_report = _restaurant_report(staff, date_obj)
    else:
        dept_report = _general_report(staff, date_obj)

    return JsonResponse({
        "success": True,
        "staff": {
            "id":          staff.id,
            "name":        staff.name,
            "employee_id": getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
            "department":  staff.department.name if staff.department else "N/A",
            "role":        getattr(staff, "role", "Staff") or "Staff",
            "dept_type":   dept_type,
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

    dept_filter = request.GET.get("department", "")

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
        elif dept_type == "restaurant":
            rep = _restaurant_report(staff, date_obj)
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
                "restaurant":   "Restaurant",
                "hr":           "HR",
                "general":      "General",
            }.get(dept_type, dept_type.title()),
        })

    return JsonResponse({
        "success": True,
        "date":    date_str,
        "count":   len(results),
        "staff":   results,
    })
import json
from decimal import Decimal
from django.shortcuts import render, redirect
from django.http import JsonResponse,HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.db import connection
import csv
from accounts.models import Staff, Department
from hotel.models import Task, Shift, Attendance, LeaveRequest
from pms.models import Booking, Room, RoomUnit
from billing.models import GuestFolio, FolioCharge, Invoice, BillingPayment


def _get_hotel():
    try:
        from django_tenants.utils import schema_context
        from accounts.models import Hotel
        tenant_schema = connection.tenant.schema_name
        with schema_context('public'):
            return Hotel.objects.filter(schema_name=tenant_schema).first()
    except Exception:
        return None

@never_cache
@login_required
def accountant_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    hotel = staff.hotel
    today = timezone.now().date()
    month = today.month
    year  = today.year

    today_payments = BillingPayment.objects.filter(received_at__date=today)
    today_revenue  = today_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    method_revenue = {}
    for mp in today_payments.values("method").annotate(total=Sum("amount")):
        method_revenue[mp["method"]] = float(mp["total"])

    cash_today          = Decimal(str(method_revenue.get("cash", 0)))
    card_today          = Decimal(str(method_revenue.get("card", 0)))
    upi_today           = Decimal(str(method_revenue.get("upi", 0)))
    bank_transfer_today = Decimal(str(method_revenue.get("bank_transfer", 0)))

    try:
        from restaurant.models import RestaurantOrder
        restaurant_today = RestaurantOrder.objects.filter(
            created_at__date=today, status="served"
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

        restaurant_month = RestaurantOrder.objects.filter(
            created_at__month=month, created_at__year=year, status="served"
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

        restaurant_orders_today = RestaurantOrder.objects.filter(
            created_at__date=today
        ).count()

        restaurant_orders_list = []
        for order in RestaurantOrder.objects.select_related(
            "served_by", "table"
        ).filter(created_at__date=today).order_by("-created_at")[:50]:
            local_time = timezone.localtime(order.created_at)
            restaurant_orders_list.append({
                "id":           order.id,
                "table":        str(order.table.number) if order.table else "—",
                "staff_name":   order.served_by.get_full_name() if order.served_by else "—",
                "items_count":  order.items.count() if hasattr(order, "items") else 0,
                "total_amount": float(order.total_amount or 0),
                "status":       order.status,
                "created_at":   local_time.strftime("%d %b %Y, %I:%M %p"),
            })
    except Exception:
        restaurant_today        = Decimal("0")
        restaurant_month        = Decimal("0")
        restaurant_orders_today = 0
        restaurant_orders_list  = []

    room_charges_today = FolioCharge.objects.filter(
        charge_type="room", date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    laundry_today = FolioCharge.objects.filter(
        charge_type="laundry", date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    minibar_today = FolioCharge.objects.filter(
        charge_type="minibar", date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    spa_today = FolioCharge.objects.filter(
        charge_type="spa", date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    transport_today = FolioCharge.objects.filter(
        charge_type="transport", date=today
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    other_charges_today = FolioCharge.objects.filter(
        date=today
    ).exclude(
        charge_type__in=["room", "laundry", "minibar", "spa", "transport"]
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    dept_today_breakdown = [
        {"type": "room",       "label": "Room Charges",  "total": float(room_charges_today),  "icon": "fa-bed"},
        {"type": "restaurant", "label": "Restaurant",    "total": float(restaurant_today),     "icon": "fa-utensils"},
        {"type": "laundry",    "label": "Laundry",       "total": float(laundry_today),        "icon": "fa-tshirt"},
        {"type": "minibar",    "label": "Minibar",       "total": float(minibar_today),        "icon": "fa-wine-glass"},
        {"type": "spa",        "label": "Spa",           "total": float(spa_today),            "icon": "fa-spa"},
        {"type": "transport",  "label": "Transport",     "total": float(transport_today),      "icon": "fa-car"},
        {"type": "other",      "label": "Other",         "total": float(other_charges_today),  "icon": "fa-tag"},
    ]

    monthly_payments = BillingPayment.objects.filter(
        received_at__month=month, received_at__year=year
    )
    monthly_revenue = monthly_payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    open_folios     = GuestFolio.objects.filter(status="open")
    pending_balance = sum(f.balance_due for f in open_folios)

    invoices_qs = Invoice.objects.select_related(
        "folio__booking__guest",
        "folio__booking__room_unit",
        "folio__booking__room",
    ).order_by("-generated_at")

    total_invoices   = invoices_qs.count()
    paid_invoices    = invoices_qs.filter(status="paid").count()
    pending_invoices = invoices_qs.filter(status="pending").count()
    partial_invoices = invoices_qs.filter(status="partial").count()

    month_invoices = invoices_qs.filter(
        generated_at__month=month, generated_at__year=year
    )
    month_grand_total = month_invoices.aggregate(
        total=Sum("grand_total")
    )["total"] or Decimal("0")

    room_type_revenue = []
    for item in FolioCharge.objects.filter(
        date__month=month, date__year=year
    ).values("charge_type").annotate(total=Sum("amount")).order_by("-total"):
        room_type_revenue.append({
            "type":  item["charge_type"],
            "total": float(item["total"]),
        })

    last_30 = today - timedelta(days=29)
    daily_data = BillingPayment.objects.filter(
        received_at__date__gte=last_30
    ).annotate(day=TruncDate("received_at")).values("day").annotate(
        total=Sum("amount")
    ).order_by("day")

    daily_map     = {str(d["day"]): float(d["total"]) for d in daily_data}
    chart_labels  = []
    chart_revenue = []
    for i in range(30):
        day = last_30 + timedelta(days=i)
        chart_labels.append(day.strftime("%d %b"))
        chart_revenue.append(daily_map.get(str(day), 0))

    monthly_trend = BillingPayment.objects.filter(
        received_at__year=year
    ).annotate(month=TruncMonth("received_at")).values("month").annotate(
        total=Sum("amount")
    ).order_by("month")

    month_names     = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    monthly_labels  = [month_names[d["month"].month - 1] for d in monthly_trend]
    monthly_amounts = [float(d["total"]) for d in monthly_trend]

    tax_collected_today = FolioCharge.objects.filter(
        date=today
    ).aggregate(total=Sum("tax_amount"))["total"] or Decimal("0")

    tax_collected_month = FolioCharge.objects.filter(
        date__month=month, date__year=year
    ).aggregate(total=Sum("tax_amount"))["total"] or Decimal("0")

    tax_from_invoices_month = month_invoices.aggregate(
        total=Sum("tax_total")
    )["total"] or Decimal("0")

    settled_today = GuestFolio.objects.filter(
        status="closed", updated_at__date=today
    ).count()

    total_rooms    = RoomUnit.objects.count()
    occupied_rooms = RoomUnit.objects.filter(status="Occupied").count()
    occupancy_rate = round((occupied_rooms / total_rooms * 100) if total_rooms else 0, 1)

    try:
        expected_room_income = Booking.objects.filter(
            status__in=["confirmed", "checked_in"],
            check_out__gte=today
        ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0")

        expected_restaurant_income = restaurant_today

        total_expected = expected_room_income + expected_restaurant_income
    except Exception:
        expected_room_income        = Decimal("0")
        expected_restaurant_income  = Decimal("0")
        total_expected              = Decimal("0")

    recent_invoices = []
    for inv in invoices_qs[:50]:
        folio   = inv.folio
        booking = folio.booking
        guest   = booking.guest if booking else None
        recent_invoices.append({
            "id":              inv.id,
            "invoice_number":  inv.invoice_number,
            "guest_name":      guest.full_name if guest else "—",
            "guest_email":     guest.email     if guest else "",
            "room_number":     booking.room_unit.room_number if booking and booking.room_unit else "—",
            "room_type":       booking.room.room_type        if booking and booking.room      else "—",
            "check_in":        booking.check_in.strftime("%d %b %Y")  if booking and booking.check_in  else "—",
            "check_out":       booking.check_out.strftime("%d %b %Y") if booking and booking.check_out else "—",
            "subtotal":        float(inv.subtotal),
            "tax_total":       float(inv.tax_total),
            "discount":        float(inv.discount),
            "grand_total":     float(inv.grand_total),
            "status":          inv.status,
            "generated_at":    inv.generated_at.strftime("%d %b %Y, %I:%M %p"),
            "generated_date":  inv.generated_at.strftime("%Y-%m-%d"),
            "generated_month": inv.generated_at.strftime("%Y-%m"),
        })

    recent_payments = []
    for pay in BillingPayment.objects.select_related(
        "folio__booking__guest", "received_by",
        "order", "order__table"
    ).order_by("-received_at")[:100]:

        local_time = timezone.localtime(pay.received_at)

        if pay.folio:
            booking    = pay.folio.booking
            guest      = booking.guest if booking else None
            guest_name = guest.full_name if guest else "—"
            booking_id = booking.id if booking else "—"
        elif pay.order:
            order      = pay.order
            guest_name = f"Takeaway #{order.order_number}"
            booking_id = f"Order #{order.order_number}"
        else:
            guest_name = "—"
            booking_id = "—"

        recent_payments.append({
            "id":               pay.id,
            "amount":           float(pay.amount),
            "method":           pay.method or "—",
            "method_label":     pay.get_method_display() if pay.method else "—",
            "reference_number": pay.reference_number or "—",
            "guest_name":       guest_name,
            "booking_id":       booking_id,
            "received_by":      pay.received_by.name if pay.received_by else "System",
            "received_at":      local_time.strftime("%d %b %Y, %I:%M %p"),
            "received_date":    local_time.strftime("%Y-%m-%d"),
            "received_month":   local_time.strftime("%Y-%m"),
            "note":             pay.note or "",
        })

    attendance_qs = Attendance.objects.filter(
        staff=staff, date__month=month, date__year=year
    )
    present_days   = attendance_qs.filter(status="Present").count()
    late_days      = attendance_qs.filter(status="Late").count()
    absent_days    = attendance_qs.filter(status="Absent").count()
    overtime_hours = attendance_qs.aggregate(
        total=Sum("overtime_hours")
    )["total"] or 0

    hotel_staff    = Staff.objects.filter(hotel=hotel).select_related("department")
    departments    = Department.objects.filter(hotel=hotel)
    leave_requests = LeaveRequest.objects.filter(staff=staff).order_by("-applied_at")
    room_units     = RoomUnit.objects.select_related("room").all()
    recent_tasks   = Task.objects.select_related("staff", "room_unit").order_by("-created_at")[:10]

    rooms_qs  = Room.objects.filter(is_active=True).prefetch_related("units")
    room_list = []
    for room in rooms_qs:
        units_qs        = room.units.all().order_by("room_number")
        available_units = units_qs.filter(status="Available").count()
        price           = getattr(room, "base_price", None) or getattr(room, "price", None) or 0
        room_list.append({
            "id":              room.id,
            "room_type":       getattr(room, "room_type", "Unknown"),
            "total_rooms":     units_qs.count(),
            "available_rooms": available_units,
            "price":           float(price),
            "units": [
                {"id": u.id, "number": u.room_number, "status": u.status}
                for u in units_qs
            ],
        })

    context = {
        "staff":          staff,
        "hotel":          hotel,
        "hotel_staff":    hotel_staff,
        "departments":    departments,
        "today":          today,

        "today_revenue":           float(today_revenue),
        "monthly_revenue":         float(monthly_revenue),
        "pending_balance":         float(pending_balance),
        "month_grand_total":       float(month_grand_total),
        "restaurant_today":        float(restaurant_today),
        "restaurant_month":        float(restaurant_month),
        "restaurant_orders_today": restaurant_orders_today,
        "room_charges_today":      float(room_charges_today),
        "laundry_today":           float(laundry_today),
        "minibar_today":           float(minibar_today),
        "spa_today":               float(spa_today),
        "transport_today":         float(transport_today),
        "other_charges_today":     float(other_charges_today),
        "tax_collected_today":     float(tax_collected_today),
        "tax_collected_month":     float(tax_collected_month),
        "tax_invoices_month":      float(tax_from_invoices_month),

        "cash_today":          float(cash_today),
        "card_today":          float(card_today),
        "upi_today":           float(upi_today),
        "bank_transfer_today": float(bank_transfer_today),

        "expected_room_income":       float(expected_room_income),
        "expected_restaurant_income": float(expected_restaurant_income),
        "total_expected":             float(total_expected),

        "dept_today_breakdown": json.dumps(dept_today_breakdown),

        "total_invoices":   total_invoices,
        "paid_invoices":    paid_invoices,
        "pending_invoices": pending_invoices,
        "partial_invoices": partial_invoices,
        "settled_today":    settled_today,

        "total_rooms":    total_rooms,
        "occupied_rooms": occupied_rooms,
        "occupancy_rate": occupancy_rate,

        "method_revenue": json.dumps(method_revenue),
        "dept_revenue":   json.dumps(room_type_revenue),

        "chart_labels":    json.dumps(chart_labels),
        "chart_revenue":   json.dumps(chart_revenue),
        "monthly_labels":  json.dumps(monthly_labels),
        "monthly_amounts": json.dumps(monthly_amounts),

        "recent_invoices":        recent_invoices,
        "recent_payments":        recent_payments,
        "restaurant_orders_list": json.dumps(restaurant_orders_list),

        "present_days":   present_days,
        "late_days":      late_days,
        "absent_days":    absent_days,
        "overtime_hours": float(overtime_hours),
        "leave_requests": leave_requests,

        "rooms_json":  json.dumps(room_list),
        "room_units":  room_units,
        "recent_tasks": recent_tasks,
        "housekeeping_staff": hotel_staff.filter(
            department__name__icontains="housekeeping"
        ),
    }

    return render(request, "accountant.html", context)
@require_GET
def accountant_revenue_api(request):
    today = timezone.now().date()
    month = today.month
    year  = today.year
 
    filter_date  = request.GET.get("date")
    filter_month = request.GET.get("month")
 
    if filter_date:
        try:
            fdate         = date.fromisoformat(filter_date)
            today_payments = BillingPayment.objects.filter(received_at__date=fdate)
            today_revenue  = today_payments.aggregate(total=Sum("amount"))["total"] or 0
            room_charges   = FolioCharge.objects.filter(charge_type="room", date=fdate).aggregate(total=Sum("amount"))["total"] or 0
            tax_today      = FolioCharge.objects.filter(date=fdate).aggregate(total=Sum("tax_amount"))["total"] or 0
            try:
                from restaurant.models import RestaurantOrder
                restaurant_rev = RestaurantOrder.objects.filter(created_at__date=fdate, status="served").aggregate(total=Sum("total_amount"))["total"] or 0
                rest_orders    = RestaurantOrder.objects.filter(created_at__date=fdate).count()
            except Exception:
                restaurant_rev = 0
                rest_orders    = 0
            method_revenue = {}
            for mp in today_payments.values("method").annotate(total=Sum("amount")):
                method_revenue[mp["method"]] = float(mp["total"])
            return JsonResponse({
                "success": True, "filter": "date", "value": filter_date,
                "today_revenue":   float(today_revenue),
                "room_charges":    float(room_charges),
                "restaurant_rev":  float(restaurant_rev),
                "rest_orders":     rest_orders,
                "tax_today":       float(tax_today),
                "cash":            float(method_revenue.get("cash", 0)),
                "card":            float(method_revenue.get("card", 0)),
                "upi":             float(method_revenue.get("upi", 0)),
                "bank_transfer":   float(method_revenue.get("bank_transfer", 0)),
            })
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid date"})
 
    if filter_month:
        try:
            parts  = filter_month.split("-")
            fy, fm = int(parts[0]), int(parts[1])
            monthly_payments = BillingPayment.objects.filter(received_at__month=fm, received_at__year=fy)
            monthly_revenue  = monthly_payments.aggregate(total=Sum("amount"))["total"] or 0
            month_invoices   = Invoice.objects.filter(generated_at__month=fm, generated_at__year=fy)
            month_billed     = month_invoices.aggregate(total=Sum("grand_total"))["total"] or 0
            tax_month        = FolioCharge.objects.filter(date__month=fm, date__year=fy).aggregate(total=Sum("tax_amount"))["total"] or 0
            dept_breakdown   = []
            for item in FolioCharge.objects.filter(date__month=fm, date__year=fy).values("charge_type").annotate(total=Sum("amount")).order_by("-total"):
                dept_breakdown.append({"type": item["charge_type"], "total": float(item["total"])})
            try:
                from restaurant.models import RestaurantOrder
                rest_rev    = RestaurantOrder.objects.filter(created_at__month=fm, created_at__year=fy, status="served").aggregate(total=Sum("total_amount"))["total"] or 0
                rest_orders = RestaurantOrder.objects.filter(created_at__month=fm, created_at__year=fy).count()
            except Exception:
                rest_rev    = 0
                rest_orders = 0
            return JsonResponse({
                "success": True, "filter": "month", "value": filter_month,
                "monthly_revenue": float(monthly_revenue),
                "month_billed":    float(month_billed),
                "tax_month":       float(tax_month),
                "rest_revenue":    float(rest_rev),
                "rest_orders":     rest_orders,
                "dept_breakdown":  dept_breakdown,
            })
        except (ValueError, IndexError):
            return JsonResponse({"success": False, "error": "Invalid month"})
 
    today_payments  = BillingPayment.objects.filter(received_at__date=today)
    today_revenue   = today_payments.aggregate(total=Sum("amount"))["total"] or 0
    monthly_revenue = BillingPayment.objects.filter(received_at__month=month, received_at__year=year).aggregate(total=Sum("amount"))["total"] or 0
    open_folios     = GuestFolio.objects.filter(status="open")
    pending_balance = sum(f.balance_due for f in open_folios)
    method_revenue  = {}
    for mp in today_payments.values("method").annotate(total=Sum("amount")):
        method_revenue[mp["method"]] = float(mp["total"])
    room_charges = FolioCharge.objects.filter(charge_type="room", date=today).aggregate(total=Sum("amount"))["total"] or 0
    try:
        from restaurant.models import RestaurantOrder
        restaurant_today = RestaurantOrder.objects.filter(created_at__date=today, status="served").aggregate(total=Sum("total_amount"))["total"] or 0
    except Exception:
        restaurant_today = 0
    tax_today = FolioCharge.objects.filter(date=today).aggregate(total=Sum("tax_amount"))["total"] or 0
    return JsonResponse({
        "success":             True,
        "today_revenue":       float(today_revenue),
        "monthly_revenue":     float(monthly_revenue),
        "pending_balance":     float(pending_balance),
        "restaurant_today":    float(restaurant_today),
        "room_charges_today":  float(room_charges),
        "tax_today":           float(tax_today),
        "cash_today":          float(method_revenue.get("cash", 0)),
        "card_today":          float(method_revenue.get("card", 0)),
        "upi_today":           float(method_revenue.get("upi", 0)),
        "bank_transfer_today": float(method_revenue.get("bank_transfer", 0)),
    })
@login_required
@require_GET
def accountant_collections_api(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    try:
        staff = Staff.objects.select_related("hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"success": False, "error": "Staff not found"}, status=404)

    filter_date  = request.GET.get("date")
    filter_month = request.GET.get("month")
    filter_staff = request.GET.get("staff_id")

    payments_qs = BillingPayment.objects.select_related(
        "folio__booking__guest", "received_by",
        "received_by__department",
        "folio__booking__room_unit",
        "order", "order__table"
    )
    charges_qs = FolioCharge.objects.all()

    d = fm = fy = None

    if filter_date:
        try:
            d = date.fromisoformat(filter_date)
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid date"})
        payments_qs = payments_qs.filter(received_at__date=d)
        charges_qs  = charges_qs.filter(date=d)
    elif filter_month:
        try:
            parts  = filter_month.split("-")
            fy, fm = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return JsonResponse({"success": False, "error": "Invalid month"})
        payments_qs = payments_qs.filter(received_at__month=fm, received_at__year=fy)
        charges_qs  = charges_qs.filter(date__month=fm, date__year=fy)
    else:
        d = timezone.now().date()
        payments_qs = payments_qs.filter(received_at__date=d)
        charges_qs  = charges_qs.filter(date=d)

    if filter_staff:
        payments_qs = payments_qs.filter(received_by__id=filter_staff)

    total_collection  = float(payments_qs.aggregate(t=Sum("amount"))["t"] or 0)
    transaction_count = payments_qs.count()
    tax_collected     = float(charges_qs.aggregate(t=Sum("tax_amount"))["t"] or 0)

    method_breakdown = {}
    for mp in payments_qs.values("method").annotate(total=Sum("amount")):
        method_breakdown[mp["method"]] = float(mp["total"])

    DEPT_LABELS = {
        "room":       "Room Charges",
        "restaurant": "Restaurant",
        "laundry":    "Laundry",
        "minibar":    "Minibar",
        "spa":        "Spa",
        "transport":  "Transport",
        "other":      "Other",
    }

    charge_type_totals = {}
    for item in charges_qs.values("charge_type").annotate(total=Sum("amount")):
        charge_type_totals[item["charge_type"]] = float(item["total"])

    restaurant_payments = []
    rest_total = 0
    try:
        from restaurant.models import RestaurantOrder
        if d and not fm:
            rest_qs = payments_qs.filter(order__isnull=False, order__order_type="takeaway")
            rest_total = float(rest_qs.aggregate(t=Sum("total_amount"))["t"] or 0)
            for pay in rest_qs.order_by("-received_at")[:100]:
                order      = pay.order
                local_time = timezone.localtime(pay.received_at)
                restaurant_payments.append({
                    "time":         local_time.strftime("%I:%M %p"),
                    "guest":        f"Takeaway #{order.order_number}" if order else "—",
                    "booking":      f"Order #{order.order_number}" if order else "—",
                    "amount":       float(pay.total_amount or pay.amount),
                    "method":       pay.method or "—",
                    "method_label": pay.get_method_display() if pay.method else "—",
                    "staff":        pay.received_by.name if pay.received_by else "—",
                    "reference":    pay.reference_number or "—",
                })
            if not rest_total:
                rest_total = float(
                    RestaurantOrder.objects.filter(
                        created_at__date=d, status="served"
                    ).aggregate(t=Sum("total_amount"))["t"] or 0
                )
        elif fm and fy:
            rest_qs = payments_qs.filter(order__isnull=False, order__order_type="takeaway")
            rest_total = float(rest_qs.aggregate(t=Sum("total_amount"))["t"] or 0)
            for pay in rest_qs.order_by("-received_at")[:100]:
                order      = pay.order
                local_time = timezone.localtime(pay.received_at)
                restaurant_payments.append({
                    "time":         local_time.strftime("%I:%M %p"),
                    "guest":        f"Takeaway #{order.order_number}" if order else "—",
                    "booking":      f"Order #{order.order_number}" if order else "—",
                    "amount":       float(pay.total_amount or pay.amount),
                    "method":       pay.method or "—",
                    "method_label": pay.get_method_display() if pay.method else "—",
                    "staff":        pay.received_by.name if pay.received_by else "—",
                    "reference":    pay.reference_number or "—",
                })
            if not rest_total:
                rest_total = float(
                    RestaurantOrder.objects.filter(
                        created_at__month=fm, created_at__year=fy, status="served"
                    ).aggregate(t=Sum("total_amount"))["t"] or 0
                )
        charge_type_totals["restaurant"] = rest_total
    except Exception:
        pass

    dept_breakdown = []

    for ctype, total in charge_type_totals.items():
        if ctype == "restaurant":
            dept_breakdown.append({
                "type":              "restaurant",
                "label":             "Restaurant",
                "total":             rest_total,
                "transaction_count": len(restaurant_payments),
                "transactions":      restaurant_payments,
            })
            continue

        txs = []
        for pay in payments_qs.filter(folio__charges__charge_type=ctype).distinct().order_by("-received_at")[:100]:
            booking    = pay.folio.booking if pay.folio else None
            guest      = booking.guest if booking else None
            local_time = timezone.localtime(pay.received_at)
            txs.append({
                "time":         local_time.strftime("%I:%M %p"),
                "guest":        guest.full_name if guest else "—",
                "booking":      f"#{booking.id}" if booking else "—",
                "amount":       float(pay.amount),
                "method":       pay.method or "—",
                "method_label": pay.get_method_display() if pay.method else "—",
                "staff":        pay.received_by.name if pay.received_by else "—",
                "reference":    pay.reference_number or "—",
            })
        dept_breakdown.append({
            "type":              ctype,
            "label":             DEPT_LABELS.get(ctype, ctype.title()),
            "total":             total,
            "transaction_count": len(txs),
            "transactions":      txs,
        })

    dept_breakdown.sort(key=lambda x: x["total"], reverse=True)

    staff_breakdown = []
    for row in payments_qs.values(
        "received_by__id",
        "received_by__name",
        "received_by__department__name",
    ).annotate(total=Sum("amount")).order_by("-total"):
        sid = row["received_by__id"]
        staff_methods = {}
        for sm in payments_qs.filter(received_by__id=sid).values("method").annotate(t=Sum("amount")):
            staff_methods[sm["method"]] = float(sm["t"])
        staff_breakdown.append({
            "name":          row["received_by__name"] or "—",
            "department":    row["received_by__department__name"] or "—",
            "cash":          staff_methods.get("cash", 0),
            "card":          staff_methods.get("card", 0),
            "upi":           staff_methods.get("upi", 0),
            "bank_transfer": staff_methods.get("bank_transfer", 0),
            "total":         float(row["total"]),
            "count":         payments_qs.filter(received_by__id=sid).count(),
        })

    return JsonResponse({
        "success":           True,
        "total_collection":  total_collection,
        "transaction_count": transaction_count,
        "tax_collected":     tax_collected,
        "method_breakdown":  method_breakdown,
        "dept_breakdown":    dept_breakdown,
        "staff_breakdown":   staff_breakdown,
    })


@login_required
@require_GET
def accountant_collections_export(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    filter_date  = request.GET.get("date")
    filter_month = request.GET.get("month")
    filter_staff = request.GET.get("staff_id")

    payments_qs = BillingPayment.objects.select_related(
        "folio__booking__guest", "received_by",
        "order"
    )

    if filter_date:
        try:
            d = date.fromisoformat(filter_date)
            payments_qs = payments_qs.filter(received_at__date=d)
            filename = f"collections_{filter_date}.csv"
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid date"})
    elif filter_month:
        try:
            parts  = filter_month.split("-")
            fy, fm = int(parts[0]), int(parts[1])
            payments_qs = payments_qs.filter(received_at__month=fm, received_at__year=fy)
            filename = f"collections_{filter_month}.csv"
        except (ValueError, IndexError):
            return JsonResponse({"success": False, "error": "Invalid month"})
    else:
        d = timezone.now().date()
        payments_qs = payments_qs.filter(received_at__date=d)
        filename = f"collections_{d}.csv"

    if filter_staff:
        payments_qs = payments_qs.filter(received_by__id=filter_staff)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(["#", "Date & Time", "Guest", "Booking", "Amount", "Method", "Reference", "Received By", "Note"])

    for pay in payments_qs.order_by("-received_at"):
        local_time = timezone.localtime(pay.received_at)

        if pay.folio:
            booking    = pay.folio.booking
            guest      = booking.guest if booking else None
            guest_name = guest.full_name if guest else "—"
            booking_ref = f"#{booking.id}" if booking else "—"
        elif pay.order:
            guest_name  = f"Takeaway #{pay.order.order_number}"
            booking_ref = f"Order #{pay.order.order_number}"
        else:
            guest_name  = "—"
            booking_ref = "—"

        writer.writerow([
            pay.id,
            local_time.strftime("%d %b %Y %I:%M %p"),
            guest_name,
            booking_ref,
            float(pay.amount),
            pay.get_method_display() if pay.method else "—",
            pay.reference_number or "—",
            pay.received_by.name if pay.received_by else "—",
            pay.note or "",
        ])

    return response