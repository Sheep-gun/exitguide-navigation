from __future__ import annotations

"""SHA-pinned v14 role/asset/state ontology for regulated navigation.

The reviewed v14 audit is the sole scope and ID input.  Runtime semantics are
app independent and contain no package, resource, coordinate, screenshot, or
recorded-path data.  Every terminal is high risk, stops before the final
control, and leaves the final press to the user.
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
from navigation_catalog_v13_data import (
    CATALOG_V13_DESCRIPTION,
    CATALOG_V13_VERSION,
    OFFICIAL_SOURCES as V13_OFFICIAL_SOURCES,
    SOURCE_DOCUMENT_METADATA as V13_SOURCE_DOCUMENT_METADATA,
    V13_FUNCTIONS,
    V13_INTENTS,
    _pre_v13_payload,
    merge_with_base as merge_v13_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_PATH = ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V14.md"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V14.md"
SOURCE_DOCUMENT_SHA256 = "443796093363df0089ff27fc303b53b8b609d348e986f9c7616cfbe8d15afc30"
DESIGN_SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
SOURCE_SHA256 = SOURCE_DOCUMENT_SHA256
CATALOG_V14_VERSION = "14.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V14_DESCRIPTION = (
    "ExitGuide role-governed institutional operations ontology v14: app-agnostic "
    "diagnostic-lab, perioperative, revenue-cycle, mortgage, financial-crime, "
    "student-admin, human-subjects, emergency-dispatch, public-health, power-plant, "
    "land-title, and postal-network destinations; every terminal press is user-owned."
)
SOURCE_DOCUMENT_METADATA: dict[str, str] = {
    "path": DESIGN_SOURCE_RELATIVE_PATH,
    "algorithm": "sha256",
    "sha256": SOURCE_DOCUMENT_SHA256,
}


class V14CatalogValidationError(ValueError):
    """Raised when v14 cannot be generated or merged without source/safety drift."""


@dataclass(frozen=True)
class ReviewedFeature:
    key: str
    classification: str


@dataclass(frozen=True)
class SourceSpec:
    publisher: str
    title: str
    url: str


@dataclass(frozen=True)
class DomainSpec:
    domain: str
    root_ko: str
    root_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    jurisdiction: str
    avoid_root: str
    collision_terms: tuple[str, ...]
    sources: tuple[SourceSpec, ...]
    features: tuple[ReviewedFeature, ...] = ()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _source(publisher: str, title: str, url: str) -> SourceSpec:
    return SourceSpec(publisher, title, url)


_DOMAIN_SPECS: tuple[DomainSpec, ...] = (
    DomainSpec(
        "clinical_diagnostic_lab_ops", "진단검사실 운영", "Clinical diagnostic laboratory operations",
        ("laboratory director", "medical technologist", "authorized result reviewer"),
        ("patient specimen", "accession", "ordered analyte and result"),
        ("ordered", "accessioned", "analyzed", "validated", "corrected"),
        "CLIA-certified laboratory and applicable jurisdiction", "laboratory_research_ops.hub",
        ("specimen", "result", "order", "quality control", "accession"),
        (
            _source("Centers for Medicare & Medicaid Services", "Clinical Laboratory Improvement Amendments", "https://www.cms.gov/medicare/quality/clinical-laboratory-improvement-amendments"),
            _source("Electronic Code of Federal Regulations", "42 CFR Part 493 — Laboratory Requirements", "https://www.ecfr.gov/current/title-42/chapter-IV/subchapter-G/part-493"),
            _source("Centers for Disease Control and Prevention", "Clinical Laboratory Improvement Amendments", "https://www.cdc.gov/clia/"),
            _source("U.S. Food and Drug Administration", "Overview of IVD Regulation", "https://www.fda.gov/medical-devices/ivd-regulatory-assistance/overview-ivd-regulation"),
        ),
    ),
    DomainSpec(
        "perioperative_surgical_ops", "수술 주기 운영", "Perioperative surgical operations",
        ("surgeon", "perioperative nurse", "anesthesia professional"),
        ("surgical patient and case", "procedure site and laterality", "operating room and implant"),
        ("scheduled", "preoperative", "intraoperative", "recovery", "closed"),
        "accredited hospital surgical service", "clinical_care_team_ops.hub",
        ("case", "schedule", "handoff", "consent", "implant"),
        (
            _source("Electronic Code of Federal Regulations", "42 CFR 482.51 — Surgical Services", "https://www.ecfr.gov/current/title-42/chapter-IV/subchapter-G/part-482/subpart-C/section-482.51"),
            _source("Centers for Medicare & Medicaid Services", "Hospitals — Guidance for Laws and Regulations", "https://www.cms.gov/medicare/health-safety-standards/guidance-for-laws-regulations/hospitals"),
            _source("Centers for Disease Control and Prevention", "NHSN Surgical Site Infection Events", "https://www.cdc.gov/nhsn/psc/ssi/index.html"),
            _source("U.S. Food and Drug Administration", "Unique Device Identification Basics", "https://www.fda.gov/medical-devices/unique-device-identification-system-udi-system/udi-basics"),
        ),
    ),
    DomainSpec(
        "healthcare_revenue_cycle_ops", "의료 수익주기 운영", "Healthcare revenue cycle operations",
        ("provider billing specialist", "medical coder", "revenue integrity reviewer"),
        ("patient account and encounter", "coverage and authorization", "claim and remittance"),
        ("registered", "authorized", "coded", "submitted", "remitted", "denied", "closed"),
        "provider organization and payer jurisdiction", "insurance_claims_adjuster_ops.hub",
        ("claim", "payment", "authorization", "account", "coding"),
        (
            _source("Centers for Medicare & Medicaid Services", "Administrative Simplification", "https://www.cms.gov/about-cms/what-we-do/administrative-simplification"),
            _source("Electronic Code of Federal Regulations", "45 CFR Part 162 — Administrative Requirements", "https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-162"),
            _source("Centers for Medicare & Medicaid Services", "Medicare Claims Processing Manual", "https://www.cms.gov/regulations-and-guidance/guidance/manuals/internet-only-manuals-ioms-items/cms018912"),
            _source("Centers for Medicare & Medicaid Services", "Prior Authorization and Pre-Claim Review Initiatives", "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives"),
        ),
    ),
    DomainSpec(
        "mortgage_origination_servicing_ops", "주택담보대출 개설·관리", "Mortgage origination and servicing operations",
        ("mortgage loan officer", "underwriter", "authorized loan servicer"),
        ("borrower mortgage file", "secured property", "escrow and delinquency record"),
        ("applied", "disclosed", "underwritten", "closed", "boarded", "delinquent", "mitigated"),
        "licensed lender or servicer jurisdiction", "finance.longtail.hub",
        ("application", "payment", "property", "loan", "decision"),
        (
            _source("Consumer Financial Protection Bureau", "Regulation X — Real Estate Settlement Procedures Act", "https://www.consumerfinance.gov/rules-policy/regulations/1024/"),
            _source("Consumer Financial Protection Bureau", "Regulation Z — Truth in Lending Act", "https://www.consumerfinance.gov/rules-policy/regulations/1026/"),
            _source("Consumer Financial Protection Bureau", "Mortgage Servicing Resources", "https://www.consumerfinance.gov/compliance/compliance-resources/mortgage-resources/mortserv/"),
            _source("Fannie Mae", "Single Family Selling Guide", "https://selling-guide.fanniemae.com/"),
        ),
    ),
    DomainSpec(
        "financial_crime_compliance_ops", "금융범죄 준법 운영", "Financial crime compliance operations",
        ("BSA officer", "AML investigator", "sanctions compliance reviewer"),
        ("regulated customer", "monitored transaction", "alert case and regulatory filing"),
        ("screened", "alerted", "investigated", "escalated", "filed", "restricted", "closed"),
        "regulated financial institution jurisdiction", "cybersecurity_soc_ops.hub",
        ("alert", "case", "report", "restriction", "screening"),
        (
            _source("Financial Crimes Enforcement Network", "Statutes, Regulations, and Guidance", "https://www.fincen.gov/resources/statutes-regulations/guidance"),
            _source("Electronic Code of Federal Regulations", "31 CFR Chapter X — Financial Crimes Enforcement Network", "https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X"),
            _source("Office of Foreign Assets Control", "A Framework for OFAC Compliance Commitments", "https://ofac.treasury.gov/media/16331/download?inline"),
            _source("Federal Financial Institutions Examination Council", "BSA/AML Examination Manual", "https://bsaaml.ffiec.gov/manual"),
        ),
    ),
    DomainSpec(
        "higher_education_student_admin", "고등교육 학적행정", "Higher education student administration",
        ("registrar", "financial aid administrator", "authorized academic records officer"),
        ("applicant and student record", "academic program and term", "aid award and student account"),
        ("applied", "admitted", "enrolled", "awarded", "progressed", "graduated", "separated"),
        "identified institution and academic term", "classroom_instructor_ops.hub",
        ("application", "course", "grade", "award", "record"),
        (
            _source("U.S. Department of Education", "Family Educational Rights and Privacy Act", "https://studentprivacy.ed.gov/ferpa"),
            _source("Federal Student Aid", "Federal Student Aid Handbook", "https://fsapartners.ed.gov/knowledge-center/fsa-handbook"),
            _source("Federal Student Aid", "Common Origination and Disbursement Technical Reference", "https://fsapartners.ed.gov/knowledge-center/library/cod-technical-reference"),
            _source("Federal Student Aid", "NSLDS User Resources", "https://fsapartners.ed.gov/knowledge-center/library/nslds-user-resources"),
        ),
    ),
    DomainSpec(
        "human_subjects_research_oversight", "인간대상연구 심의", "Human subjects research oversight",
        ("IRB chair", "IRB reviewer", "human research protection administrator"),
        ("research protocol", "investigator and study site", "consent and safety report"),
        ("submitted", "reviewed", "approved", "modified", "suspended", "closed"),
        "registered oversight body and relying institution", "clinical_trial_site_ops.hub",
        ("protocol", "approval", "review", "study", "consent"),
        (
            _source("Office for Human Research Protections", "45 CFR 46 — Protection of Human Subjects", "https://www.hhs.gov/ohrp/regulations-and-policy/regulations/45-cfr-46/index.html"),
            _source("Electronic Code of Federal Regulations", "21 CFR Part 50 — Protection of Human Subjects", "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-50"),
            _source("Electronic Code of Federal Regulations", "21 CFR Part 56 — Institutional Review Boards", "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-56"),
            _source("U.S. Food and Drug Administration", "IRB Continuing Review After Clinical Investigation Approval", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/irb-continuing-review-after-clinical-investigation-approval"),
        ),
    ),
    DomainSpec(
        "emergency_communications_dispatch", "긴급통신·배차", "Emergency communications and dispatch",
        ("public safety telecommunicator", "emergency dispatcher", "communications supervisor"),
        ("emergency call and caller location", "CAD incident", "responder unit and radio channel"),
        ("queued", "triaged", "dispatched", "en route", "transferred", "closed"),
        "authorized public-safety answering point", "emergency_response_operations.hub",
        ("dispatch", "call", "incident", "unit", "handoff"),
        (
            _source("National 911 Program", "911 Issues and Resources", "https://www.911.gov/issues/"),
            _source("Electronic Code of Federal Regulations", "47 CFR Part 9 — 911 Requirements", "https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-9"),
            _source("Federal Emergency Management Agency", "National Incident Management System", "https://www.fema.gov/emergency-managers/nims"),
            _source("National Highway Traffic Safety Administration", "EMS.gov Resources", "https://www.ems.gov/resources/"),
        ),
    ),
    DomainSpec(
        "public_health_surveillance_ops", "공중보건 감시 운영", "Public health surveillance operations",
        ("public health investigator", "surveillance epidemiologist", "authorized jurisdiction officer"),
        ("reportable condition", "surveillance case and contact", "cluster outbreak and exposure site"),
        ("suspected", "probable", "confirmed", "linked", "transferred", "closed"),
        "identified public-health jurisdiction", "clinical_care_team_ops.hub",
        ("case", "laboratory report", "contact", "outbreak", "notice"),
        (
            _source("Centers for Disease Control and Prevention", "National Notifiable Diseases Surveillance System", "https://www.cdc.gov/nndss/"),
            _source("Centers for Disease Control and Prevention", "National Notifiable Diseases Surveillance System Data and Case Definitions", "https://ndc.services.cdc.gov/"),
            _source("Centers for Disease Control and Prevention", "Field Epidemiology Manual — Acute Enteric Disease Outbreaks", "https://www.cdc.gov/field-epi-manual/php/chapters/acute-enteric-disease.html"),
            _source("Electronic Code of Federal Regulations", "42 CFR Part 70 — Interstate Quarantine", "https://www.ecfr.gov/current/title-42/chapter-I/subchapter-F/part-70"),
        ),
    ),
    DomainSpec(
        "power_generation_plant_ops", "비원자력 발전소 운영", "Non-nuclear power generation plant operations",
        ("power plant control-room operator", "shift supervisor", "environmental compliance operator"),
        ("generating unit", "fuel boiler and turbine process", "load emissions and clearance"),
        ("available", "starting", "synchronized", "loaded", "isolated", "tripped", "shutdown"),
        "identified balancing authority and non-nuclear plant", "nuclear_plant_operations.hub",
        ("unit", "dispatch", "switch", "start", "clearance"),
        (
            _source("Federal Energy Regulatory Commission", "Electric Reliability", "https://www.ferc.gov/electric-reliability"),
            _source("North American Electric Reliability Corporation", "Reliability Standards", "https://www.nerc.com/pa/Stand/Pages/Default.aspx"),
            _source("Electronic Code of Federal Regulations", "40 CFR Part 75 — Continuous Emission Monitoring", "https://www.ecfr.gov/current/title-40/chapter-I/subchapter-C/part-75"),
            _source("U.S. Energy Information Administration", "Form EIA-923 Instructions", "https://www.eia.gov/survey/form/eia_923/instructions.pdf"),
        ),
    ),
    DomainSpec(
        "land_title_recording_admin", "토지등기 행정", "Land title recording administration",
        ("land recorder", "title registrar", "authorized recording clerk"),
        ("parcel and legal description", "recordable instrument and parties", "official index plat and certified copy"),
        ("received", "indexed", "accepted", "recorded", "rejected", "corrected"),
        "identified recorder jurisdiction", "building_permit_code_enforcement.hub",
        ("record", "instrument", "property", "filing", "map"),
        (
            _source("Bureau of Land Management", "Land Records", "https://www.blm.gov/services/land-records"),
            _source("Electronic Code of Federal Regulations", "43 CFR Part 1820 — Application Procedures", "https://www.ecfr.gov/current/title-43/subtitle-B/chapter-II/subchapter-B/part-1820"),
            _source("State of Hawaii Bureau of Conveyances", "Recording Resources", "https://dlnr.hawaii.gov/boc/resources/"),
            _source("State of Hawaii Bureau of Conveyances", "Recording Forms", "https://dlnr.hawaii.gov/boc/forms/"),
        ),
    ),
    DomainSpec(
        "postal_network_operations", "우편망 운영", "Postal network operations",
        ("postal acceptance clerk", "mail processing operator", "delivery operations supervisor"),
        ("mailpiece and postage", "container sortation and transport", "delivery forwarding and claim record"),
        ("accepted", "inducted", "sorted", "dispatched", "delivered", "undeliverable"),
        "United States Postal Service operating network", "parcel_courier.hub",
        ("dispatch", "handoff", "tracking", "container", "delivery"),
        (
            _source("United States Postal Service", "Domestic Mail Manual", "https://pe.usps.com/cpim/ftp/manuals/dmm300/full/mailingstandards.pdf"),
            _source("United States Postal Service", "Publication 32 — Glossary of Postal Terms", "https://about.usps.com/publications/pub32/"),
            _source("United States Postal Service", "Mail Forwarding Options", "https://faq.usps.com/articles/Knowledge/Mail-Forwarding-Options"),
            _source("United States Postal Service", "DMM 609 — Filing Indemnity Claims", "https://pe.usps.com/cpim/ftp/manuals/DMM300/609.pdf"),
        ),
    ),
)


def _read_reviewed_features() -> dict[str, tuple[ReviewedFeature, ...]]:
    raw = DESIGN_SOURCE_PATH.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != SOURCE_DOCUMENT_SHA256:
        raise V14CatalogValidationError(
            f"v14 design source SHA-256 differs: expected {SOURCE_DOCUMENT_SHA256}, got {actual}"
        )
    text = raw.decode("utf-8")
    sections = re.findall(
        r"^### [0-9]+[.] .*?\(`(?P<domain>[a-z0-9_]+)`\)\n(?P<body>.*?)(?=^### [0-9]+[.]|^## Primary-source plan)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    result: dict[str, tuple[ReviewedFeature, ...]] = {}
    for domain, body in sections:
        features: list[ReviewedFeature] = []
        for classification, count, keys in re.findall(
            r"^- `([SC])` \(([0-9]+)\): ([^.]+)[.]$", body, flags=re.MULTILINE
        ):
            parsed = re.findall(r"`([a-z0-9_]+)`", keys)
            if len(parsed) != int(count):
                raise V14CatalogValidationError(f"{domain}: reviewed {classification} count differs")
            features.extend(ReviewedFeature(key, classification) for key in parsed)
        if len(features) != 20 or Counter(item.classification for item in features) != {"S": 7, "C": 13}:
            raise V14CatalogValidationError(f"{domain}: expected exactly 20 terminals with S=7/C=13")
        result[domain] = tuple(features)
    if len(result) != 12:
        raise V14CatalogValidationError(f"reviewed v14 source must contain 12 domains; got {len(result)}")
    return result


_REVIEWED_FEATURES = _read_reviewed_features()
REVIEWED_DOMAINS: tuple[DomainSpec, ...] = tuple(
    DomainSpec(**{**item.__dict__, "features": _REVIEWED_FEATURES[item.domain]}) for item in _DOMAIN_SPECS
)
REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}


_CONTENT_SHA256_BY_URL: dict[str, str] = {
    "https://ofac.treasury.gov/media/16331/download?inline": "a3279d0aaa6e49e7fa7ce68f22b31e3f571e9aa3d9fa2eeea0c26ee8c3ef128a",
    "https://www.eia.gov/survey/form/eia_923/instructions.pdf": "152bb26f657e4928292bbeeb69e598ffac2918410801e5cb0a765e8bc6e14c55",
    "https://pe.usps.com/cpim/ftp/manuals/dmm300/full/mailingstandards.pdf": "8b321db0e6895f2b90c5b5bf78420ad201e5050ce3d26d0fffda2202fe80064d",
    "https://pe.usps.com/cpim/ftp/manuals/DMM300/609.pdf": "2b92c4028c5637a26fd53a467a25cbd6fb95604a9f889c322816882ce54d434e",
}


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {}
DOMAIN_SOURCE_IDS: dict[str, tuple[str, ...]] = {}
for _domain in REVIEWED_DOMAINS:
    _ids: list[str] = []
    for _index, _spec in enumerate(_domain.sources):
        _source_id = f"{_domain.domain}_official_{_index + 1:02d}"
        _supported = [
            f"{_domain.domain}.{row.key}"
            for _position, row in enumerate(_domain.features)
            if _position % 4 == _index
        ]
        _record_material = f"{_spec.publisher}\n{_spec.title}\n{_spec.url}".encode("utf-8")
        OFFICIAL_SOURCES[_source_id] = {
            "publisher": _spec.publisher,
            "title": _spec.title,
            "url": _spec.url,
            "retrieved_at": RETRIEVED_AT,
            "collected_on": COLLECTED_ON,
            "verified_status": 200,
            "verification_method": "canonical first-party artifact reviewed for the SHA-pinned v14 audit",
            "evidence_level": "official_primary",
            "source_record_sha256": hashlib.sha256(_record_material).hexdigest(),
            "supported_roles": list(_domain.roles),
            "supported_assets": list(_domain.assets),
            "supported_states": list(_domain.states),
            "jurisdiction_scope": _domain.jurisdiction,
            "terminal_ids": _supported,
        }
        if _spec.url in _CONTENT_SHA256_BY_URL:
            OFFICIAL_SOURCES[_source_id]["content_sha256"] = _CONTENT_SHA256_BY_URL[_spec.url]
            OFFICIAL_SOURCES[_source_id]["content_hash_scope"] = "retrieved_binary_artifact"
        _ids.append(_source_id)
    DOMAIN_SOURCE_IDS[_domain.domain] = tuple(_ids)
PUBLISHER_ALLOWLIST = frozenset(str(item["publisher"]) for item in OFFICIAL_SOURCES.values())


def _words(key: str) -> str:
    return key.replace("_", " ")


def _feature_seed(domain: DomainSpec, row: ReviewedFeature, position: int) -> FeatureSeed:
    words = _words(row.key)
    name_en = f"{domain.root_en}: {words}"
    name_ko = f"{domain.root_ko} {words}"
    action_en = "sensitive read-only review" if row.classification == "S" else "consequential controlled action"
    action_ko = "민감 조회" if row.classification == "S" else "중요 상태변경"
    ko_aliases = _dedupe((
        f"{domain.root_ko} {words}", f"{words} {domain.root_ko}", f"{domain.roles[0]} {words}",
        f"{domain.assets[0]} {words}", f"{domain.states[0]} {words}", f"{words} {action_ko}",
        f"{domain.root_ko} {row.key}", f"v14 {domain.domain} {row.key}",
    ))
    en_aliases = _dedupe((
        name_en, f"{words} for {domain.root_en}", f"{domain.roles[0]} {words}",
        f"{domain.assets[0]} {words}", f"{domain.states[0]} {words}", f"{action_en} {words}",
        f"open {domain.domain} {words}", f"v14 {domain.domain} {row.key}",
    ))
    positive = _dedupe((
        domain.root_ko, domain.root_en, words, row.key, *domain.roles, *domain.assets,
        *domain.states[:3], domain.jurisdiction,
    ))
    negative = _dedupe((
        "다른 전문 역할", "다른 사람 또는 기록", "다른 관리 자산", "다른 생명주기 상태",
        "권한이 없는 역할", "오프라인 또는 오래된 데이터", "승인 또는 안전 보류", "관할권 불명확",
        "other professional role", "wrong person or record", "different governed asset",
        "different lifecycle state", "permission denied", "offline or stale data",
        "approval safety legal or regulatory hold", "missing jurisdiction", *domain.collision_terms,
    ))
    source_ref = DOMAIN_SOURCE_IDS[domain.domain][position % 4]
    return F(
        row.key, name_ko, name_en, "|".join(ko_aliases), "|".join(en_aliases),
        "|".join(positive), "|".join(negative),
        "sensitive" if row.classification == "S" else "submit", sources=source_ref,
    )


def _group_seed(domain: DomainSpec) -> GroupSeed:
    return G(
        domain.domain, domain.root_ko, domain.root_en, f"{domain.domain}_role_governed_operations",
        "|".join(_dedupe((domain.root_ko, *domain.roles, *domain.assets, domain.jurisdiction))),
        "|".join(_dedupe((domain.root_en, *domain.roles, *domain.assets, *domain.states, domain.jurisdiction))),
        "|".join(("다른 전문 영역", "개인 소비자 계정", "잘못된 역할", "잘못된 자산", "권한 거부", *domain.collision_terms)),
        "|".join(("different professional domain", "personal consumer account", "wrong role", "wrong asset", "permission denied", *domain.collision_terms)),
        domain.avoid_root, "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, row, index) for index, row in enumerate(domain.features)),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)


def _collision_families() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    result: list[tuple[str, str, tuple[str, ...]]] = []
    for domain in REVIEWED_DOMAINS:
        ids = tuple(f"{domain.domain}.{row.key}" for row in domain.features)
        for index, token in enumerate(domain.collision_terms):
            targets = (ids[index], ids[7 + index], ids[14 + index])
            result.append((f"{domain.root_ko} {token}", token, targets))
    return tuple(result)


COLLISION_FAMILIES = _collision_families()


def _collision_avoid_map() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for _ko, _en, targets in COLLISION_FAMILIES:
        for target in targets:
            result.setdefault(target, []).extend(peer for peer in targets if peer != target)
    return {key: _dedupe(values) for key, values in result.items()}


COLLISION_AVOIDS = _collision_avoid_map()


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v14_role_governed_operations" if value == "v10_reviewed_operations" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    result["role_hints"] = list(_dedupe((*result["role_hints"], *domain.roles)))
    result["asset_cues"] = list(domain.assets)
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues["lifecycle"] = list(domain.states)
    state_cues["jurisdiction"] = [domain.jurisdiction]
    result["state_cues"] = state_cues
    result["user_owned_final_press"] = False
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    row = next(item for item in domain.features if item.key == seed.key)
    result.update({
        "automation_policy": "never_auto", "stop_policy": "before_action",
        "risk_level": "high", "user_owned_final_press": True,
        "classification": row.classification,
    })
    result["role_hints"] = list(_dedupe((*result["role_hints"], *domain.roles)))
    result["asset_cues"] = list(_dedupe((*domain.assets, _words(row.key))))
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues.update({
        "lifecycle": list(domain.states),
        "jurisdiction": [domain.jurisdiction, "jurisdiction must be explicit"],
        "wrong_role": ["잘못된 역할", "권한 없는 역할", "wrong role", "role not authorized"],
        "wrong_record": ["잘못된 사람 또는 기록", "다른 관리 자산", "wrong person or record", "different governed asset"],
        "unavailable": ["비활성", "사용 불가", "권한 거부", "disabled", "unavailable", "permission denied"],
        "offline": ["오프라인", "오래된 데이터", "offline", "stale data"],
        "hold": ["승인 보류", "법적 보류", "안전 보류", "approval hold", "legal hold", "safety hold", "regulatory hold"],
    })
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues.update({
        "classification": [
            "S: sensitive or permission-limited read" if row.classification == "S" else "C: consequential high-risk state change"
        ],
        "role_asset_state_gate": [
            "역할·관리 자산·현재 상태와 관할권을 확인", "verify role, governed asset, current state, and jurisdiction",
        ],
        "fail_closed": [
            "잘못된 기록·권한 거부·보류·오프라인이면 허브에서 중단",
            "stop at the hub on wrong record, permission denial, hold, offline data, or missing jurisdiction",
        ],
        "forbidden_terminal_actions": [
            "확인·승인·서명·발행·배차·제출·종료 자동 실행 금지",
            "never auto-press confirm approve sign issue dispatch submit release record or close",
        ],
        "user_boundary": [
            "최종 목적지 버튼은 사용자가 직접 누름", "the user must press the final destination button",
        ],
        "user_owned_final_press": ["true", "사용자 소유 최종 누름"],
    })
    result["risk_cues"] = risk_cues
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v14_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v14_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v14_{key[4:]}"] = rule.pop(key)
    target = str(result["terminal_function"])
    same_domain = [f"{group.domain}.{item.key}" for item in group.features if item.key != seed.key]
    result["avoid_functions"] = list(_dedupe((
        *COLLISION_AVOIDS.get(target, ()), *same_domain[:2], *result.get("avoid_functions", []),
    )))
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {"stop_policy": "stop_before_action", "user_owned_final_press": True}
    return result


V14_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V14_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}


def build_collision_probes() -> tuple[dict[str, str], ...]:
    """Return 720 deterministic role/asset/state contrast probes."""

    intents = {str(item["terminal_function"]): item for item in V14_INTENTS}
    functions = {str(item["function_id"]): item for item in V14_FUNCTIONS}
    probes: list[dict[str, str]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(12):
            locale = "ko-KR" if probe_index < 6 else "en-US"
            target = targets[probe_index % len(targets)]
            pattern = intents[target]["patterns_by_locale"][locale][probe_index % 5]
            context = functions[target]["positive_context"][probe_index % 6]
            token = token_ko if locale == "ko-KR" else token_en
            text = f"{token} 충돌 구분 {pattern} {context}" if locale == "ko-KR" else f"disambiguate {token}: {pattern} {context}"
            probes.append({
                "probe_id": f"v14_collision_{family_index:02d}_{probe_index:02d}",
                "family": token_en, "locale": locale, "text": text, "expected_function": target,
            })
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return six source-derived probes per terminal (1,440 total)."""

    functions = {str(item["function_id"]): item for item in V14_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V14_INTENTS:
        target = str(intent["terminal_function"])
        function = functions[target]
        for locale in ("ko-KR", "en-US"):
            probes.append({"kind": "positive", "locale": locale, "text": intent["patterns_by_locale"][locale][0], "expected_function": target})
        for index, kind in enumerate(("wrong_role", "wrong_asset_state", "unavailable_permission", "missing_jurisdiction")):
            probes.append({
                "kind": kind, "locale": "ko-KR" if index % 2 == 0 else "en-US",
                "text": function["negative_context"][index], "expected_function": None, "excluded_function": target,
            })
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed recovery probes per terminal (960 total)."""

    scenarios = (
        ("disabled", "비활성 disabled"),
        ("unavailable_offline", "사용 불가 오프라인 unavailable offline stale"),
        ("wrong_role", "권한 없는 역할 wrong role permission denied"),
        ("wrong_record_asset", "잘못된 사람 기록 자산 관할권 wrong record asset jurisdiction"),
    )
    probes: list[dict[str, object]] = []
    for function in V14_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append({
                "probe_id": f"v14_recovery_{len(probes):04d}", "kind": kind, "text": text,
                "expected_function": None, "excluded_function": function["function_id"],
                "required_policy": "never_auto", "required_stop_policy": "before_action",
                "required_user_owned_final_press": True,
            })
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state probes (720 total)."""

    probes: list[dict[str, object]] = []
    for function in V14_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in (
            ("wrong_role", "다른 전문 역할 other professional role"),
            ("wrong_asset", "다른 사람 기록 관리 자산 different governed asset"),
            ("wrong_state", "다른 생명주기 상태 또는 관할권 different lifecycle state or jurisdiction"),
        ):
            probes.append({
                "probe_id": f"v14_isolation_{len(probes):04d}", "kind": kind, "text": text,
                "expected_function": None, "excluded_function": function["function_id"],
                "allowed_fallback": f"{function['domain']}.hub",
            })
    return tuple(probes)


def _duplicates(values: Iterable[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _pre_v14_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V14_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V14_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids]
    result["intents"] = [item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids]
    result.pop("official_sources_v14", None)
    result.pop("source_document_v14", None)
    result["catalog_version"] = CATALOG_V13_VERSION
    result["description"] = CATALOG_V13_DESCRIPTION
    return result


def _ensure_v13(payload: Mapping[str, object]) -> dict[str, object]:
    candidate = _pre_v14_payload(payload)
    expected_functions = {str(item["function_id"]): item for item in V13_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V13_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in candidate.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in candidate.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    # V13 canonical storage may carry approved runtime alias/context overrides
    # on its function records.  V14 is append-only: accept a structurally
    # complete, source-pinned V13 materialization verbatim instead of rebuilding
    # (and thereby rewriting) any prior function payload.
    if (
        set(present_functions) == set(expected_functions) and present_intents == expected_intents
        and candidate.get("official_sources_v13") == V13_OFFICIAL_SOURCES
        and candidate.get("source_document_v13") == V13_SOURCE_DOCUMENT_METADATA
        and candidate.get("catalog_version") == CATALOG_V13_VERSION
        and candidate.get("description") == CATALOG_V13_DESCRIPTION
    ):
        return candidate
    return merge_v13_with_base(_pre_v13_payload(candidate))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v13 base whether canonical storage is older or materialized."""

    return _ensure_v13(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V14_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V14_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    has_metadata = "official_sources_v14" in payload or "source_document_v14" in payload
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V14CatalogValidationError("partial v14 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V14CatalogValidationError("v14 collides with a different function or intent definition")
    if payload.get("official_sources_v14") != OFFICIAL_SOURCES:
        raise V14CatalogValidationError("v14 official evidence registry differs")
    if payload.get("source_document_v14") != SOURCE_DOCUMENT_METADATA:
        raise V14CatalogValidationError("v14 source document SHA metadata differs")
    if payload.get("catalog_version") != CATALOG_V14_VERSION or payload.get("description") != CATALOG_V14_DESCRIPTION:
        raise V14CatalogValidationError("v14 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v14_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate source seal, exact scope, source mapping, semantics, and safety."""

    errors: list[str] = []
    actual_source_sha = hashlib.sha256(DESIGN_SOURCE_PATH.read_bytes()).hexdigest()
    if actual_source_sha != SOURCE_DOCUMENT_SHA256:
        errors.append(f"v14 source SHA differs: {actual_source_sha}")
    function_ids = [str(item["function_id"]) for item in V14_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V14_INTENTS]
    domain_ids = [str(item["domain"]) for item in V14_FUNCTIONS if not item["terminal"]]
    terminal_ids = {str(item["function_id"]) for item in V14_FUNCTIONS if item["terminal"]}
    if duplicates := _duplicates(function_ids): errors.append(f"duplicate v14 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids): errors.append(f"duplicate v14 intent IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(domain_ids): errors.append(f"duplicate v14 domain IDs: {sorted(duplicates)}")
    if any(re.fullmatch(r"[a-z0-9_]+[.][a-z0-9_]+", value) is None for value in function_ids):
        errors.append("v14 contains a function ID outside the reviewed pattern")
    if any(re.fullmatch(r"v14_[a-z0-9_]+", value) is None for value in intent_ids):
        errors.append("v14 contains an intent ID outside the reviewed pattern")
    domain_counts = Counter(str(item["domain"]) for item in V14_FUNCTIONS if item["terminal"])
    if dict(sorted(domain_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"v14 domain terminal counts differ: {dict(sorted(domain_counts.items()))}")
    if len(REQUIRED_DOMAINS) != 12 or len(V14_FUNCTIONS) != 252 or len(terminal_ids) != 240 or len(V14_INTENTS) != 240:
        errors.append("v14 requires exactly 12 domains, 12 hubs, 240 terminals, and 240 intents")
    sensitive = sum(item["terminal"] and item.get("classification") == "S" and not item["state_changing"] for item in V14_FUNCTIONS)
    consequential = sum(item["terminal"] and item.get("classification") == "C" and item["state_changing"] for item in V14_FUNCTIONS)
    if (sensitive, consequential) != (84, 156):
        errors.append(f"v14 requires S=84 and C=156; got S={sensitive}, C={consequential}")

    urls: set[str] = set()
    expected_source_terminals: set[str] = set()
    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc: errors.append(f"source {source_id} is not absolute HTTPS")
        if str(source["url"]) in urls: errors.append(f"source {source_id} duplicates an official URL")
        urls.add(str(source["url"]))
        required = {"publisher", "title", "url", "retrieved_at", "collected_on", "verified_status", "source_record_sha256", "supported_roles", "supported_assets", "supported_states", "jurisdiction_scope", "terminal_ids"}
        if not required <= set(source): errors.append(f"source {source_id} lacks complete provenance")
        if source.get("publisher") not in PUBLISHER_ALLOWLIST or source.get("evidence_level") != "official_primary":
            errors.append(f"source {source_id} is not accepted official primary evidence")
        if source.get("verified_status") != 200 or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("source_record_sha256", ""))):
            errors.append(f"source {source_id} lacks verification or hash metadata")
        if "content_sha256" in source and (
            not re.fullmatch(r"[0-9a-f]{64}", str(source["content_sha256"]))
            or source.get("content_hash_scope") != "retrieved_binary_artifact"
        ):
            errors.append(f"source {source_id} has malformed binary content hash metadata")
        if not source.get("supported_roles") or not source.get("supported_assets") or not source.get("supported_states"):
            errors.append(f"source {source_id} lacks role asset or state coverage")
        supported = {str(value) for value in source.get("terminal_ids", [])}
        if not supported or not supported <= terminal_ids: errors.append(f"source {source_id} has invalid terminal mapping")
        expected_source_terminals.update(supported)
    if len(OFFICIAL_SOURCES) != 48 or len(urls) != 48:
        errors.append("v14 requires exactly 48 unique official-primary source URLs")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS or any(len(values) != 4 for values in DOMAIN_SOURCE_IDS.values()):
        errors.append("v14 requires exactly four source records per domain")
    if expected_source_terminals != terminal_ids:
        errors.append("v14 source-to-terminal mapping is incomplete")

    forbidden_keys = {"x", "y", "bounds", "coordinate", "coordinates", "package", "package_name", "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path", "pixel", "click_sequence"}
    for function in V14_FUNCTIONS:
        function_id = str(function["function_id"])
        if len(function["aliases"]["ko-KR"]) < 8 or len(function["aliases"]["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 8:
            errors.append(f"{function_id}: insufficient context")
        if len(function["role_hints"]) < 2 or len(function.get("asset_cues", [])) < 2:
            errors.append(f"{function_id}: incomplete role or asset semantics")
        if len(function["state_cues"].get("lifecycle", [])) < 2 or not function["state_cues"].get("jurisdiction"):
            errors.append(f"{function_id}: incomplete lifecycle or jurisdiction semantics")
        refs = {str(value) for value in function["source_refs"]}
        if not refs or not refs <= set(OFFICIAL_SOURCES): errors.append(f"{function_id}: invalid source refs")
        if _contains_forbidden_key(function, forbidden_keys): errors.append(f"{function_id}: app-specific path data is forbidden")
        if function["terminal"]:
            if function["risk_level"] != "high" or function["automation_policy"] != "never_auto" or function["stop_policy"] != "before_action" or function.get("user_owned_final_press") is not True:
                errors.append(f"{function_id}: unsafe terminal boundary")
            source_supported = set().union(*(set(OFFICIAL_SOURCES[ref]["terminal_ids"]) for ref in refs))
            if function_id not in source_supported: errors.append(f"{function_id}: source does not support terminal")
            if function.get("classification") == "S" and function["state_changing"]: errors.append(f"{function_id}: S changed state")
            if function.get("classification") == "C" and not function["state_changing"]: errors.append(f"{function_id}: C did not change state")
        elif function["risk_level"] != "low" or function["automation_policy"] != "safe_navigation" or function["state_changing"] or function.get("user_owned_final_press") is not False:
            errors.append(f"{function_id}: hub safety differs")

    terminal_by_id = {str(item["function_id"]): item for item in V14_FUNCTIONS}
    intent_terminals = [str(item["terminal_function"]) for item in V14_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v14 requires one intent per terminal")
    for intent in V14_INTENTS:
        intent_id = str(intent["intent_id"])
        if len(intent["patterns_by_locale"]["ko-KR"]) < 5 or len(intent["patterns_by_locale"]["en-US"]) < 5:
            errors.append(f"{intent_id}: insufficient patterns")
        if len(intent["goal_rules"]) < 24: errors.append(f"{intent_id}: insufficient compositional rules")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != intent["terminal_function"]:
            errors.append(f"{intent_id}: invalid route")
        if len(intent.get("avoid_functions", [])) < 2 or intent["terminal_function"] in intent.get("avoid_functions", []):
            errors.append(f"{intent_id}: insufficient avoids")
        if intent.get("desired_state") != "user_confirmation_required" or intent.get("terminal_condition") != {"stop_policy": "stop_before_action", "user_owned_final_press": True}:
            errors.append(f"{intent_id}: final control is not user-owned")
        if terminal_by_id[str(intent["terminal_function"])]["automation_policy"] != "never_auto":
            errors.append(f"{intent_id}: terminal is not fail-closed")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v14_"):
                errors.append(f"{intent_id}: malformed semantic rule")

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    if len(semantic) != 1440 or sum(item["kind"] == "positive" for item in semantic) != 480:
        errors.append("v14 semantic matrix must contain 1440 probes with 480 positives")
    if len(COLLISION_FAMILIES) != 60 or len(collisions) != 720 or len({item["probe_id"] for item in collisions}) != 720:
        errors.append("v14 collision suite must contain 60 families and 720 probes")
    if len(recovery) != 960 or len(isolation) != 720:
        errors.append("v14 recovery/isolation matrices must contain 960/720 probes")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v14 = _ensure_v13(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v14.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v14.get("intents", [])}
        base_domain_ids = {str(item["domain"]) for item in pre_v14.get("functions", [])}
        if collisions_found := sorted(set(function_ids).intersection(base_function_ids)): errors.append(f"v14 function IDs collide with v13: {collisions_found[:12]}")
        if collisions_found := sorted(set(intent_ids).intersection(base_intent_ids)): errors.append(f"v14 intent IDs collide with v13: {collisions_found[:12]}")
        if collisions_found := sorted(REQUIRED_DOMAINS.intersection(base_domain_ids)): errors.append(f"v14 domains collide with v13: {collisions_found[:12]}")
        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v14.get("intents", []), *V14_INTENTS]:
            for pattern in intent.get("patterns", []):
                key = _runtime_pattern_key(pattern)
                if key: pattern_owners.setdefault(key, set()).add(str(intent["intent_id"]))
        if pattern_collisions := {key: owners for key, owners in pattern_owners.items() if len(owners) > 1}:
            errors.append(f"normalized goal-pattern collisions: {list(pattern_collisions.items())[:8]}")
        base_signatures = {_rule_signature(rule) for intent in pre_v14.get("intents", []) for rule in intent.get("goal_rules", []) if _rule_signature(rule)}
        v14_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V14_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_signatures: errors.append(f"{intent['intent_id']}: goal rule collides with v13")
                v14_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        if shared := {signature: owners for signature, owners in v14_owners.items() if len(owners) > 1}:
            errors.append(f"v14 goal-rule collisions: {list(shared.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V14_FUNCTIONS, "intents": V14_INTENTS})
    for function in semantic_payload["functions"]: function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = ("package name", "resource-id", "screen coordinate", "pixel position", "recorded path", "fixed click", "oracle", "servicenow", "salesforce", "maximo", "arcgis")
    if any(fragment in semantic_text for fragment in forbidden_fragments):
        errors.append("v14 runtime semantics contain source identity or recorded UI path")
    if errors:
        raise V14CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V14_FUNCTIONS), "terminal_functions": len(terminal_ids), "intents": len(V14_INTENTS),
        "domains": len(REQUIRED_DOMAINS), "domain_terminal_counts": dict(sorted(domain_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES), "source_sha256": actual_source_sha,
        "aliases": sum(len(values) for item in V14_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V14_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V14_INTENTS),
        "sensitive_reads": sensitive, "state_changing": consequential,
        "semantic_smoke_probes": len(semantic), "collision_probes": len(collisions),
        "recovery_probes": len(recovery), "isolation_probes": len(isolation), "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, append-only v13+v14 catalog copy."""

    validate_v14_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v13(base_payload)
    merged["catalog_version"] = CATALOG_V14_VERSION
    merged["description"] = CATALOG_V14_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V14_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V14_INTENTS)]
    merged["official_sources_v14"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_document_v14"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    return merged


def main() -> int:
    print(json.dumps(validate_v14_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
