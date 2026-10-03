from django.db import models

from tenants.models import Tenant, User


class Customer(models.Model):
    """End customer with an udhaar (credit) account — receivables."""

    TYPE_RETAIL = "retail"
    TYPE_WHOLESALE = "wholesale"
    TYPE_CHOICES = (
        (TYPE_RETAIL, "Retail"),
        (TYPE_WHOLESALE, "Wholesale"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    cnic = models.CharField(max_length=20, blank=True)
    customer_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_RETAIL,
        help_text="Wholesale customers get wholesale rates + volume slabs",
    )
    wholesale_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Extra automatic bill-level discount for this wholesale customer",
    )
    credit_limit = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="0 = no limit set"
    )
    whatsapp_opt_in = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "phone"], name="uniq_customer_phone_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def balance(self):
        from django.db.models import Sum

        agg = LedgerEntry.objects.filter(customer=self).aggregate(total=Sum("amount"))
        return agg["total"] or 0


class Supplier(models.Model):
    """Goods supplier — payables."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    cnic = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uniq_supplier_name_per_tenant"
            )
        ]

    def __str__(self):
        return self.name

    @property
    def balance(self):
        from django.db.models import Sum

        agg = LedgerEntry.objects.filter(supplier=self).aggregate(total=Sum("amount"))
        return agg["total"] or 0


class LedgerEntry(models.Model):
    """
    One khata movement. Positive amount increases what is owed (receivable from a
    customer, or payable to a supplier); negative amount is a payment/adjustment.
    Exactly one of customer / supplier must be set.
    """

    ENTRY_SALE = "sale"  # credit sale to customer (receivable +)
    ENTRY_PAYMENT = "payment"  # payment received from customer / paid to supplier (-)
    ENTRY_PURCHASE = "purchase"  # credit purchase from supplier (payable +)
    ENTRY_PAY_ADJUST = "pay_adjust"  # manual correction, signed
    ENTRY_CHOICES = (
        (ENTRY_SALE, "Sale (credit)"),
        (ENTRY_PAYMENT, "Payment"),
        (ENTRY_PURCHASE, "Purchase (credit)"),
        (ENTRY_PAY_ADJUST, "Adjustment"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ledger_entries")
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.CASCADE, related_name="ledger_entries"
    )
    entry_type = models.CharField(max_length=20, choices=ENTRY_CHOICES)
    bill = models.ForeignKey(
        "billing.Bill",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ledger_entries",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    allocated_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="How much of this due has been settled (FIFO allocation)",
    )
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger_entries"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(customer__isnull=False, supplier__isnull=True)
                    | models.Q(customer__isnull=True, supplier__isnull=False)
                ),
                name="ledger_exactly_one_party",
            )
        ]
        ordering = ["created_at", "id"]

    def __str__(self):
        party = self.customer or self.supplier
        return f"{self.entry_type} {party} {self.amount:+}"

    @property
    def remaining(self):
        return self.amount - self.allocated_amount


class KhataPayment(models.Model):
    """A payment against khata dues, allocated FIFO to the oldest unpaid entries."""

    MODE_CASH = "cash"
    MODE_CARD = "card"
    MODE_BANK_TRANSFER = "bank_transfer"
    MODE_CHOICES = (
        (MODE_CASH, "Cash"),
        (MODE_CARD, "Card"),
        (MODE_BANK_TRANSFER, "Bank transfer"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="khata_payments"
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.CASCADE, related_name="khata_payments"
    )
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.CASCADE, related_name="khata_payments"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_CASH)
    reference = models.CharField(max_length=200, blank=True)
    allocation = models.JSONField(
        default=list,
        help_text="[{ledger_entry: id, allocated: amount}] in FIFO order",
    )
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="khata_payments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(customer__isnull=False, supplier__isnull=True)
                    | models.Q(customer__isnull=True, supplier__isnull=False)
                ),
                name="khatapayment_exactly_one_party",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        party = self.customer or self.supplier
        return f"Payment {self.amount} ({party})"
