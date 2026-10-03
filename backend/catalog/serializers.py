from rest_framework import serializers

from .models import Brand, Category, PriceSlab, Product, ProductBarcode


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("id", "tenant", "name", "name_urdu", "is_active")
        read_only_fields = ("id", "tenant")


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "tenant", "name", "is_active")
        read_only_fields = ("id", "tenant")


class ProductBarcodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBarcode
        fields = ("id", "tenant", "product", "barcode")
        read_only_fields = ("id", "tenant")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    stock_qty = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True, required=False
    )

    class Meta:
        model = Product
        fields = (
            "id",
            "tenant",
            "sku",
            "barcode",
            "name",
            "name_urdu",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "unit",
            "purchase_price",
            "retail_price",
            "wholesale_price",
            "tax_percent",
            "reorder_level",
            "track_expiry",
            "is_active",
            "stock_qty",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "tenant", "created_at", "updated_at")
        extra_kwargs = {
            "sku": {"required": False, "allow_blank": True},
            "barcode": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        # Blank SKU is allowed (auto-generated); normalise "" -> None handling in save().
        if attrs.get("sku") == "":
            attrs.pop("sku")
        return attrs


class PriceSlabSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PriceSlab
        fields = (
            "id",
            "tenant",
            "product",
            "product_sku",
            "product_name",
            "min_qty",
            "discount_percent",
        )
        read_only_fields = ("id", "tenant")

    def validate_product(self, value):
        user = self.context["request"].user
        if not user.is_superuser and value.tenant_id != user.tenant_id:
            raise serializers.ValidationError("Product does not belong to your tenant.")
        return value

    def validate_min_qty(self, value):
        if value <= 0:
            raise serializers.ValidationError("min_qty must be positive.")
        return value

    def validate(self, attrs):
        # Friendly 400 for the (tenant, product, min_qty) unique constraint
        # (DRF doesn't auto-generate validators for Meta.constraints).
        user = self.context["request"].user
        tenant = user.tenant if not user.is_superuser else attrs.get("tenant")
        product = attrs.get("product") or (
            self.instance.product if self.instance else None
        )
        min_qty = attrs.get("min_qty") or (
            self.instance.min_qty if self.instance else None
        )
        if tenant and product is not None and min_qty is not None:
            qs = PriceSlab.objects.filter(
                tenant=tenant, product=product, min_qty=min_qty
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A slab for this product at this quantity already exists."
                )
        return attrs
