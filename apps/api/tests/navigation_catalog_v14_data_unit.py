from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_catalog_quality import audit_navigation_catalog  # noqa: E402
from app.services.navigation_function_catalog import NavigationFunctionCatalog, validate_catalog_payload  # noqa: E402
from navigation_alias_context_overrides import apply_alias_context_overrides, strip_alias_context_overrides  # noqa: E402
from navigation_catalog_v14_data import (  # noqa: E402
    CATALOG_V14_DESCRIPTION,
    CATALOG_V14_VERSION,
    COLLECTED_ON,
    COLLISION_FAMILIES,
    DESIGN_SOURCE_PATH,
    DOMAIN_SOURCE_IDS,
    EXPECTED_DOMAIN_COUNTS,
    GROUPS,
    OFFICIAL_SOURCES,
    PUBLISHER_ALLOWLIST,
    REQUIRED_DOMAINS,
    RETRIEVED_AT,
    SOURCE_DOCUMENT_METADATA,
    SOURCE_DOCUMENT_SHA256,
    V14CatalogValidationError,
    V14_FUNCTIONS,
    V14_INTENTS,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
    validate_v14_data,
)
from navigation_catalog_v15_data import (  # noqa: E402
    CATALOG_V15_DESCRIPTION,
    CATALOG_V15_VERSION,
    V15_FUNCTIONS,
    V15_INTENTS,
    merge_with_base as merge_v15_with_base,
)


def _serialized(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v14_data(payload)
    except V14CatalogValidationError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"invalid v14 payload accepted; expected {fragment!r}")


def main() -> None:
    actual_source_sha = hashlib.sha256(DESIGN_SOURCE_PATH.read_bytes()).hexdigest()
    assert actual_source_sha == SOURCE_DOCUMENT_SHA256
    assert SOURCE_DOCUMENT_METADATA == {
        "path": "docs/NAVIGATION_COVERAGE_GAPS_V14.md",
        "algorithm": "sha256",
        "sha256": SOURCE_DOCUMENT_SHA256,
    }

    base = load_base_catalog()
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    base["functions"] = [
        item for item in base["functions"] if str(item["function_id"]) not in v15_function_ids
    ]
    base["intents"] = [
        item for item in base["intents"] if str(item["intent_id"]) not in v15_intent_ids
    ]
    base.pop("official_sources_v15", None)
    base.pop("source_document_v15", None)
    base.pop("semantic_equivalence_v15", None)
    snapshot = copy.deepcopy(base)
    base_functions_hash = hashlib.sha256(_serialized(base["functions"])).hexdigest()
    base_intents_hash = hashlib.sha256(_serialized(base["intents"])).hexdigest()
    assert base["catalog_version"] == "13.0.0"
    assert len(base["functions"]) == 2362
    assert len(base["intents"]) == 2180
    assert not v15_function_ids.intersection(str(item["function_id"]) for item in base["functions"])
    assert not v15_intent_ids.intersection(str(item["intent_id"]) for item in base["intents"])
    assert not {"official_sources_v15", "source_document_v15", "semantic_equivalence_v15"} & set(base)
    assert base["catalog_version"] != CATALOG_V15_VERSION
    assert base["description"] != CATALOG_V15_DESCRIPTION

    stats = validate_v14_data(base)
    assert stats == {
        **stats,
        "functions": 252,
        "terminal_functions": 240,
        "intents": 240,
        "domains": 12,
        "domain_terminal_counts": EXPECTED_DOMAIN_COUNTS,
        "official_sources": 48,
        "source_sha256": SOURCE_DOCUMENT_SHA256,
        "sensitive_reads": 84,
        "state_changing": 156,
        "semantic_smoke_probes": 1440,
        "collision_probes": 720,
        "recovery_probes": 960,
        "isolation_probes": 720,
        "materialized": False,
    }
    assert base == snapshot

    base_function_ids = {str(item["function_id"]) for item in base["functions"]}
    base_intent_ids = {str(item["intent_id"]) for item in base["intents"]}
    base_domain_ids = {str(item["domain"]) for item in base["functions"]}
    function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V14_FUNCTIONS if item["terminal"]}
    intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    assert len(REQUIRED_DOMAINS) == 12
    assert len(V14_FUNCTIONS) == 252
    assert len(terminal_ids) == 240
    assert len(V14_INTENTS) == 240
    assert {str(item["terminal_function"]) for item in V14_INTENTS} == terminal_ids
    assert not function_ids.intersection(base_function_ids)
    assert not intent_ids.intersection(base_intent_ids)
    assert not REQUIRED_DOMAINS.intersection(base_domain_ids)
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value) for value in function_ids)
    assert all(re.fullmatch(r"v14_[a-z0-9_]+", value) for value in intent_ids)
    assert all(
        str(rule["rule_kind"]).startswith("v14_")
        and "v14_discriminative_keys" in rule
        and "v13_discriminative_keys" not in rule
        for intent in V14_INTENTS for rule in intent["goal_rules"]
    )
    assert all(
        "v14_role_governed_operations" in item["legacy_tags"]
        and "v13_governed_operations" not in item["legacy_tags"]
        for item in V14_FUNCTIONS
    )

    assert len(OFFICIAL_SOURCES) == 48
    assert len({str(item["url"]) for item in OFFICIAL_SOURCES.values()}) == 48
    assert all(str(item["url"]).startswith("https://") for item in OFFICIAL_SOURCES.values())
    assert all(item["publisher"] in PUBLISHER_ALLOWLIST for item in OFFICIAL_SOURCES.values())
    assert all(item["collected_on"] == COLLECTED_ON for item in OFFICIAL_SOURCES.values())
    assert all(item["retrieved_at"] == RETRIEVED_AT for item in OFFICIAL_SOURCES.values())
    assert all(item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert all(re.fullmatch(r"[0-9a-f]{64}", str(item["source_record_sha256"])) for item in OFFICIAL_SOURCES.values())
    content_hashed = [item for item in OFFICIAL_SOURCES.values() if "content_sha256" in item]
    assert len(content_hashed) == 4
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", str(item["content_sha256"]))
        and item["content_hash_scope"] == "retrieved_binary_artifact"
        for item in content_hashed
    )
    assert all(
        item["supported_roles"] and item["supported_assets"] and item["supported_states"]
        and item["jurisdiction_scope"] and item["terminal_ids"]
        for item in OFFICIAL_SOURCES.values()
    )
    assert set(DOMAIN_SOURCE_IDS) == REQUIRED_DOMAINS
    assert all(len(values) == 4 for values in DOMAIN_SOURCE_IDS.values())
    assert all(
        len(set().union(*(set(OFFICIAL_SOURCES[source_id]["terminal_ids"]) for source_id in source_ids))) == 20
        for source_ids in DOMAIN_SOURCE_IDS.values()
    )

    sensitive = 0
    consequential = 0
    forbidden = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_name",
        "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path",
        "pixel", "click_sequence",
    }
    for item in V14_FUNCTIONS:
        assert len(item["aliases"]["ko-KR"]) >= 8
        assert len(item["aliases"]["en-US"]) >= 8
        assert len(item["positive_context"]) >= 6
        assert len(item["negative_context"]) >= 8
        assert len(item["role_hints"]) >= 2
        assert len(item["asset_cues"]) >= 2
        assert len(item["state_cues"]["lifecycle"]) >= 2
        assert item["state_cues"]["jurisdiction"]
        assert item["risk_cues"]
        assert item["source_refs"] and set(item["source_refs"]) <= set(OFFICIAL_SOURCES)
        assert not forbidden.intersection(item)
        if item["terminal"]:
            sensitive += item["classification"] == "S" and not bool(item["state_changing"])
            consequential += item["classification"] == "C" and bool(item["state_changing"])
            assert item["risk_level"] == "high"
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] == "before_action"
            assert item["user_owned_final_press"] is True
            boundary = " ".join(item["risk_cues"]["user_boundary"])
            assert "사용자" in boundary and "user" in boundary.casefold() and "press" in boundary.casefold()
            assert item["risk_cues"]["role_asset_state_gate"]
            assert item["risk_cues"]["fail_closed"]
            assert item["risk_cues"]["forbidden_terminal_actions"]
            assert item["function_id"] in set().union(
                *(set(OFFICIAL_SOURCES[source_id]["terminal_ids"]) for source_id in item["source_refs"])
            )
        else:
            assert item["node_kind"] == "hub"
            assert item["risk_level"] == "low"
            assert item["automation_policy"] == "safe_navigation"
            assert item["stop_policy"] == "continue"
            assert item["state_changing"] is False
            assert item["user_owned_final_press"] is False
    assert (sensitive, consequential) == (84, 156)

    for item in V14_INTENTS:
        assert len(item["patterns_by_locale"]["ko-KR"]) >= 5
        assert len(item["patterns_by_locale"]["en-US"]) >= 5
        assert len(item["goal_rules"]) >= 24
        assert any(rule["rule_kind"] == "v14_compositional_domain" for rule in item["goal_rules"])
        assert any(rule["rule_kind"] == "v14_consequence_context" for rule in item["goal_rules"])
        assert len(item["route"]) == 2
        assert item["route"][-1]["function_id"] == item["terminal_function"]
        assert len(item["avoid_functions"]) >= 2
        assert item["terminal_function"] not in item["avoid_functions"]
        assert item["desired_state"] == "user_confirmation_required"
        assert item["terminal_condition"] == {
            "stop_policy": "stop_before_action",
            "user_owned_final_press": True,
        }

    matrix = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    assert len(matrix) == 1440
    assert sum(item["kind"] == "positive" for item in matrix) == 480
    assert sum(item["kind"] != "positive" for item in matrix) == 960
    assert len(COLLISION_FAMILIES) == 60
    assert len({(item[0], item[1]) for item in COLLISION_FAMILIES}) == 60
    assert all(len(item[2]) == 3 for item in COLLISION_FAMILIES)
    assert len(collisions) == 720
    assert len({item["probe_id"] for item in collisions}) == 720
    assert {item["locale"] for item in collisions} == {"ko-KR", "en-US"}
    assert all(item["expected_function"] in terminal_ids for item in collisions)
    assert len(recovery) == 960
    assert {item["kind"] for item in recovery} == {
        "disabled", "unavailable_offline", "wrong_role", "wrong_record_asset",
    }
    assert all(item["required_user_owned_final_press"] is True for item in recovery)
    assert len(isolation) == 720
    assert {item["kind"] for item in isolation} == {"wrong_role", "wrong_asset", "wrong_state"}

    merged = merge_with_base(base)
    assert base == snapshot
    assert merged["catalog_version"] == CATALOG_V14_VERSION
    assert merged["description"] == CATALOG_V14_DESCRIPTION
    assert merged["official_sources_v14"] == OFFICIAL_SOURCES
    assert merged["source_document_v14"] == SOURCE_DOCUMENT_METADATA
    assert len(merged["functions"]) == 2614
    assert len(merged["intents"]) == 2420
    assert len({str(item["domain"]) for item in merged["functions"]}) == 167
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert hashlib.sha256(_serialized(merged["functions"][:len(base["functions"])] )).hexdigest() == base_functions_hash
    assert hashlib.sha256(_serialized(merged["intents"][:len(base["intents"])] )).hexdigest() == base_intents_hash
    validate_catalog_payload(merged)
    assert validate_v14_data(merged)["materialized"] is True
    merged_twice = merge_with_base(merged)
    merged_thrice = merge_with_base(merged_twice)
    assert merged_twice == merged == merged_thrice
    merged_function_ids = {str(item["function_id"]) for item in merged["functions"]}
    assert all(set(str(value) for value in intent["avoid_functions"]) <= merged_function_ids for intent in V14_INTENTS)

    digest_one = hashlib.sha256(_serialized(merged)).hexdigest()
    digest_two = hashlib.sha256(_serialized(merge_with_base(copy.deepcopy(base)))).hexdigest()
    digest_three = hashlib.sha256(_serialized(merged_thrice)).hexdigest()
    assert digest_one == digest_two == digest_three

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v14-source-") as temp_dir:
        temp = Path(temp_dir)
        merged_path = temp / "v14-source.json"
        quality_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(merge_v15_with_base(merged))
        )
        merged_path.write_text(json.dumps(quality_payload, ensure_ascii=False), encoding="utf-8")
        quality = audit_navigation_catalog(merged_path, policy_path)
        assert quality["quality_score"] == 100.0, quality
        assert quality["severity_counts"] == {}
        assert quality["goal_pattern_collisions"] == []

        catalog = NavigationFunctionCatalog(temp / "v14.sqlite", merged_path)
        positive_count = 0
        function_by_id = {str(item["function_id"]): item for item in V14_FUNCTIONS}
        intent_by_function = {str(item["terminal_function"]): item for item in V14_INTENTS}
        for probe in matrix:
            if probe["kind"] == "positive":
                plan = catalog.plan_goal(str(probe["text"]))
                assert plan.terminal_function == probe["expected_function"], probe
                definition = catalog.function(plan.terminal_function)
                assert definition is not None
                assert definition.risk_level == "high"
                assert definition.automation_policy == "never_auto"
                assert definition.stop_policy == "before_action"
                positive_count += 1
            else:
                function = function_by_id[str(probe["excluded_function"])]
                intent = intent_by_function[str(probe["excluded_function"])]
                positive_fields = {
                    str(value).casefold()
                    for value in (
                        *function["aliases"]["ko-KR"], *function["aliases"]["en-US"],
                        *function["positive_context"], *intent["patterns"],
                    )
                }
                assert str(probe["text"]).casefold() not in positive_fields
        assert positive_count == 480

        for probe in collisions:
            plan = catalog.plan_goal(str(probe["text"]))
            assert plan.terminal_function == probe["expected_function"], probe

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V14_FUNCTIONS[0]))
    _expect_failure(partial, "partial v14")

    changed_function = copy.deepcopy(merged)
    changed_function["functions"][-1]["description"] = "conflicting v14 definition"
    _expect_failure(changed_function, "different function or intent definition")

    changed_intent = copy.deepcopy(merged)
    changed_intent["intents"][-1]["goal_rules"] = changed_intent["intents"][-1]["goal_rules"][:-1]
    _expect_failure(changed_intent, "different function or intent definition")

    changed_sources = copy.deepcopy(merged)
    changed_sources["official_sources_v14"] = {}
    _expect_failure(changed_sources, "official evidence registry")

    changed_source_sha = copy.deepcopy(merged)
    changed_source_sha["source_document_v14"]["sha256"] = "0" * 64
    _expect_failure(changed_source_sha, "source document SHA metadata")

    changed_metadata = copy.deepcopy(merged)
    changed_metadata["catalog_version"] = "14.0.0-modified"
    _expect_failure(changed_metadata, "materialization metadata")

    unsafe = copy.deepcopy(merged)
    unsafe["functions"][len(base["functions"]) + 1]["automation_policy"] = "auto_execute"
    _expect_failure(unsafe, "different function or intent definition")

    assert sum(len(group.features) for group in GROUPS) == 240
    print(
        "navigation catalog v14 source checks ok: "
        f"functions={stats['functions']} terminals={stats['terminal_functions']} "
        f"intents={stats['intents']} domains={stats['domains']} sources={stats['official_sources']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']} "
        f"sensitive={sensitive} state_changing={consequential} matrix={len(matrix)} "
        f"collisions={len(collisions)} recovery={len(recovery)} isolation={len(isolation)} "
        f"quality=100 source_sha256={SOURCE_DOCUMENT_SHA256} "
        f"v13_functions_sha256={base_functions_hash} v13_intents_sha256={base_intents_hash} "
        f"catalog_sha256={digest_one}"
    )


if __name__ == "__main__":
    main()
