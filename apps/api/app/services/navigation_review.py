from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ActionJudgment = Literal["correct", "acceptable", "wrong", "unsafe", "cannot_judge"]
ProgressJudgment = Literal["advanced", "unchanged", "regressed", "reached", "unknown"]
SafetyJudgment = Literal["true", "false", "unknown"]
BetterCandidateStatus = Literal["selected", "none", "unknown"]
SuccessJudgment = Literal["correct", "incorrect", "unknown", "not_applicable"]


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json_value(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


class NavigationHumanReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewer: str = Field(default="human", min_length=1, max_length=80)
    action_judgment: ActionJudgment
    progress_judgment: ProgressJudgment
    safety_boundary_judgment: SafetyJudgment
    better_candidate_status: BetterCandidateStatus
    better_candidate_id: str | None = Field(default=None, max_length=200)
    system_success_judgment: SuccessJudgment
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_better_candidate(self) -> "NavigationHumanReviewRequest":
        if self.better_candidate_status == "selected" and not self.better_candidate_id:
            raise ValueError("better_candidate_id is required when a candidate is selected")
        if self.better_candidate_status != "selected" and self.better_candidate_id is not None:
            raise ValueError("better_candidate_id is only allowed for a selected candidate")
        return self


REVIEW_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS navigation_review_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS navigation_human_reviews (
    review_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    action_judgment TEXT NOT NULL CHECK (action_judgment IN (
        'correct', 'acceptable', 'wrong', 'unsafe', 'cannot_judge'
    )),
    progress_judgment TEXT NOT NULL CHECK (progress_judgment IN (
        'advanced', 'unchanged', 'regressed', 'reached', 'unknown'
    )),
    safety_boundary_judgment TEXT NOT NULL CHECK (safety_boundary_judgment IN (
        'true', 'false', 'unknown'
    )),
    better_candidate_status TEXT NOT NULL CHECK (better_candidate_status IN (
        'selected', 'none', 'unknown'
    )),
    better_candidate_id TEXT,
    system_success_judgment TEXT NOT NULL CHECK (system_success_judgment IN (
        'correct', 'incorrect', 'unknown', 'not_applicable'
    )),
    notes TEXT NOT NULL DEFAULT '',
    source_summary_json TEXT NOT NULL CHECK (json_valid(source_summary_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(decision_id, reviewer),
    CHECK (
        (better_candidate_status = 'selected' AND better_candidate_id IS NOT NULL)
        OR (better_candidate_status <> 'selected' AND better_candidate_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS navigation_machine_assessments (
    decision_id TEXT PRIMARY KEY,
    assessor TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    assessment_json TEXT NOT NULL CHECK (json_valid(assessment_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_navigation_reviews_reviewer
    ON navigation_human_reviews(reviewer, updated_at);

INSERT OR REPLACE INTO navigation_review_metadata(key, value) VALUES
    ('schema_version', '1'),
    ('database_kind', 'navigation_human_review'),
    ('source_policy', 'runtime_database_read_only');

PRAGMA user_version = 1;
"""


class NavigationReviewStore:
    """Read navigation evidence without ever opening the Runtime DB for writes."""

    def __init__(self, runtime_db_path: str | Path, review_db_path: str | Path) -> None:
        self.runtime_db_path = Path(runtime_db_path).expanduser().resolve()
        self.review_db_path = Path(review_db_path).expanduser().resolve()
        if self.runtime_db_path == self.review_db_path:
            raise ValueError("the Runtime DB and review DB must be different files")
        if not self.runtime_db_path.is_file():
            raise FileNotFoundError(self.runtime_db_path)
        self.review_db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._review_connect()) as connection:
            connection.executescript(REVIEW_SCHEMA)

    def _runtime_connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self.runtime_db_path.as_uri()}?mode=ro",
            uri=True,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        return connection

    def _review_connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.review_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def status(self, *, reviewer: str = "human") -> dict[str, object]:
        with closing(self._runtime_connect()) as source:
            source_counts = {
                "sessions": int(source.execute("SELECT count(*) FROM navigation_sessions").fetchone()[0]),
                "decisions": int(source.execute("SELECT count(*) FROM navigation_decisions").fetchone()[0]),
                "reached": int(
                    source.execute(
                        "SELECT count(*) FROM navigation_observations WHERE progress_label = 'reached'"
                    ).fetchone()[0]
                ),
                "safety_stops": int(
                    source.execute(
                        "SELECT count(*) FROM navigation_decisions WHERE action_name = 'stop_for_user'"
                    ).fetchone()[0]
                ),
            }
            source_ids = {
                str(row[0]) for row in source.execute("SELECT decision_id FROM navigation_decisions")
            }
        with closing(self._review_connect()) as target:
            reviewed_ids = {
                str(row[0])
                for row in target.execute(
                    "SELECT decision_id FROM navigation_human_reviews WHERE reviewer = ?",
                    (reviewer,),
                )
            }
        reviewed = len(source_ids & reviewed_ids)
        total = source_counts["decisions"]
        return {
            "ready": True,
            "source_read_only": True,
            "source_database": self.runtime_db_path.name,
            "review_database": self.review_db_path.name,
            "reviewer": reviewer,
            "counts": {
                **source_counts,
                "reviewed": reviewed,
                "remaining": max(0, total - reviewed),
            },
        }

    @staticmethod
    def _priority(row: dict[str, Any]) -> tuple[int, str, list[str]]:
        reasons: list[str] = []
        progress = str(row.get("progress_label") or "")
        outcome = str(row.get("outcome_type") or "")
        action = str(row.get("action_name") or "")
        confidence = float(row.get("confidence") or 0.0)

        if progress == "reached" or outcome == "destination_reached":
            return 0, "reached", ["목표 도달 판정"]
        if action == "stop_for_user":
            return 1, "safety", ["사용자에게 넘긴 안전 경계"]
        if int(row.get("high_risk_candidates") or 0) > 0:
            reasons.append("고위험 후보 포함")
        if outcome in {"wrong_destination", "blocked", "external_app", "unknown"}:
            reasons.append("실패 또는 불명확한 결과")
        if row.get("observation_id") is None:
            reasons.append("실제 결과 기록 없음")
        if str(row.get("execution_status") or "") in {
            "executor_error",
            "transport_error",
            "device_disconnected",
        }:
            reasons.append("실행 오류")
        if confidence < 0.6:
            reasons.append("낮은 선택 확신")
        if int(row.get("reflection_on_demand") or 0):
            reasons.append("추가 판단 사용")
        if str(row.get("safety_status") or "") == "replaced_with_safe_action":
            reasons.append("안전 정책이 행동 변경")
        if reasons:
            return 2, "uncertain", reasons
        return 3, "routine", ["일반 행동 표본"]

    def _review_map(self, reviewer: str) -> dict[str, dict[str, Any]]:
        with closing(self._review_connect()) as connection:
            rows = connection.execute(
                """
                SELECT decision_id, action_judgment, progress_judgment,
                       safety_boundary_judgment, system_success_judgment, updated_at
                FROM navigation_human_reviews WHERE reviewer = ?
                """,
                (reviewer,),
            ).fetchall()
        return {str(row["decision_id"]): dict(row) for row in rows}

    def list_queue(
        self,
        *,
        reviewer: str = "human",
        queue: str = "priority",
        review_status: str = "unreviewed",
        query: str = "",
        limit: int = 80,
        offset: int = 0,
    ) -> dict[str, object]:
        allowed_queues = {"priority", "reached", "safety", "uncertain", "all"}
        if queue not in allowed_queues:
            raise ValueError(f"unsupported review queue: {queue}")
        if review_status not in {"unreviewed", "reviewed", "all"}:
            raise ValueError(f"unsupported review status: {review_status}")
        review_map = self._review_map(reviewer)
        with closing(self._runtime_connect()) as connection:
            source_rows = connection.execute(
                """
                SELECT d.decision_id, d.session_id, d.step_ordinal, d.action_name,
                       d.candidate_id, d.confidence, d.score_margin,
                       d.reflection_on_demand, d.safety_status, d.safety_reason,
                       d.plan_stage, d.planner_provider, d.created_at,
                       s.app_package, s.app_version, s.goal_text_redacted,
                       s.goal_id AS session_goal_id, s.status AS session_status,
                       s.terminal_reason AS session_terminal_reason,
                       o.observation_id, o.outcome_type, o.progress_label,
                       o.failure_class, o.state_changed, o.destination_match_after,
                       x.execution_status, x.execution_succeeded,
                       (SELECT count(*)
                        FROM navigation_screen_snapshots ss
                        JOIN navigation_screen_candidates sc ON sc.snapshot_id = ss.snapshot_id
                        WHERE ss.decision_id = d.decision_id AND ss.phase = 'before'
                          AND sc.risk_level IN ('high', 'blocked')) AS high_risk_candidates,
                       (SELECT count(*)
                        FROM navigation_screen_snapshots ss
                        JOIN navigation_screen_candidates sc ON sc.snapshot_id = ss.snapshot_id
                        WHERE ss.decision_id = d.decision_id AND ss.phase = 'before') AS candidate_count
                FROM navigation_decisions d
                JOIN navigation_sessions s ON s.session_id = d.session_id
                LEFT JOIN navigation_observations o ON o.decision_id = d.decision_id
                LEFT JOIN navigation_step_executions x ON x.decision_id = d.decision_id
                ORDER BY d.created_at DESC
                """
            ).fetchall()

        normalized_query = query.strip().casefold()
        items: list[dict[str, Any]] = []
        category_counts = {"reached": 0, "safety": 0, "uncertain": 0, "routine": 0}
        for source_row in source_rows:
            item = dict(source_row)
            priority, category, reasons = self._priority(item)
            category_counts[category] += 1
            review = review_map.get(str(item["decision_id"]))
            is_reviewed = review is not None
            if review_status == "unreviewed" and is_reviewed:
                continue
            if review_status == "reviewed" and not is_reviewed:
                continue
            if queue != "all" and queue != "priority" and category != queue:
                continue
            if normalized_query:
                haystack = " ".join(
                    str(item.get(key) or "")
                    for key in (
                        "app_package",
                        "goal_text_redacted",
                        "session_goal_id",
                        "action_name",
                        "outcome_type",
                    )
                ).casefold()
                if normalized_query not in haystack:
                    continue
            item.update(
                {
                    "priority": priority,
                    "category": category,
                    "priority_reasons": reasons,
                    "reviewed": is_reviewed,
                    "review": review,
                }
            )
            items.append(item)

        items.sort(key=lambda item: (int(item["priority"]), str(item["created_at"])), reverse=False)
        total = len(items)
        page = items[offset : offset + min(max(limit, 1), 200)]
        return {
            "reviewer": reviewer,
            "queue": queue,
            "review_status": review_status,
            "total": total,
            "offset": offset,
            "limit": limit,
            "category_counts": category_counts,
            "items": page,
        }

    @staticmethod
    def _compact_screen(snapshot: sqlite3.Row, candidates: list[sqlite3.Row]) -> dict[str, Any]:
        payload = _json_value(snapshot["screen_payload_json"], {})
        visible_texts: list[str] = []
        compact_nodes: list[dict[str, Any]] = []
        seen_texts: set[str] = set()
        for node in payload.get("nodes", []):
            if not isinstance(node, dict) or node.get("private_input"):
                continue
            text_parts = [str(node.get("text") or "").strip(), str(node.get("content_description") or "").strip()]
            for text in text_parts:
                if text and text not in seen_texts:
                    seen_texts.add(text)
                    visible_texts.append(text[:500])
            if any(text_parts) or node.get("clickable") or node.get("scrollable"):
                compact_nodes.append(
                    {
                        key: node.get(key)
                        for key in (
                            "node_id",
                            "parent_id",
                            "role",
                            "text",
                            "content_description",
                            "clickable",
                            "scrollable",
                            "enabled",
                            "selected",
                            "position_bucket",
                            "bounds_normalized",
                        )
                    }
                )
        candidate_items: list[dict[str, Any]] = []
        for row in candidates:
            item = dict(row)
            item["observed_payload"] = _json_value(item.pop("observed_payload_json"), {})
            candidate_items.append(item)
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "phase": snapshot["phase"],
            "screen_fingerprint": snapshot["screen_fingerprint"],
            "window_title": snapshot["window_title_redacted"],
            "activity_name": snapshot["activity_name_redacted"],
            "navigation_depth": snapshot["navigation_depth"],
            "candidate_set_status": snapshot["candidate_set_status"],
            "screen_width_px": snapshot["screen_width_px"],
            "screen_height_px": snapshot["screen_height_px"],
            "nodes_total": snapshot["nodes_total"],
            "nodes_captured": snapshot["nodes_captured"],
            "nodes_truncated": bool(snapshot["nodes_truncated"]),
            "candidates_total": snapshot["candidates_total"],
            "candidates_captured": snapshot["candidates_captured"],
            "candidates_truncated": bool(snapshot["candidates_truncated"]),
            "missing_parts": _json_value(snapshot["missing_parts_json"], []),
            "captured_at": snapshot["captured_at"],
            "visible_texts": visible_texts[:120],
            "nodes": compact_nodes[:160],
            "candidates": candidate_items,
        }

    @staticmethod
    def _boundary_candidate_id(decision: dict[str, Any], before: dict[str, Any] | None) -> str | None:
        candidate_id = decision.get("candidate_id")
        if candidate_id:
            return str(candidate_id)
        for key in ("safety_rewritten_action", "proposed_action"):
            action = decision.get(key) or {}
            if isinstance(action, dict) and action.get("candidate_id"):
                return str(action["candidate_id"])
        if before:
            selected = [
                candidate for candidate in before["candidates"] if int(candidate.get("selected") or 0)
            ]
            if len(selected) == 1:
                return str(selected[0]["candidate_id"])
            dangerous = [
                candidate
                for candidate in before["candidates"]
                if candidate.get("risk_level") in {"high", "blocked"}
                and int(candidate.get("terminal") or 0)
            ]
            if len(dangerous) == 1:
                return str(dangerous[0]["candidate_id"])
        return None

    def detail(self, decision_id: str, *, reviewer: str = "human") -> dict[str, object]:
        with closing(self._runtime_connect()) as connection:
            row = connection.execute(
                """
                SELECT d.*, s.run_id, s.app_package, s.app_version, s.locale,
                       s.goal_text_redacted, s.goal_id AS session_goal_id,
                       s.task_context_json, s.status AS session_status,
                       s.terminal_reason AS session_terminal_reason,
                       s.handoff_reason AS session_handoff_reason,
                       s.created_at AS session_created_at, s.updated_at AS session_updated_at,
                       r.collector_alias, r.device_instance_id, r.manufacturer,
                       r.model AS device_model, r.android_api_level, r.android_release,
                       r.collector_app_version, r.collector_build_id,
                       r.executor_version, r.executor_build_id, r.server_release_id,
                       r.run_mode, r.artifact_policy, r.test_account,
                       o.observation_id, o.connectivity_status, o.next_screen_fingerprint,
                       o.state_changed, o.outcome_type, o.progress_label,
                       o.destination_match_after, o.failure_class,
                       o.terminal_reason AS observation_terminal_reason,
                       o.handoff_reason AS observation_handoff_reason,
                       o.outcome_judge, o.evaluator_id, o.evaluator_version,
                       o.outcome_evidence_frame_ids_json, o.observed_at,
                       x.execution_status, x.execution_succeeded, x.observed_signal,
                       x.recovery_action, x.actual_action_json, x.executor_method,
                       x.attempt_no, x.failure_code, x.settle_duration_ms,
                       x.settle_reason, x.external_package, x.human_intervention,
                       x.candidate_forbidden, x.reflection_level, x.reflection_reason
                FROM navigation_decisions d
                JOIN navigation_sessions s ON s.session_id = d.session_id
                LEFT JOIN navigation_collection_runs r ON r.run_id = s.run_id
                LEFT JOIN navigation_observations o ON o.decision_id = d.decision_id
                LEFT JOIN navigation_step_executions x ON x.decision_id = d.decision_id
                WHERE d.decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
            if row is None:
                raise KeyError(decision_id)
            decision = dict(row)
            for key, fallback in (
                ("screen_payload_json", {}),
                ("plan_json", {}),
                ("evidence_case_ids_json", []),
                ("candidate_values_json", []),
                ("proposed_action_json", {}),
                ("safety_rewritten_action_json", {}),
                ("retrieval_hits_json", []),
                ("decision_provenance_json", {}),
                ("task_context_json", {}),
                ("outcome_evidence_frame_ids_json", []),
                ("actual_action_json", {}),
            ):
                target_key = key.removesuffix("_json")
                decision[target_key] = _json_value(decision.pop(key, None), fallback)

            snapshot_rows = connection.execute(
                """
                SELECT * FROM navigation_screen_snapshots
                WHERE decision_id = ? ORDER BY CASE phase WHEN 'before' THEN 0 ELSE 1 END
                """,
                (decision_id,),
            ).fetchall()
            screens: dict[str, dict[str, Any]] = {}
            for snapshot in snapshot_rows:
                candidates = connection.execute(
                    """
                    SELECT * FROM navigation_screen_candidates
                    WHERE snapshot_id = ? ORDER BY ordinal
                    """,
                    (snapshot["snapshot_id"],),
                ).fetchall()
                screens[str(snapshot["phase"])] = self._compact_screen(snapshot, candidates)

            timeline_rows = connection.execute(
                """
                SELECT d.decision_id, d.step_ordinal, d.action_name, d.candidate_id,
                       d.confidence, d.safety_status, d.created_at,
                       o.outcome_type, o.progress_label, o.state_changed
                FROM navigation_decisions d
                LEFT JOIN navigation_observations o ON o.decision_id = d.decision_id
                WHERE d.session_id = ? ORDER BY d.step_ordinal
                """,
                (decision["session_id"],),
            ).fetchall()
        review_map = self._review_map(reviewer)
        timeline = []
        for timeline_row in timeline_rows:
            item = dict(timeline_row)
            item["reviewed"] = str(item["decision_id"]) in review_map
            timeline.append(item)

        with closing(self._review_connect()) as target:
            review_row = target.execute(
                """
                SELECT * FROM navigation_human_reviews
                WHERE decision_id = ? AND reviewer = ?
                """,
                (decision_id, reviewer),
            ).fetchone()
            machine_row = target.execute(
                "SELECT * FROM navigation_machine_assessments WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        review = dict(review_row) if review_row else None
        if review:
            review["source_summary"] = _json_value(review.pop("source_summary_json"), {})
        machine_assessment = dict(machine_row) if machine_row else None
        if machine_assessment:
            machine_assessment["assessment"] = _json_value(
                machine_assessment.pop("assessment_json"), {}
            )

        decision["boundary_candidate_id"] = self._boundary_candidate_id(
            decision, screens.get("before")
        )
        decision["evidence_complete"] = bool(
            screens.get("before") and decision.get("observation_id") and screens.get("after")
        )
        return {
            "decision": decision,
            "screens": screens,
            "timeline": timeline,
            "human_review": review,
            "machine_assessment": machine_assessment,
            "source_read_only": True,
        }

    def save_review(
        self,
        decision_id: str,
        request: NavigationHumanReviewRequest,
    ) -> dict[str, object]:
        with closing(self._runtime_connect()) as source:
            source_row = source.execute(
                """
                SELECT d.decision_id, d.session_id, d.step_ordinal, d.action_name,
                       d.candidate_id, d.confidence, d.safety_status,
                       s.app_package, s.goal_text_redacted,
                       o.outcome_type, o.progress_label
                FROM navigation_decisions d
                JOIN navigation_sessions s ON s.session_id = d.session_id
                LEFT JOIN navigation_observations o ON o.decision_id = d.decision_id
                WHERE d.decision_id = ?
                """,
                (decision_id,),
            ).fetchone()
            if source_row is None:
                raise KeyError(decision_id)
            if request.better_candidate_status == "selected":
                candidate_exists = source.execute(
                    """
                    SELECT 1
                    FROM navigation_screen_snapshots ss
                    JOIN navigation_screen_candidates sc ON sc.snapshot_id = ss.snapshot_id
                    WHERE ss.decision_id = ? AND ss.phase = 'before'
                      AND sc.candidate_id = ?
                    """,
                    (decision_id, request.better_candidate_id),
                ).fetchone()
                if candidate_exists is None:
                    raise ValueError("the selected better candidate is not on the before screen")
            source_summary = dict(source_row)

        now = utc_now()
        with closing(self._review_connect()) as target:
            existing = target.execute(
                """
                SELECT review_id, created_at FROM navigation_human_reviews
                WHERE decision_id = ? AND reviewer = ?
                """,
                (decision_id, request.reviewer),
            ).fetchone()
            review_id = str(existing["review_id"]) if existing else f"navr_{uuid.uuid4().hex}"
            created_at = str(existing["created_at"]) if existing else now
            target.execute(
                """
                INSERT INTO navigation_human_reviews(
                    review_id, decision_id, reviewer, action_judgment,
                    progress_judgment, safety_boundary_judgment,
                    better_candidate_status, better_candidate_id,
                    system_success_judgment, notes, source_summary_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id, reviewer) DO UPDATE SET
                    action_judgment = excluded.action_judgment,
                    progress_judgment = excluded.progress_judgment,
                    safety_boundary_judgment = excluded.safety_boundary_judgment,
                    better_candidate_status = excluded.better_candidate_status,
                    better_candidate_id = excluded.better_candidate_id,
                    system_success_judgment = excluded.system_success_judgment,
                    notes = excluded.notes,
                    source_summary_json = excluded.source_summary_json,
                    updated_at = excluded.updated_at
                """,
                (
                    review_id,
                    decision_id,
                    request.reviewer,
                    request.action_judgment,
                    request.progress_judgment,
                    request.safety_boundary_judgment,
                    request.better_candidate_status,
                    request.better_candidate_id,
                    request.system_success_judgment,
                    request.notes,
                    json.dumps(source_summary, ensure_ascii=False, sort_keys=True),
                    created_at,
                    now,
                ),
            )
            target.commit()
        return {
            "review_id": review_id,
            "decision_id": decision_id,
            "reviewer": request.reviewer,
            "updated_at": now,
            "source_read_only": True,
        }
