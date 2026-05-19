from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from .models import (
    ItemCategory, Vendor, InventoryItem, StockAdjustment,
    PurchaseOrder, PurchaseItem, ExpenseCategory, Expense,
    AssetCategory, HotelAsset, MaintenanceLog,
    LaundryService, LaundryOrder, LaundryOrderItem, LaundryStatusLog,
)
from .serializers import (
    ItemCategorySerializer, VendorSerializer, InventoryItemSerializer,
    StockAdjustmentSerializer, PurchaseOrderSerializer, PurchaseOrderCreateSerializer,
    ExpenseCategorySerializer, ExpenseSerializer,
    AssetCategorySerializer, HotelAssetSerializer, MaintenanceLogSerializer,
    LaundryServiceSerializer, LaundryOrderSerializer, LaundryOrderCreateSerializer,
    LaundryStatusLogSerializer,
)


class ItemCategoryListAPIView(APIView):
    def get(self, request):
        return Response(ItemCategorySerializer(ItemCategory.objects.all(), many=True).data)

    def post(self, request):
        s = ItemCategorySerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class ItemCategoryDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(ItemCategorySerializer(get_object_or_404(ItemCategory, pk=pk)).data)

    def put(self, request, pk):
        s = ItemCategorySerializer(get_object_or_404(ItemCategory, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(ItemCategory, pk=pk).delete()
        return Response({"success": True}, status=204)


class VendorListAPIView(APIView):
    def get(self, request):
        return Response(VendorSerializer(Vendor.objects.all(), many=True).data)

    def post(self, request):
        s = VendorSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class VendorDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(VendorSerializer(get_object_or_404(Vendor, pk=pk)).data)

    def put(self, request, pk):
        s = VendorSerializer(get_object_or_404(Vendor, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(Vendor, pk=pk).delete()
        return Response({"success": True}, status=204)


class InventoryItemListAPIView(APIView):
    def get(self, request):
        items = InventoryItem.objects.select_related("category", "vendor", "department").all()
        return Response(InventoryItemSerializer(items, many=True).data)

    def post(self, request):
        s = InventoryItemSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class InventoryItemDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(InventoryItemSerializer(get_object_or_404(InventoryItem, pk=pk)).data)

    def put(self, request, pk):
        s = InventoryItemSerializer(get_object_or_404(InventoryItem, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(InventoryItem, pk=pk).delete()
        return Response({"success": True}, status=204)


class InventoryByDepartmentAPIView(APIView):
    def get(self, request):
        dept_id = request.query_params.get("department_id")
        items   = InventoryItem.objects.filter(department_id=dept_id) if dept_id else InventoryItem.objects.all()
        return Response(InventoryItemSerializer(items, many=True).data)


class StockAdjustmentListAPIView(APIView):
    def get(self, request):
        return Response(StockAdjustmentSerializer(StockAdjustment.objects.select_related("item").all(), many=True).data)

    def post(self, request):
        s = StockAdjustmentSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class PurchaseOrderListAPIView(APIView):
    def get(self, request):
        pos = PurchaseOrder.objects.prefetch_related("items").select_related("vendor").all()
        return Response(PurchaseOrderSerializer(pos, many=True).data)

    def post(self, request):
        s = PurchaseOrderCreateSerializer(data=request.data)
        if s.is_valid():
            po = s.save()
            return Response(PurchaseOrderSerializer(po).data, status=201)
        return Response(s.errors, status=400)


class PurchaseOrderDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(PurchaseOrderSerializer(get_object_or_404(PurchaseOrder, pk=pk)).data)

    def put(self, request, pk):
        po     = get_object_or_404(PurchaseOrder, pk=pk)
        status = request.data.get("status")
        if status not in dict(PurchaseOrder.STATUS):
            return Response({"error": "Invalid status"}, status=400)
        po.status = status
        po.save()
        return Response(PurchaseOrderSerializer(po).data)


class PurchaseOrderItemsAPIView(APIView):
    def get(self, request, pk):
        po    = get_object_or_404(PurchaseOrder, pk=pk)
        items = po.items.select_related("item").all()
        from .serializers import PurchaseItemSerializer
        return Response(PurchaseItemSerializer(items, many=True).data)


class ExpenseCategoryListAPIView(APIView):
    def get(self, request):
        return Response(ExpenseCategorySerializer(ExpenseCategory.objects.all(), many=True).data)

    def post(self, request):
        s = ExpenseCategorySerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class ExpenseListAPIView(APIView):
    def get(self, request):
        expenses = Expense.objects.select_related("department", "expense_category").all()
        return Response(ExpenseSerializer(expenses, many=True).data)

    def post(self, request):
        s = ExpenseSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class ExpenseDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(ExpenseSerializer(get_object_or_404(Expense, pk=pk)).data)

    def delete(self, request, pk):
        get_object_or_404(Expense, pk=pk).delete()
        return Response({"success": True}, status=204)


class ExpenseSummaryAPIView(APIView):
    def get(self, request):
        summary = (
            Expense.objects
            .values("expense_category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        return Response(list(summary))


class AssetCategoryListAPIView(APIView):
    def get(self, request):
        return Response(AssetCategorySerializer(AssetCategory.objects.all(), many=True).data)

    def post(self, request):
        s = AssetCategorySerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class HotelAssetListAPIView(APIView):
    def get(self, request):
        assets = HotelAsset.objects.select_related("asset_category", "vendor", "department", "room_unit", "room").all()
        return Response(HotelAssetSerializer(assets, many=True).data)

    def post(self, request):
        s = HotelAssetSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class HotelAssetDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(HotelAssetSerializer(get_object_or_404(HotelAsset, pk=pk)).data)

    def put(self, request, pk):
        s = HotelAssetSerializer(get_object_or_404(HotelAsset, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(HotelAsset, pk=pk).delete()
        return Response({"success": True}, status=204)


class MaintenanceLogListAPIView(APIView):
    def get(self, request):
        logs = MaintenanceLog.objects.select_related("asset", "department", "recorded_by").all()
        return Response(MaintenanceLogSerializer(logs, many=True).data)

    def post(self, request):
        s = MaintenanceLogSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class MaintenanceLogDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(MaintenanceLogSerializer(get_object_or_404(MaintenanceLog, pk=pk)).data)

    def put(self, request, pk):
        s = MaintenanceLogSerializer(get_object_or_404(MaintenanceLog, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(MaintenanceLog, pk=pk).delete()
        return Response({"success": True}, status=204)


class LaundryServiceListAPIView(APIView):
    def get(self, request):
        return Response(LaundryServiceSerializer(LaundryService.objects.all(), many=True).data)

    def post(self, request):
        s = LaundryServiceSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class LaundryOrderListAPIView(APIView):
    def get(self, request):
        orders = LaundryOrder.objects.prefetch_related("items", "logs").all()
        return Response(LaundryOrderSerializer(orders, many=True).data)

    def post(self, request):
        s = LaundryOrderCreateSerializer(data=request.data)
        if s.is_valid():
            order = s.save()
            return Response(LaundryOrderSerializer(order).data, status=201)
        return Response(s.errors, status=400)


class LaundryOrderDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(LaundryOrderSerializer(get_object_or_404(LaundryOrder, pk=pk)).data)

    def put(self, request, pk):
        order  = get_object_or_404(LaundryOrder, pk=pk)
        status = request.data.get("status")
        note   = request.data.get("note", "")
        staff  = request.data.get("updated_by")
        if status not in dict(LaundryOrder.STATUS):
            return Response({"error": "Invalid status"}, status=400)
        order.status = status
        order.save()
        LaundryStatusLog.objects.create(order=order, status=status, note=note, updated_by_id=staff)
        return Response(LaundryOrderSerializer(order).data)