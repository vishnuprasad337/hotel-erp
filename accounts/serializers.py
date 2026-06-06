from rest_framework import serializers
from django.contrib.auth import get_user_model

from accounts.models import (
    Hotel, Department, Permission, RolePermission,
    Amenity, SubscriptionPlan, PlanPayment, HotelModule, Staff
)
from pms.models import Room, RoomUnit, RoomImage, Guest, Booking, Payment
from restaurant.models import (
    MenuCategory, MenuItem, Table, TableReservation,
    RestaurantOrder, OrderItem
)
from billing.models import GuestFolio, FolioCharge, Invoice, BillingPayment
from inventory.models import (
    InventoryItem, StockAdjustment, PurchaseOrder, PurchaseItem,
    Expense, HotelAsset, MaintenanceLog,
    LaundryOrder, LaundryOrderItem, LaundryStatusLog
)
from hotel.models import (
    Task, ShiftTemplate, Shift, Attendance, LeaveRequest,
    Payroll, Notification
)

User = get_user_model()


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ['id', 'name']


class DepartmentSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    hotel_name = serializers.CharField(source='hotel.hotel_name', read_only=True)

    class Meta:
        model = Department
        fields = ['id', 'hotel', 'hotel_name', 'name', 'permissions']
    def get_permissions(self, obj):
        return list(
            RolePermission.objects.filter(role=obj)
            .values_list('permission__name', flat=True)
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    hotel_name = serializers.CharField(source='hotel.hotel_name', read_only=True)

    class Meta:
        model = Staff
        fields = [
            'id', 'hotel', 'hotel_name', 'name', 'employee_id', 'phone', 'salary',
            'is_active', 'is_available', 'department', 'user'
        ]


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ['id', 'name', 'description', 'is_core']


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    modules = AmenitySerializer(many=True, read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'price', 'modules', 'is_trial_plan', 'trial_days', 'tagline']


class PlanPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanPayment
        fields = ['id', 'plan', 'amount', 'status', 'due_date', 'paid_date', 'transaction_id']


class HotelModuleSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source='module.name', read_only=True)

    class Meta:
        model = HotelModule
        fields = ['id', 'module', 'module_name', 'is_enabled']


class RoomImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomImage
        fields = ['id', 'image', 'is_primary']


class RoomUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomUnit
        fields = ['id', 'room_number', 'status']


class RoomSerializer(serializers.ModelSerializer):
    units = RoomUnitSerializer(many=True, read_only=True)
    images = RoomImageSerializer(many=True, read_only=True)

    class Meta:
        model = Room
        fields = [
            'id', 'room_type', 'base_price', 'max_adults', 'max_children',
            'description', 'extra_adult_price', 'extra_child_price',
            'is_active', 'units', 'images'
        ]


class GuestSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guest
        fields = ['id', 'full_name', 'phone', 'email', 'nationality', 'id_type', 'id_number']


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            'id', 'room_charges', 'tax', 'total_amount',
            'payment_method', 'payment_status', 'paid_at'
        ]


class BookingSerializer(serializers.ModelSerializer):
    guest = GuestSerializer(read_only=True)
    room = serializers.StringRelatedField()
    room_unit = serializers.StringRelatedField()
    payment = PaymentSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_code', 'guest', 'room', 'room_unit',
            'check_in', 'check_out', 'actual_check_in', 'actual_check_out',
            'adults', 'children', 'status', 'base_price', 'discount',
            'tax', 'total_amount', 'source', 'notes', 'payment', 'created_at'
        ]


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = ['id', 'name', 'description', 'price', 'tax_percent', 'is_available', 'is_veg', 'image']


class MenuCategorySerializer(serializers.ModelSerializer):
    items = MenuItemSerializer(many=True, read_only=True)

    class Meta:
        model = MenuCategory
        fields = ['id', 'name', 'order', 'items']


class TableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Table
        fields = ['id', 'number', 'capacity', 'is_occupied']


class TableReservationSerializer(serializers.ModelSerializer):
    table = serializers.StringRelatedField()

    class Meta:
        model = TableReservation
        fields = ['id', 'table', 'guest_name', 'phone', 'reservation_time', 'guests_count', 'status']


class OrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ['id', 'item', 'item_name', 'quantity', 'unit_price', 'note', 'subtotal']


class RestaurantOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = RestaurantOrder
        fields = [
            'id', 'order_number', 'order_type', 'table', 'room',
            'booking', 'status', 'charge_to_room',
            'total_amount', 'tax_amount', 'created_at', 'items'
        ]


class FolioChargeSerializer(serializers.ModelSerializer):
    total = serializers.ReadOnlyField()

    class Meta:
        model = FolioCharge
        fields = ['id', 'charge_type', 'description', 'amount', 'tax_amount', 'total', 'date']


class BillingPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingPayment
        fields = ['id', 'amount', 'tax_amount', 'total_amount', 'method', 'payment_status', 'received_at']


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'subtotal', 'tax_total',
            'discount', 'grand_total', 'status', 'generated_at'
        ]


class GuestFolioSerializer(serializers.ModelSerializer):
    charges = FolioChargeSerializer(many=True, read_only=True)
    payments = BillingPaymentSerializer(many=True, read_only=True)
    invoice = InvoiceSerializer(read_only=True)
    total_charges = serializers.ReadOnlyField()
    total_paid = serializers.ReadOnlyField()
    balance_due = serializers.ReadOnlyField()
    is_settled = serializers.ReadOnlyField()

    class Meta:
        model = GuestFolio
        fields = [
            'id', 'status', 'total_charges', 'total_paid',
            'balance_due', 'is_settled', 'notes',
            'charges', 'payments', 'invoice', 'created_at'
        ]


class StockAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAdjustment
        fields = ['id', 'adjustment_type', 'quantity', 'note', 'created_at']


class InventoryItemSerializer(serializers.ModelSerializer):
    adjustments = StockAdjustmentSerializer(many=True, read_only=True)
    is_low_stock = serializers.ReadOnlyField()
    stock_value = serializers.ReadOnlyField()

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'name', 'unit', 'current_stock', 'minimum_stock',
            'cost_per_unit', 'is_low_stock', 'stock_value', 'adjustments'
        ]


class PurchaseItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = PurchaseItem
        fields = ['id', 'item', 'item_name', 'quantity', 'unit_price', 'subtotal']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ['id', 'vendor', 'total_amount', 'status', 'ordered_at', 'received_at', 'items']


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = ['id', 'source', 'amount', 'description', 'expense_date']


class MaintenanceLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceLog
        fields = [
            'id', 'maintenance_type', 'priority', 'status',
            'description', 'performed_at', 'labour_cost', 'parts_cost', 'cost'
        ]


class HotelAssetSerializer(serializers.ModelSerializer):
    maintenance_logs = MaintenanceLogSerializer(many=True, read_only=True)
    location_display = serializers.ReadOnlyField()
    is_warranty_active = serializers.ReadOnlyField()
    maintenance_due = serializers.ReadOnlyField()

    class Meta:
        model = HotelAsset
        fields = [
            'id', 'name', 'serial_number', 'status', 'location_display',
            'purchase_date', 'purchase_cost', 'warranty_end', 'next_maintenance',
            'is_warranty_active', 'maintenance_due', 'maintenance_logs'
        ]


class LaundryOrderItemSerializer(serializers.ModelSerializer):
    service_name = serializers.CharField(source='service.name', read_only=True)
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = LaundryOrderItem
        fields = ['id', 'service', 'service_name', 'item_name', 'quantity', 'unit_price', 'subtotal']


class LaundryStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LaundryStatusLog
        fields = ['id', 'status', 'note', 'created_at']


class LaundryOrderSerializer(serializers.ModelSerializer):
    items = LaundryOrderItemSerializer(many=True, read_only=True)
    logs = LaundryStatusLogSerializer(many=True, read_only=True)

    class Meta:
        model = LaundryOrder
        fields = [
            'id', 'room_number', 'order_type', 'guest_name',
            'status', 'total_amount', 'created_at', 'items', 'logs'
        ]


class TaskSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.name', read_only=True)

    class Meta:
        model = Task
        fields = ['id', 'title', 'description', 'status', 'created_at', 'staff_name']


class ShiftTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftTemplate
        fields = ['id', 'shift_name', 'start_time', 'end_time', 'color', 'is_active']


class ShiftSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Shift
        fields = ['id', 'staff_name', 'department_name', 'shift', 'date']


class AttendanceSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.name', read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'staff_name', 'date', 'check_in', 'check_out', 'status', 'overtime_hours']


class LeaveRequestSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.name', read_only=True)

    class Meta:
        model = LeaveRequest
        fields = ['id', 'staff_name', 'from_date', 'to_date', 'reason', 'status', 'applied_at']


class PayrollSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.name', read_only=True)

    class Meta:
        model = Payroll
        fields = [
            'id', 'staff_name', 'month', 'year', 'basic_salary',
            'overtime_amount', 'bonus', 'incentive', 'deductions',
            'net_salary', 'paid_status', 'paid_at'
        ]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'notif_type', 'title', 'body', 'is_read', 'created_at']


class HotelFullDetailsSerializer(serializers.ModelSerializer):
    subscription_plan = SubscriptionPlanSerializer(read_only=True)
    payments = PlanPaymentSerializer(many=True, read_only=True)
    modules = serializers.SerializerMethodField()
    departments = DepartmentSerializer(many=True, read_only=True)
    staffs = StaffSerializer(many=True, read_only=True)
    rooms = serializers.SerializerMethodField()
    bookings = serializers.SerializerMethodField()
    menu_categories = serializers.SerializerMethodField()
    tables = serializers.SerializerMethodField()
    table_reservations = serializers.SerializerMethodField()
    restaurant_orders = serializers.SerializerMethodField()
    folios = serializers.SerializerMethodField()
    inventory_items = serializers.SerializerMethodField()
    purchase_orders = serializers.SerializerMethodField()
    expenses = serializers.SerializerMethodField()
    assets = serializers.SerializerMethodField()
    laundry_orders = serializers.SerializerMethodField()
    shift_templates = serializers.SerializerMethodField()
    shifts = serializers.SerializerMethodField()
    attendance = serializers.SerializerMethodField()
    leave_requests = serializers.SerializerMethodField()
    payrolls = serializers.SerializerMethodField()
    trial_is_active = serializers.BooleanField(read_only=True)
    trial_has_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Hotel
        fields = [
            'id', 'hotel_name', 'email', 'owner_name', 'address', 'city',
            'property_type', 'image', 'logo', 'description', 'amenities',
            'is_approved', 'is_subscribed', 'is_setup_complete',
            'subscription_status', 'subscription_expiry',
            'trial_eligible', 'is_on_trial', 'trial_start', 'trial_end',
            'trial_is_active', 'trial_has_expired', 'created_at',
            'subscription_plan', 'payments', 'modules',
            'departments', 'staffs',
            'rooms', 'bookings',
            'menu_categories', 'tables', 'table_reservations', 'restaurant_orders',
            'folios',
            'inventory_items', 'purchase_orders', 'expenses', 'assets', 'laundry_orders',
            'shift_templates', 'shifts', 'attendance', 'leave_requests', 'payrolls',
        ]

    def get_modules(self, obj):
        return HotelModuleSerializer(
            HotelModule.objects.filter(hotel=obj).select_related('module'), many=True
        ).data

    def get_rooms(self, obj):
   
        tenant_rooms = self.context.get('tenant_rooms')
        if tenant_rooms is not None:
            return tenant_rooms

    
        return []
    def get_bookings(self, obj):
        return BookingSerializer(
            Booking.objects.filter(room__in=Room.objects.all())
            .select_related('guest', 'room', 'room_unit')
            .prefetch_related('payment'),
            many=True
        ).data

    def get_menu_categories(self, obj):
        return MenuCategorySerializer(
            MenuCategory.objects.prefetch_related('items').all(), many=True
        ).data

    def get_tables(self, obj):
        return TableSerializer(Table.objects.all(), many=True).data

    def get_table_reservations(self, obj):
        return TableReservationSerializer(TableReservation.objects.all(), many=True).data

    def get_restaurant_orders(self, obj):
        return RestaurantOrderSerializer(
            RestaurantOrder.objects.prefetch_related('items').all(), many=True
        ).data

    def get_folios(self, obj):
        return GuestFolioSerializer(
            GuestFolio.objects.filter(booking__in=Booking.objects.all())
            .prefetch_related('charges', 'payments')
            .select_related('invoice'),
            many=True
        ).data

    def get_inventory_items(self, obj):
        return InventoryItemSerializer(
            InventoryItem.objects.prefetch_related('adjustments').all(), many=True
        ).data

    def get_purchase_orders(self, obj):
        return PurchaseOrderSerializer(
            PurchaseOrder.objects.prefetch_related('items').all(), many=True
        ).data

    def get_expenses(self, obj):
        return ExpenseSerializer(Expense.objects.all(), many=True).data

    def get_assets(self, obj):
        return HotelAssetSerializer(
            HotelAsset.objects.prefetch_related('maintenance_logs').all(), many=True
        ).data

    def get_laundry_orders(self, obj):
        return LaundryOrderSerializer(
            LaundryOrder.objects.prefetch_related('items', 'logs').all(), many=True
        ).data

    def get_shift_templates(self, obj):
        return ShiftTemplateSerializer(
            ShiftTemplate.objects.filter(hotel=obj), many=True
        ).data

    def get_shifts(self, obj):
        return ShiftSerializer(
            Shift.objects.filter(hotel=obj).select_related('staff', 'department'), many=True
        ).data

    def get_attendance(self, obj):
        return AttendanceSerializer(
            Attendance.objects.filter(hotel=obj).select_related('staff'), many=True
        ).data

    def get_leave_requests(self, obj):
        staff_ids = obj.staffs.values_list('id', flat=True)
        return LeaveRequestSerializer(
            LeaveRequest.objects.filter(staff_id__in=staff_ids).select_related('staff'), many=True
        ).data

    def get_payrolls(self, obj):
        return PayrollSerializer(
            Payroll.objects.filter(hotel=obj).select_related('staff'), many=True
        ).data
from rest_framework import serializers
from .models import Hotel


class HotelSerializer(serializers.ModelSerializer):
    trial_is_active = serializers.ReadOnlyField()
    trial_has_expired = serializers.ReadOnlyField()
    subscription_plan_name = serializers.CharField(
        source='subscription_plan.name',
        read_only=True
    )

    class Meta:
        model = Hotel
        fields = [
            'id',
            'tenant',
            'schema_name',
            'hotel_name',
            'email',
            'owner_name',
            'address',
            'city',
            'property_type',
            'image',
            'description',
            'amenities',
            'is_approved',
            'is_subscribed',
            'is_setup_complete',
            'logo',
            'created_at',
            'subscription_plan',
            'subscription_plan_name',
            'subscription_status',
            'subscription_expiry',
            'trial_eligible',
            'is_on_trial',
            'trial_start',
            'trial_end',
            'trial_days',
            'trial_granted_by',
            'trial_is_active',
            'trial_has_expired',
        ]
        read_only_fields = [
            'created_at',
            'trial_is_active',
            'trial_has_expired',
        ]

class RolePermissionSerializer(serializers.ModelSerializer):
    role_name = serializers.CharField(source='role.name', read_only=True)
    permission_name = serializers.CharField(source='permission.name', read_only=True)

    class Meta:
        model = RolePermission
        fields = [
            'id',
            'role',
            'role_name',
            'permission',
            'permission_name',
        ]