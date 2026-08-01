from __future__ import annotations

import csv
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


KCA_SOURCE_ID = "data_go_kr_kca_standard_answers"
FTC_CASE_SOURCE_ID = "data_go_kr_ftc_consumer_model_cases"


def convert_consumer_guidance(raw_root: Path, output_root: Path) -> dict[str, dict[str, object]]:
    return {
        KCA_SOURCE_ID: _convert_kca(raw_root / KCA_SOURCE_ID, output_root),
        FTC_CASE_SOURCE_ID: _convert_ftc_cases(raw_root / FTC_CASE_SOURCE_ID, output_root),
    }


def _convert_kca(source_dir: Path, output_root: Path) -> dict[str, object]:
    input_path = _single_csv(source_dir)
    return _convert_csv_records(
        source_id=KCA_SOURCE_ID,
        source_url="https://www.data.go.kr/data/15144809/fileData.do",
        input_path=input_path,
        encoding="cp949",
        output_root=output_root,
        records_factory=lambda: _iter_kca(input_path),
    )


def _convert_ftc_cases(source_dir: Path, output_root: Path) -> dict[str, object]:
    input_path = _single_csv(source_dir)
    return _convert_csv_records(
        source_id=FTC_CASE_SOURCE_ID,
        source_url="https://www.data.go.kr/data/15098335/fileData.do",
        input_path=input_path,
        encoding="utf-8-sig",
        output_root=output_root,
        records_factory=lambda: _iter_ftc_cases(input_path),
    )


def _convert_csv_records(
    source_id: str,
    source_url: str,
    input_path: Path,
    encoding: str,
    output_root: Path,
    records_factory,
) -> dict[str, object]:
    output_dir = output_root / source_id
    output_path = output_dir / "records.jsonl"
    categories: Counter[str] = Counter()
    content_hashes: set[str] = set()

    def records() -> Iterator[NormalizedTermsRecord]:
        for record in records_factory():
            categories[record.category] += 1
            content_hashes.add(record.content_sha256)
            yield record

    document_count, output_bytes = write_jsonl(records(), output_path)
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": source_id,
        "source_url": source_url,
        "conversion_scope": "all_consumer_guidance_rows",
        "decision_method": "schema_probe_and_rule_based_conversion",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "category_count": len(categories),
        "input_encoding": encoding,
        "input_file": input_file_descriptor(input_path),
        "output": {"name": output_path.name, "bytes": output_bytes, "sha256": sha256_file(output_path)},
        "review_status": "needs_review",
        "license_notes": "Reuse is subject to the source public-data terms and review.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _iter_kca(path: Path) -> Iterator[NormalizedTermsRecord]:
    with path.open(encoding="cp949", newline="") as handle:
        for row in csv.DictReader(handle):
            row_id = normalize_text(row.get("번호") or "")
            item = normalize_text(row.get("품목명") or "")
            category = normalize_text(row.get("구분") or "")
            question = normalize_text(row.get("질문") or "")
            answer = normalize_text(row.get("답변") or "")
            text = normalize_text(f"질문\n{question}\n\n답변\n{answer}")
            yield _guidance_record(
                KCA_SOURCE_ID,
                row_id,
                item,
                category or "consumer_consultation",
                text,
                path.name,
                "https://www.data.go.kr/data/15144809/fileData.do",
            )


def _iter_ftc_cases(path: Path) -> Iterator[NormalizedTermsRecord]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            row_id = normalize_text(row.get("사건번호(ACCIDENT_NO)") or "")
            title = normalize_text(row.get("사건제목(ACCIDENT_TITLE)") or "")
            body = normalize_text(row.get("사건내용(ACCIDENT_CONTENT)") or "")
            answer = normalize_text(row.get("답변내용(ANS_CONTENT)") or "")
            text = normalize_text(f"{title}\n\n사건 내용\n{body}\n\n답변\n{answer}")
            yield _guidance_record(
                FTC_CASE_SOURCE_ID,
                row_id,
                "Korea FTC consumer case",
                "consumer_model_case",
                text,
                path.name,
                "https://www.data.go.kr/data/15098335/fileData.do",
            )


def _guidance_record(
    source_id: str,
    row_id: str,
    service_name: str,
    category: str,
    text: str,
    source_file: str,
    source_url: str,
) -> NormalizedTermsRecord:
    return NormalizedTermsRecord(
        record_id=stable_record_id(source_id, row_id),
        source_id=source_id,
        split="all",
        locale="ko-KR",
        service_name=service_name,
        document_type="consumer_guidance",
        category=category,
        version_at="",
        text=text,
        content_sha256=sha256_text(text),
        review_status="needs_review",
        license_notes="Reuse is subject to the source public-data terms and review.",
        provenance={"source_url": source_url, "source_file": source_file, "source_row_id": row_id},
        record_type="consumer_guidance",
    )


def _single_csv(source_dir: Path) -> Path:
    files = list(source_dir.glob("*.csv"))
    if len(files) != 1:
        raise ValueError(f"Expected one CSV in {source_dir}, found {len(files)}")
    return files[0]
