from rest_framework import serializers

from .models import Expense, ExpenseCategory


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ("id", "tenant", "name", "is_active")
        read_only_fields = ("id", "tenant")

    def validate(self, attrs):
        # DRF doesn't auto-validate UniqueConstraint, so check explicitly -> 400.
        request = self.context.get("request")
        name = attrs.get("name", getattr(self.instance, "name", None))
        if request is not None and name:
            qs = ExpenseCategory.objects.filter(
                tenant=request.user.tenant, name=name
            )
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"name": "This category already exists."}
                )
        return attrs


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True
    )

    class Meta:
        model = Expense
        fields = (
            "id",
            "tenant",
            "date",
            "category",
            "category_name",
            "amount",
            "payment_mode",
            "notes",
            "created_by",
            "created_by_username",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_by", "created_at")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Expense amount must be positive.")
        return value

    def validate_category(self, value):
        request = self.context.get("request")
        if request and value.tenant_id != request.user.tenant_id:
            raise serializers.ValidationError("Category does not belong to this tenant.")
        return value
