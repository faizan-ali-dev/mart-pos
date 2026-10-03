from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import (
    Batch,
    GRN,
    GRNLine,
    PurchaseOrder,
    StockAdjustment,
    StockLevel,
    StockLocation,
)


@admin.register(StockLocation)
class StockLocationAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "location_type", "is_active")
    list_filter = ("tenant", "location_type", "is_active")
    search_fields = ("name",)


@admin.register(StockLevel)
class StockLevelAdmin(TenantScopedAdmin):
    tenant_lookup = "product__tenant"
    list_display = ("product", "location", "qty", "updated_at")
    list_filter = ("location",)
    search_fields = ("product__sku", "product__name")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(TenantScopedAdmin):
    list_display = ("id", "supplier", "tenant", "status", "expected_date", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("supplier__name",)


class GRNLineInline(admin.TabularInline):
    model = GRNLine
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(GRN)
class GRNAdmin(TenantScopedAdmin):
    list_display = (
        "id",
        "supplier",
        "tenant",
        "supplier_invoice_no",
        "location",
        "on_credit",
        "total_cost",
        "received_at",
    )
    list_filter = ("tenant", "on_credit", "location")
    search_fields = ("supplier__name", "supplier_invoice_no")
    inlines = [GRNLineInline]


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(TenantScopedAdmin):
    list_display = (
        "id",
        "product",
        "location",
        "adjustment_type",
        "qty_change",
        "approved_by",
        "created_at",
    )
    list_filter = ("tenant", "adjustment_type", "location")
    search_fields = ("product__sku", "product__name", "reason")


@admin.register(Batch)
class BatchAdmin(TenantScopedAdmin):
    list_display = ("product", "expiry_date", "qty", "tenant")
    list_filter = ("tenant",)
    search_fields = ("product__sku", "product__name")
