"""
Seed a demo tenant with realistic Pakistani mart data.

Creates: Tenant "Demo Mart" (code DM), Store "Main Branch",
users owner/manager/cashier (password: demo123 -- DEV ONLY),
superuser admin/admin123 (DEV ONLY), categories, brands, ~15 products,
one supplier, two customers, opening stock via GRN, notification rules,
templates, and one open shift.

Usage: python manage.py seed_demo
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import Shift
from catalog.models import Brand, Category, Product
from inventory.models import StockLocation
from inventory.services import receive_grn
from khata.models import Customer, Supplier
from notifications.models import NotificationRule, WhatsAppTemplate
from tenants.models import Store, Tenant, User

DEV_PASSWORD = "demo123"

# (name, name_urdu, category, brand, unit, barcode, purchase, retail, reorder, track_expiry)
PRODUCTS = [
    ("Dalda Cooking Oil 1 Litre", "ڈالڈا کوکنگ آئل 1 لیٹر", "Grocery", "Dalda", "litre", "8964000111011", 480, 540, 20, False),
    ("Dalda Banaspati Ghee 1 KG", "ڈالڈا بناسپتی گھی 1 کلو", "Grocery", "Dalda", "kg", "8964000111028", 520, 590, 20, False),
    ("National Iodized Salt 800g", "نیشنل نمک 800 گرام", "Grocery", "National", "pcs", "8964000222017", 95, 120, 50, False),
    ("National Tomato Ketchup 800g", "نیشنل ٹماٹو کیچپ 800 گرام", "Grocery", "National", "pcs", "8964000222024", 320, 370, 30, False),
    ("Shan Biryani Masala 50g", "شان بریانی مصالحہ 50 گرام", "Spices", "Shan", "pcs", "8964000333013", 110, 140, 60, False),
    ("Shan Chicken Tikka Masala 50g", "شان چکن ٹکا مصالحہ 50 گرام", "Spices", "Shan", "pcs", "8964000333020", 110, 140, 60, False),
    ("Tapal Danedar Tea 950g", "ٹاپل دانے دار چائے 950 گرام", "Grocery", "Tapal", "pcs", "8964000444019", 1450, 1580, 15, False),
    ("Tapal Tezdum 190g", "ٹاپل تیز دم 190 گرام", "Grocery", "Tapal", "pcs", "8964000444026", 320, 360, 30, False),
    ("Nestle Everyday Powder 800g", "نیسلے ایوری ڈے 800 گرام", "Dairy", "Nestle", "pcs", "8964000555015", 1650, 1780, 15, True),
    ("Nestle Pure Life Water 1.5L", "نیسلے پیور لائف پانی 1.5 لیٹر", "Beverages", "Nestle", "pcs", "8964000555022", 110, 130, 60, False),
    ("Olpers Milk 1 Litre", "اولپرز دودھ 1 لیٹر", "Dairy", "Olpers", "pcs", "8964000666011", 195, 220, 40, True),
    ("Coca-Cola 1.5 Litre", "کوکا کولا 1.5 لیٹر", "Beverages", "Coca-Cola", "pcs", "8964000777017", 175, 200, 60, False),
    ("Sunlight Washing Powder 1KG", "سن لائٹ واشنگ پاؤڈر 1 کلو", "Household", "Unilever", "pcs", "8964000888014", 380, 430, 30, False),
    ("Lux Soap 140g", "لکس صابن 140 گرام", "Household", "Unilever", "pcs", "8964000888021", 145, 170, 60, False),
    ("Basmati Rice 5KG", "باسمتی چاول 5 کلو", "Grocery", "Falak", "pcs", "8964000999010", 1750, 1950, 10, False),
    ("Farm Eggs (Dozen)", "فارمی انڈے (درجن)", "Dairy", "Farm Fresh", "pcs", "8964000101016", 340, 390, 30, True),
]

CATEGORIES = ["Grocery", "Beverages", "Dairy", "Spices", "Household", "Snacks"]
BRANDS = ["Dalda", "National", "Shan", "Tapal", "Nestle", "Olpers", "Coca-Cola",
          "Unilever", "Falak", "Farm Fresh"]

TEMPLATES = [
    ("bill_receipt", "en",
     "Thank you for shopping at {shop_name}! Bill {bill_no}: Rs {total}. {khata_line}"),
    ("bill_receipt", "ur",
     "{shop_name} سے خریداری کا شکریہ! بل {bill_no}: روپے {total}۔ {khata_line}"),
    ("khata_reminder", "en",
     "Assalam-o-Alaikum {name}, your outstanding balance at {shop_name} is Rs {balance}. Please pay at your convenience."),
    ("khata_reminder", "ur",
     "السلام علیکم {name}، {shop_name} میں آپ کا بقایا روپے {balance} ہے۔ براہ کرم ادائیگی فرما دیں۔"),
    ("day_close", "en",
     "Day summary {date}: {bills_count} bills, total Rs {total_sales} (cash {cash}, card {card}, khata {khata})."),
]


class Command(BaseCommand):
    help = "Seed demo tenant data (dev only)"

    @transaction.atomic
    def handle(self, *args, **options):
        if Tenant.objects.filter(code="DM").exists():
            self.stdout.write(self.style.WARNING("Demo data already exists (tenant DM). Skipping."))
            return

        tenant = Tenant.objects.create(
            name="Demo Mart", code="DM", phone="0300-1234567",
            address="Main Bazaar Road, Lahore",
        )
        store = Store.objects.create(
            tenant=tenant, name="Main Branch", address="Main Bazaar Road, Lahore",
            phone="0300-1234567",
        )

        # Users (DEV ONLY passwords)
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin123")
        owner = User.objects.create_user("owner", password=DEV_PASSWORD, role="owner",
                                         tenant=tenant, store=store,
                                         first_name="Demo", last_name="Owner")
        manager = User.objects.create_user("manager", password=DEV_PASSWORD, role="manager",
                                           tenant=tenant, store=store,
                                           first_name="Demo", last_name="Manager")
        cashier = User.objects.create_user("cashier", password=DEV_PASSWORD, role="cashier",
                                           tenant=tenant, store=store,
                                           first_name="Demo", last_name="Cashier")

        categories = {c: Category.objects.create(tenant=tenant, name=c) for c in CATEGORIES}
        brands = {b: Brand.objects.create(tenant=tenant, name=b) for b in BRANDS}

        products = []
        for (name, name_urdu, cat, brand, unit, barcode, purchase, retail,
             reorder, track_expiry) in PRODUCTS:
            # save() one-by-one so the auto-SKU logic in Product.save() runs
            # (bulk_create would bypass it and violate the unique SKU constraint).
            products.append(Product.objects.create(
                tenant=tenant, name=name, name_urdu=name_urdu,
                category=categories[cat], brand=brands[brand], unit=unit,
                barcode=barcode, purchase_price=Decimal(purchase),
                retail_price=Decimal(retail), reorder_level=Decimal(reorder),
                track_expiry=track_expiry,
            ))

        shop_floor = StockLocation.objects.create(
            tenant=tenant, name="Shop Floor", location_type=StockLocation.SHOP_FLOOR)
        StockLocation.objects.create(
            tenant=tenant, name="Godown", location_type=StockLocation.GODOWN)

        supplier = Supplier.objects.create(
            tenant=tenant, name="Metro Distributors", phone="0321-9876543",
            address="Wholesale Market, Lahore")
        Customer.objects.create(
            tenant=tenant, name="Bilal Ahmed", phone="0300-1112233",
            address="House 12, Model Town", credit_limit=Decimal("20000"))
        Customer.objects.create(
            tenant=tenant, name="Kamran Sheikh", phone="0300-4445566",
            address="Shop 4, Main Bazaar", credit_limit=Decimal("5000"))

        # Opening stock via GRN (also sets weighted-average cost + expiry batches)
        lines = []
        for i, p in enumerate(products):
            qty = Decimal(50 + (i * 7) % 120)
            entry = {"product": p, "qty": qty, "purchase_rate": p.purchase_price}
            if p.track_expiry:
                entry["expiry_date"] = date.today() + timedelta(days=60 + (i * 13) % 200)
            lines.append(entry)
        receive_grn(
            tenant=tenant, supplier=supplier, location=shop_floor, lines=lines,
            supplier_invoice_no="OPENING-001", on_credit=False,
            notes="Opening stock", received_by=owner,
        )

        for event, _ in NotificationRule.EVENT_CHOICES:
            NotificationRule.objects.create(tenant=tenant, event=event, enabled=True)
        for name, lang, body in TEMPLATES:
            WhatsAppTemplate.objects.create(
                tenant=None, name=name, language=lang, body=body, is_active=True)

        Shift.objects.create(tenant=tenant, store=store, opened_by=cashier,
                             opening_cash=Decimal("5000"))

        self.stdout.write(self.style.SUCCESS(
            "Seeded Demo Mart: 16 products, 1 supplier, 2 customers, opening stock, "
            "open shift. Logins (dev only): owner/manager/cashier -> demo123, "
            "superuser admin -> admin123."
        ))
