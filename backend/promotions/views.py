from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from tenants.permissions import RolePermission, TenantScopedMixin

from .models import Promotion
from .serializers import PromotionSerializer


class PromotionViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Promotion engine master data. Owner/manager writes; everyone can read."""

    queryset = Promotion.objects.select_related("buy_product", "get_product").all()
    serializer_class = PromotionSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def get_queryset(self):
        qs = super().get_queryset()
        promo_type = self.request.query_params.get("promo_type")
        if promo_type:
            qs = qs.filter(promo_type=promo_type)
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)
