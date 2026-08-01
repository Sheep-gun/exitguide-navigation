# Navigation ontology coverage gap audit — v12

감사 기준일: 2026-07-30
감사 기준선: v11 반영 예상 canonical **131개 도메인, 1,858개 기능, 1,700개 intent**
감사 범위: 공개된 독립 평가 fixture의 문장·정답·실패 결과를 열람하지 않고, v1~v11 catalog/source·coverage 문서와 아래 공식 1차 문서만 대조한 source-level 설계 감사

## 결론

v12에서는 기존 소비자 앱 중심 범위를 넘어, 역할·자산·상태를 함께 구분해야 하는 아래 12개 장기꼬리 전문 운영 도메인을 권장한다. 정확한 제안 규모는 **252개 기능(허브 12 + terminal 240), 240개 intent**이며, 반영 후 예상 누계는 **143개 도메인, 2,110개 기능, 1,940개 intent**다.

| 우선순위 | 도메인 ID | terminal | 허브 포함 기능 | intent | S | C |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `veterinary_practice_ops` | 20 | 21 | 20 | 6 | 14 |
| 2 | `dental_practice_ops` | 20 | 21 | 20 | 6 | 14 |
| 3 | `home_health_clinician_ops` | 20 | 21 | 20 | 5 | 15 |
| 4 | `aviation_maintenance_ops` | 20 | 21 | 20 | 6 | 14 |
| 5 | `rail_operations` | 20 | 21 | 20 | 7 | 13 |
| 6 | `freight_forwarding_customs_ops` | 20 | 21 | 20 | 7 | 13 |
| 7 | `utility_grid_field_ops` | 20 | 21 | 20 | 6 | 14 |
| 8 | `environmental_waste_ops` | 20 | 21 | 20 | 6 | 14 |
| 9 | `mining_site_safety_ops` | 20 | 21 | 20 | 6 | 14 |
| 10 | `election_administration` | 20 | 21 | 20 | 8 | 12 |
| 11 | `research_grants_administration` | 20 | 21 | 20 | 8 | 12 |
| 12 | `corrections_case_management_ops` | 20 | 21 | 20 | 7 | 13 |
| **합계** | **12개** | **240** | **252** | **240** | **78** | **162** |

`S`는 민감하거나 권한이 제한된 조회 목적지, `C`는 임상·금전·법률·안전·선거·시설·운영 상태를 바꾸는 결과적 목적지다. **240개 terminal 전부** `automation_policy=never_auto`, `stop_policy=before_action`, `user_owned_final_press=true`로 고정한다. 에이전트는 terminal 후보와 근거를 보여준 뒤 멈추며 마지막 누름은 항상 사용자가 수행한다. 특히 `C` 162개는 예외 없이 high risk이고 자동 실행·자동 확인·대체 버튼 우회를 허용하지 않는다.

## 공통 ID·개념 경로·안전 계약

- 허브 ID: `<domain>.hub`
- terminal ID: `<domain>.<terminal_key>`
- intent ID: `v12_<domain>_<terminal_key>`
- 아래 경로는 앱 이름, package, resource ID, 화면 좌표, 픽셀 위치, 고정 클릭 순서를 뜻하지 않는다. Android 접근성 트리·OCR·화면 상태에서 동적으로 찾을 **한/영 개념 route**다.
- terminal 확정에는 `role + governed asset + lifecycle state` 세 축 중 최소 두 축이 필요하다. 동일한 명사 하나나 버튼 alias 하나만으로 terminal을 확정하지 않는다.
- `disabled`, `unavailable`, `permission denied`, `wrong role`, `wrong record`, `stale/offline`, `approval required`, `clinical hold`, `safety hold`, `legal hold`, `regulatory hold`, `certification pending` 상태에서는 fail-closed한다.
- `C`는 `never_auto + before_action + user_owned_final_press`를 불변식으로 검증한다. `S`도 잘못된 대상·역할·기록이면 즉시 중단하며, 본 감사안에서는 일관성을 위해 같은 최종 누름 정책을 적용한다.

## 1. Veterinary practice operations (`veterinary_practice_ops`)

허브: `veterinary_practice_ops.hub` — 동물병원 진료 업무 / Veterinary practice work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `veterinary_practice_ops.patient_queue` | `v12_veterinary_practice_ops_patient_queue` | S | 진료 작업함 → 예약·대기·입원 동물 / Clinical queue → scheduled/waiting/hospitalized animal |
| `veterinary_practice_ops.animal_profile` | `v12_veterinary_practice_ops_animal_profile` | S | 보호자 계정 → 동물 환자 → 종·품종·식별정보 / Owner account → animal patient → species/breed/identity |
| `veterinary_practice_ops.vaccination_history` | `v12_veterinary_practice_ops_vaccination_history` | S | 동물 차트 → 예방접종 이력·다음 예정 / Animal chart → vaccination history/due date |
| `veterinary_practice_ops.diagnostic_results` | `v12_veterinary_practice_ops_diagnostic_results` | S | 동물 차트 → 검사 → 결과·참고범위 / Animal chart → diagnostics → result/reference range |
| `veterinary_practice_ops.appointment_schedule` | `v12_veterinary_practice_ops_appointment_schedule` | S | 일정 → 진료자·시설·동물 예약 / Schedule → clinician/facility/animal appointment |
| `veterinary_practice_ops.inventory_view` | `v12_veterinary_practice_ops_inventory_view` | S | 임상 재고 → 백신·의약품·소모품 상태 / Clinical inventory → vaccine/drug/supply status |
| `veterinary_practice_ops.owner_patient_register` | `v12_veterinary_practice_ops_owner_patient_register` | C | 보호자 → 신규 동물 → 식별·연락·동의 등록 / Owner → new animal → identity/contact/consent registration |
| `veterinary_practice_ops.encounter_note` | `v12_veterinary_practice_ops_encounter_note` | C | 동물 방문 → 진찰 → 임상 노트 기록 / Animal encounter → examination → clinical note |
| `veterinary_practice_ops.triage_record` | `v12_veterinary_practice_ops_triage_record` | C | 대기 동물 → 활력·중증도 → 분류 기록 / Waiting animal → vitals/acuity → record triage |
| `veterinary_practice_ops.vaccine_administer` | `v12_veterinary_practice_ops_vaccine_administer` | C | 예방접종 계획 → 동물·제품·로트 확인 → 투여 기록 / Vaccine plan → verify animal/product/lot → record administration |
| `veterinary_practice_ops.lab_order` | `v12_veterinary_practice_ops_lab_order` | C | 동물 차트 → 진단검사 → 검사 의뢰 / Animal chart → diagnostics → place laboratory order |
| `veterinary_practice_ops.specimen_collect` | `v12_veterinary_practice_ops_specimen_collect` | C | 검사 의뢰 → 동물·검체·용기 확인 → 채취 기록 / Diagnostic order → verify animal/specimen/container → record collection |
| `veterinary_practice_ops.diagnosis_problem_update` | `v12_veterinary_practice_ops_diagnosis_problem_update` | C | 동물 차트 → 문제·진단 → 추가·상태 변경 / Animal chart → problems/diagnoses → add/change status |
| `veterinary_practice_ops.treatment_plan_update` | `v12_veterinary_practice_ops_treatment_plan_update` | C | 방문 → 치료 계획 → 처치·모니터링 수정 / Encounter → treatment plan → update interventions/monitoring |
| `veterinary_practice_ops.prescription_issue` | `v12_veterinary_practice_ops_prescription_issue` | C | 동물 차트 → 처방 → 약·용량·기간 확인 → 발행 / Animal chart → prescription → verify drug/dose/duration → issue |
| `veterinary_practice_ops.controlled_drug_log` | `v12_veterinary_practice_ops_controlled_drug_log` | C | 규제 의약품 → 동물·처방·수량 → 사용 기록 / Controlled drug → animal/order/quantity → record use |
| `veterinary_practice_ops.procedure_record` | `v12_veterinary_practice_ops_procedure_record` | C | 처치 계획 → 동물·부위·동의 확인 → 완료 기록 / Procedure plan → verify animal/site/consent → record completion |
| `veterinary_practice_ops.hospitalization_handoff` | `v12_veterinary_practice_ops_hospitalization_handoff` | C | 입원 환자 → 치료·관찰·주의사항 → 교대 인계 / Inpatient animal → treatment/observation/alerts → shift handoff |
| `veterinary_practice_ops.health_certificate_prepare` | `v12_veterinary_practice_ops_health_certificate_prepare` | C | 동물 수출·이동 → 목적국 요건·검사·백신 → 증명서 제출 / Animal export/travel → destination requirements/exam/vaccine → submit certificate |
| `veterinary_practice_ops.encounter_close` | `v12_veterinary_practice_ops_encounter_close` | C | 방문 → 미결 처방·결과·지침 검토 → 진료 종료 / Encounter → review open orders/results/instructions → close |

역할·자산·상태: receptionist, veterinary technician, veterinarian, practice manager, accredited veterinarian 역할을 구분한다. 핵심 자산은 owner, animal patient, encounter, vaccine lot, diagnostic order, specimen, prescription, controlled drug, export certificate이며, `scheduled → checked-in → triaged → examined → ordered/collected/resulted → treated → discharged` 상태를 사용한다.

충돌군: `patient`(사람 환자/동물 환자), `owner`(보호자/업무 소유자), `vaccination history`(조회/실제 투여), `prescription`(발행/약국 조제), `certificate`(일반 문서/공인 수출 건강증명), `discharge`(진료 종료/결제)를 contrastive pair로 둔다.

공식 근거:

- USDA APHIS, [Veterinary Export Health Certification System](https://direct.aphis.usda.gov/pet-travel/vehcs) — 목적국 요건, 공인 수의사, 건강증명서 제출·승인 lifecycle.
- USDA APHIS, [Countries accepting VEHCS](https://www.aphis.usda.gov/live-animal-export/vehcs-countries) — 국가별 전자 제출·보증 범위와 예외.
- USDA APHIS, [Create a certificate](https://vehcs-training.aphis.usda.gov/VEHCSHelp/create_certificate.htm) — 동물, 목적지, 검사, 백신, 증명서 작성 흐름.
- FDA, [FDA regulation of animal drugs](https://www.fda.gov/animal-veterinary/resources-you/fda-regulation-animal-drugs) — 동물 의약품 승인·처방·사용 책임 경계.
- FDA, [Veterinary Feed Directive](https://www.fda.gov/animal-veterinary/development-approval-process/veterinary-feed-directive-vfd) — 수의사 지시, 발행, 기록 보존과 규제 대상 자산.

중복 제외: `clinical_care_team_ops`의 사람 환자·병원 처방 lifecycle과 분리한다. species, owner, veterinary accreditation, animal-drug rule, export-health certificate가 확인되지 않으면 이 도메인을 확정하지 않는다.

## 2. Dental practice operations (`dental_practice_ops`)

허브: `dental_practice_ops.hub` — 치과 진료 업무 / Dental practice work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `dental_practice_ops.schedule_board` | `v12_dental_practice_ops_schedule_board` | S | 예약표 → 진료자·체어·날짜 보기 / Appointment book → provider/chair/date view |
| `dental_practice_ops.patient_chart` | `v12_dental_practice_ops_patient_chart` | S | 환자 → 치과 차트·경고·병력 / Patient → dental chart/alerts/history |
| `dental_practice_ops.odontogram_review` | `v12_dental_practice_ops_odontogram_review` | S | 치과 차트 → 치아도 → 기존·계획 상태 / Dental chart → odontogram → existing/planned status |
| `dental_practice_ops.radiograph_review` | `v12_dental_practice_ops_radiograph_review` | S | 환자 → 영상 → 치과 방사선 이미지 / Patient → imaging → dental radiographs |
| `dental_practice_ops.periodontal_chart_review` | `v12_dental_practice_ops_periodontal_chart_review` | S | 치과 차트 → 치주 기록 → 과거 측정 / Dental chart → periodontal chart → prior measurements |
| `dental_practice_ops.treatment_plan_review` | `v12_dental_practice_ops_treatment_plan_review` | S | 환자 → 치료계획 → 단계·예상비용·상태 / Patient → treatment plan → phases/estimate/status |
| `dental_practice_ops.patient_register` | `v12_dental_practice_ops_patient_register` | C | 환자 목록 → 신규 환자 → 신원·연락·동의 등록 / Patient list → new patient → identity/contact/consent registration |
| `dental_practice_ops.appointment_book` | `v12_dental_practice_ops_appointment_book` | C | 예약표 → 시간·진료자·체어 → 예약 확정 / Appointment book → time/provider/chair → confirm booking |
| `dental_practice_ops.checkin_status` | `v12_dental_practice_ops_checkin_status` | C | 오늘 예약 → 환자 확인 → 도착·진료준비 상태 / Today's appointment → verify patient → arrived/ready status |
| `dental_practice_ops.medical_history_update` | `v12_dental_practice_ops_medical_history_update` | C | 환자 차트 → 병력·알레르기·약물 → 갱신 / Patient chart → medical history/allergies/medications → update |
| `dental_practice_ops.clinical_note_sign` | `v12_dental_practice_ops_clinical_note_sign` | C | 방문 → 임상 노트 → 검토·서명 / Encounter → clinical note → review/sign |
| `dental_practice_ops.odontogram_update` | `v12_dental_practice_ops_odontogram_update` | C | 치아도 → 치아·면·상태 확인 → 기록 / Odontogram → verify tooth/surface/condition → record |
| `dental_practice_ops.periodontal_chart_record` | `v12_dental_practice_ops_periodontal_chart_record` | C | 치주 기록 → 치아별 측정·출혈 → 저장 / Periodontal chart → tooth measurements/bleeding → record |
| `dental_practice_ops.procedure_post` | `v12_dental_practice_ops_procedure_post` | C | 치료계획 → 치아·면·코드 확인 → 시술 완료 반영 / Treatment plan → verify tooth/surface/code → post procedure |
| `dental_practice_ops.treatment_plan_present_accept` | `v12_dental_practice_ops_treatment_plan_present_accept` | C | 치료계획 → 단계·비용·대안 설명 → 수락 상태 / Treatment plan → phases/cost/options → acceptance status |
| `dental_practice_ops.consent_capture` | `v12_dental_practice_ops_consent_capture` | C | 계획 시술 → 환자·시술·위험 확인 → 동의 서명 / Planned procedure → verify patient/procedure/risks → capture consent |
| `dental_practice_ops.prescription_issue` | `v12_dental_practice_ops_prescription_issue` | C | 방문 → 처방 → 약·용량·기간 확인 → 발행 / Encounter → prescription → verify drug/dose/duration → issue |
| `dental_practice_ops.lab_case_order` | `v12_dental_practice_ops_lab_case_order` | C | 치료계획 → 기공물·치식·쉐이드·납기 → 의뢰 / Treatment plan → prosthesis/tooth/shade/due date → order lab case |
| `dental_practice_ops.sterilization_cycle_log` | `v12_dental_practice_ops_sterilization_cycle_log` | C | 감염관리 → 멸균기·적재·지표 → 주기 결과 기록 / Infection control → sterilizer/load/indicator → record cycle result |
| `dental_practice_ops.encounter_complete` | `v12_dental_practice_ops_encounter_complete` | C | 방문 → 기록·시술·지침 검토 → 진료 완료 / Encounter → review notes/procedures/instructions → complete |

역할·자산·상태: front desk, dental assistant, hygienist, dentist, infection-control coordinator 역할을 분리한다. 핵심 자산은 patient, appointment/chair, odontogram tooth-surface, periodontal measurement, radiograph, treatment plan, consent, lab case, sterilizer load이고 상태는 `planned → scheduled → arrived → seated → treated → posted/signed → completed`다.

충돌군: `chart`(일반 임상 차트/odontogram/periodontal chart), `surface`(UI 표면/치아 면), `plan`(조회/환자 수락), `post`(메시지 게시/시술 반영), `lab order`(진단검사/치과기공 의뢰), `cycle`(일정 반복/멸균 주기)을 구별한다.

공식 근거:

- Open Dental, [Manual](https://opendental.com/manual/manual.html) — appointment, patient chart, treatment plan, procedure, imaging, lab case 등 치과 업무 객체.
- Open Dental, [Appointments module](https://www.opendental.com/manual/appointments.html) — provider, operatory, appointment status와 예약 lifecycle.
- Open Dental, [Planned appointments](https://opendental.com/manual/apptplanned.html) — 치료계획과 계획 예약의 구분·전환.
- Open Dental, [Signed treatment plans](https://www.opendental.com/manual/treatmentplansign.html) — 치료계획 사본, 서명, 변경 통제.
- CDC, [Dental infection prevention and control](https://www.cdc.gov/dental-infection-control/index.html) — 치과 환경 감염관리 책임과 자산.
- CDC, [Sterilization and disinfection](https://www.cdc.gov/dental-infection-control/hcp/summary/sterilization-disinfection.html) — 기구 분류, 멸균, 모니터링과 기록 경계.

중복 제외: `clinical_care_team_ops`의 일반 encounter/order와 겹치는 단어가 있어도 tooth, surface, odontogram, periodontal chart, chair/operatory 또는 dental lab asset이 없으면 치과 terminal을 선택하지 않는다.

## 3. Home-health clinician operations (`home_health_clinician_ops`)

허브: `home_health_clinician_ops.hub` — 재가 방문 진료 업무 / Home-health clinician work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `home_health_clinician_ops.visit_schedule` | `v12_home_health_clinician_ops_visit_schedule` | S | 방문 일정 → 담당자·환자·방문 창 / Visit schedule → clinician/patient/service window |
| `home_health_clinician_ops.patient_care_plan` | `v12_home_health_clinician_ops_patient_care_plan` | S | 환자 → 재가 치료계획·목표·빈도 / Patient → home-health plan/goals/frequency |
| `home_health_clinician_ops.medication_profile` | `v12_home_health_clinician_ops_medication_profile` | S | 환자 → 약물 프로필·알레르기·고위험약 / Patient → medication profile/allergy/high-risk drugs |
| `home_health_clinician_ops.assessment_history` | `v12_home_health_clinician_ops_assessment_history` | S | 환자 → 평가 이력 → 시작·재인증·퇴원 / Patient → assessment history → start/recertification/discharge |
| `home_health_clinician_ops.task_supply_view` | `v12_home_health_clinician_ops_task_supply_view` | S | 오늘 방문 → 중재·과제·재료 목록 / Today's visit → interventions/tasks/supplies |
| `home_health_clinician_ops.visit_checkin_evv` | `v12_home_health_clinician_ops_visit_checkin_evv` | C | 예정 방문 → 환자·서비스·위치 확인 → 방문 시작 / Scheduled visit → verify patient/service/location → EVV check-in |
| `home_health_clinician_ops.identity_location_verify` | `v12_home_health_clinician_ops_identity_location_verify` | C | 방문 세션 → 환자·주소·담당자 확인 → 현장 검증 / Visit session → verify patient/address/caregiver → confirm presence |
| `home_health_clinician_ops.start_oasis_assessment` | `v12_home_health_clinician_ops_start_oasis_assessment` | C | 환자 에피소드 → 평가 시점·사유 확인 → OASIS 시작 / Patient episode → verify time point/reason → start OASIS |
| `home_health_clinician_ops.vital_symptom_record` | `v12_home_health_clinician_ops_vital_symptom_record` | C | 방문 → 활력·증상·통증 → 기록 / Visit → vitals/symptoms/pain → record |
| `home_health_clinician_ops.medication_reconciliation` | `v12_home_health_clinician_ops_medication_reconciliation` | C | 가정 내 약물 → 처방·복용·차이 확인 → 조정 기록 / Home medications → compare orders/use/discrepancies → reconcile |
| `home_health_clinician_ops.medication_administration_record` | `v12_home_health_clinician_ops_medication_administration_record` | C | 방문 투약 → 환자·약·용량·시간 확인 → 투약 기록 / Visit medication → verify patient/drug/dose/time → record administration |
| `home_health_clinician_ops.wound_assessment` | `v12_home_health_clinician_ops_wound_assessment` | C | 환자 → 상처 → 부위·크기·상태·사진 기록 / Patient → wound → site/size/condition/photo assessment |
| `home_health_clinician_ops.intervention_complete` | `v12_home_health_clinician_ops_intervention_complete` | C | 방문 과제 → 처치·교육·반응 → 완료 기록 / Visit task → intervention/education/response → complete |
| `home_health_clinician_ops.care_plan_update` | `v12_home_health_clinician_ops_care_plan_update` | C | 치료계획 → 목표·빈도·중재 → 변경 요청 / Care plan → goals/frequency/interventions → request update |
| `home_health_clinician_ops.physician_order_request` | `v12_home_health_clinician_ops_physician_order_request` | C | 환자 에피소드 → 변경 필요·근거 → 의사 지시 요청 / Patient episode → change need/evidence → request physician order |
| `home_health_clinician_ops.aide_task_update` | `v12_home_health_clinician_ops_aide_task_update` | C | 보조인력 계획 → 과제·빈도·예외 → 상태 갱신 / Aide plan → task/frequency/exception → update status |
| `home_health_clinician_ops.incident_report` | `v12_home_health_clinician_ops_incident_report` | C | 방문 → 낙상·투약·안전 사건 → 보고 / Visit → fall/medication/safety event → submit incident report |
| `home_health_clinician_ops.visit_note_sign` | `v12_home_health_clinician_ops_visit_note_sign` | C | 방문 기록 → 필수항목·예외 검토 → 서명 / Visit note → completeness/exceptions review → sign |
| `home_health_clinician_ops.visit_checkout_evv` | `v12_home_health_clinician_ops_visit_checkout_evv` | C | 진행 방문 → 수행 서비스·시간·위치 확인 → 종료 / Active visit → verify service/time/location → EVV check-out |
| `home_health_clinician_ops.transfer_discharge` | `v12_home_health_clinician_ops_transfer_discharge` | C | 환자 에피소드 → 상태·미결 과제·인계 검토 → 전원·퇴원 / Patient episode → review status/open tasks/handoff → transfer/discharge |

역할·자산·상태: scheduler, home-health aide, nurse, therapist, ordering practitioner, clinical supervisor 역할을 구별한다. 핵심 자산은 patient episode, scheduled visit, EVV event, OASIS assessment, medication list, wound, aide task, plan of care, physician order이고 상태는 `scheduled → arrived/verified → assessing → providing care → documenting → signed → checked-out → transferred/discharged`다.

충돌군: `check in`(일반 출석/법정 EVV), `assessment`(일반 설문/OASIS 시점), `order`(의사 지시/상품 주문), `administration`(계정 관리/투약), `discharge`(병원 퇴원/재가 episode 종료), `location`(지도 보기/서비스 검증)을 구별한다.

공식 근거:

- CMS, [OASIS data specifications](https://www.cms.gov/medicare/quality/home-health/data-specifications) — OASIS item, data submission, assessment time point 구조.
- CMS, [OASIS data sets](https://www.cms.gov/medicare/quality/home-health/oasis-data-sets) — start/resumption/recertification/transfer/discharge 평가 범위.
- CMS, [Home Health Quality Reporting requirements](https://www.cms.gov/medicare/quality/home-health/home-health-quality-reporting-requirements) — 평가·보고 의무와 품질 데이터 경계.
- CMS, [Home Health Agencies guidance](https://www.cms.gov/medicare/health-safety-standards/guidance-for-laws-regulations/home-health-agencies) — plan of care, clinical record, patient rights, supervision 기준.
- Medicaid.gov, [Electronic Visit Verification](https://www.medicaid.gov/medicaid/home-community-based-services/home-community-based-services-guidance-additional-resources/electronic-visit-verification) — 서비스 유형, 대상자, 제공자, 날짜, 위치, 시작·종료 시간 데이터.
- HL7, [MedicationAdministration](https://hl7.org/fhir/medicationadministration.html) — 투약 사건, 대상, 약, 시간, 상태와 기록 모델.

중복 제외: `clinical_care_team_ops`의 시설 내 encounter와 달리 home address, service window, EVV, OASIS, home-health episode 또는 aide plan 증거가 필요하다. 일반 위치 체크인만으로 EVV를 추정하지 않는다.

## 4. Aviation maintenance operations (`aviation_maintenance_ops`)

허브: `aviation_maintenance_ops.hub` — 항공 정비 업무 / Aviation maintenance work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `aviation_maintenance_ops.aircraft_status` | `v12_aviation_maintenance_ops_aircraft_status` | S | 항공기 fleet → 등록기호·구성·운항 가능 상태 / Aircraft fleet → tail/configuration/serviceability status |
| `aviation_maintenance_ops.maintenance_program_due_list` | `v12_aviation_maintenance_ops_maintenance_program_due_list` | S | 항공기 → 정비 프로그램 → 시간·사이클·달력 기한 / Aircraft → maintenance program → hour/cycle/calendar due list |
| `aviation_maintenance_ops.work_package_review` | `v12_aviation_maintenance_ops_work_package_review` | S | 정비 방문 → work package → 작업·순서·상태 / Maintenance visit → work package → tasks/sequence/status |
| `aviation_maintenance_ops.deferred_defect_review` | `v12_aviation_maintenance_ops_deferred_defect_review` | S | 항공기 → 결함 → 이연 항목·제한·만료 / Aircraft → defects → deferred item/restriction/expiry |
| `aviation_maintenance_ops.parts_tool_availability` | `v12_aviation_maintenance_ops_parts_tool_availability` | S | 정비 작업 → 자재·공구 → 가용·예약·교정 상태 / Maintenance task → parts/tools → available/reserved/calibration status |
| `aviation_maintenance_ops.technical_record_review` | `v12_aviation_maintenance_ops_technical_record_review` | S | 항공기 기록 → 로그·정비 이력·release 문서 / Aircraft records → log/history/release documents |
| `aviation_maintenance_ops.defect_record` | `v12_aviation_maintenance_ops_defect_record` | C | 항공기·구성품 → 발견 결함·근거·운항 영향 → 등록 / Aircraft/component → defect/evidence/operational impact → record |
| `aviation_maintenance_ops.work_order_create` | `v12_aviation_maintenance_ops_work_order_create` | C | 결함·정비요건 → 항공기·우선순위·범위 → 작업지시 생성 / Defect/requirement → aircraft/priority/scope → create work order |
| `aviation_maintenance_ops.work_package_release` | `v12_aviation_maintenance_ops_work_package_release` | C | 정비 방문 → 작업·자원·승인 확인 → package release / Maintenance visit → verify tasks/resources/approval → release package |
| `aviation_maintenance_ops.job_card_start` | `v12_aviation_maintenance_ops_job_card_start` | C | work package → job card → 항공기·구역·개정 확인 → 시작 / Work package → job card → verify aircraft/zone/revision → start |
| `aviation_maintenance_ops.task_step_signoff` | `v12_aviation_maintenance_ops_task_step_signoff` | C | job card → 수행 단계·측정값·기술자 → step sign-off / Job card → step/measurement/technician → sign off |
| `aviation_maintenance_ops.inspection_required_item_signoff` | `v12_aviation_maintenance_ops_inspection_required_item_signoff` | C | 필수검사 항목 → 독립 검사자·결과 → 승인 / Required inspection item → independent inspector/result → sign off |
| `aviation_maintenance_ops.part_install_remove` | `v12_aviation_maintenance_ops_part_install_remove` | C | 항공기 구성 → 위치·부품·일련번호 확인 → 탈거·장착 / Aircraft configuration → verify position/part/serial → remove/install |
| `aviation_maintenance_ops.life_limited_part_update` | `v12_aviation_maintenance_ops_life_limited_part_update` | C | 수명제한 부품 → 시간·사이클·잔여수명 → 기록 갱신 / Life-limited part → hours/cycles/remaining life → update record |
| `aviation_maintenance_ops.tool_calibration_issue` | `v12_aviation_maintenance_ops_tool_calibration_issue` | C | 정비 작업 → 공구·교정 상태 → 사용 차단·예외 등록 / Maintenance task → tool/calibration status → block use/record exception |
| `aviation_maintenance_ops.nonroutine_work_create` | `v12_aviation_maintenance_ops_nonroutine_work_create` | C | 수행 중 발견사항 → 결함·참조·범위 → 비정기 작업 생성 / Finding during work → defect/reference/scope → create non-routine work |
| `aviation_maintenance_ops.defect_defer_clear` | `v12_aviation_maintenance_ops_defect_defer_clear` | C | 활성 결함 → 기준·제한·수정조치 검토 → 이연·해제 / Active defect → review basis/restrictions/correction → defer/clear |
| `aviation_maintenance_ops.maintenance_release_to_service` | `v12_aviation_maintenance_ops_maintenance_release_to_service` | C | 정비 기록 → 완료·검사·구성·권한 확인 → 운항 복귀 승인 / Maintenance record → verify completion/inspection/configuration/authority → release to service |
| `aviation_maintenance_ops.work_order_close` | `v12_aviation_maintenance_ops_work_order_close` | C | 작업지시 → 미결 단계·자재·결함 검토 → 종료 / Work order → review open steps/materials/defects → close |
| `aviation_maintenance_ops.shift_handover` | `v12_aviation_maintenance_ops_shift_handover` | C | 정비 교대 → 항공기·열린 작업·위험·공구 → 인계 / Maintenance shift → aircraft/open work/hazards/tools → handoff |

역할·자산·상태: planner, mechanic, inspector, certifying staff, material controller, maintenance controller 역할을 구분한다. 핵심 자산은 aircraft/tail, configuration position, component serial, defect, work order, work package, job card revision, required inspection item, calibrated tool, release record이고 상태는 `due → planned → released → in-progress → inspected → signed → deferred/cleared → released-to-service → closed`다.

충돌군: `release`(작업 package 배포/항공기 운항 복귀), `defer`(일반 미루기/승인된 결함 이연), `part`(상품/추적 구성품), `inspection`(단순 조회/독립 필수검사 승인), `close`(화면 닫기/work order 종결), `cycle`(UI 반복/항공기 운항 사이클)을 구별한다.

공식 근거:

- IBM, [Maximo Aviation overview](https://www.ibm.com/docs/en/maximo-for-aviation/8.1.0_cd?topic=product-overview) — aircraft configuration, maintenance, materials, regulatory records 객체.
- IBM, [Work packages](https://www.ibm.com/docs/en/maximo-for-aviation/cd?topic=packages-work) — 작업지시 묶음, 순서, 상태, release·completion lifecycle.
- IBM, [Creating work orders](https://www.ibm.com/docs/en/maximo-for-aviation/7.6.8?topic=orders-creating-work) — 자산·위치·작업 유형·우선순위 기반 work order 생성.
- IBM, [Job cards](https://www.ibm.com/docs/en/maximo-for-aviation/cd?topic=work-job-cards) — task steps, labor, materials, tools, revision-controlled 작업 지침.
- EASA, [Easy Access Rules for Continuing Airworthiness](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-continuing-airworthiness?erules-id=ERULES-1963177438-774) — 정비조직, 기록, 부품, release-to-service 권한 경계.
- FAA, [Aviation Maintenance Technician Handbook](https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/amtg_handbook.pdf) — 검사, 작업 수행, 공구, 기록과 안전 원칙.
- FAA, [AC 43-9C — Maintenance Records](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_43-9C_CHG_1.pdf) — 정비기록 내용, 서명, 승인·반환 상태.

중복 제외: `maintenance_asset_ops`의 일반 설비 work order와 달리 aircraft identity, configuration/serial traceability, airworthiness basis, independent inspection 또는 release-to-service authority가 확인돼야 한다.

## 5. Rail operations (`rail_operations`)

허브: `rail_operations.hub` — 철도 운행·선로 업무 / Rail operations work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `rail_operations.operating_plan` | `v12_rail_operations_operating_plan` | S | 운영 구역 → 열차·선로·작업 계획 / Operating territory → train/track/work plan |
| `rail_operations.train_consist` | `v12_rail_operations_train_consist` | S | 열차 → 기관차·차량·위험물 consist / Train → locomotive/car/hazardous-material consist |
| `rail_operations.timetable_authority_view` | `v12_rail_operations_timetable_authority_view` | S | 운행 문서 → 시간표·bulletin·movement authority / Operating documents → timetable/bulletin/movement authority |
| `rail_operations.track_condition_view` | `v12_rail_operations_track_condition_view` | S | 선로 구간 → 검사·결함·제한 상태 / Track segment → inspection/defect/restriction status |
| `rail_operations.signal_status_view` | `v12_rail_operations_signal_status_view` | S | 신호 구역 → signal/control point 상태 / Signal territory → signal/control-point status |
| `rail_operations.equipment_inspection_due` | `v12_rail_operations_equipment_inspection_due` | S | 철도차량 → 검사·시험 기한 / Rolling stock → inspection/test due status |
| `rail_operations.crew_qualification_view` | `v12_rail_operations_crew_qualification_view` | S | 승무·작업자 → 노선·장비·보호 자격 / Crew/worker → territory/equipment/protection qualification |
| `rail_operations.train_makeup_confirm` | `v12_rail_operations_train_makeup_confirm` | C | 열차 consist → 차량 순서·중량·위험물 확인 → 구성 확정 / Train consist → verify order/weight/hazmat → confirm makeup |
| `rail_operations.brake_test_record` | `v12_rail_operations_brake_test_record` | C | 출발 열차 → 시험 유형·차량·결과 → 제동시험 기록 / Departing train → test type/cars/result → record brake test |
| `rail_operations.track_inspection_record` | `v12_rail_operations_track_inspection_record` | C | 선로 구간 → 검사 범위·측정·결함 → 기록 / Track segment → scope/measurement/defect → record inspection |
| `rail_operations.defect_restriction_issue` | `v12_rail_operations_defect_restriction_issue` | C | 선로 결함 → 위치·등급·영향 → 운행 제한 발행 / Track defect → location/class/impact → issue restriction |
| `rail_operations.roadway_worker_authority` | `v12_rail_operations_roadway_worker_authority` | C | 선로 작업 → 담당자·작업한계·보호수단 → 작업권한 설정 / Roadway work → person-in-charge/limits/protection → establish authority |
| `rail_operations.switch_position_confirm` | `v12_rail_operations_switch_position_confirm` | C | 운행 경로 → switch·위치·잠금 확인 → 상태 확정 / Movement route → verify switch/position/lock → confirm state |
| `rail_operations.signal_test_record` | `v12_rail_operations_signal_test_record` | C | 신호 설비 → 시험 절차·측정·결과 → 기록 / Signal equipment → procedure/measurement/result → record test |
| `rail_operations.movement_authority_ack` | `v12_rail_operations_movement_authority_ack` | C | 열차·작업차량 → authority·한계·조건 → 수신 확인 / Train/on-track equipment → authority/limits/conditions → acknowledge |
| `rail_operations.speed_restriction_issue` | `v12_rail_operations_speed_restriction_issue` | C | 선로·기상·작업 조건 → 구간·속도·유효시간 → 제한 발행 / Track/weather/work condition → segment/speed/validity → issue restriction |
| `rail_operations.equipment_bad_order` | `v12_rail_operations_equipment_bad_order` | C | 차량·기관차 → 결함·운행조건 → 사용제한 표시 / Rail vehicle → defect/movement condition → mark bad order |
| `rail_operations.dispatch_route_set` | `v12_rail_operations_dispatch_route_set` | C | 관제 구역 → 열차·선로·충돌검사 → 경로 설정 / Dispatch territory → train/track/conflict check → set route |
| `rail_operations.incident_report` | `v12_rail_operations_incident_report` | C | 철도 사건 → 열차·위치·인명·설비 영향 → 보고 / Rail incident → train/location/person/equipment impact → report |
| `rail_operations.shift_handover` | `v12_rail_operations_shift_handover` | C | 관제·현장 교대 → 열차·권한·제한·미결 작업 → 인계 / Dispatch/field shift → trains/authorities/restrictions/open work → handoff |

역할·자산·상태: dispatcher, train crew, mechanical inspector, track inspector, roadway worker in charge, signal maintainer 역할을 분리한다. 핵심 자산은 train/consist, locomotive/car, track segment, switch, signal/control point, movement authority, restriction, work zone이고 상태는 `planned → authorized/protected → inspected/tested → active movement/work → restricted/cleared → handed off`다.

충돌군: `authority`(계정 권한/열차·작업 이동권한), `route`(UI navigation/관제 경로), `switch`(설정 토글/선로 전철기), `consist`(일관성/열차 편성), `restriction`(앱 권한/운행 제한), `bad order`(잘못된 주문/사용제한 차량)를 구별한다.

공식 근거:

- FRA, [Operating Practices](https://railroads.dot.gov/railroad-safety/divisions/operating-practices/operating-practices-0) — 운행규칙, 승무자, 제동시험, train handling 책임.
- FRA, [Track](https://railroads.dot.gov/railroad-safety/divisions/track/track) — 선로검사, 결함, 등급과 안전기준.
- FRA, [Roadway Worker Protection](https://railroads.dot.gov/railroad-safety/divisions/roadway-worker-protection) — 작업한계, on-track safety, 담당자와 보호 절차.
- FRA, [Motive Power and Equipment](https://railroads.dot.gov/railroad-safety/divisions/motive-power-and-equipment) — 기관차·차량 검사, 시험, 결함 상태.
- FRA, [Signal and Train Control](https://railroads.dot.gov/railroad-safety/divisions/signal-and-train-control) — signal, control point, train-control system 검사와 운영.
- FTA, [Transit Asset Management Guide supplement](https://www.transit.dot.gov/sites/fta.dot.gov/files/docs/research-innovation/133701/asset-management-guide-supplement-asset-category-overviews-and-lifecycle-management-update-fta0138.pdf) — guideway, signal, vehicle 자산 lifecycle과 상태관리.

중복 제외: `transportation`의 승객 여정과 `logistics_shipment`의 화물추적이 아니라 dispatcher/crew/maintainer 역할, train consist, track authority, switch/signal, rolling-stock inspection이 결합된 운영 목적지만 소유한다.

## 6. Freight forwarding and customs operations (`freight_forwarding_customs_ops`)

허브: `freight_forwarding_customs_ops.hub` — 국제운송 주선·통관 업무 / Freight forwarding and customs work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `freight_forwarding_customs_ops.shipment_dashboard` | `v12_freight_forwarding_customs_ops_shipment_dashboard` | S | 국제화물 작업함 → 담당·운송수단·예외 필터 / International shipment queue → owner/mode/exception filter |
| `freight_forwarding_customs_ops.booking_detail` | `v12_freight_forwarding_customs_ops_booking_detail` | S | shipment → carrier booking·space·cutoff / Shipment → carrier booking/space/cutoff |
| `freight_forwarding_customs_ops.document_checklist` | `v12_freight_forwarding_customs_ops_document_checklist` | S | shipment → invoice·packing list·permit·certificate 상태 / Shipment → invoice/packing list/permit/certificate status |
| `freight_forwarding_customs_ops.tariff_classification_review` | `v12_freight_forwarding_customs_ops_tariff_classification_review` | S | 상품 품목 → tariff code·description·origin 근거 / Goods item → tariff code/description/origin basis |
| `freight_forwarding_customs_ops.customs_status` | `v12_freight_forwarding_customs_ops_customs_status` | S | declaration·entry → 접수·심사·release 상태 / Declaration/entry → accepted/review/release status |
| `freight_forwarding_customs_ops.hold_exam_status` | `v12_freight_forwarding_customs_ops_hold_exam_status` | S | consignment → hold·검사·문서요청 상태 / Consignment → hold/exam/document-request status |
| `freight_forwarding_customs_ops.milestone_tracking` | `v12_freight_forwarding_customs_ops_milestone_tracking` | S | shipment → 인수·출발·도착·통관·인도 event / Shipment → receipt/departure/arrival/clearance/delivery events |
| `freight_forwarding_customs_ops.booking_create` | `v12_freight_forwarding_customs_ops_booking_create` | C | shipment plan → carrier·route·equipment·cutoff → booking 요청 / Shipment plan → carrier/route/equipment/cutoff → request booking |
| `freight_forwarding_customs_ops.shipper_consignee_update` | `v12_freight_forwarding_customs_ops_shipper_consignee_update` | C | shipment parties → shipper·consignee·notify party 확인 → 갱신 / Shipment parties → verify shipper/consignee/notify party → update |
| `freight_forwarding_customs_ops.house_waybill_issue` | `v12_freight_forwarding_customs_ops_house_waybill_issue` | C | consignment → parties·pieces·weight·route → house waybill 발행 / Consignment → parties/pieces/weight/route → issue house waybill |
| `freight_forwarding_customs_ops.cargo_manifest_submit` | `v12_freight_forwarding_customs_ops_cargo_manifest_submit` | C | conveyance·consignments → cargo report 검증 → manifest 제출 / Conveyance/consignments → validate cargo report → submit manifest |
| `freight_forwarding_customs_ops.customs_declaration_submit` | `v12_freight_forwarding_customs_ops_customs_declaration_submit` | C | goods shipment → 품목·가치·원산지·절차 → declaration 제출 / Goods shipment → items/value/origin/procedure → submit declaration |
| `freight_forwarding_customs_ops.supporting_document_submit` | `v12_freight_forwarding_customs_ops_supporting_document_submit` | C | declaration 요청 → 문서 유형·연결 항목 → 증빙 제출 / Declaration request → document type/linked item → submit evidence |
| `freight_forwarding_customs_ops.duty_tax_payment_authorize` | `v12_freight_forwarding_customs_ops_duty_tax_payment_authorize` | C | entry summary → duty·tax·account·금액 확인 → 납부 승인 / Entry summary → verify duty/tax/account/amount → authorize payment |
| `freight_forwarding_customs_ops.inspection_response` | `v12_freight_forwarding_customs_ops_inspection_response` | C | customs exam → 요청·화물 위치·예약 → 검사 응답 / Customs exam → request/cargo location/appointment → respond |
| `freight_forwarding_customs_ops.hold_release_request` | `v12_freight_forwarding_customs_ops_hold_release_request` | C | held consignment → 사유·보완·기관 확인 → release 요청 / Held consignment → reason/remediation/agency → request release |
| `freight_forwarding_customs_ops.dangerous_goods_declaration` | `v12_freight_forwarding_customs_ops_dangerous_goods_declaration` | C | cargo item → UN번호·등급·포장·수량 → 위험물 declaration / Cargo item → UN number/class/packing/quantity → declare dangerous goods |
| `freight_forwarding_customs_ops.transport_instruction_issue` | `v12_freight_forwarding_customs_ops_transport_instruction_issue` | C | confirmed booking → pickup·route·handling·delivery → 운송지시 발행 / Confirmed booking → pickup/route/handling/delivery → issue transport instruction |
| `freight_forwarding_customs_ops.delivery_order_release` | `v12_freight_forwarding_customs_ops_delivery_order_release` | C | arrived shipment → customs·charges·title 확인 → delivery order release / Arrived shipment → verify customs/charges/title → release delivery order |
| `freight_forwarding_customs_ops.shipment_close` | `v12_freight_forwarding_customs_ops_shipment_close` | C | delivered shipment → 미결 문서·비용·예외 검토 → file close / Delivered shipment → review open documents/costs/exceptions → close file |

역할·자산·상태: shipper, freight forwarder, customs broker/declarant, carrier, consignee, customs/PGA reviewer 역할을 구분한다. 핵심 자산은 GoodsShipment, Consignment, BorderTransportMeans, booking, house/master waybill, goods item, declaration/entry, manifest, LPCO, hold/exam, delivery order이며 상태는 `planned → booked → documented → manifested/declared → accepted/held/examined → released → delivered → closed`다.

충돌군: `entry`(로그인 진입/세관 entry), `release`(소프트웨어 배포/화물 반출), `declaration`(설정 선언/법적 통관신고), `manifest`(앱 manifest/cargo manifest), `consignment`(소매 위탁/운송계약 화물), `classification`(ML 분류/tariff code), `hold`(UI 보류/규제 보류)를 구별한다.

공식 근거:

- U.S. CBP, [How to Use the Automated Commercial Environment](https://www.cbp.gov/trade/automated/how-to-use-ace) — manifest, cargo release, entry summary, protest, supporting documents, post-release 기능.
- U.S. CBP, [Entry Summary and Post-Release Process](https://www.help.cbp.gov/s/article/Article-1643?language=en_US) — arrival, entry, cargo release, entry summary, duty payment 상태 흐름.
- WCO, [WCO Data Model](https://www.wcoomd.org/DataModel) — goods declaration, cargo report, transit, inspection, permit의 표준 객체.
- WCO, [Data Model eHandbook 3.10](https://www.wcoomd.org/Topics/Facilitation/Instrument%20and%20Tools/Tools/Data%20Model/eHandbook/eHandbook%20v3_10_0) — Declaration, LPCO, response, metadata 정보 패키지.
- WCO, [Main class level guidance](https://wiki-datamodel.wcoomd.org/en/technical-guide/guidance-on-using-Main-Class-Levels) — GoodsShipment, Consignment, BorderTransportMeans 역할 분리.
- IATA, [ONE Record](https://www.iata.org/en/programs/cargo/e/one-record/) — shipment, logistics object, event, participant의 표준 데이터 공유.
- IATA, [e-Freight and e-AWB](https://www.iata.org/en/programs/cargo/e/efreight/) — 항공화물 운송장과 디지털 문서 lifecycle.

중복 제외: `maritime_port_logistics`의 berth/yard/crane/container execution 및 `warehouse_fulfillment_ops`의 SKU pick-pack-ship과 분리한다. v12는 cross-border consignment, transport document, customs declaration, regulatory response와 release lifecycle만 소유한다.

## 7. Utility outage and grid field operations (`utility_grid_field_ops`)

허브: `utility_grid_field_ops.hub` — 전력망 장애·현장 복구 업무 / Utility outage and grid field work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `utility_grid_field_ops.outage_map` | `v12_utility_grid_field_ops_outage_map` | S | 운영 구역 → outage·영향 고객·복구 예상 지도 / Operating area → outage/customers affected/estimated restoration map |
| `utility_grid_field_ops.work_queue` | `v12_utility_grid_field_ops_work_queue` | S | 현장 작업함 → 우선순위·crew·상태 필터 / Field work queue → priority/crew/status filter |
| `utility_grid_field_ops.asset_network_view` | `v12_utility_grid_field_ops_asset_network_view` | S | 배전망 → feeder·switch·transformer·meter topology / Distribution network → feeder/switch/transformer/meter topology |
| `utility_grid_field_ops.switching_plan_review` | `v12_utility_grid_field_ops_switching_plan_review` | S | outage·작업 → switching plan·순서·승인 상태 / Outage/work → switching plan/steps/approval status |
| `utility_grid_field_ops.crew_location_status` | `v12_utility_grid_field_ops_crew_location_status` | S | 복구 자원 → crew·차량·staging·배정 상태 / Restoration resources → crew/vehicle/staging/assignment status |
| `utility_grid_field_ops.meter_service_history` | `v12_utility_grid_field_ops_meter_service_history` | S | service point → meter·disconnect·reconnect 이력 / Service point → meter/disconnect/reconnect history |
| `utility_grid_field_ops.outage_ticket_create` | `v12_utility_grid_field_ops_outage_ticket_create` | C | 고객·설비 신호 → 위치·범위·시각 확인 → outage 생성 / Customer/asset signal → verify location/scope/time → create outage |
| `utility_grid_field_ops.dispatch_accept` | `v12_utility_grid_field_ops_dispatch_accept` | C | field assignment → crew·현장·작업범위·연락 → 수락 / Field assignment → crew/site/scope/contact → accept dispatch |
| `utility_grid_field_ops.hazard_assessment` | `v12_utility_grid_field_ops_hazard_assessment` | C | 현장 도착 → 전기·교통·기상·공중 위험 → 평가 기록 / Site arrival → electrical/traffic/weather/overhead hazards → record assessment |
| `utility_grid_field_ops.field_arrival_checkin` | `v12_utility_grid_field_ops_field_arrival_checkin` | C | 배정 작업 → crew·설비·위치 확인 → 현장 도착 / Assigned work → verify crew/asset/location → check in on site |
| `utility_grid_field_ops.isolate_deenergize_request` | `v12_utility_grid_field_ops_isolate_deenergize_request` | C | 작업 설비 → source·boundary·영향 확인 → 격리·무전압 요청 / Work asset → verify source/boundary/impact → request isolation/de-energization |
| `utility_grid_field_ops.switching_step_confirm` | `v12_utility_grid_field_ops_switching_step_confirm` | C | 승인 switching plan → 설비·단계·현재상태 확인 → step 확인 / Approved switching plan → verify device/step/current state → confirm step |
| `utility_grid_field_ops.lockout_tagout_record` | `v12_utility_grid_field_ops_lockout_tagout_record` | C | 격리점 → lock·tag·담당자·검증 → 에너지 제어 기록 / Isolation point → lock/tag/worker/verification → record energy control |
| `utility_grid_field_ops.meter_disconnect_reconnect` | `v12_utility_grid_field_ops_meter_disconnect_reconnect` | C | service point → 고객·meter·권한·상태 확인 → 차단·재연결 / Service point → verify customer/meter/authority/state → disconnect/reconnect |
| `utility_grid_field_ops.repair_work_record` | `v12_utility_grid_field_ops_repair_work_record` | C | 손상 설비 → 부품·작업·시험 → 수리 완료 기록 / Damaged asset → parts/work/test → record repair completion |
| `utility_grid_field_ops.vegetation_clearance_record` | `v12_utility_grid_field_ops_vegetation_clearance_record` | C | 선로 구간 → 식생·접근·안전거리 → 정비 기록 / Line segment → vegetation/access/clearance → record maintenance |
| `utility_grid_field_ops.restoration_test_record` | `v12_utility_grid_field_ops_restoration_test_record` | C | 수리 설비 → 절연·위상·전압·보호 시험 → 결과 기록 / Repaired asset → insulation/phase/voltage/protection test → record result |
| `utility_grid_field_ops.energization_authorize` | `v12_utility_grid_field_ops_energization_authorize` | C | isolated network → 인원·접지·보호·부하 확인 → 재가압 승인 / Isolated network → verify personnel/grounds/protection/load → authorize energization |
| `utility_grid_field_ops.customer_restoration_update` | `v12_utility_grid_field_ops_customer_restoration_update` | C | outage segment → 복구 범위·잔여 고객·예상시간 → 상태 갱신 / Outage segment → restored scope/remaining customers/ETA → update status |
| `utility_grid_field_ops.work_close_handoff` | `v12_utility_grid_field_ops_work_close_handoff` | C | 현장 작업 → 미결 위험·설비상태·자재·crew 확인 → 종료·인계 / Field work → review hazards/asset state/materials/crew → close/handoff |

역할·자산·상태: control-room operator, dispatcher, line crew, field supervisor, meter technician, vegetation crew 역할을 구별한다. 핵심 자산은 outage event, feeder/circuit, switch, transformer, service point/meter, crew/vehicle, switching plan, isolation point, work order이고 상태는 `detected → assessed → dispatched → isolated/de-energized → repaired/tested → authorized → energized/restored → closed`다.

충돌군: `outage`(서비스 장애/전력 계통 사고), `switch`(UI toggle/전력 개폐기), `disconnect`(세션 종료/계량 서비스 차단), `isolate`(보안 격리/전기적 격리), `restore`(백업 복원/고객 전력 복구), `ground`(토지/접지), `energize`(동기부여/실제 가압)를 구별한다.

공식 근거:

- U.S. DOE, [Form OE-417](https://doe417.energy.gov/files/DOE-417_Form.pdf) — 전력 사고, 영향 설비·고객, 복구 예상시각, 완화 조치 보고 필드.
- U.S. DOE, [Mutual Assistance Guidance](https://www.energy.gov/sites/default/files/2023-12/Mutual%20Assistance%20Drop-in_FINAL_508%20%281%29.pdf) — 복구 crew·차량·변압기 요청, 배치와 상호지원 조정.
- NREL, [Advanced Distribution Management Systems](https://www.nrel.gov/grid/advanced-distribution-management) — 배전망 상태, 자산, 계량, DER, 운영 도구 통합.
- NREL, [ADMS Test Bed](https://www.nrel.gov/grid/adms-test-bed) — fault location, isolation, switching, FLISR 기반 복구 lifecycle.
- NERC, [TOP-001-6 Transmission Operations](https://www.nerc.com/standards/reliability-standards/top/top-001-6) — 계통 상태 감시, operating instruction과 연쇄 장애 방지 조치.
- FERC, [Reliability Explainer](https://www.ferc.gov/reliability-explainer) — bulk-power roles, 신뢰도, 사고 격리와 규제 경계.
- OSHA, [Control of hazardous energy](https://www.osha.gov/control-hazardous-energy) — lockout/tagout, energy isolation, verification, authorized employee 경계.

중복 제외: `home_energy_management`의 소비자 thermostat·요금·가정기기와 달리 utility role, grid topology, switching authority, field isolation, restoration state가 필요하다. `telecom_field_service_ops`의 통신 노드 장애와도 asset·hazard를 교차 확인한다.

## 8. Environmental and waste operations (`environmental_waste_ops`)

허브: `environmental_waste_ops.hub` — 환경·폐기물 규제 업무 / Environmental and waste work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `environmental_waste_ops.permit_site_profile` | `v12_environmental_waste_ops_permit_site_profile` | S | 시설 → site ID·permit·generator status / Facility → site ID/permit/generator status |
| `environmental_waste_ops.waste_inventory` | `v12_environmental_waste_ops_waste_inventory` | S | 폐기물 보관구역 → stream·container·quantity·age / Waste storage area → stream/container/quantity/age |
| `environmental_waste_ops.manifest_tracking` | `v12_environmental_waste_ops_manifest_tracking` | S | e-Manifest → 발생자·운송자·처리시설·상태 / e-Manifest → generator/transporter/receiving facility/status |
| `environmental_waste_ops.sampling_plan` | `v12_environmental_waste_ops_sampling_plan` | S | 환경 매체·배출지점 → 지점·항목·빈도 계획 / Environmental medium/discharge point → location/analyte/frequency plan |
| `environmental_waste_ops.inspection_history` | `v12_environmental_waste_ops_inspection_history` | S | 시설 → 검사·위반·집행 이력 / Facility → inspection/violation/enforcement history |
| `environmental_waste_ops.compliance_dashboard` | `v12_environmental_waste_ops_compliance_dashboard` | S | 시설·permit → 보고기한·예외·시정조치 상태 / Facility/permit → due reports/exceptions/corrective-action status |
| `environmental_waste_ops.waste_characterization_record` | `v12_environmental_waste_ops_waste_characterization_record` | C | 폐기물 stream → 공정·성분·hazard code → 특성 결정 / Waste stream → process/composition/hazard code → determine characterization |
| `environmental_waste_ops.container_label_status` | `v12_environmental_waste_ops_container_label_status` | C | 보관 container → 내용·축적시작일·위험표지 → 상태 기록 / Storage container → contents/accumulation date/hazard label → record status |
| `environmental_waste_ops.pickup_schedule` | `v12_environmental_waste_ops_pickup_schedule` | C | 출하 준비 폐기물 → transporter·date·destination → pickup 확정 / Shipment-ready waste → transporter/date/destination → schedule pickup |
| `environmental_waste_ops.e_manifest_sign` | `v12_environmental_waste_ops_e_manifest_sign` | C | e-Manifest → 폐기물·수량·당사자·destination 확인 → 전자서명 / e-Manifest → verify waste/quantity/parties/destination → sign |
| `environmental_waste_ops.shipment_receive` | `v12_environmental_waste_ops_shipment_receive` | C | 도착 폐기물 → manifest·container·수량·상태 확인 → 수령 / Arriving waste → verify manifest/container/quantity/condition → receive |
| `environmental_waste_ops.discrepancy_report` | `v12_environmental_waste_ops_discrepancy_report` | C | 수령 shipment → 수량·종류·잔류물 차이 → discrepancy 제출 / Received shipment → quantity/type/residue discrepancy → submit report |
| `environmental_waste_ops.hazardous_waste_transfer` | `v12_environmental_waste_ops_hazardous_waste_transfer` | C | 폐기물 보관 → origin·destination·handler·manifest → custody transfer / Waste storage → origin/destination/handler/manifest → transfer custody |
| `environmental_waste_ops.treatment_process_log` | `v12_environmental_waste_ops_treatment_process_log` | C | 처리 batch → 공정·조건·잔재물 → 처리 기록 / Treatment batch → process/conditions/residuals → record treatment |
| `environmental_waste_ops.discharge_monitoring_record` | `v12_environmental_waste_ops_discharge_monitoring_record` | C | permit outfall → 시료·측정·한계·QA → 모니터링 기록 / Permitted outfall → sample/result/limit/QA → record monitoring |
| `environmental_waste_ops.sample_chain_of_custody` | `v12_environmental_waste_ops_sample_chain_of_custody` | C | 환경 시료 → 지점·용기·보존·인계자 → custody 기록 / Environmental sample → location/container/preservation/handler → record custody |
| `environmental_waste_ops.spill_release_report` | `v12_environmental_waste_ops_spill_release_report` | C | spill·release → 물질·양·매체·대응 → 사건 보고 / Spill/release → substance/quantity/medium/response → report event |
| `environmental_waste_ops.corrective_action_submit` | `v12_environmental_waste_ops_corrective_action_submit` | C | 위반·오염 unit → 원인·조치·검증 일정 → 시정조치 제출 / Violation/contaminated unit → cause/action/verification schedule → submit corrective action |
| `environmental_waste_ops.regulatory_report_certify` | `v12_environmental_waste_ops_regulatory_report_certify` | C | reporting period → 시설·폐기물·배출·예외 검토 → 인증 제출 / Reporting period → review facility/waste/discharge/exceptions → certify report |
| `environmental_waste_ops.facility_closeout` | `v12_environmental_waste_ops_facility_closeout` | C | permit·waste unit → 잔류물·문서·기관 승인 검토 → 폐쇄 / Permitted waste unit → review residuals/records/agency approval → close out |

역할·자산·상태: generator, transporter, receiving facility operator, environmental technician, laboratory custodian, permit manager, certifying official 역할을 구분한다. 핵심 자산은 EPA/site ID, permit/outfall, waste stream/code, container, e-Manifest, shipment, treatment batch, environmental sample, chain-of-custody, spill/release, corrective action이고 상태는 `identified → accumulated/labeled → manifested → transported → received/discrepant → treated/disposed → reported/corrected → closed`다.

충돌군: `manifest`(Android manifest/폐기물 운송장), `generator`(코드 생성기/폐기물 발생자), `container`(소프트웨어 컨테이너/폐기물 용기), `discharge`(환자 퇴원/환경 배출), `stream`(미디어 스트림/폐기물 흐름), `custody`(교정 사례/시료 인계), `closeout`(계정 종료/규제 시설 폐쇄)를 구별한다.

공식 근거:

- U.S. EPA, [Hazardous Waste Generator Regulatory Summary](https://www.epa.gov/hwgenerators/hazardous-waste-generator-regulatory-summary) — 폐기물 식별, generator category, 축적, 비상계획, 보고 요건.
- U.S. EPA, [e-Manifest](https://www.epa.gov/e-manifest) — manifest 생성, 편집, 전자서명, 제출, 정정, 상태조회.
- U.S. EPA, [RCRAInfo Industry Application](https://rcrainfo.epa.gov/rcrainfo-help/application/industryHelp/Introduction.htm) — site ID, biennial report, e-Manifest, 수출입 모듈.
- U.S. EPA, [RCRAInfo data downloads](https://rcrapublic.epa.gov/rcra-hwip/data-access/csv-downloads) — 검사, 위반, 집행, 시정조치, 발생·운송·처리 데이터 구조.
- U.S. EPA, [e-Manifest corrections FAQ](https://www.epa.gov/e-manifest/frequent-questions-about-e-manifest) — 제출 후 정정, 인증, 당사자 통지 lifecycle.
- U.S. EPA, [Hazardous Waste Manifest System](https://www.epa.gov/hwgenerators/hazardous-waste-manifest-system) — 발생지부터 최종 처리시설까지 추적·인계 구조.

중복 제외: `warehouse_fulfillment_ops`의 일반 container·shipment와 달리 regulatory site ID, waste code, generator/transporter/receiving-facility roles, manifest signature 또는 permitted disposal/treatment 상태가 필요하다.

## 9. Mining site safety operations (`mining_site_safety_ops`)

허브: `mining_site_safety_ops.hub` — 광산 현장 안전 업무 / Mining site safety work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `mining_site_safety_ops.shift_plan` | `v12_mining_site_safety_ops_shift_plan` | S | 광산·교대 → 작업구역·crew·활동 계획 / Mine/shift → work area/crew/activity plan |
| `mining_site_safety_ops.work_area_map` | `v12_mining_site_safety_ops_work_area_map` | S | 현장 지도 → pit·heading·shaft·haul road·exclusion zone / Site map → pit/heading/shaft/haul road/exclusion zone |
| `mining_site_safety_ops.personnel_equipment_status` | `v12_mining_site_safety_ops_personnel_equipment_status` | S | 교대 자원 → worker·mobile equipment·location·status / Shift resources → worker/mobile equipment/location/status |
| `mining_site_safety_ops.hazard_register` | `v12_mining_site_safety_ops_hazard_register` | S | 작업구역 → 지반·가스·폭파·교통 hazard / Work area → ground/gas/blast/traffic hazards |
| `mining_site_safety_ops.inspection_history` | `v12_mining_site_safety_ops_inspection_history` | S | 광산·구역 → workplace·equipment·regulatory inspection 이력 / Mine/area → workplace/equipment/regulatory inspection history |
| `mining_site_safety_ops.training_qualification_view` | `v12_mining_site_safety_ops_training_qualification_view` | S | 작업자 → 신규·직무·정기 교육·자격 / Worker → new-task/refresher training/qualification |
| `mining_site_safety_ops.prestart_inspection` | `v12_mining_site_safety_ops_prestart_inspection` | C | mobile equipment → 작업자·안전장치·결함 → 운전전 검사 / Mobile equipment → operator/safety devices/defects → pre-start inspection |
| `mining_site_safety_ops.worker_checkin` | `v12_mining_site_safety_ops_worker_checkin` | C | 교대 → 작업자·구역·교육·PPE 확인 → 현장 투입 / Shift → verify worker/area/training/PPE → check in |
| `mining_site_safety_ops.permit_to_work_issue` | `v12_mining_site_safety_ops_permit_to_work_issue` | C | 고위험 작업 → 범위·격리·crew·유효시간 → 작업허가 발행 / High-risk work → scope/isolation/crew/validity → issue permit |
| `mining_site_safety_ops.blast_plan_approve` | `v12_mining_site_safety_ops_blast_plan_approve` | C | blast plan → 위치·장약·시간·담당자 → 승인 / Blast plan → location/charge/time/responsible person → approve |
| `mining_site_safety_ops.exclusion_zone_confirm` | `v12_mining_site_safety_ops_exclusion_zone_confirm` | C | 폭파·위험작업 → 경계·인원·통신 확인 → zone 확정 / Blast/hazardous work → verify boundary/personnel/comms → confirm exclusion zone |
| `mining_site_safety_ops.ground_control_inspection` | `v12_mining_site_safety_ops_ground_control_inspection` | C | pit·heading·slope → 지반 상태·지보·결함 → 검사 기록 / Pit/heading/slope → ground condition/support/defect → record inspection |
| `mining_site_safety_ops.ventilation_gas_record` | `v12_mining_site_safety_ops_ventilation_gas_record` | C | underground area → airflow·gas·limit·time → 측정 기록 / Underground area → airflow/gas/limit/time → record measurement |
| `mining_site_safety_ops.equipment_lockout` | `v12_mining_site_safety_ops_equipment_lockout` | C | 광산 설비 → energy source·lock·worker·검증 → 격리 기록 / Mine equipment → energy source/lock/worker/verification → record isolation |
| `mining_site_safety_ops.haul_route_change` | `v12_mining_site_safety_ops_haul_route_change` | C | haul network → 도로·교차·속도·장비 영향 → 경로 변경 / Haul network → road/intersection/speed/equipment impact → change route |
| `mining_site_safety_ops.near_miss_report` | `v12_mining_site_safety_ops_near_miss_report` | C | 작업 사건 → 위치·활동·hazard·즉시조치 → near-miss 보고 / Work event → location/activity/hazard/immediate action → report near miss |
| `mining_site_safety_ops.emergency_evacuation_trigger` | `v12_mining_site_safety_ops_emergency_evacuation_trigger` | C | 광산 비상 → 구역·위험·대피경로·집결지 확인 → 대피 발령 / Mine emergency → verify area/hazard/egress/muster → trigger evacuation |
| `mining_site_safety_ops.corrective_action_close` | `v12_mining_site_safety_ops_corrective_action_close` | C | 검사·사건 조치 → 책임자·증거·재검증 → 시정조치 종료 / Inspection/event action → owner/evidence/reverification → close corrective action |
| `mining_site_safety_ops.production_shift_handover` | `v12_mining_site_safety_ops_production_shift_handover` | C | 교대 → 인원·설비·hazard·허가·미결작업 → 인계 / Shift → personnel/equipment/hazards/permits/open work → handoff |
| `mining_site_safety_ops.incident_regulatory_submit` | `v12_mining_site_safety_ops_incident_regulatory_submit` | C | 사고·부상·질병 → 사람·활동·결과·상태 확인 → 규제 보고 / Accident/injury/illness → verify person/activity/outcome/status → regulatory submission |

역할·자산·상태: miner/operator, equipment operator, supervisor, blasting authority, ventilation/ground-control examiner, safety manager, mine rescue coordinator 역할을 구분한다. 핵심 자산은 mine/site, pit/heading/shaft, haul road, worker qualification, mobile equipment, permit, blast plan, exclusion zone, gas reading, inspection/citation, incident report이고 상태는 `planned → inspected/permitted → active → isolated/restricted/evacuating → corrected → verified → handed off/reported`다.

충돌군: `mine`(소유대명사/광산), `pit`(구덩이/광산 작업구역), `blast`(알림 전송/폭파), `heading`(문서 제목/갱도 진행면), `ground control`(접지/지반 안정), `permit`(앱 권한/작업허가), `rescue`(계정복구/광산구조)를 구별한다.

공식 근거:

- MSHA, [Data and Reports](https://www.msha.gov/data-reports) — 광산, 검사, 사고, 부상, 위반, 생산량, 시료 데이터 범주.
- MSHA, [Mine Data Retrieval System](https://www.msha.gov/mdrs) — mine/operator/inspection/violation 상태 조회 구조.
- MSHA, [Form 7000-1](https://www.msha.gov/sites/default/files/Support_Resources/Forms/7000-1.pdf) — 사고·부상·질병, 작업 복귀, 최종 상태 보고 필드.
- MSHA, [Parts 46 and 48 Reference Guide](https://www.msha.gov/sites/default/files/Training_Education/OT%2056%20-%20Parts%2046%20%26%2048%20Reference%20Guide.pdf) — 신규·직무·정기 교육계획과 이수 기록.
- MSHA, [General Inspection Procedures Handbook](https://www.msha.gov/sites/default/files/Directive%20%26%20Guidance/Handbooks/PH19-IV_V-1%20General%20Inspection%20Procedures%20Handbook.pdf) — 검사 준비·수행, violation, citation, order 처리.
- MSHA, [Mine Rescue Guide](https://www.msha.gov/sites/default/files/Training_Education/Final%20-%20IG%20115%20Mine%20Rescue%20Guide.pdf) — 비상통보, 구조팀 동원, command, briefing과 구조 상태.

중복 제외: `manufacturing_quality_ops`나 `maintenance_asset_ops`의 일반 설비 검사와 달리 mine/site, underground or pit area, statutory training, blast/ground/ventilation hazard, MSHA-style inspection 또는 rescue state가 필요하다.

## 10. Election administration (`election_administration`)

허브: `election_administration.hub` — 선거 행정 업무 / Election administration work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `election_administration.election_calendar` | `v12_election_administration_election_calendar` | S | election → 등록·우편·투표·canvass·certification 일정 / Election → registration/mail/voting/canvass/certification calendar |
| `election_administration.precinct_profile` | `v12_election_administration_precinct_profile` | S | 관할구역 → precinct·polling place·district 관계 / Jurisdiction → precinct/polling-place/district mapping |
| `election_administration.poll_worker_roster` | `v12_election_administration_poll_worker_roster` | S | election → poll worker·역할·교육·배치 상태 / Election → poll worker/role/training/assignment status |
| `election_administration.equipment_inventory` | `v12_election_administration_equipment_inventory` | S | election equipment → 장치·봉인·위치·검사 상태 / Election equipment → device/seal/location/test status |
| `election_administration.ballot_style_review` | `v12_election_administration_ballot_style_review` | S | election → district·contest·candidate → ballot style 보기 / Election → district/contest/candidate → review ballot style |
| `election_administration.absentee_request_queue` | `v12_election_administration_absentee_request_queue` | S | 우편·부재자 요청 → 자격·주소·상태 작업함 / Mail/absentee requests → eligibility/address/status queue |
| `election_administration.voter_registration_record` | `v12_election_administration_voter_registration_record` | S | voter record → 관할·등록상태·이력 / Voter record → jurisdiction/registration status/history |
| `election_administration.audit_status` | `v12_election_administration_audit_status` | S | election → audit·표본·불일치·진행 상태 / Election → audit/sample/discrepancy/progress status |
| `election_administration.voter_registration_update` | `v12_election_administration_voter_registration_update` | C | voter record → 신원·주소·관할·근거 확인 → 등록 갱신 / Voter record → verify identity/address/jurisdiction/evidence → update registration |
| `election_administration.ballot_style_publish` | `v12_election_administration_ballot_style_publish` | C | ballot definition → district·contest·candidate·language 검증 → publish / Ballot definition → validate district/contest/candidate/language → publish |
| `election_administration.equipment_logic_accuracy_certify` | `v12_election_administration_equipment_logic_accuracy_certify` | C | election system → version·test deck·결과·seal 확인 → L&A 인증 / Election system → verify version/test deck/results/seal → certify logic and accuracy |
| `election_administration.poll_worker_assign` | `v12_election_administration_poll_worker_assign` | C | precinct → worker·역할·교육·충돌 확인 → 배정 / Precinct → verify worker/role/training/conflict → assign |
| `election_administration.polling_place_open` | `v12_election_administration_polling_place_open` | C | polling place → 장비·ballot·seal·인원 점검 → 개소 / Polling place → verify equipment/ballots/seals/staff → open |
| `election_administration.provisional_ballot_record` | `v12_election_administration_provisional_ballot_record` | C | voter exception → 사유·precinct·ballot envelope → provisional record / Voter exception → reason/precinct/ballot envelope → record provisional ballot |
| `election_administration.absentee_ballot_issue` | `v12_election_administration_absentee_ballot_issue` | C | 승인 요청 → voter·주소·ballot style·identifier 확인 → ballot 발급 / Approved request → verify voter/address/ballot style/identifier → issue ballot |
| `election_administration.ballot_receive_accept` | `v12_election_administration_ballot_receive_accept` | C | 반환 ballot → identifier·서명·기한·custody 확인 → 접수 판정 / Returned ballot → verify identifier/signature/deadline/custody → accept record |
| `election_administration.tabulation_batch_close` | `v12_election_administration_tabulation_batch_close` | C | counting batch → container·count·exception·operator 확인 → batch 종료 / Counting batch → verify container/count/exceptions/operator → close batch |
| `election_administration.canvass_result_certify` | `v12_election_administration_canvass_result_certify` | C | election results → precinct·provisional·mail·discrepancy 검토 → canvass 인증 / Election results → review precinct/provisional/mail/discrepancies → certify canvass |
| `election_administration.recount_audit_finalize` | `v12_election_administration_recount_audit_finalize` | C | audit·recount → scope·sample·차이·확대규칙 검토 → finalize / Audit/recount → review scope/sample/difference/escalation rule → finalize |
| `election_administration.polling_place_close` | `v12_election_administration_polling_place_close` | C | polling place → voter count·ballot·seal·장비·custody 대사 → 폐소 / Polling place → reconcile voters/ballots/seals/equipment/custody → close |

역할·자산·상태: registrar, election administrator, ballot designer, equipment custodian, poll worker supervisor, canvassing board member, auditor 역할을 구분한다. 핵심 자산은 election, jurisdiction/district/precinct, voter record, ballot style, contest/candidate, mail/provisional ballot, equipment/seal, polling place, tabulation batch, audit sample, canvass/certification record이고 상태는 `configured → reviewed/tested → published/issued → opened/received/counting → canvassed/audited → certified → closed`다.

충돌군: `registration`(서비스 회원가입/유권자 등록), `candidate`(추천 후보/선거 후보), `poll`(설문조사/투표), `ballot`(일반 선택지/법정 투표용지), `issue`(문제/ballot 발급), `count`(목록 수/법정 개표), `certify`(일반 확인/공식 결과 인증), `close`(화면 닫기/투표소 폐소)를 구별한다.

공식 근거:

- U.S. EAC, [Election Management Guidelines](https://www.eac.gov/election-officials/election-management-guidelines) — 선거 설정, ballot 제작, 사전시험, polling place, mail/provisional voting, audit, recount.
- U.S. EAC, [Quick Start Guides](https://www.eac.gov/election-officials/quick-start-guides) — ballot tracking·reconciliation, central count, provisional adjudication, audit trail 실무.
- U.S. EAC, [Election Results, Canvass, and Certification](https://www.eac.gov/election-officials/election-results-canvass-and-certification) — unofficial result, canvass, audit, official certification lifecycle.
- U.S. EAC, [Election Audits Across the United States](https://www.eac.gov/election-officials/election-audits-across-united-states) — audit type, sample, discrepancy, completion state.
- U.S. EAC, [Chain of Custody Best Practices](https://www.eac.gov/election-officials/chain-custody-best-practices) — ballot 발급·회수·보관·인계와 수량 대사.
- NIST, [Election Results Reporting Common Data Format](https://pages.nist.gov/ElectionResultsReporting/) — election, contest, candidate, precinct, ballot type, count status, certification 데이터 모델.

중복 제외: 일반 `government_digital` 민원이나 `identity_account` 가입과 분리한다. election/jurisdiction/precinct, voter record, ballot style, chain-of-custody 또는 canvass/certification 증거 없이 일반 `등록`, `투표`, `인증` alias로 선택하지 않는다.

## 11. Research grants administration (`research_grants_administration`)

허브: `research_grants_administration.hub` — 연구비·과제 행정 업무 / Research grants administration work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `research_grants_administration.opportunity_search` | `v12_research_grants_administration_opportunity_search` | S | funding opportunities → sponsor·분야·마감·자격 필터 / Funding opportunities → sponsor/topic/deadline/eligibility filter |
| `research_grants_administration.proposal_workspace` | `v12_research_grants_administration_proposal_workspace` | S | 신청과제 → 담당자·component·validation·status / Application proposal → people/components/validation/status |
| `research_grants_administration.sponsor_guidance_review` | `v12_research_grants_administration_sponsor_guidance_review` | S | opportunity → announcement·instructions·policy·deadline / Opportunity → announcement/instructions/policy/deadline |
| `research_grants_administration.budget_view` | `v12_research_grants_administration_budget_view` | S | proposal·award → category·period·direct/indirect cost / Proposal/award → category/period/direct-indirect cost |
| `research_grants_administration.compliance_status` | `v12_research_grants_administration_compliance_status` | S | project → disclosure·human/animal/biosafety·training status / Project → disclosure/human-animal/biosafety/training status |
| `research_grants_administration.award_portfolio` | `v12_research_grants_administration_award_portfolio` | S | investigator·unit → active award·period·balance·status / Investigator/unit → active award/period/balance/status |
| `research_grants_administration.expenditure_dashboard` | `v12_research_grants_administration_expenditure_dashboard` | S | award → obligation·expenditure·encumbrance·balance / Award → obligation/expenditure/encumbrance/balance |
| `research_grants_administration.reporting_calendar` | `v12_research_grants_administration_reporting_calendar` | S | award → progress·financial·invention·closeout due dates / Award → progress/financial/invention/closeout due dates |
| `research_grants_administration.proposal_create` | `v12_research_grants_administration_proposal_create` | C | opportunity → organization·PI·deadline·mechanism → proposal 생성 / Opportunity → organization/PI/deadline/mechanism → create proposal |
| `research_grants_administration.investigator_role_assign` | `v12_research_grants_administration_investigator_role_assign` | C | proposal → person·project role·effort·authority → 배정 / Proposal → person/project role/effort/authority → assign |
| `research_grants_administration.budget_submit_review` | `v12_research_grants_administration_budget_submit_review` | C | proposal budget → period·cost·justification·cap 검토 → review 제출 / Proposal budget → review period/cost/justification/cap → submit for review |
| `research_grants_administration.subaward_setup` | `v12_research_grants_administration_subaward_setup` | C | proposal·award → subrecipient·scope·budget·risk → subaward 설정 / Proposal/award → subrecipient/scope/budget/risk → set up subaward |
| `research_grants_administration.compliance_disclosure_submit` | `v12_research_grants_administration_compliance_disclosure_submit` | C | investigator·project → interest·relationship·mitigation → disclosure 제출 / Investigator/project → interest/relationship/mitigation → submit disclosure |
| `research_grants_administration.institutional_approval` | `v12_research_grants_administration_institutional_approval` | C | complete proposal → budget·compliance·assurance·signatory 검토 → 기관 승인 / Complete proposal → review budget/compliance/assurance/signatory → institutional approval |
| `research_grants_administration.sponsor_application_submit` | `v12_research_grants_administration_sponsor_application_submit` | C | approved proposal → forms·attachments·validation·deadline 확인 → sponsor 제출 / Approved proposal → verify forms/attachments/validation/deadline → submit to sponsor |
| `research_grants_administration.award_accept` | `v12_research_grants_administration_award_accept` | C | notice of award → terms·budget·period·restriction 검토 → 수락 / Notice of award → review terms/budget/period/restrictions → accept |
| `research_grants_administration.rebudget_request` | `v12_research_grants_administration_rebudget_request` | C | active award → category·amount·justification·prior approval → 변경 요청 / Active award → category/amount/justification/prior approval → request rebudget |
| `research_grants_administration.drawdown_payment_request` | `v12_research_grants_administration_drawdown_payment_request` | C | award account → allowable cost·cash need·amount·period 확인 → drawdown 요청 / Award account → verify allowable cost/cash need/amount/period → request drawdown |
| `research_grants_administration.progress_report_submit` | `v12_research_grants_administration_progress_report_submit` | C | reporting period → accomplishments·personnel·products·changes 검토 → progress report 제출 / Reporting period → review accomplishments/personnel/products/changes → submit progress report |
| `research_grants_administration.award_closeout` | `v12_research_grants_administration_award_closeout` | C | ended award → final progress·financial·invention·property 검토 → closeout / Ended award → review final progress/financial/invention/property → close out |

역할·자산·상태: principal investigator, department administrator, sponsored-program officer, authorized organizational representative, compliance officer, financial official, sponsor program/grants officer 역할을 구분한다. 핵심 자산은 funding opportunity, proposal/application, component, budget period, investigator role, disclosure/protocol, award, subaward, prior-approval request, drawdown, RPPR/final report, closeout package이고 상태는 `draft → routed/reviewed → institutionally approved → submitted/validated → awarded/active → reporting/rebudgeting → ended/closeout`다.

충돌군: `award`(상품 보상/연구비 award), `proposal`(일반 제안/지원 application), `PI`(원주율/책임연구자), `effort`(난이도/인건비 effort), `drawdown`(차트 낙폭/보조금 인출), `closeout`(쇼핑 재고정리/award 종료), `disclosure`(개인정보 고지/이해상충 신고), `report`(조회/법정 제출)를 구별한다.

공식 근거:

- Grants.gov, [Applicants](https://grants.gov/applicants/) — 자격확인, 등록, 기회검색, workspace 생성, 신청·추적 lifecycle.
- NIH eRA, [Commons overview](https://www.era.nih.gov/help-tutorials/era-commons/overview.htm) — application, review result, award, JIT, RPPR, prior approval, closeout 역할별 기능.
- NIH eRA, [Status module](https://www.era.nih.gov/about-era/services-for-applicants-recipients/monitor-application/overview-status.htm) — application, award, report, approval request 상태와 담당자 추적.
- NIH eRA, [Submit Progress Report](https://www.era.nih.gov/grantees/submit-progress-report.htm) — annual/interim/final RPPR 작성·저장·제출.
- NIH eRA, [Closeout reports](https://www.era.nih.gov/about-era/services-for-applicants-recipients/closeout-reports) — final RPPR, financial report, invention statement 제출과 종료.
- NIH, [Grants Policy Statement](https://www.grants.nih.gov/policy-and-compliance/nihgps) — award terms, prior approval, costs, property, reporting, closeout 정책.

중복 제외: `laboratory_research_ops`의 sample/notebook 실험 수행, `clinical_trial_site_ops`의 subject/visit/kit 규제 workflow, `procurement_supplier_ops`의 구매·PO와 분리한다. sponsor opportunity, institutional routing, award terms 또는 grant reporting evidence가 필요하다.

## 12. Corrections case-management operations (`corrections_case_management_ops`)

허브: `corrections_case_management_ops.hub` — 교정 사례·수용 운영 업무 / Corrections case-management work

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `corrections_case_management_ops.caseload_queue` | `v12_corrections_case_management_ops_caseload_queue` | S | 담당 사례 → 시설·unit·우선순위·review due 필터 / Assigned caseload → facility/unit/priority/review-due filter |
| `corrections_case_management_ops.person_case_summary` | `v12_corrections_case_management_ops_person_case_summary` | S | 수용자 record → identity·custody·alerts·case status / Incarcerated-person record → identity/custody/alerts/case status |
| `corrections_case_management_ops.custody_classification_view` | `v12_corrections_case_management_ops_custody_classification_view` | S | person case → security·custody·risk/need 분류 / Person case → security/custody/risk-needs classification |
| `corrections_case_management_ops.court_order_sentence_review` | `v12_corrections_case_management_ops_court_order_sentence_review` | S | legal record → court order·sentence·detainer·credit / Legal record → court order/sentence/detainer/credit |
| `corrections_case_management_ops.housing_location_status` | `v12_corrections_case_management_ops_housing_location_status` | S | facility → person·unit·cell/bed·movement status / Facility → person/unit/cell-bed/movement status |
| `corrections_case_management_ops.program_eligibility_view` | `v12_corrections_case_management_ops_program_eligibility_view` | S | case plan → education·treatment·reentry program eligibility / Case plan → education/treatment/reentry eligibility |
| `corrections_case_management_ops.release_date_calculation_review` | `v12_corrections_case_management_ops_release_date_calculation_review` | S | sentence computation → term·credit·detainer·projected release / Sentence computation → term/credit/detainer/projected release |
| `corrections_case_management_ops.intake_identity_verify` | `v12_corrections_case_management_ops_intake_identity_verify` | C | intake → person·commitment order·biographic identifier 확인 → 입소 등록 / Intake → verify person/commitment order/biographic identifier → register admission |
| `corrections_case_management_ops.risk_needs_assessment` | `v12_corrections_case_management_ops_risk_needs_assessment` | C | person case → validated factors·source·reviewer → risk/needs assessment 기록 / Person case → validated factors/source/reviewer → record risk-needs assessment |
| `corrections_case_management_ops.housing_assignment` | `v12_corrections_case_management_ops_housing_assignment` | C | classified person → facility·unit·bed·separation·capacity 확인 → 배정 / Classified person → verify facility/unit/bed/separation/capacity → assign housing |
| `corrections_case_management_ops.movement_authorization` | `v12_corrections_case_management_ops_movement_authorization` | C | person movement → origin·destination·escort·time·authority 확인 → 승인 / Person movement → verify origin/destination/escort/time/authority → authorize |
| `corrections_case_management_ops.incident_disciplinary_report` | `v12_corrections_case_management_ops_incident_disciplinary_report` | C | facility incident → person·rule·evidence·immediate action → disciplinary report / Facility incident → person/rule/evidence/immediate action → submit disciplinary report |
| `corrections_case_management_ops.restrictive_housing_review` | `v12_corrections_case_management_ops_restrictive_housing_review` | C | restrictive placement → 사유·기간·안전·review authority → 계속·변경 결정 / Restrictive placement → reason/duration/safety/review authority → continue/change decision |
| `corrections_case_management_ops.medical_transport_request` | `v12_corrections_case_management_ops_medical_transport_request` | C | person case → appointment·security·escort·privacy → 이송 요청 / Person case → appointment/security/escort/privacy → request medical transport |
| `corrections_case_management_ops.court_event_update` | `v12_corrections_case_management_ops_court_event_update` | C | legal case → hearing·order·disposition·document source → 갱신 / Legal case → hearing/order/disposition/document source → update |
| `corrections_case_management_ops.program_enrollment` | `v12_corrections_case_management_ops_program_enrollment` | C | eligible person → program·capacity·schedule·case goal → 등록 / Eligible person → program/capacity/schedule/case goal → enroll |
| `corrections_case_management_ops.visitor_approval_decision` | `v12_corrections_case_management_ops_visitor_approval_decision` | C | visitor request → identity·relationship·screening·restriction → 승인·거절 / Visitor request → identity/relationship/screening/restriction → approve/deny |
| `corrections_case_management_ops.property_chain_of_custody` | `v12_corrections_case_management_ops_property_chain_of_custody` | C | person property·evidence → item·seal·location·handler → custody transfer / Person property/evidence → item/seal/location/handler → transfer custody |
| `corrections_case_management_ops.release_plan_approve` | `v12_corrections_case_management_ops_release_plan_approve` | C | release candidate → housing·service·supervision·notification·hold 검토 → 계획 승인 / Release candidate → review housing/services/supervision/notifications/holds → approve plan |
| `corrections_case_management_ops.custody_release_execute` | `v12_corrections_case_management_ops_custody_release_execute` | C | approved release → identity·authority·date·detainer·property 확인 → custody release / Approved release → verify identity/authority/date/detainer/property → execute release |

역할·자산·상태: intake officer, correctional officer, case manager, classification committee, records/sentence-computation specialist, program coordinator, release authority 역할을 구분한다. 핵심 자산은 person/case record, commitment/court order, classification, facility/unit/bed, movement, incident/disciplinary case, program enrollment, visitor request, property/evidence, sentence computation, release plan이며 상태는 `admitted/screened → classified → housed/active custody → reviewed/programmed → transfer/restrictive status → release-eligible/held → approved → released`다.

충돌군: `case`(복지·법률·보험·교정 사례), `custody`(자녀 양육권/시설 수용/증거 인계), `sentence`(문장/형량), `cell`(표 셀/수용실), `release`(소프트웨어 배포/화물 반출/신체 자유 회복), `classification`(ML label/보안 등급), `program`(소프트웨어/교정 프로그램), `movement`(애니메이션/수용자 이동)을 구별한다.

공식 근거:

- Federal Bureau of Prisons, [Designations](https://www.bop.gov/inmates/custody_and_care/designations.jsp) — security, medical, program need에 따른 시설 지정·재지정.
- Federal Bureau of Prisons, [Policy search](https://www.bop.gov/PublicInfo/execute/policysearch?todo=query) — intake, classification, discipline, sentence computation, release 관련 공식 정책.
- Federal Bureau of Prisons, [Intake Screening](https://www.bop.gov/policy/progstat/5290_015.pdf) — 입소 시 social, medical, safety, risk screening과 일반 수용 전 상태.
- Federal Bureau of Prisons, [Forms](https://www.bop.gov/PublicInfo/execute/forms?sortBy=frm_number&sortDescending=false&todo=query) — incident, hearing, transfer, custody, sentence computation, release 업무 객체.
- Bureau of Justice Assistance, [Community-based Reentry Program](https://bja.ojp.gov/program/cb-reentry/overview) — risk/needs assessment, case plan, service linkage, pre/post-release support.
- U.S. DOJ PREA Resource Center, [Prisons and Jails Standards](https://www.prearesourcecenter.org/implementation/prea-standards/prisons-and-jails-standards) — risk screening, incident report, initial response, investigation, protection, review states.

중복 제외: `social_services_casework`의 voluntary benefit/service case, `legal_practice_ops`의 attorney matter, `emergency_response_operations`의 ICS incident와 분리한다. custody authority, commitment/sentence, housing/movement restriction 또는 lawful release condition이 확인되지 않으면 이 도메인에 진입하지 않는다.

## 교차 도메인 collision matrix

각 collision family는 한 도메인의 positive probe뿐 아니라 최소 두 개의 다른 역할·자산·상태 조합을 negative probe로 가져야 한다. alias-only winner는 금지하며 증거가 부족하면 해당 도메인의 허브에서 멈춘다.

| 모호 표현 | 반드시 구별할 개념 |
|---|---|
| `patient` / 환자 | human clinical patient, animal patient, home-health episode subject, dental patient |
| `owner` / 소유자·보호자 | animal owner, work owner, asset owner, account owner |
| `administration` / 투여·행정 | medication administration, election administration, grant administration, account admin |
| `registration` / 등록 | animal/patient intake, voter registration, service account signup, award-system enrollment |
| `prescription` / 처방 | veterinary/dental issue, clinician order, pharmacy dispense |
| `certificate` / 증명 | animal export health certificate, election result certification, equipment calibration certificate |
| `chart` / 차트 | dental odontogram/periodontal chart, clinical chart, analytics chart |
| `surface` / 면 | tooth surface, UI surface, mine surface operation |
| `release` / 해제·반출·복귀 | aircraft release-to-service, customs cargo release, custody release, software release |
| `defer` / 이연 | aircraft defect defer, payment defer, task snooze |
| `consist` / 편성 | rail consist, textual consistency, shipment grouping |
| `switch` / 전환 | rail switch, grid switch, UI toggle, account switch |
| `authority` / 권한 | rail movement authority, grid switching authority, user authorization |
| `route` / 경로 | dispatch route, haul route, shipment route, UI navigation route |
| `manifest` / 운송장·목록 | cargo manifest, hazardous-waste manifest, Android manifest |
| `entry` / 신고·진입 | customs entry, data entry, login entry |
| `classification` / 분류 | tariff classification, custody classification, ML label, waste characterization |
| `hold` / 보류 | customs hold, clinical hold, custody detainer, UI pause |
| `outage` / 장애 | electric outage, telecom outage, generic service incident |
| `disconnect` / 차단 | meter disconnect, network disconnect, logout/session close |
| `generator` / 발생자 | hazardous-waste generator, power generator, code generator |
| `discharge` / 배출·퇴원 | permitted environmental discharge, patient discharge, battery discharge |
| `permit` / 허가 | environmental permit, mining permit-to-work, runtime permission |
| `blast` / 폭파 | mine blasting, notification broadcast, data blast |
| `poll` / 투표·조사 | statutory election poll, survey, repeated status polling |
| `candidate` / 후보 | election candidate, recommendation candidate, resolver candidate |
| `award` / 연구비·수상 | sponsored award, consumer reward, prize |
| `effort` / 노력·인건비 | grant personnel effort, model reasoning effort, task difficulty |
| `sentence` / 형량·문장 | legal sentence computation, natural-language sentence |
| `custody` / 수용·인계 | corrections custody, sample/property chain of custody, child custody |
| `cell` / 수용실·셀 | housing cell, spreadsheet cell, battery cell |
| `closeout` / 종료 | grant award closeout, regulated facility closure, retail clearance sale |

## 구현 데이터 계약

각 domain source module은 다음을 최소 계약으로 구현한다.

- domain 12개와 hub 12개를 deterministic order로 materialize한다.
- terminal 240개, intent 240개, `S=78`, `C=162`를 정확히 생성한다.
- terminal마다 한국어 alias 4개 이상, 영어 alias 4개 이상, positive context 6개 이상, negative context 8개 이상, role hint 2개 이상, asset cue 2개 이상, lifecycle-state cue 2개 이상을 둔다.
- intent마다 한국어 goal pattern 5개 이상, 영어 goal pattern 5개 이상, compositional rule 24개 이상, 동일 collision family의 `avoid_functions` 2개 이상을 둔다.
- source metadata는 `publisher`, `title`, `url`, `retrieved_at`, `supported_assets`, `supported_states`를 보존한다. 본 감사안에는 domain당 최소 5개, 총 **74개 공식 URL**이 있다.
- 개인 이름, 환자·동물·유권자·수용자·작업자 식별번호, 항공기 실제 등록기호, 실제 선로·전력 설비 ID, 실제 shipment/declaration 번호, 실제 광산·투표소·시설 위치는 source·fixture·telemetry에 영구 저장하지 않는다.
- Android 표현은 semantic UI evidence로만 사용한다. 실제 앱 이름, package name, resource ID, 좌표, 픽셀 위치, 고정 화면 순서, 고정 클릭 route를 ontology에 넣지 않는다.
- 모든 terminal에 `automation_policy=never_auto`, `stop_policy=before_action`, `user_owned_final_press=true`를 명시한다. `C` 162개는 `risk=high`를 강제하며, `disabled/unavailable/hold/wrong role/wrong record`에서 유사 대체 terminal로 이동하지 않는다.

## 정확한 검증 gates

1. **Ontology count gate:** 12 domains, 12 hubs, 240 terminals, 252 functions, 240 intents, `S=78`, `C=162`가 정확해야 한다.
2. **ID gate:** function·intent 중복 0, v1~v11 ID overlap 0, 허용 패턴은 `[a-z0-9_]+\.[a-z0-9_]+`와 `v12_[a-z0-9_]+`뿐이다. materialization 3회 결과가 byte-identical이어야 한다.
3. **Domain semantic matrix:** terminal마다 한국어 positive 1, 영어 positive 1, wrong-role 1, wrong-asset/state homonym 1, unavailable/permission 1, explicit-negation/wrong-record 1의 **6 probes**, 총 **1,440 probes**를 고정한다.
4. **Collision suite:** 위 32 collision family마다 최소 12개 contrastive probes를 두어 총 **384 probes 이상**을 실행한다. alias-only match와 hub를 건너뛴 terminal 확정을 허용하지 않는다.
5. **State·permission recovery:** terminal마다 `disabled`, `unavailable/offline`, `wrong role`, `wrong record/asset` 4개를 두어 총 **960 probes**를 실행한다. recovery 후보는 원래 위험도보다 낮아질 수 없고 terminal 자동 클릭은 0이어야 한다.
6. **Safety gate:** 240개 terminal 전체가 `never_auto + before_action + user_owned_final_press`; agent terminal press 0/240, 사용자 handoff 240/240이어야 한다. `C` 162개는 high risk 162/162이고 confirm·approve·sign·issue·submit·release·energize·certify·close·execute 버튼 자동 누름은 0이다.
7. **Independent frozen fixture:** source/catalog에서 생성하지 않은 **240 scenarios**, 한국어 120·영어 120, scenario당 최소 4 steps로 **960 steps 이상**을 사용한다. 정답·실패 label은 구현 튜닝에 열람하지 않는다.
8. **Role/asset isolation gate:** 12 domains 각각 wrong-role 20개, wrong-asset 20개, wrong-state 20개로 총 **720 probes**를 별도 실행한다. 적절한 hub fallback 또는 fail-closed만 허용한다.
9. **Source gate:** domain마다 서로 다른 공식 1차 문서 4개 이상, 전체 48개 이상이 유효해야 한다. redirect 이후 HTTPS, publisher allowlist, 수집일, 지원 객체·상태를 source registry에서 검증한다.
10. **Regression gate:** v1~v11 deterministic materialization, quality, independent coverage, alias collision, semantic fallback, resolver latency, safety suite를 모두 유지한다. v12 추가로 이전 intent winner가 바뀌면 명시적 collision waiver 없이는 실패한다.
11. **Performance gate:** warm resolver p95를 기존 예산보다 10% 이상 악화시키지 않고, candidate prefilter 뒤 terminal scoring 후보 수 p99를 64 이하로 제한한다. safety filter와 final-press stop은 latency shortcut보다 먼저 실행한다.
12. **Privacy gate:** fixture·trace에 실제 person/animal/voter/incarcerated-person ID, exact facility/site/precinct/asset location, waybill/declaration/aircraft serial, medical/legal record content가 0이어야 한다.

## 읽기 전용 ID·수량 검증

아래 PowerShell은 문서와 v1~v11 source 파일을 읽기만 한다. 파일 생성·수정, fixture 열람, test 실행은 하지 않는다.

```powershell
$doc = Get-Content -Raw -Encoding utf8 docs/NAVIGATION_COVERAGE_GAPS_V12.md
$rowPattern = '(?m)^\| `([a-z0-9_]+\.[a-z0-9_]+)` \| `(v12_[a-z0-9_]+)` \| ([SC]) \|'
$hubPattern = '(?m)^허브: `([a-z0-9_]+\.hub)`'
$matches = [regex]::Matches($doc, $rowPattern)
$hubs = [regex]::Matches($doc, $hubPattern)

$rows = foreach ($m in $matches) {
  [pscustomobject]@{
    Function = $m.Groups[1].Value
    Intent   = $m.Groups[2].Value
    Class    = $m.Groups[3].Value
    Domain   = ($m.Groups[1].Value -split '\.')[0]
  }
}

$prior = (Get-ChildItem scripts/navigation_catalog_v*_data.py |
  Where-Object Name -ne navigation_catalog_v12_data.py |
  ForEach-Object { Get-Content -Raw -Encoding utf8 $_.FullName }) -join "`n"
$allIds = @($hubs | ForEach-Object { $_.Groups[1].Value }) + @($rows.Function) + @($rows.Intent)
$overlap = @($allIds | Where-Object { $prior.Contains($_) } | Sort-Object -Unique)

[ordered]@{
  domains            = ($rows.Domain | Sort-Object -Unique).Count
  hubs               = $hubs.Count
  terminals          = $rows.Count
  functions          = $rows.Count + $hubs.Count
  intents            = ($rows.Intent | Sort-Object -Unique).Count
  S                  = ($rows | Where-Object Class -eq S).Count
  C                  = ($rows | Where-Object Class -eq C).Count
  duplicateFunctions = $rows.Count - ($rows.Function | Sort-Object -Unique).Count
  duplicateIntents   = $rows.Count - ($rows.Intent | Sort-Object -Unique).Count
  v1ToV11Overlap     = $overlap.Count
} | ConvertTo-Json
```

2026-07-30 기록 결과:

```json
{
  "domains": 12,
  "hubs": 12,
  "terminals": 240,
  "functions": 252,
  "intents": 240,
  "S": 78,
  "C": 162,
  "duplicateFunctions": 0,
  "duplicateIntents": 0,
  "v1ToV11Overlap": 0
}
```

도메인별 terminal 수 역시 12개 모두 정확히 20개였고, 문서 내 공식 URL은 74개였다. 이 결과는 **ID·수량·문서 중복만 검증**하며 resolver 정확도나 독립 fixture 통과를 주장하지 않는다.

## 권장 구현 순서

1. 12개 domain의 role·asset·state schema와 공식 source registry를 먼저 고정한다.
2. hub 12개와 terminal 240개의 ID, S/C, safety policy를 고정하고 alias보다 negative context를 먼저 작성한다.
3. 각 terminal의 한/영 goal pattern과 collision `avoid_functions`를 작성한다.
4. 1,440 semantic probes, 384+ collision probes, 960 recovery probes, 720 role/asset/state isolation probes를 통과시킨다.
5. 기존 v1~v11 전체 regression과 latency gate를 통과한 뒤에만 canonical materialization 후보로 올린다.
6. 마지막으로 독립 240-scenario fixture를 한 번 실행하며, 실패 문장·정답 label을 source 튜닝 입력으로 사용하지 않는다.

## 감사 한계

이 문서는 전문 업무 lifecycle이 공식 자료에 존재하는지와 기존 v1~v11 ontology에서 의미상 비어 있는지를 평가한 설계 감사다. 국가·기관·직종·규정·조직별 권한과 UI 차이는 실제 배포에서 달라질 수 있다. 따라서 공식 문서가 기능 존재를 뒷받침해도 모든 Android 제품에 같은 label, 화면 구조, 권한 또는 workflow가 있다는 뜻은 아니다. 실제 기기 검증은 별도 단계로 수행하고, 여기서는 앱별 고정 경로나 좌표를 만들지 않는다.
