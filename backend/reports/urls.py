from django.urls import path

from .views import (
    DailySummaryView,
    ProfitReportView,
    PurchasesReportView,
    SalesReportView,
    WholesaleSummaryView,
)

urlpatterns = [
    path("reports/daily-summary/", DailySummaryView.as_view(), name="daily-summary"),
    path(
        "reports/wholesale-summary/",
        WholesaleSummaryView.as_view(),
        name="wholesale-summary",
    ),
    path("reports/sales/", SalesReportView.as_view(), name="sales-report"),
    path("reports/purchases/", PurchasesReportView.as_view(), name="purchases-report"),
    path("reports/profit/", ProfitReportView.as_view(), name="profit-report"),
]
