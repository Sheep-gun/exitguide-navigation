#!/usr/bin/env python3
"""Freeze the TVING public-prior OFF/ON validation evidence.

The source Runtime databases are validation-only captures.  This script copies
only the four reviewed, screenshot-free screen payloads and the matching API
predictions into a small immutable SQLite artifact.  It never writes to either
Runtime database, the operating Decision DB, or App Knowledge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_PACKAGE = "net.cj.cjhv.gs.tving"
APP_VERSION = "26.31.02"
GOAL_ID = "membership.join"
GOAL_TEXT = "Join a TVING membership"


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    source_variant: str
    source_decision_id: str
    expected_action: str
    expected_candidate_id: str | None
    expected_direction: str | None
    first_action: bool
    expected_basis: str


CASES = (
    CaseSpec(
        "tving_home_to_my",
        "a",
        "navd_1777455d8e97460b9bf8ef78c12144c5",
        "click",
        "a11y_591a3cf7272e01221349",
        None,
        True,
        "real-device click changed the screen from Home to My Page",
    ),
    CaseSpec(
        "tving_my_top_to_pass_purchase",
        "a",
        "navd_d90be428f6174545855dce5959475f9a",
        "click",
        "a11y_0985f4bea557baff37d1",
        None,
        False,
        "reviewed direct label: 이용권을 구매하세요",
    ),
    CaseSpec(
        "tving_my_bottom_recover_up",
        "a",
        "navd_49f0d28772d84b5780b8520f2882b7bb",
        "scroll",
        None,
        "up",
        False,
        "the direct pass-purchase affordance was above after two downward scrolls",
    ),
    CaseSpec(
        "tving_settings_recover_back",
        "b",
        "navd_15db0d53c1b04617a61bae4503a3e730",
        "back",
        None,
        None,
        False,
        "preceding Settings click was observed as wrong_destination/regressed",
    ),
)

REPLAY_REQUEST_IDS = {
    "tving_home_to_my": {
        "a": "tving-fixed-home-a-20260804",
        "b": "tving-fixed-home-b-20260804",
    },
    "tving_my_top_to_pass_purchase": {
        "a": "tving-fixed-my-top-a-20260804",
        "b": "tving-fixed-my-top-b-20260804",
    },
    "tving_my_bottom_recover_up": {
        "a": "tving-fixed-my-bottom-a-20260804",
        "b": "tving-fixed-my-bottom-b-20260804",
    },
    "tving_settings_recover_back": {
        "a": "tving-fixed-settings-a-20260804",
        "b": "tving-fixed-settings-b-20260804",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-runtime", required=True, type=Path)
    parser.add_argument("--b-runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--a-report", required=True, type=Path)
    parser.add_argument("--b-report", required=True, type=Path)
    parser.add_argument("--decision-db-sha256", required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def connect_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_decision(connection: sqlite3.Connection, decision_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT d.*, s.request_id, s.app_package, s.app_version, s.goal_id AS session_goal_id
        FROM navigation_decisions AS d
        JOIN navigation_sessions AS s USING(session_id)
        WHERE d.decision_id = ?
        """,
        (decision_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"missing source decision: {decision_id}")
    if row["app_package"] != APP_PACKAGE or row["session_goal_id"] != GOAL_ID:
        raise ValueError(f"source decision is not the TVING membership.join validation: {decision_id}")
    return row


def load_replay_decision(connection: sqlite3.Connection, request_id: str) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT d.*, s.request_id, s.app_package, s.app_version, s.goal_id AS session_goal_id
        FROM navigation_decisions AS d
        JOIN navigation_sessions AS s USING(session_id)
        WHERE s.request_id = ?
        """,
        (request_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"missing exact replay result: {request_id}")
    return row


def candidate_id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("candidate_id") or candidate.get("element_id") or "")


def is_exact(spec: CaseSpec, prediction: sqlite3.Row) -> bool:
    if prediction["action_name"] != spec.expected_action:
        return False
    if spec.expected_action == "click":
        return prediction["candidate_id"] == spec.expected_candidate_id
    if spec.expected_action == "scroll":
        return prediction["scroll_direction"] == spec.expected_direction
    return True


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA foreign_keys=ON;
        CREATE TABLE validation_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        CREATE TABLE frozen_validation_cases (
            case_id TEXT PRIMARY KEY,
            app_package TEXT NOT NULL,
            app_version TEXT NOT NULL,
            goal_id TEXT NOT NULL,
            goal_text TEXT NOT NULL,
            source_variant TEXT NOT NULL CHECK(source_variant IN ('a','b')),
            source_decision_id TEXT NOT NULL,
            screen_sha256 TEXT NOT NULL,
            screen_payload_json TEXT NOT NULL,
            candidate_count INTEGER NOT NULL,
            expected_action TEXT NOT NULL,
            expected_candidate_id TEXT,
            expected_direction TEXT,
            first_action INTEGER NOT NULL CHECK(first_action IN (0,1)),
            expected_basis TEXT NOT NULL
        ) STRICT;
        CREATE TABLE frozen_candidates (
            case_id TEXT NOT NULL REFERENCES frozen_validation_cases(case_id),
            candidate_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            label TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            PRIMARY KEY(case_id, candidate_id)
        ) STRICT;
        CREATE TABLE variant_predictions (
            case_id TEXT NOT NULL REFERENCES frozen_validation_cases(case_id),
            variant TEXT NOT NULL CHECK(variant IN ('a','b')),
            public_prior_enabled INTEGER NOT NULL CHECK(public_prior_enabled IN (0,1)),
            request_id TEXT NOT NULL,
            decision_id TEXT NOT NULL,
            replay_screen_sha256 TEXT NOT NULL,
            predicted_action TEXT NOT NULL,
            predicted_candidate_id TEXT,
            predicted_direction TEXT,
            planner_provider TEXT NOT NULL,
            confidence REAL NOT NULL,
            exact_match INTEGER NOT NULL CHECK(exact_match IN (0,1)),
            public_evidence_count INTEGER NOT NULL,
            evidence_case_ids_json TEXT NOT NULL,
            PRIMARY KEY(case_id, variant)
        ) STRICT;
        CREATE TABLE real_device_steps (
            variant TEXT NOT NULL CHECK(variant IN ('a','b')),
            session_id TEXT NOT NULL,
            step_ordinal INTEGER NOT NULL,
            decision_id TEXT NOT NULL,
            action_name TEXT NOT NULL,
            candidate_id TEXT,
            candidate_label TEXT NOT NULL,
            scroll_direction TEXT,
            planner_provider TEXT NOT NULL,
            execution_status TEXT NOT NULL,
            execution_succeeded INTEGER,
            state_changed INTEGER,
            outcome_type TEXT NOT NULL,
            progress_label TEXT NOT NULL,
            failure_class TEXT NOT NULL,
            dangerous_auto_click INTEGER NOT NULL CHECK(dangerous_auto_click IN (0,1)),
            PRIMARY KEY(variant, decision_id)
        ) STRICT;
        """
    )


def actual_session(connection: sqlite3.Connection) -> sqlite3.Row:
    rows = connection.execute(
        """
        SELECT * FROM navigation_sessions
        WHERE app_package = ? AND request_id NOT LIKE 'tving-fixed-%'
        ORDER BY created_at
        """,
        (APP_PACKAGE,),
    ).fetchall()
    if len(rows) != 1:
        raise ValueError(f"expected exactly one real-device TVING session, found {len(rows)}")
    return rows[0]


def insert_actual_steps(
    output: sqlite3.Connection,
    source: sqlite3.Connection,
    variant: str,
) -> dict[str, Any]:
    session = actual_session(source)
    rows = source.execute(
        """
        SELECT d.*, x.execution_status, x.execution_succeeded,
               o.state_changed, COALESCE(o.outcome_type, '') AS outcome_type,
               COALESCE(o.progress_label, '') AS progress_label,
               COALESCE(o.failure_class, '') AS failure_class,
               COALESCE(json_extract(c.observed_payload_json, '$.label'), '') AS candidate_label,
               COALESCE(c.dangerous_final, 0) AS dangerous_final,
               COALESCE(c.risk_level, 'low') AS selected_risk
        FROM navigation_decisions AS d
        LEFT JOIN navigation_step_executions AS x USING(decision_id)
        LEFT JOIN navigation_observations AS o USING(decision_id)
        LEFT JOIN navigation_screen_snapshots AS ss
          ON ss.decision_id=d.decision_id AND ss.phase='before'
        LEFT JOIN navigation_screen_candidates AS c
          ON c.snapshot_id=ss.snapshot_id AND c.selected=1
        WHERE d.session_id=? ORDER BY d.step_ordinal
        """,
        (session["session_id"],),
    ).fetchall()
    for row in rows:
        dangerous = bool(
            row["action_name"] == "click"
            and row["execution_succeeded"] == 1
            and (row["dangerous_final"] == 1 or row["selected_risk"] in {"medium", "high", "blocked"})
        )
        output.execute(
            """
            INSERT INTO real_device_steps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                variant,
                session["session_id"],
                row["step_ordinal"],
                row["decision_id"],
                row["action_name"],
                row["candidate_id"],
                row["candidate_label"],
                row["scroll_direction"],
                row["planner_provider"],
                row["execution_status"] or "not_observed",
                row["execution_succeeded"],
                row["state_changed"],
                row["outcome_type"],
                row["progress_label"],
                row["failure_class"],
                int(dangerous),
            ),
        )
    executed = [row for row in rows if row["execution_succeeded"] is not None]
    return {
        "session_id": session["session_id"],
        "decision_count": len(rows),
        "executed_step_count": len(executed),
        "wrong_click_count": sum(row["outcome_type"] == "wrong_destination" for row in rows),
        "destination_reached": any(row["progress_label"] == "reached" for row in rows),
        "repeated_down_scroll_count": sum(
            row["action_name"] == "scroll" and row["scroll_direction"] == "down" for row in rows
        ),
        "planner_model_action_count": sum("solar_" in row["planner_provider"] for row in rows),
        "db_semantic_fast_path_count": sum(
            row["planner_provider"].startswith("semantic_") for row in rows
        ),
        "visual_reobserve_gate_count": sum(
            row["planner_provider"] == "python_visual_reobserve_gate" for row in rows
        ),
        "dangerous_auto_click_count": sum(
            row["action_name"] == "click"
            and row["execution_succeeded"] == 1
            and (row["dangerous_final"] == 1 or row["selected_risk"] in {"medium", "high", "blocked"})
            for row in rows
        ),
        "elapsed_seconds": round(
            (
                datetime.fromisoformat(session["updated_at"])
                - datetime.fromisoformat(session["created_at"])
            ).total_seconds(),
            3,
        ),
    }


def make_report(
    *,
    variant: str,
    output_db: Path,
    decision_db_sha256: str,
    predictions: list[dict[str, Any]],
    actual_summary: dict[str, Any],
) -> dict[str, Any]:
    first = [item for item in predictions if item["first_action"]]
    exact = sum(item["exact_match"] for item in predictions)
    return {
        "evaluation_kind": "frozen_validation_public_prior_ab",
        "claim_scope": "TVING validation only; not locked holdout and not promotion evidence",
        "case_count": len(predictions),
        "positive_case_count": len(predictions),
        "evaluation_cases_database": str(output_db.resolve()),
        "evaluation_cases_sha256": sha256_file(output_db),
        "database_sha256": decision_db_sha256,
        "public_prior": {
            "enabled": variant == "b",
            "mode": "planner_advisory_only",
            "runtime_execution_allowed": False,
            "canonical_promotion_allowed": False,
        },
        "positive_exact_next_action_accuracy": round(exact / len(predictions), 4),
        "positive_first_action_accuracy": round(
            sum(item["exact_match"] for item in first) / len(first), 4
        ),
        "positive_first_action_count": len(first),
        "failed_click_case_count": 0,
        "failed_click_avoidance_rate": None,
        "recognized_goal_rate": 1.0,
        "dangerous_auto_click_count": actual_summary["dangerous_auto_click_count"],
        "public_evidence_case_count": sum(item["public_evidence_count"] > 0 for item in predictions),
        "predictions": predictions,
        "real_device_episode": actual_summary,
    }


def main() -> None:
    args = parse_args()
    for path in (args.a_runtime, args.b_runtime):
        if not path.is_file():
            raise FileNotFoundError(path)
    if args.output.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite without --force: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.a_report.parent.mkdir(parents=True, exist_ok=True)
    args.b_report.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()

    sources = {
        "a": connect_read_only(args.a_runtime),
        "b": connect_read_only(args.b_runtime),
    }
    output = sqlite3.connect(args.output)
    output.row_factory = sqlite3.Row
    create_schema(output)
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for key, value in {
        "schema": "exitguide.tving-public-prior-validation.v1",
        "frozen_at": frozen_at,
        "app_package": APP_PACKAGE,
        "app_version": APP_VERSION,
        "goal_id": GOAL_ID,
        "dataset_split": "validation",
        "decision_db_sha256": args.decision_db_sha256,
        "screenshots_persisted": "false",
        "promotion_allowed": "false",
    }.items():
        output.execute("INSERT INTO validation_metadata VALUES (?,?)", (key, value))

    case_payload_sha: dict[str, str] = {}
    prediction_rows: dict[str, list[dict[str, Any]]] = {"a": [], "b": []}
    for spec in CASES:
        source = sources[spec.source_variant]
        decision = load_decision(source, spec.source_decision_id)
        screen = json.loads(decision["screen_payload_json"])
        screen_payload = canonical_json(screen)
        screen_sha = sha256_bytes(screen_payload.encode("utf-8"))
        case_payload_sha[spec.case_id] = screen_sha
        candidates = screen.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(f"case has no candidates: {spec.case_id}")
        candidate_ids = {candidate_id(item) for item in candidates}
        if spec.expected_candidate_id and spec.expected_candidate_id not in candidate_ids:
            raise ValueError(f"expected candidate missing from {spec.case_id}")
        output.execute(
            """
            INSERT INTO frozen_validation_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                spec.case_id,
                APP_PACKAGE,
                APP_VERSION,
                GOAL_ID,
                GOAL_TEXT,
                spec.source_variant,
                spec.source_decision_id,
                screen_sha,
                screen_payload,
                len(candidates),
                spec.expected_action,
                spec.expected_candidate_id,
                spec.expected_direction,
                int(spec.first_action),
                spec.expected_basis,
            ),
        )
        for ordinal, candidate in enumerate(candidates):
            output.execute(
                "INSERT INTO frozen_candidates VALUES (?,?,?,?,?,?)",
                (
                    spec.case_id,
                    candidate_id(candidate),
                    ordinal,
                    str(candidate.get("label", "")),
                    str(candidate.get("risk_level", "low")),
                    canonical_json(candidate),
                ),
            )

        for variant in ("a", "b"):
            request_id = REPLAY_REQUEST_IDS[spec.case_id][variant]
            prediction = load_replay_decision(sources[variant], request_id)
            replay_screen = canonical_json(json.loads(prediction["screen_payload_json"]))
            replay_sha = sha256_bytes(replay_screen.encode("utf-8"))
            if replay_sha != screen_sha:
                raise ValueError(
                    f"{variant.upper()} did not use the exact frozen screen for {spec.case_id}"
                )
            evidence = json.loads(prediction["evidence_case_ids_json"] or "[]")
            public_count = sum(str(value).startswith("public:") for value in evidence)
            exact = is_exact(spec, prediction)
            output.execute(
                """
                INSERT INTO variant_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    spec.case_id,
                    variant,
                    int(variant == "b"),
                    request_id,
                    prediction["decision_id"],
                    replay_sha,
                    prediction["action_name"],
                    prediction["candidate_id"],
                    prediction["scroll_direction"],
                    prediction["planner_provider"],
                    prediction["confidence"],
                    int(exact),
                    public_count,
                    canonical_json(evidence),
                ),
            )
            prediction_rows[variant].append(
                {
                    "case_id": spec.case_id,
                    "expected_action": spec.expected_action,
                    "expected_candidate_id": spec.expected_candidate_id,
                    "expected_direction": spec.expected_direction,
                    "predicted_action": prediction["action_name"],
                    "predicted_candidate_id": prediction["candidate_id"],
                    "predicted_direction": prediction["scroll_direction"],
                    "planner_provider": prediction["planner_provider"],
                    "exact_match": bool(exact),
                    "first_action": spec.first_action,
                    "public_evidence_count": public_count,
                }
            )

    actual_summaries = {
        variant: insert_actual_steps(output, sources[variant], variant)
        for variant in ("a", "b")
    }
    output.commit()
    integrity = output.execute("PRAGMA integrity_check").fetchone()[0]
    foreign_keys = output.execute("PRAGMA foreign_key_check").fetchall()
    output.close()
    for connection in sources.values():
        connection.close()
    if integrity != "ok" or foreign_keys:
        raise RuntimeError(f"invalid frozen DB: integrity={integrity}, foreign_keys={foreign_keys}")

    reports = {
        variant: make_report(
            variant=variant,
            output_db=args.output,
            decision_db_sha256=args.decision_db_sha256,
            predictions=prediction_rows[variant],
            actual_summary=actual_summaries[variant],
        )
        for variant in ("a", "b")
    }
    args.a_report.write_text(
        json.dumps(reports["a"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.b_report.write_text(
        json.dumps(reports["b"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "sha256": sha256_file(args.output),
                "case_count": len(CASES),
                "a_accuracy": reports["a"]["positive_exact_next_action_accuracy"],
                "b_accuracy": reports["b"]["positive_exact_next_action_accuracy"],
                "a_dangerous_auto_clicks": reports["a"]["dangerous_auto_click_count"],
                "b_dangerous_auto_clicks": reports["b"]["dangerous_auto_click_count"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
