from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


LEGACY_ROUTE_TABLES = {
    "universal_routes",
    "universal_app_function_routes",
    "route_rankings",
    "route_performance",
}
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
RAW_ELEMENT_PATTERN = re.compile(r"\b(?:an|ocr)_[a-f0-9]{12,}\b", re.IGNORECASE)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _visible_observation_texts(value: str) -> Iterable[str]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return ()
    result: list[str] = []

    def visit(item: object, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child_value in item.items():
                visit(child_value, str(child_key))
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str) and key in {"label", "labels", "window_title", "summary", "text"}:
            result.append(item)

    visit(payload)
    return result


def _contains_coordinate_key(value: str) -> bool:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return False

    def visit(item: object) -> bool:
        if isinstance(item, dict):
            if any(str(key).casefold() in {"bounds", "x", "y", "left", "top", "right", "bottom"} for key in item):
                return True
            return any(visit(child) for child in item.values())
        if isinstance(item, list):
            return any(visit(child) for child in item)
        return False

    return visit(payload)


def validate(database: Path, *, expected_source_sha256: str) -> dict[str, object]:
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    metadata = dict(connection.execute("SELECT key,value FROM navigation_db_metadata"))
    table_names = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    foreign_key_violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    duplicate_split_apps = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT app_package FROM evaluation_app_splits
                GROUP BY app_package HAVING COUNT(DISTINCT split) > 1
            )
            """
        ).fetchone()[0]
    )
    cases_without_split = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM decision_cases AS c
            LEFT JOIN evaluation_app_splits AS s
              ON s.app_package=c.source_app_package AND s.split_version='app-disjoint-v1'
            WHERE s.app_package IS NULL
            """
        ).fetchone()[0]
    )
    invalid_connectivity = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM transition_outcomes
            WHERE connectivity_status <> 'observed'
              AND (next_screen_id IS NOT NULL OR state_changed IS NOT NULL OR progress_label <> 'unknown')
            """
        ).fetchone()[0]
    )
    dangerous_final_clicks = int(
        connection.execute(
            """
            SELECT COUNT(*) FROM decision_cases AS c
            JOIN affordances AS a ON a.affordance_id=c.chosen_affordance_id
            WHERE c.chosen_action='click' AND a.dangerous_final=1
            """
        ).fetchone()[0]
    )
    stop_for_user_cases = int(
        connection.execute(
            "SELECT COUNT(*) FROM decision_cases WHERE chosen_action='stop_for_user'"
        ).fetchone()[0]
    )
    visible_texts: list[str] = []
    for table, column in (
        ("semantic_screens", "title_normalized"),
        ("affordances", "label"),
        ("affordances", "parent_semantics"),
        ("affordances", "nearby_text"),
        ("decision_cases", "goal_text_normalized"),
    ):
        visible_texts.extend(str(row[0] or "") for row in connection.execute(f'SELECT "{column}" FROM "{table}"'))
    observation_values = [
        str(value or "")
        for row in connection.execute(
            "SELECT accessibility_json,ocr_json,vlm_json FROM screen_observations"
        )
        for value in row
    ]
    for value in observation_values:
        visible_texts.extend(_visible_observation_texts(value))
    unredacted_email_hits = sum(bool(EMAIL_PATTERN.search(value)) for value in visible_texts)
    unredacted_phone_hits = sum(bool(PHONE_PATTERN.search(value)) for value in visible_texts)
    raw_element_id_hits = sum(bool(RAW_ELEMENT_PATTERN.search(value)) for value in visible_texts)
    raw_coordinate_documents = sum(_contains_coordinate_key(value) for value in observation_values)
    checks = {
        "sqlite_quick_check": connection.execute("PRAGMA quick_check").fetchone()[0] == "ok",
        "foreign_key_violations_zero": foreign_key_violations == 0,
        "schema_version_is_1": int(connection.execute("PRAGMA user_version").fetchone()[0]) == 1 and metadata.get("schema_version") == "1",
        "source_sha256_matches": metadata.get("source_sha256") == expected_source_sha256,
        "legacy_route_tables_absent": not (LEGACY_ROUTE_TABLES & table_names),
        "app_split_has_no_leak": duplicate_split_apps == 0 and cases_without_split == 0,
        "connectivity_not_conflated_with_navigation": invalid_connectivity == 0,
        "dangerous_final_clicks_zero": dangerous_final_clicks == 0,
        "safe_stop_examples_present": stop_for_user_cases > 0,
        "unredacted_email_hits_zero": unredacted_email_hits == 0,
        "unredacted_phone_hits_zero": unredacted_phone_hits == 0,
        "raw_element_ids_absent_from_visible_text": raw_element_id_hits == 0,
        "raw_coordinates_absent": raw_coordinate_documents == 0,
    }
    counts = {
        table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        for table in (
            "goals", "goal_phrases", "goal_relations", "destination_signatures",
            "affordance_roles", "affordance_role_aliases", "semantic_screens",
            "screen_observations", "affordances", "decision_cases", "transition_outcomes",
            "recovery_memories", "evidence_records", "evaluation_app_splits",
        )
    }
    goal_case_counts = dict(
        connection.execute(
            "SELECT goal_id,COUNT(*) FROM decision_cases GROUP BY goal_id ORDER BY goal_id"
        )
    )
    goal_app_counts = dict(
        connection.execute(
            "SELECT goal_id,COUNT(DISTINCT source_app_package) FROM decision_cases GROUP BY goal_id ORDER BY goal_id"
        )
    )
    vlm_observations = int(
        connection.execute(
            "SELECT COUNT(*) FROM screen_observations WHERE vlm_json NOT IN ('{}','null','')"
        ).fetchone()[0]
    )
    warnings: list[str] = []
    if int(goal_case_counts.get("membership.manage", 0)) == 0:
        warnings.append("membership.manage has no migrated verified decision case")
    if int(goal_app_counts.get("membership.join", 0)) < 2:
        warnings.append("membership.join has fewer than two source apps and is not generalization-ready")
    if vlm_observations == 0:
        warnings.append("legacy source has no VLM observations; v1 migrated screens use Accessibility/OCR only")
    connection.close()
    return {
        "schema_version": 1,
        "validation_scope": "database_structure_and_migration_only",
        "database": {
            "path": str(database),
            "bytes": database.stat().st_size,
            "sha256": file_sha256(database),
        },
        "checks": checks,
        "passed": all(checks.values()),
        "counts": counts,
        "goal_case_counts": goal_case_counts,
        "goal_distinct_app_counts": goal_app_counts,
        "warnings": warnings,
        "not_evaluated": [
            "first_action_accuracy",
            "next_action_accuracy",
            "destination_arrival_rate",
            "recovery_success_rate",
            "planner-model quality",
        ],
        "validated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Navigation Decision DB structure and migration")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not re.fullmatch(r"[a-f0-9]{64}", args.expected_source_sha256):
        raise ValueError("--expected-source-sha256 must be a lowercase SHA-256")
    report = validate(
        args.database.resolve(), expected_source_sha256=args.expected_source_sha256
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
