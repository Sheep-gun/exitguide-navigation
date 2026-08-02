from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from app.navigation_contracts import (
    CandidateValue,
    HierarchicalPlan,
    NavigationAction,
    ScreenObservation,
)
from app.services.navigation_decision_memory import redact_text


RUNTIME_SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class NavigationRuntimeStore:
    """Append-only runtime evidence kept separate from validated memory.

    Runtime observations are not retrieval evidence until an offline validator
    promotes them. This prevents model output from self-reinforcing without a
    successful observed transition.
    """

    def __init__(self, path: str | Path, *, schema_path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.schema_path = (
            Path(schema_path).expanduser().resolve()
            if schema_path
            else Path(__file__).resolve().parents[4] / "db" / "navigation_runtime_v1.sql"
        )
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        schema = self.schema_path.read_text(encoding="utf-8")
        with self._lock, closing(self._connect()) as connection:
            connection.executescript(schema)
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            metadata = dict(connection.execute("SELECT key, value FROM navigation_runtime_metadata"))
            if version != RUNTIME_SCHEMA_VERSION or metadata.get("schema_version") != str(version):
                raise ValueError("navigation runtime DB schema version mismatch")
            connection.commit()

    def status(self) -> dict[str, object]:
        with self._lock, closing(self._connect()) as connection:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            sessions = int(connection.execute("SELECT count(*) FROM navigation_sessions").fetchone()[0])
            decisions = int(connection.execute("SELECT count(*) FROM navigation_decisions").fetchone()[0])
            observations = int(connection.execute("SELECT count(*) FROM navigation_observations").fetchone()[0])
            pending_revisions = int(
                connection.execute(
                    "SELECT count(*) FROM navigation_knowledge_revision_queue WHERE status = 'pending'"
                ).fetchone()[0]
            )
        return {
            "ready": quick_check == "ok",
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "sessions": sessions,
            "decisions": decisions,
            "observations": observations,
            "pending_knowledge_revisions": pending_revisions,
        }

    def upsert_session(
        self,
        *,
        session_id: str,
        request_id: str,
        app_package: str,
        locale: str,
        goal_text: str,
        goal_id: str | None,
    ) -> None:
        now = utc_now()
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO navigation_sessions(
                    session_id, request_id, app_package, locale, goal_text_redacted,
                    goal_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    request_id = excluded.request_id,
                    app_package = excluded.app_package,
                    locale = excluded.locale,
                    goal_text_redacted = excluded.goal_text_redacted,
                    goal_id = excluded.goal_id,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    request_id,
                    app_package,
                    locale,
                    redact_text(goal_text),
                    goal_id,
                    now,
                    now,
                ),
            )
            connection.commit()

    def record_decision(
        self,
        *,
        decision_id: str,
        session_id: str,
        step_ordinal: int,
        screen_fingerprint: str,
        screen: ScreenObservation,
        goal_id: str | None,
        plan: HierarchicalPlan,
        action: NavigationAction,
        confidence: float,
        score_margin: float,
        reflection_on_demand: bool,
        planner_provider: str,
        planner_fallback_used: bool,
        safety_status: str,
        safety_reason: str,
        destination_match_before: float,
        evidence_case_ids: Iterable[str],
        candidate_values: Iterable[CandidateValue],
    ) -> None:
        screen_payload = {
            "window_title": redact_text(screen.window_title),
            "activity_name": redact_text(screen.activity_name),
            "navigation_depth": screen.navigation_depth,
            "candidate_ids": [candidate.candidate_id for candidate in screen.candidates],
        }
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO navigation_decisions VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    decision_id,
                    session_id,
                    step_ordinal,
                    screen_fingerprint,
                    json.dumps(screen_payload, ensure_ascii=False, sort_keys=True),
                    goal_id,
                    plan.stage,
                    json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                    action.name,
                    action.candidate_id,
                    action.direction,
                    round(confidence, 4),
                    round(score_margin, 4),
                    int(reflection_on_demand),
                    planner_provider,
                    int(planner_fallback_used),
                    safety_status,
                    safety_reason,
                    round(destination_match_before, 4),
                    json.dumps(list(evidence_case_ids), ensure_ascii=False),
                    json.dumps(
                        [value.model_dump(mode="json") for value in candidate_values],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    utc_now(),
                ),
            )
            connection.commit()

    def decision(self, decision_id: str) -> dict[str, Any]:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT d.*, s.request_id, s.app_package, s.locale, s.goal_text_redacted,
                       s.status AS session_status
                FROM navigation_decisions AS d
                JOIN navigation_sessions AS s ON s.session_id = d.session_id
                WHERE d.decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
        if row is None:
            raise KeyError(decision_id)
        result = dict(row)
        result["screen_payload"] = json.loads(result.pop("screen_payload_json"))
        result["plan"] = json.loads(result.pop("plan_json"))
        result["evidence_case_ids"] = json.loads(result.pop("evidence_case_ids_json"))
        result["candidate_values"] = json.loads(result.pop("candidate_values_json"))
        return result

    def recent_history(self, session_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT d.step_ordinal, d.screen_fingerprint, d.action_name, d.candidate_id,
                       d.scroll_direction, d.confidence, d.plan_stage,
                       o.connectivity_status, o.outcome_type, o.progress_label, o.failure_class
                FROM navigation_decisions AS d
                LEFT JOIN navigation_observations AS o ON o.decision_id = d.decision_id
                WHERE d.session_id = ?
                ORDER BY d.step_ordinal DESC
                LIMIT ?
                """,
                (session_id, max(1, min(limit, 20))),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def record_observation(
        self,
        *,
        observation_id: str,
        decision_id: str,
        connectivity_status: str,
        next_screen_fingerprint: str | None,
        state_changed: bool | None,
        outcome_type: str,
        progress_label: str,
        destination_match_before: float | None,
        destination_match_after: float | None,
        failure_class: str,
        session_status: str | None = None,
    ) -> None:
        now = utc_now()
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO navigation_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    decision_id,
                    connectivity_status,
                    next_screen_fingerprint,
                    None if state_changed is None else int(state_changed),
                    outcome_type,
                    progress_label,
                    destination_match_before,
                    destination_match_after,
                    failure_class,
                    now,
                ),
            )
            if session_status:
                connection.execute(
                    """
                    UPDATE navigation_sessions SET status = ?, updated_at = ?
                    WHERE session_id = (
                        SELECT session_id FROM navigation_decisions WHERE decision_id = ?
                    )
                    """,
                    (session_status, now, decision_id),
                )
            connection.commit()

    def remember_failure(
        self,
        *,
        session_id: str,
        screen_fingerprint: str,
        candidate_id: str,
        failure_signature: str,
        recovery_action: str,
    ) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO navigation_recovery_memory(
                    session_id, screen_fingerprint, candidate_id, failure_signature,
                    strike_count, forbidden, recovery_action, updated_at
                ) VALUES (?, ?, ?, ?, 1, 1, ?, ?)
                ON CONFLICT(session_id, screen_fingerprint, candidate_id, failure_signature)
                DO UPDATE SET
                    strike_count = strike_count + 1,
                    forbidden = 1,
                    recovery_action = excluded.recovery_action,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    screen_fingerprint,
                    candidate_id,
                    failure_signature,
                    recovery_action,
                    utc_now(),
                ),
            )
            connection.commit()

    def queue_knowledge_revision(
        self,
        *,
        revision_id: str,
        session_id: str,
        decision_id: str,
        goal_id: str | None,
        first_failure_step: int,
        revision_operator: str,
        proposed_patch: dict[str, object],
    ) -> None:
        """Queue a K²-style local revision without mutating validated memory."""

        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO navigation_knowledge_revision_queue(
                    revision_id, session_id, decision_id, goal_id, first_failure_step,
                    revision_operator, proposed_patch_json, source, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'observed_transition', 'pending', ?)
                """,
                (
                    revision_id,
                    session_id,
                    decision_id,
                    goal_id,
                    first_failure_step,
                    revision_operator,
                    json.dumps(proposed_patch, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
            connection.commit()

    def forbidden_candidates(self, session_id: str, screen_fingerprint: str) -> set[str]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT candidate_id FROM navigation_recovery_memory
                WHERE session_id = ? AND screen_fingerprint = ? AND forbidden = 1
                """,
                (session_id, screen_fingerprint),
            ).fetchall()
        return {str(row["candidate_id"]) for row in rows}
