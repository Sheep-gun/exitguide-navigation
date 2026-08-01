import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from app.schemas import UniversalNavigationObserveRequest
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


def main() -> None:
    assert_session_keeps_its_origin_app_when_a_later_screen_is_external()
    print("universal navigation session origin checks ok")


def assert_session_keeps_its_origin_app_when_a_later_screen_is_external() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        repository = UniversalNavigationGraphRepository(
            Path(temporary_directory) / "graph.sqlite"
        )
        common = {
            "session_id": "cross-app-session",
            "app_version": "1.0",
            "locale": "ko-KR",
            "goal_text": "Cancel YouTube Premium subscription",
            "goal_interpretation": "subscription cancellation",
            "target_function": "subscription.cancel.entry",
            "decision_mode": "deterministic_fallback",
            "action_id": None,
            "confidence": 0.8,
        }
        youtube_screen = _observe_empty_screen(
            repository,
            app_package="com.google.android.youtube",
            activity_name="YouTubeMainActivity",
        )
        browser_screen = _observe_empty_screen(
            repository,
            app_package="com.sec.android.app.sbrowser",
            activity_name="CustomTabActivity",
        )
        repository.record_recommendation(
            recommendation_id="youtube-step",
            app_package="com.google.android.youtube",
            screen_fingerprint=youtube_screen,
            **common,
        )
        repository.record_recommendation(
            recommendation_id="browser-step",
            app_package="com.sec.android.app.sbrowser",
            screen_fingerprint=browser_screen,
            **common,
        )

        with sqlite3.connect(repository.database_path) as connection:
            row = connection.execute(
                """
                SELECT apps.app_package
                FROM universal_sessions sessions
                JOIN universal_apps apps ON apps.app_key = sessions.app_key
                WHERE sessions.session_id = ?
                """,
                ("cross-app-session",),
            ).fetchone()
        assert row is not None
        assert row[0] == "com.google.android.youtube"


def _observe_empty_screen(
    repository: UniversalNavigationGraphRepository,
    *,
    app_package: str,
    activity_name: str,
) -> str:
    request = UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": f"request-{app_package}",
            "session_id": "cross-app-session",
            "app_package": app_package,
            "app_version": "1.0",
            "locale": "ko-KR",
            "goal_text": "Cancel YouTube Premium subscription",
            "screen": {
                "activity_name": activity_name,
                "window_title": "",
                "elements": [
                    {
                        "id": f"heading-{app_package}",
                        "text": activity_name,
                        "role": "heading",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                    }
                ],
            },
        }
    )
    return repository.observe(request, []).screen_fingerprint


if __name__ == "__main__":
    main()
