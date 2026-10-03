from django.contrib.auth.models import AbstractUser
from django.db import models


class Tenant(models.Model):
    """One mart business = one tenant. Every other record is scoped to a tenant."""

    name = models.CharField(max_length=200)
    code = models.CharField(
        max_length=10, unique=True, help_text="Short code used in bill numbers, e.g. DM"
    )
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    bill_seq = models.PositiveIntegerField(
        default=0, help_text="Last used bill sequence number (incremented atomically)"
    )
    block_khata_over_limit = models.BooleanField(
        default=True,
        help_text="If true, credit sales that exceed a customer's credit limit are rejected",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Store(models.Model):
    """A physical branch/counter location inside a tenant."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="stores")
    name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name"], name="uniq_store_name_per_tenant"
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.tenant.code})"


class User(AbstractUser):
    """Custom user: every login belongs to a tenant and has a POS role."""

    ROLE_OWNER = "owner"
    ROLE_MANAGER = "manager"
    ROLE_CASHIER = "cashier"
    ROLE_CHOICES = (
        (ROLE_OWNER, "Owner"),
        (ROLE_MANAGER, "Manager"),
        (ROLE_CASHIER, "Cashier"),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_CASHIER)
    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="users",
        help_text="Null only for the global superuser",
    )
    store = models.ForeignKey(
        Store,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="users",
        help_text="Counter/branch this user normally works at",
    )
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return self.username

    @property
    def is_owner(self):
        return self.role == self.ROLE_OWNER

    @property
    def is_manager(self):
        return self.role == self.ROLE_MANAGER

    @property
    def is_cashier(self):
        return self.role == self.ROLE_CASHIER
