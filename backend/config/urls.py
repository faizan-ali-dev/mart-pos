from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

admin.site.site_header = "Mart POS Admin"
admin.site.site_title = "Mart POS"
admin.site.index_title = "Administration"


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("tenants.urls")),
    path("api/", include("catalog.urls")),
    path("api/", include("inventory.urls")),
    path("api/", include("billing.urls")),
    path("api/", include("khata.urls")),
    path("api/", include("notifications.urls")),
    path("api/", include("reports.urls")),
    path("api/", include("expenses.urls")),
    path("api/", include("promotions.urls")),
]
