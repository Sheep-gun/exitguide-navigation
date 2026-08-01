from __future__ import annotations

from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Iterator
from zipfile import ZipFile, ZipInfo

from app.services.dataset_adapters.common import (
    STAGING_SCHEMA_VERSION,
    NormalizedTermsRecord,
    normalize_text,
    sha256_file,
    sha256_text,
    stable_record_id,
    write_jsonl,
    write_manifest,
)


SOURCE_ID = "open_terms_archive_contrib"
SOURCE_URL = "https://opentermsarchive.org/en/collections/contrib/"
LICENSE_NOTES = "Open Database License (ODbL), Open Terms Archive Contributors."


def convert_open_terms_archive(source_zip: Path, output_root: Path) -> dict[str, object]:
    if not source_zip.is_file():
        raise FileNotFoundError(f"Open Terms Archive ZIP was not found: {source_zip}")

    output_dir = output_root / SOURCE_ID
    output_path = output_dir / "documents-latest.jsonl"
    service_counts: Counter[str] = Counter()
    term_type_counts: Counter[str] = Counter()
    content_hashes: set[str] = set()
    record_ids: set[str] = set()

    with ZipFile(source_zip) as archive:
        latest, all_version_count = _latest_entries(archive)

        def records() -> Iterator[NormalizedTermsRecord]:
            for (service_name, raw_term_type), entry in sorted(latest.items()):
                text = normalize_text(archive.read(entry).decode("utf-8-sig"))
                if not text:
                    raise ValueError(f"Open Terms Archive entry is empty: {entry.filename}")
                version_at = PurePosixPath(entry.filename).stem
                content_hash = sha256_text(text)
                record_id = stable_record_id(SOURCE_ID, entry.filename)
                if record_id in record_ids:
                    raise ValueError(f"Duplicate normalized record ID: {record_id}")
                record_ids.add(record_id)
                service_counts[service_name] += 1
                term_type_counts[raw_term_type] += 1
                content_hashes.add(content_hash)
                yield NormalizedTermsRecord(
                    record_id=record_id,
                    source_id=SOURCE_ID,
                    split="latest",
                    locale="und",
                    service_name=service_name,
                    document_type=_normalize_document_type(raw_term_type),
                    category=raw_term_type,
                    version_at=version_at,
                    text=text,
                    content_sha256=content_hash,
                    review_status="needs_review",
                    license_notes=LICENSE_NOTES,
                    provenance={
                        "source_url": SOURCE_URL,
                        "source_archive": source_zip.name,
                        "source_entry": entry.filename,
                    },
                )

        document_count, output_bytes = write_jsonl(records(), output_path)

    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "conversion_scope": "latest_version_per_service_and_term_type",
        "all_version_count": all_version_count,
        "document_count": document_count,
        "service_count": len(service_counts),
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "term_type_counts": dict(sorted(term_type_counts.items())),
        "input_archive": {
            "name": source_zip.name,
            "bytes": source_zip.stat().st_size,
            "sha256": sha256_file(source_zip),
        },
        "output": {
            "name": output_path.name,
            "bytes": output_bytes,
            "sha256": sha256_file(output_path),
        },
        "review_status": "needs_review",
        "license_notes": LICENSE_NOTES,
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _latest_entries(archive: ZipFile) -> tuple[dict[tuple[str, str], ZipInfo], int]:
    latest: dict[tuple[str, str], ZipInfo] = {}
    all_version_count = 0
    for entry in archive.infolist():
        if entry.is_dir() or PurePosixPath(entry.filename).suffix.lower() != ".md":
            continue
        parts = PurePosixPath(entry.filename).parts
        if len(parts) < 4:
            continue
        service_name, term_type = parts[-3], parts[-2]
        key = (service_name, term_type)
        all_version_count += 1
        current = latest.get(key)
        if current is None or PurePosixPath(entry.filename).stem > PurePosixPath(current.filename).stem:
            latest[key] = entry
    if not latest:
        raise ValueError("Open Terms Archive ZIP contains no version Markdown files")
    return latest, all_version_count


def _normalize_document_type(raw_term_type: str) -> str:
    normalized = raw_term_type.lower()
    if "privacy" in normalized:
        return "privacy_policy"
    if "subscription" in normalized:
        return "subscription_terms"
    if "marketing" in normalized or "advertising" in normalized:
        return "marketing_terms"
    if "location" in normalized:
        return "location_terms"
    if "terms" in normalized or "conditions" in normalized:
        return "terms_of_service"
    return "unknown"
