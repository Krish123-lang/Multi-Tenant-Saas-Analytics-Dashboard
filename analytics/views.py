from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, render

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

from datetime import date, timedelta
from django.db.models import Q
from django.db.models.functions import Cast
from django.db.models import TextField

from rest_framework import generics
from rest_framework.exceptions import ValidationError

from .pagination import DatasetRecordPagination
from .serializers import DatasetRecordSerializer

from django.contrib.auth.decorators import login_required

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

class DatasetRecordListView(generics.ListAPIView):
    serializer_class = DatasetRecordSerializer
    pagination_class = DatasetRecordPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        dataset = get_object_or_404(
            Dataset.objects.filter(
                organization__memberships__user=self.request.user,
                status=Dataset.Status.COMPLETED,
            ).distinct(),
            pk=self.kwargs["dataset_id"],
        )

        queryset = DatasetRecord.objects.filter(
            dataset=dataset
        ).order_by("row_number")

        params = self.request.query_params
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        search = params.get("search", "").strip()

        if start_date:
            try:
                start = date.fromisoformat(start_date)
            except ValueError:
                raise ValidationError({
                    "start_date": "Use YYYY-MM-DD format."
                })

            queryset = queryset.filter(
                transaction_date__gte=start
            )

        if end_date:
            try:
                end = date.fromisoformat(end_date)
            except ValueError:
                raise ValidationError({
                    "end_date": "Use YYYY-MM-DD format."
                })

            queryset = queryset.filter(
                transaction_date__lte=end
            )

        if start_date and end_date and start > end:
            raise ValidationError({
                "date_range": (
                    "start_date must be on or before end_date."
                )
            })

        if search:
            # Search across the JSON representation of each CSV row.
            queryset = queryset.annotate(
                data_text=Cast("data", output_field=TextField())
            ).filter(
                Q(data_text__icontains=search)
            )

        return queryset
    
class DatasetTimeSeriesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, dataset_id):
        dataset = get_object_or_404(
            Dataset.objects.filter(
                organization__memberships__user=request.user,
                status=Dataset.Status.COMPLETED,
            ).distinct(),
            pk=dataset_id,
        )

        if not dataset.column_mapping.get("date"):
            raise ValidationError({
                "date": "Configure a date column mapping first."
            })

        if not dataset.column_mapping.get("amount"):
            raise ValidationError({
                "amount": "Configure an amount column mapping first."
            })

        try:
            start = date.fromisoformat(
                request.query_params["start_date"]
            )
            end = date.fromisoformat(
                request.query_params["end_date"]
            )
        except (KeyError, ValueError):
            raise ValidationError({
                "date_range": (
                    "Provide valid start_date and end_date "
                    "parameters in YYYY-MM-DD format."
                )
            })

        if start > end:
            raise ValidationError({
                "date_range": "start_date must not exceed end_date."
            })

        if (end - start).days > 365:
            raise ValidationError({
                "date_range": "The maximum range is 366 calendar days."
            })

        records = DatasetRecord.objects.filter(
            dataset=dataset,
            transaction_date__gte=start,
            transaction_date__lte=end,
        )

        # Do not silently produce misleading totals if normalization
        # has not been completed for all records in the date range.
        if records.filter(amount_value__isnull=True).exists():
            raise ValidationError({
                "amount": (
                    "Some records have not been normalized. "
                    "Reprocess or repair the dataset first."
                )
            })

        aggregates = (
            records.values("transaction_date")
            .annotate(
                total=Sum("amount_value"),
                record_count=Count("id"),
            )
            .order_by("transaction_date")
        )

        totals_by_date = {
            item["transaction_date"]: item
            for item in aggregates
        }

        labels = []
        totals = []
        counts = []

        current = start

        while current <= end:
            item = totals_by_date.get(current)

            labels.append(current.isoformat())
            totals.append(
                str(item["total"])
                if item and item["total"] is not None
                else "0"
            )
            counts.append(item["record_count"] if item else 0)

            current += timedelta(days=1)

        return Response({
            "dataset_id": dataset.pk,
            "period": {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            "labels": labels,
            "datasets": [
                {
                    "label": "Total amount",
                    "data": totals,
                },
                {
                    "label": "Record count",
                    "data": counts,
                },
            ],
        })

@login_required
def dashboard_page(request):
    organizations = Organization.objects.filter(memberships__user=request.user).distinct().order_by("name")

    datasets = Dataset.objects.filter(
        organization__memberships__user=request.user,
        status=Dataset.Status.COMPLETED,
    ).select_related("organization").distinct().order_by("-created_at")

    return render(request,"analytics/dashboard.html",
        {
            "organizations": organizations,
            "datasets": datasets,
        },
    )