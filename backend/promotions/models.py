"""Promotion engine: bogo, bundle, bill-level percent/flat discounts.

Promotions are evaluated inside the atomic bill-creation service. Only
promotions active *right now* (date range + weekday + time window) apply.
"""
from django.db import models

from catalog.models import Product
from tenants.models import Tenant


class Promotion(models.Model):
    TYPE_BOGO = "bogo"
    TYPE_BUNDLE = "bundle"
    TYPE_PERCENT = "percent"
    TYPE_FLAT = "flat"
    TYPE_CHOICES = (
        (TYPE_BOGO, "Buy X get Y free"),
        (TYPE_BUNDLE, "Bundle discount on two products"),
        (TYPE_PERCENT, "Bill-level percent off"),
        (TYPE_FLAT, "Bill-level flat amount off"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="promotions"
    )
    name = models.CharField(max_length=200)
    promo_type = models.CharField(max_length=10, choices=TYPE_CHOICES)

    # bogo / bundle configuration
    buy_product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="buy_promotions",
        help_text="bogo/bundle: the product the customer must buy",
    )
    buy_qty = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    get_product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="get_promotions",
        help_text="bogo: the free product; bundle: the second discounted product",
    )
    get_qty = models.DecimalField(max_digits=12, decimal_places=3, default=1)

    # discount configuration (bundle line % or bill-level)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    min_bill_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Bill-level promos only apply when subtotal >= this",
    )

    # scheduling
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    days_of_week = models.JSONField(
        default=list,
        blank=True,
        help_text="Weekdays the promo is active, 0=Monday..6=Sunday. Empty = every day.",
    )
    time_start = models.TimeField(null=True, blank=True)
    time_end = models.TimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=0,
        help_text="Higher priority wins ties between bill-level promos",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "name"]

    def __str__(self):
        return f"{self.name} ({self.promo_type})"

    def is_live(self, now) -> bool:
        """Is this promotion active at the given (aware) datetime?"""
        if not self.is_active:
            return False
        today = now.date()
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        if self.days_of_week and today.weekday() not in self.days_of_week:
            return False
        current = now.time()
        if self.time_start and current < self.time_start:
            return False
        if self.time_end and current > self.time_end:
            return False
        return True
