from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from organizations.models import Membership
from .models import Dataset
from .permissions import IsDatasetMember
from .serializers import DatasetSerializer


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
