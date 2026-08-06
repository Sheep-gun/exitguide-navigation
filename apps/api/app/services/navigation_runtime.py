from __future__ import annotations

import logging
import sqlite3
import uuid
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import httpx

from app.navigation_contracts import (
    AccessibilityNodeSummary,
    CandidateValue,
    DecideRequest,
    DecideResponse,
    GoalResolution,
    HierarchicalPlan,
    NavigationAction,
    NavigationCandidate,
    ObserveRequest,
    ObserveResponse,
    ScreenObservation,
    SafetyContext,
)
from app.services.navigation_agent_rules import NavigationAgentRuleStore
from app.services.navigation_decision_memory import (
    DecisionMemoryQuery,
    NavigationDecisionMemory,
    NormalizedGoal,
    is_dangerous_final_candidate,
    is_contextual_membership_cancellation_action,
    is_state_changing_action_label,
    normalize_text,
    tokenize,
)
from app.services.navigation_dataset_split import NavigationDatasetSplitManifest
from app.services.navigation_model_clients import PerceptionOutput
from app.services.navigation_extensions import ExtensionMode, NavigationExtensionRuntime
from app.services.navigation_extensions.n100_adapter import (
    action_mapping,
    build_policy_facts,
    build_procedure_screen_facts,
    construct_action,
    merge_procedure_hint,
    procedure_fast_path_matches,
)
from app.services.navigation_planner import PlannerProposal
from app.services.navigation_public_prior import NavigationPublicPrior
from app.services.navigation_research_policy import (
    AndroidWorldResearchPolicy,
    ReflectionTriggerPolicy,
    _is_reverse_navigation_candidate,
    _profile_gate_existing_entry_candidate_id,
)
from app.services.navigation_runtime_store import NavigationRuntimeStore


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerifiedTransition:
    outcome_type: str
    state_changed: bool | None
    progress_label: str
    destination_match_after: float | None
    failure_class: str
    recovery_action: NavigationAction | None


class NavigationRuntime:
    """Decision-memory runtime with planning, safety, verification and recovery."""

    def __init__(
        self,
        *,
        memory: NavigationDecisionMemory,
        store: NavigationRuntimeStore,
        policy: AndroidWorldResearchPolicy,
        public_prior: NavigationPublicPrior | None = None,
        dataset_split_manifest: NavigationDatasetSplitManifest | None = None,
        allow_locked_holdout: bool = False,
        extension: NavigationExtensionRuntime | None = None,
        agent_rules: NavigationAgentRuleStore | None = None,
        goal_fast_path_confidence: float = 0.92,
    ) -> None:
        self.memory = memory
        self.store = store
        self.policy = policy
        self.public_prior = public_prior
        self.dataset_split_manifest = dataset_split_manifest
        self.allow_locked_holdout = allow_locked_holdout
        self.extension = extension
        self.agent_rules = agent_rules
        self.goal_fast_path_confidence = max(0.85, min(1.0, goal_fast_path_confidence))
        self.reflection_policy = ReflectionTriggerPolicy()
        if dataset_split_manifest is not None:
            self.store.install_dataset_split_manifest(
                manifest_version=dataset_split_manifest.manifest_version,
                manifest_sha256=dataset_split_manifest.digest,
                entries=[entry.as_dict() for entry in dataset_split_manifest.entries],
            )

    def status(self) -> dict[str, object]:
        research_models_ready = (
            self.policy.planner_model.configured and self.policy.exaone_vlm.configured
        )
        model_blockers: list[str] = []
        if not self.policy.planner_model.configured:
            model_blockers.append("planner_model_endpoint_or_credentials_missing")
        if not self.policy.exaone_vlm.configured:
            model_blockers.append("exaone_4_5_endpoint_or_credentials_missing")
        return {
            "ready": True,
            "research_models_ready": research_models_ready,
            "serving_mode": (
                "research_models" if research_models_ready else "decision_memory_fallback"
            ),
            "research_model_blockers": model_blockers,
            "decision_db": {
                "schema_version": self.memory.metadata.get("schema_version"),
                "database_kind": self.memory.metadata.get("database_kind"),
                "standards_profile": self.memory.metadata.get("standards_profile", "legacy-v1"),
                "profile_aware_retrieval": self.memory.profile_enabled,
                "access_mode": "read_only",
            },
            "runtime_db": self.store.status(),
            "navigation_extension": (
                {"enabled": False}
                if self.extension is None
                else {
                    "enabled": True,
                    "mode": self.extension.mode.value,
                    "store": self.extension.store.status(),
                    "procedure_catalog": self.extension.catalog.metadata(),
                    "policy_version": self.extension.verifier.policy_version,
                }
            ),
            "public_prior": (
                {"enabled": False}
                if self.public_prior is None
                else self.public_prior.status()
            ),
            "codex_rule_retrieval": (
                {"enabled": False, "mode": "off", "runtime_execution_allowed": False}
                if self.agent_rules is None
                else self.agent_rules.status()
            ),
            "dataset_split": (
                {"enabled": False}
                if self.dataset_split_manifest is None
                else self.dataset_split_manifest.status(
                    allow_locked_holdout=self.allow_locked_holdout
                )
            ),
            "planner": {
                "architecture": "k2_planner_vdroid_verifier_mobileuse_reflection",
                "structured_output": "hermes_tools_without_direct_action_execution",
                "planner_model_provider": self.policy.planner_model.name,
                "planner_model_configured": self.policy.planner_model.configured,
                "planner_model_fallback_provider": getattr(
                    self.policy.planner_model, "fallback_name", None
                ),
                "planner_model_fallback_configured": bool(
                    getattr(self.policy.planner_model, "fallback_configured", False)
                ),
                "exaone_4_5_configured": self.policy.exaone_vlm.configured,
                "fallback_allowed": self.policy.allow_model_fallback,
                "planner_model_mode": self.policy.planner_mode,
                "goal_classifier": "python_high_confidence_then_solar_db_allowlist",
                "goal_fast_path_confidence": self.goal_fast_path_confidence,
                "exaone_4_5_mode": self.policy.vlm_mode,
            },
            "allowed_actions": [
                "click(candidate_id)",
                "scroll(direction)",
                "back()",
                "wait_and_observe()",
                "stop_for_user()",
            ],
        }

    def stop_session(
        self,
        session_id: str,
        *,
        terminal_reason: str = "manual_stop",
        handoff_reason: str = "",
    ) -> dict[str, object]:
        """Idempotently close one executor session without fabricating a UI outcome."""

        session = self.store.session(session_id)
        if session is None:
            raise KeyError(session_id)
        if session["status"] == "active":
            self.store.set_session_status(
                session_id,
                "stopped",
                terminal_reason=terminal_reason,
                handoff_reason=handoff_reason,
            )
            session = self.store.session(session_id)
            if session is None:  # Defensive: the row cannot disappear under the store lock.
                raise KeyError(session_id)
        return session

    def decide(self, request: DecideRequest) -> DecideResponse:
        if not request.origin_app_package:
            existing_session = (
                None if request.session_id is None else self.store.session(request.session_id)
            )
            request = request.model_copy(
                update={
                    "origin_app_package": (
                        request.current_app_package
                        if existing_session is None
                        else str(existing_session["app_package"])
                    )
                }
            )
        if self.dataset_split_manifest is not None:
            self.dataset_split_manifest.require_collection_access(
                request.origin_app_package,
                allow_locked_holdout=self.allow_locked_holdout,
            )
        session_id = request.session_id or f"navs_{uuid.uuid4().hex}"
        normalized_goal, goal_resolution = self._resolve_goal(
            session_id=session_id,
            goal_text=request.goal_text,
            locale=request.locale,
        )
        request = request.model_copy(
            update={
                "screen": _contextualize_membership_cancellation_safety(
                    request.screen,
                    None if normalized_goal is None else normalized_goal.goal_id,
                )
            }
        )
        structured_screen = self.memory.semantic_screen_state(
            window_title=request.screen.window_title,
            activity_name=request.screen.activity_name,
            candidates=[
                candidate.model_dump(mode="json") for candidate in request.screen.candidates
            ],
            locale=request.locale,
            navigation_depth=request.screen.navigation_depth,
        )
        structured_query = self.memory.retrieve(
            goal_text=request.goal_text,
            window_title=request.screen.window_title,
            activity_name=request.screen.activity_name,
            candidates=[
                candidate.model_dump(mode="json") for candidate in request.screen.candidates
            ],
            locale=request.locale,
            exclude_app_package=request.app_package,
            top_k=0,
            normalized_goal=normalized_goal,
            resolve_goal_from_text=False,
        )
        structured_terminal_boundary = (
            goal_resolution.status == "recognized"
            and structured_query.destination_match >= _destination_threshold(structured_query)
        )
        if request.operator_action is not None:
            perception = PerceptionOutput(
                screen=request.screen,
                semantic_summary="Codex selected an accessibility-grounded action",
                provider="codex_operator_grounded_input",
            )
        elif _is_authentication_boundary(
            normalized_goal,
            structured_screen.auth_state,
            screen=request.screen,
        ):
            perception = PerceptionOutput(
                screen=request.screen,
                semantic_summary="explicit authentication boundary from structured UI",
                provider="structured_input_auth_boundary",
            )
        elif structured_terminal_boundary:
            perception = PerceptionOutput(
                screen=request.screen,
                semantic_summary="destination signature satisfied by structured UI",
                provider="structured_input_terminal_boundary",
            )
        else:
            perception = self.policy.perceive(
                goal_text=request.goal_text,
                screen=request.screen,
                screenshot_data_url=request.screenshot_data_url,
                force_visual_reasoning=request.visual_reasoning_required,
            )
        effective_screen = perception.screen
        query = self.memory.retrieve(
            goal_text=request.goal_text,
            window_title=effective_screen.window_title,
            activity_name=effective_screen.activity_name,
            candidates=[candidate.model_dump(mode="json") for candidate in effective_screen.candidates],
            locale=request.locale,
            exclude_app_package=request.app_package,
            top_k=5,
            normalized_goal=normalized_goal,
            resolve_goal_from_text=False,
        )
        destination_threshold = _destination_threshold(query)
        if (
            request.operator_action is None
            and self.public_prior is not None
            and query.goal is not None
            and query.destination_match < destination_threshold
            and query.fast_path_candidate_id() is None
        ):
            try:
                public_evidence = self.public_prior.search(
                    goal_text=request.goal_text,
                    normalized_goal=query.goal,
                    screen=query.screen,
                    app_package=request.app_package,
                )
                if public_evidence:
                    query = replace(query, public_prior_evidence=public_evidence)
            except (OSError, ValueError, sqlite3.Error) as error:
                LOGGER.warning(
                    "public_prior_search_skipped failure_class=%s detail=%s",
                    type(error).__name__,
                    str(error)[:500],
                )
        recent_history = self.store.recent_history(session_id, limit=5)
        forbidden = self.store.forbidden_candidates(
            session_id, query.screen.semantic_fingerprint
        )
        forbidden.update(
            _automatic_recovery_forbidden_candidates(
                screen_fingerprint=query.screen.semantic_fingerprint,
                candidates=effective_screen.candidates,
                recent_history=recent_history,
                goal_id=None if query.goal is None else query.goal.goal_id,
            )
        )
        procedure_screen_facts = build_procedure_screen_facts(
            query,
            destination_threshold=destination_threshold,
        )
        procedure_hint = None
        if self.extension is not None:
            try:
                procedure_hint = self.extension.prepare_decision(
                    session_id=session_id,
                    goal_id=None if query.goal is None else query.goal.goal_id,
                    app_package=request.app_package,
                    app_version=request.app_version,
                    locale=request.locale,
                    facts={"screen": procedure_screen_facts},
                    parameters=(
                        None if query.goal is None else {"operation": query.goal.operation}
                    ),
                )
            except (OSError, ValueError, sqlite3.Error) as error:
                LOGGER.warning(
                    "navigation_procedure_skipped failure_class=%s detail=%s",
                    type(error).__name__,
                    str(error)[:500],
                )
        if request.operator_action is not None:
            plan = HierarchicalPlan(
                goal_id=None if query.goal is None else query.goal.goal_id,
                stage="selective_recovery",
                target_roles=[],
                immediate_subgoal="Codex가 지정한 현재 화면 행동을 검증한다.",
                expected_outcome="지정한 행동 이후의 화면 변화를 관찰한다.",
                completion_rule="실제 실행 결과와 다음 화면이 함께 기록된다.",
                source="python_safety_gate",
            )
            planner_provider = "codex_operator"
            planner_fallback = False
        else:
            plan, planner_provider, planner_fallback = self.policy.plan(
                query=query,
                forbidden_candidate_ids=forbidden,
                destination_threshold=destination_threshold,
                recent_history=recent_history,
            )
            plan = merge_procedure_hint(plan, procedure_hint)
        candidate_values = self.policy.prior_scorer.score(
            query,
            effective_screen.candidates,
            forbidden_candidate_ids=forbidden,
        )
        memory_candidate_values = list(candidate_values)
        resolved_query_goal_id = None if query.goal is None else query.goal.goal_id
        raw_profile_gate_candidate_id = _profile_gate_existing_entry_candidate_id(
            candidates=request.screen.candidates,
            goal_id=resolved_query_goal_id,
            screen_title=request.screen.window_title,
            recent_history=recent_history,
            forbidden_candidate_ids=(),
        )
        raw_guarded_profile_gate_candidate_id = _profile_gate_existing_entry_candidate_id(
            candidates=request.screen.candidates,
            goal_id=resolved_query_goal_id,
            screen_title=request.screen.window_title,
            recent_history=recent_history,
            forbidden_candidate_ids=tuple(forbidden),
        )
        effective_profile_gate_candidate_id = _profile_gate_existing_entry_candidate_id(
            candidates=effective_screen.candidates,
            goal_id=resolved_query_goal_id,
            screen_title=effective_screen.window_title,
            recent_history=recent_history,
            forbidden_candidate_ids=tuple(forbidden),
            visually_recommended_candidate_id=perception.recommended_candidate_id,
        )
        profile_gate_fast_path_candidate_id = (
            raw_profile_gate_candidate_id
            or raw_guarded_profile_gate_candidate_id
            or effective_profile_gate_candidate_id
        )
        if "프로필" in effective_screen.window_title.casefold():
            LOGGER.info(
                "profile_gate_fast_path candidate_id=%s goal_id=%s raw_candidates=%d "
                "effective_candidates=%d recent_steps=%d raw_title_match=%s",
                profile_gate_fast_path_candidate_id or "none",
                goal_resolution.goal_id,
                len(request.screen.candidates),
                len(effective_screen.candidates),
                len(recent_history),
                "프로필" in request.screen.window_title.casefold(),
            )
        safe_goal_entry_fast_path_candidate_id = (
            self.policy.semantic_safe_goal_entry_fast_path_candidate(
                query=query,
                plan=plan,
                recent_history=recent_history,
            )
        )
        modal_dismiss_fast_path_candidate_id = _dismissible_modal_fast_path_candidate_id(
            request.screen
        ) or _dismissible_modal_fast_path_candidate_id(effective_screen)
        semantic_fast_path_candidate_id = (
            modal_dismiss_fast_path_candidate_id
            or profile_gate_fast_path_candidate_id
            or safe_goal_entry_fast_path_candidate_id
            or self.policy.semantic_intermediate_fast_path_candidate(
                query=query,
                plan=plan,
                prior_values=memory_candidate_values,
                recent_history=recent_history,
            )
        )
        procedure_fast_path_used = procedure_fast_path_matches(
            hint=procedure_hint,
            candidate_id=semantic_fast_path_candidate_id,
            candidate_payloads=query.screen.candidate_payloads,
        )
        semantic_scroll_fast_path = self.policy.semantic_destination_scroll_fast_path(
            query=query,
            plan=plan,
            screen=effective_screen,
            recent_history=recent_history,
        )
        transient_navigation_waits = _transient_navigation_control_waits(
            screen=effective_screen,
            screen_fingerprint=query.screen.semantic_fingerprint,
            recent_history=recent_history,
        )
        empty_candidate_waits = _empty_candidate_screen_waits(
            screen=effective_screen,
            screen_fingerprint=query.screen.semantic_fingerprint,
            recent_history=recent_history,
        )
        score_margin = 0.0
        reflection_on_demand = False
        verifier_provider = "not_invoked"
        visual_reobserve_reason = ""
        if request.operator_action is not None:
            proposal = PlannerProposal(
                request.operator_action,
                1.0,
                "codex_operator",
                False,
            )
            planner_provider = proposal.provider
            verifier_provider = "python_safety_gate"
            score_margin = 1.0
        elif goal_resolution.status != "recognized":
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                max(0.8, goal_resolution.confidence),
                "python_goal_gate",
                False,
            )
            planner_provider = "python_goal_gate"
        elif plan.stage == "terminal_boundary":
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                max(query.destination_match, 0.8),
                "python_terminal_boundary",
                False,
            )
            planner_provider = "python_terminal_boundary"
        elif _goal_already_satisfied(query):
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                1.0,
                "python_goal_already_satisfied",
                False,
            )
            planner_provider = "python_goal_already_satisfied"
        elif _is_authentication_boundary(
            query.goal,
            query.screen.auth_state,
            screen=request.screen,
        ):
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                1.0,
                "python_authentication_boundary",
                False,
            )
            planner_provider = "python_authentication_boundary"
        elif empty_candidate_waits is not None:
            if empty_candidate_waits >= 2:
                proposal = PlannerProposal(
                    NavigationAction(name="back"),
                    1.0,
                    "python_empty_candidate_back_guard",
                    False,
                )
                planner_provider = proposal.provider
                verifier_provider = proposal.provider
            else:
                if _can_request_visual_reobserve(request, perception, self.policy):
                    visual_reobserve_reason = "transient_empty_candidate_screen"
                    provider = "python_visual_reobserve_gate"
                    verifier_provider = "deferred_until_visual_context"
                else:
                    provider = "python_empty_candidate_wait_gate"
                    verifier_provider = provider
                proposal = PlannerProposal(
                    NavigationAction(name="wait_and_observe"),
                    1.0,
                    provider,
                    False,
                )
                planner_provider = provider
        elif effective_screen.candidates and all(
            candidate.risk_level in {"medium", "high", "blocked"}
            or is_state_changing_action_label(candidate.label)
            or is_dangerous_final_candidate(
                " ".join(
                    (
                        candidate.label,
                        candidate.icon_semantics,
                        candidate.nearby_text,
                        candidate.parent_semantics,
                    )
                )
            )
            for candidate in effective_screen.candidates
        ):
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                1.0,
                "python_state_change_boundary",
                False,
            )
            planner_provider = "python_state_change_boundary"
        elif modal_dismiss_fast_path_candidate_id is not None:
            proposal = PlannerProposal(
                NavigationAction(
                    name="click",
                    candidate_id=modal_dismiss_fast_path_candidate_id,
                ),
                1.0,
                "semantic_modal_dismiss_fast_path",
                False,
            )
            planner_provider = proposal.provider
            verifier_provider = proposal.provider
            score_margin = 1.0
        elif profile_gate_fast_path_candidate_id is not None:
            proposal = PlannerProposal(
                NavigationAction(
                    name="click",
                    candidate_id=profile_gate_fast_path_candidate_id,
                ),
                1.0,
                "semantic_intermediate_role_fast_path",
                False,
            )
            planner_provider = proposal.provider
            verifier_provider = proposal.provider
            score_margin = 1.0
        elif safe_goal_entry_fast_path_candidate_id is not None:
            proposal = PlannerProposal(
                NavigationAction(
                    name="click",
                    candidate_id=safe_goal_entry_fast_path_candidate_id,
                ),
                1.0,
                "semantic_safe_goal_entry_fast_path",
                False,
            )
            planner_provider = proposal.provider
            verifier_provider = proposal.provider
            score_margin = 1.0
        elif transient_navigation_waits is not None:
            if transient_navigation_waits >= 2:
                proposal = PlannerProposal(
                    NavigationAction(name="back"),
                    1.0,
                    "python_transient_navigation_back_guard",
                    False,
                )
                planner_provider = proposal.provider
                verifier_provider = proposal.provider
            else:
                if _can_request_visual_reobserve(request, perception, self.policy):
                    visual_reobserve_reason = "transient_single_navigation_control"
                    provider = "python_visual_reobserve_gate"
                    verifier_provider = "deferred_until_visual_context"
                else:
                    provider = "python_transient_navigation_wait_gate"
                    verifier_provider = provider
                proposal = PlannerProposal(
                    NavigationAction(name="wait_and_observe"),
                    1.0,
                    provider,
                    False,
                )
                planner_provider = provider
        else:
            if semantic_scroll_fast_path:
                proposal = PlannerProposal(
                    NavigationAction(name="scroll", direction="down"),
                    0.95,
                    "semantic_destination_scroll_fast_path",
                    False,
                )
                planner_provider = proposal.provider
                verifier_provider = proposal.provider
                score_margin = 0.95
            else:
                if (
                    semantic_fast_path_candidate_id is None
                    and _can_request_visual_reobserve(request, perception, self.policy)
                ):
                    visual_reobserve_reason = _candidate_score_visual_reason(
                        memory_candidate_values,
                        effective_screen.candidates,
                        self.policy.planner_margin_threshold,
                    )
                if visual_reobserve_reason:
                    proposal = PlannerProposal(
                        NavigationAction(name="wait_and_observe"),
                        1.0,
                        "python_visual_reobserve_gate",
                        False,
                    )
                    planner_provider = "python_visual_reobserve_gate"
                    verifier_provider = "deferred_until_visual_context"
                else:
                    research_decision = self.policy.decide_action(
                        query=query,
                        plan=plan,
                        candidates=effective_screen.candidates,
                        forbidden_candidate_ids=forbidden,
                        recent_history=recent_history,
                        screen_scrollable=any(
                            node.visible and node.scrollable for node in effective_screen.nodes
                        ),
                    )
                    plan = research_decision.plan
                    proposal = research_decision.proposal
                    # Keep the hierarchy source in plan.source, but report the
                    # component that actually selected the next action here.
                    planner_provider = proposal.provider
                    candidate_values = list(research_decision.candidate_values)
                    verifier_provider = research_decision.verifier_provider
                    score_margin = research_decision.score_margin
                    reflection_on_demand = research_decision.reflection_on_demand
                    if _can_request_visual_reobserve(request, perception, self.policy):
                        visual_reobserve_reason = _db_solar_conflict_visual_reason(
                            memory_candidate_values,
                            effective_screen.candidates,
                            proposal,
                            candidate_values,
                        )
                    if visual_reobserve_reason:
                        proposal = PlannerProposal(
                            NavigationAction(name="wait_and_observe"),
                            1.0,
                            "python_visual_reobserve_gate",
                            False,
                        )
                        planner_provider = "python_visual_reobserve_gate"
                        verifier_provider += "->visual_reobserve_deferred"
        if (
            request.operator_action is None
            and proposal.action.name == "stop_for_user"
            and not _planner_stop_has_grounded_boundary(
                planner_provider=planner_provider,
                plan_stage=plan.stage,
            )
        ):
            proposal = PlannerProposal(
                NavigationAction(name="wait_and_observe"),
                1.0,
                "python_ungrounded_handoff_reobserve_guard",
                False,
            )
            planner_provider = proposal.provider
            verifier_provider = proposal.provider
            reflection_on_demand = True
        sparse_reverse_guard_action = (
            None
            if request.operator_action is not None
            or planner_provider == "semantic_modal_dismiss_fast_path"
            else _selected_reverse_navigation_guard(
                proposal.action,
                candidates=effective_screen.candidates,
                nodes=effective_screen.nodes,
                screen_fingerprint=query.screen.semantic_fingerprint,
                recent_history=recent_history,
            )
        )
        if sparse_reverse_guard_action is not None:
            alternate = _safe_alternate_after_reverse_selection(
                proposal.action,
                candidates=effective_screen.candidates,
                candidate_values=candidate_values,
                forbidden_candidate_ids=forbidden,
            )
            if alternate is not None:
                provider = "python_reverse_navigation_alternate_guard"
                proposal = PlannerProposal(
                    NavigationAction(name="click", candidate_id=alternate.candidate_id),
                    alternate.final_score,
                    provider,
                    False,
                )
                planner_provider = provider
                verifier_provider = provider
                reflection_on_demand = True
                plan = plan.model_copy(
                    update={
                        "stage": "selective_recovery",
                        "immediate_subgoal": "뒤로가기 대신 다음 안전 후보로 경로를 이어간다.",
                        "expected_outcome": "현재 화면에서 목적에 가까운 다음 화면으로 진행한다.",
                        "completion_rule": "역방향 후보를 누르지 않고 화면 의미가 달라진다.",
                    }
                )
                sparse_reverse_guard_action = None
        if sparse_reverse_guard_action is not None:
            provider = (
                "python_reverse_navigation_back_guard"
                if sparse_reverse_guard_action.name == "back"
                else "python_transient_navigation_wait_gate"
            )
            proposal = PlannerProposal(sparse_reverse_guard_action, 1.0, provider, False)
            planner_provider = provider
            verifier_provider = provider
            reflection_on_demand = True
        repeat_guard_action = (
            None
            if request.operator_action is not None
            or planner_provider == "semantic_modal_dismiss_fast_path"
            else _interleaved_repeat_guard(
                proposal.action,
                recent_history=recent_history,
            )
        )
        if repeat_guard_action is not None:
            provider = (
                "python_interleaved_repeat_back_guard"
                if repeat_guard_action.name == "back"
                else "python_interleaved_repeat_wait_guard"
            )
            proposal = PlannerProposal(repeat_guard_action, 1.0, provider, False)
            planner_provider = provider
            verifier_provider = provider
            reflection_on_demand = True
        safety_forbidden = set(forbidden)
        if (
            profile_gate_fast_path_candidate_id is not None
            and proposal.action.name == "click"
            and proposal.action.candidate_id == profile_gate_fast_path_candidate_id
        ):
            safety_forbidden.discard(profile_gate_fast_path_candidate_id)
        safe_action, safety_status, safety_reason = self.policy.safety_gate.validate(
            proposal.action,
            candidates=effective_screen.candidates,
            forbidden_candidate_ids=safety_forbidden,
        )
        decision_id = f"navd_{uuid.uuid4().hex}"
        procedure_fast_path_used = bool(
            procedure_fast_path_used
            and proposal.action.name == "click"
            and proposal.action.candidate_id == semantic_fast_path_candidate_id
            and safe_action == proposal.action
        )
        policy_decision = None
        if self.extension is not None:
            query_candidate_payloads = {
                str(payload.get("candidate_id", "")): dict(payload)
                for payload in query.screen.candidate_payloads
            }
            policy_candidates = []
            for candidate in effective_screen.candidates:
                payload = candidate.model_dump(mode="json")
                payload.update(query_candidate_payloads.get(candidate.candidate_id, {}))
                screen_context = " ".join(
                    (
                        candidate.label,
                        candidate.icon_semantics,
                        candidate.nearby_text,
                        candidate.parent_semantics,
                    )
                )
                terminal = (
                    is_state_changing_action_label(candidate.label)
                    or is_dangerous_final_candidate(
                        " ".join((candidate.label, candidate.icon_semantics))
                    )
                    or is_contextual_membership_cancellation_action(
                        candidate.label,
                        screen_context,
                    )
                )
                payload["terminal"] = terminal
                # Query-time memory enrichment can carry a conservative dangerous_final flag
                # derived from adjacent/parent text. Replace it with the authoritative current
                # candidate-action classification before the external safety policy evaluates it.
                payload["dangerous_final"] = terminal
                payload["state_changing"] = terminal
                policy_candidates.append(payload)
            policy_facts = build_policy_facts(
                goal_id=None if query.goal is None else query.goal.goal_id,
                proposed_action=proposal.action,
                candidates=policy_candidates,
                forbidden_candidate_ids=safety_forbidden,
                screen_trusted=True,
                screen_facts=procedure_screen_facts,
                procedure_hint=procedure_hint,
            )
            try:
                extension_action, policy_decision = self.extension.verify_action(
                    session_id=session_id,
                    decision_id=decision_id,
                    planner_action=action_mapping(proposal.action),
                    proposed_action=action_mapping(proposal.action),
                    grounded_action=action_mapping(safe_action),
                    grounding_status=safety_status,
                    grounding_reason=safety_reason,
                    facts=policy_facts,
                    confirmation_id=request.confirmation_id,
                )
                safe_action = construct_action(type(safe_action), extension_action)
                if (
                    self.extension.mode == ExtensionMode.ENFORCE
                    and policy_decision.verdict.value != "allow"
                ):
                    safety_status = "replaced_with_safe_action"
                    safety_reason = (
                        f"policy:{policy_decision.rule_ids[0]}: {policy_decision.reason}"
                    )[:1000]
                    procedure_fast_path_used = False
                verifier_provider += "->logic_policy_v1"
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                LOGGER.error(
                    "navigation_policy_verifier_failed mode=%s failure_class=%s detail=%s",
                    self.extension.mode.value,
                    type(error).__name__,
                    str(error)[:500],
                )
                if self.extension.mode == ExtensionMode.ENFORCE:
                    safe_action = NavigationAction(name="stop_for_user")
                    safety_status = "replaced_with_safe_action"
                    safety_reason = "navigation extension verifier failed closed"
                    procedure_fast_path_used = False
        confidence = proposal.confidence if safe_action == proposal.action else 1.0
        consulted_rules = (
            ()
            if self.agent_rules is None
            else self.agent_rules.consult(
                None if query.goal is None else query.goal.goal_id,
                screen_terms=(
                    effective_screen.window_title,
                    effective_screen.activity_name,
                    *(candidate.label for candidate in effective_screen.candidates),
                ),
            )
        )
        safety_context = _build_shadow_safety_context(
            action=safe_action,
            proposed_action=proposal.action,
            plan_stage=plan.stage,
            planner_provider=planner_provider,
            confidence=confidence,
            consulted_rule_ids=tuple(rule.rule_id for rule in consulted_rules),
            candidates=effective_screen.candidates,
            policy_blocked=(
                policy_decision is not None and policy_decision.verdict.value != "allow"
            ),
        )
        self.store.upsert_session(
            session_id=session_id,
            request_id=request.request_id,
            app_package=request.origin_app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            goal_id=None if query.goal is None else query.goal.goal_id,
            origin_app_package=request.origin_app_package,
            current_app_package=request.current_app_package,
            previous_app_package=request.previous_app_package,
            transition_reason=request.transition_reason,
            collection_run=request.collection_run,
            task_context=request.task_context,
        )
        evidence_case_ids = [evidence.case_id for evidence in query.evidence]
        evidence_case_ids.extend(
            f"public:{evidence.evidence_id}" for evidence in query.public_prior_evidence
        )
        retrieval_rows = [
            {
                "evidence_id": evidence.case_id,
                "source_type": evidence.source_type,
                "rank": rank,
                "score": evidence.score,
                "used": evidence.case_id in evidence_case_ids,
                "metadata": {
                    "verification_count": evidence.verification_count,
                    "provenance_validated": evidence.provenance_validated,
                    "source_app_package": evidence.source_app_package,
                },
            }
            for rank, evidence in enumerate(query.evidence, start=1)
        ]
        retrieval_rows.extend(
            {
                "evidence_id": f"public:{evidence.evidence_id}",
                "source_type": "public_prior",
                "rank": len(retrieval_rows) + rank,
                "score": getattr(evidence, "score", None),
                "used": True,
                "metadata": {},
            }
            for rank, evidence in enumerate(query.public_prior_evidence, start=1)
        )
        self.store.record_decision(
            decision_id=decision_id,
            session_id=session_id,
            step_ordinal=request.step_ordinal,
            screen_fingerprint=query.screen.semantic_fingerprint,
            screen=effective_screen,
            goal_id=None if query.goal is None else query.goal.goal_id,
            plan=plan,
            proposed_action=proposal.action,
            action=safe_action,
            confidence=confidence,
            score_margin=score_margin,
            reflection_on_demand=reflection_on_demand,
            planner_provider=planner_provider,
            planner_fallback_used=(
                goal_resolution.fallback_used or planner_fallback or proposal.fallback_used
            ),
            safety_status=safety_status,
            safety_reason=safety_reason,
            destination_match_before=query.destination_match,
            evidence_case_ids=evidence_case_ids,
            candidate_values=candidate_values,
            retrieval_hits=retrieval_rows,
            decision_provenance={
                "perception_provider": perception.provider,
                "planner_provider": planner_provider,
                "verifier_provider": verifier_provider,
                "planner_fallback_used": (
                    goal_resolution.fallback_used
                    or planner_fallback
                    or proposal.fallback_used
                ),
                "prompt_contract_version": "navigation-runtime-v5",
                "profile_gate_resolution": {
                    "goal_id": resolved_query_goal_id,
                    "raw_candidate_count": len(request.screen.candidates),
                    "effective_candidate_count": len(effective_screen.candidates),
                    "raw_title_has_profile": "프로필"
                    in request.screen.window_title.casefold(),
                    "effective_title_has_profile": "프로필"
                    in effective_screen.window_title.casefold(),
                    "recent_step_count": len(recent_history),
                    "forbidden_candidate_ids": sorted(forbidden)[:5],
                    "raw_candidate_id": raw_profile_gate_candidate_id,
                    "raw_guarded_candidate_id": raw_guarded_profile_gate_candidate_id,
                    "effective_candidate_id": effective_profile_gate_candidate_id,
                },
                "app_context": {
                    "origin_app_package": request.origin_app_package,
                    "current_app_package": request.current_app_package,
                    "previous_app_package": request.previous_app_package,
                    "transition_reason": request.transition_reason,
                },
                "operator_command": {
                    "source": request.operator_source,
                    "command_id": request.operator_command_id,
                    "reason_codes": request.operator_reason_codes,
                    "reason_text": request.operator_reason_text,
                    "review_status": request.operator_review_status,
                    "requested_action": (
                        None
                        if request.operator_action is None
                        else request.operator_action.model_dump(mode="json")
                    ),
                },
                "safety_context": safety_context.model_dump(mode="json"),
            },
            screenshot_data_url=(
                request.raw_screenshot_data_url or request.screenshot_data_url
            ),
        )
        if self.extension is not None:
            try:
                self.extension.record_memory_retrievals(
                    session_id=session_id,
                    decision_id=decision_id,
                    task_run_id=None,
                    rows=retrieval_rows,
                )
            except (OSError, ValueError, sqlite3.Error) as error:
                LOGGER.warning(
                    "navigation_extension_retrieval_log_skipped failure_class=%s detail=%s",
                    type(error).__name__,
                    str(error)[:500],
                )
        return DecideResponse(
            request_id=request.request_id,
            session_id=session_id,
            decision_id=decision_id,
            goal=goal_resolution,
            plan=plan,
            action=safe_action,
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            perception_provider=perception.provider,
            planner_provider=planner_provider,
            verifier_provider=verifier_provider,
            planner_fallback_used=(
                goal_resolution.fallback_used or planner_fallback or proposal.fallback_used
            ),
            safety_status=safety_status,
            safety_reason=safety_reason,
            destination_match=query.destination_match,
            candidate_values=candidate_values,
            evidence_case_ids=evidence_case_ids,
            visual_reobserve_required=bool(visual_reobserve_reason),
            visual_reobserve_reason=visual_reobserve_reason,
            vlm_recommended_candidate_id=perception.recommended_candidate_id,
            procedure_id=procedure_hint.procedure_id if procedure_hint else None,
            procedure_step_ordinal=procedure_hint.step_ordinal if procedure_hint else None,
            procedure_fast_path_eligible=(
                procedure_hint.fast_path_eligible if procedure_hint else False
            ),
            procedure_fast_path_used=procedure_fast_path_used,
            policy_verdict=(policy_decision.verdict.value if policy_decision else None),
            policy_rule_ids=(list(policy_decision.rule_ids) if policy_decision else []),
            confirmation_id=(policy_decision.confirmation_id if policy_decision else None),
            safety_context=safety_context,
        )

    def _resolve_goal(
        self,
        *,
        session_id: str,
        goal_text: str,
        locale: str,
    ) -> tuple[NormalizedGoal | None, GoalResolution]:
        cached = self.store.session(session_id)
        if cached is not None:
            cached_goal_id = str(cached.get("goal_id") or "")
            if not cached_goal_id:
                return None, GoalResolution(
                    status="out_of_scope",
                    goal_id=None,
                    confidence=1.0,
                    provider="session_cached_goal",
                    validated_against_db=True,
                    fallback_used=False,
                )
            cached_goal = self.memory.goal_by_id(
                cached_goal_id,
                confidence=1.0,
                matched_phrase="session_cached_goal",
            )
            if cached_goal is None:
                raise ValueError("cached navigation goal is no longer active in Goal Ontology DB")
            return cached_goal, _goal_resolution(
                cached_goal,
                provider="session_cached_goal",
                validated_against_db=True,
                fallback_used=False,
            )

        phrase_goal = self.memory.normalize_goal(goal_text, locale=locale)
        if (
            phrase_goal is not None
            and phrase_goal.confidence >= self.goal_fast_path_confidence
            and _unambiguous_db_goal_phrase(
                memory=self.memory,
                goal_text=goal_text,
                locale=locale,
                goal_id=phrase_goal.goal_id,
            )
        ):
            return phrase_goal, _goal_resolution(
                phrase_goal,
                provider="python_high_confidence_goal_phrase",
                validated_against_db=True,
                fallback_used=False,
            )

        if self.policy.planner_model.configured:
            try:
                classified = self.policy.planner_model.classify_goal(
                    goal_text=goal_text,
                    locale=locale,
                    goal_catalog=self.memory.goal_catalog(locale=locale),
                )
                if classified.goal_id is None:
                    return None, GoalResolution(
                        status="out_of_scope",
                        goal_id=None,
                        confidence=classified.confidence,
                        provider=(
                            f"{getattr(self.policy.planner_model, 'active_name', self.policy.planner_model.name)}"
                            "_goal_classifier"
                        ),
                        validated_against_db=True,
                        fallback_used=False,
                    )
                classified_goal = self.memory.goal_by_id(
                    classified.goal_id,
                    confidence=classified.confidence,
                    matched_phrase=classified.reason or "solar_goal_classifier",
                )
                if classified_goal is None:
                    raise ValueError("goal classifier returned an inactive Goal Ontology ID")
                return classified_goal, _goal_resolution(
                    classified_goal,
                    provider=(
                        f"{getattr(self.policy.planner_model, 'active_name', self.policy.planner_model.name)}"
                        "_goal_classifier"
                    ),
                    validated_against_db=True,
                    fallback_used=False,
                )
            except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
                if not self.policy.allow_model_fallback:
                    raise
                fallback_used = True
        else:
            fallback_used = True

        return phrase_goal, _goal_resolution(
            phrase_goal,
            provider="python_phrase_fallback",
            validated_against_db=phrase_goal is not None,
            fallback_used=fallback_used,
        )

    def observe(self, request: ObserveRequest) -> ObserveResponse:
        decision = self.store.decision(request.decision_id)
        if request.next_screen is not None:
            request = request.model_copy(
                update={
                    "next_screen": _contextualize_membership_cancellation_safety(
                        request.next_screen,
                        str(decision.get("goal_id") or ""),
                    )
                }
            )
        before_match = float(decision["destination_match_before"])
        effective_next_screen = None
        next_query = None
        if request.connectivity_status != "observed":
            verified = VerifiedTransition(
                outcome_type="unknown",
                state_changed=None,
                progress_label="unknown",
                destination_match_after=None,
                failure_class=request.connectivity_status,
                recovery_action=NavigationAction(name="wait_and_observe"),
            )
            next_fingerprint = None
        else:
            assert request.next_screen is not None
            stored_goal = self.memory.goal_by_id(
                str(decision.get("goal_id") or ""),
                confidence=1.0,
                matched_phrase="stored_decision_goal",
            )
            structured_next_screen = self.memory.semantic_screen_state(
                window_title=request.next_screen.window_title,
                activity_name=request.next_screen.activity_name,
                candidates=[
                    candidate.model_dump(mode="json")
                    for candidate in request.next_screen.candidates
                ],
                locale=str(decision["locale"]),
                navigation_depth=request.next_screen.navigation_depth,
            )
            if _is_authentication_boundary(
                stored_goal,
                structured_next_screen.auth_state,
                screen=request.next_screen,
            ):
                next_perception = PerceptionOutput(
                    screen=request.next_screen,
                    semantic_summary="explicit authentication boundary from structured UI",
                    provider="structured_input_auth_boundary",
                )
            else:
                next_perception = self.policy.perceive(
                    goal_text=str(decision["goal_text_redacted"]),
                    screen=request.next_screen,
                    screenshot_data_url=request.after_screenshot_data_url,
                )
            effective_next_screen = next_perception.screen
            next_query = self.memory.retrieve(
                goal_text=str(decision["goal_text_redacted"]),
                window_title=effective_next_screen.window_title,
                activity_name=effective_next_screen.activity_name,
                candidates=[
                    candidate.model_dump(mode="json")
                    for candidate in effective_next_screen.candidates
                ],
                locale=str(decision["locale"]),
                exclude_app_package=str(decision["app_package"]),
                top_k=0,
                normalized_goal=stored_goal,
                resolve_goal_from_text=False,
            )
            next_fingerprint = next_query.screen.semantic_fingerprint
            observed_signal = request.observed_signal
            if _is_authentication_boundary(
                stored_goal,
                next_query.screen.auth_state,
                screen=request.next_screen,
            ):
                observed_signal = "login_required"
            session_app_package = str(decision.get("app_package") or "")
            previous_app_package = str(
                decision.get("screen_payload", {}).get("app_package") or ""
            )
            returned_to_session_app = (
                observed_signal == "external_app"
                and bool(session_app_package)
                and bool(previous_app_package)
                and previous_app_package != session_app_package
                and effective_next_screen.app_package == session_app_package
            )
            successful_back_recovery = _successful_back_recovery(
                action_name=str(decision["action_name"]),
                previous_fingerprint=str(decision["screen_fingerprint"]),
                next_fingerprint=next_fingerprint,
                session_app_package=session_app_package,
                next_app_package=effective_next_screen.app_package,
                recent_history=self.store.recent_history(
                    str(decision["session_id"]),
                    limit=5,
                ),
            )
            if successful_back_recovery:
                verified = VerifiedTransition(
                    outcome_type="navigated",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="advanced",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=None,
                )
            elif returned_to_session_app:
                verified = VerifiedTransition(
                    outcome_type="navigated",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="advanced",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=None,
                )
            elif _is_non_plan_payment_method_screen(
                None if stored_goal is None else stored_goal.goal_id,
                next_query.screen.tokens,
            ):
                verified = VerifiedTransition(
                    outcome_type="wrong_destination",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="regressed",
                    destination_match_after=next_query.destination_match,
                    failure_class="payment_method_update_not_plan_change",
                    recovery_action=NavigationAction(name="back"),
                )
            elif (
                str(decision["action_name"]) == "stop_for_user"
                and str(decision["planner_provider"]) == "python_terminal_boundary"
                and next_query.destination_match >= _destination_threshold(next_query)
            ):
                # The Executor reports an intentional non-executed stop as a
                # blocked signal.  When the planner stopped specifically
                # because the freshly observed screen satisfies its
                # Destination Signature, that is the safe success boundary,
                # not an executor/navigation failure.
                verified = VerifiedTransition(
                    outcome_type="destination_reached",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="reached",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=NavigationAction(name="stop_for_user"),
                )
            elif (
                observed_signal == "external_app"
                and str(decision["screen_fingerprint"]) != next_fingerprint
                and _semantic_fast_path_grounded_progress(
                    planner_provider=str(decision["planner_provider"]),
                    goal_id="" if stored_goal is None else stored_goal.goal_id,
                    screen_tokens=next_query.screen.tokens,
                )
            ):
                # A provider-scoped account-management control can legitimately
                # hand navigation from the app into the platform/provider UI.
                # The selected control and the observed destination must both
                # be semantically grounded; package change alone must not turn
                # that expected K2 hierarchy step into failure evidence.
                verified = VerifiedTransition(
                    outcome_type="navigated",
                    state_changed=True,
                    progress_label="advanced",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=None,
                )
            elif observed_signal != "none":
                verified = verify_transition(
                    action_name=str(decision["action_name"]),
                    previous_fingerprint=str(decision["screen_fingerprint"]),
                    next_fingerprint=next_fingerprint,
                    destination_match_before=before_match,
                    destination_match_after=next_query.destination_match,
                    destination_threshold=_destination_threshold(next_query),
                    observed_signal=observed_signal,
                )
            elif (
                decision["planner_provider"]
                in {
                    "python_visual_reobserve_gate",
                    "python_transient_navigation_wait_gate",
                }
                or "python_promotional_modal_dismiss_guard"
                in str(decision["planner_provider"])
            ):
                verified = VerifiedTransition(
                    outcome_type="navigated",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="unknown",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=None,
                )
            elif (
                decision["planner_provider"] == "python_goal_already_satisfied"
                or _goal_already_satisfied(next_query)
            ):
                verified = VerifiedTransition(
                    outcome_type="blocked",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label=(
                        "advanced"
                        if str(decision["screen_fingerprint"]) != next_fingerprint
                        else "unchanged"
                    ),
                    destination_match_after=next_query.destination_match,
                    failure_class="already_satisfied",
                    recovery_action=NavigationAction(name="stop_for_user"),
                )
            elif (
                str(decision["screen_fingerprint"]) != next_fingerprint
                and _is_profile_gate_entry_progress(
                    action_name=str(decision["action_name"]),
                    previous_screen=decision.get("screen_payload", {}),
                    next_screen=effective_next_screen,
                )
            ):
                verified = VerifiedTransition(
                    outcome_type="navigated",
                    state_changed=True,
                    progress_label="advanced",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=None,
                )
            elif (
                str(decision["screen_fingerprint"]) != next_fingerprint
                and next_query.destination_match < _destination_threshold(next_query)
                and _semantic_fast_path_grounded_progress(
                    planner_provider=str(decision["planner_provider"]),
                    goal_id="" if stored_goal is None else stored_goal.goal_id,
                    screen_tokens=next_query.screen.tokens,
                )
            ):
                # A K2 intermediate hub can have less final-destination text
                # than the previous screen even though the grounded semantic
                # fast-path click was correct. Do not turn that expected
                # hierarchy step into a false MobileUse back recovery solely
                # because the final Destination Signature score decreased.
                verified = VerifiedTransition(
                    outcome_type="navigated",
                    state_changed=True,
                    progress_label="advanced",
                    destination_match_after=next_query.destination_match,
                    failure_class="",
                    recovery_action=None,
                )
            else:
                verified = verify_transition(
                    action_name=str(decision["action_name"]),
                    previous_fingerprint=str(decision["screen_fingerprint"]),
                    next_fingerprint=next_fingerprint,
                    destination_match_before=before_match,
                    destination_match_after=next_query.destination_match,
                    destination_threshold=_destination_threshold(next_query),
                    observed_signal=observed_signal,
                )
            if (
                request.execution_succeeded is False
                and str(decision["action_name"]) in {"click", "scroll", "back"}
            ):
                # An Accessibility action can be rejected even though the
                # observed screen remains safe and usable. Keep that failure as
                # runtime evidence, then let the next decision re-observe and
                # choose another action instead of turning it into a human
                # safety handoff.
                verified = VerifiedTransition(
                    outcome_type="blocked",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="unknown",
                    destination_match_after=next_query.destination_match,
                    failure_class="executor_action_not_executed",
                    recovery_action=None,
                )
        if (
            str(decision["planner_provider"]) == "codex_operator"
            and str(decision["action_name"]) != "stop_for_user"
            and verified.outcome_type == "destination_reached"
        ):
            # During supervised collection, a destination-signature score is
            # evidence for the operator, not permission to terminate the
            # episode. Intermediate pages often repeat the goal text (for
            # example, a cancellation request page before the final CTA).
            # Only an explicit operator handoff may end that path.
            screen_changed = str(decision["screen_fingerprint"]) != next_fingerprint
            verified = VerifiedTransition(
                outcome_type="navigated",
                state_changed=screen_changed,
                progress_label="advanced" if screen_changed else "unknown",
                destination_match_after=next_query.destination_match,
                failure_class="",
                recovery_action=None,
            )
        candidate_forbidden = False
        knowledge_revision_queued = False
        candidate_id = decision.get("candidate_id")
        if (
            request.connectivity_status == "observed"
            and request.execution_succeeded is not False
            and candidate_id
            and verified.failure_class != "already_satisfied"
            and verified.outcome_type
            in {"no_change", "wrong_destination", "external_app", "infinite_feed", "blocked"}
        ):
            recovery_name = (
                verified.recovery_action.name if verified.recovery_action is not None else "reselect"
            )
            self.store.remember_failure(
                session_id=str(decision["session_id"]),
                screen_fingerprint=str(decision["screen_fingerprint"]),
                candidate_id=str(candidate_id),
                failure_signature=verified.failure_class or verified.outcome_type,
                recovery_action=recovery_name,
            )
            candidate_forbidden = True
        session_status = None
        if verified.outcome_type == "destination_reached":
            session_status = "reached"
        elif (
            verified.outcome_type == "blocked"
            and verified.failure_class != "executor_action_not_executed"
        ) or decision["action_name"] == "stop_for_user":
            session_status = "stopped"
        terminal_reason = request.terminal_reason
        if terminal_reason is None:
            if verified.outcome_type == "destination_reached":
                terminal_reason = "destination_reached"
            elif decision["action_name"] == "stop_for_user":
                terminal_reason = "safe_user_handoff"
            elif request.observed_signal == "login_required":
                terminal_reason = "login_required"
            elif request.observed_signal == "network_error":
                terminal_reason = "network_error"
            elif request.connectivity_status == "device_disconnected":
                terminal_reason = "device_disconnected"
            elif request.connectivity_status == "transport_error":
                terminal_reason = "transport_error"
            elif session_status == "stopped":
                terminal_reason = "safe_user_handoff"
        observation_id = self.store.record_observation(
            observation_id=f"navo_{uuid.uuid4().hex}",
            request_id=request.request_id,
            decision_id=request.decision_id,
            connectivity_status=request.connectivity_status,
            next_screen_fingerprint=next_fingerprint,
            state_changed=verified.state_changed,
            outcome_type=verified.outcome_type,
            progress_label=verified.progress_label,
            destination_match_before=before_match,
            destination_match_after=verified.destination_match_after,
            failure_class=verified.failure_class,
            next_screen=effective_next_screen,
            session_status=session_status,
            terminal_reason=terminal_reason,
            handoff_reason=request.handoff_reason,
            outcome_judge=request.outcome_judge,
            evaluator_id=request.evaluator_id,
            evaluator_version=request.evaluator_version,
            after_screenshot_data_url=(
                request.after_raw_screenshot_data_url
                or request.after_screenshot_data_url
            ),
        )
        procedure_observation = None
        if self.extension is not None and next_query is not None:
            procedure_facts = {
                "screen": build_procedure_screen_facts(
                    next_query,
                    destination_threshold=_destination_threshold(next_query),
                ),
                "outcome": {
                    "type": verified.outcome_type,
                    "progress": verified.progress_label,
                    "state_changed": verified.state_changed,
                },
            }
            try:
                procedure_observation = self.extension.observe_procedure(
                    session_id=str(decision["session_id"]),
                    decision_id=request.decision_id,
                    observation_id=observation_id,
                    facts=procedure_facts,
                )
            except (OSError, ValueError, sqlite3.Error) as error:
                LOGGER.warning(
                    "navigation_procedure_observation_skipped failure_class=%s detail=%s",
                    type(error).__name__,
                    str(error)[:500],
                )
        if candidate_forbidden:
            recent_history = self.store.recent_history(str(decision["session_id"]), limit=20)
            failure_steps = [
                int(item["step_ordinal"])
                for item in recent_history
                if item.get("failure_class")
                or item.get("progress_label") in {"unchanged", "regressed"}
            ]
            first_failure_step = min(failure_steps, default=int(decision["step_ordinal"]))
            self.store.queue_knowledge_revision(
                revision_id=f"navr_{uuid.uuid4().hex}",
                session_id=str(decision["session_id"]),
                decision_id=request.decision_id,
                goal_id=decision.get("goal_id"),
                first_failure_step=first_failure_step,
                revision_operator="Highlight",
                proposed_patch={
                    "scope": "same_goal_semantic_screen_candidate",
                    "screen_fingerprint": decision["screen_fingerprint"],
                    "candidate_id": candidate_id,
                    "failure_signature": verified.failure_class or verified.outcome_type,
                    "recommended_effect": "negative_evidence_pending_human_or_replay_validation",
                },
            )
            knowledge_revision_queued = True
        if request.connectivity_status != "observed":
            reflection_level, reflection_reason = (
                "none",
                "transport/device failure is retried without UI-failure reflection",
            )
        else:
            recent_history = self.store.recent_history(str(decision["session_id"]), limit=5)
            reflection_level, reflection_reason = self.reflection_policy.choose_level(
                outcome_type=verified.outcome_type,
                execution_succeeded=request.execution_succeeded,
                action_confidence=float(decision["confidence"]),
                reflection_on_demand=bool(decision["reflection_on_demand"]),
                action_name=str(decision["action_name"]),
                recent_history=recent_history,
            )
            reflection_result = None
            if (
                reflection_level == "action"
                and request.before_screenshot_data_url
                and request.after_screenshot_data_url
                and self.policy.exaone_vlm.configured
            ):
                try:
                    reflection_result = self.policy.exaone_vlm.reflect_action(
                        goal_text=str(decision["goal_text_redacted"]),
                        action={
                            "name": decision["action_name"],
                            "candidate_id": decision.get("candidate_id"),
                            "direction": decision.get("scroll_direction"),
                        },
                        expected_outcome=str(decision["plan"].get("expected_outcome", "")),
                        before_screenshot_data_url=request.before_screenshot_data_url,
                        after_screenshot_data_url=request.after_screenshot_data_url,
                        semantic_observation={
                            "outcome_type": verified.outcome_type,
                            "progress_label": verified.progress_label,
                            "state_changed": verified.state_changed,
                        },
                    )
                except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
                    reflection_result = None
            elif reflection_level == "trajectory" and self.policy.planner_model.configured:
                try:
                    reflection_result = self.policy.planner_model.reflect_trajectory(
                        goal={
                            "goal_id": decision.get("goal_id"),
                            "text_redacted": decision["goal_text_redacted"],
                        },
                        plan=decision["plan"],
                        recent_history=recent_history,
                        latest_observation={
                            "outcome_type": verified.outcome_type,
                            "progress_label": verified.progress_label,
                            "state_changed": verified.state_changed,
                            "failure_class": verified.failure_class,
                        },
                    )
                except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
                    reflection_result = None
            elif reflection_level == "global" and self.policy.planner_model.configured:
                try:
                    reflection_result = self.policy.planner_model.reflect_global(
                        goal={
                            "goal_id": decision.get("goal_id"),
                            "text_redacted": decision["goal_text_redacted"],
                        },
                        plan=decision["plan"],
                        destination_match=verified.destination_match_after,
                        recent_history=recent_history,
                    )
                except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
                    reflection_result = None
            if reflection_result is not None:
                reflection_reason = f"{reflection_reason}; {reflection_result.reason}"[:1000]
                recovery_hint = _validated_reflection_recovery_hint(
                    reflection_result.recovery_hint,
                    outcome_type=verified.outcome_type,
                    decision_action_name=str(decision["action_name"]),
                    terminal_reason=terminal_reason,
                )
                if recovery_hint is not None:
                    verified = VerifiedTransition(
                        verified.outcome_type,
                        verified.state_changed,
                        verified.progress_label,
                        verified.destination_match_after,
                        verified.failure_class,
                        NavigationAction(name=recovery_hint),
                    )
        final_session_status = session_status or "active"
        if (
            request.connectivity_status == "observed"
            and verified.recovery_action is not None
            and verified.recovery_action.name == "stop_for_user"
            and final_session_status != "reached"
        ):
            final_session_status = "stopped"
            terminal_reason = terminal_reason or "safe_user_handoff"
            self.store.set_session_status(
                str(decision["session_id"]),
                final_session_status,
                terminal_reason=terminal_reason,
                handoff_reason=request.handoff_reason,
                append_event=False,
            )
        self.store.record_execution_details(
            request_id=request.request_id,
            decision_id=request.decision_id,
            observation_id=observation_id,
            connectivity_status=request.connectivity_status,
            execution_succeeded=request.execution_succeeded,
            observed_signal=request.observed_signal,
            recovery_action=verified.recovery_action,
            candidate_forbidden=candidate_forbidden,
            reflection_level=reflection_level,
            reflection_reason=reflection_reason,
            execution_report=request.execution_report,
        )
        return ObserveResponse(
            request_id=request.request_id,
            session_id=str(decision["session_id"]),
            decision_id=request.decision_id,
            outcome_type=verified.outcome_type,
            connectivity_status=request.connectivity_status,
            state_changed=verified.state_changed,
            progress_label=verified.progress_label,
            destination_match_before=before_match,
            destination_match_after=verified.destination_match_after,
            failure_class=verified.failure_class,
            recovery_action=verified.recovery_action,
            candidate_forbidden=candidate_forbidden,
            reflection_triggered=reflection_level != "none",
            reflection_level=reflection_level,
            reflection_reason=reflection_reason,
            knowledge_revision_queued=knowledge_revision_queued,
            session_status=final_session_status,
            planner_decision_succeeded=decision["safety_status"] == "allowed",
            executor_action_succeeded=request.execution_succeeded,
            screen_changed=verified.state_changed,
            navigation_progressed=(
                True
                if verified.progress_label in {"advanced", "reached"}
                else False
                if verified.progress_label in {"unchanged", "regressed"}
                else None
            ),
            connection_error=request.connectivity_status != "observed",
            procedure_id=(
                procedure_observation.procedure_id if procedure_observation else None
            ),
            procedure_step_ordinal=(
                procedure_observation.current_step_ordinal if procedure_observation else None
            ),
            procedure_completed=(
                procedure_observation.procedure_completed if procedure_observation else False
            ),
        )


def _unambiguous_db_goal_phrase(
    *,
    memory: NavigationDecisionMemory,
    goal_text: str,
    locale: str,
    goal_id: str,
) -> bool:
    normalized_text = normalize_text(goal_text)
    if not normalized_text:
        return False
    matched_goal_ids: set[str] = set()
    selected_negative_hit = False
    for item in memory.goal_catalog(locale=locale):
        item_goal_id = str(item.get("goal_id", ""))
        positive_phrases = item.get("positive_phrases", [])
        negative_phrases = item.get("negative_phrases", [])
        if isinstance(positive_phrases, list) and any(
            (normalized_phrase := normalize_text(str(phrase)))
            and normalized_phrase in normalized_text
            for phrase in positive_phrases
        ):
            matched_goal_ids.add(item_goal_id)
        if item_goal_id == goal_id and isinstance(negative_phrases, list):
            selected_negative_hit = any(
                (normalized_phrase := normalize_text(str(phrase)))
                and normalized_phrase in normalized_text
                for phrase in negative_phrases
            )
    return matched_goal_ids == {goal_id} and not selected_negative_hit


def _can_request_visual_reobserve(
    request: DecideRequest,
    perception: PerceptionOutput,
    policy: AndroidWorldResearchPolicy,
) -> bool:
    return (
        not request.visual_reasoning_required
        and perception.provider != policy.exaone_vlm.name
        and policy.exaone_vlm.configured
        and policy.vlm_mode != "disabled"
    )


def _contextualize_membership_cancellation_safety(
    screen: ScreenObservation,
    goal_id: str | None,
) -> ScreenObservation:
    """Raise generic cancellation CTAs to high risk using grounded screen text."""

    if goal_id != "membership.cancel" or not screen.candidates:
        return screen
    context_parts = [screen.window_title, screen.activity_name]
    for node in screen.nodes:
        if node.private_input:
            continue
        context_parts.extend((node.text, node.content_description))
    for candidate in screen.candidates:
        context_parts.extend(
            (
                candidate.label,
                candidate.icon_semantics,
                candidate.nearby_text,
                candidate.parent_semantics,
                candidate.child_semantics,
            )
        )
    screen_context = " ".join(part for part in context_parts if part)
    updated = []
    changed = False
    for candidate in screen.candidates:
        if (
            candidate.risk_level not in {"high", "blocked"}
            and is_contextual_membership_cancellation_action(
                candidate.label,
                screen_context,
            )
        ):
            updated.append(candidate.model_copy(update={"risk_level": "high"}))
            changed = True
        else:
            updated.append(candidate)
    return screen.model_copy(update={"candidates": updated}) if changed else screen


def _transient_navigation_control_waits(
    *,
    screen: ScreenObservation,
    screen_fingerprint: str,
    recent_history: Sequence[dict[str, object]],
) -> int | None:
    """Detect a sparse transition surface whose only affordance navigates away.

    A model must not turn the absence of forward controls into confidence that
    a generic Up/Back icon is the next forward action.  We allow two bounded
    observations (the first can request VLM context), then navigate back.
    """

    # Accessibility trees for WebView/loading surfaces can contain many
    # non-clickable or off-screen nodes even when the only executable control
    # is Navigate Up.  Candidate sparsity, not raw node count, is the reliable
    # signal here.
    if len(screen.candidates) != 1:
        return None
    candidate = screen.candidates[0]
    if (
        not candidate.clickable
        or not candidate.enabled
        or candidate.risk_level != "low"
        or candidate.role.casefold() not in {"button", "icon_button", "image_button"}
    ):
        return None
    semantics = " ".join(
        (
            candidate.label,
            candidate.icon_semantics,
            candidate.nearby_text,
            candidate.parent_semantics,
        )
    ).casefold()
    navigation_markers = (
        "위로 이동",
        "뒤로",
        "이전 화면",
        "navigate up",
        "navigate_up",
        "go back",
    )
    if not any(marker in semantics for marker in navigation_markers):
        return None
    return sum(
        str(item.get("screen_fingerprint", "")) == screen_fingerprint
        and str(item.get("action_name", "")) == "wait_and_observe"
        for item in recent_history
    )


def _empty_candidate_screen_waits(
    *,
    screen: ScreenObservation,
    screen_fingerprint: str,
    recent_history: Sequence[dict[str, object]],
) -> int | None:
    if screen.candidates:
        return None
    return sum(
        str(item.get("screen_fingerprint", "")) == screen_fingerprint
        and str(item.get("action_name", "")) == "wait_and_observe"
        for item in recent_history
    )


def _dismissible_modal_fast_path_candidate_id(
    screen: ScreenObservation,
) -> str | None:
    title = " ".join((screen.window_title, screen.activity_name)).casefold()
    title_confirms_modal = any(
        marker in title
        for marker in ("팝업", "대화상자", "popup", "modal", "dialog", "overlay")
    )
    candidate_semantics = " ".join(
        " ".join(
            (
                candidate.label,
                candidate.icon_semantics,
                candidate.visual_role,
                candidate.parent_semantics,
            )
        ).casefold()
        for candidate in screen.candidates
    )
    feedback_overlay = any(
        marker in candidate_semantics
        for marker in (
            "사용자 피드백 입력",
            "추천/비추천 버튼 그룹",
            "recommendation feedback",
            "rating feedback",
        )
    ) or (
        any(marker in candidate_semantics for marker in ("맘에 안 들어요", "비추천", "dislike"))
        and any(marker in candidate_semantics for marker in ("좋아요", "최고예요", "like"))
    )
    private_input_detour = any(node.private_input for node in screen.nodes) and any(
        candidate.risk_level == "blocked" for candidate in screen.candidates
    )
    if not (title_confirms_modal or feedback_overlay or private_input_detour):
        return None
    dismiss_labels = {
        "닫기",
        "나중에",
        "뒤로",
        "back",
        "close",
        "dismiss",
        "not now",
        "maybe later",
    }
    dismiss_candidates = [
        candidate
        for candidate in screen.candidates
        if " ".join(candidate.label.casefold().split()) in dismiss_labels
        and candidate.clickable
        and candidate.enabled
        and not candidate.selected
        and candidate.risk_level == "low"
    ]
    if len(dismiss_candidates) != 1:
        return None
    return dismiss_candidates[0].candidate_id


def _interleaved_repeat_guard(
    action: NavigationAction,
    *,
    recent_history: Sequence[Mapping[str, object]],
) -> NavigationAction | None:
    """Break click -> visual wait -> same click loops without a false handoff."""

    if action.name != "click" or not action.candidate_id:
        return None
    prior_index = None
    for index in range(len(recent_history) - 1, -1, -1):
        item = recent_history[index]
        if (
            str(item.get("action_name", "")) == "click"
            and str(item.get("candidate_id", "")) == action.candidate_id
        ):
            prior_index = index
            break
    if prior_index is None:
        return None
    prior = recent_history[prior_index]
    if (
        str(prior.get("connectivity_status", "")) != "observed"
        or str(prior.get("progress_label", "")) in {"advanced", "reached"}
    ):
        return None
    waits_since = sum(
        str(item.get("action_name", "")) == "wait_and_observe"
        for item in recent_history[prior_index + 1 :]
    )
    # Repeated non-progress is a navigation problem, not proof of a dangerous
    # user boundary. After one visual re-observation, back out and let the
    # planner try another grounded route while the collector stays active.
    return NavigationAction(name="back" if waits_since >= 2 else "wait_and_observe")


def _selected_reverse_navigation_guard(
    action: NavigationAction,
    *,
    candidates: Sequence[NavigationCandidate],
    nodes: Sequence[AccessibilityNodeSummary],
    screen_fingerprint: str,
    recent_history: Sequence[Mapping[str, object]],
) -> NavigationAction | None:
    """Require the dedicated ``back()`` action for reverse navigation."""

    if action.name != "click" or not action.candidate_id:
        return None
    candidate = next(
        (item for item in candidates if item.candidate_id == action.candidate_id),
        None,
    )
    grounded_node = next(
        (item for item in nodes if item.node_id == action.candidate_id),
        None,
    )
    node_semantics = (
        ""
        if grounded_node is None
        else " ".join((grounded_node.text, grounded_node.content_description)).casefold()
    )
    node_is_reverse = any(
        marker in node_semantics
        for marker in (
            "위로 이동",
            "뒤로",
            "이전 화면",
            "navigate up",
            "go back",
            "back button",
        )
    )
    candidate_is_reverse = (
        candidate is not None and _is_reverse_navigation_candidate(candidate)
    )
    structural_reverse = (
        candidate is not None
        and len(candidates) == 1
        and candidate.role.casefold() in {"icon_button", "image_button"}
        and candidate.position_bucket == "top"
    )
    LOGGER.debug(
        "reverse_navigation_gate candidate_found=%s candidate_reverse=%s "
        "node_found=%s node_reverse=%s structural_reverse=%s candidate_count=%d "
        "node_count=%d",
        candidate is not None,
        candidate_is_reverse,
        grounded_node is not None,
        node_is_reverse,
        structural_reverse,
        len(candidates),
        len(nodes),
    )
    if candidate is None or not (
        candidate_is_reverse or node_is_reverse or structural_reverse
    ):
        return None
    waits = sum(
        str(item.get("screen_fingerprint", "")) == screen_fingerprint
        and str(item.get("action_name", "")) == "wait_and_observe"
        for item in recent_history[-5:]
    )
    # A repeated reverse-control proposal proves a navigation stall, not a
    # dangerous user boundary. Back out after bounded re-observation so the
    # collector can continue from another grounded route.
    return NavigationAction(name="back" if waits >= 2 else "wait_and_observe")


def _safe_alternate_after_reverse_selection(
    action: NavigationAction,
    *,
    candidates: Sequence[NavigationCandidate],
    candidate_values: Sequence[CandidateValue],
    forbidden_candidate_ids: set[str],
) -> CandidateValue | None:
    """Reuse existing scores to avoid a reverse-control wait loop without another model call."""

    if action.name != "click" or not action.candidate_id:
        return None
    candidates_by_id = {candidate.candidate_id: candidate for candidate in candidates}
    ranked = sorted(
        candidate_values,
        key=lambda value: (-value.final_score, value.candidate_id),
    )
    for value in ranked:
        candidate = candidates_by_id.get(value.candidate_id)
        if (
            candidate is None
            or value.candidate_id == action.candidate_id
            or value.candidate_id in forbidden_candidate_ids
            or value.forbidden
            or value.final_score < 0.55
            or value.risk_level != "low"
            or candidate.risk_level != "low"
            or not candidate.clickable
            or not candidate.enabled
            or candidate.selected
            or _is_reverse_navigation_candidate(candidate)
            or not " ".join(
                (candidate.label, candidate.icon_semantics, candidate.visual_role)
            ).strip()
        ):
            continue
        return value
    return None


def _safe_ranked_values(
    values: Sequence[CandidateValue],
    candidates: Sequence[NavigationCandidate],
) -> list[CandidateValue]:
    allowed = {
        candidate.candidate_id
        for candidate in candidates
        if candidate.clickable and candidate.enabled and candidate.risk_level == "low"
    }
    return sorted(
        (
            value
            for value in values
            if value.candidate_id in allowed and not value.forbidden
        ),
        key=lambda value: (-value.final_score, value.candidate_id),
    )


def _candidate_score_visual_reason(
    values: Sequence[CandidateValue],
    candidates: Sequence[NavigationCandidate],
    margin_threshold: float,
) -> str:
    if not candidates:
        return "no_grounded_candidates"
    normalized_labels = [" ".join(candidate.label.casefold().split()) for candidate in candidates]
    if any(not label for label in normalized_labels):
        return "accessibility_candidate_semantics_missing"
    if any(len(candidate.label.strip()) > 160 for candidate in candidates):
        return "accessibility_candidate_text_merged"
    nonempty_labels = [label for label in normalized_labels if label]
    if len(nonempty_labels) != len(set(nonempty_labels)):
        return "accessibility_candidate_labels_duplicated"
    ranked = _safe_ranked_values(values, candidates)
    if len(ranked) < 2:
        return ""
    if ranked[0].final_score - ranked[1].final_score < margin_threshold:
        return "candidate_scores_too_close"
    return ""


def _db_solar_conflict_visual_reason(
    memory_values: Sequence[CandidateValue],
    candidates: Sequence[NavigationCandidate],
    proposal: PlannerProposal,
    model_values: Sequence[CandidateValue],
) -> str:
    model_was_used = proposal.provider.startswith("solar") or any(
        value.score_source == "planner_model_verifier"
        or value.verifier_score is not None
        for value in model_values
    )
    if not model_was_used:
        return ""
    ranked = _safe_ranked_values(memory_values, candidates)
    if not ranked:
        return ""
    memory_best = ranked[0]
    if memory_best.supporting_cases <= 0:
        return ""
    selected_id = (
        proposal.action.candidate_id if proposal.action.name == "click" else None
    )
    if selected_id != memory_best.candidate_id:
        return "db_solar_candidate_conflict"
    return ""


def _validated_reflection_recovery_hint(
    recovery_hint: str,
    *,
    outcome_type: str,
    decision_action_name: str,
    terminal_reason: str | None,
) -> str | None:
    """Keep model reflection advisory unless a user boundary is already proven."""

    if recovery_hint == "reselect":
        return None
    if recovery_hint != "stop_for_user":
        return recovery_hint
    if decision_action_name == "stop_for_user" or terminal_reason:
        return "stop_for_user"
    if outcome_type in {"destination_reached", "login_required"}:
        return "stop_for_user"
    return None


def verify_transition(
    *,
    action_name: str,
    previous_fingerprint: str,
    next_fingerprint: str,
    destination_match_before: float,
    destination_match_after: float,
    destination_threshold: float,
    observed_signal: str,
) -> VerifiedTransition:
    """DroidRun-inspired post-action verification using observed state only."""

    state_changed = previous_fingerprint != next_fingerprint
    signal_outcomes = {
        "external_app": ("external_app", "regressed", "observed_external_app", "back"),
        "login_required": ("login_required", "unknown", "observed_login_required", "stop_for_user"),
        "popup": ("popup", "unknown", "observed_popup", "wait_and_observe"),
        "infinite_feed": ("infinite_feed", "regressed", "observed_infinite_feed", "back"),
        "network_error": ("network_error", "unknown", "observed_network_error", "wait_and_observe"),
        "blocked": ("blocked", "unknown", "observed_blocked", "stop_for_user"),
    }
    if observed_signal in signal_outcomes:
        outcome, progress, failure, recovery = signal_outcomes[observed_signal]
        return VerifiedTransition(
            outcome,
            state_changed,
            progress,
            destination_match_after,
            failure,
            NavigationAction(name=recovery),
        )
    # A foreign app, login wall, popup, network error, or blocked executor is
    # an observed state boundary.  It must take precedence over a coincidental
    # destination-signature match on that new screen.
    if destination_match_after >= destination_threshold:
        return VerifiedTransition(
            "destination_reached",
            state_changed,
            "reached",
            destination_match_after,
            "",
            NavigationAction(name="stop_for_user"),
        )
    if not state_changed:
        failure = "observed_click_no_change" if action_name == "click" else "observed_no_change"
        return VerifiedTransition(
            "no_change",
            False,
            "unchanged",
            destination_match_after,
            failure,
            None,
        )
    delta = destination_match_after - destination_match_before
    if delta >= 0.08:
        return VerifiedTransition(
            "navigated", True, "advanced", destination_match_after, "", None
        )
    if delta <= -0.08:
        return VerifiedTransition(
            "wrong_destination",
            True,
            "regressed",
            destination_match_after,
            "semantic_distance_increased",
            NavigationAction(name="back"),
        )
    return VerifiedTransition("navigated", True, "unknown", destination_match_after, "", None)


def _semantic_fast_path_grounded_progress(
    *,
    planner_provider: str,
    goal_id: str,
    screen_tokens: Sequence[str],
) -> bool:
    """Recognize an observed K2 intermediate without trusting app identity."""

    if planner_provider == "semantic_destination_scroll_fast_path":
        return True
    privacy_hub_guarded = (
        "python_account_delete_privacy_entry_guard" in planner_provider
    )
    explicit_account_guarded = (
        "python_account_delete_explicit_account_guard" in planner_provider
    )
    provider_gateway_guarded = (
        "python_account_delete_provider_gateway_guard" in planner_provider
    )
    if planner_provider not in {
        "semantic_intermediate_role_fast_path",
        "semantic_safe_goal_entry_fast_path",
    } and not any(
        (
            privacy_hub_guarded,
            explicit_account_guarded,
            provider_gateway_guarded,
        )
    ):
        return False
    tokens = {str(token).casefold().strip() for token in screen_tokens if str(token).strip()}
    text = " ".join(sorted(tokens))
    account_hub_markers = (
        "계정",
        "프로필",
        "내 정보",
        "마이페이지",
        "개인 정보",
        "개인정보",
        "설정",
        "관리",
        "account",
        "profile",
        "personal info",
        "privacy",
        "settings",
        "management",
    )
    membership_markers = (
        "멤버십",
        "멤버쉽",
        "구독 관리",
        "이용권",
        "요금제",
        "플랜",
        "membership",
        "manage subscription",
        "subscription settings",
        "pass",
        "plan",
    )
    signup_markers = (
        "회원가입",
        "계정 만들기",
        "가입하기",
        "sign up",
        "create account",
        "register",
    )
    if privacy_hub_guarded:
        # SemanticScreenState tokenizes multi-word labels.  Match both the
        # compact Korean form (개인정보) and split forms (개인/정보/보호)
        # rather than requiring a phrase to survive tokenization verbatim.
        has_privacy = any(
            "privacy" in token
            or "개인정보" in token
            or "개인 정보" in token
            for token in tokens
        )
        has_split_personal_info = (
            {"개인", "정보"}.issubset(tokens)
            or {"personal", "information"}.issubset(tokens)
        )
        has_protection_context = bool(
            tokens & {"보호", "설정", "privacy", "protection", "settings"}
        )
        return goal_id == "account.delete" and (
            has_privacy or (has_split_personal_info and has_protection_context)
        )
    if provider_gateway_guarded:
        return goal_id == "account.delete" and any(
            marker in text for marker in ("계정", "account")
        )
    if explicit_account_guarded:
        return goal_id == "account.delete" and any(
            marker in text
            for marker in ("계정", "내 계정", "account", "my account")
        )
    if goal_id == "account.delete":
        return any(marker in text for marker in account_hub_markers)
    if goal_id == "account.signup":
        return any(marker in text for marker in (*signup_markers, *account_hub_markers))
    if goal_id.startswith("membership."):
        return any(
            marker in text
            for marker in (*membership_markers, *account_hub_markers)
        )
    return False


def _is_profile_gate_entry_progress(
    *,
    action_name: str,
    previous_screen: Mapping[str, object],
    next_screen: ScreenObservation,
) -> bool:
    """Treat profile selection into an app home as entry, not regression."""

    if action_name != "click":
        return False
    previous_candidates = previous_screen.get("candidates", [])
    previous_text = " ".join(
        (
            str(previous_screen.get("window_title") or ""),
            str(previous_screen.get("activity_name") or ""),
            *(
                " ".join(
                    str(candidate.get(field) or "")
                    for field in ("label", "icon_semantics", "nearby_text")
                )
                for candidate in previous_candidates
                if isinstance(candidate, Mapping)
            ),
        )
    ).casefold()
    profile_gate_markers = (
        "프로필을 선택",
        "시청할 프로필",
        "choose a profile",
        "select profile",
        "who's watching",
    )
    if not any(marker in previous_text for marker in profile_gate_markers):
        return False
    next_text = " ".join(
        (
            next_screen.window_title,
            next_screen.activity_name,
            *(
                " ".join((candidate.label, candidate.icon_semantics, candidate.nearby_text))
                for candidate in next_screen.candidates
            ),
        )
    ).casefold()
    home_markers = ("홈", "home")
    navigation_markers = ("검색", "search", "나의", "my ", "browse")
    return any(marker in next_text for marker in home_markers) and any(
        marker in next_text for marker in navigation_markers
    )


def _build_shadow_safety_context(
    *,
    action: NavigationAction,
    proposed_action: NavigationAction,
    plan_stage: str,
    planner_provider: str,
    confidence: float,
    consulted_rule_ids: Sequence[str],
    candidates: Sequence[NavigationCandidate],
    policy_blocked: bool,
) -> SafetyContext:
    boundary_evidence = "none"
    boundary_candidate_id = None
    if action.name == "stop_for_user":
        effect_class = (
            "goal_reached"
            if "goal_already_satisfied" in planner_provider
            else "user_handoff"
        )
        boundary = True
        confirmation_required = effect_class != "goal_reached"
        if proposed_action.name == "click" and proposed_action.candidate_id:
            boundary_evidence = "dangerous_candidate"
            boundary_candidate_id = proposed_action.candidate_id
        elif policy_blocked:
            boundary_evidence = "policy_block"
        elif "authentication_boundary" in planner_provider:
            boundary_evidence = "authentication_boundary"
        elif (
            plan_stage == "terminal_boundary"
            or "goal_already_satisfied" in planner_provider
            or "terminal_boundary" in planner_provider
        ):
            dangerous = [
                candidate.candidate_id
                for candidate in candidates
                if candidate.risk_level in {"high", "blocked"}
                or is_state_changing_action_label(candidate.label)
                or normalize_text(candidate.label)
                in {
                    "가입하기",
                    "계정 만들기",
                    "sign up",
                    "create account",
                    "register",
                }
                or is_dangerous_final_candidate(
                    " ".join(
                        (
                            candidate.label,
                            candidate.icon_semantics,
                            candidate.nearby_text,
                            candidate.parent_semantics,
                        )
                    )
                )
            ]
            if len(dangerous) == 1:
                boundary_evidence = "dangerous_candidate"
                boundary_candidate_id = dangerous[0]
            else:
                boundary_evidence = "destination_signature"
    elif plan_stage == "selective_recovery":
        effect_class = "automatic_recovery"
        boundary = False
        confirmation_required = False
    elif action.name == "wait_and_observe":
        effect_class = "observe_only"
        boundary = False
        confirmation_required = False
    else:
        effect_class = "navigate_only"
        boundary = False
        confirmation_required = False
    return SafetyContext(
        policy_version="boundary-v2-shadow",
        procedure_stage=plan_stage or "unknown",
        effect_class=effect_class,
        boundary=boundary,
        confirmation_required=confirmation_required,
        boundary_evidence=boundary_evidence,
        boundary_candidate_id=boundary_candidate_id,
        target_confidence=round(max(0.0, min(1.0, confidence)), 4),
        reason_code=planner_provider[:300],
        consulted_rule_ids=list(consulted_rule_ids)[:10],
        rule_conflict=False,
        pending_revision=False,
        shadow_mode=True,
    )


def _planner_stop_has_grounded_boundary(*, planner_provider: str, plan_stage: str) -> bool:
    return plan_stage == "terminal_boundary" or planner_provider.startswith(
        (
            "python_goal_gate",
            "python_terminal_boundary",
            "python_goal_already_satisfied",
            "python_authentication_boundary",
            "python_state_change_boundary",
        )
    )


def _automatic_recovery_forbidden_candidates(
    *,
    screen_fingerprint: str,
    candidates: Sequence[NavigationCandidate],
    recent_history: Sequence[Mapping[str, object]],
    goal_id: str | None,
) -> set[str]:
    """Suppress no-op navigation targets while preserving other safe choices."""

    forbidden = {
        candidate.candidate_id
        for candidate in candidates
        if candidate.selected and candidate.clickable and candidate.enabled
    }
    for item in recent_history:
        if (
            screen_fingerprint
            and str(item.get("screen_fingerprint", "")) == screen_fingerprint
            and str(item.get("action_name", "")) == "click"
        ):
            candidate_id = str(item.get("candidate_id", "")).strip()
            if candidate_id:
                forbidden.add(candidate_id)

    def semantic_signature(
        candidate_id: object,
        label: object,
        icon_semantics: object,
        nearby_text: object,
        parent_semantics: object,
        child_semantics: object,
    ) -> tuple[str, str, str, str, str, str]:
        return tuple(
            " ".join(str(value or "").casefold().split())
            for value in (
                candidate_id,
                label,
                icon_semantics,
                nearby_text,
                parent_semantics,
                child_semantics,
            )
        )

    repeated_semantic_clicks: dict[tuple[str, str, str, str, str, str], int] = {}
    for item in recent_history:
        if (
            str(item.get("connectivity_status", "")) != "observed"
            or str(item.get("action_name", "")) != "click"
        ):
            continue
        signature = semantic_signature(
            item.get("candidate_id"),
            item.get("selected_candidate_label"),
            item.get("selected_candidate_icon_semantics"),
            item.get("selected_candidate_nearby_text"),
            item.get("selected_candidate_parent_semantics"),
            item.get("selected_candidate_child_semantics"),
        )
        # Dynamic counters and banners can continuously change the full-screen
        # fingerprint. A stable candidate plus stable local context is a better
        # signal that a persistent navigation control is being re-clicked.
        if signature[0] and (signature[1] or signature[2]) and any(signature[3:]):
            repeated_semantic_clicks[signature] = (
                repeated_semantic_clicks.get(signature, 0) + 1
            )
    for candidate in candidates:
        signature = semantic_signature(
            candidate.candidate_id,
            candidate.label,
            candidate.icon_semantics,
            candidate.nearby_text,
            candidate.parent_semantics,
            candidate.child_semantics,
        )
        if repeated_semantic_clicks.get(signature, 0) >= 3:
            forbidden.add(candidate.candidate_id)

    if goal_id == "account.delete" or str(goal_id or "").startswith("membership."):
        settings_markers = ("설정", "setting", "계정 관리", "account management")
        has_settings_entry = any(
            any(marker in _candidate_direct_text(candidate) for marker in settings_markers)
            for candidate in candidates
        )
        if has_settings_entry:
            profile_markers = (
                "마이쿠팡",
                "마이페이지",
                "내 페이지",
                "my page",
                "profile",
            )
            for candidate in candidates:
                is_bottom_navigation = (
                    candidate.position_bucket == "bottom"
                    or "bottom" in candidate.visual_region.casefold()
                    or "navigation" in candidate.visual_role.casefold()
                )
                if is_bottom_navigation and any(
                    marker in _candidate_text(candidate) for marker in profile_markers
                ):
                    forbidden.add(candidate.candidate_id)
    return forbidden


def _candidate_text(candidate: NavigationCandidate) -> str:
    return " ".join(
        (
            candidate.label,
            candidate.icon_semantics,
            candidate.nearby_text,
            candidate.parent_semantics,
            candidate.child_semantics,
        )
    ).casefold()


def _candidate_direct_text(candidate: NavigationCandidate) -> str:
    return " ".join((candidate.label, candidate.icon_semantics)).casefold()


def _is_non_plan_payment_method_screen(
    goal_id: str | None,
    screen_tokens: Sequence[str],
) -> bool:
    """Detect an observed payment-method editor reached during plan change."""

    if goal_id != "membership.change":
        return False
    tokens = {str(token).casefold().strip() for token in screen_tokens if str(token).strip()}
    text = " ".join(sorted(tokens))
    has_payment_method = any(
        marker in text for marker in ("결제 수단", "payment method", "billing method")
    ) or {"결제", "수단"}.issubset(tokens)
    has_maintenance = any(
        marker in text
        for marker in (
            "업데이트",
            "갱신",
            "카드 추가",
            "결제 추가",
            "update",
            "add card",
            "add payment",
        )
    ) or bool(tokens & {"업데이트", "갱신", "추가", "update"})
    has_plan_change = any(
        marker in text
        for marker in (
            "요금제 변경",
            "플랜 변경",
            "change plan",
            "switch plan",
            "upgrade",
            "downgrade",
        )
    ) or (
        bool(tokens & {"요금제", "플랜", "plan"})
        and bool(tokens & {"변경", "change", "switch", "upgrade", "downgrade"})
    )
    return has_payment_method and has_maintenance and not has_plan_change


def _successful_back_recovery(
    *,
    action_name: str,
    previous_fingerprint: str,
    next_fingerprint: str,
    session_app_package: str,
    next_app_package: str,
    recent_history: Sequence[Mapping[str, object]],
) -> bool:
    """Recognize a verified return to the screen before a bad transition.

    Destination distance alone is not a valid recovery metric: returning from
    a purchase/enrollment dead end can reduce destination-signature overlap
    while still being the correct MobileUse-style recovery. The result must
    be an actually changed screen inside the original app; consecutive blind
    back actions and external-app exits are therefore not rewarded.
    """

    if (
        action_name != "back"
        or not next_fingerprint
        or previous_fingerprint == next_fingerprint
        or not session_app_package
        or next_app_package != session_app_package
    ):
        return False
    for item in reversed(recent_history):
        if not str(item.get("outcome_type", "")).strip():
            continue
        if str(item.get("action_name", "")) == "back":
            continue
        return (
            str(item.get("connectivity_status", "")) == "observed"
            and str(item.get("action_name", "")) != "back"
            and str(item.get("outcome_type", "")) == "wrong_destination"
            and str(item.get("progress_label", "")) == "regressed"
            and str(item.get("recovery_action", "")) == "back"
        )
    return False


def _requires_authenticated_account(goal_id: str) -> bool:
    return goal_id in {
        "account.delete",
        "membership.cancel",
        "membership.change",
        "membership.manage",
    }


_ACTIVE_MEMBERSHIP_FEATURES = (
    "프리미엄 회원",
    "premium 회원",
    "현재 멤버십",
    "활성 멤버십",
    "구독 중",
    "혜택 이용중",
    "premium member",
    "current membership",
    "active membership",
    "already subscribed",
    "benefits active",
    "benefits in use",
)


def _goal_already_satisfied(query: DecisionMemoryQuery) -> bool:
    """Stop a join request when the observed account is already an active member."""

    if query.goal is None or query.goal.goal_id != "membership.join":
        return False

    # Keep the evidence local to one visible semantic field. A screen-wide token
    # bag can combine unrelated phrases such as "currently playing" and a
    # separate "membership information" navigation label into a false
    # "current membership" match.
    evidence_surfaces = [query.screen.title]
    for candidate in query.screen.candidate_payloads:
        evidence_surfaces.extend(
            str(candidate.get(field, ""))
            for field in (
                "label",
                "icon_semantics",
                "nearby_text",
                "parent_semantics",
                "child_semantics",
                "visual_role",
            )
        )
    surface_token_sets = [set(tokenize(surface)) for surface in evidence_surfaces if surface]
    return any(
        feature_tokens.issubset(surface_tokens)
        for feature in _ACTIVE_MEMBERSHIP_FEATURES
        if (feature_tokens := set(tokenize(feature)))
        for surface_tokens in surface_token_sets
    )


def _is_authentication_boundary(
    goal: NormalizedGoal | None,
    auth_state: str,
    *,
    screen: ScreenObservation | None = None,
) -> bool:
    if goal is None:
        return False
    # Device credential and biometric prompts are user-only authentication
    # boundaries for every goal, including account.signup.  A signup flow may
    # legitimately traverse a normal logged-out screen, so do not treat a
    # generic login/signup surface as terminal for that goal.  Vendor prompts
    # frequently redact their visible text; stable semantic view IDs and the
    # platform package/activity identity therefore provide the grounding.
    if screen is not None and _is_device_credential_prompt(screen):
        return True
    if (
        screen is not None
        and _requires_authenticated_account(goal.goal_id)
        and _is_web_authentication_surface(screen)
    ):
        return True
    if auth_state == "reauthentication":
        return True
    return _requires_authenticated_account(goal.goal_id) and auth_state == "logged_out"


def _is_web_authentication_surface(screen: ScreenObservation) -> bool:
    """Recognize grounded browser login/reauthentication surfaces."""

    identity = " ".join(
        (
            screen.window_title,
            screen.activity_name,
            *(candidate.label for candidate in screen.candidates),
            *(candidate.icon_semantics for candidate in screen.candidates),
            *(candidate.nearby_text for candidate in screen.candidates),
            *(node.view_id for node in screen.nodes),
            *(node.text for node in screen.nodes),
            *(node.content_description for node in screen.nodes),
        )
    ).casefold()
    if any(
        marker in identity
        for marker in (
            "login.",
            "signin.",
            "/login",
            "/signin",
            "비밀번호 확인",
            "비밀번호를 입력",
            "password confirmation",
            "confirm password",
            "sign in to continue",
        )
    ):
        return True
    return any(node.private_input for node in screen.nodes) and any(
        marker in identity
        for marker in ("로그인", "비밀번호", "password", "sign in", "signin")
    )


def _is_device_credential_prompt(screen: ScreenObservation) -> bool:
    identity = " ".join(
        (
            screen.app_package,
            screen.activity_name,
            screen.window_title,
            *(node.view_id for node in screen.nodes),
            *(node.text for node in screen.nodes),
            *(node.content_description for node in screen.nodes),
        )
    ).casefold()
    platform_prompt = any(
        marker in identity
        for marker in (
            "biometric",
            "fingerprint",
            "credential",
            "본인 인증",
            "본인인증",
            "본인 확인",
            "지문을 입력",
            "생체 인증",
            "verify it's you",
            "verify your identity",
        )
    )
    prompt_structure = any(
        marker in identity
        for marker in (
            "prompt_layout",
            "prompt_dialog",
            "use_credential",
            "authenticate",
            "authentication",
            "지문",
            "생체",
            "credential",
        )
    )
    return platform_prompt and prompt_structure


def _goal_resolution(
    goal: NormalizedGoal | None,
    *,
    provider: str,
    validated_against_db: bool,
    fallback_used: bool,
) -> GoalResolution:
    if goal is None:
        return GoalResolution(
            status="out_of_scope",
            goal_id=None,
            confidence=0.0,
            provider=provider,
            validated_against_db=validated_against_db,
            fallback_used=fallback_used,
        )
    status = "recognized" if goal.confidence >= 0.58 else "ambiguous"
    return GoalResolution(
        status=status,
        goal_id=goal.goal_id,
        confidence=goal.confidence,
        provider=provider,
        validated_against_db=validated_against_db,
        fallback_used=fallback_used,
    )


def _destination_threshold(query: DecisionMemoryQuery) -> float:
    thresholds = [
        float(signature.get("threshold", 0.72)) for signature in query.destination_signatures
    ]
    return min(thresholds, default=0.72)
