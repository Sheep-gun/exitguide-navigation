import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database = root / "navigation.sqlite"
        repository = UniversalNavigationGraphRepository(database)
        first = observe(repository, request("gold-1", "gold-session", [element("settings", "설정")]))
        assert first.status == "recording"
        assert first.phase == "recording"
        assert first.decision_mode == "human_recording"
        assert first.automation.action == "none"
        assert first.automation.safe_to_execute is False
        assert first.recommendation is None

        second = observe(
            repository,
            request(
                "gold-2",
                "gold-session",
                [element("notifications", "알림")],
                transition={
                    "from_screen_fingerprint": first.screen_fingerprint,
                    "performed_element_id": "settings",
                    "action_kind": "click",
                    "outcome": "navigated",
                },
            ),
        )
        assert second.status == "recording"
        third = observe(
            repository,
            request(
                "gold-3",
                "gold-session",
                [element("marketing-toggle", "마케팅 알림")],
                transition={
                    "from_screen_fingerprint": second.screen_fingerprint,
                    "performed_element_id": "notifications",
                    "action_kind": "scroll_forward",
                    "outcome": "navigated",
                },
            ),
        )
        assert third.status == "recording"
        completed = repository.complete_gold_recording(
            "gold-session",
            destination_correct=True,
            safe_stop=True,
            reviewer="tester",
            notes="destination checked",
        )
        assert completed["status"] == "review_pending"
        assert completed["step_count"] == 3
        assert completed["selected_step_count"] == 2

        reviewed = repository.review_gold_recording(
            "gold-session",
            decision="human_gold",
            reviewer="reviewer",
            notes="approved",
        )
        assert reviewed["status"] == "human_gold"

        row_start = observe(
            repository,
            request(
                "row-1",
                "row-session",
                [
                    {
                        "id": "settings-list",
                        "parent_id": "root",
                        "text": None,
                        "content_description": None,
                        "view_id": "com.example.gold:id/settings-list",
                        "role": "list",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "scrollable": True,
                        "bounds": [0, 80, 1080, 2200],
                    },
                    element("notifications", "알림"),
                ],
            ),
        )
        observe(
            repository,
            request(
                "row-2",
                "row-session",
                [
                    {
                        **element("back", "위로 이동"),
                        "content_description": "위로 이동",
                    },
                    {
                        **element("notification-title", "알림"),
                        "role": "text",
                        "clickable": False,
                    },
                ],
                transition={
                    "from_screen_fingerprint": row_start.screen_fingerprint,
                    "performed_element_id": "settings-list",
                    "action_kind": "scroll_forward",
                    "outcome": "navigated",
                },
            ),
        )
        connection = sqlite3.connect(database)
        try:
            inferred = connection.execute(
                """
                SELECT selected_element_id, selected_label, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = 'row-session' AND ordinal = 0
                """
            ).fetchone()
        finally:
            connection.close()
        assert inferred == ("notifications", "알림", "click")
        repository.cancel_gold_recording("row-session")

        compose_start = observe(
            repository,
            request(
                "compose-1",
                "compose-session",
                [
                    element("profile-settings", "Profile settings"),
                    element("account", "Account"),
                ],
            ),
        )
        observe(
            repository,
            request(
                "compose-2",
                "compose-session",
                [
                    {
                        **element("profile-title", "Profile"),
                        "role": "text",
                        "clickable": False,
                    }
                ],
                transition={
                    "from_screen_fingerprint": compose_start.screen_fingerprint,
                    "performed_element_id": "__screen_change__",
                    "action_kind": "click",
                    "outcome": "navigated",
                },
            ),
        )
        connection = sqlite3.connect(database)
        try:
            compose_inferred = connection.execute(
                """
                SELECT selected_element_id, selected_label, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = 'compose-session' AND ordinal = 0
                """
            ).fetchone()
        finally:
            connection.close()
        assert compose_inferred == ("profile-settings", "Profile settings", "click")
        repository.cancel_gold_recording("compose-session")

        account_start = observe(
            repository,
            request(
                "account-1",
                "account-session",
                [element("account", "Account"), element("help", "Help Center")],
            ),
        )
        observe(
            repository,
            request(
                "account-2",
                "account-session",
                [
                    {**element("external", "External link"), "role": "text", "clickable": False},
                    {**element("brand", "Netflix"), "role": "text", "clickable": False},
                    {**element("account-title", "Account"), "role": "text", "clickable": False},
                ],
                transition={
                    "from_screen_fingerprint": account_start.screen_fingerprint,
                    "performed_element_id": "__screen_change__",
                    "action_kind": "click",
                    "outcome": "navigated",
                },
            ),
        )
        connection = sqlite3.connect(database)
        try:
            account_inferred = connection.execute(
                """
                SELECT selected_element_id, selected_label, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = 'account-session' AND ordinal = 0
                """
            ).fetchone()
        finally:
            connection.close()
        assert account_inferred == ("account", "Account", "click")
        repository.cancel_gold_recording("account-session")

        output = root / "training.jsonl"
        script = Path(__file__).resolve().parents[3] / "scripts" / "Export-NavigationGoldTraining.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--database",
                str(database),
                "--output",
                str(output),
            ],
            check=True,
        )
        rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2
        assert rows[0]["provenance"] == "real_device_human_gold"
        assert rows[0]["correct_candidate"]["element_id"] == "settings"
        assert rows[0]["next_screen_fingerprint"] == second.screen_fingerprint
        assert rows[1]["action"] == "scroll_forward"
        assert rows[1]["next_screen_fingerprint"] == third.screen_fingerprint
    print("navigation Gold recording checks ok")


def observe(repository: UniversalNavigationGraphRepository, payload: UniversalNavigationObserveRequest):
    return observe_universal_navigation(
        payload,
        settings=Settings(navigation_agent_provider="mock"),
        repository=repository,
    )


def request(
    request_id: str,
    session_id: str,
    elements: list[dict[str, object]],
    *,
    transition: dict[str, object] | None = None,
) -> UniversalNavigationObserveRequest:
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": request_id,
            "session_id": session_id,
            "app_package": "com.example.gold",
            "app_version": "1.2.3",
            "locale": "ko-KR",
            "goal_text": "알림 수신을 끄고 싶어",
            "operation_mode": "record",
            "screen": {
                "activity_name": "com.example.gold.MainActivity",
                "window_title": "테스트",
                "event_type": "window_state_changed",
                "captured_at": "2026-08-01T00:00:00Z",
                "elements": elements,
            },
            "transition": transition,
        }
    )


def element(element_id: str, label: str) -> dict[str, object]:
    return {
        "id": element_id,
        "parent_id": "root",
        "text": label,
        "content_description": None,
        "view_id": f"com.example.gold:id/{element_id}",
        "role": "button",
        "clickable": True,
        "enabled": True,
        "visible": True,
        "bounds": [20, 100, 1000, 180],
    }


if __name__ == "__main__":
    main()
