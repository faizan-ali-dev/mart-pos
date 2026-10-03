from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BatchViewSet,
    GRNViewSet,
    InventoryAlertsView,
    PurchaseOrderViewSet,
    StockAdjustmentViewSet,
    StockLevelViewSet,
    StockLocationViewSet,
)

router = DefaultRouter()
router.register(r"inventory/locations", StockLocationViewSet, basename="stock-location")
router.register(r"inventory/stock-levels", StockLevelViewSet, basename="stock-level")
router.register(r"inventory/purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register(r"inventory/grns", GRNViewSet, basename="grn")
router.register(r"inventory/adjustments", StockAdjustmentViewSet, basename="adjustment")
router.register(r"inventory/batches", BatchViewSet, basename="batch")

urlpatterns = [
    path("inventory/alerts/", InventoryAlertsView.as_view(), name="inventory-alerts"),
    path("", include(router.urls)),
]
