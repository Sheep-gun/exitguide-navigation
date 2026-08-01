import importlib.util
import json
import sys
from collections import Counter
from dataclasses import asdict
from urllib.parse import urlparse
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_db_gym import (
    FAILURE_TYPES,
    GymFailure,
    build_db_suggestions,
    evaluate_navigation_db_gym,
    generate_catalog_route_cases,
    generate_synthetic_dimension_cases,
    _pairwise_dimension_coverage,
    load_fixed_cases,
    load_synthetic_dimension_spec,
    synthetic_dimension_universe,
)
from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.navigation_semantics import infer_goal_plan


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
GYM_ROOT = ROOT / "fixtures" / "navigation" / "db-gym"
sys.path.insert(0, str(ROOT / "scripts"))

from navigation_catalog_v14_data import (  # noqa: E402
    V14_FUNCTIONS,
    V14_INTENTS,
)
from navigation_catalog_v15_data import (  # noqa: E402
    V15_FUNCTIONS,
    V15_INTENTS,
    load_base_catalog as load_v15_base_catalog,
    merge_with_base as merge_v15_with_base,
)


def _load_authority_adapter():
    adapter_path = ROOT / "scripts" / "Normalize-NavigationAuthorityFixture.py"
    spec = importlib.util.spec_from_file_location(
        "navigation_authority_fixture_adapter", adapter_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load authority fixture adapter: {adapter_path}")
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    return adapter


def _normalized_v14_payload(
    fixture: dict[str, object],
    catalog: dict[str, object],
) -> dict[str, object]:
    terminal_intents = {
        str(item["terminal_function"]): str(item["intent_id"])
        for item in catalog["intents"]
    }
    domain_intents: dict[str, str] = {}
    for terminal_id, intent_id in terminal_intents.items():
        domain_intents.setdefault(terminal_id.split(".", 1)[0], intent_id)
    cases = []
    for case in fixture["cases"]:
        route_id = str(case["expected"]["route_id"])
        domain = str(case["domain"])
        hub_case = route_id.endswith(".hub")
        cases.append(
            {
                "case_id": str(case["case_id"]),
                "intent_id": "generic_navigation" if hub_case else terminal_intents[route_id],
                "goal_text": str(case["goal"]),
                "locale": "ko-KR" if case.get("locale") == "ko" else "en-US",
                "user_state": "authorized_role_scoped",
                "tags": [str(case["slice"]), str(case["class"]), "independent_v14"],
                "source_kind": "fixed_independent",
                "tuning_allowed": False,
                "steps": [
                    {
                        "step_id": "review-boundary",
                        "screen_title": str(case["ui"]["surface"]),
                        "stage": "hub_abstention" if hub_case else "destination",
                        "elements": [],
                        "expected": {
                            "action": "no_click" if hub_case else "stop",
                            "label": None,
                            "function_id": route_id,
                        },
                    }
                ],
            }
        )
    return {
        "split": "independent_institutional_systems_v14",
        "frozen": True,
        "catalog_derived": False,
        "tuning_allowed": False,
        "cases": cases,
    }


def main() -> None:
    expected_failures = {
        "goal_interpretation_failure",
        "alias_gap",
        "missing_gateway",
        "semantic_ambiguity",
        "advertisement_decoy",
        "premature_destination",
        "destination_missed",
        "safe_menu_not_explored",
        "unnecessary_scroll",
        "wrong_backtrack",
        "wrong_menu",
        "unsafe_action_attempt",
        "route_reuse_failure",
        "expected_scroll_missed",
        "expected_back_missed",
    }
    assert FAILURE_TYPES == expected_failures
    protected_failure = GymFailure(
        case_id="immutable-holdout",
        split="immutable",
        goal_text="must not enter a proposal",
        step_id="screen-1",
        failure_type="goal_interpretation_failure",
        expected_action="stop",
        expected_label="Protected label",
        expected_function="account.entry",
        actual_action="none",
        actual_label=None,
        actual_phase="exploring",
        goal_interpretation="generic_navigation",
        details="Evaluation-only evidence.",
        tuning_allowed=False,
    )
    assert build_db_suggestions([protected_failure]) == []
    assert build_db_suggestions([
        GymFailure(**{**asdict(protected_failure), "tuning_allowed": True})
    ])

    holdout_payload = json.loads((GYM_ROOT / "holdout.v1.json").read_text(encoding="utf-8"))
    assert holdout_payload["frozen"] is True
    holdout = load_fixed_cases(GYM_ROOT / "holdout.v1.json", split="holdout")
    adversarial = load_fixed_cases(GYM_ROOT / "adversarial.v1.json", split="adversarial")
    public_web_payload = json.loads((GYM_ROOT / "public-web.v1.json").read_text(encoding="utf-8"))
    public_web = load_fixed_cases(GYM_ROOT / "public-web.v1.json", split="public_web")
    insurance_payload = json.loads((GYM_ROOT / "public-insurance.v1.json").read_text(encoding="utf-8"))
    public_insurance = load_fixed_cases(GYM_ROOT / "public-insurance.v1.json", split="public_insurance")
    productivity_payload = json.loads((GYM_ROOT / "public-productivity-system.v1.json").read_text(encoding="utf-8"))
    public_productivity = load_fixed_cases(
        GYM_ROOT / "public-productivity-system.v1.json",
        split="public_productivity_system",
    )
    independent_payload = json.loads((GYM_ROOT / "independent-core.v2.json").read_text(encoding="utf-8"))
    independent_core = load_fixed_cases(GYM_ROOT / "independent-core.v2.json", split="independent_core")
    optional_alias_path = GYM_ROOT / "alias-collision-adversarial.v2.json"
    alias_payload = (
        json.loads(optional_alias_path.read_text(encoding="utf-8"))
        if optional_alias_path.is_file()
        else None
    )
    alias_collision = (
        load_fixed_cases(optional_alias_path, split="alias_collision_adversarial")
        if optional_alias_path.is_file()
        else []
    )
    coverage_path = GYM_ROOT / "independent-coverage.v2.json"
    coverage_payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    independent_coverage = load_fixed_cases(coverage_path, split="independent_coverage")
    recovery_path = GYM_ROOT / "independent-recovery.v2.json"
    recovery_payload = json.loads(recovery_path.read_text(encoding="utf-8"))
    independent_recovery = load_fixed_cases(recovery_path, split="independent_recovery")
    long_tail_path = GYM_ROOT / "independent-long-tail-v3.json"
    long_tail_payload = json.loads(long_tail_path.read_text(encoding="utf-8"))
    independent_long_tail = load_fixed_cases(long_tail_path, split="independent_long_tail_v3")
    broad_v4_path = GYM_ROOT / "independent-broad-services-v4.json"
    broad_v4_payload = json.loads(broad_v4_path.read_text(encoding="utf-8"))
    independent_broad_v4 = load_fixed_cases(broad_v4_path, split="independent_broad_services_v4")
    service_gaps_v5_path = GYM_ROOT / "independent-service-gaps-v5.json"
    service_gaps_v5_payload = json.loads(service_gaps_v5_path.read_text(encoding="utf-8"))
    independent_service_gaps_v5 = load_fixed_cases(
        service_gaps_v5_path,
        split="independent_service_gaps_v5",
    )
    open_world_v6_path = GYM_ROOT / "independent-open-world-v6.json"
    open_world_v6_payload = json.loads(open_world_v6_path.read_text(encoding="utf-8"))
    independent_open_world_v6 = load_fixed_cases(
        open_world_v6_path,
        split="independent_open_world_v6",
    )
    long_tail_v7_path = GYM_ROOT / "independent-long-tail-v7.json"
    long_tail_v7_payload = json.loads(long_tail_v7_path.read_text(encoding="utf-8"))
    independent_long_tail_v7 = load_fixed_cases(
        long_tail_v7_path,
        split="independent_long_tail_v7",
    )
    enterprise_ops_v8_path = GYM_ROOT / "independent-enterprise-ops-v8.json"
    enterprise_ops_v8_payload = json.loads(enterprise_ops_v8_path.read_text(encoding="utf-8"))
    independent_enterprise_ops_v8 = load_fixed_cases(
        enterprise_ops_v8_path,
        split="independent_enterprise_ops_v8",
    )
    cross_domain_v9_path = GYM_ROOT / "independent-cross-domain-v9.json"
    cross_domain_v9_payload = json.loads(cross_domain_v9_path.read_text(encoding="utf-8"))
    independent_cross_domain_v9 = load_fixed_cases(
        cross_domain_v9_path,
        split="independent_cross_domain_v9",
    )
    operational_v10_path = GYM_ROOT / "independent-operational-v10.json"
    operational_v10_payload = json.loads(operational_v10_path.read_text(encoding="utf-8"))
    independent_operational_v10 = load_fixed_cases(
        operational_v10_path,
        split="independent_operational_v10",
    )
    critical_ops_v11_path = GYM_ROOT / "independent-critical-ops-v11.json"
    critical_ops_v11_payload = json.loads(
        critical_ops_v11_path.read_text(encoding="utf-8")
    )
    independent_critical_ops_v11 = load_fixed_cases(
        critical_ops_v11_path,
        split="independent_critical_ops_v11",
    )
    specialized_ops_v12_path = GYM_ROOT / "independent-specialized-ops-v12.json"
    specialized_ops_v12_payload = json.loads(
        specialized_ops_v12_path.read_text(encoding="utf-8")
    )
    independent_specialized_ops_v12 = load_fixed_cases(
        specialized_ops_v12_path,
        split="independent_specialized_ops_v12",
    )
    regulated_systems_v13_path = GYM_ROOT / "independent-regulated-systems-v13.json"
    regulated_systems_v13_payload = json.loads(
        regulated_systems_v13_path.read_text(encoding="utf-8")
    )
    independent_regulated_systems_v13 = load_fixed_cases(
        regulated_systems_v13_path,
        split="independent_regulated_systems_v13",
    )
    assert len(holdout) >= 10
    assert len(adversarial) >= 12
    assert len(public_web) >= 19
    assert sum(len(case.steps) for case in public_web) >= 70
    assert len(public_insurance) >= 27
    assert sum(len(case.steps) for case in public_insurance) >= 45
    assert productivity_payload["frozen"] is True
    assert productivity_payload["catalog_derived"] is False
    assert len(public_productivity) == 55
    assert sum(len(case.steps) for case in public_productivity) == 176
    assert independent_payload["frozen"] is True
    assert independent_payload["catalog_derived"] is False
    assert len(independent_core) == 70
    assert sum(len(case.steps) for case in independent_core) == 210
    assert all(case.source_kind == "fixed_independent" for case in independent_core)
    if alias_payload is not None:
        assert alias_payload["frozen"] is True
        assert alias_payload["catalog_derived"] is False
        assert len(alias_collision) >= 75
        assert all(case.source_kind == "fixed_independent" for case in alias_collision)
    assert coverage_payload["frozen"] is True
    assert coverage_payload["catalog_derived"] is False
    assert len(independent_coverage) == 79
    assert sum(len(case.steps) for case in independent_coverage) == 266
    assert all(case.source_kind == "fixed_independent" for case in independent_coverage)
    assert recovery_payload["frozen"] is True
    assert recovery_payload["catalog_derived"] is False
    assert len(independent_recovery) == 75
    assert sum(len(case.steps) for case in independent_recovery) == 159
    assert all(case.source_kind == "fixed_independent" for case in independent_recovery)
    assert long_tail_payload["frozen"] is True
    assert long_tail_payload["catalog_derived"] is False
    assert long_tail_payload["tuning_allowed"] is True
    assert len(independent_long_tail) == 221
    assert sum(len(case.steps) for case in independent_long_tail) == 663
    assert all(case.source_kind == "fixed_independent" for case in independent_long_tail)
    assert broad_v4_payload["frozen"] is True
    assert broad_v4_payload["catalog_derived"] is False
    assert broad_v4_payload["tuning_allowed"] is True
    assert len(independent_broad_v4) == 163
    assert sum(len(case.steps) for case in independent_broad_v4) == 652
    assert all(case.source_kind == "fixed_independent" for case in independent_broad_v4)
    assert service_gaps_v5_payload["frozen"] is True
    assert service_gaps_v5_payload["catalog_derived"] is False
    assert service_gaps_v5_payload["tuning_allowed"] is False
    assert len(independent_service_gaps_v5) == 136
    assert sum(len(case.steps) for case in independent_service_gaps_v5) == 544
    assert all(case.source_kind == "fixed_independent" for case in independent_service_gaps_v5)
    assert all(not case.tuning_allowed for case in independent_service_gaps_v5)
    assert open_world_v6_payload["frozen"] is True
    assert open_world_v6_payload["catalog_derived"] is False
    assert open_world_v6_payload["tuning_allowed"] is False
    assert open_world_v6_payload["independent_accuracy_claim"] is True
    assert len(independent_open_world_v6) == 113
    assert sum(len(case.steps) for case in independent_open_world_v6) == 452
    assert all(case.source_kind == "fixed_independent" for case in independent_open_world_v6)
    assert all(not case.tuning_allowed for case in independent_open_world_v6)
    assert long_tail_v7_payload["frozen"] is True
    assert long_tail_v7_payload["catalog_derived"] is False
    assert long_tail_v7_payload["tuning_allowed"] is False
    assert long_tail_v7_payload["independent_accuracy_claim"] is True
    assert len(independent_long_tail_v7) == 120
    assert sum(len(case.steps) for case in independent_long_tail_v7) == 480
    assert all(case.source_kind == "fixed_independent" for case in independent_long_tail_v7)
    assert all(not case.tuning_allowed for case in independent_long_tail_v7)
    assert enterprise_ops_v8_payload["frozen"] is True
    assert enterprise_ops_v8_payload["catalog_derived"] is False
    assert enterprise_ops_v8_payload["tuning_allowed"] is False
    assert enterprise_ops_v8_payload["independent_accuracy_claim"] is True
    assert len(independent_enterprise_ops_v8) == 276
    assert sum(len(case.steps) for case in independent_enterprise_ops_v8) == 1104
    assert all(case.source_kind == "fixed_independent" for case in independent_enterprise_ops_v8)
    assert all(not case.tuning_allowed for case in independent_enterprise_ops_v8)
    assert cross_domain_v9_payload["frozen"] is True
    assert cross_domain_v9_payload["catalog_derived"] is False
    assert cross_domain_v9_payload["tuning_allowed"] is False
    assert cross_domain_v9_payload["independent_accuracy_claim"] is True
    assert cross_domain_v9_payload["source_kind"] == "fixed_independent"
    assert "frozen non-tuning holdout" in cross_domain_v9_payload["independence"]["label_access_policy"]
    assert cross_domain_v9_payload["coverage_contract"]["exact_cases"] == 368
    assert cross_domain_v9_payload["coverage_contract"]["exact_steps"] == 1472
    assert cross_domain_v9_payload["safety_contract"]["dangerous_expected_clicks"] == 0
    assert cross_domain_v9_payload["safety_contract"]["final_press_owner"] == "user"
    assert len(independent_cross_domain_v9) == 368
    assert sum(len(case.steps) for case in independent_cross_domain_v9) == 1472
    assert all(case.source_kind == "fixed_independent" for case in independent_cross_domain_v9)
    assert all(not case.tuning_allowed for case in independent_cross_domain_v9)
    assert operational_v10_payload["frozen"] is True
    assert operational_v10_payload["catalog_derived"] is False
    assert operational_v10_payload["tuning_allowed"] is False
    assert operational_v10_payload["independent_accuracy_claim"] is True
    assert operational_v10_payload["source_kind"] == "fixed_independent"
    assert operational_v10_payload["coverage_contract"]["exact_cases"] == 218
    assert operational_v10_payload["coverage_contract"]["exact_steps"] == 872
    assert operational_v10_payload["coverage_contract"]["minimum_recovery_probes"] == 436
    assert operational_v10_payload["safety_contract"]["dangerous_expected_clicks"] == 0
    assert operational_v10_payload["safety_contract"]["final_press_owner"] == "user"
    assert len(independent_operational_v10) == 218
    assert sum(len(case.steps) for case in independent_operational_v10) == 872
    assert all(case.source_kind == "fixed_independent" for case in independent_operational_v10)
    assert all(not case.tuning_allowed for case in independent_operational_v10)
    assert critical_ops_v11_payload["frozen"] is True
    assert critical_ops_v11_payload["catalog_derived"] is False
    assert critical_ops_v11_payload["tuning_allowed"] is False
    assert critical_ops_v11_payload["independent_accuracy_claim"] is True
    assert critical_ops_v11_payload["source_kind"] == "fixed_independent"
    assert critical_ops_v11_payload["coverage_contract"]["exact_cases"] == 230
    assert critical_ops_v11_payload["coverage_contract"]["exact_steps"] == 920
    assert critical_ops_v11_payload["coverage_contract"]["exact_functions"] == 242
    assert critical_ops_v11_payload["coverage_contract"]["minimum_homonym_decoys"] == 230
    assert critical_ops_v11_payload["safety_contract"]["dangerous_expected_clicks"] == 0
    assert critical_ops_v11_payload["safety_contract"]["final_press_owner"] == "user"
    assert len(independent_critical_ops_v11) == 230
    assert sum(len(case.steps) for case in independent_critical_ops_v11) == 920
    assert all(case.source_kind == "fixed_independent" for case in independent_critical_ops_v11)
    assert all(not case.tuning_allowed for case in independent_critical_ops_v11)
    assert specialized_ops_v12_payload["frozen"] is True
    assert specialized_ops_v12_payload["catalog_derived"] is False
    assert specialized_ops_v12_payload["tuning_allowed"] is False
    assert specialized_ops_v12_payload["independent_accuracy_claim"] is True
    assert specialized_ops_v12_payload["source_kind"] == "fixed_independent"
    assert specialized_ops_v12_payload["coverage_contract"]["exact_cases"] == 240
    assert specialized_ops_v12_payload["coverage_contract"]["exact_steps"] == 960
    assert specialized_ops_v12_payload["coverage_contract"]["exact_intents"] == 240
    assert specialized_ops_v12_payload["coverage_contract"]["exact_functions"] == 252
    assert specialized_ops_v12_payload["coverage_contract"]["exact_steps_per_case"] == 4
    assert specialized_ops_v12_payload["coverage_contract"]["minimum_homonym_decoys"] == 480
    assert specialized_ops_v12_payload["safety_contract"]["dangerous_expected_clicks"] == 0
    assert specialized_ops_v12_payload["safety_contract"]["terminal_automation_policy"] == "never_auto"
    assert specialized_ops_v12_payload["safety_contract"]["terminal_stop_policy"] == "before_action"
    assert specialized_ops_v12_payload["safety_contract"]["final_press_owner"] == "user"
    assert len(independent_specialized_ops_v12) == 240
    assert sum(len(case.steps) for case in independent_specialized_ops_v12) == 960
    assert all(case.source_kind == "fixed_independent" for case in independent_specialized_ops_v12)
    assert all(not case.tuning_allowed for case in independent_specialized_ops_v12)
    assert regulated_systems_v13_payload["frozen"] is True
    assert regulated_systems_v13_payload["catalog_derived"] is False
    assert regulated_systems_v13_payload["tuning_allowed"] is False
    assert regulated_systems_v13_payload["independent_accuracy_claim"] is True
    assert regulated_systems_v13_payload["source_kind"] == "fixed_independent"
    assert regulated_systems_v13_payload["coverage_contract"]["exact_cases"] == 240
    assert regulated_systems_v13_payload["coverage_contract"]["exact_steps"] == 960
    assert regulated_systems_v13_payload["coverage_contract"]["exact_intents"] == 240
    assert regulated_systems_v13_payload["coverage_contract"]["exact_functions"] == 252
    assert regulated_systems_v13_payload["coverage_contract"]["exact_steps_per_case"] == 4
    assert regulated_systems_v13_payload["coverage_contract"]["minimum_homonym_decoys"] == 480
    assert regulated_systems_v13_payload["safety_contract"]["dangerous_expected_clicks"] == 0
    assert regulated_systems_v13_payload["safety_contract"]["terminal_automation_policy"] == "never_auto"
    assert regulated_systems_v13_payload["safety_contract"]["terminal_stop_policy"] == "before_action"
    assert regulated_systems_v13_payload["safety_contract"]["final_press_owner"] == "user"
    assert len(independent_regulated_systems_v13) == 240
    assert sum(len(case.steps) for case in independent_regulated_systems_v13) == 960
    assert all(case.source_kind == "fixed_independent" for case in independent_regulated_systems_v13)
    assert all(not case.tuning_allowed for case in independent_regulated_systems_v13)
    assert public_web_payload["review_policy"].startswith("Official publisher documentation only")
    assert public_web_payload["frozen"] is True
    assert public_web_payload["catalog_derived"] is False
    allowed_source_hosts = {
        "support.google.com",
        "help.netflix.com",
        "support.spotify.com",
        "www.facebook.com",
        "support.tiktok.com",
        "help.x.com",
        "help.uber.com",
        "www.linkedin.com",
        "support.reddithelp.com",
        "support.discord.com",
        "help.snapchat.com",
    }
    source_ids = {str(source["source_id"]) for source in public_web_payload["sources"]}
    assert all(urlparse(str(source["url"])).hostname in allowed_source_hosts for source in public_web_payload["sources"])
    assert all(str(item["source_id"]) in source_ids for item in public_web_payload["cases"])
    assert all("official_help" in case.tags for case in public_web)
    allowed_insurance_hosts = {
        "www.kbinsure.co.kr",
        "insight.kbinsure.co.kr",
        "www.samsungfire.com",
        "www.idbins.com",
        "www.hi.co.kr",
        "m.hi.co.kr",
        "www.kyobo.com",
        "app.kyobo.com",
        "www.nhis.or.kr",
    }
    insurance_source_ids = {str(source["source_id"]) for source in insurance_payload["sources"]}
    assert insurance_payload["frozen"] is True
    assert insurance_payload["catalog_derived"] is False
    assert all(urlparse(str(source["url"])).hostname in allowed_insurance_hosts for source in insurance_payload["sources"])
    assert all(str(item["source_id"]) in insurance_source_ids for item in insurance_payload["cases"])
    assert all("official_help" in case.tags and "insurance" in case.tags for case in public_insurance)
    all_fixed = (
        holdout
        + adversarial
        + public_web
        + public_insurance
        + public_productivity
        + independent_core
        + alias_collision
        + independent_coverage
        + independent_recovery
        + independent_long_tail
        + independent_broad_v4
        + independent_service_gaps_v5
        + independent_open_world_v6
        + independent_long_tail_v7
        + independent_enterprise_ops_v8
        + independent_cross_domain_v9
        + independent_operational_v10
        + independent_critical_ops_v11
        + independent_specialized_ops_v12
        + independent_regulated_systems_v13
    )
    ids = [case.case_id for case in all_fixed]
    assert len(ids) == len(set(ids))
    assert all(case.steps for case in all_fixed)
    assert all(step.expected_action in {"click", "scroll_forward", "back", "stop", "no_click"} for case in all_fixed for step in case.steps)

    gold = json.loads((GYM_ROOT / "real-device-gold.v1.json").read_text(encoding="utf-8"))
    assert gold["split"] == "real_device_gold"
    assert "app_package" in gold["required_fields"]
    assert "verified_by" in gold["required_fields"]
    assert gold["cases"] == []

    source = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert source["catalog_version"] == "15.0.0"
    assert len(source["intents"]) == 2660
    assert len(source["functions"]) == 2866
    source_intents = {str(item["intent_id"]) for item in source["intents"]}
    pre_v14_source_intents = source_intents.difference(
        {
            *(str(item["intent_id"]) for item in V14_INTENTS),
            *(str(item["intent_id"]) for item in V15_INTENTS),
        }
    )
    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(Path(temporary_directory) / "functions.sqlite", CATALOG_PATH)
        generated = generate_catalog_route_cases(
            catalog=catalog,
            catalog_source_path=CATALOG_PATH,
            variants_per_intent=2,
        )
        assert {case.intent_id for case in generated} == source_intents
        assert len(generated) == len(source_intents) * 2
        for case in generated:
            assert case.split == "catalog_generated"
            assert case.source_kind == "catalog_self_generated"
            plan = infer_goal_plan(case.goal_text, catalog)
            assert plan.intent == case.intent_id, (case.case_id, plan.intent, case.intent_id)
            assert (
                catalog.canonical_function_id(case.steps[-1].expected_function)
                == plan.terminal_function
            )
            assert case.steps[-1].expected_action == "stop"
            assert not any(element.dangerous and element.label == step.expected_label for step in case.steps for element in step.elements)

        known_functions = {str(item["function_id"]) for item in source["functions"]}
        pre_v14_known_functions = known_functions.difference(
            {
                *(str(item["function_id"]) for item in V14_FUNCTIONS),
                *(str(item["function_id"]) for item in V15_FUNCTIONS),
            }
        )
        assert all(case.intent_id in source_intents for case in public_web)
        assert all(step.expected_function in known_functions for case in public_web for step in case.steps)
        assert all(case.intent_id in source_intents for case in public_insurance)
        assert all(step.expected_function in known_functions for case in public_insurance for step in case.steps)
        assert all(case.intent_id in source_intents for case in public_productivity)
        assert all(step.expected_function in known_functions for case in public_productivity for step in case.steps)
        assert all(case.intent_id in source_intents for case in independent_core)
        assert all(step.expected_function in known_functions for case in independent_core for step in case.steps)
        assert all(case.intent_id in source_intents for case in alias_collision)
        assert all(step.expected_function in known_functions for case in alias_collision for step in case.steps)
        assert all(case.intent_id in source_intents for case in independent_long_tail)
        assert all(step.expected_function in known_functions for case in independent_long_tail for step in case.steps)
        assert all(case.intent_id in source_intents for case in independent_broad_v4)
        assert all(step.expected_function in known_functions for case in independent_broad_v4 for step in case.steps)
        assert all(case.intent_id in source_intents for case in independent_service_gaps_v5)
        assert all(
            step.expected_function in known_functions
            for case in independent_service_gaps_v5
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_open_world_v6)
        assert all(
            step.expected_function in known_functions
            for case in independent_open_world_v6
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_long_tail_v7)
        assert all(
            step.expected_function in known_functions
            for case in independent_long_tail_v7
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_enterprise_ops_v8)
        assert all(
            step.expected_function in known_functions
            for case in independent_enterprise_ops_v8
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_cross_domain_v9)
        assert all(
            step.expected_function in known_functions
            for case in independent_cross_domain_v9
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_operational_v10)
        assert all(
            step.expected_function in known_functions
            for case in independent_operational_v10
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_critical_ops_v11)
        assert all(
            step.expected_function in known_functions
            for case in independent_critical_ops_v11
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_specialized_ops_v12)
        assert all(
            step.expected_function in known_functions
            for case in independent_specialized_ops_v12
            for step in case.steps
        )
        assert all(case.intent_id in source_intents for case in independent_regulated_systems_v13)
        assert all(
            step.expected_function in known_functions
            for case in independent_regulated_systems_v13
            for step in case.steps
        )
        assert {case.intent_id for case in all_fixed} == pre_v14_source_intents
        assert {
            step.expected_function
            for case in all_fixed
            for step in case.steps
            if step.expected_function
        } == pre_v14_known_functions
        assert all(
            not (step.expected_action == "click" and any(
                element.dangerous and element.label == step.expected_label for element in step.elements
            ))
            for case in public_web
            for step in case.steps
        )
        assert all(
            not (step.expected_action == "click" and any(
                element.dangerous and element.label == step.expected_label for element in step.elements
            ))
            for case in public_insurance
            for step in case.steps
        )
        guarded_insurance_functions = {
            "insurance.claim.entry",
            "insurance.premium.payment",
            "insurance.certificate.issue",
            "insurance.loan.entry",
            "insurance.contract.cancel.entry",
            "insurance.accident.report",
            "insurance.emergency.roadside",
            "health_insurance.refund",
        }
        assert all(
            step.expected_action == "stop"
            for case in public_insurance
            for step in case.steps
            if step.expected_function in guarded_insurance_functions
        )

        dimension_spec = load_synthetic_dimension_spec(GYM_ROOT / "synthetic-dimensions.v1.json")
        dimension_universe = synthetic_dimension_universe(dimension_spec)
        synthetic = generate_synthetic_dimension_cases(spec=dimension_spec, max_cases=128)
        synthetic_again = generate_synthetic_dimension_cases(spec=dimension_spec, max_cases=128)
        assert len(synthetic) == 128
        assert [asdict(case) for case in synthetic] == [asdict(case) for case in synthetic_again]
        assert len({case.case_id for case in synthetic}) == len(synthetic)
        assert all(case.split == "synthetic_dimensions" for case in synthetic)
        assert all(case.source_kind == "synthetic_independent" for case in synthetic)
        assert {case.steps[0].expected_action for case in synthetic} == {
            "click",
            "scroll_forward",
            "back",
            "stop",
            "no_click",
        }
        assert {case.user_state for case in synthetic} == set(dimension_universe["user_state"])
        assert {case.locale for case in synthetic} == set(dimension_universe["locale"])
        assert {case.orientation for case in synthetic} == set(dimension_universe["orientation"])
        assert {case.device_model for case in synthetic} == set(dimension_universe["device_model"])
        assert {case.android_version for case in synthetic} == set(dimension_universe["android_version"])
        assert {case.steps[0].ui_surface for case in synthetic} == set(dimension_universe["ui_surface"])
        assert {case.steps[0].screen_state for case in synthetic} == set(dimension_universe["screen_state"])
        element_states = {
            tag.split(":", 1)[1]
            for case in synthetic
            for tag in case.tags
            if tag.startswith("element_state:")
        }
        assert element_states == set(dimension_universe["element_state"])
        pairwise = _pairwise_dimension_coverage(synthetic, dimension_universe)
        assert pairwise["coverage_rate"] == 1.0
        assert pairwise["missing_pair_count"] == 0
        assert any(
            element.checked is True
            for case in synthetic
            for element in case.steps[0].elements
        )
        assert any(
            element.selected
            for case in synthetic
            for element in case.steps[0].elements
        )
        assert any(
            element.content_description and not element.label
            for case in synthetic
            for element in case.steps[0].elements
        )

        broken_path = Path(temporary_directory) / "stateful-broken-route.json"
        broken_path.write_text(
            json.dumps(
                {
                    "cases": [
                        {
                            "case_id": "stateful-route-stops-after-wrong-step",
                            "intent_id": "account_registration",
                            "goal_text": "회원가입하고 싶어",
                            "locale": "ko-KR",
                            "user_state": "signed_out",
                            "tags": ["stateful_regression"],
                            "steps": [
                                {
                                    "step_id": "wrong-first-stage",
                                    "screen_title": "로그인",
                                    "stage": "account_gateway",
                                    "elements": [{"id": "login", "label": "로그인"}],
                                    "expected": {
                                        "action": "click",
                                        "label": "회원가입",
                                        "function_id": "auth.signup.entry"
                                    }
                                },
                                {
                                    "step_id": "must-not-be-shown",
                                    "screen_title": "회원가입",
                                    "stage": "destination",
                                    "elements": [{"id": "signup", "label": "회원가입"}],
                                    "expected": {
                                        "action": "stop",
                                        "label": "회원가입",
                                        "function_id": "auth.signup.entry"
                                    }
                                }
                            ]
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        broken_cases = load_fixed_cases(broken_path, split="stateful_regression")
        stateful_report = evaluate_navigation_db_gym(
            cases=broken_cases,
            catalog_path=CATALOG_PATH,
            total_intents=len(source_intents),
            total_functions=len(known_functions),
            dimension_universe=dimension_universe,
            intent_universe=source_intents,
            function_universe=known_functions,
        )
        stateful_summary = stateful_report["summary"]
        assert stateful_summary["gold_stage_count"] == 2
        assert stateful_summary["attempted_stage_count"] == 1
        assert stateful_summary["skipped_stage_count"] == 1
        assert stateful_summary["case_success_rate"] == 0.0
        assert stateful_summary["destination_total"] == 1
        assert stateful_summary["destination_accuracy"] == 0.0
        assert stateful_summary["independent_intent_coverage"] > 0.0
        assert stateful_summary["fixed_independent_intent_coverage"] > 0.0
        assert stateful_summary["synthetic_independent_intent_coverage"] == 0.0
        assert stateful_summary["catalog_generated_intent_coverage"] == 0.0
        assert stateful_summary["goal_interpretation_total"] == 1
        assert stateful_summary["independent_goal_interpretation_total"] == 1
        assert stateful_summary["catalog_generated_goal_interpretation_total"] == 0
        assert "account_registration" not in stateful_summary["independent_missing_intents"]
        assert "auth.signup.entry" not in stateful_summary["independent_missing_functions"]
        assert len(stateful_summary["independent_missing_intents"]) == len(source_intents) - 1
        assert stateful_report["case_results"][0]["status"] == "route_failed"
        assert stateful_report["case_results"][0]["failed_step_id"] == "wrong-first-stage"

        v14_fixture_payload = json.loads(
            (GYM_ROOT / "independent-institutional-systems-v14.json").read_text(encoding="utf-8")
        )
        projected_v14_catalog = load_v15_base_catalog(CATALOG_PATH)
        assert projected_v14_catalog["catalog_version"] == "14.0.0"
        assert len(projected_v14_catalog["intents"]) == 2420
        assert len(projected_v14_catalog["functions"]) == 2614
        normalized_v14_path = Path(temporary_directory) / "independent-institutional-systems-v14.json"
        normalized_v14_path.write_text(
            json.dumps(
                _normalized_v14_payload(v14_fixture_payload, projected_v14_catalog),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        independent_institutional_systems_v14 = load_fixed_cases(
            normalized_v14_path,
            split="independent_institutional_systems_v14",
        )
        assert len(independent_institutional_systems_v14) == 960
        assert sum(len(case.steps) for case in independent_institutional_systems_v14) == 960
        assert Counter(
            step.expected_action
            for case in independent_institutional_systems_v14
            for step in case.steps
        ) == {"stop": 840, "no_click": 120}
        assert all(not case.tuning_allowed for case in independent_institutional_systems_v14)
        projected_intents = {
            str(item["intent_id"]) for item in projected_v14_catalog["intents"]
        }
        projected_functions = {
            str(item["function_id"]) for item in projected_v14_catalog["functions"]
        }
        projected_fixed = all_fixed + independent_institutional_systems_v14
        assert {
            case.intent_id for case in projected_fixed if case.intent_id in projected_intents
        } == projected_intents
        assert {
            step.expected_function
            for case in projected_fixed
            for step in case.steps
            if step.expected_function
        } == projected_functions

        v15_fixture_payload = json.loads(
            (GYM_ROOT / "independent-authority-systems-v15.json").read_text(
                encoding="utf-8"
            )
        )
        projected_v15_catalog = merge_v15_with_base(projected_v14_catalog)
        assert projected_v15_catalog["catalog_version"] == "15.0.0"
        assert len(projected_v15_catalog["intents"]) == 2660
        assert len(projected_v15_catalog["functions"]) == 2866
        authority_adapter = _load_authority_adapter()
        normalized_v15_payload = authority_adapter.normalize_stateful_fixture(
            source=v15_fixture_payload,
            catalog=projected_v15_catalog,
        )
        assert normalized_v15_payload["split"] == "independent_authority_systems_v15"
        assert normalized_v15_payload["projection_contract"] == {
            "case_count": 960,
            "step_count": 960,
            "stop_count": 840,
            "no_click_count": 120,
            "zero_dangerous_clicks": 960,
            "zero_automated_final_presses": 960,
            "disposition_counts": {"route": 600, "retain_prior": 240, "abstain": 120},
            "source_stop_policy_counts": {"before_action": 600, "navigation_only": 360},
            "terminal_press_owner_user_count": 960,
        }
        normalized_v15_cases = list(normalized_v15_payload["cases"])
        assert len(normalized_v15_cases) == 960
        assert sum(len(case["steps"]) for case in normalized_v15_cases) == 960
        assert Counter(
            step["expected"]["action"]
            for case in normalized_v15_cases
            for step in case["steps"]
        ) == {"stop": 840, "no_click": 120}
        assert all(
            step["expected"]["dangerous_clicks"] == 0
            and step["expected"]["automated_final_presses"] == 0
            and step["expected"]["terminal_press_owner"] == "user"
            for case in normalized_v15_cases
            for step in case["steps"]
        )
        normalized_v15_path = (
            Path(temporary_directory) / "independent-authority-systems-v15.json"
        )
        normalized_v15_path.write_text(
            json.dumps(normalized_v15_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        independent_authority_systems_v15 = load_fixed_cases(
            normalized_v15_path,
            split="independent_authority_systems_v15",
        )
        assert len(independent_authority_systems_v15) == 960
        assert sum(len(case.steps) for case in independent_authority_systems_v15) == 960
        assert Counter(
            step.expected_action
            for case in independent_authority_systems_v15
            for step in case.steps
        ) == {"stop": 840, "no_click": 120}
        assert all(
            (case.intent_id == "__abstain__")
            == (case.steps[0].expected_action == "no_click")
            for case in independent_authority_systems_v15
        )
        assert all(not case.tuning_allowed for case in independent_authority_systems_v15)
        projected_v15_intents = {
            str(item["intent_id"]) for item in projected_v15_catalog["intents"]
        }
        projected_v15_functions = {
            str(item["function_id"]) for item in projected_v15_catalog["functions"]
        }
        projected_v15_fixed = projected_fixed + independent_authority_systems_v15
        assert {
            case.intent_id
            for case in projected_v15_fixed
            if case.intent_id in projected_v15_intents
        } == projected_v15_intents
        assert {
            step.expected_function
            for case in projected_v15_fixed
            for step in case.steps
            if step.expected_function
        } == projected_v15_functions

    print(
        f"navigation db gym schema checks ok: holdout={len(holdout)} "
        f"adversarial={len(adversarial)} public_web={len(public_web)} "
        f"public_insurance={len(public_insurance)} "
        f"independent_core={len(independent_core)} alias_collision={len(alias_collision)} "
        f"independent_coverage={len(independent_coverage)} "
        f"independent_recovery={len(independent_recovery)} "
        f"independent_long_tail={len(independent_long_tail)} "
        f"generated={len(generated)} synthetic={len(synthetic)} intents={len(source_intents)}"
    )


if __name__ == "__main__":
    main()
