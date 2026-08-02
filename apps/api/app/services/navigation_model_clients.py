from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from app.navigation_contracts import NavigationCandidate, ScreenObservation


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


@dataclass(frozen=True)
class PerceptionOutput:
    screen: ScreenObservation
    semantic_summary: str
    provider: str


@dataclass(frozen=True)
class ReflectionOutput:
    outcome: str
    reason: str
    recovery_hint: str


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
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.team = team
        self.timeout_seconds = timeout_seconds
        self.chat_template_kwargs = dict(chat_template_kwargs or {})

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
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


class NavigationPlannerResearchClient:
    """A bounded planner model used for high-level planning and action verification.

    It never emits coordinates. The planner emits only a sub-goal; the verifier
    receives one already-enumerated action and returns a bounded score.
    """

    def __init__(
        self,
        client: OpenAICompatibleChatClient,
        *,
        provider_name: str = "solar_pro3",
    ) -> None:
        self.client = client
        self.name = provider_name.strip() or "planner_model"

    @property
    def configured(self) -> bool:
        return self.client.configured

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
                                "immediate_subgoal": {"type": "string"},
                                "expected_outcome": {"type": "string"},
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
        """Return a K2-style subgoal and V-Droid-style values in one inference."""

        packet = {
            "goal": goal,
            "current_screen": screen,
            "destination_signatures": list(destination_signatures),
            "cross_app_decision_evidence": list(decision_evidence),
            "recent_observed_history": list(recent_history),
            "deterministic_hierarchy_hint": fallback_plan,
            "candidate_actions": list(actions),
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the combined K2-style planner and V-Droid-style batch verifier "
                        "of an Android navigation agent. First form one immediately verifiable "
                        "semantic subgoal, then score every supplied candidate_action independently "
                        "for that subgoal. This is multi-step navigation: a profile, account, or "
                        "settings hub can be highly helpful even when it is not the final destination "
                        "button. Assign one unique best_action_key; use stop_for_user as the best "
                        "action only when no safe progress action exists. Do not execute an action. Never invent an "
                        "action_key, candidate ID, coordinate, or app-specific route. Keep every "
                        "action_key unchanged and return exactly one score for each supplied key. "
                        "The unique best action must have helpful_probability at least 0.5."
                    ),
                },
                {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
            ],
            max_tokens=1_250,
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
                                    "maxItems": 8,
                                },
                                "best_action_key": {"type": "string"},
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
                                },
                            },
                            "required": [
                                "stage",
                                "immediate_subgoal",
                                "expected_outcome",
                                "target_roles",
                                "best_action_key",
                                "scores",
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
        outputs = _parse_batch_scores(payload.get("scores"), actions)
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
        candidate_packet = [
            {
                "candidate_id": candidate.candidate_id,
                "label": candidate.label,
                "role": candidate.role,
                "icon_semantics": candidate.icon_semantics,
                "nearby_text": candidate.nearby_text,
                "parent_semantics": candidate.parent_semantics,
                "position_bucket": candidate.position_bucket,
            }
            for candidate in screen.candidates
        ]
        prompt = {
            "goal": goal_text,
            "accessibility_ocr_candidates": candidate_packet,
            "required_output": {
                "semantic_summary": "screen-level meaning",
                "candidate_annotations": [
                    {
                        "candidate_id": "must be one of the supplied IDs",
                        "icon_semantics": "",
                        "nearby_text": "",
                        "parent_semantics": "",
                    }
                ],
            },
        }
        response = self.client.complete(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are the visual perception module for Android navigation. Describe the "
                        "whole screen semantically and annotate only candidate IDs supplied by the "
                        "client. Never invent a candidate, coordinate, route, or action. Return JSON."
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
            max_tokens=900,
            temperature=0.6,
            top_p=0.95,
            presence_penalty=1.5,
        )
        payload = _response_json(response)
        annotations = payload.get("candidate_annotations", [])
        if not isinstance(annotations, list):
            annotations = []
        annotation_by_id = {
            str(annotation.get("candidate_id")): annotation
            for annotation in annotations
            if isinstance(annotation, Mapping)
        }
        allowed_ids = {candidate.candidate_id for candidate in screen.candidates}
        annotation_by_id = {
            candidate_id: annotation
            for candidate_id, annotation in annotation_by_id.items()
            if candidate_id in allowed_ids
        }
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
                    }
                )
            )
        return PerceptionOutput(
            screen=screen.model_copy(update={"candidates": enriched}),
            semantic_summary=str(payload.get("semantic_summary", ""))[:1000],
            provider=self.name,
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
