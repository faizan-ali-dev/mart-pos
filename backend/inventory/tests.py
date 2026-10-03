from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError

from inventory.models import Batch, StockLocation
from inventory.services import apply_adjustment, receive_grn
from khata.models import LedgerEntry
from test_utils import POSTestCase


class GRNTests(POSTestCase):
    def test_grn_updates_weighted_average_cost(self):
        # 50 units @ 80 avg cost; receive 50 @ 100 -> avg 90, stock 100
        grn = receive_grn(
            tenant=self.tenant,
            supplier=self.supplier,
            location=self.location,
            lines=[{"product": self.product, "qty": Decimal("50"),
                    "purchase_rate": Decimal("100")}],
            received_by=self.owner,
        )
        self.assertEqual(grn.total_cost, Decimal("5000.00"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price, Decimal("90.00"))
        self.assertEqual(self.stock_qty(), Decimal("100"))

    def test_grn_first_stock_sets_cost(self):
        from catalog.models import Product

        new_product = Product.objects.create(
            tenant=self.tenant, sku="T-002", name="New Item",
            retail_price=Decimal("50"),
        )
        receive_grn(
            tenant=self.tenant, supplier=self.supplier, location=self.location,
            lines=[{"product": new_product, "qty": Decimal("10"),
                    "purchase_rate": Decimal("37.50")}],
            received_by=self.owner,
        )
        new_product.refresh_from_db()
        self.assertEqual(new_product.purchase_price, Decimal("37.50"))

    def test_grn_on_credit_creates_payable(self):
        receive_grn(
            tenant=self.tenant, supplier=self.supplier, location=self.location,
            lines=[{"product": self.product, "qty": Decimal("10"),
                    "purchase_rate": Decimal("80")}],
            on_credit=True, received_by=self.owner,
        )
        entry = LedgerEntry.objects.get(
            supplier=self.supplier, entry_type=LedgerEntry.ENTRY_PURCHASE
        )
        self.assertEqual(entry.amount, Decimal("800.00"))
        self.assertEqual(self.supplier.balance, Decimal("800.00"))

    def test_grn_creates_expiry_batch(self):
        from catalog.models import Product

        perishable = Product.objects.create(
            tenant=self.tenant, sku="T-003", name="Milk", retail_price=Decimal("200"),
            track_expiry=True,
        )
        expiry = date.today() + timedelta(days=45)
        receive_grn(
            tenant=self.tenant, supplier=self.supplier, location=self.location,
            lines=[{"product": perishable, "qty": Decimal("20"),
                    "purchase_rate": Decimal("180"), "expiry_date": expiry}],
            received_by=self.owner,
        )
        batch = Batch.objects.get(product=perishable)
        self.assertEqual(batch.expiry_date, expiry)
        self.assertEqual(batch.qty, Decimal("20"))

    def test_grn_api_applies_stock(self):
        client = self.client_for(self.manager)
        resp = client.post(
            "/api/inventory/grns/",
            {
                "supplier": self.supplier.id,
                "lines": [{"product": self.product.id, "qty": "10",
                           "purchase_rate": "90.00"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(self.stock_qty(), Decimal("60"))
        # weighted avg: (50*80 + 10*90)/60 = 81.67
        self.product.refresh_from_db()
        self.assertEqual(self.product.purchase_price, Decimal("81.67"))

    def test_cashier_cannot_receive_grn(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/inventory/grns/",
            {"supplier": self.supplier.id, "lines": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class AdjustmentTests(POSTestCase):
    def test_damage_adjustment_reduces_stock(self):
        adj = apply_adjustment(
            tenant=self.tenant, product=self.product, location=self.location,
            adjustment_type="damage", qty_change=Decimal("-5"),
            reason="broken packs", created_by=self.manager, approved_by=self.manager,
        )
        self.assertEqual(self.stock_qty(), Decimal("45"))
        self.assertEqual(adj.qty_change, Decimal("-5"))

    def test_negative_adjustment_needs_manager_approval(self):
        with self.assertRaises(ValidationError):
            apply_adjustment(
                tenant=self.tenant, product=self.product, location=self.location,
                adjustment_type="theft_loss", qty_change=Decimal("-5"),
                reason="missing", created_by=self.cashier,
                approved_by=self.cashier,  # cashier can't approve
            )

    def test_adjustment_below_zero_rejected(self):
        with self.assertRaises(ValidationError):
            apply_adjustment(
                tenant=self.tenant, product=self.product, location=self.location,
                adjustment_type="correction", qty_change=Decimal("-999"),
                reason="oops", created_by=self.owner, approved_by=self.owner,
            )
        self.assertEqual(self.stock_qty(), Decimal("50"))

    def test_found_stock_increases(self):
        apply_adjustment(
            tenant=self.tenant, product=self.product, location=self.location,
            adjustment_type="found_stock", qty_change=Decimal("7"),
            reason="found in godown", created_by=self.owner, approved_by=self.owner,
        )
        self.assertEqual(self.stock_qty(), Decimal("57"))


class AlertTests(POSTestCase):
    def test_low_stock_filter(self):
        client = self.client_for(self.owner)
        # stock 50, reorder 10 -> not low
        self.assertEqual(
            client.get("/api/inventory/stock-levels/?low_stock=true").json()["count"], 0
        )
        # drop to 5 -> low
        from inventory.services import deduct_stock
        from django.db import transaction

        with transaction.atomic():
            deduct_stock(self.tenant, self.product, Decimal("45"))
        resp = client.get("/api/inventory/stock-levels/?low_stock=true")
        self.assertEqual(resp.json()["count"], 1)

    def test_alerts_endpoint(self):
        client = self.client_for(self.owner)
        resp = client.get("/api/inventory/alerts/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("low_stock", resp.json())
        self.assertIn("expiring_soon", resp.json())

    def test_tenant_isolation_on_grns(self):
        client = self.client_for(self.other_owner)
        self.assertEqual(client.get("/api/inventory/grns/").json()["count"], 0)
