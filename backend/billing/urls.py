from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BillViewSet, ParkedBillViewSet, PayoutViewSet, ReturnViewSet, ShiftViewSet

router = DefaultRouter()
router.register(r"billing/bills", BillViewSet, basename="bill")
router.register(r"billing/parked-bills", ParkedBillViewSet, basename="parked-bill")
router.register(r"billing/returns", ReturnViewSet, basename="return")
router.register(r"billing/shifts", ShiftViewSet, basename="shift")
router.register(r"billing/payouts", PayoutViewSet, basename="payout")

urlpatterns = [path("", include(router.urls))]
