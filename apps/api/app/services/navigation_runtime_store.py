from __future__ import annotations

import base64
import binascii
import json
import os
import sqlite3
import threading
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from app.navigation_contracts import (
    AccessibilityNodeSummary,
    CandidateValue,
    CollectionRunContext,
    ExecutionReport,
    HierarchicalPlan,
    NavigationAction,
    NavigationCandidate,
    ScreenObservation,
    TaskContext,
)
from app.services.navigation_decision_memory import (
    contextual_account_identifiers,
    redact_text,
)


RUNTIME_SCHEMA_VERSION = 5


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _candidate_payload(
    candidate: NavigationCandidate,
    account_identifiers: Iterable[str] = (),
) -> dict[str, object]:
    payload = candidate.model_dump(mode="json")
    for field in (
        "label", "icon_semantics", "nearby_text", "parent_semantics", "child_semantics",
        "visual_role", "visual_region",
    ):
        payload[field] = redact_text(
            str(payload.get(field, "")),
            account_identifiers=account_identifiers,
        )
    return payload


def _node_payload(
    node: AccessibilityNodeSummary,
    account_identifiers: Iterable[str] = (),
) -> dict[str, object]:
    payload = node.model_dump(mode="json")
    for field in ("text", "content_description"):
        payload[field] = redact_text(
            str(payload.get(field, "")),
            account_identifiers=account_identifiers,
        )
    return payload


def _screen_payload(screen: ScreenObservation) -> dict[str, object]:
    semantic_values = [screen.window_title, screen.activity_name]
    semantic_values.extend(
        value
        for node in screen.nodes
        for value in (node.text, node.content_description)
    )
    semantic_values.extend(
        str(getattr(candidate, field, ""))
        for candidate in screen.candidates
        for field in (
            "label", "icon_semantics", "nearby_text", "parent_semantics",
            "child_semantics", "visual_role", "visual_region",
        )
    )
    account_identifiers = contextual_account_identifiers(semantic_values)
    return {
        "app_package": screen.app_package,
        "window_title": redact_text(
            screen.window_title, account_identifiers=account_identifiers
        ),
        "activity_name": redact_text(
            screen.activity_name, account_identifiers=account_identifiers
        ),
        "navigation_depth": screen.navigation_depth,
        "nodes": [
            _node_payload(node, account_identifiers) for node in screen.nodes
        ],
        "candidates": [
            _candidate_payload(candidate, account_identifiers)
            for candidate in screen.candidates
        ],
    }


class NavigationRuntimeStore:
    """Append-only runtime evidence kept separate from validated memory.

    Runtime observations are not retrieval evidence until an offline validator
    promotes them. This prevents model output from self-reinforcing without a
    successful observed transition.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        schema_path: str | Path | None = None,
        server_release_id: str = "unknown",
        screen_artifact_dir: str | Path | None = None,
    ) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.schema_path = (
            Path(schema_path).expanduser().resolve()
            if schema_path
            else Path(__file__).resolve().parents[4] / "db" / "navigation_runtime_v1.sql"
        )
        self.server_release_id = server_release_id.strip()[:200] or "unknown"
        self.screen_artifact_dir = (
            None
            if screen_artifact_dir is None or not str(screen_artifact_dir).strip()
            else Path(screen_artifact_dir).expanduser().resolve()
        )
        if self.screen_artifact_dir is not None:
            self.screen_artifact_dir.mkdir(parents=True, exist_ok=True)
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
            previous_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if previous_version in {1, 2, 3, 4} and connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='navigation_sessions'"
            ).fetchone():
                _ensure_column(
                    connection,
                    "navigation_sessions",
                    "app_version",
                    "TEXT NOT NULL DEFAULT ''",
                )
                self._migrate_v5_columns(connection)
            connection.executescript(schema)
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            metadata = dict(connection.execute("SELECT key, value FROM navigation_runtime_metadata"))
            if version != RUNTIME_SCHEMA_VERSION or metadata.get("schema_version") != str(version):
                raise ValueError("navigation runtime DB schema version mismatch")
            connection.commit()

    @staticmethod
    def _migrate_v5_columns(connection: sqlite3.Connection) -> None:
        additions = {
            "navigation_sessions": {
                "run_id": "TEXT",
                "task_context_json": "TEXT NOT NULL DEFAULT '{}'",
                "terminal_reason": "TEXT",
                "handoff_reason": "TEXT NOT NULL DEFAULT ''",
            },
            "navigation_decisions": {
                "proposed_action_json": "TEXT NOT NULL DEFAULT '{}'",
                "safety_rewritten_action_json": "TEXT NOT NULL DEFAULT '{}'",
                "retrieval_hits_json": "TEXT NOT NULL DEFAULT '[]'",
                "decision_provenance_json": "TEXT NOT NULL DEFAULT '{}'",
            },
            "navigation_observations": {
                "terminal_reason": "TEXT",
                "handoff_reason": "TEXT NOT NULL DEFAULT ''",
                "outcome_judge": "TEXT NOT NULL DEFAULT 'deterministic_evaluator'",
                "evaluator_id": "TEXT NOT NULL DEFAULT 'navigation_transition_verifier'",
                "evaluator_version": "TEXT NOT NULL DEFAULT '1'",
                "outcome_evidence_frame_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            },
            "navigation_screen_snapshots": {
                "frame_id": "TEXT",
                "screen_width_px": "INTEGER",
                "screen_height_px": "INTEGER",
                "density_dpi": "INTEGER",
                "nodes_total": "INTEGER NOT NULL DEFAULT 0",
                "nodes_captured": "INTEGER NOT NULL DEFAULT 0",
                "nodes_truncated": "INTEGER NOT NULL DEFAULT 0",
                "candidates_total": "INTEGER NOT NULL DEFAULT 0",
                "candidates_captured": "INTEGER NOT NULL DEFAULT 0",
                "candidates_truncated": "INTEGER NOT NULL DEFAULT 0",
                "missing_parts_json": "TEXT NOT NULL DEFAULT '[]'",
            },
            "navigation_step_executions": {
                "actual_action_json": "TEXT NOT NULL DEFAULT '{}'",
                "executor_method": "TEXT NOT NULL DEFAULT 'unknown'",
                "attempt_no": "INTEGER NOT NULL DEFAULT 1",
                "execution_started_device_monotonic_ms": "INTEGER",
                "execution_finished_device_monotonic_ms": "INTEGER",
                "failure_code": "TEXT NOT NULL DEFAULT ''",
                "settle_duration_ms": "INTEGER",
                "settle_reason": "TEXT NOT NULL DEFAULT ''",
                "external_package": "TEXT NOT NULL DEFAULT ''",
                "human_intervention": "INTEGER NOT NULL DEFAULT 0",
            },
        }
        for table, columns in additions.items():
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone() is None:
                continue
            for column, declaration in columns.items():
                _ensure_column(connection, table, column, declaration)

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
            collection_runs = int(
                connection.execute("SELECT count(*) FROM navigation_collection_runs").fetchone()[0]
            )
            collection_events = int(
                connection.execute("SELECT count(*) FROM navigation_collection_events").fetchone()[0]
            )
            screen_artifacts = int(
                connection.execute("SELECT count(*) FROM navigation_screen_artifacts").fetchone()[0]
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
            "collection_runs": collection_runs,
            "collection_events": collection_events,
            "screen_artifacts": screen_artifacts,
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

    def _upsert_collection_run(
        self,
        connection: sqlite3.Connection,
        context: CollectionRunContext,
        *,
        now: str,
    ) -> None:
        payload = context.model_dump(mode="json")
        connection.execute(
            """
            INSERT INTO navigation_collection_runs(
                run_id, collection_batch_id, collector_alias, device_instance_id,
                manufacturer, model, android_api_level, android_release,
                display_width_px, display_height_px, density_dpi, font_scale,
                ui_mode, orientation, locale, collector_app_version,
                collector_build_id, executor_version, executor_build_id,
                server_release_id, run_mode, artifact_policy, test_account,
                context_json, started_at, last_seen_at, ended_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(run_id) DO UPDATE SET
                collection_batch_id = excluded.collection_batch_id,
                collector_alias = excluded.collector_alias,
                device_instance_id = excluded.device_instance_id,
                manufacturer = excluded.manufacturer,
                model = excluded.model,
                android_api_level = excluded.android_api_level,
                android_release = excluded.android_release,
                display_width_px = excluded.display_width_px,
                display_height_px = excluded.display_height_px,
                density_dpi = excluded.density_dpi,
                font_scale = excluded.font_scale,
                ui_mode = excluded.ui_mode,
                orientation = excluded.orientation,
                locale = excluded.locale,
                collector_app_version = excluded.collector_app_version,
                collector_build_id = excluded.collector_build_id,
                executor_version = excluded.executor_version,
                executor_build_id = excluded.executor_build_id,
                server_release_id = excluded.server_release_id,
                run_mode = excluded.run_mode,
                artifact_policy = excluded.artifact_policy,
                test_account = excluded.test_account,
                context_json = excluded.context_json,
                last_seen_at = excluded.last_seen_at
            """,
            (
                context.run_id,
                context.collection_batch_id,
                context.collector_alias,
                context.device_instance_id,
                context.manufacturer,
                context.model,
                context.android_api_level,
                context.android_release,
                context.display_width_px,
                context.display_height_px,
                context.density_dpi,
                context.font_scale,
                context.ui_mode,
                context.orientation,
                context.locale,
                context.collector_app_version,
                context.collector_build_id,
                context.executor_version,
                context.executor_build_id,
                self.server_release_id,
                context.run_mode,
                context.artifact_policy,
                int(context.test_account),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                context.started_at or now,
                now,
            ),
        )

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        *,
        run_id: str | None,
        session_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, object],
        step_id: str | None = None,
        device_monotonic_ms: int | None = None,
        device_wall_time: str | None = None,
        request_id: str | None = None,
        decision_id: str | None = None,
        before_frame_id: str | None = None,
        after_frame_id: str | None = None,
        privacy_status: str = "redacted",
    ) -> None:
        sequence_no = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(sequence_no), -1) + 1
                FROM navigation_collection_events WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()[0]
        )
        now = utc_now()
        connection.execute(
            """
            INSERT INTO navigation_collection_events(
                event_id, event_schema_version, run_id, session_id, step_id,
                sequence_no, event_type, actor, device_monotonic_ms,
                device_wall_time, server_received_at, request_id, decision_id,
                before_frame_id, after_frame_id, payload_json_redacted,
                privacy_status, redaction_version, created_at
            ) VALUES (?, 'navigation-collection-event.v1', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'runtime-redaction-v1', ?)
            """,
            (
                f"nave_{uuid.uuid4().hex}",
                run_id,
                session_id,
                step_id,
                sequence_no,
                event_type,
                actor,
                device_monotonic_ms,
                device_wall_time,
                now,
                request_id,
                decision_id,
                before_frame_id,
                after_frame_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                privacy_status,
                now,
            ),
        )

    def upsert_session(
        self,
        *,
        session_id: str,
        request_id: str,
        app_package: str,
        app_version: str,
        locale: str,
        goal_text: str,
        goal_id: str | None,
        origin_app_package: str = "",
        current_app_package: str = "",
        previous_app_package: str = "",
        transition_reason: str = "unknown",
        collection_run: CollectionRunContext | None = None,
        task_context: TaskContext | None = None,
    ) -> None:
        now = utc_now()
        context = collection_run or CollectionRunContext(
            run_id=(f"legacy_{session_id}")[:200],
            collection_batch_id="legacy_runtime",
            collector_alias="legacy_unknown",
            device_instance_id="legacy_unknown",
            locale=locale,
            artifact_policy="none",
        )
        task = task_context or TaskContext()
        origin_package = origin_app_package or app_package
        current_package = current_app_package or app_package
        with self._lock, closing(self._connect()) as connection:
            previous_session = connection.execute(
                "SELECT app_package FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            is_new = previous_session is None
            self._upsert_collection_run(connection, context, now=now)
            if is_new and context.device_instance_id not in {"", "legacy_unknown"}:
                superseded = connection.execute(
                    """
                    SELECT s.session_id, s.run_id
                    FROM navigation_sessions AS s
                    JOIN navigation_collection_runs AS r ON r.run_id = s.run_id
                    WHERE s.status = 'active'
                      AND s.session_id <> ?
                      AND r.device_instance_id = ?
                    """,
                    (session_id, context.device_instance_id),
                ).fetchall()
                for stale in superseded:
                    connection.execute(
                        """
                        UPDATE navigation_sessions
                        SET status = 'stopped',
                            terminal_reason = COALESCE(terminal_reason, 'manual_stop'),
                            handoff_reason = 'superseded_by_new_device_session',
                            updated_at = ?
                        WHERE session_id = ? AND status = 'active'
                        """,
                        (now, stale["session_id"]),
                    )
                    connection.execute(
                        """
                        UPDATE navigation_collection_runs
                        SET ended_at = COALESCE(ended_at, ?)
                        WHERE run_id = ?
                        """,
                        (now, stale["run_id"]),
                    )
                    self._append_event(
                        connection,
                        run_id=stale["run_id"],
                        session_id=stale["session_id"],
                        event_type="session_ended",
                        actor="system",
                        payload={
                            "status": "stopped",
                            "terminal_reason": "manual_stop",
                            "handoff_reason": "superseded_by_new_device_session",
                            "replacement_session_id": session_id,
                        },
                    )
            connection.execute(
                """
                INSERT INTO navigation_sessions(
                    session_id, run_id, request_id, app_package, app_version, locale,
                    goal_text_redacted, goal_id, task_context_json, status,
                    terminal_reason, handoff_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, '', ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    request_id = excluded.request_id,
                    app_package = excluded.app_package,
                    app_version = excluded.app_version,
                    locale = excluded.locale,
                    goal_text_redacted = excluded.goal_text_redacted,
                    goal_id = excluded.goal_id,
                    task_context_json = excluded.task_context_json,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    context.run_id,
                    request_id,
                    app_package,
                    app_version,
                    locale,
                    redact_text(goal_text),
                    goal_id,
                    json.dumps(task.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            if is_new:
                self._append_event(
                    connection,
                    run_id=context.run_id,
                    session_id=session_id,
                    event_type="session_started",
                    actor="system",
                    request_id=request_id,
                    payload={
                        "app_package": origin_package,
                        "origin_app_package": origin_package,
                        "current_app_package": current_package,
                        "previous_app_package": previous_app_package,
                        "transition_reason": transition_reason,
                        "app_version": app_version,
                        "locale": locale,
                        "goal_text_redacted": redact_text(goal_text),
                        "goal_id": goal_id,
                        "task_context": task.model_dump(mode="json"),
                    },
                )
            elif previous_app_package and previous_app_package != current_package:
                self._append_event(
                    connection,
                    run_id=context.run_id,
                    session_id=session_id,
                    event_type="app_transition",
                    actor="system",
                    request_id=request_id,
                    payload={
                        "origin_app_package": origin_package,
                        "previous_app_package": previous_app_package,
                        "current_app_package": current_package,
                        "transition_reason": transition_reason,
                    },
                )
            connection.commit()

    def session(self, session_id: str) -> dict[str, Any] | None:
        """Return the cached, server-validated goal for one navigation session."""

        with self._lock, closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT session_id, run_id, app_package, app_version, locale,
                       goal_text_redacted, goal_id, status, terminal_reason,
                       handoff_reason
                FROM navigation_sessions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def set_session_status(
        self,
        session_id: str,
        status: str,
        *,
        terminal_reason: str | None = None,
        handoff_reason: str = "",
        append_event: bool = True,
    ) -> None:
        if status not in {"active", "stopped", "reached", "failed"}:
            raise ValueError(f"unsupported navigation session status: {status}")
        with self._lock, closing(self._connect()) as connection:
            current = connection.execute(
                "SELECT run_id, terminal_reason FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if current is None:
                raise KeyError(session_id)
            preserved_terminal_reason = current["terminal_reason"] or terminal_reason
            now = utc_now()
            connection.execute(
                """
                UPDATE navigation_sessions
                SET status = ?, terminal_reason = ?, handoff_reason = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    status,
                    preserved_terminal_reason,
                    handoff_reason[:300],
                    now,
                    session_id,
                ),
            )
            if status != "active":
                connection.execute(
                    "UPDATE navigation_collection_runs SET ended_at = COALESCE(ended_at, ?) WHERE run_id = ?",
                    (now, current["run_id"]),
                )
                if append_event:
                    self._append_event(
                        connection,
                        run_id=current["run_id"],
                        session_id=session_id,
                        event_type=(
                            "human_handoff"
                            if preserved_terminal_reason == "safe_user_handoff"
                            else "session_ended"
                        ),
                        actor="system",
                        payload={
                            "status": status,
                            "terminal_reason": preserved_terminal_reason,
                            "handoff_reason": handoff_reason[:300],
                        },
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
        proposed_action: NavigationAction,
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
        retrieval_hits: Iterable[dict[str, object]] = (),
        decision_provenance: dict[str, object] | None = None,
        screenshot_data_url: str | None = None,
    ) -> None:
        values = list(candidate_values)
        retrieval_rows = list(retrieval_hits)
        value_by_candidate = {value.candidate_id: value for value in values}
        screen_payload = _screen_payload(screen)
        created_at = utc_now()
        with self._lock, closing(self._connect()) as connection:
            session = connection.execute(
                "SELECT run_id FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if session is None:
                raise KeyError(session_id)
            collection_run = (
                None
                if session["run_id"] is None
                else connection.execute(
                    "SELECT * FROM navigation_collection_runs WHERE run_id = ?",
                    (session["run_id"],),
                ).fetchone()
            )
            connection.execute(
                """
                INSERT INTO navigation_decisions(
                    decision_id, session_id, step_ordinal, screen_fingerprint,
                    screen_payload_json, goal_id, plan_stage, plan_json,
                    action_name, candidate_id, scroll_direction, confidence,
                    score_margin, reflection_on_demand, planner_provider,
                    planner_fallback_used, safety_status, safety_reason,
                    destination_match_before, evidence_case_ids_json,
                    candidate_values_json, proposed_action_json,
                    safety_rewritten_action_json, retrieval_hits_json,
                    decision_provenance_json, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    json.dumps(
                        proposed_action.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(
                        action.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(retrieval_rows, ensure_ascii=False, sort_keys=True),
                    json.dumps(
                        decision_provenance or {},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    created_at,
                ),
            )
            snapshot_id = f"navss_before_{decision_id}"
            self._insert_screen_snapshot(
                connection,
                snapshot_id=snapshot_id,
                decision_id=decision_id,
                observation_id=None,
                phase="before",
                screen_fingerprint=screen_fingerprint,
                screen=screen,
                candidate_values=value_by_candidate,
                selected_candidate_id=(action.candidate_id if action.name == "click" else None),
                captured_at=created_at,
            )
            self._persist_screen_artifact(
                connection,
                snapshot_id=snapshot_id,
                screen=screen,
                screenshot_data_url=screenshot_data_url,
                phase="before",
            )
            frame_id = screen.frame_id or snapshot_id
            step_id = f"{session_id}:{step_ordinal}"
            self._append_event(
                connection,
                run_id=session["run_id"],
                session_id=session_id,
                step_id=step_id,
                event_type="screen_observed",
                actor="system",
                device_monotonic_ms=screen.captured_device_monotonic_ms,
                request_id=None,
                decision_id=decision_id,
                before_frame_id=frame_id,
                payload={"phase": "before", "screen": screen_payload},
            )
            self._append_event(
                connection,
                run_id=session["run_id"],
                session_id=session_id,
                step_id=step_id,
                event_type="candidates_built",
                actor="system",
                decision_id=decision_id,
                before_frame_id=frame_id,
                payload={
                    "candidate_ids": [candidate.candidate_id for candidate in screen.candidates],
                    "candidates_total": screen.candidates_total,
                    "candidates_captured": screen.candidates_captured,
                    "candidates_truncated": screen.candidates_truncated,
                },
            )
            self._append_event(
                connection,
                run_id=session["run_id"],
                session_id=session_id,
                step_id=step_id,
                event_type="decision_proposed",
                actor="agent",
                decision_id=decision_id,
                before_frame_id=frame_id,
                payload={
                    "action": proposed_action.model_dump(mode="json"),
                    "retrieval_hits": retrieval_rows,
                    "provenance": decision_provenance or {},
                },
            )
            self._append_event(
                connection,
                run_id=session["run_id"],
                session_id=session_id,
                step_id=step_id,
                event_type="decision_safety_rewritten",
                actor="system",
                decision_id=decision_id,
                before_frame_id=frame_id,
                payload={
                    "proposed_action": proposed_action.model_dump(mode="json"),
                    "safe_action": action.model_dump(mode="json"),
                    "safety_status": safety_status,
                    "safety_reason": safety_reason,
                },
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
        result["proposed_action"] = json.loads(result.pop("proposed_action_json"))
        result["safety_rewritten_action"] = json.loads(
            result.pop("safety_rewritten_action_json")
        )
        result["retrieval_hits"] = json.loads(result.pop("retrieval_hits_json"))
        result["decision_provenance"] = json.loads(
            result.pop("decision_provenance_json")
        )
        return result

    def recent_history(self, session_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT d.step_ordinal, d.screen_fingerprint, d.action_name, d.candidate_id,
                       d.scroll_direction, d.confidence, d.plan_stage,
                       json_extract(c.observed_payload_json, '$.label')
                           AS selected_candidate_label,
                       json_extract(c.observed_payload_json, '$.icon_semantics')
                           AS selected_candidate_icon_semantics,
                       json_extract(c.observed_payload_json, '$.nearby_text')
                           AS selected_candidate_nearby_text,
                       json_extract(c.observed_payload_json, '$.parent_semantics')
                           AS selected_candidate_parent_semantics,
                       json_extract(c.observed_payload_json, '$.child_semantics')
                           AS selected_candidate_child_semantics,
                       json_extract(c.observed_payload_json, '$.visual_role')
                           AS selected_candidate_visual_role,
                       o.connectivity_status, o.outcome_type, o.progress_label, o.failure_class,
                       x.recovery_action
                FROM navigation_decisions AS d
                LEFT JOIN navigation_observations AS o ON o.decision_id = d.decision_id
                LEFT JOIN navigation_step_executions AS x ON x.decision_id = d.decision_id
                LEFT JOIN navigation_screen_snapshots AS b
                       ON b.decision_id = d.decision_id AND b.phase = 'before'
                LEFT JOIN navigation_screen_candidates AS c
                       ON c.snapshot_id = b.snapshot_id AND c.candidate_id = d.candidate_id
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
        request_id: str,
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
        terminal_reason: str | None = None,
        handoff_reason: str = "",
        outcome_judge: str = "deterministic_evaluator",
        evaluator_id: str = "navigation_transition_verifier",
        evaluator_version: str = "1",
        after_screenshot_data_url: str | None = None,
    ) -> str:
        now = utc_now()
        with self._lock, closing(self._connect()) as connection:
            decision_scope = connection.execute(
                """
                SELECT d.session_id, d.step_ordinal, s.run_id,
                       b.frame_id AS before_frame_id
                FROM navigation_decisions AS d
                JOIN navigation_sessions AS s ON s.session_id = d.session_id
                LEFT JOIN navigation_screen_snapshots AS b
                       ON b.decision_id = d.decision_id AND b.phase = 'before'
                WHERE d.decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
            if decision_scope is None:
                raise KeyError(decision_id)
            evidence_frame_ids = [
                frame_id
                for frame_id in (
                    decision_scope["before_frame_id"],
                    None if next_screen is None else next_screen.frame_id,
                )
                if frame_id
            ]
            connection.execute(
                """
                INSERT INTO navigation_observations(
                    observation_id, decision_id, connectivity_status,
                    next_screen_fingerprint, state_changed, outcome_type,
                    progress_label, destination_match_before,
                    destination_match_after, failure_class, terminal_reason,
                    handoff_reason, outcome_judge, evaluator_id, evaluator_version,
                    outcome_evidence_frame_ids_json, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    terminal_reason,
                    handoff_reason[:300],
                    outcome_judge,
                    evaluator_id,
                    evaluator_version,
                    json.dumps(evidence_frame_ids, ensure_ascii=False),
                    now,
                ),
            )
            if session_status:
                connection.execute(
                    """
                    UPDATE navigation_sessions
                    SET status = ?,
                        terminal_reason = COALESCE(terminal_reason, ?),
                        handoff_reason = ?,
                        updated_at = ?
                    WHERE session_id = (
                        SELECT session_id FROM navigation_decisions WHERE decision_id = ?
                    )
                    """,
                    (session_status, terminal_reason, handoff_reason[:300], now, decision_id),
                )
                if session_status != "active":
                    connection.execute(
                        """
                        UPDATE navigation_collection_runs
                        SET ended_at = COALESCE(ended_at, ?)
                        WHERE run_id = ?
                        """,
                        (now, decision_scope["run_id"]),
                    )
            if next_screen is not None and next_screen_fingerprint is not None:
                snapshot_id = f"navss_after_{observation_id}"
                self._insert_screen_snapshot(
                    connection,
                    snapshot_id=snapshot_id,
                    decision_id=decision_id,
                    observation_id=observation_id,
                    phase="after",
                    screen_fingerprint=next_screen_fingerprint,
                    screen=next_screen,
                    candidate_values={},
                    selected_candidate_id=None,
                    captured_at=now,
                )
                self._persist_screen_artifact(
                    connection,
                    snapshot_id=snapshot_id,
                    screen=next_screen,
                    screenshot_data_url=after_screenshot_data_url,
                    phase="after",
                )
            connection.commit()
        return observation_id

    def record_execution_details(
        self,
        *,
        request_id: str,
        decision_id: str,
        observation_id: str,
        connectivity_status: str,
        execution_succeeded: bool | None,
        observed_signal: str,
        recovery_action: NavigationAction | None,
        candidate_forbidden: bool,
        reflection_level: str,
        reflection_reason: str,
        execution_report: ExecutionReport | None = None,
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
            scope = connection.execute(
                """
                SELECT d.session_id, d.step_ordinal, d.action_name, d.candidate_id,
                       d.scroll_direction, s.run_id, s.status AS session_status,
                       s.terminal_reason AS session_terminal_reason,
                       s.handoff_reason AS session_handoff_reason,
                       o.outcome_type, o.progress_label, o.state_changed,
                       o.failure_class, o.terminal_reason,
                       o.handoff_reason, o.outcome_judge, o.evaluator_id,
                       o.evaluator_version, b.frame_id AS before_frame_id,
                       a.frame_id AS after_frame_id,
                       a.screen_payload_json AS after_screen_payload_json
                FROM navigation_decisions AS d
                JOIN navigation_sessions AS s ON s.session_id = d.session_id
                JOIN navigation_observations AS o ON o.decision_id = d.decision_id
                LEFT JOIN navigation_screen_snapshots AS b
                       ON b.decision_id = d.decision_id AND b.phase = 'before'
                LEFT JOIN navigation_screen_snapshots AS a
                       ON a.decision_id = d.decision_id AND a.phase = 'after'
                WHERE d.decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
            if scope is None:
                raise KeyError(decision_id)
            report = execution_report
            if report is None:
                inferred_action = None
                if execution_succeeded is not None and scope["action_name"] != "stop_for_user":
                    inferred_action = NavigationAction(
                        name=str(scope["action_name"]),
                        candidate_id=scope["candidate_id"],
                        direction=scope["scroll_direction"],
                    )
                report = ExecutionReport(actual_action=inferred_action)
            connection.execute(
                """
                INSERT INTO navigation_step_executions(
                    decision_id, observation_id, execution_status, execution_succeeded,
                    observed_signal, recovery_action, actual_action_json,
                    executor_method, attempt_no,
                    execution_started_device_monotonic_ms,
                    execution_finished_device_monotonic_ms, failure_code,
                    settle_duration_ms, settle_reason, external_package,
                    human_intervention, candidate_forbidden, reflection_level,
                    reflection_reason, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    observation_id,
                    execution_status,
                    None if execution_succeeded is None else int(execution_succeeded),
                    observed_signal,
                    None if recovery_action is None else recovery_action.name,
                    json.dumps(
                        {}
                        if report.actual_action is None
                        else report.actual_action.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    report.executor_method,
                    report.attempt_no,
                    report.execution_started_device_monotonic_ms,
                    report.execution_finished_device_monotonic_ms,
                    report.failure_code,
                    report.settle_duration_ms,
                    report.settle_reason,
                    report.external_package,
                    int(report.human_intervention),
                    int(candidate_forbidden),
                    reflection_level,
                    reflection_reason[:1000],
                    utc_now(),
                ),
            )
            step_id = f"{scope['session_id']}:{scope['step_ordinal']}"
            actual_action_payload = (
                None
                if report.actual_action is None
                else report.actual_action.model_dump(mode="json")
            )
            if actual_action_payload is not None:
                self._append_event(
                    connection,
                    run_id=scope["run_id"],
                    session_id=scope["session_id"],
                    step_id=step_id,
                    event_type="action_attempted",
                    actor="human" if report.human_intervention else "agent",
                    device_monotonic_ms=report.execution_started_device_monotonic_ms,
                    request_id=request_id,
                    decision_id=decision_id,
                    before_frame_id=scope["before_frame_id"],
                    payload={
                        "actual_action": actual_action_payload,
                        "executor_method": report.executor_method,
                        "attempt_no": report.attempt_no,
                    },
                )
            self._append_event(
                connection,
                run_id=scope["run_id"],
                session_id=scope["session_id"],
                step_id=step_id,
                event_type="action_completed",
                actor="human" if report.human_intervention else "agent",
                device_monotonic_ms=report.execution_finished_device_monotonic_ms,
                request_id=request_id,
                decision_id=decision_id,
                before_frame_id=scope["before_frame_id"],
                after_frame_id=scope["after_frame_id"],
                payload={
                    "actual_action": actual_action_payload,
                    "execution_status": execution_status,
                    "execution_succeeded": execution_succeeded,
                    "observed_signal": observed_signal,
                    "executor_method": report.executor_method,
                    "failure_code": report.failure_code,
                    "settle_duration_ms": report.settle_duration_ms,
                    "settle_reason": report.settle_reason,
                    "external_package": report.external_package,
                },
            )
            if scope["after_frame_id"]:
                self._append_event(
                    connection,
                    run_id=scope["run_id"],
                    session_id=scope["session_id"],
                    step_id=step_id,
                    event_type="screen_observed",
                    actor="system",
                    request_id=request_id,
                    decision_id=decision_id,
                    before_frame_id=scope["before_frame_id"],
                    after_frame_id=scope["after_frame_id"],
                    payload={
                        "phase": "after",
                        "screen": json.loads(scope["after_screen_payload_json"]),
                    },
                )
            self._append_event(
                connection,
                run_id=scope["run_id"],
                session_id=scope["session_id"],
                step_id=step_id,
                event_type="outcome_evaluated",
                actor="system",
                request_id=request_id,
                decision_id=decision_id,
                before_frame_id=scope["before_frame_id"],
                after_frame_id=scope["after_frame_id"],
                payload={
                    "outcome_type": scope["outcome_type"],
                    "progress_label": scope["progress_label"],
                    "state_changed": (
                        None if scope["state_changed"] is None else bool(scope["state_changed"])
                    ),
                    "failure_class": scope["failure_class"],
                    "outcome_judge": scope["outcome_judge"],
                    "evaluator_id": scope["evaluator_id"],
                    "evaluator_version": scope["evaluator_version"],
                },
            )
            terminal_reason = scope["terminal_reason"] or scope["session_terminal_reason"]
            if terminal_reason:
                self._append_event(
                    connection,
                    run_id=scope["run_id"],
                    session_id=scope["session_id"],
                    step_id=step_id,
                    event_type=(
                        "human_handoff"
                        if terminal_reason == "safe_user_handoff"
                        else "session_ended"
                    ),
                    actor="system",
                    request_id=request_id,
                    decision_id=decision_id,
                    before_frame_id=scope["before_frame_id"],
                    after_frame_id=scope["after_frame_id"],
                    payload={
                        "terminal_reason": terminal_reason,
                        "handoff_reason": (
                            scope["handoff_reason"] or scope["session_handoff_reason"]
                        ),
                        "session_status": scope["session_status"],
                    },
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
            collection_run = None
            if session["run_id"]:
                collection_run = connection.execute(
                    """
                    SELECT * FROM navigation_collection_runs
                    WHERE run_id = ?
                    """,
                    (session["run_id"],),
                ).fetchone()
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
                       o.terminal_reason, o.handoff_reason, o.outcome_judge,
                       o.evaluator_id, o.evaluator_version,
                       o.outcome_evidence_frame_ids_json,
                       x.execution_status, x.execution_succeeded, x.observed_signal,
                       x.recovery_action, x.actual_action_json, x.executor_method,
                       x.attempt_no, x.execution_started_device_monotonic_ms,
                       x.execution_finished_device_monotonic_ms, x.failure_code,
                       x.settle_duration_ms, x.settle_reason, x.external_package,
                       x.human_intervention, x.candidate_forbidden,
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
                    snapshot_item["missing_parts"] = json.loads(
                        snapshot_item.pop("missing_parts_json")
                    )
                    snapshot_item["artifacts"] = [
                        dict(artifact)
                        for artifact in connection.execute(
                            """
                            SELECT * FROM navigation_screen_artifacts
                            WHERE snapshot_id = ? ORDER BY created_at
                            """,
                            (snapshot_item["snapshot_id"],),
                        ).fetchall()
                    ]
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
                item["proposed_action"] = json.loads(item.pop("proposed_action_json"))
                item["safety_rewritten_action"] = json.loads(
                    item.pop("safety_rewritten_action_json")
                )
                item["retrieval_hits"] = json.loads(item.pop("retrieval_hits_json"))
                item["decision_provenance"] = json.loads(
                    item.pop("decision_provenance_json")
                )
                item["outcome_evidence_frame_ids"] = json.loads(
                    item.pop("outcome_evidence_frame_ids_json") or "[]"
                )
                item["actual_action"] = json.loads(item.pop("actual_action_json") or "{}")
                item["screen"] = screens
                item.pop("screen_payload_json", None)
                steps.append(item)
            event_rows = connection.execute(
                """
                SELECT * FROM navigation_collection_events
                WHERE session_id = ? ORDER BY sequence_no
                """,
                (session_id,),
            ).fetchall()
        session_payload = dict(session)
        session_payload["task_context"] = json.loads(
            session_payload.pop("task_context_json") or "{}"
        )
        session_payload["dataset_split"] = (
            "unassigned" if split_row is None else str(split_row["split"])
        )
        return {
            "schema_version": "runtime-episode.v3",
            "session": session_payload,
            "collection_run": (
                None
                if collection_run is None
                else {
                    **dict(collection_run),
                    "context": json.loads(collection_run["context_json"]),
                }
            ),
            "candidate_set_status": episode_candidate_status,
            "steps": steps,
            "events": [
                {
                    **dict(event),
                    "payload": json.loads(event["payload_json_redacted"]),
                }
                for event in event_rows
            ],
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

    def _persist_screen_artifact(
        self,
        connection: sqlite3.Connection,
        *,
        snapshot_id: str,
        screen: ScreenObservation,
        screenshot_data_url: str | None,
        phase: str,
    ) -> None:
        if self.screen_artifact_dir is None or not screenshot_data_url:
            return
        policy = connection.execute(
            """
            SELECT r.artifact_policy, r.test_account
            FROM navigation_screen_snapshots AS ss
            JOIN navigation_decisions AS d ON d.decision_id = ss.decision_id
            JOIN navigation_sessions AS s ON s.session_id = d.session_id
            JOIN navigation_collection_runs AS r ON r.run_id = s.run_id
            WHERE ss.snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        if policy is None:
            return
        artifact_policy = str(policy["artifact_policy"])
        if artifact_policy == "raw_full_capture":
            redaction_status = "raw"
            redaction_version = ""
            retention_class = "raw_full_capture"
        elif artifact_policy == "test_account_restricted" and bool(policy["test_account"]):
            redaction_status = "redacted"
            redaction_version = "android-visual-mask-v1"
            retention_class = "test_account_restricted"
        else:
            return
        try:
            header, encoded = screenshot_data_url.split(",", 1)
            mime_type = header.removeprefix("data:").split(";", 1)[0].lower()
            suffix = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
            }.get(mime_type)
            if suffix is None:
                return
            payload = base64.b64decode(encoded, validate=True)
            if not payload or len(payload) > 12_000_000:
                return
            artifact_id = f"navart_{uuid.uuid4().hex}"
            target = self.screen_artifact_dir / f"{artifact_id}{suffix}"
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(payload)
            os.chmod(temporary, 0o600)
            temporary.replace(target)
        except (ValueError, binascii.Error, OSError):
            return
        connection.execute(
            """
            INSERT INTO navigation_screen_artifacts(
                artifact_id, snapshot_id, frame_id, artifact_type, storage_uri,
                mime_type, byte_size, width, height, redaction_status,
                redaction_version, retention_class, capture_tree_delta_ms,
                created_at, expires_at
            ) VALUES (?, ?, ?, 'screenshot', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                artifact_id,
                snapshot_id,
                screen.frame_id,
                str(target),
                mime_type,
                len(payload),
                screen.screen_width_px,
                screen.screen_height_px,
                redaction_status,
                redaction_version,
                retention_class,
                screen.screenshot_tree_delta_ms,
                utc_now(),
            ),
        )

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
        # Reuse the screen-wide privacy context for both the snapshot JSON and
        # the normalized candidate rows.  Redacting each candidate in
        # isolation can miss an account identifier whose profile context is
        # carried by a sibling/visual field.
        sanitized_screen = _screen_payload(screen)
        sanitized_candidates = {
            str(candidate["candidate_id"]): candidate
            for candidate in sanitized_screen["candidates"]
        }
        candidate_set_status = (
            "partial"
            if screen.nodes_truncated or screen.candidates_truncated
            else "complete"
        )
        connection.execute(
            """
            INSERT INTO navigation_screen_snapshots(
                snapshot_id, decision_id, observation_id, phase, frame_id, screen_fingerprint,
                window_title_redacted, activity_name_redacted, navigation_depth,
                candidate_set_status, screen_width_px, screen_height_px, density_dpi,
                nodes_total, nodes_captured, nodes_truncated, candidates_total,
                candidates_captured, candidates_truncated, missing_parts_json,
                screen_payload_json, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                decision_id,
                observation_id,
                phase,
                screen.frame_id,
                screen_fingerprint,
                redact_text(screen.window_title),
                redact_text(screen.activity_name),
                screen.navigation_depth,
                candidate_set_status,
                screen.screen_width_px,
                screen.screen_height_px,
                screen.density_dpi,
                screen.nodes_total,
                screen.nodes_captured,
                int(screen.nodes_truncated),
                screen.candidates_total,
                screen.candidates_captured,
                int(screen.candidates_truncated),
                json.dumps(screen.missing_parts, ensure_ascii=False),
                json.dumps(sanitized_screen, ensure_ascii=False, sort_keys=True),
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
                    json.dumps(
                        sanitized_candidates[candidate.candidate_id],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
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
        """Return reliable failed candidates for the active collection attempt.

        Candidate IDs already include the accessibility resource/class/label/path
        identity.  Scoping the ban only to a full-screen fingerprint allowed the
        same stable candidate to be clicked again whenever dynamic screen content
        changed the fingerprint.  A bounded Android episode can also roll over to
        a new session while the app, version, locale, and goal stay unchanged.  A
        candidate failed in two prior sessions is reliable enough to suppress in
        that continuation, while one-off failures remain local to their session.
        """

        with self._lock, closing(self._connect()) as connection:
            rows = connection.execute(
                """
                WITH current_session AS (
                    SELECT app_package, app_version, locale, COALESCE(goal_id, '') AS goal_id
                    FROM navigation_sessions
                    WHERE session_id = ?
                ), candidate_failures AS (
                    SELECT
                        recovery.candidate_id,
                        MAX(CASE WHEN recovery.session_id = ? THEN 1 ELSE 0 END)
                            AS failed_in_current_session,
                        COUNT(DISTINCT CASE
                            WHEN recovery.session_id <> ? THEN recovery.session_id
                        END) AS prior_session_failures
                    FROM navigation_recovery_memory AS recovery
                    JOIN navigation_sessions AS failed_session
                        ON failed_session.session_id = recovery.session_id
                    JOIN current_session
                        ON failed_session.app_package = current_session.app_package
                       AND failed_session.app_version = current_session.app_version
                       AND failed_session.locale = current_session.locale
                       AND COALESCE(failed_session.goal_id, '') = current_session.goal_id
                    WHERE recovery.forbidden = 1
                      AND (
                          recovery.session_id = ?
                          OR julianday(recovery.updated_at) >= julianday('now', '-1 day')
                      )
                    GROUP BY recovery.candidate_id
                )
                SELECT candidate_id
                FROM candidate_failures
                WHERE failed_in_current_session = 1 OR prior_session_failures >= 2
                """,
                (session_id, session_id, session_id, session_id),
            ).fetchall()
        return {str(row["candidate_id"]) for row in rows}
