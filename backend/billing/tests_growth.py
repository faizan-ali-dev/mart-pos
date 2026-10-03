from decimal import Decimal

from test_utils import POSTestCase

from billing.models import Payout
from billing.services import close_shift
from khata.models import KhataPayment
from khata.services import party_balance, record_payable


class PayoutTests(POSTestCase):
    def test_payout_requires_open_shift(self):
        close_shift(shift=self.shift, counted_cash=Decimal("1000"))
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/payouts/",
            {"amount": "100.00", "purpose": "other"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No open shift", resp.json()["detail"])

    def test_payout_auto_attaches_to_open_shift(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/payouts/",
            {"amount": "50.00", "purpose": "other", "notes": "chai"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data["shift"], self.shift.id)
        self.assertEqual(data["amount"], "50.00")

    def test_payout_reduces_expected_cash(self):
        client = self.client_for(self.cashier)
        client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [{"mode": "cash", "amount": "200.00"}],
                "shift": self.shift.id,
            },
            format="json",
        )
        client.post(
            "/api/billing/payouts/",
            {"amount": "50.00", "purpose": "other"},
            format="json",
        )
        resp = client.post(
            f"/api/billing/shifts/{self.shift.id}/close/",
            {"counted_cash": "1150.00"},
            format="json",
        )
        data = resp.json()
        # opening 1000 + cash sales 200 - payout 50 = 1150 expected
        self.assertEqual(data["expected_cash"], "1150.00")
        self.assertEqual(data["difference"], "0.00")

    def test_supplier_payout_creates_khata_payment(self):
        record_payable(
            tenant=self.tenant, supplier=self.supplier,
            amount=Decimal("500"), notes="stock",
        )
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/payouts/",
            {
                "amount": "200.00",
                "purpose": "supplier_payment",
                "supplier": self.supplier.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(
            party_balance(self.tenant, supplier=self.supplier), Decimal("300")
        )
        kp = KhataPayment.objects.get(supplier=self.supplier)
        self.assertEqual(kp.amount, Decimal("200"))
        self.assertEqual(kp.allocation[0]["allocated"], "200.00")

    def test_supplier_payout_overpay_rejected(self):
        record_payable(
            tenant=self.tenant, supplier=self.supplier, amount=Decimal("100")
        )
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/payouts/",
            {
                "amount": "200.00",
                "purpose": "supplier_payment",
                "supplier": self.supplier.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_supplier_required_for_supplier_payout(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/payouts/",
            {"amount": "200.00", "purpose": "supplier_payment"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_payout_list_and_purpose_filter(self):
        cashier = self.client_for(self.cashier)
        cashier.post(
            "/api/billing/payouts/",
            {"amount": "50.00", "purpose": "other"},
            format="json",
        )
        cashier.post(
            "/api/billing/payouts/",
            {"amount": "30.00", "purpose": "expense"},
            format="json",
        )
        owner = self.client_for(self.owner)
        self.assertEqual(
            owner.get("/api/billing/payouts/").json()["count"], 2
        )
        resp = owner.get("/api/billing/payouts/?purpose=expense")
        self.assertEqual(resp.json()["count"], 1)

    def test_tenant_isolation(self):
        Payout.objects.create(
            tenant=self.tenant, shift=self.shift, amount=Decimal("10"),
            purpose="other", created_by=self.owner,
        )
        other = self.client_for(self.other_owner)
        self.assertEqual(other.get("/api/billing/payouts/").json()["count"], 0)
