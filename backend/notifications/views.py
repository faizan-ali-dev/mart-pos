from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.permissions import RolePermission, TenantScopedMixin

from .models import MessageLog, NotificationRule, WhatsAppTemplate
from .providers import send_whatsapp
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
    """POST /api/notifications/send-test/ {to, message} — logs via the provider."""

    permission_classes = [IsAuthenticated, RolePermission]
    allowed_roles = ("owner", "manager")

    def post(self, request):
        ser = SendTestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        if request.user.is_superuser:
            return Response({"detail": "Superusers have no tenant scope."}, status=400)
        log = send_whatsapp(
            tenant=request.user.tenant,
            to=ser.validated_data["to"],
            body=ser.validated_data["message"],
            event="send_test",
        )
        return Response(MessageLogSerializer(log).data, status=status.HTTP_201_CREATED)
