from __future__ import annotations

import logging
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
    NavigationPlannerResearchClient,
    PerceptionOutput,
)
from app.services.navigation_planner import (
    ActionSafetyGate,
    CandidateValueScorer,
    HierarchicalPlanBuilder,
    PlannerProposal,
)


LOGGER = logging.getLogger(__name__)


STRICT_FAST_PATH_SCORE_FLOOR = 0.90
STRICT_FAST_PATH_MARGIN_FLOOR = 0.25


@dataclass(frozen=True)
class ResearchDecision:
    plan: HierarchicalPlan
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
        planner_model: NavigationPlannerResearchClient,
        exaone_vlm: Exaone45VisionClient,
        allow_model_fallback: bool = True,
        max_verified_clicks: int = 12,
        reflection_confidence_threshold: float = 0.45,
        reflection_margin_threshold: float = 0.08,
        planner_mode: str = "selective",
        planner_score_threshold: float = STRICT_FAST_PATH_SCORE_FLOOR,
        planner_margin_threshold: float = STRICT_FAST_PATH_MARGIN_FLOOR,
        vlm_mode: str = "selective",
    ) -> None:
        self.planner_model = planner_model
        self.exaone_vlm = exaone_vlm
        self.allow_model_fallback = allow_model_fallback
        self.max_verified_clicks = max(1, max_verified_clicks)
        self.reflection_confidence_threshold = reflection_confidence_threshold
        self.reflection_margin_threshold = reflection_margin_threshold
        self.planner_mode = _validated_mode(planner_mode, "planner_mode")
        # Configuration may make the gate stricter, but never weaker than the
        # agreed LLM-first policy. Fast path is reserved for an obvious,
        # effectively identical candidate; every ordinary ambiguity goes to
        # the Solar-backed K²/V-Droid evaluation.
        self.planner_score_threshold = max(
            STRICT_FAST_PATH_SCORE_FLOOR, planner_score_threshold
        )
        self.planner_margin_threshold = max(
            STRICT_FAST_PATH_MARGIN_FLOOR, planner_margin_threshold
        )
        self.vlm_mode = _validated_mode(vlm_mode, "vlm_mode")
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
        should_invoke_vlm = self.vlm_mode == "always" or _needs_visual_reasoning(screen)
        if (
            screenshot_data_url
            and self.exaone_vlm.configured
            and self.vlm_mode != "disabled"
            and should_invoke_vlm
        ):
            try:
                return self.exaone_vlm.perceive(
                    goal_text=goal_text,
                    screen=screen,
                    screenshot_data_url=screenshot_data_url,
                )
            except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                LOGGER.warning(
                    "vlm_perception_fallback failure_class=%s detail=%s",
                    type(error).__name__,
                    str(error)[:500],
                )
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
        # The deterministic hierarchy is built first so goal ambiguity and the
        # terminal boundary are enforced without a model call. For navigable
        # screens, Solar Pro 3 refines this plan together with all candidate
        # values in one bounded Hermes round trip inside decide_action().
        return fallback, fallback.source, False

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
        should_invoke_planner = self._should_invoke_planner(
            query=query,
            plan=plan,
            prior_values=prior_values,
            recent_history=recent_history,
        )
        if self.planner_model.configured and should_invoke_planner:
            try:
                model_plan, scored, updated_values = self._plan_and_verify_actions_with_retry(
                    query=query,
                    plan=plan,
                    recent_history=recent_history,
                    enumerated=enumerated,
                    prior_values=prior_values,
                )
                provider = f"{self.planner_model.name}_step_evaluator"
                fallback_used = False
            except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                LOGGER.warning(
                    "planner_model_fallback provider=%s failure_class=%s detail=%s",
                    self.planner_model.name,
                    type(error).__name__,
                    str(error)[:500],
                )
                if not self.allow_model_fallback:
                    raise
                model_plan = plan
                scored = [(item.memory_prior, item) for item in enumerated]
                updated_values = prior_values
                provider = (
                    f"{self.planner_model.name}_step_evaluator"
                    "->decision_memory_fallback"
                )
                fallback_used = True
        else:
            model_plan = plan
            scored = [(item.memory_prior, item) for item in enumerated]
            updated_values = prior_values
            provider = (
                "decision_memory_profile_fast_path"
                if query.standards_profile == "exitguide.navigation-experience.v1"
                else "decision_memory_high_confidence"
                if self.planner_model.configured and self.planner_mode == "selective"
                else "decision_memory_fallback"
            )
            fallback_used = False
        scored.sort(key=lambda item: (-item[0], _action_sort_key(item[1].action)))
        if not scored:
            proposal = PlannerProposal(
                NavigationAction(name="wait_and_observe"),
                0.0,
                provider,
                fallback_used,
            )
            return ResearchDecision(model_plan, proposal, tuple(updated_values), provider, 0.0, True)
        best_score, best = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = max(0.0, best_score - second_score)
        if (
            fallback_used
            and (
                best_score < self.planner_score_threshold
                or margin < self.planner_margin_threshold
            )
        ):
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                1.0,
                provider + "->fail_closed",
                True,
            )
            return ResearchDecision(
                plan=model_plan,
                proposal=proposal,
                candidate_values=tuple(updated_values),
                verifier_provider=provider + "->fail_closed",
                score_margin=round(margin, 4),
                reflection_on_demand=True,
            )
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
            plan=model_plan,
            proposal=proposal,
            candidate_values=tuple(updated_values),
            verifier_provider=provider,
            score_margin=round(margin, 4),
            reflection_on_demand=reflect,
        )

    def _plan_and_verify_actions_with_retry(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        recent_history: Sequence[Mapping[str, object]],
        enumerated: Sequence[EnumeratedAction],
        prior_values: Sequence[CandidateValue],
    ) -> tuple[
        HierarchicalPlan,
        list[tuple[float, EnumeratedAction]],
        list[CandidateValue],
    ]:
        try:
            return self._plan_and_verify_actions(
                query=query,
                plan=plan,
                recent_history=recent_history,
                enumerated=enumerated,
                prior_values=prior_values,
            )
        except (KeyError, TypeError, ValueError) as error:
            LOGGER.warning(
                "planner_model_output_retry provider=%s failure_class=%s detail=%s",
                self.planner_model.name,
                type(error).__name__,
                str(error)[:500],
            )
            return self._plan_and_verify_actions(
                query=query,
                plan=plan,
                recent_history=recent_history,
                enumerated=enumerated,
                prior_values=prior_values,
            )

    def _should_invoke_planner(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        prior_values: Sequence[CandidateValue],
        recent_history: Sequence[Mapping[str, object]],
    ) -> bool:
        if self.planner_mode == "disabled":
            return False
        if self.planner_mode == "always":
            return True
        if plan.stage == "selective_recovery" or _history_requires_planner(recent_history):
            return True
        safe = [
            value
            for value in prior_values
            if not value.forbidden and value.score_source != "safety_blocked"
        ]
        if not safe:
            return True
        safe.sort(key=lambda value: (-value.final_score, value.candidate_id))
        best = safe[0].final_score
        second = safe[1].final_score if len(safe) > 1 else 0.0
        if query.standards_profile == "exitguide.navigation-experience.v1":
            fast_path_candidate_id = query.fast_path_candidate_id()
            eligible_count = sum(value.fast_path_eligible for value in safe)
            return not (
                fast_path_candidate_id is not None
                and safe[0].candidate_id == fast_path_candidate_id
                and safe[0].fast_path_eligible
                and eligible_count == 1
                and best >= self.planner_score_threshold
                and best - second >= self.planner_margin_threshold
            )
        return not (
            best >= self.planner_score_threshold
            and best - second >= self.planner_margin_threshold
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

    def _plan_and_verify_actions(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        recent_history: Sequence[Mapping[str, object]],
        enumerated: Sequence[EnumeratedAction],
        prior_values: Sequence[CandidateValue],
    ) -> tuple[
        HierarchicalPlan,
        list[tuple[float, EnumeratedAction]],
        list[CandidateValue],
    ]:
        batch_actions = [
            {
                "action_key": _action_key(item.action),
                "action": item.prompt_payload(),
                "memory_prior": item.memory_prior,
            }
            for item in enumerated
        ]
        model_plan, outputs = self.planner_model.plan_and_verify_actions(
            goal=query.goal.prompt_payload() if query.goal else {},
            screen=query.screen.prompt_payload(),
            destination_signatures=query.destination_signatures,
            decision_evidence=[evidence.prompt_payload() for evidence in query.evidence],
            recent_history=recent_history,
            fallback_plan=plan.model_dump(mode="json"),
            actions=batch_actions,
        )
        scores = {
            key: (output.helpful_probability, output.reason)
            for key, output in outputs.items()
        }
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
                        "score_source": "planner_model_verifier",
                        "verifier_reason": result[1],
                    }
                )
            )
        updated_values.sort(key=lambda value: (-value.final_score, value.candidate_id))
        refined_plan = HierarchicalPlan(
            goal_id=None if query.goal is None else query.goal.goal_id,
            stage=model_plan.stage,
            target_roles=list(model_plan.target_roles) or plan.target_roles,
            immediate_subgoal=model_plan.immediate_subgoal or plan.immediate_subgoal,
            expected_outcome=model_plan.expected_outcome or plan.expected_outcome,
            completion_rule=plan.completion_rule,
            source="solar_pro3",
        )
        return refined_plan, scored, updated_values


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


def _validated_mode(value: str, name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"always", "selective", "disabled"}:
        raise ValueError(f"{name} must be always, selective, or disabled")
    return normalized


def _needs_visual_reasoning(screen: ScreenObservation) -> bool:
    activity = screen.activity_name.lower()
    if not screen.candidates or "webview" in activity or "canvas" in activity:
        return True
    for candidate in screen.candidates:
        if not candidate.label.strip():
            return True
        if candidate.role in {"icon_button", "unknown"} and not candidate.icon_semantics.strip():
            return True
    return False


def _history_requires_planner(
    recent_history: Sequence[Mapping[str, object]],
) -> bool:
    """Escalate only observed navigation anomalies or a detected loop.

    Normal `advanced` history is positive evidence and must not disable the DB
    fast path. Transport/device errors are kept separate from navigation
    failures; invoking a planner cannot repair a disconnected observation path.
    """

    observed_failure_outcomes = {
        "no_change",
        "wrong_destination",
        "external_app",
        "login_required",
        "popup",
        "infinite_feed",
        "network_error",
        "blocked",
    }
    for item in recent_history[-5:]:
        if str(item.get("connectivity_status", "")) != "observed":
            continue
        if str(item.get("progress_label", "")) in {"unchanged", "regressed"}:
            return True
        if str(item.get("outcome_type", "")) in observed_failure_outcomes:
            return True
        if str(item.get("failure_class", "")).strip():
            return True

    if len(recent_history) < 2:
        return False
    latest = recent_history[-1]
    if str(latest.get("connectivity_status", "")) != "observed":
        return False
    latest_screen = str(latest.get("screen_fingerprint", "")).strip()
    if not latest_screen:
        return False

    # A -> B -> A is a semantic screen loop even when individual execution
    # calls succeeded. Repeating the same action on the same screen is the
    # shorter A -> A form of the same failure.
    if any(
        str(item.get("connectivity_status", "")) == "observed"
        and str(item.get("screen_fingerprint", "")).strip() == latest_screen
        for item in recent_history[-5:-1]
    ):
        return True
    return False
