from rest_framework import serializers
from .models import Hotel, User, Permission, RolePermission,  HotelModule,Department,Staff
from django.db import connection
from django_tenants.utils import schema_context

class HotelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hotel
        fields = '__all__'


from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password

User = get_user_model()

class DepartmentSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "name", "permissions"]

    def get_permissions(self, obj):
        perms = RolePermission.objects.filter(role=obj)\
            .values_list("permission__name", flat=True)
        return list(perms)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer()
    department = DepartmentSerializer()

    class Meta:
        model = Staff
        fields = [
            "id",
            "name",
            "employee_id",
            "phone",
            "salary",
            "is_active",
            "is_available",
            "department",
            "user"
        ]



class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = '__all__'


class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = '__all__'





class HotelModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = HotelModule
        fields = '__all__'