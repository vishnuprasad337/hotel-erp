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

    folio_id         = data.get("folio_id")
    amount           = data.get("amount")
    method           = data.get("method", "cash")
    reference_number = (data.get("reference_number") or "").strip()
    note             = (data.get("note") or "").strip()

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
        pms_pay.paid_at        = timezone.now()
        pms_pay.save()

    # ── Send payment confirmation email ──────────────────
    email_sent    = False
    email_address = ""
    email_error   = ""
    try:
        email_sent, result = _send_payment_confirmation_email(folio, payment)
        if email_sent:
            email_address = result
        else:
            email_error = result
    except Exception as e:
        email_error = str(e)

    return JsonResponse({
        "success":       True,
        "payment": {
            "id":               payment.pk,
            "amount":           float(payment.amount),
            "method":           payment.method,
            "method_label":     payment.get_method_display(),
            "reference_number": payment.reference_number,
            "received_at":      payment.received_at.isoformat(),
        },
        "folio_balance":  float(folio.balance_due),
        "is_settled":     folio.is_settled,
        "total_paid":     float(folio.total_paid),
        "total_charges":  float(folio.total_charges),
        "email_sent":     email_sent,
        "email_address":  email_address,
        "email_error":    email_error,
    })


from io import BytesIO
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import connection
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    Table, TableStyle, HRFlowable, KeepTogether, Flowable
)
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Fonts ─────────────────────────────────────────────────────────────────────
_FONTS_REGISTERED = False

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        pdfmetrics.registerFont(TTFont("Poppins-Bold",
            "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"))
        pdfmetrics.registerFont(TTFont("Poppins",
            "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf"))
        pdfmetrics.registerFont(TTFont("Poppins-Italic",
            "/usr/share/fonts/truetype/google-fonts/Poppins-Italic.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        _FONTS_REGISTERED = True
    except Exception:
        pass

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#0D1B2A")
GOLD      = colors.HexColor("#B8952A")
GOLD_LT   = colors.HexColor("#FDF6E3")
CREAM     = colors.HexColor("#FAFAF7")
GREY      = colors.HexColor("#E0E0DA")
DARK      = colors.HexColor("#1A1A1A")
MUTED     = colors.HexColor("#888888")
WHITE     = colors.white

W, H  = A4
MX    = 20 * mm
MY    = 16 * mm
CW    = W - 2 * MX   # ~170mm


def _styles(p=True):
    B  = "Poppins-Bold"   if p else "Helvetica-Bold"
    R  = "Poppins"        if p else "Helvetica"
    I  = "Poppins-Italic" if p else "Helvetica-Oblique"
    DV = "DejaVu"         if p else "Helvetica"
    DB = "DejaVu-Bold"    if p else "Helvetica-Bold"

    def S(n, **k): return ParagraphStyle(n, **k)
    return {
        "hotel_name":   S("hn",  fontName=B,  fontSize=22, leading=26, textColor=NAVY),
        "tagline":      S("tl",  fontName=I,  fontSize=9,  leading=12, textColor=GOLD, spaceBefore=2),
        "contact":      S("co",  fontName=R,  fontSize=8,  leading=12, textColor=MUTED),
        "badge":        S("ba",  fontName=B,  fontSize=11, leading=14, textColor=WHITE, alignment=TA_CENTER),
        "sec_head":     S("sh",  fontName=B,  fontSize=7.5,leading=10, textColor=GOLD),
        "lbl":          S("lb",  fontName=R,  fontSize=8.5,leading=12, textColor=MUTED),
        "val":          S("vl",  fontName=B,  fontSize=8.5,leading=13, textColor=DARK),
        "col_head":     S("ch",  fontName=B,  fontSize=8.5,leading=12, textColor=WHITE),
        "cell":         S("ce",  fontName=R,  fontSize=8.5,leading=12, textColor=DARK),
        "cell_r":       S("cr",  fontName=DV, fontSize=8.5,leading=12, textColor=DARK,  alignment=TA_RIGHT),
        "total_lbl":    S("tl2", fontName=R,  fontSize=9,  leading=13, textColor=DARK,  alignment=TA_RIGHT),
        "total_val":    S("tv",  fontName=DV, fontSize=9,  leading=13, textColor=DARK,  alignment=TA_RIGHT),
        "grand_lbl":    S("gl",  fontName=B,  fontSize=11, leading=14, textColor=NAVY,  alignment=TA_RIGHT),
        "grand_val":    S("gv",  fontName=DB, fontSize=11, leading=14, textColor=NAVY,  alignment=TA_RIGHT),
        "status":       S("st",  fontName=B,  fontSize=9,  leading=12, textColor=WHITE, alignment=TA_CENTER),
        "footer":       S("ft",  fontName=I,  fontSize=7.5,leading=11, textColor=MUTED, alignment=TA_CENTER),
        "meta_lbl":     S("ml",  fontName=R,  fontSize=8.5,leading=12, textColor=MUTED, alignment=TA_RIGHT),
        "meta_val":     S("mv",  fontName=B,  fontSize=8.5,leading=13, textColor=DARK,  alignment=TA_RIGHT),
    }


def _kv(label, value, s):
    return [Paragraph(label, s["lbl"]), Paragraph(str(value), s["val"])]


def _info_box(title, rows, s):
    t = Table([[Paragraph(title, s["sec_head"]), ""]] + rows,
              colWidths=[28*mm, 52*mm])
    t.setStyle(TableStyle([
        ("SPAN",          (0,0),(1,0)),
        ("BACKGROUND",    (0,0),(1,0),  GOLD_LT),
        ("LINEBELOW",     (0,0),(1,0),  1, GOLD),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 6),
        ("GRID",          (0,1),(-1,-1), 0.3, GREY),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, CREAM]),
    ]))
    return t


class _LogoPlaceholder(Flowable):
    """Shown only when hotel has no logo uploaded."""
    def __init__(self, w, h):
        self.width, self.height = w, h
    def draw(self):
        c = self.canv
        c.setFillColor(NAVY)
        c.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        c.setFillColor(GOLD)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(self.width/2, self.height/2 - 4, "NO LOGO")


def _get_hotel():
    """
    Fetch the Hotel object from the public schema using the current tenant.
    This is needed because Hotel lives in public schema, not the tenant schema.
    """
    try:
        from django_tenants.utils import schema_context
        from accounts.models import Hotel   # adjust import to your actual model path

        tenant_schema = connection.tenant.schema_name
        with schema_context('public'):
            return Hotel.objects.filter(schema_name=tenant_schema).first()
    except Exception:
        return None


def _send_invoice_email_helper(invoice):
    folio   = invoice.folio
    booking = folio.booking
    guest   = booking.guest

    if not guest or not guest.email:
        return False, "No guest email on file"

    _register_fonts()
    s = _styles(_FONTS_REGISTERED)

    # ── Fetch hotel from public schema ────────────────────────────────────────
    hotel = _get_hotel()

    hotel_name    = (getattr(hotel, "hotel_name", None) or
                     getattr(hotel, "name", None) or "Hotel")
    hotel_addr    = getattr(hotel, "address",  "") or ""
    hotel_city    = getattr(hotel, "city",     "") or ""
    hotel_phone   = getattr(hotel, "phone",    "") or ""
    hotel_email_s = getattr(hotel, "email",    "") or ""
    hotel_gstin   = getattr(hotel, "gstin",    "") or ""
    hotel_tagline = getattr(hotel, "tagline",  "") or ""

    # ── Logo ──────────────────────────────────────────────────────────────────
    LOGO_W, LOGO_H = 40*mm, 40*mm
    logo_cell = _LogoPlaceholder(LOGO_W, LOGO_H)
    if hotel and hotel.logo:
        try:
            logo_cell = Image(
                hotel.logo.path,
                width=LOGO_W, height=LOGO_H,
                kind="proportional",
            )
        except Exception:
            pass

    # ── PDF ───────────────────────────────────────────────────────────────────
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=MX, rightMargin=MX,
        topMargin=MY,  bottomMargin=MY)
    el = []

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1 — LETTERHEAD
    # Logo on the LEFT, hotel name + tagline + contacts on the RIGHT
    # VALIGN MIDDLE so logo is vertically centred with the text block
    # ══════════════════════════════════════════════════════════════════════════
    name_block = [
        Paragraph(hotel_name.upper(), s["hotel_name"]),
    ]
    if hotel_tagline:
        name_block.append(Paragraph(hotel_tagline, s["tagline"]))
    name_block.append(Spacer(1, 3*mm))

    loc = "  ·  ".join(x for x in [hotel_addr, hotel_city] if x)
    if loc:
        name_block.append(Paragraph(loc, s["contact"]))

    phone_email = "  ·  ".join(x for x in [hotel_phone, hotel_email_s] if x)
    if phone_email:
        name_block.append(Paragraph(phone_email, s["contact"]))

    if hotel_gstin:
        name_block.append(Paragraph(f"GSTIN: {hotel_gstin}", s["contact"]))

    lh = Table([[logo_cell, name_block]],
               colWidths=[48*mm, CW - 48*mm])
    lh.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(0,0),   10),
    ]))
    el.append(lh)
    el.append(Spacer(1, 5*mm))
    el.append(HRFlowable(width="100%", thickness=2.5, color=GOLD,
                         spaceAfter=1.5, spaceBefore=0))
    el.append(HRFlowable(width="100%", thickness=0.6, color=NAVY,
                         spaceAfter=7,  spaceBefore=0))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2 — TAX INVOICE badge + invoice meta
    # ══════════════════════════════════════════════════════════════════════════
    inv_date = str(getattr(invoice, "created_at", None) or
                   getattr(invoice, "date", "") or "")
    due_date = str(getattr(invoice, "due_date", None) or "On Arrival")

    badge = Table([[Paragraph("TAX INVOICE", s["badge"])]],
                  colWidths=[44*mm], rowHeights=[11*mm])
    badge.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), NAVY),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
    ]))

    meta = Table([
        [Paragraph("Invoice No.",  s["meta_lbl"]), Paragraph(invoice.invoice_number, s["meta_val"])],
        [Paragraph("Date",         s["meta_lbl"]), Paragraph(inv_date,               s["meta_val"])],
        [Paragraph("Due",          s["meta_lbl"]), Paragraph(due_date,               s["meta_val"])],
    ], colWidths=[28*mm, 50*mm])
    meta.setStyle(TableStyle([
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("ALIGN",        (0,0),(-1,-1), "RIGHT"),
    ]))

    banner = Table([[badge, "", meta]],
                   colWidths=[44*mm, CW-122*mm, 78*mm])
    banner.setStyle(TableStyle([
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    el.append(banner)
    el.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3 — BILLED TO | STAY DETAILS
    # ══════════════════════════════════════════════════════════════════════════
    room_no = booking.room_unit.room_number if booking.room_unit else "N/A"
    try:
        nights = str((booking.check_out - booking.check_in).days)
    except Exception:
        nights = "—"

    guest_box = _info_box("BILLED TO", [
        _kv("Guest Name", guest.full_name or "Guest", s),
        _kv("Booking ID", str(booking.id),            s),
        _kv("Email",      guest.email or "—",         s),
        _kv("Phone",      getattr(guest, "phone", "") or "—", s),
    ], s)

    stay_box = _info_box("STAY DETAILS", [
        _kv("Room No.",  room_no,                s),
        _kv("Check-In",  str(booking.check_in),  s),
        _kv("Check-Out", str(booking.check_out), s),
        _kv("Nights",    nights,                 s),
    ], s)

    el.append(Table([[guest_box, Spacer(6*mm,1), stay_box]],
                    colWidths=[80*mm, 6*mm, 80*mm]))
    el.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4 — CHARGES TABLE
    # ══════════════════════════════════════════════════════════════════════════
    col_w = [82*mm, 18*mm, 32*mm, 32*mm]
    rows = [[
        Paragraph("DESCRIPTION", s["col_head"]),
        Paragraph("QTY",         s["col_head"]),
        Paragraph("RATE",        s["col_head"]),
        Paragraph("AMOUNT",      s["col_head"]),
    ]]
    for c in folio.charges.all():
        qty  = getattr(c, "quantity", 1) or 1
        rate = getattr(c, "unit_price", None)
        rate = float(rate) if rate is not None else float(c.total) / qty
        rows.append([
            Paragraph(c.description,              s["cell"]),
            Paragraph(str(qty),                   s["cell_r"]),
            Paragraph(f"Rs.{rate:,.2f}",           s["cell_r"]),
            Paragraph(f"Rs.{float(c.total):,.2f}", s["cell_r"]),
        ])

    ct = Table(rows, colWidths=col_w, repeatRows=1)
    ct.setStyle(TableStyle([
        ("BACKGROUND",     (0,0),(-1,0),  NAVY),
        ("TOPPADDING",     (0,0),(-1,0),  7),
        ("BOTTOMPADDING",  (0,0),(-1,0),  7),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [WHITE, CREAM]),
        ("TOPPADDING",     (0,1),(-1,-1), 5),
        ("BOTTOMPADDING",  (0,1),(-1,-1), 5),
        ("ALIGN",          (0,0),(0,-1),  "LEFT"),
        ("ALIGN",          (1,0),(-1,-1), "RIGHT"),
        ("LINEBELOW",      (0,0),(-1,-1), 0.3, GREY),
        ("LINEAFTER",      (0,0),(-2,-1), 0.3, GREY),
        ("LEFTPADDING",    (0,0),(-1,-1), 6),
        ("RIGHTPADDING",   (0,0),(-1,-1), 6),
        ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
    ]))
    el.append(ct)
    el.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5 — STATUS PILL + TOTALS
    # ══════════════════════════════════════════════════════════════════════════
    sub   = float(invoice.subtotal)
    tax   = float(invoice.tax_total)
    disc  = float(invoice.discount)
    grand = float(invoice.grand_total)

    totals = Table([
        [Paragraph("Subtotal",    s["total_lbl"]), Paragraph(f"Rs.{sub:,.2f}",    s["total_val"])],
        [Paragraph("Tax / GST",   s["total_lbl"]), Paragraph(f"Rs.{tax:,.2f}",    s["total_val"])],
        [Paragraph("Discount",    s["total_lbl"]), Paragraph(f"- Rs.{disc:,.2f}", s["total_val"])],
        [Paragraph("GRAND TOTAL", s["grand_lbl"]), Paragraph(f"Rs.{grand:,.2f}",  s["grand_val"])],
    ], colWidths=[40*mm, 36*mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("ALIGN",         (0,0),(-1,-1), "RIGHT"),
        ("LINEABOVE",     (0,-1),(-1,-1), 1.5, NAVY),
        ("LINEBELOW",     (0,-1),(-1,-1), 2,   GOLD),
        ("BACKGROUND",    (0,-1),(-1,-1), GOLD_LT),
        ("LINEBELOW",     (0,0),(-1,-2),  0.3, GREY),
    ]))

    status_str = invoice.status.upper()
    pill_bg    = colors.HexColor("#1B6B36") if status_str == "PAID" else colors.HexColor("#A52B2B")
    pill_text  = "✓  PAID" if status_str == "PAID" else status_str

    pill = Table([[Paragraph(pill_text, s["status"])]],
                 colWidths=[30*mm], rowHeights=[10*mm])
    pill.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), pill_bg),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
    ]))

    el.append(KeepTogether(
        Table([[pill, "", totals]],
              colWidths=[32*mm, CW-108*mm, 76*mm],
              style=[
                  ("VALIGN",       (0,0),(-1,-1), "BOTTOM"),
                  ("LEFTPADDING",  (0,0),(-1,-1), 0),
                  ("RIGHTPADDING", (0,0),(-1,-1), 0),
                  ("TOPPADDING",   (0,0),(-1,-1), 0),
                  ("BOTTOMPADDING",(0,0),(-1,-1), 0),
              ])
    ))
    el.append(Spacer(1, 12*mm))

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 6 — FOOTER
    # ══════════════════════════════════════════════════════════════════════════
    el.append(HRFlowable(width="100%", thickness=2, color=GOLD,
                         spaceBefore=0, spaceAfter=4))
    footer = f"Thank you for staying at <b>{hotel_name}</b>. We look forward to welcoming you again."
    if hotel_email_s:
        footer += f"   ·   {hotel_email_s}"
    el.append(Paragraph(footer, s["footer"]))

    doc.build(el)
    pdf = buffer.getvalue()
    buffer.close()

    # ── Email ─────────────────────────────────────────────────────────────────
    msg = EmailMessage(
        subject=f"Your Invoice – {invoice.invoice_number} | {hotel_name}",
        body=(
            f"Dear {guest.full_name or 'Valued Guest'},\n\n"
            f"Please find your invoice ({invoice.invoice_number}) attached.\n\n"
            f"We appreciate your stay at {hotel_name} and hope you had a wonderful experience.\n\n"
            "Warm regards,\n"
            f"The {hotel_name} Team"
        ),
        from_email=settings.EMAIL_HOST_USER,
        to=[guest.email],
    )
    msg.attach(f"Invoice_{invoice.invoice_number}.pdf", pdf, "application/pdf")
    msg.send()

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
def _send_payment_confirmation_email(folio, payment):
   
   
    booking = folio.booking
    guest   = booking.guest

    if not guest or not guest.email:
        return False, "No guest email on file"

    _register_fonts()
    p  = _FONTS_REGISTERED
    B  = "Poppins-Bold"   if p else "Helvetica-Bold"
    R  = "Poppins"        if p else "Helvetica"
    I  = "Poppins-Italic" if p else "Helvetica-Oblique"
    DV = "DejaVu"         if p else "Helvetica"

    hotel         = _get_hotel()
    hotel_name    = getattr(hotel, "hotel_name", None) or getattr(hotel, "name", None) or "Hotel"
    hotel_addr    = getattr(hotel, "address",  "") or ""
    hotel_city    = getattr(hotel, "city",     "") or ""
    hotel_phone   = getattr(hotel, "phone",    "") or ""
    hotel_email_s = getattr(hotel, "email",    "") or ""

    method_labels = {
        "cash":          "Cash",
        "card":          "Credit / Debit Card",
        "upi":           "UPI",
        "bank_transfer": "Bank Transfer",
    }
    method_label = method_labels.get(payment.method, payment.method.title())

    
    def S(name, **kw): return ParagraphStyle(name, **kw)

    BLACK  = colors.HexColor("#1A1A1A")
    GRAY   = colors.HexColor("#888888")
    LGRAY  = colors.HexColor("#EEEEEE")
    WHITE  = colors.white

    sHotel  = S("h",  fontName=B,  fontSize=13, leading=17, textColor=BLACK,  alignment=TA_CENTER)
    sSub    = S("s",  fontName=I,  fontSize=8,  leading=11, textColor=GRAY,   alignment=TA_CENTER)
    sTitle  = S("t",  fontName=B,  fontSize=10, leading=13, textColor=BLACK,  alignment=TA_CENTER)
    sLbl    = S("l",  fontName=R,  fontSize=8,  leading=12, textColor=GRAY,   alignment=TA_LEFT)
    sVal    = S("v",  fontName=B,  fontSize=8,  leading=12, textColor=BLACK,  alignment=TA_RIGHT)
    sMono   = S("m",  fontName=DV, fontSize=8,  leading=12, textColor=BLACK,  alignment=TA_RIGHT)
    sAmt    = S("a",  fontName=B,  fontSize=16, leading=20, textColor=BLACK,  alignment=TA_CENTER)
    sAmtLbl = S("al", fontName=R,  fontSize=8,  leading=11, textColor=GRAY,   alignment=TA_CENTER)
    sFoot   = S("f",  fontName=I,  fontSize=8,  leading=12, textColor=GRAY,   alignment=TA_CENTER)
    sStatus = S("st", fontName=B,  fontSize=9,  leading=12, textColor=colors.HexColor("#166534"), alignment=TA_CENTER)

    # ── Page setup (A6 = receipt width) ───────────────────
    W, H = A6          # 105mm × 148mm
    MX   = 8 * mm
    MY   = 10 * mm

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A6,
        leftMargin=MX, rightMargin=MX,
        topMargin=MY,  bottomMargin=MY,
    )

    el = []

   
    el.append(Paragraph(hotel_name.upper(), sHotel))
    if hotel_addr or hotel_city:
        loc = ", ".join(x for x in [hotel_addr, hotel_city] if x)
        el.append(Paragraph(loc, sSub))
    if hotel_phone:
        el.append(Paragraph(f"Tel: {hotel_phone}", sSub))
    if hotel_email_s:
        el.append(Paragraph(hotel_email_s, sSub))

    el.append(Spacer(1, 3*mm))
    el.append(HRFlowable(width="100%", thickness=1, color=BLACK, dash=(2,2)))
    el.append(Spacer(1, 3*mm))

    
    el.append(Paragraph("PAYMENT RECEIPT", sTitle))
    el.append(Spacer(1, 3*mm))
    el.append(HRFlowable(width="100%", thickness=0.5, color=LGRAY))
    el.append(Spacer(1, 3*mm))

    
    CW = W - 2 * MX  # content width

    def row(label, value, mono=False):
        vs = sMono if mono else sVal
        return [Paragraph(label, sLbl), Paragraph(str(value), vs)]

    room_no = booking.room_unit.room_number if booking.room_unit else "N/A"
    try:
        nights = str((booking.check_out - booking.check_in).days)
    except Exception:
        nights = "—"

    details = Table([
        row("Receipt Date",    payment.received_at.strftime("%d %b %Y, %I:%M %p")),
        row("Booking ID",      f"#{booking.id}"),
        row("Guest Name",      guest.full_name or "Guest"),
        row("Room No.",        room_no),
        row("Check-In",        str(booking.check_in)),
        row("Check-Out",       str(booking.check_out)),
        row("Nights",          nights),
    ], colWidths=[CW * 0.5, CW * 0.5])

    details.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("LINEBELOW",     (0,0),(-1,-2), 0.3, LGRAY),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ]))
    el.append(details)

    el.append(Spacer(1, 3*mm))
    el.append(HRFlowable(width="100%", thickness=0.5, color=LGRAY))
    el.append(Spacer(1, 3*mm))

   
    pay_details = Table([
        row("Payment Method",  method_label),
        row("Reference No.",   payment.reference_number or "—"),
        row("Total Charges",   f"\u20b9{float(folio.total_charges):,.2f}", mono=True),
        row("Amount Paid",     f"\u20b9{float(payment.amount):,.2f}",      mono=True),
        row("Balance Due",     f"\u20b9{float(folio.balance_due):,.2f}",   mono=True),
    ], colWidths=[CW * 0.5, CW * 0.5])

    pay_details.setStyle(TableStyle([
        ("TOPPADDING",    (0,0),(-1,-1), 3),
        ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ("LEFTPADDING",   (0,0),(-1,-1), 0),
        ("RIGHTPADDING",  (0,0),(-1,-1), 0),
        ("LINEBELOW",     (0,0),(-1,-2), 0.3, LGRAY),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        # highlight balance row
        ("TEXTCOLOR",     (1,4),(1,4),
            colors.HexColor("#166534") if folio.is_settled else colors.HexColor("#991B1B")),
    ]))
    el.append(pay_details)

    el.append(Spacer(1, 4*mm))
    el.append(HRFlowable(width="100%", thickness=1.5, color=BLACK))
    el.append(Spacer(1, 4*mm))

   
    el.append(Paragraph("AMOUNT PAID", sAmtLbl))
    el.append(Paragraph(f"\u20b9{float(payment.amount):,.2f}", sAmt))
    el.append(Spacer(1, 3*mm))

    
    if folio.is_settled:
        status_tbl = Table(
            [[Paragraph("✓  FULLY SETTLED", sStatus)]],
            colWidths=[CW],
        )
        status_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#DCFCE7")),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 0),
            ("RIGHTPADDING",  (0,0),(-1,-1), 0),
            ("ROUNDEDCORNERS", [4]),
        ]))
        el.append(status_tbl)
    else:
        sBalance = S("b", fontName=B, fontSize=9, leading=12,
                     textColor=colors.HexColor("#991B1B"), alignment=TA_CENTER)
        el.append(Paragraph(
            f"Balance Due: \u20b9{float(folio.balance_due):,.2f}",
            sBalance,
        ))

    el.append(Spacer(1, 4*mm))
    el.append(HRFlowable(width="100%", thickness=1, color=BLACK, dash=(2,2)))
    el.append(Spacer(1, 3*mm))

    
    el.append(Paragraph(f"Thank you for staying at {hotel_name}!", sFoot))
    el.append(Paragraph("We look forward to welcoming you again.", sFoot))
    if hotel_email_s:
        el.append(Spacer(1, 2*mm))
        el.append(Paragraph(f"Queries? {hotel_email_s}", sFoot))

    doc.build(el)
    pdf = buffer.getvalue()
    buffer.close()

   
    msg = EmailMessage(
        subject=f"Payment Receipt – {hotel_name}",
        body=(
            f"Dear {guest.full_name or 'Valued Guest'},\n\n"
            f"Thank you for your payment of \u20b9{float(payment.amount):,.2f}.\n"
            f"Please find your payment receipt attached.\n\n"
            f"{'Your account is now fully settled.' if folio.is_settled else f'A balance of Rs.{float(folio.balance_due):,.2f} remains.'}\n\n"
            f"Warm regards,\n"
            f"The {hotel_name} Team"
        ),
        from_email=settings.EMAIL_HOST_USER,
        to=[guest.email],
    )
    msg.attach(
        f"Receipt_{booking.id}_{payment.received_at.strftime('%Y%m%d')}.pdf",
        pdf,
        "application/pdf",
    )
    msg.send()

    return True, guest.email