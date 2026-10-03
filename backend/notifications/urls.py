from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    MessageLogViewSet,
    NotificationRuleViewSet,
    SendTestView,
    WhatsAppTemplateViewSet,
)

router = DefaultRouter()
router.register(r"notifications/templates", WhatsAppTemplateViewSet, basename="wa-template")
router.register(r"notifications/messages", MessageLogViewSet, basename="wa-message")
router.register(r"notifications/rules", NotificationRuleViewSet, basename="wa-rule")

urlpatterns = [
    path("notifications/send-test/", SendTestView.as_view(), name="wa-send-test"),
    path("", include(router.urls)),
]
