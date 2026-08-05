from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import PolicyDecision, ProcedureSelection


STORE_SCHEMA_VERSION = "1.1"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS extension_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_run_id TEXT NOT NULL,
    task_case_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL CHECK (attempt_index >= 0),
    memory_profile TEXT NOT NULL,
    procedure_profile TEXT NOT NULL,
    verifier_profile TEXT NOT NULL,
    app_package TEXT NOT NULL,
    app_version TEXT NOT NULL,
    goal_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'failed', 'aborted')),
    success INTEGER,
    outcome TEXT NOT NULL DEFAULT 'unknown',
    within_attempt_recoveries INTEGER NOT NULL DEFAULT 0,
    total_actions INTEGER,
    llm_calls INTEGER,
    false_finish INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(task_run_id, attempt_index)
);

CREATE TABLE IF NOT EXISTS procedure_invocations (
    invocation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    procedure_id TEXT NOT NULL,
    generation_id TEXT NOT NULL,
    bound_parameters_json TEXT NOT NULL,
    selection_score REAL NOT NULL,
    selection_reason TEXT NOT NULL,
    current_step_ordinal INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'failed', 'aborted')),
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_procedure_per_session
ON procedure_invocations(session_id) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS procedure_step_events (
    event_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL REFERENCES procedure_invocations(invocation_id),
    decision_id TEXT,
    observation_id TEXT,
    previous_step_ordinal INTEGER NOT NULL,
    current_step_ordinal INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('selected', 'observed', 'advanced', 'completed', 'failed', 'aborted')
    ),
    reason TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_retrieval_events (
    retrieval_id TEXT PRIMARY KEY,
    task_run_id TEXT,
    session_id TEXT NOT NULL,
    decision_id TEXT,
    evidence_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    rank INTEGER NOT NULL CHECK (rank >= 0),
    score REAL,
    applicable INTEGER,
    used INTEGER NOT NULL DEFAULT 0,
    changed_action INTEGER,
    outcome_effect TEXT NOT NULL DEFAULT 'unknown' CHECK (
        outcome_effect IN ('improved', 'neutral', 'harmed', 'unknown')
    ),
    stale INTEGER,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verifier_decisions (
    verifier_event_id TEXT PRIMARY KEY,
    task_run_id TEXT,
    session_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    verdict TEXT NOT NULL,
    rule_ids_json TEXT NOT NULL,
    planner_action_json TEXT NOT NULL,
    grounding_status TEXT NOT NULL,
    grounding_reason TEXT NOT NULL,
    proposed_action_json TEXT NOT NULL,
    grounded_action_json TEXT NOT NULL,
    policy_action_json TEXT NOT NULL,
    actual_action_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    missing_facts_json TEXT NOT NULL,
    obligations_json TEXT NOT NULL,
    confirmation_id TEXT,
    latency_ms REAL NOT NULL,
    shadow INTEGER NOT NULL,
    evaluator_label TEXT CHECK (
        evaluator_label IS NULL OR evaluator_label IN ('correct_allow', 'correct_block', 'false_allow', 'false_block')
    ),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_interventions (
    intervention_id TEXT PRIMARY KEY,
    task_run_id TEXT,
    session_id TEXT NOT NULL,
    decision_id TEXT,
    kind TEXT NOT NULL CHECK (
        kind IN ('confirmation', 'correction', 'goal_rephrase', 'manual_override', 'stop')
    ),
    reason_code TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confirmation_challenges (
    confirmation_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    action_digest TEXT NOT NULL,
    nonce TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'consumed', 'expired', 'cancelled')),
    confirmation_source TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    confirmed_at TEXT,
    consumed_at TEXT
);

CREATE INDEX IF NOT EXISTS attempts_case_idx
ON task_attempts(task_case_id, attempt_index);
CREATE INDEX IF NOT EXISTS retrieval_session_idx
ON memory_retrieval_events(session_id, decision_id);
CREATE INDEX IF NOT EXISTS verifier_session_idx
ON verifier_decisions(session_id, decision_id);
CREATE INDEX IF NOT EXISTS intervention_session_idx
ON user_interventions(session_id, decision_id);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _action_digest(session_id: str, action: Mapping[str, Any]) -> str:
    canonical = _json({"session_id": session_id, "action": dict(action)})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class NavigationEvaluationStore:
    """Append-only extension evidence kept outside the existing runtime DB."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT INTO extension_metadata(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (STORE_SCHEMA_VERSION,),
            )

    def status(self) -> dict[str, Any]:
        tables = (
            "task_attempts",
            "procedure_invocations",
            "procedure_step_events",
            "memory_retrieval_events",
            "verifier_decisions",
            "user_interventions",
            "confirmation_challenges",
        )
        with self._lock, self._connection() as connection:
            counts = {
                table: int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
                for table in tables
            }
        return {"schema_version": STORE_SCHEMA_VERSION, "path": str(self.path), "counts": counts}

    def start_attempt(
        self,
        *,
        task_run_id: str,
        task_case_id: str,
        session_id: str,
        attempt_index: int,
        memory_profile: str,
        procedure_profile: str,
        verifier_profile: str,
        app_package: str,
        app_version: str,
        goal_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if attempt_index < 0:
            raise ValueError("attempt_index must be non-negative")
        attempt_id = f"nava_{uuid.uuid4().hex}"
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO task_attempts(
                    attempt_id, task_run_id, task_case_id, session_id, attempt_index,
                    memory_profile, procedure_profile, verifier_profile,
                    app_package, app_version, goal_id, status, metadata_json, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    attempt_id,
                    task_run_id,
                    task_case_id,
                    session_id,
                    attempt_index,
                    memory_profile,
                    procedure_profile,
                    verifier_profile,
                    app_package,
                    app_version,
                    goal_id,
                    _json(dict(metadata or {})),
                    utc_now(),
                ),
            )
        return attempt_id

    def finish_attempt(
        self,
        attempt_id: str,
        *,
        success: bool,
        outcome: str,
        within_attempt_recoveries: int,
        total_actions: int,
        llm_calls: int,
        false_finish: bool = False,
    ) -> None:
        if min(within_attempt_recoveries, total_actions, llm_calls) < 0:
            raise ValueError("attempt counters must be non-negative")
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE task_attempts
                   SET status = ?, success = ?, outcome = ?,
                       within_attempt_recoveries = ?, total_actions = ?, llm_calls = ?,
                       false_finish = ?, finished_at = ?
                 WHERE attempt_id = ? AND status = 'active'
                """,
                (
                    "completed" if success else "failed",
                    int(success),
                    outcome,
                    within_attempt_recoveries,
                    total_actions,
                    llm_calls,
                    int(false_finish),
                    utc_now(),
                    attempt_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(attempt_id)

    def active_procedure(self, session_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM procedure_invocations WHERE session_id = ? AND status = 'active'",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["bound_parameters"] = json.loads(result.pop("bound_parameters_json"))
        return result

    def begin_procedure(
        self,
        *,
        session_id: str,
        selection: ProcedureSelection,
        facts: Mapping[str, Any],
    ) -> str:
        existing = self.active_procedure(session_id)
        if existing is not None:
            if existing["procedure_id"] == selection.procedure.procedure_id:
                return str(existing["invocation_id"])
            raise ValueError(f"session already has active procedure: {session_id}")
        invocation_id = f"navp_{uuid.uuid4().hex}"
        now = utc_now()
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO procedure_invocations(
                    invocation_id, session_id, procedure_id, generation_id,
                    bound_parameters_json, selection_score, selection_reason,
                    current_step_ordinal, status, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?)
                """,
                (
                    invocation_id,
                    session_id,
                    selection.procedure.procedure_id,
                    selection.procedure.generation_id,
                    _json(selection.parameters),
                    selection.score,
                    selection.reason,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO procedure_step_events(
                    event_id, invocation_id, previous_step_ordinal,
                    current_step_ordinal, event_type, reason, facts_json, created_at
                ) VALUES (?, ?, 0, 0, 'selected', ?, ?, ?)
                """,
                (
                    f"navpe_{uuid.uuid4().hex}",
                    invocation_id,
                    selection.reason,
                    _json(dict(facts)),
                    now,
                ),
            )
        return invocation_id

    def record_procedure_observation(
        self,
        *,
        invocation_id: str,
        decision_id: str | None,
        observation_id: str | None,
        previous_step_ordinal: int,
        current_step_ordinal: int,
        event_type: str,
        reason: str,
        facts: Mapping[str, Any],
    ) -> None:
        allowed = {"observed", "advanced", "completed", "failed", "aborted"}
        if event_type not in allowed:
            raise ValueError(f"invalid procedure event type: {event_type}")
        now = utc_now()
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE procedure_invocations
                   SET current_step_ordinal = ?, status = ?, updated_at = ?,
                       completed_at = CASE WHEN ? IN ('completed', 'failed', 'aborted') THEN ? ELSE completed_at END
                 WHERE invocation_id = ? AND status = 'active'
                """,
                (
                    current_step_ordinal,
                    event_type if event_type in {"completed", "failed", "aborted"} else "active",
                    now,
                    event_type,
                    now,
                    invocation_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(invocation_id)
            connection.execute(
                """
                INSERT INTO procedure_step_events(
                    event_id, invocation_id, decision_id, observation_id,
                    previous_step_ordinal, current_step_ordinal,
                    event_type, reason, facts_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"navpe_{uuid.uuid4().hex}",
                    invocation_id,
                    decision_id,
                    observation_id,
                    previous_step_ordinal,
                    current_step_ordinal,
                    event_type,
                    reason,
                    _json(dict(facts)),
                    now,
                ),
            )

    def record_memory_retrievals(
        self,
        *,
        session_id: str,
        decision_id: str | None,
        task_run_id: str | None,
        rows: Sequence[Mapping[str, Any]],
    ) -> tuple[str, ...]:
        now = utc_now()
        retrieval_ids: list[str] = []
        with self._lock, self._connection() as connection:
            for rank, row in enumerate(rows):
                retrieval_id = f"navr_{uuid.uuid4().hex}"
                connection.execute(
                    """
                    INSERT INTO memory_retrieval_events(
                        retrieval_id, task_run_id, session_id, decision_id,
                        evidence_id, source_type, rank, score, applicable, used,
                        changed_action, outcome_effect, stale, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        retrieval_id,
                        task_run_id,
                        session_id,
                        decision_id,
                        str(row["evidence_id"]),
                        str(row.get("source_type", "unknown")),
                        int(row.get("rank", rank)),
                        row.get("score"),
                        _optional_bool(row.get("applicable")),
                        int(bool(row.get("used", False))),
                        _optional_bool(row.get("changed_action")),
                        str(row.get("outcome_effect", "unknown")),
                        _optional_bool(row.get("stale")),
                        _json(dict(row.get("metadata", {}))),
                        now,
                    ),
                )
                retrieval_ids.append(retrieval_id)
        return tuple(retrieval_ids)

    def label_memory_retrieval(
        self,
        retrieval_id: str,
        *,
        applicable: bool,
        changed_action: bool | None,
        outcome_effect: str,
        stale: bool | None = None,
    ) -> None:
        if outcome_effect not in {"improved", "neutral", "harmed", "unknown"}:
            raise ValueError(f"invalid memory outcome effect: {outcome_effect}")
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_retrieval_events
                   SET applicable = ?, changed_action = ?, outcome_effect = ?, stale = ?
                 WHERE retrieval_id = ?
                """,
                (
                    int(applicable),
                    _optional_bool(changed_action),
                    outcome_effect,
                    _optional_bool(stale),
                    retrieval_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(retrieval_id)

    def record_verifier_decision(
        self,
        *,
        session_id: str,
        decision_id: str,
        task_run_id: str | None,
        decision: PolicyDecision,
        actual_action: Mapping[str, Any],
    ) -> str:
        event_id = f"navv_{uuid.uuid4().hex}"
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO verifier_decisions(
                    verifier_event_id, task_run_id, session_id, decision_id,
                    policy_version, verdict, rule_ids_json,
                    planner_action_json, grounding_status, grounding_reason,
                    proposed_action_json, grounded_action_json,
                    policy_action_json, actual_action_json,
                    reason, missing_facts_json, obligations_json, confirmation_id,
                    latency_ms, shadow, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    task_run_id,
                    session_id,
                    decision_id,
                    decision.policy_version,
                    decision.verdict.value,
                    _json(decision.rule_ids),
                    _json(decision.planner_action),
                    decision.grounding_status,
                    decision.grounding_reason,
                    _json(decision.proposed_action),
                    _json(decision.grounded_action),
                    _json(decision.final_action),
                    _json(dict(actual_action)),
                    decision.reason,
                    _json(decision.missing_facts),
                    _json(decision.obligations),
                    decision.confirmation_id,
                    decision.latency_ms,
                    int(decision.shadow),
                    utc_now(),
                ),
            )
        return event_id

    def label_verifier_decision(self, verifier_event_id: str, label: str) -> None:
        allowed = {"correct_allow", "correct_block", "false_allow", "false_block"}
        if label not in allowed:
            raise ValueError(f"invalid verifier label: {label}")
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "UPDATE verifier_decisions SET evaluator_label = ? WHERE verifier_event_id = ?",
                (label, verifier_event_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(verifier_event_id)

    def record_user_intervention(
        self,
        *,
        session_id: str,
        kind: str,
        reason_code: str,
        decision_id: str | None = None,
        task_run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        allowed = {"confirmation", "correction", "goal_rephrase", "manual_override", "stop"}
        if kind not in allowed:
            raise ValueError(f"invalid user intervention kind: {kind}")
        intervention_id = f"navu_{uuid.uuid4().hex}"
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO user_interventions(
                    intervention_id, task_run_id, session_id, decision_id,
                    kind, reason_code, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intervention_id,
                    task_run_id,
                    session_id,
                    decision_id,
                    kind,
                    reason_code,
                    _json(dict(metadata or {})),
                    utc_now(),
                ),
            )
        return intervention_id

    def create_confirmation_challenge(
        self,
        *,
        session_id: str,
        action: Mapping[str, Any],
        ttl_seconds: int = 300,
    ) -> str:
        if not 1 <= ttl_seconds <= 900:
            raise ValueError("confirmation ttl_seconds must be between 1 and 900")
        confirmation_id = f"navc_{uuid.uuid4().hex}"
        created = datetime.now(timezone.utc)
        expires = created + timedelta(seconds=ttl_seconds)
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO confirmation_challenges(
                    confirmation_id, session_id, action_digest, nonce, status,
                    created_at, expires_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    confirmation_id,
                    session_id,
                    _action_digest(session_id, action),
                    secrets.token_urlsafe(24),
                    created.isoformat(),
                    expires.isoformat(),
                ),
            )
        return confirmation_id

    def confirm_challenge(
        self,
        confirmation_id: str,
        *,
        source: str,
        session_id: str,
        action: Mapping[str, Any],
    ) -> None:
        if source != "native_ui":
            raise ValueError("only native_ui may confirm a navigation action")
        now = datetime.now(timezone.utc)
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM confirmation_challenges WHERE confirmation_id = ?",
                (confirmation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(confirmation_id)
            if row["status"] != "pending":
                raise ValueError("confirmation challenge is not pending")
            if row["session_id"] != session_id or row["action_digest"] != _action_digest(
                session_id, action
            ):
                raise ValueError("confirmation challenge does not match session and action")
            if datetime.fromisoformat(str(row["expires_at"])) <= now:
                connection.execute(
                    "UPDATE confirmation_challenges SET status = 'expired' WHERE confirmation_id = ?",
                    (confirmation_id,),
                )
                raise ValueError("confirmation challenge expired")
            connection.execute(
                """
                UPDATE confirmation_challenges
                   SET status = 'confirmed', confirmation_source = ?, confirmed_at = ?
                 WHERE confirmation_id = ?
                """,
                (source, now.isoformat(), confirmation_id),
            )
            connection.execute(
                """
                INSERT INTO user_interventions(
                    intervention_id, task_run_id, session_id, decision_id,
                    kind, reason_code, metadata_json, created_at
                ) VALUES (?, NULL, ?, NULL, 'confirmation', 'native_action_confirmation', ?, ?)
                """,
                (
                    f"navu_{uuid.uuid4().hex}",
                    session_id,
                    _json({"confirmation_id": confirmation_id}),
                    now.isoformat(),
                ),
            )

    def consume_confirmation(
        self,
        confirmation_id: str | None,
        *,
        session_id: str,
        action: Mapping[str, Any],
    ) -> bool:
        if not confirmation_id:
            return False
        now = datetime.now(timezone.utc)
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM confirmation_challenges WHERE confirmation_id = ?",
                (confirmation_id,),
            ).fetchone()
            if row is None or row["status"] != "confirmed":
                return False
            valid = (
                row["session_id"] == session_id
                and row["confirmation_source"] == "native_ui"
                and row["action_digest"] == _action_digest(session_id, action)
                and datetime.fromisoformat(str(row["expires_at"])) > now
            )
            if not valid:
                return False
            connection.execute(
                """
                UPDATE confirmation_challenges
                   SET status = 'consumed', consumed_at = ?
                 WHERE confirmation_id = ? AND status = 'confirmed'
                """,
                (now.isoformat(), confirmation_id),
            )
            return True

    def summary(self) -> dict[str, Any]:
        with self._lock, self._connection() as connection:
            first = connection.execute(
                """
                SELECT count(*) AS total, coalesce(sum(success), 0) AS success
                  FROM task_attempts
                 WHERE attempt_index = 0 AND status IN ('completed', 'failed')
                """
            ).fetchone()
            retry = connection.execute(
                """
                SELECT count(*) AS total, coalesce(sum(success), 0) AS success
                  FROM (
                    SELECT task_run_id, max(coalesce(success, 0)) AS success
                      FROM task_attempts
                     WHERE attempt_index <= 1 AND status IN ('completed', 'failed')
                     GROUP BY task_run_id
                  )
                """
            ).fetchone()
            retrieval = connection.execute(
                """
                SELECT
                  sum(CASE WHEN applicable IS NOT NULL THEN 1 ELSE 0 END) AS labeled,
                  sum(CASE WHEN applicable = 0 THEN 1 ELSE 0 END) AS false_recall,
                  sum(CASE WHEN used = 1 AND outcome_effect = 'harmed' THEN 1 ELSE 0 END) AS harmful
                FROM memory_retrieval_events
                """
            ).fetchone()
            corrections = int(
                connection.execute(
                    """
                    SELECT count(*) FROM user_interventions
                     WHERE kind IN ('correction', 'goal_rephrase', 'manual_override')
                    """
                ).fetchone()[0]
            )
            confirmations = int(
                connection.execute(
                    "SELECT count(*) FROM user_interventions WHERE kind = 'confirmation'"
                ).fetchone()[0]
            )
            verifier_rows = connection.execute(
                "SELECT verdict, count(*) AS count FROM verifier_decisions GROUP BY verdict"
            ).fetchall()
            labels = connection.execute(
                """
                SELECT evaluator_label, count(*) AS count FROM verifier_decisions
                 WHERE evaluator_label IS NOT NULL GROUP BY evaluator_label
                """
            ).fetchall()
        return {
            "first_attempt": _rate_row(first),
            "within_one_retry": _rate_row(retry),
            "memory": {
                "labeled_retrievals": int(retrieval["labeled"] or 0),
                "false_recall_count": int(retrieval["false_recall"] or 0),
                "harmful_recall_count": int(retrieval["harmful"] or 0),
                "false_recall_rate": _ratio(retrieval["false_recall"], retrieval["labeled"]),
            },
            "user": {"corrections": corrections, "confirmations": confirmations},
            "verifier": {
                "verdict_counts": {str(row["verdict"]): int(row["count"]) for row in verifier_rows},
                "label_counts": {
                    str(row["evaluator_label"]): int(row["count"]) for row in labels
                },
            },
        }


def _optional_bool(value: Any) -> int | None:
    if value is None:
        return None
    return int(bool(value))


def _ratio(numerator: Any, denominator: Any) -> float | None:
    denominator_value = int(denominator or 0)
    if denominator_value == 0:
        return None
    return round(int(numerator or 0) / denominator_value, 4)


def _rate_row(row: sqlite3.Row) -> dict[str, Any]:
    total = int(row["total"] or 0)
    success = int(row["success"] or 0)
    return {"total": total, "success": success, "rate": _ratio(success, total)}
