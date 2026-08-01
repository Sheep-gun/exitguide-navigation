from __future__ import annotations

import copy
import hashlib
import json
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
from navigation_catalog_v11_data import (  # noqa: E402
    CATALOG_V11_DESCRIPTION,
    CATALOG_V11_VERSION,
    COLLECTED_ON,
    COLLISION_FAMILIES,
    EXPECTED_DOMAIN_COUNTS,
    GROUPS,
    OFFICIAL_SOURCES,
    REQUIRED_DOMAINS,
    V11CatalogValidationError,
    V11_FUNCTIONS,
    V11_INTENTS,
    build_collision_probes,
    build_semantic_development_matrix,
    load_base_catalog,
    merge_with_base,
    validate_v11_data,
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
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v11_data(payload)
    except V11CatalogValidationError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"invalid v11 payload accepted; expected {fragment!r}")


def main() -> None:
    base = load_base_catalog()
    v12_function_ids = {str(item["function_id"]) for item in V12_FUNCTIONS}
    v12_intent_ids = {str(item["intent_id"]) for item in V12_INTENTS}
    v13_function_ids = {str(item["function_id"]) for item in V13_FUNCTIONS}
    v13_intent_ids = {str(item["intent_id"]) for item in V13_INTENTS}
    v14_function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    v14_intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    v15_function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    v15_intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    base["functions"] = [
        item
        for item in base["functions"]
        if str(item["function_id"]) not in v12_function_ids | v13_function_ids | v14_function_ids | v15_function_ids
    ]
    base["intents"] = [
        item
        for item in base["intents"]
        if str(item["intent_id"]) not in v12_intent_ids | v13_intent_ids | v14_intent_ids | v15_intent_ids
    ]
    base.pop("official_sources_v12", None)
    base.pop("source_document_v12", None)
    base.pop("official_sources_v13", None)
    base.pop("source_document_v13", None)
    base.pop("official_sources_v14", None)
    base.pop("source_document_v14", None)
    base.pop("official_sources_v15", None)
    base.pop("source_document_v15", None)
    base.pop("semantic_equivalence_v15", None)
    snapshot = copy.deepcopy(base)
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
    assert base["catalog_version"] == "10.0.0"
    assert len(base["functions"]) == 1616
    assert len(base["intents"]) == 1470

    stats = validate_v11_data(base)
    assert stats["functions"] == 242
    assert stats["terminal_functions"] == 230
    assert stats["intents"] == 230
    assert stats["domains"] == 12
    assert stats["domain_terminal_counts"] == EXPECTED_DOMAIN_COUNTS
    assert stats["official_sources"] == 50
    assert stats["sensitive_reads"] == 74
    assert stats["state_changing"] == 156
    assert stats["semantic_smoke_probes"] == 1150
    assert stats["collision_probes"] == 160
    assert stats["materialized"] is False
    assert base == snapshot

    function_ids = {str(item["function_id"]) for item in V11_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V11_FUNCTIONS if item["terminal"]}
    assert len(REQUIRED_DOMAINS) == 12
    assert len(V11_FUNCTIONS) == 242
    assert len(terminal_ids) == 230
    assert len(V11_INTENTS) == 230
    assert {str(item["terminal_function"]) for item in V11_INTENTS} == terminal_ids
    assert all(str(item["intent_id"]).startswith("v11_") for item in V11_INTENTS)
    assert all(
        str(rule["rule_kind"]).startswith("v11_")
        and "v11_discriminative_keys" in rule
        and "v10_discriminative_keys" not in rule
        for intent in V11_INTENTS for rule in intent["goal_rules"]
    )
    assert all(
        "v11_professional_operations" in item["legacy_tags"]
        and "v10_reviewed_operations" not in item["legacy_tags"]
        for item in V11_FUNCTIONS
    )

    assert len(OFFICIAL_SOURCES) == 50
    assert len({str(item["url"]) for item in OFFICIAL_SOURCES.values()}) == 50
    assert all(str(item["url"]).startswith("https://") for item in OFFICIAL_SOURCES.values())
    assert all(item["collected_on"] == COLLECTED_ON for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert all(item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())

    sensitive = 0
    consequential = 0
    forbidden = {"x", "y", "bounds", "coordinate", "coordinates", "package", "package_name", "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path"}
    for item in V11_FUNCTIONS:
        assert len(item["aliases"]["ko-KR"]) >= 8
        assert len(item["aliases"]["en-US"]) >= 8
        assert len(item["positive_context"]) >= 6
        assert len(item["negative_context"]) >= 6
        assert len(item["role_hints"]) >= 5
        assert item["state_cues"] and item["risk_cues"]
        assert item["source_refs"] and set(item["source_refs"]) <= set(OFFICIAL_SOURCES)
        assert not forbidden.intersection(item)
        if item["terminal"]:
            sensitive += not bool(item["state_changing"])
            consequential += bool(item["state_changing"])
            assert item["risk_level"] == "high"
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] == "before_action"
            boundary = " ".join(item["risk_cues"]["user_boundary"])
            assert "사용자" in boundary and "user" in boundary.casefold() and "press" in boundary.casefold()
        else:
            assert item["node_kind"] == "hub"
            assert item["automation_policy"] == "safe_navigation"
            assert item["stop_policy"] == "continue"
    assert (sensitive, consequential) == (74, 156)

    for item in V11_INTENTS:
        assert len(item["patterns_by_locale"]["ko-KR"]) >= 10
        assert len(item["patterns_by_locale"]["en-US"]) >= 10
        assert len(item["goal_rules"]) >= 24
        assert any(rule["rule_kind"] == "v11_compositional_domain" for rule in item["goal_rules"])
        assert any(rule["rule_kind"] == "v11_consequence_context" for rule in item["goal_rules"])
        assert len(item["route"]) == 2
        assert item["route"][-1]["function_id"] == item["terminal_function"]
        assert item["avoid_functions"]
        assert item["desired_state"] == "user_confirmation_required"
        assert item["terminal_condition"]["stop_policy"] == "stop_before_action"

    matrix = build_semantic_development_matrix()
    collisions = build_collision_probes()
    assert len(matrix) == 1150
    assert sum(item["kind"] == "positive" for item in matrix) == 460
    assert sum(item["kind"] != "positive" for item in matrix) == 690
    assert len(COLLISION_FAMILIES) == 16
    assert len(collisions) == 160
    assert len({item["probe_id"] for item in collisions}) == 160
    assert {item["locale"] for item in collisions} == {"ko-KR", "en-US"}
    assert all(item["expected_function"] in terminal_ids for item in collisions)

    merged = merge_with_base(base)
    assert base == snapshot
    assert merged["functions"][:len(base["functions"])] == base["functions"]
    assert merged["intents"][:len(base["intents"])] == base["intents"]
    assert merged["catalog_version"] == CATALOG_V11_VERSION
    assert merged["description"] == CATALOG_V11_DESCRIPTION
    assert merged["official_sources_v11"] == OFFICIAL_SOURCES
    assert len(merged["functions"]) == 1858
    assert len(merged["intents"]) == 1700
    validate_catalog_payload(merged)
    assert validate_v11_data(merged)["materialized"] is True
    assert merge_with_base(merged) == merged

    digest_one = hashlib.sha256(_serialized(merge_with_base(base))).hexdigest()
    digest_two = hashlib.sha256(_serialized(merge_with_base(copy.deepcopy(base)))).hexdigest()
    assert digest_one == digest_two

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v11-trial-") as temp_dir:
        temp = Path(temp_dir)
        merged_path = temp / "v11-trial.json"
        quality_payload = apply_alias_context_overrides(
            strip_alias_context_overrides(
                merge_v14_with_base(
                    merge_v13_with_base(merge_v12_with_base(merged))
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

        catalog = NavigationFunctionCatalog(temp / "v11.sqlite", merged_path)
        positive_count = 0
        function_by_id = {str(item["function_id"]): item for item in V11_FUNCTIONS}
        for probe in matrix:
            if probe["kind"] == "positive":
                plan = catalog.plan_goal(str(probe["text"]))
                assert plan.terminal_function == probe["expected_function"]
                definition = catalog.function(plan.terminal_function)
                assert definition is not None
                assert definition.automation_policy == "never_auto"
                assert definition.stop_policy == "before_action"
                positive_count += 1
            else:
                function = function_by_id[str(probe["excluded_function"])]
                positive_fields = {
                    str(value).casefold()
                    for value in (
                        *function["aliases"]["ko-KR"],
                        *function["aliases"]["en-US"],
                        *function["positive_context"],
                        *next(item for item in V11_INTENTS if item["terminal_function"] == probe["excluded_function"])["patterns"],
                    )
                }
                assert str(probe["text"]).casefold() not in positive_fields
        assert positive_count == 460

        collision_matches = 0
        for probe in collisions:
            plan = catalog.plan_goal(str(probe["text"]))
            assert plan.terminal_function == probe["expected_function"], probe
            collision_matches += 1
        assert collision_matches == 160

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V11_FUNCTIONS[0]))
    _expect_failure(partial, "partial v11")

    changed_function = copy.deepcopy(merged)
    changed_function["functions"][-1]["description"] = "conflicting v11 definition"
    _expect_failure(changed_function, "different function or intent definition")

    changed_intent = copy.deepcopy(merged)
    changed_intent["intents"][-1]["goal_rules"] = changed_intent["intents"][-1]["goal_rules"][:-1]
    _expect_failure(changed_intent, "different function or intent definition")

    changed_sources = copy.deepcopy(merged)
    changed_sources["official_sources_v11"] = {}
    _expect_failure(changed_sources, "official evidence registry")

    changed_metadata = copy.deepcopy(merged)
    changed_metadata["catalog_version"] = "11.0.0-modified"
    _expect_failure(changed_metadata, "materialization metadata")

    unsafe = copy.deepcopy(merged)
    unsafe["functions"][len(base["functions"]) + 1]["automation_policy"] = "auto_execute"
    _expect_failure(unsafe, "different function or intent definition")

    assert sum(len(group.features) for group in GROUPS) == 230
    print(
        "navigation catalog v11 data checks ok: "
        f"functions={stats['functions']} terminals={stats['terminal_functions']} "
        f"intents={stats['intents']} domains={stats['domains']} sources={stats['official_sources']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']} "
        f"sensitive={sensitive} state_changing={consequential} matrix={len(matrix)} "
        f"collisions={len(collisions)} quality=100 sha256={digest_one}"
    )


if __name__ == "__main__":
    main()
