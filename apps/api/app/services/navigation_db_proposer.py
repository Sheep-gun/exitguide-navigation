from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings
from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.provider_errors import compact_text, response_error_detail


ALLOWED_ACTIONS = {
    "add_alias",
    "add_context_guard",
    "add_intent_pattern",
    "add_goal_rule",
    "add_route_function",
    "add_terminal_cue_guard",
    "add_regression_case",
    "tighten_automation_policy",
}


def propose_with_exaone(
    *,
    report: dict[str, Any],
    catalog: NavigationFunctionCatalog,
    settings: Settings,
    max_failures: int = 40,
) -> dict[str, Any]:
    """Ask K-EXAONE for reviewable hard-case hypotheses, never labels.

    The benchmark's expected actions remain the only ground truth. Model output
    is schema-validated, restricted to known function IDs, and always marked
    ``auto_apply=false`` so it cannot silently modify the function catalog.
    """

    if not settings.exaone_api_key or not settings.exaone_model:
        raise RuntimeError("K-EXAONE API configuration is unavailable")
    failures = [
        item
        for item in report.get("failures", [])
        if bool(item.get("tuning_allowed", True))
    ][: max(1, min(max_failures, 100))]
    known_case_ids = {str(item.get("case_id", "")) for item in failures}
    tool = {
        "type": "function",
        "function": {
            "name": "propose_navigation_db_changes",
            "description": "Propose hypotheses for human review. Do not determine benchmark truth or execute changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "maxItems": 30,
                        "items": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string", "enum": sorted(ALLOWED_ACTIONS)},
                                "function_id": {"type": "string"},
                                "value": {"type": "string"},
                                "rationale": {"type": "string"},
                                "evidence_case_ids": {"type": "array", "items": {"type": "string"}},
                                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            },
                            "required": [
                                "action",
                                "function_id",
                                "value",
                                "rationale",
                                "evidence_case_ids",
                                "confidence",
                            ],
                        },
                    }
                },
                "required": ["suggestions"],
            },
        },
    }
    prompt = json.dumps(
        {
            "catalog_version": catalog.version,
            "failure_counts": report.get("failure_counts", {}),
            "failures": failures,
            "deterministic_suggestions": report.get("suggestions", []),
            "rules": [
                "Treat expected benchmark fields as immutable evidence.",
                "Prefer cross-app aliases, context guards, and goal rules over app-specific coordinates.",
                "Never propose automatic execution of a state-changing control.",
                "Every proposal must cite at least one supplied case ID.",
            ],
        },
        ensure_ascii=False,
    )
    payload = {
        "model": settings.exaone_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a Navigation DB error-analysis assistant. You may propose reviewable hypotheses only. "
                    "You are not a truth oracle, may not rewrite expected results, and may not auto-apply changes."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "tools": [tool],
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "temperature": 0.1,
        "top_p": 0.9,
        "max_tokens": 1800,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {
        "Authorization": f"Bearer {settings.exaone_api_key}",
        "Content-Type": "application/json",
    }
    if settings.exaone_team:
        headers["X-Friendli-Team"] = settings.exaone_team
    try:
        response = httpx.post(
            f"{settings.exaone_base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json=payload,
            timeout=settings.exaone_timeout_seconds,
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
        arguments = _tool_arguments(message)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"K-EXAONE HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"K-EXAONE connection failed: {compact_text(str(exc))}") from exc
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"K-EXAONE returned invalid proposal data: {compact_text(str(exc))}") from exc

    validated: list[dict[str, Any]] = []
    for raw in list(arguments.get("suggestions", []))[:30]:
        action = str(raw.get("action", ""))
        function_id = str(raw.get("function_id", ""))
        evidence = [
            str(case_id)
            for case_id in raw.get("evidence_case_ids", [])
            if str(case_id) in known_case_ids
        ]
        if action not in ALLOWED_ACTIONS or catalog.function(function_id) is None or not evidence:
            continue
        validated.append(
            {
                "action": action,
                "function_id": function_id,
                "value": str(raw.get("value", ""))[:300],
                "rationale": str(raw.get("rationale", ""))[:600],
                "evidence_case_ids": sorted(set(evidence)),
                "confidence": round(max(0.0, min(1.0, float(raw.get("confidence", 0.0)))), 4),
                "auto_apply": False,
                "review_required": True,
                "source": "k_exaone_hard_case_hypothesis",
            }
        )
    return {
        "schema_version": 1,
        "provider": "k_exaone",
        "catalog_version": catalog.version,
        "ground_truth_source": "benchmark_expected_fields_only",
        "review_required": True,
        "auto_apply": False,
        "suggestions": validated,
    }


def _tool_arguments(message: dict[str, Any]) -> dict[str, Any]:
    calls = message.get("tool_calls") or []
    if not calls:
        raise ValueError("tool call is missing")
    function = calls[0].get("function") or {}
    if function.get("name") != "propose_navigation_db_changes":
        raise ValueError("unexpected tool name")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    return arguments
