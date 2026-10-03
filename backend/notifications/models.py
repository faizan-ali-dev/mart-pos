from django.db import models

from tenants.models import Tenant


class WhatsAppTemplate(models.Model):
    LANG_EN = "en"
    LANG_UR = "ur"
    LANG_CHOICES = ((LANG_EN, "English"), (LANG_UR, "Urdu"))

    tenant = models.ForeignKey(
        Tenant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="whatsapp_templates",
        help_text="Null = global template available to every tenant",
    )
    name = models.CharField(max_length=100, help_text="e.g. bill_receipt")
    language = models.CharField(max_length=5, choices=LANG_CHOICES, default=LANG_EN)
    body = models.TextField(help_text="Use {placeholders}, e.g. {bill_no}, {total}")
    meta_template_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Approved Meta template name, e.g. bill_receipt. When set and the "
        "tenant uses the Meta provider, sends go as this template instead of free text.",
    )
    meta_language = models.CharField(
        max_length=10,
        default="en",
        help_text="Meta template language code, e.g. en, ur.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "name", "language"], name="uniq_template_per_tenant"
            )
        ]

    def __str__(self):
        scope = self.tenant.code if self.tenant else "global"
        return f"{self.name} [{self.language}] ({scope})"


class MessageLog(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SIMULATED = "simulated"
    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SIMULATED, "Simulated (dev)"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="message_logs"
    )
    to = models.CharField(max_length=30, help_text="Recipient phone number")
    template = models.ForeignKey(
        WhatsAppTemplate, null=True, blank=True, on_delete=models.SET_NULL
    )
    event = models.CharField(max_length=50, help_text="e.g. bill_completed, day_close")
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    provider_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event} -> {self.to} ({self.status})"


class NotificationRule(models.Model):
    EVENT_BILL_COMPLETED = "bill_completed"
    EVENT_KHATA_PAYMENT = "khata_payment"
    EVENT_DUE_REMINDER = "due_reminder"
    EVENT_LOW_STOCK = "low_stock"
    EVENT_EXPIRY_ALERT = "expiry_alert"
    EVENT_DAY_CLOSE = "day_close"
    EVENT_CHOICES = (
        (EVENT_BILL_COMPLETED, "Bill completed"),
        (EVENT_KHATA_PAYMENT, "Khata payment received"),
        (EVENT_DUE_REMINDER, "Due / overdue reminder"),
        (EVENT_LOW_STOCK, "Low stock alert"),
        (EVENT_EXPIRY_ALERT, "Expiry alert"),
        (EVENT_DAY_CLOSE, "Day close summary"),
    )

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="notification_rules"
    )
    event = models.CharField(max_length=50, choices=EVENT_CHOICES)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "event"], name="uniq_rule_per_tenant")
        ]

    def __str__(self):
        return f"{self.event} ({'on' if self.enabled else 'off'})"
