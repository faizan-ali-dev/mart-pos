from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Store, Tenant, User


class TenantScopedAdmin(admin.ModelAdmin):
    """
    Hide other tenants' rows from non-superuser staff.
    Set ``tenant_lookup`` when the model has no direct ``tenant`` FK,
    e.g. ``tenant_lookup = "bill__tenant"``.
    """

    tenant_lookup = "tenant"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = getattr(request.user, "tenant", None)
        if tenant is None:
            return qs.none()
        return qs.filter(**{self.tenant_lookup: tenant})


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "phone", "block_khata_over_limit", "created_at")
    search_fields = ("name", "code")
    readonly_fields = ("bill_seq",)


@admin.register(Store)
class StoreAdmin(TenantScopedAdmin):
    list_display = ("name", "tenant", "phone", "is_active")
    list_filter = ("tenant", "is_active")
    search_fields = ("name",)


@admin.register(User)
class UserAdmin(TenantScopedAdmin, BaseUserAdmin):
    """Full user management with standard Django password-change support."""

    list_display = ("username", "tenant", "role", "store", "is_active", "is_staff")
    list_filter = ("tenant", "role", "is_active", "is_staff")
    search_fields = ("username", "first_name", "last_name", "phone", "email")

    fieldsets = BaseUserAdmin.fieldsets + (
        ("POS", {"fields": ("tenant", "store", "role", "phone")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("POS", {"fields": ("tenant", "store", "role", "phone")}),
    )

    def get_queryset(self, request):
        # User has a direct tenant FK, so the default tenant_lookup works.
        return super().get_queryset(request)
