from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
FIXTURE_PATH = (
    ROOT / "fixtures/navigation/db-gym/independent-evidence-systems-v16.json"
)
ADAPTER_PATH = SCRIPTS / "Normalize-NavigationEvidenceFixture.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

import navigation_catalog_v16_data as v16  # noqa: E402
from app.schemas import UniversalNavigationObserveResponse  # noqa: E402
from app.services import navigation_db_gym as db_gym  # noqa: E402
from app.services.navigation_semantics import GoalPlan  # noqa: E402


EXPECTED_GOAL_OUTPUT_SHA256 = (
    "562c8615beba8f0a9579cf3e9c988c9b8ef24fc10de5b2ed50f36b2cc6be5c4b"
)
EXPECTED_STATEFUL_OUTPUT_SHA256 = (
    "de887f458a71f6eb647a516625133329787f94c22c0b3e82306260a9f04542d3"
)


def _load_adapter() -> Any:
    spec = importlib.util.spec_from_file_location(
        "normalize_navigation_evidence_fixture", ADAPTER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load evidence fixture adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _reseal_source(source: dict[str, Any]) -> None:
    source["metadata"]["cases_payload_sha256"] = _digest(source["cases"])
    payload = dict(source)
    payload.pop("canonical_json_sha256", None)
    source["canonical_json_sha256"] = _digest(payload)


def _expect_rejection(
    adapter: Any,
    operation: Callable[..., dict[str, Any]],
    *,
    source: dict[str, Any],
    catalog: dict[str, Any],
    expected_fragment: str | None = None,
) -> None:
    try:
        operation(source=source, catalog=catalog)
    except adapter.EvidenceFixtureValidationError as error:
        if expected_fragment is not None:
            assert expected_fragment in str(error), str(error)
        return
    raise AssertionError("tampered evidence projection was accepted")


def _expect_deep_fixture_rejection(
    adapter: Any,
    operation: Callable[..., dict[str, Any]],
    *,
    source: dict[str, Any],
    catalog: dict[str, Any],
    expected_fragment: str,
) -> None:
    """Exercise a semantic validator after deliberately accepting test seals."""

    old_canonical = adapter.EXPECTED_CANONICAL_JSON_SHA256
    old_cases = adapter.EXPECTED_CASES_PAYLOAD_SHA256
    adapter.EXPECTED_CANONICAL_JSON_SHA256 = source["canonical_json_sha256"]
    adapter.EXPECTED_CASES_PAYLOAD_SHA256 = source["metadata"][
        "cases_payload_sha256"
    ]
    try:
        _expect_rejection(
            adapter,
            operation,
            source=source,
            catalog=catalog,
            expected_fragment=expected_fragment,
        )
    finally:
        adapter.EXPECTED_CANONICAL_JSON_SHA256 = old_canonical
        adapter.EXPECTED_CASES_PAYLOAD_SHA256 = old_cases


def main() -> None:
    adapter = _load_adapter()
    source = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    base = v16.load_base_catalog()
    assert base["catalog_version"] == "15.0.0"
    base_snapshot = copy.deepcopy(base)
    catalog = v16.merge_with_base(base)
    assert base == base_snapshot
    del base_snapshot
    assert catalog["catalog_version"] == "16.0.0"
    assert len(catalog["functions"]) == 3118
    assert len(catalog["intents"]) == 2900
    assert len({str(item["domain"]) for item in catalog["functions"]}) == 191
    assert (
        adapter._digest(
            adapter._v16_catalog_structure(catalog["functions"], catalog["intents"])
        )
        == adapter.EXPECTED_V16_CATALOG_STRUCTURE_SHA256
    )

    # Goal normalization contains only the 840 routable cases and uses catalog
    # intent identifiers.  We deliberately never inspect or print goal text.
    goals = adapter.normalize_goal_fixture(source=source, catalog=catalog)
    assert goals["split"] == "independent_evidence_systems_v16"
    assert goals["frozen"] is True
    assert goals["catalog_derived"] is False
    assert goals["tuning_allowed"] is False
    assert goals["source_fixture_sha256"] == adapter.EXPECTED_CANONICAL_JSON_SHA256
    assert goals["source_cases_sha256"] == adapter.EXPECTED_CASES_PAYLOAD_SHA256
    assert goals["projection_contract"] == {
        "source_case_count": 960,
        "routable_case_count": 840,
        "excluded_abstention_count": 120,
    }
    assert len(goals["cases"]) == 840
    catalog_intent_ids = {str(item["intent_id"]) for item in catalog["intents"]}
    assert all(case["intent_id"] in catalog_intent_ids for case in goals["cases"])
    assert all(case["intent_id"] != adapter.ABSTAIN_INTENT_ID for case in goals["cases"])
    assert all(case["tuning_allowed"] is False for case in goals["cases"])
    assert Counter(case["locale"] for case in goals["cases"]) == {
        "ko-KR": 420,
        "en-US": 420,
    }
    assert [case["case_id"] for case in goals["cases"]] == [
        case["case_id"]
        for case in source["cases"]
        if case["expected"]["decision"] == "route"
    ]
    goal_output_sha256 = _digest(goals)
    assert goal_output_sha256 == EXPECTED_GOAL_OUTPUT_SHA256, goal_output_sha256

    # Stateful normalization preserves all cases and makes the safety boundary
    # executable only as stop/no-click.  It never creates a final press.
    stateful = adapter.normalize_stateful_fixture(source=source, catalog=catalog)
    assert stateful["split"] == "independent_evidence_systems_v16"
    assert stateful["frozen"] is True
    assert stateful["catalog_derived"] is False
    assert stateful["tuning_allowed"] is False
    assert stateful["source_fixture_sha256"] == adapter.EXPECTED_CANONICAL_JSON_SHA256
    assert stateful["source_cases_sha256"] == adapter.EXPECTED_CASES_PAYLOAD_SHA256
    assert len(stateful["cases"]) == 960
    assert [case["case_id"] for case in stateful["cases"]] == [
        f"v16-independent-{index:04d}" for index in range(1, 961)
    ]
    steps = [case["steps"][0] for case in stateful["cases"]]
    assert Counter(step["stage"] for step in steps) == {
        "destination": 840,
        "hub_abstention": 120,
    }
    assert Counter(step["expected"]["action"] for step in steps) == {
        "stop": 840,
        "no_click": 120,
    }
    assert stateful["abstention_scoring_contract"] == {
        "intent_source": "sealed_unsafe_candidate_context_only",
        "execution_function": "safe_fallback_hub",
        "expected_action": "no_click",
        "authorizes_execution": False,
    }
    assert all(case["intent_id"] in catalog_intent_ids for case in stateful["cases"])
    assert all(case["intent_id"] != adapter.ABSTAIN_INTENT_ID for case in stateful["cases"])
    assert Counter(case["intent_role"] for case in stateful["cases"]) == {
        "destination": 840,
        "guarded_candidate_context_only": 120,
    }
    assert all(step["expected"]["dangerous_clicks"] == 0 for step in steps)
    assert all(step["expected"]["automated_final_presses"] == 0 for step in steps)
    assert all(step["expected"]["terminal_press_owner"] == "user" for step in steps)
    function_ids = {str(item["function_id"]) for item in catalog["functions"]}
    assert all(step["expected"]["function_id"] in function_ids for step in steps)
    source_by_id = {str(case["case_id"]): case for case in source["cases"]}
    intent_by_terminal = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in catalog["intents"]
        if item.get("terminal_function")
    }
    for projected in stateful["cases"]:
        raw = source_by_id[str(projected["case_id"])]
        raw_expected = raw["expected"]
        projected_expected = projected["steps"][0]["expected"]
        assert projected["goal_text"] == raw["goal"]
        assert projected["independent_expected"] == raw_expected
        assert projected["independent_surface"] == raw["surface"]
        assert projected["independent_evidence"] == raw["evidence"]
        if raw_expected["decision"] == "abstain":
            unsafe_candidate_id = str(raw_expected["unsafe_candidate_id"])
            assert projected["intent_id"] == intent_by_terminal[unsafe_candidate_id]
            assert projected["intent_role"] == "guarded_candidate_context_only"
            assert projected_expected["action"] == "no_click"
            assert projected_expected["function_id"] == (
                f"{raw_expected['safe_fallback_domain']}.hub"
            )
        else:
            function_id = str(raw_expected["function_id"])
            assert projected["intent_id"] == intent_by_terminal[function_id]
            assert projected["intent_role"] == "destination"
            assert projected_expected["action"] == "stop"
            assert projected_expected["function_id"] == function_id
    assert stateful["projection_contract"] == {
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
    }
    stateful_output_sha256 = _digest(stateful)
    assert stateful_output_sha256 == EXPECTED_STATEFUL_OUTPUT_SHA256, (
        stateful_output_sha256
    )

    # Exercise the actual DB Gym scoring consumer with one sealed abstention.
    # A perfect guarded decision must be capable of earning both goal and
    # no-click credit; the old reserved intent made that structurally impossible.
    with TemporaryDirectory(prefix="egl-v16-evidence-consumer-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        stateful_path = temporary_root / "stateful.json"
        catalog_path = temporary_root / "catalog.json"
        adapter._atomic_write_json(stateful_path, stateful)
        adapter._atomic_write_json(catalog_path, catalog)
        loaded = db_gym.load_fixed_cases(stateful_path, split=stateful["split"])
        assert len(loaded) == 960
        assert Counter(step.expected_action for case in loaded for step in case.steps) == {
            "stop": 840,
            "no_click": 120,
        }
        assert all(case.intent_id in catalog_intent_ids for case in loaded)
        guarded_case = next(
            case for case in loaded if case.steps[0].expected_action == "no_click"
        )

        original_infer = db_gym.infer_goal_plan
        original_observe = db_gym.observe_universal_navigation

        def perfect_guarded_plan(_goal_text: str, _catalog: Any = None) -> GoalPlan:
            return GoalPlan(
                intent=guarded_case.intent_id,
                preferred_functions=(),
                terminal_function=guarded_case.steps[0].expected_function,
                confidence=1.0,
            )

        def perfect_guarded_observation(
            request: Any, **_kwargs: Any
        ) -> UniversalNavigationObserveResponse:
            return UniversalNavigationObserveResponse.model_validate(
                {
                    "request_id": request.request_id,
                    "session_id": request.session_id,
                    "status": "no_safe_action",
                    "screen_fingerprint": "us_0123456789abcdef",
                    "goal_interpretation": guarded_case.intent_id,
                    "decision_mode": "deterministic_fallback",
                    "phase": "stopped",
                    "candidates": [],
                    "recommendation": None,
                    "graph_update": {
                        "screen_created": False,
                        "actions_created": 0,
                        "transition_recorded": False,
                        "known_screen_count": 1,
                        "known_transition_count": 0,
                    },
                    "automation": {
                        "action": "none",
                        "safe_to_execute": False,
                        "selected_element_id": None,
                        "selected_element_key": None,
                        "selected_label": None,
                        "reason": "guarded benchmark abstention",
                        "action_count": 0,
                        "action_limit": 40,
                        "elapsed_seconds": 0.0,
                        "timeout_seconds": 120,
                    },
                    "warnings": [],
                }
            )

        try:
            db_gym.infer_goal_plan = perfect_guarded_plan
            db_gym.observe_universal_navigation = perfect_guarded_observation
            consumer_report = db_gym.evaluate_navigation_db_gym(
                cases=[guarded_case],
                catalog_path=catalog_path,
                total_intents=len(catalog["intents"]),
                total_functions=len(catalog["functions"]),
                intent_universe=catalog_intent_ids,
                function_universe=function_ids,
            )
        finally:
            db_gym.infer_goal_plan = original_infer
            db_gym.observe_universal_navigation = original_observe
        consumer_summary = consumer_report["summary"]
        assert consumer_summary["goal_interpretation_accuracy"] == 1.0
        assert consumer_summary["case_success_rate"] == 1.0
        assert consumer_summary["safe_stop_accuracy"] == 1.0
        assert consumer_summary["unsafe_click_rate"] == 0.0
        assert consumer_report["failures"] == []

    # CLI paths can never alias either immutable input.  Atomic replacement
    # also leaves a previous output intact if serialization fails.
    with TemporaryDirectory(prefix="egl-v16-evidence-paths-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        source_path = temporary_root / "source.json"
        catalog_path = temporary_root / "catalog.json"
        output_path = temporary_root / "output.json"
        source_path.write_text("{}", encoding="utf-8")
        catalog_path.write_text("{}", encoding="utf-8")
        for paths, expected_fragment in (
            ((source_path, catalog_path, source_path), "output path must not alias"),
            ((source_path, catalog_path, catalog_path), "output path must not alias"),
            ((source_path, source_path, output_path), "source and catalog paths"),
        ):
            try:
                adapter._resolve_distinct_cli_paths(*paths)
            except adapter.EvidenceFixtureValidationError as error:
                assert expected_fragment in str(error), str(error)
            else:
                raise AssertionError("CLI input/output alias was accepted")
        adapter._atomic_write_json(output_path, {"generation": 1})
        assert json.loads(output_path.read_text(encoding="utf-8")) == {"generation": 1}
        try:
            adapter._atomic_write_json(output_path, {"not_serializable": object()})
        except TypeError:
            pass
        else:
            raise AssertionError("non-serializable output was accepted")
        assert json.loads(output_path.read_text(encoding="utf-8")) == {"generation": 1}
        assert list(temporary_root.glob(".output.json.*.tmp")) == []

    # The two pinned seals reject mutations before projection.
    changed_outer_seal = copy.deepcopy(source)
    changed_outer_seal["canonical_json_sha256"] = "0" * 64
    for operation in (
        adapter.normalize_goal_fixture,
        adapter.normalize_stateful_fixture,
    ):
        _expect_rejection(
            adapter,
            operation,
            source=changed_outer_seal,
            catalog=catalog,
            expected_fragment="canonical seal is not pinned",
        )

    changed_cases_seal = copy.deepcopy(source)
    changed_cases_seal["metadata"]["cases_payload_sha256"] = "1" * 64
    payload = dict(changed_cases_seal)
    payload.pop("canonical_json_sha256", None)
    changed_cases_seal["canonical_json_sha256"] = _digest(payload)
    original_canonical_seal = adapter.EXPECTED_CANONICAL_JSON_SHA256
    adapter.EXPECTED_CANONICAL_JSON_SHA256 = changed_cases_seal[
        "canonical_json_sha256"
    ]
    try:
        for operation in (
            adapter.normalize_goal_fixture,
            adapter.normalize_stateful_fixture,
        ):
            _expect_rejection(
                adapter,
                operation,
                source=changed_cases_seal,
                catalog=catalog,
                expected_fragment="cases seal is not pinned",
            )
    finally:
        adapter.EXPECTED_CANONICAL_JSON_SHA256 = original_canonical_seal

    # Resealed mutations temporarily receive matching test-only pins so every
    # deeper semantic branch is proved independently of the outer seal.
    semantic_mutations: list[
        tuple[Callable[[dict[str, Any]], None], str]
    ] = []

    def remove_case_and_reseal(value: dict[str, Any]) -> None:
        value["cases"].pop()
        _reseal_source(value)

    semantic_mutations.append((remove_case_and_reseal, "must contain 960 cases"))

    def change_case_id_and_reseal(value: dict[str, Any]) -> None:
        value["cases"][0]["case_id"] = "v16-independent-tampered"
        _reseal_source(value)

    semantic_mutations.append((change_case_id_and_reseal, "case identifiers differ"))

    def allow_tuning_and_reseal(value: dict[str, Any]) -> None:
        value["metadata"]["tuning_allowed"] = True
        _reseal_source(value)

    semantic_mutations.append((allow_tuning_and_reseal, "metadata tuning_allowed differs"))

    def change_expected_id_and_reseal(value: dict[str, Any]) -> None:
        route = next(
            case for case in value["cases"] if case["expected"]["decision"] == "route"
        )
        route["expected"]["function_id"] = "tampered.terminal"
        route["expected"]["domain"] = "tampered"
        route["expected"]["acceptable_top3"] = ["tampered.terminal"]
        _reseal_source(value)

    semantic_mutations.append((change_expected_id_and_reseal, "unknown terminal identifier"))

    def change_safety_and_reseal(value: dict[str, Any]) -> None:
        value["cases"][0]["expected"]["dangerous_clicks"] = 1
        _reseal_source(value)

    semantic_mutations.append((change_safety_and_reseal, "final-action safety contract differs"))

    def change_evidence_cardinality_and_reseal(value: dict[str, Any]) -> None:
        value["cases"][0]["evidence"]["screen_cues"].pop()
        _reseal_source(value)

    semantic_mutations.append(
        (change_evidence_cardinality_and_reseal, "evidence cardinality differs")
    )

    for mutate, expected_fragment in semantic_mutations:
        tampered_source = copy.deepcopy(source)
        mutate(tampered_source)
        for operation in (
            adapter.normalize_goal_fixture,
            adapter.normalize_stateful_fixture,
        ):
            _expect_deep_fixture_rejection(
                adapter,
                operation,
                source=tampered_source,
                catalog=catalog,
                expected_fragment=expected_fragment,
            )

    # Catalog rejection covers the prior V15 generation, partial V16 appends,
    # same-count identifier substitution, and terminal safety substitution.
    _expect_rejection(
        adapter,
        adapter.normalize_goal_fixture,
        source=source,
        catalog=base,
    )

    partial_functions = copy.deepcopy(catalog)
    partial_functions["functions"].pop()
    _expect_rejection(
        adapter,
        adapter.normalize_stateful_fixture,
        source=source,
        catalog=partial_functions,
    )
    del partial_functions

    partial_intents = copy.deepcopy(catalog)
    partial_intents["intents"].pop()
    _expect_rejection(
        adapter,
        adapter.normalize_goal_fixture,
        source=source,
        catalog=partial_intents,
    )
    del partial_intents

    changed_id = copy.deepcopy(catalog)
    v16_terminal = next(
        item
        for item in changed_id["functions"]
        if item.get("terminal") is True
        and item.get("domain") in set(adapter.EXPECTED_DOMAINS)
    )
    v16_terminal["function_id"] = str(v16_terminal["function_id"]) + "_tampered"
    _expect_rejection(
        adapter,
        adapter.normalize_stateful_fixture,
        source=source,
        catalog=changed_id,
    )
    del changed_id

    changed_safety = copy.deepcopy(catalog)
    v16_terminal = next(
        item
        for item in changed_safety["functions"]
        if item.get("terminal") is True
        and item.get("domain") in set(adapter.EXPECTED_DOMAINS)
    )
    v16_terminal["automation_policy"] = "auto"
    _expect_rejection(
        adapter,
        adapter.normalize_goal_fixture,
        source=source,
        catalog=changed_safety,
    )
    del changed_safety

    # Swap direct targets while retaining the generated intent-ID form.  The
    # unchanged routes now name different owners and must fail closed.
    changed_mapping = copy.deepcopy(catalog)
    mapping_intents = [
        item
        for item in changed_mapping["intents"]
        if str(item.get("terminal_function", "")).split(".", 1)[0]
        in set(adapter.EXPECTED_DOMAINS)
    ][:2]
    mapping_intents[0]["terminal_function"], mapping_intents[1]["terminal_function"] = (
        mapping_intents[1]["terminal_function"],
        mapping_intents[0]["terminal_function"],
    )
    mapping_intents[0]["intent_id"], mapping_intents[1]["intent_id"] = (
        mapping_intents[1]["intent_id"],
        mapping_intents[0]["intent_id"],
    )
    _expect_rejection(
        adapter,
        adapter.normalize_goal_fixture,
        source=source,
        catalog=changed_mapping,
        expected_fragment="route candidates disagree",
    )
    del changed_mapping

    changed_rule_owner = copy.deepcopy(catalog)
    rule_intents = [
        item
        for item in changed_rule_owner["intents"]
        if str(item.get("terminal_function", "")).split(".", 1)[0]
        in set(adapter.EXPECTED_DOMAINS)
    ][:2]
    rule_intents[0]["goal_rules"][0]["terminal_function"] = rule_intents[1][
        "terminal_function"
    ]
    _expect_rejection(
        adapter,
        adapter.normalize_stateful_fixture,
        source=source,
        catalog=changed_rule_owner,
        expected_fragment="rule candidates disagree",
    )
    del changed_rule_owner

    # A safety-structure mutation that leaves candidate ownership consistent is
    # rejected by the exact structural projection seal itself.
    changed_structure = copy.deepcopy(catalog)
    structural_intent = next(
        item
        for item in changed_structure["intents"]
        if str(item.get("terminal_function", "")).split(".", 1)[0]
        in set(adapter.EXPECTED_DOMAINS)
    )
    structural_intent["terminal_condition"]["stop_policy"] = "tampered"
    _expect_rejection(
        adapter,
        adapter.normalize_goal_fixture,
        source=source,
        catalog=changed_structure,
        expected_fragment="structural projection differs",
    )
    del changed_structure

    changed_prior_id = copy.deepcopy(catalog)
    prior_function = next(
        item
        for item in changed_prior_id["functions"]
        if item.get("domain") not in set(adapter.EXPECTED_DOMAINS)
    )
    prior_function["function_id"] = str(prior_function["function_id"]) + "_tampered"
    _expect_rejection(
        adapter,
        adapter.normalize_stateful_fixture,
        source=source,
        catalog=changed_prior_id,
    )
    del changed_prior_id

    print(
        json.dumps(
            {
                "result": "PASS",
                "source_cases": 960,
                "goal_cases": 840,
                "stateful_cases": 960,
                "safe_stops": 840,
                "no_click_abstentions": 120,
                "dangerous_clicks": 0,
                "automated_final_presses": 0,
                "source_fixture_sha256": adapter.EXPECTED_CANONICAL_JSON_SHA256,
                "source_cases_sha256": adapter.EXPECTED_CASES_PAYLOAD_SHA256,
                "goal_output_sha256": EXPECTED_GOAL_OUTPUT_SHA256,
                "stateful_output_sha256": EXPECTED_STATEFUL_OUTPUT_SHA256,
                "v16_catalog_structure_sha256": adapter.EXPECTED_V16_CATALOG_STRUCTURE_SHA256,
                "fixture_tamper_probes": 4 + len(semantic_mutations) * 2,
                "catalog_tamper_probes": 9,
                "consumer_abstention_cases": 1,
                "cli_alias_probes": 3,
                "atomic_write_failure_probes": 1,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
