from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from billing.models import Bill, BillLine
from billing.services import _q2, day_summary


class DailySummaryView(APIView):
    """
    GET /api/reports/daily-summary/?date=YYYY-MM-DD
    -> {date, bills_count, returns_count, total_sales, by_mode:{...},
        payouts, top_items[]}
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        raw = request.query_params.get("date")
        try:
            target = date.fromisoformat(raw) if raw else date.today()
        except ValueError:
            return Response({"date": "Use YYYY-MM-DD format."}, status=400)
        return Response(day_summary(request.user.tenant, target))


class WholesaleSummaryView(APIView):
    """
    GET /api/reports/wholesale-summary/?date=YYYY-MM-DD&customer=<id>
    -> {date, bills_count, total_sales, by_customer:[{id, name, bills, total}],
        top_items:[{sku, name, qty, revenue}], margin_estimate}

    margin_estimate = sum(line_total - qty * purchase_price). It is an estimate
    because purchase_price is the *current* weighted-average cost, not the cost
    at the time of sale. The bill-level discount is allocated to lines
    proportionally so the margin reflects what was actually charged.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        raw = request.query_params.get("date")
        try:
            target = date.fromisoformat(raw) if raw else date.today()
        except ValueError:
            return Response({"date": "Use YYYY-MM-DD format."}, status=400)

        tenant = request.user.tenant
        bills = Bill.objects.filter(
            tenant=tenant, sale_type=Bill.SALE_WHOLESALE, created_at__date=target
        )
        customer_id = request.query_params.get("customer")
        if customer_id:
            bills = bills.filter(customer_id=customer_id)

        agg = bills.aggregate(total=Sum("grand_total"), n=Count("id"))
        total_sales = agg["total"] or Decimal("0")

        by_customer = list(
            bills.values("customer__id", "customer__name")
            .annotate(total=Sum("grand_total"), bills=Count("id"))
            .order_by("-total")
        )
        for row in by_customer:
            row["id"] = row.pop("customer__id")
            row["name"] = row.pop("customer__name") or "Walk-in"
            row["total"] = str(_q2(row["total"] or 0))

        lines = BillLine.objects.filter(bill__in=bills).select_related(
            "product", "bill"
        )
        top_items = list(
            lines.values("product__sku", "product__name")
            .annotate(qty=Sum("qty"), revenue=Sum("line_total"))
            .order_by("-qty")[:10]
        )
        for item in top_items:
            item["sku"] = item.pop("product__sku")
            item["name"] = item.pop("product__name")
            item["qty"] = str(item["qty"])
            item["revenue"] = str(_q2(item["revenue"] or 0))

        margin = Decimal("0")
        for line in lines:
            bill = line.bill
            if bill.subtotal:
                line_revenue = (
                    line.line_total
                    - bill.bill_discount * line.line_total / bill.subtotal
                )
            else:
                line_revenue = line.line_total
            margin += line_revenue - line.qty * line.product.purchase_price

        return Response(
            {
                "date": target.isoformat(),
                "bills_count": agg["n"],
                "total_sales": str(_q2(total_sales)),
                "by_customer": by_customer,
                "top_items": top_items,
                "margin_estimate": str(_q2(margin)),
            }
        )
