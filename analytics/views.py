from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from organizations.models import Organization

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from rest_framework import status
from datasets.models import Dataset, DatasetRecord
from organizations.models import Membership

from django.db.models import Avg, Count, Sum
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate


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
        
class DatasetAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id):
        dataset = (
            Dataset.objects.filter(
                pk=dataset_id,
                organization__memberships__user=request.user,
                status=Dataset.Status.COMPLETED,
            )
            .distinct()
            .first()
        )

        if dataset is None:
            return Response(
                {"detail": "Dataset not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        mapping = dataset.column_mapping

        if "amount" not in mapping:
            return Response(
                {
                    "detail": (
                        "Configure an amount column mapping "
                        "before requesting amount analytics."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount_column = mapping["amount"]
        category_column = mapping.get("category")

        total = Decimal("0")
        valid_count = 0
        categories = defaultdict(lambda: Decimal("0"))

        records = DatasetRecord.objects.filter(
            dataset=dataset
        ).values_list("data", flat=True)

        for row in records.iterator(chunk_size=1000):
            if amount_column not in row:
                return Response(
                    {"detail": "Mapped amount column was not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                amount = Decimal(str(row[amount_column]).strip())
            except (InvalidOperation, ValueError):
                return Response(
                    {
                        "detail": (
                            "The mapped amount column contains "
                            "a value that is not numeric."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not amount.is_finite():
                return Response(
                    {"detail": "Amount values must be finite numbers."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            total += amount
            valid_count += 1

            if category_column:
                category = str(row.get(category_column, "Uncategorized"))
                categories[category] += amount

        average = (
            total / valid_count if valid_count else Decimal("0")
        )

        return Response({
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "record_count": valid_count,
            "total_amount": str(total),
            "average_amount": str(average),
            "category_totals": {
                name: str(amount)
                for name, amount in categories.items()
            },
        })

class DatasetDatabaseAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id):
        dataset = (
            Dataset.objects.filter(pk=dataset_id,organization__memberships__user=request.user,status=Dataset.Status.COMPLETED,)
            .distinct()
            .first()
        )

        if dataset is None:
            return Response({"detail": "Dataset not found."},status=status.HTTP_404_NOT_FOUND,)

        mapping = dataset.column_mapping

        if "amount" not in mapping:
            return Response(
                {"detail": "Configure an amount column first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        records = dataset.records.all()

        # Reject records that have not been normalized.
        if records.filter(amount_value__isnull=True).exists():
            return Response(
                {
                    "detail": (
                        "Some records are not normalized. "
                        "Save the column mapping again."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = records.aggregate(record_count=Count("id"),total_amount=Sum("amount_value"),average_amount=Avg("amount_value"),)

        response = {
            "dataset_id": dataset.pk,
            "record_count": summary["record_count"],
            "total_amount": str(
                summary["total_amount"] or Decimal("0")
            ),
            "average_amount": str(
                summary["average_amount"] or Decimal("0")
            ),
        }

        if "category" in mapping:
            category_column = mapping["category"]

            category_totals = (
                records.annotate(
                    category_value=KeyTextTransform(
                        category_column,
                        "data",
                    )
                )
                .values("category_value")
                .annotate(total=Sum("amount_value"))
                .order_by("category_value")
            )

            response["category_totals"] = [
                {
                    "category": item["category_value"] or "Uncategorized",
                    "total": str(item["total"] or Decimal("0")),
                }
                for item in category_totals
            ]

        if "date" in mapping:
            daily_totals = (
                records.filter(transaction_date__isnull=False)
                .annotate(day=TruncDate("transaction_date"))
                .values("day")
                .annotate(total=Sum("amount_value"))
                .order_by("day")
            )

            response["daily_totals"] = [
                {
                    "date": item["day"].isoformat(),
                    "total": str(item["total"] or Decimal("0")),
                }
                for item in daily_totals
            ]

        return Response(response)