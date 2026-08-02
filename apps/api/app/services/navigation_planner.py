from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from app.navigation_contracts import (
    CandidateValue,
    HierarchicalPlan,
    NavigationAction,
    NavigationCandidate,
)
from app.services.navigation_decision_memory import (
    GOAL_ROLE_PRIORS,
    DecisionMemoryQuery,
    is_dangerous_final_candidate,
)


HERMES_TOOL_PATTERN = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


@dataclass(frozen=True)
class PlannerProposal:
    action: NavigationAction
    confidence: float
    provider: str
    fallback_used: bool


class HierarchicalPlanBuilder:
    """Small K²-inspired hierarchy: goal -> stage -> next semantic roles."""

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
    """V-Droid-inspired per-candidate value, constrained to observed IDs."""

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
            inferred_roles = [str(role) for role in memory_candidate.get("inferred_function_roles", [])]
            role_score = max((goal_priors.get(role, 0.0) for role in inferred_roles), default=0.0)
            memory_score = float(query.candidate_scores.get(candidate.candidate_id, 0.0))
            value = max(memory_score, role_score * 0.78 + memory_score * 0.22)
            forbidden = candidate.candidate_id in forbidden_candidate_ids
            semantic_text = " ".join(
                (
                    candidate.label,
                    candidate.icon_semantics,
                    candidate.nearby_text,
                    candidate.parent_semantics,
                )
            )
            dangerous = bool(memory_candidate.get("dangerous_final")) or is_dangerous_final_candidate(
                semantic_text
            )
            if candidate.risk_level in {"medium", "high", "blocked"} or dangerous or forbidden:
                value = 0.0
            score_source = (
                "safety_blocked"
                if candidate.risk_level in {"medium", "high", "blocked"} or dangerous or forbidden
                else "decision_memory_fallback"
            )
            values.append(
                CandidateValue(
                    candidate_id=candidate.candidate_id,
                    value=round(max(0.0, min(1.0, value)), 4),
                    memory_score=round(max(0.0, min(1.0, memory_score)), 4),
                    role_score=round(max(0.0, min(1.0, role_score)), 4),
                    final_score=round(max(0.0, min(1.0, value)), 4),
                    score_source=score_source,
                    forbidden=forbidden,
                    risk_level=candidate.risk_level,
                )
            )
        values.sort(key=lambda value: (-value.value, value.candidate_id))
        return values


class HeuristicPlanner:
    name = "decision_memory_policy"

    def propose(
        self,
        *,
        plan: HierarchicalPlan,
        query: DecisionMemoryQuery,
        candidates: Sequence[NavigationCandidate],
        candidate_values: Sequence[CandidateValue],
    ) -> PlannerProposal:
        if query.goal is None:
            return PlannerProposal(
                NavigationAction(name="stop_for_user"), 1.0, self.name, False
            )
        ranked = [value for value in candidate_values if not value.forbidden and value.value > 0.0]
        if ranked and ranked[0].value >= 0.22:
            return PlannerProposal(
                NavigationAction(name="click", candidate_id=ranked[0].candidate_id),
                ranked[0].value,
                self.name,
                False,
            )
        if candidates:
            # Safe exploration is preferable to silently ending on the first
            # screen, but no ungrounded click is allowed.
            return PlannerProposal(
                NavigationAction(name="scroll", direction="down"), 0.2, self.name, False
            )
        return PlannerProposal(
            NavigationAction(name="wait_and_observe"), 0.15, self.name, False
        )


class KExaoneHermesPlanner:
    name = "k_exaone_hermes"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        team: str = "",
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.team = team
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def propose(
        self,
        *,
        plan: HierarchicalPlan,
        query: DecisionMemoryQuery,
        candidates: Sequence[NavigationCandidate],
        candidate_values: Sequence[CandidateValue],
    ) -> PlannerProposal:
        if not self.configured:
            raise RuntimeError("K-EXAONE planner credentials/model are not configured")
        candidate_by_id = {candidate.candidate_id: candidate for candidate in candidates}
        value_by_id = {value.candidate_id: value for value in candidate_values}
        prompt_candidates = []
        for candidate_id, candidate in candidate_by_id.items():
            value = value_by_id[candidate_id]
            prompt_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "label": candidate.label,
                    "role": candidate.role,
                    "icon_semantics": candidate.icon_semantics,
                    "nearby_text": candidate.nearby_text,
                    "parent_semantics": candidate.parent_semantics,
                    "position_bucket": candidate.position_bucket,
                    "risk_level": candidate.risk_level,
                    "candidate_value": value.value,
                    "forbidden": value.forbidden,
                }
            )
        user_packet = {
            "hierarchical_plan": plan.model_dump(mode="json"),
            "decision_memory": query.prompt_payload(),
            "candidate_values": prompt_candidates,
            "instruction": "Select exactly one Hermes tool call. Never invent a candidate_id.",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are the ExitGuide next-action planner. Use the current semantic screen, "
                        "cross-app decision evidence, and candidate values. You have no coordinate tool. "
                        "Only click a candidate_id present in the packet. Never execute payment, account "
                        "deletion confirmation, membership cancellation confirmation, purchase, or personal "
                        "information submission. Stop for the user at a dangerous final action. Return one "
                        "Hermes <tool_call> JSON object and no prose."
                    ),
                },
                {"role": "user", "content": json.dumps(user_packet, ensure_ascii=False)},
            ],
            "tools": _hermes_tools(),
            "tool_choice": "required",
            "temperature": 0.0,
            "max_tokens": 400,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        if self.team:
            headers["X-Friendli-Team"] = self.team
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        action = parse_hermes_action(response.json())
        return PlannerProposal(action, 0.6, self.name, False)


class PlannerRouter:
    def __init__(
        self,
        *,
        provider: str,
        allow_fallback: bool,
        k_exaone: KExaoneHermesPlanner,
    ) -> None:
        self.provider = provider
        self.allow_fallback = allow_fallback
        self.k_exaone = k_exaone
        self.heuristic = HeuristicPlanner()

    @property
    def configured(self) -> bool:
        if self.provider == "k_exaone":
            return self.k_exaone.configured
        return self.provider == "heuristic"

    def propose(
        self,
        *,
        plan: HierarchicalPlan,
        query: DecisionMemoryQuery,
        candidates: Sequence[NavigationCandidate],
        candidate_values: Sequence[CandidateValue],
    ) -> PlannerProposal:
        if self.provider == "heuristic":
            return self.heuristic.propose(
                plan=plan, query=query, candidates=candidates, candidate_values=candidate_values
            )
        if self.provider != "k_exaone":
            raise RuntimeError(f"unsupported navigation planner provider: {self.provider}")
        try:
            return self.k_exaone.propose(
                plan=plan, query=query, candidates=candidates, candidate_values=candidate_values
            )
        except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            if not self.allow_fallback:
                raise
            proposal = self.heuristic.propose(
                plan=plan, query=query, candidates=candidates, candidate_values=candidate_values
            )
            return PlannerProposal(
                proposal.action,
                proposal.confidence,
                f"{self.name_with_requested_provider()}->{proposal.provider}",
                True,
            )

    def name_with_requested_provider(self) -> str:
        return "k_exaone_hermes" if self.provider == "k_exaone" else self.provider


class ActionSafetyGate:
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
        if candidate.candidate_id in forbidden_candidate_ids:
            return (
                NavigationAction(name="wait_and_observe"),
                "replaced_with_safe_action",
                "candidate is forbidden by observed failure memory",
            )
        semantic_text = " ".join(
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
        if is_dangerous_final_candidate(semantic_text):
            return (
                NavigationAction(name="stop_for_user"),
                "replaced_with_safe_action",
                "candidate is a dangerous final action",
            )
        return action, "allowed", "candidate exists on screen and passed the risk gate"


def parse_hermes_action(response_payload: Mapping[str, Any]) -> NavigationAction:
    message = response_payload["choices"][0]["message"]
    tool_calls = message.get("tool_calls") or []
    if tool_calls:
        function = tool_calls[0].get("function", {})
        name = str(function.get("name", ""))
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        return _action_from_tool(name, arguments)
    content = str(message.get("content", "")).strip()
    match = HERMES_TOOL_PATTERN.search(content)
    raw = match.group(1) if match else content.removeprefix("```json").removesuffix("```").strip()
    parsed = json.loads(raw)
    name = str(parsed.get("name") or parsed.get("tool") or parsed.get("function", {}).get("name", ""))
    arguments = parsed.get("arguments") or parsed.get("function", {}).get("arguments") or {}
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    return _action_from_tool(name, arguments)


def _action_from_tool(name: str, arguments: Mapping[str, Any]) -> NavigationAction:
    if name == "click":
        return NavigationAction(name="click", candidate_id=str(arguments.get("candidate_id", "")))
    if name == "scroll":
        return NavigationAction(name="scroll", direction=str(arguments.get("direction", "")))
    if name in {"back", "wait_and_observe", "stop_for_user"}:
        return NavigationAction(name=name)
    raise ValueError(f"unsupported Hermes tool: {name}")


def _hermes_tools() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "Click one candidate that exists on the current screen.",
                "parameters": {
                    "type": "object",
                    "properties": {"candidate_id": {"type": "string"}},
                    "required": ["candidate_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "scroll",
                "description": "Scroll the current surface without selecting a candidate.",
                "parameters": {
                    "type": "object",
                    "properties": {"direction": {"type": "string", "enum": ["up", "down"]}},
                    "required": ["direction"],
                    "additionalProperties": False,
                },
            },
        },
        *[
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }
            for name, description in (
                ("back", "Return to the previous screen when recovery is justified."),
                ("wait_and_observe", "Wait for transient UI or request a fresh observation."),
                ("stop_for_user", "Stop before a dangerous final action or when user input is required."),
            )
        ],
    ]
