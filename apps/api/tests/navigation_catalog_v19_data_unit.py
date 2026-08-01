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

from navigation_catalog_v19_data import (  # noqa: E402
    BASELINE_COUNTS,
    BASE_LAYER_SEAL,
    CATALOG_V19_DESCRIPTION,
    CATALOG_V19_VERSION,
    COLLISION_FAMILIES,
    DOCUMENT_DIGESTS,
    DOMAIN_SOURCE_IDS,
    DOMAIN_TERMINAL_SOURCE_IDS,
    EXPECTED_CLASS_COUNTS,
    EXPECTED_DOMAIN_COUNTS,
    EXPECTED_DOMAIN_FUNCTION_COUNTS,
    EXPECTED_OFFICIAL_SOURCES_SHA256,
    EXPECTED_PROBE_COUNTS,
    EXPECTED_SOURCE_DISTRIBUTION,
    EXPECTED_V19_LAYER_SHA256,
    KOREAN_DOMAIN_TERMS,
    KOREAN_TERMINAL_IDS,
    LOCALIZATION_CORRECTIONS,
    LOCALIZATION_CORRECTION_BY_ID,
    LOCALIZATION_CORRECTION_IDS,
    LOCALIZATION_FIELDS,
    LOCALIZATION_PREIMAGE_SHA256,
    NEAREST_EXISTING_FUNCTIONS,
    NON_HANGUL_NAME_KO_ALLOWLIST,
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
    SOURCE_DOCUMENT_TEXT_PROFILE,
    V19CatalogValidationError,
    V19_FUNCTIONS,
    V19_INTENTS,
    V19_LAYER_SHA256,
    _function_semantic_dimensions,
    _non_hangul_name_ids,
    _pre_v19_payload,
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
    validate_v19_data,
)


EXPECTED_DOMAINS = {
    "voter_registration_ballot_services",
    "vital_records_certificate_services",
    "nutrition_assistance_case_services",
    "court_litigant_self_service",
    "jury_summons_response_services",
    "consumer_postal_mail_services",
    "public_health_coverage_case_services",
    "retirement_plan_participant_services",
    "consular_visa_application_services",
}

EXPECTED_CORRECTED_NAMES = {
    "freight_forwarding_customs_ops.booking_detail": "선적·운송사 예약·선복·마감 상세",
    "research_grants_administration.sponsor_guidance_review": "연구지원 기회·공고·지침 검토",
    "research_grants_administration.budget_view": "연구제안·과제 예산 조회",
    "research_grants_administration.compliance_status": "연구과제 준수 상태",
    "research_grants_administration.award_portfolio": "연구자·부서 수주과제 포트폴리오",
    "research_grants_administration.expenditure_dashboard": "연구과제 지출 대시보드",
    "research_grants_administration.reporting_calendar": "연구과제 보고 일정",
    "corrections_case_management_ops.court_order_sentence_review": "법원명령·형기·구금명령·산입일수 검토",
    "corrections_case_management_ops.housing_location_status": "수용시설·수용동·거실 위치 상태",
    "corrections_case_management_ops.program_eligibility_view": "교육·치료·사회복귀 프로그램 자격 조회",
    "corrections_case_management_ops.release_date_calculation_review": "형기·산입일수·출소예정일 계산 검토",
    "corrections_case_management_ops.incident_disciplinary_report": "시설 사건·징계 보고 제출",
    "corrections_case_management_ops.property_chain_of_custody": "개인물품·증거물 보관이력 이전",
}

EXPECTED_REJECTED_FAMILIES = (
    "passport_application_and_renewal",
    "broad_immigration_case_navigation",
    "generic_government_certificates",
    "generic_benefits_discovery",
    "election_administration",
    "generic_court_filing_and_docket_operations",
    "parcel_tracking_hold_reroute_and_reschedule",
    "generic_health_insurance_eligibility_screening_and_refund",
    "pension_plan_administration",
    "driver_vehicle_unemployment_and_social_insurance_services",
    "v18_provider_specific_alias_duplicates",
    "tax_filing_refund_and_general_public_payment",
)


def _serialized(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_serialized(value)).hexdigest()


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _expect_failure(payload: dict[str, object], fragment: str) -> None:
    try:
        validate_v19_data(payload)
    except V19CatalogValidationError as error:
        assert fragment.casefold() in str(error).casefold(), str(error)
    else:
        raise AssertionError(f"invalid V19 payload accepted; expected {fragment!r}")


def _without_localized_fields(function: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(function)
    for field in LOCALIZATION_FIELDS:
        result.pop(field, None)
    return result


def main() -> None:
    assert DOCUMENT_DIGESTS == SOURCE_DOCUMENT_SHA256
    assert SOURCE_DOCUMENT_METADATA == {
        path: {"path": path, "algorithm": "sha256", "sha256": digest}
        for path, digest in SOURCE_DOCUMENT_SHA256.items()
    }
    source_text = (ROOT / next(iter(SOURCE_DOCUMENT_SHA256))).read_text(encoding="utf-8")
    assert "\ufffd" not in source_text
    assert {
        "hangul_syllables": len(re.findall(r"[\uac00-\ud7a3]", source_text)),
        "replacement_characters": source_text.count("\ufffd"),
    } == SOURCE_DOCUMENT_TEXT_PROFILE == {"hangul_syllables": 0, "replacement_characters": 0}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected
    assert BASE_LAYER_SEAL == {
        "catalog_version": "18.0.0",
        "algorithm": "sha256",
        "sha256": "5037b41f24de175d9100a1bcc2c82efa438dfd00abeffaf9018282d797f37d99",
    }
    assert OFFICIAL_SOURCES_SHA256 == EXPECTED_OFFICIAL_SOURCES_SHA256
    assert OFFICIAL_SOURCES_SHA256 == _canonical_digest(OFFICIAL_SOURCES)
    assert V19_LAYER_SHA256 == EXPECTED_V19_LAYER_SHA256
    assert re.fullmatch(r"[0-9a-f]{64}", V19_LAYER_SHA256)

    function_ids = {str(item["function_id"]) for item in V19_FUNCTIONS}
    terminal_ids = {str(item["function_id"]) for item in V19_FUNCTIONS if item["terminal"]}
    intent_ids = {str(item["intent_id"]) for item in V19_INTENTS}
    assert REQUIRED_DOMAINS == EXPECTED_DOMAINS
    assert len(REVIEWED_DOMAINS) == len(REQUIRED_DOMAINS) == 9
    assert len(V19_FUNCTIONS) == len(function_ids) == 123
    assert len(terminal_ids) == 114
    assert len(V19_INTENTS) == len(intent_ids) == 114
    assert len(_research_proposed_terminal_ids(source_text)) == 114
    assert set(_research_proposed_terminal_ids(source_text)) == terminal_ids
    assert Counter(str(item["domain"]) for item in V19_FUNCTIONS) == EXPECTED_DOMAIN_FUNCTION_COUNTS
    assert Counter(str(item["domain"]) for item in V19_FUNCTIONS if item["terminal"]) == EXPECTED_DOMAIN_COUNTS
    assert sum(EXPECTED_DOMAIN_COUNTS.values()) == 114
    assert all(re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", value) for value in function_ids)
    assert all(re.fullmatch(r"v19_[a-z0-9_]+", value) for value in intent_ids)
    assert REJECTED_DUPLICATE_FAMILIES == EXPECTED_REJECTED_FAMILIES
    assert len(set(REJECTED_DUPLICATE_FAMILIES)) == 12
    assert len(_research_rejected_candidate_labels(source_text)) == 12

    hangul = re.compile(r"[\uac00-\ud7a3]")
    sensitive = consequential = 0
    goals_ko: set[str] = set()
    goals_en: set[str] = set()
    purposes_ko: set[str] = set()
    purposes_en: set[str] = set()
    semantic_scopes: set[str] = set()
    forbidden_keys = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_id",
        "package_name", "resource_id", "screenshot", "screenshot_hash", "screen_path",
        "recorded_route", "recorded_path", "fixed_ui_path", "pixel", "click_sequence",
        "selector", "xpath",
    }

    def assert_no_forbidden_key(value: object) -> None:
        if isinstance(value, dict):
            assert not forbidden_keys.intersection(str(key).casefold() for key in value)
            for child in value.values():
                assert_no_forbidden_key(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                assert_no_forbidden_key(child)

    for function in V19_FUNCTIONS:
        function_id = str(function["function_id"])
        assert_no_forbidden_key(function)
        assert "v19_research_isolated_services" in function["legacy_tags"]
        assert hangul.search(str(function["name_ko"]))
        assert len(function["aliases"]["ko-KR"]) >= 8
        assert len(function["aliases"]["en-US"]) >= 8
        assert all(hangul.search(str(alias)) for alias in function["aliases"]["ko-KR"])
        assert function["role_hints"] and function["asset_cues"]
        assert function["state_cues"]["jurisdiction"]
        assert function["provider_scopes"]
        assert function["source_refs"] and set(function["source_refs"]) <= set(OFFICIAL_SOURCES)
        if function["terminal"]:
            reviewed = REVIEWED_FEATURE_BY_ID[function_id]
            sensitive += bool(function["classification"] == "S" and function["view_only"] and not function["state_changing"])
            consequential += bool(function["classification"] == "C" and function["consequential"] and function["state_changing"])
            assert function["name_ko"] == reviewed.name_ko
            assert function["name_en"] == reviewed.name_en
            assert function["representative_goals"] == {"ko-KR": reviewed.goal_ko, "en-US": reviewed.goal_en}
            assert function["purpose_by_locale"] == {"ko-KR": reviewed.purpose_ko, "en-US": reviewed.purpose_en}
            assert reviewed.roles and reviewed.assets and reviewed.states
            assert reviewed.jurisdiction_guard and reviewed.safety_boundary
            goals_ko.add(reviewed.goal_ko)
            goals_en.add(reviewed.goal_en)
            purposes_ko.add(reviewed.purpose_ko)
            purposes_en.add(reviewed.purpose_en)
            semantic_scopes.add(_digest(function["semantic_scope"]))
            assert all(reviewed.name_ko in str(alias) for alias in function["aliases"]["ko-KR"])
            assert all(reviewed.name_en.casefold() in str(alias).casefold() for alias in function["aliases"]["en-US"])
            assert function["automation_policy"] == "never_auto"
            assert function["stop_policy"] == "before_action"
            assert function["risk_level"] == "high"
            assert function["user_owned_final_press"] is True
            assert set(function["source_refs"]) == set(DOMAIN_TERMINAL_SOURCE_IDS[function_id])
            assert function["risk_cues"]["source_boundary"] == [reviewed.safety_boundary]
            assert function["semantic_scope"]["roles"]
            assert function["semantic_scope"]["assets"]
            assert function["semantic_scope"]["states"]
            assert function["semantic_scope"]["jurisdiction"]
        else:
            assert function["node_kind"] == "hub"
            assert function["automation_policy"] == "safe_navigation"
            assert function["stop_policy"] == "continue"
            assert function["fail_closed"] is True
            assert function["resolution_policy"] == "fail_closed"
            assert function["requires_explicit_terminal_disambiguation"] is True
            assert function["user_owned_final_press"] is False
    assert {"S": sensitive, "C": consequential} == EXPECTED_CLASS_COUNTS
    assert len(goals_ko) == len(goals_en) == len(purposes_ko) == len(purposes_en) == 114
    assert len(semantic_scopes) == 114

    for intent in V19_INTENTS:
        target = str(intent["terminal_function"])
        reviewed = REVIEWED_FEATURE_BY_ID[target]
        assert intent["intent_id"] == f"v19_{target.replace('.', '_')}"
        assert intent["patterns_by_locale"]["ko-KR"][0] == reviewed.goal_ko
        assert intent["patterns_by_locale"]["en-US"][0] == reviewed.goal_en
        assert len(intent["patterns_by_locale"]["ko-KR"]) >= 5
        assert len(intent["patterns_by_locale"]["en-US"]) >= 5
        assert len(set(intent["patterns_by_locale"]["ko-KR"])) == len(intent["patterns_by_locale"]["ko-KR"])
        assert len(set(intent["patterns_by_locale"]["en-US"])) == len(intent["patterns_by_locale"]["en-US"])
        assert all(hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"])
        gate = next(rule for rule in intent["goal_rules"] if rule["rule_kind"] == "v19_role_asset_state_jurisdiction_gate")
        assert gate["v19_required_dimension_count"] == 4
        assert gate["v19_required_dimensions"] == [
            "authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction",
        ]
        assert intent["terminal_condition"] == {"stop_policy": "stop_before_action", "user_owned_final_press": True}
        assert intent["resolution_gate"]["minimum_positive_dimensions"] == 4
        assert intent["resolution_gate"]["on_missing_dimension"] == "fail_closed"
        assert intent["resolution_gate"]["fail_closed_to"] == f"{target.split('.', 1)[0]}.hub"

    assert len(OFFICIAL_SOURCES) == 73
    assert set(DOMAIN_SOURCE_IDS) == REQUIRED_DOMAINS
    assert set(DOMAIN_TERMINAL_SOURCE_IDS) == terminal_ids
    assert {domain: len(values) for domain, values in DOMAIN_SOURCE_IDS.items()} == EXPECTED_SOURCE_DISTRIBUTION
    normalized_urls = [normalize_official_url(str(item["canonical_url"])) for item in OFFICIAL_SOURCES.values()]
    assert len(normalized_urls) == len(set(normalized_urls)) == 73
    assert set(normalized_urls) == _research_direct_urls(source_text)
    assert all(item["source_id"] == source_id for source_id, item in OFFICIAL_SOURCES.items())
    assert all(item["publisher"] in PUBLISHER_ALLOWLIST for item in OFFICIAL_SOURCES.values())
    assert all(item["provider_scope"] == item["publisher"] for item in OFFICIAL_SOURCES.values())
    assert all(item["verification_status"] == "accepted" for item in OFFICIAL_SOURCES.values())
    assert all(item["http_status"] == item["verified_status"] == 200 for item in OFFICIAL_SOURCES.values())
    assert all(item["evidence_level"] == "official_primary" for item in OFFICIAL_SOURCES.values())
    assert all(
        item["source_record_sha256"]
        == _canonical_digest({key: value for key, value in item.items() if key != "source_record_sha256"})
        for item in OFFICIAL_SOURCES.values()
    )
    assert all(sum(item["jurisdiction"] != "KR" for item in OFFICIAL_SOURCES.values() if item["domains"] == [domain]) >= 5 for domain in REQUIRED_DOMAINS)
    assert all(sum(item["jurisdiction"] == "KR" for item in OFFICIAL_SOURCES.values() if item["domains"] == [domain]) >= 1 for domain in REQUIRED_DOMAINS)
    referenced_sources = {source_id for values in DOMAIN_TERMINAL_SOURCE_IDS.values() for source_id in values}
    assert referenced_sources == set(OFFICIAL_SOURCES)
    for terminal_id in KOREAN_TERMINAL_IDS:
        function = next(item for item in V19_FUNCTIONS if item["function_id"] == terminal_id)
        assert any(
            term in str(alias) and str(function["name_ko"]) in str(alias)
            for term in KOREAN_DOMAIN_TERMS[str(function["domain"])]
            for alias in function["aliases"]["ko-KR"]
        )

    assert len(COLLISION_FAMILIES) == 61
    assert {
        "semantic": len(build_semantic_development_matrix()),
        "collision": len(build_collision_probes()),
        "recovery": len(build_state_permission_recovery_matrix()),
        "role_asset": len(build_role_asset_isolation_matrix()),
    } == EXPECTED_PROBE_COUNTS
    assert all(item["expected_function"].endswith(".hub") for item in build_collision_probes())
    assert all(item["expected_function"].endswith(".hub") for item in build_state_permission_recovery_matrix())
    assert all(item["expected_function"].endswith(".hub") for item in build_role_asset_isolation_matrix())

    assert len(LOCALIZATION_CORRECTIONS) == len(LOCALIZATION_CORRECTION_IDS) == 13
    assert set(EXPECTED_CORRECTED_NAMES) == LOCALIZATION_CORRECTION_IDS
    assert {
        correction.function_id: correction.corrected_name_ko
        for correction in LOCALIZATION_CORRECTIONS
    } == EXPECTED_CORRECTED_NAMES
    assert NON_HANGUL_NAME_KO_ALLOWLIST == {
        "android_connectivity.quick_share", "android_connectivity.nfc", "sim.pin",
    }
    assert set(LOCALIZATION_PREIMAGE_SHA256) == LOCALIZATION_CORRECTION_IDS
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in LOCALIZATION_PREIMAGE_SHA256.values())

    # The following section deliberately exercises the full V18-composed base.
    # It is not part of import-time checks and may be deferred while another
    # independent evaluator owns the large canonical-catalog read.
    base = load_base_catalog()
    base_snapshot_sha256 = _digest(base)
    assert base["catalog_version"] == "18.0.0"
    assert len(base["functions"]) == BASELINE_COUNTS["functions"] == 3610
    assert len(base["intents"]) == BASELINE_COUNTS["intents"] == 3368
    assert len({str(item["domain"]) for item in base["functions"]}) == BASELINE_COUNTS["domains"] == 215
    base_functions = {str(item["function_id"]): item for item in base["functions"]}
    base_function_ids = set(base_functions)
    base_intent_ids = {str(item["intent_id"]) for item in base["intents"]}
    assert not function_ids.intersection(base_function_ids)
    assert not intent_ids.intersection(base_intent_ids)
    assert not REQUIRED_DOMAINS.intersection(str(item["domain"]) for item in base["functions"])
    assert {neighbor for values in NEAREST_EXISTING_FUNCTIONS.values() for neighbor in values} <= base_function_ids
    assert {domain.avoid_root for domain in REVIEWED_DOMAINS} <= base_function_ids
    assert all(
        base_functions[correction.function_id]["name_ko"] == correction.expected_name_ko
        for correction in LOCALIZATION_CORRECTIONS
    )
    base_localization_records = {
        function_id: copy.deepcopy(base_functions[function_id])
        for function_id in LOCALIZATION_CORRECTION_IDS
    }
    base_terminal_dimensions = {
        function_id: _function_semantic_dimensions(function)
        for function_id, function in base_functions.items()
        if function.get("terminal")
    }

    stats = validate_v19_data(base)
    assert stats["functions"] == 123
    assert stats["terminal_functions"] == 114
    assert stats["intents"] == 114
    assert stats["domains"] == 9
    assert stats["official_sources"] == 73
    assert stats["official_sources_sha256"] == EXPECTED_OFFICIAL_SOURCES_SHA256
    assert stats["source_orphans"] == 0
    assert stats["layer_sha256"] == EXPECTED_V19_LAYER_SHA256
    assert stats["projected_counts"] == PROJECTED_COUNTS
    assert stats["localization_corrections"] == 13
    assert stats["materialized"] is False
    assert _digest(base) == base_snapshot_sha256

    partial = copy.deepcopy(base)
    partial["functions"].append(copy.deepcopy(V19_FUNCTIONS[0]))
    _expect_failure(partial, "partial V19")
    del partial

    first_correction = next(iter(LOCALIZATION_CORRECTION_IDS))
    tampered_preimage = copy.deepcopy(base)
    tampered_preimage_map = {str(item["function_id"]): item for item in tampered_preimage["functions"]}
    tampered_preimage_map[first_correction]["name_ko"] = "tampered preimage"
    _expect_failure(tampered_preimage, "preimage name")
    del tampered_preimage, tampered_preimage_map

    tampered_hangul_gate = copy.deepcopy(base)
    tampered_hangul_map = {str(item["function_id"]): item for item in tampered_hangul_gate["functions"]}
    hangul_target = next(
        function_id
        for function_id, function in tampered_hangul_map.items()
        if function_id not in LOCALIZATION_CORRECTION_IDS
        and function_id not in NON_HANGUL_NAME_KO_ALLOWLIST
        and hangul.search(str(function["name_ko"]))
    )
    tampered_hangul_map[hangul_target]["name_ko"] = "English only tamper"
    _expect_failure(tampered_hangul_gate, "Korean-name allowlist")
    del tampered_hangul_gate, tampered_hangul_map

    merged = merge_with_base(base)
    assert _digest(base) == base_snapshot_sha256
    del base_functions, base
    assert merged["catalog_version"] == CATALOG_V19_VERSION
    assert merged["description"] == CATALOG_V19_DESCRIPTION
    assert len(merged["functions"]) == PROJECTED_COUNTS["physical_functions"] == 3733
    assert len(merged["intents"]) == PROJECTED_COUNTS["physical_intents"] == 3482
    assert len({str(item["domain"]) for item in merged["functions"]}) == PROJECTED_COUNTS["domains"] == 224
    assert merged["layer_integrity_v19"]["sha256"] == EXPECTED_V19_LAYER_SHA256
    assert merged["layer_integrity_v19"]["official_sources_sha256"] == EXPECTED_OFFICIAL_SOURCES_SHA256
    assert merged["base_layer_seal_v19"] == BASE_LAYER_SEAL
    assert merged["rejected_duplicate_families_v19"] == list(REJECTED_DUPLICATE_FAMILIES)
    assert validate_v19_data(merged)["materialized"] is True
    assert _digest(merge_with_base(merged)) == _digest(merged)
    assert _digest(_pre_v19_payload(merged)) == base_snapshot_sha256

    merged_functions = {str(item["function_id"]): item for item in merged["functions"]}
    ledger = merged["localization_corrections_v19"]
    assert ledger["correction_ids"] == sorted(LOCALIZATION_CORRECTION_IDS)
    assert ledger["non_hangul_name_ko_allowlist"] == sorted(NON_HANGUL_NAME_KO_ALLOWLIST)
    assert set(ledger["corrections"]) == LOCALIZATION_CORRECTION_IDS
    for function_id, corrected_name in EXPECTED_CORRECTED_NAMES.items():
        before = base_localization_records[function_id]
        after = merged_functions[function_id]
        correction = LOCALIZATION_CORRECTION_BY_ID[function_id]
        row = ledger["corrections"][function_id]
        assert after["name_ko"] == corrected_name
        assert str(after["description"]).startswith(corrected_name)
        assert corrected_name in after["aliases"]["ko-KR"]
        assert set(correction.context_ko) <= set(after["aliases"]["ko-KR"])
        assert set(correction.context_ko) <= set(after["positive_context"])
        assert _without_localized_fields(after) == _without_localized_fields(before)
        assert row["before"] == {field: before.get(field) for field in LOCALIZATION_FIELDS}
        assert row["after"] == {field: after.get(field) for field in LOCALIZATION_FIELDS}
        assert row["before_sha256"] == _canonical_digest(row["before"])
        assert row["before_sha256"] == LOCALIZATION_PREIMAGE_SHA256[function_id]
        assert row["after_sha256"] == _canonical_digest(row["after"])

    assert _non_hangul_name_ids(merged["functions"]) == NON_HANGUL_NAME_KO_ALLOWLIST
    for function_id in NON_HANGUL_NAME_KO_ALLOWLIST:
        assert not hangul.search(str(merged_functions[function_id]["name_ko"]))

    v19_terminal_dimensions = {
        str(function["function_id"]): _function_semantic_dimensions(function)
        for function in V19_FUNCTIONS
        if function["terminal"]
    }
    assert len(set(map(repr, v19_terminal_dimensions.values()))) == 114
    assert all(
        not all(left.intersection(right) for left, right in zip(v19_dimensions, prior_dimensions))
        for v19_dimensions in v19_terminal_dimensions.values()
        for prior_dimensions in base_terminal_dimensions.values()
    )

    tampered_function = copy.deepcopy(merged)
    next(item for item in tampered_function["functions"] if item["function_id"] in terminal_ids)["name_ko"] += " 변조"
    _expect_failure(tampered_function, "different function")
    del tampered_function

    tampered_source = copy.deepcopy(merged)
    first_source = next(iter(tampered_source["official_sources_v19"]))
    tampered_source["official_sources_v19"][first_source]["provider_scope"] += " tampered"
    _expect_failure(tampered_source, "official-source registry")
    del tampered_source

    tampered_hash = copy.deepcopy(merged)
    tampered_hash["layer_integrity_v19"]["sha256"] = "0" * 64
    _expect_failure(tampered_hash, "layer-integrity")
    del tampered_hash

    tampered_localized_function = copy.deepcopy(merged)
    tampered_localized_function_map = {
        str(item["function_id"]): item for item in tampered_localized_function["functions"]
    }
    tampered_localized_function_map[next(iter(LOCALIZATION_CORRECTION_IDS))]["name_ko"] += " 변조"
    _expect_failure(tampered_localized_function, "localized function")
    del tampered_localized_function, tampered_localized_function_map

    tampered_ledger = copy.deepcopy(merged)
    tampered_ledger["localization_corrections_v19"]["corrections"][first_correction]["before_sha256"] = "0" * 64
    _expect_failure(tampered_ledger, "snapshot seal")
    del tampered_ledger

    print(
        json.dumps(
            {
                "status": "ok",
                "research_sha256": next(iter(SOURCE_DOCUMENT_SHA256.values())),
                "official_sources_sha256": EXPECTED_OFFICIAL_SOURCES_SHA256,
                "layer_sha256": EXPECTED_V19_LAYER_SHA256,
                "functions": 123,
                "terminals": 114,
                "intents": 114,
                "domains": 9,
                "official_sources": 73,
                "class_counts": EXPECTED_CLASS_COUNTS,
                "localization_corrections": 13,
                "non_hangul_name_ko_allowlist": sorted(NON_HANGUL_NAME_KO_ALLOWLIST),
                "probe_counts": EXPECTED_PROBE_COUNTS,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
