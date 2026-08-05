from __future__ import annotations

import json
import logging
import re
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from app.navigation_contracts import NavigationCandidate, ScreenObservation


LOGGER = logging.getLogger(__name__)
JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass(frozen=True)
class PlannerOutput:
    stage: str
    immediate_subgoal: str
    expected_outcome: str
    target_roles: tuple[str, ...]


@dataclass(frozen=True)
class VerifierOutput:
    helpful_probability: float
    expected_progress: str
    reason: str
    model_ranked: bool = True


@dataclass(frozen=True)
class PerceptionOutput:
    screen: ScreenObservation
    semantic_summary: str
    provider: str
    recommended_candidate_id: str | None = None


@dataclass(frozen=True)
class ReflectionOutput:
    outcome: str
    reason: str
    recovery_hint: str


@dataclass(frozen=True)
class GoalClassificationOutput:
    goal_id: str | None
    confidence: float
    reason: str


class OpenAICompatibleChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        team: str = "",
        timeout_seconds: float = 30.0,
        chat_template_kwargs: Mapping[str, object] | None = None,
        reasoning_effort: str = "",
        telemetry_name: str = "",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.team = team
        self.timeout_seconds = timeout_seconds
        self.chat_template_kwargs = dict(chat_template_kwargs or {})
        self.reasoning_effort = reasoning_effort.strip()
        self.telemetry_name = telemetry_name.strip() or model

    @property
    def configured(self) -> bool:
        local_endpoint = self.base_url.startswith(("http://127.0.0.1", "http://localhost"))
        return bool(self.base_url and self.model and (self.api_key or local_endpoint))

    def complete(
        self,
        *,
        messages: list[dict[str, object]],
        max_tokens: int,
        temperature: float = 0.0,
        top_p: float | None = None,
        presence_penalty: float | None = None,
        tools: list[dict[str, object]] | None = None,
        tool_choice: object | None = None,
    ) -> Mapping[str, Any]:
        if not self.configured:
            raise RuntimeError("model endpoint and model name are not configured")
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.chat_template_kwargs:
            payload["chat_template_kwargs"] = self.chat_template_kwargs
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if top_p is not None:
            payload["top_p"] = top_p
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.team:
            headers["X-Friendli-Team"] = self.team
        operation = "chat"
        if isinstance(tool_choice, Mapping):
            function = tool_choice.get("function")
            if isinstance(function, Mapping):
                operation = str(function.get("name", operation))
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError):
            LOGGER.warning(
                "navigation_model_call_failed provider=%s model=%s operation=%s "
                "elapsed_ms=%.1f timeout_seconds=%.1f",
                self.telemetry_name,
                self.model,
                operation,
                (time.perf_counter() - started) * 1000,
                self.timeout_seconds,
            )
            raise
        usage = result.get("usage", {}) if isinstance(result, Mapping) else {}
        choices = result.get("choices", []) if isinstance(result, Mapping) else []
        finish_reason = (
            choices[0].get("finish_reason", "unknown")
            if isinstance(choices, list) and choices and isinstance(choices[0], Mapping)
            else "unknown"
        )
        LOGGER.info(
            "navigation_model_call provider=%s model=%s operation=%s elapsed_ms=%.1f "
            "prompt_tokens=%s completion_tokens=%s finish_reason=%s reasoning_effort=%s",
            self.telemetry_name,
            self.model,
            operation,
            (time.perf_counter() - started) * 1000,
            usage.get("prompt_tokens", "unknown") if isinstance(usage, Mapping) else "unknown",
            usage.get("completion_tokens", "unknown") if isinstance(usage, Mapping) else "unknown",
            finish_reason,
            self.reasoning_effort or "provider_default",
        )
        return result


class NavigationPlannerResearchClient:
    """A bounded planner model used for high-level planning and action verification.

    It never emits coordinates. The planner emits only a sub-goal; the verifier
    receives one already-enumerated action and returns a bounded score.
    """

    def __init__(
        self,
        client: OpenAICompatibleChatClient,
        *,
        provider_name: str = "solar_pro4",
        step_evaluation_max_tokens: int = 400,
    ) -> None:
        self.client = client
        self.name = provider_name.strip() or "planner_model"
        self.step_evaluation_max_tokens = max(240, min(600, step_evaluation_max_tokens))

    @property
    def configured(self) -> bool:
        return self.client.configured

    def classify_goal(
        self,
        *,
        goal_text: str,
        locale: str,
        goal_catalog: Sequence[Mapping[str, object]],
    ) -> GoalClassificationOutput:
        """Select one DB-owned goal ID without allowing the model to invent IDs."""

        allowed_ids = tuple(
            sorted(
                {
                    str(item.get("goal_id", "")).strip()
                    for item in goal_catalog
                    if str(item.get("goal_id", "")).strip()
                }
            )
        )
        if not allowed_ids:
            raise ValueError("Goal Ontology DB returned no active goal IDs")
        out_of_scope = "__out_of_scope__"
        packet = {
            "user_goal_text": goal_text,
            "locale": locale,
            "goal_ontology": list(goal_catalog),
            "instruction": (
                "Return one supplied goal_id when the intent is supported. "
                "Otherwise return __out_of_scope__."
            ),
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the Goal Ontology classifier for an Android navigation agent. "
                        "Interpret the user's natural-language intent and select exactly one ID "
                        "from the supplied Goal Ontology DB catalog. Never invent, rewrite, or "
                        "combine goal IDs. Opposite operations such as join and cancel must remain "
                        "distinct. Use __out_of_scope__ only when none of the supplied goals fit."
                    ),
                },
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
            max_tokens=120,
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "select_navigation_goal",
                        "description": "Select one and only one Goal Ontology DB ID.",
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "goal_id": {
                                    "type": "string",
                                    "enum": [*allowed_ids, out_of_scope],
                                },
                                "confidence": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["goal_id", "confidence", "reason"],
                        },
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "select_navigation_goal"},
            },
        )
        payload = _response_json(response, expected_tool="select_navigation_goal")
        goal_id = str(payload.get("goal_id", "")).strip()
        if goal_id == out_of_scope:
            selected_goal_id = None
        elif goal_id in allowed_ids:
            selected_goal_id = goal_id
        else:
            raise ValueError("Goal classifier returned an ID outside the DB allowlist")
        confidence = float(payload.get("confidence", 0.0))
        return GoalClassificationOutput(
            goal_id=selected_goal_id,
            confidence=max(0.0, min(1.0, confidence)),
            reason=str(payload.get("reason", ""))[:500],
        )

    def plan(
        self,
        *,
        goal: Mapping[str, object],
        screen: Mapping[str, object],
        destination_signatures: Sequence[Mapping[str, object]],
        decision_evidence: Sequence[Mapping[str, object]],
        recent_history: Sequence[Mapping[str, object]],
        target_roles: Sequence[str],
    ) -> PlannerOutput:
        packet = {
            "goal": goal,
            "current_screen": screen,
            "destination_signatures": list(destination_signatures),
            "cross_app_decision_evidence": list(decision_evidence),
            "recent_observed_history": list(recent_history),
            "candidate_role_hints": list(target_roles),
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the high-level planner of an Android navigation agent. "
                        "Follow a K2-style planner/executor separation. Do not choose an action, "
                        "candidate ID, coordinate, or app-specific route. Produce one immediately "
                        "verifiable semantic subgoal and its expected next-screen outcome. Return "
                        "JSON with stage, immediate_subgoal, expected_outcome, target_roles."
                    ),
                },
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
            max_tokens=450,
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_navigation_subgoal",
                        "description": "Submit one semantic subgoal; never submit an action.",
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "stage": {
                                    "type": "string",
                                    "enum": [
                                        "hub_discovery",
                                        "destination_entry",
                                        "destination_verification",
                                        "selective_recovery",
                                    ],
                                },
                                "immediate_subgoal": {
                                    "type": "string",
                                    "maxLength": 60,
                                },
                                "expected_outcome": {
                                    "type": "string",
                                    "maxLength": 60,
                                },
                                "target_roles": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 8,
                                },
                            },
                            "required": [
                                "stage",
                                "immediate_subgoal",
                                "expected_outcome",
                                "target_roles",
                            ],
                        },
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "submit_navigation_subgoal"},
            },
        )
        payload = _response_json(response, expected_tool="submit_navigation_subgoal")
        stage = str(payload.get("stage", "hub_discovery"))
        if stage not in {
            "hub_discovery",
            "destination_entry",
            "destination_verification",
            "selective_recovery",
        }:
            stage = "hub_discovery"
        roles = payload.get("target_roles", [])
        if not isinstance(roles, list):
            roles = []
        return PlannerOutput(
            stage=stage,
            immediate_subgoal=str(payload.get("immediate_subgoal", "")).strip()[:500],
            expected_outcome=str(payload.get("expected_outcome", "")).strip()[:500],
            target_roles=tuple(str(role)[:120] for role in roles[:8]),
        )

    def verify_action(
        self,
        *,
        goal: Mapping[str, object],
        subgoal: str,
        expected_outcome: str,
        screen: Mapping[str, object],
        recent_history: Sequence[Mapping[str, object]],
        action: Mapping[str, object],
        memory_prior: float,
        decision_evidence: Sequence[Mapping[str, object]],
    ) -> VerifierOutput:
        packet = {
            "goal": goal,
            "immediate_subgoal": subgoal,
            "expected_outcome": expected_outcome,
            "current_screen": screen,
            "recent_observed_history": list(recent_history),
            "candidate_action": action,
            "decision_memory_prior": memory_prior,
            "cross_app_evidence": list(decision_evidence),
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Act as a V-Droid-style verifier, not an action generator. Evaluate only "
                        "the single candidate_action provided. Decide whether it is helpful for "
                        "the immediate subgoal from the current screen. A prior is evidence, not "
                        "ground truth. Penalize repeats and observed failures. Return JSON with "
                        "helpful_probability (0..1), expected_progress, reason."
                    ),
                },
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
            max_tokens=220,
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "score_navigation_candidate",
                        "description": "Score only the supplied candidate action.",
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "helpful_probability": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                                "expected_progress": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": [
                                "helpful_probability",
                                "expected_progress",
                                "reason",
                            ],
                        },
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "score_navigation_candidate"},
            },
        )
        payload = _response_json(response, expected_tool="score_navigation_candidate")
        probability = float(payload.get("helpful_probability", 0.0))
        return VerifierOutput(
            helpful_probability=max(0.0, min(1.0, probability)),
            expected_progress=str(payload.get("expected_progress", "unknown"))[:120],
            reason=str(payload.get("reason", ""))[:500],
        )

    def verify_actions(
        self,
        *,
        goal: Mapping[str, object],
        subgoal: str,
        expected_outcome: str,
        screen: Mapping[str, object],
        recent_history: Sequence[Mapping[str, object]],
        actions: Sequence[Mapping[str, object]],
        decision_evidence: Sequence[Mapping[str, object]],
    ) -> dict[str, VerifierOutput]:
        """Score the bounded action allowlist in one model round trip.

        This preserves V-Droid-style per-candidate values while avoiding one
        expensive planner-model request for every visible candidate.
        """

        packet = {
            "goal": goal,
            "immediate_subgoal": subgoal,
            "expected_outcome": expected_outcome,
            "current_screen": screen,
            "recent_observed_history": list(recent_history),
            "candidate_actions": list(actions),
            "cross_app_evidence": list(decision_evidence),
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Act as a V-Droid-style batch verifier, not an action generator. "
                        "Score every supplied candidate_action independently for the immediate "
                        "subgoal. Keep each action_key unchanged. Priors are evidence, not ground "
                        "truth. Penalize repeats and observed failures. Return exactly one score "
                        "for every supplied action_key."
                    ),
                },
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
            max_tokens=900,
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "score_navigation_candidates",
                        "description": "Score all and only the supplied candidate actions.",
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "scores": {
                                    "type": "array",
                                    "maxItems": 20,
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "action_key": {"type": "string"},
                                            "helpful_probability": {
                                                "type": "number",
                                                "minimum": 0.0,
                                                "maximum": 1.0,
                                            },
                                            "expected_progress": {"type": "string"},
                                            "reason": {"type": "string"},
                                        },
                                        "required": [
                                            "action_key",
                                            "helpful_probability",
                                            "expected_progress",
                                            "reason",
                                        ],
                                    },
                                }
                            },
                            "required": ["scores"],
                        },
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "score_navigation_candidates"},
            },
        )
        payload = _response_json(response, expected_tool="score_navigation_candidates")
        raw_scores = payload.get("scores", [])
        if not isinstance(raw_scores, list):
            raise ValueError("batch verifier scores must be a list")
        expected_keys = {str(item.get("action_key", "")) for item in actions}
        outputs: dict[str, VerifierOutput] = {}
        for item in raw_scores:
            if not isinstance(item, Mapping):
                continue
            action_key = str(item.get("action_key", ""))
            if action_key not in expected_keys or action_key in outputs:
                continue
            probability = float(item.get("helpful_probability", 0.0))
            outputs[action_key] = VerifierOutput(
                helpful_probability=max(0.0, min(1.0, probability)),
                expected_progress=str(item.get("expected_progress", "unknown"))[:120],
                reason=str(item.get("reason", ""))[:500],
            )
        if set(outputs) != expected_keys:
            raise ValueError("batch verifier omitted or invented action keys")
        return outputs

    def plan_and_verify_actions(
        self,
        *,
        goal: Mapping[str, object],
        screen: Mapping[str, object],
        destination_signatures: Sequence[Mapping[str, object]],
        decision_evidence: Sequence[Mapping[str, object]],
        recent_history: Sequence[Mapping[str, object]],
        fallback_plan: Mapping[str, object],
        actions: Sequence[Mapping[str, object]],
    ) -> tuple[PlannerOutput, dict[str, VerifierOutput]]:
        """Return one bounded subgoal and the model's top-two actions in one inference.

        Python retains the complete action inventory. Non-ranked actions keep a
        capped deterministic prior so safety guards can still inspect every
        action without making Solar serialize a score for each candidate.
        """

        packet = {
            "goal": goal,
            "current_screen": screen,
            "destination_signatures": list(destination_signatures),
            "cross_app_decision_evidence": list(decision_evidence),
            "recent_observed_history": list(recent_history),
            "deterministic_hierarchy_hint": fallback_plan,
            "candidate_actions": list(actions),
        }
        expected_action_keys = [
            str(item.get("action_key", "")) for item in actions
        ]
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Choose one safe intermediate action for an Android navigation agent. "
                        "Form one immediately verifiable semantic subgoal, then return the best "
                        "and runner-up action keys only. Prefer a candidate's own label and icon "
                        "over nearby text. A profile, account, or settings hub may be useful before "
                        "the final destination. Treat unverified_public_prior only as a weak hint. "
                        "Never invent or execute an action, coordinate, candidate ID, or route. "
                        "Use stop_for_user only when no safe progress action exists. The best key "
                        "must be unique, have probability at least 0.5, and exceed the runner-up."
                    ),
                },
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
            max_tokens=self.step_evaluation_max_tokens,
            temperature=0.0,
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_navigation_step_evaluation",
                        "description": (
                            "Submit one semantic subgoal and independent values for the bounded "
                            "action allowlist; do not choose an action."
                        ),
                        "parameters": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "stage": {
                                    "type": "string",
                                    "enum": [
                                        "hub_discovery",
                                        "destination_entry",
                                        "destination_verification",
                                        "selective_recovery",
                                    ],
                                },
                                "immediate_subgoal": {"type": "string"},
                                "expected_outcome": {"type": "string"},
                                "target_roles": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "maxItems": 4,
                                },
                                "best_action_key": {
                                    "type": "string",
                                    "enum": expected_action_keys,
                                },
                                "best_probability": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                                "runner_up_action_key": {
                                    "type": "string",
                                    "enum": expected_action_keys,
                                },
                                "runner_up_probability": {
                                    "type": "number",
                                    "minimum": 0.0,
                                    "maximum": 1.0,
                                },
                                "expected_progress": {
                                    "type": "string",
                                    "maxLength": 60,
                                },
                                "decision_reason": {
                                    "type": "string",
                                    "maxLength": 100,
                                },
                            },
                            "required": [
                                "stage",
                                "immediate_subgoal",
                                "expected_outcome",
                                "target_roles",
                                "best_action_key",
                                "best_probability",
                                "runner_up_action_key",
                                "runner_up_probability",
                                "expected_progress",
                                "decision_reason",
                            ],
                        },
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "submit_navigation_step_evaluation"},
            },
        )
        payload = _response_json(
            response,
            expected_tool="submit_navigation_step_evaluation",
        )
        stage = str(payload.get("stage", "hub_discovery"))
        if stage not in {
            "hub_discovery",
            "destination_entry",
            "destination_verification",
            "selective_recovery",
        }:
            stage = "hub_discovery"
        roles = payload.get("target_roles", [])
        if not isinstance(roles, list):
            roles = []
        plan = PlannerOutput(
            stage=stage,
            immediate_subgoal=str(payload.get("immediate_subgoal", ""))[:500],
            expected_outcome=str(payload.get("expected_outcome", ""))[:500],
            target_roles=tuple(str(role)[:120] for role in roles[:8]),
        )
        outputs = _parse_top_two_scores(
            payload,
            actions,
            expected_progress=str(payload.get("expected_progress", "unknown"))[:120],
            reason=str(payload.get("decision_reason", ""))[:500],
        )
        best_action_key = str(payload.get("best_action_key", ""))
        ranked = sorted(
            outputs.items(),
            key=lambda item: (-item[1].helpful_probability, item[0]),
        )
        if not ranked or best_action_key not in outputs:
            raise ValueError("step evaluator omitted or invented best_action_key")
        best_key, best_output = ranked[0]
        second_probability = ranked[1][1].helpful_probability if len(ranked) > 1 else 0.0
        if (
            best_key != best_action_key
            or best_output.helpful_probability < 0.5
            or best_output.helpful_probability - second_probability < 0.02
        ):
            raise ValueError("step evaluator returned an uninformative or inconsistent ranking")
        return plan, outputs

    def reflect_trajectory(
        self,
        *,
        goal: Mapping[str, object],
        plan: Mapping[str, object],
        recent_history: Sequence[Mapping[str, object]],
        latest_observation: Mapping[str, object],
    ) -> ReflectionOutput:
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a MobileUse-style trajectory reflector for Android navigation. "
                        "Diagnose only repeated actions/screens or accumulated observed failures. "
                        "Do not invent coordinates, candidate IDs, or app-specific routes. Return "
                        "JSON with outcome (met, failed, uncertain), reason, and recovery_hint "
                        "(reselect, back, wait_and_observe, stop_for_user)."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "plan": plan,
                            "recent_observed_history": list(recent_history),
                            "latest_observation": latest_observation,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            max_tokens=400,
            temperature=0.0,
        )
        return _reflection_output(response)

    def reflect_global(
        self,
        *,
        goal: Mapping[str, object],
        plan: Mapping[str, object],
        destination_match: float | None,
        recent_history: Sequence[Mapping[str, object]],
    ) -> ReflectionOutput:
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the global completion reflector for a safety-critical Android "
                        "navigation agent. Verify whether the semantic destination is reached, but "
                        "never authorize a purchase, cancellation confirmation, account deletion, "
                        "or personal-data submission. Return JSON with outcome (met, failed, "
                        "uncertain), reason, and recovery_hint (reselect, back, "
                        "wait_and_observe, stop_for_user)."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "plan": plan,
                            "destination_match": destination_match,
                            "recent_observed_history": list(recent_history),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            max_tokens=350,
            temperature=0.0,
        )
        return _reflection_output(response)


class Exaone45VisionClient:
    """EXAONE 4.5 annotates existing candidate IDs; it cannot create taps."""

    name = "exaone_4_5"

    def __init__(self, client: OpenAICompatibleChatClient) -> None:
        self.client = client

    @property
    def configured(self) -> bool:
        return self.client.configured

    def perceive(
        self,
        *,
        goal_text: str,
        screen: ScreenObservation,
        screenshot_data_url: str,
    ) -> PerceptionOutput:
        allowed_ids = {candidate.candidate_id for candidate in screen.candidates}
        candidate_id_enum = sorted(allowed_ids)
        candidate_packet = [
            {
                "candidate_id": candidate.candidate_id,
                "label": candidate.label[:160],
                "role": candidate.role,
                "icon_semantics": candidate.icon_semantics[:80],
                "nearby_text": candidate.nearby_text[:120],
                "parent_semantics": candidate.parent_semantics[:80],
                "position_bucket": candidate.position_bucket,
            }
            for candidate in screen.candidates
        ]
        prompt = {
            "goal": goal_text,
            "accessibility_ocr_candidates": candidate_packet,
            "required_output": {
                "semantic_summary": "screen-level meaning",
                "annotation_policy": (
                    "Annotate at most 4 candidates whose icon or context is missing; "
                    "omit candidates already clear from text."
                ),
                "candidate_annotations": [
                    {
                        "candidate_id": "must be one of the supplied IDs",
                        "icon_semantics": "",
                        "visual_role": "candidate function inferred from the image",
                        "visual_region": "screen region containing the candidate",
                        "goal_relevance": "number between 0 and 1",
                    }
                ],
                "recommended_candidate_id": "one supplied ID or null",
            },
        }
        tool_name = "annotate_navigation_screen"
        tools = [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": (
                        "Annotate the current Android screen using only candidate IDs supplied "
                        "by the client. Never create coordinates or new candidates."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "semantic_summary": {"type": "string", "maxLength": 400},
                            "candidate_annotations": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "candidate_id": {
                                            "type": "string",
                                            "enum": candidate_id_enum,
                                        },
                                        "icon_semantics": {
                                            "type": "string",
                                            "maxLength": 80,
                                        },
                                        "visual_role": {"type": "string", "maxLength": 100},
                                        "visual_region": {"type": "string", "maxLength": 80},
                                        "goal_relevance": {
                                            "type": "number",
                                            "minimum": 0.0,
                                            "maximum": 1.0,
                                        },
                                    },
                                    "required": ["candidate_id"],
                                    "additionalProperties": False,
                                },
                            },
                            "recommended_candidate_id": {
                                "type": ["string", "null"],
                                "enum": [*candidate_id_enum, None],
                            },
                        },
                        "required": [
                            "semantic_summary",
                            "candidate_annotations",
                            "recommended_candidate_id",
                        ],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the visual perception module for Android navigation. Describe the "
                        "whole screen semantically and annotate only candidate IDs supplied by the "
                        "client. Use one short sentence for semantic_summary. Emit at most 4 "
                        "compact annotations and omit already-clear text candidates. Keep every "
                        "annotation string under 100 characters. Never invent a candidate, "
                        "coordinate, route, or action. "
                        "Return the result only through the required tool."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": screenshot_data_url}},
                        {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)},
                    ],
                },
            ],
            max_tokens=360,
            temperature=0.0,
            top_p=1.0,
            presence_penalty=0.0,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        payload = _response_json(response, expected_tool=tool_name)
        annotations = payload.get("candidate_annotations", [])
        if not isinstance(annotations, list):
            annotations = []
        annotation_by_id = {
            str(annotation.get("candidate_id")): annotation
            for annotation in annotations[:8]
            if isinstance(annotation, Mapping)
        }
        returned_ids = set(annotation_by_id)
        annotation_by_id = {
            candidate_id: annotation
            for candidate_id, annotation in annotation_by_id.items()
            if candidate_id in allowed_ids
        }
        LOGGER.info(
            "vlm_candidate_allowlist supplied=%d returned=%d accepted=%d rejected=%d",
            len(allowed_ids),
            len(returned_ids),
            len(annotation_by_id),
            len(returned_ids - allowed_ids),
        )
        raw_recommended_candidate_id = str(payload.get("recommended_candidate_id") or "")
        recommended_candidate_id = raw_recommended_candidate_id
        if recommended_candidate_id not in allowed_ids:
            recommended_candidate_id = ""
        LOGGER.info(
            "vlm_recommendation_allowlist returned=%s accepted=%s",
            bool(raw_recommended_candidate_id),
            bool(recommended_candidate_id),
        )
        enriched = []
        for candidate in screen.candidates:
            annotation = annotation_by_id.get(candidate.candidate_id, {})
            enriched.append(
                candidate.model_copy(
                    update={
                        "icon_semantics": _prefer(candidate.icon_semantics, annotation.get("icon_semantics")),
                        "nearby_text": _prefer(candidate.nearby_text, annotation.get("nearby_text")),
                        "parent_semantics": _prefer(
                            candidate.parent_semantics, annotation.get("parent_semantics")
                        ),
                        "visual_role": str(annotation.get("visual_role", ""))[:200],
                        "visual_region": str(annotation.get("visual_region", ""))[:200],
                        "visual_relevance": _bounded_optional_score(
                            annotation.get("goal_relevance")
                        ),
                    }
                )
            )
        return PerceptionOutput(
            screen=screen.model_copy(update={"candidates": enriched}),
            semantic_summary=str(payload.get("semantic_summary", ""))[:1000],
            provider=self.name,
            recommended_candidate_id=recommended_candidate_id or None,
        )

    def reflect_action(
        self,
        *,
        goal_text: str,
        action: Mapping[str, object],
        expected_outcome: str,
        before_screenshot_data_url: str,
        after_screenshot_data_url: str,
        semantic_observation: Mapping[str, object],
    ) -> ReflectionOutput:
        prompt = {
            "goal": goal_text,
            "action": action,
            "expected_outcome": expected_outcome,
            "semantic_observation": semantic_observation,
            "instruction": (
                "Compare before and after. Return JSON: outcome one of met, failed, uncertain; "
                "reason; recovery_hint one of reselect, back, wait_and_observe, stop_for_user."
            ),
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an on-demand action reflector. Verify observed effect; do not "
                        "invent an action and do not confuse transport errors with UI failure."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": before_screenshot_data_url}},
                        {"type": "image_url", "image_url": {"url": after_screenshot_data_url}},
                        {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)},
                    ],
                },
            ],
            max_tokens=350,
            temperature=0.6,
            top_p=0.95,
            presence_penalty=1.5,
        )
        payload = _response_json(response)
        outcome = str(payload.get("outcome", "uncertain"))
        if outcome not in {"met", "failed", "uncertain"}:
            outcome = "uncertain"
        recovery = str(payload.get("recovery_hint", "wait_and_observe"))
        if recovery not in {"reselect", "back", "wait_and_observe", "stop_for_user"}:
            recovery = "wait_and_observe"
        return ReflectionOutput(outcome, str(payload.get("reason", ""))[:500], recovery)


class FallbackNavigationPlannerResearchClient:
    """Use the stable planner only when the primary model call is unusable."""

    def __init__(
        self,
        *,
        primary: NavigationPlannerResearchClient,
        fallback: NavigationPlannerResearchClient | None,
        failover_on_timeout: bool = False,
        failover_on_invalid_output: bool = False,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.failover_on_timeout = failover_on_timeout
        self.failover_on_invalid_output = failover_on_invalid_output
        self.name = primary.name
        self._active_name: ContextVar[str] = ContextVar(
            "navigation_planner_active_name", default=primary.name
        )

    @property
    def configured(self) -> bool:
        return self.primary.configured or bool(self.fallback and self.fallback.configured)

    @property
    def active_name(self) -> str:
        return self._active_name.get()

    @property
    def fallback_name(self) -> str | None:
        return None if self.fallback is None else self.fallback.name

    @property
    def fallback_configured(self) -> bool:
        return bool(self.fallback and self.fallback.configured)

    def _call(self, method: str, **kwargs):
        if self.primary.configured:
            try:
                result = getattr(self.primary, method)(**kwargs)
                self._active_name.set(self.primary.name)
                return result
            except (RuntimeError, httpx.HTTPError, KeyError, TypeError, ValueError) as error:
                if isinstance(error, httpx.TimeoutException) and not self.failover_on_timeout:
                    raise
                if isinstance(error, (KeyError, TypeError, ValueError)) and not self.failover_on_invalid_output:
                    raise
                if self.fallback is None or not self.fallback.configured:
                    raise
                LOGGER.warning(
                    "planner_model_provider_failover primary=%s fallback=%s "
                    "method=%s failure_class=%s detail=%s",
                    self.primary.name,
                    self.fallback.name,
                    method,
                    type(error).__name__,
                    str(error)[:500],
                )
        if self.fallback is None or not self.fallback.configured:
            raise RuntimeError("no configured planner model provider")
        result = getattr(self.fallback, method)(**kwargs)
        self._active_name.set(self.fallback.name)
        return result

    def classify_goal(self, **kwargs):
        return self._call("classify_goal", **kwargs)

    def plan(self, **kwargs):
        return self._call("plan", **kwargs)

    def verify_action(self, **kwargs):
        return self._call("verify_action", **kwargs)

    def verify_actions(self, **kwargs):
        return self._call("verify_actions", **kwargs)

    def plan_and_verify_actions(self, **kwargs):
        return self._call("plan_and_verify_actions", **kwargs)

    def reflect_trajectory(self, **kwargs):
        return self._call("reflect_trajectory", **kwargs)

    def reflect_global(self, **kwargs):
        return self._call("reflect_global", **kwargs)


def _response_json(
    response: Mapping[str, Any], *, expected_tool: str | None = None
) -> Mapping[str, Any]:
    message = response["choices"][0]["message"]
    tool_calls = message.get("tool_calls", [])
    if isinstance(tool_calls, list) and tool_calls:
        function = tool_calls[0].get("function", {})
        tool_name = str(function.get("name", ""))
        if expected_tool is not None and tool_name != expected_tool:
            raise ValueError(f"unexpected model tool call: {tool_name}")
        arguments = function.get("arguments", "{}")
        payload = json.loads(arguments) if isinstance(arguments, str) else arguments
        if not isinstance(payload, Mapping):
            raise ValueError("model tool arguments must be a JSON object")
        return payload
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) for item in content if isinstance(item, Mapping))
    text = str(content).strip()
    match = JSON_FENCE.search(text)
    if match:
        text = match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise ValueError("model response JSON must be an object")
    return payload


def _reflection_output(response: Mapping[str, Any]) -> ReflectionOutput:
    payload = _response_json(response)
    outcome = str(payload.get("outcome", "uncertain"))
    if outcome not in {"met", "failed", "uncertain"}:
        outcome = "uncertain"
    recovery = str(payload.get("recovery_hint", "wait_and_observe"))
    if recovery not in {"reselect", "back", "wait_and_observe", "stop_for_user"}:
        recovery = "wait_and_observe"
    return ReflectionOutput(outcome, str(payload.get("reason", ""))[:500], recovery)


def _prefer(existing: str, proposed: object) -> str:
    if existing:
        return existing
    return str(proposed or "")[:500]


def _bounded_optional_score(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _parse_batch_scores(
    raw_scores: object,
    actions: Sequence[Mapping[str, object]],
) -> dict[str, VerifierOutput]:
    if not isinstance(raw_scores, list):
        raise ValueError("batch verifier scores must be a list")
    expected_keys = {str(item.get("action_key", "")) for item in actions}
    outputs: dict[str, VerifierOutput] = {}
    for item in raw_scores:
        if not isinstance(item, Mapping):
            continue
        action_key = str(item.get("action_key", ""))
        if action_key not in expected_keys or action_key in outputs:
            continue
        probability = float(item.get("helpful_probability", 0.0))
        outputs[action_key] = VerifierOutput(
            helpful_probability=max(0.0, min(1.0, probability)),
            expected_progress=str(item.get("expected_progress", "unknown"))[:120],
            reason=str(item.get("reason", ""))[:500],
        )
    if set(outputs) != expected_keys:
        raise ValueError("batch verifier omitted or invented action keys")
    return outputs


def _parse_top_two_scores(
    payload: Mapping[str, object],
    actions: Sequence[Mapping[str, object]],
    *,
    expected_progress: str,
    reason: str,
) -> dict[str, VerifierOutput]:
    action_by_key = {
        str(item.get("action_key", "")): item
        for item in actions
        if str(item.get("action_key", ""))
    }
    best_key = str(payload.get("best_action_key", ""))
    runner_up_key = str(payload.get("runner_up_action_key", ""))
    if (
        best_key not in action_by_key
        or runner_up_key not in action_by_key
        or best_key == runner_up_key
    ):
        raise ValueError("step evaluator returned invalid top-two action keys")
    best_probability = max(0.0, min(1.0, float(payload.get("best_probability", 0.0))))
    runner_up_probability = max(
        0.0,
        min(1.0, float(payload.get("runner_up_probability", 0.0))),
    )
    if best_probability < 0.5 or best_probability - runner_up_probability < 0.02:
        raise ValueError("step evaluator returned an uninformative top-two ranking")

    outputs: dict[str, VerifierOutput] = {}
    prior_ceiling = max(0.0, runner_up_probability - 0.03)
    for action_key, action in action_by_key.items():
        if action_key == best_key:
            probability = best_probability
            ranked_reason = reason or "model_best_action"
            model_ranked = True
        elif action_key == runner_up_key:
            probability = runner_up_probability
            ranked_reason = "model_runner_up"
            model_ranked = True
        else:
            probability = min(
                max(0.0, min(1.0, float(action.get("memory_prior", 0.0)))),
                prior_ceiling,
            )
            ranked_reason = "deterministic_prior_capped_below_model_top_two"
            model_ranked = False
        outputs[action_key] = VerifierOutput(
            helpful_probability=probability,
            expected_progress=expected_progress or "unknown",
            reason=ranked_reason,
            model_ranked=model_ranked,
        )
    return outputs
