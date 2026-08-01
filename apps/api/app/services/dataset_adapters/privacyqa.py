from __future__ import annotations

import csv
import io
from collections import Counter
from pathlib import Path
from typing import Iterator
from zipfile import ZipFile

from app.services.dataset_adapters.common import (
    STAGING_SCHEMA_VERSION,
    NormalizedTermsRecord,
    input_file_descriptor,
    normalize_text,
    sha256_file,
    sha256_text,
    stable_record_id,
    write_jsonl,
    write_manifest,
)


SOURCE_ID = "privacyqa_emnlp"
SOURCE_URL = "https://github.com/AbhilashaRavichander/PrivacyQA_EMNLP"


def convert_privacyqa(source_dir: Path, output_root: Path) -> dict[str, object]:
    archives = list(source_dir.glob("*.zip"))
    if len(archives) != 1:
        raise ValueError(f"Expected one PrivacyQA ZIP in {source_dir}")
    archive_path = archives[0]
    output_dir = output_root / SOURCE_ID
    output_path = output_dir / "qa-segments.jsonl"
    split_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    content_hashes: set[str] = set()

    with ZipFile(archive_path) as archive:
        entries = sorted(
            [
                entry
                for entry in archive.infolist()
                if entry.filename.endswith(("policy_train_data.csv", "policy_test_data.csv"))
            ],
            key=lambda entry: entry.filename,
        )

        def records() -> Iterator[NormalizedTermsRecord]:
            for entry in entries:
                wrapper = io.TextIOWrapper(archive.open(entry), encoding="utf-8-sig", errors="replace", newline="")
                reader = csv.DictReader(wrapper, delimiter="\t")
                for source_row, row in enumerate(reader, start=2):
                    query = normalize_text(row.get("Query", ""))
                    segment = normalize_text(row.get("Segment", ""))
                    if not query or not segment:
                        raise ValueError(f"PrivacyQA row is missing query or segment: {entry.filename}:{source_row}")
                    split = normalize_text(row.get("Split", "")) or (
                        "train" if "train" in entry.filename.lower() else "test"
                    )
                    label = normalize_text(row.get("Label", "") or row.get("Any_Relevant", "")) or "unknown"
                    locator = f"{entry.filename}:{row.get('QueryID', '')}:{row.get('SentID', '')}:{source_row}"
                    text = normalize_text(f"질문\n{query}\n\n정책 구간\n{segment}")
                    annotation = {
                        key: value
                        for key, value in row.items()
                        if key not in {"Folder", "DocID", "Query", "Segment"}
                    }
                    record = NormalizedTermsRecord(
                        record_id=stable_record_id(SOURCE_ID, locator),
                        source_id=SOURCE_ID,
                        split=split,
                        locale="en",
                        service_name=normalize_text(row.get("DocID", "")),
                        document_type="privacy_policy_qa",
                        category=label,
                        version_at="",
                        text=text,
                        content_sha256=sha256_text(text),
                        review_status="needs_review",
                        license_notes="See the PrivacyQA repository license and OPP-115 source terms before reuse.",
                        provenance={
                            "source_url": SOURCE_URL,
                            "source_archive": archive_path.name,
                            "source_entry": entry.filename,
                            "source_row": str(source_row),
                            "document_id": normalize_text(row.get("DocID", "")),
                            "query_id": normalize_text(row.get("QueryID", "")),
                            "sentence_id": normalize_text(row.get("SentID", "")),
                        },
                        annotations=[annotation],
                        record_type="privacy_qa",
                    )
                    split_counts[split] += 1
                    label_counts[label] += 1
                    content_hashes.add(record.content_sha256)
                    yield record

        document_count, output_bytes = write_jsonl(records(), output_path)

    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "conversion_scope": "all_policy_question_segment_rows",
        "decision_method": "schema_probe_and_rule_based_conversion",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "split_counts": dict(sorted(split_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "input_archive": input_file_descriptor(archive_path),
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": "See the PrivacyQA repository license and OPP-115 source terms before reuse.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest
