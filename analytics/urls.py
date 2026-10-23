from django.urls import path

from .views import OrganizationAnalyticsSummaryView, DatasetAnalyticsView

urlpatterns = [
    path("organizations/<int:organization_id>/summary/", OrganizationAnalyticsSummaryView.as_view(),name="organization-analytics-summary",),
    path("datasets/<int:dataset_id>/summary/",DatasetAnalyticsView.as_view(),name="dataset-analytics-summary",),
]