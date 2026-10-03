from django.db import models

from tenants.models import Tenant


class Category(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=200)
    name_urdu = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uniq_category_name_per_tenant"
            )
        ]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Brand(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="brands")
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_brand_name_per_tenant")
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    UNIT_PCS = "pcs"
    UNIT_KG = "kg"
    UNIT_LITRE = "litre"
    UNIT_CHOICES = (
        (UNIT_PCS, "Pieces"),
        (UNIT_KG, "Kilogram"),
        (UNIT_LITRE, "Litre"),
    )

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="products")
    sku = models.CharField(
        max_length=64, help_text="Internal SKU; auto-generated if left blank"
    )
    barcode = models.CharField(
        max_length=64, blank=True, help_text="Manufacturer barcode (EAN-13 etc.)"
    )
    name = models.CharField(max_length=255)
    name_urdu = models.CharField(max_length=255, blank=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default=UNIT_PCS)
    purchase_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="Weighted-average cost"
    )
    retail_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wholesale_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="Used by the Phase-2 wholesale module"
    )
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    track_expiry = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], name="uniq_sku_per_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "barcode"],
                name="uniq_barcode_per_tenant",
                condition=~models.Q(barcode=""),
            ),
        ]

    def __str__(self):
        return f"{self.sku} — {self.name}"

    def save(self, *args, **kwargs):
        if not self.sku:
            # Auto-generate a simple internal SKU; refined to be unique per tenant.
            base = (self.name[:3] or "PRD").upper()
            existing = (
                Product.objects.filter(tenant=self.tenant, sku__startswith=base).count()
                if self.tenant_id
                else 0
            )
            self.sku = f"{base}-{existing + 1:04d}"
        super().save(*args, **kwargs)


class ProductBarcode(models.Model):
    """Extra barcodes (e.g. supplier barcodes) mapping to one product."""

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="product_barcodes"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="extra_barcodes"
    )
    barcode = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "barcode"], name="uniq_extra_barcode_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.barcode} -> {self.product.sku}"


class PriceSlab(models.Model):
    """
    Volume discount tier for wholesale pricing: buying >= min_qty units of the
    product earns discount_percent off the wholesale rate.

    The applicable slab for a bill line is the one with the highest min_qty
    that is still <= the line quantity. Slab and manual line discounts are
    NOT stacked — the larger of the two wins (see billing.services).
    """

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="price_slabs"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="price_slabs"
    )
    min_qty = models.DecimalField(
        max_digits=12, decimal_places=3, help_text="Slab activates at this quantity"
    )
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product", "min_qty"],
                name="uniq_price_slab_per_tenant_product_qty",
            )
        ]
        ordering = ["product__name", "min_qty"]

    def __str__(self):
        return f"{self.product.sku} >= {self.min_qty}: {self.discount_percent}%"
