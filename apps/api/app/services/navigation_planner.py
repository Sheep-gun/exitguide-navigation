from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.navigation_contracts import (
    CandidateValue,
    HierarchicalPlan,
    NavigationAction,
    NavigationCandidate,
)
from app.services.navigation_decision_memory import (
    GOAL_ROLE_PRIORS,
    DecisionMemoryQuery,
    _candidate_ontology_score,
    is_contextual_membership_cancellation_action,
    is_dangerous_final_candidate,
    is_state_changing_action_label,
)


@dataclass(frozen=True)
class PlannerProposal:
    action: NavigationAction
    confidence: float
    provider: str
    fallback_used: bool


class HierarchicalPlanBuilder:
    """K²-inspired goal -> stage -> immediately verifiable sub-goal fallback."""

    def build(
        self,
        query: DecisionMemoryQuery,
        *,
        forbidden_candidate_ids: set[str],
        destination_threshold: float,
    ) -> HierarchicalPlan:
        if query.goal is None:
            return HierarchicalPlan(
                goal_id=None,
                stage="goal_disambiguation",
                target_roles=[],
                immediate_subgoal="지원하는 사용자 목적을 명확히 확인한다.",
                expected_outcome="목적이 recognized 상태로 정규화된다.",
                completion_rule="지원 목적을 식별할 수 있을 때까지 사용자 확인을 기다린다.",
                source="python_safety_gate",
            )

        target_roles = [
            role
            for role, _ in sorted(
                GOAL_ROLE_PRIORS.get(query.goal.goal_id, {}).items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        if query.destination_match >= destination_threshold:
            stage = "terminal_boundary"
            subgoal = "목적지 화면의 의미적 조건을 확인하고 사용자에게 최종 행동을 넘긴다."
            expected = "위험한 최종 행동을 자동 실행하지 않고 멈춘다."
            completion = "목적지 의미 서명이 충족되었으므로 최종 행동은 사용자에게 넘긴다."
        elif forbidden_candidate_ids:
            stage = "selective_recovery"
            subgoal = "관찰된 실패 후보를 제외하고 현재 화면에서 다른 안전 경로를 찾는다."
            expected = "동일 실패 후보를 반복하지 않고 화면 진행 가능성이 회복된다."
            completion = "같은 실패 후보를 제외하고 다른 안전 후보 또는 복구 행동을 선택한다."
        else:
            strongest_role = max(
                (
                    GOAL_ROLE_PRIORS.get(query.goal.goal_id, {}).get(str(role), 0.0)
                    for candidate in query.screen.candidate_payloads
                    for role in candidate.get("inferred_function_roles", [])
                ),
                default=0.0,
            )
            if strongest_role >= 0.72:
                stage = "destination_entry"
                subgoal = "목적 기능으로 직접 이어질 가능성이 높은 메뉴에 진입한다."
                expected = "다음 화면에서 목적지 서명 일치도가 증가한다."
                completion = "목적 기능으로 직접 이어지는 안전 후보를 선택한다."
            else:
                stage = "hub_discovery"
                subgoal = "계정·프로필·멤버십 허브 역할의 화면으로 이동한다."
                expected = "목적 기능과 관련된 후보 역할이 더 구체적으로 나타난다."
                completion = "계정·프로필·멤버십 허브에 가까워지는 안전 후보를 찾는다."

        return HierarchicalPlan(
            goal_id=query.goal.goal_id,
            stage=stage,
            target_roles=target_roles[:6],
            immediate_subgoal=subgoal,
            expected_outcome=expected,
            completion_rule=completion,
            source="decision_memory_fallback",
        )


class CandidateValueScorer:
    """V-Droid-inspired value prior, constrained to observed candidate IDs."""

    def score(
        self,
        query: DecisionMemoryQuery,
        candidates: Sequence[NavigationCandidate],
        *,
        forbidden_candidate_ids: set[str],
    ) -> list[CandidateValue]:
        goal_priors = GOAL_ROLE_PRIORS.get(query.goal.goal_id, {}) if query.goal else {}
        memory_candidates = {
            str(candidate["candidate_id"]): candidate for candidate in query.screen.candidate_payloads
        }
        values: list[CandidateValue] = []
        for candidate in candidates:
            memory_candidate = memory_candidates.get(candidate.candidate_id, {})
            role_score = _candidate_ontology_score(memory_candidate, goal_priors)
            memory_score = float(query.candidate_scores.get(candidate.candidate_id, 0.0))
            memory_confidence = query.candidate_confidence.get(candidate.candidate_id)
            value = max(memory_score, role_score * 0.78 + memory_score * 0.22)
            if memory_confidence and memory_confidence.conflicting_cases > 0:
                # The retriever has already combined positive and negative
                # transition evidence into memory_score.  Do not let a broad
                # ontology alias re-inflate a candidate that has an observed
                # matching failure; ambiguous cases must go to the planner.
                evidence_total = (
                    memory_confidence.supporting_cases
                    + memory_confidence.conflicting_cases
                )
                conflict_adjusted_support = (
                    memory_confidence.supporting_cases / evidence_total
                    if evidence_total
                    else 0.0
                )
                value = min(value, memory_score) * conflict_adjusted_support
            forbidden = candidate.candidate_id in forbidden_candidate_ids
            semantic_text = " ".join(
                (
                    candidate.label,
                    candidate.icon_semantics,
                    candidate.nearby_text,
                    candidate.parent_semantics,
                )
            )
            dangerous = (
                bool(memory_candidate.get("dangerous_final"))
                or is_state_changing_action_label(candidate.label)
                or is_dangerous_final_candidate(semantic_text)
            )
            blocked = (
                candidate.risk_level in {"medium", "high", "blocked"}
                or dangerous
                or forbidden
                or not candidate.clickable
                or not candidate.enabled
            )
            if blocked:
                value = 0.0
            elif candidate.selected:
                # Clicking an already-selected tab/control rarely advances
                # navigation. Keep it visible for comparison but strongly
                # demote it instead of deleting it from the full inventory.
                value *= 0.25
            confidence_reasons = (
                list(memory_confidence.reasons) if memory_confidence else []
            )
            if candidate.selected:
                confidence_reasons.append("already_selected_state")
            values.append(
                CandidateValue(
                    candidate_id=candidate.candidate_id,
                    value=round(max(0.0, min(1.0, value)), 4),
                    memory_score=round(max(0.0, min(1.0, memory_score)), 4),
                    role_score=round(max(0.0, min(1.0, role_score)), 4),
                    final_score=round(max(0.0, min(1.0, value)), 4),
                    score_source="safety_blocked" if blocked else "decision_memory_fallback",
                    memory_support_tier=(
                        memory_confidence.support_tier if memory_confidence else "unknown"
                    ),
                    supporting_cases=(
                        memory_confidence.supporting_cases if memory_confidence else 0
                    ),
                    supporting_apps=(
                        memory_confidence.supporting_apps if memory_confidence else 0
                    ),
                    conflicting_cases=(
                        memory_confidence.conflicting_cases if memory_confidence else 0
                    ),
                    provenance_quality=(
                        memory_confidence.provenance_quality if memory_confidence else 0.0
                    ),
                    fast_path_eligible=(
                        bool(memory_confidence.fast_path_eligible) if memory_confidence else False
                    ) and not blocked and not candidate.selected,
                    confidence_reasons=confidence_reasons,
                    forbidden=forbidden,
                    risk_level=candidate.risk_level,
                )
            )
        values.sort(key=lambda candidate_value: (-candidate_value.value, candidate_value.candidate_id))
        return values


class ActionSafetyGate:
    """Reject ungrounded IDs and stop before every dangerous final action."""

    def validate(
        self,
        action: NavigationAction,
        *,
        candidates: Sequence[NavigationCandidate],
        forbidden_candidate_ids: set[str],
    ) -> tuple[NavigationAction, str, str]:
        if action.name != "click":
            return action, "allowed", "non-click navigation action"

        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        candidate = candidate_by_id.get(action.candidate_id or "")
        if candidate is None:
            return (
                NavigationAction(name="wait_and_observe"),
                "replaced_with_safe_action",
                "planner selected an ID not present on the observed screen",
            )
        if not candidate.clickable or not candidate.enabled:
            return (
                NavigationAction(name="wait_and_observe"),
                "replaced_with_safe_action",
                "candidate is not currently clickable and enabled",
            )
        if candidate.candidate_id in forbidden_candidate_ids:
            return (
                NavigationAction(name="wait_and_observe"),
                "replaced_with_safe_action",
                "candidate is forbidden by observed failure memory",
            )

        screen_context = " ".join(
            (
                candidate.label,
                candidate.icon_semantics,
                candidate.nearby_text,
                candidate.parent_semantics,
            )
        )
        if candidate.risk_level in {"medium", "high", "blocked"}:
            return (
                NavigationAction(name="stop_for_user"),
                "replaced_with_safe_action",
                f"candidate risk level is {candidate.risk_level}",
            )
        # Nearby or parent text may contain an adjacent destructive control (for example,
        # "로그아웃" beside a safe "회원탈퇴 페이지로 이동하기" link). Only the candidate's
        # own semantics can trigger the general final-action phrase gate. The one deliberately
        # contextual exception is a generic cancellation CTA on a membership/billing screen.
        own_action_semantics = " ".join((candidate.label, candidate.icon_semantics))
        if (
            is_state_changing_action_label(candidate.label)
            or is_dangerous_final_candidate(own_action_semantics)
            or is_contextual_membership_cancellation_action(
                candidate.label,
                screen_context,
            )
        ):
            return (
                NavigationAction(name="stop_for_user"),
                "replaced_with_safe_action",
                "candidate is a dangerous final action",
            )
        return action, "allowed", "candidate exists on screen and passed the risk gate"
