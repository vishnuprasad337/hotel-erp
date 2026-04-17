
from rest_framework import serializers
from .models import Booking, Guest, Room, RoomUnit, Payment
from datetime import datetime
from rest_framework import serializers

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