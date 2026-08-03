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
    NavigationAction,
    NavigationCandidate,
    ObserveRequest,
    ObserveResponse,
)
from app.services.navigation_decision_memory import (
    DecisionMemoryQuery,
    NavigationDecisionMemory,
    NormalizedGoal,
    is_dangerous_final_candidate,
    is_state_changing_action_label,
    tokenize,
)
from app.services.navigation_dataset_split import NavigationDatasetSplitManifest
from app.services.navigation_model_clients import PerceptionOutput
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
    ) -> None:
        self.memory = memory
        self.store = store
        self.policy = policy
        self.public_prior = public_prior
        self.dataset_split_manifest = dataset_split_manifest
        self.allow_locked_holdout = allow_locked_holdout
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
            "public_prior": (
                {"enabled": False}
                if self.public_prior is None
                else self.public_prior.status()
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
                "goal_classifier": "solar_db_allowlist_then_python_validation",
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

    def stop_session(self, session_id: str) -> dict[str, object]:
        """Idempotently close one executor session without fabricating a UI outcome."""

        session = self.store.session(session_id)
        if session is None:
            raise KeyError(session_id)
        if session["status"] == "active":
            self.store.set_session_status(session_id, "stopped")
            session = self.store.session(session_id)
            if session is None:  # Defensive: the row cannot disappear under the store lock.
                raise KeyError(session_id)
        return session

    def decide(self, request: DecideRequest) -> DecideResponse:
        if self.dataset_split_manifest is not None:
            self.dataset_split_manifest.require_collection_access(
                request.app_package,
                allow_locked_holdout=self.allow_locked_holdout,
            )
        session_id = request.session_id or f"navs_{uuid.uuid4().hex}"
        normalized_goal, goal_resolution = self._resolve_goal(
            session_id=session_id,
            goal_text=request.goal_text,
            locale=request.locale,
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
        if _is_authentication_boundary(normalized_goal, structured_screen.auth_state):
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
            self.public_prior is not None
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
        forbidden = self.store.forbidden_candidates(session_id, query.screen.semantic_fingerprint)
        recent_history = self.store.recent_history(session_id, limit=5)
        plan, planner_provider, planner_fallback = self.policy.plan(
            query=query,
            forbidden_candidate_ids=forbidden,
            destination_threshold=destination_threshold,
            recent_history=recent_history,
        )
        candidate_values = self.policy.prior_scorer.score(
            query,
            effective_screen.candidates,
            forbidden_candidate_ids=forbidden,
        )
        memory_candidate_values = list(candidate_values)
        profile_gate_fast_path_candidate_id = _profile_gate_existing_entry_candidate_id(
            candidates=request.screen.candidates,
            goal_id=goal_resolution.goal_id,
            screen_title=request.screen.window_title,
            recent_history=recent_history,
            forbidden_candidate_ids=tuple(forbidden),
        ) or _profile_gate_existing_entry_candidate_id(
            candidates=effective_screen.candidates,
            goal_id=goal_resolution.goal_id,
            screen_title=effective_screen.window_title,
            recent_history=recent_history,
            forbidden_candidate_ids=tuple(forbidden),
            visually_recommended_candidate_id=perception.recommended_candidate_id,
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
        semantic_fast_path_candidate_id = (
            profile_gate_fast_path_candidate_id
            or self.policy.semantic_intermediate_fast_path_candidate(
                query=query,
                plan=plan,
                prior_values=memory_candidate_values,
                recent_history=recent_history,
            )
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
        score_margin = 0.0
        reflection_on_demand = False
        verifier_provider = "not_invoked"
        visual_reobserve_reason = ""
        if goal_resolution.status != "recognized":
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
        elif (
            query.goal is not None
            and _requires_authenticated_account(query.goal.goal_id)
            and query.screen.auth_state in {"logged_out", "reauthentication"}
        ):
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                1.0,
                "python_authentication_boundary",
                False,
            )
            planner_provider = "python_authentication_boundary"
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
        elif transient_navigation_waits is not None:
            if transient_navigation_waits >= 2:
                proposal = PlannerProposal(
                    NavigationAction(name="stop_for_user"),
                    1.0,
                    "python_transient_navigation_stall_guard",
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
        sparse_reverse_guard_action = _selected_reverse_navigation_guard(
            proposal.action,
            candidates=effective_screen.candidates,
            nodes=effective_screen.nodes,
            screen_fingerprint=query.screen.semantic_fingerprint,
            recent_history=recent_history,
        )
        if sparse_reverse_guard_action is not None:
            provider = (
                "python_transient_navigation_stall_guard"
                if sparse_reverse_guard_action.name == "stop_for_user"
                else "python_transient_navigation_wait_gate"
            )
            proposal = PlannerProposal(sparse_reverse_guard_action, 1.0, provider, False)
            planner_provider = provider
            verifier_provider = provider
            reflection_on_demand = True
        repeat_guard_action = _interleaved_repeat_guard(
            proposal.action,
            recent_history=recent_history,
        )
        if repeat_guard_action is not None:
            provider = (
                "python_interleaved_repeat_stall_guard"
                if repeat_guard_action.name == "stop_for_user"
                else "python_interleaved_repeat_wait_guard"
            )
            proposal = PlannerProposal(repeat_guard_action, 1.0, provider, False)
            planner_provider = provider
            verifier_provider = provider
            reflection_on_demand = True
        safe_action, safety_status, safety_reason = self.policy.safety_gate.validate(
            proposal.action,
            candidates=effective_screen.candidates,
            forbidden_candidate_ids=forbidden,
        )
        confidence = proposal.confidence if safe_action == proposal.action else 1.0
        decision_id = f"navd_{uuid.uuid4().hex}"
        self.store.upsert_session(
            session_id=session_id,
            request_id=request.request_id,
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            goal_id=None if query.goal is None else query.goal.goal_id,
        )
        evidence_case_ids = [evidence.case_id for evidence in query.evidence]
        evidence_case_ids.extend(
            f"public:{evidence.evidence_id}" for evidence in query.public_prior_evidence
        )
        self.store.record_decision(
            decision_id=decision_id,
            session_id=session_id,
            step_ordinal=request.step_ordinal,
            screen_fingerprint=query.screen.semantic_fingerprint,
            screen=effective_screen,
            goal_id=None if query.goal is None else query.goal.goal_id,
            plan=plan,
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

        fallback_goal = self.memory.normalize_goal(goal_text, locale=locale)
        return fallback_goal, _goal_resolution(
            fallback_goal,
            provider="python_phrase_fallback",
            validated_against_db=fallback_goal is not None,
            fallback_used=fallback_used,
        )

    def observe(self, request: ObserveRequest) -> ObserveResponse:
        decision = self.store.decision(request.decision_id)
        before_match = float(decision["destination_match_before"])
        effective_next_screen = None
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
            if _is_authentication_boundary(stored_goal, structured_next_screen.auth_state):
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
            if _is_authentication_boundary(stored_goal, next_query.screen.auth_state):
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
            elif decision["planner_provider"] in {
                "python_visual_reobserve_gate",
                "python_transient_navigation_wait_gate",
            }:
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
                verified = VerifiedTransition(
                    outcome_type="blocked",
                    state_changed=(
                        str(decision["screen_fingerprint"]) != next_fingerprint
                    ),
                    progress_label="unknown",
                    destination_match_after=next_query.destination_match,
                    failure_class="executor_action_not_executed",
                    recovery_action=NavigationAction(name="stop_for_user"),
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
        elif verified.outcome_type == "blocked" or decision["action_name"] == "stop_for_user":
            session_status = "stopped"
        observation_id = self.store.record_observation(
            observation_id=f"navo_{uuid.uuid4().hex}",
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
                if reflection_result.recovery_hint != "reselect":
                    verified = VerifiedTransition(
                        verified.outcome_type,
                        verified.state_changed,
                        verified.progress_label,
                        verified.destination_match_after,
                        verified.failure_class,
                        NavigationAction(name=reflection_result.recovery_hint),
                    )
        final_session_status = session_status or "active"
        if (
            request.connectivity_status == "observed"
            and verified.recovery_action is not None
            and verified.recovery_action.name == "stop_for_user"
            and final_session_status != "reached"
        ):
            final_session_status = "stopped"
            self.store.set_session_status(str(decision["session_id"]), final_session_status)
        self.store.record_execution_details(
            decision_id=request.decision_id,
            observation_id=observation_id,
            connectivity_status=request.connectivity_status,
            execution_succeeded=request.execution_succeeded,
            observed_signal=request.observed_signal,
            recovery_action=verified.recovery_action,
            candidate_forbidden=candidate_forbidden,
            reflection_level=reflection_level,
            reflection_reason=reflection_reason,
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
        )


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


def _transient_navigation_control_waits(
    *,
    screen: ScreenObservation,
    screen_fingerprint: str,
    recent_history: Sequence[dict[str, object]],
) -> int | None:
    """Detect a sparse transition surface whose only affordance navigates away.

    A model must not turn the absence of forward controls into confidence that
    a generic Up/Back icon is the next forward action.  We allow two bounded
    observations (the first can request VLM context), then stop for the user.
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


def _interleaved_repeat_guard(
    action: NavigationAction,
    *,
    recent_history: Sequence[Mapping[str, object]],
) -> NavigationAction | None:
    """Block click -> visual wait -> same click loops without observed progress."""

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
    return NavigationAction(
        name="stop_for_user" if waits_since >= 2 else "wait_and_observe"
    )


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
    return NavigationAction(name="stop_for_user" if waits >= 2 else "wait_and_observe")


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
    visible_tokens = set(query.screen.tokens)
    return any(
        set(tokenize(feature)).issubset(visible_tokens)
        for feature in _ACTIVE_MEMBERSHIP_FEATURES
    )


def _is_authentication_boundary(
    goal: NormalizedGoal | None,
    auth_state: str,
) -> bool:
    return (
        goal is not None
        and _requires_authenticated_account(goal.goal_id)
        and auth_state in {"logged_out", "reauthentication"}
    )


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
