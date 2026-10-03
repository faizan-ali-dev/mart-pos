from django.db.models import Sum
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from tenants.permissions import RolePermission, TenantScopedMixin

from .models import Brand, Category, PriceSlab, Product, ProductBarcode
from .serializers import (
    BrandSerializer,
    CategorySerializer,
    PriceSlabSerializer,
    ProductBarcodeSerializer,
    ProductSerializer,
)


class CategoryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "name_urdu"]


class BrandViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Brand.objects.all().order_by("name")
    serializer_class = BrandSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    filter_backends = [filters.SearchFilter]
    search_fields = ["name"]


class ProductViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = (
        Product.objects.select_related("category", "brand")
        .annotate(stock_qty=Sum("stock_levels__qty"))
        .all()
        .order_by("name")
    )
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "name_urdu", "sku", "barcode"]

    def get_queryset(self):
        qs = super().get_queryset()
        barcode = self.request.query_params.get("barcode")
        if barcode:
            qs = qs.filter(barcode=barcode)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category_id=category)
        active = self.request.query_params.get("is_active")
        if active is not None:
            qs = qs.filter(is_active=active.lower() in ("1", "true", "yes"))
        return qs


class ProductBarcodeViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ProductBarcode.objects.select_related("product").all()
    serializer_class = ProductBarcodeSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")


class PriceSlabViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """Volume discount tiers for wholesale pricing (per product, per tenant)."""

    queryset = PriceSlab.objects.select_related("product").all()
    serializer_class = PriceSlabSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def get_queryset(self):
        qs = super().get_queryset()
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        return qs
