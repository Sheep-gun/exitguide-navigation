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

from navigation_catalog_v20_data import (  # noqa: E402
    BASELINE_COUNTS,
    BASE_LAYER_SEAL,
    BASE_PAYLOAD_SEAL,
    CATALOG_V20_DESCRIPTION,
    CATALOG_V20_VERSION,
    COLLISION_FAMILIES,
    DOCUMENT_DIGESTS,
    DOMAIN_SOURCE_IDS,
    DOMAIN_TERMINAL_SOURCE_IDS,
    EXPECTED_BASE_PAYLOAD_SHA256,
    EXPECTED_CLASS_COUNTS,
    EXPECTED_DOMAIN_COUNTS,
    EXPECTED_DOMAIN_FUNCTION_COUNTS,
    EXPECTED_INHERITED_REFERENCE_COUNTS,
    EXPECTED_OFFICIAL_SOURCES_SHA256,
    EXPECTED_PROBE_COUNTS,
    EXPECTED_SOURCE_DISTRIBUTION,
    EXPECTED_V20_LAYER_SHA256,
    KOREAN_DOMAIN_TERMS,
    KOREAN_TERMINAL_IDS,
    INHERITED_REFERENCE_CORRECTIONS,
    INHERITED_REFERENCE_CORRECTION_BY_BAD_ID,
    INHERITED_REFERENCE_CORRECTION_SHA256,
    INHERITED_REFERENCE_PREIMAGE,
    INHERITED_REFERENCE_PREIMAGE_SHA256,
    NEAREST_EXISTING_FUNCTIONS,
    OFFICIAL_SOURCES,
    OFFICIAL_SOURCES_SHA256,
    PROJECTED_COUNTS,
    PUBLISHER_ALLOWLIST,
    REJECTED_DUPLICATE_FAMILIES,
    REQUIRED_DOMAINS,
    REVIEWED_DOMAINS,
    REVIEWED_FEATURE_BY_ID,
    SOURCE_DOCUMENT_METADATA,
    SOURCE_DOCUMENT_SHA256,
    V20CatalogValidationError,
    V20_FUNCTIONS,
    V20_INTENTS,
    V20_LAYER_SHA256,
    WITHIN_V20_COLLISIONS,
    _digest,
    _apply_inherited_reference_corrections,
    _function_semantic_dimensions,
    _pre_v20_payload,
    _research_direct_urls,
    _research_proposed_terminal_ids,
    _research_rejected_candidate_labels,
    build_collision_probes,
    build_role_asset_isolation_matrix,
    build_semantic_development_matrix,
    build_state_permission_recovery_matrix,
    load_base_catalog,
    merge_with_base,
    normalize_official_url,
    validate_v20_data,
)


EXPECTED_DOMAINS = {
    "workers_compensation_claimant_services",
    "paid_family_medical_leave_claimant_services",
    "foster_adoption_family_services",
    "consumer_bankruptcy_case_services",
    "workplace_leave_accommodation_services",
    "long_term_services_supports_case_services",
    "child_care_assistance_case_services",
    "special_education_family_services",
}


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v20_data(payload)
    except V20CatalogValidationError as error:
        assert fragment.casefold() in str(error).casefold(), str(error)
    else:
        raise AssertionError(f"invalid V20 payload accepted; expected {fragment!r}")


def main() -> None:
    assert DOCUMENT_DIGESTS == SOURCE_DOCUMENT_SHA256
    assert SOURCE_DOCUMENT_METADATA == {
        path: {"path": path, "algorithm": "sha256", "sha256": digest}
        for path, digest in SOURCE_DOCUMENT_SHA256.items()
    }
    source_text = (ROOT / next(iter(SOURCE_DOCUMENT_SHA256))).read_text(encoding="utf-8")
    assert "\ufffd" not in source_text
    # The authoritative research memo contains English plus pinned typographic
    # punctuation only; Korean localization is independently authored below.
    assert len(re.findall(r"[\uac00-\ud7a3]", source_text)) == 0
    assert {
        ord(character) for character in source_text if ord(character) > 127
    } == {0x2013, 0x2014, 0x201C, 0x201D}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected
    assert BASE_LAYER_SEAL == {
        "catalog_version": "19.0.0",
        "algorithm": "sha256",
        "sha256": "4438e2745075abc00a4d4adeb3aac661c1417affb24835c6955e09f353197587",
    }
    assert BASE_PAYLOAD_SEAL == {
        "algorithm": "sha256",
        "sha256": "e7d7d53145e1769a0320716014b9bfdc7ce8e700bed82f3aab606732ededd5b1",
    }
    assert OFFICIAL_SOURCES_SHA256 == EXPECTED_OFFICIAL_SOURCES_SHA256
    assert OFFICIAL_SOURCES_SHA256 == _digest(OFFICIAL_SOURCES)
    assert V20_LAYER_SHA256 == EXPECTED_V20_LAYER_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", V20_LAYER_SHA256)

    function_ids = {str(item["function_id"]) for item in V20_FUNCTIONS}
    terminal_ids = {
        str(item["function_id"]) for item in V20_FUNCTIONS if item["terminal"]
    }
    intent_ids = {str(item["intent_id"]) for item in V20_INTENTS}
    assert REQUIRED_DOMAINS == EXPECTED_DOMAINS
    assert len(REVIEWED_DOMAINS) == len(REQUIRED_DOMAINS) == 8
    assert len(V20_FUNCTIONS) == len(function_ids) == 136
    assert len(terminal_ids) == 128
    assert len(V20_INTENTS) == len(intent_ids) == 128
    assert len(_research_proposed_terminal_ids(source_text)) == 128
    assert set(_research_proposed_terminal_ids(source_text)) == terminal_ids
    assert Counter(str(item["domain"]) for item in V20_FUNCTIONS) == EXPECTED_DOMAIN_FUNCTION_COUNTS
    assert Counter(
        str(item["domain"]) for item in V20_FUNCTIONS if item["terminal"]
    ) == EXPECTED_DOMAIN_COUNTS
    assert sorted(EXPECTED_DOMAIN_COUNTS.values()) == [15, 15, 16, 16, 16, 16, 17, 17]
    assert sum(EXPECTED_DOMAIN_COUNTS.values()) == 128
    assert set(REVIEWED_FEATURE_BY_ID) == terminal_ids

    assert len(REJECTED_DUPLICATE_FAMILIES) == 16
    assert len(set(REJECTED_DUPLICATE_FAMILIES)) == 16
    assert len(_research_rejected_candidate_labels(source_text)) == 16
    assert len(COLLISION_FAMILIES) == 47
    assert len(WITHIN_V20_COLLISIONS) == 12
    assert all(left in REQUIRED_DOMAINS and right in REQUIRED_DOMAINS for left, right, _ in WITHIN_V20_COLLISIONS)
    assert len(INHERITED_REFERENCE_CORRECTIONS) == 54
    assert len(INHERITED_REFERENCE_CORRECTION_BY_BAD_ID) == 54
    assert len(INHERITED_REFERENCE_PREIMAGE) == 354
    assert sum(map(len, INHERITED_REFERENCE_PREIMAGE.values())) == 1314
    assert sum(bool(item.replacements) for item in INHERITED_REFERENCE_CORRECTIONS) == 46
    assert sum(not item.replacements for item in INHERITED_REFERENCE_CORRECTIONS) == 8
    assert re.fullmatch(r"[0-9a-f]{64}", INHERITED_REFERENCE_CORRECTION_SHA256)
    assert re.fullmatch(r"[0-9a-f]{64}", INHERITED_REFERENCE_PREIMAGE_SHA256)

    assert len(OFFICIAL_SOURCES) == 63
    assert len(_research_direct_urls(source_text)) == 63
    assert _research_direct_urls(source_text) == {
        str(source["normalized_url"]) for source in OFFICIAL_SOURCES.values()
    }
    assert set(DOMAIN_SOURCE_IDS) == REQUIRED_DOMAINS
    assert set(DOMAIN_TERMINAL_SOURCE_IDS) == terminal_ids
    assert KOREAN_TERMINAL_IDS == terminal_ids
    assert EXPECTED_SOURCE_DISTRIBUTION == {
        domain: (7 if domain == "workers_compensation_claimant_services" else 8)
        for domain in sorted(REQUIRED_DOMAINS)
    }
    for source_id, source in OFFICIAL_SOURCES.items():
        assert source_id == source["source_id"]
        assert source["publisher"] in PUBLISHER_ALLOWLIST
        assert source["provider_scope"] == source["publisher"]
        assert source["verification_status"] == "accepted"
        assert source["evidence_level"] == "official_primary"
        assert source["http_status"] == source["verified_status"] == 200
        assert source["normalized_url"] == normalize_official_url(str(source["canonical_url"]))
        assert source["terminal_ids"]
        assert set(source["terminal_ids"]) <= terminal_ids

    classes = Counter(
        str(item["classification"]) for item in V20_FUNCTIONS if item["terminal"]
    )
    assert classes == EXPECTED_CLASS_COUNTS
    hangul = re.compile(r"[\uac00-\ud7a3]")
    semantic_signatures = []
    for function in V20_FUNCTIONS:
        domain = str(function["domain"])
        assert function["source_refs"]
        assert function["provider_scopes"]
        assert function["role_hints"]
        assert function["asset_cues"]
        assert function["state_cues"]["jurisdiction"]
        assert len(function["aliases"]["ko-KR"]) >= 8
        assert len(function["aliases"]["en-US"]) >= 8
        assert all(hangul.search(str(alias)) for alias in function["aliases"]["ko-KR"])
        if function["terminal"]:
            assert function["automation_policy"] == "never_auto"
            assert function["stop_policy"] == "before_action"
            assert function["risk_level"] == "high"
            assert function["user_owned_final_press"] is True
            assert function["classification"] in {"S", "C"}
            assert function["view_only"] is (function["classification"] == "S")
            assert function["state_changing"] is (function["classification"] == "C")
            assert function["consequential"] is (function["classification"] == "C")
            assert function["semantic_scope"]["roles"]
            assert function["semantic_scope"]["assets"]
            assert function["semantic_scope"]["states"]
            assert function["semantic_scope"]["jurisdiction"]
            assert set(function["source_refs"]) == set(
                DOMAIN_TERMINAL_SOURCE_IDS[str(function["function_id"])]
            )
            semantic_signatures.append(_function_semantic_dimensions(function))
        else:
            assert str(function["function_id"]) == f"{domain}.hub"
            assert function["node_kind"] == "hub"
            assert function["fail_closed"] is True
            assert function["resolution_policy"] == "fail_closed"
            assert function["requires_explicit_terminal_disambiguation"] is True
            assert function["automation_policy"] == "safe_navigation"
            assert function["stop_policy"] == "continue"
            assert function["state_changing"] is False
            assert function["user_owned_final_press"] is False
    assert len(set(map(repr, semantic_signatures))) == 128

    for intent in V20_INTENTS:
        target = str(intent["terminal_function"])
        domain = target.split(".", 1)[0]
        assert intent["intent_id"] == f"v20_{target.replace('.', '_')}"
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 5
        assert len(intent["patterns_by_locale"]["en-US"]) >= 5
        assert all(hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"])
        assert intent["route"][-1]["function_id"] == target
        assert intent["terminal_condition"] == {
            "stop_policy": "stop_before_action",
            "user_owned_final_press": True,
        }
        assert intent["resolution_gate"]["minimum_positive_dimensions"] == 4
        assert intent["resolution_gate"]["on_missing_dimension"] == "fail_closed"
        assert intent["resolution_gate"]["fail_closed_to"] == f"{domain}.hub"

    probes = {
        "semantic": build_semantic_development_matrix(),
        "collision": build_collision_probes(),
        "recovery": build_state_permission_recovery_matrix(),
        "role_asset": build_role_asset_isolation_matrix(),
    }
    assert {name: len(values) for name, values in probes.items()} == EXPECTED_PROBE_COUNTS
    assert Counter(str(item["kind"]) for item in probes["semantic"]) == {
        "positive": 256,
        "missing_role": 128,
        "missing_asset": 128,
        "missing_state": 128,
        "missing_jurisdiction": 128,
    }
    assert Counter(str(item["kind"]) for item in probes["collision"]) == {
        "nearest_existing_collision": 94,
        "within_v20_collision": 24,
    }
    assert all(
        item["required_policy"] == "never_auto"
        and item["required_stop_policy"] == "before_action"
        and item["required_user_owned_final_press"] is True
        for item in probes["recovery"]
    )

    base = load_base_catalog()
    base_snapshot = copy.deepcopy(base)
    assert base["catalog_version"] == "19.0.0"
    assert len(base["functions"]) == BASELINE_COUNTS["functions"] == 3733
    assert len(base["intents"]) == BASELINE_COUNTS["intents"] == 3482
    assert len({str(item["domain"]) for item in base["functions"]}) == BASELINE_COUNTS["domains"] == 224
    assert _digest(base) == EXPECTED_BASE_PAYLOAD_SHA256
    base_function_ids = {str(item["function_id"]) for item in base["functions"]}
    inherited_unknown = [
        (str(intent["intent_id"]), str(value))
        for intent in base["intents"]
        for value in intent.get("avoid_functions", [])
        if str(value) not in base_function_ids
    ]
    assert len(inherited_unknown) == EXPECTED_INHERITED_REFERENCE_COUNTS["references"] == 1314
    assert len({intent_id for intent_id, _ in inherited_unknown}) == 354
    assert {value for _, value in inherited_unknown} == set(
        INHERITED_REFERENCE_CORRECTION_BY_BAD_ID
    )
    corrected_trial = copy.deepcopy(base)
    trial_ledger = _apply_inherited_reference_corrections(corrected_trial)
    corrected_function_ids = {
        str(item["function_id"]) for item in corrected_trial["functions"]
    }
    assert not {
        str(value)
        for intent in corrected_trial["intents"]
        for value in intent.get("avoid_functions", [])
        if str(value) not in corrected_function_ids
    }
    assert len(trial_ledger["corrections"]) == 354
    stats = validate_v20_data(base)
    assert stats["materialized"] is False
    assert stats["functions"] == 136
    assert stats["terminal_functions"] == stats["intents"] == 128
    assert stats["domains"] == 8
    assert stats["official_sources"] == 63
    assert stats["korean_terminals"] == 128
    assert stats["source_orphans"] == 0
    assert stats["base_payload_sha256"] == EXPECTED_BASE_PAYLOAD_SHA256
    assert stats["inherited_reference_corrections"] == 354
    assert stats["inherited_reference_bad_ids"] == 54
    assert stats["inherited_reference_count"] == 1314

    merged = merge_with_base(base)
    assert base == base_snapshot
    assert merged is not base
    assert merged["catalog_version"] == CATALOG_V20_VERSION
    assert merged["description"] == CATALOG_V20_DESCRIPTION
    assert len(merged["functions"]) == PROJECTED_COUNTS["physical_functions"] == 3869
    assert len(merged["intents"]) == PROJECTED_COUNTS["physical_intents"] == 3610
    assert len({str(item["domain"]) for item in merged["functions"]}) == PROJECTED_COUNTS["domains"] == 232
    assert _pre_v20_payload(merged) == base
    assert merged["base_layer_seal_v20"] == BASE_LAYER_SEAL
    assert merged["base_payload_seal_v20"] == BASE_PAYLOAD_SEAL
    assert merged["inherited_reference_corrections_v20"]["expected_counts"] == EXPECTED_INHERITED_REFERENCE_COUNTS
    assert len(merged["inherited_reference_corrections_v20"]["corrections"]) == 354
    assert merged["layer_integrity_v20"]["sha256"] == EXPECTED_V20_LAYER_SHA256
    assert merged["official_sources_v20"] == OFFICIAL_SOURCES
    assert merge_with_base(merged) == merged
    assert validate_v20_data(merged)["materialized"] is True
    merged_function_ids = {str(item["function_id"]) for item in merged["functions"]}
    assert not {
        str(value)
        for intent in merged["intents"]
        for value in intent.get("avoid_functions", [])
        if str(value) not in merged_function_ids
    }

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V20_FUNCTIONS[0]))
    _expect_failure(partial, "partial V20 ID collision")

    tampered_base = copy.deepcopy(base)
    tampered_base["functions"][0]["name_en"] += " tampered"
    _expect_failure(tampered_base, "base payload SHA differs")

    tampered_function = copy.deepcopy(merged)
    next(
        item for item in tampered_function["functions"] if item["function_id"] in terminal_ids
    )["name_ko"] += " 변조"
    _expect_failure(tampered_function, "different function")

    tampered_source = copy.deepcopy(merged)
    first_source = next(iter(tampered_source["official_sources_v20"]))
    tampered_source["official_sources_v20"][first_source]["provider_scope"] += " tampered"
    _expect_failure(tampered_source, "official-source registry")

    tampered_hash = copy.deepcopy(merged)
    tampered_hash["layer_integrity_v20"]["sha256"] = "0" * 64
    _expect_failure(tampered_hash, "layer-integrity")

    tampered_correction = copy.deepcopy(merged)
    first_owner = next(
        iter(tampered_correction["inherited_reference_corrections_v20"]["corrections"])
    )
    tampered_correction["inherited_reference_corrections_v20"]["corrections"][first_owner][
        "after_sha256"
    ] = "0" * 64
    _expect_failure(tampered_correction, "snapshot seal")

    print(
        json.dumps(
            {
                "status": "ok",
                "research_sha256": next(iter(SOURCE_DOCUMENT_SHA256.values())),
                "base_payload_sha256": EXPECTED_BASE_PAYLOAD_SHA256,
                "official_sources_sha256": EXPECTED_OFFICIAL_SOURCES_SHA256,
                "layer_sha256": EXPECTED_V20_LAYER_SHA256,
                "functions": 136,
                "terminals": 128,
                "intents": 128,
                "domains": 8,
                "official_sources": 63,
                "class_counts": EXPECTED_CLASS_COUNTS,
                "inherited_reference_counts": EXPECTED_INHERITED_REFERENCE_COUNTS,
                "probe_counts": EXPECTED_PROBE_COUNTS,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
