from datetime import date

from test_utils import POSTestCase


class DailySummaryTests(POSTestCase):
    def test_daily_summary(self):
        client = self.client_for(self.cashier)
        client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [
                    {"mode": "cash", "amount": "120.00"},
                    {"mode": "card", "amount": "80.00"},
                ],
                "shift": self.shift.id,
            },
            format="json",
        )
        resp = client.get("/api/reports/daily-summary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["date"], date.today().isoformat())
        self.assertEqual(data["bills_count"], 1)
        self.assertEqual(data["total_sales"], "200.00")
        self.assertEqual(data["by_mode"]["cash"], "120.00")
        self.assertEqual(data["by_mode"]["card"], "80.00")
        self.assertEqual(data["top_items"][0]["product__sku"], "T-001")

    def test_daily_summary_nets_returns(self):
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
        data = cashier.get("/api/reports/daily-summary/").json()
        self.assertEqual(data["total_sales"], "100.00")  # 200 - 100 return
        self.assertEqual(data["payouts"], "100.00")

    def test_bad_date_rejected(self):
        client = self.client_for(self.owner)
        self.assertEqual(
            client.get("/api/reports/daily-summary/?date=not-a-date").status_code, 400
        )
