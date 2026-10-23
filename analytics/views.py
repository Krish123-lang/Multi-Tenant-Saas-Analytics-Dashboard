from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from datasets.models import Dataset
from organizations.models import Organization


class OrganizationAnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_id):
        organization = get_object_or_404(Organization.objects.filter(memberships__user=request.user).distinct(),pk=organization_id,)

        summary = Dataset.objects.filter(
            organization=organization
        ).aggregate(
            total_datasets=Count("id"),
            completed_datasets=Count(
                "id",
                filter=Q(status=Dataset.Status.COMPLETED),
            ),
            failed_datasets=Count(
                "id",
                filter=Q(status=Dataset.Status.FAILED),
            ),
            total_rows=Sum("row_count"),
        )

        return Response({
            "organization_id": organization.id,
            "organization_name": organization.name,
            "total_datasets": summary["total_datasets"],
            "completed_datasets": summary["completed_datasets"],
            "failed_datasets": summary["failed_datasets"],
            "total_rows": summary["total_rows"] or 0,
        })