from rest_framework import serializers
from .models import (
    ItemCategory, Vendor, InventoryItem, StockAdjustment,
    PurchaseOrder, PurchaseItem, ExpenseCategory, Expense,
    AssetCategory, HotelAsset, MaintenanceLog,
    LaundryService, LaundryOrder, LaundryOrderItem, LaundryStatusLog,
)


class ItemCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = ItemCategory
        fields = ["id", "name"]


class VendorSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Vendor
        fields = ["id", "name", "contact_person", "phone", "email", "address", "created_at"]


class InventoryItemSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.SerializerMethodField()
    stock_value  = serializers.SerializerMethodField()

    class Meta:
        model  = InventoryItem
        fields = [
            "id", "category", "department", "name", "unit",
            "current_stock", "minimum_stock", "cost_per_unit",
            "vendor", "created_at", "is_low_stock", "stock_value",
        ]

    def get_is_low_stock(self, obj):
        return obj.is_low_stock

    def get_stock_value(self, obj):
        return float(obj.stock_value)


class StockAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StockAdjustment
        fields = ["id", "item", "adjustment_type", "quantity", "note", "adjusted_by", "created_at"]

    def create(self, validated_data):
        adjustment = super().create(validated_data)
        item = adjustment.item
        if adjustment.adjustment_type == "in":
            item.current_stock += adjustment.quantity
        elif adjustment.adjustment_type == "out":
            item.current_stock -= adjustment.quantity
        elif adjustment.adjustment_type == "adjust":
            item.current_stock = adjustment.quantity
        item.save()
        return adjustment


class PurchaseItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model  = PurchaseItem
        fields = ["id", "item", "quantity", "unit_price", "subtotal"]

    def get_subtotal(self, obj):
        return float(obj.subtotal)


class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)

    class Meta:
        model  = PurchaseOrder
        fields = [
            "id", "vendor", "department", "total_amount", "status",
            "note", "ordered_by", "approved_by", "ordered_at", "received_at", "items",
        ]


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True)

    class Meta:
        model  = PurchaseOrder
        fields = [
            "id", "vendor", "department", "status", "note",
            "ordered_by", "approved_by", "items",
        ]

    def create(self, validated_data):
        items_data   = validated_data.pop("items", [])
        total_amount = sum(i["quantity"] * i["unit_price"] for i in items_data)
        po = PurchaseOrder.objects.create(total_amount=total_amount, **validated_data)
        for i in items_data:
            PurchaseItem.objects.create(purchase_order=po, **i)
        return po


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = ExpenseCategory
        fields = ["id", "name", "budget"]


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Expense
        fields = [
            "id", "department", "expense_category", "purchase_order",
            "inventory_item", "source", "amount", "description",
            "expense_date", "recorded_by", "created_at", "maintenance_log",
        ]


class AssetCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = AssetCategory
        fields = ["id", "name"]


class HotelAssetSerializer(serializers.ModelSerializer):
    location_display   = serializers.SerializerMethodField()
    is_warranty_active = serializers.SerializerMethodField()
    maintenance_due    = serializers.SerializerMethodField()

    class Meta:
        model  = HotelAsset
        fields = [
            "id", "name", "asset_category", "serial_number",
            "room_unit", "room", "area", "department", "status",
            "purchase_date", "purchase_cost", "vendor",
            "warranty_end", "next_maintenance", "assigned_to",
            "notes", "created_at",
            "location_display", "is_warranty_active", "maintenance_due",
        ]

    def get_location_display(self, obj):
        return obj.location_display

    def get_is_warranty_active(self, obj):
        return obj.is_warranty_active

    def get_maintenance_due(self, obj):
        return obj.maintenance_due


class MaintenanceLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MaintenanceLog
        fields = [
            "id", "asset", "department", "custom_asset", "location",
            "maintenance_type", "priority", "status", "description",
            "performed_by", "performed_at", "duration",
            "labour_cost", "parts_cost", "cost",
            "next_due", "parts_replaced", "notes",
            "recorded_by", "created_at",
        ]


class LaundryServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LaundryService
        fields = ["id", "name", "service_type", "price_per_unit", "turnaround_hours"]


class LaundryOrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model  = LaundryOrderItem
        fields = ["id", "service", "item_name", "quantity", "unit_price", "subtotal"]

    def get_subtotal(self, obj):
        return float(obj.subtotal)


class LaundryStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LaundryStatusLog
        fields = ["id", "status", "note", "updated_by", "created_at"]


class LaundryOrderSerializer(serializers.ModelSerializer):
    items  = LaundryOrderItemSerializer(many=True, read_only=True)
    logs   = LaundryStatusLogSerializer(many=True, read_only=True)

    class Meta:
        model  = LaundryOrder
        fields = [
            "id", "room_number", "booking", "order_type", "guest_name",
            "status", "total_amount", "created_at", "updated_at",
            "delivered_by", "items", "logs",
        ]


class LaundryOrderCreateSerializer(serializers.ModelSerializer):
    items = LaundryOrderItemSerializer(many=True)

    class Meta:
        model  = LaundryOrder
        fields = [
            "id", "room_number", "booking", "order_type",
            "guest_name", "delivered_by", "items",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        order      = LaundryOrder.objects.create(**validated_data)
        total      = 0
        for i in items_data:
            item = LaundryOrderItem.objects.create(order=order, **i)
            total += float(item.subtotal)
        order.total_amount = total
        order.save()
        return order