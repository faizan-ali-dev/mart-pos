import os

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import TenantSettings
from tenants.permissions import RolePermission, TenantScopedMixin

from .models import MessageLog, NotificationRule, WhatsAppTemplate
from .providers import get_provider, send_whatsapp
from .serializers import (
    MessageLogSerializer,
    NotificationRuleSerializer,
    SendTestSerializer,
    WhatsAppTemplateSerializer,
)


class WhatsAppTemplateViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = WhatsAppTemplate.objects.all().order_by("name", "language")
    serializer_class = WhatsAppTemplateSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def get_queryset(self):
        # Templates are global (tenant=null) or belong to my tenant.
        qs = WhatsAppTemplate.objects.all().order_by("name", "language")
        user = self.request.user
        if user.is_superuser:
            return qs
        from django.db.models import Q

        return qs.filter(Q(tenant__isnull=True) | Q(tenant=user.tenant))


class MessageLogViewSet(TenantScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = MessageLog.objects.all()
    serializer_class = MessageLogSerializer
    permission_classes = [IsAuthenticated]


class NotificationRuleViewSet(TenantScopedMixin, viewsets.ModelViewSet):
    queryset = NotificationRule.objects.all().order_by("event")
    serializer_class = NotificationRuleSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")


class SendTestView(APIView):
    """POST /api/notifications/send-test/ {to, message}.

    Uses the tenant's configured provider (Settings → WhatsApp). When test
    mode is on and a test number is set, the recipient is FORCED to the test
    number so a real customer can never receive a test message.
    Returns {ok, provider, to, forced_to_test_number, detail, log_id}.
    """

    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def post(self, request):
        ser = SendTestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        tenant = request.user.tenant
        settings, _ = TenantSettings.objects.get_or_create(tenant=tenant)

        db_meta = settings.whatsapp_mode == TenantSettings.MODE_META
        db_creds = bool(
            settings.whatsapp_phone_number_id and settings.whatsapp_access_token
        )
        env_meta = (
            os.environ.get("WHATSAPP_PROVIDER", "dummy") == "meta"
            and os.environ.get("WHATSAPP_TOKEN")
            and os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        )
        if db_meta and not db_creds and not env_meta:
            return Response(
                {
                    "detail": "WhatsApp mode is 'meta' but the phone number ID / "
                    "access token are missing. Add them in Settings → WhatsApp."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        to = ser.validated_data["to"]
        forced = False
        if settings.whatsapp_test_mode and settings.whatsapp_test_number:
            to = settings.whatsapp_test_number
            forced = True

        provider = get_provider(tenant)
        log = send_whatsapp(
            tenant=tenant,
            to=to,
            body=ser.validated_data["message"],
            event="send_test",
        )
        return Response(
            {
                "ok": log.status != MessageLog.STATUS_FAILED,
                "provider": provider.name,
                "to": log.to,
                "forced_to_test_number": forced,
                "detail": f"Message logged as '{log.status}'.",
                "log_id": log.id,
            },
            status=status.HTTP_201_CREATED,
        )
