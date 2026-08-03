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
from app.services.navigation_decision_memory import (
    DecisionMemoryQuery,
    is_dangerous_final_candidate,
    is_state_changing_action_label,
)
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
DIRECT_ROLE_GUARD_FLOOR = 0.78
UNRELATED_ROLE_CEILING = 0.50
DIRECT_ROLE_MODEL_FLOOR = 0.50
SEMANTIC_FAST_PATH_ROLE_FLOOR = 0.95
SEMANTIC_FAST_PATH_LABEL_MAX_CHARS = 48
DESTINATION_SCROLL_MATCH_FLOOR = 0.30
DESTINATION_SCROLL_LIMIT = 4
MODEL_RETRY_CLICK_LIMIT = 6
SAFE_INTERMEDIATE_FAST_PATH_ROLES = frozenset(
    {
        "account.hub",
        "account.settings",
        "billing.manage",
        "membership.hub",
        "navigation.menu",
        "privacy.settings",
        "profile.hub",
    }
)


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
        force_visual_reasoning: bool = False,
    ) -> PerceptionOutput:
        should_invoke_vlm = (
            self.vlm_mode == "always"
            or force_visual_reasoning
            or _needs_visual_reasoning(screen)
        )
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
        current_fingerprint = query.screen.semantic_fingerprint
        prior_visits = sum(
            bool(current_fingerprint)
            and str(item.get("screen_fingerprint", "")) == current_fingerprint
            for item in recent_history
        )
        if prior_visits >= 2:
            provider = "python_screen_visit_guard"
            proposal = PlannerProposal(
                NavigationAction(name="stop_for_user"),
                1.0,
                provider,
                False,
            )
            return ResearchDecision(
                plan=plan,
                proposal=proposal,
                candidate_values=tuple(prior_values),
                verifier_provider=provider,
                score_margin=1.0,
                reflection_on_demand=True,
            )
        enumerated = self._enumerate_actions(
            candidates=candidates,
            prior_values=prior_values,
            plan=plan,
            recent_history=recent_history,
        )
        structural_continuation_candidate_id = (
            self._structural_continuation_fast_path_candidate(
                query=query,
                plan=plan,
                candidates=candidates,
                recent_history=recent_history,
            )
        )
        if structural_continuation_candidate_id is not None and not any(
            item.action.name == "click"
            and item.action.candidate_id == structural_continuation_candidate_id
            for item in enumerated
        ):
            structural_continuation_candidate_id = None
        semantic_fast_path_candidate_id = (
            None
            if structural_continuation_candidate_id is not None
            else self.semantic_intermediate_fast_path_candidate(
                query=query,
                plan=plan,
                prior_values=prior_values,
                recent_history=recent_history,
            )
        )
        should_invoke_planner = self._should_invoke_planner(
            query=query,
            plan=plan,
            prior_values=prior_values,
            recent_history=recent_history,
            semantic_fast_path_candidate_id=semantic_fast_path_candidate_id,
            structural_continuation_candidate_id=structural_continuation_candidate_id,
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
                if any(
                    value.verifier_reason.startswith("python_direct_role_guard:")
                    for value in updated_values
                ):
                    provider += "->python_direct_role_guard"
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
                "structural_continuation_fast_path"
                if structural_continuation_candidate_id is not None
                else "semantic_intermediate_role_fast_path"
                if semantic_fast_path_candidate_id is not None
                else "decision_memory_profile_fast_path"
                if query.standards_profile == "exitguide.navigation-experience.v1"
                else "decision_memory_high_confidence"
                if self.planner_model.configured and self.planner_mode == "selective"
                else "decision_memory_fallback"
            )
            fallback_used = False
            deterministic_fast_path_candidate_id = (
                structural_continuation_candidate_id or semantic_fast_path_candidate_id
            )
            if deterministic_fast_path_candidate_id is not None:
                selected_key = f"click:{deterministic_fast_path_candidate_id}"
                scored = [
                    (
                        1.0 if _action_key(item.action) == selected_key else min(score, 0.74),
                        item,
                    )
                    for score, item in scored
                ]
                updated_values = [
                    value.model_copy(
                        update={
                            "final_score": 1.0,
                            "verifier_reason": (
                                "python_structural_continuation_fast_path: "
                                "successful expander revealed a same-label safe child"
                                if structural_continuation_candidate_id is not None
                                else
                                "python_semantic_fast_path: unique safe intermediate role"
                            ),
                        }
                    )
                    if value.candidate_id == deterministic_fast_path_candidate_id
                    else value
                    for value in updated_values
                ]
        fallback_semantically_resolved = False
        if fallback_used:
            resolved_key = self._resolve_structural_direct_candidate(
                query=query,
                plan=model_plan,
                prior_values=prior_values,
                enumerated=enumerated,
            )
            if resolved_key is not None:
                scored = [
                    (
                        1.0 if _action_key(item.action) == resolved_key else min(score, 0.74),
                        item,
                    )
                    for score, item in scored
                ]
                updated_values = [
                    value.model_copy(
                        update={
                            "final_score": 1.0,
                            "verifier_reason": (
                                "python_structural_direct_tiebreak: unique unselected direct-role "
                                "candidate after model output failure"
                            ),
                        }
                    )
                    if f"click:{value.candidate_id}" == resolved_key
                    else value
                    for value in updated_values
                ]
                provider += "->python_structural_direct_tiebreak"
                fallback_semantically_resolved = True
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
            and not fallback_semantically_resolved
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

    def _resolve_structural_direct_candidate(
        self,
        *,
        query: DecisionMemoryQuery | None = None,
        plan: HierarchicalPlan | None = None,
        prior_values: Sequence[CandidateValue],
        enumerated: Sequence[EnumeratedAction],
    ) -> str | None:
        """Resolve only a uniquely best, grounded direct-role structure.

        This is a fail-safe for malformed/inconsistent Solar output, not an
        app route. It uses standard accessibility state plus label/parent
        structure and refuses equal semantic ties.
        """

        value_by_id = {value.candidate_id: value for value in prior_values}

        # A malformed model response must not strand the agent when the
        # current screen itself grounds exactly one obvious intermediate hub.
        # This rescue is intentionally narrower than the regular fast path:
        # it runs only after model failure, accepts only safe intermediate
        # roles requested by the current hierarchy, and refuses ambiguity.
        if query is not None and plan is not None:
            target_roles = set(plan.target_roles) & SAFE_INTERMEDIATE_FAST_PATH_ROLES
            payload_by_id = {
                str(payload.get("candidate_id", "")): payload
                for payload in query.screen.candidate_payloads
            }
            grounded: list[str] = []
            for item in enumerated:
                if item.action.name != "click" or item.candidate is None:
                    continue
                candidate = item.candidate
                value = value_by_id.get(candidate.candidate_id)
                payload = payload_by_id.get(candidate.candidate_id, {})
                role_scores = payload.get("function_role_scores", {})
                semantic_text = " ".join(
                    (
                        candidate.label,
                        candidate.icon_semantics,
                        candidate.nearby_text,
                        candidate.parent_semantics,
                    )
                )
                if (
                    value is None
                    or value.forbidden
                    or value.risk_level != "low"
                    or candidate.risk_level != "low"
                    or not candidate.clickable
                    or not candidate.enabled
                    or candidate.selected
                    or bool(payload.get("dangerous_final", False))
                    or not bool(payload.get("clickable", True))
                    or not bool(payload.get("enabled", True))
                    or bool(payload.get("selected", False))
                    or is_state_changing_action_label(candidate.label)
                    or is_dangerous_final_candidate(semantic_text)
                    or not isinstance(role_scores, Mapping)
                    or not any(
                        float(role_scores.get(role, 0.0))
                        >= SEMANTIC_FAST_PATH_ROLE_FLOOR
                        for role in target_roles
                    )
                ):
                    continue
                grounded.append(f"click:{candidate.candidate_id}")
            if len(grounded) == 1:
                return grounded[0]
            if len(grounded) > 1:
                return None

        ranked: list[tuple[tuple[int, int, float], str]] = []
        for item in enumerated:
            if item.action.name != "click" or item.candidate is None:
                continue
            candidate = item.candidate
            value = value_by_id.get(candidate.candidate_id)
            if (
                value is None
                or value.forbidden
                or value.role_score < DIRECT_ROLE_GUARD_FLOOR
                or value.risk_level != "low"
                or not candidate.clickable
                or not candidate.enabled
                or candidate.selected
            ):
                continue
            label = " ".join(candidate.label.casefold().split())
            parent = " ".join(candidate.parent_semantics.casefold().split())
            parent_consistent = int(bool(label) and label == parent)
            token_count = max(1, len(label.split()))
            semantic_rank = (parent_consistent, -token_count, round(value.role_score, 4))
            ranked.append((semantic_rank, f"click:{candidate.candidate_id}"))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return None
        return ranked[0][1]

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
            retry_enumerated = self._compact_model_retry_actions(enumerated)
            LOGGER.warning(
                "planner_model_output_retry provider=%s failure_class=%s "
                "original_actions=%s retry_actions=%s detail=%s",
                self.planner_model.name,
                type(error).__name__,
                len(enumerated),
                len(retry_enumerated),
                str(error)[:500],
            )
            return self._plan_and_verify_actions(
                query=query,
                plan=plan,
                recent_history=recent_history,
                enumerated=retry_enumerated,
                prior_values=prior_values,
            )

    @staticmethod
    def _compact_model_retry_actions(
        enumerated: Sequence[EnumeratedAction],
    ) -> tuple[EnumeratedAction, ...]:
        """Bound a malformed-output retry while retaining all safe controls."""

        clicks = [
            item for item in enumerated if item.action.name == "click"
        ][:MODEL_RETRY_CLICK_LIMIT]
        controls = [item for item in enumerated if item.action.name != "click"]
        return tuple((*clicks, *controls))

    def _should_invoke_planner(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        prior_values: Sequence[CandidateValue],
        recent_history: Sequence[Mapping[str, object]],
        semantic_fast_path_candidate_id: str | None = None,
        structural_continuation_candidate_id: str | None = None,
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
            if structural_continuation_candidate_id is not None and any(
                value.candidate_id == structural_continuation_candidate_id
                for value in safe
            ):
                return False
            if semantic_fast_path_candidate_id is None:
                semantic_fast_path_candidate_id = self.semantic_intermediate_fast_path_candidate(
                    query=query,
                    plan=plan,
                    prior_values=prior_values,
                    recent_history=recent_history,
                )
            if (
                semantic_fast_path_candidate_id is not None
                and safe[0].candidate_id == semantic_fast_path_candidate_id
            ):
                return False
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

    def semantic_intermediate_fast_path_candidate(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        prior_values: Sequence[CandidateValue],
        recent_history: Sequence[Mapping[str, object]],
    ) -> str | None:
        """Return one obvious, safe intermediate-role candidate or refuse.

        This is the strict B-policy fast path: it does not cover enrollment,
        deletion, cancellation, payment or other terminal roles.  A role must
        come directly from the candidate label/icon (>= 0.95), be unique on
        the screen, remain the top deterministic prior, and have no observed
        anomaly in the active episode.
        """

        if (
            query.standards_profile != "exitguide.navigation-experience.v1"
            or plan.stage not in {"hub_discovery", "destination_entry"}
            or _history_requires_planner(recent_history)
        ):
            return None
        target_roles = tuple(
            role
            for role in plan.target_roles
            if role in SAFE_INTERMEDIATE_FAST_PATH_ROLES
        )
        if not target_roles:
            return None
        value_by_id = {value.candidate_id: value for value in prior_values}
        eligible_by_role: dict[str, list[str]] = {role: [] for role in target_roles}
        for candidate in query.screen.candidate_payloads:
            candidate_id = str(candidate.get("candidate_id", ""))
            label = str(candidate.get("label", "")).strip()
            value = value_by_id.get(candidate_id)
            role_scores = candidate.get("function_role_scores", {})
            if (
                value is None
                or value.forbidden
                or value.conflicting_cases > 0
                or value.risk_level != "low"
                or str(candidate.get("risk_level", "low")) != "low"
                or bool(candidate.get("dangerous_final", False))
                or not bool(candidate.get("clickable", True))
                or not bool(candidate.get("enabled", True))
                or bool(candidate.get("selected", False))
                or not isinstance(role_scores, Mapping)
                # Accessibility roots often concatenate an entire screen into
                # one clickable label.  Such composite text may contain a
                # perfect alias but is not an obvious single affordance.
                or (label and len(label) > SEMANTIC_FAST_PATH_LABEL_MAX_CHARS)
            ):
                continue
            for target_role in target_roles:
                if (
                    float(role_scores.get(target_role, 0.0))
                    >= SEMANTIC_FAST_PATH_ROLE_FLOOR
                ):
                    eligible_by_role[target_role].append(candidate_id)
        safe_values = sorted(
            (
                value
                for value in prior_values
                if not value.forbidden and value.score_source != "safety_blocked"
            ),
            key=lambda value: (-value.final_score, value.candidate_id),
        )
        if not safe_values:
            return None
        # K² emits target roles in subgoal priority order. Resolve ambiguity
        # within the first role that is actually visible; do not let a
        # lower-priority profile/menu affordance cancel an exact account or
        # billing match. Multiple candidates for that same role remain
        # ambiguous and still require the planner.
        for target_role in target_roles:
            role_candidates = eligible_by_role[target_role]
            if not role_candidates:
                continue
            if len(role_candidates) != 1:
                return None
            if safe_values[0].candidate_id != role_candidates[0]:
                return None
            return role_candidates[0]
        return None

    def _semantic_stage_fast_path_candidate(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        prior_values: Sequence[CandidateValue],
        recent_history: Sequence[Mapping[str, object]],
    ) -> str | None:
        """Backward-compatible private alias retained for focused policy tests."""

        return self.semantic_intermediate_fast_path_candidate(
            query=query,
            plan=plan,
            prior_values=prior_values,
            recent_history=recent_history,
        )

    def semantic_destination_scroll_fast_path(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        screen: ScreenObservation,
        recent_history: Sequence[Mapping[str, object]],
    ) -> bool:
        """Continue down a partially matched static destination page.

        This is deliberately narrower than a generic scroll heuristic.  It is
        allowed only after the destination signature has begun to match, on a
        screen that Accessibility confirms is scrollable, and while no direct
        or dangerous target is already visible.  A short episode-local bound
        prevents the rule from turning a feed into an infinite-scroll loop.
        """

        if (
            query.standards_profile != "exitguide.navigation-experience.v1"
            or plan.stage not in {"destination_entry", "destination_verification"}
            or query.destination_match < DESTINATION_SCROLL_MATCH_FLOOR
            or _history_requires_planner(recent_history)
            or not any(node.visible and node.scrollable for node in screen.nodes)
        ):
            return False

        target_roles = set(plan.target_roles)
        for candidate in query.screen.candidate_payloads:
            if bool(candidate.get("dangerous_final", False)):
                return False
            role_scores = candidate.get("function_role_scores", {})
            label = str(candidate.get("label", "")).strip()
            if (
                isinstance(role_scores, Mapping)
                and label
                and len(label) <= SEMANTIC_FAST_PATH_LABEL_MAX_CHARS
                and bool(candidate.get("clickable", True))
                and bool(candidate.get("enabled", True))
                and not bool(candidate.get("selected", False))
                and str(candidate.get("risk_level", "low")) == "low"
                and any(
                    float(role_scores.get(role, 0.0)) >= SEMANTIC_FAST_PATH_ROLE_FLOOR
                    for role in target_roles
                )
            ):
                return False

        trailing_scrolls = 0
        for item in reversed(recent_history):
            if str(item.get("action_name", "")) != "scroll":
                break
            if str(item.get("scroll_direction", "")) != "down":
                break
            if str(item.get("connectivity_status", "")) != "observed":
                return False
            trailing_scrolls += 1
        return trailing_scrolls < DESTINATION_SCROLL_LIMIT

    def _structural_continuation_fast_path_candidate(
        self,
        *,
        query: DecisionMemoryQuery,
        plan: HierarchicalPlan,
        candidates: Sequence[NavigationCandidate],
        recent_history: Sequence[Mapping[str, object]],
    ) -> str | None:
        """Return a newly revealed safe child of the last successful expander."""

        if (
            query.standards_profile != "exitguide.navigation-experience.v1"
            or plan.stage not in {"hub_discovery", "destination_entry"}
            or not recent_history
        ):
            return None
        latest = recent_history[-1]
        if (
            str(latest.get("connectivity_status", "")) != "observed"
            or str(latest.get("action_name", "")) != "click"
            or str(latest.get("progress_label", "")) != "advanced"
        ):
            return None
        previous_id = str(latest.get("candidate_id", "")).strip()
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        previous = candidate_by_id.get(previous_id)
        if previous is None:
            return None

        def semantic_key(candidate: NavigationCandidate) -> str:
            direct = candidate.label.strip() or candidate.icon_semantics.strip()
            return " ".join(direct.casefold().split())

        previous_key = semantic_key(previous)
        if not previous_key:
            return None
        target_roles = set(plan.target_roles) & SAFE_INTERMEDIATE_FAST_PATH_ROLES
        if not target_roles:
            return None
        payload_by_id = {
            str(payload.get("candidate_id", "")): payload
            for payload in query.screen.candidate_payloads
        }
        children: list[str] = []
        for candidate in candidates:
            if candidate.candidate_id == previous_id or semantic_key(candidate) != previous_key:
                continue
            label_key = " ".join(candidate.label.casefold().split())
            parent_key = " ".join(candidate.parent_semantics.casefold().split())
            payload = payload_by_id.get(candidate.candidate_id, {})
            role_scores = payload.get("function_role_scores", {})
            semantic_text = " ".join(
                (
                    candidate.label,
                    candidate.icon_semantics,
                    candidate.nearby_text,
                    candidate.parent_semantics,
                )
            )
            if (
                not label_key
                or label_key != parent_key
                or not candidate.clickable
                or not candidate.enabled
                or candidate.selected
                or candidate.risk_level != "low"
                or is_state_changing_action_label(candidate.label)
                or is_dangerous_final_candidate(semantic_text)
                or not isinstance(role_scores, Mapping)
                or not any(
                    float(role_scores.get(role, 0.0)) >= SEMANTIC_FAST_PATH_ROLE_FLOOR
                    for role in target_roles
                )
            ):
                continue
            children.append(candidate.candidate_id)
        return children[0] if len(children) == 1 else None

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
        scores = self._apply_direct_role_guard(
            scores=scores,
            prior_values=prior_values,
            enumerated=enumerated,
        )
        scores = self._apply_immediate_repeat_guard(
            scores=scores,
            enumerated=enumerated,
            recent_history=recent_history,
        )
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
            source=(
                "solar_pro4"
                if self.planner_model.name == "solar_pro4"
                else "solar_pro3"
            ),
        )
        return refined_plan, scored, updated_values

    def _apply_direct_role_guard(
        self,
        *,
        scores: Mapping[str, tuple[float, str]],
        prior_values: Sequence[CandidateValue],
        enumerated: Sequence[EnumeratedAction],
    ) -> dict[str, tuple[float, str]]:
        """Prevent an unrelated click from outranking an observed direct role.

        Solar still evaluates the complete bounded action set.  This guard is
        only activated when Solar itself gives at least one safe, direct-role
        click a useful score but selects a semantically weaker click instead.
        It never creates a candidate ID and it leaves genuine same-role
        ambiguity to Solar's scores and semantic context.
        """

        adjusted = dict(scores)
        prior_by_key = {
            f"click:{value.candidate_id}": value
            for value in prior_values
            if not value.forbidden and value.score_source != "safety_blocked"
        }
        if not adjusted or not prior_by_key:
            return adjusted
        ranked = sorted(adjusted.items(), key=lambda item: (-item[1][0], item[0]))
        best_key = ranked[0][0]
        best_prior = prior_by_key.get(best_key)
        if best_prior is None or best_prior.role_score >= UNRELATED_ROLE_CEILING:
            return adjusted
        candidate_by_key = {
            f"click:{item.action.candidate_id}": item.candidate
            for item in enumerated
            if item.action.name == "click" and item.candidate is not None
        }
        direct_keys = [
            key
            for key, value in prior_by_key.items()
            if value.role_score >= DIRECT_ROLE_GUARD_FLOOR
            and adjusted.get(key, (0.0, ""))[0] >= DIRECT_ROLE_MODEL_FLOOR
            and candidate_by_key.get(key) is not None
            and candidate_by_key[key].clickable
            and candidate_by_key[key].enabled
            and not candidate_by_key[key].selected
        ]
        if not direct_keys:
            return adjusted

        def direct_rank(key: str) -> tuple[float, float, int, int, int, str]:
            value = prior_by_key[key]
            candidate = candidate_by_key.get(key)
            label = "" if candidate is None else candidate.label.strip()
            parent = "" if candidate is None else candidate.parent_semantics.strip()
            parent_consistent = int(bool(label) and label.casefold() == parent.casefold())
            return (
                adjusted[key][0],
                value.role_score,
                int(candidate is not None and not candidate.selected),
                parent_consistent,
                -len(label),
                key,
            )

        selected_key = max(direct_keys, key=direct_rank)
        best_score = adjusted[best_key][0]
        selected_score, selected_reason = adjusted[selected_key]
        adjusted[selected_key] = (
            min(1.0, max(selected_score, best_score + 0.001)),
            "python_direct_role_guard: direct candidate role outranks unrelated click; "
            + selected_reason,
        )
        return adjusted

    def _apply_immediate_repeat_guard(
        self,
        *,
        scores: Mapping[str, tuple[float, str]],
        enumerated: Sequence[EnumeratedAction],
        recent_history: Sequence[Mapping[str, object]],
    ) -> dict[str, tuple[float, str]]:
        """Prefer a newly revealed child over re-clicking its successful expander.

        Android accessibility trees often expose an expanded menu category and
        its child page with the same label but different candidate IDs.  When
        the immediately previous click advanced the UI, selecting the same
        persistent candidate again usually collapses the category or produces
        no change.  This guard only acts when an enabled low-risk sibling with
        the same direct label/icon is present, so unrelated alternatives remain
        under Solar's control.
        """

        if not recent_history:
            return dict(scores)
        latest = recent_history[-1]
        if (
            str(latest.get("connectivity_status", "")) != "observed"
            or str(latest.get("action_name", "")) != "click"
            or str(latest.get("progress_label", "")) != "advanced"
        ):
            return dict(scores)
        repeated_id = str(latest.get("candidate_id", "")).strip()
        if not repeated_id:
            return dict(scores)

        click_items = {
            str(item.action.candidate_id): item
            for item in enumerated
            if item.action.name == "click" and item.candidate is not None
        }
        repeated = click_items.get(repeated_id)
        if repeated is None or repeated.candidate is None:
            return dict(scores)

        def semantic_key(candidate: NavigationCandidate) -> str:
            direct = candidate.label.strip() or candidate.icon_semantics.strip()
            return " ".join(direct.casefold().split())

        repeated_key = semantic_key(repeated.candidate)
        if not repeated_key:
            return dict(scores)
        alternatives = [
            item
            for candidate_id, item in click_items.items()
            if candidate_id != repeated_id
            and item.candidate is not None
            and semantic_key(item.candidate) == repeated_key
            and item.candidate.clickable
            and item.candidate.enabled
            and not item.candidate.selected
            and item.candidate.risk_level == "low"
        ]
        if not alternatives:
            return dict(scores)

        def child_rank(item: EnumeratedAction) -> tuple[int, float, str]:
            assert item.candidate is not None
            label = " ".join(item.candidate.label.casefold().split())
            parent = " ".join(item.candidate.parent_semantics.casefold().split())
            return (
                int(bool(label) and label == parent),
                item.memory_prior,
                str(item.action.candidate_id),
            )

        child = max(alternatives, key=child_rank)
        child_action_key = _action_key(child.action)
        repeat_action_key = f"click:{repeated_id}"
        adjusted = dict(scores)
        if repeat_action_key not in adjusted or child_action_key not in adjusted:
            return adjusted
        child_score = adjusted[child_action_key][0]
        repeated_score, repeated_reason = adjusted[repeat_action_key]
        adjusted[repeat_action_key] = (
            min(repeated_score, max(0.0, child_score - 0.001)),
            "python_immediate_repeat_guard: successful expander persisted while a "
            "same-label child appeared; " + repeated_reason,
        )
        return adjusted


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
        screens = [str(item.get("screen_fingerprint", "")) for item in recent_history[-5:]]
        errors = sum(
            str(item.get("progress_label", "")) in {"unchanged", "regressed"}
            or bool(item.get("failure_class"))
            for item in recent_history[-5:]
        )
        action_signatures = [
            (
                str(item.get("screen_fingerprint", "")),
                str(item.get("action_name", "")),
                str(item.get("candidate_id", "")),
                str(item.get("scroll_direction", "")),
            )
            for item in recent_history[-5:]
        ]
        repeated_action_on_screen = (
            len(action_signatures) >= 2
            and bool(action_signatures[-1][0])
            and action_signatures[-1] == action_signatures[-2]
        )
        repeated_screens = (
            len(screens) >= 2 and bool(screens[-1]) and screens[-1] == screens[-2]
        )
        nonempty_screens = [screen for screen in screens if screen]
        revisited_screen = len(nonempty_screens) != len(set(nonempty_screens))
        if repeated_action_on_screen or repeated_screens or revisited_screen or errors >= 2:
            return "trajectory", "revisited screen/action loop or accumulated observed errors"
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
        # `python_visual_reobserve_gate` deliberately emits one
        # wait_and_observe before the Executor attaches a screenshot.  A
        # successful non-mutating wait is not a navigation failure and must
        # not suppress a newly visible, unique semantic fast path on the next
        # screen.  A failed wait still carries failure_class and repeated
        # waits on the same fingerprint are caught by the loop check below.
        if (
            str(item.get("action_name", "")) == "wait_and_observe"
            and not str(item.get("failure_class", "")).strip()
            and str(item.get("outcome_type", "")) == "no_change"
            and str(item.get("progress_label", "")) == "unchanged"
        ):
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
