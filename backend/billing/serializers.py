from rest_framework import serializers

from .models import Bill, BillLine, ParkedBill, Payment, Return, ReturnLine, Shift


class ShiftSerializer(serializers.ModelSerializer):
    opened_by_username = serializers.CharField(source="opened_by.username", read_only=True)

    class Meta:
        model = Shift
        fields = (
            "id",
            "tenant",
            "store",
            "opened_by",
            "opened_by_username",
            "opened_at",
            "closed_at",
            "opening_cash",
            "expected_cash",
            "counted_cash",
            "difference",
            "status",
            "notes",
        )
        read_only_fields = (
            "id",
            "tenant",
            "opened_by",
            "opened_at",
            "closed_at",
            "expected_cash",
            "counted_cash",
            "difference",
            "status",
        )


class BillLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    applied_rate = serializers.DecimalField(
        source="rate", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = BillLine
        fields = (
            "id",
            "product",
            "product_sku",
            "product_name",
            "qty",
            "rate",
            "applied_rate",
            "discount_percent",
            "discount_amount",
            "slab_discount_percent",
            "line_total",
        )


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id", "mode", "amount", "reference", "created_at")


class BillSerializer(serializers.ModelSerializer):
    lines = BillLineSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    cashier_username = serializers.CharField(source="cashier.username", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = Bill
        fields = (
            "id",
            "bill_no",
            "tenant",
            "shift",
            "cashier",
            "cashier_username",
            "customer",
            "customer_name",
            "sale_type",
            "subtotal",
            "bill_discount",
            "bill_discount_reason",
            "tax_total",
            "grand_total",
            "tendered",
            "change_due",
            "notes",
            "created_at",
            "lines",
            "payments",
        )


class BillCreateLineSerializer(serializers.Serializer):
    product = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0
    )
    discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0
    )


class BillCreatePaymentSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=Payment.MODE_CHOICES)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True, default="")


class BillCreateSerializer(serializers.Serializer):
    lines = BillCreateLineSerializer(many=True)
    payments = BillCreatePaymentSerializer(many=True)
    bill_discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, default=0
    )
    bill_discount_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=0
    )
    bill_discount_reason = serializers.CharField(required=False, allow_blank=True, default="")
    customer = serializers.IntegerField(required=False, allow_null=True)
    shift = serializers.IntegerField(required=False, allow_null=True)
    sale_type = serializers.ChoiceField(
        choices=Bill.SALE_CHOICES, required=False, allow_null=True
    )
    tendered = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class ParkedBillSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParkedBill
        fields = (
            "id",
            "tenant",
            "token",
            "payload",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "tenant", "token", "created_by", "created_at", "updated_at")


class ReturnLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReturnLine
        fields = ("id", "bill_line", "product", "qty", "rate", "line_total")


class ReturnSerializer(serializers.ModelSerializer):
    lines = ReturnLineSerializer(many=True, read_only=True)
    bill_no = serializers.CharField(source="bill.bill_no", read_only=True)

    class Meta:
        model = Return
        fields = (
            "id",
            "tenant",
            "bill",
            "bill_no",
            "reason",
            "refund_mode",
            "total_refund",
            "created_by",
            "created_at",
            "lines",
        )
        read_only_fields = ("id", "tenant", "total_refund", "created_by", "created_at")


class ReturnCreateLineSerializer(serializers.Serializer):
    bill_line = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)


class ReturnCreateSerializer(serializers.Serializer):
    bill = serializers.IntegerField()
    lines = ReturnCreateLineSerializer(many=True)
    reason = serializers.CharField()
    refund_mode = serializers.ChoiceField(choices=Return.REFUND_CHOICES)


class ShiftCloseSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
