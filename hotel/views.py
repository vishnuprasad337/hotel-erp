from django.shortcuts import render, redirect

from .models import (
    Hotel,
    Amenity,
    Room,
    Department,
    Staff,
    Task,
    Shift,
    RoomUnit,
    Attendance,
    LeaveRequest,
    Payroll,
    PayrollLineItem,
    ShiftTemplate,
)

from datetime import datetime
from django.conf import settings
from django.utils import timezone


from accounts.decorators import staff_login_required

from decimal import Decimal, InvalidOperation
import calendar
from inventory.models import (
    InventoryItem as HotelInventoryItem,
    ItemCategory,
    Vendor,
)


from django.http import JsonResponse, HttpResponse
from pms.models import Booking,Payment
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate ,login
from django.contrib.auth.decorators import login_required
import json
from django.contrib.auth.models import User
from accounts.models import Department,HotelModule,Staff
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from datetime import timedelta,date
from django.db.models import Count, Sum, Q, F
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache


from .services.face_verification import (
    validate_face_descriptor,
    verify_staff_face,
    normalize_descriptors,
    FACE_MATCH_THRESHOLD,
)

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
        "inventory": HotelInventoryItem.objects.all().order_by("-id")
    }

    return render(request, "staff.html", context)




@staff_login_required
def gets_inventory(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:

        return JsonResponse(
            {
                "error": "Not logged in"
            },
            status=401
        )

    try:
        Staff.objects.get(
            id=staff_id
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "error": "Staff not found"
            },
            status=404
        )

    items = (
        HotelInventoryItem.objects
        .select_related(
            "category",
            "department",
            "vendor",
        )
        .all()
        .order_by("-created_at")
    )

    data = []

    for item in items:

        data.append(
            {
                "id": item.id,

                "name": item.name,

                "category":
                    item.category.name
                    if item.category
                    else "",

                # Compatibility with old JS
                "quantity":
                    float(
                        item.current_stock or 0
                    ),

                "current_stock":
                    float(
                        item.current_stock or 0
                    ),

                "unit":
                    item.unit,

                "reorder_level":
                    float(
                        item.minimum_stock or 0
                    ),

                "minimum_stock":
                    float(
                        item.minimum_stock or 0
                    ),

                "cost_per_unit":
                    float(
                        item.cost_per_unit or 0
                    ),

                "department":
                    item.department.name
                    if item.department
                    else "",

                "vendor":
                    str(item.vendor)
                    if item.vendor
                    else "",

                # Old fields no longer exist
                "room_number": "N/A",
                "updated_by": "N/A",
                "assigned_by": "N/A",
                "description": "",
            }
        )

    return JsonResponse(
        data,
        safe=False
    )




@require_POST
def assign_task(request):

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Session expired. Please login again."
            },
            status=401
        )

    staff_id = request.POST.get("staff")
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()

    # ========================================================
    # VALIDATION
    # ========================================================

    if not staff_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Please select an employee."
            },
            status=400
        )

    if not title:
        return JsonResponse(
            {
                "success": False,
                "error": "Task title is required."
            },
            status=400
        )

    # ========================================================
    # MAKE SURE STAFF BELONGS TO THIS HOTEL
    # ========================================================

    try:
        staff = Staff.objects.select_related(
            "department"
        ).get(
            id=staff_id,
            hotel_id=hotel_id
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Employee not found."
            },
            status=404
        )

    # ========================================================
    # CREATE TASK
    # ========================================================

    task = Task.objects.create(
        staff=staff,
        title=title,
        description=description,
        status="Pending"
    )

    return JsonResponse(
        {
            "success": True,
            "message": "Task assigned successfully.",

            "task": {
                "id": task.id,
                "title": task.title,
                "description": task.description or "",
                "staff_id": staff.id,
                "staff": staff.name,

                "department": (
                    staff.department.name
                    if staff.department
                    else "—"
                ),

                "status": task.status,

                "created_at": task.created_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            }
        }
    )





# def get_tasks(request):
#     hotel_id = request.session.get("hotel_id")
#     tasks = Task.objects.filter(staff__hotel_id=hotel_id).select_related("staff")
    
#     task_list = []
#     for t in tasks:
#         task_list.append({
#             "id": t.id,
#             "title": t.title,
#             "description": t.description,
#             "staff": t.staff.name,
#             "staff_id": t.staff.id, 
#             "status": t.status,
#             "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(t, 'created_at') else None
#         })
    
#     return JsonResponse({"tasks": task_list, "count": tasks.count()})





@require_GET
def get_tasks(request):

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Session expired. Please login again."
            },
            status=401
        )

    # ========================================================
    # ONLY CURRENT HOTEL TASKS
    # ========================================================

    tasks = (
        Task.objects
        .filter(
            staff__hotel_id=hotel_id
        )
        .select_related(
            "staff",
            "staff__department",
            "room",
            "room_unit"
        )
        .order_by("-created_at")
    )

    task_list = []

    for task in tasks:

        task_list.append(
            {
                "id": task.id,

                "title": task.title,

                "description": (
                    task.description or ""
                ),

                "staff": task.staff.name,

                "staff_id": task.staff.id,

                "department": (
                    task.staff.department.name
                    if task.staff.department
                    else "—"
                ),

                "department_id": (
                    task.staff.department.id
                    if task.staff.department
                    else None
                ),

                "status": task.status,

                "room_number": (
                    task.room_unit.room_number
                    if task.room_unit
                    else None
                ),

                "room_type": (
                    task.room.room_type
                    if task.room
                    else None
                ),

                "created_at": (
                    task.created_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if task.created_at
                    else None
                ),
            }
        )

    # ========================================================
    # STATS
    # ========================================================

    total_tasks = tasks.count()

    pending_tasks = tasks.filter(
        status="Pending"
    ).count()

    in_progress_tasks = tasks.filter(
        status="In Progress"
    ).count()

    completed_tasks = tasks.filter(
        status="Completed"
    ).count()

    return JsonResponse(
        {
            "success": True,

            "tasks": task_list,

            # Keep old response field too
            "count": total_tasks,

            "stats": {
                "total": total_tasks,
                "pending": pending_tasks,
                "in_progress": in_progress_tasks,
                "completed": completed_tasks,
            }
        }
    )




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


MAX_RANGE_DAYS = 366
 
 
def _local(dt):
    if dt and timezone.is_aware(dt):
        return timezone.localtime(dt)
    return dt
 
 
def _fmt_clock(dt):
    dt = _local(dt)
    return dt.strftime("%I:%M %p").lstrip("0") if dt else None
 
 
def _fmt_worked(check_in, check_out):
    if not (check_in and check_out):
        return None
    secs = max((check_out - check_in).total_seconds(), 0)
    return f"{int(secs // 3600)}h {int((secs % 3600) // 60):02d}m"
 
 
def get_shifts(request):
    """
    GET /get_shifts/?date=YYYY-MM-DD
    GET /get_shifts/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
 
    Returns shifts joined with that day's attendance so the Shift
    Management list can show check-in/out, hours, face status and
    attendance status.
    """
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)
 
    date_str = request.GET.get("date")
    from_str = request.GET.get("date_from")
    to_str = request.GET.get("date_to")
 
    try:
        if from_str and to_str:
            date_from = datetime.strptime(from_str, "%Y-%m-%d").date()
            date_to = datetime.strptime(to_str, "%Y-%m-%d").date()
        elif date_str:
            date_from = date_to = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            date_from = date_to = timezone.now().date()
    except ValueError:
        return JsonResponse({"error": "Invalid date format"}, status=400)
 
    if date_from > date_to:
        return JsonResponse({"error": "date_from cannot be after date_to"}, status=400)
    if (date_to - date_from).days > MAX_RANGE_DAYS:
        return JsonResponse(
            {"error": f"Range too large (max {MAX_RANGE_DAYS} days)"}, status=400
        )
 
    shifts = (
        Shift.objects
        .filter(hotel_id=hotel_id, date__range=(date_from, date_to))
        .select_related("staff", "department")
        .order_by("date", "staff__name")
    )
 
    # Attendance for the same range, keyed by (staff_id, date)
    att_map = {
        (a.staff_id, a.date): a
        for a in Attendance.objects.filter(
            hotel_id=hotel_id, date__range=(date_from, date_to)
        )
    }
 
    templates = {
        t.shift_name: t
        for t in ShiftTemplate.objects.filter(hotel_id=hotel_id, is_active=True)
    }
    DEFAULTS = {
        "Morning": ("06:00", "14:00", "#d97706"),
        "Evening": ("14:00", "22:00", "#1a65f5"),
        "Night":   ("22:00", "06:00", "#7c3aed"),
    }
 
    def resolve(s):
        """Returns (start, end, color) as 'HH:MM' strings + hex color."""
        if s.custom_start and s.custom_end:
            return (
                s.custom_start.strftime("%H:%M"),
                s.custom_end.strftime("%H:%M"),
                s.custom_color or "#0d9488",
            )
        tpl = templates.get(s.shift)
        if tpl:
            return (tpl.start_time if which == "start" else tpl.end_time).strftime("%H:%M")
        d = DEFAULTS.get(s.shift, ("00:00", "00:00"))
        return d[0] if which == "start" else d[1]

    data = [{
    "id": s.id,

    "staff": (
        s.staff.name
        if s.staff
        else "N/A"
    ),

    "staff_id": (
        s.staff.id
        if s.staff
        else None
    ),

    "department": (
        s.department.name
        if s.department
        else "N/A"
    ),

    "department_id": s.department_id,

    "shift": s.shift,

    "custom_name": s.custom_name or "",

    "custom_start": (
        s.custom_start.strftime("%H:%M")
        if s.custom_start
        else ""
    ),

    "custom_end": (
        s.custom_end.strftime("%H:%M")
        if s.custom_end
        else ""
    ),

    "custom_color": s.custom_color or "",

    "start_time": resolve(s, "start"),
    "end_time": resolve(s, "end"),

    "date": s.date.strftime("%Y-%m-%d"),

} for s in shifts]

    return JsonResponse(data, safe=False)
 
 
@require_POST
def assign_shift(request):
    try:
        hotel_id = request.session.get("hotel_id")
        staff_id = request.session.get("staff_id")
 
        if not hotel_id and not staff_id:
            return JsonResponse({"error": "Login required"}, status=401)
 
        if not hotel_id:
            try:
                staff_obj = Staff.objects.select_related("hotel").get(id=staff_id)
                hotel_id = staff_obj.hotel_id
                request.session["hotel_id"] = hotel_id
            except Staff.DoesNotExist:
                return JsonResponse({"error": "Staff not found"}, status=404)
 
        req_staff_id = request.POST.get("staff") or request.POST.get("staff_id")
        if not req_staff_id:
            if staff_id:
                req_staff_id = staff_id
            else:
                return JsonResponse({"error": "staff is required"}, status=400)
 
        department_id = request.POST.get("department") or request.POST.get("department_id")
        shift_value = request.POST.get("shift")
        from_date = request.POST.get("from_date")
        to_date = request.POST.get("to_date")
        custom_name = request.POST.get("custom_name", "").strip()
        custom_start = request.POST.get("custom_start", "").strip()
        custom_end = request.POST.get("custom_end", "").strip()
        custom_color = request.POST.get("custom_color", "").strip()
 
        if not all([shift_value, from_date, to_date]):
            return JsonResponse(
                {"error": "shift, from_date and to_date are required"}, status=400
            )
 
        try:
            start_date = datetime.strptime(from_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(to_date, "%Y-%m-%d").date()
        except ValueError:
            return JsonResponse({"error": "Dates must be YYYY-MM-DD"}, status=400)
 
        if start_date > end_date:
            return JsonResponse({"error": "Invalid date range"}, status=400)
        if (end_date - start_date).days > MAX_RANGE_DAYS:
            return JsonResponse({"error": "Date range too large"}, status=400)
 
        # Make sure the staff member belongs to this hotel
        target_staff = Staff.objects.filter(id=req_staff_id, hotel_id=hotel_id).first()
        if not target_staff:
            return JsonResponse({"error": "Staff not found in this hotel"}, status=404)
 
        if not department_id:
            department_id = target_staff.department_id
        if not department_id:
            return JsonResponse({"error": "Department could not be resolved"}, status=400)
 
        # ── FIX ────────────────────────────────────────────────────
        # Only Custom shifts store their own times. Standard shifts
        # (Morning/Evening/Night) leave custom_* empty so they keep
        # following the Shift Timings templates when those are edited.
        parsed_start = parsed_end = None
        if shift_value == "Custom":
            if not (custom_start and custom_end):
                return JsonResponse(
                    {"error": "Custom shifts need a start and end time"}, status=400
                )
            try:
                parsed_start = datetime.strptime(custom_start, "%H:%M").time()
                parsed_end = datetime.strptime(custom_end, "%H:%M").time()
            except ValueError:
                return JsonResponse({"error": "Times must be HH:MM"}, status=400)
        else:
            custom_name = ""
            custom_color = ""
 
        created_count = updated_count = 0
        current = start_date
        while current <= end_date:
            _, created = Shift.objects.update_or_create(
                hotel_id=hotel_id,
                staff_id=target_staff.id,
                date=current,
                defaults={
                    "department_id": department_id,
                    "shift": shift_value,
                    "custom_name": custom_name or None,
                    "custom_start": parsed_start,
                    "custom_end": parsed_end,
                    "custom_color": custom_color or None,
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1
            current += timedelta(days=1)
 
        return JsonResponse({
            "success": True,
            "message": f"{created_count} shifts created, {updated_count} updated",
        })
 
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
 
 
@require_POST
def update_shift(request):
    """Change a shift's type. Switching to a standard shift clears custom times."""
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)
 
    shift_id = request.POST.get("shift_id")
    new_shift = request.POST.get("shift")
    if new_shift not in ("Morning", "Evening", "Night", "Custom"):
        return JsonResponse({"error": "Invalid shift type"}, status=400)
 
    try:
        shift = Shift.objects.get(id=shift_id, hotel_id=hotel_id)
    except (Shift.DoesNotExist, ValueError):
        return JsonResponse({"error": "Shift not found"}, status=404)
 
    if new_shift == "Custom" and not (shift.custom_start and shift.custom_end):
        return JsonResponse(
            {"error": "This shift has no custom times. Use Assign Shift to create a Custom shift."},
            status=400,
        )
 
    if new_shift != "Custom":
        shift.custom_name = None
        shift.custom_start = None
        shift.custom_end = None
        shift.custom_color = None
 
    shift.shift = new_shift
    shift.save()
    return JsonResponse({"success": True})


@require_POST
def assign_shift(request):
    try:
        hotel_id = request.session.get("hotel_id")
        logged_staff_id = request.session.get("staff_id")

        # =====================================================
        # LOGIN CHECK
        # =====================================================

        if not hotel_id and not logged_staff_id:
            return JsonResponse({
                "success": False,
                "error": "Login required"
            }, status=401)

        # Staff login -> resolve hotel
        if not hotel_id:
            try:
                logged_staff = Staff.objects.select_related(
                    "hotel"
                ).get(id=logged_staff_id)

                hotel_id = logged_staff.hotel_id

                request.session["hotel_id"] = hotel_id

            except Staff.DoesNotExist:
                return JsonResponse({
                    "success": False,
                    "error": "Staff not found"
                }, status=404)

        # =====================================================
        # ACCEPT JSON + OLD FORM POST
        # =====================================================

        data = {}

        if request.content_type and "application/json" in request.content_type:
            try:
                data = json.loads(request.body or "{}")
            except json.JSONDecodeError:
                return JsonResponse({
                    "success": False,
                    "error": "Invalid JSON"
                }, status=400)
        else:
            data = request.POST

        # =====================================================
        # GET VALUES
        # =====================================================

        target_staff_id = (
            data.get("staff_id")
            or data.get("staff")
        )

        shift_value = data.get("shift")

        # New JS sends date.
        single_date = data.get("date")

        # Old page may send range.
        from_date = (
            data.get("from_date")
            or single_date
        )

        to_date = (
            data.get("to_date")
            or single_date
        )

        department_id = data.get("department")

        custom_name = (
            data.get("custom_name") or ""
        ).strip()

        custom_start = (
            data.get("custom_start") or ""
        ).strip()

        custom_end = (
            data.get("custom_end") or ""
        ).strip()

        custom_color = (
            data.get("custom_color") or ""
        ).strip()

        # =====================================================
        # STAFF
        # =====================================================

        if not target_staff_id:

            # Staff users can default to themselves
            if logged_staff_id:
                target_staff_id = logged_staff_id

            else:
                return JsonResponse({
                    "success": False,
                    "error": "Employee is required"
                }, status=400)

        try:
            target_staff = Staff.objects.select_related(
                "department",
                "hotel"
            ).get(
                id=target_staff_id,
                hotel_id=hotel_id
            )

        except Staff.DoesNotExist:
            return JsonResponse({
                "success": False,
                "error": "Employee not found for this hotel"
            }, status=404)

        # =====================================================
        # VALIDATE SHIFT
        # =====================================================

        allowed_shifts = [
            "Morning",
            "Evening",
            "Night",
            "Custom",
        ]

        if shift_value not in allowed_shifts:
            return JsonResponse({
                "success": False,
                "error": "Invalid shift type"
            }, status=400)

        # =====================================================
        # DATES
        # =====================================================

        if not from_date or not to_date:
            return JsonResponse({
                "success": False,
                "error": "Shift date is required"
            }, status=400)

        try:
            start_date = datetime.strptime(
                from_date,
                "%Y-%m-%d"
            ).date()

            end_date = datetime.strptime(
                to_date,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            return JsonResponse({
                "success": False,
                "error": "Date must use YYYY-MM-DD format"
            }, status=400)

        if start_date > end_date:
            return JsonResponse({
                "success": False,
                "error": "From date cannot be after To date"
            }, status=400)

        # Safety limit
        if (end_date - start_date).days > 366:
            return JsonResponse({
                "success": False,
                "error": "Date range is too large"
            }, status=400)

        # =====================================================
        # DEPARTMENT
        # =====================================================

        if department_id:

            department = Department.objects.filter(
                id=department_id,
                hotel_id=hotel_id
            ).first()

            if not department:
                return JsonResponse({
                    "success": False,
                    "error": "Invalid department"
                }, status=400)

        else:
            department = target_staff.department

        if not department:
            return JsonResponse({
                "success": False,
                "error": "Employee has no department assigned"
            }, status=400)

        # =====================================================
        # CUSTOM SHIFT
        # =====================================================

        parsed_start = None
        parsed_end = None

        if shift_value == "Custom":

            if not custom_name:
                return JsonResponse({
                    "success": False,
                    "error": "Custom shift name is required"
                }, status=400)

            if not custom_start or not custom_end:
                return JsonResponse({
                    "success": False,
                    "error": "Custom start and end times are required"
                }, status=400)

            try:
                parsed_start = datetime.strptime(
                    custom_start,
                    "%H:%M"
                ).time()

                parsed_end = datetime.strptime(
                    custom_end,
                    "%H:%M"
                ).time()

            except ValueError:
                return JsonResponse({
                    "success": False,
                    "error": "Custom times must use HH:MM format"
                }, status=400)

        else:

            # =================================================
            # NORMAL SHIFT -> GET TEMPLATE TIME
            # =================================================

            template = ShiftTemplate.objects.filter(
                hotel_id=hotel_id,
                shift_name=shift_value,
                is_active=True
            ).first()

            if template:
                parsed_start = template.start_time
                parsed_end = template.end_time

        # =====================================================
        # CREATE / UPDATE
        # =====================================================

        current_date = start_date

        created_count = 0
        updated_count = 0

        created_ids = []

        while current_date <= end_date:

            shift_obj, created = Shift.objects.update_or_create(
                hotel_id=hotel_id,
                staff=target_staff,
                date=current_date,

                defaults={
                    "department": department,
                    "shift": shift_value,

                    "custom_name": (
                        custom_name
                        if shift_value == "Custom"
                        else None
                    ),

                    "custom_start": parsed_start,

                    "custom_end": parsed_end,

                    "custom_color": (
                        custom_color
                        if shift_value == "Custom"
                        else None
                    ),
                }
            )

            created_ids.append(shift_obj.id)

            if created:
                created_count += 1
            else:
                updated_count += 1

            current_date += timedelta(days=1)

        # =====================================================
        # RESPONSE
        # =====================================================

        return JsonResponse({
            "success": True,

            "message": (
                f"{created_count} shift(s) created, "
                f"{updated_count} shift(s) updated"
            ),

            "created": created_count,
            "updated": updated_count,
            "shift_ids": created_ids,
        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)

    
def weekly_schedule(request):
    staff_id  = request.session.get("staff_id")
    hotel_id  = request.session.get("hotel_id")
    start_date = request.GET.get("start_date")

   
    if not staff_id and not hotel_id:
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
        day           = s.date.strftime("%Y-%m-%d")
        st, et, color = get_times(s)
        data[day].append({
            "id":           s.id,
            "staff":        s.staff.name if s.staff else "N/A",
            "staff_id":     s.staff.id   if s.staff else None,
            "shift":        s.shift,
            "department":   s.department.name if s.department else "N/A",
            "department_id": s.department_id,
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




@require_POST
def update_shift(request):
    try:

        hotel_id = request.session.get("hotel_id")
        staff_id = request.session.get("staff_id")

        if not hotel_id and staff_id:

            current_staff = Staff.objects.filter(
                id=staff_id
            ).first()

            if current_staff:
                hotel_id = current_staff.hotel_id

        if not hotel_id:
            return JsonResponse({
                "success": False,
                "error": "Login required"
            }, status=401)

        # ==============================================
        # SUPPORT JSON + FORM POST
        # ==============================================

        if request.content_type and "application/json" in request.content_type:

            try:
                data = json.loads(
                    request.body or "{}"
                )

            except json.JSONDecodeError:

                return JsonResponse({
                    "success": False,
                    "error": "Invalid JSON"
                }, status=400)

        else:
            data = request.POST

        shift_id = data.get("shift_id")

        if not shift_id:

            return JsonResponse({
                "success": False,
                "error": "shift_id is required"
            }, status=400)

        try:

            shift_obj = Shift.objects.get(
                id=shift_id,
                hotel_id=hotel_id
            )

        except Shift.DoesNotExist:

            return JsonResponse({
                "success": False,
                "error": "Shift not found"
            }, status=404)

        # ==============================================
        # SHIFT TYPE
        # ==============================================

        new_shift = data.get("shift")

        if new_shift:

            if new_shift not in [
                "Morning",
                "Evening",
                "Night",
                "Custom"
            ]:

                return JsonResponse({
                    "success": False,
                    "error": "Invalid shift type"
                }, status=400)

            shift_obj.shift = new_shift

        # ==============================================
        # DATE
        # ==============================================

        date_value = data.get("date")

        if date_value:

            try:
                shift_obj.date = datetime.strptime(
                    date_value,
                    "%Y-%m-%d"
                ).date()

            except ValueError:

                return JsonResponse({
                    "success": False,
                    "error": "Invalid date"
                }, status=400)

        # ==============================================
        # CUSTOM SHIFT
        # ==============================================

        if shift_obj.shift == "Custom":

            custom_name = (
                data.get("custom_name") or ""
            ).strip()

            custom_start = (
                data.get("custom_start") or ""
            ).strip()

            custom_end = (
                data.get("custom_end") or ""
            ).strip()

            custom_color = (
                data.get("custom_color") or ""
            ).strip()

            if custom_name:
                shift_obj.custom_name = custom_name

            if custom_start:

                try:
                    shift_obj.custom_start = datetime.strptime(
                        custom_start,
                        "%H:%M"
                    ).time()

                except ValueError:

                    return JsonResponse({
                        "success": False,
                        "error": "Invalid custom start time"
                    }, status=400)

            if custom_end:

                try:
                    shift_obj.custom_end = datetime.strptime(
                        custom_end,
                        "%H:%M"
                    ).time()

                except ValueError:

                    return JsonResponse({
                        "success": False,
                        "error": "Invalid custom end time"
                    }, status=400)

            if custom_color:
                shift_obj.custom_color = custom_color

        else:

            # Remove old custom information if converted
            # from Custom -> Morning/Evening/Night.

            shift_obj.custom_name = None
            shift_obj.custom_start = None
            shift_obj.custom_end = None
            shift_obj.custom_color = None

        shift_obj.save()

        return JsonResponse({
            "success": True,
            "message": "Shift updated successfully",
            "shift_id": shift_obj.id
        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)





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



# ============================================================
# UPDATE LOGGED-IN STAFF PROFILE
# ============================================================

from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import staff_login_required
from accounts.models import Staff


@require_POST
@staff_login_required
def update_staff_profile(request):

    try:

        # =====================================================
        # CURRENT STAFF
        # =====================================================

        staff_id = request.session.get("staff_id")

        if not staff_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Login required."
                },
                status=401,
            )

        staff = get_object_or_404(
            Staff.objects.select_related(
                "user",
                "department",
                "hotel",
            ),
            id=staff_id,
        )

        user = staff.user

        if not user:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Login account is not connected to this employee."
                },
                status=400,
            )

        # =====================================================
        # PROFILE VALUES
        # =====================================================

        name = (
            request.POST.get("name", "")
            or ""
        ).strip()

        phone = (
            request.POST.get("phone", "")
            or ""
        ).strip()

        email = (
            request.POST.get("email", "")
            or ""
        ).strip()

        # =====================================================
        # VALIDATION
        # =====================================================

        if not name:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Name is required."
                },
                status=400,
            )

        if not email:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Email address is required."
                },
                status=400,
            )

        # =====================================================
        # UPDATE BASIC PROFILE
        # =====================================================

        staff.name = name
        staff.phone = phone

        user.email = email

        # =====================================================
        # PROFILE PHOTO
        # =====================================================

        photo = request.FILES.get("photo")

        if photo:

            # Maximum 5 MB
            if photo.size > 5 * 1024 * 1024:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Profile photo must be smaller than 5 MB."
                    },
                    status=400,
                )

            allowed_types = [
                "image/jpeg",
                "image/png",
                "image/webp",
            ]

            if (
                hasattr(photo, "content_type")
                and photo.content_type not in allowed_types
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Only JPG, PNG or WEBP images are allowed."
                    },
                    status=400,
                )

            staff.photo = photo

        # =====================================================
        # PASSWORD CHANGE
        # =====================================================

        current_password = (
            request.POST.get("current_password", "")
            or ""
        )

        new_password = (
            request.POST.get("new_password", "")
            or ""
        )

        confirm_password = (
            request.POST.get("confirm_password", "")
            or ""
        )

        # Password fields are optional.
        # Only process them when user enters a new password.

        if new_password:

            if not current_password:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Enter your current password."
                    },
                    status=400,
                )

            if not user.check_password(current_password):

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Current password is incorrect."
                    },
                    status=400,
                )

            if new_password != confirm_password:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "New password and confirmation do not match."
                    },
                    status=400,
                )

            if len(new_password) < 8:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "New password must contain at least 8 characters."
                    },
                    status=400,
                )

            user.set_password(new_password)

        # =====================================================
        # SAVE
        # =====================================================

        user.save()
        staff.save()

        # =====================================================
        # PHOTO URL
        # =====================================================

        photo_url = None

        try:
            if staff.photo:
                photo_url = staff.photo.url
        except Exception:
            photo_url = None

        # =====================================================
        # RESPONSE
        # =====================================================

        return JsonResponse(
            {
                "success": True,
                "message": "Profile updated successfully.",
                "profile": {
                    "name": staff.name,
                    "phone": staff.phone or "",
                    "email": user.email or "",
                    "photo": photo_url,
                },
                # Keep old response fields for compatibility
                "name": staff.name,
                "email": user.email or "",
                "photo": photo_url,
            }
        )

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )


#----------------------HOUSEKEEPING MODULE----------------------
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils import timezone
from accounts.decorators import staff_login_required




@never_cache
@staff_login_required
def housekeeping_dashboard(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")


    context = _housekeeping_common_context(
        staff
    )


    # ========================================================
    # ALL ROOM UNITS
    # ========================================================

    units = (
        RoomUnit.objects
        .select_related("room")
        .all()
        .order_by("room_number")
    )


    # ========================================================
    # CURRENT HOUSEKEEPING TASKS
    # ========================================================

    active_tasks = (
        Task.objects
        .filter(
            staff=staff,
            room_unit__isnull=False,
        )
        .exclude(
            status__iexact="Completed"
        )
        .select_related(
            "room",
            "room_unit",
        )
        .order_by("-created_at")
    )


    task_map = {}

    for task in active_tasks:

        if (
            task.room_unit_id
            and
            task.room_unit_id
            not in task_map
        ):

            task_map[
                task.room_unit_id
            ] = task


    # ========================================================
    # BUILD ROOM DATA
    # ========================================================

    rooms = []

    for unit in units:

        task = task_map.get(
            unit.id
        )

        status = (
            unit.status or ""
        ).strip()

        rooms.append({

            "id": unit.id,

            "number": (
                unit.room_number
            ),

            "room_type": (
                unit.room.room_type
                if unit.room
                else "Standard"
            ),

            "status": (
                status.lower()
            ),

            "status_display": (
                status or "Unknown"
            ),

            "task_id": (
                task.id
                if task
                else None
            ),

            "task_title": (
                task.title
                if task
                else ""
            ),

            "task_status": (
                task.status
                if task
                else ""
            ),

        })


    context.update({

        "rooms": rooms,

        "all_tasks": (
            Task.objects
            .filter(staff=staff)
            .select_related(
                "room",
                "room_unit",
            )
            .order_by(
                "-created_at"
            )
        ),

    })


    return render(
        request,
        "housekeeping/dashboard.html",
        context,
    )



from calendar import month_name
from datetime import datetime

from django.conf import settings
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache


# ============================================================
# SAFE DATETIME FORMATTER
# ============================================================

from calendar import month_name
from datetime import datetime

from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache


# ============================================================
# SAFE ATTENDANCE DATETIME FORMATTER
# ============================================================

def housekeeping_format_datetime(value, fmt="%I:%M %p"):
    """
    Safely format Attendance datetime values.

    We intentionally DO NOT call timezone.localtime()
    because this project contains naive datetime values.
    """

    if not value:
        return ""

    try:
        return value.strftime(fmt)
    except (AttributeError, TypeError, ValueError):
        return str(value)


# ============================================================
# HOUSEKEEPING ATTENDANCE
# ============================================================

@never_cache
@staff_login_required
def housekeeping_attendance(request):

    # --------------------------------------------------------
    # STAFF
    # --------------------------------------------------------

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    # --------------------------------------------------------
    # TODAY
    # --------------------------------------------------------
    # DO NOT USE:
    #
    #     timezone.localdate()
    #
    # because localdate() internally calls localtime().
    # --------------------------------------------------------

    today = timezone.now().date()

    # --------------------------------------------------------
    # MONTH
    # --------------------------------------------------------

    try:
        selected_month = int(
            request.GET.get(
                "month",
                today.month
            )
        )
    except (TypeError, ValueError):
        selected_month = today.month

    if selected_month < 1 or selected_month > 12:
        selected_month = today.month

    # --------------------------------------------------------
    # YEAR
    # --------------------------------------------------------

    try:
        selected_year = int(
            request.GET.get(
                "year",
                today.year
            )
        )
    except (TypeError, ValueError):
        selected_year = today.year

    # --------------------------------------------------------
    # FILTER OPTIONS
    # --------------------------------------------------------

    months = [
        (number, month_name[number])
        for number in range(1, 13)
    ]

    years = list(
        range(
            today.year - 3,
            today.year + 2
        )
    )

    # --------------------------------------------------------
    # ATTENDANCE RECORDS
    # --------------------------------------------------------

    attendance_records_qs = (
        Attendance.objects
        .filter(
            staff=staff,
            date__year=selected_year,
            date__month=selected_month,
        )
        .order_by("-date")
    )

    # --------------------------------------------------------
    # TODAY ATTENDANCE
    # --------------------------------------------------------

    today_attendance = (
        Attendance.objects
        .filter(
            staff=staff,
            date=today,
        )
        .first()
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    total_records = attendance_records_qs.count()

    present_days = attendance_records_qs.filter(
        status__iexact="Present"
    ).count()

    late_days = attendance_records_qs.filter(
        status__iexact="Late"
    ).count()

    absent_days = attendance_records_qs.filter(
        status__iexact="Absent"
    ).count()

    # --------------------------------------------------------
    # OVERTIME
    # --------------------------------------------------------

    overtime_hours = 0.0

    for record in attendance_records_qs:
        try:
            overtime_hours += float(
                record.overtime_hours or 0
            )
        except (TypeError, ValueError):
            pass

    overtime_hours = round(
        overtime_hours,
        2
    )

    # --------------------------------------------------------
    # ATTENDANCE TABLE
    # --------------------------------------------------------

    attendance_records = []

    for record in attendance_records_qs:

        attendance_records.append({
            "id": record.id,

            "date": record.date,

            "status": record.status or "",

            "overtime_hours":
                record.overtime_hours or 0,

            "check_in":
                housekeeping_format_datetime(
                    record.check_in
                ),

            "check_out":
                housekeeping_format_datetime(
                    record.check_out
                ),
        })

    # --------------------------------------------------------
    # TODAY CHECK-IN / CHECK-OUT
    # --------------------------------------------------------

    today_check_in = ""
    today_check_out = ""

    has_checked_in = False
    has_checked_out = False

    if today_attendance:

        has_checked_in = bool(
            today_attendance.check_in
        )

        has_checked_out = bool(
            today_attendance.check_out
        )

        today_check_in = (
            housekeeping_format_datetime(
                today_attendance.check_in
            )
            if today_attendance.check_in
            else ""
        )

        today_check_out = (
            housekeeping_format_datetime(
                today_attendance.check_out
            )
            if today_attendance.check_out
            else ""
        )

    # --------------------------------------------------------
    # FACE DESCRIPTORS
    # --------------------------------------------------------

    descriptors = normalize_descriptors(
        getattr(
            staff,
            "face_descriptor",
            None
        )
    )

    face_enrolled = bool(descriptors)

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    context = {

        "staff":
            staff,

        "hotel":
            getattr(staff, "hotel", None),

        "today":
            today,

        "today_attendance":
            today_attendance,

        "today_check_in":
            today_check_in,

        "today_check_out":
            today_check_out,

        "has_checked_in":
            has_checked_in,

        "has_checked_out":
            has_checked_out,

        "attendance_records":
            attendance_records,

        "total_records":
            total_records,

        "present_days":
            present_days,

        "late_days":
            late_days,

        "absent_days":
            absent_days,

        "overtime_hours":
            overtime_hours,

        "months":
            months,

        "years":
            years,

        "selected_month":
            selected_month,

        "selected_year":
            selected_year,

        "face_enrolled":
            face_enrolled,

        "face_descriptor_json":
            json.dumps(descriptors),

        "face_threshold":
            FACE_MATCH_THRESHOLD,

        "active_housekeeping_page":
            "attendance",
    }

    return render(
        request,
        "housekeeping/attendance.html",
        context,
    )





import json
import math

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST


def _housekeeping_face_distance(face1, face2):
    """
    Euclidean distance between two face-api.js
    128-value descriptors.
    """

    if (
        not isinstance(face1, list)
        or not isinstance(face2, list)
        or len(face1) != 128
        or len(face2) != 128
    ):
        return float("inf")

    try:
        return math.sqrt(
            sum(
                (float(a) - float(b)) ** 2
                for a, b in zip(face1, face2)
            )
        )

    except (TypeError, ValueError):
        return float("inf")


@staff_login_required
@never_cache
@require_POST
def housekeeping_mark_attendance(request):

    # ============================================================
    # 1. GET LOGGED-IN HOUSEKEEPING STAFF
    # ============================================================

    staff = _get_housekeeping_staff(request)

    if not staff:
        return JsonResponse(
            {
                "success": False,
                "matched": False,
                "message": "Your session has expired or Housekeeping access is required.",
            },
            status=403,
        )

    # ============================================================
    # 2. ACTION
    # ============================================================

    action = (
        request.POST.get("action")
        or ""
    ).strip().lower()

    if action not in ("check_in", "check_out"):
        return JsonResponse(
            {
                "success": False,
                "matched": False,
                "message": "Invalid attendance action.",
            },
            status=400,
        )

    # ============================================================
    # 3. CURRENT DATE / TIME
    # ============================================================

    now = timezone.now()

    # IMPORTANT:
    # Do NOT use timezone.localdate().
    #
    # Your project has already shown that timezone.localdate()
    # causes:
    # localtime() cannot be applied to a naive datetime
    if timezone.is_aware(now):
        try:
            today = timezone.localtime(now).date()
        except ValueError:
            today = now.date()
    else:
        today = now.date()

    # ============================================================
    # 4. CHECK IN
    # ============================================================

    if action == "check_in":

        # --------------------------------------------------------
        # REGISTERED FACE DESCRIPTORS
        # --------------------------------------------------------

        stored_faces = normalize_descriptors(
            getattr(
                staff,
                "face_descriptor",
                None,
            )
        )

        if not stored_faces:
            return JsonResponse(
                {
                    "success": False,
                    "matched": False,
                    "code": "FACE_NOT_REGISTERED",
                    "message":
                        "Your face is not registered. Please ask HR/Admin to register your face.",
                },
                status=400,
            )

        # --------------------------------------------------------
        # DESCRIPTOR FROM CAMERA
        # --------------------------------------------------------

        raw_descriptor = request.POST.get(
            "face_descriptor"
        )

        if not raw_descriptor:
            return JsonResponse(
                {
                    "success": False,
                    "matched": False,
                    "code": "FACE_REQUIRED",
                    "message":
                        "Face verification is required for check-in.",
                },
                status=400,
            )

        # --------------------------------------------------------
        # PARSE JSON
        # --------------------------------------------------------

        try:
            incoming_face = json.loads(
                raw_descriptor
            )

        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            return JsonResponse(
                {
                    "success": False,
                    "matched": False,
                    "code": "INVALID_FACE_DATA",
                    "message": "Invalid face data received from camera.",
                },
                status=400,
            )

        # --------------------------------------------------------
        # VALIDATE DESCRIPTOR
        # --------------------------------------------------------

        if (
            not isinstance(incoming_face, list)
            or len(incoming_face) != 128
            or not all(
                isinstance(value, (int, float))
                for value in incoming_face
            )
        ):
            return JsonResponse(
                {
                    "success": False,
                    "matched": False,
                    "code": "INVALID_FACE_DATA",
                    "message":
                        "Invalid face descriptor received from camera.",
                },
                status=400,
            )

        # --------------------------------------------------------
        # SERVER-SIDE FACE MATCH
        # --------------------------------------------------------

        distances = []

        for stored_face in stored_faces:

            distance = _housekeeping_face_distance(
                incoming_face,
                stored_face,
            )

            distances.append(distance)

        if not distances:
            return JsonResponse(
                {
                    "success": False,
                    "matched": False,
                    "code": "FACE_NOT_REGISTERED",
                    "message":
                        "No valid registered face descriptor was found.",
                },
                status=400,
            )

        best_distance = min(distances)

        # IMPORTANT:
        # Use your project's EXISTING threshold.
        threshold = float(FACE_MATCH_THRESHOLD)

        # Helpful while testing.
        print(
            "HOUSEKEEPING FACE DEBUG:",
            {
                "staff_id": staff.id,
                "staff_name": staff.name,
                "registered_faces": len(stored_faces),
                "incoming_length": len(incoming_face),
                "best_distance": best_distance,
                "threshold": threshold,
            }
        )

        if best_distance > threshold:

            return JsonResponse(
                {
                    "success": False,
                    "matched": False,
                    "code": "FACE_NOT_MATCHED",
                    "message":
                        "Face does not match the registered employee.",
                    "distance": round(
                        best_distance,
                        4,
                    ),
                    "threshold": threshold,
                },
                status=403,
            )

        # --------------------------------------------------------
        # CREATE / GET TODAY ATTENDANCE
        # --------------------------------------------------------

        attendance, created = (
            Attendance.objects.get_or_create(
                staff=staff,
                hotel=staff.hotel,
                date=today,
                defaults={
                "status": "Present",
               },
            )
        )

        # --------------------------------------------------------
        # ALREADY CHECKED IN
        # --------------------------------------------------------

        if attendance.check_in:

            return JsonResponse(
                {
                    "success": False,
                    "matched": True,
                    "code": "ALREADY_CHECKED_IN",
                    "message":
                        "You have already checked in today.",
                },
                status=400,
            )

        # --------------------------------------------------------
        # SAVE CHECK-IN
        # --------------------------------------------------------

        attendance.check_in = now

        if not attendance.status:
            attendance.status = "Present"

        attendance.save()

        return JsonResponse(
            {
                "success": True,
                "matched": True,
                "message":
                    "Face verified. Checked in successfully.",
                "check_in":
                    now.strftime("%I:%M %p"),
                "distance":
                    round(best_distance, 4),
            }
        )

    # ============================================================
    # 5. CHECK OUT
    # ============================================================

    attendance = (
        Attendance.objects
        .filter(
             staff=staff,
             hotel=staff.hotel,
             date=today,
        )
        .first()
    )

    if not attendance:

        return JsonResponse(
            {
                "success": False,
                "message":
                    "You have not checked in today.",
            },
            status=400,
        )

    if not attendance.check_in:

        return JsonResponse(
            {
                "success": False,
                "message":
                    "You must check in before checking out.",
            },
            status=400,
        )

    if attendance.check_out:

        return JsonResponse(
            {
                "success": False,
                "message":
                    "You have already checked out today.",
            },
            status=400,
        )

    # ============================================================
    # 6. SAVE CHECK OUT
    # ============================================================

    attendance.check_out = now

    # ------------------------------------------------------------
    # CALCULATE OVERTIME
    # ------------------------------------------------------------

    try:

        worked_seconds = (
            attendance.check_out
            - attendance.check_in
        ).total_seconds()

        worked_hours = (
            worked_seconds / 3600
        )

        attendance.overtime_hours = max(
            round(
                worked_hours - 8,
                2,
            ),
            0,
        )

    except Exception:

        # Do not prevent checkout if old attendance datetime
        # values are incompatible.
        pass

    attendance.save()

    return JsonResponse(
        {
            "success": True,
            "message":
                "Checked out successfully.",
            "check_out":
                now.strftime("%I:%M %p"),
        }
    )





# ============================================================
# HOUSEKEEPING - MY SHIFTS
# ============================================================

@never_cache
@staff_login_required
def housekeeping_shifts(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    today = timezone.now().date()

    # --------------------------------------------------------
    # WEEK
    # --------------------------------------------------------

    start_date_string = request.GET.get("start_date")

    if start_date_string:
        try:
            week_start = datetime.strptime(
                start_date_string,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            week_start = today - timedelta(
                days=today.weekday()
            )

    else:
        week_start = today - timedelta(
            days=today.weekday()
        )

    week_end = week_start + timedelta(days=6)

    # --------------------------------------------------------
    # STAFF SHIFTS ONLY
    # --------------------------------------------------------

    shifts = (
        Shift.objects
        .filter(
            staff=staff,
            date__range=[
                week_start,
                week_end,
            ],
        )
        .select_related(
            "department",
        )
        .order_by(
            "date",
        )
    )

    # --------------------------------------------------------
    # SHIFT TEMPLATES
    # --------------------------------------------------------

    templates = {
        template.shift_name: template
        for template in ShiftTemplate.objects.filter(
            hotel_id=staff.hotel_id,
            is_active=True,
        )
    }

    default_times = {
        "Morning": (
            "06:00",
            "14:00",
        ),
        "Evening": (
            "14:00",
            "22:00",
        ),
        "Night": (
            "22:00",
            "06:00",
        ),
    }

    # --------------------------------------------------------
    # BUILD WEEK
    # --------------------------------------------------------

    week_days = []

    for i in range(7):

        current_date = (
            week_start
            + timedelta(days=i)
        )

        day_shifts = []

        for shift in shifts:

            if shift.date != current_date:
                continue

            start_time = ""
            end_time = ""

            if shift.custom_start:

                start_time = (
                    shift.custom_start
                    .strftime("%I:%M %p")
                )

                if shift.custom_end:
                    end_time = (
                        shift.custom_end
                        .strftime("%I:%M %p")
                    )

            else:

                template = templates.get(
                    shift.shift
                )

                if template:

                    start_time = (
                        template.start_time
                        .strftime("%I:%M %p")
                    )

                    end_time = (
                        template.end_time
                        .strftime("%I:%M %p")
                    )

                else:

                    default = default_times.get(
                        shift.shift
                    )

                    if default:

                        start_time = (
                            datetime.strptime(
                                default[0],
                                "%H:%M"
                            )
                            .strftime("%I:%M %p")
                        )

                        end_time = (
                            datetime.strptime(
                                default[1],
                                "%H:%M"
                            )
                            .strftime("%I:%M %p")
                        )

            day_shifts.append({
                "id": shift.id,
                "shift": shift.shift,
                "name": (
                    shift.custom_name
                    if shift.shift == "Custom"
                    and shift.custom_name
                    else shift.shift
                ),
                "start_time": start_time,
                "end_time": end_time,
                "department": (
                    shift.department.name
                    if shift.department
                    else ""
                ),
            })

        week_days.append({
            "date": current_date,
            "is_today": (
                current_date == today
            ),
            "shifts": day_shifts,
        })

    context = {
        "staff": staff,
        "hotel": staff.hotel,

        "today": today,

        "week_start": week_start,
        "week_end": week_end,

        "previous_week": (
            week_start
            - timedelta(days=7)
        ),

        "next_week": (
            week_start
            + timedelta(days=7)
        ),

        "week_days": week_days,

        "total_week_shifts":
            shifts.count(),

        "active_housekeeping_page":
            "shifts",
    }

    return render(
        request,
        "housekeeping/shifts.html",
        context,
    )



# ============================================================
# HOUSEKEEPING - LEAVE
# ============================================================

@never_cache
@staff_login_required
def housekeeping_leave(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    leave_requests = (
        LeaveRequest.objects
        .filter(
            staff=staff
        )
        .order_by(
            "-applied_at"
        )
    )

    context = {
        "staff": staff,
        "hotel": staff.hotel,

        "leave_requests":
            leave_requests,

        "total_leave_requests":
            leave_requests.count(),

        "pending_leave_requests":
            leave_requests.filter(
                status__iexact="Pending"
            ).count(),

        "approved_leave_requests":
            leave_requests.filter(
                status__iexact="Approved"
            ).count(),

        "rejected_leave_requests":
            leave_requests.filter(
                status__iexact="Rejected"
            ).count(),

        "active_housekeeping_page":
            "leave",
    }

    return render(
        request,
        "housekeeping/leave.html",
        context,
    )



# ============================================================
# HOUSEKEEPING - PROFILE
# ============================================================

@never_cache
@staff_login_required
def housekeeping_profile(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = {
        "staff": staff,

        "hotel":
            staff.hotel,

        "department":
            staff.department,

        "user":
            staff.user,

        "active_housekeeping_page":
            "profile",
    }

    return render(
        request,
        "housekeeping/profile.html",
        context,
    )    



# ============================================================
# HOUSEKEEPING - MY WORK REPORT
# ============================================================

# ============================================================
# HOUSEKEEPING REPORTS
# ============================================================


def _housekeeping_report_date_range(request):
    """
    Return the requested report date range.

    Default:
        From = first day of current month
        To   = today
    """

    today = timezone.now().date()
    first_day = today.replace(day=1)

    start_raw = (request.GET.get("start_date") or "").strip()
    end_raw = (request.GET.get("end_date") or "").strip()

    try:
        start_date = datetime.strptime(
            start_raw,
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        start_date = first_day

    try:
        end_date = datetime.strptime(
            end_raw,
            "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        end_date = today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


# ============================================================
# 1. HOUSEKEEPING REPORT PAGE
# ============================================================

@never_cache
@staff_login_required
def housekeeping_reports(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    today = timezone.now().date()
    first_day = today.replace(day=1)

    context = _housekeeping_common_context(staff)

    context.update({
        "staff": staff,
        "hotel": staff.hotel,

        "active_housekeeping_page": "reports",

        "report_start_date":
            first_day.strftime("%Y-%m-%d"),

        "report_end_date":
            today.strftime("%Y-%m-%d"),
    })

    return render(
        request,
        "housekeeping/reports.html",
        context,
    )


# ============================================================
# 2. HOUSEKEEPING REPORT DATA API
# ============================================================

@require_GET
@never_cache
@staff_login_required
def housekeeping_reports_data(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return JsonResponse(
            {
                "success": False,
                "error": "Housekeeping staff not found.",
            },
            status=403,
        )

    start_date, end_date = (
        _housekeeping_report_date_range(request)
    )

    # ========================================================
    # ATTENDANCE
    # ========================================================

    attendance_qs = (
        Attendance.objects
        .filter(
            staff=staff,
            date__range=[
                start_date,
                end_date,
            ],
        )
        .order_by("-date")
    )

    attendance_stats = attendance_qs.aggregate(

        present=Count(
            "id",
            filter=Q(status="Present"),
        ),

        late=Count(
            "id",
            filter=Q(status="Late"),
        ),

        absent=Count(
            "id",
            filter=Q(status="Absent"),
        ),

        half_day=Count(
            "id",
            filter=Q(status="Half Day"),
        ),

        overtime=Sum(
            "overtime_hours"
        ),
    )

    # ========================================================
    # TASKS
    # ========================================================

    task_qs = (
        Task.objects
        .filter(
            staff=staff,
            created_at__date__range=[
                start_date,
                end_date,
            ],
        )
        .select_related(
            "room",
            "room_unit",
        )
        .order_by("-created_at")
    )

    task_stats = task_qs.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="Pending"),
        ),

        in_progress=Count(
            "id",
            filter=Q(status="In Progress"),
        ),

        completed=Count(
            "id",
            filter=Q(status="Completed"),
        ),
    )

    # ========================================================
    # LEAVE
    # ========================================================

    leave_qs = (
        LeaveRequest.objects
        .filter(
            staff=staff,

            # Leave overlaps selected period
            from_date__lte=end_date,
            to_date__gte=start_date,
        )
        .order_by("-applied_at")
    )

    leave_stats = leave_qs.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="Pending"),
        ),

        approved=Count(
            "id",
            filter=Q(status="Approved"),
        ),

        rejected=Count(
            "id",
            filter=Q(status="Rejected"),
        ),
    )

    # ========================================================
    # ATTENDANCE TABLE
    # ========================================================

    attendance_records = []

    for attendance in attendance_qs:

        attendance_records.append({
            "id":
                attendance.id,

            "date":
                attendance.date.strftime("%Y-%m-%d")
                if attendance.date
                else "",

            "check_in":
                attendance.check_in.strftime("%I:%M %p")
                if attendance.check_in
                else "—",

            "check_out":
                attendance.check_out.strftime("%I:%M %p")
                if attendance.check_out
                else "—",

            "status":
                attendance.status or "—",

            "overtime":
                float(
                    attendance.overtime_hours or 0
                ),
        })

    # ========================================================
    # TASK TABLE
    # ========================================================

    task_records = []

    for task in task_qs:

        room_number = "—"

        if task.room_unit:
            room_number = (
                task.room_unit.room_number
            )

        task_records.append({
            "id":
                task.id,

            "title":
                task.title or "—",

            "room":
                room_number,

            "status":
                task.status or "—",

            "created_at":
                task.created_at.strftime(
                    "%Y-%m-%d"
                )
                if task.created_at
                else "",
        })

    # ========================================================
    # LEAVE TABLE
    # ========================================================

    leave_records = []

    for leave in leave_qs:

        leave_records.append({
            "id":
                leave.id,

            "from_date":
                leave.from_date.strftime(
                    "%Y-%m-%d"
                )
                if leave.from_date
                else "",

            "to_date":
                leave.to_date.strftime(
                    "%Y-%m-%d"
                )
                if leave.to_date
                else "",

            "reason":
                leave.reason or "",

            "status":
                leave.status or "Pending",
        })

    # ========================================================
    # JSON RESPONSE
    # ========================================================

    return JsonResponse({

        "success": True,

        "filters": {
            "start_date":
                start_date.strftime("%Y-%m-%d"),

            "end_date":
                end_date.strftime("%Y-%m-%d"),
        },

        "employee": {
            "id":
                staff.id,

            "name":
                staff.name,

            "department":
                staff.department.name
                if staff.department
                else "Housekeeping",
        },

        "attendance": {

            "present":
                attendance_stats.get(
                    "present"
                ) or 0,

            "late":
                attendance_stats.get(
                    "late"
                ) or 0,

            "absent":
                attendance_stats.get(
                    "absent"
                ) or 0,

            "half_day":
                attendance_stats.get(
                    "half_day"
                ) or 0,

            "overtime":
                float(
                    attendance_stats.get(
                        "overtime"
                    ) or 0
                ),
        },

        "tasks": {

            "total":
                task_stats.get(
                    "total"
                ) or 0,

            "pending":
                task_stats.get(
                    "pending"
                ) or 0,

            "in_progress":
                task_stats.get(
                    "in_progress"
                ) or 0,

            "completed":
                task_stats.get(
                    "completed"
                ) or 0,
        },

        "leaves": {

            "total":
                leave_stats.get(
                    "total"
                ) or 0,

            "pending":
                leave_stats.get(
                    "pending"
                ) or 0,

            "approved":
                leave_stats.get(
                    "approved"
                ) or 0,

            "rejected":
                leave_stats.get(
                    "rejected"
                ) or 0,
        },

        "attendance_records":
            attendance_records,

        "task_records":
            task_records,

        "leave_records":
            leave_records,
    })


# ============================================================
# 3. HOUSEKEEPING REPORT CSV EXPORT
# ============================================================

@require_GET
@never_cache
@staff_login_required
def housekeeping_reports_export_csv(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return HttpResponse(
            "Housekeeping staff not found.",
            status=403,
        )

    start_date, end_date = (
        _housekeeping_report_date_range(request)
    )

    # ========================================================
    # GET DATA
    # ========================================================

    attendance_qs = (
        Attendance.objects
        .filter(
            staff=staff,
            date__range=[
                start_date,
                end_date,
            ],
        )
        .order_by("date")
    )

    task_qs = (
        Task.objects
        .filter(
            staff=staff,
            created_at__date__range=[
                start_date,
                end_date,
            ],
        )
        .select_related(
            "room",
            "room_unit",
        )
        .order_by("created_at")
    )

    leave_qs = (
        LeaveRequest.objects
        .filter(
            staff=staff,
            from_date__lte=end_date,
            to_date__gte=start_date,
        )
        .order_by("from_date")
    )

    # ========================================================
    # CREATE CSV RESPONSE
    # ========================================================

    filename = (
        "housekeeping_report_"
        f"{start_date}_"
        f"{end_date}.csv"
    )

    response = HttpResponse(
        content_type=(
            "text/csv; charset=utf-8"
        )
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; filename="{filename}"'
    )

    # Excel UTF-8 support
    response.write("\ufeff")

    writer = csv.writer(response)

    # ========================================================
    # EMPLOYEE INFORMATION
    # ========================================================

    writer.writerow([
        "HOUSEKEEPING REPORT"
    ])

    writer.writerow([])

    writer.writerow([
        "Employee",
        staff.name,
    ])

    writer.writerow([
        "Department",
        (
            staff.department.name
            if staff.department
            else "Housekeeping"
        ),
    ])

    writer.writerow([
        "Hotel",
        (
            staff.hotel.name
            if staff.hotel
            else ""
        ),
    ])

    writer.writerow([
        "From Date",
        start_date.strftime(
            "%d-%m-%Y"
        ),
    ])

    writer.writerow([
        "To Date",
        end_date.strftime(
            "%d-%m-%Y"
        ),
    ])

    writer.writerow([])
    writer.writerow([])

    # ========================================================
    # ATTENDANCE
    # ========================================================

    writer.writerow([
        "ATTENDANCE"
    ])

    writer.writerow([
        "Date",
        "Check In",
        "Check Out",
        "Status",
        "Overtime Hours",
    ])

    for attendance in attendance_qs:

        writer.writerow([

            attendance.date.strftime(
                "%d-%m-%Y"
            )
            if attendance.date
            else "",

            attendance.check_in.strftime(
                "%I:%M %p"
            )
            if attendance.check_in
            else "",

            attendance.check_out.strftime(
                "%I:%M %p"
            )
            if attendance.check_out
            else "",

            attendance.status or "",

            attendance.overtime_hours or 0,
        ])

    writer.writerow([])
    writer.writerow([])

    # ========================================================
    # TASKS
    # ========================================================

    writer.writerow([
        "TASKS"
    ])

    writer.writerow([
        "Task",
        "Room",
        "Status",
        "Created Date",
    ])

    for task in task_qs:

        room_number = ""

        if task.room_unit:
            room_number = (
                task.room_unit.room_number
            )

        writer.writerow([

            task.title or "",

            room_number,

            task.status or "",

            task.created_at.strftime(
                "%d-%m-%Y"
            )
            if task.created_at
            else "",
        ])

    writer.writerow([])
    writer.writerow([])

    # ========================================================
    # LEAVE
    # ========================================================

    writer.writerow([
        "LEAVE"
    ])

    writer.writerow([
        "From Date",
        "To Date",
        "Reason",
        "Status",
    ])

    for leave in leave_qs:

        writer.writerow([

            leave.from_date.strftime(
                "%d-%m-%Y"
            )
            if leave.from_date
            else "",

            leave.to_date.strftime(
                "%d-%m-%Y"
            )
            if leave.to_date
            else "",

            leave.reason or "",

            leave.status or "Pending",
        ])

    return response


# ============================================================
# HOUSEKEEPING REPORTS
# ============================================================

import csv

from datetime import datetime, timedelta

from django.db.models import Count, Sum, Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET


# ============================================================
# REPORT DATE HELPER
# ============================================================

def _housekeeping_report_dates(request):

    today = timezone.now().date()

    default_start = today.replace(day=1)

    start_raw = (
        request.GET.get("start_date")
        or ""
    ).strip()

    end_raw = (
        request.GET.get("end_date")
        or ""
    ).strip()

    try:
        start_date = datetime.strptime(
            start_raw,
            "%Y-%m-%d",
        ).date()
    except (ValueError, TypeError):
        start_date = default_start

    try:
        end_date = datetime.strptime(
            end_raw,
            "%Y-%m-%d",
        ).date()
    except (ValueError, TypeError):
        end_date = today

    if start_date > end_date:
        start_date, end_date = (
            end_date,
            start_date,
        )

    return start_date, end_date


# ============================================================
# REPORT PAGE
# ============================================================

@staff_login_required
def housekeeping_reports_page(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:

        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        request.session.flush()
        return redirect("staff_login")

    today = timezone.now().date()

    start_date = today.replace(day=1)

    return render(
        request,
        "housekeeping/reports.html",
        {
            "staff": staff,
            "hotel": staff.hotel,

            "report_start_date":
                start_date.strftime("%Y-%m-%d"),

            "report_end_date":
                today.strftime("%Y-%m-%d"),
        },
    )


# ============================================================
# REPORT DATA
# ============================================================

@require_GET
@staff_login_required
def housekeeping_reports_data(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:

        return JsonResponse(
            {
                "success": False,
                "error": "Session expired.",
            },
            status=401,
        )

    try:

        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Staff not found.",
            },
            status=404,
        )

    start_date, end_date = (
        _housekeeping_report_dates(request)
    )

    hotel = staff.hotel

    # ========================================================
    # ATTENDANCE
    # ========================================================

    attendance_qs = (
        Attendance.objects
        .filter(
            staff=staff,
            hotel=hotel,
            date__range=(
                start_date,
                end_date,
            ),
        )
        .order_by("-date")
    )

    attendance_stats = attendance_qs.aggregate(

        present=Count(
            "id",
            filter=Q(status="Present"),
        ),

        late=Count(
            "id",
            filter=Q(status="Late"),
        ),

        absent=Count(
            "id",
            filter=Q(status="Absent"),
        ),

        half_day=Count(
            "id",
            filter=Q(status="Half Day"),
        ),

        overtime=Sum(
            "overtime_hours"
        ),
    )

    # ========================================================
    # TASKS
    # ========================================================

    task_qs = (
        Task.objects
        .filter(
            staff=staff,
            created_at__date__range=(
                start_date,
                end_date,
            ),
        )
        .select_related(
            "room",
            "room_unit",
        )
        .order_by("-created_at")
    )

    task_stats = task_qs.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="Pending"),
        ),

        in_progress=Count(
            "id",
            filter=Q(status="In Progress"),
        ),

        completed=Count(
            "id",
            filter=Q(status="Completed"),
        ),
    )

    # ========================================================
    # LEAVES
    # ========================================================

    leave_qs = (
        LeaveRequest.objects
        .filter(
            staff=staff,

            # Leave overlaps selected report range
            from_date__lte=end_date,
            to_date__gte=start_date,
        )
        .order_by("-applied_at")
    )

    leave_stats = leave_qs.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="Pending"),
        ),

        approved=Count(
            "id",
            filter=Q(status="Approved"),
        ),

        rejected=Count(
            "id",
            filter=Q(status="Rejected"),
        ),
    )

    # ========================================================
    # PAYROLL
    # ========================================================

    payroll_qs = Payroll.objects.filter(
        staff=staff,
        hotel=hotel,
    )

    payroll_ids = []

    start_month = start_date.replace(day=1)
    end_month = end_date.replace(day=1)

    for payroll in payroll_qs:

        try:

            payroll_date = datetime(
                int(payroll.year),
                int(payroll.month),
                1,
            ).date()

        except (TypeError, ValueError):
            continue

        if start_month <= payroll_date <= end_month:
            payroll_ids.append(payroll.id)

    payroll_qs = payroll_qs.filter(
        id__in=payroll_ids
    )

    payroll_total = (
        payroll_qs.aggregate(
            total=Sum("net_salary")
        )["total"]
        or 0
    )

    # ========================================================
    # ATTENDANCE RECORDS
    # ========================================================

    attendance_records = []

    for item in attendance_qs:

        attendance_records.append(
            {
                "date":
                    item.date.strftime(
                        "%Y-%m-%d"
                    ),

                "check_in":
                    item.check_in.strftime(
                        "%I:%M %p"
                    )
                    if item.check_in
                    else "—",

                "check_out":
                    item.check_out.strftime(
                        "%I:%M %p"
                    )
                    if item.check_out
                    else "—",

                "status":
                    item.status or "—",

                "overtime":
                    float(
                        item.overtime_hours or 0
                    ),
            }
        )

    # ========================================================
    # TASK RECORDS
    # ========================================================

    task_records = []

    for task in task_qs:

        room_number = "—"

        if task.room_unit:
            room_number = (
                task.room_unit.room_number
            )

        task_records.append(
            {
                "id":
                    task.id,

                "title":
                    task.title,

                "room":
                    room_number,

                "status":
                    task.status,

                "created_at":
                    task.created_at.strftime(
                        "%Y-%m-%d"
                    )
                    if task.created_at
                    else "",
            }
        )

    # ========================================================
    # LEAVE RECORDS
    # ========================================================

    leave_records = []

    for leave in leave_qs:

        leave_records.append(
            {
                "id":
                    leave.id,

                "from_date":
                    leave.from_date.strftime(
                        "%Y-%m-%d"
                    ),

                "to_date":
                    leave.to_date.strftime(
                        "%Y-%m-%d"
                    ),

                "reason":
                    leave.reason or "",

                "status":
                    leave.status or "Pending",
            }
        )

    # ========================================================
    # RESPONSE
    # ========================================================

    return JsonResponse(
        {
            "success": True,

            "filters": {
                "start_date":
                    start_date.isoformat(),

                "end_date":
                    end_date.isoformat(),
            },

            "employee": {
                "id":
                    staff.id,

                "name":
                    staff.name,

                "department":
                    (
                        staff.department.name
                        if staff.department
                        else "Housekeeping"
                    ),
            },

            "attendance": {
                "present":
                    attendance_stats["present"]
                    or 0,

                "late":
                    attendance_stats["late"]
                    or 0,

                "absent":
                    attendance_stats["absent"]
                    or 0,

                "half_day":
                    attendance_stats["half_day"]
                    or 0,

                "overtime":
                    float(
                        attendance_stats[
                            "overtime"
                        ]
                        or 0
                    ),
            },

            "tasks": {
                "total":
                    task_stats["total"]
                    or 0,

                "pending":
                    task_stats["pending"]
                    or 0,

                "in_progress":
                    task_stats["in_progress"]
                    or 0,

                "completed":
                    task_stats["completed"]
                    or 0,
            },

            "leaves": {
                "total":
                    leave_stats["total"]
                    or 0,

                "pending":
                    leave_stats["pending"]
                    or 0,

                "approved":
                    leave_stats["approved"]
                    or 0,

                "rejected":
                    leave_stats["rejected"]
                    or 0,
            },

            "payroll": {
                "total":
                    float(payroll_total),

                "records":
                    payroll_qs.count(),
            },

            "attendance_records":
                attendance_records,

            "task_records":
                task_records,

            "leave_records":
                leave_records,
        }
    )


# ============================================================
# EXPORT CSV
# ============================================================

@require_GET
@staff_login_required
def housekeeping_reports_export_csv(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:

        return HttpResponse(
            "Session expired.",
            status=401,
        )

    try:

        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:

        return HttpResponse(
            "Staff not found.",
            status=404,
        )

    start_date, end_date = (
        _housekeeping_report_dates(request)
    )

    # ========================================================
    # DATA
    # ========================================================

    attendance_qs = (
        Attendance.objects
        .filter(
            staff=staff,
            hotel=staff.hotel,
            date__range=(
                start_date,
                end_date,
            ),
        )
        .order_by("date")
    )

    task_qs = (
        Task.objects
        .filter(
            staff=staff,
            created_at__date__range=(
                start_date,
                end_date,
            ),
        )
        .select_related("room_unit")
        .order_by("created_at")
    )

    leave_qs = (
        LeaveRequest.objects
        .filter(
            staff=staff,
            from_date__lte=end_date,
            to_date__gte=start_date,
        )
        .order_by("from_date")
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    filename = (
        f"Housekeeping_Report_"
        f"{start_date}_to_{end_date}.csv"
    )

    response = HttpResponse(
        content_type="text/csv; charset=utf-8"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    # Excel UTF-8 support
    response.write("\ufeff")

    writer = csv.writer(response)

    # ========================================================
    # HEADER
    # ========================================================

    writer.writerow([
        "HOUSEKEEPING STAFF REPORT"
    ])

    writer.writerow([
        "Employee",
        staff.name,
    ])

    writer.writerow([
        "Department",
        (
            staff.department.name
            if staff.department
            else "Housekeeping"
        ),
    ])

    writer.writerow([
        "From",
        start_date.strftime("%d-%m-%Y"),
    ])

    writer.writerow([
        "To",
        end_date.strftime("%d-%m-%Y"),
    ])

    writer.writerow([])

    # ========================================================
    # ATTENDANCE
    # ========================================================

    writer.writerow([
        "ATTENDANCE"
    ])

    writer.writerow([
        "Date",
        "Check In",
        "Check Out",
        "Status",
        "Overtime Hours",
    ])

    for attendance in attendance_qs:

        writer.writerow([
            attendance.date.strftime(
                "%d-%m-%Y"
            ),

            (
                attendance.check_in.strftime(
                    "%I:%M %p"
                )
                if attendance.check_in
                else ""
            ),

            (
                attendance.check_out.strftime(
                    "%I:%M %p"
                )
                if attendance.check_out
                else ""
            ),

            attendance.status,

            attendance.overtime_hours or 0,
        ])

    writer.writerow([])
    writer.writerow([])

    # ========================================================
    # TASKS
    # ========================================================

    writer.writerow([
        "TASKS"
    ])

    writer.writerow([
        "Task",
        "Room",
        "Status",
        "Created",
    ])

    for task in task_qs:

        writer.writerow([
            task.title,

            (
                task.room_unit.room_number
                if task.room_unit
                else ""
            ),

            task.status,

            (
                task.created_at.strftime(
                    "%d-%m-%Y"
                )
                if task.created_at
                else ""
            ),
        ])

    writer.writerow([])
    writer.writerow([])

    # ========================================================
    # LEAVE
    # ========================================================

    writer.writerow([
        "LEAVE"
    ])

    writer.writerow([
        "From",
        "To",
        "Reason",
        "Status",
    ])

    for leave in leave_qs:

        writer.writerow([
            leave.from_date.strftime(
                "%d-%m-%Y"
            ),

            leave.to_date.strftime(
                "%d-%m-%Y"
            ),

            leave.reason or "",

            leave.status,
        ])

    return response



@require_POST
@staff_login_required
def start_cleaning(request):

    # =========================================================
    # STAFF
    # =========================================================

    staff = _get_housekeeping_staff(request)

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Housekeeping access required.",
            },
            status=403,
        )


    try:

        # =====================================================
        # REQUEST DATA
        # =====================================================

        data = json.loads(
            request.body or "{}"
        )

        room_unit_id = data.get(
            "room_unit_id"
        )


        if not room_unit_id:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Room is required.",
                },
                status=400,
            )


        # =====================================================
        # ROOM
        # =====================================================

        try:

            room_unit = (
                RoomUnit.objects
                .select_related("room")
                .get(
                    id=room_unit_id
                )
            )

        except RoomUnit.DoesNotExist:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Room not found.",
                },
                status=404,
            )


        # =====================================================
        # CURRENT STATUS
        # =====================================================

        current_status = (
            room_unit.status or ""
        ).strip().lower()


        # Already cleaning
        if current_status == "cleaning":

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        f"Room {room_unit.room_number} "
                        "is already being cleaned."
                    ),
                },
                status=400,
            )


        # Only dirty rooms can start cleaning
        if current_status != "dirty":

            return JsonResponse(
                {
                    "success": False,
                    "error": (
                        f"Room {room_unit.room_number} "
                        f"is currently {room_unit.status}. "
                        "Only dirty rooms can start cleaning."
                    ),
                },
                status=400,
            )


        # =====================================================
        # CHECK EXISTING ACTIVE CLEANING TASK
        # =====================================================

        existing_task = (
            Task.objects
            .filter(
                room_unit=room_unit,
            )
            .exclude(
                status__iexact="Completed"
            )
            .order_by("-created_at")
            .first()
        )


        if existing_task:

            # If an active task exists, assign/use it
            # instead of creating duplicate cleaning tasks.

            existing_task.staff = staff
            existing_task.status = "In Progress"

            existing_task.save(
                update_fields=[
                    "staff",
                    "status",
                ]
            )

            task = existing_task

        else:

            # =================================================
            # CREATE CLEANING TASK
            # =================================================

            task = Task.objects.create(

                staff=staff,

                room_unit=room_unit,

                room=room_unit.room,

                title=(
                    f"Clean Room "
                    f"{room_unit.room_number}"
                ),

                description=(
                    "Room cleaning in progress"
                ),

                status="In Progress",
            )


        # =====================================================
        # CHANGE ROOM STATUS
        # =====================================================

        room_unit.status = "Cleaning"

        room_unit.save(
            update_fields=["status"]
        )


        # =====================================================
        # RESPONSE
        # =====================================================

        return JsonResponse(
            {
                "success": True,

                "message": (
                    f"Cleaning started for "
                    f"Room {room_unit.room_number}."
                ),

                "new_status": "Cleaning",

                "task_id": task.id,
            }
        )


    except json.JSONDecodeError:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )


    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )


@require_POST
@staff_login_required
def complete_cleaning(request):

    # =========================================================
    # STAFF
    # =========================================================

    staff = _get_housekeeping_staff(request)

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Housekeeping access required.",
            },
            status=403,
        )


    try:

        # =====================================================
        # REQUEST
        # =====================================================

        data = json.loads(
            request.body or "{}"
        )

        room_unit_id = data.get(
            "room_unit_id"
        )

        task_id = data.get(
            "task_id"
        )


        if not room_unit_id:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Room is required.",
                },
                status=400,
            )


        # =====================================================
        # ROOM
        # =====================================================

        try:

            room_unit = (
                RoomUnit.objects
                .select_related("room")
                .get(
                    id=room_unit_id
                )
            )

        except RoomUnit.DoesNotExist:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Room not found.",
                },
                status=404,
            )


        # =====================================================
        # STATUS VALIDATION
        # =====================================================

        current_status = (
            room_unit.status or ""
        ).strip().lower()


        if current_status != "cleaning":

            return JsonResponse(
                {
                    "success": False,

                    "error": (
                        f"Room {room_unit.room_number} "
                        f"is currently {room_unit.status}. "
                        "Only rooms being cleaned can "
                        "be marked ready."
                    ),
                },
                status=400,
            )


        # =====================================================
        # COMPLETE SPECIFIC TASK
        # =====================================================

        if task_id:

            Task.objects.filter(
                id=task_id,
                room_unit=room_unit,
            ).update(
                status="Completed"
            )


        # =====================================================
        # COMPLETE REMAINING ACTIVE CLEANING TASKS
        # =====================================================

        Task.objects.filter(
            room_unit=room_unit,
            status__in=[
                "Pending",
                "In Progress",
            ],
        ).update(
            status="Completed"
        )


        # =====================================================
        # ROOM IS NOW READY
        # =====================================================

        room_unit.status = "Available"

        room_unit.save(
            update_fields=["status"]
        )


        # =====================================================
        # RESPONSE
        # =====================================================

        return JsonResponse(
            {
                "success": True,

                "message": (
                    f"Room {room_unit.room_number} "
                    "is clean and ready."
                ),

                "new_status": "Available",
            }
        )


    except json.JSONDecodeError:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )


    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )

# ============================================================
# HOUSEKEEPING STOCK - CENTRAL INVENTORY
# ============================================================


def _decimal_post_value(request, key, default):
    """
    Safely convert a POST value to Decimal.
    """
    value = request.POST.get(key)

    if value is None or str(value).strip() == "":
        value = default

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Invalid value for {key}.")


def _inventory_status(item):
    """
    Return stock status based on central InventoryItem fields.
    """
    current = item.current_stock or Decimal("0")
    minimum = item.minimum_stock or Decimal("0")

    if current <= 0:
        return "out-of-stock"

    if current <= minimum:
        return "low-stock"

    return "in-stock"


# ============================================================
# STOCK PAGE
# ============================================================

@never_cache
@staff_login_required
def housekeeping_stock_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    # --------------------------------------------------------
    # Inventory
    # --------------------------------------------------------

    inventory_items = (
        HotelInventoryItem.objects
        .select_related(
            "category",
            "department",
            "vendor",
        )
        .all()
        .order_by(
            "category__name",
            "name",
        )
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    total_inventory_items = inventory_items.count()

    total_inventory_quantity = (
        inventory_items.aggregate(
            total=Sum("current_stock")
        )["total"]
        or Decimal("0")
    )

    low_stock_count = (
        inventory_items
        .filter(
            current_stock__gt=0,
            current_stock__lte=F("minimum_stock"),
        )
        .count()
    )

    out_of_stock_count = (
        inventory_items
        .filter(
            current_stock__lte=0
        )
        .count()
    )

    in_stock_count = (
        inventory_items
        .filter(
            current_stock__gt=F("minimum_stock")
        )
        .count()
    )

    # --------------------------------------------------------
    # Modal dropdown data
    # --------------------------------------------------------

    categories = (
        ItemCategory.objects
        .all()
        .order_by("name")
    )

    departments = (
        Department.objects
        .all()
        .order_by("name")
    )

    vendors = (
        Vendor.objects
        .all()
        .order_by("name")
    )

    context.update({

        "inventory_items": inventory_items,

        "categories": categories,
        "departments": departments,
        "vendors": vendors,

        "total_inventory_items":
            total_inventory_items,

        "total_inventory_quantity":
            total_inventory_quantity,

        "low_stock_count":
            low_stock_count,

        "out_of_stock_count":
            out_of_stock_count,

        "in_stock_count":
            in_stock_count,
    })

    return render(
        request,
        "housekeeping/stock.html",
        context,
    )


# ============================================================
# ADD INVENTORY
# ============================================================

@csrf_exempt
@staff_login_required
def add_inventory(request):

    if request.method != "POST":
        return JsonResponse(
            {
                "success": False,
                "error": "Method not allowed.",
            },
            status=405,
        )

    try:

        # ----------------------------------------------------
        # Logged in staff
        # ----------------------------------------------------

        staff_id = request.session.get("staff_id")

        if not staff_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Login required.",
                },
                status=401,
            )

        Staff.objects.get(id=staff_id)

        # ----------------------------------------------------
        # Values
        # ----------------------------------------------------

        name = (
            request.POST.get("name") or ""
        ).strip()

        category_id = (
            request.POST.get("category_id") or ""
        ).strip()

        department_id = (
            request.POST.get("department_id") or ""
        ).strip()

        vendor_id = (
            request.POST.get("vendor_id") or ""
        ).strip()

        unit = (
            request.POST.get("unit") or "piece"
        ).strip()

        if not name:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Item name is required.",
                },
                status=400,
            )

        # ----------------------------------------------------
        # Numbers
        # ----------------------------------------------------

        try:

            current_stock = _decimal_post_value(
                request,
                "current_stock",
                "0",
            )

            minimum_stock = _decimal_post_value(
                request,
                "minimum_stock",
                "10",
            )

            cost_per_unit = _decimal_post_value(
                request,
                "cost_per_unit",
                "0",
            )

        except ValueError as exc:

            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        if current_stock < 0:
            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Current stock cannot be negative.",
                },
                status=400,
            )

        if minimum_stock < 0:
            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Minimum stock cannot be negative.",
                },
                status=400,
            )

        if cost_per_unit < 0:
            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Cost per unit cannot be negative.",
                },
                status=400,
            )

        # ----------------------------------------------------
        # Foreign keys
        # ----------------------------------------------------

        category = None

        if category_id:
            category = ItemCategory.objects.filter(
                id=category_id
            ).first()

            if not category:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Invalid category.",
                    },
                    status=400,
                )

        department = None

        if department_id:
            department = Department.objects.filter(
                id=department_id
            ).first()

            if not department:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Invalid department.",
                    },
                    status=400,
                )

        vendor = None

        if vendor_id:
            vendor = Vendor.objects.filter(
                id=vendor_id
            ).first()

            if not vendor:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Invalid vendor.",
                    },
                    status=400,
                )

        # ----------------------------------------------------
        # Create
        # ----------------------------------------------------

        item = HotelInventoryItem.objects.create(

            name=name,

            category=category,
            department=department,
            vendor=vendor,

            unit=unit,

            current_stock=current_stock,
            minimum_stock=minimum_stock,
            cost_per_unit=cost_per_unit,
        )

        return JsonResponse(
            {
                "success": True,

                "message":
                    f"{item.name} added successfully.",

                "item": {
                    "id": item.id,
                    "name": item.name,

                    "category_id":
                        item.category_id,

                    "category":
                        item.category.name
                        if item.category
                        else "",

                    "department_id":
                        item.department_id,

                    "department":
                        item.department.name
                        if item.department
                        else "",

                    "vendor_id":
                        item.vendor_id,

                    "vendor":
                        str(item.vendor)
                        if item.vendor
                        else "",

                    "unit":
                        item.unit,

                    "current_stock":
                        float(item.current_stock),

                    "minimum_stock":
                        float(item.minimum_stock),

                    "cost_per_unit":
                        float(item.cost_per_unit),

                    "status":
                        _inventory_status(item),
                },
            }
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Staff account not found.",
            },
            status=404,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )


# ============================================================
# GET INVENTORY
# ============================================================

@staff_login_required
def get_inventory(request):

    try:

        staff_id = request.session.get("staff_id")

        if not staff_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Login required.",
                },
                status=401,
            )

        Staff.objects.get(id=staff_id)

        items = (
            HotelInventoryItem.objects
            .select_related(
                "category",
                "department",
                "vendor",
            )
            .all()
            .order_by(
                "category__name",
                "name",
            )
        )

        data = []

        for item in items:

            data.append(
                {
                    "id":
                        item.id,

                    "name":
                        item.name,

                    "category_id":
                        item.category_id,

                    "category":
                        item.category.name
                        if item.category
                        else "",

                    "department_id":
                        item.department_id,

                    "department":
                        item.department.name
                        if item.department
                        else "",

                    "vendor_id":
                        item.vendor_id,

                    "vendor":
                        str(item.vendor)
                        if item.vendor
                        else "",

                    "unit":
                        item.unit,

                    "current_stock":
                        float(
                            item.current_stock or 0
                        ),

                    "minimum_stock":
                        float(
                            item.minimum_stock or 0
                        ),

                    "cost_per_unit":
                        float(
                            item.cost_per_unit or 0
                        ),

                    "status":
                        _inventory_status(item),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "items": data,
            }
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Staff account not found.",
            },
            status=404,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )


# ============================================================
# UPDATE INVENTORY
# ============================================================

@csrf_exempt
@staff_login_required
def update_inventory(request, item_id):

    if request.method != "POST":

        return JsonResponse(
            {
                "success": False,
                "error": "Method not allowed.",
            },
            status=405,
        )

    try:

        staff_id = request.session.get("staff_id")

        if not staff_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Login required.",
                },
                status=401,
            )

        Staff.objects.get(id=staff_id)

        item = get_object_or_404(
            HotelInventoryItem,
            id=item_id,
        )

        # ----------------------------------------------------
        # Form values
        # ----------------------------------------------------

        name = (
            request.POST.get("name") or ""
        ).strip()

        category_id = (
            request.POST.get("category_id") or ""
        ).strip()

        department_id = (
            request.POST.get("department_id") or ""
        ).strip()

        vendor_id = (
            request.POST.get("vendor_id") or ""
        ).strip()

        unit = (
            request.POST.get("unit") or "piece"
        ).strip()

        if not name:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Item name is required.",
                },
                status=400,
            )

        # ----------------------------------------------------
        # Numeric values
        # ----------------------------------------------------

        try:

            current_stock = _decimal_post_value(
                request,
                "current_stock",
                "0",
            )

            minimum_stock = _decimal_post_value(
                request,
                "minimum_stock",
                "10",
            )

            cost_per_unit = _decimal_post_value(
                request,
                "cost_per_unit",
                "0",
            )

        except ValueError as exc:

            return JsonResponse(
                {
                    "success": False,
                    "error": str(exc),
                },
                status=400,
            )

        if current_stock < 0:
            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Current stock cannot be negative.",
                },
                status=400,
            )

        if minimum_stock < 0:
            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Minimum stock cannot be negative.",
                },
                status=400,
            )

        if cost_per_unit < 0:
            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Cost per unit cannot be negative.",
                },
                status=400,
            )

        # ----------------------------------------------------
        # Category
        # ----------------------------------------------------

        category = None

        if category_id:

            category = ItemCategory.objects.filter(
                id=category_id
            ).first()

            if not category:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Invalid category.",
                    },
                    status=400,
                )

        # ----------------------------------------------------
        # Department
        # ----------------------------------------------------

        department = None

        if department_id:

            department = Department.objects.filter(
                id=department_id
            ).first()

            if not department:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Invalid department.",
                    },
                    status=400,
                )

        # ----------------------------------------------------
        # Vendor
        # ----------------------------------------------------

        vendor = None

        if vendor_id:

            vendor = Vendor.objects.filter(
                id=vendor_id
            ).first()

            if not vendor:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Invalid vendor.",
                    },
                    status=400,
                )

        # ----------------------------------------------------
        # Save
        # ----------------------------------------------------

        item.name = name

        item.category = category
        item.department = department
        item.vendor = vendor

        item.unit = unit

        item.current_stock = current_stock
        item.minimum_stock = minimum_stock
        item.cost_per_unit = cost_per_unit

        item.save()

        return JsonResponse(
            {
                "success": True,

                "message":
                    f"{item.name} updated successfully.",

                "item": {
                    "id": item.id,
                    "name": item.name,

                    "category_id":
                        item.category_id,

                    "department_id":
                        item.department_id,

                    "vendor_id":
                        item.vendor_id,

                    "unit":
                        item.unit,

                    "current_stock":
                        float(item.current_stock),

                    "minimum_stock":
                        float(item.minimum_stock),

                    "cost_per_unit":
                        float(item.cost_per_unit),

                    "status":
                        _inventory_status(item),
                },
            }
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Staff account not found.",
            },
            status=404,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )


# ============================================================
# DELETE INVENTORY
# ============================================================

@csrf_exempt
@staff_login_required
def delete_inventory(request, item_id):

    if request.method != "DELETE":

        return JsonResponse(
            {
                "success": False,
                "error": "Method not allowed.",
            },
            status=405,
        )

    try:

        staff_id = request.session.get("staff_id")

        if not staff_id:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Login required.",
                },
                status=401,
            )

        Staff.objects.get(id=staff_id)

        item = get_object_or_404(
            HotelInventoryItem,
            id=item_id,
        )

        item_name = item.name

        item.delete()

        return JsonResponse(
            {
                "success": True,
                "message":
                    f"{item_name} deleted successfully.",
            }
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Staff account not found.",
            },
            status=404,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "success": False,
                "error": str(exc),
            },
            status=500,
        )




import json
from django.shortcuts import render, redirect
from django.utils import timezone

import json
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Prefetch, Count

@staff_login_required
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
    HR_KEYWORDS = ['hr', 'human resource', 'admin', 'manager', 'owner', 'hotel']
    dept_name = (staff.department.name.lower() if staff.department else "")
    role      = (getattr(staff, 'role', '') or '').lower()
    combined  = dept_name + " " + role

    if not any(k in combined for k in HR_KEYWORDS):
        return redirect("staff_login") 

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

    # ── NEW: figure out which modules are enabled for this hotel ──────────
    from accounts.models import HotelModule

    enabled_modules = HotelModule.objects.select_related('module').filter(
        hotel=hotel,
        is_enabled=True
    )

    # Raw lowercase module names, e.g. "billing", "inventory management"
    raw_module_names = [
        m.module.name.lower().strip()
        for m in enabled_modules
    ]

    # Also keep space/underscore variants for exact-match template checks
    active_module_names = set()
    for name in raw_module_names:
        active_module_names.add(name)
        active_module_names.add(name.replace(' ', '_'))
        active_module_names.add(name.replace(' ', ''))
    active_module_names = list(active_module_names)

    # Substring-based flags — robust to naming like "Billing & Invoicing",
    # "Inventory Management", "Laundry Service", "HR Suite", etc.
    def _has_module(keyword):
        return any(keyword in name for name in raw_module_names)

    show_billing   = _has_module('billing') or _has_module('invoice')
    show_inventory = _has_module('inventory')
    show_laundry   = _has_module('laundry')
    show_hr        = _has_module('hr') or _has_module('human resource') or _has_module('payroll')
    # ── END NEW ─────────────────────────────────────────────────────────

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
    today = timezone.now().date()

    monthly_attendance = Attendance.objects.filter(
        staff=staff,
        date__month=today.month,
        date__year=today.year,
    ).order_by("date")

    present_days = monthly_attendance.filter(status="Present").count()
    half_days = monthly_attendance.filter(status="Half Day").count()
    late_days = monthly_attendance.filter(status="Late").count()
    absent_days = monthly_attendance.filter(status="Absent").count()

    overtime_hours = monthly_attendance.aggregate(
        total=Sum("overtime_hours")
    )["total"] or 0

    attendance_records = []

    for att in monthly_attendance:
        working_hours = 0.0

        if att.check_in and att.check_out:
            working_hours = round(
                (att.check_out - att.check_in).total_seconds() / 3600,
                2
            )

        attendance_records.append({
            "date": att.date,
            "check_in": att.check_in.strftime("%H:%M") if att.check_in else "—",
            "check_out": att.check_out.strftime("%H:%M") if att.check_out else "—",
            "status": att.status,
            "working_hours": working_hours,
            "overtime": float(att.overtime_hours or 0),
        })

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

    return render(request,"hr/dashboard.html", {
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
        "present_days": present_days,
        "half_days": half_days,
        "late_days": late_days,
        "absent_days": absent_days,
        "overtime_hours": round(float(overtime_hours), 2),
        "attendance_records": attendance_records,
        "current_month": today.strftime("%B %Y"),
        "housekeeping_staff": housekeeping_staff,
        "hotel_staff": hotel_staff,
        "departments": departments,
        "recent_tasks": recent_tasks,
        "shifts": shifts,
        "total_staff": total_staff,
        "total_departments": total_departments,
        "schema": schema,
        "token": "",
        # ── NEW context for module gating ──
        "active_module_names": active_module_names,
        "show_billing": show_billing,
        "show_inventory": show_inventory,
        "show_laundry": show_laundry,
        "show_hr": show_hr,
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

    action = request.POST.get("action")
    if action not in ("check_in", "check_out"):
        return JsonResponse({"success": False, "message": "Invalid or missing action"}, status=400)

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

    if action == "check_in":
        if attendance.check_in is not None:
            return JsonResponse({"success": False, "message": "Already clocked in today."})

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

    # action == "check_out"
    if attendance.check_in is None:
        return JsonResponse({"success": False, "message": "You have not clocked in yet."})
    if attendance.check_out is not None:
        return JsonResponse({"success": False, "message": "Already clocked out today."})

    attendance.check_out = now

    working_hours = (attendance.check_out - attendance.check_in).total_seconds() / 3600
    overtime = 0

    if shift_start and shift_end:
        shift_start_dt = datetime.combine(today, shift_start)
        shift_end_dt = datetime.combine(today, shift_end)

        # Match awareness of attendance.check_out so the comparison never fails.
        # Depending on USE_TZ / how check_in/check_out were saved, these can be
        # naive or aware — normalize shift_start_dt/shift_end_dt to match.
        if timezone.is_aware(attendance.check_out):
            tz = timezone.get_current_timezone()
            if timezone.is_naive(shift_start_dt):
                shift_start_dt = timezone.make_aware(shift_start_dt, tz)
            if timezone.is_naive(shift_end_dt):
                shift_end_dt = timezone.make_aware(shift_end_dt, tz)
        else:
            if timezone.is_aware(shift_start_dt):
                shift_start_dt = timezone.make_naive(shift_start_dt)
            if timezone.is_aware(shift_end_dt):
                shift_end_dt = timezone.make_naive(shift_end_dt)

        if shift_end < shift_start:
            shift_end_dt += timedelta(days=1)

        if attendance.check_out > shift_end_dt:
            overtime = (attendance.check_out - shift_end_dt).total_seconds() / 3600

        shift_duration = (shift_end_dt - shift_start_dt).total_seconds() / 3600

        if working_hours < (shift_duration / 2):
            attendance.status = "Half Day"
        elif attendance.status != "Late":
            attendance.status = "Present"

    attendance.overtime_hours = round(max(overtime, 0), 2)
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



@require_POST
def hr_mark_employee_attendance(request):

    # =========================================================
    # HOTEL SESSION
    # =========================================================

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Login required."
            },
            status=401
        )


    # =========================================================
    # FORM VALUES
    # =========================================================

    staff_id = request.POST.get("staff_id")
    date_str = request.POST.get("date")
    status = (request.POST.get("status") or "").strip()

    check_in_str = (
        request.POST.get("check_in") or ""
    ).strip()

    check_out_str = (
        request.POST.get("check_out") or ""
    ).strip()


    # =========================================================
    # VALIDATION
    # =========================================================

    if not staff_id:

        return JsonResponse(
            {
                "success": False,
                "error": "Please select an employee."
            },
            status=400
        )


    if not date_str:

        return JsonResponse(
            {
                "success": False,
                "error": "Please select attendance date."
            },
            status=400
        )


    allowed_statuses = [
        "Present",
        "Late",
        "Half Day",
        "Absent",
    ]


    if status not in allowed_statuses:

        return JsonResponse(
            {
                "success": False,
                "error": "Please select a valid attendance status."
            },
            status=400
        )


    # =========================================================
    # DATE
    # =========================================================

    try:

        attendance_date = datetime.strptime(
            date_str,
            "%Y-%m-%d"
        ).date()

    except (ValueError, TypeError):

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid attendance date."
            },
            status=400
        )


    # =========================================================
    # EMPLOYEE
    # =========================================================

    try:

        staff = Staff.objects.get(
            id=staff_id,
            hotel_id=hotel_id
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Employee not found."
            },
            status=404
        )


    # =========================================================
    # TIME PARSER
    # =========================================================

    def parse_attendance_time(value):

        if not value:
            return None

        try:

            parsed_time = datetime.strptime(
                value,
                "%H:%M"
            ).time()

        except ValueError:

            raise ValueError(
                "Invalid time format."
            )


        dt = datetime.combine(
            attendance_date,
            parsed_time
        )


        if timezone.is_naive(dt):

            dt = timezone.make_aware(
                dt,
                timezone.get_current_timezone()
            )


        return dt


    try:

        check_in = parse_attendance_time(
            check_in_str
        )

        check_out = parse_attendance_time(
            check_out_str
        )

    except ValueError as error:

        return JsonResponse(
            {
                "success": False,
                "error": str(error)
            },
            status=400
        )


    # =========================================================
    # STATUS RULES
    # =========================================================

    if status == "Absent":

        check_in = None
        check_out = None


    if (
        check_in and
        check_out and
        check_out < check_in
    ):

        return JsonResponse(
            {
                "success": False,
                "error": "Check-out cannot be before check-in."
            },
            status=400
        )


    # =========================================================
    # OVERTIME
    # =========================================================

    overtime_hours = 0


    if check_in and check_out:

        total_hours = (
            check_out - check_in
        ).total_seconds() / 3600


        overtime_hours = round(
            max(
                total_hours - 8,
                0
            ),
            2
        )


    # =========================================================
    # CREATE / UPDATE
    # =========================================================

    attendance, created = (
        Attendance.objects.update_or_create(

            staff=staff,

            hotel_id=hotel_id,

            date=attendance_date,

            defaults={

                "status":
                    status,

                "check_in":
                    check_in,

                "check_out":
                    check_out,

                "overtime_hours":
                    overtime_hours,
            }
        )
    )


    # =========================================================
    # RESPONSE
    # =========================================================

    return JsonResponse(
        {
            "success": True,

            "created": created,

            "message":
                (
                    "Attendance added successfully."
                    if created
                    else
                    "Attendance updated successfully."
                ),

            "attendance": {

                "id":
                    attendance.id,

                "staff_id":
                    staff.id,

                "name":
                    staff.name,

                "date":
                    str(attendance.date),

                "status":
                    attendance.status,

                "check_in":
                    (
                        attendance.check_in.isoformat()
                        if attendance.check_in
                        else None
                    ),

                "check_out":
                    (
                        attendance.check_out.isoformat()
                        if attendance.check_out
                        else None
                    ),

                "overtime_hours":
                    float(
                        attendance.overtime_hours or 0
                    ),
            }
        }
    )





import math
import json

from datetime import datetime, timedelta, time

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt


SHIFT_TIMINGS = {
    "Morning": (time(9, 0), time(17, 0)),
    "Evening": (time(14, 0), time(22, 0)),
    "Night": (time(22, 0), time(6, 0)),
}


from datetime import datetime, timedelta, time

from django.utils import timezone

from .models import Attendance, Shift, ShiftTemplate


def _do_mark_attendance(staff, action):

    # ============================================================
    # CURRENT LOCAL DATE / TIME
    # ============================================================

    now = timezone.now()

    if timezone.is_aware(now):
        local_now = timezone.localtime(now)
    else:
        local_now = now

    today = local_now.date()


    # ============================================================
    # GET / CREATE TODAY'S ATTENDANCE
    # ============================================================

    attendance, created = Attendance.objects.get_or_create(
        staff=staff,
        hotel=staff.hotel,
        date=today,
    )


    # ============================================================
    # GET TODAY'S SHIFT
    # ============================================================

    shift_obj = (
        Shift.objects
        .filter(
            staff=staff,
            hotel=staff.hotel,
            date=today,
        )
        .first()
    )

    shift_name = None
    shift_start = None
    shift_end = None


    # ============================================================
    # RESOLVE SHIFT TIMES
    # ============================================================

    if shift_obj:

        shift_name = shift_obj.shift

        # --------------------------------------------------------
        # CUSTOM SHIFT
        # --------------------------------------------------------

        if shift_obj.custom_start and shift_obj.custom_end:

            shift_start = shift_obj.custom_start
            shift_end = shift_obj.custom_end

        else:

            # ----------------------------------------------------
            # SHIFT TEMPLATE
            # ----------------------------------------------------

            template = (
                ShiftTemplate.objects
                .filter(
                    hotel=staff.hotel,
                    shift_name=shift_name,
                    is_active=True,
                )
                .first()
            )

            if template:

                shift_start = template.start_time
                shift_end = template.end_time

            else:

                # ------------------------------------------------
                # FALLBACK SHIFT TIMES
                # ------------------------------------------------

                fallback_timings = {
                    "Morning": (
                        time(9, 0),
                        time(17, 0),
                    ),

                    "Evening": (
                        time(14, 0),
                        time(22, 0),
                    ),

                    "Night": (
                        time(22, 0),
                        time(6, 0),
                    ),
                }

                shift_start, shift_end = fallback_timings.get(
                    shift_name,
                    (None, None),
                )


    # ============================================================
    # HELPER: CREATE SHIFT DATETIMES
    # ============================================================

    def get_shift_datetimes():

        if not shift_start or not shift_end:
            return None, None

        start_dt = datetime.combine(
            today,
            shift_start,
        )

        end_dt = datetime.combine(
            today,
            shift_end,
        )

        # --------------------------------------------------------
        # NIGHT SHIFT
        #
        # Example:
        # 22:00 -> 06:00
        # --------------------------------------------------------

        if shift_end <= shift_start:
            end_dt += timedelta(days=1)


        # --------------------------------------------------------
        # MATCH TIMEZONE WITH ATTENDANCE DATETIME
        # --------------------------------------------------------

        if timezone.is_aware(now):

            tz = timezone.get_current_timezone()

            if timezone.is_naive(start_dt):
                start_dt = timezone.make_aware(
                    start_dt,
                    tz,
                )

            if timezone.is_naive(end_dt):
                end_dt = timezone.make_aware(
                    end_dt,
                    tz,
                )

        return start_dt, end_dt


    # ============================================================
    # CHECK IN
    # ============================================================

    if action == "check_in":

        if attendance.check_in is not None:

            return {
                "success": False,
                "message": "You have already checked in today.",
            }


        attendance.check_in = now


        # ========================================================
        # DETERMINE INITIAL STATUS
        # ========================================================

        if shift_start:

            current_time = local_now.time()

            # Remove timezone information from time object
            if current_time.tzinfo is not None:
                current_time = current_time.replace(
                    tzinfo=None
                )

            # ----------------------------------------------------
            # LATE
            # ----------------------------------------------------

            if current_time > shift_start:

                attendance.status = "Late"

            else:

                attendance.status = "Present"

        else:

            # ----------------------------------------------------
            # NO SHIFT ASSIGNED
            #
            # Still allow check-in.
            # ----------------------------------------------------

            attendance.status = "Present"


        attendance.save(
            update_fields=[
                "check_in",
                "status",
            ]
        )


        return {
            "success": True,
            "type": "checkin",
            "message": "Checked in successfully.",
            "shift": shift_name,
            "check_in": attendance.check_in.isoformat(),
            "status": attendance.status,
        }


    # ============================================================
    # CHECK OUT
    # ============================================================

    if action == "check_out":

        # --------------------------------------------------------
        # MUST CHECK IN FIRST
        # --------------------------------------------------------

        if attendance.check_in is None:

            return {
                "success": False,
                "message": "You must check in before checking out.",
            }


        # --------------------------------------------------------
        # PREVENT MULTIPLE CHECKOUTS
        # --------------------------------------------------------

        if attendance.check_out is not None:

            return {
                "success": False,
                "message": "You have already checked out today.",
            }


        attendance.check_out = now


        # ========================================================
        # CALCULATE ACTUAL WORKING HOURS
        # ========================================================

        working_seconds = (
            attendance.check_out
            -
            attendance.check_in
        ).total_seconds()


        working_hours = max(
            working_seconds / 3600,
            0,
        )


        # ========================================================
        # DEFAULT OVERTIME
        # ========================================================

        overtime = 0


        # ========================================================
        # SHIFT-BASED CALCULATIONS
        # ========================================================

        shift_start_dt, shift_end_dt = (
            get_shift_datetimes()
        )


        if shift_start_dt and shift_end_dt:

            # ====================================================
            # SHIFT DURATION
            # ====================================================

            shift_duration_seconds = (
                shift_end_dt
                -
                shift_start_dt
            ).total_seconds()


            shift_duration_hours = (
                shift_duration_seconds / 3600
            )


            # ====================================================
            # OVERTIME
            # ====================================================

            if attendance.check_out > shift_end_dt:

                overtime = (
                    attendance.check_out
                    -
                    shift_end_dt
                ).total_seconds() / 3600


            # ====================================================
            # FINAL ATTENDANCE STATUS
            # ====================================================

            half_day_threshold = (
                shift_duration_hours / 2
            )


            # ----------------------------------------------------
            # LESS THAN HALF SHIFT
            # ----------------------------------------------------

            if working_hours < half_day_threshold:

                attendance.status = "Half Day"


            # ----------------------------------------------------
            # FULL / SUFFICIENT WORKING TIME
            # ----------------------------------------------------

            else:

                # Keep Late if employee was marked Late
                # during check-in.

                if attendance.status != "Late":

                    attendance.status = "Present"


        else:

            # ====================================================
            # NO SHIFT AVAILABLE
            # ====================================================
            #
            # Since there is no scheduled shift duration,
            # use a fallback rule.
            #
            # Less than 4 hours = Half Day
            # 4+ hours = Present
            #
            # You can change 4 hours later if needed.
            # ====================================================

            HALF_DAY_FALLBACK_HOURS = 4.0


            if working_hours < HALF_DAY_FALLBACK_HOURS:

                attendance.status = "Half Day"

            elif attendance.status != "Late":

                attendance.status = "Present"


        # ========================================================
        # SAVE OVERTIME
        # ========================================================

        attendance.overtime_hours = round(
            max(overtime, 0),
            2,
        )


        attendance.save(
            update_fields=[
                "check_out",
                "status",
                "overtime_hours",
            ]
        )


        # ========================================================
        # RETURN RESULT
        # ========================================================

        return {
            "success": True,
            "type": "checkout",

            "message": (
                "Checked out successfully."
            ),

            "shift": shift_name,

            "check_out": (
                attendance.check_out.isoformat()
            ),

            "working_hours": round(
                working_hours,
                2,
            ),

            "overtime": float(
                attendance.overtime_hours or 0
            ),

            "status": attendance.status,
        }


    # ============================================================
    # INVALID ACTION
    # ============================================================

    return {
        "success": False,
        "message": "Invalid attendance action.",
    }





@staff_login_required
@never_cache
@require_POST
def accountant_mark_attendance(request):

    # ============================================================
    # GET CURRENT STAFF
    # ============================================================

    staff = _get_accountant_staff(request)

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "message": "Staff account not found.",
            },
            status=403,
        )


    # ============================================================
    # CHECK ACTIVE STAFF
    # ============================================================

    if not staff.is_active:

        return JsonResponse(
            {
                "success": False,
                "message": "Your staff account is inactive.",
            },
            status=403,
        )


    # ============================================================
    # GET ACTION
    # ============================================================

    action = (
        request.POST
        .get("action", "")
        .strip()
        .lower()
    )


    if action not in (
        "check_in",
        "check_out",
    ):

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid attendance action.",
            },
            status=400,
        )


    # ============================================================
    # FACE VERIFICATION  (ONLY FOR CHECK IN)
    # ============================================================

    if action == "check_in":

        # ---- 1. employee must have a registered face ----------

        stored = normalize_descriptors(
            staff.face_descriptor
        )

        if not stored:

            return JsonResponse(
                {
                    "success": False,
                    "code": "FACE_NOT_REGISTERED",
                    "message": (
                        "Your face has not been registered. "
                        "Please contact HR."
                    ),
                },
                status=403,
            )


        # ---- 2. live face must be sent by the page ------------

        raw_descriptor = request.POST.get(
            "face_descriptor"
        )

        if not raw_descriptor:

            return JsonResponse(
                {
                    "success": False,
                    "code": "FACE_REQUIRED",
                    "message": (
                        "Face verification is required "
                        "before check-in."
                    ),
                },
                status=400,
            )


        # ---- 3. JSON text -> Python list ----------------------

        try:

            live_descriptor = json.loads(
                raw_descriptor
            )

        except (TypeError, ValueError):

            return JsonResponse(
                {
                    "success": False,
                    "code": "INVALID_FACE_DATA",
                    "message": (
                        "Invalid face verification data."
                    ),
                },
                status=400,
            )


        # ---- 4. must be exactly 128 numbers -------------------

        if not validate_face_descriptor(
            live_descriptor
        ):

            return JsonResponse(
                {
                    "success": False,
                    "code": "INVALID_FACE_DATA",
                    "message": "Invalid face descriptor.",
                },
                status=400,
            )


        # ---- 5. compare live face with saved face(s) ----------

        matched, distance = verify_staff_face(
            stored,
            live_descriptor,
        )

        if not matched:

            return JsonResponse(
                {
                    "success": False,
                    "matched": False,      # the page uses this for the "Wrong face" popup
                    "code": "FACE_MISMATCH",
                    "message": (
                        "Face does not match the "
                        "registered employee."
                    ),
                },
                status=403,
            )

        # Face verified. We do NOT save attendance here.
        # We continue to _do_mark_attendance() below.


    # ============================================================
    # SAVE ATTENDANCE (existing code, unchanged)
    # ============================================================

    try:

        result = _do_mark_attendance(
            staff,
            action,
        )

    except Exception as error:

        print(
            "Attendance error:",
            error,
        )

        return JsonResponse(
            {
                "success": False,
                "message": "Unable to mark attendance.",
            },
            status=500,
        )


    # ============================================================
    # RETURN RESULT
    # ============================================================

    status_code = (
        200
        if result.get("success")
        else 400
    )

    return JsonResponse(
        result,
        status=status_code,
    )




@csrf_exempt
@require_POST
def verify_face_and_mark_attendance(request):
    """Clock in/out only if the live face matches THIS logged-in staff's enrolled descriptor."""
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    try:
        staff = Staff.objects.get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    action = data.get("action")
    if action not in ("check_in", "check_out"):
        return JsonResponse({"success": False, "message": "Invalid or missing action"}, status=400)

    live_descriptor = data.get("descriptor")
    if not live_descriptor or len(live_descriptor) != 128:
        return JsonResponse({"error": "No face detected. Please try again."}, status=400)

    if not staff.face_descriptor:
        return JsonResponse(
            {"error": "Your face is not enrolled. Please ask HR/Admin to register your face first."},
            status=400,
        )

    def euclidean(a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

    distance = euclidean(live_descriptor, staff.face_descriptor)
    FACE_MATCH_THRESHOLD = 0.5  # lower = stricter match

    if distance >= FACE_MATCH_THRESHOLD:
        return JsonResponse({
            "success": False,
            "face_matched": False,
            "message": "Face does not match your enrolled profile. Attendance not marked.",
            "confidence": round(max(0, 1 - distance), 3),
        }, status=403)

    result = _do_mark_attendance(staff, action)
    result["face_matched"] = True
    result["confidence"] = round(max(0, 1 - distance), 3)
    return JsonResponse(result, status=200 if result.get("success") else 400)
def today_attendance(request):
    staff_id = request.session.get("staff_id")
    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)

    today = timezone.now().date()

    try:
        att = Attendance.objects.get(staff_id=staff_id, date=today)
    except Attendance.DoesNotExist:
        # No record yet = not clocked in
        return JsonResponse({
            "clocked_in":    False,
            "clocked_out":   False,
            "check_in":      None,
            "check_out":     None,
            "status":        None,
            "working_hours": None
        })

    def fmt(dt):
        if not dt:
            return None
        return dt.strftime("%I:%M %p")  # 09:30 AM

    working_hours = None
    if att.check_in and att.check_out:
        working_hours = round(
            (att.check_out - att.check_in).total_seconds() / 3600, 2
        )

    return JsonResponse({
        "clocked_in":    att.check_in  is not None,
        "clocked_out":   att.check_out is not None,
        "check_in":      fmt(att.check_in),
        "check_out":     fmt(att.check_out),
        "status":        att.status,
        "working_hours": working_hours
    })   
def live_attendance(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    today = timezone.now().date()

    records = Attendance.objects.filter(
        hotel_id=hotel_id,
        date=today
    ).select_related("staff", "staff__department").order_by("-check_in")  # ← add staff__department

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
            "department": r.staff.department.name if r.staff.department else "—",  
            "date": str(r.date),                                                    
            "check_in": r.check_in.isoformat() if r.check_in else None,
            "check_out": r.check_out.isoformat() if r.check_out else None,
            "overtime_hours": float(r.overtime_hours or 0),
            "status": status
        })

    return JsonResponse(data, safe=False)
from django.db import models
def get_attendance(request):
    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse({
            "error": "Login required"
        }, status=401)

    try:
        staff = Staff.objects.select_related("department").get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({
            "error": "Staff not found"
        }, status=404)

    today = timezone.now().date()

    attendance = Attendance.objects.filter(
        staff=staff,
        date=today
    ).first()

    # Scope to the current month, and cover every status bucket
    month_qs = Attendance.objects.filter(
        staff=staff,
        date__year=today.year,
        date__month=today.month,
    )

    total_present   = month_qs.filter(status="Present").count()
    total_late      = month_qs.filter(status="Late").count()
    total_absent    = month_qs.filter(status="Absent").count()
    total_half_day  = month_qs.filter(status="Half Day").count()

    total_overtime = month_qs.aggregate(
        total=models.Sum("overtime_hours")
    )["total"] or 0

    response = {
        "staff": {
            "id": staff.id,
            "name": staff.name,
            "department": staff.department.name if staff.department else "—",
            "designation": getattr(staff, "designation", None),
        },

        "today": {
            "date": str(today),
            "check_in": attendance.check_in.strftime("%I:%M %p") if attendance and attendance.check_in else None,
            "check_out": attendance.check_out.strftime("%I:%M %p") if attendance and attendance.check_out else None,
            "status": attendance.status if attendance else "Absent",
            "overtime_hours": float(attendance.overtime_hours or 0) if attendance else 0,
        },

        "summary": {
            "total_present_days": total_present,
            "total_late_days": total_late,
            "total_absent_days": total_absent,
            "total_half_days": total_half_day,
            "total_overtime_hours": round(float(total_overtime), 2),
        }
    }

    return JsonResponse(response)
from datetime import timedelta
from django.utils import timezone

def get_attendance_history(request):
    staff_id = request.session.get("staff_id")
    
    if not staff_id:
        return JsonResponse({"error": "Login required"}, status=401)
    
    try:
        staff = Staff.objects.get(id=staff_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)
    
    # Get filter parameters
    months = request.GET.get('months', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    
    today = timezone.now().date()
    
   
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    elif months:
        
        months_offset = int(months) if months else 0
        start_date = today.replace(day=1) - timedelta(days=30 * abs(months_offset))
    else:
        start_date = today - timedelta(days=30)
    
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = today
    
    attendance_records = Attendance.objects.filter(
        staff=staff,
        date__range=[start_date, end_date]
    ).order_by('-date')
    
    records_data = []
    for record in attendance_records:
        working_hours = None
        if record.check_in and record.check_out:
            delta = record.check_out - record.check_in
            working_hours = round(delta.total_seconds() / 3600, 2)
        
        records_data.append({
            "date": record.date,
            "check_in": record.check_in.strftime("%I:%M %p") if record.check_in else None,
            "check_out": record.check_out.strftime("%I:%M %p") if record.check_out else None,
            "status": record.status,
            "working_hours": working_hours,
            "overtime_hours": float(record.overtime_hours or 0)
        })
    
    return JsonResponse({"attendance": records_data})    
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
            # If attendance row exists but status is blank, treat as Absent
            "status": (a.status or "Absent") if a else "Absent",
            "overtime": float(a.overtime_hours or 0) if a else 0.0
        })

    return JsonResponse(data, safe=False)


def monthly_report(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    month_str = request.GET.get("month")
    if month_str:
        try:
            parsed = datetime.strptime(month_str, "%Y-%m")
            month, year = parsed.month, parsed.year
        except ValueError:
            return JsonResponse({"error": "Invalid month format. Use YYYY-MM"}, status=400)
    else:
        now = timezone.now()
        month, year = now.month, now.year

    from calendar import monthrange
    from collections import defaultdict

    first_day = date(year, month, 1)
    last_day  = date(year, month, monthrange(year, month)[1])

    # ✅ ALL staff in hotel, not just scheduled ones
    all_staff = Staff.objects.filter(hotel_id=hotel_id).order_by("name")

    # All attendance rows for this month
    att_rows = Attendance.objects.filter(
        hotel_id=hotel_id,
        date__month=month,
        date__year=year
    )
    att_map = defaultdict(list)
    for a in att_rows:
        att_map[a.staff_id].append(a)

    # Scheduled dates per staff
    shift_days = Shift.objects.filter(
        hotel_id=hotel_id,
        date__range=(first_day, last_day)
    ).values("staff_id", "date").distinct()

    scheduled_days_map = defaultdict(set)
    for row in shift_days:
        scheduled_days_map[row["staff_id"]].add(row["date"])

    data = []
    for s in all_staff:
        records         = att_map[s.id]
        scheduled_dates = scheduled_days_map[s.id]   
        scheduled       = len(scheduled_dates)

       
        scheduled_records = [a for a in records if a.date in scheduled_dates]

        present  = sum(1 for a in scheduled_records if a.status in ("Present", "Late", "Half Day"))
        late     = sum(1 for a in scheduled_records if a.status == "Late")
        half_day = sum(1 for a in scheduled_records if a.status == "Half Day")

        attended_dates = {a.date for a in scheduled_records if a.check_in}
        absent = max(scheduled - len(attended_dates), 0)

       
        extra_day_records = [a for a in records if a.date not in scheduled_dates and a.check_in]
        extra_days = len(extra_day_records)

        overtime = round(sum(float(a.overtime_hours or 0) for a in scheduled_records), 2)

        data.append({
            "name":       s.name,
            "scheduled":  scheduled,     
            "present":    present,
            "absent":     absent,
            "late":       late,
            "half_day":   half_day,
            "extra_days": extra_days,
            "overtime":   overtime
        })

    return JsonResponse(data, safe=False)



# ============================================================
# APPLY LEAVE
# HR can apply leave for an employee
# ============================================================

from datetime import datetime
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache


@require_POST
@staff_login_required
def apply_leave(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Session expired.",
            },
            status=401,
        )

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "error": "Staff not found.",
            },
            status=404,
        )

    # =====================================================
    # FORM DATA
    # =====================================================

    from_date = (
        request.POST.get("from_date")
        or ""
    ).strip()

    to_date = (
        request.POST.get("to_date")
        or ""
    ).strip()

    leave_type = (
        request.POST.get("leave_type")
        or ""
    ).strip()

    reason = (
        request.POST.get("reason")
        or ""
    ).strip()

    # =====================================================
    # VALIDATION
    # =====================================================

    if not from_date or not to_date:
        return JsonResponse(
            {
                "success": False,
                "error":
                    "From Date and To Date are required.",
            },
            status=400,
        )

    if not reason:
        return JsonResponse(
            {
                "success": False,
                "error": "Reason is required.",
            },
            status=400,
        )

    try:
        from_date_obj = datetime.strptime(
            from_date,
            "%Y-%m-%d",
        ).date()

        to_date_obj = datetime.strptime(
            to_date,
            "%Y-%m-%d",
        ).date()

    except ValueError:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid date.",
            },
            status=400,
        )

    if to_date_obj < from_date_obj:
        return JsonResponse(
            {
                "success": False,
                "error":
                    "To Date cannot be before From Date.",
            },
            status=400,
        )

    # =====================================================
    # CREATE LEAVE
    # IMPORTANT: tenant must be saved
    # =====================================================

    leave = LeaveRequest.objects.create(

        tenant=request.tenant,

        staff=staff,

        from_date=from_date_obj,

        to_date=to_date_obj,

        reason=reason,
        status="Pending",
    )

    return JsonResponse(
        {
            "success": True,

            "message":
                "Leave request submitted successfully.",

            "leave_id":
                leave.id,
        }
    )



@require_GET
@staff_login_required
def leave_requests(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Session expired.",
            },
            status=401,
        )

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "error": "Staff not found.",
            },
            status=404,
        )

    # =====================================================
    # FILTERS
    # =====================================================

    month = (
        request.GET.get("month")
        or ""
    ).strip()

    year = (
        request.GET.get("year")
        or ""
    ).strip()

    # =====================================================
    # ONLY CURRENT STAFF LEAVES
    # =====================================================

    leaves = (
        LeaveRequest.objects
        .filter(
            tenant=request.tenant,
            staff=staff,
        )
        .select_related(
            "staff",
            "staff__department",
        )
        .order_by(
            "-applied_at",
            "-id",
        )
    )

    # =====================================================
    # OPTIONAL MONTH
    # =====================================================

    if month:
        try:
            leaves = leaves.filter(
                from_date__month=int(month)
            )
        except (ValueError, TypeError):
            pass

    # =====================================================
    # OPTIONAL YEAR
    # =====================================================

    if year:
        try:
            leaves = leaves.filter(
                from_date__year=int(year)
            )
        except (ValueError, TypeError):
            pass

    # =====================================================
    # RESPONSE
    # =====================================================

    data = []

    for leave in leaves:

        data.append(
            {
                "id":
                    leave.id,

                "staff":
                    leave.staff.name
                    if leave.staff
                    else "Deleted Staff",

                "staff_id":
                    leave.staff_id,

                "from_date":
                    leave.from_date.strftime(
                        "%Y-%m-%d"
                    )
                    if leave.from_date
                    else "",

                "to_date":
                    leave.to_date.strftime(
                        "%Y-%m-%d"
                    )
                    if leave.to_date
                    else "",

                "reason":
                    leave.reason or "",

                "leave_type":
                    getattr(
                        leave,
                        "leave_type",
                        ""
                    )
                    or "",

                "applied_at":
                    leave.applied_at.strftime(
                        "%Y-%m-%d"
                    )
                    if leave.applied_at
                    else "",

                "status":
                    leave.status or "Pending",

                "is_admin_view":
                    False,
            }
        )

    return JsonResponse(
        data,
        safe=False,
    )



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


# ============================================================
# HR - APPROVE / REJECT LEAVE
# ============================================================

@require_POST
def admin_leave_update(request, leave_id):
    try:
        hotel_id = request.session.get("hotel_id")
        staff_id = request.session.get("staff_id")

        if not hotel_id:
            return JsonResponse({
                "success": False,
                "error": "Hotel session not found"
            }, status=400)

        action = request.POST.get(
            "action",
            ""
        ).lower().strip()

        if action not in [
            "approve",
            "reject"
        ]:
            return JsonResponse({
                "success": False,
                "error": "Invalid action"
            }, status=400)

        # ----------------------------------------------------
        # GET LEAVE
        # ----------------------------------------------------

        try:
            leave = (
                LeaveRequest.objects
                .select_related(
                    "staff",
                    "staff__department"
                )
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

        # ----------------------------------------------------
        # ALREADY PROCESSED
        # ----------------------------------------------------

        if leave.status != "Pending":
            return JsonResponse({
                "success": False,
                "error": f"Leave already {leave.status}"
            }, status=400)

        # ----------------------------------------------------
        # UPDATE STATUS
        # ----------------------------------------------------

        if action == "approve":
            leave.status = "Approved"
        else:
            leave.status = "Rejected"

        # ----------------------------------------------------
        # RECORD HR USER
        # ----------------------------------------------------

        if staff_id:

            try:
                action_staff = Staff.objects.get(
                    id=staff_id,
                    hotel_id=hotel_id
                )

                leave.action_by = action_staff

            except Staff.DoesNotExist:
                pass

        leave.action_at = timezone.now()

        leave.save()

        # ----------------------------------------------------
        # RESPONSE
        # ----------------------------------------------------

        return JsonResponse({
            "success": True,
            "id": leave.id,
            "status": leave.status,

            "staff": (
                leave.staff.name
                if leave.staff
                else ""
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
import csv
from decimal import Decimal
from io import BytesIO
from datetime import date, datetime, timedelta

from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count, Q


def _sf(v):
    try:
        return float(v) if v not in (None, '', 'None') else 0.0
    except (TypeError, ValueError):
        return 0.0


def _dec(v):
    try:
        return Decimal(str(v)) if v not in (None, '', 'None') else Decimal("0")
    except Exception:
        return Decimal("0")


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


def _approved_leave_days(staff, month, year):
    from hotel.models import LeaveRequest

    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])

    total = 0
    qs = LeaveRequest.objects.filter(
        staff=staff, status="Approved",
        from_date__lte=last, to_date__gte=first,
    )
    for leave in qs:
        start = max(leave.from_date, first)
        end = min(leave.to_date, last)
        total += (end - start).days + 1
    return total


def _calculate_payroll(staff, month, year):
    from hotel.models import Attendance, LeaveRequest

    attendances = Attendance.objects.filter(staff=staff, date__month=month, date__year=year)

    absent_days    = attendances.filter(status="Absent").count()
    half_days      = attendances.filter(status="Half Day").count()
    present_days   = attendances.filter(status__in=["Present", "Late"]).count()
    late_days      = attendances.filter(status="Late").count()
    overtime_hours = max(sum(_sf(a.overtime_hours) for a in attendances), 0)

    # ← FIX: count actual approved leave DAYS in this month, not leave REQUESTS
    approved_leaves = _approved_leave_days(staff, month, year)

    total_days   = _total_days_in_month(month, year)
    eligible     = _eligible_days(staff, month, year)
    is_pro_rated = eligible < total_days

    basic_salary = Decimal(str(_sf(staff.salary)))

    pro_rated_basic = (basic_salary / Decimal(str(total_days))) * Decimal(str(eligible)) if is_pro_rated else basic_salary
    per_day         = basic_salary / Decimal(str(total_days)) if total_days else Decimal("0")
    per_hour        = per_day / Decimal("8")

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


def _build_auto_line_items(payroll, calc):
    from hotel.models import PayrollLineItem
    items = []

    items.append(PayrollLineItem(
        payroll=payroll, line_type="earning", source="basic",
        label="Basic Salary", amount=payroll.basic_salary, is_auto=True, order=1
    ))
    if payroll.overtime_amount > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="earning", source="overtime",
            label=f"Overtime ({calc['overtime_hours']} hrs)",
            amount=payroll.overtime_amount, is_auto=True, order=2
        ))
    if payroll.bonus > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="earning", source="bonus",
            label="Bonus", amount=payroll.bonus, is_auto=True, order=3
        ))
    if payroll.incentive > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="earning", source="incentive",
            label="Incentive", amount=payroll.incentive, is_auto=True, order=4
        ))
    if payroll.deductions > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="deduction", source="leave",
            label=f"Leave/Absent ({calc['absent_days']} absent + {calc['approved_leaves']} leave, {calc['half_days']} half days)",
            amount=payroll.deductions, is_auto=True, order=1
        ))
    if payroll.pf_amount > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="deduction", source="pf",
            label="PF (Employee)", amount=payroll.pf_amount, is_auto=True, order=2
        ))
    if payroll.esi_amount > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="deduction", source="esi",
            label="ESI (Employee)", amount=payroll.esi_amount, is_auto=True, order=3
        ))
    if payroll.loan_deduction > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="deduction", source="loan",
            label="Loan Deduction", amount=payroll.loan_deduction, is_auto=True, order=4
        ))
    if payroll.tax_deduction > 0:
        items.append(PayrollLineItem(
            payroll=payroll, line_type="deduction", source="tax",
            label="Tax/TDS", amount=payroll.tax_deduction, is_auto=True, order=5
        ))
    for e in (payroll.custom_earnings or []):
        if _sf(e.get("amount")) > 0:
            items.append(PayrollLineItem(
                payroll=payroll, line_type="earning", source="custom",
                label=e.get("label", "Custom Earning"),
                amount=Decimal(str(_sf(e.get("amount")))), is_auto=False, order=10
            ))
    for d in (payroll.custom_deductions or []):
        if _sf(d.get("amount")) > 0:
            items.append(PayrollLineItem(
                payroll=payroll, line_type="deduction", source="custom",
                label=d.get("label", "Custom Deduction"),
                amount=Decimal(str(_sf(d.get("amount")))), is_auto=False, order=10
            ))
    return items


def _sync_line_items(payroll, calc):
    from hotel.models import PayrollLineItem
    PayrollLineItem.objects.filter(payroll=payroll, is_auto=True).delete()
    PayrollLineItem.objects.bulk_create(_build_auto_line_items(payroll, calc))


def _recalculate_net(payroll):
    from hotel.models import PayrollLineItem
    earnings   = PayrollLineItem.objects.filter(payroll=payroll, line_type="earning").aggregate(t=Sum("amount"))["t"] or Decimal("0")
    deductions = PayrollLineItem.objects.filter(payroll=payroll, line_type="deduction").aggregate(t=Sum("amount"))["t"] or Decimal("0")
    net = max(earnings - deductions, Decimal("0"))
    payroll.net_salary = net
    payroll.save(update_fields=["net_salary"])
    return {"gross": float(earnings), "total_deductions": float(deductions), "net_salary": float(net)}


def _line_item_dict(item):
    return {
        "id":        item.id,
        "line_type": item.line_type,
        "source":    item.source,
        "label":     item.label,
        "amount":    float(item.amount),
        "pct":       float(item.pct) if item.pct else None,
        "pct_base":  item.pct_base,
        "is_auto":   item.is_auto,
        "note":      item.note,
        "order":     item.order,
    }


def _ensure_payroll_records(hotel_id, month, year):

    from hotel.models import Payroll
    from accounts.models import Staff

    staffs = (
        Staff.objects
        .filter(hotel_id=hotel_id)
        .select_related(
            "department",
            "user"
        )
    )

    results = []

    for staff in staffs:

        calc = _calculate_payroll(
            staff,
            month,
            year
        )

        base_deduct = (
            calc["absent_deduction"]
            +
            calc["half_day_deduction"]
        )

        calculated_net = max(
            calc["pro_rated_basic"]
            +
            calc["overtime_amount"]
            -
            base_deduct,
            Decimal("0")
        )

        payroll, created = (
            Payroll.objects.get_or_create(

                staff=staff,
                hotel_id=hotel_id,
                month=month,
                year=year,

                defaults={

                    "basic_salary":
                        max(
                            calc["pro_rated_basic"],
                            Decimal("0")
                        ),

                    "overtime_amount":
                        calc["overtime_amount"],

                    "deductions":
                        base_deduct,

                    "net_salary":
                        calculated_net,

                    "paid_status":
                        "Unpaid",

                    "bonus":
                        Decimal("0"),

                    "incentive":
                        Decimal("0"),

                    "pf_amount":
                        Decimal("0"),

                    "esi_amount":
                        Decimal("0"),

                    "loan_deduction":
                        Decimal("0"),

                    "tax_deduction":
                        Decimal("0"),

                    "custom_earnings":
                        [],

                    "custom_deductions":
                        [],
                }
            )
        )

        # ----------------------------------------------------
        # NEW PAYROLL
        # ----------------------------------------------------

        if created:

            _sync_line_items(
                payroll,
                calc
            )

            _recalculate_net(
                payroll
            )

        # ----------------------------------------------------
        # EXISTING UNPAID PAYROLL
        #
        # Refresh attendance-controlled fields.
        # Manual bonus/incentive/PF/etc are preserved.
        # ----------------------------------------------------

        elif payroll.paid_status != "Paid":

            payroll.basic_salary = max(
                calc["pro_rated_basic"],
                Decimal("0")
            )

            payroll.overtime_amount = (
                calc["overtime_amount"]
            )

            payroll.deductions = (
                base_deduct
            )

            payroll.save(
                update_fields=[
                    "basic_salary",
                    "overtime_amount",
                    "deductions",
                ]
            )

            _sync_line_items(
                payroll,
                calc
            )

            _recalculate_net(
                payroll
            )

        # ----------------------------------------------------
        # PAID PAYROLL
        #
        # NEVER recalculate historical paid payroll.
        # ----------------------------------------------------

        results.append(
            (
                payroll,
                created
            )
        )

    return results



# ============================================================
# PAYROLL MANAGEMENT PAGE
# ============================================================

from django.shortcuts import render
from django.utils import timezone


# ============================================================
# PAYROLL MANAGEMENT PAGE
# ============================================================

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from hotel.models import Staff, Payroll


@staff_login_required
@login_required
def payroll_management(request):
    """
    Accountant Payroll Management page.

    Handles:
    - Logged-in accountant/staff
    - Current hotel
    - Month/year filtering
    - Employee search
    - Paid/unpaid filtering
    - Payroll summary cards
    - Employee list for Generate Payroll modal
    """

    # ============================================================
    # GET LOGGED-IN STAFF
    # ============================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
                "user",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return redirect("staff_login")


    # ============================================================
    # HOTEL
    # ============================================================

    hotel = staff.hotel

    if not hotel:
        return redirect("staff_login")

    # Keep hotel_id available for payroll API endpoints
    request.session["hotel_id"] = hotel.id


    # ============================================================
    # CURRENT DATE
    # ============================================================

    # Using timezone.now().date() instead of timezone.localdate()
    # because your project contains legacy naive datetime values.

    now = timezone.now()
    today = now.date()


    # ============================================================
    # GET FILTER VALUES
    # ============================================================

    selected_month = request.GET.get(
        "month",
        today.month,
    )

    selected_year = request.GET.get(
        "year",
        today.year,
    )

    search = (
        request.GET.get("q")
        or request.GET.get("search")
        or ""
    ).strip()

    status_filter = (
        request.GET.get("status")
        or ""
    ).strip().lower()


    # ============================================================
    # VALIDATE MONTH
    # ============================================================

    try:
        selected_month = int(selected_month)

    except (TypeError, ValueError):
        selected_month = today.month


    if selected_month < 1 or selected_month > 12:
        selected_month = today.month


    # ============================================================
    # VALIDATE YEAR
    # ============================================================

    try:
        selected_year = int(selected_year)

    except (TypeError, ValueError):
        selected_year = today.year


    # ============================================================
    # PAYROLL QUERY
    # IMPORTANT:
    # Restrict payroll to CURRENT HOTEL.
    # ============================================================

    payrolls = (
        Payroll.objects
        .select_related(
            "staff",
            "staff__department",
            "staff__user",
        )
        .filter(
            staff__hotel=hotel,
            month=selected_month,
            year=selected_year,
        )
        .order_by(
            "staff__name"
        )
    )


    # ============================================================
    # SEARCH
    # ============================================================

    if search:

        payrolls = payrolls.filter(

            Q(
                staff__name__icontains=search
            )

            |

            Q(
                staff__employee_id__icontains=search
            )

            |

            Q(
                staff__user__email__icontains=search
            )

        )


    # ============================================================
    # STATUS FILTER
    #
    # IMPORTANT:
    # This version assumes your Payroll.paid_status is Boolean:
    #
    # True  = Paid
    # False = Unpaid
    #
    # This matches the payroll filtering code you shared.
    # ============================================================

    if status_filter == "paid":

        payrolls = payrolls.filter(
            paid_status=True
        )

    elif status_filter in [
        "pending",
        "unpaid",
    ]:

        payrolls = payrolls.filter(
            paid_status=False
        )


    # ============================================================
    # TOTAL PAYROLL
    # ============================================================

    total_payroll = (
        payrolls.aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )


    # ============================================================
    # PAID PAYROLL
    # ============================================================

    paid_payroll = (
        payrolls
        .filter(
            paid_status=True
        )
        .aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )


    # ============================================================
    # PENDING PAYROLL
    # ============================================================

    pending_payroll = (
        payrolls
        .filter(
            paid_status=False
        )
        .aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )


    # ============================================================
    # COUNTS
    # ============================================================

    paid_count = (
        payrolls
        .filter(
            paid_status=True
        )
        .count()
    )

    pending_count = (
        payrolls
        .filter(
            paid_status=False
        )
        .count()
    )

    total_count = payrolls.count()


    # ============================================================
    # EMPLOYEES FOR GENERATE PAYROLL MODAL
    #
    # THIS FIXES YOUR EMPTY EMPLOYEE DROPDOWN
    # ============================================================

    staff_list = (
        Staff.objects
        .filter(
            hotel=hotel
        )
        .select_related(
            "department",
            "user",
        )
        .order_by(
            "name"
        )
    )


    # ============================================================
    # YEAR DROPDOWN
    # ============================================================

    years = list(
        range(
            today.year - 5,
            today.year + 2,
        )
    )


    # ============================================================
    # MONTH DROPDOWN
    # ============================================================

    months = [

        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),

        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),

    ]


    # ============================================================
    # CONTEXT
    # ============================================================

    context = {

        # --------------------------------------------------------
        # Logged-in staff / hotel
        # --------------------------------------------------------

        "staff":
            staff,

        "hotel":
            hotel,


        # --------------------------------------------------------
        # Payroll
        # --------------------------------------------------------

        "payrolls":
            payrolls,


        # --------------------------------------------------------
        # Generate Payroll modal employees
        # --------------------------------------------------------

        "staff_list":
            staff_list,


        # --------------------------------------------------------
        # Selected filters
        # --------------------------------------------------------

        "selected_month":
            selected_month,

        "selected_year":
            selected_year,

        "current_month":
            today.month,

        "current_year":
            today.year,

        "search":
            search,

        "status":
            status_filter,


        # --------------------------------------------------------
        # Financial summary
        # --------------------------------------------------------

        "total_payroll":
            total_payroll,

        "paid_payroll":
            paid_payroll,

        "pending_payroll":
            pending_payroll,


        # --------------------------------------------------------
        # Counts
        # --------------------------------------------------------

        "paid_count":
            paid_count,

        "pending_count":
            pending_count,

        "total_count":
            total_count,


        # --------------------------------------------------------
        # Dropdown data
        # --------------------------------------------------------

        "years":
            years,

        "months":
            months,

        "today":
            today,
    }


    # ============================================================
    # RENDER
    # ============================================================

    return render(
        request,
        "accountant/payroll.html",
        context,
    )



@csrf_exempt
@require_POST
def generate_payroll(request):

    hotel_id = request.session.get(
        "hotel_id"
    )

    if not hotel_id:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required"
            },
            status=401
        )

    try:

        data = json.loads(
            request.body or "{}"
        )

        month = int(
            data.get("month")
        )

        year = int(
            data.get("year")
        )

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError
    ):

        return JsonResponse(
            {
                "success": False,
                "error":
                    "Valid month and year are required."
            },
            status=400
        )

    if month < 1 or month > 12:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid month."
            },
            status=400
        )

    if year < 2000 or year > 2200:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid year."
            },
            status=400
        )

    results = _ensure_payroll_records(
        hotel_id,
        month,
        year
    )

    created_count = sum(
        1
        for payroll, created in results
        if created
    )

    existing_count = (
        len(results)
        -
        created_count
    )

    return JsonResponse(
        {
            "success": True,

            "message":
                f"Payroll prepared for "
                f"{len(results)} employees.",

            "created":
                created_count,

            "existing":
                existing_count,

            "month":
                month,

            "year":
                year,

            "total":
                len(results),
        }
    )



@require_GET
def payroll_dashboard(request):

    hotel_id = request.session.get(
        "hotel_id"
    )

    if not hotel_id:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required"
            },
            status=401
        )

    try:

        month = int(
            request.GET.get(
                "month",
                timezone.now().month
            )
        )

        year = int(
            request.GET.get(
                "year",
                timezone.now().year
            )
        )

    except (TypeError, ValueError):

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid month or year."
            },
            status=400
        )

    if month < 1 or month > 12:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid month."
            },
            status=400
        )

    # Make sure payroll exists and unpaid payroll
    # reflects current attendance.
    _ensure_payroll_records(
        hotel_id,
        month,
        year
    )

    from hotel.models import Payroll
    from accounts.models import Staff

    staffs = (
        Staff.objects
        .filter(
            hotel_id=hotel_id
        )
        .select_related(
            "department",
            "user"
        )
        .order_by("name")
    )

    payrolls = (
        Payroll.objects
        .filter(
            hotel_id=hotel_id,
            month=month,
            year=year
        )
        .select_related(
            "staff",
            "staff__department",
            "staff__user",
            "paid_by"
        )
        .prefetch_related(
            "line_items"
        )
    )

    payroll_map = {
        payroll.staff_id: payroll
        for payroll in payrolls
    }

    employees = []

    total_gross = Decimal("0")
    total_deductions = Decimal("0")
    total_net = Decimal("0")

    paid_count = 0
    unpaid_count = 0

    for staff in staffs:

        payroll = payroll_map.get(
            staff.id
        )

        if not payroll:
            continue

        calc = _calculate_payroll(
            staff,
            month,
            year
        )

        earnings_items = []
        deduction_items = []

        employee_gross = Decimal("0")
        employee_deductions = Decimal("0")

        for item in payroll.line_items.all():

            item_data = _line_item_dict(
                item
            )

            if item.line_type == "earning":

                earnings_items.append(
                    item_data
                )

                employee_gross += (
                    item.amount
                )

            else:

                deduction_items.append(
                    item_data
                )

                employee_deductions += (
                    item.amount
                )

        total_gross += employee_gross
        total_deductions += employee_deductions
        total_net += payroll.net_salary

        if payroll.paid_status == "Paid":
            paid_count += 1
        else:
            unpaid_count += 1

        employees.append(
            {
                "id":
                    payroll.id,

                "staff_id":
                    staff.id,

                "staff":
                    staff.name,

                "employee_id":
                    getattr(
                        staff,
                        "employee_id",
                        f"EMP{staff.id:03d}"
                    ),

                "department":
                    (
                        staff.department.name
                        if staff.department
                        else "—"
                    ),

                "email":
                    (
                        staff.user.email
                        if staff.user
                        else ""
                    ),

                "month":
                    month,

                "year":
                    year,

                "month_label":
                    MONTH_NAMES[month],

                # Salary
                "original_basic":
                    _sf(staff.salary),

                "basic_salary":
                    float(
                        payroll.basic_salary
                    ),

                "gross_salary":
                    float(
                        employee_gross
                    ),

                "total_deductions":
                    float(
                        employee_deductions
                    ),

                "net_salary":
                    float(
                        payroll.net_salary
                    ),

                # Attendance
                "present_days":
                    calc["present_days"],

                "absent_days":
                    calc["absent_days"],

                "half_days":
                    calc["half_days"],

                "late_days":
                    calc["late_days"],

                "approved_leaves":
                    calc["approved_leaves"],

                "overtime_hours":
                    calc["overtime_hours"],

                "eligible_days":
                    calc["eligible_days"],

                "total_days":
                    calc["total_days"],

                "is_pro_rated":
                    calc["is_pro_rated"],

                # Earnings
                "overtime_amount":
                    float(
                        payroll.overtime_amount
                    ),

                "bonus":
                    float(
                        payroll.bonus
                    ),

                "incentive":
                    float(
                        payroll.incentive
                    ),

                # Deductions
                "leave_deduction":
                    float(
                        payroll.deductions
                    ),

                "pf_amount":
                    float(
                        payroll.pf_amount
                    ),

                "esi_amount":
                    float(
                        payroll.esi_amount
                    ),

                "loan_deduction":
                    float(
                        payroll.loan_deduction
                    ),

                "tax_deduction":
                    float(
                        payroll.tax_deduction
                    ),

                # Line items
                "earnings_items":
                    earnings_items,

                "deductions_items":
                    deduction_items,

                # Status
                "paid_status":
                    payroll.paid_status,

                "paid_at":
                    (
                        payroll.paid_at.strftime(
                            "%d %b %Y, %I:%M %p"
                        )
                        if payroll.paid_at
                        else None
                    ),

                "paid_by":
                    (
                        payroll.paid_by.name
                        if payroll.paid_by
                        else "—"
                    ),

                "notes":
                    payroll.notes or "",
            }
        )

    return JsonResponse(
        {
            "success": True,

            "month":
                month,

            "year":
                year,

            "month_label":
                MONTH_NAMES[month],

            "summary": {
                "employees":
                    len(employees),

                "paid":
                    paid_count,

                "unpaid":
                    unpaid_count,

                "total_gross":
                    float(total_gross),

                "total_deductions":
                    float(total_deductions),

                "total_net":
                    float(total_net),
            },

            "employees":
                employees,
        }
    )



def payroll_detail(request, payroll_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll

    try:
        p = Payroll.objects.select_related(
            "staff__user", "staff__department", "paid_by"
        ).prefetch_related("line_items").get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll not found"}, status=404)

    calc = _calculate_payroll(p.staff, p.month, p.year)

    earnings_items   = [_line_item_dict(i) for i in p.line_items.filter(line_type="earning").order_by("order", "id")]
    deductions_items = [_line_item_dict(i) for i in p.line_items.filter(line_type="deduction").order_by("order", "id")]

    total_earnings   = sum(i["amount"] for i in earnings_items)
    total_deductions = sum(i["amount"] for i in deductions_items)

    return JsonResponse({
        "success":            True,
        "id":                 p.id,
        "staff":              p.staff.name,
        "staff_id":           p.staff.id,
        "employee_id":        getattr(p.staff, "employee_id", f"EMP{p.staff.id:03d}"),
        "department":         p.staff.department.name if p.staff.department else "—",
        "email":              p.staff.user.email if p.staff.user else "",
        "month":              p.month,
        "year":               p.year,
        "month_label":        MONTH_NAMES[p.month],
        "original_basic":     _sf(p.staff.salary),
        "basic_salary":       float(p.basic_salary),
        "is_pro_rated":       calc["is_pro_rated"],
        "eligible_days":      calc["eligible_days"],
        "total_days":         calc["total_days"],
        "per_day_rate":       float(calc["per_day_rate"]),
        "per_hour_rate":      float(calc["per_hour_rate"]),
        "present_days":       calc["present_days"],
        "absent_days":        calc["absent_days"],
        "half_days":          calc["half_days"],
        "late_days":          calc["late_days"],
        "overtime_hours":     calc["overtime_hours"],
        "approved_leaves":    calc["approved_leaves"],
        "overtime_amount":    float(p.overtime_amount),
        "bonus":              float(p.bonus),
        "incentive":          float(p.incentive),
        "pf_amount":          float(p.pf_amount),
        "esi_amount":         float(p.esi_amount),
        "loan_deduction":     float(p.loan_deduction),
        "tax_deduction":      float(p.tax_deduction),
        "absent_deduction":   float(calc["absent_deduction"]),
        "half_day_deduction": float(calc["half_day_deduction"]),
        "deductions":         float(p.deductions),
        "custom_earnings":    p.custom_earnings or [],
        "custom_deductions":  p.custom_deductions or [],
        "earnings_items":     earnings_items,
        "deductions_items":   deductions_items,
        "gross_salary":       float(total_earnings),
        "total_deductions":   float(total_deductions),
        "net_salary":         float(p.net_salary),
        "paid_status":        p.paid_status,
        "paid_at":            p.paid_at.strftime("%d %b %Y, %I:%M %p") if p.paid_at else None,
        "paid_by":            p.paid_by.name if p.paid_by else "—",
        "notes":              p.notes or "",
    })


@csrf_exempt
def payroll_line_items(request, payroll_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll, PayrollLineItem

    try:
        p = Payroll.objects.get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll not found"}, status=404)

    if request.method == "GET":
        items    = p.line_items.all().order_by("line_type", "order", "id")
        earnings = [_line_item_dict(i) for i in items if i.line_type == "earning"]
        deductions = [_line_item_dict(i) for i in items if i.line_type == "deduction"]

        total_earnings   = sum(i["amount"] for i in earnings)
        total_deductions = sum(i["amount"] for i in deductions)

        return JsonResponse({
            "success":          True,
            "payroll_id":       p.id,
            "staff":            p.staff.name,
            "month":            p.month,
            "year":             p.year,
            "month_label":      MONTH_NAMES[p.month],
            "earnings":         earnings,
            "deductions":       deductions,
            "total_earnings":   float(total_earnings),
            "total_deductions": float(total_deductions),
            "net_salary":       float(p.net_salary),
            "paid_status":      p.paid_status,
        })

    if request.method == "POST":
        if p.paid_status == "Paid":
            return JsonResponse({"error": "Cannot edit a paid payroll"}, status=400)

        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        line_type = data.get("line_type", "").strip()
        source    = data.get("source", "custom").strip()
        label     = data.get("label", "").strip()
        amount    = _dec(data.get("amount", 0))
        pct       = _dec(data.get("pct")) if data.get("pct") else None
        pct_base  = data.get("pct_base", "").strip()
        note      = data.get("note", "").strip()
        order     = int(data.get("order", 10))

        if line_type not in ("earning", "deduction"):
            return JsonResponse({"error": "line_type must be 'earning' or 'deduction'"}, status=400)
        if not label:
            return JsonResponse({"error": "label is required"}, status=400)
        if amount <= 0 and not pct:
            return JsonResponse({"error": "amount must be > 0"}, status=400)

        if pct and pct > 0:
            if pct_base == "basic":
                base_val = p.basic_salary
            elif pct_base == "gross":
                base_val = p.line_items.filter(line_type="earning").aggregate(t=Sum("amount"))["t"] or Decimal("0")
            else:
                base_val = p.basic_salary
            amount = (base_val * pct / Decimal("100")).quantize(Decimal("0.01"))

        item = PayrollLineItem.objects.create(
            payroll=p, line_type=line_type, source=source,
            label=label, amount=amount, pct=pct,
            pct_base=pct_base, note=note, order=order, is_auto=False
        )

        result = _recalculate_net(p)

        return JsonResponse({
            "success":          True,
            "item":             _line_item_dict(item),
            "net_salary":       result["net_salary"],
            "gross_salary":     result["gross"],
            "total_deductions": result["total_deductions"],
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def payroll_line_item_detail(request, item_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import PayrollLineItem

    try:
        item = PayrollLineItem.objects.select_related("payroll__staff").get(
            id=item_id, payroll__hotel_id=hotel_id
        )
    except PayrollLineItem.DoesNotExist:
        return JsonResponse({"error": "Line item not found"}, status=404)

    p = item.payroll

    if request.method == "GET":
        return JsonResponse({"success": True, "item": _line_item_dict(item)})

    if request.method in ("POST", "PATCH"):
        if p.paid_status == "Paid":
            return JsonResponse({"error": "Cannot edit a paid payroll"}, status=400)

        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if "label"  in data: item.label  = data["label"].strip()
        if "note"   in data: item.note   = data["note"].strip()
        if "order"  in data: item.order  = int(data["order"])
        if "source" in data: item.source = data["source"].strip()

        if "pct" in data and data["pct"]:
            # Percentage mode: amount is calculated from the chosen base
            item.pct      = _dec(data["pct"])
            item.pct_base = data.get("pct_base") or item.pct_base or "basic"
            if item.pct_base == "gross":
                base_val = p.line_items.filter(line_type="earning").aggregate(t=Sum("amount"))["t"] or Decimal("0")
            else:
                base_val = p.basic_salary
            item.amount = (base_val * item.pct / Decimal("100")).quantize(Decimal("0.01"))
        elif "amount" in data:
            # FIX: a fixed amount overrides any percentage, so the edit sticks
            item.amount = _dec(data["amount"])
            item.pct    = None

        item.save()
        result = _recalculate_net(p)

        return JsonResponse({
            "success":          True,
            "item":             _line_item_dict(item),
            "net_salary":       result["net_salary"],
            "gross_salary":     result["gross"],
            "total_deductions": result["total_deductions"],
        })

    if request.method == "DELETE":
        if p.paid_status == "Paid":
            return JsonResponse({"error": "Cannot edit a paid payroll"}, status=400)
        if item.is_auto:
            return JsonResponse({"error": "Auto-generated items cannot be deleted directly. Edit the payroll fields instead."}, status=400)
        item.delete()
        result = _recalculate_net(p)
        return JsonResponse({
            "success":          True,
            "net_salary":       result["net_salary"],
            "gross_salary":     result["gross"],
            "total_deductions": result["total_deductions"],
        })

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def recalculate_payroll(request, payroll_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll

    try:
        p = Payroll.objects.select_related("staff").get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll not found"}, status=404)

    if p.paid_status == "Paid":
        return JsonResponse({"error": "Cannot edit a paid payroll"}, status=400)

    calc = _calculate_payroll(p.staff, p.month, p.year)

    # ── FIX: refresh basic_salary / overtime_amount / deductions from current staff data
    p.basic_salary    = calc["pro_rated_basic"]
    p.overtime_amount = calc["overtime_amount"]
    p.deductions      = calc["absent_deduction"] + calc["half_day_deduction"]
    p.save(update_fields=["basic_salary", "overtime_amount", "deductions"])

    _sync_line_items(p, calc)
    result = _recalculate_net(p)

    return JsonResponse({
        "success":          True,
        "basic_salary":     float(p.basic_salary),
        "net_salary":       result["net_salary"],
        "gross_salary":     result["gross"],
        "total_deductions": result["total_deductions"],
    })
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

    # FIX: only touch a field if the request actually sent it.
    # Before, every Save (which only sends "notes") reset all of these to 0.
    for key in ("bonus", "incentive", "pf_amount", "esi_amount",
                "loan_deduction", "tax_deduction"):
        if key in data:
            setattr(p, key, dec(key))

    if "leave_deduction" in data:
        p.deductions = max(Decimal("0"), Decimal(str(_sf(data["leave_deduction"]))))
    if "custom_earnings"   in data: p.custom_earnings   = data["custom_earnings"]
    if "custom_deductions" in data: p.custom_deductions = data["custom_deductions"]
    if "notes"             in data: p.notes             = data["notes"]

    p.save()

    calc = _calculate_payroll(p.staff, p.month, p.year)

    # Always refresh basic_salary / overtime from the staff's current data
    p.basic_salary    = calc["pro_rated_basic"]
    p.overtime_amount = calc["overtime_amount"]
    p.save(update_fields=["basic_salary", "overtime_amount"])

    # Rebuilds auto items only; custom line items added in the modal are kept
    _sync_line_items(p, calc)
    result = _recalculate_net(p)

    return JsonResponse({
        "success":          True,
        "basic_salary":     float(p.basic_salary),
        "net_salary":       result["net_salary"],
        "gross_salary":     result["gross"],
        "total_deductions": result["total_deductions"],
    })
def staff_payroll_history(request, staff_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll
    from accounts.models import Staff

    try:
        staff = Staff.objects.select_related("department", "user").get(id=staff_id, hotel_id=hotel_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    year = request.GET.get("year")
    qs = Payroll.objects.filter(staff=staff, hotel_id=hotel_id).prefetch_related("line_items").order_by("-year", "-month")
    if year:
        qs = qs.filter(year=int(year))

    history = []
    for p in qs:
        earnings_items   = [_line_item_dict(i) for i in p.line_items.filter(line_type="earning").order_by("order", "id")]
        deductions_items = [_line_item_dict(i) for i in p.line_items.filter(line_type="deduction").order_by("order", "id")]

        total_earnings   = sum(i["amount"] for i in earnings_items)
        total_deductions = sum(i["amount"] for i in deductions_items)

        earnings_by_source   = {}
        deductions_by_source = {}
        for i in earnings_items:
            earnings_by_source.setdefault(i["source"], {"source": i["source"], "total": 0.0, "items": []})
            earnings_by_source[i["source"]]["total"] += i["amount"]
            earnings_by_source[i["source"]]["items"].append(i)
        for i in deductions_items:
            deductions_by_source.setdefault(i["source"], {"source": i["source"], "total": 0.0, "items": []})
            deductions_by_source[i["source"]]["total"] += i["amount"]
            deductions_by_source[i["source"]]["items"].append(i)

        history.append({
            "id":                    p.id,
            "month":                 p.month,
            "year":                  p.year,
            "month_label":           MONTH_NAMES[p.month],
            "basic_salary":          float(p.basic_salary),
            "overtime_amount":       float(p.overtime_amount),
            "bonus":                 float(p.bonus),
            "incentive":             float(p.incentive),
            "pf_amount":             float(p.pf_amount),
            "esi_amount":            float(p.esi_amount),
            "loan_deduction":        float(p.loan_deduction),
            "tax_deduction":         float(p.tax_deduction),
            "deductions":            float(p.deductions),
            "gross_salary":          float(total_earnings),
            "total_deductions":      float(total_deductions),
            "net_salary":            float(p.net_salary),
            "paid_status":           p.paid_status,
            "paid_at":               p.paid_at.strftime("%d %b %Y, %I:%M %p") if p.paid_at else None,
            "paid_by":               p.paid_by.name if p.paid_by else "—",
            "notes":                 p.notes or "",
            "earnings_items":        earnings_items,
            "deductions_items":      deductions_items,
            "earnings_by_source":    list(earnings_by_source.values()),
            "deductions_by_source":  list(deductions_by_source.values()),
        })

    yearly_totals = {
        "total_gross":      sum(h["gross_salary"]     for h in history),
        "total_deductions": sum(h["total_deductions"] for h in history),
        "total_net":        sum(h["net_salary"]        for h in history),
        "paid_months":      sum(1 for h in history if h["paid_status"] == "Paid"),
        "total_months":     len(history),
    }

    return JsonResponse({
        "success":       True,
        "staff_id":      staff.id,
        "staff":         staff.name,
        "employee_id":   getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
        "department":    staff.department.name if staff.department else "—",
        "year_filter":   year,
        "yearly_totals": yearly_totals,
        "history":       history,
    })


def hotel_monthly_summary(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll

    year     = int(request.GET.get("year", timezone.now().year))
    payrolls = Payroll.objects.filter(hotel_id=hotel_id, year=year).prefetch_related("line_items", "staff__department")

    monthly = {}
    for p in payrolls:
        key = p.month
        if key not in monthly:
            monthly[key] = {
                "month":                 key,
                "month_label":           MONTH_NAMES[key],
                "year":                  year,
                "staff_count":           0,
                "paid_count":            0,
                "unpaid_count":          0,
                "total_basic":           0.0,
                "total_overtime":        0.0,
                "total_bonus":           0.0,
                "total_incentive":       0.0,
                "total_pf":              0.0,
                "total_esi":             0.0,
                "total_loan":            0.0,
                "total_tax":             0.0,
                "total_leave_deduction": 0.0,
                "total_gross":           0.0,
                "total_deductions":      0.0,
                "total_net":             0.0,
                "by_department":         {},
                "staff_records":         [],
            }

        m = monthly[key]
        m["staff_count"]          += 1
        m["total_basic"]          += float(p.basic_salary)
        m["total_overtime"]       += float(p.overtime_amount)
        m["total_bonus"]          += float(p.bonus)
        m["total_incentive"]      += float(p.incentive)
        m["total_pf"]             += float(p.pf_amount)
        m["total_esi"]            += float(p.esi_amount)
        m["total_loan"]           += float(p.loan_deduction)
        m["total_tax"]            += float(p.tax_deduction)
        m["total_leave_deduction"] += float(p.deductions)
        m["total_net"]            += float(p.net_salary)

        if p.paid_status == "Paid":
            m["paid_count"] += 1
        else:
            m["unpaid_count"] += 1

        earnings   = p.line_items.filter(line_type="earning").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        deductions = p.line_items.filter(line_type="deduction").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        m["total_gross"]      += float(earnings)
        m["total_deductions"] += float(deductions)

        dept_name = p.staff.department.name if p.staff.department else "Unassigned"
        if dept_name not in m["by_department"]:
            m["by_department"][dept_name] = {
                "department":  dept_name,
                "staff_count": 0,
                "total_gross": 0.0,
                "total_net":   0.0,
            }
        m["by_department"][dept_name]["staff_count"] += 1
        m["by_department"][dept_name]["total_gross"] += float(earnings)
        m["by_department"][dept_name]["total_net"]   += float(p.net_salary)

        m["staff_records"].append({
            "payroll_id":  p.id,
            "staff":       p.staff.name,
            "staff_id":    p.staff.id,
            "employee_id": getattr(p.staff, "employee_id", f"EMP{p.staff.id:03d}"),
            "department":  dept_name,
            "gross":       float(earnings),
            "deductions":  float(deductions),
            "net":         float(p.net_salary),
            "paid_status": p.paid_status,
        })

    for m in monthly.values():
        m["by_department"] = list(m["by_department"].values())

    sorted_months = sorted(monthly.values(), key=lambda x: x["month"])

    year_totals = {
        "total_basic":           sum(m["total_basic"]           for m in sorted_months),
        "total_overtime":        sum(m["total_overtime"]        for m in sorted_months),
        "total_bonus":           sum(m["total_bonus"]           for m in sorted_months),
        "total_incentive":       sum(m["total_incentive"]       for m in sorted_months),
        "total_pf":              sum(m["total_pf"]              for m in sorted_months),
        "total_esi":             sum(m["total_esi"]             for m in sorted_months),
        "total_loan":            sum(m["total_loan"]            for m in sorted_months),
        "total_tax":             sum(m["total_tax"]             for m in sorted_months),
        "total_leave_deduction": sum(m["total_leave_deduction"] for m in sorted_months),
        "total_gross":           sum(m["total_gross"]           for m in sorted_months),
        "total_deductions":      sum(m["total_deductions"]      for m in sorted_months),
        "total_net":             sum(m["total_net"]             for m in sorted_months),
    }

    return JsonResponse({
        "success":     True,
        "year":        year,
        "monthly":     sorted_months,
        "year_totals": year_totals,
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

    from hotel.models import Payroll
    from accounts.models import Hotel

    try:
        p = Payroll.objects.select_related(
            "staff__user", "staff__department", "paid_by"
        ).prefetch_related("line_items").get(id=payroll_id, hotel_id=hotel_id)
    except Payroll.DoesNotExist:
        return JsonResponse({"error": "Payroll record not found.", "success": False}, status=404)

    calc = _calculate_payroll(p.staff, p.month, p.year)

    earnings_items   = [_line_item_dict(i) for i in p.line_items.filter(line_type="earning").order_by("order", "id")]
    deductions_items = [_line_item_dict(i) for i in p.line_items.filter(line_type="deduction").order_by("order", "id")]

    total_earnings   = sum(i["amount"] for i in earnings_items)
    total_deductions = sum(i["amount"] for i in deductions_items)

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
        "staff_id":           p.staff.id,
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
        "original_basic":     _sf(p.staff.salary),
        "basic_salary":       float(p.basic_salary),
        "is_pro_rated":       calc["is_pro_rated"],
        "eligible_days":      calc["eligible_days"],
        "total_days":         calc["total_days"],
        "per_day_rate":       float(calc["per_day_rate"]),
        "per_hour_rate":      float(calc["per_hour_rate"]),
        "present_days":       calc["present_days"],
        "absent_days":        calc["absent_days"],
        "half_days":          calc["half_days"],
        "late_days":          calc["late_days"],
        "overtime_hours":     calc["overtime_hours"],
        "approved_leaves":    calc["approved_leaves"],
        "overtime_amount":    float(p.overtime_amount),
        "bonus":              float(p.bonus),
        "incentive":          float(p.incentive),
        "pf_amount":          float(p.pf_amount),
        "esi_amount":         float(p.esi_amount),
        "loan_deduction":     float(p.loan_deduction),
        "tax_deduction":      float(p.tax_deduction),
        "absent_deduction":   float(calc["absent_deduction"]),
        "half_day_deduction": float(calc["half_day_deduction"]),
        "deductions":         float(p.deductions),
        "custom_earnings":    p.custom_earnings or [],
        "custom_deductions":  p.custom_deductions or [],
        "earnings_items":     earnings_items,
        "deductions_items":   deductions_items,
        "gross_salary":       float(total_earnings),
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

    from hotel.models import Payroll
    from accounts.models import Hotel

    try:
        p = Payroll.objects.select_related(
            "staff__user", "staff__department", "paid_by"
        ).prefetch_related("line_items").get(id=payroll_id, hotel_id=hotel_id)
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

    p      = payroll
    styles = getSampleStyleSheet()
    buf    = BytesIO()

    doc = SimpleDocTemplate(buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)

    month_label = MONTH_NAMES[p.month]
    hotel_name  = hotel.hotel_name if hotel else "Hotel ERP"

    story       = []
    header_data = []
    logo_img    = None

    if hotel and hotel.logo:
        try:
            if hasattr(hotel.logo, "path"):
                logo_img = Image(hotel.logo.path, width=50, height=50)
        except Exception:
            pass

    title = Paragraph(f"<b>{hotel_name}</b>", styles["Title"])
    header_data.append([logo_img or "", title])
    story.append(Table(header_data, colWidths=[60, 400]))
    story.append(Spacer(1, 5))
    story.append(Paragraph(f"Payslip - {month_label} {p.year}", styles["Heading2"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Employee: {p.staff.name}", styles["Normal"]))
    story.append(Paragraph(f"Employee ID: {getattr(p.staff, 'employee_id', f'EMP{p.staff.id:03d}')}", styles["Normal"]))
    story.append(Paragraph(f"Department: {p.staff.department.name if p.staff.department else '-'}", styles["Normal"]))
    story.append(Paragraph(f"Email: {p.staff.user.email if p.staff.user else '-'}", styles["Normal"]))
    story.append(Spacer(1, 12))

    earnings_items   = list(p.line_items.filter(line_type="earning").order_by("order", "id"))
    deductions_items = list(p.line_items.filter(line_type="deduction").order_by("order", "id"))

    total_earnings   = sum(float(i.amount) for i in earnings_items)
    total_deductions = sum(float(i.amount) for i in deductions_items)

    story.append(Paragraph("<b>Salary Details</b>", styles["Heading3"]))
    story.append(Spacer(1, 8))

    earn_rows = [[i.label, f"{float(i.amount):,.2f}"] for i in earnings_items]
    earn_rows.append(["Gross Salary", f"{total_earnings:,.2f}"])

    ded_rows = [[i.label, f"{float(i.amount):,.2f}"] for i in deductions_items]
    ded_rows.append(["Total Deduction", f"{total_deductions:,.2f}"])

    max_len = max(len(earn_rows), len(ded_rows))
    while len(earn_rows) < max_len: earn_rows.append(["", ""])
    while len(ded_rows)  < max_len: ded_rows.append(["", ""])

    table_data = [["Earnings", "Amount (₹)", "Deductions", "Amount (₹)"]]
    for i in range(max_len):
        table_data.append([earn_rows[i][0], earn_rows[i][1], ded_rows[i][0], ded_rows[i][1]])

    main_table = Table(table_data, colWidths=[145, 75, 145, 75])
    main_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 1), (1, -1), colors.HexColor("#ecfdf5")),
        ("BACKGROUND", (2, 1), (3, -1), colors.HexColor("#fef2f2")),
        ("FONTNAME",   (0, max_len), (1, max_len), "Helvetica-Bold"),
        ("FONTNAME",   (2, max_len), (3, max_len), "Helvetica-Bold"),
    ]))

    story.append(main_table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"<b>Net Salary: ₹{float(p.net_salary):,.2f}</b>", styles["Heading2"]))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def _send_payslip_email(payroll, hotel, payment_mode, reference, pdf_bytes):
    from django.core.mail import EmailMultiAlternatives
    from email.mime.base import MIMEBase
    from email import encoders
    from django.conf import settings

    p           = payroll
    month_label = MONTH_NAMES[p.month]
    subject     = f"Salary Credited - {month_label} {p.year}"
    from_email  = settings.DEFAULT_FROM_EMAIL
    to_email    = [p.staff.user.email]

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


@csrf_exempt
def financial_account(request, staff_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import EmployeeFinancialAccount
    from accounts.models import Staff

    try:
        staff = Staff.objects.select_related("department").get(id=staff_id, hotel_id=hotel_id)
    except Staff.DoesNotExist:
        return JsonResponse({"error": "Staff not found"}, status=404)

    account, _ = EmployeeFinancialAccount.objects.get_or_create(staff=staff)

    if request.method == "GET":
        return JsonResponse({
            "success":          True,
            "staff_id":         staff.id,
            "staff":            staff.name,
            "employee_id":      getattr(staff, "employee_id", f"EMP{staff.id:03d}"),
            "department":       staff.department.name if staff.department else "—",
            "pf_balance":       float(account.pf_balance),
            "esi_balance":      float(account.esi_balance),
            "loan_balance":     float(account.loan_balance),
            "advance_balance":  float(account.advance_balance),
            "gratuity_balance": float(account.gratuity_balance),
            "updated_at":       account.updated_at.strftime("%d %b %Y, %I:%M %p"),
        })

    if request.method in ("POST", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if "pf_balance"       in data: account.pf_balance       = _dec(data["pf_balance"])
        if "esi_balance"      in data: account.esi_balance       = _dec(data["esi_balance"])
        if "loan_balance"     in data: account.loan_balance      = _dec(data["loan_balance"])
        if "advance_balance"  in data: account.advance_balance   = _dec(data["advance_balance"])
        if "gratuity_balance" in data: account.gratuity_balance  = _dec(data["gratuity_balance"])

        account.save()

        return JsonResponse({
            "success":          True,
            "pf_balance":       float(account.pf_balance),
            "esi_balance":      float(account.esi_balance),
            "loan_balance":     float(account.loan_balance),
            "advance_balance":  float(account.advance_balance),
            "gratuity_balance": float(account.gratuity_balance),
            "updated_at":       account.updated_at.strftime("%d %b %Y, %I:%M %p"),
        })

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def final_settlements(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import FinalSettlement
    from accounts.models import Staff

    if request.method == "GET":
        qs = FinalSettlement.objects.filter(staff__hotel_id=hotel_id).select_related("staff__department").order_by("-last_working_day")

        data = []
        for s in qs:
            data.append({
                "id":               s.id,
                "staff_id":         s.staff.id,
                "staff":            s.staff.name,
                "employee_id":      getattr(s.staff, "employee_id", f"EMP{s.staff.id:03d}"),
                "department":       s.staff.department.name if s.staff.department else "—",
                "last_working_day": str(s.last_working_day),
                "pending_salary":   float(s.pending_salary),
                "leave_encashment": float(s.leave_encashment),
                "gratuity":         float(s.gratuity),
                "pf_payable":       float(s.pf_payable),
                "total_deductions": float(s.total_deductions),
                "final_amount":     float(s.final_amount),
                "settled_at":       s.settled_at.strftime("%d %b %Y, %I:%M %p") if s.settled_at else None,
            })

        return JsonResponse({"success": True, "count": len(data), "settlements": data})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        staff_id = data.get("staff_id")
        if not staff_id:
            return JsonResponse({"error": "staff_id is required"}, status=400)

        try:
            staff = Staff.objects.get(id=staff_id, hotel_id=hotel_id)
        except Staff.DoesNotExist:
            return JsonResponse({"error": "Staff not found"}, status=404)

        pending_salary   = _dec(data.get("pending_salary", 0))
        leave_encashment = _dec(data.get("leave_encashment", 0))
        gratuity         = _dec(data.get("gratuity", 0))
        pf_payable       = _dec(data.get("pf_payable", 0))
        total_deductions = _dec(data.get("total_deductions", 0))

        final_amount = max(
            pending_salary + leave_encashment + gratuity + pf_payable - total_deductions,
            Decimal("0")
        )

        last_working_day_str = data.get("last_working_day")
        try:
            last_working_day = datetime.strptime(last_working_day_str, "%Y-%m-%d").date()
        except Exception:
            return JsonResponse({"error": "last_working_day is required (YYYY-MM-DD)"}, status=400)

        settlement = FinalSettlement.objects.create(
            staff=staff,
            last_working_day=last_working_day,
            pending_salary=pending_salary,
            leave_encashment=leave_encashment,
            gratuity=gratuity,
            pf_payable=pf_payable,
            total_deductions=total_deductions,
            final_amount=final_amount,
            settled_at=timezone.now() if data.get("mark_settled") else None,
        )

        return JsonResponse({
            "success":          True,
            "id":               settlement.id,
            "staff":            staff.name,
            "final_amount":     float(settlement.final_amount),
            "last_working_day": str(settlement.last_working_day),
            "settled_at":       settlement.settled_at.strftime("%d %b %Y, %I:%M %p") if settlement.settled_at else None,
        }, status=201)

    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
def final_settlement_detail(request, settlement_id):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import FinalSettlement

    try:
        s = FinalSettlement.objects.select_related("staff__department").get(
            id=settlement_id, staff__hotel_id=hotel_id
        )
    except FinalSettlement.DoesNotExist:
        return JsonResponse({"error": "Settlement not found"}, status=404)

    if request.method == "GET":
        return JsonResponse({
            "success":          True,
            "id":               s.id,
            "staff_id":         s.staff.id,
            "staff":            s.staff.name,
            "employee_id":      getattr(s.staff, "employee_id", f"EMP{s.staff.id:03d}"),
            "department":       s.staff.department.name if s.staff.department else "—",
            "last_working_day": str(s.last_working_day),
            "pending_salary":   float(s.pending_salary),
            "leave_encashment": float(s.leave_encashment),
            "gratuity":         float(s.gratuity),
            "pf_payable":       float(s.pf_payable),
            "total_deductions": float(s.total_deductions),
            "final_amount":     float(s.final_amount),
            "settled_at":       s.settled_at.strftime("%d %b %Y, %I:%M %p") if s.settled_at else None,
        })

    if request.method in ("POST", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if "pending_salary"   in data: s.pending_salary   = _dec(data["pending_salary"])
        if "leave_encashment" in data: s.leave_encashment = _dec(data["leave_encashment"])
        if "gratuity"         in data: s.gratuity         = _dec(data["gratuity"])
        if "pf_payable"       in data: s.pf_payable       = _dec(data["pf_payable"])
        if "total_deductions" in data: s.total_deductions = _dec(data["total_deductions"])
        if "last_working_day" in data:
            try:
                s.last_working_day = datetime.strptime(data["last_working_day"], "%Y-%m-%d").date()
            except Exception:
                pass
        if data.get("mark_settled") and not s.settled_at:
            s.settled_at = timezone.now()

        s.final_amount = max(
            s.pending_salary + s.leave_encashment + s.gratuity + s.pf_payable - s.total_deductions,
            Decimal("0")
        )
        s.save()

        return JsonResponse({
            "success":      True,
            "final_amount": float(s.final_amount),
            "settled_at":   s.settled_at.strftime("%d %b %Y, %I:%M %p") if s.settled_at else None,
        })

    if request.method == "DELETE":
        s.delete()
        return JsonResponse({"success": True, "deleted": settlement_id})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def payroll_export_csv(request):
    hotel_id = request.session.get("hotel_id")
    if not hotel_id:
        return JsonResponse({"error": "Login required"}, status=401)

    from hotel.models import Payroll

    month = int(request.GET.get("month", timezone.now().month))
    year  = int(request.GET.get("year",  timezone.now().year))

    payrolls = Payroll.objects.filter(hotel_id=hotel_id, month=month, year=year).select_related(
        "staff__department", "staff__user", "paid_by"
    ).prefetch_related("line_items")

    month_label = MONTH_NAMES[month]
    filename    = f"Payroll_{month_label}_{year}.csv"

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([
        "Employee ID", "Name", "Department", "Email",
        "Basic", "Overtime", "Bonus", "Incentive",
        "Gross", "Leave Deduction", "PF", "ESI",
        "Loan", "Tax", "Custom Deductions", "Total Deductions",
        "Net Salary", "Status", "Paid At",
    ])

    for p in payrolls:
        earnings   = float(p.line_items.filter(line_type="earning").aggregate(t=Sum("amount"))["t"] or 0)
        deductions = float(p.line_items.filter(line_type="deduction").aggregate(t=Sum("amount"))["t"] or 0)
        custom_ded = sum(_sf(d.get("amount")) for d in (p.custom_deductions or []))

        writer.writerow([
            getattr(p.staff, "employee_id", f"EMP{p.staff.id:03d}"),
            p.staff.name,
            p.staff.department.name if p.staff.department else "—",
            p.staff.user.email if p.staff.user else "",
            float(p.basic_salary),
            float(p.overtime_amount),
            float(p.bonus),
            float(p.incentive),
            earnings,
            float(p.deductions),
            float(p.pf_amount),
            float(p.esi_amount),
            float(p.loan_deduction),
            float(p.tax_deduction),
            custom_ded,
            deductions,
            float(p.net_salary),
            p.paid_status,
            p.paid_at.strftime("%d %b %Y") if p.paid_at else "",
        ])

    return response
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

        
        if att.check_out:
            end_time = att.check_out
        else:
            end_time = timezone.now()

        
        check_in = att.check_in
        end_time = end_time

        diff = end_time - check_in

        working_hours = round(diff.total_seconds() / 3600, 2)

        if working_hours < 0:
            working_hours = 0

        overtime_hours = max(0, round(working_hours - 8, 2))

    return {
        "status": att.status,
        "check_in": att.check_in.strftime("%I:%M %p") if att.check_in else None,
        "check_out": att.check_out.strftime("%I:%M %p") if att.check_out else None,
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

    return None         



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
            local_t = safe_localtime(pay.received_at)

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
from accounts.decorators import staff_login_required


def _get_hotel():
    try:
        from django_tenants.utils import schema_context
        from accounts.models import Hotel
        tenant_schema = connection.tenant.schema_name
        with schema_context('public'):
            return Hotel.objects.filter(schema_name=tenant_schema).first()
    except Exception:
        return None



from datetime import datetime, date
from django.utils import timezone


def safe_localtime(value):
    """
    Safely handle:
    - None
    - datetime.date
    - naive datetime
    - timezone-aware datetime
    """

    if value is None:
        return None

    # A pure DateField value does NOT need timezone conversion.
    # Important: datetime is a subclass of date, so exclude datetime.
    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    # Only datetime objects should reach Django timezone functions.
    if isinstance(value, datetime):

        if timezone.is_naive(value):
            value = timezone.make_aware(
                value,
                timezone.get_current_timezone()
            )

        return timezone.localtime(value)

    # Unknown value: return unchanged rather than crashing.
    return value


@staff_login_required
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

    ACCOUNTANT_KEYWORDS = ['accountant', 'account', 'finance', 'billing',
                           'manager', 'owner', 'admin', 'hotel']
    dept_name = (staff.department.name.lower() if staff.department else "")
    role      = (getattr(staff, 'role', '') or '').lower()
    combined  = dept_name + " " + role

    if not any(k in combined for k in ACCOUNTANT_KEYWORDS):
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
            local_time = safe_localtime(order.created_at)
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
        {"type": "room",       "label": "Room Charges", "total": float(room_charges_today),  "icon": "fa-bed"},
        {"type": "restaurant", "label": "Restaurant",   "total": float(restaurant_today),    "icon": "fa-utensils"},
        {"type": "laundry",    "label": "Laundry",      "total": float(laundry_today),       "icon": "fa-tshirt"},
        {"type": "minibar",    "label": "Minibar",      "total": float(minibar_today),       "icon": "fa-wine-glass"},
        {"type": "spa",        "label": "Spa",          "total": float(spa_today),           "icon": "fa-spa"},
        {"type": "transport",  "label": "Transport",    "total": float(transport_today),     "icon": "fa-car"},
        {"type": "other",      "label": "Other",        "total": float(other_charges_today), "icon": "fa-tag"},
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
        expected_room_income       = Decimal("0")
        expected_restaurant_income = Decimal("0")
        total_expected             = Decimal("0")

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
        local_time = safe_localtime(pay.received_at)
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
            "id":              payroll.id,
            "month_label":     MONTH_NAMES[payroll.month],
            "year":            payroll.year,
            "basic_salary":    float(payroll.basic_salary),
            "overtime_amount": float(payroll.overtime_amount),
            "bonus":           float(payroll.bonus),
            "incentive":       float(payroll.incentive),
            "pf_amount":       float(payroll.pf_amount),
            "esi_amount":      float(payroll.esi_amount),
            "loan_deduction":  float(payroll.loan_deduction),
            "tax_deduction":   float(payroll.tax_deduction),
            "deductions":      float(payroll.deductions),
            "net_salary":      float(payroll.net_salary),
            "paid_status":     payroll.paid_status,
            "paid_at":         payroll.paid_at.strftime("%d %b %Y, %I:%M %p") if payroll.paid_at else None,
            "earnings_items":  earnings_items,
            "deductions_items": deductions_items,
        }
    else:
        current_payroll = None

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

        "current_payroll":     current_payroll,
        "payroll_history":     payroll_history_list,
        "payroll_month_label": MONTH_NAMES[month],
        "payroll_year":        year,

        "rooms_json":  json.dumps(room_list),
        "room_units":  room_units,
        "recent_tasks": recent_tasks,
        "housekeeping_staff": hotel_staff.filter(
            department__name__icontains="housekeeping"
        ),
    }

    return render(request, "accountant/dashboard.html", context)

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

    d = fm = fy = None

    if filter_date:
        try:
            d = date.fromisoformat(filter_date)
        except ValueError:
            return JsonResponse({"success": False, "error": "Invalid date"})
        payments_qs = payments_qs.filter(received_at__date=d)
    elif filter_month:
        try:
            parts  = filter_month.split("-")
            fy, fm = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            return JsonResponse({"success": False, "error": "Invalid month"})
        payments_qs = payments_qs.filter(received_at__month=fm, received_at__year=fy)
    else:
        d = timezone.now().date()
        payments_qs = payments_qs.filter(received_at__date=d)

    if filter_staff:
        payments_qs = payments_qs.filter(received_by__id=filter_staff)

    total_collection  = float(payments_qs.aggregate(t=Sum("amount"))["t"] or 0)
    transaction_count = payments_qs.count()

    tax_collected = float(
        payments_qs.aggregate(
            t=Sum("folio__charges__tax_amount")
        )["t"] or 0
    )

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

    room_collected = float(
        payments_qs.filter(
            folio__charges__charge_type="room"
        ).distinct().aggregate(t=Sum("amount"))["t"] or 0
    )
    if room_collected:
        charge_type_totals["room"] = room_collected

    for ctype in ["laundry", "minibar", "spa", "transport"]:
        collected = float(
            payments_qs.filter(
                folio__charges__charge_type=ctype
            ).distinct().aggregate(t=Sum("amount"))["t"] or 0
        )
        if collected:
            charge_type_totals[ctype] = collected

    other_collected = float(
        payments_qs.filter(folio__isnull=False).exclude(
            folio__charges__charge_type__in=["room", "laundry", "minibar", "spa", "transport"]
        ).distinct().aggregate(t=Sum("amount"))["t"] or 0
    )
    if other_collected:
        charge_type_totals["other"] = other_collected

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
            local_time = safe_localtime(order.created_at)

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

        if rest_total:
            charge_type_totals["restaurant"] = rest_total

    except Exception:
        import traceback
        traceback.print_exc()

    dept_breakdown = []

    for ctype, total in charge_type_totals.items():

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

        if ctype == "room":
            room_service_billed       = []
            room_service_billed_total = 0.0
            room_service_by_room      = {}

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
                    local_time = safe_localtime(order.created_at)
                    bk         = order.booking
                    room_num   = bk.room_unit.room_number if bk and bk.room_unit else None
                    guest_name = bk.guest.full_name if bk and bk.guest else "—"
                    amount     = float(order.total_amount or 0)

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

            txs = []
            for pay in payments_qs.filter(
                folio__charges__charge_type="room"
            ).distinct().order_by("-received_at")[:100]:
                booking    = pay.folio.booking if pay.folio else None
                guest      = booking.guest if booking else None
                local_time = safe_localtime(pay.received_at)
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
                "type":                        "room",
                "label":                       "Room Charges",
                "total":                       total,
                "transaction_count":           len(txs),
                "transactions":                txs,
                "room_service_billed":         room_service_billed,
                "room_service_billed_total":   room_service_billed_total,
                "room_service_billed_count":   len(room_service_billed),
                "room_service_by_room":        list(room_service_by_room.values()),
            })
            continue

        txs = []
        for pay in payments_qs.filter(
            folio__charges__charge_type=ctype
        ).distinct().order_by("-received_at")[:100]:
            booking    = pay.folio.booking if pay.folio else None
            guest      = booking.guest if booking else None
            local_time = safe_localtime(pay.received_at)
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
        local_time = safe_localtime(pay.received_at)

        if pay.folio:
            booking     = pay.folio.booking
            guest       = booking.guest if booking else None
            guest_name  = guest.full_name if guest else "—"
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
    Expense,
    ExpenseCategory,
    PurchaseOrder,
    PurchaseItem,
    MaintenanceLog,
    StockAdjustment,
)

from inventory.models import (
    InventoryItem as MainInventoryItem,
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





def _accountant_staff(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return None

    try:
        return (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return None




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
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
import json

from .models import Staff, User, Hotel




@login_required
@require_GET
def get_email_recipients(request):

    hotel = request.user.hotel

    if hotel is None:
        return JsonResponse(
            {
                "error":
                    "No hotel associated with this user."
            },
            status=400
        )

    staff_qs = (
        Staff.objects
        .filter(
            hotel=hotel,
            is_active=True,
            user__email__isnull=False,
        )
        .exclude(
            user=request.user
        )
        .select_related(
            "user",
            "department"
        )
    )

    staff_list = []

    for staff in staff_qs:

        email = (
            staff.user.email or ""
        ).strip()

        if not email:
            continue

        staff_list.append(
            {
                # IMPORTANT:
                # USER ID, not Staff ID
                "id": staff.user.id,

                "name": staff.name,

                "email": email,

                "department":
                    staff.department.name
                    if staff.department
                    else "No Department",

                "type": "staff",
            }
        )

    hotel_admin_ids = (
        Staff.objects
        .filter(
            hotel=hotel
        )
        .values_list(
            "user_id",
            flat=True
        )
    )

    admin_qs = (
        User.objects
        .filter(
            hotel=hotel,
            is_staff=True,
            is_active=True,
        )
        .exclude(
            id=request.user.id
        )
        .exclude(
            id__in=hotel_admin_ids
        )
    )

    admin_list = []

    for admin in admin_qs:

        email = (
            admin.email or ""
        ).strip()

        if not email:
            continue

        admin_list.append(
            {
                "id":
                    admin.id,

                "name":
                    admin.get_full_name()
                    or admin.username,

                "email":
                    email,

                "department":
                    "Hotel Admin",

                "type":
                    "admin",
            }
        )

    return JsonResponse(
        {
            "recipients":
                staff_list +
                admin_list,

            "hotel_email":
                hotel.email or "",

            "hotel_name":
                hotel.hotel_name,
        }
    )



@login_required
@require_POST
def send_compose_email(request):
   
   
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON payload.'}, status=400)

    subject = (data.get('subject') or '').strip()
    message = (data.get('message') or '').strip()
    recipient_ids = data.get('recipient_ids', [])
    include_hotel_admin = data.get('include_hotel_admin', False)

    
    if not subject:
        return JsonResponse({'error': 'Subject is required.'}, status=400)
    if not message:
        return JsonResponse({'error': 'Message body is required.'}, status=400)
    if not recipient_ids and not include_hotel_admin:
        return JsonResponse({'error': 'Please select at least one recipient.'}, status=400)

    hotel = request.user.hotel
    if hotel is None:
        return JsonResponse({'error': 'No hotel associated with this user.'}, status=400)

    # --- Resolve recipient emails ---
    to_emails = []

    if recipient_ids:
        users = User.objects.filter(
            id__in=recipient_ids,
            hotel=hotel,
            is_active=True,
        )
        for u in users:
            email = (u.email or '').strip()
            if email and email not in to_emails:
                to_emails.append(email)

    if include_hotel_admin and hotel.email:
        hotel_email = hotel.email.strip()
        if hotel_email and hotel_email not in to_emails:
            to_emails.append(hotel_email)

    if not to_emails:
        return JsonResponse({'error': 'No valid email addresses found for selected recipients.'}, status=400)

    # --- Compose & send ---
    sender_name = request.user.get_full_name() or request.user.username
    from_email = settings.DEFAULT_FROM_EMAIL

    full_message = (
        f"Message from: {sender_name} ({request.user.email})\n"
        f"Hotel: {hotel.hotel_name}\n"
        f"{'─' * 40}\n\n"
        f"{message}"
    )

    try:
        send_mail(
            subject=subject,
            message=full_message,
            from_email=from_email,
            recipient_list=to_emails,
            fail_silently=False,
        )
    except Exception as e:
        return JsonResponse({'error': f'Failed to send email: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'sent_to': to_emails,
        'count': len(to_emails),
        'message': f'Email sent successfully to {len(to_emails)} recipient(s).',
    })



def face_attendance_lookup(request):
    """
    Later: kiosk/check-in POSTs a live descriptor here.
    Compares against all registered staff descriptors and returns best match.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        data = json.loads(request.body)
        live = data.get("descriptor")
        if not live or len(live) != 128:
            return JsonResponse({"error": "Invalid descriptor"}, status=400)

        import math
        def euclidean(a, b):
            return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))

        best_staff, best_dist = None, 999
        for s in Staff.objects.exclude(face_descriptor__isnull=True):
            dist = euclidean(live, s.face_descriptor)
            if dist < best_dist:
                best_dist, best_staff = dist, s

        THRESHOLD = 0.5  # lower = stricter match; tune based on testing
        if best_staff and best_dist < THRESHOLD:
            return JsonResponse({
                "success": True,
                "staff_id": best_staff.id,
                "name": best_staff.name,
                "confidence": round(1 - best_dist, 3)
            })
        return JsonResponse({"success": False, "error": "No match found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    



 # ============================================================
# HR PAGE COMMON CONTEXT
# ============================================================

# ============================================================
# HR PAGE COMMON CONTEXT
# ============================================================

def _get_hr_page_context(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return None

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department"
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return None

    hotel = staff.hotel

    # ========================================================
    # ALL STAFF FOR CURRENT HOTEL
    # Used by pages such as Leave -> Apply Leave
    # ========================================================

    staff_members = (
        Staff.objects
        .filter(hotel=hotel)
        .select_related("department")
        .order_by("name")
    )

    return {
        "staff": staff,
        "hotel": hotel,
        "staff_members": staff_members,
    }


# ============================================================
# EMPLOYEES PAGE
# ============================================================

def hr_employees_page(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        current_staff = Staff.objects.select_related(
            "hotel",
            "department"
        ).get(id=staff_id)

    except Staff.DoesNotExist:
        return redirect("staff_login")


    hotel = current_staff.hotel


    # =====================================================
    # EMPLOYEES
    # =====================================================

    employees = (
        Staff.objects
        .filter(hotel=hotel)
        .select_related(
            "department",
            "user"
        )
        .order_by("name")
    )


    # =====================================================
    # DEPARTMENTS
    # =====================================================

    departments = (
        Department.objects
        .filter(hotel=hotel)
        .annotate(
            staff_count=Count(
                "staff"
            )
        )
        .order_by("name")
    )


    # =====================================================
    # FILTERS
    # =====================================================

    selected_department = (
        request.GET.get("department")
        or ""
    )

    search_query = (
        request.GET.get("q")
        or ""
    ).strip()


    if selected_department:

        employees = employees.filter(
            department_id=selected_department
        )


    if search_query:

        employees = employees.filter(

            Q(
                name__icontains=search_query
            )

            |

            Q(
                employee_id__icontains=search_query
            )

            |

            Q(
                phone__icontains=search_query
            )

            |

            Q(
                user__email__icontains=search_query
            )

        )


    # =====================================================
    # COUNTS
    # =====================================================

    total_employees = (
        Staff.objects
        .filter(hotel=hotel)
        .count()
    )


    total_departments = (
        Department.objects
        .filter(hotel=hotel)
        .count()
    )


    # Don't assume every Staff model has is_active.
    active_employees = total_employees


    # =====================================================
    # UNPAID PAYROLL
    # =====================================================

    today = timezone.now().date()

    unpaid_payroll = (
        Payroll.objects
        .filter(
            staff__hotel=hotel,
            month=today.month,
            year=today.year,
            paid_status=False,
        )
        .count()
    )


    # =====================================================
    # CONTEXT
    # =====================================================

    context = {

        "staff": current_staff,

        "hotel": hotel,

        "employees": employees,

        "departments": departments,

        "total_employees":
            total_employees,

        "total_departments":
            total_departments,

        "active_employees":
            active_employees,

        "unpaid_payroll":
            unpaid_payroll,

        "selected_department":
            selected_department,

        "search_query":
            search_query,

        "open_add_employee":
            request.GET.get(
                "action"
            ) == "add",
    }


    return render(
        request,
        "hr/employees.html",
        context
    )


# ============================================================
# ATTENDANCE PAGE
# ============================================================



def hr_attendance_page(request):

    hotel_id = request.session.get("hotel_id")
    staff_id = request.session.get("staff_id")

    # Staff login -> resolve hotel
    if not hotel_id and staff_id:
        staff = Staff.objects.filter(
            id=staff_id
        ).select_related("hotel").first()

        if staff:
            hotel_id = staff.hotel_id
            request.session["hotel_id"] = hotel_id

    if not hotel_id:
        return redirect("staff_login")

    staff_members = (
        Staff.objects
        .filter(hotel_id=hotel_id)
        .select_related("department")
        .order_by("name")
    )

    departments = (
        Department.objects
        .filter(hotel_id=hotel_id)
        .order_by("name")
    )

    context = {
        "staff_members": staff_members,
        "departments": departments,
    }

    return render(
        request,
        "hr/attendance.html",
        context
    )



@require_POST
def hr_mark_employee_attendance(request):

    try:
        # =====================================================
        # HOTEL
        # =====================================================

        hotel_id = request.session.get("hotel_id")
        logged_staff_id = request.session.get("staff_id")

        if not hotel_id and logged_staff_id:

            logged_staff = (
                Staff.objects
                .filter(id=logged_staff_id)
                .select_related("hotel")
                .first()
            )

            if logged_staff:
                hotel_id = logged_staff.hotel_id
                request.session["hotel_id"] = hotel_id

        if not hotel_id:
            return JsonResponse({
                "success": False,
                "error": "Login required"
            }, status=401)

        # =====================================================
        # INPUT
        # =====================================================

        if (
            request.content_type
            and "application/json" in request.content_type
        ):

            try:
                data = json.loads(request.body or "{}")
            except json.JSONDecodeError:
                return JsonResponse({
                    "success": False,
                    "error": "Invalid JSON"
                }, status=400)

        else:
            data = request.POST

        staff_id = (
            data.get("staff_id")
            or data.get("staff")
        )

        date_value = data.get("date")
        status = data.get("status")

        check_in_value = data.get("check_in")
        check_out_value = data.get("check_out")

        notes = (
            data.get("notes")
            or ""
        ).strip()

        # =====================================================
        # VALIDATE STAFF
        # =====================================================

        if not staff_id:
            return JsonResponse({
                "success": False,
                "error": "Employee is required"
            }, status=400)

        staff = (
            Staff.objects
            .filter(
                id=staff_id,
                hotel_id=hotel_id
            )
            .select_related("department")
            .first()
        )

        if not staff:
            return JsonResponse({
                "success": False,
                "error": "Employee not found"
            }, status=404)

        # =====================================================
        # DATE
        # =====================================================

        if not date_value:
            attendance_date = timezone.localdate()

        else:
            try:
                attendance_date = datetime.strptime(
                    date_value,
                    "%Y-%m-%d"
                ).date()

            except ValueError:
                return JsonResponse({
                    "success": False,
                    "error": "Invalid date"
                }, status=400)

        # =====================================================
        # STATUS
        # =====================================================

        allowed_statuses = [
            "Present",
            "Late",
            "Absent",
            "Half Day",
            "Leave",
        ]

        if status not in allowed_statuses:
            return JsonResponse({
                "success": False,
                "error": "Invalid attendance status"
            }, status=400)

        # =====================================================
        # TIME
        # =====================================================

        check_in = None
        check_out = None

        if check_in_value:

            try:
                check_in = datetime.strptime(
                    check_in_value,
                    "%H:%M"
                ).time()

            except ValueError:
                return JsonResponse({
                    "success": False,
                    "error": "Invalid check-in time"
                }, status=400)

        if check_out_value:

            try:
                check_out = datetime.strptime(
                    check_out_value,
                    "%H:%M"
                ).time()

            except ValueError:
                return JsonResponse({
                    "success": False,
                    "error": "Invalid check-out time"
                }, status=400)

        # =====================================================
        # CREATE / UPDATE ATTENDANCE
        # =====================================================

        attendance, created = (
            Attendance.objects.update_or_create(

                staff=staff,
                date=attendance_date,

                defaults={
                    "status": status,
                    "check_in": check_in,
                    "check_out": check_out,
                }
            )
        )

        # =====================================================
        # RESPONSE
        # =====================================================

        return JsonResponse({
            "success": True,

            "created": created,

            "message": (
                "Attendance marked successfully"
                if created
                else
                "Attendance updated successfully"
            ),

            "attendance": {
                "id": attendance.id,
                "staff_id": staff.id,
                "staff_name": staff.name,

                "department": (
                    staff.department.name
                    if staff.department
                    else ""
                ),

                "date": attendance.date.strftime(
                    "%Y-%m-%d"
                ),

                "status": attendance.status,

                "check_in": (
                    attendance.check_in.strftime("%H:%M")
                    if attendance.check_in
                    else ""
                ),

                "check_out": (
                    attendance.check_out.strftime("%H:%M")
                    if attendance.check_out
                    else ""
                ),
            }
        })

    except Exception as e:

        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)



# ============================================================
# SHIFTS PAGE
# ============================================================

def hr_shifts_page(request):

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    return render(
        request,
        "hr/shifts.html",
        context
    )


# ============================================================
# HR - LEAVE PAGE
# ============================================================

def hr_leave_page(request):

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    context["active_hr_page"] = "leave"

    return render(
        request,
        "hr/leave.html",
        context
    )





# ============================================================
# HR - PAYROLL PAGE
# ============================================================

def hr_payroll_page(request):

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    # --------------------------------------------------------
    # ACTIVE NAVIGATION
    # --------------------------------------------------------

    context["active_hr_page"] = "payroll"

    # --------------------------------------------------------
    # CURRENT DATE
    # --------------------------------------------------------

    now = timezone.now()

    if timezone.is_aware(now):
        today = timezone.localtime(now).date()
    else:
        today = now.date()

    context["current_month"] = today.month
    context["current_year"] = today.year

    # --------------------------------------------------------
    # VIEW MODE
    #
    # /hr/payroll/
    #       -> payroll management
    #
    # /hr/payroll/?view=history
    #       -> salary records
    # --------------------------------------------------------

    view_mode = request.GET.get(
        "view",
        "payroll"
    )

    if view_mode not in [
        "payroll",
        "history",
    ]:
        view_mode = "payroll"

    context["payroll_view"] = view_mode

    # --------------------------------------------------------
    # YEARS
    # --------------------------------------------------------

    context["payroll_years"] = list(
        range(
            today.year - 4,
            today.year + 2
        )
    )

    return render(
        request,
        "hr/payroll.html",
        context
    )


# ============================================================
# TASKS PAGE
# ============================================================

def hr_tasks_page(request):

    # ========================================================
    # EXISTING HR BASE CONTEXT
    # ========================================================

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return redirect("staff_login")

    # ========================================================
    # ACTIVE NAVIGATION
    # ========================================================

    context["active_hr_page"] = "tasks"

    # ========================================================
    # STAFF
    # ========================================================

    staff_members = (
        Staff.objects
        .filter(
            hotel_id=hotel_id
        )
        .select_related(
            "department"
        )
        .order_by(
            "name"
        )
    )

    # ========================================================
    # DEPARTMENTS
    # ========================================================

    departments = (
        Department.objects
        .filter(
            hotel_id=hotel_id
        )
        .order_by(
            "name"
        )
    )

    # ========================================================
    # TASKS
    # ========================================================

    tasks = (
        Task.objects
        .filter(
            staff__hotel_id=hotel_id
        )
        .select_related(
            "staff",
            "staff__department",
            "room",
            "room_unit"
        )
        .order_by(
            "-created_at"
        )
    )

    # ========================================================
    # STATISTICS
    # ========================================================

    context.update(
        {
            "staff_members": staff_members,
            "departments": departments,

            "tasks": tasks,

            "total_tasks": tasks.count(),

            "pending_tasks": tasks.filter(
                status="Pending"
            ).count(),

            "in_progress_tasks": tasks.filter(
                status="In Progress"
            ).count(),

            "completed_tasks": tasks.filter(
                status="Completed"
            ).count(),

            # Opens modal when:
            # /hr/tasks/?action=assign
            "open_assign_modal": (
                request.GET.get("action")
                == "assign"
            ),
        }
    )

    return render(
        request,
        "hr/tasks.html",
        context
    )





# ============================================================
# HR REPORTS
# ============================================================

from datetime import datetime, timedelta
from decimal import Decimal


from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET


def _hr_report_dates(request):
    """
    Returns validated start_date and end_date.

    Default:
        first day of current month -> today
    """

    today = timezone.now().date()

    default_start = today.replace(day=1)
    default_end = today

    start_raw = request.GET.get("start_date")
    end_raw = request.GET.get("end_date")

    try:
        start_date = (
            datetime.strptime(start_raw, "%Y-%m-%d").date()
            if start_raw
            else default_start
        )
    except (TypeError, ValueError):
        start_date = default_start

    try:
        end_date = (
            datetime.strptime(end_raw, "%Y-%m-%d").date()
            if end_raw
            else default_end
        )
    except (TypeError, ValueError):
        end_date = default_end

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


# ============================================================
# REPORT PAGE
# ============================================================

def hr_reports_page(request):

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return redirect("staff_login")

    context["active_hr_page"] = "reports"

    # --------------------------------------------------------
    # DEPARTMENTS
    # --------------------------------------------------------

    departments = (
        Department.objects
        .filter(hotel_id=hotel_id)
        .order_by("name")
    )

    # --------------------------------------------------------
    # STAFF
    # --------------------------------------------------------

    staff_members = (
        Staff.objects
        .filter(hotel_id=hotel_id)
        .select_related("department")
        .order_by("name")
    )

    # --------------------------------------------------------
    # DEFAULT DATE RANGE
    # --------------------------------------------------------

    today = timezone.now().date()
    start_date = today.replace(day=1)

    context.update({
        "departments": departments,
        "staff_members": staff_members,

        "report_start_date": start_date.strftime("%Y-%m-%d"),
        "report_end_date": today.strftime("%Y-%m-%d"),
    })

    return render(
        request,
        "hr/reports.html",
        context
    )


# ============================================================
# REPORT DATA API
# ============================================================

@require_GET
def hr_reports_data(request):

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return JsonResponse(
            {
                "success": False,
                "error": "Session expired. Please login again."
            },
            status=401
        )

    # ========================================================
    # FILTERS
    # ========================================================

    start_date, end_date = _hr_report_dates(request)

    department_id = request.GET.get("department")
    staff_id = request.GET.get("staff")

    # ========================================================
    # STAFF QUERYSET
    # ========================================================

    staff_qs = (
        Staff.objects
        .filter(hotel_id=hotel_id)
        .select_related("department")
    )

    if department_id:
        staff_qs = staff_qs.filter(
            department_id=department_id
        )

    if staff_id:
        staff_qs = staff_qs.filter(
            id=staff_id
        )

    staff_ids = list(
        staff_qs.values_list("id", flat=True)
    )

    # ========================================================
    # ATTENDANCE
    # ========================================================

    attendance_qs = (
        Attendance.objects
        .filter(
            hotel_id=hotel_id,
            staff_id__in=staff_ids,
            date__range=(start_date, end_date)
        )
        .select_related(
            "staff",
            "staff__department"
        )
    )

    attendance_stats = attendance_qs.aggregate(

        present=Count(
            "id",
            filter=Q(status="Present")
        ),

        late=Count(
            "id",
            filter=Q(status="Late")
        ),

        absent=Count(
            "id",
            filter=Q(status="Absent")
        ),

        half_day=Count(
            "id",
            filter=Q(status="Half Day")
        ),

        overtime=Sum(
            "overtime_hours"
        )
    )

    # ========================================================
    # TASKS
    # ========================================================

    task_qs = (
        Task.objects
        .filter(
            staff__hotel_id=hotel_id,
            staff_id__in=staff_ids,
            created_at__date__range=(
                start_date,
                end_date
            )
        )
        .select_related(
            "staff",
            "staff__department"
        )
    )

    task_stats = task_qs.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="Pending")
        ),

        in_progress=Count(
            "id",
            filter=Q(status="In Progress")
        ),

        completed=Count(
            "id",
            filter=Q(status="Completed")
        )
    )

    # ========================================================
    # LEAVE
    # ========================================================

    leave_qs = (
        LeaveRequest.objects
        .filter(
            staff__hotel_id=hotel_id,
            staff_id__in=staff_ids,

            # Leave overlaps selected period
            from_date__lte=end_date,
            to_date__gte=start_date
        )
        .select_related(
            "staff",
            "staff__department"
        )
    )

    leave_stats = leave_qs.aggregate(

        total=Count("id"),

        pending=Count(
            "id",
            filter=Q(status="Pending")
        ),

        approved=Count(
            "id",
            filter=Q(status="Approved")
        ),

        rejected=Count(
            "id",
            filter=Q(status="Rejected")
        )
    )

    # ========================================================
    # PAYROLL
    #
    # Payroll is month/year based in your current system.
    # Include payroll records whose month falls inside
    # selected report range.
    # ========================================================

    payroll_qs = (
        Payroll.objects
        .filter(
            staff__hotel_id=hotel_id,
            staff_id__in=staff_ids
        )
        .select_related(
            "staff",
            "staff__department"
        )
    )

    payroll_filtered = []

    total_payroll = Decimal("0")
    paid_payroll = Decimal("0")
    unpaid_payroll = Decimal("0")

    paid_count = 0
    unpaid_count = 0

    for payroll in payroll_qs:

        try:
            payroll_date = datetime(
                payroll.year,
                payroll.month,
                1
            ).date()
        except (TypeError, ValueError):
            continue

        # Last day of payroll month
        if payroll.month == 12:
            next_month = datetime(
                payroll.year + 1,
                1,
                1
            ).date()
        else:
            next_month = datetime(
                payroll.year,
                payroll.month + 1,
                1
            ).date()

        payroll_month_end = (
            next_month -
            timedelta(days=1)
        )

        # Month overlaps selected report range
        if (
            payroll_date <= end_date
            and payroll_month_end >= start_date
        ):

            payroll_filtered.append(payroll)

            amount = Decimal(
                str(payroll.net_salary or 0)
            )

            total_payroll += amount

            if payroll.paid_status:
                paid_count += 1
                paid_payroll += amount

            else:
                unpaid_count += 1
                unpaid_payroll += amount

    # ========================================================
    # STAFF SUMMARY
    # ========================================================

    staff_summary = []

    for staff in staff_qs.order_by("name"):

        staff_attendance = attendance_qs.filter(
            staff=staff
        )

        staff_tasks = task_qs.filter(
            staff=staff
        )

        staff_leaves = leave_qs.filter(
            staff=staff
        )

        staff_payroll_total = Decimal("0")

        for payroll in payroll_filtered:
            if payroll.staff_id == staff.id:
                staff_payroll_total += Decimal(
                    str(payroll.net_salary or 0)
                )

        present = staff_attendance.filter(
            status="Present"
        ).count()

        late = staff_attendance.filter(
            status="Late"
        ).count()

        absent = staff_attendance.filter(
            status="Absent"
        ).count()

        half_day = staff_attendance.filter(
            status="Half Day"
        ).count()

        overtime = (
            staff_attendance.aggregate(
                total=Sum("overtime_hours")
            )["total"]
            or 0
        )

        total_tasks = staff_tasks.count()

        completed_tasks = staff_tasks.filter(
            status="Completed"
        ).count()

        pending_tasks = staff_tasks.filter(
            status="Pending"
        ).count()

        progress_tasks = staff_tasks.filter(
            status="In Progress"
        ).count()

        approved_leaves = staff_leaves.filter(
            status="Approved"
        ).count()

        staff_summary.append({

            "id": staff.id,

            "name": staff.name,

            "employee_id": (
                getattr(
                    staff,
                    "employee_id",
                    ""
                )
                or ""
            ),

            "department": (
                staff.department.name
                if staff.department
                else "ΓÇö"
            ),

            "attendance": {
                "present": present,
                "late": late,
                "absent": absent,
                "half_day": half_day,
                "overtime": float(overtime),
            },

            "tasks": {
                "total": total_tasks,
                "completed": completed_tasks,
                "pending": pending_tasks,
                "in_progress": progress_tasks,
            },

            "approved_leaves": approved_leaves,

            "payroll": float(
                staff_payroll_total
            ),
        })

    # ========================================================
    # DEPARTMENT SUMMARY
    # ========================================================

    department_summary = []

    department_ids = (
        staff_qs
        .exclude(department__isnull=True)
        .values_list(
            "department_id",
            flat=True
        )
        .distinct()
    )

    departments = Department.objects.filter(
        id__in=department_ids
    ).order_by("name")

    for department in departments:

        department_staff_ids = list(
            staff_qs
            .filter(department=department)
            .values_list(
                "id",
                flat=True
            )
        )

        department_attendance = (
            attendance_qs.filter(
                staff_id__in=department_staff_ids
            )
        )

        department_tasks = (
            task_qs.filter(
                staff_id__in=department_staff_ids
            )
        )

        department_summary.append({

            "id": department.id,

            "name": department.name,

            "staff_count": len(
                department_staff_ids
            ),

            "present": (
                department_attendance
                .filter(status="Present")
                .count()
            ),

            "late": (
                department_attendance
                .filter(status="Late")
                .count()
            ),

            "absent": (
                department_attendance
                .filter(status="Absent")
                .count()
            ),

            "completed_tasks": (
                department_tasks
                .filter(status="Completed")
                .count()
            ),

            "total_tasks": (
                department_tasks.count()
            ),
        })

    # ========================================================
    # RESPONSE
    # ========================================================

    return JsonResponse({

        "success": True,

        "filters": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },

        "staff_count": len(staff_ids),

        "attendance": {
            "present": (
                attendance_stats["present"]
                or 0
            ),
            "late": (
                attendance_stats["late"]
                or 0
            ),
            "absent": (
                attendance_stats["absent"]
                or 0
            ),
            "half_day": (
                attendance_stats["half_day"]
                or 0
            ),
            "overtime": float(
                attendance_stats["overtime"]
                or 0
            ),
        },

        "tasks": {
            "total": (
                task_stats["total"]
                or 0
            ),
            "pending": (
                task_stats["pending"]
                or 0
            ),
            "in_progress": (
                task_stats["in_progress"]
                or 0
            ),
            "completed": (
                task_stats["completed"]
                or 0
            ),
        },

        "leaves": {
            "total": (
                leave_stats["total"]
                or 0
            ),
            "pending": (
                leave_stats["pending"]
                or 0
            ),
            "approved": (
                leave_stats["approved"]
                or 0
            ),
            "rejected": (
                leave_stats["rejected"]
                or 0
            ),
        },

        "payroll": {
            "total": float(total_payroll),
            "paid": float(paid_payroll),
            "unpaid": float(unpaid_payroll),
            "paid_count": paid_count,
            "unpaid_count": unpaid_count,
        },

        "staff": staff_summary,

        "departments": department_summary,
    })



# ============================================================
# EXPORT HR REPORT CSV
# ============================================================

import csv

from django.http import HttpResponse



@require_GET
def hr_reports_export_csv(request):

    # ========================================================
    # HOTEL / LOGIN
    # ========================================================

    hotel_id = request.session.get("hotel_id")

    if not hotel_id:
        return HttpResponse(
            "Session expired. Please login again.",
            status=401,
        )

    # ========================================================
    # FILTERS
    # ========================================================

    start_date, end_date = _hr_report_dates(request)

    department_id = request.GET.get("department")
    staff_id = request.GET.get("staff")

    # ========================================================
    # STAFF
    # ========================================================

    staff_qs = (
        Staff.objects
        .filter(hotel_id=hotel_id)
        .select_related("department")
        .order_by("name")
    )

    if department_id:
        staff_qs = staff_qs.filter(
            department_id=department_id
        )

    if staff_id:
        staff_qs = staff_qs.filter(
            id=staff_id
        )

    staff_ids = list(
        staff_qs.values_list("id", flat=True)
    )

    # ========================================================
    # ATTENDANCE
    # ========================================================

    attendance_qs = (
        Attendance.objects
        .filter(
            hotel_id=hotel_id,
            staff_id__in=staff_ids,
            date__range=(
                start_date,
                end_date,
            ),
        )
    )

    # ========================================================
    # TASKS
    # ========================================================

    task_qs = (
        Task.objects
        .filter(
            staff__hotel_id=hotel_id,
            staff_id__in=staff_ids,
            created_at__date__range=(
                start_date,
                end_date,
            ),
        )
    )

    # ========================================================
# LEAVES
# ========================================================

    leave_qs = (
       LeaveRequest.objects
       .filter(
          staff__hotel_id=hotel_id,
          staff_id__in=staff_ids,

          # Leave overlaps selected report date range
          from_date__lte=end_date,
          to_date__gte=start_date,
        )
        .select_related(
        "staff",
        "staff__department",
       )
    )

    # ========================================================
    # PAYROLL
    # ========================================================

    payroll_qs = (
        Payroll.objects
        .filter(
            hotel_id=hotel_id,
            staff_id__in=staff_ids,
        )
    )

    # Payroll is month/year based.
    # Keep records whose payroll month falls inside selected range.

    payroll_ids = []

    for payroll in payroll_qs:

        try:
            payroll_date = datetime(
                int(payroll.year),
                int(payroll.month),
                1,
            ).date()
        except (TypeError, ValueError):
            continue

        start_month = start_date.replace(day=1)
        end_month = end_date.replace(day=1)

        if start_month <= payroll_date <= end_month:
            payroll_ids.append(payroll.id)

    payroll_qs = payroll_qs.filter(
        id__in=payroll_ids
    )

    # ========================================================
    # CREATE RESPONSE
    # ========================================================

    filename = (
        f"HR_Report_"
        f"{start_date.strftime('%Y-%m-%d')}_to_"
        f"{end_date.strftime('%Y-%m-%d')}.csv"
    )

    response = HttpResponse(
        content_type="text/csv; charset=utf-8"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )

    # Excel UTF-8 support
    response.write("\ufeff")

    writer = csv.writer(response)

    # ========================================================
    # REPORT INFORMATION
    # ========================================================

    writer.writerow([
        "HR REPORT"
    ])

    writer.writerow([
        "From",
        start_date.strftime("%d-%m-%Y"),
    ])

    writer.writerow([
        "To",
        end_date.strftime("%d-%m-%Y"),
    ])

    if department_id:

        department = Department.objects.filter(
            id=department_id,
            hotel_id=hotel_id,
        ).first()

        writer.writerow([
            "Department",
            department.name if department else "",
        ])

    else:

        writer.writerow([
            "Department",
            "All Departments",
        ])

    if staff_id:

        selected_staff = staff_qs.filter(
            id=staff_id
        ).first()

        writer.writerow([
            "Employee",
            selected_staff.name if selected_staff else "",
        ])

    else:

        writer.writerow([
            "Employee",
            "All Employees",
        ])

    writer.writerow([])

    # ========================================================
    # MAIN SUMMARY
    # ========================================================

    attendance_stats = attendance_qs.aggregate(

        present=Count(
            "id",
            filter=Q(status="Present"),
        ),

        late=Count(
            "id",
            filter=Q(status="Late"),
        ),

        absent=Count(
            "id",
            filter=Q(status="Absent"),
        ),

        overtime=Sum(
            "overtime_hours"
        ),
    )

    task_stats = task_qs.aggregate(

        total=Count("id"),

        completed=Count(
            "id",
            filter=Q(status="Completed"),
        ),

        in_progress=Count(
            "id",
            filter=Q(status="In Progress"),
        ),

        pending=Count(
            "id",
            filter=Q(status="Pending"),
        ),
    )

    leave_stats = leave_qs.aggregate(

        total=Count("id"),

        approved=Count(
            "id",
            filter=Q(status="Approved"),
        ),

        pending=Count(
            "id",
            filter=Q(status="Pending"),
        ),

        rejected=Count(
            "id",
            filter=Q(status="Rejected"),
        ),
    )

    payroll_stats = payroll_qs.aggregate(
        total=Sum("net_salary")
    )

    writer.writerow([
        "SUMMARY"
    ])

    writer.writerow([
        "Employees",
        staff_qs.count(),
    ])

    writer.writerow([
        "Present",
        attendance_stats["present"] or 0,
    ])

    writer.writerow([
        "Late",
        attendance_stats["late"] or 0,
    ])

    writer.writerow([
        "Absent",
        attendance_stats["absent"] or 0,
    ])

    writer.writerow([
        "Overtime Hours",
        attendance_stats["overtime"] or 0,
    ])

    writer.writerow([
        "Total Tasks",
        task_stats["total"] or 0,
    ])

    writer.writerow([
        "Completed Tasks",
        task_stats["completed"] or 0,
    ])

    writer.writerow([
        "In Progress Tasks",
        task_stats["in_progress"] or 0,
    ])

    writer.writerow([
        "Pending Tasks",
        task_stats["pending"] or 0,
    ])

    writer.writerow([
        "Leave Requests",
        leave_stats["total"] or 0,
    ])

    writer.writerow([
        "Approved Leaves",
        leave_stats["approved"] or 0,
    ])

    writer.writerow([
        "Pending Leaves",
        leave_stats["pending"] or 0,
    ])

    writer.writerow([
        "Rejected Leaves",
        leave_stats["rejected"] or 0,
    ])

    writer.writerow([
        "Total Payroll",
        payroll_stats["total"] or 0,
    ])

    writer.writerow([])
    writer.writerow([])

    # ========================================================
    # EMPLOYEE REPORT
    # ========================================================

    writer.writerow([
        "EMPLOYEE REPORT"
    ])

    writer.writerow([
        "Employee ID",
        "Employee",
        "Department",
        "Present",
        "Late",
        "Absent",
        "Overtime Hours",
        "Total Tasks",
        "Completed Tasks",
        "Approved Leaves",
        "Payroll",
    ])

    # ========================================================
    # EACH STAFF MEMBER
    # ========================================================

    for staff in staff_qs:

        # ----------------------------------------------------
        # ATTENDANCE
        # ----------------------------------------------------

        staff_attendance = attendance_qs.filter(
            staff_id=staff.id
        )

        staff_attendance_stats = (
            staff_attendance.aggregate(

                present=Count(
                    "id",
                    filter=Q(status="Present"),
                ),

                late=Count(
                    "id",
                    filter=Q(status="Late"),
                ),

                absent=Count(
                    "id",
                    filter=Q(status="Absent"),
                ),

                overtime=Sum(
                    "overtime_hours"
                ),
            )
        )

        # ----------------------------------------------------
        # TASKS
        # ----------------------------------------------------

        staff_tasks = task_qs.filter(
            staff_id=staff.id
        )

        total_tasks = staff_tasks.count()

        completed_tasks = staff_tasks.filter(
            status="Completed"
        ).count()

        # ----------------------------------------------------
        # LEAVE
        # ----------------------------------------------------

        approved_leaves = leave_qs.filter(
            staff_id=staff.id,
            status="Approved",
        ).count()

        # ----------------------------------------------------
        # PAYROLL
        # ----------------------------------------------------

        staff_payroll = (
            payroll_qs
            .filter(
                staff_id=staff.id
            )
            .aggregate(
                total=Sum("net_salary")
            )["total"]
            or 0
        )

        # ----------------------------------------------------
        # EMPLOYEE ID
        # ----------------------------------------------------

        employee_id = getattr(
            staff,
            "employee_id",
            "",
        )

        if not employee_id:
            employee_id = f"EMP{staff.id:03d}"

        # ----------------------------------------------------
        # WRITE ROW
        # ----------------------------------------------------

        writer.writerow([

            employee_id,

            staff.name,

            (
                staff.department.name
                if staff.department
                else ""
            ),

            staff_attendance_stats[
                "present"
            ] or 0,

            staff_attendance_stats[
                "late"
            ] or 0,

            staff_attendance_stats[
                "absent"
            ] or 0,

            staff_attendance_stats[
                "overtime"
            ] or 0,

            total_tasks,

            completed_tasks,

            approved_leaves,

            staff_payroll,
        ])

    # ========================================================
    # DEPARTMENT REPORT
    # ========================================================

    writer.writerow([])
    writer.writerow([])

    writer.writerow([
        "DEPARTMENT REPORT"
    ])

    writer.writerow([
        "Department",
        "Employees",
        "Present",
        "Late",
        "Absent",
        "Total Tasks",
        "Completed Tasks",
    ])

    department_ids = (
        staff_qs
        .exclude(department_id=None)
        .values_list(
            "department_id",
            flat=True,
        )
        .distinct()
    )

    departments = Department.objects.filter(
        hotel_id=hotel_id,
        id__in=department_ids,
    ).order_by("name")

    for department in departments:

        department_staff_ids = list(
            staff_qs
            .filter(
                department_id=department.id
            )
            .values_list(
                "id",
                flat=True,
            )
        )

        department_attendance = (
            attendance_qs
            .filter(
                staff_id__in=department_staff_ids
            )
            .aggregate(

                present=Count(
                    "id",
                    filter=Q(status="Present"),
                ),

                late=Count(
                    "id",
                    filter=Q(status="Late"),
                ),

                absent=Count(
                    "id",
                    filter=Q(status="Absent"),
                ),
            )
        )

        department_tasks = (
            task_qs
            .filter(
                staff_id__in=department_staff_ids
            )
        )

        writer.writerow([

            department.name,

            len(department_staff_ids),

            department_attendance[
                "present"
            ] or 0,

            department_attendance[
                "late"
            ] or 0,

            department_attendance[
                "absent"
            ] or 0,

            department_tasks.count(),

            department_tasks.filter(
                status="Completed"
            ).count(),
        ])

    return response




# ============================================================
# PROFILE PAGE
# ============================================================

def hr_profile_page(request):

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    return render(
        request,
        "hr/profile.html",
        context
    )







# ============================================================
# HR - UPDATE EMPLOYEE
# ============================================================

from django.db import transaction
from django_tenants.utils import schema_context
from django.views.decorators.http import require_POST



@require_POST
def hr_update_employee(request):
    try:

        # ====================================================
        # HOTEL
        # ====================================================

        hotel_id = request.session.get("hotel_id")

        if not hotel_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Session expired. Please login again."
                },
                status=401
            )

        with schema_context("public"):
            try:
                hotel = Hotel.objects.get(id=hotel_id)

            except Hotel.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Hotel not found."
                    },
                    status=404
                )

        tenant_schema = hotel.schema_name


        # ====================================================
        # STAFF ID
        # ====================================================

        staff_id = request.POST.get("staff_id")

        if not staff_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Employee ID is required."
                },
                status=400
            )


        # ====================================================
        # FIELD HELPER
        # ====================================================

        def get_field(key):

            value = request.POST.get(key, "")

            if hasattr(value, "strip"):
                value = value.strip()

            return value if value != "" else None


        # ====================================================
        # FORM VALUES
        # ====================================================

        name = get_field("name")
        email = get_field("email")
        phone = get_field("phone")

        nickname = get_field("nickname")
        dob = get_field("dob")
        gender = get_field("gender")
        address = get_field("address")

        employee_id = get_field("employee_id")

        department_id = (
            get_field("department_id")
            or get_field("department")
        )

        role = get_field("role")

        employment_type = get_field(
            "employment_type"
        )

        joining_date = get_field(
            "joining_date"
        )

        salary = get_field("salary")

        emergency_contact_name = get_field(
            "emergency_contact_name"
        )

        emergency_contact_phone = get_field(
            "emergency_contact_phone"
        )

        bank_account = get_field(
            "bank_account"
        )

        ifsc = get_field("ifsc")

        pf_number = get_field(
            "pf_number"
        )

        esi_number = get_field(
            "esi_number"
        )

        id_proof_type = get_field(
            "id_proof_type"
        )

        id_proof_number = get_field(
            "id_proof_number"
        )

        notes = get_field("notes")

        photo = request.FILES.get(
            "photo"
        )

        id_proof_image = request.FILES.get(
            "id_proof_image"
        )


        # ====================================================
        # VALIDATION
        # ====================================================

        if not name:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Employee name is required."
                },
                status=400
            )


        # ====================================================
        # TENANT SCHEMA
        # ====================================================

        with schema_context(tenant_schema):

            with transaction.atomic():

                # ============================================
                # IMPORTANT:
                # DO NOT select_related() here.
                #
                # select_for_update + nullable relationship
                # causes PostgreSQL:
                #
                # FOR UPDATE cannot be applied to the
                # nullable side of an outer join
                # ============================================

                try:

                    staff = (
                        Staff.objects
                        .select_for_update()
                        .get(
                            id=staff_id,
                            hotel=hotel
                        )
                    )

                except Staff.DoesNotExist:

                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Employee not found."
                        },
                        status=404
                    )


                # ============================================
                # DEPARTMENT
                # ============================================

                department = None

                if department_id:

                    try:

                        department = (
                            Department.objects
                            .get(
                                id=int(
                                    department_id
                                )
                            )
                        )

                    except (
                        Department.DoesNotExist,
                        ValueError,
                        TypeError
                    ):

                        return JsonResponse(
                            {
                                "success": False,
                                "error": "Department not found."
                            },
                            status=400
                        )


                # ============================================
                # DUPLICATE EMPLOYEE ID
                # ============================================

                if employee_id:

                    duplicate = (
                        Staff.objects
                        .filter(
                            hotel=hotel,
                            employee_id=employee_id
                        )
                        .exclude(
                            id=staff.id
                        )
                        .exists()
                    )

                    if duplicate:

                        return JsonResponse(
                            {
                                "success": False,
                                "error":
                                    f"Employee ID "
                                    f"'{employee_id}' "
                                    f"is already in use."
                            },
                            status=400
                        )


                # ============================================
                # UPDATE LOGIN USER
                # ============================================

                if staff.user and email:

                    unique_username = (
                        f"{email}_{hotel.id}"
                    )

                    duplicate_user = (
                        User.objects
                        .filter(
                            username=unique_username
                        )
                        .exclude(
                            id=staff.user_id
                        )
                        .exists()
                    )

                    if duplicate_user:

                        return JsonResponse(
                            {
                                "success": False,
                                "error":
                                    "Another employee already "
                                    "uses this email."
                            },
                            status=400
                        )


                    staff.user.email = email

                    staff.user.username = (
                        unique_username
                    )

                    staff.user.save(
                        update_fields=[
                            "email",
                            "username"
                        ]
                    )


                # ============================================
                # UPDATE STAFF
                # ============================================

                staff.name = name
                staff.phone = phone

                staff.nickname = nickname

                staff.dob = (
                    dob or None
                )

                staff.gender = gender

                staff.address = address

                staff.department = department

                if employee_id:
                    staff.employee_id = (
                        employee_id
                    )

                staff.role = role

                staff.employment_type = (
                    employment_type
                )

                staff.joining_date = (
                    joining_date or None
                )

                staff.salary = (
                    salary or 0
                )

                staff.emergency_contact_name = (
                    emergency_contact_name
                )

                staff.emergency_contact_phone = (
                    emergency_contact_phone
                )

                staff.bank_account = (
                    bank_account
                )

                staff.ifsc = ifsc

                staff.pf_number = (
                    pf_number
                )

                staff.esi_number = (
                    esi_number
                )

                staff.id_proof_type = (
                    id_proof_type
                )

                staff.id_proof_number = (
                    id_proof_number
                )

                staff.notes = notes


                # ============================================
                # FILES
                # ============================================

                if photo:
                    staff.photo = photo

                if id_proof_image:
                    staff.id_proof_image = (
                        id_proof_image
                    )


                # ============================================
                # SAVE
                # ============================================

                staff.save()


        return JsonResponse(
            {
                "success": True,
                "message":
                    "Employee updated successfully."
            }
        )


    except Exception as e:

        print(
            "HR UPDATE EMPLOYEE ERROR:",
            str(e)
        )

        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status=500
        )



# ============================================================
# HR - DELETE EMPLOYEE
# ============================================================

@require_POST
def hr_delete_employee(request):
    try:

        hotel_id = request.session.get(
            "hotel_id"
        )

        if not hotel_id:

            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Session expired. Please login again."
                },
                status=401
            )


        with schema_context("public"):

            try:

                hotel = Hotel.objects.get(
                    id=hotel_id
                )

            except Hotel.DoesNotExist:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Hotel not found."
                    },
                    status=404
                )


        staff_id = request.POST.get(
            "staff_id"
        )

        if not staff_id:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Employee ID is required."
                },
                status=400
            )


        with schema_context(
            hotel.schema_name
        ):

            with transaction.atomic():

                try:

                    # IMPORTANT:
                    # No select_related() here.

                    staff = (
                        Staff.objects
                        .select_for_update()
                        .get(
                            id=staff_id,
                            hotel=hotel
                        )
                    )

                except Staff.DoesNotExist:

                    return JsonResponse(
                        {
                            "success": False,
                            "error":
                                "Employee not found."
                        },
                        status=404
                    )


                employee_name = (
                    staff.name
                )


                # Get user before deleting Staff

                user = staff.user


                # Delete employee

                staff.delete()


                # Delete login account

                if user:
                    user.delete()


        return JsonResponse(
            {
                "success": True,
                "message":
                    f"{employee_name} "
                    f"deleted successfully."
            }
        )


    except Exception as e:

        print(
            "HR DELETE EMPLOYEE ERROR:",
            str(e)
        )

        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status=500
        )





# ============================================================
# HR - ADD DEPARTMENT
# ============================================================

@require_POST
def hr_add_department(request):
    try:

        hotel_id = request.session.get("hotel_id")

        if not hotel_id:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Session expired. Please login again."
                },
                status=401
            )


        with schema_context("public"):

            try:
                hotel = Hotel.objects.get(
                    id=hotel_id
                )

            except Hotel.DoesNotExist:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Hotel not found."
                    },
                    status=404
                )


        name = request.POST.get(
            "name",
            ""
        ).strip()


        if not name:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Department name is required."
                },
                status=400
            )


        with schema_context(
            hotel.schema_name
        ):

            # Prevent duplicate names

            if Department.objects.filter(
                hotel=hotel,
                name__iexact=name
            ).exists():

                return JsonResponse(
                    {
                        "success": False,
                        "error":
                            "A department with this name "
                            "already exists."
                    },
                    status=400
                )


            department = Department.objects.create(
                hotel=hotel,
                name=name
            )


        return JsonResponse(
            {
                "success": True,

                "message":
                    "Department added successfully.",

                "department": {
                    "id": department.id,
                    "name": department.name
                }
            }
        )


    except Exception as e:

        print(
            "HR ADD DEPARTMENT ERROR:",
            str(e)
        )

        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status=500
        )


# ============================================================
# HR - UPDATE DEPARTMENT
# ============================================================

@require_POST
def hr_update_department(request):
    try:

        hotel_id = request.session.get(
            "hotel_id"
        )

        if not hotel_id:

            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Session expired. Please login again."
                },
                status=401
            )


        with schema_context("public"):

            try:

                hotel = Hotel.objects.get(
                    id=hotel_id
                )

            except Hotel.DoesNotExist:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Hotel not found."
                    },
                    status=404
                )


        department_id = request.POST.get(
            "department_id"
        )

        name = request.POST.get(
            "name",
            ""
        ).strip()


        if not department_id:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Department ID is required."
                },
                status=400
            )


        if not name:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Department name is required."
                },
                status=400
            )


        with schema_context(
            hotel.schema_name
        ):

            try:

                department = Department.objects.get(
                    id=department_id,
                    hotel=hotel
                )

            except Department.DoesNotExist:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Department not found."
                    },
                    status=404
                )


            duplicate = (
                Department.objects
                .filter(
                    hotel=hotel,
                    name__iexact=name
                )
                .exclude(
                    id=department.id
                )
                .exists()
            )


            if duplicate:

                return JsonResponse(
                    {
                        "success": False,
                        "error":
                            "A department with this name "
                            "already exists."
                    },
                    status=400
                )


            department.name = name

            department.save(
                update_fields=[
                    "name"
                ]
            )


        return JsonResponse(
            {
                "success": True,

                "message":
                    "Department updated successfully.",

                "department": {
                    "id": department.id,
                    "name": department.name
                }
            }
        )


    except Exception as e:

        print(
            "HR UPDATE DEPARTMENT ERROR:",
            str(e)
        )

        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status=500
        )


# ============================================================
# HR - DELETE DEPARTMENT
# ============================================================

@require_POST
def hr_delete_department(request):
    try:

        hotel_id = request.session.get(
            "hotel_id"
        )

        if not hotel_id:

            return JsonResponse(
                {
                    "success": False,
                    "error":
                        "Session expired. Please login again."
                },
                status=401
            )


        with schema_context("public"):

            try:

                hotel = Hotel.objects.get(
                    id=hotel_id
                )

            except Hotel.DoesNotExist:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Hotel not found."
                    },
                    status=404
                )


        department_id = request.POST.get(
            "department_id"
        )


        if not department_id:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Department ID is required."
                },
                status=400
            )


        with schema_context(
            hotel.schema_name
        ):

            try:

                department = Department.objects.get(
                    id=department_id,
                    hotel=hotel
                )

            except Department.DoesNotExist:

                return JsonResponse(
                    {
                        "success": False,
                        "error": "Department not found."
                    },
                    status=404
                )


            # ------------------------------------------------
            # SAFETY:
            # Do not delete a department that still has staff.
            # ------------------------------------------------

            staff_count = Staff.objects.filter(
                hotel=hotel,
                department=department
            ).count()


            if staff_count > 0:

                return JsonResponse(
                    {
                        "success": False,

                        "error":
                            f"This department has "
                            f"{staff_count} employee(s). "
                            f"Move those employees to another "
                            f"department before deleting it."
                    },
                    status=400
                )


            department_name = department.name

            department.delete()


        return JsonResponse(
            {
                "success": True,

                "message":
                    f"{department_name} deleted successfully."
            }
        )


    except Exception as e:

        print(
            "HR DELETE DEPARTMENT ERROR:",
            str(e)
        )

        return JsonResponse(
            {
                "success": False,
                "error": str(e)
            },
            status=500
        )




@never_cache
@staff_login_required
def hr_shifts_page(request):

    context = _get_hr_page_context(request)

    if context is None:
        return redirect("staff_login")

    hotel = context.get("hotel")

    if hotel:
        employees = (
            Staff.objects
            .filter(hotel=hotel)
            .select_related(
                "department",
                "user"
            )
            .order_by("name")
        )

        departments = (
            Department.objects
            .filter(hotel=hotel)
            .order_by("name")
        )
    else:
        employees = Staff.objects.none()
        departments = Department.objects.none()

    context.update({
        "employees": employees,
        "departments": departments,
        "active_hr_page": "shifts",
    })

    return render(
        request,
        "hr/shifts.html",
        context
    )
    """
    HR Shift Management page.
    Actual shift data is loaded through the existing APIs.
    """

    return render(
        request,
        "hr/shifts.html",
        {
            "active_hr_page": "shifts",
        },
    )






# ============================================================
# HOUSEKEEPING MODULE
# ============================================================

from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Q, Sum
from accounts.decorators import staff_login_required


HOUSEKEEPING_KEYWORDS = (
    "housekeeping",
    "hk",
    "cleaning",
    "laundry",
)


def _get_housekeeping_staff(request):
    """
    Return currently logged-in housekeeping staff.

    Returns None if:
    - no staff session exists
    - staff does not exist
    - employee is not part of housekeeping
    """

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return None

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
                "user",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return None

    department_name = (
        staff.department.name.lower()
        if staff.department
        else ""
    )

    role = str(
        getattr(staff, "role", "") or ""
    ).lower()

    combined = f"{department_name} {role}"

    if not any(
        keyword in combined
        for keyword in HOUSEKEEPING_KEYWORDS
    ):
        return None

    return staff






def _housekeeping_common_context(staff):

    # ========================================================
    # DATE
    # ========================================================

    today = date.today()


    # ========================================================
    # STAFF TASKS
    # ========================================================

    my_tasks = (
        Task.objects
        .filter(staff=staff)
        .select_related(
            "room",
            "room_unit",
            "room_unit__room",
        )
        .order_by("-created_at")
    )


    # ========================================================
    # ROOM UNITS
    # ========================================================

    all_units = (
        RoomUnit.objects
        .select_related("room")
        .all()
        .order_by("room_number")
    )


    # ========================================================
    # TASK COUNTS
    # ========================================================

    pending_tasks_qs = my_tasks.filter(
        status__iexact="Pending"
    )

    in_progress_tasks_qs = my_tasks.filter(
        status__iexact="In Progress"
    )

    completed_tasks_qs = my_tasks.filter(
        status__iexact="Completed"
    )


    # ========================================================
    # ROOM COUNTS
    # ========================================================

    clean_rooms = all_units.filter(
        status__iexact="Available"
    ).count()

    dirty_rooms = all_units.filter(
        status__iexact="Dirty"
    ).count()

    cleaning_rooms = all_units.filter(
        status__iexact="Cleaning"
    ).count()

    maintenance_rooms = all_units.filter(
        status__iexact="Maintenance"
    ).count()


    # ========================================================
    # RETURN COMMON CONTEXT
    # ========================================================

    return {

        "staff": staff,

        "hotel": staff.hotel,

        "today": today,

        # Rooms
        "total_rooms": all_units.count(),

        "clean_rooms": clean_rooms,

        "dirty_rooms": dirty_rooms,

        "cleaning_rooms": cleaning_rooms,

        "maintenance_rooms": maintenance_rooms,

        # Tasks
        "total_tasks": my_tasks.count(),

        "pending_tasks": pending_tasks_qs.count(),

        "in_progress_tasks": (
            in_progress_tasks_qs.count()
        ),

        "completed_tasks": (
            completed_tasks_qs.count()
        ),

        "recent_tasks": my_tasks[:6],

    }




@never_cache
@staff_login_required
def housekeeping_rooms_page(request):

    # =========================================================
    # CURRENT HOUSEKEEPING STAFF
    # =========================================================

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")


    context = _housekeeping_common_context(staff)


    # =========================================================
    # ROOM UNITS
    # =========================================================
    #
    # If each hotel uses a separate tenant schema, this is fine.
    # We deliberately work with RoomUnit because cleaning happens
    # against a physical room number, not the Room type.
    # =========================================================

    units = (
        RoomUnit.objects
        .select_related("room")
        .all()
        .order_by("room_number")
    )


    # =========================================================
    # ACTIVE TASKS BELONGING TO CURRENT HOUSEKEEPING STAFF
    # =========================================================

    active_tasks = (
        Task.objects
        .filter(
            staff=staff,
            room_unit__isnull=False,
        )
        .exclude(
            status__iexact="Completed"
        )
        .select_related(
            "room",
            "room_unit",
        )
        .order_by("-created_at")
    )


    # =========================================================
    # MAP LATEST ACTIVE TASK TO EACH ROOM
    # =========================================================

    task_map = {}

    for task in active_tasks:

        if not task.room_unit_id:
            continue

        # Because queryset is ordered newest first,
        # first task found is the newest active task.
        if task.room_unit_id not in task_map:
            task_map[task.room_unit_id] = task


    # =========================================================
    # BUILD TEMPLATE DATA
    # =========================================================

    rooms = []

    room_types = set()

    for unit in units:

        task = task_map.get(unit.id)

        room_type = (
            unit.room.room_type
            if unit.room
            else "Standard"
        )

        room_types.add(room_type)

        raw_status = (
            unit.status or "Unknown"
        ).strip()

        normalized_status = (
            raw_status.lower()
        )


        # -----------------------------------------------------
        # NORMALIZE STATUS
        # -----------------------------------------------------

        if normalized_status == "clean":
            normalized_status = "available"
            raw_status = "Available"

        elif normalized_status == "ready":
            normalized_status = "available"
            raw_status = "Available"

        elif normalized_status == "in progress":
            normalized_status = "cleaning"
            raw_status = "Cleaning"


        rooms.append({

            "id": unit.id,

            "number": unit.room_number,

            "room_type": room_type,

            "status": normalized_status,

            "status_display": raw_status,

            "task_id": (
                task.id
                if task
                else None
            ),

            "task_title": (
                task.title
                if task
                else ""
            ),

            "task_status": (
                task.status
                if task
                else ""
            ),

            "has_active_task": bool(task),

        })


    # =========================================================
    # PAGE COUNTS
    # =========================================================

    total_rooms = len(rooms)

    clean_rooms = sum(
        1
        for room in rooms
        if room["status"] == "available"
    )

    dirty_rooms = sum(
        1
        for room in rooms
        if room["status"] == "dirty"
    )

    cleaning_rooms = sum(
        1
        for room in rooms
        if room["status"] == "cleaning"
    )

    maintenance_rooms = sum(
        1
        for room in rooms
        if room["status"] == "maintenance"
    )

    occupied_rooms = sum(
        1
        for room in rooms
        if room["status"] == "occupied"
    )


    # =========================================================
    # UPDATE CONTEXT
    # =========================================================

    context.update({

        "rooms": rooms,

        "room_types": sorted(room_types),

        "total_rooms": total_rooms,

        "clean_rooms": clean_rooms,

        "dirty_rooms": dirty_rooms,

        "cleaning_rooms": cleaning_rooms,

        "maintenance_rooms": maintenance_rooms,

        "occupied_rooms": occupied_rooms,

    })


    return render(
        request,
        "housekeeping/rooms.html",
        context,
    )




@never_cache
@staff_login_required
def housekeeping_tasks_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    tasks = (
        Task.objects
        .filter(staff=staff)
        .select_related(
            "room",
            "room_unit",
            "room_unit__room",
        )
        .order_by("-created_at")
    )

    context.update({

        "tasks": tasks,

        "total_tasks": tasks.count(),

        "pending_count": tasks.filter(
            status__iexact="Pending"
        ).count(),

        "progress_count": tasks.filter(
            status__iexact="In Progress"
        ).count(),

        "completed_count": tasks.filter(
            status__iexact="Completed"
        ).count(),

    })

    return render(
        request,
        "housekeeping/tasks.html",
        context,
    )





from django.db.models import Q
from django.shortcuts import render, redirect
from accounts.decorators import staff_login_required


from django.db.models import Sum, F, Q
from django.shortcuts import render, redirect

from accounts.decorators import staff_login_required

from django.db.models import Sum, F
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache

from accounts.decorators import staff_login_required


from django.db.models import Sum, F
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache

from accounts.decorators import staff_login_required



@never_cache
@staff_login_required
def housekeeping_stock_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    inventory_items = (
        HotelInventoryItem.objects
        .select_related(
            "category",
            "department",
            "vendor",
        )
        .all()
        .order_by(
            "category__name",
            "name",
        )
    )

    total_items = inventory_items.count()

    total_quantity = (
        inventory_items.aggregate(
            total=Sum("current_stock")
        )["total"]
        or 0
    )

    low_stock_count = (
        inventory_items
        .filter(
            current_stock__gt=0,
            current_stock__lte=F("minimum_stock"),
        )
        .count()
    )

    out_of_stock_count = (
        inventory_items
        .filter(
            current_stock__lte=0
        )
        .count()
    )

    in_stock_count = (
        inventory_items
        .filter(
            current_stock__gt=F("minimum_stock")
        )
        .count()
    )

    categories = (
        inventory_items
        .exclude(category__isnull=True)
        .values_list(
            "category__name",
            flat=True,
        )
        .distinct()
        .order_by("category__name")
    )

    context.update({
        "inventory_items": inventory_items,
        "categories": categories,

        "total_inventory_items": total_items,
        "total_inventory_quantity": total_quantity,

        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "in_stock_count": in_stock_count,
    })

    return render(
        request,
        "housekeeping/stock.html",
        context,
    )


@staff_login_required
def housekeeping_laundry_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    return render(
        request,
        "housekeeping/laundry.html",
        context,
    )


@staff_login_required
def housekeeping_linen_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    return render(
        request,
        "housekeeping/linen.html",
        context,
    )


@staff_login_required
def housekeeping_maintenance_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    context["departments"] = (
        Department.objects
        .filter(hotel=staff.hotel)
        .order_by("name")
    )

    return render(
        request,
        "housekeeping/maintenance.html",
        context,
    )






@staff_login_required
def housekeeping_linen_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    return render(
        request,
        "housekeeping/linen.html",
        context,
    )


@staff_login_required
def housekeeping_maintenance_page(request):

    staff = _get_housekeeping_staff(request)

    if not staff:
        return redirect("staff_login")

    context = _housekeeping_common_context(staff)

    context["departments"] = (
        Department.objects
        .filter(hotel=staff.hotel)
        .order_by("name")
    )

    return render(
        request,
        "housekeeping/maintenance.html",
        context,
    )





from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache

from accounts.models import Staff, Department


@never_cache
def housekeeping_maintenance_page(request):
    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        request.session.flush()
        return redirect("staff_login")

    hotel = staff.hotel

    departments = (
        Department.objects
        .filter(hotel=hotel)
        .order_by("name")
    )

    context = {
        "staff": staff,
        "hotel": hotel,
        "departments": departments,
    }

    return render(
        request,
        "housekeeping/maintenance.html",
        context,
    )



# ============================================================
# ACCOUNTANT - PROFILE
# ============================================================

from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache

from accounts.decorators import staff_login_required
from accounts.models import Staff


@never_cache
@staff_login_required
def accountant_profile(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "department",
                "hotel",
                "user",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        request.session.flush()
        return redirect("staff_login")

    hotel = staff.hotel

    context = {
        "staff": staff,
        "hotel": hotel,
    }

    return render(
        request,
        "accountant/profile.html",
        context,
    )



from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.decorators import staff_login_required
from accounts.models import Staff


@staff_login_required
@login_required
def accountant_payroll(request):

    # ============================================================
    # LOGGED-IN ACCOUNTANT
    # ============================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "department",
                "hotel",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        request.session.flush()
        return redirect("staff_login")


    # ============================================================
    # ACCOUNTANT ACCESS
    # ============================================================

    department_name = (
        staff.department.name.lower()
        if staff.department
        else ""
    )

    role = (
        getattr(staff, "role", "") or ""
    ).lower()

    combined = f"{department_name} {role}"

    ACCOUNTANT_KEYWORDS = [
        "accountant",
        "account",
        "accounts",
        "finance",
        "billing",
        "manager",
        "owner",
        "admin",
    ]

    if not any(
        keyword in combined
        for keyword in ACCOUNTANT_KEYWORDS
    ):
        return redirect("staff_login")


    # ============================================================
    # CURRENT DATE
    # ============================================================

    now = timezone.now()

    if timezone.is_aware(now):
        today = timezone.localtime(now).date()
    else:
        today = now.date()


    # ============================================================
    # FILTERS
    # ============================================================

    selected_month = request.GET.get(
        "month",
        str(today.month),
    )

    selected_year = request.GET.get(
        "year",
        str(today.year),
    )

    search = (
        request.GET.get(
            "search",
            "",
        )
        or ""
    ).strip()

    status_filter = (
        request.GET.get(
            "status",
            "",
        )
        or ""
    ).strip().lower()


    # ============================================================
    # VALIDATE MONTH
    # ============================================================

    try:
        selected_month = int(selected_month)

    except (TypeError, ValueError):
        selected_month = today.month


    if selected_month < 1 or selected_month > 12:
        selected_month = today.month


    # ============================================================
    # VALIDATE YEAR
    # ============================================================

    try:
        selected_year = int(selected_year)

    except (TypeError, ValueError):
        selected_year = today.year


    # ============================================================
    # PAYROLL QUERY
    # ============================================================

    payrolls = (
        Payroll.objects
        .select_related(
            "staff",
            "staff__department",
        )
        .filter(
            month=selected_month,
            year=selected_year,
        )
        .order_by(
            "staff__name"
        )
    )


    # ============================================================
    # SEARCH
    # ============================================================

    if search:

        payrolls = payrolls.filter(

            Q(
                staff__name__icontains=search
            )

            |

            Q(
                staff__employee_id__icontains=search
            )

        )


    # ============================================================
    # STATUS FILTER
    #
    # Your Payroll model uses paid_status=True / False.
    # ============================================================

    if status_filter == "paid":

        payrolls = payrolls.filter(
            paid_status=True
        )

    elif status_filter in [
        "pending",
        "unpaid",
    ]:

        payrolls = payrolls.filter(
            paid_status=False
        )


    # ============================================================
    # SUMMARY
    # ============================================================

    total_payroll = (
        payrolls.aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )


    paid_payroll = (
        payrolls
        .filter(
            paid_status=True
        )
        .aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )


    pending_payroll = (
        payrolls
        .filter(
            paid_status=False
        )
        .aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )


    paid_count = (
        payrolls
        .filter(
            paid_status=True
        )
        .count()
    )


    pending_count = (
        payrolls
        .filter(
            paid_status=False
        )
        .count()
    )


    total_count = payrolls.count()


    # ============================================================
    # YEAR DROPDOWN
    # ============================================================

    years = list(
        range(
            today.year - 5,
            today.year + 2,
        )
    )


    # ============================================================
    # MONTH DROPDOWN
    # ============================================================

    months = [

        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),

        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),

    ]

    # ============================================================
# STAFF LIST FOR GENERATE PAYROLL MODAL
# ============================================================

    staff_list = (
          Staff.objects
        .filter(hotel=staff.hotel)
        .select_related(
        "department",
        "user",
        )
        .order_by("name")
    )


    # ============================================================
    # CONTEXT
    # ============================================================

    context = {

        "staff":
            staff,

        "hotel":
            staff.hotel,

        "payrolls":
            payrolls,

        "selected_month":
            selected_month,

        "selected_year":
            selected_year,
        "staff_list": staff_list,    

        "search":
            search,

        "status":
            status_filter,

        "total_payroll":
            total_payroll,

        "paid_payroll":
            paid_payroll,

        "pending_payroll":
            pending_payroll,

        "paid_count":
            paid_count,

        "pending_count":
            pending_count,

        "total_count":
            total_count,

        "years":
            years,

        "months":
            months,

        "today":
            today,

    }


    # ============================================================
    # RENDER
    # ============================================================

    return render(
        request,
        "accountant/payroll.html",
        context,
    )



@staff_login_required
@login_required
@require_POST
def accountant_send_dashboard_email(request):
    """
    Send accountant dashboard / financial summary by email.
    """

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return JsonResponse(
            {
                "success": False,
                "message": "Your session has expired. Please login again."
            },
            status=401,
        )

    try:
        staff = Staff.objects.select_related(
            "department",
            "hotel",
        ).get(id=staff_id)

    except Staff.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "Staff account was not found."
            },
            status=404,
        )

    # ============================================================
    # ACCOUNTANT ACCESS CHECK
    # ============================================================

    ACCOUNTANT_KEYWORDS = [
        "accountant",
        "account",
        "finance",
        "billing",
        "manager",
        "owner",
        "admin",
        "hotel",
    ]

    department_name = (
        staff.department.name.lower()
        if staff.department
        else ""
    )

    role = (
        getattr(staff, "role", "") or ""
    ).lower()

    combined = f"{department_name} {role}"

    if not any(
        keyword in combined
        for keyword in ACCOUNTANT_KEYWORDS
    ):
        return JsonResponse(
            {
                "success": False,
                "message": "You do not have permission to send financial reports."
            },
            status=403,
        )

    # ============================================================
    # READ JSON
    # ============================================================

    try:
        data = json.loads(
            request.body.decode("utf-8")
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request data."
            },
            status=400,
        )

    recipient = (
        data.get("recipient") or ""
    ).strip()

    subject = (
        data.get("subject") or ""
    ).strip()

    message = (
        data.get("message") or ""
    ).strip()

    include_summary = bool(
        data.get("include_summary", True)
    )

    # ============================================================
    # VALIDATION
    # ============================================================

    if not recipient:
        return JsonResponse(
            {
                "success": False,
                "message": "Recipient email address is required."
            },
            status=400,
        )

    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    try:
        validate_email(recipient)

    except ValidationError:
        return JsonResponse(
            {
                "success": False,
                "message": "Please enter a valid recipient email address."
            },
            status=400,
        )

    if not subject:
        subject = "Financial Dashboard Report"

    if len(subject) > 200:
        return JsonResponse(
            {
                "success": False,
                "message": "Email subject is too long."
            },
            status=400,
        )

    # ============================================================
    # DASHBOARD VALUES FROM FRONTEND
    # ============================================================

    summary = data.get("summary") or {}

    today_revenue = summary.get(
        "today_revenue",
        "Γé╣0.00"
    )

    month_revenue = summary.get(
        "month_revenue",
        "Γé╣0.00"
    )

    outstanding = summary.get(
        "outstanding",
        "Γé╣0.00"
    )

    tax_collected = summary.get(
        "tax_collected",
        "Γé╣0.00"
    )

    room_revenue = summary.get(
        "room_revenue",
        "Γé╣0.00"
    )

    restaurant_revenue = summary.get(
        "restaurant_revenue",
        "Γé╣0.00"
    )

    other_revenue = summary.get(
        "other_revenue",
        "Γé╣0.00"
    )

    total_expenses = summary.get(
        "total_expenses",
        "Γé╣0.00"
    )

    net_position = summary.get(
        "net_position",
        "Γé╣0.00"
    )

    period_label = (
        summary.get("period_label")
        or "Current Period"
    )

    # ============================================================
    # HOTEL DETAILS
    # ============================================================

    hotel = getattr(
        staff,
        "hotel",
        None
    )

    hotel_name = (
        getattr(hotel, "name", None)
        or getattr(hotel, "hotel_name", None)
        or "Hotel ERP"
    )

    accountant_name = (
        getattr(staff, "name", None)
        or request.user.get_full_name()
        or request.user.username
        or "Accountant"
    )

    # ============================================================
    # PLAIN TEXT EMAIL
    # ============================================================

    text_body = f"""
{hotel_name}
Financial Dashboard Report

Prepared by: {accountant_name}
Period: {period_label}

{message}
"""

    if include_summary:

        text_body += f"""

FINANCIAL SUMMARY
------------------------------

Today's Revenue: {today_revenue}
This Month Revenue: {month_revenue}
Outstanding: {outstanding}
Tax Collected: {tax_collected}

Room Revenue: {room_revenue}
Restaurant Revenue: {restaurant_revenue}
Other Revenue: {other_revenue}

Total Expenses: {total_expenses}
Net Position: {net_position}

------------------------------
Generated from Hotel ERP
"""

    # ============================================================
    # HTML SUMMARY
    # ============================================================

    from django.utils.html import escape

    safe_message = escape(message).replace(
        "\n",
        "<br>"
    )

    summary_html = ""

    if include_summary:

        summary_html = f"""
        <div style="
            margin-top:24px;
            border:1px solid #e5e7eb;
            border-radius:12px;
            overflow:hidden;
        ">

            <div style="
                padding:16px 20px;
                background:#f8fafc;
                border-bottom:1px solid #e5e7eb;
            ">
                <strong style="
                    color:#111827;
                    font-size:16px;
                ">
                    Financial Summary
                </strong>

                <div style="
                    color:#64748b;
                    font-size:12px;
                    margin-top:4px;
                ">
                    {escape(str(period_label))}
                </div>
            </div>

            <table
                width="100%"
                cellpadding="0"
                cellspacing="0"
                style="
                    border-collapse:collapse;
                    font-family:Arial,sans-serif;
                "
            >

                <tr>
                    <td style="{_email_label_style()}">
                        Today's Revenue
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(today_revenue))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        This Month Revenue
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(month_revenue))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        Outstanding
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(outstanding))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        Tax Collected
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(tax_collected))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        Room Revenue
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(room_revenue))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        Restaurant Revenue
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(restaurant_revenue))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        Other Revenue
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(other_revenue))}
                    </td>
                </tr>

                <tr>
                    <td style="{_email_label_style()}">
                        Total Expenses
                    </td>

                    <td style="{_email_value_style()}">
                        {escape(str(total_expenses))}
                    </td>
                </tr>

                <tr>
                    <td style="
                        padding:14px 20px;
                        color:#111827;
                        font-size:14px;
                        font-weight:700;
                        border-top:2px solid #e5e7eb;
                    ">
                        Net Position
                    </td>

                    <td style="
                        padding:14px 20px;
                        color:#7c3aed;
                        font-size:15px;
                        font-weight:700;
                        text-align:right;
                        border-top:2px solid #e5e7eb;
                    ">
                        {escape(str(net_position))}
                    </td>
                </tr>

            </table>

        </div>
        """

    html_body = f"""
    <!DOCTYPE html>

    <html>
    <body style="
        margin:0;
        padding:0;
        background:#f4f6f8;
        font-family:Arial,sans-serif;
    ">

        <div style="
            max-width:680px;
            margin:30px auto;
            padding:0 15px;
        ">

            <div style="
                background:#ffffff;
                border-radius:16px;
                overflow:hidden;
                box-shadow:0 5px 20px rgba(15,23,42,.08);
            ">

                <div style="
                    padding:25px 28px;
                    background:linear-gradient(
                        135deg,
                        #7c3aed,
                        #4c1d95
                    );
                    color:#ffffff;
                ">

                    <div style="
                        font-size:12px;
                        opacity:.8;
                        margin-bottom:6px;
                    ">
                        {escape(str(hotel_name))}
                    </div>

                    <div style="
                        font-size:24px;
                        font-weight:700;
                    ">
                        Financial Dashboard Report
                    </div>

                </div>

                <div style="
                    padding:28px;
                ">

                    <div style="
                        color:#64748b;
                        font-size:13px;
                        margin-bottom:20px;
                    ">
                        Prepared by
                        <strong style="color:#111827;">
                            {escape(str(accountant_name))}
                        </strong>
                    </div>

                    {
                        f'''
                        <div style="
                            color:#334155;
                            font-size:14px;
                            line-height:1.7;
                            margin-bottom:20px;
                        ">
                            {safe_message}
                        </div>
                        '''
                        if safe_message
                        else ""
                    }

                    {summary_html}

                </div>

                <div style="
                    padding:17px 28px;
                    background:#f8fafc;
                    color:#94a3b8;
                    font-size:11px;
                    text-align:center;
                    border-top:1px solid #e5e7eb;
                ">
                    This report was generated from Hotel ERP.
                </div>

            </div>

        </div>

    </body>
    </html>
    """

    # ============================================================
    # SEND EMAIL
    # ============================================================

    try:

        from_email = getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            None,
        )

        if not from_email:
            from_email = getattr(
                settings,
                "EMAIL_HOST_USER",
                None,
            )

        if not from_email:
            return JsonResponse(
                {
                    "success": False,
                    "message": (
                        "Email sender is not configured. "
                        "Set DEFAULT_FROM_EMAIL or EMAIL_HOST_USER."
                    ),
                },
                status=500,
            )

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=from_email,
            to=[recipient],
        )

        email.attach_alternative(
            html_body,
            "text/html",
        )

        sent_count = email.send(
            fail_silently=False
        )

        if sent_count != 1:
            raise RuntimeError(
                "Email backend did not confirm delivery."
            )

        return JsonResponse(
            {
                "success": True,
                "message": f"Financial report sent successfully to {recipient}."
            }
        )

    except Exception as exc:

        # During development this helps you see the actual
        # SMTP/backend error in the terminal.
        print(
            "ACCOUNTANT EMAIL ERROR:",
            repr(exc)
        )

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Unable to send the email. "
                    "Please check the email configuration and try again."
                ),
            },
            status=500,
        )


def _email_label_style():
    return (
        "padding:12px 20px;"
        "color:#64748b;"
        "font-size:13px;"
        "border-bottom:1px solid #f1f5f9;"
    )


def _email_value_style():
    return (
        "padding:12px 20px;"
        "color:#111827;"
        "font-size:13px;"
        "font-weight:600;"
        "text-align:right;"
        "border-bottom:1px solid #f1f5f9;"
    )







# ============================================================
# ACCOUNTANT PAYROLL HELPERS
# ============================================================

def _decimal_value(value, default="0.00"):
    try:
        return Decimal(str(value or default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _staff_name(staff):
    first_name = getattr(staff, "first_name", "") or ""
    last_name = getattr(staff, "last_name", "") or ""

    name = f"{first_name} {last_name}".strip()

    if name:
        return name

    return (
        getattr(staff, "name", "")
        or getattr(staff, "employee_id", "")
        or f"Staff #{staff.pk}"
    )


def _payroll_to_dict(payroll):

    # ========================================================
    # EARNINGS
    # ========================================================

    basic_salary = _decimal_value(
        getattr(
            payroll,
            "basic_salary",
            0
        )
    )

    overtime_amount = _decimal_value(
        getattr(
            payroll,
            "overtime_amount",
            0
        )
    )

    bonus = _decimal_value(
        getattr(
            payroll,
            "bonus",
            0
        )
    )

    incentive = _decimal_value(
        getattr(
            payroll,
            "incentive",
            0
        )
    )


    # ========================================================
    # TOTAL ALLOWANCES
    #
    # Accountant UI calls this total_allowances.
    # Actual Payroll model stores individual earnings.
    # ========================================================

    total_allowances = (
        overtime_amount
        + bonus
        + incentive
    )


    # ========================================================
    # DEDUCTIONS
    # ========================================================

    deductions = _decimal_value(
        getattr(
            payroll,
            "deductions",
            0
        )
    )

    pf_amount = _decimal_value(
        getattr(
            payroll,
            "pf_amount",
            0
        )
    )

    esi_amount = _decimal_value(
        getattr(
            payroll,
            "esi_amount",
            0
        )
    )

    loan_deduction = _decimal_value(
        getattr(
            payroll,
            "loan_deduction",
            0
        )
    )

    tax_deduction = _decimal_value(
        getattr(
            payroll,
            "tax_deduction",
            0
        )
    )


    total_deductions = (
        deductions
        + pf_amount
        + esi_amount
        + loan_deduction
        + tax_deduction
    )


    # ========================================================
    # NET SALARY
    # ========================================================

    net_salary = _decimal_value(
        getattr(
            payroll,
            "net_salary",
            0
        )
    )


    # ========================================================
    # STATUS
    # Actual model uses paid_status
    # ========================================================

    paid_status = getattr(
        payroll,
        "paid_status",
        "Unpaid"
    )

    status = (
        "paid"
        if str(paid_status).lower() == "paid"
        else "pending"
    )


    # ========================================================
    # RESPONSE
    # ========================================================

    return {

        "id": payroll.pk,

        "staff_id": payroll.staff_id,

        "employee_name":
            _staff_name(
                payroll.staff
            ),

        "employee_id": (
            getattr(
                payroll.staff,
                "employee_id",
                ""
            )
            or ""
        ),

        "month":
            payroll.month,

        "year":
            payroll.year,

        "basic_salary":
            str(basic_salary),

        # Keep these names because the current
        # accountant JS expects them.
        "total_allowances":
            str(total_allowances),

        "total_deductions":
            str(total_deductions),

        "net_salary":
            str(net_salary),

        "overtime_amount":
            str(overtime_amount),

        "bonus":
            str(bonus),

        "incentive":
            str(incentive),

        "deductions":
            str(deductions),

        "pf_amount":
            str(pf_amount),

        "esi_amount":
            str(esi_amount),

        "loan_deduction":
            str(loan_deduction),

        "tax_deduction":
            str(tax_deduction),

        "paid_status":
            paid_status,

        "status":
            status,

        "paid_at": (
            payroll.paid_at.isoformat()
            if getattr(
                payroll,
                "paid_at",
                None
            )
            else None
        ),
    }

    

# ============================================================
# PAYROLL DETAILS
# ============================================================
@login_required
@require_GET
def accountant_payroll_details(request, payroll_id):

    payroll = get_object_or_404(
        Payroll.objects.select_related(
            "staff",
            "hotel",
            "staff__department",
        ).prefetch_related("line_items"),
        pk=payroll_id,
    )

    staff = payroll.staff

    # ---------------------------------------------------------
    # SECURITY
    # ---------------------------------------------------------
    # If your project already has tenant/hotel permission
    # checking here, KEEP that checking.
    # Do not remove your existing hotel isolation logic.
    # ---------------------------------------------------------

    # ---------------------------------------------------------
    # PAYROLL PERIOD
    # ---------------------------------------------------------
    last_day = calendar.monthrange(
        payroll.year,
        payroll.month
    )[1]

    period_from = f"{payroll.year:04d}-{payroll.month:02d}-01"
    period_to = (
        f"{payroll.year:04d}-"
        f"{payroll.month:02d}-"
        f"{last_day:02d}"
    )

    # ---------------------------------------------------------
    # EMPLOYEE DETAILS
    # ---------------------------------------------------------
    employee_name = (
        getattr(staff, "name", None)
        or getattr(staff, "full_name", None)
        or str(staff)
    )

    employee_id = (
        getattr(staff, "employee_id", None)
        or getattr(staff, "staff_id", None)
        or f"EMP-{staff.pk:03d}"
    )

    department_obj = getattr(staff, "department", None)

    department = (
        getattr(department_obj, "name", None)
        or str(department_obj)
        if department_obj
        else "ΓÇö"
    )

    designation = (
        getattr(staff, "designation", None)
        or getattr(staff, "role", None)
        or getattr(staff, "position", None)
        or "ΓÇö"
    )

    # ---------------------------------------------------------
    # LINE ITEMS
    # ---------------------------------------------------------
    earning_items = []
    deduction_items = []

    earning_total = Decimal("0.00")
    deduction_total = Decimal("0.00")

    basic_salary = payroll.basic_salary or Decimal("0.00")

    # Basic salary is shown separately and locked in the UI.
    earning_total += basic_salary

    for item in payroll.line_items.all():

        item_data = {
            "id": item.id,
            "source": item.source,
            "label": item.label,
            "amount": str(item.amount or Decimal("0.00")),
            "pct": (
                str(item.pct)
                if item.pct is not None
                else ""
            ),
            "pct_base": item.pct_base or "",
            "is_auto": item.is_auto,
            "note": item.note or "",
            "order": item.order,
        }

        if item.line_type == "earning":

            # Do not add a line-item basic salary again.
            # The main Payroll.basic_salary is authoritative.
            if item.source != "basic":
                earning_total += item.amount or Decimal("0.00")
                earning_items.append(item_data)

        elif item.line_type == "deduction":
            deduction_total += item.amount or Decimal("0.00")
            deduction_items.append(item_data)

    # ---------------------------------------------------------
    # LEGACY FALLBACK
    # ---------------------------------------------------------
    # If old payroll records were created before PayrollLineItem
    # was being used, expose existing fixed values as rows.
    # This avoids old records appearing empty in the new modal.
    # ---------------------------------------------------------

    if not earning_items:

        legacy_earnings = [
            (
                "overtime",
                "Overtime",
                payroll.overtime_amount,
            ),
            (
                "bonus",
                "Bonus",
                payroll.bonus,
            ),
            (
                "incentive",
                "Incentive",
                payroll.incentive,
            ),
        ]

        for source, label, amount in legacy_earnings:

            amount = amount or Decimal("0.00")

            if amount > 0:

                earning_items.append({
                    "id": None,
                    "source": source,
                    "label": label,
                    "amount": str(amount),
                    "pct": "",
                    "pct_base": "",
                    "is_auto": False,
                    "note": "",
                    "order": len(earning_items) + 1,
                })

                earning_total += amount

    if not deduction_items:

        legacy_deductions = [
            (
                "custom",
                "Other Deduction",
                payroll.deductions,
            ),
            (
                "pf",
                "PF",
                payroll.pf_amount,
            ),
            (
                "esi",
                "ESI",
                payroll.esi_amount,
            ),
            (
                "tax",
                "Tax / TDS",
                payroll.tax_deduction,
            ),
            (
                "loan",
                "Loan Deduction",
                payroll.loan_deduction,
            ),
        ]

        for source, label, amount in legacy_deductions:

            amount = amount or Decimal("0.00")

            if amount > 0:

                deduction_items.append({
                    "id": None,
                    "source": source,
                    "label": label,
                    "amount": str(amount),
                    "pct": "",
                    "pct_base": "",
                    "is_auto": False,
                    "note": "",
                    "order": len(deduction_items) + 1,
                })

                deduction_total += amount

    net_salary = earning_total - deduction_total

    return JsonResponse({
        "success": True,

        "payroll": {
            "id": payroll.id,

            "employee_name": employee_name,
            "employee_id": employee_id,

            "department": department,
            "designation": designation,

            "month": payroll.month,
            "year": payroll.year,

            "period_from": period_from,
            "period_to": period_to,

            "basic_salary": str(basic_salary),

            "earnings": earning_items,
            "deductions": deduction_items,

            "total_earnings": str(earning_total),
            "total_deductions": str(deduction_total),
            "net_salary": str(net_salary),

            "paid_status": payroll.paid_status,

            "notes": payroll.notes or "",

            "paid_at": (
                payroll.paid_at.strftime(
                    "%d-%m-%Y %I:%M %p"
                )
                if payroll.paid_at
                else None
            ),
        }
    })




# ============================================================
# GENERATE PAYROLL
# ============================================================

@login_required
@require_POST
@transaction.atomic
def accountant_generate_payroll(request):

    try:
        data = json.loads(
            request.body.decode("utf-8")
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request data.",
            },
            status=400,
        )

    staff_id = data.get("staff_id")
    month = data.get("month")
    year = data.get("year")

    basic_salary = _decimal_value(
        data.get("basic_salary")
    )

    allowances = _decimal_value(
        data.get("allowances")
    )

    deductions = _decimal_value(
        data.get("deductions")
    )

    if not staff_id:
        return JsonResponse(
            {
                "success": False,
                "message": "Please select an employee.",
            },
            status=400,
        )

    try:
        month = int(month)
        year = int(year)
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid month or year.",
            },
            status=400,
        )

    if month < 1 or month > 12:
        return JsonResponse(
            {
                "success": False,
                "message": "Invalid payroll month.",
            },
            status=400,
        )

    if basic_salary < 0:
        return JsonResponse(
            {
                "success": False,
                "message": "Basic salary cannot be negative.",
            },
            status=400,
        )

    if allowances < 0 or deductions < 0:
        return JsonResponse(
            {
                "success": False,
                "message":
                    "Allowances and deductions cannot be negative.",
            },
            status=400,
        )

    staff = get_object_or_404(
        Staff,
        pk=staff_id,
    )

    net_salary = (
        basic_salary
        + allowances
        - deductions
    )

    if net_salary < 0:
        return JsonResponse(
            {
                "success": False,
                "message":
                    "Net salary cannot be negative.",
            },
            status=400,
        )

    payroll, created = (
        Payroll.objects.get_or_create(
            staff=staff,
            month=month,
            year=year,
            defaults={
                "basic_salary":
                    basic_salary,
                "bonus":
                      allowances,

                "deductions":
                      deductions,

                 "net_salary":
                     net_salary,

                 "paid_status":
                      "Unpaid",

               
            },
        )
    )

    if not created:

        if (
        str(
            getattr(
                payroll,
                "paid_status",
                ""
            )
        ).lower()
        == "paid"
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message":
                        "This payroll is already paid and cannot be regenerated.",
                },
                status=400,
            )

        payroll.basic_salary = basic_salary
        payroll.total_allowances = allowances
        payroll.total_deductions = deductions
        payroll.net_salary = net_salary

        payroll.save(
            update_fields=[
                "basic_salary",
                "total_allowances",
                "total_deductions",
                "net_salary",
            ]
        )

    return JsonResponse({
        "success": True,

        "created": created,

        "message": (
            "Payroll generated successfully."
            if created
            else "Payroll updated successfully."
        ),

        "payroll":
            _payroll_to_dict(payroll),
    })


# ============================================================
# UPDATE PAYROLL
# ============================================================
@login_required
@require_POST
def accountant_update_payroll(request, payroll_id):

    payroll = get_object_or_404(
        Payroll.objects.select_related(
            "staff",
            "hotel",
        ),
        pk=payroll_id,
    )

    # ---------------------------------------------------------
    # SECURITY
    # ---------------------------------------------------------
    # IMPORTANT:
    # If your existing view checks current hotel / tenant /
    # accountant permissions, KEEP those checks here.
    # ---------------------------------------------------------

    if payroll.paid_status == "Paid":
        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Paid payroll cannot be edited."
                ),
            },
            status=400,
        )

    try:
        data = json.loads(
            request.body.decode("utf-8")
        )

    except (json.JSONDecodeError, UnicodeDecodeError):

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid request data.",
            },
            status=400,
        )

    # ---------------------------------------------------------
    # DECIMAL HELPER
    # ---------------------------------------------------------

    def decimal_value(value, default="0.00"):

        if value in (
            None,
            "",
        ):
            return Decimal(default)

        try:
            result = Decimal(str(value))

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            raise ValueError(
                f"Invalid amount: {value}"
            )

        if result < 0:
            raise ValueError(
                "Amounts cannot be negative."
            )

        return result.quantize(
            Decimal("0.01")
        )

    try:

        basic_salary = decimal_value(
            data.get("basic_salary")
        )

        earnings = data.get(
            "earnings",
            []
        )

        deductions = data.get(
            "deductions",
            []
        )

        notes = str(
            data.get("notes", "")
        ).strip()

        if not isinstance(
            earnings,
            list
        ):
            raise ValueError(
                "Invalid earnings data."
            )

        if not isinstance(
            deductions,
            list
        ):
            raise ValueError(
                "Invalid deductions data."
            )

        cleaned_earnings = []
        cleaned_deductions = []

        # -----------------------------------------------------
        # VALIDATE EARNINGS
        # -----------------------------------------------------

        for index, row in enumerate(
            earnings
        ):

            label = str(
                row.get("label", "")
            ).strip()

            source = str(
                row.get(
                    "source",
                    "custom"
                )
            ).strip()

            amount = decimal_value(
                row.get("amount")
            )

            pct_raw = row.get("pct")

            pct = None

            if pct_raw not in (
                None,
                "",
            ):

                pct = decimal_value(
                    pct_raw
                )

                if pct > Decimal("1000"):
                    raise ValueError(
                        "Percentage is too large."
                    )

            if not label:
                raise ValueError(
                    "Every earning requires a name."
                )

            cleaned_earnings.append({
                "label": label[:100],
                "source": source,
                "amount": amount,
                "pct": pct,
                "order": index + 1,
            })

        # -----------------------------------------------------
        # VALIDATE DEDUCTIONS
        # -----------------------------------------------------

        for index, row in enumerate(
            deductions
        ):

            label = str(
                row.get("label", "")
            ).strip()

            source = str(
                row.get(
                    "source",
                    "custom"
                )
            ).strip()

            amount = decimal_value(
                row.get("amount")
            )

            pct_raw = row.get("pct")

            pct = None

            if pct_raw not in (
                None,
                "",
            ):

                pct = decimal_value(
                    pct_raw
                )

                if pct > Decimal("1000"):
                    raise ValueError(
                        "Percentage is too large."
                    )

            if not label:
                raise ValueError(
                    "Every deduction requires a name."
                )

            cleaned_deductions.append({
                "label": label[:100],
                "source": source,
                "amount": amount,
                "pct": pct,
                "order": index + 1,
            })

        # -----------------------------------------------------
        # TOTALS
        # -----------------------------------------------------

        extra_earnings_total = sum(
            (
                row["amount"]
                for row in cleaned_earnings
            ),
            Decimal("0.00"),
        )

        deduction_total = sum(
            (
                row["amount"]
                for row in cleaned_deductions
            ),
            Decimal("0.00"),
        )

        total_earnings = (
            basic_salary
            + extra_earnings_total
        )

        net_salary = (
            total_earnings
            - deduction_total
        )

        if net_salary < 0:
            raise ValueError(
                "Net salary cannot be negative."
            )

        # -----------------------------------------------------
        # SAVE EVERYTHING ATOMICALLY
        # -----------------------------------------------------

        with transaction.atomic():

            payroll.basic_salary = (
                basic_salary
            )

            # Reset fixed compatibility fields.
            payroll.overtime_amount = (
                Decimal("0.00")
            )

            payroll.bonus = (
                Decimal("0.00")
            )

            payroll.incentive = (
                Decimal("0.00")
            )

            payroll.deductions = (
                Decimal("0.00")
            )

            payroll.pf_amount = (
                Decimal("0.00")
            )

            payroll.esi_amount = (
                Decimal("0.00")
            )

            payroll.tax_deduction = (
                Decimal("0.00")
            )

            payroll.loan_deduction = (
                Decimal("0.00")
            )

            # ---------------------------------------------
            # Map known earnings back to legacy fields
            # ---------------------------------------------

            for row in cleaned_earnings:

                if row["source"] == "overtime":
                    payroll.overtime_amount += (
                        row["amount"]
                    )

                elif row["source"] == "bonus":
                    payroll.bonus += (
                        row["amount"]
                    )

                elif row["source"] == "incentive":
                    payroll.incentive += (
                        row["amount"]
                    )

            # ---------------------------------------------
            # Map known deductions back to legacy fields
            # ---------------------------------------------

            custom_deduction_total = (
                Decimal("0.00")
            )

            for row in cleaned_deductions:

                if row["source"] == "pf":
                    payroll.pf_amount += (
                        row["amount"]
                    )

                elif row["source"] == "esi":
                    payroll.esi_amount += (
                        row["amount"]
                    )

                elif row["source"] in (
                    "tax",
                    "pt",
                ):
                    payroll.tax_deduction += (
                        row["amount"]
                    )

                elif row["source"] == "loan":
                    payroll.loan_deduction += (
                        row["amount"]
                    )

                else:
                    custom_deduction_total += (
                        row["amount"]
                    )

            payroll.deductions = (
                custom_deduction_total
            )

            payroll.net_salary = (
                net_salary
            )

            payroll.notes = notes

            # Keep JSON compatibility fields populated.
            payroll.custom_earnings = [
                {
                    "label": row["label"],
                    "source": row["source"],
                    "amount": str(
                        row["amount"]
                    ),
                    "pct": (
                        str(row["pct"])
                        if row["pct"] is not None
                        else None
                    ),
                }
                for row in cleaned_earnings
                if row["source"] == "custom"
            ]

            payroll.custom_deductions = [
                {
                    "label": row["label"],
                    "source": row["source"],
                    "amount": str(
                        row["amount"]
                    ),
                    "pct": (
                        str(row["pct"])
                        if row["pct"] is not None
                        else None
                    ),
                }
                for row in cleaned_deductions
                if row["source"] == "custom"
            ]

            payroll.save()

            # ---------------------------------------------
            # Replace editable line items
            # ---------------------------------------------

            payroll.line_items.all().delete()

            line_items = []

            for row in cleaned_earnings:

                line_items.append(
                    PayrollLineItem(
                        payroll=payroll,
                        line_type="earning",
                        source=(
                            row["source"]
                            if row["source"] in dict(
                                PayrollLineItem.SOURCE_CHOICES
                            )
                            else "custom"
                        ),
                        label=row["label"],
                        amount=row["amount"],
                        pct=row["pct"],
                        pct_base=(
                            "basic"
                            if row["pct"] is not None
                            else ""
                        ),
                        is_auto=False,
                        order=row["order"],
                    )
                )

            for row in cleaned_deductions:

                line_items.append(
                    PayrollLineItem(
                        payroll=payroll,
                        line_type="deduction",
                        source=(
                            row["source"]
                            if row["source"] in dict(
                                PayrollLineItem.SOURCE_CHOICES
                            )
                            else "custom"
                        ),
                        label=row["label"],
                        amount=row["amount"],
                        pct=row["pct"],
                        pct_base=(
                            "basic"
                            if row["pct"] is not None
                            else ""
                        ),
                        is_auto=False,
                        order=row["order"],
                    )
                )

            PayrollLineItem.objects.bulk_create(
                line_items
            )

        return JsonResponse({
            "success": True,

            "message": (
                "Payroll updated successfully."
            ),

            "total_earnings": str(
                total_earnings
            ),

            "total_deductions": str(
                deduction_total
            ),

            "net_salary": str(
                net_salary
            ),
        })

    except ValueError as error:

        return JsonResponse(
            {
                "success": False,
                "message": str(error),
            },
            status=400,
        )

    except Exception as error:

        return JsonResponse(
            {
                "success": False,
                "message": (
                    "Unable to update payroll."
                ),
                "error": str(error),
            },
            status=500,
        )



# ============================================================
# MARK PAYROLL PAID
# ============================================================

@login_required
@require_POST
@transaction.atomic
def accountant_mark_payroll_paid(
    request,
    payroll_id
):

    payroll = get_object_or_404(
        Payroll,
        pk=payroll_id,
    )


    # ========================================================
    # ALREADY PAID
    # ========================================================

    if (
        str(
            getattr(
                payroll,
                "paid_status",
                ""
            )
        ).lower()
        == "paid"
    ):

        return JsonResponse({
            "success": True,
            "message":
                "Payroll is already marked as paid.",
        })


    # ========================================================
    # MARK PAID
    # ========================================================

    payroll.paid_status = "Paid"

    update_fields = [
        "paid_status"
    ]


    # ========================================================
    # PAID TIME
    # ========================================================

    if hasattr(
        payroll,
        "paid_at"
    ):

        payroll.paid_at = (
            timezone.now()
        )

        update_fields.append(
            "paid_at"
        )


    payroll.save(
        update_fields=
            update_fields
    )


    return JsonResponse({
        "success": True,

        "message":
            "Payroll marked as paid successfully.",
    })




# ============================================================
# PAYSLIP
# ============================================================

@login_required
@require_GET
def accountant_payroll_payslip(request, payroll_id):

    # =========================================================
    # GET LOGGED-IN ACCOUNTANT
    # =========================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    accountant = get_object_or_404(
        Staff.objects.select_related(
            "hotel",
            "department",
        ),
        pk=staff_id,
    )

    hotel = accountant.hotel

    if not hotel:
        return redirect("staff_login")


    # =========================================================
    # GET PAYROLL
    # IMPORTANT:
    # Only payroll belonging to this accountant's hotel
    # =========================================================

    payroll = get_object_or_404(
        Payroll.objects.select_related(
            "staff",
            "staff__department",
            "hotel",
            "paid_by",
        ),
        pk=payroll_id,
        hotel=hotel,
    )


    # =========================================================
    # CUSTOM EARNINGS
    # =========================================================

    custom_earnings_total = Decimal("0.00")

    for item in payroll.custom_earnings or []:

        try:
            custom_earnings_total += Decimal(
                str(item.get("amount", 0))
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
            AttributeError,
        ):
            continue


    # =========================================================
    # CUSTOM DEDUCTIONS
    # =========================================================

    custom_deductions_total = Decimal("0.00")

    for item in payroll.custom_deductions or []:

        try:
            custom_deductions_total += Decimal(
                str(item.get("amount", 0))
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError,
            AttributeError,
        ):
            continue


    # =========================================================
    # TOTAL EARNINGS
    # =========================================================

    total_earnings = (
        payroll.basic_salary
        + payroll.overtime_amount
        + payroll.bonus
        + payroll.incentive
        + custom_earnings_total
    )


    # =========================================================
    # TOTAL DEDUCTIONS
    # =========================================================

    total_deductions = (
        payroll.deductions
        + payroll.pf_amount
        + payroll.esi_amount
        + payroll.tax_deduction
        + payroll.loan_deduction
        + custom_deductions_total
    )


    context = {

        "payroll": payroll,

        "total_earnings": total_earnings,

        "total_deductions": total_deductions,

        "custom_earnings_total":
            custom_earnings_total,

        "custom_deductions_total":
            custom_deductions_total,
    }


    return render(
        request,
        "accountant/payslip.html",
        context,
    )


# ============================================================
# ACCOUNTANT - EXPENSE MANAGEMENT
# ============================================================

import csv
import json

from datetime import date
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import staff_login_required
from accounts.models import Staff, Department

from inventory.models import (
    Expense,
    ExpenseCategory,
    PurchaseOrder,
    MaintenanceLog,
)


# ============================================================
# HELPER - GET CURRENT STAFF
# ============================================================

def _get_accountant_expense_staff(request):

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return None

    try:

        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
                "user",
            )
            .get(id=staff_id)
        )

        # Make sure hotel_id is available in session too
        if staff.hotel_id:
            request.session["hotel_id"] = staff.hotel_id

        return staff

    except Staff.DoesNotExist:
        return None


# ============================================================
# HELPER - PARSE FILTER PERIOD
# ============================================================

def _expense_parse_period(request):

    filter_date = (
        request.GET.get("date") or ""
    ).strip()

    filter_month = (
        request.GET.get("month") or ""
    ).strip()

    # --------------------------------------------------------
    # Exact date has priority
    # --------------------------------------------------------

    if filter_date:

        try:
            selected_date = date.fromisoformat(
                filter_date
            )

            return {
                "type": "date",
                "date": selected_date,
                "month": None,
                "year": None,
            }

        except ValueError:
            pass

    # --------------------------------------------------------
    # Month
    # --------------------------------------------------------

    if filter_month:

        try:

            year_text, month_text = (
                filter_month.split("-")
            )

            selected_year = int(year_text)
            selected_month = int(month_text)

            if 1 <= selected_month <= 12:

                return {
                    "type": "month",
                    "date": None,
                    "month": selected_month,
                    "year": selected_year,
                }

        except (
            ValueError,
            TypeError,
            IndexError,
        ):
            pass

    # --------------------------------------------------------
    # Default = current month
    # --------------------------------------------------------

    today = timezone.now().date()

    return {
        "type": "month",
        "date": None,
        "month": today.month,
        "year": today.year,
    }


# ============================================================
# HELPER - HOTEL EXPENSE QUERYSET
# ============================================================

def _hotel_expense_queryset(staff):

    """
    IMPORTANT:
    Expense itself does not need a hotel field here.

    Expense -> Department -> Hotel

    This makes sure an accountant can only access expenses
    belonging to his/her hotel.
    """

    return (
        Expense.objects
        .filter(
            department__hotel_id=staff.hotel_id
        )
        .select_related(
            "department",
            "expense_category",
            "purchase_order",
            "purchase_order__vendor",
            "maintenance_log",
            "recorded_by",
        )
    )


# ============================================================
# HELPER - APPLY FILTERS
# ============================================================

def _filter_expense_queryset(
    request,
    queryset,
):

    period = _expense_parse_period(request)

    # --------------------------------------------------------
    # DATE / MONTH
    # --------------------------------------------------------

    if period["type"] == "date":

        queryset = queryset.filter(
            expense_date=period["date"]
        )

    else:

        queryset = queryset.filter(
            expense_date__month=period["month"],
            expense_date__year=period["year"],
        )

    # --------------------------------------------------------
    # DEPARTMENT
    # --------------------------------------------------------

    department_id = (
        request.GET.get("department_id") or ""
    ).strip()

    if department_id:

        queryset = queryset.filter(
            department_id=department_id
        )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    category_id = (
        request.GET.get("category_id") or ""
    ).strip()

    if category_id:

        queryset = queryset.filter(
            expense_category_id=category_id
        )

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source = (
        request.GET.get("source") or ""
    ).strip()

    allowed_sources = {
        "manual",
        "purchase_order",
        "maintenance",
    }

    if source in allowed_sources:

        queryset = queryset.filter(
            source=source
        )

    return queryset, period


# ============================================================
# EXPENSE PAGE
# ============================================================

@never_cache
@staff_login_required
def expense_report_view(request):

    # ============================================================
    # GET LOGGED-IN ACCOUNTANT / STAFF
    # ============================================================

    staff = _get_accountant_expense_staff(request)

    if not staff:
        return redirect("staff_login")

    hotel = staff.hotel

    # ============================================================
    # DEPARTMENTS
    # ============================================================

    departments = (
        Department.objects
        .filter(hotel_id=hotel.id)
        .order_by("name")
    )

    # ============================================================
    # DEFAULT EXPENSE CATEGORIES
    # ============================================================

    DEFAULT_EXPENSE_CATEGORIES = [
        "Food & Beverage",
        "Utilities",
        "Maintenance",
        "Housekeeping",
        "Laundry",
        "Staff Expense",
        "Transport",
        "Office Supplies",
        "Marketing",
        "Internet & Telephone",
        "Electricity",
        "Water",
        "Gas",
        "Repairs",
        "Purchase",
        "Miscellaneous",
    ]

    # ============================================================
    # CREATE CATEGORIES IF THEY DO NOT EXIST
    # ============================================================

    for category_name in DEFAULT_EXPENSE_CATEGORIES:

        ExpenseCategory.objects.get_or_create(
            name=category_name
        )

    # ============================================================
    # GET CATEGORIES
    # ============================================================

    categories = (
        ExpenseCategory.objects
        .all()
        .order_by("name")
    )

    # ============================================================
    # DATE
    #
    # Do NOT use timezone.localdate() here because your project
    # currently contains naive datetime values.
    # ============================================================

    today = timezone.now().date()

    # ============================================================
    # CONTEXT
    # ============================================================

    context = {

        "staff": staff,

        "hotel": hotel,

        "today": today,

        "current_month": today.strftime("%Y-%m"),

        "departments": departments,

        "categories": categories,
    }

    # ============================================================
    # RENDER
    # ============================================================

    return render(
        request,
        "accountant/expenses.html",
        context,
    )

# ============================================================
# EXPENSE REPORT API
# ============================================================

@staff_login_required
@require_GET
def expense_report_api(request):

    staff = _get_accountant_expense_staff(
        request
    )

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required.",
            },
            status=401,
        )

    # --------------------------------------------------------
    # BASE QUERYSET
    # --------------------------------------------------------

    queryset = _hotel_expense_queryset(
        staff
    )

    queryset, period = (
        _filter_expense_queryset(
            request,
            queryset,
        )
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    total_amount = (
        queryset.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    manual_qs = queryset.filter(
        source="manual"
    )

    purchase_qs = queryset.filter(
        source="purchase_order"
    )

    maintenance_qs = queryset.filter(
        source="maintenance"
    )

    manual_total = (
        manual_qs.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    purchase_total = (
        purchase_qs.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    maintenance_total = (
        maintenance_qs.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    summary = {

        "total": float(total_amount),

        "count": queryset.count(),

        "manual_total": float(
            manual_total
        ),

        "manual_count": (
            manual_qs.count()
        ),

        "po_total": float(
            purchase_total
        ),

        "po_count": (
            purchase_qs.count()
        ),

        "maintenance_total": float(
            maintenance_total
        ),

        "maintenance_count": (
            maintenance_qs.count()
        ),
    }

    # --------------------------------------------------------
    # DEPARTMENT BREAKDOWN
    # --------------------------------------------------------

    department_breakdown = []

    department_rows = (
        queryset
        .values(
            "department_id",
            "department__name",
        )
        .annotate(
            total=Sum("amount"),
            count=Count("id"),
        )
        .order_by("-total")
    )

    for row in department_rows:

        department_breakdown.append(
            {
                "department_id":
                    row["department_id"],

                "department":
                    row["department__name"]
                    or "Unassigned",

                "total":
                    float(
                        row["total"] or 0
                    ),

                "count":
                    row["count"],
            }
        )

    # --------------------------------------------------------
    # CATEGORY BREAKDOWN
    # --------------------------------------------------------

    category_breakdown = []

    category_rows = (
        queryset
        .values(
            "expense_category_id",
            "expense_category__name",
        )
        .annotate(
            total=Sum("amount"),
            count=Count("id"),
        )
        .order_by("-total")
    )

    for row in category_rows:

        category_breakdown.append(
            {
                "category_id":
                    row["expense_category_id"],

                "category":
                    row[
                        "expense_category__name"
                    ]
                    or "Uncategorised",

                "total":
                    float(
                        row["total"] or 0
                    ),

                "count":
                    row["count"],
            }
        )

    # --------------------------------------------------------
    # TRANSACTIONS
    # --------------------------------------------------------

    transactions = []

    for expense in queryset.order_by(
        "-expense_date",
        "-id",
    ):

        if expense.purchase_order_id:

            reference = (
                f"PO-{expense.purchase_order_id}"
            )

        elif expense.maintenance_log_id:

            reference = (
                f"ML-{expense.maintenance_log_id}"
            )

        else:
            reference = "ΓÇö"

        transactions.append(
            {
                "id":
                    expense.id,

                "date":
                    expense.expense_date.strftime(
                        "%Y-%m-%d"
                    ),

                "display_date":
                    expense.expense_date.strftime(
                        "%d %b %Y"
                    ),

                "department_id":
                    expense.department_id,

                "department":
                    (
                        expense.department.name
                        if expense.department
                        else "ΓÇö"
                    ),

                "category_id":
                    expense.expense_category_id,

                "category":
                    (
                        expense.expense_category.name
                        if expense.expense_category
                        else "ΓÇö"
                    ),

                "source":
                    expense.source or "manual",

                "reference":
                    reference,

                # Keep old name too
                "ref":
                    reference,

                "description":
                    expense.description or "",

                "amount":
                    float(
                        expense.amount or 0
                    ),

                "recorded_by":
                    (
                        expense.recorded_by.name
                        if expense.recorded_by
                        else "ΓÇö"
                    ),

                # Only manually entered expenses
                # can be edited/deleted here.
                "can_edit":
                    expense.source == "manual",

                "can_delete":
                    expense.source == "manual",
            }
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return JsonResponse(
        {
            "success": True,

            "period": {
                "type": period["type"],

                "date": (
                    str(period["date"])
                    if period["date"]
                    else None
                ),

                "month":
                    period["month"],

                "year":
                    period["year"],
            },

            "summary":
                summary,

            "by_department":
                department_breakdown,

            "by_category":
                category_breakdown,

            "transactions":
                transactions,
        }
    )


# ============================================================
# ADD MANUAL EXPENSE
# ============================================================

@staff_login_required
@require_POST
def expense_add(request):

    staff = _get_accountant_expense_staff(
        request
    )

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required.",
            },
            status=401,
        )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        data = json.loads(
            request.body or "{}"
        )

    except json.JSONDecodeError:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    # --------------------------------------------------------
    # VALUES
    # --------------------------------------------------------

    department_id = data.get(
        "department_id"
    )

    category_id = data.get(
        "expense_category_id"
    )

    amount_value = data.get(
        "amount"
    )

    description = (
        data.get("description") or ""
    ).strip()

    expense_date_value = (
        data.get("expense_date") or ""
    ).strip()

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not department_id:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Please select a department."
                ),
            },
            status=400,
        )

    if not category_id:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Please select an expense category."
                ),
            },
            status=400,
        )

    if not description:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Expense description is required."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # AMOUNT
    # --------------------------------------------------------

    try:

        amount = Decimal(
            str(amount_value)
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Enter a valid expense amount."
                ),
            },
            status=400,
        )

    if amount <= 0:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Expense amount must be "
                    "greater than zero."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if expense_date_value:

        try:

            expense_date_obj = (
                date.fromisoformat(
                    expense_date_value
                )
            )

        except ValueError:

            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid expense date.",
                },
                status=400,
            )

    else:

        expense_date_obj = (
            timezone.localdate()
        )

    # --------------------------------------------------------
    # DEPARTMENT MUST BELONG TO HOTEL
    # --------------------------------------------------------

    try:

        department = (
            Department.objects.get(
                id=department_id,
                hotel_id=staff.hotel_id,
            )
        )

    except Department.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Invalid department."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    try:

        category = (
            ExpenseCategory.objects.get(
                id=category_id
            )
        )

    except ExpenseCategory.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Invalid expense category."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # CREATE
    # --------------------------------------------------------

    expense = Expense.objects.create(

        department=department,

        expense_category=category,

        # IMPORTANT:
        # User cannot fake PO or maintenance source.
        source="manual",

        amount=amount,

        description=description,

        expense_date=expense_date_obj,

        recorded_by=staff,
    )

    return JsonResponse(
        {
            "success": True,

            "message":
                "Expense added successfully.",

            "expense": {
                "id": expense.id,
            },
        },
        status=201,
    )


# ============================================================
# UPDATE MANUAL EXPENSE
# ============================================================

@staff_login_required
@require_POST
def expense_update(
    request,
    expense_id,
):

    staff = _get_accountant_expense_staff(
        request
    )

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required.",
            },
            status=401,
        )

    # --------------------------------------------------------
    # EXPENSE
    # Current hotel + manual only
    # --------------------------------------------------------

    try:

        expense = (
            Expense.objects
            .select_related(
                "department",
                "expense_category",
            )
            .get(
                id=expense_id,
                department__hotel_id=(
                    staff.hotel_id
                ),
            )
        )

    except Expense.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Expense not found.",
            },
            status=404,
        )

    # --------------------------------------------------------
    # Do not edit PO/Maintenance from Expense page
    # --------------------------------------------------------

    if expense.source != "manual":

        return JsonResponse(
            {
                "success": False,

                "error": (
                    "Purchase order and maintenance "
                    "expenses must be edited from "
                    "their original module."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    try:

        data = json.loads(
            request.body or "{}"
        )

    except json.JSONDecodeError:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid request data.",
            },
            status=400,
        )

    department_id = data.get(
        "department_id"
    )

    category_id = data.get(
        "expense_category_id"
    )

    description = (
        data.get("description") or ""
    ).strip()

    amount_value = data.get(
        "amount"
    )

    expense_date_value = (
        data.get("expense_date") or ""
    ).strip()

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not department_id:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Please select a department."
                ),
            },
            status=400,
        )

    if not category_id:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Please select a category."
                ),
            },
            status=400,
        )

    if not description:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Description is required."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # AMOUNT
    # --------------------------------------------------------

    try:

        amount = Decimal(
            str(amount_value)
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid amount.",
            },
            status=400,
        )

    if amount <= 0:

        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Amount must be greater "
                    "than zero."
                ),
            },
            status=400,
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    try:

        expense_date_obj = (
            date.fromisoformat(
                expense_date_value
            )
        )

    except ValueError:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid expense date.",
            },
            status=400,
        )

    # --------------------------------------------------------
    # DEPARTMENT
    # --------------------------------------------------------

    try:

        department = (
            Department.objects.get(
                id=department_id,
                hotel_id=staff.hotel_id,
            )
        )

    except Department.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid department.",
            },
            status=400,
        )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    try:

        category = (
            ExpenseCategory.objects.get(
                id=category_id
            )
        )

    except ExpenseCategory.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid category.",
            },
            status=400,
        )

    # --------------------------------------------------------
    # UPDATE
    # --------------------------------------------------------

    expense.department = department

    expense.expense_category = category

    expense.amount = amount

    expense.description = description

    expense.expense_date = (
        expense_date_obj
    )

    # Never change source
    expense.source = "manual"

    expense.save()

    return JsonResponse(
        {
            "success": True,

            "message":
                "Expense updated successfully.",

            "expense": {
                "id": expense.id,
            },
        }
    )


# ============================================================
# DELETE MANUAL EXPENSE
# ============================================================

@staff_login_required
@require_POST
def expense_delete(
    request,
    expense_id,
):

    staff = _get_accountant_expense_staff(
        request
    )

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required.",
            },
            status=401,
        )

    try:

        expense = Expense.objects.get(
            id=expense_id,
            department__hotel_id=(
                staff.hotel_id
            ),
        )

    except Expense.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "error": "Expense not found.",
            },
            status=404,
        )

    # --------------------------------------------------------
    # Only manual expenses can be deleted here
    # --------------------------------------------------------

    if expense.source != "manual":

        return JsonResponse(
            {
                "success": False,

                "error": (
                    "This is a system-generated "
                    "expense. Delete or modify it "
                    "from its original module."
                ),
            },
            status=400,
        )

    expense.delete()

    return JsonResponse(
        {
            "success": True,
            "message": (
                "Expense deleted successfully."
            ),
        }
    )


# ============================================================
# EXPENSE SUMMARY API
# ============================================================

@staff_login_required
@require_GET
def expense_summary_api(request):

    staff = _get_accountant_expense_staff(
        request
    )

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required.",
            },
            status=401,
        )

    queryset = _hotel_expense_queryset(
        staff
    )

    queryset, period = (
        _filter_expense_queryset(
            request,
            queryset,
        )
    )

    grand_total = (
        queryset.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0")
    )

    by_department = list(
        queryset
        .values(
            "department__name"
        )
        .annotate(
            total=Sum("amount"),
            count=Count("id"),
        )
        .order_by("-total")
    )

    by_category = list(
        queryset
        .values(
            "expense_category__name"
        )
        .annotate(
            total=Sum("amount"),
            count=Count("id"),
        )
        .order_by("-total")
    )

    department_data = [
        {
            "department":
                row["department__name"]
                or "Unassigned",

            "total":
                float(
                    row["total"] or 0
                ),

            "count":
                row["count"],
        }
        for row in by_department
    ]

    category_data = [
        {
            "category":
                row[
                    "expense_category__name"
                ]
                or "Uncategorised",

            "total":
                float(
                    row["total"] or 0
                ),

            "count":
                row["count"],
        }
        for row in by_category
    ]

    return JsonResponse(
        {
            "success": True,

            "grand_total":
                float(grand_total),

            "by_department":
                department_data,

            "by_category":
                category_data,
        }
    )


# ============================================================
# EXPORT EXPENSE CSV
# ============================================================

@staff_login_required
@require_GET
def expense_export_csv(request):

    staff = _get_accountant_expense_staff(
        request
    )

    if not staff:

        return JsonResponse(
            {
                "success": False,
                "error": "Login required.",
            },
            status=401,
        )

    queryset = _hotel_expense_queryset(
        staff
    )

    queryset, period = (
        _filter_expense_queryset(
            request,
            queryset,
        )
    )

    # --------------------------------------------------------
    # FILE NAME
    # --------------------------------------------------------

    if period["type"] == "date":

        filename = (
            f"expenses_{period['date']}.csv"
        )

    else:

        filename = (
            f"expenses_"
            f"{period['year']}-"
            f"{period['month']:02d}.csv"
        )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    response = HttpResponse(
        content_type=(
            "text/csv; charset=utf-8"
        )
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; filename="{filename}"'
    )

    # Excel UTF-8 support
    response.write("\ufeff")

    writer = csv.writer(response)

    writer.writerow(
        [
            "ID",
            "Date",
            "Department",
            "Category",
            "Source",
            "Reference",
            "Description",
            "Amount",
            "Recorded By",
        ]
    )

    for expense in queryset.order_by(
        "-expense_date",
        "-id",
    ):

        if expense.purchase_order_id:

            reference = (
                f"PO-{expense.purchase_order_id}"
            )

        elif expense.maintenance_log_id:

            reference = (
                f"ML-{expense.maintenance_log_id}"
            )

        else:
            reference = "ΓÇö"

        writer.writerow(
            [
                expense.id,

                expense.expense_date.strftime(
                    "%Y-%m-%d"
                ),

                (
                    expense.department.name
                    if expense.department
                    else "ΓÇö"
                ),

                (
                    expense.expense_category.name
                    if expense.expense_category
                    else "ΓÇö"
                ),

                expense.source or "manual",

                reference,

                expense.description or "",

                str(expense.amount),

                (
                    expense.recorded_by.name
                    if expense.recorded_by
                    else "ΓÇö"
                ),
            ]
        )

    return response  







# ============================================================
# ACCOUNTANT - INVOICES PAGE
# ============================================================

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.decorators import staff_login_required
from accounts.models import Staff
from billing.models import Invoice


@staff_login_required
@never_cache
@login_required
def accountant_invoices(request):

    # ========================================================
    # CURRENT ACCOUNTANT
    # ========================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "department",
                "hotel",
                "user",
            )
            .get(id=staff_id)
        )
    except Staff.DoesNotExist:
        request.session.flush()
        return redirect("staff_login")

    # ========================================================
    # ACCOUNTANT ACCESS
    # ========================================================

    department_name = (
        staff.department.name.lower()
        if staff.department
        else ""
    )

    role = (
        getattr(staff, "role", "") or ""
    ).lower()

    combined = f"{department_name} {role}"

    ACCOUNTANT_KEYWORDS = [
        "accountant",
        "account",
        "accounts",
        "finance",
        "billing",
        "manager",
        "owner",
        "admin",
        "hotel",
    ]

    if not any(
        keyword in combined
        for keyword in ACCOUNTANT_KEYWORDS
    ):
        return redirect("staff_login")

    hotel = staff.hotel

    # ========================================================
    # FILTER VALUES
    # ========================================================

    search = (
        request.GET.get("search", "") or ""
    ).strip()

    status_filter = (
        request.GET.get("status", "") or ""
    ).strip().lower()

    date_filter = (
        request.GET.get("date", "") or ""
    ).strip()

    month_filter = (
        request.GET.get("month", "") or ""
    ).strip()

    # ========================================================
    # BASE QUERY
    # ========================================================

    invoices = (
        Invoice.objects
        .select_related(
            "folio",
            "folio__booking",
            "folio__booking__guest",
            "folio__booking__room",
            "folio__booking__room_unit",
        )
        .order_by("-generated_at")
    )

    # ========================================================
    # SEARCH
    # ========================================================

    if search:

        invoices = invoices.filter(
            Q(invoice_number__icontains=search)
            |
            Q(
                folio__booking__guest__full_name__icontains=
                search
            )
            |
            Q(
                folio__booking__guest__email__icontains=
                search
            )
            |
            Q(
                folio__booking__room_unit__room_number__icontains=
                search
            )
        )

    # ========================================================
    # STATUS FILTER
    # ========================================================

    if status_filter in [
        "paid",
        "pending",
        "partial",
    ]:
        invoices = invoices.filter(
            status=status_filter
        )

    # ========================================================
    # DATE FILTER
    # ========================================================

    if date_filter:

        try:
            selected_date = timezone.datetime.strptime(
                date_filter,
                "%Y-%m-%d",
            ).date()

            invoices = invoices.filter(
                generated_at__date=selected_date
            )

        except ValueError:
            date_filter = ""

    # ========================================================
    # MONTH FILTER
    # ========================================================

    elif month_filter:

        try:

            year_value, month_value = (
                month_filter.split("-")
            )

            invoices = invoices.filter(
                generated_at__year=int(year_value),
                generated_at__month=int(month_value),
            )

        except (
            ValueError,
            TypeError,
        ):
            month_filter = ""

    # ========================================================
    # FILTERED SUMMARY
    # ========================================================

    total_count = invoices.count()

    paid_count = invoices.filter(
        status="paid"
    ).count()

    pending_count = invoices.filter(
        status="pending"
    ).count()

    partial_count = invoices.filter(
        status="partial"
    ).count()

    total_billed = (
        invoices.aggregate(
            total=Sum("grand_total")
        )["total"]
        or Decimal("0.00")
    )

    paid_value = (
        invoices.filter(
            status="paid"
        ).aggregate(
            total=Sum("grand_total")
        )["total"]
        or Decimal("0.00")
    )

    pending_value = (
        invoices.filter(
            status="pending"
        ).aggregate(
            total=Sum("grand_total")
        )["total"]
        or Decimal("0.00")
    )

    partial_value = (
        invoices.filter(
            status="partial"
        ).aggregate(
            total=Sum("grand_total")
        )["total"]
        or Decimal("0.00")
    )

    # ========================================================
    # BUILD TEMPLATE DATA
    # ========================================================

    invoice_rows = []

    for invoice in invoices:

        folio = invoice.folio

        booking = (
            folio.booking
            if folio
            else None
        )

        guest = (
            booking.guest
            if booking
            else None
        )

        room_unit = (
            booking.room_unit
            if booking
            else None
        )

        room = (
            booking.room
            if booking
            else None
        )

        invoice_rows.append({

            "id":
                invoice.id,

            "invoice_number":
                invoice.invoice_number,

            "guest_name": (
                guest.full_name
                if guest
                else "Walk-in Guest"
            ),

            "guest_email": (
                guest.email
                if guest
                else ""
            ),

            "room_number": (
                room_unit.room_number
                if room_unit
                else "ΓÇö"
            ),

            "room_type": (
                room.room_type
                if room
                else "ΓÇö"
            ),

            "check_in": (
              safe_localtime(booking.check_in)
              if booking and booking.check_in
              else None
            ),

            "check_out": (
               safe_localtime(booking.check_out)
               if booking and booking.check_out
               else None
            ),

            "subtotal":
                invoice.subtotal,

            "tax_total":
                invoice.tax_total,

            "discount":
                invoice.discount,

            "grand_total":
                invoice.grand_total,

            "status":
                invoice.status,

            "generated_at": (
               safe_localtime(invoice.generated_at)
               if invoice.generated_at
               else None
            ),
        })

    # ========================================================
    # CONTEXT
    # ========================================================

    context = {

        "staff":
            staff,

        "hotel":
            hotel,

        "invoices":
            invoice_rows,

        "total_count":
            total_count,

        "paid_count":
            paid_count,

        "pending_count":
            pending_count,

        "partial_count":
            partial_count,

        "total_billed":
            total_billed,

        "paid_value":
            paid_value,

        "pending_value":
            pending_value,

        "partial_value":
            partial_value,

        "search":
            search,

        "status_filter":
            status_filter,

        "date_filter":
            date_filter,

        "month_filter":
            month_filter,

        "today":
              timezone.now().date(),
    }

    return render(
        request,
        "accountant/invoices.html",
        context,
    )






# ============================================================
# ACCOUNTANT - PAYMENTS
# ============================================================

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.decorators import staff_login_required
from accounts.models import Staff
from billing.models import BillingPayment


@staff_login_required
@never_cache
@login_required
def accountant_payments(request):

    # ========================================================
    # AUTHENTICATED STAFF
    # ========================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "department",
                "hotel",
                "user",
            )
            .get(pk=staff_id)
        )

    except Staff.DoesNotExist:

        request.session.flush()

        return redirect("staff_login")


    hotel = staff.hotel


    # ========================================================
    # FILTER VALUES
    # ========================================================

    search = (
        request.GET.get("search", "") or ""
    ).strip()

    method_filter = (
        request.GET.get("method", "") or ""
    ).strip()

    date_filter = (
        request.GET.get("date", "") or ""
    ).strip()

    month_filter = (
        request.GET.get("month", "") or ""
    ).strip()


    # ========================================================
    # BASE QUERY
    # ========================================================

    payments = (
        BillingPayment.objects
        .select_related(
            "folio",
            "folio__booking",
            "folio__booking__guest",
            "folio__booking__room",
            "folio__booking__room_unit",
            "received_by",
        )
        .order_by("-received_at")
    )


    # ========================================================
    # HOTEL FILTER
    #
    # IMPORTANT:
    # If BillingPayment has hotel directly, use hotel=hotel.
    # Otherwise filter through folio -> booking -> hotel.
    # ========================================================

    payment_field_names = {
        field.name
        for field in BillingPayment._meta.get_fields()
    }

    if "hotel" in payment_field_names:

        payments = payments.filter(
            hotel=hotel
        )

    else:

        try:

            payments = payments.filter(
                folio__booking__hotel=hotel
            )

        except Exception:

            # If Booking does not have hotel either,
            # leave the queryset untouched rather than
            # crashing this page.
            pass


    # ========================================================
    # SEARCH
    # ========================================================

    if search:

        search_query = (
            Q(reference_number__icontains=search)
            |
            Q(
                folio__booking__guest__full_name__icontains=
                search
            )
            |
            Q(
                folio__booking__guest__email__icontains=
                search
            )
            |
            Q(
                folio__booking__room_unit__room_number__icontains=
                search
            )
        )

        # If BillingPayment has an ID/reference-like field,
        # the normal reference_number search above handles it.

        payments = payments.filter(
            search_query
        )


    # ========================================================
    # PAYMENT METHOD FILTER
    # ========================================================

    if method_filter:

        payments = payments.filter(
            method__iexact=method_filter
        )


    # ========================================================
    # DATE FILTER
    # ========================================================

    if date_filter:

        try:

            selected_date = (
                timezone.datetime.strptime(
                    date_filter,
                    "%Y-%m-%d",
                ).date()
            )

            payments = payments.filter(
                received_at__date=selected_date
            )

        except ValueError:

            date_filter = ""


    # ========================================================
    # MONTH FILTER
    # ========================================================

    elif month_filter:

        try:

            selected_year, selected_month = (
                month_filter.split("-")
            )

            payments = payments.filter(
                received_at__year=int(selected_year),
                received_at__month=int(selected_month),
            )

        except (
            ValueError,
            TypeError,
        ):

            month_filter = ""


    # ========================================================
    # SUMMARY
    # ========================================================

    total_transactions = payments.count()

    total_received = (
        payments.aggregate(
            total=Sum("amount")
        )["total"]
        or Decimal("0.00")
    )


    # ========================================================
    # PAYMENT METHOD TOTALS
    # ========================================================

    method_summary = list(
        payments
        .values("method")
        .annotate(
            total=Sum("amount"),
            count=Count("id"),
        )
        .order_by("-total")
    )


    # ========================================================
    # COMMON METHOD TOTALS
    # ========================================================

    cash_total = (
        payments
        .filter(method__iexact="cash")
        .aggregate(total=Sum("amount"))
        ["total"]
        or Decimal("0.00")
    )

    card_total = (
        payments
        .filter(method__iexact="card")
        .aggregate(total=Sum("amount"))
        ["total"]
        or Decimal("0.00")
    )

    upi_total = (
        payments
        .filter(method__iexact="upi")
        .aggregate(total=Sum("amount"))
        ["total"]
        or Decimal("0.00")
    )


    # ========================================================
    # BUILD PAYMENT ROWS
    # ========================================================

    payment_rows = []

    for payment in payments:

        folio = getattr(
            payment,
            "folio",
            None,
        )

        booking = (
            getattr(
                folio,
                "booking",
                None,
            )
            if folio
            else None
        )

        guest = (
            getattr(
                booking,
                "guest",
                None,
            )
            if booking
            else None
        )

        room = (
            getattr(
                booking,
                "room",
                None,
            )
            if booking
            else None
        )

        room_unit = (
            getattr(
                booking,
                "room_unit",
                None,
            )
            if booking
            else None
        )

        received_by = getattr(
            payment,
            "received_by",
            None,
        )


        # ----------------------------------------------------
        # RECEIVER NAME
        # ----------------------------------------------------

        receiver_name = "ΓÇö"

        if received_by:

            receiver_name = (
                getattr(
                    received_by,
                    "name",
                    None,
                )
                or
                " ".join(
                    filter(
                        None,
                        [
                            getattr(
                                received_by,
                                "first_name",
                                "",
                            ),
                            getattr(
                                received_by,
                                "last_name",
                                "",
                            ),
                        ],
                    )
                ).strip()
                or
                str(received_by)
            )


        # ----------------------------------------------------
        # SAFE DATETIME
        # ----------------------------------------------------

        received_at = getattr(
            payment,
            "received_at",
            None,
        )

        if received_at:

            if timezone.is_naive(
                received_at
            ):

                received_at = (
                    timezone.make_aware(
                        received_at,
                        timezone.get_current_timezone(),
                    )
                )

            received_at = timezone.localtime(
                received_at
            )


        payment_rows.append({

            "id":
                payment.pk,

            "reference_number":
                getattr(
                    payment,
                    "reference_number",
                    "",
                )
                or
                f"PAY-{payment.pk}",

            "guest_name": (
                getattr(
                    guest,
                    "full_name",
                    "",
                )
                if guest
                else ""
            )
            or
            "Walk-in Guest",

            "guest_email": (
                getattr(
                    guest,
                    "email",
                    "",
                )
                if guest
                else ""
            ),

            "room_number": (
                getattr(
                    room_unit,
                    "room_number",
                    "",
                )
                if room_unit
                else ""
            )
            or
            "ΓÇö",

            "room_type": (
                getattr(
                    room,
                    "room_type",
                    "",
                )
                if room
                else ""
            )
            or
            "ΓÇö",

            "amount":
                getattr(
                    payment,
                    "amount",
                    Decimal("0.00"),
                ),

            "method":
                getattr(
                    payment,
                    "method",
                    "",
                )
                or
                "Unknown",

            "received_by":
                receiver_name,

            "received_at":
                received_at,

            "note":
                getattr(
                    payment,
                    "note",
                    "",
                )
                or
                "",

        })


    # ========================================================
    # CONTEXT
    # ========================================================

    context = {

        "staff":
            staff,

        "hotel":
            hotel,

        "payments":
            payment_rows,

        "total_transactions":
            total_transactions,

        "total_received":
            total_received,

        "cash_total":
            cash_total,

        "card_total":
            card_total,

        "upi_total":
            upi_total,

        "method_summary":
            method_summary,

        "search":
            search,

        "method_filter":
            method_filter,

        "date_filter":
            date_filter,

        "month_filter":
            month_filter,

        # Do not use timezone.localdate() here.
        # Your project contains legacy naive datetime data.
        "today":
            timezone.now().date(),
    }


    return render(
        request,
        "accountant/payments.html",
        context,
    )





# ============================================================
# ACCOUNTANT - COLLECTIONS
# ============================================================

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache


@staff_login_required
@never_cache
@login_required
def accountant_collections(request):

    # ========================================================
    # STAFF
    # ========================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "department",
                "hotel",
            )
            .get(pk=staff_id)
        )

    except Staff.DoesNotExist:

        request.session.flush()

        return redirect("staff_login")


    hotel = staff.hotel


    # ========================================================
    # FILTERS
    # ========================================================

    search = (
        request.GET.get("search", "") or ""
    ).strip()

    status_filter = (
        request.GET.get("status", "") or ""
    ).strip().lower()

    date_filter = (
        request.GET.get("date", "") or ""
    ).strip()

    month_filter = (
        request.GET.get("month", "") or ""
    ).strip()


    # ========================================================
    # INVOICES
    #
    # IMPORTANT:
    # Replace Invoice below with the SAME invoice model used
    # inside your existing accountant_invoices() function.
    # ========================================================

    invoices = (
        Invoice.objects
        .select_related(
            "folio",
            "folio__booking",
            "folio__booking__guest",
            "folio__booking__room",
            "folio__booking__room_unit",
        )
        .order_by("-generated_at")
    )


    # ========================================================
    # HOTEL FILTER
    #
    # Use the same hotel-filter relationship already working
    # inside accountant_invoices().
    # ========================================================

    invoice_fields = {
        field.name
        for field in Invoice._meta.get_fields()
    }

    if "hotel" in invoice_fields:

        invoices = invoices.filter(
            hotel=hotel
        )

    else:

        try:
            invoices = invoices.filter(
                folio__booking__hotel=hotel
            )

        except Exception:
            pass


    # ========================================================
    # SEARCH
    # ========================================================

    if search:

        invoices = invoices.filter(

            Q(
                invoice_number__icontains=search
            )

            |

            Q(
                folio__booking__guest__full_name__icontains=
                search
            )

            |

            Q(
                folio__booking__guest__email__icontains=
                search
            )

            |

            Q(
                folio__booking__room_unit__room_number__icontains=
                search
            )

        )


    # ========================================================
    # DATE FILTER
    # ========================================================

    if date_filter:

        try:

            selected_date = (
                timezone.datetime.strptime(
                    date_filter,
                    "%Y-%m-%d",
                ).date()
            )

            invoices = invoices.filter(
                generated_at__date=selected_date
            )

        except ValueError:

            date_filter = ""


    # ========================================================
    # MONTH FILTER
    # ========================================================

    elif month_filter:

        try:

            selected_year, selected_month = (
                month_filter.split("-")
            )

            invoices = invoices.filter(
                generated_at__year=int(
                    selected_year
                ),
                generated_at__month=int(
                    selected_month
                ),
            )

        except (
            ValueError,
            TypeError,
        ):

            month_filter = ""


    # ========================================================
    # COLLECTION ROWS
    # ========================================================

    collection_rows = []

    total_billed = Decimal("0.00")
    total_collected = Decimal("0.00")
    total_outstanding = Decimal("0.00")

    paid_count = 0
    partial_count = 0
    pending_count = 0


    for invoice in invoices:

        folio = getattr(
            invoice,
            "folio",
            None,
        )

        booking = (
            getattr(
                folio,
                "booking",
                None,
            )
            if folio
            else None
        )

        guest = (
            getattr(
                booking,
                "guest",
                None,
            )
            if booking
            else None
        )

        room = (
            getattr(
                booking,
                "room",
                None,
            )
            if booking
            else None
        )

        room_unit = (
            getattr(
                booking,
                "room_unit",
                None,
            )
            if booking
            else None
        )


        # ====================================================
        # INVOICE TOTAL
        # ====================================================

        invoice_total = (
            getattr(
                invoice,
                "grand_total",
                Decimal("0.00"),
            )
            or Decimal("0.00")
        )


        # ====================================================
        # PAYMENTS FOR THIS FOLIO
        #
        # BillingPayment is already part of your accounting
        # payment system.
        # ====================================================

        paid_amount = Decimal("0.00")

        if folio:

            paid_amount = (
                BillingPayment.objects
                .filter(
                    folio=folio
                )
                .aggregate(
                    total=Sum("amount")
                )
                .get("total")
                or Decimal("0.00")
            )


        # Never allow negative outstanding balance.

        outstanding = (
            invoice_total
            -
            paid_amount
        )

        if outstanding < Decimal("0.00"):
            outstanding = Decimal("0.00")


        # ====================================================
        # COMPUTED COLLECTION STATUS
        # ====================================================

        if (
            invoice_total > Decimal("0.00")
            and
            paid_amount >= invoice_total
        ):

            collection_status = "paid"
            paid_count += 1

        elif paid_amount > Decimal("0.00"):

            collection_status = "partial"
            partial_count += 1

        else:

            collection_status = "pending"
            pending_count += 1


        # ====================================================
        # STATUS FILTER
        # ====================================================

        if (
            status_filter
            and
            collection_status != status_filter
        ):
            continue


        # ====================================================
# SAFE GENERATED DATE
# ====================================================

        generated_at = safe_localtime(
              getattr(
                invoice,
                 "generated_at",
                 None,
             )
        )

        # ====================================================
        # COLLECTION PERCENT
        # ====================================================

        collection_percent = Decimal("0.00")

        if invoice_total > Decimal("0.00"):

            collection_percent = (
                paid_amount
                /
                invoice_total
                *
                Decimal("100")
            )

            if collection_percent > Decimal("100"):
                collection_percent = Decimal("100")


        # ====================================================
        # TOTALS
        # ====================================================

        total_billed += invoice_total

        total_collected += min(
            paid_amount,
            invoice_total,
        )

        total_outstanding += outstanding


        # ====================================================
        # ROW
        # ====================================================

        collection_rows.append({

            "invoice_id":
                invoice.pk,

            "invoice_number":
                getattr(
                    invoice,
                    "invoice_number",
                    "",
                )
                or
                f"INV-{invoice.pk}",

            "guest_name": (
                getattr(
                    guest,
                    "full_name",
                    "",
                )
                if guest
                else ""
            )
            or
            "Walk-in Guest",

            "guest_email": (
                getattr(
                    guest,
                    "email",
                    "",
                )
                if guest
                else ""
            ),

            "room_number": (
                getattr(
                    room_unit,
                    "room_number",
                    "",
                )
                if room_unit
                else ""
            )
            or
            "ΓÇö",

            "room_type": (
                getattr(
                    room,
                    "room_type",
                    "",
                )
                if room
                else ""
            )
            or
            "ΓÇö",

            "invoice_total":
                invoice_total,

            "paid_amount":
                paid_amount,

            "outstanding":
                outstanding,

            "collection_percent":
                collection_percent,

            "status":
                collection_status,

            "generated_at":
                generated_at,

        })


    # ========================================================
    # OVERALL COLLECTION RATE
    # ========================================================

    collection_rate = Decimal("0.00")

    if total_billed > Decimal("0.00"):

        collection_rate = (
            total_collected
            /
            total_billed
            *
            Decimal("100")
        )


    # ========================================================
    # CONTEXT
    # ========================================================

    context = {

        "staff":
            staff,

        "hotel":
            hotel,

        "collections":
            collection_rows,

        "total_billed":
            total_billed,

        "total_collected":
            total_collected,

        "total_outstanding":
            total_outstanding,

        "collection_rate":
            collection_rate,

        "paid_count":
            paid_count,

        "partial_count":
            partial_count,

        "pending_count":
            pending_count,

        "search":
            search,

        "status_filter":
            status_filter,

        "date_filter":
            date_filter,

        "month_filter":
            month_filter,

        # Avoid timezone.localdate() because your existing
        # database contains legacy naive datetimes.
        "today":
            timezone.now().date(),
    }


    return render(
        request,
        "accountant/collections.html",
        context,
    )




from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache

from hotel.models import Staff, Payroll


# ============================================================
# MY PAYROLL
# ============================================================

@never_cache
@staff_login_required
@login_required
def accountant_my_payroll(request):
    """
    My Payroll page.

    Shows payroll records ONLY for the currently logged-in staff member.

    Features:
    - Current/selected payroll
    - Month/year filtering
    - Salary summary
    - Earnings breakdown
    - Deduction breakdown
    - Payment status
    - Payroll history
    - Payslip access
    """

    # ========================================================
    # LOGGED-IN STAFF
    # ========================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:

        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
                "user",
            )
            .get(
                id=staff_id
            )
        )

    except Staff.DoesNotExist:

        return redirect("staff_login")


    hotel = staff.hotel

    if not hotel:
        return redirect("staff_login")


    # ========================================================
    # PAYROLL HISTORY
    #
    # SECURITY:
    # Only payroll belonging to logged-in employee.
    # ========================================================

    payroll_history = (
        Payroll.objects
        .filter(
            staff=staff,
            hotel=hotel,
        )
        .select_related(
            "staff",
            "paid_by",
        )
        .order_by(
            "-year",
            "-month",
        )
    )


    # ========================================================
    # FILTER
    # ========================================================

    selected_month = request.GET.get("month")
    selected_year = request.GET.get("year")


    # Convert month
    if selected_month:

        try:
            selected_month = int(selected_month)

        except (TypeError, ValueError):
            selected_month = None


    # Convert year
    if selected_year:

        try:
            selected_year = int(selected_year)

        except (TypeError, ValueError):
            selected_year = None


    # ========================================================
    # SELECTED PAYROLL
    # ========================================================

    selected_payroll = None


    if selected_month and selected_year:

        selected_payroll = (
            payroll_history
            .filter(
                month=selected_month,
                year=selected_year,
            )
            .first()
        )


    # If nothing explicitly selected,
    # display newest payroll record.

    if selected_payroll is None:

        selected_payroll = payroll_history.first()


    # ========================================================
    # DEFAULT VALUES
    # ========================================================

    basic_salary = Decimal("0.00")

    overtime_amount = Decimal("0.00")

    bonus = Decimal("0.00")

    incentive = Decimal("0.00")

    gross_salary = Decimal("0.00")


    normal_deduction = Decimal("0.00")

    pf_amount = Decimal("0.00")

    esi_amount = Decimal("0.00")

    tax_deduction = Decimal("0.00")

    loan_deduction = Decimal("0.00")

    total_deductions = Decimal("0.00")


    net_salary = Decimal("0.00")


    # ========================================================
    # CALCULATE SELECTED PAYROLL
    # ========================================================

    if selected_payroll:

        basic_salary = (
            selected_payroll.basic_salary
            or Decimal("0.00")
        )

        overtime_amount = (
            selected_payroll.overtime_amount
            or Decimal("0.00")
        )

        bonus = (
            selected_payroll.bonus
            or Decimal("0.00")
        )

        incentive = (
            selected_payroll.incentive
            or Decimal("0.00")
        )


        # ----------------------------------------------------
        # TOTAL EARNINGS
        # ----------------------------------------------------

        gross_salary = (
            basic_salary
            + overtime_amount
            + bonus
            + incentive
        )


        # ----------------------------------------------------
        # DEDUCTIONS
        # ----------------------------------------------------

        normal_deduction = (
            selected_payroll.deductions
            or Decimal("0.00")
        )

        pf_amount = (
            selected_payroll.pf_amount
            or Decimal("0.00")
        )

        esi_amount = (
            selected_payroll.esi_amount
            or Decimal("0.00")
        )

        tax_deduction = (
            selected_payroll.tax_deduction
            or Decimal("0.00")
        )

        loan_deduction = (
            selected_payroll.loan_deduction
            or Decimal("0.00")
        )


        total_deductions = (
            normal_deduction
            + pf_amount
            + esi_amount
            + tax_deduction
            + loan_deduction
        )


        # ----------------------------------------------------
        # NET SALARY
        # ----------------------------------------------------

        net_salary = (
            selected_payroll.net_salary
            or Decimal("0.00")
        )


    # ========================================================
    # MONTHS
    # ========================================================

    months = [

        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),

        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),

    ]


    # ========================================================
    # AVAILABLE YEARS
    # ========================================================

    years = (
        payroll_history
        .values_list(
            "year",
            flat=True,
        )
        .distinct()
        .order_by("-year")
    )


    # ========================================================
    # MONTH NAME
    # ========================================================

    selected_month_name = ""

    if selected_payroll:

        for month_number, month_name in months:

            if month_number == selected_payroll.month:

                selected_month_name = month_name

                break


    # ========================================================
    # CONTEXT
    # ========================================================

    context = {

        # Employee
        "staff":
            staff,

        "hotel":
            hotel,


        # Current payroll
        "payroll":
            selected_payroll,

        "selected_payroll":
            selected_payroll,


        # History
        "payroll_history":
            payroll_history,


        # Filters
        "months":
            months,

        "years":
            years,

        "selected_month":
            (
                selected_payroll.month
                if selected_payroll
                else selected_month
            ),

        "selected_year":
            (
                selected_payroll.year
                if selected_payroll
                else selected_year
            ),

        "selected_month_name":
            selected_month_name,


        # Earnings
        "basic_salary":
            basic_salary,

        "overtime_amount":
            overtime_amount,

        "bonus":
            bonus,

        "incentive":
            incentive,

        "gross_salary":
            gross_salary,


        # Deductions
        "normal_deduction":
            normal_deduction,

        "pf_amount":
            pf_amount,

        "esi_amount":
            esi_amount,

        "tax_deduction":
            tax_deduction,

        "loan_deduction":
            loan_deduction,

        "total_deductions":
            total_deductions,


        # Final salary
        "net_salary":
            net_salary,
    }


    # ========================================================
    # RENDER
    # ========================================================

    return render(
        request,
        "accountant/my_payroll.html",
        context,
    )





from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Q, Sum, Count
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache

import csv


# ============================================================
# ACCOUNTANT REPORT HELPERS
# ============================================================

def _report_decimal(value):
    if value is None:
        return Decimal("0.00")

    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _get_accountant_staff(request):
    """
    Return the currently logged-in staff member.

    IMPORTANT:
    Uses the same session structure as the rest of the
    accountant module.
    """

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return None

    try:
        return (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(pk=staff_id)
        )

    except Staff.DoesNotExist:
        return None


def _parse_report_dates(request):

    today = timezone.now().date()

    period = (
        request.GET.get("period", "month")
        or "month"
    ).strip().lower()

    start_string = (
        request.GET.get("start_date", "")
        or ""
    ).strip()

    end_string = (
        request.GET.get("end_date", "")
        or ""
    ).strip()

    # --------------------------------------------------------
    # CUSTOM RANGE
    # --------------------------------------------------------

    if start_string and end_string:

        try:

            start_date = datetime.strptime(
                start_string,
                "%Y-%m-%d",
            ).date()

            end_date = datetime.strptime(
                end_string,
                "%Y-%m-%d",
            ).date()

            if start_date > end_date:
                start_date, end_date = end_date, start_date

            return start_date, end_date, "custom"

        except ValueError:
            pass

    # --------------------------------------------------------
    # PREDEFINED RANGE
    # --------------------------------------------------------

    if period == "today":

        start_date = today
        end_date = today

    elif period == "week":

        start_date = today - timedelta(
            days=today.weekday()
        )

        end_date = today

    elif period == "year":

        start_date = today.replace(
            month=1,
            day=1,
        )

        end_date = today

    else:

        period = "month"

        start_date = today.replace(
            day=1
        )

        end_date = today

    return start_date, end_date, period


def _safe_model_fields(model):

    return {
        field.name
        for field in model._meta.get_fields()
    }


def _filter_hotel(queryset, model, hotel):

    fields = _safe_model_fields(model)

    if "hotel" in fields:
        return queryset.filter(
            hotel=hotel
        )

    return queryset





@staff_login_required
@never_cache
def accountant_reports(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    hotel = staff.hotel

    start_date, end_date, period = (
        _parse_report_dates(request)
    )

    # ========================================================
    # REVENUE
    # ========================================================

    payments = Payment.objects.all()

    payment_fields = _safe_model_fields(Payment)

    if "hotel" in payment_fields:
        payments = payments.filter(
            hotel=hotel
        )

    # Use date filtering only when field exists.
    if "created_at" in payment_fields:

        payments = payments.filter(
            created_at__date__range=(
                start_date,
                end_date,
            )
        )

    elif "payment_date" in payment_fields:

        payments = payments.filter(
            payment_date__range=(
                start_date,
                end_date,
            )
        )

    revenue_field = None

    for candidate in [
        "total_amount",
        "amount",
        "paid_amount",
    ]:
        if candidate in payment_fields:
            revenue_field = candidate
            break

    total_revenue = Decimal("0.00")

    if revenue_field:

        total_revenue = (
            payments.aggregate(
                total=Sum(revenue_field)
            )["total"]
            or Decimal("0.00")
        )

    # ========================================================
    # EXPENSES
    # ========================================================

    total_expenses = Decimal("0.00")
    expense_count = 0

    try:

        expenses = Expense.objects.all()

        expense_fields = _safe_model_fields(
            Expense
        )

        if "hotel" in expense_fields:
            expenses = expenses.filter(
                hotel=hotel
            )

        date_field = None

        for candidate in [
            "expense_date",
            "date",
            "created_at",
        ]:

            if candidate in expense_fields:
                date_field = candidate
                break

        if date_field:

            if date_field == "created_at":

                expenses = expenses.filter(
                    created_at__date__range=(
                        start_date,
                        end_date,
                    )
                )

            else:

                expenses = expenses.filter(
                    **{
                        f"{date_field}__range": (
                            start_date,
                            end_date,
                        )
                    }
                )

        amount_field = None

        for candidate in [
            "amount",
            "total_amount",
            "expense_amount",
        ]:

            if candidate in expense_fields:
                amount_field = candidate
                break

        if amount_field:

            total_expenses = (
                expenses.aggregate(
                    total=Sum(amount_field)
                )["total"]
                or Decimal("0.00")
            )

        expense_count = expenses.count()

    except Exception:

        total_expenses = Decimal("0.00")
        expense_count = 0

    # ========================================================
    # PAYROLL
    # ========================================================

    payrolls = Payroll.objects.all()

    payroll_fields = _safe_model_fields(
        Payroll
    )

    if "hotel" in payroll_fields:

        payrolls = payrolls.filter(
            hotel=hotel
        )

    elif "staff" in payroll_fields:

        payrolls = payrolls.filter(
            staff__hotel=hotel
        )

    if "month" in payroll_fields:

        if (
            start_date.year == end_date.year
            and
            start_date.month == end_date.month
        ):

            payrolls = payrolls.filter(
                year=start_date.year,
                month=start_date.month,
            )

    total_payroll = (
        payrolls.aggregate(
            total=Sum("net_salary")
        )["total"]
        or Decimal("0.00")
    )

    # ========================================================
    # PROFIT
    # ========================================================

    total_revenue = _report_decimal(
        total_revenue
    )

    total_expenses = _report_decimal(
        total_expenses
    )

    total_payroll = _report_decimal(
        total_payroll
    )

    operating_cost = (
        total_expenses
        +
        total_payroll
    )

    net_result = (
        total_revenue
        -
        operating_cost
    )

    context = {

        "staff":
            staff,

        "hotel":
            hotel,

        "period":
            period,

        "start_date":
            start_date,

        "end_date":
            end_date,

        "total_revenue":
            total_revenue,

        "total_expenses":
            total_expenses,

        "total_payroll":
            total_payroll,

        "operating_cost":
            operating_cost,

        "net_result":
            net_result,

        "payment_count":
            payments.count(),

        "expense_count":
            expense_count,

        "payroll_count":
            payrolls.count(),
    }

    return render(
        request,
        "accountant/reports/index.html",
        context,
    )




@staff_login_required
@never_cache
def accountant_revenue_report(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    hotel = staff.hotel

    start_date, end_date, period = (
        _parse_report_dates(request)
    )

    payments = Payment.objects.all()

    fields = _safe_model_fields(Payment)

    if "hotel" in fields:
        payments = payments.filter(
            hotel=hotel
        )

    if "created_at" in fields:

        payments = payments.filter(
            created_at__date__range=(
                start_date,
                end_date,
            )
        )

    elif "payment_date" in fields:

        payments = payments.filter(
            payment_date__range=(
                start_date,
                end_date,
            )
        )

    payments = payments.order_by("-id")

    amount_field = None

    for candidate in [
        "total_amount",
        "amount",
        "paid_amount",
    ]:

        if candidate in fields:
            amount_field = candidate
            break

    total_revenue = Decimal("0.00")

    if amount_field:

        total_revenue = (
            payments.aggregate(
                total=Sum(amount_field)
            )["total"]
            or Decimal("0.00")
        )

    context = {

        "staff": staff,
        "hotel": hotel,

        "payments": payments,

        "total_revenue": total_revenue,

        "total_transactions":
            payments.count(),

        "start_date": start_date,
        "end_date": end_date,
        "period": period,
    }

    return render(
        request,
        "accountant/reports/revenue.html",
        context,
    )




@staff_login_required
@never_cache
def accountant_expense_report_page(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    start_date, end_date, period = (
        _parse_report_dates(request)
    )

    context = {

        "staff":
            staff,

        "hotel":
            staff.hotel,

        "start_date":
            start_date,

        "end_date":
            end_date,

        "period":
            period,

        # Existing Expense module URLs
        "expense_page_url":
            "expense_report",

        "expense_export_url":
            "expense_export_csv",
    }

    return render(
        request,
        "accountant/reports/expense.html",
        context,
    )




@staff_login_required
@never_cache
def accountant_payroll_report(request):

    # ============================================================
    # LOGGED-IN ACCOUNTANT
    # ============================================================

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    hotel = staff.hotel


    # ============================================================
    # REPORT DATE RANGE
    # ============================================================

    start_date, end_date, period = _parse_report_dates(request)


    # ============================================================
    # FILTER VALUES
    # ============================================================

    selected_department = (
        request.GET.get("department", "")
        .strip()
    )

    selected_status = (
        request.GET.get("status", "")
        .strip()
        .lower()
    )


    # ============================================================
    # BASE QUERYSET
    # ============================================================

    payrolls = (
        Payroll.objects
        .select_related(
            "staff",
            "staff__department",
        )
        .prefetch_related(
            "line_items",
        )
        .filter(
            staff__hotel=hotel
        )
    )


    # ============================================================
    # DATE FILTER
    #
    # Payroll records use month + year.
    # Therefore build a Q expression containing every month
    # inside the requested report range.
    # ============================================================

    month_filter = Q()

    current_year = start_date.year
    current_month = start_date.month

    while (
        current_year < end_date.year
        or (
            current_year == end_date.year
            and current_month <= end_date.month
        )
    ):

        month_filter |= Q(
            year=current_year,
            month=current_month,
        )

        current_month += 1

        if current_month > 12:
            current_month = 1
            current_year += 1


    payrolls = payrolls.filter(
        month_filter
    )


    # ============================================================
    # DEPARTMENT FILTER
    # ============================================================

    if selected_department:

        payrolls = payrolls.filter(
            staff__department_id=selected_department
        )


    # ============================================================
    # STATUS FILTER
    #
    # IMPORTANT:
    # Your model uses:
    #
    #   "Paid"
    #   "Unpaid"
    #
    # It is NOT a boolean field.
    # ============================================================

    if selected_status == "paid":

        payrolls = payrolls.filter(
            paid_status__iexact="Paid"
        )

    elif selected_status in ["pending", "unpaid"]:

        payrolls = payrolls.filter(
            paid_status__iexact="Unpaid"
        )


    # ============================================================
    # ORDERING
    # ============================================================

    payrolls = payrolls.order_by(
        "-year",
        "-month",
        "-id",
    )


    # ============================================================
    # NUMERIC DATABASE TOTALS
    #
    # ONLY numeric DB columns belong inside Sum().
    #
    # DO NOT put:
    #
    #   custom_earnings
    #   custom_deductions
    #
    # here because they are JSON fields.
    # ============================================================

    summary = payrolls.aggregate(

        basic_salary=Sum(
            "basic_salary"
        ),

        overtime_amount=Sum(
            "overtime_amount"
        ),

        bonus=Sum(
            "bonus"
        ),

        incentive=Sum(
            "incentive"
        ),

        deductions=Sum(
            "deductions"
        ),

        pf_amount=Sum(
            "pf_amount"
        ),

        esi_amount=Sum(
            "esi_amount"
        ),

        loan_deduction=Sum(
            "loan_deduction"
        ),

        tax_deduction=Sum(
            "tax_deduction"
        ),

        net_salary=Sum(
            "net_salary"
        ),
    )


    ZERO = Decimal("0.00")


    # ============================================================
    # SAFE DECIMAL HELPER
    # ============================================================

    def safe_decimal(value):

        if value in (
            None,
            "",
        ):
            return ZERO

        try:
            return Decimal(str(value))

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):
            return ZERO


    # ============================================================
    # NORMAL NUMERIC TOTALS
    # ============================================================

    total_basic_salary = safe_decimal(
        summary.get("basic_salary")
    )

    total_overtime = safe_decimal(
        summary.get("overtime_amount")
    )

    total_bonus = safe_decimal(
        summary.get("bonus")
    )

    total_incentive = safe_decimal(
        summary.get("incentive")
    )

    base_deductions = safe_decimal(
        summary.get("deductions")
    )

    total_pf = safe_decimal(
        summary.get("pf_amount")
    )

    total_esi = safe_decimal(
        summary.get("esi_amount")
    )

    total_loan_deduction = safe_decimal(
        summary.get("loan_deduction")
    )

    total_tax = safe_decimal(
        summary.get("tax_deduction")
    )

    total_payroll = safe_decimal(
        summary.get("net_salary")
    )


    # ============================================================
    # JSON TOTALS
    #
    # custom_earnings and custom_deductions are lists like:
    #
    # [
    #     {"label": "Food Allowance", "amount": 1000},
    #     {"label": "Special Bonus", "amount": 500}
    # ]
    #
    # PostgreSQL cannot SUM the whole JSON object.
    # Calculate the amount values in Python.
    # ============================================================

    total_custom_earnings = ZERO
    total_custom_deductions = ZERO


    # ============================================================
    # ALSO PREPARE DISPLAY VALUES FOR EACH PAYROLL
    # ============================================================

    payroll_list = list(payrolls)


    for payroll in payroll_list:

        custom_earnings_total = ZERO
        custom_deductions_total = ZERO


        # --------------------------------------------------------
        # CUSTOM EARNINGS
        # --------------------------------------------------------

        custom_earnings = (
            payroll.custom_earnings
            or []
        )

        if isinstance(
            custom_earnings,
            list
        ):

            for item in custom_earnings:

                if isinstance(item, dict):

                    custom_earnings_total += (
                        safe_decimal(
                            item.get(
                                "amount",
                                0
                            )
                        )
                    )


        # --------------------------------------------------------
        # CUSTOM DEDUCTIONS
        # --------------------------------------------------------

        custom_deductions = (
            payroll.custom_deductions
            or []
        )

        if isinstance(
            custom_deductions,
            list
        ):

            for item in custom_deductions:

                if isinstance(item, dict):

                    custom_deductions_total += (
                        safe_decimal(
                            item.get(
                                "amount",
                                0
                            )
                        )
                    )


        # --------------------------------------------------------
        # GLOBAL REPORT TOTALS
        # --------------------------------------------------------

        total_custom_earnings += (
            custom_earnings_total
        )

        total_custom_deductions += (
            custom_deductions_total
        )


        # --------------------------------------------------------
        # EXTRA EARNINGS FOR THIS PAYROLL
        # --------------------------------------------------------

        payroll.report_extra_earnings = (

            safe_decimal(
                payroll.overtime_amount
            )

            +

            safe_decimal(
                payroll.bonus
            )

            +

            safe_decimal(
                payroll.incentive
            )

            +

            custom_earnings_total
        )


        # --------------------------------------------------------
        # TOTAL DEDUCTIONS FOR THIS PAYROLL
        # --------------------------------------------------------

        payroll.report_total_deductions = (

            safe_decimal(
                payroll.deductions
            )

            +

            safe_decimal(
                payroll.pf_amount
            )

            +

            safe_decimal(
                payroll.esi_amount
            )

            +

            safe_decimal(
                payroll.loan_deduction
            )

            +

            safe_decimal(
                payroll.tax_deduction
            )

            +

            custom_deductions_total
        )


        # --------------------------------------------------------
        # NORMALIZED STATUS FOR TEMPLATE
        # --------------------------------------------------------

        payroll.report_status = (

            "paid"

            if str(
                payroll.paid_status
            ).lower() == "paid"

            else "pending"
        )


    # ============================================================
    # TOTAL EXTRA EARNINGS / ALLOWANCES
    # ============================================================

    total_allowances = (

        total_overtime

        +

        total_bonus

        +

        total_incentive

        +

        total_custom_earnings
    )


    # ============================================================
    # TOTAL DEDUCTIONS
    #
    # This gives the complete payroll deduction amount.
    # ============================================================

    total_deductions = (

        base_deductions

        +

        total_pf

        +

        total_esi

        +

        total_loan_deduction

        +

        total_tax

        +

        total_custom_deductions
    )


    # ============================================================
    # PAID / UNPAID QUERYSETS
    # ============================================================

    paid_queryset = payrolls.filter(
        paid_status__iexact="Paid"
    )

    pending_queryset = payrolls.filter(
        paid_status__iexact="Unpaid"
    )


    # ============================================================
    # STATUS COUNTS
    # ============================================================

    paid_count = (
        paid_queryset.count()
    )

    pending_count = (
        pending_queryset.count()
    )


    # ============================================================
    # PAID PAYROLL VALUE
    # ============================================================

    paid_summary = (
        paid_queryset.aggregate(
            total=Sum(
                "net_salary"
            )
        )
    )

    paid_payroll = safe_decimal(
        paid_summary.get(
            "total"
        )
    )


    # ============================================================
    # PENDING PAYROLL VALUE
    # ============================================================

    pending_summary = (
        pending_queryset.aggregate(
            total=Sum(
                "net_salary"
            )
        )
    )

    pending_payroll = safe_decimal(
        pending_summary.get(
            "total"
        )
    )


    # ============================================================
    # COUNTS
    # ============================================================

    payroll_count = (
        payrolls.count()
    )

    employee_count = (
        payrolls
        .values(
            "staff_id"
        )
        .distinct()
        .count()
    )


    # ============================================================
    # DEPARTMENTS
    # ============================================================

    departments = (
        Department.objects
        .filter(
            staff__hotel=hotel
        )
        .distinct()
        .order_by(
            "name"
        )
    )


    # ============================================================
    # PAYROLL TREND
    # ============================================================

    trend_rows = (

        payrolls

        .values(
            "year",
            "month",
        )

        .annotate(
            total=Sum(
                "net_salary"
            )
        )

        .order_by(
            "year",
            "month",
        )
    )


    month_names = [
        "",
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]


    chart_labels = []
    chart_values = []


    for row in trend_rows:

        try:

            month_number = int(
                row["month"]
            )

        except (
            TypeError,
            ValueError,
        ):

            month_number = 0


        if 1 <= month_number <= 12:

            label = (
                f"{month_names[month_number]} "
                f"{row['year']}"
            )

        else:

            label = str(
                row["year"]
            )


        chart_labels.append(
            label
        )

        chart_values.append(
            float(
                safe_decimal(
                    row["total"]
                )
            )
        )


    # ============================================================
    # STATUS CHART
    # ============================================================

    status_labels = [
        "Paid",
        "Pending",
    ]

    status_values = [
        paid_count,
        pending_count,
    ]


    # ============================================================
    # CONTEXT
    # ============================================================

    context = {

        # --------------------------------------------------------
        # ACCOUNT
        # --------------------------------------------------------

        "staff":
            staff,

        "hotel":
            hotel,


        # --------------------------------------------------------
        # FILTER
        # --------------------------------------------------------

        "period":
            period,

        "start_date":
            start_date,

        "end_date":
            end_date,

        "selected_department":
            selected_department,

        "selected_status":
            selected_status,

        "departments":
            departments,


        # --------------------------------------------------------
        # PAYROLL RECORDS
        # --------------------------------------------------------

        "payrolls":
            payroll_list,

        "payroll_count":
            payroll_count,

        "employee_count":
            employee_count,


        # --------------------------------------------------------
        # MAIN TOTALS
        # --------------------------------------------------------

        "total_payroll":
            total_payroll,

        "paid_payroll":
            paid_payroll,

        "pending_payroll":
            pending_payroll,


        # --------------------------------------------------------
        # EARNINGS
        # --------------------------------------------------------

        "total_basic_salary":
            total_basic_salary,

        "total_allowances":
            total_allowances,

        "total_overtime":
            total_overtime,

        "total_bonus":
            total_bonus,

        "total_incentive":
            total_incentive,

        "total_custom_earnings":
            total_custom_earnings,


        # --------------------------------------------------------
        # DEDUCTIONS
        # --------------------------------------------------------

        "total_deductions":
            total_deductions,

        "base_deductions":
            base_deductions,

        "total_pf":
            total_pf,

        "total_esi":
            total_esi,

        "total_loan_deduction":
            total_loan_deduction,

        "total_tax":
            total_tax,

        "total_custom_deductions":
            total_custom_deductions,


        # --------------------------------------------------------
        # STATUS
        # --------------------------------------------------------

        "paid_count":
            paid_count,

        "pending_count":
            pending_count,

        "hold_count":
            0,


        # --------------------------------------------------------
        # CHART
        # --------------------------------------------------------

        "chart_labels":
            chart_labels,

        "chart_values":
            chart_values,

        "status_labels":
            status_labels,

        "status_values":
            status_values,
    }


    # ============================================================
    # RENDER
    # ============================================================

    return render(
        request,
        "accountant/reports/payroll.html",
        context,
    )



@staff_login_required
@never_cache
def accountant_tax_report(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    hotel = staff.hotel

    start_date, end_date, period = (
        _parse_report_dates(request)
    )

    payments = Payment.objects.all()

    fields = _safe_model_fields(Payment)

    if "hotel" in fields:
        payments = payments.filter(
            hotel=hotel
        )

    if "created_at" in fields:

        payments = payments.filter(
            created_at__date__range=(
                start_date,
                end_date,
            )
        )

    tax_field = None

    for candidate in [
        "tax_amount",
        "tax",
        "gst_amount",
        "gst",
    ]:

        if candidate in fields:
            tax_field = candidate
            break

    total_tax = Decimal("0.00")

    if tax_field:

        total_tax = (
            payments.aggregate(
                total=Sum(tax_field)
            )["total"]
            or Decimal("0.00")
        )

    context = {

        "staff":
            staff,

        "hotel":
            hotel,

        "payments":
            payments,

        "tax_field":
            tax_field,

        "total_tax":
            total_tax,

        "start_date":
            start_date,

        "end_date":
            end_date,

        "period":
            period,
    }

    return render(
        request,
        "accountant/reports/tax.html",
        context,
    )





@staff_login_required
@never_cache
def accountant_reports_export(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    report_type = (
        request.GET.get(
            "type",
            "payroll",
        )
        or "payroll"
    ).lower()

    start_date, end_date, period = (
        _parse_report_dates(request)
    )

    response = HttpResponse(
        content_type="text/csv"
    )

    response[
        "Content-Disposition"
    ] = (
        f'attachment; filename="'
        f'{report_type}_report_'
        f'{start_date}_to_{end_date}.csv"'
    )

    writer = csv.writer(response)

    if report_type == "payroll":

        payrolls = (
            Payroll.objects
            .select_related(
                "staff",
                "staff__department",
            )
            .filter(
                staff__hotel=staff.hotel
            )
            .order_by(
                "-year",
                "-month",
            )
        )

        writer.writerow([
            "Employee",
            "Department",
            "Year",
            "Month",
            "Basic Salary",
            "Allowances",
            "Deductions",
            "Net Salary",
            "Status",
        ])

        for payroll in payrolls:

            writer.writerow([

                payroll.staff.name,

                (
                    payroll.staff.department.name
                    if payroll.staff.department
                    else ""
                ),

                payroll.year,

                payroll.month,

                payroll.basic_salary,

                payroll.allowances,

                payroll.deductions,

                payroll.net_salary,

                (
                    "Paid"
                    if payroll.paid_status
                    else "Pending"
                ),
            ])

    else:

        writer.writerow([
            "Report",
            "Start Date",
            "End Date",
        ])

        writer.writerow([
            report_type.title(),
            start_date,
            end_date,
        ])

    return response






from datetime import datetime, timedelta, time

from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.decorators import staff_login_required

from .models import (
    Attendance,
    Shift,
    ShiftTemplate,
    LeaveRequest,
)


# ============================================================
# ACCOUNTANT - MY ATTENDANCE
# ============================================================

@staff_login_required
@never_cache
def accountant_my_attendance(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    today = timezone.now().date()

    # --------------------------------------------------------
    # SELECTED MONTH
    # --------------------------------------------------------

    month_value = (
        request.GET.get("month")
        or today.strftime("%Y-%m")
    )

    try:
        selected_date = datetime.strptime(
            month_value,
            "%Y-%m"
        ).date()

        selected_year = selected_date.year
        selected_month = selected_date.month

    except ValueError:

        selected_year = today.year
        selected_month = today.month

        month_value = today.strftime("%Y-%m")


    # --------------------------------------------------------
    # TODAY ATTENDANCE
    # --------------------------------------------------------

    today_attendance = (
        Attendance.objects
        .filter(
            staff=staff,
            date=today,
        )
        .first()
    )


    # --------------------------------------------------------
    # MONTH ATTENDANCE
    # --------------------------------------------------------

    attendance_records = (
        Attendance.objects
        .filter(
            staff=staff,
            date__year=selected_year,
            date__month=selected_month,
        )
        .order_by("-date")
    )


    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    present_count = attendance_records.filter(
        status="Present"
    ).count()

    late_count = attendance_records.filter(
        status="Late"
    ).count()

    half_day_count = attendance_records.filter(
        status="Half Day"
    ).count()

    absent_count = attendance_records.filter(
        status="Absent"
    ).count()

    leave_count = attendance_records.filter(
        status="Leave"
    ).count()


    overtime_total = (
        attendance_records.aggregate(
            total=Sum("overtime_hours")
        )["total"]
        or 0
    )


    # --------------------------------------------------------
    # WORKING HOURS
    # --------------------------------------------------------

    attendance_rows = []

    total_working_hours = 0

    for record in attendance_records:

        working_hours = 0

        if record.check_in and record.check_out:

            working_hours = round(
                (
                    record.check_out
                    -
                    record.check_in
                ).total_seconds() / 3600,
                2
            )

            total_working_hours += working_hours

        attendance_rows.append({
            "record": record,
            "working_hours": working_hours,
        })


    # --------------------------------------------------------
    # FACE DATA  (NEW)
    # --------------------------------------------------------

    descriptors = normalize_descriptors(staff.face_descriptor)


    context = {

        "staff": staff,
        "hotel": staff.hotel,

        "today": today,

        "today_attendance":
            today_attendance,

        "attendance_rows":
            attendance_rows,

        "present_count":
            present_count,

        "late_count":
            late_count,

        "half_day_count":
            half_day_count,

        "absent_count":
            absent_count,

        "leave_count":
            leave_count,

        "overtime_total":
            round(float(overtime_total), 2),

        "total_working_hours":
            round(total_working_hours, 2),

        "selected_month":
            month_value,

        # ---------------- NEW: face verification ----------------

        "face_enrolled":
            bool(descriptors),

        "face_descriptor_json":
            json.dumps(descriptors),

        "face_threshold":
            FACE_MATCH_THRESHOLD,
    }

    return render(
        request,
        "accountant/attendance.html",
        context,
    )


# ============================================================
# ACCOUNTANT - MY SHIFT
# ============================================================

@staff_login_required
@never_cache
def accountant_my_shift(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    today = timezone.now().date()


    # --------------------------------------------------------
    # DATE RANGE
    # --------------------------------------------------------

    start_value = request.GET.get("start_date")

    if start_value:

        try:
            start_date = datetime.strptime(
                start_value,
                "%Y-%m-%d"
            ).date()

        except ValueError:
            start_date = today

    else:

        # Monday of current week
        start_date = (
            today
            -
            timedelta(days=today.weekday())
        )

    end_date = start_date + timedelta(days=6)


    # --------------------------------------------------------
    # SHIFTS
    # --------------------------------------------------------

    shifts = (
        Shift.objects
        .filter(
            staff=staff,
            date__range=(
                start_date,
                end_date,
            ),
        )
        .select_related(
            "department",
        )
        .order_by("date")
    )


    # --------------------------------------------------------
    # SHIFT TEMPLATES
    # --------------------------------------------------------

    templates = {
        template.shift_name: template
        for template in (
            ShiftTemplate.objects
            .filter(
                hotel_id=staff.hotel_id,
                is_active=True,
            )
        )
    }


    DEFAULT_TIMES = {

        "Morning": (
            time(6, 0),
            time(14, 0),
        ),

        "Evening": (
            time(14, 0),
            time(22, 0),
        ),

        "Night": (
            time(22, 0),
            time(6, 0),
        ),
    }


    # --------------------------------------------------------
    # BUILD 7 DAY SCHEDULE
    # --------------------------------------------------------

    shift_map = {
        shift.date: shift
        for shift in shifts
    }

    week_days = []

    for index in range(7):

        day = start_date + timedelta(
            days=index
        )

        shift = shift_map.get(day)

        shift_name = None
        start_time = None
        end_time = None

        if shift:

            shift_name = (
                shift.custom_name
                if (
                    shift.shift == "Custom"
                    and shift.custom_name
                )
                else shift.shift
            )

            # Custom shift
            if shift.custom_start:

                start_time = shift.custom_start
                end_time = shift.custom_end

            else:

                template = templates.get(
                    shift.shift
                )

                if template:

                    start_time = (
                        template.start_time
                    )

                    end_time = (
                        template.end_time
                    )

                elif shift.shift in DEFAULT_TIMES:

                    start_time, end_time = (
                        DEFAULT_TIMES[
                            shift.shift
                        ]
                    )

        week_days.append({

            "date": day,

            "is_today":
                day == today,

            "shift":
                shift,

            "shift_name":
                shift_name,

            "start_time":
                start_time,

            "end_time":
                end_time,
        })


    # --------------------------------------------------------
    # TODAY SHIFT
    # --------------------------------------------------------

    today_shift = (
        Shift.objects
        .filter(
            staff=staff,
            date=today,
        )
        .first()
    )


    previous_week = (
        start_date
        -
        timedelta(days=7)
    )

    next_week = (
        start_date
        +
        timedelta(days=7)
    )


    context = {

        "staff": staff,
        "hotel": staff.hotel,

        "today": today,

        "today_shift":
            today_shift,

        "week_days":
            week_days,

        "start_date":
            start_date,

        "end_date":
            end_date,

        "previous_week":
            previous_week,

        "next_week":
            next_week,

        "shift_count":
            shifts.count(),
    }

    return render(
        request,
        "accountant/shifts.html",
        context,
    )


# ============================================================
# ACCOUNTANT - MY LEAVE
# ============================================================

@staff_login_required
@never_cache
def accountant_my_leave(request):

    staff = _get_accountant_staff(request)

    if not staff:
        return redirect("staff_login")

    today = timezone.now().date()


    # --------------------------------------------------------
    # MY LEAVE REQUESTS
    # --------------------------------------------------------

    leaves = (
        LeaveRequest.objects
        .filter(
            staff=staff,
        )
        .order_by("-applied_at")
    )


    # --------------------------------------------------------
    # FILTER
    # --------------------------------------------------------

    selected_status = (
        request.GET.get("status")
        or ""
    ).strip()

    if selected_status in [
        "Pending",
        "Approved",
        "Rejected",
    ]:

        leaves = leaves.filter(
            status=selected_status
        )


    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    all_leaves = (
        LeaveRequest.objects
        .filter(
            staff=staff,
        )
    )

    total_leave_count = (
        all_leaves.count()
    )

    pending_leave_count = (
        all_leaves
        .filter(status="Pending")
        .count()
    )

    approved_leave_count = (
        all_leaves
        .filter(status="Approved")
        .count()
    )

    rejected_leave_count = (
        all_leaves
        .filter(status="Rejected")
        .count()
    )


    # --------------------------------------------------------
    # APPROVED DAYS
    # --------------------------------------------------------

    approved_days = 0

    for leave in all_leaves.filter(
        status="Approved"
    ):

        if leave.from_date and leave.to_date:

            approved_days += (
                leave.to_date
                -
                leave.from_date
            ).days + 1


    context = {

        "staff": staff,
        "hotel": staff.hotel,

        "today": today,

        "leaves":
            leaves,

        "selected_status":
            selected_status,

        "total_leave_count":
            total_leave_count,

        "pending_leave_count":
            pending_leave_count,

        "approved_leave_count":
            approved_leave_count,

        "rejected_leave_count":
            rejected_leave_count,

        "approved_days":
            approved_days,
    }

    return render(
        request,
        "accountant/leave.html",
        context,
    )






# ============================================================
# MY ATTENDANCE PAGE
# ============================================================
@staff_login_required
@never_cache
def hr_my_attendance(request):

    # ============================================================
    # CURRENT STAFF
    # ============================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:
        return redirect("staff_login")

    try:
        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
                "user",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:
        return redirect("staff_login")


    hotel = staff.hotel

    if not hotel:
        return redirect("staff_login")


    # Keep hotel session synchronized
    if request.session.get("hotel_id") != staff.hotel_id:
        request.session["hotel_id"] = staff.hotel_id


    # ============================================================
    # CURRENT DATE
    #
    # IMPORTANT:
    # Do NOT use timezone.localdate() here.
    #
    # Your current project is returning a naive datetime from
    # timezone.now(), therefore localdate()/localtime() crashes.
    # ============================================================

    now = timezone.now()

    if timezone.is_aware(now):
        current_now = timezone.localtime(now)
    else:
        current_now = now

    today = current_now.date()


    # ============================================================
    # SELECTED MONTH
    # ============================================================

    month_value = (
        request.GET.get("month")
        or today.strftime("%Y-%m")
    ).strip()

    try:
        selected_date = datetime.strptime(
            month_value,
            "%Y-%m"
        )

        selected_year = selected_date.year
        selected_month = selected_date.month

    except (ValueError, TypeError):

        selected_year = today.year
        selected_month = today.month

        month_value = today.strftime("%Y-%m")


    selected_month_label = datetime(
        selected_year,
        selected_month,
        1
    ).strftime("%B %Y")


    # ============================================================
    # STATUS FILTER
    # ============================================================

    selected_status = (
        request.GET.get("status")
        or ""
    ).strip()

    allowed_statuses = [
        "Present",
        "Late",
        "Half Day",
        "Absent",
        "Leave",
    ]

    if selected_status not in allowed_statuses:
        selected_status = ""


    # ============================================================
    # TODAY'S ATTENDANCE
    # ============================================================

    today_attendance = (
        Attendance.objects
        .filter(
            staff=staff,
            hotel=hotel,
            date=today,
        )
        .first()
    )


    # ============================================================
    # CURRENT MONTH ATTENDANCE
    # ============================================================

    monthly_attendance = (
        Attendance.objects
        .filter(
            staff=staff,
            hotel=hotel,
            date__year=selected_year,
            date__month=selected_month,
        )
        .order_by("-date")
    )


    # ============================================================
    # MONTH SUMMARY
    # ============================================================

    # Present means the employee attended.
    # Late is still an attended day.
    present_count = (
        monthly_attendance
        .filter(
            status__in=[
                "Present",
                "Late",
            ]
        )
        .count()
    )

    late_count = (
        monthly_attendance
        .filter(status="Late")
        .count()
    )

    half_day_count = (
        monthly_attendance
        .filter(status="Half Day")
        .count()
    )

    absent_count = (
        monthly_attendance
        .filter(status="Absent")
        .count()
    )

    leave_count = (
        monthly_attendance
        .filter(status="Leave")
        .count()
    )


    overtime_total = (
        monthly_attendance
        .aggregate(
            total=Sum("overtime_hours")
        )
        .get("total")
        or 0
    )


    # ============================================================
    # APPLY STATUS FILTER TO TABLE
    # ============================================================

    table_queryset = monthly_attendance

    if selected_status:

        table_queryset = table_queryset.filter(
            status=selected_status
        )


    # ============================================================
    # ATTENDANCE TABLE
    # ============================================================

    attendance_rows = []

    total_working_hours = 0

    for record in table_queryset:

        working_hours = 0
        working_hours_text = "ΓÇö"

        if record.check_in and record.check_out:

            try:
                difference = (
                    record.check_out
                    -
                    record.check_in
                )

                seconds = max(
                    int(difference.total_seconds()),
                    0
                )

                hours = seconds // 3600

                minutes = (
                    seconds % 3600
                ) // 60

                working_hours = round(
                    seconds / 3600,
                    2
                )

                working_hours_text = (
                    f"{hours}h {minutes}m"
                )

                total_working_hours += working_hours

            except Exception:
                working_hours = 0
                working_hours_text = "ΓÇö"


        attendance_rows.append({

            "record":
                record,

            "date":
                record.date,

            "check_in":
                record.check_in,

            "check_out":
                record.check_out,

            "status":
                record.status or "Absent",

            "working_hours":
                working_hours,

            "working_hours_text":
                working_hours_text,

            "overtime":
                float(
                    record.overtime_hours or 0
                ),
        })


    # ============================================================
    # TODAY WORKING TIME
    # ============================================================

    today_working_hours = 0
    today_working_minutes = 0
    today_working_text = "0h 0m"


    if (
        today_attendance
        and
        today_attendance.check_in
    ):

        start_time = today_attendance.check_in

        if today_attendance.check_out:
            end_time = today_attendance.check_out
        else:
            end_time = now


        # --------------------------------------------------------
        # Make timezone awareness compatible
        # --------------------------------------------------------

        if (
            timezone.is_aware(start_time)
            and
            timezone.is_naive(end_time)
        ):

            try:
                end_time = timezone.make_aware(
                    end_time,
                    timezone.get_current_timezone()
                )
            except Exception:
                pass


        elif (
            timezone.is_naive(start_time)
            and
            timezone.is_aware(end_time)
        ):

            end_time = timezone.make_naive(
                end_time,
                timezone.get_current_timezone()
            )


        try:

            duration = (
                end_time
                -
                start_time
            )

            total_seconds = max(
                int(duration.total_seconds()),
                0
            )

            today_working_hours = (
                total_seconds // 3600
            )

            today_working_minutes = (
                (total_seconds % 3600) // 60
            )

            today_working_text = (
                f"{today_working_hours}h "
                f"{today_working_minutes}m"
            )

        except Exception:

            today_working_hours = 0
            today_working_minutes = 0
            today_working_text = "0h 0m"


    # ============================================================
    # TODAY ATTENDANCE STATE
    # ============================================================

    if not today_attendance:

        today_state = "not_started"

    elif (
        today_attendance.check_in
        and
        not today_attendance.check_out
    ):

        today_state = "working"

    elif (
        today_attendance.check_in
        and
        today_attendance.check_out
    ):

        today_state = "completed"

    else:

        today_state = "not_started"


    # ============================================================
    # TODAY'S SHIFT
    # ============================================================

    today_shift = (
        Shift.objects
        .filter(
            staff=staff,
            hotel=hotel,
            date=today,
        )
        .first()
    )


    shift_name = "No shift assigned"
    shift_start = None
    shift_end = None


    if today_shift:

        shift_name = (
            today_shift.custom_name
            if (
                today_shift.shift == "Custom"
                and today_shift.custom_name
            )
            else today_shift.shift
        )


        # Custom shift
        if (
            today_shift.custom_start
            and
            today_shift.custom_end
        ):

            shift_start = (
                today_shift.custom_start
            )

            shift_end = (
                today_shift.custom_end
            )

        else:

            # Shift template
            shift_template = (
                ShiftTemplate.objects
                .filter(
                    hotel=hotel,
                    shift_name=today_shift.shift,
                    is_active=True,
                )
                .first()
            )

            if shift_template:

                shift_start = (
                    shift_template.start_time
                )

                shift_end = (
                    shift_template.end_time
                )

            else:

                fallback = {
                    "Morning": (
                        time(9, 0),
                        time(17, 0),
                    ),

                    "Evening": (
                        time(14, 0),
                        time(22, 0),
                    ),

                    "Night": (
                        time(22, 0),
                        time(6, 0),
                    ),
                }

                shift_start, shift_end = (
                    fallback.get(
                        today_shift.shift,
                        (None, None)
                    )
                )


    # ============================================================
    # FACE DATA
    # ============================================================

    descriptors = normalize_descriptors(
        staff.face_descriptor
    )

    face_enrolled = bool(descriptors)


    # ============================================================
    # CONTEXT
    # ============================================================

    context = {

        # Employee
        "staff":
            staff,

        "hotel":
            hotel,

        # Current date
        "today":
            today,

        # Month
        "selected_month":
            month_value,

        "selected_month_value":
            month_value,

        "selected_month_label":
            selected_month_label,

        "selected_status":
            selected_status,

        # Today's attendance
        "today_attendance":
            today_attendance,

        "today_state":
            today_state,

        "today_working_hours":
            today_working_hours,

        "today_working_minutes":
            today_working_minutes,

        "today_working_text":
            today_working_text,

        # Shift
        "today_shift":
            today_shift,

        "shift_name":
            shift_name,

        "shift_start":
            shift_start,

        "shift_end":
            shift_end,

        # Statistics
        "present_count":
            present_count,

        "late_count":
            late_count,

        "half_day_count":
            half_day_count,

        "absent_count":
            absent_count,

        "leave_count":
            leave_count,

        "overtime_total":
            round(
                float(overtime_total),
                2
            ),

        "total_working_hours":
            round(
                total_working_hours,
                2
            ),

        # Table
        "attendance_rows":
            attendance_rows,

        # Face verification
        "face_enrolled":
            face_enrolled,

        "face_descriptor_json":
            json.dumps(descriptors),

        "face_threshold":
            FACE_MATCH_THRESHOLD,

        # Sidebar
        "active_hr_page":
            "my_attendance",
    }


    return render(
        request,
        "hr/my_attendance.html",
        context,
    )





@staff_login_required
@never_cache
@require_POST
def hr_my_attendance_mark(request):

    # ============================================================
    # CURRENT STAFF
    # ============================================================

    staff_id = request.session.get("staff_id")

    if not staff_id:

        return JsonResponse(
            {
                "success": False,
                "message": "Login required.",
            },
            status=401,
        )


    try:

        staff = (
            Staff.objects
            .select_related(
                "hotel",
                "department",
            )
            .get(id=staff_id)
        )

    except Staff.DoesNotExist:

        return JsonResponse(
            {
                "success": False,
                "message": "Staff account not found.",
            },
            status=404,
        )


    # ============================================================
    # ACTION
    # ============================================================

    action = (
        request.POST.get(
            "action",
            ""
        )
        .strip()
        .lower()
    )


    if action not in [
        "check_in",
        "check_out",
    ]:

        return JsonResponse(
            {
                "success": False,
                "message": "Invalid attendance action.",
            },
            status=400,
        )


    # ============================================================
    # FACE VERIFICATION
    #
    # We require face verification for CHECK-IN.
    #
    # This follows the same approach already used by your
    # accountant/staff attendance code.
    # ============================================================

    if action == "check_in":

        # --------------------------------------------------------
        # SAVED FACE
        # --------------------------------------------------------

        stored_descriptors = normalize_descriptors(
            staff.face_descriptor
        )


        if not stored_descriptors:

            return JsonResponse(
                {
                    "success": False,

                    "code":
                        "FACE_NOT_REGISTERED",

                    "message":
                        (
                            "Your face has not been registered. "
                            "Please contact HR/Admin."
                        ),
                },
                status=403,
            )


        # --------------------------------------------------------
        # LIVE FACE
        # --------------------------------------------------------

        raw_descriptor = request.POST.get(
            "face_descriptor"
        )


        if not raw_descriptor:

            return JsonResponse(
                {
                    "success": False,

                    "code":
                        "FACE_REQUIRED",

                    "message":
                        (
                            "Face verification is required "
                            "before check-in."
                        ),
                },
                status=400,
            )


        # --------------------------------------------------------
        # PARSE DESCRIPTOR
        # --------------------------------------------------------

        try:

            live_descriptor = json.loads(
                raw_descriptor
            )

        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):

            return JsonResponse(
                {
                    "success": False,

                    "code":
                        "INVALID_FACE_DATA",

                    "message":
                        "Invalid face verification data.",
                },
                status=400,
            )


        # --------------------------------------------------------
        # VALIDATE 128-D FACE DESCRIPTOR
        # --------------------------------------------------------

        if not validate_face_descriptor(
            live_descriptor
        ):

            return JsonResponse(
                {
                    "success": False,

                    "code":
                        "INVALID_FACE_DATA",

                    "message":
                        "Invalid face descriptor.",
                },
                status=400,
            )


        # --------------------------------------------------------
        # COMPARE FACE
        # --------------------------------------------------------

        matched, distance = verify_staff_face(
            stored_descriptors,
            live_descriptor,
        )


        if not matched:

            return JsonResponse(
                {
                    "success": False,

                    "matched":
                        False,

                    "code":
                        "FACE_MISMATCH",

                    "message":
                        (
                            "Face does not match the "
                            "registered employee."
                        ),

                    "distance":
                        round(
                            float(distance),
                            4
                        ),
                },
                status=403,
            )


    # ============================================================
    # MARK ATTENDANCE
    #
    # Use your existing common function.
    # ============================================================

    try:

        result = _do_mark_attendance(
            staff,
            action,
        )

    except Exception as error:

        print(
            "HR attendance error:",
            error,
        )

        return JsonResponse(
            {
                "success": False,
                "message": "Unable to mark attendance.",
            },
            status=500,
        )


    # ============================================================
    # RESPONSE
    # ============================================================

    if action == "check_in":
        result["face_verified"] = True


    return JsonResponse(
        result,
        status=(
            200
            if result.get("success")
            else 400
        ),
    )
