from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_function_catalog import (
    GOAL_CONCRETE_SCORE_FLOOR,
    GoalRuleDefinition,
    NavigationFunctionCatalog,
    _normalize,
    _should_run_exhaustive_goal_fuzzy,
)
from app.services.navigation_goal_char_retrieval import (
    get_navigation_goal_char_retriever,
)


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
SEMANTIC_FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-semantic-fallback.v1.json"
)
CHAR_FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-char-retrieval.v1.json"
)


def _plan_before_char(
    catalog: NavigationFunctionCatalog, goal: str
) -> tuple[object, float, object | None]:
    normalized = _normalize(goal)
    match = catalog._best_goal_match(normalized, include_fuzzy=False)
    reviewed_winner = match[2][1] >= 1
    if (
        not reviewed_winner
        and match[1] < 0.72
        and _should_run_exhaustive_goal_fuzzy(normalized, match[1])
    ):
        match = catalog._best_fuzzy_goal_match(normalized, baseline=match)
    semantic_match = None
    fallback_required = catalog._goal_match_requires_fallback(
        best_intent=match[0],
        best_score=match[1],
        best_key=match[2],
        reviewed_winner=reviewed_winner,
    )
    if fallback_required:
        semantic_match = catalog._best_semantic_goal_match(goal)
        if semantic_match is not None:
            default_terminal = catalog._intent_terminal.get(
                semantic_match.intent_id, ""
            )
            rule = (
                GoalRuleDefinition(
                    score=semantic_match.score,
                    terms=(),
                    terminal_function=semantic_match.terminal_function,
                )
                if semantic_match.terminal_function != default_terminal
                else None
            )
            return (
                catalog._goal_plan_from_match(
                    best_intent=semantic_match.intent_id,
                    best_score=semantic_match.score,
                    best_rule=rule,
                ),
                semantic_match.score,
                semantic_match,
            )
        fail_closed_score = min(
            match[1], GOAL_CONCRETE_SCORE_FLOOR - 0.000001
        )
        return (
            catalog._goal_plan_from_match(
                best_intent="generic_navigation",
                best_score=fail_closed_score,
                best_rule=None,
            ),
            fail_closed_score,
            None,
        )
    return (
        catalog._goal_plan_from_match(
            best_intent=match[0],
            best_score=match[1],
            best_rule=match[3],
        ),
        match[1],
        semantic_match,
    )


def main() -> None:
    controls = json.loads(CHAR_FIXTURE_PATH.read_text(encoding="utf-8"))
    semantic_fixture = json.loads(
        SEMANTIC_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    integration_cases = list(controls["integration_cases"])
    contract = controls["integration_contract"]
    assert controls["tuning_allowed"] is True
    assert controls["catalog_derived"] is True
    assert controls["claims"]["independent_accuracy_evidence"] is False
    assert len(integration_cases) >= int(contract["minimum_char_adoptions"])
    assert len({case["case_key"] for case in integration_cases}) == len(
        integration_cases
    )

    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "char-integration.sqlite", CATALOG_PATH
        )
        before_stats = catalog.goal_char_retrieval_stats()
        assert before_stats["initialized"] is False

        adopted = 0
        correct = 0
        for case in integration_cases:
            goal = str(case["goal"])
            pre_char_plan, pre_char_score, semantic_match = _plan_before_char(
                catalog, goal
            )
            assert pre_char_score < 0.34
            assert pre_char_plan.intent == "generic_navigation"
            assert semantic_match is None

            plan = catalog.plan_goal(goal)
            retriever = get_navigation_goal_char_retriever(
                catalog.catalog_path,
                catalog_fingerprint=catalog._sha256,
            )
            retrieval = retriever.retrieve(goal, limit=5)
            assert retrieval.admitted is True
            assert retrieval.negated is False
            candidate = retrieval.candidates[0]
            adopted += 1
            is_correct = (
                plan.intent == str(case["expected_intent_id"])
                and plan.terminal_function == str(case["expected_function_id"])
                and candidate.intent_id == str(case["expected_intent_id"])
                and candidate.terminal_function
                == str(case["expected_function_id"])
            )
            correct += int(is_correct)
            assert is_correct
            assert plan.confidence >= 0.34
            assert plan.preferred_functions[-1] == (
                str(case["expected_function_id"]),
                1.0,
            )
            definition = catalog.function(plan.terminal_function)
            assert definition is not None
            if definition.state_changing or definition.risk_level == "high":
                assert definition.automation_policy == "never_auto"

        assert adopted >= int(contract["minimum_char_adoptions"])
        assert correct / adopted >= float(
            contract["minimum_char_adoption_precision"]
        )

        # A strong char disagreement must never replace an existing concrete
        # reviewed/fuzzy decision.
        source_case = next(
            pair
            for pair in semantic_fixture["intent_pairs"]
            if pair["case_key"] == "ev_post_charge_fee"
        )
        concrete_goal = str(source_case["en"])
        concrete_before, concrete_score, _semantic = _plan_before_char(
            catalog, concrete_goal
        )
        assert concrete_score >= 0.34
        retriever = get_navigation_goal_char_retriever(
            catalog.catalog_path,
            catalog_fingerprint=catalog._sha256,
        )
        disagreement = retriever.retrieve(concrete_goal, limit=5)
        assert disagreement.admitted is True
        assert disagreement.candidates[0].intent_id != concrete_before.intent
        query_count_before = int(retriever.runtime_stats()["query_count"])
        assert catalog.plan_goal(concrete_goal) == concrete_before
        query_count_after = int(retriever.runtime_stats()["query_count"])
        assert query_count_after == query_count_before

        # A semantic rescue also bypasses the final retriever layer.
        semantic_case = None
        semantic_plan = None
        for pair in semantic_fixture["intent_pairs"]:
            for field in ("ko", "en"):
                candidate_goal = str(pair[field])
                before, score, semantic = _plan_before_char(catalog, candidate_goal)
                if score >= 0.34 and semantic is not None:
                    semantic_case = candidate_goal
                    semantic_plan = before
                    break
            if semantic_case is not None:
                break
        assert semantic_case is not None and semantic_plan is not None
        query_count_before = int(retriever.runtime_stats()["query_count"])
        assert catalog.plan_goal(semantic_case) == semantic_plan
        query_count_after = int(retriever.runtime_stats()["query_count"])
        assert query_count_after == query_count_before

        # Concurrent lazy getter calls share the already-built revision.
        with ThreadPoolExecutor(max_workers=8) as executor:
            instances = list(
                executor.map(
                    lambda _index: get_navigation_goal_char_retriever(
                        catalog.catalog_path,
                        catalog_fingerprint=catalog._sha256,
                    ),
                    range(24),
                )
            )
        assert len({id(instance) for instance in instances}) == 1
        after_stats = catalog.goal_char_retrieval_stats()
        assert after_stats["initialized"] is True
        assert after_stats["build_count"] == 1
        runtime = after_stats["runtime"]
        assert isinstance(runtime, dict)
        assert int(runtime["cache_entries"]) <= int(runtime["cache_capacity"])

        print(
            "navigation goal char integration checks ok: "
            f"adopted_precision={correct}/{adopted} "
            f"singleton_builds={after_stats['build_count']} "
            f"queries={runtime['query_count']} cache={runtime['cache_entries']}/"
            f"{runtime['cache_capacity']}"
        )


if __name__ == "__main__":
    main()
