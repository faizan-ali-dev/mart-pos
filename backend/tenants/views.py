from django.contrib.auth import authenticate
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Store, Tenant, TenantSettings, User
from .permissions import RolePermission, TenantScopedMixin, UserManagementPermission
from .serializers import (
    StoreSerializer,
    TenantSerializer,
    TenantSettingsSerializer,
    UserSerializer,
)


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": user.role,
        "is_superuser": user.is_superuser,
        "tenant": user.tenant_id,
        "tenant_name": user.tenant.name if user.tenant else None,
        "store": user.store_id,
    }


class LoginView(APIView):
    """POST {username, password} -> {token, user}. Deactivated users are rejected."""

    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            # Covers wrong credentials AND is_active=False (Django rejects inactive).
            return Response(
                {"detail": "Invalid credentials or inactive account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": _user_payload(user)})


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_user_payload(request.user))


class TenantViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Tenant.objects.all().order_by("name")
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]


class StoreViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Store.objects.select_related("tenant").all().order_by("name")
    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")


class UserViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """
    Full user management for a tenant.

    GET    /api/tenants/users/            list users in my tenant
    POST   /api/tenants/users/            create user (owner: any role; manager: cashier only)
    PATCH  /api/tenants/users/{id}/       update role / is_active / name
    POST   /api/tenants/users/{id}/reset-password/  {password}

    Cashiers get 403 on every endpoint. DELETE is disabled — deactivate instead.
    """

    queryset = User.objects.select_related("tenant", "store").all().order_by("username")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, UserManagementPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser and user.role == User.ROLE_MANAGER:
            # Managers only ever see the cashiers they can manage.
            qs = qs.filter(role=User.ROLE_CASHIER)
        return qs

    def perform_create(self, serializer):
        # Tenant assignment is forced inside UserSerializer.create; never from input.
        serializer.save()

    def _check_target_role_allowed(self, target_role: str):
        requester = self.request.user
        if requester.is_superuser:
            return
        if requester.role == User.ROLE_MANAGER and target_role != User.ROLE_CASHIER:
            raise PermissionDenied("Managers can only create or manage cashier accounts.")

    def create(self, request, *args, **kwargs):
        self._check_target_role_allowed(request.data.get("role", User.ROLE_CASHIER))
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()  # enforces object-level permission (403/404)
        if instance.is_superuser and not request.user.is_superuser:
            raise PermissionDenied("Only a superuser can modify this account.")
        if instance.pk == request.user.pk and (
            "role" in request.data or "is_active" in request.data
        ):
            raise PermissionDenied("You cannot change your own role or deactivate yourself.")
        if "role" in request.data:
            self._check_target_role_allowed(request.data["role"])
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        target = self.get_object()  # owner: anyone in tenant; manager: cashiers only
        if target.is_superuser and not request.user.is_superuser:
            raise PermissionDenied("Only a superuser can modify this account.")
        new_password = (request.data.get("password") or "").strip()
        if len(new_password) < 4:
            return Response(
                {"password": "A new password of at least 4 characters is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target.set_password(new_password)
        target.save(update_fields=["password"])
        return Response({"detail": f"Password reset for user '{target.username}'."})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    """Delete the current token (log out this device)."""
    request.user.auth_token.delete()
    return Response({"detail": "Logged out."})


class TenantSettingsView(APIView):
    """GET/PUT /api/tenants/settings/ — per-tenant WhatsApp + print config.

    Owner: read + write. Manager: read only. Cashier: 403. Superusers have no
    tenant scope and manage settings in Django admin instead.
    """

    permission_classes = [IsAuthenticated]

    def _settings(self, request, write=False):
        user = request.user
        if getattr(user, "is_superuser", False) or user.tenant_id is None:
            return None
        if user.role == User.ROLE_CASHIER:
            raise PermissionDenied("Cashiers cannot access tenant settings.")
        if write and user.role != User.ROLE_OWNER:
            raise PermissionDenied("Only the owner can change tenant settings.")
        settings, _ = TenantSettings.objects.get_or_create(tenant=user.tenant)
        return settings

    def get(self, request):
        settings = self._settings(request)
        if settings is None:
            return Response(
                {"detail": "Superusers manage tenant settings in Django admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(TenantSettingsSerializer(settings).data)

    def put(self, request):
        settings = self._settings(request, write=True)
        if settings is None:
            return Response(
                {"detail": "Superusers manage tenant settings in Django admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ser = TenantSettingsSerializer(settings, data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(TenantSettingsSerializer(settings).data)
