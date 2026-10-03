from django.contrib import admin

from tenants.admin import TenantScopedAdmin

from .models import MessageLog, NotificationRule, WhatsAppTemplate


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "language", "tenant", "is_active")
    list_filter = ("language", "is_active")
    search_fields = ("name", "body")


@admin.register(MessageLog)
class MessageLogAdmin(TenantScopedAdmin):
    list_display = ("id", "event", "to", "status", "tenant", "created_at")
    list_filter = ("tenant", "event", "status")
    search_fields = ("to", "body")
    readonly_fields = ("provider_response",)


@admin.register(NotificationRule)
class NotificationRuleAdmin(TenantScopedAdmin):
    list_display = ("event", "tenant", "enabled")
    list_filter = ("tenant", "event", "enabled")
