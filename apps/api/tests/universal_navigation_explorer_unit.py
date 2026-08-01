import gc
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services import universal_navigation_agent as agent_module
from app.services.universal_navigation_agent import extract_navigation_candidates, observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository
from app.services.universal_navigation_graph import ExplorationState
from app.services.navigation_performance import StageMeasurement
from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.navigation_semantics import infer_goal_plan
from app.services.universal_navigation_explorer import (
    _automatic_click_is_low_risk,
    _looks_like_creator_audience_metric,
    _looks_like_final_state_change_action,
    _looks_like_goal_irrelevant_auxiliary_link,
    _looks_like_management_goal_media_detour,
    _looks_like_paid_subscription_content_detour,
    _is_explicit_settings_gateway,
    _looks_like_notification_inbox_control,
    _looks_like_transient_feedback_overlay,
    _looks_like_transient_in_app_message_overlay,
    _screen_is_notification_preferences_surface,
    _same_as_current_screen,
    _subscription_detail_needs_bounded_reobserve,
    _satisfies_semantic_terminal_concepts,
)


# The function catalog is deterministic read-only test infrastructure.  A
# shared process-local database prevents every graph-isolated test from
# rebuilding and retaining another ~180 MB catalog cache entry.
_SHARED_FUNCTION_CATALOG_DIRECTORY = TemporaryDirectory(
    prefix="exitguide-explorer-catalog-",
    ignore_cleanup_errors=True,
)
_SHARED_FUNCTION_CATALOG_DB = (
    Path(_SHARED_FUNCTION_CATALOG_DIRECTORY.name) / "functions.sqlite"
)


def main() -> None:
    checks = (
        assert_korean_notification_setting_goals_resolve_canonical_destination,
        assert_action_owned_top_bar_label_is_not_current_screen_title,
        assert_short_settings_ocr_noise_is_a_gateway,
        assert_automatic_click_requires_candidate_and_action_to_be_low_risk,
        assert_delete_all_variants_are_destructive_final_actions,
        assert_destructive_goal_does_not_stop_on_home_screen_unnamed_icons,
        assert_safe_exploration_returns_then_switches_to_manual_route,
        assert_running_exploration_joins_verified_route_at_destination,
        assert_terminal_and_state_changing_controls_are_never_auto_clicked,
        assert_catalog_never_auto_targets_are_user_owned_boundaries,
        assert_product_name_overlap_cannot_fake_a_terminal_destination,
        assert_exploration_budget_stops_additional_automation,
        assert_youtube_premium_controls_are_recognized,
        assert_youtube_membership_list_opens_active_plan_instead_of_claiming_destination,
        assert_youtube_loading_detail_is_reobserved_then_stops_at_late_cancel_control,
        assert_youtube_physical_detail_prefers_cancel_over_support_and_external_links,
        assert_youtube_sparse_purchase_page_backtracks_from_global_navigation,
        assert_youtube_selected_playlist_is_not_a_cancellation_destination,
        assert_creator_audience_metrics_are_not_paid_subscription_progress,
        assert_youtube_paid_subscription_rejects_creator_content_detours,
        assert_youtube_notification_settings_rejects_watch_history_videos,
        assert_netflix_paid_subscription_prefers_account_over_catalog_content,
        assert_backtracked_branch_is_not_reselected_after_ocr_fingerprint_change,
        assert_youtube_settings_entry_is_preferred,
        assert_baemin_gift_is_not_subscription_progress,
        assert_baemin_active_membership_sparse_detail_is_reobserved,
        assert_notification_inbox_guard_accepts_missing_resource_id,
        assert_notification_preferences_surface_accepts_accessibility_back_title,
        assert_notification_settings_distinguish_inbox_and_selected_content,
        assert_notification_settings_prefers_settings_over_account_commerce,
        assert_transient_recovery_preserves_one_parent_gateway_retry,
        assert_survey_overlay_retries_account_then_opens_settings,
        assert_full_screen_in_app_message_is_safely_dismissed,
        assert_scroll_and_unlabeled_icon_exploration,
        assert_infinite_feed_scrolls_are_bounded,
        assert_baemin_club_cancellation_route_is_recognized,
        assert_just_entered_bottom_account_tab_is_not_clicked_again,
        assert_cross_app_signup_gateways_are_explored,
        assert_netflix_signup_gateways_are_recognized,
        assert_intermediate_hubs_cannot_borrow_terminal_action_concepts,
        assert_reversible_target_gateways_beat_weak_terminal_collisions,
        assert_explicit_dead_end_uses_back_without_prior_path,
        assert_expired_session_prefers_reauthentication,
    )
    for check in checks:
        check()
        # Most checks build a large temporary semantic catalog.  CPython can
        # otherwise retain several catalog generations until process exit,
        # making the script consume many gigabytes despite each fixture being
        # independent.
        gc.collect()
    print("universal navigation explorer checks ok")


def assert_korean_notification_setting_goals_resolve_canonical_destination() -> None:
    in_app_settings_goals = (
        "배달의민족 알림 설정을 열고 싶어",
        "배달의민족 알림 설정으로 가고 싶어",
        "배달의민족 알림설정을 열고 싶어",
        "배달의 민족 알림 설정을 열고 싶어",
        "배달의민족알림설정을열고싶어",
        "배달의민족 푸시 알림을 끄고 싶어",
        "배민에서 알림 설정 변경하고 싶어",
        "알림을 끄고 싶어",
        "푸시 알림 설정",
        "유튜브 알림 수신 설정 화면으로 이동",
        "제주항공 앱에서 알림 설정을 변경하고 싶어",
    )
    for goal in in_app_settings_goals:
        plan = infer_goal_plan(goal)
        assert plan.intent == "notification_control", (goal, plan)
        assert plan.terminal_function == "notification.settings", (goal, plan)
        explorer_target = plan.terminal_function or plan.preferred_functions[-1][0]
        assert explorer_target == "notification.settings", (goal, plan)

    # Opening the notification feed is a content-reading goal, not an
    # in-app notification-preference destination.
    for inbox_goal in (
        "배달의민족 알림함을 열어 새 알림을 보고 싶어",
        "X 알림 목록에서 받은 알림을 읽고 싶어",
    ):
        assert infer_goal_plan(inbox_goal).terminal_function != "notification.settings"

    # Explicit Android/system requests must retain the system-settings route.
    for system_goal in (
        "Android 시스템 설정에서 배달의민족 앱 알림을 끄고 싶어",
        "휴대폰 설정 앱에서 배달의민족 알림 권한을 끄고 싶어",
    ):
        system_plan = infer_goal_plan(system_goal)
        assert system_plan.terminal_function != "notification.settings", (system_goal, system_plan)

    # A reviewed subtype remains more specific than generic push settings.
    marketing_plan = infer_goal_plan("배달의민족 마케팅 푸시 알림을 끄고 싶어")
    assert marketing_plan.terminal_function.startswith("marketing."), marketing_plan


def assert_action_owned_top_bar_label_is_not_current_screen_title() -> None:
    settings_parent = element("settings-touch-target", "")
    settings_parent.update(
        {
            "parent_id": "top-bar",
            "view_id": None,
            "bounds": [930, 50, 1050, 170],
        }
    )
    settings_child = {
        "id": "settings-icon",
        "parent_id": "settings-touch-target",
        "content_description": "환경설정",
        "role": "image",
        "clickable": False,
        "enabled": True,
        "visible": True,
        "bounds": [945, 65, 1035, 155],
    }
    request = custom_request(
        session_id="nested-settings-heading-guard",
        goal_text="알림 설정을 열고 싶어",
        title="마이배민",
        elements=[settings_parent, settings_child],
        app_package="com.example.firstseen.delivery",
    )

    assert not _same_as_current_screen("환경설정", request)
    assert _same_as_current_screen("마이배민", request)


def assert_short_settings_ocr_noise_is_a_gateway() -> None:
    assert _is_explicit_settings_gateway("환경설정")
    assert _is_explicit_settings_gateway("환경 설정")
    assert _is_explicit_settings_gateway("환경설젱")
    assert not _is_explicit_settings_gateway("환경 설정 방법을 자세히 설명합니다")


def assert_baemin_gift_is_not_subscription_progress() -> None:
    assert _looks_like_goal_irrelevant_auxiliary_link(
        "선물하기",
        goal_text="Cancel the Baemin Club subscription",
        target_function="subscription.cancel.entry",
    )
    assert not _looks_like_goal_irrelevant_auxiliary_link(
        "선물하기",
        goal_text="배민 상품을 친구에게 선물하고 싶어",
        target_function="gift.send",
    )


def assert_baemin_active_membership_sparse_detail_is_reobserved() -> None:
    request = custom_request(
        session_id="baemin-active-membership-loading",
        goal_text="Cancel the Baemin Club subscription",
        title="상태 표시줄",
        app_package="com.sampleapp",
        elements=[{**element("status", "8:57", role="text"), "clickable": False}],
    )
    state = ExplorationState(
        exploration_id="baemin-active-membership-loading",
        app_key="baemin",
        goal_key="cancel-baemin-club",
        goal_text="Cancel the Baemin Club subscription",
        target_function="subscription.cancel.entry",
        status="exploring",
        start_screen_fingerprint="home",
        current_screen_fingerprint="sparse-detail",
        destination_screen_fingerprint="",
        started_at="2026-07-31T00:00:00+00:00",
        updated_at="2026-07-31T00:00:01+00:00",
        action_count=3,
        back_count=0,
        max_actions=16,
        max_depth=9,
        timeout_seconds=55,
        path=(
            {
                "kind": "click",
                "label": "배민클럽 이용 중",
                "function_ids": ["subscription.detail", "subscription.manage"],
                "expected_to_screen_fingerprint": "sparse-detail",
                "pending": False,
            },
        ),
        pending=None,
        route_id="",
    )
    assert _subscription_detail_needs_bounded_reobserve(
        target_function="subscription.cancel.entry",
        request=request,
        state=state,
        latest_attempt={"command": "click", "label": "배민클럽 이용 중"},
    )


def assert_notification_inbox_guard_accepts_missing_resource_id() -> None:
    request = custom_request(
        session_id="notification-null-resource-id",
        goal_text="Open YouTube notification settings",
        title="설정",
        elements=[element("notifications", "알림")],
    )


def assert_notification_preferences_surface_accepts_accessibility_back_title() -> None:
    request = custom_request(
        session_id="youtube-notification-preferences-back-title",
        goal_text="Open YouTube notification settings",
        title="위로 이동",
        elements=[
            {**element("heading", "알림", role="text"), "clickable": False},
            {**element("mobile", "모바일 알림", role="text"), "clickable": False},
            {
                **element("subscriptions", "구독 중인 채널의 활동에 대한 알림 수신", role="text"),
                "clickable": False,
            },
            {**element("subscription-switch", "", role="switch"), "clickable": False},
            {**element("recommendations", "맞춤 동영상 알림 수신", role="text"), "clickable": False},
            {**element("recommendation-switch", "", role="switch"), "clickable": False},
        ],
    )
    assert _screen_is_notification_preferences_surface(request)
    assert not _looks_like_notification_inbox_control(
        "알림",
        role="button",
        view_id=None,
        target_function="notification.settings",
        request=request,
    )


def assert_intermediate_hubs_cannot_borrow_terminal_action_concepts() -> None:
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(Path(temporary_directory) / "terminal-concepts.sqlite")
        assert not _satisfies_semantic_terminal_concepts(
            catalog,
            "marketing.settings",
            "알림 수신 설정",
        )
        assert _satisfies_semantic_terminal_concepts(
            catalog,
            "marketing.settings",
            "이벤트와 광고성 혜택 수신",
        )
        assert not _satisfies_semantic_terminal_concepts(
            catalog,
            "privacy.delete_data",
            "활동 데이터",
        )
        assert _satisfies_semantic_terminal_concepts(
            catalog,
            "privacy.delete_data",
            "활동 기록 지우기",
        )


def assert_explicit_dead_end_uses_back_without_prior_path() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="initial-dead-end",
                goal_text="카메라 권한을 가진 앱을 확인하고 싶어",
                title="일시적인 연결 문제",
                elements=[element("wait", "계속 기다리기")],
            ),
            settings=settings,
            repository=repository,
        )
        assert response.phase == "exploring"
        assert response.automation.action == "back"
        assert response.automation.safe_to_execute is True


def assert_expired_session_prefers_reauthentication() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="expired-session",
                goal_text="Show my coupons",
                title="Session expired",
                elements=[
                    element("verify", "Open account verification"),
                    element("new-account", "Create a different account"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert response.phase == "exploring", response.model_dump()
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "Open account verification"
        assert response.automation.safe_to_execute is True

        password = element("password", "Password", role="input")
        password["password"] = True
        credential_form = observe_universal_navigation(
            custom_request(
                session_id="expired-session-credential-form",
                goal_text="Show my coupons",
                title="Session expired",
                elements=[
                    element("email", "Email address", role="input"),
                    password,
                    element("submit", "Sign in again"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert credential_form.phase == "stopped", credential_form.model_dump()
        assert credential_form.automation.action == "none"
        assert credential_form.failure_reason == "relogin_required"


def assert_automatic_click_requires_candidate_and_action_to_be_low_risk() -> None:
    class ActionRiskOverrideRepository(UniversalNavigationGraphRepository):
        def observe(self, request, candidates):
            observation = super().observe(request, candidates)
            actions = dict(observation.actions_by_element_id)
            for element_id, action in actions.items():
                if action.label == "Account":
                    actions[element_id] = replace(action, risk_level="medium")
            return replace(observation, actions_by_element_id=actions)

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        repository = ActionRiskOverrideRepository(root / "graph.sqlite")
        settings = Settings(
            navigation_agent_provider="mock",
            android_control_index_path="",
            navigation_function_db_path=str(root / "functions.sqlite"),
            navigation_exploration_timeout_seconds=55,
            navigation_exploration_max_actions=16,
            navigation_exploration_max_depth=9,
        )
        request_value = custom_request(
            session_id="dual-low-risk-boundary",
            goal_text="Open my account",
            title="Home",
            app_package="com.example.dynamic",
            elements=[
                element("account", "Account"),
                element("settings", "Settings"),
            ],
        )
        candidates = extract_navigation_candidates(request_value)
        observation = repository.observe(request_value, candidates)
        account_candidate = next(item for item in candidates if item.label == "Account")
        account_action = observation.actions_by_element_id[account_candidate.element_id]
        assert account_candidate.risk_level == "low"
        assert account_action.risk_level == "medium"
        assert not _automatic_click_is_low_risk(account_candidate, account_action)
        assert _automatic_click_is_low_risk(
            account_candidate,
            replace(account_action, risk_level="low"),
        )
        assert not _automatic_click_is_low_risk(
            account_candidate.model_copy(update={"risk_level": "medium"}),
            replace(account_action, risk_level="low"),
        )

        response = observe_universal_navigation(
            request_value,
            settings=settings,
            repository=repository,
        )
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "Settings", response.model_dump()
        assert response.recommendation is not None
        assert response.recommendation.risk_level == "low"


def assert_delete_all_variants_are_destructive_final_actions() -> None:
    for label in ("전체삭제", "모두삭제", "일괄삭제", "Delete all"):
        assert _looks_like_final_state_change_action(label), label


def assert_destructive_goal_does_not_stop_on_home_screen_unnamed_icons() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="baemin-delete-home-unnamed-icons",
                goal_text="Delete my Baemin account",
                title="Baemin Home",
                app_package="com.sampleapp",
                elements=[
                    element("my-baemin", "My Baemin", role="tab"),
                    element("food-more", "See more food delivery"),
                    {
                        "id": "unnamed-toolbar-icon",
                        "role": "image",
                        "clickable": True,
                        "enabled": True,
                        "visible": True,
                        "bounds": [920, 80, 1040, 200],
                    },
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert response.failure_reason != "user_boundary_required", response.model_dump()
        assert response.phase == "exploring", response.model_dump()
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "My Baemin", response.model_dump()

        profile_gateway = observe_universal_navigation(
            custom_request(
                session_id="baemin-delete-home-unnamed-icons",
                goal_text="Delete my Baemin account",
                title="My Baemin",
                app_package="com.sampleapp",
                transition=performed_transition(response),
                elements=[
                    {
                        "id": "screen-root",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [0, 0, 1440, 3120],
                    },
                    {
                        **element("nickname-ocr", "CandleMaster"),
                        "view_id": "exitguide:ocr",
                        "bounds": [445, 855, 996, 918],
                    },
                    {
                        **element("decorate", "Decorate"),
                        "bounds": [1206, 803, 1384, 971],
                    },
                    element("membership", "Baemin Club active"),
                    element("food-more", "See more food delivery"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert profile_gateway.phase == "exploring", profile_gateway.model_dump()
        assert profile_gateway.automation.action == "click", profile_gateway.model_dump()
        assert profile_gateway.automation.selected_label == "CandleMaster", profile_gateway.model_dump()

        loading_profile = observe_universal_navigation(
            custom_request(
                session_id="baemin-delete-home-unnamed-icons",
                goal_text="Delete my Baemin account",
                title="U 7:34",
                app_package="com.sampleapp",
                transition=performed_transition(profile_gateway),
                elements=[
                    {
                        "id": "loading-webview",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [0, 0, 1440, 3120],
                    },
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert loading_profile.phase == "exploring", loading_profile.model_dump()
        assert loading_profile.automation.action == "none", loading_profile.model_dump()
        assert loading_profile.automation.selected_label == "프로필 정보 불러오는 중", loading_profile.model_dump()

        loaded_profile = observe_universal_navigation(
            custom_request(
                session_id="baemin-delete-home-unnamed-icons",
                goal_text="Delete my Baemin account",
                title="뒤로 가기",
                app_package="com.sampleapp",
                elements=[
                    {
                        "id": "profile-webview",
                        "role": "list",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "scrollable": True,
                        "bounds": [0, 127, 1440, 2952],
                    },
                    {
                        "id": "profile-heading",
                        "text": "내 정보 수정",
                        "role": "heading",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [0, 158, 1440, 249],
                    },
                    element("nickname-row", "닉네임, CandleMaster"),
                    element("refund-row", "환불 관리"),
                    {
                        **element("withdrawal-clipped", "회원탈퇴 페이지로 이동하기"),
                        "bounds": [721, 2941, 962, 2952],
                    },
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert loaded_profile.phase == "exploring", loaded_profile.model_dump()
        assert loaded_profile.automation.action == "scroll_forward", loaded_profile.model_dump()

        already_open = observe_universal_navigation(
            custom_request(
                session_id="baemin-delete-already-on-my-page",
                goal_text="배민 회원탈퇴",
                title="배민의 음식주문 경험, 어떠셨나요?",
                app_package="com.sampleapp",
                elements=[
                    {
                        "id": "screen-root",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [0, 0, 1440, 3120],
                    },
                    {
                        "id": "my-baemin-heading",
                        "text": "마이배민",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [60, 180, 360, 280],
                    },
                    {
                        **element("nickname-ocr", "CandleMaster"),
                        "view_id": "exitguide:ocr",
                        "bounds": [445, 855, 996, 918],
                    },
                    {
                        **element("my-baemin-tab", "마이배민"),
                        "bounds": [1200, 2760, 1400, 2940],
                    },
                    {
                        **element("settings", "환경설정"),
                        "bounds": [1265, 141, 1433, 309],
                    },
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert already_open.phase == "exploring", already_open.model_dump()
        assert already_open.automation.action == "click", already_open.model_dump()
        assert already_open.automation.selected_label == "CandleMaster", already_open.model_dump()

        already_open_loading = observe_universal_navigation(
            custom_request(
                session_id="baemin-delete-already-on-my-page",
                goal_text="배민 회원탈퇴",
                title="U 7:34",
                app_package="com.sampleapp",
                transition=performed_transition(already_open),
                elements=[
                    {
                        "id": "loading-profile-webview",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [0, 0, 1440, 3120],
                    },
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert already_open_loading.phase == "exploring", already_open_loading.model_dump()
        assert already_open_loading.automation.action == "none", already_open_loading.model_dump()
        assert already_open_loading.automation.selected_label == "프로필 정보 불러오는 중", already_open_loading.model_dump()


def assert_safe_exploration_returns_then_switches_to_manual_route() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        screens = scenario_screens()
        previous = None
        forward_responses = []
        for index in range(4):
            transition = None if previous is None else performed_transition(previous)
            response = observe_universal_navigation(
                request(index, index, screens, transition=transition),
                settings=settings,
                repository=repository,
            )
            forward_responses.append(response)
            previous = response

        assert [response.automation.selected_label for response in forward_responses[:3]] == [
            "My page",
            "Payments and subscriptions",
            "Premium membership",
        ]
        for response in forward_responses[:3]:
            assert response.phase == "exploring"
            assert response.automation.action == "click"
            assert response.automation.safe_to_execute is True
            assert response.recommendation is not None
            assert response.recommendation.risk_level == "low"

        destination = forward_responses[3]
        assert destination.phase == "destination_reached"
        assert destination.status == "goal_completed"
        assert destination.automation.action == "stop"
        assert destination.discovered_route is not None
        assert destination.discovered_route.lifecycle_status == "shadow"
        assert destination.discovered_route.provisional is True
        assert len(destination.discovered_route.steps) == 4
        assert destination.discovered_route.steps[-1].label == "Cancel subscription"
        assert destination.discovered_route.steps[-1].terminal is True
        assert destination.recommendation is not None
        assert destination.recommendation.selected_label == "Cancel subscription"
        assert destination.recommendation.requires_user_confirmation is True

        # Runtime discovery and trusted validation are deliberately
        # shadow-only. The test performs a separate explicit lifecycle review
        # before route_cache may serve it.
        approve_discovered_route(
            repository,
            destination.discovered_route.route_id,
            existing_session_id="exploration-session",
        )

        original_android_control_lookup = agent_module._android_control_demonstrations
        agent_module._android_control_demonstrations = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("approved app/function route must bypass AndroidControl")
        )
        try:
            automatic_reuse = observe_universal_navigation(
                request(19, 0, screens, session_id="approved-auto-route-session"),
                settings=settings,
                repository=repository,
            )
        finally:
            agent_module._android_control_demonstrations = original_android_control_lookup
        assert automatic_reuse.phase == "exploring"
        assert automatic_reuse.decision_mode == "route_cache"
        assert automatic_reuse.automation.action == "click"
        assert automatic_reuse.automation.selected_label == "My page"

        reused = observe_universal_navigation(
            request(20, 0, screens, mode="guide", session_id="manual-route-session"),
            settings=settings,
            repository=repository,
        )
        assert reused.phase == "guiding"
        assert reused.decision_mode == "route_cache"
        assert reused.automation.action == "none"
        assert reused.recommendation is not None
        assert reused.recommendation.selected_label == "My page"

        cached_destination = observe_universal_navigation(
            request(21, 3, screens, mode="guide", session_id="manual-route-destination"),
            settings=settings,
            repository=repository,
        )
        assert cached_destination.phase == "destination_reached"
        assert cached_destination.automation.action == "stop"
        assert cached_destination.automation.safe_to_execute is False
        assert cached_destination.recommendation is not None
        assert cached_destination.recommendation.selected_label == "Cancel subscription"
        assert cached_destination.recommendation.requires_user_confirmation is True

        updated_payload = request(
            22,
            0,
            screens,
            session_id="updated-resource-id-session",
        ).model_dump()
        for item in updated_payload["screen"]["elements"]:
            if item.get("view_id"):
                item["view_id"] = str(item["view_id"]).replace(":id/", ":id/v2_")
        updated = observe_universal_navigation(
            UniversalNavigationObserveRequest.model_validate(updated_payload),
            settings=settings,
            repository=repository,
        )
        assert updated.phase == "exploring"
        assert updated.decision_mode == "function_graph_exploration"
        assert updated.automation.action == "click"
        assert updated.automation.selected_label == "My page"
        assert any("현재 UI와 달라" in warning for warning in updated.warnings)

        connection = sqlite3.connect(repository.database_path)
        try:
            route_count = connection.execute("SELECT COUNT(*) FROM universal_routes").fetchone()[0]
            click_attempts = connection.execute(
                "SELECT COUNT(*) FROM universal_exploration_attempts WHERE command = 'click'"
            ).fetchone()[0]
            stale_routes = connection.execute(
                "SELECT COUNT(*) FROM universal_routes WHERE status = 'stale'"
            ).fetchone()[0]
        finally:
            connection.close()
        assert route_count == 1
        assert click_attempts == 4
        assert stale_routes == 1

        deviated = observe_universal_navigation(
            request(
                13,
                0,
                [("Unexpected screen", [element("settings-new", "Settings")])],
            ),
            settings=settings,
            repository=repository,
        )
        assert deviated.phase == "exploring"
        assert deviated.automation.action in {"click", "scroll_forward"}


def assert_running_exploration_joins_verified_route_at_destination() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        screens = scenario_screens()
        previous = None
        destination = None
        for index in range(4):
            transition = None if previous is None else performed_transition(previous)
            destination = observe_universal_navigation(
                request(index, index, screens, transition=transition),
                settings=settings,
                repository=repository,
            )
            previous = destination

        assert destination is not None
        assert destination.discovered_route is not None
        route_id = destination.discovered_route.route_id
        repository.performance.apply_validation(
            session_id="exploration-session",
            destination_correct=True,
            safe_stop=True,
            verification_level="benchmark_gold",
        )
        verified = repository.verify_route_candidate(route_id)
        assert verified.lifecycle_status == "verified_candidate"

        volatile_home_payload = request(
            39,
            0,
            screens,
            session_id="volatile-home-route-session",
        ).model_dump()
        volatile_home_payload["screen"]["elements"].extend(
            {
                "id": f"dynamic-feed-{index}",
                "text": f"Limited-time promotion {index}",
                "role": "text",
                "clickable": False,
                "enabled": True,
                "visible": True,
            }
            for index in range(24)
        )
        volatile_home = observe_universal_navigation(
            UniversalNavigationObserveRequest.model_validate(volatile_home_payload),
            settings=settings,
            repository=repository,
        )
        assert volatile_home.decision_mode == "route_cache", volatile_home.model_dump()
        assert volatile_home.automation.action == "click", volatile_home.model_dump()
        assert volatile_home.automation.selected_label == "My page"

        skip_home = observe_universal_navigation(
            request(
                42,
                0,
                screens,
                session_id="route-skip-to-destination-session",
            ),
            settings=settings,
            repository=repository,
        )
        assert skip_home.decision_mode == "route_cache", skip_home.model_dump()
        skipped_to_destination = observe_universal_navigation(
            request(
                43,
                3,
                screens,
                transition=performed_transition(skip_home),
                session_id="route-skip-to-destination-session",
            ),
            settings=settings,
            repository=repository,
        )
        assert skipped_to_destination.decision_mode == "route_cache", skipped_to_destination.model_dump()
        assert skipped_to_destination.phase == "destination_reached", skipped_to_destination.model_dump()
        assert skipped_to_destination.automation.action == "stop"

        repository.start_exploration(
            exploration_id="opportunistic-route-session",
            app_package="com.example.dynamic",
            app_version="1.0.0",
            locale="en-US",
            goal_text="cancel subscription",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="unrelated-volatile-home",
            max_actions=16,
            max_depth=9,
            timeout_seconds=55,
        )
        joined = observe_universal_navigation(
            request(
                44,
                3,
                screens,
                session_id="opportunistic-route-session",
            ),
            settings=settings,
            repository=repository,
        )
        assert joined.decision_mode == "route_cache", joined.model_dump()
        assert joined.phase == "destination_reached", joined.model_dump()
        assert joined.automation.action == "stop", joined.model_dump()
        assert joined.recommendation is not None
        assert joined.recommendation.selected_label == "Cancel subscription"

        # Exercise invalidation last because it deliberately removes the
        # shared verified candidate used by the independent reuse checks
        # above.
        volatile_account_payload = request(
            40,
            1,
            screens,
            transition=performed_transition(volatile_home),
            session_id="volatile-home-route-session",
        ).model_dump()
        volatile_account_payload["screen"]["elements"].extend(
            {
                "id": f"dynamic-account-card-{index}",
                "text": f"Recent account activity {index}",
                "role": "text",
                "clickable": False,
                "enabled": True,
                "visible": True,
            }
            for index in range(24)
        )
        volatile_account = observe_universal_navigation(
            UniversalNavigationObserveRequest.model_validate(volatile_account_payload),
            settings=settings,
            repository=repository,
        )
        # A material change after the entry click may retain an old element
        # key, but must invalidate the cached intermediate stage and fall back
        # in-session instead of blindly rejoining it.
        assert (
            volatile_account.decision_mode == "function_graph_exploration"
        ), volatile_account.model_dump()
        assert volatile_account.automation.action == "click", volatile_account.model_dump()
        assert volatile_account.automation.selected_label == "Payments and subscriptions"
        stale_route = repository.route(route_id)
        assert stale_route is not None
        assert stale_route.lifecycle_status == "stale"


def assert_terminal_and_state_changing_controls_are_never_auto_clicked() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        screens = [
            (
                "Plan details",
                [
                    element("cancel", "Cancel subscription"),
                    element("delete", "Delete account"),
                    element("renew", "Auto renewal", role="switch", checkable=True),
                ],
            )
        ]
        response = observe_universal_navigation(
            request(1, 0, screens, session_id="terminal-safety"),
            settings=settings,
            repository=repository,
        )
        assert response.phase == "destination_reached"
        assert response.automation.action == "stop"
        assert response.automation.safe_to_execute is False
        assert response.recommendation is not None
        assert response.recommendation.selected_label == "Cancel subscription"
        assert response.recommendation.requires_user_confirmation is True
        connection = sqlite3.connect(repository.database_path)
        try:
            automated = connection.execute(
                "SELECT COUNT(*) FROM universal_exploration_attempts WHERE command = 'click'"
            ).fetchone()[0]
        finally:
            connection.close()
        assert automated == 0


def assert_catalog_never_auto_targets_are_user_owned_boundaries() -> None:
    scenarios = (
        ("보험금을 청구하고 싶어", "보험금 청구", "보험계약 조회", None),
        ("보험계약대출 메뉴를 찾고 싶어", "보험계약대출", "보험계약 조회", None),
        (
            "Begin spoken turn-by-turn guidance to the airport",
            "Start",
            "Alternate route",
            {
                "from_screen_fingerprint": "us_0000000000000000",
                "performed_element_id": "directions",
                "outcome": "navigated",
            },
        ),
    )
    for index, (goal, target, decoy, transition) in enumerate(scenarios):
        with TemporaryDirectory() as temporary_directory:
            repository, settings = environment(temporary_directory)
            response = observe_universal_navigation(
                custom_request(
                    session_id=f"never-auto-boundary-{index}",
                    goal_text=goal,
                    title="Route preview" if transition else "Review",
                    elements=[element("target", target), element("decoy", decoy)],
                    app_package="com.example.firstseen",
                    transition=transition,
                ),
                settings=settings,
                repository=repository,
            )
            assert response.phase == "destination_reached", response.model_dump()
            assert response.automation.action == "stop", response.model_dump()
            assert response.automation.safe_to_execute is False
            assert response.automation.selected_label == target, response.model_dump()


def assert_sensitive_destination_rows_stop_before_opening() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="sensitive-location-history-boundary",
                goal_text="Take me to the place where Maps keeps my visited-location timeline",
                title="Profile menu",
                elements=[
                    element("timeline", "Timeline"),
                    element("sharing", "Location sharing"),
                    element("offline", "Offline maps"),
                ],
                app_package="com.google.android.apps.maps",
                transition={
                    "from_screen_fingerprint": "us_0000000000000000",
                    "performed_element_id": "profile",
                    "outcome": "navigated",
                },
            ),
            settings=settings,
            repository=repository,
        )
        assert response.phase == "destination_reached", response.model_dump()
        assert response.automation.action == "stop", response.model_dump()
        assert response.automation.safe_to_execute is False
        assert response.automation.selected_label == "Timeline", response.model_dump()


def assert_product_name_overlap_cannot_fake_a_terminal_destination() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="named-product-is-not-autoplay",
                goal_text="Turn off autoplay in YouTube",
                title="Account",
                elements=[
                    element("settings", "Settings"),
                    element("premium", "YouTube Premium"),
                    element("help", "Help and feedback"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert response.phase == "exploring", response.model_dump()
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "Settings", response.model_dump()


def assert_exploration_budget_stops_additional_automation() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory, max_actions=1)
        screens = scenario_screens()
        first = observe_universal_navigation(
            request(1, 0, screens, session_id="budget-session"),
            settings=settings,
            repository=repository,
        )
        assert first.automation.action == "click"
        second = observe_universal_navigation(
            request(
                2,
                1,
                screens,
                transition=performed_transition(first),
                session_id="budget-session",
            ),
            settings=settings,
            repository=repository,
        )
        assert second.phase == "stopped"
        assert second.automation.action == "stop"
        assert second.automation.safe_to_execute is False


def assert_youtube_premium_controls_are_recognized() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        elements = [
            {
                "id": "cancel-row",
                "role": "button",
                "clickable": True,
                "enabled": True,
                "visible": True,
                "bounds": [0, 400, 1080, 520],
            },
            {
                "id": "cancel-label",
                "parent_id": "cancel-row",
                "text": "취소",
                "role": "text",
                "clickable": False,
                "enabled": True,
                "visible": True,
            },
            {
                "id": "manage-row",
                "role": "button",
                "clickable": True,
                "enabled": True,
                "visible": True,
                "bounds": [0, 700, 1080, 840],
            },
            {
                "id": "manage-label",
                "parent_id": "manage-row",
                "text": "Google Play에서 관리",
                "role": "text",
                "clickable": False,
                "enabled": True,
                "visible": True,
            },
        ]
        cancellation = observe_universal_navigation(
            custom_request(
                session_id="youtube-cancel",
                goal_text="유튜브 프리미엄 구독을 해지하고 싶어",
                title="YouTube Premium 개인 멤버십 다음 결제일 8월 3일",
                elements=elements,
            ),
            settings=settings,
            repository=repository,
        )
        assert cancellation.phase == "destination_reached"
        assert cancellation.automation.action == "stop"
        assert cancellation.recommendation is not None
        assert cancellation.recommendation.selected_label == "취소"

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        management = observe_universal_navigation(
            custom_request(
                session_id="youtube-manage",
                goal_text="유튜브 프리미엄 구독 관리",
                title="YouTube Premium 개인 멤버십 다음 결제일 8월 3일",
                elements=elements,
            ),
            settings=settings,
            repository=repository,
        )
        assert management.phase == "destination_reached"
        assert management.automation.action == "stop"
        assert management.recommendation is not None
        assert management.recommendation.selected_label == "Google Play에서 관리"


def assert_youtube_membership_list_opens_active_plan_instead_of_claiming_destination() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="youtube-active-membership-list",
                goal_text="유튜브 프리미엄 구독 해지",
                title="구매 항목 및 멤버십",
                elements=[
                    {
                        "id": "membership-heading",
                        "text": "멤버십 및 채널",
                        "role": "heading",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                        "bounds": [40, 480, 500, 580],
                    },
                    element(
                        "premium-card",
                        "YouTube Premium 개인 멤버십 월 ₩14,900 갱신일 8월 3일",
                    ),
                ],
            ),
            settings=settings,
            repository=repository,
        )

        assert response.phase == "exploring", response.model_dump()
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label.startswith("YouTube Premium"), response.model_dump()

        # Reproduce the real-device state after My page -> Settings ->
        # Purchases and memberships.  Persistent bottom navigation remains
        # clickable, but it must not beat the active paid-plan card and create
        # a loop back to My page.
        arrived_request = custom_request(
            session_id="youtube-active-membership-arrived",
            goal_text="유튜브 프리미엄 구독 해지",
            title="구매 항목 및 멤버십",
            elements=[
                element(
                    "premium-card-arrived",
                    "YouTube Premium 개인 멤버십 월 ₩14,900 갱신일 8월 3일",
                ),
                element("my-page-persistent", "내 페이지", role="tab"),
            ],
        )
        arrived_candidates = extract_navigation_candidates(arrived_request)
        arrived_observation = repository.observe(arrived_request, arrived_candidates)
        repository.start_exploration(
            exploration_id=arrived_request.session_id,
            app_package=arrived_request.app_package,
            app_version=arrived_request.app_version,
            locale=arrived_request.locale,
            goal_text=arrived_request.goal_text,
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="youtube-settings-screen",
            max_actions=16,
            max_depth=9,
            timeout_seconds=55,
        )
        repository.update_exploration(
            arrived_request.session_id,
            current_screen_fingerprint=arrived_observation.screen_fingerprint,
            path=[
                {
                    "ordinal": 0,
                    "label": "구매 항목 및 멤버십",
                    "function_ids": ["subscription.manage", "subscription.list"],
                    "from_screen_fingerprint": "youtube-settings-screen",
                    "expected_to_screen_fingerprint": arrived_observation.screen_fingerprint,
                    "pending": False,
                }
            ],
        )
        arrived = observe_universal_navigation(
            arrived_request,
            settings=settings,
            repository=repository,
        )
        assert arrived.phase == "exploring", arrived.model_dump()
        assert arrived.automation.action == "click", arrived.model_dump()
        assert arrived.automation.selected_label.startswith("YouTube Premium"), arrived.model_dump()


def assert_youtube_loading_detail_is_reobserved_then_stops_at_late_cancel_control() -> None:
    """A blank first detail snapshot must not abandon a correct Premium branch."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "youtube-loading-premium-detail"
        loading_request = _seed_youtube_loading_detail(repository, settings, session_id)
        loading_detail = observe_universal_navigation(
            loading_request,
            settings=settings,
            repository=repository,
        )
        assert loading_detail.phase == "exploring", loading_detail.model_dump()
        assert loading_detail.automation.action == "none", loading_detail.model_dump()
        assert loading_detail.automation.safe_to_execute is True

        # Simulate content becoming accessible just after the nominal 55 s
        # exploration deadline. It may be reported, but never auto-clicked.
        expired_started_at = (
            datetime.now(timezone.utc) - timedelta(seconds=60)
        ).isoformat(timespec="seconds")
        connection = sqlite3.connect(repository.database_path)
        try:
            connection.execute(
                "UPDATE universal_explorations SET started_at = ? WHERE exploration_id = ?",
                (expired_started_at, session_id),
            )
            connection.commit()
        finally:
            connection.close()

        settled_detail = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="유튜브 프리미엄 구독을 해지하고 싶어",
                title="YouTube Premium 개인 멤버십",
                elements=[
                    {
                        "id": "renewal-date",
                        "text": "다음 결제일 8월 3일",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                    },
                    element("manage", "Google Play에서 관리"),
                    element("cancel", "취소"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert settled_detail.phase == "destination_reached", settled_detail.model_dump()
        assert settled_detail.automation.action == "stop"
        assert settled_detail.automation.safe_to_execute is False
        assert settled_detail.recommendation is not None
        assert settled_detail.recommendation.selected_label == "취소"

        connection = sqlite3.connect(repository.database_path)
        try:
            wait_count = connection.execute(
                "SELECT COUNT(*) FROM universal_exploration_attempts "
                "WHERE exploration_id = ? AND command = 'wait'",
                (session_id,),
            ).fetchone()[0]
            final_click_count = connection.execute(
                "SELECT COUNT(*) FROM universal_exploration_attempts "
                "WHERE exploration_id = ? AND command = 'click' AND label = '취소'",
                (session_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert wait_count == 1
        assert final_click_count == 0

        # The no-op is bounded even if the web-backed detail remains blank.
        second_session_id = "youtube-loading-premium-detail-one-shot"
        second_loading_request = _seed_youtube_loading_detail(
            repository,
            settings,
            second_session_id,
        )
        first_blank = observe_universal_navigation(
            second_loading_request,
            settings=settings,
            repository=repository,
        )
        assert first_blank.automation.action == "none", first_blank.model_dump()
        second_loading_payload = second_loading_request.model_dump()
        second_loading_payload["request_id"] = "request-youtube-loading-premium-detail-one-shot-repeat"
        second_loading_payload["transition"] = None
        second_blank = observe_universal_navigation(
            UniversalNavigationObserveRequest.model_validate(second_loading_payload),
            settings=settings,
            repository=repository,
        )
        assert second_blank.automation.action != "none", second_blank.model_dump()
        connection = sqlite3.connect(repository.database_path)
        try:
            second_wait_count = connection.execute(
                "SELECT COUNT(*) FROM universal_exploration_attempts "
                "WHERE exploration_id = ? AND command = 'wait'",
                (second_session_id,),
            ).fetchone()[0]
        finally:
            connection.close()
        assert second_wait_count == 1


def _seed_youtube_loading_detail(
    repository: UniversalNavigationGraphRepository,
    settings: Settings,
    session_id: str,
) -> UniversalNavigationObserveRequest:
    """Mirror the reconciled row-20 path without retesting catalog ranking."""

    request = custom_request(
        session_id=session_id,
        goal_text="유튜브 프리미엄 구독을 해지하고 싶어",
        title="위로 이동",
        elements=[
            element(f"search-{session_id}", "검색", role="image"),
            element(f"more-{session_id}", "옵션 더보기", role="image"),
            element(f"home-{session_id}", "홈", role="tab"),
            element(f"shorts-{session_id}", "Shorts", role="tab"),
            element(f"create-{session_id}", "만들기", role="tab"),
            element(f"subscriptions-{session_id}", "구독", role="tab"),
            element(f"you-{session_id}", "내 페이지", role="tab"),
        ],
    )
    observation = repository.observe(request, extract_navigation_candidates(request))
    repository.start_exploration(
        exploration_id=session_id,
        app_package=request.app_package,
        app_version=request.app_version,
        locale=request.locale,
        goal_text=request.goal_text,
        target_function="subscription.cancel.entry",
        start_screen_fingerprint="us_seed_youtube_home",
        max_actions=settings.navigation_exploration_max_actions,
        max_depth=settings.navigation_exploration_max_depth,
        timeout_seconds=settings.navigation_exploration_timeout_seconds,
    )
    premium_label = "YouTube Premium 개인 멤버십 #14,900"
    premium_key = "ue_seed_youtube_premium_membership"
    path = [
        {
            "ordinal": 0,
            "from_screen_fingerprint": "us_seed_youtube_settings",
            "element_key": "ue_seed_purchases_memberships",
            "label": "구매 항목 및 멤버십",
            "function_ids": [
                "billing.manage",
                "subscription.cancel.entry",
                "subscription.list",
                "subscription.manage",
            ],
            "expected_to_screen_fingerprint": "us_seed_youtube_membership_list",
            "terminal": False,
            "reversible": True,
            "confidence": 0.8788,
            "action_id": "ua_seed_purchases_memberships",
            "element_id": "purchases",
            "pending": False,
        },
        {
            "ordinal": 1,
            "from_screen_fingerprint": "us_seed_youtube_membership_list",
            "element_key": premium_key,
            "label": premium_label,
            "function_ids": ["navigation.menu"],
            "expected_to_screen_fingerprint": observation.screen_fingerprint,
            "terminal": False,
            "reversible": True,
            "confidence": 0.98,
            "action_id": "ua_seed_youtube_premium_membership",
            "element_id": "premium",
            "pending": False,
        },
    ]
    repository.update_exploration(
        session_id,
        current_screen_fingerprint=observation.screen_fingerprint,
        action_count=2,
        path=path,
        clear_pending=True,
    )
    repository.record_exploration_attempt(
        exploration_id=session_id,
        screen_fingerprint="us_seed_youtube_membership_list",
        action_id="ua_seed_youtube_premium_membership",
        element_key_value=premium_key,
        label=premium_label,
        function_ids=["navigation.menu"],
        command="click",
        outcome="navigated",
        to_screen_fingerprint=observation.screen_fingerprint,
    )
    return request


def assert_youtube_physical_detail_prefers_cancel_over_support_and_external_links() -> None:
    """Mirror settled physical session 4df6d5fe without raw UI payloads."""

    for irrelevant_label in (
        "YouTube 지원팀",
        "공유",
        "YouTube 고객센터",
        "서비스 이용약관",
    ):
        assert _looks_like_goal_irrelevant_auxiliary_link(
            irrelevant_label,
            goal_text="Cancel YouTube Premium subscription",
            target_function="subscription.cancel.entry",
        )
    assert not _looks_like_goal_irrelevant_auxiliary_link(
        "YouTube 지원팀",
        goal_text="YouTube 지원팀에 문의하고 싶어",
        target_function="support.help",
    )

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "youtube-physical-support-link-regression"
        loading_request = _seed_youtube_loading_detail(
            repository,
            settings,
            session_id,
        )
        waiting = observe_universal_navigation(
            loading_request,
            settings=settings,
            repository=repository,
        )
        assert waiting.automation.action == "none", waiting.model_dump()

        settled_request = custom_request(
            session_id=session_id,
            goal_text="Cancel YouTube Premium subscription",
            title="위로 이동",
            elements=[
                element("provider", "Google P이ay에서 관리 기"),
                element("support", "YouTube 지원팀"),
                element("plan", "개인 멤버십: \\14,900/월"),
                element("billing-date", "다음 결제일: 8월 3일"),
                element("cancel", "취소"),
                element("share", "공유"),
                element("help", "YouTube 고객센터"),
                element("terms", "서비스 이용약관"),
            ],
        )
        settled_candidates = extract_navigation_candidates(settled_request)
        cancel_candidate = next(
            candidate for candidate in settled_candidates if candidate.label == "취소"
        )
        assert cancel_candidate.risk_level == "medium"

        settled = observe_universal_navigation(
            settled_request,
            settings=settings,
            repository=repository,
        )
        assert settled.phase == "destination_reached", settled.model_dump()
        assert settled.automation.action == "stop"
        assert settled.automation.safe_to_execute is False
        assert settled.recommendation is not None
        assert settled.recommendation.selected_label == "취소"
        assert settled.recommendation.requires_user_confirmation is True

        connection = sqlite3.connect(repository.database_path)
        try:
            irrelevant_clicks = connection.execute(
                "SELECT COUNT(*) FROM universal_exploration_attempts "
                "WHERE exploration_id = ? AND command = 'click' "
                "AND label IN (?, ?, ?, ?)",
                (
                    session_id,
                    "YouTube 지원팀",
                    "공유",
                    "YouTube 고객센터",
                    "서비스 이용약관",
                ),
            ).fetchone()[0]
        finally:
            connection.close()
        assert irrelevant_clicks == 0

        # A short Cancel label is ambiguous outside a verified paid-plan
        # surface.  It must not become a subscription destination merely
        # because the user's goal contains the same generic action word.
        unrelated_cancel = observe_universal_navigation(
            custom_request(
                session_id="unrelated-short-cancel",
                goal_text="Cancel subscription",
                title="Edit profile picture",
                elements=[
                    element("save-profile", "Save"),
                    element("cancel-edit", "취소"),
                ],
                app_package="com.example.profile",
            ),
            settings=settings,
            repository=repository,
        )
        assert unrelated_cancel.phase != "destination_reached", unrelated_cancel.model_dump()
        assert (
            unrelated_cancel.recommendation is None
            or unrelated_cancel.recommendation.selected_label != "취소"
        )

        # A descriptive control remains valid without historical path state.
        descriptive_cancel = observe_universal_navigation(
            custom_request(
                session_id="descriptive-subscription-cancel",
                goal_text="Cancel subscription",
                title="Account",
                elements=[element("cancel-subscription", "Cancel subscription")],
                app_package="com.example.subscription",
            ),
            settings=settings,
            repository=repository,
        )
        assert descriptive_cancel.phase == "destination_reached", descriptive_cancel.model_dump()
        assert descriptive_cancel.automation.action == "stop"
        assert descriptive_cancel.automation.safe_to_execute is False
        assert descriptive_cancel.recommendation is not None
        assert descriptive_cancel.recommendation.selected_label == "Cancel subscription"

        # Fee/policy/media labels are not subscription-exit controls even on
        # a paid-plan detail surface.
        for index, unrelated_label in enumerate(
            (
                "취소 수수료 및 환불 규정",
                "Cancellation policy",
                "재생 종료",
            )
        ):
            negative_session_id = f"youtube-unrelated-cancel-{index}"
            negative_loading = _seed_youtube_loading_detail(
                repository,
                settings,
                negative_session_id,
            )
            negative_wait = observe_universal_navigation(
                negative_loading,
                settings=settings,
                repository=repository,
            )
            assert negative_wait.automation.action == "none", negative_wait.model_dump()
            negative = observe_universal_navigation(
                custom_request(
                    session_id=negative_session_id,
                    goal_text="Cancel YouTube Premium subscription",
                    title="YouTube Premium plan",
                    elements=[
                        element("unrelated-cancel", unrelated_label),
                        element("plan", "Premium membership 14,900/month"),
                        element("billing-date", "Next billing August 3"),
                    ],
                ),
                settings=settings,
                repository=repository,
            )
            assert negative.phase != "destination_reached", negative.model_dump()
            assert (
                negative.recommendation is None
                or negative.recommendation.selected_label != unrelated_label
            )

        # A combined support-only exit instruction is materially different
        # from a generic support link: stop at it for the user instead of
        # auto-opening a browser or abandoning the only cancellation route.
        support_only_session_id = "support-only-subscription-cancel"
        support_only_loading = _seed_youtube_loading_detail(
            repository,
            settings,
            support_only_session_id,
        )
        support_only_wait = observe_universal_navigation(
            support_only_loading,
            settings=settings,
            repository=repository,
        )
        assert support_only_wait.automation.action == "none", support_only_wait.model_dump()
        support_only_label = "Contact customer support to cancel subscription"
        support_only = observe_universal_navigation(
            custom_request(
                session_id=support_only_session_id,
                goal_text="Cancel subscription",
                title="Premium plan",
                elements=[
                    element("support-only", support_only_label),
                    element("plan", "Premium membership 14.99/month"),
                    element("billing-date", "Next billing August 3"),
                ],
                app_package="com.example.subscription",
            ),
            settings=settings,
            repository=repository,
        )
        assert support_only.phase == "destination_reached", support_only.model_dump()
        assert support_only.automation.action == "stop"
        assert support_only.automation.safe_to_execute is False
        assert support_only.recommendation is not None
        assert support_only.recommendation.selected_label == support_only_label

        # The reviewed provider handoff remains available when an app does not
        # expose an in-app cancel control.  OCR may split ``Play`` with one
        # stray character on a physical screen, but automation still stops
        # before leaving the app.
        provider_session_id = "youtube-physical-ocr-provider-handoff"
        provider_loading = _seed_youtube_loading_detail(
            repository,
            settings,
            provider_session_id,
        )
        provider_wait = observe_universal_navigation(
            provider_loading,
            settings=settings,
            repository=repository,
        )
        assert provider_wait.automation.action == "none", provider_wait.model_dump()
        provider = observe_universal_navigation(
            custom_request(
                session_id=provider_session_id,
                goal_text="Cancel YouTube Premium subscription",
                title="위로 이동",
                elements=[
                    element("provider", "Google P이ay에서 관리 기"),
                    element("support", "YouTube 지원팀"),
                    element("plan", "개인 멤버십: \\14,900/월"),
                    element("billing-date", "다음 결제일: 8월 3일"),
                    element("share", "공유"),
                    element("help", "YouTube 고객센터"),
                    element("terms", "서비스 이용약관"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert provider.phase == "destination_reached", provider.model_dump()
        assert provider.automation.action == "stop"
        assert provider.automation.safe_to_execute is False
        assert provider.recommendation is not None
        assert provider.recommendation.selected_label == "Google P이ay에서 관리 기"

        # ``Google Pay`` and payment-method management are not Play Store
        # subscription handoffs, despite sharing the ``P...ay`` characters.
        for index, payment_label in enumerate(
            ("Google Pay에서 관리", "Google Payment 관리")
        ):
            payment_session_id = f"youtube-google-payment-negative-{index}"
            payment_loading = _seed_youtube_loading_detail(
                repository,
                settings,
                payment_session_id,
            )
            payment_wait = observe_universal_navigation(
                payment_loading,
                settings=settings,
                repository=repository,
            )
            assert payment_wait.automation.action == "none", payment_wait.model_dump()
            payment = observe_universal_navigation(
                custom_request(
                    session_id=payment_session_id,
                    goal_text="Cancel YouTube Premium subscription",
                    title="YouTube Premium plan",
                    elements=[
                        element("payment-provider", payment_label),
                        element("plan", "Premium membership 14,900/month"),
                        element("billing-date", "Next billing August 3"),
                    ],
                ),
                settings=settings,
                repository=repository,
            )
            assert payment.phase != "destination_reached", payment.model_dump()
            assert (
                payment.recommendation is None
                or payment.recommendation.selected_label != payment_label
            )


def assert_youtube_sparse_purchase_page_backtracks_from_global_navigation() -> None:
    """Do not leave a reached subscription branch through YouTube bottom nav."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        first = observe_universal_navigation(
            custom_request(
                session_id="youtube-sparse-purchase",
                goal_text="cancel subscription",
                title="Settings",
                elements=[
                    element("purchases", "구매 항목 및 멤버십"),
                    element("privacy", "개인정보 보호"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert first.phase == "exploring"
        assert first.automation.action == "click"
        assert first.automation.selected_label == "구매 항목 및 멤버십", first.model_dump()

        sparse = observe_universal_navigation(
            custom_request(
                session_id="youtube-sparse-purchase",
                goal_text="cancel subscription",
                title="구매 항목 및 멤버십",
                elements=[
                    element("create", "+", role="tab"),
                    element("shorts", "Shorts", role="tab"),
                    element("status", "오전 10:38 구매 항목 및 멤버십", role="text"),
                    element("search", "검색", role="image"),
                    element("subscriptions", "구독", role="tab"),
                    element("you", "내 페이지", role="tab"),
                    element("more", "옵션 더보기", role="image"),
                    element("up", "위로 이동", role="image"),
                    element("home", "홈", role="tab"),
                ],
                transition=performed_transition(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert sparse.phase == "exploring", sparse.model_dump()
        assert sparse.automation.action == "back", sparse.model_dump()
        assert sparse.automation.selected_label != "내 페이지"


def assert_youtube_selected_playlist_is_not_a_cancellation_destination() -> None:
    """A selected content tab cannot borrow cancellation identity from context."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        first = observe_universal_navigation(
            custom_request(
                session_id="youtube-playlist-regression",
                goal_text="cancel subscription",
                title="Settings",
                elements=[element("purchases", "구매 항목 및 멤버십")],
            ),
            settings=settings,
            repository=repository,
        )
        assert first.phase == "exploring"
        assert first.automation.action == "click"

        playlist = element("playlist", "재생목록", role="tab")
        playlist["selected"] = True
        response = observe_universal_navigation(
            custom_request(
                session_id="youtube-playlist-regression",
                goal_text="cancel subscription",
                title="YouTube 내 페이지",
                elements=[
                    playlist,
                    element("home", "홈", role="tab"),
                    element("shorts", "Shorts", role="tab"),
                    element("subscriptions", "구독", role="tab"),
                    element("you", "내 페이지", role="tab"),
                ],
                transition=performed_transition(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert response.phase != "destination_reached", response.model_dump()
        assert response.status != "goal_completed"
        assert response.automation.selected_label != "재생목록"
        assert response.automation.action == "back", response.model_dump()


def assert_creator_audience_metrics_are_not_paid_subscription_progress() -> None:
    assert _looks_like_creator_audience_metric("구독자 98명 >")
    assert _looks_like_creator_audience_metric("98 subscribers")
    assert _looks_like_creator_audience_metric("1.2K followers")
    assert _looks_like_creator_audience_metric("Subscriber count")
    assert not _looks_like_creator_audience_metric("구독자 전용 멤버십 해지")
    assert not _looks_like_creator_audience_metric("Cancel subscriber-only membership")
    assert not _looks_like_creator_audience_metric("구독자 멤버십 관리")
    assert not _looks_like_creator_audience_metric("Manage subscriber-only membership")


def assert_youtube_paid_subscription_rejects_creator_content_detours() -> None:
    request_value = custom_request(
        session_id="youtube-paid-vs-channel-subscription",
        goal_text="유튜브 프리미엄 구독 해지",
        title="YouTube 홈",
        elements=[
            element(
                "video-card",
                "25:45 최대 고점의 트페 등장 괴물쥐 유튜브 조회수 74만회 11개월 전",
            ),
            element("subscriber-count", "괴물쥐 유튜브 구독자 121만명"),
            element("channel-subscription", "구독중"),
            element("my-page", "내 페이지", role="tab"),
        ],
    )
    for label in (
        "25:45 최대 고점의 트페 등장 괴물쥐 유튜브 조회수 74만회 11개월 전",
        "괴물쥐 유튜브 구독자 121만명",
        "구독중",
    ):
        assert _looks_like_paid_subscription_content_detour(
            label,
            request=request_value,
            target_function="subscription.cancel.entry",
        )

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            request_value,
            settings=settings,
            repository=repository,
        )
        assert response.phase == "exploring", response.model_dump()
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "내 페이지", response.model_dump()

    channel_request = custom_request(
        session_id="youtube-paid-channel-unsubscribe-terminal",
        goal_text="유튜브 프리미엄 구독 해지",
        title="괴물쥐 유튜브 채널",
        elements=[
            element("unsubscribe", "괴물쥐 유튜브을(를) 구독 취소합니다."),
            element("my-page", "내 페이지", role="tab"),
        ],
    )
    assert _looks_like_paid_subscription_content_detour(
        "괴물쥐 유튜브을(를) 구독 취소합니다.",
        request=channel_request,
        target_function="subscription.cancel.entry",
    )


def assert_youtube_notification_settings_rejects_watch_history_videos() -> None:
    request_value = custom_request(
        session_id="youtube-notification-vs-watch-history",
        goal_text="유튜브 알림 수신 설정 화면으로 이동",
        title="YouTube 내 페이지",
        elements=[
            element(
                "history-video",
                "23:01 케~넨 괴물쥐 유튜브 조회수 41만회 1일 전 동영상 재생",
            ),
            element("subscriber-count", "괴물쥐 유튜브 구독자 121만명"),
            element("settings", "설정", role="image"),
        ],
    )
    plan = infer_goal_plan(request_value.goal_text)
    assert plan.terminal_function == "notification.settings", plan
    for label in (
        "23:01 케~넨 괴물쥐 유튜브 조회수 41만회 1일 전 동영상 재생",
        "괴물쥐 유튜브 구독자 121만명",
    ):
        assert _looks_like_management_goal_media_detour(
            label,
            request=request_value,
            target_function=plan.terminal_function,
        )

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            request_value,
            settings=settings,
            repository=repository,
        )
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "설정", response.model_dump()


def assert_netflix_paid_subscription_prefers_account_over_catalog_content() -> None:
    request_value = custom_request(
        session_id="netflix-paid-vs-catalog",
        goal_text="넷플릭스 구독 해지",
        title="Netflix 홈",
        app_package="com.netflix.mediaclient",
        elements=[
            element("see-all", "모두 보기"),
            element("game-card", "페이퍼 퍼즐"),
            element("home", "홈", role="tab"),
            element("clips", "클립 영상", role="tab"),
            element("search", "검색", role="tab"),
            element("my-netflix", "나의 넷플릭스", role="tab"),
        ],
    )
    assert _looks_like_paid_subscription_content_detour(
        "모두 보기",
        request=request_value,
        target_function="subscription.cancel.entry",
    )
    assert _looks_like_paid_subscription_content_detour(
        "페이퍼 퍼즐",
        request=request_value,
        target_function="subscription.cancel.entry",
    )
    assert not _looks_like_paid_subscription_content_detour(
        "나의 넷플릭스",
        request=request_value,
        target_function="subscription.cancel.entry",
    )

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            request_value,
            settings=settings,
            repository=repository,
        )
        assert response.phase == "exploring", response.model_dump()
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "나의 넷플릭스", response.model_dump()

    # Match the physical Netflix tree: Compose reports an ordinary button,
    # inserts U+FEFF between Korean syllables, exposes a scrollable catalogue,
    # and includes several noisy content actions.  The account gateway must
    # still be chosen before the first scroll.
    physical_request = custom_request(
        session_id="netflix-physical-compose-account-tab",
        goal_text="넷플릭스 구독 해지",
        title="사이버펑크: 엣지러너",
        app_package="com.netflix.mediaclient",
        elements=[
            element("billboard", "사이버펑크: 엣지러너"),
            element("play", "플레이"),
            element("see-all", "모\ufeff두 보\ufeff기"),
            element("clips", "클\ufeff립 영\ufeff상", role="button"),
            element("search", "검\ufeff색", role="button"),
            {
                **element(
                    "my-netflix-compose",
                    "나\ufeff의 넷\ufeff플\ufeff릭\ufeff스",
                    role="button",
                ),
                # Samsung/Compose combinations have been observed reporting
                # the parent navigation container as selected even while the
                # visible Home item is active. The account-hub screen guard,
                # rather than this unreliable state bit, prevents repeats.
                "selected": True,
            },
            {
                **element("my-netflix-compose", "", role="text"),
                # Compose can duplicate the parent's stable ID on a later
                # decorative child. This item intentionally overwrites the
                # request-side lookup without invalidating the clickable
                # candidate/action that was already extracted from its parent.
                "clickable": False,
                "selected": False,
            },
            {
                "id": "catalog",
                "text": "신규 회원을 위한 추천 콘텐츠",
                "role": "list",
                "clickable": False,
                "scrollable": True,
                "enabled": True,
                "visible": True,
                "bounds": [0, 500, 1440, 2800],
            },
        ],
    )
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        physical = observe_universal_navigation(
            physical_request,
            settings=settings,
            repository=repository,
        )
        assert physical.phase == "exploring", physical.model_dump()
        assert physical.automation.action == "click", physical.model_dump()
        assert physical.automation.selected_label == (
            "나\ufeff의 넷\ufeff플\ufeff릭\ufeff스"
        ), physical.model_dump()

    my_netflix_request = custom_request(
        session_id="netflix-physical-profile-gateway",
        goal_text="넷플릭스 구독 해지",
        title="나의 넷플릭스",
        app_package="com.netflix.mediaclient",
        elements=[
            element(
                "profile-gateway",
                "프\ufeff로\ufeff필\ufeff을 변\ufeff경 또\ufeff는 관\ufeff리\ufeff하\ufeff세\ufeff요.",
            ),
            {
                **element("profile-gateway", "", role="text"),
                "clickable": False,
            },
            element("saved-content", "저장한 콘텐츠 목록"),
            element("my-list", "내가 찜한 리스트"),
            {
                "id": "catalog",
                "text": "시청하신 예고편",
                "role": "list",
                "clickable": False,
                "scrollable": True,
                "enabled": True,
                "visible": True,
                "bounds": [0, 500, 1440, 2800],
            },
        ],
    )
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        profile_gateway = observe_universal_navigation(
            my_netflix_request,
            settings=settings,
            repository=repository,
        )
        assert profile_gateway.phase == "exploring", profile_gateway.model_dump()
        assert profile_gateway.automation.action == "click", profile_gateway.model_dump()
        assert profile_gateway.automation.selected_label.startswith(
            "프\ufeff로\ufeff필"
        ), profile_gateway.model_dump()

        account_menu = observe_universal_navigation(
            custom_request(
                session_id=my_netflix_request.session_id,
                goal_text="넷플릭스 구독 해지",
                title="프로필 메뉴",
                app_package="com.netflix.mediaclient",
                transition=performed_transition(profile_gateway),
                elements=[
                    element("profile-management", "프로필 관리"),
                    element("app-settings", "앱 설정"),
                    element("account-settings", "계정"),
                    element("help-center", "고객 센터"),
                    element("logout", "로그아웃"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert account_menu.phase == "exploring", account_menu.model_dump()
        assert account_menu.automation.action == "click", account_menu.model_dump()
        assert account_menu.automation.selected_label == "계정", account_menu.model_dump()

        # Netflix opens the account page in an internal WebView.  Its first
        # accessibility snapshot can contain only the toolbar while the HTML
        # content is still mounting.  Wait once instead of abandoning the
        # correct branch and pressing Back.
        loading_account = observe_universal_navigation(
            custom_request(
                session_id=my_netflix_request.session_id,
                goal_text="넷플릭스 구독 해지",
                title="위로 이동",
                app_package="com.netflix.mediaclient",
                transition=performed_transition(account_menu),
                elements=[
                    {
                        **element("account-webview", "계정", role="webview"),
                        "clickable": False,
                    },
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert loading_account.phase == "exploring", loading_account.model_dump()
        assert loading_account.automation.action == "none", loading_account.model_dump()
        assert loading_account.automation.selected_label == (
            "구독 상세 불러오는 중"
        ), loading_account.model_dump()

        loaded_account = observe_universal_navigation(
            custom_request(
                session_id=my_netflix_request.session_id,
                goal_text="넷플릭스 구독 해지",
                title="계정",
                app_package="com.netflix.mediaclient",
                elements=[
                    element("cancel-membership", "멤버십 해지"),
                    element("delete-account", "계정 삭제"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert loaded_account.phase == "destination_reached", loaded_account.model_dump()
        assert loaded_account.automation.action == "stop", loaded_account.model_dump()
        assert loaded_account.automation.selected_label == "멤버십 해지", loaded_account.model_dump()

    # The production Netflix bottom navigation is custom drawn and may expose
    # no label to either Accessibility or OCR.  The rightmost bottom control
    # must still beat scrolling through an effectively unbounded catalog.
    structural_request = custom_request(
        session_id="netflix-unlabeled-account-tab",
        goal_text="넷플릭스 구독 해지",
        title="Netflix 홈",
        app_package="com.netflix.mediaclient",
        elements=[
            {
                "id": "catalog",
                "text": "신규 회원을 위한 추천 콘텐츠",
                "role": "list",
                "clickable": False,
                "scrollable": True,
                "enabled": True,
                "visible": True,
                "bounds": [0, 260, 1440, 2700],
            },
            *[
                {
                    "id": f"bottom-tab-{index}",
                    "text": "",
                    "content_description": "",
                    "view_id": "",
                    "role": "button",
                    "clickable": True,
                    "enabled": True,
                    "visible": True,
                    "bounds": [left, 2760, right, 3050],
                }
                for index, (left, right) in enumerate(
                    ((20, 320), (360, 660), (700, 1000), (1040, 1400))
                )
            ],
        ],
    )
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        structural = observe_universal_navigation(
            structural_request,
            settings=settings,
            repository=repository,
        )
        assert structural.phase == "exploring", structural.model_dump()
        assert structural.automation.action == "click", structural.model_dump()
        assert structural.automation.selected_label == "이름 없는 하단 오른쪽 아이콘", (
            structural.model_dump()
        )


def assert_backtracked_branch_is_not_reselected_after_ocr_fingerprint_change() -> None:
    """A failed stable element cannot loop when only OCR changes the screen."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        first_request = custom_request(
            session_id="youtube-subscriber-backtrack",
            goal_text="cancel subscription",
            title="YouTube channel 10:38",
            elements=[
                element("subscriber-count", "구독자 98명 >"),
                element("purchases", "구매 항목 및 멤버십"),
            ],
        )
        returned_request = custom_request(
            session_id="youtube-subscriber-backtrack",
            goal_text="cancel subscription",
            title="YouTube channel 10:39",
            elements=[
                element("subscriber-count", "구독자 98명 >"),
                element("purchases", "구매 항목 및 멤버십"),
            ],
        )
        first_candidates = extract_navigation_candidates(first_request)
        returned_candidates = extract_navigation_candidates(returned_request)
        first_subscriber = next(
            candidate for candidate in first_candidates if candidate.label == "구독자 98명 >"
        )
        returned_subscriber = next(
            candidate for candidate in returned_candidates if candidate.label == "구독자 98명 >"
        )
        assert first_subscriber.element_key == returned_subscriber.element_key
        first_observation = repository.observe(first_request, first_candidates)

        repository.start_exploration(
            exploration_id=first_request.session_id,
            app_package=first_request.app_package,
            app_version=first_request.app_version,
            locale=first_request.locale,
            goal_text=first_request.goal_text,
            target_function="subscription.cancel.entry",
            start_screen_fingerprint=first_observation.screen_fingerprint,
            max_actions=16,
            max_depth=9,
            timeout_seconds=55,
        )
        repository.record_exploration_attempt(
            exploration_id=first_request.session_id,
            screen_fingerprint=first_observation.screen_fingerprint,
            action_id="legacy-subscriber-click",
            element_key_value=first_subscriber.element_key,
            label=first_subscriber.label,
            function_ids=("account.entry",),
            command="click",
            outcome="navigated",
            to_screen_fingerprint="us_subscriber_detail",
        )
        repository.record_exploration_attempt(
            exploration_id=first_request.session_id,
            screen_fingerprint=first_observation.screen_fingerprint,
            action_id="backtrack:1:legacy-subscriber-click",
            element_key_value=first_subscriber.element_key,
            label=first_subscriber.label,
            function_ids=("account.entry",),
            command="backtrack",
            outcome="backtracking",
            to_screen_fingerprint="us_subscriber_detail",
        )
        repository.update_exploration(first_request.session_id, back_count=1)

        response = observe_universal_navigation(
            returned_request,
            settings=settings,
            repository=repository,
        )
        assert response.phase != "destination_reached", response.model_dump()
        assert response.automation.selected_label != "구독자 98명 >", response.model_dump()
        assert response.automation.action in {"click", "back", "stop", "none"}
        if response.automation.action == "click":
            assert response.automation.selected_label == "구매 항목 및 멤버십"


def assert_scroll_and_unlabeled_icon_exploration() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        for _ in range(4):
            scrolling = observe_universal_navigation(
                custom_request(
                    session_id="scroll-screen",
                    goal_text="구독 해지",
                    title="배민클럽 이용 중 다음 결제일",
                    elements=[
                        # A cancellation search must scroll for a relevant
                        # destination instead of detouring into billing history.
                        element("payment-history", "결제내역"),
                        element("current-membership", "배민클럽"),
                        element("bundle-offer", "배민클럽 + TVING"),
                        element("active-summary", "배민클럽 이용 중 변경 >"),
                        element("restaurant-promo", "내 취향 배민클럽 가게 전체보기"),
                        element("shopping-promo", "배민클럽 특가 0원"),
                        element("delivery-promo", "배달팁 0원 20,000원 이상 주문 시 마이배민클럽"),
                        element("status-heading", "Ut 8:31 100 마이배민클럽"),
                        {
                            "id": "list",
                            "role": "list",
                            "clickable": False,
                            "scrollable": True,
                            "enabled": True,
                            "visible": True,
                            "bounds": [0, 100, 1080, 2200],
                        }
                    ],
                ),
                settings=settings,
                repository=repository,
            )
            assert scrolling.phase == "exploring"
            assert scrolling.automation.action == "scroll_forward"
            assert scrolling.automation.safe_to_execute is True

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        icon = observe_universal_navigation(
            custom_request(
                session_id="unnamed-icon",
                goal_text="구독 해지",
                title="YouTube",
                elements=[
                    {
                        "id": "gear",
                        "role": "image",
                        "clickable": True,
                        "enabled": True,
                        "visible": True,
                        "bounds": [940, 100, 1040, 200],
                    }
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert icon.phase == "exploring"
        assert icon.automation.action == "click"
        assert icon.automation.selected_label is not None
        assert icon.automation.selected_label.startswith("이름 없는")


def assert_youtube_settings_entry_is_preferred() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            custom_request(
                session_id="youtube-settings",
                goal_text="유튜브 프리미엄 구독 해지",
                title="YouTube 내 페이지",
                elements=[
                    element("notifications", "알림", role="image"),
                    element("search", "검색", role="image"),
                    element("settings", "설정", role="image"),
                    element("history", "기록"),
                ],
            ),
            settings=settings,
            repository=repository,
        )
        assert response.phase == "exploring"
        assert response.automation.action == "click"
        assert response.automation.selected_label == "설정", response.model_dump()


def assert_notification_settings_distinguish_inbox_and_selected_content() -> None:
    """Mirror a toolbar-bell failure without relying on an app-specific route."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "physical-notification-settings-mirror"
        package = "com.example.firstseen.media"

        home = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="Open this app's notification settings",
                title="홈",
                elements=[
                    element("notification-bell", "알림", role="image"),
                    element("search", "검색", role="image"),
                    element("profile", "내 페이지"),
                ],
                app_package=package,
            ),
            settings=settings,
            repository=repository,
        )
        assert home.phase == "exploring", home.model_dump()
        assert home.automation.action == "click"
        assert home.automation.selected_label == "내 페이지", home.model_dump()

        # Mirror the real trace after returning from the first mistaken bell
        # branch. Backtracking must not turn an unrelated selected control into
        # destination evidence on the next observation.
        repository.update_exploration(session_id, back_count=1)

        selected_playlist = element("playlist", "재생목록", role="tab")
        selected_playlist["selected"] = True
        profile = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="Open this app's notification settings",
                title="내 페이지",
                elements=[
                    element("notification-bell", "알림", role="image"),
                    element("settings", "설정", role="image"),
                    selected_playlist,
                    element("history", "기록"),
                ],
                app_package=package,
                transition=performed_transition(home),
            ),
            settings=settings,
            repository=repository,
        )
        assert profile.phase == "exploring", profile.model_dump()
        assert profile.automation.action == "click"
        assert profile.automation.selected_label == "설정", profile.model_dump()

        settings_hub = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="Open this app's notification settings",
                title="설정",
                elements=[
                    element("notifications", "알림"),
                    element("playback", "재생"),
                    element("privacy", "개인정보"),
                ],
                app_package=package,
                transition=performed_transition(profile),
            ),
            settings=settings,
            repository=repository,
        )
        assert settings_hub.phase == "exploring", settings_hub.model_dump()
        assert settings_hub.automation.action == "click"
        assert settings_hub.automation.selected_label == "알림", settings_hub.model_dump()

        subscriptions = element(
            "subscription-notifications",
            "구독 알림",
            role="switch",
            checkable=True,
        )
        destination = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="Open this app's notification settings",
                title="알림",
                elements=[
                    subscriptions,
                    element("recommended", "추천 동영상 알림", role="switch", checkable=True),
                ],
                app_package=package,
                transition=performed_transition(settings_hub),
            ),
            settings=settings,
            repository=repository,
        )
        assert destination.phase == "destination_reached", destination.model_dump()
        assert destination.automation.action == "stop"
        assert destination.automation.safe_to_execute is False

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        doorway = observe_universal_navigation(
            custom_request(
                session_id="notification-inbox-negative-mirror",
                goal_text="알림 설정 열기",
                title="홈",
                elements=[element("profile", "내 페이지")],
                app_package="com.example.firstseen.social",
            ),
            settings=settings,
            repository=repository,
        )
        inbox = observe_universal_navigation(
            custom_request(
                session_id="notification-inbox-negative-mirror",
                goal_text="알림 설정 열기",
                title="알림",
                elements=[
                    element("all", "전체", role="tab"),
                    element("comments", "댓글", role="tab"),
                    element("mentions", "멘션", role="tab"),
                    element("up", "위로 이동"),
                ],
                app_package="com.example.firstseen.social",
                transition=performed_transition(doorway),
            ),
            settings=settings,
            repository=repository,
        )
        assert inbox.phase != "destination_reached", inbox.model_dump()
        assert inbox.automation.action in {"back", "click"}
        assert inbox.automation.selected_label not in {"전체", "댓글", "멘션"}


def assert_notification_settings_prefers_settings_over_account_commerce() -> None:
    """A dense first-seen account page must retain its settings doorway."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "notification-settings-dense-account"
        current_account = element("current-account", "내 계정", role="tab")
        current_account["selected"] = True
        settings_gateway = element("preferences", "환경설정")
        settings_gateway["bounds"] = [960, 120, 1060, 220]
        scroll_container = {
            "id": "account-scroll",
            "role": "list",
            "clickable": False,
            "enabled": True,
            "visible": True,
            "scrollable": True,
            "bounds": [0, 220, 1080, 2000],
        }
        response = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="이 앱에서 알림 설정을 열고 싶어",
                title="내 계정",
                elements=[
                    current_account,
                    element("notification-inbox", "알림", role="image"),
                    element("active-membership", "클럽 이용 중"),
                    element("payment-method", "결제수단 관리"),
                    element("wallet", "서비스페이"),
                    element("webview", "webview"),
                    element("login", "로그인"),
                    element("onboarding", "시작하기"),
                    settings_gateway,
                    element("orders", "주문내역"),
                    scroll_container,
                ],
                app_package="com.example.firstseen.delivery",
            ),
            settings=settings,
            repository=repository,
        )

        assert response.phase == "exploring", response.model_dump()
        assert response.recommendation is not None
        assert response.recommendation.target_function == "notification.settings"
        assert response.automation.action == "click"
        assert response.automation.selected_label == "환경설정", response.model_dump()

        frontier_labels = {
            item.label
            for item in repository.exploration_frontier(
                session_id,
                statuses=("queued", "issued", "expanded", "failed", "stale"),
            )
        }
        assert "환경설정" in frontier_labels, frontier_labels
        assert not frontier_labels & {
            "알림",
            "클럽 이용 중",
            "결제수단 관리",
            "서비스페이",
            "webview",
            "로그인",
            "시작하기",
        }, frontier_labels


def assert_transient_recovery_preserves_one_parent_gateway_retry() -> None:
    """A recoverable child may retry its parent once, without forming a loop."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "transient-parent-retry"
        package = "com.example.firstseen.utility"
        home_request = custom_request(
            session_id=session_id,
            goal_text="이 앱에서 알림 설정을 열고 싶어",
            title="홈",
            elements=[
                element("account", "내 계정"),
                element("notification-inbox", "알림", role="image"),
            ],
            app_package=package,
        )
        first = observe_universal_navigation(
            home_request,
            settings=settings,
            repository=repository,
        )
        assert first.automation.action == "click", first.model_dump()
        assert first.automation.selected_label == "내 계정", first.model_dump()

        dead_end = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="이 앱에서 알림 설정을 열고 싶어",
                title="Server error",
                elements=[element("retry-later", "잠시 후 다시 시도", role="text")],
                app_package=package,
                transition=performed_transition(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert dead_end.automation.action == "back", dead_end.model_dump()
        assert repository.transient_retry_element_keys(session_id)

        returned = custom_request(
            session_id=session_id,
            goal_text="이 앱에서 알림 설정을 열고 싶어",
            title="홈",
            elements=[
                element("account", "내 계정"),
                element("notification-inbox", "알림", role="image"),
            ],
            app_package=package,
            transition={
                "from_screen_fingerprint": dead_end.screen_fingerprint,
                "performed_element_id": "android-back",
                "recommendation_id": None,
                "outcome": "navigated",
            },
        )
        retry = observe_universal_navigation(
            returned,
            settings=settings,
            repository=repository,
        )
        assert retry.automation.action == "click", retry.model_dump()
        assert retry.automation.selected_label == "내 계정", retry.model_dump()
        assert not repository.transient_retry_element_keys(session_id)

        second_dead_end = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="이 앱에서 알림 설정을 열고 싶어",
                title="Server error",
                elements=[element("retry-later", "잠시 후 다시 시도", role="text")],
                app_package=package,
                transition=performed_transition(retry),
            ),
            settings=settings,
            repository=repository,
        )
        assert second_dead_end.automation.action == "back", second_dead_end.model_dump()
        assert not repository.transient_retry_element_keys(session_id)
        latest = repository.latest_exploration_attempt(session_id)
        assert latest is not None and latest["command"] == "backtrack", latest


def assert_survey_overlay_retries_account_then_opens_settings() -> None:
    """Mirror home -> account -> survey -> Back -> retry -> clean settings."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "survey-overlay-account-retry"
        package = "com.example.firstseen.delivery"

        def home(*, transition=None):
            return custom_request(
                session_id=session_id,
                goal_text="이 앱에서 알림 설정을 열고 싶어",
                title="홈",
                elements=[
                    element("account", "내 계정"),
                    element("notification-inbox", "알림", role="image"),
                ],
                app_package=package,
                transition=transition,
            )

        first = observe_universal_navigation(
            home(),
            settings=settings,
            repository=repository,
        )
        assert first.automation.action == "click", first.model_dump()
        assert first.automation.selected_label == "내 계정", first.model_dump()

        survey_request = custom_request(
            session_id=session_id,
            goal_text="이 앱에서 알림 설정을 열고 싶어",
            title="서비스 이용 경험, 어떠셨나요?",
            elements=[
                {
                    **element("rating-prompt", "별점을 선택해 주세요", role="text"),
                    "clickable": False,
                },
                element("active-membership", "클럽 이용 중"),
                element("payment-method", "결제수단 관리"),
                element("preferences", "환경설정"),
                element("unnamed-dismiss", "이름 없는 하단 오른쪽 아이콘"),
            ],
            app_package=package,
            transition=performed_transition(first),
        )
        assert _looks_like_transient_feedback_overlay(survey_request)
        survey = observe_universal_navigation(
            survey_request,
            settings=settings,
            repository=repository,
        )
        assert survey.automation.action == "back", survey.model_dump()
        assert repository.transient_retry_element_keys(session_id)

        retried = observe_universal_navigation(
            home(
                transition={
                    "from_screen_fingerprint": survey.screen_fingerprint,
                    "performed_element_id": "android-back",
                    "recommendation_id": None,
                    "outcome": "navigated",
                }
            ),
            settings=settings,
            repository=repository,
        )
        assert retried.automation.action == "click", retried.model_dump()
        assert retried.automation.selected_label == "내 계정", retried.model_dump()
        assert not repository.transient_retry_element_keys(session_id)

        clean_account = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="이 앱에서 알림 설정을 열고 싶어",
                title="내 계정",
                elements=[
                    element("active-membership", "클럽 이용 중"),
                    element("payment-method", "결제수단 관리"),
                    element("preferences", "환경설정"),
                    element("orders", "주문내역"),
                ],
                app_package=package,
                transition=performed_transition(retried),
            ),
            settings=settings,
            repository=repository,
        )
        assert clean_account.automation.action == "click", clean_account.model_dump()
        assert clean_account.automation.selected_label == "환경설정", clean_account.model_dump()

    explicit_form = custom_request(
        session_id="explicit-feedback-form",
        goal_text="계정 설정을 열고 싶어",
        title="Rate your experience - feedback form",
        elements=[
            element("feedback", "의견을 입력해 주세요", role="edittext"),
            element("submit", "Send feedback"),
        ],
        app_package="com.example.firstseen.utility",
    )
    assert not _looks_like_transient_feedback_overlay(explicit_form)

    requested_survey = custom_request(
        session_id="requested-feedback-survey",
        goal_text="앱 만족도 설문에 응답하고 싶어",
        title="서비스 이용 경험, 어떠셨나요?",
        elements=[element("rating", "별점을 선택해 주세요")],
        app_package="com.example.firstseen.utility",
    )
    assert not _looks_like_transient_feedback_overlay(requested_survey)

    mixed_account_tree = custom_request(
        session_id="survey-question-inside-account-tree",
        goal_text="배달의민족 알림 설정을 열고 싶어",
        title="마이배민",
        elements=[
            element("survey-question", "배민의 음식주문 경험, 어떠셨나요?", role="text"),
            element("preferences", "환경설정"),
            element("support", "고객센터"),
        ],
        app_package="com.sampleapp",
    )
    assert _looks_like_transient_feedback_overlay(mixed_account_tree)

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        static_card_response = observe_universal_navigation(
            mixed_account_tree,
            settings=settings,
            repository=repository,
        )
        assert static_card_response.automation.action == "click", static_card_response.model_dump()
        assert static_card_response.automation.selected_label == "환경설정", static_card_response.model_dump()


def assert_full_screen_in_app_message_is_safely_dismissed() -> None:
    """A touch-intercepting SDK WebView must not hide valid app controls."""

    overlay = {
        "id": "in-app-message",
        "view_id": "com.example.dynamic:id/com_braze_inappmessage_html",
        "role": "button",
        "clickable": True,
        "enabled": True,
        "visible": True,
        "bounds": [0, 0, 1440, 3120],
    }
    underlying_account = {
        **element("my-account", "마이페이지"),
        "bounds": [1152, 2766, 1440, 2948],
    }
    request = custom_request(
        session_id="full-screen-in-app-message",
        goal_text="배달의민족 알림 설정을 열고 싶어",
        title="배달의민족",
        elements=[overlay, element("close", "닫기"), underlying_account],
        app_package="com.sampleapp",
    )
    assert _looks_like_transient_in_app_message_overlay(request)
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            request,
            settings=settings,
            repository=repository,
        )
        assert response.automation.action == "click", response.model_dump()
        assert response.automation.selected_label == "닫기", response.model_dump()
        assert response.automation.safe_to_execute, response.model_dump()

    without_close = request.model_copy(
        update={
            "request_id": "request-full-screen-in-app-message-without-close",
            "session_id": "full-screen-in-app-message-without-close",
            "screen": request.screen.model_copy(
                update={
                    "elements": [
                        item
                        for item in request.screen.elements
                        if (item.text or item.content_description or "") != "닫기"
                    ]
                }
            ),
        }
    )
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        response = observe_universal_navigation(
            without_close,
            settings=settings,
            repository=repository,
        )
        assert response.automation.action == "back", response.model_dump()
        assert response.automation.safe_to_execute, response.model_dump()

    ordinary_webview = custom_request(
        session_id="ordinary-full-screen-webview",
        goal_text="고객센터를 열고 싶어",
        title="고객센터",
        elements=[
            {
                **overlay,
                "id": "support-webview",
                "view_id": "com.example.dynamic:id/support_webview",
            }
        ],
    )
    assert not _looks_like_transient_in_app_message_overlay(ordinary_webview)

    requested_offer = request.model_copy(
        update={"goal_text": "배달의민족 혜택 팝업 내용을 보고 싶어"}
    )
    assert not _looks_like_transient_in_app_message_overlay(requested_offer)


def assert_baemin_club_cancellation_route_is_recognized() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        package = "com.sampleapp"
        first = observe_universal_navigation(
            custom_request(
                session_id="baemin-club-cancel",
                goal_text="배달의민족 배민클럽 구독 해지",
                title="배달의민족 홈",
                elements=[
                    element("my-baemin", "마이배민"),
                    element("search", "검색"),
                    element("orders", "주문내역"),
                ],
                app_package=package,
            ),
            settings=settings,
            repository=repository,
        )
        assert first.phase == "exploring"
        assert first.automation.action == "click"
        assert first.automation.selected_label == "마이배민"

        # The app can already be on the My page when exploration starts. The
        # selected/current tab must not be clicked repeatedly; the visible
        # club card should win over the settings icon.
        current_screen_heading = element("my-heading", "마이배민", role="text")
        current_screen_heading["clickable"] = False
        current_screen_heading["bounds"] = [53, 133, 214, 205]
        current_tab = element("current-my", "마이배민")
        current_tab["bounds"] = [864, 2075, 1080, 2212]
        club_card = element("club-current", "배민클럽 이용 중")
        club_card["bounds"] = [42, 742, 1038, 1013]
        settings_button = element("settings-current", "환경설정")
        settings_button["bounds"] = [980, 137, 1043, 200]
        already_on_my = observe_universal_navigation(
            custom_request(
                session_id="baemin-club-already-on-my",
                goal_text="배달의민족 배민클럽 구독 해지",
                title="배민의 음식주문 경험, 어떠셨나요?",
                elements=[
                    current_screen_heading,
                    current_tab,
                    club_card,
                    settings_button,
                ],
                app_package=package,
            ),
            settings=settings,
            repository=repository,
        )
        assert already_on_my.phase == "exploring"
        assert already_on_my.automation.action == "click", already_on_my.model_dump()
        assert already_on_my.automation.selected_label == "배민클럽 이용 중", already_on_my.automation.model_dump()

        second = observe_universal_navigation(
            custom_request(
                session_id="baemin-club-cancel",
                goal_text="배달의민족 배민클럽 구독 해지",
                title="마이배민",
                elements=[
                    element("club-info", "배민클럽 이용 중"),
                    element("orders", "주문내역"),
                    element("support", "고객센터"),
                    element("settings", "환경설정"),
                ],
                app_package=package,
                transition=performed_transition(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert second.phase == "exploring"
        assert second.automation.action == "click"
        assert second.automation.selected_label == "배민클럽 이용 중"

        destination = observe_universal_navigation(
            custom_request(
                session_id="baemin-club-cancel",
                goal_text="배달의민족 배민클럽 구독 해지",
                title="마이배민클럽",
                elements=[
                    element("cancel-club", "해지하기"),
                    element("benefits", "혜택 보기"),
                    element("payments", "결제내역"),
                ],
                app_package=package,
                transition=performed_transition(second),
            ),
            settings=settings,
            repository=repository,
        )
        assert destination.phase == "destination_reached"
        assert destination.status == "goal_completed"
        assert destination.automation.action == "stop"
        assert destination.recommendation is not None
        assert destination.recommendation.selected_label == "해지하기"
        assert destination.recommendation.requires_user_confirmation is True


def assert_just_entered_bottom_account_tab_is_not_clicked_again() -> None:
    """A stable bottom tab that produced this screen is already active."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "bottom-account-tab-repeat-guard"
        package = "com.example.firstseen.delivery"
        first = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="현재 이용 중인 멤버십 구독을 해지하고 싶어",
                title="추천",
                elements=[
                    element("home-tab", "하단탭바 홈탭"),
                    element("account-tab", "하단탭바 내 계정탭"),
                    element("search", "검색", role="image"),
                ],
                app_package=package,
            ),
            settings=settings,
            repository=repository,
        )
        assert first.phase == "exploring", first.model_dump()
        assert first.automation.action == "click"
        assert first.automation.selected_label == "하단탭바 내 계정탭", first.model_dump()

        # The custom bar exposes role=button and omits selected state on the
        # destination screen. The stable semantic element and transition
        # history must still identify it as the current tab.
        current_account = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="현재 이용 중인 멤버십 구독을 해지하고 싶어",
                title="내 계정",
                elements=[
                    element("account-tab", "하단탭바 내 계정탭"),
                    element("active-membership", "현재 멤버십 이용 중"),
                    element("orders", "주문 내역"),
                ],
                app_package=package,
                transition=performed_transition(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert current_account.phase == "exploring", current_account.model_dump()
        assert current_account.automation.action == "click"
        assert current_account.automation.selected_label == "현재 멤버십 이용 중", current_account.model_dump()

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        session_id = "bottom-account-tab-no-alternative"
        package = "com.example.firstseen.shopping"
        first = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="구독 관리",
                title="홈",
                elements=[element("account-tab", "Bottom navigation My account tab")],
                app_package=package,
            ),
            settings=settings,
            repository=repository,
        )
        repeated = observe_universal_navigation(
            custom_request(
                session_id=session_id,
                goal_text="구독 관리",
                title="My account",
                # Dynamic renderers may replace the node ID while retaining
                # the semantic tab label and role.
                elements=[element("account-tab-refreshed", "Bottom navigation My account tab")],
                app_package=package,
                transition=performed_transition(first),
            ),
            settings=settings,
            repository=repository,
        )
        assert not (
            repeated.automation.action == "click"
            and repeated.automation.selected_label == "Bottom navigation My account tab"
        ), repeated.model_dump()


def assert_cross_app_signup_gateways_are_explored() -> None:
    """A new app can reach sign-up through common menus without an app route."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        package = "com.jejuair.android"
        home = observe_universal_navigation(
            custom_request(
                session_id="jeju-signup",
                goal_text="제주항공 회원가입",
                title="제주항공",
                elements=[
                    element("booking", "항공권 예매"),
                    element("my-page", "마이페이지", role="tab"),
                    element("all-menu", "전체메뉴", role="image"),
                ],
                app_package=package,
            ),
            settings=settings,
            repository=repository,
        )
        assert home.phase == "exploring"
        assert home.automation.action == "click"
        assert home.automation.selected_label == "마이페이지"

        auth_hub = observe_universal_navigation(
            custom_request(
                session_id="jeju-signup",
                goal_text="제주항공 회원가입",
                title="마이페이지",
                elements=[
                    element("auth-hub", "로그인 / 회원가입"),
                    element("reservation", "비회원 예약조회"),
                    element("customer", "고객센터"),
                ],
                app_package=package,
                transition=performed_transition(home),
            ),
            settings=settings,
            repository=repository,
        )
        assert auth_hub.phase == "exploring"
        assert auth_hub.automation.action == "click", auth_hub.model_dump()
        assert auth_hub.automation.selected_label == "로그인 / 회원가입"

        signup = observe_universal_navigation(
            custom_request(
                session_id="jeju-signup",
                goal_text="제주항공 회원가입",
                title="로그인",
                elements=[
                    element("login", "로그인"),
                    element("signup", "회원가입"),
                    element("guest", "비회원 예약조회"),
                ],
                app_package=package,
                transition=performed_transition(auth_hub),
            ),
            settings=settings,
            repository=repository,
        )
        assert signup.phase == "destination_reached"
        assert signup.automation.action == "stop"
        assert signup.automation.selected_label == "회원가입"
        assert signup.automation.safe_to_execute is False


def assert_infinite_feed_scrolls_are_bounded() -> None:
    """Changing feed fingerprints cannot bypass the session scroll budget."""

    feed_elements = [
        {
            "id": "timeline",
            "role": "list",
            "clickable": False,
            "scrollable": True,
            "enabled": True,
            "visible": True,
            "bounds": [0, 200, 1080, 2210],
        },
        element("reply", "답글"),
        element("repost", "재게시"),
        element("like", "마음에 들어요"),
        element("share", "공유하기"),
    ]
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        first = observe_universal_navigation(
            custom_request(
                session_id="changing-feed",
                goal_text="X 계정 삭제",
                title="추천 피드 첫 게시물",
                elements=feed_elements,
                app_package="com.twitter.android",
            ),
            settings=settings,
            repository=repository,
        )
        assert first.phase == "exploring"
        assert first.automation.action == "scroll_forward"

        second = observe_universal_navigation(
            custom_request(
                session_id="changing-feed",
                goal_text="X 계정 삭제",
                title="추천 피드 다음 게시물",
                elements=feed_elements,
                app_package="com.twitter.android",
            ),
            settings=settings,
            repository=repository,
        )
        assert second.phase == "stopped"
        assert second.automation.action == "stop"
        assert any("무한 피드" in warning for warning in second.warnings)

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        drawer = observe_universal_navigation(
            custom_request(
                session_id="feed-drawer",
                goal_text="X 계정 삭제",
                title="추천 피드",
                elements=[element("drawer", "탐색 서랍 보기", role="image"), *feed_elements],
                app_package="com.twitter.android",
            ),
            settings=settings,
            repository=repository,
        )
        assert drawer.phase == "exploring"
        assert drawer.automation.action == "click"
        assert drawer.automation.selected_label == "탐색 서랍 보기"


def assert_netflix_signup_gateways_are_recognized() -> None:
    """Netflix-style onboarding and unified auth forms are sign-up entries."""

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        landing = observe_universal_navigation(
            custom_request(
                session_id="netflix-signup-landing",
                goal_text="넷플릭스 회원가입",
                title="Netflix",
                elements=[
                    element("get-started", "시\ufeff작\ufeff하\ufeff기"),
                    element("login", "로\ufeff그\ufeff인"),
                ],
                app_package="com.netflix.mediaclient",
            ),
            settings=settings,
            repository=repository,
        )
        assert landing.phase == "destination_reached", landing.model_dump()
        assert landing.automation.action == "stop"
        assert landing.automation.selected_label is not None
        assert landing.automation.selected_label.replace("\ufeff", "") == "시작하기"

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        unified = observe_universal_navigation(
            custom_request(
                session_id="netflix-unified-signup",
                goal_text="넷플릭스 회원가입",
                title="시청할 준비가 되셨나요?",
                elements=[
                    {
                        "id": "signup-explanation",
                        "text": "정보를 입력해 로그인하거나 새 계정으로 시작하세요.",
                        "role": "text",
                        "clickable": False,
                        "enabled": True,
                        "visible": True,
                    },
                    element("email-or-phone", "이메일 주소 또는 휴대폰 번호", role="input"),
                    element("continue", "다음"),
                ],
                app_package="com.netflix.mediaclient",
            ),
            settings=settings,
            repository=repository,
        )
        assert unified.phase == "destination_reached", unified.model_dump()
        assert unified.automation.action == "stop"
        assert unified.automation.selected_label == "이메일 주소 또는 휴대폰 번호"
        assert unified.automation.safe_to_execute is False


def assert_reversible_target_gateways_beat_weak_terminal_collisions() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        account = observe_universal_navigation(
            custom_request(
                session_id="netflix-cancel-gateway-regression",
                goal_text="Cancel my Netflix membership",
                title="Netflix menu",
                elements=[
                    element("account", "Account"),
                    element("list", "My List"),
                    element("help", "Help"),
                ],
                app_package="com.netflix.mediaclient",
            ),
            settings=settings,
            repository=repository,
        )
        assert account.automation.action == "click", account.model_dump()
        assert account.automation.selected_label == "Account", account.model_dump()

        manage = observe_universal_navigation(
            custom_request(
                session_id="netflix-cancel-gateway-regression",
                goal_text="Cancel my Netflix membership",
                title="Account",
                elements=[
                    element("manage", "Manage membership"),
                    element("change", "Change plan"),
                    element("history", "Payment history"),
                ],
                app_package="com.netflix.mediaclient",
                transition=performed_transition(account),
            ),
            settings=settings,
            repository=repository,
        )
        assert manage.phase == "exploring", manage.model_dump()
        assert manage.automation.action == "click", manage.model_dump()
        assert manage.automation.selected_label == "Manage membership", manage.model_dump()

    with TemporaryDirectory() as temporary_directory:
        repository, settings = environment(temporary_directory)
        features = observe_universal_navigation(
            custom_request(
                session_id="safety-feature-gateway-regression",
                goal_text="Show the car-crash detection preference on this supported phone",
                title="Safety app",
                elements=[
                    element("features", "Features"),
                    element("info", "Your info"),
                    element("alerts", "Alerts"),
                ],
                app_package="com.google.android.apps.safetyhub",
            ),
            settings=settings,
            repository=repository,
        )
        assert features.automation.action == "click", features.model_dump()
        assert features.automation.selected_label == "Features", features.model_dump()

        feature_list = element("feature-list", "Safety features")
        feature_list.update({"clickable": False, "scrollable": True, "role": "list"})
        crash = observe_universal_navigation(
            custom_request(
                session_id="safety-feature-gateway-regression",
                goal_text="Show the car-crash detection preference on this supported phone",
                title="Safety features",
                elements=[
                    feature_list,
                    element("crash", "Car crash detection"),
                    element("sos", "Emergency SOS"),
                ],
                app_package="com.google.android.apps.safetyhub",
                transition=performed_transition(features),
            ),
            settings=settings,
            repository=repository,
        )
        assert crash.phase == "exploring", crash.model_dump()
        assert crash.automation.action == "click", crash.model_dump()
        assert crash.automation.selected_label == "Car crash detection", crash.model_dump()


def environment(directory: str, *, max_actions: int = 16):
    root = Path(directory)
    repository = UniversalNavigationGraphRepository(root / "graph.sqlite")
    settings = Settings(
        navigation_agent_provider="mock",
        android_control_index_path="",
        navigation_function_db_path=str(_SHARED_FUNCTION_CATALOG_DB),
        navigation_exploration_timeout_seconds=55,
        navigation_exploration_max_actions=max_actions,
        navigation_exploration_max_depth=9,
    )
    return repository, settings


def scenario_screens():
    return [
        ("Home", [element("my", "My page"), element("feed", "Subscriptions")]),
        (
            "Account",
            [element("subscriptions", "Payments and subscriptions"), element("settings", "Settings")],
        ),
        (
            "Memberships",
            [element("premium", "Premium membership"), element("history", "Purchase history")],
        ),
        (
            "Plan details",
            [element("cancel", "Cancel subscription"), element("payment", "Payment method")],
        ),
    ]


def request(
    request_number: int,
    screen_index: int,
    screens,
    *,
    transition: dict | None = None,
    mode: str = "explore",
    session_id: str = "exploration-session",
) -> UniversalNavigationObserveRequest:
    title, elements = screens[screen_index]
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": f"explore-{request_number}",
            "session_id": session_id,
            "app_package": "com.example.dynamic",
            "app_version": "1.0.0",
            "locale": "en-US",
            "goal_text": "cancel subscription",
            "operation_mode": mode,
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


def custom_request(
    *,
    session_id: str,
    goal_text: str,
    title: str,
    elements: list[dict],
    app_package: str = "com.google.android.youtube",
    transition: dict | None = None,
):
    return UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": f"request-{session_id}",
            "session_id": session_id,
            "app_package": app_package,
            "app_version": "21.0",
            "locale": "ko-KR",
            "goal_text": goal_text,
            "operation_mode": "explore",
            "screen": {
                "activity_name": "InternalMainActivity",
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


def element(element_id: str, label: str, *, role: str = "button", checkable: bool = False) -> dict:
    return {
        "id": element_id,
        "text": label,
        "view_id": f"com.example.dynamic:id/{element_id}",
        "role": role,
        "clickable": True,
        "enabled": True,
        "visible": True,
        "checkable": checkable,
        "checked": False if checkable else None,
        "bounds": [20, 100, 1000, 180],
    }


def performed_transition(response) -> dict:
    assert response.recommendation is not None
    assert response.automation.selected_element_id is not None
    return {
        "from_screen_fingerprint": response.screen_fingerprint,
        "performed_element_id": response.automation.selected_element_id,
        "recommendation_id": response.recommendation.recommendation_id,
        "outcome": "navigated",
    }


def approve_discovered_route(
    repository: UniversalNavigationGraphRepository,
    route_id: str,
    *,
    existing_session_id: str,
) -> None:
    route = repository.route(route_id)
    assert route is not None
    repository.performance.apply_validation(
        session_id=existing_session_id,
        destination_correct=True,
        safe_stop=True,
        verification_level="benchmark_gold",
    )
    for index in range(2):
        session_id = f"{route_id}-approval-{index}"
        repository.performance.record_stage(
            session_id=session_id,
            app_package="com.example.dynamic",
            app_version="1.0.0",
            locale="en-US",
            goal_key=route.goal_key,
            target_function=route.target_function,
            start_screen_fingerprint=route.start_screen_fingerprint,
            current_screen_fingerprint=route.destination_screen_fingerprint,
            destination_screen_fingerprint=route.destination_screen_fingerprint,
            decision_mode="function_graph_exploration",
            phase="destination_reached",
            action="stop",
            safe_to_execute=False,
            selected_risk_level="medium",
            selected_element_key="ue_terminal",
            route_id=route_id,
            failure_type="",
            measurement=StageMeasurement(
                measurement_source="synthetic",
                server_total_ms=10.0,
                exploration_elapsed_ms=1000.0 + index,
            ),
        )
        repository.performance.apply_validation(
            session_id=session_id,
            destination_correct=True,
            safe_stop=True,
            verification_level="benchmark_gold",
        )
    repository.approve_route(route_id)


if __name__ == "__main__":
    main()
