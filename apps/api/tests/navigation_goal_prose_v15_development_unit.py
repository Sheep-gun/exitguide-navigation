from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.services.navigation_function_catalog import (
    NEVER_AUTO_STOP_POLICIES,
    NavigationFunctionCatalog,
    _normalize,
)
from app.services.navigation_goal_prose_development import (
    evaluate_catalog_derived_prose_cases,
    generate_catalog_derived_governance_prose_cases,
    validate_catalog_derived_governance_policy,
)


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
POLICY_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-prose-v15.v1.json"
)


def main() -> None:
    catalog_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    policy_payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    validate_catalog_derived_governance_policy(policy_payload)
    cases = generate_catalog_derived_governance_prose_cases(
        catalog_payload=catalog_payload,
        policy_payload=policy_payload,
    )
    v15_intents = {
        str(intent["intent_id"])
        for intent in catalog_payload["intents"]
        if str(intent["intent_id"]).startswith("v15_")
    }
    categories = {
        "role_clause",
        "asset_clause",
        "state_clause",
        "jurisdiction_clause",
        "purpose_clause",
    }
    assert len(v15_intents) == 240
    assert len(cases) == 240
    assert {case.intent_id for case in cases} == v15_intents
    assert Counter(case.intent_id for case in cases) == {
        intent_id: 1 for intent_id in v15_intents
    }
    assert Counter(case.category for case in cases) == {
        category: 48 for category in categories
    }
    assert len({case.case_id for case in cases}) == 240

    catalog_phrases = {
        _normalize(str(value))
        for intent in catalog_payload["intents"]
        for value in intent.get("patterns", [])
    }
    catalog_phrases.update(
        _normalize(str(value))
        for function in catalog_payload["functions"]
        for values in function.get("aliases", {}).values()
        for value in values
    )
    assert all(_normalize(case.goal_text) not in catalog_phrases for case in cases)

    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "v15-prose-development.sqlite",
            CATALOG_PATH,
        )
        assert catalog.stats()["asset_cue_count"] >= 504
        catalog._best_enriched_semantic_goal_match = lambda _goal_text: None
        baseline_plans = tuple(catalog.plan_goal(case.goal_text) for case in cases)
        baseline_report = evaluate_catalog_derived_prose_cases(catalog, cases)
        del catalog._best_enriched_semantic_goal_match
        enriched_started = perf_counter()
        catalog._ensure_goal_semantic_enriched_index()
        enriched_cold_seconds = perf_counter() - enriched_started
        assert enriched_cold_seconds < 25.0
        catalog._goal_plan_cache.clear()
        final_plans_list = []
        timings = []
        for case in cases:
            started = perf_counter()
            final_plans_list.append(catalog.plan_goal(case.goal_text))
            timings.append(perf_counter() - started)
        final_plans = tuple(final_plans_list)
        report = evaluate_catalog_derived_prose_cases(catalog, cases)

        assert report["catalog_derived"] is True
        assert report["tuning_allowed"] is True
        assert report["independent_accuracy_evidence"] is False
        assert report["total"] == 240
        assert set(report["categories"]) == categories
        assert report["logical_terminal_correct"] == report["correct"]
        assert baseline_report["correct"] == 85
        assert baseline_report["generic"] == 15
        assert report["correct"] >= 96
        assert report["generic"] <= 4
        minimum_correct = {
            "asset_clause": 18,
            "jurisdiction_clause": 13,
            "purpose_clause": 19,
            "role_clause": 14,
            "state_clause": 32,
        }
        for category, minimum in minimum_correct.items():
            assert report["categories"][category]["correct"] >= minimum

        rescued = 0
        for case, baseline_plan, final_plan in zip(
            cases,
            baseline_plans,
            final_plans,
            strict=True,
        ):
            if baseline_plan.intent != "generic_navigation":
                assert final_plan == baseline_plan
                continue
            if final_plan.intent != "generic_navigation":
                assert final_plan.intent == case.intent_id
                rescued += 1
        assert rescued == 11
        p95_index = max(0, round(0.95 * len(timings) + 0.499999) - 1)
        warm_p95 = sorted(timings)[p95_index]
        assert warm_p95 < 0.65

        for case, plan in zip(cases, final_plans, strict=True):
            if plan.intent != case.intent_id:
                continue
            definition = catalog.function(plan.terminal_function)
            assert definition is not None
            assert definition.automation_policy == "never_auto"
            assert definition.stop_policy in NEVER_AUTO_STOP_POLICIES

    compact = ",".join(
        f"{category}={values['correct']}/{values['total']}"
        for category, values in report["categories"].items()
    )
    print(
        "navigation V15 catalog-derived governance prose checks ok | "
        f"before={baseline_report['correct']}/{baseline_report['total']} "
        f"generic={baseline_report['generic']} "
        f"after={report['correct']}/{report['total']} "
        f"generic={report['generic']} rescued={rescued} "
        f"enriched_cold={enriched_cold_seconds:.4f}s "
        f"warm_p95={warm_p95:.4f}s warm_mean={statistics.mean(timings):.4f}s "
        f"{compact}"
    )


if __name__ == "__main__":
    main()
