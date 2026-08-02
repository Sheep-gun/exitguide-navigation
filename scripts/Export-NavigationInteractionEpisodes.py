from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACTS = ROOT / "db" / "contracts" / "shared_app_knowledge_v0_9_1"
INTERACTION_SCHEMA_NAME = "interaction-episode.v1.json"
CROSSWALK_NAME = "navigation-goal-crosswalk.v1.json"
CROSSWALK_SCHEMA_NAME = "navigation-goal-crosswalk.v1.schema.json"
ADAPTER_VERSION = "navigation-interaction-adapter/v0.9.1"
DEFAULT_LOCALE = "ko-KR"
LANGUAGE_TAG_PATTERN = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
SAFE_ACTIONS = {"click", "scroll", "back", "wait_and_observe", "stop_for_user"}
TRANSPORT_FAILURES = {"device_disconnected", "transport_error", "executor_error"}
REQUIRED_TABLES = {
    "navigation_db_metadata",
    "semantic_screens",
    "screen_observations",
    "affordances",
    "decision_cases",
    "transition_outcomes",
    "evidence_records",
    "experience_episodes",
    "experience_steps",
}
LEGACY_REQUIRED_TABLES = {
    "navigation_training_examples",
    "universal_exploration_attempts",
    "universal_actions",
}

sys.path.insert(0, str(ROOT / "apps" / "api"))
from app.services.shared_contract_validation import (  # noqa: E402
    ContractSemanticError,
    validate_interaction_episode,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rfc3339(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("a source timestamp is required")
    text = text.replace(" ", "T", 1)
    if text.endswith("Z") or re.search(r"[+-]\d\d:\d\d$", text):
        return text
    return f"{text}+00:00"


def language_tag(value: str | None) -> str:
    candidate = str(value or DEFAULT_LOCALE).strip().replace("_", "-")
    return candidate if LANGUAGE_TAG_PATTERN.fullmatch(candidate) else DEFAULT_LOCALE


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def verify_source(connection: sqlite3.Connection) -> dict[str, str]:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != 2:
        raise ValueError(f"source must be Navigation Decision DB schema version 2, got {version}")
    available = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = sorted(REQUIRED_TABLES - available)
    if missing:
        raise ValueError(f"source is missing required tables: {', '.join(missing)}")
    metadata = dict(connection.execute("SELECT key,value FROM navigation_db_metadata"))
    if metadata.get("standards_profile") != "exitguide.navigation-experience.v1":
        raise ValueError("source does not carry the Navigation Experience Profile v1")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("source failed SQLite quick_check")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("source contains foreign-key violations")
    return metadata


def verify_legacy_source(
    connection: sqlite3.Connection,
    *,
    actual_sha256: str,
    expected_sha256: str,
) -> None:
    available = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = sorted(LEGACY_REQUIRED_TABLES - available)
    if missing:
        raise ValueError(f"legacy source is missing required tables: {', '.join(missing)}")
    if not expected_sha256:
        raise ValueError("Decision DB does not declare its upstream legacy source SHA-256")
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "legacy source SHA-256 does not match the Decision DB provenance: "
            f"{actual_sha256} != {expected_sha256}"
        )
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise ValueError("legacy source failed SQLite quick_check")


def load_contracts(contracts_root: Path) -> tuple[dict[str, Any], dict[str, str], str]:
    schema_path = contracts_root / INTERACTION_SCHEMA_NAME
    crosswalk_path = contracts_root / CROSSWALK_NAME
    crosswalk_schema_path = contracts_root / CROSSWALK_SCHEMA_NAME
    if not schema_path.is_file() or not crosswalk_path.is_file() or not crosswalk_schema_path.is_file():
        raise FileNotFoundError(f"missing v0.9.1 contracts under {contracts_root}")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    crosswalk_payload = json.loads(crosswalk_path.read_text(encoding="utf-8"))
    crosswalk_schema = json.loads(crosswalk_schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(crosswalk_schema)
    Draft202012Validator(
        crosswalk_schema, format_checker=FormatChecker()
    ).validate(crosswalk_payload)
    mappings = {
        str(row["source_goal_id"]): str(row["target_goal_id"])
        for row in crosswalk_payload.get("mappings", [])
        if row.get("mapping_type") == "exact"
    }
    if not mappings:
        raise ValueError("goal crosswalk contains no exact mappings")
    contract_digest = hashlib.sha256(
        schema_path.read_bytes()
        + b"\x00"
        + crosswalk_path.read_bytes()
        + b"\x00"
        + crosswalk_schema_path.read_bytes()
    ).hexdigest()
    return schema, mappings, contract_digest


def source_rows(connection: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    rows = connection.execute(
        """
        SELECT
            ep.episode_id AS profile_episode_id,
            ep.source_type AS episode_source_type,
            ep.source_record_id AS episode_source_record_id,
            ep.source_app_package AS episode_app_package,
            ep.app_version AS episode_app_version,
            ep.language_tag AS episode_language_tag,
            ep.split_version,
            ep.split,
            ep.started_at,
            ep.ended_at,
            ep.end_reason,
            ep.metadata_json AS episode_metadata_json,
            es.step_index,
            es.is_first,
            es.is_last,
            es.is_terminal,
            es.reward,
            es.discount,
            c.*,
            COALESCE((
                SELECT er.source_ref
                FROM evidence_records AS er
                WHERE er.entity_type='decision_case' AND er.entity_id=c.case_id
                ORDER BY er.confidence DESC, er.verification_count DESC, er.evidence_id
                LIMIT 1
            ), '') AS decision_source_ref,
            a.candidate_key AS selected_candidate_key,
            a.normalized_label AS selected_label,
            a.icon_semantics AS selected_icon_semantics,
            a.role AS selected_role,
            a.function_roles_json AS selected_function_roles_json,
            o.outcome_id,
            o.next_screen_id,
            o.outcome_type,
            o.connectivity_status,
            o.state_changed,
            o.destination_match_before,
            o.destination_match_after,
            o.distance_before,
            o.distance_after,
            o.distance_method,
            o.progress_label,
            o.failure_class,
            o.external_target,
            o.observed_at AS outcome_observed_at
        FROM experience_episodes AS ep
        JOIN experience_steps AS es ON es.episode_id=ep.episode_id
        JOIN decision_cases AS c ON c.case_id=es.case_id
        JOIN transition_outcomes AS o ON o.case_id=c.case_id
        LEFT JOIN affordances AS a ON a.affordance_id=c.chosen_affordance_id
        ORDER BY ep.episode_id, es.step_index, c.case_id
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        grouped[str(row["profile_episode_id"])].append(row)
    return grouped


def best_observation(
    connection: sqlite3.Connection,
    *,
    screen_id: str,
    app_package: str,
    source_type: str,
    reference_time: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT so.*, ss.semantic_fingerprint
        FROM screen_observations AS so
        JOIN semantic_screens AS ss ON ss.screen_id=so.screen_id
        WHERE so.screen_id=? AND so.app_package=?
        ORDER BY
            CASE WHEN so.source_type=? THEN 0 ELSE 1 END,
            ABS(julianday(so.captured_at)-julianday(?)),
            so.captured_at DESC,
            so.observation_id
        LIMIT 1
        """,
        (screen_id, app_package, source_type, reference_time),
    ).fetchone()


def observation_payload(
    connection: sqlite3.Connection,
    *,
    case_id: str,
    phase: str,
    screen_id: str,
    app_package: str,
    source_type: str,
    reference_time: str,
) -> dict[str, Any]:
    row = best_observation(
        connection,
        screen_id=screen_id,
        app_package=app_package,
        source_type=source_type,
        reference_time=reference_time,
    )
    if row is None:
        raise ValueError(f"{case_id}: no observation for {phase} screen {screen_id}")
    return {
        "observation_id": stable_id("observation", case_id, phase, row["observation_id"]),
        "screen_fingerprint": str(row["semantic_fingerprint"]),
        "matched_app_screen_id": None,
        "accessibility_summary": json_object(row["accessibility_json"]),
        "ocr_summary": json_object(row["ocr_json"]),
        "vision_summary": json_object(row["vlm_json"]),
        "screenshot_ref": None,
        "ui_tree_ref": None,
        "privacy_status": "synthetic" if source_type == "synthetic" else "redacted",
        "captured_at": rfc3339(row["captured_at"]),
    }


def immediate_subgoal(row: sqlite3.Row) -> str:
    action = str(row["chosen_action"])
    if action == "click":
        roles = [str(value) for value in json_list(row["selected_function_roles_json"]) if value]
        if roles:
            return f"follow_affordance:{roles[0]}"
        return "select_recorded_candidate"
    if action == "scroll":
        return f"reveal_candidates:{row['scroll_direction'] or 'unknown'}"
    if action == "back":
        return "recover_to_previous_screen"
    if action == "wait_and_observe":
        return "wait_for_state_change"
    return "handoff_before_user_decision"


def action_payload(row: sqlite3.Row) -> dict[str, Any]:
    action_type = str(row["chosen_action"])
    if action_type not in SAFE_ACTIONS:
        raise ValueError(f"{row['case_id']}: unsupported action {action_type}")
    if action_type == "click":
        candidate_id = str(row["selected_candidate_key"] or "")
        if not candidate_id:
            raise ValueError(f"{row['case_id']}: click has no recorded candidate key")
        return {"type": action_type, "candidate_id": candidate_id, "parameters": {}}
    if action_type == "scroll":
        direction = str(row["scroll_direction"] or "")
        if direction not in {"up", "down"}:
            raise ValueError(f"{row['case_id']}: invalid scroll direction {direction}")
        return {"type": action_type, "candidate_id": None, "parameters": {"direction": direction}}
    return {"type": action_type, "candidate_id": None, "parameters": {}}


def execution_payload(row: sqlite3.Row) -> dict[str, Any]:
    connectivity = str(row["connectivity_status"] or "not_observed")
    action_type = str(row["chosen_action"])
    status_by_connectivity = {
        "observed": "not_executed" if action_type == "stop_for_user" else "executed",
        "device_disconnected": "device_disconnected",
        "transport_error": "transport_error",
        "not_observed": "not_executed",
    }
    status = status_by_connectivity.get(connectivity, "executor_error")
    transport_failure = status in TRANSPORT_FAILURES
    return {
        "status": status,
        "safety_status": "not_applicable",
        "safety_reason": "legacy_import_without_executor_safety_trace",
        "outcome_type": "unknown" if transport_failure else str(row["outcome_type"] or "unknown"),
        "progress_label": "unknown" if transport_failure else str(row["progress_label"] or "unknown"),
        "failure_class": str(row["failure_class"] or ""),
        "external_target": str(row["external_target"]) if row["external_target"] else None,
        "destination_match_before": row["destination_match_before"],
        "destination_match_after": None if transport_failure else row["destination_match_after"],
        "distance_before": row["distance_before"],
        "distance_after": None if transport_failure else row["distance_after"],
        "distance_method": str(row["distance_method"] or ""),
        "reward": row["reward"],
    }


def source_element_key_hash(candidate: dict[str, Any]) -> str:
    source_id = str(candidate.get("element_id") or candidate.get("action_id") or "")
    element_key = str(candidate.get("element_key") or source_id)
    if not element_key:
        return ""
    return hashlib.sha256(element_key.encode("utf-8")).hexdigest()[:20]


def legacy_candidates_for_case(
    legacy_connection: sqlite3.Connection,
    row: sqlite3.Row,
) -> list[dict[str, Any]]:
    source_ref = str(row["decision_source_ref"] or "")
    if not source_ref:
        return []
    source_type = str(row["source_type"])
    if source_type == "human_gold":
        source = legacy_connection.execute(
            """
            SELECT candidates_json
            FROM navigation_training_examples
            WHERE example_id=? AND provenance='real_device_human_gold'
            """,
            (source_ref,),
        ).fetchone()
        if source is None:
            return []
        return [
            value
            for value in json_list(source["candidates_json"])
            if isinstance(value, dict)
        ]
    if source_type == "real_device":
        attempt = legacy_connection.execute(
            "SELECT screen_fingerprint FROM universal_exploration_attempts WHERE attempt_id=?",
            (source_ref,),
        ).fetchone()
        if attempt is None:
            return []
        return [
            dict(value)
            for value in legacy_connection.execute(
                """
                SELECT action_id AS element_id,element_key,label,role,risk_level,risk_reason
                FROM universal_actions
                WHERE screen_fingerprint=?
                ORDER BY action_id
                """,
                (attempt["screen_fingerprint"],),
            )
        ]
    return []


def candidate_inventory(
    connection: sqlite3.Connection,
    legacy_connection: sqlite3.Connection | None,
    row: sqlite3.Row,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    if legacy_connection is None:
        return "unavailable", [], {
            "source_candidate_count": None,
            "matched_candidate_count": 0,
            "target_affordance_count": int(
                connection.execute(
                    "SELECT COUNT(*) FROM affordances WHERE screen_id=?", (row["screen_id"],)
                ).fetchone()[0]
            ),
            "inventory_reason": "legacy_source_not_supplied",
        }

    source_candidates = legacy_candidates_for_case(legacy_connection, row)
    affordances = connection.execute(
        "SELECT * FROM affordances WHERE screen_id=? ORDER BY candidate_key",
        (row["screen_id"],),
    ).fetchall()
    source_by_hash: dict[str, dict[str, Any]] = {}
    duplicate_source_keys = False
    for candidate in source_candidates:
        key_hash = source_element_key_hash(candidate)
        if not key_hash or key_hash in source_by_hash:
            duplicate_source_keys = True
            continue
        source_by_hash[key_hash] = candidate
    affordance_by_hash: dict[str, sqlite3.Row] = {}
    duplicate_affordance_keys = False
    for affordance in affordances:
        key_hash = str(affordance["source_element_key"] or "")
        if not key_hash or key_hash in affordance_by_hash:
            duplicate_affordance_keys = True
            continue
        affordance_by_hash[key_hash] = affordance

    source_keys = set(source_by_hash)
    target_keys = set(affordance_by_hash)
    matched_keys = source_keys & target_keys
    exact = (
        not duplicate_source_keys
        and not duplicate_affordance_keys
        and len(source_candidates) == len(affordances)
        and len(source_by_hash) == len(source_candidates)
        and len(affordance_by_hash) == len(affordances)
        and source_keys == target_keys
    )
    status = "complete" if exact else "partial" if matched_keys else "unavailable"
    selected_candidate_key = str(row["selected_candidate_key"] or "")
    candidates: list[dict[str, Any]] = []
    for key_hash in sorted(matched_keys, key=lambda key: str(affordance_by_hash[key]["candidate_key"])):
        source = source_by_hash[key_hash]
        affordance = affordance_by_hash[key_hash]
        candidate_id = str(affordance["candidate_key"])
        dangerous_final = bool(affordance["dangerous_final"])
        risk_class = str(affordance["risk_level"] or "low")
        if risk_class not in {"low", "medium", "high", "critical", "blocked"}:
            risk_class = "low"
        source_element_id = str(source.get("element_id") or source.get("action_id") or "")
        candidates.append(
            {
                "candidate_id": candidate_id,
                "observed_payload": {
                    "label": str(affordance["label"] or ""),
                    "normalized_label": str(affordance["normalized_label"] or ""),
                    "role": str(affordance["role"] or "unknown"),
                    "icon_semantics": str(affordance["icon_semantics"] or ""),
                    "parent_semantics": str(affordance["parent_semantics"] or ""),
                    "nearby_text": str(affordance["nearby_text"] or ""),
                    "position_bucket": str(affordance["position_bucket"] or "unknown"),
                    "function_roles": json_list(affordance["function_roles_json"]),
                    "source_modality": "ocr" if source_element_id.startswith("ocr_") else "accessibility",
                },
                "matched_affordance_id": str(affordance["affordance_id"]),
                "memory_score": None,
                "verifier_score": None,
                "final_score": None,
                "risk_class": risk_class,
                "terminal": dangerous_final,
                "dangerous_final": dangerous_final,
                "forbidden": dangerous_final or risk_class in {"critical", "blocked"},
                "selected": bool(
                    str(row["chosen_action"]) == "click"
                    and candidate_id == selected_candidate_key
                ),
            }
        )

    selected_count = sum(candidate["selected"] is True for candidate in candidates)
    if str(row["chosen_action"]) == "click" and selected_count != 1:
        status, candidates = "unavailable", []
    return status, candidates, {
        "source_candidate_count": len(source_candidates),
        "matched_candidate_count": len(matched_keys),
        "target_affordance_count": len(affordances),
        "inventory_reason": (
            "exact_hash_key_match"
            if exact
            else "partial_hash_key_match"
            if matched_keys
            else "no_hash_key_match"
        ),
    }


def episode_status(end_reason: str) -> tuple[str, str]:
    return {
        "user_handoff": ("completed", "user_stopped"),
        "destination_reached": ("completed", "success"),
        "failed": ("failed", "failure"),
        "truncated": ("aborted", "unknown"),
        "unknown": ("completed", "partial"),
    }.get(end_reason, ("completed", "unknown"))


def build_episode(
    connection: sqlite3.Connection,
    rows: list[sqlite3.Row],
    goal_crosswalk: dict[str, str],
    legacy_connection: sqlite3.Connection | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    first = rows[0]
    legacy_goal_id = str(first["goal_id"])
    if legacy_goal_id not in goal_crosswalk:
        raise ValueError(f"unmapped Navigation goal ID: {legacy_goal_id}")
    end_reason = str(first["end_reason"])
    status, outcome = episode_status(end_reason)
    source_type = str(first["episode_source_type"])
    source_record_id = str(first["episode_source_record_id"])
    app_package = str(first["episode_app_package"])
    episode_id = stable_id("interaction_episode", source_type, source_record_id)
    steps: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []

    for ordinal, row in enumerate(rows):
        case_id = str(row["case_id"])
        before = observation_payload(
            connection,
            case_id=case_id,
            phase="before",
            screen_id=str(row["screen_id"]),
            app_package=app_package,
            source_type=source_type,
            reference_time=str(row["observed_at"]),
        )
        connectivity = str(row["connectivity_status"] or "not_observed")
        after = None
        if connectivity == "observed" and row["next_screen_id"]:
            after = observation_payload(
                connection,
                case_id=case_id,
                phase="after",
                screen_id=str(row["next_screen_id"]),
                app_package=app_package,
                source_type=source_type,
                reference_time=str(row["outcome_observed_at"] or row["observed_at"]),
            )
        step_id = stable_id("interaction_step", case_id)
        action = action_payload(row)
        candidate_set_status, candidates, inventory_audit = candidate_inventory(
            connection, legacy_connection, row
        )
        is_last = ordinal == len(rows) - 1
        is_terminal = bool(is_last and int(row["is_terminal"] or 0))
        step = {
            "step_id": step_id,
            "ordinal": ordinal,
            "plan_stage": "legacy_recorded_navigation",
            "immediate_subgoal": immediate_subgoal(row),
            "before": before,
            "candidate_set_status": candidate_set_status,
            "candidates": candidates,
            "selected_action": action,
            "execution": execution_payload(row),
            "after": after,
            "retrieval_hits": [],
            "model_calls": [],
            "rlds": {
                "is_first": ordinal == 0,
                "is_last": is_last,
                "is_terminal": is_terminal,
                "discount": 0.0 if is_terminal else 1.0,
            },
            "latency_ms": {},
        }
        steps.append(step)
        mappings.append(
            {
                "source_case_id": case_id,
                "source_step_ordinal": int(row["source_step_ordinal"]),
                "source_profile_step_index": int(row["step_index"]),
                "source_affordance_id": row["chosen_affordance_id"],
                "source_candidate_key": row["selected_candidate_key"],
                "episode_id": episode_id,
                "step_id": step_id,
                "exported_ordinal": ordinal,
                "candidate_set_status": candidate_set_status,
                "promotion_validation_eligible": candidate_set_status == "complete",
                **inventory_audit,
            }
        )

    user_intent = str(first["goal_text_normalized"] or "").strip()
    if not user_intent:
        user_intent = f"redacted_navigation_goal:{legacy_goal_id}"
    episode = {
        "schema_version": "1.0",
        "episode_id": episode_id,
        "request_id": stable_id("request", source_type, source_record_id),
        "session_id": stable_id("session", source_type, source_record_id),
        "context": {
            "app_id": None,
            "app_package": app_package,
            "app_version": str(first["episode_app_version"] or ""),
            "platform": "android",
            "locale": language_tag(first["episode_language_tag"]),
            "goal_id": goal_crosswalk[legacy_goal_id],
            "user_intent_redacted": user_intent,
            "agent_version": ADAPTER_VERSION,
            "navigation_generation_id": None,
            "terms_generation_id": None,
            "device_context": {
                "source_database_kind": "navigation_decision_memory",
                "source_profile": "exitguide.navigation-experience.v1",
                "source_type": source_type,
                "source_record_id": source_record_id,
                "evaluation_split_version": str(first["split_version"]),
                "evaluation_split": str(first["split"]),
                "legacy_goal_id": legacy_goal_id,
                "candidate_inventory": "not_recorded",
            },
        },
        "status": status,
        "outcome": outcome,
        "steps": steps,
        "started_at": rfc3339(first["started_at"]),
        "finished_at": rfc3339(first["ended_at"]),
    }
    return episode, mappings


def semantic_errors(episode: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    steps = episode["steps"]
    step_ids: set[str] = set()
    for index, step in enumerate(steps):
        prefix = f"{episode['episode_id']}.steps[{index}]"
        if step["step_id"] in step_ids:
            errors.append(f"{prefix}: duplicate step_id")
        step_ids.add(step["step_id"])
        if step["ordinal"] != index:
            errors.append(f"{prefix}: non-contiguous ordinal")
        if step["candidate_set_status"] == "unavailable" and step["candidates"]:
            errors.append(f"{prefix}: unavailable candidate set must be empty")
        action = step["selected_action"]
        if action["type"] == "click" and not action["candidate_id"]:
            errors.append(f"{prefix}: click requires recorded candidate_id")
        if action["type"] != "click" and action["candidate_id"] is not None:
            errors.append(f"{prefix}: non-click action must not carry candidate_id")
        if step["rlds"]["is_first"] != (index == 0):
            errors.append(f"{prefix}: incorrect is_first")
        if step["rlds"]["is_last"] != (index == len(steps) - 1):
            errors.append(f"{prefix}: incorrect is_last")
        if step["rlds"]["is_terminal"] and step["rlds"]["discount"] != 0:
            errors.append(f"{prefix}: terminal step requires discount=0")
        execution = step["execution"]
        if execution["status"] in TRANSPORT_FAILURES:
            if step["after"] is not None:
                errors.append(f"{prefix}: transport failure cannot have after observation")
            if execution["outcome_type"] != "unknown" or execution["progress_label"] != "unknown":
                errors.append(f"{prefix}: transport failure cannot claim navigation outcome")
    return errors


def round_trip_errors(
    connection: sqlite3.Connection,
    episodes: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    goal_crosswalk: dict[str, str],
) -> list[str]:
    errors: list[str] = []
    episode_by_id = {episode["episode_id"]: episode for episode in episodes}
    for mapping in mappings:
        row = connection.execute(
            """
            SELECT c.*, a.candidate_key, o.outcome_type, o.connectivity_status,
                   o.progress_label, o.destination_match_before, o.destination_match_after,
                   o.distance_before, o.distance_after
            FROM decision_cases AS c
            JOIN transition_outcomes AS o ON o.case_id=c.case_id
            LEFT JOIN affordances AS a ON a.affordance_id=c.chosen_affordance_id
            WHERE c.case_id=?
            """,
            (mapping["source_case_id"],),
        ).fetchone()
        if row is None:
            errors.append(f"missing source case {mapping['source_case_id']}")
            continue
        episode = episode_by_id[mapping["episode_id"]]
        step = episode["steps"][mapping["exported_ordinal"]]
        checks = {
            "goal_id": (episode["context"]["goal_id"], goal_crosswalk[str(row["goal_id"])]),
            "action": (step["selected_action"]["type"], str(row["chosen_action"])),
            "candidate": (
                step["selected_action"]["candidate_id"],
                str(row["candidate_key"]) if row["chosen_action"] == "click" else None,
            ),
            "direction": (
                step["selected_action"]["parameters"].get("direction"),
                str(row["scroll_direction"]) if row["chosen_action"] == "scroll" else None,
            ),
            "outcome_type": (
                step["execution"]["outcome_type"],
                "unknown" if row["connectivity_status"] in {"device_disconnected", "transport_error"} else str(row["outcome_type"]),
            ),
            "progress_label": (
                step["execution"]["progress_label"],
                "unknown" if row["connectivity_status"] in {"device_disconnected", "transport_error"} else str(row["progress_label"]),
            ),
            "destination_match_before": (step["execution"]["destination_match_before"], row["destination_match_before"]),
            "distance_before": (step["execution"]["distance_before"], row["distance_before"]),
        }
        for field, (actual, expected) in checks.items():
            if actual != expected:
                errors.append(f"{row['case_id']}: {field} {actual!r} != {expected!r}")
        if mapping["candidate_set_status"] == "complete":
            expected_candidate_ids = {
                str(value[0])
                for value in connection.execute(
                    "SELECT candidate_key FROM affordances WHERE screen_id=?",
                    (row["screen_id"],),
                )
            }
            actual_candidate_ids = {
                str(candidate["candidate_id"]) for candidate in step["candidates"]
            }
            if actual_candidate_ids != expected_candidate_ids:
                errors.append(f"{row['case_id']}: complete candidate inventory changed")
            selected_ids = [
                str(candidate["candidate_id"])
                for candidate in step["candidates"]
                if candidate["selected"] is True
            ]
            expected_selected = [str(row["candidate_key"])] if row["chosen_action"] == "click" else []
            if selected_ids != expected_selected:
                errors.append(
                    f"{row['case_id']}: selected candidate flags {selected_ids!r} != {expected_selected!r}"
                )
    return errors


def export(
    source: Path,
    contracts_root: Path,
    output: Path,
    report_path: Path,
    *,
    legacy_source: Path | None = None,
    require_complete_candidates: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    source = source.resolve()
    contracts_root = contracts_root.resolve()
    output = output.resolve()
    report_path = report_path.resolve()
    legacy_source = legacy_source.resolve() if legacy_source is not None else None
    if not source.is_file():
        raise FileNotFoundError(source)
    if legacy_source is not None and not legacy_source.is_file():
        raise FileNotFoundError(legacy_source)
    for target in (output, report_path):
        if target.exists() and not force:
            raise FileExistsError(f"refusing to overwrite generated artifact: {target}")
        if target == source:
            raise ValueError("generated output must not overwrite the source database")
        if legacy_source is not None and target == legacy_source:
            raise ValueError("generated output must not overwrite the legacy source database")

    source_hash_before = file_sha256(source)
    legacy_hash_before = file_sha256(legacy_source) if legacy_source is not None else None
    schema, goal_crosswalk, contract_digest = load_contracts(contracts_root)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    connection = open_read_only(source)
    legacy_connection: sqlite3.Connection | None = None
    try:
        metadata = verify_source(connection)
        if legacy_source is not None:
            legacy_connection = open_read_only(legacy_source)
            verify_legacy_source(
                legacy_connection,
                actual_sha256=str(legacy_hash_before),
                expected_sha256=metadata.get("upstream_legacy_source_sha256", ""),
            )
        grouped = source_rows(connection)
        episodes: list[dict[str, Any]] = []
        mappings: list[dict[str, Any]] = []
        for profile_episode_id in sorted(grouped):
            episode, episode_mappings = build_episode(
                connection, grouped[profile_episode_id], goal_crosswalk, legacy_connection
            )
            episodes.append(episode)
            mappings.extend(episode_mappings)

        schema_errors: list[str] = []
        semantic_validation_errors: list[str] = []
        for episode in episodes:
            for error in sorted(validator.iter_errors(episode), key=lambda value: list(value.path)):
                path = ".".join(str(part) for part in error.path)
                schema_errors.append(f"{episode['episode_id']}:{path}: {error.message}")
            semantic_validation_errors.extend(semantic_errors(episode))
            try:
                validate_interaction_episode(episode)
            except ContractSemanticError as error:
                semantic_validation_errors.append(
                    f"{episode['episode_id']}: shared v0.9.1 validator: {error}"
                )
        roundtrip = round_trip_errors(connection, episodes, mappings, goal_crosswalk)
        incomplete = [
            mapping for mapping in mappings if mapping["candidate_set_status"] != "complete"
        ]
        if require_complete_candidates and incomplete:
            raise ValueError(
                f"strict candidate inventory requested but {len(incomplete)} steps are incomplete"
            )
        source_counts = {
            "decision_cases": int(connection.execute("SELECT COUNT(*) FROM decision_cases").fetchone()[0]),
            "transition_outcomes": int(connection.execute("SELECT COUNT(*) FROM transition_outcomes").fetchone()[0]),
            "experience_episodes": int(connection.execute("SELECT COUNT(*) FROM experience_episodes").fetchone()[0]),
            "experience_steps": int(connection.execute("SELECT COUNT(*) FROM experience_steps").fetchone()[0]),
        }
    finally:
        if legacy_connection is not None:
            legacy_connection.close()
        connection.close()

    source_hash_after = file_sha256(source)
    legacy_hash_after = file_sha256(legacy_source) if legacy_source is not None else None
    if source_hash_before != source_hash_after:
        raise RuntimeError("source database changed during read-only export")
    if legacy_hash_before != legacy_hash_after:
        raise RuntimeError("legacy source database changed during read-only export")
    if schema_errors or semantic_validation_errors or roundtrip:
        details = schema_errors + semantic_validation_errors + roundtrip
        raise ValueError("interaction export validation failed: " + "; ".join(details[:10]))

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(episode, ensure_ascii=False, sort_keys=True) + "\n" for episode in episodes),
        encoding="utf-8",
    )
    goal_counts = Counter(episode["context"]["goal_id"] for episode in episodes)
    action_counts = Counter(
        step["selected_action"]["type"] for episode in episodes for step in episode["steps"]
    )
    source_type_counts = Counter(
        episode["context"]["device_context"]["source_type"] for episode in episodes
    )
    candidate_status_counts = Counter(
        str(mapping["candidate_set_status"]) for mapping in mappings
    )
    complete_steps = candidate_status_counts.get("complete", 0)
    limitations = [
        "retrieval hits, model calls, latency, and executor safety traces were not recorded",
        "legacy mojibake is preserved rather than guessed or silently repaired",
        "complete candidate inventory permits promotion validation but never automatic promotion",
    ]
    if legacy_source is None:
        limitations.insert(
            0, "legacy source was not supplied, so complete on-screen candidates were unavailable"
        )
    report = {
        "schema_version": "1.0",
        "adapter_version": ADAPTER_VERSION,
        "generated_at": utc_now(),
        "source": {
            "filename": source.name,
            "sha256": source_hash_before,
            "read_only": True,
            "preserved": source_hash_before == source_hash_after,
            "metadata": {
                key: metadata.get(key, "")
                for key in (
                    "database_kind",
                    "schema_version",
                    "standards_profile",
                    "standards_profile_version",
                    "upstream_legacy_source_sha256",
                )
            },
            "counts": source_counts,
        },
        "legacy_source": None
        if legacy_source is None
        else {
            "filename": legacy_source.name,
            "sha256": legacy_hash_before,
            "read_only": True,
            "preserved": legacy_hash_before == legacy_hash_after,
            "provenance_match": legacy_hash_before
            == metadata.get("upstream_legacy_source_sha256", ""),
        },
        "contract": {
            "version": "0.9.1",
            "interaction_schema": INTERACTION_SCHEMA_NAME,
            "goal_crosswalk": CROSSWALK_NAME,
            "combined_sha256": contract_digest,
        },
        "output": {
            "filename": output.name,
            "sha256": file_sha256(output),
            "episodes": len(episodes),
            "steps": sum(len(episode["steps"]) for episode in episodes),
            "candidate_set_status": {
                key: candidate_status_counts.get(key, 0)
                for key in ("unavailable", "partial", "complete")
            },
            "promotion_validation_eligible_steps": complete_steps,
            "automatically_promoted_steps": 0,
            "goal_counts": dict(sorted(goal_counts.items())),
            "action_counts": dict(sorted(action_counts.items())),
            "source_type_episode_counts": dict(sorted(source_type_counts.items())),
        },
        "validation": {
            "json_schema_errors": 0,
            "semantic_errors": 0,
            "round_trip_mismatches": 0,
            "source_hash_unchanged": True,
            "legacy_source_hash_unchanged": None
            if legacy_source is None
            else legacy_hash_before == legacy_hash_after,
            "passed": True,
        },
        "limitations": limitations,
        "step_mappings": mappings,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Navigation Decision DB v2 into shared interaction-episode v1 JSONL"
    )
    parser.add_argument("--source", type=Path, required=True, help="read-only Decision DB v2")
    parser.add_argument(
        "--legacy-source",
        type=Path,
        help="optional exact-hash legacy DB used to recover the original full candidate inventory",
    )
    parser.add_argument("--contracts-root", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--output", type=Path, required=True, help="new interaction episode JSONL")
    parser.add_argument("--report", type=Path, required=True, help="new validation/round-trip report")
    parser.add_argument(
        "--require-complete-candidates",
        action="store_true",
        help="fail without writing outputs unless every step has an exact full candidate inventory",
    )
    parser.add_argument("--force", action="store_true", help="overwrite only the two generated outputs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = export(
        args.source,
        args.contracts_root,
        args.output,
        args.report,
        legacy_source=args.legacy_source,
        require_complete_candidates=args.require_complete_candidates,
        force=args.force,
    )
    print(json.dumps({
        "passed": report["validation"]["passed"],
        "episodes": report["output"]["episodes"],
        "steps": report["output"]["steps"],
        "candidate_set_status": report["output"]["candidate_set_status"],
        "output_sha256": report["output"]["sha256"],
        "source_preserved": report["source"]["preserved"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
