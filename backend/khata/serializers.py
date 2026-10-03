from rest_framework import serializers

from .models import Customer, KhataPayment, LedgerEntry, Supplier


class CustomerSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "tenant",
            "name",
            "phone",
            "address",
            "cnic",
            "customer_type",
            "wholesale_discount_percent",
            "credit_limit",
            "whatsapp_opt_in",
            "is_active",
            "notes",
            "balance",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["balance"] = str(instance.balance)
        return data


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = (
            "id",
            "tenant",
            "name",
            "phone",
            "address",
            "cnic",
            "is_active",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_at")

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["balance"] = str(instance.balance)
        return data


class LedgerEntrySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = (
            "id",
            "tenant",
            "customer",
            "customer_name",
            "supplier",
            "supplier_name",
            "entry_type",
            "bill",
            "amount",
            "balance_after",
            "allocated_amount",
            "due_date",
            "notes",
            "created_by",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_at")


class KhataPaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)

    class Meta:
        model = KhataPayment
        fields = (
            "id",
            "tenant",
            "customer",
            "customer_name",
            "supplier",
            "supplier_name",
            "amount",
            "mode",
            "reference",
            "allocation",
            "created_by",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "allocation", "created_by", "created_at")


class KhataPaymentCreateSerializer(serializers.Serializer):
    customer = serializers.IntegerField(required=False, allow_null=True)
    supplier = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    mode = serializers.ChoiceField(choices=KhataPayment.MODE_CHOICES, default="cash")
    reference = serializers.CharField(required=False, allow_blank=True, default="")
