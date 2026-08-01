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
from navigation_catalog_v15_data import (  # noqa: E402
    CATALOG_V15_DESCRIPTION,
    CATALOG_V15_VERSION,
    COLLECTED_ON,
    COLLISION_FAMILIES,
    DESIGN_SOURCE_PATH,
    DOMAIN_SOURCE_IDS,
    DOMAIN_TERMINAL_SOURCE_IDS,
    EXPECTED_DOMAIN_COUNTS,
    EXPECTED_SOURCE_DISTRIBUTION,
    GROUPS,
    OFFICIAL_SOURCES,
    PROJECTED_COUNTS,
    PUBLISHER_ALLOWLIST,
    REQUIRED_DOMAINS,
    RETRIEVED_AT,
    REVIEWED_FEATURE_BY_ID,
    SOURCE_DOCUMENT_METADATA,
    SOURCE_DOCUMENT_SHA256,
    V15CatalogValidationError,
    V15_FUNCTIONS,
    V15_INTENTS,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_semantic_equivalence_report,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
    normalize_official_url,
    validate_v15_data,
)
from navigation_catalog_v16_data import (  # noqa: E402
    merge_with_base as merge_v16_with_base,
)


def _serialized(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_serialized(value)).hexdigest()


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v15_data(payload)
    except V15CatalogValidationError as error:
        assert fragment in str(error), str(error)
    else:
        raise AssertionError(f"invalid v15 payload accepted; expected {fragment!r}")


def _load_temporary_catalog(payload: dict[str, object]) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="exitguide-v15-future-loader-") as temp_dir:
        path = Path(temp_dir) / "function-catalog.v1.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return load_base_catalog(path)


def _expect_loader_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        _load_temporary_catalog(payload)
    except V15CatalogValidationError as error:
        assert fragment.casefold() in str(error).casefold(), str(error)
    else:
        raise AssertionError(
            f"invalid future catalog accepted by V15 loader; expected {fragment!r}"
        )


def main() -> None:
    actual_source_sha = hashlib.sha256(DESIGN_SOURCE_PATH.read_bytes()).hexdigest()
    assert actual_source_sha == SOURCE_DOCUMENT_SHA256
    assert SOURCE_DOCUMENT_METADATA == {
        "path": "docs/NAVIGATION_COVERAGE_GAPS_V15.md",
        "algorithm": "sha256",
        "sha256": SOURCE_DOCUMENT_SHA256,
    }

    base = load_base_catalog()
    snapshot = copy.deepcopy(base)
    base_functions_hash = _digest(base["functions"])
    base_intents_hash = _digest(base["intents"])
    assert base["catalog_version"] == "14.0.0"
    assert len(base["functions"]) == 2614
    assert len(base["intents"]) == 2420
    assert len({str(item["domain"]) for item in base["functions"]}) == 167

    # Synthesize the exact storage shape that the canonical materializer will
    # produce after V16 promotion: clean V15 source, complete V16 append, then
    # one global alias/context override pass.  V15 must recover the byte-model
    # equivalent V14 projection without importing the V16 module itself.
    canonical_path = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
    canonical_before = canonical_path.read_bytes()
    canonical_v15 = json.loads(canonical_before.decode("utf-8"))
    v16_source = merge_v16_with_base(
        strip_alias_context_overrides(canonical_v15)
    )
    materialized_v16 = apply_alias_context_overrides(v16_source)
    recovered_v14 = _load_temporary_catalog(materialized_v16)
    assert recovered_v14 == base
    assert _digest(recovered_v14) == _digest(base)
    assert _digest(recovered_v14["functions"]) == base_functions_hash
    assert _digest(recovered_v14["intents"]) == base_intents_hash
    assert recovered_v14["catalog_version"] == "14.0.0"
    assert len(recovered_v14["functions"]) == 2614
    assert len(recovered_v14["intents"]) == 2420
    assert len({str(item["domain"]) for item in recovered_v14["functions"]}) == 167
    assert recovered_v14.get("alias_context_overrides") == base.get(
        "alias_context_overrides"
    )
    assert all(key not in recovered_v14 for key in (
        "official_sources_v16",
        "source_documents_v16",
        "semantic_equivalence_v16",
        "refinement_v16",
    ))
    assert not any(
        "v16_role_governed_operations" in item.get("legacy_tags", [])
        for item in recovered_v14["functions"]
    )
    assert not any(
        str(item["intent_id"]).startswith("v16_")
        for item in recovered_v14["intents"]
    )

    partial_source = copy.deepcopy(v16_source)
    partial_source["intents"].remove(
        next(
            item
            for item in partial_source["intents"]
            if str(item["intent_id"]).startswith("v16_")
        )
    )
    _expect_loader_failure(
        apply_alias_context_overrides(partial_source),
        "partial/mixed V16",
    )

    changed_marker_source = copy.deepcopy(v16_source)
    changed_marker_function = next(
        item
        for item in changed_marker_source["functions"]
        if "v16_role_governed_operations" in item.get("legacy_tags", [])
    )
    marker_index = changed_marker_function["legacy_tags"].index(
        "v16_role_governed_operations"
    )
    changed_marker_function["legacy_tags"][marker_index] = (
        "v16_role_governed_operations_modified"
    )
    _expect_loader_failure(
        apply_alias_context_overrides(changed_marker_source),
        "partial/mixed V16",
    )

    missing_metadata_source = copy.deepcopy(v16_source)
    missing_metadata_source.pop("refinement_v16")
    _expect_loader_failure(
        apply_alias_context_overrides(missing_metadata_source),
        "partial/mixed V16",
    )

    changed_document_source = copy.deepcopy(v16_source)
    first_document = next(iter(changed_document_source["source_documents_v16"].values()))
    first_document["sha256"] = "0" * 64
    _expect_loader_failure(
        apply_alias_context_overrides(changed_document_source),
        "source-document metadata",
    )

    changed_override = copy.deepcopy(materialized_v16)
    changed_override["alias_context_overrides"]["source_catalog_sha256"] = "0" * 64
    _expect_loader_failure(changed_override, "alias context override")
    assert canonical_path.read_bytes() == canonical_before

    stats = validate_v15_data(base)
    assert stats == {
        **stats,
        "functions": 252,
        "terminal_functions": 240,
        "intents": 240,
        "domains": 12,
        "domain_terminal_counts": EXPECTED_DOMAIN_COUNTS,
        "official_sources": 131,
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "source_sha256": SOURCE_DOCUMENT_SHA256,
        "sensitive_reads": 84,
        "state_changing": 156,
        "semantic_smoke_probes": 1440,
        "collision_probes": 720,
        "recovery_probes": 960,
        "isolation_probes": 720,
        "equivalence_reports": 240,
        "equivalence_collisions": 0,
        "projected_counts": PROJECTED_COUNTS,
        "materialized": False,
    }
    assert base == snapshot

    base_function_ids = {str(item["function_id"]) for item in base["functions"]}
    base_intent_ids = {str(item["intent_id"]) for item in base["intents"]}
    base_domain_ids = {str(item["domain"]) for item in base["functions"]}
    function_ids = {str(item["function_id"]) for item in V15_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V15_FUNCTIONS if item["terminal"]}
    intent_ids = {str(item["intent_id"]) for item in V15_INTENTS}
    assert len(REQUIRED_DOMAINS) == 12
    assert len(V15_FUNCTIONS) == 252
    assert len(terminal_ids) == 240
    assert len(V15_INTENTS) == 240
    assert {str(item["terminal_function"]) for item in V15_INTENTS} == terminal_ids
    assert not function_ids.intersection(base_function_ids)
    assert not intent_ids.intersection(base_intent_ids)
    assert not REQUIRED_DOMAINS.intersection(base_domain_ids)
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value) for value in function_ids)
    assert all(re.fullmatch(r"v15_[a-z0-9_]+", value) for value in intent_ids)
    assert all(
        str(rule["rule_kind"]).startswith("v15_")
        and "v15_discriminative_keys" in rule
        and "v14_discriminative_keys" not in rule
        for intent in V15_INTENTS
        for rule in intent["goal_rules"]
    )
    assert all(
        "v15_role_governed_operations" in item["legacy_tags"]
        and "v14_role_governed_operations" not in item["legacy_tags"]
        for item in V15_FUNCTIONS
    )

    assert len(OFFICIAL_SOURCES) == 131
    normalized_urls = [normalize_official_url(str(item["canonical_url"])) for item in OFFICIAL_SOURCES.values()]
    assert len(set(normalized_urls)) == 131
    assert all(value.startswith("https://") for value in normalized_urls)
    assert all(item["source_id"] == source_id for source_id, item in OFFICIAL_SOURCES.items())
    assert all(item["publisher"] in PUBLISHER_ALLOWLIST for item in OFFICIAL_SOURCES.values())
    assert all(item["collected_on"] == COLLECTED_ON for item in OFFICIAL_SOURCES.values())
    assert all(item["retrieved_at"] == RETRIEVED_AT for item in OFFICIAL_SOURCES.values())
    assert all(item["http_status"] == item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())
    assert all(item["verification_status"] == "accepted" for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert all(item["final_url"] == item["canonical_url"] for item in OFFICIAL_SOURCES.values())
    assert all(item["mime_type"] in {"text/html", "application/pdf"} for item in OFFICIAL_SOURCES.values())
    assert all(re.fullmatch(r"[0-9a-f]{64}", str(item["source_record_sha256"])) for item in OFFICIAL_SOURCES.values())
    assert all(item["content_hash_status"] == "not_materialized_by_source_plan" for item in OFFICIAL_SOURCES.values())
    assert all(
        item["supported_roles"]
        and item["supported_assets"]
        and item["supported_states"]
        and item["jurisdiction"]
        and item["terminal_ids"]
        for item in OFFICIAL_SOURCES.values()
    )
    assert set(DOMAIN_SOURCE_IDS) == REQUIRED_DOMAINS
    assert {domain: len(values) for domain, values in DOMAIN_SOURCE_IDS.items()} == EXPECTED_SOURCE_DISTRIBUTION
    assert set(DOMAIN_TERMINAL_SOURCE_IDS) == terminal_ids
    assert all(
        set().union(*(set(OFFICIAL_SOURCES[source_id]["terminal_ids"]) for source_id in source_ids))
        == {f"{domain}.{row.key}" for row in next(item for item in GROUPS if item.domain == domain).features}
        for domain, source_ids in DOMAIN_SOURCE_IDS.items()
    )

    sensitive = 0
    consequential = 0
    forbidden = {
        "x",
        "y",
        "bounds",
        "coordinate",
        "coordinates",
        "package",
        "package_name",
        "resource_id",
        "screenshot_hash",
        "screen_path",
        "recorded_path",
        "fixed_ui_path",
        "pixel",
        "click_sequence",
    }
    for item in V15_FUNCTIONS:
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
            reviewed = REVIEWED_FEATURE_BY_ID[str(item["function_id"])]
            sensitive += item["classification"] == "S" and not bool(item["state_changing"])
            consequential += item["classification"] == "C" and bool(item["state_changing"])
            assert item["name_ko"] == reviewed.name_ko
            assert item["name_en"] == reviewed.name_en
            assert item["representative_goals"] == {"ko-KR": reviewed.goal_ko, "en-US": reviewed.goal_en}
            assert item["risk_level"] == "high"
            assert item["automation_policy"] == "never_auto"
            assert item["stop_policy"] == "before_action"
            assert item["user_owned_final_press"] is True
            assert set(item["source_refs"]) == set(DOMAIN_TERMINAL_SOURCE_IDS[str(item["function_id"])])
            boundary = " ".join(item["risk_cues"]["user_boundary"])
            assert "사용자" in boundary and "user" in boundary.casefold() and "press" in boundary.casefold()
            assert item["risk_cues"]["role_asset_state_gate"]
            assert item["risk_cues"]["fail_closed"]
            assert item["risk_cues"]["forbidden_terminal_actions"]
            assert item["risk_cues"]["blocked_final_channels"]
        else:
            assert item["node_kind"] == "hub"
            assert item["risk_level"] == "low"
            assert item["automation_policy"] == "safe_navigation"
            assert item["stop_policy"] == "continue"
            assert item["state_changing"] is False
            assert item["user_owned_final_press"] is False
    assert (sensitive, consequential) == (84, 156)

    for item in V15_INTENTS:
        reviewed = REVIEWED_FEATURE_BY_ID[str(item["terminal_function"])]
        assert item["patterns_by_locale"]["ko-KR"][0] == reviewed.goal_ko
        assert item["patterns_by_locale"]["en-US"][0] == reviewed.goal_en
        assert len(item["patterns_by_locale"]["ko-KR"]) >= 5
        assert len(item["patterns_by_locale"]["en-US"]) >= 5
        assert len(item["goal_rules"]) >= 24
        assert any(rule["rule_kind"] == "v15_compositional_domain" for rule in item["goal_rules"])
        assert any(rule["rule_kind"] == "v15_consequence_context" for rule in item["goal_rules"])
        assert any(rule["rule_kind"] == "v15_role_asset_state_gate" for rule in item["goal_rules"])
        assert len(item["route"]) == 2
        assert item["route"][-1]["function_id"] == item["terminal_function"]
        assert len(item["avoid_functions"]) >= 2
        assert item["terminal_function"] not in item["avoid_functions"]
        assert item["resolution_gate"]["minimum_positive_dimensions"] == (
            3 if reviewed.classification == "C" else 2
        )
        assert item["desired_state"] == "user_confirmation_required"
        assert item["terminal_condition"] == {
            "stop_policy": "stop_before_action",
            "user_owned_final_press": True,
        }

    matrix = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    reports = build_semantic_equivalence_report(base)
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
        "disabled",
        "unavailable_offline",
        "wrong_role",
        "wrong_record_asset",
    }
    assert all(item["required_user_owned_final_press"] is True for item in recovery)
    assert len(isolation) == 720
    assert {item["kind"] for item in isolation} == {"wrong_role", "wrong_asset", "wrong_state"}
    assert len(reports) == 240
    assert all(item["decision"] == "distinct_append" and not item["unresolved_findings"] for item in reports)
    assert all(not item["exact_match"] for item in reports)
    assert all(not item["equivalence_class"]["is_member"] for item in reports)

    merged = merge_with_base(base)
    assert base == snapshot
    assert merged["catalog_version"] == CATALOG_V15_VERSION
    assert merged["description"] == CATALOG_V15_DESCRIPTION
    assert merged["official_sources_v15"] == OFFICIAL_SOURCES
    assert merged["source_document_v15"] == SOURCE_DOCUMENT_METADATA
    assert merged["semantic_equivalence_v15"] == list(reports)
    assert len(merged["functions"]) == PROJECTED_COUNTS["physical_functions"]
    assert len(merged["intents"]) == PROJECTED_COUNTS["physical_intents"]
    assert len({str(item["domain"]) for item in merged["functions"]}) == PROJECTED_COUNTS["domains"]
    assert sum(bool(item["terminal"]) for item in merged["functions"]) == PROJECTED_COUNTS[
        "physical_terminal_functions"
    ]
    assert merged["functions"][: len(base["functions"])] == base["functions"]
    assert merged["intents"][: len(base["intents"])] == base["intents"]
    assert _digest(merged["functions"][: len(base["functions"])]) == base_functions_hash
    assert _digest(merged["intents"][: len(base["intents"])]) == base_intents_hash
    validate_catalog_payload(merged)
    assert validate_v15_data(merged)["materialized"] is True
    assert merge_with_base(merged) == merged

    clean_second = merge_with_base(copy.deepcopy(base))
    digest_one = _digest(merged)
    digest_two = _digest(clean_second)
    assert clean_second == merged
    assert digest_one == digest_two
    sources_hash = _digest(OFFICIAL_SOURCES)
    report_hash = _digest(reports)

    merged_function_ids = {str(item["function_id"]) for item in merged["functions"]}
    assert all(set(str(value) for value in intent["avoid_functions"]) <= merged_function_ids for intent in V15_INTENTS)

    policy_path = ROOT / "fixtures" / "navigation" / "catalog-quality-policy.v2.json"
    with tempfile.TemporaryDirectory(prefix="exitguide-v15-source-") as temp_dir:
        temp = Path(temp_dir)
        merged_path = temp / "v15-source.json"
        quality_payload = apply_alias_context_overrides(strip_alias_context_overrides(merged))
        merged_path.write_text(json.dumps(quality_payload, ensure_ascii=False), encoding="utf-8")
        quality = audit_navigation_catalog(merged_path, policy_path)
        assert quality["quality_score"] == 100.0, quality
        assert quality["severity_counts"] == {}
        assert quality["goal_pattern_collisions"] == []

        catalog = NavigationFunctionCatalog(temp / "v15.sqlite", merged_path)
        positive_count = 0
        function_by_id = {str(item["function_id"]): item for item in V15_FUNCTIONS}
        intent_by_function = {str(item["terminal_function"]): item for item in V15_INTENTS}
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
                        *function["aliases"]["ko-KR"],
                        *function["aliases"]["en-US"],
                        *function["positive_context"],
                        *intent["patterns"],
                    )
                }
                assert str(probe["text"]).casefold() not in positive_fields
        assert positive_count == 480

        for probe in collisions:
            plan = catalog.plan_goal(str(probe["text"]))
            assert plan.terminal_function == probe["expected_function"], probe

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V15_FUNCTIONS[0]))
    _expect_failure(partial, "partial v15")

    changed_function = copy.deepcopy(merged)
    changed_function["functions"][-1]["description"] = "conflicting v15 definition"
    _expect_failure(changed_function, "different function or intent definition")

    changed_intent = copy.deepcopy(merged)
    changed_intent["intents"][-1]["goal_rules"] = changed_intent["intents"][-1]["goal_rules"][:-1]
    _expect_failure(changed_intent, "different function or intent definition")

    changed_sources = copy.deepcopy(merged)
    changed_sources["official_sources_v15"] = {}
    _expect_failure(changed_sources, "official evidence registry")

    changed_source_sha = copy.deepcopy(merged)
    changed_source_sha["source_document_v15"]["sha256"] = "0" * 64
    _expect_failure(changed_source_sha, "source document SHA metadata")

    changed_report = copy.deepcopy(merged)
    changed_report["semantic_equivalence_v15"][0]["decision"] = "reject"
    _expect_failure(changed_report, "semantic equivalence report")

    changed_metadata = copy.deepcopy(merged)
    changed_metadata["catalog_version"] = "15.0.0-modified"
    _expect_failure(changed_metadata, "materialization metadata")

    unsafe = copy.deepcopy(merged)
    unsafe["functions"][len(base["functions"]) + 1]["automation_policy"] = "auto_execute"
    _expect_failure(unsafe, "different function or intent definition")

    assert sum(len(group.features) for group in GROUPS) == 240
    print(
        "navigation catalog v15 source checks ok: "
        f"functions={stats['functions']} terminals={stats['terminal_functions']} "
        f"intents={stats['intents']} domains={stats['domains']} sources={stats['official_sources']} "
        f"aliases={stats['aliases']} patterns={stats['goal_patterns']} rules={stats['goal_rules']} "
        f"sensitive={sensitive} state_changing={consequential} matrix={len(matrix)} "
        f"collisions={len(collisions)} recovery={len(recovery)} isolation={len(isolation)} "
        f"equivalence_reports={len(reports)} equivalence_collisions=0 quality=100 "
        f"source_sha256={SOURCE_DOCUMENT_SHA256} sources_sha256={sources_hash} "
        f"report_sha256={report_hash} v14_functions_sha256={base_functions_hash} "
        f"v14_intents_sha256={base_intents_hash} catalog_sha256={digest_one}"
    )


if __name__ == "__main__":
    main()
