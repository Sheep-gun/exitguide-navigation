from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.navigation_contracts import (  # noqa: E402
    AccessibilityNodeSummary,
    CandidateValue,
    DecideRequest,
    HierarchicalPlan,
    NavigationAction,
    NavigationCandidate,
    ObserveRequest,
    ScreenObservation,
)
from app.services.navigation_decision_memory import (  # noqa: E402
    CandidateMemoryConfidence,
    DecisionMemoryQuery,
    NavigationDecisionMemory,
    NormalizedGoal,
    SemanticScreenState,
)
from app.services.navigation_model_clients import (  # noqa: E402
    Exaone45VisionClient,
    NavigationPlannerResearchClient,
)
from app.services.navigation_planner import (  # noqa: E402
    ActionSafetyGate,
    CandidateValueScorer,
    PlannerProposal,
)
from app.services.navigation_research_policy import (  # noqa: E402
    AndroidWorldResearchPolicy,
    EnumeratedAction,
    ReflectionTriggerPolicy,
)
from app.services.navigation_runtime import (  # noqa: E402
    NavigationRuntime,
    _candidate_score_visual_reason,
    _db_solar_conflict_visual_reason,
)
from app.services.navigation_runtime_store import NavigationRuntimeStore  # noqa: E402


def _response(payload: dict[str, object]) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}


def _tool_response(name: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(payload, ensure_ascii=False),
                            },
                        }
                    ],
                }
            }
        ]
    }


class ScriptedPlannerClient:
    configured = True

    def __init__(self, *, fail_first_step_evaluation: bool = False) -> None:
        self.plan_calls = 0
        self.verifier_actions: list[str] = []
        self.fail_first_step_evaluation = fail_first_step_evaluation

    def complete(self, *, messages, **_kwargs):
        system = str(messages[0]["content"])
        if "Goal Ontology classifier" in system:
            assert _kwargs["tools"][0]["function"]["name"] == "select_navigation_goal"
            allowed = _kwargs["tools"][0]["function"]["parameters"]["properties"]["goal_id"]["enum"]
            assert "account.delete" in allowed
            return _tool_response(
                "select_navigation_goal",
                {
                    "goal_id": "account.delete",
                    "confidence": 0.99,
                    "reason": "scripted exact goal classification",
                },
            )
        if "combined K2-style planner and V-Droid-style batch verifier" in system:
            assert _kwargs["max_tokens"] == 2_000
            assert (
                _kwargs["tools"][0]["function"]["name"]
                == "submit_navigation_step_evaluation"
            )
            parameters = _kwargs["tools"][0]["function"]["parameters"]
            packet = json.loads(messages[1]["content"])
            expected_keys = [item["action_key"] for item in packet["candidate_actions"]]
            assert parameters["properties"]["best_action_key"]["enum"] == expected_keys
            score_schema = parameters["properties"]["scores"]
            assert score_schema["minItems"] == len(expected_keys)
            assert score_schema["maxItems"] == len(expected_keys)
            assert score_schema["items"]["properties"]["action_key"]["enum"] == expected_keys
            self.plan_calls += 1
            if self.fail_first_step_evaluation and self.plan_calls == 1:
                return _tool_response(
                    "submit_navigation_step_evaluation",
                    {
                        "stage": "hub_discovery",
                        "immediate_subgoal": "open account hub",
                        "expected_outcome": "account entries appear",
                        "target_roles": ["account_hub"],
                        "best_action_key": "click:profile",
                        "scores": [],
                    },
                )
            assert "app_package" not in packet
            scores = {
                "click:profile": 0.93,
                "click:search": 0.04,
                "scroll:down": 0.12,
                "wait_and_observe": 0.08,
                "stop_for_user": 0.02,
            }
            output_scores = []
            for item in packet["candidate_actions"]:
                key = item["action_key"]
                self.verifier_actions.append(key)
                output_scores.append(
                    {
                        "action_key": key,
                        "helpful_probability": scores[key],
                        "expected_progress": "account hub" if key == "click:profile" else "unlikely",
                        "reason": f"scripted score for {key}",
                    }
                )
            return _tool_response(
                "submit_navigation_step_evaluation",
                {
                    "stage": "hub_discovery",
                    "immediate_subgoal": "open the account or profile hub",
                    "expected_outcome": "account management entries become visible",
                    "target_roles": ["account_hub", "profile_hub"],
                    "best_action_key": "click:profile",
                    "scores": output_scores,
                },
            )
        if "high-level planner" in system:
            assert _kwargs["tools"][0]["function"]["name"] == "submit_navigation_subgoal"
            self.plan_calls += 1
            assert "Do not choose an action" in system
            packet = json.loads(messages[1]["content"])
            assert "app_package" not in packet
            return _tool_response(
                "submit_navigation_subgoal",
                {
                    "stage": "hub_discovery",
                    "immediate_subgoal": "계정 또는 프로필 허브를 연다",
                    "expected_outcome": "계정 관리 메뉴가 보이는 화면",
                    "target_roles": ["account_hub", "profile_hub"],
                }
            )
        if "V-Droid-style batch verifier" in system:
            assert _kwargs["tools"][0]["function"]["name"] == "score_navigation_candidates"
            packet = json.loads(messages[1]["content"])
            scores = {
                "click:profile": 0.93,
                "click:search": 0.04,
                "scroll:down": 0.12,
                "wait_and_observe": 0.08,
                "stop_for_user": 0.02,
            }
            output_scores = []
            for item in packet["candidate_actions"]:
                key = item["action_key"]
                self.verifier_actions.append(key)
                output_scores.append(
                    {
                        "action_key": key,
                        "helpful_probability": scores[key],
                        "expected_progress": "account hub" if key == "click:profile" else "unlikely",
                        "reason": f"scripted score for {key}",
                    }
                )
            return _tool_response(
                "score_navigation_candidates",
                {"scores": output_scores},
            )
        if "trajectory reflector" in system:
            return _response(
                {"outcome": "failed", "reason": "repeat loop", "recovery_hint": "back"}
            )
        if "global completion reflector" in system:
            return _response(
                {"outcome": "met", "reason": "signature met", "recovery_hint": "stop_for_user"}
            )
        raise AssertionError(system)


class ScriptedVisionClient:
    configured = True

    def __init__(self) -> None:
        self.perception_calls = 0
        self.reflection_calls = 0

    def complete(self, *, messages, **_kwargs):
        system = str(messages[0]["content"])
        if "visual perception module" in system:
            assert _kwargs["temperature"] == 0.0
            assert _kwargs["top_p"] == 1.0
            assert _kwargs["presence_penalty"] == 0.0
            assert _kwargs["tool_choice"] == {
                "type": "function",
                "function": {"name": "annotate_navigation_screen"},
            }
            candidate_enum = _kwargs["tools"][0]["function"]["parameters"][
                "properties"
            ]["recommended_candidate_id"]["enum"]
            assert candidate_enum == ["profile", "search", None]
            self.perception_calls += 1
            return _tool_response(
                "annotate_navigation_screen",
                {
                    "semantic_summary": "홈 하단에 계정 진입점이 있는 화면",
                    "candidate_annotations": [
                        {
                            "candidate_id": "profile",
                            "icon_semantics": "사람 모양 프로필",
                            "visual_role": "계정 프로필 허브",
                            "visual_region": "하단 탐색 영역",
                            "goal_relevance": 0.91,
                        },
                        {"candidate_id": "invented-id", "icon_semantics": "환각 후보"},
                    ],
                    "recommended_candidate_id": "profile",
                },
            )
        if "on-demand action reflector" in system:
            self.reflection_calls += 1
            return _response(
                {"outcome": "failed", "reason": "화면이 바뀌지 않음", "recovery_hint": "back"}
            )
        raise AssertionError(system)


def _load_migration_module():
    path = ROOT / "scripts" / "Migrate-NavigationDecisionDb.py"
    spec = importlib.util.spec_from_file_location("navigation_research_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_decision_db(path: Path) -> None:
    migration = _load_migration_module()
    connection = sqlite3.connect(path)
    connection.executescript((ROOT / "db" / "navigation_decision_v1.sql").read_text(encoding="utf-8"))
    migration.seed_database(connection, "b" * 64)
    connection.commit()
    connection.close()


def _screen() -> ScreenObservation:
    return ScreenObservation(
        window_title="홈",
        activity_name="android.view.View",
        candidates=[
            NavigationCandidate(candidate_id="profile", label="마이페이지", role="button"),
            NavigationCandidate(candidate_id="search", label="검색", role="button"),
        ],
    )


def main() -> None:
    planner_transport = ScriptedPlannerClient()
    vision_transport = ScriptedVisionClient()
    planner_model = NavigationPlannerResearchClient(
        planner_transport,
        provider_name="solar_pro3",
    )
    exaone_vlm = Exaone45VisionClient(vision_transport)
    policy = AndroidWorldResearchPolicy(
        planner_model=planner_model,
        exaone_vlm=exaone_vlm,
        allow_model_fallback=False,
        planner_mode="always",
        vlm_mode="always",
    )

    perceived = exaone_vlm.perceive(
        goal_text="회원 탈퇴 메뉴 찾기",
        screen=_screen(),
        screenshot_data_url="data:image/png;base64,AA==",
    )
    assert [item.candidate_id for item in perceived.screen.candidates] == ["profile", "search"]
    assert perceived.screen.candidates[0].icon_semantics == "사람 모양 프로필"
    assert perceived.screen.candidates[0].visual_role == "계정 프로필 허브"
    assert perceived.screen.candidates[0].visual_relevance == 0.91
    assert perceived.recommended_candidate_id == "profile"

    grounded_screen = ScreenObservation(
        window_title="홈",
        nodes=[
            AccessibilityNodeSummary(
                node_id="profile",
                child_ids=["search"],
                text="프로필",
                clickable=True,
            ),
            AccessibilityNodeSummary(
                node_id="search", parent_id="profile", text="검색", clickable=True
            ),
        ],
        candidates=list(_screen().candidates),
    )
    assert grounded_screen.nodes[1].parent_id == "profile"
    try:
        ScreenObservation(
            nodes=[AccessibilityNodeSummary(node_id="profile")],
            candidates=[NavigationCandidate(candidate_id="invented", label="환각")],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("ungrounded candidate_id must be rejected")

    selective_visual_policy = AndroidWorldResearchPolicy(
        planner_model=planner_model,
        exaone_vlm=exaone_vlm,
        allow_model_fallback=False,
        planner_mode="selective",
        vlm_mode="selective",
    )
    visual_calls_before = vision_transport.perception_calls
    clear_perception = selective_visual_policy.perceive(
        goal_text="open account settings",
        screen=_screen(),
        screenshot_data_url="data:image/png;base64,AA==",
    )
    assert clear_perception.provider == "structured_input"
    assert vision_transport.perception_calls == visual_calls_before
    forced_perception = selective_visual_policy.perceive(
        goal_text="open account settings",
        screen=_screen(),
        screenshot_data_url="data:image/png;base64,AA==",
        force_visual_reasoning=True,
    )
    assert forced_perception.provider == "exaone_4_5"
    assert vision_transport.perception_calls == visual_calls_before + 1

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        decision_db = root / "decision.sqlite"
        _build_decision_db(decision_db)
        runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(root / "runtime.sqlite"),
            policy=policy,
        )
        decision = runtime.decide(
            DecideRequest(
                request_id="research-1",
                app_package="heldout.app",
                goal_text="회원 탈퇴 메뉴를 찾아줘",
                screenshot_data_url="data:image/png;base64,AA==",
                screen=_screen(),
            )
        )
        assert decision.plan.source == "solar_pro3"
        assert decision.action.name == "click" and decision.action.candidate_id == "profile"
        assert decision.perception_provider == "exaone_4_5"
        assert decision.verifier_provider == "solar_pro3_step_evaluator"
        assert planner_transport.plan_calls == 1
        assert sorted(planner_transport.verifier_actions) == sorted(
            ["click:profile", "click:search", "scroll:down", "wait_and_observe", "stop_for_user"]
        )

        retry_transport = ScriptedPlannerClient(fail_first_step_evaluation=True)
        retry_policy = AndroidWorldResearchPolicy(
            planner_model=NavigationPlannerResearchClient(
                retry_transport,
                provider_name="solar_pro3",
            ),
            exaone_vlm=exaone_vlm,
            allow_model_fallback=False,
            planner_mode="always",
            vlm_mode="disabled",
        )
        retry_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(root / "retry-runtime.sqlite"),
            policy=retry_policy,
        )
        retried = retry_runtime.decide(
            DecideRequest(
                request_id="research-retry-1",
                app_package="heldout.retry.app",
                goal_text="회원 탈퇴 메뉴를 찾아줘",
                screen=_screen(),
            )
        )
        assert retried.action.name == "click" and retried.action.candidate_id == "profile"
        assert retry_transport.plan_calls == 2

        observation = runtime.observe(
            ObserveRequest(
                request_id="research-observe-1",
                decision_id=decision.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                before_screenshot_data_url="data:image/png;base64,AA==",
                after_screenshot_data_url="data:image/png;base64,AA==",
                next_screen=_screen(),
            )
        )
        assert observation.reflection_level == "action"
        assert vision_transport.reflection_calls == 1
        assert observation.recovery_action is not None
        assert observation.recovery_action.name == "back"
        assert observation.knowledge_revision_queued is True

    trigger = ReflectionTriggerPolicy()
    level, _ = trigger.choose_level(
        outcome_type="navigated",
        execution_succeeded=True,
        action_confidence=0.9,
        reflection_on_demand=False,
        action_name="click",
        recent_history=[
            {"action_name": "click", "screen_fingerprint": "same", "progress_label": "advanced"},
            {"action_name": "click", "screen_fingerprint": "same", "progress_label": "unknown"},
        ],
    )
    assert level == "trajectory"
    level, _ = trigger.choose_level(
        outcome_type="navigated",
        execution_succeeded=True,
        action_confidence=0.9,
        reflection_on_demand=False,
        action_name="click",
        recent_history=[
            {
                "action_name": "click",
                "candidate_id": "profile",
                "screen_fingerprint": "screen-a",
                "progress_label": "advanced",
            },
            {
                "action_name": "click",
                "candidate_id": "menu",
                "screen_fingerprint": "screen-b",
                "progress_label": "unknown",
            },
        ],
    )
    assert level == "none"
    level, _ = trigger.choose_level(
        outcome_type="navigated",
        execution_succeeded=True,
        action_confidence=0.9,
        reflection_on_demand=False,
        action_name="click",
        recent_history=[
            {"screen_fingerprint": "screen-a", "progress_label": "unknown"},
            {"screen_fingerprint": "screen-b", "progress_label": "unknown"},
            {"screen_fingerprint": "screen-a", "progress_label": "unknown"},
        ],
    )
    assert level == "trajectory"
    level, _ = trigger.choose_level(
        outcome_type="destination_reached",
        execution_succeeded=True,
        action_confidence=0.9,
        reflection_on_demand=False,
        action_name="click",
        recent_history=[],
    )
    assert level == "global"

    high_confidence_values = [
        CandidateValue(
            candidate_id="signup",
            value=0.94,
            memory_score=0.74,
            role_score=1.0,
            final_score=0.94,
            fast_path_eligible=True,
            forbidden=False,
            risk_level="low",
        ),
        CandidateValue(
            candidate_id="login",
            value=0.68,
            memory_score=0.58,
            role_score=0.78,
            final_score=0.68,
            forbidden=False,
            risk_level="low",
        ),
    ]
    fast_path_plan = HierarchicalPlan(
        goal_id="account.signup",
        stage="destination_entry",
        target_roles=["auth.signup.entry"],
        immediate_subgoal="open sign up",
        expected_outcome="registration screen appears",
        completion_rule="choose a safe direct entry",
        source="decision_memory_fallback",
    )
    selective_policy = AndroidWorldResearchPolicy(
        planner_model=planner_model,
        exaone_vlm=exaone_vlm,
        allow_model_fallback=False,
        planner_mode="selective",
    )
    fast_path_query = DecisionMemoryQuery(
        goal=None,
        screen=SemanticScreenState(
            semantic_fingerprint="screen-a",
            title="account",
            auth_state="unknown",
            surface_type="native",
            navigation_depth=None,
            tokens=(),
            candidate_payloads=(),
        ),
        destination_signatures=(),
        evidence=(),
        candidate_scores={"signup": 0.94, "login": 0.68},
        candidate_confidence={
            "signup": CandidateMemoryConfidence(
                candidate_id="signup",
                score=0.94,
                support_tier="high",
                supporting_cases=4,
                supporting_apps=3,
                conflicting_cases=0,
                provenance_quality=0.95,
                fast_path_eligible=True,
                reasons=("cross-app observed support",),
            ),
            "login": CandidateMemoryConfidence(
                candidate_id="login",
                score=0.68,
                support_tier="medium",
                supporting_cases=2,
                supporting_apps=1,
                conflicting_cases=0,
                provenance_quality=0.8,
                fast_path_eligible=False,
                reasons=("insufficient app diversity",),
            ),
        },
        action_scores={},
        destination_match=0.0,
        standards_profile="exitguide.navigation-experience.v1",
    )
    selected_value = CandidateValueScorer().score(
        fast_path_query,
        [
            NavigationCandidate(
                candidate_id="signup",
                label="회원가입",
                role="tab",
                position_bucket="middle",
                risk_level="low",
                selected=True,
            )
        ],
        forbidden_candidate_ids=set(),
    )[0]
    assert selected_value.value == 0.235
    assert selected_value.fast_path_eligible is False
    assert "already_selected_state" in selected_value.confidence_reasons
    conflict_query = DecisionMemoryQuery(
        goal=NormalizedGoal(
            goal_id="membership.cancel",
            family="membership",
            operation="cancel",
            confidence=1.0,
            matched_phrase="cancel membership",
            terminal_action_policy="stop_before_final_confirmation",
        ),
        screen=SemanticScreenState(
            semantic_fingerprint="video-screen",
            title="video playback",
            auth_state="logged_in",
            surface_type="native",
            navigation_depth=None,
            tokens=("my page",),
            candidate_payloads=(
                {
                    "candidate_id": "my-page",
                    "label": "My page",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "function_role_scores": {"account.hub": 1.0},
                },
            ),
        ),
        destination_signatures=(),
        evidence=(),
        candidate_scores={"my-page": 0.0},
        candidate_confidence={
            "my-page": CandidateMemoryConfidence(
                candidate_id="my-page",
                score=0.0,
                support_tier="ontology_only",
                supporting_cases=0,
                supporting_apps=0,
                conflicting_cases=1,
                provenance_quality=0.0,
                fast_path_eligible=False,
                reasons=("conflicting_cases=1",),
            )
        },
        action_scores={},
        destination_match=0.0,
        standards_profile="exitguide.navigation-experience.v1",
    )
    conflicted_value = CandidateValueScorer().score(
        conflict_query,
        [
            NavigationCandidate(
                candidate_id="my-page",
                label="My page",
                role="button",
                risk_level="low",
            )
        ],
        forbidden_candidate_ids=set(),
    )[0]
    assert conflicted_value.value == 0.0
    mixed_conflict_query = replace(
        conflict_query,
        candidate_scores={"my-page": 0.3825},
        candidate_confidence={
            "my-page": replace(
                conflict_query.candidate_confidence["my-page"],
                score=0.3825,
                support_tier="cross_app_verified",
                supporting_cases=2,
                supporting_apps=2,
                conflicting_cases=3,
            )
        },
    )
    mixed_conflicted_value = CandidateValueScorer().score(
        mixed_conflict_query,
        [
            NavigationCandidate(
                candidate_id="my-page",
                label="My page",
                role="button",
                risk_level="low",
            )
        ],
        forbidden_candidate_ids=set(),
    )[0]
    assert mixed_conflicted_value.value < 0.18
    assert selective_policy._semantic_stage_fast_path_candidate(
        query=conflict_query,
        plan=HierarchicalPlan(
            goal_id="membership.cancel",
            stage="hub_discovery",
            target_roles=["account.hub"],
            immediate_subgoal="open account hub",
            expected_outcome="membership controls appear",
            completion_rule="select one safe account hub",
            source="decision_memory_fallback",
        ),
        prior_values=[conflicted_value],
        recent_history=[],
    ) is None
    destination_scroll_plan = HierarchicalPlan(
        goal_id="membership.cancel",
        stage="destination_entry",
        target_roles=["membership.cancel.entry", "membership.hub", "billing.manage"],
        immediate_subgoal="find cancellation controls on the account page",
        expected_outcome="cancellation entry becomes visible",
        completion_rule="stop before final cancellation confirmation",
        source="decision_memory_fallback",
    )
    destination_scroll_query = replace(
        conflict_query,
        screen=SemanticScreenState(
            semantic_fingerprint="membership-account-webview",
            title="account",
            auth_state="logged_in",
            surface_type="webview",
            navigation_depth=2,
            tokens=("account", "membership", "next billing date"),
            candidate_payloads=(
                {
                    "candidate_id": "billing-history",
                    "label": "billing history",
                    "risk_level": "low",
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "dangerous_final": False,
                    "function_role_scores": {},
                },
            ),
        ),
        candidate_scores={},
        candidate_confidence={},
        destination_match=0.38,
    )
    scrollable_screen = ScreenObservation(
        app_package="evaluation.membership.app",
        window_title="account",
        activity_name="android.webkit.WebView",
        nodes=[
            AccessibilityNodeSummary(
                node_id="scroll-root",
                role="container",
                scrollable=True,
                clickable=False,
            )
        ],
        candidates=[],
    )
    assert selective_policy.semantic_destination_scroll_fast_path(
        query=destination_scroll_query,
        plan=destination_scroll_plan,
        screen=scrollable_screen,
        recent_history=[],
    ) is True
    assert selective_policy.semantic_destination_scroll_fast_path(
        query=destination_scroll_query,
        plan=destination_scroll_plan,
        screen=scrollable_screen,
        recent_history=[
            {
                "action_name": "scroll",
                "scroll_direction": "down",
                "connectivity_status": "observed",
                "outcome_type": "navigated",
                "progress_label": "advanced",
            }
            for _ in range(4)
        ],
    ) is False
    disabled_action, disabled_status, _ = ActionSafetyGate().validate(
        NavigationAction(name="click", candidate_id="disabled"),
        candidates=[
            NavigationCandidate(
                candidate_id="disabled",
                label="회원가입",
                role="button",
                position_bucket="middle",
                risk_level="low",
                enabled=False,
            )
        ],
        forbidden_candidate_ids=set(),
    )
    assert disabled_action.name == "wait_and_observe"
    assert disabled_status == "replaced_with_safe_action"
    planner_calls_before_loop_guard = planner_transport.plan_calls
    loop_guarded = selective_policy.decide_action(
        query=fast_path_query,
        plan=fast_path_plan,
        candidates=[
            NavigationCandidate(
                candidate_id="signup",
                label="회원가입",
                role="button",
                position_bucket="middle",
                risk_level="low",
            )
        ],
        forbidden_candidate_ids=set(),
        recent_history=[
            {"step_ordinal": 1, "screen_fingerprint": "screen-a"},
            {"step_ordinal": 2, "screen_fingerprint": "screen-b"},
            {"step_ordinal": 3, "screen_fingerprint": "screen-a"},
        ],
    )
    assert loop_guarded.proposal.action.name == "stop_for_user"
    assert loop_guarded.verifier_provider == "python_screen_visit_guard"
    assert planner_transport.plan_calls == planner_calls_before_loop_guard
    assert selective_policy._should_invoke_planner(
        query=fast_path_query,
        plan=fast_path_plan,
        prior_values=high_confidence_values,
        recent_history=[
            {
                "screen_fingerprint": "screen-a",
                "connectivity_status": "observed",
                "outcome_type": "navigated",
                "progress_label": "advanced",
                "failure_class": "",
            }
        ],
    ) is False

    semantic_fast_path_query = replace(
        fast_path_query,
        screen=SemanticScreenState(
            semantic_fingerprint="membership-home",
            title="home",
            auth_state="unknown",
            surface_type="native",
            navigation_depth=None,
            tokens=("마이페이지",),
            candidate_payloads=(
                {
                    "candidate_id": "my-page",
                    "label": "마이페이지",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"account.hub": 1.0},
                },
                {
                    "candidate_id": "search",
                    "label": "검색",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {},
                },
            ),
        ),
        candidate_scores={"my-page": 0.44, "search": 0.02},
        candidate_confidence={},
    )
    semantic_fast_path_plan = HierarchicalPlan(
        goal_id="membership.join",
        stage="hub_discovery",
        target_roles=["membership.join.entry", "membership.hub", "account.hub"],
        immediate_subgoal="open an account or membership hub",
        expected_outcome="membership choices become visible",
        completion_rule="choose one uniquely matching safe hub",
        source="decision_memory_fallback",
    )
    semantic_fast_path_values = [
        CandidateValue(
            candidate_id="my-page",
            value=0.44,
            memory_score=0.44,
            role_score=0.44,
            final_score=0.44,
            forbidden=False,
            risk_level="low",
        ),
        CandidateValue(
            candidate_id="search",
            value=0.02,
            memory_score=0.02,
            role_score=0.0,
            final_score=0.02,
            forbidden=False,
            risk_level="low",
        ),
    ]
    assert selective_policy._should_invoke_planner(
        query=semantic_fast_path_query,
        plan=semantic_fast_path_plan,
        prior_values=semantic_fast_path_values,
        recent_history=[],
    ) is False
    planner_calls_before_semantic_fast_path = planner_transport.plan_calls
    semantic_fast_path_decision = selective_policy.decide_action(
        query=semantic_fast_path_query,
        plan=semantic_fast_path_plan,
        candidates=[
            NavigationCandidate(
                candidate_id="my-page", label="마이페이지", role="button", risk_level="low"
            ),
            NavigationCandidate(
                candidate_id="search", label="검색", role="button", risk_level="low"
            ),
        ],
        forbidden_candidate_ids=set(),
        recent_history=[],
    )
    assert semantic_fast_path_decision.proposal.action.candidate_id == "my-page"
    assert semantic_fast_path_decision.proposal.provider == (
        "semantic_intermediate_role_fast_path"
    )
    assert semantic_fast_path_decision.reflection_on_demand is False
    assert planner_transport.plan_calls == planner_calls_before_semantic_fast_path
    ambiguous_semantic_query = replace(
        semantic_fast_path_query,
        screen=replace(
            semantic_fast_path_query.screen,
            candidate_payloads=(
                *semantic_fast_path_query.screen.candidate_payloads,
                {
                    "candidate_id": "full-menu",
                    "label": "전체 메뉴",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"account.hub": 1.0},
                },
            ),
        ),
    )
    ambiguous_values = [
        *semantic_fast_path_values,
        CandidateValue(
            candidate_id="full-menu",
            value=0.43,
            memory_score=0.43,
            role_score=0.44,
            final_score=0.43,
            forbidden=False,
            risk_level="low",
        ),
    ]
    ambiguous_candidates = [
        NavigationCandidate(candidate_id="my-page", label="마이페이지"),
        NavigationCandidate(candidate_id="search", label="검색"),
        NavigationCandidate(candidate_id="full-menu", label="전체 메뉴"),
    ]
    assert _candidate_score_visual_reason(
        ambiguous_values,
        ambiguous_candidates,
        0.25,
    ) == "candidate_scores_too_close"
    assert _candidate_score_visual_reason(
        ambiguous_values[:2],
        [
            NavigationCandidate(candidate_id="merged-1", label="account membership"),
            NavigationCandidate(candidate_id="merged-2", label="account membership"),
        ],
        0.25,
    ) == "accessibility_candidate_labels_duplicated"
    assert _candidate_score_visual_reason(
        ambiguous_values[:1],
        [NavigationCandidate(candidate_id="merged", label="account " * 30)],
        0.25,
    ) == "accessibility_candidate_text_merged"
    memory_confident_values = [
        value.model_copy(update={"supporting_cases": 2})
        if value.candidate_id == "my-page"
        else value
        for value in semantic_fast_path_values
    ]
    assert _db_solar_conflict_visual_reason(
        memory_confident_values,
        ambiguous_candidates,
        PlannerProposal(
            NavigationAction(name="click", candidate_id="search"),
            0.8,
            "solar_pro3",
            False,
        ),
        [
            value.model_copy(
                update={
                    "score_source": "planner_model_verifier",
                    "verifier_score": 0.8,
                }
            )
            for value in memory_confident_values
        ],
    ) == "db_solar_candidate_conflict"
    assert selective_policy._should_invoke_planner(
        query=ambiguous_semantic_query,
        plan=semantic_fast_path_plan,
        prior_values=ambiguous_values,
        recent_history=[],
    ) is True

    compact_menu_query = replace(
        semantic_fast_path_query,
        screen=replace(
            semantic_fast_path_query.screen,
            semantic_fingerprint="compact-menu",
            candidate_payloads=(
                {
                    "candidate_id": "menu-button",
                    "label": "Open all menu",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"navigation.menu": 1.0},
                },
                {
                    "candidate_id": "screen-root",
                    "label": "Open all menu " + "unrelated composite screen text " * 4,
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"navigation.menu": 1.0},
                },
            ),
        ),
    )
    assert selective_policy._semantic_stage_fast_path_candidate(
        query=compact_menu_query,
        plan=semantic_fast_path_plan.model_copy(
            update={
                "target_roles": [
                    *semantic_fast_path_plan.target_roles,
                    "navigation.menu",
                ]
            }
        ),
        prior_values=[
            CandidateValue(
                candidate_id="menu-button", value=0.60, memory_score=0.60,
                role_score=0.60, final_score=0.60, forbidden=False, risk_level="low",
            ),
            CandidateValue(
                candidate_id="screen-root", value=0.50, memory_score=0.50,
                role_score=0.50, final_score=0.50, forbidden=False, risk_level="low",
            ),
        ],
        recent_history=[],
    ) == "menu-button"

    continuation_query = replace(
        semantic_fast_path_query,
        screen=replace(
            semantic_fast_path_query.screen,
            semantic_fingerprint="expanded-members-menu",
            candidate_payloads=(
                {
                    "candidate_id": "members-category",
                    "label": "Members",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"membership.hub": 0.98},
                },
                {
                    "candidate_id": "members-entry",
                    "label": "Members",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"membership.hub": 0.98},
                },
                {
                    "candidate_id": "benefits",
                    "label": "Member benefits",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "clickable": True,
                    "enabled": True,
                    "selected": False,
                    "function_role_scores": {"membership.hub": 0.98},
                },
            ),
        ),
        candidate_scores={
            "members-category": 0.74,
            "members-entry": 0.74,
            "benefits": 0.74,
        },
        candidate_confidence={},
    )
    continuation_candidates = [
        NavigationCandidate(
            candidate_id="members-category", label="Members", role="clickable",
            parent_semantics="Travel preparation", risk_level="low",
        ),
        NavigationCandidate(
            candidate_id="members-entry", label="Members", role="clickable",
            parent_semantics="Members", risk_level="low",
        ),
        NavigationCandidate(
            candidate_id="benefits", label="Member benefits", role="clickable",
            parent_semantics="Member benefits", risk_level="low",
        ),
    ]
    advanced_history = [
        {
            "connectivity_status": "observed",
            "action_name": "click",
            "candidate_id": "members-category",
            "outcome_type": "navigated",
            "progress_label": "advanced",
        }
    ]
    assert selective_policy._structural_continuation_fast_path_candidate(
        query=continuation_query,
        plan=semantic_fast_path_plan,
        candidates=continuation_candidates,
        recent_history=advanced_history,
    ) == "members-entry"
    planner_calls_before_continuation = planner_transport.plan_calls
    continuation_decision = selective_policy.decide_action(
        query=continuation_query,
        plan=semantic_fast_path_plan,
        candidates=continuation_candidates,
        forbidden_candidate_ids=set(),
        recent_history=advanced_history,
    )
    assert continuation_decision.proposal.action.candidate_id == "members-entry"
    assert continuation_decision.proposal.provider == "structural_continuation_fast_path"
    assert planner_transport.plan_calls == planner_calls_before_continuation

    guarded = selective_policy._apply_direct_role_guard(
        scores={
            "click:travel": (0.70, "surrounding text suggests account access"),
            "click:members-category": (0.60, "direct membership label"),
            "click:members-entry": (0.60, "direct membership label"),
            "wait_and_observe": (0.10, "no need to wait"),
        },
        prior_values=[
            CandidateValue(
                candidate_id="travel", value=0.30, memory_score=0.20, role_score=0.44,
                final_score=0.30, forbidden=False, risk_level="low",
            ),
            CandidateValue(
                candidate_id="members-category", value=0.78, memory_score=0.60,
                role_score=0.82, final_score=0.78, forbidden=False, risk_level="low",
            ),
            CandidateValue(
                candidate_id="members-entry", value=0.78, memory_score=0.60,
                role_score=0.82, final_score=0.78, forbidden=False, risk_level="low",
            ),
        ],
        enumerated=[
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="travel"), 0.30,
                NavigationCandidate(
                    candidate_id="travel", label="내 여행 취향", role="clickable",
                    nearby_text="내 여행 취향", parent_semantics="로그인 회원가입",
                    position_bucket="top", risk_level="low",
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="members-category"), 0.78,
                NavigationCandidate(
                    candidate_id="members-category", label="J 멤버스", role="clickable",
                    nearby_text="J 멤버스", parent_semantics="예약 여행 준비",
                    position_bucket="top", risk_level="low", selected=True,
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="members-entry"), 0.78,
                NavigationCandidate(
                    candidate_id="members-entry", label="J 멤버스", role="clickable",
                    nearby_text="J 멤버스", parent_semantics="J 멤버스",
                    position_bucket="middle", risk_level="low",
                ),
            ),
            EnumeratedAction(NavigationAction(name="wait_and_observe"), 0.10, None),
        ],
    )
    assert max(guarded, key=lambda key: (guarded[key][0], key)) == "click:members-entry"
    assert guarded["click:members-entry"][1].startswith("python_direct_role_guard:")
    repeat_guarded = selective_policy._apply_immediate_repeat_guard(
        scores={
            "click:members-category": (0.90, "top-level membership category"),
            "click:members-entry": (0.70, "membership child page"),
            "click:benefits": (0.60, "membership benefits"),
        },
        enumerated=[
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="members-category"), 0.80,
                NavigationCandidate(
                    candidate_id="members-category", label="Members", role="clickable",
                    parent_semantics="Travel preparation", risk_level="low",
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="members-entry"), 0.78,
                NavigationCandidate(
                    candidate_id="members-entry", label="Members", role="clickable",
                    parent_semantics="Members", risk_level="low",
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="benefits"), 0.60,
                NavigationCandidate(
                    candidate_id="benefits", label="Member benefits", role="clickable",
                    parent_semantics="Member benefits", risk_level="low",
                ),
            ),
        ],
        recent_history=[
            {
                "connectivity_status": "observed",
                "action_name": "click",
                "candidate_id": "members-category",
                "outcome_type": "navigated",
                "progress_label": "advanced",
            }
        ],
    )
    assert max(repeat_guarded, key=lambda key: (repeat_guarded[key][0], key)) == (
        "click:members-entry"
    )
    assert repeat_guarded["click:members-category"][1].startswith(
        "python_immediate_repeat_guard:"
    )
    structurally_resolved = selective_policy._resolve_structural_direct_candidate(
        prior_values=[
            CandidateValue(
                candidate_id="members-category", value=0.20, memory_score=0.53,
                role_score=0.8036, final_score=0.20, forbidden=False, risk_level="low",
            ),
            CandidateValue(
                candidate_id="members-entry", value=0.74, memory_score=0.53,
                role_score=0.8036, final_score=0.74, forbidden=False, risk_level="low",
            ),
            CandidateValue(
                candidate_id="benefits", value=0.74, memory_score=0.53,
                role_score=0.8036, final_score=0.74, forbidden=False, risk_level="low",
            ),
        ],
        enumerated=[
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="members-category"), 0.20,
                NavigationCandidate(
                    candidate_id="members-category", label="J 멤버스", role="clickable",
                    nearby_text="J 멤버스", parent_semantics="예약 여행 준비",
                    position_bucket="top", risk_level="low", selected=True,
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="members-entry"), 0.74,
                NavigationCandidate(
                    candidate_id="members-entry", label="J 멤버스", role="clickable",
                    nearby_text="J 멤버스", parent_semantics="J 멤버스",
                    position_bucket="middle", risk_level="low",
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="benefits"), 0.74,
                NavigationCandidate(
                    candidate_id="benefits", label="J 멤버스 혜택존", role="clickable",
                    nearby_text="J 멤버스 혜택존", parent_semantics="J 멤버스 혜택존",
                    position_bucket="bottom", risk_level="low",
                ),
            ),
        ],
    )
    assert structurally_resolved == "click:members-entry"
    retry_inventory = AndroidWorldResearchPolicy._compact_model_retry_actions(
        [
            *[
                EnumeratedAction(
                    NavigationAction(name="click", candidate_id=f"candidate-{index}"),
                    1.0 - index / 10,
                    NavigationCandidate(
                        candidate_id=f"candidate-{index}",
                        label=f"Candidate {index}",
                        role="button",
                        risk_level="low",
                    ),
                )
                for index in range(8)
            ],
            EnumeratedAction(NavigationAction(name="scroll", direction="down"), 0.18, None),
            EnumeratedAction(NavigationAction(name="wait_and_observe"), 0.12, None),
            EnumeratedAction(NavigationAction(name="stop_for_user"), 0.05, None),
        ]
    )
    assert [item.action.candidate_id for item in retry_inventory[:6]] == [
        f"candidate-{index}" for index in range(6)
    ]
    assert [item.action.name for item in retry_inventory[6:]] == [
        "scroll", "wait_and_observe", "stop_for_user"
    ]
    malformed_model_rescue = selective_policy._resolve_structural_direct_candidate(
        query=conflict_query,
        plan=HierarchicalPlan(
            goal_id="membership.cancel",
            stage="hub_discovery",
            target_roles=["membership.hub", "account.hub"],
            immediate_subgoal="open the account or membership hub",
            expected_outcome="membership controls become visible",
            completion_rule="choose one safe intermediate hub",
            source="decision_memory_fallback",
        ),
        prior_values=[conflicted_value],
        enumerated=[
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="my-page"),
                conflicted_value.final_score,
                NavigationCandidate(
                    candidate_id="my-page",
                    label="My page",
                    role="button",
                    risk_level="low",
                ),
            ),
            EnumeratedAction(NavigationAction(name="wait_and_observe"), 0.12, None),
        ],
    )
    assert malformed_model_rescue == "click:my-page"
    ambiguous_rescue_query = replace(
        conflict_query,
        screen=replace(
            conflict_query.screen,
            candidate_payloads=(
                *conflict_query.screen.candidate_payloads,
                {
                    "candidate_id": "account",
                    "label": "Account",
                    "risk_level": "low",
                    "dangerous_final": False,
                    "function_role_scores": {"account.hub": 1.0},
                },
            ),
        ),
    )
    assert selective_policy._resolve_structural_direct_candidate(
        query=ambiguous_rescue_query,
        plan=HierarchicalPlan(
            goal_id="membership.cancel",
            stage="hub_discovery",
            target_roles=["account.hub"],
            immediate_subgoal="open account hub",
            expected_outcome="membership controls become visible",
            completion_rule="choose one safe intermediate hub",
            source="decision_memory_fallback",
        ),
        prior_values=[
            conflicted_value,
            conflicted_value.model_copy(update={"candidate_id": "account"}),
        ],
        enumerated=[
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="my-page"), 0.0,
                NavigationCandidate(
                    candidate_id="my-page", label="My page", role="button",
                    risk_level="low",
                ),
            ),
            EnumeratedAction(
                NavigationAction(name="click", candidate_id="account"), 0.0,
                NavigationCandidate(
                    candidate_id="account", label="Account", role="button",
                    risk_level="low",
                ),
            ),
        ],
    ) is None
    near_tie_values = [
        high_confidence_values[0],
        high_confidence_values[1].model_copy(
            update={"value": 0.70, "final_score": 0.70}
        ),
    ]
    near_tie_query = replace(
        fast_path_query,
        candidate_scores={"signup": 0.94, "login": 0.70},
        candidate_confidence={
            **fast_path_query.candidate_confidence,
            "login": replace(
                fast_path_query.candidate_confidence["login"],
                score=0.70,
            ),
        },
    )
    assert selective_policy._should_invoke_planner(
        query=near_tie_query,
        plan=fast_path_plan,
        prior_values=near_tie_values,
        recent_history=[],
    ) is True
    assert selective_policy._should_invoke_planner(
        query=fast_path_query,
        plan=fast_path_plan,
        prior_values=high_confidence_values,
        recent_history=[
            {
                "screen_fingerprint": "screen-a",
                "connectivity_status": "observed",
                "outcome_type": "no_change",
                "progress_label": "unchanged",
                "failure_class": "screen_unchanged",
            }
        ],
    ) is True
    assert selective_policy._should_invoke_planner(
        query=fast_path_query,
        plan=fast_path_plan,
        prior_values=high_confidence_values,
        recent_history=[
            {
                "screen_fingerprint": "screen-a",
                "connectivity_status": "transport_error",
                "outcome_type": "unknown",
                "progress_label": "unknown",
                "failure_class": "transport_error",
            }
        ],
    ) is False
    assert selective_policy._should_invoke_planner(
        query=fast_path_query,
        plan=fast_path_plan,
        prior_values=high_confidence_values,
        recent_history=[
            {
                "screen_fingerprint": "screen-a",
                "connectivity_status": "observed",
                "progress_label": "advanced",
            },
            {
                "screen_fingerprint": "screen-b",
                "connectivity_status": "observed",
                "progress_label": "advanced",
            },
            {
                "screen_fingerprint": "screen-a",
                "connectivity_status": "observed",
                "progress_label": "advanced",
            },
        ],
    ) is True
    print("navigation_research_architecture_unit: ok")


if __name__ == "__main__":
    main()
