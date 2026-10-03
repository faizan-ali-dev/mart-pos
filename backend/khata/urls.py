from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AgingReportView,
    CustomerViewSet,
    KhataPaymentViewSet,
    LedgerEntryViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register(r"khata/customers", CustomerViewSet, basename="customer")
router.register(r"khata/suppliers", SupplierViewSet, basename="supplier")
router.register(r"khata/ledger", LedgerEntryViewSet, basename="ledger-entry")
router.register(r"khata/payments", KhataPaymentViewSet, basename="khata-payment")

urlpatterns = [
    path("khata/aging/", AgingReportView.as_view(), name="khata-aging"),
    path("", include(router.urls)),
]
