from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from app.services.navigation_function_catalog import validate_catalog_payload  # noqa: E402
from navigation_catalog_v10_data import _rule_signature, _runtime_pattern_key  # noqa: E402
from navigation_catalog_v16_data import (  # noqa: E402
    CATALOG_V16_DESCRIPTION,
    CATALOG_V16_VERSION,
    COLLISION_FAMILIES,
    DOCUMENT_DIGESTS,
    DOMAIN_SOURCE_IDS,
    DOMAIN_TERMINAL_SOURCE_IDS,
    EXPECTED_DOMAIN_COUNTS,
    EXPECTED_SOURCE_DISTRIBUTION,
    FINAL_TERMINAL_IDS,
    OFFICIAL_SOURCES,
    PROJECTED_COUNTS,
    PUBLISHER_ALLOWLIST,
    REFINEMENTS,
    REFINEMENT_BY_OLD_ID,
    REFINEMENT_NEW_IDS,
    REFINEMENT_OLD_IDS,
    REFINEMENT_TERMINAL_SOURCE_IDS,
    REQUIRED_DOMAINS,
    REVIEWED_FEATURE_BY_ID,
    SOURCE_DOCUMENT_METADATA,
    SOURCE_DOCUMENT_SHA256,
    V16CatalogValidationError,
    V16_FUNCTIONS,
    V16_INTENTS,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_semantic_equivalence_report,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_equivalence_with_v16,
    merge_with_base,
    normalize_official_url,
    validate_v16_data,
)


EXPECTED_FUNCTIONS_SHA256 = "979560f5573d621843d703d4f65c85a36956f97b9b269f770a007bc5a70e8f50"
EXPECTED_INTENTS_SHA256 = "2991ecf160bc73fa9bea514fec2754679a70cc099b09b1c7f1bd1f7c7540ac68"
EXPECTED_SOURCES_SHA256 = "805329481362a0bd2f3abade57c64d7aebf5d5a645b48ae24b447b30ef88070c"
EXPECTED_REFINEMENT_SOURCE_MAP_SHA256 = "fa4f90e0a60c09714815da79502daf3356b57ef83f7b5c3ff48c832adb66fa93"
EXPECTED_MERGED_SHA256 = "95f9c6675bbbf63204197d11de8067f6b8057f66cb9491e0668f9e0c7d45ce95"


def _serialized(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_serialized(value)).hexdigest()


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v16_data(payload)
    except V16CatalogValidationError as error:
        assert fragment.casefold() in str(error).casefold(), str(error)
    else:
        raise AssertionError(f"invalid V16 payload accepted; expected {fragment!r}")


def main() -> None:
    assert DOCUMENT_DIGESTS == SOURCE_DOCUMENT_SHA256
    assert SOURCE_DOCUMENT_METADATA == {
        path: {"path": path, "algorithm": "sha256", "sha256": digest}
        for path, digest in SOURCE_DOCUMENT_SHA256.items()
    }
    assert len(SOURCE_DOCUMENT_SHA256) == 7
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected

    base = load_base_catalog()
    snapshot = copy.deepcopy(base)
    assert base["catalog_version"] == "15.0.0"
    assert len(base["functions"]) == 2866
    assert len(base["intents"]) == 2660
    assert len({str(item["domain"]) for item in base["functions"]}) == 179

    stats = validate_v16_data(base)
    assert stats == {
        "functions": 252,
        "terminal_functions": 240,
        "intents": 240,
        "domains": 12,
        "domain_terminal_counts": EXPECTED_DOMAIN_COUNTS,
        "sensitive_reads": 84,
        "state_changing": 156,
        "official_sources": 127,
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "source_documents": SOURCE_DOCUMENT_SHA256,
        "source_orphans": 0,
        "refinement_replacements": 16,
        "aliases": 7010,
        "goal_patterns": 8654,
        "goal_rules": 8880,
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

    function_ids = {str(item["function_id"]) for item in V16_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V16_FUNCTIONS if item["terminal"]}
    intent_ids = {str(item["intent_id"]) for item in V16_INTENTS}
    assert len(REQUIRED_DOMAINS) == 12
    assert len(V16_FUNCTIONS) == 252
    assert len(terminal_ids) == 240
    assert len(V16_INTENTS) == len(intent_ids) == 240
    assert terminal_ids == FINAL_TERMINAL_IDS
    assert not terminal_ids.intersection(REFINEMENT_OLD_IDS)
    assert REFINEMENT_NEW_IDS <= terminal_ids
    assert len(REFINEMENTS) == 16
    assert Counter(item.new_feature.classification for item in REFINEMENTS) == {"S": 1, "C": 15}
    assert all(
        old_id.split(".", 1)[0]
        == f"{old_id.split('.', 1)[0]}.{refinement.new_feature.key}".split(".", 1)[0]
        for old_id, refinement in REFINEMENT_BY_OLD_ID.items()
    )
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value) for value in function_ids)
    assert all(re.fullmatch(r"v16_[a-z0-9_]+", value) for value in intent_ids)

    base_function_ids = {str(item["function_id"]) for item in base["functions"]}
    base_intent_ids = {str(item["intent_id"]) for item in base["intents"]}
    base_domains = {str(item["domain"]) for item in base["functions"]}
    assert not function_ids.intersection(base_function_ids)
    assert not intent_ids.intersection(base_intent_ids)
    assert not REQUIRED_DOMAINS.intersection(base_domains)

    assert len(OFFICIAL_SOURCES) == 127
    assert set(DOMAIN_SOURCE_IDS) == REQUIRED_DOMAINS
    assert set(DOMAIN_TERMINAL_SOURCE_IDS) == terminal_ids
    assert {domain: len(values) for domain, values in DOMAIN_SOURCE_IDS.items()} == EXPECTED_SOURCE_DISTRIBUTION
    normalized_urls = [normalize_official_url(str(item["canonical_url"])) for item in OFFICIAL_SOURCES.values()]
    assert len(normalized_urls) == len(set(normalized_urls)) == 127
    assert all(value.startswith("https://") for value in normalized_urls)
    assert all(item["source_id"] == source_id for source_id, item in OFFICIAL_SOURCES.items())
    assert all(item["publisher"] in PUBLISHER_ALLOWLIST for item in OFFICIAL_SOURCES.values())
    assert all(item["verification_status"] == "accepted" for item in OFFICIAL_SOURCES.values())
    assert all(item["http_status"] == item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert all(item["final_url"] == item["canonical_url"] for item in OFFICIAL_SOURCES.values())
    assert all(item["terminal_ids"] for item in OFFICIAL_SOURCES.values())
    assert all(set(item["source_documents"]) <= set(SOURCE_DOCUMENT_SHA256) for item in OFFICIAL_SOURCES.values())
    referenced_sources = {source_id for values in DOMAIN_TERMINAL_SOURCE_IDS.values() for source_id in values}
    assert referenced_sources == set(OFFICIAL_SOURCES)
    assert all(DOMAIN_TERMINAL_SOURCE_IDS[terminal_id] for terminal_id in terminal_ids)
    assert all(DOMAIN_TERMINAL_SOURCE_IDS[terminal_id] == source_ids for terminal_id, source_ids in REFINEMENT_TERMINAL_SOURCE_IDS.items())

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
    for function in V16_FUNCTIONS:
        function_id = str(function["function_id"])
        assert len(function["aliases"]["ko-KR"]) >= 8
        assert len(function["aliases"]["en-US"]) >= 8
        assert len(function["positive_context"]) >= 6
        assert len(function["negative_context"]) >= 8
        assert len(function["role_hints"]) >= 2
        assert len(function["asset_cues"]) >= 2
        assert len(function["state_cues"]["lifecycle"]) >= 2
        assert function["state_cues"]["jurisdiction"]
        assert function["source_refs"] and set(function["source_refs"]) <= set(OFFICIAL_SOURCES)
        assert not forbidden.intersection(function)
        assert "v16_role_governed_operations" in function["legacy_tags"]
        if function["terminal"]:
            reviewed = REVIEWED_FEATURE_BY_ID[function_id]
            sensitive += function["classification"] == "S" and not bool(function["state_changing"])
            consequential += function["classification"] == "C" and bool(function["state_changing"])
            assert function["name_ko"] == reviewed.name_ko
            assert function["name_en"] == reviewed.name_en
            assert function["representative_goals"] == {"ko-KR": reviewed.goal_ko, "en-US": reviewed.goal_en}
            assert function["risk_level"] == "high"
            assert function["automation_policy"] == "never_auto"
            assert function["stop_policy"] == "before_action"
            assert function["user_owned_final_press"] is True
            assert set(function["source_refs"]) == set(DOMAIN_TERMINAL_SOURCE_IDS[function_id])
            assert function["risk_cues"]["role_asset_state_gate"]
            assert function["risk_cues"]["fail_closed"]
            assert function["risk_cues"]["source_boundary"]
            assert function["risk_cues"]["forbidden_terminal_actions"]
            assert function["risk_cues"]["blocked_final_channels"]
        else:
            assert function["node_kind"] == "hub"
            assert function["risk_level"] == "low"
            assert function["automation_policy"] == "safe_navigation"
            assert function["stop_policy"] == "continue"
            assert function["state_changing"] is False
            assert function["user_owned_final_press"] is False
    assert (sensitive, consequential) == (84, 156)

    pattern_keys: list[str] = []
    rule_signatures: list[tuple[object, ...]] = []
    for intent in V16_INTENTS:
        terminal_id = str(intent["terminal_function"])
        reviewed = REVIEWED_FEATURE_BY_ID[terminal_id]
        assert intent["patterns_by_locale"]["ko-KR"][0] == reviewed.goal_ko
        assert intent["patterns_by_locale"]["en-US"][0] == reviewed.goal_en
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 5
        assert len(intent["patterns_by_locale"]["en-US"]) >= 5
        assert len(intent["goal_rules"]) >= 20
        assert any(rule["rule_kind"] == "v16_role_asset_state_gate" for rule in intent["goal_rules"])
        assert all(str(rule["rule_kind"]).startswith("v16_") for rule in intent["goal_rules"])
        assert len(intent["route"]) == 2 and intent["route"][-1]["function_id"] == terminal_id
        assert intent["terminal_condition"] == {"stop_policy": "stop_before_action", "user_owned_final_press": True}
        assert intent["resolution_gate"]["minimum_positive_dimensions"] == (3 if reviewed.classification == "C" else 2)
        pattern_keys.extend(_runtime_pattern_key(value) for value in intent["patterns"])
        rule_signatures.extend(_rule_signature(rule) for rule in intent["goal_rules"])
    assert len(pattern_keys) == len(set(pattern_keys)) == 8654
    assert len(rule_signatures) == len(set(rule_signatures)) == 8880

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    reports = build_semantic_equivalence_report(base)
    assert len(COLLISION_FAMILIES) == 60
    assert len(semantic) == 1440
    assert len(collisions) == 720
    assert len(recovery) == 960
    assert len(isolation) == 720
    assert len(reports) == 240
    assert all(item["decision"] == "distinct_append" and not item["unresolved_findings"] for item in reports)
    assert all(item["expected_function"] in terminal_ids for item in collisions)
    assert all(item["required_policy"] == "never_auto" and item["required_stop_policy"] == "before_action" for item in recovery)
    assert all(item["expected_function"] is None and item["allowed_fallback"].endswith(".hub") for item in isolation)

    assert _digest(V16_FUNCTIONS) == EXPECTED_FUNCTIONS_SHA256
    assert _digest(V16_INTENTS) == EXPECTED_INTENTS_SHA256
    assert _digest(OFFICIAL_SOURCES) == EXPECTED_SOURCES_SHA256
    assert (
        _digest({terminal_id: DOMAIN_TERMINAL_SOURCE_IDS[terminal_id] for terminal_id in sorted(REFINEMENT_NEW_IDS)})
        == EXPECTED_REFINEMENT_SOURCE_MAP_SHA256
    )

    merged = merge_with_base(base)
    assert base == snapshot
    assert merged["catalog_version"] == CATALOG_V16_VERSION
    assert merged["description"] == CATALOG_V16_DESCRIPTION
    assert len(merged["functions"]) == 3118
    assert len(merged["intents"]) == 2900
    assert len({str(item["domain"]) for item in merged["functions"]}) == 191
    assert merged["functions"][: len(base["functions"])] == base["functions"]
    assert merged["intents"][: len(base["intents"])] == base["intents"]
    assert merged["official_sources_v16"] == OFFICIAL_SOURCES
    assert merged["source_documents_v16"] == SOURCE_DOCUMENT_METADATA
    assert merged["refinement_v16"]["old_ids"] == sorted(REFINEMENT_OLD_IDS)
    assert merged["refinement_v16"]["new_ids"] == sorted(REFINEMENT_NEW_IDS)
    merged_sha256 = _digest(merged)
    assert merged_sha256 == EXPECTED_MERGED_SHA256, merged_sha256
    validate_catalog_payload(merged)
    merged_snapshot = copy.deepcopy(merged)
    base_equivalence = json.loads(
        (ROOT / "fixtures/navigation/function-equivalence.v1.json").read_text(
            encoding="utf-8"
        )
    )
    merged_equivalence = merge_equivalence_with_v16(base_equivalence, merged)
    assert (
        validate_v16_data(merged, equivalence_payload=merged_equivalence)[
            "materialized"
        ]
        is True
    )
    # A materialized V16 catalog must be validated with its matching V16
    # equivalence ledger.  Falling back to the canonical on-disk V15 ledger
    # is intentionally rejected as a split-generation pair.
    assert merge_with_base(merged, merged_equivalence) == merged
    assert merged == merged_snapshot

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V16_FUNCTIONS[0]))
    _expect_failure(partial, "partial V16")
    partial = copy.deepcopy(merged)
    partial["intents"] = partial["intents"][:-1]
    _expect_failure(partial, "partial V16")
    tampered = copy.deepcopy(merged)
    tampered_terminal = next(item for item in tampered["functions"] if item.get("terminal") and item["function_id"] in terminal_ids)
    tampered_terminal["automation_policy"] = "auto"
    _expect_failure(tampered, "different function")
    tampered = copy.deepcopy(merged)
    tampered["official_sources_v16"] = copy.deepcopy(tampered["official_sources_v16"])
    tampered["official_sources_v16"].pop(next(iter(tampered["official_sources_v16"])))
    _expect_failure(tampered, "official-source registry")

    print(
        json.dumps(
            {
                "result": "PASS",
                "functions": 252,
                "terminals": 240,
                "intents": 240,
                "domains": 12,
                "sensitive": 84,
                "consequential": 156,
                "official_sources": 127,
                "source_orphans": 0,
                "refinements": 16,
                "semantic_probes": 1440,
                "collision_probes": 720,
                "recovery_probes": 960,
                "isolation_probes": 720,
                "equivalence_collisions": 0,
                "functions_sha256": EXPECTED_FUNCTIONS_SHA256,
                "intents_sha256": EXPECTED_INTENTS_SHA256,
                "sources_sha256": EXPECTED_SOURCES_SHA256,
                "merged_sha256": EXPECTED_MERGED_SHA256,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
