from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.navigation_decision_memory import (  # noqa: E402
    CURRENCY_AMOUNT_PATTERN,
    EMAIL_PATTERN,
    LONG_NUMBER_PATTERN,
    MASKED_KOREAN_NAME_PATTERN,
    PHONE_PATTERN,
    USER_HANDLE_PATTERN,
    canonical_json,
    redact_text,
)


TEXT_COLUMNS = {
    "navigation_sessions": ("goal_text_redacted",),
    "navigation_decisions": ("safety_reason",),
    "navigation_observations": ("failure_class",),
    "navigation_screen_snapshots": (
        "window_title_redacted",
        "activity_name_redacted",
    ),
    "navigation_screen_candidates": ("score_source",),
    "navigation_step_executions": ("observed_signal", "reflection_reason"),
    "navigation_recovery_memory": ("failure_signature",),
}

JSON_COLUMNS = {
    "navigation_decisions": (
        "screen_payload_json",
        "plan_json",
        "candidate_values_json",
    ),
    "navigation_screen_snapshots": ("screen_payload_json",),
    "navigation_screen_candidates": ("observed_payload_json",),
    "navigation_api_response_cache": ("response_json",),
    "navigation_knowledge_revision_queue": ("proposed_patch_json",),
}

# Opaque IDs, timestamps and hashes must remain byte-for-byte stable.  Only
# user-visible semantic fields are redacted while recursively walking JSON.
REDACTED_JSON_KEYS = {
    "activity_name",
    "completion_rule",
    "detail",
    "explanation",
    "failure_signature",
    "icon_semantics",
    "immediate_subgoal",
    "label",
    "message",
    "nearby_text",
    "parent_semantics",
    "rationale",
    "reason",
    "reflection_reason",
    "safety_reason",
    "semantic_summary",
    "stop_reason",
    "window_title",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up and redact sensitive text in Navigation Runtime DB content fields."
    )
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_json_value(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            item_key: redact_json_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_json_value(item, key=key) for item in value]
    if isinstance(value, str) and key in REDACTED_JSON_KEYS:
        return redact_text(value)
    return value


def sensitive_hits(value: str) -> int:
    return sum(
        len(pattern.findall(value))
        for pattern in (
            EMAIL_PATTERN,
            USER_HANDLE_PATTERN,
            MASKED_KOREAN_NAME_PATTERN,
            PHONE_PATTERN,
            CURRENCY_AMOUNT_PATTERN,
            LONG_NUMBER_PATTERN,
        )
    )


def sanitize_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    *,
    json_column: bool,
) -> tuple[int, int, int]:
    changed = 0
    hits_before = 0
    hits_after = 0
    rows = connection.execute(f'SELECT rowid, "{column}" FROM "{table}"').fetchall()
    for rowid, raw_value in rows:
        raw = str(raw_value or "")
        if json_column:
            payload = json.loads(raw)
            before_sensitive = sensitive_json_hits(payload)
            redacted_payload = redact_json_value(payload)
            rendered = canonical_json(redacted_payload) if redacted_payload != payload else raw
            after_sensitive = sensitive_json_hits(redacted_payload)
        else:
            before_sensitive = sensitive_hits(raw)
            rendered = redact_text(raw)
            after_sensitive = sensitive_hits(rendered)
        hits_before += before_sensitive
        hits_after += after_sensitive
        if rendered != raw:
            connection.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE rowid = ?',
                (rendered, rowid),
            )
            changed += 1
    return changed, hits_before, hits_after


def sensitive_json_hits(value: Any, *, key: str | None = None) -> int:
    if isinstance(value, dict):
        return sum(
            sensitive_json_hits(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        )
    if isinstance(value, list):
        return sum(sensitive_json_hits(item, key=key) for item in value)
    if isinstance(value, str) and key in REDACTED_JSON_KEYS:
        return sensitive_hits(value)
    return 0


def main() -> None:
    args = parse_args()
    database = args.database.expanduser().resolve()
    backup = args.backup.expanduser().resolve()
    report = args.report.expanduser().resolve()
    if not database.is_file():
        raise SystemExit(f"runtime database not found: {database}")
    for output in (backup, report):
        if output.exists():
            raise SystemExit(f"refusing to overwrite existing output: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)

    before_hash = sha256(database)
    source = sqlite3.connect(database)
    source.execute("PRAGMA busy_timeout = 10000")
    backup_connection = sqlite3.connect(backup)
    source.backup(backup_connection)
    backup_quick_check = str(backup_connection.execute("PRAGMA quick_check").fetchone()[0])
    backup_connection.close()
    if backup_quick_check != "ok":
        source.close()
        raise SystemExit("SQLite backup integrity check failed")

    changes: dict[str, dict[str, int]] = {}
    total_before = 0
    total_after = 0
    try:
        source.execute("BEGIN IMMEDIATE")
        for table, columns in TEXT_COLUMNS.items():
            for column in columns:
                changed, before_hits, after_hits = sanitize_column(
                    source, table, column, json_column=False
                )
                changes[f"{table}.{column}"] = {
                    "rows_changed": changed,
                    "sensitive_hits_before": before_hits,
                    "sensitive_hits_after": after_hits,
                }
                total_before += before_hits
                total_after += after_hits
        for table, columns in JSON_COLUMNS.items():
            for column in columns:
                changed, before_hits, after_hits = sanitize_column(
                    source, table, column, json_column=True
                )
                changes[f"{table}.{column}"] = {
                    "rows_changed": changed,
                    "sensitive_hits_before": before_hits,
                    "sensitive_hits_after": after_hits,
                }
                total_before += before_hits
                total_after += after_hits
        if total_after:
            raise ValueError(f"sensitive content remains after redaction: {total_after}")
        source.commit()
        quick_check = str(source.execute("PRAGMA quick_check").fetchone()[0])
        foreign_key_errors = len(source.execute("PRAGMA foreign_key_check").fetchall())
    except Exception:
        source.rollback()
        source.close()
        raise
    source.close()

    result = {
        "database": str(database),
        "backup": str(backup),
        "database_sha256_before": before_hash,
        "backup_sha256": sha256(backup),
        "backup_quick_check": backup_quick_check,
        "database_sha256_after": sha256(database),
        "sensitive_hits_before": total_before,
        "sensitive_hits_after": total_after,
        "quick_check": quick_check,
        "foreign_key_errors": foreign_key_errors,
        "fields": changes,
    }
    if quick_check != "ok" or foreign_key_errors:
        raise SystemExit("runtime database integrity check failed after redaction")
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
