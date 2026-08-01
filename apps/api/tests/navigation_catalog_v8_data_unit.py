from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_catalog_quality import audit_navigation_catalog  # noqa: E402
from app.services.navigation_function_catalog import (  # noqa: E402
    NavigationFunctionCatalog,
    validate_catalog_payload,
)
from navigation_catalog_v8_data import (  # noqa: E402
    CATALOG_V8_DESCRIPTION,
    CATALOG_V8_VERSION,
    COLLECTED_ON,
    OFFICIAL_SOURCES,
    REQUIRED_DOMAINS,
    REQUIRED_FUNCTIONS,
    V8CatalogValidationError,
    V8_FUNCTIONS,
    V8_INTENTS,
    load_base_catalog,
    merge_with_base,
    validate_v8_data,
)
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)
from navigation_catalog_v9_data import (  # noqa: E402
    V9_FUNCTIONS,
    V9_INTENTS,
    merge_with_base as merge_v9_with_base,
)
from navigation_catalog_v10_data import (  # noqa: E402
    V10_FUNCTIONS,
    V10_INTENTS,
    merge_with_base as merge_v10_with_base,
)
from navigation_catalog_v11_data import (  # noqa: E402
    V11_FUNCTIONS,
    V11_INTENTS,
    merge_with_base as merge_v11_with_base,
)
from navigation_catalog_v12_data import (  # noqa: E402
    V12_FUNCTIONS,
    V12_INTENTS,
    merge_with_base as merge_v12_with_base,
)
from navigation_catalog_v13_data import (  # noqa: E402
    V13_FUNCTIONS,
    V13_INTENTS,
    merge_with_base as merge_v13_with_base,
)
from navigation_catalog_v14_data import (  # noqa: E402
    CATALOG_V14_DESCRIPTION,
    CATALOG_V14_VERSION,
    V14_FUNCTIONS,
    V14_INTENTS,
    merge_with_base as merge_v14_with_base,
)
from navigation_catalog_v15_data import (  # noqa: E402
    CATALOG_V15_DESCRIPTION,
    CATALOG_V15_VERSION,
    V15_FUNCTIONS,
    V15_INTENTS,
    merge_with_base as merge_v15_with_base,
)


def _serialized(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _expect_validation_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v8_data(payload)
    except V8CatalogValidationError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"invalid v8 payload was accepted; expected {fragment!r}")


def main() -> None:
    base = strip_alias_context_overrides(load_base_catalog())
    v9_function_ids = {str(item["function_id"]) for item in V9_FUNCTIONS}
    v9_intent_ids = {str(item["intent_id"]) for item in V9_INTENTS}
    v10_function_ids = {str(item["function_id"]) for item in V10_FUNCTIONS}
    v10_intent_ids = {str(item["intent_id"]) for item in V10_INTENTS}
    v11_function_ids = {str(item["function_id"]) for item in V11_FUNCTIONS}
    v11_intent_ids = {str(item["intent_id"]) for item in V11_INTENTS}
    v12_function_ids = {str(item["function_id"]) for item in V12_FUNCTIONS}
    v12_intent_ids = {str(item["intent_id"]) for item in V12_INTENTS}
    v13_function_ids = {str(item["function_id"]) for item in V13_FUNCTIONS}
    v13_intent_ids = {str(item["intent_id"]) for item in V13_INTENTS}
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    base["functions"] = [
        item for item in base["functions"]
        if str(item["function_id"])
        not in v9_function_ids | v10_function_ids | v11_function_ids | v12_function_ids | v13_function_ids | v14_function_ids | v15_function_ids
    ]
    base["intents"] = [
        item for item in base["intents"]
        if str(item["intent_id"])
        not in v9_intent_ids | v10_intent_ids | v11_intent_ids | v12_intent_ids | v13_intent_ids | v14_intent_ids | v15_intent_ids
    ]
    base.pop("official_sources_v9", None)
    base.pop("official_sources_v10", None)
    base.pop("official_sources_v11", None)
    base.pop("official_sources_v12", None)
    base.pop("source_document_v12", None)
    base.pop("official_sources_v13", None)
    base.pop("source_document_v13", None)
    base.pop("official_sources_v14", None)
    base.pop("source_document_v14", None)
    base.pop("official_sources_v15", None)
    base.pop("source_document_v15", None)
    base.pop("semantic_equivalence_v15", None)
    base_snapshot = copy.deepcopy(base)
    assert not v14_function_ids.intersection(str(item["function_id"]) for item in base["functions"])
    assert not v14_intent_ids.intersection(str(item["intent_id"]) for item in base["intents"])
    assert "official_sources_v14" not in base and "source_document_v14" not in base
    assert base["catalog_version"] != CATALOG_V14_VERSION
    assert base["description"] != CATALOG_V14_DESCRIPTION
    assert not v15_function_ids.intersection(str(item["function_id"]) for item in base["functions"])
    assert not v15_intent_ids.intersection(str(item["intent_id"]) for item in base["intents"])
    assert not {"official_sources_v15", "source_document_v15", "semantic_equivalence_v15"} & set(base)
    assert base["catalog_version"] != CATALOG_V15_VERSION
    assert base["description"] != CATALOG_V15_DESCRIPTION
    assert base["catalog_version"] == "7.0.0"
    stats = validate_v8_data(base)
    assert stats == {
        "functions": 146,
        "terminal_functions": 138,
        "intents": 138,
        "domains": 8,
        "domain_terminal_counts": {
            "business_accounting": 19,
            "credential_vault": 17,
            "crm_sales": 17,
            "customer_support_agent": 15,
            "field_construction_ops": 19,
            "gig_worker_dispatch": 17,
            "incident_oncall": 15,
            "merchant_pos_inventory": 19,
        },
        "official_sources": 16,
        "aliases": 2368,
        "goal_patterns": 3312,
        "goal_rules": 4968,
        "compositional_goal_rules": 1656,
        "state_changing": 82,
        "high_risk": 126,
        "materialized": False,
    }
    assert base == base_snapshot, "validation mutated the v7 base"
    assert REQUIRED_DOMAINS == {
        "credential_vault",
        "business_accounting",
        "crm_sales",
        "customer_support_agent",
        "merchant_pos_inventory",
        "field_construction_ops",
        "gig_worker_dispatch",
        "incident_oncall",
    }

    function_ids = {str(item["function_id"]) for item in V8_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V8_FUNCTIONS if item["terminal"]}
    assert REQUIRED_FUNCTIONS <= function_ids
    assert len(V8_FUNCTIONS) == len(terminal_ids) + len(REQUIRED_DOMAINS)
    assert {str(item["terminal_function"]) for item in V8_INTENTS} == terminal_ids
    assert all(str(item["intent_id"]).startswith("v8_") for item in V8_INTENTS)
    assert all(
        str(rule["rule_kind"]).startswith("v8_")
        and "v8_discriminative_keys" in rule
        and "v7_discriminative_keys" not in rule
        for intent in V8_INTENTS
        for rule in intent["goal_rules"]
    )
    assert all(
        "v8_operational_workflow" in item["legacy_tags"] and "v7_long_tail" not in item["legacy_tags"]
        for item in V8_FUNCTIONS
    )

    source_hosts = {
        "bitwarden.com",
        "support.google.com",
        "quickbooks.intuit.com",
        "central.xero.com",
        "help.salesforce.com",
        "support.zendesk.com",
        "squareup.com",
        "support.procore.com",
        "help.uber.com",
        "support.pagerduty.com",
    }
    assert {urlparse(str(item["url"])).netloc for item in OFFICIAL_SOURCES.values()} == source_hosts
    assert all(item["collected_on"] == COLLECTED_ON for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert all(item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())
    assert all(str(item["verification_method"]).strip() for item in OFFICIAL_SOURCES.values())

    consequential_count = 0
    for item in V8_FUNCTIONS:
        assert len(item["aliases"]["ko-KR"]) >= 8
        assert len(item["aliases"]["en-US"]) >= 8
        assert len(item["positive_context"]) >= 6
        assert len(item["negative_context"]) >= 4
        assert len(item["role_hints"]) >= 5
        assert item["state_cues"] and item["risk_cues"]
        assert item["source_refs"] and set(item["source_refs"]) <= set(OFFICIAL_SOURCES)
        assert not {"x", "y", "bounds", "coordinates", "package", "package_name", "resource_id"}.intersection(item)
        if item["state_changing"] or item["risk_level"] == "high":
            consequential_count += 1
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] == "before_action"
            boundary = " ".join(item["risk_cues"]["user_boundary"])
            assert "사용자" in boundary and "user" in boundary.casefold()
            assert "press" in boundary.casefold()
        elif item["terminal"]:
            assert item["automation_policy"] == "safe_navigation"
        else:
            assert item["node_kind"] == "hub"
            assert item["automation_policy"] == "safe_navigation"
            assert item["stop_policy"] == "continue"
    assert consequential_count == 137

    for item in V8_INTENTS:
        assert len(item["patterns_by_locale"]["ko-KR"]) >= 10
        assert len(item["patterns_by_locale"]["en-US"]) >= 10
        assert len(item["goal_rules"]) >= 24
        assert any(rule["rule_kind"] == "v8_compositional_domain" for rule in item["goal_rules"])
        assert any(rule["rule_kind"] == "v8_consequence_context" for rule in item["goal_rules"])
        assert len(item["route"]) == 2
        assert item["route"][-1]["function_id"] == item["terminal_function"]
        assert item["avoid_functions"]

    merged = merge_with_base(base)
    assert base == base_snapshot, "merge mutated the caller"
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert merged["catalog_version"] == CATALOG_V8_VERSION
    assert merged["description"] == CATALOG_V8_DESCRIPTION
    assert merged["official_sources_v8"] == OFFICIAL_SOURCES
    assert len(merged["functions"]) == len(base["functions"]) + len(V8_FUNCTIONS)
    assert len(merged["intents"]) == len(base["intents"]) + len(V8_INTENTS)
    validate_catalog_payload(merged)
    assert validate_v8_data(merged)["materialized"] is True
    assert merge_with_base(merged) == merged

    digest_one = hashlib.sha256(_serialized(merge_with_base(base))).hexdigest()
    digest_two = hashlib.sha256(_serialized(merge_with_base(copy.deepcopy(base)))).hexdigest()
    assert digest_one == digest_two

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v8-trial-") as temp_dir:
        temp = Path(temp_dir)
        merged_path = temp / "v8-trial.json"
        quality_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(
                merge_v14_with_base(
                    merge_v13_with_base(
                        merge_v12_with_base(
                            merge_v11_with_base(
                                merge_v10_with_base(merge_v9_with_base(merged))
                            )
                        )
                    )
                )
            )
        )
        quality_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(
                merge_v15_with_base(strip_alias_context_overrides(quality_payload))
            )
        )
        merged_path.write_text(json.dumps(quality_payload, ensure_ascii=False), encoding="utf-8")
        quality = audit_navigation_catalog(merged_path, policy_path)
        assert quality["quality_score"] == 100.0
        assert quality["severity_counts"] == {}
        assert quality["goal_pattern_collisions"] == []

        catalog = NavigationFunctionCatalog(temp / "v8.sqlite", merged_path)
        smoke_count = 0
        for intent in V8_INTENTS:
            for locale in ("ko-KR", "en-US"):
                goal = str(intent["patterns_by_locale"][locale][0])
                plan = catalog.plan_goal(goal)
                assert plan.terminal_function == intent["terminal_function"], (
                    goal,
                    plan.terminal_function,
                    intent["terminal_function"],
                )
                definition = catalog.function(plan.terminal_function)
                assert definition is not None
                if definition.state_changing or definition.risk_level == "high":
                    assert definition.automation_policy == "never_auto"
                    assert definition.stop_policy == "before_action"
                smoke_count += 1
        assert smoke_count == 276

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V8_FUNCTIONS[0]))
    _expect_validation_failure(partial, "partial v8")

    changed_function = copy.deepcopy(merged)
    changed_function["functions"][-1]["description"] = "conflicting v8 definition"
    _expect_validation_failure(changed_function, "different function or intent definition")

    changed_intent = copy.deepcopy(merged)
    changed_intent["intents"][-1]["goal_rules"] = changed_intent["intents"][-1]["goal_rules"][:-1]
    _expect_validation_failure(changed_intent, "different function or intent definition")

    changed_sources = copy.deepcopy(merged)
    changed_sources["official_sources_v8"] = {}
    _expect_validation_failure(changed_sources, "official evidence registry")

    changed_metadata = copy.deepcopy(merged)
    changed_metadata["catalog_version"] = "8.0.0-modified"
    _expect_validation_failure(changed_metadata, "materialization metadata")

    print(
        "navigation catalog v8 data checks ok: "
        f"functions={stats['functions']} terminals={stats['terminal_functions']} "
        f"intents={stats['intents']} domains={stats['domains']} sources={stats['official_sources']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} "
        f"rules={stats['goal_rules']} smoke=276 sha256={digest_one}"
    )


if __name__ == "__main__":
    main()
