from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

from .models import ProcedureHint


def object_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="json"))
    if is_dataclass(value):
        return asdict(value)
    result: dict[str, Any] = {}
    for name in (
        "name",
        "candidate_id",
        "element_id",
        "direction",
        "label",
        "clickable",
        "enabled",
        "risk_level",
        "selected",
        "operation",
        "terminal",
        "dangerous_final",
        "state_changing",
        "inferred_function_roles",
    ):
        if hasattr(value, name):
            result[name] = getattr(value, name)
    return result


def action_mapping(action: Any) -> dict[str, Any]:
    payload = object_mapping(action)
    return {
        key: payload[key]
        for key in ("name", "candidate_id", "direction")
        if key in payload and payload[key] is not None
    }


def construct_action(action_type: type[Any], payload: Mapping[str, Any]) -> Any:
    values = {
        key: payload[key]
        for key in ("name", "candidate_id", "direction")
        if key in payload and payload[key] is not None
    }
    return action_type(**values)


def build_policy_facts(
    *,
    goal_id: str | None,
    proposed_action: Any,
    candidates: Sequence[Any],
    forbidden_candidate_ids: set[str] | None = None,
    screen_trusted: bool,
    screen_facts: Mapping[str, Any] | None = None,
    procedure_hint: ProcedureHint | None = None,
    terms_constraint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    action = action_mapping(proposed_action)
    candidate_id = str(action.get("candidate_id", ""))
    candidate_payload: dict[str, Any] | None = None
    for item in candidates:
        payload = object_mapping(item)
        observed_id = str(payload.get("candidate_id", payload.get("element_id", "")))
        if observed_id == candidate_id:
            candidate_payload = payload
            break

    candidate_payload = candidate_payload or {}
    candidate_operation = candidate_payload.get("operation")
    goal_operation = goal_id.rsplit(".", 1)[-1] if goal_id and "." in goal_id else None
    operation_match: bool | None = None
    if candidate_operation and goal_operation:
        operation_match = str(candidate_operation) == goal_operation

    terminal = bool(
        candidate_payload.get("terminal", False)
        or candidate_payload.get("dangerous_final", False)
    )
    state_changing = bool(candidate_payload.get("state_changing", False) or terminal)
    candidate_observed = bool(candidate_payload) if action.get("name") == "click" else True

    facts: dict[str, Any] = {
        "goal_id": goal_id,
        "goal_operation": goal_operation,
        "goal_candidate_operation_match": operation_match,
        "screen": {"trusted": bool(screen_trusted), **dict(screen_facts or {})},
        "candidate": {
            "candidate_id": candidate_id or None,
            "observed": candidate_observed,
            "clickable": bool(candidate_payload.get("clickable", False)),
            "enabled": bool(candidate_payload.get("enabled", False)),
            "forbidden": candidate_id in (forbidden_candidate_ids or set()),
            "risk_level": str(candidate_payload.get("risk_level", "unknown")),
            "terminal": terminal,
            "state_changing": state_changing,
            "operation": candidate_operation,
            "roles": list(candidate_payload.get("inferred_function_roles", [])),
        },
        "procedure": {
            "procedure_id": procedure_hint.procedure_id if procedure_hint else None,
            "step_ordinal": procedure_hint.step_ordinal if procedure_hint else None,
        },
        "terms": {
            "required": False,
            "status": "not_applicable",
            "blocked": False,
            **dict(terms_constraint or {}),
        },
        "confirmation": {"valid": False},
    }
    return facts


def build_procedure_screen_facts(
    query: Any,
    *,
    destination_threshold: float,
) -> dict[str, Any]:
    query_payload = object_mapping(query)
    screen = getattr(query, "screen", None)
    screen_payload = object_mapping(screen) if screen is not None else {}
    candidates = getattr(screen, "candidate_payloads", ()) if screen is not None else ()
    roles: set[str] = set()
    for candidate in candidates:
        payload = object_mapping(candidate)
        for role in payload.get("inferred_function_roles", []):
            roles.add(str(role))
    destination_match = float(
        getattr(query, "destination_match", query_payload.get("destination_match", 0.0)) or 0.0
    )
    account_hub_signals = {
        "account.settings",
        "membership.hub",
        "billing.manage",
        "privacy.settings",
        "account.delete.entry",
    }
    membership_hub_signals = {
        "membership.cancel.entry",
        "membership.change.entry",
        "membership.join.entry",
    }
    return {
        "auth_state": screen_payload.get("auth_state", getattr(screen, "auth_state", "unknown")),
        "roles_present": sorted(roles),
        "account_hub_reached": bool(roles & account_hub_signals),
        "membership_hub_reached": bool(roles & membership_hub_signals),
        "terminal_boundary_reached": destination_match >= destination_threshold,
        "destination_match": destination_match,
    }


def merge_procedure_hint(plan: Any, hint: ProcedureHint | None) -> Any:
    if hint is None or not hint.enforced:
        return plan
    payload = object_mapping(plan)
    target_roles = list(payload.get("target_roles", []))
    # Only an app/version/locale-scoped, repeatedly validated procedure may
    # inject a role into the deterministic fast path. Hint-only procedures
    # still refine the model-visible subgoal and completion rule.
    if (
        hint.fast_path_eligible
        and hint.preferred_role_id
        and hint.preferred_role_id not in target_roles
    ):
        target_roles.insert(0, hint.preferred_role_id)
    updates = {
        "target_roles": target_roles[:6],
        "immediate_subgoal": hint.immediate_subgoal,
        "completion_rule": _completion_text(hint.completion_check),
    }
    if hasattr(plan, "model_copy"):
        return plan.model_copy(update=updates)
    payload.update(updates)
    return payload


def procedure_fast_path_matches(
    *,
    hint: ProcedureHint | None,
    candidate_id: str | None,
    candidate_payloads: Sequence[Mapping[str, Any]],
    role_score_floor: float = 0.95,
) -> bool:
    """Prove that a model-free click came from the recalled procedure role."""

    if (
        hint is None
        or not hint.fast_path_eligible
        or not hint.preferred_role_id
        or not candidate_id
    ):
        return False
    for candidate in candidate_payloads:
        if str(candidate.get("candidate_id", "")) != candidate_id:
            continue
        role_scores = candidate.get("function_role_scores", {})
        return bool(
            isinstance(role_scores, Mapping)
            and float(role_scores.get(hint.preferred_role_id, 0.0)) >= role_score_floor
            and str(candidate.get("risk_level", "low")) == "low"
            and bool(candidate.get("clickable", True))
            and bool(candidate.get("enabled", True))
            and not bool(candidate.get("dangerous_final", False))
        )
    return False


def _completion_text(completion_check: Mapping[str, Any]) -> str:
    label = completion_check.get("description")
    if isinstance(label, str) and label.strip():
        return label.strip()
    return "Observe the next screen and evaluate the procedure step completion predicate."
