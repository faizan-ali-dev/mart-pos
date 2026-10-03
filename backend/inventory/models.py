from django.db import models

from catalog.models import Product
from tenants.models import Tenant, User


class StockLocation(models.Model):
    SHOP_FLOOR = "shop_floor"
    GODOWN = "godown"
    TYPE_CHOICES = (
        (SHOP_FLOOR, "Shop floor"),
        (GODOWN, "Godown"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="stock_locations"
    )
    name = models.CharField(max_length=200)
    location_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=SHOP_FLOOR)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uniq_location_name_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.code})"


class StockLevel(models.Model):
    """Quantity on hand of one product at one location."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="stock_levels")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stock_levels"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.CASCADE, related_name="stock_levels"
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "location"], name="uniq_stock_per_product_location"
            )
        ]

    def __str__(self):
        return f"{self.product.sku} @ {self.location.name}: {self.qty}"


class PurchaseOrder(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ORDERED = "ordered"
    STATUS_RECEIVED = "received"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_ORDERED, "Ordered"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="purchase_orders"
    )
    supplier = models.ForeignKey(
        "khata.Supplier", on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_orders"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PO-{self.id} ({self.supplier.name})"


class GRN(models.Model):
    """Goods Received Note — the moment stock (and cost) actually enters the shop."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="grns")
    supplier = models.ForeignKey(
        "khata.Supplier", on_delete=models.PROTECT, related_name="grns"
    )
    supplier_invoice_no = models.CharField(max_length=100, blank=True)
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="grns"
    )
    on_credit = models.BooleanField(
        default=False, help_text="If true, creates a supplier payable (khata) entry"
    )
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="grns"
    )
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"GRN-{self.id} ({self.supplier.name})"


class GRNLine(models.Model):
    grn = models.ForeignKey(GRN, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="grn_lines"
    )
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    purchase_rate = models.DecimalField(max_digits=12, decimal_places=2)
    expiry_date = models.DateField(null=True, blank=True)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.product.sku} x {self.qty}"


class StockAdjustment(models.Model):
    TYPE_DAMAGE = "damage"
    TYPE_EXPIRY = "expiry_writeoff"
    TYPE_THEFT = "theft_loss"
    TYPE_FOUND = "found_stock"
    TYPE_CORRECTION = "correction"
    TYPE_CHOICES = (
        (TYPE_DAMAGE, "Damage"),
        (TYPE_EXPIRY, "Expiry write-off"),
        (TYPE_THEFT, "Theft / loss"),
        (TYPE_FOUND, "Found stock"),
        (TYPE_CORRECTION, "Correction"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="stock_adjustments"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="adjustments"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="adjustments"
    )
    adjustment_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    qty_change = models.DecimalField(
        max_digits=12, decimal_places=3, help_text="Signed: negative removes stock"
    )
    reason = models.TextField()
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_adjustments",
        help_text="Manager/owner who approved a stock-reducing adjustment",
    )
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="adjustments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.adjustment_type} {self.product.sku} {self.qty_change:+}"


class Batch(models.Model):
    """Expiry-tracked stock lot (created from GRN lines of track_expiry products)."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="batches")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="batches")
    expiry_date = models.DateField()
    qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    grn_line = models.ForeignKey(
        GRNLine, null=True, blank=True, on_delete=models.SET_NULL, related_name="batches"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "batches"

    def __str__(self):
        return f"{self.product.sku} exp {self.expiry_date} ({self.qty})"
