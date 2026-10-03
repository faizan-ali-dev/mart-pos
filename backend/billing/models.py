from django.core.exceptions import ValidationError
from django.db import models

from catalog.models import Product
from tenants.models import Tenant, User


class Shift(models.Model):
    STATUS_OPEN = "open"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = ((STATUS_OPEN, "Open"), (STATUS_CLOSED, "Closed"))

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="shifts")
    store = models.ForeignKey(
        "tenants.Store",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="shifts",
    )
    opened_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="opened_shifts"
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Shift {self.id} ({self.opened_by.username}, {self.status})"


class Bill(models.Model):
    """
    A completed sale. IMMUTABLE: no updates or deletes are allowed once created
    (enforced at the model, API and admin layers) so offline sync never conflicts.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="bills")
    bill_no = models.CharField(max_length=30)
    shift = models.ForeignKey(
        Shift, null=True, blank=True, on_delete=models.SET_NULL, related_name="bills"
    )
    cashier = models.ForeignKey(User, on_delete=models.PROTECT, related_name="bills")
    customer = models.ForeignKey(
        "khata.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bills",
        help_text="Set for khata (credit) sales and WhatsApp receipts",
    )
    SALE_RETAIL = "retail"
    SALE_WHOLESALE = "wholesale"
    SALE_CHOICES = (
        (SALE_RETAIL, "Retail"),
        (SALE_WHOLESALE, "Wholesale"),
    )
    sale_type = models.CharField(
        max_length=10,
        choices=SALE_CHOICES,
        default=SALE_RETAIL,
        help_text="Wholesale bills use wholesale rates + volume price slabs",
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    bill_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bill_discount_reason = models.CharField(max_length=255, blank=True)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2)
    tendered = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    change_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "bill_no"], name="uniq_bill_no_per_tenant"
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Bill {self.bill_no}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Bills are immutable and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Bills are immutable and cannot be deleted.")


class BillLine(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="bill_lines")
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    slab_discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Volume slab that applied to this line (informational; "
        "discount_percent already reflects the winning discount)",
    )
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.sku} x {self.qty}"


class Payment(models.Model):
    MODE_CASH = "cash"
    MODE_CARD = "card"
    MODE_BANK_TRANSFER = "bank_transfer"
    MODE_KHATA = "khata"
    MODE_CHOICES = (
        (MODE_CASH, "Cash"),
        (MODE_CARD, "Card"),
        (MODE_BANK_TRANSFER, "Bank transfer"),
        (MODE_KHATA, "Khata (credit)"),
    )

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="payments")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.mode} {self.amount} ({self.bill.bill_no})"


class ParkedBill(models.Model):
    """A bill held mid-sale (customer forgot wallet etc.). Recalled later by token."""

    STATUS_PARKED = "parked"
    STATUS_RECALLED = "recalled"
    STATUS_VOIDED = "voided"
    STATUS_CHOICES = (
        (STATUS_PARKED, "Parked"),
        (STATUS_RECALLED, "Recalled"),
        (STATUS_VOIDED, "Voided"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="parked_bills")
    token = models.CharField(max_length=32, unique=True)
    payload = models.JSONField(help_text="Cart snapshot: lines, discounts, customer")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PARKED)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="parked_bills"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Parked {self.token} ({self.status})"


class Return(models.Model):
    """A return against a bill: restocks items and records the refund."""

    REFUND_CASH = "cash"
    REFUND_CARD = "card"
    REFUND_BANK_TRANSFER = "bank_transfer"
    REFUND_KHATA = "khata"
    REFUND_STORE_CREDIT = "store_credit"
    REFUND_CHOICES = (
        (REFUND_CASH, "Cash"),
        (REFUND_CARD, "Card"),
        (REFUND_BANK_TRANSFER, "Bank transfer"),
        (REFUND_KHATA, "Khata (reduce receivable)"),
        (REFUND_STORE_CREDIT, "Store credit"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="returns")
    bill = models.ForeignKey(Bill, on_delete=models.PROTECT, related_name="returns")
    reason = models.TextField()
    refund_mode = models.CharField(max_length=20, choices=REFUND_CHOICES)
    total_refund = models.DecimalField(max_digits=12, decimal_places=2)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="returns")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Return on {self.bill.bill_no} ({self.total_refund})"


class ReturnLine(models.Model):
    return_obj = models.ForeignKey(
        Return, on_delete=models.CASCADE, related_name="lines"
    )
    bill_line = models.ForeignKey(
        BillLine, on_delete=models.PROTECT, related_name="return_lines"
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    rate = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.sku} x {self.qty} returned"
