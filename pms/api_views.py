from rest_framework.views import APIView
from rest_framework.response import Response
from django.conf import settings
from .models import Room, RoomUnit, Guest, Booking, Payment
from .serializers import (
    RoomSerializer,
    RoomCreateSerializer,
    RoomUnitSerializer,
    RoomUnitStatusSerializer,
    GuestSerializer,
    GuestCreateSerializer,
    PaymentSerializer,
    CheckInSerializer,
    CheckOutSerializer,
    CreateBookingSerializer,
)


class RoomListAPIView(APIView):
    def get(self, request):
        rooms = Room.objects.prefetch_related("units", "amenities", "images").all()
        serializer = RoomSerializer(rooms, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = RoomCreateSerializer(data=request.data)
        if serializer.is_valid():
            room = serializer.save()
            return Response(RoomSerializer(room).data, status=201)
        return Response(serializer.errors, status=400)


class RoomDetailAPIView(APIView):
    def get(self, request, pk):
        try:
            room = Room.objects.prefetch_related("units", "amenities", "images").get(id=pk)
            serializer = RoomSerializer(room)
            return Response(serializer.data)
        except Room.DoesNotExist:
            return Response({"error": "Room not found"}, status=404)


class RoomUnitStatusAPIView(APIView):
    def post(self, request):
        room_unit_id = request.data.get("room_unit_id")
        try:
            room_unit = RoomUnit.objects.get(id=room_unit_id)
        except RoomUnit.DoesNotExist:
            return Response({"error": "Room unit not found"}, status=404)

        serializer = RoomUnitStatusSerializer(room_unit, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"success": True, "room_unit_id": room_unit.id, "new_status": room_unit.status})
        return Response(serializer.errors, status=400)


class GuestListAPIView(APIView):
    def get(self, request):
        from django.db.models import Count
        guests = Guest.objects.annotate(booking_count=Count("booking")).order_by("-created_at")
        serializer = GuestSerializer(guests, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = GuestCreateSerializer(data=request.data)
        if serializer.is_valid():
            guest = serializer.save()
            return Response({"success": True, "guest_id": guest.id, "message": "Guest added successfully"}, status=201)
        return Response(serializer.errors, status=400)


class GuestDetailAPIView(APIView):
    def get(self, request, pk):
        try:
            guest = Guest.objects.prefetch_related("id_photos").get(id=pk)
            serializer = GuestSerializer(guest)
            return Response(serializer.data)
        except Guest.DoesNotExist:
            return Response({"error": "Guest not found"}, status=404)


class GuestPhotosAPIView(APIView):
    def get(self, request, guest_id):
        try:
            guest = Guest.objects.prefetch_related("id_photos").get(id=guest_id)
        except Guest.DoesNotExist:
            return Response({"error": "Guest not found"}, status=404)

        photos = []
        for p in guest.id_photos.all().order_by("id"):
            uploaded = "ID Photo"
            for field in ["uploaded_at", "created_at", "timestamp"]:
                val = getattr(p, field, None)
                if val:
                    uploaded = val.strftime("%d %b %Y, %H:%M")
                    break
            photos.append({
                "url":         request.build_absolute_uri(p.image.url),
                "uploaded_at": uploaded,
            })

        return Response({"photos": photos})


class BookingListAPIView(APIView):
    def get(self, request):
        bookings = Booking.objects.select_related(
            "guest", "room", "room_unit", "payment", "created_by"
        ).order_by("-created_at")

        data = []
        for b in bookings:
            try:
                total          = float(b.payment.total_amount)
                payment_status = b.payment.payment_status
            except Payment.DoesNotExist:
                total          = 0.0
                payment_status = "no_payment"

            data.append({
                "id":             b.id,
                "booking_code":   b.booking_code or f"BK{b.id:06d}",
                "guest":          b.guest.full_name if b.guest else "N/A",
                "guest_id":       b.guest.id if b.guest else None,
                "phone":          b.guest.phone if b.guest else "",
                "room_type":      b.room.room_type if b.room else "N/A",
                "room_no":        b.room_unit.room_number if b.room_unit else "N/A",
                "check_in":       b.check_in.isoformat() if b.check_in else "",
                "check_out":      b.check_out.isoformat() if b.check_out else "",
                "adults":         b.adults,
                "children":       b.children,
                "status":         b.status,
                "source":         b.source or "",
                "total":          total,
                "payment_status": payment_status,
                "created_at":     b.created_at.isoformat() if b.created_at else "",
                "booked_by":      b.created_by.name if b.created_by else "",
            })

        return Response(data)

    def post(self, request):
        serializer = CreateBookingSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            booking = serializer.save()
            return Response({
                "success":      True,
                "booking_id":   booking.id,
                "booking_code": f"BK{booking.id:06d}",
                "guest_id":     booking.guest.id,
                "room_number":  booking.room_unit.room_number,
                "nights":       (booking.check_out - booking.check_in).days,
                "total_amount": float(booking.total_amount),
                "message":      "Booking created successfully",
            }, status=201)
        return Response(serializer.errors, status=400)


class CheckInAPIView(APIView):
    def post(self, request):
        from django.db import transaction
        from pms.views import send_guest_portal_email

        serializer = CheckInSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        try:
            with transaction.atomic():
                booking, checked_in_by = serializer.save()
                send_guest_portal_email(request, booking)
        except Exception as e:
            return Response({"success": False, "message": f"Check-in failed: {str(e)}"}, status=500)

        return Response({
            "success":       True,
            "message":       "Check-in successful",
            "checked_in_by": checked_in_by.name if checked_in_by else None,
        })


class CheckOutAPIView(APIView):
    def post(self, request):
        serializer = CheckOutSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        booking, checked_out_by = serializer.save()

        return Response({
            "success":        True,
            "message":        "Check-out completed successfully",
            "checked_out_by": checked_out_by.name if checked_out_by else None,
        })


class BillAPIView(APIView):
    def get(self, request):
        from billing.models import GuestFolio

        booking_id = request.query_params.get("booking_id")
        if not booking_id:
            return Response({"error": "booking_id required"}, status=400)

        try:
            booking = Booking.objects.select_related(
                "guest", "room", "room_unit"
            ).get(id=booking_id)
        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=404)

        try:
            folio = GuestFolio.objects.get(booking=booking)
        except GuestFolio.DoesNotExist:
            return Response({"error": "Folio not created yet"}, status=404)

        charges = [
            {
                "charge_type": c.charge_type,
                "description": c.description,
                "amount":      float(c.amount),
                "tax":         float(c.tax_amount),
                "total":       float(c.total),
            }
            for c in folio.charges.all()
        ]

        payments = [
            {
                "amount": float(p.amount),
                "method": p.method,
            }
            for p in folio.payments.all()
        ]

        return Response({
            "booking_id": booking.id,
            "guest":      booking.guest.full_name if booking.guest else "N/A",
            "room":       booking.room_unit.room_number if booking.room_unit else "N/A",
            "charges":    charges,
            "payments":   payments,
            "subtotal":   float(folio.total_charges),
            "paid":       float(folio.total_paid),
            "balance":    float(folio.balance_due),
            "status":     folio.status,
        })
class BookingFullDetailAPIView(APIView):
    def get(self, request, pk):
        try:
            booking = Booking.objects.select_related(
                "guest",
                "room",
                "room_unit",
                "payment",
                "created_by",
                "checked_in_by",
                "checked_out_by",
            ).prefetch_related(
                "guest__id_photos",
                "room__amenities",
                "room__images",
                "room__units",
            ).get(id=pk)

        except Booking.DoesNotExist:
            return Response({"error": "Booking not found"}, status=404)

        guest   = booking.guest
        room    = booking.room
        unit    = booking.room_unit
        payment = getattr(booking, "payment", None)

        from billing.models import GuestFolio
        try:
            folio   = GuestFolio.objects.prefetch_related("charges", "payments").get(booking=booking)
            charges = [
                {
                    "charge_type": c.charge_type,
                    "description": c.description,
                    "amount":      float(c.amount),
                    "tax":         float(c.tax_amount),
                    "total":       float(c.total),
                    "date":        c.date.isoformat() if c.date else None,
                }
                for c in folio.charges.all()
            ]
            folio_payments = [
                {
                    "amount": float(p.amount),
                    "method": p.method,
                }
                for p in folio.payments.all()
            ]
            folio_data = {
                "status":   folio.status,
                "subtotal": float(folio.total_charges),
                "paid":     float(folio.total_paid),
                "balance":  float(folio.balance_due),
                "charges":  charges,
                "payments": folio_payments,
            }
        except GuestFolio.DoesNotExist:
            folio_data = None

        data = {
            "booking": {
                "id":                booking.id,
                "booking_code":      booking.booking_code or f"BK{booking.id:06d}",
                "status":            booking.status,
                "source":            booking.source or "",
                "check_in":          booking.check_in.isoformat() if booking.check_in else None,
                "check_out":         booking.check_out.isoformat() if booking.check_out else None,
                "actual_check_in":   booking.actual_check_in.isoformat() if booking.actual_check_in else None,
                "actual_check_out":  booking.actual_check_out.isoformat() if booking.actual_check_out else None,
                "nights":            (booking.check_out - booking.check_in).days if booking.check_in and booking.check_out else 0,
                "adults":            booking.adults,
                "children":          booking.children,
                "guests_count":      booking.guests_count,
                "special_requests":  booking.special_requests or "",
                "base_price":        float(booking.base_price),
                "tax":               float(booking.tax),
                "total_amount":      float(booking.total_amount),
                "created_at":        booking.created_at.isoformat() if booking.created_at else None,
                "created_by":        booking.created_by.name if booking.created_by else None,
                "checked_in_by":     booking.checked_in_by.name if booking.checked_in_by else None,
                "checked_out_by":    booking.checked_out_by.name if booking.checked_out_by else None,
            },

            "guest": {
                "id":          guest.id,
                "full_name":   guest.full_name,
                "phone":       guest.phone,
                "email":       guest.email or "",
                "nationality": guest.nationality or "",
                "id_type":     guest.id_type or "",
                "id_number":   guest.id_number or "",
                "id_photo":    request.build_absolute_uri(guest.id_photo.url) if guest.id_photo else None,
                "created_at":  guest.created_at.isoformat() if guest.created_at else None,
                "id_photos": [
                    {
                        "url":         request.build_absolute_uri(p.image.url),
                        "uploaded_at": p.uploaded_at.strftime("%d %b %Y, %H:%M") if p.uploaded_at else None,
                    }
                    for p in guest.id_photos.all()
                ],
            } if guest else None,

            "room": {
                "id":                room.id,
                "room_type":         room.room_type,
                "base_price":        float(room.base_price),
                "max_adults":        room.max_adults,
                "max_children":      room.max_children,
                "description":       room.description or "",
                "extra_adult_price": float(room.extra_adult_price),
                "extra_child_price": float(room.extra_child_price),
                "is_active":         room.is_active,
                "amenities": [
                    {"id": a.id, "name": a.name}
                    for a in room.amenities.all()
                ],
                "images": [
                    {
                        "url":        request.build_absolute_uri(img.image.url),
                        "is_primary": img.is_primary,
                    }
                    for img in room.images.all()
                ],
                "total_units":     room.total_units(),
                "available_units": room.available_units(),
            } if room else None,

            "room_unit": {
                "id":          unit.id,
                "room_number": unit.room_number,
                "status":      unit.status,
            } if unit else None,

            "payment": {
                "id":             payment.id,
                "room_charges":   float(payment.room_charges),
                "tax":            float(payment.tax),
                "total_amount":   float(payment.total_amount),
                "payment_method": payment.payment_method or "",
                "payment_status": payment.payment_status,
                "paid_at":        payment.paid_at.isoformat() if payment.paid_at else None,
                "collected_by":   payment.collected_by.name if payment.collected_by else None,
            } if payment else None,

            "folio": folio_data,
        }

        return Response(data)
from rest_framework.views import APIView
from rest_framework.response import Response
from billing.models import GuestFolio

class BookingFullListAPIView(APIView):
    def get(self, request):

        bookings = Booking.objects.select_related(
            "guest",
            "room",
            "room_unit",
            "payment",
            "created_by",
            "checked_in_by",
            "checked_out_by",
        ).prefetch_related(
            "guest__id_photos",
            "room__amenities",
            "room__images",
            "room__units",
        ).order_by("-created_at")

        data = []

        for booking in bookings:

            guest = booking.guest
            room = booking.room
            unit = booking.room_unit
            payment = getattr(booking, "payment", None)

            try:
                folio = GuestFolio.objects.prefetch_related(
                    "charges",
                    "payments"
                ).get(booking=booking)

                folio_data = {
                    "status": folio.status,
                    "subtotal": float(folio.total_charges),
                    "paid": float(folio.total_paid),
                    "balance": float(folio.balance_due),
                    "charges": [
                        {
                            "charge_type": c.charge_type,
                            "description": c.description,
                            "amount": float(c.amount),
                            "tax": float(c.tax_amount),
                            "total": float(c.total),
                            "date": c.date.isoformat() if c.date else None,
                        }
                        for c in folio.charges.all()
                    ],
                    "payments": [
                        {
                            "amount": float(p.amount),
                            "method": p.method,
                        }
                        for p in folio.payments.all()
                    ],
                }

            except GuestFolio.DoesNotExist:
                folio_data = None

            data.append({
                "booking": {
                    "id": booking.id,
                    "booking_code": booking.booking_code or f"BK{booking.id:06d}",
                    "status": booking.status,
                    "source": booking.source or "",
                    "check_in": booking.check_in.isoformat() if booking.check_in else None,
                    "check_out": booking.check_out.isoformat() if booking.check_out else None,
                    "actual_check_in": booking.actual_check_in.isoformat() if booking.actual_check_in else None,
                    "actual_check_out": booking.actual_check_out.isoformat() if booking.actual_check_out else None,
                    "nights": (
                        booking.check_out - booking.check_in
                    ).days if booking.check_in and booking.check_out else 0,
                    "adults": booking.adults,
                    "children": booking.children,
                    "guests_count": booking.guests_count,
                    "special_requests": booking.special_requests or "",
                    "base_price": float(booking.base_price),
                    "tax": float(booking.tax),
                    "total_amount": float(booking.total_amount),
                    "created_at": booking.created_at.isoformat() if booking.created_at else None,
                    "created_by": booking.created_by.name if booking.created_by else None,
                    "checked_in_by": booking.checked_in_by.name if booking.checked_in_by else None,
                    "checked_out_by": booking.checked_out_by.name if booking.checked_out_by else None,
                },

                "guest": {
                    "id": guest.id,
                    "full_name": guest.full_name,
                    "phone": guest.phone,
                    "email": guest.email or "",
                    "nationality": guest.nationality or "",
                    "id_type": guest.id_type or "",
                    "id_number": guest.id_number or "",
                    "id_photo": request.build_absolute_uri(
                        guest.id_photo.url
                    ) if guest and guest.id_photo else None,
                    "created_at": guest.created_at.isoformat() if guest and guest.created_at else None,
                } if guest else None,

                "room": {
                    "id": room.id,
                    "room_type": room.room_type,
                    "base_price": float(room.base_price),
                    "max_adults": room.max_adults,
                    "max_children": room.max_children,
                    "description": room.description or "",
                    "extra_adult_price": float(room.extra_adult_price),
                    "extra_child_price": float(room.extra_child_price),
                    "is_active": room.is_active,
                    "amenities": [
                        {"id": a.id, "name": a.name}
                        for a in room.amenities.all()
                    ],
                    "images": [
                        {
                            "url": request.build_absolute_uri(img.image.url),
                            "is_primary": img.is_primary,
                        }
                        for img in room.images.all()
                    ],
                } if room else None,

                "room_unit": {
                    "id": unit.id,
                    "room_number": unit.room_number,
                    "status": unit.status,
                } if unit else None,

                "payment": {
                    "id": payment.id,
                    "room_charges": float(payment.room_charges),
                    "tax": float(payment.tax),
                    "total_amount": float(payment.total_amount),
                    "payment_method": payment.payment_method or "",
                    "payment_status": payment.payment_status,
                    "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
                    "collected_by": payment.collected_by.name if payment.collected_by else None,
                } if payment else None,

                "folio": folio_data,
            })

        return Response(data)
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import connection
from django_tenants.utils import schema_context

from accounts.models import Hotel
from .models import Room, Booking


class RoomWithBookingsAPIView(APIView):
    def get(self, request):

        current_tenant = connection.tenant

        with schema_context("public"):
            hotel = Hotel.objects.filter(
                schema_name=current_tenant.schema_name
            ).first()

        rooms = Room.objects.prefetch_related(
            "units",
            "amenities",
            "images"
        ).all()

        data = {
            "hotel": {
                "id": hotel.id if hotel else None,
                "hotel_name": hotel.hotel_name if hotel else "",
                "owner_name": hotel.owner_name if hotel else "",
                "email": hotel.email if hotel else "",
                "city": hotel.city if hotel else "",
                "address": hotel.address if hotel else "",
                "property_type": hotel.property_type if hotel else "",
                "logo": (
                    request.build_absolute_uri(hotel.logo.url)
                    if hotel and hotel.logo else None
                ),
            },
            "rooms": []
        }

        for room in rooms:

            bookings = Booking.objects.select_related(
                "guest",
                "room_unit",
                "payment"
            ).filter(room=room).order_by("-created_at")

            room_data = {
                "id": room.id,
                "room_type": room.room_type,
                "base_price": float(room.base_price),
                "max_adults": room.max_adults,
                "max_children": room.max_children,
                "extra_adult_price": float(room.extra_adult_price),
                "extra_child_price": float(room.extra_child_price),
                "description": room.description,
                "is_active": room.is_active,
                "total_units": room.total_units(),
                "available_units": room.available_units(),

                "amenities": [
                    {
                        "id": a.id,
                        "name": a.name
                    }
                    for a in room.amenities.all()
                ],

                "images": [
                    {
                        "id": img.id,
                        "url": request.build_absolute_uri(img.image.url),
                        "is_primary": img.is_primary
                    }
                    for img in room.images.all()
                ],

                "units": [
                    {
                        "id": unit.id,
                        "room_number": unit.room_number,
                        "status": unit.status,
                    }
                    for unit in room.units.all()
                ],

                "bookings": [
                    {
                        "booking_id": b.id,
                        "booking_code": b.booking_code or f"BK{b.id:06d}",
                        "status": b.status,

                        "guest": {
                            "id": b.guest.id if b.guest else None,
                            "name": b.guest.full_name if b.guest else "",
                            "phone": b.guest.phone if b.guest else "",
                            "email": b.guest.email if b.guest else "",
                        },

                        "room_unit": {
                            "id": b.room_unit.id if b.room_unit else None,
                            "room_number": b.room_unit.room_number if b.room_unit else "",
                            "status": b.room_unit.status if b.room_unit else "",
                        },

                        "check_in": b.check_in.isoformat() if b.check_in else None,
                        "check_out": b.check_out.isoformat() if b.check_out else None,
                        "actual_check_in": b.actual_check_in.isoformat() if b.actual_check_in else None,
                        "actual_check_out": b.actual_check_out.isoformat() if b.actual_check_out else None,

                        "adults": b.adults,
                        "children": b.children,
                        "guests_count": b.guests_count,

                        "base_price": float(b.base_price),
                        "tax": float(b.tax),
                        "total_amount": float(b.total_amount),

                        "payment": {
                            "payment_status": b.payment.payment_status,
                            "payment_method": b.payment.payment_method,
                            "total_amount": float(b.payment.total_amount),
                        } if hasattr(b, "payment") and b.payment else None,
                    }
                    for b in bookings
                ]
            }

            data["rooms"].append(room_data)

        return Response(data)