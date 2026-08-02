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
    NavigationCandidate,
    ScreenObservation,
)
from app.services.navigation_decision_memory import redact_text


RUNTIME_SCHEMA_VERSION = 3


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _candidate_payload(candidate: NavigationCandidate) -> dict[str, object]:
    payload = candidate.model_dump(mode="json")
    for field in ("label", "icon_semantics", "nearby_text", "parent_semantics"):
        payload[field] = redact_text(str(payload.get(field, "")))
    return payload


def _screen_payload(screen: ScreenObservation) -> dict[str, object]:
    return {
        "window_title": redact_text(screen.window_title),
        "activity_name": redact_text(screen.activity_name),
        "navigation_depth": screen.navigation_depth,
        "candidates": [_candidate_payload(candidate) for candidate in screen.candidates],
    }


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
            screen_snapshots = int(
                connection.execute("SELECT count(*) FROM navigation_screen_snapshots").fetchone()[0]
            )
            screen_candidates = int(
                connection.execute("SELECT count(*) FROM navigation_screen_candidates").fetchone()[0]
            )
            complete_steps = int(
                connection.execute("SELECT count(*) FROM navigation_step_executions").fetchone()[0]
            )
            pending_revisions = int(
                connection.execute(
                    "SELECT count(*) FROM navigation_knowledge_revision_queue WHERE status = 'pending'"
                ).fetchone()[0]
            )
            split_rows = connection.execute(
                """
                SELECT split, count(*) AS count
                FROM navigation_dataset_split_manifest GROUP BY split
                """
            ).fetchall()
            split_identity = connection.execute(
                """
                SELECT manifest_version, manifest_sha256
                FROM navigation_dataset_split_manifest LIMIT 1
                """
            ).fetchone()
        return {
            "ready": quick_check == "ok",
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "sessions": sessions,
            "decisions": decisions,
            "observations": observations,
            "screen_snapshots": screen_snapshots,
            "screen_candidates": screen_candidates,
            "complete_steps": complete_steps,
            "pending_knowledge_revisions": pending_revisions,
            "dataset_split_manifest": {
                "installed": split_identity is not None,
                "manifest_version": (
                    None if split_identity is None else str(split_identity["manifest_version"])
                ),
                "sha256": (
                    None if split_identity is None else str(split_identity["manifest_sha256"])
                ),
                "counts": {str(row["split"]): int(row["count"]) for row in split_rows},
            },
        }

    def install_dataset_split_manifest(
        self,
        *,
        manifest_version: str,
        manifest_sha256: str,
        entries: Iterable[dict[str, object]],
    ) -> None:
        """Install one immutable split manifest into the runtime evidence DB."""

        rows = list(entries)
        with self._lock, closing(self._connect()) as connection:
            existing_identity = connection.execute(
                """
                SELECT manifest_version, manifest_sha256
                FROM navigation_dataset_split_manifest LIMIT 1
                """
            ).fetchone()
            if existing_identity is not None:
                if (
                    str(existing_identity["manifest_version"]) != manifest_version
                    or str(existing_identity["manifest_sha256"]) != manifest_sha256
                ):
                    raise ValueError("runtime DB already contains a different locked split manifest")
                existing_packages = {
                    str(row["app_package"])
                    for row in connection.execute(
                        "SELECT app_package FROM navigation_dataset_split_manifest"
                    )
                }
                incoming_packages = {str(row["app_package"]) for row in rows}
                if existing_packages != incoming_packages:
                    raise ValueError("runtime DB split manifest package set does not match")
                return
            now = utc_now()
            connection.executemany(
                """
                INSERT INTO navigation_dataset_split_manifest(
                    manifest_version, manifest_sha256, app_package, app_name, split,
                    reason, existing_decision_cases, available_on_device,
                    priority_app, locked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        manifest_version,
                        manifest_sha256,
                        str(row["app_package"]),
                        str(row["app_name"]),
                        str(row["split"]),
                        str(row["reason"]),
                        int(row["existing_decision_cases"]),
                        int(bool(row["available_on_device"])),
                        int(bool(row["priority_app"])),
                        now,
                    )
                    for row in rows
                ],
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO navigation_runtime_metadata(key, value)
                VALUES ('dataset_split_manifest_version', ?),
                       ('dataset_split_manifest_sha256', ?)
                """,
                (manifest_version, manifest_sha256),
            )
            connection.commit()

    def dataset_split_manifest(self) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT manifest_version, app_package, app_name, split, reason,
                       existing_decision_cases, available_on_device, priority_app, locked_at
                FROM navigation_dataset_split_manifest
                ORDER BY CASE split
                    WHEN 'collection' THEN 1
                    WHEN 'validation' THEN 2
                    ELSE 3 END, app_package
                """
            ).fetchall()
        return [dict(row) for row in rows]

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

    def session(self, session_id: str) -> dict[str, Any] | None:
        """Return the cached, server-validated goal for one navigation session."""

        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT session_id, locale, goal_text_redacted, goal_id, status
                FROM navigation_sessions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return None if row is None else dict(row)

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
        values = list(candidate_values)
        value_by_candidate = {value.candidate_id: value for value in values}
        screen_payload = _screen_payload(screen)
        created_at = utc_now()
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
                        [value.model_dump(mode="json") for value in values],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at,
                ),
            )
            self._insert_screen_snapshot(
                connection,
                snapshot_id=f"navss_before_{decision_id}",
                decision_id=decision_id,
                observation_id=None,
                phase="before",
                screen_fingerprint=screen_fingerprint,
                screen=screen,
                candidate_values=value_by_candidate,
                selected_candidate_id=(action.candidate_id if action.name == "click" else None),
                captured_at=created_at,
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
        next_screen: ScreenObservation | None = None,
        session_status: str | None = None,
    ) -> str:
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
            if next_screen is not None and next_screen_fingerprint is not None:
                self._insert_screen_snapshot(
                    connection,
                    snapshot_id=f"navss_after_{observation_id}",
                    decision_id=decision_id,
                    observation_id=observation_id,
                    phase="after",
                    screen_fingerprint=next_screen_fingerprint,
                    screen=next_screen,
                    candidate_values={},
                    selected_candidate_id=None,
                    captured_at=now,
                )
            connection.commit()
        return observation_id

    def record_execution_details(
        self,
        *,
        decision_id: str,
        observation_id: str,
        connectivity_status: str,
        execution_succeeded: bool | None,
        observed_signal: str,
        recovery_action: NavigationAction | None,
        candidate_forbidden: bool,
        reflection_level: str,
        reflection_reason: str,
    ) -> None:
        if connectivity_status == "device_disconnected":
            execution_status = "device_disconnected"
        elif connectivity_status == "transport_error":
            execution_status = "transport_error"
        elif execution_succeeded is True:
            execution_status = "executed"
        elif execution_succeeded is False:
            execution_status = "not_executed"
        else:
            execution_status = "executor_error"
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO navigation_step_executions(
                    decision_id, observation_id, execution_status, execution_succeeded,
                    observed_signal, recovery_action, candidate_forbidden,
                    reflection_level, reflection_reason, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    observation_id,
                    execution_status,
                    None if execution_succeeded is None else int(execution_succeeded),
                    observed_signal,
                    None if recovery_action is None else recovery_action.name,
                    int(candidate_forbidden),
                    reflection_level,
                    reflection_reason[:1000],
                    utc_now(),
                ),
            )
            connection.commit()

    def interaction_episode(self, session_id: str) -> dict[str, Any]:
        """Return one lossless runtime episode for inspection/export."""

        with self._lock, closing(self._connect()) as connection:
            session = connection.execute(
                "SELECT * FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(session_id)
            split_row = connection.execute(
                """
                SELECT split FROM navigation_dataset_split_manifest
                WHERE app_package = ?
                """,
                (session["app_package"],),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT d.*, o.observation_id, o.connectivity_status,
                       o.next_screen_fingerprint, o.state_changed, o.outcome_type,
                       o.progress_label, o.destination_match_after, o.failure_class,
                       x.execution_status, x.execution_succeeded, x.observed_signal,
                       x.recovery_action, x.candidate_forbidden,
                       x.reflection_level, x.reflection_reason
                FROM navigation_decisions AS d
                LEFT JOIN navigation_observations AS o ON o.decision_id = d.decision_id
                LEFT JOIN navigation_step_executions AS x ON x.decision_id = d.decision_id
                WHERE d.session_id = ?
                ORDER BY d.step_ordinal
                """,
                (session_id,),
            ).fetchall()
            steps: list[dict[str, Any]] = []
            episode_candidate_status = "complete"
            for row in rows:
                item = dict(row)
                snapshots = connection.execute(
                    """
                    SELECT * FROM navigation_screen_snapshots
                    WHERE decision_id = ? ORDER BY phase DESC
                    """,
                    (item["decision_id"],),
                ).fetchall()
                screens: dict[str, Any] = {}
                for snapshot in snapshots:
                    snapshot_item = dict(snapshot)
                    candidates = connection.execute(
                        """
                        SELECT * FROM navigation_screen_candidates
                        WHERE snapshot_id = ? ORDER BY ordinal
                        """,
                        (snapshot_item["snapshot_id"],),
                    ).fetchall()
                    snapshot_item["screen_payload"] = json.loads(
                        snapshot_item.pop("screen_payload_json")
                    )
                    snapshot_item["candidates"] = [
                        {
                            **dict(candidate),
                            "observed_payload": json.loads(candidate["observed_payload_json"]),
                        }
                        for candidate in candidates
                    ]
                    for candidate in snapshot_item["candidates"]:
                        candidate.pop("observed_payload_json", None)
                    screens[str(snapshot_item["phase"])] = snapshot_item
                if "before" not in screens:
                    episode_candidate_status = "unavailable"
                elif (
                    item.get("connectivity_status") == "observed"
                    and "after" not in screens
                    and episode_candidate_status == "complete"
                ):
                    episode_candidate_status = "partial"
                item["plan"] = json.loads(item.pop("plan_json"))
                item["evidence_case_ids"] = json.loads(item.pop("evidence_case_ids_json"))
                item["candidate_values"] = json.loads(item.pop("candidate_values_json"))
                item["screen"] = screens
                item.pop("screen_payload_json", None)
                steps.append(item)
        session_payload = dict(session)
        session_payload["dataset_split"] = (
            "unassigned" if split_row is None else str(split_row["split"])
        )
        return {
            "schema_version": "runtime-episode.v2",
            "session": session_payload,
            "candidate_set_status": episode_candidate_status,
            "steps": steps,
        }

    def cached_api_response(self, request_kind: str, request_id: str) -> dict[str, Any] | None:
        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT response_json FROM navigation_api_response_cache
                WHERE request_kind = ? AND request_id = ?
                """,
                (request_kind, request_id),
            ).fetchone()
        return None if row is None else json.loads(str(row["response_json"]))

    def cache_api_response(
        self,
        request_kind: str,
        request_id: str,
        response: dict[str, Any],
    ) -> None:
        with self._lock, closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO navigation_api_response_cache(
                    request_kind, request_id, response_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    request_kind,
                    request_id,
                    json.dumps(response, ensure_ascii=False, sort_keys=True),
                    utc_now(),
                ),
            )
            connection.commit()

    @staticmethod
    def _insert_screen_snapshot(
        connection: sqlite3.Connection,
        *,
        snapshot_id: str,
        decision_id: str,
        observation_id: str | None,
        phase: str,
        screen_fingerprint: str,
        screen: ScreenObservation,
        candidate_values: dict[str, CandidateValue],
        selected_candidate_id: str | None,
        captured_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO navigation_screen_snapshots(
                snapshot_id, decision_id, observation_id, phase, screen_fingerprint,
                window_title_redacted, activity_name_redacted, navigation_depth,
                candidate_set_status, screen_payload_json, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'complete', ?, ?)
            """,
            (
                snapshot_id,
                decision_id,
                observation_id,
                phase,
                screen_fingerprint,
                redact_text(screen.window_title),
                redact_text(screen.activity_name),
                screen.navigation_depth,
                json.dumps(_screen_payload(screen), ensure_ascii=False, sort_keys=True),
                captured_at,
            ),
        )
        for ordinal, candidate in enumerate(screen.candidates):
            value = candidate_values.get(candidate.candidate_id)
            dangerous = candidate.risk_level in {"high", "blocked"}
            connection.execute(
                """
                INSERT INTO navigation_screen_candidates(
                    snapshot_id, candidate_id, ordinal, observed_payload_json,
                    memory_score, verifier_score, final_score, score_source,
                    risk_level, terminal, dangerous_final, forbidden, selected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    candidate.candidate_id,
                    ordinal,
                    json.dumps(_candidate_payload(candidate), ensure_ascii=False, sort_keys=True),
                    None if value is None else value.memory_score,
                    None if value is None else value.verifier_score,
                    None if value is None else value.final_score,
                    "" if value is None else value.score_source,
                    candidate.risk_level,
                    int(dangerous),
                    int(dangerous),
                    0 if value is None else int(value.forbidden),
                    int(candidate.candidate_id == selected_candidate_id),
                ),
            )

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
