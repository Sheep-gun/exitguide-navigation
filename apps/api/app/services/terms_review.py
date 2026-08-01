from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.terms_corpus import DEFAULT_DB_PATH, build_terms_corpus_sqlite


REVIEW_DECISIONS = {
    "approved_for_search",
    "rejected_license",
    "rejected_privacy",
    "rejected_quality",
    "deprecated",
}


def record_terms_review_decision(
    db_path: Path,
    version_id: str,
    decision: str,
    reviewer: str,
    reason: str,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    version_id = version_id.strip()
    decision = decision.strip()
    reviewer = reviewer.strip()
    reason = reason.strip()
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"unsupported review decision: {decision}")
    if not version_id:
        raise ValueError("version_id is required")
    if not reviewer:
        raise ValueError("reviewer is required")
    if not reason:
        raise ValueError("reason is required")
    if not db_path.exists():
        raise FileNotFoundError(f"terms corpus database does not exist: {db_path}")

    created_at = datetime.now(timezone.utc).isoformat()
    event_digest = hashlib.sha256(
        f"{version_id}:{decision}:{reviewer}:{reason}:{created_at}".encode("utf-8")
    ).hexdigest()[:20]
    event_id = f"tre_{event_digest}"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        has_registry = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'terms_document_versions'"
        ).fetchone()
        if not has_registry:
            raise ValueError("terms review registry is not initialized")
        row = connection.execute(
            "SELECT source_id, is_current, review_status FROM terms_document_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"terms document version was not found: {version_id}")
        connection.execute(
            "UPDATE terms_document_versions SET review_status = ? WHERE version_id = ?",
            (decision, version_id),
        )
        connection.execute(
            """
            INSERT INTO terms_review_events (event_id, version_id, reviewer, decision, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, version_id, reviewer, decision, reason, created_at),
        )
        connection.commit()
        previous_status = row["review_status"]
        is_current = bool(row["is_current"])
        source_id = row["source_id"]
    finally:
        connection.close()

    build_terms_corpus_sqlite(db_path)
    return {
        "event_id": event_id,
        "version_id": version_id,
        "source_id": source_id,
        "previous_status": previous_status,
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "created_at": created_at,
        "is_current": is_current,
        "search_eligible": is_current and decision == "approved_for_search",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an audited terms-document review decision.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--version-id", required=True)
    parser.add_argument("--decision", required=True, choices=sorted(REVIEW_DECISIONS))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    result = record_terms_review_decision(
        db_path=args.db,
        version_id=args.version_id,
        decision=args.decision,
        reviewer=args.reviewer,
        reason=args.reason,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
