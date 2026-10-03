from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(TenantScopedAdmin):
    list_display = (
        "date",
        "category",
        "amount",
        "payment_mode",
        "tenant",
        "created_by",
        "created_at",
    )
    list_filter = ("tenant", "category", "payment_mode", "date")
    search_fields = ("notes",)
    date_hierarchy = "date"
