from decimal import Decimal

from billing.models import Bill, Payment, Return, Shift
from billing.services import close_shift, create_bill
from inventory.models import StockLevel
from khata.models import LedgerEntry
from test_utils import POSTestCase

URL = "/api/billing/bills/"


class BillCreationTests(POSTestCase):
    def _bill_payload(self, **overrides):
        payload = {
            "lines": [{"product": self.product.id, "qty": "2"}],
            "payments": [{"mode": "cash", "amount": "200.00"}],
            "shift": self.shift.id,
        }
        payload.update(overrides)
        return payload

    def test_bill_totals_stock_and_change(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            URL,
            self._bill_payload(
                lines=[{
                    "product": self.product.id, "qty": "3",
                    "discount_percent": "10.00",
                }],
                payments=[{"mode": "cash", "amount": "250.00"}],
                bill_discount_amount="20.00",
                bill_discount_reason="loyal customer",
                tendered="300.00",
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        # 3 x 100 = 300 - 10% = 270 subtotal; -20 bill discount = 250 grand
        self.assertEqual(bill["subtotal"], "270.00")
        self.assertEqual(bill["bill_discount"], "20.00")
        self.assertEqual(bill["grand_total"], "250.00")
        self.assertEqual(bill["change_due"], "50.00")
        self.assertTrue(bill["bill_no"].startswith("TM-"))
        # stock deducted: 50 - 3 = 47
        self.assertEqual(self.stock_qty(), Decimal("47"))

    def test_bill_number_increments(self):
        client = self.client_for(self.cashier)
        b1 = client.post(URL, self._bill_payload(), format="json").json()["bill_no"]
        b2 = client.post(URL, self._bill_payload(), format="json").json()["bill_no"]
        self.assertNotEqual(b1, b2)

    def test_insufficient_stock_rejected_atomically(self):
        client = self.client_for(self.cashier)
        before = Bill.objects.count()
        resp = client.post(
            URL,
            self._bill_payload(
                lines=[{"product": self.product.id, "qty": "999"}],
                payments=[{"mode": "cash", "amount": "99900.00"}],
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Bill.objects.count(), before)  # nothing persisted
        self.assertEqual(self.stock_qty(), Decimal("50"))

    def test_payment_total_must_match(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            URL, self._bill_payload(payments=[{"mode": "cash", "amount": "150.00"}]),
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_bill_discount_needs_reason(self):
        client = self.client_for(self.cashier)
        # grand would be 190 (200 - 10 discount); payments match, but no reason given
        resp = client.post(
            URL,
            self._bill_payload(
                bill_discount_amount="10.00",
                payments=[{"mode": "cash", "amount": "190.00"}],
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("reason", resp.json()["detail"])

    def test_split_payment(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            URL,
            self._bill_payload(
                payments=[
                    {"mode": "cash", "amount": "120.00"},
                    {"mode": "card", "amount": "80.00"},
                ]
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        modes = {p["mode"]: p["amount"] for p in resp.json()["payments"]}
        self.assertEqual(modes, {"cash": "120.00", "card": "80.00"})

    def test_requires_open_shift(self):
        self.shift.status = Shift.STATUS_CLOSED
        self.shift.save()
        client = self.client_for(self.cashier)
        resp = client.post(URL, self._bill_payload(shift=None), format="json")
        self.assertEqual(resp.status_code, 400)

    def test_other_tenant_product_rejected(self):
        from catalog.models import Product

        other_product = Product.objects.create(
            tenant=self.other_tenant, sku="O-1", name="Other",
            retail_price=Decimal("10"),
        )
        client = self.client_for(self.cashier)
        resp = client.post(
            URL,
            self._bill_payload(
                lines=[{"product": other_product.id, "qty": "1"}],
                payments=[{"mode": "cash", "amount": "10.00"}],
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_bill_immutable_via_api(self):
        client = self.client_for(self.cashier)
        bill_id = client.post(URL, self._bill_payload(), format="json").json()["id"]
        self.assertEqual(client.put(f"{URL}{bill_id}/", {}, format="json").status_code, 405)
        self.assertEqual(client.patch(f"{URL}{bill_id}/", {}, format="json").status_code, 405)
        self.assertEqual(client.delete(f"{URL}{bill_id}/").status_code, 405)

    def test_bill_model_blocks_update(self):
        from django.core.exceptions import ValidationError

        client = self.client_for(self.cashier)
        bill_id = client.post(URL, self._bill_payload(), format="json").json()["id"]
        bill = Bill.objects.get(pk=bill_id)
        bill.notes = "hack"
        with self.assertRaises(ValidationError):
            bill.save()
        with self.assertRaises(ValidationError):
            bill.delete()


class KhataSaleTests(POSTestCase):
    def test_khata_sale_creates_receivable(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [{"mode": "khata", "amount": "200.00"}],
                "customer": self.customer.id,
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        entry = LedgerEntry.objects.get(
            customer=self.customer, entry_type=LedgerEntry.ENTRY_SALE
        )
        self.assertEqual(entry.amount, Decimal("200.00"))
        self.assertEqual(entry.balance_after, Decimal("200.00"))
        self.assertIsNotNone(entry.bill)

    def test_khata_requires_customer(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "1"}],
                "payments": [{"mode": "khata", "amount": "100.00"}],
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_credit_limit_blocked(self):
        client = self.client_for(self.cashier)
        # customer limit is 1000; this sale is 2000 on khata
        resp = client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "20"}],
                "payments": [{"mode": "khata", "amount": "2000.00"}],
                "customer": self.customer.id,
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Credit limit", resp.json()["detail"])
        self.assertEqual(Bill.objects.count(), 0)


class ShiftCloseTests(POSTestCase):
    def test_close_computes_expected_and_difference(self):
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
        resp = client.post(
            f"/api/billing/shifts/{self.shift.id}/close/",
            {"counted_cash": "1250.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        # opening 1000 + cash sales 200 = 1200 expected; counted 1250 -> +50
        self.assertEqual(data["expected_cash"], "1200.00")
        self.assertEqual(data["difference"], "50.00")
        self.assertEqual(data["status"], "closed")

    def test_double_close_rejected(self):
        close_shift(shift=self.shift, counted_cash=Decimal("1000"))
        with self.assertRaises(Exception):
            close_shift(shift=self.shift, counted_cash=Decimal("1000"))

    def test_second_open_shift_blocked(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/shifts/", {"opening_cash": "500"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)


class ReturnTests(POSTestCase):
    def _make_bill(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "4"}],
                "payments": [{"mode": "cash", "amount": "400.00"}],
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        return resp.json()

    def test_return_restocks_and_refunds(self):
        bill = self._make_bill()
        self.assertEqual(self.stock_qty(), Decimal("46"))
        mgr = self.client_for(self.manager)
        resp = mgr.post(
            "/api/billing/returns/",
            {
                "bill": bill["id"],
                "lines": [{"bill_line": bill["lines"][0]["id"], "qty": "1"}],
                "reason": "damaged pack",
                "refund_mode": "cash",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["total_refund"], "100.00")
        self.assertEqual(self.stock_qty(), Decimal("47"))  # restocked
        self.assertEqual(Return.objects.count(), 1)

    def test_return_more_than_bought_rejected(self):
        bill = self._make_bill()
        mgr = self.client_for(self.manager)
        resp = mgr.post(
            "/api/billing/returns/",
            {
                "bill": bill["id"],
                "lines": [{"bill_line": bill["lines"][0]["id"], "qty": "99"}],
                "reason": "oops",
                "refund_mode": "cash",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cashier_cannot_return(self):
        bill = self._make_bill()
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/returns/",
            {
                "bill": bill["id"],
                "lines": [{"bill_line": bill["lines"][0]["id"], "qty": "1"}],
                "reason": "oops",
                "refund_mode": "cash",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_khata_refund_reduces_receivable(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "2"}],
                "payments": [{"mode": "khata", "amount": "200.00"}],
                "customer": self.customer.id,
                "shift": self.shift.id,
            },
            format="json",
        )
        bill = resp.json()
        mgr = self.client_for(self.manager)
        resp = mgr.post(
            "/api/billing/returns/",
            {
                "bill": bill["id"],
                "lines": [{"bill_line": bill["lines"][0]["id"], "qty": "2"}],
                "reason": "full return",
                "refund_mode": "khata",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.balance, Decimal("0"))


class TenantIsolationTests(POSTestCase):
    def test_other_tenant_bills_invisible(self):
        client = self.client_for(self.cashier)
        client.post(
            "/api/billing/bills/",
            {
                "lines": [{"product": self.product.id, "qty": "1"}],
                "payments": [{"mode": "cash", "amount": "100.00"}],
                "shift": self.shift.id,
            },
            format="json",
        )
        other = self.client_for(self.other_owner)
        self.assertEqual(other.get("/api/billing/bills/").json()["count"], 0)
