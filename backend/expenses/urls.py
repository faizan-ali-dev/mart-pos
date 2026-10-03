from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ExpenseCategoryViewSet, ExpenseSummaryView, ExpenseViewSet

router = DefaultRouter()
router.register(r"expenses/categories", ExpenseCategoryViewSet, basename="expense-category")
router.register(r"expenses/expenses", ExpenseViewSet, basename="expense")

urlpatterns = [
    path("", include(router.urls)),
    path("expenses/summary/", ExpenseSummaryView.as_view(), name="expense-summary"),
]
