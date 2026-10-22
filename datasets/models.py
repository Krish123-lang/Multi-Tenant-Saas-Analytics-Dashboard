import uuid
from pathlib import Path

from django.conf import settings
from django.db import models


def dataset_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    return (
        f"private_datasets/org_{instance.organization_id}/"
        f"{uuid.uuid4().hex}{extension}"
    )

class Dataset(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    organization = models.ForeignKey("organizations.Organization",on_delete=models.CASCADE,related_name="datasets",)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="uploaded_datasets",)
    name = models.CharField(max_length=150)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=dataset_upload_path,max_length=500,)
    file_size = models.PositiveBigIntegerField(default=0)
    row_count = models.PositiveBigIntegerField(null=True,blank=True,)
    status = models.CharField(max_length=20,choices=Status.choices,default=Status.PENDING,db_index=True,)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True,blank=True,)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="dataset_org_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization})"
