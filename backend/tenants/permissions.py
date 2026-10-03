from rest_framework import permissions

from .models import User


class RolePermission(permissions.BasePermission):
    """
    Gate unsafe HTTP methods by user role.

    Set ``allowed_roles`` on the view, e.g. ``allowed_roles = ("owner", "manager")``.
    Safe methods are allowed for any authenticated user (tenant scoping still applies).
    Superusers bypass all checks.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        if request.method in permissions.SAFE_METHODS:
            return True
        allowed = getattr(view, "allowed_roles", None)
        if allowed is None:
            return True
        return user.role in allowed


class TenantScopedMixin:
    """
    Restrict querysets to the requester's tenant and auto-assign tenant on create.
    Superusers (tenant=None) see everything.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs
        tenant = getattr(user, "tenant", None)
        if tenant is None:
            return qs.none()
        return qs.filter(tenant=tenant)

    def perform_create(self, serializer):
        model = serializer.Meta.model
        if hasattr(model, "tenant") and "tenant" not in serializer.validated_data:
            serializer.save(tenant=self.request.user.tenant)
        else:
            serializer.save()


class UserManagementPermission(permissions.BasePermission):
    """
    Rules for /api/tenants/users/:
      - owner:   manage everyone in their own tenant
      - manager: manage cashiers only (cannot create/promote managers or owners)
      - cashier: no access at all (403)
    Superusers bypass all checks.
    """

    message = "You do not have permission to manage users."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return user.role in (User.ROLE_OWNER, User.ROLE_MANAGER)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if getattr(user, "is_superuser", False):
            return True
        if obj.tenant_id != user.tenant_id:
            return False
        if user.role == User.ROLE_OWNER:
            return True
        # Manager: cashiers only.
        return obj.role == User.ROLE_CASHIER
