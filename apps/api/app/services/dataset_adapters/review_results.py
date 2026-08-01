from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.services.dataset_adapters.common import input_file_descriptor, sha256_file, write_manifest


RESULT_SCHEMA_VERSION = "1.0"
LICENSE_STATUSES = {"unknown", "research_only", "redistributable", "blocked"}
SEARCHABLE_LICENSE_STATUSES = {"research_only", "redistributable"}
PRIVACY_STATUSES = {"clear", "redaction_required", "blocked"}
PARSE_QUALITIES = {"pass", "minor_issue", "major_issue"}
ANNOTATION_QUALITIES = {"correct", "incorrect", "uncertain", "not_applicable"}
FINAL_DECISIONS = {"candidate_for_search", "needs_followup", "reject"}
REVIEW_COLUMNS = (
    "reviewer",
    "license_status",
    "privacy_status",
    "parse_quality",
    "annotation_quality",
    "final_decision",
    "reason",
)


def validate_public_corpus_review(
    checklist_path: Path,
    review_items_path: Path,
    source_review_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    items = _load_review_items(review_items_path)
    source_reviews = _load_source_reviews(source_review_path)
    rows = _load_checklist(checklist_path)
    if set(rows) != set(items):
        missing = sorted(set(items) - set(rows))
        unknown = sorted(set(rows) - set(items))
        raise ValueError(f"review checklist item coverage mismatch: missing={missing[:5]}, unknown={unknown[:5]}")

    results: list[dict[str, Any]] = []
    counters: Counter[str] = Counter()
    section_decisions: dict[tuple[str, str], set[str]] = {}
    for item_id in sorted(items):
        item = items[item_id]
        row = rows[item_id]
        _validate_identity_fields(row, item)
        review = {column: row.get(column, "").strip() for column in REVIEW_COLUMNS}
        if not any(review.values()):
            counters["pending_count"] += 1
            continue
        empty = [column for column, value in review.items() if not value]
        if empty:
            raise ValueError(f"partially completed review row {item_id}: missing={empty}")
        _validate_review_values(item, review)
        source_review = source_reviews.get(item["source_id"])
        if source_review is None:
            raise ValueError(f"source review is missing for {item['source_id']}")
        eligible = _is_eligible_for_pending_import(item_id, review, source_review)
        section_id = item["section"]["section_id"]
        section_key = (item["source_id"], section_id)
        section_decisions.setdefault(section_key, set()).add(review["final_decision"])
        normalized_review = json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        results.append(
            {
                "schema_version": RESULT_SCHEMA_VERSION,
                "review_item_id": item_id,
                "source_id": item["source_id"],
                "document_record_id": item["document_record_id"],
                "section_id": section_id,
                "section_content_sha256": item["section"]["content_sha256"],
                "source_content_sha256": item["source_content_sha256"],
                "review": review,
                "source_review": source_review,
                "annotation_usable": bool(item.get("annotation")) and review["annotation_quality"] == "correct",
                "eligible_for_pending_import": eligible,
                "review_sha256": hashlib.sha256(normalized_review.encode("utf-8")).hexdigest(),
            }
        )
        counters["completed_count"] += 1
        counters[f"decision_{review['final_decision']}_count"] += 1
        if eligible:
            counters["eligible_for_pending_import_count"] += 1

    conflicts = [
        f"{source_id}:{section_id}"
        for (source_id, section_id), decisions in section_decisions.items()
        if len(decisions) > 1
    ]
    if conflicts:
        raise ValueError(f"conflicting final decisions for the same section: {conflicts[:5]}")

    output_root.mkdir(parents=True, exist_ok=True)
    results_path = output_root / "validated-results.jsonl"
    with results_path.open("w", encoding="utf-8", newline="\n") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
    source_status_counts = Counter(
        "reviewed" if review["reviewed"] else "pending" for review in source_reviews.values()
    )
    summary = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "ai_used": False,
        "search_approval_changed": False,
        "review_item_count": len(items),
        "source_review_counts": dict(sorted(source_status_counts.items())),
        "counters": dict(sorted(counters.items())),
        "inputs": {
            "checklist": input_file_descriptor(checklist_path),
            "review_items": input_file_descriptor(review_items_path),
            "source_review": input_file_descriptor(source_review_path),
        },
        "outputs": {
            "validated_results": {
                "name": results_path.name,
                "bytes": results_path.stat().st_size,
                "sha256": sha256_file(results_path),
                "record_count": len(results),
            }
        },
    }
    write_manifest(output_root / "summary.json", summary)
    return summary


def _load_review_items(path: Path) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            item_id = item["review_item_id"]
            if item_id in items:
                raise ValueError(f"duplicate review item id: {item_id}")
            items[item_id] = item
    return items


def _load_checklist(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_columns = set(REVIEW_COLUMNS) | {"review_item_id"}
        missing_columns = sorted(required_columns - set(reader.fieldnames or []))
        if missing_columns:
            raise ValueError(f"review checklist is missing columns: {missing_columns}")
        for row in reader:
            item_id = (row.get("review_item_id") or "").strip()
            if not item_id:
                raise ValueError("review checklist contains a blank review_item_id")
            if item_id in rows:
                raise ValueError(f"duplicate checklist review_item_id: {item_id}")
            rows[item_id] = {key: value or "" for key, value in row.items() if key is not None}
    return rows


def _load_source_reviews(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    reviews: dict[str, dict[str, Any]] = {}
    for raw in payload.get("sources", []):
        source_id = str(raw.get("source_id", "")).strip()
        if not source_id or source_id in reviews:
            raise ValueError(f"invalid or duplicate source review id: {source_id}")
        license_status = str(raw.get("license_status", "")).strip()
        reviewer = str(raw.get("reviewer", "")).strip()
        reason = str(raw.get("reason", "")).strip()
        reviewed_at = str(raw.get("reviewed_at", "")).strip()
        evidence_urls = raw.get("evidence_urls", [])
        local_search_allowed = raw.get("local_search_allowed", False)
        if not isinstance(local_search_allowed, bool) or not isinstance(evidence_urls, list):
            raise ValueError(f"invalid source review types for {source_id}")
        reviewed_values = [license_status, reviewer, reason, reviewed_at, *[str(url).strip() for url in evidence_urls]]
        reviewed = any(reviewed_values) or local_search_allowed
        if reviewed:
            if license_status not in LICENSE_STATUSES:
                raise ValueError(f"invalid source license_status for {source_id}: {license_status}")
            if not reviewer or not reason or not reviewed_at:
                raise ValueError(f"source review is incomplete for {source_id}")
            _parse_datetime(reviewed_at, source_id)
            if local_search_allowed:
                if license_status not in SEARCHABLE_LICENSE_STATUSES:
                    raise ValueError(f"source cannot allow local search with license status {license_status}: {source_id}")
                if not evidence_urls:
                    raise ValueError(f"source local-search approval requires evidence URL: {source_id}")
            for url in evidence_urls:
                parsed = urlparse(str(url))
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError(f"invalid source evidence URL for {source_id}: {url}")
        reviews[source_id] = {
            "source_id": source_id,
            "license_status": license_status,
            "local_search_allowed": local_search_allowed,
            "reviewer": reviewer,
            "reason": reason,
            "reviewed_at": reviewed_at,
            "evidence_urls": [str(url).strip() for url in evidence_urls],
            "reviewed": reviewed,
        }
    return reviews


def _validate_identity_fields(row: dict[str, str], item: dict[str, Any]) -> None:
    expected = {
        "source_id": item["source_id"],
        "stratum": item["stratum"],
        "document_record_id": item["document_record_id"],
    }
    for field, expected_value in expected.items():
        if row.get(field, "").strip() != expected_value:
            raise ValueError(f"immutable checklist field changed for {item['review_item_id']}: {field}")


def _validate_review_values(item: dict[str, Any], review: dict[str, str]) -> None:
    item_id = item["review_item_id"]
    allowed = {
        "license_status": LICENSE_STATUSES,
        "privacy_status": PRIVACY_STATUSES,
        "parse_quality": PARSE_QUALITIES,
        "annotation_quality": ANNOTATION_QUALITIES,
        "final_decision": FINAL_DECISIONS,
    }
    for field, values in allowed.items():
        if review[field] not in values:
            raise ValueError(f"invalid {field} for {item_id}: {review[field]}")
    if len(review["reason"]) < 10:
        raise ValueError(f"review reason is too short for {item_id}")
    has_annotation = bool(item.get("annotation"))
    if has_annotation and review["annotation_quality"] == "not_applicable":
        raise ValueError(f"annotation review cannot be not_applicable: {item_id}")
    if not has_annotation and review["annotation_quality"] != "not_applicable":
        raise ValueError(f"non-annotation review must be not_applicable: {item_id}")


def _is_eligible_for_pending_import(
    item_id: str,
    review: dict[str, str],
    source_review: dict[str, Any],
) -> bool:
    if review["final_decision"] != "candidate_for_search":
        return False
    if not source_review["reviewed"] or not source_review["local_search_allowed"]:
        raise ValueError(f"candidate row requires reviewed source local-search approval: {item_id}")
    if review["license_status"] != source_review["license_status"]:
        raise ValueError(f"row/source license status mismatch: {item_id}")
    if review["privacy_status"] != "clear":
        raise ValueError(f"candidate row must have clear privacy status: {item_id}")
    if review["parse_quality"] != "pass":
        raise ValueError(f"candidate row must have passing parse quality: {item_id}")
    return True


def _parse_datetime(value: str, source_id: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid source reviewed_at for {source_id}: {value}") from error
    if parsed.utcoffset() is None:
        raise ValueError(f"source reviewed_at must include timezone: {source_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate completed public-corpus human review fields.")
    parser.add_argument("--checklist", type=Path, required=True)
    parser.add_argument("--review-items", type=Path, required=True)
    parser.add_argument("--source-review", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    summary = validate_public_corpus_review(
        checklist_path=args.checklist,
        review_items_path=args.review_items,
        source_review_path=args.source_review,
        output_root=args.output_root,
    )
    print(json.dumps(summary["counters"], ensure_ascii=False))


if __name__ == "__main__":
    main()
