"""Shared fixtures for the Mart POS test suite."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from billing.models import Shift
from catalog.models import Category, Product
from inventory.models import StockLevel, StockLocation
from khata.models import Customer, Supplier
from tenants.models import Store, Tenant, User


class POSTestCase(TestCase):
    """Two tenants, three roles, one stocked product, customer, supplier, open shift."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Mart", code="TM")
        self.other_tenant = Tenant.objects.create(name="Other Mart", code="OM")
        self.store = Store.objects.create(tenant=self.tenant, name="Main")
        self.owner = self._user("t_owner", "owner", self.tenant)
        self.manager = self._user("t_manager", "manager", self.tenant)
        self.cashier = self._user("t_cashier", "cashier", self.tenant)
        self.other_owner = self._user("o_owner", "owner", self.other_tenant)

        self.location = StockLocation.objects.create(
            tenant=self.tenant, name="Shop Floor",
            location_type=StockLocation.SHOP_FLOOR,
        )
        self.category = Category.objects.create(tenant=self.tenant, name="Grocery")
        self.product = Product.objects.create(
            tenant=self.tenant,
            sku="T-001",
            name="Test Tea 950g",
            category=self.category,
            unit="pcs",
            purchase_price=Decimal("80"),
            retail_price=Decimal("100"),
            tax_percent=Decimal("0"),
            reorder_level=Decimal("10"),
        )
        StockLevel.objects.create(
            tenant=self.tenant, product=self.product,
            location=self.location, qty=Decimal("50"),
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, name="Test Customer", phone="03001112222",
            credit_limit=Decimal("1000"),
        )
        self.supplier = Supplier.objects.create(tenant=self.tenant, name="Test Supplier")
        self.shift = Shift.objects.create(
            tenant=self.tenant, store=self.store, opened_by=self.cashier,
            opening_cash=Decimal("1000"),
        )

    def _user(self, username, role, tenant):
        return User.objects.create_user(
            username, password="pw123", role=role, tenant=tenant, store=self.store
            if tenant == self.tenant else None,
        )

    def client_for(self, user):
        client = APIClient()
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def stock_qty(self):
        return StockLevel.objects.get(
            tenant=self.tenant, product=self.product, location=self.location
        ).qty
