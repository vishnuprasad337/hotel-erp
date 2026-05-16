import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import (
    ItemCategory, Vendor, InventoryItem,
    StockAdjustment, PurchaseOrder, PurchaseItem,
    LaundryService, LaundryOrder, LaundryOrderItem, LaundryStatusLog
)

import json
from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Q, F, Count

from .models import (
    ItemCategory, Vendor, InventoryItem,
    StockAdjustment, PurchaseOrder, PurchaseItem,
    ExpenseCategory, Expense,
    AssetCategory, HotelAsset, MaintenanceLog,
)


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _json(request):
    return json.loads(request.body)


def _require_post(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)


def _get_staff(request):
    
    from accounts.models import Staff
    try:
        return Staff.objects.get(user=request.user) if request.user.is_authenticated else None
    except Staff.DoesNotExist:
        return None



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
# INVENTORY ITEMS
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def add_inventory_item(request):
   
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    obj = InventoryItem.objects.create(
        category_id=data.get("category_id"),
        department_id=data.get("department_id"),
        name=data.get("name"),
        unit=data.get("unit", "piece"),
        current_stock=data.get("current_stock", 0),
        minimum_stock=data.get("minimum_stock", 10),
        cost_per_unit=data.get("cost_per_unit", 0),
        vendor_id=data.get("vendor_id"),
    )
    return JsonResponse({"id": obj.id}, status=201)


def list_inventory(request):
   
    qs = InventoryItem.objects.select_related("category", "department", "vendor")

    dept_id = request.GET.get("department_id")
    if dept_id:
        qs = qs.filter(department_id=dept_id)

    if request.GET.get("low_stock") == "1":
        qs = qs.filter(current_stock__lte=F("minimum_stock"))

    data = [
        {
            "id":            i.id,
            "name":          i.name,
            "category":      i.category.name if i.category else None,
            "department":    i.department.name if i.department else None,
            "department_id": i.department_id,
            "unit":          i.unit,
            "stock":         float(i.current_stock),
            "min_stock":     float(i.minimum_stock),
            "cost_per_unit": float(i.cost_per_unit),
            "vendor":        i.vendor.name if i.vendor else None,
            "low_stock":     i.is_low_stock,
            "stock_value":   float(i.stock_value),
        }
        for i in qs
    ]
    return JsonResponse({"items": data})


def inventory_by_department(request):
   
    rows = (
        InventoryItem.objects
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


# ══════════════════════════════════════════════════════════════
# STOCK ADJUSTMENTS
# ══════════════════════════════════════════════════════════════

@csrf_exempt
def stock_adjust(request):
    
    err = _require_post(request)
    if err:
        return err
    data  = _json(request)
    staff = _get_staff(request)  # FIX: was never set in original view

    item = InventoryItem.objects.get(id=data["item_id"])
    qty  = Decimal(str(data["quantity"]))
    typ  = data["type"]

    if typ == "in":
        item.current_stock += qty
    elif typ == "out":
        item.current_stock -= qty
    else:                          
        item.current_stock = qty

    item.save()

    StockAdjustment.objects.create(
        item=item,
        adjustment_type=typ,
        quantity=qty,
        note=data.get("note", ""),
        adjusted_by=staff,         # FIX: model has FK to accounts.Staff
    )
    return JsonResponse({"success": True, "new_stock": float(item.current_stock)})


def list_stock_adjustments(request):
    qs = StockAdjustment.objects.select_related(
        "item", "item__department", "adjusted_by", "adjusted_by__department"  # add this
    )

    if request.GET.get("item_id"):
        qs = qs.filter(item_id=request.GET["item_id"])
    if request.GET.get("department_id"):
        qs = qs.filter(item__department_id=request.GET["department_id"])

    data = [
        {
            "id":                      a.id,
            "item":                    a.item.name,
            "department":              a.item.department.name if a.item.department else None,
            "type":                    a.adjustment_type,
            "quantity":                float(a.quantity),
            "note":                    a.note,
            "adjusted_by":             str(a.adjusted_by) if a.adjusted_by else None,
            "adjusted_by_department":  a.adjusted_by.department.name if a.adjusted_by and a.adjusted_by.department else None,  # add this
            "date":                    a.created_at.isoformat(),
        }
        for a in qs.order_by("-created_at")[:100]
    ]
    return JsonResponse({"adjustments": data})



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

        category, _ = ExpenseCategory.objects.get_or_create(
            name="Purchase"
        )

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

    return JsonResponse({
        "success": True,
        "status": po.status
    })


def list_purchase_orders(request):

    qs = PurchaseOrder.objects.select_related(
        "vendor", "department", "ordered_by", "approved_by"
    ).prefetch_related("items__item")  

    if request.GET.get("department_id"):
        qs = qs.filter(department_id=request.GET["department_id"])
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])

    data = []
    for po in qs.order_by("-ordered_at"):
        lines = [
            {
                "id":         pi.id,
                "item_id":    pi.item_id,
                "item_name":  pi.item.name if pi.item else "—",
                "quantity":   float(pi.quantity),
                "unit":       pi.item.unit if pi.item else "",
                "unit_price": float(pi.unit_price),
                "total":      float(pi.subtotal),
            }
            for pi in po.items.all()
        ]
        data.append({
            "id":            po.id,
            "vendor":        po.vendor.name,
            "department":    po.department.name if po.department else None,
            "department_id": po.department_id,
            "status":        po.status,
            "total":         float(po.total_amount),
            "note":          po.note,
            "ordered_by":    str(po.ordered_by) if po.ordered_by else None,
            "approved_by":   str(po.approved_by) if po.approved_by else None,
            "ordered_at":    po.ordered_at.isoformat(),
            "received_at":   po.received_at.isoformat() if po.received_at else None,
            "lines":         lines,
        })

    return JsonResponse({"purchase_orders": data})

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
def add_asset_category(request):
    
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    obj = AssetCategory.objects.create(name=data["name"])
    return JsonResponse({"id": obj.id, "name": obj.name}, status=201)


def list_asset_categories(request):
   
    return JsonResponse({"asset_categories": list(AssetCategory.objects.values())})



@csrf_exempt
def add_asset(request):
    
    err = _require_post(request)
    if err:
        return err
    data = _json(request)
    asset = HotelAsset.objects.create(
        name=data["name"],
        asset_category_id=data.get("asset_category_id"),
        department_id=data.get("department_id"),
        serial_number=data.get("serial_number", ""),
        
        room_unit_id=data.get("room_unit_id"),
        room_id=data.get("room_id"),
        area=data.get("area", ""),
        purchase_date=data.get("purchase_date"),
        purchase_cost=data.get("purchase_cost", 0),
        vendor_id=data.get("vendor_id"),
        warranty_end=data.get("warranty_end"),
        next_maintenance=data.get("next_maintenance"),
        assigned_to_id=data.get("assigned_to_id"),
        notes=data.get("notes", ""),
    )
    return JsonResponse({"id": asset.id}, status=201)


def list_assets(request):
    
    qs = HotelAsset.objects.select_related(
        "asset_category", "department", "vendor", "assigned_to",
        "room_unit", "room",
    )

    if request.GET.get("department_id"):
        qs = qs.filter(department_id=request.GET["department_id"])
    if request.GET.get("status"):
        qs = qs.filter(status=request.GET["status"])
    if request.GET.get("type_id"):
        qs = qs.filter(asset_category_id=request.GET["type_id"])

    data = [
        {
            "id":               a.id,
            "name":             a.name,
            "type":             a.asset_category.name if a.asset_category else None,
            "department":       a.department.name if a.department else None,
            "department_id":    a.department_id,
           
            "location":         a.location_display,
            "room_unit_id":     a.room_unit_id,
            "room_id":          a.room_id,
            "area":             a.area,
            "status":           a.status,
            "serial_number":    a.serial_number,
            "purchase_date":    str(a.purchase_date) if a.purchase_date else None,
            "purchase_cost":    float(a.purchase_cost),
            "vendor":           a.vendor.name if a.vendor else None,
            "warranty_end":     str(a.warranty_end) if a.warranty_end else None,
            "warranty_active":  a.is_warranty_active,
            "next_maintenance": str(a.next_maintenance) if a.next_maintenance else None,
            "maintenance_due":  a.maintenance_due,
            "assigned_to":      str(a.assigned_to) if a.assigned_to else None,
        }
        for a in qs.order_by("name")
    ]
    return JsonResponse({"assets": data})


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



from decimal import Decimal
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone


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

    log = MaintenanceLog.objects.create(
        asset=asset,
        department_id=data.get("department_id") or (asset.department_id if asset else None),
        custom_asset=data.get("custom_asset", ""),
        location=data.get("location", ""),

        maintenance_type=data.get("maintenance_type", "scheduled"),
        priority=data.get("priority", "low"),
        status=data.get("status", "completed"),
        description=data.get("description", ""),
        performed_by=data.get("performed_by", ""),
        performed_at=data.get("performed_at") or timezone.now(),
        duration=data.get("duration", ""),
        labour_cost=Decimal(str(data.get("labour_cost", 0))),
        parts_cost=Decimal(str(data.get("parts_cost", 0))),
        cost=Decimal(str(data.get("cost", 0))),
        next_due=data.get("next_due") or None,
        parts_replaced=data.get("parts_replaced", ""),
        notes=data.get("notes", ""),
        recorded_by=staff,
    )

    cost = Decimal(str(data.get("cost", 0)))

    if data.get("create_expense") and cost > 0:

        category, _ = ExpenseCategory.objects.get_or_create(
            name="Maintenance"
        )

        Expense.objects.create(
             maintenance_log=log,

            department_id=data.get("department_id") or (asset.department_id if asset else None),

            expense_category=category,

            source="maintenance",

            amount=cost,

            description=f"Maintenance — {(asset.name if asset else data.get('custom_asset', 'Custom Asset'))}",

            expense_date=timezone.now().date(),

            recorded_by=staff,
        )

    return JsonResponse({"id": log.id}, status=201)
def list_maintenance_logs(request):
    qs = MaintenanceLog.objects.select_related(
        "asset",
        "asset__department",
        "department",
        "recorded_by",
        "recorded_by__department",  
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
        return JsonResponse(
            {"error": "Maintenance log not found"},
            status=404
        )

    status_value = data.get("status")

    valid_status = [
        "open",
        "in_progress",
        "completed",
        "cancelled"
    ]

    if status_value not in valid_status:
        return JsonResponse(
            {"error": "Invalid status"},
            status=400
        )

    log.status = status_value
    if status_value=="completed" and not (log.performed_by or "").strip():
        staff =_get_staff(request)
        if staff:
            log.performed_by=staff.name
            log.save(update_fields=["status","performed_by"])
        else:
             log.save(update_fields=["status"])

    else:
        log.save(update_fields=["status"])

    return JsonResponse({
        "success": True,
        "status": log.status
    })
@csrf_exempt
def edit_maintenance_log(request, log_id):

    print("EDIT API CALLED")

    err = _require_post(request)
    if err:
        return err

    try:
        data = _json(request)
        print("DATA:", data)

        log = MaintenanceLog.objects.get(id=log_id)

        log.description = data.get("description", log.description)
        log.priority = data.get("priority", log.priority)

        if hasattr(log, "labour_cost"):
            log.labour_cost = data.get("labour_cost", 0)

        if hasattr(log, "parts_cost"):
            log.parts_cost = data.get("parts_cost", 0)

        if hasattr(log, "cost"):
            log.cost = data.get("cost", 0)

        if hasattr(log, "next_due"):
            log.next_due = data.get("next_due") or None

        if hasattr(log, "notes"):
            log.notes = data.get("notes", "")

        log.save()

        return JsonResponse({
            "success": True
        })

    except Exception as e:
        print("EDIT ERROR:", e)

        return JsonResponse({
            "error": str(e)
        }, status=400)

@csrf_exempt
def delete_maintenance_log(request, log_id):

    err = _require_post(request)

    if err:
        return err

    try:
        log = MaintenanceLog.objects.get(id=log_id)

    except MaintenanceLog.DoesNotExist:
        return JsonResponse(
            {"error": "Maintenance log not found"},
            status=404
        )

    log.delete()

    return JsonResponse({
        "success": True
    })
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

from decimal import Decimal
from pms.models import Booking
from billing.models import GuestFolio, FolioCharge

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
        'booking',
        'delivered_by'
    ).prefetch_related(
        'items__service',
        'logs__updated_by'
    ).all().order_by('-id'):

        logs = o.logs.all().order_by('-created_at')

        delivered_log = logs.filter(status="delivered").first()

        delivered_by = ""
        if delivered_log and delivered_log.updated_by:
            delivered_by = delivered_log.updated_by.name

        last_log = logs.first()

        # selected services/items
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
                last_log.updated_by.name
                if last_log and last_log.updated_by else ""
            ),
        })

    return JsonResponse({"orders": data})
from accounts.models import Staff

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

    # if frontend sends staff_id
    if staff_id:
        staff = Staff.objects.filter(id=staff_id).first()

    # fallback → logged in user
    if not staff and request.user.is_authenticated:
        staff = Staff.objects.filter(user=request.user).first()

    order.status = new_status

    if new_status == "delivered" and staff:
        order.delivered_by = staff

    order.save()

    LaundryStatusLog.objects.create(
        order=order,
        status=new_status,
        note=note,
        updated_by=staff
    )

    return JsonResponse({
        "success": True,
        "status": order.status,
        "updated_by": staff.name if staff else None,
        "delivered_by": order.delivered_by.name if order.delivered_by else None,
    })
@csrf_exempt
def update_inventory_item(request, pk):
       if request.method != 'POST': return JsonResponse({'error':'POST required'},status=405)
       item = get_object_or_404(InventoryItem, pk=pk)
       data = json.loads(request.body)
       for f in ['name','unit','current_stock','minimum_stock','cost_per_unit']:
           if f in data: setattr(item, f, data[f])
       if 'category_id' in data: item.category_id = data['category_id'] or None
       if 'department_id' in data: item.department_id = data['department_id'] or None
       if 'vendor_id' in data: item.vendor_id = data['vendor_id'] or None
       item.save()
       return JsonResponse({'success': True, 'id': item.id})
   
@csrf_exempt
def delete_inventory_item(request, pk):
       if request.method != 'POST': return JsonResponse({'error':'POST required'},status=405)
       get_object_or_404(InventoryItem, pk=pk).delete()
       return JsonResponse({'success': True})
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
from django.views.decorators.http import require_POST
@csrf_exempt
@require_POST
def delete_expense(request, expense_id):
    try:
        expense = Expense.objects.get(id=expense_id)
        expense.delete()

        return JsonResponse({
            "success": True,
            "message": "Expense deleted successfully"
        })

    except Expense.DoesNotExist:
        return JsonResponse({
            "success": False,
            "error": "Expense not found"
        }, status=404)