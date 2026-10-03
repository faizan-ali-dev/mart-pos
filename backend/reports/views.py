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


# ---------------------------------------------------------------------------
# Filtered reports + CSV/Excel export
# ---------------------------------------------------------------------------
import csv
from io import BytesIO, StringIO

from django.db.models import Q
from django.http import HttpResponse
from rest_framework.pagination import PageNumberPagination

import openpyxl

from billing.models import Bill, BillLine, Payout
from expenses.models import Expense
from inventory.models import GRNLine


def _parse_opt_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return "invalid"


def _export_csv(filename, headers, rows):
    buf = StringIO()
    buf.write("\ufeff")  # BOM so Excel opens UTF-8 (Urdu names) correctly
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    response = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _export_xlsx(filename, headers, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _maybe_export(request, filename_base, columns, rows):
    """
    export=csv|xlsx -> file download of ALL rows; otherwise paginated JSON.

    (Named `export`, not `format`: DRF reserves ?format= for content negotiation
    and 404s on unknown renderer names like "csv".)
    """
    fmt = (request.query_params.get("export") or "").lower()
    keys = [key for key, _ in columns]
    headers = [label for _, label in columns]
    if fmt == "csv":
        return _export_csv(
            f"{filename_base}.csv", headers, [[r[k] for k in keys] for r in rows]
        )
    if fmt == "xlsx":
        return _export_xlsx(
            f"{filename_base}.xlsx", headers, [[r[k] for k in keys] for r in rows]
        )
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(page)


class SalesReportView(APIView):
    """
    GET /api/reports/sales/?from=YYYY-MM-DD&to=YYYY-MM-DD&search=&category=
        &sale_type=&payment_mode=&export=
    Line-level sales. Paginated JSON by default; export=csv|xlsx downloads
    every filtered row as a file.
    """

    permission_classes = [IsAuthenticated]
    COLUMNS = [
        ("bill_no", "Bill No"),
        ("date", "Date"),
        ("time", "Time"),
        ("cashier", "Cashier"),
        ("customer", "Customer"),
        ("sale_type", "Sale Type"),
        ("sku", "SKU"),
        ("product", "Product"),
        ("qty", "Qty"),
        ("rate", "Rate"),
        ("discount", "Discount"),
        ("line_total", "Line Total"),
        ("payment_modes", "Payment Modes"),
        ("free_item", "Free Item"),
    ]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        tenant = request.user.tenant
        date_from = _parse_opt_date(request.query_params.get("from"))
        date_to = _parse_opt_date(request.query_params.get("to"))
        if date_from == "invalid" or date_to == "invalid":
            return Response({"detail": "Use YYYY-MM-DD for from/to."}, status=400)

        lines = (
            BillLine.objects.filter(bill__tenant=tenant)
            .select_related("bill", "bill__cashier", "bill__customer",
                            "product", "product__category")
            .prefetch_related("bill__payments")
            .order_by("-bill__created_at", "id")
        )
        if date_from:
            lines = lines.filter(bill__created_at__date__gte=date_from)
        if date_to:
            lines = lines.filter(bill__created_at__date__lte=date_to)
        search = request.query_params.get("search")
        if search:
            lines = lines.filter(
                Q(bill__bill_no__icontains=search)
                | Q(product__name__icontains=search)
                | Q(product__sku__icontains=search)
            )
        category = request.query_params.get("category")
        if category:
            lines = lines.filter(product__category_id=category)
        sale_type = request.query_params.get("sale_type")
        if sale_type:
            lines = lines.filter(bill__sale_type=sale_type)
        payment_mode = request.query_params.get("payment_mode")
        if payment_mode:
            lines = lines.filter(bill__payments__mode=payment_mode)

        rows = []
        for line in lines:
            bill = line.bill
            modes = ",".join(sorted({p.mode for p in bill.payments.all()}))
            rows.append(
                {
                    "bill_no": bill.bill_no,
                    "date": bill.created_at.date().isoformat(),
                    "time": bill.created_at.strftime("%H:%M"),
                    "cashier": bill.cashier.username,
                    "customer": bill.customer.name if bill.customer else "",
                    "sale_type": bill.sale_type,
                    "sku": line.product.sku,
                    "product": line.product.name,
                    "qty": str(line.qty),
                    "rate": str(line.rate),
                    "discount": str(line.discount_amount),
                    "line_total": str(line.line_total),
                    "payment_modes": modes,
                    "free_item": "Yes" if line.is_free else "",
                }
            )
        fname = f"sales-{date_from or 'all'}-to-{date_to or 'all'}"
        return _maybe_export(request, fname, self.COLUMNS, rows)


class PurchasesReportView(APIView):
    """
    GET /api/reports/purchases/?from=&to=&supplier=&search=&export=
    Line-level purchases (GRN). Paginated JSON by default; export=csv|xlsx
    downloads every filtered row as a file.
    """

    permission_classes = [IsAuthenticated]
    COLUMNS = [
        ("grn", "GRN"),
        ("date", "Date"),
        ("supplier", "Supplier"),
        ("supplier_invoice", "Supplier Invoice"),
        ("sku", "SKU"),
        ("product", "Product"),
        ("qty", "Qty"),
        ("purchase_rate", "Purchase Rate"),
        ("line_total", "Line Total"),
        ("on_credit", "On Credit"),
    ]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        tenant = request.user.tenant
        date_from = _parse_opt_date(request.query_params.get("from"))
        date_to = _parse_opt_date(request.query_params.get("to"))
        if date_from == "invalid" or date_to == "invalid":
            return Response({"detail": "Use YYYY-MM-DD for from/to."}, status=400)

        lines = (
            GRNLine.objects.filter(grn__tenant=tenant)
            .select_related("grn", "grn__supplier", "product")
            .order_by("-grn__received_at", "id")
        )
        if date_from:
            lines = lines.filter(grn__received_at__date__gte=date_from)
        if date_to:
            lines = lines.filter(grn__received_at__date__lte=date_to)
        supplier = request.query_params.get("supplier")
        if supplier:
            lines = lines.filter(grn__supplier_id=supplier)
        search = request.query_params.get("search")
        if search:
            lines = lines.filter(
                Q(grn__supplier__name__icontains=search)
                | Q(product__name__icontains=search)
                | Q(product__sku__icontains=search)
                | Q(grn__supplier_invoice_no__icontains=search)
            )

        rows = [
            {
                "grn": f"GRN-{line.grn_id}",
                "date": line.grn.received_at.date().isoformat(),
                "supplier": line.grn.supplier.name,
                "supplier_invoice": line.grn.supplier_invoice_no,
                "sku": line.product.sku,
                "product": line.product.name,
                "qty": str(line.qty),
                "purchase_rate": str(line.purchase_rate),
                "line_total": str(line.line_total),
                "on_credit": "Yes" if line.grn.on_credit else "",
            }
            for line in lines
        ]
        fname = f"purchases-{date_from or 'all'}-to-{date_to or 'all'}"
        return _maybe_export(request, fname, self.COLUMNS, rows)


class ProfitReportView(APIView):
    """
    GET /api/reports/profit/?from=YYYY-MM-DD&to=YYYY-MM-DD
    -> {from, to, sales_total, returns_total, net_sales, cogs_estimate,
        gross_profit, expenses_total, payouts_total, net_profit}

    cogs_estimate uses each product's CURRENT weighted-average cost, not the
    cost at the time of sale — it is an estimate, and it still counts lines
    that were later returned. Free (bogo) lines cost the shop too, so they
    are included in COGS.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        tenant = request.user.tenant
        date_from = _parse_opt_date(request.query_params.get("from"))
        date_to = _parse_opt_date(request.query_params.get("to"))
        if date_from == "invalid" or date_to == "invalid":
            return Response({"detail": "Use YYYY-MM-DD for from/to."}, status=400)

        bills = Bill.objects.filter(tenant=tenant)
        if date_from:
            bills = bills.filter(created_at__date__gte=date_from)
        if date_to:
            bills = bills.filter(created_at__date__lte=date_to)

        from billing.models import Return

        returns = Return.objects.filter(tenant=tenant)
        if date_from:
            returns = returns.filter(created_at__date__gte=date_from)
        if date_to:
            returns = returns.filter(created_at__date__lte=date_to)

        sales_total = bills.aggregate(t=Sum("grand_total"))["t"] or Decimal("0")
        returns_total = returns.aggregate(t=Sum("total_refund"))["t"] or Decimal("0")
        net_sales = _q2(sales_total - returns_total)

        cogs = Decimal("0")
        for line in BillLine.objects.filter(bill__in=bills).select_related("product"):
            cogs += line.qty * line.product.purchase_price
        cogs = _q2(cogs)

        expenses_total = Expense.objects.filter(tenant=tenant)
        if date_from:
            expenses_total = expenses_total.filter(date__gte=date_from)
        if date_to:
            expenses_total = expenses_total.filter(date__lte=date_to)
        expenses_total = expenses_total.aggregate(t=Sum("amount"))["t"] or Decimal("0")

        payouts_total = Payout.objects.filter(tenant=tenant)
        if date_from:
            payouts_total = payouts_total.filter(created_at__date__gte=date_from)
        if date_to:
            payouts_total = payouts_total.filter(created_at__date__lte=date_to)
        payouts_total = payouts_total.aggregate(t=Sum("amount"))["t"] or Decimal("0")

        gross_profit = _q2(net_sales - cogs)
        net_profit = _q2(gross_profit - expenses_total - payouts_total)

        return Response(
            {
                "from": date_from.isoformat() if date_from else None,
                "to": date_to.isoformat() if date_to else None,
                "sales_total": str(_q2(sales_total)),
                "returns_total": str(_q2(returns_total)),
                "net_sales": str(net_sales),
                "cogs_estimate": str(cogs),
                "gross_profit": str(gross_profit),
                "expenses_total": str(_q2(expenses_total)),
                "payouts_total": str(_q2(payouts_total)),
                "net_profit": str(net_profit),
            }
        )
