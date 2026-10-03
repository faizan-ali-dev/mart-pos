import secrets

from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tenants.permissions import RolePermission, TenantScopedMixin

from .models import Bill, ParkedBill, Return, Shift
from .serializers import (
    BillCreateSerializer,
    BillSerializer,
    ParkedBillSerializer,
    ReturnCreateSerializer,
    ReturnSerializer,
    ShiftCloseSerializer,
    ShiftSerializer,
)
from .services import close_shift, create_bill, create_return


class ShiftViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Shift.objects.select_related("opened_by").all()
    serializer_class = ShiftSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager", "cashier")
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("open_only") in ("1", "true", "yes"):
            qs = qs.filter(status=Shift.STATUS_OPEN)
        return qs

    def perform_create(self, serializer):
        tenant = self.request.user.tenant
        if _open_shift_for_user(tenant, self.request.user):
            # DRF ValidationError -> 400
            from rest_framework.exceptions import ValidationError as DRFValidationError

            raise DRFValidationError("You already have an open shift.")
        serializer.save(
            tenant=tenant,
            opened_by=self.request.user,
            store=self.request.user.store,
        )

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        shift = self.get_object()
        ser = ShiftCloseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            shift = close_shift(
                shift=shift,
                counted_cash=ser.validated_data["counted_cash"],
                notes=ser.validated_data.get("notes", ""),
                closed_by=request.user,
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShiftSerializer(shift).data)


def _open_shift_for_user(tenant, user):
    return Shift.objects.filter(
        tenant=tenant, opened_by=user, status=Shift.STATUS_OPEN
    ).exists()


class BillViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """
    Bills are immutable: only list / retrieve / create exist.
    POST creates the whole bill atomically (totals, stock, khata).
    """

    queryset = Bill.objects.select_related("cashier", "customer", "shift").prefetch_related(
        "lines__product", "payments"
    ).all()
    serializer_class = BillSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager", "cashier")
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        date = self.request.query_params.get("date")
        if date:
            qs = qs.filter(created_at__date=date)
        sale_type = self.request.query_params.get("sale_type")
        if sale_type:
            qs = qs.filter(sale_type=sale_type)
        return qs

    def create(self, request, *args, **kwargs):
        ser = BillCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        tenant = request.user.tenant
        shift = None
        if data.get("shift"):
            shift = Shift.objects.filter(pk=data["shift"], tenant=tenant).first()
            if shift is None:
                return Response({"shift": "Not found."}, status=400)
        try:
            bill = create_bill(
                tenant=tenant,
                cashier=request.user,
                lines=[
                    {
                        "product": line["product"],
                        "qty": line["qty"],
                        "discount_percent": line.get("discount_percent", 0),
                        "discount_amount": line.get("discount_amount", 0),
                    }
                    for line in data["lines"]
                ],
                payments=[
                    {
                        "mode": p["mode"],
                        "amount": p["amount"],
                        "reference": p.get("reference", ""),
                    }
                    for p in data["payments"]
                ],
                bill_discount_percent=data.get("bill_discount_percent", 0),
                bill_discount_amount=data.get("bill_discount_amount", 0),
                bill_discount_reason=data.get("bill_discount_reason", ""),
                customer=data.get("customer"),
                tendered=data.get("tendered"),
                notes=data.get("notes", ""),
                shift=shift,
                sale_type=data.get("sale_type"),
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BillSerializer(bill).data, status=status.HTTP_201_CREATED)


class ParkedBillViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ParkedBill.objects.all().order_by("-created_at")
    serializer_class = ParkedBillSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager", "cashier")

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant,
            created_by=self.request.user,
            token=secrets.token_hex(8),
        )


class ReturnViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """POST records a return (restock + refund). Manager/owner only."""

    queryset = Return.objects.select_related("bill").prefetch_related("lines").all()
    serializer_class = ReturnSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        ser = ReturnCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        tenant = request.user.tenant
        bill = Bill.objects.filter(pk=data["bill"], tenant=tenant).first()
        if bill is None:
            return Response({"bill": "Not found."}, status=400)
        try:
            ret = create_return(
                tenant=tenant,
                bill=bill,
                lines=[
                    {"bill_line": line["bill_line"], "qty": line["qty"]}
                    for line in data["lines"]
                ],
                reason=data["reason"],
                refund_mode=data["refund_mode"],
                created_by=request.user,
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReturnSerializer(ret).data, status=status.HTTP_201_CREATED)
