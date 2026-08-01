from __future__ import annotations

import json
import shutil
import sys
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
for path in (API_ROOT, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.services.navigation_function_catalog import (  # noqa: E402
    GOAL_GOVERNANCE_BLOCKED_INTENT,
    NavigationFunctionCatalog,
)
from app.services.navigation_semantics import infer_goal_plan  # noqa: E402
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)
from navigation_catalog_v17_data import (  # noqa: E402
    EXPECTED_DOMAIN_COUNTS,
    GROUPS,
    REQUIRED_DOMAINS,
    V17_FUNCTIONS,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
)


V17_MARKER = "v17_public_case_operations"
ROLE_RECORD_STATE_KINDS = frozenset({"wrong_role", "wrong_record", "wrong_state"})
RECOVERY_KINDS = frozenset(
    {"disabled", "unavailable_offline", "wrong_role", "wrong_record_jurisdiction"}
)
REQUIRED_USER_OWNED_OPERATION_GROUPS = {
    "legal_submission": {
        "unemployment_insurance_case_services.weekly_certification_submit",
        "wage_hour_enforcement_ops.worker_complaint_submit",
    },
    "signature": {
        "student_financial_aid_services.fafsa_sign_submit",
        "student_financial_aid_services.master_promissory_note_sign",
    },
    "payment": {
        "driver_vehicle_licensing_services.reinstatement_fee_payment",
        "unemployment_insurance_case_services.payment_method_update",
        "wage_hour_enforcement_ops.resolution_payment_confirm",
    },
    "objection_or_appeal": {
        "consumer_credit_reporting_services.tradeline_dispute_create",
        "social_security_benefit_services.decision_appeal_request",
        "unemployment_insurance_case_services.determination_appeal_submit",
    },
    "ownership_change": {
        "disaster_assistance_case_services.home_occupancy_ownership_verify",
        "driver_vehicle_licensing_services.vehicle_title_transfer",
        "healthcare_provider_enrollment_ops.ownership_change_report",
    },
}


def _safe_hub_plan(
    catalog: NavigationFunctionCatalog,
    *,
    terminal_function: str,
    preferred_functions: tuple[tuple[str, float], ...],
    expected_hub: str,
) -> bool:
    if terminal_function != expected_hub or not preferred_functions:
        return False
    for function_id, _weight in preferred_functions:
        definition = catalog.function(function_id)
        if definition is None or definition.terminal or definition.state_changing:
            return False
    hub = catalog.function(expected_hub)
    return bool(
        hub is not None
        and hub.node_kind == "hub"
        and not hub.terminal
        and not hub.state_changing
        and hub.automation_policy == "safe_navigation"
        and hub.stop_policy == "continue"
    )


def _assert_safe_stop(
    catalog: NavigationFunctionCatalog,
    probe: dict[str, object],
) -> None:
    excluded = str(probe["excluded_function"])
    expected_hub = str(probe["allowed_fallback"])
    text = str(probe["text"])
    plan = catalog.plan_goal(text)
    consumer_plan = infer_goal_plan(text, catalog)
    assert plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT, probe
    assert plan.terminal_function != excluded, probe
    assert _safe_hub_plan(
        catalog,
        terminal_function=plan.terminal_function,
        preferred_functions=plan.preferred_functions,
        expected_hub=expected_hub,
    ), probe
    assert consumer_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT, probe
    assert consumer_plan.terminal_function == expected_hub, probe
    assert excluded in consumer_plan.avoid_functions, probe


def main() -> None:
    base = load_base_catalog()
    reviewed = merge_with_base(base)
    runtime_payload = apply_alias_context_overrides(
        strip_alias_context_overrides(reviewed)
    )
    assert runtime_payload["catalog_version"] == "17.0.0"
    assert len(runtime_payload["functions"]) == 3358
    assert len(runtime_payload["intents"]) == 3128
    assert len({str(item["domain"]) for item in runtime_payload["functions"]}) == 203

    governed_functions = [
        item
        for item in runtime_payload["functions"]
        if V17_MARKER in item.get("legacy_tags", [])
    ]
    assert len(governed_functions) == len(V17_FUNCTIONS) == 240
    functions_by_id = {
        str(item["function_id"]): item for item in governed_functions
    }
    hubs_by_domain = {
        str(item["domain"]): item
        for item in governed_functions
        if item.get("node_kind") == "hub"
    }
    assert set(hubs_by_domain) == set(REQUIRED_DOMAINS)
    assert {
        domain: sum(
            bool(item["terminal"]) and item["domain"] == domain
            for item in governed_functions
        )
        for domain in sorted(REQUIRED_DOMAINS)
    } == EXPECTED_DOMAIN_COUNTS

    v17_terminals = [item for item in governed_functions if item.get("terminal")]
    assert len(v17_terminals) == 228
    assert all(
        item["risk_level"] == "high"
        and item["automation_policy"] == "never_auto"
        and item["stop_policy"] == "before_action"
        and item["user_owned_final_press"] is True
        for item in v17_terminals
    )

    for operation, function_ids in REQUIRED_USER_OWNED_OPERATION_GROUPS.items():
        assert function_ids <= set(functions_by_id), operation
        for function_id in function_ids:
            source = functions_by_id[function_id]
            assert source["terminal"] is True, (operation, function_id)
            assert source["state_changing"] is True, (operation, function_id)
            assert source["automation_policy"] == "never_auto", (
                operation,
                function_id,
            )
            assert source["stop_policy"] == "before_action", (
                operation,
                function_id,
            )

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    assert (len(semantic), len(collisions), len(recovery), len(isolation)) == (
        1368,
        720,
        912,
        684,
    )

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        catalog_path = root / "function-catalog.v17.runtime.json"
        catalog_path.write_text(
            json.dumps(runtime_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        shutil.copyfile(
            ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json",
            root / "function-equivalence.v1.json",
        )
        catalog = NavigationFunctionCatalog(root / "runtime.sqlite", catalog_path)

        for operation, function_ids in REQUIRED_USER_OWNED_OPERATION_GROUPS.items():
            for function_id in function_ids:
                definition = catalog.function(function_id)
                assert definition is not None, (operation, function_id)
                assert definition.automation_policy == "never_auto", (
                    operation,
                    function_id,
                )
                assert definition.stop_policy == "before_action", (
                    operation,
                    function_id,
                )
                assert definition.state_changing is True, (operation, function_id)

        positive_by_domain: dict[str, dict[str, object]] = {}
        missing_jurisdiction_by_domain: dict[str, dict[str, object]] = {}
        for probe in semantic:
            target = probe.get("expected_function") or probe.get("excluded_function")
            if target is None or str(target) not in functions_by_id:
                continue
            domain = str(functions_by_id[str(target)]["domain"])
            if probe["kind"] == "positive" and probe["locale"] == "en-US":
                positive_by_domain.setdefault(domain, probe)
            elif probe["kind"] == "missing_jurisdiction":
                missing_jurisdiction_by_domain.setdefault(domain, probe)
        assert set(positive_by_domain) == set(REQUIRED_DOMAINS)
        assert set(missing_jurisdiction_by_domain) == set(REQUIRED_DOMAINS)

        positive_plans = {}
        for domain, probe in positive_by_domain.items():
            plan = catalog.plan_goal(str(probe["text"]))
            assert plan.terminal_function == probe["expected_function"], probe
            positive_plans[domain] = plan
        for probe in missing_jurisdiction_by_domain.values():
            _assert_safe_stop(catalog, probe)

        collision_by_domain: dict[str, dict[str, object]] = {}
        for probe in collisions:
            target = str(probe["expected_function"])
            domain = str(functions_by_id[target]["domain"])
            collision_by_domain.setdefault(domain, probe)
        assert set(collision_by_domain) == set(REQUIRED_DOMAINS)
        for probe in collision_by_domain.values():
            plan = catalog.plan_goal(str(probe["text"]))
            assert plan.terminal_function == probe["expected_function"], probe

        # Every V17 domain declares a reviewed nearest existing domain.  Mixing
        # that neighbor into otherwise positive evidence must not select either
        # consequential terminal; ambiguity is safer than guessing a program.
        groups_by_domain = {str(group.domain): group for group in GROUPS}
        assert set(groups_by_domain) == set(REQUIRED_DOMAINS)
        for domain, group in groups_by_domain.items():
            neighboring_hub = catalog.function(str(group.avoid_root))
            assert neighboring_hub is not None, (domain, group.avoid_root)
            bounded = catalog.apply_governance_evidence_boundary(
                result=positive_plans[domain],
                evidence_text=(
                    f"{hubs_by_domain[domain]['name_en']} and "
                    f"{neighboring_hub.name_en}: different program wrong record"
                ),
            )
            assert bounded.intent == GOAL_GOVERNANCE_BLOCKED_INTENT, domain
            assert (
                (
                    not bounded.terminal_function
                    and not bounded.preferred_functions
                )
                or _safe_hub_plan(
                    catalog,
                    terminal_function=bounded.terminal_function,
                    preferred_functions=bounded.preferred_functions,
                    expected_hub=str(hubs_by_domain[domain]["function_id"]),
                )
            ), domain

        isolation_by_domain_kind: dict[tuple[str, str], dict[str, object]] = {}
        for probe in isolation:
            excluded = str(probe["excluded_function"])
            domain = str(functions_by_id[excluded]["domain"])
            key = (domain, str(probe["kind"]))
            isolation_by_domain_kind.setdefault(key, probe)
        assert set(isolation_by_domain_kind) == set(
            product(REQUIRED_DOMAINS, ROLE_RECORD_STATE_KINDS)
        )
        for probe in isolation_by_domain_kind.values():
            _assert_safe_stop(catalog, probe)

        recovery_by_domain_kind: dict[tuple[str, str], dict[str, object]] = {}
        for probe in recovery:
            excluded = str(probe["excluded_function"])
            domain = str(functions_by_id[excluded]["domain"])
            key = (domain, str(probe["kind"]))
            recovery_by_domain_kind.setdefault(key, probe)
        assert set(recovery_by_domain_kind) == set(
            product(REQUIRED_DOMAINS, RECOVERY_KINDS)
        )
        for probe in recovery_by_domain_kind.values():
            assert probe["required_policy"] == "never_auto"
            assert probe["required_stop_policy"] == "before_action"
            assert probe["required_user_owned_final_press"] is True
            _assert_safe_stop(catalog, probe)

        ordered_domains = sorted(REQUIRED_DOMAINS)
        for index, domain in enumerate(ordered_domains):
            other = ordered_domains[(index + 1) % len(ordered_domains)]
            bounded = catalog.apply_governance_evidence_boundary(
                result=positive_plans[domain],
                evidence_text=(
                    f"{hubs_by_domain[domain]['name_en']} and "
                    f"{hubs_by_domain[other]['name_en']}: wrong role "
                    "different person or case record"
                ),
            )
            assert bounded.intent == GOAL_GOVERNANCE_BLOCKED_INTENT, domain
            assert not bounded.terminal_function, domain
            assert not bounded.preferred_functions, domain

    print(
        json.dumps(
            {
                "result": "PASS",
                "domains": len(REQUIRED_DOMAINS),
                "semantic_positive": len(positive_by_domain),
                "semantic_negative": len(missing_jurisdiction_by_domain),
                "collision": len(collision_by_domain),
                "near_domain_negative": len(REQUIRED_DOMAINS),
                "role_record_state_safe_stop": len(isolation_by_domain_kind),
                "recovery_safe_stop": len(recovery_by_domain_kind),
                "cross_domain_isolation": len(REQUIRED_DOMAINS),
                "user_owned_operation_groups": len(
                    REQUIRED_USER_OWNED_OPERATION_GROUPS
                ),
                "user_owned_operation_targets": sum(
                    len(values)
                    for values in REQUIRED_USER_OWNED_OPERATION_GROUPS.values()
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
