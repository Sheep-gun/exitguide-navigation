from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.services.navigation_training_examples import _redact


SCHEMA_VERSION = "1"
MODEL_DECISION_MODES = frozenset({"exaone", "k_exaone", "llm", "semantic_planner"})


@dataclass(frozen=True)
class RuntimeLearningExample:
    example_id: str
    session_id: str
    recommendation_id: str
    lifecycle_status: str
    review_status: str
    app_package: str
    app_version: str
    locale: str
    goal_text: str
    target_function: str
    screen_fingerprint: str
    screen_context: dict[str, object]
    candidates: tuple[dict[str, object], ...]
    selected_action: dict[str, object]
    decision_mode: str
    confidence: float
    performed: bool
    outcome: str
    next_screen_fingerprint: str
    destination_confirmed: bool
    safe_stop: bool
    unsafe_click_count: int
    wrong_click_count: int
    quality_reasons: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": int(SCHEMA_VERSION),
            "example_id": self.example_id,
            "lifecycle_status": self.lifecycle_status,
            "review_status": self.review_status,
            "provenance": "runtime_agent_shadow",
            "gold_is_evidence_not_macro": True,
            "input": {
                "goal": {"text": self.goal_text, "target_function": self.target_function},
                "app": {
                    "package": self.app_package,
                    "version": self.app_version,
                    "locale": self.locale,
                },
                "screen": {"fingerprint": self.screen_fingerprint, "context": self.screen_context},
                "candidates": list(self.candidates),
            },
            "agent_decision": {
                "tool_call": self.selected_action,
                "decision_mode": self.decision_mode,
                "confidence": self.confidence,
            },
            "observed_result": {
                "performed": self.performed,
                "outcome": self.outcome,
                "next_screen_fingerprint": self.next_screen_fingerprint,
                "destination_confirmed": self.destination_confirmed,
                "safe_stop": self.safe_stop,
                "unsafe_click_count": self.unsafe_click_count,
                "wrong_click_count": self.wrong_click_count,
            },
            "automatic_quality": {
                "passed": self.lifecycle_status == "auto_quality_passed",
                "reasons": list(self.quality_reasons),
            },
        }


def initialize_learning_queue_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS navigation_runtime_learning_queue (
          example_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          recommendation_id TEXT NOT NULL UNIQUE,
          lifecycle_status TEXT NOT NULL,
          review_status TEXT NOT NULL,
          app_package TEXT NOT NULL,
          app_version TEXT NOT NULL,
          locale TEXT NOT NULL,
          goal_text TEXT NOT NULL,
          target_function TEXT NOT NULL,
          screen_fingerprint TEXT NOT NULL,
          screen_context_json TEXT NOT NULL,
          candidates_json TEXT NOT NULL,
          selected_action_json TEXT NOT NULL,
          decision_mode TEXT NOT NULL,
          confidence REAL NOT NULL,
          performed INTEGER NOT NULL,
          outcome TEXT NOT NULL,
          next_screen_fingerprint TEXT NOT NULL,
          destination_confirmed INTEGER NOT NULL,
          safe_stop INTEGER NOT NULL,
          unsafe_click_count INTEGER NOT NULL,
          wrong_click_count INTEGER NOT NULL,
          quality_reasons_json TEXT NOT NULL,
          reviewer TEXT NOT NULL DEFAULT '',
          review_notes TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_runtime_learning_review
        ON navigation_runtime_learning_queue(review_status, lifecycle_status, target_function);
        CREATE INDEX IF NOT EXISTS idx_runtime_learning_app
        ON navigation_runtime_learning_queue(app_package, app_version, target_function);
        CREATE TABLE IF NOT EXISTS navigation_runtime_learning_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )


def materialize_runtime_learning_queue(
    database_path: str | Path,
    *,
    replace_unreviewed: bool = True,
) -> list[RuntimeLearningExample]:
    """Snapshot runtime feedback for review without manufacturing Human Gold."""

    connection = sqlite3.connect(Path(database_path))
    connection.row_factory = sqlite3.Row
    try:
        initialize_learning_queue_schema(connection)
        navigation_join = ""
        navigation_fields = (
            "0 AS destination_correct, 0 AS safe_stop, 0 AS unsafe_click_count, "
            "0 AS wrong_click_count, 'runtime_inferred' AS verification_level"
        )
        if _table_columns(connection, "navigation_sessions"):
            navigation_join = (
                "LEFT JOIN navigation_sessions AS validation "
                "ON validation.session_id = session.session_id"
            )
            navigation_fields = (
                "COALESCE(validation.destination_correct, 0) AS destination_correct, "
                "COALESCE(validation.safe_stop, 0) AS safe_stop, "
                "COALESCE(validation.unsafe_click_count, 0) AS unsafe_click_count, "
                "COALESCE(validation.wrong_click_count, 0) AS wrong_click_count, "
                "COALESCE(validation.verification_level, 'runtime_inferred') AS verification_level"
            )
        rows = connection.execute(
            f"""
            SELECT step.*, session.goal_text, session.status AS session_status,
                   app.app_package, app.app_version, app.locale,
                   screen.activity_name, screen.title, screen.structure_json,
                   action.last_element_id, action.element_key, action.label,
                   action.role, action.risk_level, action.risk_reason,
                   {navigation_fields}
            FROM universal_session_steps AS step
            JOIN universal_sessions AS session ON session.session_id = step.session_id
            JOIN universal_apps AS app ON app.app_key = session.app_key
            JOIN universal_screens AS screen
              ON screen.screen_fingerprint = step.screen_fingerprint
            LEFT JOIN universal_actions AS action ON action.action_id = step.action_id
            {navigation_join}
            ORDER BY step.created_at, step.recommendation_id
            """
        ).fetchall()
        action_rows = connection.execute(
            """
            SELECT screen_fingerprint, action_id, last_element_id, element_key,
                   label, role, risk_level, risk_reason
            FROM universal_actions ORDER BY screen_fingerprint, action_id
            """
        ).fetchall()
        candidates_by_screen: dict[str, list[dict[str, object]]] = {}
        for action in action_rows:
            candidates_by_screen.setdefault(str(action["screen_fingerprint"]), []).append(
                _candidate_payload(action)
            )
        examples = [
            _runtime_example(row, tuple(candidates_by_screen.get(str(row["screen_fingerprint"]), ())))
            for row in rows
        ]
        if replace_unreviewed:
            connection.execute(
                "DELETE FROM navigation_runtime_learning_queue WHERE review_status IN ('hold', 'pending_review')"
            )
        for example in examples:
            _upsert_runtime_example(connection, example)
        for key, value in {
            "schema_version": SCHEMA_VERSION,
            "last_materialized_count": str(len(examples)),
            "promotion_policy": "runtime_to_shadow_to_auto_quality_to_human_review;never_auto_gold",
        }.items():
            connection.execute(
                "INSERT OR REPLACE INTO navigation_runtime_learning_metadata(key, value) VALUES (?, ?)",
                (key, value),
            )
        connection.commit()
        return examples
    finally:
        connection.close()


def review_runtime_example(
    database_path: str | Path,
    example_id: str,
    *,
    approved: bool,
    reviewer: str,
    notes: str = "",
) -> None:
    if not reviewer.strip():
        raise ValueError("reviewer is required")
    connection = sqlite3.connect(Path(database_path))
    try:
        initialize_learning_queue_schema(connection)
        row = connection.execute(
            "SELECT lifecycle_status FROM navigation_runtime_learning_queue WHERE example_id = ?",
            (example_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Unknown runtime learning example: {example_id}")
        if approved and str(row[0]) != "auto_quality_passed":
            raise ValueError("Only an automatic-quality-passed example can become verified_candidate")
        lifecycle_status = "verified_candidate" if approved else "rejected"
        review_status = "approved" if approved else "rejected"
        connection.execute(
            """
            UPDATE navigation_runtime_learning_queue
            SET lifecycle_status = ?, review_status = ?, reviewer = ?, review_notes = ?,
                updated_at = CURRENT_TIMESTAMP WHERE example_id = ?
            """,
            (lifecycle_status, review_status, reviewer.strip(), _redact(notes), example_id),
        )
        connection.commit()
    finally:
        connection.close()


def write_runtime_learning_artifacts(
    examples: Iterable[RuntimeLearningExample],
    output_directory: str | Path,
) -> dict[str, object]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[RuntimeLearningExample]] = {
        "runtime": [],
        "shadow": [],
        "auto_quality_passed": [],
    }
    for example in examples:
        grouped.setdefault(example.lifecycle_status, []).append(example)
    artifacts: dict[str, object] = {}
    for lifecycle, rows in grouped.items():
        path = output / f"navigation-runtime-{lifecycle}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row.payload(), ensure_ascii=False, separators=(",", ":")) + "\n")
        artifacts[lifecycle] = {"file": path.name, "examples": len(rows)}
    manifest = {
        "schema_version": int(SCHEMA_VERSION),
        "provenance": "runtime_agent_shadow",
        "never_auto_gold": True,
        "total_examples": sum(len(rows) for rows in grouped.values()),
        "artifacts": artifacts,
    }
    (output / "navigation-runtime-learning-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _runtime_example(
    row: sqlite3.Row,
    candidates: tuple[dict[str, object], ...],
) -> RuntimeLearningExample:
    selected = {
        "name": "click",
        "arguments": {
            "candidate_id": str(row["last_element_id"] or ""),
            "target_element_key": str(row["element_key"] or ""),
            "target_label": _redact(row["label"] or ""),
            "expected_next_function": str(row["target_function"] or ""),
            "confidence": float(row["confidence"] or 0.0),
            "risk_level": str(row["risk_level"] or "unknown"),
        },
    }
    reasons: list[str] = []
    performed = bool(row["performed"])
    outcome = str(row["outcome"] or "")
    next_screen = str(row["next_screen_fingerprint"] or "")
    destination = bool(row["destination_correct"])
    safe_stop = bool(row["safe_stop"])
    unsafe_clicks = int(row["unsafe_click_count"] or 0)
    wrong_clicks = int(row["wrong_click_count"] or 0)
    decision_mode = str(row["decision_mode"] or "")
    risk_level = str(row["risk_level"] or "unknown")
    if not performed:
        reasons.append("action_not_observed_as_performed")
    if outcome not in {"navigated", "destination_reached", "guided"}:
        reasons.append("outcome_not_positive")
    if not next_screen and outcome == "navigated":
        reasons.append("missing_next_screen")
    if risk_level != "low":
        reasons.append("selected_action_not_low_risk")
    if decision_mode not in MODEL_DECISION_MODES:
        reasons.append("not_a_model_policy_decision")
    if unsafe_clicks:
        reasons.append("unsafe_click_observed")
    if wrong_clicks:
        reasons.append("wrong_click_observed")
    if not destination:
        reasons.append("destination_not_independently_confirmed")
    if not safe_stop:
        reasons.append("safe_stop_not_confirmed")
    quality_passed = not reasons
    if quality_passed:
        lifecycle, review_status = "auto_quality_passed", "pending_review"
    elif performed and outcome in {"navigated", "destination_reached", "guided"}:
        lifecycle, review_status = "shadow", "hold"
    else:
        lifecycle, review_status = "runtime", "hold"
    recommendation_id = str(row["recommendation_id"])
    example_id = "nrl_" + hashlib.sha256(
        f"{recommendation_id}|{SCHEMA_VERSION}".encode("utf-8")
    ).hexdigest()[:20]
    return RuntimeLearningExample(
        example_id=example_id,
        session_id=str(row["session_id"]),
        recommendation_id=recommendation_id,
        lifecycle_status=lifecycle,
        review_status=review_status,
        app_package=str(row["app_package"]),
        app_version=str(row["app_version"]),
        locale=str(row["locale"]),
        goal_text=_redact(row["goal_text"] or ""),
        target_function=str(row["target_function"] or ""),
        screen_fingerprint=str(row["screen_fingerprint"]),
        screen_context={
            "activity_name": _redact(row["activity_name"] or ""),
            "title": _redact(row["title"] or ""),
            "structure": _json_object(row["structure_json"]),
        },
        candidates=candidates,
        selected_action=selected,
        decision_mode=decision_mode,
        confidence=float(row["confidence"] or 0.0),
        performed=performed,
        outcome=outcome,
        next_screen_fingerprint=next_screen,
        destination_confirmed=destination,
        safe_stop=safe_stop,
        unsafe_click_count=unsafe_clicks,
        wrong_click_count=wrong_clicks,
        quality_reasons=tuple(reasons),
    )


def _candidate_payload(row: sqlite3.Row) -> dict[str, object]:
    return {
        "candidate_id": str(row["last_element_id"] or ""),
        "element_key": str(row["element_key"] or ""),
        "label": _redact(row["label"] or ""),
        "role": str(row["role"] or ""),
        "risk_level": str(row["risk_level"] or "unknown"),
        "risk_reason": _redact(row["risk_reason"] or ""),
    }


def _upsert_runtime_example(connection: sqlite3.Connection, example: RuntimeLearningExample) -> None:
    connection.execute(
        """
        INSERT INTO navigation_runtime_learning_queue (
          example_id, session_id, recommendation_id, lifecycle_status, review_status,
          app_package, app_version, locale, goal_text, target_function,
          screen_fingerprint, screen_context_json, candidates_json,
          selected_action_json, decision_mode, confidence, performed, outcome,
          next_screen_fingerprint, destination_confirmed, safe_stop,
          unsafe_click_count, wrong_click_count, quality_reasons_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(example_id) DO UPDATE SET
          lifecycle_status = CASE WHEN navigation_runtime_learning_queue.review_status IN ('approved', 'rejected')
            THEN navigation_runtime_learning_queue.lifecycle_status ELSE excluded.lifecycle_status END,
          review_status = CASE WHEN navigation_runtime_learning_queue.review_status IN ('approved', 'rejected')
            THEN navigation_runtime_learning_queue.review_status ELSE excluded.review_status END,
          candidates_json = excluded.candidates_json,
          selected_action_json = excluded.selected_action_json,
          confidence = excluded.confidence,
          performed = excluded.performed,
          outcome = excluded.outcome,
          next_screen_fingerprint = excluded.next_screen_fingerprint,
          destination_confirmed = excluded.destination_confirmed,
          safe_stop = excluded.safe_stop,
          unsafe_click_count = excluded.unsafe_click_count,
          wrong_click_count = excluded.wrong_click_count,
          quality_reasons_json = excluded.quality_reasons_json,
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            example.example_id, example.session_id, example.recommendation_id,
            example.lifecycle_status, example.review_status, example.app_package,
            example.app_version, example.locale, example.goal_text, example.target_function,
            example.screen_fingerprint,
            json.dumps(example.screen_context, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.candidates, ensure_ascii=False, separators=(",", ":")),
            json.dumps(example.selected_action, ensure_ascii=False, separators=(",", ":")),
            example.decision_mode, example.confidence, int(example.performed), example.outcome,
            example.next_screen_fingerprint, int(example.destination_confirmed), int(example.safe_stop),
            example.unsafe_click_count, example.wrong_click_count,
            json.dumps(example.quality_reasons, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _json_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}
