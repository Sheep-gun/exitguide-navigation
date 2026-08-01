from __future__ import annotations

"""Reviewed v11 professional-operations ontology for universal navigation.

The pack is deliberately app independent: it models destinations, roles,
assets, states, and safety boundaries, never packages, resource IDs,
coordinates, screenshots, or fixed UI paths.  Every terminal is fail-closed;
the user owns the final press.
"""

import copy
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import urlparse

from navigation_catalog_v10_data import (
    CATALOG_V10_DESCRIPTION,
    CATALOG_V10_VERSION,
    F,
    G,
    FeatureSeed,
    GroupSeed,
    _build_feature as _v10_build_feature,
    _build_intent as _v10_build_intent,
    _build_root as _v10_build_root,
    _pre_v10_payload,
    _rule_signature,
    _runtime_pattern_key,
    merge_with_base as merge_v10_with_base,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_CATALOG = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
CATALOG_V11_VERSION = "11.0.0"
COLLECTED_ON = "2026-07-30"
CATALOG_V11_DESCRIPTION = (
    "ExitGuide professional operations ontology v11: app-agnostic clinical, "
    "pharmacy, insurance, airline, telecom, ITSM/CMDB, SOC, social-services, "
    "probate, port-logistics, clinical-trial, and emergency-response destinations; "
    "every final press remains user-owned."
)


def _source(publisher: str, title: str, url: str) -> dict[str, object]:
    return {
        "publisher": publisher,
        "title": title,
        "url": url,
        "collected_on": COLLECTED_ON,
        "evidence_level": "official_primary",
        "verified_status": 200,
        "verification_method": "official first-party page reviewed in the v11 coverage audit",
    }


OFFICIAL_SOURCES: dict[str, dict[str, object]] = {
    "oracle_ehr_overview": _source("Oracle Health", "Oracle Health EHR", "https://docs.oracle.com/en/industries/health/oracle-health-ehr/"),
    "oracle_ehr_orders": _source("Oracle Health", "Orders", "https://docs.oracle.com/en/industries/health/oracle-health-ehr/ehrug/orders.html"),
    "oracle_ehr_inbox": _source("Oracle Health", "Inbox", "https://docs.oracle.com/en/industries/health/oracle-health-ehr/ehrfg/inbox.html"),
    "oracle_ehr_results": _source("Oracle Health", "Results", "https://docs.oracle.com/en/industries/health/oracle-health-ehr/ehrug/results.html"),
    "hl7_medication_dispense": _source("HL7", "MedicationDispense", "https://hl7.org/fhir/medicationdispense.html"),
    "oracle_medication_dispense_api": _source("Oracle Health", "MedicationDispense REST endpoints", "https://docs.oracle.com/en/industries/health/millennium-platform-apis/mfrap/api-medicationdispense.html"),
    "fda_rems_roles": _source("FDA", "Roles of Different Participants in REMS", "https://www.fda.gov/drugs/risk-evaluation-and-mitigation-strategies-rems/roles-different-participants-rems"),
    "fda_dscsa_pharmacists": _source("FDA", "Pharmacists and DSCSA requirements", "https://www.fda.gov/drugs/drug-supply-chain-security-act-dscsa/pharmacists-utilize-dscsa-requirements-protect-your-patients"),
    "guidewire_exposures": _source("Guidewire", "Overview of exposures in ClaimCenter", "https://docs.guidewire.com/cloud/is/202603/cloudapibf/cloudAPI/ClaimCenter/fnol/exposures/c_overview-of-exposures-in-ClaimCenter.html"),
    "guidewire_reserves": _source("Guidewire", "Overview of reserves in ClaimCenter", "https://docs.guidewire.com/cloud/cc/202511/cloudapibf/cloudAPI/topics/112-CCFin/01-reserves/c_overview-of-reserves-in-ClaimCenter.html"),
    "guidewire_checks": _source("Guidewire", "Creating checks", "https://docs.guidewire.com/cloud/cc/202507/cloudapibf/cloudAPI/topics/112-CCFin/02-check-creating/c_creating-checks.html"),
    "guidewire_recoveries": _source("Guidewire", "Recoveries and recovery reserves", "https://docs.guidewire.com/cloud/is/202603/cloudapibf/cloudAPI/ClaimCenter/financials/recoveries.html"),
    "boeing_foreflight_dispatch": _source("Boeing", "ForeFlight Dispatch booklet", "https://services.boeing.com/bgsmedias/NBAA-2021-Dispatch-booklet.pdf?context=bWFzdGVyfHJvb3R8MTIwMDMwNjR8YXBwbGljYXRpb24vcGRmfGg0Ny9oOTkvODgzOTQ3MDk0MDE5MC5wZGZ8MzcyY2RmMjM1NTgxYzIzODM0ZWJlMmU4YzM3MTAyYTZiMjc3NjRiMjMzMzQwODAyYWQxNTcxNjYzNmE5MzUyYQ"),
    "boeing_flight_manuals": _source("Boeing", "Licensed Flight Training Manuals", "https://services.boeing.com/training-solutions/flight-training/licensed-manuals"),
    "icao_fatigue_management": _source("ICAO", "Fatigue Management Approaches", "https://www.icao.int/operational-safety/fatigue-management/fatigue-management-approaches"),
    "sap_technical_debrief": _source("SAP", "Technical Debriefing", "https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/e08e0da88aa64d9095334cdb5fa3b25d/704b859d56c440e8b3f63b5b22b55852.html"),
    "servicenow_telecom_fsm": _source("ServiceNow", "Field Service Management for Telecommunications", "https://www.servicenow.com/content/dam/servicenow-assets/public/en-us/doc-type/resource-center/data-sheet/ds-field-service-management-for-telecommunications.pdf"),
    "microsoft_field_service_mobile": _source("Microsoft", "Work with the Field Service mobile app", "https://learn.microsoft.com/en-us/dynamics365/field-service/mobile/get-work-done-mobile-app"),
    "microsoft_field_service_architecture": _source("Microsoft", "Field Service work order architecture", "https://learn.microsoft.com/en-us/dynamics365/field-service/field-service-architecture"),
    "servicenow_fsm_inventory": _source("ServiceNow", "Manage inventory in Field Service Management", "https://www.servicenow.com/docs/r/field-service-management/work-order-management/sourcing-parts.html"),
    "servicenow_mobile_incidents": _source("ServiceNow", "My incidents in ITSM Mobile Agent", "https://www.servicenow.com/docs/r/it-service-management/itsm-mobile-agent/assigned-incidents-mobile.html"),
    "servicenow_cmdb_overview": _source("ServiceNow", "Overview of CMDB", "https://www.servicenow.com/docs/r/servicenow-platform/configuration-management-database-cmdb/cnfig-mgmt-and-cmdb.html"),
    "servicenow_cmdb_relationships": _source("ServiceNow", "CI relationships in the CMDB", "https://www.servicenow.com/docs/r/servicenow-platform/configuration-management-database-cmdb/c_CIRelationships.html"),
    "servicenow_cmdb_data_manager": _source("ServiceNow", "Working with CMDB Data Manager", "https://www.servicenow.com/docs/r/servicenow-platform/configuration-management-database-cmdb/cmdb-data-management.html"),
    "sentinel_investigate": _source("Microsoft", "Investigate Microsoft Sentinel incidents", "https://learn.microsoft.com/en-us/azure/sentinel/investigate-incidents"),
    "sentinel_triage": _source("Microsoft", "Navigate, triage and manage Sentinel incidents", "https://learn.microsoft.com/en-us/azure/sentinel/incident-navigate-triage"),
    "defender_response_actions": _source("Microsoft", "Take response actions on a device", "https://learn.microsoft.com/en-us/defender-endpoint/respond-machine-alerts"),
    "servicenow_sir": _source("ServiceNow", "Security Incident Response", "https://www.servicenow.com/docs/r/security-management/security-incident-response/sir-landing-page.html"),
    "salesforce_public_sector": _source("Salesforce", "Public Sector Solutions", "https://help.salesforce.com/s/articleView?id=release-notes.rn_public_sector_solutions.htm&language=en_US&release=244&type=5"),
    "salesforce_care_plans": _source("Salesforce", "Care Plans for Program and Case Management", "https://help.salesforce.com/s/articleView?id=ind.prog_case_mgmt_care_plans.htm&language=en_US&type=5"),
    "govuk_youth_assessment": _source("UK Youth Justice Board", "How to assess children in the youth justice system", "https://www.gov.uk/guidance/case-management-guidance/how-to-assess-children-in-the-youth-justice-system"),
    "govuk_adult_social_care": _source("UK Government", "Adult social care terminology", "https://www.gov.uk/government/publications/adult-social-care-finance-return-2025-to-2026/ascfr-terminology-and-its-usage"),
    "hmcts_probate": _source("HM Courts & Tribunals Service", "Apply for probate with MyHMCTS", "https://www.gov.uk/government/publications/myhmcts-how-to-apply-for-probate-online/apply-for-probate-with-myhmcts"),
    "govuk_applying_probate": _source("UK Government", "Applying for probate", "https://www.gov.uk/applying-for-probate"),
    "irs_estate_admin": _source("IRS", "Responsibilities of an estate administrator", "https://www.irs.gov/individuals/responsibilities-of-an-estate-administrator"),
    "irs_publication_559": _source("IRS", "Publication 559", "https://www.irs.gov/publications/p559"),
    "mumbai_ipos": _source("Mumbai Port Authority", "Integrated Port Operating System", "https://www.mumbaiport.gov.in/show_content.php?lang=1&level=3&lid=640&ls_id=834"),
    "imo_cargo_securing": _source("IMO", "Cargo Securing and Packing", "https://www.imo.org/en/ourwork/safety/pages/cargosecuring-default.aspx"),
    "imo_imdg": _source("IMO", "International Maritime Dangerous Goods Code", "https://www.imo.org/en/ourwork/safety/pages/dangerousgoods-default.aspx"),
    "imo_ems": _source("IMO", "Emergency Response Procedures for Ships Carrying Dangerous Goods", "https://www.imo.org/en/ourwork/safety/pages/ems-guide.aspx"),
    "oracle_clinical_quick_start": _source("Oracle Life Sciences", "Quick Start for Sites", "https://docs.oracle.com/en/industries/life-sciences/clinical-one/quick-site-setup/index_text.html"),
    "oracle_clinical_modes": _source("Oracle Life Sciences", "Access study modes and pages", "https://docs.oracle.com/en/industries/life-sciences/clinical-one/site-information/access-study-modes.html"),
    "oracle_clinical_randomize_dispense": _source("Oracle Life Sciences", "Complete a randomization or dispensation visit", "https://docs.oracle.com/en/industries/life-sciences/clinical-one/site-information/complete-randomization-or-dispensation-visit.html"),
    "fda_clinical_investigators": _source("FDA", "Federal Regulations for Clinical Investigators", "https://www.fda.gov/drugs/investigational-new-drug-ind-application/federal-regulations-clinical-investigators"),
    "fda_protocol_deviations": _source("FDA", "Protocol Deviations guidance", "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/protocol-deviations-clinical-investigations-drugs-biological-products-and-devices"),
    "fema_ems_templates": _source("FEMA/USFA", "Operational Templates and Guidance for EMS Mass Incident Deployment", "https://www.usfa.fema.gov/downloads/pdf/publications/templates_guidance_ems_mass_incident_deployment.pdf"),
    "fema_division_checklist": _source("FEMA", "Division/Group Supervisor Position Checklist", "https://training.fema.gov/emiweb/is/icsresource/assets/dgs_pcl.pdf"),
    "esri_field_maps_get_started": _source("Esri", "Get started with ArcGIS Field Maps", "https://doc.arcgis.com/en/field-maps/get-started/get-started.htm"),
    "esri_field_maps_tasks": _source("Esri", "Prepare tasks in Field Maps", "https://doc.arcgis.com/en/field-maps/latest/prepare-maps/prepare-tasks.htm"),
    "esri_field_maps_download": _source("Esri", "Download maps", "https://doc.arcgis.com/en/field-maps/ios/use-maps/download-maps.htm"),
}


FeatureRow = tuple[str, str, str, str]


def _rows(text: str) -> tuple[FeatureRow, ...]:
    result: list[FeatureRow] = []
    for raw in text.strip().splitlines():
        key, name_ko, name_en, mode = (value.strip() for value in raw.split("|"))
        result.append((key, name_ko, name_en, mode))
    return tuple(result)


def _feature_rows(
    rows: Sequence[FeatureRow], *, sources: str, negative: str,
) -> tuple[FeatureSeed, ...]:
    result: list[FeatureSeed] = []
    for key, name_ko, name_en, mode in rows:
        action_ko = f"{name_ko} 찾기" if mode == "sensitive" else f"{name_ko} 작업"
        action_en = f"review {name_en.lower()}" if mode == "sensitive" else f"perform {name_en.lower()}"
        result.append(F(
            key,
            name_ko,
            name_en,
            "|".join((action_ko, f"{name_ko} 화면", f"{name_ko} 세부", f"{name_ko} 메뉴", f"{name_ko} 정보", f"{name_ko} 열기")),
            "|".join((action_en, f"{name_en} screen", f"{name_en} details", f"{name_en} workflow", f"{name_en} information", f"open {name_en.lower()}")),
            "|".join((name_ko, action_ko, name_en, action_en)),
            negative,
            mode,
            sources=sources,
        ))
    return tuple(result)


CLINICAL_ROWS = _rows("""
patient_list|환자 목록|Patient list|sensitive
patient_chart_summary|환자 차트 요약|Patient chart summary|sensitive
allergy_review|환자 알레르기 검토|Patient allergy review|sensitive
problem_list_review|환자 문제 목록 검토|Patient problem list review|sensitive
medication_reconciliation|투약 조정|Medication reconciliation|submit
vital_sign_record|활력징후 기록|Vital sign record|submit
clinical_note_draft|임상 기록 초안|Clinical note draft|submit
clinical_note_sign|임상 기록 서명|Clinical note signing|submit
order_entry|임상 처방 입력|Clinical order entry|submit
order_modify_stop|임상 처방 변경·중지|Clinical order modify or stop|submit
specimen_collection_record|검체 채취 기록|Specimen collection record|submit
medication_administration|투약 시행 기록|Medication administration record|submit
result_review|임상 결과 검토|Clinical result review|sensitive
result_endorse|임상 결과 확인 서명|Clinical result endorsement|submit
referral_create|진료 의뢰 생성|Clinical referral creation|submit
care_team_message|진료팀 메시지|Care team message|submit
handoff_update|환자 인계 갱신|Patient handoff update|submit
discharge_instruction|퇴원 안내 작성|Discharge instruction preparation|submit
care_plan_update|진료 계획 갱신|Care plan update|submit
encounter_close|진료 종료|Clinical encounter closure|submit
""")

PHARMACY_ROWS = _rows("""
prescription_queue|처방전 대기열|Prescription queue|sensitive
prescription_detail|처방전 상세|Prescription detail|sensitive
patient_medication_profile|환자 투약 프로필|Patient medication profile|sensitive
clinical_safety_review|조제 임상 안전 검토|Dispensing clinical safety review|submit
insurance_claim_adjudication|약제 보험 청구 심사|Pharmacy insurance claim adjudication|submit
prescriber_clarification|처방자 확인 요청|Prescriber clarification|submit
substitution_decision|대체조제 결정|Medication substitution decision|submit
fill_quantity_days_supply|조제 수량·투약일수|Fill quantity and days supply|submit
label_generate|조제 라벨 생성|Dispensing label generation|submit
product_lot_serial_scan|의약품 로트·일련번호 스캔|Medication lot and serial scan|submit
compound_prepare|조제·혼합 준비|Compound preparation|submit
final_verification|조제 최종 검수|Dispensing final verification|submit
controlled_substance_log|마약류 기록|Controlled substance log|submit
dispense_hold_resume|조제 보류·재개|Dispense hold or resume|submit
patient_counseling_record|복약지도 기록|Patient counseling record|submit
pickup_identity_receiver_check|수령인 신원 확인|Pickup identity and receiver check|submit
handover_complete|의약품 인계 완료|Medication handover completion|submit
return_to_stock_reverse|재고 반납·청구 취소|Return to stock and reversal|submit
""")

CLAIMS_ROWS = _rows("""
claim_queue|보험 사고 대기열|Insurance claim queue|sensitive
claim_summary|보험 사고 요약|Insurance claim summary|sensitive
policy_coverage_verify|보험 보장 확인|Policy coverage verification|sensitive
loss_parties_contacts|사고 관계자·연락처|Loss parties and contacts|sensitive
incident_exposure_review|사고·손해 항목 검토|Incident and exposure review|sensitive
document_evidence_review|보험 증빙 문서 검토|Claim document evidence review|sensitive
assign_reassign_claim|보험 사고 배정·재배정|Assign or reassign claim|submit
claimant_contact_log|청구인 연락 기록|Claimant contact log|submit
coverage_decision|보험 보장 결정|Coverage decision|submit
exposure_create|손해 항목 생성|Claim exposure creation|submit
reserve_set|보험 준비금 설정|Claim reserve setting|submit
appraisal_inspection_assign|손해사정·검사 배정|Appraisal or inspection assignment|submit
liability_assessment|보험 책임 평가|Liability assessment|submit
settlement_offer|보험 합의 제안|Settlement offer|submit
payment_check_issue|보험금 지급 발행|Claim payment or check issuance|submit
recovery_subrogation|구상·회수 처리|Recovery and subrogation|submit
fraud_referral|보험 사기 조사 의뢰|Fraud investigation referral|submit
claim_note|보험 사고 메모|Claim note|submit
close_reopen_exposure|손해 항목 종결·재개|Close or reopen exposure|submit
close_reopen_claim|보험 사고 종결·재개|Close or reopen claim|submit
""")

AIRLINE_ROWS = _rows("""
roster|승무원 근무표|Crew roster|sensitive
duty_details|승무원 근무 상세|Crew duty details|sensitive
flight_sector_briefing|비행 구간 브리핑|Flight sector briefing|sensitive
crew_list_positions|승무원 명단·직책|Crew list and positions|sensitive
aircraft_assignment|항공기 배정|Aircraft assignment|sensitive
operational_flight_plan|운항 비행계획|Operational flight plan|sensitive
weather_notam|기상·항공고시|Weather and NOTAM|sensitive
manual_bulletin|운항 매뉴얼·게시물|Operational manual and bulletin|sensitive
flight_duty_limit_assessment|비행근무시간 제한 평가|Flight duty limit assessment|sensitive
roster_change_ack|근무표 변경 확인|Roster change acknowledgement|submit
duty_checkin|승무 근무 체크인|Duty check-in|submit
fit_for_duty_declaration|근무 적합 선언|Fit-for-duty declaration|submit
fatigue_report|승무원 피로 보고|Crew fatigue report|submit
briefing_ack|운항 브리핑 확인|Flight briefing acknowledgement|submit
emergency_duties_signoff|비상 임무 확인 서명|Emergency duties sign-off|submit
defect_technical_debrief|결함·기술 디브리핑|Defect and technical debrief|submit
cabin_service_issue|객실 서비스 문제 보고|Cabin service issue report|submit
flight_report_submit|비행 보고서 제출|Flight report submission|submit
""")

TELECOM_ROWS = _rows("""
assigned_work_order|통신 작업지시 목록|Assigned telecom work order|sensitive
site_customer_access|통신 현장·고객 출입 정보|Site and customer access information|sensitive
network_asset_detail|통신망 자산 상세|Network asset detail|sensitive
port_circuit_trace|포트·회선 추적|Port and circuit trace|sensitive
equipment_serial_scan|통신 장비 일련번호 스캔|Equipment serial scan|sensitive
route_checkin|현장 이동·체크인|Route and site check-in|submit
work_order_accept|통신 작업지시 수락|Telecom work order acceptance|submit
safety_permit_checklist|현장 안전 허가 체크리스트|Field safety permit checklist|submit
signal_line_test|신호·회선 시험|Signal and line test|submit
fiber_copper_splice_record|광·동선 접속 기록|Fiber or copper splice record|submit
device_config_activate|통신 장비 설정·개통|Device configuration and activation|submit
service_provision_test|통신 서비스 개통 시험|Service provisioning test|submit
outage_escalation|통신 장애 상향 보고|Network outage escalation|submit
parts_stock_request|현장 부품 요청|Field parts stock request|submit
parts_consume_return|현장 부품 사용·반납|Field parts consume or return|submit
customer_service_restore_ack|고객 서비스 복구 확인|Customer service restoration acknowledgement|submit
photo_signature|현장 사진·서명 제출|Field photo and signature submission|submit
work_order_complete_sync|작업 완료·동기화|Work order completion and synchronization|submit
""")

ITSM_ROWS = _rows("""
incident_queue|IT 사고 대기열|IT incident queue|sensitive
incident_detail|IT 사고 상세|IT incident detail|sensitive
problem_record_review|문제 기록 검토|Problem record review|sensitive
known_error_review|알려진 오류 검토|Known error review|sensitive
change_request_review|변경 요청 검토|Change request review|sensitive
ci_search_detail|구성항목 검색·상세|Configuration item search and detail|sensitive
ci_relationship_map|구성항목 관계도|Configuration item relationship map|sensitive
ci_baseline_compare|구성항목 기준선 비교|Configuration item baseline comparison|sensitive
service_dependency_impact|서비스 의존성·영향|Service dependency and impact|sensitive
assign_reassign|IT 사고 배정·재배정|IT incident assignment or reassignment|submit
incident_work_note|IT 사고 작업 메모|IT incident work note|submit
priority_severity_update|우선순위·심각도 갱신|Priority and severity update|submit
major_incident_propose|중대 사고 제안|Major incident proposal|submit
incident_resolve|IT 사고 해결 처리|IT incident resolution|submit
change_risk_assessment|변경 위험 평가|Change risk assessment|submit
change_approve_reject|변경 승인·거절|Change approval or rejection|submit
change_implement_status|변경 구현 상태 갱신|Change implementation status update|submit
ci_create_edit|구성항목 생성·편집|Configuration item create or edit|submit
ci_relationship_edit|구성항목 관계 편집|Configuration item relationship edit|submit
ci_retire_archive|구성항목 폐기·보관|Configuration item retirement or archive|submit
""")

SOC_ROWS = _rows("""
alert_incident_queue|보안 경보·사고 대기열|Security alert and incident queue|sensitive
incident_detail|보안 사고 상세|Security incident detail|sensitive
alert_evidence_timeline|보안 증거·시간선|Security evidence timeline|sensitive
entity_investigation_graph|보안 개체 조사 그래프|Security entity investigation graph|sensitive
related_incident_hunt|연관 사고 헌팅|Related incident hunt|sensitive
indicator_enrichment|위협 지표 보강|Threat indicator enrichment|sensitive
query_hunt|보안 쿼리 헌팅|Security query hunt|sensitive
assign_owner|보안 사고 담당자 배정|Security incident owner assignment|submit
severity_status_update|보안 심각도·상태 갱신|Security severity and status update|submit
case_comment|보안 사례 의견|Security case comment|submit
contain_device|보안 장치 격리 조치|Device containment|submit
isolate_device|보안 장치 네트워크 차단|Device isolation|submit
contain_user|보안 사용자 차단|User containment|submit
block_indicator|위협 지표 차단|Threat indicator blocking|submit
collect_investigation_package|조사 패키지 수집|Investigation package collection|submit
quarantine_file|악성 파일 격리|File quarantine|submit
run_response_playbook|대응 플레이북 실행|Response playbook execution|submit
eradication_recovery_status|제거·복구 상태 갱신|Eradication and recovery status update|submit
close_classify_incident|보안 사고 분류·종결|Security incident classification and closure|submit
post_incident_report|사후 사고 보고서|Post-incident report|submit
""")

SOCIAL_ROWS = _rows("""
case_queue|복지 사례 대기열|Social services case queue|sensitive
constituent_household_profile|주민·가구 프로필|Constituent and household profile|sensitive
eligibility_application_review|복지 자격 신청 검토|Benefit eligibility application review|sensitive
document_evidence|복지 증빙 문서|Social services document evidence|sensitive
care_plan_view|복지 돌봄 계획 보기|Social care plan view|sensitive
referral_intake|복지 의뢰 접수|Social services referral intake|submit
dynamic_needs_assessment|동적 욕구 평가|Dynamic needs assessment|submit
safeguarding_risk_assessment|보호·위험 평가|Safeguarding risk assessment|submit
home_visit_plan|가정 방문 계획|Home visit plan|submit
interaction_note|복지 상호작용 기록|Social services interaction note|submit
care_plan_create_update|복지 돌봄 계획 생성·갱신|Social care plan create or update|submit
goal_benefit_assignment|복지 목표·급여 배정|Goal and benefit assignment|submit
service_referral|복지 서비스 의뢰|Social service referral|submit
benefit_eligibility_decision|복지 급여 자격 결정|Benefit eligibility decision|submit
benefit_schedule_disbursement|급여 일정·지급|Benefit scheduling and disbursement|submit
multiagency_case_conference|다기관 사례 회의|Multi-agency case conference|submit
case_review|복지 사례 심사|Social services case review|submit
case_close_transfer|복지 사례 종결·이관|Social services case closure or transfer|submit
""")

ESTATE_ROWS = _rows("""
estate_case_queue|상속 재산 사건 대기열|Estate case queue|sensitive
decedent_will_executor_detail|피상속인·유언·집행자 상세|Decedent will and executor detail|sensitive
beneficiary_heir_directory|수익자·상속인 명부|Beneficiary and heir directory|sensitive
asset_inventory|상속 재산 목록|Estate asset inventory|sensitive
liability_debt_inventory|상속 채무 목록|Estate liability and debt inventory|sensitive
inheritance_tax_status|상속세 상태|Inheritance tax status|sensitive
grant_status|검인 허가 상태|Probate grant status|sensitive
estate_valuation|상속 재산 평가|Estate valuation|submit
probate_application_draft|검인 신청서 초안|Probate application draft|submit
supporting_document_bundle|검인 증빙 문서 묶음|Probate supporting document bundle|submit
statement_of_truth_sign|진실 진술 서명|Statement of truth signing|submit
probate_submit_pay|검인 제출·납부|Probate submission and payment|submit
caveat_stop_application|검인 경고·신청 중지|Probate caveat or stop application|submit
estate_accounting|상속 재산 회계|Estate accounting|submit
creditor_debt_payment|채권자 채무 지급|Creditor debt payment|submit
asset_sale_transfer|상속 자산 매각·이전|Estate asset sale or transfer|submit
beneficiary_distribution|수익자 재산 분배|Beneficiary distribution|submit
estate_close_final_return|상속 사건 종결·최종 신고|Estate closure and final return|submit
""")

MARITIME_ROWS = _rows("""
vessel_schedule|선박 일정|Vessel schedule|sensitive
berth_plan|선석 계획|Berth plan|sensitive
yard_map_slot|야드 지도·슬롯|Yard map and slot|sensitive
container_cargo_lookup|컨테이너·화물 조회|Container and cargo lookup|sensitive
dangerous_goods_manifest|위험물 적하목록|Dangerous goods manifest|sensitive
gate_appointment|항만 게이트 예약|Port gate appointment|sensitive
vessel_stow_plan|선박 적부 계획|Vessel stow plan|sensitive
gang_equipment_plan|작업조·장비 계획|Gang and equipment plan|sensitive
berth_assignment|선석 배정|Berth assignment|submit
yard_slot_assignment|야드 슬롯 배정|Yard slot assignment|submit
gate_in_out|항만 반입·반출|Port gate-in or gate-out|submit
container_inspection_hold|컨테이너 검사·보류|Container inspection and hold|submit
cargo_receipt_delivery|화물 수령·인도|Cargo receipt and delivery|submit
container_stuff_strip|컨테이너 적입·적출|Container stuffing and stripping|submit
load_discharge_move|선적·양하 이동|Load and discharge move|submit
reefer_temperature_exception|냉동 컨테이너 온도 예외|Reefer temperature exception|submit
dangerous_goods_segregation_release|위험물 격리·해제|Dangerous goods segregation and release|submit
rail_handover|철도 인계|Rail handover|submit
equipment_dispatch|항만 장비 배차|Port equipment dispatch|submit
operation_close_report|항만 작업 종결 보고|Port operation closure report|submit
""")

TRIAL_ROWS = _rows("""
study_site_mode|임상시험 연구·기관 모드|Clinical study and site mode|sensitive
subject_list_profile|시험대상자 목록·프로필|Clinical trial subject list and profile|sensitive
informed_consent_status|시험대상자 동의 상태|Informed consent status|sensitive
visit_schedule|임상시험 방문 일정|Clinical trial visit schedule|sensitive
kit_site_inventory|시험약 키트·기관 재고|Clinical kit and site inventory|sensitive
subject_add_screen|시험대상자 등록·선별|Subject addition and screening|submit
screen_fail_rescreen|선별 실패·재선별|Screen failure or rescreening|submit
eligibility_randomization|적격성·무작위 배정|Eligibility and randomization|submit
visit_form_data|임상 방문 양식 데이터|Clinical visit form data|submit
visit_skip_unscheduled|방문 건너뛰기·비정규 방문|Visit skip or unscheduled visit|submit
adverse_event_record|이상반응 기록|Adverse event record|submit
concomitant_medication_record|병용약물 기록|Concomitant medication record|submit
data_query_answer|임상 데이터 질의 답변|Clinical data query response|submit
source_data_sign|임상 원자료 서명|Clinical source data signing|submit
shipment_receive|시험약 배송 수령|Clinical kit shipment receipt|submit
kit_dispense|시험약 키트 불출|Clinical kit dispensing|submit
dose_titration_hold|용량 조절·보류|Dose titration or hold|submit
kit_reconcile_return_destroy|시험약 키트 대조·반납·폐기|Kit reconciliation return or destruction|submit
subject_withdraw_complete|시험대상자 중도탈락·완료|Subject withdrawal or completion|submit
study_report_export|임상시험 보고서 내보내기|Clinical study report export|submit
""")

EMERGENCY_ROWS = _rows("""
incident_map|재난 사고 지도|Emergency incident map|sensitive
incident_briefing_iap|사고 브리핑·행동계획|Incident briefing and action plan|sensitive
personnel_resource_status|대원·자원 상태|Personnel and resource status|sensitive
hazard_hot_zone|위험·통제 구역|Hazard and hot zone|sensitive
assignment_list|재난 임무 목록|Emergency assignment list|sensitive
offline_map_download|오프라인 재난 지도 다운로드|Offline emergency map download|submit
responder_checkin|대응요원 체크인|Responder check-in|submit
assignment_accept|재난 임무 수락|Emergency assignment acceptance|submit
situation_observation_submit|상황 관찰 제출|Situation observation submission|submit
damage_needs_assessment|피해·수요 평가|Damage and needs assessment|submit
resource_request|재난 자원 요청|Emergency resource request|submit
resource_dispatch|재난 자원 배차|Emergency resource dispatch|submit
evacuation_shelter_status|대피·보호소 상태|Evacuation and shelter status|submit
patient_triage_record|환자 분류 기록|Patient triage record|submit
safety_message_ack|안전 메시지 확인|Safety message acknowledgement|submit
incident_log_update|재난 사고 일지 갱신|Emergency incident log update|submit
personnel_accountability_update|대원 책임·위치 갱신|Personnel accountability update|submit
resource_demobilize|재난 자원 철수|Emergency resource demobilization|submit
offline_sync|재난 오프라인 동기화|Emergency offline synchronization|submit
incident_close_handoff|재난 사고 종결·인계|Emergency incident closure and handoff|submit
""")


GROUPS: tuple[GroupSeed, ...] = (
    G(
        "clinical_care_team_ops", "임상 진료팀 운영", "Clinical care team operations", "clinical_care_team_operations",
        "임상의|담당 환자|진료 기록|처방 수명주기|검사 결과|환자 인계",
        "clinician|assigned patient|clinical record|order lifecycle|diagnostic result|patient handoff",
        "개인 건강 기록|약국 조제|임상시험 대상자", "personal health journal|pharmacy dispensing|clinical trial subject",
        "wellbeing.hub", "oracle_ehr_overview|oracle_ehr_orders|oracle_ehr_inbox|oracle_ehr_results",
        *_feature_rows(CLINICAL_ROWS, sources="oracle_ehr_overview|oracle_ehr_orders|oracle_ehr_inbox|oracle_ehr_results", negative="개인 증상 기록|약국 처방 조제|시험대상자 방문|personal symptom log|retail prescription fill|trial subject visit"),
    ),
    G(
        "pharmacy_dispensing_ops", "약국 조제 운영", "Pharmacy dispensing operations", "pharmacy_dispensing_operations",
        "약사|처방전|환자 투약 이력|조제 수명주기|의약품 재고|수령인",
        "pharmacist|prescription|patient medication history|dispense lifecycle|medication inventory|receiver",
        "임상 처방 입력|소매 상품 판매|시험약 키트", "clinical order entry|retail product sale|clinical trial kit",
        "clinical_care_team_ops.hub", "hl7_medication_dispense|oracle_medication_dispense_api|fda_rems_roles|fda_dscsa_pharmacists",
        *_feature_rows(PHARMACY_ROWS, sources="hl7_medication_dispense|oracle_medication_dispense_api|fda_rems_roles|fda_dscsa_pharmacists", negative="의사 처방 작성|일반 창고 출고|시험약 불출|prescriber order authoring|warehouse shipment|investigational kit dispense"),
    ),
    G(
        "insurance_claims_adjuster_ops", "보험 손해사정 운영", "Insurance claims adjusting operations", "insurance_claims_adjusting",
        "손해사정 담당자|보험 사고|보장 범위|손해 항목|준비금|보험금 지급",
        "claims adjuster|insurance claim|policy coverage|exposure|reserve|claim payment",
        "의료 보험 청구|개인 보험 가입|IT 사고", "medical billing claim|personal policy purchase|IT incident",
        "insurance.claim.hub", "guidewire_exposures|guidewire_reserves|guidewire_checks|guidewire_recoveries",
        *_feature_rows(CLAIMS_ROWS, sources="guidewire_exposures|guidewire_reserves|guidewire_checks|guidewire_recoveries", negative="병원 진료비 청구|보험 상품 비교|보안 사고 처리|hospital billing claim|insurance shopping|security incident response"),
    ),
    G(
        "airline_crew_operations", "항공 승무 운영", "Airline crew operations", "airline_crew_operations",
        "운항 승무원|근무표|비행 구간|항공기 배정|운항 브리핑|피로 위험",
        "operating crew|duty roster|flight sector|aircraft assignment|flight briefing|fatigue hazard",
        "승객 항공 예약|항공 화물 추적|정비 작업지시", "passenger flight booking|air cargo tracking|maintenance work order",
        "air_travel_planning.hub", "boeing_foreflight_dispatch|boeing_flight_manuals|icao_fatigue_management|sap_technical_debrief",
        *_feature_rows(AIRLINE_ROWS, sources="boeing_foreflight_dispatch|boeing_flight_manuals|icao_fatigue_management|sap_technical_debrief", negative="여행객 좌석 예약|공항 운송 조회|일반 설비 고장|traveler seat booking|airport shipment lookup|generic equipment failure"),
    ),
    G(
        "telecom_field_service_ops", "통신 현장 서비스 운영", "Telecom field service operations", "telecom_field_service_operations",
        "통신 현장 기사|망 자산|회선·포트|현장 작업지시|부품 재고|서비스 복구",
        "telecom field technician|network asset|circuit and port|field work order|parts inventory|service restoration",
        "고객 요금제 설정|IT 구성항목|건물 정비", "customer plan settings|IT configuration item|building maintenance",
        "maintenance_asset_ops.hub", "servicenow_telecom_fsm|microsoft_field_service_mobile|microsoft_field_service_architecture|servicenow_fsm_inventory",
        *_feature_rows(TELECOM_ROWS, sources="servicenow_telecom_fsm|microsoft_field_service_mobile|microsoft_field_service_architecture|servicenow_fsm_inventory", negative="개인 통신 요금제|서버 구성 관리|주택 수리 요청|personal telecom plan|server configuration management|home repair request"),
    ),
    G(
        "itsm_cmdb_operations", "IT 서비스·구성 운영", "IT service and CMDB operations", "itsm_cmdb_operations",
        "IT 서비스 담당자|사고 기록|문제·알려진 오류|변경 요청|구성항목|서비스 의존성",
        "IT service operator|incident record|problem and known error|change request|configuration item|service dependency",
        "보안 위협 대응|보험 사고|통신 현장 작업", "cyber threat response|insurance claim|telecom field work",
        "incident_oncall.hub", "servicenow_mobile_incidents|servicenow_cmdb_overview|servicenow_cmdb_relationships|servicenow_cmdb_data_manager",
        *_feature_rows(ITSM_ROWS, sources="servicenow_mobile_incidents|servicenow_cmdb_overview|servicenow_cmdb_relationships|servicenow_cmdb_data_manager", negative="보안 침해 격리|보험 손해 조사|통신망 현장 개통|security breach containment|insurance loss investigation|telecom field activation"),
    ),
    G(
        "cybersecurity_soc_ops", "사이버보안 관제 운영", "Cybersecurity SOC operations", "cybersecurity_soc_operations",
        "보안 분석가|경보·사고|위협 지표|조사 증거|격리 조치|대응 플레이북",
        "security analyst|alert and incident|threat indicator|investigation evidence|containment action|response playbook",
        "IT 일반 장애|보험 사기 조사|개인 보안 설정", "general IT outage|insurance fraud review|personal security settings",
        "android_safety.hub", "sentinel_investigate|sentinel_triage|defender_response_actions|servicenow_sir",
        *_feature_rows(SOC_ROWS, sources="sentinel_investigate|sentinel_triage|defender_response_actions|servicenow_sir", negative="일반 헬프데스크 사고|보험 청구 사기|계정 개인정보 설정|helpdesk incident|claim fraud case|account privacy setting"),
    ),
    G(
        "social_services_casework", "사회복지 사례 운영", "Social services casework", "social_services_casework",
        "사회복지사|주민·가구|복지 신청|욕구 평가|돌봄 계획|급여 지급",
        "caseworker|constituent household|benefit application|needs assessment|care plan|benefit disbursement",
        "보험 청구|가족 개인 돌봄|법률 사건", "insurance claim|personal family care|legal matter",
        "government_digital.hub", "salesforce_public_sector|salesforce_care_plans|govuk_youth_assessment|govuk_adult_social_care",
        *_feature_rows(SOCIAL_ROWS, sources="salesforce_public_sector|salesforce_care_plans|govuk_youth_assessment|govuk_adult_social_care", negative="보험금 신청|가족 일정 공유|법률 의뢰인 사건|insurance benefit claim|family schedule sharing|legal client matter"),
    ),
    G(
        "estate_probate_administration", "상속·검인 행정", "Estate and probate administration", "estate_probate_administration",
        "상속 재산 관리자|피상속인|유언 집행자|수익자·상속인|검인 신청|재산 분배",
        "estate administrator|decedent|executor|beneficiary and heir|probate application|estate distribution",
        "개인 자산관리|부동산 임대|일반 세금 신고", "personal wealth management|rental property|general tax filing",
        "legal_practice_ops.hub", "hmcts_probate|govuk_applying_probate|irs_estate_admin|irs_publication_559",
        *_feature_rows(ESTATE_ROWS, sources="hmcts_probate|govuk_applying_probate|irs_estate_admin|irs_publication_559", negative="개인 투자 자산|임대 주택 자산|일반 소득세 신고|personal investment asset|rental housing asset|ordinary income tax return"),
    ),
    G(
        "maritime_port_logistics", "해상·항만 물류 운영", "Maritime and port logistics", "maritime_port_logistics",
        "항만 운영자|선박 일정|선석·야드|컨테이너 화물|위험물|하역 장비",
        "port operator|vessel schedule|berth and yard|container cargo|dangerous goods|handling equipment",
        "소비자 택배|창고 주문이행|여객선 예약", "consumer parcel|warehouse fulfillment|passenger ferry booking",
        "shopping_logistics.hub", "mumbai_ipos|imo_cargo_securing|imo_imdg|imo_ems",
        *_feature_rows(MARITIME_ROWS, sources="mumbai_ipos|imo_cargo_securing|imo_imdg|imo_ems", negative="개인 배송 추적|일반 창고 피킹|여객 승선권|personal delivery tracking|generic warehouse picking|passenger boarding ticket"),
    ),
    G(
        "clinical_trial_site_ops", "임상시험 기관 운영", "Clinical trial site operations", "clinical_trial_site_operations",
        "임상시험 연구자|시험 기관|시험대상자|방문 일정|시험약 키트|데이터 질의",
        "clinical investigator|trial site|study subject|visit schedule|investigational kit|data query",
        "일반 환자 진료|약국 조제|연구실 실험", "routine patient care|retail pharmacy dispensing|laboratory experiment",
        "laboratory_research_ops.hub", "oracle_clinical_quick_start|oracle_clinical_modes|oracle_clinical_randomize_dispense|fda_clinical_investigators|fda_protocol_deviations",
        *_feature_rows(TRIAL_ROWS, sources="oracle_clinical_quick_start|oracle_clinical_modes|oracle_clinical_randomize_dispense|fda_clinical_investigators|fda_protocol_deviations", negative="일반 진료 환자|소매 약국 처방|비임상 연구 시료|routine care patient|retail pharmacy prescription|nonclinical research sample"),
    ),
    G(
        "emergency_response_operations", "재난·긴급 대응 운영", "Emergency response operations", "emergency_response_operations",
        "현장 지휘관|대응요원|사고 행동계획|재난 자원|위험 구역|대원 책임",
        "incident commander|responder|incident action plan|emergency resource|hazard zone|personnel accountability",
        "개인 긴급전화|보안 사고|병원 진료", "personal emergency call|cyber incident|hospital encounter",
        "safety.hub", "fema_ems_templates|fema_division_checklist|esri_field_maps_get_started|esri_field_maps_tasks|esri_field_maps_download",
        *_feature_rows(EMERGENCY_ROWS, sources="fema_ems_templates|fema_division_checklist|esri_field_maps_get_started|esri_field_maps_tasks|esri_field_maps_download", negative="개인 긴급 연락처|사이버 보안 사고|정규 진료 환자|personal emergency contact|cybersecurity incident|routine clinical patient"),
    ),
)


def _retag_function(payload: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(payload)
    result["legacy_tags"] = [
        "v11_professional_operations" if value == "v10_reviewed_operations" else value
        for value in result.get("legacy_tags", [])
    ]
    return result


def _build_root(group: GroupSeed) -> dict[str, object]:
    return _retag_function(_v10_build_root(group))


def _build_feature(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = _retag_function(_v10_build_feature(group, seed))
    result["automation_policy"] = "never_auto"
    result["stop_policy"] = "before_action"
    risk_cues = copy.deepcopy(result["risk_cues"])
    risk_cues["user_boundary"] = [
        "최종 목적지 버튼은 사용자가 직접 누름",
        "the user must press the final destination button",
    ]
    result["risk_cues"] = risk_cues
    return result


def _build_intent(group: GroupSeed, seed: FeatureSeed) -> dict[str, object]:
    result = copy.deepcopy(_v10_build_intent(group, seed))
    result["intent_id"] = str(result["intent_id"]).replace("v10_", "v11_", 1)
    for rule in result["goal_rules"]:
        rule["rule_kind"] = str(rule["rule_kind"]).replace("v10_", "v11_", 1)
        for key in tuple(rule):
            if key.startswith("v10_"):
                rule[f"v11_{key[4:]}"] = rule.pop(key)
    return result


V11_FUNCTIONS: tuple[dict[str, object], ...] = tuple(
    item
    for group in GROUPS
    for item in (_build_root(group), *(_build_feature(group, feature) for feature in group.features))
)
V11_INTENTS: tuple[dict[str, object], ...] = tuple(
    _build_intent(group, feature) for group in GROUPS for feature in group.features
)
REQUIRED_DOMAINS = frozenset(group.domain for group in GROUPS)
EXPECTED_DOMAIN_COUNTS = {
    "airline_crew_operations": 18,
    "clinical_care_team_ops": 20,
    "clinical_trial_site_ops": 20,
    "cybersecurity_soc_ops": 20,
    "emergency_response_operations": 20,
    "estate_probate_administration": 18,
    "insurance_claims_adjuster_ops": 20,
    "itsm_cmdb_operations": 20,
    "maritime_port_logistics": 20,
    "pharmacy_dispensing_ops": 18,
    "social_services_casework": 18,
    "telecom_field_service_ops": 18,
}


# Sixteen collision families, ten bilingual probes each.  These deliberately
# place homonymous operational words beside a fully qualified target phrase.
COLLISION_FAMILIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("처방·주문", "order", ("clinical_care_team_ops.order_entry", "pharmacy_dispensing_ops.prescription_detail", "telecom_field_service_ops.assigned_work_order", "itsm_cmdb_operations.change_request_review")),
    ("조제·불출", "dispense", ("pharmacy_dispensing_ops.handover_complete", "clinical_trial_site_ops.kit_dispense", "social_services_casework.benefit_schedule_disbursement")),
    ("환자·대상자", "patient or subject", ("clinical_care_team_ops.patient_chart_summary", "pharmacy_dispensing_ops.patient_medication_profile", "clinical_trial_site_ops.subject_list_profile", "emergency_response_operations.patient_triage_record")),
    ("사례·사건", "case", ("social_services_casework.case_queue", "estate_probate_administration.estate_case_queue", "insurance_claims_adjuster_ops.claim_queue", "cybersecurity_soc_ops.incident_detail")),
    ("사고", "incident", ("insurance_claims_adjuster_ops.incident_exposure_review", "itsm_cmdb_operations.incident_detail", "cybersecurity_soc_ops.incident_detail", "emergency_response_operations.incident_map")),
    ("준비금·예비", "reserve", ("insurance_claims_adjuster_ops.reserve_set", "airline_crew_operations.roster", "telecom_field_service_ops.parts_stock_request")),
    ("노출·위험", "exposure", ("insurance_claims_adjuster_ops.exposure_create", "cybersecurity_soc_ops.entity_investigation_graph", "social_services_casework.safeguarding_risk_assessment")),
    ("종결", "close", ("clinical_care_team_ops.encounter_close", "insurance_claims_adjuster_ops.close_reopen_claim", "itsm_cmdb_operations.incident_resolve", "estate_probate_administration.estate_close_final_return", "emergency_response_operations.incident_close_handoff")),
    ("해제·복구", "release", ("cybersecurity_soc_ops.eradication_recovery_status", "maritime_port_logistics.dangerous_goods_segregation_release", "telecom_field_service_ops.customer_service_restore_ack")),
    ("배정", "assignment", ("insurance_claims_adjuster_ops.assign_reassign_claim", "airline_crew_operations.aircraft_assignment", "itsm_cmdb_operations.assign_reassign", "cybersecurity_soc_ops.assign_owner", "emergency_response_operations.assignment_accept")),
    ("보류", "hold", ("pharmacy_dispensing_ops.dispense_hold_resume", "clinical_trial_site_ops.dose_titration_hold", "maritime_port_logistics.container_inspection_hold", "cybersecurity_soc_ops.isolate_device")),
    ("서명·확인", "sign or acknowledge", ("clinical_care_team_ops.clinical_note_sign", "clinical_trial_site_ops.source_data_sign", "estate_probate_administration.statement_of_truth_sign", "emergency_response_operations.safety_message_ack")),
    ("보고", "report", ("airline_crew_operations.flight_report_submit", "clinical_trial_site_ops.adverse_event_record", "cybersecurity_soc_ops.post_incident_report", "emergency_response_operations.situation_observation_submit")),
    ("자산", "asset", ("telecom_field_service_ops.network_asset_detail", "itsm_cmdb_operations.ci_search_detail", "estate_probate_administration.asset_inventory", "insurance_claims_adjuster_ops.incident_exposure_review")),
    ("재고", "inventory", ("pharmacy_dispensing_ops.product_lot_serial_scan", "telecom_field_service_ops.parts_consume_return", "maritime_port_logistics.yard_map_slot", "clinical_trial_site_ops.kit_site_inventory")),
    ("분류·우선순위", "triage", ("cybersecurity_soc_ops.alert_incident_queue", "social_services_casework.safeguarding_risk_assessment", "emergency_response_operations.patient_triage_record", "clinical_care_team_ops.patient_list")),
)


def build_collision_probes() -> tuple[dict[str, str], ...]:
    """Return 160 deterministic, bilingual, source-derived collision probes."""

    intents = {str(item["terminal_function"]): item for item in V11_INTENTS}
    functions = {str(item["function_id"]): item for item in V11_FUNCTIONS}
    probes: list[dict[str, str]] = []
    for family_index, (token_ko, token_en, targets) in enumerate(COLLISION_FAMILIES):
        for probe_index in range(10):
            locale = "ko-KR" if probe_index < 5 else "en-US"
            target = targets[probe_index % len(targets)]
            intent = intents[target]
            function = functions[target]
            pattern = intent["patterns_by_locale"][locale][probe_index % 5]
            context_values = function["positive_context"]
            context = context_values[probe_index % len(context_values)]
            token = token_ko if locale == "ko-KR" else token_en
            probes.append({
                "probe_id": f"collision_{family_index:02d}_{probe_index:02d}",
                "family": token_en,
                "locale": locale,
                "text": f"{token} 구분 {pattern} {context}" if locale == "ko-KR" else f"disambiguate {token}: {pattern} {context}",
                "expected_function": target,
            })
    return tuple(probes)


def build_semantic_development_matrix() -> tuple[dict[str, object], ...]:
    """Return five source-derived smoke probes per terminal (1,150 total)."""

    functions = {str(item["function_id"]): item for item in V11_FUNCTIONS}
    probes: list[dict[str, object]] = []
    for intent in V11_INTENTS:
        target = str(intent["terminal_function"])
        function = functions[target]
        for locale in ("ko-KR", "en-US"):
            probes.append({
                "kind": "positive",
                "locale": locale,
                "text": intent["patterns_by_locale"][locale][0],
                "expected_function": target,
            })
        for index, kind in enumerate(("role_inversion", "asset_homonym", "lifecycle_contrast")):
            probes.append({
                "kind": kind,
                "locale": "ko-KR" if index != 1 else "en-US",
                "text": function["negative_context"][index],
                "expected_function": None,
                "excluded_function": target,
            })
    return tuple(probes)


class V11CatalogValidationError(ValueError):
    """Raised when v11 cannot be merged without semantic or safety drift."""


def _duplicates(values: Iterable[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def _pre_v11_payload(payload: Mapping[str, object]) -> dict[str, object]:
    function_ids = {str(item["function_id"]) for item in V11_FUNCTIONS}
    intent_ids = {str(item["intent_id"]) for item in V11_INTENTS}
    result = copy.deepcopy(dict(payload))
    result["functions"] = [item for item in result.get("functions", []) if str(item["function_id"]) not in function_ids]
    result["intents"] = [item for item in result.get("intents", []) if str(item["intent_id"]) not in intent_ids]
    result.pop("official_sources_v11", None)
    result["catalog_version"] = CATALOG_V10_VERSION
    result["description"] = CATALOG_V10_DESCRIPTION
    return result


def _ensure_v10(payload: Mapping[str, object]) -> dict[str, object]:
    return merge_v10_with_base(_pre_v10_payload(_pre_v11_payload(payload)))


def load_base_catalog(path: Path = DEFAULT_BASE_CATALOG) -> dict[str, object]:
    """Load a clean v10 base whether canonical storage is older or materialized."""

    return _ensure_v10(json.loads(path.read_text(encoding="utf-8")))


def _materialization_state(payload: Mapping[str, object]) -> bool:
    expected_functions = {str(item["function_id"]): item for item in V11_FUNCTIONS}
    expected_intents = {str(item["intent_id"]): item for item in V11_INTENTS}
    present_functions = {
        str(item["function_id"]): item for item in payload.get("functions", [])
        if str(item["function_id"]) in expected_functions
    }
    present_intents = {
        str(item["intent_id"]): item for item in payload.get("intents", [])
        if str(item["intent_id"]) in expected_intents
    }
    if not present_functions and not present_intents and "official_sources_v11" not in payload:
        return False
    if set(present_functions) != set(expected_functions) or set(present_intents) != set(expected_intents):
        raise V11CatalogValidationError("partial v11 ID collision; refusing mixed materialization")
    if present_functions != expected_functions or present_intents != expected_intents:
        raise V11CatalogValidationError("v11 collides with a different function or intent definition")
    if payload.get("official_sources_v11") != OFFICIAL_SOURCES:
        raise V11CatalogValidationError("v11 official evidence registry differs")
    if payload.get("catalog_version") != CATALOG_V11_VERSION or payload.get("description") != CATALOG_V11_DESCRIPTION:
        raise V11CatalogValidationError("v11 materialization metadata differs")
    return True


def _contains_forbidden_key(value: object, forbidden: set[str]) -> bool:
    if isinstance(value, Mapping):
        if forbidden.intersection(str(key).casefold() for key in value):
            return True
        return any(_contains_forbidden_key(item, forbidden) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item, forbidden) for item in value)
    return False


def validate_v11_data(base_payload: Mapping[str, object] | None = None) -> dict[str, object]:
    """Validate exact scope, evidence, semantic richness, and fail-closed safety."""

    errors: list[str] = []
    function_ids = [str(item["function_id"]) for item in V11_FUNCTIONS]
    intent_ids = [str(item["intent_id"]) for item in V11_INTENTS]
    terminal_ids = {str(item["function_id"]) for item in V11_FUNCTIONS if bool(item["terminal"])}
    if duplicates := _duplicates(function_ids):
        errors.append(f"duplicate v11 function IDs: {sorted(duplicates)}")
    if duplicates := _duplicates(intent_ids):
        errors.append(f"duplicate v11 intent IDs: {sorted(duplicates)}")
    domain_counts = Counter(str(item["domain"]) for item in V11_FUNCTIONS if bool(item["terminal"]))
    if dict(sorted(domain_counts.items())) != EXPECTED_DOMAIN_COUNTS:
        errors.append(f"v11 domain terminal counts differ: {dict(sorted(domain_counts.items()))}")
    if len(REQUIRED_DOMAINS) != 12 or len(V11_FUNCTIONS) != 242 or len(terminal_ids) != 230 or len(V11_INTENTS) != 230:
        errors.append("v11 requires exactly 12 domains, 12 hubs, 230 terminals, and 230 intents")

    sensitive_count = sum(bool(item["terminal"]) and not bool(item["state_changing"]) for item in V11_FUNCTIONS)
    consequential_count = sum(bool(item["state_changing"]) for item in V11_FUNCTIONS)
    if sensitive_count != 74 or consequential_count != 156:
        errors.append(f"v11 requires S=74 and C=156; got S={sensitive_count}, C={consequential_count}")

    urls: set[str] = set()
    for source_id, source in OFFICIAL_SOURCES.items():
        parsed = urlparse(str(source.get("url", "")))
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"source {source_id} is not an absolute HTTPS URL")
        if str(source.get("url")) in urls:
            errors.append(f"source {source_id} duplicates an official URL")
        urls.add(str(source.get("url")))
        if not str(source.get("publisher", "")).strip() or not str(source.get("title", "")).strip():
            errors.append(f"source {source_id} lacks publisher or title")
        if source.get("evidence_level") != "official_primary" or source.get("collected_on") != COLLECTED_ON:
            errors.append(f"source {source_id} lacks official-primary collection metadata")
        if source.get("verified_status") != 200 or not str(source.get("verification_method", "")).strip():
            errors.append(f"source {source_id} lacks verification metadata")
    if len(OFFICIAL_SOURCES) != 50 or len(urls) != 50:
        errors.append("v11 requires exactly fifty unique official-primary sources")

    known_sources = set(OFFICIAL_SOURCES)
    used_sources: set[str] = set()
    forbidden_keys = {
        "x", "y", "bounds", "coordinate", "coordinates", "package", "package_name",
        "resource_id", "screenshot_hash", "screen_path", "recorded_path", "fixed_ui_path",
    }
    for function in V11_FUNCTIONS:
        function_id = str(function["function_id"])
        aliases = function["aliases"]
        if len(aliases["ko-KR"]) < 8 or len(aliases["en-US"]) < 8:
            errors.append(f"{function_id}: insufficient bilingual aliases")
        if len(function["positive_context"]) < 6 or len(function["negative_context"]) < 6:
            errors.append(f"{function_id}: insufficient positive or negative context")
        if len(function["role_hints"]) < 5 or not function["state_cues"] or not function["risk_cues"]:
            errors.append(f"{function_id}: incomplete role, state, or risk semantics")
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
            boundary = " ".join(function["risk_cues"].get("user_boundary", []))
            if "사용자" not in boundary or "user" not in boundary.casefold() or "press" not in boundary.casefold():
                errors.append(f"{function_id}: explicit user-owned final press is missing")
        elif function["automation_policy"] != "safe_navigation" or function["stop_policy"] != "continue":
            errors.append(f"{function_id}: hub must remain navigation-only")
    if used_sources != known_sources:
        errors.append(f"orphan official sources: {sorted(known_sources - used_sources)}")

    terminal_by_id = {str(item["function_id"]): item for item in V11_FUNCTIONS}
    intent_terminals = [str(item["terminal_function"]) for item in V11_INTENTS]
    if set(intent_terminals) != terminal_ids or len(intent_terminals) != len(terminal_ids):
        errors.append("v11 requires exactly one intent per terminal function")
    for intent in V11_INTENTS:
        intent_id = str(intent["intent_id"])
        localized = intent["patterns_by_locale"]
        if len(localized["ko-KR"]) < 10 or len(localized["en-US"]) < 10:
            errors.append(f"{intent_id}: insufficient bilingual patterns")
        if len(intent["goal_rules"]) < 24:
            errors.append(f"{intent_id}: insufficient compositional rules")
        if len(intent["route"]) != 2 or intent["route"][-1]["function_id"] != intent["terminal_function"]:
            errors.append(f"{intent_id}: invalid hub-to-destination route")
        if not intent["avoid_functions"] or intent["desired_state"] != "user_confirmation_required":
            errors.append(f"{intent_id}: missing contrast or user confirmation")
        if intent["terminal_condition"]["stop_policy"] != "stop_before_action":
            errors.append(f"{intent_id}: route must stop before action")
        if terminal_by_id[str(intent["terminal_function"])]["automation_policy"] != "never_auto":
            errors.append(f"{intent_id}: terminal is not fail-closed")
        for rule in intent["goal_rules"]:
            if len(rule.get("all_of", [])) < 2 or not str(rule.get("rule_kind", "")).startswith("v11_"):
                errors.append(f"{intent_id}: malformed semantic rule")
            for key in ("v11_discriminative_keys", "v11_negative_context_keys", "v11_positive_context_keys"):
                values = list(rule.get(key, []))
                if values != sorted(dict.fromkeys(values)):
                    errors.append(f"{intent_id}: nondeterministic {key}")

    semantic_matrix = build_semantic_development_matrix()
    collision_probes = build_collision_probes()
    if len(semantic_matrix) != 1150 or sum(item["kind"] == "positive" for item in semantic_matrix) != 460:
        errors.append("v11 semantic development matrix must contain 1,150 probes with 460 positives")
    if len(collision_probes) != 160 or len({item["probe_id"] for item in collision_probes}) != 160:
        errors.append("v11 collision suite must contain 160 unique probes")
    if any(item["expected_function"] not in terminal_ids for item in collision_probes):
        errors.append("v11 collision suite references an unknown terminal")

    materialized = False
    if base_payload is not None:
        materialized = _materialization_state(base_payload)
        pre_v11 = _ensure_v10(base_payload)
        base_function_ids = {str(item["function_id"]) for item in pre_v11.get("functions", [])}
        base_intent_ids = {str(item["intent_id"]) for item in pre_v11.get("intents", [])}
        if collisions := sorted(set(function_ids).intersection(base_function_ids)):
            errors.append(f"v11 function IDs collide with v1-v10: {collisions[:12]}")
        if collisions := sorted(set(intent_ids).intersection(base_intent_ids)):
            errors.append(f"v11 intent IDs collide with v1-v10: {collisions[:12]}")

        pattern_owners: dict[str, set[str]] = {}
        for intent in [*pre_v11.get("intents", []), *V11_INTENTS]:
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
            for intent in pre_v11.get("intents", [])
            for rule in intent.get("goal_rules", [])
            if _rule_signature(rule)
        }
        v11_rule_owners: dict[tuple[str, ...], set[str]] = {}
        for intent in V11_INTENTS:
            for rule in intent["goal_rules"]:
                signature = _rule_signature(rule)
                if signature in base_rule_signatures:
                    errors.append(f"{intent['intent_id']}: goal rule collides with v1-v10")
                v11_rule_owners.setdefault(signature, set()).add(str(intent["intent_id"]))
        shared_rules = {signature: owners for signature, owners in v11_rule_owners.items() if len(owners) > 1}
        if shared_rules:
            errors.append(f"v11 goal-rule collisions: {list(shared_rules.items())[:8]}")

    semantic_payload = copy.deepcopy({"functions": V11_FUNCTIONS, "intents": V11_INTENTS})
    for function in semantic_payload["functions"]:
        function.pop("source_refs", None)
    semantic_text = json.dumps(semantic_payload, ensure_ascii=False).casefold()
    forbidden_fragments = (
        "com.", "package name", "resource-id", "screen coordinate", "recorded path",
        "oracle", "hl7", "fda", "guidewire", "boeing", "icao", "servicenow",
        "microsoft", "salesforce", "hmcts", "esri", "arcgis",
    )
    if any(re.search(rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])", semantic_text) for value in forbidden_fragments):
        errors.append("v11 runtime semantics contain a source identity or recorded UI path")

    if errors:
        raise V11CatalogValidationError("; ".join(errors))
    return {
        "functions": len(V11_FUNCTIONS),
        "terminal_functions": len(terminal_ids),
        "intents": len(V11_INTENTS),
        "domains": len(REQUIRED_DOMAINS),
        "domain_terminal_counts": dict(sorted(domain_counts.items())),
        "official_sources": len(OFFICIAL_SOURCES),
        "aliases": sum(len(values) for item in V11_FUNCTIONS for values in item["aliases"].values()),
        "goal_patterns": sum(len(item["patterns"]) for item in V11_INTENTS),
        "goal_rules": sum(len(item["goal_rules"]) for item in V11_INTENTS),
        "sensitive_reads": sensitive_count,
        "state_changing": consequential_count,
        "semantic_smoke_probes": len(semantic_matrix),
        "collision_probes": len(collision_probes),
        "materialized": materialized,
    }


def merge_with_base(base_payload: Mapping[str, object]) -> dict[str, object]:
    """Return a deterministic, idempotent, fail-closed v10+v11 catalog copy."""

    validate_v11_data(base_payload)
    if _materialization_state(base_payload):
        return copy.deepcopy(dict(base_payload))
    merged = _ensure_v10(base_payload)
    merged["catalog_version"] = CATALOG_V11_VERSION
    merged["description"] = CATALOG_V11_DESCRIPTION
    merged["functions"] = [*merged.get("functions", []), *copy.deepcopy(V11_FUNCTIONS)]
    merged["intents"] = [*merged.get("intents", []), *copy.deepcopy(V11_INTENTS)]
    merged["official_sources_v11"] = copy.deepcopy(OFFICIAL_SOURCES)
    return merged


def main() -> int:
    print(json.dumps(validate_v11_data(load_base_catalog()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
