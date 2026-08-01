import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


SETTINGS = Settings(
    navigation_agent_provider="mock",
    navigation_agent_allow_fallback=True,
)


def main() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        repository = UniversalNavigationGraphRepository(
            Path(temporary_directory) / "runtime-telemetry.sqlite"
        )
        assert_failed_executed_instructions_are_counted_once(repository)
        assert_success_and_cancel_are_not_wrong_guidance(repository)
        assert_unmatched_or_unexecuted_instructions_are_not_counted(repository)
        assert_detailed_stop_reason_is_persisted(repository)
        assert_runtime_summary_uses_executed_instruction_denominator(repository)
    print("navigation runtime telemetry checks ok")


def assert_failed_executed_instructions_are_counted_once(
    repository: UniversalNavigationGraphRepository,
) -> None:
    no_change = _execute_transition(
        repository,
        session_id="runtime-no-change",
        reported_outcome="navigated",
        moved=False,
    )
    assert no_change.performance is not None
    assert no_change.performance.executed_transition_outcome == "no_change"
    assert no_change.performance.wrong_guidance_delta == 1
    assert no_change.performance.wrong_click_delta == 1
    assert _session_counts(repository, "runtime-no-change") == (1, 1)

    # Retrying the same observation carries the same recommendation ID.  It is
    # one executed instruction, so delivery retries must not inflate counters.
    first = _first_instruction(repository, "runtime-idempotent")
    transition = _transition(first, outcome="failed")
    first_failure = _observe(
        repository,
        _request(
            request_id="runtime-idempotent-result-1",
            session_id="runtime-idempotent",
            transition=transition,
        ),
    )
    duplicate = _observe(
        repository,
        _request(
            request_id="runtime-idempotent-result-2",
            session_id="runtime-idempotent",
            transition=transition,
        ),
    )
    assert first_failure.performance is not None
    assert first_failure.performance.wrong_click_delta == 1
    assert duplicate.performance is not None
    assert duplicate.performance.wrong_click_delta == 0
    assert _session_counts(repository, "runtime-idempotent") == (1, 1)
    assert _instruction_outcome_count(repository, "runtime-idempotent") == 1

    unexpected = _execute_transition(
        repository,
        session_id="runtime-unexpected",
        reported_outcome="unexpected",
        moved=True,
    )
    assert unexpected.performance is not None
    assert unexpected.performance.executed_transition_outcome == "unexpected"
    assert _session_counts(repository, "runtime-unexpected") == (1, 1)


def assert_success_and_cancel_are_not_wrong_guidance(
    repository: UniversalNavigationGraphRepository,
) -> None:
    navigated = _execute_transition(
        repository,
        session_id="runtime-navigated",
        reported_outcome="navigated",
        moved=True,
    )
    assert navigated.performance is not None
    assert navigated.performance.executed_transition_outcome == "navigated"
    assert navigated.performance.wrong_guidance_delta == 0
    assert _session_counts(repository, "runtime-navigated") == (0, 0)

    cancelled = _execute_transition(
        repository,
        session_id="runtime-cancelled",
        reported_outcome="cancelled",
        moved=False,
    )
    assert cancelled.performance is not None
    assert cancelled.performance.executed_transition_outcome == "cancelled"
    assert cancelled.performance.wrong_guidance_delta == 0
    assert _session_counts(repository, "runtime-cancelled") == (0, 0)


def assert_unmatched_or_unexecuted_instructions_are_not_counted(
    repository: UniversalNavigationGraphRepository,
) -> None:
    owner = _first_instruction(repository, "runtime-owner")
    forged = _observe(
        repository,
        _request(
            request_id="runtime-forged-result",
            session_id="runtime-forged",
            transition=_transition(owner, outcome="failed"),
        ),
    )
    assert forged.graph_update.transition_recorded is True
    assert forged.performance is not None
    assert forged.performance.executed_transition_outcome is None
    assert forged.performance.wrong_click_delta == 0
    assert _session_counts(repository, "runtime-forged") == (0, 0)
    assert _instruction_outcome_count(repository, "runtime-forged") == 0


def assert_detailed_stop_reason_is_persisted(
    repository: UniversalNavigationGraphRepository,
) -> None:
    stopped = _observe(
        repository,
        _request(
            request_id="runtime-stop",
            session_id="runtime-stop",
            goal_text="show me an unspecified thing",
            elements=[_element("home", "Home")],
            operation_mode="explore",
        ),
    )
    assert stopped.phase == "stopped"
    assert stopped.failure_reason == "insufficient_screen_evidence"
    assert stopped.performance is not None
    assert stopped.performance.failure_reason == "insufficient_screen_evidence"
    session = repository.performance.session("runtime-stop")
    assert session is not None
    assert session["status"] == "failed"
    assert session["failure_type"] == "insufficient_screen_evidence"
    assert int(session["wrong_guidance_count"]) == 0
    assert int(session["wrong_click_count"]) == 0


def assert_runtime_summary_uses_executed_instruction_denominator(
    repository: UniversalNavigationGraphRepository,
) -> None:
    # Finish representative sessions without adding execution evidence so the
    # public summary includes them.  Runtime correctness remains untrusted; only
    # the observed instruction outcomes contribute to these dedicated metrics.
    for session_id in (
        "runtime-no-change",
        "runtime-idempotent",
        "runtime-unexpected",
        "runtime-navigated",
        "runtime-cancelled",
        "runtime-forged",
    ):
        repository.performance.record_stage(
            session_id=session_id,
            app_package="com.exitguide.runtime",
            app_version="1.0",
            locale="ko-KR",
            goal_key="a" * 16,
            target_function="settings.notifications.entry",
            start_screen_fingerprint="us_1111111111111111",
            current_screen_fingerprint="us_1111111111111111",
            destination_screen_fingerprint="",
            decision_mode="function_graph_exploration",
            phase="stopped",
            action="stop",
            safe_to_execute=False,
            selected_risk_level="low",
            selected_element_key="",
            route_id="",
            failure_type="test_session_closed",
            measurement=_measurement(),
        )
    summary = repository.performance.summary(measurement_source="real_device")
    assert summary["runtime_executed_instruction_count"] == 5
    assert summary["runtime_wrong_guidance_count"] == 3
    assert summary["runtime_wrong_click_count"] == 3
    assert summary["runtime_wrong_guidance_rate"] == 0.6
    assert summary["runtime_wrong_click_rate"] == 0.6
    assert summary["runtime_transition_outcome_counts"] == {
        "cancelled": 1,
        "failed": 1,
        "navigated": 1,
        "no_change": 1,
        "unexpected": 1,
    }
    assert summary["failure_reason_counts"]["insufficient_screen_evidence"] == 1


def _execute_transition(
    repository: UniversalNavigationGraphRepository,
    *,
    session_id: str,
    reported_outcome: str,
    moved: bool,
):
    first = _first_instruction(repository, session_id)
    elements = [_element("settings", "Settings"), _element("profile", "Profile")]
    if moved:
        elements.append(_element("notifications", "Notification settings"))
    return _observe(
        repository,
        _request(
            request_id=f"{session_id}-result",
            session_id=session_id,
            elements=elements,
            transition=_transition(first, outcome=reported_outcome),
        ),
    )


def _first_instruction(
    repository: UniversalNavigationGraphRepository,
    session_id: str,
):
    response = _observe(
        repository,
        _request(request_id=f"{session_id}-start", session_id=session_id),
    )
    assert response.recommendation is not None
    assert response.recommendation.selected_element_id is not None
    return response


def _transition(response, *, outcome: str) -> dict[str, object]:
    assert response.recommendation is not None
    assert response.recommendation.selected_element_id is not None
    return {
        "from_screen_fingerprint": response.screen_fingerprint,
        "performed_element_id": response.recommendation.selected_element_id,
        "recommendation_id": response.recommendation.recommendation_id,
        "outcome": outcome,
    }


def _observe(
    repository: UniversalNavigationGraphRepository,
    request: UniversalNavigationObserveRequest,
):
    return observe_universal_navigation(
        request,
        settings=SETTINGS,
        repository=repository,
    )


def _request(
    *,
    request_id: str,
    session_id: str,
    goal_text: str = "notification settings",
    elements: list[dict[str, object]] | None = None,
    transition: dict[str, object] | None = None,
    operation_mode: str = "guide",
) -> UniversalNavigationObserveRequest:
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": request_id,
            "session_id": session_id,
            "app_package": "com.exitguide.runtime",
            "app_version": "1.0",
            "locale": "ko-KR",
            "goal_text": goal_text,
            "operation_mode": operation_mode,
            "screen": {
                "activity_name": "com.exitguide.runtime.MainActivity",
                "window_title": "Settings",
                "elements": elements
                or [_element("settings", "Settings"), _element("profile", "Profile")],
            },
            "transition": transition,
            "client_timing": {
                "measurement_source": "real_device",
                "exploration_elapsed_ms": 1000.0,
                "action_execution_ms": 20.0,
                "ui_settle_ms": 200.0,
            },
        }
    )


def _element(element_id: str, text: str) -> dict[str, object]:
    return {
        "id": element_id,
        "text": text,
        "role": "button",
        "clickable": True,
        "enabled": True,
        "visible": True,
    }


def _session_counts(
    repository: UniversalNavigationGraphRepository,
    session_id: str,
) -> tuple[int, int]:
    session = repository.performance.session(session_id)
    assert session is not None
    return int(session["wrong_guidance_count"]), int(session["wrong_click_count"])


def _instruction_outcome_count(
    repository: UniversalNavigationGraphRepository,
    session_id: str,
) -> int:
    with sqlite3.connect(repository.database_path) as connection:
        return int(
            connection.execute(
                "SELECT COUNT(*) FROM navigation_instruction_outcomes WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
        )


def _measurement():
    from app.services.navigation_performance import StageMeasurement

    return StageMeasurement(measurement_source="real_device", server_total_ms=1.0)


if __name__ == "__main__":
    main()
