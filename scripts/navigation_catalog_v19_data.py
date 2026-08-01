from __future__ import annotations

"""Research-isolated V19 catalog and inherited Korean display correction.

The module composes only in memory on the exact V18 candidate payload.  It
adds nine evidence-backed citizen/applicant/participant domains and applies a
reversible display-only localization overlay to thirteen inherited V12
functions.  It never writes the canonical catalog or any runtime fixture.
"""

import copy
import hashlib
import json
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from navigation_catalog_v10_data import (
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v10_build_feature,
    _build_intent as _v10_build_intent,
    _build_root as _v10_build_root,
    _runtime_pattern_key,
)
from navigation_catalog_v12_data import V12_FUNCTIONS
from navigation_catalog_v18_data import (
    CATALOG_V18_DESCRIPTION,
    CATALOG_V18_VERSION,
    EXPECTED_V18_LAYER_SHA256,
    V18_FUNCTIONS,
    V18_INTENTS,
    V18_LAYER_SHA256,
    load_base_catalog as load_v17_source_base,
    merge_with_base as merge_v18_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V19_RESEARCH.md"
SOURCE_DOCUMENT_SHA256 = {
    DESIGN_SOURCE_RELATIVE_PATH: "f5997e4728a3131b995d2796a9b61cc943aeaf66d82d1e1ee3b5da811dc27d6b",
}
SOURCE_DOCUMENT_METADATA = {
    path: {"path": path, "algorithm": "sha256", "sha256": digest}
    for path, digest in SOURCE_DOCUMENT_SHA256.items()
}
SOURCE_DOCUMENT_TEXT_PROFILE = {
    "hangul_syllables": 0,
    "replacement_characters": 0,
}
BASE_LAYER_SEAL = {
    "catalog_version": CATALOG_V18_VERSION,
    "algorithm": "sha256",
    "sha256": EXPECTED_V18_LAYER_SHA256,
}

CATALOG_V19_VERSION = "19.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V19_DESCRIPTION = (
    "ExitGuide research-isolated V19 ontology for voter registration, vital "
    "records, nutrition assistance, self-represented court cases, jury summons, "
    "consumer postal mail, public health coverage, retirement-plan participant "
    "requests, and consular visa applications; every terminal press remains "
    "user-owned, with a reversible inherited Korean display correction."
)

BASELINE_COUNTS = {"domains": 215, "functions": 3610, "intents": 3368}
PROJECTED_COUNTS = {
    "domains": 224,
    "physical_functions": 3733,
    "physical_terminal_functions": 3482,
    "physical_intents": 3482,
}


class V19CatalogValidationError(ValueError):
    """Raised when V19 cannot be proven complete, isolated, and reversible."""


@dataclass(frozen=True)
class FeatureRow:
    key: str
    classification: str
    name_ko: str
    name_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    source_tags: tuple[str, ...]


@dataclass(frozen=True)
class ReviewedFeature:
    key: str
    classification: str
    name_ko: str
    name_en: str
    goal_ko: str
    goal_en: str
    purpose_ko: str
    purpose_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    jurisdiction_guard: str
    safety_boundary: str
    source_tags: tuple[str, ...]


@dataclass(frozen=True)
class DomainSpec:
    domain: str
    root_ko: str
    root_en: str
    role_ko: str
    jurisdiction: str
    boundary: str
    avoid_root: str
    collision_terms: tuple[str, ...]
    nearest_existing_functions: tuple[str, ...]
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    features: tuple[ReviewedFeature, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _terms(value: str) -> tuple[str, ...]:
    return _dedupe(value.split("|"))


def R(
    key: str,
    classification: str,
    name_ko: str,
    name_en: str,
    roles: str,
    assets: str,
    states: str,
    source_tags: str,
) -> FeatureRow:
    if classification not in {"S", "C"}:
        raise V19CatalogValidationError(f"{key}: classification must be S or C")
    return FeatureRow(
        key=key,
        classification=classification,
        name_ko=name_ko,
        name_en=name_en,
        roles=_terms(roles),
        assets=_terms(assets),
        states=_terms(states),
        source_tags=_terms(source_tags),
    )


def D(
    domain: str,
    root_ko: str,
    root_en: str,
    role_ko: str,
    jurisdiction: str,
    boundary: str,
    avoid_root: str,
    collision_terms: str,
    nearest_existing_functions: str,
    roles: str,
    assets: str,
    states: str,
    rows: tuple[FeatureRow, ...],
) -> DomainSpec:
    features = tuple(
        ReviewedFeature(
            key=row.key,
            classification=row.classification,
            name_ko=row.name_ko,
            name_en=row.name_en,
            goal_ko=f"{root_ko}에서 {row.name_ko} 목적지로 안내해 줘",
            goal_en=f"Guide me to {row.name_en.lower()} within {root_en.lower()}",
            purpose_ko=(
                f"{row.name_ko}의 권한 역할·정확한 자산·현재 상태·제공자·관할을 "
                "확인하고 사용자의 최종 동작 전에 중단"
            ),
            purpose_en=(
                f"Verify role, exact asset, current state, provider, and jurisdiction for "
                f"{row.name_en.lower()}, then stop before the user's final action"
            ),
            roles=row.roles,
            assets=row.assets,
            states=row.states,
            jurisdiction_guard=jurisdiction,
            safety_boundary=(
                f"{row.name_en}: {boundary}; do not infer eligibility, identity, facts, "
                "advice, or authority; stop before any final disclosure, submission, "
                "payment, certification, cancellation, selection, or state change"
            ),
            source_tags=row.source_tags,
        )
        for row in rows
    )
    return DomainSpec(
        domain=domain,
        root_ko=root_ko,
        root_en=root_en,
        role_ko=role_ko,
        jurisdiction=jurisdiction,
        boundary=boundary,
        avoid_root=avoid_root,
        collision_terms=_terms(collision_terms),
        nearest_existing_functions=_terms(nearest_existing_functions),
        roles=_terms(roles),
        assets=_terms(assets),
        states=_terms(states),
        features=features,
    )


# The exact nine-domain/114-terminal research scope.  Every row retains a
# specific actor, governed asset, lifecycle state, provider, and jurisdiction.
REVIEWED_DOMAINS: tuple[DomainSpec, ...] = (
    D(
        "voter_registration_ballot_services",
        "유권자 등록 및 투표 지원 서비스",
        "Citizen voter registration and ballot services",
        "유권자 또는 예비 유권자",
        "identified election authority, election, voter jurisdiction, and citizen-facing service lane",
        "the actor is the individual voter; exclude election-worker administration and ballot casting",
        "election_administration.hub",
        "유권자 등록|투표소|우편투표|투표용지 치유|registration|polling place|mail ballot|ballot cure",
        "election_administration.voter_registration_record|election_administration.voter_registration_update|election_administration.ballot_style_review|election_administration.absentee_request_queue|election_administration.absentee_ballot_issue|election_administration.polling_place_open",
        "eligible voter|prospective voter|authorized voter with an accessibility need",
        "personal voter registration record|polling assignment|mail-ballot request|ballot-cure request|voting accommodation request",
        "information available|application ready|registered|update pending|cancellation pending|assigned|requested|mailed|cure required|accommodation pending",
        (
            R("registration_eligibility_review", "S", "유권자 등록 자격 정보 검토", "Voter registration eligibility information", "prospective voter", "personal voter-registration eligibility information", "criteria available|jurisdiction unresolved", "register|guide|faq"),
            R("registration_apply", "C", "유권자 등록 신청", "Voter registration application", "prospective voter", "personal voter-registration application", "application ready|awaiting applicant confirmation", "register|form"),
            R("registration_status", "S", "유권자 등록 상태 조회", "Personal voter registration status", "eligible voter", "personal voter registration record", "registered|pending|not found", "guide|state|faq"),
            R("registration_update", "C", "유권자 등록 정보 변경", "Personal voter registration update", "registered voter", "personal voter registration record", "registered|change prepared|awaiting voter confirmation", "register|state|form"),
            R("registration_cancel", "C", "유권자 등록 취소", "Personal voter registration cancellation", "registered voter", "personal voter registration record", "registered|cancellation prepared|awaiting voter confirmation", "state|faq"),
            R("polling_place_lookup", "S", "유권자 투표소 조회", "Voter polling-place lookup", "eligible voter", "personal polling assignment", "assigned|location changed|not yet assigned", "guide|state|faq"),
            R("voter_id_requirements", "S", "투표자 신분증 요건 확인", "Voter identification requirements", "eligible voter", "voter identification requirement for one election", "requirements published|jurisdiction unresolved", "guide|state|faq"),
            R("mail_ballot_request", "C", "유권자 우편투표용지 요청", "Voter mail-ballot request", "eligible voter", "personal mail-ballot request", "eligible request lane|request prepared|awaiting voter confirmation", "state|faq|form"),
            R("mail_ballot_status", "S", "유권자 우편투표용지 상태", "Personal mail-ballot status", "eligible voter", "personal mail-ballot request and issuance record", "requested|issued|mailed|returned|status stale", "state|faq"),
            R("ballot_cure", "C", "유권자 투표용지 치유 요청", "Voter ballot-cure response", "voter named in a cure notice", "personal ballot-cure notice and response", "cure required|evidence prepared|awaiting voter confirmation", "state|faq"),
            R("early_voting_lookup", "S", "유권자 사전투표 장소 및 기간 조회", "Voter early-voting location and period", "eligible voter", "early-voting assignment and schedule", "published|changed|unavailable", "guide|state|faq"),
            R("accessibility_accommodation", "C", "유권자 접근성 편의 요청", "Voter accessibility accommodation request", "voter with an accessibility need", "personal voting accommodation request", "request lane available|request prepared|awaiting voter confirmation", "state|faq"),
        ),
    ),
    D(
        "vital_records_certificate_services",
        "출생·사망·혼인 기록 증명 서비스",
        "Vital-record certificate services",
        "기록 당사자·가족 또는 법적 권한 보유 요청자",
        "named issuing authority, record jurisdiction, record type, subject relationship, and requester-authority lane",
        "the asset is one real civil-status record; exclude generic certificate issue and any invented requester authority",
        "government.hub",
        "출생증명|사망증명|혼인증명|기록 정정|birth record|death record|marriage record|amendment",
        "government.certificate_search|government.certificate_issue|government.certificate_wallet",
        "record subject|parent of record subject|spouse|next of kin|legally authorized requester",
        "birth record|death record|marriage record|vital-record copy order|record amendment evidence|authentication handoff",
        "authority identified|requester review|order prepared|in delivery|correction prepared|amendment prepared|authentication ready",
        (
            R("issuing_authority_lookup", "S", "출생·사망·혼인 기록 발급기관 조회", "Vital-record issuing-authority lookup", "record subject|legally authorized requester", "issuing-authority directory for a specific vital record", "authority unknown|authority identified", "directory|all"),
            R("authorized_requester_review", "S", "출생·사망·혼인 기록 요청 권한 검토", "Vital-record requester-authority review", "record subject|parent|spouse|next of kin|legally authorized requester", "requester-authority rules for a specific vital record", "relationship unverified|requirements available", "directory|birth|correction|all"),
            R("record_copy_order", "C", "출생·사망·혼인 기록 증명서 사본 주문", "Vital-record certificate copy order", "legally authorized requester", "specific vital-record copy order", "record selected|delivery unresolved|awaiting requester confirmation", "directory|birth|all"),
            R("delivery_method", "C", "출생·사망·혼인 기록 증명서 수령 방식 선택", "Vital-record certificate delivery selection", "legally authorized requester", "delivery method for one vital-record order", "options available|method selected|awaiting requester confirmation", "directory|birth|all"),
            R("order_status", "S", "출생·사망·혼인 기록 증명서 주문 상태", "Vital-record certificate order status", "legally authorized requester", "specific vital-record copy order", "received|processing|mailed|held", "directory|all"),
            R("birth_record_correction", "C", "출생기록 정정 요청", "Birth-record correction request", "record subject|parent|legally authorized requester", "specific birth-record correction case", "error identified|evidence prepared|awaiting requester confirmation", "birth|correction|all"),
            R("death_record_correction", "C", "사망기록 정정 요청", "Death-record correction request", "next of kin|legally authorized requester", "specific death-record correction case", "error identified|evidence prepared|awaiting requester confirmation", "death|correction|all"),
            R("marriage_record_correction", "C", "혼인기록 정정 요청", "Marriage-record correction request", "spouse|legally authorized requester", "specific marriage-record correction case", "error identified|evidence prepared|awaiting requester confirmation", "marriage|correction|all"),
            R("birth_record_amendment", "C", "출생기록 개정 신청", "Birth-record amendment application", "record subject|parent|legally authorized requester", "specific birth-record amendment case", "amendment basis reviewed|evidence prepared|awaiting requester confirmation", "birth|correction|all"),
            R("certificate_authentication_handoff", "C", "출생·사망·혼인 기록 증명서 인증 절차 인계", "Vital-record certificate authentication handoff", "legally authorized requester", "issued vital-record certificate authentication request", "certificate issued|authority identified|handoff ready", "directory|all"),
        ),
    ),
    D(
        "nutrition_assistance_case_services",
        "영양지원 신청자 사례 서비스",
        "Nutrition-assistance case services",
        "가구 신청자·수급자·부모·보호자 또는 WIC 참여자",
        "named SNAP/WIC-equivalent program, applicant household, responsible agency, provider, and program jurisdiction",
        "the actor is the applicant or participant; never cross into caseworker eligibility decisions or benefit scheduling",
        "government.hub",
        "영양지원|식품지원|신청 상태|면담|재인증|nutrition assistance|food benefit|interview|recertification",
        "government.benefits|social_services_casework.eligibility_application_review|social_services_casework.benefit_eligibility_decision|social_services_casework.benefit_schedule_disbursement",
        "household applicant|nutrition-benefit recipient|parent|guardian|WIC participant",
        "named nutrition-assistance application|applicant interview|verification task|eligibility notice|benefit account|EBT card|recertification|hearing request|WIC appointment",
        "information available|agency identified|application started|interview due|verification due|notice issued|active benefit|change due|recertification due|hearing available",
        (
            R("program_eligibility_review", "S", "영양지원 프로그램 자격 정보 검토", "Nutrition-program eligibility information", "household applicant|WIC participant", "named nutrition-program eligibility information", "criteria available|household answers unresolved", "eligibility|snap|wic|all"),
            R("state_agency_lookup", "S", "영양지원 담당기관 조회", "Nutrition-assistance agency lookup", "household applicant|recipient", "responsible nutrition-program agency directory", "agency unknown|agency identified", "agency|snap|wic|all"),
            R("application_start", "C", "영양지원 신청 시작", "Nutrition-assistance application start", "household applicant", "named household nutrition-assistance application", "not started|application ready|awaiting applicant confirmation", "application|snap|wic|all"),
            R("application_status", "S", "영양지원 신청 상태 조회", "Nutrition-assistance application status", "household applicant", "named household nutrition-assistance application", "received|processing|interview due|verification due|decided", "application|snap|all"),
            R("interview_schedule", "C", "영양지원 신청 면담 예약", "Nutrition-assistance interview scheduling", "household applicant", "applicant nutrition-assistance interview", "interview required|slot selected|awaiting applicant confirmation", "interview|snap|all"),
            R("verification_upload", "C", "영양지원 확인자료 제출", "Nutrition-assistance verification upload", "household applicant|guardian", "verification task for a named nutrition case", "evidence requested|files selected|awaiting applicant confirmation", "application|snap|all"),
            R("eligibility_notice", "S", "영양지원 자격 통지 조회", "Nutrition-assistance eligibility notice", "household applicant|recipient", "official eligibility notice for a named nutrition case", "notice issued|unread|appeal window open", "eligibility|snap|all"),
            R("benefit_balance", "S", "영양지원 급여 잔액 조회", "Nutrition-benefit account balance", "nutrition-benefit recipient|WIC participant", "personal nutrition-benefit account", "active|balance available|data stale", "snap|wic|benefit|all"),
            R("ebt_card_replace", "C", "영양지원 EBT 카드 교체 요청", "Nutrition-benefit EBT card replacement", "nutrition-benefit recipient", "personal EBT card replacement request", "card lost or damaged|request prepared|awaiting recipient confirmation", "snap|benefit|all"),
            R("change_report", "C", "영양지원 가구 변경 보고", "Nutrition-assistance household change report", "household applicant|recipient", "household change report for a named nutrition case", "reportable change selected|facts unresolved|awaiting recipient confirmation", "snap|application|all"),
            R("recertification", "C", "영양지원 재인증 제출", "Nutrition-assistance recertification", "nutrition-benefit recipient", "named nutrition-case recertification", "renewal due|answers reviewed|awaiting recipient certification", "snap|application|all"),
            R("fair_hearing_request", "C", "영양지원 공정심리 요청", "Nutrition-assistance fair-hearing request", "household applicant|recipient", "hearing request tied to one nutrition notice", "notice issued|hearing window open|awaiting requester confirmation", "eligibility|snap|all"),
            R("wic_appointment", "C", "WIC 참여자 방문 예약", "WIC participant appointment", "WIC participant|parent|guardian", "WIC participant appointment", "appointment required|slot selected|awaiting participant confirmation", "wic|agency|all"),
        ),
    ),
    D(
        "court_litigant_self_service",
        "본인소송 당사자 법원 서비스",
        "Self-represented court litigant services",
        "변호사 없이 본인 사건을 수행하는 명시된 당사자",
        "named self-represented party, case or filing packet, court, case type, filing state, and jurisdiction",
        "the actor is a named self-represented party; exclude attorney practice, clerk administration, and legal strategy",
        "court_clerk_case_admin.hub",
        "본인소송|법원 서류|사건 기록|송달|기한|self represented|court filing|docket|service|deadline",
        "legal_practice_ops.court_filing_prepare|legal_practice_ops.court_filing_submit|court_clerk_case_admin.case_open|court_clerk_case_admin.filing_docket_entry|court_clerk_case_admin.fee_waiver_route|court_clerk_case_admin.summons_issue|court_clerk_case_admin.docket_sheet_view|court_clerk_case_admin.fee_payment_status|court_clerk_case_admin.service_notice_status|court_clerk_case_admin.calendar_deadline_view",
        "self-represented claimant|self-represented petitioner|self-represented defendant|self-represented respondent|named case party",
        "party case|party filing packet|fee-waiver request|service task|proof of service|case docket|court deadline|party response|court order",
        "triage needed|forms available|draft|ready to file|submitted|service due|docket available|deadline published|response due|order issued",
        (
            R("case_type_triage", "S", "본인소송 사건유형 안내", "Self-represented case-type triage", "self-represented prospective party", "case-type information for a prospective party matter", "case type unresolved|information available", "selfhelp|file|public|all"),
            R("court_jurisdiction_lookup", "S", "본인소송 관할 법원 조회", "Self-represented court-jurisdiction lookup", "self-represented party", "court and jurisdiction directory for a party matter", "court unresolved|court identified", "selfhelp|file|public|all"),
            R("form_packet", "S", "본인소송 서식 묶음 조회", "Self-represented court form packet", "self-represented party", "court-approved form packet for one case type", "packet available|version current|jurisdiction confirmed", "selfhelp|file|korea|all"),
            R("filing_prepare", "C", "본인소송 제출서류 준비", "Self-represented filing preparation", "self-represented party", "party-owned filing draft for one court case", "draft|validation pending|ready for party review", "file|korea|all"),
            R("filing_submit", "C", "본인소송 서류 제출", "Self-represented court filing submission", "self-represented party", "reviewed party filing for one court case", "ready to file|fee unresolved|awaiting party confirmation", "file|korea|all"),
            R("filing_status", "S", "본인소송 제출 상태 조회", "Self-represented filing status", "self-represented party", "party filing receipt and status", "received|rejected|accepted|docketed", "file|pacer|korea|all"),
            R("fee_waiver_request", "C", "본인소송 수수료 면제 요청", "Self-represented fee-waiver request", "self-represented party", "party fee-waiver request for one court case", "requirements reviewed|request prepared|awaiting party confirmation", "waiver|selfhelp|all"),
            R("service_instructions", "S", "본인소송 송달 안내", "Self-represented service instructions", "self-represented party", "service instructions for a named party filing", "service required|method jurisdiction-specific|not completed", "service|selfhelp|all"),
            R("proof_of_service_file", "C", "본인소송 송달증명 제출", "Self-represented proof-of-service filing", "self-represented party", "proof-of-service filing for a named case and recipient", "service asserted by user|proof prepared|awaiting party confirmation", "service|file|all"),
            R("case_docket_view", "S", "본인소송 사건기록 조회", "Self-represented case docket view", "named self-represented case party", "party-accessible docket for one case", "case found|entries available|access limited", "pacer|public|korea|all"),
            R("hearing_deadline_view", "S", "본인소송 심리 및 기한 조회", "Self-represented hearing and deadline view", "named self-represented case party", "court-issued hearing and deadline record", "scheduled|continued|deadline published|changed", "pacer|public|korea|all"),
            R("response_prepare", "C", "본인소송 답변서 준비", "Self-represented response preparation", "self-represented defendant|respondent", "party-owned response draft for one case", "response due|draft|ready for party review", "selfhelp|file|korea|all"),
            R("response_submit", "C", "본인소송 답변서 제출", "Self-represented response submission", "self-represented defendant|respondent", "reviewed party response for one case", "ready to file|deadline unresolved|awaiting party confirmation", "file|korea|all"),
            R("order_download", "S", "본인소송 법원명령 내려받기", "Self-represented court-order download", "named self-represented case party", "issued court order for one party case", "issued|available|sealed or restricted", "pacer|public|korea|all"),
        ),
    ),
    D(
        "jury_summons_response_services",
        "배심원 소환 응답 서비스",
        "Jury-summons response services",
        "배심원 소환장을 받은 사람 또는 진위를 확인하는 수령인",
        "named summons recipient, issuing court, summons identifier, reporting state, court district, and jurisdiction",
        "the actor is the summoned person; exclude jury-pool administration, juror selection, and request decisions",
        "court_clerk_case_admin.hub",
        "배심원 소환|자격 설문|출석|연기|면제|jury summons|questionnaire|reporting|postponement|excuse",
        "court_clerk_case_admin.summons_issue|election_administration.voter_registration_record",
        "jury-summons recipient|prospective juror verifying a summons|summoned juror",
        "jury summons|qualification questionnaire|reporting instruction|postponement request|excusal request|accommodation request|attendance record|juror payment",
        "authenticity unresolved|questionnaire due|reporting due|request available|attendance pending|service complete|payment pending",
        (
            R("summons_authenticity_check", "S", "배심원 소환장 진위 확인", "Jury-summons authenticity check", "jury-summons recipient", "personal jury summons and issuing-court identity", "unverified|official contact confirmed|possible scam", "service|summoned|forms|korea|all"),
            R("qualification_questionnaire", "C", "배심원 자격 설문 제출", "Juror qualification questionnaire", "jury-summons recipient", "personal juror qualification questionnaire", "due|answers incomplete|awaiting recipient certification", "qualifications|forms|korea|all"),
            R("reporting_status", "S", "배심원 출석 상태 조회", "Juror reporting status", "summoned juror", "personal jury reporting-status record", "must report|stand by|excused by court|service complete", "summoned|service|korea|all"),
            R("reporting_instructions", "S", "배심원 출석 안내 조회", "Juror reporting instructions", "summoned juror", "court-issued jury reporting instructions", "published|changed|weather notice|call-in required", "summoned|service|korea|all"),
            R("postponement_request", "C", "배심원 출석 연기 요청", "Jury-service postponement request", "summoned juror", "personal jury-service postponement request", "request available|date selected|awaiting juror confirmation", "qualifications|summoned|forms|korea|all"),
            R("excusal_request", "C", "배심원 소집 면제 요청", "Jury-service excusal request", "summoned juror", "personal jury-service excusal request", "request available|basis entered by juror|awaiting confirmation", "qualifications|summoned|forms|korea|all"),
            R("accommodation_request", "C", "배심원 편의지원 요청", "Juror accommodation request", "summoned juror with an accommodation need", "personal jury-service accommodation request", "request lane available|need entered by juror|awaiting confirmation", "service|summoned|korea|all"),
            R("attendance_checkin", "C", "배심원 출석 확인", "Juror attendance check-in", "summoned juror", "personal jury attendance check-in", "reporting window open|location verified|awaiting juror confirmation", "service|summoned|korea|all"),
            R("service_completion_status", "S", "배심원 복무 완료 상태", "Jury-service completion status", "summoned juror", "personal jury-service completion record", "serving|released|completed|not recorded", "service|summoned|korea|all"),
            R("payment_status", "S", "배심원 수당 지급 상태", "Juror payment status", "summoned juror", "personal juror payment record", "calculated|issued|delayed|returned", "pay|service|korea|all"),
        ),
    ),
    D(
        "consumer_postal_mail_services",
        "소비자 우편물 수령 서비스",
        "Consumer postal-mail services",
        "주거지 우편물 수령인·수취인 또는 세대주",
        "named postal operator, residential addressee or householder, service address, postal-mail asset, and address jurisdiction",
        "the asset is residential postal mail; exclude postal staff operations and parcel-courier shipment controls",
        "postal_network_operations.hub",
        "우편물 보관|주소 이전|우편물 전달|재배달|분실우편|hold mail|change of address|forwarding|redelivery|missing mail",
        "postal_network_operations.hold_mail_activate|postal_network_operations.forwarding_order_apply|postal_network_operations.mailpiece_tracking|postal_network_operations.delivery_exception_queue|postal_network_operations.postal_claim_adjudicate|parcel_courier.hold|parcel_courier.reroute|parcel_courier.reschedule|parcel_courier.missing_claim",
        "residential recipient|postal addressee|verified householder",
        "service address|hold-mail request|change-of-address order|forwarding option|incoming-mail preview|redelivery instruction|missing-mail search|mail-theft report",
        "address eligible|request prepared|active|modification pending|forwarding available|mail preview available|redelivery available|search open|report prepared",
        (
            R("address_eligibility", "S", "우편 서비스 주소 자격 확인", "Postal-service address eligibility", "residential recipient|verified householder", "residential postal-service address", "eligible|ineligible|address unresolved", "coa|hold|forward|all"),
            R("hold_mail_request", "C", "우편물 보관 요청", "Residential hold-mail request", "verified householder", "residential hold-mail request", "dates selected|identity pending|awaiting householder confirmation", "hold|all"),
            R("hold_mail_status", "S", "우편물 보관 상태 조회", "Residential hold-mail status", "verified householder", "active residential hold-mail order", "scheduled|active|completed|not found", "hold|all"),
            R("hold_mail_modify_cancel", "C", "우편물 보관 변경 또는 취소", "Residential hold-mail modification or cancellation", "verified householder", "active residential hold-mail order", "active|change prepared|cancellation prepared|awaiting confirmation", "hold|all"),
            R("change_of_address_request", "C", "우편 주소 이전 요청", "Postal change-of-address request", "postal addressee|verified householder", "personal change-of-address order", "move type selected|addresses entered|awaiting requester confirmation", "coa|forward|all"),
            R("change_of_address_status", "S", "우편 주소 이전 상태", "Postal change-of-address status", "postal addressee|verified householder", "personal change-of-address order", "received|processing|active|expired|not found", "coa|forward|all"),
            R("change_of_address_modify_cancel", "C", "우편 주소 이전 변경 또는 취소", "Postal change-of-address modification or cancellation", "postal addressee|verified householder", "active change-of-address order", "active|change prepared|cancellation prepared|awaiting confirmation", "coa|forward|all"),
            R("forwarding_option_compare", "S", "우편물 전달 방식 비교", "Postal-mail forwarding option comparison", "postal addressee|verified householder", "postal forwarding option set for one address", "options available|duration and fee published", "forward|coa|all"),
            R("incoming_mail_preview", "S", "도착 예정 우편물 미리보기", "Incoming postal-mail preview", "verified residential recipient", "incoming postal-mail preview for one verified address", "preview available|image unavailable|delivery pending", "all"),
            R("redelivery_request", "C", "우편물 재배달 요청", "Postal-mail redelivery request", "postal addressee", "eligible postal-mail redelivery item", "notice found|date selected|awaiting addressee confirmation", "redelivery|all"),
            R("delivery_instruction_request", "C", "우편물 배달 지시 요청", "Postal-mail delivery-instruction request", "postal addressee|verified householder", "delivery instruction for one eligible mail item", "item eligible|instruction selected|awaiting confirmation", "delivery|all"),
            R("missing_mail_search", "C", "분실 우편물 찾기 요청", "Missing postal-mail search request", "postal addressee|residential recipient", "missing postal-mail search case", "delivery overdue|item facts entered|awaiting requester confirmation", "theft|all"),
            R("mail_theft_report", "C", "우편물 도난 신고", "Postal-mail theft report", "postal addressee|residential recipient", "postal-mail theft report", "suspected theft|facts entered by user|awaiting reporter confirmation", "theft|all"),
        ),
    ),
    D(
        "public_health_coverage_case_services",
        "공공 건강보장 신청자 사례 서비스",
        "Public health-coverage case services",
        "공공 건강보장 신청자·수급자·부모·보호자 또는 가구 대리인",
        "named Medicaid/CHIP-equivalent program, applicant household, responsible state agency, managed plan, and program jurisdiction",
        "the actor is the applicant or beneficiary; exclude provider claims, caseworker adjudication, and generic commercial insurance",
        "health_insurance.civil_service",
        "공공 건강보장|메디케이드|아동건강보험|갱신|공정심리|public health coverage|Medicaid|CHIP|renewal|hearing",
        "health_insurance.civil_service|health_insurance.eligibility|health_insurance.screening|health_insurance.refund|government.benefits|social_services_casework.eligibility_application_review|social_services_casework.benefit_eligibility_decision",
        "public-coverage applicant|public-coverage beneficiary|parent|guardian|authorized household representative",
        "public-coverage application|verification task|eligibility notice|managed-plan selection|coverage period|member card|household change|renewal|hearing request|coverage transition",
        "screening information|agency identified|application started|verification due|notice issued|selection available|coverage active|renewal due|hearing available|transition available",
        (
            R("program_eligibility_screen", "S", "공공 건강보장 자격 정보 확인", "Public health-coverage eligibility information", "public-coverage applicant|parent|guardian", "named public-coverage screening information", "criteria available|household facts unresolved", "eligibility|medicaid|marketplace|all"),
            R("state_agency_lookup", "S", "공공 건강보장 담당기관 조회", "Public health-coverage agency lookup", "public-coverage applicant|beneficiary", "responsible public-coverage agency directory", "agency unknown|agency identified", "eligibility|medicaid|all"),
            R("application_start", "C", "공공 건강보장 신청 시작", "Public health-coverage application start", "public-coverage applicant|authorized household representative", "named household public-coverage application", "not started|application ready|awaiting applicant confirmation", "eligibility|marketplace|all"),
            R("application_status", "S", "공공 건강보장 신청 상태", "Public health-coverage application status", "public-coverage applicant", "named household public-coverage application", "received|processing|verification due|decided", "eligibility|medicaid|all"),
            R("verification_submit", "C", "공공 건강보장 확인자료 제출", "Public health-coverage verification submission", "public-coverage applicant|authorized household representative", "verification task for one public-coverage application", "evidence requested|files selected|awaiting applicant confirmation", "eligibility|renewal|all"),
            R("eligibility_notice", "S", "공공 건강보장 자격 통지", "Public health-coverage eligibility notice", "public-coverage applicant|beneficiary", "official eligibility notice for one public-coverage case", "notice issued|unread|hearing window open", "eligibility|medicaid|all"),
            R("managed_plan_select", "C", "공공 건강보장 관리형 플랜 선택", "Public health-coverage managed-plan selection", "public-coverage beneficiary|authorized household representative", "managed-plan choice for an eligible public-coverage member", "selection available|choice made by user|awaiting confirmation", "coverage|all"),
            R("coverage_effective_status", "S", "공공 건강보장 적용 상태", "Public health-coverage effective status", "public-coverage beneficiary", "personal public-coverage period", "approved|effective|future start|ended|data stale", "coverage|renewal|all"),
            R("member_card_status", "S", "공공 건강보장 회원카드 상태", "Public health-coverage member-card status", "public-coverage beneficiary|parent|guardian", "personal public-coverage member card", "ordered|mailed|active|replacement needed", "coverage|all"),
            R("household_change_report", "C", "공공 건강보장 가구 변경 보고", "Public health-coverage household change report", "public-coverage applicant|beneficiary|authorized household representative", "household change report for one public-coverage case", "change selected|facts unresolved|awaiting reporter confirmation", "eligibility|renewal|all"),
            R("renewal_due", "S", "공공 건강보장 갱신 기한 조회", "Public health-coverage renewal due status", "public-coverage beneficiary", "renewal record for one public-coverage case", "not due|due soon|overdue|automatic review", "renewal|all"),
            R("renewal_submit", "C", "공공 건강보장 갱신 제출", "Public health-coverage renewal submission", "public-coverage beneficiary|authorized household representative", "renewal response for one public-coverage case", "renewal due|answers reviewed|awaiting beneficiary certification", "renewal|all"),
            R("fair_hearing_request", "C", "공공 건강보장 공정심리 요청", "Public health-coverage fair-hearing request", "public-coverage applicant|beneficiary", "hearing request tied to one public-coverage notice", "notice issued|hearing window open|awaiting requester confirmation", "eligibility|renewal|all"),
            R("coverage_transition", "C", "공공 건강보장 전환 절차 인계", "Public health-coverage transition handoff", "public-coverage applicant|beneficiary", "coverage transition from one named public program", "transition notice issued|destination identified|handoff ready", "marketplace|coverage|all"),
        ),
    ),
    D(
        "retirement_plan_participant_services",
        "퇴직연금 가입자 요청 서비스",
        "Retirement-plan participant services",
        "본인 계좌를 다루는 가입자·전 직원·퇴직자·수익자 또는 대체수취인",
        "named retirement plan, participant-owned account, plan provider, request type, governing plan terms, and jurisdiction",
        "the actor owns the participant request; exclude plan-administrator recordkeeping, eligibility decisions, adjudication, and release",
        "pension_plan_administration.hub",
        "퇴직연금 가입자|기여율|투자배분|수익자|롤오버|대출|인출|retirement participant|contribution|allocation|beneficiary|rollover|loan|distribution",
        "pension_plan_administration.plan_document_version|pension_plan_administration.participant_service_history|pension_plan_administration.eligibility_vesting_status|pension_plan_administration.accrued_benefit_account_view|pension_plan_administration.contribution_allocation_status|pension_plan_administration.beneficiary_record_view|pension_plan_administration.distribution_claim_status|pension_plan_administration.participant_eligibility_determine|pension_plan_administration.benefit_claim_decide|pension_plan_administration.claim_appeal_decide|hr_payroll.benefits_enrollment",
        "retirement-plan participant|former employee participant|retiree|beneficiary|alternate payee",
        "participant contribution election|investment allocation|beneficiary designation|rollover request|participant loan|hardship withdrawal|retirement distribution|participant claim|appeal|payment account|tax withholding",
        "terms available|election editable|request prepared|estimate available|eligibility information|claim ready|appeal available|payment setting editable|withholding editable",
        (
            R("contribution_rate_election", "C", "퇴직연금 가입자 기여율 선택", "Participant contribution-rate election", "retirement-plan participant", "participant contribution-rate election", "editable|rate selected by participant|awaiting confirmation", "life|erisa|korea|all"),
            R("investment_allocation_change", "C", "퇴직연금 가입자 투자배분 변경", "Participant investment-allocation change", "retirement-plan participant", "participant investment-allocation election", "editable|allocation chosen by participant|awaiting confirmation", "life|erisa|korea|all"),
            R("beneficiary_change_submit", "C", "퇴직연금 수익자 변경 제출", "Retirement-plan beneficiary change", "retirement-plan participant", "participant beneficiary designation", "editable|designation entered by participant|awaiting confirmation", "beneficiary|life|korea|all"),
            R("rollover_option_compare", "S", "퇴직연금 롤오버 선택지 비교", "Retirement-plan rollover option comparison", "retirement-plan participant|former employee participant", "participant rollover option set", "options published|tax treatment unresolved|advice excluded", "rollover|distribution|erisa|korea|all"),
            R("rollover_initiate", "C", "퇴직연금 롤오버 시작", "Retirement-plan rollover initiation", "retirement-plan participant|former employee participant", "participant-originated rollover request", "destination account identified|request prepared|awaiting confirmation", "rollover|distribution|korea|all"),
            R("loan_estimate", "S", "퇴직연금 가입자 대출 예상 조회", "Retirement-plan participant loan estimate", "retirement-plan participant", "participant loan estimate", "indicative|plan terms applied|not an approval", "hardship|erisa|korea|all"),
            R("loan_application_submit", "C", "퇴직연금 가입자 대출 신청", "Retirement-plan participant loan application", "retirement-plan participant", "participant-originated plan-loan application", "estimate reviewed|application prepared|awaiting confirmation", "hardship|erisa|korea|all"),
            R("hardship_eligibility_review", "S", "퇴직연금 긴급인출 자격 정보 검토", "Retirement-plan hardship eligibility information", "retirement-plan participant", "plan hardship-withdrawal criteria", "criteria available|participant facts unresolved|not a determination", "hardship|erisa|korea|all"),
            R("hardship_withdrawal_apply", "C", "퇴직연금 긴급인출 신청", "Retirement-plan hardship-withdrawal application", "retirement-plan participant", "participant-originated hardship-withdrawal request", "basis entered by participant|request prepared|awaiting confirmation", "hardship|distribution|korea|all"),
            R("retirement_distribution_option", "S", "퇴직연금 급여수령 방식 검토", "Retirement distribution option review", "retirement-plan participant|retiree|beneficiary|alternate payee", "participant retirement-distribution option set", "options published|tax treatment unresolved|advice excluded", "distribution|rmd|claims|korea|all"),
            R("retirement_claim_submit", "C", "퇴직연금 급여청구 제출", "Retirement-plan participant claim submission", "retirement-plan participant|retiree|beneficiary|alternate payee", "participant-originated retirement claim", "claim prepared|documents selected|awaiting claimant confirmation", "claims|distribution|korea|all"),
            R("claim_appeal_submit", "C", "퇴직연금 청구 이의제기 제출", "Retirement-plan participant claim appeal", "retirement-plan participant|retiree|beneficiary|alternate payee", "participant-originated retirement claim appeal", "decision received|appeal prepared|awaiting claimant confirmation", "claims|erisa|korea|all"),
            R("payment_account_update", "C", "퇴직연금 지급계좌 변경", "Retirement-plan payment-account update", "retirement-plan participant|retiree|beneficiary|alternate payee", "participant retirement-payment account", "current account verified|new account entered|awaiting confirmation", "distribution|claims|korea|all"),
            R("tax_withholding_update", "C", "퇴직연금 원천징수 설정 변경", "Retirement-plan tax-withholding update", "retirement-plan participant|retiree|beneficiary|alternate payee", "participant retirement-payment tax-withholding election", "current election shown|choice made by participant|awaiting confirmation", "distribution|rmd|korea|all"),
        ),
    ),
    D(
        "consular_visa_application_services",
        "영사 비자 신청자 서비스",
        "Consular visa-application services",
        "외국인 비자 신청자 또는 권한 있는 신청 대리인",
        "named destination country, visa category, consular post, applicant-owned application, provider, and consular jurisdiction",
        "the asset is a consular visa application; exclude passports and domestic immigration-benefit petitions or case management",
        "government_digital.hub",
        "영사 비자|비자 신청서|영사관 면접|행정처리|여권 반환|consular visa|visa application|interview|administrative processing|passport return",
        "government_digital.immigration_case|government_digital.processing_times|government_digital.office_appointment|government_digital.form_filing|government_digital.fee_calculator|government_digital.passport_apply|government_digital.passport_renew|government_digital.passport_status|government_digital.passport_records",
        "foreign-national visa applicant|authorized visa-applicant representative",
        "consular visa category|consular post|visa application form instance|visa fee|visa interview|document checklist|administrative-processing record|passport return|refusal information",
        "category review|post identified|form started|application retrievable|ready to submit|fee due|wait time published|appointment available|documents due|submitted|administrative processing|passport return|refusal issued",
        (
            R("visa_category_review", "S", "영사 비자 유형 검토", "Consular visa-category review", "foreign-national visa applicant|authorized representative", "destination-country consular visa category", "categories published|applicant eligibility unresolved", "form|visitor|korea|all"),
            R("post_lookup", "S", "영사 비자 신청 공관 조회", "Consular visa-post lookup", "foreign-national visa applicant|authorized representative", "destination-country consular-post directory", "post unresolved|post identified|service limited", "visitor|wait|korea|all"),
            R("application_form_start", "C", "영사 비자 신청서 시작", "Consular visa application-form start", "foreign-national visa applicant|authorized representative", "applicant-owned consular visa form instance", "not started|category and post selected|awaiting applicant confirmation", "form|faq|korea|all"),
            R("application_retrieve", "S", "영사 비자 신청서 불러오기", "Consular visa application retrieval", "foreign-national visa applicant|authorized representative", "applicant-owned consular visa form instance", "saved|retrievable|not found|locked after submit", "form|faq|status|korea|all"),
            R("application_submit", "C", "영사 비자 신청서 제출", "Consular visa application submission", "foreign-national visa applicant|authorized representative", "reviewed applicant-owned consular visa application", "validation passed|signature due|awaiting applicant confirmation", "form|faq|korea|all"),
            R("fee_payment", "C", "영사 비자 수수료 납부", "Consular visa fee payment", "foreign-national visa applicant|authorized payer", "fee for one consular visa application", "fee due|amount and post confirmed|awaiting payer confirmation", "fees|visitor|korea|all"),
            R("interview_wait_time", "S", "영사 비자 면접 대기기간 조회", "Consular visa interview wait time", "foreign-national visa applicant|authorized representative", "consular-post interview wait-time information", "published|estimated|changed|category scoped", "wait|visitor|korea|all"),
            R("interview_schedule", "C", "영사 비자 면접 예약", "Consular visa interview scheduling", "foreign-national visa applicant|authorized representative", "interview appointment for one consular visa application", "appointment required|slot selected|awaiting applicant confirmation", "wait|visitor|korea|all"),
            R("interview_reschedule_cancel", "C", "영사 비자 면접 변경 또는 취소", "Consular visa interview reschedule or cancellation", "foreign-national visa applicant|authorized representative", "existing interview appointment for one consular visa application", "scheduled|change or cancellation prepared|awaiting confirmation", "wait|visitor|korea|all"),
            R("document_checklist", "S", "영사 비자 구비서류 목록", "Consular visa document checklist", "foreign-national visa applicant|authorized representative", "category-and-post-specific visa document checklist", "published|post-specific|documents incomplete", "form|visitor|korea|all"),
            R("application_status", "S", "영사 비자 신청 상태", "Consular visa application status", "foreign-national visa applicant|authorized representative", "submitted consular visa application", "received|interview pending|issued|refused|status stale", "status|processing|korea|all"),
            R("administrative_processing_status", "S", "영사 비자 행정처리 상태", "Consular visa administrative-processing status", "foreign-national visa applicant|authorized representative", "administrative-processing record for one consular visa application", "administrative processing|additional information requested|complete|no decision inferred", "processing|status|korea|all"),
            R("passport_return_status", "S", "영사 비자 신청 여권 반환 상태", "Consular visa passport-return status", "foreign-national visa applicant|authorized representative", "passport-return record tied to one consular visa application", "held by post|ready for pickup|couriered|returned", "status|processing|korea|all"),
            R("refusal_information", "S", "영사 비자 거절 안내 조회", "Consular visa refusal information", "foreign-national visa applicant|authorized representative", "official refusal-information record for one consular visa application", "refusal issued|reason category published|next step not selected", "processing|status|korea|all"),
        ),
    ),
)


REVIEWED_BY_DOMAIN = {domain.domain: domain for domain in REVIEWED_DOMAINS}
REVIEWED_FEATURE_BY_ID = {
    f"{domain.domain}.{feature.key}": feature
    for domain in REVIEWED_DOMAINS
    for feature in domain.features
}


KOREAN_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "voter_registration_ballot_services": _terms("중앙선거관리위원회|유권자 등록|투표소 찾기|우편투표 안내"),
    "vital_records_certificate_services": _terms("정부민원안내|출생 기록|사망 기록|혼인 기록"),
    "nutrition_assistance_case_services": _terms("보건복지부 영양지원|식품 지원|가구 신청|영양지원 사례"),
    "court_litigant_self_service": _terms("대한민국 법원 전자소송|본인소송|법원 서식|사건 기록"),
    "jury_summons_response_services": _terms("대한민국 법원 배심원|국민참여재판|배심원 소환|배심원 출석"),
    "consumer_postal_mail_services": _terms("우정사업본부|우편물 보관|주소 이전|우편물 재배달"),
    "public_health_coverage_case_services": _terms("국민건강보험공단|공공 건강보장|가구 자격|건강보장 갱신"),
    "retirement_plan_participant_services": _terms("국민연금공단|퇴직연금 가입자|연금 급여|연금 청구"),
    "consular_visa_application_services": _terms("대한민국 비자포털|재외공관 비자|비자 신청|영사 면접"),
}


REJECTED_DUPLICATE_FAMILIES: tuple[str, ...] = (
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


@dataclass(frozen=True)
class SourceSeed:
    source_id: str
    domain: str
    publisher: str
    title: str
    canonical_url: str
    jurisdiction: str
    lifecycle_tags: tuple[str, ...]


def _source_rows(
    domain: str,
    prefix: str,
    rows: tuple[tuple[str, str, str, str, str], ...],
) -> tuple[SourceSeed, ...]:
    return tuple(
        SourceSeed(
            source_id=f"v19_{prefix}_{index:02d}",
            domain=domain,
            publisher=publisher,
            title=title,
            canonical_url=url,
            jurisdiction=jurisdiction,
            lifecycle_tags=_terms(tags),
        )
        for index, (publisher, title, url, jurisdiction, tags) in enumerate(rows, start=1)
    )


SOURCE_SEEDS: tuple[SourceSeed, ...] = (
    *_source_rows(
        "voter_registration_ballot_services",
        "vote",
        (
            ("Vote.gov", "Register to vote", "https://vote.gov/register", "US", "register|state"),
            ("Vote.gov", "Guide to voting", "https://vote.gov/guide-to-voting", "US", "guide|state"),
            ("U.S. Election Assistance Commission", "Register and vote in your state", "https://www.eac.gov/voters/register-and-vote-in-your-state", "US", "register|state"),
            ("U.S. Election Assistance Commission", "National mail voter registration form", "https://www.eac.gov/voters/national-mail-voter-registration-form", "US", "form|register"),
            ("U.S. Election Assistance Commission", "National mail voter registration form FAQs", "https://www.eac.gov/voters/national-mail-voter-registration-form-faqs", "US", "form|register"),
            ("U.S. Election Assistance Commission", "Voter FAQs", "https://www.eac.gov/voters/voter-faqs", "US", "faq"),
            ("National Election Commission Korea", "유권자 선거정보 안내", "https://www.nec.go.kr/site/nec/ex/bbs/View.do?bcIdx=231068&cbIdx=1147", "KR", "all"),
        ),
    ),
    *_source_rows(
        "vital_records_certificate_services",
        "vital",
        (
            ("U.S. Centers for Disease Control and Prevention", "Where to write for vital records", "https://www.cdc.gov/nchs/w2w/index.htm", "US", "directory"),
            ("New York State Department of Health", "Vital records", "https://www.health.ny.gov/vital_records/", "US-NY", "all"),
            ("New York State Department of Health", "Birth certificates", "https://www.health.ny.gov/vital_records/birth.htm", "US-NY", "birth"),
            ("New York State Department of Health", "Vital-record amendments and corrections", "https://www.health.ny.gov/vital_records/amend_corr.htm", "US-NY", "correction"),
            ("New York State Department of Health", "Birth-record amendments", "https://www.health.ny.gov/vital_records/amend_birth.htm", "US-NY", "birth|correction"),
            ("New York State Department of Health", "Public instructions for death corrections", "https://www.health.ny.gov/vital_records/docs/public_instructions_for_death_corrections.pdf", "US-NY", "death|correction"),
            ("New York State Department of Health", "Public instructions for marriage corrections", "https://www.health.ny.gov/vital_records/docs/public_instructions_for_marriage_corrections.pdf", "US-NY", "marriage|correction"),
            ("Government24 Korea", "가족관계 기록 증명 민원 안내", "https://m.gov.kr/mw/AA020InfoCappView.do?CappBizCD=97400000004&HighCtgCD=A01008&tp_seq=", "KR", "all"),
        ),
    ),
    *_source_rows(
        "nutrition_assistance_case_services",
        "nutrition",
        (
            ("USDA Food and Nutrition Service", "SNAP recipient eligibility", "https://www.fns.usda.gov/snap/recipient/eligibility", "US", "eligibility|snap"),
            ("USA.gov", "Food assistance and SNAP", "https://www.usa.gov/food-stamps", "US", "snap|all"),
            ("USDA Food and Nutrition Service", "SNAP interview toolkit", "https://www.fns.usda.gov/snap/state/interview-toolkit/providing", "US", "interview|snap"),
            ("USDA Food and Nutrition Service", "WIC benefits", "https://www.fns.usda.gov/wic/benefits", "US", "wic|benefit"),
            ("USDA Food and Nutrition Service", "WIC frequently asked questions", "https://www.fns.usda.gov/wic/faqs", "US", "wic|eligibility"),
            ("USDA Food and Nutrition Service", "WIC program contacts", "https://www.fns.usda.gov/wic/program-contacts", "US", "wic|agency"),
            ("USDA Food and Nutrition Service", "WIC model online application", "https://www.fns.usda.gov/wic/application-toolkit/model-online-application", "US", "wic|application"),
            ("Ministry of Health and Welfare Korea", "영양지원 사업 안내", "https://www.mohw.go.kr/menu.es?mid=a10708010200", "KR", "all"),
        ),
    ),
    *_source_rows(
        "court_litigant_self_service",
        "litigant",
        (
            ("California Courts Self-Help Guide", "California court self-help", "https://selfhelp.courts.ca.gov/", "US-CA", "selfhelp|all"),
            ("California Courts Self-Help Guide", "File a small-claims case", "https://www.selfhelp.courts.ca.gov/small-claims/start-case/file", "US-CA", "file"),
            ("California Courts Self-Help Guide", "Court service basics", "https://selfhelp.courts.ca.gov/court-basics/service", "US-CA", "service"),
            ("California Courts Self-Help Guide", "Fee-waiver next steps", "https://selfhelp.courts.ca.gov/fee-waiver/if-fee-waiver-isnt-granted", "US-CA", "waiver"),
            ("Administrative Office of the U.S. Courts", "Find a case with PACER", "https://www.uscourts.gov/court-records/find-a-case-pacer", "US", "pacer"),
            ("PACER", "File a case", "https://pacer.uscourts.gov/file-case", "US", "file|pacer"),
            ("Supreme Court of Korea", "전자소송 사용자 설명서", "https://ecfs.scourt.go.kr/psp/help/ecfs_scourt_manual_v1.1.pdf", "KR", "korea|file|all"),
            ("Supreme Court of Korea", "국민을 위한 사법정보", "https://www.scourt.go.kr/judiciary/information/public/", "KR", "korea|public|all"),
        ),
    ),
    *_source_rows(
        "jury_summons_response_services",
        "jury",
        (
            ("Administrative Office of the U.S. Courts", "Jury service", "https://www.uscourts.gov/court-programs/jury-service", "US", "service|all"),
            ("Administrative Office of the U.S. Courts", "Summoned for federal jury service", "https://www.uscourts.gov/court-programs/jury-service/summoned-federal-jury-service", "US", "summoned"),
            ("Administrative Office of the U.S. Courts", "Juror selection process", "https://www.uscourts.gov/court-programs/jury-service/juror-selection-process", "US", "qualifications"),
            ("Administrative Office of the U.S. Courts", "Juror qualifications, exemptions, and excuses", "https://www.uscourts.gov/court-programs/jury-service/juror-qualifications-exemptions-and-excuses", "US", "qualifications"),
            ("Administrative Office of the U.S. Courts", "Juror pay", "https://www.uscourts.gov/court-programs/jury-service/juror-pay", "US", "pay"),
            ("Administrative Office of the U.S. Courts", "Types of juries", "https://www.uscourts.gov/court-programs/jury-service/types-juries", "US", "service"),
            ("Administrative Office of the U.S. Courts", "Jury forms", "https://www.uscourts.gov/forms-rules/forms/jury-forms", "US", "forms"),
            ("Supreme Court of Korea", "국민참여재판 배심원 안내", "https://www.scourt.go.kr/nm/min_9/min_9_8/index.html", "KR", "korea|all"),
            ("Supreme Court of Korea", "국민참여재판 절차 안내", "https://www.scourt.go.kr/nm/min_9/min_9_3/index.html", "KR", "korea|all"),
        ),
    ),
    *_source_rows(
        "consumer_postal_mail_services",
        "postal",
        (
            ("United States Postal Service", "Change of Address basics", "https://faq.usps.com/articles/Knowledge/Change-of-Address-The-Basics", "US", "coa"),
            ("United States Postal Service", "USPS Hold Mail basics", "https://faq.usps.com/articles/FAQ/USPS-Hold-Mail-The-Basics/1000", "US", "hold"),
            ("United States Postal Service", "Mail forwarding options", "https://faq.usps.com/articles/Knowledge/Mail-Forwarding-Options", "US", "forward"),
            ("United States Postal Service", "Redelivery basics", "https://faq.usps.com/articles/Knowledge/Redelivery-The-Basics", "US", "redelivery"),
            ("United States Postal Service", "USPS Delivery Instructions basics", "https://faq.usps.com/articles/Knowledge/USPS-Delivery-Instructions-The-Basics", "US", "delivery"),
            ("United States Postal Service", "Mail theft", "https://faq.usps.com/articles/Knowledge/Mail-Theft", "US", "theft"),
            ("Korea Post", "국내 통상우편 이용 안내", "https://kpds.koreapost.go.kr/site/kpost/download/%EA%B5%AD%EB%82%B4%ED%86%B5%EC%83%81_%EC%9A%B0%ED%8E%B8%EC%9A%94%EA%B8%88%EB%B0%8F%EC%9A%B0%ED%8E%B8%EC%9D%B4%EC%9A%A9%EC%97%90%EA%B4%80%ED%95%9C%EC%88%98%EC%88%98%EB%A3%8C.pdf", "KR", "all"),
        ),
    ),
    *_source_rows(
        "public_health_coverage_case_services",
        "coverage",
        (
            ("Centers for Medicare & Medicaid Services", "Eligibility, enrollment, and renewal resources", "https://www.medicaid.gov/resources-for-states/eligibility-enrollment-and-renewal-tools-and-resources", "US", "eligibility|renewal"),
            ("Centers for Medicare & Medicaid Services", "Medicaid eligibility policy", "https://www.medicaid.gov/medicaid/eligibility-policy", "US", "eligibility"),
            ("HealthCare.gov", "Getting Medicaid or CHIP", "https://www.healthcare.gov/medicaid-chip/getting-medicaid-chip/", "US", "eligibility|marketplace"),
            ("HealthCare.gov", "Transfer from Medicaid or CHIP to the Marketplace", "https://www.healthcare.gov/medicaid-chip/transfer-to-marketplace/", "US", "marketplace"),
            ("HealthCare.gov", "Medicaid to Marketplace transition", "https://www.healthcare.gov/medicaid-to-marketplace/", "US", "marketplace"),
            ("HealthCare.gov", "Using Medicaid or CHIP coverage", "https://www.healthcare.gov/medicaid-chip/using-medicaid-or-chip-coverage/", "US", "coverage"),
            ("Centers for Medicare & Medicaid Services", "Medicaid and CHIP renewal outreach resources", "https://www.medicaid.gov/medicaid/outreach-tools/medicaid-and-chip-renewals-outreach-and-educational-resources", "US", "renewal"),
            ("National Health Insurance Service Korea", "건강보험 제도 안내", "https://www.nhis.or.kr/static/html/wbdb/f/wbdbf0102.html", "KR", "all"),
        ),
    ),
    *_source_rows(
        "retirement_plan_participant_services",
        "retire",
        (
            ("Internal Revenue Service", "Rollovers of retirement-plan and IRA distributions", "https://www.irs.gov/retirement-plans/plan-participant-employee/rollovers-of-retirement-plan-and-ira-distributions", "US", "rollover"),
            ("Internal Revenue Service", "Life changes and retirement planning", "https://www.irs.gov/retirement-plans/plan-participant-employee/changes-in-your-life-may-affect-retirement-planning", "US", "life"),
            ("Internal Revenue Service", "Retirement topics: hardship distributions", "https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-hardship-distributions", "US", "hardship"),
            ("Internal Revenue Service", "Retirement topics: beneficiary", "https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-beneficiary", "US", "beneficiary"),
            ("Internal Revenue Service", "401(k) participant distribution rules", "https://www.irs.gov/retirement-plans/plan-participant-employee/401k-resource-guide-plan-participants-general-distribution-rules", "US", "distribution"),
            ("Internal Revenue Service", "Required minimum distributions", "https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-required-minimum-distributions-rmds", "US", "rmd|distribution"),
            ("U.S. Department of Labor", "Retirement plans and ERISA FAQs", "https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/resource-center/faqs/retirement-plans-and-erisa", "US", "erisa"),
            ("U.S. Department of Labor", "Filing retirement-benefit claims", "https://www.dol.gov/sites/dolgov/files/ebsa/about-ebsa/our-activities/resource-center/publications/retirement-benefits-filing-claims.pdf", "US", "claims"),
            ("National Pension Service Korea", "국민연금 급여 안내", "https://nps.or.kr/pnsinfo/ntpsklg/getOHAF0095M0.do", "KR", "korea|all"),
        ),
    ),
    *_source_rows(
        "consular_visa_application_services",
        "visa",
        (
            ("U.S. Department of State", "DS-160 online nonimmigrant visa application", "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application.html", "US", "form"),
            ("U.S. Department of State", "DS-160 FAQs", "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application/ds-160-faqs.html", "US", "form|faq"),
            ("U.S. Department of State", "Visitor visa", "https://travel.state.gov/content/travel/en/us-visas/tourism-visit/visitor.html", "US", "visitor"),
            ("U.S. Department of State", "Global visa wait times", "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/wait-times.html", "US", "wait"),
            ("U.S. Department of State", "Fees for visa services", "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/fees/fees-visa-services.html", "US", "fees"),
            ("U.S. Department of State", "Administrative processing information", "https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/administrative-processing-information.html", "US", "processing"),
            ("U.S. Department of State", "CEAC visa status check", "https://ceac.state.gov/ceacstattracker/status.aspx", "US", "status"),
            ("Korea Visa Portal", "대한민국 비자 안내", "https://visa.go.kr/openPage.do?MENU_ID=10105&lang=en", "KR", "korea|all"),
            ("Ministry of Foreign Affairs Korea", "재외공관 비자 신청 안내", "https://overseas.mofa.go.kr/cd-ko/brd/m_10659/view.do?seq=1270153", "KR", "korea|all"),
        ),
    ),
)


PUBLISHER_ALLOWLIST = frozenset(seed.publisher for seed in SOURCE_SEEDS)


def normalize_official_url(value: str) -> str:
    parts = urlsplit(value.strip())
    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    if scheme != "https" or not host:
        raise V19CatalogValidationError(f"invalid official source URL: {value}")
    port = parts.port
    netloc = host if port is None or port == 443 else f"{host}:{port}"
    path = posixpath.normpath(parts.path or "/")
    if not path.startswith("/"):
        path = f"/{path}"
    if parts.path.endswith("/") and not path.endswith("/"):
        path = f"{path}/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _source_digest(payload: Mapping[str, object]) -> str:
    return _digest(payload)


def _build_official_sources() -> tuple[
    dict[str, dict[str, object]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    sources: dict[str, dict[str, object]] = {}
    terminal_sources: dict[str, list[str]] = defaultdict(list)
    domain_sources: dict[str, list[str]] = defaultdict(list)
    for seed in SOURCE_SEEDS:
        domain = REVIEWED_BY_DOMAIN[seed.domain]
        terminal_ids = [
            f"{seed.domain}.{feature.key}"
            for feature in domain.features
            if "all" in seed.lifecycle_tags or set(seed.lifecycle_tags).intersection(feature.source_tags)
        ]
        if not terminal_ids:
            raise V19CatalogValidationError(f"{seed.source_id}: source has no terminal mapping")
        record: dict[str, object] = {
            "source_id": seed.source_id,
            "publisher": seed.publisher,
            "provider_scope": seed.publisher,
            "title": seed.title,
            "canonical_url": seed.canonical_url,
            "normalized_url": normalize_official_url(seed.canonical_url),
            "final_url": seed.canonical_url,
            "retrieved_at": RETRIEVED_AT,
            "collected_on": COLLECTED_ON,
            "evidence_level": "official_primary",
            "verification_status": "accepted",
            "verification_method": "direct official lifecycle URL opened and recorded in the SHA-pinned V19 research document",
            "http_status": 200,
            "verified_status": 200,
            "jurisdiction": seed.jurisdiction,
            "domains": [seed.domain],
            "lifecycle_tags": list(seed.lifecycle_tags),
            "terminal_ids": terminal_ids,
            "source_documents": [DESIGN_SOURCE_RELATIVE_PATH],
        }
        record["source_record_sha256"] = _source_digest(record)
        sources[seed.source_id] = record
        domain_sources[seed.domain].append(seed.source_id)
        for terminal_id in terminal_ids:
            terminal_sources[terminal_id].append(seed.source_id)
    return (
        sources,
        {key: _dedupe(values) for key, values in terminal_sources.items()},
        {key: _dedupe(values) for key, values in domain_sources.items()},
    )


OFFICIAL_SOURCES, DOMAIN_TERMINAL_SOURCE_IDS, DOMAIN_SOURCE_IDS = _build_official_sources()
OFFICIAL_SOURCES_SHA256 = _digest(OFFICIAL_SOURCES)
EXPECTED_OFFICIAL_SOURCES_SHA256 = "974591e7c12300b51a301572a8d2058b6809f40836df18ba87864bf6a60315ca"
EXPECTED_SOURCE_DISTRIBUTION = {
    domain: len(DOMAIN_SOURCE_IDS[domain]) for domain in sorted(DOMAIN_SOURCE_IDS)
}
KOREAN_TERMINAL_IDS = frozenset(
    terminal_id
    for source in OFFICIAL_SOURCES.values()
    if source["jurisdiction"] == "KR"
    for terminal_id in source["terminal_ids"]
)


def _words(value: str) -> str:
    return " ".join(part for part in value.replace("-", "_").split("_") if part)


def _ko_aliases(domain: DomainSpec, feature: ReviewedFeature) -> tuple[str, ...]:
    return _dedupe(
        (
            feature.name_ko,
            f"{feature.name_ko} 보기",
            f"{feature.name_ko} 확인",
            f"{feature.name_ko} 화면",
            f"{feature.name_ko} 메뉴",
            f"{feature.name_ko} 상태",
            f"{feature.name_ko} 상세",
            f"{feature.name_ko} 기록",
            f"{domain.root_ko} {feature.name_ko}",
            f"{domain.role_ko} {feature.name_ko}",
            *(f"{term} {feature.name_ko}" for term in KOREAN_DOMAIN_TERMS[domain.domain]),
        )
    )


def _en_aliases(domain: DomainSpec, feature: ReviewedFeature) -> tuple[str, ...]:
    lower = feature.name_en.lower()
    return _dedupe(
        (
            feature.name_en,
            f"view {lower}",
            f"check {lower}",
            f"open {lower}",
            f"find {lower}",
            f"{lower} details",
            f"{lower} status screen",
            f"{domain.root_en}: {feature.name_en}",
            f"authorized participant {lower}",
        )
    )


def _feature_seed(domain: DomainSpec, feature: ReviewedFeature) -> FeatureSeed:
    function_id = f"{domain.domain}.{feature.key}"
    positive = _dedupe(
        (
            feature.goal_ko,
            feature.goal_en,
            feature.purpose_ko,
            feature.purpose_en,
            domain.role_ko,
            *feature.roles,
            *feature.assets,
            *feature.states,
            feature.jurisdiction_guard,
        )
    )
    negative = _dedupe(
        (
            "역할 불일치",
            "다른 사람 또는 다른 기록",
            "다른 생명주기 상태",
            "제공자 또는 관할 불명확",
            "자격 또는 권한을 추정하는 요청",
            "운영자 또는 심사자 화면",
            "wrong role",
            "different person or record",
            "wrong lifecycle state",
            "missing provider or jurisdiction",
            "eligibility or authority must not be inferred",
            "operator or adjudicator surface",
            *domain.collision_terms,
            *domain.nearest_existing_functions,
        )
    )
    return F(
        feature.key,
        feature.name_ko,
        feature.name_en,
        "|".join(_ko_aliases(domain, feature)),
        "|".join(_en_aliases(domain, feature)),
        "|".join(positive),
        "|".join(negative),
        "sensitive" if feature.classification == "S" else "submit",
        sources="|".join(DOMAIN_TERMINAL_SOURCE_IDS[function_id]),
    )


def _group_seed(domain: DomainSpec) -> GroupSeed:
    return G(
        domain.domain,
        domain.root_ko,
        domain.root_en,
        f"{domain.domain}_v19_researched_services",
        "|".join(
            _dedupe(
                (
                    domain.root_ko,
                    domain.role_ko,
                    *domain.assets,
                    *KOREAN_DOMAIN_TERMS[domain.domain],
                )
            )
        ),
        "|".join(_dedupe((domain.root_en, *domain.roles, *domain.assets, *domain.states, domain.jurisdiction))),
        "|".join(_dedupe(("역할 불일치", "다른 기록", "상태 불명확", "제공자·관할 불명확", *domain.collision_terms))),
        "|".join(_dedupe(("wrong role", "different record", "unclear state", "missing provider or jurisdiction", *domain.nearest_existing_functions))),
        domain.avoid_root,
        "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, feature) for feature in domain.features),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {
    domain.domain: len(domain.features) for domain in sorted(REVIEWED_DOMAINS, key=lambda item: item.domain)
}
EXPECTED_DOMAIN_FUNCTION_COUNTS = {
    domain: count + 1 for domain, count in EXPECTED_DOMAIN_COUNTS.items()
}
NEAREST_EXISTING_FUNCTIONS = {
    domain.domain: domain.nearest_existing_functions for domain in REVIEWED_DOMAINS
}


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    tags = [value for value in result.get("legacy_tags", []) if value != "v10_reviewed_operations"]
    result["legacy_tags"] = list(_dedupe((*tags, "v19_research_isolated_services")))
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    ko_aliases = _dedupe(
        (
            domain.root_ko,
            f"{domain.root_ko} 보기",
            f"{domain.root_ko} 화면",
            f"{domain.root_ko} 메뉴",
            f"{domain.root_ko} 안내",
            f"{domain.root_ko} 서비스",
            f"{domain.root_ko} 목록",
            f"{domain.root_ko} 도움",
            *KOREAN_DOMAIN_TERMS[group.domain],
        )
    )
    en_aliases = _dedupe(
        (
            domain.root_en,
            f"{domain.root_en} hub",
            f"{domain.root_en} menu",
            f"{domain.root_en} services",
            f"open {domain.root_en.lower()}",
            f"find {domain.root_en.lower()}",
            f"{domain.root_en} help",
            f"{domain.root_en} destinations",
        )
    )
    result.update(
        {
            "aliases": {"ko-KR": list(ko_aliases), "en-US": list(en_aliases)},
            "automation_policy": "safe_navigation",
            "stop_policy": "continue",
            "risk_level": "low",
            "state_changing": False,
            "user_owned_final_press": False,
            "classification": "H",
            "fail_closed": True,
            "resolution_policy": "fail_closed",
            "requires_explicit_terminal_disambiguation": True,
            "jurisdiction_aliases": {
                "KR": list(KOREAN_DOMAIN_TERMS[group.domain]),
                "provider_scoped": [domain.jurisdiction],
            },
        }
    )
    result["role_hints"] = list(_dedupe((domain.role_ko, *domain.roles)))
    result["asset_cues"] = list(_dedupe((*domain.assets, f"{domain.root_en} governed record")))
    result["state_cues"] = {
        "lifecycle": list(domain.states),
        "jurisdiction": [domain.jurisdiction, "provider and jurisdiction must be explicit"],
        "missing_dimension": ["missing role", "missing governed asset", "missing state", "missing provider or jurisdiction"],
    }
    result["risk_cues"] = {
        "hub_boundary": [
            "역할·자산·상태·제공자·관할 중 하나라도 불명확하면 허브에서 중단",
            "stop on this hub when any role, asset, state, provider, or jurisdiction dimension is missing",
        ],
        "source_boundary": [domain.boundary],
        "collision_neighbors": list(domain.nearest_existing_functions),
    }
    result["source_refs"] = list(DOMAIN_SOURCE_IDS[group.domain])
    result["provider_scopes"] = sorted(
        {str(OFFICIAL_SOURCES[source_id]["provider_scope"]) for source_id in result["source_refs"]}
    )
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    function_id = str(result["function_id"])
    result.update(
        {
            "aliases": {
                "ko-KR": list(_ko_aliases(domain, feature)),
                "en-US": list(_en_aliases(domain, feature)),
            },
            "automation_policy": "never_auto",
            "stop_policy": "before_action",
            "risk_level": "high",
            "state_changing": feature.classification == "C",
            "consequential": feature.classification == "C",
            "view_only": feature.classification == "S",
            "user_owned_final_press": True,
            "classification": feature.classification,
            "representative_goals": {"ko-KR": feature.goal_ko, "en-US": feature.goal_en},
            "purpose_by_locale": {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en},
            "jurisdiction_aliases": {
                "KR": list(KOREAN_DOMAIN_TERMS[group.domain]),
                "provider_scoped": [feature.jurisdiction_guard],
            },
            "semantic_scope": {
                "roles": list(feature.roles),
                "assets": list(feature.assets),
                "states": list(feature.states),
                "jurisdiction": feature.jurisdiction_guard,
                "safety_boundary": feature.safety_boundary,
            },
        }
    )
    result["positive_context"] = list(
        _dedupe(
            (
                *result.get("positive_context", []),
                domain.role_ko,
                feature.goal_ko,
                feature.purpose_ko,
                *feature.roles,
                *feature.assets,
                *feature.states,
                feature.jurisdiction_guard,
            )
        )
    )
    result["role_hints"] = list(_dedupe((domain.role_ko, *feature.roles)))
    result["asset_cues"] = list(_dedupe((*feature.assets, feature.name_ko, feature.name_en, _words(feature.key))))
    result["state_cues"] = {
        "lifecycle": list(feature.states),
        "jurisdiction": [feature.jurisdiction_guard, "provider and jurisdiction must be explicit"],
        "wrong_role": ["역할 불일치", "권한 없는 사용자", "wrong role", "role not authorized"],
        "wrong_asset": ["다른 사람 또는 기록", "다른 자산", "wrong person or record", "different asset"],
        "wrong_state": ["다른 생명주기 상태", "현재 상태 불명확", "wrong lifecycle state", "state unclear"],
        "unavailable": ["비활성", "사용 불가", "권한 거부", "disabled", "unavailable", "permission denied"],
        "offline": ["오프라인", "오래된 정보", "offline", "stale data"],
        "hold": ["검토 대기", "법적 보류", "안전 보류", "pending review", "legal hold", "safety hold"],
    }
    result["risk_cues"] = {
        "classification": [
            "S: sensitive or permission-limited view"
            if feature.classification == "S"
            else "C: consequential applicant- or participant-owned action"
        ],
        "role_asset_state_jurisdiction_gate": [
            "권한 역할·정확한 자산·현재 상태·제공자와 관할을 모두 확인",
            "verify authorized role, exact governed asset, current lifecycle state, provider, and jurisdiction",
            "all four routing dimensions are mandatory",
        ],
        "fail_closed": [
            "어느 차원이라도 없거나 충돌하면 도메인 허브에서 중단",
            "stop at the domain hub on any missing or conflicting dimension",
        ],
        "forbidden_terminal_actions": [
            "제출·결제·인증·취소·선택·변경·신고·이의제기 자동 실행 금지",
            "never auto-submit, pay, certify, cancel, select, change, report, or appeal",
        ],
        "blocked_final_channels": [
            "음성·키보드·딥링크·재시도·접근성 동작으로 최종 행동 우회 금지",
            "no final-action bypass through voice, keyboard, deep link, retry, or accessibility action",
        ],
        "user_boundary": ["최종 목적지 동작은 사용자가 직접 수행", "the user must perform the final destination action"],
        "user_owned_final_press": ["true", "사용자 소유 최종 누름"],
        "source_boundary": [feature.safety_boundary],
        "collision_neighbors": list(domain.nearest_existing_functions),
    }
    result["source_refs"] = list(DOMAIN_TERMINAL_SOURCE_IDS[function_id])
    result["provider_scopes"] = sorted(
        {str(OFFICIAL_SOURCES[source_id]["provider_scope"]) for source_id in result["source_refs"]}
    )
    return result


def _intent_patterns(domain: DomainSpec, feature: ReviewedFeature) -> dict[str, list[str]]:
    role_en = feature.roles[0]
    asset_en = feature.assets[0]
    state_en = feature.states[0]
    return {
        "ko-KR": list(
            _dedupe(
                (
                    feature.goal_ko,
                    f"{domain.role_ko}로서 {feature.name_ko} 화면을 열고 싶어",
                    f"{domain.root_ko}의 {feature.name_ko} 메뉴를 찾아줘",
                    f"정확한 대상 기록과 현재 상태를 확인하고 {feature.name_ko} 위치로 이동해 줘",
                    f"제공자와 관할을 확인한 뒤 {feature.name_ko}을 찾아줘",
                )
            )
        ),
        "en-US": list(
            _dedupe(
                (
                    feature.goal_en,
                    f"As {role_en}, open {feature.name_en.lower()}",
                    f"Find {feature.name_en.lower()} within {domain.root_en.lower()}",
                    f"For {asset_en} in state {state_en}, locate {feature.name_en.lower()}",
                    f"After confirming provider and jurisdiction, take me to {feature.name_en.lower()}",
                )
            )
        ),
    }


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = f"v19_{group.domain}_{seed.key}"
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v19_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v19_{key[4:]}"] = rule.pop(key)
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    target = f"{group.domain}.{seed.key}"
    patterns_by_locale = _intent_patterns(domain, feature)
    result["patterns_by_locale"] = patterns_by_locale
    result["patterns"] = [*patterns_by_locale["ko-KR"], *patterns_by_locale["en-US"]]
    result["representative_goal_by_locale"] = {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}
    result["purpose_by_locale"] = {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}
    governance_terms = [feature.roles[0], feature.assets[0], feature.states[0], feature.jurisdiction_guard]
    result["goal_rules"].append(
        {
            "all_of": governance_terms,
            "none_of": [
                "wrong role",
                "different person or record",
                "wrong lifecycle state",
                "missing provider or jurisdiction",
                "operator or adjudicator surface",
            ],
            "score": 0.999,
            "rule_kind": "v19_role_asset_state_jurisdiction_gate",
            "v19_discriminative_keys": [
                key for key in (_runtime_pattern_key(value) for value in governance_terms) if key
            ],
            "v19_required_dimensions": ["authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction"],
            "v19_required_dimension_count": 4,
        }
    )
    result["goal_rules"].append(
        {
            "all_of": [KOREAN_DOMAIN_TERMS[group.domain][0], feature.name_ko],
            "none_of": ["잘못된 역할", "다른 제공자", "관할 불명확"],
            "score": 0.999,
            "rule_kind": "v19_kr_provider_jurisdiction_gate",
            "v19_jurisdiction": "KR",
            "v19_discriminative_keys": [
                _runtime_pattern_key(KOREAN_DOMAIN_TERMS[group.domain][0]),
                _runtime_pattern_key(feature.name_ko),
            ],
        }
    )
    peers = [f"{group.domain}.{item.key}" for item in domain.features if item.key != seed.key]
    result["avoid_functions"] = list(
        _dedupe((*peers[:3], *result.get("avoid_functions", []), domain.avoid_root, *domain.nearest_existing_functions))
    )
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {"stop_policy": "stop_before_action", "user_owned_final_press": True}
    result["resolution_gate"] = {
        "dimensions": ["authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction"],
        "required_dimensions": ["authorized_role", "governed_asset", "lifecycle_state", "provider_jurisdiction"],
        "minimum_positive_dimensions": 4,
        "on_missing_dimension": "fail_closed",
        "fail_closed_to": f"{group.domain}.hub",
    }
    return result


V19_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V19_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


COLLISION_FAMILIES = tuple(
    (domain.domain, neighbor, domain.collision_terms[index % len(domain.collision_terms)])
    for domain in REVIEWED_DOMAINS
    for index, neighbor in enumerate(domain.nearest_existing_functions)
)


def build_collision_probes() -> tuple[dict[str, object], ...]:
    """Return bilingual fail-closed probes for every documented nearby collision."""

    probes: list[dict[str, object]] = []
    for family_index, (domain, neighbor, token) in enumerate(COLLISION_FAMILIES):
        spec = REVIEWED_BY_DOMAIN[domain]
        for locale, text_value in (
            ("ko-KR", f"{spec.root_ko}에서 {token}이라는 말만 있고 역할·자산·상태·제공자·관할이 불명확해"),
            ("en-US", f"{token} is ambiguous between {domain} and {neighbor} with no role asset state provider or jurisdiction"),
        ):
            probes.append(
                {
                    "probe_id": f"v19_collision_{family_index:02d}_{locale}",
                    "locale": locale,
                    "text": text_value,
                    "expected_function": f"{domain}.hub",
                    "excluded_function": neighbor,
                    "required_policy": "fail_closed",
                }
            )
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return two positive and four missing-dimension probes per terminal."""

    probes: list[dict[str, object]] = []
    for intent in V19_INTENTS:
        target = str(intent["terminal_function"])
        domain = target.split(".", 1)[0]
        for locale in ("ko-KR", "en-US"):
            probes.append(
                {
                    "kind": "positive",
                    "locale": locale,
                    "text": intent["patterns_by_locale"][locale][0],
                    "expected_function": target,
                }
            )
        for kind, text_value in (
            ("missing_role", "authorized applicant or participant role is missing"),
            ("missing_asset", "governed personal asset is missing"),
            ("missing_state", "lifecycle state is missing"),
            ("missing_jurisdiction", "provider and jurisdiction are missing"),
        ):
            probes.append(
                {
                    "kind": kind,
                    "locale": "en-US",
                    "text": f"{target} {text_value}",
                    "expected_function": f"{domain}.hub",
                    "excluded_function": target,
                }
            )
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed state/permission interlocks per terminal."""

    scenarios = (
        ("disabled", "disabled control interlock"),
        ("unavailable_offline", "provider unavailable offline or stale data"),
        ("permission_denied", "permission denied for the current personal role"),
        ("hold_or_changed_state", "legal safety or provider hold and lifecycle state changed"),
    )
    probes: list[dict[str, object]] = []
    for function in V19_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text_value in scenarios:
            probes.append(
                {
                    "probe_id": f"v19_recovery_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{function['name_en']} {text_value}",
                    "expected_function": f"{function['domain']}.hub",
                    "excluded_function": function["function_id"],
                    "required_policy": "never_auto",
                    "required_stop_policy": "before_action",
                    "required_user_owned_final_press": True,
                }
            )
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-asset, and wrong-state isolation probes."""

    scenarios = (
        ("wrong_role", "다른 운영자·심사자 역할 other unauthorized operator or adjudicator role"),
        ("wrong_asset", "다른 사람 또는 자산 different person or governed asset"),
        ("wrong_state", "다른 생명주기 상태 different lifecycle state"),
    )
    probes: list[dict[str, object]] = []
    for function in V19_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text_value in scenarios:
            probes.append(
                {
                    "probe_id": f"v19_isolation_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{function['name_en']} {text_value}",
                    "expected_function": f"{function['domain']}.hub",
                    "excluded_function": function["function_id"],
                }
            )
    return tuple(probes)


@dataclass(frozen=True)
class LocalizationCorrection:
    function_id: str
    expected_name_ko: str
    corrected_name_ko: str
    context_ko: tuple[str, ...]


def L(function_id: str, expected_name_ko: str, corrected_name_ko: str, context_ko: str) -> LocalizationCorrection:
    return LocalizationCorrection(function_id, expected_name_ko, corrected_name_ko, _terms(context_ko))


# These are display-only overlays on inherited V12 records.  IDs, English
# names, routing, safety, sources, and intents are deliberately unchanged.
LOCALIZATION_CORRECTIONS: tuple[LocalizationCorrection, ...] = (
    L("freight_forwarding_customs_ops.booking_detail", "shipment · carrier booking·space·cutoff", "선적·운송사 예약·선복·마감 상세", "선적 예약|운송사 예약|선복 확인|화물 마감"),
    L("research_grants_administration.sponsor_guidance_review", "opportunity · announcement·instructions·policy·deadline", "연구지원 기회·공고·지침 검토", "연구지원 기회|지원기관 공고|과제 지침|제출 마감"),
    L("research_grants_administration.budget_view", "proposal·award · category·period·direct/indirect cost", "연구제안·과제 예산 조회", "연구제안 예산|수주과제 예산|직접비·간접비|예산 기간"),
    L("research_grants_administration.compliance_status", "project · disclosure·human/animal/biosafety·training status", "연구과제 준수 상태", "연구윤리 준수|인체·동물 연구|생물안전|교육 이수"),
    L("research_grants_administration.award_portfolio", "investigator·unit · active award·period·balance·status", "연구자·부서 수주과제 포트폴리오", "연구자 수주과제|부서 과제 현황|과제 기간|과제 잔액"),
    L("research_grants_administration.expenditure_dashboard", "award · obligation·expenditure·encumbrance·balance", "연구과제 지출 대시보드", "연구과제 지출|지출 의무|예산 약정|과제 잔액"),
    L("research_grants_administration.reporting_calendar", "award · progress·financial·invention·closeout due dates", "연구과제 보고 일정", "진도 보고|재무 보고|발명 보고|종료 보고 기한"),
    L("corrections_case_management_ops.court_order_sentence_review", "legal record · court order·sentence·detainer·credit", "법원명령·형기·구금명령·산입일수 검토", "법원명령|형기 검토|구금명령|산입일수"),
    L("corrections_case_management_ops.housing_location_status", "facility · person·unit·cell/bed·movement status", "수용시설·수용동·거실 위치 상태", "수용시설 위치|수용동|거실·침상|이동 상태"),
    L("corrections_case_management_ops.program_eligibility_view", "case plan · education·treatment·reentry program eligibility", "교육·치료·사회복귀 프로그램 자격 조회", "교육 프로그램|치료 프로그램|사회복귀 프로그램|사례계획 자격"),
    L("corrections_case_management_ops.release_date_calculation_review", "sentence computation · term·credit·detainer·projected release", "형기·산입일수·출소예정일 계산 검토", "형기 계산|산입일수|구금명령|출소예정일"),
    L("corrections_case_management_ops.incident_disciplinary_report", "facility incident · person·rule·evidence·immediate action · disciplinary report", "시설 사건·징계 보고 제출", "시설 사건|징계 보고|관련자·규정|증거·즉시조치"),
    L("corrections_case_management_ops.property_chain_of_custody", "person property·evidence · item·seal·location·handler · custody transfer", "개인물품·증거물 보관이력 이전", "개인물품|증거물|봉인·보관위치|인계 담당자"),
)
LOCALIZATION_CORRECTION_BY_ID = {
    correction.function_id: correction for correction in LOCALIZATION_CORRECTIONS
}
LOCALIZATION_CORRECTION_IDS = frozenset(LOCALIZATION_CORRECTION_BY_ID)
NON_HANGUL_NAME_KO_ALLOWLIST = frozenset(
    {"android_connectivity.quick_share", "android_connectivity.nfc", "sim.pin"}
)
LOCALIZATION_FIELDS = ("name_ko", "description", "aliases", "positive_context")


def _localization_field_snapshot(function: Mapping[str, object]) -> dict[str, object]:
    return {field: copy.deepcopy(function.get(field)) for field in LOCALIZATION_FIELDS}


_V12_FUNCTION_BY_ID = {str(item["function_id"]): item for item in V12_FUNCTIONS}
if not LOCALIZATION_CORRECTION_IDS <= set(_V12_FUNCTION_BY_ID):
    raise V19CatalogValidationError("V19 localization targets are missing from the inherited V12 layer")
LOCALIZATION_PREIMAGE_SHA256 = {
    function_id: _digest(_localization_field_snapshot(_V12_FUNCTION_BY_ID[function_id]))
    for function_id in sorted(LOCALIZATION_CORRECTION_IDS)
}


def _localized_fields(
    function: Mapping[str, object], correction: LocalizationCorrection
) -> dict[str, object]:
    result = _localization_field_snapshot(function)
    aliases = result.get("aliases")
    if not isinstance(aliases, Mapping):
        raise V19CatalogValidationError(f"{correction.function_id}: localization aliases are malformed")
    ko_aliases = aliases.get("ko-KR", [])
    if not isinstance(ko_aliases, (list, tuple)):
        raise V19CatalogValidationError(f"{correction.function_id}: Korean aliases are malformed")
    localized_aliases = copy.deepcopy(dict(aliases))
    localized_aliases["ko-KR"] = list(
        _dedupe(
            (
                correction.corrected_name_ko,
                f"{correction.corrected_name_ko} 조회",
                f"{correction.corrected_name_ko} 확인",
                f"{correction.corrected_name_ko} 화면",
                f"{correction.corrected_name_ko} 상세",
                f"{correction.corrected_name_ko} 메뉴",
                f"{correction.corrected_name_ko} 열기",
                f"{correction.corrected_name_ko} 찾기",
                *correction.context_ko,
                *(str(value) for value in ko_aliases),
            )
        )
    )
    positive_context = result.get("positive_context")
    if not isinstance(positive_context, (list, tuple)):
        raise V19CatalogValidationError(f"{correction.function_id}: positive context is malformed")
    name_en = str(function.get("name_en", "")).strip()
    if not name_en:
        raise V19CatalogValidationError(f"{correction.function_id}: English name is missing")
    result.update(
        {
            "name_ko": correction.corrected_name_ko,
            "description": (
                f"{correction.corrected_name_ko} 목적지와 사용자 소유 최종 동작의 경계를 먼저 식별한다. "
                f"Preserves the inherited {name_en} routing and user-owned final-action boundary."
            ),
            "aliases": localized_aliases,
            "positive_context": list(
                _dedupe(
                    (
                        correction.corrected_name_ko,
                        *correction.context_ko,
                        *(str(value) for value in positive_context),
                    )
                )
            ),
        }
    )
    return result


def _apply_localization_corrections(payload: dict[str, object]) -> dict[str, object]:
    functions = payload.get("functions", [])
    if not isinstance(functions, list):
        raise V19CatalogValidationError("V19 localization requires a function list")
    by_id: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in functions:
        if isinstance(item, dict):
            by_id[str(item.get("function_id", ""))].append(item)
    ledger_rows: dict[str, dict[str, object]] = {}
    for correction in LOCALIZATION_CORRECTIONS:
        matches = by_id.get(correction.function_id, [])
        if len(matches) != 1:
            raise V19CatalogValidationError(
                f"{correction.function_id}: localization preimage must occur exactly once"
            )
        function = matches[0]
        if function.get("name_ko") != correction.expected_name_ko:
            raise V19CatalogValidationError(
                f"{correction.function_id}: localization preimage name differs"
            )
        before = _localization_field_snapshot(function)
        if _digest(before) != LOCALIZATION_PREIMAGE_SHA256[correction.function_id]:
            raise V19CatalogValidationError(
                f"{correction.function_id}: localization preimage fields differ"
            )
        after = _localized_fields(function, correction)
        for field, value in after.items():
            function[field] = copy.deepcopy(value)
        ledger_rows[correction.function_id] = {
            "function_id": correction.function_id,
            "expected_name_ko": correction.expected_name_ko,
            "corrected_name_ko": correction.corrected_name_ko,
            "before": before,
            "after": after,
            "before_sha256": _digest(before),
            "after_sha256": _digest(after),
        }
    return {
        "schema_version": 1,
        "mode": "display_only_reversible_overlay",
        "fields": list(LOCALIZATION_FIELDS),
        "correction_ids": sorted(LOCALIZATION_CORRECTION_IDS),
        "non_hangul_name_ko_allowlist": sorted(NON_HANGUL_NAME_KO_ALLOWLIST),
        "corrections": ledger_rows,
    }


def _validate_localization_ledger(
    payload: Mapping[str, object], ledger: object
) -> dict[str, object]:
    if not isinstance(ledger, Mapping):
        raise V19CatalogValidationError("V19 localization ledger is missing or malformed")
    if (
        ledger.get("schema_version") != 1
        or ledger.get("mode") != "display_only_reversible_overlay"
        or ledger.get("fields") != list(LOCALIZATION_FIELDS)
        or ledger.get("correction_ids") != sorted(LOCALIZATION_CORRECTION_IDS)
        or ledger.get("non_hangul_name_ko_allowlist") != sorted(NON_HANGUL_NAME_KO_ALLOWLIST)
    ):
        raise V19CatalogValidationError("V19 localization ledger contract differs")
    rows = ledger.get("corrections")
    if not isinstance(rows, Mapping) or set(rows) != LOCALIZATION_CORRECTION_IDS:
        raise V19CatalogValidationError("V19 localization ledger IDs differ")
    functions = payload.get("functions", [])
    by_id: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    if isinstance(functions, (list, tuple)):
        for item in functions:
            if isinstance(item, Mapping):
                by_id[str(item.get("function_id", ""))].append(item)
    for function_id, correction in LOCALIZATION_CORRECTION_BY_ID.items():
        matches = by_id.get(function_id, [])
        row = rows.get(function_id)
        if len(matches) != 1 or not isinstance(row, Mapping):
            raise V19CatalogValidationError(f"{function_id}: localization ledger target differs")
        function = matches[0]
        before = row.get("before")
        after = row.get("after")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise V19CatalogValidationError(f"{function_id}: localization snapshots are malformed")
        if (
            row.get("function_id") != function_id
            or row.get("expected_name_ko") != correction.expected_name_ko
            or row.get("corrected_name_ko") != correction.corrected_name_ko
            or before.get("name_ko") != correction.expected_name_ko
            or after.get("name_ko") != correction.corrected_name_ko
            or row.get("before_sha256") != _digest(before)
            or row.get("before_sha256") != LOCALIZATION_PREIMAGE_SHA256[function_id]
            or row.get("after_sha256") != _digest(after)
        ):
            raise V19CatalogValidationError(f"{function_id}: localization snapshot seal differs")
        preimage = copy.deepcopy(dict(function))
        for field in LOCALIZATION_FIELDS:
            preimage[field] = copy.deepcopy(before.get(field))
        expected_after = _localized_fields(preimage, correction)
        if dict(after) != expected_after or _localization_field_snapshot(function) != dict(after):
            raise V19CatalogValidationError(f"{function_id}: localized function differs from ledger")
    return copy.deepcopy(dict(ledger))


def _revert_localization_corrections(payload: dict[str, object], ledger: object) -> None:
    validated = _validate_localization_ledger(payload, ledger)
    functions = {
        str(item["function_id"]): item
        for item in payload.get("functions", [])
        if isinstance(item, dict) and "function_id" in item
    }
    rows = validated["corrections"]
    for function_id in sorted(LOCALIZATION_CORRECTION_IDS):
        before = rows[function_id]["before"]
        for field in LOCALIZATION_FIELDS:
            functions[function_id][field] = copy.deepcopy(before[field])


def _verify_source_documents() -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        path = ROOT / relative_path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual[relative_path] = digest
        if digest != expected:
            raise V19CatalogValidationError(
                f"V19 source SHA-256 differs for {relative_path}: expected {expected}, got {digest}"
            )
    return actual


def _layer_digest() -> str:
    payload = {
        "catalog_version": CATALOG_V19_VERSION,
        "base_layer_seal": BASE_LAYER_SEAL,
        "reviewed_domains": [asdict(domain) for domain in REVIEWED_DOMAINS],
        "functions": V19_FUNCTIONS,
        "intents": V19_INTENTS,
        "official_sources": OFFICIAL_SOURCES,
        "official_sources_sha256": OFFICIAL_SOURCES_SHA256,
        "source_documents": SOURCE_DOCUMENT_METADATA,
        "source_document_text_profile": SOURCE_DOCUMENT_TEXT_PROFILE,
        "korean_domain_terms": KOREAN_DOMAIN_TERMS,
        "nearest_existing_functions": NEAREST_EXISTING_FUNCTIONS,
        "rejected_duplicate_families": REJECTED_DUPLICATE_FAMILIES,
        "localization_corrections": [asdict(item) for item in LOCALIZATION_CORRECTIONS],
        "localization_preimage_sha256": LOCALIZATION_PREIMAGE_SHA256,
        "non_hangul_name_ko_allowlist": sorted(NON_HANGUL_NAME_KO_ALLOWLIST),
        "projected_counts": PROJECTED_COUNTS,
    }
    return _digest(payload)


DOCUMENT_DIGESTS = _verify_source_documents()
V19_LAYER_SHA256 = _layer_digest()
EXPECTED_V19_LAYER_SHA256 = "4438e2745075abc00a4d4adeb3aac661c1417affb24835c6955e09f353197587"
EXPECTED_CLASS_COUNTS = {"S": 52, "C": 62}
EXPECTED_PROBE_COUNTS = {
    "semantic": 684,
    "collision": 122,
    "recovery": 456,
    "role_asset": 342,
}


def _korean_metadata() -> dict[str, object]:
    return {
        "terms": {domain: list(terms) for domain, terms in sorted(KOREAN_DOMAIN_TERMS.items())},
        "terminal_ids": sorted(KOREAN_TERMINAL_IDS),
        "source_ids": sorted(
            source_id for source_id, source in OFFICIAL_SOURCES.items() if source["jurisdiction"] == "KR"
        ),
        "localization_correction_ids": sorted(LOCALIZATION_CORRECTION_IDS),
        "non_hangul_name_ko_allowlist": sorted(NON_HANGUL_NAME_KO_ALLOWLIST),
        "isolation": "provider- and jurisdiction-specific; Korean labels never relabel a different jurisdictional form",
    }


def _layer_integrity_metadata() -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "sha256": V19_LAYER_SHA256,
        "expected_sha256": EXPECTED_V19_LAYER_SHA256,
        "official_sources_sha256": OFFICIAL_SOURCES_SHA256,
        "expected_official_sources_sha256": EXPECTED_OFFICIAL_SOURCES_SHA256,
        "base_layer_sha256": EXPECTED_V18_LAYER_SHA256,
        "localization_contract_sha256": _digest(
            {
                "corrections": [asdict(item) for item in LOCALIZATION_CORRECTIONS],
                "preimage_sha256": LOCALIZATION_PREIMAGE_SHA256,
                "allowlist": sorted(NON_HANGUL_NAME_KO_ALLOWLIST),
            }
        ),
        "domains": 9,
        "functions": 123,
        "terminal_functions": 114,
        "intents": 114,
        "official_sources": len(OFFICIAL_SOURCES),
        "localization_corrections": len(LOCALIZATION_CORRECTIONS),
    }


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Return the exact prospective V18 payload, materialized only in memory."""

    return merge_v18_with_base(load_v17_source_base(path))


V19_METADATA_KEYS = (
    "official_sources_v19",
    "source_documents_v19",
    "korean_jurisdiction_v19",
    "nearest_function_collisions_v19",
    "rejected_duplicate_families_v19",
    "base_layer_seal_v19",
    "localization_corrections_v19",
    "layer_integrity_v19",
)


def _pre_v19_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V19_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V19_INTENTS}
    result = copy.deepcopy(dict(payload))
    if "localization_corrections_v19" in result:
        _revert_localization_corrections(result, result["localization_corrections_v19"])
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    for key in V19_METADATA_KEYS:
        result.pop(key, None)
    result["catalog_version"] = CATALOG_V18_VERSION
    result["description"] = CATALOG_V18_DESCRIPTION
    return result


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V19_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V19_INTENTS}
    present_functions = {
        str(item["function_id"]): item
        for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item
        for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    has_metadata = any(key in payload for key in V19_METADATA_KEYS)
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V19CatalogValidationError("partial V19 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V19CatalogValidationError("V19 collides with a different function or intent definition")
    if payload.get("official_sources_v19") != OFFICIAL_SOURCES:
        raise V19CatalogValidationError("V19 official-source registry differs")
    if payload.get("source_documents_v19") != SOURCE_DOCUMENT_METADATA:
        raise V19CatalogValidationError("V19 source-document SHA registry differs")
    if payload.get("korean_jurisdiction_v19") != _korean_metadata():
        raise V19CatalogValidationError("V19 Korean-jurisdiction metadata differs")
    if payload.get("nearest_function_collisions_v19") != {
        key: list(value) for key, value in sorted(NEAREST_EXISTING_FUNCTIONS.items())
    }:
        raise V19CatalogValidationError("V19 nearest-function collision registry differs")
    if payload.get("rejected_duplicate_families_v19") != list(REJECTED_DUPLICATE_FAMILIES):
        raise V19CatalogValidationError("V19 rejected-duplicate registry differs")
    if payload.get("base_layer_seal_v19") != BASE_LAYER_SEAL:
        raise V19CatalogValidationError("V19 base-layer seal differs")
    _validate_localization_ledger(payload, payload.get("localization_corrections_v19"))
    if payload.get("layer_integrity_v19") != _layer_integrity_metadata():
        raise V19CatalogValidationError("V19 layer-integrity metadata differs")
    if payload.get("catalog_version") != CATALOG_V19_VERSION or payload.get("description") != CATALOG_V19_DESCRIPTION:
        raise V19CatalogValidationError("V19 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def _duplicates(values: Iterable[str]) -> set[str]:
    return {value for value, count in Counter(values).items() if count > 1}


def _research_direct_urls(source_text: str) -> set[str]:
    values = (match.rstrip(".,;") for match in re.findall(r"https://[^\s]+", source_text))
    return {normalize_official_url(value) for value in values}


def _research_proposed_terminal_ids(source_text: str) -> tuple[str, ...]:
    blocks = re.findall(
        r"(?ms)\*\*Prospective terminal seams\.\*\*\s*(.*?)\*\*Nearest canonical collisions",
        source_text,
    )
    return tuple(
        terminal_id
        for block in blocks
        for terminal_id in re.findall(r"`([a-z0-9_]+\.[a-z0-9_]+)`", block)
    )


def _research_rejected_candidate_labels(source_text: str) -> tuple[str, ...]:
    match = re.search(
        r"(?ms)## Explicitly rejected duplicates and weak candidates\s*(.*?)Rejected duplicate count:",
        source_text,
    )
    if match is None:
        return ()
    rows = re.findall(r"(?m)^\|\s*([^|]+?)\s*\|", match.group(1))
    return tuple(value for value in rows if value not in {"Rejected candidate", "---"})


def _dimension_keys(values: Iterable[object]) -> frozenset[str]:
    return frozenset(
        key
        for value in values
        for key in (_runtime_pattern_key(str(value)),)
        if key
    )


def _function_semantic_dimensions(function: Mapping[str, object]) -> tuple[
    frozenset[str], frozenset[str], frozenset[str], frozenset[str]
]:
    scope = function.get("semantic_scope", {})
    state_cues = function.get("state_cues", {})
    if not isinstance(scope, Mapping):
        scope = {}
    if not isinstance(state_cues, Mapping):
        state_cues = {}
    roles = scope.get("roles", function.get("role_hints", []))
    assets = scope.get("assets", function.get("asset_cues", []))
    states = scope.get("states", state_cues.get("lifecycle", []))
    jurisdiction = scope.get("jurisdiction", state_cues.get("jurisdiction", []))
    if isinstance(jurisdiction, str):
        jurisdiction = [jurisdiction]
    return (
        _dimension_keys(roles if isinstance(roles, (list, tuple)) else [roles]),
        _dimension_keys(assets if isinstance(assets, (list, tuple)) else [assets]),
        _dimension_keys(states if isinstance(states, (list, tuple)) else [states]),
        _dimension_keys(jurisdiction if isinstance(jurisdiction, (list, tuple)) else [jurisdiction]),
    )


def _has_four_dimension_overlap(
    left: tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]],
    right: tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]],
) -> bool:
    return all(a.intersection(b) for a, b in zip(left, right))


def _non_hangul_name_ids(functions: Iterable[Mapping[str, object]]) -> set[str]:
    hangul = re.compile(r"[\uac00-\ud7a3]")
    return {
        str(function.get("function_id", ""))
        for function in functions
        if not hangul.search(str(function.get("name_ko", "")))
    }


def validate_v19_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate evidence, semantics, safety, localization, and V18 isolation."""

    # Validation is read-only.  Keep only a shallow top-level view here; the
    # reversible pre-V19 projection below owns the one required deep copy.
    base = load_base_catalog() if base_payload is None else dict(base_payload)
    errors: list[str] = []
    source_path = ROOT / DESIGN_SOURCE_RELATIVE_PATH
    source_text = source_path.read_text(encoding="utf-8")
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"source SHA differs for {relative_path}: {actual}")
    source_text_profile = {
        "hangul_syllables": len(re.findall(r"[\uac00-\ud7a3]", source_text)),
        "replacement_characters": source_text.count("\ufffd"),
    }
    if source_text_profile != SOURCE_DOCUMENT_TEXT_PROFILE:
        errors.append(f"V19 source document Unicode profile differs: {source_text_profile}")
    if V18_LAYER_SHA256 != EXPECTED_V18_LAYER_SHA256:
        errors.append(f"V18 base layer SHA differs: {V18_LAYER_SHA256}")
    current_sources_sha256 = _digest(OFFICIAL_SOURCES)
    if OFFICIAL_SOURCES_SHA256 != EXPECTED_OFFICIAL_SOURCES_SHA256 or current_sources_sha256 != EXPECTED_OFFICIAL_SOURCES_SHA256:
        errors.append(f"V19 official-source SHA differs: {current_sources_sha256}")
    current_layer_sha256 = _layer_digest()
    if V19_LAYER_SHA256 != EXPECTED_V19_LAYER_SHA256 or current_layer_sha256 != EXPECTED_V19_LAYER_SHA256:
        errors.append(f"V19 layer SHA differs: {current_layer_sha256}")

    function_ids = [str(item["function_id"]) for item in V19_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V19_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V19_FUNCTIONS if item["terminal"]}
    domain_terminal_counts = Counter(str(item["domain"]) for item in V19_FUNCTIONS if item["terminal"])
    domain_function_counts = Counter(str(item["domain"]) for item in V19_FUNCTIONS)
    if _duplicates(function_ids) or _duplicates(intent_ids):
        errors.append("V19 contains duplicate function or intent IDs")
    research_terminal_ids = _research_proposed_terminal_ids(source_text)
    if len(research_terminal_ids) != 114 or set(research_terminal_ids) != terminal_ids:
        errors.append("V19 terminal IDs differ from the nine research proposal lists")
    if len(REQUIRED_DOMAINS) != 9 or len(V19_FUNCTIONS) != 123 or len(terminal_ids) != 114 or len(V19_INTENTS) != 114:
        errors.append("V19 requires 9 domains, 9 hubs, 114 terminals, 123 functions, and 114 intents")
    if dict(sorted(domain_terminal_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"V19 terminal counts differ: {dict(sorted(domain_terminal_counts.items()))}")
    if dict(sorted(domain_function_counts.items())) != EXPECTED_DOMAIN_FUNCTION_COUNTS:
        errors.append(f"V19 function counts differ: {dict(sorted(domain_function_counts.items()))}")
    if len(REJECTED_DUPLICATE_FAMILIES) != 12 or len(set(REJECTED_DUPLICATE_FAMILIES)) != 12:
        errors.append("V19 requires exactly twelve distinct rejected duplicate families")
    if len(_research_rejected_candidate_labels(source_text)) != 12:
        errors.append("V19 research rejected-candidate table must contain exactly twelve families")

    sensitive = sum(
        bool(item["terminal"])
        and item.get("classification") == "S"
        and item.get("view_only") is True
        and item.get("state_changing") is False
        for item in V19_FUNCTIONS
    )
    consequential = sum(
        bool(item["terminal"])
        and item.get("classification") == "C"
        and item.get("consequential") is True
        and item.get("state_changing") is True
        for item in V19_FUNCTIONS
    )
    if {"S": sensitive, "C": consequential} != EXPECTED_CLASS_COUNTS:
        errors.append(f"V19 S/C counts differ: S={sensitive}, C={consequential}")

    forbidden = {
        "x",
        "y",
        "bounds",
        "coordinate",
        "coordinates",
        "package",
        "package_id",
        "package_name",
        "resource_id",
        "screenshot",
        "screenshot_hash",
        "screen_path",
        "recorded_route",
        "recorded_path",
        "fixed_ui_path",
        "pixel",
        "click_sequence",
        "selector",
        "xpath",
    }
    hangul = re.compile(r"[\uac00-\ud7a3]")
    functions_by_id = {str(item["function_id"]): item for item in V19_FUNCTIONS}
    goals_ko: list[str] = []
    goals_en: list[str] = []
    purposes_ko: list[str] = []
    purposes_en: list[str] = []
    semantic_signatures: list[tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]] = []
    for function in V19_FUNCTIONS:
        function_id = str(function["function_id"])
        if _contains_forbidden_key(function, forbidden):
            errors.append(f"{function_id}: forbidden app-specific UI key")
        if not function.get("source_refs") or set(function["source_refs"]) - set(OFFICIAL_SOURCES):
            errors.append(f"{function_id}: invalid official source references")
        if len(function["aliases"]["ko-KR"]) < 8 or len(function["aliases"]["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if not hangul.search(str(function["name_ko"])) or any(
            not hangul.search(str(alias)) for alias in function["aliases"]["ko-KR"]
        ):
            errors.append(f"{function_id}: Korean name or alias lacks Hangul")
        if not function.get("role_hints") or not function.get("asset_cues") or not function.get("state_cues", {}).get("jurisdiction"):
            errors.append(f"{function_id}: missing role, asset, state, or jurisdiction semantics")
        if not function.get("provider_scopes"):
            errors.append(f"{function_id}: provider scope is empty")
        if function["terminal"]:
            feature = REVIEWED_FEATURE_BY_ID[function_id]
            goals_ko.append(feature.goal_ko)
            goals_en.append(feature.goal_en)
            purposes_ko.append(feature.purpose_ko)
            purposes_en.append(feature.purpose_en)
            semantic_signatures.append(_function_semantic_dimensions(function))
            if any(feature.name_ko not in str(alias) for alias in function["aliases"]["ko-KR"]) or any(
                feature.name_en.casefold() not in str(alias).casefold()
                for alias in function["aliases"]["en-US"]
            ):
                errors.append(f"{function_id}: terminal alias lacks its governed asset/state label")
            if function.get("classification") != feature.classification:
                errors.append(f"{function_id}: classification differs")
            if function.get("name_ko") != feature.name_ko or function.get("name_en") != feature.name_en:
                errors.append(f"{function_id}: bilingual name differs")
            if function.get("representative_goals") != {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}:
                errors.append(f"{function_id}: representative goal differs")
            if function.get("purpose_by_locale") != {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}:
                errors.append(f"{function_id}: terminal purpose differs")
            if (
                function.get("automation_policy") != "never_auto"
                or function.get("stop_policy") != "before_action"
                or function.get("risk_level") != "high"
                or function.get("user_owned_final_press") is not True
                or not function.get("risk_cues", {}).get("source_boundary")
            ):
                errors.append(f"{function_id}: terminal safety boundary differs")
            if set(function["source_refs"]) != set(DOMAIN_TERMINAL_SOURCE_IDS.get(function_id, ())):
                errors.append(f"{function_id}: terminal source mapping differs")
        elif (
            function.get("node_kind") != "hub"
            or function.get("automation_policy") != "safe_navigation"
            or function.get("stop_policy") != "continue"
            or function.get("state_changing") is not False
            or function.get("user_owned_final_press") is not False
            or function.get("fail_closed") is not True
            or function.get("resolution_policy") != "fail_closed"
            or function.get("requires_explicit_terminal_disambiguation") is not True
        ):
            errors.append(f"{function_id}: hub fail-closed policy differs")
    for label, values in (
        ("Korean representative goals", goals_ko),
        ("English representative goals", goals_en),
        ("Korean purposes", purposes_ko),
        ("English purposes", purposes_en),
    ):
        if _duplicates(values):
            errors.append(f"V19 contains duplicate {label}")
    if _duplicates(repr(value) for value in semantic_signatures):
        errors.append("V19 contains duplicate role/asset/state/jurisdiction terminal scopes")

    for intent in V19_INTENTS:
        target = str(intent["terminal_function"])
        feature = REVIEWED_FEATURE_BY_ID[target]
        if str(intent["intent_id"]) != f"v19_{target.replace('.', '_')}":
            errors.append(f"{target}: intent ID differs")
        if intent["patterns_by_locale"]["ko-KR"][0] != feature.goal_ko or intent["patterns_by_locale"]["en-US"][0] != feature.goal_en:
            errors.append(f"{target}: representative patterns differ")
        if any(not hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"]):
            errors.append(f"{target}: Korean goal pattern lacks Hangul")
        if len(intent["patterns_by_locale"]["ko-KR"]) < 5 or len(intent["patterns_by_locale"]["en-US"]) < 5:
            errors.append(f"{target}: insufficient independent bilingual patterns")
        gates = [rule for rule in intent["goal_rules"] if rule.get("rule_kind") == "v19_role_asset_state_jurisdiction_gate"]
        if len(gates) != 1 or gates[0].get("v19_required_dimension_count") != 4:
            errors.append(f"{target}: missing four-dimension gate")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != target:
            errors.append(f"{target}: route differs")
        if intent.get("terminal_condition") != {"stop_policy": "stop_before_action", "user_owned_final_press": True}:
            errors.append(f"{target}: terminal condition differs")
        gate = intent.get("resolution_gate", {})
        if gate.get("minimum_positive_dimensions") != 4 or gate.get("on_missing_dimension") != "fail_closed" or gate.get("fail_closed_to") != f"{target.split('.', 1)[0]}.hub":
            errors.append(f"{target}: fail-closed resolution gate differs")
        if target not in functions_by_id:
            errors.append(f"{target}: intent target missing")

    normalized_urls: set[str] = set()
    mapped_terminal_union: set[str] = set()
    referenced_source_ids: set[str] = set()
    per_domain_jurisdiction: Counter[tuple[str, str]] = Counter()
    for source_id, source in OFFICIAL_SOURCES.items():
        normalized = normalize_official_url(str(source.get("canonical_url", "")))
        if normalized in normalized_urls:
            errors.append(f"duplicate normalized V19 source URL: {normalized}")
        normalized_urls.add(normalized)
        record_without_hash = {key: value for key, value in source.items() if key != "source_record_sha256"}
        mapped = {str(value) for value in source.get("terminal_ids", [])}
        domain = str(source.get("domains", [""])[0])
        jurisdiction = str(source.get("jurisdiction", ""))
        per_domain_jurisdiction[(domain, "KR" if jurisdiction == "KR" else "NON_KR")] += 1
        if source.get("source_id") != source_id or source.get("normalized_url") != normalized:
            errors.append(f"source identity differs: {source_id}")
        if (
            source.get("verification_status") != "accepted"
            or source.get("evidence_level") != "official_primary"
            or source.get("http_status") != 200
            or source.get("verified_status") != 200
            or source.get("final_url") != source.get("canonical_url")
            or source.get("publisher") not in PUBLISHER_ALLOWLIST
            or source.get("provider_scope") != source.get("publisher")
            or source.get("source_record_sha256") != _source_digest(record_without_hash)
        ):
            errors.append(f"source verification or provider metadata differs: {source_id}")
        if not mapped or not mapped <= terminal_ids:
            errors.append(f"source has empty or invalid terminal mapping: {source_id}")
        mapped_terminal_union.update(mapped)
        for terminal_id in mapped:
            referenced_source_ids.add(source_id)
            if source_id not in DOMAIN_TERMINAL_SOURCE_IDS.get(terminal_id, ()):
                errors.append(f"source reverse mapping differs: {source_id} -> {terminal_id}")
    if len(OFFICIAL_SOURCES) != 73:
        errors.append(f"V19 requires exactly 73 direct official sources; got {len(OFFICIAL_SOURCES)}")
    research_urls = _research_direct_urls(source_text)
    if normalized_urls != research_urls:
        errors.append(
            f"V19 official registry differs from research URLs: registry={len(normalized_urls)}, research={len(research_urls)}"
        )
    if mapped_terminal_union != terminal_ids or set(DOMAIN_TERMINAL_SOURCE_IDS) != terminal_ids:
        errors.append("V19 official source-to-terminal mapping is incomplete")
    if referenced_source_ids != set(OFFICIAL_SOURCES):
        errors.append("V19 official registry has orphan or missing source records")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS:
        errors.append("V19 domain source registry differs")
    for domain in REQUIRED_DOMAINS:
        if per_domain_jurisdiction[(domain, "NON_KR")] < 5 or per_domain_jurisdiction[(domain, "KR")] < 1:
            errors.append(f"{domain}: requires at least five non-Korean and one Korean official lifecycle source")
    for terminal_id in KOREAN_TERMINAL_IDS:
        function = functions_by_id[terminal_id]
        terms = KOREAN_DOMAIN_TERMS[str(function["domain"])]
        if not any(
            term in str(alias) and str(function["name_ko"]) in str(alias)
            for term in terms
            for alias in function["aliases"]["ko-KR"]
        ):
            errors.append(f"{terminal_id}: lacks a scoped Korean provider-and-terminal alias")

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    actual_probe_counts = {
        "semantic": len(semantic),
        "collision": len(collisions),
        "recovery": len(recovery),
        "role_asset": len(isolation),
    }
    if actual_probe_counts != EXPECTED_PROBE_COUNTS:
        errors.append(f"V19 derived probe cardinality differs: {actual_probe_counts}")

    try:
        materialized = _materialization_state(base)
    except V19CatalogValidationError as error:
        errors.append(str(error))
        materialized = False
    try:
        pre_v19 = _pre_v19_payload(base)
    except V19CatalogValidationError as error:
        errors.append(str(error))
        pre_v19 = copy.deepcopy(base)
    del base
    if (
        pre_v19.get("catalog_version") != CATALOG_V18_VERSION
        or pre_v19.get("description") != CATALOG_V18_DESCRIPTION
        or len(pre_v19.get("functions", [])) != BASELINE_COUNTS["functions"]
        or len(pre_v19.get("intents", [])) != BASELINE_COUNTS["intents"]
        or len({str(item["domain"]) for item in pre_v19.get("functions", [])}) != BASELINE_COUNTS["domains"]
    ):
        errors.append("V19 base must be the exact prospective 215-domain V18 payload")
    base_function_ids = {str(item["function_id"]) for item in pre_v19.get("functions", [])}
    base_intent_ids = {str(item["intent_id"]) for item in pre_v19.get("intents", [])}
    base_domains = {str(item["domain"]) for item in pre_v19.get("functions", [])}
    if set(function_ids).intersection(base_function_ids) or set(intent_ids).intersection(base_intent_ids) or REQUIRED_DOMAINS.intersection(base_domains):
        errors.append("V19 IDs or domains collide with the V18-composed baseline")
    nearest_functions = {
        neighbor for values in NEAREST_EXISTING_FUNCTIONS.values() for neighbor in values
    }
    if not nearest_functions <= base_function_ids:
        errors.append(
            f"V19 nearest-function registry contains non-baseline IDs: {sorted(nearest_functions - base_function_ids)}"
        )
    avoid_roots = {domain.avoid_root for domain in REVIEWED_DOMAINS}
    if not avoid_roots <= base_function_ids:
        errors.append(f"V19 collision handoffs contain non-baseline roots: {sorted(avoid_roots - base_function_ids)}")
    expected_v18_functions = {str(item["function_id"]): item for item in V18_FUNCTIONS}
    expected_v18_intents = {str(item["intent_id"]): item for item in V18_INTENTS}
    present_v18_functions = {
        str(item["function_id"]): item
        for item in pre_v19.get("functions", [])
        if str(item["function_id"]) in expected_v18_functions
    }
    present_v18_intents = {
        str(item["intent_id"]): item
        for item in pre_v19.get("intents", [])
        if str(item["intent_id"]) in expected_v18_intents
    }
    if present_v18_functions != expected_v18_functions or present_v18_intents != expected_v18_intents:
        errors.append("prospective V18 layer differs before V19")

    try:
        localized_base = copy.deepcopy(pre_v19)
        localization_ledger = _apply_localization_corrections(localized_base)
        localized_functions = [*localized_base.get("functions", []), *copy.deepcopy(V19_FUNCTIONS)]
        non_hangul_ids = _non_hangul_name_ids(localized_functions)
        if non_hangul_ids != NON_HANGUL_NAME_KO_ALLOWLIST:
            errors.append(
                f"fully composed V19 Korean-name allowlist differs: {sorted(non_hangul_ids)}"
            )
        if len(localization_ledger["corrections"]) != 13:
            errors.append("V19 localization correction ledger count differs")
        del localized_base, localized_functions
    except V19CatalogValidationError as error:
        errors.append(str(error))
        localization_ledger = {}

    base_terminal_dimensions = [
        (str(item["function_id"]), _function_semantic_dimensions(item))
        for item in pre_v19.get("functions", [])
        if item.get("terminal")
    ]
    for function in V19_FUNCTIONS:
        if not function["terminal"]:
            continue
        dimensions = _function_semantic_dimensions(function)
        collisions_found = [
            base_id
            for base_id, base_dimensions in base_terminal_dimensions
            if dimensions == base_dimensions or _has_four_dimension_overlap(dimensions, base_dimensions)
        ]
        if collisions_found:
            errors.append(
                f"{function['function_id']}: duplicates baseline role/asset/state/jurisdiction scope {collisions_found[:3]}"
            )

    if errors:
        raise V19CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V19_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V19_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "domain_function_counts": dict(sorted(domain_function_counts.items())),
        "sensitive_reads": sensitive,
        "state_changing": consequential,
        "official_sources": len(OFFICIAL_SOURCES),
        "official_sources_sha256": OFFICIAL_SOURCES_SHA256,
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "korean_sources": sum(source["jurisdiction"] == "KR" for source in OFFICIAL_SOURCES.values()),
        "source_documents": copy.deepcopy(DOCUMENT_DIGESTS),
        "source_orphans": len(set(OFFICIAL_SOURCES) - referenced_source_ids),
        "layer_sha256": V19_LAYER_SHA256,
        "localization_corrections": len(localization_ledger.get("corrections", {})),
        "non_hangul_name_ko_allowlist": sorted(NON_HANGUL_NAME_KO_ALLOWLIST),
        "semantic_probes": len(semantic),
        "collision_probes": len(collisions),
        "recovery_probes": len(recovery),
        "role_asset_probes": len(isolation),
        "projected_counts": copy.deepcopy(PROJECTED_COUNTS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, non-mutating, idempotent V18+V19 copy."""

    stats = validate_v19_data(base_payload)
    if stats["materialized"]:
        return copy.deepcopy(dict(base_payload))
    merged = _pre_v19_payload(base_payload)
    localization_ledger = _apply_localization_corrections(merged)
    merged["catalog_version"] = CATALOG_V19_VERSION
    merged["description"] = CATALOG_V19_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V19_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V19_INTENTS)]
    merged["official_sources_v19"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_documents_v19"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    merged["korean_jurisdiction_v19"] = copy.deepcopy(_korean_metadata())
    merged["nearest_function_collisions_v19"] = {
        key: list(value) for key, value in sorted(NEAREST_EXISTING_FUNCTIONS.items())
    }
    merged["rejected_duplicate_families_v19"] = list(REJECTED_DUPLICATE_FAMILIES)
    merged["base_layer_seal_v19"] = copy.deepcopy(BASE_LAYER_SEAL)
    merged["localization_corrections_v19"] = localization_ledger
    merged["layer_integrity_v19"] = copy.deepcopy(_layer_integrity_metadata())
    return merged


def main() -> int:
    print(json.dumps(validate_v19_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
