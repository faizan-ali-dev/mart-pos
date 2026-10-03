from decimal import Decimal

from django.core.exceptions import ValidationError

from khata.models import Customer, LedgerEntry
from khata.services import (
    aging_report,
    party_balance,
    record_khata_payment,
    record_receivable,
)
from test_utils import POSTestCase


class KhataPaymentTests(POSTestCase):
    def _two_dues(self):
        # oldest due 500, newer due 300
        record_receivable(
            tenant=self.tenant, customer=self.customer, amount=Decimal("500"),
            notes="first", created_by=self.owner,
        )
        record_receivable(
            tenant=self.tenant, customer=self.customer, amount=Decimal("300"),
            notes="second", created_by=self.owner,
        )

    def test_fifo_allocation(self):
        self._two_dues()
        payment = record_khata_payment(
            tenant=self.tenant, customer=self.customer, amount=Decimal("600"),
            mode="cash", reference="R-1", created_by=self.cashier,
        )
        alloc = payment.allocation
        self.assertEqual(len(alloc), 2)
        # oldest due fully settled first
        self.assertEqual(Decimal(alloc[0]["allocated"]), Decimal("500"))
        self.assertEqual(Decimal(alloc[1]["allocated"]), Decimal("100"))
        first = LedgerEntry.objects.get(notes="first")
        second = LedgerEntry.objects.get(notes="second")
        self.assertEqual(first.allocated_amount, Decimal("500"))
        self.assertEqual(second.allocated_amount, Decimal("100"))
        # balance: 800 dues - 600 payment = 200
        self.assertEqual(party_balance(self.tenant, customer=self.customer), Decimal("200"))

    def test_payment_exceeding_balance_rejected(self):
        self._two_dues()
        with self.assertRaises(ValidationError):
            record_khata_payment(
                tenant=self.tenant, customer=self.customer, amount=Decimal("9999"),
                created_by=self.cashier,
            )

    def test_exact_payment_clears_dues(self):
        self._two_dues()
        record_khata_payment(
            tenant=self.tenant, customer=self.customer, amount=Decimal("800"),
            created_by=self.cashier,
        )
        self.assertEqual(party_balance(self.tenant, customer=self.customer), Decimal("0"))

    def test_payment_api_applies_fifo(self):
        self._two_dues()
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/khata/payments/",
            {"customer": self.customer.id, "amount": "600.00", "mode": "cash"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(len(resp.json()["allocation"]), 2)

    def test_payment_needs_party(self):
        client = self.client_for(self.cashier)
        resp = client.post(
            "/api/khata/payments/", {"amount": "100.00"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_supplier_payment_fifo(self):
        from khata.services import record_payable

        record_payable(tenant=self.tenant, supplier=self.supplier,
                       amount=Decimal("1000"), created_by=self.owner)
        payment = record_khata_payment(
            tenant=self.tenant, supplier=self.supplier, amount=Decimal("400"),
            created_by=self.owner,
        )
        self.assertEqual(len(payment.allocation), 1)
        self.assertEqual(party_balance(self.tenant, supplier=self.supplier), Decimal("600"))

    def test_aging_report(self):
        self._two_dues()
        report = aging_report(self.tenant)
        self.assertEqual(len(report), 1)
        row = report[0]
        self.assertEqual(row["customer_name"], "Test Customer")
        self.assertEqual(row["total_due"], "800.00")
        self.assertEqual(row["buckets"]["0_30"], "800.00")

    def test_aging_api(self):
        self._two_dues()
        client = self.client_for(self.owner)
        resp = client.get("/api/khata/aging/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 1)

    def test_ledger_filter_by_customer(self):
        self._two_dues()
        client = self.client_for(self.owner)
        resp = client.get(f"/api/khata/ledger/?customer={self.customer.id}")
        self.assertEqual(resp.json()["count"], 2)

    def test_customer_balance_in_serializer(self):
        self._two_dues()
        client = self.client_for(self.owner)
        resp = client.get(f"/api/khata/customers/{self.customer.id}/")
        self.assertEqual(resp.json()["balance"], "800")
