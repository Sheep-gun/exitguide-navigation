from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_function_catalog import (
    NEVER_AUTO_STOP_POLICIES,
    NavigationFunctionCatalog,
)
from app.services.navigation_goal_prose_development import (
    evaluate_catalog_derived_prose_cases,
    generate_catalog_derived_prose_cases,
    validate_catalog_derived_prose_policy,
)


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
POLICY_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-prose-catalog.v1.json"
)


def main() -> None:
    catalog_payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    policy_payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    validate_catalog_derived_prose_policy(policy_payload)
    cases = generate_catalog_derived_prose_cases(
        catalog_payload=catalog_payload,
        policy_payload=policy_payload,
    )
    categories = {case.category for case in cases}
    assert categories == {
        "asset",
        "decoy_clause",
        "lifecycle_state",
        "long_prose",
        "negation",
        "role",
    }
    assert len(cases) == int(policy_payload["cases_per_category"]) * len(categories)
    assert len({case.case_id for case in cases}) == len(cases)

    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "prose-development.sqlite",
            CATALOG_PATH,
        )
        assert catalog._goal_semantic_enriched_postings is None
        # Exact catalog goals remain authoritative; prose fallback work may
        # rescue only goals that the reviewed resolver left unresolved.
        intents = catalog_payload["intents"]
        direct_indices = [
            ((2 * index + 1) * len(intents)) // 80
            for index in range(40)
        ]
        for index in direct_indices:
            source_intent = intents[index]
            plan = catalog.plan_goal(str(source_intent["patterns"][0]))
            assert plan.intent == str(source_intent["intent_id"])

        # Measure the same deterministic cases with only the new final stage
        # disabled. This is development evidence, not an independent score.
        catalog._best_enriched_semantic_goal_match = lambda _goal_text: None
        baseline_plans = tuple(catalog.plan_goal(case.goal_text) for case in cases)
        baseline_report = evaluate_catalog_derived_prose_cases(catalog, cases)
        del catalog._best_enriched_semantic_goal_match
        assert catalog._goal_semantic_enriched_postings is None
        assert baseline_report["correct"] == 164
        assert baseline_report["generic"] == 40

        catalog._goal_plan_cache.clear()
        final_plans = tuple(catalog.plan_goal(case.goal_text) for case in cases)
        report = evaluate_catalog_derived_prose_cases(catalog, cases)
        assert catalog._goal_semantic_enriched_postings is not None
        assert report["catalog_derived"] is True
        assert report["tuning_allowed"] is True
        assert report["independent_accuracy_evidence"] is False
        assert report["total"] == len(cases)
        assert set(report["categories"]) == categories
        assert report["correct"] >= 190
        assert report["generic"] <= 9
        assert report["logical_terminal_correct"] == report["correct"]
        minimum_correct = {
            "asset": 34,
            "decoy_clause": 25,
            "lifecycle_state": 32,
            "long_prose": 33,
            "negation": 30,
            "role": 31,
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
        assert rescued == 31

        for case in cases:
            plan = catalog.plan_goal(case.goal_text)
            if not plan.terminal_function:
                continue
            definition = catalog.function(plan.terminal_function)
            assert definition is not None
            if definition.risk_level == "high" or definition.state_changing:
                assert definition.automation_policy == "never_auto"
                assert definition.stop_policy in NEVER_AUTO_STOP_POLICIES

        high_risk = next(
            function
            for function in catalog_payload["functions"]
            if function.get("risk_level") == "high" and function.get("name_en")
        )
        negated_high_risk = f"My actual goal is not {high_risk['name_en']}"
        assert catalog._best_semantic_goal_match(negated_high_risk) is None
        assert catalog._best_enriched_semantic_goal_match(negated_high_risk) is None

    compact = ",".join(
        f"{category}={values['correct']}/{values['total']}"
        for category, values in report["categories"].items()
    )
    print(
        "navigation catalog-derived prose development checks ok | "
        f"before={baseline_report['correct']}/{baseline_report['total']} "
        f"generic={baseline_report['generic']} "
        f"after={report['correct']}/{report['total']} "
        f"generic={report['generic']} rescued={rescued} {compact}"
    )


if __name__ == "__main__":
    main()
