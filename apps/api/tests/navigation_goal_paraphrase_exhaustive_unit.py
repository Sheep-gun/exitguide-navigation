from __future__ import annotations

import hashlib
import json
import statistics
from copy import deepcopy
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.services.navigation_function_catalog import (
    NEVER_AUTO_STOP_POLICIES,
    NavigationFunctionCatalog,
    _normalize,
)
from app.services.navigation_goal_paraphrase_development import (
    evaluate_catalog_derived_paraphrases,
    generate_catalog_derived_paraphrase_cases,
    validate_paraphrase_development_policy,
)


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
EQUIVALENCE_PATH = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"
POLICY_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-paraphrase-exhaustive-v1.json"
)


def main() -> None:
    catalog_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    equivalence_payload = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    policy_payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    validate_paraphrase_development_policy(policy_payload)
    _assert_policy_corruptions_fail(policy_payload)
    expected = policy_payload["catalog_expectations"]
    assert isinstance(expected, dict)
    assert hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest() == expected["catalog_sha256"]
    assert hashlib.sha256(EQUIVALENCE_PATH.read_bytes()).hexdigest() == expected["equivalence_sha256"]
    assert equivalence_payload["equivalence_version"] == expected["equivalence_version"]

    generation_started = perf_counter()
    cases = generate_catalog_derived_paraphrase_cases(
        catalog_payload=catalog_payload,
        equivalence_payload=equivalence_payload,
        policy_payload=policy_payload,
    )
    generation_seconds = perf_counter() - generation_started
    assert generation_seconds < 30.0
    repeated_cases = generate_catalog_derived_paraphrase_cases(
        catalog_payload=catalog_payload,
        equivalence_payload=equivalence_payload,
        policy_payload=policy_payload,
    )
    assert repeated_cases == cases

    exact_intents = int(expected["exact_intents"])
    exact_cases = int(expected["exact_cases"])
    exact_families = len(policy_payload["family_order"])
    functions = {item["function_id"]: item for item in catalog_payload["functions"]}
    intents = {item["intent_id"]: item for item in catalog_payload["intents"]}
    assert len(cases) == exact_cases == 5320
    assert len(intents) == exact_intents == 2660
    assert len({case.case_id for case in cases}) == exact_cases
    assert len({_normalize(case.goal_text) for case in cases}) == exact_cases
    assert Counter(case.locale for case in cases) == {
        "ko": int(expected["cases_per_locale"]),
        "en": int(expected["cases_per_locale"]),
    }
    assert Counter(case.family for case in cases) == {
        family: int(expected["cases_per_family"])
        for family in policy_payload["family_order"]
    }
    assert len({case.family for case in cases}) == exact_families == 8
    assert Counter(case.intent_id for case in cases) == {
        intent_id: 2 for intent_id in intents
    }
    assert all(
        {case.locale for case in cases if case.intent_id == intent_id} == {"ko", "en"}
        for intent_id in intents
    )

    terminal_domain_counts = Counter(
        functions[intent["terminal_function"]]["domain"]
        for intent in catalog_payload["intents"]
    )
    case_domain_counts = Counter(case.domain for case in cases)
    assert len(terminal_domain_counts) == int(expected["exact_domains"])
    assert case_domain_counts == Counter(
        {domain: count * 2 for domain, count in terminal_domain_counts.items()}
    )
    intent_generation_counts = Counter(_generation(intent_id) for intent_id in intents)
    assert Counter(case.generation for case in cases) == Counter(
        {generation: count * 2 for generation, count in intent_generation_counts.items()}
    )

    global_source_phrases = {
        _normalize(str(value))
        for intent in catalog_payload["intents"]
        for value in intent.get("patterns", [])
        if _normalize(str(value))
    }
    global_source_phrases.update(
        _normalize(str(value))
        for intent in catalog_payload["intents"]
        for values in intent.get("patterns_by_locale", {}).values()
        for value in values
        if _normalize(str(value))
    )
    global_source_phrases.update(
        _normalize(str(value))
        for function in catalog_payload["functions"]
        for values in function.get("aliases", {}).values()
        for value in values
        if _normalize(str(value))
    )
    maximum_fraction = float(policy_payload["anti_copy_policy"]["maximum_source_phrase_fraction"])
    minimum_length = int(policy_payload["anti_copy_policy"]["minimum_normalized_phrase_length"])
    for case in cases:
        intent = intents[case.intent_id]
        definition = functions[case.raw_terminal_function]
        assert intent["terminal_function"] == case.raw_terminal_function
        assert case.risk_level == definition["risk_level"]
        assert case.state_changing is definition["state_changing"]
        assert case.automation_policy == definition["automation_policy"]
        assert case.stop_policy == definition["stop_policy"]
        normalized_goal = _normalize(case.goal_text)
        assert normalized_goal not in global_source_phrases
        all_local_sources = _all_normalized_source_phrases(intent, definition)
        protected = frozenset(
            value for value in all_local_sources if len(value) >= minimum_length
        )
        assert not any(source in normalized_goal for source in protected)
        assert _normalize(case.action) not in global_source_phrases
        assert case.maximum_source_phrase_fraction <= maximum_fraction
        expected_short_overlap_count = sum(
            1
            for value in all_local_sources
            if 0 < len(value) < minimum_length and value in normalized_goal
        )
        assert case.short_source_overlap_count == expected_short_overlap_count
        expected_rule_overlap_count = sum(
            1
            for value in _normalized_goal_rule_terms(intent)
            if len(value) >= minimum_length and value in _normalize(case.action)
        )
        assert case.goal_rule_action_overlap_count == expected_rule_overlap_count
        dimensions = (case.role, case.asset, case.state, case.action, case.outcome)
        assert all(value in case.goal_text for value in dimensions)
        assert len({_normalize(value) for value in dimensions}) == len(dimensions)
        assert all("review reference" not in value and "검토 분류 부호" not in value for value in dimensions)

    with TemporaryDirectory() as temporary_directory:
        construction_started = perf_counter()
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "paraphrase-exhaustive.sqlite",
            CATALOG_PATH,
        )
        construction_seconds = perf_counter() - construction_started
        assert construction_seconds < 60.0
        catalog.validate()
        for case in cases:
            assert catalog.canonical_function_id(case.raw_terminal_function) == case.canonical_terminal_function
            definition = catalog.function(case.canonical_terminal_function)
            assert definition is not None
            if case.risk_level == "high" or case.state_changing:
                assert definition.automation_policy == "never_auto"
                assert definition.stop_policy in NEVER_AUTO_STOP_POLICIES

        cold_timings: list[float] = []
        resolution_started = perf_counter()
        for case in cases:
            started = perf_counter()
            catalog.plan_goal(case.goal_text)
            cold_timings.append(perf_counter() - started)
        resolution_seconds = perf_counter() - resolution_started
        cold_p95 = _percentile(cold_timings, 0.95)
        assert resolution_seconds < 900.0
        assert cold_p95 < 1.5

        report = evaluate_catalog_derived_paraphrases(catalog, cases)
        assert report["catalog_derived"] is True
        assert report["tuning_allowed"] is True
        assert report["independent_accuracy_evidence"] is False
        assert report["total"] == exact_cases
        assert report["correct"] + report["generic"] + report["wrong"] == exact_cases
        assert report["logical_terminal_correct"] == report["correct"]
        gates = policy_payload["diagnostic_gates"]
        assert report["correct"] >= int(gates["minimum_correct"])
        assert report["generic"] <= int(gates["maximum_generic"])
        assert report["wrong"] <= int(gates["maximum_wrong"])
        assert report["short_source_overlap_cases"] <= int(
            gates["maximum_short_source_overlap_cases"]
        )
        assert report["goal_rule_action_overlap_cases"] <= int(
            gates["maximum_goal_rule_action_overlap_cases"]
        )
        assert report["expected_boundary_mismatch_cases"] <= int(
            gates["maximum_expected_boundary_mismatch_cases"]
        )
        assert report["safety_violations"] <= int(
            gates["maximum_safety_violations"]
        )
        assert set(report["families"]) == set(policy_payload["family_order"])
        assert set(report["locales"]) == {"ko", "en"}
        for values in report["families"].values():
            assert values["total"] == int(expected["cases_per_family"])
            assert values["correct"] + values["generic"] + values["wrong"] == values["total"]
        for values in report["locales"].values():
            assert values["total"] == int(expected["cases_per_locale"])
            assert values["correct"] + values["generic"] + values["wrong"] == values["total"]

        warm_timings: list[float] = []
        warm_sample = cases[::37]
        for case in warm_sample:
            started = perf_counter()
            catalog.plan_goal(case.goal_text)
            warm_timings.append(perf_counter() - started)
        warm_p95 = _percentile(warm_timings, 0.95)
        assert warm_p95 < 0.25

    family_summary = ",".join(
        f"{family}={values['correct']}/{values['generic']}/{values['wrong']}"
        for family, values in report["families"].items()
    )
    locale_summary = ",".join(
        f"{locale}={values['correct']}/{values['generic']}/{values['wrong']}"
        for locale, values in report["locales"].items()
    )
    generation_summary = ",".join(
        f"{generation}={count}"
        for generation, count in sorted(Counter(case.generation for case in cases).items())
    )
    print(
        "navigation exhaustive catalog-derived paraphrase checks ok | "
        f"cases={exact_cases} intents={exact_intents} domains={len(case_domain_counts)} "
        f"correct={report['correct']} generic={report['generic']} wrong={report['wrong']} "
        f"short_overlap={report['short_source_overlap_cases']} "
        f"rule_overlap={report['goal_rule_action_overlap_cases']} "
        f"boundary_mismatch={report['expected_boundary_mismatch_cases']} "
        f"generation={generation_seconds:.4f}s construction={construction_seconds:.4f}s "
        f"resolution={resolution_seconds:.4f}s cold_p95={cold_p95:.4f}s "
        f"warm_p95={warm_p95:.4f}s warm_mean={statistics.mean(warm_timings):.6f}s "
        f"locales[{locale_summary}] families[{family_summary}] generations[{generation_summary}]"
    )


def _generation(intent_id: str) -> str:
    for generation in ("v15", "v14", "v13", "v12", "v11", "v10", "v9", "v8", "v7", "v6", "v5", "v4", "v3"):
        if intent_id.startswith(generation + "_"):
            return generation
    return "core"


def _assert_policy_corruptions_fail(policy_payload: dict[str, object]) -> None:
    corruptions: list[dict[str, object]] = []
    false_independence = deepcopy(policy_payload)
    false_independence["independent_accuracy_evidence"] = True
    corruptions.append(false_independence)
    copy_allowed = deepcopy(policy_payload)
    copy_allowed["anti_copy_policy"][
        "reject_normalized_source_substring_at_or_above_minimum"
    ] = False
    corruptions.append(copy_allowed)
    missing_dimension = deepcopy(policy_payload)
    missing_dimension["templates"]["role_first"]["ko"] = "{role} {asset} {state} {action} {safety}"
    corruptions.append(missing_dimension)
    disabled_quality_gate = deepcopy(policy_payload)
    disabled_quality_gate["diagnostic_gates"]["minimum_correct"] = -1
    corruptions.append(disabled_quality_gate)
    for corrupted in corruptions:
        try:
            validate_paraphrase_development_policy(corrupted)
        except ValueError:
            continue
        raise AssertionError("corrupted paraphrase development policy was accepted")


def _all_normalized_source_phrases(
    intent: dict[str, object],
    definition: dict[str, object],
) -> frozenset[str]:
    """Reconstruct protected source text without trusting generator helpers."""

    values: list[object] = list(intent.get("patterns", []))
    localized_patterns = intent.get("patterns_by_locale", {})
    assert isinstance(localized_patterns, dict)
    for localized in localized_patterns.values():
        values.extend(localized if isinstance(localized, list) else [localized])
    representative = intent.get("representative_goal_by_locale", {})
    assert isinstance(representative, dict)
    values.extend(representative.values())
    aliases = definition.get("aliases", {})
    assert isinstance(aliases, dict)
    for localized in aliases.values():
        values.extend(localized if isinstance(localized, list) else [localized])
    values.extend((definition.get("name_ko", ""), definition.get("name_en", "")))
    return frozenset(
        normalized
        for value in values
        if (normalized := _normalize(str(value).strip()))
    )


def _normalized_goal_rule_terms(intent: dict[str, object]) -> frozenset[str]:
    goal_rules = intent.get("goal_rules", [])
    assert isinstance(goal_rules, list)
    values: list[object] = []
    for raw_rule in goal_rules:
        assert isinstance(raw_rule, dict)
        raw_terms = raw_rule.get("all_of", [])
        assert isinstance(raw_terms, list)
        values.extend(raw_terms)
    return frozenset(
        normalized
        for value in values
        if (normalized := _normalize(str(value).strip()))
    )


def _percentile(values: list[float], quantile: float) -> float:
    assert values
    index = max(0, min(len(values) - 1, round(quantile * len(values) + 0.499999) - 1))
    return sorted(values)[index]


if __name__ == "__main__":
    main()
