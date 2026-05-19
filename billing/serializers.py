from rest_framework import serializers
from .models import GuestFolio, FolioCharge, Invoice, BillingPayment


class FolioChargeSerializer(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()

    class Meta:
        model  = FolioCharge
        fields = [
            "id", "folio", "charge_type", "description",
            "amount", "tax_amount", "date", "added_by", "total",
        ]

    def get_total(self, obj):
        return float(obj.total)


class BillingPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = BillingPayment
        fields = [
            "id", "folio", "order", "amount", "tax_amount", "total_amount",
            "method", "payment_status", "reference_number", "note",
            "received_at", "paid_at", "received_by",
        ]

    def validate(self, data):
        if not data.get("folio") and not data.get("order"):
            raise serializers.ValidationError("Payment must be linked to either a folio or an order.")
        if data.get("folio") and data.get("order"):
            raise serializers.ValidationError("Payment cannot be linked to both a folio and an order.")
        return data


class GuestFolioSerializer(serializers.ModelSerializer):
    charges       = FolioChargeSerializer(many=True, read_only=True)
    payments      = BillingPaymentSerializer(many=True, read_only=True)
    total_charges = serializers.SerializerMethodField()
    total_paid    = serializers.SerializerMethodField()
    balance_due   = serializers.SerializerMethodField()
    is_settled    = serializers.SerializerMethodField()

    class Meta:
        model  = GuestFolio
        fields = [
            "id", "booking", "status", "notes", "created_at", "updated_at",
            "charges", "payments",
            "total_charges", "total_paid", "balance_due", "is_settled",
        ]

    def get_total_charges(self, obj):
        return float(obj.total_charges)

    def get_total_paid(self, obj):
        return float(obj.total_paid)

    def get_balance_due(self, obj):
        return float(obj.balance_due)

    def get_is_settled(self, obj):
        return obj.is_settled


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Invoice
        fields = [
            "id", "invoice_number", "folio", "subtotal", "tax_total",
            "discount", "grand_total", "status", "generated_by",
            "generated_at", "notes",
        ]
        read_only_fields = ["invoice_number", "generated_at"]