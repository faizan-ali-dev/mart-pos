from django.core.exceptions import ValidationError
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product
from khata.models import Supplier
from tenants.models import User
from tenants.permissions import RolePermission, TenantScopedMixin

from .models import Batch, GRN, PurchaseOrder, StockAdjustment, StockLevel, StockLocation
from .serializers import (
    BatchSerializer,
    GRNCreateSerializer,
    GRNSerializer,
    PurchaseOrderSerializer,
    StockAdjustmentCreateSerializer,
    StockAdjustmentSerializer,
    StockLevelSerializer,
    StockLocationSerializer,
)
from .services import apply_adjustment, expiring_batches, low_stock_items, receive_grn


class StockLocationViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = StockLocation.objects.all().order_by("name")
    serializer_class = StockLocationSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")


class StockLevelViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = StockLevel.objects.select_related("product", "location").all().order_by(
        "product__name"
    )
    serializer_class = StockLevelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("low_stock") in ("1", "true", "yes"):
            qs = qs.filter(qty__lte=F("product__reorder_level"))
        product = self.request.query_params.get("product")
        if product:
            qs = qs.filter(product_id=product)
        return qs


class PurchaseOrderViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").all().order_by("-created_at")
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant, created_by=self.request.user)


class GRNViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """
    GET lists GRNs; POST receives stock (creates GRN + updates stock levels,
    weighted-average cost, batches and supplier payable when on_credit).
    """

    queryset = GRN.objects.select_related("supplier", "location").prefetch_related(
        "lines__product"
    ).all().order_by("-received_at")
    serializer_class = GRNSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        ser = GRNCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        tenant = request.user.tenant
        try:
            supplier = Supplier.objects.get(pk=data["supplier"], tenant=tenant)
        except Supplier.DoesNotExist:
            return Response({"supplier": "Not found."}, status=status.HTTP_400_BAD_REQUEST)
        location = None
        if data.get("location"):
            try:
                location = StockLocation.objects.get(pk=data["location"], tenant=tenant)
            except StockLocation.DoesNotExist:
                return Response({"location": "Not found."}, status=status.HTTP_400_BAD_REQUEST)
        else:
            location = StockLocation.objects.filter(
                tenant=tenant, location_type=StockLocation.SHOP_FLOOR, is_active=True
            ).first() or StockLocation.objects.filter(tenant=tenant, is_active=True).first()
            if location is None:
                return Response(
                    {"detail": "No active stock location. Create one first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        lines = []
        for line in data["lines"]:
            try:
                product = Product.objects.get(pk=line["product"], tenant=tenant)
            except Product.DoesNotExist:
                return Response(
                    {"lines": f"Product {line['product']} not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lines.append(
                {
                    "product": product,
                    "qty": line["qty"],
                    "purchase_rate": line["purchase_rate"],
                    "expiry_date": line.get("expiry_date"),
                }
            )
        try:
            grn = receive_grn(
                tenant=tenant,
                supplier=supplier,
                location=location,
                lines=lines,
                supplier_invoice_no=data.get("supplier_invoice_no", ""),
                on_credit=data.get("on_credit", False),
                notes=data.get("notes", ""),
                received_by=request.user,
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(GRNSerializer(grn).data, status=status.HTTP_201_CREATED)


class StockAdjustmentViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = StockAdjustment.objects.select_related("product", "location").all().order_by(
        "-created_at"
    )
    serializer_class = StockAdjustmentSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        ser = StockAdjustmentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        tenant = request.user.tenant
        try:
            product = Product.objects.get(pk=data["product"], tenant=tenant)
            location = StockLocation.objects.get(pk=data["location"], tenant=tenant)
        except (Product.DoesNotExist, StockLocation.DoesNotExist):
            return Response(
                {"detail": "Product or location not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # A manager/owner must approve stock-reducing adjustments. If the
        # requester is one, they self-approve; otherwise approval is required
        # and must come from a manager/owner (passed as approved_by id... kept
        # simple: only owner/manager can POST this endpoint at all).
        approver = request.user if request.user.role in ("owner", "manager") else None
        try:
            adj = apply_adjustment(
                tenant=tenant,
                product=product,
                location=location,
                adjustment_type=data["adjustment_type"],
                qty_change=data["qty_change"],
                reason=data["reason"],
                created_by=request.user,
                approved_by=approver,
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            StockAdjustmentSerializer(adj).data, status=status.HTTP_201_CREATED
        )


class BatchViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Batch.objects.select_related("product").all().order_by("expiry_date")
    serializer_class = BatchSerializer
    permission_classes = [IsAuthenticated]


class InventoryAlertsView(APIView):
    """Low-stock products + batches expiring within 90 days."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = request.user.tenant
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        low = [
            {
                "product": p.id,
                "sku": p.sku,
                "name": p.name,
                "total_qty": str(p.total_qty or 0),
                "reorder_level": str(p.reorder_level),
            }
            for p in low_stock_items(tenant)
        ]
        exp = [
            {
                "batch": b.id,
                "product": b.product_id,
                "sku": b.product.sku,
                "name": b.product.name,
                "expiry_date": b.expiry_date.isoformat(),
                "qty": str(b.qty),
            }
            for b in expiring_batches(tenant)
        ]
        return Response({"low_stock": low, "expiring_soon": exp})
