# Navigation ontology coverage gap audit — v13

감사 기준일: 2026-07-30
감사 기준선: v12 source layer 반영 예상 **143개 도메인, 2,110개 기능, 1,940개 intent**. 현재 materialized catalog는 v11 **131개 도메인, 1,858개 기능, 1,700개 intent**이며, v12 source module·설계 문서의 **12개 도메인, 252개 기능, 240개 intent**를 함께 선행 집합으로 감사했다.
감사 범위: 공개 독립 평가 fixture의 문장·정답·실패 결과를 열람하지 않고, `function-catalog.v1.json`, v3~v12 source module, `NAVIGATION_COVERAGE_GAPS_V5.md`~`V12.md`와 아래 공식 1차 문서만 대조한 source-level 설계 감사

## 결론

v13에서는 범용 소비자·업무 앱과 v11~v12 전문 운영 팩에도 아직 독립된 역할·자산·상태 경계가 없는 아래 12개 장기꼬리 영역을 권장한다. 정확한 제안 규모는 **252개 기능(허브 12 + terminal 240), 240개 intent**이며, 반영 후 예상 누계는 **155개 도메인, 2,362개 기능, 2,180개 intent**다.

| 우선순위 | 도메인 ID | terminal | 허브 포함 기능 | intent | S | C |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `blood_bank_transfusion_ops` | 20 | 21 | 20 | 7 | 13 |
| 2 | `organ_transplant_coordination` | 20 | 21 | 20 | 7 | 13 |
| 3 | `radiation_therapy_ops` | 20 | 21 | 20 | 7 | 13 |
| 4 | `court_clerk_case_admin` | 20 | 21 | 20 | 7 | 13 |
| 5 | `ip_prosecution_docketing` | 20 | 21 | 20 | 7 | 13 |
| 6 | `food_establishment_inspection` | 20 | 21 | 20 | 7 | 13 |
| 7 | `building_permit_code_enforcement` | 20 | 21 | 20 | 7 | 13 |
| 8 | `water_wastewater_plant_ops` | 20 | 21 | 20 | 7 | 13 |
| 9 | `nuclear_plant_operations` | 20 | 21 | 20 | 7 | 13 |
| 10 | `pipeline_control_integrity_ops` | 20 | 21 | 20 | 7 | 13 |
| 11 | `museum_collections_ops` | 20 | 21 | 20 | 7 | 13 |
| 12 | `air_traffic_control_ops` | 20 | 21 | 20 | 7 | 13 |
| **합계** | **12개** | **240** | **252** | **240** | **84** | **156** |

`S`는 민감하거나 자격·권한이 제한된 조회 목적지이고, `C`는 임상·법률·규제·시설·공공안전·산업 설비·항공 교통의 기록이나 현실 상태를 바꾸는 결과적 목적지다. **240개 terminal 전부** `automation_policy=never_auto`, `stop_policy=before_action`, `user_owned_final_press=true`로 고정한다. 에이전트는 대상·역할·상태와 공식 근거를 보여준 뒤 멈추고, 마지막 누름은 항상 사용자가 수행한다. `C` 156개는 예외 없이 `risk=high`이며 자동 실행, 자동 확인, 음성 명령 대행, 우회 버튼 선택을 허용하지 않는다.

## 공통 ID·개념 경로·안전 계약

- 허브 ID: `<domain>.hub`
- terminal ID: `<domain>.<terminal_key>`
- intent ID: `v13_<domain>_<terminal_key>`
- 아래 경로는 앱 이름, package, resource ID, 좌표, 픽셀 위치, 고정 클릭 순서가 아니다. Android 접근성 트리·OCR·현재 화면 상태에서 동적으로 찾을 **한/영 개념 route**다.
- terminal 확정에는 `role + governed asset + lifecycle state` 세 축 중 최소 두 축이 필요하다. 버튼 alias나 단일 명사만으로 terminal을 확정하지 않는다.
- `disabled`, `unavailable`, `permission denied`, `wrong role`, `wrong record`, `wrong facility`, `stale/offline`, `approval required`, `clinical hold`, `legal hold`, `quality hold`, `safety hold`, `regulatory hold`, `equipment out of service`, `emergency control`에서는 fail-closed한다.
- `C`는 `never_auto + before_action + user_owned_final_press`를 불변식으로 검증한다. 본 팩에서는 `S`에도 같은 최종 누름 정책을 적용하며, 잘못된 사람·시설·사건·자산·수명주기이면 허브에서 멈춘다.
- 실시간 안전 업무에서 UI가 `confirm`, `approve`, `issue`, `release`, `operate`, `start`, `stop`, `trip`, `submit`, `close`를 제시해도 에이전트는 버튼을 누르거나 동등한 음성·키보드 동작을 수행하지 않는다.

## 1. Blood-bank and transfusion operations (`blood_bank_transfusion_ops`)

허브: `blood_bank_transfusion_ops.hub` — 혈액은행·수혈 운영 / Blood-bank and transfusion operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `blood_bank_transfusion_ops.donor_eligibility_queue` | `v13_blood_bank_transfusion_ops_donor_eligibility_queue` | S | 헌혈자 작업함 → 문진·검사 대기 → 적격성 상태 / Donor worklist → screening/testing due → eligibility status |
| `blood_bank_transfusion_ops.component_inventory_view` | `v13_blood_bank_transfusion_ops_component_inventory_view` | S | 혈액 성분 재고 → 성분형·혈액형·유효기간·보관 위치 / Component inventory → type/ABO-Rh/expiration/storage location |
| `blood_bank_transfusion_ops.unit_traceability_view` | `v13_blood_bank_transfusion_ops_unit_traceability_view` | S | 혈액 단위 → 헌혈·가공·검사·배포 이력 / Blood unit → collection/processing/testing/distribution history |
| `blood_bank_transfusion_ops.compatibility_result_review` | `v13_blood_bank_transfusion_ops_compatibility_result_review` | S | 수혈 대상자 → 검체·항체 선별·교차시험 결과 / Recipient → specimen/antibody screen/crossmatch result |
| `blood_bank_transfusion_ops.transfusion_order_review` | `v13_blood_bank_transfusion_ops_transfusion_order_review` | S | 환자 수혈 의뢰 → 성분·수량·임상 지시 검토 / Patient transfusion order → component/quantity/clinical instruction review |
| `blood_bank_transfusion_ops.storage_temperature_status` | `v13_blood_bank_transfusion_ops_storage_temperature_status` | S | 보관 장비 → 온도 로그·경보·영향 단위 / Storage equipment → temperature log/alarm/affected units |
| `blood_bank_transfusion_ops.adverse_event_dashboard` | `v13_blood_bank_transfusion_ops_adverse_event_dashboard` | S | 혈액안전 → 수혈 반응·사건·조사 상태 / Blood safety → reaction/incident/investigation status |
| `blood_bank_transfusion_ops.donor_registration` | `v13_blood_bank_transfusion_ops_donor_registration` | C | 헌혈 접수 → 헌혈자 신원·동의·연락처 확인 → 등록 / Donation intake → verify donor identity/consent/contact → register |
| `blood_bank_transfusion_ops.donor_deferral_record` | `v13_blood_bank_transfusion_ops_donor_deferral_record` | C | 헌혈자 평가 → 사유·기간·검토자 확인 → 보류 기록 / Donor assessment → verify reason/duration/reviewer → record deferral |
| `blood_bank_transfusion_ops.collection_session_start` | `v13_blood_bank_transfusion_ops_collection_session_start` | C | 적격 헌혈자 → 채혈 키트·라벨·시각 확인 → 채혈 세션 시작 / Eligible donor → verify collection kit/labels/time → start collection session |
| `blood_bank_transfusion_ops.component_processing_record` | `v13_blood_bank_transfusion_ops_component_processing_record` | C | 채혈 단위 → 분리·가공·파생 성분 → 처리 기록 / Collected unit → separation/processing/derived components → record process |
| `blood_bank_transfusion_ops.test_result_verify` | `v13_blood_bank_transfusion_ops_test_result_verify` | C | 혈액 단위 → 감염성·혈액형 검사 결과 → 기술 검증 / Blood unit → infectious/typing test results → technical verification |
| `blood_bank_transfusion_ops.component_label_release` | `v13_blood_bank_transfusion_ops_component_label_release` | C | 검사 완료 성분 → 라벨·유효기간·출고 기준 확인 → 사용 가능 방출 / Tested component → verify label/expiration/release criteria → release for use |
| `blood_bank_transfusion_ops.unit_quarantine` | `v13_blood_bank_transfusion_ops_unit_quarantine` | C | 혈액 단위 → 이상·영향 범위·보관 위치 확인 → 격리 / Blood unit → verify deviation/scope/location → quarantine |
| `blood_bank_transfusion_ops.unit_recall` | `v13_blood_bank_transfusion_ops_unit_recall` | C | 배포 성분 → 수령 시설·추적 단위·사유 확인 → 회수 개시 / Distributed component → verify consignee/trace units/reason → initiate recall |
| `blood_bank_transfusion_ops.crossmatch_issue` | `v13_blood_bank_transfusion_ops_crossmatch_issue` | C | 환자 수혈 의뢰 → 환자·검체·성분 단위·적합성 확인 → 교차시험 출고 / Transfusion order → verify patient/specimen/unit/compatibility → issue crossmatched unit |
| `blood_bank_transfusion_ops.transfusion_issue` | `v13_blood_bank_transfusion_ops_transfusion_issue` | C | 배정 성분 → 수령인·임상 위치·운송 조건 확인 → 수혈용 인계 / Allocated component → verify receiver/clinical location/transport conditions → hand off for transfusion |
| `blood_bank_transfusion_ops.transfusion_start_record` | `v13_blood_bank_transfusion_ops_transfusion_start_record` | C | 병상 수혈 → 환자·성분·동의·시작 활력 확인 → 시작 기록 / Bedside transfusion → verify patient/component/consent/baseline vitals → record start |
| `blood_bank_transfusion_ops.transfusion_reaction_report` | `v13_blood_bank_transfusion_ops_transfusion_reaction_report` | C | 의심 수혈 반응 → 환자·단위·증상·조치 확인 → 반응 보고 / Suspected transfusion reaction → verify patient/unit/symptoms/actions → report reaction |
| `blood_bank_transfusion_ops.product_deviation_submit` | `v13_blood_bank_transfusion_ops_product_deviation_submit` | C | 혈액 제품 일탈 → 영향 제품·통제 시점·보고 기준 확인 → 규제 보고 제출 / Blood-product deviation → verify affected product/control/reportability → submit regulatory report |

역할·자산·상태: donor registrar, phlebotomist, blood-bank technologist, transfusion-medicine physician, quality officer, bedside nurse 역할을 구분한다. 핵심 자산은 donor, collection session, blood component unit, specimen, test result, transfusion order, recipient, storage equipment, reaction, product deviation이며, 상태는 `screened → eligible/deferred → collected → processed → tested → quarantined/released → allocated → issued → transfused/recalled → investigated/reported`다.

충돌군: `unit`(혈액 단위/측정 단위/UI 단위), `release`(사용 가능 방출/소프트웨어 배포/구금 해제), `issue`(출고/문제/발행), `order`(임상 수혈 지시/구매 주문), `deferral`(헌혈 보류/결제 연기), `quarantine`(혈액 제품 격리/보안 격리)을 대조한다.

공식 근거:

- eCFR, [21 CFR Part 606 — Current Good Manufacturing Practice for Blood and Blood Components](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-F/part-606) — 수집·가공·검사·보관·배포 기록, 오류·사고와 제품 일탈 경계.
- eCFR, [21 CFR Part 640 — Additional Standards for Human Blood and Blood Products](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-F/part-640) — 전혈·적혈구·혈장·혈소판 등 성분별 자산과 적격 상태.
- FDA, [Biologics Establishment Registration](https://www.fda.gov/vaccines-blood-biologics/guidance-compliance-regulatory-information-biologics/biologics-establishment-registration) — 혈액 제조 시설 등록과 제품 목록 수명주기.
- FDA, [Biological Product Deviations](https://www.fda.gov/vaccines-blood-biologics/report-problem-center-biologics-evaluation-research/biological-product-deviations) — 혈액 시설·수혈 서비스의 일탈 분류, 제출 주체와 기한.
- FDA, [An Acceptable Circular of Information for the Use of Human Blood and Blood Components](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/acceptable-circular-information-use-human-blood-and-blood-components) — 수혈용 성분 라벨·투여 정보와 사용 경계.
- CDC NHSN, [Hemovigilance Module](https://www.cdc.gov/nhsn/biovigilance/blood-safety/index.html) — 수혈 반응, TTI 경보·조사와 시설 보고 양식.

중복 제외: `clinical_care_team_ops`의 일반 처방·병상 기록과 `pharmacy_dispensing_ops`의 의약품 조제를 분리한다. donor eligibility, component unit, ABO/Rh·항체·교차시험, controlled storage, hemovigilance 중 두 축 이상이 없으면 이 도메인을 확정하지 않는다.

## 2. Organ-transplant coordination (`organ_transplant_coordination`)

허브: `organ_transplant_coordination.hub` — 장기이식 대기·배정 조정 / Organ-transplant waiting-list and allocation coordination

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `organ_transplant_coordination.candidate_worklist` | `v13_organ_transplant_coordination_candidate_worklist` | S | 이식 프로그램 → 장기별 후보·검토 기한 작업함 / Transplant program → organ-specific candidate/review-due worklist |
| `organ_transplant_coordination.candidate_status_review` | `v13_organ_transplant_coordination_candidate_status_review` | S | 이식 후보 → 활성·비활성·보류·제거 상태 이력 / Transplant candidate → active/inactive/hold/removal status history |
| `organ_transplant_coordination.wait_time_score_review` | `v13_organ_transplant_coordination_wait_time_score_review` | S | 후보 등록 → 대기시간·의학적 우선순위·예외 점수 / Candidate registration → waiting time/medical priority/exception score |
| `organ_transplant_coordination.donor_offer_queue` | `v13_organ_transplant_coordination_donor_offer_queue` | S | 기증자 사례 → 장기별 현재·예비 제안 대기열 / Donor case → organ-specific primary/backup offer queue |
| `organ_transplant_coordination.match_run_review` | `v13_organ_transplant_coordination_match_run_review` | S | 기증 장기 → 정책 버전·호환성·순위별 match run / Donor organ → policy version/compatibility/ranked match run |
| `organ_transplant_coordination.compatibility_result_review` | `v13_organ_transplant_coordination_compatibility_result_review` | S | 기증자·후보 쌍 → 혈액형·HLA·교차시험 결과 / Donor-candidate pair → blood type/HLA/crossmatch results |
| `organ_transplant_coordination.transport_logistics_view` | `v13_organ_transplant_coordination_transport_logistics_view` | S | 배정 장기 → 회수·포장·운송·도착 예정 추적 / Allocated organ → recovery/packaging/transport/ETA tracking |
| `organ_transplant_coordination.candidate_register` | `v13_organ_transplant_coordination_candidate_register` | C | 승인 이식 프로그램 → 후보·장기·필수 데이터 확인 → 대기명단 등록 / Approved transplant program → verify candidate/organ/required data → register on waiting list |
| `organ_transplant_coordination.candidate_activate` | `v13_organ_transplant_coordination_candidate_activate` | C | 비활성 후보 → 의학적 준비·동의·프로그램 승인 확인 → 활성화 / Inactive candidate → verify readiness/consent/program approval → activate |
| `organ_transplant_coordination.candidate_inactivate` | `v13_organ_transplant_coordination_candidate_inactivate` | C | 활성 후보 → 일시 부적합 사유·검토 기한 확인 → 비활성화 / Active candidate → verify temporary unsuitability/review date → inactivate |
| `organ_transplant_coordination.candidate_remove_waitlist` | `v13_organ_transplant_coordination_candidate_remove_waitlist` | C | 후보 등록 → 제거 사유·통지·권한 확인 → 대기명단 제거 / Candidate registration → verify removal reason/notice/authority → remove from waiting list |
| `organ_transplant_coordination.candidate_data_update` | `v13_organ_transplant_coordination_candidate_data_update` | C | 이식 후보 → 임상 지표·대기시간 기준·검증자 확인 → 갱신 / Transplant candidate → verify clinical metrics/wait-time basis/validator → update |
| `organ_transplant_coordination.exception_request_submit` | `v13_organ_transplant_coordination_exception_request_submit` | C | 후보 우선순위 → 근거·기간·검토위원회 확인 → 예외 요청 제출 / Candidate priority → verify evidence/duration/review board → submit exception request |
| `organ_transplant_coordination.donor_referral_record` | `v13_organ_transplant_coordination_donor_referral_record` | C | 잠재 기증자 → 의뢰 시설·동의 권한·임상 상태 확인 → 사례 생성 / Potential donor → verify referring facility/authorization/clinical state → create referral case |
| `organ_transplant_coordination.donor_data_verify` | `v13_organ_transplant_coordination_donor_data_verify` | C | 기증자 사례 → 혈액형·감염검사·장기 평가·이중 확인 → 검증 / Donor case → verify blood type/infectious tests/organ assessment/dual check → validate |
| `organ_transplant_coordination.organ_offer_response` | `v13_organ_transplant_coordination_organ_offer_response` | C | match run 제안 → 후보·장기·수락 기준·의사 권한 확인 → 수락·거절 응답 / Match-run offer → verify candidate/organ/acceptance criteria/physician authority → accept or decline |
| `organ_transplant_coordination.allocation_variance_report` | `v13_organ_transplant_coordination_allocation_variance_report` | C | 배정 순서 이탈 → 제안 순서·사유·영향 후보 확인 → 보고 / Allocation variance → verify offer sequence/reason/affected candidates → report |
| `organ_transplant_coordination.organ_recovery_handoff` | `v13_organ_transplant_coordination_organ_recovery_handoff` | C | 수락 장기 → 회수팀·기증자·장기·시간창 확인 → 회수 인계 / Accepted organ → verify recovery team/donor/organ/time window → hand off recovery |
| `organ_transplant_coordination.organ_transport_handoff` | `v13_organ_transplant_coordination_organ_transport_handoff` | C | 회수 장기 → 포장·봉인·보존시각·수령팀 확인 → 운송 인계 / Recovered organ → verify packaging/seal/preservation time/receiver → transport handoff |
| `organ_transplant_coordination.transplant_event_record` | `v13_organ_transplant_coordination_transplant_event_record` | C | 이식 사례 → 후보·기증자 장기·수술시각·결과 확인 → 이식 사건 기록 / Transplant case → verify candidate/donor organ/procedure time/outcome → record transplant event |

역할·자산·상태: transplant coordinator, transplant physician, organ procurement coordinator, histocompatibility specialist, allocation specialist, recovery team lead, transport coordinator 역할을 구분한다. 핵심 자산은 candidate registration, waiting-list status, donor case, donor organ, match run, organ offer, compatibility result, exception request, recovery handoff, transplant event이며, 상태는 `referred → evaluated → registered/inactive/active → ranked → offered → accepted/declined → recovered → transported → transplanted/not used → removed/reported`다.

충돌군: `candidate`(이식 후보/채용 후보/검색 후보), `match`(배정 순위/문자열 일치/데이트 상대), `offer`(장기 제안/상거래 할인), `allocation`(장기 배정/메모리·예산 배분), `active`(대기명단 활성/계정 활성), `recovery`(장기 회수/데이터 복구)를 대조한다.

공식 근거:

- HRSA OPTN, [Policies and bylaws](https://www.hrsa.gov/optn/policies-bylaws) — 이식병원·OPO·조직적합성 검사실에 적용되는 정책 주체와 규칙.
- HRSA OPTN, [OPTN Policies](https://www.hrsa.gov/sites/default/files/hrsa/optn/optn_policies.pdf) — 후보 등록·변경·제거, 장기 제안·수락·검증, 장기별 배정 lifecycle.
- HRSA OPTN, [Continuous Distribution](https://www.hrsa.gov/optn/policies-bylaws/policy-issues/continuous-distribution) — 기증자·후보 호환성과 정책 요소에 따른 전산 순위.
- HRSA OPTN, [Allocation Out of OPTN Sequence](https://www.hrsa.gov/optn/policies-bylaws/policy-issues/allocation-out-of-sequence-aoos) — 순차 제안 원칙, 이탈·낭비 예외와 보고 경계.
- HRSA OPTN, [Patient glossary](https://www.hrsa.gov/optn/patients/glossary) — candidate와 registration의 구분, active·inactive·removal과 waiting-time 상태.
- HRSA, [About the OPTN](https://www.hrsa.gov/optn/about) — OPTN Final Rule, 회원 역할과 이식 네트워크 권한 경계.

중복 제외: `clinical_care_team_ops`의 일반 환자 차트, `clinical_trial_site_ops`의 시험대상자, `maritime_port_logistics`의 운송을 분리한다. organ-specific candidate registration, match run, OPO/OPTN role, offer sequence, preservation handoff가 확인되지 않으면 이 도메인으로 진입하지 않는다.

## 3. Radiation-therapy operations (`radiation_therapy_ops`)

허브: `radiation_therapy_ops.hub` — 방사선치료 계획·투여 운영 / Radiation-therapy planning and delivery operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `radiation_therapy_ops.patient_course_queue` | `v13_radiation_therapy_ops_patient_course_queue` | S | 방사선종양 작업함 → 모의치료·계획·분할치료 단계별 환자 / Radiation-oncology worklist → patient by simulation/planning/fraction stage |
| `radiation_therapy_ops.prescription_review` | `v13_radiation_therapy_ops_prescription_review` | S | 치료 과정 → 처방 선량·분할수·부위·기법 검토 / Treatment course → prescription dose/fractions/site/technique review |
| `radiation_therapy_ops.simulation_image_review` | `v13_radiation_therapy_ops_simulation_image_review` | S | 환자 치료 과정 → 모의치료 영상·자세·고정 장치 / Patient course → simulation images/position/immobilization |
| `radiation_therapy_ops.treatment_plan_review` | `v13_radiation_therapy_ops_treatment_plan_review` | S | 계획 버전 → 빔·선량 분포·DVH·계산 상태 / Plan version → beams/dose distribution/DVH/calculation status |
| `radiation_therapy_ops.dose_constraint_review` | `v13_radiation_therapy_ops_dose_constraint_review` | S | 계획 → 표적·위험장기 제약·달성 여부 / Plan → target/organ-at-risk constraints/compliance |
| `radiation_therapy_ops.machine_qa_status` | `v13_radiation_therapy_ops_machine_qa_status` | S | 치료 장비 → 일일·월간 QA·교정·사용 가능 상태 / Treatment machine → daily/monthly QA/calibration/service status |
| `radiation_therapy_ops.fraction_history` | `v13_radiation_therapy_ops_fraction_history` | S | 치료 과정 → 예정·전달·중단 분할과 누적 선량 / Treatment course → scheduled/delivered/interrupted fractions and cumulative dose |
| `radiation_therapy_ops.patient_identity_site_verify` | `v13_radiation_therapy_ops_patient_identity_site_verify` | C | 예정 분할 → 환자·부위·계획 버전·자세 확인 → 치료 준비 검증 / Scheduled fraction → verify patient/site/plan version/position → treatment readiness check |
| `radiation_therapy_ops.prescription_sign` | `v13_radiation_therapy_ops_prescription_sign` | C | 방사선 처방 → 환자·부위·총선량·분할·의사 권한 확인 → 서명 / Radiation prescription → verify patient/site/total dose/fractions/authorized physician → sign |
| `radiation_therapy_ops.contour_approve` | `v13_radiation_therapy_ops_contour_approve` | C | 모의치료 영상 → 표적·위험장기·영상 세트 확인 → 윤곽 승인 / Simulation image set → verify targets/organs at risk/image set → approve contours |
| `radiation_therapy_ops.treatment_plan_approve` | `v13_radiation_therapy_ops_treatment_plan_approve` | C | 계산 완료 계획 → 처방·제약·기계·버전 확인 → 임상 승인 / Calculated plan → verify prescription/constraints/machine/version → clinical approval |
| `radiation_therapy_ops.dose_check_sign` | `v13_radiation_therapy_ops_dose_check_sign` | C | 승인 후보 계획 → 독립 계산·불일치·검토자 확인 → 선량검증 서명 / Plan pending approval → verify independent calculation/discrepancy/reviewer → sign dose check |
| `radiation_therapy_ops.physics_chart_check` | `v13_radiation_therapy_ops_physics_chart_check` | C | 치료 차트 → 처방·계획·기록·누적선량 확인 → 물리 검토 완료 / Treatment chart → verify prescription/plan/record/cumulative dose → complete physics check |
| `radiation_therapy_ops.machine_qa_record` | `v13_radiation_therapy_ops_machine_qa_record` | C | 치료 장비 QA → 측정·허용기준·이상·조치 확인 → 결과 기록 / Treatment-machine QA → verify measurement/tolerance/deviation/action → record result |
| `radiation_therapy_ops.schedule_release` | `v13_radiation_therapy_ops_schedule_release` | C | 승인 치료 과정 → 장비·분할 일정·준비 상태 확인 → 치료 일정 방출 / Approved course → verify machine/fraction schedule/readiness → release schedule |
| `radiation_therapy_ops.fraction_delivery_authorize` | `v13_radiation_therapy_ops_fraction_delivery_authorize` | C | 치료실 세션 → 환자·부위·영상 유도·인터록 확인 → 분할 투여 승인 / Treatment-room session → verify patient/site/image guidance/interlocks → authorize fraction delivery |
| `radiation_therapy_ops.fraction_delivery_record` | `v13_radiation_therapy_ops_fraction_delivery_record` | C | 완료 분할 → 실제 MU·선량·시간·중단 여부 확인 → 투여 기록 / Completed fraction → verify delivered MU/dose/time/interruption → record delivery |
| `radiation_therapy_ops.adaptive_plan_replace` | `v13_radiation_therapy_ops_adaptive_plan_replace` | C | 활성 치료 과정 → 재계획 근거·새 버전·잔여 분할 확인 → 계획 교체 / Active course → verify replanning basis/new version/remaining fractions → replace plan |
| `radiation_therapy_ops.course_complete` | `v13_radiation_therapy_ops_course_complete` | C | 치료 과정 → 처방 분할·미완료·최종 선량·후속조치 확인 → 완료 / Treatment course → verify prescribed fractions/open items/final dose/follow-up → complete |
| `radiation_therapy_ops.medical_event_report` | `v13_radiation_therapy_ops_medical_event_report` | C | 의심 의료 사건 → 처방·실제 투여·기준·통지 확인 → 규제 보고 / Suspected medical event → verify directive/delivery/threshold/notifications → regulatory report |

역할·자산·상태: radiation oncologist, dosimetrist, medical physicist, radiation therapist, radiation safety officer, treatment-unit administrator 역할을 구분한다. 핵심 자산은 patient treatment course, written directive, simulation image set, contour set, plan version, dose constraint, treatment machine, QA result, fraction record, medical event이며, 상태는 `referred → simulated → contoured → planned/calculated → checked → approved → scheduled → positioned → delivered/interrupted → adapted → completed/reported`다.

충돌군: `course`(치료 과정/교육 과정), `plan`(방사선 계획/일반 할 일), `fraction`(분할치료/수학 분수), `beam`(방사선 빔/구조 보), `dose`(흡수선량/약물 용량), `directive`(서면 처방/소프트웨어 지시문), `medical event`(규제 정의 사건/일반 진료 일정)을 대조한다.

공식 근거:

- NRC, [Medical Uses Licensee Toolkit](https://www.nrc.gov/materials/miau/med-use-toolkit) — authorized user·medical physicist·RSO 역할, 의료용 물질 허가·검사·사건 보고.
- eCFR, [10 CFR Part 35 — Medical Use of Byproduct Material](https://www.ecfr.gov/current/title-10/chapter-I/part-35) — written directive, 치료 절차, 기록·보고의 규제 경계.
- NRC, [10 CFR 35.40 — Written directives](https://www.nrc.gov/reading-rm/doc-collections/cfr/part035/part035-0040.html) — 환자·치료 부위·선량·분할을 포함한 지시 작성·서명.
- NRC, [10 CFR 35.41 — Procedures for administrations requiring a written directive](https://www.nrc.gov/reading-rm/doc-collections/cfr/part035/part035-0041.html) — 투여 전 신원·지시 일치 검증과 오류 방지 절차.
- NRC, [10 CFR 35.3045 — Report and notification of a medical event](https://www.nrc.gov/reading-rm/doc-collections/cfr/part035/part035-3045.html) — 의료 사건 임계치, 통지·기록·보고 lifecycle.
- IAEA, [Setting Up a Radiotherapy Programme](https://www-pub.iaea.org/MTCD/Publications/PDF/pub1296_web.pdf) — 다직종 계획·QA·장비·치료 전달과 환자안전 단계.

중복 제외: `clinical_care_team_ops`의 일반 처방·진료 기록과 `laboratory_research_ops`의 비임상 방사선 사용을 분리한다. prescribed dose/fractions, plan version, treatment unit, image guidance, physics QA 중 두 축 이상이 없으면 방사선치료 terminal을 선택하지 않는다.

## 4. Court-clerk case administration (`court_clerk_case_admin`)

허브: `court_clerk_case_admin.hub` — 법원 서기 사건·도켓 행정 / Court-clerk case and docket administration

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `court_clerk_case_admin.case_intake_queue` | `v13_court_clerk_case_admin_case_intake_queue` | S | 법원 접수 → 사건유형·관할·접수시각별 신규 사건 / Court intake → new matters by case type/jurisdiction/received time |
| `court_clerk_case_admin.docket_sheet_view` | `v13_court_clerk_case_admin_docket_sheet_view` | S | 사건 기록 → 번호·당사자·도켓 항목·현재 상태 / Case record → number/parties/docket entries/current status |
| `court_clerk_case_admin.filing_deficiency_queue` | `v13_court_clerk_case_admin_filing_deficiency_queue` | S | 전자 제출 → 누락·형식 오류·수정 기한 작업함 / Electronic filings → missing/format error/correction-due queue |
| `court_clerk_case_admin.fee_payment_status` | `v13_court_clerk_case_admin_fee_payment_status` | S | 사건 비용 → 납부·면제 신청·환불·미결 상태 / Case fees → paid/waiver request/refund/pending status |
| `court_clerk_case_admin.service_notice_status` | `v13_court_clerk_case_admin_service_notice_status` | S | 도켓 항목 → NEF·송달 대상·전송·반송 상태 / Docket entry → NEF/service recipients/transmission/bounce status |
| `court_clerk_case_admin.calendar_deadline_view` | `v13_court_clerk_case_admin_calendar_deadline_view` | S | 사건 일정 → 심리·답변·제출·판결 기한 / Case calendar → hearing/response/filing/judgment deadlines |
| `court_clerk_case_admin.sealed_document_access_review` | `v13_court_clerk_case_admin_sealed_document_access_review` | S | 봉인 기록 → 봉인 근거·허용 역할·접근 로그 / Sealed record → sealing basis/authorized role/access log |
| `court_clerk_case_admin.case_open` | `v13_court_clerk_case_admin_case_open` | C | 접수 문서 → 법원·사건유형·당사자·비용 확인 → 사건 개설 / Intake document → verify court/case type/parties/fee → open case |
| `court_clerk_case_admin.party_attorney_update` | `v13_court_clerk_case_admin_party_attorney_update` | C | 사건 → 당사자·대리인·출석·송달 주소 확인 → 참가자 갱신 / Case → verify party/counsel/appearance/service address → update participant |
| `court_clerk_case_admin.filing_docket_entry` | `v13_court_clerk_case_admin_filing_docket_entry` | C | 제출 문서 → 사건·event type·문서·접수시각 확인 → 도켓 반영 / Submitted filing → verify case/event type/document/received time → docket entry |
| `court_clerk_case_admin.filing_reject_deficiency` | `v13_court_clerk_case_admin_filing_reject_deficiency` | C | 제출 문서 → 결함·근거·수정 방법·기한 확인 → 결함 통지 / Submitted filing → verify deficiency/basis/cure method/deadline → issue deficiency notice |
| `court_clerk_case_admin.fee_waiver_route` | `v13_court_clerk_case_admin_fee_waiver_route` | C | 비용 면제 신청 → 사건·서류·결정권자 확인 → 심사 경로 지정 / Fee-waiver application → verify case/documents/decision authority → route for review |
| `court_clerk_case_admin.summons_issue` | `v13_court_clerk_case_admin_summons_issue` | C | 개설 사건 → 당사자·법원 인장·응답 기한 확인 → 소환장 발행 / Open case → verify party/court seal/response deadline → issue summons |
| `court_clerk_case_admin.notice_send` | `v13_court_clerk_case_admin_notice_send` | C | 도켓 사건 → 수신자·문서·송달 예외 확인 → 전자 통지 전송 / Docket event → verify recipients/document/service exceptions → send electronic notice |
| `court_clerk_case_admin.deadline_update` | `v13_court_clerk_case_admin_deadline_update` | C | 사건 일정 → 법원 명령·기존 기한·새 기한 확인 → 변경 / Case calendar → verify court order/current due date/new due date → update |
| `court_clerk_case_admin.hearing_calendar_set` | `v13_court_clerk_case_admin_hearing_calendar_set` | C | 사건 → 재판부·심리 유형·시간·법정 확인 → 일정 확정 / Case → verify judge/hearing type/time/courtroom → set calendar |
| `court_clerk_case_admin.document_seal_unseal` | `v13_court_clerk_case_admin_document_seal_unseal` | C | 사건 문서 → 명령·봉인 범위·공개 버전 확인 → 봉인·해제 / Case document → verify order/sealing scope/public version → seal or unseal |
| `court_clerk_case_admin.order_judgment_enter` | `v13_court_clerk_case_admin_order_judgment_enter` | C | 서명 명령·판결 → 사건·재판관·발효일 확인 → 도켓 입력 / Signed order or judgment → verify case/judge/effective date → enter on docket |
| `court_clerk_case_admin.case_transfer` | `v13_court_clerk_case_admin_case_transfer` | C | 사건 → 이송 명령·목적 법원·기록 묶음 확인 → 이송 / Case → verify transfer order/destination court/record package → transfer |
| `court_clerk_case_admin.case_close` | `v13_court_clerk_case_admin_case_close` | C | 사건 → 종결 명령·미결 제출·비용·보존 분류 확인 → 종결 / Case → verify closing order/open filings/fees/retention class → close |

역할·자산·상태: intake clerk, docket clerk, courtroom deputy, records clerk, financial deputy, clerk supervisor, judge as decision authority 역할을 구분한다. 핵심 자산은 case, filing, docket entry, party, counsel, fee, summons, electronic notice, hearing, order, judgment, sealed document이며, 상태는 `received → deficient/accepted → opened → filed/docketed → noticed → scheduled → decided/entered → transferred/closed → retained/archived`다.

충돌군: `case`(법원 사건/복지·보험·고객 사례), `docket`(법원 도켓/일반 할 일 목록), `file`(제출/파일 객체), `serve`(법적 송달/음식 제공/서버 운영), `issue`(소환장 발행/문제), `enter`(도켓 입력/UI 입력), `seal`(봉인/포장 봉인)을 대조한다.

공식 근거:

- Administrative Office of the U.S. Courts, [Electronic Filing (CM/ECF)](https://www.uscourts.gov/court-records/electronic-filing-cm-ecf) — 제출 권한, 전자 사건파일, PACER와 개인정보 삭제 경계.
- Administrative Office of the U.S. Courts, [CM/ECF FAQs](https://www.uscourts.gov/court-records/file-a-case-cm-ecf/faqs-case-management-electronic-case-files-cm-ecf) — 도켓 갱신, Notice of Electronic Filing, 참가자 통지 lifecycle.
- PACER, [File a Case](https://pacer.uscourts.gov/file-case) — 법원별 e-file 승인, 사건 개설, 시스템 중단·대체 절차.
- PACER, [How to Use CM/ECF](https://pacer.uscourts.gov/help/cmecf) — 사건유형별 사용자 문서와 제출·계정 역할.
- Administrative Office of the U.S. Courts, [Find a Case (PACER)](https://www.uscourts.gov/court-records/find-a-case-pacer) — 공식 case/docket 조회와 법원별 기록 경계.
- U.S. District Court for the District of Oregon, [CM/ECF User Manual](https://ord.uscourts.gov/index.php/filing-and-forms/cm-ecf/user-manual) — 사건·문서·도켓·통지·공개 접근 객체와 상태.

중복 제외: `legal_practice_ops`의 변호사 matter·의뢰인 업무와 `estate_probate_administration`의 검인 신청을 분리한다. court-issued case number, clerk role, official docket event, NEF/service, signed judicial order가 확인되지 않으면 법원 서기 terminal로 확정하지 않는다.

## 5. IP prosecution docketing (`ip_prosecution_docketing`)

허브: `ip_prosecution_docketing.hub` — 특허·상표 출원 도켓 관리 / Patent and trademark prosecution docketing

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `ip_prosecution_docketing.matter_docket_view` | `v13_ip_prosecution_docketing_matter_docket_view` | S | 지식재산 도켓 → 특허·상표 matter·기한·담당자 / IP docket → patent/trademark matter/deadline/owner |
| `ip_prosecution_docketing.patent_application_status` | `v13_ip_prosecution_docketing_patent_application_status` | S | 특허 출원 → application number·제출·심사·허여 상태 / Patent application → application number/filing/examination/allowance status |
| `ip_prosecution_docketing.trademark_application_status` | `v13_ip_prosecution_docketing_trademark_application_status` | S | 상표 출원·등록 → serial/registration number·TSDR 상태 / Trademark application or registration → serial/registration number/TSDR status |
| `ip_prosecution_docketing.office_action_deadline_view` | `v13_ip_prosecution_docketing_office_action_deadline_view` | S | 관청 통지 → 응답 유형·법정 기한·연장 가능성 / Office correspondence → response type/statutory deadline/extension availability |
| `ip_prosecution_docketing.correspondence_review` | `v13_ip_prosecution_docketing_correspondence_review` | S | 출원 기록 → Office action·notice·receipt·certificate 문서 / Application file → office action/notice/receipt/certificate documents |
| `ip_prosecution_docketing.fee_status_view` | `v13_ip_prosecution_docketing_fee_status_view` | S | 출원·등록 → 관납료 항목·납부 상태·기한 / Application or registration → official fee item/payment status/due date |
| `ip_prosecution_docketing.ownership_record_view` | `v13_ip_prosecution_docketing_ownership_record_view` | S | 권리 기록 → 출원인·소유자·양도·담보 이력 / Rights record → applicant/owner/assignment/security-interest history |
| `ip_prosecution_docketing.patent_application_prepare` | `v13_ip_prosecution_docketing_patent_application_prepare` | C | 특허 matter → 발명자·출원인·명세서·청구항·우선권 확인 → 제출본 준비 / Patent matter → verify inventors/applicant/specification/claims/priority → prepare filing |
| `ip_prosecution_docketing.patent_submission_file` | `v13_ip_prosecution_docketing_patent_submission_file` | C | Patent Center 제출 → 출원유형·문서·서명·수수료 확인 → 전자 제출 / Patent Center submission → verify application type/documents/signature/fees → file electronically |
| `ip_prosecution_docketing.patent_office_action_response` | `v13_ip_prosecution_docketing_patent_office_action_response` | C | 특허 Office action → 출원·쟁점·보정·기한 확인 → 응답 제출 / Patent office action → verify application/issues/amendment/deadline → submit response |
| `ip_prosecution_docketing.patent_fee_pay` | `v13_ip_prosecution_docketing_patent_fee_pay` | C | 특허 출원 → fee code·entity status·금액·기한 확인 → 관납료 납부 / Patent application → verify fee code/entity status/amount/deadline → pay official fee |
| `ip_prosecution_docketing.trademark_application_prepare` | `v13_ip_prosecution_docketing_trademark_application_prepare` | C | 상표 matter → 소유자·표장·상품서비스·출원 근거 확인 → 신청 준비 / Trademark matter → verify owner/mark/goods-services/filing basis → prepare application |
| `ip_prosecution_docketing.trademark_application_file` | `v13_ip_prosecution_docketing_trademark_application_file` | C | Trademark Center → 신청인·표장·class·specimen·서명 확인 → 출원 / Trademark Center → verify applicant/mark/classes/specimen/signature → file application |
| `ip_prosecution_docketing.trademark_office_action_response` | `v13_ip_prosecution_docketing_trademark_office_action_response` | C | 상표 Office action → serial·거절사유·증거·기한 확인 → 응답 제출 / Trademark office action → verify serial/refusal/evidence/deadline → submit response |
| `ip_prosecution_docketing.trademark_statement_use_file` | `v13_ip_prosecution_docketing_trademark_statement_use_file` | C | 사용의도 출원 → 사용일·specimen·class·선언 확인 → 사용 진술 제출 / Intent-to-use application → verify dates/specimen/classes/declaration → file statement of use |
| `ip_prosecution_docketing.trademark_maintenance_file` | `v13_ip_prosecution_docketing_trademark_maintenance_file` | C | 상표 등록 → Section 8/9/15·사용 증거·기한 확인 → 유지·갱신 제출 / Trademark registration → verify Section 8/9/15/use evidence/window → file maintenance or renewal |
| `ip_prosecution_docketing.assignment_record_submit` | `v13_ip_prosecution_docketing_assignment_record_submit` | C | 특허·상표 권리 → 양도인·양수인·실행 문서·대상 확인 → 소유권 기록 제출 / Patent or trademark right → verify assignor/assignee/executed document/property → submit ownership record |
| `ip_prosecution_docketing.correspondence_change_submit` | `v13_ip_prosecution_docketing_correspondence_change_submit` | C | 출원·등록 → correspondence owner·주소·대리권 확인 → 변경 제출 / Application or registration → verify correspondence owner/address/authority → submit change |
| `ip_prosecution_docketing.extension_petition_file` | `v13_ip_prosecution_docketing_extension_petition_file` | C | 법정 기한 → 허용 근거·기간·fee·서명 확인 → 연장·petition 제출 / Official deadline → verify basis/period/fee/signature → file extension or petition |
| `ip_prosecution_docketing.matter_docket_close` | `v13_ip_prosecution_docketing_matter_docket_close` | C | IP matter → 등록·포기·만료·후속기한·보존 확인 → 도켓 종결 / IP matter → verify registration/abandonment/expiry/future deadlines/retention → close docket |

역할·자산·상태: patent attorney, patent agent, trademark attorney, docket specialist, applicant or owner, inventor, authorized signatory 역할을 구분한다. 핵심 자산은 IP matter, patent application, trademark application, registration, office action, response, official fee, deadline, specimen, assignment record, correspondence record이며, 상태는 `drafted → filed → formalities review → published/examined → office action → response pending/filed → allowed/registered → maintained/renewed → abandoned/expired/closed`다.

충돌군: `application`(특허·상표 출원/앱 프로그램/일반 신청), `claim`(특허 청구항/보험 청구), `office action`(관청 심사통지/사내 조치), `class`(상품서비스 국제분류/프로그래밍 클래스), `specimen`(상표 사용 증거/임상·연구 검체), `assignment`(권리 양도/업무 배정), `maintenance`(상표 유지/설비 정비)를 대조한다.

공식 근거:

- USPTO, [Patent Center](https://www.uspto.gov/patents/apply/patent-center) — 특허 전자 제출, 비공개 출원 조회, 대응 문서·receipt·fee 상태.
- USPTO, [Manual of Patent Examining Procedure](https://www.uspto.gov/web/offices/pac/mpep/index.html) — 특허 출원·심사·응답·허여·포기 절차의 공식 기준.
- USPTO, [Trademarks](https://www.uspto.gov/trademarks) — Trademark Center, TEAS, TSDR, TMEP, Assignment Center의 공식 업무 경계.
- USPTO, [Apply online](https://www.uspto.gov/trademarks/apply) — 신규 상표 신청, Office action 응답, 전자 서명·기한·시스템 중단 대체 경로.
- USPTO, [Online trademark tools](https://www.uspto.gov/trademarks/basics/online-tools) — Trademark Center 신청·도켓, TEAS 후속 양식, TSDR 상태·문서.
- USPTO, [Maintaining your federal registration](https://www.uspto.gov/trademarks/basics/maintaining-registration) — Section 8·9·15 유지 제출, 기간·증거·만료 상태.

중복 제외: `legal_practice_ops`의 일반 client matter·문서 제출과 `code_repository`의 code review를 분리한다. USPTO application/serial number, Patent Center·Trademark Center·TSDR, statutory prosecution deadline, office action 또는 registration maintenance가 없으면 이 도메인을 확정하지 않는다.

## 6. Food-establishment inspection (`food_establishment_inspection`)

허브: `food_establishment_inspection.hub` — 식품업소 위생 점검·집행 / Food-establishment safety inspection and enforcement

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `food_establishment_inspection.establishment_risk_queue` | `v13_food_establishment_inspection_establishment_risk_queue` | S | 관할 업소 → 위험등급·점검주기·기한 작업함 / Jurisdiction establishments → risk category/inspection frequency/due queue |
| `food_establishment_inspection.permit_status_view` | `v13_food_establishment_inspection_permit_status_view` | S | 식품업소 → permit·조건·유효기간·집행 상태 / Food establishment → permit/conditions/expiration/enforcement status |
| `food_establishment_inspection.prior_inspection_review` | `v13_food_establishment_inspection_prior_inspection_review` | S | 업소 기록 → 이전 위반·시정·재점검 이력 / Establishment file → prior violations/corrections/reinspection history |
| `food_establishment_inspection.plan_review_status` | `v13_food_establishment_inspection_plan_review_status` | S | 신규·변경 업소 → 평면도·장비·배관·HACCP 검토 / New or remodeled establishment → plans/equipment/plumbing/HACCP review |
| `food_establishment_inspection.food_code_reference` | `v13_food_establishment_inspection_food_code_reference` | S | 점검 항목 → 관할 Food Code 조항·priority 분류 / Inspection item → jurisdiction Food Code provision/priority designation |
| `food_establishment_inspection.sampling_result_review` | `v13_food_establishment_inspection_sampling_result_review` | S | 업소·식품·환경 검체 → 채취·시험·결과·영향 범위 / Establishment food or environmental sample → collection/test/result/affected scope |
| `food_establishment_inspection.complaint_outbreak_queue` | `v13_food_establishment_inspection_complaint_outbreak_queue` | S | 민원·질병 신호 → 업소·노출일·우선순위·조사 상태 / Complaint or illness signal → establishment/exposure date/priority/investigation state |
| `food_establishment_inspection.inspection_checkin` | `v13_food_establishment_inspection_inspection_checkin` | C | 예정 점검 → 자격증명·업소·점검 유형·도착시각 확인 → 현장 시작 / Scheduled inspection → verify credential/establishment/type/arrival time → start visit |
| `food_establishment_inspection.person_in_charge_verify` | `v13_food_establishment_inspection_person_in_charge_verify` | C | 현장 점검 → person in charge·권한·식품안전 지식 확인 → 책임자 기록 / On-site inspection → verify person in charge/authority/food-safety knowledge → record PIC |
| `food_establishment_inspection.temperature_observation_record` | `v13_food_establishment_inspection_temperature_observation_record` | C | 식품 공정 → 식품·단계·측정기·시간온도 확인 → 관찰 기록 / Food process → verify item/stage/instrument/time-temperature → record observation |
| `food_establishment_inspection.employee_health_observation_record` | `v13_food_establishment_inspection_employee_health_observation_record` | C | 종사자 건강관리 → 증상·보고·제외·제한 상태 확인 → 관찰 기록 / Employee health control → verify symptom/reporting/exclusion/restriction status → record observation |
| `food_establishment_inspection.sanitation_violation_record` | `v13_food_establishment_inspection_sanitation_violation_record` | C | 시설·장비 → 오염·세척·해충·배관 사실과 코드 확인 → 위반 기록 / Facility or equipment → verify contamination/cleaning/pest/plumbing facts and code → record violation |
| `food_establishment_inspection.risk_factor_classify` | `v13_food_establishment_inspection_risk_factor_classify` | C | 관찰 항목 → IN/OUT/NA/NO·priority·공중보건 근거 확인 → 분류 / Observed item → verify IN/OUT/NA/NO/priority/public-health basis → classify |
| `food_establishment_inspection.onsite_correction_record` | `v13_food_establishment_inspection_onsite_correction_record` | C | 위반 항목 → 시정 주체·조치·재측정·시각 확인 → 현장 시정 기록 / Violation → verify responsible person/action/recheck/time → record on-site correction |
| `food_establishment_inspection.product_disposition_order` | `v13_food_establishment_inspection_product_disposition_order` | C | 위해 식품 → 품목·수량·위험·법적 권한 확인 → 보류·폐기 명령 / Hazardous food → verify item/quantity/risk/legal authority → order hold or disposal |
| `food_establishment_inspection.inspection_report_issue` | `v13_food_establishment_inspection_inspection_report_issue` | C | 완료 점검 → 업소·관찰·코드·시정기한·수령인 확인 → 보고서 발행 / Completed inspection → verify establishment/findings/code/correction dates/recipient → issue report |
| `food_establishment_inspection.corrective_action_plan_accept` | `v13_food_establishment_inspection_corrective_action_plan_accept` | C | 반복 위험요인 → 원인·통제·책임자·검증 일정 확인 → 시정계획 수락 / Recurrent risk factor → verify cause/controls/owner/verification schedule → accept corrective plan |
| `food_establishment_inspection.reinspection_schedule` | `v13_food_establishment_inspection_reinspection_schedule` | C | 미시정 업소 → 위반 위험·법정 기한·검사자 확인 → 재점검 확정 / Noncompliant establishment → verify violation risk/statutory due date/inspector → schedule reinspection |
| `food_establishment_inspection.permit_suspension_recommend` | `v13_food_establishment_inspection_permit_suspension_recommend` | C | 중대·반복 위반 → 증거·즉시 위해·청문 권리·권한 확인 → 정지 권고 / Serious or repeated violation → verify evidence/imminent hazard/hearing rights/authority → recommend suspension |
| `food_establishment_inspection.case_close_compliance` | `v13_food_establishment_inspection_case_close_compliance` | C | 집행 사례 → 모든 위반·시정 증거·재점검·감독 승인 확인 → 준수 종결 / Enforcement case → verify all violations/correction evidence/reinspection/supervisor approval → close compliant |

역할·자산·상태: food-safety inspector, standardization officer, plan reviewer, program supervisor, epidemiologist, permit or hearing official 역할을 구분한다. 핵심 자산은 food establishment, permit, plan set, inspection, Food Code item, risk factor, food or environmental sample, violation, corrective action plan, enforcement case이며, 상태는 `permitted → inspection due → in progress → in/out of compliance → corrected/held → report issued → reinspection/enforcement → compliant/suspended → closed`다.

충돌군: `inspection`(식품 규제 점검/제조 품질검사/건물검사), `permit`(식품업 영업허가/runtime permission), `hold`(식품 보류/결제·법적 보류), `code`(Food Code/소프트웨어 코드), `score`(위험 점수/신용·게임 점수), `plan review`(식품 시설 도면/프로젝트 계획)을 대조한다.

공식 근거:

- FDA, [Food Code 2022](https://www.fda.gov/food/fda-food-code/food-code-2022) — 식품업소 허가·계획 검토·점검·위반·시정·집행의 모델 규정.
- FDA, [Retail Food Protection](https://www.fda.gov/food/guidance-regulation-food-and-dietary-supplements/retail-food-protection) — 규제기관·점검자·업소 역할과 위험기반 점검 범위.
- FDA, [Voluntary National Retail Food Regulatory Program Standards](https://www.fda.gov/food/retail-food-protection/voluntary-national-retail-food-regulatory-program-standards) — 교육, HACCP 기반 점검, uniform inspection, compliance and enforcement 체계.
- FDA, [Standard 4 — Uniform Inspection Program](https://www.fda.gov/media/86785/download) — 업소 파일 사전 검토, 현장 관찰, 보고서·시정 기록과 품질 검토.
- FDA, [Standard 6 — Compliance and Enforcement](https://www.fda.gov/media/86829/download) — 경고·재점검·벌금·permit suspension·청문 등 후속 상태.
- FDA, [Food Establishment Plan Review Guide](https://www.fda.gov/food/retail-food-industryregulatory-assistance-training/food-establishment-plan-review-guide) — 신규·변경 업소의 평면도·장비·기계·배관 사전 검토.

중복 제외: `restaurant_service_ops`의 주문·주방 서비스와 `manufacturing_quality_ops`의 공장 품질검사를 분리한다. credentialed regulator, jurisdiction permit, Food Code citation, IN/OUT risk-factor finding, correction/enforcement lifecycle가 없으면 이 도메인으로 분류하지 않는다.

## 7. Building-permit and code enforcement (`building_permit_code_enforcement`)

허브: `building_permit_code_enforcement.hub` — 건축 허가·검사·법규 집행 / Building permitting, inspection, and code enforcement

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `building_permit_code_enforcement.application_queue` | `v13_building_permit_code_enforcement_application_queue` | S | 건축부서 작업함 → 신규·변경·보완 신청과 검토 기한 / Building department queue → new/amended/correction applications and review due dates |
| `building_permit_code_enforcement.parcel_project_profile` | `v13_building_permit_code_enforcement_parcel_project_profile` | S | 대지·건물 → 주소·소유자·용도·job·허가 연결 / Parcel or building → address/owner/use/jobs/permit relationships |
| `building_permit_code_enforcement.plan_set_review` | `v13_building_permit_code_enforcement_plan_set_review` | S | 신청 → 설계도서·revision·전문가 서명·검토 상태 / Application → plan set/revision/professional seal/review status |
| `building_permit_code_enforcement.zoning_code_status` | `v13_building_permit_code_enforcement_zoning_code_status` | S | 프로젝트 → zoning·건축법규·예외·objection 상태 / Project → zoning/building-code/variance/objection status |
| `building_permit_code_enforcement.permit_status_view` | `v13_building_permit_code_enforcement_permit_status_view` | S | 건축 permit → 범위·contractor·발행·만료·보류 / Building permit → scope/contractor/issued/expiration/hold |
| `building_permit_code_enforcement.inspection_history` | `v13_building_permit_code_enforcement_inspection_history` | S | permit·job → 요구 검사·예약·pass/fail·sign-off 이력 / Permit or job → required inspections/schedule/pass-fail/sign-off history |
| `building_permit_code_enforcement.violation_complaint_view` | `v13_building_permit_code_enforcement_violation_complaint_view` | S | 건물 → 민원·violation·stop-work·시정 상태 / Building → complaint/violation/stop-work/correction status |
| `building_permit_code_enforcement.application_intake_accept` | `v13_building_permit_code_enforcement_application_intake_accept` | C | 제출 신청 → parcel·scope·신청인·필수 문서 확인 → 접수 / Submitted application → verify parcel/scope/applicant/required documents → accept intake |
| `building_permit_code_enforcement.plan_review_comment_issue` | `v13_building_permit_code_enforcement_plan_review_comment_issue` | C | 도면 세트 → code section·sheet·objection·검토자 확인 → 보완 의견 발행 / Plan set → verify code section/sheet/objection/reviewer → issue correction comment |
| `building_permit_code_enforcement.plan_revision_accept` | `v13_building_permit_code_enforcement_plan_revision_accept` | C | 수정 도면 → revision·응답·전문가 seal·남은 objection 확인 → 수락 / Revised plans → verify revision/responses/professional seal/open objections → accept |
| `building_permit_code_enforcement.permit_issue` | `v13_building_permit_code_enforcement_permit_issue` | C | 승인 신청 → 범위·licensee·보험·fee·선행조건 확인 → permit 발행 / Approved application → verify scope/licensee/insurance/fees/prerequisites → issue permit |
| `building_permit_code_enforcement.permit_amend` | `v13_building_permit_code_enforcement_permit_amend` | C | 활성 permit → 변경 범위·도면·비용·영향 검사 확인 → 수정 / Active permit → verify changed scope/plans/fees/affected inspections → amend |
| `building_permit_code_enforcement.inspection_schedule` | `v13_building_permit_code_enforcement_inspection_schedule` | C | permit → 검사 유형·공사 단계·현장 연락처·검사자 확인 → 예약 / Permit → verify inspection type/work stage/site contact/inspector → schedule |
| `building_permit_code_enforcement.inspection_result_record` | `v13_building_permit_code_enforcement_inspection_result_record` | C | 현장 검사 → permit·scope·관찰·code·pass/fail 확인 → 결과 기록 / Field inspection → verify permit/scope/observations/code/pass-fail → record result |
| `building_permit_code_enforcement.stop_work_order_issue` | `v13_building_permit_code_enforcement_stop_work_order_issue` | C | 현장 위반 → 위치·작업·즉시 위험·법적 권한 확인 → 작업중지 명령 / Site violation → verify location/work/immediate hazard/legal authority → issue stop-work order |
| `building_permit_code_enforcement.violation_notice_issue` | `v13_building_permit_code_enforcement_violation_notice_issue` | C | 건물 위반 → owner·code·증거·시정기한·이의절차 확인 → 통지 / Building violation → verify owner/code/evidence/cure date/appeal process → issue notice |
| `building_permit_code_enforcement.corrective_action_verify` | `v13_building_permit_code_enforcement_corrective_action_verify` | C | 미시정 위반 → 수리·사진·재검사·code 준수 확인 → 시정 검증 / Open violation → verify repair/evidence/reinspection/code compliance → verify correction |
| `building_permit_code_enforcement.permit_reinstate` | `v13_building_permit_code_enforcement_permit_reinstate` | C | 보류·만료 permit → 시정·보험·fee·승인 확인 → 복구 / Suspended or expired permit → verify correction/insurance/fees/approval → reinstate |
| `building_permit_code_enforcement.certificate_occupancy_recommend` | `v13_building_permit_code_enforcement_certificate_occupancy_recommend` | C | 완료 job → 도면 일치·필수 sign-off·미결 violation 확인 → 점유 승인 권고 / Completed job → verify plan conformity/required sign-offs/open violations → recommend occupancy |
| `building_permit_code_enforcement.certificate_occupancy_issue` | `v13_building_permit_code_enforcement_certificate_occupancy_issue` | C | 점유 요청 → 승인 용도·최종 검사·기관 승인·fee 확인 → CO 발행 / Occupancy request → verify approved use/final inspections/agency approvals/fees → issue certificate |

역할·자산·상태: owner, filing representative, registered design professional, plan examiner, building inspector, code official, certificate-of-occupancy reviewer 역할을 구분한다. 핵심 자산은 parcel, building, job application, plan set, objection, permit, inspection, violation, stop-work order, schedule of occupancy, certificate of occupancy이며, 상태는 `draft → submitted → under review/objections → approved → permit issued → work active → inspection failed/passed → signed off → occupancy pending/issued → closed`다.

충돌군: `build`(건축 공사/소프트웨어 빌드), `job`(건축 신청/채용·백그라운드 작업), `plan`(설계도서/일반 계획), `issue`(permit 발행/문제), `inspection`(건축/식품/품질), `occupancy`(법적 점유/숙박 객실 사용), `sign-off`(검사 승인/로그아웃)을 대조한다.

공식 근거:

- NYC Department of Buildings, [Building Applications & Permits](https://www.nyc.gov/site/buildings/dob/building-applications-permits.page) — application, job, plan review, permit, certificate 데이터 객체.
- NYC Department of Buildings, [DOB NOW](https://www.nyc.gov/site/buildings/property-or-business-owner/dob-now.page) — 신청·납부·검사 예약·permit 발급·갱신·CO 요청 기능 경계.
- NYC Department of Buildings, [Permits by Type](https://www.nyc.gov/site/buildings/property-or-business-owner/permits-by-type.page) — 전문가 신청, plan objection 해소, permit·검사 유형과 선행조건.
- NYC Department of Buildings, [DOB NOW: Inspections FAQs](https://www.nyc.gov/site/buildings/industry/dob-now-inspection-faqs.page) — inspection request, pass/final, job paid, complete 상태 전이.
- NYC Department of Buildings, [Certificate of Occupancy](https://www.nyc.gov/site/buildings/property-or-business-owner/certificate-of-occupancy.page) — 최종 sign-off, 미결 위반·신청·fee, CO/TCO 발행 lifecycle.
- Seattle Department of Construction and Inspections, [Inspections](https://www.seattle.gov/construction-and-inspections/inspections) — permit별 검사 유형, 예약, 자동·special inspection과 단계 순서.

중복 제외: `field_construction_ops`의 contractor 작업 수행, `property_management_ops`의 입주자·임대 운영, `maintenance_asset_ops`의 설비 정비를 분리한다. government code official, parcel/job application, sealed plan set, statutory inspection, permit/CO authority가 없으면 이 도메인을 선택하지 않는다.

## 8. Water and wastewater plant operations (`water_wastewater_plant_ops`)

허브: `water_wastewater_plant_ops.hub` — 정수·하수 처리장 운전 / Drinking-water and wastewater plant operations

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `water_wastewater_plant_ops.plant_shift_dashboard` | `v13_water_wastewater_plant_ops_plant_shift_dashboard` | S | 처리장 → 교대·유량·주요 공정·미결 경보 / Treatment plant → shift/flow/key process/open alarms |
| `water_wastewater_plant_ops.source_influent_quality_view` | `v13_water_wastewater_plant_ops_source_influent_quality_view` | S | 정수 원수·하수 유입수 → 탁도·미생물·부하·추세 / Drinking source or wastewater influent → turbidity/microbial/load/trend |
| `water_wastewater_plant_ops.process_unit_status` | `v13_water_wastewater_plant_ops_process_unit_status` | S | 공정 열차 → basin·filter·disinfection·aeration 상태 / Process train → basin/filter/disinfection/aeration status |
| `water_wastewater_plant_ops.laboratory_results_review` | `v13_water_wastewater_plant_ops_laboratory_results_review` | S | 규정준수 시료 → 분석항목·방법·한정자·결과·기준 / Compliance sample → analyte/method/qualifier/result/limit |
| `water_wastewater_plant_ops.permit_limit_review` | `v13_water_wastewater_plant_ops_permit_limit_review` | S | 시설 permit·규칙 → parameter·limit·frequency·reporting period / Facility permit or rule → parameter/limit/frequency/reporting period |
| `water_wastewater_plant_ops.chemical_inventory_view` | `v13_water_wastewater_plant_ops_chemical_inventory_view` | S | 약품 저장 → 품목·농도·탱크·재고·안전 상태 / Treatment chemical storage → product/concentration/tank/inventory/safety status |
| `water_wastewater_plant_ops.alarm_history` | `v13_water_wastewater_plant_ops_alarm_history` | S | 처리장 경보 → 공정·시각·acknowledgment·복구 이력 / Plant alarm → process/time/acknowledgment/recovery history |
| `water_wastewater_plant_ops.shift_handoff_accept` | `v13_water_wastewater_plant_ops_shift_handoff_accept` | C | 교대 인계 → 처리장 모드·경보·격리·샘플·작업 확인 → 인수 / Shift handoff → verify plant mode/alarms/isolations/samples/work → accept |
| `water_wastewater_plant_ops.sampling_event_record` | `v13_water_wastewater_plant_ops_sampling_event_record` | C | sampling plan → 위치·시각·용기·보존·채취자 확인 → 채취 기록 / Sampling plan → verify location/time/container/preservation/collector → record sample |
| `water_wastewater_plant_ops.lab_result_certify` | `v13_water_wastewater_plant_ops_lab_result_certify` | C | 분석 결과 → sample·method·QC·qualifier·검토자 확인 → 인증 / Analytical result → verify sample/method/QC/qualifier/reviewer → certify |
| `water_wastewater_plant_ops.treatment_setpoint_change` | `v13_water_wastewater_plant_ops_treatment_setpoint_change` | C | 활성 공정 → parameter·현재값·새값·운전 한계·권한 확인 → 설정 변경 / Active process → verify parameter/current/new value/operating limit/authority → change setpoint |
| `water_wastewater_plant_ops.chemical_dose_change` | `v13_water_wastewater_plant_ops_chemical_dose_change` | C | 약품 주입 → chemical·feed point·목표·계산·interlock 확인 → dose 변경 / Chemical feed → verify chemical/feed point/target/calculation/interlock → change dose |
| `water_wastewater_plant_ops.process_unit_start_stop` | `v13_water_wastewater_plant_ops_process_unit_start_stop` | C | 공정 unit → 장비·valve lineup·용량·안전 상태 확인 → 시작·정지 / Process unit → verify equipment/valve lineup/capacity/safety state → start or stop |
| `water_wastewater_plant_ops.bypass_diversion_authorize` | `v13_water_wastewater_plant_ops_bypass_diversion_authorize` | C | 처리 공정 → bypass 경로·사유·영향·permit 조건 확인 → 우회 승인 / Treatment process → verify bypass path/reason/impact/permit conditions → authorize diversion |
| `water_wastewater_plant_ops.maintenance_isolation_release` | `v13_water_wastewater_plant_ops_maintenance_isolation_release` | C | 정비 격리 → 장비·lockout·작업완료·lineup·책임자 확인 → 운전 복귀 / Maintenance isolation → verify equipment/lockout/work complete/lineup/owner → release to service |
| `water_wastewater_plant_ops.compliance_excursion_record` | `v13_water_wastewater_plant_ops_compliance_excursion_record` | C | 한계 초과 → parameter·기간·원인·영향·시정 확인 → excursion 기록 / Limit exceedance → verify parameter/period/cause/impact/correction → record excursion |
| `water_wastewater_plant_ops.public_notice_issue` | `v13_water_wastewater_plant_ops_public_notice_issue` | C | 음용수 위반·위험 → system·대상 인구·tier·문구·승인 확인 → 공지 발행 / Drinking-water violation or risk → verify system/population/tier/message/approval → issue public notice |
| `water_wastewater_plant_ops.discharge_monitoring_report_sign` | `v13_water_wastewater_plant_ops_discharge_monitoring_report_sign` | C | DMR 기간 → outfall·parameter·결과·no-discharge·certifier 확인 → 전자 서명 / DMR period → verify outfall/parameters/results/no-discharge/certifier → sign |
| `water_wastewater_plant_ops.netdmr_submit` | `v13_water_wastewater_plant_ops_netdmr_submit` | C | 서명 DMR → permit·기간·첨부·certification 확인 → NetDMR 제출 / Signed DMR → verify permit/period/attachments/certification → submit NetDMR |
| `water_wastewater_plant_ops.incident_emergency_report` | `v13_water_wastewater_plant_ops_incident_emergency_report` | C | 처리장 사건 → 유출·서비스 영향·규제 기한·통지 대상 확인 → 긴급 보고 / Plant incident → verify release/service impact/regulatory clock/recipients → emergency report |

역할·자산·상태: certified plant operator, chief operator, laboratory analyst, maintenance technician, environmental compliance officer, utility incident manager 역할을 구분한다. 핵심 자산은 treatment plant, source or influent, process train, pump or valve, chemical feed, compliance sample, lab result, permit limit, alarm, DMR, public notice이며, 상태는 `normal → alarmed/degraded → adjusted/isolated/bypassed → sampled → resulted/certified → compliant/excursion → corrected → signed/submitted/notified`다.

충돌군: `plant`(처리장/공장/식물), `source`(원수/코드 소스), `dose`(수처리 약품량/임상 약물·방사선량), `discharge`(방류/환자 퇴원/배터리 방전), `bypass`(공정 우회/인증 우회), `release`(운전 복귀/환경 유출/배포), `sample`(수질 검체/연구·음악 샘플)을 대조한다.

공식 근거:

- EPA, [Drinking Water Regulations](https://www.epa.gov/dwreginfo/drinking-water-regulations) — 오염물질 한계, 시험 일정·방법, treatment technique·public notice 규칙.
- EPA, [Surface Water Treatment Rules](https://www.epa.gov/dwreginfo/surface-water-treatment-rules) — 여과·소독·탁도·병원체 통제와 sanitary survey 상태.
- EPA, [NPDES eReporting for Permittees](https://www.epa.gov/compliance/npdes-ereporting-information-permittees-and-other-regulated-entities) — DMR 전자 제출, NetDMR와 주별 eDMR 역할·인증 경계.
- EPA, [NPDES Applications and Forms](https://www.epa.gov/npdes/npdes-applications-and-forms-epa-forms) — permit, NOI/NOT, DMR와 outfall·monitoring 결과 객체.
- EPA, [NPDES Compliance Inspection Manual](https://www.epa.gov/compliance/compliance-inspection-manual-national-pollutant-discharge-elimination-system) — 처리장 현장 검토, 기록·보고, 샘플링과 공정 unit 검사.
- EPA, [What to Expect During a Public Water System Inspection](https://www.epa.gov/compliance/fact-sheet-what-expect-during-public-water-system-inspection) — operator, monitoring plan, sampling log, calibration·maintenance record 역할과 자산.

중복 제외: `utilities`의 소비자 계정·요금, `utility_grid_field_ops`의 전력 switching, `environmental_waste_ops`의 폐기물 manifest를 분리한다. treatment process train, certified operator, compliance sample, permit limit, DMR/public-notice lifecycle가 없으면 이 도메인을 확정하지 않는다.

## 9. Nuclear-plant operations (`nuclear_plant_operations`)

허브: `nuclear_plant_operations.hub` — 원자력발전소 운전·작업통제 / Nuclear-power plant operations and work control

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `nuclear_plant_operations.unit_status_board` | `v13_nuclear_plant_operations_unit_status_board` | S | 원자로 unit → mode·출력·주요 안전계통·교대 상태 / Reactor unit → mode/power/key safety systems/shift status |
| `nuclear_plant_operations.technical_spec_limit_review` | `v13_nuclear_plant_operations_technical_spec_limit_review` | S | unit 조건 → Technical Specification LCO·surveillance·completion time / Unit condition → Technical Specification LCO/surveillance/completion time |
| `nuclear_plant_operations.equipment_operability_view` | `v13_nuclear_plant_operations_equipment_operability_view` | S | structure·system·component → operable/inoperable·basis·제한 / Structure-system-component → operable/inoperable/basis/restrictions |
| `nuclear_plant_operations.work_clearance_status` | `v13_nuclear_plant_operations_work_clearance_status` | S | 작업지시 → clearance·tag·경계·정비·복귀 상태 / Work order → clearance/tags/boundary/maintenance/return-to-service state |
| `nuclear_plant_operations.radiological_condition_view` | `v13_nuclear_plant_operations_radiological_condition_view` | S | 작업 구역 → dose rate·오염·RWP·출입 조건 / Work area → dose rate/contamination/radiation work permit/access conditions |
| `nuclear_plant_operations.corrective_action_queue` | `v13_nuclear_plant_operations_corrective_action_queue` | S | condition report → 안전 중요도·owner·조치·기한 / Condition report → safety significance/owner/actions/due dates |
| `nuclear_plant_operations.event_reportability_review` | `v13_nuclear_plant_operations_event_reportability_review` | S | 발전소 사건 → 10 CFR 기준·통지 시계·LER 상태 / Plant event → 10 CFR criteria/notification clock/LER status |
| `nuclear_plant_operations.operator_shift_handoff` | `v13_nuclear_plant_operations_operator_shift_handoff` | C | 주제어실 교대 → unit mode·LCO·경보·작업·비정상 상태 확인 → 인수 / Control-room shift → verify unit mode/LCOs/alarms/work/abnormal conditions → accept handoff |
| `nuclear_plant_operations.surveillance_test_record` | `v13_nuclear_plant_operations_surveillance_test_record` | C | surveillance requirement → 절차·SSC·측정·acceptance criteria 확인 → 결과 기록 / Surveillance requirement → verify procedure/SSC/measurements/acceptance criteria → record result |
| `nuclear_plant_operations.equipment_operability_determination` | `v13_nuclear_plant_operations_equipment_operability_determination` | C | degraded SSC → 기능·설계기준·증거·승인자 확인 → operability 결정 / Degraded SSC → verify function/design basis/evidence/approver → determine operability |
| `nuclear_plant_operations.limiting_condition_action_start` | `v13_nuclear_plant_operations_limiting_condition_action_start` | C | inoperable SSC → 적용 LCO·required action·completion time 확인 → action 진입 / Inoperable SSC → verify applicable LCO/required action/completion time → enter action statement |
| `nuclear_plant_operations.work_clearance_issue` | `v13_nuclear_plant_operations_work_clearance_issue` | C | 승인 작업 → 장비·에너지원·tag 경계·독립 검증 확인 → clearance 발행 / Approved work → verify equipment/energy sources/tag boundary/independent verification → issue clearance |
| `nuclear_plant_operations.tagout_boundary_release` | `v13_nuclear_plant_operations_tagout_boundary_release` | C | 완료 작업 → 모든 작업자·도구·tag·계통 lineup 확인 → 격리 해제 / Completed work → verify workers/tools/tags/system lineup → release tagout boundary |
| `nuclear_plant_operations.maintenance_return_service` | `v13_nuclear_plant_operations_maintenance_return_service` | C | 정비 SSC → 작업완료·시험·결함·운전 승인 확인 → service 복귀 / Maintained SSC → verify work complete/post-maintenance test/defects/operations approval → return to service |
| `nuclear_plant_operations.procedure_step_signoff` | `v13_nuclear_plant_operations_procedure_step_signoff` | C | 진행 절차 → unit·step·전제조건·측정·performer/verifier 확인 → 서명 / In-progress procedure → verify unit/step/prerequisite/measurement/performer-verifier → sign off |
| `nuclear_plant_operations.reactor_power_change_authorize` | `v13_nuclear_plant_operations_reactor_power_change_authorize` | C | 원자로 운전 → 현재·목표 출력·reactivity plan·제한·승인 확인 → 출력 변경 승인 / Reactor operation → verify current/target power/reactivity plan/limits/authority → authorize change |
| `nuclear_plant_operations.manual_reactor_trip` | `v13_nuclear_plant_operations_manual_reactor_trip` | C | 원자로 unit → 비정상 조건·보호 기능·절차·shift manager 확인 → 수동 trip / Reactor unit → verify abnormal condition/protective function/procedure/shift manager → manual trip |
| `nuclear_plant_operations.emergency_class_declare` | `v13_nuclear_plant_operations_emergency_class_declare` | C | 발전소 사건 → EAL·unit·영향·emergency director 권한 확인 → 비상등급 선언 / Plant event → verify EAL/unit/impact/emergency-director authority → declare emergency class |
| `nuclear_plant_operations.nrc_event_notify` | `v13_nuclear_plant_operations_nrc_event_notify` | C | 보고 가능 사건 → 1/4/8-hour 기준·사실·외부통지 확인 → NRC 통지 / Reportable event → verify 1/4/8-hour criterion/facts/external notifications → notify NRC |
| `nuclear_plant_operations.licensee_event_report_submit` | `v13_nuclear_plant_operations_licensee_event_report_submit` | C | event record → 원인·안전 영향·corrective action·60-day 기준 확인 → LER 제출 / Event record → verify cause/safety impact/corrective action/60-day criterion → submit LER |

역할·자산·상태: licensed reactor operator, senior reactor operator, shift manager, work-control planner, maintenance supervisor, radiation-protection technician, emergency director, regulatory affairs specialist 역할을 구분한다. 핵심 자산은 reactor unit, structure-system-component, Technical Specification, surveillance requirement, procedure, work order, clearance, tag boundary, condition report, emergency action level, event notification, licensee event report이며, 상태는 `startup → operating → hot standby/shutdown/refueling → degraded/inoperable → LCO action → isolated/under maintenance → tested/returned to service → emergency declared → notified/reported`다.

충돌군: `unit`(원자로 호기/혈액 단위/UI 단위), `trip`(원자로 정지/여행), `mode`(원자로 운전 모드/UI 모드), `clearance`(작업 격리/항공 허가/결제 승인), `release`(tagout 해제/제품 배포), `tag`(격리 표찰/메타데이터), `event report`(규제 사건/분석 이벤트)를 대조한다.

공식 근거:

- NRC, [Operating Reactors](https://www.nrc.gov/reactors/operating) — 상업 원자로 운전, 허가·감독·운영경험 역할과 범위.
- NRC, [Operating Reactor Licensee Toolkit](https://www.nrc.gov/reactors/operating/op-reactor-toolkit) — event notification, reactor status, Part 21, inspection·regulatory 자료.
- NRC, [Standard Technical Specifications — Current Versions](https://www.nrc.gov/reactors/operating/licensing/techspecs/current-approved-sts) — LCO, surveillance, action·completion-time의 plant별 운전 경계.
- NRC, [Reactor Oversight Process](https://www.nrc.gov/reactors/operating/oversight) — 안전 성과, inspection finding, performance indicator, action matrix lifecycle.
- NRC, [Event Reporting Guidelines: 10 CFR 50.72 and 50.73](https://www.nrc.gov/reading-rm/doc-collections/nuregs/staff/sr1022/index) — 즉시 통지와 Licensee Event Report 판단·제출 기준.
- NRC, [Reports Associated with Events](https://www.nrc.gov/reading-rm/doc-collections/event-status/index) — power status, Event Notification, Preliminary Notification, LER 조회 객체.

중복 제외: `utility_grid_field_ops`의 전력망 switching, `maintenance_asset_ops`의 일반 설비 정비, `emergency_response_operations`의 다기관 재난 지휘를 분리한다. licensed reactor role, reactor unit mode, Technical Specification/LCO, nuclear work clearance, NRC reporting clock가 없으면 이 도메인을 확정하지 않는다.

## 10. Pipeline control and integrity operations (`pipeline_control_integrity_ops`)

허브: `pipeline_control_integrity_ops.hub` — 가스·위험액체 파이프라인 관제·건전성 / Gas and hazardous-liquid pipeline control and integrity

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `pipeline_control_integrity_ops.scada_overview` | `v13_pipeline_control_integrity_ops_scada_overview` | S | pipeline control room → segment·pressure·flow·valve·pump 상태 / Pipeline control room → segment/pressure/flow/valve/pump status |
| `pipeline_control_integrity_ops.alarm_queue` | `v13_pipeline_control_integrity_ops_alarm_queue` | S | SCADA 경보 → priority·point·시간·acknowledgment 상태 / SCADA alarms → priority/point/time/acknowledgment status |
| `pipeline_control_integrity_ops.linepack_pressure_view` | `v13_pipeline_control_integrity_ops_linepack_pressure_view` | S | gas·liquid segment → linepack·압력 프로파일·운전 한계 / Gas or liquid segment → linepack/pressure profile/operating limits |
| `pipeline_control_integrity_ops.controller_shift_log` | `v13_pipeline_control_integrity_ops_controller_shift_log` | S | 관제 교대 → 명령·경보·비정상 조건·미결 조치 이력 / Controller shift → commands/alarms/abnormal conditions/open actions history |
| `pipeline_control_integrity_ops.valve_station_status` | `v13_pipeline_control_integrity_ops_valve_station_status` | S | 차단 밸브·펌프/압축기 스테이션 → 원격/현장·개방/폐쇄·가용 상태 / Block valve or pump-compressor station → remote-local/open-closed/availability |
| `pipeline_control_integrity_ops.leak_detection_status` | `v13_pipeline_control_integrity_ops_leak_detection_status` | S | 관로 구간 → 누출 모델·불균형·센서 상태·조사 / Pipeline segment → leak model/imbalance/sensor health/investigation |
| `pipeline_control_integrity_ops.integrity_assessment_queue` | `v13_pipeline_control_integrity_ops_integrity_assessment_queue` | S | 고영향구역(HCA) 구간 → 평가 방법·이상 징후·수리 기한·검증 / HCA segment → assessment method/anomaly/repair due/verification |
| `pipeline_control_integrity_ops.controller_shift_handoff` | `v13_pipeline_control_integrity_ops_controller_shift_handoff` | C | 관제 위치 → active alarms·abnormal conditions·outages·commands 확인 → 인수 / Control position → verify active alarms/abnormal conditions/outages/commands → accept handoff |
| `pipeline_control_integrity_ops.alarm_acknowledge_classify` | `v13_pipeline_control_integrity_ops_alarm_acknowledge_classify` | C | SCADA alarm → point·priority·원인 증거·동시 경보 확인 → 인지·분류 / SCADA alarm → verify point/priority/cause evidence/correlated alarms → acknowledge and classify |
| `pipeline_control_integrity_ops.setpoint_change_request` | `v13_pipeline_control_integrity_ops_setpoint_change_request` | C | control parameter → current/new setpoint·limit·영향·승인 확인 → 변경 요청 / Control parameter → verify current/new setpoint/limit/impact/approval → submit change request |
| `pipeline_control_integrity_ops.valve_remote_operate` | `v13_pipeline_control_integrity_ops_valve_remote_operate` | C | remote valve → segment·valve ID·position·downstream impact·authority 확인 → 개폐 / Remote valve → verify segment/valve ID/position/downstream impact/authority → open or close |
| `pipeline_control_integrity_ops.pump_compressor_start_stop` | `v13_pipeline_control_integrity_ops_pump_compressor_start_stop` | C | station unit → lineup·pressure·availability·interlock·권한 확인 → 시작·정지 / Station unit → verify lineup/pressure/availability/interlock/authority → start or stop |
| `pipeline_control_integrity_ops.pressure_reduction_apply` | `v13_pipeline_control_integrity_ops_pressure_reduction_apply` | C | affected segment → anomaly·현재·target pressure·기간·통지 확인 → 감압 적용 / Affected segment → verify anomaly/current-target pressure/duration/notifications → apply reduction |
| `pipeline_control_integrity_ops.pipeline_shutdown_execute` | `v13_pipeline_control_integrity_ops_pipeline_shutdown_execute` | C | pipeline system → 범위·valve sequence·고객·emergency plan 확인 → shutdown / Pipeline system → verify scope/valve sequence/customers/emergency plan → execute shutdown |
| `pipeline_control_integrity_ops.abnormal_condition_declare` | `v13_pipeline_control_integrity_ops_abnormal_condition_declare` | C | 관제 사건 → abnormal criterion·segment·증거·supervisor 확인 → 상태 선언 / Control-room event → verify abnormal criterion/segment/evidence/supervisor → declare condition |
| `pipeline_control_integrity_ops.emergency_response_activate` | `v13_pipeline_control_integrity_ops_emergency_response_activate` | C | pipeline incident → 위치·제품·영향·isolation·연락망 확인 → 대응 활성화 / Pipeline incident → verify location/product/impact/isolation/contact tree → activate response |
| `pipeline_control_integrity_ops.leak_investigation_dispatch` | `v13_pipeline_control_integrity_ops_leak_investigation_dispatch` | C | leak indication → segment·접근 위험·field crew·계측 요구 확인 → 조사 파견 / Leak indication → verify segment/access hazard/field crew/instrument needs → dispatch investigation |
| `pipeline_control_integrity_ops.integrity_anomaly_classify` | `v13_pipeline_control_integrity_ops_integrity_anomaly_classify` | C | assessment result → feature·dimension·HCA·repair criterion·reviewer 확인 → anomaly 분류 / Assessment result → verify feature/dimensions/HCA/repair criterion/reviewer → classify anomaly |
| `pipeline_control_integrity_ops.repair_priority_approve` | `v13_pipeline_control_integrity_ops_repair_priority_approve` | C | integrity anomaly → immediate/scheduled criterion·pressure restriction·due date 확인 → 우선순위 승인 / Integrity anomaly → verify immediate-scheduled criterion/pressure restriction/due date → approve priority |
| `pipeline_control_integrity_ops.incident_report_submit` | `v13_pipeline_control_integrity_ops_incident_report_submit` | C | pipeline event → reportability·release·피해·원인·수정조치 확인 → PHMSA 보고 / Pipeline event → verify reportability/release/damage/cause/corrective actions → submit PHMSA report |

역할·자산·상태: pipeline controller, control-room supervisor, integrity engineer, field technician, emergency coordinator, regulatory reporting specialist 역할을 구분한다. 핵심 자산은 pipeline segment, SCADA point, alarm, block valve, pump or compressor, pressure setpoint, leak model, high consequence area, integrity anomaly, repair, incident report이며, 상태는 `normal → alarmed/acknowledged → abnormal → pressure-reduced → isolated/shutdown → dispatched/investigated → assessed → repair-due/repaired → restored/reported`다.

충돌군: `line`(pipeline segment/텍스트 줄/전화 회선), `alarm`(SCADA process alarm/일반 알림), `valve`(pipeline valve/생물학 판막), `segment`(pipeline 구간/고객 세그먼트), `pressure`(운전 압력/업무 압박), `shutdown`(물리 계통 정지/서버 종료), `dispatch`(현장 조사/배달 배차)를 대조한다.

공식 근거:

- PHMSA, [Control Room Management](https://www.phmsa.dot.gov/pipeline/control-room-management/control-room-management) — controller, control room, SCADA, fatigue·alarm·abnormal/emergency response 경계.
- PHMSA, [Gas Transmission Integrity Management](https://www.phmsa.dot.gov/technical-resources/gas-transmission-integrity-management) — HCA segment 식별·우선순위·평가·수리·검증 lifecycle.
- PHMSA, [Hazardous Liquid Integrity Management Fact Sheet](https://www.phmsa.dot.gov/pipeline/hazardous-liquid-integrity-management/hl-im-fact-sheet) — baseline assessment, anomaly·repair criteria, pressure reduction, 기록 보존.
- PHMSA, [Hazardous Liquid Integrity Assurance Notifications](https://www.phmsa.dot.gov/pipeline/hazardous-liquid-integrity-management/hl-im-notifications) — 수리 지연·감압·assessment interval·기술 사용 통지.
- PHMSA, [Pipeline Compliance Forms](https://www.phmsa.dot.gov/forms/pipeline-compliance-forms) — gas·hazardous-liquid incident, accident, annual report의 제출 주체와 양식.
- PHMSA, [National Pipeline Performance Measures](https://www.phmsa.dot.gov/data-and-statistics/pipeline/national-pipeline-performance-measures) — HCA mileage, assessment, repair, leak·incident 성과 상태.

중복 제외: `telecom_field_service_ops`의 회선·포트, `utility_grid_field_ops`의 전력 switch, `maintenance_asset_ops`의 일반 work order를 분리한다. regulated pipeline segment, control-room SCADA, block valve/pump-compressor, HCA, PHMSA reportability가 확인되지 않으면 이 도메인으로 진입하지 않는다.

## 11. Museum collections operations (`museum_collections_ops`)

허브: `museum_collections_ops.hub` — 박물관 소장품 등록·보존·대여 / Museum collection registration, care, and loans

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `museum_collections_ops.accession_queue` | `v13_museum_collections_ops_accession_queue` | S | 소장품 등록 작업함 → 제안·incoming loan·미완료 accession / Collections registration queue → proposed acquisitions/incoming loans/incomplete accessions |
| `museum_collections_ops.object_catalog_view` | `v13_museum_collections_ops_object_catalog_view` | S | 소장품 → 수증·카탈로그 번호·출처 이력·설명 / Collection object → accession/catalog number/provenance/description |
| `museum_collections_ops.location_inventory_view` | `v13_museum_collections_ops_location_inventory_view` | S | 보관 위치 → object·container·barcode·inventory status / Storage location → object/container/barcode/inventory status |
| `museum_collections_ops.condition_history` | `v13_museum_collections_ops_condition_history` | S | object → condition assessment·damage·treatment·환경 이력 / Object → condition assessment/damage/treatment/environment history |
| `museum_collections_ops.loan_status_view` | `v13_museum_collections_ops_loan_status_view` | S | incoming/outgoing loan → borrower/lender·objects·dates·보험·return / Incoming or outgoing loan → party/objects/dates/insurance/return |
| `museum_collections_ops.rights_restriction_review` | `v13_museum_collections_ops_rights_restriction_review` | S | 소장품·기록물 → 소유권·저작권·기증자·문화적 제한 / Object or archive → ownership/copyright/donor/cultural restrictions |
| `museum_collections_ops.research_access_request` | `v13_museum_collections_ops_research_access_request` | S | 소장품 이용 → 연구자·목적·대상·요청일·상태 / Collection use → researcher/purpose/objects/requested dates/status |
| `museum_collections_ops.acquisition_proposal_submit` | `v13_museum_collections_ops_acquisition_proposal_submit` | C | proposed object → scope·title/provenance·condition·restrictions·committee 확인 → 취득 제안 / Proposed object → verify scope/title-provenance/condition/restrictions/committee → submit acquisition proposal |
| `museum_collections_ops.accession_record_create` | `v13_museum_collections_ops_accession_record_create` | C | accepted acquisition·incoming loan → legal custody·source·date·object count 확인 → accession 생성 / Accepted acquisition or incoming loan → verify legal custody/source/date/object count → create accession |
| `museum_collections_ops.catalog_record_publish` | `v13_museum_collections_ops_catalog_record_publish` | C | accessioned object → catalog number·description·classification·restriction 확인 → record 공개 / Accessioned object → verify catalog number/description/classification/restriction → publish record |
| `museum_collections_ops.object_location_transfer` | `v13_museum_collections_ops_object_location_transfer` | C | object movement → object ID·from/to location·handler·time 확인 → 위치 이전 / Object movement → verify object ID/from-to location/handler/time → transfer location |
| `museum_collections_ops.inventory_discrepancy_record` | `v13_museum_collections_ops_inventory_discrepancy_record` | C | inventory check → object·expected/actual location·상태·조사 owner 확인 → 불일치 기록 / Inventory check → verify object/expected-actual location/status/investigation owner → record discrepancy |
| `museum_collections_ops.condition_assessment_sign` | `v13_museum_collections_ops_condition_assessment_sign` | C | object examination → material·damage·severity·images·examiner 확인 → 상태평가 서명 / Object examination → verify material/damage/severity/images/examiner → sign assessment |
| `museum_collections_ops.conservation_treatment_approve` | `v13_museum_collections_ops_conservation_treatment_approve` | C | treatment proposal → object·method·risk·reversibility·authority 확인 → 보존처리 승인 / Treatment proposal → verify object/method/risk/reversibility/authority → approve conservation |
| `museum_collections_ops.outgoing_loan_approve` | `v13_museum_collections_ops_outgoing_loan_approve` | C | loan request → borrower·purpose·facility report·object condition·authority 확인 → 대여 승인 / Loan request → verify borrower/purpose/facility report/object condition/authority → approve loan |
| `museum_collections_ops.loan_shipment_release` | `v13_museum_collections_ops_loan_shipment_release` | C | approved loan → objects·packing·condition·insurance·courier·seal 확인 → 출고 / Approved loan → verify objects/packing/condition/insurance/courier/seal → release shipment |
| `museum_collections_ops.research_access_approve` | `v13_museum_collections_ops_research_access_approve` | C | research request → researcher·objects·restrictions·supervision·handling 확인 → 접근 승인 / Research request → verify researcher/objects/restrictions/supervision/handling → approve access |
| `museum_collections_ops.exhibit_installation_handoff` | `v13_museum_collections_ops_exhibit_installation_handoff` | C | exhibit object → mount·location·condition·light/security limits 확인 → 설치 인계 / Exhibit object → verify mount/location/condition/light-security limits → installation handoff |
| `museum_collections_ops.deaccession_recommend` | `v13_museum_collections_ops_deaccession_recommend` | C | collection object → title·scope·criteria·restriction·committee 확인 → 제적 권고 / Collection object → verify title/scope/criteria/restrictions/committee → recommend deaccession |
| `museum_collections_ops.disposal_execute` | `v13_museum_collections_ops_disposal_execute` | C | approved deaccession → method·recipient·legal/ethical condition·records 확인 → 처분 실행 / Approved deaccession → verify method/recipient/legal-ethical conditions/records → execute disposal |

역할·자산·상태: curator, registrar, collections manager, conservator, rights specialist, preparator, loan officer, collections committee 역할을 구분한다. 핵심 자산은 collection object or specimen, acquisition proposal, accession, catalog record, storage location, condition report, treatment proposal, loan, rights restriction, exhibit, deaccession case이며, 상태는 `proposed → accepted/rejected → accessioned → cataloged → stored/on exhibit/on loan → under treatment/restricted/missing → returned → deaccession recommended/approved → disposed`다.

충돌군: `accession`(소장품 등록/시스템 access), `catalog`(소장품 기록/앱 상품 카탈로그), `object`(박물관 물건/프로그래밍 객체), `condition`(보존 상태/조건문), `loan`(소장품 대여/금융 대출), `rights`(저작·문화 권리/계정 권한), `disposal`(제적 처분/폐기물 처리)을 대조한다.

공식 근거:

- National Park Service, [National Park Service Museum Handbook](https://www.nps.gov/subjects/museums/museumhandbook.htm) — collection care, records, access/use의 3부 구조와 책임 경계.
- National Park Service, [Museum Handbook Part I — Museum Collections](https://www.nps.gov/subjects/museums/mh1.htm) — scope, preservation, storage, environment, treatment, security·emergency 자산.
- National Park Service, [Museum Handbook Part II — Museum Records](https://www.nps.gov/subjects/museums/mh2.htm) — accessioning, cataloging, inventory, loans, deaccessioning 절차.
- National Park Service, [Museum Handbook Part III — Museum Collection Use](https://home.nps.gov/subjects/museums/mh3.htm) — 연구·출판·복제·전시 access and use 검토.
- Smithsonian Institution, [Smithsonian Directive 600 — Collections Management](https://www.si.edu/sites/default/files/about/SD600.pdf) — acquisition, accession, deaccession, inventory, preservation, access, loan, 권리의 lifecycle.
- Smithsonian National Collections Program, [Collections Management Policies](https://ncp.si.edu/policy) — acquisition, loan, access, inventory, deaccession을 통제하는 collecting-unit 정책 구조.

중복 제외: `digital_library`의 전자책 대출, `documents_cloud`의 파일 저장·공유, `genealogy_family_history`의 개인 기록을 분리한다. accession/catalog number, legal custody or title, physical object location, condition report, museum loan/deaccession authority가 없으면 이 도메인을 선택하지 않는다.

## 12. Air-traffic control operations (`air_traffic_control_ops`)

허브: `air_traffic_control_ops.hub` — 항공교통 관제·흐름관리 / Air-traffic control and flow management

| terminal function ID | intent ID | class | 한/영 개념 경로 |
|---|---|:---:|---|
| `air_traffic_control_ops.sector_traffic_picture` | `v13_air_traffic_control_ops_sector_traffic_picture` | S | ATC sector·position → aircraft track·altitude·route·separation 상태 / ATC sector or position → aircraft track/altitude/route/separation status |
| `air_traffic_control_ops.flight_plan_strip_review` | `v13_air_traffic_control_ops_flight_plan_strip_review` | S | 비행 자료 → 호출부호·항공기 형식·항로·고도·비고 / Flight data → callsign/aircraft type/route/altitude/remarks |
| `air_traffic_control_ops.weather_hazard_view` | `v13_air_traffic_control_ops_weather_hazard_view` | S | 관제 구역·공항 → 대류·결빙·난기류·바람·시정 / Sector or airport → convection/icing/turbulence/wind/visibility |
| `air_traffic_control_ops.runway_airspace_status` | `v13_air_traffic_control_ops_runway_airspace_status` | S | airport·airspace → runway·taxiway·SUA/TFR·open/restricted 상태 / Airport or airspace → runway/taxiway/SUA-TFR/open-restricted status |
| `air_traffic_control_ops.notam_status_review` | `v13_air_traffic_control_ops_notam_status_review` | S | 책임 위치 → 유효 항공고시(NOTAM)·키워드·유효기간·검증 / Accountable location → active NOTAM/keyword/validity/verification |
| `air_traffic_control_ops.traffic_flow_plan_view` | `v13_air_traffic_control_ops_traffic_flow_plan_view` | S | NAS flow → demand·capacity·reroute·GDP·ground-stop 상태 / NAS flow → demand/capacity/reroute/GDP/ground-stop status |
| `air_traffic_control_ops.equipment_outage_view` | `v13_air_traffic_control_ops_equipment_outage_view` | S | 관제 시설 → 레이더·주파수·항행시설·자동화 가용성 / ATC facility → radar/frequency/NAVAID/automation availability |
| `air_traffic_control_ops.position_relief_briefing_accept` | `v13_air_traffic_control_ops_position_relief_briefing_accept` | C | ATC position → traffic·weather·equipment·restrictions·coordination 확인 → position 인수 / ATC position → verify traffic/weather/equipment/restrictions/coordination → accept relief briefing |
| `air_traffic_control_ops.flight_data_amend` | `v13_air_traffic_control_ops_flight_data_amend` | C | flight plan → aircraft·route·altitude·time·coordination 확인 → 데이터 수정 / Flight plan → verify aircraft/route/altitude/time/coordination → amend data |
| `air_traffic_control_ops.clearance_issue` | `v13_air_traffic_control_ops_clearance_issue` | C | aircraft request → callsign·route·limit·restriction·readback 필요 확인 → clearance 발행 / Aircraft request → verify callsign/route/clearance limit/restrictions/readback → issue clearance |
| `air_traffic_control_ops.altitude_assignment` | `v13_air_traffic_control_ops_altitude_assignment` | C | controlled aircraft → identity·current/requested altitude·traffic·minimum 확인 → altitude 지정 / Controlled aircraft → verify identity/current-requested altitude/traffic/minimum → assign altitude |
| `air_traffic_control_ops.handoff_transfer_accept` | `v13_air_traffic_control_ops_handoff_transfer_accept` | C | aircraft track → transferring/receiving sector·identity·altitude·coordination 확인 → handoff 수락 / Aircraft track → verify transferring-receiving sectors/identity/altitude/coordination → accept handoff |
| `air_traffic_control_ops.runway_crossing_clearance` | `v13_air_traffic_control_ops_runway_crossing_clearance` | C | aircraft·vehicle → runway·position·traffic·hold-short status 확인 → crossing clearance / Aircraft or vehicle → verify runway/position/traffic/hold-short status → issue crossing clearance |
| `air_traffic_control_ops.traffic_management_initiative_apply` | `v13_air_traffic_control_ops_traffic_management_initiative_apply` | C | NAS constraint → affected flights·capacity·initiative·coordination·time 확인 → TMI 적용 / NAS constraint → verify affected flights/capacity/initiative/coordination/time → apply TMI |
| `air_traffic_control_ops.ground_stop_issue` | `v13_air_traffic_control_ops_ground_stop_issue` | C | destination constraint → scope·start/end·exceptions·coordination 권한 확인 → ground stop 발행 / Destination constraint → verify scope/start-end/exceptions/coordination authority → issue ground stop |
| `air_traffic_control_ops.airspace_restriction_activate` | `v13_air_traffic_control_ops_airspace_restriction_activate` | C | special-use/TFR airspace → lateral·vertical·time·controlling agency·NOTAM 확인 → 활성화 / SUA or TFR airspace → verify lateral/vertical/time/controlling agency/NOTAM → activate |
| `air_traffic_control_ops.notam_originate` | `v13_air_traffic_control_ops_notam_originate` | C | temporary hazard·change → accountable location·keyword·validity·source 확인 → NOTAM 발행 / Temporary hazard or change → verify accountable location/keyword/validity/source → originate NOTAM |
| `air_traffic_control_ops.notam_cancel` | `v13_air_traffic_control_ops_notam_cancel` | C | active NOTAM → condition restored/published·identifier·authority 확인 → 취소 / Active NOTAM → verify condition restored or published/identifier/authority → cancel |
| `air_traffic_control_ops.emergency_assistance_coordinate` | `v13_air_traffic_control_ops_emergency_assistance_coordinate` | C | aircraft emergency → callsign·nature·position·intentions·support agency 확인 → 지원 조정 / Aircraft emergency → verify callsign/nature/position/intentions/support agency → coordinate assistance |
| `air_traffic_control_ops.operational_incident_report` | `v13_air_traffic_control_ops_operational_incident_report` | C | ATC occurrence → aircraft·sector·separation·audio/data·supervisor 확인 → 사건 보고 / ATC occurrence → verify aircraft/sector/separation/audio-data/supervisor → report incident |

역할·자산·상태: air traffic controller, controller-in-charge, operations supervisor, traffic-management coordinator, flight-data specialist, NOTAM originator, facility manager 역할을 구분한다. 핵심 자산은 aircraft track, flight plan, ATC sector or position, runway, route, altitude, weather hazard, NAS capacity constraint, traffic management initiative, special-use airspace, NOTAM, operational incident이며, 상태는 `proposed → coordinated → issued/read back → active → handed off/accepted → restricted/held → amended → canceled/restored → emergency assisted → reported`다.

충돌군: `clearance`(ATC 운항 허가/보안 인가/결제·세일), `strip`(flight progress strip/문자 제거), `handoff`(관제 이양/임상·업무 인계), `position`(관제석/지도 좌표/채용 직위), `sector`(공역 sector/산업군), `ground stop`(교통 흐름 조치/육상 정류장), `issue`(clearance·NOTAM 발행/문제)를 대조한다.

공식 근거:

- FAA, [Order JO 7110.65 — Air Traffic Control](https://www.faa.gov/air_traffic/publications/atpubs/atc_html/index.html) — 관제 절차·phraseology, 분리·safety alert·clearance·handoff 경계.
- FAA, [Order JO 7210.3 — Facility Operation and Administration](https://www.faa.gov/air_traffic/publications/atpubs/foa_html/index.html) — facility, position, staffing, 기록·보고, traffic management 역할.
- FAA, [JO 7110.65 Chapter 2 — General Control](https://www.faa.gov/air_traffic/publications/atpubs/atc_html/chap2_section_1.html) — duty priority, approval/unable/stand by, operational request와 safety alert.
- FAA, [NOTAM Order — Scope](https://www.faa.gov/air_traffic/publications/atpubs/notam_html/chap1_section_2.html) — authorized originator, keyword, format, system processing과 검증.
- FAA, [NOTAM Responsibilities](https://www.faa.gov/air_traffic/publications/atpubs/notam_html/chap3_section_1.html) — source, accuracy, coordination, validity, issue·reissue·duration 책임.
- FAA, [AIP ENR 1.9 — Air Traffic Flow Management and Airspace Management](https://www.faa.gov/air_traffic/publications/atpubs/aip_html/part2_enr_section_1.9.html) — demand-capacity 균형, TMI·trajectory·time-based management 상태.

중복 제외: `airline_crew_operations`의 운항승무원 roster·briefing, `aviation_maintenance_ops`의 항공기 정비 release, `air_travel_planning`의 승객 예약을 분리한다. controller position, live aircraft track, separation/clearance, sector transfer, NAS flow or NOTAM authority가 없으면 이 도메인을 확정하지 않는다.

## 교차 도메인 collision matrix

각 collision family는 alias-only winner를 금지한다. 현재 화면에서 두 개 이상의 `role + governed asset + lifecycle state` 증거가 맞지 않으면 해당 terminal을 제시하지 않고 허브 또는 fail-closed 결과만 반환한다. 아래 표현은 v13 내부뿐 아니라 v1~v12의 동명 기능과도 대조한다.

| 모호 표현 | 반드시 구분할 개념 |
|---|---|
| `unit` / 단위·호기 | blood component unit, reactor unit, measurement unit, UI unit |
| `patient` / 환자 | transfusion recipient, radiation-therapy patient, general clinical patient, animal patient |
| `donor` / 기증자 | blood donor, organ donor, museum donor, financial donor |
| `recipient` / 수령인 | transfusion recipient, organ candidate, museum-loan recipient, payment receiver |
| `release` / 방출·해제 | blood component release, nuclear tagout release, pipeline pressure release, software release, custody release |
| `issue` / 발행·출고·문제 | blood unit issue, permit or summons issue, ATC clearance issue, generic problem |
| `order` / 지시·명령 | transfusion order, judicial order, stop-work order, purchase order |
| `match` / 일치·배정 | organ match run, compatibility match, dating match, resolver string match |
| `candidate` / 후보 | transplant candidate, election candidate, job applicant, resolver candidate |
| `offer` / 제안 | organ offer, gig-work offer, retail promotion, employment offer |
| `allocation` / 배정 | organ allocation, budget allocation, memory allocation, warehouse slotting |
| `recovery` / 회수·복구 | organ recovery, product recovery/recall, disaster recovery, data recovery |
| `course` / 과정 | radiation treatment course, class course, travel itinerary |
| `plan` / 계획·도면 | radiotherapy plan, building plan set, food HACCP plan, treatment/care plan, subscription plan |
| `fraction` / 분할 | radiotherapy fraction, mathematical fraction, partial payment |
| `dose` / 용량·선량 | radiation dose, medication dose, water-treatment chemical dose |
| `directive` / 지시 | radiotherapy written directive, organization policy directive, UI command |
| `case` / 사건·사례 | court case, social-service case, insurance claim case, customer-support case |
| `docket` / 도켓 | court docket, IP deadline docket, generic work queue |
| `file` / 제출·파일 | court filing, patent/trademark filing, cloud file, local file operation |
| `serve` / 송달·제공 | legal service, restaurant service, server operation, sports serve |
| `seal` / 봉인 | sealed court document, organ/blood/museum shipment seal, professional design seal |
| `application` / 출원·신청·앱 | patent/trademark application, permit application, benefit application, software application |
| `claim` / 청구항·청구 | patent claim, insurance claim, refund claim, statement assertion |
| `class` / 분류·등급 | trademark class, school class, programming class, safety classification |
| `specimen` / 증거·검체 | trademark specimen, blood/lab specimen, museum natural-history specimen |
| `assignment` / 양도·배정 | IP ownership assignment, work assignment, aircraft altitude assignment |
| `maintenance` / 유지·정비 | trademark registration maintenance, nuclear/pipeline maintenance, app maintenance |
| `inspection` / 점검 | food inspection, building inspection, nuclear regulatory inspection, manufacturing quality inspection |
| `permit` / 허가 | building or food permit, environmental permit, runtime permission |
| `hold` / 보류 | food product hold, organ candidate inactive hold, customs hold, legal hold, payment hold |
| `code` / 법규·코드 | Food Code, building code, software source code, authentication code |
| `build` / 건축·빌드 | building construction, software build, manufacturing build order |
| `job` / 신청·작업 | building job application, background job, employment position, gig job |
| `occupancy` / 점유 | certificate of occupancy, hotel occupancy, seat occupancy, memory occupancy |
| `plant` / 시설·식물 | water treatment plant, nuclear power plant, manufacturing plant, botanical plant |
| `source` / 원천 | drinking-water source, radiation source, software source, evidence source |
| `discharge` / 방류·퇴원 | wastewater discharge, patient discharge, battery discharge, debt discharge |
| `bypass` / 우회 | treatment-process bypass, security bypass, road bypass |
| `sample` / 검체·표본 | compliance water sample, blood specimen, research sample, music sample |
| `trip` / 정지·여행 | reactor trip, protection trip, travel trip, circuit breaker trip |
| `mode` / 운전상태 | reactor operating mode, aircraft mode, UI display mode, model mode |
| `clearance` / 허가·정산 | nuclear work clearance, ATC clearance, security clearance, retail clearance sale |
| `tag` / 표찰·메타데이터 | nuclear tagout, museum object tag, software metadata tag, social tag |
| `line` / 배관·회선·문장 | pipeline segment, telecom line, text line, product line |
| `alarm` / 공정 경보·알림 | pipeline or plant alarm, clock alarm, notification badge |
| `valve` / 밸브 | pipeline valve, water-process valve, biological heart valve |
| `segment` / 구간 | pipeline segment, customer segment, text segment, rail segment |
| `shutdown` / 물리 정지·종료 | pipeline shutdown, reactor shutdown, server shutdown, business closure |
| `dispatch` / 파견·배차 | pipeline field dispatch, gig dispatch, emergency dispatch, delivery dispatch |
| `accession` / 등록·접근 | museum accession, system access, sequence accession number |
| `catalog` / 소장기록·상품목록 | museum catalog, app catalog, commerce product catalog |
| `object` / 소장품·객체 | museum object, programming object, goal object |
| `condition` / 상태·조건 | museum condition, abnormal operating condition, rule condition |
| `loan` / 대여·대출 | museum loan, financial loan, library loan |
| `rights` / 권리·권한 | museum copyright/cultural rights, account permissions, legal rights |
| `strip` / flight strip·제거 | flight progress strip, string strip, material strip |
| `handoff` / 이양·인계 | ATC control transfer, clinical handoff, organ transport handoff, work handoff |
| `position` / 관제석·위치 | ATC position, map coordinate, job position, investment position |
| `sector` / 공역·산업군 | ATC sector, market sector, disk sector |
| `ground stop` / 흐름 통제 | NAS ground stop, physical stop on ground, transit stop |

## 구현 데이터 계약

각 domain source module은 다음 하한을 충족해야 한다.

- 12개 domain과 12개 hub를 deterministic order로 materialize한다.
- terminal 240개, intent 240개, 총 function 252개를 정확히 생성하고 분류는 `S=84`, `C=156`으로 고정한다.
- terminal마다 한국어 alias 4개 이상, 영어 alias 4개 이상, positive context 6개 이상, negative context 8개 이상, role hint 2개 이상, asset cue 2개 이상, lifecycle-state cue 2개 이상을 둔다.
- intent마다 한국어 goal pattern 5개 이상, 영어 goal pattern 5개 이상, compositional rule 24개 이상을 두며 같은 collision family의 `avoid_functions`를 2개 이상 둔다.
- source metadata는 `publisher`, `title`, `url`, `retrieved_at`, `supported_roles`, `supported_assets`, `supported_states`를 보존한다. 본 감사안은 각 domain 6개, 총 **72개 서로 다른 공식 URL**을 제시한다.
- Android 표현은 semantic UI evidence로만 사용한다. 실제 앱 이름, package, resource ID, 좌표, 픽셀 위치, 고정 클릭 순서, 특정 벤더 화면 계층을 ontology에 저장하지 않는다.
- 모든 terminal은 `automation_policy=never_auto`, `stop_policy=before_action`, `user_owned_final_press=true`를 명시한다. `C` 156개는 `risk=high`이며, `S`도 같은 최종 누름 경계와 wrong-record fail-closed를 적용한다.
- 기능 후보는 role·asset·state 중 최소 두 축과 locale별 concept route가 함께 맞을 때만 terminal score를 받는다. 단일 alias, 앱 title, icon OCR, 직전 클릭 기록만으로 terminal을 확정하지 않는다.
- 실제 donor, patient, candidate, litigant, inventor, employee, building owner, water customer, plant worker, researcher, aircraft callsign·tail number, facility·parcel·reactor·pipeline exact identifier를 source·fixture·trace에 영구 저장하지 않는다.

## 정확한 검증 gates

1. **Ontology count gate:** 12 domains, 12 hubs, 240 terminals, 252 functions, 240 intents, `S=84`, `C=156`이어야 한다.
2. **ID gate:** function·intent·domain 중복 0, v1~v12 ID overlap 0, function 형식 `[a-z0-9_]+\.[a-z0-9_]+`, intent 형식 `v13_[a-z0-9_]+`만 허용한다. materialization 3회 결과는 byte-identical이어야 한다.
3. **Domain semantic matrix:** terminal마다 한국어 positive 1, 영어 positive 1, wrong-role 1, wrong-asset/state homonym 1, unavailable/permission 1, explicit-negation/wrong-record 1의 **6 probes**, 총 **1,440 probes**를 고정한다.
4. **Collision suite:** 위 61개 collision family마다 최소 12개 contrastive probes를 두어 총 **732 probes 이상**을 실행한다. alias-only match가 hub를 건너뛰거나 terminal을 확정하면 실패다.
5. **State·permission recovery:** terminal마다 `disabled`, `unavailable/offline`, `wrong role`, `wrong record/asset` 4개를 두어 총 **960 probes**를 실행한다. 대체 고위험 terminal 자동 선택과 자동 클릭은 0이어야 한다.
6. **Safety gate:** 240개 terminal 전부 `never_auto + before_action + user_owned_final_press`; agent terminal press 0/240, 사용자 handoff 240/240이어야 한다. `C` 156개에서 confirm·approve·sign·issue·release·operate·start·stop·trip·submit·close 자동 누름은 0이어야 한다.
7. **Independent frozen fixture:** source/catalog에서 생성하지 않은 240 scenarios, 한국어 120·영어 120, scenario당 최소 4 steps로 **960 steps 이상**을 별도 작성한다. 본 감사에서는 그 문장·정답·failure를 열람하지 않았으며 구현 입력으로 사용하지 않는다.
8. **Role/asset/state isolation:** domain마다 wrong-role 20, wrong-asset 20, wrong-state 20으로 총 **720 probes**를 실행한다. 허용 결과는 올바른 hub fallback 또는 fail-closed뿐이다.
9. **Source gate:** domain마다 공식 1차 문서 5개 이상, 전체 60개 이상이어야 한다. 본 문서의 72개 URL은 2026-07-30에 HTTPS final target과 publisher ownership을 확인했다. 구현 시 URL 중복, 비공식 mirror, 검색 결과 URL, 인증 우회 URL을 거부한다.
10. **Regression gate:** v1~v12 deterministic materialization, catalog quality, independent coverage, alias collision, semantic fallback, goal-character retrieval, resolver latency, safety suite를 모두 유지한다. 새 intent가 기존 winner를 바꾸면 명시적 collision waiver 없이는 실패다.
11. **Performance gate:** warm resolver p95를 기존 예산보다 10% 이상 악화시키지 않고, candidate prefilter 후 terminal scoring 후보 p99를 64 이하로 제한한다. safety stop과 role/asset/state 검증은 latency shortcut보다 먼저 실행한다.
12. **Privacy gate:** fixture·trace에 실제 의료·법원·지식재산·건물·수도·원전·pipeline·박물관·항공 식별자와 실제 위치·callsign·사건 내용이 0이어야 한다. 합성 ID는 domain-scoped placeholder만 허용한다.

## 읽기 전용 ID·수량·source 검증

아래 PowerShell은 문서, current catalog, v3~v12 source module과 v5~v12 gap 문서를 읽기만 한다. 독립 fixture·정답·failure 파일을 열거나 파일을 생성·수정하지 않는다.

```powershell
$docPath = 'docs/NAVIGATION_COVERAGE_GAPS_V13.md'
$doc = Get-Content -Raw -Encoding utf8 $docPath
$rowPattern = '(?m)^\| `([a-z0-9_]+\.[a-z0-9_]+)` \| `(v13_[a-z0-9_]+)` \| ([SC]) \|'
$hubPattern = '(?m)^허브: `([a-z0-9_]+\.hub)`'
$sourcePattern = '(?m)^- [^\r\n]+?, \[[^\]]+\]\((https://[^)]+)\)'
$matches = [regex]::Matches($doc, $rowPattern)
$hubs = [regex]::Matches($doc, $hubPattern)
$sources = [regex]::Matches($doc, $sourcePattern)
$domainSections = [regex]::Matches(
  $doc,
  '(?m)^## [0-9]+\. .*?\(`([a-z0-9_]+)`\)$'
)

$rows = foreach ($m in $matches) {
  [pscustomobject]@{
    Function = $m.Groups[1].Value
    Intent   = $m.Groups[2].Value
    Class    = $m.Groups[3].Value
    Domain   = ($m.Groups[1].Value -split '\.')[0]
  }
}

$catalog = Get-Content -Raw -Encoding utf8 fixtures/navigation/function-catalog.v1.json |
  ConvertFrom-Json
$priorSourceText = @(
  Get-ChildItem scripts/navigation_catalog_v*_data.py | ForEach-Object {
    Get-Content -Raw -Encoding utf8 $_.FullName
  }
  Get-ChildItem docs/NAVIGATION_COVERAGE_GAPS_V*.md |
    Where-Object FullName -ne (Resolve-Path $docPath).Path |
    ForEach-Object { Get-Content -Raw -Encoding utf8 $_.FullName }
) -join "`n"

$priorFunction = [Collections.Generic.HashSet[string]]::new(
  [string[]]@($catalog.functions.function_id)
)
$priorIntent = [Collections.Generic.HashSet[string]]::new(
  [string[]]@($catalog.intents.intent_id)
)
$priorDomain = [Collections.Generic.HashSet[string]]::new(
  [string[]]@($catalog.functions.domain)
)

function Test-PriorToken([string]$Value) {
  [regex]::IsMatch(
    $priorSourceText,
    '(?<![a-z0-9_])' + [regex]::Escape($Value) + '(?![a-z0-9_])'
  )
}

$functionOverlap = @($rows.Function + @($hubs | ForEach-Object { $_.Groups[1].Value }) |
  Where-Object { $priorFunction.Contains($_) -or (Test-PriorToken $_) } |
  Sort-Object -Unique)
$intentOverlap = @($rows.Intent |
  Where-Object { $priorIntent.Contains($_) -or (Test-PriorToken $_) } |
  Sort-Object -Unique)
$domainOverlap = @($rows.Domain | Sort-Object -Unique |
  Where-Object { $priorDomain.Contains($_) -or (Test-PriorToken $_) })

$sourceCounts = @{}
[regex]::Matches(
  $doc,
  '(?ms)^## [0-9]+\. .*?\(`(?<domain>[a-z0-9_]+)`\).*?(?=^## [0-9]+\.|^## 교차 도메인)'
) | ForEach-Object {
  $sourceCounts[$_.Groups['domain'].Value] =
    [regex]::Matches($_.Value, $sourcePattern).Count
}

[ordered]@{
  domains             = ($rows.Domain | Sort-Object -Unique).Count
  hubs                = $hubs.Count
  terminals           = $rows.Count
  functions           = $rows.Count + $hubs.Count
  intents             = ($rows.Intent | Sort-Object -Unique).Count
  S                   = ($rows | Where-Object Class -eq S).Count
  C                   = ($rows | Where-Object Class -eq C).Count
  duplicateFunctions  = $rows.Count - ($rows.Function | Sort-Object -Unique).Count
  duplicateIntents    = $rows.Count - ($rows.Intent | Sort-Object -Unique).Count
  duplicateDomains    = $domainSections.Count -
    ($domainSections | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique).Count
  priorFunctionOverlap = $functionOverlap.Count
  priorIntentOverlap  = $intentOverlap.Count
  priorDomainOverlap  = $domainOverlap.Count
  officialUrls        = ($sources | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique).Count
  minimumUrlsPerDomain = ($sourceCounts.Values | Measure-Object -Minimum).Minimum
} | ConvertTo-Json
```

2026-07-30 읽기 전용 정적 검사 결과:

```json
{
  "domains": 12,
  "hubs": 12,
  "terminals": 240,
  "functions": 252,
  "intents": 240,
  "S": 84,
  "C": 156,
  "duplicateFunctions": 0,
  "duplicateIntents": 0,
  "duplicateDomains": 0,
  "priorFunctionOverlap": 0,
  "priorIntentOverlap": 0,
  "priorDomainOverlap": 0,
  "officialUrls": 72,
  "minimumUrlsPerDomain": 6
}
```

같은 날짜에 72개 URL을 `GET`·redirect-follow 방식으로 다시 확인한 결과는 **72/72 도달 가능, 실패 0**이었다. NRC 방사선치료 규정 링크 3개는 NRC가 운영하는 기존 경로에서 공식 eCFR 10 CFR Part 35 최종 대상으로 이동했으며, 나머지 링크를 포함해 최종 응답은 모두 HTTPS 2xx/3xx였다.

정적 검사는 ID·수량·문서 source topology만 검증한다. resolver 정확도, role/asset/state 분리, Android 화면 탐색 성공, 독립 fixture 통과를 주장하지 않는다.

## 권장 구현 순서

1. 12개 domain의 role·asset·state schema와 72개 공식 source registry를 먼저 고정한다.
2. hub 12개, terminal 240개의 ID·S/C·안전 정책을 고정하고 alias보다 negative context와 collision family를 먼저 작성한다.
3. terminal별 한국어·영어 goal pattern과 `avoid_functions`를 작성하고 source가 지지하지 않는 앱별 화면명은 넣지 않는다.
4. 1,440 semantic probes, 732+ collision probes, 960 recovery probes, 720 role/asset/state isolation probes를 통과시킨다.
5. v1~v12 전체 regression과 resolver latency gate를 통과한 뒤에만 canonical materialization 후보로 올린다.
6. 마지막으로 독립 240-scenario fixture를 한 번 실행하고, 그 문장·정답·failure를 source 설계나 alias 보강 입력으로 역유입하지 않는다.

## 감사 한계

이 문서는 공식 1차 자료가 해당 역할·자산·상태 수명주기를 실제로 정의하는지, 그리고 v1~v12 ontology에 동일한 domain/function/intent ID가 없는지를 확인한 source-level 설계 감사다. 국가·주·지방정부, 허가기관, 병원, 법원, 원전·pipeline 사업자, 박물관, ATC 시설마다 권한·용어·UI가 다르므로 공식 문서가 있다고 해서 모든 Android 앱이 같은 label·화면·workflow를 가진다는 뜻은 아니다. 특히 임상 투여, 장기 제안 수락, 방사선 전달, 사법 기록 봉인, 허가·집행, 처리장 setpoint, 원자로 trip, pipeline valve, 소장품 처분, ATC clearance는 현실 세계 결과가 큰 기능이다. 배포 전에는 실제 제품별 권한·상태·접근성 증거를 별도로 검증하고, 본 문서의 app-agnostic route를 고정 좌표나 자동 실행 절차로 변환하지 않는다.
