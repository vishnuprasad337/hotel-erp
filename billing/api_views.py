from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import GuestFolio, FolioCharge, Invoice, BillingPayment
from .serializers import (
    GuestFolioSerializer, FolioChargeSerializer,
    InvoiceSerializer, BillingPaymentSerializer,
)


class GuestFolioListAPIView(APIView):
    def get(self, request):
        folios = GuestFolio.objects.prefetch_related("charges", "payments").all()
        return Response(GuestFolioSerializer(folios, many=True).data)

    def post(self, request):
        s = GuestFolioSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class GuestFolioDetailAPIView(APIView):
    def get(self, request, pk):
        folio = get_object_or_404(
            GuestFolio.objects.prefetch_related("charges", "payments"), pk=pk
        )
        return Response(GuestFolioSerializer(folio).data)

    def put(self, request, pk):
        folio = get_object_or_404(GuestFolio, pk=pk)
        s = GuestFolioSerializer(folio, data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


class FolioChargeListAPIView(APIView):
    def get(self, request, folio_id):
        charges = FolioCharge.objects.filter(folio_id=folio_id).order_by("date")
        return Response(FolioChargeSerializer(charges, many=True).data)

    def post(self, request, folio_id):
        data = request.data.copy()
        data["folio"] = folio_id
        s = FolioChargeSerializer(data=data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class FolioChargeDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(FolioChargeSerializer(get_object_or_404(FolioCharge, pk=pk)).data)

    def put(self, request, pk):
        s = FolioChargeSerializer(get_object_or_404(FolioCharge, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(FolioCharge, pk=pk).delete()
        return Response({"success": True}, status=204)


class InvoiceListAPIView(APIView):
    def get(self, request):
        return Response(InvoiceSerializer(Invoice.objects.select_related("folio").all(), many=True).data)

    def post(self, request):
        s = InvoiceSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class InvoiceDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(InvoiceSerializer(get_object_or_404(Invoice, pk=pk)).data)

    def put(self, request, pk):
        s = InvoiceSerializer(get_object_or_404(Invoice, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)


class BillingPaymentListAPIView(APIView):
    def get(self, request):
        payments = BillingPayment.objects.select_related("folio", "order", "received_by").all()
        return Response(BillingPaymentSerializer(payments, many=True).data)

    def post(self, request):
        s = BillingPaymentSerializer(data=request.data)
        if s.is_valid():
            s.save()
            return Response(s.data, status=201)
        return Response(s.errors, status=400)


class BillingPaymentDetailAPIView(APIView):
    def get(self, request, pk):
        return Response(BillingPaymentSerializer(get_object_or_404(BillingPayment, pk=pk)).data)

    def put(self, request, pk):
        s = BillingPaymentSerializer(get_object_or_404(BillingPayment, pk=pk), data=request.data, partial=True)
        if s.is_valid():
            s.save()
            return Response(s.data)
        return Response(s.errors, status=400)

    def delete(self, request, pk):
        get_object_or_404(BillingPayment, pk=pk).delete()
        return Response({"success": True}, status=204)


class FolioByBookingAPIView(APIView):
    def get(self, request, booking_id):
        folio = get_object_or_404(
            GuestFolio.objects.prefetch_related("charges", "payments"),
            booking_id=booking_id
        )
        return Response(GuestFolioSerializer(folio).data)