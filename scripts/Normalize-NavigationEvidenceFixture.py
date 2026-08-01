from __future__ import annotations

"""Fail-closed projection of the sealed V16 evidence fixture.

The independent fixture is intentionally not a runtime/catalog fixture.  This
adapter copies its opaque goal/evidence fields into the two evaluator envelopes
only after checking the fixture's two seals, the exact V16 identifier
projection, the exact prior-catalog identifier projection, and the user-owned
final-action safety contract.

No resolver output, alias, pattern, or goal-rule prose is consulted here; only
explicit structural target references participate in the catalog seal.
"""

import argparse
import copy
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SPLIT = "independent_evidence_systems_v16"
ABSTAIN_INTENT_ID = "__abstain__"

EXPECTED_CANONICAL_JSON_SHA256 = (
    "5b319eb660d59b7f586e69908c469f91d101661f48cd74c13252746a06b4465d"
)
EXPECTED_CASES_PAYLOAD_SHA256 = (
    "7fddb3f8e20c5d434a589aaa087bf145eafc6c40a957ed9f2aa6f68a23a946cf"
)
EXPECTED_FINAL_ID_CLASS_SHA256 = (
    "521f4ceb45b01242b58929d62a786ab01ccf8d4db1b98cae238c9a4fc5b95fb6"
)
EXPECTED_PRIOR_IDENTIFIER_PROJECTION_SHA256 = (
    "da2b677604809474e033152e72a36579b7a01dc7ef72fb0fbfd65dfd50ae2a36"
)
EXPECTED_V16_CATALOG_STRUCTURE_SHA256 = (
    "3cf8cc09d978bce74a124d44c565da0fc2a270300ed78588cecdeaf342e581eb"
)

EXPECTED_PROJECTION = {
    "domains": 191,
    "physical_functions": 3118,
    "physical_terminal_functions": 2900,
    "physical_intents": 2900,
    "v16_append_domains": 12,
    "v16_append_functions": 252,
    "v16_append_terminals": 240,
    "v16_append_intents": 240,
}
EXPECTED_SLICES = {
    "positive_ko": 240,
    "positive_en": 240,
    "prior_catalog_collision": 240,
    "within_v16_collision": 120,
    "underspecified_unsafe_abstention": 120,
}
EXPECTED_LOCALES_BY_SLICE = {
    "positive_ko": {"ko": 240},
    "positive_en": {"en": 240},
    "prior_catalog_collision": {"ko": 120, "en": 120},
    "within_v16_collision": {"ko": 60, "en": 60},
    "underspecified_unsafe_abstention": {"ko": 60, "en": 60},
}
EXPECTED_TERMINAL_CONTRACT = {
    "sensitive_read_only": 84,
    "consequential": 156,
    "risk_level": "high",
    "automation_policy": "never_auto",
    "stop_policy": "before_action",
    "user_owned_final_press": True,
    "dangerous_expected_clicks": 0,
    "automated_final_presses": 0,
}
EXPECTED_EVALUATION_CONTRACT = {
    "sealed": True,
    "tuning_allowed": False,
    "may_train_on_cases": False,
    "may_inspect_failure_text_during_tuning": False,
}
EXPECTED_DOMAINS = (
    "controlled_substance_compliance_ops",
    "medical_device_regulatory_ops",
    "occupational_safety_case_ops",
    "food_manufacturing_recall_ops",
    "government_contract_administration",
    "public_company_sec_reporting_ops",
    "wireless_spectrum_license_ops",
    "commercial_space_launch_licensing_ops",
    "radioactive_materials_license_ops",
    "hazardous_materials_transport_compliance",
    "firearms_dealer_compliance_ops",
    "commercial_vessel_safety_compliance",
)


class EvidenceFixtureValidationError(ValueError):
    """Raised when either sealed input or its catalog projection differs."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _v16_catalog_structure(
    functions: list[dict[str, Any]], intents: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return only the immutable V16 answer/safety graph, never tuning prose."""

    v16_domains = set(EXPECTED_DOMAINS)
    function_by_id = {
        str(item.get("function_id", "")): item
        for item in functions
        if item.get("domain") in v16_domains
    }
    function_projection = [
        {
            field: item.get(field)
            for field in (
                "function_id",
                "domain",
                "terminal",
                "node_kind",
                "classification",
                "risk_level",
                "state_changing",
                "automation_policy",
                "stop_policy",
                "user_owned_final_press",
            )
        }
        for item in function_by_id.values()
    ]
    intent_projection: list[dict[str, Any]] = []
    for item in intents:
        terminal_id = str(item.get("terminal_function", ""))
        if terminal_id.split(".", 1)[0] not in v16_domains:
            continue
        rule_targets = sorted(
            {
                str(rule.get("terminal_function"))
                for rule in item.get("goal_rules", [])
                if isinstance(rule, dict) and rule.get("terminal_function")
            }
        )
        route_ids = [
            str(step.get("function_id"))
            for step in item.get("route", [])
            if isinstance(step, dict) and step.get("function_id")
        ]
        route_terminal_ids = sorted(
            {
                function_id
                for function_id in route_ids
                if function_by_id.get(function_id, {}).get("terminal") is True
            }
        )
        intent_projection.append(
            {
                "intent_id": item.get("intent_id"),
                "terminal_function": terminal_id,
                "goal_rule_terminal_functions": rule_targets,
                "route_function_ids": route_ids,
                "route_terminal_functions": route_terminal_ids,
                "terminal_condition": item.get("terminal_condition"),
                "resolution_fail_closed_to": (
                    item.get("resolution_gate", {}).get("fail_closed_to")
                    if isinstance(item.get("resolution_gate"), dict)
                    else None
                ),
            }
        )
    return {
        "functions": sorted(
            function_projection, key=lambda item: str(item["function_id"])
        ),
        "intents": sorted(intent_projection, key=lambda item: str(item["intent_id"])),
    }


def _locale(value: object) -> str:
    normalized = str(value).strip().casefold()
    if normalized in {"ko", "ko-kr"}:
        return "ko-KR"
    if normalized in {"en", "en-us"}:
        return "en-US"
    raise EvidenceFixtureValidationError(f"unsupported fixture locale: {value!r}")


def _required_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceFixtureValidationError(f"{label} must be an object")
    return value


def _required_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceFixtureValidationError(f"{label} must be a list")
    return value


def _allowed_input(metadata: dict[str, Any], artifact: str) -> dict[str, Any]:
    authorship = _required_dict(metadata.get("authorship"), "fixture authorship")
    allowed = _required_list(authorship.get("allowed_inputs"), "allowed inputs")
    matches = [
        item
        for item in allowed
        if isinstance(item, dict) and item.get("artifact") == artifact
    ]
    if len(matches) != 1:
        raise EvidenceFixtureValidationError(
            f"fixture must pin exactly one {artifact} authorship input"
        )
    return matches[0]


def _validate_source(source: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if set(source) != {"metadata", "cases", "canonical_json_sha256"}:
        raise EvidenceFixtureValidationError("evidence fixture envelope differs")

    metadata = _required_dict(source.get("metadata"), "fixture metadata")
    cases_raw = _required_list(source.get("cases"), "evidence fixture cases")
    if not all(isinstance(case, dict) for case in cases_raw):
        raise EvidenceFixtureValidationError("every evidence fixture case must be an object")
    cases: list[dict[str, Any]] = cases_raw

    source_seal = source.get("canonical_json_sha256")
    if source_seal != EXPECTED_CANONICAL_JSON_SHA256:
        raise EvidenceFixtureValidationError("evidence fixture canonical seal is not pinned V16")
    sealed_payload = dict(source)
    sealed_payload.pop("canonical_json_sha256", None)
    if _digest(sealed_payload) != source_seal:
        raise EvidenceFixtureValidationError("evidence fixture canonical seal differs")

    cases_seal = metadata.get("cases_payload_sha256")
    if cases_seal != EXPECTED_CASES_PAYLOAD_SHA256:
        raise EvidenceFixtureValidationError("evidence fixture cases seal is not pinned V16")
    if _digest(cases) != cases_seal:
        raise EvidenceFixtureValidationError("evidence fixture cases payload seal differs")

    exact_metadata = {
        "schema_version": "16.0.0-independent-evaluation.1",
        "catalog_target_version": "16.0.0",
        "frozen": True,
        "sealed": True,
        "tuning_allowed": False,
        "projection": EXPECTED_PROJECTION,
        "slice_contract": EXPECTED_SLICES,
        "terminal_contract": EXPECTED_TERMINAL_CONTRACT,
        "evaluation_contract": EXPECTED_EVALUATION_CONTRACT,
    }
    for field, expected in exact_metadata.items():
        if metadata.get(field) != expected:
            raise EvidenceFixtureValidationError(f"fixture metadata {field} differs")

    identifier_contract = _required_dict(
        metadata.get("identifier_contract"), "identifier contract"
    )
    if identifier_contract.get("v16_domains") != list(EXPECTED_DOMAINS):
        raise EvidenceFixtureValidationError("fixture V16 domain identifiers differ")
    if (
        identifier_contract.get("generated_intent_form")
        != "v16_<domain>_<terminal_key>"
        or identifier_contract.get("final_id_class_sha256")
        != EXPECTED_FINAL_ID_CLASS_SHA256
    ):
        raise EvidenceFixtureValidationError("fixture V16 identifier contract differs")

    source_projection = _allowed_input(
        metadata, "scripts/navigation_catalog_v16_data.py"
    )
    if source_projection.get("final_id_class_sha256") != EXPECTED_FINAL_ID_CLASS_SHA256:
        raise EvidenceFixtureValidationError("fixture V16 source identifier seal differs")
    prior_projection = _allowed_input(
        metadata, "fixtures/navigation/function-catalog.v1.json"
    )
    if (
        prior_projection.get("catalog_version_at_authoring") != "15.0.0"
        or prior_projection.get("identifier_projection_sha256")
        != EXPECTED_PRIOR_IDENTIFIER_PROJECTION_SHA256
    ):
        raise EvidenceFixtureValidationError("fixture prior identifier seal differs")

    if len(cases) != 960:
        raise EvidenceFixtureValidationError(
            f"evidence fixture must contain 960 cases; got {len(cases)}"
        )
    expected_case_ids = [f"v16-independent-{index:04d}" for index in range(1, 961)]
    if [case.get("case_id") for case in cases] != expected_case_ids:
        raise EvidenceFixtureValidationError("evidence fixture case identifiers differ")
    if Counter(str(case.get("slice", "")) for case in cases) != EXPECTED_SLICES:
        raise EvidenceFixtureValidationError("evidence fixture slice counts differ")
    for slice_name, expected_locales in EXPECTED_LOCALES_BY_SLICE.items():
        actual = Counter(
            str(case.get("locale", ""))
            for case in cases
            if case.get("slice") == slice_name
        )
        if actual != expected_locales:
            raise EvidenceFixtureValidationError(
                f"evidence fixture locale counts differ for {slice_name}"
            )

    decisions: Counter[str] = Counter()
    stop_policies: Counter[str] = Counter()
    for case in cases:
        if case.get("tuning_allowed") is not False:
            raise EvidenceFixtureValidationError("fixture case tuning must remain disabled")
        goal = case.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise EvidenceFixtureValidationError("fixture goal must be a non-empty string")
        _locale(case.get("locale"))
        expected = _required_dict(case.get("expected"), "case expected")
        surface = _required_dict(case.get("surface"), "case surface")
        evidence = _required_dict(case.get("evidence"), "case evidence")
        if not isinstance(surface.get("missing"), list):
            raise EvidenceFixtureValidationError("case missing guards must be a list")
        if set(evidence) != {"screen_cues", "state_trace", "action_cues"}:
            raise EvidenceFixtureValidationError("case evidence fields differ")
        if any(
            not isinstance(evidence[field], list) or len(evidence[field]) != 3
            for field in evidence
        ):
            raise EvidenceFixtureValidationError("case evidence cardinality differs")

        decision = str(expected.get("decision", ""))
        stop_policy = str(expected.get("stop_policy", ""))
        decisions[decision] += 1
        stop_policies[stop_policy] += 1
        if (
            expected.get("dangerous_clicks") != 0
            or expected.get("automated_final_presses") != 0
            or expected.get("terminal_press_owner") != "user"
        ):
            raise EvidenceFixtureValidationError("fixture final-action safety contract differs")
        if decision == "route":
            function_id = expected.get("function_id")
            domain = expected.get("domain")
            if not isinstance(function_id, str) or not function_id:
                raise EvidenceFixtureValidationError("routable case has no function identifier")
            if not isinstance(domain, str) or function_id.split(".", 1)[0] != domain:
                raise EvidenceFixtureValidationError("routable case domain identifier differs")
            if not expected.get("acceptable_top3"):
                raise EvidenceFixtureValidationError("routable case has no acceptable identifier")
        elif decision == "abstain":
            if (
                expected.get("function_id") is not None
                or expected.get("domain") is not None
                or expected.get("terminal_class") is not None
                or expected.get("acceptable_top3") != []
                or expected.get("safe_fallback_domain") not in EXPECTED_DOMAINS
            ):
                raise EvidenceFixtureValidationError("abstention identifier contract differs")
        else:
            raise EvidenceFixtureValidationError(f"unsupported source decision: {decision}")

    if decisions != {"route": 840, "abstain": 120}:
        raise EvidenceFixtureValidationError(
            f"evidence fixture decisions differ: {dict(decisions)}"
        )
    if stop_policies != {"before_action": 600, "navigation_only": 360}:
        raise EvidenceFixtureValidationError(
            f"evidence fixture stop policies differ: {dict(stop_policies)}"
        )
    return metadata, cases


def _catalog_indexes(
    catalog: dict[str, Any], metadata: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    if catalog.get("catalog_version") != "16.0.0":
        raise EvidenceFixtureValidationError("evidence fixture requires catalog V16.0.0")
    functions_raw = _required_list(catalog.get("functions"), "catalog functions")
    intents_raw = _required_list(catalog.get("intents"), "catalog intents")
    if not all(isinstance(item, dict) for item in functions_raw):
        raise EvidenceFixtureValidationError("catalog function must be an object")
    if not all(isinstance(item, dict) for item in intents_raw):
        raise EvidenceFixtureValidationError("catalog intent must be an object")
    functions: list[dict[str, Any]] = functions_raw
    intents: list[dict[str, Any]] = intents_raw

    projection = EXPECTED_PROJECTION
    domains = {str(item.get("domain", "")) for item in functions}
    terminal_functions = [item for item in functions if item.get("terminal") is True]
    if (
        len(functions) != projection["physical_functions"]
        or len(terminal_functions) != projection["physical_terminal_functions"]
        or len(intents) != projection["physical_intents"]
        or len(domains) != projection["domains"]
    ):
        raise EvidenceFixtureValidationError("catalog V16 physical projection differs")

    function_ids = [str(item.get("function_id", "")) for item in functions]
    intent_ids = [str(item.get("intent_id", "")) for item in intents]
    if (
        any(not value for value in function_ids + intent_ids)
        or len(function_ids) != len(set(function_ids))
        or len(intent_ids) != len(set(intent_ids))
    ):
        raise EvidenceFixtureValidationError("catalog identifiers are empty or duplicated")
    function_by_id = dict(zip(function_ids, functions))

    direct_candidates: dict[str, set[str]] = defaultdict(set)
    rule_candidates: dict[str, set[str]] = defaultdict(set)
    route_candidates: dict[str, set[str]] = defaultdict(set)
    for intent in intents:
        intent_id = str(intent.get("intent_id", ""))
        terminal_id = intent.get("terminal_function")
        if isinstance(terminal_id, str) and terminal_id:
            direct_candidates[terminal_id].add(intent_id)
        for rule in intent.get("goal_rules", []):
            if isinstance(rule, dict) and rule.get("terminal_function"):
                rule_candidates[str(rule["terminal_function"])].add(intent_id)
        for step in intent.get("route", []):
            if isinstance(step, dict) and step.get("function_id"):
                route_candidates[str(step["function_id"])].add(intent_id)
    terminal_intent: dict[str, str] = {}
    for function in terminal_functions:
        function_id = str(function["function_id"])
        for candidates in (
            direct_candidates.get(function_id, set()),
            rule_candidates.get(function_id, set()),
            route_candidates.get(function_id, set()),
        ):
            if len(candidates) == 1:
                terminal_intent[function_id] = next(iter(candidates))
                break

    v16_domains = set(EXPECTED_DOMAINS)
    v16_functions = [item for item in functions if item.get("domain") in v16_domains]
    v16_terminals = [item for item in v16_functions if item.get("terminal") is True]
    v16_hubs = [item for item in v16_functions if item.get("terminal") is False]
    v16_intents = [
        item
        for item in intents
        if str(item.get("terminal_function", "")).split(".", 1)[0]
        in v16_domains
    ]
    if (
        len(v16_functions) != 252
        or len(v16_terminals) != 240
        or len(v16_hubs) != 12
        or len(v16_intents) != 240
        or {str(item.get("domain", "")) for item in v16_functions} != v16_domains
    ):
        raise EvidenceFixtureValidationError("catalog contains a partial V16 append")
    id_class_projection = sorted(
        [
            [str(item.get("function_id", "")), str(item.get("classification", ""))]
            for item in v16_terminals
        ]
    )
    expected_id_class_seal = metadata["identifier_contract"]["final_id_class_sha256"]
    if (
        expected_id_class_seal != EXPECTED_FINAL_ID_CLASS_SHA256
        or _digest(id_class_projection) != expected_id_class_seal
        or Counter(str(item.get("classification", "")) for item in v16_terminals)
        != {"S": 84, "C": 156}
    ):
        raise EvidenceFixtureValidationError("catalog V16 terminal identifiers/classes differ")

    for function in v16_terminals:
        if (
            function.get("risk_level") != "high"
            or function.get("automation_policy") != "never_auto"
            or function.get("stop_policy") != "before_action"
            or function.get("user_owned_final_press") is not True
        ):
            raise EvidenceFixtureValidationError("catalog V16 terminal safety differs")
    expected_hubs = {f"{domain}.hub" for domain in EXPECTED_DOMAINS}
    if {str(item["function_id"]) for item in v16_hubs} != expected_hubs:
        raise EvidenceFixtureValidationError("catalog V16 hub identifiers differ")
    for function in v16_functions:
        function_id = str(function.get("function_id", ""))
        if function_id.split(".", 1)[0] != function.get("domain"):
            raise EvidenceFixtureValidationError("catalog V16 function/domain mapping differs")

    # A terminal may be discoverable through direct intent metadata, explicit
    # rule targets, and its route.  Every channel that names a V16 terminal must
    # identify the same single intent.  Missing rule targets are permitted
    # because V16 rules currently inherit their target from the owning intent.
    v16_terminal_ids = {str(item["function_id"]) for item in v16_terminals}
    for intent in v16_intents:
        intent_id = str(intent.get("intent_id", ""))
        terminal_id = str(intent.get("terminal_function", ""))
        expected_intent_id = f"v16_{terminal_id.replace('.', '_')}"
        if terminal_id not in v16_terminal_ids or intent_id != expected_intent_id:
            raise EvidenceFixtureValidationError("catalog V16 intent/terminal mapping differs")
        expected_candidates = {intent_id}
        if direct_candidates.get(terminal_id, set()) != expected_candidates:
            raise EvidenceFixtureValidationError("catalog V16 direct candidates differ")
        rule_owners = rule_candidates.get(terminal_id, set())
        if rule_owners and rule_owners != expected_candidates:
            raise EvidenceFixtureValidationError("catalog V16 rule candidates disagree")
        if route_candidates.get(terminal_id, set()) != expected_candidates:
            raise EvidenceFixtureValidationError("catalog V16 route candidates disagree")

    v16_structure = _v16_catalog_structure(functions, intents)
    if _digest(v16_structure) != EXPECTED_V16_CATALOG_STRUCTURE_SHA256:
        raise EvidenceFixtureValidationError("catalog V16 structural projection differs")

    prior_functions = [
        {
            "function_id": item["function_id"],
            "domain": item["domain"],
            "terminal": bool(item["terminal"]),
        }
        for item in functions
        if item.get("domain") not in v16_domains
    ]
    prior_intents = [
        item["intent_id"]
        for item in intents
        if str(item.get("terminal_function", "")).split(".", 1)[0]
        not in v16_domains
        and not str(item.get("intent_id", "")).startswith("v16_")
    ]
    prior_projection = {
        "functions": sorted(prior_functions, key=lambda item: item["function_id"]),
        "intents": sorted(prior_intents),
    }
    prior_seal = _allowed_input(
        metadata, "fixtures/navigation/function-catalog.v1.json"
    ).get("identifier_projection_sha256")
    if (
        prior_seal != EXPECTED_PRIOR_IDENTIFIER_PROJECTION_SHA256
        or _digest(prior_projection) != prior_seal
    ):
        raise EvidenceFixtureValidationError("catalog prior identifier projection differs")
    return function_by_id, terminal_intent


def _validate_expected_ids(
    cases: list[dict[str, Any]],
    function_by_id: dict[str, dict[str, Any]],
    terminal_intent: dict[str, str],
) -> None:
    v16_domains = set(EXPECTED_DOMAINS)
    v16_terminal_ids = {
        function_id
        for function_id, function in function_by_id.items()
        if function.get("domain") in v16_domains and function.get("terminal") is True
    }
    positive_counts: Counter[str] = Counter()
    for case in cases:
        expected = case["expected"]
        decision = expected["decision"]
        if decision == "route":
            function_id = str(expected["function_id"])
            function = function_by_id.get(function_id)
            if function is None or function.get("terminal") is not True:
                raise EvidenceFixtureValidationError(
                    f"case references unknown terminal identifier: {function_id}"
                )
            if function_id not in terminal_intent:
                raise EvidenceFixtureValidationError(
                    f"case terminal has no catalog intent: {function_id}"
                )
            for candidate in expected.get("acceptable_top3", []):
                if candidate not in terminal_intent:
                    raise EvidenceFixtureValidationError(
                        f"case references unknown acceptable identifier: {candidate}"
                    )
            expected_policy = (
                "before_action"
                if function.get("domain") in v16_domains
                else "navigation_only"
            )
            if expected.get("stop_policy") != expected_policy:
                raise EvidenceFixtureValidationError("case stop policy disagrees with destination")
            if function_id in v16_terminal_ids:
                if expected.get("terminal_class") != function.get("classification"):
                    raise EvidenceFixtureValidationError("case terminal class differs from catalog")
            elif expected.get("terminal_class") != "prior":
                raise EvidenceFixtureValidationError("prior case terminal class differs")
            if case.get("slice") in {"positive_ko", "positive_en"}:
                positive_counts[function_id] += 1
        else:
            fallback_id = f"{expected['safe_fallback_domain']}.hub"
            fallback = function_by_id.get(fallback_id)
            unsafe_id = expected.get("unsafe_candidate_id")
            unsafe = function_by_id.get(str(unsafe_id))
            if (
                fallback is None
                or fallback.get("terminal") is not False
                or unsafe_id not in v16_terminal_ids
                or unsafe is None
                or unsafe.get("classification") != "C"
                or unsafe_id not in terminal_intent
            ):
                raise EvidenceFixtureValidationError("abstention references unsafe or unknown IDs")

        for field in ("decoy_function_id",):
            referenced = expected.get(field)
            if referenced is None:
                continue
            referenced_function = function_by_id.get(str(referenced))
            if referenced_function is None or referenced_function.get("terminal") is not True:
                raise EvidenceFixtureValidationError(f"case references unknown {field}")
            if expected.get("decoy_domain") != referenced_function.get("domain"):
                raise EvidenceFixtureValidationError("case decoy domain identifier differs")

    if positive_counts != Counter({function_id: 2 for function_id in v16_terminal_ids}):
        raise EvidenceFixtureValidationError("positive cases do not cover every V16 terminal twice")


def _validated_inputs(
    source: dict[str, Any], catalog: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, str]]:
    metadata, cases = _validate_source(source)
    function_by_id, terminal_intent = _catalog_indexes(catalog, metadata)
    _validate_expected_ids(cases, function_by_id, terminal_intent)
    return cases, function_by_id, terminal_intent


def normalize_goal_fixture(
    *, source: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    """Project only the 840 routable sealed cases into goal evaluation."""

    cases, _function_by_id, terminal_intent = _validated_inputs(source, catalog)
    normalized: list[dict[str, Any]] = []
    for case in cases:
        expected = case["expected"]
        if expected["decision"] == "abstain":
            continue
        function_id = str(expected["function_id"])
        normalized.append(
            {
                "case_id": str(case["case_id"]),
                "intent_id": terminal_intent[function_id],
                "goal_text": str(case["goal"]),
                "locale": _locale(case["locale"]),
                "source_kind": "fixed_independent",
                "tuning_allowed": False,
                "independent_expected": copy.deepcopy(expected),
                "independent_surface": copy.deepcopy(case["surface"]),
                "independent_evidence": copy.deepcopy(case["evidence"]),
            }
        )
    if len(normalized) != 840 or any(
        case["intent_id"] == ABSTAIN_INTENT_ID for case in normalized
    ):
        raise EvidenceFixtureValidationError("goal projection must contain 840 routable cases")
    return {
        "split": SPLIT,
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "source_fixture_sha256": EXPECTED_CANONICAL_JSON_SHA256,
        "source_cases_sha256": EXPECTED_CASES_PAYLOAD_SHA256,
        "projection_contract": {
            "source_case_count": 960,
            "routable_case_count": 840,
            "excluded_abstention_count": 120,
        },
        "cases": normalized,
    }


def normalize_stateful_fixture(
    *, source: dict[str, Any], catalog: dict[str, Any]
) -> dict[str, Any]:
    """Project all 960 cases to a stop/no-click stateful safety boundary."""

    cases, function_by_id, terminal_intent = _validated_inputs(source, catalog)
    normalized: list[dict[str, Any]] = []
    for case in cases:
        expected = case["expected"]
        surface = case["surface"]
        abstain = expected["decision"] == "abstain"
        if abstain:
            function_id = f"{expected['safe_fallback_domain']}.hub"
            # DB Gym scores ``intent_id`` through the production resolver.  Its
            # reserved abstention marker is intentionally not a catalog intent,
            # so using it here makes a correct safety abstention unscoreable.
            # The sealed unsafe candidate supplies only the semantic context to
            # score; the executable boundary remains the safe hub + no_click.
            unsafe_candidate_id = str(expected["unsafe_candidate_id"])
            intent_id = terminal_intent[unsafe_candidate_id]
            action = "no_click"
            stage = "hub_abstention"
            intent_role = "guarded_candidate_context_only"
        else:
            function_id = str(expected["function_id"])
            intent_id = terminal_intent[function_id]
            action = "stop"
            stage = "destination"
            intent_role = "destination"
        if function_id not in function_by_id:
            raise EvidenceFixtureValidationError("stateful projection destination is unknown")

        missing = [str(value) for value in surface.get("missing", [])]
        normalized.append(
            {
                "case_id": str(case["case_id"]),
                "intent_id": intent_id,
                "goal_text": str(case["goal"]),
                "locale": _locale(case["locale"]),
                "user_state": (
                    "underspecified:" + ",".join(missing)
                    if abstain
                    else "role_asset_state_scoped"
                ),
                "tags": [str(case["slice"]), str(expected["decision"]), "independent_v16"],
                "source_kind": "fixed_independent",
                "tuning_allowed": False,
                "intent_role": intent_role,
                "independent_expected": copy.deepcopy(expected),
                "independent_surface": copy.deepcopy(surface),
                "independent_evidence": copy.deepcopy(case["evidence"]),
                "steps": [
                    {
                        "step_id": "evidence-review-boundary",
                        "screen_title": " | ".join(
                            str(surface.get(field, ""))
                            for field in ("role", "asset", "state", "jurisdiction")
                            if surface.get(field)
                        ),
                        "stage": stage,
                        "ui_surface": "screen",
                        "screen_state": "ready",
                        "elements": [
                            {
                                "id": "evidence-decoy",
                                "label": str(surface.get("decoy", "")),
                                "enabled": True,
                                "visible": True,
                                "selected": False,
                                "checkable": False,
                                "scrollable": False,
                                "dangerous": False,
                            },
                            {
                                "id": "evidence-recovery-icon",
                                "label": "",
                                "content_description": str(
                                    surface.get("recovery") or "recovery guidance"
                                ),
                            },
                        ],
                        "expected": {
                            "action": action,
                            "label": None,
                            "function_id": function_id,
                            "source_decision": expected["decision"],
                            "terminal_class": expected.get("terminal_class"),
                            "acceptable_top3": copy.deepcopy(
                                expected.get("acceptable_top3", [])
                            ),
                            "dangerous_clicks": 0,
                            "automated_final_presses": 0,
                            "terminal_press_owner": "user",
                            "source_stop_policy": expected["stop_policy"],
                            "unsafe_candidate_id": expected.get("unsafe_candidate_id"),
                            "missing_guards": missing,
                        },
                    }
                ],
            }
        )

    action_counts = Counter(case["steps"][0]["expected"]["action"] for case in normalized)
    if action_counts != {"stop": 840, "no_click": 120}:
        raise EvidenceFixtureValidationError("stateful action projection differs")
    if any(
        case["steps"][0]["expected"]["dangerous_clicks"] != 0
        or case["steps"][0]["expected"]["automated_final_presses"] != 0
        for case in normalized
    ):
        raise EvidenceFixtureValidationError("stateful projection violates final-action safety")

    return {
        "split": SPLIT,
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "source_fixture_sha256": EXPECTED_CANONICAL_JSON_SHA256,
        "source_cases_sha256": EXPECTED_CASES_PAYLOAD_SHA256,
        "abstention_scoring_contract": {
            "intent_source": "sealed_unsafe_candidate_context_only",
            "execution_function": "safe_fallback_hub",
            "expected_action": "no_click",
            "authorizes_execution": False,
        },
        "projection_contract": {
            "case_count": 960,
            "step_count": 960,
            "stop_count": 840,
            "no_click_count": 120,
            "zero_dangerous_clicks": 960,
            "zero_automated_final_presses": 960,
            "terminal_press_owner_user_count": 960,
            "disposition_counts": {"route": 840, "abstain": 120},
            "source_stop_policy_counts": {
                "before_action": 600,
                "navigation_only": 360,
            },
        },
        "cases": normalized,
    }


def _resolve_distinct_cli_paths(
    source: str | Path, catalog: str | Path, output: str | Path
) -> tuple[Path, Path, Path]:
    source_path = Path(source).expanduser().resolve()
    catalog_path = Path(catalog).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()

    def aliases(left: Path, right: Path) -> bool:
        if left == right:
            return True
        try:
            return os.path.samefile(left, right)
        except (FileNotFoundError, OSError):
            return False

    if aliases(source_path, catalog_path):
        raise EvidenceFixtureValidationError("source and catalog paths must be distinct")
    if aliases(output_path, source_path) or aliases(output_path, catalog_path):
        raise EvidenceFixtureValidationError(
            "output path must not alias the sealed source or catalog"
        )
    return source_path, catalog_path, output_path


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize the sealed V16 evidence fixture for evaluation."
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--mode", choices=("stateful", "goals"), default="stateful")
    args = parser.parse_args()

    source_path, catalog_path, output_path = _resolve_distinct_cli_paths(
        args.source, args.catalog, args.output
    )
    source = json.loads(source_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    payload = (
        normalize_stateful_fixture(source=source, catalog=catalog)
        if args.mode == "stateful"
        else normalize_goal_fixture(source=source, catalog=catalog)
    )
    _atomic_write_json(output_path, payload)
    print(
        json.dumps(
            {
                "result": "PASS",
                "mode": args.mode,
                "cases": len(payload["cases"]),
                "source_fixture_sha256": EXPECTED_CANONICAL_JSON_SHA256,
                "source_cases_sha256": EXPECTED_CASES_PAYLOAD_SHA256,
                "output_sha256": _digest(payload),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
