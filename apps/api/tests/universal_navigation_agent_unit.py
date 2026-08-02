import json
import sqlite3
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services import universal_navigation_agent as agent_module
from app.services.android_control_index import AndroidControlIndex, read_normalized_jsonl
from app.services.universal_navigation_agent import extract_navigation_candidates, observe_universal_navigation
from app.services.universal_navigation_graph import (
    UniversalNavigationGraphRepository,
    fingerprint_screen,
    sanitize_text,
)


def main() -> None:
    assert_unicode_format_controls_are_removed()
    assert_non_actionable_chrome_is_not_a_navigation_candidate()
    assert_unknown_app_is_guided_without_prebuilt_route()
    assert_subscription_feed_is_not_confused_with_billing()
    assert_native_label_beats_corrupted_ocr_of_same_control()
    assert_short_native_label_beats_corrupted_hangul_ocr()
    assert_visible_ocr_label_overrides_stale_accessibility_description()
    assert_profile_action_description_beats_visible_account_name()
    assert_empty_native_label_uses_owned_ocr()
    assert_clickable_parent_inherits_settings_content_description()
    assert_accessible_tab_label_beats_merged_navigation_ocr()
    assert_orphan_ocr_coordinate_is_a_navigation_candidate()
    assert_static_native_heading_suppresses_duplicate_coordinate_ocr()
    assert_static_native_button_semantics_preserve_coordinate_ocr()
    assert_multiple_unlabeled_icons_in_one_region_remain_distinct_candidates()
    assert_read_only_purchase_hub_is_low_risk()
    assert_read_only_insurance_refund_labels_are_low_risk()
    assert_successful_trace_becomes_reusable_graph_memory()
    assert_risky_action_requires_user_confirmation()
    assert_sensitive_labels_are_redacted_before_storage()
    assert_exaone_uses_hermes_tool_contract()
    assert_exaone_planner_uses_strict_bounded_hermes_actions()
    assert_exaone_planner_repairs_one_malformed_hermes_call()
    assert_planner_accepts_exact_hermes_content_wrapper_only()
    assert_exaone_must_confirm_terminal_destination()
    assert_exaone_total_deadline_stops_trickle_style_active_call()
    assert_hermes_actual_tool_call_has_priority_and_known_wrappers_are_accepted()
    assert_hermes_rejects_ambiguous_or_malformed_calls_and_strict_types()
    assert_failed_exaone_attempt_records_model_decision_time()
    assert_exploration_fails_closed_when_exaone_planner_is_unavailable()
    assert_invalid_model_action_falls_back_safely()
    assert_semantically_weaker_model_choice_is_guarded()
    assert_low_confidence_matching_model_choice_uses_independent_score()
    assert_initially_completed_goal_closes_session()
    assert_screen_state_changes_have_distinct_fingerprints()
    assert_ocr_geometry_does_not_fragment_screen_identity()
    assert_transition_cannot_reuse_another_session_recommendation()
    print("universal navigation agent checks ok")


def assert_unicode_format_controls_are_removed() -> None:
    assert sanitize_text("로\ufeff그\u200b인") == "로그인"


def assert_non_actionable_chrome_is_not_a_navigation_candidate() -> None:
    candidates = extract_navigation_candidates(
        request(
            request_id="req_candidate_noise",
            session_id="session_candidate_noise",
            elements=[
                element("page", "4페이지"),
                element("back-symbol", "<"),
                element("top-anchor", "TOP"),
                element("mount", "appMountPoint"),
                element("settings", "설정"),
            ],
        )
    )
    assert [candidate.element_id for candidate in candidates] == ["settings"]


def assert_visible_ocr_label_overrides_stale_accessibility_description() -> None:
    button = element("club-card", "")
    button["content_description"] = "지금 사용할 수 있는 브랜드 쿠폰팩을 확인해보세요"
    button["bounds"] = [42, 742, 1038, 1013]
    ocr = element("ocr-club", "배민클럽 이용 중", clickable=False, role="text")
    ocr["parent_id"] = "club-card"
    ocr["view_id"] = "exitguide:ocr"
    ocr["bounds"] = [84, 760, 360, 820]
    candidates = extract_navigation_candidates(
        request(
            request_id="req_ocr_visible_label",
            session_id="session_ocr_visible_label",
            elements=[button, ocr],
        )
    )
    assert candidates[0].element_id == "club-card"
    assert candidates[0].label == "배민클럽 이용 중"


def assert_profile_action_description_beats_visible_account_name() -> None:
    button = element("profile-gateway", "")
    button["content_description"] = (
        "프\ufeff로\ufeff필\ufeff을 변\ufeff경 또\ufeff는 관\ufeff리\ufeff하\ufeff세\ufeff요."
    )
    button["bounds"] = [0, 127, 820, 309]
    ocr = element("ocr-profile-name", "carson0306 -", clickable=False, role="text")
    ocr["parent_id"] = "profile-gateway"
    ocr["view_id"] = "exitguide:ocr"
    ocr["bounds"] = [40, 150, 600, 280]

    candidates = extract_navigation_candidates(
        request(
            request_id="req_profile_action_over_name",
            session_id="session_profile_action_over_name",
            elements=[button, ocr],
        )
    )

    assert candidates[0].element_id == "profile-gateway"
    assert candidates[0].label == "프로필을 변경 또는 관리하세요."


def assert_native_label_beats_corrupted_ocr_of_same_control() -> None:
    button = element("manage-google-play", "Google Play에서 관리")
    button["bounds"] = [42, 742, 1038, 1013]
    ocr = element(
        "ocr-manage-google-play",
        "Google P이ay에서 관리 기",
        clickable=False,
        role="text",
    )
    ocr["parent_id"] = "manage-google-play"
    ocr["view_id"] = "exitguide:ocr"
    ocr["bounds"] = [84, 760, 520, 820]

    candidates = extract_navigation_candidates(
        request(
            request_id="req_native_over_corrupted_ocr",
            session_id="session_native_over_corrupted_ocr",
            elements=[button, ocr],
        )
    )

    assert candidates[0].element_id == "manage-google-play"
    assert candidates[0].label == "Google Play에서 관리"


def assert_short_native_label_beats_corrupted_hangul_ocr() -> None:
    button = element("gift", "선물하기")
    button["bounds"] = [42, 742, 1038, 1013]
    ocr = element("ocr-gift", "서무하기", clickable=False, role="text")
    ocr["parent_id"] = "gift"
    ocr["view_id"] = "exitguide:ocr"
    ocr["bounds"] = [84, 760, 360, 820]

    candidates = extract_navigation_candidates(
        request(
            request_id="req_native_short_hangul_ocr",
            session_id="session_native_short_hangul_ocr",
            elements=[button, ocr],
        )
    )

    assert candidates[0].element_id == "gift"
    assert candidates[0].label == "선물하기"


def assert_empty_native_label_uses_owned_ocr() -> None:
    button = element("custom-manage", "")
    button["view_id"] = None
    button["bounds"] = [42, 742, 1038, 1013]
    ocr = element("ocr-custom-manage", "멤버십 관리", clickable=False, role="text")
    ocr["parent_id"] = "custom-manage"
    ocr["view_id"] = "exitguide:ocr"
    ocr["bounds"] = [84, 760, 360, 820]

    candidates = extract_navigation_candidates(
        request(
            request_id="req_empty_native_uses_ocr",
            session_id="session_empty_native_uses_ocr",
            elements=[button, ocr],
        )
    )

    assert candidates[0].element_id == "custom-manage"
    assert candidates[0].label == "멤버십 관리"


def assert_multiple_unlabeled_icons_in_one_region_remain_distinct_candidates() -> None:
    icons = []
    for element_id, bounds in (
        ("unknown-search", [780, 80, 860, 160]),
        ("unknown-bell", [880, 80, 960, 160]),
        ("unknown-gear", [980, 80, 1060, 160]),
    ):
        payload = element(element_id, "", role="image")
        payload.update(
            {
                "parent_id": "top-bar",
                "content_description": None,
                "view_id": None,
                "bounds": bounds,
            }
        )
        icons.append(payload)

    candidates = extract_navigation_candidates(
        request(
            request_id="req_multiple_unlabeled_top_icons",
            session_id="session_multiple_unlabeled_top_icons",
            goal_text="알림 설정을 열고 싶어",
            elements=[
                {
                    "id": "screen-root",
                    "role": "container",
                    "clickable": False,
                    "enabled": True,
                    "visible": True,
                    "bounds": [0, 0, 1080, 2400],
                },
                *icons,
            ],
        )
    )

    assert [candidate.element_id for candidate in candidates] == [
        "unknown-search",
        "unknown-bell",
        "unknown-gear",
    ]
    assert len({candidate.element_key for candidate in candidates}) == 3
    assert all(candidate.label == "이름 없는 상단 오른쪽 아이콘" for candidate in candidates)


def assert_clickable_parent_inherits_settings_content_description() -> None:
    parent = element("settings-touch-target", "", role="button")
    parent.update(
        {
            "parent_id": "top-bar",
            "content_description": None,
            "view_id": None,
            "bounds": [940, 80, 1060, 200],
        }
    )
    gear = element("settings-gear-image", "", clickable=False, role="image")
    gear.update(
        {
            "parent_id": "settings-touch-target",
            "content_description": "환경설정",
            "view_id": None,
            "bounds": [960, 100, 1040, 180],
        }
    )

    candidates = extract_navigation_candidates(
        request(
            request_id="req_settings_descendant",
            session_id="session_settings_descendant",
            goal_text="알림 설정을 열고 싶어",
            elements=[parent, gear],
        )
    )

    assert len(candidates) == 1
    assert candidates[0].element_id == "settings-touch-target"
    assert candidates[0].label == "환경설정"


def assert_accessible_tab_label_beats_merged_navigation_ocr() -> None:
    tab = element("my-page-tab", "")
    tab["bounds"] = [864, 2004, 1080, 2214]
    child = element("my-page-label", "마이페이지", clickable=False, role="text")
    child["parent_id"] = "my-page-tab"
    merged_ocr = element(
        "ocr-bottom-navigation",
        "홈 항공권예매 모바일탑승권 스케줄조회 마이페이지",
        clickable=False,
        role="text",
    )
    merged_ocr["parent_id"] = "my-page-tab"
    merged_ocr["view_id"] = "exitguide:ocr"
    merged_ocr["bounds"] = [216, 2122, 1080, 2170]
    candidates = extract_navigation_candidates(
        request(
            request_id="req_accessible_tab_over_ocr",
            session_id="session_accessible_tab_over_ocr",
            elements=[tab, child, merged_ocr],
        )
    )
    assert candidates[0].element_id == "my-page-tab"
    assert candidates[0].label == "마이페이지"

    icon_tab = element("center-icon-tab", "")
    icon_tab["view_id"] = "com.example:id/tab3"
    icon_tab["bounds"] = [432, 2004, 648, 2214]
    merged_ocr["parent_id"] = "center-icon-tab"
    icon_candidates = extract_navigation_candidates(
        request(
            request_id="req_icon_tab_over_ocr",
            session_id="session_icon_tab_over_ocr",
            elements=[icon_tab, merged_ocr],
        )
    )
    assert icon_candidates[0].element_id == "center-icon-tab"
    assert icon_candidates[0].label == "tab3"


def assert_orphan_ocr_coordinate_is_a_navigation_candidate() -> None:
    ocr = element("ocr-coordinate", "Membership management", clickable=True, role="button")
    ocr["view_id"] = "exitguide:ocr"
    ocr["bounds"] = [84, 760, 420, 820]
    candidates = extract_navigation_candidates(
        request(
            request_id="req_ocr_coordinate",
            session_id="session_ocr_coordinate",
            elements=[ocr],
        )
    )
    assert len(candidates) == 1
    assert candidates[0].element_id == "ocr-coordinate"
    assert candidates[0].label == "Membership management"


def assert_static_native_heading_suppresses_duplicate_coordinate_ocr() -> None:
    heading = element("membership-section", "멤버십 및 채널", clickable=False, role="heading")
    heading["bounds"] = [42, 520, 460, 610]
    duplicate_ocr = element("ocr-membership-section", "멤버십 및 채널", clickable=True, role="button")
    duplicate_ocr["view_id"] = "exitguide:ocr"
    duplicate_ocr["bounds"] = [40, 518, 465, 612]
    membership_card = element(
        "youtube-premium-card",
        "YouTube Premium 개인 멤버십 월 ₩14,900 갱신일 8월 3일",
    )
    membership_card["bounds"] = [0, 720, 1080, 980]

    candidates = extract_navigation_candidates(
        request(
            request_id="req_static_heading_ocr",
            session_id="session_static_heading_ocr",
            elements=[heading, duplicate_ocr, membership_card],
        )
    )

    assert [candidate.element_id for candidate in candidates] == ["youtube-premium-card"]


def assert_static_native_button_semantics_preserve_coordinate_ocr() -> None:
    profile_name = element(
        "profile-name",
        "왕십리캔들마스터",
        clickable=False,
        role="button",
    )
    profile_name["bounds"] = [445, 855, 996, 918]
    coordinate_ocr = element(
        "ocr-profile-name",
        "왕십리캔들마스터",
        clickable=True,
        role="button",
    )
    coordinate_ocr["view_id"] = "exitguide:ocr"
    coordinate_ocr["bounds"] = [445, 855, 996, 918]

    candidates = extract_navigation_candidates(
        request(
            request_id="req_static_button_coordinate_ocr",
            session_id="session_static_button_coordinate_ocr",
            elements=[profile_name, coordinate_ocr],
        )
    )

    assert [candidate.element_id for candidate in candidates] == ["ocr-profile-name"]


def assert_read_only_purchase_hub_is_low_risk() -> None:
    candidates = extract_navigation_candidates(
        request(
            request_id="req_purchase_hub_risk",
            session_id="session_purchase_hub_risk",
            elements=[element("purchases", "Purchases and memberships")],
        )
    )
    assert len(candidates) == 1
    assert candidates[0].risk_level == "low"


def assert_read_only_insurance_refund_labels_are_low_risk() -> None:
    candidates = extract_navigation_candidates(
        request(
            request_id="req_insurance_refund_risk",
            session_id="session_insurance_refund_risk",
            elements=[
                element("refund-hub", "환급/해지"),
                element("surrender-value", "해지환급금 조회"),
                element("cancel-policy", "계약 해지"),
            ],
        )
    )
    by_id = {candidate.element_id: candidate for candidate in candidates}
    assert by_id["refund-hub"].risk_level == "low"
    assert by_id["surrender-value"].risk_level == "low"
    assert by_id["cancel-policy"].risk_level == "medium"


ANDROID_CONTROL_SAMPLE = Path(__file__).resolve().parents[3] / "fixtures" / "android-control" / "normalized-sample.jsonl"


def assert_unknown_app_is_guided_without_prebuilt_route() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        response = observe(
            repository,
            request(
                request_id="req_unknown_1",
                session_id="session_unknown",
                elements=[
                    element("title", "계정", clickable=False, role="heading"),
                    element("membership", "구매 항목 및 멤버십"),
                    element("settings", "설정"),
                ],
            ),
        )
        assert response.status == "guided"
        assert response.decision_mode == "deterministic_fallback"
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "membership"
        assert response.graph_update.screen_created is True
        assert response.graph_update.actions_created == 2
        snapshot = repository.snapshot("com.unknown.video")
        assert snapshot.screen_count == 1
        assert snapshot.action_count == 2
        assert snapshot.transition_count == 0


def assert_subscription_feed_is_not_confused_with_billing() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        payload = request(
            request_id="req_subscription_homonym",
            session_id="session_subscription_homonym",
            goal_text="유튜브 프리미엄 구독을 해지하고 싶어",
            elements=[
                positioned_element("home", "홈", [0, 2100, 200, 2240]),
                positioned_element("shorts", "Shorts", [200, 2100, 400, 2240]),
                positioned_element("subscriptions", "구독", [400, 2100, 600, 2240]),
                positioned_element("my_page", "내 페이지", [800, 2100, 1080, 2240]),
            ],
        )
        settings = Settings(
            navigation_agent_provider="mock",
            android_control_index_path="",
        )
        response = observe_universal_navigation(payload, settings=settings, repository=repository)
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "my_page"
        assert response.recommendation.selected_element_id != "subscriptions"


def assert_successful_trace_becomes_reusable_graph_memory() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        first = observe(
            repository,
            request(
                request_id="req_trace_1",
                session_id="session_trace",
                elements=[
                    element("title", "계정", clickable=False, role="heading"),
                    element("membership", "구매 항목 및 멤버십"),
                    element("settings", "설정"),
                ],
            ),
        )
        second = observe(
            repository,
            request(
                request_id="req_trace_2",
                session_id="session_trace",
                elements=[
                    element("title", "구매 항목 및 멤버십", clickable=False, role="heading"),
                    element("premium", "Premium 멤버십"),
                    element("history", "구매 내역"),
                ],
                transition=transition(first, "membership"),
            ),
        )
        assert second.recommendation is not None
        assert second.recommendation.selected_element_id == "premium"
        third = observe(
            repository,
            request(
                request_id="req_trace_3",
                session_id="session_trace",
                elements=[
                    element("title", "멤버십 관리", clickable=False, role="heading"),
                    element("deactivate", "비활성화"),
                    element("billing", "결제 수단"),
                ],
                transition=transition(second, "premium"),
            ),
        )
        assert third.recommendation is not None
        assert third.recommendation.selected_element_id == "deactivate"
        completed = observe(
            repository,
            request(
                request_id="req_trace_4",
                session_id="session_trace",
                elements=[
                    element("complete", "구독 해지 완료", clickable=False, role="heading"),
                    element("next", "다음 결제 없음", clickable=False),
                ],
                transition=transition(third, "deactivate"),
            ),
        )
        assert completed.status == "goal_completed"
        snapshot = repository.snapshot("com.unknown.video")
        assert snapshot.screen_count == 4
        assert snapshot.transition_count == 3

        reused = observe(
            repository,
            request(
                request_id="req_trace_reuse",
                session_id="session_reuse",
                elements=[
                    element("title", "계정", clickable=False, role="heading"),
                    element("membership_new_id", "구매 항목 및 멤버십"),
                    element("settings_new_id", "설정"),
                ],
            ),
        )
        assert reused.decision_mode == "graph_cache"
        assert reused.recommendation is not None
        assert reused.recommendation.selected_element_id == "membership_new_id"
        assert reused.recommendation.confidence == 0.93


def assert_risky_action_requires_user_confirmation() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        response = observe(
            repository,
            request(
                request_id="req_risk",
                session_id="session_risk",
                goal_text="계정을 삭제하고 싶어",
                elements=[
                    element("delete", "계정 삭제"),
                    element("settings", "설정"),
                ],
            ),
        )
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "delete"
        assert response.recommendation.risk_level == "high"
        assert response.recommendation.requires_user_confirmation is True
        assert response.warnings


def assert_sensitive_labels_are_redacted_before_storage() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        observe(
            repository,
            request(
                request_id="req_private",
                session_id="session_private",
                elements=[
                    element("profile", "yang@example.com 계정 010-1234-5678"),
                    element("settings", "설정"),
                ],
            ),
        )
        connection = sqlite3.connect(repository.database_path)
        try:
            serialized = json.dumps(connection.execute("SELECT label FROM universal_actions").fetchall())
            structures = json.dumps(connection.execute("SELECT structure_json FROM universal_screens").fetchall())
        finally:
            connection.close()
        assert "yang@example.com" not in serialized + structures
        assert "010-1234-5678" not in serialized + structures
        assert "[email]" in serialized + structures
        assert "[phone]" in serialized + structures


def assert_exaone_uses_hermes_tool_contract() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        captured: dict = {}
        original_post = agent_module.httpx.post

        def fake_post(url, *, headers, json, timeout):
            captured.update({"url": url, "headers": headers, "payload": json, "timeout": timeout})
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "recommend_navigation_action",
                                            "arguments": json_module_dumps(
                                                {
                                                    "goal_interpretation": "마케팅 알림 해제",
                                                    "target_function": "알림 설정 열기",
                                                    "selected_element_id": "settings",
                                                    "reason": "알림 설정으로 이어질 가능성이 높습니다.",
                                                    "expected_next_screen": "설정 화면",
                                                    "instruction": "설정을 눌러 주세요.",
                                                    "confidence": 0.88,
                                                    "goal_reached": False,
                                                    "requires_user_confirmation": False,
                                                }
                                            ),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        agent_module.httpx.post = fake_post
        try:
            android_control_path = Path(temporary_directory) / "android-control.sqlite"
            AndroidControlIndex(android_control_path).build(read_normalized_jsonl(ANDROID_CONTROL_SAMPLE))
            settings = Settings(
                navigation_agent_provider="exaone",
                navigation_agent_allow_fallback=True,
                navigation_agent_timeout_seconds=10.0,
                android_control_index_path=str(android_control_path),
                exaone_api_key="test-key",
                exaone_model="test-model",
                exaone_base_url="https://example.invalid/v1",
            )
            response = observe_universal_navigation(
                request(
                    request_id="req_exaone",
                    session_id="session_exaone",
                    goal_text="마케팅 알림을 끄고 싶어",
                    elements=[element("settings", "설정"), element("profile", "프로필")],
                ),
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post
        assert response.decision_mode == "exaone"
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "settings"
        tool = captured["payload"]["tools"][0]
        assert tool["function"]["name"] == "recommend_navigation_action"
        assert captured["payload"]["tool_choice"] == "required"
        assert captured["payload"]["parallel_tool_calls"] is False
        assert captured["payload"]["temperature"] == 0.1
        assert captured["payload"]["top_p"] == 0.9
        assert captured["payload"]["chat_template_kwargs"]["enable_thinking"] is False
        assert captured["timeout"] == 10.0
        prompt = json.loads(captured["payload"]["messages"][1]["content"])
        assert prompt["goal_plan"]["intent"] == "marketing_notification_control"
        assert prompt["android_control_demonstrations"]
        assert all("inferred_functions" in item for item in prompt["action_candidates"])
        selected_enum = tool["function"]["parameters"]["properties"]["selected_element_id"]["enum"]
        assert selected_enum == ["", "settings", "profile"]


def assert_exaone_planner_uses_strict_bounded_hermes_actions() -> None:
    captured: dict = {}
    original_post = agent_module.httpx.post

    def fake_post(url, *, headers, json, timeout):
        captured.update({"payload": json, "timeout": timeout})
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "plan_navigation_step",
                                        "arguments": json_module_dumps(
                                            {
                                                "target_function": "settings.notifications",
                                                "command": "click",
                                                "selected_element_id": "settings",
                                                "reason": "알림 설정으로 이어지는 저위험 메뉴입니다.",
                                                "expected_next_screen": "설정 화면",
                                                "instruction": "설정을 확인합니다.",
                                                "confidence": 0.91,
                                            }
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

    agent_module.httpx.post = fake_post
    try:
        settings = Settings(
            navigation_agent_provider="exaone",
            navigation_agent_timeout_seconds=8.0,
            exaone_api_key="test-key",
            exaone_model="test-model",
            exaone_base_url="https://example.invalid/v1",
        )
        payload = request(
            request_id="req_exaone_planner",
            session_id="session_exaone_planner",
            goal_text="마케팅 알림을 끄고 싶어",
            elements=[element("settings", "설정"), element("feed", "추천 영상")],
        )
        candidates = extract_navigation_candidates(payload)
        result = agent_module.ExaoneNavigationDecisionProvider(settings).plan_exploration_step(
            goal_text=payload.goal_text,
            request=payload,
            candidates=candidates,
            graph_hints=[
                {
                    "source": "current_session_history",
                    "steps": [{"selected_label": "내 페이지", "outcome": "navigated"}],
                },
                {"source": "human_gold", "evidence_only": True},
            ],
            demonstrations=[],
            allow_scroll=True,
            allow_back=False,
        )
    finally:
        agent_module.httpx.post = original_post

    assert result["command"] == "click"
    assert result["selected_element_id"] == "settings"
    tool = captured["payload"]["tools"][0]["function"]
    assert tool["name"] == "plan_navigation_step"
    assert tool["parameters"]["properties"]["command"]["enum"] == [
        "scroll_forward",
        "click",
        "stop_for_user",
        "wait_and_observe",
    ]
    assert captured["payload"]["max_tokens"] == 800
    assert tool["parameters"]["properties"]["reason"]["maxLength"] == 240
    prompt = json.loads(captured["payload"]["messages"][1]["content"])
    assert prompt["current_session_history"] == [
        {"selected_label": "내 페이지", "outcome": "navigated"}
    ]
    assert all(
        item.get("source") != "current_session_history"
        for item in prompt["human_gold_and_app_graph_evidence"]
    )
    assert prompt["human_gold_and_app_graph_evidence"][0]["evidence_only"] is True
    assert prompt["allowed_commands"] == [
        "scroll_forward",
        "click",
        "stop_for_user",
        "wait_and_observe",
    ]
    invalid = dict(result, command="back", selected_element_id="settings")
    try:
        agent_module._validate_planner_arguments(
            invalid,
            candidate_ids=[candidate.element_id for candidate in candidates],
            allowed_commands=["click", "back"],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("non-click planner action accepted a coordinate candidate")


def assert_exaone_planner_repairs_one_malformed_hermes_call() -> None:
    original_post = agent_module.httpx.post
    calls: list[dict] = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"payload": json, "timeout": timeout})
        if len(calls) == 1:
            arguments = '{"target_function":"notification.settings","command":"click"'
        else:
            arguments = json_module_dumps(
                {
                    "target_function": "notification.settings",
                    "command": "click",
                    "selected_element_id": "settings",
                    "reason": "현재 화면의 설정 관문입니다.",
                    "expected_next_screen": "설정 화면",
                    "instruction": "설정을 엽니다.",
                    "confidence": 0.87,
                }
            )
        return FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "plan_navigation_step",
                                        "arguments": arguments,
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        )

    agent_module.httpx.post = fake_post
    try:
        settings = Settings(
            navigation_agent_provider="exaone",
            navigation_agent_timeout_seconds=10.0,
            exaone_api_key="test-key",
            exaone_model="test-model",
            exaone_base_url="https://example.invalid/v1",
        )
        payload = request(
            request_id="req_exaone_planner_repair",
            session_id="session_exaone_planner_repair",
            goal_text="알림 설정을 열고 싶어",
            elements=[element("settings", "설정")],
        )
        result = agent_module.ExaoneNavigationDecisionProvider(settings).plan_exploration_step(
            goal_text=payload.goal_text,
            request=payload,
            candidates=extract_navigation_candidates(payload),
            graph_hints=[],
            demonstrations=[],
            allow_scroll=False,
            allow_back=False,
        )
    finally:
        agent_module.httpx.post = original_post

    assert result["selected_element_id"] == "settings"
    assert len(calls) == 2
    assert all(call["timeout"] == 5.0 for call in calls)
    assert len(calls[1]["payload"]["messages"]) == 2
    assert "schema-repair retry" in calls[1]["payload"]["messages"][0]["content"]
    assert calls[1]["payload"]["temperature"] == 0.0
    assert calls[1]["payload"]["max_tokens"] == 1200
    assert calls[1]["payload"]["tool_choice"]["function"]["name"] == "plan_navigation_step"


def assert_planner_accepts_exact_hermes_content_wrapper_only() -> None:
    arguments = {
        "target_function": "notification.settings",
        "command": "click",
        "selected_element_id": "settings",
        "reason": "설정 관문",
        "expected_next_screen": "설정",
        "instruction": "설정을 엽니다.",
        "confidence": 0.8,
    }
    wrapped = {
        "name": "plan_navigation_step",
        "arguments": arguments,
    }
    parsed = agent_module._planner_arguments(
        {"content": "<tool_call>\n" + json_module_dumps(wrapped) + "\n</tool_call>"}
    )
    assert parsed == arguments
    try:
        agent_module._planner_arguments(
            {"content": json_module_dumps(wrapped) + "\n" + json_module_dumps(wrapped)}
        )
    except ValueError:
        pass
    else:
        raise AssertionError("multiple planner pseudo calls were accepted")


def assert_exaone_total_deadline_stops_trickle_style_active_call() -> None:
    """A continuously active sync transport must not extend total API time.

    ``httpx`` itself treats its timeout as an inactivity threshold.  This fake
    models a peer that remains active indefinitely and therefore would never
    trip that threshold; the independent wall deadline still has to return.
    """

    original_post = agent_module.httpx.post
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    captured: dict[str, object] = {}

    def active_forever_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "payload": json, "timeout": timeout})
        entered.set()
        # Simulate recurring network activity that stays below every
        # per-operation inactivity timeout until the test releases the worker.
        while not release.wait(0.005):
            pass
        finished.set()
        return FakeResponse({"choices": []})

    agent_module.httpx.post = active_forever_post
    started = time.perf_counter()
    try:
        try:
            agent_module._post_with_total_deadline(
                "https://example.invalid/v1/chat/completions",
                headers={"Authorization": "Bearer test"},
                payload={"model": "test-model"},
                timeout_seconds=0.05,
            )
        except agent_module.NavigationDecisionDeadlineExceeded as exc:
            assert "total wall-clock deadline" in str(exc)
        else:
            raise AssertionError("expected the total K-EXAONE wall deadline to expire")
    finally:
        elapsed = time.perf_counter() - started
        release.set()
        agent_module.httpx.post = original_post

    assert entered.is_set()
    assert finished.wait(0.5), "timed-out daemon worker did not release its bounded slot"
    assert 0.035 <= elapsed < 0.25, elapsed
    assert captured["timeout"] == 0.05


def assert_hermes_actual_tool_call_has_priority_and_known_wrappers_are_accepted() -> None:
    actual = valid_hermes_arguments(selected_element_id="settings")
    conflicting_content = valid_hermes_arguments(selected_element_id="profile")
    parsed = agent_module._tool_arguments(
        {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "recommend_navigation_action",
                        # A deployed Hermes endpoint has appended this exact
                        # transport sentinel to otherwise valid arguments.
                        "arguments": json_module_dumps(actual) + "\n</tool_call>",
                    },
                }
            ],
            # A pseudo call may be repeated in content.  It must never
            # override the structured tool_calls channel.
            "content": (
                "<tool_call>\n"
                + json_module_dumps(
                    {
                        "name": "recommend_navigation_action",
                        "arguments": conflicting_content,
                    }
                )
                + "\n</tool_call>"
            ),
        }
    )
    assert parsed == actual

    exact_named_wrapper = {
        "recommend_navigation_action": valid_hermes_arguments(selected_element_id="settings")
    }
    fenced = agent_module._tool_arguments(
        {"content": "```json\n" + json_module_dumps(exact_named_wrapper) + "\n```"}
    )
    assert fenced == actual

    pseudo_call = {
        "name": "recommend_navigation_action",
        "arguments": valid_hermes_arguments(selected_element_id="settings"),
    }
    tagged = agent_module._tool_arguments(
        {"content": "<tool_call>\n" + json_module_dumps(pseudo_call) + "\n</tool_call>"}
    )
    assert tagged == actual


def assert_hermes_rejects_ambiguous_or_malformed_calls_and_strict_types() -> None:
    valid = valid_hermes_arguments(selected_element_id="settings")
    valid_call = {
        "type": "function",
        "function": {
            "name": "recommend_navigation_action",
            "arguments": json_module_dumps(valid),
        },
    }

    invalid_messages = [
        # Two JSON values and arbitrary trailing prose are never repaired.
        {"content": json_module_dumps(valid) + "\n" + json_module_dumps(valid)},
        {"content": json_module_dumps(valid) + " trailing text"},
        # Only one structured call to the one exposed function is legal.
        {"tool_calls": [valid_call, valid_call]},
        {
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "delete_account",
                        "arguments": json_module_dumps(valid),
                    },
                }
            ],
            "content": json_module_dumps(valid),
        },
        # Wrapper keys must be exact; hidden metadata is not ignored.
        {
            "content": json_module_dumps(
                {
                    "name": "recommend_navigation_action",
                    "arguments": valid,
                    "second_call": valid,
                }
            )
        },
        {"content": json_module_dumps({"some_other_wrapper": valid})},
        {"content": "```python\n" + json_module_dumps(valid) + "\n```"},
    ]
    for message in invalid_messages:
        expect_value_error(lambda message=message: parse_hermes_decision(message, ["settings"]))

    invalid_arguments: list[dict] = []
    for field, value in (
        ("goal_reached", "false"),
        ("requires_user_confirmation", 0),
        ("confidence", True),
        ("selected_element_id", 7),
        ("reason", None),
    ):
        payload = dict(valid)
        payload[field] = value
        invalid_arguments.append(payload)
    missing = dict(valid)
    missing.pop("instruction")
    invalid_arguments.append(missing)
    unexpected = dict(valid)
    unexpected["hidden_action"] = "click"
    invalid_arguments.append(unexpected)
    nonfinite = dict(valid)
    nonfinite["confidence"] = float("nan")
    invalid_arguments.append(nonfinite)

    for arguments in invalid_arguments:
        expect_value_error(lambda arguments=arguments: agent_module._decision_from_arguments(arguments))

    decision = agent_module._decision_from_arguments(valid_hermes_arguments(selected_element_id="off_screen"))
    expect_value_error(lambda: agent_module._validate_selected_element(decision, ["settings"]))


def assert_failed_exaone_attempt_records_model_decision_time() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        original_post = agent_module.httpx.post

        def fake_post(url, *, headers, json, timeout):
            agent_module.time.sleep(0.012)
            arguments = json_module_dumps(valid_hermes_arguments(selected_element_id="settings"))
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                # A second object must fail and invoke the
                                # deterministic fallback, while retaining the
                                # elapsed K-EXAONE attempt time.
                                "content": arguments + "\n" + arguments
                            }
                        }
                    ]
                }
            )

        agent_module.httpx.post = fake_post
        try:
            settings = Settings(
                navigation_agent_provider="exaone",
                navigation_agent_allow_fallback=True,
                exaone_api_key="test-key",
                exaone_model="test-model",
            )
            response = observe_universal_navigation(
                request(
                    request_id="req_exaone_failed_timing",
                    session_id="session_exaone_failed_timing",
                    elements=[element("settings", "설정"), element("profile", "프로필")],
                ),
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post

        assert response.decision_mode == "deterministic_fallback"
        assert response.performance is not None
        assert response.performance.model_decision_ms >= 8.0
        assert any("폴백" in warning for warning in response.warnings)


def assert_exploration_fails_closed_when_exaone_planner_is_unavailable() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        original_post = agent_module.httpx.post
        observed_timeouts: list[float] = []

        def fake_post(url, *, headers, json, timeout):
            observed_timeouts.append(float(timeout))
            return FakeResponse({"choices": [{"message": {"content": "not-a-tool-call"}}]})

        agent_module.httpx.post = fake_post
        try:
            android_control_path = Path(temporary_directory) / "android-control.sqlite"
            AndroidControlIndex(android_control_path).build(
                read_normalized_jsonl(ANDROID_CONTROL_SAMPLE)
            )
            settings = Settings(
                navigation_agent_provider="exaone",
                navigation_agent_allow_fallback=True,
                android_control_index_path=str(android_control_path),
                exaone_api_key="test-key",
                exaone_model="test-model",
                navigation_agent_timeout_seconds=35.0,
            )
            payload = request(
                request_id="req_exaone_explore_fail_closed",
                session_id="session_exaone_explore_fail_closed",
                elements=[
                    element("membership", "구매 항목 및 멤버십"),
                    element("settings", "설정"),
                ],
            ).model_copy(update={"operation_mode": "explore"})
            response = observe_universal_navigation(
                payload,
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post

        assert response.phase == "stopped", response.model_dump()
        assert response.runtime_state == "FINISHED"
        assert response.runtime_state_trace == [
            "OBSERVING",
            "RETRIEVING",
            "PLANNING",
            "SAFETY_CHECK",
            "FINISHED",
        ]
        assert response.automation.action == "stop", response.model_dump()
        assert response.automation.safe_to_execute is False, response.model_dump()
        assert "K-EXAONE" in response.automation.reason, response.model_dump()
        assert observed_timeouts == [17.5, 17.5], observed_timeouts
        connection = sqlite3.connect(repository.database_path)
        connection.row_factory = sqlite3.Row
        try:
            clicks = int(
                connection.execute(
                    "SELECT COUNT(*) FROM universal_exploration_attempts WHERE command = 'click'"
                ).fetchone()[0]
            )
            trace = connection.execute(
                """
                SELECT planner_command, candidate_json, evidence_sources_json,
                       evidence_json, planner_input_sha256, outcome,
                       safety_action, safety_allowed
                FROM navigation_retrieval_events
                WHERE request_id = ?
                """,
                (payload.request_id,),
            ).fetchone()
        finally:
            connection.close()
        assert clicks == 0
        assert trace is not None
        assert trace["planner_command"] == "stop_for_user"
        assert len(json.loads(trace["candidate_json"])) == 2
        assert "android_control" in json.loads(trace["evidence_sources_json"])
        assert json.loads(trace["evidence_json"])["android_control"]
        assert len(trace["planner_input_sha256"]) == 64
        assert str(trace["outcome"]).startswith(response.status), dict(trace)
        assert trace["safety_action"] == "stop"
        assert int(trace["safety_allowed"]) == 0


def assert_exaone_must_confirm_terminal_destination() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        original_post = agent_module.httpx.post
        observed_allowed_commands: list[str] = []

        def fake_post(url, *, headers, json, timeout):
            schema = json["tools"][0]["function"]["parameters"]
            observed_allowed_commands.extend(schema["properties"]["command"]["enum"])
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": "plan_navigation_step",
                                            "arguments": json_module_dumps(
                                                {
                                                    "target_function": "subscription.cancel.entry",
                                                    "command": "mark_destination",
                                                    "selected_element_id": "",
                                                    "alternative_candidate_ids": [],
                                                    "reason": "해지 최종 버튼과 화면 문맥이 함께 보입니다.",
                                                    "expected_next_screen": "사용자 최종 확인",
                                                    "instruction": "최종 해지는 직접 눌러 주세요.",
                                                    "confidence": 0.93,
                                                }
                                            ),
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        agent_module.httpx.post = fake_post
        try:
            settings = Settings(
                navigation_agent_provider="exaone",
                android_control_index_path="",
                exaone_api_key="test-key",
                exaone_model="test-model",
            )
            payload = request(
                request_id="req_exaone_terminal_confirmation",
                session_id="session_exaone_terminal_confirmation",
                elements=[element("cancel-final", "구독 해지")],
            ).model_copy(update={"operation_mode": "explore"})
            response = observe_universal_navigation(
                payload,
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post

        assert "mark_destination" in observed_allowed_commands
        assert response.phase == "destination_reached", response.model_dump()
        assert response.runtime_state == "WAITING_FOR_USER_FINAL_ACTION"
        assert response.runtime_state_trace[-2:] == [
            "DESTINATION_REACHED",
            "WAITING_FOR_USER_FINAL_ACTION",
        ]
        assert response.automation.action == "stop", response.model_dump()
        assert response.automation.safe_to_execute is False, response.model_dump()
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "cancel-final"


def assert_invalid_model_action_falls_back_safely() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        original_post = agent_module.httpx.post

        def fake_post(url, *, headers, json, timeout):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "recommend_navigation_action",
                                            "arguments": json_module_dumps(
                                                {
                                                    "goal_interpretation": "구독 해지",
                                                    "target_function": "숨은 버튼",
                                                    "selected_element_id": "not_on_screen",
                                                    "reason": "잘못된 후보",
                                                    "expected_next_screen": "",
                                                    "instruction": "",
                                                    "confidence": 0.9,
                                                    "goal_reached": False,
                                                    "requires_user_confirmation": False,
                                                }
                                            )
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        agent_module.httpx.post = fake_post
        try:
            settings = Settings(
                navigation_agent_provider="exaone",
                navigation_agent_allow_fallback=True,
                exaone_api_key="test-key",
                exaone_model="test-model",
            )
            response = observe_universal_navigation(
                request(
                    request_id="req_bad_exaone",
                    session_id="session_bad_exaone",
                    elements=[element("membership", "멤버십"), element("settings", "설정")],
                ),
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post
        assert response.decision_mode == "deterministic_fallback"
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id in {"membership", "settings"}
        assert any("폴백" in warning for warning in response.warnings)


def assert_semantically_weaker_model_choice_is_guarded() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        original_post = agent_module.httpx.post

        def fake_post(url, *, headers, json, timeout):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "recommend_navigation_action",
                                            "arguments": json_module_dumps(
                                                {
                                                    "goal_interpretation": "구독 해지",
                                                    "target_function": "설정 열기",
                                                    "selected_element_id": "settings",
                                                    "reason": "일반 설정을 먼저 확인합니다.",
                                                    "expected_next_screen": "설정",
                                                    "instruction": "설정을 눌러 주세요.",
                                                    "confidence": 0.9,
                                                    "goal_reached": False,
                                                    "requires_user_confirmation": False,
                                                }
                                            )
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        agent_module.httpx.post = fake_post
        try:
            settings = Settings(
                navigation_agent_provider="exaone",
                navigation_agent_allow_fallback=True,
                exaone_api_key="test-key",
                exaone_model="test-model",
            )
            response = observe_universal_navigation(
                request(
                    request_id="req_guard",
                    session_id="session_guard",
                    elements=[
                        element("membership", "구매 항목 및 멤버십"),
                        element("settings", "설정"),
                    ],
                ),
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post
        assert response.decision_mode == "deterministic_fallback"
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "membership"
        assert any("가드레일" in warning for warning in response.warnings)


def assert_low_confidence_matching_model_choice_uses_independent_score() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        original_post = agent_module.httpx.post

        def fake_post(url, *, headers, json, timeout):
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "recommend_navigation_action",
                                            "arguments": json_module_dumps(
                                                {
                                                    "goal_interpretation": "cancel youtube premium subscription",
                                                    "target_function": "open account entry",
                                                    "selected_element_id": "my_page",
                                                    "reason": "",
                                                    "expected_next_screen": "account and purchases",
                                                    "instruction": "Open My page.",
                                                    "confidence": 0.0,
                                                    "goal_reached": False,
                                                    "requires_user_confirmation": False,
                                                }
                                            )
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        agent_module.httpx.post = fake_post
        try:
            settings = Settings(
                navigation_agent_provider="exaone",
                navigation_agent_allow_fallback=True,
                android_control_index_path="",
                exaone_api_key="test-key",
                exaone_model="test-model",
            )
            response = observe_universal_navigation(
                request(
                    request_id="req_low_confidence_match",
                    session_id="session_low_confidence_match",
                    goal_text="cancel youtube premium subscription",
                    elements=[
                        positioned_element("home", "Home", [0, 2100, 200, 2240]),
                        positioned_element("shorts", "Shorts", [200, 2100, 400, 2240]),
                        positioned_element("subscriptions", "Subscriptions", [400, 2100, 600, 2240]),
                        positioned_element("my_page", "My page", [800, 2100, 1080, 2240]),
                    ],
                ),
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module.httpx.post = original_post
        assert response.decision_mode == "deterministic_fallback"
        assert response.recommendation is not None
        assert response.recommendation.selected_element_id == "my_page"
        assert response.recommendation.confidence >= 0.55
        assert response.recommendation.selected_element_id != "subscriptions"
        assert any("독립 점수" in warning for warning in response.warnings)


def assert_initially_completed_goal_closes_session() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        response = observe(
            repository,
            request(
                request_id="req_already_complete",
                session_id="session_already_complete",
                elements=[element("complete", "구독 해지 완료", clickable=False, role="heading")],
            ),
        )
        assert response.status == "goal_completed"
        connection = sqlite3.connect(repository.database_path)
        try:
            status = connection.execute(
                "SELECT status FROM universal_sessions WHERE session_id = ?",
                ("session_already_complete",),
            ).fetchone()[0]
        finally:
            connection.close()
        assert status == "completed"


def assert_screen_state_changes_have_distinct_fingerprints() -> None:
    unchecked = request(
        request_id="req_switch_off",
        session_id="session_switch",
        elements=[switch_element("marketing", "마케팅 알림", checked=False)],
    )
    checked = request(
        request_id="req_switch_on",
        session_id="session_switch",
        elements=[switch_element("marketing", "마케팅 알림", checked=True)],
    )
    assert fingerprint_screen(unchecked.app_package, unchecked.screen) != fingerprint_screen(
        checked.app_package,
        checked.screen,
    )


def assert_ocr_geometry_does_not_fragment_screen_identity() -> None:
    first_ocr = element("ocr-first", "배민클럽 이용 중", clickable=False, role="text")
    first_ocr["view_id"] = "exitguide:ocr"
    first_ocr["bounds"] = [84, 760, 360, 820]
    second_ocr = element("ocr-second", "배민클럽 이용중", clickable=False, role="text")
    second_ocr["view_id"] = "exitguide:ocr"
    second_ocr["bounds"] = [86, 763, 362, 823]
    first = request(
        request_id="req_ocr_fingerprint_1",
        session_id="session_ocr_fingerprint",
        elements=[element("club", "브랜드 쿠폰팩"), first_ocr],
    )
    second = request(
        request_id="req_ocr_fingerprint_2",
        session_id="session_ocr_fingerprint",
        elements=[element("club", "브랜드 쿠폰팩"), second_ocr],
    )
    assert fingerprint_screen(first.app_package, first.screen) == fingerprint_screen(
        second.app_package,
        second.screen,
    )


def assert_transition_cannot_reuse_another_session_recommendation() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = repository_at(temporary_directory)
        first = observe(
            repository,
            request(
                request_id="req_owner",
                session_id="session_owner",
                elements=[element("membership", "멤버십"), element("settings", "설정")],
            ),
        )
        forged = request(
            request_id="req_forged",
            session_id="session_attacker",
            elements=[element("premium", "Premium 멤버십"), element("history", "구매 내역")],
            transition={
                "from_screen_fingerprint": first.screen_fingerprint,
                "performed_element_id": "membership",
                "recommendation_id": first.recommendation.recommendation_id,
                "outcome": "navigated",
            },
        )
        response = observe(repository, forged)
        assert response.graph_update.transition_recorded is True
        connection = sqlite3.connect(repository.database_path)
        try:
            owner_step = connection.execute(
                "SELECT performed FROM universal_session_steps WHERE recommendation_id = ?",
                (first.recommendation.recommendation_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert owner_step == 0


def observe(repository: UniversalNavigationGraphRepository, payload: UniversalNavigationObserveRequest):
    settings = Settings(navigation_agent_provider="mock", navigation_agent_allow_fallback=True)
    return observe_universal_navigation(payload, settings=settings, repository=repository)


def repository_at(directory: str) -> UniversalNavigationGraphRepository:
    return UniversalNavigationGraphRepository(Path(directory) / "universal-navigation.sqlite")


def request(
    *,
    request_id: str,
    session_id: str,
    elements: list[dict],
    goal_text: str = "구독을 해지하고 싶어",
    transition: dict | None = None,
) -> UniversalNavigationObserveRequest:
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": request_id,
            "session_id": session_id,
            "app_package": "com.unknown.video",
            "app_version": "9.9.9",
            "locale": "ko-KR",
            "goal_text": goal_text,
            "screen": {
                "activity_name": "com.unknown.video.MainActivity",
                "window_title": "",
                "elements": elements,
            },
            "transition": transition,
        }
    )


def element(element_id: str, text: str, *, clickable: bool = True, role: str = "button") -> dict:
    return {
        "id": element_id,
        "parent_id": "root",
        "text": text,
        "content_description": None,
        "view_id": f"com.unknown.video:id/{element_id}",
        "role": role,
        "clickable": clickable,
        "enabled": True,
        "visible": True,
        "bounds": [20, 100, 1000, 180],
    }


def positioned_element(element_id: str, text: str, bounds: list[int]) -> dict:
    payload = element(element_id, text)
    payload["bounds"] = bounds
    return payload


def switch_element(element_id: str, text: str, *, checked: bool) -> dict:
    payload = element(element_id, text, role="switch")
    payload["checkable"] = True
    payload["checked"] = checked
    return payload


def transition(response, element_id: str) -> dict:
    assert response.recommendation is not None
    return {
        "from_screen_fingerprint": response.screen_fingerprint,
        "performed_element_id": element_id,
        "recommendation_id": response.recommendation.recommendation_id,
        "outcome": "navigated",
    }


def json_module_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def valid_hermes_arguments(*, selected_element_id: str = "") -> dict:
    return {
        "goal_interpretation": "구독 해지",
        "target_function": "구독 관리 열기",
        "selected_element_id": selected_element_id,
        "reason": "현재 화면의 안전한 설정 진입점입니다.",
        "expected_next_screen": "구독 관리 화면",
        "instruction": "설정을 눌러 주세요.",
        "confidence": 0.82,
        "goal_reached": False,
        "requires_user_confirmation": False,
    }


def parse_hermes_decision(message: dict, candidate_ids: list[str]):
    arguments = agent_module._tool_arguments(message)
    decision = agent_module._decision_from_arguments(arguments)
    agent_module._validate_selected_element(decision, candidate_ids)
    return decision


def expect_value_error(callback) -> None:
    try:
        callback()
    except ValueError:
        return
    raise AssertionError("expected ValueError")


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


if __name__ == "__main__":
    main()
