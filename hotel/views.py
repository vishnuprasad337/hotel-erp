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

from django.utils import timezone

def housekeeping_dashboard(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    staff = Staff.objects.select_related("department").get(id=staff_id)

    my_tasks = Task.objects.filter(
        staff=staff
    ).select_related("room_unit", "room_unit__room")

    seen_ids = set()
    rooms = []
    for task in my_tasks:
        unit = task.room_unit
        if unit and unit.id not in seen_ids:
            seen_ids.add(unit.id)
            rooms.append({
                "id": unit.id,
                "number": unit.room_number,
                "status": unit.status.lower(),
                "room_type": unit.room.room_type if unit.room else "Standard",
                "has_task": True,
            })

    all_units = RoomUnit.objects.all()
    tasks = my_tasks.filter(status="Pending")
    all_tasks = my_tasks

   
    today = timezone.now().date()

    # This month's attendance for the logged-in staff
    monthly_attendance = Attendance.objects.filter(
        staff=staff,
        date__month=today.month,
        date__year=today.year,
    ).order_by("date")

    
    present_days   = monthly_attendance.filter(status__in=["Present", "Late"]).count()
    late_days      = monthly_attendance.filter(status="Late").count()
    absent_days    = monthly_attendance.filter(status="Absent").count()
    overtime_hours = sum(
        float(a.overtime_hours or 0) for a in monthly_attendance
    )

    
    attendance_records = []
    for att in monthly_attendance:
        working_hours = 0.0
        if att.check_in and att.check_out:
            working_hours = round(
                (att.check_out - att.check_in).total_seconds() / 3600, 2
            )
        attendance_records.append({
            "date":          att.date,
            "check_in":      att.check_in.strftime("%H:%M") if att.check_in else "—",
            "check_out":     att.check_out.strftime("%H:%M") if att.check_out else "—",
            "status":        att.status,
            "working_hours": working_hours,
            "overtime":      float(att.overtime_hours or 0),
        })
   
    context = {
        "staff":        staff,
        "rooms":        rooms,
        "tasks":        tasks,
        "all_tasks":    all_tasks,
        "clean_rooms":  all_units.filter(status="Available").count(),
        "dirty_rooms":  all_units.filter(status="Dirty").count(),
        "cleaning_rooms": all_units.filter(status="Cleaning").count(),
        "pending_tasks": tasks.count(),
        "departments":   Department.objects.filter(hotel=staff.hotel).order_by("name"),

       
        "present_days":       present_days,
        "late_days":          late_days,
        "absent_days":        absent_days,
        "overtime_hours":     round(overtime_hours, 2),
        "attendance_records": attendance_records,
        "current_month":      today.strftime("%B %Y"),
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
        staff = Staff.objects.select_related(
            "hotel",
            "department"
        ).get(id=staff_id)

    except Staff.DoesNotExist:
        return redirect("staff_login")

    hotel = staff.hotel
    today = timezone.now().date()

    bookings = Booking.objects.select_related(
        "guest",
        "room",
        "room_unit",
        "created_by"
    ).order_by("-id")

    arrivals = bookings.filter(
        check_in=today,
        status="confirmed"
    )

    departures = bookings.filter(
        check_out=today,
        status="checked_in"
    )

    occupied_rooms = RoomUnit.objects.filter(
        status="Occupied"
    ).count()

    rooms_qs = Room.objects.filter(
        is_active=True
    ).prefetch_related("units")

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

    room_units = RoomUnit.objects.select_related(
        "room"
    ).order_by("room_number")

    hk_dept = Department.objects.filter(
        hotel=hotel,
        name__icontains="housekeeping"
    ).first()

    if hk_dept:
        housekeeping_staff = Staff.objects.filter(
            hotel=hotel,
            department=hk_dept
        ).select_related("department")

    else:
        housekeeping_staff = Staff.objects.filter(
            hotel=hotel
        ).select_related("department")

    hotel_staff = Staff.objects.filter(
        hotel=hotel
    ).select_related("department")

    departments = Department.objects.filter(
        hotel=hotel
    ).prefetch_related(
        Prefetch(
            "staff_set",
            queryset=Staff.objects.filter(
                hotel=hotel
            ).select_related("department"),
            to_attr="employees"
        )
    ).annotate(
        staff_count=Count("staff")
    )

    recent_tasks = Task.objects.filter(
        staff__hotel=hotel
    ).select_related(
        "staff",
        "room_unit",
        "room_unit__room"
    ).order_by("-created_at")[:30]

    shifts = Shift.objects.filter(
        hotel=hotel
    ).select_related(
        "staff",
        "department"
    )

    total_bookings = bookings.count()

    arrivals_count = arrivals.count()

    departures_count = departures.count()

    total_staff = hotel_staff.count()

    total_departments = departments.count()

    schema = (
        getattr(hotel, "schema_name", "")
        or getattr(hotel, "slug", "")
        or str(hotel.id)
    )

    return render(request, "hr.html", {
        "staff": staff,
        "hotel": hotel,
        "bookings": bookings,
        "arrivals": arrivals,
        "departures": departures,
        "arrivals_count": arrivals_count,
        "departures_count": departures_count,
        "total_bookings": total_bookings,
        "occupied_rooms": occupied_rooms,
        "rooms": rooms_qs,
        "rooms_json": rooms_json,
        "room_units": room_units,
        "housekeeping_staff": housekeeping_staff,
        "hotel_staff": hotel_staff,
        "departments": departments,
        "recent_tasks": recent_tasks,
        "shifts": shifts,
        "total_staff": total_staff,
        "total_departments": total_departments,
        "schema": schema,
        "token": "",
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
            
           
            ADMIN_KEYWORDS = ['hr', 'admin', 'manager', 'owner', 'hotel', 'supervisor']
            is_admin = any(k in role or k in dept_name for k in ADMIN_KEYWORDS)
            
            # ✅ Also check if they are the tenant owner/superuser
            if not is_admin and getattr(current_staff, 'is_superuser', False):
                is_admin = True

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
            "leave_type": getattr(l, "leave_type", None) or l.reason or "",  # ✅ Fixed duplicate
            "applied_at": l.applied_at.strftime("%Y-%m-%d") if getattr(l, "applied_at", None) else None,
            "status": l.status,
            "is_admin_view": is_admin,
        })

    return JsonResponse(data, safe=False)
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q

from .models import LeaveRequest


def admin_leave_requests(request):

    try:

        hotel_id = request.session.get("hotel_id")

        if not hotel_id:
            return JsonResponse({
                "success": False,
                "error": "Hotel session not found"
            }, status=400)

        month  = request.GET.get("month")
        year   = request.GET.get("year")
        status = request.GET.get("status")
        search = request.GET.get("search")

        leaves = (
            LeaveRequest.objects
            .filter(staff__hotel_id=hotel_id)
            .select_related("staff", "staff__department")
            .order_by("-applied_at")
        )

        if month:
            leaves = leaves.filter(from_date__month=month)

        if year:
            leaves = leaves.filter(from_date__year=year)

        if status:
            leaves = leaves.filter(status=status)

        if search:
            leaves = leaves.filter(
                Q(staff__name__icontains=search) |
                Q(staff__department__name__icontains=search)
            )

        total    = leaves.count()
        pending  = leaves.filter(status="Pending").count()
        approved = leaves.filter(status="Approved").count()
        rejected = leaves.filter(status="Rejected").count()

        data = []

        for l in leaves:

            data.append({

                "id": l.id,

                "staff": (
                    l.staff.name
                    if l.staff else "Deleted Staff"
                ),

                "staff_id": (
                    l.staff.id
                    if l.staff else None
                ),

                "department": (
                    l.staff.department.name
                    if l.staff and l.staff.department
                    else ""
                ),

                "from_date": (
                    l.from_date.strftime("%Y-%m-%d")
                    if l.from_date else ""
                ),

                "to_date": (
                    l.to_date.strftime("%Y-%m-%d")
                    if l.to_date else ""
                ),

                "reason": l.reason or "",

                "leave_type": (
                    getattr(l, "leave_type", "")
                ),

                "applied_at": (
                    l.applied_at.strftime("%Y-%m-%d %H:%M")
                    if l.applied_at else ""
                ),

                "status": l.status,

                "is_admin_view": True,
            })

        return JsonResponse({

            "success": True,

            "is_admin": True,

            "summary": {
                "total": total,
                "pending": pending,
                "approved": approved,
                "rejected": rejected,
            },

            "leaves": data,
        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@require_POST
def admin_leave_update(request, leave_id):

    try:

        hotel_id = request.session.get("hotel_id")

        if not hotel_id:
            return JsonResponse({
                "success": False,
                "error": "Hotel session not found"
            }, status=400)

        action = request.POST.get("action", "").lower()

        if action not in ["approve", "reject"]:

            return JsonResponse({
                "success": False,
                "error": "Invalid action"
            }, status=400)

        try:

            leave = (
                LeaveRequest.objects
                .select_related("staff")
                .get(
                    id=leave_id,
                    staff__hotel_id=hotel_id
                )
            )

        except LeaveRequest.DoesNotExist:

            return JsonResponse({
                "success": False,
                "error": "Leave request not found"
            }, status=404)

        if leave.status != "Pending":

            return JsonResponse({
                "success": False,
                "error": f"Leave already {leave.status}"
            }, status=400)

        leave.status = (
            "Approved"
            if action == "approve"
            else "Rejected"
        )

        leave.save()

        return JsonResponse({

            "success": True,

            "id": leave.id,

            "status": leave.status,

            "staff": (
                leave.staff.name
                if leave.staff else ""
            ),

            "message": (
                f"Leave {leave.status.lower()} successfully"
            )

        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)
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






from django.utils import timezone
from django.http import JsonResponse
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD LISTS  (shared with messaging / display helpers)
# ─────────────────────────────────────────────────────────────────────────────
FRONT_DESK_KEYWORDS   = ["front desk", "front office", "reception", "fd"]
HOUSEKEEPING_KEYWORDS = ["housekeeping", "hk", "cleaning"]
RESTAURANT_KEYWORDS   = ["restaurant", "f&b", "food", "kitchen", "dining", "bar", "cafe", "fbservice"]
ACCOUNTANT_KEYWORDS   = ["account", "accountant", "finance", "billing", "accounts"]


# ─────────────────────────────────────────────────────────────────────────────
# DEPARTMENT DETECTOR
# ─────────────────────────────────────────────────────────────────────────────
def _dept_type(staff):
    dept     = (staff.department.name.lower() if staff.department else "")
    role     = (getattr(staff, "role", "") or "").lower()
    combined = dept + " " + role

    if any(k in combined for k in FRONT_DESK_KEYWORDS):
        return "frontdesk"
    if any(k in combined for k in HOUSEKEEPING_KEYWORDS):
        return "housekeeping"
    if any(k in combined for k in RESTAURANT_KEYWORDS):
        return "restaurant"
    if any(k in combined for k in ACCOUNTANT_KEYWORDS):
        return "accountant"
    return "general"


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE & SHIFT HELPERS
# ─────────────────────────────────────────────────────────────────────────────
from django.utils import timezone

def _attendance_for(staff, date_obj):
    att = Attendance.objects.filter(
        staff=staff,
        date=date_obj
    ).first()

    if not att:
        return None

    working_hours = 0
    overtime_hours = 0

    if att.check_in:

        # checkout or current local time
        if att.check_out:
            end_time = att.check_out
        else:
            end_time = timezone.now()

        # convert both to local timezone
        check_in = timezone.localtime(att.check_in)
        end_time = timezone.localtime(end_time)

        diff = end_time - check_in

        working_hours = round(diff.total_seconds() / 3600, 2)

        if working_hours < 0:
            working_hours = 0

        overtime_hours = max(0, round(working_hours - 8, 2))

    return {
        "status": att.status,
        "check_in": timezone.localtime(att.check_in).strftime("%I:%M %p") if att.check_in else None,
        "check_out": timezone.localtime(att.check_out).strftime("%I:%M %p") if att.check_out else None,
        "working_hours": working_hours,
        "overtime_hours": overtime_hours,
    }
def _shift_for(staff, date_obj):
    shift = Shift.objects.filter(staff=staff, date=date_obj).first()
    return shift.shift if shift else None


# ─────────────────────────────────────────────────────────────────────────────
# FRONT DESK REPORT  — STAFF-SPECIFIC
# ─────────────────────────────────────────────────────────────────────────────
def _get_booking_staff_fk():
    """
    Inspect the Booking model's fields ONCE and return the first FK field name
    that points to Staff / accounts.Staff.
    Returns None if no such FK exists yet.
    """
    from django.db import models as _models

    # Explicit priority list – add more names here if needed
    CANDIDATES = [
        "handled_by",
        "checked_in_by",
        "created_by",
        "assigned_to",
        "staff",
    ]

    # Build a set of actual field names on Booking for O(1) lookup
    booking_field_names = {f.name for f in Booking._meta.get_fields()}

    for candidate in CANDIDATES:
        if candidate in booking_field_names:
            field = Booking._meta.get_field(candidate)
            # Make sure it's actually a FK/OneToOne (not just a coincidental name)
            if isinstance(field, (_models.ForeignKey, _models.OneToOneField)):
                return candidate

    return None          # No staff FK found on Booking


# Cache the result so we only introspect once per process
_BOOKING_STAFF_FK = None

def _staff_booking_qs(base_qs, staff):
    
    global _BOOKING_STAFF_FK

    if _BOOKING_STAFF_FK is None:
        _BOOKING_STAFF_FK = _get_booking_staff_fk() or "__NONE__"

    fk = _BOOKING_STAFF_FK

    if fk == "__NONE__":
       
        return base_qs

    return base_qs.filter(**{fk: staff})
def _frontdesk_report(staff, date_obj):

    checkins = Booking.objects.filter(
        actual_check_in__date=date_obj,
        status__in=["checked_in", "checked_out"],
        checked_in_by=staff
    ).select_related(
        "guest",
        "room",
        "room_unit",
        "payment"
    )

    checkouts = Booking.objects.filter(
        actual_check_out__date=date_obj,
        status="checked_out",
        checked_out_by=staff
    ).select_related(
        "guest",
        "room",
        "room_unit",
        "payment"
    )

    new_bookings = Booking.objects.filter(
        created_at__date=date_obj,
        created_by=staff
    ).select_related(
        "guest",
        "room",
        "room_unit",
        "payment"
    )

    scheduled_checkins = Booking.objects.filter(
        check_in=date_obj,
        created_by=staff
    ).select_related(
        "guest",
        "room",
        "room_unit",
        "payment"
    )

    def serialize_booking(b, event_type):

        try:
            payment = b.payment
            total = float(payment.total_amount or 0)
            payment_status = payment.payment_status or "pending"
        except Exception:
            total = float(b.total_amount or 0)
            payment_status = "pending"

        return {
            "booking_id": b.id,
            "booking_code": getattr(b, "booking_code", None) or f"BK{b.id:06d}",
            "event": event_type,
            "guest_name": b.guest.full_name if b.guest else "N/A",
            "guest_phone": b.guest.phone if b.guest else "",
            "room_type": b.room.room_type if b.room else "N/A",
            "room_number": b.room_unit.room_number if b.room_unit else "N/A",
            "check_in": b.check_in.isoformat() if b.check_in else None,
            "check_out": b.check_out.isoformat() if b.check_out else None,
            "adults": b.adults,
            "children": b.children,
            "source": b.source or "",
            "status": b.status,
            "total_amount": total,
            "payment_status": payment_status,
            "booked_at": b.created_at.strftime("%H:%M") if b.created_at else None,
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

    for b in scheduled_checkins:
        if b.id not in seen_ids:
            activity.append(serialize_booking(b, "scheduled_check_in"))
            seen_ids.add(b.id)

    activity.sort(key=lambda x: x["booked_at"] or "")

    revenue_today = 0

    for b in checkouts:
        try:
            revenue_today += float(b.payment.total_amount or 0)
        except Exception:
            revenue_today += float(b.total_amount or 0)

    return {
        "type": "frontdesk",
        "summary": {
            "check_ins": checkins.count(),
            "check_outs": checkouts.count(),
            "new_bookings": new_bookings.count(),
            "scheduled_check_ins": scheduled_checkins.count(),
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
            "total_orders":         0,
            "total_revenue":        0.0,
            "avg_order_value":      0.0,
            "covers_served":        0,
            "dine_in_orders":       0,
            "room_service_orders":  0,
            "takeaway_orders":      0,
            "dine_in_revenue":      0.0,
            "room_service_revenue": 0.0,
            "takeaway_revenue":     0.0,
            "completed_orders":     0,
            "pending_orders":       0,
            "cancelled_orders":     0,
        },
        "categories": [],
        "top_items":  [],
        "hourly":     [],
        "activity":   [],
    }

    orders_qs = RestaurantOrder.objects.filter(
        created_at__date=date_obj,
        staff=staff
    ).select_related(
        "table", "room", "booking", "booking__room_unit", "reservation"
    ).order_by("created_at")

    # fallback: all orders for date (restaurants where staff FK not used)
    if not orders_qs.exists():
        orders_qs = RestaurantOrder.objects.filter(
            created_at__date=date_obj
        ).select_related(
            "table", "room", "booking", "booking__room_unit", "reservation"
        ).order_by("created_at")

    if not orders_qs.exists():
        return EMPTY

    total_orders    = orders_qs.count()
    total_revenue   = float(orders_qs.aggregate(s=Sum("total_amount"))["s"] or 0)
    avg_order_value = round(total_revenue / total_orders, 2) if total_orders else 0.0

    covers_served = 0
    for o in orders_qs:
        if o.reservation_id and o.reservation:
            covers_served += o.reservation.guests_count
        elif o.table_id and o.table:
            covers_served += o.table.capacity

    dine_in_qs       = orders_qs.filter(order_type="dine_in")
    room_service_qs  = orders_qs.filter(order_type="room_service")
    takeaway_qs      = orders_qs.filter(order_type="takeaway")

    dine_in_count      = dine_in_qs.count()
    room_service_count = room_service_qs.count()
    takeaway_count     = takeaway_qs.count()

    dine_in_rev      = float(dine_in_qs.aggregate(s=Sum("total_amount"))["s"] or 0)
    room_service_rev = float(room_service_qs.aggregate(s=Sum("total_amount"))["s"] or 0)
    takeaway_rev     = float(takeaway_qs.aggregate(s=Sum("total_amount"))["s"] or 0)

    completed_orders = orders_qs.filter(status="served").count()
    pending_orders   = orders_qs.filter(status__in=["pending", "preparing"]).count()
    cancelled_orders = orders_qs.filter(status="cancelled").count()

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
            "total_orders":         total_orders,
            "total_revenue":        round(total_revenue, 2),
            "avg_order_value":      avg_order_value,
            "covers_served":        covers_served,
            "dine_in_orders":       dine_in_count,
            "room_service_orders":  room_service_count,
            "takeaway_orders":      takeaway_count,
            "dine_in_revenue":      round(dine_in_rev, 2),
            "room_service_revenue": round(room_service_rev, 2),
            "takeaway_revenue":     round(takeaway_rev, 2),
            "completed_orders":     completed_orders,
            "pending_orders":       pending_orders,
            "cancelled_orders":     cancelled_orders,
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
def _accountant_report(date_obj):
    from django.db.models import Sum, Count

    try:
        from billing.models import BillingPayment, FolioCharge, Invoice
        HAS_BILLING = True
    except ImportError:
        HAS_BILLING = False

    try:
        from inventory.models import Expense
        HAS_INVENTORY = True
    except ImportError:
        HAS_INVENTORY = False

    revenue_activity   = []
    total_revenue      = 0.0
    method_totals      = {"cash": 0.0, "card": 0.0, "upi": 0.0, "bank_transfer": 0.0}
    other_payments     = 0.0
    total_transactions = 0

    if HAS_BILLING:
        pay_qs = BillingPayment.objects.filter(
            received_at__date=date_obj,
        ).select_related("folio__booking__guest", "folio__booking__room_unit", "order")

        total_transactions = pay_qs.count()
        total_revenue      = float(pay_qs.aggregate(s=Sum("amount"))["s"] or 0)

        for mp in pay_qs.values("method").annotate(t=Sum("amount")):
            method = (mp["method"] or "other").lower()
            amount = float(mp["t"] or 0)
            if method in method_totals:
                method_totals[method] = amount
            else:
                other_payments += amount

        for pay in pay_qs.order_by("-received_at")[:200]:
            local_t = timezone.localtime(pay.received_at)

            if pay.folio:
                booking    = pay.folio.booking
                guest      = booking.guest if booking else None
                guest_name = guest.full_name if guest else "—"
                ref        = f"#{booking.id}" if booking else "—"
                room_no    = (
                    booking.room_unit.room_number
                    if (booking and booking.room_unit) else "—"
                )
            elif pay.order:
                guest_name = f"Takeaway #{pay.order.order_number}"
                ref        = f"Order #{pay.order.order_number}"
                room_no    = "—"
            else:
                guest_name = "—"
                ref        = "—"
                room_no    = "—"

            revenue_activity.append({
                "payment_id":  pay.id,
                "time":        local_t.strftime("%H:%M"),
                "guest":       guest_name,
                "booking_ref": ref,
                "room_number": room_no,
                "amount":      float(pay.amount),
                "method":      pay.method or "—",
                "reference":   pay.reference_number or "—",
                "note":        pay.note or "",
                "received_by": pay.received_by.name if pay.received_by else "—",
            })

    expense_activity      = []
    total_expenses        = 0.0
    manual_exp_total      = 0.0
    po_exp_total          = 0.0
    maintenance_exp_total = 0.0
    total_expense_count   = 0

    if HAS_INVENTORY:
        exp_qs = Expense.objects.filter(
            expense_date=date_obj,
        ).select_related("department", "expense_category")

        total_expense_count   = exp_qs.count()
        total_expenses        = float(exp_qs.aggregate(s=Sum("amount"))["s"] or 0)
        manual_exp_total      = float(
            exp_qs.filter(source="manual").aggregate(s=Sum("amount"))["s"] or 0
        )
        po_exp_total          = float(
            exp_qs.filter(source="purchase_order").aggregate(s=Sum("amount"))["s"] or 0
        )
        maintenance_exp_total = float(
            exp_qs.filter(source="maintenance").aggregate(s=Sum("amount"))["s"] or 0
        )

        for exp in exp_qs.order_by("expense_date"):
            expense_activity.append({
                "expense_id":  exp.id,
                "department":  exp.department.name if exp.department else "—",
                "category":    exp.expense_category.name if exp.expense_category else "—",
                "source":      exp.source or "manual",
                "description": exp.description or "",
                "amount":      float(exp.amount),
                "recorded_by": exp.recorded_by.name if exp.recorded_by else "—",
            })

    charge_breakdown = []
    if HAS_BILLING:
        try:
            from collections import defaultdict
            type_totals = defaultdict(float)

            for pay in pay_qs:
                if pay.folio:
                    type_totals["room"] += float(pay.amount)
                elif pay.order:
                    type_totals["restaurant"] += float(pay.amount)

            for charge_type, total in sorted(type_totals.items(), key=lambda x: -x[1]):
                charge_breakdown.append({
                    "charge_type": charge_type,
                    "total":       round(total, 2),
                })
        except Exception:
            pass

    invoices_today = []
    if HAS_BILLING:
        try:
            inv_qs = Invoice.objects.filter(
                generated_at__date=date_obj
            ).select_related(
                "folio__booking__guest", "folio__booking__room_unit"
            )
            for inv in inv_qs.order_by("-generated_at")[:50]:
                booking = inv.folio.booking if inv.folio else None
                guest   = booking.guest if booking else None
                invoices_today.append({
                    "invoice_id":     inv.id,
                    "invoice_number": inv.invoice_number,
                    "guest":          guest.full_name if guest else "—",
                    "room_number":    (
                        booking.room_unit.room_number
                        if (booking and booking.room_unit) else "—"
                    ),
                    "grand_total":    float(inv.grand_total),
                    "status":         inv.status,
                    "generated_at":   timezone.localtime(inv.generated_at).strftime("%H:%M"),
                })
        except Exception:
            pass

    net = round(total_revenue - total_expenses, 2)

    return {
        "type": "accountant",
        "summary": {
            "total_revenue_collected": round(total_revenue, 2),
            "cash":                    round(method_totals["cash"], 2),
            "card":                    round(method_totals["card"], 2),
            "upi":                     round(method_totals["upi"], 2),
            "bank_transfer":           round(method_totals["bank_transfer"], 2),
            "other_payments":          round(other_payments, 2),
            "total_transactions":      total_transactions,
            "total_expenses_recorded": round(total_expenses, 2),
            "manual_expenses":         round(manual_exp_total, 2),
            "po_expenses":             round(po_exp_total, 2),
            "maintenance_expenses":    round(maintenance_exp_total, 2),
            "total_expense_count":     total_expense_count,
            "net":                     net,
        },
        "charge_breakdown": charge_breakdown,
        "invoices_today":   invoices_today,
        "revenue_activity": revenue_activity,
        "expense_activity": expense_activity,
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
    elif dept_type == "accountant":
        dept_report = _accountant_report( date_obj)
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

    DEPT_TYPE_LABELS = {
        "frontdesk":    "Front Desk",
        "housekeeping": "Housekeeping",
        "restaurant":   "Restaurant",
        "accountant":   "Accountant",
        "hr":           "HR",
        "general":      "General",
    }

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
        elif dept_type == "accountant":
            rep = _accountant_report(date_obj)
        else:
            rep = _general_report(staff, date_obj)

        results.append({
            "staff_id":        staff.id,
            "name":            staff.name,
            "employee_id":     getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
            "department":      staff.department.name if staff.department else "N/A",
            "dept_type":       dept_type,
            "dept_type_label": DEPT_TYPE_LABELS.get(dept_type, dept_type.title()),
            "shift":           shift,
            "attendance":      attendance,
            "summary":         rep["summary"],
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
 
    # ── RESTAURANT BLOCK ──────────────────────────────────────────────────────
    # Collects all restaurant orders for the period, grouped by order_type
    # (dine_in / room_service / takeaway). Room service entries carry room number,
    # guest name, booking id, and a flag indicating the order was placed on the
    # same day as the guest's check-out (is_checkout_charge).
    restaurant_payments = []
    rest_total = 0
    try:
        from restaurant.models import RestaurantOrder
 
        if d and not fm:
            rest_orders_qs = RestaurantOrder.objects.filter(
                created_at__date=d
            ).select_related(
                "table", "booking", "booking__room_unit",
                "booking__guest", "staff"
            )
        elif fm and fy:
            rest_orders_qs = RestaurantOrder.objects.filter(
                created_at__month=fm, created_at__year=fy
            ).select_related(
                "table", "booking", "booking__room_unit",
                "booking__guest", "staff"
            )
        else:
            rest_orders_qs = RestaurantOrder.objects.none()
 
        rest_total = float(
            rest_orders_qs.filter(status="served")
            .aggregate(t=Sum("total_amount"))["t"] or 0
        )
 
        for order in rest_orders_qs.order_by("-created_at")[:300]:
            local_time = timezone.localtime(order.created_at)
 
            room_number        = None
            room_unit_id       = None
            booking_id         = None
            guest_name         = None
            is_checkout_charge = False
 
            if order.order_type == "room_service" and order.booking:
                bk         = order.booking
                booking_id = bk.id
                if bk.room_unit:
                    room_number  = bk.room_unit.room_number
                    room_unit_id = bk.room_unit.id
                if bk.guest:
                    guest_name = bk.guest.full_name
                if bk.check_out:
                    checkout_day = (
                        bk.check_out.date()
                        if hasattr(bk.check_out, "date")
                        else bk.check_out
                    )
                    order_day = order.created_at.date()
                    is_checkout_charge = (order_day == checkout_day)
            elif order.order_type == "dine_in":
                guest_name = f"Table {order.table.number}" if order.table else "Dine-In"
            elif order.order_type == "takeaway":
                guest_name = f"Takeaway #{order.order_number}"
 
            restaurant_payments.append({
                "time":               local_time.strftime("%I:%M %p"),
                "guest":              guest_name or "—",
                "booking":            f"#{booking_id}" if booking_id else (order.order_number or "—"),
                "amount":             float(order.total_amount or 0),
                "tax":                float(order.tax_amount or 0) if hasattr(order, "tax_amount") else 0,
                "method":             getattr(order, "payment_method", None) or "—",
                "method_label":       (
                    order.get_payment_method_display()
                    if hasattr(order, "get_payment_method_display")
                    else "—"
                ),
                "staff":              order.staff.get_full_name() if order.staff else "—",
                "reference":          order.order_number or "—",
                "order_type":         order.order_type,
                "order_type_label":   order.order_type.replace("_", " ").title(),
                "room_number":        room_number,
                "room_unit_id":       room_unit_id,
                "booking_id":         booking_id,
                "is_checkout_charge": is_checkout_charge,
                "charge_to_room":     getattr(order, "charge_to_room", False),
                "status":             order.status,
            })
 
        charge_type_totals["restaurant"] = rest_total
 
    except Exception:
        import traceback
        traceback.print_exc()
 
    # ── BUILD dept_breakdown ──────────────────────────────────────────────────
    dept_breakdown = []
 
    for ctype, total in charge_type_totals.items():
 
        # ── RESTAURANT ───────────────────────────────────────────────────────
        if ctype == "restaurant":
            dine_in_list      = [t for t in restaurant_payments if t["order_type"] == "dine_in"]
            room_service_list = [t for t in restaurant_payments if t["order_type"] == "room_service"]
            takeaway_list     = [t for t in restaurant_payments if t["order_type"] == "takeaway"]
            checkout_list     = [t for t in restaurant_payments if t.get("is_checkout_charge")]
 
            dept_breakdown.append({
                "type":              "restaurant",
                "label":             "Restaurant",
                "total":             rest_total,
                "transaction_count": len(restaurant_payments),
                "transactions":      restaurant_payments,
                "sub_breakdown": {
                    "dine_in": {
                        "count": len(dine_in_list),
                        "total": sum(t["amount"] for t in dine_in_list),
                        "items": dine_in_list,
                    },
                    "room_service": {
                        "count":          len(room_service_list),
                        "total":          sum(t["amount"] for t in room_service_list),
                        "checkout_count": len(checkout_list),
                        "checkout_total": sum(t["amount"] for t in checkout_list),
                        "items":          room_service_list,
                    },
                    "takeaway": {
                        "count": len(takeaway_list),
                        "total": sum(t["amount"] for t in takeaway_list),
                        "items": takeaway_list,
                    },
                },
            })
            continue
 
        # ── ROOM CHARGES — with restaurant-billed-to-room sub-breakdown ──────
        if ctype == "room":
            # Collect all room-service orders that were charged to the room folio
            room_service_billed       = []
            room_service_billed_total = 0.0
            # Group by room number so the UI can show per-room summaries
            room_service_by_room      = {}   # room_number → {total, count, items[]}
 
            try:
                from restaurant.models import RestaurantOrder
 
                if d and not fm:
                    rs_qs = RestaurantOrder.objects.filter(
                        created_at__date=d,
                        order_type="room_service",
                        charge_to_room=True,
                    ).select_related(
                        "booking", "booking__room_unit", "booking__guest", "staff"
                    )
                elif fm and fy:
                    rs_qs = RestaurantOrder.objects.filter(
                        created_at__month=fm,
                        created_at__year=fy,
                        order_type="room_service",
                        charge_to_room=True,
                    ).select_related(
                        "booking", "booking__room_unit", "booking__guest", "staff"
                    )
                else:
                    rs_qs = RestaurantOrder.objects.none()
 
                room_service_billed_total = float(
                    rs_qs.aggregate(t=Sum("total_amount"))["t"] or 0
                )
 
                for order in rs_qs.order_by("-created_at"):
                    local_time = timezone.localtime(order.created_at)
                    bk         = order.booking
                    room_num   = bk.room_unit.room_number if bk and bk.room_unit else None
                    guest_name = bk.guest.full_name if bk and bk.guest else "—"
                    amount     = float(order.total_amount or 0)
 
                    # Checkout flag
                    is_checkout = False
                    if bk and bk.check_out:
                        checkout_day = (
                            bk.check_out.date()
                            if hasattr(bk.check_out, "date")
                            else bk.check_out
                        )
                        is_checkout = (order.created_at.date() == checkout_day)
 
                    row = {
                        "time":               local_time.strftime("%I:%M %p"),
                        "guest":              guest_name,
                        "room_number":        room_num,
                        "booking_id":         bk.id if bk else None,
                        "order_number":       order.order_number or "—",
                        "amount":             amount,
                        "tax":                float(order.tax_amount or 0) if hasattr(order, "tax_amount") else 0,
                        "status":             order.status,
                        "staff":              order.staff.get_full_name() if order.staff else "—",
                        "is_checkout_charge": is_checkout,
                    }
                    room_service_billed.append(row)
 
                    # Accumulate per-room summary
                    key = room_num or "Unknown"
                    if key not in room_service_by_room:
                        room_service_by_room[key] = {
                            "room_number": room_num,
                            "total":       0.0,
                            "count":       0,
                            "items":       [],
                        }
                    room_service_by_room[key]["total"] += amount
                    room_service_by_room[key]["count"] += 1
                    room_service_by_room[key]["items"].append(row)
 
            except Exception:
                import traceback
                traceback.print_exc()
 
            # Standard room-charge payment transactions (existing logic)
            txs = []
            for pay in payments_qs.filter(
                folio__charges__charge_type="room"
            ).distinct().order_by("-received_at")[:100]:
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
                "type":              "room",
                "label":             "Room Charges",
                "total":             total,
                "transaction_count": len(txs),
                "transactions":      txs,
                # ── new fields ────────────────────────────────────────────────
                "room_service_billed":         room_service_billed,
                "room_service_billed_total":   room_service_billed_total,
                "room_service_billed_count":   len(room_service_billed),
                "room_service_by_room":        list(room_service_by_room.values()),
            })
            continue
 
        # ── ALL OTHER CHARGE TYPES (laundry, minibar, spa, transport, other) ─
        txs = []
        for pay in payments_qs.filter(
            folio__charges__charge_type=ctype
        ).distinct().order_by("-received_at")[:100]:
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
 
    # ── STAFF BREAKDOWN ───────────────────────────────────────────────────────
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
import json
from decimal import Decimal
from datetime import date, timedelta

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
import csv

from accounts.models import Staff, Department
from hotel.models import Task
from inventory.models import (
    Expense, ExpenseCategory,
    PurchaseOrder, PurchaseItem,
    MaintenanceLog, InventoryItem,
    StockAdjustment,
)


# ─────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────

def _parse_period(request):
  
    filter_date  = request.GET.get("date")
    filter_month = request.GET.get("month")

    if filter_date:
        try:
            d = date.fromisoformat(filter_date)
            return d, None, None
        except ValueError:
            pass

    if filter_month:
        try:
            parts = filter_month.split("-")
            return None, int(parts[1]), int(parts[0])
        except (ValueError, IndexError):
            pass

    return timezone.now().date(), None, None


def _apply_period(qs, field, d, month, year):
    
    if d:
        return qs.filter(**{f"{field}__date": d}) if "__date" not in field else qs.filter(**{field: d})
    return qs.filter(**{f"{field}__month": month, f"{field}__year": year})


# ─────────────────────────────────────────────────────────────
# 1. EXPENSE REPORT PAGE  (renders accountant_expense.html)
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def expense_report_view(request):
    
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return redirect("staff_login")

    try:
        staff = Staff.objects.select_related("department", "hotel").get(id=staff_id)
    except Staff.DoesNotExist:
        return redirect("staff_login")

    hotel       = staff.hotel
    today       = timezone.now().date()
    departments = Department.objects.filter(hotel=hotel)
    categories  = ExpenseCategory.objects.all()

    context = {
        "staff":       staff,
        "hotel":       hotel,
        "today":       today,
        "departments": departments,
        "categories":  categories,
    }
    return render(request, "accountant_expense.html", context)


# ─────────────────────────────────────────────────────────────
# 2. EXPENSE REPORT API  (JSON — called by the page via fetch)
# ─────────────────────────────────────────────────────────────

@login_required
@require_GET
def expense_report_api(request):
    
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    d, month, year = _parse_period(request)

    dept_filter     = request.GET.get("department_id")
    category_filter = request.GET.get("category_id")
    source_filter   = request.GET.get("source")

    # ── Base Expense queryset ─────────────────────────────────
    exp_qs = Expense.objects.select_related(
        "department", "expense_category",
        "purchase_order", "purchase_order__vendor",
        "maintenance_log", "maintenance_log__asset",
        "recorded_by",
    )

    if d:
        exp_qs = exp_qs.filter(expense_date=d)
    else:
        exp_qs = exp_qs.filter(expense_date__month=month, expense_date__year=year)

    if dept_filter:
        exp_qs = exp_qs.filter(department_id=dept_filter)
    if category_filter:
        exp_qs = exp_qs.filter(expense_category_id=category_filter)
    if source_filter:
        exp_qs = exp_qs.filter(source=source_filter)

    # ── Summary totals ────────────────────────────────────────
    total          = float(exp_qs.aggregate(t=Sum("amount"))["t"] or 0)
    po_qs          = exp_qs.filter(source="purchase_order")
    maint_qs       = exp_qs.filter(source="maintenance")
    manual_qs      = exp_qs.filter(source="manual")

    po_total        = float(po_qs.aggregate(t=Sum("amount"))["t"] or 0)
    maint_total     = float(maint_qs.aggregate(t=Sum("amount"))["t"] or 0)
    manual_total    = float(manual_qs.aggregate(t=Sum("amount"))["t"] or 0)

    summary = {
        "total":              total,
        "po_total":           po_total,
        "maintenance_total":  maint_total,
        "manual_total":       manual_total,
        "po_count":           po_qs.count(),
        "maintenance_count":  maint_qs.count(),
        "manual_count":       manual_qs.count(),
    }

    # ── By department ─────────────────────────────────────────
    by_dept = []
    for row in exp_qs.values("department__id", "department__name").annotate(
        total=Sum("amount"), count=Count("id")
    ).order_by("-total"):
        did = row["department__id"]
        sub = exp_qs.filter(department_id=did)
        by_dept.append({
            "dept_id":    did,
            "department": row["department__name"] or "Unassigned",
            "total":      float(row["total"]),
            "count":      row["count"],
            "by_source": {
                "manual":         float(sub.filter(source="manual").aggregate(t=Sum("amount"))["t"] or 0),
                "purchase_order": float(sub.filter(source="purchase_order").aggregate(t=Sum("amount"))["t"] or 0),
                "maintenance":    float(sub.filter(source="maintenance").aggregate(t=Sum("amount"))["t"] or 0),
            },
        })

    # ── By category ───────────────────────────────────────────
    by_cat = []
    for row in exp_qs.values("expense_category__name").annotate(
        total=Sum("amount"), count=Count("id")
    ).order_by("-total"):
        by_cat.append({
            "category": row["expense_category__name"] or "Uncategorised",
            "total":    float(row["total"]),
            "count":    row["count"],
        })

    # ── By source ─────────────────────────────────────────────
    by_source = []
    for row in exp_qs.values("source").annotate(
        total=Sum("amount"), count=Count("id")
    ).order_by("-total"):
        by_source.append({
            "source": row["source"] or "manual",
            "total":  float(row["total"]),
            "count":  row["count"],
        })

    # ── Purchase order detail ─────────────────────────────────
    po_ids = po_qs.values_list("purchase_order_id", flat=True).distinct()
    po_list = []
    for po in PurchaseOrder.objects.filter(id__in=po_ids).select_related(
        "vendor", "department", "ordered_by", "approved_by"
    ).prefetch_related("items__item"):
        items = []
        for pi in po.items.select_related("item"):
            items.append({
                "item":       pi.item.name,
                "unit":       pi.item.unit,
                "qty":        float(pi.quantity),
                "unit_price": float(pi.unit_price),
                "subtotal":   float(pi.quantity * pi.unit_price),
            })
        po_list.append({
            "po_id":       po.id,
            "vendor":      po.vendor.name,
            "department":  po.department.name if po.department else "—",
            "total":       float(po.total_amount),
            "status":      po.status,
            "ordered_by":  str(po.ordered_by) if po.ordered_by else "—",
            "approved_by": str(po.approved_by) if po.approved_by else "—",
            "ordered_at":  po.ordered_at.strftime("%d %b %Y") if po.ordered_at else "—",
            "received_at": po.received_at.strftime("%d %b %Y") if po.received_at else "—",
            "items_count": len(items),
            "items":       items,
        })

   
    maint_ids = maint_qs.values_list("maintenance_log_id", flat=True).distinct()
    maint_list = []
    for log in MaintenanceLog.objects.filter(id__in=maint_ids).select_related(
        "asset", "asset__department", "department", "recorded_by"
    ):
        maint_list.append({
            "id":             log.id,
            "asset":          log.asset.name if log.asset else log.custom_asset or "—",
            "department":     (
                log.department.name if log.department_id
                else (log.asset.department.name if log.asset and log.asset.department else "—")
            ),
            "type":           log.maintenance_type,
            "priority":       log.priority,
            "status":         log.status,
            "description":    log.description,
            "location":       log.location,
            "performed_by":   log.performed_by,
            "performed_at":   log.performed_at.strftime("%d %b %Y, %I:%M %p") if log.performed_at else "—",
            "cost":           float(log.cost),
            "labour_cost":    float(log.labour_cost),
            "parts_cost":     float(log.parts_cost),
            "parts_replaced": log.parts_replaced,
            "notes":          log.notes,
            "duration":       log.duration,
        })

    # ── Manual expense detail ─────────────────────────────────
    manual_list = []
    for exp in manual_qs.order_by("-expense_date"):
        manual_list.append({
            "id":          exp.id,
            "date":        str(exp.expense_date),
            "department":  exp.department.name if exp.department else "—",
            "category":    exp.expense_category.name if exp.expense_category else "—",
            "source":      exp.source,
            "description": exp.description,
            "amount":      float(exp.amount),
            "recorded_by": str(exp.recorded_by) if exp.recorded_by else "—",
        })

    # ── Unified transaction list ──────────────────────────────
    transactions = []
    for exp in exp_qs.order_by("-expense_date"):
        row = {
            "id":          exp.id,
            "date":        str(exp.expense_date),
            "department":  exp.department.name if exp.department else "—",
            "category":    exp.expense_category.name if exp.expense_category else "—",
            "source":      exp.source or "manual",
            "description": exp.description,
            "amount":      float(exp.amount),
            "recorded_by": str(exp.recorded_by) if exp.recorded_by else "—",
            "ref":         (
                f"PO-{exp.purchase_order_id}" if exp.purchase_order_id
                else f"ML-{exp.maintenance_log_id}" if exp.maintenance_log_id
                else "—"
            ),
        }
        transactions.append(row)

    return JsonResponse({
        "success":          True,
        "summary":          summary,
        "by_department":    by_dept,
        "by_category":      by_cat,
        "by_source":        by_source,
        "purchase_orders":  po_list,
        "maintenance_logs": maint_list,
        "manual_expenses":  manual_list,
        "transactions":     transactions,
    })



@login_required
@require_GET
def expense_export_csv(request):
   
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    d, month, year = _parse_period(request)
    dept_filter    = request.GET.get("department_id")
    source_filter  = request.GET.get("source")

    exp_qs = Expense.objects.select_related(
        "department", "expense_category", "purchase_order",
        "purchase_order__vendor", "maintenance_log", "recorded_by",
    )

    if d:
        exp_qs = exp_qs.filter(expense_date=d)
        filename = f"expenses_{d}.csv"
    else:
        exp_qs = exp_qs.filter(expense_date__month=month, expense_date__year=year)
        filename = f"expenses_{year}-{str(month).zfill(2)}.csv"

    if dept_filter:
        exp_qs = exp_qs.filter(department_id=dept_filter)
    if source_filter:
        exp_qs = exp_qs.filter(source=source_filter)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        "#", "Date", "Department", "Category", "Source",
        "Reference", "Description", "Amount", "Recorded By",
    ])

    for exp in exp_qs.order_by("-expense_date"):
        ref = (
            f"PO-{exp.purchase_order_id}" if exp.purchase_order_id
            else f"ML-{exp.maintenance_log_id}" if exp.maintenance_log_id
            else "—"
        )
        writer.writerow([
            exp.id,
            str(exp.expense_date),
            exp.department.name if exp.department else "—",
            exp.expense_category.name if exp.expense_category else "—",
            exp.source or "manual",
            ref,
            exp.description,
            float(exp.amount),
            str(exp.recorded_by) if exp.recorded_by else "—",
        ])

    return response


# ─────────────────────────────────────────────────────────────
# 4. ADD MANUAL EXPENSE  (AJAX POST from accountant page)
# ─────────────────────────────────────────────────────────────

@csrf_exempt
@login_required
def expense_add(request):
    
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    try:
        staff = Staff.objects.get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"success": False, "error": "Staff not found"}, status=404)

    import json as _json
    data = _json.loads(request.body)

    exp = Expense.objects.create(
        department_id=data.get("department_id"),
        expense_category_id=data.get("expense_category_id"),
        source=data.get("source", "manual"),
        amount=Decimal(str(data["amount"])),
        description=data.get("description", ""),
        expense_date=data.get("expense_date", timezone.now().date()),
        recorded_by=staff,
    )

    return JsonResponse({"success": True, "id": exp.id}, status=201)


# ─────────────────────────────────────────────────────────────
# 5. DELETE EXPENSE  (AJAX POST)
# ─────────────────────────────────────────────────────────────

@csrf_exempt
@login_required
@require_POST
def expense_delete(request, expense_id):
   
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    try:
        exp = Expense.objects.get(id=expense_id)
        exp.delete()
        return JsonResponse({"success": True})
    except Expense.DoesNotExist:
        return JsonResponse({"success": False, "error": "Expense not found"}, status=404)




@login_required
@require_GET
def expense_summary_api(request):
    
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"success": False, "error": "Not authenticated"}, status=401)

    d, month, year = _parse_period(request)

    exp_qs = Expense.objects.all()
    if d:
        exp_qs = exp_qs.filter(expense_date=d)
    else:
        exp_qs = exp_qs.filter(expense_date__month=month, expense_date__year=year)

    by_dept = [
        {
            "department": r["department__name"] or "Unassigned",
            "total": float(r["total"]),
            "count": r["count"],
        }
        for r in exp_qs.values("department__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    ]

    by_cat = [
        {
            "category": r["expense_category__name"] or "Uncategorised",
            "total": float(r["total"]),
            "count": r["count"],
        }
        for r in exp_qs.values("expense_category__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    ]

    grand_total = float(exp_qs.aggregate(t=Sum("amount"))["t"] or 0)

    return JsonResponse({
        "success":        True,
        "grand_total":    grand_total,
        "by_department":  by_dept,
        "by_category":    by_cat,
    })
@csrf_exempt
@login_required
@require_POST
def expense_update(request, expense_id):

    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({
            "success": False,
            "error": "Not authenticated"
        }, status=401)

    try:
        exp = Expense.objects.get(id=expense_id)
    except Expense.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Expense not found"
        }, status=404)

    import json as _json
    data = _json.loads(request.body)

    exp.department_id = data.get(
        "department_id",
        exp.department_id
    )

    exp.expense_category_id = data.get(
        "expense_category_id",
        exp.expense_category_id
    )

    exp.source = data.get(
        "source",
        exp.source
    )

    if data.get("amount") is not None:
        exp.amount = Decimal(str(data.get("amount")))

    exp.description = data.get(
        "description",
        exp.description
    )

    if data.get("expense_date"):
        exp.expense_date = data.get("expense_date")

    exp.save()

    return JsonResponse({
        "success": True,
        "id": exp.id
    })


import json
import re
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from accounts.models import Staff, Department
from .models import (
    MessageThread, ThreadParticipant,
    Message, MessageAttachment, MessageReadStatus,
    Reaction, PinnedMessage, StarredMessage,
    Mention, Poll, PollOption, PollVote,
    Notification,
)

User = get_user_model()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def json_ok(data, status=200):
    return JsonResponse(data, status=status, safe=isinstance(data, dict))

def json_err(msg, status=400):
    return JsonResponse({'error': msg}, status=status)

def get_hotel(user):
    return getattr(user, 'hotel', None)

def require_hotel(user):
    hotel = get_hotel(user)
    if not hotel:
        raise PermissionError('No hotel linked to this account.')
    return hotel


def _staff_dict(user):
    staff = getattr(user, 'staff_profile', None)
    
    # Get best display name
    name = (
        staff.name if (staff and staff.name)
        else user.get_full_name()
        or user.username
    )
    
    # Get role/department label
    dept_name = staff.department.name if (staff and staff.department) else None
    role      = getattr(staff, 'role', None) or dept_name or 'Staff'

    return {
        'id':          user.id,
        'staff_id':    staff.id        if staff else None,
        'username':    user.username,
        'name':        name,
        'role':        role,
        'employee_id': staff.employee_id  if staff else None,
        'department':  dept_name,
        'dept_id':     staff.department_id if staff else None,
        'photo':       staff.photo.url     if (staff and staff.photo) else None,
    }
def _attachment_dict(att):
    return {
        'id':        att.id,
        'url':       att.file.url,
        'file_name': att.file_name,
        'file_size': att.file_size,
        'file_type': att.file_type,
    }


def _message_dict(msg, current_user):
    reactions = {}
    for r in msg.reactions.all():
        reactions.setdefault(r.emoji, []).append({
            'user_id': r.user_id,
            'name':    r.user.get_full_name(),
        })

    reply_preview = None
    if msg.reply_to_id and not msg.reply_to.is_deleted:
        rp = msg.reply_to
        reply_preview = {
            'id':     rp.id,
            'body':   rp.body[:100],
            'sender': rp.sender.get_full_name() if rp.sender else '',
        }

    fwd_preview = None
    if msg.forwarded_from_id and not msg.forwarded_from.is_deleted:
        ff = msg.forwarded_from
        fwd_preview = {
            'id':            ff.id,
            'body':          ff.body[:100],
            'original_sender': ff.sender.get_full_name() if ff.sender else '',
        }

    poll_data = None
    if hasattr(msg, 'poll'):
        p = msg.poll
        my_votes = list(PollVote.objects.filter(option__poll=p, user=current_user)
                                        .values_list('option_id', flat=True))
        poll_data = {
            'id':           p.id,
            'question':     p.question,
            'is_anonymous': p.is_anonymous,
            'allow_multi':  p.allow_multi,
            'is_open':      p.is_open,
            'closes_at':    str(p.closes_at) if p.closes_at else None,
            'total_votes':  p.total_votes,
            'my_votes':     my_votes,
            'options': [
                {
                    'id':         opt.id,
                    'text':       opt.text,
                    'votes':      opt.vote_count(),
                    'percentage': opt.percentage(),
                    'voted':      opt.id in my_votes,
                    'voters': [] if p.is_anonymous else [
                        v.user.get_full_name() for v in opt.votes.select_related('user').all()
                    ],
                }
                for opt in p.options.all()
            ],
        }

    mentions = list(msg.mentions.filter(is_all=False)
                                .values_list('mentioned_user__username', flat=True))
    has_all_mention = msg.mentions.filter(is_all=True).exists()

    return {
        'id':             msg.id,
        'thread_id':      msg.thread_id,
        'sender':         _staff_dict(msg.sender) if msg.sender else None,
        'body':           msg.body if not msg.is_deleted else '🚫 This message was deleted.',
        'priority':       msg.priority,
        'attachments':    [_attachment_dict(a) for a in msg.attachments.all()],
        'reply_to':       reply_preview,
        'forwarded_from': fwd_preview,
        'poll':           poll_data,
        'is_edited':      msg.is_edited,
        'is_deleted':     msg.is_deleted,
        'is_system_msg':  msg.is_system_msg,
        'is_mine':        msg.sender_id == current_user.id,
        'reactions':      reactions,
        'read_by': [] if msg.is_deleted else list(
            msg.read_statuses.values_list('user__username', flat=True)
        ),
        'mentions':       mentions,
        'has_all_mention': has_all_mention,
        'created_at':     str(msg.created_at),
        'updated_at':     str(msg.updated_at),
    }


def _thread_dict(thread, current_user):
    membership = thread.memberships.filter(user=current_user).first()
    last  = thread.last_message()
    return {
        'id':              thread.id,
        'type':            thread.thread_type,
        'name':            thread.display_name(for_user=current_user),
        'description':     thread.description,
        'avatar':          thread.avatar.url if thread.avatar else None,
        'department':      thread.department.name if thread.department else None,
        'is_archived':     thread.is_archived,
        'is_locked':       thread.is_locked,
        'is_muted':        membership.is_muted       if membership else False,
        'is_pinned_chat':  membership.is_pinned_chat if membership else False,
        'is_admin':        membership.is_admin       if membership else False,
        'participant_count': thread.participants.count(),
        'participants':    [_staff_dict(u) for u in thread.participants.select_related('staff_profile').all()],
        'last_message': {
            'id':         last.id,
            'body':       last.body if not last.is_deleted else '🚫 Message deleted',
            'sender':     last.sender.get_full_name() if last.sender else '—',
            'priority':   last.priority,
            'created_at': str(last.created_at),
        } if last else None,
        'unread_count':    thread.unread_count_for(current_user),
        'pinned_count':    thread.pinned_messages.count(),
        'updated_at':      str(thread.updated_at),
        'created_at':      str(thread.created_at),
    }

def _display(user):
    s    = getattr(user, 'staff_profile', None)
    name = (
        s.name
        if (s and s.name)
        else user.get_full_name() or user.username
    )

    # Collect all role/dept text to check against
    role_field = (getattr(s, 'role', None) or '').lower()
    dept_name  = (s.department.name if (s and s.department) else '') or ''
    dept_lower = dept_name.lower()
    combined   = role_field + ' ' + dept_lower

    # ── Priority 1: Hotel Admin ──────────────────────────────────────
    if any(k in combined for k in [
        'hotel admin', 'admin', 'manager', 'owner',
        'general manager', 'gm', 'director'
    ]):
        role = 'Hotel Admin'

    # ── Priority 2: HR ───────────────────────────────────────────────
    elif any(k in combined for k in [
        'hr', 'human resource', 'human resources',
        'personnel', 'people ops'
    ]):
        role = 'HR'

    # ── Priority 3: Other departments ────────────────────────────────
    elif any(k in combined for k in ['front', 'reception', 'fd', 'front desk', 'front office']):
        role = 'Front Desk'

    elif any(k in combined for k in ['house', 'hk', 'housekeeping', 'clean']):
        role = 'Housekeeping'

    elif any(k in combined for k in ['restaurant', 'f&b', 'food', 'kitchen', 'dining', 'bar']):
        role = 'Restaurant'

    elif any(k in combined for k in ['account', 'finance', 'billing', 'accounts']):
        role = 'Accountant'

    elif any(k in combined for k in ['security', 'guard']):
        role = 'Security'

    elif any(k in combined for k in ['maintenance', 'engineer', 'technician']):
        role = 'Maintenance'

    elif any(k in combined for k in ['store', 'inventory', 'purchase', 'procurement']):
        role = 'Store'

    # ── Fallback: use raw department name or Staff ────────────────────
    else:
        role = dept_name if dept_name else 'Staff'

    return name, role
def _parse_mentions(body, thread, sender):
   
    mentions = []
    if '@all' in body:
        mentions.append(Mention(mentioned_user=None, is_all=True))
    usernames = set(re.findall(r'@(\w+)', body))
    usernames.discard('all')
    if usernames:
        users = User.objects.filter(
            username__in=usernames,
            hotel=sender.hotel,
            message_threads=thread
        )
        for u in users:
            if u != sender:
                mentions.append(Mention(mentioned_user=u, is_all=False))
    return mentions


def _fan_out_notifications(msg, thread, sender):
    participants = thread.participants.exclude(id=sender.id).filter(
        threadparticipant__thread=thread,
        threadparticipant__is_muted=False
    )
    notifs = [
        Notification(
            recipient=u,
            notif_type='message',
            title=f"New message in {thread.display_name(for_user=u)}",
            body=msg.body[:100] if not msg.is_deleted else '',
            thread=thread,
            message=msg,
        )
        for u in participants
    ]
    Notification.objects.bulk_create(notifs)



@method_decorator(login_required, name='dispatch')
class StaffListView(View):

    def get(self, request):
        hotel = get_hotel(request.user)

        if not hotel:
            return JsonResponse({
                "staff": [],
                "error": "No hotel linked."
            }, status=403)

        qs = (
            Staff.objects
            .filter(hotel=hotel, is_active=True)
            .exclude(user=request.user)
            .select_related('user', 'department')
            .order_by('name')
        )

        dept = request.GET.get('department')
        if dept:
            qs = qs.filter(department_id=dept)

        q = request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(name__icontains=q) |
                Q(employee_id__icontains=q)
            )

        staff_data = []

        for s in qs:
            staff_data.append({
                "id": s.id,
                "name": (
                    s.name
                    or s.user.get_full_name()
                    or s.user.username
                ),
                "department": (
                    s.department.name
                    if s.department else ''
                ),
                "employee_id": s.employee_id,
            })

        return JsonResponse({
            "staff": staff_data
        })

@method_decorator(login_required, name='dispatch')
class ThreadListView(View):

    def get(self, request):
        hotel = get_hotel(request.user)
        if not hotel:
            return json_err('No hotel linked.', 403)

        qs = (
            MessageThread.objects
            .filter(hotel=hotel, participants=request.user)
            .prefetch_related(
                Prefetch('memberships', queryset=ThreadParticipant.objects.select_related('user')),
                Prefetch('participants'),
            )
        )
        if t := request.GET.get('type'):
            qs = qs.filter(thread_type=t)
        if request.GET.get('archived') == 'true':
            qs = qs.filter(is_archived=True)
        else:
            qs = qs.filter(is_archived=False)
        if request.GET.get('pinned') == 'true':
            qs = qs.filter(memberships__user=request.user, memberships__is_pinned_chat=True)

        return json_ok([_thread_dict(t, request.user) for t in qs])

    @transaction.atomic
    def post(self, request):
        hotel = get_hotel(request.user)
        if not hotel:
            return json_err('No hotel linked.', 403)

        data        = json.loads(request.body)
        thread_type = data.get('type', 'direct')

        # ── Shared helper: get display name + role label from a User ─────────
        def _display(user):
            s    = getattr(user, 'staff_profile', None)
            name = (
                s.name
                if (s and s.name)
                else user.get_full_name() or user.username
            )

            # Collect role + department into one string for matching
            role_field = (getattr(s, 'role', None) or '').lower()
            dept_name  = (s.department.name if (s and s.department) else '') or ''
            dept_lower = dept_name.lower()
            combined   = role_field + ' ' + dept_lower

            # ── Priority 1: Hotel Admin ──────────────────────────────────
            if any(k in combined for k in [
                'hotel admin', 'admin', 'manager', 'owner',
                'general manager', 'gm', 'director', 'supervisor'
            ]):
                role = 'Hotel Admin'

            # ── Priority 2: HR ───────────────────────────────────────────
            elif any(k in combined for k in [
                'hr', 'human resource', 'human resources',
                'personnel', 'people ops'
            ]):
                role = 'HR'

            # ── Priority 3: Front Desk ───────────────────────────────────
            elif any(k in combined for k in [
                'front desk', 'front office', 'front', 'reception',
                'receptionist', 'fd'
            ]):
                role = 'Front Desk'

            
            elif any(k in combined for k in [
                'housekeeping', 'house keeping', 'hk', 'cleaning', 'clean'
            ]):
                role = 'Housekeeping'

            
            elif any(k in combined for k in [
                'restaurant', 'f&b', 'food', 'kitchen',
                'dining', 'bar', 'cafe', 'fbservice'
            ]):
                role = 'Restaurant'

            
            elif any(k in combined for k in [
                'account', 'accountant', 'finance', 'billing', 'accounts'
            ]):
                role = 'Accountant'

            
            elif any(k in combined for k in [
                'maintenance', 'engineer', 'technician', 'engineering'
            ]):
                role = 'Maintenance'

           
            elif any(k in combined for k in [
                'security', 'guard', 'safety'
            ]):
                role = 'Security'

           
            elif any(k in combined for k in [
                'store', 'inventory', 'purchase', 'procurement', 'storekeeper'
            ]):
                role = 'Store'

            
            else:
                role = dept_name if dept_name else 'Staff'

            return name, role

        
        if thread_type == 'direct':
            other_id = data.get('participant_id')
            if not other_id:
                return json_err('participant_id is required.')

           
            try:
                other = User.objects.get(
                    staff_profile__id=other_id,
                    hotel=hotel
                )
            except User.DoesNotExist:
                try:
                    other = User.objects.get(id=other_id, hotel=hotel)
                except User.DoesNotExist:
                    return json_err('User not found in this hotel.', 404)

          
            existing = (
                MessageThread.objects
                .filter(hotel=hotel, thread_type='direct', participants=request.user)
                .filter(participants=other)
                .annotate(cnt=Count('participants'))
                .filter(cnt=2)
                .first()
            )
            if existing:
                return json_ok(_thread_dict(existing, request.user))

            thread = MessageThread.objects.create(
                hotel=hotel, thread_type='direct', created_by=request.user
            )
            ThreadParticipant.objects.bulk_create([
                ThreadParticipant(thread=thread, user=request.user, is_admin=True),
                ThreadParticipant(thread=thread, user=other),
            ])
            return json_ok(_thread_dict(thread, request.user), 201)

        
        if thread_type == 'group':
            name = data.get('name', '').strip()
            if not name:
                return json_err('name is required for group chats.')

            ids = data.get('participant_ids', [])
            if not ids or len(ids) < 1:
                return json_err('At least 1 other participant is required.')

           
            others = User.objects.filter(
                staff_profile__id__in=ids,
                hotel=hotel
            ).exclude(id=request.user.id).select_related('staff_profile__department')

           
            if not others.exists():
                others = User.objects.filter(
                    id__in=ids,
                    hotel=hotel
                ).exclude(id=request.user.id).select_related('staff_profile__department')

            if not others.exists():
                return json_err(
                    f'No valid staff members found. Received IDs: {ids}.', 400
                )

            thread = MessageThread.objects.create(
                hotel=hotel,
                thread_type='group',
                name=name,
                description=data.get('description', ''),
                created_by=request.user,
            )

            members = [ThreadParticipant(thread=thread, user=request.user, is_admin=True)]
            members += [ThreadParticipant(thread=thread, user=u) for u in others]
            ThreadParticipant.objects.bulk_create(members)

            
            creator_name, creator_role = _display(request.user)

            member_parts = []
            for u in others:
                m_name, m_role = _display(u)
                member_parts.append(f'{m_name} ({m_role})')
            members_str = ', '.join(member_parts)

            Message.objects.create(
                thread=thread,
                sender=request.user,
                body=(
                    f'{creator_name} ({creator_role}) created the group "{name}" '
                    f'with {members_str}.'
                ),
                is_system_msg=True,
            )
            return json_ok(_thread_dict(thread, request.user), 201)

       
        if thread_type == 'department':
            dept_id = data.get('department_id')
            try:
                dept = Department.objects.get(id=dept_id, hotel=hotel)
            except Department.DoesNotExist:
                return json_err('Department not found.', 404)

            thread, created = MessageThread.objects.get_or_create(
                hotel=hotel, thread_type='department', department=dept,
                defaults={'name': dept.name, 'created_by': request.user}
            )
            if created:
                dept_users = User.objects.filter(hotel=hotel, role=dept, is_active_staff=True)
                ThreadParticipant.objects.bulk_create([
                    ThreadParticipant(thread=thread, user=u, is_admin=(u == request.user))
                    for u in dept_users
                ])
            return json_ok(_thread_dict(thread, request.user), 201 if created else 200)

       
        if thread_type == 'announcement':
            name = data.get('name', '').strip()
            if not name:
                return json_err('name is required for announcement boards.')

            staff = getattr(request.user, 'staff_profile', None)
            is_manager = staff and staff.department and \
                         RolePermission_check(staff.department, 'manage_announcements')

            thread = MessageThread.objects.create(
                hotel=hotel,
                thread_type='announcement',
                name=name,
                description=data.get('description', ''),
                created_by=request.user,
            )

            add_all = data.get('add_all_staff', False)
            if add_all:
                all_users = User.objects.filter(hotel=hotel, is_active_staff=True)
                ThreadParticipant.objects.bulk_create([
                    ThreadParticipant(thread=thread, user=u, is_admin=(u == request.user))
                    for u in all_users
                ])
            else:
                ThreadParticipant.objects.create(
                    thread=thread, user=request.user, is_admin=True
                )
            return json_ok(_thread_dict(thread, request.user), 201)

        return json_err(f'Unknown thread type: {thread_type}')
def RolePermission_check(department, perm_name):
  
    from accounts.models import RolePermission, Permission
    return RolePermission.objects.filter(
        role=department,
        permission__name=perm_name
    ).exists()


@method_decorator(login_required, name='dispatch')
class ThreadDetailView(View):
    

    def _get_thread(self, request, thread_id):
        hotel = get_hotel(request.user)
        return MessageThread.objects.filter(
            id=thread_id, hotel=hotel, participants=request.user
        ).prefetch_related('memberships', 'participants').first()

    def get(self, request, thread_id):
        thread = self._get_thread(request, thread_id)
        if not thread:
            return json_err('Thread not found.', 404)
        return json_ok(_thread_dict(thread, request.user))

    def patch(self, request, thread_id):
        thread = self._get_thread(request, thread_id)
        if not thread:
            return json_err('Thread not found.', 404)

        data       = json.loads(request.body)
        membership = thread.memberships.filter(user=request.user).first()

        # Non-admin operations (any member can do these)
        if 'is_muted' in data:
            membership.is_muted = bool(data['is_muted'])
            membership.save(update_fields=['is_muted'])
        if 'is_pinned_chat' in data:
            membership.is_pinned_chat = bool(data['is_pinned_chat'])
            membership.save(update_fields=['is_pinned_chat'])

        # Admin-only operations
        if membership.is_admin:
            if 'name' in data:
                thread.name = data['name'].strip()
            if 'description' in data:
                thread.description = data['description'].strip()
            if 'is_locked' in data:
                thread.is_locked = bool(data['is_locked'])
            thread.save()

        return json_ok(_thread_dict(thread, request.user))

    def delete(self, request, thread_id):
        thread = self._get_thread(request, thread_id)
        if not thread:
            return json_err('Thread not found.', 404)
        membership = thread.memberships.filter(user=request.user).first()
        if not membership or not membership.is_admin:
            return json_err('Only admins can archive this thread.', 403)
        thread.is_archived = True
        thread.save(update_fields=['is_archived'])
        return json_ok({'archived': True})


# ─────────────────────────────────────────────────────────────────────────────
# E.  Thread members  (add / remove)
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class ThreadMembersView(View):
    

    def _get_admin_thread(self, request, thread_id):
        hotel  = get_hotel(request.user)
        thread = MessageThread.objects.filter(id=thread_id, hotel=hotel).first()
        if not thread:
            return None, json_err('Thread not found.', 404)
        m = thread.memberships.filter(user=request.user).first()
        if not m or not m.is_admin:
            return None, json_err('Admin permission required.', 403)
        return thread, None

    def post(self, request, thread_id):
        thread, err = self._get_admin_thread(request, thread_id)
        if err:
            return err
        data = json.loads(request.body)
        ids  = data.get('user_ids', [])
        hotel = get_hotel(request.user)
        users = User.objects.filter(id__in=ids, hotel=hotel)
        added = []
        for u in users:
            _, created = ThreadParticipant.objects.get_or_create(thread=thread, user=u)
            if created:
                added.append(u.get_full_name())
                Message.objects.create(
                    thread=thread, sender=request.user,
                    body=f"{u.get_full_name()} was added to the group.",
                    is_system_msg=True,
                )
        thread.save(update_fields=['updated_at'])
        return json_ok({'added': added})

    def delete(self, request, thread_id):
        hotel  = get_hotel(request.user)
        thread = MessageThread.objects.filter(id=thread_id, hotel=hotel).first()
        if not thread:
            return json_err('Thread not found.', 404)

        data    = json.loads(request.body)
        user_id = data.get('user_id', request.user.id)
        m_self  = thread.memberships.filter(user=request.user).first()

        # Members can only remove themselves; admins can remove anyone
        if user_id != request.user.id and (not m_self or not m_self.is_admin):
            return json_err('You can only remove yourself unless you are an admin.', 403)

        ThreadParticipant.objects.filter(thread=thread, user_id=user_id).delete()
        try:
            removed_user = User.objects.get(id=user_id)
            Message.objects.create(
                thread=thread, sender=request.user,
                body=f"{removed_user.get_full_name()} left the group.",
                is_system_msg=True,
            )
        except User.DoesNotExist:
            pass
        thread.save(update_fields=['updated_at'])
        return json_ok({'removed': user_id})



import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

@login_required
def thread_messages_view(request, thread_id):

    hotel = get_hotel(request.user)

    thread = get_object_or_404(
        MessageThread,
        id=thread_id,
        hotel=hotel,
        participants=request.user
    )

    
    if request.method == "GET":

        messages = thread.messages.select_related(
            'sender__staff_profile'
        ).prefetch_related(
            'attachments',
            'reactions'
        ).order_by('created_at')

        after = request.GET.get('after')

        if after:
            messages = messages.filter(id__gt=after)

        unread_ids = [
            m.id for m in messages
            if m.sender_id != request.user.id and not m.is_deleted
        ]

        if unread_ids:
            MessageReadStatus.objects.bulk_create(
                [
                    MessageReadStatus(
                        message_id=mid,
                        user=request.user
                    )
                    for mid in unread_ids
                ],
                ignore_conflicts=True
            )

            membership = thread.memberships.filter(
                user=request.user
            ).first()

            if membership:
                membership.mark_read()

        data = []

        for msg in messages:
            data.append({
                'id': msg.id,
                'body': msg.body,
                'sender_id': msg.sender.id,
                'sender_name': msg.sender.get_full_name(),
                'created_at': msg.created_at.isoformat(),
                'priority': msg.priority,
            })

        return JsonResponse({
            'success': True,
            'messages': data
        })

    # POST new message
    elif request.method == "POST":

        data = json.loads(request.body)

        body = data.get('body', '').strip()

        if not body:
            return JsonResponse({
                'success': False,
                'message': 'Message body required'
            }, status=400)

        msg = Message.objects.create(
            thread=thread,
            sender=request.user,
            body=body,
            priority=data.get('priority', 'normal')
        )

        membership = thread.memberships.filter(
            user=request.user
        ).first()

        if membership:
            membership.mark_read()

        return JsonResponse({
            'success': True,
            'message': {
                'id': msg.id,
                'body': msg.body,
                'sender_id': msg.sender.id,
                'sender_name': msg.sender.get_full_name(),
                'created_at': msg.created_at.isoformat(),
                'priority': msg.priority,
            }
        }, status=201)

    return JsonResponse({
        'success': False,
        'message': 'Method not allowed'
    }, status=405)



@method_decorator(login_required, name='dispatch')
class MessageDetailView(View):
   

    def _get_msg(self, request, msg_id, own_only=True):
        hotel = get_hotel(request.user)
        qs = Message.objects.filter(id=msg_id, thread__hotel=hotel, is_deleted=False)
        if own_only:
            qs = qs.filter(sender=request.user)
        return qs.first()

    def get(self, request, msg_id):
        msg = self._get_msg(request, msg_id, own_only=False)
        if not msg:
            return json_err('Message not found.', 404)
        return json_ok(_message_dict(msg, request.user))

    def patch(self, request, msg_id):
        msg = self._get_msg(request, msg_id)
        if not msg:
            return json_err('Message not found or not yours.', 404)
        data = json.loads(request.body)
        new_body = data.get('body', '').strip()
        if not new_body:
            return json_err('Body cannot be empty.')
        msg.body      = new_body
        msg.is_edited = True
        msg.save(update_fields=['body', 'is_edited', 'updated_at'])
        return json_ok(_message_dict(msg, request.user))

    def delete(self, request, msg_id):
        msg = self._get_msg(request, msg_id)
        if not msg:
            return json_err('Message not found or not yours.', 404)
        msg.soft_delete()
        return json_ok({'deleted': True, 'id': msg_id})


# ─────────────────────────────────────────────────────────────────────────────
# H.  Attachments upload
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class AttachmentUploadView(View):
    """
    POST /api/messaging/messages/<id>/attachments/
    Multipart form: files[] (multiple allowed)
    """
    MAX_SIZE_MB = 20

    def post(self, request, msg_id):
        hotel = get_hotel(request.user)
        msg   = Message.objects.filter(
            id=msg_id, sender=request.user, thread__hotel=hotel, is_deleted=False
        ).first()
        if not msg:
            return json_err('Message not found or not yours.', 404)

        files  = request.FILES.getlist('files[]')
        if not files:
            return json_err('No files provided.')

        created = []
        for f in files:
            if f.size > self.MAX_SIZE_MB * 1024 * 1024:
                return json_err(f'{f.name} exceeds {self.MAX_SIZE_MB}MB limit.')
            att = MessageAttachment.objects.create(
                message=msg, file=f,
                file_name=f.name, file_size=f.size,
            )
            created.append(_attachment_dict(att))

        return json_ok({'attachments': created}, 201)


# ─────────────────────────────────────────────────────────────────────────────
# I.  Reactions
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class ReactionView(View):
    """
    POST /api/messaging/messages/<id>/react/
    Body: { "emoji": "👍" }   — toggles add/remove
    """
    def post(self, request, msg_id):
        hotel = get_hotel(request.user)
        msg   = Message.objects.filter(id=msg_id, thread__hotel=hotel, is_deleted=False).first()
        if not msg:
            return json_err('Message not found.', 404)
        data  = json.loads(request.body)
        emoji = data.get('emoji', '').strip()
        valid = [e for e, _ in Reaction.EMOJI_CHOICES]
        if emoji not in valid:
            return json_err(f'Invalid emoji. Choose from: {valid}')

        reaction, created = Reaction.objects.get_or_create(message=msg, user=request.user, emoji=emoji)
        if not created:
            reaction.delete()
            return json_ok({'action': 'removed', 'emoji': emoji})

        # Notify message owner
        if msg.sender and msg.sender != request.user:
            Notification.objects.create(
                recipient=msg.sender, notif_type='reaction',
                title=f"{request.user.get_full_name()} reacted {emoji} to your message",
                body=msg.body[:80], thread=msg.thread, message=msg,
            )
        return json_ok({'action': 'added', 'emoji': emoji})


# ─────────────────────────────────────────────────────────────────────────────
# J.  Pin / unpin messages
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class PinMessageView(View):
    """
    GET    /api/messaging/threads/<id>/pins/     → list pinned messages
    POST   /api/messaging/threads/<id>/pins/     → pin a message  (admin only)
           body: { "message_id": <id> }
    DELETE /api/messaging/threads/<id>/pins/<pin_id>/  → unpin  (admin only)
    """

    def _get_admin_membership(self, request, thread_id):
        hotel  = get_hotel(request.user)
        thread = MessageThread.objects.filter(id=thread_id, hotel=hotel).first()
        if not thread:
            return None, None, json_err('Thread not found.', 404)
        m = thread.memberships.filter(user=request.user).first()
        if not m or not m.is_admin:
            return None, None, json_err('Only thread admins can manage pins.', 403)
        return thread, m, None

    def get(self, request, thread_id):
        hotel  = get_hotel(request.user)
        thread = MessageThread.objects.filter(id=thread_id, hotel=hotel, participants=request.user).first()
        if not thread:
            return json_err('Thread not found.', 404)
        pins = (
            thread.pinned_messages
            .select_related('message__sender', 'pinned_by')
            .prefetch_related('message__attachments')
            .order_by('-pinned_at')
        )
        return json_ok([{
            'pin_id':    p.id,
            'message':   _message_dict(p.message, request.user),
            'pinned_by': p.pinned_by.get_full_name() if p.pinned_by else '—',
            'pinned_at': str(p.pinned_at),
        } for p in pins])

    def post(self, request, thread_id):
        thread, _, err = self._get_admin_membership(request, thread_id)
        if err:
            return err
        if thread.pinned_messages.count() >= 10:
            return json_err('Maximum 10 pinned messages per thread.')
        data = json.loads(request.body)
        msg  = Message.objects.filter(id=data.get('message_id'), thread=thread, is_deleted=False).first()
        if not msg:
            return json_err('Message not found in this thread.', 404)
        pin, created = PinnedMessage.objects.get_or_create(
            thread=thread, message=msg, defaults={'pinned_by': request.user}
        )
        return json_ok({'pin_id': pin.id, 'created': created}, 201 if created else 200)

    def delete(self, request, thread_id, pin_id):
        thread, _, err = self._get_admin_membership(request, thread_id)
        if err:
            return err
        deleted, _ = PinnedMessage.objects.filter(id=pin_id, thread=thread).delete()
        return json_ok({'deleted': bool(deleted)})


# ─────────────────────────────────────────────────────────────────────────────
# K.  Starred messages  (personal bookmarks)
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class StarredMessageView(View):
    """
    GET    /api/messaging/starred/              → all starred messages
    POST   /api/messaging/messages/<id>/star/   → toggle star
    """
    def get(self, request):
        hotel = get_hotel(request.user)
        stars = (
            StarredMessage.objects
            .filter(user=request.user, message__thread__hotel=hotel)
            .select_related('message__sender', 'message__thread')
            .prefetch_related('message__attachments')
            .order_by('-starred_at')
        )
        return json_ok([{
            'star_id':    s.id,
            'thread':     s.message.thread.display_name(for_user=request.user),
            'thread_id':  s.message.thread_id,
            'message':    _message_dict(s.message, request.user),
            'starred_at': str(s.starred_at),
        } for s in stars])

    def post(self, request, msg_id):
        hotel = get_hotel(request.user)
        msg   = Message.objects.filter(id=msg_id, thread__hotel=hotel, is_deleted=False).first()
        if not msg:
            return json_err('Message not found.', 404)
        star, created = StarredMessage.objects.get_or_create(user=request.user, message=msg)
        if not created:
            star.delete()
            return json_ok({'action': 'unstarred'})
        return json_ok({'action': 'starred', 'star_id': star.id})


# ─────────────────────────────────────────────────────────────────────────────
# L.  Poll voting
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class PollVoteView(View):
    """
    POST /api/messaging/polls/<poll_id>/vote/
    Body: { "option_ids": [<id>] }   — single-choice: list of 1; multi: list of N
    """
    def post(self, request, poll_id):
        hotel = get_hotel(request.user)
        poll  = Poll.objects.filter(
            id=poll_id, message__thread__hotel=hotel
        ).prefetch_related('options').first()
        if not poll:
            return json_err('Poll not found.', 404)
        if not poll.is_open:
            return json_err('This poll is closed.')

        data       = json.loads(request.body)
        option_ids = data.get('option_ids', [])
        if not option_ids:
            return json_err('option_ids is required.')
        if not poll.allow_multi and len(option_ids) > 1:
            return json_err('This poll only allows one choice.')

        valid_ids = set(poll.options.values_list('id', flat=True))
        if not all(oid in valid_ids for oid in option_ids):
            return json_err('One or more option IDs are invalid.')

        with transaction.atomic():
            # Remove previous votes
            PollVote.objects.filter(option__poll=poll, user=request.user).delete()
            # Cast new votes
            PollVote.objects.bulk_create([
                PollVote(option_id=oid, user=request.user)
                for oid in option_ids
            ])

        poll.refresh_from_db()
        return json_ok({
            'total_votes': poll.total_votes,
            'options': [
                {
                    'id':         opt.id,
                    'text':       opt.text,
                    'votes':      opt.vote_count(),
                    'percentage': opt.percentage(),
                    'voted':      opt.id in option_ids,
                }
                for opt in poll.options.all()
            ]
        })


# ─────────────────────────────────────────────────────────────────────────────
# M.  Message search
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class MessageSearchView(View):
    """
    GET /api/messaging/search/?q=<text>&thread=<id>&priority=<p>
    Returns up to 50 matching messages across all the user's threads in this hotel.
    """
    def get(self, request):
        hotel = get_hotel(request.user)
        if not hotel:
            return json_err('No hotel linked.', 403)
        q = request.GET.get('q', '').strip()
        if len(q) < 2:
            return json_err('Query must be at least 2 characters.')

        qs = Message.objects.filter(
            thread__hotel=hotel,
            thread__participants=request.user,
            is_deleted=False,
            body__icontains=q,
        ).select_related('sender__staff_profile', 'thread').order_by('-created_at')

        if tid := request.GET.get('thread'):
            qs = qs.filter(thread_id=tid)
        if prio := request.GET.get('priority'):
            qs = qs.filter(priority=prio)

        results = qs[:50]
        return json_ok([{
            **_message_dict(m, request.user),
            'thread_name': m.thread.display_name(for_user=request.user),
        } for m in results])


# ─────────────────────────────────────────────────────────────────────────────
# N.  Notifications
# ─────────────────────────────────────────────────────────────────────────────

@method_decorator(login_required, name='dispatch')
class NotificationView(View):
    """
    GET   /api/messaging/notifications/         → all notifications (paginated)
          ?unread=true                           → only unread
          ?type=mention|reaction|message|poll
    POST  /api/messaging/notifications/read/    → mark all read
          body: { "ids": [1,2,3] }              → mark specific ids read
    """
    def get(self, request):
        qs = Notification.objects.filter(recipient=request.user)
        if request.GET.get('unread') == 'true':
            qs = qs.filter(is_read=False)
        if ntype := request.GET.get('type'):
            qs = qs.filter(notif_type=ntype)
        limit  = min(int(request.GET.get('limit', 30)), 100)
        notifs = qs[:limit]
        return json_ok({
            'unread_total': Notification.objects.filter(recipient=request.user, is_read=False).count(),
            'results': [
                {
                    'id':         n.id,
                    'type':       n.notif_type,
                    'title':      n.title,
                    'body':       n.body,
                    'thread_id':  n.thread_id,
                    'message_id': n.message_id,
                    'is_read':    n.is_read,
                    'created_at': str(n.created_at),
                }
                for n in notifs
            ]
        })

    def post(self, request):
        data = json.loads(request.body)
        ids  = data.get('ids')
        qs   = Notification.objects.filter(recipient=request.user)
        if ids:
            qs = qs.filter(id__in=ids)
        qs.update(is_read=True)
        return json_ok({'marked_read': True})
@method_decorator(login_required, name='dispatch')
class MarkThreadReadView(View):
    def post(self, request, thread_id):
        hotel = get_hotel(request.user)
        thread = MessageThread.objects.filter(
            id=thread_id, hotel=hotel, participants=request.user
        ).first()
        if not thread:
            return json_err('Thread not found.', 404)
        membership = thread.memberships.filter(user=request.user).first()
        if membership:
            membership.mark_read()
        MessageReadStatus.objects.bulk_create(
            [MessageReadStatus(message_id=mid, user=request.user)
             for mid in thread.messages.exclude(sender=request.user)
                                       .values_list('id', flat=True)],
            ignore_conflicts=True
        )
        return json_ok({'ok': True})


@method_decorator(login_required, name='dispatch')
class PinnedMessagesView(View):
    """GET /messages/threads/<id>/pinned/  — lightweight list for the pinned bar"""
    def get(self, request, thread_id):
        hotel = get_hotel(request.user)
        thread = MessageThread.objects.filter(
            id=thread_id, hotel=hotel, participants=request.user
        ).first()
        if not thread:
            return json_err('Thread not found.', 404)
        pins = thread.pinned_messages.select_related(
            'message__sender', 'pinned_by'
        ).order_by('-pinned_at')[:10]
        return json_ok({'pinned': [_message_dict(p.message, request.user) for p in pins]})