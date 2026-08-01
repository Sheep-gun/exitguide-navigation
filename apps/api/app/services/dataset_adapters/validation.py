from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from app.services.dataset_adapters.common import (
    STAGING_SCHEMA_VERSION,
    SUPPORTED_RECORD_TYPES,
    sha256_file,
    sha256_text,
)


def validate_normalized_jsonl(
    input_path: Path,
    manifest_path: Path,
    expected_source_id: str,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record_ids: set[str] = set()
    content_hashes: Counter[str] = Counter()
    review_statuses: Counter[str] = Counter()
    categories: set[str] = set()
    record_types: Counter[str] = Counter()
    text_lengths: list[int] = []

    with input_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            record = json.loads(line)
            _validate_record(record, line_number, expected_source_id)
            record_id = str(record["record_id"])
            if record_id in record_ids:
                raise ValueError(f"Duplicate record_id at line {line_number}: {record_id}")
            record_ids.add(record_id)

            text = str(record["text"])
            content_hash = sha256_text(text)
            if content_hash != record["content_sha256"]:
                raise ValueError(f"content_sha256 mismatch at line {line_number}: {record_id}")
            content_hashes[content_hash] += 1
            review_statuses[str(record["review_status"])] += 1
            categories.add(str(record["category"]))
            record_types[str(record["record_type"])] += 1
            text_lengths.append(len(text))

    document_count = len(text_lengths)
    if not document_count:
        raise ValueError(f"Normalized dataset is empty: {input_path}")
    if manifest["document_count"] != document_count:
        raise ValueError("Manifest document_count does not match normalized JSONL")

    output_hash = sha256_file(input_path)
    if manifest["output"]["sha256"] != output_hash:
        raise ValueError("Manifest output hash does not match normalized JSONL")

    return {
        "source_id": expected_source_id,
        "document_count": document_count,
        "unique_record_count": len(record_ids),
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": sum(count - 1 for count in content_hashes.values()),
        "category_count": len(categories),
        "record_type_counts": dict(sorted(record_types.items())),
        "review_status_counts": dict(sorted(review_statuses.items())),
        "text_length": {
            "min": min(text_lengths),
            "median": int(statistics.median(text_lengths)),
            "max": max(text_lengths),
        },
        "output_sha256": output_hash,
    }


def _validate_record(record: dict[str, object], line_number: int, expected_source_id: str) -> None:
    required_text_fields = (
        "record_id",
        "source_id",
        "locale",
        "document_type",
        "category",
        "text",
        "content_sha256",
        "review_status",
    )
    for field_name in required_text_fields:
        value = record.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing or empty {field_name} at line {line_number}")
    if record["source_id"] != expected_source_id:
        raise ValueError(f"Unexpected source_id at line {line_number}: {record['source_id']}")
    if record.get("schema_version") != STAGING_SCHEMA_VERSION:
        raise ValueError(f"Unexpected schema_version at line {line_number}")
    if record.get("record_type") not in SUPPORTED_RECORD_TYPES:
        raise ValueError(f"Unexpected record_type at line {line_number}")
    if not isinstance(record.get("provenance"), dict):
        raise ValueError(f"Missing provenance at line {line_number}")
    if not isinstance(record.get("annotations"), list):
        raise ValueError(f"Missing annotations at line {line_number}")
