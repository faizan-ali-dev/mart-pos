from rest_framework import serializers

from .models import (
    Batch,
    GRN,
    GRNLine,
    PurchaseOrder,
    StockAdjustment,
    StockLevel,
    StockLocation,
)


class StockLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLocation
        fields = ("id", "tenant", "name", "location_type", "is_active")
        read_only_fields = ("id", "tenant")


class StockLevelSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)
    reorder_level = serializers.DecimalField(
        source="product.reorder_level", max_digits=12, decimal_places=3, read_only=True
    )

    class Meta:
        model = StockLevel
        fields = (
            "id",
            "tenant",
            "product",
            "product_sku",
            "product_name",
            "location",
            "location_name",
            "qty",
            "reorder_level",
            "updated_at",
        )
        read_only_fields = ("id", "tenant", "updated_at")


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "tenant",
            "supplier",
            "supplier_name",
            "status",
            "expected_date",
            "notes",
            "created_by",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_by", "created_at")


class GRNLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = GRNLine
        fields = (
            "id",
            "product",
            "product_sku",
            "product_name",
            "qty",
            "purchase_rate",
            "expiry_date",
            "line_total",
        )
        read_only_fields = ("id", "line_total")


class GRNCreateLineSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    purchase_rate = serializers.DecimalField(max_digits=12, decimal_places=2)
    expiry_date = serializers.DateField(required=False, allow_null=True)


class GRNCreateSerializer(serializers.Serializer):
    supplier = serializers.IntegerField()
    location = serializers.IntegerField(required=False, allow_null=True)
    supplier_invoice_no = serializers.CharField(required=False, allow_blank=True, default="")
    on_credit = serializers.BooleanField(default=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = GRNCreateLineSerializer(many=True)


class GRNSerializer(serializers.ModelSerializer):
    lines = GRNLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = GRN
        fields = (
            "id",
            "tenant",
            "supplier",
            "supplier_name",
            "supplier_invoice_no",
            "location",
            "location_name",
            "on_credit",
            "total_cost",
            "notes",
            "received_by",
            "received_at",
            "lines",
        )
        read_only_fields = ("id", "tenant", "total_cost", "received_by", "received_at")


class StockAdjustmentSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = StockAdjustment
        fields = (
            "id",
            "tenant",
            "product",
            "product_sku",
            "location",
            "adjustment_type",
            "qty_change",
            "reason",
            "approved_by",
            "created_by",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_by", "created_at")


class StockAdjustmentCreateSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    location = serializers.IntegerField()
    adjustment_type = serializers.ChoiceField(choices=StockAdjustment.TYPE_CHOICES)
    qty_change = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField()


class BatchSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Batch
        fields = (
            "id",
            "tenant",
            "product",
            "product_sku",
            "product_name",
            "expiry_date",
            "qty",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_at")
