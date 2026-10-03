from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import Promotion


@admin.register(Promotion)
class PromotionAdmin(TenantScopedAdmin):
    list_display = (
        "name",
        "tenant",
        "promo_type",
        "is_active",
        "priority",
        "start_date",
        "end_date",
    )
    list_filter = ("tenant", "promo_type", "is_active")
    search_fields = ("name",)
