from __future__ import annotations

import json
import lzma
import sqlite3
import sys
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
    write_manifest,
)


SOURCE_ID = "princeton_leuven_privacy_policies"
SOURCE_URL = "https://privacypolicies.cs.princeton.edu/"


def prepare_princeton_database(input_path: Path, output_root: Path) -> dict[str, object]:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_dir = output_root / SOURCE_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "release_db.sqlite"
    partial_path = output_dir / "release_db.sqlite.partial"

    if database_path.is_file() and _has_sqlite_header(database_path):
        reused = True
    else:
        if partial_path.exists():
            raise FileExistsError(
                f"Incomplete Princeton expansion exists: {partial_path}. Inspect it before retrying."
            )
        reused = False
        written = 0
        with lzma.open(input_path, "rb") as source, partial_path.open("xb") as target:
            while chunk := source.read(8 * 1024 * 1024):
                target.write(chunk)
                written += len(chunk)
                if written and written % (1024 * 1024 * 1024) < len(chunk):
                    print(f"expanded_gib={written / (1024 ** 3):.1f}", flush=True)
        if not _has_sqlite_header(partial_path):
            raise ValueError("Expanded Princeton file is not a SQLite database")
        partial_path.rename(database_path)

    database = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    schema = [
        {"name": name, "type": object_type, "sql": sql}
        for name, object_type, sql in database.execute(
            "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
        )
    ]
    table_counts = {
        item["name"]: database.execute(f'SELECT COUNT(*) FROM "{item["name"]}"').fetchone()[0]
        for item in schema
        if item["type"] == "table"
    }
    database.close()

    result = {
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "status": "database_ready",
        "decision_method": "xz_stream_expansion_and_sqlite_schema_probe",
        "reused_existing_database": reused,
        "input_file": input_file_descriptor(input_path),
        "database": {
            "name": database_path.name,
            "bytes": database_path.stat().st_size,
            "sha256": sha256_file(database_path),
        },
        "schema": schema,
        "table_counts": table_counts,
    }
    (output_dir / "database-profile.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def convert_princeton_policies(database_path: Path, output_root: Path) -> dict[str, object]:
    if not database_path.is_file() or not _has_sqlite_header(database_path):
        raise ValueError(f"Princeton SQLite database is missing or invalid: {database_path}")
    output_dir = output_root / SOURCE_ID
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "documents.jsonl"
    partial_path = output_dir / "documents.jsonl.partial"
    if partial_path.exists():
        raise FileExistsError(f"Incomplete Princeton output exists: {partial_path}")

    database = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    database.execute("PRAGMA query_only = ON")
    database.execute("PRAGMA temp_store = FILE")
    years: Counter[int] = Counter()
    content_hashes: set[str] = set()
    snapshot_count = 0
    document_count = 0
    try:
        with partial_path.open("x", encoding="utf-8", newline="\n") as output:
            for record, capture_years in _iter_policy_records(database):
                output.write(json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")))
                output.write("\n")
                document_count += 1
                content_hashes.add(record.content_sha256)
                snapshot_count += len(capture_years)
                years.update(capture_years)
                if document_count % 10_000 == 0:
                    print(f"normalized_documents={document_count}", flush=True)
    except Exception:
        raise
    finally:
        database.close()

    partial_path.replace(output_path)
    profile_path = output_dir / "database-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.is_file() else {}
    manifest = {
        "schema_version": STAGING_SCHEMA_VERSION,
        "source_id": SOURCE_ID,
        "source_url": SOURCE_URL,
        "conversion_scope": "all_unique_policy_texts_with_all_snapshot_provenance",
        "decision_method": "sqlite_schema_probe_and_streaming_relational_merge",
        "document_count": document_count,
        "unique_content_count": len(content_hashes),
        "duplicate_content_count": document_count - len(content_hashes),
        "snapshot_count": snapshot_count,
        "year_counts": {str(year): count for year, count in sorted(years.items())},
        "input_database": profile.get(
            "database",
            {"name": database_path.name, "bytes": database_path.stat().st_size},
        ),
        "input_profile": {
            "name": profile_path.name,
            "bytes": profile_path.stat().st_size,
            "sha256": sha256_file(profile_path),
        }
        if profile_path.is_file()
        else None,
        "output": {
            "name": output_path.name,
            "bytes": output_path.stat().st_size,
            "sha256": sha256_file(output_path),
        },
        "review_status": "needs_review",
        "license_notes": "Research corpus terms and original website rights require review before reuse.",
    }
    write_manifest(output_dir / "manifest.json", manifest)
    return manifest


def _iter_policy_records(
    database: sqlite3.Connection,
) -> Iterator[tuple[NormalizedTermsRecord, list[int]]]:
    source_database = Path(str(database.execute("PRAGMA database_list").fetchone()[2])).name
    snapshots = database.execute(
        """
        SELECT ps.policy_text_id, ps.id, s.domain, s.categories, ps.year, ps.phase,
               ps.policy_url, ps.policy_snapshot_url, ps.homepage_snapshot_url,
               ps.policy_title, ps.file_type, ps.classifier_probability,
               ps.analysis_subcorpus
        FROM policy_snapshots ps
        JOIN sites s ON s.id = ps.site_id
        WHERE ps.policy_text_id IS NOT NULL
        ORDER BY ps.policy_text_id, ps.id
        """
    )
    snapshot = snapshots.fetchone()
    texts = database.execute(
        """
        SELECT id, policy_text, sha1, flesch_kincaid, smog, flesch_ease, length, simhash
        FROM policy_texts
        ORDER BY id
        """
    )
    for text_row in texts:
        text_id = int(text_row[0])
        captures: list[dict[str, object]] = []
        capture_years: list[int] = []
        while snapshot is not None and int(snapshot[0]) < text_id:
            snapshot = snapshots.fetchone()
        while snapshot is not None and int(snapshot[0]) == text_id:
            year = int(snapshot[4])
            capture_years.append(year)
            captures.append(
                {
                    "snapshot_id": int(snapshot[1]),
                    "domain": snapshot[2] or "",
                    "site_categories": snapshot[3] or "",
                    "year": year,
                    "phase": snapshot[5] or "",
                    "policy_url": snapshot[6] or "",
                    "policy_snapshot_url": snapshot[7] or "",
                    "homepage_snapshot_url": snapshot[8] or "",
                    "policy_title": snapshot[9] or "",
                    "file_type": snapshot[10] or "",
                    "classifier_probability": snapshot[11],
                    "analysis_subcorpus": snapshot[12],
                }
            )
            snapshot = snapshots.fetchone()
        if not captures:
            raise ValueError(f"Princeton policy_texts row has no snapshot: {text_id}")
        text = normalize_text(str(text_row[1]))
        if not text:
            raise ValueError(f"Princeton policy_texts row is empty: {text_id}")
        first_year = min(capture_years)
        last_year = max(capture_years)
        version_at = str(first_year) if first_year == last_year else f"{first_year}-{last_year}"
        yield (
            NormalizedTermsRecord(
                record_id=stable_record_id(SOURCE_ID, str(text_id)),
                source_id=SOURCE_ID,
                split="all",
                locale="en",
                service_name=str(captures[0]["domain"]),
                document_type="privacy_policy",
                category="privacy_policy_longitudinal",
                version_at=version_at,
                text=text,
                content_sha256=sha256_text(text),
                review_status="needs_review",
                license_notes="Research corpus terms and original website rights require review before reuse.",
                provenance={
                    "source_url": SOURCE_URL,
                    "source_database": source_database,
                    "source_policy_text_id": str(text_id),
                    "source_sha1": text_row[2] or "",
                    "source_length": str(text_row[6] or ""),
                    "snapshot_count": str(len(captures)),
                },
                annotations=[
                    {
                        "kind": "readability",
                        "flesch_kincaid": text_row[3],
                        "smog": text_row[4],
                        "flesch_ease": text_row[5],
                        "simhash": text_row[7],
                    },
                    *captures,
                ],
                record_type="privacy_policy_document",
            ),
            capture_years,
        )


def _has_sqlite_header(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(16) == b"SQLite format 3\x00"


def main() -> None:
    if len(sys.argv) == 3:
        result = prepare_princeton_database(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    elif len(sys.argv) == 4 and sys.argv[1] == "prepare":
        result = prepare_princeton_database(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    elif len(sys.argv) == 4 and sys.argv[1] == "convert":
        result = convert_princeton_policies(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    else:
        raise SystemExit(
            "usage: python -m app.services.dataset_adapters.princeton "
            "[prepare INPUT_XZ | convert DATABASE] OUTPUT_ROOT"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
