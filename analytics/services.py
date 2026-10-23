from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from datasets.models import DatasetRecord


class MappingValidationError(ValueError):
    pass


@transaction.atomic
def normalize_dataset_records(dataset, mapping):
    records = DatasetRecord.objects.filter(dataset=dataset).order_by("row_number")

    updates = []

    for record in records.iterator(chunk_size=1000):
        amount_value = None
        transaction_date = None

        if "amount" in mapping:
            column = mapping["amount"]

            if column not in record.data:
                raise MappingValidationError(f"Mapped amount column '{column}' is missing.")

            try:
                amount_value = Decimal(str(record.data[column]).strip())
            except (InvalidOperation, ValueError):
                raise MappingValidationError(
                    f"Invalid numeric value in row "
                    f"{record.row_number}."
                )

            if not amount_value.is_finite():
                raise MappingValidationError(f"Non-finite amount in row {record.row_number}.")

            if amount_value.as_tuple().exponent < -4:
                raise MappingValidationError(
                    f"Amount in row {record.row_number} has "
                    "more than four decimal places."
                )

            if amount_value.adjusted() > 15:
                raise MappingValidationError(
                    f"Amount in row {record.row_number} "
                    "exceeds the supported range."
                )

        if "date" in mapping:
            column = mapping["date"]

            if column not in record.data:
                raise MappingValidationError(f"Mapped date column '{column}' is missing.")

            try:
                transaction_date = date.fromisoformat(str(record.data[column]).strip())
            except ValueError:
                raise MappingValidationError(
                    f"Invalid ISO date in row {record.row_number}. "
                    "Use YYYY-MM-DD."
                )

        record.amount_value = amount_value
        record.transaction_date = transaction_date
        updates.append(record)

        if len(updates) >= 1000:
            DatasetRecord.objects.bulk_update(updates,["amount_value", "transaction_date"],batch_size=1000,)
            updates.clear()

    if updates:
        DatasetRecord.objects.bulk_update(updates,["amount_value", "transaction_date"],batch_size=1000,)