from __future__ import annotations

import json
import statistics
from pathlib import Path
from time import perf_counter
import tracemalloc

from app.services.navigation_goal_char_retrieval import NavigationGoalCharRetriever


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
SOURCE_FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-semantic-fallback.v1.json"
)
CONTROL_FIXTURE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "development-goal-char-retrieval.v1.json"
)


def main() -> None:
    source_fixture = json.loads(SOURCE_FIXTURE_PATH.read_text(encoding="utf-8"))
    controls = json.loads(CONTROL_FIXTURE_PATH.read_text(encoding="utf-8"))
    contract = controls["gate_contract"]
    assert controls["schema_version"] == 1
    assert controls["frozen"] is False
    assert controls["catalog_derived"] is True
    assert controls["tuning_allowed"] is True
    assert controls["source_fixture"] == SOURCE_FIXTURE_PATH.name
    assert controls["claims"] == {
        "independent_accuracy_evidence": False,
        "unseen_holdout": False,
        "production_device_accuracy": False,
    }
    assert len(source_fixture["intent_pairs"]) == 30
    assert len(controls["negation_controls"]) >= 6
    assert len(controls["generic_controls"]) >= 6
    assert len(controls["integration_cases"]) >= 5

    build_started = perf_counter()
    retriever = NavigationGoalCharRetriever(CATALOG_PATH)
    build_seconds = perf_counter() - build_started
    # Trace a separate cold construction so instrumentation overhead does not
    # masquerade as the production initialization time.
    tracemalloc.start()
    traced_retriever = NavigationGoalCharRetriever(CATALOG_PATH)
    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    stats = retriever.stats
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert stats.catalog_version == str(catalog["catalog_version"])
    assert stats.candidate_count == 2690
    assert stats.candidate_count >= len(catalog["intents"])
    assert stats.candidate_count <= len(catalog["intents"]) + 100
    assert 0 < stats.feature_count <= stats.posting_count
    assert stats.posting_count <= stats.candidate_count * 176
    assert stats.maximum_profile_features <= 176
    assert stats.maximum_posting_length <= 64
    print(
        "navigation goal char retrieval cold metrics: "
        f"build={build_seconds:.4f}s peak_bytes={peak_bytes} "
        f"estimated_index_bytes={stats.estimated_index_bytes}"
    )
    assert build_seconds < float(contract["maximum_build_seconds"])
    assert peak_bytes < int(contract["maximum_traced_peak_bytes"])
    assert stats.estimated_index_bytes < int(contract["maximum_estimated_index_bytes"])

    authored_cases = [
        (pair, locale, str(pair[field]))
        for pair in source_fixture["intent_pairs"]
        for locale, field in (("ko-KR", "ko"), ("en-US", "en"))
    ]
    timings: list[float] = []
    first_results = []
    top_one_correct = 0
    admitted = 0
    admitted_correct = 0
    for pair, _locale, goal in authored_cases:
        started = perf_counter()
        result = retriever.retrieve(goal, limit=5)
        timings.append(perf_counter() - started)
        first_results.append(result)
        assert result.query == goal
        assert len(result.candidates) <= 5
        assert all(
            result.candidates[index].score >= result.candidates[index + 1].score
            for index in range(len(result.candidates) - 1)
        )
        assert all(candidate.evidence for candidate in result.candidates)
        serialized = result.as_dict()
        assert serialized["best_score"] == result.best_score
        assert serialized["candidates"] == [
            candidate.as_dict() for candidate in result.candidates
        ]
        expected_intent = str(pair["intent_id"])
        expected_function = str(pair["expected_function_id"])
        correct = bool(
            result.candidates
            and result.candidates[0].intent_id == expected_intent
            and result.candidates[0].terminal_function == expected_function
        )
        top_one_correct += int(correct)
        if result.admitted:
            admitted += 1
            admitted_correct += int(correct)
            assert result.reason == "precision_gate_passed"
            assert not result.negated

    assert admitted >= int(contract["minimum_development_admissions"])
    assert admitted_correct / admitted >= float(contract["minimum_admitted_precision"])

    for goal in controls["negation_controls"]:
        result = retriever.retrieve(str(goal), limit=5)
        assert result.negated is True
        assert result.admitted is False
        assert result.reason == "negation_requires_resolution"

    for goal in controls["generic_controls"]:
        result = retriever.retrieve(str(goal), limit=5)
        assert result.admitted is False

    # Cached and uncached traversal order must be exactly deterministic.
    reverse_results = [
        traced_retriever.retrieve(goal, limit=5)
        for _pair, _locale, goal in reversed(authored_cases)
    ]
    assert first_results == list(reversed(reverse_results))
    assert retriever.retrieve("", limit=5).reason == "empty_query"
    for index in range(retriever.config.cache_size + 17):
        retriever.retrieve(f"bounded cache probe {index}", limit=3)
    assert len(retriever._cache) <= retriever.config.cache_size

    p95_index = max(0, round(0.95 * len(timings) + 0.499999) - 1)
    warm_p95 = sorted(timings)[p95_index]
    assert warm_p95 < float(contract["maximum_warm_p95_seconds"])
    print(
        "navigation goal char retrieval checks ok: "
        f"catalog={stats.catalog_version} candidates={stats.candidate_count} "
        f"features={stats.feature_count} postings={stats.posting_count} "
        f"top1={top_one_correct}/{len(authored_cases)} "
        f"admitted_precision={admitted_correct}/{admitted} "
        f"build={build_seconds:.4f}s warm_p95={warm_p95:.4f}s "
        f"warm_mean={statistics.mean(timings):.4f}s "
        f"peak_bytes={peak_bytes} estimated_index_bytes={stats.estimated_index_bytes}"
    )


if __name__ == "__main__":
    main()
