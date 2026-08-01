from __future__ import annotations

import json
import shutil
import sys
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
from navigation_catalog_v20_data import (  # noqa: E402
    EXPECTED_DOMAIN_COUNTS,
    REQUIRED_DOMAINS,
    V20_FUNCTIONS,
    WITHIN_V20_COLLISIONS,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
)


V20_MARKER = "v20_claimant_family_services"
MISSING_KINDS = ("missing_role", "missing_asset", "missing_state", "missing_jurisdiction")
ISOLATION_KINDS = ("wrong_role", "wrong_record", "wrong_state")
RECOVERY_KINDS = ("disabled", "unavailable_offline", "wrong_role", "wrong_record_jurisdiction")


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


def _one_per_domain(
    values: tuple[dict[str, object], ...],
    *,
    target_key: str,
    predicate,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for value in values:
        if not predicate(value):
            continue
        target = str(value[target_key])
        domain = target.split(".", 1)[0]
        if domain in REQUIRED_DOMAINS:
            result.setdefault(domain, value)
    return result


def main() -> None:
    base = load_base_catalog()
    reviewed = merge_with_base(base)
    runtime_payload = apply_alias_context_overrides(strip_alias_context_overrides(reviewed))
    assert runtime_payload["catalog_version"] == "20.0.0"
    assert len(runtime_payload["functions"]) == 3869
    assert len(runtime_payload["intents"]) == 3610
    assert len({str(item["domain"]) for item in runtime_payload["functions"]}) == 232
    assert len(
        runtime_payload["inherited_reference_corrections_v20"]["corrections"]
    ) == 354
    runtime_function_ids = {
        str(item["function_id"]) for item in runtime_payload["functions"]
    }
    assert not {
        str(value)
        for intent in runtime_payload["intents"]
        for value in intent.get("avoid_functions", [])
        if str(value) not in runtime_function_ids
    }

    governed_functions = [
        item
        for item in runtime_payload["functions"]
        if V20_MARKER in item.get("legacy_tags", [])
    ]
    assert len(governed_functions) == len(V20_FUNCTIONS) == 136
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

    terminals = [item for item in governed_functions if item.get("terminal")]
    assert len(terminals) == 128
    assert all(
        item["risk_level"] == "high"
        and item["automation_policy"] == "never_auto"
        and item["stop_policy"] == "before_action"
        and item["user_owned_final_press"] is True
        for item in terminals
    )

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    assert (len(semantic), len(collisions), len(recovery), len(isolation)) == (
        768,
        118,
        512,
        384,
    )

    positive_by_domain = _one_per_domain(
        semantic,
        target_key="expected_function",
        predicate=lambda probe: probe["kind"] == "positive" and probe["locale"] == "en-US",
    )
    assert set(positive_by_domain) == set(REQUIRED_DOMAINS)

    ordered_domains = sorted(REQUIRED_DOMAINS)
    missing_by_domain: dict[str, dict[str, object]] = {}
    isolation_by_domain: dict[str, dict[str, object]] = {}
    recovery_by_domain: dict[str, dict[str, object]] = {}
    collision_by_domain: dict[str, dict[str, object]] = {}
    for index, domain in enumerate(ordered_domains):
        missing_kind = MISSING_KINDS[index % len(MISSING_KINDS)]
        isolation_kind = ISOLATION_KINDS[index % len(ISOLATION_KINDS)]
        recovery_kind = RECOVERY_KINDS[index % len(RECOVERY_KINDS)]
        missing_by_domain[domain] = next(
            probe
            for probe in semantic
            if probe["kind"] == missing_kind
            and str(probe["excluded_function"]).startswith(f"{domain}.")
        )
        isolation_by_domain[domain] = next(
            probe
            for probe in isolation
            if probe["kind"] == isolation_kind
            and str(probe["excluded_function"]).startswith(f"{domain}.")
        )
        recovery_by_domain[domain] = next(
            probe
            for probe in recovery
            if probe["kind"] == recovery_kind
            and str(probe["excluded_function"]).startswith(f"{domain}.")
        )
        collision_by_domain[domain] = next(
            probe
            for probe in collisions
            if probe["kind"] == "nearest_existing_collision"
            and str(probe["expected_function"]) == f"{domain}.hub"
        )

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        catalog_path = root / "function-catalog.v20.runtime.json"
        catalog_path.write_text(
            json.dumps(runtime_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        shutil.copyfile(
            ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json",
            root / "function-equivalence.v1.json",
        )
        catalog = NavigationFunctionCatalog(root / "runtime.sqlite", catalog_path)

        for item in terminals:
            definition = catalog.function(str(item["function_id"]))
            assert definition is not None
            assert definition.automation_policy == "never_auto"
            assert definition.stop_policy == "before_action"

        positive_plans = {}
        for domain, probe in positive_by_domain.items():
            plan = catalog.plan_goal(str(probe["text"]))
            assert plan.terminal_function == probe["expected_function"], probe
            terminal = catalog.function(plan.terminal_function)
            assert terminal is not None
            assert terminal.automation_policy == "never_auto"
            assert terminal.stop_policy == "before_action"
            positive_plans[domain] = plan

        for probe in missing_by_domain.values():
            _assert_safe_stop(catalog, probe)
        for probe in isolation_by_domain.values():
            _assert_safe_stop(catalog, probe)
        for probe in recovery_by_domain.values():
            assert probe["required_policy"] == "never_auto"
            assert probe["required_stop_policy"] == "before_action"
            assert probe["required_user_owned_final_press"] is True
            _assert_safe_stop(catalog, probe)
        for probe in collision_by_domain.values():
            _assert_safe_stop(catalog, probe)

        # Every documented V20-to-V20 ambiguity is replayed through the
        # governance boundary.  It may remain wholly abstained or stop at the
        # originating safe hub, but it may never preserve a terminal choice.
        for domain, other, token in WITHIN_V20_COLLISIONS:
            bounded = catalog.apply_governance_evidence_boundary(
                result=positive_plans[domain],
                evidence_text=(
                    f"{hubs_by_domain[domain]['name_en']} and "
                    f"{hubs_by_domain[other]['name_en']}: {token}; wrong role "
                    "and different claimant family case or lifecycle state"
                ),
            )
            assert bounded.intent == GOAL_GOVERNANCE_BLOCKED_INTENT, (domain, other)
            assert (
                (not bounded.terminal_function and not bounded.preferred_functions)
                or _safe_hub_plan(
                    catalog,
                    terminal_function=bounded.terminal_function,
                    preferred_functions=bounded.preferred_functions,
                    expected_hub=f"{domain}.hub",
                )
            ), (domain, other)

    print(
        json.dumps(
            {
                "result": "PASS",
                "domains": len(REQUIRED_DOMAINS),
                "all_terminal_safety": len(terminals),
                "positive_runtime": len(positive_by_domain),
                "missing_dimension_runtime": len(missing_by_domain),
                "nearest_collision_runtime": len(collision_by_domain),
                "role_asset_runtime": len(isolation_by_domain),
                "recovery_runtime": len(recovery_by_domain),
                "within_v20_runtime": len(WITHIN_V20_COLLISIONS),
                "inherited_reference_corrections": 354,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
