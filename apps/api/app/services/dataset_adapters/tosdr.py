from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
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
from app.services.dataset_adapters.text_utils import decode_bytes, html_to_text, infer_document_type, nullable


ZENODO_SOURCE_ID = "tosdr_zenodo_raw_2023"
MIRROR_SOURCE_ID = "tosdr_terms_corpus_github"
ZENODO_URL = "https://zenodo.org/records/15012282"
MIRROR_URL = "https://github.com/sonu-gupta/tosdr-terms-of-service-corpus"


def convert_tosdr_sources(raw_root: Path, output_root: Path) -> dict[str, dict[str, object]]:
    return {
        ZENODO_SOURCE_ID: convert_tosdr_zenodo(raw_root / ZENODO_SOURCE_ID, output_root),
        MIRROR_SOURCE_ID: convert_tosdr_mirror(raw_root / MIRROR_SOURCE_ID, output_root),
    }


def convert_tosdr_zenodo(source_dir: Path, output_root: Path) -> dict[str, object]:
    csv.field_size_limit(sys.maxsize)
    paths = {name: source_dir / name for name in ("cases.csv", "documents.csv", "points.csv", "services.csv", "topics.csv")}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    services = _read_index(paths["services.csv"], "id")
    cases = _read_index(paths["cases.csv"], "id")
    points_by_document: dict[str, list[dict[str, object]]] = defaultdict(list)
    with paths["points.csv"].open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            document_id = nullable(row.get("document_id"))
            if not document_id:
                continue
            case = cases.get(nullable(row.get("case_id")), {})
            points_by_document[document_id].append(
                {
                    "point_id": nullable(row.get("id")),
                    "rank": nullable(row.get("rank")),
                    "title": nullable(row.get("title")),
                    "status": nullable(row.get("status")),
                    "analysis": nullable(row.get("analysis")),
                    "quote_text": nullable(row.get("quote_text")),
                    "case_id": nullable(row.get("case_id")),
                    "case_classification": nullable(case.get("classification")),
                    "case_title": nullable(case.get("title")),
                    "topic_id": nullable(case.get("topic_id")),
                }
            )

    output_dir = output_root / ZENODO_SOURCE_ID
    output_path = output_dir / "documents.jsonl"
    content_hashes: set[str] = set()
    type_counts: Counter[str] = Counter()
    skipped_empty = 0

    def records() -> Iterator[NormalizedTermsRecord]:
        nonlocal skipped_empty
        with paths["documents.csv"].open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                document_id = nullable(row.get("id"))
                raw_text = nullable(row.get("text"))
                if not raw_text:
                    skipped_empty += 1
                    continue
                text = html_to_text(raw_text) if re.search(r"</?[a-z][^>]*>", raw_text, re.I) else normalize_text(raw_text)
                if not text:
                    skipped_empty += 1
                    continue
                service = services.get(nullable(row.get("service_id")), {})
                name = nullable(row.get("name"))
                url = nullable(row.get("url"))
                document_type = infer_document_type(name, url)
                record = NormalizedTermsRecord(
                    record_id=stable_record_id(ZENODO_SOURCE_ID, document_id),
                    source_id=ZENODO_SOURCE_ID,
                    split="all",
                    locale="und",
                    service_name=nullable(service.get("name")) or name,
                    document_type=document_type,
                    category=document_type,
                    version_at=nullable(row.get("updated_at")) or nullable(row.get("created_at")),
                    text=text,
                    content_sha256=sha256_text(text),
                    review_status="needs_review",
                    license_notes="Zenodo record 15012282 lists GPL-3.0-or-later; verify downstream document rights.",
                    provenance={
                        "source_url": ZENODO_URL,
                        "source_file": paths["documents.csv"].name,
                        "source_row_id": document_id,
                        "document_url": url,
                        "service_id": nullable(row.get("service_id")),
                        "reviewed": nullable(row.get("reviewed")),
                        "status": nullable(row.get("status")),
                    },
                    annotations=points_by_document.get(document_id, []),
                )
                type_counts[document_type] += 1
                content_hashes.add(record.content_sha256)
                yield record

    document_count, output_bytes = write_jsonl(records(), output_path)
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": ZENODO_SOURCE_ID,
        "source_url": ZENODO_URL,
        "conversion_scope": "all_nonempty_documents_with_linked_points",
        "decision_method": "schema_probe_and_rule_based_conversion",
        "document_count": document_count,
        "skipped_empty_document_count": skipped_empty,
        "linked_point_count": sum(len(value) for value in points_by_document.values()),
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "document_type_counts": dict(sorted(type_counts.items())),
        "input_files": [input_file_descriptor(path) for path in paths.values()],
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": "Zenodo record 15012282 lists GPL-3.0-or-later; verify downstream document rights.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def convert_tosdr_mirror(source_dir: Path, output_root: Path) -> dict[str, object]:
    archives = list(source_dir.glob("*.zip"))
    if len(archives) != 1:
        raise ValueError(f"Expected one ToS;DR mirror ZIP in {source_dir}")
    archive_path = archives[0]
    output_dir = output_root / MIRROR_SOURCE_ID
    output_path = output_dir / "documents.jsonl"
    content_hashes: set[str] = set()
    type_counts: Counter[str] = Counter()
    encoding_counts: Counter[str] = Counter()

    with ZipFile(archive_path) as archive:
        entries = sorted(
            [
                entry
                for entry in archive.infolist()
                if not entry.is_dir()
                and "/corpus/text/" in entry.filename.lower()
                and entry.filename.lower().endswith(".txt")
            ],
            key=lambda entry: entry.filename,
        )

        def records() -> Iterator[NormalizedTermsRecord]:
            for entry in entries:
                decoded, encoding = decode_bytes(archive.read(entry))
                text = normalize_text(decoded)
                if not text:
                    raise ValueError(f"Empty ToS;DR mirror text: {entry.filename}")
                stem = PurePosixPath(entry.filename).stem
                service_name, document_label = _split_mirror_name(stem)
                document_type = infer_document_type(document_label)
                record = NormalizedTermsRecord(
                    record_id=stable_record_id(MIRROR_SOURCE_ID, entry.filename),
                    source_id=MIRROR_SOURCE_ID,
                    split="all",
                    locale="und",
                    service_name=service_name,
                    document_type=document_type,
                    category=document_label or document_type,
                    version_at="",
                    text=text,
                    content_sha256=sha256_text(text),
                    review_status="needs_review",
                    license_notes="See the source repository documentation and linked service terms before reuse.",
                    provenance={
                        "source_url": MIRROR_URL,
                        "source_archive": archive_path.name,
                        "source_entry": entry.filename,
                        "source_encoding": encoding,
                    },
                )
                type_counts[document_type] += 1
                encoding_counts[encoding] += 1
                content_hashes.add(record.content_sha256)
                yield record

        document_count, output_bytes = write_jsonl(records(), output_path)

    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": MIRROR_SOURCE_ID,
        "source_url": MIRROR_URL,
        "conversion_scope": "all_corpus_text_entries",
        "decision_method": "archive_structure_probe_and_rule_based_conversion",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "document_type_counts": dict(sorted(type_counts.items())),
        "encoding_counts": dict(sorted(encoding_counts.items())),
        "input_archive": input_file_descriptor(archive_path),
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": "See the source repository documentation and linked service terms before reuse.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _read_index(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {nullable(row.get(key)): row for row in csv.DictReader(handle) if nullable(row.get(key))}


def _split_mirror_name(stem: str) -> tuple[str, str]:
    suffix_pattern = re.compile(
        r"^(?P<service>.+?)_(?P<label>privacy policy|privacy statement|terms of service|terms of use|terms and conditions|user agreement|cookie policy)$",
        re.IGNORECASE,
    )
    match = suffix_pattern.match(stem)
    if match:
        return match.group("service"), match.group("label")
    return stem, "terms_or_policy"
