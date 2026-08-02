from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Sequence

import httpx

from app.navigation_contracts import (
    DecideRequest,
    DecideResponse,
    GoalResolution,
    NavigationAction,
    ObserveRequest,
    ObserveResponse,
)
from app.services.navigation_decision_memory import (
    DecisionMemoryQuery,
    NavigationDecisionMemory,
    NormalizedGoal,
    is_dangerous_final_candidate,
)
from app.services.navigation_dataset_split import NavigationDatasetSplitManifest
from app.services.navigation_planner import PlannerProposal
from app.services.navigation_research_policy import (
    AndroidWorldResearchPolicy,
    ReflectionTriggerPolicy,
)
from app.services.navigation_runtime_store import NavigationRuntimeStore


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
        dataset_split_manifest: NavigationDatasetSplitManifest | None = None,
        allow_locked_holdout: bool = False,
    ) -> None:
        self.memory = memory
        self.store = store
        self.policy = policy
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

    def decide(self, request: DecideRequest) -> DecideResponse:
        if self.dataset_split_manifest is not None:
            self.dataset_split_manifest.require_collection_access(
                request.app_package,
                allow_locked_holdout=self.allow_locked_holdout,
            )
        session_id = request.session_id or f"navs_{uuid.uuid4().hex}"
        perception = self.policy.perceive(
            goal_text=request.goal_text,
            screen=request.screen,
            screenshot_data_url=request.screenshot_data_url,
        )
        effective_screen = perception.screen
        normalized_goal, goal_resolution = self._resolve_goal(
            session_id=session_id,
            goal_text=request.goal_text,
            locale=request.locale,
        )
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
        score_margin = 0.0
        reflection_on_demand = False
        verifier_provider = "not_invoked"
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
        elif effective_screen.candidates and all(
            candidate.risk_level in {"medium", "high", "blocked"}
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
        else:
            research_decision = self.policy.decide_action(
                query=query,
                plan=plan,
                candidates=effective_screen.candidates,
                forbidden_candidate_ids=forbidden,
                recent_history=recent_history,
            )
            plan = research_decision.plan
            planner_provider = plan.source
            proposal = research_decision.proposal
            candidate_values = list(research_decision.candidate_values)
            verifier_provider = research_decision.verifier_provider
            score_margin = research_decision.score_margin
            reflection_on_demand = research_decision.reflection_on_demand
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
            locale=request.locale,
            goal_text=request.goal_text,
            goal_id=None if query.goal is None else query.goal.goal_id,
        )
        evidence_case_ids = [evidence.case_id for evidence in query.evidence]
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
                        provider=f"{self.policy.planner_model.name}_goal_classifier",
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
                    provider=f"{self.policy.planner_model.name}_goal_classifier",
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
                normalized_goal=self.memory.goal_by_id(
                    str(decision.get("goal_id") or ""),
                    confidence=1.0,
                    matched_phrase="stored_decision_goal",
                ),
                resolve_goal_from_text=False,
            )
            next_fingerprint = next_query.screen.semantic_fingerprint
            verified = verify_transition(
                action_name=str(decision["action_name"]),
                previous_fingerprint=str(decision["screen_fingerprint"]),
                next_fingerprint=next_fingerprint,
                destination_match_before=before_match,
                destination_match_after=next_query.destination_match,
                destination_threshold=_destination_threshold(next_query),
                observed_signal=request.observed_signal,
            )
        candidate_forbidden = False
        knowledge_revision_queued = False
        candidate_id = decision.get("candidate_id")
        if (
            request.connectivity_status == "observed"
            and candidate_id
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
        elif verified.outcome_type == "blocked":
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
        )


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
    if destination_match_after >= destination_threshold:
        return VerifiedTransition(
            "destination_reached",
            state_changed,
            "reached",
            destination_match_after,
            "",
            NavigationAction(name="stop_for_user"),
        )
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
