from __future__ import annotations

"""Source-pinned v13 governed-operations ontology for universal navigation.

The reviewed v13 markdown is the sole design input for this layer.  Its
SHA-256 is pinned below and its tables are parsed into deterministic,
app-independent role/asset/lifecycle destinations.  No package, resource ID,
coordinate, screenshot, recorded route, or independent fixture is used.
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
from navigation_catalog_v12_data import (
    CATALOG_V12_DESCRIPTION,
    CATALOG_V12_VERSION,
    OFFICIAL_SOURCES as V12_OFFICIAL_SOURCES,
    SOURCE_DOCUMENT_METADATA as V12_SOURCE_DOCUMENT_METADATA,
    V12_FUNCTIONS,
    V12_INTENTS,
    _pre_v12_payload,
    merge_with_base as merge_v12_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_PATH = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V13.md"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V13.md"
SOURCE_DOCUMENT_SHA256 = "82f35fcc31aa4295d2c5476a9508b437cf757b5df6298755150940f2ca98fa67"
DESIGN_SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
CATALOG_V13_VERSION = "13.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V13_DESCRIPTION = (
    "ExitGuide governed professional operations ontology v13: app-agnostic "
    "blood-bank, organ-transplant, radiation-therapy, court-clerk, IP-docketing, "
    "food-inspection, building-code, water-plant, nuclear-plant, pipeline, museum, "
    "and air-traffic-control destinations; every terminal press remains user-owned."
)
SOURCE_DOCUMENT_METADATA: dict[str, str] = {
    "path": DESIGN_SOURCE_RELATIVE_PATH,
    "algorithm": "sha256",
    "sha256": SOURCE_DOCUMENT_SHA256,
}


class V13CatalogValidationError(ValueError):
    """Raised when v13 cannot be built or merged without source/safety drift."""


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


@dataclass(frozen=True)
class ReviewedCollision:
    token_en: str
    label_ko: str
    contrasted_concepts: tuple[str, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _split_csv(value: str) -> tuple[str, ...]:
    return _dedupe(part.strip(" .") for part in value.split(","))


def _read_design_source() -> str:
    raw = DESIGN_SOURCE_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SOURCE_DOCUMENT_SHA256:
        raise V13CatalogValidationError(
            f"v13 design source SHA-256 differs: expected {SOURCE_DOCUMENT_SHA256}, got {actual}"
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
    r"\| `(?P<intent>v13_[a-z0-9_]+)` \| (?P<classification>[SC]) "
    r"\| (?P<ko>.*?) / (?P<en>.*?) \|$",
    re.MULTILINE,
)
_SOURCE_RE = re.compile(
    r"^- (?P<publisher>.*?), \[(?P<title>[^]]+)\]"
    r"\((?P<url>https://[^)]+)\)",
    re.MULTILINE,
)
_COLLISION_SECTION_RE = re.compile(
    r"^## 교차 도메인 collision matrix\n(?P<body>.*?)(?=^## 구현 데이터 계약)",
    re.MULTILINE | re.DOTALL,
)
_COLLISION_ROW_RE = re.compile(
    r"^\| `(?P<en>[^`]+)` / (?P<ko>[^|]+?) \| (?P<concepts>[^|]+?) \|$",
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
            raise V13CatalogValidationError(f"{domain}: incomplete reviewed domain section")
        if hub.group("hub") != f"{domain}.hub":
            raise V13CatalogValidationError(f"{domain}: reviewed hub ID differs")

        try:
            role_chunk, asset_state_chunk = role_line[len("역할·자산·상태: "):].split(
                "핵심 자산은 ", 1
            )
            role_text = role_chunk.split(" 역할", 1)[0]
            asset_text = re.split(r"(?:이며|이고)", asset_state_chunk.split("`", 1)[0], 1)[0]
            lifecycle_text = asset_state_chunk.split("`")[1]
        except (IndexError, ValueError) as error:
            raise V13CatalogValidationError(f"{domain}: malformed role/asset/state line") from error

        features: list[ReviewedFeature] = []
        for row in _ROW_RE.finditer(body):
            function_id = row.group("function")
            key = function_id.split(".", 1)[1]
            intent_id = row.group("intent")
            expected_intent = f"v13_{domain}_{key}"
            if function_id != f"{domain}.{key}" or intent_id != expected_intent:
                raise V13CatalogValidationError(f"{function_id}: reviewed ID contract differs")
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
        if len(features) != 20 or Counter(item.classification for item in features) != {"S": 7, "C": 13}:
            raise V13CatalogValidationError(f"{domain}: expected exactly 20 terminals with S=7/C=13")
        if len(sources) != 6:
            raise V13CatalogValidationError(f"{domain}: expected exactly six reviewed official sources")
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
        raise V13CatalogValidationError(f"reviewed source must contain 12 domains; got {len(domains)}")
    return tuple(domains)


def _parse_reviewed_collisions(text: str) -> tuple[ReviewedCollision, ...]:
    section = _COLLISION_SECTION_RE.search(text)
    if section is None:
        raise V13CatalogValidationError("reviewed source lacks the collision matrix")
    rows = tuple(
        ReviewedCollision(
            token_en=item.group("en").strip(),
            label_ko=item.group("ko").strip(),
            contrasted_concepts=_split_csv(item.group("concepts")),
        )
        for item in _COLLISION_ROW_RE.finditer(section.group("body"))
    )
    if len(rows) != 61 or len({row.token_en for row in rows}) != 61:
        raise V13CatalogValidationError(
            f"reviewed collision matrix must contain 61 unique families; got {len(rows)}"
        )
    return rows


_DESIGN_TEXT = _read_design_source()
REVIEWED_DOMAINS = _parse_reviewed_domains(_DESIGN_TEXT)
REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}
REVIEWED_COLLISIONS = _parse_reviewed_collisions(_DESIGN_TEXT)


def _source(
    publisher: str,
    title: str,
    url: str,
    *,
    roles: Sequence[str],
    assets: Sequence[str],
    states: Sequence[str],
) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "retrieved_at": RETRIEVED_AT,
        "collected_on": COLLECTED_ON,
        "supported_roles": list(roles),
        "supported_assets": list(assets),
        "supported_states": list(states),
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official first-party page reviewed in the SHA-pinned v13 audit",
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
            roles=_domain.roles,
            assets=_domain.assets,
            states=_domain.lifecycle_states,
        )
        _source_ids.append(_source_id)
    DOMAIN_SOURCE_IDS[_domain.domain] = tuple(_source_ids)
PUBLISHER_ALLOWLIST = frozenset(str(item["publisher"]) for item in OFFICIAL_SOURCES.values())


AVOID_ROOTS: dict[str, str] = {
    "blood_bank_transfusion_ops": "home_health_clinician_ops.hub",
    "organ_transplant_coordination": "home_health_clinician_ops.hub",
    "radiation_therapy_ops": "dental_practice_ops.hub",
    "court_clerk_case_admin": "corrections_case_management_ops.hub",
    "ip_prosecution_docketing": "research_grants_administration.hub",
    "food_establishment_inspection": "environmental_waste_ops.hub",
    "building_permit_code_enforcement": "mining_site_safety_ops.hub",
    "water_wastewater_plant_ops": "utility_grid_field_ops.hub",
    "nuclear_plant_operations": "aviation_maintenance_ops.hub",
    "pipeline_control_integrity_ops": "utility_grid_field_ops.hub",
    "museum_collections_ops": "research_grants_administration.hub",
    "air_traffic_control_ops": "rail_operations.hub",
}


def _path_parts(value: str) -> tuple[str, ...]:
    return _dedupe(part.strip() for part in value.split("→"))


def _feature_seed(domain: ReviewedDomain, row: ReviewedFeature) -> FeatureSeed:
    ko_parts = _path_parts(row.path_ko)
    en_parts = _path_parts(row.path_en)
    name_ko = " · ".join(ko_parts)
    name_en = " · ".join(en_parts)
    action_ko = "민감 조회" if row.classification == "S" else "결과적 업무"
    action_en = "sensitive review" if row.classification == "S" else "consequential workflow"
    ko_aliases = _dedupe((
        row.path_ko,
        " ".join(ko_parts),
        f"{ko_parts[0]}에서 {ko_parts[-1]}",
        f"{name_ko} {action_ko}",
        f"{name_ko} 목적지",
        f"{name_ko} 상태 화면",
        f"{name_ko} 세부 정보",
        f"{name_ko} 열기",
    ))
    en_aliases = _dedupe((
        row.path_en,
        " ".join(en_parts),
        f"{en_parts[-1]} under {en_parts[0]}",
        f"{action_en} {name_en.lower()}",
        f"{name_en} destination",
        f"{name_en} status screen",
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
        *domain.roles[:2],
        *domain.assets[:2],
        *domain.lifecycle_states[:2],
    ))
    negative = _dedupe((
        "다른 전문 역할의 기록",
        "잘못된 사람·시설·사건",
        "잘못된 관리 자산",
        "잘못된 수명주기 상태",
        "해당 역할 권한 없음",
        "명시적으로 다른 대상 기록",
        "오프라인·오래된 데이터·사용 불가",
        "승인·임상·법적·품질·안전·규제 보류",
        "other professional role",
        "wrong person facility or case",
        "wrong governed asset",
        "wrong lifecycle state",
        "permission denied for this role",
        "explicitly different record",
        "offline stale or unavailable",
        "approval clinical legal quality safety or regulatory hold",
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
        "다른 전문 도메인", "개인 소비자 계정", "잘못된 역할", "잘못된 자산",
        "잘못된 기록", "잘못된 시설", "권한 거부", *domain.collision_terms,
    ))
    negative_en = _dedupe((
        "different professional domain", "personal consumer account", "wrong role",
        "wrong governed asset", "wrong record", "wrong facility", "permission denied",
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


# Reviewed collision families are source-derived; these targets make each
# contrast concrete using only v13 role/asset/lifecycle destinations.
_COLLISION_TARGET_IDS: dict[str, tuple[str, ...]] = {
    "unit": (
        "blood_bank_transfusion_ops.unit_traceability_view",
        "water_wastewater_plant_ops.process_unit_status",
        "nuclear_plant_operations.unit_status_board",
    ),
    "patient": (
        "blood_bank_transfusion_ops.transfusion_order_review",
        "radiation_therapy_ops.patient_course_queue",
        "radiation_therapy_ops.patient_identity_site_verify",
    ),
    "donor": (
        "blood_bank_transfusion_ops.donor_eligibility_queue",
        "organ_transplant_coordination.donor_offer_queue",
        "organ_transplant_coordination.donor_referral_record",
    ),
    "recipient": (
        "blood_bank_transfusion_ops.compatibility_result_review",
        "blood_bank_transfusion_ops.transfusion_issue",
        "organ_transplant_coordination.candidate_status_review",
    ),
    "release": (
        "blood_bank_transfusion_ops.component_label_release",
        "water_wastewater_plant_ops.maintenance_isolation_release",
        "nuclear_plant_operations.tagout_boundary_release",
    ),
    "issue": (
        "blood_bank_transfusion_ops.crossmatch_issue",
        "court_clerk_case_admin.summons_issue",
        "air_traffic_control_ops.clearance_issue",
    ),
    "order": (
        "blood_bank_transfusion_ops.transfusion_order_review",
        "court_clerk_case_admin.order_judgment_enter",
        "building_permit_code_enforcement.stop_work_order_issue",
    ),
    "match": (
        "blood_bank_transfusion_ops.compatibility_result_review",
        "organ_transplant_coordination.match_run_review",
        "organ_transplant_coordination.compatibility_result_review",
    ),
    "candidate": (
        "organ_transplant_coordination.candidate_worklist",
        "organ_transplant_coordination.candidate_status_review",
        "organ_transplant_coordination.candidate_register",
    ),
    "offer": (
        "organ_transplant_coordination.donor_offer_queue",
        "organ_transplant_coordination.organ_offer_response",
        "organ_transplant_coordination.allocation_variance_report",
    ),
    "allocation": (
        "organ_transplant_coordination.match_run_review",
        "organ_transplant_coordination.organ_offer_response",
        "organ_transplant_coordination.allocation_variance_report",
    ),
    "recovery": (
        "organ_transplant_coordination.organ_recovery_handoff",
        "blood_bank_transfusion_ops.unit_recall",
        "pipeline_control_integrity_ops.leak_investigation_dispatch",
    ),
    "course": (
        "radiation_therapy_ops.patient_course_queue",
        "radiation_therapy_ops.fraction_history",
        "radiation_therapy_ops.course_complete",
    ),
    "plan": (
        "radiation_therapy_ops.treatment_plan_review",
        "radiation_therapy_ops.treatment_plan_approve",
        "building_permit_code_enforcement.plan_set_review",
    ),
    "fraction": (
        "radiation_therapy_ops.fraction_history",
        "radiation_therapy_ops.fraction_delivery_authorize",
        "radiation_therapy_ops.fraction_delivery_record",
    ),
    "dose": (
        "radiation_therapy_ops.dose_constraint_review",
        "radiation_therapy_ops.dose_check_sign",
        "water_wastewater_plant_ops.chemical_dose_change",
    ),
    "directive": (
        "radiation_therapy_ops.prescription_review",
        "radiation_therapy_ops.prescription_sign",
        "court_clerk_case_admin.order_judgment_enter",
    ),
    "case": (
        "court_clerk_case_admin.case_intake_queue",
        "court_clerk_case_admin.case_open",
        "organ_transplant_coordination.donor_referral_record",
    ),
    "docket": (
        "court_clerk_case_admin.docket_sheet_view",
        "court_clerk_case_admin.filing_docket_entry",
        "ip_prosecution_docketing.matter_docket_view",
    ),
    "file": (
        "court_clerk_case_admin.filing_docket_entry",
        "ip_prosecution_docketing.patent_submission_file",
        "ip_prosecution_docketing.trademark_application_file",
    ),
    "serve": (
        "court_clerk_case_admin.service_notice_status",
        "court_clerk_case_admin.notice_send",
        "court_clerk_case_admin.summons_issue",
    ),
    "seal": (
        "court_clerk_case_admin.document_seal_unseal",
        "organ_transplant_coordination.organ_transport_handoff",
        "museum_collections_ops.loan_shipment_release",
    ),
    "application": (
        "ip_prosecution_docketing.patent_application_status",
        "ip_prosecution_docketing.trademark_application_status",
        "building_permit_code_enforcement.application_queue",
    ),
    "claim": (
        "ip_prosecution_docketing.patent_application_prepare",
        "ip_prosecution_docketing.patent_office_action_response",
        "ip_prosecution_docketing.trademark_statement_use_file",
    ),
    "class": (
        "ip_prosecution_docketing.trademark_application_prepare",
        "food_establishment_inspection.risk_factor_classify",
        "pipeline_control_integrity_ops.integrity_anomaly_classify",
    ),
    "specimen": (
        "blood_bank_transfusion_ops.compatibility_result_review",
        "ip_prosecution_docketing.trademark_statement_use_file",
        "museum_collections_ops.object_catalog_view",
    ),
    "assignment": (
        "ip_prosecution_docketing.assignment_record_submit",
        "air_traffic_control_ops.altitude_assignment",
        "museum_collections_ops.object_location_transfer",
    ),
    "maintenance": (
        "ip_prosecution_docketing.trademark_maintenance_file",
        "nuclear_plant_operations.maintenance_return_service",
        "water_wastewater_plant_ops.maintenance_isolation_release",
    ),
    "inspection": (
        "food_establishment_inspection.prior_inspection_review",
        "food_establishment_inspection.inspection_checkin",
        "building_permit_code_enforcement.inspection_history",
    ),
    "permit": (
        "food_establishment_inspection.permit_status_view",
        "food_establishment_inspection.permit_suspension_recommend",
        "building_permit_code_enforcement.permit_status_view",
    ),
    "hold": (
        "food_establishment_inspection.product_disposition_order",
        "organ_transplant_coordination.candidate_inactivate",
        "blood_bank_transfusion_ops.unit_quarantine",
    ),
    "code": (
        "food_establishment_inspection.food_code_reference",
        "building_permit_code_enforcement.zoning_code_status",
        "building_permit_code_enforcement.plan_review_comment_issue",
    ),
    "build": (
        "building_permit_code_enforcement.application_queue",
        "building_permit_code_enforcement.plan_set_review",
        "building_permit_code_enforcement.permit_issue",
    ),
    "job": (
        "building_permit_code_enforcement.application_queue",
        "building_permit_code_enforcement.parcel_project_profile",
        "building_permit_code_enforcement.application_intake_accept",
    ),
    "occupancy": (
        "building_permit_code_enforcement.certificate_occupancy_recommend",
        "building_permit_code_enforcement.certificate_occupancy_issue",
        "building_permit_code_enforcement.inspection_result_record",
    ),
    "plant": (
        "water_wastewater_plant_ops.plant_shift_dashboard",
        "nuclear_plant_operations.unit_status_board",
        "pipeline_control_integrity_ops.scada_overview",
    ),
    "source": (
        "water_wastewater_plant_ops.source_influent_quality_view",
        "water_wastewater_plant_ops.laboratory_results_review",
        "nuclear_plant_operations.radiological_condition_view",
    ),
    "discharge": (
        "water_wastewater_plant_ops.discharge_monitoring_report_sign",
        "water_wastewater_plant_ops.netdmr_submit",
        "radiation_therapy_ops.course_complete",
    ),
    "bypass": (
        "water_wastewater_plant_ops.bypass_diversion_authorize",
        "nuclear_plant_operations.tagout_boundary_release",
        "pipeline_control_integrity_ops.pressure_reduction_apply",
    ),
    "sample": (
        "water_wastewater_plant_ops.sampling_event_record",
        "water_wastewater_plant_ops.lab_result_certify",
        "food_establishment_inspection.sampling_result_review",
    ),
    "trip": (
        "nuclear_plant_operations.manual_reactor_trip",
        "air_traffic_control_ops.ground_stop_issue",
        "pipeline_control_integrity_ops.pipeline_shutdown_execute",
    ),
    "mode": (
        "nuclear_plant_operations.unit_status_board",
        "nuclear_plant_operations.reactor_power_change_authorize",
        "pipeline_control_integrity_ops.scada_overview",
    ),
    "clearance": (
        "nuclear_plant_operations.work_clearance_status",
        "nuclear_plant_operations.work_clearance_issue",
        "air_traffic_control_ops.clearance_issue",
    ),
    "tag": (
        "nuclear_plant_operations.tagout_boundary_release",
        "museum_collections_ops.accession_record_create",
        "air_traffic_control_ops.notam_originate",
    ),
    "line": (
        "pipeline_control_integrity_ops.linepack_pressure_view",
        "water_wastewater_plant_ops.process_unit_status",
        "air_traffic_control_ops.flight_data_amend",
    ),
    "alarm": (
        "pipeline_control_integrity_ops.alarm_queue",
        "pipeline_control_integrity_ops.alarm_acknowledge_classify",
        "water_wastewater_plant_ops.alarm_history",
    ),
    "valve": (
        "pipeline_control_integrity_ops.valve_station_status",
        "pipeline_control_integrity_ops.valve_remote_operate",
        "water_wastewater_plant_ops.process_unit_status",
    ),
    "segment": (
        "pipeline_control_integrity_ops.linepack_pressure_view",
        "pipeline_control_integrity_ops.integrity_assessment_queue",
        "air_traffic_control_ops.sector_traffic_picture",
    ),
    "shutdown": (
        "pipeline_control_integrity_ops.pipeline_shutdown_execute",
        "nuclear_plant_operations.manual_reactor_trip",
        "water_wastewater_plant_ops.process_unit_start_stop",
    ),
    "dispatch": (
        "pipeline_control_integrity_ops.leak_investigation_dispatch",
        "organ_transplant_coordination.organ_transport_handoff",
        "air_traffic_control_ops.emergency_assistance_coordinate",
    ),
    "accession": (
        "museum_collections_ops.accession_queue",
        "museum_collections_ops.accession_record_create",
        "museum_collections_ops.catalog_record_publish",
    ),
    "catalog": (
        "museum_collections_ops.object_catalog_view",
        "museum_collections_ops.catalog_record_publish",
        "museum_collections_ops.location_inventory_view",
    ),
    "object": (
        "museum_collections_ops.object_catalog_view",
        "museum_collections_ops.object_location_transfer",
        "museum_collections_ops.condition_history",
    ),
    "condition": (
        "museum_collections_ops.condition_history",
        "museum_collections_ops.condition_assessment_sign",
        "pipeline_control_integrity_ops.abnormal_condition_declare",
    ),
    "loan": (
        "museum_collections_ops.loan_status_view",
        "museum_collections_ops.outgoing_loan_approve",
        "museum_collections_ops.loan_shipment_release",
    ),
    "rights": (
        "museum_collections_ops.rights_restriction_review",
        "museum_collections_ops.research_access_approve",
        "museum_collections_ops.deaccession_recommend",
    ),
    "strip": (
        "air_traffic_control_ops.flight_plan_strip_review",
        "air_traffic_control_ops.flight_data_amend",
        "air_traffic_control_ops.clearance_issue",
    ),
    "handoff": (
        "air_traffic_control_ops.handoff_transfer_accept",
        "organ_transplant_coordination.organ_recovery_handoff",
        "organ_transplant_coordination.organ_transport_handoff",
    ),
    "position": (
        "air_traffic_control_ops.position_relief_briefing_accept",
        "air_traffic_control_ops.sector_traffic_picture",
        "air_traffic_control_ops.runway_airspace_status",
    ),
    "sector": (
        "air_traffic_control_ops.sector_traffic_picture",
        "air_traffic_control_ops.handoff_transfer_accept",
        "air_traffic_control_ops.traffic_flow_plan_view",
    ),
    "ground stop": (
        "air_traffic_control_ops.ground_stop_issue",
        "air_traffic_control_ops.traffic_flow_plan_view",
        "air_traffic_control_ops.traffic_management_initiative_apply",
    ),
}


def _reviewed_collision_families() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    reviewed_tokens = {item.token_en for item in REVIEWED_COLLISIONS}
    if set(_COLLISION_TARGET_IDS) != reviewed_tokens:
        missing = sorted(reviewed_tokens - set(_COLLISION_TARGET_IDS))
        extra = sorted(set(_COLLISION_TARGET_IDS) - reviewed_tokens)
        raise V13CatalogValidationError(f"collision target map differs: missing={missing}, extra={extra}")
    return tuple(
        (item.label_ko, item.token_en, _COLLISION_TARGET_IDS[item.token_en])
        for item in REVIEWED_COLLISIONS
    )


COLLISION_FAMILIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    _reviewed_collision_families()
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
        "v13_governed_operations" if value == "v10_reviewed_operations" else value
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
        "wrong_record": [
            "잘못된 사람·시설·사건·기록", "다른 관리 대상",
            "wrong person facility case or record", "different governed asset",
        ],
        "unavailable": [
            "비활성", "사용 불가", "권한 거부", "disabled", "unavailable", "permission denied",
        ],
        "offline": ["오프라인", "오래된 데이터", "offline", "stale data"],
        "hold": [
            "승인 필요", "임상 보류", "법적 보류", "품질 보류", "안전 보류", "규제 보류",
            "approval required", "clinical hold", "legal hold", "quality hold", "safety hold",
            "regulatory hold",
        ],
        "equipment_emergency": [
            "장비 사용 불가", "비상 통제", "equipment out of service", "emergency control",
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
            "비활성·권한거부·잘못된 기록·보류·장비고장·비상통제 상태에서는 중단",
            "stop on disabled, permission denied, wrong record, hold, equipment outage, or emergency control",
        ],
        "forbidden_terminal_actions": [
            "confirm·approve·sign·issue·release·operate·start·stop·trip·submit·close 자동 누름 금지",
            "never auto-press confirm approve sign issue release operate start stop trip submit or close",
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
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v13_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v13_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v13_{key[4:]}"] = rule.pop(key)
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


V13_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V13_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}


def build_collision_probes() -> tuple[dict[str, str], ...]:
    """Return 732 deterministic contrastive probes (61 families x 12)."""

    intents = {str(item["terminal_function"]): item for item in V13_INTENTS}
    functions = {str(item["function_id"]): item for item in V13_FUNCTIONS}
    probes: list[dict[str, str]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(12):
            locale = "ko-KR" if probe_index < 6 else "en-US"
            target = targets[probe_index % len(targets)]
            intent = intents[target]
            function = functions[target]
            patterns = intent["patterns_by_locale"][locale]
            pattern = patterns[probe_index % len(patterns)]
            context = function["positive_context"][probe_index % len(function["positive_context"])]
            token = token_ko if locale == "ko-KR" else token_en
            text = (
                f"{token} 충돌 구분 {pattern} {context}"
                if locale == "ko-KR"
                else f"disambiguate {token}: {pattern} {context}"
            )
            probes.append({
                "probe_id": f"v13_collision_{family_index:02d}_{probe_index:02d}",
                "family": token_en,
                "locale": locale,
                "text": text,
                "expected_function": target,
            })
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return six source-derived probes per terminal (1,440 total)."""

    functions = {str(item["function_id"]): item for item in V13_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V13_INTENTS:
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

    probes: list[dict[str, object]] = []
    scenarios = (
        ("disabled", "비활성 disabled"),
        ("unavailable_offline", "사용 불가·오프라인 unavailable offline stale"),
        ("wrong_role", "권한 없는 역할 wrong role permission denied"),
        ("wrong_record_asset", "잘못된 사람·시설·사건·기록·자산 wrong record governed asset"),
    )
    for function in V13_FUNCTIONS:
        if not function["terminal"]:
            continue
        target = str(function["function_id"])
        for kind, text in scenarios:
            probes.append({
                "probe_id": f"recovery_{len(probes):04d}",
                "kind": kind,
                "text": text,
                "expected_function": None,
                "excluded_function": target,
                "required_policy": "never_auto",
                "required_stop_policy": "before_action",
                "required_user_owned_final_press": True,
            })
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state probes (720 total)."""

    probes: list[dict[str, object]] = []
    for function in V13_FUNCTIONS:
        if not function["terminal"]:
            continue
        target = str(function["function_id"])
        for kind, text in (
            ("wrong_role", "다른 전문 역할 other professional role"),
            ("wrong_asset", "다른 사람·시설·사건·관리 자산 different governed asset"),
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


def _pre_v13_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V13_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V13_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    result.pop("official_sources_v13", None)
    result.pop("source_document_v13", None)
    result["catalog_version"] = CATALOG_V12_VERSION
    result["description"] = CATALOG_V12_DESCRIPTION
    return result


def _ensure_v12(payload: Mapping[str, object]) -> dict[str, object]:
    candidate = _pre_v13_payload(payload)
    expected_function_ids = {str(item["function_id"]): item for item in V12_FUNCTIONS}
    expected_intent_ids = {str(item["intent_id"]): item for item in V12_INTENTS}
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
        and candidate.get("official_sources_v12") == V12_OFFICIAL_SOURCES
        and candidate.get("source_document_v12") == V12_SOURCE_DOCUMENT_METADATA
        and candidate.get("catalog_version") == CATALOG_V12_VERSION
        and candidate.get("description") == CATALOG_V12_DESCRIPTION
    ):
        return candidate
    # Canonical storage may contain runtime alias/context overrides on older
    # layers. Rebuild the reviewed v12 source layer before adding v13.
    return merge_v12_with_base(_pre_v12_payload(candidate))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v12 base whether canonical storage is older or materialized."""

    return _ensure_v12(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V13_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V13_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    has_metadata = "official_sources_v13" in payload or "source_document_v13" in payload
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V13CatalogValidationError("partial v13 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V13CatalogValidationError("v13 collides with a different function or intent definition")
    if payload.get("official_sources_v13") != OFFICIAL_SOURCES:
        raise V13CatalogValidationError("v13 official evidence registry differs")
    if payload.get("source_document_v13") != SOURCE_DOCUMENT_METADATA:
        raise V13CatalogValidationError("v13 source document SHA metadata differs")
    if payload.get("catalog_version") != CATALOG_V13_VERSION or payload.get("description") != CATALOG_V13_DESCRIPTION:
        raise V13CatalogValidationError("v13 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v13_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate source seal, exact scope, semantic depth, and fail-closed safety."""

    errors: list[str] = []
    actual_source_sha = hashlib.sha256(DESIGN_SOURCE_PATH.read_bytes()).hexdigest()
    if actual_source_sha != SOURCE_DOCUMENT_SHA256:
        errors.append(f"v13 source SHA differs: {actual_source_sha}")

    function_ids = [str(item["function_id"]) for item in V13_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V13_INTENTS]
    domain_ids = [str(item["domain"]) for item in V13_FUNCTIONS if not bool(item["terminal"])]
    terminal_ids = {str(item["function_id"]) for item in V13_FUNCTIONS if bool(item["terminal"])}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v13 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v13 intent IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(domain_ids):
        errors.append(f"duplicate v13 domain IDs: {sorted(duplicates)}")
    function_id_re = re.compile(r"^[a-z0-9_]+[.][a-z0-9_]+$")
    intent_id_re = re.compile(r"^v13_[a-z0-9_]+$")
    if any(function_id_re.fullmatch(value) is None for value in function_ids):
        errors.append("v13 contains a function ID outside the reviewed pattern")
    if any(intent_id_re.fullmatch(value) is None for value in intent_ids):
        errors.append("v13 contains an intent ID outside the reviewed pattern")

    domain_counts = Counter(str(item["domain"]) for item in V13_FUNCTIONS if bool(item["terminal"]))
    if dict(sorted(domain_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"v13 domain terminal counts differ: {dict(sorted(domain_counts.items()))}")
    if len(REQUIRED_DOMAINS) != 12 or len(V13_FUNCTIONS) != 252 or len(terminal_ids) != 240 or len(V13_INTENTS) != 240:
        errors.append("v13 requires exactly 12 domains, 12 hubs, 240 terminals, and 240 intents")

    sensitive_count = sum(bool(item["terminal"]) and not bool(item["state_changing"]) for item in V13_FUNCTIONS)
    consequential_count = sum(bool(item["terminal"]) and bool(item["state_changing"]) for item in V13_FUNCTIONS)
    if sensitive_count != 84 or consequential_count != 156:
        errors.append(f"v13 requires S=84 and C=156; got S={sensitive_count}, C={consequential_count}")

    urls: set[str] = set()
    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not an absolute HTTPS URL")
        if str(source.get("url")) in urls:
            errors.append(f"source {source_id} duplicates an official URL")
        urls.add(str(source.get("url")))
        required = {
            "publisher", "title", "url", "retrieved_at", "supported_roles",
            "supported_assets", "supported_states",
        }
        if not required <= set(source):
            errors.append(f"source {source_id} lacks required source metadata")
        if source.get("publisher") not in PUBLISHER_ALLOWLIST:
            errors.append(f"source {source_id} publisher is not allowlisted")
        if not source.get("supported_roles") or not source.get("supported_assets") or not source.get("supported_states"):
            errors.append(f"source {source_id} lacks supported roles, assets, or states")
        if source.get("evidence_level") != "official_primary" or source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} lacks official-primary collection metadata")
        if source.get("verified_status") != 200:
            errors.append(f"source {source_id} lacks verification metadata")
    if len(OFFICIAL_SOURCES) != 72 or len(urls) != 72:
        errors.append("v13 requires exactly 72 unique official-primary sources")
    if any(len(DOMAIN_SOURCE_IDS[domain]) != 6 for domain in REQUIRED_DOMAINS):
        errors.append("v13 requires exactly six reviewed official sources per domain")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    forbidden_keys = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_name",
        "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path",
        "pixel", "click_sequence",
    }
    for function in V13_FUNCTIONS:
        function_id = str(function["function_id"])
        aliases = function["aliases"]
        if len(aliases["ko-KR"]) < 8 or len(aliases["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 8:
            errors.append(f"{function_id}: insufficient positive or negative context")
        if len(function["role_hints"]) < 2 or len(function.get("asset_cues", [])) < 2:
            errors.append(f"{function_id}: incomplete role or asset semantics")
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
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))
            if "사용자" not in boundary or "user" not in boundary.casefold() or "press" not in boundary.casefold():
                errors.append(f"{function_id}: explicit user-owned final press is missing")
            classification = function.get("classification")
            if classification == "C":
                if not function["state_changing"] or function["risk_level"] != "high":
                    errors.append(f"{function_id}: C destination must be state-changing and high-risk")
            elif classification == "S":
                if function["state_changing"]:
                    errors.append(f"{function_id}: S destination cannot be state-changing")
            else:
                errors.append(f"{function_id}: classification must be S or C")
        elif function["automation_policy"] != "safe_navigation" or function["stop_policy"] != "continue":
            errors.append(f"{function_id}: hub must remain navigation-only")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    terminal_by_id = {str(item["function_id"]): item for item in V13_FUNCTIONS}
    intent_terminals = [str(item["terminal_function"]) for item in V13_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v13 requires exactly one intent per terminal function")
    for intent in V13_INTENTS:
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
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v13_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v13_discriminative_keys", "v13_negative_context_keys", "v13_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    semantic_matrix = build_semantic_development_matrix()
    collision_probes = build_collision_probes()
    recovery_matrix = build_state_permission_recovery_matrix()
    isolation_matrix = build_role_asset_isolation_matrix()
    if len(semantic_matrix) != 1440 or sum(item["kind"] == "positive" for item in semantic_matrix) != 480:
        errors.append("v13 semantic matrix must contain 1,440 probes with 480 positives")
    if len(COLLISION_FAMILIES) != 61 or len(collision_probes) != 732:
        errors.append("v13 collision suite must contain 61 families and 732 probes")
    if len({item["probe_id"] for item in collision_probes}) != 732:
        errors.append("v13 collision probe IDs are not unique")
    if any(item["expected_function"] not in terminal_ids for item in collision_probes):
        errors.append("v13 collision suite references an unknown terminal")
    if len(recovery_matrix) != 960 or len(isolation_matrix) != 720:
        errors.append("v13 recovery/isolation matrices must contain 960/720 probes")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v13 = _ensure_v12(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v13.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v13.get("intents", [])}
        base_domain_ids = {str(item["domain"]) for item in pre_v13.get("functions", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v13 function IDs collide with v1-v12: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v13 intent IDs collide with v1-v12: {collisions[:12]}")
        if collisions := sorted(REQUIRED_DOMAINS.intersection(base_domain_ids)):
            errors.append(f"v13 domain IDs collide with v1-v12: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v13.get("intents", []), *V13_INTENTS]:
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
            for intent in pre_v13.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v13_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V13_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v12")
                v13_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {signature: owners for signature, owners in v13_rule_owners.items() if len(owners) > 1}
        if shared_rules:
            errors.append(f"v13 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V13_FUNCTIONS, "intents": V13_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "pixel position",
        "recorded path", "fixed click", "oracle", "servicenow", "salesforce",
        "maximo", "arcgis",
    )
    if any(re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", semantic_text) for value in forbidden_fragments):
        errors.append("v13 runtime semantics contain a source identity or recorded UI path")

    if errors:
        raise V13CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V13_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V13_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "source_sha256": actual_source_sha,
        "aliases": sum(len(values) for item in V13_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V13_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V13_INTENTS),
        "sensitive_reads": sensitive_count,
        "state_changing": consequential_count,
        "semantic_smoke_probes": len(semantic_matrix),
        "collision_probes": len(collision_probes),
        "recovery_probes": len(recovery_matrix),
        "isolation_probes": len(isolation_matrix),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, fail-closed v12+v13 catalog copy."""

    validate_v13_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v12(base_payload)
    merged["catalog_version"] = CATALOG_V13_VERSION
    merged["description"] = CATALOG_V13_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V13_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V13_INTENTS)]
    merged["official_sources_v13"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_document_v13"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    return merged


def main() -> int:
    print(json.dumps(validate_v13_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
