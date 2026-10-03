from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.permissions import RolePermission, TenantScopedMixin

from .models import Expense, ExpenseCategory
from .serializers import ExpenseCategorySerializer, ExpenseSerializer


def _q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ExpenseCategoryViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all().order_by("name")
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class ExpenseViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.select_related("category", "created_by").all()
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        date_from = self.request.query_params.get("from")
        date_to = self.request.query_params.get("to")
        category = self.request.query_params.get("category")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if category:
            qs = qs.filter(category_id=category)
        return qs

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant, created_by=self.request.user
        )


class ExpenseSummaryView(APIView):
    """
    GET /api/expenses/summary/?from=YYYY-MM-DD&to=YYYY-MM-DD
    -> {from, to, total, by_category: [{id, name, total}]}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        tenant = request.user.tenant
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")
        qs = Expense.objects.filter(tenant=tenant)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        total = _q2(qs.aggregate(t=Sum("amount"))["t"] or Decimal("0"))
        by_category = list(
            qs.values("category__id", "category__name")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        for row in by_category:
            row["id"] = row.pop("category__id")
            row["name"] = row.pop("category__name")
            row["total"] = str(_q2(row["total"] or 0))
        return Response(
            {
                "from": date_from,
                "to": date_to or date.today().isoformat(),
                "total": str(total),
                "by_category": by_category,
            }
        )
