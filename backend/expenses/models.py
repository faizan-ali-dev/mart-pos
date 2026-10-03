"""Dukaan ka kharcha: rent, bijli, salaries — taake maalik ko asal profit nazar aaye."""
from django.db import models

from tenants.models import Tenant, User


class ExpenseCategory(models.Model):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="expense_categories"
    )
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uniq_expense_category_per_tenant"
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.tenant.code})"


class Expense(models.Model):
    MODE_CASH = "cash"
    MODE_CARD = "card"
    MODE_BANK_TRANSFER = "bank_transfer"
    MODE_CHOICES = (
        (MODE_CASH, "Cash"),
        (MODE_CARD, "Card"),
        (MODE_BANK_TRANSFER, "Bank transfer"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="expenses"
    )
    date = models.DateField(help_text="The day the expense belongs to")
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_mode = models.CharField(
        max_length=20, choices=MODE_CHOICES, default=MODE_CASH
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.category.name} {self.amount} ({self.date})"
