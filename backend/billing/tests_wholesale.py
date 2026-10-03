"""Wholesale module tests: pricing, slabs, auto discounts, reports, isolation."""
from decimal import Decimal

from django.db import IntegrityError, transaction

from catalog.models import PriceSlab
from inventory.models import StockLevel
from khata.models import Customer
from test_utils import POSTestCase

BILL_URL = "/api/billing/bills/"
SLAB_URL = "/api/catalog/price-slabs/"
SUMMARY_URL = "/api/reports/wholesale-summary/"


class WholesaleBillingTests(POSTestCase):
    """Wholesale pricing on top of the shared fixture (retail 100, cost 80)."""

    def setUp(self):
        super().setUp()
        self.product.wholesale_price = Decimal("90")
        self.product.save(update_fields=["wholesale_price"])
        # Plenty of stock for volume-quantity bills.
        StockLevel.objects.filter(
            tenant=self.tenant, product=self.product, location=self.location
        ).update(qty=Decimal("100000"))
        self.ws_customer = Customer.objects.create(
            tenant=self.tenant,
            name="Wholesale Trader",
            phone="03009998888",
            customer_type=Customer.TYPE_WHOLESALE,
            wholesale_discount_percent=Decimal("2"),
            credit_limit=Decimal("200000"),
        )
        PriceSlab.objects.create(
            tenant=self.tenant, product=self.product,
            min_qty=Decimal("24"), discount_percent=Decimal("3"),
        )
        PriceSlab.objects.create(
            tenant=self.tenant, product=self.product,
            min_qty=Decimal("60"), discount_percent=Decimal("5"),
        )

    def _bill(self, **overrides):
        payload = {
            "lines": [{"product": self.product.id, "qty": "2"}],
            "payments": [{"mode": "cash", "amount": "176.40"}],
            "customer": self.ws_customer.id,
            "shift": self.shift.id,
        }
        payload.update(overrides)
        return self.client_for(self.cashier).post(BILL_URL, payload, format="json")

    # --- pricing ---------------------------------------------------------
    def test_wholesale_rate_auto_detected_from_customer(self):
        resp = self._bill()
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        # 2 x 90 (wholesale rate) = 180; no slab at qty 2; auto 2% = 3.60
        self.assertEqual(bill["sale_type"], "wholesale")
        line = bill["lines"][0]
        self.assertEqual(line["rate"], "90.00")
        self.assertEqual(line["applied_rate"], "90.00")
        self.assertEqual(line["slab_discount_percent"], "0.00")
        self.assertEqual(bill["subtotal"], "180.00")
        self.assertEqual(bill["bill_discount"], "3.60")
        self.assertEqual(bill["grand_total"], "176.40")
        self.assertIn("Wholesale customer discount", bill["bill_discount_reason"])

    def test_slab_tier_boundaries(self):
        # qty 24 -> 3% slab: 2160 - 64.80 = 2095.20; auto 2% = 41.90; grand 2053.30
        resp = self._bill(
            lines=[{"product": self.product.id, "qty": "24"}],
            payments=[{"mode": "cash", "amount": "2053.30"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.json()["lines"][0]
        self.assertEqual(line["slab_discount_percent"], "3.00")
        self.assertEqual(line["discount_percent"], "3.00")
        self.assertEqual(line["line_total"], "2095.20")
        self.assertEqual(resp.json()["grand_total"], "2053.30")

        # qty 23 -> no slab
        resp = self._bill(
            lines=[{"product": self.product.id, "qty": "23"}],
            payments=[{"mode": "cash", "amount": "2028.60"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.json()["lines"][0]
        self.assertEqual(line["slab_discount_percent"], "0.00")
        self.assertEqual(line["line_total"], "2070.00")

        # qty 60 -> 5% slab: 5400 - 270 = 5130; auto 2% = 102.60; grand 5027.40
        resp = self._bill(
            lines=[{"product": self.product.id, "qty": "60"}],
            payments=[{"mode": "cash", "amount": "5027.40"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.json()["lines"][0]
        self.assertEqual(line["slab_discount_percent"], "5.00")
        self.assertEqual(resp.json()["grand_total"], "5027.40")

    def test_slab_and_manual_line_discount_not_stacked_max_wins(self):
        # manual 10% beats slab 3%: 2160 - 216 = 1944; auto 2% = 38.88
        resp = self._bill(
            lines=[{"product": self.product.id, "qty": "24", "discount_percent": "10"}],
            payments=[{"mode": "cash", "amount": "1905.12"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.json()["lines"][0]
        self.assertEqual(line["slab_discount_percent"], "3.00")  # informational
        self.assertEqual(line["discount_percent"], "10.00")  # winner
        self.assertEqual(line["line_total"], "1944.00")

        # manual 1% loses to slab 3%
        resp = self._bill(
            lines=[{"product": self.product.id, "qty": "24", "discount_percent": "1"}],
            payments=[{"mode": "cash", "amount": "2053.30"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        line = resp.json()["lines"][0]
        self.assertEqual(line["discount_percent"], "3.00")
        self.assertEqual(line["line_total"], "2095.20")

    def test_retail_bill_unaffected(self):
        resp = self._bill(
            customer=self.customer.id,  # retail customer from the base fixture
            payments=[{"mode": "cash", "amount": "200.00"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        self.assertEqual(bill["sale_type"], "retail")
        self.assertEqual(bill["lines"][0]["rate"], "100.00")
        self.assertEqual(bill["lines"][0]["slab_discount_percent"], "0.00")
        self.assertEqual(bill["bill_discount"], "0.00")
        self.assertEqual(bill["grand_total"], "200.00")

    def test_explicit_sale_type_retail_overrides_wholesale_customer(self):
        resp = self._bill(
            sale_type="retail",
            lines=[{"product": self.product.id, "qty": "24"}],
            payments=[{"mode": "cash", "amount": "2400.00"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        self.assertEqual(bill["sale_type"], "retail")
        self.assertEqual(bill["lines"][0]["rate"], "100.00")
        self.assertEqual(bill["lines"][0]["slab_discount_percent"], "0.00")
        self.assertEqual(bill["grand_total"], "2400.00")

    def test_wholesale_without_customer_no_auto_discount(self):
        payload = {
            "lines": [{"product": self.product.id, "qty": "2"}],
            "payments": [{"mode": "cash", "amount": "180.00"}],
            "sale_type": "wholesale",
            "shift": self.shift.id,
        }
        resp = self.client_for(self.cashier).post(BILL_URL, payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        self.assertEqual(bill["sale_type"], "wholesale")
        self.assertEqual(bill["lines"][0]["rate"], "90.00")
        self.assertEqual(bill["bill_discount"], "0.00")
        self.assertEqual(bill["grand_total"], "180.00")

    def test_wholesale_rate_falls_back_to_retail_when_unset(self):
        self.product.wholesale_price = Decimal("0")
        self.product.save(update_fields=["wholesale_price"])
        resp = self._bill(payments=[{"mode": "cash", "amount": "196.00"}])
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        # rate falls back to 100, but the 2% wholesale customer discount still applies
        self.assertEqual(bill["lines"][0]["rate"], "100.00")
        self.assertEqual(bill["bill_discount"], "4.00")
        self.assertEqual(bill["grand_total"], "196.00")

    def test_bill_discount_capped_at_50_percent(self):
        big = Customer.objects.create(
            tenant=self.tenant,
            name="Big Trader",
            phone="03007776666",
            customer_type=Customer.TYPE_WHOLESALE,
            wholesale_discount_percent=Decimal("40"),
        )
        # manual 20% + auto 40% would be 60% -> capped at 50%: 180 -> 90
        resp = self._bill(
            customer=big.id,
            bill_discount_percent="20",
            bill_discount_reason="promo",
            payments=[{"mode": "cash", "amount": "90.00"}],
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        bill = resp.json()
        self.assertEqual(bill["bill_discount"], "90.00")
        self.assertEqual(bill["grand_total"], "90.00")

    def test_wholesale_khata_credit_limit_enforced(self):
        client = self.client_for(self.cashier)
        # qty 2000 hits the 5% slab: 180000 - 9000 = 171000; auto 2% = 3420
        # -> 167580 on khata: within the 200000 limit
        resp = client.post(
            BILL_URL,
            {
                "lines": [{"product": self.product.id, "qty": "2000"}],
                "payments": [{"mode": "khata", "amount": "167580.00"}],
                "customer": self.ws_customer.id,
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        # qty 500: 45000 - 5% slab (2250) = 42750; auto 2% = 855 -> 41895.
        # 167580 + 41895 = 209475 > 200000 -> rejected
        resp = client.post(
            BILL_URL,
            {
                "lines": [{"product": self.product.id, "qty": "500"}],
                "payments": [{"mode": "khata", "amount": "41895.00"}],
                "customer": self.ws_customer.id,
                "shift": self.shift.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertIn("Credit limit exceeded", resp.json()["detail"])

    def test_invalid_sale_type_rejected(self):
        resp = self._bill(sale_type="bogus")
        self.assertEqual(resp.status_code, 400)

    # --- slabs API -------------------------------------------------------
    def test_slab_crud_and_unique_constraint(self):
        client = self.client_for(self.owner)
        # list
        resp = client.get(SLAB_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["results"]), 2)
        # create
        resp = client.post(
            SLAB_URL,
            {"product": self.product.id, "min_qty": "120", "discount_percent": "7"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["product_sku"], self.product.sku)
        # duplicate (tenant, product, min_qty) -> 400 via unique constraint
        resp = client.post(
            SLAB_URL,
            {"product": self.product.id, "min_qty": "24", "discount_percent": "9"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        # model-level unique constraint also raises IntegrityError
        with transaction.atomic(), self.assertRaises(IntegrityError):
            PriceSlab.objects.create(
                tenant=self.tenant,
                product=self.product,
                min_qty=Decimal("24"),
                discount_percent=Decimal("9"),
            )
        # cashier cannot create slabs (owner/manager only)
        resp = self.client_for(self.cashier).post(
            SLAB_URL,
            {"product": self.product.id, "min_qty": "200", "discount_percent": "8"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_slab_tenant_isolation(self):
        other_client = self.client_for(self.other_owner)
        # other tenant sees none of our slabs
        resp = other_client.get(SLAB_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["results"], [])
        # other tenant cannot create a slab on our product
        resp = other_client.post(
            SLAB_URL,
            {"product": self.product.id, "min_qty": "10", "discount_percent": "1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    # --- reports ---------------------------------------------------------
    def test_wholesale_summary_report(self):
        # one wholesale + one retail bill today
        self.assertEqual(self._bill().status_code, 201)
        self.assertEqual(
            self._bill(
                customer=self.customer.id,
                payments=[{"mode": "cash", "amount": "200.00"}],
            ).status_code,
            201,
        )
        resp = self.client_for(self.owner).get(SUMMARY_URL)
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["bills_count"], 1)
        self.assertEqual(data["total_sales"], "176.40")
        self.assertEqual(len(data["by_customer"]), 1)
        self.assertEqual(data["by_customer"][0]["name"], "Wholesale Trader")
        self.assertEqual(data["by_customer"][0]["total"], "176.40")
        self.assertEqual(data["top_items"][0]["sku"], self.product.sku)
        self.assertEqual(Decimal(data["top_items"][0]["qty"]), Decimal("2"))
        # margin: 176.40 - 2 x 80 (purchase price) = 16.40
        self.assertEqual(data["margin_estimate"], "16.40")
        # customer filter
        resp = self.client_for(self.owner).get(
            SUMMARY_URL, {"customer": self.customer.id}
        )
        self.assertEqual(resp.json()["bills_count"], 0)
