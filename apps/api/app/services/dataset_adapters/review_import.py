from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import TermsDocument, TermsSection
from app.services.dataset_adapters.common import sha256_file
from app.services.terms_corpus import DEFAULT_DB_PATH, build_terms_corpus_sqlite
from app.services.terms_ingestion import ensure_terms_registry_tables


IMPORTER_VERSION = "public_review_import_v1"
SOURCE_DEFAULTS = {
    "ftc_standard_terms": {
        "provider_name": "Korea Fair Trade Commission",
        "source_url": "https://www.ftc.go.kr/www/selectBbsNttList.do?bordCd=201&key=202",
    },
    "aihub_legal_regulation_terms": {
        "provider_name": "AI Hub",
        "source_url": "https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=580",
    },
}


def import_reviewed_public_sections(
    validated_results_path: Path,
    review_items_path: Path,
    processed_root: Path,
    db_path: Path = DEFAULT_DB_PATH,
    apply: bool = False,
) -> dict[str, Any]:
    results = _load_jsonl(validated_results_path, "review_item_id")
    review_items = _load_jsonl(review_items_path, "review_item_id")
    eligible_results = [row for row in results.values() if row.get("eligible_for_pending_import")]
    eligible_by_section: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for result in eligible_results:
        _assert_result_eligible(result)
        item_id = result["review_item_id"]
        item = review_items.get(item_id)
        if not item:
            raise ValueError(f"validated result references unknown review item: {item_id}")
        if result["source_id"] != item["source_id"] or result["section_id"] != item["section"]["section_id"]:
            raise ValueError(f"validated result identity mismatch: {item_id}")
        if result["section_content_sha256"] != item["section"]["content_sha256"]:
            raise ValueError(f"validated result section hash mismatch: {item_id}")
        if result["source_content_sha256"] != item["source_content_sha256"]:
            raise ValueError(f"validated result source hash mismatch: {item_id}")
        eligible_by_section[(result["source_id"], result["section_id"])].append(result)

    selected_sections = _load_selected_sections(processed_root, eligible_by_section)
    documents = _build_pending_documents(eligible_by_section, selected_sections, review_items)
    preview = {
        "schema_version": "1.0",
        "apply": apply,
        "search_approval_changed": False,
        "validated_result_count": len(results),
        "eligible_review_count": len(eligible_results),
        "unique_section_count": len(eligible_by_section),
        "pending_document_count": len(documents),
        "source_counts": dict(sorted(Counter(document["dataset_source_id"] for document in documents).items())),
        "database": str(db_path.resolve()),
    }
    if not apply or not documents:
        return preview

    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    input_sha = sha256_file(validated_results_path)
    run_id = "pri_run_" + hashlib.sha256(f"{input_sha}:{created_at}".encode("utf-8")).hexdigest()[:20]
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        ensure_terms_registry_tables(connection)
        _ensure_public_import_tables(connection)
        imported_count = 0
        duplicate_count = 0
        for entry in documents:
            status, registered_version_id = _register_pending_document(connection, entry, created_at)
            if status == "imported":
                imported_count += 1
            else:
                duplicate_count += 1
            for result in entry["review_results"]:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO terms_public_review_item_links (
                      version_id, review_item_id, section_id, review_sha256,
                      source_review_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        registered_version_id,
                        result["review_item_id"],
                        result["section_id"],
                        result["review_sha256"],
                        json.dumps(result["source_review"], ensure_ascii=False, sort_keys=True),
                        created_at,
                    ),
                )
        connection.execute(
            """
            INSERT INTO terms_public_review_import_runs (
              run_id, validated_results_sha256, imported_document_count,
              duplicate_document_count, section_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, input_sha, imported_count, duplicate_count, len(eligible_by_section), created_at),
        )
        connection.commit()
    finally:
        connection.close()
    build_terms_corpus_sqlite(db_path)
    preview.update(
        {
            "run_id": run_id,
            "imported_document_count": imported_count,
            "duplicate_document_count": duplicate_count,
        }
    )
    return preview


def _load_jsonl(path: Path, key_field: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = str(row[key_field])
            if key in rows:
                raise ValueError(f"duplicate {key_field}: {key}")
            rows[key] = row
    return rows


def _load_selected_sections(
    processed_root: Path,
    eligible_by_section: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[tuple[str, str], dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    source_ids = sorted({source_id for source_id, _section_id in eligible_by_section})
    for source_id in source_ids:
        sections_path = processed_root / source_id / "sections.jsonl"
        if not sections_path.exists():
            raise FileNotFoundError(f"processed sections file does not exist: {sections_path}")
        with sections_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                section = json.loads(line)
                key = (source_id, section["section_id"])
                if key not in eligible_by_section:
                    continue
                expected_hashes = {result["section_content_sha256"] for result in eligible_by_section[key]}
                if len(expected_hashes) != 1 or section["content_sha256"] not in expected_hashes:
                    raise ValueError(f"processed section hash mismatch: {source_id}:{section['section_id']}")
                expected_source_hashes = {result["source_content_sha256"] for result in eligible_by_section[key]}
                if len(expected_source_hashes) != 1 or section["source_content_sha256"] not in expected_source_hashes:
                    raise ValueError(f"processed source hash mismatch: {source_id}:{section['section_id']}")
                selected[key] = section
    missing = sorted(set(eligible_by_section) - set(selected))
    if missing:
        raise ValueError(f"eligible sections were not found in processed corpus: {missing[:5]}")
    return selected


def _build_pending_documents(
    eligible_by_section: dict[tuple[str, str], list[dict[str, Any]]],
    selected_sections: dict[tuple[str, str], dict[str, Any]],
    review_items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], list[dict[str, Any]]]]] = defaultdict(list)
    for key, results in eligible_by_section.items():
        section = selected_sections[key]
        grouped[(key[0], section["document_record_id"])].append((section, results))

    documents: list[dict[str, Any]] = []
    for (dataset_source_id, document_record_id), section_entries in sorted(grouped.items()):
        defaults = SOURCE_DEFAULTS.get(dataset_source_id)
        if not defaults:
            raise ValueError(f"unsupported reviewed public source: {dataset_source_id}")
        section_entries.sort(key=lambda entry: int(entry[0]["section_index"]))
        all_results = [result for _section, results in section_entries for result in results]
        first_item = review_items[all_results[0]["review_item_id"]]
        source_review = all_results[0]["source_review"]
        if any(result["source_review"] != source_review for result in all_results):
            raise ValueError(f"inconsistent source review within document: {document_record_id}")
        section_ids = [section["section_id"] for section, _results in section_entries]
        version_digest = hashlib.sha256(
            f"{dataset_source_id}:{document_record_id}:{':'.join(section_ids)}".encode("utf-8")
        ).hexdigest()[:20]
        version_id = f"tpv_{version_digest}"
        service_name = first_item.get("service_name") or first_item.get("provenance", {}).get("original_name")
        if not service_name:
            service_name = f"{defaults['provider_name']} {document_record_id}"
        terms_sections = [
            TermsSection(id=section["section_id"], heading=section["heading"], text=section["text"])
            for section, _results in section_entries
        ]
        document_type = first_item.get("document_type", "terms_of_service")
        if document_type not in {
            "terms_of_service",
            "privacy_policy",
            "subscription_terms",
            "location_terms",
            "marketing_terms",
            "cancellation_policy",
            "unknown",
        }:
            document_type = "terms_of_service"
        license_notes = (
            f"{first_item.get('license_notes', '')} | local review: "
            f"{source_review['license_status']} ({source_review['reason']})"
        ).strip(" |")
        document = TermsDocument(
            id=version_id,
            service_name=service_name,
            provider_name=defaults["provider_name"],
            document_type=document_type,
            locale=first_item.get("locale") or "ko-KR",
            source_url=first_item.get("provenance", {}).get("source_url") or defaults["source_url"],
            collected_at=first_item.get("version_at") or "source-date-unknown",
            collection_method="imported",
            retrieval_status="needs_review",
            public_fixture_allowed=False,
            raw_personal_data=False,
            license_notes=license_notes,
            tags=["reviewed_public", dataset_source_id],
            sections=terms_sections,
        )
        documents.append(
            {
                "dataset_source_id": dataset_source_id,
                "registry_source_id": f"public:{dataset_source_id}:{document_record_id}",
                "document_record_id": document_record_id,
                "document": document,
                "source_review": source_review,
                "review_results": all_results,
            }
        )
    return documents


def _assert_result_eligible(result: dict[str, Any]) -> None:
    item_id = result.get("review_item_id", "")
    review = result.get("review", {})
    source_review = result.get("source_review", {})
    normalized_review = json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected_review_sha = hashlib.sha256(normalized_review.encode("utf-8")).hexdigest()
    if result.get("review_sha256") != expected_review_sha:
        raise ValueError(f"validated review hash mismatch: {item_id}")
    if review.get("final_decision") != "candidate_for_search":
        raise ValueError(f"eligible result is not a search candidate: {item_id}")
    if review.get("privacy_status") != "clear" or review.get("parse_quality") != "pass":
        raise ValueError(f"eligible result failed privacy or parse gate: {item_id}")
    if not source_review.get("reviewed") or not source_review.get("local_search_allowed"):
        raise ValueError(f"eligible result source is not approved for local search: {item_id}")
    if source_review.get("license_status") not in {"research_only", "redistributable"}:
        raise ValueError(f"eligible result source has unsupported license status: {item_id}")
    if review.get("license_status") != source_review.get("license_status"):
        raise ValueError(f"eligible result row/source license mismatch: {item_id}")
    if not source_review.get("reviewer") or not source_review.get("reason") or not source_review.get("evidence_urls"):
        raise ValueError(f"eligible result source review is incomplete: {item_id}")


def _register_pending_document(
    connection: sqlite3.Connection,
    entry: dict[str, Any],
    created_at: str,
) -> tuple[str, str]:
    document: TermsDocument = entry["document"]
    source_id = entry["registry_source_id"]
    source_review = entry["source_review"]
    text_sha = hashlib.sha256(
        "\n\n".join(section.text for section in document.sections).encode("utf-8")
    ).hexdigest()
    existing = connection.execute(
        "SELECT content_sha256, document_json FROM terms_document_versions WHERE version_id = ?",
        (document.id,),
    ).fetchone()
    if existing:
        if existing[0] != text_sha or json.loads(existing[1]) != json.loads(document.model_dump_json()):
            raise ValueError(f"existing public review version differs from import: {document.id}")
        return "duplicate", document.id
    existing_content = connection.execute(
        "SELECT version_id FROM terms_document_versions WHERE content_sha256 = ?",
        (text_sha,),
    ).fetchone()
    if existing_content:
        return "duplicate", existing_content[0]

    connection.execute(
        """
        INSERT INTO terms_sources (
          source_id, service_name, provider_name, document_type, canonical_url,
          source_url, collection_policy_status, robots_checked_at, robots_allowed,
          license_review_status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
          service_name = excluded.service_name,
          provider_name = excluded.provider_name,
          source_url = excluded.source_url,
          collection_policy_status = excluded.collection_policy_status,
          license_review_status = excluded.license_review_status
        """,
        (
            source_id,
            document.service_name,
            document.provider_name,
            document.document_type,
            document.source_url,
            document.source_url,
            "reviewed_for_local_search",
            "",
            0,
            source_review["license_status"],
            created_at,
        ),
    )
    previous = connection.execute(
        "SELECT version_id FROM terms_document_versions WHERE source_id = ? AND is_current = 1",
        (source_id,),
    ).fetchone()
    previous_version_id = previous[0] if previous else None
    connection.execute("UPDATE terms_document_versions SET is_current = 0 WHERE source_id = ?", (source_id,))
    connection.execute(
        """
        INSERT INTO terms_document_versions (
          version_id, source_id, collected_at, collector, collector_version,
          retrieval_status, http_status, final_url, content_sha256, text_sha256,
          locale, is_current, supersedes_version_id, review_status,
          document_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document.id,
            source_id,
            document.collected_at,
            "imported",
            IMPORTER_VERSION,
            document.retrieval_status,
            "",
            document.source_url,
            text_sha,
            text_sha,
            document.locale,
            1,
            previous_version_id,
            "pending_review",
            document.model_dump_json(),
            created_at,
        ),
    )
    return "imported", document.id


def _ensure_public_import_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS terms_public_review_import_runs (
          run_id TEXT PRIMARY KEY,
          validated_results_sha256 TEXT NOT NULL,
          imported_document_count INTEGER NOT NULL,
          duplicate_document_count INTEGER NOT NULL,
          section_count INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS terms_public_review_item_links (
          version_id TEXT NOT NULL,
          review_item_id TEXT NOT NULL,
          section_id TEXT NOT NULL,
          review_sha256 TEXT NOT NULL,
          source_review_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY (version_id, review_item_id),
          FOREIGN KEY (version_id) REFERENCES terms_document_versions(version_id) ON DELETE CASCADE
        );
        """
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import validated public sections as pending terms versions.")
    parser.add_argument("--validated-results", type=Path, required=True)
    parser.add_argument("--review-items", type=Path, required=True)
    parser.add_argument("--processed-root", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = import_reviewed_public_sections(
        validated_results_path=args.validated_results,
        review_items_path=args.review_items,
        processed_root=args.processed_root,
        db_path=args.db,
        apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
