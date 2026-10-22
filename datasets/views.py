from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from organizations.models import Membership
from .models import Dataset
from .permissions import IsDatasetMember
from .serializers import DatasetSerializer

import logging
from django.db import transaction
from .models import Dataset
from .tasks import process_dataset

logger = logging.getLogger(__name__)


class DatasetViewSet(ModelViewSet):
    serializer_class = DatasetSerializer

    permission_classes = [
        IsAuthenticated,
        IsDatasetMember,
    ]

    def get_queryset(self):
        return Dataset.objects.filter(organization__memberships__user=self.request.user).select_related(
            "organization",
            "uploaded_by",
        ).distinct()

    def perform_create(self, serializer):
        dataset = serializer.save()

        def enqueue_processing():
            try:
                process_dataset.delay(dataset.pk)

            except Exception:
                logger.exception(
                    "Could not queue dataset %s",
                    dataset.pk,
                )

                Dataset.objects.filter(pk=dataset.pk).update(
                    status=Dataset.Status.FAILED,
                    error_message=(
                        "The processing job could not be queued. "
                        "Please contact support or retry later."
                    ),
                )

        transaction.on_commit(enqueue_processing)
