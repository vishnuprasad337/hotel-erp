import json
from decimal import Decimal
from collections import defaultdict

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.timezone import now
from django.db.models import Sum, Q, F, Count
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache

from django_tenants.utils import schema_context
from django.db import connection

from .models import (
    ItemCategory, Vendor, InventoryItem,
    StockAdjustment, PurchaseOrder, PurchaseItem,
    ExpenseCategory, Expense,
    AssetCategory, HotelAsset, MaintenanceLog, AssetLocation,
    LaundryService, LaundryOrder, LaundryOrderItem, LaundryStatusLog,
    HotelLinenBatch, HotelLinenBatchItem, LinenMissingReason,
)

from accounts.models import Staff, Department
from pms.models import Booking
from billing.models import GuestFolio, FolioCharge


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _json(request):
    try:
        return json.loads(request.body)
    except Exception:
        return {}


def _require_post(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    return None


def _get_staff(request):
    """
    Always returns a single value: a Staff instance, or None.
    Never unpack this as a tuple — callers must do `staff = _get_staff(request)`.
    Tries session first (staff_id), then falls back to the authenticated user.
    """
    staff_id = request.session.get("staff_id")
    if staff_id:
        try:
            return Staff.objects.select_related("department", "user").get(id=staff_id)
        except Staff.DoesNotExist:
            pass
    if request.user.is_authenticated:
        try:
            return Staff.objects.select_related("department", "user").get(user=request.user)
        except Staff.DoesNotExist:
            pass
    return None


def _is_admin(staff):
    if not staff:
        return True
    ADMIN_DEPARTMENTS = ("hr", "admin", "management", "hotel")
    return (
        staff.user.is_staff
        or staff.user.is_superuser
        or (staff.department and staff.department.name.lower() in ADMIN_DEPARTMENTS)
    )


# ══════════════════════════════════════════════════════════════
# CATEGORIES
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def add_category(request):
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    obj = ItemCategory.objects.create(name=data.get("name"))
    return JsonResponse({"id": obj.id, "name": obj.name}, status=201)


def list_categories(request):
    return JsonResponse({"categories": list(ItemCategory.objects.values())})


# ══════════════════════════════════════════════════════════════
# VENDORS
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def add_vendor(request):
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    obj = Vendor.objects.create(
        name=data.get("name"),
        contact_person=data.get("contact_person", ""),
        phone=data.get("phone"),
        email=data.get("email", ""),
        address=data.get("address", ""),
    )
    return JsonResponse({"id": obj.id}, status=201)


def list_vendors(request):
    return JsonResponse({"vendors": list(Vendor.objects.values())})


# ══════════════════════════════════════════════════════════════
# DEPARTMENTS
# ══════════════════════════════════════════════════════════════

def departments(request):
    """
    Deduped by name (case-insensitive), keeping the lowest-id row for
    each distinct name. Does NOT touch the database — duplicate rows
    still exist underneath, this just hides them from every dropdown
    that calls this endpoint.
    """
    qs = Department.objects.all().order_by('name', 'id')

    seen = set()
    result = []
    for d in qs:
        key = d.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        result.append({"id": d.id, "name": d.name})

    return JsonResponse({"departments": result})


# ══════════════════════════════════════════════════════════════
# INVENTORY ITEMS
# ══════════════════════════════════════════════════════════════

def list_inventory(request):
    staff = _get_staff(request)

    qs = InventoryItem.objects.select_related("category", "department", "vendor")

    if _is_admin(staff):
        # Hotel admin — see everything, optional dept filter
        dept_id = request.GET.get("department_id")
        if dept_id:
            qs = qs.filter(department_id=dept_id)
    else:
        if not staff.department:
            return JsonResponse({"items": []})

        dept_name = staff.department.name.lower()

        full_access_keywords = (
            "hr", "human resource", "human resources",
            "admin", "administration", "manager", "management",
            "accounts", "finance", "front desk", "general"
        )

        if any(k in dept_name for k in full_access_keywords):
            pass  # no filter — see all inventory

        elif any(k in dept_name for k in ("housekeeping", "cleaning", "laundry")):
            qs = qs.filter(
                Q(department=staff.department)
                | Q(department__name__icontains="housekeeping")
                | Q(department__name__icontains="cleaning")
                | Q(department__name__icontains="laundry")
                | Q(department__isnull=True)
            ).distinct()

        elif any(k in dept_name for k in ("restaurant", "kitchen", "dining", "food", "bar")):
            qs = qs.filter(
                Q(department=staff.department)
                | Q(department__name__icontains="restaurant")
                | Q(department__name__icontains="kitchen")
                | Q(department__name__icontains="dining")
            ).distinct()

        else:
            qs = qs.filter(
                Q(department=staff.department) | Q(department__isnull=True)
            ).distinct()

    if request.GET.get("low_stock") == "1":
        qs = qs.filter(current_stock__lte=F("minimum_stock"))

    data = [
        {
            "id": item.id,
            "name": item.name,
            "category": item.category.name if item.category else None,
            "category_id": item.category_id,
            "department": item.department.name if item.department else None,
            "department_id": item.department_id,
            "vendor_id": item.vendor_id,
            "unit": item.unit,
            "stock": float(item.current_stock),
            "min_stock": float(item.minimum_stock),
            "cost_per_unit": float(item.cost_per_unit),
            "vendor": item.vendor.name if item.vendor else None,
            "low_stock": item.is_low_stock,
            "stock_value": float(item.stock_value),
            "image": request.build_absolute_uri(item.image.url) if item.image else None,
        }
        for item in qs
    ]
    return JsonResponse({"items": data})


def inventory_by_department(request):
    staff = _get_staff(request)

    qs = InventoryItem.objects.all()

    if not _is_admin(staff):
        if not staff or not staff.department:
            return JsonResponse({"departments": []})
        qs = qs.filter(department=staff.department)

    rows = (
        qs
        .values("department__id", "department__name")
        .annotate(
            item_count=Count("id"),
            total_value=Sum(F("current_stock") * F("cost_per_unit")),
            low_stock_count=Count(
                "id",
                filter=Q(current_stock__lte=F("minimum_stock"))
            ),
        )
        .order_by("department__name")
    )

    result = [
        {
            "department_id":   r["department__id"],
            "department":      r["department__name"] or "Unassigned",
            "item_count":      r["item_count"],
            "total_value":     float(r["total_value"] or 0),
            "low_stock_count": r["low_stock_count"],
        }
        for r in rows
    ]
    return JsonResponse({"departments": result})


@csrf_exempt
def add_inventory_item(request):
    post_err = _require_post(request)
    if post_err:
        return post_err

    staff = _get_staff(request)

    # Support both JSON (no image) and multipart/form-data (with image file)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.POST
        image_file = request.FILES.get('image')
    else:
        data = _json(request)
        image_file = None

    name = data.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Item name is required"}, status=400)

    if _is_admin(staff):
        department_id = data.get("department_id")
        if not department_id:
            return JsonResponse({"error": "department_id is required"}, status=400)
    else:
        if not staff.department:
            return JsonResponse({"error": "You are not assigned to any department"}, status=403)
        department_id = staff.department.id

    obj = InventoryItem.objects.create(
        category_id=data.get("category_id") or None,
        department_id=department_id,
        name=name,
        unit=data.get("unit", "piece"),
        current_stock=data.get("current_stock", 0),
        minimum_stock=data.get("minimum_stock", 10),
        cost_per_unit=data.get("cost_per_unit", 0),
        vendor_id=data.get("vendor_id") or None,
    )

    if image_file:
        obj.image = image_file
        obj.save(update_fields=["image"])

    return JsonResponse({
        "id":            obj.id,
        "name":          obj.name,
        "department":    obj.department.name if obj.department else None,
        "department_id": obj.department_id,
        "unit":          obj.unit,
        "stock":         float(obj.current_stock),
        "min_stock":     float(obj.minimum_stock),
        "cost_per_unit": float(obj.cost_per_unit),
        "low_stock":     obj.is_low_stock,
        "stock_value":   float(obj.stock_value),
        "image":         request.build_absolute_uri(obj.image.url) if obj.image else None,
    }, status=201)


@csrf_exempt
def update_inventory_item(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    item = get_object_or_404(InventoryItem, pk=pk)

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.POST
        image_file = request.FILES.get('image')
    else:
        data = json.loads(request.body)
        image_file = None

    for f in ['name', 'unit', 'current_stock', 'minimum_stock', 'cost_per_unit']:
        if f in data:
            setattr(item, f, data[f])

    if 'category_id' in data:
        item.category_id = data['category_id'] or None
    if 'department_id' in data:
        item.department_id = data['department_id'] or None
    if 'vendor_id' in data:
        item.vendor_id = data['vendor_id'] or None

    if image_file:
        item.image = image_file
    elif data.get('remove_image') in ('1', 'true', 'True'):
        item.image = None

    item.save()

    return JsonResponse({
        'success': True,
        'id': item.id,
        'image': request.build_absolute_uri(item.image.url) if item.image else None,
    })


@csrf_exempt
def delete_inventory_item(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    get_object_or_404(InventoryItem, pk=pk).delete()
    return JsonResponse({'success': True})


# ══════════════════════════════════════════════════════════════
# STOCK ADJUSTMENTS
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def stock_adjust(request):
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    staff = _get_staff(request)

    try:
        item = InventoryItem.objects.get(id=data["item_id"])
    except InventoryItem.DoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)

    try:
        qty = Decimal(str(data["quantity"]))
    except Exception:
        return JsonResponse({"error": "Invalid quantity"}, status=400)

    typ = data.get("adjustment_type") or data.get("type", "in")

    if typ == "in":
        item.current_stock += qty
    elif typ == "out":
        item.current_stock = max(Decimal("0"), item.current_stock - qty)
    else:
        item.current_stock = qty  # "adjust" / "set" — set exact value

    item.save()

    StockAdjustment.objects.create(
        item=item,
        adjustment_type=typ,
        quantity=qty,
        note=data.get("note", ""),
        adjusted_by=staff,
    )

    return JsonResponse({
        "success":   True,
        "new_stock": float(item.current_stock),
        "item_id":   item.id,
        "item_name": item.name,
    })


def list_stock_adjustments(request):
    qs = StockAdjustment.objects.select_related(
        "item",
        "item__department",
        "adjusted_by",
        "adjusted_by__department",
    )

    if request.GET.get("item_id"):
        qs = qs.filter(item_id=request.GET["item_id"])
    if request.GET.get("department_id"):
        qs = qs.filter(item__department_id=request.GET["department_id"])
    if request.GET.get("limit"):
        try:
            limit = int(request.GET["limit"])
        except ValueError:
            limit = 100
    else:
        limit = 100

    data = [
        {
            "id":                     a.id,
            "item":                   a.item.name,
            "item_id":                a.item.id,
            "department":             a.item.department.name if a.item.department else None,
            "type":                   a.adjustment_type,
            "adjustment_type":        a.adjustment_type,
            "quantity":               float(a.quantity),
            "note":                   a.note,
            "adjusted_by":            str(a.adjusted_by) if a.adjusted_by else None,
            "adjusted_by_department": (
                a.adjusted_by.department.name
                if a.adjusted_by and a.adjusted_by.department
                else None
            ),
            "date":                   a.created_at.isoformat(),
            "created_at":             a.created_at.isoformat(),
        }
        for a in qs.order_by("-created_at")[:limit]
    ]
    return JsonResponse({"adjustments": data})


# ══════════════════════════════════════════════════════════════
# PURCHASE ORDERS
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def create_purchase_order(request):
    err = _require_post(request)
    if err:
        return err
    data  = _json(request)
    staff = _get_staff(request)

    po = PurchaseOrder.objects.create(
        vendor_id=data["vendor_id"],
        department_id=data.get("department_id"),
        note=data.get("note", ""),
        ordered_by=staff,
    )

    total = Decimal("0")
    for i in data.get("items", []):
        qty   = Decimal(str(i["quantity"]))
        price = Decimal(str(i["unit_price"]))
        PurchaseItem.objects.create(
            purchase_order=po,
            item_id=i["item_id"],
            quantity=qty,
            unit_price=price,
        )
        total += qty * price

    po.total_amount = total
    po.save()
    return JsonResponse({"po_id": po.id, "total": float(total)}, status=201)


@csrf_exempt
def update_po_status(request, po_id):
    err = _require_post(request)
    if err:
        return err

    data   = _json(request)
    status = data.get("status")
    staff  = _get_staff(request)

    try:
        po = PurchaseOrder.objects.get(id=po_id)
    except PurchaseOrder.DoesNotExist:
        return JsonResponse({"error": "PO not found"}, status=404)

    po.status = status

    if status == "approved":
        po.approved_by = staff

    if status == "received":
        po.received_at = timezone.now()

        for pi in po.items.select_related("item"):
            pi.item.current_stock += pi.quantity
            pi.item.save()

            StockAdjustment.objects.create(
                item=pi.item,
                adjustment_type="in",
                quantity=pi.quantity,
                note=f"PO-{po.id} received",
                adjusted_by=staff,
            )

        category, _ = ExpenseCategory.objects.get_or_create(name="Purchase")

        Expense.objects.get_or_create(
            purchase_order=po,
            defaults={
                "department": po.department,
                "expense_category": category,
                "source": "purchase_order",
                "amount": po.total_amount,
                "description": f"PO-{po.id} — {po.vendor.name}",
                "expense_date": timezone.now().date(),
                "recorded_by": staff,
            },
        )

    po.save()

    return JsonResponse({"success": True, "status": po.status})@csrf_exempt
def update_po_status(request, po_id):
    err = _require_post(request)
    if err:
        return err

    data = _json(request)
    status = data.get("status")
    staff = _get_staff(request)

    if not status:
        return JsonResponse({"error": "status is required"}, status=400)

    with transaction.atomic():
        try:
            po = PurchaseOrder.objects.select_for_update().get(id=po_id)
        except PurchaseOrder.DoesNotExist:
            return JsonResponse({"error": "PO not found"}, status=404)

        was_received = po.status == "received"
        po.status = status

        if status == "approved":
            po.approved_by = staff

        if status == "received":
            # Add stock only the first time, so re-sending "received"
            # never doubles the inventory.
            if not was_received:
                po.received_at = timezone.now()

                for pi in po.items.select_related("item"):
                    pi.item.current_stock += pi.quantity
                    pi.item.save()

                    StockAdjustment.objects.create(
                        item=pi.item,
                        adjustment_type="in",
                        quantity=pi.quantity,
                        note=f"PO-{po.id} received",
                        adjusted_by=staff,
                    )

            # Fall back to the line items if the stored total is empty.
            amount = po.total_amount or sum(
                (pi.quantity * pi.unit_price for pi in po.items.all()),
                Decimal("0"),
            )

            # Runs on every "received" call, so a missing expense is
            # created even if an earlier attempt failed.
            if amount > 0:
                category, _ = ExpenseCategory.objects.get_or_create(name="Purchase")

                Expense.objects.get_or_create(
                    purchase_order=po,
                    defaults={
                        "department": po.department,
                        "expense_category": category,
                        "source": "purchase_order",
                        "amount": amount,
                        "description": f"PO-{po.id} — {po.vendor.name}",
                        "expense_date": timezone.now().date(),
                        "recorded_by": staff,
                    },
                )

        po.save()

    return JsonResponse({"success": True, "status": po.status})


from django.db.models import Q
from django.http import JsonResponse


def list_purchase_orders(request):
    staff = _get_staff(request)

    qs = PurchaseOrder.objects.select_related(
        "vendor",
        "department",
        "ordered_by",
        "approved_by",
    ).prefetch_related("items__item")

    # Preserve existing department access rules.
    if not _is_admin(staff):
        if not staff or not staff.department:
            return JsonResponse({"purchase_orders": []})

        dept_name = staff.department.name.lower()

        full_access_keywords = (
            "hr",
            "human resource",
            "human resources",
            "admin",
            "administration",
            "manager",
            "management",
            "accounts",
            "finance",
            "front desk",
            "general",
        )

        if any(k in dept_name for k in full_access_keywords):
            pass

        elif any(
            k in dept_name
            for k in ("housekeeping", "cleaning", "laundry")
        ):
            qs = qs.filter(
                Q(department=staff.department)
                | Q(department__name__icontains="housekeeping")
                | Q(department__name__icontains="cleaning")
                | Q(department__name__icontains="laundry")
                | Q(department__isnull=True)
            ).distinct()

        elif any(
            k in dept_name
            for k in ("restaurant", "kitchen", "dining", "food", "bar")
        ):
            qs = qs.filter(
                Q(department=staff.department)
                | Q(department__name__icontains="restaurant")
                | Q(department__name__icontains="kitchen")
                | Q(department__name__icontains="dining")
            ).distinct()

        else:
            qs = qs.filter(
                Q(department=staff.department)
                | Q(department__isnull=True)
            ).distinct()

    data = []

    for po in qs.order_by("-ordered_at"):
        ordered_by_name = (
            str(po.ordered_by)
            if po.ordered_by
            else "Admin"
        )

        if po.approved_by:
            approved_by_name = str(po.approved_by)
        elif po.status in ("approved", "received"):
            approved_by_name = "Admin"
        else:
            approved_by_name = None

        lines = [
            {
                "id": pi.id,
                "item_id": pi.item_id,
                "item_name": pi.item.name if pi.item else "—",
                "quantity": float(pi.quantity),
                "unit": pi.item.unit if pi.item else "",
                "unit_price": float(pi.unit_price),
                "subtotal": float(pi.subtotal),
            }
            for pi in po.items.all()
        ]

        data.append({
            "id": po.id,
            "vendor": po.vendor.name,
            "vendor_id": po.vendor_id,
            "department": (
                po.department.name if po.department else None
            ),
            "department_id": po.department_id,
            "status": po.status,
            "total": float(po.total_amount),
            "note": po.note,
            "ordered_by": ordered_by_name,
            "approved_by": approved_by_name,
            "ordered_at": po.ordered_at.isoformat(),
            "received_at": (
                po.received_at.isoformat()
                if po.received_at
                else None
            ),
            "items": lines,
        })

    return JsonResponse({"purchase_orders": data})
@csrf_exempt
def get_po_items(request, pk):
    po = get_object_or_404(PurchaseOrder, pk=pk)
    items = [{
        'item_name': pi.item.name,
        'unit': pi.item.unit,
        'quantity': float(pi.quantity),
        'unit_price': float(pi.unit_price),
    } for pi in po.items.select_related('item')]
    return JsonResponse({'items': items})


# ══════════════════════════════════════════════════════════════
# EXPENSES
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def add_expense_category(request):
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    obj = ExpenseCategory.objects.create(
        name=data["name"],
        budget=Decimal(str(data.get("budget", 0))),
    )
    return JsonResponse({"id": obj.id, "name": obj.name}, status=201)


def list_expense_categories(request):
    return JsonResponse({"expense_categories": list(ExpenseCategory.objects.values())})


@csrf_exempt
def add_expense(request):
    err = _require_post(request)
    if err:
        return err
    data  = _json(request)
    staff = _get_staff(request)

    exp = Expense.objects.create(
        department_id=data.get("department_id"),
        expense_category_id=data.get("expense_category_id"),
        inventory_item_id=data.get("inventory_item_id"),
        source=data.get("source", "manual"),
        amount=Decimal(str(data["amount"])),
        description=data.get("description", ""),
        expense_date=data.get("expense_date", timezone.now().date()),
        recorded_by=staff,
    )
    return JsonResponse({"id": exp.id}, status=201)


def list_expenses(request):
    qs = Expense.objects.select_related(
        "department", "expense_category", "purchase_order",
        "recorded_by", "recorded_by__department"
    )

    if request.GET.get("department_id"):
        qs = qs.filter(department_id=request.GET["department_id"])

    month = request.GET.get("month")
    date  = request.GET.get("date")
    if date:
        qs = qs.filter(expense_date=date)
    elif month:
        year, mon = month.split("-")
        qs = qs.filter(expense_date__year=year, expense_date__month=mon)

    def get_department(e):
        if e.department:
            return e.department.name
        if e.recorded_by and hasattr(e.recorded_by, 'department') and e.recorded_by.department:
            return e.recorded_by.department.name
        return ""

    data = [
        {
            "id":               e.id,
            "department":       get_department(e),
            "expense_category": e.expense_category.name if e.expense_category else "",
            "source":           e.source or "manual",
            "amount":           float(e.amount),
            "description":      e.description or "",
            "expense_date":     str(e.expense_date),
            "recorded_by":      str(e.recorded_by) if e.recorded_by else "",
        }
        for e in qs.order_by("-expense_date")
    ]
    return JsonResponse({"expenses": data})


def expense_summary(request):
    qs = Expense.objects.all()
    month = request.GET.get("month")
    if month:
        year, mon = month.split("-")
        qs = qs.filter(expense_date__year=year, expense_date__month=mon)

    by_dept = (
        qs.values("department__name")
          .annotate(total=Sum("amount"))
          .order_by("-total")
    )
    by_cat = (
        qs.values("expense_category__name")
          .annotate(total=Sum("amount"))
          .order_by("-total")
    )

    return JsonResponse({
        "by_department": [
            {"department": r["department__name"] or "Unassigned", "total": float(r["total"])}
            for r in by_dept
        ],
        "by_category": [
            {"category": r["expense_category__name"] or "Uncategorised", "total": float(r["total"])}
            for r in by_cat
        ],
        "grand_total": float(qs.aggregate(t=Sum("amount"))["t"] or 0),
    })


@csrf_exempt
@require_POST
def delete_expense(request, expense_id):
    try:
        expense = Expense.objects.get(id=expense_id)
        expense.delete()
        return JsonResponse({"success": True, "message": "Expense deleted successfully"})
    except Expense.DoesNotExist:
        return JsonResponse({"success": False, "error": "Expense not found"}, status=404)


# ══════════════════════════════════════════════════════════════
# ASSETS
# ══════════════════════════════════════════════════════════════

VALID_ROOM_TYPES = {"Single", "Double", "Deluxe", "Suite", "Custom"}


def _room_label(room):
    if not room:
        return None
    rt = (room.room_type or "").strip()
    if rt == "Custom":
        return (room.custom_room_type or "").strip() or "Custom"
    if rt in {"Single", "Double", "Deluxe", "Suite"}:
        return rt
    return room.custom_room_type.strip() if room.custom_room_type else rt or "Unknown"
def _asset_room_number(room_unit):
    if room_unit is None:
        return None

    for field in ("room_number", "number", "name"):
        value = getattr(room_unit, field, None)
        if value is not None and str(value).strip():
            return str(value).strip()

    return None


def _asset_location_label(room, room_unit=None, area=""):
    room_type = _room_label(room)
    number = _asset_room_number(room_unit)

    if number:
        room_text = (
            number
            if number.lower().startswith("room ")
            else f"Room {number}"
        )
        return (
            f"{room_text} — {room_type}"
            if room_type
            else room_text
        )

    if room_type:
        return f"{room_type} — room number not assigned"

    return (area or "").strip() or None

@csrf_exempt
def add_asset_category(request):
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    name = data.get("name", "").strip()
    if not name:
        return JsonResponse({"success": False, "error": "Category name is required"}, status=400)
    obj = AssetCategory.objects.create(name=name)
    return JsonResponse({"success": True, "id": obj.id, "name": obj.name}, status=201)


def list_asset_categories(request):
    return JsonResponse({"asset_categories": list(AssetCategory.objects.values())})


@csrf_exempt
def assign_room_to_assets(request):
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    room_id   = data.get("room_id")
    area      = data.get("area", "").strip()
    asset_ids = data.get("asset_ids", [])

    if not asset_ids:
        return JsonResponse({"error": "No asset_ids provided"}, status=400)
    if not room_id and not area:
        return JsonResponse({"error": "Provide room_id or area"}, status=400)

    with schema_context(connection.tenant.schema_name):
        for asset in HotelAsset.objects.filter(id__in=asset_ids):
            if room_id:
                # Only deactivate an existing current location for THIS
                # same room — don't touch the asset's other current
                # locations, so multi-location assets stay intact.
                AssetLocation.objects.filter(
                    asset=asset, room_id=int(room_id), is_current=True,
                ).update(is_current=False)

                AssetLocation.objects.get_or_create(
                    asset=asset,
                    room_id=int(room_id),
                    room_unit=None,
                    area="",
                    is_current=True,
                )

                # Legacy single-location fields on HotelAsset: only set
                # them if this is the asset's only current location, so
                # we don't overwrite the summary fields for an asset
                # that's deliberately assigned to multiple places.
                if not AssetLocation.objects.filter(
                    asset=asset, is_current=True
                ).exclude(room_id=int(room_id)).exists():
                    asset.room_id      = int(room_id)
                    asset.room_unit_id = None
                    asset.area         = ""

            elif area:
                AssetLocation.objects.filter(
                    asset=asset, area=area, is_current=True,
                ).update(is_current=False)

                AssetLocation.objects.get_or_create(
                    asset=asset,
                    room=None,
                    room_unit=None,
                    area=area,
                    is_current=True,
                )

                if not AssetLocation.objects.filter(
                    asset=asset, is_current=True
                ).exclude(area=area).exists():
                    asset.room_id      = None
                    asset.room_unit_id = None
                    asset.area         = area

            asset.save()

    return JsonResponse({"success": True})


@csrf_exempt
def add_asset(request):
    err = _require_post(request)
    if err:
        return err

    # Support both JSON (no image) and multipart/form-data (with image file)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.POST
        image_file = request.FILES.get('image')
    else:
        data = _json(request)
        image_file = None

    room_id = data.get("room_id")

    asset = HotelAsset.objects.create(
        name=data["name"],
        asset_category_id=data.get("asset_category_id"),
        department_id=data.get("department_id"),
        serial_number=data.get("serial_number", ""),
        room_unit_id=data.get("room_unit_id"),
        room_id=room_id,
        area=data.get("area", ""),
        purchase_date=data.get("purchase_date"),
        purchase_cost=data.get("purchase_cost", 0),
        vendor_id=data.get("vendor_id"),
        warranty_end=data.get("warranty_end"),
        next_maintenance=data.get("next_maintenance"),
        assigned_to_id=data.get("assigned_to_id"),
        notes=data.get("notes", ""),
    )

    if image_file:
        asset.image = image_file
        asset.save(update_fields=["image"])

    if room_id:
        AssetLocation.objects.create(
            asset=asset, room_id=int(room_id), room_unit_id=data.get("room_unit_id"),
            area="", is_current=True,
        )
    elif data.get("area", "").strip():
        AssetLocation.objects.create(asset=asset, area=data.get("area", "").strip(), is_current=True)

    return JsonResponse({
        "id": asset.id,
        "image": request.build_absolute_uri(asset.image.url) if asset.image else None,
    }, status=201)
@csrf_exempt
def bulk_add_assets(request):
    """
    Bulk-creates assets from a JSON array. Does not support image uploads —
    this endpoint only accepts application/json, so there's no file channel
    per row. Add images afterward via update_asset for individual assets.
    """
    err = _require_post(request)
    if err:
        return err

    data = _json(request)
    assets_data = data.get("assets", [])

    if not assets_data:
        return JsonResponse({"error": "No assets provided"}, status=400)
    if len(assets_data) > 200:
        return JsonResponse({"error": "Maximum 200 assets per bulk request"}, status=400)

    created = []
    errors  = []

    with transaction.atomic():
        for i, item in enumerate(assets_data):
            name     = (item.get("name") or "").strip()
            cat_id   = item.get("asset_category_id")
            room_id  = item.get("room_id")
            area     = (item.get("area") or "").strip()

            if not name:
                errors.append({"index": i, "error": "name is required"})
                continue
            if not cat_id:
                errors.append({"index": i, "name": name, "error": "asset_category_id is required"})
                continue

            try:
                asset = HotelAsset.objects.create(
                    name=name,
                    asset_category_id=int(cat_id),
                    department_id=item.get("department_id") or None,
                    serial_number=item.get("serial_number", ""),
                    room_id=int(room_id) if room_id else None,
                    room_unit_id=item.get("room_unit_id") or None,
                    area=area,
                    purchase_date=item.get("purchase_date") or None,
                    purchase_cost=item.get("purchase_cost") or 0,
                    vendor_id=item.get("vendor_id") or None,
                    warranty_end=item.get("warranty_end") or None,
                    next_maintenance=item.get("next_maintenance") or None,
                    notes=item.get("notes", ""),
                )

                if room_id:
                    AssetLocation.objects.create(
                        asset=asset, room_id=int(room_id),
                        room_unit_id=item.get("room_unit_id") or None,
                        area="", is_current=True,
                    )
                elif area:
                    AssetLocation.objects.create(asset=asset, area=area, is_current=True)

                created.append({"id": asset.id, "name": asset.name, "image": None})

            except Exception as e:
                errors.append({"index": i, "name": name, "error": str(e)})

    if errors and not created:
        return JsonResponse({"error": "All assets failed", "errors": errors}, status=400)

    return JsonResponse({
        "success": True,
        "created": created,
        "count":   len(created),
        "errors":  errors,
    }, status=201)

   

def _asset_location_data(*, asset_id, room=None, room_unit=None, area=""):
    """Build a location row, including the specific room unit when present."""
    area = (area or "").strip()

    if room is None and room_unit is not None:
        room = room_unit.room

    room_type = room.display_type() if room else None
    room_number = None
    if room_unit is not None and room_unit.room_number is not None:
        room_number = str(room_unit.room_number).strip() or None

    if room_number:
        label = f"Room {room_number} — {room_type}" if room_type else f"Room {room_number}"
    elif room_type:
        label = room_type
    else:
        label = area or "Unassigned"

    return {
        "asset_id": asset_id,
        "room_id": room.pk if room else None,
        "room_unit_id": room_unit.pk if room_unit else None,
        "room_number": room_number,
        "room_type": room_type,
        "area": area,
        "location": label,
        "is_current": True,
    }
from collections import defaultdict
@login_required
@require_GET
def list_assets(request):
    qs = HotelAsset.objects.select_related(
        "asset_category",
        "department",
        "vendor",
        "assigned_to",
        "room",
        "room_unit",
        "room_unit__room",
    )

    if request.GET.get("department_id"):
        qs = qs.filter(
            department_id=request.GET["department_id"]
        )

    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])

    if request.GET.get("type_id"):
        qs = qs.filter(
            asset_category_id=request.GET["type_id"]
        )

    asset_list = list(qs.order_by("name"))
    asset_ids = [asset.pk for asset in asset_list]

    location_map = defaultdict(list)

    current_locations = (
        AssetLocation.objects
        .filter(
            asset_id__in=asset_ids,
            is_current=True,
        )
        .select_related(
            "room",
            "room_unit",
            "room_unit__room",
        )
        .order_by("asset_id", "assigned_at", "pk")
    )

    for location in current_locations:
        row = _asset_location_data(
            asset_id=location.asset_id,
            room=location.room,
            room_unit=location.room_unit,  
            area=location.area,
        )

        row["assigned_at"] = (
            location.assigned_at.isoformat()
            if location.assigned_at
            else None
        )

        location_map[location.asset_id].append(row)

    assets = []

    for asset in asset_list:
        locations = location_map.get(asset.pk, [])

        # Support assets created before multiple locations were added.
        if not locations and (
            asset.room_unit_id
            or asset.room_id
            or asset.area
        ):
            locations = [
                _asset_location_data(
                    asset_id=asset.pk,
                    room=asset.room,
                    room_unit=asset.room_unit,
                    area=asset.area,
                )
            ]

        labels = list(dict.fromkeys(
            location["location"]
            for location in locations
        ))

        assets.append({
            "id": asset.pk,
            "name": asset.name,
            "type": (
                asset.asset_category.name
                if asset.asset_category
                else None
            ),
            "category_id": asset.asset_category_id,
            "department": (
                asset.department.name
                if asset.department
                else None
            ),
            "department_id": asset.department_id,
            "status": asset.status,
            "serial_number": asset.serial_number,
            "purchase_date": (
                asset.purchase_date.isoformat()
                if asset.purchase_date
                else None
            ),
            "purchase_cost": float(asset.purchase_cost),
            "vendor": (
                asset.vendor.name
                if asset.vendor
                else None
            ),
            "vendor_id": asset.vendor_id,
            "assigned_to": (
                str(asset.assigned_to)
                if asset.assigned_to
                else None
            ),
            "assigned_to_id": asset.assigned_to_id,
            "warranty_end": (
                asset.warranty_end.isoformat()
                if asset.warranty_end
                else None
            ),
            "warranty_active": asset.is_warranty_active,
            "next_maintenance": (
                asset.next_maintenance.isoformat()
                if asset.next_maintenance
                else None
            ),
            "maintenance_due": asset.maintenance_due,
            "notes": asset.notes,
            "room_id": asset.room_id,
            "room_unit_id": asset.room_unit_id,
            "area": asset.area,
            "location": ", ".join(labels) or "Unassigned",
            "locations": locations,
            "image": (
                request.build_absolute_uri(asset.image.url)
                if asset.image
                else None
            ),
        })

    return JsonResponse({"assets": assets})
from pms.models import RoomUnit
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect
@login_required
@require_GET
def asset_room_options(request):
    """Return actual room units for the multiple-room selector."""
    rooms = (
        RoomUnit.objects
        .select_related("room")
        .order_by("room_number")
    )

    return JsonResponse({
        "rooms": [
            {
                "id": unit.pk,
                "room_id": unit.room_id,
                "room_number": unit.room_number,
                "room_type": unit.room.display_type(),
                "label": (
                    f"Room {unit.room_number}"
                    f" — {unit.room.display_type()}"
                ),
            }
            for unit in rooms
        ]
    })


@login_required
@require_POST
@csrf_protect

def save_asset_locations(request, asset_id):
    """
    Replace the complete current location set.

    Request:
    {
        "room_unit_ids": [1, 2, 3],
        "areas": ["Lobby"]
    }

    Previous assignments remain as historical records.
    """
    try:
        data = json.loads(request.body)

        if not isinstance(data, dict):
            raise ValueError

        room_ids = data.get("room_unit_ids")
        areas = data.get("areas", [])

        if not isinstance(room_ids, list):
            raise ValueError

        if not isinstance(areas, list):
            raise ValueError

        if any(
            type(room_id) is not int or room_id <= 0
            for room_id in room_ids
        ):
            raise ValueError

        if any(
            not isinstance(area, str)
            or len(area.strip()) > 200
            for area in areas
        ):
            raise ValueError

        room_ids = list(dict.fromkeys(room_ids))

        areas = list(dict.fromkeys(
            area.strip()
            for area in areas
            if area.strip()
        ))

        if len(room_ids) + len(areas) > 200:
            raise ValueError

    except (ValueError, TypeError):
        return JsonResponse(
            {
                "error": (
                    "Provide valid room IDs and areas. "
                    "Maximum 200 locations; each area may "
                    "contain up to 200 characters."
                )
            },
            status=400,
        )

    with transaction.atomic():
        # Serialize simultaneous assignment changes for this asset.
        asset = (
            HotelAsset.objects
            .select_for_update()
            .filter(pk=asset_id)
            .first()
        )

        if asset is None:
            return JsonResponse(
                {"error": "Asset not found."},
                status=404,
            )

        units = list(
            RoomUnit.objects
            .select_related("room")
            .filter(pk__in=room_ids)
        )

        if len(units) != len(room_ids):
            return JsonResponse(
                {
                    "error": (
                        "One or more selected rooms no longer exist. "
                        "Refresh the form and try again."
                    )
                },
                status=400,
            )

        AssetLocation.objects.filter(
            asset=asset,
            is_current=True,
        ).update(is_current=False)

        new_locations = [
            AssetLocation(
                asset=asset,
                room=unit.room,
                room_unit=unit,
                area="",
                is_current=True,
            )
            for unit in units
        ]

        new_locations.extend(
            AssetLocation(
                asset=asset,
                room=None,
                room_unit=None,
                area=area,
                is_current=True,
            )
            for area in areas
        )

        AssetLocation.objects.bulk_create(new_locations)

        # Keep legacy fields consistent without choosing an arbitrary
        # room when the asset has multiple current locations.
        asset.room = None
        asset.room_unit = None
        asset.area = ""

        if len(units) == 1 and not areas:
            asset.room = units[0].room
            asset.room_unit = units[0]

        elif len(areas) == 1 and not units:
            asset.area = areas[0]

        asset.save(update_fields=[
            "room",
            "room_unit",
            "area",
        ])

    return JsonResponse({
        "success": True,
        "location_count": len(room_ids) + len(areas),
    })


@csrf_exempt
def update_asset(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    asset = get_object_or_404(HotelAsset, pk=pk)

    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.POST
        image_file = request.FILES.get('image')
    else:
        data = json.loads(request.body)
        image_file = None

    for f in ['name', 'serial_number', 'purchase_cost', 'warranty_end',
              'next_maintenance', 'notes', 'purchase_date']:
        if f in data:
            setattr(asset, f, data[f])

    for f in ['asset_category_id', 'department_id', 'vendor_id', 'assigned_to_id']:
        if f in data:
            setattr(asset, f, data[f] or None)

    if image_file:
        asset.image = image_file
    elif data.get('remove_image') in ('1', 'true', 'True'):
        asset.image = None

    asset.save()

    return JsonResponse({
        'success': True,
        'id': asset.id,
        'image': request.build_absolute_uri(asset.image.url) if asset.image else None,
    })

@csrf_exempt
def update_asset_status(request, asset_id):
    err = _require_post(request)
    if err:
        return err
    data    = _json(request)
    updated = HotelAsset.objects.filter(pk=asset_id).update(status=data["status"])
    if not updated:
        return JsonResponse({"error": "Asset not found"}, status=404)
    return JsonResponse({"success": True})


@csrf_exempt
def list_assets_by_location(request):
    current_schema = connection.tenant.schema_name
    with schema_context(current_schema):
        qs = HotelAsset.objects.select_related("asset_category", "department", "room_unit", "room")
        asset_list = list(qs.order_by("name"))
        asset_ids  = [a.id for a in asset_list]

        all_locations = (
            AssetLocation.objects
            .filter(asset_id__in=asset_ids, is_current=True)
            .select_related("room", "room_unit")
            .order_by("asset_id", "-assigned_at")
        )
        from collections import defaultdict
        loc_map = defaultdict(list)
        for loc in all_locations:
            loc_map[loc.asset_id].append(loc)

        grouped = defaultdict(list)

        for a in asset_list:
            locs = loc_map.get(a.id, [])
            if locs:
                loc = locs[0]
                label = _room_label(loc.room)
                if label and loc.room_unit:
                    key = f"{label} – Unit {loc.room_unit.name}"
                    icon_type = "room"
                elif label:
                    key = label
                    icon_type = "room"
                elif loc.area and loc.area.strip():
                    key = loc.area.strip()
                    icon_type = "area"
                else:
                    key = "__unassigned__"
                    icon_type = "unset"
            elif a.area and a.area.strip():
                key = a.area.strip()
                icon_type = "area"
            elif a.room_id:
                key = _room_label(a.room) or "Unknown"
                icon_type = "room"
            else:
                key = "__unassigned__"
                icon_type = "unset"

            grouped[key].append({
                "id":          a.id,
                "name":        a.name,
                "type":        a.asset_category.name if a.asset_category else None,
                "status":      a.status,
                "department":  a.department.name if a.department else None,
                "icon_type":   icon_type,
                "room_id":     loc.room_id if locs else (a.room_id or None),
                "room_unit":   loc.room_unit.name if (locs and loc.room_unit) else (
                                   a.room_unit.name if a.room_unit else None
                               ),
            })

        result = []
        for loc_key, assets in sorted(grouped.items(), key=lambda x: (x[0] == "__unassigned__", x[0])):
            result.append({
                "location":   loc_key if loc_key != "__unassigned__" else None,
                "icon_type":  assets[0]["icon_type"],
                "room_id":    next((a["room_id"] for a in assets if a.get("room_id")), None),
                "room_units": list(dict.fromkeys(a["room_unit"] for a in assets if a.get("room_unit"))),
                "department": next((a["department"] for a in assets if a.get("department")), None),
                "assets":     assets,
            })

    return JsonResponse({"groups": result})


# ══════════════════════════════════════════════════════════════
# MAINTENANCE
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def add_maintenance_log(request):
    err = _require_post(request)
    if err:
        return err

    data = _json(request)
    staff = _get_staff(request)

    asset = None
    asset_id = data.get("asset_id")

    if asset_id:
        try:
            asset = HotelAsset.objects.get(id=asset_id)
        except HotelAsset.DoesNotExist:
            return JsonResponse({"error": "Asset not found"}, status=404)

    department_id = data.get("department_id") or (asset.department_id if asset else None)

    try:
        labour_cost = Decimal(str(data.get("labour_cost") or 0))
        parts_cost = Decimal(str(data.get("parts_cost") or 0))
        cost = Decimal(str(data.get("cost") or 0))
    except Exception:
        return JsonResponse({"error": "Invalid cost value"}, status=400)

    with transaction.atomic():
        log = MaintenanceLog.objects.create(
            asset=asset,
            department_id=department_id,
            custom_asset=data.get("custom_asset", ""),
            location=data.get("location", ""),
            maintenance_type=data.get("maintenance_type", "scheduled"),
            priority=data.get("priority", "low"),
            status=data.get("status", "completed"),
            description=data.get("description", ""),
            performed_by=data.get("performed_by", ""),
            performed_at=data.get("performed_at") or timezone.now(),
            duration=data.get("duration", ""),
            labour_cost=labour_cost,
            parts_cost=parts_cost,
            cost=cost,
            next_due=data.get("next_due") or None,
            parts_replaced=data.get("parts_replaced", ""),
            notes=data.get("notes", ""),
            recorded_by=staff,
        )

        # A maintenance cost above 0 always creates an expense, unless the
        # page explicitly sends create_expense: false.
        if data.get("create_expense", True) and cost > 0:
            category, _ = ExpenseCategory.objects.get_or_create(name="Maintenance")

            Expense.objects.get_or_create(
                maintenance_log=log,
                defaults={
                    "department_id": department_id,
                    "expense_category": category,
                    "source": "maintenance",
                    "amount": cost,
                    "description": (
                        "Maintenance — "
                        + (asset.name if asset else (data.get("custom_asset") or "Custom Asset"))
                    ),
                    "expense_date": timezone.now().date(),
                    "recorded_by": staff,
                },
            )

    return JsonResponse({"id": log.id}, status=201)

def list_maintenance_logs(request):
    qs = MaintenanceLog.objects.select_related(
        "asset", "asset__department", "department",
        "recorded_by", "recorded_by__department",
    )

    if request.GET.get("asset_id"):
        qs = qs.filter(asset_id=request.GET["asset_id"])

    def get_department(log):
        if log.department_id:
            return log.department.name
        if log.asset and log.asset.department:
            return log.asset.department.name
        if log.recorded_by and hasattr(log.recorded_by, 'department') and log.recorded_by.department:
            return log.recorded_by.department.name
        return None

    data = [
        {
            "id":             log.id,
            "asset":          log.asset.name if log.asset else None,
            "asset_id":       log.asset_id,
            "custom_asset":   log.custom_asset,
            "department":     get_department(log),
            "type":           log.maintenance_type,
            "priority":       log.priority,
            "status":         log.status,
            "description":    log.description,
            "location":       log.location,
            "cost":           float(log.cost),
            "labour_cost":    float(log.labour_cost),
            "parts_cost":     float(log.parts_cost),
            "performed_by":   log.performed_by,
            "performed_at":   log.performed_at.isoformat() if log.performed_at else None,
            "duration":       log.duration,
            "next_due":       str(log.next_due) if log.next_due else None,
            "parts_replaced": log.parts_replaced,
            "notes":          log.notes,
            "recorded_by":    str(log.recorded_by) if log.recorded_by else None,
        }
        for log in qs.order_by("-performed_at")
    ]

    return JsonResponse({"logs": data})


@csrf_exempt
def update_maintenance_status(request, log_id):
    err = _require_post(request)
    if err:
        return err

    data = _json(request)

    try:
        log = MaintenanceLog.objects.get(id=log_id)
    except MaintenanceLog.DoesNotExist:
        return JsonResponse({"error": "Maintenance log not found"}, status=404)

    status_value = data.get("status")
    valid_status = ["open", "in_progress", "completed", "cancelled"]

    if status_value not in valid_status:
        return JsonResponse({"error": "Invalid status"}, status=400)

    log.status = status_value
    if status_value == "completed" and not (log.performed_by or "").strip():
        staff = _get_staff(request)
        if staff:
            log.performed_by = staff.name
            log.save(update_fields=["status", "performed_by"])
        else:
            log.save(update_fields=["status"])
    else:
        log.save(update_fields=["status"])

    return JsonResponse({"success": True, "status": log.status})


@csrf_exempt
def edit_maintenance_log(request, log_id):
    err = _require_post(request)
    if err:
        return err

    data = _json(request)

    try:
        with transaction.atomic():
            # Lock only the log row. Joining nullable tables (asset,
            # recorded_by) with select_for_update() is what caused the
            # "FOR UPDATE cannot be applied to the nullable side of an
            # outer join" error.
            log = (
                MaintenanceLog.objects
                .select_for_update()
                .get(id=log_id)
            )

            try:
                new_labour = Decimal(str(data.get("labour_cost", log.labour_cost) or 0))
                new_parts = Decimal(str(data.get("parts_cost", log.parts_cost) or 0))
                new_cost = Decimal(str(data.get("cost", log.cost) or 0))
            except Exception:
                return JsonResponse({"error": "Invalid cost value"}, status=400)

            if new_labour < 0 or new_parts < 0 or new_cost < 0:
                return JsonResponse({"error": "Costs cannot be negative"}, status=400)

            log.description = data.get("description", log.description)
            log.priority = data.get("priority", log.priority)
            log.labour_cost = new_labour
            log.parts_cost = new_parts
            log.cost = new_cost
            log.next_due = data.get("next_due") or None
            log.notes = data.get("notes", log.notes)
            log.save()

            # Keep the linked expense in step with the log's cost.
            expense = Expense.objects.filter(maintenance_log=log).first()

            if new_cost > 0:
                asset_name = (
                    log.asset.name if log.asset
                    else (log.custom_asset or "Custom Asset")
                )
                if expense:
                    expense.amount = new_cost
                    expense.description = f"Maintenance — {asset_name}"
                    expense.save(update_fields=["amount", "description"])
                else:
                    category, _ = ExpenseCategory.objects.get_or_create(name="Maintenance")
                    Expense.objects.create(
                        maintenance_log=log,
                        department_id=log.department_id or (log.asset.department_id if log.asset else None),
                        expense_category=category,
                        source="maintenance",
                        amount=new_cost,
                        description=f"Maintenance — {asset_name}",
                        expense_date=(log.performed_at or timezone.now()).date(),
                        recorded_by=log.recorded_by,
                    )
            elif expense:
                # Cost set to 0: remove the expense so totals stay correct.
                expense.delete()

        return JsonResponse({"success": True})

    except MaintenanceLog.DoesNotExist:
        return JsonResponse({"error": "Maintenance log not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)


@csrf_exempt
def delete_maintenance_log(request, log_id):
    err = _require_post(request)
    if err:
        return err

    try:
        log = MaintenanceLog.objects.get(id=log_id)
    except MaintenanceLog.DoesNotExist:
        return JsonResponse({"error": "Maintenance log not found"}, status=404)

    log.delete()
    return JsonResponse({"success": True})


# ══════════════════════════════════════════════════════════════
# LAUNDRY
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def add_laundry_service(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    data = json.loads(request.body)

    obj = LaundryService.objects.create(
        name=data["name"],
        service_type=data["service_type"],
        price_per_unit=data["price_per_unit"],
        turnaround_hours=data.get("turnaround_hours", 24)
    )

    return JsonResponse({"id": obj.id})


def list_laundry_services(request):
    return JsonResponse({"services": list(LaundryService.objects.values())})


@csrf_exempt
def create_laundry_order(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    data = json.loads(request.body)

    booking_id = data.get("booking_id")
    booking = None

    if booking_id:
        booking = Booking.objects.filter(id=booking_id).first()

    order = LaundryOrder.objects.create(
        room_number=data["room_number"],
        guest_name=data.get("guest_name", ""),
        booking=booking,
        order_type=data.get("order_type", "guest_laundry")
    )

    total = Decimal("0")

    for i in data.get("items", []):
        service = LaundryService.objects.get(id=i["service_id"])
        qty = Decimal(str(i["quantity"]))
        price = service.price_per_unit
        LaundryOrderItem.objects.create(
            order=order,
            service=service,
            item_name=i.get("item_name", service.name),
            quantity=qty,
            unit_price=price
        )
        total += qty * price

    order.total_amount = total
    order.save()

    if booking:
        folio, _ = GuestFolio.objects.get_or_create(booking=booking)
        if folio.status == "open":
            FolioCharge.objects.create(
                folio=folio,
                charge_type='laundry',
                description=f'Laundry Order #{order.id}',
                amount=total,
                tax_amount=Decimal("0"),
                added_by=None
            )

    return JsonResponse({
        "order_id": order.id,
        "total": float(total),
        "booking_id": booking.id if booking else None
    })


def list_laundry_orders(request):
    data = []

    for o in LaundryOrder.objects.select_related(
        'booking', 'delivered_by'
    ).prefetch_related(
        'items__service', 'logs__updated_by'
    ).all().order_by('-id'):

        logs = o.logs.all().order_by('-created_at')
        delivered_log = logs.filter(status="delivered").first()

        delivered_by = ""
        if delivered_log and delivered_log.updated_by:
            delivered_by = delivered_log.updated_by.name

        last_log = logs.first()

        services = []
        for item in o.items.all():
            services.append({
                "service_name": item.service.name if item.service else item.item_name,
                "qty": float(item.quantity),
            })

        data.append({
            "id": o.id,
            "room_number": o.room_number,
            "guest_name": o.guest_name or "",
            "status": o.status,
            "order_type": o.order_type or "",
            "total": float(o.total_amount),
            "items_count": o.items.count(),
            "created_at": o.created_at.isoformat() if o.created_at else "",
            "delivered_by": delivered_by,
            "services": services,
            "status_updated_by": (
                last_log.updated_by.name if last_log and last_log.updated_by else ""
            ),
        })

    return JsonResponse({"orders": data})


@csrf_exempt
def update_laundry_status(request, order_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    data = json.loads(request.body)

    new_status = data.get("status")
    staff_id   = data.get("staff_id")
    note       = data.get("note", "")

    try:
        order = LaundryOrder.objects.get(id=order_id)
    except LaundryOrder.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    staff = None
    if staff_id:
        staff = Staff.objects.filter(id=staff_id).first()
    if not staff and request.user.is_authenticated:
        staff = Staff.objects.filter(user=request.user).first()

    order.status = new_status
    if new_status == "delivered" and staff:
        order.delivered_by = staff
    order.save()

    LaundryStatusLog.objects.create(
        order=order, status=new_status, note=note, updated_by=staff
    )

    return JsonResponse({
        "success": True,
        "status": order.status,
        "updated_by": staff.name if staff else None,
        "delivered_by": order.delivered_by.name if order.delivered_by else None,
    })


# ══════════════════════════════════════════════════════════════
# MODAL / META DATA
# ══════════════════════════════════════════════════════════════

def get_modal_data(request):
    staff = _get_staff(request)
    categories = list(ItemCategory.objects.values('id', 'name').order_by('name'))
    vendors    = list(Vendor.objects.values('id', 'name').order_by('name'))

    if not staff or _is_admin(staff):
        seen = set()
        depts = []
        for d in Department.objects.all().order_by('name', 'id'):
            key = d.name.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            depts.append({'id': d.id, 'name': d.name})
    elif staff.department:
        depts = [{'id': staff.department.id, 'name': staff.department.name}]
    else:
        depts = []

    return JsonResponse({'categories': categories, 'vendors': vendors, 'departments': depts})


def inventory_meta(request):
    vendors      = Vendor.objects.all().order_by('name')
    items        = InventoryItem.objects.all().order_by('name')
    item_cats    = ItemCategory.objects.all().order_by('name')
    asset_cats   = AssetCategory.objects.all().order_by('name')
    expense_cats = ExpenseCategory.objects.all().order_by('name')

    seen = set()
    depts = []
    for d in Department.objects.all().order_by('name', 'id'):
        key = d.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        depts.append({"id": d.id, "name": d.name})

    return JsonResponse({
        "vendors": [{"id": v.id, "name": v.name} for v in vendors],
        "departments": depts,
        "items": [
            {
                "id":            i.id,
                "name":          i.name,
                "unit":          i.unit or "",
                "stock":         float(i.current_stock or 0),
                "cost_per_unit": float(i.cost_per_unit or 0),
            }
            for i in items
        ],
        "categories": [{"id": c.id, "name": c.name} for c in item_cats],
        "asset_categories": [{"id": c.id, "name": c.name} for c in asset_cats],
        "expense_categories": [{"id": c.id, "name": c.name} for c in expense_cats],
    })


# ══════════════════════════════════════════════════════════════
# HOTEL LINEN BATCHES
# ══════════════════════════════════════════════════════════════

def _batch_dict(b):
    items = list(b.items.select_related('missing_reason').all())

    total_pieces    = sum(i.quantity for i in items)
    received_pieces = sum(i.received_quantity for i in items)
    missing_pieces  = sum(
        i.quantity - i.received_quantity for i in items if i.received_quantity < i.quantity
    )
    missing_cost = sum(
        (i.quantity - i.received_quantity) * i.item_price
        for i in items if i.received_quantity < i.quantity
    )
    total_cost = sum(i.quantity * i.item_price for i in items)

    return {
        'id':               b.id,
        'batch_code':       f'LB{str(b.id).zfill(3)}',
        'dispatched_by':    b.dispatched_by.name if b.dispatched_by else '',
        'dispatched_by_id': b.dispatched_by_id,
        'sent_to_laundry':  b.sent_to_laundry,
        'laundry_contact':  b.laundry_contact,
        'laundry_phone':    b.laundry_phone,
        'note':             b.note,
        'status':           b.status,
        'total_pieces':     total_pieces,
        'received_pieces':  received_pieces,
        'missing_pieces':   missing_pieces,
        'total_cost':       float(total_cost),
        'missing_cost':     float(missing_cost),
        'payable_amount':   float(total_cost - missing_cost),
        'dispatched_at':    b.dispatched_at.isoformat() if b.dispatched_at else '',
        'received_at':      b.received_at.isoformat() if b.received_at else '',
        'received_by':      b.received_by.name if b.received_by else '',
        'received_by_id':   b.received_by_id,
        'expected_return_date': (
            b.expected_return_date.isoformat()
            if hasattr(b.expected_return_date, 'isoformat')
            else (b.expected_return_date or '')
        ),
        'items': [
            {
                'id':                i.id,
                'label':             i.item_label,
                'quantity':          i.quantity,
                'item_price':        float(i.item_price),
                'received_quantity': i.received_quantity,
                'missing':           i.quantity - i.received_quantity,
                'missing_cost':      float((i.quantity - i.received_quantity) * i.item_price),
                'damaged_quantity':  i.damaged_quantity,
                'missing_reason_id': i.missing_reason_id,
                'missing_reason':    i.missing_reason.label if i.missing_reason else None,
                'missing_note':      i.missing_note,
                'received':          i.received,
                'is_partial':        i.is_partial,
                'received_at':       i.received_at.isoformat() if i.received_at else '',
            }
            for i in items
        ],
    }


def _resolve_staff(data, request):
    if data.get('staff_id'):
        return Staff.objects.filter(id=data['staff_id']).first()
    if request.user.is_authenticated:
        return Staff.objects.filter(user=request.user).first()
    return None


def _update_batch_status(batch, data, request):
    all_items = list(batch.items.all())
    total    = sum(i.quantity for i in all_items)
    received = sum(i.received_quantity for i in all_items)

    if received == 0:
        batch.status      = 'dispatched'
        batch.received_at = None
        batch.received_by = None
    elif received < total:
        batch.status = 'partial'
        if not batch.received_at:
            batch.received_at = now()
            batch.received_by = _resolve_staff(data, request)
    else:
        batch.status = 'received'
        if not batch.received_at:
            batch.received_at = now()
        batch.received_by = _resolve_staff(data, request)

    batch.save()
    _sync_linen_expense(batch, _resolve_staff(data, request))
    return total, received


def _sync_linen_expense(batch, recorded_by_staff):
    items = list(batch.items.all())

    total_cost = sum(i.quantity * i.item_price for i in items)
    missing_cost = sum(
        (i.quantity - i.received_quantity) * i.item_price
        for i in items if i.received_quantity < i.quantity
    )
    payable = total_cost - missing_cost

    # Nothing to pay yet (still dispatched, no prices, or everything missing).
    if batch.status == 'dispatched' or total_cost <= 0 or payable <= 0:
        Expense.objects.filter(linen_batch=batch).delete()
        return

    laundry_category, _ = ExpenseCategory.objects.get_or_create(
        name='Laundry', defaults={'budget': 0}
    )

    # Put the expense under the laundry / housekeeping department if one exists.
    laundry_dept = (
        Department.objects
        .filter(Q(name__icontains="laundry") | Q(name__icontains="housekeeping"))
        .order_by("id")
        .first()
    )

    description = (
        f"Laundry payment — Batch LB{str(batch.id).zfill(3)} | "
        f"{batch.sent_to_laundry} ({batch.laundry_contact} {batch.laundry_phone}) | "
        f"Total: {total_cost}, Missing deduction: {missing_cost}, Payable: {payable}"
    )

    expense = Expense.objects.filter(linen_batch=batch).first()

    if expense is None:
        Expense.objects.create(
            linen_batch=batch,
            department=laundry_dept,
            source='laundry',
            expense_category=laundry_category,
            amount=Decimal(str(payable)),
            description=description,
            expense_date=now().date(),
            recorded_by=recorded_by_staff,
        )
    else:
        # Keep the original date and recorder; only refresh the amounts.
        expense.amount = Decimal(str(payable))
        expense.description = description
        expense.expense_category = laundry_category
        if expense.department_id is None and laundry_dept:
            expense.department = laundry_dept
        if expense.recorded_by_id is None and recorded_by_staff:
            expense.recorded_by = recorded_by_staff
        expense.save()

@csrf_exempt
def dispatch_linen_batch(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)

    raw_items = [
        i for i in data.get('items', [])
        if i.get('label', '').strip() and int(i.get('quantity', 0)) > 0
    ]
    if not raw_items:
        return JsonResponse({'error': 'At least one item with quantity > 0 required'}, status=400)

    staff = _resolve_staff(data, request)

    batch = HotelLinenBatch.objects.create(
        dispatched_by   = staff,
        sent_to_laundry = data.get('sent_to_laundry', '').strip(),
        laundry_contact = data.get('laundry_contact', '').strip(),
        laundry_phone   = data.get('laundry_phone', '').strip(),
        note            = data.get('note', '').strip(),
        expected_return_date = data.get('expected_return_date') or None,
    )

    for i in raw_items:
        HotelLinenBatchItem.objects.create(
            batch      = batch,
            item_label = i['label'].strip(),
            quantity   = int(i['quantity']),
            item_price = Decimal(str(i.get('item_price', 0))),
        )

    return JsonResponse(_batch_dict(batch), status=201)


def list_linen_batches(request):
    qs = HotelLinenBatch.objects.select_related(
        'dispatched_by', 'received_by'
    ).prefetch_related('items__missing_reason')

    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)

    return JsonResponse({'batches': [_batch_dict(b) for b in qs]})


def linen_batch_detail(request, batch_id):
    try:
        b = HotelLinenBatch.objects.select_related(
            'dispatched_by', 'received_by'
        ).prefetch_related('items__missing_reason').get(id=batch_id)
    except HotelLinenBatch.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    return JsonResponse(_batch_dict(b))


@csrf_exempt
def mark_item_received(request, batch_id, item_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)

    try:
        item = HotelLinenBatchItem.objects.select_related('batch').get(id=item_id, batch_id=batch_id)
    except HotelLinenBatchItem.DoesNotExist:
        return JsonResponse({'error': 'Item not found'}, status=404)

    if 'received_quantity' in data:
        recv_qty = max(0, min(int(data['received_quantity']), item.quantity))
        item.received_quantity = recv_qty
        item.received_at       = now() if recv_qty > 0 else None

        if recv_qty < item.quantity:
            reason_id             = data.get('missing_reason_id')
            item.missing_reason   = LinenMissingReason.objects.filter(id=reason_id, is_active=True).first() if reason_id else item.missing_reason
            item.missing_note     = data.get('missing_note', item.missing_note)
            item.missing_quantity = item.quantity - recv_qty
            item.damaged_quantity = max(0, int(data.get('damaged_quantity', item.damaged_quantity or 0)))
        else:
            item.missing_reason   = None
            item.missing_note     = ''
            item.missing_quantity = 0
            item.damaged_quantity = 0

        item.save()
        total, received = _update_batch_status(item.batch, data, request)

    else:
        if 'missing_reason_id' in data:
            reason_id           = data.get('missing_reason_id')
            item.missing_reason = LinenMissingReason.objects.filter(id=reason_id, is_active=True).first() if reason_id else None
        if 'missing_note' in data:
            item.missing_note = data.get('missing_note', '')
        item.save()

        all_items = list(item.batch.items.all())
        total     = sum(i.quantity for i in all_items)
        received  = sum(i.received_quantity for i in all_items)

    return JsonResponse({
        'item_id':           item.id,
        'received_quantity': item.received_quantity,
        'missing':           item.quantity - item.received_quantity,
        'missing_cost':      float(item.missing_cost),
        'damaged_quantity':  item.damaged_quantity,
        'missing_reason':    item.missing_reason.label if item.missing_reason else None,
        'received':          item.received,
        'is_partial':        item.is_partial,
        'batch_status':      item.batch.status,
        'batch_missing':     total - received,
        'batch_received_at': item.batch.received_at.isoformat() if item.batch.received_at else None,
        'batch_received_by': item.batch.received_by.name if item.batch.received_by else None,
    })


@csrf_exempt
def confirm_batch_received(request, batch_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data = json.loads(request.body)

    try:
        batch = HotelLinenBatch.objects.prefetch_related('items').get(id=batch_id)
    except HotelLinenBatch.DoesNotExist:
        return JsonResponse({'error': 'Batch not found'}, status=404)

    if batch.status == 'received':
        return JsonResponse({'error': 'Already marked received'}, status=400)

    staff = _resolve_staff(data, request)
    stamp = now()

    for item in batch.items.all():
        if item.received_quantity < item.quantity:
            item.received_quantity = item.quantity
            item.received_at       = stamp
            item.missing_quantity  = 0
            item.save()

    batch.status      = 'received'
    batch.received_at = stamp
    batch.received_by = staff
    batch.save()

    _sync_linen_expense(batch, staff)

    return JsonResponse(_batch_dict(batch))


def list_missing_reasons(request):
    reasons = LinenMissingReason.objects.filter(is_active=True)
    return JsonResponse({
        'reasons': [
            {'id': r.id, 'label': r.label, 'order': r.order, 'is_active': r.is_active}
            for r in reasons
        ]
    })


@csrf_exempt
def manage_missing_reason(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    data  = json.loads(request.body)
    label = data.get('label', '').strip()

    if not label:
        return JsonResponse({'error': 'label is required'}, status=400)
    if LinenMissingReason.objects.filter(label__iexact=label).exists():
        return JsonResponse({'error': 'Reason already exists'}, status=400)

    reason = LinenMissingReason.objects.create(label=label, order=int(data.get('order', 0)))
    return JsonResponse(
        {'id': reason.id, 'label': reason.label, 'order': reason.order, 'is_active': reason.is_active},
        status=201
    )


@csrf_exempt
def update_missing_reason(request, reason_id):
    try:
        reason = LinenMissingReason.objects.get(id=reason_id)
    except LinenMissingReason.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if request.method == 'DELETE':
        reason.is_active = False
        reason.save()
        return JsonResponse({'deleted': True})

    if request.method == 'PATCH':
        data = json.loads(request.body)
        if 'label' in data:
            new_label = data['label'].strip()
            if not new_label:
                return JsonResponse({'error': 'label cannot be empty'}, status=400)
            if new_label.lower() != reason.label.lower():
                if LinenMissingReason.objects.filter(label__iexact=new_label).exists():
                    return JsonResponse({'error': 'Reason already exists'}, status=400)
            reason.label = new_label
        if 'order' in data:
            reason.order = int(data['order'])
        if 'is_active' in data:
            reason.is_active = bool(data['is_active'])
        reason.save()
        return JsonResponse({
            'id': reason.id, 'label': reason.label,
            'order': reason.order, 'is_active': reason.is_active
        })

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def seed_missing_reasons(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    defaults = [
        ('Damaged at laundry',  1),
        ('Lost in transit',     2),
        ('Suspected stolen',    3),
        ('Left in room',        4),
        ('Held for re-washing', 5),
        ('Laundry error',       6),
    ]

    created = []
    skipped = []
    for label, order in defaults:
        obj, was_created = LinenMissingReason.objects.get_or_create(
            label=label, defaults={'order': order, 'is_active': True}
        )
        (created if was_created else skipped).append(label)

    return JsonResponse({
        'created': created,
        'skipped': skipped,
        'message': f'{len(created)} added, {len(skipped)} already existed',
    })


# ══════════════════════════════════════════════════════════════
# PAGE
# ══════════════════════════════════════════════════════════════

@login_required
@never_cache
def inventory_items_page(request):
    """
    Inventory "Items & stock" page. Extends the shared admin shell.
    All data (categories, departments, vendors, items) loads client-side
    via the existing inventory JSON APIs (list_inventory, list_categories,
    departments, list_vendors, add_inventory_item, update_inventory_item,
    delete_inventory_item, stock_adjust, add_category), so this view
    stays cheap to render.
    """
    return render(request, "hotel/items.html", {})

@csrf_exempt
def update_vendor(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    vendor = get_object_or_404(Vendor, pk=pk)
    data = _json(request)

    for f in ['name', 'contact_person', 'phone', 'email', 'address']:
        if f in data:
            setattr(vendor, f, data[f])

    vendor.save()
    return JsonResponse({'success': True, 'id': vendor.id})


@csrf_exempt
def delete_vendor(request, pk):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    get_object_or_404(Vendor, pk=pk).delete()
    return JsonResponse({'success': True})


@login_required
@never_cache
def vendors_page(request):
    """
    Vendors management page. Extends the shared admin shell.
    All data loads client-side via list_vendors, add_vendor,
    update_vendor, delete_vendor — same pattern as inventory_items_page.
    """
    return render(request, "hotel/vendors.html", {})

@login_required
@never_cache
def purchase_orders_page(request):
    return render(request, "hotel/purchase_orders.html", {})
@login_required
@never_cache
def assets_page(request):
    """
    Asset Tracking page. Extends the shared admin shell.
    All data (asset categories, departments, vendors, assets, locations)
    loads client-side via the existing asset JSON APIs (list_assets,
    list_asset_categories, departments, list_vendors, add_asset,
    update_asset, update_asset_status, bulk_add_assets,
    list_assets_by_location, assign_room_to_assets), so this view
    stays cheap to render.
    """
    return render(request, "hotel/assets.html", {})

@login_required
@never_cache
def maintenance_page(request):
    def get_choices(field_name, fallback):
        choices = list(
            MaintenanceLog._meta.get_field(field_name).flatchoices
        )

        return [
            [str(value), str(label)]
            for value, label in choices
        ] or fallback

    context = {
        "maintenance_choices": {
            "types": get_choices(
                "maintenance_type",
                [["scheduled", "Scheduled"]],
            ),
            "priorities": get_choices(
                "priority",
                [
                    ["low", "Low"],
                    ["medium", "Medium"],
                    ["high", "High"],
                ],
            ),
            "statuses": [
                ["open", "Open"],
                ["in_progress", "In progress"],
                ["completed", "Completed"],
                ["cancelled", "Cancelled"],
            ],
        },
    }

    return render(
        request,
        "hotel/maintenance.html",
        context,
    )


@login_required
@never_cache
def expenses_page(request):
    return render(
        request,
        "hotel/expenses.html",
        {},
    )


@login_required
@never_cache
def laundry_orders_page(request):
    return render(request, "hotel/laundry_orders.html")

@login_required
@never_cache
def laundry_services_page(request):
    """
    Laundry Services setup page. Extends the shared admin shell.
    All data loads client-side via list_laundry_services and
    add_laundry_service — same pattern as vendors_page.
    """
    return render(request, "hotel/laundry_services.html", {})
    
@login_required
@never_cache
def laundry_report_page(request):
    """
    Laundry Report page. Extends the shared admin shell.
    Summary data (totals, by status, by type, by date range) loads
    client-side via a dedicated laundry_report JSON endpoint.
    """
    return render(request, "hotel/laundry_report.html", {})

@login_required
@never_cache
def inventory_overview_page(request):
    """
    Inventory Overview dashboard. Extends the shared admin shell.
    Pulls together stat cards, low stock alerts, expenses by department,
    recent stock adjustments and quick actions — all client-side via the
    existing inventory JSON APIs (list_inventory, list_purchase_orders,
    expense_summary, list_stock_adjustments), so this view stays cheap
    to render.
    """
    return render(request, "hotel/inventory_overview.html", {})


from datetime import timedelta

def expense_daily_summary(request):
    """
    Daily expense totals for the Expense Trends chart.
    Query params: days (default 30, max 365), department_id (optional).
    Returns one series per department, all keyed to the same date list.
    """
    try:
        days = int(request.GET.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))

    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)

    qs = Expense.objects.filter(expense_date__gte=start_date, expense_date__lte=end_date)

    dept_id = request.GET.get("department_id")
    if dept_id:
        qs = qs.filter(department_id=dept_id)

    rows = (
        qs.values("expense_date", "department_id", "department__name")
          .annotate(total=Sum("amount"))
    )

    by_date = defaultdict(lambda: defaultdict(float))
    dept_names = {}
    for r in rows:
        key = r["department_id"] or 0
        dept_names[key] = r["department__name"] or "Unassigned"
        by_date[r["expense_date"]][key] += float(r["total"] or 0)

    dates = []
    d = start_date
    while d <= end_date:
        dates.append(d)
        d += timedelta(days=1)

    dept_keys = sorted(dept_names.keys(), key=lambda k: dept_names[k])
    series = [
        {
            "department_id": k or None,
            "department": dept_names[k],
            "totals": [round(by_date[d].get(k, 0), 2) for d in dates],
        }
        for k in dept_keys
    ]

    return JsonResponse({
        "dates": [d.isoformat() for d in dates],
        "series": series,
        "grand_totals": [round(sum(by_date[d].values()), 2) for d in dates],
    })