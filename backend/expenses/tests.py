from datetime import date, timedelta
from decimal import Decimal

from test_utils import POSTestCase

from .models import Expense, ExpenseCategory


class ExpenseCategoryTests(POSTestCase):
    def test_owner_can_crud_categories(self):
        client = self.client_for(self.owner)
        resp = client.post(
            "/api/expenses/categories/", {"name": "Rent"}, format="json"
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        cat_id = resp.json()["id"]
        # duplicate name rejected per tenant
        resp = client.post("/api/expenses/categories/", {"name": "Rent"}, format="json")
        self.assertEqual(resp.status_code, 400)
        # list + delete
        self.assertEqual(client.get("/api/expenses/categories/").json()["count"], 1)
        self.assertEqual(
            client.delete(f"/api/expenses/categories/{cat_id}/").status_code, 204
        )

    def test_cashier_cannot_manage_categories(self):
        client = self.client_for(self.cashier)
        self.assertEqual(
            client.post("/api/expenses/categories/", {"name": "X"}, format="json").status_code,
            403,
        )

    def test_tenant_isolation(self):
        ExpenseCategory.objects.create(tenant=self.tenant, name="Rent")
        other = self.client_for(self.other_owner)
        self.assertEqual(other.get("/api/expenses/categories/").json()["count"], 0)


class ExpenseTests(POSTestCase):
    def setUp(self):
        super().setUp()
        self.rent = ExpenseCategory.objects.create(tenant=self.tenant, name="Rent")
        self.power = ExpenseCategory.objects.create(tenant=self.tenant, name="Electricity")

    def _add(self, day, category, amount, notes=""):
        return self.client_for(self.owner).post(
            "/api/expenses/expenses/",
            {
                "date": day.isoformat(),
                "category": category.id,
                "amount": str(amount),
                "payment_mode": "cash",
                "notes": notes,
            },
            format="json",
        )

    def test_create_and_filters(self):
        today = date.today()
        self._add(today, self.rent, Decimal("20000"))
        self._add(today - timedelta(days=10), self.power, Decimal("8500"))
        client = self.client_for(self.owner)
        self.assertEqual(client.get("/api/expenses/expenses/").json()["count"], 2)
        # date range
        resp = client.get(
            f"/api/expenses/expenses/?from={today.isoformat()}&to={today.isoformat()}"
        )
        self.assertEqual(resp.json()["count"], 1)
        # category filter
        resp = client.get(f"/api/expenses/expenses/?category={self.power.id}")
        self.assertEqual(resp.json()["count"], 1)

    def test_negative_amount_rejected(self):
        resp = self._add(date.today(), self.rent, Decimal("-5"))
        self.assertEqual(resp.status_code, 400)

    def test_cashier_cannot_add_expense(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/expenses/expenses/",
            {
                "date": date.today().isoformat(),
                "category": self.rent.id,
                "amount": "100",
                "payment_mode": "cash",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_summary_by_category(self):
        today = date.today()
        self._add(today, self.rent, Decimal("20000"))
        self._add(today, self.power, Decimal("8500"))
        data = self.client_for(self.owner).get("/api/expenses/summary/").json()
        self.assertEqual(data["total"], "28500.00")
        by_cat = {r["name"]: r["total"] for r in data["by_category"]}
        self.assertEqual(by_cat["Rent"], "20000.00")
        self.assertEqual(by_cat["Electricity"], "8500.00")
