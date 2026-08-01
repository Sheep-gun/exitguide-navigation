"""Deterministic contract checks for the app-agnostic v6 ontology layer.

This test deliberately trial-merges v6 in memory.  It does not promote v6 to
the canonical catalog and it does not read independent/holdout fixture labels.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
SCRIPTS = ROOT / "scripts"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_catalog_quality import audit_navigation_catalog  # noqa: E402
from app.services.navigation_function_catalog import (  # noqa: E402
    NavigationFunctionCatalog,
    validate_catalog_payload,
)

from navigation_catalog_v6_data import (  # noqa: E402
    CATALOG_V6_DESCRIPTION,
    CATALOG_V6_VERSION,
    COLLECTED_ON,
    EXCLUDED_AS_ALREADY_COVERED,
    OFFICIAL_SOURCES,
    REQUIRED_DOMAINS,
    REQUIRED_FUNCTIONS,
    V6CatalogValidationError,
    V6_FUNCTIONS,
    V6_INTENTS,
    _rule_signature,
    _runtime_pattern_key,
    load_base_catalog,
    merge_with_base,
    validate_v6_data,
)
from navigation_catalog_v5_data import CATALOG_V5_DESCRIPTION, CATALOG_V5_VERSION  # noqa: E402
from navigation_catalog_v7_data import (  # noqa: E402
    V7_FUNCTIONS,
    V7_INTENTS,
    merge_with_base as merge_v7_with_base,
)
from navigation_catalog_v8_data import (  # noqa: E402
    V8_FUNCTIONS,
    V8_INTENTS,
    merge_with_base as merge_v8_with_base,
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
from navigation_alias_context_overrides import (  # noqa: E402
    apply_alias_context_overrides,
    strip_alias_context_overrides,
)


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _expect_fail_closed(payload: dict[str, object], message: str) -> None:
    try:
        merge_with_base(payload)
    except V6CatalogValidationError:
        return
    raise AssertionError(message)


def main() -> None:
    base = strip_alias_context_overrides(load_base_catalog())
    v7_function_ids = {
        str(item["function_id"])
        for item in (*V7_FUNCTIONS, *V8_FUNCTIONS, *V9_FUNCTIONS, *V10_FUNCTIONS, *V11_FUNCTIONS, *V12_FUNCTIONS, *V13_FUNCTIONS, *V14_FUNCTIONS, *V15_FUNCTIONS)
    }
    v7_intent_ids = {
        str(item["intent_id"])
        for item in (*V7_INTENTS, *V8_INTENTS, *V9_INTENTS, *V10_INTENTS, *V11_INTENTS, *V12_INTENTS, *V13_INTENTS, *V14_INTENTS, *V15_INTENTS)
    }
    base["functions"] = [
        item for item in base["functions"] if str(item["function_id"]) not in v7_function_ids
    ]
    base["intents"] = [
        item for item in base["intents"] if str(item["intent_id"]) not in v7_intent_ids
    ]
    base.pop("official_sources_v7", None)
    base.pop("official_sources_v8", None)
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
    base["catalog_version"] = CATALOG_V5_VERSION
    base["description"] = CATALOG_V5_DESCRIPTION
    base_snapshot = copy.deepcopy(base)
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
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
    stats = validate_v6_data(base)

    assert stats == {
        "functions": 121,
        "terminal_functions": 113,
        "intents": 113,
        "domains": 8,
        "domain_terminal_counts": {
            "automotive_vehicle": 12,
            "civic_local": 14,
            "fitness_membership": 15,
            "grocery_loyalty": 14,
            "home_services": 14,
            "hr_payroll": 16,
            "parking_tolls": 14,
            "pet_care": 14,
        },
        "official_sources": 62,
        "aliases": 2194,
        "goal_patterns": 2938,
        "goal_rules": 4450,
        "compositional_goal_rules": 1742,
        "state_changing": 76,
        "high_risk": 92,
        "materialized": False,
    }
    assert REQUIRED_DOMAINS == {
        "automotive_vehicle",
        "parking_tolls",
        "hr_payroll",
        "fitness_membership",
        "home_services",
        "civic_local",
        "pet_care",
        "grocery_loyalty",
    }
    assert len(REQUIRED_FUNCTIONS) >= 15
    assert REQUIRED_FUNCTIONS <= {str(item["function_id"]) for item in V6_FUNCTIONS}

    # The v6 layer is gap-driven.  Nearby concepts already owned by v1-v5 are
    # documented and may not be silently reintroduced with duplicate IDs.
    base_function_ids = {str(item["function_id"]) for item in base["functions"]}
    base_intent_ids = {str(item["intent_id"]) for item in base["intents"]}
    v6_function_ids = {str(item["function_id"]) for item in V6_FUNCTIONS}
    v6_intent_ids = {str(item["intent_id"]) for item in V6_INTENTS}
    assert not base_function_ids.intersection(v6_function_ids)
    assert not base_intent_ids.intersection(v6_intent_ids)
    assert EXCLUDED_AS_ALREADY_COVERED

    official_hosts = {
        "apps.adp.com",
        "apps.akcreunite.org",
        "help.classpass.com",
        "help.target.com",
        "portal.311.nyc.gov",
        "service.tesla.com",
        "services.petsmart.com",
        "support.google.com",
        "support.parkmobile.io",
        "support.taskrabbit.com",
        "thruway.ny.gov",
        "www.adp.com",
        "www.akcreunite.org",
        "www.chewy.com",
        "www.e-zpassny.com",
        "www.kroger.com",
        "www.nyc.gov",
        "www.petco.com",
        "www.tesla.com",
        "www.walmart.com",
        "www.workday.com",
    }
    assert {urlparse(str(source["url"])).netloc for source in OFFICIAL_SOURCES.values()} <= official_hosts
    assert all(source["collected_on"] == COLLECTED_ON for source in OFFICIAL_SOURCES.values())
    assert all(source["evidence_level"] == "official_primary" for source in OFFICIAL_SOURCES.values())
    assert all(source["verified_status"] == 200 for source in OFFICIAL_SOURCES.values())
    assert all(str(source["verification_method"]).strip() for source in OFFICIAL_SOURCES.values())

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    terminal_ids = {
        str(item["function_id"])
        for item in V6_FUNCTIONS
        if bool(item["terminal"])
    }
    assert terminal_ids == {str(item["terminal_function"]) for item in V6_INTENTS}
    for function in V6_FUNCTIONS:
        function_id = str(function["function_id"])
        refs = {str(value) for value in function["source_refs"]}
        assert refs and refs <= known_sources, function_id
        used_sources.update(refs)
        assert len(function["aliases"]["ko-KR"]) >= 8
        assert len(function["aliases"]["en-US"]) >= 8
        assert len(function["positive_context"]) >= 6
        assert len(function["negative_context"]) >= 4
        assert function["role_hints"] and function["state_cues"] and function["risk_cues"]
        assert function["evidence_level"] == "official"
        assert not {
            "x", "y", "bounds", "coordinates", "package", "package_name", "resource_id"
        }.intersection(function)
        if function["state_changing"] or function["risk_level"] == "high":
            assert function["automation_policy"] == "never_auto"
            assert function["stop_policy"] == "before_action"
            boundary = " ".join(function["risk_cues"]["user_boundary"])
            assert "사용자" in boundary and "user" in boundary.casefold()
    assert used_sources == known_sources

    base_pattern_owners: dict[str, set[str]] = {}
    base_rule_signatures: set[tuple[str, ...]] = set()
    for intent in base["intents"]:
        intent_id = str(intent["intent_id"])
        for pattern in intent.get("patterns", []):
            key = _runtime_pattern_key(pattern)
            if key:
                base_pattern_owners.setdefault(key, set()).add(intent_id)
        for rule in intent.get("goal_rules", []):
            signature = _rule_signature(rule)
            if signature:
                base_rule_signatures.add(signature)

    v6_pattern_owners: dict[str, set[str]] = {}
    v6_rule_owners: dict[tuple[str, ...], set[str]] = {}
    for intent in V6_INTENTS:
        intent_id = str(intent["intent_id"])
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 10
        assert len(intent["patterns_by_locale"]["en-US"]) >= 10
        assert len(intent["goal_rules"]) >= 24
        assert len(intent["route"]) == 2
        assert intent["route"][-1]["function_id"] == intent["terminal_function"]
        assert intent["avoid_functions"]
        for pattern in intent["patterns"]:
            key = _runtime_pattern_key(pattern)
            assert key not in base_pattern_owners
            v6_pattern_owners.setdefault(key, set()).add(intent_id)
        for rule in intent["goal_rules"]:
            signature = _rule_signature(rule)
            assert signature and signature not in base_rule_signatures
            v6_rule_owners.setdefault(signature, set()).add(intent_id)
            for key in (
                "v6_discriminative_keys",
                "v6_negative_context_keys",
                "v6_positive_context_keys",
            ):
                values = list(rule[key])
                assert values == sorted(set(values))
    assert all(len(owners) == 1 for owners in v6_pattern_owners.values())
    assert all(len(owners) == 1 for owners in v6_rule_owners.values())

    merged = merge_with_base(base)
    assert base == base_snapshot, "v6 trial merge must not mutate the v5 input"
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert merged["catalog_version"] == CATALOG_V6_VERSION
    assert merged["description"] == CATALOG_V6_DESCRIPTION
    assert merged["official_sources_v6"] == OFFICIAL_SOURCES
    assert len(merged["functions"]) == len(base["functions"]) + len(V6_FUNCTIONS)
    assert len(merged["intents"]) == len(base["intents"]) + len(V6_INTENTS)
    validate_catalog_payload(merged)

    # Rebuilding from the same v5 input and merging an already merged payload
    # must both yield identical canonical JSON bytes.
    merged_second = merge_with_base(copy.deepcopy(base))
    assert _canonical_bytes(merged) == _canonical_bytes(merged_second)
    merged_snapshot = copy.deepcopy(merged)
    merged_again = merge_with_base(merged)
    assert merged == merged_snapshot
    assert _canonical_bytes(merged_again) == _canonical_bytes(merged)
    assert validate_v6_data(merged)["materialized"] is True

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v6-trial-") as temp_dir:
        temp = Path(temp_dir)
        base_path = temp / "v5.json"
        merged_path = temp / "v6-trial.json"
        base_path.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        quality_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(
                merge_v14_with_base(
                    merge_v13_with_base(
                        merge_v12_with_base(
                            merge_v11_with_base(
                                merge_v10_with_base(
                                    merge_v9_with_base(merge_v8_with_base(merge_v7_with_base(merged)))
                                )
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

        # Runtime smoke coverage uses ontology-owned patterns only.  Existing
        # inputs are compared through the complete static collision inventory
        # above without reading any sealed expected labels.
        catalog = NavigationFunctionCatalog(temp / "v6.sqlite", merged_path)
        for intent in V6_INTENTS:
            for locale in ("ko-KR", "en-US"):
                goal = str(intent["patterns_by_locale"][locale][0])
                plan = catalog.plan_goal(goal)
                assert plan.terminal_function == intent["terminal_function"], (
                    goal,
                    plan.terminal_function,
                    intent["terminal_function"],
                )

    # Fail closed on partial materialization and on drift in any persisted v6
    # definition, evidence registry, or materialization metadata.
    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V6_FUNCTIONS[0]))
    _expect_fail_closed(partial, "partial v6 materialization must fail closed")

    changed_function = copy.deepcopy(merged)
    next(
        item for item in changed_function["functions"]
        if item["function_id"] == V6_FUNCTIONS[0]["function_id"]
    )["description"] = "conflicting v6 definition"
    _expect_fail_closed(changed_function, "changed v6 function must fail closed")

    changed_intent = copy.deepcopy(merged)
    next(
        item for item in changed_intent["intents"]
        if item["intent_id"] == V6_INTENTS[0]["intent_id"]
    )["goal_rules"] = V6_INTENTS[0]["goal_rules"][:-1]
    _expect_fail_closed(changed_intent, "changed v6 intent must fail closed")

    changed_sources = copy.deepcopy(merged)
    changed_sources["official_sources_v6"] = {}
    _expect_fail_closed(changed_sources, "changed v6 source registry must fail closed")

    changed_metadata = copy.deepcopy(merged)
    changed_metadata["catalog_version"] = "6.0.0-modified"
    _expect_fail_closed(changed_metadata, "changed v6 metadata must fail closed")

    print(
        "navigation catalog v6 trial checks ok: "
        f"functions={stats['functions']} terminals={stats['terminal_functions']} "
        f"intents={stats['intents']} domains={stats['domains']} "
        f"sources={stats['official_sources']} aliases={stats['aliases']} "
        f"patterns={stats['goal_patterns']} rules={stats['goal_rules']} "
        "quality=100 byte_deterministic=true idempotent=true"
    )


if __name__ == "__main__":
    main()
