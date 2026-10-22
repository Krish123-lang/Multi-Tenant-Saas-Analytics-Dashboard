from django.contrib import admin
from .models import Dataset

@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "uploaded_by", "status", "file_size", "created_at",)
    list_filter = ("status", "organization")
    search_fields = ("name", "original_filename", "organization__name",)
    readonly_fields = ("original_filename", "file_size", "row_count", "status", "error_message", "created_at", "processed_at",)
