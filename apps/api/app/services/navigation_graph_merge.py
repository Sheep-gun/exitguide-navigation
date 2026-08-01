from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


class NavigationGraphMergeError(RuntimeError):
    """Raised before any candidate data can alter the canonical database."""


@dataclass(frozen=True)
class NavigationGraphMergeReport:
    schema_version: int
    status: str
    source_run_id: str
    source_sha256: str
    destination_sha256_before: str
    destination_sha256_after: str
    backup_path: str
    already_imported: bool
    source_counts: dict[str, int]
    inserted_counts: dict[str, int]
    reused_counts: dict[str, int]
    skipped_counts: dict[str, int]

    def payload(self) -> dict[str, Any]:
        return asdict(self)


_OBSERVATION_TABLES = (
    "universal_apps",
    "universal_screens",
    "universal_actions",
    "universal_transitions",
)
_ROUTE_TABLES = ("universal_routes", "route_performance")
_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def merge_validated_navigation_graph(
    *,
    candidate_database: Path,
    validation_artifact: Path,
    destination_database: Path,
    backup_path: Path | None = None,
) -> NavigationGraphMergeReport:
    """Merge privacy-validated graph evidence without replacing canonical truth.

    Screen/action/transition evidence is merged idempotently.  A route can be
    imported only when its source lifecycle is ``verified_candidate`` and its
    trusted performance row proves a clean destination validation.  Shadow,
    stale, rejected, and approved source routes are deliberately skipped.
    Existing destination rows are never replaced by source rows.
    """

    candidate_database = candidate_database.expanduser().resolve()
    validation_artifact = validation_artifact.expanduser().resolve()
    destination_database = destination_database.expanduser().resolve()
    if not candidate_database.is_file():
        raise NavigationGraphMergeError("candidate graph database is missing")
    if not validation_artifact.is_file():
        raise NavigationGraphMergeError("validation artifact is missing")
    if candidate_database == destination_database:
        raise NavigationGraphMergeError("candidate and destination databases must differ")

    validation = _read_validation(validation_artifact)
    source_run_id = str(validation.get("run_id") or "").strip()
    if not source_run_id:
        raise NavigationGraphMergeError("validation artifact has no run_id")
    source_sha256 = _sha256(candidate_database)
    expected_sha256 = str(
        dict(validation.get("core_artifact_sha256") or {}).get(
            "graph-candidate.sqlite", ""
        )
    )
    if source_sha256 != expected_sha256:
        raise NavigationGraphMergeError(
            "candidate graph hash does not match the passed validation artifact"
        )

    source = _connect_read_only(candidate_database)
    try:
        _assert_database_integrity(source, label="candidate")
        _assert_required_schema(source)
        source_rows = {
            table: _read_rows(source, table)
            for table in (*_OBSERVATION_TABLES, *_ROUTE_TABLES)
        }
    finally:
        source.close()

    eligible_route_ids = _eligible_verified_route_ids(source_rows)
    source_counts = {table: len(rows) for table, rows in source_rows.items()}
    source_counts["eligible_verified_routes"] = len(eligible_route_ids)

    destination_database.parent.mkdir(parents=True, exist_ok=True)
    UniversalNavigationGraphRepository(destination_database)
    destination_sha256_before = _sha256(destination_database)
    backup_path = (
        backup_path.expanduser().resolve()
        if backup_path is not None
        else destination_database.with_name(
            f"{destination_database.stem}.before-{source_run_id}-{source_sha256[:12]}.sqlite"
        )
    )
    if backup_path == destination_database:
        raise NavigationGraphMergeError("backup path must differ from destination")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    _sqlite_backup(destination_database, backup_path)

    inserted = {table: 0 for table in (*_OBSERVATION_TABLES, *_ROUTE_TABLES)}
    reused = {table: 0 for table in (*_OBSERVATION_TABLES, *_ROUTE_TABLES)}
    skipped = {
        "unverified_routes": source_counts["universal_routes"]
        - len(eligible_route_ids),
        "untrusted_route_performance": source_counts["route_performance"]
        - len(eligible_route_ids),
    }
    already_imported = False
    destination = sqlite3.connect(destination_database, timeout=60.0)
    destination.row_factory = sqlite3.Row
    destination.execute("PRAGMA foreign_keys=ON")
    try:
        _create_import_audit_table(destination)
        prior = destination.execute(
            "SELECT 1 FROM navigation_graph_imports WHERE source_sha256 = ?",
            (source_sha256,),
        ).fetchone()
        if prior is not None:
            already_imported = True
        else:
            destination.execute("BEGIN IMMEDIATE")
            _merge_apps(destination, source_rows["universal_apps"], inserted, reused)
            _merge_screens(
                destination, source_rows["universal_screens"], inserted, reused
            )
            _merge_actions(
                destination, source_rows["universal_actions"], inserted, reused
            )
            _merge_transitions(
                destination, source_rows["universal_transitions"], inserted, reused
            )
            _merge_verified_routes(
                destination,
                source_rows["universal_routes"],
                source_rows["route_performance"],
                eligible_route_ids,
                inserted,
                reused,
            )
            foreign_key_errors = destination.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise NavigationGraphMergeError(
                    f"destination foreign-key check failed ({len(foreign_key_errors)} rows)"
                )
            destination.execute(
                """
                INSERT INTO navigation_graph_imports (
                  source_sha256, source_run_id, validation_status, imported_at,
                  source_counts_json, inserted_counts_json, skipped_counts_json
                ) VALUES (?, ?, 'passed', ?, ?, ?, ?)
                """,
                (
                    source_sha256,
                    source_run_id,
                    _utc_now(),
                    _json(source_counts),
                    _json(inserted),
                    _json(skipped),
                ),
            )
            destination.commit()
        _assert_database_integrity(destination, label="destination")
    except Exception:
        destination.rollback()
        raise
    finally:
        destination.close()

    return NavigationGraphMergeReport(
        schema_version=1,
        status="passed",
        source_run_id=source_run_id,
        source_sha256=source_sha256,
        destination_sha256_before=destination_sha256_before,
        destination_sha256_after=_sha256(destination_database),
        backup_path=str(backup_path),
        already_imported=already_imported,
        source_counts=source_counts,
        inserted_counts=inserted,
        reused_counts=reused,
        skipped_counts=skipped,
    )


def _read_validation(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NavigationGraphMergeError("validation artifact is unreadable") from exc
    if not isinstance(payload, dict):
        raise NavigationGraphMergeError("validation artifact must be an object")
    if payload.get("status") != "passed":
        raise NavigationGraphMergeError("candidate corpus did not pass validation")
    if payload.get("validator") != "Validate-RealDeviceObservationCorpus.py":
        raise NavigationGraphMergeError("candidate validator identity is not trusted")
    if payload.get("provenance") != "real_device_observation_candidate":
        raise NavigationGraphMergeError("candidate provenance is not a real-device candidate")
    return payload


def _connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _assert_database_integrity(connection: sqlite3.Connection, *, label: str) -> None:
    quick = connection.execute("PRAGMA quick_check").fetchone()
    if quick is None or str(quick[0]).casefold() != "ok":
        raise NavigationGraphMergeError(f"{label} database quick_check failed")
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise NavigationGraphMergeError(
            f"{label} database foreign-key check failed ({len(foreign_key_errors)} rows)"
        )


def _assert_required_schema(connection: sqlite3.Connection) -> None:
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = sorted(set((*_OBSERVATION_TABLES, *_ROUTE_TABLES)) - tables)
    if missing:
        raise NavigationGraphMergeError(
            "candidate graph is missing required tables: " + ", ".join(missing)
        )


def _read_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def _eligible_verified_route_ids(
    source_rows: dict[str, list[dict[str, Any]]],
) -> set[str]:
    performance = {
        str(row["route_id"]): row for row in source_rows["route_performance"]
    }
    eligible: set[str] = set()
    for route in source_rows["universal_routes"]:
        route_id = str(route["route_id"])
        row = performance.get(route_id)
        if (
            route.get("status") == "verified_candidate"
            and int(route.get("provisional") or 0) == 1
            and row is not None
            and int(row.get("trusted_sample_count") or 0) >= 1
            and int(row.get("success_count") or 0) >= 1
            and int(row.get("failure_count") or 0) == 0
            and float(row.get("destination_accuracy") or 0.0) == 1.0
            and float(row.get("safe_stop_rate") or 0.0) == 1.0
            and int(row.get("unsafe_click_count") or 0) == 0
            and int(row.get("wrong_click_count") or 0) == 0
            and _route_steps_are_safe(str(route.get("steps_json") or ""))
        ):
            eligible.add(route_id)
    return eligible


def _route_steps_are_safe(raw_steps: str) -> bool:
    try:
        steps = json.loads(raw_steps)
    except json.JSONDecodeError:
        return False
    if not isinstance(steps, list) or not steps:
        return False
    terminal_count = 0
    for step in steps:
        if not isinstance(step, dict):
            return False
        terminal = bool(step.get("terminal"))
        terminal_count += int(terminal)
        if terminal:
            continue
        if str(step.get("kind") or "click") == "click" and str(
            step.get("risk_level") or ""
        ) != "low":
            return False
    return terminal_count == 1 and bool(steps[-1].get("terminal"))


def _merge_apps(connection, rows, inserted, reused) -> None:
    for row in rows:
        existing = connection.execute(
            "SELECT * FROM universal_apps WHERE app_key = ?", (row["app_key"],)
        ).fetchone()
        if existing is None:
            _insert_row(connection, "universal_apps", row)
            inserted["universal_apps"] += 1
            continue
        _require_equal(existing, row, ("app_package", "app_version", "locale"), "app")
        connection.execute(
            "UPDATE universal_apps SET first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?) WHERE app_key = ?",
            (row["first_seen_at"], row["last_seen_at"], row["app_key"]),
        )
        reused["universal_apps"] += 1


def _merge_screens(connection, rows, inserted, reused) -> None:
    for row in rows:
        existing = connection.execute(
            "SELECT * FROM universal_screens WHERE screen_fingerprint = ?",
            (row["screen_fingerprint"],),
        ).fetchone()
        if existing is None:
            _insert_row(connection, "universal_screens", row)
            inserted["universal_screens"] += 1
            continue
        _require_same_app_package(connection, str(existing["app_key"]), str(row["app_key"]))
        _require_equal(
            existing,
            row,
            ("activity_name", "title", "structure_json"),
            "screen",
        )
        connection.execute(
            "UPDATE universal_screens SET first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?), seen_count = MAX(seen_count, ?) WHERE screen_fingerprint = ?",
            (
                row["first_seen_at"],
                row["last_seen_at"],
                row["seen_count"],
                row["screen_fingerprint"],
            ),
        )
        reused["universal_screens"] += 1


def _merge_actions(connection, rows, inserted, reused) -> None:
    for row in rows:
        existing = connection.execute(
            "SELECT * FROM universal_actions WHERE action_id = ?", (row["action_id"],)
        ).fetchone()
        if existing is None:
            _insert_row(connection, "universal_actions", row)
            inserted["universal_actions"] += 1
            continue
        _require_equal(
            existing,
            row,
            ("screen_fingerprint", "element_key", "label", "role"),
            "action",
        )
        existing_risk = str(existing["risk_level"])
        source_risk = str(row["risk_level"])
        if existing_risk not in _RISK_ORDER or source_risk not in _RISK_ORDER:
            raise NavigationGraphMergeError("action contains an unknown risk level")
        strictest = max((existing_risk, source_risk), key=_RISK_ORDER.__getitem__)
        risk_reason = (
            row.get("risk_reason")
            if strictest == source_risk and source_risk != existing_risk
            else existing["risk_reason"]
        )
        connection.execute(
            "UPDATE universal_actions SET risk_level = ?, risk_reason = ?, first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?), seen_count = MAX(seen_count, ?) WHERE action_id = ?",
            (
                strictest,
                risk_reason,
                row["first_seen_at"],
                row["last_seen_at"],
                row["seen_count"],
                row["action_id"],
            ),
        )
        reused["universal_actions"] += 1


def _merge_transitions(connection, rows, inserted, reused) -> None:
    for row in rows:
        existing = connection.execute(
            "SELECT * FROM universal_transitions WHERE transition_id = ?",
            (row["transition_id"],),
        ).fetchone()
        if existing is None:
            _insert_row(connection, "universal_transitions", row)
            inserted["universal_transitions"] += 1
            continue
        _require_equal(
            existing,
            row,
            ("from_screen_fingerprint", "action_id", "to_screen_fingerprint"),
            "transition",
        )
        connection.execute(
            "UPDATE universal_transitions SET success_count = MAX(success_count, ?), failure_count = MAX(failure_count, ?), first_seen_at = MIN(first_seen_at, ?), last_seen_at = MAX(last_seen_at, ?) WHERE transition_id = ?",
            (
                row["success_count"],
                row["failure_count"],
                row["first_seen_at"],
                row["last_seen_at"],
                row["transition_id"],
            ),
        )
        reused["universal_transitions"] += 1


def _merge_verified_routes(
    connection,
    route_rows,
    performance_rows,
    eligible_route_ids,
    inserted,
    reused,
) -> None:
    performance_by_id = {str(row["route_id"]): row for row in performance_rows}
    for row in route_rows:
        route_id = str(row["route_id"])
        if route_id not in eligible_route_ids:
            continue
        existing = connection.execute(
            "SELECT * FROM universal_routes WHERE route_id = ?", (route_id,)
        ).fetchone()
        if existing is None:
            _insert_row(connection, "universal_routes", row)
            inserted["universal_routes"] += 1
        else:
            _require_equal(
                existing,
                row,
                (
                    "app_key",
                    "goal_key",
                    "target_function",
                    "start_screen_fingerprint",
                    "destination_screen_fingerprint",
                    "steps_json",
                    "provisional",
                    "status",
                ),
                "route",
            )
            reused["universal_routes"] += 1
        performance = performance_by_id[route_id]
        existing_performance = connection.execute(
            "SELECT * FROM route_performance WHERE route_id = ?", (route_id,)
        ).fetchone()
        if existing_performance is None:
            _insert_row(connection, "route_performance", performance)
            inserted["route_performance"] += 1
        else:
            # Never replace canonical performance truth.  An already imported
            # route is reused only if the immutable scope is identical.
            _require_equal(
                existing_performance,
                performance,
                (
                    "app_key",
                    "target_function",
                    "version_signature",
                    "start_screen_fingerprint",
                ),
                "route performance",
            )
            reused["route_performance"] += 1


def _require_same_app_package(connection, left_app_key: str, right_app_key: str) -> None:
    packages = []
    for app_key in (left_app_key, right_app_key):
        row = connection.execute(
            "SELECT app_package FROM universal_apps WHERE app_key = ?", (app_key,)
        ).fetchone()
        if row is None:
            raise NavigationGraphMergeError("screen references an unknown app scope")
        packages.append(str(row[0]))
    if packages[0] != packages[1]:
        raise NavigationGraphMergeError("screen fingerprint collides across app packages")


def _require_equal(existing, source, fields: Iterable[str], label: str) -> None:
    differing = [field for field in fields if existing[field] != source[field]]
    if differing:
        raise NavigationGraphMergeError(
            f"{label} identity conflict in fields: {', '.join(differing)}"
        )


def _insert_row(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    columns = tuple(row)
    placeholders = ",".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})",
        tuple(row[column] for column in columns),
    )


def _create_import_audit_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS navigation_graph_imports (
          source_sha256 TEXT PRIMARY KEY,
          source_run_id TEXT NOT NULL,
          validation_status TEXT NOT NULL CHECK(validation_status = 'passed'),
          imported_at TEXT NOT NULL,
          source_counts_json TEXT NOT NULL,
          inserted_counts_json TEXT NOT NULL,
          skipped_counts_json TEXT NOT NULL
        )
        """
    )
    connection.commit()


def _sqlite_backup(source_path: Path, backup_path: Path) -> None:
    source = sqlite3.connect(source_path, timeout=60.0)
    backup = sqlite3.connect(backup_path)
    try:
        source.backup(backup)
        backup.commit()
    finally:
        backup.close()
        source.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge a validated real-device graph candidate without replacing canonical data."
    )
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = merge_validated_navigation_graph(
        candidate_database=args.candidate,
        validation_artifact=args.validation,
        destination_database=args.destination,
        backup_path=args.backup,
    )
    payload = report.payload()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
