from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


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


class TenantSettings(models.Model):
    """Per-tenant app configuration, editable from Settings UI — no code/env changes.

    WhatsApp: the provider is chosen here (dummy for testing, meta for the
    official WhatsApp Business Cloud API). Test mode forces every send-test to
    the configured test number so real customers never get test messages.
    The access token is never logged and never returned in full via the API.
    """

    MODE_DUMMY = "dummy"
    MODE_META = "meta"
    MODE_CHOICES = (
        (MODE_DUMMY, "Simulated (dev / testing)"),
        (MODE_META, "Meta WhatsApp Cloud API"),
    )

    PRINT_THERMAL_80 = "thermal_80"
    PRINT_A4 = "a4"
    PRINT_CHOICES = (
        (PRINT_THERMAL_80, "Thermal 80mm receipt"),
        (PRINT_A4, "A4 invoice"),
    )

    tenant = models.OneToOneField(
        Tenant, on_delete=models.CASCADE, related_name="settings"
    )
    whatsapp_mode = models.CharField(
        max_length=10, choices=MODE_CHOICES, default=MODE_DUMMY
    )
    whatsapp_phone_number_id = models.CharField(max_length=50, blank=True)
    whatsapp_access_token = models.CharField(max_length=255, blank=True)
    whatsapp_test_mode = models.BooleanField(
        default=True,
        help_text="When on, send-test is forced to the test number below.",
    )
    whatsapp_test_number = models.CharField(max_length=30, blank=True)
    default_print_format = models.CharField(
        max_length=12, choices=PRINT_CHOICES, default=PRINT_THERMAL_80
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Settings ({self.tenant.code})"

    @property
    def token_masked(self) -> str:
        """Never expose the full token: '****' + last 4, or '' when unset."""
        if not self.whatsapp_access_token:
            return ""
        return "****" + self.whatsapp_access_token[-4:]


@receiver(post_save, sender=Tenant)
def _auto_create_tenant_settings(sender, instance, created, **kwargs):
    if created:
        TenantSettings.objects.get_or_create(tenant=instance)
