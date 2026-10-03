from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BillViewSet, ParkedBillViewSet, ReturnViewSet, ShiftViewSet

router = DefaultRouter()
router.register(r"billing/bills", BillViewSet, basename="bill")
router.register(r"billing/parked-bills", ParkedBillViewSet, basename="parked-bill")
router.register(r"billing/returns", ReturnViewSet, basename="return")
router.register(r"billing/shifts", ShiftViewSet, basename="shift")

urlpatterns = [path("", include(router.urls))]
