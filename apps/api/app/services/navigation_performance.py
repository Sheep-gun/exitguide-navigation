from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}\b")
SENSITIVE_KEYS = {
    "account_name",
    "card_number",
    "cookie",
    "email",
    "goal_text",
    "password",
    "phone",
    "screen_text",
    "token",
    "user_name",
}
SAFE_MEASUREMENT_SOURCES = {
    "server_runtime",
    "synthetic",
    "real_device",
    "real_device_gold",
}
IMPORT_MEASUREMENT_SOURCES = {"real_device", "real_device_gold"}
# Only evidence produced by a server-controlled benchmark or an explicitly
# reviewed human-gold import may change route correctness/safety eligibility.
# ``device_gold`` is retained as a read-compatible legacy value for databases
# created before the lifecycle hardening migration.
TRUSTED_VERIFICATION_LEVELS = frozenset({"benchmark_gold", "human_gold", "device_gold"})
SCREEN_FINGERPRINT_PATTERN = re.compile(r"^us_[a-f0-9]{16}$")
EXECUTED_TRANSITION_OUTCOMES = frozenset(
    {
        "navigated",
        "no_change",
        "failed",
        "unexpected",
        "cancelled",
        "off_target",
        "dead_end_branch",
    }
)
WRONG_NAVIGATION_OUTCOMES = frozenset(
    {"no_change", "failed", "unexpected", "off_target", "dead_end_branch"}
)


@dataclass(frozen=True)
class StageMeasurement:
    measurement_source: str = "server_runtime"
    server_total_ms: float = 0.0
    model_decision_ms: float = 0.0
    db_lookup_ms: float = 0.0
    screen_analysis_ms: float = 0.0
    screen_capture_ms: float = 0.0
    action_execution_ms: float = 0.0
    ui_settle_ms: float = 0.0
    external_wait_ms: float = 0.0
    exploration_elapsed_ms: float | None = None

    def normalized(self) -> StageMeasurement:
        source = self.measurement_source if self.measurement_source in SAFE_MEASUREMENT_SOURCES else "server_runtime"
        return StageMeasurement(
            measurement_source=source,
            server_total_ms=_duration(self.server_total_ms),
            model_decision_ms=_duration(self.model_decision_ms),
            db_lookup_ms=_duration(self.db_lookup_ms),
            screen_analysis_ms=_duration(self.screen_analysis_ms),
            screen_capture_ms=_duration(self.screen_capture_ms),
            action_execution_ms=_duration(self.action_execution_ms),
            ui_settle_ms=_duration(self.ui_settle_ms),
            external_wait_ms=_duration(self.external_wait_ms),
            exploration_elapsed_ms=(
                None if self.exploration_elapsed_ms is None else _duration(self.exploration_elapsed_ms, 3_600_000.0)
            ),
        )


@dataclass(frozen=True)
class RealDeviceImportPlan:
    """Fully validated, immutable plan shared by check-only and import paths."""

    measurement_source: str
    verification_level: str
    sessions: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PerformanceResult:
    stage_ordinal: int
    measurement_source: str
    server_total_ms: float
    model_decision_ms: float
    db_lookup_ms: float
    screen_analysis_ms: float
    screen_capture_ms: float
    action_execution_ms: float
    ui_settle_ms: float
    external_wait_ms: float
    time_to_confirmed_destination_ms: float | None
    route_reused: bool
    route_rank: int | None
    executed_transition_outcome: str | None
    wrong_guidance_delta: int
    wrong_click_delta: int
    failure_reason: str | None

    def payload(self) -> dict[str, object]:
        return {
            "stage_ordinal": self.stage_ordinal,
            "measurement_source": self.measurement_source,
            "server_total_ms": round(self.server_total_ms, 3),
            "model_decision_ms": round(self.model_decision_ms, 3),
            "db_lookup_ms": round(self.db_lookup_ms, 3),
            "screen_analysis_ms": round(self.screen_analysis_ms, 3),
            "screen_capture_ms": round(self.screen_capture_ms, 3),
            "action_execution_ms": round(self.action_execution_ms, 3),
            "ui_settle_ms": round(self.ui_settle_ms, 3),
            "external_wait_ms": round(self.external_wait_ms, 3),
            "time_to_confirmed_destination_ms": (
                None
                if self.time_to_confirmed_destination_ms is None
                else round(self.time_to_confirmed_destination_ms, 3)
            ),
            "route_reused": self.route_reused,
            "route_rank": self.route_rank,
            "executed_transition_outcome": self.executed_transition_outcome,
            "wrong_guidance_delta": self.wrong_guidance_delta,
            "wrong_click_delta": self.wrong_click_delta,
            "failure_reason": self.failure_reason,
        }


class NavigationPerformanceStore:
    """Safety-constrained route timing store backed by the graph SQLite DB.

    Raw screen text and the user's goal are deliberately absent. Only package
    metadata, opaque fingerprints, function IDs, counters, and timings are
    persisted. Synthetic measurements are tagged and never mixed into the
    real-device performance baseline.
    """

    def __init__(self, database_path: Path, *, minimum_samples: int = 3) -> None:
        self.database_path = database_path
        self.minimum_samples = max(1, minimum_samples)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def record_stage(
        self,
        *,
        session_id: str,
        app_package: str,
        app_version: str,
        locale: str,
        goal_key: str,
        target_function: str,
        start_screen_fingerprint: str,
        current_screen_fingerprint: str,
        destination_screen_fingerprint: str,
        decision_mode: str,
        phase: str,
        action: str,
        safe_to_execute: bool,
        selected_risk_level: str,
        selected_element_key: str,
        route_id: str,
        failure_type: str,
        measurement: StageMeasurement,
        executed_recommendation_id: str = "",
        executed_transition_outcome: str = "",
    ) -> PerformanceResult:
        measurement = measurement.normalized()
        executed_recommendation_id = executed_recommendation_id.strip()
        executed_transition_outcome = executed_transition_outcome.strip()
        if bool(executed_recommendation_id) != bool(executed_transition_outcome):
            raise ValueError(
                "Executed recommendation ID and transition outcome must be provided together"
            )
        if (
            executed_transition_outcome
            and executed_transition_outcome not in EXECUTED_TRANSITION_OUTCOMES
        ):
            raise ValueError("Unsupported executed navigation transition outcome")
        now = _utc_now()
        app_key = _app_key(app_package, app_version, locale)
        version_signature = _version_signature(app_package, app_version, locale)
        route_reused = decision_mode == "route_cache"
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO app_version_signatures (
                  version_signature, app_key, app_package, app_version, locale,
                  first_screen_fingerprint, first_seen_at, last_seen_at,
                  valid_route_count, invalid_route_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                ON CONFLICT(version_signature) DO UPDATE SET
                  last_seen_at = excluded.last_seen_at,
                  first_screen_fingerprint = CASE
                    WHEN app_version_signatures.first_screen_fingerprint = ''
                    THEN excluded.first_screen_fingerprint
                    ELSE app_version_signatures.first_screen_fingerprint
                  END
                """,
                (
                    version_signature,
                    app_key,
                    app_package,
                    app_version,
                    locale,
                    start_screen_fingerprint,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO navigation_sessions (
                  session_id, app_key, version_signature, goal_key, target_function,
                  measurement_source, status, start_screen_fingerprint,
                  destination_screen_fingerprint, route_id, route_reused,
                  destination_correct, safe_stop, unsafe_click_count, wrong_click_count,
                  click_count, scroll_count, back_count, revisit_count, recovery_count,
                  failure_type, started_at, destination_confirmed_at,
                  time_to_destination_ms, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, '', '', 0,
                          0, 0, 0, 0, 0, 0, 0, 0, 0, '', ?, '', NULL, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  target_function = excluded.target_function,
                  measurement_source = CASE
                    WHEN navigation_sessions.measurement_source IN ('real_device', 'real_device_gold')
                    THEN navigation_sessions.measurement_source
                    ELSE excluded.measurement_source
                  END,
                  updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    app_key,
                    version_signature,
                    goal_key,
                    target_function,
                    measurement.measurement_source,
                    start_screen_fingerprint,
                    now,
                    now,
                    now,
                ),
            )
            wrong_guidance_delta = 0
            wrong_click_delta = 0
            if executed_recommendation_id:
                outcome_insert = connection.execute(
                    """
                    INSERT OR IGNORE INTO navigation_instruction_outcomes (
                      recommendation_id, session_id, outcome, wrong_guidance,
                      wrong_click, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        executed_recommendation_id,
                        session_id,
                        executed_transition_outcome,
                        int(executed_transition_outcome in WRONG_NAVIGATION_OUTCOMES),
                        int(executed_transition_outcome in WRONG_NAVIGATION_OUTCOMES),
                        now,
                    ),
                )
                if outcome_insert.rowcount == 1:
                    wrong_guidance_delta = int(
                        executed_transition_outcome in WRONG_NAVIGATION_OUTCOMES
                    )
                    wrong_click_delta = wrong_guidance_delta
            ordinal = int(
                connection.execute(
                    "SELECT COUNT(*) FROM navigation_stage_timings WHERE session_id = ?",
                    (session_id,),
                ).fetchone()[0]
            )
            stage_total_ms = _stage_total(measurement)
            connection.execute(
                """
                INSERT INTO navigation_stage_timings (
                  session_id, ordinal, screen_fingerprint, decision_mode, phase,
                  automation_action, selected_element_key, route_id, measurement_source, server_total_ms,
                  model_decision_ms, db_lookup_ms, screen_analysis_ms,
                  screen_capture_ms, action_execution_ms, ui_settle_ms,
                  external_wait_ms, stage_total_ms, executed_transition_outcome,
                  wrong_guidance_delta, wrong_click_delta, failure_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    ordinal,
                    current_screen_fingerprint,
                    decision_mode,
                    phase,
                    action,
                    selected_element_key,
                    route_id,
                    measurement.measurement_source,
                    measurement.server_total_ms,
                    measurement.model_decision_ms,
                    measurement.db_lookup_ms,
                    measurement.screen_analysis_ms,
                    measurement.screen_capture_ms,
                    measurement.action_execution_ms,
                    measurement.ui_settle_ms,
                    measurement.external_wait_ms,
                    stage_total_ms,
                    executed_transition_outcome,
                    wrong_guidance_delta,
                    wrong_click_delta,
                    failure_type,
                    now,
                ),
            )
            revisit = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM navigation_stage_timings
                    WHERE session_id = ? AND screen_fingerprint = ?
                    """,
                    (session_id, current_screen_fingerprint),
                ).fetchone()[0]
                > 1
            )
            unsafe_click = int(action == "click" and (not safe_to_execute or selected_risk_level != "low"))
            connection.execute(
                """
                UPDATE navigation_sessions SET
                  click_count = click_count + ?,
                  scroll_count = scroll_count + ?,
                  back_count = back_count + ?,
                  revisit_count = revisit_count + ?,
                  recovery_count = recovery_count + ?,
                  unsafe_click_count = unsafe_click_count + ?,
                  wrong_guidance_count = wrong_guidance_count + ?,
                  wrong_click_count = wrong_click_count + ?,
                  route_reused = MAX(route_reused, ?),
                  route_id = CASE WHEN ? <> '' THEN ? ELSE route_id END,
                  destination_screen_fingerprint = CASE WHEN ? <> '' THEN ? ELSE destination_screen_fingerprint END,
                  failure_type = CASE WHEN ? <> '' THEN ? ELSE failure_type END,
                  updated_at = ?
                WHERE session_id = ?
                """,
                (
                    int(action == "click"),
                    int(action == "scroll_forward"),
                    int(action == "back"),
                    revisit,
                    int(action == "back" or bool(failure_type)),
                    unsafe_click,
                    wrong_guidance_delta,
                    wrong_click_delta,
                    int(route_reused),
                    route_id,
                    route_id,
                    destination_screen_fingerprint,
                    destination_screen_fingerprint,
                    failure_type,
                    failure_type,
                    now,
                    session_id,
                ),
            )
            time_to_destination_ms: float | None = None
            if phase == "destination_reached":
                time_to_destination_ms = self._finish_session(
                    connection,
                    session_id=session_id,
                    route_id=route_id,
                    destination_screen_fingerprint=destination_screen_fingerprint or current_screen_fingerprint,
                    destination_correct=True,
                    safe_stop=(action == "stop" and not safe_to_execute),
                    failure_type="",
                    client_elapsed_ms=measurement.exploration_elapsed_ms,
                    now=now,
                )
            elif phase == "stopped":
                self._finish_session(
                    connection,
                    session_id=session_id,
                    route_id=route_id,
                    destination_screen_fingerprint="",
                    destination_correct=False,
                    safe_stop=(action == "stop" and not safe_to_execute),
                    failure_type=failure_type or "exploration_stopped",
                    client_elapsed_ms=None,
                    now=now,
                )
            connection.commit()
            route_rank = self._route_rank(connection, route_id)
        return PerformanceResult(
            stage_ordinal=ordinal,
            measurement_source=measurement.measurement_source,
            server_total_ms=measurement.server_total_ms,
            model_decision_ms=measurement.model_decision_ms,
            db_lookup_ms=measurement.db_lookup_ms,
            screen_analysis_ms=measurement.screen_analysis_ms,
            screen_capture_ms=measurement.screen_capture_ms,
            action_execution_ms=measurement.action_execution_ms,
            ui_settle_ms=measurement.ui_settle_ms,
            external_wait_ms=measurement.external_wait_ms,
            time_to_confirmed_destination_ms=time_to_destination_ms,
            route_reused=route_reused,
            route_rank=route_rank,
            executed_transition_outcome=(
                executed_transition_outcome or None
            ),
            wrong_guidance_delta=wrong_guidance_delta,
            wrong_click_delta=wrong_click_delta,
            failure_reason=failure_type or None,
        )

    def apply_validation(
        self,
        *,
        session_id: str,
        destination_correct: bool,
        safe_stop: bool,
        unsafe_clicks: int = 0,
        wrong_clicks: int = 0,
        failure_type: str = "",
        verification_level: str = "benchmark_gold",
    ) -> None:
        """Replace inferred success with benchmark/user verified truth."""
        if verification_level not in TRUSTED_VERIFICATION_LEVELS:
            raise ValueError(
                "Route correctness validation requires benchmark_gold or human_gold provenance"
            )
        destination_correct = _validated_bool(destination_correct, "destination_correct")
        safe_stop = _validated_bool(safe_stop, "safe_stop")
        unsafe_clicks = _validated_count(unsafe_clicks, "unsafe_clicks")
        wrong_clicks = _validated_count(wrong_clicks, "wrong_clicks")
        now = _utc_now()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown navigation performance session: {session_id}")
            connection.execute(
                """
                UPDATE navigation_sessions SET status = ?, destination_correct = ?, safe_stop = ?,
                  unsafe_click_count = ?, wrong_click_count = ?, failure_type = ?,
                  verification_level = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (
                    "completed" if destination_correct else "failed",
                    int(destination_correct),
                    int(safe_stop),
                    unsafe_clicks,
                    wrong_clicks,
                    failure_type,
                    verification_level,
                    now,
                    session_id,
                ),
            )
            self._refresh_performance_from_sessions(
                connection,
                app_key=str(row["app_key"]),
                target_function=str(row["target_function"]),
                start_screen_fingerprint=str(row["start_screen_fingerprint"]),
            )
            connection.commit()

    def ranked_route_ids(
        self,
        *,
        app_package: str,
        app_version: str,
        locale: str,
        target_function: str,
        start_screen_fingerprint: str = "",
    ) -> list[str]:
        app_key = _app_key(app_package, app_version, locale)
        with self._connection() as connection:
            if start_screen_fingerprint:
                rows = connection.execute(
                    """
                    SELECT route_id FROM route_rankings
                    WHERE app_key = ? AND target_function = ?
                      AND start_screen_fingerprint = ? AND eligible = 1
                    ORDER BY rank_order, route_id
                    """,
                    (app_key, target_function, start_screen_fingerprint),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT route_id, MIN(rank_order) AS best_rank
                    FROM route_rankings
                    WHERE app_key = ? AND target_function = ? AND eligible = 1
                    GROUP BY route_id ORDER BY best_rank, route_id
                    """,
                    (app_key, target_function),
                ).fetchall()
            route_ids = [str(row["route_id"]) for row in rows]
            if len(route_ids) > 1:
                first = connection.execute(
                    "SELECT selection_count FROM route_rankings WHERE route_id = ? ORDER BY rank_order LIMIT 1",
                    (route_ids[0],),
                ).fetchone()
                selection_count = 0 if first is None else int(first["selection_count"])
                # Deterministic 10% exploration keeps a verified backup route
                # alive without making request outcomes random.
                if selection_count > 0 and selection_count % 10 == 9:
                    route_ids[0], route_ids[1] = route_ids[1], route_ids[0]
            if route_ids:
                connection.execute(
                    """
                    UPDATE route_rankings SET selection_count = selection_count + 1,
                      last_selected_at = ? WHERE route_id = ?
                    """,
                    (_utc_now(), route_ids[0]),
                )
                connection.commit()
        return route_ids

    def session(self, session_id: str) -> dict[str, object] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return None if row is None else dict(row)

    def record_client_completion(
        self,
        *,
        session_id: str,
        time_to_confirmed_destination_ms: float,
        measurement_source: str = "real_device",
    ) -> dict[str, object]:
        # Public clients provide timing only. Gold provenance is assigned only
        # by the offline, server-controlled importer after full validation.
        if measurement_source != "real_device":
            raise ValueError("Client completion timing provenance is fixed to real_device")
        elapsed_ms = _duration(time_to_confirmed_destination_ms, 3_600_000.0)
        if elapsed_ms <= 0.0:
            raise ValueError("time_to_confirmed_destination_ms must be greater than zero")
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM navigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown navigation performance session: {session_id}")
            if str(row["status"]) != "completed" or not bool(row["destination_correct"]):
                raise ValueError("Client completion timing requires a completed destination session")
            if (
                str(row["measurement_source"]) == "real_device_gold"
                or str(row["verification_level"]) in TRUSTED_VERIFICATION_LEVELS
            ):
                raise ValueError("Trusted gold sessions are immutable from the public completion API")
            connection.execute(
                """
                UPDATE navigation_sessions SET measurement_source = ?,
                  time_to_destination_ms = ?, updated_at = ? WHERE session_id = ?
                """,
                ("real_device", elapsed_ms, _utc_now(), session_id),
            )
            self._refresh_performance_from_sessions(
                connection,
                app_key=str(row["app_key"]),
                target_function=str(row["target_function"]),
                start_screen_fingerprint=str(row["start_screen_fingerprint"]),
            )
            connection.commit()
        updated = self.session(session_id)
        if updated is None:
            raise RuntimeError("Navigation completion timing was not persisted")
        return updated

    def invalidate_route(self, route_id: str) -> None:
        """Remove a UI-mismatched route from the safe timing candidate set."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM route_performance WHERE route_id = ?",
                (route_id,),
            ).fetchone()
            if row is None:
                return
            connection.execute(
                """
                UPDATE route_performance SET eligible = 0,
                  failure_count = failure_count + 1, updated_at = ?
                WHERE route_id = ?
                """,
                (_utc_now(), route_id),
            )
            self._recompute_rankings(
                connection,
                app_key=str(row["app_key"]),
                target_function=str(row["target_function"]),
                start_screen_fingerprint=str(row["start_screen_fingerprint"]),
            )
            connection.execute(
                """
                UPDATE app_version_signatures SET invalid_route_count = invalid_route_count + 1
                WHERE version_signature = ?
                """,
                (str(row["version_signature"]),),
            )
            connection.commit()

    def summary(self, *, measurement_source: str | None = None) -> dict[str, object]:
        clauses = ["session.status IN ('completed', 'failed')"]
        values: list[object] = []
        if measurement_source:
            clauses.append("session.measurement_source = ?")
            values.append(measurement_source)
        where = " AND ".join(clauses)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT session.*,
                  COALESCE((
                    SELECT SUM(stage.model_decision_ms)
                    FROM navigation_stage_timings stage
                    WHERE stage.session_id = session.session_id
                  ), 0) AS model_decision_ms
                FROM navigation_sessions session WHERE {where}
                """,
                values,
            ).fetchall()
            execution_rows = connection.execute(
                f"""
                SELECT outcome.outcome, outcome.wrong_guidance, outcome.wrong_click
                FROM navigation_instruction_outcomes outcome
                JOIN navigation_sessions session ON session.session_id = outcome.session_id
                WHERE {where}
                """,
                values,
            ).fetchall()
        outcome_rows = [dict(row) for row in rows]
        timing_rows = [
            row
            for row in outcome_rows
            if row.get("status") == "completed" and row.get("time_to_destination_ms") is not None
        ]
        trusted_rows = [
            row
            for row in outcome_rows
            if str(row.get("verification_level", "runtime_inferred"))
            in TRUSTED_VERIFICATION_LEVELS
        ]
        metrics = _session_metrics(timing_rows)
        trusted_metrics = _session_metrics(trusted_rows)
        runtime_wrong_guidance_count = sum(
            int(row["wrong_guidance"]) for row in execution_rows
        )
        runtime_wrong_click_count = sum(int(row["wrong_click"]) for row in execution_rows)
        failure_reason_counts: dict[str, int] = {}
        for row in outcome_rows:
            failure_reason = str(row.get("failure_type") or "")
            if failure_reason:
                failure_reason_counts[failure_reason] = (
                    failure_reason_counts.get(failure_reason, 0) + 1
                )
        transition_outcome_counts: dict[str, int] = {}
        for row in execution_rows:
            outcome = str(row["outcome"])
            transition_outcome_counts[outcome] = transition_outcome_counts.get(outcome, 0) + 1
        for key in (
            "destination_accuracy",
            "safe_stop_rate",
            "unsafe_click_rate",
            "wrong_click_rate",
        ):
            metrics[key] = trusted_metrics[key]
        metrics.update(
            {
                "timing_session_count": len(timing_rows),
                "outcome_session_count": len(outcome_rows),
                "trusted_session_count": len(trusted_rows),
                "correctness_provenance": "trusted_gold" if trusted_rows else "unavailable",
                "runtime_executed_instruction_count": len(execution_rows),
                "runtime_wrong_guidance_count": runtime_wrong_guidance_count,
                "runtime_wrong_click_count": runtime_wrong_click_count,
                "runtime_wrong_guidance_rate": _ratio(
                    runtime_wrong_guidance_count,
                    len(execution_rows),
                ),
                "runtime_wrong_click_rate": _ratio(
                    runtime_wrong_click_count,
                    len(execution_rows),
                ),
                "runtime_transition_outcome_counts": dict(
                    sorted(transition_outcome_counts.items())
                ),
                "failure_reason_counts": dict(sorted(failure_reason_counts.items())),
            }
        )
        return metrics

    def import_real_device_log(self, payload: Mapping[str, Any]) -> dict[str, object]:
        return self.import_real_device_plan(plan_real_device_import(payload))

    def import_real_device_plan(self, plan: RealDeviceImportPlan) -> dict[str, object]:
        """Apply one prevalidated plan as a single idempotent transaction."""
        expected_verification = (
            "human_gold" if plan.measurement_source == "real_device_gold" else "runtime_inferred"
        )
        if (
            plan.measurement_source not in IMPORT_MEASUREMENT_SOURCES
            or plan.verification_level != expected_verification
        ):
            raise ValueError("Invalid navigation performance import provenance plan")
        affected_groups: set[tuple[str, str, str]] = set()
        with self._connection() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                for item in plan.sessions:
                    old_row = connection.execute(
                        "SELECT app_key, target_function, start_screen_fingerprint, verification_level "
                        "FROM navigation_sessions "
                        "WHERE session_id = ?",
                        (item["session_id"],),
                    ).fetchone()
                    if old_row is not None:
                        if (
                            str(old_row["verification_level"]) in TRUSTED_VERIFICATION_LEVELS
                            and plan.verification_level not in TRUSTED_VERIFICATION_LEVELS
                        ):
                            raise ValueError(
                                f"Timing-only import cannot overwrite trusted session: {item['session_id']}"
                            )
                        affected_groups.add(
                            (
                                str(old_row["app_key"]),
                                str(old_row["target_function"]),
                                str(old_row["start_screen_fingerprint"]),
                            )
                        )
                    affected_groups.add(
                        self._import_session(
                            connection,
                            item,
                            source=plan.measurement_source,
                            verification_level=plan.verification_level,
                        )
                    )
                for app_key, target_function, start_screen_fingerprint in sorted(affected_groups):
                    self._refresh_performance_from_sessions(
                        connection,
                        app_key=app_key,
                        target_function=target_function,
                        start_screen_fingerprint=start_screen_fingerprint,
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return {
            "imported_sessions": len(plan.sessions),
            "measurement_source": plan.measurement_source,
            "verification_level": plan.verification_level,
            "privacy_check": "pass",
            "atomic": True,
            "idempotent": True,
        }

    def _import_session(
        self,
        connection: sqlite3.Connection,
        item: Mapping[str, Any],
        *,
        source: str,
        verification_level: str,
    ) -> tuple[str, str, str]:
        session_id = str(item["session_id"])
        app_package = str(item["app_package"])
        app_version = str(item["app_version"])
        locale = str(item["locale"])
        app_key = _app_key(app_package, app_version, locale)
        signature = _version_signature(app_package, app_version, locale)
        now = _utc_now()
        destination_correct = bool(item["destination_correct"])
        destination_confirmed_at = (
            str(item.get("destination_confirmed_at") or now) if destination_correct else ""
        )
        connection.execute(
            """
            INSERT INTO app_version_signatures (
              version_signature, app_key, app_package, app_version, locale,
              first_screen_fingerprint, first_seen_at, last_seen_at,
              valid_route_count, invalid_route_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
            ON CONFLICT(version_signature) DO UPDATE SET
              app_key = excluded.app_key,
              app_package = excluded.app_package,
              app_version = excluded.app_version,
              locale = excluded.locale,
              last_seen_at = excluded.last_seen_at,
              first_screen_fingerprint = CASE
                WHEN app_version_signatures.first_screen_fingerprint = ''
                THEN excluded.first_screen_fingerprint
                ELSE app_version_signatures.first_screen_fingerprint
              END
            """,
            (
                signature,
                app_key,
                app_package,
                app_version,
                locale,
                str(item["start_screen_fingerprint"]),
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO navigation_sessions (
              session_id, app_key, version_signature, goal_key, target_function,
              measurement_source, status, start_screen_fingerprint,
              destination_screen_fingerprint, route_id, route_reused,
              destination_correct, safe_stop, unsafe_click_count, wrong_click_count,
              click_count, scroll_count, back_count, revisit_count, recovery_count,
              failure_type, verification_level, started_at, destination_confirmed_at,
              time_to_destination_ms, controllable_time_ms, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              app_key = excluded.app_key,
              version_signature = excluded.version_signature,
              goal_key = excluded.goal_key,
              target_function = excluded.target_function,
              measurement_source = excluded.measurement_source,
              status = excluded.status,
              start_screen_fingerprint = excluded.start_screen_fingerprint,
              destination_screen_fingerprint = excluded.destination_screen_fingerprint,
              route_id = excluded.route_id,
              route_reused = excluded.route_reused,
              destination_correct = excluded.destination_correct,
              safe_stop = excluded.safe_stop,
              unsafe_click_count = excluded.unsafe_click_count,
              wrong_click_count = excluded.wrong_click_count,
              click_count = excluded.click_count,
              scroll_count = excluded.scroll_count,
              back_count = excluded.back_count,
              revisit_count = excluded.revisit_count,
              recovery_count = excluded.recovery_count,
              failure_type = excluded.failure_type,
              verification_level = excluded.verification_level,
              started_at = excluded.started_at,
              destination_confirmed_at = excluded.destination_confirmed_at,
              time_to_destination_ms = excluded.time_to_destination_ms,
              controllable_time_ms = NULL,
              updated_at = excluded.updated_at
            """,
            (
                session_id,
                app_key,
                signature,
                str(item["goal_key"]),
                str(item["target_function"]),
                source,
                "completed" if destination_correct else "failed",
                str(item["start_screen_fingerprint"]),
                str(item["destination_screen_fingerprint"]),
                str(item.get("route_id", "")),
                int(bool(item.get("route_reused", False))),
                int(destination_correct),
                int(bool(item["safe_stop"])),
                int(item.get("unsafe_click_count", 0)),
                int(item.get("wrong_click_count", 0)),
                int(item.get("click_count", 0)),
                int(item.get("scroll_count", 0)),
                int(item.get("back_count", 0)),
                int(item.get("revisit_count", 0)),
                int(item.get("recovery_count", 0)),
                str(item.get("failure_type", "")),
                verification_level,
                str(item.get("started_at") or now),
                destination_confirmed_at,
                float(item["time_to_destination_ms"]),
                now,
                now,
            ),
        )
        # Re-importing the same immutable session replaces, rather than appends,
        # its stage set. This also removes obsolete trailing stages.
        connection.execute(
            "DELETE FROM navigation_stage_timings WHERE session_id = ?",
            (session_id,),
        )
        for ordinal, stage in enumerate(item.get("stages", [])):
            connection.execute(
                """
                INSERT INTO navigation_stage_timings (
                  session_id, ordinal, screen_fingerprint, decision_mode, phase,
                  automation_action, selected_element_key, route_id, measurement_source, server_total_ms,
                  model_decision_ms, db_lookup_ms, screen_analysis_ms,
                  screen_capture_ms, action_execution_ms, ui_settle_ms,
                  external_wait_ms, stage_total_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    ordinal,
                    str(stage.get("screen_fingerprint", "")),
                    str(stage.get("decision_mode", "unknown")),
                    str(stage.get("phase", "unknown")),
                    str(stage.get("automation_action", "none")),
                    str(stage.get("selected_element_key", "")),
                    str(item.get("route_id", "")),
                    source,
                    float(stage.get("server_total_ms", 0.0)),
                    float(stage.get("model_decision_ms", 0.0)),
                    float(stage.get("db_lookup_ms", 0.0)),
                    float(stage.get("screen_analysis_ms", 0.0)),
                    float(stage.get("screen_capture_ms", 0.0)),
                    float(stage.get("action_execution_ms", 0.0)),
                    float(stage.get("ui_settle_ms", 0.0)),
                    float(stage.get("external_wait_ms", 0.0)),
                    float(stage.get("stage_total_ms", 0.0)),
                    now,
                ),
            )
        controllable_ms = item.get("controllable_time_ms")
        if controllable_ms is None:
            controllable_ms = connection.execute(
                """
                SELECT COALESCE(SUM(stage_total_ms - external_wait_ms), 0)
                FROM navigation_stage_timings WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()[0]
            if float(controllable_ms or 0.0) <= 0.0:
                controllable_ms = item["time_to_destination_ms"]
        connection.execute(
            "UPDATE navigation_sessions SET controllable_time_ms = ? WHERE session_id = ?",
            (float(controllable_ms), session_id),
        )
        return app_key, str(item["target_function"]), str(item["start_screen_fingerprint"])

    def _finish_session(
        self,
        connection: sqlite3.Connection,
        *,
        session_id: str,
        route_id: str,
        destination_screen_fingerprint: str,
        destination_correct: bool,
        safe_stop: bool,
        failure_type: str,
        client_elapsed_ms: float | None,
        now: str,
    ) -> float:
        row = connection.execute(
            "SELECT * FROM navigation_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return 0.0
        if row["status"] == "completed" and row["time_to_destination_ms"] is not None:
            return float(row["time_to_destination_ms"])
        stage_total = float(
            connection.execute(
                "SELECT COALESCE(SUM(stage_total_ms), 0) FROM navigation_stage_timings WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        )
        controllable_total = float(
            connection.execute(
                """
                SELECT COALESCE(SUM(stage_total_ms - external_wait_ms), 0)
                FROM navigation_stage_timings WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()[0]
        )
        time_to_destination_ms = client_elapsed_ms if client_elapsed_ms is not None else stage_total
        status = "completed" if destination_correct else "failed"
        connection.execute(
            """
            UPDATE navigation_sessions SET status = ?, destination_screen_fingerprint = ?,
              route_id = CASE WHEN ? <> '' THEN ? ELSE route_id END,
              destination_correct = ?, safe_stop = ?, failure_type = ?,
              destination_confirmed_at = ?, time_to_destination_ms = ?, updated_at = ?
              , controllable_time_ms = ?
            WHERE session_id = ?
            """,
            (
                status,
                destination_screen_fingerprint,
                route_id,
                route_id,
                int(destination_correct),
                int(safe_stop),
                failure_type,
                now if destination_correct else "",
                time_to_destination_ms,
                now,
                controllable_total,
                session_id,
            ),
        )
        self._refresh_performance_from_sessions(
            connection,
            app_key=str(row["app_key"]),
            target_function=str(row["target_function"]),
            start_screen_fingerprint=str(row["start_screen_fingerprint"]),
        )
        return time_to_destination_ms

    def _refresh_performance_from_sessions(
        self,
        connection: sqlite3.Connection,
        *,
        app_key: str,
        target_function: str,
        start_screen_fingerprint: str,
    ) -> None:
        route_rows = connection.execute(
            """
            SELECT route_id FROM navigation_sessions
            WHERE app_key = ? AND target_function = ? AND start_screen_fingerprint = ? AND route_id <> ''
            UNION
            SELECT route_id FROM route_performance
            WHERE app_key = ? AND target_function = ? AND start_screen_fingerprint = ?
            """,
            (
                app_key,
                target_function,
                start_screen_fingerprint,
                app_key,
                target_function,
                start_screen_fingerprint,
            ),
        ).fetchall()
        for route_row in route_rows:
            route_id = str(route_row["route_id"])
            all_sessions = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM navigation_sessions
                    WHERE route_id = ? AND status IN ('completed', 'failed')
                    """,
                    (route_id,),
                ).fetchall()
            ]
            timing_sessions = [
                row
                for row in all_sessions
                if row.get("time_to_destination_ms") is not None
            ]
            trusted_sessions = [
                row
                for row in all_sessions
                if str(row.get("verification_level", "runtime_inferred"))
                in TRUSTED_VERIFICATION_LEVELS
            ]
            real_gold_sessions = [
                row for row in timing_sessions if row["measurement_source"] == "real_device_gold"
            ]
            real_sessions = [
                row for row in timing_sessions if row["measurement_source"] == "real_device"
            ]
            performance_source = (
                "real_device_gold"
                if real_gold_sessions
                else "real_device"
                if real_sessions
                else "synthetic"
                if timing_sessions
                and all(row["measurement_source"] == "synthetic" for row in timing_sessions)
                else "server_runtime"
            )
            timing_metrics = _session_metrics(timing_sessions)
            trusted_metrics = _session_metrics(trusted_sessions)
            success_count = sum(
                1
                for row in trusted_sessions
                if bool(row["destination_correct"])
                and bool(row["safe_stop"])
                and int(row["unsafe_click_count"]) == 0
                and int(row["wrong_click_count"]) == 0
            )
            failure_count = len(trusted_sessions) - success_count
            trusted_sample_count = len(trusted_sessions)
            timing_sample_count = len(timing_sessions)
            under_sampled = int(trusted_sample_count < self.minimum_samples)
            unsafe_click_count = sum(int(row["unsafe_click_count"]) for row in trusted_sessions)
            wrong_click_count = sum(int(row["wrong_click_count"]) for row in trusted_sessions)
            eligible = int(
                not under_sampled
                and failure_count == 0
                and success_count > 0
                and unsafe_click_count == 0
                and wrong_click_count == 0
            )
            last_success = max(
                (
                    str(row["destination_confirmed_at"])
                    for row in trusted_sessions
                    if row["destination_correct"]
                ),
                default="",
            )
            connection.execute(
                """
                INSERT INTO route_performance (
                  route_id, app_key, target_function, version_signature, measurement_source,
                  start_screen_fingerprint, sample_count, timing_sample_count,
                  trusted_sample_count, success_count, failure_count,
                  destination_accuracy, safe_stop_rate, unsafe_click_count, wrong_click_count,
                  p50_time_to_destination_ms, p90_time_to_destination_ms,
                  p50_controllable_time_ms, p90_controllable_time_ms,
                  mean_click_count, mean_scroll_count, mean_back_count,
                  last_success_at, eligible, under_sampled, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_id) DO UPDATE SET
                  measurement_source = excluded.measurement_source,
                  sample_count = excluded.sample_count,
                  timing_sample_count = excluded.timing_sample_count,
                  trusted_sample_count = excluded.trusted_sample_count,
                  success_count = excluded.success_count,
                  failure_count = excluded.failure_count,
                  destination_accuracy = excluded.destination_accuracy,
                  safe_stop_rate = excluded.safe_stop_rate,
                  unsafe_click_count = excluded.unsafe_click_count,
                  wrong_click_count = excluded.wrong_click_count,
                  p50_time_to_destination_ms = excluded.p50_time_to_destination_ms,
                  p90_time_to_destination_ms = excluded.p90_time_to_destination_ms,
                  p50_controllable_time_ms = excluded.p50_controllable_time_ms,
                  p90_controllable_time_ms = excluded.p90_controllable_time_ms,
                  mean_click_count = excluded.mean_click_count,
                  mean_scroll_count = excluded.mean_scroll_count,
                  mean_back_count = excluded.mean_back_count,
                  last_success_at = excluded.last_success_at,
                  eligible = excluded.eligible,
                  under_sampled = excluded.under_sampled,
                  updated_at = excluded.updated_at
                """,
                (
                    route_id,
                    app_key,
                    target_function,
                    str(all_sessions[-1]["version_signature"]) if all_sessions else "",
                    performance_source,
                    start_screen_fingerprint,
                    trusted_sample_count,
                    timing_sample_count,
                    trusted_sample_count,
                    success_count,
                    failure_count,
                    float(trusted_metrics["destination_accuracy"]),
                    float(trusted_metrics["safe_stop_rate"]),
                    unsafe_click_count,
                    wrong_click_count,
                    float(timing_metrics["time_to_destination_p50_ms"]),
                    float(timing_metrics["time_to_destination_p90_ms"]),
                    float(timing_metrics["controllable_time_p50_ms"]),
                    float(timing_metrics["controllable_time_p90_ms"]),
                    float(timing_metrics["mean_clicks_per_session"]),
                    float(timing_metrics["mean_scrolls_per_session"]),
                    float(timing_metrics["mean_backs_per_session"]),
                    last_success,
                    eligible,
                    under_sampled,
                    _utc_now(),
                ),
            )
            self._sync_route_performance_counters(connection, route_id=route_id)
        self._recompute_rankings(
            connection,
            app_key=app_key,
            target_function=target_function,
            start_screen_fingerprint=start_screen_fingerprint,
        )
        self._refresh_edge_performance(connection, app_key=app_key, target_function=target_function)
        for signature_row in connection.execute(
            "SELECT version_signature FROM app_version_signatures WHERE app_key = ?",
            (app_key,),
        ).fetchall():
            signature = str(signature_row["version_signature"])
            counts = connection.execute(
                """
                SELECT
                  SUM(CASE WHEN eligible = 1 THEN 1 ELSE 0 END) AS valid_count,
                  SUM(CASE WHEN eligible = 0 THEN 1 ELSE 0 END) AS invalid_count
                FROM route_performance WHERE version_signature = ?
                """,
                (signature,),
            ).fetchone()
            connection.execute(
                """
                UPDATE app_version_signatures SET valid_route_count = ?, invalid_route_count = ?
                WHERE version_signature = ?
                """,
                (
                    int(counts["valid_count"] or 0),
                    int(counts["invalid_count"] or 0),
                    signature,
                ),
            )

    def _sync_route_performance_counters(
        self,
        connection: sqlite3.Connection,
        *,
        route_id: str,
    ) -> None:
        """Mirror aggregate counts without making an implicit lifecycle decision.

        Gold validation establishes performance truth and route eligibility.  It
        deliberately does not approve or reject a discovered route: lifecycle
        review is a separate, explicit graph action.  This keeps every newly
        learned route shadow/provisional even when a validated session is clean
        or contains an action outside the saved route that was marked wrong.
        """
        if not _table_exists(connection, "universal_routes"):
            return
        performance = connection.execute(
            "SELECT * FROM route_performance WHERE route_id = ?",
            (route_id,),
        ).fetchone()
        if performance is None:
            return
        connection.execute(
            """
            UPDATE universal_routes SET success_count = ?, failure_count = ?, last_seen_at = ?
            WHERE route_id = ?
            """,
            (
                int(performance["success_count"]),
                int(performance["failure_count"]),
                _utc_now(),
                route_id,
            ),
        )

    def _recompute_rankings(
        self,
        connection: sqlite3.Connection,
        *,
        app_key: str,
        target_function: str,
        start_screen_fingerprint: str,
    ) -> None:
        rows = connection.execute(
            """
            SELECT * FROM route_performance
            WHERE app_key = ? AND target_function = ? AND start_screen_fingerprint = ?
            ORDER BY eligible DESC, destination_accuracy DESC, safe_stop_rate DESC,
              CASE WHEN sample_count >= ? THEN 1 ELSE 0 END DESC,
              CASE WHEN sample_count = 0 THEN 1.0 ELSE CAST(success_count AS REAL) / sample_count END DESC,
              p90_controllable_time_ms ASC, p50_controllable_time_ms ASC,
              p90_time_to_destination_ms ASC, p50_time_to_destination_ms ASC,
              mean_click_count ASC, mean_scroll_count ASC, mean_back_count ASC,
              last_success_at DESC, route_id
            """,
            (app_key, target_function, start_screen_fingerprint, self.minimum_samples),
        ).fetchall()
        existing_counts = {
            str(row["route_id"]): (int(row["selection_count"]), str(row["last_selected_at"]))
            for row in connection.execute(
                """
                SELECT route_id, selection_count, last_selected_at FROM route_rankings
                WHERE app_key = ? AND target_function = ? AND start_screen_fingerprint = ?
                """,
                (app_key, target_function, start_screen_fingerprint),
            ).fetchall()
        }
        connection.execute(
            """
            DELETE FROM route_rankings
            WHERE app_key = ? AND target_function = ? AND start_screen_fingerprint = ?
            """,
            (app_key, target_function, start_screen_fingerprint),
        )
        for rank, row in enumerate(rows, start=1):
            route_id = str(row["route_id"])
            selection_count, last_selected_at = existing_counts.get(route_id, (0, ""))
            confidence = min(
                1.0,
                float(row["destination_accuracy"]) * 0.45
                + float(row["safe_stop_rate"]) * 0.35
                + min(1.0, int(row["success_count"]) / self.minimum_samples) * 0.20,
            )
            connection.execute(
                """
                INSERT INTO route_rankings (
                  app_key, target_function, start_screen_fingerprint, route_id,
                  rank_order, eligible, under_sampled, confidence,
                  p50_time_to_destination_ms, p90_time_to_destination_ms,
                  p50_controllable_time_ms, p90_controllable_time_ms,
                  selection_count, last_selected_at, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    app_key,
                    target_function,
                    start_screen_fingerprint,
                    route_id,
                    rank,
                    int(row["eligible"]),
                    int(row["under_sampled"]),
                    confidence,
                    float(row["p50_time_to_destination_ms"]),
                    float(row["p90_time_to_destination_ms"]),
                    float(row["p50_controllable_time_ms"]),
                    float(row["p90_controllable_time_ms"]),
                    selection_count,
                    last_selected_at,
                    _utc_now(),
                ),
            )

    def _refresh_edge_performance(
        self,
        connection: sqlite3.Connection,
        *,
        app_key: str,
        target_function: str,
    ) -> None:
        if not _table_exists(connection, "universal_routes"):
            return
        routes = connection.execute(
            "SELECT route_id, steps_json FROM universal_routes WHERE app_key = ? AND target_function = ?",
            (app_key, target_function),
        ).fetchall()
        for route in routes:
            route_id = str(route["route_id"])
            performance = connection.execute(
                "SELECT * FROM route_performance WHERE route_id = ?",
                (route_id,),
            ).fetchone()
            if performance is None:
                continue
            try:
                steps = json.loads(route["steps_json"] or "[]")
            except json.JSONDecodeError:
                steps = []
            step_count = max(1, len(steps))
            for step in steps:
                if not isinstance(step, Mapping) or bool(step.get("terminal")):
                    continue
                from_screen = str(step.get("from_screen_fingerprint", ""))
                element_key = str(step.get("element_key", ""))
                to_screen = str(step.get("expected_to_screen_fingerprint", ""))
                if not from_screen or not element_key:
                    continue
                edge_key = hashlib.sha256(
                    f"{app_key}|{target_function}|{from_screen}|{element_key}|{to_screen}".encode("utf-8")
                ).hexdigest()[:24]
                connection.execute(
                    """
                    INSERT INTO graph_edge_performance (
                      edge_key, app_key, target_function, from_screen_fingerprint,
                      element_key, to_screen_fingerprint, sample_count, success_count,
                      failure_count, destination_accuracy, safe_stop_rate,
                      mean_transition_ms, estimated_p50_ms, estimated_p90_ms,
                      last_success_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(edge_key) DO UPDATE SET
                      sample_count = excluded.sample_count,
                      success_count = excluded.success_count,
                      failure_count = excluded.failure_count,
                      destination_accuracy = excluded.destination_accuracy,
                      safe_stop_rate = excluded.safe_stop_rate,
                      mean_transition_ms = excluded.mean_transition_ms,
                      estimated_p50_ms = excluded.estimated_p50_ms,
                      estimated_p90_ms = excluded.estimated_p90_ms,
                      last_success_at = excluded.last_success_at,
                      updated_at = excluded.updated_at
                    """,
                    (
                        edge_key,
                        app_key,
                        target_function,
                        from_screen,
                        element_key,
                        to_screen,
                        int(performance["sample_count"]),
                        int(performance["success_count"]),
                        int(performance["failure_count"]),
                        float(performance["destination_accuracy"]),
                        float(performance["safe_stop_rate"]),
                        (
                            float(performance["p50_time_to_destination_ms"])
                            + float(performance["p90_time_to_destination_ms"])
                        ) / (2 * step_count),
                        float(performance["p50_time_to_destination_ms"]) / step_count,
                        float(performance["p90_time_to_destination_ms"]) / step_count,
                        str(performance["last_success_at"]),
                        _utc_now(),
                    ),
                )

    @staticmethod
    def _route_rank(connection: sqlite3.Connection, route_id: str) -> int | None:
        if not route_id:
            return None
        row = connection.execute(
            "SELECT MIN(rank_order) AS rank_order FROM route_rankings WHERE route_id = ?",
            (route_id,),
        ).fetchone()
        if row is None or row["rank_order"] is None:
            return None
        return int(row["rank_order"])

    def _ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_version_signatures (
                  version_signature TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  app_package TEXT NOT NULL,
                  app_version TEXT NOT NULL,
                  locale TEXT NOT NULL,
                  first_screen_fingerprint TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  valid_route_count INTEGER NOT NULL,
                  invalid_route_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS navigation_sessions (
                  session_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  version_signature TEXT NOT NULL,
                  goal_key TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  measurement_source TEXT NOT NULL,
                  status TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  destination_screen_fingerprint TEXT NOT NULL,
                  route_id TEXT NOT NULL,
                  route_reused INTEGER NOT NULL,
                  destination_correct INTEGER NOT NULL,
                  safe_stop INTEGER NOT NULL,
                  unsafe_click_count INTEGER NOT NULL,
                  wrong_click_count INTEGER NOT NULL,
                  wrong_guidance_count INTEGER NOT NULL DEFAULT 0,
                  click_count INTEGER NOT NULL,
                  scroll_count INTEGER NOT NULL,
                  back_count INTEGER NOT NULL,
                  revisit_count INTEGER NOT NULL,
                  recovery_count INTEGER NOT NULL,
                  failure_type TEXT NOT NULL,
                  verification_level TEXT NOT NULL DEFAULT 'runtime_inferred',
                  started_at TEXT NOT NULL,
                  destination_confirmed_at TEXT NOT NULL,
                  time_to_destination_ms REAL,
                  controllable_time_ms REAL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS navigation_stage_timings (
                  session_id TEXT NOT NULL,
                  ordinal INTEGER NOT NULL,
                  screen_fingerprint TEXT NOT NULL,
                  decision_mode TEXT NOT NULL,
                  phase TEXT NOT NULL,
                  automation_action TEXT NOT NULL,
                  selected_element_key TEXT NOT NULL,
                  route_id TEXT NOT NULL,
                  measurement_source TEXT NOT NULL,
                  server_total_ms REAL NOT NULL,
                  model_decision_ms REAL NOT NULL,
                  db_lookup_ms REAL NOT NULL,
                  screen_analysis_ms REAL NOT NULL,
                  screen_capture_ms REAL NOT NULL,
                  action_execution_ms REAL NOT NULL,
                  ui_settle_ms REAL NOT NULL,
                  external_wait_ms REAL NOT NULL,
                  stage_total_ms REAL NOT NULL,
                  executed_transition_outcome TEXT NOT NULL DEFAULT '',
                  wrong_guidance_delta INTEGER NOT NULL DEFAULT 0,
                  wrong_click_delta INTEGER NOT NULL DEFAULT 0,
                  failure_reason TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  PRIMARY KEY(session_id, ordinal)
                );

                CREATE TABLE IF NOT EXISTS navigation_instruction_outcomes (
                  recommendation_id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  outcome TEXT NOT NULL,
                  wrong_guidance INTEGER NOT NULL,
                  wrong_click INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(session_id) REFERENCES navigation_sessions(session_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS graph_edge_performance (
                  edge_key TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  from_screen_fingerprint TEXT NOT NULL,
                  element_key TEXT NOT NULL,
                  to_screen_fingerprint TEXT NOT NULL,
                  sample_count INTEGER NOT NULL,
                  success_count INTEGER NOT NULL,
                  failure_count INTEGER NOT NULL,
                  destination_accuracy REAL NOT NULL,
                  safe_stop_rate REAL NOT NULL,
                  mean_transition_ms REAL NOT NULL,
                  estimated_p50_ms REAL NOT NULL,
                  estimated_p90_ms REAL NOT NULL,
                  last_success_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS route_performance (
                  route_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  version_signature TEXT NOT NULL,
                  measurement_source TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  sample_count INTEGER NOT NULL,
                  timing_sample_count INTEGER NOT NULL,
                  trusted_sample_count INTEGER NOT NULL,
                  success_count INTEGER NOT NULL,
                  failure_count INTEGER NOT NULL,
                  destination_accuracy REAL NOT NULL,
                  safe_stop_rate REAL NOT NULL,
                  unsafe_click_count INTEGER NOT NULL,
                  wrong_click_count INTEGER NOT NULL,
                  p50_time_to_destination_ms REAL NOT NULL,
                  p90_time_to_destination_ms REAL NOT NULL,
                  p50_controllable_time_ms REAL NOT NULL,
                  p90_controllable_time_ms REAL NOT NULL,
                  mean_click_count REAL NOT NULL,
                  mean_scroll_count REAL NOT NULL,
                  mean_back_count REAL NOT NULL,
                  last_success_at TEXT NOT NULL,
                  eligible INTEGER NOT NULL,
                  under_sampled INTEGER NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS route_rankings (
                  app_key TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  route_id TEXT NOT NULL,
                  rank_order INTEGER NOT NULL,
                  eligible INTEGER NOT NULL,
                  under_sampled INTEGER NOT NULL,
                  confidence REAL NOT NULL,
                  p50_time_to_destination_ms REAL NOT NULL,
                  p90_time_to_destination_ms REAL NOT NULL,
                  p50_controllable_time_ms REAL NOT NULL,
                  p90_controllable_time_ms REAL NOT NULL,
                  selection_count INTEGER NOT NULL,
                  last_selected_at TEXT NOT NULL,
                  generated_at TEXT NOT NULL,
                  PRIMARY KEY(app_key, target_function, start_screen_fingerprint, route_id)
                );

                CREATE INDEX IF NOT EXISTS idx_navigation_sessions_metrics
                  ON navigation_sessions(measurement_source, status, target_function);
                CREATE INDEX IF NOT EXISTS idx_navigation_stage_session
                  ON navigation_stage_timings(session_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_navigation_instruction_outcome_session
                  ON navigation_instruction_outcomes(session_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_route_performance_lookup
                  ON route_performance(app_key, target_function, eligible, p90_time_to_destination_ms);
                CREATE INDEX IF NOT EXISTS idx_route_rankings_lookup
                  ON route_rankings(app_key, target_function, start_screen_fingerprint, rank_order);
                CREATE INDEX IF NOT EXISTS idx_edge_performance_lookup
                  ON graph_edge_performance(app_key, target_function, from_screen_fingerprint);
                """
            )
            self._ensure_column(
                connection,
                "navigation_sessions",
                "verification_level",
                "TEXT NOT NULL DEFAULT 'runtime_inferred'",
            )
            self._ensure_column(
                connection,
                "navigation_sessions",
                "controllable_time_ms",
                "REAL",
            )
            self._ensure_column(
                connection,
                "navigation_sessions",
                "wrong_guidance_count",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "navigation_stage_timings",
                "selected_element_key",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                "navigation_stage_timings",
                "executed_transition_outcome",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                "navigation_stage_timings",
                "wrong_guidance_delta",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "navigation_stage_timings",
                "wrong_click_delta",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "navigation_stage_timings",
                "failure_reason",
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                "graph_edge_performance",
                "mean_transition_ms",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "route_performance",
                "measurement_source",
                "TEXT NOT NULL DEFAULT 'server_runtime'",
            )
            self._ensure_column(
                connection,
                "route_performance",
                "timing_sample_count",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "route_performance",
                "trusted_sample_count",
                "INTEGER NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "route_performance",
                "p50_controllable_time_ms",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "route_performance",
                "p90_controllable_time_ms",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "route_rankings",
                "p50_controllable_time_ms",
                "REAL NOT NULL DEFAULT 0",
            )
            self._ensure_column(
                connection,
                "route_rankings",
                "p90_controllable_time_ms",
                "REAL NOT NULL DEFAULT 0",
            )
            connection.commit()

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        declaration: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}"
            )

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            yield connection
        finally:
            connection.close()


def plan_real_device_import(payload: Mapping[str, Any]) -> RealDeviceImportPlan:
    """Validate every record before any database write is attempted."""
    validate_privacy_safe_payload(payload)
    schema_version = payload.get("schema_version", 1)
    if isinstance(schema_version, bool) or schema_version != 1:
        raise ValueError("Unsupported navigation performance schema_version")
    source = str(payload.get("measurement_source", "real_device"))
    if source not in IMPORT_MEASUREMENT_SOURCES:
        raise ValueError("Imported device logs must use real_device or real_device_gold")
    sessions = payload.get("sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list")
    normalized_sessions: list[dict[str, Any]] = []
    seen_session_ids: set[str] = set()
    for index, raw_item in enumerate(sessions):
        path = f"sessions[{index}]"
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"{path} must be an object")
        required = (
            "session_id",
            "app_package",
            "app_version",
            "locale",
            "goal_key",
            "target_function",
            "start_screen_fingerprint",
            "destination_screen_fingerprint",
            "time_to_destination_ms",
            "destination_correct",
            "safe_stop",
        )
        missing = [name for name in required if name not in raw_item]
        if missing:
            raise ValueError(f"{path} missing device log fields: " + ", ".join(missing))
        session_id = _validated_text(raw_item["session_id"], f"{path}.session_id", 120)
        if session_id in seen_session_ids:
            raise ValueError(f"duplicate session_id in import: {session_id}")
        seen_session_ids.add(session_id)
        start_screen = _validated_fingerprint(
            raw_item["start_screen_fingerprint"], f"{path}.start_screen_fingerprint"
        )
        destination_screen = _validated_fingerprint(
            raw_item["destination_screen_fingerprint"],
            f"{path}.destination_screen_fingerprint",
        )
        stages_value = raw_item.get("stages", [])
        if not isinstance(stages_value, list):
            raise ValueError(f"{path}.stages must be a list")
        stages: list[dict[str, Any]] = []
        for stage_index, raw_stage in enumerate(stages_value):
            stage_path = f"{path}.stages[{stage_index}]"
            if not isinstance(raw_stage, Mapping):
                raise ValueError(f"{stage_path} must be an object")
            stage_screen = str(raw_stage.get("screen_fingerprint", ""))
            if stage_screen:
                stage_screen = _validated_fingerprint(stage_screen, f"{stage_path}.screen_fingerprint")
            stages.append(
                {
                    "screen_fingerprint": stage_screen,
                    "decision_mode": _validated_optional_text(
                        raw_stage.get("decision_mode", "unknown"),
                        f"{stage_path}.decision_mode",
                        80,
                    ),
                    "phase": _validated_optional_text(
                        raw_stage.get("phase", "unknown"), f"{stage_path}.phase", 80
                    ),
                    "automation_action": _validated_optional_text(
                        raw_stage.get("automation_action", "none"),
                        f"{stage_path}.automation_action",
                        80,
                    ),
                    "selected_element_key": _validated_optional_text(
                        raw_stage.get("selected_element_key", ""),
                        f"{stage_path}.selected_element_key",
                        500,
                    ),
                    **{
                        name: _validated_duration(
                            raw_stage.get(name, 0.0), f"{stage_path}.{name}", 300_000.0
                        )
                        for name in (
                            "server_total_ms",
                            "model_decision_ms",
                            "db_lookup_ms",
                            "screen_analysis_ms",
                            "screen_capture_ms",
                            "action_execution_ms",
                            "ui_settle_ms",
                            "external_wait_ms",
                            "stage_total_ms",
                        )
                    },
                }
            )
        destination_correct = _validated_bool(
            raw_item["destination_correct"], f"{path}.destination_correct"
        )
        safe_stop = _validated_bool(raw_item["safe_stop"], f"{path}.safe_stop")
        normalized: dict[str, Any] = {
            "session_id": session_id,
            "app_package": _validated_text(raw_item["app_package"], f"{path}.app_package", 240),
            "app_version": _validated_optional_text(
                raw_item["app_version"], f"{path}.app_version", 120
            ),
            "locale": _validated_text(raw_item["locale"], f"{path}.locale", 40),
            "goal_key": _validated_text(raw_item["goal_key"], f"{path}.goal_key", 128),
            "target_function": _validated_text(
                raw_item["target_function"], f"{path}.target_function", 240
            ),
            "start_screen_fingerprint": start_screen,
            "destination_screen_fingerprint": destination_screen,
            "route_id": _validated_optional_text(raw_item.get("route_id", ""), f"{path}.route_id", 120),
            "route_reused": _validated_bool(
                raw_item.get("route_reused", False), f"{path}.route_reused"
            ),
            "destination_correct": destination_correct,
            "safe_stop": safe_stop,
            "unsafe_click_count": _validated_count(
                raw_item.get("unsafe_click_count", 0), f"{path}.unsafe_click_count"
            ),
            "wrong_click_count": _validated_count(
                raw_item.get("wrong_click_count", 0), f"{path}.wrong_click_count"
            ),
            "click_count": _validated_count(raw_item.get("click_count", 0), f"{path}.click_count"),
            "scroll_count": _validated_count(raw_item.get("scroll_count", 0), f"{path}.scroll_count"),
            "back_count": _validated_count(raw_item.get("back_count", 0), f"{path}.back_count"),
            "revisit_count": _validated_count(
                raw_item.get("revisit_count", 0), f"{path}.revisit_count"
            ),
            "recovery_count": _validated_count(
                raw_item.get("recovery_count", 0), f"{path}.recovery_count"
            ),
            "failure_type": _validated_optional_text(
                raw_item.get("failure_type", ""), f"{path}.failure_type", 160
            ),
            "started_at": _validated_optional_text(
                raw_item.get("started_at", ""), f"{path}.started_at", 80
            ),
            "destination_confirmed_at": _validated_optional_text(
                raw_item.get("destination_confirmed_at", ""),
                f"{path}.destination_confirmed_at",
                80,
            ),
            "time_to_destination_ms": _validated_duration(
                raw_item["time_to_destination_ms"],
                f"{path}.time_to_destination_ms",
                3_600_000.0,
                strictly_positive=True,
            ),
            "stages": stages,
        }
        if raw_item.get("controllable_time_ms") is not None:
            normalized["controllable_time_ms"] = _validated_duration(
                raw_item["controllable_time_ms"],
                f"{path}.controllable_time_ms",
                3_600_000.0,
            )
        normalized_sessions.append(normalized)
    return RealDeviceImportPlan(
        measurement_source=source,
        verification_level="human_gold" if source == "real_device_gold" else "runtime_inferred",
        sessions=tuple(normalized_sessions),
    )


def validate_privacy_safe_payload(payload: Mapping[str, Any]) -> None:
    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized_key = str(key).strip().lower()
                if normalized_key in SENSITIVE_KEYS:
                    raise ValueError(f"privacy-sensitive field is forbidden: {path}{key}")
                visit(child, f"{path}{key}.")
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}{index}.")
            return
        if isinstance(value, str):
            if EMAIL_PATTERN.search(value) or PHONE_PATTERN.search(value):
                raise ValueError(f"privacy-sensitive text found at {path.rstrip('.')}")

    visit(payload, "")


def _validated_text(value: Any, path: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{path} exceeds {max_length} characters")
    return normalized


def _validated_optional_text(value: Any, path: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{path} exceeds {max_length} characters")
    return normalized


def _validated_fingerprint(value: Any, path: str) -> str:
    fingerprint = _validated_text(value, path, 19)
    if not SCREEN_FINGERPRINT_PATTERN.fullmatch(fingerprint):
        raise ValueError(f"{path} must match us_<16 lowercase hex characters>")
    return fingerprint


def _validated_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _validated_count(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return value


def _validated_duration(
    value: Any,
    path: str,
    upper_bound: float,
    *,
    strictly_positive: bool = False,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{path} must be a finite duration")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{path} must be a finite duration") from error
    lower_ok = number > 0.0 if strictly_positive else number >= 0.0
    if not math.isfinite(number) or not lower_ok or number > upper_bound:
        comparator = "greater than zero" if strictly_positive else "non-negative"
        raise ValueError(f"{path} must be {comparator} and no greater than {upper_bound}")
    return number


def _session_metrics(rows: Iterable[Mapping[str, Any]]) -> dict[str, object]:
    rows = list(rows)
    times = [float(row["time_to_destination_ms"]) for row in rows if row.get("time_to_destination_ms") is not None]
    controllable_times = [
        float(row["controllable_time_ms"])
        for row in rows
        if row.get("controllable_time_ms") is not None
    ]
    decision_times = [
        float(row.get("model_decision_ms", 0.0))
        for row in rows
        if row.get("model_decision_ms") is not None
    ]
    destination_correct = sum(int(bool(row.get("destination_correct"))) for row in rows)
    safe_stops = sum(int(bool(row.get("safe_stop"))) for row in rows)
    return {
        "session_count": len(rows),
        "destination_accuracy": _ratio(destination_correct, len(rows)),
        "safe_stop_rate": _ratio(safe_stops, len(rows)),
        "unsafe_click_rate": _ratio(sum(int(row.get("unsafe_click_count", 0)) for row in rows), len(rows)),
        "wrong_click_rate": _ratio(sum(int(row.get("wrong_click_count", 0)) for row in rows), len(rows)),
        "time_to_destination_p50_ms": _percentile(times, 0.50),
        "time_to_destination_p90_ms": _percentile(times, 0.90),
        "controllable_time_p50_ms": _percentile(controllable_times, 0.50),
        "controllable_time_p90_ms": _percentile(controllable_times, 0.90),
        "decision_time_p50_ms": _percentile(decision_times, 0.50),
        "decision_time_p90_ms": _percentile(decision_times, 0.90),
        "success_within_10s_rate": _ratio(sum(int(value <= 10_000) for value in times), len(times)),
        "success_within_30s_rate": _ratio(sum(int(value <= 30_000) for value in times), len(times)),
        "success_within_60s_rate": _ratio(sum(int(value <= 60_000) for value in times), len(times)),
        "mean_clicks_per_session": _mean([float(row.get("click_count", 0)) for row in rows]),
        "mean_scrolls_per_session": _mean([float(row.get("scroll_count", 0)) for row in rows]),
        "mean_backs_per_session": _mean([float(row.get("back_count", 0)) for row in rows]),
        "route_reuse_rate": _ratio(sum(int(bool(row.get("route_reused"))) for row in rows), len(rows)),
    }


def _stage_total(measurement: StageMeasurement) -> float:
    # server_total already contains model/DB/screen-analysis subcomponents, so
    # those values are not added a second time.
    return (
        measurement.server_total_ms
        + measurement.screen_capture_ms
        + measurement.action_execution_ms
        + measurement.ui_settle_ms
        + measurement.external_wait_ms
    )


def _duration(value: Any, upper_bound: float = 300_000.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(upper_bound, number))


def _percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    weight = position - lower
    return round(ordered[lower] * (1.0 - weight) + ordered[upper] * weight, 3)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return 0.0 if not values else round(sum(values) / len(values), 3)


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator <= 0 else round(numerator / denominator, 6)


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _app_key(app_package: str, app_version: str, locale: str) -> str:
    return hashlib.sha256(f"{app_package}|{app_version}|{locale.lower()}".encode("utf-8")).hexdigest()[:20]


def _version_signature(app_package: str, app_version: str, locale: str) -> str:
    digest = hashlib.sha256(f"{app_package}|{app_version}|{locale.lower()}".encode("utf-8")).hexdigest()[:20]
    return f"avs_{digest}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
