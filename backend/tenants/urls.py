from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LoginView, MeView, StoreViewSet, TenantViewSet, UserViewSet, logout

router = DefaultRouter()
router.register(r"tenants/tenants", TenantViewSet, basename="tenant")
router.register(r"tenants/stores", StoreViewSet, basename="store")
router.register(r"tenants/users", UserViewSet, basename="tenant-user")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/logout/", logout, name="logout"),
    path("", include(router.urls)),
]
