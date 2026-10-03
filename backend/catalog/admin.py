from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import Brand, Category, PriceSlab, Product, ProductBarcode


@admin.register(Category)
class CategoryAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "name_urdu", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "name_urdu")


@admin.register(Brand)
class BrandAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(TenantScopedAdmin):
    list_display = (
        "sku",
        "name",
        "tenant",
        "category",
        "brand",
        "unit",
        "purchase_price",
        "retail_price",
        "reorder_level",
        "track_expiry",
        "is_active",
    )
    list_filter = ("tenant", "category", "brand", "unit", "track_expiry", "is_active")
    search_fields = ("sku", "barcode", "name", "name_urdu")


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(TenantScopedAdmin):
    list_display = ("barcode", "product", "tenant")
    list_filter = ("tenant",)
    search_fields = ("barcode", "product__sku", "product__name")


@admin.register(PriceSlab)
class PriceSlabAdmin(TenantScopedAdmin):
    list_display = ("product", "min_qty", "discount_percent", "tenant")
    list_filter = ("tenant",)
    search_fields = ("product__sku", "product__name")
