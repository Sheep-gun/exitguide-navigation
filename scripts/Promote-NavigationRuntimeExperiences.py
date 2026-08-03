from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.navigation_contracts import ScreenObservation  # noqa: E402
from app.services.navigation_decision_memory import redact_text, tokenize  # noqa: E402
from app.services.navigation_runtime_store import _screen_payload  # noqa: E402
from app.services.shared_contract_validation import (  # noqa: E402
    validate_app_knowledge,
    validate_interaction_episode,
    validate_knowledge_promotion,
)


GENERATOR_NAME = "exitguide.runtime-action-unit-promoter"
GENERATOR_VERSION = "2.0.0"
SHARED_CONTRACTS = ROOT / "db" / "contracts" / "shared_app_knowledge_v0_9_1"
INTERACTION_CONTRACT = SHARED_CONTRACTS / "interaction-episode.v1.json"
APP_KNOWLEDGE_CONTRACT = SHARED_CONTRACTS / "app-knowledge.v1.json"
GENERATION_CONTRACT = SHARED_CONTRACTS / "app-knowledge-generation.v1.schema.json"
CROSSWALK_PATH = SHARED_CONTRACTS / "navigation-goal-crosswalk.v1.json"
GENERIC_REVERSE_MARKERS = (
    "위로 이동",
    "뒤로",
    "이전 화면",
    "navigate up",
    "navigate_up",
    "go back",
)
POSITIVE_PROGRESS = {"advanced", "reached"}
ELIGIBLE_ACTIONS = {"click", "scroll"}
FAILURE_OUTCOMES = {"wrong_destination", "external_app", "infinite_feed", "no_change"}
RECOVERY_ACTIONS = {"back", "scroll", "wait_and_observe", "stop_for_user"}
REWARD_BY_PROGRESS = {
    "reached": 1.0,
    "advanced": 0.5,
    "unchanged": 0.0,
    "regressed": -0.5,
    "unknown": None,
}


def episode_end_reason(session_status: object) -> str:
    normalized = normalize(session_status)
    if normalized in {"reached", "destination_reached", "completed"}:
        return "destination_reached"
    if normalized in {"stopped_for_user", "user_handoff"}:
        return "user_handoff"
    if normalized in {"failed", "error"}:
        return "failed"
    return "truncated"


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def rfc3339(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("source timestamp is required")
    text = text.replace(" ", "T", 1)
    if text.endswith("Z") or (
        len(text) >= 6 and text[-6] in {"+", "-"} and text[-3] == ":"
    ):
        return text
    return f"{text}+00:00"


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_payload(path: Path, *, root: Path, record_count: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "byte_size": path.stat().st_size,
    }
    if record_count is not None:
        payload["record_count"] = record_count
    return payload


def validate_json_schema(payload: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    validator = Draft202012Validator(contract, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        details = "; ".join(
            f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors[:12]
        )
        raise ValueError(details)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    write_json(temporary, payload)
    os.replace(temporary, path)


def goal_crosswalk() -> dict[str, str]:
    payload = load_contract(CROSSWALK_PATH)
    return {
        str(item["source_goal_id"]): str(item["target_goal_id"])
        for item in payload.get("mappings", [])
        if item.get("mapping_type") == "exact"
    }


def load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sanitized_screen(raw: str) -> dict[str, Any]:
    model = ScreenObservation.model_validate(json.loads(raw))
    return _screen_payload(model)


def selected_candidate(screen: Mapping[str, Any], candidate_id: str | None) -> dict[str, Any] | None:
    if not candidate_id:
        return None
    return next(
        (
            dict(candidate)
            for candidate in screen.get("candidates", [])
            if candidate.get("candidate_id") == candidate_id
        ),
        None,
    )


def candidate_semantics(candidate: Mapping[str, Any] | None) -> str:
    if not candidate:
        return ""
    return normalize(
        " ".join(
            str(candidate.get(field, ""))
            for field in (
                "label",
                "icon_semantics",
                "child_semantics",
                "parent_semantics",
                "nearby_text",
            )
        )
    )


def action_group_key(row: Mapping[str, Any]) -> str:
    action = str(row["action_name"])
    if action == "scroll":
        return ":".join(
            (str(row["goal_id"]), action, str(row["scroll_direction"]), str(row["plan_stage"]))
        )
    candidate = row.get("selected_candidate")
    if not isinstance(candidate, Mapping):
        return ""
    identity = normalize(
        candidate.get("label")
        or candidate.get("icon_semantics")
        or candidate.get("child_semantics")
        or candidate.get("role")
    )
    # K2 stage labels are planner state, not part of the observed decision
    # identity. The same grounded control can be classified as hub_discovery
    # in one run and destination_entry in another while producing the same
    # verified transition. Keep stage as evidence metadata, but do not split
    # repeated click support by model-plan wording.
    return ":".join((str(row["goal_id"]), action, identity))


def recovery_group_key(row: Mapping[str, Any]) -> str:
    return ":".join(
        (
            action_group_key(row),
            normalize(row.get("failure_class") or row.get("outcome_type")),
            normalize(row.get("recovery_action")),
        )
    )


def eligible_row(row: Mapping[str, Any]) -> bool:
    # A stopped/active/failed episode can contain individually successful
    # clicks but it has not established source-goal consistency.  In
    # particular, an operator-aborted session must never leak those clicks
    # into canonical App Knowledge.
    if normalize(row.get("session_status")) not in {"reached", "completed"}:
        return False
    if row.get("action_name") not in ELIGIBLE_ACTIONS:
        return False
    if row.get("connectivity_status") != "observed":
        return False
    if int(row.get("execution_succeeded") or 0) != 1 or int(row.get("state_changed") or 0) != 1:
        return False
    if row.get("outcome_type") not in {"navigated", "destination_reached"}:
        return False
    if row.get("candidate_set_status") != "complete":
        return False
    candidate = row.get("selected_candidate")
    if row.get("action_name") == "click":
        if not isinstance(candidate, Mapping):
            return False
        if candidate.get("risk_level") != "low" or not candidate.get("clickable", False):
            return False
        semantics = candidate_semantics(candidate)
        if any(marker in semantics for marker in GENERIC_REVERSE_MARKERS):
            return False
    return True


def eligible_failure_row(row: Mapping[str, Any]) -> bool:
    if normalize(row.get("session_status")) not in {"reached", "completed"}:
        return False
    if row.get("action_name") != "click":
        return False
    if row.get("connectivity_status") != "observed":
        return False
    if int(row.get("execution_succeeded") or 0) != 1:
        return False
    if row.get("outcome_type") not in FAILURE_OUTCOMES:
        return False
    if row.get("progress_label") not in {"unchanged", "regressed"}:
        return False
    if row.get("recovery_action") not in RECOVERY_ACTIONS:
        return False
    if row.get("candidate_set_status") != "complete":
        return False
    candidate = row.get("selected_candidate")
    return isinstance(candidate, Mapping) and bool(candidate_semantics(candidate))


def runtime_rows(connection: sqlite3.Connection, session_ids: Iterable[str]) -> list[dict[str, Any]]:
    connection.row_factory = sqlite3.Row
    placeholders = ",".join("?" for _ in session_ids)
    values = tuple(session_ids)
    if not values:
        raise ValueError("at least one session id is required")
    query = f"""
        SELECT s.session_id, s.request_id, s.app_package, s.app_version, s.locale,
               s.goal_text_redacted, s.status AS session_status,
               s.created_at AS session_created_at, s.updated_at AS session_updated_at,
               d.decision_id, d.step_ordinal, d.goal_id, d.action_name, d.candidate_id,
               d.scroll_direction, d.plan_stage, d.planner_provider, d.confidence,
               d.score_margin, d.safety_status, d.safety_reason,
               d.evidence_case_ids_json, d.candidate_values_json,
               d.destination_match_before, d.created_at AS decision_created_at,
               b.snapshot_id AS before_snapshot_id, b.screen_fingerprint,
               b.captured_at AS before_captured_at,
               b.candidate_set_status, b.screen_payload_json AS before_screen_json,
               a.snapshot_id AS after_snapshot_id,
               a.screen_fingerprint AS next_screen_fingerprint,
               a.captured_at AS after_captured_at,
               a.screen_payload_json AS after_screen_json,
               o.observation_id, o.connectivity_status, o.state_changed, o.outcome_type,
               o.progress_label, o.destination_match_after, o.failure_class, o.observed_at,
               x.execution_status, x.execution_succeeded, x.recovery_action,
               x.candidate_forbidden
        FROM navigation_sessions AS s
        JOIN navigation_decisions AS d ON d.session_id=s.session_id
        JOIN navigation_observations AS o ON o.decision_id=d.decision_id
        JOIN navigation_step_executions AS x ON x.decision_id=d.decision_id
        JOIN navigation_screen_snapshots AS b
          ON b.decision_id=d.decision_id AND b.phase='before'
        LEFT JOIN navigation_screen_snapshots AS a
          ON a.decision_id=d.decision_id AND a.phase='after'
        WHERE s.session_id IN ({placeholders})
        ORDER BY s.created_at, d.step_ordinal
    """
    rows: list[dict[str, Any]] = []
    for raw in connection.execute(query, values):
        row = dict(raw)
        row["before_screen"] = sanitized_screen(row.pop("before_screen_json"))
        after_raw = row.pop("after_screen_json")
        row["after_screen"] = sanitized_screen(after_raw) if after_raw else None
        row["selected_candidate"] = selected_candidate(
            row["before_screen"], row.get("candidate_id")
        )
        row["group_key"] = action_group_key(row)
        rows.append(row)
    return rows


def runtime_candidate_payloads(
    connection: sqlite3.Connection,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in connection.execute(
        """
        SELECT candidate_id,observed_payload_json,memory_score,verifier_score,
               final_score,risk_level,terminal,dangerous_final,forbidden,selected
        FROM navigation_screen_candidates
        WHERE snapshot_id=? ORDER BY ordinal
        """,
        (snapshot_id,),
    ):
        values.append(
            {
                "candidate_id": str(row[0]),
                "observed_payload": json.loads(str(row[1])),
                "matched_affordance_id": None,
                "memory_score": row[2],
                "verifier_score": row[3],
                "final_score": row[4],
                "risk_class": str(row[5]),
                "terminal": bool(row[6]),
                "dangerous_final": bool(row[7]),
                "forbidden": bool(row[8]),
                "selected": bool(row[9]),
            }
        )
    return values


def interaction_observation(
    *,
    observation_id: str,
    fingerprint: str,
    screen: Mapping[str, Any],
    captured_at: object,
) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "screen_fingerprint": fingerprint,
        "matched_app_screen_id": None,
        "accessibility_summary": {
            "window_title": screen.get("window_title", ""),
            "activity_name": screen.get("activity_name", ""),
            "navigation_depth": screen.get("navigation_depth"),
            "nodes": list(screen.get("nodes", [])),
        },
        "ocr_summary": {},
        "vision_summary": {},
        "screenshot_ref": None,
        "ui_tree_ref": None,
        "privacy_status": "redacted",
        "captured_at": rfc3339(captured_at),
    }


def episode_status(session_status: object) -> tuple[str, str]:
    normalized = normalize(session_status)
    if normalized == "reached":
        return "completed", "success"
    if normalized == "failed":
        return "failed", "failure"
    if normalized == "stopped":
        return "aborted", "user_stopped"
    return "active", "unknown"


def interaction_episode_from_rows(
    connection: sqlite3.Connection,
    rows: list[dict[str, Any]],
    *,
    source_runtime_sha256: str,
    crosswalk: Mapping[str, str],
) -> dict[str, Any]:
    if not rows:
        raise ValueError("cannot export an empty Runtime session")
    first = rows[0]
    local_goal = str(first.get("goal_id") or "")
    if local_goal not in crosswalk:
        raise ValueError(f"unmapped navigation goal: {local_goal}")
    status, outcome = episode_status(first["session_status"])
    steps: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        before = row["before_screen"]
        after = row["after_screen"]
        execution_status = str(row["execution_status"])
        transport_failure = execution_status in {
            "device_disconnected",
            "transport_error",
            "executor_error",
        }
        selected_action = {
            "type": row["action_name"],
            "candidate_id": row["candidate_id"],
            "parameters": {},
        }
        if row["action_name"] == "scroll":
            selected_action["parameters"]["direction"] = row["scroll_direction"]
        if row.get("recovery_action"):
            selected_action["parameters"]["exitguide_recovery_action"] = row[
                "recovery_action"
            ]
        selected_action["parameters"]["exitguide_candidate_forbidden"] = bool(
            row.get("candidate_forbidden")
        )
        before_match = row.get("destination_match_before")
        after_match = None if transport_failure else row.get("destination_match_after")
        candidates = runtime_candidate_payloads(
            connection, str(row["before_snapshot_id"])
        )
        # Older Runtime rows predate the normalized candidate table. The
        # contract forbids reconstructing scores, so those rows remain partial.
        candidate_set_status = str(row["candidate_set_status"])
        if candidate_set_status == "complete" and not candidates and before.get("candidates"):
            raise ValueError(
                f"complete candidate inventory missing normalized rows: {row['session_id']}:{row['step_ordinal']}"
            )
        after_observation = None
        if not transport_failure and after is not None:
            after_observation = interaction_observation(
                observation_id=str(row.get("after_snapshot_id") or row["observation_id"]),
                fingerprint=str(row["next_screen_fingerprint"]),
                screen=after,
                captured_at=row.get("after_captured_at") or row["observed_at"],
            )
        reward = REWARD_BY_PROGRESS.get(str(row.get("progress_label") or "unknown"))
        step = {
            "step_id": f"{row['session_id']}:{row['step_ordinal']}",
            "ordinal": index,
            "plan_stage": str(row.get("plan_stage") or "unknown"),
            "immediate_subgoal": str(row.get("plan_stage") or "unknown"),
            "before": interaction_observation(
                observation_id=str(row["before_snapshot_id"]),
                fingerprint=str(row["screen_fingerprint"]),
                screen=before,
                captured_at=row.get("before_captured_at") or row["decision_created_at"],
            ),
            "candidate_set_status": candidate_set_status,
            "candidates": candidates,
            "selected_action": selected_action,
            "execution": {
                "status": execution_status,
                "safety_status": (
                    "replaced"
                    if row.get("safety_status") == "replaced_with_safe_action"
                    else "allowed"
                ),
                "safety_reason": str(row.get("safety_reason") or ""),
                "outcome_type": "unknown" if transport_failure else row["outcome_type"],
                "progress_label": "unknown" if transport_failure else row["progress_label"],
                "failure_class": str(row.get("failure_class") or ""),
                "external_target": None,
                "destination_match_before": before_match,
                "destination_match_after": after_match,
                "distance_before": None if before_match is None else 1.0 - float(before_match),
                "distance_after": None if after_match is None else 1.0 - float(after_match),
                "distance_method": "destination_signature_match_v1",
                "reward": None if transport_failure else reward,
            },
            "after": after_observation,
            # The Runtime schema retained evidence IDs but not their individual
            # scores. Do not invent contract-compliant retrieval scores.
            "retrieval_hits": [],
            "model_calls": [],
            "rlds": {
                "is_first": index == 0,
                "is_last": index == len(rows) - 1,
                "is_terminal": index == len(rows) - 1
                and row.get("progress_label") == "reached",
                "discount": 0.0
                if index == len(rows) - 1 and row.get("progress_label") == "reached"
                else 1.0,
            },
            "latency_ms": {},
        }
        steps.append(step)
    payload = {
        "schema_version": "1.0",
        "episode_id": stable_id("episode_runtime", first["session_id"]),
        "request_id": str(first["request_id"]),
        "session_id": str(first["session_id"]),
        "context": {
            "app_id": stable_id("app", first["app_package"]),
            "app_package": str(first["app_package"]),
            "app_version": str(first["app_version"]),
            "platform": "android",
            "locale": str(first["locale"]),
            "goal_id": crosswalk[local_goal],
            "user_intent_redacted": str(first.get("goal_text_redacted") or local_goal),
            "agent_version": "exitguide-navigation-runtime-v4",
            "navigation_generation_id": None,
            "terms_generation_id": None,
            "device_context": {
                "navigation_goal_id": local_goal,
                "runtime_db_sha256": source_runtime_sha256,
                "retrieval_scores_retained": False,
            },
        },
        "status": status,
        "outcome": outcome,
        "steps": steps,
        "started_at": rfc3339(first["session_created_at"]),
        "finished_at": (
            None if status == "active" else rfc3339(first["session_updated_at"])
        ),
    }
    validate_json_schema(payload, load_contract(INTERACTION_CONTRACT))
    validate_interaction_episode(payload)
    return payload


def export_runtime_episodes(
    runtime_db: Path,
    session_ids: Iterable[str],
) -> list[dict[str, Any]]:
    source_sha256 = file_sha256(runtime_db)
    session_ids = list(dict.fromkeys(session_ids))
    with closing(
        sqlite3.connect(f"file:{runtime_db.resolve().as_posix()}?mode=ro", uri=True)
    ) as connection:
        connection.execute("PRAGMA query_only=ON")
        rows = runtime_rows(connection, session_ids)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["session_id"])].append(row)
        missing = sorted(set(session_ids) - set(grouped))
        if missing:
            raise ValueError(f"Runtime sessions have no complete observed steps: {missing}")
        crosswalk = goal_crosswalk()
        return [
            interaction_episode_from_rows(
                connection,
                grouped[session_id],
                source_runtime_sha256=source_sha256,
                crosswalk=crosswalk,
            )
            for session_id in session_ids
        ]


def load_interaction_episodes(path: Path) -> list[dict[str, Any]]:
    contract = load_contract(INTERACTION_CONTRACT)
    episodes = read_jsonl(path)
    if not episodes:
        raise ValueError("interaction episode artifact is empty")
    for episode in episodes:
        validate_json_schema(episode, contract)
        validate_interaction_episode(episode)
    return episodes


def screen_from_interaction_observation(
    observation: Mapping[str, Any] | None,
    candidates: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any] | None:
    if observation is None:
        return None
    accessibility = observation.get("accessibility_summary", {})
    accessibility = accessibility if isinstance(accessibility, Mapping) else {}
    return {
        "window_title": accessibility.get("window_title", ""),
        "activity_name": accessibility.get("activity_name", ""),
        "navigation_depth": accessibility.get("navigation_depth"),
        "nodes": list(accessibility.get("nodes", [])),
        "candidates": [dict(candidate.get("observed_payload", {})) for candidate in candidates],
    }


def rows_from_interaction_episodes(
    episodes: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        context = episode["context"]
        device_context = context.get("device_context", {})
        local_goal = str(device_context.get("navigation_goal_id") or "")
        if not local_goal:
            raise ValueError(f"episode lacks Navigation goal crosswalk provenance: {episode['episode_id']}")
        steps = list(episode["steps"])
        for source_step_index, step in enumerate(steps):
            source_step_id = str(step["step_id"])
            source_step_ordinal = int(source_step_id.rsplit(":", 1)[1])
            candidates = list(step["candidates"])
            action = step["selected_action"]
            execution = step["execution"]
            before_observation = step["before"]
            after_observation = step["after"]
            parameters = action.get("parameters", {})
            selected = next(
                (
                    dict(candidate.get("observed_payload", {}))
                    for candidate in candidates
                    if candidate.get("candidate_id") == action.get("candidate_id")
                ),
                None,
            )
            before_screen = screen_from_interaction_observation(
                before_observation, candidates
            )
            after_screen = screen_from_interaction_observation(after_observation)
            status = str(execution["status"])
            connectivity = (
                status
                if status in {"device_disconnected", "transport_error"}
                else "transport_error"
                if status == "executor_error"
                else "observed"
            )
            state_changed = int(
                after_observation is not None
                and (
                    after_observation["screen_fingerprint"]
                    != before_observation["screen_fingerprint"]
                    or execution["outcome_type"] not in {"no_change", "unknown"}
                )
            )
            row = {
                    "session_id": episode["session_id"],
                    "request_id": episode["request_id"],
                    "app_package": context["app_package"],
                    "app_version": context["app_version"],
                    "locale": context["locale"],
                    "goal_text_redacted": context["user_intent_redacted"],
                    "session_status": episode["status"],
                    "session_created_at": episode["started_at"],
                    "session_updated_at": episode["finished_at"] or episode["started_at"],
                    "decision_id": stable_id("decision_episode", source_step_id),
                    "source_step_id": source_step_id,
                    "step_ordinal": source_step_ordinal,
                    "goal_id": local_goal,
                    "action_name": action["type"],
                    "candidate_id": action.get("candidate_id"),
                    "scroll_direction": parameters.get("direction"),
                    "plan_stage": step["plan_stage"],
                    "planner_provider": "interaction-episode.v1",
                    "confidence": max(
                        (
                            float(candidate.get("final_score") or 0.0)
                            for candidate in candidates
                            if candidate.get("selected") is True
                        ),
                        default=1.0 if action["type"] != "click" else 0.0,
                    ),
                    "destination_match_before": execution["destination_match_before"],
                    "decision_created_at": before_observation["captured_at"],
                    "before_snapshot_id": before_observation["observation_id"],
                    "screen_fingerprint": before_observation["screen_fingerprint"],
                    "candidate_set_status": step["candidate_set_status"],
                    "before_screen": before_screen,
                    "next_screen_fingerprint": (
                        None if after_observation is None else after_observation["screen_fingerprint"]
                    ),
                    "after_screen": after_screen,
                    "observation_id": (
                        stable_id("observation_episode", step["step_id"])
                        if after_observation is None
                        else after_observation["observation_id"]
                    ),
                    "connectivity_status": connectivity,
                    "state_changed": state_changed,
                    "outcome_type": execution["outcome_type"],
                    "progress_label": execution["progress_label"],
                    "destination_match_after": execution["destination_match_after"],
                    "failure_class": execution["failure_class"],
                    "observed_at": (
                        after_observation["captured_at"]
                        if after_observation is not None
                        else before_observation["captured_at"]
                    ),
                    "execution_status": status,
                    "execution_succeeded": int(status == "executed"),
                    "recovery_action": parameters.get("exitguide_recovery_action"),
                    "candidate_forbidden": int(
                        bool(parameters.get("exitguide_candidate_forbidden"))
                    ),
                    "selected_candidate": selected,
                }
            row["group_key"] = action_group_key(row)
            rows.append(row)
    return rows


def best_per_episode(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: dict[str, dict[str, Any]] = {}
    outcome_rank = {"reached": 3, "advanced": 2, "unknown": 1, "unchanged": 0, "regressed": -1}
    for row in rows:
        current = ranked.get(row["session_id"])
        score = (outcome_rank.get(str(row["progress_label"]), -2), int(row["step_ordinal"]))
        if current is None:
            ranked[row["session_id"]] = row
            continue
        current_score = (
            outcome_rank.get(str(current["progress_label"]), -2),
            int(current["step_ordinal"]),
        )
        if score > current_score:
            ranked[row["session_id"]] = row
    return sorted(ranked.values(), key=lambda item: (item["session_id"], item["step_ordinal"]))


def build_candidates(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(rows)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if eligible_row(row) and row["group_key"]:
            groups[(str(row["app_package"]), str(row["group_key"]))].append(row)

    generated_at = now()
    result: list[dict[str, Any]] = []
    for (app_package, group_key), grouped in sorted(groups.items()):
        support = best_per_episode(grouped)
        support_count = len(support)
        all_progressed = support_count >= 2 and all(
            row["progress_label"] in POSITIVE_PROGRESS for row in support
        )
        # Real-device repetition establishes a validation candidate, not an
        # automatic retrieval-memory write. Acceptance additionally requires
        # an offline replay that improves (or at least does not regress) the
        # configured evaluation metrics.
        status = "ready_for_validation" if support_count >= 2 else "draft"
        confidence = 0.82 if all_progressed else 0.72 if support_count >= 2 else 0.55
        representative = support[0]
        action_payload: dict[str, Any] = {"name": representative["action_name"]}
        if representative["action_name"] == "click":
            candidate = representative["selected_candidate"]
            action_payload.update(
                {
                    "semantic_label": normalize(candidate.get("label")),
                    "icon_semantics": normalize(candidate.get("icon_semantics")),
                    "role": normalize(candidate.get("role")),
                }
            )
        else:
            action_payload["direction"] = representative["scroll_direction"]
        sources = [
            {
                "episode_id": row["session_id"],
                "step_id": f"{row['session_id']}:{row['step_ordinal']}",
                "support_kind": "positive",
                "candidate_set_status": row["candidate_set_status"],
                "weight": round(confidence, 2),
            }
            for row in support
        ]
        validations = [
            {
                "validation_id": stable_id("validation", group_key, "schema"),
                "kind": "schema_check",
                "result": "passed",
                "validator_kind": "rule",
                "validator_version": GENERATOR_VERSION,
                "metrics": {"eligible_source_steps": support_count},
                "evidence_refs": [source["step_id"] for source in sources],
            }
        ]
        if support_count >= 2:
            validations.append(
                {
                    "validation_id": stable_id("validation", group_key, "device"),
                    "kind": "real_device",
                    "result": "passed",
                    "validator_kind": "rule",
                    "validator_version": GENERATOR_VERSION,
                    "metrics": {
                        "distinct_episodes": support_count,
                        "executed_and_screen_changed": support_count,
                    },
                    "evidence_refs": [source["step_id"] for source in sources],
                }
            )
        if all_progressed:
            validations.append(
                {
                    "validation_id": stable_id("validation", group_key, "consistency"),
                    "kind": "consistency_check",
                    "result": "passed",
                    "validator_kind": "rule",
                    "validator_version": GENERATOR_VERSION,
                    "metrics": {
                        "distinct_episodes": support_count,
                        "progressed_episodes": support_count,
                        "contradictions": 0,
                    },
                    "evidence_refs": [source["step_id"] for source in sources],
                }
            )
        result.append(
            {
                "schema_version": "1.0",
                "candidate_id": stable_id("promotion_candidate", app_package, group_key),
                "candidate_type": "transition",
                "target_entity_id": None,
                "proposed_payload": {
                    "goal_id": representative["goal_id"],
                    "app_package": app_package,
                    "group_key": group_key,
                    "plan_stage": representative["plan_stage"],
                    "action": action_payload,
                    "expected_outcomes": sorted({str(row["outcome_type"]) for row in support}),
                    "expected_progress": sorted({str(row["progress_label"]) for row in support}),
                    "apply_eligible": False,
                },
                "sources": sources,
                "support_count": support_count,
                "contradiction_count": 0,
                "confidence": confidence,
                "risk_class": "low",
                "generator": {
                    "kind": "rule",
                    "name": GENERATOR_NAME,
                    "version": GENERATOR_VERSION,
                    "generated_at": generated_at,
                },
                "status": status,
                "validation_runs": validations,
                "promotion": None,
            }
        )

    failure_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not eligible_failure_row(row) or not row["group_key"]:
            continue
        failure_key = recovery_group_key(row)
        failure_groups[(str(row["app_package"]), failure_key)].append(row)

    for (app_package, failure_key), grouped in sorted(failure_groups.items()):
        support = best_per_episode(grouped)
        support_count = len(support)
        status = "ready_for_validation" if support_count >= 2 else "draft"
        confidence = 0.8 if support_count >= 3 else 0.74 if support_count >= 2 else 0.55
        representative = support[0]
        observed = representative["selected_candidate"]
        sources = [
            {
                "episode_id": row["session_id"],
                "step_id": f"{row['session_id']}:{row['step_ordinal']}",
                "support_kind": "negative",
                "candidate_set_status": row["candidate_set_status"],
                "weight": round(confidence, 2),
            }
            for row in support
        ]
        evidence_refs = [source["step_id"] for source in sources]
        validations = [
            {
                "validation_id": stable_id("validation", failure_key, "schema"),
                "kind": "schema_check",
                "result": "passed",
                "validator_kind": "rule",
                "validator_version": GENERATOR_VERSION,
                "metrics": {"eligible_failure_steps": support_count},
                "evidence_refs": evidence_refs,
            }
        ]
        if support_count >= 2:
            validations.extend(
                [
                    {
                        "validation_id": stable_id("validation", failure_key, "device"),
                        "kind": "real_device",
                        "result": "passed",
                        "validator_kind": "rule",
                        "validator_version": GENERATOR_VERSION,
                        "metrics": {
                            "distinct_episodes": support_count,
                            "executed_observed_failures": support_count,
                        },
                        "evidence_refs": evidence_refs,
                    },
                    {
                        "validation_id": stable_id("validation", failure_key, "consistency"),
                        "kind": "consistency_check",
                        "result": "passed",
                        "validator_kind": "rule",
                        "validator_version": GENERATOR_VERSION,
                        "metrics": {
                            "distinct_episodes": support_count,
                            "contradictions": 0,
                        },
                        "evidence_refs": evidence_refs,
                    },
                ]
            )
        result.append(
            {
                "schema_version": "1.0",
                "candidate_id": stable_id(
                    "promotion_candidate_recovery", app_package, failure_key
                ),
                "candidate_type": "recovery_rule",
                "target_entity_id": None,
                "proposed_payload": {
                    "goal_id": representative["goal_id"],
                    "app_package": app_package,
                    "group_key": failure_key,
                    "plan_stage": representative["plan_stage"],
                    "action": {
                        "name": "click",
                        "semantic_label": normalize(observed.get("label")),
                        "icon_semantics": normalize(observed.get("icon_semantics")),
                        "role": normalize(observed.get("role")),
                    },
                    "expected_outcomes": sorted(
                        {str(row["outcome_type"]) for row in support}
                    ),
                    "expected_progress": sorted(
                        {str(row["progress_label"]) for row in support}
                    ),
                    "failure_signature": str(
                        representative.get("failure_class")
                        or representative.get("outcome_type")
                    ),
                    "recovery_action": str(representative["recovery_action"]),
                    "recovery_direction": None,
                    "result_outcome_type": "not_observed",
                    "recovered": False,
                    "apply_eligible": False,
                },
                "sources": sources,
                "support_count": support_count,
                "contradiction_count": 0,
                "confidence": confidence,
                "risk_class": "medium",
                "generator": {
                    "kind": "rule",
                    "name": GENERATOR_NAME,
                    "version": GENERATOR_VERSION,
                    "generated_at": generated_at,
                },
                "status": status,
                "validation_runs": validations,
                "promotion": None,
            }
        )
    return result


def validate_candidates(candidates: Iterable[dict[str, Any]], contract: Mapping[str, Any]) -> None:
    validator = Draft202012Validator(contract, format_checker=FormatChecker())
    for candidate in candidates:
        errors = sorted(validator.iter_errors(candidate), key=lambda error: list(error.path))
        if errors:
            raise ValueError(
                f"{candidate.get('candidate_id')}: "
                + "; ".join(error.message for error in errors)
            )
        validate_knowledge_promotion(candidate)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def source_step(connection: sqlite3.Connection, step_id: str) -> dict[str, Any]:
    session_id, ordinal_text = step_id.rsplit(":", 1)
    rows = runtime_rows(connection, [session_id])
    for row in rows:
        if int(row["step_ordinal"]) == int(ordinal_text):
            return row
    raise KeyError(step_id)


def surface_type(screen: Mapping[str, Any]) -> str:
    descriptor = normalize(f"{screen.get('window_title', '')} {screen.get('activity_name', '')}")
    if "webview" in descriptor:
        return "webview"
    if "browser" in descriptor or "external link" in descriptor or "외부 링크" in descriptor:
        return "hybrid"
    return "native"


def insert_screen(
    connection: sqlite3.Connection,
    *,
    fingerprint: str,
    screen: Mapping[str, Any],
    source_hash: str,
    timestamp: str,
) -> str:
    screen_id = stable_id("screen_runtime", fingerprint)
    semantic_values = [screen.get("window_title", "")]
    semantic_values.extend(
        candidate.get("label", "") for candidate in screen.get("candidates", [])
    )
    tokens = sorted(tokenize(" ".join(str(value) for value in semantic_values)))
    connection.execute(
        """
        INSERT OR IGNORE INTO semantic_screens(
            screen_id, semantic_fingerprint, title_normalized, region_roles_json,
            navigation_depth, auth_state, surface_type, semantic_tokens_json,
            source_hash, created_at, updated_at
        ) VALUES (?,?,?,?,?,'unknown',?,?,?,?,?)
        """,
        (
            screen_id,
            fingerprint,
            normalize(screen.get("window_title", "")),
            "[]",
            screen.get("navigation_depth"),
            surface_type(screen),
            json.dumps(tokens, ensure_ascii=False),
            source_hash,
            timestamp,
            timestamp,
        ),
    )
    return screen_id


def role_scores(connection: sqlite3.Connection, candidate: Mapping[str, Any], locale: str) -> dict[str, float]:
    text = candidate_semantics(candidate)
    result: dict[str, float] = {}
    for role_id, alias, confidence in connection.execute(
        "SELECT role_id, normalized_alias, confidence FROM affordance_role_aliases WHERE locale=?",
        (locale,),
    ):
        normalized_alias = normalize(alias)
        if normalized_alias and normalized_alias in text:
            result[str(role_id)] = max(float(confidence), result.get(str(role_id), 0.0))
    return result


def apply_candidate(
    decision: sqlite3.Connection,
    runtime: sqlite3.Connection | None,
    candidate: dict[str, Any],
    *,
    source_lookup: Any | None = None,
) -> list[str]:
    inserted: list[str] = []
    signature_row = decision.execute(
        "SELECT signature_id FROM destination_signatures WHERE goal_id=? ORDER BY version DESC LIMIT 1",
        (candidate["proposed_payload"]["goal_id"],),
    ).fetchone()
    signature_id = None if signature_row is None else str(signature_row[0])
    for source in candidate["sources"]:
        if source_lookup is not None:
            row = source_lookup(source["step_id"])
        elif runtime is not None:
            row = source_step(runtime, source["step_id"])
        else:
            raise ValueError("projection source lookup is required")
        row_group_key = (
            recovery_group_key(row)
            if candidate["candidate_type"] == "recovery_rule"
            else action_group_key(row)
        )
        if row_group_key != candidate["proposed_payload"]["group_key"]:
            raise ValueError(f"source semantics changed: {source['step_id']}")
        before = row["before_screen"]
        after = row["after_screen"]
        if after is None:
            raise ValueError(f"missing observed next screen: {source['step_id']}")
        source_hash = hashlib.sha256(
            json.dumps(before, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        before_screen_id = insert_screen(
            decision,
            fingerprint=row["screen_fingerprint"],
            screen=before,
            source_hash=source_hash,
            timestamp=row["decision_created_at"],
        )
        after_screen_id = insert_screen(
            decision,
            fingerprint=row["next_screen_fingerprint"],
            screen=after,
            source_hash=hashlib.sha256(
                json.dumps(after, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            timestamp=row["observed_at"],
        )
        observation_id = stable_id("observation_runtime", source["step_id"], "before")
        accessibility_elements = [
            {
                "node_id": str(node.get("node_id", "")),
                "parent_node_id": str(node.get("parent_id") or ""),
                "label": str(node.get("text", "")),
                "content_description": str(node.get("content_description", "")),
                "role": str(node.get("role", "unknown")),
                "clickable": bool(node.get("clickable", False)),
                "scrollable": bool(node.get("scrollable", False)),
                "enabled": bool(node.get("enabled", True)),
                "selected": bool(node.get("selected", False)),
                "checked": node.get("checked"),
            }
            for node in before.get("nodes", [])
        ]
        decision.execute(
            """
            INSERT OR IGNORE INTO screen_observations VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                observation_id,
                before_screen_id,
                row["app_package"],
                row["app_version"],
                row["locale"],
                json.dumps(
                    {
                        "window_title": before.get("window_title", ""),
                        "activity_semantics": before.get("activity_name", ""),
                        "elements": accessibility_elements,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                '{"labels":[]}',
                "{}",
                "real_device",
                row["decision_created_at"],
            ),
        )
        decision.execute(
            """
            INSERT OR IGNORE INTO observation_contracts VALUES (?,?,?,?,?,?)
            """,
            (
                observation_id,
                "https://exitguide.ai/schemas/android-accessibility-observation.v1.schema.json",
                "android_accessibility_node_subset_v1",
                "https://exitguide.ai/schemas/ocr-observation.v1.schema.json",
                "https://exitguide.ai/schemas/vlm-observation.v1.schema.json",
                "semantic-redaction-v1",
            ),
        )
        chosen_affordance_id: str | None = None
        for observed in before.get("candidates", []):
            affordance_id = stable_id(
                "aff_runtime", before_screen_id, observed.get("candidate_id", "")
            )
            roles = role_scores(decision, observed, row["locale"])
            decision.execute(
                """
                INSERT OR IGNORE INTO affordances VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    affordance_id,
                    before_screen_id,
                    observed.get("candidate_id", ""),
                    redact_text(str(observed.get("label", ""))),
                    normalize(observed.get("label", "")),
                    redact_text(str(observed.get("icon_semantics", ""))),
                    observed.get("role", "unknown"),
                    redact_text(str(observed.get("parent_semantics", ""))),
                    redact_text(str(observed.get("nearby_text", ""))),
                    observed.get("position_bucket", "unknown"),
                    observed.get("risk_level", "low"),
                    int(observed.get("risk_level") in {"high", "blocked"}),
                    json.dumps(roles, ensure_ascii=False, sort_keys=True),
                    observed.get("candidate_id", ""),
                ),
            )
            if observed.get("candidate_id") == row.get("candidate_id"):
                chosen_affordance_id = affordance_id
        case_id = stable_id("case_runtime", source["step_id"])
        decision.execute(
            """
            INSERT OR IGNORE INTO decision_cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                case_id,
                row["goal_id"],
                before_screen_id,
                row["goal_id"],
                json.dumps({"plan_stage": row["plan_stage"]}, sort_keys=True),
                row["action_name"],
                chosen_affordance_id,
                row["scroll_direction"],
                signature_id,
                row["app_package"],
                row["session_id"],
                row["step_ordinal"],
                "real_device",
                candidate["confidence"],
                row["observed_at"],
            ),
        )
        outcome_id = stable_id("outcome_runtime", source["step_id"])
        before_match = row["destination_match_before"]
        after_match = row["destination_match_after"]
        decision.execute(
            """
            INSERT OR IGNORE INTO transition_outcomes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                outcome_id,
                case_id,
                after_screen_id,
                row["outcome_type"],
                row["connectivity_status"],
                row["state_changed"],
                before_match,
                after_match,
                None if before_match is None else 1.0 - float(before_match),
                None if after_match is None else 1.0 - float(after_match),
                "destination_signature_match_v1",
                row["progress_label"],
                row["failure_class"],
                "",
                row["observed_at"],
            ),
        )
        evidence_entities = [
            ("decision_case", case_id),
            ("transition_outcome", outcome_id),
        ]
        if candidate["candidate_type"] == "recovery_rule":
            if chosen_affordance_id is None:
                raise ValueError(
                    f"recovery rule source has no grounded affordance: {source['step_id']}"
                )
            payload = candidate["proposed_payload"]
            recovery_id = stable_id("recovery_runtime", source["step_id"])
            decision.execute(
                """
                INSERT OR IGNORE INTO recovery_memories VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    recovery_id,
                    row["goal_id"],
                    before_screen_id,
                    chosen_affordance_id,
                    payload["failure_signature"],
                    payload["recovery_action"],
                    payload.get("recovery_direction"),
                    payload.get("result_outcome_type", "not_observed"),
                    int(bool(payload.get("recovered", False))),
                    case_id,
                    row["observed_at"],
                ),
            )
            evidence_entities.append(("recovery_memory", recovery_id))
        # RLDS keeps one episode for each source runtime session, while only
        # independently verified action units are promoted into its step set.
        # Boundaries are recalculated below from the promoted subset so repeated
        # promotions from one session still have exactly one first/last step.
        episode_id = stable_id("episode_runtime", row["session_id"])
        is_terminal = int(row["progress_label"] == "reached")
        end_reason = episode_end_reason(row["session_status"])
        reward = REWARD_BY_PROGRESS.get(str(row["progress_label"] or "unknown"))
        decision.execute(
            """
            INSERT OR IGNORE INTO experience_episodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                episode_id,
                row["goal_id"],
                "real_device",
                row["session_id"],
                row["app_package"],
                row["app_version"],
                row["locale"],
                "navigation-app-split-v1-20260803",
                "train",
                row["session_created_at"],
                row["session_updated_at"],
                end_reason,
                json.dumps({"action_unit_promotion": candidate["candidate_id"]}, sort_keys=True),
            ),
        )
        decision.execute(
            "INSERT OR IGNORE INTO experience_steps VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                case_id,
                episode_id,
                row["step_ordinal"],
                1,
                1,
                is_terminal,
                reward,
                1.0,
                "exitguide_progress_v1",
                json.dumps({"runtime_decision_id": row["decision_id"]}, sort_keys=True),
            ),
        )
        decision.execute(
            """
            UPDATE experience_steps
            SET is_first = CASE WHEN step_index=(
                    SELECT MIN(step_index) FROM experience_steps WHERE episode_id=?
                ) THEN 1 ELSE 0 END,
                is_last = CASE WHEN step_index=(
                    SELECT MAX(step_index) FROM experience_steps WHERE episode_id=?
                ) THEN 1 ELSE 0 END
            WHERE episode_id=?
            """,
            (episode_id, episode_id, episode_id),
        )
        decision.execute(
            """
            UPDATE experience_steps
            SET is_terminal = CASE
                WHEN is_last=1 AND EXISTS (
                    SELECT 1 FROM transition_outcomes AS outcome
                    WHERE outcome.case_id=experience_steps.case_id
                      AND outcome.progress_label='reached'
                ) THEN 1 ELSE 0 END
            WHERE episode_id=?
            """,
            (episode_id,),
        )
        activity_id = stable_id("activity_runtime", source["step_id"])
        decision.execute(
            """
            INSERT OR IGNORE INTO provenance_activities VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                activity_id,
                f"https://exitguide.ai/provenance/activities/{activity_id}",
                "collection.real_device",
                "agent.real-device-recorder",
                source["step_id"],
                row["decision_created_at"],
                row["observed_at"],
                json.dumps({"promotion_candidate_id": candidate["candidate_id"]}, sort_keys=True),
            ),
        )
        for entity_type, entity_id in evidence_entities:
            evidence_id = stable_id("evidence_runtime", entity_type, entity_id)
            decision.execute(
                "INSERT OR IGNORE INTO evidence_records VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    evidence_id,
                    entity_type,
                    entity_id,
                    "real_device",
                    source["step_id"],
                    candidate["support_count"],
                    candidate["confidence"],
                    row["app_package"],
                    row["app_version"],
                    row["locale"],
                    row["observed_at"],
                ),
            )
            decision.execute(
                "INSERT OR IGNORE INTO evidence_provenance VALUES (?,?,?,?,?,?)",
                (
                    evidence_id,
                    f"https://exitguide.ai/navigation/{entity_type}/{entity_id}",
                    activity_id,
                    "agent.real-device-recorder",
                    source["step_id"],
                    row["observed_at"],
                ),
            )
        inserted.append(case_id)
    return inserted


def goal_descriptor(common_goal_id: str) -> dict[str, Any]:
    mapping = {
        "create_account": ("account", "create", "account", "medium"),
        "delete_account": ("account", "delete", "account", "high"),
        "join_membership": ("membership", "join", "membership", "high"),
        "manage_membership": ("membership", "manage", "membership", "medium"),
        "change_membership": ("membership", "change", "membership", "high"),
        "cancel_membership": ("membership", "cancel", "membership", "high"),
    }
    if common_goal_id not in mapping:
        raise ValueError(f"unsupported canonical goal: {common_goal_id}")
    family, operation, object_type, risk = mapping[common_goal_id]
    return {
        "goal_id": common_goal_id,
        "family": family,
        "operation": operation,
        "object_type": object_type,
        "risk_class": risk,
        "terminal_action_policy": "stop_for_user",
    }


def packet_screen_id(app_package: str, fingerprint: str) -> str:
    return stable_id("app_screen", app_package, fingerprint)


def packet_concept_id(screen: Mapping[str, Any]) -> str:
    values = [screen.get("window_title", ""), screen.get("activity_name", "")]
    values.extend(
        candidate.get("label", "") for candidate in screen.get("candidates", [])
    )
    return stable_id("screen_concept", *sorted(tokenize(" ".join(map(str, values)))))


def packet_affordance_id(
    app_package: str,
    screen_fingerprint: str,
    candidate: Mapping[str, Any],
) -> str:
    identity = (
        candidate.get("label")
        or candidate.get("icon_semantics")
        or candidate.get("child_semantics")
        or candidate.get("candidate_id")
    )
    return stable_id(
        "app_affordance",
        app_package,
        screen_fingerprint,
        normalize(identity),
        normalize(candidate.get("role")),
    )


def promotion_entity_id(candidate: Mapping[str, Any]) -> str:
    prefix = "recovery_rule" if candidate["candidate_type"] == "recovery_rule" else "transition"
    return stable_id(prefix, candidate["candidate_id"])


def build_app_knowledge_packet(
    *,
    app_package: str,
    candidates: list[dict[str, Any]],
    row_by_step: Mapping[str, dict[str, Any]],
    generation_id: str,
    source_revision: str,
    crosswalk: Mapping[str, str],
) -> dict[str, Any]:
    relevant_rows = [
        row_by_step[source["step_id"]]
        for candidate in candidates
        for source in candidate["sources"]
    ]
    versions = sorted({str(row["app_version"]) for row in relevant_rows if row["app_version"]})
    locale = str(relevant_rows[0]["locale"])
    goals: dict[str, dict[str, Any]] = {}
    capabilities: dict[str, dict[str, Any]] = {}
    concepts: dict[str, dict[str, Any]] = {}
    screens: dict[str, dict[str, Any]] = {}
    affordances: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []
    recoveries: list[dict[str, Any]] = []

    def add_screen(
        screen: Mapping[str, Any] | None,
        fingerprint: str | None,
        evidence_ids: list[str],
        confidence: float,
    ) -> tuple[str | None, str | None]:
        if screen is None or not fingerprint:
            return None, None
        screen_id = packet_screen_id(app_package, fingerprint)
        concept_id = packet_concept_id(screen)
        semantic_values = [screen.get("window_title", ""), screen.get("activity_name", "")]
        semantic_values.extend(
            candidate.get("label", "") for candidate in screen.get("candidates", [])
        )
        semantic_tokens = sorted(tokenize(" ".join(map(str, semantic_values))))
        concepts.setdefault(
            concept_id,
            {
                "concept_id": concept_id,
                "semantic_name": normalize(screen.get("window_title")) or "semantic screen",
                "description": "Observed semantic screen state",
                "auth_state": "unknown",
                "surface_type": surface_type(screen),
                "semantic_tokens": semantic_tokens,
            },
        )
        existing = screens.get(screen_id)
        combined_evidence = sorted(
            set(evidence_ids) | set(existing.get("evidence_ids", []) if existing else [])
        )
        screens[screen_id] = {
            "app_screen_id": screen_id,
            "concept_id": concept_id,
            "semantic_fingerprint": fingerprint,
            "semantic_title": redact_text(str(screen.get("window_title") or "semantic screen")),
            "state_features": {
                "activity": redact_text(str(screen.get("activity_name") or "")),
                "navigation_depth": screen.get("navigation_depth"),
            },
            "version_constraint": {
                "min_version": versions[0] if versions else None,
                "max_version": versions[-1] if versions else None,
                "observed_versions": versions,
            },
            "confidence": max(confidence, float(existing.get("confidence", 0.0)) if existing else 0.0),
            "status": "validated",
            "evidence_ids": combined_evidence,
        }
        for observed in screen.get("candidates", []):
            affordance_id = packet_affordance_id(app_package, fingerprint, observed)
            label = redact_text(
                str(
                    observed.get("label")
                    or observed.get("icon_semantics")
                    or observed.get("child_semantics")
                    or observed.get("candidate_id")
                )
            )
            prior = affordances.get(affordance_id)
            combined = sorted(
                set(evidence_ids) | set(prior.get("evidence_ids", []) if prior else [])
            )
            risk = str(observed.get("risk_level") or "low")
            affordances[affordance_id] = {
                "affordance_id": affordance_id,
                "app_screen_id": screen_id,
                "role_id": str(observed.get("role") or "unknown"),
                "semantic_label": label or "unnamed observed control",
                "operation": "click" if observed.get("clickable") else "observe",
                "expected_effects": [],
                "risk_class": risk,
                "terminal": bool(observed.get("risk_level") in {"high", "blocked"}),
                "confidence": max(confidence, float(prior.get("confidence", 0.0)) if prior else 0.0),
                "status": "validated",
                "evidence_ids": combined,
            }
        return screen_id, concept_id

    for candidate in candidates:
        local_goal = str(candidate["proposed_payload"]["goal_id"])
        if local_goal not in crosswalk:
            raise ValueError(f"promotion uses unmapped goal: {local_goal}")
        common_goal = crosswalk[local_goal]
        goals.setdefault(common_goal, goal_descriptor(common_goal))
        capability_id = stable_id("capability", app_package, common_goal)
        capabilities.setdefault(
            capability_id,
            {
                "capability_id": capability_id,
                "goal_id": common_goal,
                "capability_key": f"{app_package}:{common_goal}",
                "support_status": "partial",
                "entry_mode": "ui",
                "parameter_schema": {},
                "preconditions": [],
                "effects": [],
                "risk_class": goal_descriptor(common_goal)["risk_class"],
                "status": "validated",
            },
        )
        evidence_ids = [stable_id("evidence_step", source["step_id"]) for source in candidate["sources"]]
        rows = [row_by_step[source["step_id"]] for source in candidate["sources"]]
        representative = rows[0]
        from_screen_id, concept_id = add_screen(
            representative["before_screen"],
            representative["screen_fingerprint"],
            evidence_ids,
            float(candidate["confidence"]),
        )
        to_screen_id, _ = add_screen(
            representative["after_screen"],
            representative["next_screen_fingerprint"],
            evidence_ids,
            float(candidate["confidence"]),
        )
        if from_screen_id is None:
            raise ValueError(f"promotion lacks a grounded before screen: {candidate['candidate_id']}")
        selected = representative.get("selected_candidate")
        selected_affordance_id = (
            packet_affordance_id(
                app_package,
                representative["screen_fingerprint"],
                selected,
            )
            if isinstance(selected, Mapping)
            else None
        )
        if candidate["candidate_type"] == "recovery_rule":
            payload = candidate["proposed_payload"]
            recovery_action = str(payload["recovery_action"])
            parameters: dict[str, Any] = {}
            if payload.get("recovery_direction"):
                parameters["direction"] = payload["recovery_direction"]
            recoveries.append(
                {
                    "recovery_id": promotion_entity_id(candidate),
                    "goal_id": common_goal,
                    "screen_concept_id": concept_id,
                    "failure_signature": str(payload["failure_signature"]),
                    "forbidden_affordance_id": selected_affordance_id,
                    "recovery_action": {
                        "type": recovery_action,
                        "affordance_id": None,
                        "parameters": parameters,
                    },
                    "expected_effect": {
                        "outcome_type": payload.get("result_outcome_type", "not_observed"),
                        "recovered": bool(payload.get("recovered", False)),
                    },
                    "confidence": float(candidate["confidence"]),
                    "status": "validated",
                    "evidence_ids": evidence_ids,
                }
            )
            continue
        action = candidate["proposed_payload"]["action"]
        parameters = {}
        if action.get("direction"):
            parameters["direction"] = action["direction"]
        raw_outcome = str(representative["outcome_type"])
        outcome_class = {
            "external_app": "external",
            "wrong_destination": "unknown",
            "popup": "state_changed",
            "login_required": "blocked",
        }.get(raw_outcome, raw_outcome)
        if outcome_class not in {
            "navigated",
            "state_changed",
            "destination_reached",
            "external",
            "no_change",
            "blocked",
            "unknown",
        }:
            outcome_class = "unknown"
        transitions.append(
            {
                "transition_id": promotion_entity_id(candidate),
                "capability_id": capability_id,
                "from_screen_id": from_screen_id,
                "action": {
                    "type": action["name"],
                    "affordance_id": selected_affordance_id,
                    "parameters": parameters,
                },
                "to_screen_id": to_screen_id,
                "outcome_class": outcome_class,
                "preconditions": [{"candidate_set_status": "complete"}],
                "effects": [
                    {
                        "progress_label": representative["progress_label"],
                        "destination_match_after": representative["destination_match_after"],
                    }
                ],
                "failure_modes": [],
                "risk_class": candidate["risk_class"],
                "requires_user_confirmation": False,
                "support_count": int(candidate["support_count"]),
                "contradiction_count": int(candidate["contradiction_count"]),
                "confidence": float(candidate["confidence"]),
                "status": "validated",
                "evidence_ids": evidence_ids,
            }
        )
    packet = {
        "schema_version": "1.0",
        "packet_id": stable_id("app_knowledge_packet", generation_id, app_package),
        "generation_id": generation_id,
        "app": {
            "app_id": stable_id("app", app_package),
            "platform": "android",
            "package_name": app_package,
            "display_name": app_package,
            "locale": locale,
            "version_constraint": {
                "min_version": versions[0] if versions else None,
                "max_version": versions[-1] if versions else None,
                "observed_versions": versions,
            },
        },
        "goals": sorted(goals.values(), key=lambda item: item["goal_id"]),
        "capabilities": sorted(
            capabilities.values(), key=lambda item: item["capability_id"]
        ),
        "screen_concepts": sorted(
            concepts.values(), key=lambda item: item["concept_id"]
        ),
        "app_screens": sorted(screens.values(), key=lambda item: item["app_screen_id"]),
        "affordances": sorted(
            affordances.values(), key=lambda item: item["affordance_id"]
        ),
        "destination_signatures": [],
        "transitions": sorted(transitions, key=lambda item: item["transition_id"]),
        # Whole app paths are deliberately not materialized or executable.
        "procedures": [],
        "recovery_rules": sorted(recoveries, key=lambda item: item["recovery_id"]),
        "provenance": {
            "source_system": "exitguide.navigation.interaction-episode.v1",
            "source_revision": source_revision,
            "generated_at": now(),
            "generator_kind": "rule",
            "contract_version": "1.0",
        },
    }
    validate_json_schema(packet, load_contract(APP_KNOWLEDGE_CONTRACT))
    validate_app_knowledge(packet)
    if packet["procedures"]:
        raise ValueError("Navigation promotion generations must not materialize executable paths")
    return packet


def sealed_promotions(
    candidates: Iterable[dict[str, Any]], generation_id: str
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for original in candidates:
        candidate = json.loads(json.dumps(original))
        entity_id = promotion_entity_id(candidate)
        candidate["target_entity_id"] = entity_id
        candidate["status"] = "applied"
        candidate["promotion"] = {
            "promotion_id": stable_id("promotion", generation_id, candidate["candidate_id"]),
            "target_entity_type": candidate["candidate_type"],
            "target_entity_id": entity_id,
            "target_generation_id": generation_id,
            "decision": "accepted",
            "reviewer_kind": "replay_gate",
            "decision_reason": "accepted source-consistent evidence sealed into immutable App Knowledge",
            "rollback_of_promotion_id": None,
            "decided_at": now(),
        }
        validate_knowledge_promotion(candidate)
        result.append(candidate)
    return result


def verify_generation(generation_dir: Path) -> dict[str, Any]:
    manifest_path = generation_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_json_schema(manifest, load_contract(GENERATION_CONTRACT))
    artifacts = [
        manifest["base_decision_snapshot"],
        manifest["interaction_episodes"],
        manifest["promotions"],
        *manifest["app_knowledge_packets"],
    ]
    for artifact in artifacts:
        path = generation_dir / artifact["path"]
        if not path.is_file():
            raise FileNotFoundError(path)
        if file_sha256(path) != artifact["sha256"]:
            raise ValueError(f"generation artifact hash mismatch: {artifact['path']}")
        if path.stat().st_size != artifact["byte_size"]:
            raise ValueError(f"generation artifact size mismatch: {artifact['path']}")
    load_interaction_episodes(generation_dir / manifest["interaction_episodes"]["path"])
    promotions = read_jsonl(generation_dir / manifest["promotions"]["path"])
    validate_candidates(promotions, load_contract(SHARED_CONTRACTS / "knowledge-promotion.v1.json"))
    for packet_entry in manifest["app_knowledge_packets"]:
        packet = json.loads(
            (generation_dir / packet_entry["path"]).read_text(encoding="utf-8")
        )
        validate_json_schema(packet, load_contract(APP_KNOWLEDGE_CONTRACT))
        validate_app_knowledge(packet)
        if packet["generation_id"] != manifest["generation_id"]:
            raise ValueError("App Knowledge packet generation_id mismatch")
        if packet["procedures"]:
            raise ValueError("generation contains executable app procedure paths")
    return manifest


def command_export_episode(args: argparse.Namespace) -> None:
    episodes = export_runtime_episodes(args.runtime_db, args.session)
    write_jsonl(args.output, episodes)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "episodes": len(episodes),
                "steps": sum(len(episode["steps"]) for episode in episodes),
                "sha256": file_sha256(args.output),
            },
            ensure_ascii=False,
        )
    )


def command_build_generation(args: argparse.Namespace) -> None:
    episodes = load_interaction_episodes(args.episodes)
    candidates = read_jsonl(args.input)
    validate_candidates(candidates, load_contract(args.contract))
    selected = [
        candidate
        for candidate in candidates
        if candidate["status"] in {"accepted", "applied"}
        and candidate["proposed_payload"].get("apply_eligible") is True
        and any(
            run.get("kind") == "deterministic_replay"
            and run.get("result") == "passed"
            and run.get("metrics", {}).get("validation_scope")
            in {None, "source_consistency_only"}
            for run in candidate.get("validation_runs", [])
        )
    ]
    if not selected:
        raise ValueError("no accepted source-consistent promotions")
    rows = rows_from_interaction_episodes(episodes)
    row_by_step = {row["source_step_id"]: row for row in rows}
    missing = sorted(
        {
            source["step_id"]
            for candidate in selected
            for source in candidate["sources"]
            if source["step_id"] not in row_by_step
        }
    )
    if missing:
        raise ValueError(f"promotion references missing Interaction Episode steps: {missing}")
    contract_hash = hashlib.sha256(
        b"\x00".join(path.read_bytes() for path in sorted(SHARED_CONTRACTS.glob("*.json")))
    ).hexdigest()
    base_hash = file_sha256(args.base_decision_db)
    episode_hash = file_sha256(args.episodes)
    promotion_hash = file_sha256(args.input)
    generation_id = stable_id(
        "generation",
        args.parent_generation_id or "root",
        base_hash,
        episode_hash,
        promotion_hash,
        contract_hash,
    )
    output_dir = args.output_root / generation_id
    if output_dir.exists():
        raise FileExistsError(f"immutable generation already exists: {output_dir}")
    temporary = args.output_root / f".{generation_id}.{os.getpid()}.tmp"
    if temporary.exists():
        raise FileExistsError(temporary)
    temporary.mkdir(parents=True)
    try:
        base_path = temporary / "base-decision.sqlite"
        episodes_path = temporary / "interaction-episodes.v1.jsonl"
        promotions_path = temporary / "promotions.applied.v1.jsonl"
        shutil.copy2(args.base_decision_db, base_path)
        shutil.copy2(args.episodes, episodes_path)
        applied = sealed_promotions(selected, generation_id)
        write_jsonl(promotions_path, applied)
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in applied:
            groups[str(candidate["proposed_payload"]["app_package"])].append(candidate)
        packet_entries: list[dict[str, Any]] = []
        crosswalk = goal_crosswalk()
        for app_package, grouped in sorted(groups.items()):
            packet = build_app_knowledge_packet(
                app_package=app_package,
                candidates=grouped,
                row_by_step=row_by_step,
                generation_id=generation_id,
                source_revision=promotion_hash,
                crosswalk=crosswalk,
            )
            packet_path = temporary / "packets" / f"{stable_id('app', app_package)}.app-knowledge.v1.json"
            write_json(packet_path, packet)
            entry = artifact_payload(packet_path, root=temporary)
            entry["app_package"] = app_package
            packet_entries.append(entry)
        source_revision = hashlib.sha256(
            f"{episode_hash}:{promotion_hash}".encode("ascii")
        ).hexdigest()
        base_artifact = artifact_payload(base_path, root=temporary)
        episode_artifact = artifact_payload(
            episodes_path, root=temporary, record_count=len(episodes)
        )
        promotion_artifact = artifact_payload(
            promotions_path, root=temporary, record_count=len(applied)
        )
        manifest = {
            "schema_version": "1.0",
            "generation_id": generation_id,
            "parent_generation_id": args.parent_generation_id,
            "status": "sealed",
            "created_at": now(),
            "contract_version": "shared-app-knowledge-v0.9.1",
            "source_revision": source_revision,
            "base_decision_snapshot": base_artifact,
            "interaction_episodes": episode_artifact,
            "promotions": promotion_artifact,
            "app_knowledge_packets": packet_entries,
            "policy": {
                "decision_db_is_projection": True,
                "runtime_direct_apply_allowed": False,
                "procedures_are_executable": False,
                "activation_requires_validation_regression": True,
                "locked_holdout_used_for_tuning": False,
            },
        }
        validate_json_schema(manifest, load_contract(GENERATION_CONTRACT))
        write_json(temporary / "manifest.json", manifest)
        args.output_root.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, output_dir)
        verify_generation(output_dir)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    print(
        json.dumps(
            {
                "generation_id": generation_id,
                "generation_dir": str(output_dir),
                "packets": len(packet_entries),
                "promotions": len(selected),
                "status": "sealed",
            },
            ensure_ascii=False,
        )
    )


def command_project(args: argparse.Namespace) -> None:
    manifest = verify_generation(args.generation_dir)
    if args.output.exists() and not args.overwrite_staging:
        raise FileExistsError(f"staging DB already exists: {args.output}")
    episodes = load_interaction_episodes(
        args.generation_dir / manifest["interaction_episodes"]["path"]
    )
    rows = rows_from_interaction_episodes(episodes)
    row_by_step = {row["source_step_id"]: row for row in rows}
    promotions = read_jsonl(
        args.generation_dir / manifest["promotions"]["path"]
    )
    canonical_entity_ids: set[str] = set()
    for packet_entry in manifest["app_knowledge_packets"]:
        packet = json.loads(
            (args.generation_dir / packet_entry["path"]).read_text(encoding="utf-8")
        )
        canonical_entity_ids.update(
            item["transition_id"] for item in packet["transitions"]
        )
        canonical_entity_ids.update(
            item["recovery_id"] for item in packet["recovery_rules"]
        )
    missing_entities = sorted(
        candidate["target_entity_id"]
        for candidate in promotions
        if candidate["target_entity_id"] not in canonical_entity_ids
    )
    if missing_entities:
        raise ValueError(f"promotions are absent from canonical App Knowledge: {missing_entities}")
    base_path = args.generation_dir / manifest["base_decision_snapshot"]["path"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.{os.getpid()}.tmp")
    shutil.copy2(base_path, temporary)
    try:
        with closing(sqlite3.connect(temporary)) as decision:
            decision.execute("PRAGMA foreign_keys=ON")
            before_count = decision.execute("SELECT COUNT(*) FROM decision_cases").fetchone()[0]
            decision.execute("BEGIN IMMEDIATE")
            inserted: list[str] = []
            try:
                for candidate in promotions:
                    inserted.extend(
                        apply_candidate(
                            decision,
                            None,
                            candidate,
                            source_lookup=lambda step_id: row_by_step[step_id],
                        )
                    )
                decision.commit()
            except Exception:
                decision.rollback()
                raise
            after_count = decision.execute("SELECT COUNT(*) FROM decision_cases").fetchone()[0]
            quick_check = decision.execute("PRAGMA quick_check").fetchone()[0]
            foreign_key_errors = len(decision.execute("PRAGMA foreign_key_check").fetchall())
        if quick_check != "ok" or foreign_key_errors:
            raise ValueError("staging projection failed SQLite integrity validation")
        os.replace(temporary, args.output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    report = {
        "schema_version": "1.0",
        "kind": "app_knowledge_generation_projection",
        "generation_id": manifest["generation_id"],
        "runtime_db_accessed": False,
        "base_decision_sha256": manifest["base_decision_snapshot"]["sha256"],
        "staging_decision_db": str(args.output.resolve()),
        "staging_decision_sha256": file_sha256(args.output),
        "decision_cases_before": before_count,
        "decision_cases_after": after_count,
        "source_case_ids": sorted(set(inserted)),
        "quick_check": quick_check,
        "foreign_key_errors": foreign_key_errors,
        "created_at": now(),
    }
    write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))


def command_generate(args: argparse.Namespace) -> None:
    contract = load_contract(args.contract)
    if args.episodes:
        rows = rows_from_interaction_episodes(load_interaction_episodes(args.episodes))
    else:
        if not args.allow_legacy_runtime_input:
            raise ValueError(
                "direct Runtime input is legacy-only; run export-episode and pass --episodes"
            )
        if not args.session:
            raise ValueError("legacy Runtime generation requires at least one --session")
        with closing(sqlite3.connect(args.runtime_db)) as connection:
            rows = runtime_rows(connection, args.session)
    candidates = build_candidates(rows)
    validate_candidates(candidates, contract)
    write_jsonl(args.output, candidates)
    counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        counts[candidate["status"]] += 1
    print(json.dumps({"output": str(args.output), "candidates": len(candidates), "status": counts}, ensure_ascii=False, default=dict))


def command_accept(args: argparse.Namespace) -> None:
    """Accept candidates after source Interaction Episode consistency replay."""

    contract = load_contract(args.contract)
    candidates = read_jsonl(args.input)
    validate_candidates(candidates, contract)
    accepted: list[dict[str, Any]] = []
    if args.episodes:
        episode_rows = {
            row["source_step_id"]: row
            for row in rows_from_interaction_episodes(
                load_interaction_episodes(args.episodes)
            )
        }
        source_lookup = lambda step_id: episode_rows[step_id]
        runtime_context = None
    else:
        if not args.allow_legacy_runtime_input:
            raise ValueError(
                "direct Runtime input is legacy-only; run export-episode and pass --episodes"
            )
        runtime_context = sqlite3.connect(args.runtime_db)
        source_lookup = lambda step_id: source_step(runtime_context, step_id)
    try:
        for original in candidates:
            candidate = json.loads(json.dumps(original))
            if candidate["status"] != "ready_for_validation":
                accepted.append(candidate)
                continue
            rows = [source_lookup(source["step_id"]) for source in candidate["sources"]]
            payload = candidate["proposed_payload"]
            row_eligible = (
                eligible_failure_row
                if candidate["candidate_type"] == "recovery_rule"
                else eligible_row
            )
            row_group_key = (
                recovery_group_key
                if candidate["candidate_type"] == "recovery_rule"
                else action_group_key
            )
            replay_passed = (
                len({row["session_id"] for row in rows}) == candidate["support_count"]
                and all(row_eligible(row) for row in rows)
                and all(row_group_key(row) == payload["group_key"] for row in rows)
                and all(row["outcome_type"] in payload["expected_outcomes"] for row in rows)
                and all(row["progress_label"] in payload["expected_progress"] for row in rows)
            )
            validation = {
                "validation_id": stable_id(
                    "staging_replay", candidate["candidate_id"], *sorted(source["step_id"] for source in candidate["sources"])
                ),
                # The fixed contract enum is retained, while the validator
                # version and metrics state the narrower, truthful meaning.
                "kind": "deterministic_replay",
                "validator_kind": "rule",
                "validator_version": "source-consistency-replay-v2",
                "result": "passed" if replay_passed else "failed",
                "metrics": {
                    "validation_scope": "source_consistency_only",
                    "replayed_support_steps": len(rows),
                    "fixed_evaluation_cases": 0,
                },
                "evidence_refs": [source["step_id"] for source in candidate["sources"]],
            }
            candidate["validation_runs"].append(validation)
            if replay_passed:
                candidate["status"] = "accepted"
                candidate["proposed_payload"]["apply_eligible"] = True
            accepted.append(candidate)
    finally:
        if runtime_context is not None:
            runtime_context.close()
    validate_candidates(accepted, contract)
    write_jsonl(args.output, accepted)
    counts: dict[str, int] = defaultdict(int)
    for candidate in accepted:
        counts[candidate["status"]] += 1
    print(
        json.dumps(
            {"output": str(args.output), "candidates": len(accepted), "status": counts},
            ensure_ascii=False,
            default=dict,
        )
    )


def run_fixed_evaluation(
    *,
    retrieval_db: Path,
    cases_db: Path,
    output: Path,
) -> dict[str, Any]:
    evaluator = ROOT / "scripts" / "Evaluate-NavigationRuntimeOffline.py"
    subprocess.run(
        [
            sys.executable,
            str(evaluator),
            "--db",
            str(retrieval_db),
            "--cases-db",
            str(cases_db),
            "--output",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def validate_validation_case_split(report: Mapping[str, Any]) -> None:
    if int(report.get("case_count") or 0) <= 0:
        raise ValueError("fixed validation replay contains no cases")
    splits = set(report.get("by_app_split", {}))
    if splits != {"validation"}:
        raise ValueError(
            "activation regression must use only validation apps; "
            f"observed splits={sorted(splits)}"
        )


def compare_regression_reports(
    baseline: Mapping[str, Any],
    staging: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    validate_validation_case_split(baseline)
    validate_validation_case_split(staging)
    if baseline.get("evaluation_cases_sha256") != staging.get("evaluation_cases_sha256"):
        raise ValueError("baseline and staging did not use the same frozen validation cases")
    if baseline.get("case_count") != staging.get("case_count"):
        raise ValueError("fixed validation replay case count changed between runs")
    failures: list[str] = []
    for metric in (
        "positive_exact_next_action_accuracy",
        "positive_first_action_accuracy",
        "failed_click_avoidance_rate",
        "recognized_goal_rate",
    ):
        before = baseline.get(metric)
        after = staging.get(metric)
        if before is None and after is None:
            continue
        if before is None or after is None or float(after) < float(before):
            failures.append(f"{metric} regressed: {before} -> {after}")
    if int(staging.get("dangerous_auto_click_count") or 0) != 0:
        failures.append("staging replay selected a dangerous automatic click")
    return not failures, failures


def command_regression(args: argparse.Namespace) -> None:
    manifest = verify_generation(args.generation_dir)
    projection = json.loads(args.projection_report.read_text(encoding="utf-8"))
    if projection.get("generation_id") != manifest["generation_id"]:
        raise ValueError("projection report generation mismatch")
    if projection.get("staging_decision_sha256") != file_sha256(args.staging_db):
        raise ValueError("staging DB no longer matches its projection report")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        baseline = run_fixed_evaluation(
            retrieval_db=args.baseline_db,
            cases_db=args.cases_db,
            output=temporary_path / "baseline.json",
        )
        staging = run_fixed_evaluation(
            retrieval_db=args.staging_db,
            cases_db=args.cases_db,
            output=temporary_path / "staging.json",
        )
    passed, failures = compare_regression_reports(baseline, staging)
    report = {
        "schema_version": "1.0",
        "kind": "fixed_validation_regression_replay",
        "generation_id": manifest["generation_id"],
        "status": "passed" if passed else "failed",
        "locked_holdout_used": False,
        "evaluation_cases_sha256": baseline["evaluation_cases_sha256"],
        "case_count": baseline["case_count"],
        "baseline": baseline,
        "staging": staging,
        "failures": failures,
        "created_at": now(),
    }
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    if not passed:
        raise SystemExit(2)


def verify_sqlite(path: Path) -> None:
    with closing(
        sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    ) as connection:
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError(f"SQLite quick_check failed: {path}")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError(f"SQLite foreign-key check failed: {path}")


def replace_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    shutil.copy2(source, temporary)
    verify_sqlite(temporary)
    os.replace(temporary, target)


def command_activate(args: argparse.Namespace) -> None:
    manifest = verify_generation(args.generation_dir)
    regression = json.loads(args.regression_report.read_text(encoding="utf-8"))
    if regression.get("kind") != "fixed_validation_regression_replay":
        raise ValueError("activation requires a fixed validation regression report")
    if regression.get("generation_id") != manifest["generation_id"]:
        raise ValueError("regression report generation mismatch")
    if regression.get("status") != "passed":
        raise ValueError("only a passed fixed validation regression may be activated")
    if regression.get("locked_holdout_used") is not False:
        raise ValueError("locked holdout results cannot be used for promotion activation")
    validate_validation_case_split(regression["staging"])
    projection = json.loads(args.projection_report.read_text(encoding="utf-8"))
    if projection.get("generation_id") != manifest["generation_id"]:
        raise ValueError("projection report generation mismatch")
    staging_hash = file_sha256(args.staging_db)
    if projection.get("staging_decision_sha256") != staging_hash:
        raise ValueError("staging DB hash mismatch")
    baseline_metrics = regression.get("baseline", {})
    staging_metrics = regression.get("staging", {})
    if staging_metrics.get("database_sha256") != staging_hash:
        raise ValueError("regression report was not produced from this staging DB")
    if staging_metrics.get("evaluation_kind") != "fixed_validation_leave_source_app_out_replay":
        raise ValueError("regression report is not a fixed validation replay")
    if (
        baseline_metrics.get("evaluation_cases_sha256")
        != staging_metrics.get("evaluation_cases_sha256")
        or regression.get("evaluation_cases_sha256")
        != staging_metrics.get("evaluation_cases_sha256")
    ):
        raise ValueError("regression report validation-case identity mismatch")
    if args.backup.exists():
        raise FileExistsError(f"activation backup already exists: {args.backup}")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    previous_hash = file_sha256(args.operating_db)
    shutil.copy2(args.operating_db, args.backup)
    verify_sqlite(args.backup)
    replace_sqlite(args.staging_db, args.operating_db)
    active_hash = file_sha256(args.operating_db)
    if active_hash != staging_hash:
        raise ValueError("activated DB hash does not match staging projection")
    receipt = {
        "schema_version": "1.0",
        "kind": "navigation_generation_activation",
        "status": "active",
        "generation_id": manifest["generation_id"],
        "activated_at": now(),
        "operating_db": str(args.operating_db.resolve()),
        "operating_db_sha256": active_hash,
        "previous_db_sha256": previous_hash,
        "backup": str(args.backup.resolve()),
        "backup_sha256": file_sha256(args.backup),
        "regression_report_sha256": file_sha256(args.regression_report),
        "projection_report_sha256": file_sha256(args.projection_report),
    }
    atomic_write_json(args.active_pointer, receipt)
    write_json(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False))


def command_rollback(args: argparse.Namespace) -> None:
    activation = json.loads(args.activation_receipt.read_text(encoding="utf-8"))
    if activation.get("kind") != "navigation_generation_activation":
        raise ValueError("invalid activation receipt")
    operating_db = Path(activation["operating_db"])
    backup = Path(activation["backup"])
    if file_sha256(operating_db) != activation["operating_db_sha256"]:
        raise ValueError("operating DB changed after activation; refusing blind rollback")
    if file_sha256(backup) != activation["backup_sha256"]:
        raise ValueError("activation backup hash mismatch")
    replaced_hash = file_sha256(operating_db)
    replace_sqlite(backup, operating_db)
    receipt = {
        "schema_version": "1.0",
        "kind": "navigation_generation_rollback",
        "status": "rolled_back",
        "generation_id": activation["generation_id"],
        "rolled_back_at": now(),
        "operating_db": str(operating_db.resolve()),
        "operating_db_sha256": file_sha256(operating_db),
        "replaced_db_sha256": replaced_hash,
        "activation_receipt_sha256": file_sha256(args.activation_receipt),
    }
    atomic_write_json(args.active_pointer, receipt)
    write_json(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False))


def command_apply(args: argparse.Namespace) -> None:
    if not args.allow_legacy_direct_apply:
        raise ValueError(
            "legacy direct apply is disabled by default; use build-generation, project, "
            "regression, and activate (or pass --allow-legacy-direct-apply explicitly)"
        )
    print(
        "WARNING: legacy Runtime-to-Decision direct apply bypasses immutable App Knowledge generation",
        file=sys.stderr,
    )
    contract = load_contract(args.contract)
    candidates = read_jsonl(args.input)
    validate_candidates(candidates, contract)
    selected = [
        candidate
        for candidate in candidates
        if candidate["status"] == "accepted"
        and candidate["proposed_payload"].get("apply_eligible") is True
        and any(
            run.get("kind") == "deterministic_replay" and run.get("result") == "passed"
            for run in candidate.get("validation_runs", [])
        )
    ]
    if not selected:
        raise ValueError("no accepted promotion candidates")
    args.backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.decision_db, args.backup)
    applied: list[dict[str, Any]] = []
    with closing(sqlite3.connect(args.decision_db)) as decision, closing(
        sqlite3.connect(args.runtime_db)
    ) as runtime:
        decision.execute("PRAGMA foreign_keys=ON")
        decision.execute("BEGIN IMMEDIATE")
        try:
            for candidate in selected:
                case_ids = apply_candidate(decision, runtime, candidate)
                applied_candidate = json.loads(json.dumps(candidate))
                generation_id = stable_id("generation", candidate["candidate_id"], *case_ids)
                applied_candidate["target_entity_id"] = generation_id
                applied_candidate["status"] = "applied"
                applied_candidate["promotion"] = {
                    "promotion_id": stable_id("promotion", candidate["candidate_id"]),
                    "target_entity_type": (
                        "recovery_rule_generation"
                        if candidate["candidate_type"] == "recovery_rule"
                        else "decision_case_generation"
                    ),
                    "target_entity_id": generation_id,
                    "target_generation_id": generation_id,
                    "decision": "accepted",
                    "reviewer_kind": "replay_gate",
                    "decision_reason": (
                        "repeated real-device failures produced the same grounded recovery rule with no contradiction"
                        if candidate["candidate_type"] == "recovery_rule"
                        else "repeated real-device action units advanced navigation with no contradiction"
                    ),
                    "rollback_of_promotion_id": None,
                    "decided_at": now(),
                }
                applied_candidate["proposed_payload"]["applied_case_ids"] = case_ids
                applied.append(applied_candidate)
            validate_candidates(applied, contract)
            decision.commit()
        except Exception:
            decision.rollback()
            raise
    write_jsonl(args.output, applied)
    print(json.dumps({"output": str(args.output), "applied_candidates": len(applied), "backup": str(args.backup)}, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Promote verified Runtime action units")
    result.add_argument(
        "--contract",
        type=Path,
        default=ROOT / "db" / "contracts" / "shared_app_knowledge_v0_9_1" / "knowledge-promotion.v1.json",
    )
    commands = result.add_subparsers(dest="command", required=True)

    export_episode = commands.add_parser(
        "export-episode",
        help="normalize Runtime rows into interaction-episode.v1",
    )
    export_episode.add_argument("--runtime-db", type=Path, required=True)
    export_episode.add_argument("--session", action="append", required=True)
    export_episode.add_argument("--output", type=Path, required=True)
    export_episode.set_defaults(handler=command_export_episode)

    generate = commands.add_parser("generate")
    generate_source = generate.add_mutually_exclusive_group(required=True)
    generate_source.add_argument("--episodes", type=Path)
    generate_source.add_argument("--runtime-db", type=Path)
    generate.add_argument("--session", action="append")
    generate.add_argument("--allow-legacy-runtime-input", action="store_true")
    generate.add_argument("--output", type=Path, required=True)
    generate.set_defaults(handler=command_generate)

    accept = commands.add_parser("accept")
    accept_source = accept.add_mutually_exclusive_group(required=True)
    accept_source.add_argument("--episodes", type=Path)
    accept_source.add_argument("--runtime-db", type=Path)
    accept.add_argument("--allow-legacy-runtime-input", action="store_true")
    accept.add_argument("--input", type=Path, required=True)
    accept.add_argument("--output", type=Path, required=True)
    accept.set_defaults(handler=command_accept)

    build_generation = commands.add_parser(
        "build-generation",
        help="seal accepted evidence into an immutable App Knowledge generation",
    )
    build_generation.add_argument("--episodes", type=Path, required=True)
    build_generation.add_argument("--input", type=Path, required=True)
    build_generation.add_argument("--base-decision-db", type=Path, required=True)
    build_generation.add_argument("--output-root", type=Path, required=True)
    build_generation.add_argument("--parent-generation-id")
    build_generation.set_defaults(handler=command_build_generation)

    project = commands.add_parser(
        "project",
        help="project a sealed generation to a staging Decision DB without Runtime access",
    )
    project.add_argument("--generation-dir", type=Path, required=True)
    project.add_argument("--output", type=Path, required=True)
    project.add_argument("--report", type=Path, required=True)
    project.add_argument("--overwrite-staging", action="store_true")
    project.set_defaults(handler=command_project)

    regression = commands.add_parser(
        "regression",
        help="compare baseline and staging using one frozen validation-only case DB",
    )
    regression.add_argument("--generation-dir", type=Path, required=True)
    regression.add_argument("--projection-report", type=Path, required=True)
    regression.add_argument("--baseline-db", type=Path, required=True)
    regression.add_argument("--staging-db", type=Path, required=True)
    regression.add_argument("--cases-db", type=Path, required=True)
    regression.add_argument("--output", type=Path, required=True)
    regression.set_defaults(handler=command_regression)

    activate = commands.add_parser(
        "activate",
        help="atomically activate a regression-approved staging projection",
    )
    activate.add_argument("--generation-dir", type=Path, required=True)
    activate.add_argument("--projection-report", type=Path, required=True)
    activate.add_argument("--regression-report", type=Path, required=True)
    activate.add_argument("--staging-db", type=Path, required=True)
    activate.add_argument("--operating-db", type=Path, required=True)
    activate.add_argument("--backup", type=Path, required=True)
    activate.add_argument("--active-pointer", type=Path, required=True)
    activate.add_argument("--receipt", type=Path, required=True)
    activate.set_defaults(handler=command_activate)

    rollback = commands.add_parser(
        "rollback",
        help="restore the exact pre-activation Decision DB from an activation receipt",
    )
    rollback.add_argument("--activation-receipt", type=Path, required=True)
    rollback.add_argument("--active-pointer", type=Path, required=True)
    rollback.add_argument("--receipt", type=Path, required=True)
    rollback.set_defaults(handler=command_rollback)

    apply = commands.add_parser("apply")
    apply.add_argument("--runtime-db", type=Path, required=True)
    apply.add_argument("--decision-db", type=Path, required=True)
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--backup", type=Path, required=True)
    apply.add_argument("--allow-legacy-direct-apply", action="store_true")
    apply.set_defaults(handler=command_apply)
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.handler(arguments)
