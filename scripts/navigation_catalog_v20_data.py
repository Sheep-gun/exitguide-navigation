from __future__ import annotations

"""Research-isolated V20 catalog for claimant and family self-service cases.

The module composes only in memory on the exact V19 candidate payload.  It
adds eight evidence-backed domains, 128 terminals, and eight explicit
fail-closed hubs.  It never writes the canonical catalog or a runtime fixture.
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
from navigation_catalog_v17_data import V17_INTENTS
from navigation_catalog_v18_data import V18_INTENTS
from navigation_catalog_v19_data import (
    CATALOG_V19_DESCRIPTION,
    CATALOG_V19_VERSION,
    EXPECTED_V19_LAYER_SHA256,
    V19_FUNCTIONS,
    V19_INTENTS,
    V19_LAYER_SHA256,
    load_base_catalog as load_v18_source_base,
    merge_with_base as merge_v19_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V20_RESEARCH.md"
SOURCE_DOCUMENT_SHA256 = {
    DESIGN_SOURCE_RELATIVE_PATH: "b9fb9cfc3b0d6b8ca1120f5cc01624ee8f926687f4f86cc50301ca50f595296e",
}
SOURCE_DOCUMENT_METADATA = {
    path: {"path": path, "algorithm": "sha256", "sha256": digest}
    for path, digest in SOURCE_DOCUMENT_SHA256.items()
}
BASE_LAYER_SEAL = {
    "catalog_version": CATALOG_V19_VERSION,
    "algorithm": "sha256",
    "sha256": EXPECTED_V19_LAYER_SHA256,
}
EXPECTED_BASE_PAYLOAD_SHA256 = "e7d7d53145e1769a0320716014b9bfdc7ce8e700bed82f3aab606732ededd5b1"
BASE_PAYLOAD_SEAL = {
    "algorithm": "sha256",
    "sha256": EXPECTED_BASE_PAYLOAD_SHA256,
}

CATALOG_V20_VERSION = "20.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V20_DESCRIPTION = (
    "ExitGuide research-isolated V20 ontology for workers' compensation, paid "
    "family and medical leave, foster/adoption families, consumer bankruptcy, "
    "workplace protected leave and accommodation, long-term services and "
    "supports, child-care assistance, and special-education families; every "
    "terminal remains user-owned and stops before action."
)

BASELINE_COUNTS = {"domains": 224, "functions": 3733, "intents": 3482}
PROJECTED_COUNTS = {
    "domains": 232,
    "physical_functions": 3869,
    "physical_terminal_functions": 3610,
    "physical_intents": 3610,
}


class V20CatalogValidationError(ValueError):
    """Raised when V20 cannot be proven complete, isolated, and fail-closed."""


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
        raise V20CatalogValidationError(f"{key}: classification must be S or C")
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
            goal_ko=(
                f"{role_ko} 역할과 해당 기록의 제공자·관할을 확인하고 "
                f"{row.name_ko} 목적지까지 안내해 줘"
            ),
            goal_en=(
                f"As {row.roles[0]}, locate {row.name_en.lower()} for "
                f"{row.assets[0]} in {row.states[0]} state under {jurisdiction}"
            ),
            purpose_ko=(
                f"{row.name_ko}에 필요한 권한 역할·정확한 대상·현재 상태·제공자·관할을 "
                "모두 확인하고 사용자가 최종 동작을 직접 하기 전에 중단"
            ),
            purpose_en=(
                f"Verify authorized role, exact asset, lifecycle state, provider, and jurisdiction "
                f"for {row.name_en.lower()}, then stop before the user's final action"
            ),
            roles=row.roles,
            assets=row.assets,
            states=row.states,
            jurisdiction_guard=jurisdiction,
            safety_boundary=(
                f"{row.name_en}: {boundary}; do not infer eligibility, facts, consent, advice, "
                "or authority; stop before any final disclosure, upload, submission, payment, "
                "selection, schedule change, certification, complaint, or appeal"
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


# The exact eight-domain/128-terminal research scope.  Every row keeps an
# independently identifiable actor, governed asset, state, and source seam.
REVIEWED_DOMAINS: tuple[DomainSpec, ...] = (
    D(
        "workers_compensation_claimant_services",
        "산재보상 청구인 서비스",
        "Workers compensation claimant services",
        "산재 근로자·유족 또는 권한 있는 청구 대리인",
        "identified compensation agency or insurer, statutory system, claimant case, and governing jurisdiction",
        "claimant-facing statutory injury case only; exclude adjuster, employer, regulator, and provider decisions",
        "insurance.hub",
        "산재 청구|업무상 재해|임금대체|치료승인|claimant|work injury|wage replacement|treatment authorization",
        "insurance.claim.entry|insurance.claim.documents|insurance.claim.status|insurance_claims_adjuster_ops.claim_queue|insurance_claims_adjuster_ops.coverage_decision|occupational_safety_case_ops.incident_reporting_queue",
        "injured worker|survivor or dependent claimant|authorized claimant representative",
        "statutory workplace-injury claim|accepted conditions|treatment authorization|wage-replacement benefit|return-to-work plan|rehabilitation request|appeal",
        "notice preparation|claim pending|decision issued|treatment pending|payment issued|return planning|rehabilitation requested|appeal available",
        (
            R("agency_insurer_lookup", "S", "관할 산재기관·보험자 찾기", "Compensation agency or insurer lookup", "injured worker|authorized claimant representative", "governing compensation agency or insurer", "jurisdiction not yet selected|provider lookup", "overview|agency"),
            R("injury_notice_prepare", "C", "업무상 재해 통지 준비", "Work injury notice preparation", "injured worker|survivor claimant", "workplace injury notice", "injury identified|notice not filed", "overview|notice|claim"),
            R("claim_form_start", "C", "산재 청구서 작성 시작", "Workers compensation claim form start", "injured worker|survivor claimant", "statutory workplace-injury claim form", "claim not filed|form ready", "overview|claim|form"),
            R("claim_document_upload", "C", "산재 청구 증빙 업로드", "Workers compensation claim document upload", "authorized claimant|claimant representative", "supporting evidence for one injury claim", "claim open|evidence requested", "overview|claim|document"),
            R("claim_status", "S", "산재 청구 진행상태", "Workers compensation claim status", "authorized claimant|claimant representative", "identified workplace-injury claim", "claim filed|claim pending", "overview|claim|status"),
            R("compensability_decision_review", "S", "산재 인정 결정 검토", "Compensability decision review", "authorized claimant|survivor claimant", "agency compensability decision", "decision issued|review available", "overview|decision|appeal"),
            R("medical_provider_lookup", "S", "승인 의료기관 찾기", "Authorized medical provider lookup", "injured worker with an identified case", "authorized treatment provider directory", "treatment needed|provider not selected", "overview|medical|provider"),
            R("treatment_authorization_status", "S", "치료 승인 상태", "Treatment authorization status", "injured worker|authorized claimant representative", "treatment authorization request", "authorization pending|authorization issued", "overview|medical|authorization"),
            R("wage_replacement_payment_status", "S", "휴업급여·임금대체 지급상태", "Wage replacement payment status", "eligible claimant with an accepted case", "statutory wage-replacement payment", "benefit approved|payment pending", "overview|benefit|payment"),
            R("benefit_payment_method_update", "C", "산재급여 지급계좌 변경", "Benefit payment method update", "authorized benefit recipient", "benefit payment destination", "benefit active|payment method change ready", "overview|benefit|payment"),
            R("independent_medical_exam_status", "S", "독립 의료검사 일정·상태", "Independent medical examination status", "injured worker with scheduled examination", "independent medical examination record", "exam requested|exam scheduled", "overview|medical|exam"),
            R("return_to_work_plan_review", "S", "직장 복귀 계획 검토", "Return-to-work plan review", "injured worker with an active claim", "return-to-work plan", "work restrictions recorded|plan proposed", "overview|return|rehabilitation"),
            R("vocational_rehabilitation_request", "C", "직업재활 지원 요청", "Vocational rehabilitation request", "injured worker with an active claim", "vocational rehabilitation service request", "rehabilitation need identified|request ready", "overview|rehabilitation|return"),
            R("mileage_expense_reimbursement", "C", "치료 교통비·경비 상환 청구", "Mileage and expense reimbursement", "injured worker|authorized claimant representative", "claim-related travel or treatment expense", "expense incurred|reimbursement ready", "overview|reimbursement|medical"),
            R("claim_dispute_appeal", "C", "산재 결정 이의·심사 청구", "Workers compensation dispute or appeal", "authorized claimant|survivor claimant", "identified compensability or benefit decision", "adverse decision issued|appeal window open", "overview|decision|appeal"),
        ),
    ),
    D(
        "paid_family_medical_leave_claimant_services",
        "유급 가족·의료휴가 급여 서비스",
        "Paid family and medical leave claimant services",
        "유급휴가 급여 청구 근로자 또는 권한 있는 대리인",
        "named public paid-leave program or approved private-plan administrator, claim year, employer coverage, and jurisdiction",
        "claimant wage-replacement benefit only; exclude routine PTO, employer approval, unemployment, and private disability claims",
        "hr_payroll.hub",
        "육아휴직 급여|가족돌봄 급여|의료휴가 급여|주간 인증|paid leave|bonding benefit|weekly claim|leave benefit",
        "hr_payroll.leave_request|hr_payroll.leave_balance|unemployment_insurance_case_services.initial_claim_start|unemployment_insurance_case_services.weekly_certification_submit|insurance.claim.entry",
        "paid-leave claimant worker|authorized claimant representative",
        "public paid-leave benefit claim|supporting certification|approved leave period|weekly benefit claim|benefit payment|leave change report|appeal",
        "coverage review|application ready|verification pending|decision issued|weekly claim due|payment pending|leave changing|appeal available",
        (
            R("program_coverage_review", "S", "유급휴가 급여 프로그램 적용범위", "Paid-leave program coverage review", "worker considering a paid-leave claim", "named paid-leave program coverage", "coverage unknown|program review", "overview|coverage"),
            R("qualifying_leave_reason_review", "S", "급여 대상 휴가사유 안내", "Qualifying paid-leave reason review", "worker considering a paid-leave claim", "program-defined leave reason information", "reason not selected|information review", "overview|coverage|reason"),
            R("employer_notice_prepare", "C", "유급휴가 사용 통지 준비", "Paid-leave employer notice preparation", "worker preparing required notice", "employee notice for a paid-leave period", "leave anticipated|notice not sent", "overview|notice|application"),
            R("benefit_claim_start", "C", "유급휴가 급여 청구 시작", "Paid-leave benefit claim start", "paid-leave claimant worker", "public wage-replacement benefit claim", "claim not filed|application ready", "overview|application|claim"),
            R("identity_verification", "C", "유급휴가 청구 본인확인", "Paid-leave claimant identity verification", "paid-leave claimant worker", "identity verification for one benefit claim", "verification required|claim pending", "overview|verification|application"),
            R("wage_employment_record_review", "S", "임금·고용기록 검토", "Wage and employment record review", "paid-leave claimant worker", "wage and employment record used by the claim", "record received|review available", "overview|wage|claim"),
            R("supporting_certification_upload", "C", "휴가 증명서류 업로드", "Paid-leave supporting certification upload", "authorized paid-leave claimant", "supporting certification for one paid-leave claim", "certification requested|upload ready", "overview|certification|document"),
            R("claim_status", "S", "유급휴가 급여 청구상태", "Paid-leave benefit claim status", "authorized paid-leave claimant", "identified paid-leave benefit claim", "claim filed|decision pending", "overview|claim|status"),
            R("eligibility_decision_review", "S", "유급휴가 급여 결정 검토", "Paid-leave eligibility decision review", "authorized paid-leave claimant", "program benefit determination", "decision issued|review available", "overview|decision|appeal"),
            R("weekly_claim_certification", "C", "유급휴가 주간급여 인증", "Paid-leave weekly claim certification", "approved paid-leave claimant", "weekly benefit certification", "benefit period active|weekly claim due", "overview|weekly|certification"),
            R("benefit_payment_status", "S", "유급휴가 급여 지급상태", "Paid-leave benefit payment status", "approved paid-leave claimant", "paid-leave wage-replacement payment", "payment calculated|payment pending", "overview|payment|status"),
            R("intermittent_leave_schedule", "C", "간헐적 휴가 일정 제출", "Intermittent paid-leave schedule", "approved paid-leave claimant", "intermittent paid-leave schedule", "intermittent leave approved|schedule ready", "overview|schedule|change"),
            R("leave_period_change_report", "C", "유급휴가 기간변경 신고", "Paid-leave period change report", "approved paid-leave claimant", "approved leave-period change", "leave active|period changed", "overview|change|report"),
            R("return_to_work_date_update", "C", "복직일 변경 등록", "Return-to-work date update", "approved paid-leave claimant", "return-to-work date in a paid-leave claim", "return date changed|update ready", "overview|return|change"),
            R("determination_appeal_request", "C", "유급휴가 급여 결정 이의신청", "Paid-leave determination appeal request", "authorized paid-leave claimant", "identified adverse benefit determination", "adverse decision issued|appeal window open", "overview|decision|appeal"),
        ),
    ),
    D(
        "foster_adoption_family_services",
        "위탁·입양가정 서비스",
        "Foster and adoption family services",
        "예비·승인 위탁부모, 입양부모, 친족보호자 또는 권한 있는 가족대표",
        "named public child-welfare agency or authorized provider, family case, placement jurisdiction, and interstate branch",
        "family-facing inquiry and case only; exclude caseworker approval, child assignment, scoring, and best-interest decisions",
        "social_services_casework.hub",
        "위탁가정|입양가정|가정조사|배치상태|resource family|home study|placement|adoption assistance",
        "social_services_casework.referral_intake|social_services_casework.home_visit_plan|social_services_casework.care_plan_create_update|social_services_casework.benefit_eligibility_decision|family_caregiving.care_recipient_switch",
        "prospective foster or adoptive parent|approved resource parent|kin caregiver|authorized adult family representative",
        "family application|background check|training|home study|approval record|authorized match inquiry|placement record|caregiver payment|adoption assistance|post-placement support",
        "inquiry|application pending|home study pending|approved|matching|placed|finalization pending|post-adoption support",
        (
            R("agency_provider_lookup", "S", "위탁·입양 담당기관 찾기", "Foster or adoption agency lookup", "prospective resource parent|authorized family representative", "authorized foster or adoption provider", "provider not selected|agency lookup", "overview|agency"),
            R("orientation_registration", "C", "위탁·입양 설명회 등록", "Foster or adoption orientation registration", "prospective resource parent|prospective adoptive parent", "family orientation registration", "inquiry complete|orientation available", "overview|orientation|application"),
            R("family_application_start", "C", "위탁·입양가정 신청 시작", "Foster or adoption family application start", "prospective resource parent|prospective adoptive parent", "resource-family or adoption application", "orientation complete|application ready", "overview|application"),
            R("background_check_status", "S", "가정 구성원 신원조회 상태", "Family background check status", "applicant family adult|authorized family representative", "applicant household background-check task", "check requested|result pending", "overview|background|status"),
            R("home_study_document_upload", "C", "가정조사 서류 업로드", "Home study document upload", "applicant family adult|authorized family representative", "home-study supporting document", "home study open|document requested", "overview|home_study|document"),
            R("home_study_status", "S", "가정조사 진행상태", "Home study status", "applicant family adult|authorized family representative", "identified family home study", "home study scheduled|review pending", "overview|home_study|status"),
            R("training_requirement_status", "S", "위탁·입양 교육이수 상태", "Caregiver training requirement status", "applicant resource parent|applicant adoptive parent", "required caregiver training record", "training assigned|completion pending", "overview|training|status"),
            R("caregiver_approval_status", "S", "위탁·입양가정 승인상태", "Caregiver approval status", "applicant resource parent|applicant adoptive parent", "family approval record", "assessment complete|approval pending", "overview|approval|status"),
            R("child_match_profile_review", "S", "권한 있는 아동 매칭정보 검토", "Authorized child match profile review", "approved resource parent|approved adoptive parent", "agency-authorized child match profile", "family approved|profile access authorized", "overview|match|profile"),
            R("match_inquiry_submit", "C", "아동 매칭 문의 제출", "Authorized match inquiry submission", "approved resource parent|approved adoptive parent", "inquiry for one authorized match profile", "profile reviewed|inquiry ready", "overview|match|inquiry"),
            R("placement_transition_plan", "S", "배치 전환계획 검토", "Placement transition plan review", "approved caregiver with an identified placement", "authorized placement transition plan", "match accepted by agency|transition planned", "overview|placement|plan"),
            R("placement_status", "S", "위탁·입양 배치상태", "Foster or adoption placement status", "approved caregiver|authorized family representative", "identified placement record", "placement planned|placement active", "overview|placement|status"),
            R("caregiver_maintenance_payment_status", "S", "위탁가정 양육비 지급상태", "Caregiver maintenance payment status", "approved foster or kin caregiver", "caregiver maintenance payment", "placement active|payment pending", "overview|payment|status"),
            R("adoption_assistance_application", "C", "입양지원금 신청", "Adoption assistance application", "approved prospective adoptive parent|authorized family representative", "adoption-assistance request", "placement eligible|application ready", "overview|assistance|application"),
            R("post_placement_report_submit", "C", "배치 후 가족보고 제출", "Post-placement family report submission", "placed caregiver|authorized family representative", "family-authored post-placement report", "placement active|report due", "overview|placement|report"),
            R("adoption_finalization_status", "S", "입양 확정 진행상태", "Adoption finalization status", "prospective adoptive parent|authorized family representative", "identified adoption finalization record", "post-placement period complete|finalization pending", "overview|finalization|status"),
            R("post_adoption_support_request", "C", "입양 후 가족지원 요청", "Post-adoption support request", "adoptive parent|authorized family representative", "post-adoption family-support request", "adoption finalized|support needed", "overview|support|request"),
        ),
    ),
    D(
        "consumer_bankruptcy_case_services",
        "개인 파산·면책 사건 서비스",
        "Consumer bankruptcy case services",
        "본인 사건의 개인채무자·공동채무자 또는 권한 있는 대리인",
        "identified bankruptcy court, district or country, user-selected chapter, debtor case, and official trustee system",
        "debtor self-service only; exclude chapter recommendation, legal advice, trustee, clerk, creditor, and attorney actions",
        "court_litigant_self_service.hub",
        "개인파산|면책|채무자교육|파산사건|bankruptcy|debtor education|discharge|trustee",
        "consumer_debt_collection_services.validation_notice|consumer_debt_collection_services.dispute_submission|court_litigant_self_service.filing_prepare|court_litigant_self_service.filing_submit|court_litigant_self_service.case_docket_view|court_clerk_case_admin.filing_docket_entry",
        "individual pro se debtor|joint debtor|authorized debtor representative",
        "credit-counseling certificate|means-test inputs|petition packet|filing fee request|bankruptcy docket|trustee assignment|creditor meeting|claims register|debtor-education certificate|amendment|discharge",
        "pre-filing information|counseling complete|petition ready|case open|meeting scheduled|education due|discharge pending|case closed",
        (
            R("court_jurisdiction_lookup", "S", "파산 관할법원 찾기", "Bankruptcy court jurisdiction lookup", "prospective pro se debtor|authorized debtor representative", "bankruptcy court and district", "court not selected|jurisdiction lookup", "overview|court|jurisdiction"),
            R("bankruptcy_chapter_information", "S", "파산절차 유형 정보", "Bankruptcy chapter information", "prospective individual debtor", "official chapter information", "chapter not chosen|information review", "overview|chapter|information"),
            R("approved_credit_counseling_lookup", "S", "승인 신용상담기관 찾기", "Approved credit counseling lookup", "prospective individual debtor", "approved pre-filing counseling provider", "counseling not complete|provider lookup", "overview|counseling|provider"),
            R("means_test_form_review", "S", "자산·소득 심사양식 검토", "Bankruptcy means-test form review", "prospective individual debtor|joint debtor", "official means-test form and instructions", "chapter chosen by user|form review", "overview|means_test|form"),
            R("petition_form_packet", "S", "개인파산 신청서 묶음", "Individual bankruptcy petition packet", "prospective individual debtor|joint debtor", "official individual petition form packet", "chapter chosen by user|forms available", "overview|petition|form"),
            R("petition_document_upload", "C", "개인파산 신청서류 업로드", "Bankruptcy petition document upload", "pro se debtor|joint debtor", "prepared petition document set", "forms prepared|upload ready", "overview|petition|document"),
            R("petition_submit", "C", "개인파산 신청 최종제출", "Bankruptcy petition submission", "pro se debtor|joint debtor", "prepared individual bankruptcy petition", "petition complete|submission ready", "overview|petition|submit"),
            R("filing_fee_option_request", "C", "파산 접수비 납부방식 신청", "Bankruptcy filing fee option request", "pro se debtor|joint debtor", "installment or waiver request for filing fee", "petition ready|fee option available", "overview|fee|request"),
            R("case_number_docket_view", "S", "파산 사건번호·기록 조회", "Bankruptcy case number and docket view", "debtor in an open case|authorized debtor representative", "identified bankruptcy case docket", "case opened|docket available", "overview|case|docket"),
            R("trustee_assignment_view", "S", "파산관재인 배정 조회", "Bankruptcy trustee assignment view", "debtor in an open case|authorized debtor representative", "trustee assignment for one bankruptcy case", "case opened|trustee assigned", "overview|trustee|case"),
            R("creditor_meeting_schedule", "S", "채권자집회 일정 조회", "Creditor meeting schedule", "debtor in an open case|authorized debtor representative", "creditor meeting for one bankruptcy case", "trustee assigned|meeting scheduled", "overview|meeting|schedule"),
            R("claims_register_view", "S", "파산 채권신고 목록 조회", "Bankruptcy claims register view", "debtor in an open case|authorized debtor representative", "claims register for one bankruptcy case", "claims filed|register available", "overview|claims|case"),
            R("debtor_education_certificate_upload", "C", "채무자교육 수료증 업로드", "Debtor education certificate upload", "debtor in an open case|joint debtor", "post-filing debtor-education certificate", "course complete|certificate due", "overview|education|document"),
            R("amendment_prepare", "C", "파산 신청서 정정 준비", "Bankruptcy amendment preparation", "debtor in an open case|joint debtor", "amendment to identified petition schedules", "case open|correction identified", "overview|amendment|form"),
            R("reaffirmation_agreement_review", "S", "채무 재확약 합의서 검토", "Reaffirmation agreement review", "debtor in an open case|joint debtor", "filed reaffirmation agreement", "agreement presented|court review pending", "overview|agreement|review"),
            R("discharge_status", "S", "파산 면책 결정상태", "Bankruptcy discharge status", "debtor in an open case|authorized debtor representative", "discharge record for one bankruptcy case", "education complete|discharge pending", "overview|discharge|status"),
            R("case_closure_status", "S", "파산사건 종결상태", "Bankruptcy case closure status", "debtor|authorized debtor representative", "identified bankruptcy case closure record", "discharge issued or case dismissed|closure pending", "overview|closure|status"),
        ),
    ),
    D(
        "workplace_leave_accommodation_services",
        "직장 보호휴가·편의제공 서비스",
        "Workplace protected leave and accommodation services",
        "본인의 보호휴가·장애편의 사건을 관리하는 근로자·구직자 또는 권한 있는 대리인",
        "identified employer or authorized administrator, employment jurisdiction, protected-leave or accommodation case, and governing law",
        "employee or applicant case only; exclude manager approval, enforcement findings, housing accommodation, and paid-benefit claims",
        "hr_payroll.hub",
        "보호휴가|의료증명|장애인 편의|복직확인|protected leave|medical certification|reasonable accommodation|interactive process",
        "hr_payroll.leave_request|hr_payroll.leave_balance|hr_payroll.manager_approvals|wage_hour_enforcement_ops.worker_complaint_submit|wage_hour_enforcement_ops.fmla_finding_record|public_housing_assistance_services.reasonable_accommodation_request|jury_summons_response_services.accommodation_request",
        "employee managing own protected-leave case|job applicant requesting own accommodation|authorized employee representative",
        "protected-leave request|eligibility and designation notice|medical certification|intermittent schedule|accommodation request|interactive-process record|implementation record|return-to-work release",
        "request preparation|notice issued|certification due|leave designated|interactive process active|decision issued|implementation active|return pending",
        (
            R("protected_leave_coverage_review", "S", "보호휴가 적용범위 검토", "Protected-leave coverage review", "employee considering statutory protected leave", "named protected-leave coverage record", "coverage unknown|information review", "overview|leave|coverage"),
            R("protected_leave_request_start", "C", "직장 보호휴가 요청 시작", "Protected-leave request start", "employee requesting own protected leave", "employee protected-leave request", "leave needed|request ready", "overview|leave|request"),
            R("eligibility_notice_review", "S", "보호휴가 자격통지 검토", "Protected-leave eligibility notice review", "employee with a leave case", "employer-issued eligibility notice", "notice issued|review available", "overview|leave|notice"),
            R("rights_responsibilities_notice_review", "S", "보호휴가 권리·책임통지 검토", "Rights and responsibilities notice review", "employee with a leave case", "rights and responsibilities notice", "notice issued|requirements visible", "overview|leave|notice"),
            R("medical_certification_request", "C", "보호휴가 의료증명 요청", "Protected-leave medical certification request", "employee with a leave case", "medical-certification request record", "certification required|request ready", "overview|leave|certification"),
            R("medical_certification_upload", "C", "보호휴가 의료증명 업로드", "Protected-leave medical certification upload", "employee with a leave case|authorized representative", "medical certification for one leave case", "certification obtained|upload ready", "overview|leave|certification|document"),
            R("leave_designation_notice_review", "S", "보호휴가 지정통지 검토", "Protected-leave designation notice review", "employee with a leave case", "employer leave-designation notice", "designation issued|review available", "overview|leave|designation"),
            R("protected_leave_case_status", "S", "보호휴가 사건상태", "Protected-leave case status", "employee with a leave case|authorized representative", "identified protected-leave case", "request filed|case active", "overview|leave|status"),
            R("intermittent_leave_schedule_review", "S", "간헐적 보호휴가 일정 검토", "Intermittent protected-leave schedule review", "employee with designated intermittent leave", "approved intermittent-leave schedule", "leave designated|schedule available", "overview|leave|schedule"),
            R("recertification_request_review", "S", "보호휴가 재증명 요청 검토", "Protected-leave recertification request review", "employee with an active leave case", "recertification request for one leave case", "recertification requested|response pending", "overview|leave|recertification"),
            R("accommodation_request_start", "C", "직장 편의제공 요청 시작", "Workplace accommodation request start", "employee or job applicant requesting own accommodation", "individual workplace accommodation request", "limitation disclosed by user|request ready", "overview|accommodation|request"),
            R("accommodation_document_upload", "C", "편의제공 증빙 업로드", "Accommodation document upload", "employee or job applicant|authorized representative", "supporting document for one accommodation request", "document requested|upload ready", "overview|accommodation|document"),
            R("interactive_process_status", "S", "직장 편의 협의절차 상태", "Accommodation interactive-process status", "employee or job applicant with a request", "interactive-process record", "request filed|interactive process active", "overview|accommodation|status"),
            R("accommodation_decision_review", "S", "직장 편의제공 결정 검토", "Accommodation decision review", "employee or job applicant with a request", "employer accommodation decision", "decision issued|review available", "overview|accommodation|decision"),
            R("accommodation_implementation_review", "S", "직장 편의제공 이행상태", "Accommodation implementation review", "employee with an approved accommodation", "approved accommodation implementation record", "accommodation approved|implementation active", "overview|accommodation|implementation"),
            R("return_to_work_release_upload", "C", "보호휴가 복직확인서 업로드", "Return-to-work release upload", "employee returning from protected leave", "return-to-work release for one leave case", "return approaching|release requested", "overview|leave|return|document"),
        ),
    ),
    D(
        "long_term_services_supports_case_services",
        "장기요양·지역사회 지원 서비스",
        "Long-term services and supports case services",
        "본인의 장기요양·지역사회 지원을 신청·이용하는 당사자 또는 권한 있는 가족·법정대리인",
        "named LTSS or HCBS agency or plan, residence, program authority, participant case, and service-setting branch",
        "participant case only; exclude cash disability, general health coverage, informal family coordination, and caseworker-authored plans",
        "public_health_coverage_case_services.hub",
        "장기요양|재가서비스|기능평가|서비스 승인|LTSS|HCBS|functional assessment|service authorization",
        "social_security_benefit_services.disability_application_start|social_security_benefit_services.application_status|public_health_coverage_case_services.application_start|public_health_coverage_case_services.managed_plan_select|family_caregiving.care_calendar|social_services_casework.care_plan_create_update",
        "LTSS applicant or participant|authorized family or legal representative|authorized caregiver for the named case",
        "LTSS application|functional assessment|waiver waitlist|eligibility notice|person-centered service plan|provider choice|service authorization|changed-need report|reassessment|hearing",
        "pathway review|application pending|assessment scheduled|waitlisted|eligible|plan active|services authorized|needs changed|renewal due|appeal available",
        (
            R("program_pathway_review", "S", "장기요양 지원경로 검토", "LTSS program pathway review", "LTSS applicant|authorized representative", "available LTSS or HCBS program pathway", "pathway unknown|program review", "overview|program|pathway"),
            R("administering_agency_lookup", "S", "장기요양 담당기관 찾기", "LTSS administering agency lookup", "LTSS applicant|authorized representative", "administering LTSS agency or plan", "provider not selected|agency lookup", "overview|agency|program"),
            R("application_start", "C", "장기요양 지원 신청 시작", "LTSS application start", "LTSS applicant|authorized representative", "named LTSS application", "program selected|application ready", "overview|application"),
            R("application_status", "S", "장기요양 신청상태", "LTSS application status", "LTSS applicant|authorized representative", "identified LTSS application", "application filed|review pending", "overview|application|status"),
            R("functional_assessment_schedule", "C", "장기요양 기능평가 일정 신청", "Functional assessment scheduling", "LTSS applicant|authorized representative", "functional or level-of-care assessment appointment", "application accepted|assessment due", "overview|assessment|schedule"),
            R("assessment_result_review", "S", "장기요양 기능평가 결과", "Functional assessment result review", "LTSS applicant|authorized representative", "functional assessment result", "assessment complete|result issued", "overview|assessment|result"),
            R("waiver_waitlist_status", "S", "지역사회 지원 대기명단 상태", "HCBS waiver waitlist status", "LTSS applicant|authorized representative", "named waiver waitlist record", "assessment complete|waitlisted", "overview|waitlist|status"),
            R("eligibility_notice_review", "S", "장기요양 자격통지 검토", "LTSS eligibility notice review", "LTSS applicant|authorized representative", "program eligibility notice", "decision issued|review available", "overview|eligibility|notice"),
            R("person_centered_service_plan_review", "S", "당사자 중심 서비스계획 검토", "Person-centered service plan review", "LTSS participant|authorized representative", "participant's person-centered service plan", "eligible|plan drafted", "overview|plan|service"),
            R("service_provider_compare", "S", "승인 장기요양기관 비교", "Authorized service provider comparison", "LTSS participant|authorized representative", "authorized provider directory for approved services", "service approved|provider not selected", "overview|provider|service"),
            R("provider_selection_submit", "C", "장기요양 제공기관 선택 제출", "LTSS provider selection submission", "LTSS participant|authorized representative", "provider selection for authorized services", "provider compared|selection ready", "overview|provider|selection"),
            R("service_authorization_status", "S", "장기요양 서비스 승인상태", "LTSS service authorization status", "LTSS participant|authorized representative", "service authorization record", "plan approved|authorization pending", "overview|authorization|status"),
            R("authorized_service_schedule", "S", "승인 서비스 일정 조회", "Authorized LTSS service schedule", "LTSS participant|authorized representative", "schedule for authorized LTSS services", "services authorized|schedule active", "overview|service|schedule"),
            R("change_in_need_report", "C", "장기요양 필요변화 신고", "LTSS change-in-need report", "LTSS participant|authorized representative", "changed-need report for one LTSS case", "needs changed|report ready", "overview|change|report"),
            R("renewal_reassessment", "C", "장기요양 갱신·재평가 신청", "LTSS renewal or reassessment", "LTSS participant|authorized representative", "renewal or reassessment request", "authorization expiring|reassessment due", "overview|renewal|assessment"),
            R("fair_hearing_request", "C", "장기요양 공정심리 요청", "LTSS fair-hearing request", "LTSS applicant or participant|authorized representative", "identified adverse LTSS decision", "adverse notice issued|hearing window open", "overview|appeal|hearing"),
        ),
    ),
    D(
        "child_care_assistance_case_services",
        "공공 보육료 지원 서비스",
        "Child-care assistance case services",
        "공공 보육료 지원을 신청·관리하는 부모·보호자 또는 권한 있는 가구대표",
        "named state, territory, tribal, or Korean assistance agency, household case, child, service period, and provider branch",
        "family subsidy case only; exclude provider billing, check-in, school enrollment, nutrition benefits, and caseworker decisions",
        "childcare_family_portal.hub",
        "보육료 지원|어린이집 바우처|지원 대기명단|보육기관 선택|child-care subsidy|voucher|funding waitlist|provider selection",
        "childcare_family_portal.billing_balance|childcare_family_portal.attendance_history|childcare_family_portal.child_checkin|school_family_enrollment.registration_submission|nutrition_assistance_case_services.application_start|social_services_casework.benefit_eligibility_decision",
        "parent or guardian applicant|authorized household representative",
        "child-care subsidy application|identity and income evidence|household facts|funding waitlist|eligibility notice|authorization certificate|authorized provider|care schedule|copayment|recertification|appeal",
        "program review|application pending|verification due|waitlisted|authorized|provider selection|assistance active|recertification due|appeal available",
        (
            R("program_eligibility_review", "S", "보육료 지원 프로그램 안내", "Child-care assistance program review", "parent or guardian applicant|authorized household representative", "named child-care assistance program", "program unknown|information review", "overview|program|eligibility"),
            R("administering_agency_lookup", "S", "보육료 지원기관 찾기", "Child-care assistance agency lookup", "parent or guardian applicant|authorized household representative", "administering child-care assistance agency", "agency not selected|provider lookup", "overview|agency|program"),
            R("application_start", "C", "보육료 지원 신청 시작", "Child-care assistance application start", "parent or guardian applicant|authorized household representative", "household child-care subsidy application", "program selected|application ready", "overview|application"),
            R("application_status", "S", "보육료 지원 신청상태", "Child-care assistance application status", "parent or guardian applicant|authorized household representative", "identified child-care assistance application", "application filed|review pending", "overview|application|status"),
            R("identity_income_document_upload", "C", "보육료 지원 소득·본인서류 업로드", "Child-care assistance evidence upload", "parent or guardian applicant|authorized household representative", "identity or income evidence for one subsidy case", "verification requested|upload ready", "overview|document|verification"),
            R("child_household_change_report", "C", "보육료 지원 아동·가구변경 신고", "Child or household change report", "authorized household representative", "child or household facts in one subsidy case", "assistance active|household changed", "overview|change|report"),
            R("provider_search", "S", "지원가능 보육기관 찾기", "Authorized child-care provider search", "parent or guardian applicant|authorized household representative", "eligible provider directory for the subsidy", "assistance offered|provider not selected", "overview|provider|search"),
            R("provider_selection_submit", "C", "보육기관 선택 제출", "Child-care provider selection submission", "parent or guardian applicant|authorized household representative", "provider selection for one subsidy authorization", "provider reviewed|selection ready", "overview|provider|selection"),
            R("eligibility_notice_review", "S", "보육료 지원 결정통지 검토", "Child-care eligibility notice review", "parent or guardian applicant|authorized household representative", "child-care assistance eligibility notice", "decision issued|review available", "overview|eligibility|notice"),
            R("authorization_certificate_status", "S", "보육료 지원승인서 상태", "Child-care authorization certificate status", "authorized household representative", "subsidy authorization or certificate", "eligible|authorization pending", "overview|authorization|status"),
            R("copayment_review", "S", "보육료 본인부담금 검토", "Child-care copayment review", "authorized household representative", "program-calculated household copayment", "assistance authorized|copayment issued", "overview|copayment|payment"),
            R("authorized_care_schedule_review", "S", "승인 보육일정 검토", "Authorized child-care schedule review", "authorized household representative", "authorized care schedule for one child", "provider selected|schedule authorized", "overview|schedule|authorization"),
            R("funding_waitlist_status", "S", "보육료 예산 대기명단 상태", "Child-care funding waitlist status", "parent or guardian applicant|authorized household representative", "funding waitlist record", "application reviewed|funding waitlisted", "overview|waitlist|status"),
            R("recertification_due", "S", "보육료 지원 재인증 기한", "Child-care recertification due", "authorized household representative", "recertification deadline for one subsidy case", "assistance active|recertification approaching", "overview|recertification|due"),
            R("recertification_submit", "C", "보육료 지원 재인증 제출", "Child-care recertification submission", "authorized household representative", "prepared subsidy recertification", "recertification due|submission ready", "overview|recertification|submit"),
            R("benefit_change_appeal", "C", "보육료 지원변경 이의신청", "Child-care benefit change appeal", "parent or guardian applicant|authorized household representative", "identified adverse subsidy decision", "benefit changed or denied|appeal window open", "overview|appeal|decision"),
        ),
    ),
    D(
        "special_education_family_services",
        "특수교육 학생·가족 서비스",
        "Special-education family services",
        "권리가 이전된 학생, 부모·보호자·대리부모 또는 권한 있는 가족대표",
        "identified student, school district or education authority, school year, transferred-rights status, and governing jurisdiction",
        "student and family participation only; exclude administrator eligibility, placement, IEP authorization, and program administration",
        "special_education_program_admin.hub",
        "특수교육|평가동의|개별화교육계획|학부모 참여|special education|evaluation consent|IEP|parent participation",
        "special_education_program_admin.referral_intake|special_education_program_admin.evaluation_consent_request|special_education_program_admin.eligibility_determination_record|special_education_program_admin.iep_draft_update|special_education_program_admin.iep_implementation_authorize|school_family_enrollment.registration_submission",
        "student with transferred rights|parent or guardian|surrogate parent|authorized family representative",
        "child-find referral|evaluation request and consent|evaluation record|IEP meeting|current IEP|progress report|reevaluation|transition plan|prior written notice|mediation or complaint handoff",
        "concern identified|referral ready|evaluation pending|eligibility issued|IEP active|progress available|reevaluation due|transition active|notice issued|dispute available",
        (
            R("child_find_referral_information", "S", "특수교육 의뢰·아동찾기 안내", "Child-find referral information", "parent or guardian|student with transferred rights", "child-find or special-education referral information", "concern identified|information review", "overview|referral|information"),
            R("evaluation_request_prepare", "C", "특수교육 평가요청 준비", "Special-education evaluation request preparation", "parent or guardian|student with transferred rights", "family-authored evaluation request", "concern identified|request ready", "overview|evaluation|request"),
            R("evaluation_consent_review", "S", "특수교육 평가동의서 검토", "Special-education evaluation consent review", "parent or guardian|student with transferred rights", "informed evaluation consent form", "evaluation proposed|consent requested", "overview|evaluation|consent"),
            R("evaluation_consent_submit", "C", "특수교육 평가동의 제출", "Special-education evaluation consent submission", "parent or guardian|student with transferred rights", "informed consent for one evaluation", "consent reviewed|submission ready", "overview|evaluation|consent|submit"),
            R("evaluation_status", "S", "특수교육 평가 진행상태", "Special-education evaluation status", "parent or guardian|student with transferred rights", "identified student evaluation record", "consent received|evaluation pending", "overview|evaluation|status"),
            R("eligibility_determination_review", "S", "특수교육 대상결정 검토", "Special-education eligibility determination review", "parent or guardian|student with transferred rights", "student eligibility determination record", "evaluation complete|determination issued", "overview|eligibility|decision"),
            R("iep_meeting_schedule_review", "S", "개별화교육계획 회의일정 검토", "IEP meeting schedule review", "parent or guardian|student with transferred rights", "identified IEP meeting schedule", "meeting proposed|schedule available", "overview|iep|meeting|schedule"),
            R("iep_meeting_document_upload", "C", "개별화교육계획 회의자료 업로드", "IEP meeting document upload", "parent or guardian|student with transferred rights", "family document for an identified IEP meeting", "meeting scheduled|document ready", "overview|iep|meeting|document"),
            R("current_iep_download", "S", "현재 개별화교육계획 내려받기", "Current IEP download", "parent or guardian|student with transferred rights", "authorized current IEP record", "IEP active|record available", "overview|iep|record"),
            R("parent_input_submit", "C", "개별화교육계획 학부모 의견 제출", "IEP parent input submission", "parent or guardian|student with transferred rights", "family-authored IEP input", "meeting scheduled|input ready", "overview|iep|input|submit"),
            R("service_progress_report", "S", "특수교육 서비스 진도보고서", "Special-education service progress report", "parent or guardian|student with transferred rights", "student service progress report", "IEP active|progress report issued", "overview|progress|report"),
            R("reevaluation_due", "S", "특수교육 재평가 기한", "Special-education reevaluation due", "parent or guardian|student with transferred rights", "student reevaluation due record", "IEP active|reevaluation approaching", "overview|reevaluation|due"),
            R("transition_plan_review", "S", "특수교육 전환계획 검토", "Special-education transition plan review", "parent or guardian|student with transferred rights", "student transition plan", "transition age reached|plan available", "overview|transition|plan"),
            R("prior_written_notice_review", "S", "특수교육 사전서면통지 검토", "Prior written notice review", "parent or guardian|student with transferred rights", "prior written notice for an identified action", "school action proposed or refused|notice issued", "overview|notice|review"),
            R("mediation_request", "C", "특수교육 조정 요청", "Special-education mediation request", "parent or guardian|student with transferred rights", "mediation request for one education dispute", "disagreement identified|mediation available", "overview|mediation|dispute"),
            R("state_complaint_due_process_handoff", "C", "특수교육 민원·심리 공식인계", "Special-education complaint or due-process handoff", "parent or guardian|student with transferred rights", "official complaint or due-process handoff", "dispute identified|official handoff selected", "overview|complaint|due_process"),
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
    "workers_compensation_claimant_services": ("산재보험", "근로복지공단", "산재보상"),
    "paid_family_medical_leave_claimant_services": ("육아휴직 급여", "출산전후휴가 급여", "고용24"),
    "foster_adoption_family_services": ("위탁가정", "입양가정", "아동권리보장원"),
    "consumer_bankruptcy_case_services": ("개인파산", "면책절차", "대한민국 법원"),
    "workplace_leave_accommodation_services": ("보호휴가", "직장 내 장애인 편의", "한국장애인고용공단"),
    "long_term_services_supports_case_services": ("장기요양보험", "장기요양인정", "국민건강보험공단"),
    "child_care_assistance_case_services": ("보육료 지원", "어린이집 지원", "복지로"),
    "special_education_family_services": ("특수교육", "개별화교육계획", "특수교육지원센터"),
}


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
            source_id=f"v20_{prefix}_{index:02d}",
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
        "workers_compensation_claimant_services",
        "workers_comp",
        (
            ("U.S. Department of Labor", "Federal Employees' Compensation Act", "https://www.dol.gov/agencies/owcp/feca", "US", "overview"),
            ("U.S. Department of Labor", "FECA claimant contacts and case services", "https://www.dol.gov/agencies/owcp/feca/contacts/fecacont", "US", "claim|status|document|medical|authorization|payment"),
            ("U.S. Department of Labor", "Information for injured workers", "https://www.dol.gov/agencies/owcp/FECA/regs/compliance/infoinjuredwrkers", "US", "medical|benefit|payment|reimbursement"),
            ("U.S. Department of Labor", "Basic information on new claims", "https://www.dol.gov/agencies/owcp/FECA/regs/compliance/Basic-Information-on-New-Claims?lang=en", "US", "notice|claim|decision|return|appeal"),
            ("California Division of Workers' Compensation", "Injured worker guide", "https://www.dir.ca.gov/dwc/InjuredWorker.htm", "US-CA", "agency|claim|medical|benefit|return|rehabilitation"),
            ("California Division of Workers' Compensation", "Workers' compensation forms", "https://www.dir.ca.gov/dwc/forms.html", "US-CA", "form|claim|document|appeal"),
            ("Korea Workers' Compensation and Welfare Service", "산재보험 청구·급여·재활 안내", "https://webzine.comwel.or.kr/vol115/sub02.html", "KR", "overview|claim|benefit|rehabilitation|appeal"),
        ),
    ),
    *_source_rows(
        "paid_family_medical_leave_claimant_services",
        "paid_leave",
        (
            ("California Employment Development Department", "Paid Family Leave claim process", "https://edd.ca.gov/en/disability/pfl_claim_process/", "US-CA", "overview|coverage|application|certification|decision|appeal"),
            ("California Employment Development Department", "Disability and PFL self-service options", "https://edd.ca.gov/en/disability/SDI_Self_Service_Options/", "US-CA", "claim|status|document|payment"),
            ("California Employment Development Department", "Discontinue, continue, or extend PFL benefits", "https://edd.ca.gov/en/disability/Discontinue_Continue_or_Extend_Your_PFL_Benefits/", "US-CA", "change|return|certification"),
            ("Washington Paid Family and Medical Leave", "File a weekly claim", "https://paidleave.wa.gov/file-your-weekly-claim/", "US-WA", "weekly|certification|payment"),
            ("Washington Paid Family and Medical Leave", "Individuals and families help center", "https://paidleave.wa.gov/help-center/individuals-and-families/", "US-WA", "application|claim|status|document|appeal"),
            ("Massachusetts Department of Family and Medical Leave", "PFML benefits for employees", "https://www.mass.gov/paid-family-and-medical-leave-benefits-for-employees", "US-MA", "application|coverage|claim|status"),
            ("Massachusetts Department of Family and Medical Leave", "PFML overview and benefits", "https://www.mass.gov/info-details/paid-family-and-medical-leave-pfml-overview-and-benefits", "US-MA", "reason|schedule|payment|change|appeal"),
            ("Work24 Korea", "육아휴직·출산전후휴가 급여 신청", "https://www.work24.go.kr/cm/main.do", "KR", "overview|application|claim|certification|payment"),
        ),
    ),
    *_source_rows(
        "foster_adoption_family_services",
        "foster_adoption",
        (
            ("California Department of Social Services", "Resource Family Approval Program", "https://www.cdss.ca.gov/inforesources/resource-family-approval-program", "US-CA", "overview|application|background|home_study|training|approval"),
            ("California Department of Social Services", "Resource family application and approval forms", "https://www.cdss.ca.gov/inforesources/forms-brochures/forms-alphabetic-list/i-l", "US-CA", "application|home_study|document"),
            ("California Department of Social Services", "Prospective caregiver frequently asked questions", "https://www.cdss.ca.gov/inforesources/foster-care/foster-care-and-adoptive-resource/frequently-asked-questions", "US-CA", "orientation|training|approval|payment"),
            ("California Department of Social Services", "Foster parents and youth services", "https://www.cdss.ca.gov/benefits-services/foster-parents-and-youth", "US-CA", "placement|payment|assistance|support"),
            ("California Department of Social Services", "Foster care and permanency overview", "https://www.cdss.ca.gov/inforesources/foster-care/resource-family-approval-program", "US-CA", "approval|match|placement|finalization"),
            ("California Department of Social Services", "Interstate Compact on the Placement of Children", "https://www.cdss.ca.gov/inforesources/cdss-programs/foster-care/interstate-compact-on-the-placement-of-children-icpc/icpc-information", "US-CA", "placement|status|plan"),
            ("National Center for the Rights of the Child Korea", "예비입양부모 교육·신청 안내", "https://jarip.ncrc.or.kr/ncrc/cm/cntnts/cntntsView.do?cntntsId=1344&mi=1281", "KR", "overview|orientation|application|training"),
            ("Ministry of Health and Welfare Korea", "입양 절차와 가정조사 안내", "https://www.mohw.go.kr/menu.es?mid=a10711030500", "KR", "home_study|match|placement|finalization|support"),
        ),
    ),
    *_source_rows(
        "consumer_bankruptcy_case_services",
        "bankruptcy",
        (
            ("Administrative Office of the U.S. Courts", "Bankruptcy Basics", "https://www.uscourts.gov/court-programs/bankruptcy/bankruptcy-basics", "US", "overview|chapter|petition|case|meeting|discharge|closure"),
            ("Administrative Office of the U.S. Courts", "Filing bankruptcy without an attorney", "https://www.uscourts.gov/court-programs/bankruptcy/filing-without-attorney", "US", "court|petition|form|submit|fee"),
            ("Administrative Office of the U.S. Courts", "Discharge in bankruptcy", "https://www.uscourts.gov/court-programs/bankruptcy/bankruptcy-basics/discharge-bankruptcy-bankruptcy-basics", "US", "education|discharge|closure"),
            ("Administrative Office of the U.S. Courts", "Bankruptcy court fee schedule", "https://www.uscourts.gov/court-programs/fees/bankruptcy-court-miscellaneous-fee-schedule", "US", "fee|amendment"),
            ("U.S. Trustee Program", "Consumer information", "https://www.justice.gov/ust/consumer-information", "US", "counseling|means_test|trustee|meeting|claims"),
            ("U.S. Trustee Program", "Credit counseling and debtor education providers", "https://www.justice.gov/ust/credit-counseling-and-debtor-education-providers", "US", "counseling|education|provider"),
            ("Supreme Court of Korea", "개인파산·면책 신청 안내", "https://www.scourt.go.kr/nm/min_2/min_2_1/min_2_1_5/index.html", "KR", "overview|court|petition|discharge|closure"),
            ("Supreme Court of Korea", "개인회생 관할·서류 안내", "https://www.scourt.go.kr/nm/min_2/min_2_2/min_2_2_1/index.html", "KR", "court|form|document|case"),
        ),
    ),
    *_source_rows(
        "workplace_leave_accommodation_services",
        "workplace_leave",
        (
            ("U.S. Department of Labor", "Family and Medical Leave Act", "https://www.dol.gov/agencies/whd/fmla", "US", "overview|leave|coverage"),
            ("U.S. Department of Labor", "FMLA leave process", "https://www.dol.gov/agencies/whd/fmla/FMLA-leave-process", "US", "leave|request|notice|certification|designation|return"),
            ("U.S. Department of Labor", "FMLA forms", "https://www.dol.gov/agencies/whd/fmla/forms", "US", "leave|certification|document|return"),
            ("U.S. Department of Labor", "Talk to your employer about FMLA leave", "https://www.dol.gov/agencies/whd/fmla/how-to-talk-to-your-employer-about-leave", "US", "leave|request|notice|return"),
            ("U.S. Equal Employment Opportunity Commission", "Reasonable accommodation and undue hardship guidance", "https://www.eeoc.gov/laws/guidance/enforcement-guidance-reasonable-accommodation-and-undue-hardship-under-ada", "US", "accommodation|request|document|status|decision|implementation"),
            ("U.S. Equal Employment Opportunity Commission", "Employer-provided leave and the ADA", "https://www.eeoc.gov/laws/guidance/employer-provided-leave-and-americans-disabilities-act", "US", "leave|accommodation|interactive"),
            ("Korea Employment Agency for Persons with Disabilities", "장애인 고용지원 전자신고", "https://www.esingo.or.kr/", "KR", "overview|accommodation|request|document"),
            ("Korea Employment Agency for Persons with Disabilities", "근로지원·보조공학 신청 처리 안내", "https://www.kead.or.kr/customerCharter3/cntntsPage.do?menuId=MENU0191", "KR", "accommodation|status|decision|implementation"),
        ),
    ),
    *_source_rows(
        "long_term_services_supports_case_services",
        "ltss",
        (
            ("Centers for Medicare & Medicaid Services", "Home and community-based services", "https://www.medicaid.gov/medicaid/home-community-based-services", "US", "overview|program|application|service"),
            ("Centers for Medicare & Medicaid Services", "HCBS authorities", "https://www.medicaid.gov/medicaid/home-community-based-services/home-community-based-services-authorities", "US", "program|pathway|agency"),
            ("Centers for Medicare & Medicaid Services", "Self-directed services", "https://www.medicaid.gov/medicaid/long-term-services-supports/self-directed-services", "US", "assessment|plan|provider|selection|service"),
            ("Centers for Medicare & Medicaid Services", "Managed long-term services and supports", "https://www.medicaid.gov/medicaid/managed-care/managed-long-term-services-and-supports", "US", "assessment|eligibility|plan|authorization"),
            ("Centers for Medicare & Medicaid Services", "HCBS access provisions", "https://www.medicaid.gov/medicaid/access-care/home-and-community-based-services-provisions", "US", "waitlist|status|appeal|service"),
            ("Centers for Medicare & Medicaid Services", "Preadmission screening and resident review", "https://www.medicaid.gov/medicaid/long-term-services-supports/institutional-long-term-care/preadmission-screening-and-resident-review", "US", "assessment|result|program"),
            ("National Health Insurance Service Korea", "노인장기요양 인정 신청·평가 흐름", "https://www.nhis.or.kr/announce/wbhaec11100m01.do", "KR", "overview|application|assessment|eligibility|renewal"),
            ("Long-Term Care Insurance Korea", "장기요양 신청·서비스 포털", "https://www.longtermcare.or.kr/npbs/indexr.jsp", "KR", "application|status|provider|authorization|schedule|report"),
        ),
    ),
    *_source_rows(
        "child_care_assistance_case_services",
        "childcare_assistance",
        (
            ("ChildCare.gov", "Get help paying for child care", "https://www.childcare.gov/consumer-education/get-help-paying-for-child-care", "US", "overview|program|agency|application"),
            ("ChildCare.gov", "Child-care financial assistance options", "https://www.childcare.gov/consumer-education/get-help-paying-for-child-care/child-care-financial-assistance-options", "US", "program|eligibility|authorization"),
            ("ChildCare.gov", "State and territory child-care resources", "https://www.childcare.gov/state-resources", "US", "agency|provider|program"),
            ("Massachusetts Department of Early Education and Care", "Child-care financial assistance", "https://www.mass.gov/child-care-financial-assistance", "US-MA", "application|status|document|provider|recertification"),
            ("Massachusetts Department of Early Education and Care", "Family portal for child-care assistance", "https://www.mass.gov/news/healey-driscoll-administration-launches-new-family-portal-to-help-parents-caregivers-pay-for-child-care", "US-MA", "application|status|provider|authorization"),
            ("Massachusetts Department of Early Education and Care", "Child-care assistance program changes hub", "https://www.mass.gov/info-details/hub-for-child-care-financial-assistance-programs-changes", "US-MA", "waitlist|provider|authorization|change|recertification"),
            ("Massachusetts Department of Early Education and Care", "Income-eligible child-care policies", "https://www.mass.gov/doc/eec-ccfa-2026-04-income-eligible-consolidated-policies-may-6-2026/download", "US-MA", "document|eligibility|waitlist|copayment|schedule|appeal"),
            ("Bokjiro Korea", "온라인 보육료 지원 신청·제출 안내", "https://m.bokjiro.go.kr/ssis-tem/cms/mob/customer/notice/1309244_1155.html", "KR", "overview|application|document|submit|status"),
        ),
    ),
    *_source_rows(
        "special_education_family_services",
        "special_education",
        (
            ("U.S. Department of Education IDEA", "Procedural safeguards", "https://sites.ed.gov/idea/statute-chapter-33/subchapter-ii/1415", "US", "overview|record|meeting|notice|mediation|complaint"),
            ("U.S. Department of Education IDEA", "Parental consent", "https://sites.ed.gov/idea/regs/b/d/300.300", "US", "evaluation|consent"),
            ("U.S. Department of Education IDEA", "Parent participation in IEP meetings", "https://sites.ed.gov/idea/regs/b/d/300.322", "US", "iep|meeting|schedule|input"),
            ("U.S. Department of Education IDEA", "Procedural safeguards notice", "https://sites.ed.gov/idea/regs/b/e/300.504", "US", "notice|record|mediation|complaint"),
            ("U.S. Department of Education IDEA", "Dispute-resolution regulations", "https://sites.ed.gov/idea/regs/b/e", "US", "mediation|complaint|due_process"),
            ("U.S. Department of Education IDEA", "Evaluation procedures", "https://sites.ed.gov/idea/statute-chapter-33/subchapter-ii/1414/b", "US", "referral|evaluation|eligibility|input|report"),
            ("Gyeonggi Office of Education", "특수교육 의뢰·진단평가·배치 절차", "https://www.goeyi.kr/goeyi/cm/cntnts/cntntsView.do?cntntsId=3619&mi=23654", "KR", "overview|referral|evaluation|consent|eligibility"),
            ("National Institute of Special Education Korea", "개별화교육계획과 학부모 참여", "https://www.nise.go.kr/jsp/field/2008-3/04-2.jsp", "KR", "iep|progress|transition|input"),
        ),
    ),
)


PUBLISHER_ALLOWLIST = frozenset(seed.publisher for seed in SOURCE_SEEDS)


def normalize_official_url(value: str) -> str:
    parts = urlsplit(value.strip())
    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    if scheme != "https" or not host:
        raise V20CatalogValidationError(f"invalid official source URL: {value}")
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
            if "all" in seed.lifecycle_tags
            or set(seed.lifecycle_tags).intersection(feature.source_tags)
        ]
        if not terminal_ids:
            raise V20CatalogValidationError(f"{seed.source_id}: source has no terminal mapping")
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
            "verification_method": (
                "direct official lifecycle URL recorded in the SHA-pinned V20 research document"
            ),
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
EXPECTED_OFFICIAL_SOURCES_SHA256 = "3fd21a7de7f926067352dfe4ecb357cb330683668b16608ac40e36e951cb020f"
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
            f"authorized claimant or family {lower}",
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
            "자격·사실·동의·권한을 추정하는 요청",
            "운영자·심사자·결정권자 화면",
            "wrong role",
            "different person or record",
            "wrong lifecycle state",
            "missing provider or jurisdiction",
            "eligibility facts consent or authority must not be inferred",
            "operator adjudicator or decision-maker surface",
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
        f"{domain.domain}_v20_claimant_family_services",
        "|".join(
            _dedupe((domain.root_ko, domain.role_ko, *domain.assets, *KOREAN_DOMAIN_TERMS[domain.domain]))
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
    domain.domain: len(domain.features)
    for domain in sorted(REVIEWED_DOMAINS, key=lambda item: item.domain)
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
    result["legacy_tags"] = list(_dedupe((*tags, "v20_claimant_family_services")))
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    result.update(
        {
            "aliases": {
                "ko-KR": list(
                    _dedupe(
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
                ),
                "en-US": list(
                    _dedupe(
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
                ),
            },
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
        "missing_dimension": [
            "missing role",
            "missing governed asset",
            "missing lifecycle state",
            "missing provider or jurisdiction",
        ],
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
    result["asset_cues"] = list(
        _dedupe((*feature.assets, feature.name_ko, feature.name_en, _words(feature.key)))
    )
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
            else "C: consequential claimant- or family-owned action"
        ],
        "role_asset_state_jurisdiction_gate": [
            "권한 역할·정확한 자산·현재 상태·제공자와 관할을 모두 확인",
            "verify authorized role, exact governed asset, current lifecycle state, provider, and jurisdiction",
            "all five routing dimensions are mandatory",
        ],
        "fail_closed": [
            "어느 차원이라도 없거나 충돌하면 도메인 허브에서 중단",
            "stop at the domain hub on any missing or conflicting dimension",
        ],
        "forbidden_terminal_actions": [
            "제출·업로드·결제·인증·동의·선택·일정변경·신고·이의제기 자동 실행 금지",
            "never auto-submit, upload, pay, certify, consent, select, reschedule, report, complain, or appeal",
        ],
        "blocked_final_channels": [
            "음성·키보드·딥링크·재시도·접근성 동작으로 최종 행동 우회 금지",
            "no final-action bypass through voice, keyboard, deep link, retry, or accessibility action",
        ],
        "user_boundary": [
            "최종 목적지 동작은 사용자가 직접 수행",
            "the user must perform the final destination action",
        ],
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
    return {
        "ko-KR": list(
            _dedupe(
                (
                    feature.goal_ko,
                    f"{domain.role_ko}로서 {feature.name_ko} 화면을 열고 싶어",
                    f"{domain.root_ko}에서 내 기록의 {feature.name_ko} 메뉴를 찾아줘",
                    f"정확한 대상과 현재 상태를 확인하고 {feature.name_ko} 위치로 이동해 줘",
                    f"공식 제공자와 관할을 확인한 뒤 {feature.name_ko}을 찾아줘",
                )
            )
        ),
        "en-US": list(
            _dedupe(
                (
                    feature.goal_en,
                    f"As {feature.roles[0]}, open {feature.name_en.lower()}",
                    f"Find {feature.name_en.lower()} within {domain.root_en.lower()}",
                    f"For {feature.assets[0]} in {feature.states[0]} state, locate {feature.name_en.lower()}",
                    f"After confirming provider and jurisdiction, take me to {feature.name_en.lower()}",
                )
            )
        ),
    }


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = f"v20_{group.domain}_{seed.key}"
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v20_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v20_{key[4:]}"] = rule.pop(key)
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    target = f"{group.domain}.{seed.key}"
    patterns_by_locale = _intent_patterns(domain, feature)
    result["patterns_by_locale"] = patterns_by_locale
    result["patterns"] = [*patterns_by_locale["ko-KR"], *patterns_by_locale["en-US"]]
    result["representative_goal_by_locale"] = {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}
    result["purpose_by_locale"] = {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}
    governance_terms = [
        feature.roles[0],
        feature.assets[0],
        feature.states[0],
        feature.jurisdiction_guard,
    ]
    result["goal_rules"].append(
        {
            "all_of": governance_terms,
            "none_of": [
                "wrong role",
                "different person or record",
                "wrong lifecycle state",
                "missing provider or jurisdiction",
                "operator adjudicator or decision-maker surface",
            ],
            "score": 0.999,
            "rule_kind": "v20_role_asset_state_jurisdiction_gate",
            "v20_discriminative_keys": [
                key for key in (_runtime_pattern_key(value) for value in governance_terms) if key
            ],
            "v20_required_dimensions": [
                "authorized_role",
                "governed_asset",
                "lifecycle_state",
                "provider_jurisdiction",
            ],
            "v20_required_dimension_count": 4,
        }
    )
    result["goal_rules"].append(
        {
            "all_of": [KOREAN_DOMAIN_TERMS[group.domain][0], feature.name_ko],
            "none_of": ["잘못된 역할", "다른 기록", "다른 제공자", "관할 불명확"],
            "score": 0.999,
            "rule_kind": "v20_kr_provider_jurisdiction_gate",
            "v20_jurisdiction": "KR",
            "v20_discriminative_keys": [
                _runtime_pattern_key(KOREAN_DOMAIN_TERMS[group.domain][0]),
                _runtime_pattern_key(feature.name_ko),
            ],
        }
    )
    peers = [f"{group.domain}.{item.key}" for item in domain.features if item.key != seed.key]
    result["avoid_functions"] = list(
        _dedupe(
            (
                *peers[:3],
                *result.get("avoid_functions", []),
                domain.avoid_root,
                *domain.nearest_existing_functions,
            )
        )
    )
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {
        "stop_policy": "stop_before_action",
        "user_owned_final_press": True,
    }
    result["resolution_gate"] = {
        "dimensions": [
            "authorized_role",
            "governed_asset",
            "lifecycle_state",
            "provider_jurisdiction",
        ],
        "required_dimensions": [
            "authorized_role",
            "governed_asset",
            "lifecycle_state",
            "provider_jurisdiction",
        ],
        "minimum_positive_dimensions": 4,
        "on_missing_dimension": "fail_closed",
        "fail_closed_to": f"{group.domain}.hub",
    }
    return result


V20_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V20_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


REJECTED_DUPLICATE_FAMILIES = (
    "consumer_identity_recovery",
    "public_utility_energy_assistance",
    "passport_application_renewal_status_records",
    "broad_immigration_or_consular_visa",
    "general_tax_filing_payment_refund_documents",
    "general_insurance_claim",
    "general_hr_leave_or_pto",
    "general_social_services_or_benefits_case",
    "generic_disability_cash_benefit",
    "general_public_health_coverage",
    "ordinary_collector_notice_dispute_or_payment",
    "generic_self_represented_court_filing_or_docket",
    "childcare_provider_billing_attendance_or_checkin",
    "foster_adoption_caseworker_decision",
    "informal_long_term_family_care_coordination",
    "special_education_program_administration",
)


@dataclass(frozen=True)
class InheritedReferenceCorrection:
    bad_id: str
    replacements: tuple[str, ...]
    disposition: str
    reason: str


def C(
    bad_id: str,
    replacements: str = "",
    *,
    reason: str,
) -> InheritedReferenceCorrection:
    values = _terms(replacements)
    return InheritedReferenceCorrection(
        bad_id=bad_id,
        replacements=values,
        disposition="replace" if values else "remove_fail_closed",
        reason=reason,
    )


# V17 used six synthetic category hubs that never existed physically.  V18
# used broad domain names where the catalog schema requires concrete function
# IDs.  Every definite domain root is replaced; only two broad V18 markers and
# the six synthetic V17 categories are removed because choosing one physical
# terminal would invent a false semantic owner.  Their collision evidence
# remains in negative contexts and the sealed probe matrices.
INHERITED_REFERENCE_CORRECTIONS: tuple[InheritedReferenceCorrection, ...] = (
    C("account", "account.entry", reason="canonical account entry is the reviewed broad root"),
    C("air_traffic_control_ops", "air_traffic_control_ops.hub", reason="exact physical domain hub"),
    C("air_travel_planning", "air_travel_planning.hub", reason="exact physical domain hub"),
    C("airline_crew_operations", "airline_crew_operations.hub", reason="exact physical domain hub"),
    C("airport_airside_operations", "airport_airside_operations.hub", reason="exact physical domain hub"),
    C("android_connectivity", "android_connectivity.hub", reason="exact physical domain hub"),
    C("app_store_release_management", "app_store_release_management.hub", reason="exact physical domain hub"),
    C("authentication", "auth.entry", reason="canonical authentication entry is the reviewed broad root"),
    C("automotive_vehicle", "automotive_vehicle.hub", reason="exact physical domain hub"),
    C("campaign_finance_compliance", "campaign_finance_compliance.hub", reason="exact physical domain hub"),
    C("childcare_family_portal", "childcare_family_portal.hub", reason="exact physical domain hub"),
    C("classroom_instructor_ops", "classroom_instructor_ops.hub", reason="exact physical domain hub"),
    C("commerce", "order.list", reason="canonical order list is the broad commerce navigation root"),
    C("community_meetup", "community_meetup.hub", reason="exact physical domain hub"),
    C("consumer_credit_reporting_services", "consumer_credit_reporting_services.hub", reason="exact physical domain hub"),
    C("content", reason="broad content marker has multiple unrelated roots and no safe single owner"),
    C("creator_monetization", "creator_monetization.hub", reason="exact physical domain hub"),
    C("crm_sales", "crm_sales.hub", reason="exact physical domain hub"),
    C("education", "education.hub", reason="exact physical domain hub"),
    C("employment_workplace.hub", reason="synthetic V17 category has no physical function and no unique owner"),
    C("estate_probate_administration", "estate_probate_administration.hub", reason="exact physical domain hub"),
    C("family_legal_support.hub", reason="synthetic V17 category has no physical function and no unique owner"),
    C("fleet_driver_compliance", "fleet_driver_compliance.hub", reason="exact physical domain hub"),
    C("food_manufacturing_recall_ops", "food_manufacturing_recall_ops.hub", reason="exact physical domain hub"),
    C("gig_worker_dispatch", "gig_worker_dispatch.hub", reason="exact physical domain hub"),
    C("healthcare_provider_ops.hub", reason="synthetic V17 category has no physical function and no unique owner"),
    C("higher_education_student_admin", "higher_education_student_admin.hub", reason="exact physical domain hub"),
    C("home_services", "home_services.hub", reason="exact physical domain hub"),
    C("housing.hub", reason="synthetic V17 category has no physical function and no unique owner"),
    C("hr_payroll", "hr_payroll.hub", reason="exact physical domain hub"),
    C("identity_security.hub", reason="synthetic V17 category has no physical function and no unique owner"),
    C("jobs", "jobs.hub", reason="exact physical domain hub"),
    C("legal", reason="broad legal marker has no non-terminal root and no safe single owner"),
    C("maintenance_asset_ops", "maintenance_asset_ops.hub", reason="exact physical domain hub"),
    C("marketing", "marketing.settings", reason="canonical marketing settings is the only reviewed broad root"),
    C("marketplace", "marketplace.hub", reason="exact physical domain hub"),
    C("medical_device_regulatory_ops", "medical_device_regulatory_ops.hub", reason="exact physical domain hub"),
    C("merchant_pos_inventory", "merchant_pos_inventory.hub", reason="exact physical domain hub"),
    C("mobility_delivery", "mobility.hub", reason="canonical mobility hub owns the combined mobility-delivery root"),
    C("mortgage_origination_servicing_ops", "mortgage_origination_servicing_ops.hub", reason="exact physical domain hub"),
    C("privacy", "privacy.settings", reason="canonical privacy settings is the reviewed broad root"),
    C("professional_certification_ops.hub", reason="synthetic V17 category has no physical function and no unique owner"),
    C("refund", "refund.order_select", reason="canonical refund order selection is the reviewed broad entry"),
    C("retail_banking", "retail_banking.hub", reason="exact physical domain hub"),
    C("ride_hailing_extended", "ride_hailing.hub", reason="canonical ride-hailing hub owns the extended domain root"),
    C("special_education_program_admin", "special_education_program_admin.hub", reason="exact physical domain hub"),
    C("student_financial_aid_services", "student_financial_aid_services.hub", reason="exact physical domain hub"),
    C("subscription", "subscription.manage", reason="canonical subscription manager is the reviewed broad entry"),
    C("support", "support.help", reason="canonical support help is the reviewed broad root"),
    C("telecom", "telecom.hub", reason="exact physical domain hub"),
    C("telecom_field_service_ops", "telecom_field_service_ops.hub", reason="exact physical domain hub"),
    C("travel", "travel.bookings", reason="canonical travel bookings is the reviewed broad root"),
    C("utilities", "utilities.hub", reason="exact physical domain hub"),
    C("warehouse_fulfillment_ops", "warehouse_fulfillment_ops.hub", reason="exact physical domain hub"),
)
INHERITED_REFERENCE_CORRECTION_BY_BAD_ID = {
    correction.bad_id: correction for correction in INHERITED_REFERENCE_CORRECTIONS
}
INHERITED_REFERENCE_PREIMAGE = {
    str(intent["intent_id"]): tuple(
        str(value)
        for value in intent.get("avoid_functions", [])
        if str(value) in INHERITED_REFERENCE_CORRECTION_BY_BAD_ID
    )
    for intent in (*V17_INTENTS, *V18_INTENTS)
    if any(
        str(value) in INHERITED_REFERENCE_CORRECTION_BY_BAD_ID
        for value in intent.get("avoid_functions", [])
    )
}
INHERITED_REFERENCE_PREIMAGE_SHA256 = _digest(INHERITED_REFERENCE_PREIMAGE)
EXPECTED_INHERITED_REFERENCE_COUNTS = {
    "bad_ids": 54,
    "owner_intents": 354,
    "references": 1314,
    "replacements": 46,
    "removals": 8,
}
INHERITED_REFERENCE_CORRECTION_SHA256 = _digest(
    [asdict(correction) for correction in INHERITED_REFERENCE_CORRECTIONS]
)


COLLISION_FAMILIES = tuple(
    (domain.domain, neighbor, domain.collision_terms[index % len(domain.collision_terms)])
    for domain in REVIEWED_DOMAINS
    for index, neighbor in enumerate(domain.nearest_existing_functions)
)

WITHIN_V20_COLLISIONS = (
    ("workers_compensation_claimant_services", "paid_family_medical_leave_claimant_services", "wage replacement benefit"),
    ("workers_compensation_claimant_services", "workplace_leave_accommodation_services", "work restriction and leave"),
    ("paid_family_medical_leave_claimant_services", "workers_compensation_claimant_services", "benefit certification"),
    ("paid_family_medical_leave_claimant_services", "workplace_leave_accommodation_services", "medical leave certification"),
    ("workplace_leave_accommodation_services", "paid_family_medical_leave_claimant_services", "leave status"),
    ("workplace_leave_accommodation_services", "workers_compensation_claimant_services", "return to work"),
    ("foster_adoption_family_services", "child_care_assistance_case_services", "family application status"),
    ("child_care_assistance_case_services", "foster_adoption_family_services", "child provider and placement"),
    ("long_term_services_supports_case_services", "workplace_leave_accommodation_services", "functional assessment and accommodation"),
    ("special_education_family_services", "child_care_assistance_case_services", "child eligibility and provider"),
    ("consumer_bankruptcy_case_services", "workers_compensation_claimant_services", "claim and appeal status"),
    ("special_education_family_services", "foster_adoption_family_services", "child evaluation and family plan"),
)


def build_collision_probes() -> tuple[dict[str, object], ...]:
    """Return bilingual baseline-neighbor and within-V20 ambiguity probes."""

    probes: list[dict[str, object]] = []
    for index, (domain, neighbor, token) in enumerate(COLLISION_FAMILIES):
        spec = REVIEWED_BY_DOMAIN[domain]
        for locale, text_value in (
            (
                "ko-KR",
                f"{spec.root_ko}에서 {token} 말만 보이고 역할 불일치, 다른 사람 또는 다른 기록, "
                "다른 생명주기 상태, 제공자 또는 관할 불명확",
            ),
            (
                "en-US",
                f"{token} is ambiguous between {domain} and {neighbor}: wrong role, different "
                "person or record, wrong lifecycle state, missing provider or jurisdiction",
            ),
        ):
            probes.append(
                {
                    "probe_id": f"v20_collision_existing_{index:02d}_{locale}",
                    "kind": "nearest_existing_collision",
                    "locale": locale,
                    "text": text_value,
                    "expected_function": f"{domain}.hub",
                    "allowed_fallback": f"{domain}.hub",
                    "excluded_function": neighbor,
                    "required_policy": "fail_closed",
                }
            )
    for index, (domain, other, token) in enumerate(WITHIN_V20_COLLISIONS):
        spec = REVIEWED_BY_DOMAIN[domain]
        other_spec = REVIEWED_BY_DOMAIN[other]
        for locale, text_value in (
            (
                "ko-KR",
                f"{spec.root_ko}와 {other_spec.root_ko} 중 {token}만 보이며 역할 불일치, "
                "다른 사람 또는 다른 기록, 다른 생명주기 상태, 제공자 또는 관할 불명확",
            ),
            (
                "en-US",
                f"{token} is ambiguous between {domain} and {other}: wrong role, different "
                "person or record, wrong lifecycle state, missing provider or jurisdiction",
            ),
        ):
            probes.append(
                {
                    "probe_id": f"v20_collision_internal_{index:02d}_{locale}",
                    "kind": "within_v20_collision",
                    "locale": locale,
                    "text": text_value,
                    "expected_function": f"{domain}.hub",
                    "allowed_fallback": f"{domain}.hub",
                    "excluded_function": f"{other}.hub",
                    "required_policy": "fail_closed",
                }
            )
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return two positive and four missing-dimension probes per terminal."""

    functions = {str(item["function_id"]): item for item in V20_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V20_INTENTS:
        target = str(intent["terminal_function"])
        domain = target.split(".", 1)[0]
        function = functions[target]
        for locale in ("ko-KR", "en-US"):
            probes.append(
                {
                    "kind": "positive",
                    "locale": locale,
                    "text": intent["patterns_by_locale"][locale][0],
                    "expected_function": target,
                }
            )
        for kind, negative_index in (
            ("missing_role", 6),
            ("missing_asset", 7),
            ("missing_state", 8),
            ("missing_jurisdiction", 9),
        ):
            probes.append(
                {
                    "kind": kind,
                    "locale": "en-US",
                    "text": f"{function['name_en']} {function['negative_context'][negative_index]}",
                    "expected_function": f"{domain}.hub",
                    "allowed_fallback": f"{domain}.hub",
                    "excluded_function": target,
                    "required_policy": "fail_closed",
                }
            )
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed state and permission interlocks per terminal."""

    scenarios = (
        ("disabled", "disabled control unavailable permission denied"),
        ("unavailable_offline", "currently unavailable offline stale data"),
        ("wrong_role", "wrong role operator adjudicator or decision-maker surface"),
        ("wrong_record_jurisdiction", "different person or record wrong lifecycle state missing provider or jurisdiction"),
    )
    probes: list[dict[str, object]] = []
    for function in V20_FUNCTIONS:
        if not function["terminal"]:
            continue
        target = str(function["function_id"])
        hub = f"{function['domain']}.hub"
        for kind, detail in scenarios:
            probes.append(
                {
                    "kind": kind,
                    "locale": "en-US",
                    "text": f"{function['name_en']} {detail}",
                    "expected_function": hub,
                    "allowed_fallback": hub,
                    "excluded_function": target,
                    "required_policy": "never_auto",
                    "required_stop_policy": "before_action",
                    "required_user_owned_final_press": True,
                }
            )
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-record, and wrong-state probes per terminal."""

    scenarios = (
        ("wrong_role", "wrong role operator adjudicator or decision-maker surface"),
        ("wrong_record", "different person or record different governed asset"),
        ("wrong_state", "wrong lifecycle state current state unclear"),
    )
    probes: list[dict[str, object]] = []
    for function in V20_FUNCTIONS:
        if not function["terminal"]:
            continue
        target = str(function["function_id"])
        hub = f"{function['domain']}.hub"
        for kind, detail in scenarios:
            probes.append(
                {
                    "kind": kind,
                    "locale": "en-US",
                    "text": f"{function['name_en']} {detail}",
                    "expected_function": hub,
                    "allowed_fallback": hub,
                    "excluded_function": target,
                    "required_policy": "fail_closed",
                }
            )
    return tuple(probes)


def _apply_inherited_reference_corrections(
    payload: dict[str, object],
) -> dict[str, object]:
    """Correct only the SHA-pinned V17/V18 invalid avoidance references."""

    functions = {str(item["function_id"]) for item in payload.get("functions", [])}
    intents = {str(item["intent_id"]): item for item in payload.get("intents", [])}
    rows: dict[str, dict[str, object]] = {}
    observed_references = 0
    observed_bad_ids: set[str] = set()
    for intent_id, expected_bad_refs in sorted(INHERITED_REFERENCE_PREIMAGE.items()):
        intent = intents.get(intent_id)
        if intent is None:
            raise V20CatalogValidationError(
                f"missing inherited correction owner intent: {intent_id}"
            )
        before = list(intent.get("avoid_functions", []))
        actual_bad_refs = tuple(
            str(value)
            for value in before
            if str(value) in INHERITED_REFERENCE_CORRECTION_BY_BAD_ID
        )
        if actual_bad_refs != expected_bad_refs:
            raise V20CatalogValidationError(
                f"{intent_id}: inherited avoidance preimage differs"
            )
        after: list[str] = []
        for value in before:
            key = str(value)
            correction = INHERITED_REFERENCE_CORRECTION_BY_BAD_ID.get(key)
            if correction is None:
                after.append(key)
                continue
            observed_references += 1
            observed_bad_ids.add(key)
            after.extend(correction.replacements)
        after = list(_dedupe(after))
        unknown_after = sorted(set(after) - functions)
        if unknown_after:
            raise V20CatalogValidationError(
                f"{intent_id}: correction produced unknown avoid_functions {unknown_after}"
            )
        intent["avoid_functions"] = after
        rows[intent_id] = {
            "bad_ids": list(expected_bad_refs),
            "before": before,
            "before_sha256": _digest(before),
            "after": after,
            "after_sha256": _digest(after),
        }
    if observed_references != EXPECTED_INHERITED_REFERENCE_COUNTS["references"]:
        raise V20CatalogValidationError(
            f"inherited correction reference count differs: {observed_references}"
        )
    if observed_bad_ids != set(INHERITED_REFERENCE_CORRECTION_BY_BAD_ID):
        raise V20CatalogValidationError(
            "inherited correction bad-ID coverage differs"
        )
    all_unknown = sorted(
        {
            str(value)
            for intent in payload.get("intents", [])
            for value in intent.get("avoid_functions", [])
            if str(value) not in functions
        }
    )
    if all_unknown:
        raise V20CatalogValidationError(
            f"inherited correction left unknown avoid_functions: {all_unknown}"
        )
    return {
        "schema_version": "v20-inherited-reference-correction.v1",
        "correction_contract_sha256": INHERITED_REFERENCE_CORRECTION_SHA256,
        "preimage_sha256": INHERITED_REFERENCE_PREIMAGE_SHA256,
        "expected_counts": copy.deepcopy(EXPECTED_INHERITED_REFERENCE_COUNTS),
        "owner_intents": sorted(rows),
        "corrections": rows,
    }


def _validate_inherited_reference_ledger(
    payload: Mapping[str, object],
    ledger: object,
) -> dict[str, object]:
    if not isinstance(ledger, Mapping):
        raise V20CatalogValidationError("V20 inherited-reference ledger missing")
    if ledger.get("schema_version") != "v20-inherited-reference-correction.v1":
        raise V20CatalogValidationError("V20 inherited-reference ledger schema differs")
    if ledger.get("correction_contract_sha256") != INHERITED_REFERENCE_CORRECTION_SHA256:
        raise V20CatalogValidationError("V20 inherited-reference correction contract differs")
    if ledger.get("preimage_sha256") != INHERITED_REFERENCE_PREIMAGE_SHA256:
        raise V20CatalogValidationError("V20 inherited-reference preimage seal differs")
    if ledger.get("expected_counts") != EXPECTED_INHERITED_REFERENCE_COUNTS:
        raise V20CatalogValidationError("V20 inherited-reference expected counts differ")
    rows = ledger.get("corrections")
    if not isinstance(rows, Mapping) or set(rows) != set(INHERITED_REFERENCE_PREIMAGE):
        raise V20CatalogValidationError("V20 inherited-reference owner set differs")
    if ledger.get("owner_intents") != sorted(INHERITED_REFERENCE_PREIMAGE):
        raise V20CatalogValidationError("V20 inherited-reference owner order differs")
    intents = {str(item["intent_id"]): item for item in payload.get("intents", [])}
    functions = {str(item["function_id"]) for item in payload.get("functions", [])}
    for intent_id, expected_bad_refs in INHERITED_REFERENCE_PREIMAGE.items():
        row = rows.get(intent_id)
        intent = intents.get(intent_id)
        if not isinstance(row, Mapping) or intent is None:
            raise V20CatalogValidationError(
                f"{intent_id}: inherited-reference ledger row missing"
            )
        before = row.get("before")
        after = row.get("after")
        if not isinstance(before, list) or not isinstance(after, list):
            raise V20CatalogValidationError(
                f"{intent_id}: inherited-reference snapshots invalid"
            )
        if row.get("bad_ids") != list(expected_bad_refs):
            raise V20CatalogValidationError(
                f"{intent_id}: inherited-reference bad-ID snapshot differs"
            )
        if row.get("before_sha256") != _digest(before) or row.get("after_sha256") != _digest(after):
            raise V20CatalogValidationError(
                f"{intent_id}: inherited-reference snapshot seal differs"
            )
        if list(intent.get("avoid_functions", [])) != after:
            raise V20CatalogValidationError(
                f"{intent_id}: corrected inherited-reference payload differs"
            )
        if any(value in INHERITED_REFERENCE_CORRECTION_BY_BAD_ID for value in after):
            raise V20CatalogValidationError(
                f"{intent_id}: corrected payload retains an invalid inherited reference"
            )
    unknown = sorted(
        {
            str(value)
            for intent in payload.get("intents", [])
            for value in intent.get("avoid_functions", [])
            if str(value) not in functions
        }
    )
    if unknown:
        raise V20CatalogValidationError(
            f"corrected V20 payload contains unknown avoid_functions: {unknown}"
        )
    v20_unknown = sorted(
        {
            str(value)
            for intent in payload.get("intents", [])
            if str(intent.get("intent_id", "")).startswith("v20_")
            for value in intent.get("avoid_functions", [])
            if str(value) not in functions
        }
    )
    if v20_unknown:
        raise V20CatalogValidationError(
            f"V20-owned intent references unknown functions: {v20_unknown}"
        )
    return dict(ledger)


def _revert_inherited_reference_corrections(
    payload: dict[str, object],
    ledger: object,
) -> None:
    validated = _validate_inherited_reference_ledger(payload, ledger)
    intents = {str(item["intent_id"]): item for item in payload.get("intents", [])}
    rows = validated["corrections"]
    for intent_id in sorted(INHERITED_REFERENCE_PREIMAGE):
        intents[intent_id]["avoid_functions"] = copy.deepcopy(rows[intent_id]["before"])


def _verify_source_documents() -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        path = ROOT / relative_path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual[relative_path] = digest
        if digest != expected:
            raise V20CatalogValidationError(
                f"V20 source SHA-256 differs for {relative_path}: expected {expected}, got {digest}"
            )
    return actual


def _layer_digest() -> str:
    payload = {
        "catalog_version": CATALOG_V20_VERSION,
        "base_layer_seal": BASE_LAYER_SEAL,
        "base_payload_seal": BASE_PAYLOAD_SEAL,
        "reviewed_domains": [asdict(domain) for domain in REVIEWED_DOMAINS],
        "functions": V20_FUNCTIONS,
        "intents": V20_INTENTS,
        "official_sources": OFFICIAL_SOURCES,
        "official_sources_sha256": OFFICIAL_SOURCES_SHA256,
        "source_documents": SOURCE_DOCUMENT_METADATA,
        "korean_domain_terms": KOREAN_DOMAIN_TERMS,
        "nearest_existing_functions": NEAREST_EXISTING_FUNCTIONS,
        "within_v20_collisions": WITHIN_V20_COLLISIONS,
        "rejected_duplicate_families": REJECTED_DUPLICATE_FAMILIES,
        "inherited_reference_corrections": [
            asdict(correction) for correction in INHERITED_REFERENCE_CORRECTIONS
        ],
        "inherited_reference_correction_sha256": INHERITED_REFERENCE_CORRECTION_SHA256,
        "inherited_reference_preimage": INHERITED_REFERENCE_PREIMAGE,
        "inherited_reference_preimage_sha256": INHERITED_REFERENCE_PREIMAGE_SHA256,
        "inherited_reference_counts": EXPECTED_INHERITED_REFERENCE_COUNTS,
        "projected_counts": PROJECTED_COUNTS,
    }
    return _digest(payload)


DOCUMENT_DIGESTS = _verify_source_documents()
V20_LAYER_SHA256 = _layer_digest()
EXPECTED_V20_LAYER_SHA256 = "5344e860bf7939952f4eb37a94eeb1275687fa7b930ab1cb97711808360321e8"
EXPECTED_CLASS_COUNTS = {"S": 76, "C": 52}
EXPECTED_PROBE_COUNTS = {
    "semantic": 768,
    "collision": 118,
    "recovery": 512,
    "role_asset": 384,
}


def _korean_metadata() -> dict[str, object]:
    return {
        "terms": {domain: list(terms) for domain, terms in sorted(KOREAN_DOMAIN_TERMS.items())},
        "terminal_ids": sorted(KOREAN_TERMINAL_IDS),
        "source_ids": sorted(
            source_id for source_id, source in OFFICIAL_SOURCES.items() if source["jurisdiction"] == "KR"
        ),
        "isolation": (
            "provider- and jurisdiction-specific; Korean labels never relabel a different "
            "jurisdictional claim, family record, or legal form"
        ),
    }


def _layer_integrity_metadata() -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "sha256": V20_LAYER_SHA256,
        "expected_sha256": EXPECTED_V20_LAYER_SHA256,
        "official_sources_sha256": OFFICIAL_SOURCES_SHA256,
        "expected_official_sources_sha256": EXPECTED_OFFICIAL_SOURCES_SHA256,
        "base_layer_sha256": EXPECTED_V19_LAYER_SHA256,
        "base_payload_sha256": EXPECTED_BASE_PAYLOAD_SHA256,
        "inherited_reference_correction_sha256": INHERITED_REFERENCE_CORRECTION_SHA256,
        "inherited_reference_preimage_sha256": INHERITED_REFERENCE_PREIMAGE_SHA256,
        "inherited_reference_counts": copy.deepcopy(EXPECTED_INHERITED_REFERENCE_COUNTS),
        "domains": 8,
        "functions": 136,
        "terminal_functions": 128,
        "intents": 128,
        "official_sources": len(OFFICIAL_SOURCES),
    }


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Return the exact prospective V19 payload, materialized only in memory."""

    return merge_v19_with_base(load_v18_source_base(path))


V20_METADATA_KEYS = (
    "official_sources_v20",
    "source_documents_v20",
    "korean_jurisdiction_v20",
    "nearest_function_collisions_v20",
    "within_layer_collisions_v20",
    "rejected_duplicate_families_v20",
    "base_layer_seal_v20",
    "base_payload_seal_v20",
    "inherited_reference_corrections_v20",
    "layer_integrity_v20",
)


def _pre_v20_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V20_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V20_INTENTS}
    result = copy.deepcopy(dict(payload))
    if "inherited_reference_corrections_v20" in result:
        _revert_inherited_reference_corrections(
            result,
            result["inherited_reference_corrections_v20"],
        )
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    for key in V20_METADATA_KEYS:
        result.pop(key, None)
    result["catalog_version"] = CATALOG_V19_VERSION
    result["description"] = CATALOG_V19_DESCRIPTION
    return result


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V20_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V20_INTENTS}
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
    has_metadata = any(key in payload for key in V20_METADATA_KEYS)
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V20CatalogValidationError("partial V20 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V20CatalogValidationError("V20 collides with a different function or intent definition")
    if payload.get("official_sources_v20") != OFFICIAL_SOURCES:
        raise V20CatalogValidationError("V20 official-source registry differs")
    if payload.get("source_documents_v20") != SOURCE_DOCUMENT_METADATA:
        raise V20CatalogValidationError("V20 source-document SHA registry differs")
    if payload.get("korean_jurisdiction_v20") != _korean_metadata():
        raise V20CatalogValidationError("V20 Korean-jurisdiction metadata differs")
    if payload.get("nearest_function_collisions_v20") != {
        key: list(value) for key, value in sorted(NEAREST_EXISTING_FUNCTIONS.items())
    }:
        raise V20CatalogValidationError("V20 nearest-function collision registry differs")
    if payload.get("within_layer_collisions_v20") != [list(row) for row in WITHIN_V20_COLLISIONS]:
        raise V20CatalogValidationError("V20 within-layer collision registry differs")
    if payload.get("rejected_duplicate_families_v20") != list(REJECTED_DUPLICATE_FAMILIES):
        raise V20CatalogValidationError("V20 rejected-duplicate registry differs")
    if payload.get("base_layer_seal_v20") != BASE_LAYER_SEAL:
        raise V20CatalogValidationError("V20 base-layer seal differs")
    if payload.get("base_payload_seal_v20") != {
        "algorithm": "sha256",
        "sha256": EXPECTED_BASE_PAYLOAD_SHA256,
    }:
        raise V20CatalogValidationError("V20 base-payload seal differs")
    _validate_inherited_reference_ledger(
        payload,
        payload.get("inherited_reference_corrections_v20"),
    )
    if payload.get("layer_integrity_v20") != _layer_integrity_metadata():
        raise V20CatalogValidationError("V20 layer-integrity metadata differs")
    if payload.get("catalog_version") != CATALOG_V20_VERSION or payload.get("description") != CATALOG_V20_DESCRIPTION:
        raise V20CatalogValidationError("V20 materialization metadata differs")
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
        r"(?ms)\*\*Prospective terminal seams \(\d+\)\.\*\*\s*(.*?)\*\*Nearest existing collisions",
        source_text,
    )
    return tuple(
        terminal_id
        for block in blocks
        for terminal_id in re.findall(r"`([a-z0-9_]+\.[a-z0-9_]+)`", block)
    )


def _research_rejected_candidate_labels(source_text: str) -> tuple[str, ...]:
    match = re.search(
        r"(?ms)## Explicitly rejected duplicates\s*(.*?)## Cross-candidate collision requirements",
        source_text,
    )
    if match is None:
        return ()
    rows = re.findall(r"(?m)^\|\s*([^|]+?)\s*\|", match.group(1))
    return tuple(value for value in rows if value not in {"Rejected candidate family", "---"})


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


def validate_v20_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate V20 provenance, isolation, safety, and exact V19 composition."""

    errors: list[str] = []
    try:
        current_documents = _verify_source_documents()
    except V20CatalogValidationError as error:
        errors.append(str(error))
        current_documents = {}
    if current_documents != SOURCE_DOCUMENT_SHA256 or DOCUMENT_DIGESTS != SOURCE_DOCUMENT_SHA256:
        errors.append("V20 source-document registry differs")
    if V19_LAYER_SHA256 != EXPECTED_V19_LAYER_SHA256:
        errors.append(
            f"V19 base layer SHA differs: expected {EXPECTED_V19_LAYER_SHA256}, got {V19_LAYER_SHA256}"
        )
    if OFFICIAL_SOURCES_SHA256 != EXPECTED_OFFICIAL_SOURCES_SHA256:
        errors.append(
            f"V20 official-source SHA differs: expected {EXPECTED_OFFICIAL_SOURCES_SHA256}, got {OFFICIAL_SOURCES_SHA256}"
        )
    if V20_LAYER_SHA256 != EXPECTED_V20_LAYER_SHA256 or _layer_digest() != EXPECTED_V20_LAYER_SHA256:
        errors.append(
            f"V20 layer SHA differs: expected {EXPECTED_V20_LAYER_SHA256}, got {V20_LAYER_SHA256}"
        )

    source_text = (ROOT / DESIGN_SOURCE_RELATIVE_PATH).read_text(encoding="utf-8")
    function_ids = [str(item["function_id"]) for item in V20_FUNCTIONS]
    terminal_ids = {
        str(item["function_id"]) for item in V20_FUNCTIONS if item.get("terminal")
    }
    intent_ids = [str(item["intent_id"]) for item in V20_INTENTS]
    domain_terminal_counts = Counter(
        str(item["domain"]) for item in V20_FUNCTIONS if item.get("terminal")
    )
    domain_function_counts = Counter(str(item["domain"]) for item in V20_FUNCTIONS)
    if _duplicates(function_ids) or _duplicates(intent_ids):
        errors.append("V20 contains duplicate function or intent IDs")
    research_terminal_ids = _research_proposed_terminal_ids(source_text)
    if len(research_terminal_ids) != 128 or set(research_terminal_ids) != terminal_ids:
        errors.append("V20 terminal IDs differ from the eight research proposal lists")
    if (
        len(REQUIRED_DOMAINS) != 8
        or len(V20_FUNCTIONS) != 136
        or len(terminal_ids) != 128
        or len(V20_INTENTS) != 128
    ):
        errors.append("V20 requires 8 domains, 8 hubs, 128 terminals, 136 functions, and 128 intents")
    if dict(sorted(domain_terminal_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"V20 terminal counts differ: {dict(sorted(domain_terminal_counts.items()))}")
    if dict(sorted(domain_function_counts.items())) != EXPECTED_DOMAIN_FUNCTION_COUNTS:
        errors.append(f"V20 function counts differ: {dict(sorted(domain_function_counts.items()))}")
    if len(REJECTED_DUPLICATE_FAMILIES) != 16 or len(set(REJECTED_DUPLICATE_FAMILIES)) != 16:
        errors.append("V20 requires exactly sixteen distinct rejected duplicate families")
    if len(_research_rejected_candidate_labels(source_text)) != 16:
        errors.append("V20 research rejected-candidate table must contain exactly sixteen families")

    sensitive = sum(
        bool(item["terminal"])
        and item.get("classification") == "S"
        and item.get("view_only") is True
        and item.get("state_changing") is False
        for item in V20_FUNCTIONS
    )
    consequential = sum(
        bool(item["terminal"])
        and item.get("classification") == "C"
        and item.get("consequential") is True
        and item.get("state_changing") is True
        for item in V20_FUNCTIONS
    )
    if {"S": sensitive, "C": consequential} != EXPECTED_CLASS_COUNTS:
        errors.append(f"V20 S/C counts differ: S={sensitive}, C={consequential}")

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
    functions_by_id = {str(item["function_id"]): item for item in V20_FUNCTIONS}
    goals_ko: list[str] = []
    goals_en: list[str] = []
    purposes_ko: list[str] = []
    purposes_en: list[str] = []
    semantic_signatures: list[
        tuple[frozenset[str], frozenset[str], frozenset[str], frozenset[str]]
    ] = []
    for function in V20_FUNCTIONS:
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
        if (
            not function.get("role_hints")
            or not function.get("asset_cues")
            or not function.get("state_cues", {}).get("jurisdiction")
            or not function.get("provider_scopes")
        ):
            errors.append(f"{function_id}: missing role, asset, state, provider, or jurisdiction semantics")
        if function["terminal"]:
            feature = REVIEWED_FEATURE_BY_ID[function_id]
            goals_ko.append(feature.goal_ko)
            goals_en.append(feature.goal_en)
            purposes_ko.append(feature.purpose_ko)
            purposes_en.append(feature.purpose_en)
            semantic_signatures.append(_function_semantic_dimensions(function))
            if any(feature.name_ko not in str(alias) for alias in function["aliases"]["ko-KR"]):
                errors.append(f"{function_id}: Korean alias lacks governed terminal label")
            if any(
                feature.name_en.casefold() not in str(alias).casefold()
                for alias in function["aliases"]["en-US"]
            ):
                errors.append(f"{function_id}: English alias lacks governed terminal label")
            if function.get("classification") != feature.classification:
                errors.append(f"{function_id}: classification differs")
            if function.get("name_ko") != feature.name_ko or function.get("name_en") != feature.name_en:
                errors.append(f"{function_id}: bilingual name differs")
            if function.get("representative_goals") != {
                "ko-KR": feature.goal_ko,
                "en-US": feature.goal_en,
            }:
                errors.append(f"{function_id}: representative goal differs")
            if function.get("purpose_by_locale") != {
                "ko-KR": feature.purpose_ko,
                "en-US": feature.purpose_en,
            }:
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
            errors.append(f"V20 contains duplicate {label}")
    if _duplicates(repr(value) for value in semantic_signatures):
        errors.append("V20 contains duplicate role/asset/state/jurisdiction terminal scopes")

    for intent in V20_INTENTS:
        target = str(intent["terminal_function"])
        feature = REVIEWED_FEATURE_BY_ID[target]
        if str(intent["intent_id"]) != f"v20_{target.replace('.', '_')}":
            errors.append(f"{target}: intent ID differs")
        if (
            intent["patterns_by_locale"]["ko-KR"][0] != feature.goal_ko
            or intent["patterns_by_locale"]["en-US"][0] != feature.goal_en
        ):
            errors.append(f"{target}: representative patterns differ")
        if any(not hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"]):
            errors.append(f"{target}: Korean goal pattern lacks Hangul")
        if (
            len(intent["patterns_by_locale"]["ko-KR"]) < 5
            or len(intent["patterns_by_locale"]["en-US"]) < 5
        ):
            errors.append(f"{target}: insufficient bilingual goal patterns")
        gates = [
            rule
            for rule in intent["goal_rules"]
            if rule.get("rule_kind") == "v20_role_asset_state_jurisdiction_gate"
        ]
        if len(gates) != 1 or gates[0].get("v20_required_dimension_count") != 4:
            errors.append(f"{target}: missing four-dimension gate")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != target:
            errors.append(f"{target}: route differs")
        if intent.get("terminal_condition") != {
            "stop_policy": "stop_before_action",
            "user_owned_final_press": True,
        }:
            errors.append(f"{target}: terminal condition differs")
        gate = intent.get("resolution_gate", {})
        if (
            gate.get("minimum_positive_dimensions") != 4
            or gate.get("on_missing_dimension") != "fail_closed"
            or gate.get("fail_closed_to") != f"{target.split('.', 1)[0]}.hub"
        ):
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
            errors.append(f"duplicate normalized V20 source URL: {normalized}")
        normalized_urls.add(normalized)
        record_without_hash = {
            key: value for key, value in source.items() if key != "source_record_sha256"
        }
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
    if len(OFFICIAL_SOURCES) != 63:
        errors.append(f"V20 requires exactly 63 direct official sources; got {len(OFFICIAL_SOURCES)}")
    research_urls = _research_direct_urls(source_text)
    if normalized_urls != research_urls:
        errors.append(
            f"V20 official registry differs from research URLs: registry={len(normalized_urls)}, research={len(research_urls)}"
        )
    if mapped_terminal_union != terminal_ids or set(DOMAIN_TERMINAL_SOURCE_IDS) != terminal_ids:
        errors.append("V20 official source-to-terminal mapping is incomplete")
    if referenced_source_ids != set(OFFICIAL_SOURCES):
        errors.append("V20 official registry has orphan or missing source records")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS:
        errors.append("V20 domain source registry differs")
    for domain in REQUIRED_DOMAINS:
        if (
            per_domain_jurisdiction[(domain, "NON_KR")] < 5
            or per_domain_jurisdiction[(domain, "KR")] < 1
        ):
            errors.append(
                f"{domain}: requires at least five non-Korean and one Korean official lifecycle source"
            )
    if KOREAN_TERMINAL_IDS != terminal_ids:
        errors.append("V20 Korean official evidence must reach all 128 terminal seams")
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
        errors.append(f"V20 derived probe cardinality differs: {actual_probe_counts}")
    actual_correction_counts = {
        "bad_ids": len(INHERITED_REFERENCE_CORRECTION_BY_BAD_ID),
        "owner_intents": len(INHERITED_REFERENCE_PREIMAGE),
        "references": sum(len(values) for values in INHERITED_REFERENCE_PREIMAGE.values()),
        "replacements": sum(
            bool(correction.replacements) for correction in INHERITED_REFERENCE_CORRECTIONS
        ),
        "removals": sum(
            not correction.replacements for correction in INHERITED_REFERENCE_CORRECTIONS
        ),
    }
    if actual_correction_counts != EXPECTED_INHERITED_REFERENCE_COUNTS:
        errors.append(
            f"V20 inherited-reference correction counts differ: {actual_correction_counts}"
        )
    if len(INHERITED_REFERENCE_CORRECTIONS) != len(
        INHERITED_REFERENCE_CORRECTION_BY_BAD_ID
    ):
        errors.append("V20 inherited-reference correction bad IDs are duplicated")

    if base_payload is None:
        base = load_base_catalog()
    else:
        base = copy.deepcopy(dict(base_payload))
    try:
        materialized = _materialization_state(base)
    except V20CatalogValidationError as error:
        errors.append(str(error))
        materialized = False
    pre_v20 = _pre_v20_payload(base)
    del base
    if (
        pre_v20.get("catalog_version") != CATALOG_V19_VERSION
        or pre_v20.get("description") != CATALOG_V19_DESCRIPTION
        or len(pre_v20.get("functions", [])) != BASELINE_COUNTS["functions"]
        or len(pre_v20.get("intents", [])) != BASELINE_COUNTS["intents"]
        or len({str(item["domain"]) for item in pre_v20.get("functions", [])})
        != BASELINE_COUNTS["domains"]
    ):
        errors.append("V20 base must be the exact prospective 224-domain V19 payload")
    actual_base_digest = _digest(pre_v20)
    if actual_base_digest != EXPECTED_BASE_PAYLOAD_SHA256:
        errors.append(
            f"V20 exact V19-composed base payload SHA differs: expected {EXPECTED_BASE_PAYLOAD_SHA256}, got {actual_base_digest}"
        )
    if pre_v20.get("layer_integrity_v19", {}).get("sha256") != EXPECTED_V19_LAYER_SHA256:
        errors.append("V20 base does not carry the final V19 layer seal")
    corrected_pre_v20 = copy.deepcopy(pre_v20)
    try:
        correction_ledger = _apply_inherited_reference_corrections(corrected_pre_v20)
        correction_trial = copy.deepcopy(corrected_pre_v20)
        _revert_inherited_reference_corrections(correction_trial, correction_ledger)
        if correction_trial != pre_v20:
            errors.append("V20 inherited-reference correction is not exactly reversible")
        del correction_trial
    except V20CatalogValidationError as error:
        errors.append(str(error))
        correction_ledger = {}
    base_function_ids = {str(item["function_id"]) for item in pre_v20.get("functions", [])}
    base_intent_ids = {str(item["intent_id"]) for item in pre_v20.get("intents", [])}
    base_domains = {str(item["domain"]) for item in pre_v20.get("functions", [])}
    if set(function_ids).intersection(base_function_ids):
        errors.append("V20 function IDs collide with the V19-composed baseline")
    if set(intent_ids).intersection(base_intent_ids):
        errors.append("V20 intent IDs collide with the V19-composed baseline")
    if REQUIRED_DOMAINS.intersection(base_domains):
        errors.append("V20 domains collide with the V19-composed baseline")
    nearest_functions = {
        neighbor for values in NEAREST_EXISTING_FUNCTIONS.values() for neighbor in values
    }
    if not nearest_functions <= base_function_ids:
        errors.append(
            f"V20 nearest-function registry contains non-baseline IDs: {sorted(nearest_functions - base_function_ids)}"
        )
    avoid_roots = {domain.avoid_root for domain in REVIEWED_DOMAINS}
    if not avoid_roots <= base_function_ids:
        errors.append(
            f"V20 collision handoffs contain non-baseline roots: {sorted(avoid_roots - base_function_ids)}"
        )
    expected_v19_functions = {str(item["function_id"]): item for item in V19_FUNCTIONS}
    expected_v19_intents = {str(item["intent_id"]): item for item in V19_INTENTS}
    present_v19_functions = {
        str(item["function_id"]): item
        for item in pre_v20.get("functions", [])
        if str(item["function_id"]) in expected_v19_functions
    }
    present_v19_intents = {
        str(item["intent_id"]): item
        for item in pre_v20.get("intents", [])
        if str(item["intent_id"]) in expected_v19_intents
    }
    if present_v19_functions != expected_v19_functions or present_v19_intents != expected_v19_intents:
        errors.append("prospective V19 layer differs before V20")

    base_terminal_dimensions = [
        (str(item["function_id"]), _function_semantic_dimensions(item))
        for item in corrected_pre_v20.get("functions", [])
        if item.get("terminal")
    ]
    for function in V20_FUNCTIONS:
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
        raise V20CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V20_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V20_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "domain_function_counts": dict(sorted(domain_function_counts.items())),
        "sensitive_reads": sensitive,
        "state_changing": consequential,
        "official_sources": len(OFFICIAL_SOURCES),
        "official_sources_sha256": OFFICIAL_SOURCES_SHA256,
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "korean_sources": sum(
            source["jurisdiction"] == "KR" for source in OFFICIAL_SOURCES.values()
        ),
        "korean_terminals": len(KOREAN_TERMINAL_IDS),
        "source_documents": copy.deepcopy(DOCUMENT_DIGESTS),
        "source_orphans": len(set(OFFICIAL_SOURCES) - referenced_source_ids),
        "base_payload_sha256": actual_base_digest,
        "inherited_reference_corrections": len(
            correction_ledger.get("corrections", {})
        ),
        "inherited_reference_bad_ids": len(INHERITED_REFERENCE_CORRECTION_BY_BAD_ID),
        "inherited_reference_count": EXPECTED_INHERITED_REFERENCE_COUNTS["references"],
        "layer_sha256": V20_LAYER_SHA256,
        "semantic_probes": len(semantic),
        "collision_probes": len(collisions),
        "recovery_probes": len(recovery),
        "role_asset_probes": len(isolation),
        "projected_counts": copy.deepcopy(PROJECTED_COUNTS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, non-mutating, idempotent V19+V20 copy."""

    stats = validate_v20_data(base_payload)
    if stats["materialized"]:
        return copy.deepcopy(dict(base_payload))
    merged = _pre_v20_payload(base_payload)
    correction_ledger = _apply_inherited_reference_corrections(merged)
    merged["catalog_version"] = CATALOG_V20_VERSION
    merged["description"] = CATALOG_V20_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V20_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V20_INTENTS)]
    merged["official_sources_v20"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_documents_v20"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    merged["korean_jurisdiction_v20"] = copy.deepcopy(_korean_metadata())
    merged["nearest_function_collisions_v20"] = {
        key: list(value) for key, value in sorted(NEAREST_EXISTING_FUNCTIONS.items())
    }
    merged["within_layer_collisions_v20"] = [list(row) for row in WITHIN_V20_COLLISIONS]
    merged["rejected_duplicate_families_v20"] = list(REJECTED_DUPLICATE_FAMILIES)
    merged["base_layer_seal_v20"] = copy.deepcopy(BASE_LAYER_SEAL)
    merged["base_payload_seal_v20"] = copy.deepcopy(BASE_PAYLOAD_SEAL)
    merged["inherited_reference_corrections_v20"] = correction_ledger
    merged["layer_integrity_v20"] = copy.deepcopy(_layer_integrity_metadata())
    return merged


def main() -> int:
    print(json.dumps(validate_v20_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
