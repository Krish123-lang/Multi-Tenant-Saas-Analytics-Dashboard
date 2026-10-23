import csv
import io
import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import Dataset, DatasetRecord

logger = logging.getLogger(__name__)


class CSVValidationError(Exception):
    """Raised when a CSV does not match the expected structure."""


# def validate_and_count_csv(dataset):
#     row_count = 0

#     with dataset.file.open("rb") as binary_file:
#         with io.TextIOWrapper(binary_file, encoding="utf-8-sig", newline="",) as text_file:
#             reader = csv.reader(text_file, strict=True)

#             headers = next(reader, None)

#             if not headers:
#                 raise CSVValidationError("The CSV is empty or has no header.")

#             normalized_headers = [header.strip().casefold()
#                                   for header in headers]

#             if any(not header for header in normalized_headers):
#                 raise CSVValidationError("Column names cannot be empty.")

#             if len(set(normalized_headers)) != len(normalized_headers):
#                 raise CSVValidationError("Column names must be unique.")

#             for row in reader:
#                 if not row or all(not cell.strip() for cell in row):
#                     continue

#                 if len(row) != len(headers):
#                     raise CSVValidationError(
#                         f"Invalid column count on CSV line {reader.line_num}.")

#                 row_count += 1

#     return row_count

class CSVValidationError(Exception):
    """Raised when a CSV does not match the expected structure."""


def load_csv_records(dataset, batch_size=1000):
    row_count = 0
    batch = []

    try:
        with dataset.file.open("rb") as binary_file:
            with io.TextIOWrapper( binary_file, encoding="utf-8-sig", newline="",) as text_file:
                reader = csv.reader(text_file, strict=True)
                headers = next(reader, None)

                if not headers:
                    raise CSVValidationError("The CSV is empty or has no header.")

                headers = [header.strip() for header in headers]
                normalized_headers = [header.casefold() for header in headers]

                if any(not header for header in headers):
                    raise CSVValidationError("Column names cannot be empty.")

                if len(set(normalized_headers)) != len(headers):
                    raise CSVValidationError("Column names must be unique.")

                # This function is called inside transaction.atomic().
                # Old records are replaced only if processing succeeds.
                DatasetRecord.objects.filter(dataset=dataset).delete()

                for row in reader:
                    if not row or all(not cell.strip() for cell in row):
                        continue

                    if len(row) != len(headers):
                        raise CSVValidationError(
                            f"Invalid column count on CSV line "
                            f"{reader.line_num}."
                        )

                    row_count += 1

                    batch.append(
                        DatasetRecord(dataset=dataset,row_number=row_count,data=dict(zip(headers, row)),)
                    )

                    if len(batch) >= batch_size:
                        DatasetRecord.objects.bulk_create(batch,batch_size=batch_size,)
                        batch.clear()

                if batch:
                    DatasetRecord.objects.bulk_create(batch,batch_size=batch_size,)

    except csv.Error as exc:
        raise CSVValidationError("The CSV file contains invalid formatting.") from exc
    except UnicodeDecodeError as exc:
        raise CSVValidationError("The CSV file must use UTF-8 text encoding.") from exc

    return row_count

# @shared_task(bind=True, name="datasets.process_dataset")
# def process_dataset(self, dataset_id):
#     try:
#         with transaction.atomic():
#             dataset = Dataset.objects.select_for_update().get(pk=dataset_id)

#             if dataset.status == Dataset.Status.COMPLETED:
#                 return {"dataset_id": dataset_id, "status": "already_completed", }

#             dataset.status = Dataset.Status.PROCESSING
#             dataset.error_message = ""
#             dataset.save(update_fields=["status", "error_message"])

#     except Dataset.DoesNotExist:
#         logger.warning(
#             "Dataset %s no longer exists; skipping task.", dataset_id,)
#         return {"dataset_id": dataset_id, "status": "not_found", }

#     try:
#         row_count = validate_and_count_csv(dataset)

#         with transaction.atomic():
#             dataset = Dataset.objects.select_for_update().get(pk=dataset_id)

#             dataset.row_count = row_count
#             dataset.status = Dataset.Status.COMPLETED
#             dataset.processed_at = timezone.now()
#             dataset.error_message = ""

#             dataset.save(update_fields=[
#                          "row_count", "status", "processed_at", "error_message",])

#         return {"dataset_id": dataset_id, "status": "completed", "row_count": row_count, }

#     except CSVValidationError as exc:
#         Dataset.objects.filter(pk=dataset_id).update(
#             status=Dataset.Status.FAILED, error_message=str(exc),)

#         logger.info("CSV validation failed for dataset %s: %s",
#                     dataset_id, exc,)

#         return {"dataset_id": dataset_id, "status": "failed", }

#     except Exception:
#         Dataset.objects.filter(pk=dataset_id).update(
#             status=Dataset.Status.FAILED,
#             error_message=(
#                 "Processing failed due to an internal error."
#             ),
#         )

#         logger.exception("Unexpected error processing dataset %s", dataset_id,)

#         raise

@shared_task(bind=True, name="datasets.process_dataset")
def process_dataset(self, dataset_id):
    try:
        with transaction.atomic():
            dataset = Dataset.objects.select_for_update().get(pk=dataset_id)

            if dataset.status == Dataset.Status.COMPLETED:
                return {"dataset_id": dataset_id,"status": "already_completed",}

            dataset.status = Dataset.Status.PROCESSING
            dataset.error_message = ""
            dataset.save(update_fields=["status", "error_message"])

    except Dataset.DoesNotExist:
        logger.warning("Dataset %s no longer exists; skipping task.",dataset_id,)
        return {"dataset_id": dataset_id,"status": "not_found",}

    try:
        with transaction.atomic():
            dataset = Dataset.objects.select_for_update().get(pk=dataset_id)

            row_count = load_csv_records(dataset)

            dataset.row_count = row_count
            dataset.status = Dataset.Status.COMPLETED
            dataset.processed_at = timezone.now()
            dataset.error_message = ""

            dataset.save(update_fields=["row_count","status","processed_at","error_message",])

        return {"dataset_id": dataset_id,"status": "completed","row_count": row_count,}

    except CSVValidationError as exc:
        Dataset.objects.filter(pk=dataset_id).update(status=Dataset.Status.FAILED,error_message=str(exc),)

        logger.info("CSV validation failed for dataset %s: %s",dataset_id,exc,)

        return {"dataset_id": dataset_id,"status": "failed",}

    except Exception:
        Dataset.objects.filter(pk=dataset_id).update(
            status=Dataset.Status.FAILED,
            error_message=(
                "Processing failed due to an internal error."
            ),
        )

        logger.exception("Unexpected error processing dataset %s",dataset_id,)
        raise