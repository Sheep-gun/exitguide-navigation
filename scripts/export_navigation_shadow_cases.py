#!/usr/bin/env python3
"""Export model-independent collector evidence for offline EXAONE shadow replay."""

from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Iterator


def _read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _candidate_labels(
    review: sqlite3.Connection | None,
    decision_id: str,
) -> list[dict[str, Any]]:
    if review is None or not _table_exists(review, "navigation_candidate_labels"):
        return []
    rows = review.execute(
        """
        SELECT candidate_id, reviewer, label_source, review_status, label,
               confidence, reason_codes_json, notes, updated_at
        FROM navigation_candidate_labels
        WHERE decision_id = ? ORDER BY candidate_id, reviewer
        """,
        (decision_id,),
    ).fetchall()
    return [
        {
            **{key: row[key] for key in row.keys() if key != "reason_codes_json"},
            "reason_codes": _json(row["reason_codes_json"], []),
        }
        for row in rows
    ]


def _screen(
    runtime: sqlite3.Connection,
    decision_id: str,
    phase: str,
) -> dict[str, Any] | None:
    row = runtime.execute(
        """
        SELECT snapshot_id, screen_fingerprint, screen_payload_json,
               candidate_set_status, candidates_total, candidates_captured,
               candidates_truncated, missing_parts_json, captured_at
        FROM navigation_screen_snapshots
        WHERE decision_id = ? AND phase = ?
        """,
        (decision_id, phase),
    ).fetchone()
    if row is None:
        return None
    candidates = runtime.execute(
        """
        SELECT candidate_id, ordinal, observed_payload_json
        FROM navigation_screen_candidates
        WHERE snapshot_id = ? ORDER BY ordinal
        """,
        (row["snapshot_id"],),
    ).fetchall()
    artifacts = runtime.execute(
        """
        SELECT artifact_type, storage_uri, mime_type, byte_size,
               redaction_status, retention_class
        FROM navigation_screen_artifacts
        WHERE snapshot_id = ? ORDER BY artifact_type, storage_uri
        """,
        (row["snapshot_id"],),
    ).fetchall()
    return {
        "screen_fingerprint": row["screen_fingerprint"],
        "screen": _json(row["screen_payload_json"], {}),
        "candidate_set_status": row["candidate_set_status"],
        "candidates_total": row["candidates_total"],
        "candidates_captured": row["candidates_captured"],
        "candidates_truncated": bool(row["candidates_truncated"]),
        "missing_parts": _json(row["missing_parts_json"], []),
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "ordinal": candidate["ordinal"],
                "observed": _json(candidate["observed_payload_json"], {}),
            }
            for candidate in candidates
        ],
        "artifacts": [dict(artifact) for artifact in artifacts],
        "captured_at": row["captured_at"],
    }


def iter_cases(
    runtime: sqlite3.Connection,
    review: sqlite3.Connection | None,
    *,
    include_locked_holdout: bool,
) -> Iterator[dict[str, Any]]:
    rows = runtime.execute(
        """
        SELECT d.decision_id, d.session_id, d.step_ordinal, d.action_name,
               d.candidate_id, d.scroll_direction, d.planner_provider,
               d.safety_status, d.safety_reason, d.decision_provenance_json,
               d.created_at, s.app_package, s.app_version, s.goal_text_redacted,
               s.goal_id, s.task_context_json, s.terminal_reason AS session_terminal_reason,
               s.handoff_reason AS session_handoff_reason,
               COALESCE(m.split, 'unassigned') AS dataset_split,
               o.connectivity_status, o.state_changed, o.outcome_type,
               o.progress_label, o.failure_class,
               o.terminal_reason AS observation_terminal_reason,
               o.handoff_reason AS observation_handoff_reason
        FROM navigation_decisions d
        JOIN navigation_sessions s ON s.session_id = d.session_id
        LEFT JOIN navigation_dataset_split_manifest m ON m.app_package = s.app_package
        LEFT JOIN navigation_observations o ON o.decision_id = d.decision_id
        ORDER BY d.created_at, d.session_id, d.step_ordinal
        """
    )
    for row in rows:
        split = str(row["dataset_split"])
        if split == "locked_holdout" and not include_locked_holdout:
            continue
        provenance = _json(row["decision_provenance_json"], {})
        yield {
            "schema_version": "navigation-shadow-case.v1",
            "decision_id": row["decision_id"],
            "session_id": row["session_id"],
            "step_ordinal": row["step_ordinal"],
            "dataset_split": split,
            "training_eligible": split in {"collection", "validation"},
            "app": {
                "package": row["app_package"],
                "version": row["app_version"],
            },
            "goal": {
                "text": row["goal_text_redacted"],
                "goal_id": row["goal_id"],
                "task_context": _json(row["task_context_json"], {}),
            },
            "before": _screen(runtime, row["decision_id"], "before"),
            "codex_choice": {
                "action_name": row["action_name"],
                "candidate_id": row["candidate_id"],
                "scroll_direction": row["scroll_direction"],
                "planner_provider": row["planner_provider"],
                "operator_command": provenance.get("operator_command"),
            },
            "safety": {
                "status": row["safety_status"],
                "reason": row["safety_reason"],
            },
            "observed_result": {
                "connectivity_status": row["connectivity_status"],
                "state_changed": None
                if row["state_changed"] is None
                else bool(row["state_changed"]),
                "outcome_type": row["outcome_type"],
                "progress_label": row["progress_label"],
                "failure_class": row["failure_class"],
                "terminal_reason": row["observation_terminal_reason"],
                "handoff_reason": row["observation_handoff_reason"],
                "after": _screen(runtime, row["decision_id"], "after"),
            },
            "session_end": {
                "terminal_reason": row["session_terminal_reason"],
                "handoff_reason": row["session_handoff_reason"],
            },
            "candidate_labels": _candidate_labels(review, row["decision_id"]),
            "created_at": row["created_at"],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-db", type=Path, required=True)
    parser.add_argument("--review-db", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-locked-holdout", action="store_true")
    args = parser.parse_args()

    review = None
    if args.review_db is not None and args.review_db.is_file():
        review = _read_only(args.review_db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(_read_only(args.runtime_db)) as runtime, args.output.open(
            "w", encoding="utf-8", newline="\n"
        ) as output:
            for case in iter_cases(
                runtime,
                review,
                include_locked_holdout=args.include_locked_holdout,
            ):
                output.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    finally:
        if review is not None:
            review.close()


if __name__ == "__main__":
    main()
