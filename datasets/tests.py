from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from organizations.models import Membership, Organization
from .models import Dataset


User = get_user_model()


class DatasetAPITests(APITestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            username="dataset_owner",
            password="test-password-123",
        )

        self.analyst = User.objects.create_user(
            username="dataset_analyst",
            password="test-password-123",
        )

        self.outsider = User.objects.create_user(
            username="dataset_outsider",
            password="test-password-123",
        )

        self.organization = Organization.objects.create(
            name="Dataset Company",
        )

        self.other_organization = Organization.objects.create(
            name="Other Company",
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.analyst,
            role=Membership.Role.ANALYST,
        )

        Membership.objects.create(
            organization=self.other_organization,
            user=self.outsider,
            role=Membership.Role.OWNER,
        )

        self.dataset = Dataset.objects.create(
            organization=self.organization,
            uploaded_by=self.owner,
            name="Sales Data",
            original_filename="sales.csv",
            file=SimpleUploadedFile(
                "sales.csv",
                b"date,revenue\n2026-01-01,150\n",
                content_type="text/csv",
            ),
            file_size=31,
        )

        self.list_url = reverse("dataset-list")

        self.detail_url = reverse(
            "dataset-detail",
            args=[self.dataset.pk],
        )

    def test_user_only_sees_their_tenant_datasets(self):
        self.client.force_authenticate(user=self.analyst)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            self.dataset.pk,
        )

    def test_other_tenant_cannot_retrieve_dataset(self):
        self.client.force_authenticate(user=self.outsider)

        response = self.client.get(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_analyst_cannot_delete_dataset(self):
        self.client.force_authenticate(user=self.analyst)

        response = self.client.delete(self.detail_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertTrue(
            Dataset.objects.filter(pk=self.dataset.pk).exists()
        )

    def test_member_can_upload_csv(self):
        self.client.force_authenticate(user=self.analyst)

        upload = SimpleUploadedFile(
            "monthly_sales.csv",
            b"date,revenue\n2026-01-01,150\n",
            content_type="text/csv",
        )

        response = self.client.post(
            self.list_url,
            {
                "organization_id": self.organization.pk,
                "name": "Monthly Sales",
                "file": upload,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
        )

        dataset = Dataset.objects.get(name="Monthly Sales")

        self.assertEqual(
            dataset.organization_id,
            self.organization.pk,
        )

        self.assertEqual(dataset.uploaded_by, self.analyst)
        self.assertEqual(dataset.status, Dataset.Status.PENDING)

    def test_member_cannot_upload_to_another_tenant(self):
        self.client.force_authenticate(user=self.analyst)

        upload = SimpleUploadedFile(
            "private.csv",
            b"date,revenue\n2026-01-01,150\n",
            content_type="text/csv",
        )

        response = self.client.post(
            self.list_url,
            {
                "organization_id": self.other_organization.pk,
                "name": "Unauthorized Upload",
                "file": upload,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            Dataset.objects.filter(
                name="Unauthorized Upload"
            ).exists()
        )

    def test_non_csv_upload_is_rejected(self):
        self.client.force_authenticate(user=self.owner)

        upload = SimpleUploadedFile(
            "notes.txt",
            b"this is not a CSV file",
            content_type="text/plain",
        )

        response = self.client.post(
            self.list_url,
            {
                "organization_id": self.organization.pk,
                "name": "Invalid Upload",
                "file": upload,
            },
            format="multipart",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
