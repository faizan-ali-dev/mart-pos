from django.urls import path

from .views import DailySummaryView, WholesaleSummaryView

urlpatterns = [
    path("reports/daily-summary/", DailySummaryView.as_view(), name="daily-summary"),
    path(
        "reports/wholesale-summary/",
        WholesaleSummaryView.as_view(),
        name="wholesale-summary",
    ),
]
