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
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v17_data import (  # noqa: E402
    CATALOG_V17_DESCRIPTION,
    CATALOG_V17_VERSION,
    COLLISION_FAMILIES,
    DOCUMENT_DIGESTS,
    DOMAIN_SOURCE_IDS,
    DOMAIN_TERMINAL_SOURCE_IDS,
    EXPECTED_CLASS_COUNTS,
    EXPECTED_DOMAIN_COUNTS,
    EXPECTED_DOMAIN_FUNCTION_COUNTS,
    EXPECTED_SOURCE_DISTRIBUTION,
    EXPECTED_V17_LAYER_SHA256,
    KOREAN_DOMAIN_TERMS,
    KOREAN_TERMINAL_IDS,
    OFFICIAL_SOURCES,
    PROJECTED_COUNTS,
    PUBLISHER_ALLOWLIST,
    REQUIRED_DOMAINS,
    REVIEWED_FEATURE_BY_ID,
    SOURCE_DOCUMENT_METADATA,
    SOURCE_DOCUMENT_SHA256,
    V17CatalogValidationError,
    V17_FUNCTIONS,
    V17_INTENTS,
    V17_LAYER_SHA256,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
    normalize_official_url,
    validate_v17_data,
)


def _serialized(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_serialized(value)).hexdigest()


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v17_data(payload)
    except V17CatalogValidationError as error:
        assert fragment.casefold() in str(error).casefold(), str(error)
    else:
        raise AssertionError(f"invalid V17 payload accepted; expected {fragment!r}")


def main() -> None:
    assert DOCUMENT_DIGESTS == SOURCE_DOCUMENT_SHA256
    assert SOURCE_DOCUMENT_METADATA == {
        path: {"path": path, "algorithm": "sha256", "sha256": digest}
        for path, digest in SOURCE_DOCUMENT_SHA256.items()
    }
    source_text = (ROOT / next(iter(SOURCE_DOCUMENT_SHA256))).read_text(encoding="utf-8")
    assert "\ufffd" not in source_text
    assert len(re.findall(r"[\uac00-\ud7a3]", source_text)) >= 100
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected
    assert V17_LAYER_SHA256 == EXPECTED_V17_LAYER_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", V17_LAYER_SHA256)

    function_ids = {str(item["function_id"]) for item in V17_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V17_FUNCTIONS if item["terminal"]}
    intent_ids = {str(item["intent_id"]) for item in V17_INTENTS}
    assert len(REQUIRED_DOMAINS) == 12
    assert len(V17_FUNCTIONS) == len(function_ids) == 240
    assert len(terminal_ids) == 228
    assert len(V17_INTENTS) == len(intent_ids) == 228
    assert Counter(str(item["domain"]) for item in V17_FUNCTIONS) == EXPECTED_DOMAIN_FUNCTION_COUNTS
    assert Counter(str(item["domain"]) for item in V17_FUNCTIONS if item["terminal"]) == EXPECTED_DOMAIN_COUNTS
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value) for value in function_ids)
    assert all(re.fullmatch(r"v17_[a-z0-9_]+", value) for value in intent_ids)

    hangul = re.compile(r"[\uac00-\ud7a3]")
    sensitive = consequential = 0
    for function in V17_FUNCTIONS:
        function_id = str(function["function_id"])
        assert "v17_public_case_operations" in function["legacy_tags"]
        assert hangul.search(str(function["name_ko"]))
        assert len(function["aliases"]["ko-KR"]) >= 8
        assert len(function["aliases"]["en-US"]) >= 8
        assert all(hangul.search(str(alias)) for alias in function["aliases"]["ko-KR"])
        assert function["role_hints"] and function["asset_cues"]
        assert function["state_cues"]["jurisdiction"]
        assert function["source_refs"] and set(function["source_refs"]) <= set(OFFICIAL_SOURCES)
        if function["terminal"]:
            reviewed = REVIEWED_FEATURE_BY_ID[function_id]
            sensitive += function["classification"] == "S" and not function["state_changing"]
            consequential += function["classification"] == "C" and function["state_changing"]
            assert function["name_ko"] == reviewed.name_ko
            assert function["name_en"] == reviewed.name_en
            assert function["representative_goals"] == {"ko-KR": reviewed.goal_ko, "en-US": reviewed.goal_en}
            assert function["purpose_by_locale"] == {"ko-KR": reviewed.purpose_ko, "en-US": reviewed.purpose_en}
            assert reviewed.roles and reviewed.assets and reviewed.states
            assert reviewed.jurisdiction_guard and reviewed.safety_boundary
            assert function["automation_policy"] == "never_auto"
            assert function["stop_policy"] == "before_action"
            assert function["risk_level"] == "high"
            assert function["user_owned_final_press"] is True
            assert set(function["source_refs"]) == set(DOMAIN_TERMINAL_SOURCE_IDS[function_id])
            assert function["risk_cues"]["source_boundary"] == [reviewed.safety_boundary]
        else:
            assert function["node_kind"] == "hub"
            assert function["automation_policy"] == "safe_navigation"
            assert function["stop_policy"] == "continue"
            assert function["user_owned_final_press"] is False
    assert {"S": sensitive, "C": consequential} == EXPECTED_CLASS_COUNTS

    for intent in V17_INTENTS:
        target = str(intent["terminal_function"])
        reviewed = REVIEWED_FEATURE_BY_ID[target]
        assert intent["patterns_by_locale"]["ko-KR"][0] == reviewed.goal_ko
        assert intent["patterns_by_locale"]["en-US"][0] == reviewed.goal_en
        assert all(hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"])
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 5
        assert len(intent["patterns_by_locale"]["en-US"]) >= 5
        assert len(intent["goal_rules"]) >= 20
        assert any(rule["rule_kind"] == "v17_role_asset_state_gate" for rule in intent["goal_rules"])
        assert intent["terminal_condition"] == {"stop_policy": "stop_before_action", "user_owned_final_press": True}
        assert intent["resolution_gate"]["minimum_positive_dimensions"] == (4 if reviewed.classification == "C" else 3)
    for terminal_id in KOREAN_TERMINAL_IDS:
        function = next(item for item in V17_FUNCTIONS if item["function_id"] == terminal_id)
        intent = next(item for item in V17_INTENTS if item["terminal_function"] == terminal_id)
        terms = KOREAN_DOMAIN_TERMS[str(function["domain"])]
        assert set(terms).intersection(function["aliases"]["ko-KR"])
        assert any(any(term in pattern for term in terms) for pattern in intent["patterns_by_locale"]["ko-KR"])

    assert len(OFFICIAL_SOURCES) == 73
    assert set(DOMAIN_SOURCE_IDS) == REQUIRED_DOMAINS
    assert set(DOMAIN_TERMINAL_SOURCE_IDS) == terminal_ids
    assert {domain: len(values) for domain, values in DOMAIN_SOURCE_IDS.items()} == EXPECTED_SOURCE_DISTRIBUTION
    normalized_urls = [normalize_official_url(str(item["canonical_url"])) for item in OFFICIAL_SOURCES.values()]
    assert len(normalized_urls) == len(set(normalized_urls)) == 73
    assert all(value.startswith("https://") for value in normalized_urls)
    assert all(item["source_id"] == source_id for source_id, item in OFFICIAL_SOURCES.items())
    assert all(item["publisher"] in PUBLISHER_ALLOWLIST for item in OFFICIAL_SOURCES.values())
    assert all(item["verification_status"] == "accepted" for item in OFFICIAL_SOURCES.values())
    assert all(item["http_status"] == item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert sum(item["jurisdiction"] == "KR" for item in OFFICIAL_SOURCES.values()) == 12
    assert all(sum(item["jurisdiction"] == "US" for item in OFFICIAL_SOURCES.values() if item["domains"] == [domain]) >= 5 for domain in REQUIRED_DOMAINS)
    referenced_sources = {source_id for values in DOMAIN_TERMINAL_SOURCE_IDS.values() for source_id in values}
    assert referenced_sources == set(OFFICIAL_SOURCES)

    assert len(COLLISION_FAMILIES) == 60
    assert len(build_semantic_development_matrix()) == 1368
    assert len(build_collision_probes()) == 720
    assert len(build_state_permission_recovery_matrix()) == 912
    assert len(build_role_asset_isolation_matrix()) == 684

    base = load_base_catalog()
    snapshot = copy.deepcopy(base)
    assert base["catalog_version"] == "16.0.0"
    assert len(base["functions"]) == 3118
    assert len(base["intents"]) == 2900
    assert len({str(item["domain"]) for item in base["functions"]}) == 191
    assert not function_ids.intersection(str(item["function_id"]) for item in base["functions"])
    assert not intent_ids.intersection(str(item["intent_id"]) for item in base["intents"])
    assert not REQUIRED_DOMAINS.intersection(str(item["domain"]) for item in base["functions"])

    stats = validate_v17_data(base)
    assert stats["functions"] == 240
    assert stats["terminal_functions"] == 228
    assert stats["intents"] == 228
    assert stats["domains"] == 12
    assert stats["official_sources"] == 73
    assert stats["korean_sources"] == 12
    assert stats["source_orphans"] == 0
    assert stats["layer_sha256"] == EXPECTED_V17_LAYER_SHA256
    assert stats["projected_counts"] == PROJECTED_COUNTS
    assert stats["materialized"] is False
    assert base == snapshot

    merged = merge_with_base(base)
    assert base == snapshot
    assert merged["catalog_version"] == CATALOG_V17_VERSION
    assert merged["description"] == CATALOG_V17_DESCRIPTION
    assert len(merged["functions"]) == 3358
    assert len(merged["intents"]) == 3128
    assert len({str(item["domain"]) for item in merged["functions"]}) == 203
    assert merged["layer_integrity_v17"]["sha256"] == EXPECTED_V17_LAYER_SHA256
    assert validate_v17_data(merged)["materialized"] is True
    assert _digest(merge_with_base(merged)) == _digest(merged)

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V17_FUNCTIONS[0]))
    _expect_failure(partial, "partial V17")

    tampered_function = copy.deepcopy(merged)
    next(item for item in tampered_function["functions"] if item["function_id"] in terminal_ids)["name_ko"] += " 변조"
    _expect_failure(tampered_function, "different function")

    tampered_source = copy.deepcopy(merged)
    first_source = next(iter(tampered_source["official_sources_v17"]))
    tampered_source["official_sources_v17"][first_source]["title"] += " tampered"
    _expect_failure(tampered_source, "official-source registry")

    tampered_hash = copy.deepcopy(merged)
    tampered_hash["layer_integrity_v17"]["sha256"] = "0" * 64
    _expect_failure(tampered_hash, "layer-integrity")

    print(
        json.dumps(
            {
                "status": "ok",
                "layer_sha256": EXPECTED_V17_LAYER_SHA256,
                "source_sha256": _digest(OFFICIAL_SOURCES),
                "functions": 240,
                "terminals": 228,
                "intents": 228,
                "domains": 12,
                "official_sources": 73,
                "korean_sources": 12,
                "semantic_probes": 1368,
                "collision_probes": 720,
                "recovery_probes": 912,
                "isolation_probes": 684,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
