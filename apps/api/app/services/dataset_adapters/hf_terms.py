from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterator

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


SOURCE_ID = "hf_online_terms_of_service"
SOURCE_URL = "https://huggingface.co/datasets/joelniklaus/online_terms_of_service"


def convert_hf_online_terms(source_dir: Path, output_root: Path) -> dict[str, object]:
    input_paths = sorted(source_dir.glob("*.jsonl"))
    if len(input_paths) != 3:
        raise ValueError(f"Expected train/validation/test JSONL files in {source_dir}")

    output_dir = output_root / SOURCE_ID
    output_path = output_dir / "segments.jsonl"
    split_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    content_hashes: set[str] = set()

    def records() -> Iterator[NormalizedTermsRecord]:
        for path in input_paths:
            split = path.stem
            with path.open(encoding="utf-8-sig") as handle:
                for line_number, line in enumerate(handle, start=1):
                    row = json.loads(line)
                    text = normalize_text(str(row["sentence"]))
                    if not text:
                        raise ValueError(f"Empty Hugging Face sentence in {path.name}:{line_number}")
                    language = normalize_text(str(row["language"])) or "und"
                    label = normalize_text(str(row["unfairness_level"])) or "untagged"
                    locator = f"{split}:{line_number}"
                    annotation = {
                        "unfairness_level": label,
                        "topics": list(row.get("all_topics") or []),
                        "topic_flags": {
                            key: bool(row.get(key))
                            for key in ("a", "ch", "cr", "j", "law", "ltd", "ter", "use", "pinc")
                        },
                        "line_number": row.get("line_number"),
                    }
                    record = NormalizedTermsRecord(
                        record_id=stable_record_id(SOURCE_ID, locator),
                        source_id=SOURCE_ID,
                        split=split,
                        locale=language,
                        service_name=normalize_text(str(row["company"])),
                        document_type="terms_of_service",
                        category=label,
                        version_at="",
                        text=text,
                        content_sha256=sha256_text(text),
                        review_status="needs_review",
                        license_notes="See the Hugging Face dataset card and source repository license before reuse.",
                        provenance={
                            "source_url": SOURCE_URL,
                            "source_file": path.name,
                            "source_line": str(line_number),
                        },
                        annotations=[annotation],
                        record_type="terms_clause",
                    )
                    split_counts[split] += 1
                    language_counts[language] += 1
                    label_counts[label] += 1
                    content_hashes.add(record.content_sha256)
                    yield record

    document_count, output_bytes = write_jsonl(records(), output_path)
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "conversion_scope": "all_source_rows",
        "decision_method": "schema_probe_and_rule_based_conversion",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "split_counts": dict(sorted(split_counts.items())),
        "language_counts": dict(sorted(language_counts.items())),
        "label_counts": dict(sorted(label_counts.items())),
        "input_files": [input_file_descriptor(path) for path in input_paths],
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": "See the Hugging Face dataset card and source repository license before reuse.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest
