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


@csrf_exempt
def add_category(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    data = json.loads(request.body)
    obj = ItemCategory.objects.create(name=data.get("name"))
    return JsonResponse({"id": obj.id, "name": obj.name})


def list_categories(request):
    data = list(ItemCategory.objects.values())
    return JsonResponse({"categories": data})


@csrf_exempt
def add_vendor(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    data = json.loads(request.body)
    obj = Vendor.objects.create(
        name=data.get("name"),
        contact_person=data.get("contact_person", ""),
        phone=data.get("phone"),
        email=data.get("email", ""),
        address=data.get("address", "")
    )
    return JsonResponse({"id": obj.id})


def list_vendors(request):
    return JsonResponse({"vendors": list(Vendor.objects.values())})


@csrf_exempt
def add_inventory_item(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    data = json.loads(request.body)
    obj = InventoryItem.objects.create(
        category_id=data.get("category_id"),
        name=data.get("name"),
        unit=data.get("unit", "piece"),
        current_stock=data.get("current_stock", 0),
        minimum_stock=data.get("minimum_stock", 10),
        cost_per_unit=data.get("cost_per_unit", 0),
        vendor_id=data.get("vendor_id")
    )
    return JsonResponse({"id": obj.id})


def list_inventory(request):
    items = InventoryItem.objects.all()
    data = []
    for i in items:
        data.append({
            "id": i.id,
            "name": i.name,
            "stock": float(i.current_stock),
            "min_stock": float(i.minimum_stock),
            "low_stock": i.is_low_stock,
            "value": float(i.stock_value)
        })
    return JsonResponse({"items": data})
from decimal import Decimal

@csrf_exempt
def stock_adjust(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    data = json.loads(request.body)
    item = InventoryItem.objects.get(id=data["item_id"])

    qty = Decimal(str(data["quantity"]))  
    typ = data["type"]

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
        quantity=qty,   # ✅ keep Decimal
        note=data.get("note", "")
    )

    return JsonResponse({"success": True})


@csrf_exempt
def create_purchase_order(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    data = json.loads(request.body)

    po = PurchaseOrder.objects.create(
        vendor_id=data["vendor_id"],
        note=data.get("note", "")
    )

    total = 0

    for i in data.get("items", []):
        item = InventoryItem.objects.get(id=i["item_id"])
        qty = float(i["quantity"])
        price = float(i["unit_price"])

        PurchaseItem.objects.create(
            purchase_order=po,
            item=item,
            quantity=qty,
            unit_price=price
        )

        total += qty * price

    po.total_amount = total
    po.save()

    return JsonResponse({"po_id": po.id, "total": total})


def list_purchase_orders(request):
    data = []
    for po in PurchaseOrder.objects.all():
        data.append({
            "id": po.id,
            "vendor": po.vendor.name,
            "status": po.status,
            "total": float(po.total_amount)
        })
    return JsonResponse({"purchase_orders": data})


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
    for o in LaundryOrder.objects.all():
        data.append({
            "id": o.id,
            "room": o.room_number,
            "status": o.status,
            "total": float(o.total_amount)
        })
    return JsonResponse({"orders": data})


@csrf_exempt
def update_laundry_status(request, pk):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    order = get_object_or_404(LaundryOrder, pk=pk)
    data = json.loads(request.body)

    order.status = data["status"]
    order.save()

    LaundryStatusLog.objects.create(
        order=order,
        status=data["status"],
        note=data.get("note", "")
    )

    return JsonResponse({"success": True})