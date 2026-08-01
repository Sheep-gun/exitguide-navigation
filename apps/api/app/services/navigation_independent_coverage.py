from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ALLOWED_ACTIONS = frozenset({"click", "scroll_forward", "back", "stop", "no_click"})
SAFE_AUTO_POLICIES = frozenset({"auto", "auto_safe", "safe_auto"})
REQUIRED_LOCALES = frozenset({"ko-KR", "en-US"})
REQUIRED_UI_SURFACES = frozenset(
    {"screen", "dialog", "drawer", "bottom_sheet", "webview", "scroll_view", "endless_feed", "system_dialog"}
)
REQUIRED_SCREEN_STATES = frozenset(
    {
        "ready",
        "loading",
        "offline",
        "error",
        "relogin_required",
        "permission_rationale",
        "stale_cache",
        "transient_error",
        "recovered",
        "confirmation_required",
        "repeated_content",
    }
)
REQUIRED_ELEMENT_STATES = frozenset(
    {"disabled", "invisible", "selected", "checkable", "scrollable", "icon_only", "dangerous"}
)
ABSTAIN_INTENT_ID = "__abstain__"


def audit_independent_coverage(
    *,
    catalog_path: Path,
    fixture_paths: Iterable[Path],
) -> dict[str, Any]:
    """Audit frozen, independently authored Gym evidence against the catalog.

    Coverage is evidence that a function is represented by at least one
    independently worded goal/screen, not evidence that the agent succeeds on
    it. Runtime accuracy remains a separate DB Gym metric.
    """

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    intents = {str(item["intent_id"]): item for item in catalog.get("intents", [])}
    functions = {str(item["function_id"]): item for item in catalog.get("functions", [])}
    errors: list[dict[str, str]] = []
    covered_intents: set[str] = set()
    covered_functions: set[str] = set()
    case_ids: set[str] = set()
    case_count = 0
    step_count = 0
    action_counts: Counter[str] = Counter()
    locale_counts: Counter[str] = Counter()
    surface_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    element_state_counts: Counter[str] = Counter()
    loaded_fixtures: list[dict[str, object]] = []

    for fixture_path in fixture_paths:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        split = str(payload.get("split", fixture_path.stem))
        if payload.get("frozen") is not True:
            errors.append(_error(split, "fixture_not_frozen", str(fixture_path)))
        if payload.get("catalog_derived") is not False:
            errors.append(_error(split, "fixture_not_independent", str(fixture_path)))
        cases = list(payload.get("cases", []))
        loaded_fixtures.append(
            {"path": str(fixture_path), "split": split, "case_count": len(cases)}
        )
        for case in cases:
            case_count += 1
            case_id = str(case.get("case_id", ""))
            if not case_id:
                errors.append(_error(split, "missing_case_id", ""))
            elif case_id in case_ids:
                errors.append(_error(split, "duplicate_case_id", case_id))
            case_ids.add(case_id)
            intent_id = str(case.get("intent_id", ""))
            valid_abstention = _is_valid_abstention_case(case, functions)
            if intent_id == ABSTAIN_INTENT_ID and valid_abstention:
                pass
            elif intent_id not in intents:
                errors.append(_error(split, "unknown_intent", f"{case_id}:{intent_id}"))
            elif intent_id:
                covered_intents.add(intent_id)
            locale_counts[str(case.get("locale", "unknown"))] += 1
            steps = list(case.get("steps", []))
            if not steps:
                errors.append(_error(split, "empty_route", case_id))
            for step_index, step in enumerate(steps):
                step_count += 1
                surface_counts[str(step.get("ui_surface", "screen"))] += 1
                state_counts[str(step.get("screen_state", "ready"))] += 1
                expected = dict(step.get("expected", {}))
                action = str(expected.get("action", ""))
                action_counts[action] += 1
                if action not in ALLOWED_ACTIONS:
                    errors.append(_error(split, "unknown_action", f"{case_id}:{action}"))
                function_id = str(expected.get("function_id", ""))
                function = functions.get(function_id)
                if function is None:
                    errors.append(_error(split, "unknown_function", f"{case_id}:{function_id}"))
                elif function_id:
                    covered_functions.add(function_id)
                    if (
                        action == "click"
                        and not _safe_for_automatic_click(function)
                        and not _has_later_guarded_boundary(steps, step_index, function_id)
                    ):
                        errors.append(_error(split, "unguarded_state_change_click", f"{case_id}:{function_id}"))
                expected_label = expected.get("label")
                for element in step.get("elements", []):
                    if (
                        action == "click"
                        and expected_label
                        and element.get("label") == expected_label
                        and bool(element.get("dangerous", False))
                    ):
                        errors.append(_error(split, "dangerous_element_click", f"{case_id}:{function_id}"))
                    if not bool(element.get("enabled", True)):
                        element_state_counts["disabled"] += 1
                    if not bool(element.get("visible", True)):
                        element_state_counts["invisible"] += 1
                    if bool(element.get("selected", False)):
                        element_state_counts["selected"] += 1
                    if bool(element.get("checkable", False)):
                        element_state_counts["checkable"] += 1
                    if bool(element.get("scrollable", False)):
                        element_state_counts["scrollable"] += 1
                    if element.get("content_description") and not element.get("label"):
                        element_state_counts["icon_only"] += 1
                    if bool(element.get("dangerous", False)):
                        element_state_counts["dangerous"] += 1

    missing_intents = sorted(set(intents).difference(covered_intents))
    missing_functions = sorted(set(functions).difference(covered_functions))
    for action in sorted(ALLOWED_ACTIONS.difference(action_counts)):
        errors.append(_error("aggregate", "missing_action_dimension", action))
    for locale in sorted(REQUIRED_LOCALES.difference(locale_counts)):
        errors.append(_error("aggregate", "missing_locale_dimension", locale))
    for surface in sorted(REQUIRED_UI_SURFACES.difference(surface_counts)):
        errors.append(_error("aggregate", "missing_ui_surface_dimension", surface))
    for state in sorted(REQUIRED_SCREEN_STATES.difference(state_counts)):
        errors.append(_error("aggregate", "missing_screen_state_dimension", state))
    for state in sorted(REQUIRED_ELEMENT_STATES.difference(element_state_counts)):
        errors.append(_error("aggregate", "missing_element_state_dimension", state))
    return {
        "schema_version": 1,
        "catalog_version": str(catalog.get("catalog_version", "")),
        "catalog_derived": False,
        "fixture_count": len(loaded_fixtures),
        "case_count": case_count,
        "step_count": step_count,
        "intent_total": len(intents),
        "intent_covered": len(covered_intents),
        "intent_coverage": _ratio(len(covered_intents), len(intents)),
        "function_total": len(functions),
        "function_covered": len(covered_functions),
        "function_coverage": _ratio(len(covered_functions), len(functions)),
        "missing_intents": missing_intents,
        "missing_functions": missing_functions,
        "action_counts": dict(sorted(action_counts.items())),
        "locale_counts": dict(sorted(locale_counts.items())),
        "ui_surface_counts": dict(sorted(surface_counts.items())),
        "screen_state_counts": dict(sorted(state_counts.items())),
        "element_state_counts": dict(sorted(element_state_counts.items())),
        "fixtures": loaded_fixtures,
        "error_count": len(errors),
        "errors": errors,
        "status": "pass" if not errors and not missing_intents and not missing_functions else "fail",
    }


def _safe_for_automatic_click(function: dict[str, object]) -> bool:
    if bool(function.get("state_changing", False)):
        return False
    if str(function.get("risk_level", "")).casefold() == "high":
        return False
    policy = str(function.get("automation_policy", "")).casefold()
    return policy in SAFE_AUTO_POLICIES or policy not in {"never_auto", "user_only", "manual"}


def _is_valid_abstention_case(
    case: dict[str, object],
    functions: dict[str, dict[str, object]],
) -> bool:
    """Accept a reserved abstention only at a real nonterminal no-click boundary."""

    if str(case.get("intent_id", "")) != ABSTAIN_INTENT_ID:
        return False
    steps = case.get("steps", [])
    if not isinstance(steps, list) or not steps:
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        expected = step.get("expected", {})
        if not isinstance(expected, dict) or str(expected.get("action", "")) != "no_click":
            return False
        function = functions.get(str(expected.get("function_id", "")))
        if function is None or bool(function.get("terminal", False)):
            return False
    return True


def _has_later_guarded_boundary(
    steps: list[dict[str, object]],
    step_index: int,
    function_id: str,
) -> bool:
    """A risky function may be entered, but its final control stays user-only."""

    for later_step in steps[step_index + 1 :]:
        expected = dict(later_step.get("expected", {}))
        if str(expected.get("action", "")) in {"stop", "no_click"}:
            return True
    return False


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _error(split: str, kind: str, detail: str) -> dict[str, str]:
    return {"split": split, "kind": kind, "detail": detail}
