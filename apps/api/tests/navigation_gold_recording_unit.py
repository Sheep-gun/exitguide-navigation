import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationElement, UniversalNavigationObserveRequest
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import (
    UniversalNavigationGraphRepository,
    _infer_gold_row_click,
)


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

        semantic_start = observe(
            repository,
            request(
                "semantic-1",
                "semantic-session",
                [
                    label_element("home-title", "홈", role="heading"),
                    element("my-baemin", "마이배민"),
                    element("orders", "주문내역"),
                ],
            ),
        )
        loading = observe(
            repository,
            request(
                "semantic-2",
                "semantic-session",
                [label_element("loading", "불러오는 중")],
                transition={
                    "from_screen_fingerprint": semantic_start.screen_fingerprint,
                    "performed_element_id": "__semantic_screen_change__",
                    "action_kind": "click",
                    "outcome": "navigated",
                },
            ),
        )
        assert loading.graph_update.transition_recorded is False
        settled = observe(
            repository,
            request(
                "semantic-3",
                "semantic-session",
                [
                    label_element("my-title", "마이배민", role="heading"),
                    element("settings", "환경설정"),
                    element("support", "고객센터"),
                ],
                transition={
                    "from_screen_fingerprint": semantic_start.screen_fingerprint,
                    "performed_element_id": "__semantic_screen_change__",
                    "action_kind": "click",
                    "outcome": "navigated",
                },
            ),
        )
        assert settled.graph_update.transition_recorded is True
        connection = sqlite3.connect(database)
        try:
            semantic_inferred = connection.execute(
                """
                SELECT selected_element_id, selected_label, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = 'semantic-session' AND ordinal = 0
                """
            ).fetchone()
        finally:
            connection.close()
        assert semantic_inferred == ("my-baemin", "마이배민", "click")
        repository.cancel_gold_recording("semantic-session")

        passive_start = observe(
            repository,
            request(
                "passive-1",
                "passive-session",
                [
                    label_element("profile-title", "마이배민", role="heading"),
                    element("settings", "환경설정"),
                    element("support", "고객센터"),
                ],
            ),
        )
        passive_destination = observe(
            repository,
            request(
                "passive-2",
                "passive-session",
                [
                    label_element("settings-title", "환경설정", role="heading"),
                    element("delivery-alert", "배달현황 알림"),
                    element("review-alert", "리뷰 작성 알림"),
                ],
            ),
        )
        assert passive_start.screen_fingerprint != passive_destination.screen_fingerprint
        assert passive_destination.graph_update.transition_recorded is True
        connection = sqlite3.connect(database)
        try:
            passive_inferred = connection.execute(
                """
                SELECT selected_element_id, selected_label, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = 'passive-session' AND ordinal = 0
                """
            ).fetchone()
        finally:
            connection.close()
        assert passive_inferred == ("settings", "환경설정", "click")
        repository.cancel_gold_recording("passive-session")

        idle_start = observe(
            repository,
            request(
                "idle-1",
                "idle-session",
                [
                    label_element("home-title", "홈", role="heading"),
                    label_element("countdown", "10분 남음"),
                    element("settings", "환경설정"),
                    element("orders", "주문내역"),
                ],
            ),
        )
        idle_refresh = observe(
            repository,
            request(
                "idle-2",
                "idle-session",
                [
                    label_element("home-title", "홈", role="heading"),
                    label_element("countdown", "9분 남음"),
                    element("settings", "환경설정"),
                    element("orders", "주문내역"),
                ],
            ),
        )
        assert idle_start.screen_fingerprint != idle_refresh.screen_fingerprint
        assert idle_refresh.graph_update.transition_recorded is False
        connection = sqlite3.connect(database)
        try:
            idle_selected = connection.execute(
                """
                SELECT selected_action FROM navigation_gold_steps
                WHERE recording_id = 'idle-session' AND ordinal = 0
                """
            ).fetchone()
        finally:
            connection.close()
        assert idle_selected == (None,)
        repository.cancel_gold_recording("idle-session")

        deep_destination = [
            UniversalNavigationElement.model_validate(label_element(f"noise-{index}", f"Noise {index}"))
            for index in range(30)
        ]
        deep_destination.append(
            UniversalNavigationElement.model_validate(
                label_element("my-baemin-title", "My Baemin", role="heading")
            )
        )
        deep_match = _infer_gold_row_click(
            [
                {
                    "element_id": "my-baemin",
                    "element_key": "my-baemin-key",
                    "label": "Bottom navigation My Baemin tab",
                    "role": "button",
                    "risk_level": "low",
                },
                {
                    "element_id": "orders",
                    "element_key": "orders-key",
                    "label": "Orders",
                    "role": "button",
                    "risk_level": "low",
                },
            ],
            deep_destination,
        )
        assert deep_match is not None
        assert deep_match["element_id"] == "my-baemin"

        baemin_start = observe(
            repository,
            request(
                "baemin-1",
                "baemin-tab-session",
                [
                    label_element("home-heading", "홈", role="heading"),
                    element("promotion", "지금 신규가입하면 12,000원 할인!"),
                    element("home-tab", "하단탭바 홈탭"),
                    element("orders-tab", "하단탭바 주문내역탭"),
                    element("my-baemin-tab", "하단탭바 마이배민탭"),
                ],
            ),
        )
        baemin_refresh = observe(
            repository,
            request(
                "baemin-2",
                "baemin-tab-session",
                [
                    label_element("home-heading", "홈", role="heading"),
                    element("promotion", "주말 특가 쿠폰 2천원 할인!"),
                    element("home-tab", "하단탭바 홈탭"),
                    element("orders-tab", "하단탭바 주문내역탭"),
                    element("my-baemin-tab", "하단탭바 마이배민탭"),
                ],
                transition={
                    "from_screen_fingerprint": baemin_start.screen_fingerprint,
                    "performed_element_id": "promotion",
                    "action_kind": "scroll_forward",
                    "outcome": "navigated",
                },
            ),
        )
        assert baemin_refresh.graph_update.transition_recorded is False
        assert baemin_refresh.graph_update.transition_discarded is True
        settled_baemin = observe(
            repository,
            request(
                "baemin-3",
                "baemin-tab-session",
                [
                    label_element("my-heading", "마이배민", role="heading"),
                    element("signup", "가입하고 혜택받기"),
                    element("settings", "환경설정"),
                    element("home-tab", "하단탭바 홈탭"),
                    element("orders-tab", "하단탭바 주문내역탭"),
                    element("my-baemin-tab", "하단탭바 마이배민탭"),
                ],
                transition={
                    "from_screen_fingerprint": baemin_refresh.screen_fingerprint,
                    "performed_element_id": "__semantic_screen_change__",
                    "action_kind": "click",
                    "outcome": "navigated",
                },
            ),
        )
        assert settled_baemin.graph_update.transition_recorded is True
        assert settled_baemin.graph_update.transition_discarded is False
        connection = sqlite3.connect(database)
        try:
            baemin_inferred = connection.execute(
                """
                SELECT selected_element_id, selected_label, selected_action
                FROM navigation_gold_steps
                WHERE recording_id = 'baemin-tab-session' AND ordinal = 0
                """
            ).fetchone()
            baemin_step_count = connection.execute(
                """
                SELECT COUNT(*) FROM navigation_gold_steps
                WHERE recording_id = 'baemin-tab-session'
                """
            ).fetchone()[0]
        finally:
            connection.close()
        assert baemin_inferred == ("my-baemin-tab", "하단탭바 마이배민탭", "click")
        assert baemin_step_count == 2
        repository.cancel_gold_recording("baemin-tab-session")

        signup_destination = [
            UniversalNavigationElement.model_validate(
                label_element("signup-title", "Register a new account", role="heading")
            ),
            UniversalNavigationElement.model_validate(element("google", "Continue with Google")),
        ]
        signup_match = _infer_gold_row_click(
            [
                {
                    "element_id": "signup-benefit",
                    "element_key": "signup-benefit-key",
                    "label": "Sign up and get benefits",
                    "role": "button",
                    "risk_level": "low",
                },
                {
                    "element_id": "help",
                    "element_key": "help-key",
                    "label": "Help Center",
                    "role": "button",
                    "risk_level": "low",
                },
                {
                    "element_id": "ocr_signup_title",
                    "element_key": "ocr-signup-title-key",
                    "label": "Register a new account",
                    "role": "button",
                    "risk_level": "low",
                },
            ],
            signup_destination,
            target_function="auth.signup.entry",
        )
        assert signup_match is not None
        assert signup_match["element_id"] == "signup-benefit"

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
        assert rows[1]["action"] == "click"
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


def label_element(element_id: str, label: str, *, role: str = "text") -> dict[str, object]:
    return {
        **element(element_id, label),
        "role": role,
        "clickable": False,
    }


if __name__ == "__main__":
    main()
