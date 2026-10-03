"""
Seed growth-module demo data for the Demo Mart tenant (idempotent).

- 2 promotions: bogo (buy 2 cooking oil, get 1 salt free) and weekend
  5% off bills over Rs 2000.
- Expense categories (Rent, Electricity, Salaries, Maintenance, Misc)
  + 3 sample expenses.
- 1 sample payout (needs/creates an open shift).

Usage: python manage.py seed_growth
Requires: python manage.py seed_demo  (tenant DM must exist)
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import Payout, Shift
from billing.services import create_payout
from catalog.models import Product
from expenses.models import Expense, ExpenseCategory
from promotions.models import Promotion
from tenants.models import Tenant, User

EXPENSE_CATEGORIES = ["Rent", "Electricity", "Salaries", "Maintenance", "Misc"]


class Command(BaseCommand):
    help = "Seed growth-module demo data (idempotent; needs tenant DM from seed_demo)"

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            tenant = Tenant.objects.get(code="DM")
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.WARNING("Tenant DM not found. Run seed_demo first.")
            )
            return

        oil = Product.objects.filter(
            tenant=tenant, barcode="8964000111011"
        ).first()
        salt = Product.objects.filter(
            tenant=tenant, barcode="8964000222017"
        ).first()

        # --- promotions ---
        if oil and salt:
            bogo, created = Promotion.objects.update_or_create(
                tenant=tenant,
                name="Buy 2 Oil, Get 1 Salt Free",
                defaults={
                    "promo_type": Promotion.TYPE_BOGO,
                    "buy_product": oil,
                    "buy_qty": Decimal("2"),
                    "get_product": salt,
                    "get_qty": Decimal("1"),
                    "is_active": True,
                    "priority": 10,
                },
            )
            self.stdout.write(f"  {'+' if created else '~'} bogo: {bogo.name}")
        weekend, created = Promotion.objects.update_or_create(
            tenant=tenant,
            name="Weekend 5% Off (Rs 2000+)",
            defaults={
                "promo_type": Promotion.TYPE_PERCENT,
                "discount_percent": Decimal("5"),
                "min_bill_amount": Decimal("2000"),
                "days_of_week": [5, 6],  # Saturday, Sunday
                "is_active": True,
                "priority": 5,
            },
        )
        self.stdout.write(f"  {'+' if created else '~'} percent: {weekend.name}")

        # --- expense categories + sample expenses ---
        cats = {}
        for name in EXPENSE_CATEGORIES:
            cat, created = ExpenseCategory.objects.get_or_create(
                tenant=tenant, name=name
            )
            cats[name] = cat
            if created:
                self.stdout.write(f"  + expense category: {name}")

        owner = User.objects.filter(tenant=tenant, role="owner").first()
        today = date.today()
        samples = [
            (cats["Electricity"], today, Decimal("8500"), "WAPDA bill"),
            (cats["Salaries"], today - timedelta(days=2), Decimal("45000"),
             "Cashier monthly salary"),
            (cats["Maintenance"], today - timedelta(days=5), Decimal("3200"),
             "Freezer repair"),
        ]
        for cat, day, amount, notes in samples:
            exp, created = Expense.objects.get_or_create(
                tenant=tenant,
                date=day,
                category=cat,
                amount=amount,
                defaults={
                    "payment_mode": Expense.MODE_CASH,
                    "notes": notes,
                    "created_by": owner,
                },
            )
            if created:
                self.stdout.write(f"  + expense: {cat.name} {amount} ({day})")

        # --- sample payout (needs an open shift) ---
        shift = Shift.objects.filter(
            tenant=tenant, status=Shift.STATUS_OPEN
        ).order_by("-opened_at").first()
        if shift is None and owner is not None:
            shift = Shift.objects.create(
                tenant=tenant, opened_by=owner, opening_cash=Decimal("20000")
            )
            self.stdout.write("  + opened a shift for the sample payout")
        if shift is not None and not Payout.objects.filter(
            tenant=tenant, purpose=Payout.PURPOSE_OTHER, notes="Seed sample payout"
        ).exists():
            create_payout(
                tenant=tenant,
                user=shift.opened_by,
                amount=Decimal("1500"),
                purpose=Payout.PURPOSE_OTHER,
                notes="Seed sample payout",
            )
            self.stdout.write("  + sample payout: 1500 (other)")

        self.stdout.write(
            self.style.SUCCESS("Growth seed complete (idempotent; safe to re-run).")
        )
