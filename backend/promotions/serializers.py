from rest_framework import serializers

from .models import Promotion


class PromotionSerializer(serializers.ModelSerializer):
    buy_product_sku = serializers.CharField(source="buy_product.sku", read_only=True)
    get_product_sku = serializers.CharField(source="get_product.sku", read_only=True)

    class Meta:
        model = Promotion
        fields = (
            "id",
            "tenant",
            "name",
            "promo_type",
            "buy_product",
            "buy_product_sku",
            "buy_qty",
            "get_product",
            "get_product_sku",
            "get_qty",
            "discount_percent",
            "discount_amount",
            "min_bill_amount",
            "start_date",
            "end_date",
            "days_of_week",
            "time_start",
            "time_end",
            "is_active",
            "priority",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_at")

    def validate(self, attrs):
        promo_type = attrs.get("promo_type", getattr(self.instance, "promo_type", None))
        buy_product = attrs.get("buy_product", getattr(self.instance, "buy_product", None))
        get_product = attrs.get("get_product", getattr(self.instance, "get_product", None))
        request = self.context.get("request")
        tenant = request.user.tenant if request else None

        for field, product in (("buy_product", buy_product), ("get_product", get_product)):
            if product is not None and tenant is not None and product.tenant_id != tenant.id:
                raise serializers.ValidationError(
                    {field: "Product does not belong to this tenant."}
                )

        if promo_type == Promotion.TYPE_BOGO:
            if not buy_product or not get_product:
                raise serializers.ValidationError(
                    "BOGO needs both buy_product and get_product."
                )
        elif promo_type == Promotion.TYPE_BUNDLE:
            if not buy_product or not get_product:
                raise serializers.ValidationError(
                    "Bundle needs both buy_product and get_product."
                )
            if not attrs.get("discount_percent", getattr(self.instance, "discount_percent", None)):
                raise serializers.ValidationError(
                    {"discount_percent": "Bundle needs a discount percent."}
                )
        elif promo_type == Promotion.TYPE_PERCENT:
            if not attrs.get("discount_percent", getattr(self.instance, "discount_percent", None)):
                raise serializers.ValidationError(
                    {"discount_percent": "Percent promo needs a discount percent."}
                )
        elif promo_type == Promotion.TYPE_FLAT:
            if not attrs.get("discount_amount", getattr(self.instance, "discount_amount", None)):
                raise serializers.ValidationError(
                    {"discount_amount": "Flat promo needs a discount amount."}
                )

        days = attrs.get("days_of_week", getattr(self.instance, "days_of_week", []))
        if days and (not all(isinstance(d, int) and 0 <= d <= 6 for d in days)):
            raise serializers.ValidationError(
                {"days_of_week": "Weekdays must be integers 0 (Monday) to 6 (Sunday)."}
            )
        return attrs
