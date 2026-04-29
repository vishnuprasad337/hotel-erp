import json
from decimal import Decimal
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods
from django.core.mail import send_mail
from pms.models import Booking, Payment as PmsPayment
from accounts.models import Staff
from .models import GuestFolio, FolioCharge, Invoice, BillingPayment


def _folio_dict(folio):
    charges = [
        {
            "id": c.pk,
            "charge_type": c.charge_type,
            "label": c.get_charge_type_display(),
            "description": c.description,
            "amount": float(c.amount),
            "tax_amount": float(c.tax_amount),
            "total": float(c.total),
            "date": c.date.isoformat(),
            "added_by": c.added_by.name if c.added_by else None,
        }
        for c in folio.charges.all()
    ]

    payments = [
        {
            "id": p.pk,
            "amount": float(p.amount),
            "method": p.method,
            "method_label": p.get_method_display(),
            "reference_number": p.reference_number,
            "note": p.note,
            "received_at": p.received_at.isoformat(),
            "received_by": p.received_by.name if p.received_by else None,
        }
        for p in folio.payments.all()
    ]

    booking = folio.booking
    guest = booking.guest if booking else None

    return {
        "folio_id": folio.pk,
        "status": folio.status,
        "booking_id": folio.booking_id,
        "guest_email": guest.email if guest else "",
        "total_charges": float(folio.total_charges),
        "total_paid": float(folio.total_paid),
        "balance_due": float(folio.balance_due),
        "is_settled": folio.is_settled,
        "charges": charges,
        "payments": payments,
        "created_at": folio.created_at.isoformat(),
        "notes": folio.notes,
    }


def _get_staff(request):
    staff_id = request.session.get("staff_id")
    if staff_id:
        return Staff.objects.filter(id=staff_id).first()
    return None


def _json_error(msg, code=400):
    return JsonResponse({"success": False, "error": msg}, status=code)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def get_or_create_folio(request):
    if request.method == "GET":
        booking_id = request.GET.get("booking_id")
    else:
        try:
            booking_id = json.loads(request.body).get("booking_id")
        except Exception:
            return _json_error("Invalid JSON")

    if not booking_id:
        return _json_error("booking_id is required")

    booking = Booking.objects.select_related(
        "guest", "room", "room_unit", "payment"
    ).filter(id=booking_id).first()

    if not booking:
        return _json_error(f"Booking {booking_id} not found", 404)

    folio, created = GuestFolio.objects.get_or_create(booking=booking)

    if created:
        try:
            pms_pay = booking.payment
            room_charges = float(pms_pay.room_charges or 0)
            tax = float(pms_pay.tax or 0)
        except Exception:
            nights = (
                (booking.check_out - booking.check_in).days
                if booking.check_in and booking.check_out
                else 1
            )
            room_charges = float(booking.base_price or 0) * nights
            tax = round(room_charges * 0.18, 2)

        if room_charges:
            room_label = booking.room.room_type if booking.room else "Room"
            nights_label = ""
            if booking.check_in and booking.check_out:
                n = (booking.check_out - booking.check_in).days
                nights_label = f" × {n} night{'s' if n != 1 else ''}"
            FolioCharge.objects.create(
                folio=folio,
                charge_type="room",
                description=f"{room_label} charge{nights_label}",
                amount=Decimal(str(room_charges)),
                tax_amount=Decimal(str(tax)),
                date=booking.check_in or timezone.now().date(),
            )

    folio_data = _folio_dict(folio)
    # Also attach guest email for the checkout modal
    if booking.guest and booking.guest.email:
        folio_data["guest_email"] = booking.guest.email

    return JsonResponse({
        "success": True,
        "created": created,
        "folio": folio_data,
    })


@csrf_exempt
@require_http_methods(["POST"])
def add_charge(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("Invalid JSON")

    folio_id = data.get("folio_id")
    charge_type = data.get("charge_type", "extra")
    description = (data.get("description") or "").strip()
    amount = data.get("amount")
    tax_amount = data.get("tax_amount", 0)

    if not folio_id:
        return _json_error("folio_id is required")
    if not description:
        return _json_error("description is required")
    if amount is None:
        return _json_error("amount is required")

    try:
        amount = Decimal(str(amount))
        tax_amount = Decimal(str(tax_amount))
    except Exception:
        return _json_error("Invalid amount values")

    folio = GuestFolio.objects.filter(id=folio_id).first()
    if not folio:
        return _json_error(f"Folio {folio_id} not found", 404)
    if folio.status == "closed":
        return _json_error("Cannot add charges to a closed folio")

    charge = FolioCharge.objects.create(
        folio=folio,
        charge_type=charge_type,
        description=description,
        amount=amount,
        tax_amount=tax_amount,
        added_by=_get_staff(request),
    )

    return JsonResponse({
        "success": True,
        "charge": {
            "id": charge.pk,
            "charge_type": charge.charge_type,
            "description": charge.description,
            "amount": float(charge.amount),
            "tax_amount": float(charge.tax_amount),
            "total": float(charge.total),
            "date": charge.date.isoformat(),
        },
        "folio_balance": float(folio.balance_due),
    })


@csrf_exempt
@require_http_methods(["DELETE"])
def delete_charge(request, charge_id):
    charge = FolioCharge.objects.select_related("folio").filter(id=charge_id).first()
    if not charge:
        return _json_error("Charge not found", 404)
    if charge.charge_type == "room":
        return _json_error("Room charge cannot be deleted")
    if charge.folio.status == "closed":
        return _json_error("Cannot delete charges on a closed folio")
    folio = charge.folio
    charge.delete()
    return JsonResponse({"success": True, "folio_balance": float(folio.balance_due)})


@csrf_exempt
@require_http_methods(["POST"])
def add_payment(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("Invalid JSON")

    folio_id = data.get("folio_id")
    amount = data.get("amount")
    method = data.get("method", "cash")
    reference_number = (data.get("reference_number") or "").strip()
    note = (data.get("note") or "").strip()

    if not folio_id:
        return _json_error("folio_id is required")
    if amount is None:
        return _json_error("amount is required")

    try:
        amount = Decimal(str(amount))
    except Exception:
        return _json_error("Invalid amount")

    if amount <= 0:
        return _json_error("Amount must be greater than zero")

    folio = GuestFolio.objects.filter(id=folio_id).first()
    if not folio:
        return _json_error(f"Folio {folio_id} not found", 404)

    payment = BillingPayment.objects.create(
        folio=folio,
        amount=amount,
        method=method,
        reference_number=reference_number,
        note=note,
        received_by=_get_staff(request),
    )

    pms_pay = PmsPayment.objects.filter(booking=folio.booking).first()
    if pms_pay:
        pms_pay.payment_method = method
        pms_pay.payment_status = "paid" if folio.is_settled else "partial"
        pms_pay.paid_at = timezone.now()
        pms_pay.save()

    return JsonResponse({
        "success": True,
        "payment": {
            "id": payment.pk,
            "amount": float(payment.amount),
            "method": payment.method,
            "method_label": payment.get_method_display(),
            "reference_number": payment.reference_number,
            "received_at": payment.received_at.isoformat(),
        },
        "folio_balance": float(folio.balance_due),
        "is_settled": folio.is_settled,
        "total_paid": float(folio.total_paid),
        "total_charges": float(folio.total_charges),
    })


def _send_invoice_email_helper(invoice):
    """Internal helper — call this from other views, NOT via URL."""
    folio = invoice.folio
    booking = folio.booking
    guest = booking.guest

    if not guest or not guest.email:
        return False, "No guest email on file"

    charges_lines = "\n".join(
        f"  {c.description:<35} ₹{float(c.total):>10.2f}"
        for c in folio.charges.all()
    )

    message = f"""Dear {guest.full_name or 'Guest'},

Thank you for staying with us. Please find your invoice details below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Invoice No : {invoice.invoice_number}
  Booking ID : {booking.id}
  Room       : {booking.room_unit.room_number if booking.room_unit else 'N/A'}
  Check-in   : {booking.check_in}
  Check-out  : {booking.check_out}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CHARGES:
{charges_lines}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Subtotal   : ₹{float(invoice.subtotal):>10.2f}
  Tax (GST)  : ₹{float(invoice.tax_total):>10.2f}
  Discount   : ₹{float(invoice.discount):>10.2f}
  Grand Total: ₹{float(invoice.grand_total):>10.2f}
  Status     : {invoice.status.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

We hope you enjoyed your stay and look forward to welcoming you again!

Warm regards,
Hotel Team
"""

    send_mail(
        subject=f"Invoice {invoice.invoice_number} — Thank you for your stay!",
        message=message,
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[guest.email],
        fail_silently=False,
    )
    return True, guest.email


@csrf_exempt
@require_http_methods(["POST"])
def generate_invoice(request):
    """Generate invoice, close folio, and email guest automatically."""
    try:
        data = json.loads(request.body)
    except Exception:
        return _json_error("Invalid JSON")

    folio_id = data.get("folio_id")
    discount = Decimal(str(data.get("discount", 0)))
    send_email = data.get("send_email", True)  # default True

    if not folio_id:
        return _json_error("folio_id is required")

    folio = GuestFolio.objects.prefetch_related("charges").filter(id=folio_id).first()
    if not folio:
        return _json_error(f"Folio {folio_id} not found", 404)

    subtotal = sum(Decimal(str(c.amount)) for c in folio.charges.all())
    tax_total = sum(Decimal(str(c.tax_amount)) for c in folio.charges.all())
    grand_total = (subtotal + tax_total) - discount

    invoice, _ = Invoice.objects.update_or_create(
        folio=folio,
        defaults={
            "subtotal": subtotal,
            "tax_total": tax_total,
            "discount": discount,
            "grand_total": grand_total,
            "status": "paid" if folio.is_settled else (
                "partial" if folio.total_paid > 0 else "pending"
            ),
            "notes": data.get("notes", ""),
        },
    )

    folio.status = "closed"
    folio.save()

    email_sent = False
    email_address = ""
    email_error = ""

    if send_email:
        try:
            email_sent, result = _send_invoice_email_helper(invoice)
            if email_sent:
                email_address = result
            else:
                email_error = result
        except Exception as e:
            email_error = str(e)

    return JsonResponse({
        "success": True,
        "invoice": {
            "id": invoice.pk,
            "invoice_number": invoice.invoice_number,
            "subtotal": float(invoice.subtotal),
            "tax_total": float(invoice.tax_total),
            "discount": float(invoice.discount),
            "grand_total": float(invoice.grand_total),
            "status": invoice.status,
            "generated_at": invoice.generated_at.isoformat(),
        },
        "email_sent": email_sent,
        "email_address": email_address,
        "email_error": email_error,
    })


@csrf_exempt
@require_http_methods(["POST"])
def send_invoice_email(request, invoice_id):
    """Standalone endpoint to (re)send invoice email for an existing invoice."""
    invoice = Invoice.objects.select_related(
        "folio__booking__guest",
        "folio__booking__room_unit",
        "folio__booking__room",
    ).filter(id=invoice_id).first()

    if not invoice:
        return _json_error("Invoice not found", 404)

    try:
        sent, result = _send_invoice_email_helper(invoice)
    except Exception as e:
        return _json_error(f"Email failed: {str(e)}")

    if not sent:
        return _json_error(result)

    return JsonResponse({"success": True, "email_sent_to": result})


@require_GET
def get_invoice(request, invoice_id):
    invoice = Invoice.objects.filter(id=invoice_id).select_related(
        "folio__booking__guest",
        "folio__booking__room_unit",
        "folio__booking__room",
    ).first()

    if not invoice:
        return JsonResponse({"success": False, "error": "Invoice not found"}, status=404)

    folio   = invoice.folio
    booking = folio.booking
    guest   = booking.guest

    charges = [
        {
            "charge_type": c.charge_type,
            "description": c.description,
            "amount":      float(c.amount),
            "tax_amount":  float(c.tax_amount),
            "total":       float(c.total),
            "date":        c.date.isoformat() if c.date else None,
        }
        for c in folio.charges.all()
    ]

    payments = [
        {
            "amount":           float(p.amount),
            "method":           p.method,
            "method_label":     p.get_method_display(),
            "reference_number": p.reference_number or "",
            "received_at":      p.received_at.isoformat(),
        }
        for p in folio.payments.all()
    ]

    return JsonResponse({
        "success": True,
        "invoice": {
            "id":             invoice.id,
            "invoice_number": invoice.invoice_number,
            "status":         invoice.status,
            "subtotal":       float(invoice.subtotal),
            "tax":            float(invoice.tax_total),
            "discount":       float(invoice.discount),
            "grand_total":    float(invoice.grand_total),
            "paid":           float(folio.total_paid),
            "balance":        float(folio.balance_due),
            "generated_at":   invoice.generated_at.isoformat(),
            "notes":          invoice.notes or "",
            "guest_name":     guest.full_name   if guest else "N/A",
            "guest_email":    guest.email        if guest else "",
            "guest_phone":    guest.phone        if guest else "",
            "booking_id":     booking.id,
            "room_number":    booking.room_unit.room_number if booking.room_unit else "N/A",
            "room_type":      booking.room.room_type        if booking.room      else "N/A",
            "check_in":       booking.check_in.isoformat()  if booking.check_in  else "",
            "check_out":      booking.check_out.isoformat() if booking.check_out else "",
            "folio": {
                "id":            folio.id,
                "status":        folio.status,
                "total_charges": float(folio.total_charges),
                "total_paid":    float(folio.total_paid),
                "balance_due":   float(folio.balance_due),
            },
            "charges":  charges,
            "payments": payments,
        }
    })


@require_GET
def billing_summary(request):
    from django.db.models import Sum

    today = timezone.now().date()

    today_revenue = (
        BillingPayment.objects.filter(received_at__date=today)
        .aggregate(total=Sum("amount"))["total"] or Decimal("0")
    )

    open_folios = GuestFolio.objects.filter(status="open")
    pending_balance = sum(f.balance_due for f in open_folios)
    settled_today = GuestFolio.objects.filter(
        status="closed", updated_at__date=today
    ).count()

    return JsonResponse({
        "success": True,
        "today_revenue": float(today_revenue),
        "pending_balance": float(pending_balance),
        "open_folios": open_folios.count(),
        "settled_today": settled_today,
    })


@require_GET
def list_invoices(request):
    invoices = Invoice.objects.select_related(
        "folio__booking__guest",
        "folio__booking__room_unit",
    ).order_by("-generated_at")

    return JsonResponse({
        "invoices": [
            {
                "id":             inv.id,
                "invoice_number": inv.invoice_number,
                "guest_name":     inv.folio.booking.guest.full_name if inv.folio.booking.guest else "Unknown",
                "guest_email":    inv.folio.booking.guest.email     if inv.folio.booking.guest else "",
                "room_number":    inv.folio.booking.room_unit.room_number if inv.folio.booking.room_unit else "—",
                "check_in":       inv.folio.booking.check_in.isoformat()  if inv.folio.booking.check_in  else "",
                "check_out":      inv.folio.booking.check_out.isoformat() if inv.folio.booking.check_out else "",
                "status":         inv.status,
                "grand_total":    float(inv.grand_total),
                "generated_at":   inv.generated_at.isoformat(),
            }
            for inv in invoices
        ]
    })