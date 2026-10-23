from rest_framework import serializers

from datasets.models import DatasetRecord


class DatasetRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetRecord
        fields = [
            "id",
            "row_number",
            "data",
            "transaction_date",
            "amount_value",
            "created_at",
        ]
        read_only_fields = fields