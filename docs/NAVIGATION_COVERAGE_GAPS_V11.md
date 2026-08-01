# Navigation ontology coverage gap audit — v11

감사 기준일: 2026-07-30
감사 기준선: v10 반영 예상 canonical **119개 도메인, 1,616개 기능, 1,470개 intent**
감사 범위: 공개된 독립 평가 fixture의 문장·정답·실패 결과를 열람하지 않고, 현재 catalog/source와 공식 1차 문서만 대조한 source-level 설계 감사

## 결론

v11에서는 아래 12개 전문 운영 도메인을 권장한다. 정확한 제안 규모는 **242개 기능(허브 12 + terminal 230), 230개 intent**이며, 반영 후 예상 누계는 **131개 도메인, 1,858개 기능, 1,700개 intent**다.

| 우선순위 | 도메인 ID | terminal | 허브 포함 기능 | intent | S | C |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `clinical_care_team_ops` | 20 | 21 | 20 | 5 | 15 |
| 2 | `pharmacy_dispensing_ops` | 18 | 19 | 18 | 3 | 15 |
| 3 | `insurance_claims_adjuster_ops` | 20 | 21 | 20 | 6 | 14 |
| 4 | `airline_crew_operations` | 18 | 19 | 18 | 9 | 9 |
| 5 | `telecom_field_service_ops` | 18 | 19 | 18 | 5 | 13 |
| 6 | `itsm_cmdb_operations` | 20 | 21 | 20 | 9 | 11 |
| 7 | `cybersecurity_soc_ops` | 20 | 21 | 20 | 7 | 13 |
| 8 | `social_services_casework` | 18 | 19 | 18 | 5 | 13 |
| 9 | `estate_probate_administration` | 18 | 19 | 18 | 7 | 11 |
| 10 | `maritime_port_logistics` | 20 | 21 | 20 | 8 | 12 |
| 11 | `clinical_trial_site_ops` | 20 | 21 | 20 | 5 | 15 |
| 12 | `emergency_response_operations` | 20 | 21 | 20 | 5 | 15 |
| **합계** | **12개** | **230** | **242** | **230** | **74** | **156** |

`S`는 민감하거나 권한이 제한된 조회 목적지, `C`는 임상·금전·법률·안전·운영 상태를 바꾸는 결과적 목적지다. 230개 terminal 모두 `automation_policy=never_auto`, `stop_policy=before_action`으로 고정하고 마지막 누름은 사용자에게 남긴다. `C`는 항상 high risk이며, `S`도 민감정보 또는 전문 직무정보를 노출하므로 low-risk로 강등하지 않는다.

## 공통 ID·경로 계약

- 허브 ID: `<domain>.hub`
- terminal ID: `<domain>.<terminal_key>`
- intent ID: `v11_<domain>_<terminal_key>`
- 경로는 앱 이름·package·resource ID·좌표·고정 클릭 순서를 저장하지 않고, 아래의 한/영 **개념 경로**를 저장한다.
- terminal 탐색은 `role + governed asset + lifecycle state` 중 최소 두 축이 확인되어야 한다. 환자·약·보험금·항공 안전·통신망·CI·보안 엔터티·복지 대상자·상속재산·위험화물·시험대상자·재난 자원은 한 축만으로 확정하지 않는다.
- `disabled`, `unavailable`, `permission denied`, `wrong role`, `stale/offline`, `approval required`, `safety hold`, `clinical hold`, `legal hold`가 보이면 유사 버튼으로 우회하지 않고 fail-closed한다.

## 1. Clinical care team operations (`clinical_care_team_ops`)

허브: `clinical_care_team_ops.hub` — 진료팀 업무 / Clinical care team work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `clinical_care_team_ops.patient_list` | `v11_clinical_care_team_ops_patient_list` | S | 환자 목록 → 담당·진료일 필터 / Patient list → assignment/date filter |
| `clinical_care_team_ops.patient_chart_summary` | `v11_clinical_care_team_ops_patient_chart_summary` | S | 환자 → 차트 요약·타임라인 / Patient → chart summary/timeline |
| `clinical_care_team_ops.allergy_review` | `v11_clinical_care_team_ops_allergy_review` | S | 환자 차트 → 알레르기·이상반응 / Chart → allergies/adverse reactions |
| `clinical_care_team_ops.problem_list_review` | `v11_clinical_care_team_ops_problem_list_review` | S | 환자 차트 → 문제 목록 / Chart → problem list |
| `clinical_care_team_ops.medication_reconciliation` | `v11_clinical_care_team_ops_medication_reconciliation` | C | 약물 및 처방 → 약물 조정·서명 / Medications and orders → reconcile/sign |
| `clinical_care_team_ops.vital_sign_record` | `v11_clinical_care_team_ops_vital_sign_record` | C | 환자 차트 → 활력징후 기록 / Chart → record vitals |
| `clinical_care_team_ops.clinical_note_draft` | `v11_clinical_care_team_ops_clinical_note_draft` | C | 방문·차트 → 임상 노트 초안 / Encounter/chart → draft clinical note |
| `clinical_care_team_ops.clinical_note_sign` | `v11_clinical_care_team_ops_clinical_note_sign` | C | 노트 → 검토 → 서명 / Note → review → sign |
| `clinical_care_team_ops.order_entry` | `v11_clinical_care_team_ops_order_entry` | C | 환자 → 약물 및 처방 → 처방 입력 / Patient → medications and orders → place order |
| `clinical_care_team_ops.order_modify_stop` | `v11_clinical_care_team_ops_order_modify_stop` | C | 활성 처방 → 수정·중지·취소 / Active order → modify/stop/cancel |
| `clinical_care_team_ops.specimen_collection_record` | `v11_clinical_care_team_ops_specimen_collection_record` | C | 검체 수집 목록 → 환자·검체 확인 → 수집 기록 / Collections → verify patient/specimen → record |
| `clinical_care_team_ops.medication_administration` | `v11_clinical_care_team_ops_medication_administration` | C | 투약 목록 → 환자·약·용량 확인 → 투약 기록 / MAR → verify patient/drug/dose → record |
| `clinical_care_team_ops.result_review` | `v11_clinical_care_team_ops_result_review` | S | 결과 → 검사·진단 보고서 / Results → laboratory/diagnostic report |
| `clinical_care_team_ops.result_endorse` | `v11_clinical_care_team_ops_result_endorse` | C | 받은편지함·결과 → 검토 → 승인 / Inbox/results → review → endorse |
| `clinical_care_team_ops.referral_create` | `v11_clinical_care_team_ops_referral_create` | C | 환자 차트 → 의뢰 → 신규 의뢰 / Chart → referrals → create referral |
| `clinical_care_team_ops.care_team_message` | `v11_clinical_care_team_ops_care_team_message` | C | 환자 대화 → 진료팀 메시지 / Patient conversation → care-team message |
| `clinical_care_team_ops.handoff_update` | `v11_clinical_care_team_ops_handoff_update` | C | 환자 목록 → 인계 → 상태 업데이트 / Patient list → handoff → update status |
| `clinical_care_team_ops.discharge_instruction` | `v11_clinical_care_team_ops_discharge_instruction` | C | 방문 → 퇴원·방문후 지침 → 발행 / Encounter → discharge/post-visit instructions → issue |
| `clinical_care_team_ops.care_plan_update` | `v11_clinical_care_team_ops_care_plan_update` | C | 환자 차트 → 진료계획 → 목표·활동 수정 / Chart → care plan → update goals/actions |
| `clinical_care_team_ops.encounter_close` | `v11_clinical_care_team_ops_encounter_close` | C | 방문 → 필수기록 검토 → 종료 / Encounter → completeness review → close |

공식 근거:

- Oracle Health, [Oracle Health EHR](https://docs.oracle.com/en/industries/health/oracle-health-ehr/) — charting, medication administration, orders, results, referrals, schedules, specimen collections, vitals와 역할별 업무.
- Oracle Health, [Orders](https://docs.oracle.com/en/industries/health/oracle-health-ehr/ehrug/orders.html) — order review/place/modify/stop/cancel, medication reconciliation lifecycle.
- Oracle Health, [Inbox](https://docs.oracle.com/en/industries/health/oracle-health-ehr/ehrfg/inbox.html) — result endorsement, messages, follow-up, team assignment.
- Oracle Health, [Results](https://docs.oracle.com/en/industries/health/oracle-health-ehr/ehrug/results.html) — laboratory results와 diagnostic reports.

중복 제외: 기존 `healthcare_provider`는 환자·보호자 포털의 조회·요청 목적이다. v11은 provider 역할의 chart write, order, administration, endorsement, handoff, encounter lifecycle만 소유한다. `family_caregiving`의 가정 돌봄 기록과도 합치지 않는다.

## 2. Pharmacy dispensing operations (`pharmacy_dispensing_ops`)

허브: `pharmacy_dispensing_ops.hub` — 약국 조제 업무 / Pharmacy dispensing work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `pharmacy_dispensing_ops.prescription_queue` | `v11_pharmacy_dispensing_ops_prescription_queue` | S | 처방 작업함 → 신규·보류·진행중 / Prescription queue → new/on-hold/in-progress |
| `pharmacy_dispensing_ops.prescription_detail` | `v11_pharmacy_dispensing_ops_prescription_detail` | S | 처방 → 약·용량·수량·처방자 / Prescription → drug/dose/quantity/prescriber |
| `pharmacy_dispensing_ops.patient_medication_profile` | `v11_pharmacy_dispensing_ops_patient_medication_profile` | S | 환자 → 약력·알레르기·중복 / Patient → medication history/allergy/duplication |
| `pharmacy_dispensing_ops.clinical_safety_review` | `v11_pharmacy_dispensing_ops_clinical_safety_review` | C | 처방 → 상호작용·금기·용량 검토 / Prescription → interaction/contraindication/dose review |
| `pharmacy_dispensing_ops.insurance_claim_adjudication` | `v11_pharmacy_dispensing_ops_insurance_claim_adjudication` | C | 처방 → 보험 청구 → 승인·거절 결과 / Prescription → benefit claim → adjudication result |
| `pharmacy_dispensing_ops.prescriber_clarification` | `v11_pharmacy_dispensing_ops_prescriber_clarification` | C | 처방 문제 → 처방자 문의·응답 기록 / Prescription issue → prescriber clarification/log |
| `pharmacy_dispensing_ops.substitution_decision` | `v11_pharmacy_dispensing_ops_substitution_decision` | C | 조제 → 대체약·사유·책임자 / Dispense → substitution/reason/responsible party |
| `pharmacy_dispensing_ops.fill_quantity_days_supply` | `v11_pharmacy_dispensing_ops_fill_quantity_days_supply` | C | 조제 상세 → 수량·일수·부분조제 / Fill details → quantity/days supply/partial fill |
| `pharmacy_dispensing_ops.label_generate` | `v11_pharmacy_dispensing_ops_label_generate` | C | 조제 → 복약지시·라벨 발행 / Dispense → directions/label generation |
| `pharmacy_dispensing_ops.product_lot_serial_scan` | `v11_pharmacy_dispensing_ops_product_lot_serial_scan` | C | 조제 약품 → 제품·로트·일련번호 확인 / Product → item/lot/serial verification |
| `pharmacy_dispensing_ops.compound_prepare` | `v11_pharmacy_dispensing_ops_compound_prepare` | C | 조제 작업 → 배합·포장·준비 완료 / Fill task → compound/package/prepared |
| `pharmacy_dispensing_ops.final_verification` | `v11_pharmacy_dispensing_ops_final_verification` | C | 준비된 약 → 약사 최종 검증 / Prepared medication → pharmacist final verification |
| `pharmacy_dispensing_ops.controlled_substance_log` | `v11_pharmacy_dispensing_ops_controlled_substance_log` | C | 통제약 → 처방·수량·조제 기록 / Controlled drug → prescription/quantity/dispense log |
| `pharmacy_dispensing_ops.dispense_hold_resume` | `v11_pharmacy_dispensing_ops_dispense_hold_resume` | C | 조제 상태 → 보류·재개·중단 / Dispense status → hold/resume/stop |
| `pharmacy_dispensing_ops.patient_counseling_record` | `v11_pharmacy_dispensing_ops_patient_counseling_record` | C | 수령 준비 → 복약지도·REMS 교육 확인 / Ready for pickup → counseling/REMS education |
| `pharmacy_dispensing_ops.pickup_identity_receiver_check` | `v11_pharmacy_dispensing_ops_pickup_identity_receiver_check` | C | 수령 → 환자·대리인·신원 확인 / Pickup → patient/receiver/identity verification |
| `pharmacy_dispensing_ops.handover_complete` | `v11_pharmacy_dispensing_ops_handover_complete` | C | 검증 완료 → 인도·조제 완료 / Verified → hand over/complete dispense |
| `pharmacy_dispensing_ops.return_to_stock_reverse` | `v11_pharmacy_dispensing_ops_return_to_stock_reverse` | C | 미수령·취소 조제 → 재고 복귀·역분개 / Unclaimed/cancelled fill → return to stock/reverse |

공식 근거:

- HL7, [MedicationDispense](https://hl7.org/fhir/medicationdispense.html) — preparation, in-progress, on-hold, completed, stopped/declined 상태와 prepared/handover, receiver, substitution.
- Oracle Health, [MedicationDispense REST endpoints](https://docs.oracle.com/en/industries/health/millennium-platform-apis/mfrap/api-medicationdispense.html) — patient-specific medication supply and dispense record.
- FDA, [Roles of Different Participants in REMS](https://www.fda.gov/drugs/risk-evaluation-and-mitigation-strategies-rems/roles-different-participants-rems) — pharmacist verification, counseling, safe-use conditions and pre-dispense controls.
- FDA, [Pharmacists and DSCSA requirements](https://www.fda.gov/drugs/drug-supply-chain-security-act-dscsa/pharmacists-utilize-dscsa-requirements-protect-your-patients) — product legitimacy and supply-chain verification duties.

중복 제외: 기존 `pharmacy_telehealth`는 환자의 처방 조회·리필·배송·약국 이전 목적이다. v11은 pharmacy staff의 prescription-to-dispense lifecycle만 다루며 `warehouse_fulfillment_ops`의 일반 상품 출고와 합치지 않는다.

## 3. Insurance claims adjuster operations (`insurance_claims_adjuster_ops`)

허브: `insurance_claims_adjuster_ops.hub` — 보험 손해사정 업무 / Insurance claims adjustment

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `insurance_claims_adjuster_ops.claim_queue` | `v11_insurance_claims_adjuster_ops_claim_queue` | S | 청구 작업함 → 담당·우선순위 필터 / Claim queue → owner/priority filter |
| `insurance_claims_adjuster_ops.claim_summary` | `v11_insurance_claims_adjuster_ops_claim_summary` | S | 청구 → 손실·상태·담당 요약 / Claim → loss/status/ownership summary |
| `insurance_claims_adjuster_ops.policy_coverage_verify` | `v11_insurance_claims_adjuster_ops_policy_coverage_verify` | S | 청구 → 보험계약·담보 확인 / Claim → policy/coverage verification |
| `insurance_claims_adjuster_ops.loss_parties_contacts` | `v11_insurance_claims_adjuster_ops_loss_parties_contacts` | S | 청구 → 피보험자·청구인·관계자 / Claim → insured/claimant/parties |
| `insurance_claims_adjuster_ops.incident_exposure_review` | `v11_insurance_claims_adjuster_ops_incident_exposure_review` | S | 청구 → 사고·손해 exposure / Claim → incident/exposures |
| `insurance_claims_adjuster_ops.document_evidence_review` | `v11_insurance_claims_adjuster_ops_document_evidence_review` | S | 청구 → 사진·보고서·견적·증거 / Claim → photos/reports/estimates/evidence |
| `insurance_claims_adjuster_ops.assign_reassign_claim` | `v11_insurance_claims_adjuster_ops_assign_reassign_claim` | C | 청구 → 담당자·그룹 배정 / Claim → adjuster/group assignment |
| `insurance_claims_adjuster_ops.claimant_contact_log` | `v11_insurance_claims_adjuster_ops_claimant_contact_log` | C | 청구 → 연락·면담 기록 / Claim → contact/interview log |
| `insurance_claims_adjuster_ops.coverage_decision` | `v11_insurance_claims_adjuster_ops_coverage_decision` | C | 담보 검토 → 승인·거절·사유 / Coverage review → accept/deny/reason |
| `insurance_claims_adjuster_ops.exposure_create` | `v11_insurance_claims_adjuster_ops_exposure_create` | C | 청구 → 사고·담보·청구인 연결 → exposure 생성 / Claim → incident/coverage/claimant → create exposure |
| `insurance_claims_adjuster_ops.reserve_set` | `v11_insurance_claims_adjuster_ops_reserve_set` | C | exposure → 비용유형·통화·금액 → 준비금 제출 / Exposure → cost/currency/amount → submit reserve |
| `insurance_claims_adjuster_ops.appraisal_inspection_assign` | `v11_insurance_claims_adjuster_ops_appraisal_inspection_assign` | C | 청구 → 감정·현장조사 배정 / Claim → appraisal/inspection assignment |
| `insurance_claims_adjuster_ops.liability_assessment` | `v11_insurance_claims_adjuster_ops_liability_assessment` | C | 사고 증거 → 책임비율·판단 기록 / Loss evidence → liability assessment |
| `insurance_claims_adjuster_ops.settlement_offer` | `v11_insurance_claims_adjuster_ops_settlement_offer` | C | 청구 → 합의 권한·금액 → 제안 / Claim → authority/amount → settlement offer |
| `insurance_claims_adjuster_ops.payment_check_issue` | `v11_insurance_claims_adjuster_ops_payment_check_issue` | C | 지급 가능 exposure → 수취인·지급액 → 수표·지급 제출 / Payable exposure → payee/amount → issue payment |
| `insurance_claims_adjuster_ops.recovery_subrogation` | `v11_insurance_claims_adjuster_ops_recovery_subrogation` | C | 청구 → 구상·잔존물·회수 기록 / Claim → subrogation/salvage/recovery |
| `insurance_claims_adjuster_ops.fraud_referral` | `v11_insurance_claims_adjuster_ops_fraud_referral` | C | 청구 위험 신호 → 특별조사 의뢰 / Claim risk indicators → fraud/SIU referral |
| `insurance_claims_adjuster_ops.claim_note` | `v11_insurance_claims_adjuster_ops_claim_note` | C | 청구 → privileged 업무 노트 / Claim → privileged work note |
| `insurance_claims_adjuster_ops.close_reopen_exposure` | `v11_insurance_claims_adjuster_ops_close_reopen_exposure` | C | exposure → 결과 코드 → 종료·재개 / Exposure → outcome → close/reopen |
| `insurance_claims_adjuster_ops.close_reopen_claim` | `v11_insurance_claims_adjuster_ops_close_reopen_claim` | C | 청구 → 미결 업무·재무 확인 → 종료·재개 / Claim → open-work/financial review → close/reopen |

공식 근거:

- Guidewire, [Overview of exposures in ClaimCenter](https://docs.guidewire.com/cloud/is/202603/cloudapibf/cloudAPI/ClaimCenter/fnol/exposures/c_overview-of-exposures-in-ClaimCenter.html) — incident, claimant, coverage, exposure, reserve line and validation lifecycle.
- Guidewire, [Overview of reserves in ClaimCenter](https://docs.guidewire.com/cloud/cc/202511/cloudapibf/cloudAPI/topics/112-CCFin/01-reserves/c_overview-of-reserves-in-ClaimCenter.html) — reserve sets, approval and authority limits.
- Guidewire, [Creating checks](https://docs.guidewire.com/cloud/cc/202507/cloudapibf/cloudAPI/topics/112-CCFin/02-check-creating/c_creating-checks.html) — payment/check lifecycle.
- Guidewire, [Recoveries and recovery reserves](https://docs.guidewire.com/cloud/is/202603/cloudapibf/cloudAPI/ClaimCenter/financials/recoveries.html) — subrogation, salvage and recovery.

중복 제외: 기존 `insurance`는 소비자의 계약·보험금 청구·진행조회다. v11은 adjuster 권한의 exposure, reserve, liability, settlement, payment, recovery, claim closure만 소유한다. `business_accounting`의 일반 지급과 보험 claim financial은 객체·권한이 다르다.

## 4. Airline crew operations (`airline_crew_operations`)

허브: `airline_crew_operations.hub` — 항공 승무 업무 / Airline crew operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `airline_crew_operations.roster` | `v11_airline_crew_operations_roster` | S | 승무 일정 → 월·주·일 로스터 / Crew schedule → roster view |
| `airline_crew_operations.duty_details` | `v11_airline_crew_operations_duty_details` | S | 로스터 → duty·standby·training 상세 / Roster → duty/standby/training detail |
| `airline_crew_operations.flight_sector_briefing` | `v11_airline_crew_operations_flight_sector_briefing` | S | duty → 운항 구간 → briefing package / Duty → sector → briefing package |
| `airline_crew_operations.crew_list_positions` | `v11_airline_crew_operations_crew_list_positions` | S | 운항편 → 승무원·근무 위치 / Flight → crew list/working positions |
| `airline_crew_operations.aircraft_assignment` | `v11_airline_crew_operations_aircraft_assignment` | S | 운항편 → 기종·등록·배정 / Flight → aircraft type/registration/assignment |
| `airline_crew_operations.operational_flight_plan` | `v11_airline_crew_operations_operational_flight_plan` | S | briefing → OFP·연료·경로 / Briefing → operational flight plan/fuel/route |
| `airline_crew_operations.weather_notam` | `v11_airline_crew_operations_weather_notam` | S | briefing → 기상·NOTAM / Briefing → weather/NOTAM |
| `airline_crew_operations.manual_bulletin` | `v11_airline_crew_operations_manual_bulletin` | S | 문서 → FCOM·절차·공지 / Documents → FCOM/procedures/bulletins |
| `airline_crew_operations.flight_duty_limit_assessment` | `v11_airline_crew_operations_flight_duty_limit_assessment` | S | duty → 비행·근무시간 한도 / Duty → flight/duty time limits |
| `airline_crew_operations.roster_change_ack` | `v11_airline_crew_operations_roster_change_ack` | C | 변경 로스터 → 차이 검토 → 확인 / Roster change → compare → acknowledge |
| `airline_crew_operations.duty_checkin` | `v11_airline_crew_operations_duty_checkin` | C | 다음 duty → 보고 위치·시각 → check-in / Next duty → report location/time → check in |
| `airline_crew_operations.fit_for_duty_declaration` | `v11_airline_crew_operations_fit_for_duty_declaration` | C | duty → 적합·부적합 선언 / Duty → fit/unfit declaration |
| `airline_crew_operations.fatigue_report` | `v11_airline_crew_operations_fatigue_report` | C | 안전·피로 → 상태·업무 영향 보고 / Safety/fatigue → condition/impact report |
| `airline_crew_operations.briefing_ack` | `v11_airline_crew_operations_briefing_ack` | C | briefing package → 개정·위험 확인 → acknowledge / Briefing → revisions/hazards → acknowledge |
| `airline_crew_operations.emergency_duties_signoff` | `v11_airline_crew_operations_emergency_duties_signoff` | C | 비행 briefing → 비상 임무 → 서명 / Flight briefing → emergency duties → sign off |
| `airline_crew_operations.defect_technical_debrief` | `v11_airline_crew_operations_defect_technical_debrief` | C | 운항 후 → 결함·오작동 기술 보고 / Post-flight → defect/malfunction technical debrief |
| `airline_crew_operations.cabin_service_issue` | `v11_airline_crew_operations_cabin_service_issue` | C | 운항편 → 객실·catering·안전 이슈 / Flight → cabin/catering/safety issue |
| `airline_crew_operations.flight_report_submit` | `v11_airline_crew_operations_flight_report_submit` | C | duty 완료 → 운항·비정상 보고 → 제출 / Duty complete → operational/irregularity report → submit |

공식 근거:

- Boeing, [ForeFlight Dispatch booklet](https://services.boeing.com/bgsmedias/NBAA-2021-Dispatch-booklet.pdf?context=bWFzdGVyfHJvb3R8MTIwMDMwNjR8YXBwbGljYXRpb24vcGRmfGg0Ny9oOTkvODgzOTQ3MDk0MDE5MC5wZGZ8MzcyY2RmMjM1NTgxYzIzODM0ZWJlMmU4YzM3MTAyYTZiMjc3NjRiMjMzMzQwODAyYWQxNTcxNjYzNmE5MzUyYQ) — flight release, crew device briefing documents and synchronization.
- Boeing, [Licensed Flight Training Manuals](https://services.boeing.com/training-solutions/flight-training/licensed-manuals) — FCOM/QRH/FCTM roles and operational procedures.
- ICAO, [Fatigue Management Approaches](https://www.icao.int/operational-safety/fatigue-management/fatigue-management-approaches) — duty/rest limits, fit-for-duty responsibility and fatigue hazard reporting.
- SAP, [Technical Debriefing](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/e08e0da88aa64d9095334cdb5fa3b25d/704b859d56c440e8b3f63b5b22b55852.html) — post-flight defect and malfunction reporting from mobile operations.

중복 제외: `air_travel_planning`은 승객의 예약·체크인·탑승 목적이다. v11은 crew roster, duty, operational briefing, fatigue, acknowledgement and debrief only. `fleet_driver_compliance`와 유사한 duty 표현은 aircraft/sector/crew/FTL 문맥 없이는 매칭하지 않는다.

## 5. Telecom field service operations (`telecom_field_service_ops`)

허브: `telecom_field_service_ops.hub` — 통신 현장 서비스 / Telecom field service

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `telecom_field_service_ops.assigned_work_order` | `v11_telecom_field_service_ops_assigned_work_order` | S | 현장 일정 → 배정 작업지시 / Field schedule → assigned work order |
| `telecom_field_service_ops.site_customer_access` | `v11_telecom_field_service_ops_site_customer_access` | S | 작업지시 → 고객·현장·출입정보 / Work order → customer/site/access |
| `telecom_field_service_ops.network_asset_detail` | `v11_telecom_field_service_ops_network_asset_detail` | S | 작업지시 → 회선·장비·포트 자산 / Work order → circuit/equipment/port assets |
| `telecom_field_service_ops.port_circuit_trace` | `v11_telecom_field_service_ops_port_circuit_trace` | S | 네트워크 자산 → 상·하류 회선 추적 / Network asset → upstream/downstream trace |
| `telecom_field_service_ops.equipment_serial_scan` | `v11_telecom_field_service_ops_equipment_serial_scan` | S | 현장 장비 → 바코드·일련번호 확인 / Field equipment → barcode/serial lookup |
| `telecom_field_service_ops.route_checkin` | `v11_telecom_field_service_ops_route_checkin` | C | 작업 예약 → 이동·도착·현장 check-in / Booking → travel/arrive/check in |
| `telecom_field_service_ops.work_order_accept` | `v11_telecom_field_service_ops_work_order_accept` | C | 배정 작업 → 수락·거절 / Assigned job → accept/decline |
| `telecom_field_service_ops.safety_permit_checklist` | `v11_telecom_field_service_ops_safety_permit_checklist` | C | 작업지시 → 안전·출입 permit·체크리스트 / Work order → safety/access permit/checklist |
| `telecom_field_service_ops.signal_line_test` | `v11_telecom_field_service_ops_signal_line_test` | C | 회선·설비 → 신호·광손실·연속성 측정 / Circuit/plant → signal/loss/continuity test |
| `telecom_field_service_ops.fiber_copper_splice_record` | `v11_telecom_field_service_ops_fiber_copper_splice_record` | C | 케이블·함체 → 접속·pair/fiber 기록 / Cable/enclosure → splice/pair/fiber record |
| `telecom_field_service_ops.device_config_activate` | `v11_telecom_field_service_ops_device_config_activate` | C | 장비 → 구성·프로비저닝 → 활성화 / Equipment → configure/provision → activate |
| `telecom_field_service_ops.service_provision_test` | `v11_telecom_field_service_ops_service_provision_test` | C | 서비스 → turn-up·품질시험·검증 / Service → turn-up/quality test/verify |
| `telecom_field_service_ops.outage_escalation` | `v11_telecom_field_service_ops_outage_escalation` | C | 장애 징후 → 영향·우선도 → NOC escalation / Outage evidence → impact/priority → escalate |
| `telecom_field_service_ops.parts_stock_request` | `v11_telecom_field_service_ops_parts_stock_request` | C | 작업지시 → 필요 부품 → 재고 요청 / Work order → required part → stock request |
| `telecom_field_service_ops.parts_consume_return` | `v11_telecom_field_service_ops_parts_consume_return` | C | 작업 부품 → 사용·회수·반납 기록 / Job parts → consume/recover/return |
| `telecom_field_service_ops.customer_service_restore_ack` | `v11_telecom_field_service_ops_customer_service_restore_ack` | C | 복구 시험 → 고객 서비스 복구 확인 / Restoration test → customer service restored acknowledgement |
| `telecom_field_service_ops.photo_signature` | `v11_telecom_field_service_ops_photo_signature` | C | 작업지시 → 사진·고객 서명 첨부 / Work order → photo/customer signature |
| `telecom_field_service_ops.work_order_complete_sync` | `v11_telecom_field_service_ops_work_order_complete_sync` | C | 작업지시 → 서비스·부품·시간 검토 → 완료·동기화 / Work order → service/parts/time review → complete/sync |

공식 근거:

- ServiceNow, [Field Service Management for Telecommunications](https://www.servicenow.com/content/dam/servicenow-assets/public/en-us/doc-type/resource-center/data-sheet/ds-field-service-management-for-telecommunications.pdf) — telecom service/field operations and Mobile Agent workflows.
- Microsoft, [Work with the Field Service mobile app](https://learn.microsoft.com/en-us/dynamics365/field-service/mobile/get-work-done-mobile-app) — scheduled jobs, travel, work detail, assets, parts, time, notes, attachment and completion.
- Microsoft, [Field Service work order architecture](https://learn.microsoft.com/en-us/dynamics365/field-service/field-service-architecture) — booking status, work execution, inventory consumption, review and close.
- ServiceNow, [Manage inventory in Field Service Management](https://www.servicenow.com/docs/r/field-service-management/work-order-management/sourcing-parts.html) — technician parts requirement, reserve, pick and use.

중복 제외: `telecom`은 가입자 요금제·회선·지원이며, `maintenance_asset_ops`는 일반 설비 보전이다. v11은 telecom network/circuit/port/turn-up/outage objects를 요구한다. `field_construction_ops`의 현장 작업은 RFI·도면·공정 중심이라 별도다.

## 6. ITSM and CMDB operations (`itsm_cmdb_operations`)

허브: `itsm_cmdb_operations.hub` — IT 서비스·구성관리 / IT service and configuration management

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `itsm_cmdb_operations.incident_queue` | `v11_itsm_cmdb_operations_incident_queue` | S | ITSM 작업함 → 배정 incident / ITSM queue → assigned incidents |
| `itsm_cmdb_operations.incident_detail` | `v11_itsm_cmdb_operations_incident_detail` | S | incident → 영향·긴급도·CI·타임라인 / Incident → impact/urgency/CI/timeline |
| `itsm_cmdb_operations.problem_record_review` | `v11_itsm_cmdb_operations_problem_record_review` | S | incident → 관련 problem·근본원인 / Incident → related problem/root cause |
| `itsm_cmdb_operations.known_error_review` | `v11_itsm_cmdb_operations_known_error_review` | S | problem → known error·우회책 / Problem → known error/workaround |
| `itsm_cmdb_operations.change_request_review` | `v11_itsm_cmdb_operations_change_request_review` | S | change → 계획·일정·영향 CI / Change → plan/schedule/affected CIs |
| `itsm_cmdb_operations.ci_search_detail` | `v11_itsm_cmdb_operations_ci_search_detail` | S | CMDB → CI 검색·속성 / CMDB → CI search/attributes |
| `itsm_cmdb_operations.ci_relationship_map` | `v11_itsm_cmdb_operations_ci_relationship_map` | S | CI → 상·하류 관계·통합 맵 / CI → upstream/downstream relationships/map |
| `itsm_cmdb_operations.ci_baseline_compare` | `v11_itsm_cmdb_operations_ci_baseline_compare` | S | CI → baseline → 변경 비교 / CI → baseline → compare changes |
| `itsm_cmdb_operations.service_dependency_impact` | `v11_itsm_cmdb_operations_service_dependency_impact` | S | 서비스·CI → 의존관계·영향 분석 / Service/CI → dependency/impact analysis |
| `itsm_cmdb_operations.assign_reassign` | `v11_itsm_cmdb_operations_assign_reassign` | C | incident → 그룹·담당자 재배정 / Incident → group/assignee reassign |
| `itsm_cmdb_operations.incident_work_note` | `v11_itsm_cmdb_operations_incident_work_note` | C | incident → 업무노트·고객 댓글 / Incident → work note/customer comment |
| `itsm_cmdb_operations.priority_severity_update` | `v11_itsm_cmdb_operations_priority_severity_update` | C | incident → 영향·긴급도·우선순위 수정 / Incident → impact/urgency/priority update |
| `itsm_cmdb_operations.major_incident_propose` | `v11_itsm_cmdb_operations_major_incident_propose` | C | incident → major incident 후보·제안 / Incident → propose major incident |
| `itsm_cmdb_operations.incident_resolve` | `v11_itsm_cmdb_operations_incident_resolve` | C | incident → 해결코드·노트 → resolve / Incident → resolution code/notes → resolve |
| `itsm_cmdb_operations.change_risk_assessment` | `v11_itsm_cmdb_operations_change_risk_assessment` | C | change → 위험·충돌·영향 평가 / Change → risk/conflict/impact assessment |
| `itsm_cmdb_operations.change_approve_reject` | `v11_itsm_cmdb_operations_change_approve_reject` | C | change → 권한·검토 → approve/reject / Change → authority/review → approve/reject |
| `itsm_cmdb_operations.change_implement_status` | `v11_itsm_cmdb_operations_change_implement_status` | C | change task → 구현·검증·rollback 상태 / Change task → implement/validate/rollback status |
| `itsm_cmdb_operations.ci_create_edit` | `v11_itsm_cmdb_operations_ci_create_edit` | C | CMDB → CI class·식별자·상태 편집 / CMDB → CI class/identifier/state edit |
| `itsm_cmdb_operations.ci_relationship_edit` | `v11_itsm_cmdb_operations_ci_relationship_edit` | C | CI 맵 → parent·child·relation 수정 / CI map → parent/child/relation edit |
| `itsm_cmdb_operations.ci_retire_archive` | `v11_itsm_cmdb_operations_ci_retire_archive` | C | CI lifecycle → retire·archive·delete policy / CI lifecycle → retire/archive/delete policy |

공식 근거:

- ServiceNow, [My incidents in ITSM Mobile Agent](https://www.servicenow.com/docs/r/it-service-management/itsm-mobile-agent/assigned-incidents-mobile.html) — mobile incident detail, notes, reassignment, resolve and major incident proposal.
- ServiceNow, [Overview of CMDB](https://www.servicenow.com/docs/r/servicenow-platform/configuration-management-database-cmdb/cnfig-mgmt-and-cmdb.html) — CI and service configuration model.
- ServiceNow, [CI relationships in the CMDB](https://www.servicenow.com/docs/r/servicenow-platform/configuration-management-database-cmdb/c_CIRelationships.html) — parent/child relationships, dependencies and relationship editing.
- ServiceNow, [Working with CMDB Data Manager](https://www.servicenow.com/docs/r/servicenow-platform/configuration-management-database-cmdb/cmdb-data-management.html) — CI retirement, archive, delete, approval and lifecycle safety.

중복 제외: `incident_oncall`은 PagerDuty류의 서비스 장애 대응·온콜 조정이다. v11은 ITIL incident/problem/change와 governed CMDB CI lifecycle을 소유한다. `workspace_administration`의 사용자·조직 설정과도 분리한다.

## 7. Cybersecurity SOC operations (`cybersecurity_soc_ops`)

허브: `cybersecurity_soc_ops.hub` — 보안관제 업무 / Security operations center

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `cybersecurity_soc_ops.alert_incident_queue` | `v11_cybersecurity_soc_ops_alert_incident_queue` | S | SOC → alert·incident 작업함 / SOC → alert/incident queue |
| `cybersecurity_soc_ops.incident_detail` | `v11_cybersecurity_soc_ops_incident_detail` | S | incident → 심각도·상태·MITRE·요약 / Incident → severity/status/MITRE/summary |
| `cybersecurity_soc_ops.alert_evidence_timeline` | `v11_cybersecurity_soc_ops_alert_evidence_timeline` | S | incident → alert·event·evidence timeline / Incident → alerts/events/evidence timeline |
| `cybersecurity_soc_ops.entity_investigation_graph` | `v11_cybersecurity_soc_ops_entity_investigation_graph` | S | incident → 사용자·호스트·IP·파일 관계 / Incident → user/host/IP/file graph |
| `cybersecurity_soc_ops.related_incident_hunt` | `v11_cybersecurity_soc_ops_related_incident_hunt` | S | incident → 유사·관련 incident / Incident → similar/related incidents |
| `cybersecurity_soc_ops.indicator_enrichment` | `v11_cybersecurity_soc_ops_indicator_enrichment` | S | observable → reputation·lookup·context / Observable → reputation/lookup/context |
| `cybersecurity_soc_ops.query_hunt` | `v11_cybersecurity_soc_ops_query_hunt` | S | entity·indicator → hunting query·events / Entity/indicator → hunting query/events |
| `cybersecurity_soc_ops.assign_owner` | `v11_cybersecurity_soc_ops_assign_owner` | C | security incident → analyst·group assignment / Security incident → analyst/group assignment |
| `cybersecurity_soc_ops.severity_status_update` | `v11_cybersecurity_soc_ops_severity_status_update` | C | incident → severity·new/active status / Incident → severity/new/active status |
| `cybersecurity_soc_ops.case_comment` | `v11_cybersecurity_soc_ops_case_comment` | C | incident → investigation comment·worknote / Incident → investigation comment/worknote |
| `cybersecurity_soc_ops.contain_device` | `v11_cybersecurity_soc_ops_contain_device` | C | compromised device → 영향 검토 → containment / Compromised device → impact review → contain |
| `cybersecurity_soc_ops.isolate_device` | `v11_cybersecurity_soc_ops_isolate_device` | C | endpoint → 연결 유지 범위 확인 → network isolate / Endpoint → connectivity review → isolate |
| `cybersecurity_soc_ops.contain_user` | `v11_cybersecurity_soc_ops_contain_user` | C | compromised identity → 세션·접근 영향 → contain / Compromised identity → session/access impact → contain |
| `cybersecurity_soc_ops.block_indicator` | `v11_cybersecurity_soc_ops_block_indicator` | C | malicious IP·URL·hash → scope → block / Malicious IP/URL/hash → scope → block |
| `cybersecurity_soc_ops.collect_investigation_package` | `v11_cybersecurity_soc_ops_collect_investigation_package` | C | endpoint → 수집 범위·민감도 → package collection / Endpoint → scope/sensitivity → collect package |
| `cybersecurity_soc_ops.quarantine_file` | `v11_cybersecurity_soc_ops_quarantine_file` | C | suspicious file → hash·host 확인 → quarantine / Suspicious file → hash/host verification → quarantine |
| `cybersecurity_soc_ops.run_response_playbook` | `v11_cybersecurity_soc_ops_run_response_playbook` | C | incident → 대응 playbook·대상 검토 → run / Incident → playbook/targets review → run |
| `cybersecurity_soc_ops.eradication_recovery_status` | `v11_cybersecurity_soc_ops_eradication_recovery_status` | C | incident → containment·eradication·recovery 상태 / Incident → containment/eradication/recovery status |
| `cybersecurity_soc_ops.close_classify_incident` | `v11_cybersecurity_soc_ops_close_classify_incident` | C | incident → true/benign/false positive·사유 → close / Incident → classification/reason → close |
| `cybersecurity_soc_ops.post_incident_report` | `v11_cybersecurity_soc_ops_post_incident_report` | C | closed incident → timeline·impact·lessons → report / Closed incident → timeline/impact/lessons → report |

공식 근거:

- Microsoft, [Investigate Microsoft Sentinel incidents](https://learn.microsoft.com/en-us/azure/sentinel/investigate-incidents) — evidence, entities, graph, timeline and exploration queries.
- Microsoft, [Navigate, triage and manage Sentinel incidents](https://learn.microsoft.com/en-us/azure/sentinel/incident-navigate-triage) — ownership, severity/status, comments, classification and closure.
- Microsoft, [Take response actions on a device](https://learn.microsoft.com/en-us/defender-endpoint/respond-machine-alerts) — device/user containment, isolation and undo authority.
- ServiceNow, [Security Incident Response](https://www.servicenow.com/docs/r/security-management/security-incident-response/sir-landing-page.html) — discovery, analysis, containment, eradication, recovery and post-incident closure lifecycle.

중복 제외: `security`는 소비자 계정 보안, `incident_oncall`은 availability incident다. v11은 alert/evidence/entity/indicator/containment/classification을 갖는 cyber incident만 소유한다. `block`, `isolate`, `close`는 대상 entity와 security lifecycle이 없으면 확정하지 않는다.

## 8. Social services casework (`social_services_casework`)

허브: `social_services_casework.hub` — 사회복지 사례관리 / Social services casework

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `social_services_casework.case_queue` | `v11_social_services_casework_case_queue` | S | 사례 작업함 → 담당·위험도·기한 / Case queue → owner/risk/deadline |
| `social_services_casework.constituent_household_profile` | `v11_social_services_casework_constituent_household_profile` | S | 사례 → 당사자·가구·관계 / Case → constituent/household/relationships |
| `social_services_casework.eligibility_application_review` | `v11_social_services_casework_eligibility_application_review` | S | 사례 → 신청·소득·자산·자격자료 / Case → application/income/assets/eligibility data |
| `social_services_casework.document_evidence` | `v11_social_services_casework_document_evidence` | S | 사례 → 동의·증빙·전문가 보고 / Case → consent/evidence/professional reports |
| `social_services_casework.care_plan_view` | `v11_social_services_casework_care_plan_view` | S | 사례 → 현재 care plan·목표·급여 / Case → current care plan/goals/benefits |
| `social_services_casework.referral_intake` | `v11_social_services_casework_referral_intake` | C | 의뢰·신고 → 대상자·우려·출처 → intake / Referral/report → person/concern/source → intake |
| `social_services_casework.dynamic_needs_assessment` | `v11_social_services_casework_dynamic_needs_assessment` | C | 사례 → 욕구·강점·환경 평가 / Case → needs/strengths/environment assessment |
| `social_services_casework.safeguarding_risk_assessment` | `v11_social_services_casework_safeguarding_risk_assessment` | C | 우려 → 위해·착취·긴급도·보호요인 평가 / Concern → harm/exploitation/urgency/protective factors |
| `social_services_casework.home_visit_plan` | `v11_social_services_casework_home_visit_plan` | C | 사례 → 방문 목적·일정·안전 계획 / Case → visit purpose/schedule/safety plan |
| `social_services_casework.interaction_note` | `v11_social_services_casework_interaction_note` | C | 사례 → 면담·방문·연락 기록 / Case → interview/visit/contact note |
| `social_services_casework.care_plan_create_update` | `v11_social_services_casework_care_plan_create_update` | C | 평가 → 목표·지원·책임자·검토일 / Assessment → goals/support/owner/review date |
| `social_services_casework.goal_benefit_assignment` | `v11_social_services_casework_goal_benefit_assignment` | C | care plan → 목표·급여·서비스 배정 / Care plan → goal/benefit/service assignment |
| `social_services_casework.service_referral` | `v11_social_services_casework_service_referral` | C | 욕구 → 제공기관·서비스·동의 → referral / Need → provider/service/consent → referral |
| `social_services_casework.benefit_eligibility_decision` | `v11_social_services_casework_benefit_eligibility_decision` | C | 신청 → 기준·증빙 검토 → 승인·반려 / Application → criteria/evidence → approve/return |
| `social_services_casework.benefit_schedule_disbursement` | `v11_social_services_casework_benefit_schedule_disbursement` | C | 급여 → 일정·회기·지급 상태 / Benefit → schedule/session/disbursement status |
| `social_services_casework.multiagency_case_conference` | `v11_social_services_casework_multiagency_case_conference` | C | 사례 → 참여기관·결정·action 기록 / Case → agencies/decisions/actions record |
| `social_services_casework.case_review` | `v11_social_services_casework_case_review` | C | 사례 → 진척·위험·계획 재검토 / Case → progress/risk/plan review |
| `social_services_casework.case_close_transfer` | `v11_social_services_casework_case_close_transfer` | C | 사례 → 미결 위험·동의·인계 확인 → 종료·이관 / Case → residual risk/consent/handoff → close/transfer |

공식 근거:

- Salesforce, [Public Sector Solutions](https://help.salesforce.com/s/articleView?id=release-notes.rn_public_sector_solutions.htm&language=en_US&release=244&type=5) — mobile case objects, assessments, care plans, benefits and interaction notes.
- Salesforce, [Care Plans for Program and Case Management](https://help.salesforce.com/s/articleView?id=ind.prog_case_mgmt_care_plans.htm&language=en_US&type=5) — assistance intake, goals, benefits and service planning.
- UK Youth Justice Board, [How to assess children in the youth justice system](https://www.gov.uk/guidance/case-management-guidance/how-to-assess-children-in-the-youth-justice-system) — continuous assessment, home visits, safety/well-being and multi-professional evidence.
- UK Government, [Adult social care terminology](https://www.gov.uk/government/publications/adult-social-care-finance-return-2025-to-2026/ascfr-terminology-and-its-usage) — assessment-led care management, service access and safeguarding lifecycle.

중복 제외: `customer_support_agent`의 ticket/case는 고객 문의 해결이고 `family_caregiving`은 비공식 care circle이다. v11은 statutory/agency case, assessment, safeguarding, eligibility, benefit and multi-agency lifecycle만 소유한다.

## 9. Estate and probate administration (`estate_probate_administration`)

허브: `estate_probate_administration.hub` — 상속재산·검인 관리 / Estate and probate administration

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `estate_probate_administration.estate_case_queue` | `v11_estate_probate_administration_estate_case_queue` | S | estate matter → 상태·기한·담당 / Estate matters → status/deadline/owner |
| `estate_probate_administration.decedent_will_executor_detail` | `v11_estate_probate_administration_decedent_will_executor_detail` | S | estate → 사망자·유언·executor / Estate → decedent/will/executor |
| `estate_probate_administration.beneficiary_heir_directory` | `v11_estate_probate_administration_beneficiary_heir_directory` | S | estate → 수익자·상속인·관계 / Estate → beneficiaries/heirs/relationships |
| `estate_probate_administration.asset_inventory` | `v11_estate_probate_administration_asset_inventory` | S | estate → 부동산·계좌·증권·동산 / Estate → property/accounts/securities/assets |
| `estate_probate_administration.liability_debt_inventory` | `v11_estate_probate_administration_liability_debt_inventory` | S | estate → 채무·저당·관리비용 / Estate → debts/liens/admin expenses |
| `estate_probate_administration.inheritance_tax_status` | `v11_estate_probate_administration_inheritance_tax_status` | S | estate → 세액·신고·참조코드 상태 / Estate → tax/filing/reference status |
| `estate_probate_administration.grant_status` | `v11_estate_probate_administration_grant_status` | S | probate case → submitted·issued·stopped status / Probate case → submitted/issued/stopped status |
| `estate_probate_administration.estate_valuation` | `v11_estate_probate_administration_estate_valuation` | C | 자산·채무 → 평가일·가액·근거 기록 / Assets/liabilities → valuation date/value/evidence |
| `estate_probate_administration.probate_application_draft` | `v11_estate_probate_administration_probate_application_draft` | C | estate → grant type·applicant → application draft / Estate → grant type/applicant → draft application |
| `estate_probate_administration.supporting_document_bundle` | `v11_estate_probate_administration_supporting_document_bundle` | C | application → will·death certificate·IHT 문서 첨부 / Application → will/death certificate/tax documents |
| `estate_probate_administration.statement_of_truth_sign` | `v11_estate_probate_administration_statement_of_truth_sign` | C | application → 확인·진술 → sign / Application → declaration → sign |
| `estate_probate_administration.probate_submit_pay` | `v11_estate_probate_administration_probate_submit_pay` | C | application → fee·PBA·최종 검토 → submit/pay / Application → fee/account/final review → submit/pay |
| `estate_probate_administration.caveat_stop_application` | `v11_estate_probate_administration_caveat_stop_application` | C | decedent details → caveat·근거 → stop application / Decedent details → caveat/reason → stop application |
| `estate_probate_administration.estate_accounting` | `v11_estate_probate_administration_estate_accounting` | C | estate → receipts·expenses·income·분배 장부 / Estate → receipts/expenses/income/distribution ledger |
| `estate_probate_administration.creditor_debt_payment` | `v11_estate_probate_administration_creditor_debt_payment` | C | valid debt → creditor·amount·priority → pay / Valid debt → creditor/amount/priority → pay |
| `estate_probate_administration.asset_sale_transfer` | `v11_estate_probate_administration_asset_sale_transfer` | C | estate asset → authority·valuation·buyer/transferee → dispose / Estate asset → authority/value/recipient → dispose |
| `estate_probate_administration.beneficiary_distribution` | `v11_estate_probate_administration_beneficiary_distribution` | C | net estate → will/law share·beneficiary → distribute / Net estate → entitlement/beneficiary → distribute |
| `estate_probate_administration.estate_close_final_return` | `v11_estate_probate_administration_estate_close_final_return` | C | estate → final accounting·tax·distribution → close / Estate → final accounts/tax/distribution → close |

공식 근거:

- HM Courts & Tribunals Service, [Apply for probate with MyHMCTS](https://www.gov.uk/government/publications/myhmcts-how-to-apply-for-probate-online/apply-for-probate-with-myhmcts) — case creation, grant types, documents, tax code, submission/payment and tracking.
- UK Government, [Applying for probate](https://www.gov.uk/applying-for-probate) — executor eligibility, estate valuation, inheritance tax, grant and debt/tax/distribution order.
- IRS, [Responsibilities of an estate administrator](https://www.irs.gov/individuals/responsibilities-of-an-estate-administrator) — representative roles, estate tax and income tax duties.
- IRS, [Publication 559](https://www.irs.gov/publications/p559) — estate income, asset sale, debts/expenses, beneficiary distributions and final accounting.

중복 제외: `legal_practice_ops`는 일반 client-matter, court filing, trust ledger다. v11은 decedent/will/executor/beneficiary/estate/grant lifecycle만 소유한다. `genealogy_family_history`의 가족관계는 역사연구이며 법적 entitlement를 뜻하지 않는다.

## 10. Maritime and port logistics (`maritime_port_logistics`)

허브: `maritime_port_logistics.hub` — 항만·해상 터미널 운영 / Maritime and port terminal operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `maritime_port_logistics.vessel_schedule` | `v11_maritime_port_logistics_vessel_schedule` | S | 항만 운영 → vessel ETA·ETD·call / Port operations → vessel ETA/ETD/call |
| `maritime_port_logistics.berth_plan` | `v11_maritime_port_logistics_berth_plan` | S | vessel call → berth window·제약 / Vessel call → berth window/constraints |
| `maritime_port_logistics.yard_map_slot` | `v11_maritime_port_logistics_yard_map_slot` | S | terminal → block·bay·row·tier / Terminal → block/bay/row/tier |
| `maritime_port_logistics.container_cargo_lookup` | `v11_maritime_port_logistics_container_cargo_lookup` | S | container·BL → 상태·위치·cargo / Container/BOL → status/location/cargo |
| `maritime_port_logistics.dangerous_goods_manifest` | `v11_maritime_port_logistics_dangerous_goods_manifest` | S | vessel·container → IMDG class·UN·stow location / Vessel/container → IMDG class/UN/stow location |
| `maritime_port_logistics.gate_appointment` | `v11_maritime_port_logistics_gate_appointment` | S | gate → truck appointment·문서 / Gate → truck appointment/documents |
| `maritime_port_logistics.vessel_stow_plan` | `v11_maritime_port_logistics_vessel_stow_plan` | S | vessel → bay plan·load/discharge sequence / Vessel → bay plan/load-discharge sequence |
| `maritime_port_logistics.gang_equipment_plan` | `v11_maritime_port_logistics_gang_equipment_plan` | S | vessel operation → gang·crane·equipment plan / Vessel operation → gang/crane/equipment plan |
| `maritime_port_logistics.berth_assignment` | `v11_maritime_port_logistics_berth_assignment` | C | vessel call → draft·length·window 검토 → berth assign / Vessel call → constraints review → berth assign |
| `maritime_port_logistics.yard_slot_assignment` | `v11_maritime_port_logistics_yard_slot_assignment` | C | container → size·weight·hazard·destination → slot assign / Container → attributes → yard slot assign |
| `maritime_port_logistics.gate_in_out` | `v11_maritime_port_logistics_gate_in_out` | C | truck·container → ID·seal·문서 → gate in/out / Truck/container → ID/seal/documents → gate in/out |
| `maritime_port_logistics.container_inspection_hold` | `v11_maritime_port_logistics_container_inspection_hold` | C | container → damage·customs·security inspection → hold/release / Container → inspection → hold/release |
| `maritime_port_logistics.cargo_receipt_delivery` | `v11_maritime_port_logistics_cargo_receipt_delivery` | C | cargo → party·quantity·condition → receive/deliver / Cargo → party/quantity/condition → receive/deliver |
| `maritime_port_logistics.container_stuff_strip` | `v11_maritime_port_logistics_container_stuff_strip` | C | container → cargo·seal·location → stuff/strip / Container → cargo/seal/location → stuff/strip |
| `maritime_port_logistics.load_discharge_move` | `v11_maritime_port_logistics_load_discharge_move` | C | move instruction → container·from/to·equipment → confirm / Move instruction → container/from-to/equipment → confirm |
| `maritime_port_logistics.reefer_temperature_exception` | `v11_maritime_port_logistics_reefer_temperature_exception` | C | reefer → setpoint·reading·alarm → intervention record / Reefer → setpoint/reading/alarm → intervention |
| `maritime_port_logistics.dangerous_goods_segregation_release` | `v11_maritime_port_logistics_dangerous_goods_segregation_release` | C | dangerous cargo → compatibility·stow·permit → approve/release / Dangerous cargo → compatibility/stow/permit → approve/release |
| `maritime_port_logistics.rail_handover` | `v11_maritime_port_logistics_rail_handover` | C | rail consist → container list·seal·location → handover / Rail consist → containers/seals/location → handover |
| `maritime_port_logistics.equipment_dispatch` | `v11_maritime_port_logistics_equipment_dispatch` | C | move queue → crane·tractor·operator → dispatch / Move queue → equipment/operator → dispatch |
| `maritime_port_logistics.operation_close_report` | `v11_maritime_port_logistics_operation_close_report` | C | vessel/shift → moves·exceptions·damage → close report / Vessel/shift → moves/exceptions/damage → close report |

공식 근거:

- Mumbai Port Authority, [Integrated Port Operating System](https://www.mumbaiport.gov.in/show_content.php?lang=1&level=3&lid=640&ls_id=834) — vessel, gate, import/export, stuffing/stripping, cargo receipt/delivery, equipment and rail operations.
- IMO, [Cargo Securing and Packing](https://www.imo.org/en/ourwork/safety/pages/cargosecuring-default.aspx) — cargo packing, stowage and securing safety.
- IMO, [International Maritime Dangerous Goods Code](https://www.imo.org/en/ourwork/safety/pages/dangerousgoods-default.aspx) — classification, packing, container traffic, stowage and segregation.
- IMO, [Emergency Response Procedures for Ships Carrying Dangerous Goods](https://www.imo.org/en/ourwork/safety/pages/ems-guide.aspx) — dangerous-goods fire/spillage response tied to type, quantity, packaging and stow location.

중복 제외: `warehouse_fulfillment_ops`는 warehouse SKU/order lifecycle, `parcel_courier`는 last-mile shipment lifecycle다. v11은 vessel/berth/yard/container/gate/crane/IMDG objects의 결합이 필수다. 일반 `receive`, `move`, `release`만으로 항만 intent를 확정하지 않는다.

## 11. Clinical trial site operations (`clinical_trial_site_ops`)

허브: `clinical_trial_site_ops.hub` — 임상시험 기관 업무 / Clinical trial site operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `clinical_trial_site_ops.study_site_mode` | `v11_clinical_trial_site_ops_study_site_mode` | S | study → site → production/training mode / Study → site → production/training mode |
| `clinical_trial_site_ops.subject_list_profile` | `v11_clinical_trial_site_ops_subject_list_profile` | S | study → subjects → coded subject profile / Study → subjects → coded subject profile |
| `clinical_trial_site_ops.informed_consent_status` | `v11_clinical_trial_site_ops_informed_consent_status` | S | subject → consent version·date·status / Subject → consent version/date/status |
| `clinical_trial_site_ops.visit_schedule` | `v11_clinical_trial_site_ops_visit_schedule` | S | subject → next/past/unscheduled visits / Subject → next/past/unscheduled visits |
| `clinical_trial_site_ops.kit_site_inventory` | `v11_clinical_trial_site_ops_kit_site_inventory` | S | supplies → site inventory → kit status·location / Supplies → site inventory → kit status/location |
| `clinical_trial_site_ops.subject_add_screen` | `v11_clinical_trial_site_ops_subject_add_screen` | C | study → add subject → consent·eligibility form → screen / Study → add subject → consent/eligibility → screen |
| `clinical_trial_site_ops.screen_fail_rescreen` | `v11_clinical_trial_site_ops_screen_fail_rescreen` | C | subject → eligibility outcome·reason → screen fail/rescreen / Subject → eligibility/reason → screen fail/rescreen |
| `clinical_trial_site_ops.eligibility_randomization` | `v11_clinical_trial_site_ops_eligibility_randomization` | C | active screened subject → required data·kit availability → randomize / Eligible subject → data/supply checks → randomize |
| `clinical_trial_site_ops.visit_form_data` | `v11_clinical_trial_site_ops_visit_form_data` | C | visit → protocol form·required fields → save/complete / Visit → protocol forms/required fields → save/complete |
| `clinical_trial_site_ops.visit_skip_unscheduled` | `v11_clinical_trial_site_ops_visit_skip_unscheduled` | C | subject → missed/dynamic event → skip/start unscheduled visit / Subject → missed/dynamic event → skip/start visit |
| `clinical_trial_site_ops.adverse_event_record` | `v11_clinical_trial_site_ops_adverse_event_record` | C | subject → AE onset·severity·causality·action / Subject → AE onset/severity/causality/action |
| `clinical_trial_site_ops.concomitant_medication_record` | `v11_clinical_trial_site_ops_concomitant_medication_record` | C | subject → concomitant drug·dose·dates / Subject → concomitant medication/dose/dates |
| `clinical_trial_site_ops.data_query_answer` | `v11_clinical_trial_site_ops_data_query_answer` | C | form field → data query·source review → answer / Form field → query/source review → answer |
| `clinical_trial_site_ops.source_data_sign` | `v11_clinical_trial_site_ops_source_data_sign` | C | subject data → completeness·query review → approve/sign / Subject data → completeness/query review → sign |
| `clinical_trial_site_ops.shipment_receive` | `v11_clinical_trial_site_ops_shipment_receive` | C | supplies → shipment → seal·temperature·kits → receive / Supplies → shipment → seal/temperature/kits → receive |
| `clinical_trial_site_ops.kit_dispense` | `v11_clinical_trial_site_ops_kit_dispense` | C | visit → subject·dose·kit numbers → dispense/confirm / Visit → subject/dose/kits → dispense/confirm |
| `clinical_trial_site_ops.dose_titration_hold` | `v11_clinical_trial_site_ops_dose_titration_hold` | C | dispensation visit → protocol arm·current dose → titrate/hold / Dispensation visit → arm/current dose → titrate/hold |
| `clinical_trial_site_ops.kit_reconcile_return_destroy` | `v11_clinical_trial_site_ops_kit_reconcile_return_destroy` | C | site inventory → used/returned/damaged kits → reconcile/ship/destruct / Site inventory → kit disposition → reconcile/return/destroy |
| `clinical_trial_site_ops.subject_withdraw_complete` | `v11_clinical_trial_site_ops_subject_withdraw_complete` | C | subject → reason·last dose·follow-up → withdraw/complete / Subject → reason/last dose/follow-up → withdraw/complete |
| `clinical_trial_site_ops.study_report_export` | `v11_clinical_trial_site_ops_study_report_export` | C | study/site → subject·visit·kit report → generate/export / Study/site → subject/visit/kit report → export |

공식 근거:

- Oracle Life Sciences, [Quick Start for Sites](https://docs.oracle.com/en/industries/life-sciences/clinical-one/quick-site-setup/index_text.html) — add/screen subject, visit data, AE/CM, randomization, dispensation and query workflows.
- Oracle Life Sciences, [Access study modes and pages](https://docs.oracle.com/en/industries/life-sciences/clinical-one/site-information/access-study-modes.html) — production/training, subject management, visits, shipment and kit inventory/reconciliation.
- Oracle Life Sciences, [Complete a randomization or dispensation visit](https://docs.oracle.com/en/industries/life-sciences/clinical-one/site-information/complete-randomization-or-dispensation-visit.html) — eligibility, required forms, kit availability, withdrawn-state guard and final dispense.
- FDA, [Federal Regulations for Clinical Investigators](https://www.fda.gov/drugs/investigational-new-drug-ind-application/federal-regulations-clinical-investigators) — informed consent, subject safety, investigational drug control, records, reports and IRB responsibilities.
- FDA, [Protocol Deviations guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/protocol-deviations-clinical-investigations-drugs-biological-products-and-devices) — deviation identification, classification and reporting boundaries.

중복 제외: `laboratory_research_ops`는 general research notebook/sample workflow다. v11은 regulated study/site/subject/visit/consent/randomization/investigational kit lifecycle만 소유한다. `clinical_care_team_ops`의 patient care order는 subject protocol data와 합치지 않는다.

## 12. Emergency response operations (`emergency_response_operations`)

허브: `emergency_response_operations.hub` — 재난·긴급대응 운영 / Emergency response operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `emergency_response_operations.incident_map` | `v11_emergency_response_operations_incident_map` | S | incident → operational map·perimeter / Incident → operational map/perimeter |
| `emergency_response_operations.incident_briefing_iap` | `v11_emergency_response_operations_incident_briefing_iap` | S | incident → briefing·IAP·objectives / Incident → briefing/IAP/objectives |
| `emergency_response_operations.personnel_resource_status` | `v11_emergency_response_operations_personnel_resource_status` | S | incident → personnel·unit·equipment status / Incident → personnel/unit/equipment status |
| `emergency_response_operations.hazard_hot_zone` | `v11_emergency_response_operations_hazard_hot_zone` | S | map → hazard·hot/warm/cold zones / Map → hazard/hot-warm-cold zones |
| `emergency_response_operations.assignment_list` | `v11_emergency_response_operations_assignment_list` | S | incident → branch·division·task assignments / Incident → branch/division/task assignments |
| `emergency_response_operations.offline_map_download` | `v11_emergency_response_operations_offline_map_download` | C | incident area → map extent·layers → download / Incident area → map extent/layers → download |
| `emergency_response_operations.responder_checkin` | `v11_emergency_response_operations_responder_checkin` | C | incident → responder·agency·qualification → check in / Incident → responder/agency/qualification → check in |
| `emergency_response_operations.assignment_accept` | `v11_emergency_response_operations_assignment_accept` | C | assignment → supervisor·location·communications → accept / Assignment → supervisor/location/comms → accept |
| `emergency_response_operations.situation_observation_submit` | `v11_emergency_response_operations_situation_observation_submit` | C | map location → observation·photo·time → submit / Map location → observation/photo/time → submit |
| `emergency_response_operations.damage_needs_assessment` | `v11_emergency_response_operations_damage_needs_assessment` | C | site·population → damage·need·priority assessment / Site/population → damage/needs/priority assessment |
| `emergency_response_operations.resource_request` | `v11_emergency_response_operations_resource_request` | C | assignment → kind/type/quantity/delivery → request / Assignment → kind/type/quantity/delivery → request |
| `emergency_response_operations.resource_dispatch` | `v11_emergency_response_operations_resource_dispatch` | C | approved request → unit·route·staging → dispatch / Approved request → unit/route/staging → dispatch |
| `emergency_response_operations.evacuation_shelter_status` | `v11_emergency_response_operations_evacuation_shelter_status` | C | operational area → evacuation·shelter capacity/status / Operational area → evacuation/shelter status |
| `emergency_response_operations.patient_triage_record` | `v11_emergency_response_operations_patient_triage_record` | C | casualty → triage category·location·destination / Casualty → triage category/location/destination |
| `emergency_response_operations.safety_message_ack` | `v11_emergency_response_operations_safety_message_ack` | C | incident safety message → hazard·PPE·route → acknowledge / Safety message → hazard/PPE/route → acknowledge |
| `emergency_response_operations.incident_log_update` | `v11_emergency_response_operations_incident_log_update` | C | incident → time·decision·event log / Incident → time/decision/event log |
| `emergency_response_operations.personnel_accountability_update` | `v11_emergency_response_operations_personnel_accountability_update` | C | division/group → personnel location·condition·status / Division/group → personnel location/condition/status |
| `emergency_response_operations.resource_demobilize` | `v11_emergency_response_operations_resource_demobilize` | C | resource → assignment clear·checkout·destination → demobilize / Resource → clearance/checkout/destination → demobilize |
| `emergency_response_operations.offline_sync` | `v11_emergency_response_operations_offline_sync` | C | offline map·forms → conflict·connectivity 검토 → sync / Offline map/forms → conflict/connectivity review → sync |
| `emergency_response_operations.incident_close_handoff` | `v11_emergency_response_operations_incident_close_handoff` | C | operational period → unresolved hazards·resources·records → close/handoff / Operational period → residual hazards/resources/records → close/handoff |

공식 근거:

- FEMA/USFA, [Operational Templates and Guidance for EMS Mass Incident Deployment](https://www.usfa.fema.gov/downloads/pdf/publications/templates_guidance_ems_mass_incident_deployment.pdf) — responder check-in, IAP, unity of command, accountability and resource tracking.
- FEMA, [Division/Group Supervisor Position Checklist](https://training.fema.gov/emiweb/is/icsresource/assets/dgs_pcl.pdf) — briefing, assignments, safety, IAP, resource requests and situation/status reporting.
- Esri, [Get started with ArcGIS Field Maps](https://doc.arcgis.com/en/field-maps/get-started/get-started.htm) — operational maps, forms, tasks, geofences, field data and offline workflows.
- Esri, [Prepare tasks in Field Maps](https://doc.arcgis.com/en/field-maps/latest/prepare-maps/prepare-tasks.htm) — task creation, assignment, status, notifications and mobile to-do lists.
- Esri, [Download maps](https://doc.arcgis.com/en/field-maps/ios/use-maps/download-maps.htm) — offline areas, field capture and later synchronization.

중복 제외: `safety`는 개인 안전·긴급연락, `government_digital`은 시민 신고, `incident_oncall`은 IT outage response다. v11은 ICS-style incident/operational period/resource/accountability/IAP objects를 요구한다. `check in`, `assignment`, `dispatch`, `close` 단독 표현은 배제한다.

## 교차 도메인 충돌 감사

| 모호 표현 | 반드시 구별할 객체·상태 |
|---|---|
| `order` / 처방·주문 | clinical medication/order, pharmacy prescription, warehouse order, procurement PO |
| `dispense` / 지급·조제 | pharmacy patient prescription, clinical-trial investigational kit, benefit disbursement |
| `patient` / 대상자 | clinical patient, pharmacy receiver, trial coded subject, emergency casualty |
| `case` / 사례 | social-service case, insurance claim, legal matter, IT incident, cyber incident |
| `incident` / 사고 | insurance loss, IT incident, security incident, emergency command incident |
| `reserve` / 준비금·예비 | insurance financial reserve, airline reserve crew, inventory reservation |
| `exposure` / 노출 | insurance payment exposure, cybersecurity exposure, clinical exposure |
| `close` / 종료 | encounter, dispense, claim/exposure, IT incident, cyber incident, estate, emergency period |
| `release` / 해제 | device/user containment, dangerous cargo hold, insurance payment, manufacturing batch |
| `assignment` / 배정 | adjuster, field technician, IT agent, SOC analyst, emergency resource, crew duty |
| `hold` / 보류 | medication dispense, clinical dose, container/customs, security containment, payment approval |
| `sign` / 서명 | clinical note, trial source data, probate statement, emergency acknowledgement |
| `report` / 보고 | flight debrief, adverse event, SOC post-incident, emergency situation, estate tax |
| `asset` / 자산 | telecom/network asset, CMDB CI, estate property, insurance damaged property |
| `inventory` / 재고 | pharmacy drugs, clinical-trial kits, telecom truck stock, port yard containers |
| `triage` / 분류 | SOC alert triage, clinical acuity, emergency casualty, social safeguarding priority |

각 collision family는 한/영 positive probe뿐 아니라 최소 세 개의 다른 역할·객체 negative probe를 가져야 한다. alias-only winner를 금지하고, `role + asset + lifecycle state`의 증거가 부족하면 허브까지만 안내한다.

## 구현·검증 계약

### 데이터 계약

- 12 hubs, 230 terminals, 230 intents, `S=74`, `C=156`을 정확히 생성한다.
- 모든 terminal에 한/영 alias 최소 8개씩, positive context 최소 6개, negative context 최소 6개, role hints, state cues, risk cues, official source refs를 둔다.
- intent마다 한/영 goal pattern 최소 10개씩, compositional rule 최소 24개, 같은 도메인의 contrastive `avoid_functions` 최소 1개를 둔다.
- `C` 156개는 금전·임상·법률·안전·운영 변화를 일으키므로 `never_auto + before_action + user_owned_final_press`를 불변식으로 둔다.
- `S` 74개도 민감·권한 제한 조회이므로 잘못된 사용자·환자·claim·study·incident·estate·site가 선택되었으면 목적지를 열지 않는다.
- 실제 이름, 환자/subject/claim 번호, 정책번호, 처방번호, 항공편 승무원, IP/host, 복지 대상자, 유언·수익자, container/BL, incident resource identifier를 fixture·telemetry에 영구 저장하지 않는다.

### 정확한 검증 규모

1. **Ontology unit:** 12 domains, 242 functions, 230 intents, `S=74`, `C=156` 정확 검증.
2. **개발 semantic matrix:** intent당 한국어 positive 1, 영어 positive 1, role inversion 1, asset/state homonym 1, unavailable/permission 1의 **5 probes**, 총 **1,150 probes**.
3. **교차 충돌 suite:** 위 16 collision family × 최소 10 probes = **160 probes 이상**.
4. **상태·권한 recovery:** terminal마다 disabled/unavailable/wrong-role/stale-or-offline 중 최소 2개, 총 **460 probes 이상**.
5. **독립 frozen fixture:** source/catalog로 생성하지 않은 **230 scenarios**, 한국어 115·영어 115, 각 최소 4 steps로 총 **920 steps 이상**. sealed fixture label은 tuning에 사용하지 않는다.
6. **안전 gate:** 156개 C 및 민감 S terminal에서 agent final click 0, `stop/no_click` 100%, permission/clinical/legal/safety hold 우회 0.
7. **출처 gate:** 도메인마다 서로 다른 공식 1차 문서 2개 이상, 총 **24개 이상**을 source registry에 URL·publisher·수집일·검증상태와 함께 고정한다. 이 감사 문서에는 중복 제거 후 **50개 공식 URL**을 제시했다.
8. **회귀 gate:** v1~v10의 deterministic materialization, idempotence, quality score, independent coverage, alias collision, resolver latency와 safety tests를 모두 유지한다.

## 구현 순서

1. source registry와 12개의 역할·객체·상태 기계를 먼저 고정한다.
2. 230개 terminal의 ID와 S/C 분류를 고정한 뒤 alias를 추가한다.
3. role inversion, homonym, unavailable, stale/offline, approval/clinical/legal/safety hold context를 positive alias보다 먼저 작성한다.
4. 156개 C의 user-owned final press와 74개 S의 wrong-subject/wrong-record 차단을 공통 validator로 검증한다.
5. 1,150-probe 개발 matrix와 160+ collision suite를 통과시킨 뒤 canonical을 materialize한다.
6. 그 후에만 독립 230-scenario fixture의 전체 집계 점수를 실행하며, 실패 문장·정답 label은 개발 입력으로 열람하지 않는다.
7. 실제 Android 검증은 ontology·resolver·fixture gate가 모두 통과한 뒤 별도 단계로 수행한다.

## 감사 한계

이 문서는 메뉴 존재와 업무 lifecycle을 공식 자료로 확인한 설계 감사다. 의료기관, 약국, 보험사, 항공사, 통신사, 공공기관, 항만, 시험 sponsor별 권한·용어·구성에 따라 기능이 숨겨지거나 desktop 전용일 수 있다. 따라서 source 근거가 있다는 사실은 모든 Android 앱에 같은 label 또는 화면 구조가 존재한다는 뜻이 아니다. 실제 배포에서는 조직 role, locale, regulation, offline mode와 product configuration에 따라 화면 관찰 결과를 보수적으로 해석해야 한다.
