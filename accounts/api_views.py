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
    def get(self, request, pk):
        hotel = get_object_or_404(
            Hotel.objects.prefetch_related(
                'staffs__user',
                'staffs__department',
                'departments',
                'payments',
                'hotelmodule_set__module',
            ).select_related('subscription_plan'),
            pk=pk
        )
        return Response(HotelFullDetailsSerializer(hotel).data)


class HotelAllFullDetailsView(APIView):
    def get(self, request):
        hotels = Hotel.objects.prefetch_related(
            'staffs__user',
            'staffs__department',
            'departments',
            'payments',
            'hotelmodule_set__module',
        ).select_related('subscription_plan').all()
        return Response(HotelFullDetailsSerializer(hotels, many=True).data)


class DepartmentListCreateView(APIView):
    def get(self, request):
        hotel_id = request.query_params.get('hotel_id')
        qs = Department.objects.filter(hotel_id=hotel_id) if hotel_id else Department.objects.all()
        return Response(DepartmentSerializer(qs, many=True).data)

    def post(self, request):
        serializer = DepartmentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        return Response(UserSerializer(User.objects.all(), many=True).data)

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
        return Response(PermissionSerializer(Permission.objects.all(), many=True).data)

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
        role_id = request.query_params.get('role_id')
        qs = RolePermission.objects.filter(role_id=role_id) if role_id else RolePermission.objects.all()
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
        return Response(AmenitySerializer(Amenity.objects.all(), many=True).data)

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
        return Response(SubscriptionPlanSerializer(SubscriptionPlan.objects.all(), many=True).data)

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
        qs = Staff.objects.filter(hotel_id=hotel_id) if hotel_id else Staff.objects.all()
        return Response(StaffSerializer(qs, many=True).data)

    def post(self, request):
        serializer = StaffSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StaffDetailView(APIView):
    def get_object(self, pk):
        return get_object_or_404(Staff, pk=pk)

    def get(self, request, pk):
        return Response(StaffSerializer(self.get_object(pk)).data)

    def put(self, request, pk):
        serializer = StaffSerializer(self.get_object(pk), data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        serializer = StaffSerializer(self.get_object(pk), data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        self.get_object(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)