from django.core.exceptions import ValidationError
from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.permissions import RolePermission, TenantScopedMixin

from .models import Customer, KhataPayment, LedgerEntry, Supplier
from .serializers import (
    CustomerSerializer,
    KhataPaymentCreateSerializer,
    KhataPaymentSerializer,
    LedgerEntrySerializer,
    SupplierSerializer,
)
from .services import aging_report, record_khata_payment


class CustomerViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all().order_by("name")
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "phone"]


class SupplierViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Supplier.objects.all().order_by("name")
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "phone"]


class LedgerEntryViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = LedgerEntry.objects.select_related("customer", "supplier").all()
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        customer = self.request.query_params.get("customer")
        supplier = self.request.query_params.get("supplier")
        entry_type = self.request.query_params.get("entry_type")
        if customer:
            qs = qs.filter(customer_id=customer)
        if supplier:
            qs = qs.filter(supplier_id=supplier)
        if entry_type:
            qs = qs.filter(entry_type=entry_type)
        return qs


class KhataPaymentViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    """
    GET lists payments; POST records a payment and allocates it FIFO against
    the oldest unpaid dues. Cashiers may record payments; master data stays
    owner/manager-only.
    """

    queryset = KhataPayment.objects.select_related("customer", "supplier").all()
    serializer_class = KhataPaymentSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager", "cashier")
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        ser = KhataPaymentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        tenant = request.user.tenant
        customer = supplier = None
        if data.get("customer"):
            try:
                customer = Customer.objects.get(pk=data["customer"], tenant=tenant)
            except Customer.DoesNotExist:
                return Response({"customer": "Not found."}, status=400)
        if data.get("supplier"):
            try:
                supplier = Supplier.objects.get(pk=data["supplier"], tenant=tenant)
            except Supplier.DoesNotExist:
                return Response({"supplier": "Not found."}, status=400)
        try:
            payment = record_khata_payment(
                tenant=tenant,
                customer=customer,
                supplier=supplier,
                amount=data["amount"],
                mode=data.get("mode", "cash"),
                reference=data.get("reference", ""),
                created_by=request.user,
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(KhataPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class AgingReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        return Response(aging_report(request.user.tenant))
