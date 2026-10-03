from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BrandViewSet,
    CategoryViewSet,
    PriceSlabViewSet,
    ProductBarcodeViewSet,
    ProductViewSet,
)

router = DefaultRouter()
router.register(r"catalog/categories", CategoryViewSet, basename="category")
router.register(r"catalog/brands", BrandViewSet, basename="brand")
router.register(r"catalog/products", ProductViewSet, basename="product")
router.register(r"catalog/product-barcodes", ProductBarcodeViewSet, basename="product-barcode")
router.register(r"catalog/price-slabs", PriceSlabViewSet, basename="price-slab")

urlpatterns = [path("", include(router.urls))]
