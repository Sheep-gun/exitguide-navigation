from __future__ import annotations

import json
import os
from difflib import SequenceMatcher
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.services.navigation_function_catalog import (
    CatalogGoalPlan,
    NavigationFunctionCatalog,
    _bitset_lcs_length,
    _normalize,
    _phrase_similarity,
    _route_with_terminal_override,
)
from app.services.navigation_goal_char_retrieval import (
    get_navigation_goal_char_retriever,
)


ROOT = Path(__file__).resolve().parents[3]
GYM_ROOT = ROOT / "fixtures" / "navigation" / "db-gym"
ACTUAL_CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
INDEPENDENT_FIXTURE_NAMES = (
    "public-web.v1.json",
    "public-insurance.v1.json",
    "public-productivity-system.v1.json",
    "independent-core.v2.json",
    "alias-collision-adversarial.v2.json",
    "independent-coverage.v2.json",
    "independent-recovery.v2.json",
    "independent-long-tail-v3.json",
    "independent-broad-services-v4.json",
    "independent-service-gaps-v5.json",
    "independent-open-world-v6.json",
    "independent-long-tail-v7.json",
    "independent-enterprise-ops-v8.json",
    "independent-cross-domain-v9.json",
    "independent-operational-v10.json",
    "independent-critical-ops-v11.json",
    "independent-specialized-ops-v12.json",
    "independent-regulated-systems-v13.json",
    "independent-institutional-systems-v14.json",
    "independent-authority-systems-v15.json",
)


def _payload(*, version: str = "performance-a", intent_count: int = 128) -> dict[str, object]:
    functions: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    for index in range(intent_count):
        destination = f"benchmark.destination.{index:03d}"
        alternate = f"benchmark.alternate.{index:03d}"
        for function_id, label in ((destination, "destination"), (alternate, "alternate")):
            functions.append(
                {
                    "function_id": function_id,
                    "domain": "benchmark",
                    "name_ko": f"벤치마크 {label} {index:03d}",
                    "name_en": f"Benchmark {label} {index:03d}",
                    "description": "Synthetic resolver performance destination.",
                    "risk_level": "low",
                    "automation_policy": "safe_navigation",
                    "terminal": True,
                    "state_changing": False,
                    "aliases": {"en": [f"{label} {index:03d}"]},
                }
            )
        patterns = [
            f"open benchmark destination {index:03d} option {option}"
            for option in range(6)
        ]
        if index == 0:
            # Exercise the legacy <=2-character guard and fuzzy fallback.
            patterns.append("go")
        intents.append(
            {
                "intent_id": f"benchmark_intent_{index:03d}",
                "terminal_function": destination,
                "patterns": patterns,
                "goal_rules": [
                    {
                        "all_of": ["secure benchmark", f"token {index:03d}"],
                        "score": 1.0,
                        "terminal_function": alternate,
                    }
                ],
                "route": [{"function_id": destination, "weight": 1.0}],
                "avoid_functions": [],
            }
        )
    return {
        "catalog_version": version,
        "functions": functions,
        "intents": intents,
        "gateway_rules": [],
    }


def _legacy_plan(catalog: NavigationFunctionCatalog, query: str) -> CatalogGoalPlan:
    """Exhaustive semantic reference for the optimized goal resolver."""

    normalized_goal = _normalize(query)
    best_intent = "generic_navigation"
    best_score = 0.0
    best_key = (0.0, 0, 0, 0, 0)
    best_rule = None
    for intent_id, patterns in catalog._intent_patterns.items():
        score = max(
            (_phrase_similarity(normalized_goal, pattern) for pattern in patterns),
            default=0.0,
        )
        intent_key = (score, 2 if score >= 1.0 else 0, 0, 0, 0)
        intent_rule = None
        for rule in catalog._intent_goal_rules.get(intent_id, ()):
            if rule.terms and all(term in normalized_goal for term in rule.terms):
                rule_key = (
                    rule.score,
                    1,
                    max(len(term) for term in rule.terms),
                    len(rule.terms),
                    sum(len(term) for term in rule.terms),
                )
                if rule_key > intent_key:
                    score = rule.score
                    intent_key = rule_key
                    intent_rule = rule
        if intent_key > best_key:
            best_intent = intent_id
            best_score = score
            best_key = intent_key
            best_rule = intent_rule

    if best_score < 0.34:
        return CatalogGoalPlan(
            intent="generic_navigation",
            terminal_function="",
            preferred_functions=(
                ("settings.root", 0.45),
                ("account.entry", 0.40),
                ("navigation.menu", 0.36),
                ("support.help", 0.30),
            ),
            avoid_functions=(),
            confidence=round(best_score, 4),
            raw_terminal_function="",
            canonical_terminal_function="",
        )
    default_terminal = catalog._intent_terminal.get(best_intent, "")
    terminal_function = (
        best_rule.terminal_function
        if best_rule is not None and best_rule.terminal_function
        else default_terminal
    )
    return CatalogGoalPlan(
        intent=best_intent,
        terminal_function=terminal_function,
        preferred_functions=_route_with_terminal_override(
            catalog._intent_routes.get(best_intent, ()),
            default_terminal=default_terminal,
            terminal_function=terminal_function,
        ),
        avoid_functions=tuple(
            function_id
            for function_id in catalog._intent_avoid.get(best_intent, ())
            if function_id != terminal_function
        ),
        confidence=round(min(1.0, best_score), 4),
        raw_terminal_function=terminal_function,
        canonical_terminal_function=terminal_function,
    )


def _exhaustive_plan(catalog: NavigationFunctionCatalog, query: str) -> CatalogGoalPlan:
    """Production semantics with every non-containing pattern compared."""

    match = catalog._best_goal_match(_normalize(query), include_fuzzy=True)
    return catalog._goal_plan_from_match(
        best_intent=match[0],
        best_score=match[1],
        best_rule=match[3],
    )


def _legacy_reference_plan(
    catalog: NavigationFunctionCatalog,
    query: str,
) -> CatalogGoalPlan:
    """Exact legacy plan, eliding fuzzy work only when it cannot win."""

    normalized = _normalize(query)
    cheap_match = catalog._best_goal_match(normalized, include_fuzzy=False)
    if cheap_match[1] >= 0.72:
        match = cheap_match
        return catalog._goal_plan_from_match(
            best_intent=match[0],
            best_score=match[1],
            best_rule=match[3],
        )
    return _exhaustive_plan(catalog, query)


def _independent_goal_texts() -> tuple[list[str], list[str]]:
    """Read only immutable goal text; expected fixture answers stay unused."""

    all_goals: list[str] = []
    v5_goals: list[str] = []
    for name in INDEPENDENT_FIXTURE_NAMES:
        payload = json.loads((GYM_ROOT / name).read_text(encoding="utf-8"))
        goals = [str(case.get("goal_text", case.get("goal", ""))) for case in payload["cases"]]
        all_goals.extend(goals)
        if name == "independent-service-gaps-v5.json":
            v5_goals.extend(goals)
    return all_goals, v5_goals


def _character_masks(value: str) -> dict[str, int]:
    masks: dict[str, int] = {}
    for index, character in enumerate(value):
        masks[character] = masks.get(character, 0) | (1 << index)
    return masks


def _actual_catalog_checks() -> tuple[float, float, int, int]:
    all_goals, v5_goals = _independent_goal_texts()
    assert len(all_goals) == 4645
    assert len(v5_goals) == 136
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "actual-catalog.sqlite",
            ACTUAL_CATALOG_PATH,
        )
        stats = catalog.stats()
        assert int(stats["function_count"]) == 2866
        assert int(stats["intent_count"]) == 2660
        assert sum(len(patterns) for patterns in catalog._intent_patterns.values()) == 67092

        # The final character retriever is intentionally lazy. Its one-time
        # sparse-index construction has a separate cold-start SLA and must not
        # be charged to the steady resolver-query budget below.
        char_cold_started = perf_counter()
        char_retriever = get_navigation_goal_char_retriever(
            catalog.catalog_path,
            catalog_fingerprint=catalog._sha256,
        )
        char_cold_seconds = perf_counter() - char_cold_started
        assert char_retriever.stats.catalog_version == catalog.version
        print(f"navigation character retriever cold build={char_cold_seconds:.4f}s")
        # Keep current-catalog cold initialization bounded while allowing Windows filesystem
        # and CPU-frequency variance; warm queries have their own strict SLA.
        assert char_cold_seconds < 22.0, (
            "character retriever cold-build regression: "
            f"seconds={char_cold_seconds:.4f}"
        )

        # These are unique, previously unseen calls against the real catalog;
        # construction/import time and result-cache hits are excluded.  The
        # 20-second ceiling is four times slower than the measured optimized
        # laptop result, yet less than half the pre-optimization 43.58 seconds.
        started = perf_counter()
        optimized_v5 = [catalog.plan_goal(goal) for goal in v5_goals]
        actual_seconds = perf_counter() - started
        assert actual_seconds < 20.0, (
            "actual-catalog cold-query regression: "
            f"queries={len(v5_goals)} seconds={actual_seconds:.4f}"
        )

        # Normal unit runs use a deterministic fuzzy-triggering subset so the
        # semantic oracle remains affordable.  Set the environment flag for a
        # release audit of all 4,645 immutable goal texts. Selection depends
        # only on runtime score, never on fixture answers.
        if os.getenv("EXITGUIDE_FULL_GOAL_RESOLVER_PARITY") == "1":
            parity_goals = all_goals
        else:
            parity_goals = []
            for goal in all_goals:
                cheap_match = catalog._best_goal_match(
                    _normalize(goal),
                    include_fuzzy=False,
                )
                if cheap_match[1] < 0.72:
                    parity_goals.append(goal)
                if len(parity_goals) == 12:
                    break
        optimized = [catalog.plan_goal(goal) for goal in parity_goals]
        exhaustive = [_legacy_reference_plan(catalog, goal) for goal in parity_goals]
        for optimized_plan, legacy_plan in zip(optimized, exhaustive, strict=True):
            # Reviewed and fuzzy non-generic winners are immutable.  A legacy
            # generic result may now be conservatively rescued by the separate
            # semantic-fallback contract, so full parity must not prohibit the
            # feature it is supposed to performance-test.
            if legacy_plan.intent != "generic_navigation":
                assert optimized_plan == legacy_plan
    return actual_seconds, char_cold_seconds, len(v5_goals), len(parity_goals)


def main() -> None:
    for left, right in (
        ("abc", "acb"),
        ("subscriptioncancel", "cancelmysubscription"),
        ("aaaaab", "baaaaa"),
    ):
        lcs_length = _bitset_lcs_length(left, _character_masks(right))
        sequence_matches = sum(
            block.size for block in SequenceMatcher(None, left, right).get_matching_blocks()
        )
        assert sequence_matches <= lcs_length <= min(len(left), len(right))

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        catalog_path = root / "catalog.json"
        database_path = root / "catalog.sqlite"
        payload = _payload()
        catalog_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        catalog = NavigationFunctionCatalog(database_path, catalog_path)

        queries = [
            f"please open benchmark destination {index:03d} option {index % 6} menu"
            for index in range(128)
        ]
        queries.extend(
            (
                "secure benchmark token 000",
                "pleaze opan benchmark destinashun 017 option 4",
                "go",
                "words with no catalog relationship whatsoever",
            )
        )

        legacy_started = perf_counter()
        legacy_results = [_legacy_plan(catalog, query) for query in queries]
        legacy_seconds = perf_counter() - legacy_started

        catalog._goal_plan_cache.clear()
        optimized_started = perf_counter()
        optimized_results = [catalog.plan_goal(query) for query in queries]
        optimized_seconds = perf_counter() - optimized_started

        assert optimized_results == legacy_results
        assert optimized_results[128].terminal_function == "benchmark.alternate.000"
        # The synthetic workload is intentionally dominated by wrapped exact
        # patterns.  A generous 3x gate avoids machine-speed flakiness while
        # detecting accidental removal of the containment fast path.
        assert optimized_seconds * 3 < legacy_seconds, (
            f"goal resolver speed regression: optimized={optimized_seconds:.4f}s "
            f"legacy={legacy_seconds:.4f}s"
        )

        # A source SHA change must rebuild both the SQLite content and compiled
        # matcher tuples; no cached plan may survive a catalog revision.
        revised = _payload(version="performance-b")
        revised["intents"][0]["patterns"] = ["brand new resolver phrase"]
        catalog_path.write_text(json.dumps(revised, ensure_ascii=False), encoding="utf-8")
        reloaded = NavigationFunctionCatalog(database_path, catalog_path)
        revised_plan = reloaded.plan_goal("please brand new resolver phrase")
        assert reloaded.version == "performance-b"
        assert revised_plan.intent == "benchmark_intent_000"
        assert reloaded.plan_goal("go").intent != "benchmark_intent_000"

        print(
            "navigation goal resolver performance checks ok | "
            f"queries={len(queries)} legacy={legacy_seconds:.4f}s "
            f"optimized={optimized_seconds:.4f}s "
            f"speedup={legacy_seconds / optimized_seconds:.1f}x"
        )

    (
        actual_seconds,
        char_cold_seconds,
        actual_queries,
        parity_queries,
    ) = _actual_catalog_checks()
    print(
        "navigation actual-catalog performance checks ok | "
        f"cold_queries={actual_queries} seconds={actual_seconds:.4f}s "
        f"qps={actual_queries / actual_seconds:.1f} parity={parity_queries} "
        f"char_cold_build={char_cold_seconds:.4f}s"
    )


if __name__ == "__main__":
    main()
