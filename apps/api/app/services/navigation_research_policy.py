from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Mapping, Sequence

import httpx

from app.navigation_contracts import (
    CandidateValue,
    HierarchicalPlan,
    NavigationAction,
    NavigationCandidate,
    ScreenObservation,
)
from app.services.navigation_decision_memory import DecisionMemoryQuery
from app.services.navigation_model_clients import (
    Exaone45VisionClient,
    KExaoneResearchClient,
    PerceptionOutput,
)
from app.services.navigation_planner import (
    ActionSafetyGate,
    CandidateValueScorer,
    HierarchicalPlanBuilder,
    PlannerProposal,
)


@dataclass(frozen=True)
class ResearchDecision:
    proposal: PlannerProposal
    candidate_values: tuple[CandidateValue, ...]
    verifier_provider: str
    score_margin: float
    reflection_on_demand: bool


@dataclass(frozen=True)
class EnumeratedAction:
    action: NavigationAction
    memory_prior: float
    candidate: NavigationCandidate | None

    def prompt_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"name": self.action.name}
        if self.action.candidate_id:
            payload["candidate_id"] = self.action.candidate_id
        if self.action.direction:
            payload["direction"] = self.action.direction
        if self.candidate is not None:
            payload["candidate"] = self.candidate.model_dump(mode="json")
        return payload


class AndroidWorldResearchPolicy:
    """K² planner + V-Droid verifier + MobileUse reflection triggers.

    The class adapts the architectures; it does not claim to reproduce their
    trained weights or reported AndroidWorld success rates.
    """

    def __init__(
        self,
        *,
        k_exaone: KExaoneResearchClient,
        exaone_vlm: Exaone45VisionClient,
        allow_model_fallback: bool = True,
        max_verified_clicks: int = 12,
        verifier_workers: int = 4,
        reflection_confidence_threshold: float = 0.45,
        reflection_margin_threshold: float = 0.08,
    ) -> None:
        self.k_exaone = k_exaone
        self.exaone_vlm = exaone_vlm
        self.allow_model_fallback = allow_model_fallback
        self.max_verified_clicks = max(1, max_verified_clicks)
        self.verifier_workers = max(1, verifier_workers)
        self.reflection_confidence_threshold = reflection_confidence_threshold
        self.reflection_margin_threshold = reflection_margin_threshold
        self.fallback_planner = HierarchicalPlanBuilder()
        self.prior_scorer = CandidateValueScorer()
        self.safety_gate = ActionSafetyGate()

    def perceive(
        self,
        *,
        goal_text: str,
        screen: ScreenObservation,
        screenshot_data_url: str | None,
    ) -> PerceptionOutput:
        if screenshot_data_url and self.exaone_vlm.configured:
            try:
                return self.exaone_vlm.perceive(
                    goal_text=goal_text,
                    screen=screen,
                    screenshot_data_url=screenshot_data_url,
                )
            except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
                if not self.allow_model_fallback:
                    raise
        return PerceptionOutput(screen=screen, semantic_summary="", provider="structured_input")

    def plan(
        self,
        *,
        query: DecisionMemoryQuery,
        forbidden_candidate_ids: set[str],
        destination_threshold: float,
        recent_history: Sequence[Mapping[str, object]],
    ) -> tuple[HierarchicalPlan, str, bool]:
        fallback = self.fallback_planner.build(
            query,
            forbidden_candidate_ids=forbidden_candidate_ids,
            destination_threshold=destination_threshold,
        )
        if query.goal is None or fallback.stage in {"goal_disambiguation", "terminal_boundary"}:
            return fallback, fallback.source, False
        if not self.k_exaone.configured:
            return fallback, fallback.source, False
        try:
            result = self.k_exaone.plan(
                goal=query.goal.prompt_payload(),
                screen=query.screen.prompt_payload(),
                destination_signatures=query.destination_signatures,
                decision_evidence=[evidence.prompt_payload() for evidence in query.evidence],
                recent_history=recent_history,
                target_roles=fallback.target_roles,
            )
            target_roles = list(result.target_roles) or fallback.target_roles
            return (
                HierarchicalPlan(
                    goal_id=query.goal.goal_id,
                    stage=result.stage,
                    target_roles=target_roles,
                    immediate_subgoal=result.immediate_subgoal or fallback.immediate_subgoal,
                    expected_outcome=result.expected_outcome or fallback.expected_outcome,
                    completion_rule=fallback.completion_rule,
                    source="k_exaone",
                ),
                "k_exaone",
                False,
            )
        except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
            if not self.allow_model_fallback:
                raise
            return fallback, "k_exaone->decision_memory_fallback", True

    def decide_action(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        candidates: Sequence[NavigationCandidate],
        forbidden_candidate_ids: set[str],
        recent_history: Sequence[Mapping[str, object]],
    ) -> ResearchDecision:
        prior_values = self.prior_scorer.score(
            query,
            candidates,
            forbidden_candidate_ids=forbidden_candidate_ids,
        )
        enumerated = self._enumerate_actions(
            candidates=candidates,
            prior_values=prior_values,
            plan=plan,
            recent_history=recent_history,
        )
        if self.k_exaone.configured:
            try:
                scored, updated_values = self._verify_actions(
                    query=query,
                    plan=plan,
                    recent_history=recent_history,
                    enumerated=enumerated,
                    prior_values=prior_values,
                )
                provider = "k_exaone_verifier"
                fallback_used = False
            except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError):
                if not self.allow_model_fallback:
                    raise
                scored = [(item.memory_prior, item) for item in enumerated]
                updated_values = prior_values
                provider = "k_exaone_verifier->decision_memory_fallback"
                fallback_used = True
        else:
            scored = [(item.memory_prior, item) for item in enumerated]
            updated_values = prior_values
            provider = "decision_memory_fallback"
            fallback_used = False
        scored.sort(key=lambda item: (-item[0], _action_sort_key(item[1].action)))
        if not scored:
            proposal = PlannerProposal(
                NavigationAction(name="wait_and_observe"),
                0.0,
                provider,
                fallback_used,
            )
            return ResearchDecision(proposal, tuple(updated_values), provider, 0.0, True)
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = max(0.0, best_score - second_score)
        safe_action, safety_status, _ = self.safety_gate.validate(
            best.action,
            candidates=candidates,
            forbidden_candidate_ids=forbidden_candidate_ids,
        )
        if safety_status != "allowed":
            best_score = 1.0
        proposal = PlannerProposal(
            safe_action,
            max(0.0, min(1.0, best_score)),
            provider,
            fallback_used,
        )
        reflect = (
            best_score < self.reflection_confidence_threshold
            or margin < self.reflection_margin_threshold
        )
        return ResearchDecision(
            proposal=proposal,
            candidate_values=tuple(updated_values),
            verifier_provider=provider,
            score_margin=round(margin, 4),
            reflection_on_demand=reflect,
        )

    def _enumerate_actions(
        self,
        *,
        candidates: Sequence[NavigationCandidate],
        prior_values: Sequence[CandidateValue],
        plan: HierarchicalPlan,
        recent_history: Sequence[Mapping[str, object]],
    ) -> list[EnumeratedAction]:
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        click_values = [
            value
            for value in prior_values
            if not value.forbidden and value.score_source != "safety_blocked"
        ][: self.max_verified_clicks]
        actions = [
            EnumeratedAction(
                NavigationAction(name="click", candidate_id=value.candidate_id),
                value.final_score,
                candidate_by_id[value.candidate_id],
            )
            for value in click_values
        ]
        actions.extend(
            (
                EnumeratedAction(NavigationAction(name="scroll", direction="down"), 0.18, None),
                EnumeratedAction(NavigationAction(name="wait_and_observe"), 0.12, None),
                EnumeratedAction(NavigationAction(name="stop_for_user"), 0.05, None),
            )
        )
        if plan.stage == "selective_recovery" or any(
            str(item.get("progress_label", "")) in {"regressed", "unchanged"}
            for item in recent_history
        ):
            actions.append(EnumeratedAction(NavigationAction(name="back"), 0.2, None))
        return actions

    def _verify_actions(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        recent_history: Sequence[Mapping[str, object]],
        enumerated: Sequence[EnumeratedAction],
        prior_values: Sequence[CandidateValue],
    ) -> tuple[list[tuple[float, EnumeratedAction]], list[CandidateValue]]:
        scores: dict[str, tuple[float, str]] = {}

        def verify(item: EnumeratedAction) -> tuple[str, float, str]:
            output = self.k_exaone.verify_action(
                goal=query.goal.prompt_payload() if query.goal else {},
                subgoal=plan.immediate_subgoal,
                expected_outcome=plan.expected_outcome,
                screen=query.screen.prompt_payload(),
                recent_history=recent_history,
                action=item.prompt_payload(),
                memory_prior=item.memory_prior,
                decision_evidence=[evidence.prompt_payload() for evidence in query.evidence],
            )
            return _action_key(item.action), output.helpful_probability, output.reason

        with ThreadPoolExecutor(max_workers=min(self.verifier_workers, len(enumerated))) as executor:
            futures = {executor.submit(verify, item): item for item in enumerated}
            for future in as_completed(futures):
                key, score, reason = future.result()
                scores[key] = (score, reason)
        scored = [
            (scores[_action_key(item.action)][0], item)
            for item in enumerated
        ]
        updated_values = []
        for value in prior_values:
            result = scores.get(f"click:{value.candidate_id}")
            if result is None:
                updated_values.append(value)
                continue
            updated_values.append(
                value.model_copy(
                    update={
                        "verifier_score": round(result[0], 4),
                        "final_score": round(result[0], 4),
                        "score_source": "k_exaone_verifier",
                        "verifier_reason": result[1],
                    }
                )
            )
        updated_values.sort(key=lambda value: (-value.final_score, value.candidate_id))
        return scored, updated_values


class ReflectionTriggerPolicy:
    """MobileUse-style action/trajectory/global reflection on demand."""

    def choose_level(
        self,
        *,
        outcome_type: str,
        execution_succeeded: bool | None,
        action_confidence: float,
        reflection_on_demand: bool,
        action_name: str,
        recent_history: Sequence[Mapping[str, object]],
    ) -> tuple[str, str]:
        if outcome_type == "destination_reached" or action_name == "stop_for_user":
            return "global", "destination signature reached; verify completion boundary"
        actions = [str(item.get("action_name", "")) for item in recent_history[-5:]]
        screens = [str(item.get("screen_fingerprint", "")) for item in recent_history[-5:]]
        errors = sum(
            str(item.get("progress_label", "")) in {"unchanged", "regressed"}
            or bool(item.get("failure_class"))
            for item in recent_history[-5:]
        )
        repeated_actions = len(actions) >= 2 and actions[-1] == actions[-2]
        repeated_screens = len(screens) >= 2 and screens[-1] == screens[-2]
        if repeated_actions or repeated_screens or errors >= 2:
            return "trajectory", "recent repeated action/screen or accumulated errors"
        if (
            execution_succeeded is False
            or reflection_on_demand
            or outcome_type in {"no_change", "wrong_destination", "external_app", "blocked"}
            or action_confidence < 0.45
        ):
            return "action", "low-confidence or unexpected single-step outcome"
        return "none", "high-confidence observed progress"


def _action_key(action: NavigationAction) -> str:
    if action.name == "click":
        return f"click:{action.candidate_id}"
    if action.name == "scroll":
        return f"scroll:{action.direction}"
    return action.name


def _action_sort_key(action: NavigationAction) -> str:
    return _action_key(action)
