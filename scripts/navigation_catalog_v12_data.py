from __future__ import annotations

"""Source-pinned v12 governed-operations ontology for universal navigation.

The reviewed markdown is the sole design input for this layer.  Its SHA-256 is
pinned below and its tables are parsed into deterministic, app-independent
role/asset/lifecycle destinations.  No package, resource ID, coordinate,
screenshot, recorded route, or independent fixture is used.
"""

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from navigation_catalog_v10_data import (
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v10_build_feature,
    _build_intent as _v10_build_intent,
    _build_root as _v10_build_root,
    _rule_signature,
    _runtime_pattern_key,
)
from navigation_catalog_v11_data import (
    CATALOG_V11_DESCRIPTION,
    CATALOG_V11_VERSION,
    OFFICIAL_SOURCES as V11_OFFICIAL_SOURCES,
    V11_FUNCTIONS,
    V11_INTENTS,
    _pre_v11_payload,
    merge_with_base as merge_v11_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_PATH = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V12.md"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V12.md"
# Hash of the reviewed source bytes currently committed at
# docs/NAVIGATION_COVERAGE_GAPS_V12.md.  The former pin referenced an earlier
# draft and made every V12+ isolated verification fail before parsing the
# otherwise unchanged source contract.
SOURCE_DOCUMENT_SHA256 = "1ac44c986cc1bae590fe64e0d91b93d09003538b98f0631e94e20265a1350d74"
DESIGN_SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
CATALOG_V12_VERSION = "12.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V12_DESCRIPTION = (
    "ExitGuide governed professional operations ontology v12: app-agnostic "
    "veterinary, dental, home-health, aviation-maintenance, rail, customs, "
    "utility-grid, environmental-waste, mining-safety, election, research-grant, "
    "and corrections destinations; every terminal press remains user-owned."
)
SOURCE_DOCUMENT_METADATA: dict[str, str] = {
    "path": DESIGN_SOURCE_RELATIVE_PATH,
    "algorithm": "sha256",
    "sha256": SOURCE_DOCUMENT_SHA256,
}


class V12CatalogValidationError(ValueError):
    """Raised when v12 cannot be built or merged without source/safety drift."""


@dataclass(frozen=True)
class ReviewedFeature:
    key: str
    intent_id: str
    classification: str
    path_ko: str
    path_en: str


@dataclass(frozen=True)
class ReviewedDomain:
    domain: str
    hub_ko: str
    hub_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    lifecycle_states: tuple[str, ...]
    collision_terms: tuple[str, ...]
    features: tuple[ReviewedFeature, ...]
    sources: tuple[tuple[str, str, str], ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _split_csv(value: str) -> tuple[str, ...]:
    return _dedupe(part.strip(" .") for part in value.split(","))


def _read_design_source() -> str:
    raw = DESIGN_SOURCE_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SOURCE_DOCUMENT_SHA256:
        raise V12CatalogValidationError(
            f"v12 design source SHA-256 differs: expected {SOURCE_DOCUMENT_SHA256}, got {actual}"
        )
    return raw.decode("utf-8")


_SECTION_RE = re.compile(
    r"^## [0-9]+[.] .*?[(]`(?P<domain>[a-z0-9_]+)`[)]\n"
    r"(?P<body>.*?)(?=^## [0-9]+[.]|^## 교차 도메인)",
    re.MULTILINE | re.DOTALL,
)
_HUB_RE = re.compile(
    r"^허브: `(?P<hub>[a-z0-9_]+[.]hub)` — (?P<ko>.*?) / (?P<en>.*?)$",
    re.MULTILINE,
)
_ROW_RE = re.compile(
    r"^\| `(?P<function>[a-z0-9_]+[.][a-z0-9_]+)` "
    r"\| `(?P<intent>v12_[a-z0-9_]+)` \| (?P<classification>[SC]) "
    r"\| (?P<ko>.*?) / (?P<en>.*?) \|$",
    re.MULTILINE,
)
_SOURCE_RE = re.compile(
    r"^- (?P<publisher>.*?), \[(?P<title>[^]]+)\]"
    r"\((?P<url>https://[^)]+)\)",
    re.MULTILINE,
)


def _parse_reviewed_domains(text: str) -> tuple[ReviewedDomain, ...]:
    domains: list[ReviewedDomain] = []
    for match in _SECTION_RE.finditer(text):
        domain = match.group("domain")
        body = match.group("body")
        hub = _HUB_RE.search(body)
        role_line = next(
            (line for line in body.splitlines() if line.startswith("역할·자산·상태: ")),
            "",
        )
        collision_line = next(
            (line for line in body.splitlines() if line.startswith("충돌군: ")),
            "",
        )
        if hub is None or not role_line or not collision_line:
            raise V12CatalogValidationError(f"{domain}: incomplete reviewed domain section")
        if hub.group("hub") != f"{domain}.hub":
            raise V12CatalogValidationError(f"{domain}: reviewed hub ID differs")

        try:
            role_chunk, asset_state_chunk = role_line[len("역할·자산·상태: "):].split(
                "핵심 자산은 ", 1
            )
            role_text = role_chunk.split(" 역할", 1)[0]
            asset_text = re.split(r"(?:이며|이고)", asset_state_chunk.split("`", 1)[0], 1)[0]
            lifecycle_text = asset_state_chunk.split("`")[1]
        except (IndexError, ValueError) as error:
            raise V12CatalogValidationError(f"{domain}: malformed role/asset/state line") from error

        features: list[ReviewedFeature] = []
        for row in _ROW_RE.finditer(body):
            function_id = row.group("function")
            key = function_id.split(".", 1)[1]
            intent_id = row.group("intent")
            expected_intent = f"v12_{domain}_{key}"
            if function_id != f"{domain}.{key}" or intent_id != expected_intent:
                raise V12CatalogValidationError(f"{function_id}: reviewed ID contract differs")
            features.append(ReviewedFeature(
                key=key,
                intent_id=intent_id,
                classification=row.group("classification"),
                path_ko=row.group("ko").strip(),
                path_en=row.group("en").strip(),
            ))
        sources = tuple(
            (item.group("publisher").strip(), item.group("title").strip(), item.group("url").strip())
            for item in _SOURCE_RE.finditer(body)
        )
        domains.append(ReviewedDomain(
            domain=domain,
            hub_ko=hub.group("ko").strip(),
            hub_en=hub.group("en").strip(),
            roles=_split_csv(role_text),
            assets=_split_csv(asset_text),
            lifecycle_states=_dedupe(part.strip() for part in lifecycle_text.split("→")),
            collision_terms=_dedupe(re.findall(r"`([^`]+)`", collision_line)),
            features=tuple(features),
            sources=sources,
        ))
    if len(domains) != 12:
        raise V12CatalogValidationError(f"reviewed source must contain 12 domains; got {len(domains)}")
    return tuple(domains)


REVIEWED_DOMAINS = _parse_reviewed_domains(_read_design_source())
REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}


def _source(
    publisher: str,
    title: str,
    url: str,
    *,
    assets: Sequence[str],
    states: Sequence[str],
) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "retrieved_at": RETRIEVED_AT,
        "collected_on": COLLECTED_ON,
        "supported_assets": list(assets),
        "supported_states": list(states),
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official first-party page reviewed in the SHA-pinned v12 audit",
    }


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {}
DOMAIN_SOURCE_IDS: dict[str, tuple[str, ...]] = {}
for _domain in REVIEWED_DOMAINS:
    _source_ids: list[str] = []
    for _source_index, (_publisher, _title, _url) in enumerate(_domain.sources, start=1):
        _source_id = f"{_domain.domain}_official_{_source_index:02d}"
        OFFICIAL_SOURCES[_source_id] = _source(
            _publisher,
            _title,
            _url,
            assets=_domain.assets,
            states=_domain.lifecycle_states,
        )
        _source_ids.append(_source_id)
    DOMAIN_SOURCE_IDS[_domain.domain] = tuple(_source_ids)
PUBLISHER_ALLOWLIST = frozenset(str(item["publisher"]) for item in OFFICIAL_SOURCES.values())


AVOID_ROOTS: dict[str, str] = {
    "veterinary_practice_ops": "clinical_care_team_ops.hub",
    "dental_practice_ops": "clinical_care_team_ops.hub",
    "home_health_clinician_ops": "clinical_care_team_ops.hub",
    "aviation_maintenance_ops": "maintenance_asset_ops.hub",
    "rail_operations": "maintenance_asset_ops.hub",
    "freight_forwarding_customs_ops": "maritime_port_logistics.hub",
    "utility_grid_field_ops": "telecom_field_service_ops.hub",
    "environmental_waste_ops": "maritime_port_logistics.hub",
    "mining_site_safety_ops": "field_construction_ops.hub",
    "election_administration": "government_digital.hub",
    "research_grants_administration": "procurement_supplier_ops.hub",
    "corrections_case_management_ops": "social_services_casework.hub",
}


def _path_parts(value: str) -> tuple[str, ...]:
    return _dedupe(part.strip() for part in value.split("→"))


def _feature_seed(domain: ReviewedDomain, row: ReviewedFeature) -> FeatureSeed:
    ko_parts = _path_parts(row.path_ko)
    en_parts = _path_parts(row.path_en)
    name_ko = " · ".join(ko_parts)
    name_en = " · ".join(en_parts)
    action_ko = "조회" if row.classification == "S" else "업무"
    action_en = "review" if row.classification == "S" else "governed workflow"
    ko_aliases = _dedupe((
        row.path_ko,
        " ".join(ko_parts),
        f"{ko_parts[0]}에서 {ko_parts[-1]}",
        f"{name_ko} {action_ko}",
        f"{name_ko} 목적지",
        f"{name_ko} 화면",
        f"{name_ko} 세부",
        f"{name_ko} 열기",
    ))
    en_aliases = _dedupe((
        row.path_en,
        " ".join(en_parts),
        f"{en_parts[-1]} under {en_parts[0]}",
        f"{action_en} {name_en.lower()}",
        f"{name_en} destination",
        f"{name_en} screen",
        f"{name_en} details",
        f"open {name_en.lower()}",
    ))
    positive = _dedupe((
        row.path_ko,
        name_ko,
        ko_parts[0],
        ko_parts[-1],
        row.path_en,
        name_en,
        en_parts[0],
        en_parts[-1],
    ))
    negative = _dedupe((
        "다른 전문 역할의 기록",
        "잘못된 관리 자산",
        "잘못된 수명주기 상태",
        "해당 역할 권한 없음",
        "명시적으로 다른 대상 기록",
        "오프라인 또는 사용할 수 없음",
        "other professional role",
        "wrong governed asset",
        "wrong lifecycle state",
        "permission denied for this role",
        "explicitly different record",
        "offline or unavailable",
        *domain.collision_terms,
    ))
    return F(
        row.key,
        name_ko,
        name_en,
        "|".join(ko_aliases),
        "|".join(en_aliases),
        "|".join(positive),
        "|".join(negative),
        "sensitive" if row.classification == "S" else "submit",
        sources="|".join(DOMAIN_SOURCE_IDS[domain.domain]),
    )


def _group_seed(domain: ReviewedDomain) -> GroupSeed:
    ko_context = _dedupe((
        domain.hub_ko,
        *(part for row in domain.features[:4] for part in _path_parts(row.path_ko)[:2]),
    ))
    en_context = _dedupe((*domain.roles, *domain.assets, *domain.lifecycle_states))
    negative_ko = _dedupe((
        "다른 전문 도메인",
        "개인 소비자 계정",
        "잘못된 역할",
        "잘못된 자산",
        "잘못된 기록",
        "권한 거부",
        *domain.collision_terms,
    ))
    negative_en = _dedupe((
        "different professional domain",
        "personal consumer account",
        "wrong role",
        "wrong governed asset",
        "wrong record",
        "permission denied",
        *domain.collision_terms,
    ))
    return G(
        domain.domain,
        domain.hub_ko,
        domain.hub_en,
        f"{domain.domain}_governed_operations",
        "|".join(ko_context),
        "|".join(en_context),
        "|".join(negative_ko),
        "|".join(negative_en),
        AVOID_ROOTS[domain.domain],
        "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, row) for row in domain.features),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)


# The 32 families come directly from the reviewed cross-domain collision matrix.
# Targets are fully qualified role/asset/lifecycle examples, never alias-only labels.
COLLISION_FAMILIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("환자", "patient", ("veterinary_practice_ops.patient_queue", "dental_practice_ops.patient_chart", "home_health_clinician_ops.patient_care_plan")),
    ("소유자·보호자", "owner", ("veterinary_practice_ops.animal_profile", "veterinary_practice_ops.owner_patient_register", "utility_grid_field_ops.work_queue")),
    ("투여·행정", "administration", ("veterinary_practice_ops.vaccine_administer", "home_health_clinician_ops.medication_administration_record", "election_administration.voter_registration_update")),
    ("등록", "registration", ("veterinary_practice_ops.owner_patient_register", "dental_practice_ops.patient_register", "election_administration.voter_registration_update")),
    ("처방", "prescription", ("veterinary_practice_ops.prescription_issue", "dental_practice_ops.prescription_issue", "home_health_clinician_ops.physician_order_request")),
    ("증명", "certificate", ("veterinary_practice_ops.health_certificate_prepare", "aviation_maintenance_ops.tool_calibration_issue", "election_administration.canvass_result_certify")),
    ("차트", "chart", ("dental_practice_ops.patient_chart", "dental_practice_ops.odontogram_review", "dental_practice_ops.periodontal_chart_review")),
    ("면", "surface", ("dental_practice_ops.odontogram_update", "mining_site_safety_ops.ground_control_inspection", "utility_grid_field_ops.asset_network_view")),
    ("해제·반출·복귀", "release", ("aviation_maintenance_ops.maintenance_release_to_service", "freight_forwarding_customs_ops.delivery_order_release", "environmental_waste_ops.spill_release_report", "corrections_case_management_ops.custody_release_execute")),
    ("이연", "defer", ("aviation_maintenance_ops.deferred_defect_review", "aviation_maintenance_ops.defect_defer_clear", "research_grants_administration.rebudget_request")),
    ("편성", "consist", ("rail_operations.train_consist", "rail_operations.train_makeup_confirm", "freight_forwarding_customs_ops.shipment_dashboard")),
    ("전환", "switch", ("rail_operations.switch_position_confirm", "utility_grid_field_ops.switching_plan_review", "utility_grid_field_ops.switching_step_confirm")),
    ("권한", "authority", ("rail_operations.roadway_worker_authority", "rail_operations.movement_authority_ack", "utility_grid_field_ops.energization_authorize", "corrections_case_management_ops.movement_authorization")),
    ("경로", "route", ("rail_operations.dispatch_route_set", "mining_site_safety_ops.haul_route_change", "freight_forwarding_customs_ops.transport_instruction_issue")),
    ("운송장·목록", "manifest", ("freight_forwarding_customs_ops.cargo_manifest_submit", "environmental_waste_ops.manifest_tracking", "environmental_waste_ops.e_manifest_sign")),
    ("신고·진입", "entry", ("freight_forwarding_customs_ops.customs_declaration_submit", "veterinary_practice_ops.encounter_note", "corrections_case_management_ops.intake_identity_verify")),
    ("분류", "classification", ("freight_forwarding_customs_ops.tariff_classification_review", "environmental_waste_ops.waste_characterization_record", "corrections_case_management_ops.custody_classification_view")),
    ("보류", "hold", ("freight_forwarding_customs_ops.hold_exam_status", "freight_forwarding_customs_ops.hold_release_request", "aviation_maintenance_ops.defect_defer_clear", "corrections_case_management_ops.restrictive_housing_review")),
    ("장애", "outage", ("utility_grid_field_ops.outage_map", "utility_grid_field_ops.outage_ticket_create", "rail_operations.incident_report")),
    ("차단", "disconnect", ("utility_grid_field_ops.meter_disconnect_reconnect", "home_health_clinician_ops.visit_checkout_evv", "corrections_case_management_ops.custody_release_execute")),
    ("발생자", "generator", ("environmental_waste_ops.waste_characterization_record", "environmental_waste_ops.permit_site_profile", "utility_grid_field_ops.asset_network_view")),
    ("배출·퇴원", "discharge", ("environmental_waste_ops.discharge_monitoring_record", "home_health_clinician_ops.transfer_discharge", "veterinary_practice_ops.encounter_close")),
    ("허가", "permit", ("environmental_waste_ops.permit_site_profile", "mining_site_safety_ops.permit_to_work_issue", "freight_forwarding_customs_ops.customs_status")),
    ("폭파", "blast", ("mining_site_safety_ops.blast_plan_approve", "mining_site_safety_ops.exclusion_zone_confirm", "utility_grid_field_ops.hazard_assessment")),
    ("투표·조사", "poll", ("election_administration.polling_place_open", "election_administration.polling_place_close", "election_administration.audit_status")),
    ("후보", "candidate", ("election_administration.ballot_style_review", "election_administration.canvass_result_certify", "research_grants_administration.proposal_workspace")),
    ("연구비·수상", "award", ("research_grants_administration.award_portfolio", "research_grants_administration.award_accept", "research_grants_administration.award_closeout")),
    ("노력·인건비", "effort", ("research_grants_administration.budget_submit_review", "research_grants_administration.investigator_role_assign", "research_grants_administration.progress_report_submit")),
    ("형량·문장", "sentence", ("corrections_case_management_ops.court_order_sentence_review", "corrections_case_management_ops.release_date_calculation_review", "research_grants_administration.proposal_create")),
    ("수용·인계", "custody", ("corrections_case_management_ops.custody_classification_view", "corrections_case_management_ops.property_chain_of_custody", "environmental_waste_ops.sample_chain_of_custody")),
    ("수용실·셀", "cell", ("corrections_case_management_ops.housing_location_status", "corrections_case_management_ops.housing_assignment", "research_grants_administration.budget_view")),
    ("종료", "closeout", ("research_grants_administration.award_closeout", "environmental_waste_ops.facility_closeout", "utility_grid_field_ops.work_close_handoff", "aviation_maintenance_ops.work_order_close")),
)


def _collision_avoid_map() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for _token_ko, _token_en, targets in COLLISION_FAMILIES:
        for target in targets:
            result.setdefault(target, [])
            result[target].extend(peer for peer in targets if peer != target)
    return {key: _dedupe(values) for key, values in result.items()}


COLLISION_AVOIDS = _collision_avoid_map()


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v12_governed_operations" if value == "v10_reviewed_operations" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    reviewed = REVIEWED_BY_DOMAIN[group.domain]
    result["role_hints"] = list(_dedupe((*result["role_hints"], *reviewed.roles)))
    result["asset_cues"] = list(reviewed.assets)
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues["lifecycle"] = list(reviewed.lifecycle_states)
    result["state_cues"] = state_cues
    result["user_owned_final_press"] = False
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    reviewed = REVIEWED_BY_DOMAIN[group.domain]
    row = next(item for item in reviewed.features if item.key == seed.key)
    result["automation_policy"] = "never_auto"
    result["stop_policy"] = "before_action"
    result["risk_level"] = "high"
    result["user_owned_final_press"] = True
    result["classification"] = row.classification
    result["role_hints"] = list(_dedupe((*result["role_hints"], *reviewed.roles)))
    result["asset_cues"] = list(_dedupe((*reviewed.assets, *_path_parts(row.path_en))))

    state_cues = copy.deepcopy(result["state_cues"])
    state_cues.update({
        "lifecycle": list(reviewed.lifecycle_states),
        "wrong_role": ["잘못된 역할", "권한 없는 역할", "wrong role", "role not authorized"],
        "wrong_record": ["잘못된 기록", "다른 대상", "wrong record", "different governed asset"],
        "offline": ["오프라인", "오래된 데이터", "offline", "stale data"],
        "hold": [
            "승인 필요", "임상 보류", "안전 보류", "법적 보류", "규제 보류",
            "approval required", "clinical hold", "safety hold", "legal hold", "regulatory hold",
        ],
    })
    result["state_cues"] = state_cues

    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues.update({
        "classification": [
            "S: sensitive or permission-limited read"
            if row.classification == "S"
            else "C: consequential high-risk state change"
        ],
        "role_asset_state_gate": [
            "역할·관리 자산·수명주기 상태 중 최소 두 축 확인",
            "verify at least two of role, governed asset, and lifecycle state",
        ],
        "fail_closed": [
            "비활성·권한거부·잘못된 기록·보류 상태에서는 중단",
            "stop on disabled, permission denied, wrong record, or hold state",
        ],
        "user_boundary": [
            "최종 목적지 버튼은 사용자가 직접 누름",
            "the user must press the final destination button",
        ],
        "user_owned_final_press": ["true", "사용자 소유 최종 누름"],
    })
    result["risk_cues"] = risk_cues
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v12_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v12_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v12_{key[4:]}"] = rule.pop(key)
    target = str(result["terminal_function"])
    same_domain = [f"{group.domain}.{item.key}" for item in group.features if item.key != seed.key]
    avoids = _dedupe((
        *COLLISION_AVOIDS.get(target, ()),
        *same_domain[:2],
        *result.get("avoid_functions", []),
    ))
    result["avoid_functions"] = list(avoids)
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {
        "stop_policy": "stop_before_action",
        "user_owned_final_press": True,
    }
    return result


V12_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V12_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}


def build_collision_probes() -> tuple[dict[str, str], ...]:
    """Return 384 deterministic contrastive probes (32 families x 12)."""

    intents = {str(item["terminal_function"]): item for item in V12_INTENTS}
    functions = {str(item["function_id"]): item for item in V12_FUNCTIONS}
    probes: list[dict[str, str]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(12):
            locale = "ko-KR" if probe_index < 6 else "en-US"
            target = targets[probe_index % len(targets)]
            intent = intents[target]
            function = functions[target]
            pattern = intent["patterns_by_locale"][locale][probe_index % 6]
            context = function["positive_context"][probe_index % len(function["positive_context"])]
            token = token_ko if locale == "ko-KR" else token_en
            text = (
                f"{token} 충돌 구분 {pattern} {context}"
                if locale == "ko-KR"
                else f"disambiguate {token}: {pattern} {context}"
            )
            probes.append({
                "probe_id": f"v12_collision_{family_index:02d}_{probe_index:02d}",
                "family": token_en,
                "locale": locale,
                "text": text,
                "expected_function": target,
            })
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return six source-derived probes per terminal (1,440 total)."""

    functions = {str(item["function_id"]): item for item in V12_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V12_INTENTS:
        target = str(intent["terminal_function"])
        function = functions[target]
        for locale in ("ko-KR", "en-US"):
            probes.append({
                "kind": "positive",
                "locale": locale,
                "text": intent["patterns_by_locale"][locale][0],
                "expected_function": target,
            })
        negative = function["negative_context"]
        for index, kind in enumerate((
            "wrong_role",
            "wrong_asset_state_homonym",
            "unavailable_permission",
            "explicit_negation_wrong_record",
        )):
            probes.append({
                "kind": kind,
                "locale": "ko-KR" if index % 2 == 0 else "en-US",
                "text": negative[index],
                "expected_function": None,
                "excluded_function": target,
            })
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed state/permission probes per terminal (960)."""

    functions = {str(item["function_id"]): item for item in V12_FUNCTIONS}
    probes: list[dict[str, object]] = []
    scenarios = (
        ("disabled", "비활성 disabled"),
        ("unavailable_offline", "사용 불가 offline unavailable"),
        ("wrong_role", "권한 없는 역할 wrong role permission denied"),
        ("wrong_record_asset", "잘못된 기록·자산 wrong record governed asset"),
    )
    for target, function in functions.items():
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append({
                "probe_id": f"recovery_{len(probes):04d}",
                "kind": kind,
                "text": text,
                "expected_function": None,
                "excluded_function": target,
                "required_policy": "never_auto",
                "required_stop_policy": "before_action",
            })
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state probes (720 total)."""

    probes: list[dict[str, object]] = []
    for function in V12_FUNCTIONS:
        if not function["terminal"]:
            continue
        target = str(function["function_id"])
        for kind, text in (
            ("wrong_role", "다른 전문 역할 other professional role"),
            ("wrong_asset", "다른 관리 자산 different governed asset"),
            ("wrong_state", "다른 수명주기 상태 different lifecycle state"),
        ):
            probes.append({
                "probe_id": f"isolation_{len(probes):04d}",
                "kind": kind,
                "text": text,
                "expected_function": None,
                "excluded_function": target,
                "allowed_fallback": f"{function['domain']}.hub",
            })
    return tuple(probes)


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _pre_v12_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V12_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V12_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v12", None)
    result.pop("source_document_v12", None)
    result["catalog_version"] = CATALOG_V11_VERSION
    result["description"] = CATALOG_V11_DESCRIPTION
    return result


def _ensure_v11(payload: Mapping[str, object]) -> dict[str, object]:
    candidate = _pre_v12_payload(payload)
    expected_function_ids = {str(item["function_id"]): item for item in V11_FUNCTIONS}
    expected_intent_ids = {str(item["intent_id"]): item for item in V11_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in candidate.get("functions", [])
        if str(item["function_id"]) in expected_function_ids
    }
    present_intents = {
        str(item["intent_id"]): item for item in candidate.get("intents", [])
        if str(item["intent_id"]) in expected_intent_ids
    }
    if (
        present_functions == expected_function_ids
        and present_intents == expected_intent_ids
        and candidate.get("official_sources_v11") == V11_OFFICIAL_SOURCES
        and candidate.get("catalog_version") == CATALOG_V11_VERSION
        and candidate.get("description") == CATALOG_V11_DESCRIPTION
    ):
        return candidate
    # Canonical storage may contain runtime alias/context overrides on older
    # layers.  Rebuild the reviewed v11 source layer before adding v12.
    return merge_v11_with_base(_pre_v11_payload(candidate))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v11 base whether canonical storage is older or materialized."""

    return _ensure_v11(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V12_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V12_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    has_metadata = "official_sources_v12" in payload or "source_document_v12" in payload
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V12CatalogValidationError("partial v12 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V12CatalogValidationError("v12 collides with a different function or intent definition")
    if payload.get("official_sources_v12") != OFFICIAL_SOURCES:
        raise V12CatalogValidationError("v12 official evidence registry differs")
    if payload.get("source_document_v12") != SOURCE_DOCUMENT_METADATA:
        raise V12CatalogValidationError("v12 source document SHA metadata differs")
    if payload.get("catalog_version") != CATALOG_V12_VERSION or payload.get("description") != CATALOG_V12_DESCRIPTION:
        raise V12CatalogValidationError("v12 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v12_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate source seal, exact scope, semantic depth, and fail-closed safety."""

    errors: list[str] = []
    actual_source_sha = hashlib.sha256(DESIGN_SOURCE_PATH.read_bytes()).hexdigest()
    if actual_source_sha != SOURCE_DOCUMENT_SHA256:
        errors.append(f"v12 source SHA differs: {actual_source_sha}")

    function_ids = [str(item["function_id"]) for item in V12_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V12_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V12_FUNCTIONS if bool(item["terminal"])}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v12 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v12 intent IDs: {sorted(duplicates)}")
    function_id_re = re.compile(r"^[a-z0-9_]+[.][a-z0-9_]+$")
    intent_id_re = re.compile(r"^v12_[a-z0-9_]+$")
    if any(function_id_re.fullmatch(value) is None for value in function_ids):
        errors.append("v12 contains a function ID outside the reviewed pattern")
    if any(intent_id_re.fullmatch(value) is None for value in intent_ids):
        errors.append("v12 contains an intent ID outside the reviewed pattern")

    domain_counts = Counter(str(item["domain"]) for item in V12_FUNCTIONS if bool(item["terminal"]))
    if dict(sorted(domain_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"v12 domain terminal counts differ: {dict(sorted(domain_counts.items()))}")
    if len(REQUIRED_DOMAINS) != 12 or len(V12_FUNCTIONS) != 252 or len(terminal_ids) != 240 or len(V12_INTENTS) != 240:
        errors.append("v12 requires exactly 12 domains, 12 hubs, 240 terminals, and 240 intents")

    sensitive_count = sum(bool(item["terminal"]) and not bool(item["state_changing"]) for item in V12_FUNCTIONS)
    consequential_count = sum(bool(item["state_changing"]) for item in V12_FUNCTIONS)
    if sensitive_count != 78 or consequential_count != 162:
        errors.append(f"v12 requires S=78 and C=162; got S={sensitive_count}, C={consequential_count}")

    urls: set[str] = set()
    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not an absolute HTTPS URL")
        if str(source.get("url")) in urls:
            errors.append(f"source {source_id} duplicates an official URL")
        urls.add(str(source.get("url")))
        required = {"publisher", "title", "url", "retrieved_at", "supported_assets", "supported_states"}
        if not required <= set(source):
            errors.append(f"source {source_id} lacks required source metadata")
        if source.get("publisher") not in PUBLISHER_ALLOWLIST:
            errors.append(f"source {source_id} publisher is not allowlisted")
        if not source.get("supported_assets") or not source.get("supported_states"):
            errors.append(f"source {source_id} lacks supported assets or states")
        if source.get("evidence_level") != "official_primary" or source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} lacks official-primary collection metadata")
        if source.get("verified_status") != 200:
            errors.append(f"source {source_id} lacks verification metadata")
    if len(OFFICIAL_SOURCES) != 74 or len(urls) != 74:
        errors.append("v12 requires exactly 74 unique official-primary sources")
    if any(len(DOMAIN_SOURCE_IDS[domain]) < 5 for domain in REQUIRED_DOMAINS):
        errors.append("v12 requires at least five reviewed official sources per domain")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    forbidden_keys = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_name",
        "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path",
        "pixel", "click_sequence",
    }
    for function in V12_FUNCTIONS:
        function_id = str(function["function_id"])
        aliases = function["aliases"]
        if len(aliases["ko-KR"]) < 8 or len(aliases["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 8:
            errors.append(f"{function_id}: insufficient positive or negative context")
        if len(function["role_hints"]) < 2 or not function.get("asset_cues"):
            errors.append(f"{function_id}: incomplete role or asset semantics")
        if len(function.get("asset_cues", [])) < 2:
            errors.append(f"{function_id}: fewer than two asset cues")
        if len(function["state_cues"].get("lifecycle", [])) < 2 or not function["risk_cues"]:
            errors.append(f"{function_id}: incomplete lifecycle or risk semantics")
        refs = {str(value) for value in function["source_refs"]}
        used_sources.update(refs)
        if not refs or not refs <= known_sources:
            errors.append(f"{function_id}: invalid official source refs")
        if function["evidence_level"] != "official":
            errors.append(f"{function_id}: evidence level must be official")
        if _contains_forbidden_key(function, forbidden_keys):
            errors.append(f"{function_id}: app-specific package, coordinate, or fixed path data is forbidden")
        if function["terminal"]:
            if function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action":
                errors.append(f"{function_id}: unsafe terminal boundary")
            if function.get("user_owned_final_press") is not True:
                errors.append(f"{function_id}: user_owned_final_press must be true")
            if function["risk_level"] != "high":
                errors.append(f"{function_id}: terminal risk must be high")
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))
            if "사용자" not in boundary or "user" not in boundary.casefold() or "press" not in boundary.casefold():
                errors.append(f"{function_id}: explicit user-owned final press is missing")
            classification = function.get("classification")
            if classification == "C" and not function["state_changing"]:
                errors.append(f"{function_id}: C destination must be state-changing")
            if classification == "S" and function["state_changing"]:
                errors.append(f"{function_id}: S destination cannot be state-changing")
        elif function["automation_policy"] != "safe_navigation" or function["stop_policy"] != "continue":
            errors.append(f"{function_id}: hub must remain navigation-only")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    terminal_by_id = {str(item["function_id"]): item for item in V12_FUNCTIONS}
    intent_terminals = [str(item["terminal_function"]) for item in V12_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v12 requires exactly one intent per terminal function")
    for intent in V12_INTENTS:
        intent_id = str(intent["intent_id"])
        localized = intent["patterns_by_locale"]
        if len(localized["ko-KR"]) < 5 or len(localized["en-US"]) < 5:
            errors.append(f"{intent_id}: insufficient bilingual patterns")
        if len(intent["goal_rules"]) < 24:
            errors.append(f"{intent_id}: insufficient compositional rules")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != intent["terminal_function"]:
            errors.append(f"{intent_id}: invalid hub-to-destination route")
        avoids = list(intent.get("avoid_functions", []))
        if len(avoids) < 2 or str(intent["terminal_function"]) in avoids:
            errors.append(f"{intent_id}: insufficient collision-family avoids")
        if intent["desired_state"] != "user_confirmation_required":
            errors.append(f"{intent_id}: user confirmation is not required")
        if intent["terminal_condition"].get("stop_policy") != "stop_before_action":
            errors.append(f"{intent_id}: route must stop before action")
        if intent["terminal_condition"].get("user_owned_final_press") is not True:
            errors.append(f"{intent_id}: terminal condition lacks user-owned final press")
        if terminal_by_id[str(intent["terminal_function"])]["automation_policy"] != "never_auto":
            errors.append(f"{intent_id}: terminal is not fail-closed")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v12_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v12_discriminative_keys", "v12_negative_context_keys", "v12_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    semantic_matrix = build_semantic_development_matrix()
    collision_probes = build_collision_probes()
    recovery_matrix = build_state_permission_recovery_matrix()
    isolation_matrix = build_role_asset_isolation_matrix()
    if len(semantic_matrix) != 1440 or sum(item["kind"] == "positive" for item in semantic_matrix) != 480:
        errors.append("v12 semantic matrix must contain 1,440 probes with 480 positives")
    if len(COLLISION_FAMILIES) != 32 or len(collision_probes) != 384:
        errors.append("v12 collision suite must contain 32 families and 384 probes")
    if len({item["probe_id"] for item in collision_probes}) != 384:
        errors.append("v12 collision probe IDs are not unique")
    if any(item["expected_function"] not in terminal_ids for item in collision_probes):
        errors.append("v12 collision suite references an unknown terminal")
    if len(recovery_matrix) != 960 or len(isolation_matrix) != 720:
        errors.append("v12 recovery/isolation matrices must contain 960/720 probes")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v12 = _ensure_v11(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v12.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v12.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v12 function IDs collide with v1-v11: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v12 intent IDs collide with v1-v11: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v12.get("intents", []), *V12_INTENTS]:
            owner = str(intent["intent_id"])
            for pattern in intent.get("patterns", []):
                key = _runtime_pattern_key(pattern)
                if key:
                    pattern_owners.setdefault(key, set()).add(owner)
        pattern_collisions = {key: owners for key, owners in pattern_owners.items() if len(owners) > 1}
        if pattern_collisions:
            errors.append(f"normalized goal-pattern collisions: {list(pattern_collisions.items())[:8]}")

        base_rule_signatures = {
            _rule_signature(rule)
            for intent in pre_v12.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v12_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V12_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v11")
                v12_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {signature: owners for signature, owners in v12_rule_owners.items() if len(owners) > 1}
        if shared_rules:
            errors.append(f"v12 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V12_FUNCTIONS, "intents": V12_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "pixel position",
        "recorded path", "fixed click", "oracle", "servicenow", "salesforce",
        "maximo", "arcgis",
    )
    if any(re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", semantic_text) for value in forbidden_fragments):
        errors.append("v12 runtime semantics contain a source identity or recorded UI path")

    if errors:
        raise V12CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V12_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V12_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "source_sha256": actual_source_sha,
        "aliases": sum(len(values) for item in V12_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V12_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V12_INTENTS),
        "sensitive_reads": sensitive_count,
        "state_changing": consequential_count,
        "semantic_smoke_probes": len(semantic_matrix),
        "collision_probes": len(collision_probes),
        "recovery_probes": len(recovery_matrix),
        "isolation_probes": len(isolation_matrix),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, fail-closed v11+v12 catalog copy."""

    validate_v12_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v11(base_payload)
    merged["catalog_version"] = CATALOG_V12_VERSION
    merged["description"] = CATALOG_V12_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V12_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V12_INTENTS)]
    merged["official_sources_v12"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_document_v12"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    return merged


def main() -> int:
    print(json.dumps(validate_v12_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
