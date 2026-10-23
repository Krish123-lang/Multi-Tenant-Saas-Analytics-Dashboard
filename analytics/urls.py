from django.urls import path

from .views import OrganizationAnalyticsSummaryView

urlpatterns = [
    path("organizations/<int:organization_id>/summary/", OrganizationAnalyticsSummaryView.as_view(),name="organization-analytics-summary",),
]