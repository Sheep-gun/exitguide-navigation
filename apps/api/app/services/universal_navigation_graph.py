import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping

from app.config import Settings, get_settings
from app.resource_paths import get_resource_root
from app.schemas import (
    UniversalNavigationCandidate,
    UniversalNavigationGraphResponse,
    UniversalNavigationGraphScreen,
    UniversalNavigationGraphTransition,
    UniversalNavigationGraphUpdate,
    UniversalNavigationDiscoveredRoute,
    UniversalNavigationElement,
    UniversalNavigationObserveRequest,
    UniversalNavigationRouteStep,
    UniversalNavigationScreen,
)
from app.services.navigation_performance import NavigationPerformanceStore


ROOT = get_resource_root()
DEFAULT_DATABASE_PATH = ROOT / ".artifacts" / "universal-navigation.sqlite"
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}\b")
LONG_NUMBER_PATTERN = re.compile(r"\b\d{5,}\b")
TOKEN_PATTERN = re.compile(r"\b(?:bearer|token|session|cookie)[=: ]+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE)
SERVING_ROUTE_STATUSES = frozenset({"verified_candidate", "approved"})


@dataclass(frozen=True)
class StoredAction:
    action_id: str
    screen_fingerprint: str
    element_key: str
    last_element_id: str
    label: str
    role: str
    risk_level: str
    risk_reason: str | None


@dataclass(frozen=True)
class ObservationResult:
    screen_fingerprint: str
    screen_created: bool
    actions_created: int
    transition_recorded: bool
    actions_by_element_id: dict[str, StoredAction]
    executed_recommendation_id: str | None
    executed_transition_outcome: str | None


@dataclass(frozen=True)
class StoredRoute:
    route_id: str
    app_key: str
    goal_key: str
    target_function: str
    start_screen_fingerprint: str
    destination_screen_fingerprint: str
    provisional: bool
    lifecycle_status: str
    confidence: float
    steps: tuple[dict[str, object], ...]

    def response_model(self) -> UniversalNavigationDiscoveredRoute:
        return UniversalNavigationDiscoveredRoute(
            route_id=self.route_id,
            target_function=self.target_function,
            start_screen_fingerprint=self.start_screen_fingerprint,
            destination_screen_fingerprint=self.destination_screen_fingerprint,
            provisional=self.provisional,
            lifecycle_status=self.lifecycle_status,
            steps=[UniversalNavigationRouteStep(**step) for step in self.steps],
        )


@dataclass(frozen=True)
class ExplorationState:
    exploration_id: str
    app_key: str
    goal_key: str
    goal_text: str
    target_function: str
    status: str
    start_screen_fingerprint: str
    current_screen_fingerprint: str
    destination_screen_fingerprint: str
    started_at: str
    updated_at: str
    action_count: int
    back_count: int
    max_actions: int
    max_depth: int
    timeout_seconds: int
    path: tuple[dict[str, object], ...]
    pending: dict[str, object] | None
    route_id: str


@dataclass(frozen=True)
class ExplorationFrontierItem:
    frontier_id: str
    exploration_id: str
    screen_fingerprint: str
    action_id: str
    element_key: str
    label: str
    function_ids: tuple[str, ...]
    goal_alignment: float
    novelty: float
    risk_penalty: float
    expected_cost: float
    source_depth: int
    status: str
    first_seen_at: str


class UniversalNavigationGraphRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self.performance = NavigationPerformanceStore(database_path)

    def ensure_app_scope(self, app_package: str, app_version: str, locale: str) -> str:
        """Persist the version-scoped app identity required by graph records."""

        app_key = _app_key(app_package, app_version, locale)
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO universal_apps (
                  app_key, app_package, app_version, locale, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_key) DO UPDATE SET last_seen_at = excluded.last_seen_at
                """,
                (app_key, app_package, app_version, locale, now, now),
            )
            connection.commit()
        return app_key

    def observe(
        self,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
    ) -> ObservationResult:
        screen_fingerprint = fingerprint_screen(request.app_package, request.screen)
        app_key = _app_key(request.app_package, request.app_version, request.locale)
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO universal_apps (
                  app_key, app_package, app_version, locale, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_key) DO UPDATE SET last_seen_at = excluded.last_seen_at
                """,
                (app_key, request.app_package, request.app_version, request.locale, now, now),
            )
            existing_screen = connection.execute(
                "SELECT 1 FROM universal_screens WHERE screen_fingerprint = ?",
                (screen_fingerprint,),
            ).fetchone()
            title = sanitize_text(request.screen.window_title) or _screen_title(request.screen)
            connection.execute(
                """
                INSERT INTO universal_screens (
                  screen_fingerprint, app_key, activity_name, title, structure_json,
                  first_seen_at, last_seen_at, seen_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(screen_fingerprint) DO UPDATE SET
                  activity_name = excluded.activity_name,
                  title = excluded.title,
                  structure_json = excluded.structure_json,
                  last_seen_at = excluded.last_seen_at,
                  seen_count = universal_screens.seen_count + 1
                """,
                (
                    screen_fingerprint,
                    app_key,
                    sanitize_text(request.screen.activity_name),
                    title,
                    _screen_structure_json(request.screen),
                    now,
                    now,
                ),
            )

            created_count = 0
            actions_by_element_id: dict[str, StoredAction] = {}
            for candidate in candidates:
                action_id = _action_id(screen_fingerprint, candidate.element_key)
                existing_action = connection.execute(
                    "SELECT 1 FROM universal_actions WHERE action_id = ?",
                    (action_id,),
                ).fetchone()
                if existing_action is None:
                    created_count += 1
                connection.execute(
                    """
                    INSERT INTO universal_actions (
                      action_id, screen_fingerprint, element_key, last_element_id, label,
                      role, risk_level, risk_reason, first_seen_at, last_seen_at, seen_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(action_id) DO UPDATE SET
                      last_element_id = excluded.last_element_id,
                      label = excluded.label,
                      role = excluded.role,
                      risk_level = excluded.risk_level,
                      risk_reason = excluded.risk_reason,
                      last_seen_at = excluded.last_seen_at,
                      seen_count = universal_actions.seen_count + 1
                    """,
                    (
                        action_id,
                        screen_fingerprint,
                        candidate.element_key,
                        candidate.element_id,
                        sanitize_text(candidate.label),
                        candidate.role,
                        candidate.risk_level,
                        candidate.risk_reason,
                        now,
                        now,
                    ),
                )
                actions_by_element_id[candidate.element_id] = StoredAction(
                    action_id=action_id,
                    screen_fingerprint=screen_fingerprint,
                    element_key=candidate.element_key,
                    last_element_id=candidate.element_id,
                    label=sanitize_text(candidate.label),
                    role=candidate.role,
                    risk_level=candidate.risk_level,
                    risk_reason=candidate.risk_reason,
                )

            (
                transition_recorded,
                executed_recommendation_id,
                executed_transition_outcome,
            ) = self._record_transition(
                connection=connection,
                request=request,
                to_screen_fingerprint=screen_fingerprint,
                now=now,
            )
            connection.commit()
        return ObservationResult(
            screen_fingerprint=screen_fingerprint,
            screen_created=existing_screen is None,
            actions_created=created_count,
            transition_recorded=transition_recorded,
            actions_by_element_id=actions_by_element_id,
            executed_recommendation_id=executed_recommendation_id,
            executed_transition_outcome=executed_transition_outcome,
        )

    def record_gold_observation(
        self,
        *,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
        observation: ObservationResult,
        target_function: str,
    ) -> dict[str, object]:
        """Persist a user-driven demonstration without serving or promoting it.

        The current screen is stored with its complete candidate set.  A
        transition arriving with the next observation labels the candidate on
        the preceding screen that the human actually selected.
        """

        app_key = _app_key(request.app_package, request.app_version, request.locale)
        goal_key = fingerprint_goal(request.goal_text)
        now = _utc_now()
        candidate_payload = [candidate.model_dump(mode="json") for candidate in candidates]
        screen_context = {
            "activity_name": sanitize_text(request.screen.activity_name),
            "window_title": sanitize_text(request.screen.window_title),
            "event_type": sanitize_text(request.screen.event_type),
            "captured_at": request.screen.captured_at,
            "elements": json.loads(_screen_structure_json(request.screen)),
        }
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT status FROM navigation_gold_recordings WHERE recording_id = ?",
                (request.session_id,),
            ).fetchone()
            if existing is not None and str(existing["status"]) != "recording":
                raise ValueError(
                    f"Gold recording {request.session_id} is already {existing['status']}."
                )
            connection.execute(
                """
                INSERT INTO navigation_gold_recordings (
                  recording_id, app_key, app_package, app_version, locale,
                  goal_key, goal_text, target_function, status,
                  start_screen_fingerprint, destination_screen_fingerprint,
                  destination_correct, safe_stop, reviewer, review_notes,
                  started_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recording', ?, NULL,
                          NULL, NULL, NULL, NULL, ?, ?, NULL)
                ON CONFLICT(recording_id) DO UPDATE SET
                  target_function = excluded.target_function,
                  updated_at = excluded.updated_at
                """,
                (
                    request.session_id,
                    app_key,
                    request.app_package,
                    request.app_version,
                    request.locale,
                    goal_key,
                    sanitize_text(request.goal_text),
                    target_function,
                    observation.screen_fingerprint,
                    now,
                    now,
                ),
            )

            transition = request.transition
            if transition is not None:
                prior = connection.execute(
                    """
                    SELECT * FROM navigation_gold_steps
                    WHERE recording_id = ? AND screen_fingerprint = ?
                      AND selected_action IS NULL
                    ORDER BY ordinal DESC LIMIT 1
                    """,
                    (request.session_id, transition.from_screen_fingerprint),
                ).fetchone()
                if prior is not None:
                    selected: dict[str, object] | None = None
                    try:
                        stored_candidates = json.loads(str(prior["candidates_json"] or "[]"))
                    except json.JSONDecodeError:
                        stored_candidates = []
                    for candidate in stored_candidates if isinstance(stored_candidates, list) else []:
                        if (
                            isinstance(candidate, dict)
                            and str(candidate.get("element_id", "")) == transition.performed_element_id
                        ):
                            selected = candidate
                            break
                    recorded_action = transition.action_kind
                    if (
                        transition.action_kind == "scroll_forward"
                        and not sanitize_text(str((selected or {}).get("label", "")))
                    ):
                        inferred_row = _infer_gold_row_click(
                            stored_candidates,
                            request.screen.elements,
                        )
                        if inferred_row is not None:
                            selected = inferred_row
                            recorded_action = "click"
                    if selected is None and transition.action_kind == "click":
                        action = connection.execute(
                            """
                            SELECT element_key, label, risk_level
                            FROM universal_actions
                            WHERE screen_fingerprint = ? AND last_element_id = ?
                            """,
                            (
                                transition.from_screen_fingerprint,
                                transition.performed_element_id,
                            ),
                        ).fetchone()
                        if action is not None:
                            selected = dict(action)
                    connection.execute(
                        """
                        UPDATE navigation_gold_steps SET
                          selected_element_id = ?, selected_element_key = ?,
                          selected_label = ?, selected_action = ?,
                          selected_risk_level = ?, outcome = ?,
                          next_screen_fingerprint = ?, updated_at = ?
                        WHERE step_id = ?
                        """,
                        (
                            str((selected or {}).get("element_id", transition.performed_element_id)),
                            str((selected or {}).get("element_key", "")),
                            sanitize_text(str((selected or {}).get("label", ""))),
                            recorded_action,
                            str((selected or {}).get("risk_level", "low")),
                            transition.outcome,
                            observation.screen_fingerprint,
                            now,
                            prior["step_id"],
                        ),
                    )

            latest = connection.execute(
                """
                SELECT step_id, ordinal, screen_fingerprint, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = ? ORDER BY ordinal DESC LIMIT 1
                """,
                (request.session_id,),
            ).fetchone()
            duplicate_unselected_screen = (
                latest is not None
                and str(latest["screen_fingerprint"]) == observation.screen_fingerprint
                and latest["selected_action"] is None
                and transition is None
            )
            if duplicate_unselected_screen:
                connection.execute(
                    """
                    UPDATE navigation_gold_steps SET
                      screen_context_json = ?, candidates_json = ?, updated_at = ?
                    WHERE step_id = ?
                    """,
                    (
                        json.dumps(screen_context, ensure_ascii=False, separators=(",", ":")),
                        json.dumps(candidate_payload, ensure_ascii=False, separators=(",", ":")),
                        now,
                        latest["step_id"],
                    ),
                )
            else:
                ordinal = 0 if latest is None else int(latest["ordinal"]) + 1
                step_id = hashlib.sha256(
                    f"{request.session_id}|{ordinal}|{observation.screen_fingerprint}".encode("utf-8")
                ).hexdigest()[:24]
                connection.execute(
                    """
                    INSERT INTO navigation_gold_steps (
                      step_id, recording_id, ordinal, screen_fingerprint,
                      screen_context_json, candidates_json,
                      selected_element_id, selected_element_key, selected_label,
                      selected_action, selected_risk_level, outcome,
                      next_screen_fingerprint, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL,
                              NULL, NULL, ?, ?)
                    """,
                    (
                        step_id,
                        request.session_id,
                        ordinal,
                        observation.screen_fingerprint,
                        json.dumps(screen_context, ensure_ascii=False, separators=(",", ":")),
                        json.dumps(candidate_payload, ensure_ascii=False, separators=(",", ":")),
                        now,
                        now,
                    ),
                )
            connection.commit()
        return self.gold_recording(request.session_id)

    def complete_gold_recording(
        self,
        recording_id: str,
        *,
        destination_correct: bool,
        safe_stop: bool,
        reviewer: str,
        notes: str | None,
    ) -> dict[str, object]:
        now = _utc_now()
        with self._connection() as connection:
            recording = connection.execute(
                "SELECT status FROM navigation_gold_recordings WHERE recording_id = ?",
                (recording_id,),
            ).fetchone()
            if recording is None:
                raise KeyError(recording_id)
            if str(recording["status"]) != "recording":
                raise ValueError(f"Gold recording {recording_id} is already {recording['status']}.")
            destination = connection.execute(
                """
                SELECT screen_fingerprint FROM navigation_gold_steps
                WHERE recording_id = ? ORDER BY ordinal DESC LIMIT 1
                """,
                (recording_id,),
            ).fetchone()
            if destination is None:
                raise ValueError("Gold recording has no captured screens.")
            connection.execute(
                """
                UPDATE navigation_gold_recordings SET
                  status = 'review_pending', destination_screen_fingerprint = ?,
                  destination_correct = ?, safe_stop = ?, reviewer = ?,
                  review_notes = ?, updated_at = ?, completed_at = ?
                WHERE recording_id = ?
                """,
                (
                    destination["screen_fingerprint"],
                    int(destination_correct),
                    int(safe_stop),
                    sanitize_text(reviewer),
                    sanitize_text(notes or "") or None,
                    now,
                    now,
                    recording_id,
                ),
            )
            connection.commit()
        return self.gold_recording(recording_id)

    def review_gold_recording(
        self,
        recording_id: str,
        *,
        decision: str,
        reviewer: str,
        notes: str | None,
    ) -> dict[str, object]:
        if decision not in {"human_gold", "rejected"}:
            raise ValueError("Review decision must be human_gold or rejected.")
        now = _utc_now()
        with self._connection() as connection:
            recording = connection.execute(
                "SELECT status, destination_correct, safe_stop FROM navigation_gold_recordings WHERE recording_id = ?",
                (recording_id,),
            ).fetchone()
            if recording is None:
                raise KeyError(recording_id)
            if str(recording["status"]) != "review_pending":
                raise ValueError("Only review_pending recordings can be reviewed.")
            if decision == "human_gold" and (
                int(recording["destination_correct"] or 0) != 1
                or int(recording["safe_stop"] or 0) != 1
            ):
                raise ValueError("Human Gold requires a correct destination and safe stop.")
            connection.execute(
                """
                UPDATE navigation_gold_recordings SET status = ?, reviewer = ?,
                  review_notes = ?, updated_at = ? WHERE recording_id = ?
                """,
                (
                    decision,
                    sanitize_text(reviewer),
                    sanitize_text(notes or "") or None,
                    now,
                    recording_id,
                ),
            )
            connection.commit()
        return self.gold_recording(recording_id)

    def cancel_gold_recording(self, recording_id: str) -> dict[str, object]:
        now = _utc_now()
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE navigation_gold_recordings SET status = 'cancelled', updated_at = ?
                WHERE recording_id = ? AND status = 'recording'
                """,
                (now, recording_id),
            )
            if result.rowcount == 0:
                existing = connection.execute(
                    "SELECT status FROM navigation_gold_recordings WHERE recording_id = ?",
                    (recording_id,),
                ).fetchone()
                if existing is None:
                    raise KeyError(recording_id)
                raise ValueError(f"Gold recording {recording_id} is already {existing['status']}.")
            connection.commit()
        return self.gold_recording(recording_id)

    def gold_recording(self, recording_id: str) -> dict[str, object]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT recording.*,
                  COUNT(step.step_id) AS step_count,
                  SUM(CASE WHEN step.selected_action IS NOT NULL THEN 1 ELSE 0 END)
                    AS selected_step_count
                FROM navigation_gold_recordings recording
                LEFT JOIN navigation_gold_steps step
                  ON step.recording_id = recording.recording_id
                WHERE recording.recording_id = ?
                GROUP BY recording.recording_id
                """,
                (recording_id,),
            ).fetchone()
        if row is None:
            raise KeyError(recording_id)
        return {
            "recording_id": str(row["recording_id"]),
            "status": str(row["status"]),
            "app_package": str(row["app_package"]),
            "app_version": str(row["app_version"]),
            "locale": str(row["locale"]),
            "goal_text": str(row["goal_text"]),
            "target_function": str(row["target_function"]),
            "step_count": int(row["step_count"] or 0),
            "selected_step_count": int(row["selected_step_count"] or 0),
            "destination_screen_fingerprint": row["destination_screen_fingerprint"],
            "destination_correct": (
                None if row["destination_correct"] is None else bool(row["destination_correct"])
            ),
            "safe_stop": None if row["safe_stop"] is None else bool(row["safe_stop"]),
            "reviewer": row["reviewer"],
            "review_notes": row["review_notes"],
        }

    def record_recommendation(
        self,
        *,
        recommendation_id: str,
        session_id: str,
        app_package: str,
        app_version: str,
        locale: str,
        goal_text: str,
        goal_interpretation: str,
        target_function: str,
        decision_mode: str,
        screen_fingerprint: str,
        action_id: str | None,
        confidence: float,
    ) -> None:
        app_key = _app_key(app_package, app_version, locale)
        goal_key = fingerprint_goal(goal_text)
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO universal_sessions (
                  session_id, app_key, goal_key, goal_text, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  goal_key = excluded.goal_key,
                  goal_text = excluded.goal_text,
                  updated_at = excluded.updated_at
                """,
                (session_id, app_key, goal_key, sanitize_text(goal_text), now, now),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO universal_session_steps (
                  recommendation_id, session_id, screen_fingerprint, action_id,
                  goal_interpretation, target_function, decision_mode, confidence,
                  performed, outcome, next_screen_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', NULL, ?)
                """,
                (
                    recommendation_id,
                    session_id,
                    screen_fingerprint,
                    action_id,
                    sanitize_text(goal_interpretation),
                    sanitize_text(target_function),
                    decision_mode,
                    confidence,
                    now,
                ),
            )
            connection.commit()

    def mark_goal_completed(self, session_id: str, goal_text: str) -> None:
        goal_key = fingerprint_goal(goal_text)
        now = _utc_now()
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT action_id, AVG(confidence) AS confidence
                FROM universal_session_steps
                WHERE session_id = ? AND action_id IS NOT NULL
                  AND (performed = 1 OR outcome = 'navigated')
                GROUP BY action_id
                """,
                (session_id,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO universal_action_goal_stats (
                      action_id, goal_key, success_count, failure_count, confidence, last_updated_at
                    ) VALUES (?, ?, 1, 0, ?, ?)
                    ON CONFLICT(action_id, goal_key) DO UPDATE SET
                      success_count = universal_action_goal_stats.success_count + 1,
                      confidence = MAX(universal_action_goal_stats.confidence, excluded.confidence),
                      last_updated_at = excluded.last_updated_at
                    """,
                    (row["action_id"], goal_key, float(row["confidence"] or 0.5), now),
                )
            connection.execute(
                "UPDATE universal_sessions SET status = 'completed', updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            connection.commit()

    def cached_action(self, screen_fingerprint: str, goal_text: str) -> StoredAction | None:
        goal_key = fingerprint_goal(goal_text)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT a.*
                FROM universal_actions a
                JOIN universal_action_goal_stats stats ON stats.action_id = a.action_id
                WHERE a.screen_fingerprint = ? AND stats.goal_key = ?
                  AND stats.success_count > stats.failure_count
                ORDER BY stats.success_count DESC, stats.confidence DESC, a.seen_count DESC
                LIMIT 1
                """,
                (screen_fingerprint, goal_key),
            ).fetchone()
        return None if row is None else _stored_action(row)

    def graph_hints(self, screen_fingerprint: str) -> list[dict[str, object]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT a.element_key, a.label, t.to_screen_fingerprint,
                       SUM(t.success_count) AS success_count,
                       SUM(t.failure_count) AS failure_count
                FROM universal_actions a
                JOIN universal_transitions t ON t.action_id = a.action_id
                WHERE a.screen_fingerprint = ?
                GROUP BY a.element_key, a.label, t.to_screen_fingerprint
                ORDER BY success_count DESC, failure_count ASC
                LIMIT 20
                """,
                (screen_fingerprint,),
            ).fetchall()
        return [dict(row) for row in rows]

    def exploration(self, exploration_id: str) -> ExplorationState | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM universal_explorations WHERE exploration_id = ?",
                (exploration_id,),
            ).fetchone()
        return None if row is None else _exploration_state(row)

    def start_exploration(
        self,
        *,
        exploration_id: str,
        app_package: str,
        app_version: str,
        locale: str,
        goal_text: str,
        target_function: str,
        start_screen_fingerprint: str,
        max_actions: int,
        max_depth: int,
        timeout_seconds: int,
    ) -> ExplorationState:
        app_key = _app_key(app_package, app_version, locale)
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM universal_exploration_frontier WHERE exploration_id = ?",
                (exploration_id,),
            )
            connection.execute(
                "DELETE FROM universal_exploration_attempts WHERE exploration_id = ?",
                (exploration_id,),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO universal_explorations (
                  exploration_id, app_key, goal_key, goal_text, target_function, status,
                  start_screen_fingerprint, current_screen_fingerprint,
                  destination_screen_fingerprint, started_at, updated_at, action_count,
                  back_count, max_actions, max_depth, timeout_seconds, path_json,
                  pending_json, route_id
                ) VALUES (?, ?, ?, ?, ?, 'exploring', ?, ?, '', ?, ?, 0, 0, ?, ?, ?, '[]', '', '')
                """,
                (
                    exploration_id,
                    app_key,
                    fingerprint_goal(goal_text),
                    sanitize_text(goal_text),
                    target_function,
                    start_screen_fingerprint,
                    start_screen_fingerprint,
                    now,
                    now,
                    max_actions,
                    max_depth,
                    timeout_seconds,
                ),
            )
            connection.commit()
        state = self.exploration(exploration_id)
        if state is None:
            raise RuntimeError("Failed to create navigation exploration state")
        return state

    def update_exploration(
        self,
        exploration_id: str,
        *,
        status: str | None = None,
        current_screen_fingerprint: str | None = None,
        destination_screen_fingerprint: str | None = None,
        action_count: int | None = None,
        back_count: int | None = None,
        path: list[dict[str, object]] | tuple[dict[str, object], ...] | None = None,
        pending: dict[str, object] | None = None,
        clear_pending: bool = False,
        route_id: str | None = None,
    ) -> ExplorationState:
        assignments = ["updated_at = ?"]
        values: list[object] = [_utc_now()]
        fields: tuple[tuple[str, object | None], ...] = (
            ("status", status),
            ("current_screen_fingerprint", current_screen_fingerprint),
            ("destination_screen_fingerprint", destination_screen_fingerprint),
            ("action_count", action_count),
            ("back_count", back_count),
            ("route_id", route_id),
        )
        for name, value in fields:
            if value is not None:
                assignments.append(f"{name} = ?")
                values.append(value)
        if path is not None:
            assignments.append("path_json = ?")
            values.append(json.dumps(list(path), ensure_ascii=False, separators=(",", ":")))
        if pending is not None or clear_pending:
            assignments.append("pending_json = ?")
            values.append("" if clear_pending else json.dumps(pending, ensure_ascii=False, separators=(",", ":")))
        values.append(exploration_id)
        with self._connection() as connection:
            connection.execute(
                f"UPDATE universal_explorations SET {', '.join(assignments)} WHERE exploration_id = ?",
                values,
            )
            connection.commit()
        state = self.exploration(exploration_id)
        if state is None:
            raise RuntimeError("Navigation exploration state no longer exists")
        return state

    def record_exploration_attempt(
        self,
        *,
        exploration_id: str,
        screen_fingerprint: str,
        action_id: str,
        element_key_value: str,
        label: str,
        function_ids: Iterable[str],
        command: str,
        outcome: str = "issued",
        to_screen_fingerprint: str = "",
    ) -> None:
        now = _utc_now()
        attempt_id = "uxa_" + hashlib.sha256(
            f"{exploration_id}|{screen_fingerprint}|{action_id}|{command}".encode("utf-8")
        ).hexdigest()[:16]
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO universal_exploration_attempts (
                  attempt_id, exploration_id, screen_fingerprint, action_id, element_key,
                  label, function_ids_json, command, outcome, to_screen_fingerprint,
                  first_seen_at, last_seen_at, attempt_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(attempt_id) DO UPDATE SET
                  outcome = excluded.outcome,
                  to_screen_fingerprint = excluded.to_screen_fingerprint,
                  last_seen_at = excluded.last_seen_at,
                  attempt_count = universal_exploration_attempts.attempt_count + 1
                """,
                (
                    attempt_id,
                    exploration_id,
                    screen_fingerprint,
                    action_id,
                    element_key_value,
                    sanitize_text(label),
                    json.dumps(sorted(set(function_ids)), ensure_ascii=False),
                    command,
                    outcome,
                    to_screen_fingerprint,
                    now,
                    now,
                ),
            )
            connection.commit()

    def attempted_action_ids(self, exploration_id: str, screen_fingerprint: str) -> set[str]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT action_id FROM universal_exploration_attempts
                WHERE exploration_id = ? AND screen_fingerprint = ? AND command = 'click'
                """,
                (exploration_id, screen_fingerprint),
            ).fetchall()
        return {str(row["action_id"]) for row in rows}

    def release_transient_retry_once(
        self,
        *,
        exploration_id: str,
        screen_fingerprint: str,
        action_id: str,
        element_key_value: str,
        label: str,
        function_ids: Iterable[str],
    ) -> bool:
        """Preserve one retry when a child is only a transient dead end.

        A recovery Back must not make its parent gateway look like an ordinary
        failed branch.  The marker is keyed by stable element identity across
        fingerprint drift, remains as audit evidence after consumption, and
        can be released only once per exploration.
        """

        if not action_id or not element_key_value:
            return False
        now = _utc_now()
        attempt_id = "uxa_" + hashlib.sha256(
            f"{exploration_id}|{screen_fingerprint}|{action_id}|transient_retry".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        with self._connection() as connection:
            existing = connection.execute(
                """
                SELECT 1 FROM universal_exploration_attempts
                WHERE exploration_id = ? AND element_key = ?
                  AND command = 'transient_retry'
                LIMIT 1
                """,
                (exploration_id, element_key_value),
            ).fetchone()
            if existing is not None:
                return False
            connection.execute(
                """
                INSERT INTO universal_exploration_attempts (
                  attempt_id, exploration_id, screen_fingerprint, action_id,
                  element_key, label, function_ids_json, command, outcome,
                  to_screen_fingerprint, first_seen_at, last_seen_at,
                  attempt_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'transient_retry',
                          'available', '', ?, ?, 1)
                """,
                (
                    attempt_id,
                    exploration_id,
                    screen_fingerprint,
                    action_id,
                    element_key_value,
                    sanitize_text(label),
                    json.dumps(sorted(set(function_ids)), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE universal_exploration_frontier
                SET status = 'queued', last_seen_at = ?
                WHERE exploration_id = ? AND action_id = ?
                """,
                (now, exploration_id, action_id),
            )
            connection.commit()
        return True

    def transient_retry_element_keys(self, exploration_id: str) -> set[str]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT element_key FROM universal_exploration_attempts
                WHERE exploration_id = ? AND command = 'transient_retry'
                  AND outcome = 'available'
                """,
                (exploration_id,),
            ).fetchall()
        return {str(row["element_key"]) for row in rows}

    def consume_transient_retry(
        self,
        exploration_id: str,
        element_key_value: str,
    ) -> None:
        if not element_key_value:
            return
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE universal_exploration_attempts
                SET outcome = 'consumed', last_seen_at = ?
                WHERE exploration_id = ? AND element_key = ?
                  AND command = 'transient_retry' AND outcome = 'available'
                """,
                (_utc_now(), exploration_id, element_key_value),
            )
            connection.commit()

    def latest_exploration_attempt(self, exploration_id: str) -> dict[str, object] | None:
        """Return the most recently issued click/backtrack branch signature."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT element_key, label, function_ids_json, command, outcome
                FROM universal_exploration_attempts
                WHERE exploration_id = ?
                ORDER BY last_seen_at DESC, rowid DESC
                LIMIT 1
                """,
                (exploration_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            function_ids = json.loads(str(row["function_ids_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            function_ids = []
        return {
            "element_key": str(row["element_key"] or ""),
            "label": str(row["label"] or ""),
            "function_ids": tuple(
                sorted(
                    str(value)
                    for value in function_ids
                    if isinstance(value, str) and value
                )
            ),
            "command": str(row["command"] or ""),
            "outcome": str(row["outcome"] or ""),
        }

    def action_novelty(self, action_ids: Iterable[str]) -> dict[str, float]:
        """Return deterministic graph novelty without storing screen content."""

        unique = tuple(sorted({str(value) for value in action_ids if value}))
        if not unique:
            return {}
        placeholders = ",".join("?" for _ in unique)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT action_id, SUM(success_count + failure_count) AS observations
                FROM universal_transitions
                WHERE action_id IN ({placeholders})
                GROUP BY action_id
                """,
                unique,
            ).fetchall()
        observed = {
            str(row["action_id"]): max(0, int(row["observations"] or 0))
            for row in rows
        }
        return {
            action_id: round(1.0 / (1.0 + observed.get(action_id, 0)), 6)
            for action_id in unique
        }

    def upsert_exploration_frontier(
        self,
        exploration_id: str,
        items: Iterable[Mapping[str, object]],
    ) -> None:
        """Persist safe click alternatives; terminal and scroll actions never enter."""

        now = _utc_now()
        rows = []
        for item in items:
            action_id = str(item["action_id"])
            screen_fingerprint = str(item["screen_fingerprint"])
            frontier_id = "uxf_" + hashlib.sha256(
                f"{exploration_id}|{screen_fingerprint}|{action_id}".encode("utf-8")
            ).hexdigest()[:16]
            rows.append(
                (
                    frontier_id,
                    exploration_id,
                    screen_fingerprint,
                    action_id,
                    str(item["element_key"]),
                    sanitize_text(str(item["label"])),
                    json.dumps(
                        sorted({str(value) for value in item.get("function_ids", [])}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    max(0.0, min(1.0, float(item["goal_alignment"]))),
                    max(0.0, min(1.0, float(item["novelty"]))),
                    max(0.0, min(1.0, float(item["risk_penalty"]))),
                    max(0.0, float(item["expected_cost"])),
                    max(0, int(item["source_depth"])),
                    now,
                    now,
                )
            )
        if not rows:
            return
        with self._connection() as connection:
            connection.executemany(
                """
                INSERT INTO universal_exploration_frontier (
                  frontier_id, exploration_id, screen_fingerprint, action_id,
                  element_key, label, function_ids_json, goal_alignment,
                  novelty, risk_penalty, expected_cost, source_depth, status,
                  first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
                ON CONFLICT(frontier_id) DO UPDATE SET
                  element_key = excluded.element_key,
                  label = excluded.label,
                  function_ids_json = excluded.function_ids_json,
                  goal_alignment = excluded.goal_alignment,
                  novelty = excluded.novelty,
                  risk_penalty = excluded.risk_penalty,
                  expected_cost = excluded.expected_cost,
                  source_depth = excluded.source_depth,
                  last_seen_at = excluded.last_seen_at
                WHERE universal_exploration_frontier.status = 'queued'
                """,
                rows,
            )
            connection.commit()

    def exploration_frontier(
        self,
        exploration_id: str,
        *,
        statuses: tuple[str, ...] = ("queued",),
    ) -> tuple[ExplorationFrontierItem, ...]:
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        with self._connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM universal_exploration_frontier
                WHERE exploration_id = ? AND status IN ({placeholders})
                """,
                (exploration_id, *statuses),
            ).fetchall()
        return tuple(_frontier_item(row) for row in rows)

    def set_exploration_frontier_status(
        self,
        exploration_id: str,
        action_id: str,
        status: str,
    ) -> None:
        if status not in {"queued", "issued", "expanded", "failed", "stale"}:
            raise ValueError("Unsupported exploration frontier status")
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE universal_exploration_frontier
                SET status = ?, last_seen_at = ?
                WHERE exploration_id = ? AND action_id = ?
                """,
                (status, _utc_now(), exploration_id, action_id),
            )
            connection.commit()

    def save_route(
        self,
        *,
        app_package: str,
        app_version: str,
        locale: str,
        goal_text: str,
        target_function: str,
        start_screen_fingerprint: str,
        destination_screen_fingerprint: str,
        steps: list[dict[str, object]],
        confidence: float,
        provisional: bool = True,
    ) -> StoredRoute:
        app_key = _app_key(app_package, app_version, locale)
        serialized = json.dumps(steps, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        route_id = "ugr_" + hashlib.sha256(
            f"{app_key}|{target_function}|{start_screen_fingerprint}|{serialized}".encode("utf-8")
        ).hexdigest()[:16]
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO universal_routes (
                  route_id, app_key, goal_key, target_function, start_screen_fingerprint,
                  destination_screen_fingerprint, steps_json, confidence, provisional,
                  status, success_count, failure_count, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'shadow', 0, 0, ?, ?)
                ON CONFLICT(route_id) DO UPDATE SET
                  steps_json = excluded.steps_json,
                  confidence = MAX(universal_routes.confidence, excluded.confidence),
                  destination_screen_fingerprint = excluded.destination_screen_fingerprint,
                  last_seen_at = excluded.last_seen_at
                """,
                (
                    route_id,
                    app_key,
                    fingerprint_goal(goal_text),
                    target_function,
                    start_screen_fingerprint,
                    destination_screen_fingerprint,
                    serialized,
                    max(0.0, min(1.0, confidence)),
                    # Discovery itself never proves correctness. All new
                    # routes enter shadow/provisional regardless of caller
                    # preference and are promoted only by trusted evidence.
                    1,
                    now,
                    now,
                ),
            )
            self._sync_app_function_route(connection, route_id)
            connection.commit()
        route = self.route(route_id)
        if route is None:
            raise RuntimeError("Failed to persist discovered route")
        return route

    def route(self, route_id: str) -> StoredRoute | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM universal_routes WHERE route_id = ?",
                (route_id,),
            ).fetchone()
        return None if row is None else _stored_route(row)

    def approve_route(self, route_id: str) -> StoredRoute:
        """Explicitly approve an eligible shadow route after lifecycle review.

        Performance validation alone never calls this method.  Keeping this as
        a separate graph action prevents benchmark or human-gold measurements
        from silently promoting newly discovered routes into the serving set.
        """
        now = _utc_now()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT route.status, apps.app_version,
                  performance.eligible, performance.under_sampled,
                  performance.trusted_sample_count
                FROM universal_routes AS route
                JOIN universal_apps AS apps ON apps.app_key = route.app_key
                LEFT JOIN route_performance AS performance
                  ON performance.route_id = route.route_id
                WHERE route.route_id = ?
                """,
                (route_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown universal navigation route: {route_id}")
            if not str(row["app_version"] or "").strip():
                raise ValueError("Approved route requires a non-empty app version")
            already_approved = str(row["status"]) == "approved"
            if not already_approved and str(row["status"]) not in {
                "shadow",
                "verified_candidate",
            }:
                raise ValueError(
                    "Only a shadow or verified candidate route can be explicitly approved"
                )
            if not already_approved and (
                row["eligible"] is None
                or not bool(row["eligible"])
                or bool(row["under_sampled"])
                or int(row["trusted_sample_count"] or 0) < self.performance.minimum_samples
            ):
                raise ValueError("Route requires sufficient clean trusted evidence before approval")
            if not already_approved:
                connection.execute(
                    """
                    UPDATE universal_routes SET status = 'approved', provisional = 0,
                      last_seen_at = ? WHERE route_id = ?
                    """,
                    (now, route_id),
                )
                self._sync_app_function_route(connection, route_id)
                connection.commit()
        route = self.route(route_id)
        if route is None:
            raise RuntimeError("Failed to approve universal navigation route")
        return route

    def verify_route_candidate(self, route_id: str) -> StoredRoute:
        """Mark one independently validated route as a serving candidate.

        A verified candidate remains provisional and is not a formal approval.
        It may be reused only by the guarded explore-mode path, which checks
        every live control and expected screen transition before continuing.
        """

        now = _utc_now()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT route.status, apps.app_version,
                  performance.trusted_sample_count,
                  performance.success_count, performance.failure_count,
                  performance.destination_accuracy, performance.safe_stop_rate,
                  performance.unsafe_click_count, performance.wrong_click_count
                FROM universal_routes AS route
                JOIN universal_apps AS apps ON apps.app_key = route.app_key
                LEFT JOIN route_performance AS performance
                  ON performance.route_id = route.route_id
                WHERE route.route_id = ?
                """,
                (route_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Unknown universal navigation route: {route_id}")
            status = str(row["status"])
            if not str(row["app_version"] or "").strip():
                raise ValueError("Verified candidate requires a non-empty app version")
            if status == "verified_candidate":
                route = self.route(route_id)
                if route is None:
                    raise RuntimeError("Verified candidate route disappeared")
                return route
            if status != "shadow":
                raise ValueError("Only a shadow route can become a verified candidate")
            if (
                int(row["trusted_sample_count"] or 0) < 1
                or int(row["success_count"] or 0) < 1
                or int(row["failure_count"] or 0) != 0
                or float(row["destination_accuracy"] or 0.0) < 1.0
                or float(row["safe_stop_rate"] or 0.0) < 1.0
                or int(row["unsafe_click_count"] or 0) != 0
                or int(row["wrong_click_count"] or 0) != 0
            ):
                raise ValueError(
                    "Verified candidate requires one clean trusted destination validation"
                )
            connection.execute(
                """
                UPDATE universal_routes
                SET status = 'verified_candidate', provisional = 1, last_seen_at = ?
                WHERE route_id = ?
                """,
                (now, route_id),
            )
            self._sync_app_function_route(connection, route_id)
            connection.commit()
        route = self.route(route_id)
        if route is None:
            raise RuntimeError("Failed to verify universal navigation route candidate")
        return route

    def bind_session_missing_app_version(
        self,
        session_id: str,
        app_version: str,
    ) -> tuple[str, str, str]:
        """Bind a clean historical session to a version that its client omitted.

        This is intentionally fill-only: an existing non-empty version can
        never be overwritten. The caller must supply independently checked
        package-version evidence before candidate verification.
        """

        normalized_version = app_version.strip()
        if not normalized_version:
            raise ValueError("A non-empty observed app version is required")
        now = _utc_now()
        with self._connection() as connection:
            session = connection.execute(
                """
                SELECT navigation.*, apps.app_package, apps.app_version, apps.locale
                FROM navigation_sessions AS navigation
                JOIN universal_apps AS apps ON apps.app_key = navigation.app_key
                WHERE navigation.session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError(f"Unknown navigation session: {session_id}")
            existing_version = str(session["app_version"] or "").strip()
            if existing_version:
                if existing_version != normalized_version:
                    raise ValueError("An existing app version cannot be overwritten")
                return (
                    str(session["app_package"]),
                    existing_version,
                    str(session["locale"]),
                )
            if (
                not bool(session["destination_correct"])
                or not bool(session["safe_stop"])
                or int(session["unsafe_click_count"] or 0) != 0
                or int(session["wrong_click_count"] or 0) != 0
            ):
                raise ValueError("Only a clean successful session can be version-bound")

            app_package = str(session["app_package"])
            locale = str(session["locale"])
            app_key = _app_key(app_package, normalized_version, locale)
            version_digest = hashlib.sha256(
                f"{app_package}|{normalized_version}|{locale.lower()}".encode("utf-8")
            ).hexdigest()[:20]
            version_signature = f"avs_{version_digest}"
            connection.execute(
                """
                INSERT INTO universal_apps (
                  app_key, app_package, app_version, locale, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_key) DO UPDATE SET last_seen_at = excluded.last_seen_at
                """,
                (app_key, app_package, normalized_version, locale, now, now),
            )
            connection.execute(
                """
                INSERT INTO app_version_signatures (
                  version_signature, app_key, app_package, app_version, locale,
                  first_screen_fingerprint, first_seen_at, last_seen_at,
                  valid_route_count, invalid_route_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
                ON CONFLICT(version_signature) DO UPDATE SET
                  last_seen_at = excluded.last_seen_at
                """,
                (
                    version_signature,
                    app_key,
                    app_package,
                    normalized_version,
                    locale,
                    str(session["start_screen_fingerprint"]),
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE navigation_sessions
                SET app_key = ?, version_signature = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (app_key, version_signature, now, session_id),
            )
            connection.execute(
                "UPDATE universal_sessions SET app_key = ?, updated_at = ? WHERE session_id = ?",
                (app_key, now, session_id),
            )
            connection.commit()
        return app_package, normalized_version, locale

    def rebuild_verified_candidate_from_session(self, session_id: str) -> StoredRoute:
        """Rebuild a complete click/Back route from one trusted device session.

        Discovery-time path pruning can intentionally remove recovery Back
        operations. A verified candidate must instead reproduce every safe
        transition that was independently checked on the device. This method
        reads only persisted semantic fingerprints and action metadata.
        """

        with self._connection() as connection:
            session = connection.execute(
                """
                SELECT navigation.*, apps.app_package, apps.app_version, apps.locale,
                  universal.goal_text
                FROM navigation_sessions AS navigation
                JOIN universal_apps AS apps ON apps.app_key = navigation.app_key
                LEFT JOIN universal_sessions AS universal
                  ON universal.session_id = navigation.session_id
                WHERE navigation.session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                raise ValueError(f"Unknown navigation session: {session_id}")
            if (
                str(session["verification_level"]) not in {"benchmark_gold", "human_gold"}
                or not bool(session["destination_correct"])
                or not bool(session["safe_stop"])
                or int(session["unsafe_click_count"] or 0) != 0
                or int(session["wrong_click_count"] or 0) != 0
            ):
                raise ValueError(
                    "Candidate reconstruction requires a clean trusted device validation"
                )
            stages = connection.execute(
                """
                SELECT * FROM navigation_stage_timings
                WHERE session_id = ? ORDER BY ordinal
                """,
                (session_id,),
            ).fetchall()
            if not stages or str(stages[-1]["phase"]) != "destination_reached":
                raise ValueError("Trusted session has no confirmed destination stage")
            action_rows: dict[tuple[str, str], sqlite3.Row] = {}
            for stage in stages:
                screen_fingerprint = str(stage["screen_fingerprint"])
                element_key_value = str(stage["selected_element_key"] or "")
                if not element_key_value:
                    continue
                action = connection.execute(
                    """
                    SELECT * FROM universal_actions
                    WHERE screen_fingerprint = ? AND element_key = ?
                    """,
                    (screen_fingerprint, element_key_value),
                ).fetchone()
                if action is not None:
                    action_rows[(screen_fingerprint, element_key_value)] = action

        steps: list[dict[str, object]] = []
        for index, stage in enumerate(stages):
            phase = str(stage["phase"])
            command = str(stage["automation_action"])
            screen_fingerprint = str(stage["screen_fingerprint"])
            element_key_value = str(stage["selected_element_key"] or "")
            next_screen = (
                str(stages[index + 1]["screen_fingerprint"])
                if index + 1 < len(stages)
                else ""
            )
            if phase == "destination_reached":
                action = action_rows.get((screen_fingerprint, element_key_value))
                if action is not None:
                    steps.append(
                        {
                            "ordinal": len(steps),
                            "kind": "click",
                            "from_screen_fingerprint": screen_fingerprint,
                            "element_key": element_key_value,
                            "label": str(action["label"]),
                            "function_ids": [str(session["target_function"])],
                            "role": str(action["role"]),
                            "risk_level": str(action["risk_level"]),
                            "expected_to_screen_fingerprint": None,
                            "terminal": True,
                            "confidence": 1.0,
                        }
                    )
                continue
            if command == "back":
                if not next_screen:
                    raise ValueError("Trusted Back stage has no observed next screen")
                steps.append(
                    {
                        "ordinal": len(steps),
                        "kind": "back",
                        "from_screen_fingerprint": screen_fingerprint,
                        "element_key": "",
                        "label": "뒤로",
                        "function_ids": [str(session["target_function"])],
                        "role": "navigation",
                        "risk_level": "low",
                        "expected_to_screen_fingerprint": next_screen,
                        "terminal": False,
                        "confidence": 1.0,
                    }
                )
                continue
            if command != "click":
                continue
            action = action_rows.get((screen_fingerprint, element_key_value))
            if action is None or not next_screen:
                raise ValueError("Trusted click stage is missing semantic action evidence")
            if str(action["risk_level"]) != "low":
                raise ValueError("Trusted candidate contains a non-low-risk automatic click")
            steps.append(
                {
                    "ordinal": len(steps),
                    "kind": "click",
                    "from_screen_fingerprint": screen_fingerprint,
                    "element_key": element_key_value,
                    "label": str(action["label"]),
                    "function_ids": [str(session["target_function"])],
                    "role": str(action["role"]),
                    "risk_level": str(action["risk_level"]),
                    "expected_to_screen_fingerprint": next_screen,
                    "terminal": False,
                    "confidence": 1.0,
                }
            )
        if not steps or not any(not bool(step.get("terminal")) for step in steps):
            raise ValueError("Trusted session produced no reusable navigation steps")
        rebuilt = self.save_route(
            app_package=str(session["app_package"]),
            app_version=str(session["app_version"]),
            locale=str(session["locale"]),
            goal_text=str(session["goal_text"] or session["target_function"]),
            target_function=str(session["target_function"]),
            start_screen_fingerprint=str(session["start_screen_fingerprint"]),
            destination_screen_fingerprint=str(session["destination_screen_fingerprint"]),
            steps=steps,
            confidence=1.0,
            provisional=True,
        )
        previous_route_id = str(session["route_id"] or "")
        with self._connection() as connection:
            connection.execute(
                "UPDATE navigation_sessions SET route_id = ?, updated_at = ? WHERE session_id = ?",
                (rebuilt.route_id, _utc_now(), session_id),
            )
            connection.commit()
        # Re-applying the already trusted truth refreshes route performance for
        # the rebuilt ID without changing its provenance.
        self.performance.apply_validation(
            session_id=session_id,
            destination_correct=True,
            safe_stop=True,
            unsafe_clicks=0,
            wrong_clicks=0,
            verification_level=str(session["verification_level"]),
        )
        verified = self.verify_route_candidate(rebuilt.route_id)
        if previous_route_id and previous_route_id != rebuilt.route_id:
            self.invalidate_route(previous_route_id)
        return verified

    def invalidate_route(self, route_id: str) -> None:
        now = _utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE universal_routes SET failure_count = failure_count + 1,
                  status = 'stale', provisional = 1, last_seen_at = ? WHERE route_id = ?
                """,
                (now, route_id),
            )
            self._sync_app_function_route(connection, route_id)
            connection.commit()
        self.performance.invalidate_route(route_id)

    def rebuild_app_function_route_index(self) -> dict[str, int]:
        """Rebuild the compact app/function serving index without deleting evidence.

        Raw observations and failed explorations remain available for learning,
        but only independently verified routes enter the serving set queried on
        the latency-sensitive navigation path.
        """

        with self._connection() as connection:
            connection.execute("DELETE FROM universal_app_function_routes")
            route_ids = [
                str(row["route_id"])
                for row in connection.execute(
                    "SELECT route_id FROM universal_routes ORDER BY route_id"
                ).fetchall()
            ]
            for route_id in route_ids:
                self._sync_app_function_route(connection, route_id)
            connection.execute("ANALYZE universal_app_function_routes")
            connection.execute("PRAGMA optimize")
            serving_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM universal_app_function_routes WHERE is_serving = 1"
                ).fetchone()[0]
            )
            function_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM (
                      SELECT app_key, target_function
                      FROM universal_app_function_routes
                      WHERE is_serving = 1
                      GROUP BY app_key, target_function
                    )
                    """
                ).fetchone()[0]
            )
            connection.commit()
        return {
            "indexed_routes": len(route_ids),
            "serving_routes": serving_count,
            "serving_app_functions": function_count,
        }

    @staticmethod
    def _sync_app_function_route(connection: sqlite3.Connection, route_id: str) -> None:
        connection.execute(
            """
            INSERT INTO universal_app_function_routes (
              route_id, app_key, function_domain, target_function,
              start_screen_fingerprint, destination_screen_fingerprint,
              lifecycle_status, lifecycle_priority, is_serving,
              step_count, confidence, updated_at
            )
            SELECT route.route_id, route.app_key,
              CASE
                WHEN instr(route.target_function, '.') > 0
                  THEN substr(route.target_function, 1, instr(route.target_function, '.') - 1)
                ELSE route.target_function
              END,
              route.target_function, route.start_screen_fingerprint,
              route.destination_screen_fingerprint, route.status,
              CASE route.status
                WHEN 'approved' THEN 2
                WHEN 'verified_candidate' THEN 1
                ELSE 0
              END,
              CASE WHEN route.status IN ('approved', 'verified_candidate') THEN 1 ELSE 0 END,
              CASE
                WHEN json_valid(route.steps_json) THEN json_array_length(route.steps_json)
                ELSE 0
              END,
              route.confidence, route.last_seen_at
            FROM universal_routes AS route
            WHERE route.route_id = ?
            ON CONFLICT(route_id) DO UPDATE SET
              app_key = excluded.app_key,
              function_domain = excluded.function_domain,
              target_function = excluded.target_function,
              start_screen_fingerprint = excluded.start_screen_fingerprint,
              destination_screen_fingerprint = excluded.destination_screen_fingerprint,
              lifecycle_status = excluded.lifecycle_status,
              lifecycle_priority = excluded.lifecycle_priority,
              is_serving = excluded.is_serving,
              step_count = excluded.step_count,
              confidence = excluded.confidence,
              updated_at = excluded.updated_at
            """,
            (route_id,),
        )

    def route_action(
        self,
        *,
        app_package: str,
        app_version: str,
        locale: str,
        target_function: str,
        screen_fingerprint: str,
    ) -> tuple[StoredRoute, dict[str, object]] | None:
        if not app_version.strip():
            # An empty version collapses every release into one unsafe scope.
            # Continue with generic exploration until the client can provide
            # an exact installed version.
            return None
        app_key = _app_key(app_package, app_version, locale)
        ranked_route_ids = self.performance.ranked_route_ids(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function=target_function,
            start_screen_fingerprint=screen_fingerprint,
        )
        if not ranked_route_ids:
            # A user may resume on an approved route's intermediate or
            # destination screen. The broader lookup still returns only
            # eligible trusted routes; it is not the former unranked fallback.
            ranked_route_ids = self.performance.ranked_route_ids(
                app_package=app_package,
                app_version=app_version,
                locale=locale,
                target_function=target_function,
            )
        ranked_route_ids = list(ranked_route_ids)
        with self._connection() as connection:
            candidate_rows = connection.execute(
                """
                SELECT route.* FROM universal_app_function_routes serving
                JOIN universal_routes route ON route.route_id = serving.route_id
                JOIN route_performance performance ON performance.route_id = route.route_id
                WHERE serving.app_key = ? AND serving.target_function = ?
                  AND serving.is_serving = 1
                  AND route.status = 'verified_candidate' AND route.provisional = 1
                  AND performance.trusted_sample_count >= 1
                  AND performance.success_count >= 1 AND performance.failure_count = 0
                  AND performance.destination_accuracy = 1.0
                  AND performance.safe_stop_rate = 1.0
                  AND performance.unsafe_click_count = 0
                  AND performance.wrong_click_count = 0
                ORDER BY performance.p90_controllable_time_ms ASC,
                  performance.p90_time_to_destination_ms ASC, route.last_seen_at DESC,
                  route.route_id
                """,
                (app_key, target_function),
            ).fetchall()
            approved_rows = []
            if ranked_route_ids:
                placeholders = ",".join("?" for _ in ranked_route_ids)
                approved_rows = connection.execute(
                    f"""
                SELECT route.* FROM universal_routes route
                JOIN universal_app_function_routes serving ON serving.route_id = route.route_id
                JOIN route_performance performance ON performance.route_id = route.route_id
                WHERE serving.app_key = ? AND serving.target_function = ?
                  AND serving.is_serving = 1
                  AND route.status = 'approved' AND route.provisional = 0
                  AND performance.eligible = 1 AND performance.under_sampled = 0
                  AND performance.trusted_sample_count >= ?
                  AND route.route_id IN ({placeholders})
                    """,
                    (
                        app_key,
                        target_function,
                        self.performance.minimum_samples,
                        *ranked_route_ids,
                    ),
                ).fetchall()
            live_action_rows = connection.execute(
                """
                SELECT element_key, role, risk_level
                FROM universal_actions
                WHERE screen_fingerprint = ?
                """,
                (screen_fingerprint,),
            ).fetchall()
        approved_by_id = {str(row["route_id"]): row for row in approved_rows}
        # Formally approved routes always outrank provisional serving
        # candidates. The latter remain an immediate, guarded fallback while
        # additional trusted samples are collected.
        rows = [
            approved_by_id[route_id]
            for route_id in ranked_route_ids
            if route_id in approved_by_id
        ] + list(candidate_rows)
        live_actions = {str(row["element_key"]): row for row in live_action_rows}
        for row in rows:
            route = _stored_route(row)
            if self.screens_semantically_match(
                route.destination_screen_fingerprint,
                screen_fingerprint,
            ):
                return route, {}
            for step in route.steps:
                if self.screens_semantically_match(
                    str(step.get("from_screen_fingerprint", "")),
                    screen_fingerprint,
                ):
                    return route, step
            # Dynamic feeds and timers can replace most of a route's *entry*
            # screen while leaving its stable low-risk gateway intact.  That
            # is useful evidence for the first reversible click, but it is not
            # sufficient evidence for an arbitrary intermediate stage: a
            # redesigned intermediate can retain one old control while its
            # meaning and next transition have changed.  Restrict key-only
            # rejoin to the first low-risk click.  Every later stage remains
            # screen-bound and a mismatch is therefore invalidated/falls back
            # in the same session.
            entry_click_step = next(
                (
                    step
                    for step in sorted(
                        route.steps,
                        key=lambda value: int(value.get("ordinal", 0)),
                    )
                    if not bool(step.get("terminal"))
                    and str(step.get("kind") or "click") == "click"
                    and str(step.get("risk_level") or "low") == "low"
                ),
                None,
            )
            for step in (() if entry_click_step is None else (entry_click_step,)):
                if (
                    bool(step.get("terminal"))
                    or str(step.get("kind") or "click") != "click"
                    or str(step.get("risk_level") or "low") != "low"
                ):
                    continue
                step_key = str(step.get("element_key") or "")
                live_action = live_actions.get(step_key)
                if live_action is None or str(live_action["risk_level"]) != "low":
                    continue
                expected_role = str(step.get("role") or "").strip().casefold()
                live_role = str(live_action["role"] or "").strip().casefold()
                if expected_role and expected_role != live_role:
                    continue
                return route, step
        return None

    def screens_semantically_match(
        self,
        expected_screen_fingerprint: str,
        actual_screen_fingerprint: str,
        *,
        minimum_similarity: float = 0.88,
    ) -> bool:
        """Compare privacy-safe semantic screen structures, never coordinates."""

        if not expected_screen_fingerprint or not actual_screen_fingerprint:
            return False
        if expected_screen_fingerprint == actual_screen_fingerprint:
            return True
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT screen_fingerprint, activity_name, title, structure_json
                FROM universal_screens
                WHERE screen_fingerprint IN (?, ?)
                """,
                (expected_screen_fingerprint, actual_screen_fingerprint),
            ).fetchall()
        by_id = {str(row["screen_fingerprint"]): row for row in rows}
        expected = by_id.get(expected_screen_fingerprint)
        actual = by_id.get(actual_screen_fingerprint)
        if expected is None or actual is None:
            return False
        return _screen_semantic_similarity(expected, actual) >= minimum_similarity

    def graph_update(self, observation: ObservationResult, app_package: str) -> UniversalNavigationGraphUpdate:
        snapshot = self.snapshot(app_package)
        return UniversalNavigationGraphUpdate(
            screen_created=observation.screen_created,
            actions_created=observation.actions_created,
            transition_recorded=observation.transition_recorded,
            known_screen_count=snapshot.screen_count,
            known_transition_count=snapshot.transition_count,
        )

    def snapshot(self, app_package: str) -> UniversalNavigationGraphResponse:
        with self._connection() as connection:
            screen_rows = connection.execute(
                """
                SELECT s.screen_fingerprint, s.activity_name, s.title, s.seen_count
                FROM universal_screens s
                JOIN universal_apps a ON a.app_key = s.app_key
                WHERE a.app_package = ?
                ORDER BY s.first_seen_at, s.screen_fingerprint
                """,
                (app_package,),
            ).fetchall()
            action_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM universal_actions actions
                JOIN universal_screens screens ON screens.screen_fingerprint = actions.screen_fingerprint
                JOIN universal_apps apps ON apps.app_key = screens.app_key
                WHERE apps.app_package = ?
                """,
                (app_package,),
            ).fetchone()[0]
            transition_rows = connection.execute(
                """
                SELECT from_screen.screen_fingerprint AS from_screen_fingerprint,
                       action.element_key, action.label,
                       transition.to_screen_fingerprint,
                       transition.success_count, transition.failure_count
                FROM universal_transitions transition
                JOIN universal_screens from_screen
                  ON from_screen.screen_fingerprint = transition.from_screen_fingerprint
                JOIN universal_apps app ON app.app_key = from_screen.app_key
                JOIN universal_actions action ON action.action_id = transition.action_id
                WHERE app.app_package = ?
                ORDER BY transition.last_seen_at, transition.transition_id
                """,
                (app_package,),
            ).fetchall()
        screens = [UniversalNavigationGraphScreen(**dict(row)) for row in screen_rows]
        transitions = [UniversalNavigationGraphTransition(**dict(row)) for row in transition_rows]
        return UniversalNavigationGraphResponse(
            app_package=app_package,
            screen_count=len(screens),
            action_count=int(action_count),
            transition_count=len(transitions),
            screens=screens,
            transitions=transitions,
        )

    def _record_transition(
        self,
        *,
        connection: sqlite3.Connection,
        request: UniversalNavigationObserveRequest,
        to_screen_fingerprint: str,
        now: str,
    ) -> tuple[bool, str | None, str | None]:
        transition = request.transition
        if transition is None:
            return False, None, None
        action_row = None
        matched_recommendation = False
        if transition.recommendation_id:
            action_row = connection.execute(
                """
                SELECT step.action_id
                FROM universal_session_steps step
                JOIN universal_actions action ON action.action_id = step.action_id
                WHERE step.recommendation_id = ?
                  AND step.session_id = ?
                  AND step.screen_fingerprint = ?
                  AND action.last_element_id = ?
                """,
                (
                    transition.recommendation_id,
                    request.session_id,
                    transition.from_screen_fingerprint,
                    transition.performed_element_id,
                ),
            ).fetchone()
            if action_row is not None and not action_row["action_id"]:
                action_row = None
            matched_recommendation = action_row is not None
        if action_row is None:
            action_row = connection.execute(
                """
                SELECT action_id FROM universal_actions
                WHERE screen_fingerprint = ? AND last_element_id = ?
                """,
                (transition.from_screen_fingerprint, transition.performed_element_id),
            ).fetchone()
        if action_row is None:
            return False, None, None
        action_id = action_row["action_id"]
        transition_id = _transition_id(transition.from_screen_fingerprint, action_id, to_screen_fingerprint)
        moved = transition.from_screen_fingerprint != to_screen_fingerprint
        effective_outcome = transition.outcome
        if effective_outcome == "navigated" and not moved:
            effective_outcome = "no_change"
        elif effective_outcome in {"no_change", "failed"} and moved:
            # The client and the observed screen disagree.  This is neither a
            # successful navigation nor a simple action failure; retain the
            # contradiction as an explicit runtime outcome for diagnosis.
            effective_outcome = "unexpected"
        success_delta = 1 if effective_outcome == "navigated" else 0
        failure_delta = 1 if effective_outcome in {"no_change", "failed", "unexpected"} else 0
        connection.execute(
            """
            INSERT INTO universal_transitions (
              transition_id, from_screen_fingerprint, action_id, to_screen_fingerprint,
              success_count, failure_count, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transition_id) DO UPDATE SET
              success_count = universal_transitions.success_count + excluded.success_count,
              failure_count = universal_transitions.failure_count + excluded.failure_count,
              last_seen_at = excluded.last_seen_at
            """,
            (
                transition_id,
                transition.from_screen_fingerprint,
                action_id,
                to_screen_fingerprint,
                success_delta,
                failure_delta,
                now,
                now,
            ),
        )
        if transition.recommendation_id and matched_recommendation:
            connection.execute(
                """
                UPDATE universal_session_steps
                SET performed = 1, outcome = ?, next_screen_fingerprint = ?
                WHERE recommendation_id = ?
                """,
                (effective_outcome, to_screen_fingerprint, transition.recommendation_id),
            )
        if failure_delta:
            session = connection.execute(
                "SELECT goal_key FROM universal_sessions WHERE session_id = ?",
                (request.session_id,),
            ).fetchone()
            if session:
                connection.execute(
                    """
                    INSERT INTO universal_action_goal_stats (
                      action_id, goal_key, success_count, failure_count, confidence, last_updated_at
                    ) VALUES (?, ?, 0, 1, 0.0, ?)
                    ON CONFLICT(action_id, goal_key) DO UPDATE SET
                      failure_count = universal_action_goal_stats.failure_count + 1,
                      last_updated_at = excluded.last_updated_at
                    """,
                    (action_id, session["goal_key"], now),
                )
        return (
            True,
            transition.recommendation_id if matched_recommendation else None,
            effective_outcome if matched_recommendation else None,
        )

    def _ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS universal_apps (
                  app_key TEXT PRIMARY KEY,
                  app_package TEXT NOT NULL,
                  app_version TEXT NOT NULL,
                  locale TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  UNIQUE(app_package, app_version, locale)
                );

                CREATE TABLE IF NOT EXISTS universal_screens (
                  screen_fingerprint TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  activity_name TEXT NOT NULL,
                  title TEXT NOT NULL,
                  structure_json TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  seen_count INTEGER NOT NULL,
                  FOREIGN KEY(app_key) REFERENCES universal_apps(app_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_actions (
                  action_id TEXT PRIMARY KEY,
                  screen_fingerprint TEXT NOT NULL,
                  element_key TEXT NOT NULL,
                  last_element_id TEXT NOT NULL,
                  label TEXT NOT NULL,
                  role TEXT NOT NULL,
                  risk_level TEXT NOT NULL,
                  risk_reason TEXT,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  seen_count INTEGER NOT NULL,
                  UNIQUE(screen_fingerprint, element_key),
                  FOREIGN KEY(screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_transitions (
                  transition_id TEXT PRIMARY KEY,
                  from_screen_fingerprint TEXT NOT NULL,
                  action_id TEXT NOT NULL,
                  to_screen_fingerprint TEXT NOT NULL,
                  success_count INTEGER NOT NULL,
                  failure_count INTEGER NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  UNIQUE(from_screen_fingerprint, action_id, to_screen_fingerprint),
                  FOREIGN KEY(from_screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE,
                  FOREIGN KEY(action_id) REFERENCES universal_actions(action_id) ON DELETE CASCADE,
                  FOREIGN KEY(to_screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_sessions (
                  session_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  goal_key TEXT NOT NULL,
                  goal_text TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(app_key) REFERENCES universal_apps(app_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_session_steps (
                  recommendation_id TEXT PRIMARY KEY,
                  session_id TEXT NOT NULL,
                  screen_fingerprint TEXT NOT NULL,
                  action_id TEXT,
                  goal_interpretation TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  decision_mode TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  performed INTEGER NOT NULL,
                  outcome TEXT NOT NULL,
                  next_screen_fingerprint TEXT,
                  created_at TEXT NOT NULL,
                  FOREIGN KEY(session_id) REFERENCES universal_sessions(session_id) ON DELETE CASCADE,
                  FOREIGN KEY(screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE,
                  FOREIGN KEY(action_id) REFERENCES universal_actions(action_id) ON DELETE SET NULL,
                  FOREIGN KEY(next_screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS universal_action_goal_stats (
                  action_id TEXT NOT NULL,
                  goal_key TEXT NOT NULL,
                  success_count INTEGER NOT NULL,
                  failure_count INTEGER NOT NULL,
                  confidence REAL NOT NULL,
                  last_updated_at TEXT NOT NULL,
                  PRIMARY KEY(action_id, goal_key),
                  FOREIGN KEY(action_id) REFERENCES universal_actions(action_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_explorations (
                  exploration_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  goal_key TEXT NOT NULL,
                  goal_text TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  status TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  current_screen_fingerprint TEXT NOT NULL,
                  destination_screen_fingerprint TEXT NOT NULL,
                  started_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  action_count INTEGER NOT NULL,
                  back_count INTEGER NOT NULL,
                  max_actions INTEGER NOT NULL,
                  max_depth INTEGER NOT NULL,
                  timeout_seconds INTEGER NOT NULL,
                  path_json TEXT NOT NULL,
                  pending_json TEXT NOT NULL,
                  route_id TEXT NOT NULL,
                  FOREIGN KEY(app_key) REFERENCES universal_apps(app_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_exploration_attempts (
                  attempt_id TEXT PRIMARY KEY,
                  exploration_id TEXT NOT NULL,
                  screen_fingerprint TEXT NOT NULL,
                  action_id TEXT NOT NULL,
                  element_key TEXT NOT NULL,
                  label TEXT NOT NULL,
                  function_ids_json TEXT NOT NULL,
                  command TEXT NOT NULL,
                  outcome TEXT NOT NULL,
                  to_screen_fingerprint TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  attempt_count INTEGER NOT NULL,
                  FOREIGN KEY(exploration_id)
                    REFERENCES universal_explorations(exploration_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_exploration_frontier (
                  frontier_id TEXT PRIMARY KEY,
                  exploration_id TEXT NOT NULL,
                  screen_fingerprint TEXT NOT NULL,
                  action_id TEXT NOT NULL,
                  element_key TEXT NOT NULL,
                  label TEXT NOT NULL,
                  function_ids_json TEXT NOT NULL,
                  goal_alignment REAL NOT NULL,
                  novelty REAL NOT NULL,
                  risk_penalty REAL NOT NULL,
                  expected_cost REAL NOT NULL,
                  source_depth INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  UNIQUE(exploration_id, screen_fingerprint, action_id),
                  FOREIGN KEY(exploration_id)
                    REFERENCES universal_explorations(exploration_id) ON DELETE CASCADE,
                  FOREIGN KEY(screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE,
                  FOREIGN KEY(action_id) REFERENCES universal_actions(action_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_routes (
                  route_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  goal_key TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  destination_screen_fingerprint TEXT NOT NULL,
                  steps_json TEXT NOT NULL,
                  confidence REAL NOT NULL,
                  provisional INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  success_count INTEGER NOT NULL,
                  failure_count INTEGER NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  FOREIGN KEY(app_key) REFERENCES universal_apps(app_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS universal_app_function_routes (
                  route_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  function_domain TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  destination_screen_fingerprint TEXT NOT NULL,
                  lifecycle_status TEXT NOT NULL,
                  lifecycle_priority INTEGER NOT NULL,
                  is_serving INTEGER NOT NULL,
                  step_count INTEGER NOT NULL,
                  confidence REAL NOT NULL,
                  updated_at TEXT NOT NULL,
                  FOREIGN KEY(route_id) REFERENCES universal_routes(route_id) ON DELETE CASCADE,
                  FOREIGN KEY(app_key) REFERENCES universal_apps(app_key) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS navigation_gold_recordings (
                  recording_id TEXT PRIMARY KEY,
                  app_key TEXT NOT NULL,
                  app_package TEXT NOT NULL,
                  app_version TEXT NOT NULL,
                  locale TEXT NOT NULL,
                  goal_key TEXT NOT NULL,
                  goal_text TEXT NOT NULL,
                  target_function TEXT NOT NULL,
                  status TEXT NOT NULL,
                  start_screen_fingerprint TEXT NOT NULL,
                  destination_screen_fingerprint TEXT,
                  destination_correct INTEGER,
                  safe_stop INTEGER,
                  reviewer TEXT,
                  review_notes TEXT,
                  started_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  completed_at TEXT,
                  FOREIGN KEY(app_key) REFERENCES universal_apps(app_key) ON DELETE CASCADE,
                  FOREIGN KEY(start_screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE,
                  FOREIGN KEY(destination_screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS navigation_gold_steps (
                  step_id TEXT PRIMARY KEY,
                  recording_id TEXT NOT NULL,
                  ordinal INTEGER NOT NULL,
                  screen_fingerprint TEXT NOT NULL,
                  screen_context_json TEXT NOT NULL,
                  candidates_json TEXT NOT NULL,
                  selected_element_id TEXT,
                  selected_element_key TEXT,
                  selected_label TEXT,
                  selected_action TEXT,
                  selected_risk_level TEXT,
                  outcome TEXT,
                  next_screen_fingerprint TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(recording_id, ordinal),
                  FOREIGN KEY(recording_id)
                    REFERENCES navigation_gold_recordings(recording_id) ON DELETE CASCADE,
                  FOREIGN KEY(screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE CASCADE,
                  FOREIGN KEY(next_screen_fingerprint)
                    REFERENCES universal_screens(screen_fingerprint) ON DELETE SET NULL
                );

                CREATE INDEX IF NOT EXISTS idx_universal_screens_app
                  ON universal_screens(app_key, last_seen_at);
                CREATE INDEX IF NOT EXISTS idx_universal_actions_screen
                  ON universal_actions(screen_fingerprint, seen_count DESC);
                CREATE INDEX IF NOT EXISTS idx_universal_transitions_from
                  ON universal_transitions(from_screen_fingerprint, success_count DESC);
                CREATE INDEX IF NOT EXISTS idx_universal_goal_stats
                  ON universal_action_goal_stats(goal_key, success_count DESC);
                CREATE INDEX IF NOT EXISTS idx_universal_exploration_attempts
                  ON universal_exploration_attempts(exploration_id, screen_fingerprint, command);
                CREATE INDEX IF NOT EXISTS idx_universal_exploration_frontier
                  ON universal_exploration_frontier(
                    exploration_id, status, goal_alignment DESC, novelty DESC,
                    risk_penalty ASC, expected_cost ASC
                  );
                CREATE INDEX IF NOT EXISTS idx_universal_routes_lookup
                  ON universal_routes(app_key, target_function, status, success_count DESC);
                CREATE INDEX IF NOT EXISTS idx_app_function_routes_serving
                  ON universal_app_function_routes(
                    app_key, target_function, is_serving,
                    lifecycle_priority DESC, confidence DESC
                  );
                CREATE INDEX IF NOT EXISTS idx_app_function_routes_category
                  ON universal_app_function_routes(app_key, function_domain, target_function);
                CREATE INDEX IF NOT EXISTS idx_navigation_gold_review
                  ON navigation_gold_recordings(status, app_package, target_function, updated_at);
                CREATE INDEX IF NOT EXISTS idx_navigation_gold_steps
                  ON navigation_gold_steps(recording_id, ordinal);
                """
            )
            # Legacy ``active`` routes were runtime-inferred and therefore do
            # not have enough provenance to be served. Migrate them into the
            # non-serving shadow lifecycle until trusted validation promotes
            # them.
            connection.execute(
                """
                UPDATE universal_routes SET status = 'shadow', provisional = 1
                WHERE status = 'active' OR status NOT IN (
                  'shadow', 'verified_candidate', 'approved', 'rejected', 'stale'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO universal_app_function_routes (
                  route_id, app_key, function_domain, target_function,
                  start_screen_fingerprint, destination_screen_fingerprint,
                  lifecycle_status, lifecycle_priority, is_serving,
                  step_count, confidence, updated_at
                )
                SELECT route.route_id, route.app_key,
                  CASE
                    WHEN instr(route.target_function, '.') > 0
                      THEN substr(route.target_function, 1, instr(route.target_function, '.') - 1)
                    ELSE route.target_function
                  END,
                  route.target_function, route.start_screen_fingerprint,
                  route.destination_screen_fingerprint, route.status,
                  CASE route.status
                    WHEN 'approved' THEN 2
                    WHEN 'verified_candidate' THEN 1
                    ELSE 0
                  END,
                  CASE WHEN route.status IN ('approved', 'verified_candidate') THEN 1 ELSE 0 END,
                  CASE
                    WHEN json_valid(route.steps_json) THEN json_array_length(route.steps_json)
                    ELSE 0
                  END,
                  route.confidence, route.last_seen_at
                FROM universal_routes AS route
                WHERE 1 = 1
                ON CONFLICT(route_id) DO UPDATE SET
                  app_key = excluded.app_key,
                  function_domain = excluded.function_domain,
                  target_function = excluded.target_function,
                  start_screen_fingerprint = excluded.start_screen_fingerprint,
                  destination_screen_fingerprint = excluded.destination_screen_fingerprint,
                  lifecycle_status = excluded.lifecycle_status,
                  lifecycle_priority = excluded.lifecycle_priority,
                  is_serving = excluded.is_serving,
                  step_count = excluded.step_count,
                  confidence = excluded.confidence,
                  updated_at = excluded.updated_at
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()


def get_universal_navigation_repository(
    settings: Settings | None = None,
) -> UniversalNavigationGraphRepository:
    settings = settings or get_settings()
    configured = settings.navigation_graph_db_path.strip()
    path = Path(configured).expanduser() if configured else DEFAULT_DATABASE_PATH
    if not path.is_absolute():
        path = ROOT / path
    return _cached_repository(str(path.resolve()))


@lru_cache
def _cached_repository(path: str) -> UniversalNavigationGraphRepository:
    return UniversalNavigationGraphRepository(Path(path))


def fingerprint_screen(app_package: str, screen: UniversalNavigationScreen) -> str:
    structural_items = []
    for element in screen.elements:
        if element.password or not element.visible or element.view_id == "exitguide:ocr":
            continue
        label = sanitize_text(element.text or element.content_description or "")
        structural_items.append(
            "|".join(
                (
                    element.role,
                    "1" if element.clickable else "0",
                    "1" if element.enabled else "0",
                    "1" if element.scrollable else "0",
                    "1" if element.checkable else "0",
                    "1" if element.checked else "0",
                    "1" if element.selected else "0",
                    label[:120],
                )
            )
        )
    payload = json.dumps(
        {
            "package": app_package,
            "activity": sanitize_text(screen.activity_name),
            # Accessibility node IDs and resource IDs may change between renders or
            # app versions. The reusable identity therefore follows ordered,
            # privacy-sanitized semantics rather than volatile implementation IDs.
            "elements": structural_items[:250],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return f"us_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def fingerprint_goal(goal_text: str) -> str:
    normalized = "".join(re.findall(r"[0-9A-Za-z가-힣]+", sanitize_text(goal_text).lower()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def element_key(candidate: UniversalNavigationCandidate) -> str:
    return candidate.element_key


def sanitize_text(value: str | None) -> str:
    text = " ".join((value or "").strip().split())
    text = EMAIL_PATTERN.sub("[email]", text)
    text = PHONE_PATTERN.sub("[phone]", text)
    text = LONG_NUMBER_PATTERN.sub("[number]", text)
    text = TOKEN_PATTERN.sub("[secret]", text)
    return text[:500]


def _infer_gold_row_click(
    stored_candidates: object,
    destination_elements: list[UniversalNavigationElement],
) -> dict[str, object] | None:
    """Recover a custom list-row click exposed by Android as a scroll event.

    A few RecyclerView implementations omit TYPE_VIEW_CLICKED for a tapped
    row. Recovery is intentionally conservative: the new screen's first
    semantic title must identify exactly one low-risk clickable candidate on
    the preceding screen. Ordinary list scrolling has no unique match and is
    kept as ``scroll_forward``.
    """

    chrome_labels = {
        "back",
        "go back",
        "navigate up",
        "뒤로",
        "뒤로 가기",
        "위로 이동",
    }
    destination_title = ""
    for element in destination_elements[:24]:
        label = sanitize_text(element.content_description or element.text)
        if label and label.casefold() not in chrome_labels:
            destination_title = label
            break
    if not destination_title or not isinstance(stored_candidates, list):
        return None

    matches: list[dict[str, object]] = []
    for candidate in stored_candidates:
        if not isinstance(candidate, dict):
            continue
        label = sanitize_text(str(candidate.get("label", "")))
        if (
            label.casefold() == destination_title.casefold()
            and str(candidate.get("role", "")) in {"button", "image", "link"}
            and str(candidate.get("risk_level", "blocked")) == "low"
        ):
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _semantic_token(value: object) -> str:
    return "".join(
        re.findall(
            r"[0-9A-Za-z가-힣]+",
            sanitize_text("" if value is None else str(value)).casefold(),
        )
    )


def _semantic_structure_features(raw: object) -> set[str]:
    try:
        items = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        return set()
    features: set[str] = set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        role = _semantic_token(item.get("role")) or "unknown"
        label = _semantic_token(item.get("label"))
        view_id = _semantic_token(item.get("view_id"))
        state = "".join(
            (
                "c" if bool(item.get("clickable")) else "-",
                "s" if bool(item.get("scrollable")) else "-",
            )
        )
        # Structural role/state survives copy and ordering changes. Human-facing
        # text or resource IDs provide meaning when present, without coordinates.
        features.add(f"shape:{role}:{state}")
        if label:
            features.add(f"label:{role}:{state}:{label}")
        elif view_id:
            features.add(f"view:{role}:{state}:{view_id}")
    return features


def _set_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _screen_semantic_similarity(expected: sqlite3.Row, actual: sqlite3.Row) -> float:
    expected_activity = _semantic_token(expected["activity_name"])
    actual_activity = _semantic_token(actual["activity_name"])
    activity_score = float(
        bool(expected_activity)
        and bool(actual_activity)
        and (
            expected_activity == actual_activity
            or expected_activity in actual_activity
            or actual_activity in expected_activity
        )
    )
    expected_title = _semantic_token(expected["title"])
    actual_title = _semantic_token(actual["title"])
    title_score = float(
        bool(expected_title)
        and bool(actual_title)
        and (
            expected_title == actual_title
            or expected_title in actual_title
            or actual_title in expected_title
        )
    )
    structure_score = _set_similarity(
        _semantic_structure_features(expected["structure_json"]),
        _semantic_structure_features(actual["structure_json"]),
    )
    return activity_score * 0.25 + title_score * 0.20 + structure_score * 0.55


def _screen_structure_json(screen: UniversalNavigationScreen) -> str:
    structure = [
        {
            "parent_id": element.parent_id,
            "view_id": sanitize_text(element.view_id),
            "role": element.role,
            "clickable": element.clickable,
            "scrollable": element.scrollable,
            "label": "" if element.password else sanitize_text(element.text or element.content_description),
        }
        for element in screen.elements
        if element.visible
    ]
    return json.dumps(structure[:250], ensure_ascii=False, separators=(",", ":"))


def _screen_title(screen: UniversalNavigationScreen) -> str:
    for element in screen.elements:
        if element.role in {"heading", "title"} and not element.password:
            label = sanitize_text(element.text or element.content_description)
            if label:
                return label
    return sanitize_text(screen.activity_name) or "알 수 없는 화면"


def _stored_action(row: sqlite3.Row) -> StoredAction:
    return StoredAction(
        action_id=row["action_id"],
        screen_fingerprint=row["screen_fingerprint"],
        element_key=row["element_key"],
        last_element_id=row["last_element_id"],
        label=row["label"],
        role=row["role"],
        risk_level=row["risk_level"],
        risk_reason=row["risk_reason"],
    )


def _stored_route(row: sqlite3.Row) -> StoredRoute:
    try:
        steps = json.loads(row["steps_json"] or "[]")
    except json.JSONDecodeError:
        steps = []
    return StoredRoute(
        route_id=row["route_id"],
        app_key=row["app_key"],
        goal_key=row["goal_key"],
        target_function=row["target_function"],
        start_screen_fingerprint=row["start_screen_fingerprint"],
        destination_screen_fingerprint=row["destination_screen_fingerprint"],
        provisional=bool(row["provisional"]),
        lifecycle_status=str(row["status"]),
        confidence=float(row["confidence"]),
        steps=tuple(step for step in steps if isinstance(step, dict)),
    )


def _exploration_state(row: sqlite3.Row) -> ExplorationState:
    try:
        path = json.loads(row["path_json"] or "[]")
    except json.JSONDecodeError:
        path = []
    try:
        pending = json.loads(row["pending_json"]) if row["pending_json"] else None
    except json.JSONDecodeError:
        pending = None
    return ExplorationState(
        exploration_id=row["exploration_id"],
        app_key=row["app_key"],
        goal_key=row["goal_key"],
        goal_text=row["goal_text"],
        target_function=row["target_function"],
        status=row["status"],
        start_screen_fingerprint=row["start_screen_fingerprint"],
        current_screen_fingerprint=row["current_screen_fingerprint"],
        destination_screen_fingerprint=row["destination_screen_fingerprint"],
        started_at=row["started_at"],
        updated_at=row["updated_at"],
        action_count=int(row["action_count"]),
        back_count=int(row["back_count"]),
        max_actions=int(row["max_actions"]),
        max_depth=int(row["max_depth"]),
        timeout_seconds=int(row["timeout_seconds"]),
        path=tuple(step for step in path if isinstance(step, dict)),
        pending=pending if isinstance(pending, dict) else None,
        route_id=row["route_id"],
    )


def _frontier_item(row: sqlite3.Row) -> ExplorationFrontierItem:
    try:
        function_ids = json.loads(row["function_ids_json"] or "[]")
    except json.JSONDecodeError:
        function_ids = []
    return ExplorationFrontierItem(
        frontier_id=str(row["frontier_id"]),
        exploration_id=str(row["exploration_id"]),
        screen_fingerprint=str(row["screen_fingerprint"]),
        action_id=str(row["action_id"]),
        element_key=str(row["element_key"]),
        label=str(row["label"]),
        function_ids=tuple(
            sorted(str(value) for value in function_ids if isinstance(value, str))
        ),
        goal_alignment=float(row["goal_alignment"]),
        novelty=float(row["novelty"]),
        risk_penalty=float(row["risk_penalty"]),
        expected_cost=float(row["expected_cost"]),
        source_depth=int(row["source_depth"]),
        status=str(row["status"]),
        first_seen_at=str(row["first_seen_at"]),
    )


def _app_key(app_package: str, app_version: str, locale: str) -> str:
    payload = f"{app_package}|{app_version}|{locale.lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _action_id(screen_fingerprint: str, element_key_value: str) -> str:
    payload = f"{screen_fingerprint}|{element_key_value}"
    return f"ua_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _transition_id(from_screen: str, action_id: str, to_screen: str) -> str:
    payload = f"{from_screen}|{action_id}|{to_screen}"
    return f"ut_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
