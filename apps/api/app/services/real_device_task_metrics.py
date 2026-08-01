"""Deterministic terminal metrics for one physical-device exploration task."""

from __future__ import annotations

import re
from typing import Any, Mapping


MACHINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,191}$")
STATUS_RE = re.compile(r"^[a-z][a-z0-9_]*(?::[A-Za-z][A-Za-z0-9_]*)?$")


class TaskMetricError(ValueError):
    pass


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise TaskMetricError(f"{field}_invalid")
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as error:
        raise TaskMetricError(f"{field}_invalid") from error
    if number < 0:
        raise TaskMetricError(f"{field}_invalid")
    return number


def _nonnegative_float(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise TaskMetricError(f"{field}_invalid")
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError) as error:
        raise TaskMetricError(f"{field}_invalid") from error
    if number < 0.0 or number != number or number == float("inf"):
        raise TaskMetricError(f"{field}_invalid")
    return number


def _machine_id(value: object, field: str, *, optional: bool = False) -> str | None:
    text = str(value or "").strip()
    if optional and not text:
        return None
    if not MACHINE_ID_RE.fullmatch(text):
        raise TaskMetricError(f"{field}_invalid")
    return text


def _completion_class(status: str) -> str:
    if status == "destination_reached":
        return "candidate_destination_found"
    if status in {
        "captured",
        "dry_run_complete",
        "skipped_missing",
        "discovery_budget_complete",
        "discovery_frontier_exhausted",
    }:
        return status
    if status.startswith("boundary:"):
        return "user_boundary"
    if status.startswith("stopped:"):
        return "safe_stop"
    if status.startswith("failed:"):
        return "failed"
    raise TaskMetricError("terminal_status_invalid")


def build_task_summary_metric(
    *,
    task_id: object,
    app_package: object,
    goal_id: object,
    terminal_status: object,
    state: Mapping[str, Any],
    attempt_number: object,
    goal_candidate_id: object = None,
    goal_family_id: object = None,
    terminal_policy: object = None,
    external_api_transfer_count: object = 0,
    unsafe_auto_click_count: object = 0,
    final_action_auto_click_count: object = 0,
    human_confirmed_success: bool | None = None,
    human_confirmed_false_positive: bool | None = None,
) -> dict[str, Any]:
    """Build one non-cumulative, auditable metric row.

    A destination reached by automation is only a *candidate*.  Success and
    false-positive rates stay unavailable until a human explicitly reviews the
    result, preventing model self-assessment from inflating quality metrics.
    """

    if not isinstance(state, Mapping):
        raise TaskMetricError("state_invalid")
    task = _machine_id(task_id, "task_id")
    package = _machine_id(app_package, "app_package")
    goal = _machine_id(goal_id, "goal_id")
    status = str(terminal_status or "").strip()
    if not STATUS_RE.fullmatch(status):
        raise TaskMetricError("terminal_status_invalid")
    completion = _completion_class(status)
    attempt = _nonnegative_int(attempt_number, "attempt_number")
    if attempt < 1:
        raise TaskMetricError("attempt_number_invalid")

    action_count = _nonnegative_int(state.get("action_count"), "action_count")
    scroll_count = _nonnegative_int(state.get("scroll_count"), "scroll_count")
    back_count = _nonnegative_int(state.get("back_count"), "back_count")
    if scroll_count + back_count > action_count:
        raise TaskMetricError("action_subcount_invalid")
    visits = state.get("screen_visits") or {}
    if not isinstance(visits, Mapping):
        raise TaskMetricError("screen_visits_invalid")
    visit_counts = [_nonnegative_int(value, "screen_visit_count") for value in visits.values()]
    elapsed_seconds = _nonnegative_float(
        state.get("elapsed_seconds"), "elapsed_seconds"
    )
    unsafe_count = _nonnegative_int(
        unsafe_auto_click_count, "unsafe_auto_click_count"
    )
    final_count = _nonnegative_int(
        final_action_auto_click_count, "final_action_auto_click_count"
    )

    if human_confirmed_success is not None and not isinstance(
        human_confirmed_success, bool
    ):
        raise TaskMetricError("human_confirmed_success_invalid")
    if human_confirmed_false_positive is not None and not isinstance(
        human_confirmed_false_positive, bool
    ):
        raise TaskMetricError("human_confirmed_false_positive_invalid")
    if human_confirmed_success is True and completion != "candidate_destination_found":
        raise TaskMetricError("human_success_without_candidate_destination")

    payload: dict[str, Any] = {
        "metric_dimension": "task_summary",
        "task_id": task,
        "app_package": package,
        "goal_id": goal,
        "goal_candidate_id": _machine_id(
            goal_candidate_id, "goal_candidate_id", optional=True
        ),
        "goal_family_id": _machine_id(
            goal_family_id, "goal_family_id", optional=True
        ),
        "terminal_policy": _machine_id(
            terminal_policy, "terminal_policy", optional=True
        ),
        "terminal_status": status,
        "completion_class": completion,
        "attempt_number": attempt,
        "attempt_count": 1,
        "candidate_destination_found": completion == "candidate_destination_found",
        "human_confirmed_success": human_confirmed_success,
        "human_confirmed_false_positive": human_confirmed_false_positive,
        "exploration_time_ms": elapsed_seconds * 1000.0,
        "click_count": action_count - scroll_count - back_count,
        "scroll_count": scroll_count,
        "back_count": back_count,
        "repeat_screen_visit_count": sum(max(0, count - 1) for count in visit_counts),
        "user_intervention_count": int(completion == "user_boundary"),
        "external_api_transfer_count": _nonnegative_int(
            external_api_transfer_count, "external_api_transfer_count"
        ),
        "unsafe_auto_click_count": unsafe_count,
        "final_action_auto_click_count": final_count,
        "human_review_required": True,
        "self_assessed_success_forbidden": True,
    }
    if human_confirmed_success is not None:
        payload["success_count"] = int(human_confirmed_success)
    if human_confirmed_false_positive is not None:
        payload["false_positive_count"] = int(human_confirmed_false_positive)
    return payload
