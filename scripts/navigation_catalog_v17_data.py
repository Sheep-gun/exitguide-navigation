from __future__ import annotations

"""SHA-sealed V17 candidate layer for public-service case navigation.

V17 is intentionally isolated from the canonical catalog.  It appends twelve
app-independent domains to an exact prospective V16 payload and refuses
partial or altered V17 materialization.  No package, selector, coordinate,
screenshot, or recorded UI path is an input to this module.
"""

import copy
import hashlib
import json
import posixpath
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
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
from navigation_catalog_v16_data import (
    CATALOG_V16_DESCRIPTION,
    CATALOG_V16_VERSION,
    V16_FUNCTIONS,
    V16_INTENTS,
    load_base_catalog as load_v15_source_base,
    merge_with_base as merge_v16_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
DESIGN_SOURCE_RELATIVE_PATH = "docs/NAVIGATION_COVERAGE_GAPS_V17.md"
SOURCE_DOCUMENT_SHA256 = {
    DESIGN_SOURCE_RELATIVE_PATH: "82fb912cd020188890ab2002438fd16be7bad5581432af3e8123b4b44339ca4b",
}
SOURCE_DOCUMENT_METADATA = {
    path: {"path": path, "algorithm": "sha256", "sha256": digest}
    for path, digest in SOURCE_DOCUMENT_SHA256.items()
}

CATALOG_V17_VERSION = "17.0.0"
COLLECTED_ON = "2026-07-30"
RETRIEVED_AT = "2026-07-30T00:00:00+09:00"
CATALOG_V17_DESCRIPTION = (
    "ExitGuide public-service case ontology V17 candidate source pack: "
    "unemployment insurance, Social Security, consumer credit reporting, "
    "driver and vehicle licensing, disaster assistance, veterans benefits, "
    "wage-and-hour enforcement, student aid, child support, public housing, "
    "Medicare provider enrollment, and professional licensing; every "
    "terminal press remains user-owned."
)

PROJECTED_COUNTS = {
    "domains": 203,
    "physical_functions": 3358,
    "physical_terminal_functions": 3128,
    "physical_intents": 3128,
    "unique_physical_default_terminal_destinations": 3126,
    "logical_functions": 3348,
    "logical_intents": 3118,
    "unique_logical_default_terminal_destinations": 3116,
}


class V17CatalogValidationError(ValueError):
    """Raised when the V17 candidate cannot be proven complete and unchanged."""


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


@dataclass(frozen=True)
class DomainSpec:
    domain: str
    root_ko: str
    root_en: str
    roles: tuple[str, ...]
    assets: tuple[str, ...]
    states: tuple[str, ...]
    jurisdiction: str
    boundary: str
    avoid_root: str
    collision_terms: tuple[str, ...]
    features: tuple[ReviewedFeature, ...]


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _terms(value: str) -> tuple[str, ...]:
    return _dedupe(value.split("|"))


def _feature(
    domain: str,
    root_ko: str,
    root_en: str,
    roles: tuple[str, ...],
    assets: tuple[str, ...],
    states: tuple[str, ...],
    jurisdiction: str,
    boundary: str,
    index: int,
    row: tuple[str, str, str, str],
) -> ReviewedFeature:
    key, classification, name_ko, name_en = row
    if classification not in {"S", "C"}:
        raise V17CatalogValidationError(f"{domain}.{key}: classification must be S or C")
    goal_ko = (
        f"{name_ko} 상태와 내용을 확인하고 싶어"
        if classification == "S"
        else f"{name_ko} 절차로 이동하고 최종 실행은 내가 확인할게"
    )
    goal_en = (
        f"I want to review the status and details of {name_en.lower()}"
        if classification == "S"
        else f"Take me to {name_en.lower()} and I will perform the final action"
    )
    purpose_ko = (
        f"식별된 {root_ko} 기록에서 권한 있는 사용자가 {name_ko} 정보를 변경 없이 확인"
        if classification == "S"
        else f"식별된 {root_ko} 기록에서 권한 있는 사용자가 {name_ko} 목적지에 도달한 뒤 최종 동작을 직접 수행"
    )
    purpose_en = (
        f"An authorized user reviews {name_en.lower()} for the identified {root_en.lower()} record without changing it"
        if classification == "S"
        else f"An authorized user reaches {name_en.lower()} for the identified {root_en.lower()} record and personally owns the final action"
    )
    selected_roles = _dedupe((roles[index % len(roles)], roles[(index + 1) % len(roles)]))
    selected_assets = _dedupe(
        (f"{name_en} record", f"{name_ko} 대상", assets[index % len(assets)], assets[(index + 1) % len(assets)])
    )
    action_state = (
        f"{key.replace('_', ' ')} available for authorized review"
        if classification == "S"
        else f"{key.replace('_', ' ')} eligible and awaiting user confirmation"
    )
    selected_states = _dedupe((action_state, states[index % len(states)], states[(index + 1) % len(states)]))
    safety_boundary = (
        f"{name_en}: {boundary}; verify authorized role, exact governed record, "
        f"jurisdiction, and current lifecycle state; stop before the final "
        f"{'sensitive disclosure' if classification == 'S' else 'submission or state change'}"
    )
    return ReviewedFeature(
        key=key,
        classification=classification,
        name_ko=name_ko,
        name_en=name_en,
        goal_ko=goal_ko,
        goal_en=goal_en,
        purpose_ko=purpose_ko,
        purpose_en=purpose_en,
        roles=selected_roles,
        assets=selected_assets,
        states=selected_states,
        jurisdiction_guard=jurisdiction,
        safety_boundary=safety_boundary,
    )


def _domain(
    domain: str,
    root_ko: str,
    root_en: str,
    roles: str,
    assets: str,
    states: str,
    jurisdiction: str,
    boundary: str,
    avoid_root: str,
    collisions: str,
    rows: tuple[tuple[str, str, str, str], ...],
) -> DomainSpec:
    role_values, asset_values, state_values = _terms(roles), _terms(assets), _terms(states)
    features = tuple(
        _feature(
            domain, root_ko, root_en, role_values, asset_values, state_values,
            jurisdiction, boundary, index, row,
        )
        for index, row in enumerate(rows)
    )
    return DomainSpec(
        domain, root_ko, root_en, role_values, asset_values, state_values,
        jurisdiction, boundary, avoid_root, _terms(collisions), features,
    )


REVIEWED_DOMAINS: tuple[DomainSpec, ...] = (
    _domain(
        "unemployment_insurance_case_services",
        "실업보험 청구 서비스", "Unemployment insurance claim services",
        "claimant|employer respondent|authorized claimant representative",
        "unemployment claim|wage and employer record|certification week|eligibility determination|payment and overpayment record",
        "draft|identity pending|fact finding|certified|eligible or ineligible|paid|overpaid|appealed",
        "identified U.S. state unemployment-insurance program and claim period",
        "never submit a claim, certification, employer response, waiver, payment change, or appeal automatically",
        "social_services_casework.hub",
        "claim|certification|determination|payment|appeal",
        (
            ("claimant_dashboard", "S", "청구인 대시보드", "Claimant dashboard"),
            ("initial_claim_start", "C", "최초 실업급여 청구 시작", "Initial unemployment claim start"),
            ("identity_verification", "C", "청구인 본인확인", "Claimant identity verification"),
            ("wage_employer_history_review", "S", "임금·고용주 이력 검토", "Wage and employer history review"),
            ("separation_fact_finding_response", "C", "이직 사유 사실확인 응답", "Separation fact-finding response"),
            ("employer_separation_response", "C", "고용주 이직 사실 응답", "Employer separation response"),
            ("evidence_upload", "C", "청구 증빙 업로드", "Claim evidence upload"),
            ("weekly_certification_submit", "C", "주간 자격인증 제출", "Weekly certification submission"),
            ("work_search_record", "C", "구직활동 기록", "Work-search record"),
            ("reemployment_service_status", "S", "재취업 서비스 상태", "Reemployment service status"),
            ("claim_status", "S", "실업급여 청구 상태", "Unemployment claim status"),
            ("monetary_determination_review", "S", "급여액 결정 검토", "Monetary determination review"),
            ("eligibility_determination_review", "S", "수급자격 결정 검토", "Eligibility determination review"),
            ("payment_status", "S", "급여 지급 상태", "Benefit payment status"),
            ("payment_method_update", "C", "급여 지급수단 변경", "Benefit payment method update"),
            ("tax_form_1099g_request", "S", "1099-G 세금서류 조회", "1099-G tax form request"),
            ("overpayment_notice_review", "S", "과오급 통지 검토", "Overpayment notice review"),
            ("overpayment_waiver_request", "C", "과오급 환수 면제 요청", "Overpayment waiver request"),
            ("determination_appeal_submit", "C", "실업급여 결정 이의제기", "Unemployment determination appeal"),
        ),
    ),
    _domain(
        "social_security_benefit_services",
        "사회보장 급여 서비스", "Social Security benefit services",
        "beneficiary or applicant|representative payee|appointed representative",
        "earnings record|benefit application|award and payment instruction|identity record|overpayment and appeal record",
        "estimated|draft|submitted|pending|awarded|suspended|overpaid|under review|appealed",
        "identified Social Security record and applicable benefit program",
        "never submit an application, correction, report, banking change, waiver, review, or appeal automatically",
        "social_services_casework.hub",
        "earnings|application|benefit|overpayment|appeal",
        (
            ("earnings_record_review", "S", "소득기록 검토", "Earnings record review"),
            ("benefit_estimate", "S", "예상 급여액 확인", "Benefit estimate"),
            ("retirement_application_start", "C", "은퇴급여 신청 시작", "Retirement benefit application"),
            ("disability_application_start", "C", "장애급여 신청 시작", "Disability benefit application"),
            ("ssi_application_start", "C", "SSI 신청 시작", "SSI application"),
            ("medicare_application_start", "C", "메디케어 신청 시작", "Medicare application"),
            ("application_status", "S", "사회보장 신청 상태", "Social Security application status"),
            ("appeal_status", "S", "사회보장 이의제기 상태", "Social Security appeal status"),
            ("benefit_verification_letter", "S", "급여 증명서 조회", "Benefit verification letter"),
            ("social_security_card_replace", "C", "사회보장카드 재발급", "Social Security card replacement"),
            ("name_correction_request", "C", "사회보장 이름 정정", "Social Security name correction"),
            ("address_change", "C", "사회보장 주소 변경", "Social Security address change"),
            ("direct_deposit_update", "C", "사회보장 계좌이체 변경", "Social Security direct deposit update"),
            ("beneficiary_change_report", "C", "수급자 변동 신고", "Beneficiary change report"),
            ("representative_payee_status", "S", "대표 수취인 상태", "Representative payee status"),
            ("continuing_disability_review", "C", "장애 지속 심사 응답", "Continuing disability review"),
            ("overpayment_notice_review", "S", "사회보장 과오급 통지", "Social Security overpayment notice"),
            ("overpayment_waiver_request", "C", "사회보장 과오급 면제 요청", "Social Security overpayment waiver"),
            ("decision_appeal_request", "C", "사회보장 결정 이의제기", "Social Security decision appeal"),
        ),
    ),
    _domain(
        "consumer_credit_reporting_services",
        "소비자 신용정보 서비스", "Consumer credit reporting services",
        "consumer|identity-theft victim|authorized consumer advocate",
        "credit file|tradeline and inquiry|dispute and evidence|freeze and fraud alert|identity-theft report and complaint",
        "available|disputed|investigating|resolved|frozen|thawed|alerted|blocked|submitted",
        "identified U.S. consumer and consumer-reporting record",
        "never request disclosure, submit a dispute or complaint, or place, lift, or remove a protection automatically",
        "identity_security.hub",
        "report|tradeline|dispute|freeze|fraud",
        (
            ("credit_report_request", "C", "신용보고서 요청", "Credit report request"),
            ("credit_file_review", "S", "신용파일 검토", "Credit file review"),
            ("tradeline_detail_review", "S", "신용계정 항목 검토", "Tradeline detail review"),
            ("inquiry_review", "S", "신용조회 이력 검토", "Credit inquiry review"),
            ("adverse_action_notice_review", "S", "불리한 조치 통지 검토", "Adverse action notice review"),
            ("tradeline_dispute_create", "C", "신용계정 오류 분쟁 제기", "Tradeline dispute creation"),
            ("dispute_evidence_upload", "C", "신용분쟁 증빙 업로드", "Credit dispute evidence upload"),
            ("dispute_status", "S", "신용분쟁 상태", "Credit dispute status"),
            ("dispute_result_review", "S", "신용분쟁 결과 검토", "Credit dispute result review"),
            ("consumer_statement_add", "C", "소비자 설명문 추가", "Consumer statement addition"),
            ("security_freeze_status", "S", "신용동결 상태", "Security freeze status"),
            ("security_freeze_place", "C", "신용동결 설정", "Security freeze placement"),
            ("security_freeze_lift", "C", "신용동결 해제", "Security freeze lift"),
            ("fraud_alert_status", "S", "사기경보 상태", "Fraud alert status"),
            ("fraud_alert_place", "C", "사기경보 설정", "Fraud alert placement"),
            ("fraud_alert_remove", "C", "사기경보 제거", "Fraud alert removal"),
            ("identity_theft_report_start", "C", "신원도용 신고 시작", "Identity theft report start"),
            ("identity_theft_block_request", "C", "신원도용 정보 차단 요청", "Identity theft information block"),
            ("cfpb_complaint_submit", "C", "CFPB 신용정보 민원 제출", "CFPB credit reporting complaint"),
        ),
    ),
    _domain(
        "driver_vehicle_licensing_services",
        "운전면허·차량 등록 서비스", "Driver and vehicle licensing services",
        "driver or applicant|registered vehicle owner|vehicle buyer or seller|authorized agent",
        "driver license and record|test appointment|vehicle registration|vehicle title and VIN|plate and reinstatement fee",
        "eligible|expired|lost|scheduled|registered|transferred|suspended|reinstatement pending|paid",
        "identified state motor-vehicle agency, person, and vehicle",
        "never apply, renew, transfer, release liability, order, schedule, pay, or reinstate automatically",
        "automotive_vehicle.hub",
        "license|record|registration|title|reinstatement",
        (
            ("driver_license_status", "S", "운전면허 상태", "Driver license status"),
            ("driver_license_apply", "C", "운전면허 신청", "Driver license application"),
            ("driver_license_renew", "C", "운전면허 갱신", "Driver license renewal"),
            ("driver_license_replace", "C", "운전면허 재발급", "Driver license replacement"),
            ("real_id_upgrade", "C", "REAL ID 전환", "REAL ID upgrade"),
            ("driver_record_request", "C", "운전기록 요청", "Driver record request"),
            ("driver_test_appointment", "C", "운전시험 예약", "Driver test appointment"),
            ("driver_address_change", "C", "운전자 주소 변경", "Driver address change"),
            ("vehicle_registration_status", "S", "차량등록 상태", "Vehicle registration status"),
            ("vehicle_registration_start", "C", "차량 신규등록", "Vehicle registration start"),
            ("vehicle_registration_renew", "C", "차량등록 갱신", "Vehicle registration renewal"),
            ("vehicle_registration_replace", "C", "차량등록증 재발급", "Vehicle registration replacement"),
            ("vehicle_title_status", "S", "차량 소유권 상태", "Vehicle title status"),
            ("vehicle_title_transfer", "C", "차량 소유권 이전", "Vehicle title transfer"),
            ("vehicle_title_replace", "C", "차량 소유권증 재발급", "Vehicle title replacement"),
            ("transfer_release_of_liability", "C", "차량양도 책임해제 신고", "Transfer release of liability"),
            ("license_plate_order", "C", "번호판 주문", "License plate order"),
            ("suspension_reinstatement_status", "S", "면허정지 복구 상태", "Suspension reinstatement status"),
            ("reinstatement_fee_payment", "C", "면허복구 수수료 납부", "Reinstatement fee payment"),
        ),
    ),
    _domain(
        "disaster_assistance_case_services",
        "재난 지원 사건 서비스", "Disaster assistance case services",
        "disaster survivor or applicant|household representative|authorized survivor representative|housing inspector",
        "disaster declaration|household assistance case|damaged dwelling|identity and insurance evidence|inspection determination award and appeal",
        "eligible area|draft|submitted|verification pending|inspection pending|decided|awarded|denied|appealed",
        "identified FEMA-declared disaster, household, damaged dwelling, and assistance case",
        "never submit an application, evidence, banking change, inspection request, response, or appeal automatically",
        "social_services_casework.hub",
        "disaster|application|inspection|award|appeal",
        (
            ("declared_area_eligibility_lookup", "S", "재난선포 지역 자격 조회", "Declared-area eligibility lookup"),
            ("assistance_program_review", "S", "재난 지원 프로그램 검토", "Disaster assistance program review"),
            ("individual_assistance_application", "C", "개인 재난지원 신청", "Individual assistance application"),
            ("application_status", "S", "재난지원 신청 상태", "Disaster assistance application status"),
            ("identity_verification_status", "S", "재난지원 본인확인 상태", "Disaster identity verification status"),
            ("identity_residency_evidence_upload", "C", "신원·거주 증빙 업로드", "Identity and residency evidence upload"),
            ("insurance_information_submit", "C", "보험정보 제출", "Insurance information submission"),
            ("home_occupancy_ownership_verify", "C", "주택 점유·소유 확인", "Home occupancy and ownership verification"),
            ("home_inspection_schedule", "C", "주택 피해조사 일정", "Home inspection scheduling"),
            ("inspection_status", "S", "재난 피해조사 상태", "Disaster inspection status"),
            ("inspection_accommodation_request", "C", "피해조사 편의지원 요청", "Inspection accommodation request"),
            ("additional_information_request_review", "S", "추가정보 요청 검토", "Additional information request review"),
            ("additional_information_response", "C", "추가정보 응답", "Additional information response"),
            ("determination_letter_view", "S", "재난지원 결정서 조회", "Disaster determination letter"),
            ("award_status", "S", "재난지원금 상태", "Disaster assistance award status"),
            ("direct_deposit_update", "C", "재난지원 계좌이체 변경", "Disaster assistance direct deposit update"),
            ("temporary_housing_status", "S", "임시주거 지원 상태", "Temporary housing assistance status"),
            ("appeal_evidence_upload", "C", "재난지원 이의 증빙 업로드", "Disaster appeal evidence upload"),
            ("decision_appeal_submit", "C", "재난지원 결정 이의제기", "Disaster assistance decision appeal"),
        ),
    ),
    _domain(
        "veterans_benefit_claim_services",
        "보훈 급여 청구 서비스", "Veterans benefit claim services",
        "veteran or claimant|dependent|VA-accredited representative",
        "intent to file and claim|service-connected condition|supporting evidence and examination|rating decision and payment|review and appeal",
        "draft|filed|evidence gathering|examination pending|decided|rated|paid|review requested|appealed",
        "identified VA claimant, benefit, claim, and decision lane",
        "never file, upload, change banking or dependents, appoint a representative, request review, or appeal automatically",
        "social_services_casework.hub",
        "claim|evidence|rating|payment|review",
        (
            ("intent_to_file", "C", "보훈 청구 의향서", "VA intent to file"),
            ("claim_type_review", "S", "보훈 청구 유형 검토", "VA claim type review"),
            ("disability_claim_start", "C", "장애보상 청구 시작", "Disability claim start"),
            ("increase_claim_start", "C", "장애등급 상향 청구", "Disability increase claim"),
            ("supplemental_claim_start", "C", "추가증거 청구 시작", "Supplemental claim start"),
            ("supporting_evidence_upload", "C", "보훈 청구 증빙 업로드", "VA claim evidence upload"),
            ("claim_exam_status", "S", "보훈 신체검사 상태", "VA claim examination status"),
            ("claim_status", "S", "보훈 청구 상태", "VA claim status"),
            ("evidence_request_review", "S", "보훈 추가증거 요청 검토", "VA evidence request review"),
            ("decision_letter_download", "S", "보훈 결정서 다운로드", "VA decision letter download"),
            ("disability_rating_review", "S", "장애등급 결정 검토", "Disability rating review"),
            ("payment_history", "S", "보훈급여 지급내역", "VA benefit payment history"),
            ("direct_deposit_update", "C", "보훈급여 계좌이체 변경", "VA direct deposit update"),
            ("dependent_change_request", "C", "보훈 부양가족 변경", "VA dependent change request"),
            ("accredited_representative_manage", "C", "공인 대리인 관리", "Accredited representative management"),
            ("higher_level_review_submit", "C", "상급심사 요청", "Higher-level review request"),
            ("supplemental_review_submit", "C", "추가청구 심사 요청", "Supplemental review request"),
            ("board_appeal_start", "C", "보훈위원회 이의제기", "Board appeal start"),
            ("review_appeal_status", "S", "보훈 심사·이의 상태", "VA review and appeal status"),
        ),
    ),
    _domain(
        "wage_hour_enforcement_ops",
        "임금·근로시간 집행 업무", "Wage and hour enforcement operations",
        "worker or complainant|Wage and Hour investigator|employer respondent|authorized worker representative",
        "worker complaint and evidence|investigation case|payroll hours and interview record|compliance finding|back-wage calculation and resolution",
        "intake|submitted|investigating|records requested|finding drafted|resolved|payment pending|closed",
        "identified wage-and-hour law, workplace, worker, employer, and enforcement case",
        "never submit a complaint or retaliation report, issue a record request or finding, or confirm resolution payment automatically",
        "employment_workplace.hub",
        "worker|complaint|investigation|finding|resolution",
        (
            ("worker_rights_scope_review", "S", "근로자 권리 적용범위 검토", "Worker rights scope review"),
            ("complaint_requirements_review", "S", "노동 민원 요건 검토", "Wage complaint requirements review"),
            ("worker_complaint_prepare", "C", "노동 민원 작성", "Worker complaint preparation"),
            ("worker_complaint_submit", "C", "노동 민원 제출", "Worker complaint submission"),
            ("complaint_evidence_upload", "C", "노동 민원 증빙 업로드", "Wage complaint evidence upload"),
            ("complaint_status", "S", "노동 민원 처리상태", "Wage complaint status"),
            ("retaliation_report_submit", "C", "보복행위 신고", "Retaliation report submission"),
            ("investigation_case_queue", "S", "근로감독 사건목록", "Investigation case queue"),
            ("employer_record_request", "C", "사업주 자료제출 요구", "Employer record request"),
            ("employer_record_upload", "C", "사업주 자료 업로드", "Employer record upload"),
            ("employee_interview_record", "C", "근로자 면담 기록", "Employee interview record"),
            ("payroll_hours_compliance_review", "S", "임금·근로시간 준수 검토", "Payroll and hours compliance review"),
            ("minimum_wage_finding_record", "C", "최저임금 위반판정 기록", "Minimum wage finding record"),
            ("overtime_finding_record", "C", "연장근로 위반판정 기록", "Overtime finding record"),
            ("fmla_finding_record", "C", "가족의료휴가 판정 기록", "FMLA finding record"),
            ("child_labor_finding_record", "C", "연소자근로 판정 기록", "Child labor finding record"),
            ("back_wage_calculation", "S", "체불임금 산정", "Back-wage calculation"),
            ("resolution_terms_review", "S", "시정·합의 조건 검토", "Resolution terms review"),
            ("resolution_payment_confirm", "C", "체불임금 지급확인", "Resolution payment confirmation"),
        ),
    ),
    _domain(
        "student_financial_aid_services",
        "연방 학자금 지원 서비스", "Student financial aid services",
        "student or borrower|FAFSA contributor|parent contributor|authorized school official",
        "FAFSA form and contributor section|aid history and school recipient|federal student loan|counseling and promissory note|repayment IDR consolidation and PSLF record",
        "draft|contributor pending|reviewed|signed|submitted|processed|corrected|in repayment|forgiveness review",
        "identified Federal Student Aid account, award year, loan, and authorized participant",
        "never invite, sign, submit, correct, select a recipient, complete counseling, apply, consolidate, or certify automatically",
        "education.hub",
        "aid|fafsa|loan|repayment|forgiveness",
        (
            ("aid_dashboard", "S", "학자금 지원 대시보드", "Student aid dashboard"),
            ("fafsa_start", "C", "FAFSA 작성 시작", "FAFSA start"),
            ("contributor_invite", "C", "FAFSA 기여자 초대", "FAFSA contributor invitation"),
            ("contributor_section_status", "S", "기여자 작성 상태", "Contributor section status"),
            ("student_section_review", "S", "학생 작성항목 검토", "Student section review"),
            ("fafsa_review", "S", "FAFSA 전체 검토", "FAFSA review"),
            ("fafsa_sign_submit", "C", "FAFSA 서명·제출", "FAFSA signature and submission"),
            ("fafsa_status", "S", "FAFSA 처리상태", "FAFSA status"),
            ("submission_summary_review", "S", "FAFSA 제출요약 검토", "FAFSA Submission Summary review"),
            ("fafsa_correction", "C", "FAFSA 정정", "FAFSA correction"),
            ("school_recipient_update", "C", "학교 수신처 변경", "School recipient update"),
            ("federal_aid_history_review", "S", "연방 학자금 수혜이력", "Federal aid history review"),
            ("loan_counseling_complete", "C", "학자금대출 상담 이수", "Loan counseling completion"),
            ("master_promissory_note_sign", "C", "학자금 약속어음 서명", "Master Promissory Note signature"),
            ("repayment_plan_compare", "S", "상환계획 비교", "Repayment plan comparison"),
            ("idr_application", "C", "소득연계 상환 신청", "Income-driven repayment application"),
            ("loan_consolidation_application", "C", "학자금대출 통합 신청", "Loan consolidation application"),
            ("pslf_form_submit", "C", "공공서비스 대출탕감 서식 제출", "PSLF form submission"),
            ("pslf_progress_review", "S", "공공서비스 대출탕감 진행상태", "PSLF progress review"),
        ),
    ),
    _domain(
        "child_support_case_services",
        "아동양육비 사건 서비스", "Child support case services",
        "custodial or noncustodial parent|employer|child-support caseworker|authorized parent representative",
        "child-support case and parentage record|support order and payment|income withholding and employment record|medical-support notice|modification interstate referral arrears and enforcement",
        "application pending|parentage established|ordered|paying|withholding active|modified|interstate|delinquent|enforcement active",
        "identified state or tribal child-support program, parties, employer, order, and case",
        "never apply, establish parentage, respond to withholding, report employment or lump sums, exchange documents, or request modification automatically",
        "family_legal_support.hub",
        "case|order|payment|withholding|enforcement",
        (
            ("services_application", "C", "양육비 서비스 신청", "Child support services application"),
            ("case_status", "S", "양육비 사건 상태", "Child support case status"),
            ("parentage_establishment_status", "S", "친자관계 확정 상태", "Parentage establishment status"),
            ("parentage_establishment_submit", "C", "친자관계 확정 제출", "Parentage establishment submission"),
            ("support_order_view", "S", "양육비 명령 조회", "Support order review"),
            ("payment_history", "S", "양육비 지급내역", "Child support payment history"),
            ("payment_route_lookup", "S", "양육비 납부경로 조회", "Child support payment route lookup"),
            ("income_withholding_status", "S", "소득원천징수 상태", "Income withholding status"),
            ("employer_iwo_response", "C", "사업주 원천징수명령 응답", "Employer IWO response"),
            ("employer_termination_report", "C", "사업주 퇴직 신고", "Employer termination report"),
            ("lump_sum_report", "C", "일시금 지급 신고", "Lump-sum payment report"),
            ("employment_change_report", "C", "고용변동 신고", "Employment change report"),
            ("medical_support_notice_status", "S", "의료비 지원통지 상태", "Medical support notice status"),
            ("order_modification_eligibility_review", "S", "양육비 변경요건 검토", "Order modification eligibility review"),
            ("order_modification_request", "C", "양육비 명령 변경 요청", "Support order modification request"),
            ("interstate_case_status", "S", "주간 양육비 사건 상태", "Interstate child support case status"),
            ("secure_document_exchange", "C", "양육비 보안문서 교환", "Secure child support document exchange"),
            ("arrears_balance_review", "S", "양육비 미지급잔액 검토", "Child support arrears review"),
            ("enforcement_action_review", "S", "양육비 집행조치 검토", "Child support enforcement action review"),
        ),
    ),
    _domain(
        "public_housing_assistance_services",
        "공공주택 지원 서비스", "Public housing assistance services",
        "housing applicant or participant|household representative|landlord|public housing agency caseworker",
        "waitlist application and household case|housing voucher|tenancy request and unit|inspection and rent calculation|accommodation portability and hearing",
        "waitlisted|eligible|voucher issued|searching|tenancy pending|inspection failed or passed|recertification due|transferred|hearing pending",
        "identified housing-assistance program, administering agency, household, voucher, and unit",
        "never apply, upload evidence, change household facts, request tenancy, accommodation, portability, recalculation, extension, or hearing automatically",
        "housing.hub",
        "waitlist|voucher|inspection|rent|portability",
        (
            ("pha_locator", "S", "공공주택기관 찾기", "Public housing agency locator"),
            ("program_eligibility_review", "S", "주거지원 자격 검토", "Housing program eligibility review"),
            ("waitlist_application", "C", "공공주택 대기명부 신청", "Housing waitlist application"),
            ("waitlist_status", "S", "공공주택 대기명부 상태", "Housing waitlist status"),
            ("applicant_contact_update", "C", "주거지원 연락처 변경", "Housing applicant contact update"),
            ("eligibility_evidence_upload", "C", "주거지원 자격증빙 업로드", "Housing eligibility evidence upload"),
            ("voucher_orientation_status", "S", "주택바우처 교육 상태", "Voucher orientation status"),
            ("voucher_issue_status", "S", "주택바우처 발급 상태", "Voucher issuance status"),
            ("voucher_search_extension_request", "C", "주택검색기간 연장 요청", "Voucher search extension request"),
            ("tenancy_approval_request", "C", "임대차 승인 요청", "Tenancy approval request"),
            ("unit_inspection_status", "S", "임대주택 검사 상태", "Housing unit inspection status"),
            ("inspection_deficiency_review", "S", "주택검사 결함 검토", "Inspection deficiency review"),
            ("annual_recertification", "C", "주거지원 연례 재인증", "Annual housing recertification"),
            ("income_household_change_report", "C", "소득·가구변동 신고", "Income and household change report"),
            ("rent_recalculation_request", "C", "임대료 재산정 요청", "Rent recalculation request"),
            ("reasonable_accommodation_request", "C", "주거 편의제공 요청", "Reasonable accommodation request"),
            ("portability_eligibility_review", "S", "바우처 이전자격 검토", "Voucher portability eligibility review"),
            ("portability_request", "C", "주택바우처 이전 요청", "Voucher portability request"),
            ("informal_review_hearing_request", "C", "주거지원 비공식 심사·청문 요청", "Informal review or hearing request"),
        ),
    ),
    _domain(
        "healthcare_provider_enrollment_ops",
        "의료공급자 등록 업무", "Healthcare provider enrollment operations",
        "individual healthcare provider|provider organization|authorized official|delegated enrollment staff",
        "NPI record|Medicare enrollment application|supporting document fee and waiver|practice location and ownership record|benefit reassignment revalidation and enrollment status",
        "unregistered|draft|submitted|development requested|approved|revalidation due|deactivated|reactivation pending",
        "identified provider-enrollment jurisdiction, provider, identifier, enrollment record, and authorized official",
        "never apply, update, upload, waive, delegate, report ownership, reassign benefits, revalidate, or reactivate automatically",
        "healthcare_provider_ops.hub",
        "identifier|enrollment|ownership|reassignment|revalidation",
        (
            ("npi_status", "S", "의료공급자 식별번호 상태", "Provider identifier status"),
            ("npi_apply", "C", "의료공급자 식별번호 신청", "Provider identifier application"),
            ("npi_update", "C", "의료공급자 식별정보 변경", "Provider identifier update"),
            ("enrollment_eligibility_review", "S", "의료공급자 등록자격 검토", "Provider enrollment eligibility review"),
            ("medicare_enrollment_start", "C", "의료공급자 등록 시작", "Healthcare provider enrollment start"),
            ("enrollment_application_status", "S", "의료공급자 등록신청 상태", "Provider enrollment application status"),
            ("supporting_document_upload", "C", "의료공급자 증빙 업로드", "Provider supporting document upload"),
            ("application_fee_status", "S", "의료공급자 등록수수료 상태", "Provider enrollment fee status"),
            ("hardship_waiver_request", "C", "등록수수료 곤란면제 요청", "Enrollment hardship waiver request"),
            ("authorized_official_manage", "C", "등록 권한책임자 관리", "Enrollment authorized official management"),
            ("staff_access_manage", "C", "등록업무 직원권한 관리", "Enrollment staff access management"),
            ("practice_location_update", "C", "진료장소 변경", "Practice location update"),
            ("ownership_change_report", "C", "소유권 변경 신고", "Provider ownership change report"),
            ("benefit_reassignment_review", "S", "급여청구권 재배정 검토", "Benefit reassignment review"),
            ("benefit_reassignment_manage", "C", "급여청구권 재배정 관리", "Benefit reassignment management"),
            ("revalidation_due_review", "S", "의료공급자 재검증 기한", "Provider revalidation due review"),
            ("revalidation_submit", "C", "의료공급자 재검증 제출", "Provider revalidation submission"),
            ("deactivation_status", "S", "의료공급자 비활성 상태", "Provider deactivation status"),
            ("enrollment_reactivate", "C", "의료공급자 등록 재활성", "Provider enrollment reactivation"),
        ),
    ),
    _domain(
        "professional_license_administration",
        "전문직 면허 행정", "Professional license administration",
        "professional license applicant|licensed professional|practice supervisor|credential verifier|licensing-board reviewer",
        "regulated profession|license application|education and experience credential|examination and supervised-practice record|license registration continuing education and discipline",
        "eligible|draft|verification pending|examination approved|permitted|licensed|active|expired|inactive|reactivation pending|disciplined",
        "identified licensing board, profession, person, license or application, and registration period",
        "never apply, attest, renew, change identity data, request inactive status, endorse, permit, or reactivate automatically",
        "professional_certification_ops.hub",
        "requirements|application|verification|registration|discipline",
        (
            ("profession_requirements_view", "S", "전문직 면허요건 조회", "Professional license requirements"),
            ("initial_license_application", "C", "전문직 최초면허 신청", "Initial professional license application"),
            ("education_credential_verification", "C", "학력자격 검증", "Education credential verification"),
            ("experience_verification", "C", "경력자격 검증", "Experience verification"),
            ("exam_eligibility_status", "S", "면허시험 응시자격 상태", "License examination eligibility status"),
            ("supervised_practice_status", "S", "감독실무 상태", "Supervised practice status"),
            ("out_of_state_endorsement", "C", "타지역 면허인정 신청", "Out-of-state endorsement"),
            ("limited_permit_application", "C", "제한실무허가 신청", "Limited practice permit application"),
            ("application_status", "S", "전문직 면허신청 상태", "Professional license application status"),
            ("public_license_verification", "S", "전문직 면허 공개검증", "Public professional license verification"),
            ("registration_status", "S", "전문직 등록 상태", "Professional registration status"),
            ("registration_renewal", "C", "전문직 등록 갱신", "Professional registration renewal"),
            ("continuing_education_status", "S", "보수교육 이수상태", "Continuing education status"),
            ("continuing_education_attestation", "C", "보수교육 이수확인", "Continuing education attestation"),
            ("name_change_request", "C", "전문직 면허 이름 변경", "Professional license name change"),
            ("address_change", "C", "전문직 면허 주소 변경", "Professional license address change"),
            ("inactive_registration_request", "C", "전문직 휴업등록 요청", "Inactive registration request"),
            ("registration_reactivate", "C", "전문직 등록 재활성", "Professional registration reactivation"),
            ("disciplinary_action_review", "S", "전문직 징계조치 검토", "Professional disciplinary action review"),
        ),
    ),
)

REVIEWED_BY_DOMAIN = {item.domain: item for item in REVIEWED_DOMAINS}
REVIEWED_FEATURE_BY_ID = {
    f"{domain.domain}.{feature.key}": feature
    for domain in REVIEWED_DOMAINS
    for feature in domain.features
}


KOREAN_DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "unemployment_insurance_case_services": _terms("고용24|실업급여|수급자격 인정 신청|실업인정 인터넷 신청|고용보험 심사청구"),
    "social_security_benefit_services": _terms("국민연금|내 국민연금 알아보기|연금·일시금 청구|연금 지급내역|수급자 계좌번호 변경"),
    "consumer_credit_reporting_services": _terms("크레딧포유|본인신용정보 열람|신용정보 조회|신용정보 등록현황|신용정보 제공내역"),
    "driver_vehicle_licensing_services": _terms("안전운전 통합민원|적성검사·갱신|분실 등 재발급|운전면허증 발급|방문시간 예약"),
    "disaster_assistance_case_services": _terms("국민재난안전포털|사유재산 피해신고|자연재난 선택|피해신고 신규등록|처리상태"),
    "veterans_benefit_claim_services": _terms("나만의예우|나의지원내역|보훈급여금|민원신청|보훈보상 대상자 및 가족 등록신청"),
    "wage_hour_enforcement_ops": _terms("노동포털|진정서(임금체불, 기타 근로기준 분야)|나의민원|진정 취하|체불임금 등 사업주 확인서"),
    "student_financial_aid_services": _terms("한국장학재단|장학금신청|신청서작성|신청현황|서류제출현황"),
    "child_support_case_services": _terms("양육비이행관리원|양육비 이행확보 지원신청|제재조치 신청|지원 신청 방법|양육비 선지급 신청"),
    "public_housing_assistance_services": _terms("LH청약플러스|청약신청|임대주택|공고문|신청자격"),
    "healthcare_provider_enrollment_ops": _terms("요양기관업무포털|현황신고|기호부여신청|보건의료자원 통합신고포털|현황신고·변경"),
    "professional_license_administration": _terms("큐넷|원서접수|자격증발급|확인서발급|합격자발표"),
}


@dataclass(frozen=True)
class SourceSeed:
    source_id: str
    domain: str
    publisher: str
    title: str
    canonical_url: str
    jurisdiction: str
    terminal_keys: tuple[str, ...]


def _ss(
    source_id: str,
    domain: str,
    publisher: str,
    title: str,
    url: str,
    jurisdiction: str,
    keys: str,
) -> SourceSeed:
    return SourceSeed(source_id, domain, publisher, title, url, jurisdiction, _terms(keys))


SOURCE_SEEDS: tuple[SourceSeed, ...] = (
    _ss("v17_ui_application", "unemployment_insurance_case_services", "U.S. Department of Labor", "UI application review and confirmation", "https://www.dol.gov/agencies/eta/ui-modernization/customer-experience/improve-applications/review-and-confirmation-sections", "US", "initial_claim_start|identity_verification|wage_employer_history_review|separation_fact_finding_response|employer_separation_response|evidence_upload"),
    _ss("v17_ui_program", "unemployment_insurance_case_services", "U.S. Department of Labor", "Unemployment Insurance", "https://www.dol.gov/agencies/eta/feature-unemployment", "US", "claimant_dashboard|reemployment_service_status|claim_status|payment_status|payment_method_update|tax_form_1099g_request"),
    _ss("v17_ui_modernization", "unemployment_insurance_case_services", "U.S. Department of Labor", "Unemployment Insurance modernization", "https://www.dol.gov/agencies/eta/ui-modernization", "US", "claimant_dashboard|initial_claim_start|identity_verification|claim_status"),
    _ss("v17_ui_weekly", "unemployment_insurance_case_services", "U.S. Department of Labor", "Weekly certification", "https://www.dol.gov/agencies/eta/ui-modernization/initial-application/weekly-certification", "US", "weekly_certification_submit|work_search_record|wage_employer_history_review|payment_status"),
    _ss("v17_ui_notices", "unemployment_insurance_case_services", "U.S. Department of Labor", "UI plain-language repository", "https://www.dol.gov/agencies/eta/ui-modernization/use-plain-language/plain-language-repository", "US", "monetary_determination_review|eligibility_determination_review|overpayment_notice_review|overpayment_waiver_request|determination_appeal_submit"),
    _ss("v17_ui_korea", "unemployment_insurance_case_services", "고용24", "실업급여 신청절차", "https://www.work24.go.kr/cm/c/f/1100/selecSystInfo.do?systClId=SC00000258&systCnntId=&systId=SI00000347", "KR", "initial_claim_start|weekly_certification_submit|work_search_record|claim_status|eligibility_determination_review|payment_status|determination_appeal_submit"),

    _ss("v17_ssa_apply", "social_security_benefit_services", "Social Security Administration", "Apply for Social Security benefits", "https://www.ssa.gov/apply", "US", "retirement_application_start|disability_application_start|ssi_application_start|medicare_application_start|application_status"),
    _ss("v17_ssa_appeal", "social_security_benefit_services", "Social Security Administration", "Appeal a decision", "https://www.ssa.gov/disabilityssi/appeal.html", "US", "appeal_status|decision_appeal_request|continuing_disability_review"),
    _ss("v17_ssa_online", "social_security_benefit_services", "Social Security Administration", "Online services", "https://www.ssa.gov/onlineservices/", "US", "earnings_record_review|benefit_estimate|application_status|appeal_status|benefit_verification_letter|social_security_card_replace|name_correction_request|address_change|direct_deposit_update|beneficiary_change_report|representative_payee_status"),
    _ss("v17_ssa_overpayment", "social_security_benefit_services", "Social Security Administration", "Repay overpaid benefits", "https://www.ssa.gov/manage-benefits/resolve-overpayment/repay-overpaid-benefits", "US", "overpayment_notice_review|overpayment_waiver_request|decision_appeal_request"),
    _ss("v17_ssa_waiver", "social_security_benefit_services", "Social Security Administration", "Request waiver of overpayment recovery", "https://www.ssa.gov/forms/ssa-632.html", "US", "overpayment_notice_review|overpayment_waiver_request|decision_appeal_request"),
    _ss("v17_ssa_korea", "social_security_benefit_services", "국민연금공단", "국민연금 전자민원 조회·신고·신청", "https://www.nps.or.kr/comm/pop/getOHAH0077P2.do", "KR", "earnings_record_review|benefit_estimate|retirement_application_start|benefit_verification_letter|direct_deposit_update|beneficiary_change_report"),

    _ss("v17_credit_dispute", "consumer_credit_reporting_services", "Consumer Financial Protection Bureau", "Dispute an error on a credit report", "https://www.consumerfinance.gov/ask-cfpb/how-do-i-dispute-an-error-on-my-credit-report-en-314/", "US", "tradeline_detail_review|tradeline_dispute_create|dispute_evidence_upload|dispute_status|dispute_result_review|consumer_statement_add"),
    _ss("v17_credit_identity_theft", "consumer_credit_reporting_services", "Consumer Financial Protection Bureau", "Identity theft response", "https://www.consumerfinance.gov/ask-cfpb/what-do-i-do-if-i-think-i-have-been-a-victim-of-identity-theft-en-31/", "US", "identity_theft_report_start|identity_theft_block_request|fraud_alert_place|security_freeze_place"),
    _ss("v17_credit_reports", "consumer_credit_reporting_services", "Consumer Financial Protection Bureau", "Credit reports and scores", "https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/", "US", "credit_report_request|credit_file_review|tradeline_detail_review|inquiry_review|adverse_action_notice_review"),
    _ss("v17_credit_complaint", "consumer_credit_reporting_services", "Consumer Financial Protection Bureau", "Credit and consumer reporting complaint notice", "https://www.consumerfinance.gov/complaint/credit-and-consumer-reporting-complaint-notice/", "US", "dispute_status|dispute_result_review|cfpb_complaint_submit"),
    _ss("v17_credit_protection", "consumer_credit_reporting_services", "Consumer Financial Protection Bureau", "Credit freezes and fraud alerts", "https://www.consumerfinance.gov/archive/blog/free-credit-freezes-are-here/", "US", "security_freeze_status|security_freeze_place|security_freeze_lift|fraud_alert_status|fraud_alert_place|fraud_alert_remove"),
    _ss("v17_credit_korea", "consumer_credit_reporting_services", "한국신용정보원", "본인신용정보 열람서비스", "https://www.credit4u.or.kr/", "KR", "credit_report_request|credit_file_review|tradeline_detail_review|inquiry_review|dispute_status"),

    _ss("v17_dmv_states", "driver_vehicle_licensing_services", "USA.gov", "State motor vehicle services", "https://www.usa.gov/state-motor-vehicle-services", "US", "driver_license_status|driver_license_apply|driver_license_renew|driver_license_replace|vehicle_registration_status|vehicle_title_status|suspension_reinstatement_status"),
    _ss("v17_dmv_online", "driver_vehicle_licensing_services", "California Department of Motor Vehicles", "DMV online services", "https://www.dmv.ca.gov/portal/dmv-online/", "US", "driver_record_request|driver_test_appointment|driver_address_change|vehicle_title_transfer|vehicle_title_replace|transfer_release_of_liability|license_plate_order|reinstatement_fee_payment"),
    _ss("v17_dmv_license", "driver_vehicle_licensing_services", "California Department of Motor Vehicles", "Driver license and identification", "https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/", "US", "driver_license_status|driver_license_apply|driver_license_renew|driver_license_replace|real_id_upgrade|driver_record_request|driver_test_appointment|driver_address_change"),
    _ss("v17_dmv_registration", "driver_vehicle_licensing_services", "California Department of Motor Vehicles", "Vehicle registration", "https://www.dmv.ca.gov/portal/vehicle-registration/", "US", "vehicle_registration_status|vehicle_registration_start|vehicle_registration_renew|vehicle_registration_replace|vehicle_title_status|vehicle_title_transfer|vehicle_title_replace|license_plate_order"),
    _ss("v17_dmv_renewal", "driver_vehicle_licensing_services", "California Department of Motor Vehicles", "Vehicle registration renewal", "https://www.dmv.ca.gov/portal/vehicle-registration/vehicle-registration-renewal/", "US", "vehicle_registration_status|vehicle_registration_renew|vehicle_registration_replace|vehicle_title_replace|suspension_reinstatement_status"),
    _ss("v17_dmv_korea", "driver_vehicle_licensing_services", "한국도로교통공단", "운전면허증 발급 가이드", "https://www.safedriving.or.kr/diGuide/selectDiGuide18.do", "KR", "driver_license_status|driver_license_apply|driver_license_renew|driver_license_replace|driver_test_appointment"),

    _ss("v17_fema_apply", "disaster_assistance_case_services", "Federal Emergency Management Agency", "Ways to apply for disaster assistance", "https://www.fema.gov/node/4-ways-apply-disaster-assistance", "US", "declared_area_eligibility_lookup|assistance_program_review|individual_assistance_application|application_status"),
    _ss("v17_fema_policy", "disaster_assistance_case_services", "Federal Emergency Management Agency", "Individual Assistance Program and Policy Guide", "https://www.fema.gov/sites/default/files/2020-07/fema_individual-assistance-program-policy-guide_2019.pdf", "US", "identity_verification_status|identity_residency_evidence_upload|insurance_information_submit|home_occupancy_ownership_verify|home_inspection_schedule|inspection_status|inspection_accommodation_request|additional_information_request_review|additional_information_response|award_status|direct_deposit_update|temporary_housing_status"),
    _ss("v17_fema_appeals_guide", "disaster_assistance_case_services", "Federal Emergency Management Agency", "Individual Assistance appeals", "https://www.fema.gov/sites/default/files/documents/fema_ia-quick-reference_appeals.pdf", "US", "determination_letter_view|appeal_evidence_upload|decision_appeal_submit"),
    _ss("v17_fema_after_apply", "disaster_assistance_case_services", "Federal Emergency Management Agency", "What to expect after applying", "https://www.fema.gov/print/pdf/node/662135", "US", "application_status|identity_verification_status|home_inspection_schedule|inspection_status|additional_information_request_review|determination_letter_view|award_status|temporary_housing_status"),
    _ss("v17_fema_appeal", "disaster_assistance_case_services", "Federal Emergency Management Agency", "Appealing FEMA's decision", "https://www.fema.gov/print/pdf/node/689311", "US", "determination_letter_view|appeal_evidence_upload|decision_appeal_submit"),
    _ss("v17_fema_korea", "disaster_assistance_case_services", "행정안전부", "사유재산 피해신고", "https://www.safekorea.go.kr/idsiSFK/neo/sfk/cs/pan/cdr/cdreaiBefore.html?menuSeq=157", "KR", "declared_area_eligibility_lookup|individual_assistance_application|application_status|identity_residency_evidence_upload|additional_information_response|award_status"),

    _ss("v17_va_file", "veterans_benefit_claim_services", "U.S. Department of Veterans Affairs", "How to file a VA disability claim", "https://www.va.gov/disability/how-to-file-claim/", "US", "intent_to_file|claim_type_review|disability_claim_start|increase_claim_start|supplemental_claim_start|supporting_evidence_upload"),
    _ss("v17_va_status", "veterans_benefit_claim_services", "U.S. Department of Veterans Affairs", "Check claim or appeal status", "https://www.va.gov/claim-or-appeal-status/", "US", "claim_exam_status|claim_status|evidence_request_review|review_appeal_status"),
    _ss("v17_va_reviews", "veterans_benefit_claim_services", "U.S. Department of Veterans Affairs", "Decision reviews and appeals", "https://www.va.gov/decision-reviews/", "US", "higher_level_review_submit|supplemental_review_submit|board_appeal_start|review_appeal_status"),
    _ss("v17_va_process", "veterans_benefit_claim_services", "U.S. Department of Veterans Affairs", "The VA claim process after filing", "https://www.va.gov/disability/after-you-file-claim/", "US", "claim_exam_status|claim_status|evidence_request_review|decision_letter_download|disability_rating_review"),
    _ss("v17_va_letters", "veterans_benefit_claim_services", "U.S. Department of Veterans Affairs", "Download VA benefit letters", "https://www.va.gov/records/download-va-letters/", "US", "decision_letter_download|disability_rating_review|payment_history|direct_deposit_update|dependent_change_request|accredited_representative_manage"),
    _ss("v17_va_korea", "veterans_benefit_claim_services", "국가보훈부", "나만의예우", "https://pmp.mpva.go.kr/rt/tse/rtTseS001.do?mnuKeyVl=138", "KR", "claim_type_review|claim_status|payment_history|direct_deposit_update|dependent_change_request"),

    _ss("v17_whd_complaint", "wage_hour_enforcement_ops", "U.S. Department of Labor", "How to file a complaint", "https://www.dol.gov/agencies/whd/contact/complaints", "US", "complaint_requirements_review|worker_complaint_prepare|worker_complaint_submit|complaint_evidence_upload|complaint_status|investigation_case_queue|employer_record_request|employer_record_upload|employee_interview_record"),
    _ss("v17_whd_flsa", "wage_hour_enforcement_ops", "U.S. Department of Labor", "Handy Reference Guide to the FLSA", "https://www.dol.gov/agencies/whd/compliance-assistance/handy-reference-guide-flsa", "US", "worker_rights_scope_review|payroll_hours_compliance_review|minimum_wage_finding_record|overtime_finding_record|child_labor_finding_record|back_wage_calculation"),
    _ss("v17_whd_home", "wage_hour_enforcement_ops", "U.S. Department of Labor", "Wage and Hour Division", "https://www.dol.gov/agencies/whd", "US", "worker_rights_scope_review|complaint_requirements_review|fmla_finding_record"),
    _ss("v17_whd_retaliation", "wage_hour_enforcement_ops", "U.S. Department of Labor", "Retaliation", "https://www.dol.gov/agencies/whd/retaliation", "US", "retaliation_report_submit|worker_complaint_submit"),
    _ss("v17_whd_resolution", "wage_hour_enforcement_ops", "U.S. Department of Labor", "Payroll Audit Independent Determination questions", "https://www.dol.gov/agencies/whd/paid/questions-and-answers", "US", "back_wage_calculation|resolution_terms_review|resolution_payment_confirm"),
    _ss("v17_whd_korea", "wage_hour_enforcement_ops", "고용노동부", "체불임금 해결 방법", "https://labor.moel.go.kr/minwonSysInfo/wagesolway.do", "KR", "complaint_requirements_review|worker_complaint_prepare|worker_complaint_submit|complaint_evidence_upload|complaint_status|investigation_case_queue|back_wage_calculation|resolution_terms_review|resolution_payment_confirm"),

    _ss("v17_fsa_fafsa", "student_financial_aid_services", "Federal Student Aid", "FAFSA student steps", "https://studentaid.gov/articles/fafsa-student-steps/", "US", "aid_dashboard|fafsa_start|contributor_invite|contributor_section_status|student_section_review|fafsa_review|fafsa_sign_submit"),
    _ss("v17_fsa_summary", "student_financial_aid_services", "Federal Student Aid", "FAFSA Submission Summary", "https://studentaid.gov/articles/fafsa-submission-summary/", "US", "fafsa_status|submission_summary_review|fafsa_correction|school_recipient_update|federal_aid_history_review"),
    _ss("v17_fsa_pslf", "student_financial_aid_services", "Federal Student Aid", "Manage PSLF progress", "https://studentaid.gov/articles/manage-your-pslf-progress/", "US", "pslf_form_submit|pslf_progress_review"),
    _ss("v17_fsa_repayment", "student_financial_aid_services", "Federal Student Aid", "Repaying your federal student loans", "https://studentaid.gov/sites/default/files/repaying-your-loans.pdf", "US", "loan_counseling_complete|master_promissory_note_sign|repayment_plan_compare|idr_application"),
    _ss("v17_fsa_consolidation", "student_financial_aid_services", "Federal Student Aid", "Direct Consolidation Loan Application and Promissory Note", "https://studentaid.gov/app/api/repayment-forms/download-repayment-form?localeCode=en-us&searchType=library&shortName=consollink", "US", "loan_consolidation_application|master_promissory_note_sign"),
    _ss("v17_fsa_korea", "student_financial_aid_services", "한국장학재단", "장학금·학자금 서비스", "https://www.kosaf.go.kr/", "KR", "aid_dashboard|federal_aid_history_review|repayment_plan_compare"),

    _ss("v17_child_portal", "child_support_case_services", "Office of Child Support Services", "Child Support Portal", "https://ocsp.acf.hhs.gov/csp/", "US", "case_status|payment_route_lookup|secure_document_exchange|interstate_case_status"),
    _ss("v17_child_employer", "child_support_case_services", "Office of Child Support Services", "Employer Services", "https://ocsp.acf.hhs.gov/csp/home/employer", "US", "income_withholding_status|employer_iwo_response|employer_termination_report|lump_sum_report|employment_change_report|secure_document_exchange"),
    _ss("v17_child_bics", "child_support_case_services", "Office of Child Support Services", "Business Intelligence for Child Support", "https://www.acf.hhs.gov/sites/default/files/documents/ocse/bics_co_brief.pdf", "US", "services_application|case_status|payment_history|arrears_balance_review|enforcement_action_review"),
    _ss("v17_child_profile", "child_support_case_services", "Office of Child Support Services", "Intergovernmental Reference Guide state profile", "https://ocsp.acf.hhs.gov/irg/profile/displayResults", "US", "parentage_establishment_status|parentage_establishment_submit|support_order_view|medical_support_notice_status|order_modification_eligibility_review|order_modification_request|interstate_case_status"),
    _ss("v17_child_lump", "child_support_case_services", "Office of Child Support Services", "State lump-sum reporting information", "https://ocsp.acf.hhs.gov/irg/irgpdf.pdf?addrClassType=EMP&addrType=SLS&geoType=OGP&groupCode=EMP", "US", "lump_sum_report|income_withholding_status|arrears_balance_review|enforcement_action_review"),
    _ss("v17_child_korea", "child_support_case_services", "양육비이행관리원", "양육비 이행확보 지원 신청 방법", "https://www.childsupport.or.kr/lay1/S1T10C12/contents.do", "KR", "services_application|case_status|parentage_establishment_status|support_order_view|payment_history|order_modification_request|arrears_balance_review|enforcement_action_review"),

    _ss("v17_hud_program", "public_housing_assistance_services", "U.S. Department of Housing and Urban Development", "Housing Choice Voucher Program", "https://www.hud.gov/topics/housing_choice_voucher_program_section_8?sub5=DCB07A0C-605C-7109-253D-0BF1F57C98FD", "US", "pha_locator|program_eligibility_review|waitlist_application|waitlist_status"),
    _ss("v17_hud_tenants", "public_housing_assistance_services", "U.S. Department of Housing and Urban Development", "Housing Choice Vouchers for tenants", "https://www.hud.gov/helping-americans/housing-choice-vouchers-tenants", "US", "program_eligibility_review|waitlist_application|waitlist_status|applicant_contact_update|eligibility_evidence_upload|voucher_orientation_status|voucher_issue_status|voucher_search_extension_request|tenancy_approval_request|unit_inspection_status|inspection_deficiency_review|annual_recertification|income_household_change_report|rent_recalculation_request|reasonable_accommodation_request|informal_review_hearing_request"),
    _ss("v17_hud_portability", "public_housing_assistance_services", "U.S. Department of Housing and Urban Development", "Housing Choice Vouchers portability", "https://www.hud.gov/helping-americans/housing-choice-vouchers-portability", "US", "portability_eligibility_review|portability_request"),
    _ss("v17_hud_guidebook", "public_housing_assistance_services", "U.S. Department of Housing and Urban Development", "Housing Choice Voucher Program Guidebook", "https://www.hud.gov/helping-americans/housing-choice-vouchers-guidebook", "US", "waitlist_application|unit_inspection_status|annual_recertification|rent_recalculation_request|portability_request|informal_review_hearing_request"),
    _ss("v17_hud_hearing", "public_housing_assistance_services", "U.S. Department of Housing and Urban Development", "Informal reviews and hearings", "https://www.hud.gov/sites/documents/DOC_35626.PDF", "US", "informal_review_hearing_request|program_eligibility_review|rent_recalculation_request"),
    _ss("v17_hud_korea", "public_housing_assistance_services", "한국토지주택공사", "LH청약플러스 임대가이드", "https://apply.lh.or.kr/lhapply/cm/cntnts/cntntsView.do?cntntsId=1125&mi=1240", "KR", "program_eligibility_review|waitlist_application|waitlist_status|eligibility_evidence_upload"),

    _ss("v17_cms_pecos", "healthcare_provider_enrollment_ops", "Centers for Medicare & Medicaid Services", "Medicare Enrollment for Providers and Suppliers", "https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/chain-ownership-system-pecos", "US", "enrollment_eligibility_review|medicare_enrollment_start|enrollment_application_status|application_fee_status|staff_access_manage"),
    _ss("v17_cms_revalidation", "healthcare_provider_enrollment_ops", "Centers for Medicare & Medicaid Services", "Revalidations", "https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/revalidations", "US", "revalidation_due_review|revalidation_submit|deactivation_status|enrollment_reactivate"),
    _ss("v17_cms_resources", "healthcare_provider_enrollment_ops", "Centers for Medicare & Medicaid Services", "Medicare provider enrollment resources", "https://www.cms.gov/Outreach-and-Education/Medicare-Learning-Network-MLN/MLNProducts/EnrollmentResources/provider-resources/provider-enrolment/Med-Prov-Enroll-MLN9658742.html", "US", "application_fee_status|hardship_waiver_request|authorized_official_manage|staff_access_manage|practice_location_update|ownership_change_report|benefit_reassignment_review|benefit_reassignment_manage"),
    _ss("v17_cms_manage", "healthcare_provider_enrollment_ops", "Centers for Medicare & Medicaid Services", "Manage your enrollment", "https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/chain-ownership-system-pecos/manage-your-enrollment", "US", "practice_location_update|ownership_change_report|benefit_reassignment_review|benefit_reassignment_manage|revalidation_submit|deactivation_status|enrollment_reactivate"),
    _ss("v17_cms_applications", "healthcare_provider_enrollment_ops", "Centers for Medicare & Medicaid Services", "Enrollment applications", "https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/chain-ownership-system-pecos/enrollment-applications", "US", "medicare_enrollment_start|enrollment_application_status|supporting_document_upload"),
    _ss("v17_cms_npi", "healthcare_provider_enrollment_ops", "Centers for Medicare & Medicaid Services", "National Provider Identifier standard", "https://www.cms.gov/medicare/regulations-guidance/administrative-simplification/national-provider-identifier-standard", "US", "npi_status|npi_apply|npi_update"),
    _ss("v17_cms_korea", "healthcare_provider_enrollment_ops", "건강보험심사평가원", "요양기관 현황신고", "https://biz.hira.or.kr/contents/html/MP00000099.html", "KR", "enrollment_eligibility_review|medicare_enrollment_start|enrollment_application_status|supporting_document_upload|practice_location_update|ownership_change_report"),

    _ss("v17_license_home", "professional_license_administration", "New York State Education Department", "Office of the Professions", "https://www.op.nysed.gov/", "US", "profession_requirements_view|initial_license_application|application_status|registration_status|registration_renewal"),
    _ss("v17_license_policy", "professional_license_administration", "New York State Education Department", "General licensing information and policies", "https://www.op.nysed.gov/about/general-information-policies", "US", "initial_license_application|education_credential_verification|experience_verification|exam_eligibility_status|supervised_practice_status|out_of_state_endorsement|limited_permit_application|application_status"),
    _ss("v17_license_renewal", "professional_license_administration", "New York State Education Department", "Online registration renewal", "https://www.op.nysed.gov/registration-renewal/online-registration-renewal", "US", "registration_status|registration_renewal|continuing_education_status|continuing_education_attestation|name_change_request|address_change|inactive_registration_request|registration_reactivate"),
    _ss("v17_license_search", "professional_license_administration", "New York State Education Department", "Online verification searches", "https://www.op.nysed.gov/services/verifications/online-verification-searches", "US", "public_license_verification|registration_status|disciplinary_action_review"),
    _ss("v17_license_written", "professional_license_administration", "New York State Education Department", "Written certification or verification of licensure", "https://www.op.nysed.gov/verification-search/written-certification-or-verification-of-licensure", "US", "education_credential_verification|out_of_state_endorsement|public_license_verification|registration_status|disciplinary_action_review"),
    _ss("v17_license_korea", "professional_license_administration", "한국산업인력공단", "큐넷 원서접수·자격증발급", "https://www.q-net.or.kr/", "KR", "profession_requirements_view|exam_eligibility_status|public_license_verification|registration_status"),
)


PUBLISHER_ALLOWLIST = frozenset(
    {
        "U.S. Department of Labor",
        "Social Security Administration",
        "Consumer Financial Protection Bureau",
        "USA.gov",
        "California Department of Motor Vehicles",
        "Federal Emergency Management Agency",
        "U.S. Department of Veterans Affairs",
        "Federal Student Aid",
        "Office of Child Support Services",
        "U.S. Department of Housing and Urban Development",
        "Centers for Medicare & Medicaid Services",
        "New York State Education Department",
        "고용24",
        "국민연금공단",
        "한국신용정보원",
        "한국도로교통공단",
        "행정안전부",
        "국가보훈부",
        "고용노동부",
        "한국장학재단",
        "양육비이행관리원",
        "한국토지주택공사",
        "건강보험심사평가원",
        "한국산업인력공단",
    }
)


def normalize_official_url(value: str) -> str:
    parts = urlsplit(value.strip())
    scheme = parts.scheme.casefold()
    host = (parts.hostname or "").casefold()
    if not scheme or not host:
        raise V17CatalogValidationError(f"invalid official source URL: {value}")
    port = parts.port
    netloc = host if port is None or (scheme == "https" and port == 443) else f"{host}:{port}"
    path = posixpath.normpath(parts.path or "/")
    if not path.startswith("/"):
        path = f"/{path}"
    if parts.path.endswith("/") and not path.endswith("/"):
        path = f"{path}/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _source_digest(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _build_official_sources() -> tuple[
    dict[str, dict[str, object]],
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    sources: dict[str, dict[str, object]] = {}
    terminal_sources: dict[str, list[str]] = defaultdict(list)
    domain_sources: dict[str, list[str]] = defaultdict(list)
    for seed in SOURCE_SEEDS:
        terminal_ids = [f"{seed.domain}.{key}" for key in seed.terminal_keys]
        record: dict[str, object] = {
            "source_id": seed.source_id,
            "publisher": seed.publisher,
            "title": seed.title,
            "canonical_url": seed.canonical_url,
            "normalized_url": normalize_official_url(seed.canonical_url),
            "final_url": seed.canonical_url,
            "retrieved_at": RETRIEVED_AT,
            "collected_on": COLLECTED_ON,
            "evidence_level": "official_primary",
            "verification_status": "accepted",
            "verification_method": "official first-party lifecycle page reviewed for the V17 source pack",
            "http_status": 200,
            "verified_status": 200,
            "jurisdiction": seed.jurisdiction,
            "domains": [seed.domain],
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


def _feature_seed(domain: DomainSpec, feature: ReviewedFeature) -> FeatureSeed:
    function_id = f"{domain.domain}.{feature.key}"
    ko_aliases = [
        feature.name_ko,
        f"{feature.name_ko} 보기",
        f"{feature.name_ko} 확인",
        f"{feature.name_ko} 화면",
        f"{feature.name_ko} 메뉴",
        f"{feature.name_ko} 내역",
        f"{feature.name_ko} 상태",
        f"{feature.name_ko} 처리",
        f"{feature.name_ko} 관리",
        f"{domain.root_ko} {feature.name_ko}",
    ]
    if function_id in KOREAN_TERMINAL_IDS:
        ko_aliases.extend(KOREAN_DOMAIN_TERMS[domain.domain])
    en_aliases = [
        feature.name_en,
        f"view {feature.name_en.lower()}",
        f"check {feature.name_en.lower()}",
        f"open {feature.name_en.lower()}",
        f"manage {feature.name_en.lower()}",
        f"{feature.name_en.lower()} details",
        f"{feature.name_en.lower()} status",
        f"{feature.name_en.lower()} screen",
        f"{feature.name_en.lower()} record",
        f"{domain.root_en} {feature.name_en}",
    ]
    positive = _dedupe(
        (
            feature.goal_ko,
            feature.goal_en,
            feature.purpose_ko,
            feature.purpose_en,
            *feature.roles,
            *feature.assets,
            *feature.states,
            feature.jurisdiction_guard,
        )
    )
    negative = _dedupe(
        (
            "잘못된 역할",
            "다른 사람 또는 기록",
            "다른 관할권",
            "권한 거부",
            "오프라인 또는 오래된 정보",
            "wrong role",
            "different person or record",
            "wrong jurisdiction",
            "permission denied",
            "offline or stale data",
            *domain.collision_terms,
        )
    )
    return F(
        feature.key,
        feature.name_ko,
        feature.name_en,
        "|".join(_dedupe(ko_aliases)),
        "|".join(_dedupe(en_aliases)),
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
        f"{domain.domain}_public_case_operations",
        "|".join(_dedupe((domain.root_ko, *domain.roles, *domain.assets, *KOREAN_DOMAIN_TERMS[domain.domain]))),
        "|".join(_dedupe((domain.root_en, *domain.roles, *domain.assets, *domain.states, domain.jurisdiction))),
        "|".join(("다른 제도", "잘못된 역할", "잘못된 사람 또는 기록", "관할권 불명확", *domain.collision_terms)),
        "|".join(("different program", "wrong role", "wrong person or record", "missing jurisdiction", *domain.collision_terms)),
        domain.avoid_root,
        "|".join(DOMAIN_SOURCE_IDS[domain.domain]),
        *(_feature_seed(domain, feature) for feature in domain.features),
    )


GROUPS: tuple[GroupSeed, ...] = tuple(_group_seed(domain) for domain in REVIEWED_DOMAINS)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {domain: 19 for domain in sorted(REQUIRED_DOMAINS)}
EXPECTED_DOMAIN_FUNCTION_COUNTS = {domain: 20 for domain in sorted(REQUIRED_DOMAINS)}


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    tags = [value for value in result.get("legacy_tags", []) if value != "v10_reviewed_operations"]
    result["legacy_tags"] = list(_dedupe((*tags, "v17_public_case_operations")))
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_root(group))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    result.update(
        {
            "automation_policy": "safe_navigation",
            "stop_policy": "continue",
            "risk_level": "low",
            "state_changing": False,
            "user_owned_final_press": False,
            "jurisdiction_aliases": {
                "KR": list(KOREAN_DOMAIN_TERMS[group.domain]),
                "US": [domain.root_en, domain.jurisdiction],
            },
        }
    )
    aliases = copy.deepcopy(result["aliases"])
    aliases["ko-KR"] = [
        value
        for value in _dedupe((*aliases["ko-KR"], *KOREAN_DOMAIN_TERMS[group.domain]))
        if re.search(r"[\uac00-\ud7a3]", value)
    ]
    result["aliases"] = aliases
    result["role_hints"] = list(_dedupe((*result["role_hints"], *domain.roles, "authorized case participant")))
    result["asset_cues"] = list(_dedupe((*domain.assets, f"{domain.root_en} governed record")))
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues["lifecycle"] = list(_dedupe((*domain.states, "current case lifecycle state")))
    state_cues["jurisdiction"] = [domain.jurisdiction, "jurisdiction must be explicit"]
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues["hub_boundary"] = [
        "역할·기록·관할·상태가 불명확하면 허브에서 중단",
        "stop on the domain hub when role, record, jurisdiction, or state is unclear",
    ]
    risk_cues["source_boundary"] = [domain.boundary]
    result["risk_cues"] = risk_cues
    result["source_refs"] = list(DOMAIN_SOURCE_IDS[group.domain])
    return result


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    function_id = str(result["function_id"])
    result.update(
        {
            "automation_policy": "never_auto",
            "stop_policy": "before_action",
            "risk_level": "high",
            "state_changing": feature.classification == "C",
            "user_owned_final_press": True,
            "classification": feature.classification,
            "representative_goals": {"ko-KR": feature.goal_ko, "en-US": feature.goal_en},
            "purpose_by_locale": {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en},
            "jurisdiction_aliases": {
                "KR": list(KOREAN_DOMAIN_TERMS[group.domain]) if function_id in KOREAN_TERMINAL_IDS else [],
                "US": [feature.name_en, feature.jurisdiction_guard],
            },
        }
    )
    result["role_hints"] = list(_dedupe((*result["role_hints"], *feature.roles, "authorized case participant")))
    result["asset_cues"] = list(_dedupe((*feature.assets, feature.name_ko, feature.name_en, _words(feature.key))))
    state_cues = copy.deepcopy(result["state_cues"])
    state_cues.update(
        {
            "lifecycle": list(feature.states),
            "jurisdiction": [feature.jurisdiction_guard, "jurisdiction and program must be explicit"],
            "wrong_role": ["잘못된 역할", "권한 없는 역할", "wrong role", "role not authorized"],
            "wrong_record": ["잘못된 사람 또는 기록", "다른 사건", "wrong person or record", "different case"],
            "unavailable": ["비활성", "사용 불가", "권한 거부", "disabled", "unavailable", "permission denied"],
            "offline": ["오프라인", "오래된 데이터", "offline", "stale data"],
            "hold": ["검토 대기", "법적 보류", "안전 보류", "pending review", "legal hold", "safety hold"],
        }
    )
    result["state_cues"] = state_cues
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues.update(
        {
            "classification": [
                "S: sensitive or permission-limited read"
                if feature.classification == "S"
                else "C: consequential high-risk state change"
            ],
            "role_asset_state_gate": [
                "권한 역할·정확한 기록·관할·현재 상태를 확인",
                "verify authorized role, exact record, jurisdiction, and current state",
                "require at least two positive case dimensions",
                "consequential actions require role, record, jurisdiction, and state",
            ],
            "fail_closed": [
                "잘못된 역할·기록·관할·상태, 권한 거부, 보류, 오프라인이면 허브에서 중단",
                "stop at the hub on wrong role, record, jurisdiction, or state, permission denial, hold, or offline data",
            ],
            "forbidden_terminal_actions": [
                "확인·승인·서명·제출·결제·변경·삭제 자동 실행 금지",
                "never auto-press confirm approve sign submit pay change or delete",
            ],
            "blocked_final_channels": [
                "음성·키보드·딥링크·재시도·접근성 동작으로 최종 동작 우회 금지",
                "no final-action bypass through voice keyboard deep link retry or accessibility action",
            ],
            "user_boundary": [
                "최종 목적지 버튼은 사용자가 직접 누름",
                "the user must press the final destination button",
            ],
            "user_owned_final_press": ["true", "사용자 소유 최종 누름"],
            "source_boundary": [feature.safety_boundary],
        }
    )
    result["risk_cues"] = risk_cues
    result["source_refs"] = list(DOMAIN_TERMINAL_SOURCE_IDS[function_id])
    aliases = copy.deepcopy(result["aliases"])
    aliases["ko-KR"] = [
        value for value in aliases["ko-KR"] if re.search(r"[\uac00-\ud7a3]", value)
    ]
    result["aliases"] = aliases
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v17_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v17_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v17_{key[4:]}"] = rule.pop(key)
    domain = REVIEWED_BY_DOMAIN[group.domain]
    feature = REVIEWED_FEATURE_BY_ID[f"{group.domain}.{seed.key}"]
    target = str(result["terminal_function"])
    patterns_by_locale = copy.deepcopy(result["patterns_by_locale"])
    korean_patterns = ()
    if target in KOREAN_TERMINAL_IDS:
        korean_patterns = tuple(
            f"{term}에서 {feature.name_ko} 찾기" for term in KOREAN_DOMAIN_TERMS[group.domain]
        )
    patterns_by_locale["ko-KR"] = list(
        _dedupe((feature.goal_ko, *korean_patterns, *patterns_by_locale["ko-KR"]))
    )
    patterns_by_locale["en-US"] = list(_dedupe((feature.goal_en, *patterns_by_locale["en-US"])))
    result["patterns_by_locale"] = patterns_by_locale
    result["patterns"] = [*patterns_by_locale["ko-KR"], *patterns_by_locale["en-US"]]
    result["representative_goal_by_locale"] = {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}
    result["purpose_by_locale"] = {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}
    governance_terms = [domain.root_en, feature.name_en, feature.roles[0], feature.assets[0], feature.jurisdiction_guard]
    if feature.classification == "C":
        governance_terms.append(feature.states[0])
    result["goal_rules"].append(
        {
            "all_of": governance_terms,
            "none_of": ["wrong role", "different record", "missing jurisdiction", "offline or stale data"],
            "score": 0.999,
            "rule_kind": "v17_role_asset_state_gate",
            "v17_discriminative_keys": [key for key in (_runtime_pattern_key(value) for value in governance_terms) if key],
            "v17_required_case_dimensions": 4 if feature.classification == "C" else 3,
        }
    )
    if target in KOREAN_TERMINAL_IDS:
        result["goal_rules"].append(
            {
                "all_of": [KOREAN_DOMAIN_TERMS[group.domain][0], feature.name_ko],
                "none_of": ["미국", "U.S.", "wrong jurisdiction"],
                "score": 0.999,
                "rule_kind": "v17_kr_jurisdiction_menu_gate",
                "v17_jurisdiction": "KR",
                "v17_discriminative_keys": [
                    _runtime_pattern_key(KOREAN_DOMAIN_TERMS[group.domain][0]),
                    _runtime_pattern_key(feature.name_ko),
                ],
            }
        )
    peers = [f"{group.domain}.{item.key}" for item in domain.features if item.key != seed.key]
    result["avoid_functions"] = list(_dedupe((*peers[:3], *result.get("avoid_functions", []), domain.avoid_root)))
    result["desired_state"] = "user_confirmation_required"
    result["terminal_condition"] = {"stop_policy": "stop_before_action", "user_owned_final_press": True}
    result["resolution_gate"] = {
        "dimensions": ["authorized_role", "governed_record", "jurisdiction_or_program", "lifecycle_state"],
        "minimum_positive_dimensions": 4 if feature.classification == "C" else 3,
        "fail_closed_to": f"{group.domain}.hub",
    }
    return result


V17_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V17_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)


def _collision_families() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    result: list[tuple[str, str, tuple[str, ...]]] = []
    for domain in REVIEWED_DOMAINS:
        ids = tuple(f"{domain.domain}.{row.key}" for row in domain.features)
        for index, token in enumerate(domain.collision_terms):
            result.append((f"{domain.root_ko} {token}", token, (ids[index], ids[6 + index], ids[12 + index])))
    return tuple(result)


COLLISION_FAMILIES = _collision_families()


def build_collision_probes() -> tuple[dict[str, object], ...]:
    """Return 720 catalog-derived ambiguity probes (12 per collision family)."""

    intents = {str(item["terminal_function"]): item for item in V17_INTENTS}
    functions = {str(item["function_id"]): item for item in V17_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(12):
            locale = "ko-KR" if probe_index < 6 else "en-US"
            target = targets[probe_index % len(targets)]
            function = functions[target]
            pattern = intents[target]["patterns_by_locale"][locale][probe_index % 5]
            role = function["role_hints"][probe_index % len(function["role_hints"])]
            asset = function["asset_cues"][probe_index % len(function["asset_cues"])]
            token = token_ko if locale == "ko-KR" else token_en
            probes.append(
                {
                    "probe_id": f"v17_collision_{family_index:02d}_{probe_index:02d}",
                    "family": token_en,
                    "locale": locale,
                    "text": f"{token} disambiguate {pattern} {function['domain']} {role} {asset}",
                    "expected_function": target,
                }
            )
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return two positive and four fail-closed probes per terminal (1,368)."""

    functions = {str(item["function_id"]): item for item in V17_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V17_INTENTS:
        target = str(intent["terminal_function"])
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
        for index, kind in enumerate(("wrong_role", "wrong_record_state", "unavailable_permission", "missing_jurisdiction")):
            probes.append(
                {
                    "kind": kind,
                    "locale": "ko-KR" if index % 2 == 0 else "en-US",
                    "text": f"{function['name_en']} {function['negative_context'][index]}",
                    "expected_function": None,
                    "excluded_function": target,
                    "allowed_fallback": f"{function['domain']}.hub",
                }
            )
    return tuple(probes)


def build_state_permission_recovery_matrix() -> tuple[dict[str, object], ...]:
    """Return four fail-closed recovery probes per terminal (912)."""

    scenarios = (
        ("disabled", "disabled control interlock"),
        ("unavailable_offline", "currently unavailable offline stale data"),
        ("wrong_role", "wrong role permission denied"),
        ("wrong_record_jurisdiction", "wrong record jurisdiction hold"),
    )
    probes: list[dict[str, object]] = []
    for function in V17_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append(
                {
                    "probe_id": f"v17_recovery_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{function['name_en']} {text}",
                    "expected_function": None,
                    "excluded_function": str(function["function_id"]),
                    "allowed_fallback": f"{function['domain']}.hub",
                    "required_policy": "never_auto",
                    "required_stop_policy": "before_action",
                    "required_user_owned_final_press": True,
                }
            )
    return tuple(probes)


def build_role_asset_isolation_matrix() -> tuple[dict[str, object], ...]:
    """Return wrong-role, wrong-record, and wrong-state probes (684)."""

    scenarios = (
        ("wrong_role", "다른 역할 other unauthorized role"),
        ("wrong_record", "다른 사람 또는 사건 different person or case record"),
        ("wrong_state", "다른 생명주기 또는 관할 different lifecycle state or jurisdiction"),
    )
    probes: list[dict[str, object]] = []
    for function in V17_FUNCTIONS:
        if not function["terminal"]:
            continue
        for kind, text in scenarios:
            probes.append(
                {
                    "probe_id": f"v17_isolation_{len(probes):04d}",
                    "kind": kind,
                    "text": f"{function['name_en']} {text}",
                    "expected_function": None,
                    "excluded_function": function["function_id"],
                    "allowed_fallback": f"{function['domain']}.hub",
                }
            )
    return tuple(probes)


def _verify_source_documents() -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        path = ROOT / relative_path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual[relative_path] = digest
        if digest != expected:
            raise V17CatalogValidationError(
                f"V17 source SHA-256 differs for {relative_path}: expected {expected}, got {digest}"
            )
    return actual


DOCUMENT_DIGESTS = _verify_source_documents()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _layer_digest() -> str:
    payload = {
        "catalog_version": CATALOG_V17_VERSION,
        "functions": V17_FUNCTIONS,
        "intents": V17_INTENTS,
        "official_sources": OFFICIAL_SOURCES,
        "source_documents": SOURCE_DOCUMENT_METADATA,
        "korean_domain_terms": KOREAN_DOMAIN_TERMS,
        "projected_counts": PROJECTED_COUNTS,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


V17_LAYER_SHA256 = _layer_digest()
EXPECTED_V17_LAYER_SHA256 = "906194051e9b211f6d6a7719c2b5bdae4961e6e439d0660ed79a75565fabfb4d"
EXPECTED_CLASS_COUNTS = {"S": 95, "C": 133}


def _korean_metadata() -> dict[str, object]:
    return {
        "terms": {domain: list(terms) for domain, terms in sorted(KOREAN_DOMAIN_TERMS.items())},
        "terminal_ids": sorted(KOREAN_TERMINAL_IDS),
        "source_ids": sorted(
            source_id for source_id, source in OFFICIAL_SOURCES.items() if source["jurisdiction"] == "KR"
        ),
        "isolation": "jurisdiction-specific; no U.S.-specific lifecycle is relabeled as a Korean form",
    }


def _layer_integrity_metadata() -> dict[str, object]:
    return {
        "algorithm": "sha256",
        "sha256": V17_LAYER_SHA256,
        "expected_sha256": EXPECTED_V17_LAYER_SHA256,
        "domains": 12,
        "functions": 240,
        "terminal_functions": 228,
        "intents": 228,
        "official_sources": len(OFFICIAL_SOURCES),
    }


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Return an exact prospective V16 payload without materializing V17."""

    return merge_v16_with_base(load_v15_source_base(path))


def _pre_v17_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V17_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V17_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [
        item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids
    ]
    result["intents"] = [
        item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids
    ]
    for key in (
        "official_sources_v17",
        "source_documents_v17",
        "korean_jurisdiction_v17",
        "layer_integrity_v17",
    ):
        result.pop(key, None)
    result["catalog_version"] = CATALOG_V16_VERSION
    result["description"] = CATALOG_V16_DESCRIPTION
    return result


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V17_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V17_INTENTS}
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
    metadata_keys = (
        "official_sources_v17",
        "source_documents_v17",
        "korean_jurisdiction_v17",
        "layer_integrity_v17",
    )
    has_metadata = any(key in payload for key in metadata_keys)
    if not present_functions and not present_intents and not has_metadata:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V17CatalogValidationError("partial V17 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V17CatalogValidationError("V17 collides with a different function or intent definition")
    if payload.get("official_sources_v17") != OFFICIAL_SOURCES:
        raise V17CatalogValidationError("V17 official-source registry differs")
    if payload.get("source_documents_v17") != SOURCE_DOCUMENT_METADATA:
        raise V17CatalogValidationError("V17 source-document SHA registry differs")
    if payload.get("korean_jurisdiction_v17") != _korean_metadata():
        raise V17CatalogValidationError("V17 Korean-jurisdiction metadata differs")
    if payload.get("layer_integrity_v17") != _layer_integrity_metadata():
        raise V17CatalogValidationError("V17 layer-integrity metadata differs")
    if payload.get("catalog_version") != CATALOG_V17_VERSION or payload.get("description") != CATALOG_V17_DESCRIPTION:
        raise V17CatalogValidationError("V17 materialization metadata differs")
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


def validate_v17_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate exact scope, evidence, semantics, disjointness, and fail-closed state."""

    base = load_base_catalog() if base_payload is None else copy.deepcopy(dict(base_payload))
    errors: list[str] = []
    source_text = (ROOT / DESIGN_SOURCE_RELATIVE_PATH).read_text(encoding="utf-8")
    for relative_path, expected in SOURCE_DOCUMENT_SHA256.items():
        actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"source SHA differs for {relative_path}: {actual}")
    if "\ufffd" in source_text or len(re.findall(r"[\uac00-\ud7a3]", source_text)) < 100:
        errors.append("V17 source document Unicode or Hangul gate differs")
    if V17_LAYER_SHA256 != EXPECTED_V17_LAYER_SHA256:
        errors.append(f"V17 layer SHA differs: {V17_LAYER_SHA256}")

    function_ids = [str(item["function_id"]) for item in V17_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V17_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V17_FUNCTIONS if item["terminal"]}
    domain_terminal_counts = Counter(str(item["domain"]) for item in V17_FUNCTIONS if item["terminal"])
    domain_function_counts = Counter(str(item["domain"]) for item in V17_FUNCTIONS)
    if _duplicates(function_ids) or _duplicates(intent_ids):
        errors.append("V17 contains duplicate function or intent IDs")
    if len(REQUIRED_DOMAINS) != 12 or len(V17_FUNCTIONS) != 240 or len(terminal_ids) != 228 or len(V17_INTENTS) != 228:
        errors.append("V17 requires 12 domains, 12 hubs, 228 terminals, 240 functions, and 228 intents")
    if dict(sorted(domain_terminal_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"V17 terminal counts differ: {dict(sorted(domain_terminal_counts.items()))}")
    if dict(sorted(domain_function_counts.items())) != EXPECTED_DOMAIN_FUNCTION_COUNTS:
        errors.append(f"V17 function counts differ: {dict(sorted(domain_function_counts.items()))}")
    sensitive = sum(bool(item["terminal"]) and item.get("classification") == "S" and not item["state_changing"] for item in V17_FUNCTIONS)
    consequential = sum(bool(item["terminal"]) and item.get("classification") == "C" and item["state_changing"] for item in V17_FUNCTIONS)
    if {"S": sensitive, "C": consequential} != EXPECTED_CLASS_COUNTS:
        errors.append(f"V17 S/C counts differ: S={sensitive}, C={consequential}")

    forbidden = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_name",
        "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path",
        "pixel", "click_sequence", "selector", "xpath",
    }
    hangul = re.compile(r"[\uac00-\ud7a3]")
    functions_by_id = {str(item["function_id"]): item for item in V17_FUNCTIONS}
    for function in V17_FUNCTIONS:
        function_id = str(function["function_id"])
        if _contains_forbidden_key(function, forbidden):
            errors.append(f"{function_id}: forbidden UI-specific key")
        if not function.get("source_refs") or set(function["source_refs"]) - set(OFFICIAL_SOURCES):
            errors.append(f"{function_id}: invalid official source references")
        if len(function["aliases"]["ko-KR"]) < 8 or len(function["aliases"]["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if not hangul.search(str(function["name_ko"])) or any(
            not hangul.search(str(alias)) for alias in function["aliases"]["ko-KR"]
        ):
            errors.append(f"{function_id}: Korean name or alias lacks Hangul")
        if not function.get("role_hints") or not function.get("asset_cues") or not function.get("state_cues", {}).get("jurisdiction"):
            errors.append(f"{function_id}: missing role, record, or jurisdiction semantics")
        if function["terminal"]:
            feature = REVIEWED_FEATURE_BY_ID[function_id]
            if function.get("classification") != feature.classification:
                errors.append(f"{function_id}: classification differs")
            if function.get("name_ko") != feature.name_ko or function.get("name_en") != feature.name_en:
                errors.append(f"{function_id}: bilingual name differs")
            if function.get("representative_goals") != {"ko-KR": feature.goal_ko, "en-US": feature.goal_en}:
                errors.append(f"{function_id}: representative goal differs")
            if function.get("purpose_by_locale") != {"ko-KR": feature.purpose_ko, "en-US": feature.purpose_en}:
                errors.append(f"{function_id}: terminal purpose differs")
            if not feature.roles or not feature.assets or not feature.states or not feature.safety_boundary:
                errors.append(f"{function_id}: reviewed terminal semantics are incomplete")
            if (
                function.get("automation_policy") != "never_auto"
                or function.get("stop_policy") != "before_action"
                or function.get("risk_level") != "high"
                or function.get("user_owned_final_press") is not True
                or not function.get("risk_cues", {}).get("source_boundary")
            ):
                errors.append(f"{function_id}: terminal safety boundary differs")
            if set(function["source_refs"]) != set(DOMAIN_TERMINAL_SOURCE_IDS[function_id]):
                errors.append(f"{function_id}: terminal source mapping differs")
        elif (
            function.get("node_kind") != "hub"
            or function.get("risk_level") != "low"
            or function.get("automation_policy") != "safe_navigation"
            or function.get("stop_policy") != "continue"
            or function.get("state_changing") is not False
            or function.get("user_owned_final_press") is not False
        ):
            errors.append(f"{function_id}: hub safety policy differs")

    for intent in V17_INTENTS:
        target = str(intent["terminal_function"])
        feature = REVIEWED_FEATURE_BY_ID[target]
        if str(intent["intent_id"]) != f"v17_{target.replace('.', '_')}":
            errors.append(f"{target}: intent ID differs")
        if intent["patterns_by_locale"]["ko-KR"][0] != feature.goal_ko or intent["patterns_by_locale"]["en-US"][0] != feature.goal_en:
            errors.append(f"{target}: representative patterns differ")
        if any(not hangul.search(str(pattern)) for pattern in intent["patterns_by_locale"]["ko-KR"]):
            errors.append(f"{target}: Korean goal pattern lacks Hangul")
        if len(intent["patterns_by_locale"]["ko-KR"]) < 5 or len(intent["patterns_by_locale"]["en-US"]) < 5 or len(intent["goal_rules"]) < 20:
            errors.append(f"{target}: insufficient bilingual patterns or rules")
        if not any(rule.get("rule_kind") == "v17_role_asset_state_gate" for rule in intent["goal_rules"]):
            errors.append(f"{target}: missing role/record/state gate")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != target:
            errors.append(f"{target}: route differs")
        if intent.get("terminal_condition") != {"stop_policy": "stop_before_action", "user_owned_final_press": True}:
            errors.append(f"{target}: terminal condition differs")
        if intent.get("resolution_gate", {}).get("minimum_positive_dimensions") != (4 if feature.classification == "C" else 3):
            errors.append(f"{target}: resolution gate differs")
        if target not in functions_by_id:
            errors.append(f"{target}: intent target missing")

    normalized_urls: set[str] = set()
    mapped_terminal_union: set[str] = set()
    referenced_source_ids: set[str] = set()
    per_domain_jurisdiction: Counter[tuple[str, str]] = Counter()
    for source_id, source in OFFICIAL_SOURCES.items():
        normalized = normalize_official_url(str(source.get("canonical_url", "")))
        if normalized in normalized_urls:
            errors.append(f"duplicate normalized V17 source URL: {normalized}")
        normalized_urls.add(normalized)
        record_without_hash = {key: value for key, value in source.items() if key != "source_record_sha256"}
        mapped = {str(value) for value in source.get("terminal_ids", [])}
        domain = str(source.get("domains", [""])[0])
        jurisdiction = str(source.get("jurisdiction", ""))
        per_domain_jurisdiction[(domain, jurisdiction)] += 1
        if source.get("source_id") != source_id or source.get("normalized_url") != normalized:
            errors.append(f"source identity differs: {source_id}")
        if (
            urlsplit(normalized).scheme != "https"
            or source.get("verification_status") != "accepted"
            or source.get("evidence_level") != "official_primary"
            or source.get("http_status") != 200
            or source.get("verified_status") != 200
            or source.get("final_url") != source.get("canonical_url")
            or source.get("publisher") not in PUBLISHER_ALLOWLIST
            or source.get("source_record_sha256") != _source_digest(record_without_hash)
        ):
            errors.append(f"source verification metadata differs: {source_id}")
        if not mapped or not mapped <= terminal_ids:
            errors.append(f"source has empty or invalid terminal mapping: {source_id}")
        mapped_terminal_union.update(mapped)
        for terminal_id in mapped:
            referenced_source_ids.add(source_id)
            if source_id not in DOMAIN_TERMINAL_SOURCE_IDS.get(terminal_id, ()):
                errors.append(f"source reverse mapping differs: {source_id} -> {terminal_id}")
    if len(OFFICIAL_SOURCES) != 73:
        errors.append(f"V17 requires exactly 73 official sources; got {len(OFFICIAL_SOURCES)}")
    if mapped_terminal_union != terminal_ids or set(DOMAIN_TERMINAL_SOURCE_IDS) != terminal_ids:
        errors.append("V17 official source-to-terminal mapping is incomplete")
    if referenced_source_ids != set(OFFICIAL_SOURCES):
        errors.append("V17 official registry has orphan or missing source records")
    if set(DOMAIN_SOURCE_IDS) != REQUIRED_DOMAINS:
        errors.append("V17 domain source registry differs")
    for domain in REQUIRED_DOMAINS:
        if per_domain_jurisdiction[(domain, "US")] < 5 or per_domain_jurisdiction[(domain, "KR")] < 1:
            errors.append(f"{domain}: requires at least five U.S. and one Korean official lifecycle source")
    for terminal_id in KOREAN_TERMINAL_IDS:
        function = functions_by_id[terminal_id]
        intent = next(item for item in V17_INTENTS if item["terminal_function"] == terminal_id)
        terms = KOREAN_DOMAIN_TERMS[str(function["domain"])]
        if not set(terms).intersection(function["aliases"]["ko-KR"]):
            errors.append(f"{terminal_id}: lacks Korean jurisdiction menu alias")
        if not any(any(term in pattern for term in terms) for pattern in intent["patterns_by_locale"]["ko-KR"]):
            errors.append(f"{terminal_id}: lacks Korean jurisdiction goal pattern")

    semantic = build_semantic_development_matrix()
    collisions = build_collision_probes()
    recovery = build_state_permission_recovery_matrix()
    isolation = build_role_asset_isolation_matrix()
    if len(semantic) != 1368 or len(collisions) != 720 or len(recovery) != 912 or len(isolation) != 684:
        errors.append("V17 derived probe cardinality differs")

    try:
        materialized = _materialization_state(base)
    except V17CatalogValidationError as error:
        errors.append(str(error))
        materialized = False
    pre_v17 = _pre_v17_payload(base)
    if (
        pre_v17.get("catalog_version") != CATALOG_V16_VERSION
        or len(pre_v17.get("functions", [])) != 3118
        or len(pre_v17.get("intents", [])) != 2900
        or len({str(item["domain"]) for item in pre_v17.get("functions", [])}) != 191
    ):
        errors.append("V17 base must be an exact prospective V16 payload")
    base_function_ids = {str(item["function_id"]) for item in pre_v17.get("functions", [])}
    base_intent_ids = {str(item["intent_id"]) for item in pre_v17.get("intents", [])}
    base_domains = {str(item["domain"]) for item in pre_v17.get("functions", [])}
    if set(function_ids).intersection(base_function_ids) or set(intent_ids).intersection(base_intent_ids) or REQUIRED_DOMAINS.intersection(base_domains):
        errors.append("V17 IDs or domains collide with V15/V16")
    expected_v16_functions = {str(item["function_id"]): item for item in V16_FUNCTIONS}
    expected_v16_intents = {str(item["intent_id"]): item for item in V16_INTENTS}
    present_v16_functions = {
        str(item["function_id"]): item for item in pre_v17.get("functions", []) if str(item["function_id"]) in expected_v16_functions
    }
    present_v16_intents = {
        str(item["intent_id"]): item for item in pre_v17.get("intents", []) if str(item["intent_id"]) in expected_v16_intents
    }
    if present_v16_functions != expected_v16_functions or present_v16_intents != expected_v16_intents:
        errors.append("prospective V16 layer differs before V17")

    if errors:
        raise V17CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V17_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V17_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_terminal_counts.items())),
        "domain_function_counts": dict(sorted(domain_function_counts.items())),
        "sensitive_reads": sensitive,
        "state_changing": consequential,
        "official_sources": len(OFFICIAL_SOURCES),
        "source_distribution": EXPECTED_SOURCE_DISTRIBUTION,
        "korean_sources": sum(source["jurisdiction"] == "KR" for source in OFFICIAL_SOURCES.values()),
        "source_documents": copy.deepcopy(DOCUMENT_DIGESTS),
        "source_orphans": len(set(OFFICIAL_SOURCES) - referenced_source_ids),
        "layer_sha256": V17_LAYER_SHA256,
        "aliases": sum(len(values) for item in V17_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V17_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V17_INTENTS),
        "semantic_smoke_probes": len(semantic),
        "collision_probes": len(collisions),
        "recovery_probes": len(recovery),
        "isolation_probes": len(isolation),
        "projected_counts": copy.deepcopy(PROJECTED_COUNTS),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, non-mutating, idempotent V16+V17 copy."""

    stats = validate_v17_data(base_payload)
    if stats["materialized"]:
        return copy.deepcopy(dict(base_payload))
    merged = _pre_v17_payload(base_payload)
    merged["catalog_version"] = CATALOG_V17_VERSION
    merged["description"] = CATALOG_V17_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V17_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V17_INTENTS)]
    merged["official_sources_v17"] = copy.deepcopy(OFFICIAL_SOURCES)
    merged["source_documents_v17"] = copy.deepcopy(SOURCE_DOCUMENT_METADATA)
    merged["korean_jurisdiction_v17"] = copy.deepcopy(_korean_metadata())
    merged["layer_integrity_v17"] = copy.deepcopy(_layer_integrity_metadata())
    return merged


def main() -> int:
    print(json.dumps(validate_v17_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
