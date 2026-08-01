from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "Evaluate-NavigationV16Isolated.py"
CANONICAL_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
SOURCE_PATH = (
    ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-evidence-systems-v16.json"
)


def _load_orchestrator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "evaluate_navigation_v16_isolated", SCRIPT_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load V16 isolated evaluator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    orchestrator = _load_orchestrator()
    canonical_before = _file_sha(CANONICAL_PATH)
    observed: dict[str, object] = {}
    stateful_call_count = 0

    def fake_goal_evaluator(*, catalog_path: Path, fixture_paths: list[Path]) -> dict[str, Any]:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        fixture = json.loads(fixture_paths[0].read_text(encoding="utf-8"))
        observed["temporary_catalog"] = catalog_path
        observed["temporary_goal_fixture"] = fixture_paths[0]
        observed["temporary_equivalence"] = catalog_path.with_name(
            "function-equivalence.v1.json"
        )
        assert catalog_path != CANONICAL_PATH
        assert catalog["catalog_version"] == "16.0.0"
        assert len(catalog["functions"]) == 3118
        assert len(catalog["intents"]) == 2900
        assert catalog["alias_context_overrides"]["version"] == "1.1.0"
        assert Path(observed["temporary_equivalence"]).read_bytes() == (
            CANONICAL_PATH.with_name("function-equivalence.v1.json").read_bytes()
        )
        assert fixture["catalog_derived"] is False
        assert fixture["tuning_allowed"] is False
        assert len(fixture["cases"]) == 840
        return {
            "total": 840,
            "correct": 630,
            "accuracy": 0.75,
            "generic_count": 90,
            "generic_rate": 0.107143,
            "mean_confidence": 0.8125,
            # These intentionally sensitive values prove that orchestration
            # drops detailed evaluator output before persistence.
            "failures": [
                {
                    "case_id": "SECRET_CASE_MARKER",
                    "goal_text": "SECRET_GOAL_MARKER",
                    "details": "SECRET_FAILURE_MARKER",
                }
            ],
            "confusions": [
                {
                    "expected_intent": "SECRET_EXPECTED_MARKER",
                    "actual_intent": "SECRET_ACTUAL_MARKER",
                    "count": 210,
                }
            ],
            "intent_results": {"SECRET_INTENT_MARKER": {"total": 1}},
        }

    def fake_case_loader(path: Path, *, split: str) -> list[dict[str, object]]:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        assert fixture["catalog_derived"] is False
        assert fixture["tuning_allowed"] is False
        if split == "independent_evidence_systems_v16_routable":
            observed["temporary_routable_fixture"] = path
            assert fixture["evaluation_role"] == "routable_goal_and_terminal_stop"
            assert len(fixture["cases"]) == 840
            assert all(len(case["goal_text"]) <= 500 for case in fixture["cases"])
            assert all(
                case["steps"][0]["expected"]["action"] == "stop"
                for case in fixture["cases"]
            )
            assert all(case["intent_role"] == "destination" for case in fixture["cases"])
            return [{"opaque": True} for _ in range(840)]
        assert split == "independent_evidence_systems_v16_abstention_safety"
        observed["temporary_abstention_fixture"] = path
        assert (
            fixture["evaluation_role"]
            == "abstention_safety_only_goal_accuracy_excluded"
        )
        assert len(fixture["cases"]) == 120
        assert all(len(case["goal_text"]) <= 500 for case in fixture["cases"])
        assert all(
            case["steps"][0]["expected"]["action"] == "no_click"
            for case in fixture["cases"]
        )
        assert all(
            case["intent_role"] == "guarded_candidate_context_only"
            and case["intent_id"] != "__abstain__"
            for case in fixture["cases"]
        )
        return [{"opaque": True} for _ in range(120)]

    def fake_stateful_evaluator(**kwargs: Any) -> dict[str, Any]:
        nonlocal stateful_call_count
        stateful_call_count += 1
        assert kwargs["total_intents"] == 2900
        assert kwargs["total_functions"] == 3118
        assert len(kwargs["intent_universe"]) == 2900
        assert len(kwargs["function_universe"]) == 3118
        assert len(kwargs["cases"]) == 960
        return {
            "splits": {
                "independent_evidence_systems_v16_routable": {
                    "split": "independent_evidence_systems_v16_routable",
                    "case_count": 840,
                    "case_success_count": 630,
                    "case_failure_count": 210,
                    "case_success_rate": 0.75,
                    "goal_interpretation_total": 840,
                    "goal_interpretation_correct": 630,
                    "goal_interpretation_accuracy": 0.75,
                    "independent_goal_interpretation_total": 840,
                    "independent_goal_interpretation_correct": 630,
                    "independent_goal_interpretation_accuracy": 0.75,
                    "gold_stage_count": 840,
                    "stage_count": 840,
                    "attempted_stage_count": 840,
                    "skipped_stage_count": 0,
                    "attempted_stage_rate": 1.0,
                    "expected_action_total": 840,
                    "expected_action_correct": 630,
                    "expected_action_accuracy": 0.75,
                    "destination_total": 840,
                    "destination_accuracy": 0.75,
                    "unsafe_click_rate": 0.0,
                    "wrong_click_rate": 0.25,
                    "mean_clicks_per_case": 0.0,
                    "mean_scrolls_per_case": 0.0,
                    "mean_backs_per_case": 0.0,
                    "mean_latency_ms": 1.5,
                    "time_to_destination_p50_ms": 1200.0,
                    "time_to_destination_p90_ms": 1200.0,
                    "decision_time_p50_ms": 1.0,
                    "decision_time_p90_ms": 2.0,
                },
                "independent_evidence_systems_v16_abstention_safety": {
                    "split": "independent_evidence_systems_v16_abstention_safety",
                    "case_count": 120,
                    "case_success_count": 120,
                    "case_failure_count": 0,
                    "case_success_rate": 1.0,
                    "gold_stage_count": 120,
                    "stage_count": 120,
                    "attempted_stage_count": 120,
                    "skipped_stage_count": 0,
                    "attempted_stage_rate": 1.0,
                    "expected_action_total": 120,
                    "expected_action_correct": 120,
                    "expected_action_accuracy": 1.0,
                    "safe_stop_total": 120,
                    "safe_stop_correct": 120,
                    "safe_stop_accuracy": 1.0,
                    "unsafe_click_rate": 0.0,
                    "wrong_click_rate": 0.0,
                    "mean_clicks_per_case": 0.0,
                    "mean_scrolls_per_case": 0.0,
                    "mean_backs_per_case": 0.0,
                    "mean_latency_ms": 1.5,
                    "time_to_destination_p50_ms": 1200.0,
                    "time_to_destination_p90_ms": 1200.0,
                    "decision_time_p50_ms": 1.0,
                    "decision_time_p90_ms": 2.0,
                },
            },
            "failures": [
                {
                    "split": "independent_evidence_systems_v16_routable",
                    "failure_type": "goal_interpretation_failure",
                    "case_id": "SECRET_STATEFUL_CASE_MARKER",
                    "goal_text": "SECRET_STATEFUL_GOAL_MARKER",
                    "details": "SECRET_STATEFUL_FAILURE_MARKER",
                }
                for _ in range(105)
            ]
            + [
                {
                    "split": "independent_evidence_systems_v16_routable",
                    "failure_type": "destination_missed",
                    "case_id": "SECRET_RESULT_MARKER",
                    "goal_text": "SECRET_ABSTENTION_GOAL_MARKER",
                    "details": "SECRET_ABSTENTION_FAILURE_MARKER",
                }
                for _ in range(105)
            ],
            "case_results": [{"case_id": "SECRET_ABSTENTION_RESULT_MARKER"}],
            "suggestions": [{"value": "SECRET_ABSTENTION_SUGGESTION_MARKER"}],
        }

    report = orchestrator.run_isolated_v16_evaluation(
        canonical_catalog_path=CANONICAL_PATH,
        source_fixture_path=SOURCE_PATH,
        goal_evaluator=fake_goal_evaluator,
        stateful_evaluator=fake_stateful_evaluator,
        case_loader=fake_case_loader,
        gate=True,
        minimum_goal_accuracy=0.70,
        minimum_stateful_goal_accuracy=0.60,
        minimum_stateful_success=0.70,
    )

    assert _file_sha(CANONICAL_PATH) == canonical_before
    assert stateful_call_count == 1
    assert report["canonical_materialized"] is False
    assert report["runtime_source_provenance"]["algorithm"] == "sha256"
    assert report["runtime_source_provenance"]["source_count"] == 9
    assert report["runtime_source_provenance"]["unchanged"] is True
    assert (
        report["runtime_source_provenance"]["before"]
        == report["runtime_source_provenance"]["after"]
    )
    assert all(
        len(value) == 64
        for value in report["runtime_source_provenance"]["before"].values()
    )
    assert report["canonical_v15"]["unchanged"] is True
    assert report["canonical_v15"]["file_sha256_before"] == canonical_before
    assert report["canonical_v15"]["file_sha256_after"] == canonical_before
    assert report["isolated_v16"]["catalog_version"] == "16.0.0"
    assert report["isolated_v16"]["functions"] == 3118
    assert report["isolated_v16"]["intents"] == 2900
    assert report["isolated_v16"]["domains"] == 191
    assert report["runtime_alias_context_overrides"]["version"] == "1.1.0"
    assert report["runtime_alias_context_overrides"]["regenerated_after_v16_append"] is True
    assert report["runtime_alias_context_overrides"]["constraints"] == {
        "aliases_added": 0,
        "goal_sentences_copied": 0,
        "app_names_added": 0,
        "coordinates_added": 0,
    }
    equivalence_path = CANONICAL_PATH.with_name("function-equivalence.v1.json")
    assert report["equivalence_overlay"] == {
        "filename": "function-equivalence.v1.json",
        "equivalence_version": "1.1.0",
        "equivalence_kind": "true_equivalent",
        "class_count": 10,
        "source_sha256_before": _file_sha(equivalence_path),
        "source_sha256_after": _file_sha(equivalence_path),
        "runtime_sibling_sha256": _file_sha(equivalence_path),
        "copied_beside_temporary_catalog": True,
        "source_unchanged": True,
    }
    assert report["sealed_fixture_projection"]["goal_case_count"] == 840
    assert report["sealed_fixture_projection"]["stateful_case_count"] == 960
    assert report["sealed_fixture_projection"]["intermediates_persisted"] is False
    assert (
        report["sealed_fixture_projection"]["goal_fixture_payload_sha256"]
        == "562c8615beba8f0a9579cf3e9c988c9b8ef24fc10de5b2ed50f36b2cc6be5c4b"
    )
    assert (
        report["sealed_fixture_projection"]["stateful_fixture_payload_sha256"]
        == "de887f458a71f6eb647a516625133329787f94c22c0b3e82306260a9f04542d3"
    )
    assert report["projection_safety"] == {
        "case_count": 960,
        "step_count": 960,
        "stop_count": 840,
        "no_click_count": 120,
        "zero_dangerous_clicks": 960,
        "zero_automated_final_presses": 960,
        "terminal_press_owner_user_count": 960,
    }
    assert report["abstention_scoring"] == {
        "intent_source": "sealed_unsafe_candidate_context_only",
        "execution_function": "safe_fallback_hub",
        "expected_action": "no_click",
        "authorizes_execution": False,
        "safety_only_case_count": 120,
        "goal_accuracy_included": False,
    }
    consumer_projection = report["stateful_consumer_projection"]
    assert consumer_projection["algorithm"] == "unicode_head_tail_v1"
    assert consumer_projection["maximum_goal_chars"] == 500
    assert consumer_projection["answer_fields_consulted"] is False
    assert consumer_projection["original_goal_evaluation_unchanged"] is True
    assert consumer_projection["routable"]["case_count"] == 840
    assert consumer_projection["abstention_safety"]["case_count"] == 120
    assert consumer_projection["total_compacted_case_count"] > 0
    assert consumer_projection["routable"]["maximum_consumer_chars"] <= 500
    assert consumer_projection["abstention_safety"]["maximum_consumer_chars"] <= 500
    assert report["goal_resolution"] == {
        "case_count": 840,
        "correct_count": 630,
        "incorrect_count": 210,
        "accuracy": 0.75,
        "generic_count": 90,
        "generic_rate": 0.107143,
        "mean_confidence": 0.8125,
        "failure_count": 210,
    }
    routable = report["stateful_navigation"]["routable"]
    abstention = report["stateful_navigation"]["abstention_safety"]
    combined = report["stateful_navigation"]["combined_safety"]
    assert routable["failure_counts_by_type"] == {
        "destination_missed": 105,
        "goal_interpretation_failure": 105,
    }
    assert routable["failure_count"] == 210
    assert routable["goal_interpretation_total"] == 840
    assert routable["goal_interpretation_accuracy"] == 0.75
    assert abstention["case_count"] == 120
    assert abstention["safe_stop_total"] == 120
    assert abstention["safe_stop_correct"] == 120
    assert abstention["safe_stop_accuracy"] == 1.0
    assert "goal_interpretation_accuracy" not in abstention
    assert combined == {
        "case_count": 960,
        "case_success_count": 750,
        "case_failure_count": 210,
        "case_success_rate": 0.78125,
        "stage_count": 960,
        "unsafe_click_rate": 0.0,
        "wrong_click_rate": 0.21875,
        "route_stop_case_count": 840,
        "abstention_no_click_case_count": 120,
        "abstention_safe_stop_accuracy": 1.0,
        "goal_accuracy_denominator": 840,
        "abstention_goal_accuracy_excluded_count": 120,
    }
    assert report["privacy_contract"] == {
        "aggregate_only": True,
        "goal_text_persisted": False,
        "case_identifiers_persisted": False,
        "failure_details_persisted": False,
        "confusions_persisted": False,
        "suggestions_persisted": False,
    }
    assert report["gate"]["passed"] is True
    assert report["gate"]["failure_reasons"] == []

    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for marker in (
        "SECRET_CASE_MARKER",
        "SECRET_GOAL_MARKER",
        "SECRET_FAILURE_MARKER",
        "SECRET_EXPECTED_MARKER",
        "SECRET_ACTUAL_MARKER",
        "SECRET_INTENT_MARKER",
        "SECRET_STATEFUL_CASE_MARKER",
        "SECRET_STATEFUL_GOAL_MARKER",
        "SECRET_STATEFUL_FAILURE_MARKER",
        "SECRET_RESULT_MARKER",
        "SECRET_SUGGESTION_MARKER",
        "SECRET_ABSTENTION_CASE_MARKER",
        "SECRET_ABSTENTION_GOAL_MARKER",
        "SECRET_ABSTENTION_FAILURE_MARKER",
        "SECRET_ABSTENTION_RESULT_MARKER",
        "SECRET_ABSTENTION_SUGGESTION_MARKER",
    ):
        assert marker not in serialized
    for forbidden_key in (
        '"goal_text"',
        '"case_id"',
        '"failures"',
        '"confusions"',
        '"intent_results"',
        '"case_results"',
        '"suggestions"',
    ):
        assert forbidden_key not in serialized

    # Temporary catalog and normalized fixtures must already be gone.
    assert not Path(observed["temporary_catalog"]).exists()
    assert not Path(observed["temporary_goal_fixture"]).exists()
    assert not Path(observed["temporary_routable_fixture"]).exists()
    assert not Path(observed["temporary_abstention_fixture"]).exists()
    assert not Path(observed["temporary_equivalence"]).exists()

    rejected = orchestrator._gate_failures(
        report,
        minimum_goal_accuracy=0.80,
        minimum_stateful_goal_accuracy=0.80,
        minimum_stateful_success=0.80,
    )
    assert rejected == [
        "goal resolution accuracy below threshold",
        "stateful goal interpretation accuracy below threshold",
        "stateful case success below threshold",
    ]

    print(
        json.dumps(
            {
                "result": "PASS",
                "canonical_unchanged": True,
                "isolated_catalog": {
                    "version": "16.0.0",
                    "functions": 3118,
                    "intents": 2900,
                    "domains": 191,
                },
                "goal_cases": 840,
                "stateful_cases": 960,
                "dangerous_clicks": 0,
                "automated_final_presses": 0,
                "aggregate_only": True,
                "intermediates_persisted": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
