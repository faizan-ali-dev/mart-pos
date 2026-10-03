from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import Customer, KhataPayment, LedgerEntry, Supplier


@admin.register(Customer)
class CustomerAdmin(TenantScopedAdmin):
    list_display = (
        "name",
        "phone",
        "tenant",
        "customer_type",
        "credit_limit",
        "is_active",
        "whatsapp_opt_in",
    )
    list_filter = ("tenant", "customer_type", "is_active")
    search_fields = ("name", "phone", "cnic")


@admin.register(Supplier)
class SupplierAdmin(TenantScopedAdmin):
    list_display = ("name", "phone", "tenant", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name", "phone")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(TenantScopedAdmin):
    list_display = (
        "id",
        "entry_type",
        "customer",
        "supplier",
        "amount",
        "balance_after",
        "bill",
        "created_at",
    )
    list_filter = ("tenant", "entry_type")
    search_fields = ("customer__name", "supplier__name", "notes")
    readonly_fields = ("balance_after", "allocated_amount")


@admin.register(KhataPayment)
class KhataPaymentAdmin(TenantScopedAdmin):
    list_display = ("id", "customer", "supplier", "amount", "mode", "created_at")
    list_filter = ("tenant", "mode")
    search_fields = ("customer__name", "supplier__name", "reference")
