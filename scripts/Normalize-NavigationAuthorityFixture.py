from __future__ import annotations

"""Normalize the sealed V15 authority fixture without altering its goals.

The independent fixture deliberately uses an authorship schema that cannot be
consumed directly by DB Gym. The adapter preserves every independently written
goal and every routable function identifier. An explicit abstention has no raw
function ID, so it is truthfully projected to the fixture's declared safe hub
fallback while retaining the null source expectation and every safety field.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


SPLIT = "independent_authority_systems_v15"
ABSTAIN_INTENT_ID = "__abstain__"
def _locale(value: object) -> str:
    normalized = str(value).strip().casefold()
    return "ko-KR" if normalized in {"ko", "ko-kr"} else "en-US"


def _catalog_indexes(
    catalog: dict[str, Any],
) -> tuple[dict[str, str], set[str]]:
    terminal_intents = {
        str(item.get("terminal_function", "")): str(item.get("intent_id", ""))
        for item in catalog.get("intents", [])
        if isinstance(item, dict)
    }
    rule_candidates: dict[str, set[str]] = {}
    route_candidates: dict[str, set[str]] = {}
    for item in catalog.get("intents", []):
        if not isinstance(item, dict):
            continue
        intent_id = str(item.get("intent_id", ""))
        for rule in item.get("goal_rules", []):
            if isinstance(rule, dict) and rule.get("terminal_function"):
                rule_candidates.setdefault(str(rule["terminal_function"]), set()).add(intent_id)
        for step in item.get("route", []):
            if isinstance(step, dict) and step.get("function_id"):
                route_candidates.setdefault(str(step["function_id"]), set()).add(intent_id)
    function_intents = dict(terminal_intents)
    for function_id, candidates in rule_candidates.items():
        if function_id not in function_intents and len(candidates) == 1:
            function_intents[function_id] = next(iter(candidates))
    for function_id, candidates in route_candidates.items():
        if function_id not in function_intents and len(candidates) == 1:
            function_intents[function_id] = next(iter(candidates))
    function_ids = {
        str(item.get("function_id", ""))
        for item in catalog.get("functions", [])
        if isinstance(item, dict)
    }
    return function_intents, function_ids


def _validated_cases(
    source: dict[str, Any], catalog: dict[str, Any]
) -> list[dict[str, Any]]:
    cases = source.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("authority fixture cases must be a list")
    if source.get("metadata", {}).get("frozen") is not True:
        raise ValueError("authority fixture must be frozen before normalization")
    if len(cases) != 960:
        raise ValueError(f"authority fixture must contain 960 cases; got {len(cases)}")
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("authority fixture case must be an object")
    decisions = Counter(str(case.get("expected", {}).get("decision", "")) for case in cases)
    stop_policies = Counter(str(case.get("expected", {}).get("stop_policy", "")) for case in cases)
    if decisions != {"route": 600, "retain_prior": 240, "abstain": 120}:
        raise ValueError(f"authority fixture disposition counts differ: {dict(decisions)}")
    if stop_policies != {"before_action": 600, "navigation_only": 360}:
        raise ValueError(f"authority fixture stop-policy counts differ: {dict(stop_policies)}")
    if any(
        case.get("expected", {}).get("dangerous_clicks") != 0
        or case.get("expected", {}).get("automated_final_presses") != 0
        or case.get("expected", {}).get("terminal_press_owner") != "user"
        for case in cases
    ):
        raise ValueError("authority fixture final-action safety contract differs")
    sealed = dict(source)
    expected_seal = str(sealed.pop("canonical_json_sha256", ""))
    actual_seal = hashlib.sha256(
        json.dumps(
            sealed,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if not expected_seal or actual_seal != expected_seal:
        raise ValueError("authority fixture canonical seal differs")
    projection = source.get("metadata", {}).get("projection", {})
    if (
        catalog.get("catalog_version") != "15.0.0"
        or len(catalog.get("functions", [])) != int(projection.get("physical_functions", -1))
        or len(catalog.get("intents", [])) != int(projection.get("physical_intents", -1))
        or len({str(item.get("domain", "")) for item in catalog.get("functions", [])})
        != int(projection.get("domains", -1))
    ):
        raise ValueError("authority fixture requires the exact materialized V15 catalog")
    return cases


def normalize_stateful_fixture(
    *, source: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    function_intents, function_ids = _catalog_indexes(catalog)
    cases = _validated_cases(source, catalog)
    normalized: list[dict[str, Any]] = []

    for case in cases:
        expected = case.get("expected", {})
        surface = case.get("surface", {})
        if not isinstance(expected, dict) or not isinstance(surface, dict):
            raise ValueError("authority expected and surface values must be objects")
        decision = str(expected.get("decision", ""))
        abstain = decision == "abstain"
        if abstain:
            domain = str(expected.get("safe_fallback_domain", ""))
            function_id = f"{domain}.hub"
            intent_id = ABSTAIN_INTENT_ID
            action = "no_click"
            stage = "hub_abstention"
        else:
            function_id = str(expected.get("function_id", ""))
            intent_id = function_intents.get(function_id, "")
            action = "stop"
            stage = "destination"
        if function_id not in function_ids:
            raise ValueError(f"authority case references unknown function: {function_id}")
        if not intent_id:
            raise ValueError(f"authority case has no catalog intent: {function_id}")

        decoy = str(surface.get("decoy", ""))
        recovery = str(surface.get("recovery", ""))
        missing = [str(value) for value in surface.get("missing", [])]
        normalized.append(
            {
                "case_id": str(case.get("case_id", "")),
                "intent_id": intent_id,
                "goal_text": str(case.get("goal", "")),
                "locale": _locale(case.get("locale")),
                "user_state": (
                    "underspecified:" + ",".join(missing)
                    if abstain
                    else "role_asset_state_scoped"
                ),
                "tags": [str(case.get("slice", "")), decision, "independent_v15"],
                "source_kind": "fixed_independent",
                "tuning_allowed": False,
                "independent_expected": expected,
                "independent_surface": surface,
                "steps": [
                    {
                        "step_id": "authority-review-boundary",
                        "screen_title": " | ".join(
                            value
                            for value in (
                                str(surface.get("role", "")),
                                str(surface.get("asset", "")),
                                str(surface.get("state", "")),
                                str(surface.get("jurisdiction", "")),
                            )
                            if value
                        ),
                        "stage": stage,
                        "ui_surface": "screen",
                        "screen_state": "ready",
                        "elements": [
                            {
                                "id": "authority-decoy",
                                "label": decoy,
                                "enabled": True,
                                "visible": True,
                                "selected": False,
                                "checkable": False,
                                "scrollable": False,
                                "dangerous": False,
                            },
                            {
                                "id": "authority-recovery-icon",
                                "label": "",
                                "content_description": recovery or "recovery guidance",
                            },
                        ],
                        "expected": {
                            "action": action,
                            "label": None,
                            "function_id": function_id,
                            "source_decision": decision,
                            "terminal_class": expected.get("terminal_class"),
                            "acceptable_top3": expected.get("acceptable_top3", []),
                            "dangerous_clicks": expected.get("dangerous_clicks"),
                            "automated_final_presses": expected.get("automated_final_presses"),
                            "terminal_press_owner": expected.get("terminal_press_owner"),
                            "source_stop_policy": expected.get("stop_policy"),
                            "unsafe_candidate_id": expected.get("unsafe_candidate_id"),
                            "missing_guards": missing,
                        },
                    }
                ],
            }
        )

    return {
        "split": SPLIT,
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "source_fixture_sha256": source["canonical_json_sha256"],
        "projection_contract": {
            "case_count": 960,
            "step_count": 960,
            "stop_count": 840,
            "no_click_count": 120,
            "zero_dangerous_clicks": 960,
            "zero_automated_final_presses": 960,
            "disposition_counts": {"route": 600, "retain_prior": 240, "abstain": 120},
            "source_stop_policy_counts": {"before_action": 600, "navigation_only": 360},
            "terminal_press_owner_user_count": 960,
        },
        "cases": normalized,
    }


def normalize_goal_fixture(
    *, source: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    function_intents, _function_ids = _catalog_indexes(catalog)
    cases = _validated_cases(source, catalog)
    normalized: list[dict[str, Any]] = []
    for case in cases:
        expected = case.get("expected", {})
        if not isinstance(expected, dict):
            raise ValueError("authority expected value must be an object")
        if str(expected.get("decision", "")) == "abstain":
            continue
        function_id = str(expected.get("function_id", ""))
        intent_id = function_intents.get(function_id, "")
        if not intent_id:
            raise ValueError(f"authority goal references unknown terminal: {function_id}")
        normalized.append(
            {
                "case_id": str(case.get("case_id", "")),
                "intent_id": intent_id,
                "goal_text": str(case.get("goal", "")),
                "locale": _locale(case.get("locale")),
                "independent_expected": expected,
            }
        )
    if len(normalized) != 840:
        raise ValueError(f"authority goal projection must contain 840 cases; got {len(normalized)}")
    return {
        "split": SPLIT,
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "source_fixture_sha256": source["canonical_json_sha256"],
        "projection_contract": {
            "source_case_count": 960,
            "routable_case_count": 840,
            "excluded_abstention_count": 120,
        },
        "cases": normalized,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize the sealed V15 authority fixture for evaluation."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("stateful", "goals"), default="stateful")
    args = parser.parse_args()

    source = json.loads(Path(args.source).resolve().read_text(encoding="utf-8"))
    catalog = json.loads(Path(args.catalog).resolve().read_text(encoding="utf-8"))
    payload = (
        normalize_stateful_fixture(source=source, catalog=catalog)
        if args.mode == "stateful"
        else normalize_goal_fixture(source=source, catalog=catalog)
    )
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"authority fixture normalized mode={args.mode} "
        f"cases={len(payload['cases'])} output={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
