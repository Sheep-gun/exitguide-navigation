# Navigation Coverage Gaps V16 — Partial-terminal refinement

- 검증일: **2026-07-30**
- 상태: **materialization 전 source-constrained refinement 제안**
- 입력 범위: `NAVIGATION_COVERAGE_GAPS_V16.md`, V16 source pack 2개, V16 gap-closure pack 3개, canonical catalog의 ID·기능명·intent pattern 및 equivalence ID
- 명시적 제외: independent fixture, answer, failure, evaluation, report 및 그 파생 통계

이 문서는 공식 근거가 `partially_resolved`로 판정한 terminal 16개를 그대로 승격하지 않고, 근거가 직접 보장하는 역할·자산·상태 전이로 좁힌다. 특정 제품의 버튼·화면·API가 공식 출처에 없으면 그러한 UI의 존재를 추정하지 않는다. 이메일·우편·fillable form 또는 조직 내부 절차가 공식 채널인 경우에는 그 채널을 그대로 모델링한다.

## 1. 보존 불변식과 결정 원칙

### 1.1 정확한 수량 불변식

| 항목 | 원 V16 제안 | 이번 교체 | refinement 후 |
|---|---:|---:|---:|
| 도메인 | 12 | 0 | **12** |
| 도메인별 hub | 1 | 0 | **각 1, 총 12** |
| terminal | 240 | `16 old - 16 new` | **240** |
| S terminal | 84 | `1 old - 1 new` | **84** |
| C terminal | 156 | `15 old - 15 new` | **156** |
| 도메인별 terminal | 20 | 각 도메인에서 1:1 교체 | **각 20** |

`partially_resolved` 분포는 food 1, wireless 4, commercial space 2, radioactive materials 2, hazmat 3, firearms 2, commercial vessel 2로 정확히 **16개**다. 이 중 food 항목만 S이고 나머지 15개는 C다.

### 1.2 정제 규칙

1. **이름 좁히기(A):** 관할·서비스·대역·선박 class·물질 category를 ID와 guard에 명시한다.
2. **복합 전이 분리 후 하나 선택(B):** 하나의 old terminal이 여러 전이를 합쳤다면, 현재 공식 근거가 가장 직접적으로 입증하는 전이 하나만 count-neutral replacement로 채택한다. 나머지는 기존 terminal과 연결하거나 materialization하지 않는 future candidate로 남긴다.
3. **강한 동사 제거:** 공식 근거가 `approve`, `authorize`, `certify`, `closeout`, 독립 `record`를 입증하지 않으면 `attach`, `submit`, `assess`, `verify`, `prepare`, `maintain`, `implement`, `decide`처럼 실제 근거가 있는 동사로 바꾼다.
4. **guard 불충족 시 abstain/hub:** 아래 관할 guard 중 하나라도 확인되지 않으면 해당 terminal을 제안하지 않고 도메인 hub 또는 명시된 인접 terminal로 보낸다.
5. **제품 UI 비추정:** 출처가 온톨로지 전이만 입증하면 버튼명·화면명·API endpoint는 catalog fact로 저장하지 않는다.

## 2. 16개 exact old → new mapping

| # | S/C | 결정 | 기존 terminal | replacement terminal |
|---:|:---:|:---:|---|---|
| 1 | S | A | `food_manufacturing_recall_ops.product_complaint_signal_queue` | `food_manufacturing_recall_ops.fda_hfcs_case_review_status` |
| 2 | C | A | `wireless_spectrum_license_ops.frequency_coordination_attach` | `wireless_spectrum_license_ops.vacated_800mhz_coordination_certification_attach` |
| 3 | C | B | `wireless_spectrum_license_ops.buildout_certification_submit` | `wireless_spectrum_license_ops.lower_700mhz_buildout_evidence_attach` |
| 4 | C | A | `wireless_spectrum_license_ops.license_cancellation_request` | `wireless_spectrum_license_ops.form601_full_license_cancellation_apply` |
| 5 | C | A | `wireless_spectrum_license_ops.discontinuance_notice_file` | `wireless_spectrum_license_ops.cellular_permanent_discontinuance_notice_file` |
| 6 | C | B | `commercial_space_launch_licensing_ops.launch_mission_authorization_request` | `commercial_space_launch_licensing_ops.preflight_mission_information_submit` |
| 7 | C | A | `commercial_space_launch_licensing_ops.launch_readiness_certify` | `commercial_space_launch_licensing_ops.launch_readiness_assess` |
| 8 | C | B | `radioactive_materials_license_ops.leak_test_result_certify` | `radioactive_materials_license_ops.sealed_source_leak_test_result_record` |
| 9 | C | B | `radioactive_materials_license_ops.radioactive_material_shipment_authorize` | `radioactive_materials_license_ops.category1_2_recipient_license_verify` |
| 10 | C | A | `hazardous_materials_transport_compliance.route_plan_approve` | `hazardous_materials_transport_compliance.safety_permit_route_plan_maintain` |
| 11 | C | A | `hazardous_materials_transport_compliance.carrier_acceptance_record` | `hazardous_materials_transport_compliance.carrier_package_transport_condition_decide` |
| 12 | C | A | `hazardous_materials_transport_compliance.security_plan_approve` | `hazardous_materials_transport_compliance.transportation_security_plan_implement` |
| 13 | C | A | `firearms_dealer_compliance_ops.inventory_discrepancy_record` | `firearms_dealer_compliance_ops.unaccounted_firearm_report_submit` |
| 14 | C | B | `firearms_dealer_compliance_ops.license_surrender_closeout` | `firearms_dealer_compliance_ops.out_of_business_records_set_prepare` |
| 15 | C | A | `commercial_vessel_safety_compliance.manning_exception_request` | `commercial_vessel_safety_compliance.honolulu_dive_snorkel_reduced_manning_endorsement_request` |
| 16 | C | A | `commercial_vessel_safety_compliance.vessel_decommission_record` | `commercial_vessel_safety_compliance.vessel_documentation_deletion_letter_request` |

## 3. Terminal별 정제 명세

### 3.1 FDA/HFCS 식품 불만사건 검토 상태 (S)

- **Exact mapping:** `food_manufacturing_recall_ops.product_complaint_signal_queue` → `food_manufacturing_recall_ops.fda_hfcs_case_review_status`
- **이름:** FDA 인체식품 불만사건 검토 상태 / FDA human-food complaint case review status
- **목표:** FDA HFCS에 접수된 이 식품·건강보조식품 사건의 관할·임상검토·추가평가 상태를 보여 줘 / Show jurisdiction, clinical-review, and further-evaluation status for this FDA HFCS food or dietary-supplement case
- **Role / asset:** FDA Human Foods Program clinical reviewer·FDA investigator / HFCS complaint or adverse-event case, report ID, suspect food or dietary supplement, symptom/outcome, lot/sample and follow-up information.
- **State / transition:** `received -> jurisdiction_and_seriousness_screened -> clinical_review -> potential_safety_concern | no_causal_determination -> further_evaluation_or_investigation -> possible_regulatory_or_communication_action`.
- **Jurisdiction guard:** 미국 FDA 관할 food 또는 dietary supplement이고, actor가 FDA/HFP 검토자 또는 investigator여야 한다. manufacturer 내부 complaint queue, FDA 비관할 제품, 또는 causation이 확정됐다는 요청에는 활성화하지 않는다.
- **Accepted official sources:** [FDA Human Foods Complaint System](https://www.fda.gov/food/compliance-enforcement-food/human-foods-complaint-system-hfcs), [FDA — What Happens When a Problem is Reported?](https://www.fda.gov/safety/questions-and-answers-problem-reporting/what-happens-when-problem-reported)
- **Nearest existing-domain non-equivalence:** `reportable_food_case_status`는 책임 당사자의 Reportable Food Registry 보고 lifecycle이다. 새 terminal은 FDA 내부 complaint/adverse-event 임상 검토와 `no_causal_determination`을 포함하므로 보고대상 식품 사건 상태와 같지 않다.

### 3.2 공석 800 MHz 채널 조정인증서 첨부 (C)

- **Exact mapping:** `wireless_spectrum_license_ops.frequency_coordination_attach` → `wireless_spectrum_license_ops.vacated_800mhz_coordination_certification_attach`
- **이름:** 공석 800 MHz 채널 조정인증서 첨부 / Vacated-800-MHz channel coordination-certification attachment
- **목표:** 공인 주파수 조정자가 발급한 공석 800 MHz 채널 조정인증서를 이 신청에 첨부하는 곳으로 가 줘 / Take me to attach the certified coordinator's vacated-800-MHz channel certification to this application
- **Role / asset:** applicant와 Commission-certified frequency coordinator / vacated-800-MHz channel application, site, frequency and coordinator certification.
- **State / transition:** `candidate_site_and_channel_selected -> coordination_and_conflict_resolution -> certification_issued -> certification_attached -> application_ready_to_submit`.
- **Jurisdiction guard:** FCC DA-14-1904가 다루는 vacated 800 MHz channel 신청 profile, Commission-certified coordinator, 해당 certification asset이 모두 존재해야 한다. 다른 Part 90 service 또는 일반 ULS 신청에는 범용화하지 않는다.
- **Accepted official source:** [FCC DA-14-1904](https://docs.fcc.gov/public/attachments/DA-14-1904A1.pdf)
- **Nearest existing-domain non-equivalence:** `application_submit`은 서명된 신청 전체의 최종 제출이고, 이 terminal은 그 전에 특정 coordinator certification을 붙이는 asset-scoped subtransition이다.

### 3.3 저대역 700 MHz 구축증빙 첨부 (C)

- **Exact mapping:** `wireless_spectrum_license_ops.buildout_certification_submit` → `wireless_spectrum_license_ops.lower_700mhz_buildout_evidence_attach`
- **이름:** 저대역 700 MHz 구축증빙 첨부 / Lower-700-MHz buildout-evidence attachment
- **목표:** 구축기준 판정과 검증된 커버리지 지도·증빙을 이 저대역 700 MHz 건설통지에 첨부하는 곳으로 가 줘 / Take me to attach the benchmark determination and verified coverage map and evidence to this Lower-700-MHz construction notification
- **Role / asset:** Lower-700-MHz licensee 또는 authorized filer/certifier / call sign, applicable EA·CMA·REAG benchmark, coverage map, supporting documentation and construction notification.
- **State / transition:** `benchmark_due -> compliance_determined -> evidence_validated -> map_and_supporting_documents_attached -> construction_notification_ready_to_submit`.
- **Jurisdiction guard:** source가 다루는 Lower 700 MHz license와 해당 performance benchmark profile이어야 하며 `radio_service`, `benchmark_type`, `deadline`, `evidence_required`가 모두 바인딩돼야 한다. 다른 band에는 활성화하지 않는다.
- **Accepted official source:** [FCC DA-13-1278](https://docs.fcc.gov/public/attachments/DA-13-1278A1.pdf)
- **분리 결과:** notification 전체 제출은 기존 `construction_notification_file`이 담당한다. 이번 replacement는 coverage map과 supporting evidence의 첨부만 담당하므로 두 terminal을 합치지 않는다.
- **Nearest existing-domain non-equivalence:** `construction_notification_file`은 completed construction/operation의 notification 제출이고, 새 terminal은 그 notification에 특정 Lower-700-MHz buildout evidence를 준비·첨부하는 선행 단계다.

### 3.4 Form 601 전체 무선면허 취소 신청 (C)

- **Exact mapping:** `wireless_spectrum_license_ops.license_cancellation_request` → `wireless_spectrum_license_ops.form601_full_license_cancellation_apply`
- **이름:** Form 601 전체 무선면허 취소 신청 / Form-601 full wireless-license cancellation application
- **목표:** 권한 있는 서명자가 이 호출부호의 모든 시설을 취소하는 Form 601 CA 신청을 제출하는 곳으로 가 줘 / Take me to submit the authorized signer's Form-601 CA application cancelling every facility under this call sign
- **Role / asset:** FCC wireless licensee, delegated filer/agent and authorized signer / FRN, call sign, whole license, every facility under that call sign, signature and submission date.
- **State / transition:** `license_active -> CA_application_signed_and_submitted -> FCC_review -> granted -> license_cancelled_and_notice_generated`.
- **Jurisdiction guard:** FCC WTB Form 601/ULS license, application purpose `CA`, whole-call-sign cancellation, authorized signature가 확인돼야 한다. 일부 facility 제거는 `license_modification_apply`로 보내며, materialization 시 최신 Form 601 revision과 현재 submission channel을 다시 확인한다.
- **Accepted official sources:** [FCC Form 601 instructions](https://docs.fcc.gov/public/attachments/DOC-298965A1.pdf), [FCC DA-16-1039](https://docs.fcc.gov/public/attachments/DA-16-1039A1.pdf)
- **Nearest existing-domain non-equivalence:** `license_modification_apply`는 승인 주파수·출력·위치 또는 일부 시설을 변경하는 신청이다. 새 terminal은 call sign 아래 모든 facility를 없애는 voluntary cancellation이다.

### 3.5 셀룰러 영구 운용중단 통지 (C)

- **Exact mapping:** `wireless_spectrum_license_ops.discontinuance_notice_file` → `wireless_spectrum_license_ops.cellular_permanent_discontinuance_notice_file`
- **이름:** 셀룰러 영구 운용중단 통지 / Cellular permanent-discontinuance notice filing
- **목표:** Part 22 셀룰러 서비스의 180일 영구 중단 후 10일 이내 중단 통지를 제출하는 곳으로 가 줘 / Take me to file the discontinuance notice within 10 days after 180 days of permanent discontinuance in Part-22 Cellular Service
- **Role / asset:** Part-22 cellular licensee 또는 authorized filer / call sign, CGSA or covered cellular service, discontinuance start date and Form 601 notification.
- **State / transition:** `service_active -> permanent_discontinuance_started -> 180_days_elapsed -> notice_due_within_10_days -> notice_filed -> automatic_termination_reflected`.
- **Jurisdiction guard:** 47 CFR Part 22 Cellular Service와 source의 180-day/10-day rule profile이 정확히 적용돼야 한다. 다른 wireless service의 기간·효과는 별도 규칙 없이는 추정하지 않는다.
- **Accepted official source:** [FCC DA-18-414](https://docs.fcc.gov/public/attachments/DA-18-414A1.pdf)
- **Nearest existing-domain non-equivalence:** 위의 `form601_full_license_cancellation_apply`는 licensee가 먼저 선택하는 voluntary whole-license cancellation이다. 이 terminal은 실제 permanent discontinuance와 법정 기간 경과가 선행하고 automatic termination 효과가 뒤따르는 notice다.

### 3.6 발사 전 임무별 정보 제출 (C)

- **Exact mapping:** `commercial_space_launch_licensing_ops.launch_mission_authorization_request` → `commercial_space_launch_licensing_ops.preflight_mission_information_submit`
- **이름:** 발사 전 임무별 정보 제출 / Preflight mission-specific information submission
- **목표:** Part 450 면허 범위의 이 임무별 정보와 갱신된 비행분석을 합의된 채널로 제출하는 곳으로 가 줘 / Take me to submit this mission-specific information and updated flight analysis under the Part-450 license through the agreed channel
- **Role / asset:** Part-450 licensee/operator와 FAA/AST reviewer / existing vehicle operator license, vehicle, payload, trajectory, site, schedule, mission-specific information and updated flight analysis.
- **State / transition:** `operator_license_active -> mission_information_due_normally_60_days_prior -> information_submitted -> updated_flight_analysis_due_normally_30_days_prior -> FAA_preflight_review_supported`.
- **Jurisdiction guard:** FAA 14 CFR Part 450 vehicle operator license의 scope 안에 있는 mission이어야 하며, license 자체가 one or more launches/reentries를 authorize한다. submission channel은 email attachment 또는 license에서 합의한 방법이며 별도 mission authorization issuance를 만들지 않는다.
- **Accepted official sources:** [14 CFR §450.213](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-D/section-450.213), [14 CFR §450.3](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-A/section-450.3)
- **분리 결과:** `mission authorization request` 개념은 제거한다. mission이 기존 license 범위를 벗어나면 새 terminal이 아니라 기존 `license_modification_request`로 보낸다.
- **Nearest existing-domain non-equivalence:** `license_modification_request`는 승인 vehicle/site/operation scope를 변경한다. 새 terminal은 scope를 바꾸지 않고 이미 허가된 mission의 사전 정보를 제공한다.

### 3.7 발사 준비성 평가 (C)

- **Exact mapping:** `commercial_space_launch_licensing_ops.launch_readiness_certify` → `commercial_space_launch_licensing_ops.launch_readiness_assess`
- **이름:** 발사 준비성 평가 / Launch-readiness assessment
- **목표:** 문서화된 Part 450 절차와 기준으로 이 임무의 안전필수 인력·시스템·서비스 준비성을 평가하는 곳으로 가 줘 / Take me to assess safety-critical personnel, systems, and service readiness for this mission under the documented Part-450 procedure and criteria
- **Role / asset:** operator/license applicant, safety organization and safety-critical personnel / vehicle, site, safety-critical personnel, systems, software, procedures, equipment, property, services and mishap response plan.
- **State / transition:** `mission_planned -> documented_readiness_criteria_applied -> ready | not_ready -> unresolved_safety_items_remediated -> operation_eligible_to_proceed`.
- **Jurisdiction guard:** 14 CFR Part 450 safety program과 operator-specific documented readiness procedure가 존재해야 한다. FAA 공통 certification, 단일 submit 화면 또는 readiness meeting 자체를 필수로 추정하지 않는다.
- **Accepted official source:** [14 CFR §450.155](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450/subpart-C/section-450.155)
- **Nearest existing-domain non-equivalence:** `safety_review_status`는 application/launch configuration의 미해결 safety-analysis item을 읽는 S terminal이다. 새 terminal은 operator가 mission readiness criteria를 실제 적용하는 C assessment다.

### 3.8 밀봉선원 누설시험 결과 기록 (C)

- **Exact mapping:** `radioactive_materials_license_ops.leak_test_result_certify` → `radioactive_materials_license_ops.sealed_source_leak_test_result_record`
- **이름:** 밀봉선원 누설시험 결과 기록 / Sealed-source leak-test result record
- **목표:** 허용된 수행자가 완료한 이 밀봉선원의 식별정보·시험일·누설시험 결과를 기록하는 곳으로 가 줘 / Take me to record this sealed source's identity, test date, and completed leak-test result from an authorized performer
- **Role / asset:** licensee, permitted testing service or performer, RSO/source custodian / sealed-source model·serial, radionuclide/activity, test date, result, performer identity and retained record.
- **State / transition:** `test_due -> authorized_sampling_and_test -> result_recorded -> below_threshold_continued_use | above_threshold_use_stopped_and_source_isolated`.
- **Jurisdiction guard:** source와 use program이 10 CFR Part 35 medical use 또는 Part 34 industrial radiography profile 중 하나로 명시돼야 하며 주기·threshold·tester authority는 그 profile에서 가져온다. Agreement State 관할은 별도 rule pack 없이는 활성화하지 않는다.
- **Accepted official sources:** [10 CFR §35.2067](https://www.ecfr.gov/current/title-10/chapter-I/part-35/subpart-L/section-35.2067), [NRC 10 CFR §34.27](https://www.nrc.gov/reading-rm/doc-collections/cfr/part034/part034-0027.html)
- **분리 결과:** 위반 threshold를 넘은 source의 regulator report는 이 terminal에 합치지 않고 future `report_leaking_source` transition으로 남긴다.
- **Nearest existing-domain non-equivalence:** `annual_inventory_certify`는 tracked-source 전체의 연간 physical reconciliation이고, 새 terminal은 개별 sealed source의 주기적 leak-test result record다.

### 3.9 1·2범주 물질 수취면허 검증 (C)

- **Exact mapping:** `radioactive_materials_license_ops.radioactive_material_shipment_authorize` → `radioactive_materials_license_ops.category1_2_recipient_license_verify`
- **이름:** 1·2범주 물질 수취면허 검증 / Category-1/2 material recipient-license verification
- **목표:** 1·2범주 방사성물질 이전 전에 LVS 또는 관할 규제기관으로 수취인의 권한과 보유한도를 검증하는 곳으로 가 줘 / Take me to verify the recipient's authority and possession limits through LVS or the licensing authority before transferring Category-1/2 radioactive material
- **Role / asset:** transferor/supplier licensee, recipient licensee, NRC or Agreement State licensing authority / recipient license image, material type·form·quantity·location, possession limit and LVS verification.
- **State / transition:** `transfer_proposed -> recipient_authority_and_limits_checked -> verification_complete | blocked_pending_regulator_confirmation -> transfer_eligible_or_blocked`.
- **Jurisdiction guard:** 10 CFR §37.71 Category 1/Category 2 quantity transfer여야 한다. LVS 결과 또는 licensing authority confirmation이 필요하며, 모든 radioactive shipment에 확대하지 않는다.
- **Accepted official sources:** [NRC License Verification System overview](https://www.nrc.gov/security/byproduct/ismp/lvs/overview.html), [NRC 10 CFR §37.71](https://www.nrc.gov/reading-rm/doc-collections/cfr/part037/part037-0071.html)
- **분리 결과:** package inspection/compliance는 별도 precondition이고 조직 내부 `shipment_release_authorize`는 공식 NRC terminal로 materialize하지 않는다. 이 replacement는 recipient authority verification만 소유한다.
- **Nearest existing-domain non-equivalence:** `sealed_source_transfer_record`는 허용된 licensee 사이에서 일어난 source transfer transaction을 기록한다. 새 terminal은 그 전 단계에서 recipient의 legal authority와 possession limit을 검증한다.

### 3.10 안전허가 대상 위험물 경로계획 유지 (C)

- **Exact mapping:** `hazardous_materials_transport_compliance.route_plan_approve` → `hazardous_materials_transport_compliance.safety_permit_route_plan_maintain`
- **이름:** 안전허가 대상 위험물 경로계획 유지 / Safety-permit hazmat route-plan maintenance
- **목표:** 안전허가 적용 Class 7 또는 폭발물 운송에 필요한 서면 경로계획을 작성·유지하는 곳으로 가 줘 / Take me to prepare and maintain the written route plan required for this safety-permit Class-7 or explosives movement
- **Role / asset:** hazardous-materials safety-permit motor carrier와 vehicle operator / permit, material/movement and written route plan.
- **State / transition:** `permit_and_material_scope_identified -> applicable_route_rule_selected -> written_route_plan_developed -> plan_maintained_for_movement`.
- **Jurisdiction guard:** 미국 highway movement, applicable Hazmat Safety Permit, 그리고 `route_rule_profile = class_7_49_cfr_397_101 | explosives_part_397_19` 중 하나가 확인돼야 한다. 승인 주체나 승인 완료 상태를 만들지 않는다.
- **Accepted official source:** [FMCSA — Hazmat Safety Permit route-plan duties](https://www.fmcsa.dot.gov/regulations/hazardous-materials/what-are-carriers-required-do-obtain-and-keep-hazardous-materials)
- **Nearest existing-domain non-equivalence:** `security_plan_status`는 Part-172 security plan의 적용·검토 상태를 읽는다. 새 terminal은 safety-permit 대상 특정 movement의 written route plan을 작성·유지한다.

### 3.11 운송인 위험물 포장 운송가능 상태 판정 (C)

- **Exact mapping:** `hazardous_materials_transport_compliance.carrier_acceptance_record` → `hazardous_materials_transport_compliance.carrier_package_transport_condition_decide`
- **이름:** 운송인 위험물 포장 운송가능 상태 판정 / Carrier hazmat-package transport-condition decision
- **목표:** 운송인이 제시된 위험물 포장의 운송가능 상태를 검사해 인수 가능 또는 인수 차단으로 판정하는 곳으로 가 줘 / Take me to have the carrier inspect the offered hazmat package and decide acceptability or block acceptance
- **Role / asset:** offeror/shipper와 accepting carrier / completed hazardous-material package and its condition for shipment.
- **State / transition:** `package_in_shipper_possession -> package_offered -> carrier_condition_check -> acceptable_and_may_accept | not_in_condition_and_acceptance_blocked`.
- **Jurisdiction guard:** 49 CFR Parts 171–180이 적용되는 미국 commercial hazmat transport이고 carrier가 package를 인수하기 전이어야 한다. 별도 electronic acceptance record나 PHMSA 제출 asset을 추정하지 않는다.
- **Accepted official source:** [PHMSA Interpretation #22-0123](https://www.phmsa.dot.gov/regulations/title49/interp/22-0123)
- **Nearest existing-domain non-equivalence:** `package_nonconformance_hold`는 PHMSA enforcement/risk assessment 뒤 packaging을 service에서 제거하거나 사용 차단하는 전이다. 새 terminal은 offer 시점 carrier의 condition-for-shipment acceptability decision이다.

### 3.12 위험물 운송 보안계획 구현 (C)

- **Exact mapping:** `hazardous_materials_transport_compliance.security_plan_approve` → `hazardous_materials_transport_compliance.transportation_security_plan_implement`
- **이름:** 위험물 운송 보안계획 구현 / Hazmat transportation-security-plan implementation
- **목표:** 49 CFR 172 Subpart I 적용 운송의 인사·무단접근·운송중 보안조치를 구현하는 곳으로 가 줘 / Take me to implement personnel, unauthorized-access, and en-route measures for this transport covered by 49 CFR Part 172 Subpart I
- **Role / asset:** covered hazmat offeror/carrier and, during incident storage or transfer, the responsible party / written transportation security plan and personnel, unauthorized-access, en-route measures.
- **State / transition:** `covered_activity_identified -> plan_required -> measures_implemented -> plan_active_during_transport_or_incident -> responsibility_transferred_if_applicable`.
- **Jurisdiction guard:** 49 CFR Part 172 Subpart I coverage가 확인되고 현재 actor가 plan 책임 party여야 한다. regulator approval request 또는 approval completed state를 만들지 않는다.
- **Accepted official source:** [PHMSA Interpretation #10-0083](https://www.phmsa.dot.gov/regulations/title49/interp/10-0083)
- **Nearest existing-domain non-equivalence:** `security_plan_status`는 적용 계획과 review state를 보는 S terminal이고, 새 terminal은 covered party가 required measures를 실제 구현하는 C terminal이다.

### 3.13 미확인 미보유 총기 신고 제출 (C)

- **Exact mapping:** `firearms_dealer_compliance_ops.inventory_discrepancy_record` → `firearms_dealer_compliance_ops.unaccounted_firearm_report_submit`
- **이름:** 미확인 미보유 총기 신고 제출 / Unaccounted-firearm report submission
- **목표:** 실사에서 찾지 못했고 원인이 확인되지 않은 이 총기를 48시간 보고 절차로 신고하는 곳으로 가 줘 / Take me to report this unreconciled firearm of unknown cause through the 48-hour reporting procedure
- **Role / asset:** FFL, local law enforcement, ATF Stolen Firearms Program/NTC / unaccounted firearm inventory item, A&D record and ATF Form 3310.11.
- **State / transition:** `unaccounted_during_inventory -> reconciliation_attempted -> cause_unknown_and_item_still_missing -> telephone_and_written_report_due_within_48_hours -> reported`.
- **Jurisdiction guard:** 미국 FFL premises inventory, firearm이 물리적으로 account되지 않고 reconciliation 후에도 원인이 unknown이어야 한다. 단순 수량 오류·serial mismatch·수정 가능한 A&D entry에는 활성화하지 않는다.
- **Accepted official source:** [ATF — Report Firearms Theft or Loss](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/report-firearms-theft-or-loss)
- **Nearest existing-domain non-equivalence:** `theft_loss_report_submit`은 physical inventory로 theft 또는 loss가 확인된 사건이다. 새 terminal은 crime evidence가 없거나 recordkeeping error 가능성이 남은 `unaccounted/cause_unknown` branch에만 적용하며 두 guard를 동시에 만족시키지 않는다.

### 3.14 폐업 총기거래 기록 묶음 준비 (C)

- **Exact mapping:** `firearms_dealer_compliance_ops.license_surrender_closeout` → `firearms_dealer_compliance_ops.out_of_business_records_set_prepare`
- **이름:** 폐업 총기거래 기록 묶음 준비 / Out-of-business firearms-record set preparation
- **목표:** 폐업 FFL의 A&D 장부·Forms 4473·도난분실·다중판매 기록을 NTC 또는 지역 ATF 전달용으로 준비하는 곳으로 가 줘 / Take me to prepare the discontinued FFL's A&D books, Forms 4473, theft/loss, and multiple-sale records for delivery to NTC or the local ATF office
- **Role / asset:** discontinuing FFL and records custodian / A&D books, computer printouts, Forms 4473, theft/loss reports, multiple-sale reports and Brady forms.
- **State / transition:** `business_discontinued -> required_record_classes_identified -> record_set_complete_for_delivery -> records_pending_transfer`.
- **Jurisdiction guard:** 미국 FFL business가 실제로 discontinued됐고 out-of-business record rule이 적용돼야 한다. license surrender, license termination decision 또는 records delivered confirmation을 이 terminal이 소유하지 않는다.
- **Accepted official source:** [ATF — Discontinue Being a Federal Firearms Licensee](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/firearms/discontinue-being-a-federal-firearms-licensee-ffl)
- **분리 결과:** source가 직접 입증하지 않은 하나의 `license surrender closeout`은 제거한다. 준비 완료 뒤 실제 NTC/local ATF 전달은 기존 `records_disposition_transfer`가 담당한다.
- **Nearest existing-domain non-equivalence:** `records_disposition_transfer`는 완성된 record set을 지정 수탁처로 보내거나 전달 기록을 남기는 다음 전이다. 새 terminal은 빠진 record class가 없도록 전달 대상 묶음을 구성하는 선행 전이다.

### 3.15 호놀룰루 잠수·스노클선 감축정원 배서 요청 (C)

- **Exact mapping:** `commercial_vessel_safety_compliance.manning_exception_request` → `commercial_vessel_safety_compliance.honolulu_dive_snorkel_reduced_manning_endorsement_request`
- **이름:** 호놀룰루 잠수·스노클선 감축정원 배서 요청 / Honolulu dive/snorkel-vessel reduced-manning endorsement request
- **목표:** Sector Honolulu의 검사대상 소형여객 잠수·스노클선에 동등 안전성 근거를 갖춘 감축정원 COI 배서를 요청하는 곳으로 가 줘 / Take me to request a reduced-manning COI endorsement with equivalent-safety evidence for an inspected small passenger dive/snorkel vessel in Sector Honolulu
- **Role / asset:** small-passenger-vessel operator, attending Marine Inspector and OCMI / vessel COI, reduced-manning endorsement request and equivalent-level-of-safety evidence.
- **State / transition:** `full_manning_required -> request_prepared -> marine_inspector_safety_review -> OCMI_decision -> endorsement_active | denied | later_removed`.
- **Jurisdiction guard:** Sector Honolulu inspection zone, certificated inspected small passenger vessel, dive/snorkel operation, applicable work-instruction criteria를 모두 만족해야 한다. 다른 OCMI zone, vessel class 또는 operation에는 사용하지 않는다.
- **Accepted official source:** [USCG Sector Honolulu WI 31(2)](https://www.pacificarea.uscg.mil/Portals/8/District%2014/SectHono/docs/WI%2031%282%29%20-%20Reduced%20Manning%20Criteria%20for%20Dive%20and%20Snorkel.pdf)
- **Nearest existing-domain non-equivalence:** `crew_credential_manning_status`는 현재 crew credential과 minimum complement 충족 여부를 읽는 S terminal이다. 새 terminal은 매우 제한된 OCMI jurisdiction에서 COI reduced-manning endorsement를 요청하는 C terminal이다.

### 3.16 선박 문서등록 삭제서 요청 (C)

- **Exact mapping:** `commercial_vessel_safety_compliance.vessel_decommission_record` → `commercial_vessel_safety_compliance.vessel_documentation_deletion_letter_request`
- **이름:** 선박 문서등록 삭제서 요청 / Vessel-documentation deletion-letter request
- **목표:** NVDC에 이 문서등록 선박의 Certificate of Documentation 삭제서를 요청하는 곳으로 가 줘 / Take me to request an NVDC deletion letter for this documented vessel's Certificate of Documentation
- **Role / asset:** documented-vessel owner or authorized customer and NVDC / vessel official number, Certificate of Documentation and deletion-letter request.
- **State / transition:** `actively_documented -> deletion_letter_requested -> NVDC_processing -> deletion_letter_available_or_documentation_deletion_evidenced`.
- **Jurisdiction guard:** 미국 NVDC에 documented된 vessel과 Certificate of Documentation deletion 목적이어야 한다. physical decommissioning, lay-up, scrapping, flag deletion, COI surrender 또는 residual-risk closeout을 뜻하지 않는다.
- **Accepted official source:** [USCG NVDC — Expanded Online Ordering](https://www.dco.uscg.mil/Our-Organization/Deputy-for-Operations-Policy-and-Capabilities-DCO-D/National-Vessel-Documentation-Center/NationalVesselDocumentationCenter-OtherLinks/)
- **Nearest existing-domain non-equivalence:** `return_to_service_request`는 laid-up/COI-surrendered vessel의 inspection과 recertification 뒤 service 복귀를 요청한다. 새 terminal은 NVDC documentation registry에서 deletion letter를 요청하는 반대 방향의 별도 registry transition이다.

## 4. 분리했지만 이번 240개 terminal 집합에 추가하지 않는 전이

아래 전이는 필요성이 없다는 뜻이 아니라, 현재 공식 근거 또는 count-neutral 범위상 이번 replacement로 materialize하지 않는다는 뜻이다.

| 원 복합 항목 | 비채택 전이 | 처리 |
|---|---|---|
| Lower-700-MHz buildout | construction notification final filing | 기존 `construction_notification_file`에 유지 |
| Part-450 mission | separate per-mission authorization issuance | 공식 체계와 불일치하므로 제거; license scope 밖이면 `license_modification_request` |
| Leak test | above-threshold leaking-source regulator report | future `report_leaking_source`; program별 authority 확보 전 비활성 |
| Radioactive shipment | package-compliance check | nonterminal precondition으로 유지 |
| Radioactive shipment | internal shipment-release authorization | 조직 내부 통제 근거가 별도 확보될 때만 future terminal |
| FFL closeout | license surrender/termination | 현재 closure source가 직접 입증하지 않아 비활성 |
| FFL closeout | completed records transfer | 기존 `records_disposition_transfer`가 소유 |
| Vessel decommission | physical lay-up, scrapping, COI surrender, flag deletion | 각각의 authority가 확보될 때 별도 terminal 후보 |

## 5. 중복·충돌 자체 감사

### 5.1 감사 방법

- ID는 exact string으로 비교했다.
- bilingual name과 bilingual representative goal은 Unicode NFKC, case-fold, 공백·문장부호·기호 제거 후 비교했다.
- 비교 집합은 replacement 16개 내부, old 16개를 제외한 V16 proposal 224개, canonical catalog의 2,866개 function ID/name과 2,660개 intent pattern, equivalence file의 10개 class/20개 member ID다.
- 의미 동등성은 각 상세 항목의 role/asset/state/jurisdiction guard와 “Nearest existing-domain non-equivalence”를 대조했다. suffix가 비슷하다는 사실만으로 동등하다고 판정하지 않았다.

### 5.2 정확한 결과

| 감사 항목 | 결과 |
|---|---:|
| replacement 내부 exact ID 중복 | **0** |
| replacement 내부 normalized KO/EN name 중복 | **0** |
| replacement 내부 normalized KO/EN goal 중복 | **0** |
| 남은 V16 proposal 224개와 exact ID 충돌 | **0** |
| 남은 V16 proposal 224개와 normalized name 충돌 | **0** |
| 남은 V16 proposal 224개와 normalized goal 충돌 | **0** |
| canonical 2,866개 function과 exact ID 충돌 | **0** |
| canonical function name과 normalized name 충돌 | **0** |
| canonical 2,660개 intent pattern과 normalized goal 충돌 | **0** |
| equivalence 20개 member ID와 exact ID 충돌 | **0** |

### 5.3 source 및 합계 감사

- replacement가 인용하는 공식 HTTPS URL은 **21개**, 정규화 후 고유 URL도 **21개**, 중복은 **0개**다.
- 16개 모두 accepted gap-closure source가 직접 지지하는 더 좁은 role/asset/state/transition만 사용한다.
- 공식 source가 입증하지 않은 literal product UI, 공통 버튼, API, 승인 큐 또는 자동 실행 기능은 **0개**다.
- count-neutral 교체 뒤에도 각 도메인은 **hub 1 + terminal 20**, 전체는 **12 hubs + 240 terminals**, class 합계는 **S84/C156**이다.

## 6. Materialization gate

다음 단계의 V16 source data/materializer는 old 16개를 먼저 제거한 뒤 이 문서의 replacement 16개만 넣어야 한다. 각 replacement는 아래 조건을 모두 통과해야 한다.

1. exact ID·bilingual name·bilingual goal이 이 문서와 byte-level로 일치한다.
2. class는 이 문서의 S/C를 보존한다.
3. role/asset/state/jurisdiction guard 중 하나라도 누락되면 materialization을 실패시킨다.
4. 제품 UI 존재를 나타내는 필드는 source가 명시한 channel 이상으로 확장하지 않는다.
5. split 결과의 비채택 전이를 replacement alias나 broad goal pattern으로 다시 합치지 않는다.
6. canonical count, quality policy, equivalence projection 및 deterministic materialization을 별도 gate에서 재검증한다.

이 refinement는 “부분 근거가 있는 넓은 terminal” 16개를 억지로 유지하지 않는다. 대신 사용자의 목적과 공식 절차가 정확히 일치할 때만 활성화되는 좁은 terminal 16개로 교체하여, V16의 수량과 S/C 구성은 보존하면서 잘못된 승인·인증·종결·UI 추론을 제거한다.
