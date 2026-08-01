from __future__ import annotations

import json
import statistics
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.services.navigation_function_catalog import (
    GOAL_CONCRETE_SCORE_FLOOR,
    NavigationFunctionCatalog,
    _goal_cache_key,
    _normalize,
    _should_run_exhaustive_goal_fuzzy,
)
from app.services.navigation_goal_char_retrieval import (
    get_navigation_goal_char_retriever,
)


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-semantic-fallback.v1.json"
)


def _legacy_plan(catalog: NavigationFunctionCatalog, goal: str) -> tuple[object, float]:
    normalized = _normalize(goal)
    match = catalog._best_goal_match(normalized, include_fuzzy=False)
    reviewed_winner = match[2][1] >= 1
    if (
        not reviewed_winner
        and match[1] < 0.72
        and _should_run_exhaustive_goal_fuzzy(normalized, match[1])
    ):
        match = catalog._best_fuzzy_goal_match(normalized, baseline=match)
    if catalog._goal_match_requires_fallback(
        best_intent=match[0],
        best_score=match[1],
        best_key=match[2],
        reviewed_winner=reviewed_winner,
    ):
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
        )
    return (
        catalog._goal_plan_from_match(
            best_intent=match[0],
            best_score=match[1],
            best_rule=match[3],
        ),
        match[1],
    )


def main() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    pairs = list(fixture["intent_pairs"])
    assert fixture["schema_version"] == 1
    assert fixture["frozen"] is False
    assert fixture["catalog_derived"] is False
    assert fixture["tuning_allowed"] is True
    assert fixture["source_kind"] == "semantic_development"
    assert fixture["claims"] == {
        "independent_accuracy_evidence": False,
        "unseen_holdout": False,
        "production_device_accuracy": False,
    }
    assert len(pairs) == 30
    assert len({pair["case_key"] for pair in pairs}) == 30
    assert len({pair["intent_id"] for pair in pairs}) == 30
    assert len({pair["expected_function_id"] for pair in pairs}) == 30
    assert sum("homonym" in pair["tags"] for pair in pairs) >= 10
    assert sum("role_reversal" in pair["tags"] for pair in pairs) >= 10

    authored_cases = [
        (pair, locale, str(pair[key]))
        for pair in pairs
        for locale, key in (("ko-KR", "ko"), ("en-US", "en"))
    ]
    assert len(authored_cases) == 60
    assert len({_normalize(goal) for _pair, _locale, goal in authored_cases}) == 60
    assert all(len(goal) >= (55 if locale == "ko-KR" else 100) for _pair, locale, goal in authored_cases)

    source = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    source_intents = {str(item["intent_id"]): item for item in source["intents"]}
    source_functions = {str(item["function_id"]): item for item in source["functions"]}
    all_patterns = {
        _normalize(str(pattern))
        for item in source["intents"]
        for pattern in item.get("patterns", [])
    }
    all_aliases = {
        _normalize(str(alias))
        for item in source["functions"]
        for values in item.get("aliases", {}).values()
        for alias in values
    }
    domains = {
        str(source_functions[str(pair["expected_function_id"])]["domain"])
        for pair in pairs
    }
    assert len(domains) >= 20
    for pair, _locale, goal in authored_cases:
        intent_id = str(pair["intent_id"])
        function_id = str(pair["expected_function_id"])
        assert intent_id in source_intents
        assert function_id in source_functions
        assert str(source_intents[intent_id]["terminal_function"]) == function_id
        normalized = _normalize(goal)
        assert normalized not in all_patterns
        assert normalized not in all_aliases

    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "semantic-fallback.sqlite"
        catalog = NavigationFunctionCatalog(database_path, CATALOG_PATH)
        # The character retriever is lazy in production. Measure its one-time
        # initialization separately so it cannot masquerade as warm semantic
        # query latency in this unit.
        char_cold_started = perf_counter()
        char_retriever = get_navigation_goal_char_retriever(
            catalog.catalog_path,
            catalog_fingerprint=catalog._sha256,
        )
        char_cold_seconds = perf_counter() - char_cold_started
        assert char_retriever.stats.catalog_version == catalog.version
        print(
            "navigation goal semantic fallback char cold timing: "
            f"{char_cold_seconds:.4f}s"
        )
        # This unit only separates the lazy character-index build from warm
        # semantic latency.  The dedicated retriever/performance units retain
        # the stricter build SLA; allow filesystem-cache variance here.
        # V15 expands the sparse index to 2,690 candidates; leave modest
        # Windows scheduling headroom here while the dedicated retrieval unit
        # keeps the stricter 22-second cold-build gate.
        assert char_cold_seconds < 25.0
        fallback_rescues = 0
        semantic_admissions = 0
        deferred_generic = 0
        preserved_non_generic = 0
        overall_correct = 0
        timings: list[float] = []
        first_results: list[object] = []
        for pair, locale, goal in authored_cases:
            legacy_plan, legacy_score = _legacy_plan(catalog, goal)
            started = perf_counter()
            plan = catalog.plan_goal(goal)
            timings.append(perf_counter() - started)
            first_results.append(plan)
            expected_intent = str(pair["intent_id"])
            expected_function = str(pair["expected_function_id"])
            overall_correct += int(
                plan.intent == expected_intent and plan.terminal_function == expected_function
            )
            semantic_match = catalog._best_semantic_goal_match(goal)
            if legacy_score >= 0.34:
                # The new ensemble is strictly a generic fallback and must be
                # byte-for-byte irrelevant to every pre-existing decision.
                assert plan == legacy_plan
                preserved_non_generic += 1
            elif semantic_match is None:
                assert plan == legacy_plan
                assert plan.intent == "generic_navigation"
                deferred_generic += 1
            else:
                semantic_admissions += 1
                assert plan.intent == expected_intent, (
                    pair["case_key"], locale, expected_intent, plan.intent
                )
                assert plan.terminal_function == expected_function
                fallback_rescues += 1

            definition = catalog.function(plan.terminal_function)
            if definition is not None and (definition.state_changing or definition.risk_level == "high"):
                assert definition.automation_policy == "never_auto"
                assert definition.stop_policy in {
                    "before_action",
                    "before_activation",
                    "user_confirmation",
                    "user_only",
                    "stop_before_action",
                }

        # Fail-closed negation handling intentionally defers some otherwise
        # recoverable prose; precision and legacy preservation take priority
        # over maximizing rescue count.
        assert fallback_rescues == 11
        assert semantic_admissions == 11
        assert semantic_admissions == fallback_rescues
        assert preserved_non_generic + deferred_generic + semantic_admissions == 60

        # Catalog-derived, app-independent route vocabulary must preserve the
        # established maps.navigation winner without memorizing a fixed
        # sentence.  Two independent concepts (guidance + explicit start)
        # are required; modality or destination words alone are insufficient.
        route_guidance_development = (
            "Start spoken turn-by-turn guidance for the selected destination",
            "Begin spoken route guidance toward a chosen place",
            "Begin turn-by-turn guidance for the selected destination",
            "선택한 목적지까지 음성 길안내를 시작해 줘",
            "회전 안내가 포함된 길 안내를 시작하고 싶어",
        )
        for goal in route_guidance_development:
            plan = catalog.plan_goal(goal)
            assert plan.intent == "v3_maps_navigation", (goal, plan)
            assert plan.terminal_function == "maps.navigation"
        for goal in (
            "Open spoken feedback accessibility settings",
            "Show the airport transit timetable without starting guidance",
            "음성 피드백 접근성 설정을 열어 줘",
        ):
            assert catalog.plan_goal(goal).terminal_function != "maps.navigation"

        unresolved_negation = (
            "Not a human vaccination and health record Correct a store item's "
            "on-hand inventory discrepancy without changing animal medical data"
        )
        contrasted_inventory = (
            "Not a human vaccination and health record, correct a store item's "
            "on-hand inventory discrepancy without changing animal medical data"
        )
        assert _goal_cache_key(unresolved_negation) != _goal_cache_key(
            contrasted_inventory
        )
        catalog._goal_plan_cache.clear()
        unresolved_first = catalog.plan_goal(unresolved_negation)
        contrasted_second = catalog.plan_goal(contrasted_inventory)
        catalog._goal_plan_cache.clear()
        contrasted_first = catalog.plan_goal(contrasted_inventory)
        unresolved_second = catalog.plan_goal(unresolved_negation)
        assert unresolved_first == unresolved_second
        assert contrasted_first == contrasted_second
        assert unresolved_first.intent == "generic_navigation"
        assert catalog._best_semantic_goal_match(unresolved_negation) is None

        # Determinism is checked across cache state and reverse request order.
        catalog._goal_plan_cache.clear()
        second_results = [
            catalog.plan_goal(goal)
            for _pair, _locale, goal in reversed(authored_cases)
        ]
        assert first_results == list(reversed(second_results))

        # Reloading a current SQLite catalog exercises runtime index cold-start
        # cost without conflating it with one-time JSON-to-SQLite bootstrap.
        cold_started = perf_counter()
        reloaded = NavigationFunctionCatalog(database_path, CATALOG_PATH)
        cold_seconds = perf_counter() - cold_started
        assert reloaded.version == catalog.version
        p95_index = max(0, round(0.95 * len(timings) + 0.499999) - 1)
        warm_p95 = sorted(timings)[p95_index]
        print(
            "navigation goal semantic fallback timing: "
            f"warm_p95={warm_p95:.4f}s "
            f"warm_mean={statistics.mean(timings):.4f}s "
            f"cold_reload={cold_seconds:.4f}s "
            f"char_cold_build={char_cold_seconds:.4f}s"
        )
        # V15 contains 2,660 intents and 109,230 context phrases. Keep bounded
        # regression gates with enough headroom for cold filesystem-cache
        # variance while still rejecting a material warm-path slowdown.
        # This unit runs beside long catalog-generation regressions in the
        # feedback loop.  Keep a meaningful cold-reload ceiling without
        # duplicating the stricter isolated gate in the dedicated resolver
        # performance unit; warm-path latency remains the production-critical
        # assertion here.
        assert cold_seconds < 25.0
        assert warm_p95 < 0.65
        print(
            "navigation goal semantic fallback checks ok: "
            f"development_cases={len(authored_cases)} domains={len(domains)} "
            f"fallback_precision={fallback_rescues}/{semantic_admissions} "
            f"preserved={preserved_non_generic} deferred={deferred_generic} "
            f"overall_correct={overall_correct}/{len(authored_cases)} "
            f"warm_p95={warm_p95:.4f}s warm_mean={statistics.mean(timings):.4f}s "
            f"cold_reload={cold_seconds:.4f}s char_cold_build={char_cold_seconds:.4f}s"
        )


if __name__ == "__main__":
    main()
