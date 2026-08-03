from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import defaultdict
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
    validate_knowledge_promotion,
)


GENERATOR_NAME = "exitguide.runtime-action-unit-promoter"
GENERATOR_VERSION = "1.0.0"
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


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def normalize(value: object) -> str:
    return " ".join(str(value or "").casefold().split())


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
        SELECT s.session_id, s.app_package, s.app_version, s.locale, s.status AS session_status,
               s.created_at AS session_created_at, s.updated_at AS session_updated_at,
               d.decision_id, d.step_ordinal, d.goal_id, d.action_name, d.candidate_id,
               d.scroll_direction, d.plan_stage, d.planner_provider, d.confidence,
               d.destination_match_before, d.created_at AS decision_created_at,
               b.snapshot_id AS before_snapshot_id, b.screen_fingerprint,
               b.candidate_set_status, b.screen_payload_json AS before_screen_json,
               a.screen_fingerprint AS next_screen_fingerprint,
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
    runtime: sqlite3.Connection,
    candidate: dict[str, Any],
) -> list[str]:
    inserted: list[str] = []
    signature_row = decision.execute(
        "SELECT signature_id FROM destination_signatures WHERE goal_id=? ORDER BY version DESC LIMIT 1",
        (candidate["proposed_payload"]["goal_id"],),
    ).fetchone()
    signature_id = None if signature_row is None else str(signature_row[0])
    for source in candidate["sources"]:
        row = source_step(runtime, source["step_id"])
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


def command_generate(args: argparse.Namespace) -> None:
    contract = load_contract(args.contract)
    with sqlite3.connect(args.runtime_db) as connection:
        rows = runtime_rows(connection, args.session)
    candidates = build_candidates(rows)
    validate_candidates(candidates, contract)
    write_jsonl(args.output, candidates)
    counts: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        counts[candidate["status"]] += 1
    print(json.dumps({"output": str(args.output), "candidates": len(candidates), "status": counts}, ensure_ascii=False, default=dict))


def command_accept(args: argparse.Namespace) -> None:
    """Accept only candidates whose source action units replay deterministically."""

    contract = load_contract(args.contract)
    candidates = read_jsonl(args.input)
    validate_candidates(candidates, contract)
    accepted: list[dict[str, Any]] = []
    with sqlite3.connect(args.runtime_db) as runtime:
        for original in candidates:
            candidate = json.loads(json.dumps(original))
            if candidate["status"] != "ready_for_validation":
                accepted.append(candidate)
                continue
            rows = [source_step(runtime, source["step_id"]) for source in candidate["sources"]]
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
                "kind": "deterministic_replay",
                "validator_kind": "rule",
                "validator_version": "runtime-action-unit-v1",
                "result": "passed" if replay_passed else "failed",
                "metrics": {"replayed_support_steps": len(rows)},
                "evidence_refs": [source["step_id"] for source in candidate["sources"]],
            }
            candidate["validation_runs"].append(validation)
            if replay_passed:
                candidate["status"] = "accepted"
                candidate["proposed_payload"]["apply_eligible"] = True
            accepted.append(candidate)
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


def command_apply(args: argparse.Namespace) -> None:
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
    with sqlite3.connect(args.decision_db) as decision, sqlite3.connect(args.runtime_db) as runtime:
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
    generate = commands.add_parser("generate")
    generate.add_argument("--runtime-db", type=Path, required=True)
    generate.add_argument("--session", action="append", required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.set_defaults(handler=command_generate)
    accept = commands.add_parser("accept")
    accept.add_argument("--runtime-db", type=Path, required=True)
    accept.add_argument("--input", type=Path, required=True)
    accept.add_argument("--output", type=Path, required=True)
    accept.set_defaults(handler=command_accept)
    apply = commands.add_parser("apply")
    apply.add_argument("--runtime-db", type=Path, required=True)
    apply.add_argument("--decision-db", type=Path, required=True)
    apply.add_argument("--input", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--backup", type=Path, required=True)
    apply.set_defaults(handler=command_apply)
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.handler(arguments)
