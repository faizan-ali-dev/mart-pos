from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import Bill, BillLine, ParkedBill, Payment, Return, ReturnLine, Shift


@admin.register(Shift)
class ShiftAdmin(TenantScopedAdmin):
    list_display = (
        "id",
        "tenant",
        "opened_by",
        "status",
        "opening_cash",
        "expected_cash",
        "counted_cash",
        "difference",
        "opened_at",
    )
    list_filter = ("tenant", "status")
    search_fields = ("opened_by__username",)
    readonly_fields = ("expected_cash", "difference")


class BillLineInline(admin.TabularInline):
    model = BillLine
    extra = 0
    can_delete = False
    readonly_fields = ("product", "qty", "rate", "discount_percent", "discount_amount",
                       "slab_discount_percent", "line_total")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = ("mode", "amount", "reference", "created_at")


@admin.register(Bill)
class BillAdmin(TenantScopedAdmin):
    list_display = (
        "bill_no",
        "tenant",
        "sale_type",
        "cashier",
        "customer",
        "grand_total",
        "created_at",
    )
    list_filter = ("tenant", "sale_type")
    search_fields = ("bill_no", "cashier__username", "customer__name")
    inlines = [BillLineInline, PaymentInline]
    readonly_fields = (
        "bill_no",
        "tenant",
        "sale_type",
        "shift",
        "cashier",
        "customer",
        "subtotal",
        "bill_discount",
        "bill_discount_reason",
        "tax_total",
        "grand_total",
        "tendered",
        "change_due",
        "notes",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ReturnLineInline(admin.TabularInline):
    model = ReturnLine
    extra = 0
    can_delete = False


@admin.register(Return)
class ReturnAdmin(TenantScopedAdmin):
    list_display = ("id", "bill", "tenant", "refund_mode", "total_refund", "created_at")
    list_filter = ("tenant", "refund_mode")
    search_fields = ("bill__bill_no", "reason")
    inlines = [ReturnLineInline]


@admin.register(ParkedBill)
class ParkedBillAdmin(TenantScopedAdmin):
    list_display = ("token", "tenant", "status", "created_by", "created_at")
    list_filter = ("tenant", "status")
    search_fields = ("token",)
