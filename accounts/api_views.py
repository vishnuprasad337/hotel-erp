from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import (
    Hotel, Department, User, Permission, RolePermission,
    Amenity, SubscriptionPlan, PlanPayment, HotelModule, Staff
)
from .serializers import (
    HotelSerializer, HotelFullDetailsSerializer, DepartmentSerializer,
    UserSerializer, PermissionSerializer, RolePermissionSerializer,
    AmenitySerializer, SubscriptionPlanSerializer, PlanPaymentSerializer,
    HotelModuleSerializer, StaffSerializer
)


class HotelListCreateView(APIView):
    def get(self, request):
        serializer = HotelSerializer(Hotel.objects.all(), many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = HotelSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HotelDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Hotel, pk=pk)

    def get(self, request, pk):
        return Response(HotelSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = HotelSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = HotelSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class HotelFullDetailsView(APIView):
    def get(self, request, hotel_name):
        hotel = get_object_or_404(
            Hotel.objects.prefetch_related(
                'staffs__user',
                'staffs__department',
                'departments',
                'payments',
                'hotelmodule_set__module',
            ).select_related('subscription_plan'),
            hotel_name=hotel_name
        )

        return Response(HotelFullDetailsSerializer(hotel).data)


from django.conf import settings
from django_tenants.utils import schema_context

class HotelAllFullDetailsView(APIView):
    def get(self, request):
        api_key = request.headers.get("API-KEY")
        if api_key != settings.MY_API_KEY:
            return Response({"error": "Invalid API Key"}, status=403)

        schema_name = (
            request.headers.get("X-DTS-Schema") or
            request.headers.get("X-Schema-Name")
        )

        if not schema_name or schema_name == "public":
            return Response({"error": "X-DTS-Schema header required"}, status=400)

        from datetime import date
        from pms.models import Room as TenantRoom

        today = date.today()
        tenant_rooms = []

        with schema_context(schema_name):
            rooms = TenantRoom.objects.prefetch_related(
                'units', 'images', 'seasonal_rates'
            ).filter(is_active=True)

            for room in rooms:
                all_seasonal = list(room.seasonal_rates.all())

                seasonal = next(
                    (r for r in all_seasonal
                     if r.start_date <= today <= r.end_date),
                    None
                )
                effective_price = seasonal.price if seasonal else room.base_price

                tenant_rooms.append({
                    "id":              room.id,
                    "room_type":       (room.custom_room_type if room.room_type == "Custom" and room.custom_room_type else room.room_type).lower(),
                    "base_price":      str(effective_price),
                    "price":           str(effective_price),
                    "is_seasonal":     seasonal is not None,
                    "seasonal_reason": seasonal.reason if seasonal else "",
                    "max_adults":      room.max_adults,
                    "max_children":    room.max_children,
                    "description":     room.description,
                    "total_units":     room.units.count(),
                    "available_units": sum(1 for u in room.units.all() if u.status == "Available"),
                    "units":           [{"id": u.id, "number": u.room_number, "status": u.status} for u in room.units.all()],
                    "images":          [img.image.url for img in room.images.all()],
                    "seasonal_rates":  [
                        {
                            "start_date": str(r.start_date),
                            "end_date":   str(r.end_date),
                            "price":      str(r.price),
                            "reason":     r.reason,
                        }
                        for r in all_seasonal
                    ],
                })

        print(f"DEBUG tenant_rooms fetched: {[r['room_type'] for r in tenant_rooms]}")

        with schema_context(schema_name):
            hotels = Hotel.objects.prefetch_related(
                'staffs__user',
                'staffs__department',
                'departments',
                'payments',
                'hotelmodule_set__module',
            ).select_related('subscription_plan').all()

            data = HotelFullDetailsSerializer(
                hotels,
                many=True,
                context={
                    'schema_name': schema_name,
                    'request': request,
                    'tenant_rooms': tenant_rooms,
                }
            ).data

        data = list(data)
        for hotel in data:
            hotel['rooms'] = tenant_rooms

        return Response(data)
class DepartmentListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        hotel_name = request.query_params.get('hotel_name')
        
        qs = Department.objects.all()
        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
        if hotel_name:
            qs = qs.filter(hotel__hotel_name__icontains=hotel_name)
        
        return Response(DepartmentSerializer(qs, many=True).data)
class DepartmentDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Department, pk=pk)

    def get(self, request, pk):
        return Response(DepartmentSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = DepartmentSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = DepartmentSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = User.objects.filter(hotel_id=hotel_id) if hotel_id else User.objects.all()
        return Response(UserSerializer(qs, many=True).data)

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(User, pk=pk)

    def get(self, request, pk):
        return Response(UserSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = UserSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = UserSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = Permission.objects.filter(hotel_id=hotel_id) if hotel_id else Permission.objects.all()
        return Response(PermissionSerializer(qs, many=True).data)

    def post(self, request):
        serializer = PermissionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PermissionDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Permission, pk=pk)

    def get(self, request, pk):
        return Response(PermissionSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = PermissionSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = PermissionSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RolePermissionListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        role_id = request.query_params.get('role_id')
        qs = RolePermission.objects.all()
        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
        if role_id:
            qs = qs.filter(role_id=role_id)
        return Response(RolePermissionSerializer(qs, many=True).data)

    def post(self, request):
        serializer = RolePermissionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RolePermissionDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(RolePermission, pk=pk)

    def get(self, request, pk):
        return Response(RolePermissionSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = RolePermissionSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = RolePermissionSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AmenityListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = Amenity.objects.filter(hotel_id=hotel_id) if hotel_id else Amenity.objects.all()
        return Response(AmenitySerializer(qs, many=True).data)

    def post(self, request):
        serializer = AmenitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AmenityDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Amenity, pk=pk)

    def get(self, request, pk):
        return Response(AmenitySerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = AmenitySerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = AmenitySerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriptionPlanListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = SubscriptionPlan.objects.filter(hotel_id=hotel_id) if hotel_id else SubscriptionPlan.objects.all()
        return Response(SubscriptionPlanSerializer(qs, many=True).data)

    def post(self, request):
        serializer = SubscriptionPlanSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionPlanDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(SubscriptionPlan, pk=pk)

    def get(self, request, pk):
        return Response(SubscriptionPlanSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = SubscriptionPlanSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = SubscriptionPlanSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlanPaymentListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = PlanPayment.objects.filter(hotel_id=hotel_id) if hotel_id else PlanPayment.objects.all()
        return Response(PlanPaymentSerializer(qs, many=True).data)

    def post(self, request):
        serializer = PlanPaymentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PlanPaymentDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(PlanPayment, pk=pk)

    def get(self, request, pk):
        return Response(PlanPaymentSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = PlanPaymentSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = PlanPaymentSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HotelModuleListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = HotelModule.objects.filter(hotel_id=hotel_id) if hotel_id else HotelModule.objects.all()
        return Response(HotelModuleSerializer(qs, many=True).data)

    def post(self, request):
        serializer = HotelModuleSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HotelModuleDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(HotelModule, pk=pk)

    def get(self, request, pk):
        return Response(HotelModuleSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = HotelModuleSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = HotelModuleSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        hotel_name = request.query_params.get('hotel_name')

        qs = Staff.objects.all()
        if hotel_id:
            qs = qs.filter(hotel_id=hotel_id)
        if hotel_name:
            qs = qs.filter(hotel__hotel_name__icontains=hotel_name)

        return Response(StaffSerializer(qs, many=True).data)
    def post(self, request):
        serializer = StaffSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StaffDetailView(APIView):
    def get_object(self, pk, hotel_id):
        return get_object_or_404(Staff, pk=pk, hotel_id=hotel_id)

    def get(self, request, pk):
        hotel_id = request.query_params.get('hotel_id')
        if not hotel_id:
            return Response(
                {"error": "hotel_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        staff = self.get_object(pk, hotel_id)
        return Response(StaffSerializer(staff).data)

    def put(self, request, pk):
        hotel_id = request.data.get('hotel') or request.query_params.get('hotel_id')
        if not hotel_id:
            return Response(
                {"error": "hotel_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        staff = self.get_object(pk, hotel_id)
        serializer = StaffSerializer(staff, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        hotel_id = request.data.get('hotel') or request.query_params.get('hotel_id')
        if not hotel_id:
            return Response(
                {"error": "hotel_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        staff = self.get_object(pk, hotel_id)
        serializer = StaffSerializer(staff, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        hotel_id = request.query_params.get('hotel_id')
        if not hotel_id:
            return Response(
                {"error": "hotel_id query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        staff = self.get_object(pk, hotel_id)
        staff.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)