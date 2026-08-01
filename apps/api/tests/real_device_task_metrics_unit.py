from __future__ import annotations

from app.services.real_device_task_metrics import (
    TaskMetricError,
    build_task_summary_metric,
)


def _state() -> dict[str, object]:
    return {
        "action_count": 7,
        "scroll_count": 2,
        "back_count": 1,
        "elapsed_seconds": 12.5,
        "screen_visits": {"a": 1, "b": 3},
    }


def _expect_error(code: str, **overrides: object) -> None:
    values: dict[str, object] = {
        "task_id": "task_one",
        "app_package": "com.example.app",
        "goal_id": "goal_one",
        "terminal_status": "destination_reached",
        "state": _state(),
        "attempt_number": 1,
    }
    values.update(overrides)
    try:
        build_task_summary_metric(**values)  # type: ignore[arg-type]
    except TaskMetricError as error:
        assert str(error) == code, (str(error), code)
    else:
        raise AssertionError(f"expected {code}")


def main() -> None:
    candidate = build_task_summary_metric(
        task_id="task_one",
        app_package="com.example.app",
        goal_id="goal_one",
        goal_candidate_id="goal_candidate_one",
        goal_family_id="subscription_manage",
        terminal_policy="navigation_only",
        terminal_status="destination_reached",
        state=_state(),
        attempt_number=2,
        external_api_transfer_count=4,
    )
    assert candidate["metric_dimension"] == "task_summary"
    assert candidate["candidate_destination_found"] is True
    assert candidate["human_confirmed_success"] is None
    assert "success_count" not in candidate
    assert "false_positive_count" not in candidate
    assert candidate["click_count"] == 4
    assert candidate["scroll_count"] == 2
    assert candidate["back_count"] == 1
    assert candidate["repeat_screen_visit_count"] == 2
    assert candidate["exploration_time_ms"] == 12500.0
    assert candidate["external_api_transfer_count"] == 4

    reviewed = build_task_summary_metric(
        task_id="task_one",
        app_package="com.example.app",
        goal_id="goal_one",
        terminal_status="destination_reached",
        state=_state(),
        attempt_number=3,
        human_confirmed_success=True,
        human_confirmed_false_positive=False,
    )
    assert reviewed["success_count"] == 1
    assert reviewed["false_positive_count"] == 0

    boundary = build_task_summary_metric(
        task_id="task_two",
        app_package="com.example.app",
        goal_id="goal_login",
        terminal_status="boundary:password_boundary",
        state={
            "action_count": 1,
            "scroll_count": 0,
            "back_count": 0,
            "elapsed_seconds": 1,
            "screen_visits": {"a": 1},
        },
        attempt_number=1,
    )
    assert boundary["completion_class"] == "user_boundary"
    assert boundary["user_intervention_count"] == 1

    discovery = build_task_summary_metric(
        task_id="task_discovery",
        app_package="com.example.app",
        goal_id="goal_discovery",
        terminal_status="discovery_budget_complete",
        state=_state(),
        attempt_number=1,
    )
    assert discovery["completion_class"] == "discovery_budget_complete"
    assert discovery["candidate_destination_found"] is False

    _expect_error(
        "human_success_without_candidate_destination",
        terminal_status="failed:ObserveApiError",
        human_confirmed_success=True,
    )
    _expect_error(
        "action_subcount_invalid",
        state={
            "action_count": 1,
            "scroll_count": 2,
            "back_count": 0,
            "elapsed_seconds": 1,
            "screen_visits": {},
        },
    )
    _expect_error("attempt_number_invalid", attempt_number=0)
    _expect_error("human_confirmed_success_invalid", human_confirmed_success=1)

    print("Real-device task metric checks ok")


if __name__ == "__main__":
    main()
