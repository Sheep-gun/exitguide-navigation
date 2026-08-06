from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
PROMOTER_PATH = ROOT / "scripts" / "Promote-NavigationRuntimeExperiences.py"


def load_promoter() -> Any:
    spec = importlib.util.spec_from_file_location("navigation_promoter", PROMOTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PROMOTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROMOTER = load_promoter()
TERMINAL_COVERAGE = {
    "destination_reached",
    "safe_boundary_reached",
    "not_supported",
    "not_testable",
    "state_not_applicable",
    "failed_with_evidence",
}


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"file:{path.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def placeholders(values: Iterable[object]) -> str:
    values = list(values)
    if not values:
        raise ValueError("empty SQL value set")
    return ",".join("?" for _ in values)


def parse_json_field(row: dict[str, Any], field: str, default: object) -> None:
    raw = row.pop(field, None)
    row[field.removesuffix("_json")] = default if raw is None else json.loads(str(raw))


def coverage_cells(coverage: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for app in coverage.get("apps", []):
        if app.get("split") != "collection":
            raise ValueError(
                f"training freeze accepts collection apps only: {app.get('app_package')}"
            )
        for goal in app.get("goals", []):
            status = str(goal.get("status") or "")
            if status not in TERMINAL_COVERAGE:
                raise ValueError(
                    f"coverage cell is incomplete: {app.get('app_package')} {goal.get('goal_id')} {status}"
                )
            session_ids = [
                str(ref).split(":", 1)[1]
                for ref in goal.get("evidence_refs", [])
                if str(ref).startswith("runtime:")
            ]
            if not session_ids:
                raise ValueError(
                    f"coverage cell lacks Runtime evidence: {app.get('app_package')} {goal.get('goal_id')}"
                )
            cells.append(
                {
                    "app_name": str(app.get("app_name") or app.get("app_package")),
                    "app_package": str(app["app_package"]),
                    "app_version": str(app.get("app_version") or ""),
                    "goal_id": str(goal["goal_id"]),
                    "coverage_status": status,
                    "blocking_issue": goal.get("blocking_issue"),
                    "dangerous_action_auto_executed": bool(
                        goal.get("dangerous_action_auto_executed")
                    ),
                    "evidence_session_ids": list(dict.fromkeys(session_ids)),
                    "evidence_refs": list(goal.get("evidence_refs", [])),
                }
            )
    if len(cells) != 55:
        raise ValueError(f"expected 55 collection cells, observed {len(cells)}")
    if any(cell["dangerous_action_auto_executed"] for cell in cells):
        raise ValueError("coverage contains an automatically executed dangerous action")
    return cells


def runtime_session_inventory(
    runtime: sqlite3.Connection,
    session_ids: list[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    query = f"""
        SELECT session_id,app_package,app_version,locale,goal_id,status,
               created_at,updated_at
        FROM navigation_sessions
        WHERE session_id IN ({placeholders(session_ids)})
    """
    for row in runtime.execute(query, tuple(session_ids)):
        item = dict(row)
        item["decisions"] = []
        result[str(row["session_id"])] = item
    missing = sorted(set(session_ids) - set(result))
    if missing:
        raise ValueError(f"coverage references missing Runtime sessions: {missing}")
    decision_query = f"""
        SELECT d.session_id,d.decision_id,d.step_ordinal,d.action_name,d.candidate_id,
               d.safety_status,d.created_at,
               o.observation_id,o.connectivity_status,o.outcome_type,o.progress_label,
               o.state_changed,x.execution_status,x.execution_succeeded,
               b.snapshot_id,b.candidate_set_status
        FROM navigation_decisions AS d
        LEFT JOIN navigation_observations AS o ON o.decision_id=d.decision_id
        LEFT JOIN navigation_step_executions AS x ON x.decision_id=d.decision_id
        LEFT JOIN navigation_screen_snapshots AS b
          ON b.decision_id=d.decision_id AND b.phase='before'
        WHERE d.session_id IN ({placeholders(session_ids)})
        ORDER BY d.session_id,d.step_ordinal
    """
    for row in runtime.execute(decision_query, tuple(session_ids)):
        result[str(row["session_id"])]["decisions"].append(dict(row))
    return result


def candidate_ids(
    runtime: sqlite3.Connection,
    snapshot_id: str,
) -> list[str]:
    return [
        str(row[0])
        for row in runtime.execute(
            """
            SELECT candidate_id FROM navigation_screen_candidates
            WHERE snapshot_id=? ORDER BY ordinal
            """,
            (snapshot_id,),
        )
    ]


def review_record(
    review: sqlite3.Connection,
    *,
    reviewer: str,
    session: Mapping[str, Any],
    decision: Mapping[str, Any],
    inventory: list[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    problems: list[str] = []
    human_row = review.execute(
        """
        SELECT * FROM navigation_human_reviews
        WHERE decision_id=? AND reviewer=?
        """,
        (decision["decision_id"], reviewer),
    ).fetchone()
    label_rows = review.execute(
        """
        SELECT * FROM navigation_candidate_labels
        WHERE decision_id=? AND reviewer=? ORDER BY candidate_id
        """,
        (decision["decision_id"], reviewer),
    ).fetchall()
    if human_row is None:
        problems.append("missing_human_review")
    labels = [dict(row) for row in label_rows]
    label_ids = [str(item["candidate_id"]) for item in labels]
    if set(label_ids) != set(inventory) or len(label_ids) != len(inventory):
        problems.append("candidate_inventory_not_fully_labeled")
    if any(item.get("review_status") != "verified" for item in labels):
        problems.append("candidate_label_not_verified")
    if human_row is None or problems:
        return None, problems
    human = dict(human_row)
    parse_json_field(human, "source_summary_json", {})
    for item in labels:
        parse_json_field(item, "reason_codes_json", [])
        parse_json_field(item, "source_summary_json", {})
    return (
        {
            "schema_version": "navigation-review-decision.v1",
            "source_step_id": f"{session['session_id']}:{decision['step_ordinal']}",
            "decision_id": str(decision["decision_id"]),
            "session_id": str(session["session_id"]),
            "app_package": str(session["app_package"]),
            "goal_id": str(session["goal_id"]),
            "candidate_inventory_count": len(inventory),
            "candidate_inventory_sha256": hashlib.sha256(
                canonical_json(sorted(inventory))
            ).hexdigest(),
            "human_review": human,
            "candidate_labels": labels,
        },
        [],
    )


def session_review_records(
    runtime: sqlite3.Connection,
    review: sqlite3.Connection,
    *,
    reviewer: str,
    session: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    problems: list[str] = []
    decisions = list(session["decisions"])
    if not decisions:
        return [], ["no_runtime_decisions"]
    for decision in decisions:
        step = f"{session['session_id']}:{decision['step_ordinal']}"
        if decision.get("observation_id") is None:
            problems.append(f"{step}:missing_observation")
            continue
        if decision.get("execution_status") is None:
            problems.append(f"{step}:missing_execution")
            continue
        if decision.get("snapshot_id") is None:
            problems.append(f"{step}:missing_before_snapshot")
            continue
        if decision.get("candidate_set_status") != "complete":
            problems.append(f"{step}:candidate_set_not_complete")
            continue
        inventory = candidate_ids(runtime, str(decision["snapshot_id"]))
        record, record_problems = review_record(
            review,
            reviewer=reviewer,
            session=session,
            decision=decision,
            inventory=inventory,
        )
        problems.extend(f"{step}:{problem}" for problem in record_problems)
        if record is not None:
            records.append(record)
    return records, problems


def locate_runtime_sessions(
    runtime_paths: list[Path],
    session_ids: list[str],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, Path],
    dict[Path, sqlite3.Connection],
]:
    inventory: dict[str, dict[str, Any]] = {}
    source_by_session: dict[str, Path] = {}
    connections: dict[Path, sqlite3.Connection] = {}
    remaining = list(session_ids)
    for path in runtime_paths:
        connection = read_only(path)
        connections[path] = connection
        if not remaining:
            continue
        present = runtime_session_inventory_optional(connection, remaining)
        for session_id, session in present.items():
            inventory[session_id] = session
            source_by_session[session_id] = path
        remaining = [session_id for session_id in remaining if session_id not in present]
    if remaining:
        for connection in connections.values():
            connection.close()
        raise ValueError(f"coverage references missing Runtime sessions: {sorted(remaining)}")
    return inventory, source_by_session, connections


def runtime_session_inventory_optional(
    runtime: sqlite3.Connection,
    session_ids: list[str],
) -> dict[str, dict[str, Any]]:
    try:
        return runtime_session_inventory(runtime, session_ids)
    except ValueError as error:
        marker = "coverage references missing Runtime sessions:"
        if marker not in str(error):
            raise
        present = [
            str(row[0])
            for row in runtime.execute(
                f"SELECT session_id FROM navigation_sessions WHERE session_id IN ({placeholders(session_ids)})",
                tuple(session_ids),
            )
        ]
        if not present:
            return {}
        return runtime_session_inventory(runtime, present)


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    coverage = json.loads(args.coverage.read_text(encoding="utf-8"))
    cells = coverage_cells(coverage)
    referenced_sessions = list(
        dict.fromkeys(
            session_id
            for cell in cells
            for session_id in cell["evidence_session_ids"]
        )
    )
    runtime_paths = list(dict.fromkeys(path.resolve() for path in args.runtime_db))
    inventory, source_by_session, runtime_connections = locate_runtime_sessions(
        runtime_paths,
        referenced_sessions,
    )
    try:
        review = read_only(args.review_db)
        try:
            eligible_records: dict[str, list[dict[str, Any]]] = {}
            excluded: list[dict[str, Any]] = []
            for session_id in referenced_sessions:
                session = inventory[session_id]
                runtime = runtime_connections[source_by_session[session_id]]
                records, problems = session_review_records(
                    runtime,
                    review,
                    reviewer=args.reviewer,
                    session=session,
                )
                if problems:
                    excluded.append(
                        {
                            "session_id": session_id,
                            "app_package": session["app_package"],
                            "goal_id": session["goal_id"],
                            "runtime_db": str(source_by_session[session_id]),
                            "reasons": problems,
                        }
                    )
                else:
                    eligible_records[session_id] = records
        finally:
            review.close()
    finally:
        for connection in runtime_connections.values():
            connection.close()

    selected_cells: list[dict[str, Any]] = []
    selected_session_ids: list[str] = []
    coverage_gaps: list[dict[str, Any]] = []
    for cell in cells:
        matching = [
            session_id
            for session_id in cell["evidence_session_ids"]
            if session_id in eligible_records
            and inventory[session_id]["app_package"] == cell["app_package"]
            and inventory[session_id]["goal_id"] == cell["goal_id"]
        ]
        supplemental = [
            session_id
            for session_id in cell["evidence_session_ids"]
            if session_id in eligible_records and session_id not in matching
        ]
        if not matching:
            relevant_exclusions = [
                item
                for item in excluded
                if item["session_id"] in cell["evidence_session_ids"]
            ]
            coverage_gaps.append(
                {
                    "app_package": cell["app_package"],
                    "goal_id": cell["goal_id"],
                    "exclusions": relevant_exclusions,
                }
            )
            continue
        selected_session_ids.extend(matching)
        selected_session_ids.extend(supplemental)
        selected_cells.append(
            {
                **cell,
                "primary_session_ids": matching,
                "supplemental_session_ids": supplemental,
            }
        )
    if coverage_gaps:
        raise ValueError(
            "coverage cells lack fully reviewed matching Runtime sessions: "
            + json.dumps(coverage_gaps, ensure_ascii=False, sort_keys=True)
        )
    selected_session_ids = list(dict.fromkeys(selected_session_ids))
    review_records = [
        record
        for session_id in selected_session_ids
        for record in eligible_records[session_id]
    ]
    episodes_by_session: dict[str, dict[str, Any]] = {}
    sessions_by_runtime: dict[Path, list[str]] = defaultdict(list)
    for session_id in selected_session_ids:
        sessions_by_runtime[source_by_session[session_id]].append(session_id)
    for runtime_path, runtime_sessions in sessions_by_runtime.items():
        for episode in PROMOTER.export_runtime_episodes(runtime_path, runtime_sessions):
            episodes_by_session[str(episode["session_id"])] = episode
    episodes = [episodes_by_session[session_id] for session_id in selected_session_ids]
    if {episode["session_id"] for episode in episodes} != set(selected_session_ids):
        raise ValueError("Interaction Episode export lost selected Runtime sessions")

    temporary = args.output_root / f".freeze-{os.getpid()}.tmp"
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    try:
        frozen_coverage = dict(coverage)
        frozen_coverage["collection_frozen_at"] = now()
        frozen_coverage["frozen_source_sha256"] = file_sha256(args.coverage)
        write_json(temporary / "coverage.v1.json", frozen_coverage)
        write_jsonl(temporary / "interaction-episodes.v1.jsonl", episodes)
        write_jsonl(temporary / "review-decisions.v1.jsonl", review_records)
        selection = {
            "schema_version": "navigation-training-selection.v1",
            "reviewer": args.reviewer,
            "cell_count": len(selected_cells),
            "selected_session_count": len(selected_session_ids),
            "selected_session_ids": selected_session_ids,
            "cells": selected_cells,
            "excluded_evidence_sessions": excluded,
        }
        write_json(temporary / "selection.v1.json", selection)
        artifacts = {}
        for name in (
            "coverage.v1.json",
            "interaction-episodes.v1.jsonl",
            "review-decisions.v1.jsonl",
            "selection.v1.json",
        ):
            path = temporary / name
            artifacts[name] = {
                "sha256": file_sha256(path),
                "byte_size": path.stat().st_size,
            }
        source = {
            "runtime_dbs": [
                {
                    "path": str(path),
                    "sha256": file_sha256(path),
                    "byte_size": path.stat().st_size,
                    "access_mode": "read_only",
                    "selected_session_ids": sessions_by_runtime.get(path, []),
                }
                for path in runtime_paths
            ],
            "review_db": {
                "path": str(args.review_db.resolve()),
                "sha256": file_sha256(args.review_db),
                "byte_size": args.review_db.stat().st_size,
                "access_mode": "read_only",
            },
            "coverage": {
                "path": str(args.coverage.resolve()),
                "sha256": file_sha256(args.coverage),
            },
            "source_code_commit": args.source_code_commit,
        }
        snapshot_seed = {
            "source": source,
            "artifacts": artifacts,
            "reviewer": args.reviewer,
            "selected_session_ids": selected_session_ids,
        }
        snapshot_id = (
            "training_snapshot_"
            + hashlib.sha256(canonical_json(snapshot_seed)).hexdigest()[:24]
        )
        manifest = {
            "schema_version": "navigation-training-snapshot.v1",
            "snapshot_id": snapshot_id,
            "status": "sealed",
            "created_at": now(),
            "policy": {
                "runtime_source_read_only": True,
                "review_source_read_only": True,
                "all_current_apps_are_collection": True,
                "future_unseen_apps_reserved_for_validation_or_holdout": True,
                "direct_runtime_to_decision_projection_allowed": False,
                "dangerous_automatic_actions": 0,
            },
            "counts": {
                "apps": len({cell["app_package"] for cell in selected_cells}),
                "coverage_cells": len(selected_cells),
                "sessions": len(selected_session_ids),
                "episodes": len(episodes),
                "steps": sum(len(episode["steps"]) for episode in episodes),
                "review_decisions": len(review_records),
                "candidate_labels": sum(
                    len(record["candidate_labels"]) for record in review_records
                ),
                "excluded_evidence_sessions": len(excluded),
            },
            "source": source,
            "artifacts": artifacts,
        }
        write_json(temporary / "manifest.json", manifest)
        output_dir = args.output_root / snapshot_id
        args.output_root.mkdir(parents=True, exist_ok=True)
        if output_dir.exists():
            existing = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            if existing["snapshot_id"] != snapshot_id:
                raise ValueError(f"snapshot directory conflict: {output_dir}")
            shutil.rmtree(temporary)
            return existing
        os.replace(temporary, output_dir)
        if os.name != "nt":
            for path in output_dir.rglob("*"):
                path.chmod(0o440 if path.is_file() else 0o550)
            output_dir.chmod(0o550)
        manifest["snapshot_dir"] = str(output_dir.resolve())
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Seal fully reviewed coverage evidence into an immutable training snapshot"
    )
    result.add_argument(
        "--runtime-db",
        type=Path,
        action="append",
        required=True,
        help="Runtime DB source in precedence order; repeat for preserved historical generations",
    )
    result.add_argument("--review-db", type=Path, required=True)
    result.add_argument("--coverage", type=Path, required=True)
    result.add_argument("--output-root", type=Path, required=True)
    result.add_argument("--reviewer", default="codex-yanggeon")
    result.add_argument("--source-code-commit", required=True)
    return result


if __name__ == "__main__":
    payload = build_snapshot(parser().parse_args())
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
