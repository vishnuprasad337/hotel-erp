
from rest_framework import serializers
from .models import Booking, Guest, Room, RoomUnit, Payment,SeasonalRate
from datetime import datetime
from rest_framework import serializers
from django.utils import timezone
from pms.models import Booking, GuestIDPhoto
from accounts.models import Staff


from datetime import datetime


class BookingSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField(required=False, allow_blank=True)
    nationality = serializers.CharField(required=False, allow_blank=True)

    room_type = serializers.CharField()
    check_in = serializers.DateField()
    check_out = serializers.DateField()
    guests = serializers.IntegerField(default=1)

    requests = serializers.CharField(required=False, allow_blank=True)
    id_photo = serializers.ImageField(required=False)

    def create(self, validated_data):
        request = self.context.get("request")
        staff = self.context.get("staff")
        hotel = staff.hotel

        name = validated_data.get("name")
        phone = validated_data.get("phone")
        email = validated_data.get("email", "")
        nationality = validated_data.get("nationality", "")
        room_type = validated_data.get("room_type")
        check_in = validated_data.get("check_in")
        check_out = validated_data.get("check_out")
        guests = validated_data.get("guests", 1)
        requests_text = validated_data.get("requests", "")
        id_photo = validated_data.get("id_photo", None)

       
        guest, created = Guest.objects.get_or_create(
            phone=phone,
            hotel=hotel,
            defaults={
                "full_name": name,
                "email": email,
                "nationality": nationality,
                "id_photo": id_photo
            }
        )

        if not created and guest.full_name != name:
            guest.full_name = name
            guest.save()

        if id_photo and not guest.id_photo:
            guest.id_photo = id_photo
            guest.save()

        
        room = Room.objects.filter(hotel=hotel, room_type=room_type).first()
        if not room:
            raise serializers.ValidationError(f"Room type '{room_type}' not found")

       
        unit = RoomUnit.objects.filter(room=room, status="Available").first()
        if not unit:
            raise serializers.ValidationError(f"No available rooms for type {room_type}")

       
        nights = (check_out - check_in).days
        if nights <= 0:
            raise serializers.ValidationError("Check-out must be after check-in")

        unit.status = "Reserved"
        unit.save()

       
        booking = Booking.objects.create(
            hotel=hotel,
            guest=guest,
            room=room,
            room_unit=unit,
            check_in=check_in,
            check_out=check_out,
            guests_count=guests,
            special_requests=requests_text,
            status="confirmed",
            created_by=staff
        )

        
        room_charges = float(room.price) * nights
        tax = room_charges * 0.18
        total = room_charges + tax

        Payment.objects.create(
            booking=booking,
            room_charges=room_charges,
            tax=tax,
            total_amount=total
        )

        return booking
from rest_framework import serializers
from .models import Property, Room, RoomUnit, RoomImage, Guest, GuestIDPhoto, Payment


class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = ["id", "name"]


class RoomImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomImage
        fields = ["id", "image", "is_primary"]


class RoomUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomUnit
        fields = ["id", "room_number", "status"]

class SeasonalRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeasonalRate
        fields = ['id', 'start_date', 'end_date', 'price', 'reason', 'tag']
class RoomSerializer(serializers.ModelSerializer):
    amenities     = PropertySerializer(many=True, read_only=True)
    images        = RoomImageSerializer(many=True, read_only=True)
    units         = RoomUnitSerializer(many=True, read_only=True)
    total_units   = serializers.SerializerMethodField()
    available_units = serializers.SerializerMethodField()

    class Meta:
        model = Room
        fields = [
            "id",
            "room_type",
            "base_price",
            "max_adults",
            "max_children",
            "description",
            "extra_adult_price",
            "extra_child_price",
            "is_active",
            "amenities",
            "images",
            "units",
            "total_units",
            "available_units",
            'seasonal_rates',
        ]

    def get_total_units(self, obj):
        return obj.total_units()

    def get_available_units(self, obj):
        return obj.available_units()


class RoomCreateSerializer(serializers.ModelSerializer):
    amenities   = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(),
        many=True,
        required=False
    )
    total_units = serializers.IntegerField(write_only=True, default=1)
    images      = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Room
        fields = [
            "id",
            "room_type",
            "base_price",
            "max_adults",
            "max_children",
            "description",
            "extra_adult_price",
            "extra_child_price",
            "amenities",
            "total_units",
            "images",
        ]

    def create(self, validated_data):
        amenities   = validated_data.pop("amenities", [])
        total_units = validated_data.pop("total_units", 1)
        images      = validated_data.pop("images", [])

        room = Room.objects.create(**validated_data)

        if amenities:
            room.amenities.set(amenities)

        prefix_map = {
            "Single": "S",
            "Double": "D",
            "Deluxe": "DL",
            "Suite":  "SU",
        }
        prefix = prefix_map.get(room.room_type, "R")

        existing_numbers = set(RoomUnit.objects.values_list("room_number", flat=True))
        units   = []
        counter = 1

        while len(units) < total_units:
            number = f"{prefix}{counter}"
            if number not in existing_numbers:
                units.append(RoomUnit(room=room, room_number=number))
            counter += 1

        RoomUnit.objects.bulk_create(units)

        for i, img in enumerate(images):
            RoomImage.objects.create(room=room, image=img, is_primary=(i == 0))

        return room


class RoomUnitStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RoomUnit
        fields = ["id", "status"]

    def validate_status(self, value):
        valid_statuses = ["Available", "Occupied", "Dirty", "Cleaning", "Maintenance", "Reserved"]
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Invalid status. Choose from {valid_statuses}")
        return value

    def validate(self, data):
        if self.instance and self.instance.status == "Occupied" and data.get("status") != "Dirty":
            raise serializers.ValidationError("Cannot change occupied room status unless checking out.")
        return data


class GuestIDPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model  = GuestIDPhoto
        fields = ["id", "image", "uploaded_at"]


class GuestSerializer(serializers.ModelSerializer):
    id_photos     = GuestIDPhotoSerializer(many=True, read_only=True)
    booking_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model  = Guest
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "nationality",
            "id_type",
            "id_number",
            "id_photo",
            "created_at",
            "id_photos",
            "booking_count",
        ]


class GuestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Guest
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "nationality",
            "id_type",
            "id_number",
            "id_photo",
        ]

    def validate_full_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Full name is required.")
        return value.strip()


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Payment
        fields = [
            "id",
            "booking",
            "room_charges",
            "tax",
            "total_amount",
            "payment_method",
            "payment_status",
            "paid_at",
            "collected_by",
        ]
class CheckInSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    id_photos  = serializers.ListField(
        child=serializers.ImageField(),
        allow_empty=False,
        error_messages={"empty": "At least one ID photo is required."}
    )

    def validate_booking_id(self, value):
        try:
            booking = Booking.objects.select_related("guest", "room_unit").get(
                id=value, status="confirmed"
            )
        except Booking.DoesNotExist:
            raise serializers.ValidationError("Booking not found or not confirmed.")

        if not booking.guest:
            raise serializers.ValidationError("Guest data missing in booking.")

        self._booking = booking
        return value

    def validate_id_photos(self, photos):
        for photo in photos:
            if not photo.content_type.startswith("image/"):
                raise serializers.ValidationError("Only image files are allowed.")
        return photos

    def save(self, **kwargs):
        request      = self.context.get("request")
        booking      = self._booking
        guest        = booking.guest
        photos       = self.validated_data["id_photos"]

        for photo in photos:
            GuestIDPhoto.objects.create(guest=guest, image=photo)

        session_staff_id = request.session.get("staff_id") if request else None
        checked_in_by    = Staff.objects.filter(id=session_staff_id).first()

        booking.status          = "checked_in"
        booking.actual_check_in = timezone.now()
        booking.checked_in_by   = checked_in_by
        booking.save()

        if booking.room_unit:
            booking.room_unit.status = "Occupied"
            booking.room_unit.save()

        return booking, checked_in_by


class CheckOutSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
    method     = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        try:
            booking = Booking.objects.select_related("room_unit").get(
                id=data["booking_id"], status="checked_in"
            )
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"booking_id": "Booking not found or not checked-in."})

        try:
            payment = Payment.objects.get(booking=booking)
        except Payment.DoesNotExist:
            raise serializers.ValidationError({"booking_id": "No payment record found for this booking."})

        if payment.payment_status != "paid":
            raise serializers.ValidationError({
                "payment_status": "Payment is pending. Please collect payment before checking out.",
                "total_amount":   float(payment.total_amount),
            })

        self._booking = booking
        self._payment = payment
        return data

    def save(self, **kwargs):
        request        = self.context.get("request")
        booking        = self._booking
        payment        = self._payment
        method         = self.validated_data.get("method", payment.payment_method)

        session_staff_id = request.session.get("staff_id") if request else None
        checked_out_by   = Staff.objects.filter(id=session_staff_id).first()

        booking.status           = "checked_out"
        booking.actual_check_out = timezone.now()
        booking.checked_out_by   = checked_out_by
        booking.save()

        if booking.room_unit:
            booking.room_unit.status = "Dirty"
            booking.room_unit.save()

        payment.payment_method = method
        payment.paid_at        = timezone.now()
        payment.save()

        return booking, checked_out_by


class CreateBookingSerializer(serializers.Serializer):
    room        = serializers.IntegerField()
    room_unit   = serializers.IntegerField()
    check_in    = serializers.DateField()
    check_out   = serializers.DateField()
    adults      = serializers.IntegerField(default=1)
    children    = serializers.IntegerField(default=0)
    source           = serializers.CharField(required=False, allow_blank=True, default="walk-in")
    special_requests = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    full_name   = serializers.CharField()
    phone       = serializers.CharField()
    email       = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    nationality = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    id_type     = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    id_number   = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, data):
        from datetime import date
        from billing.models import GuestFolio

        check_in  = data.get("check_in")
        check_out = data.get("check_out")

        if check_in < date.today():
            raise serializers.ValidationError({"check_in": "Check-in cannot be in the past."})

        if check_out <= check_in:
            raise serializers.ValidationError({"check_out": "Check-out must be after check-in."})

        try:
            room = Room.objects.get(id=data.get("room"))
        except Room.DoesNotExist:
            raise serializers.ValidationError({"room": f"Room with ID {data.get('room')} not found."})

        try:
            room_unit = RoomUnit.objects.get(id=data.get("room_unit"))
        except RoomUnit.DoesNotExist:
            raise serializers.ValidationError({"room_unit": f"Room unit with ID {data.get('room_unit')} not found."})

        if room_unit.status in ["Maintenance", "Cleaning", "Dirty"]:
            raise serializers.ValidationError({
                "room_unit": f"Room {room_unit.room_number} is currently {room_unit.status} and cannot be booked."
            })

        conflict = Booking.objects.filter(
            room_unit=room_unit,
            status__in=["confirmed", "checked_in"],
            check_in__lt=check_out,
            check_out__gt=check_in,
        ).exists()

        if conflict:
            raise serializers.ValidationError({
                "room_unit": f"Room {room_unit.room_number} is already booked for the selected dates."
            })

        data["_room"]      = room
        data["_room_unit"] = room_unit
        return data

    def create(self, validated_data):
        from billing.models import GuestFolio, FolioCharge

        room      = validated_data.pop("_room")
        room_unit = validated_data.pop("_room_unit")
        request   = self.context.get("request")

        full_name   = validated_data.get("full_name", "").strip()
        phone       = validated_data.get("phone", "").strip()
        email       = validated_data.get("email")
        nationality = validated_data.get("nationality")
        id_type     = validated_data.get("id_type")
        id_number   = validated_data.get("id_number")
        check_in    = validated_data.get("check_in")
        check_out   = validated_data.get("check_out")
        adults      = validated_data.get("adults", 1)
        children    = validated_data.get("children", 0)
        source      = validated_data.get("source") or "walk-in"
        special_requests = validated_data.get("special_requests")

        guest, created = Guest.objects.get_or_create(
            phone=phone,
            defaults={
                "full_name":   full_name,
                "email":       email,
                "nationality": nationality,
                "id_type":     id_type,
                "id_number":   id_number,
            }
        )

        if not created:
            updated = False
            if full_name   and guest.full_name   != full_name:   guest.full_name   = full_name;   updated = True
            if email       is not None and guest.email       != email:      guest.email       = email;      updated = True
            if nationality is not None and guest.nationality != nationality: guest.nationality = nationality; updated = True
            if id_type     is not None and guest.id_type     != id_type:    guest.id_type     = id_type;    updated = True
            if id_number   is not None and guest.id_number   != id_number:  guest.id_number   = id_number;  updated = True
            if updated:
                guest.save()

        nights       = (check_out - check_in).days
        room_charges = float(room.base_price) * nights
        tax          = room_charges * 0.18
        total_amount = room_charges + tax

        session_staff_id = request.session.get("staff_id") if request else None
        created_by_staff = Staff.objects.filter(id=session_staff_id).first()

        booking = Booking.objects.create(
            guest            = guest,
            room             = room,
            room_unit        = room_unit,
            check_in         = check_in,
            check_out        = check_out,
            adults           = adults,
            children         = children,
            guests_count     = adults + children,
            special_requests = special_requests,
            source           = source,
            base_price       = room.base_price,
            tax              = round(tax, 2),
            total_amount     = round(total_amount, 2),
            status           = "confirmed",
            created_by       = created_by_staff,
        )

        Payment.objects.create(
            booking        = booking,
            room_charges   = round(room_charges, 2),
            tax            = round(tax, 2),
            total_amount   = round(total_amount, 2),
            payment_status = "pending",
        )

        folio = GuestFolio.objects.create(booking=booking)
        FolioCharge.objects.create(
            folio       = folio,
            charge_type = "room",
            description = f"{room.room_type} Room Charge ({nights} night(s))",
            amount      = round(room_charges, 2),
            tax_amount  = round(tax, 2),
            date        = check_in,
        )

        return booking