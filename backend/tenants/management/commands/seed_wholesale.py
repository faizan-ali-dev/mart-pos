"""
Seed wholesale demo data for the existing Demo Mart tenant (idempotent).

- Marks "Kamran Sheikh" as a wholesale customer (credit limit 200000,
  automatic 2% bill-level discount).
- Sets wholesale_price (~3% below retail) and volume PriceSlabs on 5 products.

Usage: python manage.py seed_wholesale
Requires: python manage.py seed_demo  (tenant DM must exist)
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import PriceSlab, Product
from khata.models import Customer
from tenants.models import Tenant

# (barcode, wholesale_price, [(min_qty, discount_percent), ...])
SLAB_PRODUCTS = [
    ("8964000111011", 525, [(24, 3), (60, 5)]),      # Dalda Cooking Oil 1 Litre
    ("8964000111028", 572, [(24, 3), (60, 5)]),      # Dalda Banaspati Ghee 1 KG
    ("8964000444019", 1532, [(12, 2), (36, 4)]),     # Tapal Danedar Tea 950g
    ("8964000777017", 194, [(24, 2), (48, 4)]),      # Coca-Cola 1.5 Litre
    ("8964000222017", 116, [(50, 2), (100, "3.5")]),  # National Iodized Salt 800g
]


class Command(BaseCommand):
    help = "Seed wholesale demo data (idempotent; needs tenant DM from seed_demo)"

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            tenant = Tenant.objects.get(code="DM")
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.WARNING("Tenant DM not found. Run seed_demo first.")
            )
            return

        customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            phone="0300-4445566",
            defaults={"name": "Kamran Sheikh", "address": "Shop 4, Main Bazaar"},
        )
        customer.customer_type = Customer.TYPE_WHOLESALE
        customer.credit_limit = Decimal("200000")
        customer.wholesale_discount_percent = Decimal("2")
        customer.save(
            update_fields=[
                "customer_type",
                "credit_limit",
                "wholesale_discount_percent",
            ]
        )
        self.stdout.write(f"Wholesale customer: {customer.name} ({customer.phone})")

        for barcode, ws_price, tiers in SLAB_PRODUCTS:
            product = Product.objects.filter(tenant=tenant, barcode=barcode).first()
            if product is None:
                self.stdout.write(
                    self.style.WARNING(f"Product with barcode {barcode} not found; skipping.")
                )
                continue
            product.wholesale_price = Decimal(str(ws_price))
            product.save(update_fields=["wholesale_price"])
            for min_qty, pct in tiers:
                slab, created = PriceSlab.objects.update_or_create(
                    tenant=tenant,
                    product=product,
                    min_qty=Decimal(str(min_qty)),
                    defaults={"discount_percent": Decimal(str(pct))},
                )
                self.stdout.write(
                    f"  {'+' if created else '~'} {product.sku}: "
                    f">= {min_qty} -> {pct}%"
                )

        self.stdout.write(
            self.style.SUCCESS("Wholesale seed complete (idempotent; safe to re-run).")
        )
