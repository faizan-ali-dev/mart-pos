from datetime import date
from decimal import Decimal

from test_utils import POSTestCase

from expenses.models import Expense, ExpenseCategory
from inventory.services import receive_grn


class SalesReportTests(POSTestCase):
    def _bill(self, qty="2", mode="cash", amount="200.00"):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": qty}],
                "payments": [{"mode": mode, "amount": amount}],
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()

    def test_sales_report_rows_and_filters(self):
        self._bill()
        client = self.client_for(self.owner)
        data = client.get("/api/reports/sales/").json()
        self.assertEqual(data["count"], 1)
        row = data["results"][0]
        self.assertEqual(row["sku"], "T-001")
        self.assertEqual(row["line_total"], "200.00")
        self.assertEqual(row["payment_modes"], "cash")
        self.assertEqual(row["sale_type"], "retail")

        # search by product name / sku / bill no
        self.assertEqual(
            client.get("/api/reports/sales/?search=Tea").json()["count"], 1
        )
        self.assertEqual(
            client.get("/api/reports/sales/?search=NOPE").json()["count"], 0
        )
        # sale_type + payment_mode filters
        self.assertEqual(
            client.get("/api/reports/sales/?sale_type=retail").json()["count"], 1
        )
        self.assertEqual(
            client.get("/api/reports/sales/?sale_type=wholesale").json()["count"], 0
        )
        self.assertEqual(
            client.get("/api/reports/sales/?payment_mode=card").json()["count"], 0
        )
        # category filter
        self.assertEqual(
            client.get(
                f"/api/reports/sales/?category={self.category.id}"
            ).json()["count"],
            1,
        )
        # date range
        today = date.today().isoformat()
        self.assertEqual(
            client.get(f"/api/reports/sales/?from={today}&to={today}").json()["count"],
            1,
        )
        self.assertEqual(
            client.get("/api/reports/sales/?from=2000-01-01&to=2000-01-02").json()[
                "count"
            ],
            0,
        )

    def test_sales_csv_export(self):
        self._bill()
        client = self.client_for(self.owner)
        resp = client.get("/api/reports/sales/?export=csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn(".csv", resp["Content-Disposition"])
        body = resp.content.decode("utf-8-sig")
        self.assertIn("Bill No", body)
        self.assertIn("T-001", body)

    def test_sales_xlsx_export(self):
        self._bill()
        client = self.client_for(self.owner)
        resp = client.get("/api/reports/sales/?export=xlsx")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml.sheet", resp["Content-Type"])
        self.assertIn("attachment", resp["Content-Disposition"])
        # a real xlsx is a zip archive
        self.assertTrue(resp.content[:2] == b"PK")

    def test_sales_bad_date_rejected(self):
        client = self.client_for(self.owner)
        self.assertEqual(
            client.get("/api/reports/sales/?from=nope").status_code, 400
        )


class PurchasesReportTests(POSTestCase):
    def test_purchases_rows_filters_and_export(self):
        receive_grn(
            tenant=self.tenant,
            supplier=self.supplier,
            location=self.location,
            lines=[{"product": self.product, "qty": Decimal("10"),
                    "purchase_rate": Decimal("80")}],
            supplier_invoice_no="INV-1",
            received_by=self.owner,
        )
        client = self.client_for(self.owner)
        data = client.get("/api/reports/purchases/").json()
        self.assertEqual(data["count"], 1)
        row = data["results"][0]
        self.assertEqual(row["sku"], "T-001")
        self.assertEqual(row["qty"], "10.000")
        self.assertEqual(row["purchase_rate"], "80.00")
        self.assertEqual(row["supplier"], "Test Supplier")

        self.assertEqual(
            client.get("/api/reports/purchases/?search=INV-1").json()["count"], 1
        )
        self.assertEqual(
            client.get(
                f"/api/reports/purchases/?supplier={self.supplier.id}"
            ).json()["count"],
            1,
        )
        resp = client.get("/api/reports/purchases/?export=csv")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        self.assertIn("T-001", resp.content.decode("utf-8-sig"))
        resp = client.get("/api/reports/purchases/?export=xlsx")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content[:2] == b"PK")


class ProfitReportTests(POSTestCase):
    def test_profit_math(self):
        client = self.client_for(self.cashier)
        # 2 x 100 = 200 sales; COGS = 2 x 80 = 160
        client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [{"mode": "cash", "amount": "200.00"}],
                "shift": self.shift.id,
            },
            format="json",
        )
        owner = self.client_for(self.owner)
        cat = ExpenseCategory.objects.create(tenant=self.tenant, name="Rent")
        Expense.objects.create(
            tenant=self.tenant, date=date.today(), category=cat,
            amount=Decimal("50"), payment_mode="cash", created_by=self.owner,
        )
        data = owner.get("/api/reports/profit/").json()
        self.assertEqual(data["sales_total"], "200.00")
        self.assertEqual(data["returns_total"], "0.00")
        self.assertEqual(data["net_sales"], "200.00")
        self.assertEqual(data["cogs_estimate"], "160.00")
        self.assertEqual(data["gross_profit"], "40.00")
        self.assertEqual(data["expenses_total"], "50.00")
        self.assertEqual(data["payouts_total"], "0.00")
        self.assertEqual(data["net_profit"], "-10.00")

    def test_profit_nets_returns(self):
        cashier = self.client_for(self.cashier)
        bill = cashier.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [{"mode": "cash", "amount": "200.00"}],
                "shift": self.shift.id,
            },
            format="json",
        ).json()
        mgr = self.client_for(self.manager)
        mgr.post(
            "/api/billing/returns/",
            {
                "bill": bill["id"],
                "lines": [{"bill_line": bill["lines"][0]["id"], "qty": "1"}],
                "reason": "test",
                "refund_mode": "cash",
            },
            format="json",
        )
        data = self.client_for(self.owner).get("/api/reports/profit/").json()
        self.assertEqual(data["sales_total"], "200.00")
        self.assertEqual(data["returns_total"], "100.00")
        self.assertEqual(data["net_sales"], "100.00")

    def test_daily_summary_has_expense_and_profit(self):
        cashier = self.client_for(self.cashier)
        cashier.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [{"mode": "cash", "amount": "200.00"}],
                "shift": self.shift.id,
            },
            format="json",
        )
        cat = ExpenseCategory.objects.create(tenant=self.tenant, name="Rent")
        Expense.objects.create(
            tenant=self.tenant, date=date.today(), category=cat,
            amount=Decimal("30"), payment_mode="cash", created_by=self.owner,
        )
        data = cashier.get("/api/reports/daily-summary/").json()
        self.assertEqual(data["expenses_total"], "30.00")
        self.assertEqual(data["payouts_total"], "0.00")
        self.assertEqual(data["net_profit"], "170.00")  # 200 - 30
