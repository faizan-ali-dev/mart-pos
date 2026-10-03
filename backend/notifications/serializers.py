from rest_framework import serializers

from .models import MessageLog, NotificationRule, WhatsAppTemplate


class WhatsAppTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppTemplate
        fields = ("id", "tenant", "name", "language", "body", "is_active")
        read_only_fields = ("id",)


class MessageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageLog
        fields = (
            "id",
            "tenant",
            "to",
            "template",
            "event",
            "body",
            "status",
            "provider_response",
            "created_at",
        )
        read_only_fields = ("id", "tenant", "created_at")


class NotificationRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationRule
        fields = ("id", "tenant", "event", "enabled")
        read_only_fields = ("id", "tenant")


class SendTestSerializer(serializers.Serializer):
    to = serializers.CharField(max_length=30)
    message = serializers.CharField(required=False, allow_blank=True, default="Test message from Mart POS")
