from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from test_utils import POSTestCase

from billing.models import Bill
from catalog.models import Product
from inventory.models import StockLevel
from promotions.models import Promotion


class PromotionBillTests(POSTestCase):
    def setUp(self):
        super().setUp()
        self.salt = Product.objects.create(
            tenant=self.tenant,
            sku="T-002",
            name="Test Salt 800g",
            category=self.category,
            unit="pcs",
            purchase_price=Decimal("40"),
            retail_price=Decimal("50"),
            tax_percent=Decimal("0"),
        )
        StockLevel.objects.create(
            tenant=self.tenant, product=self.salt,
            location=self.location, qty=Decimal("20"),
        )

    def _bill(self, lines, payments=None, customer=None):
        client = self.client_for(self.cashier)
        if payments is None:
            payments = [{"mode": "cash", "amount": "100000.00"}]
        payload = {"lines": lines, "payments": payments, "shift": self.shift.id}
        if customer:
            payload["customer"] = customer
        resp = client.post("/api/billing/bills/", payload, format="json")
        # fix the payment to the exact total when we guessed wrong
        if resp.status_code == 400 and "must equal grand total" in str(resp.content):
            from decimal import Decimal as D
            import re
            m = re.search(r"grand total \(([0-9.]+)\)", resp.content.decode())
            total = m.group(1)
            payload["payments"] = [{"mode": "cash", "amount": total}]
            resp = client.post("/api/billing/bills/", payload, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        return resp.json()

    def _salt_stock(self):
        return StockLevel.objects.get(
            tenant=self.tenant, product=self.salt, location=self.location
        ).qty

    def _bogo(self, **kw):
        defaults = dict(
            tenant=self.tenant,
            name="BOGO test",
            promo_type=Promotion.TYPE_BOGO,
            buy_product=self.product,
            buy_qty=Decimal("2"),
            get_product=self.salt,
            get_qty=Decimal("1"),
            is_active=True,
        )
        defaults.update(kw)
        return Promotion.objects.create(**defaults)

    def test_bogo_adds_free_line_and_deducts_stock(self):
        self._bogo()
        bill = self._bill([{"product": self.product.id, "qty": "4"}])
        free_lines = [ln for ln in bill["lines"] if ln["is_free"]]
        self.assertEqual(len(free_lines), 1)
        free = free_lines[0]
        self.assertEqual(free["product"], self.salt.id)
        self.assertEqual(free["qty"], "2.000")  # 4 // 2 buy -> 2 free
        self.assertEqual(free["rate"], "0.00")
        self.assertEqual(free["line_total"], "0.00")
        # paid lines unaffected, grand total is just the 4 paid items
        self.assertEqual(bill["grand_total"], "400.00")
        self.assertEqual(self._salt_stock(), Decimal("18"))
        self.assertEqual(self.stock_qty(), Decimal("46"))
        promos = bill["applied_promotions"]
        self.assertEqual(len(promos), 1)
        self.assertEqual(promos[0]["type"], "bogo")

    def test_bogo_time_window_respected(self):
        now = timezone.now()
        self._bogo(
            name="Future promo",
            time_start=(now + timedelta(hours=2)).time(),
            time_end=(now + timedelta(hours=3)).time(),
        )
        bill = self._bill([{"product": self.product.id, "qty": "4"}])
        self.assertEqual(
            [ln for ln in bill["lines"] if ln["is_free"]], []
        )
        self.assertEqual(bill["applied_promotions"], [])
        self.assertEqual(self._salt_stock(), Decimal("20"))

    def test_bogo_wrong_weekday_ignored(self):
        tomorrow = (timezone.now().date().weekday() + 1) % 7
        self._bogo(name="Tomorrow promo", days_of_week=[tomorrow])
        bill = self._bill([{"product": self.product.id, "qty": "4"}])
        self.assertEqual([ln for ln in bill["lines"] if ln["is_free"]], [])
        self.assertEqual(bill["applied_promotions"], [])

    def test_best_bill_promo_wins_no_stacking(self):
        Promotion.objects.create(
            tenant=self.tenant, name="5pct", promo_type=Promotion.TYPE_PERCENT,
            discount_percent=Decimal("5"), min_bill_amount=Decimal("0"),
            priority=1,
        )
        Promotion.objects.create(
            tenant=self.tenant, name="10pct", promo_type=Promotion.TYPE_PERCENT,
            discount_percent=Decimal("10"), min_bill_amount=Decimal("0"),
            priority=0,
        )
        Promotion.objects.create(
            tenant=self.tenant, name="flat15", promo_type=Promotion.TYPE_FLAT,
            discount_amount=Decimal("15"), min_bill_amount=Decimal("0"),
            priority=9,
        )
        bill = self._bill([{"product": self.product.id, "qty": "2"}])  # subtotal 200
        # 10% of 200 = 20 beats flat 15 and 5%
        self.assertEqual(bill["bill_discount"], "20.00")
        self.assertEqual(bill["grand_total"], "180.00")
        promos = bill["applied_promotions"]
        self.assertEqual(len(promos), 1)
        self.assertEqual(promos[0]["name"], "10pct")

    def test_bill_promo_min_amount_respected(self):
        Promotion.objects.create(
            tenant=self.tenant, name="big", promo_type=Promotion.TYPE_PERCENT,
            discount_percent=Decimal("50"), min_bill_amount=Decimal("10000"),
        )
        bill = self._bill([{"product": self.product.id, "qty": "2"}])
        self.assertEqual(bill["bill_discount"], "0.00")
        self.assertEqual(bill["applied_promotions"], [])

    def test_bundle_takes_max_not_stack(self):
        Promotion.objects.create(
            tenant=self.tenant, name="bundle20", promo_type=Promotion.TYPE_BUNDLE,
            buy_product=self.product, buy_qty=Decimal("1"),
            get_product=self.salt, get_qty=Decimal("1"),
            discount_percent=Decimal("20"),
        )
        bill = self._bill(
            [
                {"product": self.product.id, "qty": "1", "discount_percent": "5"},
                {"product": self.salt.id, "qty": "1"},
            ]
        )
        by_sku = {ln["product_sku"]: ln for ln in bill["lines"]}
        # 20% bundle beats the 5% manual line discount (not stacked)
        self.assertEqual(by_sku["T-001"]["discount_amount"], "20.00")
        self.assertEqual(by_sku["T-001"]["line_total"], "80.00")
        self.assertEqual(by_sku["T-002"]["discount_amount"], "10.00")
        self.assertEqual(by_sku["T-002"]["line_total"], "40.00")
        self.assertEqual(bill["grand_total"], "120.00")
        self.assertTrue(
            any(p["type"] == "bundle" for p in bill["applied_promotions"])
        )

    def test_promo_capped_with_wholesale_discount(self):
        from khata.models import Customer

        ws_customer = Customer.objects.create(
            tenant=self.tenant, name="WS", phone="03009998888",
            customer_type=Customer.TYPE_WHOLESALE,
            wholesale_discount_percent=Decimal("48"),
            credit_limit=Decimal("100000"),
        )
        Promotion.objects.create(
            tenant=self.tenant, name="10pct", promo_type=Promotion.TYPE_PERCENT,
            discount_percent=Decimal("10"), min_bill_amount=Decimal("0"),
        )
        bill = self._bill(
            [{"product": self.product.id, "qty": "2"}],
            customer=ws_customer.id,
        )
        # 48% auto + 10% promo would be 58% -> capped at 50% of 200 = 100
        self.assertEqual(Bill.objects.get(pk=bill["id"]).bill_discount, Decimal("100.00"))
