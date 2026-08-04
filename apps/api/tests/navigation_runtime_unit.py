from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import get_settings  # noqa: E402
from app.navigation_contracts import (  # noqa: E402
    AccessibilityNodeSummary,
    DecideRequest,
    NavigationAction,
    NavigationCandidate,
    ObserveRequest,
    ScreenObservation,
)
from app.services.navigation_decision_memory import NavigationDecisionMemory  # noqa: E402
from app.services.navigation_dataset_split import (  # noqa: E402
    DatasetSplitAccessError,
    NavigationDatasetSplitManifest,
)
from app.services.navigation_model_clients import (  # noqa: E402
    Exaone45VisionClient,
    NavigationPlannerResearchClient,
    OpenAICompatibleChatClient,
)
from app.services.navigation_research_policy import AndroidWorldResearchPolicy  # noqa: E402
from app.services.navigation_runtime import (  # noqa: E402
    NavigationRuntime,
    _contextualize_membership_cancellation_safety,
    _interleaved_repeat_guard,
    _is_non_plan_payment_method_screen,
    _semantic_fast_path_grounded_progress,
    _selected_reverse_navigation_guard,
    _successful_back_recovery,
    verify_transition,
)
from app.services.navigation_runtime_store import NavigationRuntimeStore  # noqa: E402


def _load_migration_module():
    path = ROOT / "scripts" / "Migrate-NavigationDecisionDb.py"
    spec = importlib.util.spec_from_file_location("navigation_decision_migration_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_decision_db(path: Path) -> None:
    migration = _load_migration_module()
    connection = sqlite3.connect(path)
    connection.executescript((ROOT / "db" / "navigation_decision_v1.sql").read_text(encoding="utf-8"))
    migration.seed_database(connection, "a" * 64)
    connection.commit()
    connection.close()


def _policy() -> AndroidWorldResearchPolicy:
    return AndroidWorldResearchPolicy(
        planner_model=NavigationPlannerResearchClient(
            OpenAICompatibleChatClient(
                api_key="", base_url="https://example.invalid/v1", model="test-solar-pro3"
            ),
            provider_name="solar_pro3",
        ),
        exaone_vlm=Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key="", base_url="", model="test-exaone-4.5"
            )
        ),
        allow_model_fallback=True,
    )


def _account_screen() -> ScreenObservation:
    return ScreenObservation(
        window_title="홈",
        activity_name="android.view.View",
        navigation_depth=0,
        candidates=[
            NavigationCandidate(
                candidate_id="profile",
                label="마이페이지",
                role="button",
                icon_semantics="프로필 사람 아이콘",
                nearby_text="내 정보와 설정",
                position_bucket="bottom",
            ),
            NavigationCandidate(candidate_id="search", label="검색", role="button"),
        ],
    )


def main() -> None:
    assert _is_non_plan_payment_method_screen(
        "membership.change",
        ("기본", "결제", "수단", "업데이트", "카드", "추가"),
    )
    assert not _is_non_plan_payment_method_screen(
        "membership.change",
        ("요금제", "변경", "결제", "수단"),
    )
    assert not _is_non_plan_payment_method_screen(
        "membership.cancel",
        ("기본", "결제", "수단", "업데이트"),
    )
    contextual_cancel_screen = _contextualize_membership_cancellation_safety(
        ScreenObservation(
            window_title="YouTube Premium",
            nodes=[
                AccessibilityNodeSummary(
                    node_id="cancel",
                    text="취소",
                    clickable=True,
                ),
                AccessibilityNodeSummary(
                    node_id="billing",
                    text="다음 결제일: 9월 3일",
                ),
            ],
            candidates=[NavigationCandidate(candidate_id="cancel", label="취소")],
        ),
        "membership.cancel",
    )
    assert contextual_cancel_screen.candidates[0].risk_level == "high"
    dismiss_cancel_screen = _contextualize_membership_cancellation_safety(
        ScreenObservation(
            window_title="알림",
            nodes=[
                AccessibilityNodeSummary(
                    node_id="cancel",
                    text="취소",
                    clickable=True,
                )
            ],
            candidates=[NavigationCandidate(candidate_id="cancel", label="취소")],
        ),
        "membership.cancel",
    )
    assert dismiss_cancel_screen.candidates[0].risk_level == "low"
    failed_screen_history = [
        {
            "action_name": "click",
            "screen_fingerprint": "membership-menu",
            "connectivity_status": "observed",
            "outcome_type": "wrong_destination",
            "progress_label": "regressed",
            "recovery_action": "back",
        }
    ]
    assert _successful_back_recovery(
        action_name="back",
        previous_fingerprint="membership-purchase",
        next_fingerprint="membership-menu-dynamic-version",
        session_app_package="evaluation.membership.app",
        next_app_package="evaluation.membership.app",
        recent_history=failed_screen_history,
    ) is True
    assert _successful_back_recovery(
        action_name="back",
        previous_fingerprint="membership-purchase",
        next_fingerprint="membership-home",
        session_app_package="evaluation.membership.app",
        next_app_package="evaluation.membership.app",
        recent_history=[
            *failed_screen_history,
            {
                "action_name": "back",
                "screen_fingerprint": "membership-purchase",
                "connectivity_status": "observed",
                "outcome_type": "wrong_destination",
                "progress_label": "regressed",
                "recovery_action": "back",
            },
        ],
    ) is True
    assert _successful_back_recovery(
        action_name="back",
        previous_fingerprint="membership-purchase",
        next_fingerprint="external-screen",
        session_app_package="evaluation.membership.app",
        next_app_package="other.app",
        recent_history=failed_screen_history,
    ) is False
    assert _successful_back_recovery(
        action_name="click",
        previous_fingerprint="membership-purchase",
        next_fingerprint="membership-menu",
        session_app_package="evaluation.membership.app",
        next_app_package="evaluation.membership.app",
        recent_history=failed_screen_history,
    ) is False
    sparse_reverse_guard = _selected_reverse_navigation_guard(
        NavigationAction(name="click", candidate_id="navigate-up"),
        candidates=[
            NavigationCandidate(
                candidate_id="forward",
                label="Account",
                role="button",
            ),
            NavigationCandidate(
                candidate_id="navigate-up",
                label="",
                role="icon_button",
            )
        ],
        nodes=[
            AccessibilityNodeSummary(
                node_id="navigate-up",
                content_description="위로 이동",
                clickable=True,
            )
        ],
        screen_fingerprint="external-loading",
        recent_history=[],
    )
    assert sparse_reverse_guard is not None
    assert sparse_reverse_guard.name == "wait_and_observe"
    unlabeled_structural_reverse = _selected_reverse_navigation_guard(
        NavigationAction(name="click", candidate_id="unknown-top-icon"),
        candidates=[
            NavigationCandidate(
                candidate_id="unknown-top-icon",
                label="",
                role="icon_button",
                position_bucket="top",
            )
        ],
        nodes=[],
        screen_fingerprint="external-loading-unlabeled",
        recent_history=[],
    )
    assert unlabeled_structural_reverse is not None
    assert unlabeled_structural_reverse.name == "wait_and_observe"

    repeated_after_visual_wait = _interleaved_repeat_guard(
        NavigationAction(name="click", candidate_id="account-url"),
        recent_history=[
            {
                "action_name": "click",
                "candidate_id": "account-url",
                "connectivity_status": "observed",
                "progress_label": "unknown",
            },
            {"action_name": "wait_and_observe"},
        ],
    )
    assert repeated_after_visual_wait is not None
    assert repeated_after_visual_wait.name == "wait_and_observe"
    repeated_after_two_waits = _interleaved_repeat_guard(
        NavigationAction(name="click", candidate_id="account-url"),
        recent_history=[
            {
                "action_name": "click",
                "candidate_id": "account-url",
                "connectivity_status": "observed",
                "progress_label": "unknown",
            },
            {"action_name": "wait_and_observe"},
            {"action_name": "wait_and_observe"},
        ],
    )
    assert repeated_after_two_waits is not None
    assert repeated_after_two_waits.name == "stop_for_user"

    external_destination_collision = verify_transition(
        action_name="back",
        previous_fingerprint="netflix-profile-gate",
        next_fingerprint="foreign-membership-screen",
        destination_match_before=0.0,
        destination_match_after=1.0,
        destination_threshold=0.7,
        observed_signal="external_app",
    )
    assert external_destination_collision.outcome_type == "external_app"
    assert external_destination_collision.progress_label == "regressed"
    assert _semantic_fast_path_grounded_progress(
        planner_provider="semantic_intermediate_role_fast_path",
        goal_id="account.delete",
        screen_tokens=("계정", "설정"),
    )
    assert not _semantic_fast_path_grounded_progress(
        planner_provider="semantic_intermediate_role_fast_path",
        goal_id="account.delete",
        screen_tokens=("구독", "새로운 콘텐츠", "홈"),
    )
    assert _semantic_fast_path_grounded_progress(
        planner_provider="semantic_safe_goal_entry_fast_path",
        goal_id="membership.cancel",
        screen_tokens=("프로필", "계정 관리"),
    )
    assert not _semantic_fast_path_grounded_progress(
        planner_provider="solar_pro3_step_evaluator",
        goal_id="account.delete",
        screen_tokens=("계정", "설정"),
    )

    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        decision_db = temporary_path / "decision.sqlite"
        runtime_db = temporary_path / "runtime.sqlite"
        _build_decision_db(decision_db)
        runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(runtime_db),
            policy=_policy(),
        )
        first = runtime.decide(
            DecideRequest(
                request_id="request-1",
                app_package="evaluation.unseen.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=_account_screen(),
            )
        )
        assert first.goal.status == "recognized"
        assert first.action.name == "click" and first.action.candidate_id == "profile"
        assert first.evidence_case_ids == []

        profile_gate_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "profile-gate-runtime.sqlite"),
            policy=_policy(),
        )
        profile_gate_decision = profile_gate_runtime.decide(
            DecideRequest(
                request_id="request-profile-gate",
                app_package="evaluation.profile-gate.app",
                goal_text="멤버십 해지",
                screen=ScreenObservation(
                    app_package="evaluation.profile-gate.app",
                    window_title="넷플릭스를 시청할 프로필을 선택하세요.",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="existing-profile",
                            label="[account] 총 3개 항목 중 1번째. [account]",
                            icon_semantics="user avatar with smiley face",
                            visual_role="current profile selection",
                        ),
                        NavigationCandidate(
                            candidate_id="add-profile",
                            label="추가 총 3개 항목 중 2번째. 프로필을 추가하세요.",
                        ),
                        NavigationCandidate(
                            candidate_id="edit-profile",
                            label="변경 총 3개 항목 중 3번째. 프로필을 변경하세요.",
                        ),
                    ],
                ),
            )
        )
        assert profile_gate_decision.action.name == "click"
        assert profile_gate_decision.action.candidate_id == "existing-profile"
        assert profile_gate_decision.planner_provider == "semantic_intermediate_role_fast_path"
        assert profile_gate_decision.visual_reobserve_required is False

        no_change = runtime.observe(
            ObserveRequest(
                request_id="request-1-observe",
                decision_id=first.decision_id,
                connectivity_status="observed",
                next_screen=_account_screen(),
            )
        )
        assert no_change.outcome_type == "no_change"
        assert no_change.screen_changed is False
        assert no_change.navigation_progressed is False
        assert no_change.connection_error is False
        assert no_change.candidate_forbidden is True
        assert no_change.knowledge_revision_queued is True
        first_history = runtime.store.recent_history(first.session_id, limit=5)
        assert first_history[-1]["selected_candidate_label"] == "마이페이지"

        changed_account_screen = _account_screen().model_copy(
            update={"window_title": "Account screen refreshed"}
        )
        retry = runtime.decide(
            DecideRequest(
                request_id="request-2",
                session_id=first.session_id,
                app_package="evaluation.unseen.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                step_ordinal=1,
                screen=changed_account_screen,
            )
        )
        assert (
            runtime.store.decision(first.decision_id)["screen_fingerprint"]
            != runtime.store.decision(retry.decision_id)["screen_fingerprint"]
        )
        assert retry.action.candidate_id != "profile"
        assert any(value.candidate_id == "profile" and value.forbidden for value in retry.candidate_values)

        disconnected = runtime.observe(
            ObserveRequest(
                request_id="request-2-observe",
                decision_id=retry.decision_id,
                connectivity_status="transport_error",
            )
        )
        assert disconnected.outcome_type == "unknown"
        assert disconnected.state_changed is None
        assert disconnected.candidate_forbidden is False
        assert disconnected.knowledge_revision_queued is False
        assert disconnected.recovery_action is not None
        assert disconnected.recovery_action.name == "wait_and_observe"
        assert disconnected.session_status == "active"
        assert disconnected.connection_error is True
        assert disconnected.screen_changed is None
        assert disconnected.navigation_progressed is None

        recovery_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "external-recovery-runtime.sqlite"),
            policy=_policy(),
        )
        original_package = "evaluation.recovery.app"
        origin_screen = _account_screen().model_copy(
            update={"app_package": original_package}
        )
        first_recovery_decision = recovery_runtime.decide(
            DecideRequest(
                request_id="request-external-origin",
                app_package=original_package,
                goal_text="Find account deletion settings",
                screen=origin_screen,
            )
        )
        first_external_observation = recovery_runtime.observe(
            ObserveRequest(
                request_id="request-external-observe",
                decision_id=first_recovery_decision.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                observed_signal="external_app",
                next_screen=ScreenObservation(
                    app_package="com.android.settings",
                    window_title="Notification settings",
                    activity_name="android.settings.NOTIFICATION_SETTINGS",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="return-to-app",
                            label="Back",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert first_external_observation.outcome_type == "external_app"
        assert first_external_observation.recovery_action is not None
        assert first_external_observation.recovery_action.name == "back"
        recovery_history = recovery_runtime.store.recent_history(
            first_recovery_decision.session_id,
            limit=5,
        )
        assert recovery_history[-1]["recovery_action"] == "back"
        external_screen_decision = recovery_runtime.decide(
            DecideRequest(
                request_id="request-external-recovery",
                session_id=first_recovery_decision.session_id,
                app_package=original_package,
                goal_text="Find account deletion settings",
                step_ordinal=1,
                screen=ScreenObservation(
                    app_package="com.android.settings",
                    window_title="Notification settings",
                    activity_name="android.settings.NOTIFICATION_SETTINGS",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="return-to-app",
                            label="Back",
                            role="button",
                        )
                    ],
                ),
            )
        )
        returned_observation = recovery_runtime.observe(
            ObserveRequest(
                request_id="request-returned-observe",
                decision_id=external_screen_decision.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                observed_signal="external_app",
                next_screen=origin_screen,
            )
        )
        assert returned_observation.outcome_type == "navigated", returned_observation
        assert returned_observation.progress_label == "advanced"
        assert returned_observation.failure_class == ""
        assert returned_observation.candidate_forbidden is False

        account_hub_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "account-hub-runtime.sqlite"),
            policy=_policy(),
        )
        account_hub_decision = account_hub_runtime.decide(
            DecideRequest(
                request_id="request-account-hub-alias",
                app_package="evaluation.account-hub.app",
                locale="ko-KR",
                goal_text="멤버십을 해지하고 싶어",
                screen=ScreenObservation(
                    app_package="evaluation.account-hub.app",
                    window_title="프로필 관리",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="account",
                            label="계정",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="app-settings",
                            label="앱 설정",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="help",
                            label="고객 센터",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert account_hub_decision.action.name == "click"
        assert account_hub_decision.action.candidate_id == "account"
        assert account_hub_decision.planner_provider in {
            "semantic_intermediate_role_fast_path",
            "decision_memory_fallback",
        }

        visual_gate_policy = _policy()
        visual_gate_policy.exaone_vlm = Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key="",
                base_url="http://127.0.0.1:9/v1",
                model="test-exaone-4.5",
            )
        )
        visual_gate_policy.semantic_intermediate_fast_path_candidate = (
            lambda **_: "account"
        )
        visual_gate_policy._structural_continuation_fast_path_candidate = (
            lambda **_: None
        )
        visual_gate_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "visual-gate-runtime.sqlite"),
            policy=visual_gate_policy,
        )
        obvious_intermediate = visual_gate_runtime.decide(
            DecideRequest(
                request_id="request-obvious-intermediate-before-visual-gate",
                app_package="evaluation.visual-gate.app",
                locale="ko-KR",
                goal_text="cancel subscription",
                screen=ScreenObservation(
                    app_package="evaluation.visual-gate.app",
                    window_title="profile management",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="account",
                            label="account",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="app-settings",
                            label="app settings",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert obvious_intermediate.action.name == "click"
        assert obvious_intermediate.action.candidate_id == "account"
        assert obvious_intermediate.planner_provider == "semantic_intermediate_role_fast_path", (
            obvious_intermediate.model_dump(mode="json")
        )
        assert obvious_intermediate.visual_reobserve_required is False

        safe_join_entry_policy = _policy()
        safe_join_entry_policy.semantic_safe_goal_entry_fast_path_candidate = (
            lambda **_: "buy-pass-entry"
        )
        safe_join_entry_policy.semantic_intermediate_fast_path_candidate = (
            lambda **_: None
        )
        safe_join_entry_policy.semantic_destination_scroll_fast_path = (
            lambda **_: True
        )
        safe_join_entry_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "safe-join-entry-runtime.sqlite"),
            policy=safe_join_entry_policy,
        )
        safe_join_entry = safe_join_entry_runtime.decide(
            DecideRequest(
                request_id="request-safe-membership-join-entry",
                app_package="evaluation.unseen-pass.app",
                locale="ko-KR",
                goal_text="멤버십 가입",
                screen=ScreenObservation(
                    app_package="evaluation.unseen-pass.app",
                    window_title="마이페이지",
                    activity_name="android.view.View",
                    nodes=[
                        AccessibilityNodeSummary(
                            node_id="scroll-root",
                            role="container",
                            scrollable=True,
                            clickable=False,
                        ),
                        AccessibilityNodeSummary(
                            node_id="buy-pass-entry",
                            parent_id="scroll-root",
                            text="이용권을 구매하세요",
                            role="button",
                            clickable=True,
                        ),
                        AccessibilityNodeSummary(
                            node_id="settings",
                            parent_id="scroll-root",
                            text="settings",
                            role="button",
                            clickable=True,
                        ),
                        AccessibilityNodeSummary(
                            node_id="favorites-more",
                            parent_id="scroll-root",
                            text="찜 더보기",
                            role="button",
                            clickable=True,
                        ),
                    ],
                    candidates=[
                        NavigationCandidate(
                            candidate_id="buy-pass-entry",
                            label="이용권을 구매하세요",
                            icon_semantics="이용권을 구매하세요",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="settings",
                            label="settings",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="favorites-more",
                            label="찜 더보기",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert safe_join_entry.action.name == "click"
        assert safe_join_entry.action.candidate_id == "buy-pass-entry"
        assert safe_join_entry.planner_provider == "semantic_safe_goal_entry_fast_path", (
            safe_join_entry.model_dump(mode="json")
        )
        assert safe_join_entry.visual_reobserve_required is False
        assert safe_join_entry.safety_status == "allowed"
        join_loading_screen = ScreenObservation(
            app_package="evaluation.unseen-pass.app",
            window_title="멤버십",
            activity_name="android.webkit.WebView",
            candidates=[
                NavigationCandidate(
                    candidate_id="membership-area",
                    label="",
                    nearby_text="이용권 관리",
                    role="unknown",
                )
            ],
        )
        safe_join_progress = safe_join_entry_runtime.observe(
            ObserveRequest(
                request_id="request-safe-membership-join-entry-observe",
                decision_id=safe_join_entry.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=join_loading_screen,
            )
        )
        assert safe_join_progress.outcome_type == "navigated"
        assert safe_join_progress.progress_label == "advanced"
        assert safe_join_progress.navigation_progressed is True
        assert safe_join_progress.candidate_forbidden is False

        safe_join_destination = safe_join_entry_runtime.decide(
            DecideRequest(
                request_id="request-safe-membership-join-destination",
                session_id=safe_join_entry.session_id,
                step_ordinal=1,
                app_package="evaluation.unseen-pass.app",
                locale="ko-KR",
                goal_text="멤버십 가입",
                screen=ScreenObservation(
                    app_package="evaluation.unseen-pass.app",
                    window_title="멤버십",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-area",
                            label="이용권 관리",
                            nearby_text=(
                                "보유한 이용권이 없습니다. "
                                "새로운 이용권을 구독해 보세요!"
                            ),
                            role="heading",
                        ),
                        NavigationCandidate(
                            candidate_id="subscribe-pass",
                            label="이용권 구독",
                            nearby_text=(
                                "보유한 이용권이 없습니다. "
                                "새로운 이용권을 구독해 보세요!"
                            ),
                            role="button",
                            risk_level="high",
                        ),
                    ],
                ),
            )
        )
        assert safe_join_destination.action.name == "stop_for_user"
        assert safe_join_destination.planner_provider == "python_terminal_boundary"
        assert safe_join_destination.safety_status == "allowed"
        safe_join_stop = safe_join_entry_runtime.observe(
            ObserveRequest(
                request_id="request-safe-membership-join-destination-observe",
                decision_id=safe_join_destination.decision_id,
                connectivity_status="observed",
                execution_succeeded=False,
                observed_signal="blocked",
                next_screen=ScreenObservation(
                    app_package="evaluation.unseen-pass.app",
                    window_title="멤버십",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-area",
                            label="이용권 관리",
                            nearby_text=(
                                "보유한 이용권이 없습니다. "
                                "새로운 이용권을 구독해 보세요!"
                            ),
                            role="heading",
                        ),
                        NavigationCandidate(
                            candidate_id="subscribe-pass",
                            label="이용권 구독",
                            nearby_text=(
                                "보유한 이용권이 없습니다. "
                                "새로운 이용권을 구독해 보세요!"
                            ),
                            role="button",
                            risk_level="high",
                        ),
                    ],
                ),
            )
        )
        assert safe_join_stop.outcome_type == "destination_reached"
        assert safe_join_stop.progress_label == "reached"
        assert safe_join_stop.navigation_progressed is True
        assert safe_join_stop.failure_class == ""
        assert safe_join_stop.session_status == "reached"
        assert safe_join_stop.executor_action_succeeded is False

        scroll_gate_policy = _policy()
        scroll_gate_policy.exaone_vlm = Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key="",
                base_url="http://127.0.0.1:9/v1",
                model="test-exaone-4.5",
            )
        )
        scroll_gate_policy.semantic_intermediate_fast_path_candidate = (
            lambda **_: None
        )
        scroll_gate_policy.semantic_destination_scroll_fast_path = (
            lambda **_: True
        )
        scroll_gate_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "scroll-gate-runtime.sqlite"),
            policy=scroll_gate_policy,
        )
        destination_continuation = scroll_gate_runtime.decide(
            DecideRequest(
                request_id="request-destination-scroll-before-visual-gate",
                app_package="evaluation.scroll-gate.app",
                locale="ko-KR",
                goal_text="cancel subscription",
                screen=ScreenObservation(
                    app_package="evaluation.scroll-gate.app",
                    window_title="account membership",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="billing-history",
                            label="billing history",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="extra-member",
                            label="extra member",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert destination_continuation.action.name == "scroll"
        assert destination_continuation.action.direction == "down"
        assert destination_continuation.planner_provider == (
            "semantic_destination_scroll_fast_path"
        )
        assert destination_continuation.visual_reobserve_required is False

        transient_policy = _policy()
        transient_policy.exaone_vlm = Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key="",
                base_url="http://127.0.0.1:9/v1",
                model="test-exaone-4.5",
            )
        )
        transient_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "transient-nav-runtime.sqlite"),
            policy=transient_policy,
        )
        transient_screen = ScreenObservation(
            app_package="evaluation.transition.app",
            window_title="External link",
            activity_name="android.view.View",
            nodes=[
                AccessibilityNodeSummary(
                    node_id="navigate-up" if index == 0 else f"static-node-{index}",
                    text="Loading account page" if index else "",
                    clickable=index == 0,
                )
                for index in range(20)
            ],
            candidates=[
                NavigationCandidate(
                    candidate_id="navigate-up",
                    label="",
                    role="icon_button",
                    icon_semantics="Navigate up",
                    position_bucket="top",
                )
            ],
        )
        first_transient = transient_runtime.decide(
            DecideRequest(
                request_id="request-transient-nav-1",
                app_package="evaluation.transition.app",
                goal_text="cancel subscription",
                screen=transient_screen,
            )
        )
        assert first_transient.action.name == "wait_and_observe"
        assert first_transient.planner_provider == "python_visual_reobserve_gate"
        assert first_transient.visual_reobserve_required is True
        transient_runtime.observe(
            ObserveRequest(
                request_id="request-transient-nav-observe-1",
                decision_id=first_transient.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=transient_screen,
            )
        )
        second_transient = transient_runtime.decide(
            DecideRequest(
                request_id="request-transient-nav-2",
                session_id=first_transient.session_id,
                step_ordinal=1,
                app_package="evaluation.transition.app",
                goal_text="cancel subscription",
                visual_reasoning_required=True,
                screen=transient_screen,
            )
        )
        assert second_transient.action.name == "wait_and_observe"
        assert second_transient.planner_provider == "python_transient_navigation_wait_gate"
        transient_runtime.observe(
            ObserveRequest(
                request_id="request-transient-nav-observe-2",
                decision_id=second_transient.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=transient_screen,
            )
        )
        stalled_transient = transient_runtime.decide(
            DecideRequest(
                request_id="request-transient-nav-3",
                session_id=first_transient.session_id,
                step_ordinal=2,
                app_package="evaluation.transition.app",
                goal_text="cancel subscription",
                screen=transient_screen,
            )
        )
        assert stalled_transient.action.name == "stop_for_user"
        assert stalled_transient.planner_provider == "python_transient_navigation_stall_guard"

        execution_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "execution-failure-runtime.sqlite"),
            policy=_policy(),
        )
        not_executed = execution_runtime.decide(
            DecideRequest(
                request_id="request-not-executed",
                app_package="evaluation.execution.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=_account_screen(),
            )
        )
        assert not_executed.action.name == "click"
        not_executed_observation = execution_runtime.observe(
            ObserveRequest(
                request_id="request-not-executed-observe",
                decision_id=not_executed.decision_id,
                connectivity_status="observed",
                execution_succeeded=False,
                observed_signal="blocked",
                next_screen=ScreenObservation(
                    window_title="런처",
                    activity_name="com.android.launcher",
                    candidates=[],
                ),
            )
        )
        assert not_executed_observation.outcome_type == "blocked"
        assert not_executed_observation.failure_class == "executor_action_not_executed"
        assert not_executed_observation.planner_decision_succeeded is True
        assert not_executed_observation.executor_action_succeeded is False
        assert not_executed_observation.connection_error is False
        assert not_executed_observation.candidate_forbidden is False
        assert not_executed_observation.knowledge_revision_queued is False
        assert not_executed_observation.session_status == "stopped"

        dangerous = runtime.decide(
            DecideRequest(
                request_id="request-3",
                app_package="evaluation.another.app",
                goal_text="멤버십을 해지하고 싶어",
                screen=ScreenObservation(
                    window_title="멤버십 결제 해지",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="confirm-cancel",
                            label="해지 확정",
                            role="button",
                            risk_level="high",
                        )
                    ],
                ),
            )
        )
        assert dangerous.action.name == "stop_for_user"

        exact_cancel_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "exact-cancel-runtime.sqlite"),
            policy=_policy(),
        )
        exact_cancel_boundary = exact_cancel_runtime.decide(
            DecideRequest(
                request_id="request-exact-membership-cancel-boundary",
                app_package="evaluation.exact-cancel.app",
                goal_text="멤버십을 해지하고 싶어",
                screen=ScreenObservation(
                    window_title="계정 멤버십",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-cancel",
                            label="멤버십 해지",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert exact_cancel_boundary.action.name == "stop_for_user"
        assert exact_cancel_boundary.planner_provider in {
            "python_state_change_boundary",
            "python_terminal_boundary",
        }
        assert exact_cancel_boundary.candidate_values[0].score_source == "safety_blocked"
        assert exact_cancel_boundary.candidate_values[0].final_score == 0.0
        assert exact_cancel_boundary.safety_status == "allowed"

        safety_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "state-change-runtime.sqlite"),
            policy=_policy(),
        )
        state_changing = safety_runtime.decide(
            DecideRequest(
                request_id="request-state-change",
                app_package="evaluation.another.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=ScreenObservation(
                    window_title="계정 설정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="logout",
                            label="로그아웃",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert state_changing.action.name == "stop_for_user"

        save_boundary = safety_runtime.decide(
            DecideRequest(
                request_id="request-save-boundary",
                app_package="evaluation.another.app",
                goal_text="멤버십 해지 메뉴를 찾고 싶어",
                screen=ScreenObservation(
                    window_title="프로필 수정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="save",
                            label="저장하기",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert save_boundary.action.name == "stop_for_user"
        assert save_boundary.planner_provider == "python_state_change_boundary"

        logged_out = safety_runtime.decide(
            DecideRequest(
                request_id="request-auth-boundary",
                app_package="evaluation.another.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=ScreenObservation(
                    window_title="전체 메뉴",
                    activity_name="androidx.drawerlayout.widget.DrawerLayout",
                    candidates=[
                        NavigationCandidate(candidate_id="signup", label="회원가입", role="button"),
                        NavigationCandidate(candidate_id="login", label="로그인", role="button"),
                        NavigationCandidate(candidate_id="my-page", label="마이페이지", role="button"),
                    ],
                ),
            )
        )
        assert logged_out.action.name == "stop_for_user"
        assert logged_out.planner_provider == "python_authentication_boundary"
        assert logged_out.perception_provider == "structured_input_auth_boundary"
        logged_out_observation = safety_runtime.observe(
            ObserveRequest(
                request_id="request-auth-boundary-observe",
                decision_id=logged_out.decision_id,
                connectivity_status="observed",
                execution_succeeded=False,
                observed_signal="blocked",
                next_screen=ScreenObservation(
                    window_title="전체 메뉴",
                    activity_name="androidx.drawerlayout.widget.DrawerLayout",
                    candidates=[
                        NavigationCandidate(candidate_id="signup", label="회원가입", role="button"),
                        NavigationCandidate(candidate_id="login", label="로그인", role="button"),
                        NavigationCandidate(candidate_id="my-page", label="마이페이지", role="button"),
                    ],
                ),
            )
        )
        assert logged_out_observation.outcome_type == "login_required"
        assert safety_runtime.store.session(logged_out.session_id)["status"] == "stopped"

        auth_transition_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "auth-transition-runtime.sqlite"),
            policy=_policy(),
        )
        auth_entry = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-auth-entry",
                app_package="evaluation.auth.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=_account_screen(),
            )
        )
        auth_observation = auth_transition_runtime.observe(
            ObserveRequest(
                request_id="request-auth-observe",
                decision_id=auth_entry.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=ScreenObservation(
                    window_title="로그인",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(candidate_id="signup", label="회원가입", role="button"),
                        NavigationCandidate(candidate_id="login", label="로그인", role="button"),
                    ],
                ),
            )
        )
        assert auth_observation.outcome_type == "login_required"
        assert auth_observation.recovery_action is not None
        assert auth_observation.recovery_action.name == "stop_for_user"
        assert auth_observation.session_status == "stopped"

        signup_terminal = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-signup-terminal",
                app_package="evaluation.auth.app",
                goal_text="새 계정을 만들고 싶어",
                screen=ScreenObservation(
                    window_title="회원가입",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(candidate_id="email", label="이메일", role="input"),
                        NavigationCandidate(candidate_id="password", label="비밀번호", role="input"),
                        NavigationCandidate(candidate_id="create", label="가입하기", role="button"),
                    ],
                ),
            )
        )
        assert signup_terminal.action.name == "stop_for_user"
        assert signup_terminal.planner_provider == "python_terminal_boundary"
        assert signup_terminal.perception_provider == "structured_input_terminal_boundary"

        already_member = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-already-member",
                app_package="evaluation.membership.app",
                goal_text="유료 멤버십에 가입하고 싶어",
                screen=ScreenObservation(
                    window_title="계정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-status",
                            label="WOW! 혜택 이용중",
                            role="text",
                        ),
                        NavigationCandidate(
                            candidate_id="benefits",
                            label="총 312,717원 절약했어요",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert already_member.action.name == "stop_for_user"
        assert already_member.planner_provider == "python_goal_already_satisfied"
        already_member_observation = auth_transition_runtime.observe(
            ObserveRequest(
                request_id="request-already-member-observe",
                decision_id=already_member.decision_id,
                connectivity_status="observed",
                execution_succeeded=False,
                next_screen=ScreenObservation(
                    window_title="계정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-status",
                            label="Premium 회원",
                            role="text",
                        ),
                        NavigationCandidate(
                            candidate_id="benefits",
                            label="Premium 혜택",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert already_member_observation.outcome_type == "blocked"
        assert already_member_observation.failure_class == "already_satisfied"
        assert already_member_observation.candidate_forbidden is False
        assert already_member_observation.session_status == "stopped"

        already_member_after_click = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-member-after-click",
                app_package="evaluation.membership.app",
                goal_text="유료 멤버십에 가입하고 싶어",
                screen=ScreenObservation(
                    window_title="홈",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="my-page",
                            label="내 페이지",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert already_member_after_click.action.name == "click"
        already_member_after_click_observation = auth_transition_runtime.observe(
            ObserveRequest(
                request_id="request-member-after-click-observe",
                decision_id=already_member_after_click.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=ScreenObservation(
                    window_title="계정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-status",
                            label="Premium 회원",
                            role="text",
                        ),
                        NavigationCandidate(
                            candidate_id="benefits",
                            label="Premium 혜택",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert already_member_after_click_observation.outcome_type == "blocked"
        assert already_member_after_click_observation.progress_label == "advanced"
        assert already_member_after_click_observation.failure_class == "already_satisfied"
        assert already_member_after_click_observation.candidate_forbidden is False
        assert already_member_after_click_observation.knowledge_revision_queued is False
        assert already_member_after_click_observation.session_status == "stopped"

        out_of_scope = runtime.decide(
            DecideRequest(
                request_id="request-4",
                app_package="evaluation.another.app",
                goal_text="오늘 날씨를 알려줘",
                screen=_account_screen(),
            )
        )
        assert out_of_scope.goal.status == "out_of_scope"
        assert out_of_scope.action.name == "stop_for_user"

        try:
            NavigationCandidate(candidate_id="bad", label="버튼", x=100, y=200)
        except ValidationError:
            pass
        else:
            raise AssertionError("coordinate fields were accepted")

        split_manifest = NavigationDatasetSplitManifest.load(
            ROOT / "db" / "navigation_dataset_split_v1.json"
        )
        split_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "split-runtime.sqlite"),
            policy=_policy(),
            dataset_split_manifest=split_manifest,
        )
        split_status = split_runtime.status()["dataset_split"]
        assert split_status["counts"]["locked_holdout"] == 3
        assert split_status["counts"]["validation"] == 3
        tving = split_manifest.entry_for("net.cj.cjhv.gs.tving")
        assert tving is not None
        assert tving.split == "validation"
        assert tving.existing_decision_cases == 0
        assert split_runtime.store.status()["schema_version"] == 4
        assert len(split_runtime.store.dataset_split_manifest()) == len(split_manifest.entries)
        try:
            split_runtime.decide(
                DecideRequest(
                    request_id="holdout-denied",
                    app_package="com.instagram.android",
                    goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                    screen=_account_screen(),
                )
            )
        except DatasetSplitAccessError:
            pass
        else:
            raise AssertionError("locked holdout app was accepted during collection")

        legacy_runtime_path = temporary_path / "legacy-runtime-v2.sqlite"
        legacy_store = NavigationRuntimeStore(legacy_runtime_path)
        legacy_store.upsert_session(
            session_id="legacy-session",
            request_id="legacy-request",
            app_package="legacy.app",
            app_version="1.0.0",
            locale="ko-KR",
            goal_text="회원 탈퇴",
            goal_id="account.delete",
        )
        connection = sqlite3.connect(legacy_runtime_path)
        try:
            connection.execute("DROP TABLE navigation_dataset_split_manifest")
            connection.execute(
                "UPDATE navigation_runtime_metadata SET value='2' WHERE key='schema_version'"
            )
            connection.execute(
                "DELETE FROM navigation_runtime_metadata WHERE key LIKE 'dataset_split_manifest_%'"
            )
            connection.execute("ALTER TABLE navigation_sessions DROP COLUMN app_version")
            connection.execute("PRAGMA user_version=2")
            connection.commit()
        finally:
            connection.close()
        upgraded_store = NavigationRuntimeStore(legacy_runtime_path)
        assert upgraded_store.status()["schema_version"] == 4
        upgraded_session = upgraded_store.session("legacy-session")
        assert upgraded_session is not None
        assert upgraded_session["app_version"] == ""

        previous = {key: os.environ.get(key) for key in (
            "NAVIGATION_DECISION_DB_PATH",
            "NAVIGATION_RUNTIME_DB_PATH",
            "NAVIGATION_DATASET_SPLIT_MANIFEST_PATH",
            "NAVIGATION_ALLOW_LOCKED_HOLDOUT",
        )}
        os.environ["NAVIGATION_DECISION_DB_PATH"] = str(decision_db)
        os.environ["NAVIGATION_RUNTIME_DB_PATH"] = str(temporary_path / "api-runtime.sqlite")
        os.environ["NAVIGATION_DATASET_SPLIT_MANIFEST_PATH"] = str(
            ROOT / "db" / "navigation_dataset_split_v1.json"
        )
        os.environ["NAVIGATION_ALLOW_LOCKED_HOLDOUT"] = "false"
        get_settings.cache_clear()
        from app import navigation_main  # noqa: E402

        navigation_main.get_navigation_runtime.cache_clear()
        with TestClient(navigation_main.app) as client:
            assert client.get("/health").status_code == 200
            status = client.get("/v1/navigation/status")
            assert status.status_code == 200 and status.json()["ready"] is True
            assert status.json()["research_models_ready"] is False
            assert status.json()["serving_mode"] == "decision_memory_fallback"
            assert status.json()["research_model_blockers"] == [
                "planner_model_endpoint_or_credentials_missing",
                "exaone_4_5_endpoint_or_credentials_missing",
            ]
            assert (
                status.json()["planner"]["structured_output"]
                == "hermes_tools_without_direct_action_execution"
            )
            split_response = client.get("/v1/navigation/dataset-splits")
            assert split_response.status_code == 200
            assert split_response.json()["policy"]["counts"]["locked_holdout"] == 3
            api_decision = client.post(
                "/v1/navigation/decide",
                json={
                    "request_id": "api-request",
                    "app_package": "com.coupang.mobile",
                    "goal_text": "회원 탈퇴",
                    "screen": _account_screen().model_dump(mode="json"),
                },
            )
            assert api_decision.status_code == 200
            assert api_decision.json()["action"]["candidate_id"] == "profile"
            holdout_decision = client.post(
                "/v1/navigation/decide",
                json={
                    "request_id": "api-holdout-denied",
                    "app_package": "com.openai.chatgpt",
                    "goal_text": "회원 탈퇴",
                    "screen": _account_screen().model_dump(mode="json"),
                },
            )
            assert holdout_decision.status_code == 403
            repeated_decision = client.post(
                "/v1/navigation/decide",
                json=json.loads(api_decision.request.content.decode("utf-8")),
            )
            assert repeated_decision.status_code == 200
            assert repeated_decision.json()["decision_id"] == api_decision.json()["decision_id"]
            api_observe_payload = {
                "request_id": "api-observe-request",
                "decision_id": api_decision.json()["decision_id"],
                "connectivity_status": "observed",
                "execution_succeeded": True,
                "next_screen": _account_screen().model_dump(mode="json"),
            }
            api_observation = client.post("/v1/navigation/observe", json=api_observe_payload)
            assert api_observation.status_code == 200
            repeated_observation = client.post(
                "/v1/navigation/observe", json=api_observe_payload
            )
            assert repeated_observation.status_code == 200
            assert repeated_observation.json() == api_observation.json()
            stop_response = client.post(
                f"/v1/navigation/sessions/{api_decision.json()['session_id']}/stop"
            )
            assert stop_response.status_code == 200
            assert stop_response.json()["status"] == "stopped"
            repeated_stop = client.post(
                f"/v1/navigation/sessions/{api_decision.json()['session_id']}/stop"
            )
            assert repeated_stop.status_code == 200
            assert repeated_stop.json() == stop_response.json()
            assert client.post("/v1/navigation/sessions/missing/stop").status_code == 404
            api_episode = client.get(
                f"/v1/navigation/sessions/{api_decision.json()['session_id']}/episode"
            )
            assert api_episode.status_code == 200
            assert api_episode.json()["candidate_set_status"] == "complete"
            assert len(api_episode.json()["steps"][0]["screen"]["before"]["candidates"]) == 2
            assert len(api_episode.json()["steps"][0]["screen"]["after"]["candidates"]) == 2
        navigation_main.get_navigation_runtime.cache_clear()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

        runtime_status = runtime.store.status()
        assert runtime_status["decisions"] == 4
        assert runtime_status["observations"] == 2
        assert runtime_status["screen_snapshots"] == 5
        assert runtime_status["screen_candidates"] == 9
        assert runtime_status["complete_steps"] == 2
        assert runtime_status["pending_knowledge_revisions"] == 1
        episode = runtime.store.interaction_episode(first.session_id)
        assert episode["candidate_set_status"] == "complete"
        assert len(episode["steps"]) == 2
        assert len(episode["steps"][0]["screen"]["before"]["candidates"]) == 2
        assert len(episode["steps"][0]["screen"]["after"]["candidates"]) == 2
        selected = [
            item
            for item in episode["steps"][0]["screen"]["before"]["candidates"]
            if item["selected"]
        ]
        assert [item["candidate_id"] for item in selected] == ["profile"]
        assert episode["steps"][1]["connectivity_status"] == "transport_error"
        assert "after" not in episode["steps"][1]["screen"]

        privacy_runtime_db = temporary_path / "privacy-runtime.sqlite"
        privacy_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(privacy_runtime_db),
            policy=_policy(),
        )
        privacy_runtime.decide(
            DecideRequest(
                request_id="request-contextual-profile-privacy",
                app_package="evaluation.profile-context.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=ScreenObservation(
                    window_title="프로필",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="profile-id",
                            label="carson0306",
                            role="button",
                            nearby_text="프로필을 변경 또는 관리하세요. carson0306",
                            parent_semantics="carson0306",
                        ),
                        NavigationCandidate(
                            candidate_id="account",
                            label="계정",
                            role="button",
                            parent_semantics="carson0306",
                        ),
                    ],
                ),
            )
        )
        privacy_connection = sqlite3.connect(privacy_runtime_db)
        stored_screen = str(
            privacy_connection.execute(
                "SELECT screen_payload_json FROM navigation_decisions LIMIT 1"
            ).fetchone()[0]
        )
        stored_candidates = " ".join(
            str(row[0])
            for row in privacy_connection.execute(
                "SELECT observed_payload_json FROM navigation_screen_candidates"
            )
        )
        privacy_connection.close()
        assert "carson0306" not in stored_screen
        assert "[account]" in stored_screen
        assert "carson0306" not in stored_candidates
        assert "[account]" in stored_candidates
    print("navigation_runtime_unit: ok")


if __name__ == "__main__":
    main()
