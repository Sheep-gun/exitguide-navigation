from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


def _element(element_id: str, label: str, *, role: str = "button") -> dict:
    return {
        "id": element_id,
        "text": label,
        "view_id": f"com.example.global:id/{element_id}",
        "role": role,
        "clickable": True,
        "enabled": True,
        "visible": True,
        "bounds": [20, 100, 1000, 180],
    }


def _request(
    *,
    session_id: str,
    title: str,
    elements: list[dict],
    transition: dict | None = None,
    goal_text: str = "cancel subscription",
    app_package: str = "com.example.global",
) -> UniversalNavigationObserveRequest:
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": f"request-{session_id}-{title}",
            "session_id": session_id,
            "app_package": app_package,
            "app_version": "1.0.0",
            "locale": "en-US",
            "goal_text": goal_text,
            "operation_mode": "explore",
            "screen": {
                "activity_name": title,
                "window_title": title,
                "elements": [
                    {
                        "id": "heading",
                        "text": title,
                        "role": "heading",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                    },
                    *elements,
                ],
            },
            "transition": transition,
        }
    )


def _performed(response) -> dict:
    assert response.recommendation is not None
    assert response.automation.selected_element_id is not None
    return {
        "from_screen_fingerprint": response.screen_fingerprint,
        "performed_element_id": response.automation.selected_element_id,
        "recommendation_id": response.recommendation.recommendation_id,
        "outcome": "navigated",
    }


def _environment(directory: str):
    root = Path(directory)
    repository = UniversalNavigationGraphRepository(root / "graph.sqlite")
    settings = Settings(
        navigation_agent_provider="mock",
        android_control_index_path="",
        navigation_function_db_path=str(root / "functions.sqlite"),
        navigation_exploration_timeout_seconds=55,
        navigation_exploration_max_actions=8,
        navigation_exploration_max_depth=9,
    )
    return repository, settings


def assert_global_frontier_beats_local_branch_and_stops_loops() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = _environment(temporary_directory)
        root_elements = [
            _element("my", "My page"),
            _element("settings", "Settings"),
            _element("delete", "Delete account"),
        ]
        root_request = lambda transition=None: _request(
            session_id="global-frontier",
            title="Home",
            elements=root_elements,
            transition=transition,
        )
        first = observe_universal_navigation(
            root_request(), settings=settings, repository=repository
        )
        assert first.automation.action == "click"
        assert first.automation.safe_to_execute is True
        first_label = first.automation.selected_label
        assert first_label in {"My page", "Settings"}

        with sqlite3.connect(repository.database_path) as connection:
            connection.row_factory = sqlite3.Row
            root_frontier = connection.execute(
                """
                SELECT label, status FROM universal_exploration_frontier
                WHERE exploration_id = ? ORDER BY label
                """,
                ("global-frontier",),
            ).fetchall()
            assert {row["label"] for row in root_frontier} == {"My page", "Settings"}
            assert "Delete account" not in {row["label"] for row in root_frontier}
            queued_label = next(
                str(row["label"]) for row in root_frontier if row["status"] == "queued"
            )
            connection.execute(
                """
                UPDATE universal_exploration_frontier
                SET goal_alignment = 0.99, novelty = 1.0,
                    risk_penalty = 0.0, expected_cost = 1.0
                WHERE exploration_id = ? AND status = 'queued'
                """,
                ("global-frontier",),
            )
        connection.close()

        child = observe_universal_navigation(
            _request(
                session_id="global-frontier",
                title="Account",
                elements=[
                    _element("payments", "Payments and subscriptions"),
                    _element("history", "Purchase history"),
                ],
                transition=_performed(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert child.automation.action == "back"
        assert child.automation.safe_to_execute is True
        assert child.recommendation is None
        state = repository.exploration("global-frontier")
        assert state is not None and state.back_count == 1

        alternative = observe_universal_navigation(
            root_request(), settings=settings, repository=repository
        )
        assert alternative.automation.action == "click"
        assert alternative.automation.selected_label == queued_label
        assert alternative.automation.selected_label != first_label
        assert alternative.automation.safe_to_execute is True

        # A same-screen transition is normalized to no_change. Both root
        # actions have now been attempted, so the explorer stops instead of
        # cycling through the same branch again.
        stopped = observe_universal_navigation(
            root_request(transition=_performed(alternative)),
            settings=settings,
            repository=repository,
        )
        assert stopped.phase == "stopped"
        assert stopped.automation.action == "stop"
        assert stopped.automation.safe_to_execute is False

        with sqlite3.connect(repository.database_path) as connection:
            click_rows = connection.execute(
                """
                SELECT label, action_id FROM universal_exploration_attempts
                WHERE exploration_id = ? AND command = 'click'
                """,
                ("global-frontier",),
            ).fetchall()
            assert len(click_rows) == 2
            assert len({row[1] for row in click_rows}) == 2
            assert all(row[0] != "Delete account" for row in click_rows)
            assert connection.execute(
                "SELECT COUNT(*) FROM universal_routes WHERE status = 'approved'"
            ).fetchone()[0] == 0
        connection.close()


def assert_content_feed_never_enters_global_frontier() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = _environment(temporary_directory)
        feed = [
            {
                "id": "timeline",
                "role": "list",
                "clickable": False,
                "scrollable": True,
                "enabled": True,
                "visible": True,
                "bounds": [0, 200, 1080, 2210],
            },
            _element("reply", "Reply"),
            _element("repost", "Repost"),
            _element("like", "Like"),
            _element("share", "Share"),
        ]
        first = observe_universal_navigation(
            _request(
                session_id="feed-frontier",
                title="For you timeline",
                elements=feed,
                goal_text="delete X account",
                app_package="com.twitter.android",
            ),
            settings=settings,
            repository=repository,
        )
        assert first.automation.action == "scroll_forward"
        second = observe_universal_navigation(
            _request(
                session_id="feed-frontier",
                title="Following timeline",
                elements=feed,
                goal_text="delete X account",
                app_package="com.twitter.android",
            ),
            settings=settings,
            repository=repository,
        )
        assert second.phase == "stopped"
        assert second.automation.action == "stop"
        with sqlite3.connect(repository.database_path) as connection:
            assert connection.execute(
                """
                SELECT COUNT(*) FROM universal_exploration_frontier
                WHERE exploration_id = ?
                """,
                ("feed-frontier",),
            ).fetchone()[0] == 0
            assert connection.execute(
                """
                SELECT COUNT(*) FROM universal_exploration_attempts
                WHERE exploration_id = ? AND command = 'click'
                """,
                ("feed-frontier",),
            ).fetchone()[0] == 0
        connection.close()


def main() -> None:
    assert_global_frontier_beats_local_branch_and_stops_loops()
    assert_content_feed_never_enters_global_frontier()
    print("universal navigation global frontier checks ok")


if __name__ == "__main__":
    main()
