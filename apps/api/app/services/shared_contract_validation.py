from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


NAVIGATION_ALLOWED_ACTIONS = frozenset(
    {"click", "scroll", "back", "wait_and_observe", "stop_for_user"}
)
NAVIGATION_ACTION_FIELDS = frozenset({"type", "name", "candidate_id", "direction"})
CANDIDATE_ACTIONS = frozenset({"click", "long_press", "input_text", "toggle", "select"})
TRANSPORT_FAILURES = frozenset({"device_disconnected", "transport_error", "executor_error"})
SUBSTANTIVE_VALIDATIONS = frozenset(
    {"deterministic_replay", "holdout_replay", "real_device", "human_review", "consistency_check"}
)
HIGH_RISK_VALIDATIONS = frozenset({"holdout_replay", "real_device", "human_review"})


class ContractSemanticError(ValueError):
    pass


def validate_interaction_episode(payload: Mapping[str, Any]) -> None:
    errors: list[str] = []
    steps = _list(payload.get("steps"))
    seen_step_ids: set[str] = set()
    seen_ordinals: set[int] = set()
    for index, raw_step in enumerate(steps):
        step = _mapping(raw_step)
        prefix = f"steps[{index}]"
        step_id = str(step.get("step_id") or "")
        ordinal = step.get("ordinal")
        if not step_id or step_id in seen_step_ids:
            errors.append(f"{prefix}.step_id must be non-empty and unique")
        seen_step_ids.add(step_id)
        if not isinstance(ordinal, int) or ordinal in seen_ordinals:
            errors.append(f"{prefix}.ordinal must be an integer unique within the episode")
        else:
            seen_ordinals.add(ordinal)
            if ordinal != index:
                errors.append(f"{prefix}.ordinal must be contiguous and match array order")

        before = _mapping(step.get("before"))
        after = step.get("after")
        for label, observation in (("before", before), ("after", after)):
            if observation is None:
                continue
            observation_id = str(_mapping(observation).get("observation_id") or "")
            if not observation_id:
                errors.append(f"{prefix}.{label}.observation_id must be non-empty")
        if after is not None and before.get("observation_id") == _mapping(after).get("observation_id"):
            errors.append(f"{prefix}.before and after must identify different captures")

        candidates = [_mapping(value) for value in _list(step.get("candidates"))]
        candidate_ids = [str(candidate.get("candidate_id") or "") for candidate in candidates]
        if any(not candidate_id for candidate_id in candidate_ids):
            errors.append(f"{prefix}.candidates contains an empty candidate_id")
        if len(candidate_ids) != len(set(candidate_ids)):
            errors.append(f"{prefix}.candidate_id values must be unique")
        selected = [candidate for candidate in candidates if candidate.get("selected") is True]
        candidate_set_status = step.get("candidate_set_status")
        if candidate_set_status == "unavailable" and candidates:
            errors.append(f"{prefix}.candidates must be empty when candidate_set_status=unavailable")

        action = _mapping(step.get("selected_action"))
        action_type = str(action.get("type") or "")
        candidate_id = action.get("candidate_id")
        if action_type in CANDIDATE_ACTIONS:
            if not isinstance(candidate_id, str) or not candidate_id:
                errors.append(f"{prefix}.selected_action {action_type} requires candidate_id")
            if candidate_set_status == "unavailable":
                if selected:
                    errors.append(f"{prefix} unavailable candidate set cannot mark a candidate selected")
            else:
                if candidate_id not in candidate_ids:
                    errors.append(f"{prefix}.selected_action candidate_id was not observed")
                if len(selected) != 1:
                    errors.append(f"{prefix} must mark exactly one candidate as selected")
                elif selected[0].get("candidate_id") != candidate_id:
                    errors.append(f"{prefix}.selected candidate must match selected_action.candidate_id")
                if selected and selected[0].get("forbidden") is True:
                    errors.append(f"{prefix} cannot select a forbidden candidate")
        else:
            if candidate_id is not None:
                errors.append(f"{prefix}.selected_action {action_type} must not carry candidate_id")
            if selected:
                errors.append(f"{prefix} non-candidate action must not mark a candidate selected")

        execution = _mapping(step.get("execution"))
        if execution.get("status") in TRANSPORT_FAILURES:
            if after is not None:
                errors.append(f"{prefix}.after must be null after transport or executor failure")
            if execution.get("outcome_type") != "unknown":
                errors.append(f"{prefix}.outcome_type must be unknown after transport or executor failure")
            if execution.get("progress_label") != "unknown":
                errors.append(f"{prefix}.progress_label must be unknown after transport or executor failure")
            if execution.get("destination_match_after") is not None:
                errors.append(f"{prefix}.destination_match_after must be null without an observation")
            if execution.get("distance_after") is not None:
                errors.append(f"{prefix}.distance_after must be null without an observation")

        rlds = _mapping(step.get("rlds"))
        if bool(rlds.get("is_first")) != (index == 0):
            errors.append(f"{prefix}.rlds.is_first does not match step order")
        if rlds.get("is_terminal") is True and rlds.get("is_last") is not True:
            errors.append(f"{prefix}.rlds.is_terminal requires is_last=true")
        if rlds.get("is_terminal") is True and rlds.get("discount") != 0:
            errors.append(f"{prefix}.rlds terminal step requires discount=0")
        if index < len(steps) - 1 and rlds.get("is_last") is True:
            errors.append(f"{prefix}.rlds.is_last can only be true on the final step")

    terminal_episode = payload.get("status") in {"completed", "failed", "aborted", "expired"}
    if terminal_episode and steps:
        final_rlds = _mapping(_mapping(steps[-1]).get("rlds"))
        if final_rlds.get("is_last") is not True:
            errors.append("the final step of a closed episode requires rlds.is_last=true")
    if payload.get("outcome") == "success" and steps:
        final_execution = _mapping(_mapping(steps[-1]).get("execution"))
        if final_execution.get("status") in TRANSPORT_FAILURES:
            errors.append("a successful episode cannot end with a transport or executor failure")

    _raise_errors(errors)


def validate_knowledge_promotion(payload: Mapping[str, Any]) -> None:
    promotion = _mapping(payload.get("promotion"))
    decision = promotion.get("decision")
    rollback_of = promotion.get("rollback_of_promotion_id")
    if decision == "rolled_back":
        if not isinstance(rollback_of, str) or not rollback_of:
            raise ContractSemanticError(
                "rolled_back promotion requires rollback_of_promotion_id"
            )
    elif promotion and rollback_of is not None:
        raise ContractSemanticError(
            "only rolled_back promotion may carry rollback_of_promotion_id"
        )

    status = payload.get("status")
    if status not in {"accepted", "applied"}:
        return

    errors: list[str] = []
    support_count = _integer(payload.get("support_count"))
    contradiction_count = _integer(payload.get("contradiction_count"))
    confidence = _number(payload.get("confidence"))
    if support_count <= 0:
        errors.append("accepted knowledge requires positive support_count")
    if support_count <= contradiction_count:
        errors.append("support_count must be greater than contradiction_count")
    if confidence < 0.6:
        errors.append("accepted knowledge requires confidence >= 0.6")

    passed_kinds = {
        str(run.get("kind"))
        for run in (_mapping(value) for value in _list(payload.get("validation_runs")))
        if run.get("result") == "passed"
    }
    if not passed_kinds & SUBSTANTIVE_VALIDATIONS:
        errors.append("accepted knowledge requires a passed substantive validation")
    if payload.get("risk_class") in {"high", "critical"} and not passed_kinds & HIGH_RISK_VALIDATIONS:
        errors.append("high-risk knowledge requires passed holdout, real-device, or human validation")

    if payload.get("candidate_type") == "transition":
        has_complete_source = any(
            source.get("support_kind") == "positive"
            and isinstance(source.get("step_id"), str)
            and bool(source.get("step_id"))
            and source.get("candidate_set_status") == "complete"
            for source in (_mapping(value) for value in _list(payload.get("sources")))
        )
        if not has_complete_source:
            errors.append("transition knowledge requires positive source with complete candidate set")

    if status == "applied":
        if promotion.get("decision") != "accepted":
            errors.append("applied knowledge requires an accepted promotion record")
        if not promotion.get("target_generation_id"):
            errors.append("applied knowledge requires target_generation_id")

    _raise_errors(errors)


def validate_app_knowledge(payload: Mapping[str, Any]) -> None:
    """Validate cross-references that JSON Schema cannot express cleanly."""

    errors: list[str] = []
    goals = _unique_ids(payload, "goals", "goal_id", errors)
    capabilities = _unique_ids(payload, "capabilities", "capability_id", errors)
    concepts = _unique_ids(payload, "screen_concepts", "concept_id", errors)
    screens = _unique_ids(payload, "app_screens", "app_screen_id", errors)
    affordances = _unique_ids(payload, "affordances", "affordance_id", errors)
    transitions = _unique_ids(payload, "transitions", "transition_id", errors)
    _unique_ids(payload, "recovery_rules", "recovery_id", errors)

    for item in (_mapping(value) for value in _list(payload.get("capabilities"))):
        if item.get("goal_id") not in goals:
            errors.append(f"capability {item.get('capability_id')} references unknown goal")
    for item in (_mapping(value) for value in _list(payload.get("app_screens"))):
        concept_id = item.get("concept_id")
        if concept_id is not None and concept_id not in concepts:
            errors.append(f"app screen {item.get('app_screen_id')} references unknown concept")
    for item in (_mapping(value) for value in _list(payload.get("affordances"))):
        if item.get("app_screen_id") not in screens:
            errors.append(f"affordance {item.get('affordance_id')} references unknown screen")
    for item in (_mapping(value) for value in _list(payload.get("transitions"))):
        transition_id = item.get("transition_id")
        capability_id = item.get("capability_id")
        if capability_id is not None and capability_id not in capabilities:
            errors.append(f"transition {transition_id} references unknown capability")
        if item.get("from_screen_id") not in screens:
            errors.append(f"transition {transition_id} references unknown from screen")
        to_screen_id = item.get("to_screen_id")
        if to_screen_id is not None and to_screen_id not in screens:
            errors.append(f"transition {transition_id} references unknown to screen")
        affordance_id = _mapping(item.get("action")).get("affordance_id")
        if affordance_id is not None and affordance_id not in affordances:
            errors.append(f"transition {transition_id} references unknown affordance")
    for item in (_mapping(value) for value in _list(payload.get("recovery_rules"))):
        recovery_id = item.get("recovery_id")
        goal_id = item.get("goal_id")
        if goal_id is not None and goal_id not in goals:
            errors.append(f"recovery rule {recovery_id} references unknown goal")
        concept_id = item.get("screen_concept_id")
        if concept_id is not None and concept_id not in concepts:
            errors.append(f"recovery rule {recovery_id} references unknown concept")
        affordance_id = item.get("forbidden_affordance_id")
        if affordance_id is not None and affordance_id not in affordances:
            errors.append(f"recovery rule {recovery_id} references unknown affordance")
    for item in (_mapping(value) for value in _list(payload.get("procedures"))):
        for step in (_mapping(value) for value in _list(item.get("steps"))):
            transition_id = step.get("transition_id")
            if transition_id is not None and transition_id not in transitions:
                errors.append(f"procedure {item.get('procedure_id')} references unknown transition")
    _raise_errors(errors)


def validate_navigation_action(
    action: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> None:
    unexpected_fields = set(action) - NAVIGATION_ACTION_FIELDS
    if unexpected_fields:
        raise ContractSemanticError(
            "navigation action contains unexpected arguments: "
            + ", ".join(sorted(unexpected_fields))
        )
    if action.get("type") and action.get("name") and action.get("type") != action.get("name"):
        raise ContractSemanticError("navigation action type and name must match")

    action_type = str(action.get("type") or action.get("name") or "")
    if action_type not in NAVIGATION_ALLOWED_ACTIONS:
        raise ContractSemanticError(f"navigation action is not allowed by safe-five policy: {action_type}")

    candidate_id = action.get("candidate_id")
    direction = action.get("direction")
    if action_type == "click":
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ContractSemanticError("click requires candidate_id")
        matches = [candidate for candidate in candidates if candidate.get("candidate_id") == candidate_id]
        if len(matches) != 1:
            raise ContractSemanticError("click candidate_id must exist exactly once on the current screen")
        if matches[0].get("forbidden") is True:
            raise ContractSemanticError("click candidate is forbidden")
        if matches[0].get("terminal") is True or matches[0].get("dangerous_final") is True:
            raise ContractSemanticError(
                "dangerous or terminal click must be replaced with stop_for_user"
            )
        if matches[0].get("risk_class") in {"critical", "blocked"}:
            raise ContractSemanticError(
                "critical or blocked click must be replaced with stop_for_user"
            )
        if direction is not None:
            raise ContractSemanticError("click forbids direction")
    elif action_type == "scroll":
        if direction not in {"up", "down"}:
            raise ContractSemanticError("scroll requires direction up or down")
        if candidate_id is not None:
            raise ContractSemanticError("scroll forbids candidate_id")
    elif candidate_id is not None or direction is not None:
        raise ContractSemanticError(f"{action_type} accepts no arguments")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _unique_ids(
    payload: Mapping[str, Any],
    collection: str,
    field: str,
    errors: list[str],
) -> set[str]:
    values = [
        str(item.get(field) or "")
        for item in (_mapping(value) for value in _list(payload.get(collection)))
    ]
    if any(not value for value in values):
        errors.append(f"{collection} contains an empty {field}")
    if len(values) != len(set(values)):
        errors.append(f"{collection} contains duplicate {field}")
    return {value for value in values if value}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _raise_errors(errors: Sequence[str]) -> None:
    if errors:
        raise ContractSemanticError("; ".join(errors))
