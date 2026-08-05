from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from .models import JsonObject, PolicyDecision, PolicyVerdict
from .predicates import PredicateError, evaluate_predicate, fact_value


ALLOWED_VERDICTS = {item.value for item in PolicyVerdict}
SAFE_ACTION_FOR_VERDICT = {
    PolicyVerdict.REOBSERVE: {"name": "wait_and_observe"},
    PolicyVerdict.REQUIRE_CONFIRMATION: {"name": "stop_for_user"},
    PolicyVerdict.BLOCK: {"name": "stop_for_user"},
}


class LogicPolicyVerifier:
    """Versioned, deterministic pre-action rules inspired by VeriSafe.

    This is a policy interpreter, not a claim of whole-program formal proof.
    Facts must be assembled from trusted runtime observations by the adapter.
    """

    def __init__(self, policy_path: str | Path) -> None:
        self.policy_path = Path(policy_path)
        payload = json.loads(self.policy_path.read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("navigation safety policy must be an object")
        self._validate_policy(payload)
        self.policy_id = str(payload["policy_id"])
        self.policy_version = str(payload["policy_version"])
        self.default_verdict = PolicyVerdict(str(payload["default_verdict"]))
        self.rules = tuple(payload["rules"])

    @staticmethod
    def _validate_policy(payload: Mapping[str, Any]) -> None:
        if payload.get("schema_version") != "1.0":
            raise ValueError("navigation safety policy schema_version must be 1.0")
        for key in ("policy_id", "policy_version", "default_verdict", "rules"):
            if key not in payload:
                raise ValueError(f"navigation safety policy is missing {key}")
        if payload["default_verdict"] not in ALLOWED_VERDICTS:
            raise ValueError("invalid default policy verdict")
        if not isinstance(payload["rules"], list):
            raise ValueError("navigation safety policy rules must be a list")
        seen: set[str] = set()
        for rule in payload["rules"]:
            if not isinstance(rule, Mapping):
                raise ValueError("navigation safety rule must be an object")
            rule_id = rule.get("rule_id")
            if not isinstance(rule_id, str) or not rule_id:
                raise ValueError("navigation safety rule_id must be a string")
            if rule_id in seen:
                raise ValueError(f"duplicate navigation safety rule_id: {rule_id}")
            seen.add(rule_id)
            if rule.get("verdict") not in ALLOWED_VERDICTS:
                raise ValueError(f"invalid verdict in rule {rule_id}")
            if not isinstance(rule.get("actions"), list) or not rule["actions"]:
                raise ValueError(f"actions are required in rule {rule_id}")
            if not isinstance(rule.get("when"), Mapping):
                raise ValueError(f"when predicate is required in rule {rule_id}")
            try:
                evaluate_predicate(rule["when"], {})
            except PredicateError:
                raise

    def verify(
        self,
        *,
        proposed_action: Mapping[str, Any],
        facts: Mapping[str, Any],
        confirmation_id: str | None = None,
    ) -> PolicyDecision:
        started = time.perf_counter()
        action = dict(proposed_action)
        action_name = str(action.get("name", ""))
        matched_rule: Mapping[str, Any] | None = None
        for rule in self.rules:
            if action_name not in rule["actions"]:
                continue
            if evaluate_predicate(rule["when"], facts):
                matched_rule = rule
                break

        if matched_rule is None:
            verdict = self.default_verdict
            rule_ids = ("default-allow",)
            reason = "No policy rule rejected or deferred the proposed action."
            obligations: tuple[str, ...] = ()
        else:
            verdict = PolicyVerdict(str(matched_rule["verdict"]))
            rule_ids = (str(matched_rule["rule_id"]),)
            reason = str(matched_rule.get("reason", ""))
            obligations = tuple(str(item) for item in matched_rule.get("obligations", []))

        final_action = action if verdict == PolicyVerdict.ALLOW else dict(
            SAFE_ACTION_FOR_VERDICT[verdict]
        )
        missing_facts = tuple(
            path
            for path in (
                "screen.trusted",
                "candidate.observed",
                "candidate.clickable",
                "candidate.enabled",
            )
            if action_name == "click" and not fact_value(facts, path)[0]
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        return PolicyDecision(
            verdict=verdict,
            policy_version=self.policy_version,
            rule_ids=rule_ids,
            reason=reason,
            planner_action=action,
            proposed_action=action,
            grounded_action=action,
            final_action=final_action,
            facts=json.loads(json.dumps(facts, ensure_ascii=False, sort_keys=True)),
            grounding_status="not_supplied",
            grounding_reason="",
            missing_facts=missing_facts,
            obligations=obligations,
            confirmation_id=confirmation_id,
            latency_ms=latency_ms,
        )
