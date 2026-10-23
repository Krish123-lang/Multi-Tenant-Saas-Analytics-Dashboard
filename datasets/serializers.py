import csv
import io
import os
from rest_framework import serializers
from organizations.models import Membership, Organization
from .models import Dataset
from analytics.services import (MappingValidationError,normalize_dataset_records,)
from django.db import transaction
from pathlib import Path

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class DatasetSerializer(serializers.ModelSerializer):
    organization_id = serializers.IntegerField(write_only=True, required=True,)
    file = serializers.FileField(write_only=True, required=True,)

    class Meta:
        model = Dataset
        fields = ["id", "organization_id", "name", "original_filename", "file", "file_size", "row_count", "status", "error_message", "created_at", "processed_at",]

        read_only_fields = ["id", "original_filename", "file_size", "row_count", "status", "error_message", "created_at", "processed_at",]

    def validate(self, attrs):
        if self.instance is None:
            if "organization_id" not in attrs:
                raise serializers.ValidationError({"organization_id": "This field is required."})

            if "file" not in attrs:
                raise serializers.ValidationError({"file": "This field is required."})
        else:
            if "organization_id" in attrs:
                raise serializers.ValidationError({"organization_id": "A dataset cannot be moved to another organization."})

            if "file" in attrs:
                raise serializers.ValidationError({"file": "Replacing uploaded files is not supported."})
        return attrs

    def validate_name(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Dataset name cannot be empty.")
        return value

    def validate_file(self, uploaded_file):
        if uploaded_file.size == 0:
            raise serializers.ValidationError("The uploaded file is empty.")

        if uploaded_file.size > MAX_UPLOAD_SIZE:
            raise serializers.ValidationError("Maximum upload size is 10 MB.")
        filename = uploaded_file.name.replace("\\", "/").split("/")[-1]

        if os.path.splitext(filename)[1].lower() != ".csv":
            raise serializers.ValidationError("Only CSV files are supported.")

        try:
            sample = uploaded_file.read(8192).decode("utf-8-sig")
            uploaded_file.seek(0)
        except (UnicodeDecodeError, AttributeError):
            raise serializers.ValidationError("The file must be a UTF-8 encoded CSV.")

        try:
            reader = csv.reader(io.StringIO(sample))
            headers = next(reader, None)
        except csv.Error:
            raise serializers.ValidationError("The CSV structure is invalid.")

        if not headers or not any(h.strip() for h in headers):
            raise serializers.ValidationError("The CSV must contain a header row.")

        normalized_headers = [h.strip().casefold() for h in headers]

        if any(not header for header in normalized_headers):
            raise serializers.ValidationError("CSV column names cannot be empty.")

        if len(set(normalized_headers)) != len(normalized_headers):
            raise serializers.ValidationError("CSV column names must be unique.")
        return uploaded_file

    def validate_organization_id(self, value):
        user = self.context["request"].user
        membership = Membership.objects.filter(organization_id=value, user=user,).first()

        if membership is None:
            raise serializers.ValidationError("You do not have access to this organization.")
        return value

    def create(self, validated_data):
        organization_id = validated_data.pop("organization_id")
        organization = Organization.objects.get(pk=organization_id)

        uploaded_file = validated_data["file"]

        original_filename = Path(uploaded_file.name).name
        file_size = uploaded_file.size

        return Dataset.objects.create(
            organization=organization,
            uploaded_by=self.context["request"].user,
            original_filename=original_filename,
            file_size=file_size,
            **validated_data,
        )

    def validate_column_mapping(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Column mapping must be a JSON object.")

        allowed_keys = {"amount", "date", "category"}

        if not set(value).issubset(allowed_keys):
            raise serializers.ValidationError("Supported mapping keys are amount, date, and category.")

        for key, column_name in value.items():
            if not isinstance(column_name, str) or not column_name.strip():
                raise serializers.ValidationError(f"The mapping for '{key}' must name a CSV column.")

        if "amount" in value and "date" in value:
            if value["amount"] == value["date"]:
                raise serializers.ValidationError("Amount and date must map to different columns.")

        return value
    
    @transaction.atomic
    def update(self, instance, validated_data):
        mapping_changed = "column_mapping" in validated_data

        if mapping_changed:
            new_mapping = validated_data["column_mapping"]

            try:
                normalize_dataset_records(instance, new_mapping)
            except MappingValidationError as exc:
                raise serializers.ValidationError({"column_mapping": str(exc)})

        return super().update(instance, validated_data)