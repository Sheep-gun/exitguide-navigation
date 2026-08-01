# Navigation ontology coverage gap audit — V16 draft

Audit date: 2026-07-30
Baseline: canonical V15 catalog `15.0.0`, **179 domains, 2,866 physical functions, 2,660 physical terminal functions/intents, and 2,658 unique physical default-terminal IDs**. The current function-equivalence overlay yields **2,856 logical functions, 2,650 logical intents, and 2,648 unique logical default-terminal destinations**.

## Audit scope and input boundary

This is a gap-audit draft only. The audit inspected only (a) the current canonical catalog's 179 domain names and function names and (b) `docs/NAVIGATION_COVERAGE_GAPS_V15.md`. It did **not** inspect any independent fixture, answer key, evaluation item, failure report, generator alias, or hidden collision probe. It does not modify the catalog, source modules, tests, fixtures, or canonical data.

The 12 candidates below were selected for materially different professional authorities, governed assets, lifecycle states, and real-world consequences. Each domain is specified as one hub plus exactly 20 terminals: seven sensitive read-only terminals (`S`) and thirteen consequential terminals (`C`).

## Decision and exact projection

| Priority | Proposed domain ID | Terminals | Functions with hub | Intents | `S` | `C` |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `controlled_substance_compliance_ops` | 20 | 21 | 20 | 7 | 13 |
| 2 | `medical_device_regulatory_ops` | 20 | 21 | 20 | 7 | 13 |
| 3 | `occupational_safety_case_ops` | 20 | 21 | 20 | 7 | 13 |
| 4 | `food_manufacturing_recall_ops` | 20 | 21 | 20 | 7 | 13 |
| 5 | `government_contract_administration` | 20 | 21 | 20 | 7 | 13 |
| 6 | `public_company_sec_reporting_ops` | 20 | 21 | 20 | 7 | 13 |
| 7 | `wireless_spectrum_license_ops` | 20 | 21 | 20 | 7 | 13 |
| 8 | `commercial_space_launch_licensing_ops` | 20 | 21 | 20 | 7 | 13 |
| 9 | `radioactive_materials_license_ops` | 20 | 21 | 20 | 7 | 13 |
| 10 | `hazardous_materials_transport_compliance` | 20 | 21 | 20 | 7 | 13 |
| 11 | `firearms_dealer_compliance_ops` | 20 | 21 | 20 | 7 | 13 |
| 12 | `commercial_vessel_safety_compliance` | 20 | 21 | 20 | 7 | 13 |
| **Total** | **12 domains** | **240** | **252** | **240** | **84** | **156** |

Exact count arithmetic if accepted unchanged:

| View | V15 baseline | V16 append | Projected V16 |
|---|---:|---:|---:|
| Domains | 179 | +12 | **191** |
| Physical functions | 2,866 | +252 | **3,118** |
| Physical terminal functions | 2,660 | +240 | **2,900** |
| Physical intents | 2,660 | +240 | **2,900** |
| Unique physical default-terminal IDs | 2,658 | +240 | **2,898** |
| Logical functions | 2,856 | +252 | **3,108** |
| Logical intents | 2,650 | +240 | **2,890** |
| Unique logical default-terminal destinations | 2,648 | +240 | **2,888** |

These projections require all 240 terminals to remain new destinations. Discovery of a true-equivalent existing destination requires removal or redesign before implementation, not a silent equivalence collapse.

## Common ID, identity, and safety contract

- Hub ID: `<domain>.hub`; terminal ID: `<domain>.<terminal_key>`; prospective intent ID: `v16_<domain>_<terminal_key>`.
- A route needs at least two positive discriminators among authorized role, governed asset, jurisdiction/facility, and lifecycle state. Every `C` route needs role, asset, and current state.
- Each hub is low risk, read-only, `safe_navigation`, and stops on the hub screen.
- Every terminal is high risk, `never_auto`, `before_action`, and `user_owned_final_press=true`. `S` is sensitive read-only; `C` changes, submits, certifies, authorizes, issues, or closes regulated state.
- Wrong role, asset, jurisdiction, or state; stale/offline data; a legal, safety, quality, or security hold; missing approval; or a disabled control causes abstention or a stop at the hub.
- Names below describe conceptual destinations, never a package, provider resource ID, coordinate, screenshot label, or fixed click path.

## 1. Controlled-substance compliance operations (`controlled_substance_compliance_ops`)

Hub: `controlled_substance_compliance_ops.hub` — 통제약물 규정준수 운영 / Controlled-substance compliance operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `controlled_substance_compliance_ops.dea_registration_profile` | DEA 등록 프로필 / DEA registration profile | 이 사업장의 DEA 등록 권한과 유효기간을 보여 줘 / Show the DEA registration authority and expiration for this location |
| S | `controlled_substance_compliance_ops.controlled_inventory_snapshot` | 통제약물 재고 현황 / Controlled-substance inventory snapshot | 지정 보관소의 스케줄별 장부 재고를 보여 줘 / Show book inventory by schedule for the named storage location |
| S | `controlled_substance_compliance_ops.order_form_status` | 통제약물 주문서 상태 / Controlled-substance order-form status | 이 Schedule II 주문서의 발행·수령 상태를 확인해 줘 / Show issue and receipt status for this Schedule II order form |
| S | `controlled_substance_compliance_ops.suspicious_order_monitoring_queue` | 의심 주문 모니터링 대기열 / Suspicious-order monitoring queue | 검토가 필요한 통제약물 주문을 보여 줘 / Show controlled-substance orders awaiting suspicious-order review |
| S | `controlled_substance_compliance_ops.theft_loss_case_status` | 도난·분실 사건 상태 / Theft-and-loss case status | 이 통제약물 분실 사건의 신고 진행 상태를 보여 줘 / Show reporting progress for this controlled-substance loss case |
| S | `controlled_substance_compliance_ops.destruction_record_status` | 폐기 기록 상태 / Destruction-record status | 지정 약물 폐기 요청과 완료 기록을 확인해 줘 / Show request and completion status for this drug destruction record |
| S | `controlled_substance_compliance_ops.reporting_calendar` | 규제 보고 일정 / Regulatory reporting calendar | 이 등록자의 재고·거래 보고 마감일을 보여 줘 / Show inventory and transaction reporting deadlines for this registrant |
| C | `controlled_substance_compliance_ops.dea_registration_application_submit` | DEA 신규 등록 신청 제출 / DEA registration-application submission | 책임자가 검토한 이 사업장 DEA 신규 등록 신청을 제출하는 곳으로 가 줘 / Take me to submit the responsible official's reviewed DEA application for this location |
| C | `controlled_substance_compliance_ops.registration_renewal_submit` | DEA 등록 갱신 제출 / DEA registration-renewal submission | 만료 예정 DEA 등록의 갱신 신청을 제출하는 화면을 열어 줘 / Open submission for the expiring DEA registration renewal |
| C | `controlled_substance_compliance_ops.power_of_attorney_record` | 주문 위임장 기록 / Ordering power-of-attorney record | 이 등록자의 Schedule II 주문 서명 위임을 기록하는 곳으로 가 줘 / Take me to record ordering power of attorney for this registrant |
| C | `controlled_substance_compliance_ops.schedule_ii_order_create` | Schedule II 주문 생성 / Schedule II order creation | 승인된 공급자에게 보낼 Schedule II 주문을 만드는 화면을 열어 줘 / Open the screen to create a Schedule II order for the approved supplier |
| C | `controlled_substance_compliance_ops.order_form_receive_close` | 주문 수령·종결 기록 / Order receipt and closure | 실제 수령 수량을 기록하고 이 주문서를 종결하는 곳으로 가 줘 / Take me to record quantities received and close this order form |
| C | `controlled_substance_compliance_ops.biennial_inventory_certify` | 2년 주기 재고 인증 / Biennial-inventory certification | 책임자가 확인한 통제약물 실사 재고를 인증하는 화면을 열어 줘 / Open certification for the responsible official's verified biennial inventory |
| C | `controlled_substance_compliance_ops.controlled_substance_transfer_record` | 통제약물 이전 기록 / Controlled-substance transfer record | 두 등록자 사이의 이 약물 이전을 장부에 기록하는 곳으로 가 줘 / Take me to record this controlled-substance transfer between registrants |
| C | `controlled_substance_compliance_ops.suspicious_order_report_submit` | 의심 주문 보고 제출 / Suspicious-order report submission | 검토 확정된 의심 주문 보고를 제출하는 화면을 열어 줘 / Open submission for the confirmed suspicious-order report |
| C | `controlled_substance_compliance_ops.theft_loss_initial_report` | 도난·중대 분실 최초 보고 / Initial theft or significant-loss report | 발견된 통제약물 중대 분실을 즉시 최초 보고하는 곳으로 가 줘 / Take me to make the initial report of the discovered significant loss |
| C | `controlled_substance_compliance_ops.theft_loss_form_submit` | 도난·분실 최종 서식 제출 / Theft-and-loss form submission | 조사 수량을 반영한 도난·분실 최종 서식을 제출해 줘 / Take me to submit the final theft-and-loss form with investigated quantities |
| C | `controlled_substance_compliance_ops.destruction_request_record` | 통제약물 폐기 요청 기록 / Destruction-request record | 승인 대상 통제약물 폐기 요청을 기록하는 화면을 열어 줘 / Open the screen to record a controlled-substance destruction request |
| C | `controlled_substance_compliance_ops.reverse_distributor_transfer` | 역유통업자 이전 / Reverse-distributor transfer | 폐기 대상 약물을 승인된 역유통업자에게 이전 기록하는 곳으로 가 줘 / Take me to record transfer of destruction stock to the authorized reverse distributor |
| C | `controlled_substance_compliance_ops.arcos_transaction_report_submit` | ARCOS 거래 보고 제출 / ARCOS transaction-report submission | 검증된 해당 기간 통제약물 거래 보고를 제출하는 화면을 열어 줘 / Open submission for the validated controlled-substance transaction report |

Roles/assets/states: DEA registrant responsible official, compliance officer, inventory custodian, ordering signer, suspicious-order reviewer, and loss reporter; DEA registration, scheduled-drug inventory, order form, purchaser/supplier, theft/loss, destruction, and transaction report; `active/expired/pending`, `open/received/closed`, `balanced/discrepant`, `normal/suspicious/reported`, `discovered/preliminary/final`, and `pending/accepted/rejected`.

Boundary and collision guard: this domain owns registrant-level DEA authority, controlled inventory, ordering, loss, destruction, and transaction reporting. `pharmacy_dispensing_ops` owns patient prescription, fill, and handoff; generic inventory, ordinary purchasing, and `financial_crime_compliance_ops` are not substitutes. A bare “order,” “inventory,” “loss,” or “report” is insufficient without a DEA registrant, scheduled substance, and lifecycle state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [21 CFR Part 1301](https://www.ecfr.gov/current/title-21/chapter-II/part-1301)
2. [21 CFR Part 1304](https://www.ecfr.gov/current/title-21/chapter-II/part-1304)
3. [21 CFR Part 1305](https://www.ecfr.gov/current/title-21/chapter-II/part-1305)
4. [DEA registration](https://www.deadiversion.usdoj.gov/drugreg/registration.html)
5. [DEA reporting](https://www.deadiversion.usdoj.gov/reporting.html)
6. [DEA electronic controlled-substance ordering](https://www.deaecom.gov/)
7. [DEA ARCOS](https://www.deadiversion.usdoj.gov/arcos/)

## 2. Medical-device regulatory operations (`medical_device_regulatory_ops`)

Hub: `medical_device_regulatory_ops.hub` — 의료기기 규제 운영 / Medical-device regulatory operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `medical_device_regulatory_ops.establishment_registration_status` | 의료기기 시설 등록 상태 / Device-establishment registration status | 이 제조 시설의 등록 유효 상태를 보여 줘 / Show the registration status of this device establishment |
| S | `medical_device_regulatory_ops.device_listing_status` | 의료기기 목록 상태 / Device-listing status | 이 시설에 연결된 해당 기기 목록 상태를 확인해 줘 / Show listing status for this device at the named establishment |
| S | `medical_device_regulatory_ops.submission_review_status` | 시판 전 제출 심사 상태 / Premarket-submission review status | 이 의료기기 제출 건의 접수와 심사 단계를 보여 줘 / Show receipt and review stage for this device submission |
| S | `medical_device_regulatory_ops.udi_gudid_record_status` | UDI·GUDID 레코드 상태 / UDI and GUDID record status | 이 기기 식별 레코드의 공개 상태를 확인해 줘 / Show publication status for this device-identifier record |
| S | `medical_device_regulatory_ops.adverse_event_signal_queue` | 이상사례 신호 대기열 / Adverse-event signal queue | 보고 가능성 검토가 필요한 기기 이상사례를 보여 줘 / Show device adverse events awaiting reportability review |
| S | `medical_device_regulatory_ops.correction_removal_status` | 시정·회수 보고 상태 / Correction-and-removal status | 이 현장 시정조치의 규제 보고 상태를 보여 줘 / Show regulatory reporting status for this field correction |
| S | `medical_device_regulatory_ops.recall_classification_status` | 의료기기 리콜 분류 상태 / Device-recall classification status | 이 리콜의 분류와 진행 상태를 확인해 줘 / Show classification and progress for this device recall |
| C | `medical_device_regulatory_ops.establishment_registration_submit` | 시설 등록 제출 / Establishment-registration submission | 소유자가 확인한 의료기기 시설 등록을 제출하는 곳으로 가 줘 / Take me to submit the owner's verified device-establishment registration |
| C | `medical_device_regulatory_ops.device_listing_create_update` | 기기 목록 생성·갱신 / Device-listing creation or update | 이 시설의 기기 목록을 생성하거나 갱신하는 화면을 열어 줘 / Open the screen to create or update this establishment's device listing |
| C | `medical_device_regulatory_ops.premarket_submission_create` | 시판 전 제출 생성 / Premarket-submission creation | 해당 기기의 시판 전 규제 제출 초안을 만드는 곳으로 가 줘 / Take me to create the premarket submission draft for this device |
| C | `medical_device_regulatory_ops.premarket_submission_submit` | 시판 전 제출 / Premarket-submission submission | 서명권자가 승인한 의료기기 시판 전 제출을 전송하는 화면을 열어 줘 / Open submission for the signatory-approved device premarket package |
| C | `medical_device_regulatory_ops.additional_information_response` | 추가정보 응답 제출 / Additional-information response | 이 심사 요청에 대한 검증된 추가정보 응답을 제출하는 곳으로 가 줘 / Take me to submit the validated response to this additional-information request |
| C | `medical_device_regulatory_ops.udi_device_record_publish` | UDI 기기 레코드 공개 / UDI device-record publication | 검증된 기기 식별 레코드를 GUDID에 공개하는 화면을 열어 줘 / Open publication for the validated device-identifier record in GUDID |
| C | `medical_device_regulatory_ops.medical_device_report_submit` | 의료기기 이상사례 보고 제출 / Medical-device report submission | 보고 가능으로 판정된 이 이상사례 보고를 제출하는 곳으로 가 줘 / Take me to submit this reportable device adverse-event report |
| C | `medical_device_regulatory_ops.correction_removal_report_submit` | 시정·회수 보고 제출 / Correction-and-removal report submission | 이 현장 시정·회수 조치의 규제 보고를 제출하는 화면을 열어 줘 / Open submission for the regulatory correction-and-removal report |
| C | `medical_device_regulatory_ops.recall_strategy_submit` | 리콜 전략 제출 / Recall-strategy submission | 승인된 의료기기 리콜 범위와 전략을 제출하는 곳으로 가 줘 / Take me to submit the approved scope and strategy for this device recall |
| C | `medical_device_regulatory_ops.recall_status_report_submit` | 리콜 상태 보고 제출 / Recall-status report submission | 이 리콜의 최신 회수·회신 수치를 보고하는 화면을 열어 줘 / Open submission for the latest recovery and response counts for this recall |
| C | `medical_device_regulatory_ops.recall_communication_issue` | 리콜 통지 발행 / Recall-communication issuance | 승인된 고객·사용자 리콜 통지를 발행하는 곳으로 가 줘 / Take me to issue the approved customer and user recall communication |
| C | `medical_device_regulatory_ops.registration_listing_deactivate` | 등록·목록 비활성화 / Registration or listing deactivation | 운영 중단이 승인된 시설 또는 기기 목록을 비활성화하는 화면을 열어 줘 / Open deactivation for the approved establishment or device listing |
| C | `medical_device_regulatory_ops.device_shortage_notification_submit` | 의료기기 부족 통지 제출 / Device-shortage notification submission | 확인된 생산 중단 또는 부족 통지를 제출하는 곳으로 가 줘 / Take me to submit the confirmed device interruption or shortage notice |

Roles/assets/states: establishment owner/operator, official correspondent, regulatory-affairs specialist, submission manager, UDI coordinator, MDR reporter, and recall coordinator; establishment, listed device, premarket submission, UDI-DI, adverse event, correction/removal, recall, and shortage notice; `registered/inactive`, `draft/submitted/in-review/additional-information-requested/cleared/approved/withdrawn`, `published/unpublished`, `reportable/submitted`, and `initiated/classified/effective/terminated`.

Boundary and collision guard: this domain owns market-entry and postmarket regulatory records for medical devices. `manufacturing_quality_ops` owns internal production quality, batch release, and CAPA; `clinical_trials_operations` owns study conduct; `public_health_case_management` owns population-health cases. “Quality,” “incident,” “submission,” and “recall” require a regulated device, establishment/submission identifier, responsible role, and regulatory state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [FDA device registration and listing](https://www.fda.gov/medical-devices/how-study-and-market-your-device/device-registration-and-listing)
2. [FDA how to register and list](https://www.fda.gov/medical-devices/device-registration-and-listing/how-register-and-list)
3. [FDA eSTAR program](https://www.fda.gov/medical-devices/how-study-and-market-your-device/estar-program)
4. [21 CFR Part 803](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-803)
5. [21 CFR Part 806](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-H/part-806)
6. [FDA GUDID](https://www.fda.gov/medical-devices/unique-device-identification-system-udi-system/global-unique-device-identification-database-gudid)
7. [FDA recalls, corrections, and removals for devices](https://www.fda.gov/medical-devices/postmarket-requirements-devices/recalls-corrections-and-removals-devices)

## 3. Occupational-safety case operations (`occupational_safety_case_ops`)

Hub: `occupational_safety_case_ops.hub` — 산업안전 사건 운영 / Occupational-safety case operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `occupational_safety_case_ops.establishment_profile` | 산업안전 사업장 프로필 / Occupational-safety establishment profile | 이 사업장의 관할·고용·기록 의무 프로필을 보여 줘 / Show jurisdiction, employment, and recordkeeping profile for this establishment |
| S | `occupational_safety_case_ops.injury_illness_log_review` | 재해·질병 기록부 검토 / Injury-and-illness log review | 지정 연도의 사업장 재해·질병 기록부를 열어 줘 / Open this establishment's injury-and-illness log for the specified year |
| S | `occupational_safety_case_ops.incident_reporting_queue` | 중대사고 보고 대기열 / Severe-incident reporting queue | 즉시 보고 여부를 검토할 사고를 보여 줘 / Show incidents awaiting immediate-reporting review |
| S | `occupational_safety_case_ops.inspection_case_status` | 산업안전 점검 사건 상태 / Safety-inspection case status | 이 사업장 점검 사건의 현재 단계를 보여 줘 / Show the current stage of this establishment inspection case |
| S | `occupational_safety_case_ops.citation_penalty_status` | 위반통지·벌금 상태 / Citation-and-penalty status | 이 점검의 위반통지와 벌금 상태를 확인해 줘 / Show citation and penalty status for this inspection |
| S | `occupational_safety_case_ops.abatement_due_status` | 시정조치 기한 상태 / Abatement-due status | 미완료 위반 항목별 시정 기한을 보여 줘 / Show abatement deadlines for each open citation item |
| S | `occupational_safety_case_ops.safety_program_audit_status` | 안전 프로그램 감사 상태 / Safety-program audit status | 이 사업장의 안전 프로그램 감사 결과를 보여 줘 / Show audit status for this establishment's safety program |
| C | `occupational_safety_case_ops.injury_illness_case_record` | 재해·질병 사례 기록 / Injury-and-illness case record | 기록 대상 근로자 재해 사례를 사업장 기록부에 추가하는 곳으로 가 줘 / Take me to add this recordable worker case to the establishment log |
| C | `occupational_safety_case_ops.annual_summary_certify` | 연간 요약 인증 / Annual-summary certification | 임원이 검토한 연간 재해·질병 요약을 인증하는 화면을 열어 줘 / Open certification for the executive-reviewed annual injury summary |
| C | `occupational_safety_case_ops.electronic_injury_data_submit` | 전자 재해자료 제출 / Electronic injury-data submission | 검증된 해당 연도 사업장 재해자료를 전자 제출하는 곳으로 가 줘 / Take me to submit the validated annual establishment injury data |
| C | `occupational_safety_case_ops.severe_injury_report_submit` | 중대 재해 즉시 보고 / Severe-injury report submission | 관할이 확인된 중대 재해를 즉시 보고하는 화면을 열어 줘 / Open immediate reporting for this jurisdiction-confirmed severe injury |
| C | `occupational_safety_case_ops.hazard_complaint_intake` | 유해요인 신고 접수 / Hazard-complaint intake | 이 사업장의 특정 유해요인 신고를 공식 접수하는 곳으로 가 줘 / Take me to formally intake the specific hazard complaint for this establishment |
| C | `occupational_safety_case_ops.inspection_open_assign` | 점검 개시·배정 / Inspection opening and assignment | 관할 승인된 점검 사건을 열고 조사관에게 배정하는 화면을 열어 줘 / Open and assign the jurisdiction-approved inspection case |
| C | `occupational_safety_case_ops.inspection_finding_record` | 점검 소견 기록 / Inspection-finding record | 증거가 연결된 점검 소견을 해당 사건에 기록하는 곳으로 가 줘 / Take me to record the evidence-linked finding in this inspection case |
| C | `occupational_safety_case_ops.citation_issue` | 위반통지 발행 / Citation issuance | 지역 책임자가 승인한 위반 항목과 벌금을 발행하는 화면을 열어 줘 / Open issuance for the area director-approved citation items and penalties |
| C | `occupational_safety_case_ops.contest_notice_record` | 이의제기 통지 기록 / Contest-notice record | 기한 내 접수된 사업주의 이의제기 통지를 사건에 기록해 줘 / Take me to record the employer's timely contest notice in this case |
| C | `occupational_safety_case_ops.abatement_plan_submit` | 시정계획 제출 / Abatement-plan submission | 위반 항목별 승인된 시정계획을 제출하는 곳으로 가 줘 / Take me to submit the approved abatement plan for each citation item |
| C | `occupational_safety_case_ops.abatement_evidence_certify` | 시정 증거 인증 / Abatement-evidence certification | 완료된 시정조치의 증거를 권한자가 인증하는 화면을 열어 줘 / Open authorized certification of evidence for the completed abatement |
| C | `occupational_safety_case_ops.informal_settlement_approve` | 비공식 합의 승인 / Informal-settlement approval | 양측이 검토한 이 점검 사건의 비공식 합의를 승인하는 곳으로 가 줘 / Take me to approve the parties' reviewed informal settlement for this case |
| C | `occupational_safety_case_ops.case_close` | 산업안전 사건 종결 / Occupational-safety case closure | 최종 위반과 시정 상태가 확인된 사건을 종결하는 화면을 열어 줘 / Open closure for the case with final citations and verified abatement |

Roles/assets/states: employer representative, recordkeeper, safety officer, compliance officer, authorized safety inspector, area director, and abatement coordinator; establishment, injury case/log/summary, severe incident, inspection, citation item, abatement evidence, contest, and settlement; `recordable/nonrecordable`, `open/submitted`, `inspection-open/closed`, `cited/contested/final`, and `abatement-pending/verified`.

Boundary and collision guard: this is cross-industry employer recordkeeping and regulator case administration. Construction, mining, food-establishment inspection, and manufacturing-quality domains keep their industry assets and workflows; this domain requires an occupational-safety establishment, statutory case or record, authorized employer/regulator role, and inspection or abatement state. A generic “incident,” “audit,” “finding,” or “close case” must abstain.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [29 CFR Part 1904](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1904)
2. [OSHA Injury Tracking Application](https://www.osha.gov/injuryreporting/ita)
3. [OSHA report a fatality or severe injury](https://www.osha.gov/report)
4. [29 CFR Part 1903](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1903)
5. [OSHA Field Operations Manual](https://www.osha.gov/enforcement/directives/cpl-02-00-164)
6. [29 CFR 1903.19](https://www.osha.gov/laws-regs/regulations/standardnumber/1903/1903.19)

## 4. Food-manufacturing recall operations (`food_manufacturing_recall_ops`)

Hub: `food_manufacturing_recall_ops.hub` — 식품 제조·리콜 운영 / Food-manufacturing recall operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `food_manufacturing_recall_ops.food_facility_registration_status` | 식품 시설 등록 상태 / Food-facility registration status | 이 제조 시설의 식품 등록 유효 상태를 보여 줘 / Show the food-registration status of this manufacturing facility |
| S | `food_manufacturing_recall_ops.preventive_controls_plan_status` | 예방관리 계획 상태 / Preventive-controls plan status | 이 제품군의 승인된 식품안전 계획 상태를 보여 줘 / Show approved food-safety-plan status for this product family |
| S | `food_manufacturing_recall_ops.supply_chain_traceability_view` | 공급망 추적성 보기 / Supply-chain traceability view | 해당 로트의 직전 공급자와 다음 수령자를 보여 줘 / Show prior suppliers and next recipients for this lot |
| S | `food_manufacturing_recall_ops.lot_distribution_status` | 로트 유통 상태 / Lot-distribution status | 이 로트가 출하된 시설과 수량을 보여 줘 / Show destinations and quantities shipped for this lot |
| S | `food_manufacturing_recall_ops.reportable_food_case_status` | 보고대상 식품 사건 상태 / Reportable-food case status | 이 식품 위해 사건의 보고 진행 상태를 확인해 줘 / Show reporting progress for this reportable-food case |
| S | `food_manufacturing_recall_ops.recall_case_status` | 식품 리콜 사건 상태 / Food-recall case status | 이 리콜의 범위·분류·회수 상태를 보여 줘 / Show scope, classification, and recovery status for this recall |
| S | `food_manufacturing_recall_ops.product_complaint_signal_queue` | 제품 불만 신호 대기열 / Product-complaint signal queue | 위해 평가가 필요한 식품 불만 신호를 보여 줘 / Show food complaints awaiting hazard evaluation |
| C | `food_manufacturing_recall_ops.facility_registration_submit` | 식품 시설 등록 제출 / Food-facility registration submission | 소유자가 확인한 이 제조 시설 등록을 제출하는 곳으로 가 줘 / Take me to submit the owner's verified registration for this food facility |
| C | `food_manufacturing_recall_ops.food_safety_plan_approve` | 식품안전 계획 승인 / Food-safety-plan approval | 자격자가 검토한 이 제품군의 식품안전 계획을 승인하는 화면을 열어 줘 / Open approval for the qualified individual's reviewed food-safety plan |
| C | `food_manufacturing_recall_ops.hazard_analysis_record` | 위해요소 분석 기록 / Hazard-analysis record | 이 공정·제품의 확인된 위해요소 분석을 기록하는 곳으로 가 줘 / Take me to record the identified hazard analysis for this process and product |
| C | `food_manufacturing_recall_ops.preventive_control_verify` | 예방관리 검증 / Preventive-control verification | 완료된 예방관리의 모니터링·검증 결과를 인증하는 화면을 열어 줘 / Open certification of monitoring and verification for this preventive control |
| C | `food_manufacturing_recall_ops.traceability_event_record` | 추적성 사건 기록 / Traceability-event record | 해당 로트의 수령·변환·출하 추적 사건을 기록하는 곳으로 가 줘 / Take me to record the receiving, transformation, or shipping event for this lot |
| C | `food_manufacturing_recall_ops.reportable_food_report_submit` | 보고대상 식품 보고 제출 / Reportable-food report submission | 책임자가 확정한 보고대상 식품 사건을 제출하는 화면을 열어 줘 / Open submission for the responsible party's confirmed reportable-food case |
| C | `food_manufacturing_recall_ops.recall_initiate` | 식품 리콜 개시 / Food-recall initiation | 승인된 제품·로트 범위로 자발적 리콜을 개시하는 곳으로 가 줘 / Take me to initiate the voluntary recall for the approved product and lot scope |
| C | `food_manufacturing_recall_ops.recall_depth_scope_approve` | 리콜 깊이·범위 승인 / Recall-depth and scope approval | 소비자·소매·도매 수준의 리콜 깊이와 로트 범위를 승인해 줘 / Take me to approve recall depth and lot scope for this case |
| C | `food_manufacturing_recall_ops.customer_notification_release` | 고객 리콜 통지 발송 / Customer-recall notification release | 승인된 유통업체·고객 리콜 통지를 발송하는 화면을 열어 줘 / Open release for the approved distributor and customer recall notice |
| C | `food_manufacturing_recall_ops.distribution_stop_issue` | 유통중지 지시 발행 / Distribution-stop issuance | 해당 로트의 출하·유통 중지 지시를 발행하는 곳으로 가 줘 / Take me to issue the shipping and distribution stop for this lot |
| C | `food_manufacturing_recall_ops.product_reconciliation_record` | 회수제품 대사 기록 / Recalled-product reconciliation | 출하·회수·폐기 수량을 이 리콜 사건에 대사 기록해 줘 / Take me to reconcile shipped, recovered, and disposed quantities for this recall |
| C | `food_manufacturing_recall_ops.effectiveness_check_certify` | 리콜 효과성 점검 인증 / Recall-effectiveness check certification | 완료된 수령자 확인 결과와 리콜 효과성을 인증하는 화면을 열어 줘 / Open certification of completed consignee checks and recall effectiveness |
| C | `food_manufacturing_recall_ops.recall_termination_request` | 리콜 종료 요청 / Recall-termination request | 회수·대사·효과성 조건을 충족한 리콜 종료를 요청하는 곳으로 가 줘 / Take me to request termination after recovery, reconciliation, and effectiveness criteria are met |

Roles/assets/states: facility owner, preventive-controls qualified individual, recall coordinator, traceability lead, reportable-food responsible party, quality lead, and regulator liaison; registered facility, food-safety plan, hazard/control, lot and trace event, reportable-food report, recall, notification, and effectiveness check; `active/lapsed`, `hazard-identified/controlled`, `produced/shipped/held/reconciled`, `draft/submitted/amended`, and `initiated/ongoing/effective/terminated`.

Boundary and collision guard: this owns manufacturer-level preventive controls, traceability, reportable-food, and recall execution. `food_establishment_inspection` owns regulator inspection/enforcement of retail or food establishments; `manufacturing_quality_ops` owns generic internal quality; freight/customs owns movement and entry; public-health domains own population case response. “Lot,” “hold,” “complaint,” or “recall” requires a food facility/product, responsible party, distribution chain, and recall state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [21 CFR Part 1 Subpart H](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-1/subpart-H)
2. [21 CFR Part 117](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-117)
3. [FDA food traceability rule](https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods)
4. [FDA Reportable Food Registry](https://www.fda.gov/food/compliance-enforcement-food/reportable-food-registry-industry)
5. [21 CFR Part 7 Subpart C](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-7/subpart-C)
6. [FDA industry guidance for recalls](https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/industry-guidance-recalls)

## 5. Government contract administration (`government_contract_administration`)

Hub: `government_contract_administration.hub` — 정부 계약 관리 / Government contract administration

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `government_contract_administration.solicitation_workspace` | 정부 입찰공고 작업공간 / Government-solicitation workspace | 이 조달 건의 공고·수정·마감 상태를 보여 줘 / Show solicitation, amendment, and closing status for this procurement |
| S | `government_contract_administration.offer_evaluation_status` | 제안서 평가 상태 / Offer-evaluation status | 잠긴 제안서별 기술·가격 평가 진행 상태를 보여 줘 / Show technical and price evaluation progress for each locked offer |
| S | `government_contract_administration.responsibility_clearance_status` | 계약이행능력 확인 상태 / Responsibility-clearance status | 선정 예정 업체의 책임성 확인 결과를 보여 줘 / Show responsibility-clearance results for the prospective awardee |
| S | `government_contract_administration.contract_funding_status` | 계약 자금 상태 / Contract-funding status | 이 계약의 배정·의무부담·잔액 상태를 보여 줘 / Show allocation, obligation, and balance status for this contract |
| S | `government_contract_administration.performance_schedule_status` | 계약 이행 일정 상태 / Contract-performance schedule status | 이 계약의 마일스톤과 지연 상태를 보여 줘 / Show milestones and delay status for this contract |
| S | `government_contract_administration.modification_history` | 계약 변경 이력 / Contract-modification history | 이 계약에 서명된 변경과 권한 근거를 보여 줘 / Show signed modifications and authority basis for this contract |
| S | `government_contract_administration.closeout_readiness_status` | 계약 종결 준비 상태 / Contract-closeout readiness status | 미정산 자산·청구·보증 조건을 보여 줘 / Show unresolved property, invoice, and warranty closeout conditions |
| C | `government_contract_administration.solicitation_issue` | 입찰공고 발행 / Solicitation issuance | 계약담당관이 승인한 입찰공고를 발행하는 화면을 열어 줘 / Open issuance for the contracting officer-approved solicitation |
| C | `government_contract_administration.amendment_issue` | 입찰공고 수정 발행 / Solicitation-amendment issuance | 마감일과 요구사항 변경이 승인된 수정 공고를 발행해 줘 / Take me to issue the approved solicitation amendment |
| C | `government_contract_administration.offer_receipt_close` | 제안서 접수 마감 / Offer-receipt closure | 마감시각 도달 후 제안서 접수를 잠그는 곳으로 가 줘 / Take me to lock offer receipt after the solicitation deadline |
| C | `government_contract_administration.technical_evaluation_record` | 기술평가 기록 / Technical-evaluation record | 평가위원회의 이해충돌 확인 후 기술평가를 기록해 줘 / Take me to record the panel's technical evaluation after conflict checks |
| C | `government_contract_administration.source_selection_approve` | 낙찰자 선정 승인 / Source-selection approval | 선정권자가 평가 근거와 선정 결정을 승인하는 화면을 열어 줘 / Open approval for the selection authority's documented award decision |
| C | `government_contract_administration.contract_award` | 정부 계약 체결 / Government-contract award | 자금과 책임성 확인이 완료된 계약을 체결하는 곳으로 가 줘 / Take me to award the contract after funding and responsibility clearance |
| C | `government_contract_administration.funds_obligation_record` | 계약 자금 의무부담 기록 / Contract-funds obligation record | 인증된 자금을 이 계약에 의무부담으로 기록하는 화면을 열어 줘 / Open the screen to obligate certified funds to this contract |
| C | `government_contract_administration.contract_modification_execute` | 계약 변경 실행 / Contract-modification execution | 양측 또는 일방 권한이 확인된 계약 변경을 서명하는 곳으로 가 줘 / Take me to execute the authorized bilateral or unilateral contract modification |
| C | `government_contract_administration.option_exercise` | 계약 옵션 행사 / Contract-option exercise | 자금·기간·가격 조건이 확인된 옵션을 행사하는 화면을 열어 줘 / Open option exercise after funding, timing, and price conditions are verified |
| C | `government_contract_administration.invoice_acceptance_authorize` | 청구 검수·지급승인 / Invoice-acceptance authorization | 계약 이행이 확인된 청구의 검수 승인을 기록하는 곳으로 가 줘 / Take me to authorize acceptance for the performance-verified invoice |
| C | `government_contract_administration.cure_show_cause_notice_issue` | 시정·소명 통지 발행 / Cure or show-cause notice issuance | 계약담당관이 승인한 시정 또는 소명 통지를 발행해 줘 / Take me to issue the contracting officer-approved cure or show-cause notice |
| C | `government_contract_administration.termination_decision` | 계약 해지 결정 / Contract-termination decision | 권한과 근거가 검토된 편의상 또는 채무불이행 해지 결정을 기록해 줘 / Take me to record the reviewed termination decision and authority |
| C | `government_contract_administration.contract_closeout` | 정부 계약 종결 / Government-contract closeout | 모든 재산·청구·감사 조건이 해소된 계약을 종결하는 곳으로 가 줘 / Take me to close the contract after all property, invoice, and audit conditions clear |

Roles/assets/states: contracting officer, contract specialist, source-selection authority, evaluation chair, funds certifier, contracting officer's representative, termination officer, and closeout officer; solicitation, offer, evaluation, responsibility clearance, award, obligated funds, modification, option, accepted invoice, termination, and closeout file; `draft/issued/amended/closed`, `received/locked/evaluated`, `selected/awarded`, `active/modified/option-exercised`, and `cure/show-cause/terminated/closed`.

Boundary and collision guard: this domain owns the government contracting officer's solicitation-to-closeout authority. `procurement_supplier_ops` owns an organization's internal requisition, RFQ, purchase order, and supplier onboarding; `research_grants_administration` owns assistance awards; `business_accounting` owns ledger and invoice bookkeeping. A generic “award,” “fund,” “invoice,” “supplier,” or “close” must not route here without a government contract, warranted authority, and acquisition lifecycle state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [FAR Part 5](https://www.acquisition.gov/far/part-5)
2. [FAR Part 15](https://www.acquisition.gov/far/part-15)
3. [FAR Part 42](https://www.acquisition.gov/far/part-42)
4. [FAR Part 43](https://www.acquisition.gov/far/part-43)
5. [FAR Part 49](https://www.acquisition.gov/far/part-49)
6. [FAR 4.804-5](https://www.acquisition.gov/far/4.804-5)
7. [SAM.gov contract opportunities](https://sam.gov/content/opportunities)
8. [Procurement Integrated Enterprise Environment](https://piee.eb.mil/)

## 6. Public-company SEC reporting operations (`public_company_sec_reporting_ops`)

Hub: `public_company_sec_reporting_ops.hub` — 상장회사 SEC 보고 운영 / Public-company SEC reporting operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `public_company_sec_reporting_ops.filer_profile_status` | SEC 제출자 프로필 상태 / SEC filer-profile status | 이 발행인의 제출자 계정과 권한 상태를 보여 줘 / Show filer-account and authorization status for this issuer |
| S | `public_company_sec_reporting_ops.filing_calendar` | SEC 공시 일정 / SEC filing calendar | 이 발행인의 예정 공시와 마감일을 보여 줘 / Show upcoming filings and deadlines for this issuer |
| S | `public_company_sec_reporting_ops.disclosure_controls_status` | 공시통제 상태 / Disclosure-controls status | 이번 보고기간의 검토·인증 통제 상태를 보여 줘 / Show review and certification-control status for this reporting period |
| S | `public_company_sec_reporting_ops.insider_reporting_queue` | 내부자 보고 대기열 / Insider-reporting queue | 임원·이사의 미제출 거래 보고를 보여 줘 / Show unfiled transaction reports for officers and directors |
| S | `public_company_sec_reporting_ops.filing_validation_status` | 공시 검증 상태 / Filing-validation status | 이 제출 패키지의 XML·XBRL 검증 오류를 보여 줘 / Show XML and XBRL validation errors for this filing package |
| S | `public_company_sec_reporting_ops.submission_acceptance_status` | EDGAR 접수 상태 / EDGAR submission-acceptance status | 이 공시 제출의 접수·정지·수락 상태를 보여 줘 / Show receipt, suspension, or acceptance status for this filing |
| S | `public_company_sec_reporting_ops.correspondence_review` | SEC 서신 검토 / SEC correspondence review | 이 제출 건과 연결된 공개·비공개 심사 서신을 열어 줘 / Open review correspondence linked to this filing |
| C | `public_company_sec_reporting_ops.filing_agent_authorization_record` | 공시 대행 권한 기록 / Filing-agent authorization record | 이 발행인을 대신할 제출 대행 권한을 기록하는 곳으로 가 줘 / Take me to record filing-agent authority for this issuer |
| C | `public_company_sec_reporting_ops.periodic_report_create` | 정기보고서 생성 / Periodic-report creation | 해당 기간의 정기보고서 제출 초안을 만드는 화면을 열어 줘 / Open the screen to create the periodic-report filing draft |
| C | `public_company_sec_reporting_ops.xbrl_facts_validate` | XBRL 사실 검증 / XBRL-facts validation | 이 보고기간의 태그·단위·맥락 사실을 검증하는 곳으로 가 줘 / Take me to validate tags, units, contexts, and facts for this period |
| C | `public_company_sec_reporting_ops.periodic_report_submit` | 정기보고서 제출 / Periodic-report submission | 서명과 인증이 완료된 정기보고서를 EDGAR에 제출해 줘 / Take me to submit the signed and certified periodic report to EDGAR |
| C | `public_company_sec_reporting_ops.current_report_submit` | 수시보고서 제출 / Current-report submission | 확정된 중요 사건에 대한 수시보고서를 제출하는 화면을 열어 줘 / Open submission for the current report on this confirmed material event |
| C | `public_company_sec_reporting_ops.registration_statement_submit` | 증권신고서 제출 / Registration-statement submission | 이 증권 발행의 서명된 등록신고서를 제출하는 곳으로 가 줘 / Take me to submit the signed registration statement for this securities offering |
| C | `public_company_sec_reporting_ops.proxy_material_file` | 위임장 자료 제출 / Proxy-material filing | 승인된 주주총회 위임장 자료를 제출하는 화면을 열어 줘 / Open filing for the approved shareholder-meeting proxy materials |
| C | `public_company_sec_reporting_ops.beneficial_ownership_report_file` | 실질소유 보고 제출 / Beneficial-ownership report filing | 이 보유자의 기준 초과 실질소유 보고를 제출하는 곳으로 가 줘 / Take me to file the threshold-triggered beneficial-ownership report |
| C | `public_company_sec_reporting_ops.insider_transaction_report_file` | 내부자 거래 보고 제출 / Insider-transaction report filing | 임원·이사의 확인된 증권 거래 보고를 제출하는 화면을 열어 줘 / Open filing for the officer or director's verified securities transaction |
| C | `public_company_sec_reporting_ops.confidential_treatment_request` | 비공개 처리 요청 / Confidential-treatment request | 근거가 검토된 부속자료 비공개 처리 요청을 제출하는 곳으로 가 줘 / Take me to submit the reviewed confidential-treatment request for this exhibit |
| C | `public_company_sec_reporting_ops.filing_amendment_submit` | 공시 정정 제출 / Filing-amendment submission | 수정을 승인받은 기존 공시의 정정본을 제출하는 화면을 열어 줘 / Open submission for the approved amendment to this filing |
| C | `public_company_sec_reporting_ops.correspondence_response_submit` | SEC 서신 응답 제출 / SEC-correspondence response submission | 법무·공시위원회가 승인한 심사서신 응답을 제출해 줘 / Take me to submit the counsel and disclosure-committee-approved response |
| C | `public_company_sec_reporting_ops.filing_withdrawal_request` | 공시 철회 요청 / Filing-withdrawal request | 권한자가 승인한 해당 제출의 철회 요청을 제출하는 곳으로 가 줘 / Take me to submit the authorized withdrawal request for this filing |

Roles/assets/states: issuer filing administrator, disclosure-committee member, controller, securities counsel, filing agent, XBRL specialist, and officer/director; filer account, periodic/current report, XBRL facts, registration statement, proxy materials, ownership report, insider transaction, and regulator correspondence; `draft/validated/suspended/accepted`, `due/filed/amended`, `comment-open/responded/closed`, and `confidential-treatment-pending/granted/denied`.

Boundary and collision guard: this domain owns an SEC-reporting issuer's EDGAR submissions and related disclosure authority. `business_accounting` owns source ledgers and ordinary financial statements, `financial_crime_compliance_ops` owns AML/sanctions cases, and `campaign_finance_compliance` owns committee disclosure. “Report,” “filing,” “ownership,” “transaction,” or “statement” requires issuer/filer identity, filing form or accession context, authorized signatory, and submission state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [SEC EDGAR Filer Manual](https://www.sec.gov/submit-filings/edgar-filer-manual)
2. [SEC EDGAR glossary and filer resources](https://www.sec.gov/submit-filings/filer-support-resources/edgar-glossary)
3. [17 CFR Part 232](https://www.ecfr.gov/current/title-17/chapter-II/part-232)
4. [SEC forms](https://www.sec.gov/forms)
5. [SEC Inline XBRL](https://www.sec.gov/structureddata/osd-inline-xbrl.html)
6. [EDGAR filing website](https://www.edgarfiling.sec.gov/)

## 7. Wireless-spectrum license operations (`wireless_spectrum_license_ops`)

Hub: `wireless_spectrum_license_ops.hub` — 무선주파수 면허 운영 / Wireless-spectrum license operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `wireless_spectrum_license_ops.license_portfolio_status` | 무선면허 포트폴리오 상태 / Wireless-license portfolio status | 이 면허권자의 활성·만료예정 호출부호를 보여 줘 / Show active and expiring call signs for this licensee |
| S | `wireless_spectrum_license_ops.authorized_frequency_location_view` | 허가 주파수·위치 보기 / Authorized-frequency and location view | 이 면허의 승인된 주파수·출력·송신 위치를 보여 줘 / Show authorized frequency, power, and transmit location for this license |
| S | `wireless_spectrum_license_ops.construction_deadline_status` | 무선시설 건설기한 상태 / Wireless-construction deadline status | 이 호출부호의 건설·운용 개시 마감일을 보여 줘 / Show construction and operational deadlines for this call sign |
| S | `wireless_spectrum_license_ops.interference_coordination_status` | 혼신 조정 상태 / Interference-coordination status | 이 주파수·위치의 조정과 이의 상태를 확인해 줘 / Show coordination and objection status for this frequency and site |
| S | `wireless_spectrum_license_ops.application_status` | 무선면허 신청 상태 / Wireless-license application status | 이 신청의 접수·반려·허가 상태를 보여 줘 / Show receipt, return, and grant status for this application |
| S | `wireless_spectrum_license_ops.buildout_compliance_status` | 구축 의무 준수 상태 / Buildout-compliance status | 이 면허의 구축·서비스 의무 충족 상태를 보여 줘 / Show buildout and service-obligation compliance for this license |
| S | `wireless_spectrum_license_ops.special_temporary_authority_status` | 특별 임시권한 상태 / Special-temporary-authority status | 이 임시 송신 권한의 기간과 심사 상태를 보여 줘 / Show term and review status for this temporary operating authority |
| C | `wireless_spectrum_license_ops.new_license_application` | 신규 무선면허 신청 생성 / New wireless-license application | 해당 서비스·주파수·위치의 신규 면허 신청을 만드는 곳으로 가 줘 / Take me to create a new license application for this service, frequency, and site |
| C | `wireless_spectrum_license_ops.frequency_coordination_attach` | 주파수 조정서 첨부 / Frequency-coordination attachment | 공인 조정 결과를 이 무선면허 신청에 첨부하는 화면을 열어 줘 / Open attachment of the certified coordination result to this application |
| C | `wireless_spectrum_license_ops.application_submit` | 무선면허 신청 제출 / Wireless-license application submission | 서명권자가 인증한 무선면허 신청을 제출하는 곳으로 가 줘 / Take me to submit the signatory-certified wireless application |
| C | `wireless_spectrum_license_ops.license_modification_apply` | 무선면허 변경 신청 / Wireless-license modification application | 승인 주파수·출력·위치 변경을 신청하는 화면을 열어 줘 / Open the application to modify authorized frequency, power, or location |
| C | `wireless_spectrum_license_ops.construction_notification_file` | 무선시설 건설완료 통지 / Construction-notification filing | 완료된 무선시설 건설과 운용 개시를 통지하는 곳으로 가 줘 / Take me to notify completed construction and operational commencement |
| C | `wireless_spectrum_license_ops.buildout_certification_submit` | 구축 의무 인증 제출 / Buildout-certification submission | 측정 근거가 확인된 면허 구축 의무 충족을 인증해 줘 / Take me to certify buildout compliance supported by verified measurements |
| C | `wireless_spectrum_license_ops.renewal_application_submit` | 무선면허 갱신 신청 제출 / License-renewal application submission | 만료 예정 호출부호의 면허 갱신 신청을 제출하는 화면을 열어 줘 / Open submission for renewal of this expiring call sign |
| C | `wireless_spectrum_license_ops.assignment_transfer_application` | 무선면허 양도 신청 / License-assignment application | 지정 면허 자산을 새 면허권자에게 양도하는 신청을 열어 줘 / Open the application to assign the identified licenses to the new licensee |
| C | `wireless_spectrum_license_ops.control_transfer_consent_request` | 지배권 이전 동의 요청 / Transfer-of-control consent request | 면허권자 지배권 변경에 대한 사전 동의를 요청하는 곳으로 가 줘 / Take me to request prior consent for this licensee control change |
| C | `wireless_spectrum_license_ops.special_temporary_authority_request` | 비방송 무선 임시권한 요청 / Non-broadcast wireless STA request | 지정 주파수·위치·기간의 임시 운용 권한을 요청하는 화면을 열어 줘 / Open a request for temporary operation at the specified frequency, site, and term |
| C | `wireless_spectrum_license_ops.interference_complaint_submit` | 유해 혼신 신고 제출 / Harmful-interference complaint submission | 측정 자료가 연결된 이 유해 혼신 신고를 제출하는 곳으로 가 줘 / Take me to submit this harmful-interference complaint with measurement evidence |
| C | `wireless_spectrum_license_ops.license_cancellation_request` | 무선면허 취소 요청 / Wireless-license cancellation request | 권한자가 확인한 해당 면허의 자진 취소 요청을 제출해 줘 / Take me to submit the authorized voluntary cancellation request for this license |
| C | `wireless_spectrum_license_ops.discontinuance_notice_file` | 무선운용 중단 통지 / Wireless-discontinuance notice filing | 이 면허 시설의 영구 운용 중단을 통지하는 화면을 열어 줘 / Open filing for permanent discontinuance of operations under this license |

Roles/assets/states: licensee administrator, frequency coordinator, RF engineer, licensing-system filer, legal signatory, buildout certifier, and interference investigator; call sign/license, frequency/site, application, construction deadline, buildout obligation, special temporary authority, assignment/control transfer, and interference case; `active/expired/termination-pending`, `draft/submitted/returned/granted/dismissed`, `unbuilt/constructed/certified`, and `coordinated/disputed/resolved`.

Boundary and collision guard: this domain covers non-broadcast spectrum authority and regulatory license lifecycle. `broadcast_station_compliance` owns broadcast station/service filings; `telecom_field_service_ops` owns physical work orders, circuits, and configuration activation; consumer connectivity domains own device controls. “Frequency,” “site,” “activation,” “transfer,” and “renewal” require an FCC license/call sign, wireless service, authorized filer, and regulatory state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [FCC Universal Licensing System](https://www.fcc.gov/wireless/universal-licensing-system)
2. [FCC ULS online filing](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources/online-filing)
3. [47 CFR Part 1](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-1)
4. [FCC renewing a license in ULS](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources/renewing-license-universal-licensing-system)
5. [FCC assigning a license or transferring control](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources/transferring-control-or-assigning-license)
6. [FCC ULS resources](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources)

## 8. Commercial-space launch licensing operations (`commercial_space_launch_licensing_ops`)

Hub: `commercial_space_launch_licensing_ops.hub` — 상업우주 발사 인허가 운영 / Commercial-space launch licensing operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `commercial_space_launch_licensing_ops.operator_license_profile` | 우주운송 사업자 면허 프로필 / Space-transportation operator-license profile | 이 사업자의 발사·재진입 면허와 승인 구성을 보여 줘 / Show launch or reentry licenses and approved configurations for this operator |
| S | `commercial_space_launch_licensing_ops.vehicle_site_configuration_view` | 발사체·장소 구성 보기 / Vehicle-and-site configuration view | 이 면허에 승인된 발사체와 발사·재진입 장소를 보여 줘 / Show vehicle and launch or reentry sites authorized by this license |
| S | `commercial_space_launch_licensing_ops.application_review_status` | 우주면허 신청 심사 상태 / Space-license application-review status | 이 신청의 접수·완전성·심사 단계를 보여 줘 / Show acceptance, completeness, and review stage for this application |
| S | `commercial_space_launch_licensing_ops.safety_review_status` | 발사 안전심사 상태 / Launch-safety review status | 이 발사 구성의 미해결 안전분석 항목을 보여 줘 / Show unresolved safety-analysis items for this launch configuration |
| S | `commercial_space_launch_licensing_ops.payload_review_status` | 탑재체 심사 상태 / Payload-review status | 이 임무 탑재체의 심사·결정 상태를 보여 줘 / Show review and determination status for this mission payload |
| S | `commercial_space_launch_licensing_ops.environmental_review_status` | 우주운송 환경심사 상태 / Space-transportation environmental-review status | 이 임무·장소의 환경심사 진행 상태를 보여 줘 / Show environmental-review progress for this mission and site |
| S | `commercial_space_launch_licensing_ops.financial_responsibility_status` | 재정책임 상태 / Financial-responsibility status | 이 임무의 최대개연손실·보험 증빙 상태를 보여 줘 / Show maximum-probable-loss and insurance-evidence status for this mission |
| C | `commercial_space_launch_licensing_ops.preapplication_consultation_record` | 사전신청 협의 기록 / Preapplication-consultation record | 이 발사체·장소에 대한 규제기관 사전협의를 기록하는 곳으로 가 줘 / Take me to record regulator preapplication consultation for this vehicle and site |
| C | `commercial_space_launch_licensing_ops.license_application_create` | 상업우주 면허 신청 생성 / Commercial-space license-application creation | 이 사업자의 발사 또는 재진입 면허 신청 초안을 만들어 줘 / Take me to create this operator's launch or reentry license draft |
| C | `commercial_space_launch_licensing_ops.safety_analysis_submit` | 발사 안전분석 제출 / Launch-safety analysis submission | 검증된 비행안전·시스템안전 분석을 이 신청에 제출하는 곳으로 가 줘 / Take me to submit the validated flight and system safety analyses |
| C | `commercial_space_launch_licensing_ops.payload_review_submit` | 탑재체 심사자료 제출 / Payload-review submission | 지정 임무 탑재체의 소유·목적·궤도 자료를 제출해 줘 / Take me to submit ownership, purpose, and trajectory data for this payload |
| C | `commercial_space_launch_licensing_ops.environmental_information_submit` | 환경정보 제출 / Environmental-information submission | 이 발사체·장소·운영의 검토된 환경정보를 제출하는 화면을 열어 줘 / Open submission for reviewed environmental information on this vehicle, site, and operation |
| C | `commercial_space_launch_licensing_ops.financial_responsibility_evidence_submit` | 재정책임 증빙 제출 / Financial-responsibility evidence submission | 확정된 보험·재정책임 증빙을 해당 임무에 제출하는 곳으로 가 줘 / Take me to submit finalized insurance and financial-responsibility evidence |
| C | `commercial_space_launch_licensing_ops.license_application_submit` | 상업우주 면허 신청 제출 / Commercial-space license-application submission | 책임자가 인증한 완전한 면허 신청을 제출하는 화면을 열어 줘 / Open submission for the responsible official's certified complete application |
| C | `commercial_space_launch_licensing_ops.license_modification_request` | 우주면허 변경 요청 / Space-license modification request | 승인된 발사체·장소·운영 구성의 변경을 요청하는 곳으로 가 줘 / Take me to request a change to the licensed vehicle, site, or operation |
| C | `commercial_space_launch_licensing_ops.safety_waiver_request` | 발사안전 면제 요청 / Launch-safety waiver request | 공익·안전 근거가 검토된 특정 요건 면제를 요청해 줘 / Take me to request waiver of the identified requirement with reviewed safety basis |
| C | `commercial_space_launch_licensing_ops.launch_mission_authorization_request` | 발사 임무 승인 요청 / Launch-mission authorization request | 면허 범위 내 지정 발사 임무의 운용 승인을 요청하는 화면을 열어 줘 / Open an authorization request for this mission under the operator license |
| C | `commercial_space_launch_licensing_ops.launch_readiness_certify` | 발사 준비 인증 / Launch-readiness certification | 안전·기상·범위·보험 조건이 충족된 임무 준비를 인증해 줘 / Take me to certify mission readiness after safety, weather, range, and insurance checks |
| C | `commercial_space_launch_licensing_ops.mishap_event_report_submit` | 우주운송 사고 보고 제출 / Space-transportation mishap report submission | 발생한 발사·재진입 사고의 최초 규제 보고를 제출하는 곳으로 가 줘 / Take me to submit the initial regulatory report for this launch or reentry mishap |
| C | `commercial_space_launch_licensing_ops.return_to_flight_request` | 비행재개 요청 / Return-to-flight request | 원인·시정조치가 승인된 사고 후 비행재개를 요청하는 화면을 열어 줘 / Open a return-to-flight request after cause and corrective actions are approved |

Roles/assets/states: applicant responsible official, licensing manager, system-safety engineer, payload-review lead, environmental lead, financial-responsibility officer, launch-safety director, and mishap investigator; operator license, vehicle/configuration, launch or reentry site, safety analysis, payload, environmental record, maximum-probable-loss/insurance evidence, mission authorization, mishap, and return-to-flight case; `preapplication/draft/submitted/accepted/in-review/issued/modified`, `hazard-open/controlled`, `mission-planned/ready/authorized/complete`, and `mishap-open/investigating/corrective/return-approved`.

Boundary and collision guard: this domain owns commercial launch/reentry operator licensing, mission authority, and regulated mishap return-to-flight. `air_traffic_control_ops` owns airspace clearances, `airport_airside_operations` owns airport movement areas, `aviation_maintenance_ops` owns aircraft airworthiness work, and emergency-response domains own incident command. “Launch,” “vehicle,” “site,” “safety,” or “return to flight” requires a licensed commercial-space operator, vehicle/site configuration, mission, and FAA licensing state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [FAA commercial-space licenses](https://www.faa.gov/space/licenses)
2. [FAA commercial-space licensing process](https://www.faa.gov/space/licenses/licensing_process)
3. [FAA operator licenses and permits](https://www.faa.gov/space/licenses/operator_licenses_permits)
4. [FAA financial responsibility](https://www.faa.gov/space/licenses/financial_responsibility)
5. [FAA compliance, enforcement, and mishap](https://www.faa.gov/space/compliance_enforcement_mishap)
6. [14 CFR Part 450](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450)
7. [14 CFR Part 440](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-440)

## 9. Radioactive-materials license operations (`radioactive_materials_license_ops`)

Hub: `radioactive_materials_license_ops.hub` — 방사성물질 면허 운영 / Radioactive-materials license operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `radioactive_materials_license_ops.materials_license_profile` | 방사성물질 면허 프로필 / Radioactive-materials license profile | 이 면허자의 허용 핵종·용도·보유한도를 보여 줘 / Show authorized nuclides, uses, and possession limits for this licensee |
| S | `radioactive_materials_license_ops.authorized_use_location_view` | 허가 사용장소 보기 / Authorized-use location view | 이 물질을 사용할 수 있는 승인 장소를 보여 줘 / Show locations authorized for use of this radioactive material |
| S | `radioactive_materials_license_ops.sealed_source_inventory_status` | 밀봉선원 재고 상태 / Sealed-source inventory status | 이 면허의 밀봉선원별 보유·이전 상태를 보여 줘 / Show possession and transfer status for each sealed source under this license |
| S | `radioactive_materials_license_ops.radiation_safety_program_status` | 방사선안전 프로그램 상태 / Radiation-safety program status | 이 면허자의 점검·선량·교육 프로그램 상태를 보여 줘 / Show survey, dose, and training-program status for this licensee |
| S | `radioactive_materials_license_ops.personnel_authorization_status` | 방사선 작업자 권한 상태 / Radiation-personnel authorization status | 이 장소의 승인 사용자와 감독 권한을 보여 줘 / Show authorized users and supervisory authority at this location |
| S | `radioactive_materials_license_ops.inspection_enforcement_status` | 방사성물질 점검·집행 상태 / Materials inspection-and-enforcement status | 이 면허의 미해결 점검 소견과 집행 상태를 보여 줘 / Show open inspection findings and enforcement status for this license |
| S | `radioactive_materials_license_ops.event_reporting_status` | 방사성물질 사건 보고 상태 / Radioactive-material event-reporting status | 이 분실·피폭·의료사건의 통지와 최종보고 상태를 보여 줘 / Show notification and final-report status for this loss, exposure, or medical event |
| C | `radioactive_materials_license_ops.license_application_submit` | 방사성물질 면허 신청 제출 / Materials-license application submission | 책임자가 인증한 방사성물질 면허 신청을 제출하는 곳으로 가 줘 / Take me to submit the responsible official's certified materials-license application |
| C | `radioactive_materials_license_ops.license_amendment_request` | 방사성물질 면허 변경 요청 / Materials-license amendment request | 핵종·용도·장소·한도 변경을 신청하는 화면을 열어 줘 / Open a request to amend authorized nuclide, use, location, or limit |
| C | `radioactive_materials_license_ops.authorized_user_add_remove` | 승인 사용자 추가·삭제 / Authorized-user addition or removal | 자격 검토가 완료된 사용자를 이 면허에 추가하거나 삭제해 줘 / Take me to add or remove the qualification-reviewed user on this license |
| C | `radioactive_materials_license_ops.possession_limit_change_request` | 보유한도 변경 요청 / Possession-limit change request | 지정 핵종의 면허 보유한도 변경을 요청하는 곳으로 가 줘 / Take me to request a possession-limit change for the specified nuclide |
| C | `radioactive_materials_license_ops.sealed_source_transfer_record` | 밀봉선원 이전 기록 / Sealed-source transfer record | 두 허가받은 면허자 사이의 선원 이전을 기록하는 화면을 열어 줘 / Open the screen to record source transfer between authorized licensees |
| C | `radioactive_materials_license_ops.source_receipt_inventory_record` | 선원 수령·재고 등록 / Source-receipt inventory record | 수령한 밀봉선원의 식별자와 위치를 재고에 등록해 줘 / Take me to record the received sealed source identifier and location in inventory |
| C | `radioactive_materials_license_ops.leak_test_result_certify` | 누설시험 결과 인증 / Leak-test result certification | 자격자가 완료한 이 선원의 누설시험 결과를 인증하는 화면을 열어 줘 / Open certification for this qualified tester's completed leak-test result |
| C | `radioactive_materials_license_ops.annual_inventory_certify` | 연간 선원재고 인증 / Annual source-inventory certification | 실물대사가 완료된 연간 선원 재고를 인증하는 곳으로 가 줘 / Take me to certify the physically reconciled annual source inventory |
| C | `radioactive_materials_license_ops.radioactive_material_shipment_authorize` | 방사성물질 출하 승인 / Radioactive-material shipment authorization | 수취인 면허와 포장이 확인된 이 출하를 승인해 줘 / Take me to authorize this shipment after recipient license and package checks |
| C | `radioactive_materials_license_ops.lost_stolen_material_report` | 방사성물질 분실·도난 보고 / Lost-or-stolen material report | 발견된 선원 분실 또는 도난을 규제기관에 보고하는 곳으로 가 줘 / Take me to report the discovered loss or theft of this source |
| C | `radioactive_materials_license_ops.medical_event_report_submit` | 방사선 의료사건 보고 제출 / Radiation medical-event report submission | 판정·통지된 의료사건의 서면 보고를 제출하는 화면을 열어 줘 / Open submission for the written report on this determined and notified medical event |
| C | `radioactive_materials_license_ops.decommissioning_plan_submit` | 방사성물질 시설 폐지계획 제출 / Materials-site decommissioning-plan submission | 오염조사와 해제기준이 포함된 폐지계획을 제출해 줘 / Take me to submit the decommissioning plan with survey and release criteria |
| C | `radioactive_materials_license_ops.license_termination_request` | 방사성물질 면허 종료 요청 / Materials-license termination request | 물질 처분과 부지 해제가 확인된 면허 종료를 요청하는 곳으로 가 줘 / Take me to request license termination after material disposition and site release |

Roles/assets/states: licensee responsible officer, radiation-safety officer, authorized-user supervisor, source custodian, licensing specialist, event reporter, and decommissioning manager; materials license, authorized location/use/nuclide/limit, sealed source, national tracking transaction, personnel authorization, leak test, inventory, event, and decommissioning plan; `active/renewal/pending-amendment/expired/terminated`, `received/in-use/transferred/lost/disposed`, `test-pass/fail`, `event-discovered/notified/final`, and `decommissioning-planned/in-progress/released`.

Boundary and collision guard: this domain owns byproduct/materials-license authority and source lifecycle. `nuclear_plant_operations` owns reactor operations; `radiation_therapy_operations` owns patient treatment delivery; `environmental_waste_operations` owns waste handling and manifests. “Radiation,” “source,” “inventory,” “shipment,” or “event” requires the specific materials license, nuclide/source, authorized role/location, and regulatory state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [NRC Web-Based Licensing](https://www.nrc.gov/security/byproduct/ismp/wbl)
2. [NRC Integrated Source Management Portfolio](https://www.nrc.gov/security/byproduct/ismp)
3. [NRC National Source Tracking System overview](https://www.nrc.gov/security/byproduct/ismp/nsts/overview.html)
4. [10 CFR Part 30](https://www.nrc.gov/reading-rm/doc-collections/cfr/part030/)
5. [10 CFR 20.2207](https://www.nrc.gov/reading-rm/doc-collections/cfr/part020/part020-2207.html)
6. [NRC NSTS frequently asked questions](https://www.nrc.gov/security/byproduct/ismp/nsts/faqs)
7. [NRC event assessment](https://www.nrc.gov/about-nrc/regulatory/event-assess)

## 10. Hazardous-materials transport compliance (`hazardous_materials_transport_compliance`)

Hub: `hazardous_materials_transport_compliance.hub` — 위험물 운송 규정준수 / Hazardous-materials transport compliance

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `hazardous_materials_transport_compliance.hazmat_registration_status` | 위험물 운송 등록 상태 / Hazmat-registration status | 이 위험물 고용주의 등록번호와 유효기간을 보여 줘 / Show registration number and validity for this hazmat employer |
| S | `hazardous_materials_transport_compliance.special_permit_status` | 위험물 특별허가 상태 / Hazmat special-permit status | 이 포장·운송 특별허가의 적용 범위와 상태를 보여 줘 / Show scope and status for this packaging or transport special permit |
| S | `hazardous_materials_transport_compliance.shipping_description_review` | 위험물 운송명세 검토 / Hazardous-material shipping-description review | 이 물질의 UN 번호·정식운송품명·등급을 보여 줘 / Show UN number, proper shipping name, and hazard class for this material |
| S | `hazardous_materials_transport_compliance.packaging_authorization_view` | 위험물 포장 승인 보기 / Hazmat-packaging authorization view | 이 물질·수량·운송방식에 허용된 포장을 보여 줘 / Show packaging authorized for this material, quantity, and mode |
| S | `hazardous_materials_transport_compliance.training_qualification_status` | 위험물 교육자격 상태 / Hazmat-training qualification status | 지정 직원의 일반·직무·안전 교육 만료 상태를 보여 줘 / Show general, function-specific, and safety training validity for this employee |
| S | `hazardous_materials_transport_compliance.security_plan_status` | 위험물 보안계획 상태 / Hazmat-security plan status | 이 사업장의 적용 대상 보안계획과 검토 상태를 보여 줘 / Show applicable security plan and review status for this operation |
| S | `hazardous_materials_transport_compliance.incident_case_status` | 위험물 운송사고 상태 / Hazmat-incident case status | 이 누출·손상 사건의 즉시통지와 서면보고 상태를 보여 줘 / Show immediate-notice and written-report status for this release or damage case |
| C | `hazardous_materials_transport_compliance.hazmat_registration_submit` | 위험물 운송 등록 제출 / Hazmat-registration submission | 책임자가 인증한 해당 연도 위험물 등록을 제출하는 곳으로 가 줘 / Take me to submit the responsible official's certified annual hazmat registration |
| C | `hazardous_materials_transport_compliance.material_classification_record` | 위험물 분류 기록 / Hazardous-material classification record | 시험·성분 근거로 이 물질의 위험등급과 UN 명세를 기록해 줘 / Take me to record hazard class and UN description from test and composition evidence |
| C | `hazardous_materials_transport_compliance.package_selection_certify` | 위험물 포장선정 인증 / Hazmat-package selection certification | 수량·상태·운송방식에 맞는 승인 포장 선정을 인증하는 화면을 열어 줘 / Open certification of authorized packaging for quantity, condition, and mode |
| C | `hazardous_materials_transport_compliance.shipping_paper_issue` | 위험물 운송서류 발행 / Hazardous-material shipping-paper issuance | 검증된 명세·수량·비상정보로 운송서류를 발행해 줘 / Take me to issue the shipping paper with validated description, quantity, and emergency data |
| C | `hazardous_materials_transport_compliance.marking_label_placard_record` | 표시·라벨·플래카드 기록 / Marking, labeling, and placarding record | 이 포장과 운송수단에 적용한 표시·라벨·플래카드를 기록해 줘 / Take me to record markings, labels, and placards applied to this package and vehicle |
| C | `hazardous_materials_transport_compliance.carrier_acceptance_record` | 운송인 위험물 인수 기록 / Carrier hazmat-acceptance record | 서류·포장·표시 검사가 통과된 화물을 인수 기록하는 곳으로 가 줘 / Take me to record carrier acceptance after document, package, and marking checks pass |
| C | `hazardous_materials_transport_compliance.route_plan_approve` | 위험물 운송경로 승인 / Hazmat-route plan approval | 보안·제한·비상요건이 반영된 운송경로를 승인하는 화면을 열어 줘 / Open approval for the route incorporating security, restriction, and emergency requirements |
| C | `hazardous_materials_transport_compliance.employee_training_certify` | 위험물 직원교육 인증 / Hazmat-employee training certification | 평가를 통과한 직원의 직무별 위험물 교육을 인증해 줘 / Take me to certify function-specific hazmat training after the employee passes evaluation |
| C | `hazardous_materials_transport_compliance.security_plan_approve` | 위험물 보안계획 승인 / Hazmat-security plan approval | 위험평가와 인사·접근·운송 조치가 검토된 계획을 승인해 줘 / Take me to approve the plan after risk, personnel, access, and transport review |
| C | `hazardous_materials_transport_compliance.special_permit_application_submit` | 위험물 특별허가 신청 제출 / Hazmat special-permit application submission | 동등 안전성 근거가 포함된 특별허가 신청을 제출하는 곳으로 가 줘 / Take me to submit the special-permit application with equivalent-safety basis |
| C | `hazardous_materials_transport_compliance.incident_initial_notice` | 위험물 사고 최초 통지 / Hazmat-incident initial notice | 기준을 충족한 이 운송 중 사고를 즉시 통지하는 화면을 열어 줘 / Open immediate notice for this threshold-triggering transportation incident |
| C | `hazardous_materials_transport_compliance.incident_report_submit` | 위험물 사고 서면보고 제출 / Hazmat-incident written-report submission | 조사된 물질·포장·피해 정보를 담은 서면보고를 제출해 줘 / Take me to submit the written incident report with investigated material, package, and consequence data |
| C | `hazardous_materials_transport_compliance.package_nonconformance_hold` | 위험물 포장 부적합 보류 / Hazmat-package nonconformance hold | 누출·손상·승인불일치 포장을 운송 보류하는 곳으로 가 줘 / Take me to hold transport of this leaking, damaged, or unauthorized package |

Roles/assets/states: hazmat employer/offeror, classifier, packaging engineer, shipping-paper preparer, carrier acceptance agent, trainer, security-plan official, and incident reporter; registration, hazardous material/UN description, package/authorization, shipping paper, marks/labels/placards, training record, security plan, special permit, route plan, and incident; `registered/lapsed`, `classified/unclassified`, `package-authorized/rejected`, `offered/accepted/held`, `trained/expired`, and `incident-immediate/report-due/closed`.

Boundary and collision guard: this domain owns cross-modal hazardous-material classification, packaging, communication, training, security, permit, and incident-reporting obligations. `freight_forwarding_customs_ops` owns forwarding and customs entry, fleet/rail/maritime domains own modal operations, and `environmental_waste_operations` owns waste disposition and environmental manifests. A generic “shipment,” “label,” “route,” “training,” or “incident” requires regulated hazardous material, offeror/carrier authority, package/mode, and compliance state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [49 CFR Part 171](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-171)
2. [49 CFR Part 172](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-172)
3. [49 CFR Part 173](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-173)
4. [49 CFR Part 107](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-A/part-107)
5. [PHMSA registration overview](https://www.phmsa.dot.gov/registration/registration-overview)
6. [PHMSA hazmat special permits](https://www.phmsa.dot.gov/approvals-and-permits/hazmat/special-permits)
7. [PHMSA incident reporting](https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-reporting)

## 11. Firearms-dealer compliance operations (`firearms_dealer_compliance_ops`)

Hub: `firearms_dealer_compliance_ops.hub` — 총기 판매면허 규정준수 운영 / Firearms-dealer compliance operations

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `firearms_dealer_compliance_ops.license_profile_status` | 총기 판매면허 프로필 상태 / Firearms-license profile status | 이 영업장의 연방총기면허 유형과 만료 상태를 보여 줘 / Show federal firearms-license type and expiration for this premises |
| S | `firearms_dealer_compliance_ops.responsible_person_roster` | 책임자 명단 / Responsible-person roster | 이 면허 법인의 등록된 책임자와 검토 상태를 보여 줘 / Show registered responsible persons and review status for this license entity |
| S | `firearms_dealer_compliance_ops.acquisition_disposition_inventory` | 총기 취득·처분 재고 / Firearm acquisition-and-disposition inventory | 이 영업장의 장부상 보유 총기와 취득 출처를 보여 줘 / Show book inventory and acquisition sources for firearms at this premises |
| S | `firearms_dealer_compliance_ops.background_check_case_status` | 총기 배경조회 상태 / Firearm background-check case status | 이 양수인의 조회가 진행·지연·거부 중인지 보여 줘 / Show whether this transferee check is pending, delayed, or denied |
| S | `firearms_dealer_compliance_ops.trace_request_queue` | 총기 추적요청 대기열 / Firearm trace-request queue | 기한 내 회신해야 할 총기 추적요청을 보여 줘 / Show firearm trace requests awaiting timely response |
| S | `firearms_dealer_compliance_ops.theft_loss_case_status` | 총기 도난·분실 사건 상태 / Firearm theft-and-loss case status | 이 영업장 분실 총기의 통지·회수 상태를 보여 줘 / Show notification and recovery status for firearms missing from this premises |
| S | `firearms_dealer_compliance_ops.inspection_correction_status` | 면허점검 시정 상태 / License-inspection correction status | 이 점검의 장부·보관 시정 항목을 보여 줘 / Show open recordkeeping and storage corrections from this inspection |
| C | `firearms_dealer_compliance_ops.license_application_submit` | 연방총기면허 신청 제출 / Federal-firearms-license application submission | 책임자가 인증한 이 영업장의 면허 신청을 제출하는 곳으로 가 줘 / Take me to submit the responsible person's certified license application for this premises |
| C | `firearms_dealer_compliance_ops.license_renewal_submit` | 연방총기면허 갱신 제출 / Federal-firearms-license renewal submission | 만료 예정 영업장 면허의 갱신 신청을 제출하는 화면을 열어 줘 / Open submission for renewal of this expiring premises license |
| C | `firearms_dealer_compliance_ops.responsible_person_update` | 면허 책임자 변경 / License responsible-person update | 신원자료가 확인된 책임자를 면허 기록에 추가하거나 삭제해 줘 / Take me to add or remove the identity-verified responsible person |
| C | `firearms_dealer_compliance_ops.firearm_acquisition_record` | 총기 취득 장부 기록 / Firearm-acquisition record | 공급자와 총기 식별정보를 취득 장부에 기록하는 곳으로 가 줘 / Take me to record supplier and firearm identifiers in the acquisition record |
| C | `firearms_dealer_compliance_ops.transferee_identity_record` | 양수인 신원기록 / Transferee-identity record | 본인확인된 양수인의 필수 거래 신원정보를 기록해 줘 / Take me to record required transaction identity data for the verified transferee |
| C | `firearms_dealer_compliance_ops.background_check_initiate` | 총기 배경조회 개시 / Firearm background-check initiation | 본인과 거래가 확인된 양수인의 배경조회를 개시하는 화면을 열어 줘 / Open background-check initiation for the identity- and transaction-verified transferee |
| C | `firearms_dealer_compliance_ops.transfer_disposition_record` | 총기 양도·처분 기록 / Firearm transfer-and-disposition record | 적법한 진행 응답과 인도가 확인된 총기 처분을 장부에 기록해 줘 / Take me to record disposition after lawful proceed status and delivery are verified |
| C | `firearms_dealer_compliance_ops.multiple_sale_report_submit` | 다중판매 보고 제출 / Multiple-sale report submission | 기준을 충족한 해당 양수인의 다중판매 보고를 제출하는 곳으로 가 줘 / Take me to submit the threshold-triggered multiple-sale report for this transferee |
| C | `firearms_dealer_compliance_ops.trace_response_submit` | 총기 추적응답 제출 / Firearm trace-response submission | 장부에서 확인된 취득·처분 정보를 이 추적요청에 회신해 줘 / Take me to submit book-verified acquisition and disposition data for this trace request |
| C | `firearms_dealer_compliance_ops.theft_loss_report_submit` | 총기 도난·분실 보고 제출 / Firearm theft-and-loss report submission | 실사로 확인된 영업장 도난·분실 총기를 신고하는 화면을 열어 줘 / Open reporting for premises theft or loss confirmed by physical inventory |
| C | `firearms_dealer_compliance_ops.inventory_discrepancy_record` | 총기 재고불일치 기록 / Firearm-inventory discrepancy record | 실물과 장부의 총기 식별 불일치를 사건으로 기록해 줘 / Take me to record firearm identifier differences between physical stock and books |
| C | `firearms_dealer_compliance_ops.records_disposition_transfer` | 폐업 장부 이전 / Discontinued-business records transfer | 폐업 면허자의 보존대상 장부를 지정 수탁처로 이전 기록하는 곳으로 가 줘 / Take me to record transfer of retained records from the discontinued licensee |
| C | `firearms_dealer_compliance_ops.license_surrender_closeout` | 총기면허 반납·종결 / Firearms-license surrender and closeout | 재고·장부 처리가 확인된 면허 반납과 영업 종결을 기록해 줘 / Take me to record license surrender after inventory and records disposition are verified |

Roles/assets/states: federal firearms license responsible person, compliance manager, bound-book custodian, transfer clerk, background-check liaison, trace responder, theft/loss reporter, and discontinued-business records custodian; license/premises, responsible persons, firearm inventory record, transferee record/background check, transfer disposition, multiple-sale report, trace request, theft/loss case, inspection correction, and surrendered records; `active/renewal/expired/surrendered`, `acquired/in-inventory/transferred`, `background-pending/proceed/delayed/denied/cancelled`, `trace-open/responded`, `loss-discovered/reported/recovered`, and `correction-open/closed`.

Boundary and collision guard: this is licensee recordkeeping and regulatory compliance, not consumer shopping or weapons-use guidance. Consumer commerce owns browsing and payment; `credential_vault` owns personal credentials; government identity domains own general identity proofing; legal domains own matters and filings. “Buy,” “transfer,” “identity,” “trace,” or “loss” cannot select it without a licensed premises, specific firearm/transaction record, authorized dealer role, and regulatory state. The domain must never supply operational weapon-use instructions.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [27 CFR Part 478](https://www.ecfr.gov/current/title-27/chapter-II/subchapter-B/part-478)
2. [ATF applications and eForms](https://www.atf.gov/firearms/applications-eforms)
3. [ATF apply for a license](https://www.atf.gov/firearms/apply-license)
4. [FBI National Instant Criminal Background Check System](https://www.fbi.gov/how-we-can-help-you/more-fbi-services-and-information/nics)
5. [ATF eTrace fact sheet](https://www.atf.gov/resource-center/fact-sheet/fact-sheet-etrace-internet-based-firearms-tracing-and-analysis)
6. [ATF report firearms theft or loss](https://www.atf.gov/firearms/report-firearms-theft-or-loss)
7. [ATF firearms forms](https://www.atf.gov/firearms/forms)

## 12. Commercial-vessel safety compliance (`commercial_vessel_safety_compliance`)

Hub: `commercial_vessel_safety_compliance.hub` — 상선 안전 규정준수 / Commercial-vessel safety compliance

| Class | Terminal function ID | 기능명 / Function name | 대표 목표 / Representative goal |
|:---:|---|---|---|
| S | `commercial_vessel_safety_compliance.vessel_certificate_profile` | 선박 증서 프로필 / Vessel-certificate profile | 이 선박의 검사증서·항로·운항제한을 보여 줘 / Show inspection certificate, route, and operating restrictions for this vessel |
| S | `commercial_vessel_safety_compliance.inspection_due_status` | 선박 검사기한 상태 / Vessel-inspection due status | 이 선박의 연차·정기·임시 검사 마감일을 보여 줘 / Show annual, periodic, and special inspection due dates for this vessel |
| S | `commercial_vessel_safety_compliance.crew_credential_manning_status` | 승무자격·정원 상태 / Crew-credential and manning status | 현재 승무원의 자격과 최소안전정원 충족 상태를 보여 줘 / Show credential and minimum-safe-manning status for the current crew |
| S | `commercial_vessel_safety_compliance.safety_equipment_status` | 선박 안전설비 상태 / Vessel-safety equipment status | 구명·소방·경보 설비의 점검과 결함 상태를 보여 줘 / Show inspection and defect status for lifesaving, fire, and alarm equipment |
| S | `commercial_vessel_safety_compliance.pollution_certificate_status` | 오염방지 증서 상태 / Pollution-prevention certificate status | 이 선박의 오염방지 증서와 기록부 상태를 보여 줘 / Show pollution-prevention certificates and record-book status for this vessel |
| S | `commercial_vessel_safety_compliance.deficiency_detention_status` | 결함·억류 상태 / Deficiency-and-detention status | 이 선박의 미시정 결함과 운항 억류 상태를 보여 줘 / Show open deficiencies and operational-detention status for this vessel |
| S | `commercial_vessel_safety_compliance.casualty_case_status` | 해양사고 사건 상태 / Marine-casualty case status | 이 좌초·충돌·인명사고의 보고·조사 상태를 보여 줘 / Show reporting and investigation status for this grounding, collision, or injury case |
| C | `commercial_vessel_safety_compliance.inspection_request_submit` | 선박 검사 요청 제출 / Vessel-inspection request submission | 소유자·운영자가 해당 선박의 법정 검사를 요청하는 곳으로 가 줘 / Take me to submit the owner or operator's statutory inspection request |
| C | `commercial_vessel_safety_compliance.deficiency_record` | 선박 안전결함 기록 / Vessel-safety deficiency record | 검사에서 확인된 설비·구조·운항 결함을 기록하는 화면을 열어 줘 / Open the screen to record an inspection-confirmed equipment, structural, or operational deficiency |
| C | `commercial_vessel_safety_compliance.corrective_action_submit` | 선박 시정조치 제출 / Vessel corrective-action submission | 결함 원인과 완료 증거가 포함된 시정조치를 제출해 줘 / Take me to submit corrective action with cause and completion evidence |
| C | `commercial_vessel_safety_compliance.certificate_endorsement_request` | 선박 증서 배서 요청 / Vessel-certificate endorsement request | 검사 완료 후 항로·서비스 증서 배서를 요청하는 화면을 열어 줘 / Open a route or service certificate-endorsement request after inspection |
| C | `commercial_vessel_safety_compliance.manning_exception_request` | 최소정원 예외 요청 / Safe-manning exception request | 운항·자격·안전 근거를 갖춘 최소정원 예외를 요청해 줘 / Take me to request a safe-manning exception with operational and safety basis |
| C | `commercial_vessel_safety_compliance.safety_drill_record` | 선박 안전훈련 기록 / Vessel-safety drill record | 완료된 화재·퇴선·구조 훈련과 참가자를 기록하는 곳으로 가 줘 / Take me to record the completed fire, abandon-ship, or rescue drill and participants |
| C | `commercial_vessel_safety_compliance.security_plan_submit` | 선박 보안계획 제출 / Vessel-security plan submission | 회사·선박 보안책임자가 검토한 보안계획을 제출해 줘 / Take me to submit the company and vessel security officers' reviewed plan |
| C | `commercial_vessel_safety_compliance.pollution_prevention_record` | 선박 오염방지 기록 / Vessel pollution-prevention record | 유류·폐기물 처리와 방지설비 작업을 공식 기록하는 곳으로 가 줘 / Take me to record oil or waste handling and pollution-control equipment work |
| C | `commercial_vessel_safety_compliance.dangerous_condition_report` | 선박 위험상태 보고 / Vessel dangerous-condition report | 항로 안전에 영향을 주는 결함·상태를 즉시 보고하는 화면을 열어 줘 / Open immediate reporting for a condition affecting safe navigation |
| C | `commercial_vessel_safety_compliance.marine_casualty_initial_report` | 해양사고 최초 보고 / Marine-casualty initial report | 기준을 충족한 좌초·충돌·부상 사고를 최초 보고하는 곳으로 가 줘 / Take me to make the initial report for this threshold-triggering casualty |
| C | `commercial_vessel_safety_compliance.marine_casualty_report_submit` | 해양사고 서면보고 제출 / Marine-casualty written-report submission | 조사된 항해·인명·손상 정보를 담은 서면보고를 제출해 줘 / Take me to submit the written casualty report with investigated navigation, injury, and damage data |
| C | `commercial_vessel_safety_compliance.return_to_service_request` | 선박 운항재개 요청 / Vessel return-to-service request | 억류 결함의 시정·재검사가 완료된 운항재개를 요청해 줘 / Take me to request return to service after correction and reinspection of detained deficiencies |
| C | `commercial_vessel_safety_compliance.vessel_decommission_record` | 상선 운항폐지 기록 / Commercial-vessel decommissioning record | 증서·등록·잔여 위험 처리가 확인된 운항폐지를 기록해 줘 / Take me to record decommissioning after certificate, registration, and residual-risk disposition |

Roles/assets/states: vessel owner/managing operator, master, marine inspector, designated person ashore, vessel-security officer, engineering officer, and casualty investigator; vessel/official number, inspection certificate/endorsement, crew/manning, lifesaving/fire/pollution systems, deficiency/detention, security plan, drill, dangerous condition, casualty, return-to-service, and decommissioning record; `certificated/expired/endorsement-pending`, `inspection-due/open/completed`, `deficiency-open/corrected/detained/released`, `underway/out-of-service/return-pending`, and `casualty-initial/final/closed`.

Boundary and collision guard: this domain owns vessel certification, inspection, manning, safety/security equipment, casualty reporting, detention, and return-to-service. `maritime_port_logistics` owns cargo, berth, gate, and yard flow; fleet-driver domains own road vehicles; environmental-waste domains own waste disposition; emergency-response domains own incident command. “Vessel,” “crew,” “inspection,” “deficiency,” or “casualty” requires a certificated commercial vessel, owner/master/inspector authority, and safety-certificate or casualty state.

Official primary-source URL candidates — **all are unverified candidates (미검증 후보)**; accessibility, current authority, jurisdiction, and terminal mapping remain unverified:

1. [USCG Homeport](https://homeport.uscg.mil/)
2. [46 CFR Part 2](https://www.ecfr.gov/current/title-46/chapter-I/subchapter-A/part-2)
3. [46 CFR Part 4](https://www.ecfr.gov/current/title-46/chapter-I/subchapter-A/part-4)
4. [46 CFR Part 15](https://www.ecfr.gov/current/title-46/chapter-I/subchapter-B/part-15)
5. [33 CFR Part 160](https://www.ecfr.gov/current/title-33/chapter-I/subchapter-P/part-160)
6. [33 CFR Part 104](https://www.ecfr.gov/current/title-33/chapter-I/subchapter-H/part-104)
7. [USCG Inspections and Compliance Directorate](https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/)

## Official-source candidate status

The 81 links above are discovery seeds, not accepted evidence. Every link is expressly an **official primary-source unverified candidate (공식 1차 출처 미검증 후보)**. Before implementation, each candidate needs retrieval, redirect and MIME capture, current-authority and jurisdiction review, normalized URL identity, content hashing where retrievable, and explicit role/asset/state/terminal mapping. A candidate that is unavailable, secondary, superseded, jurisdictionally inapplicable, or too broad must be replaced with an equal-or-better official primary source. No terminal is presently claimed as source-verified.

## Append-only collision and duplicate audit

The audit unit is `authorized actor + governed asset + jurisdiction/facility + lifecycle state or transition + real-world consequence`. Exact string uniqueness alone is not evidence of non-equivalence.

Draft-level mechanical results against the permitted current-catalog ID/name inventory:

| Check | Result |
|---|---:|
| Proposed domain IDs | **12; 0 duplicates; 0 canonical intersections** |
| Proposed function IDs, including hubs | **252; 0 duplicates; 0 canonical intersections** |
| Prospective intent IDs | **240; 0 within-draft duplicates; canonical-intent comparison deferred by the input boundary** |
| Terminal class counts | **240 total = 84 `S` + 156 `C`; every domain 7/13** |
| Korean/English function-name strings, including hubs | **504; 0 within-draft normalized duplicates; 0 canonical normalized-name intersections** |
| Official-source candidate URLs | **81; 81 normalized-string unique; 6–8 per domain** |
| Explicit per-domain “미검증 후보” labels | **12 of 12** |

Name normalization for this draft-level result used Unicode NFKC, case folding, and removal of punctuation, symbols, and spacing. URL counts by domain are **7/7/6/6/8/6/6/7/7/7/7/7** in section order. Within the proposal, `theft_loss_case_status` is shared by two domains and `license_application_submit` by three; the asset-qualified bilingual names and full IDs remain distinct. Thirteen proposed terminal keys also share a suffix with at least one current function ID: `application_submit`, `assignment_transfer_application`, `case_close`, `corrective_action_submit`, `correspondence_review`, `incident_report_submit`, `inventory_discrepancy_record`, `license_amendment_request`, `license_application_create`, `license_renewal_submit`, `periodic_report_submit`, `reporting_calendar`, and `special_temporary_authority_request`. These are suffix-only alerts; none is a full-ID or normalized bilingual-name collision. Their role/asset/state boundaries remain mandatory semantic review cases.

The highest-risk contrast sets are:

| Proposed V16 domain | Nearest existing domains by inspected names | Mandatory non-equivalence boundary |
|---|---|---|
| `controlled_substance_compliance_ops` | `pharmacy_dispensing_ops`, `procurement_supplier_ops`, generic inventory functions | DEA registrant and scheduled-substance authority, not patient dispensing or ordinary procurement |
| `medical_device_regulatory_ops` | `manufacturing_quality_ops`, `clinical_trials_operations`, public-health domains | device market authorization/listing/postmarket reporting, not internal quality, study conduct, or population cases |
| `occupational_safety_case_ops` | construction, mining, food-inspection, and manufacturing-quality domains | employer OSHA record/case/citation/abatement state, not an industry asset inspection or CAPA |
| `food_manufacturing_recall_ops` | `food_establishment_inspection`, `manufacturing_quality_ops`, freight and public-health domains | manufacturer preventive-control/traceability/recall chain, not regulator inspection, generic quality, transport, or outbreak casework |
| `government_contract_administration` | `procurement_supplier_ops`, `research_grants_administration`, `business_accounting` | warranted government contracting authority and FAR award lifecycle, not internal buying, assistance, or ledger work |
| `public_company_sec_reporting_ops` | `business_accounting`, `financial_crime_compliance_ops`, `campaign_finance_compliance` | issuer/EDGAR filing state, not books, AML cases, or political-committee disclosure |
| `wireless_spectrum_license_ops` | `broadcast_station_compliance`, `telecom_field_service_ops`, connectivity domains | non-broadcast spectrum license/call-sign lifecycle, not station content, physical network work, or device settings |
| `commercial_space_launch_licensing_ops` | `air_traffic_control_ops`, `airport_airside_operations`, `aviation_maintenance_ops`, emergency response | launch/reentry operator license, mission, and mishap return-to-flight, not air clearance, airport movement, aircraft maintenance, or incident command |
| `radioactive_materials_license_ops` | `nuclear_plant_operations`, `radiation_therapy_operations`, `environmental_waste_operations` | materials license/source custody and authorized use, not reactor control, patient treatment, or waste handling |
| `hazardous_materials_transport_compliance` | freight/customs, fleet, rail, maritime, and environmental-waste domains | cross-modal classification/package/communication/training/permit duty, not shipment orchestration, modal control, or waste disposition |
| `firearms_dealer_compliance_ops` | consumer commerce, credential, government identity, and legal domains | licensed-dealer premises, bound record, check/trace/loss state, not shopping, identity storage, general proofing, or legal matter work |
| `commercial_vessel_safety_compliance` | `maritime_port_logistics`, fleet, environmental-waste, and emergency-response domains | vessel certificate/inspection/manning/casualty state, not cargo/berth flow, road fleet, waste disposition, or incident command |

Mechanical checks must cover the proposed domain IDs, hub and terminal function IDs, generated intent IDs, normalized Korean and English names, normalized URLs, and per-domain `S/C` counts. Because the authorized input boundary excludes aliases, representative goals, evaluation fixtures, answer keys, and failure reports from the existing catalog, this draft makes no claim about collision against those excluded surfaces. Implementation must run that broader comparison only after the audit draft is accepted and the independent-evaluation separation remains protected.

Potentially ambiguous shared words and suffixes—including `application`, `registration`, `renewal`, `report`, `status`, `transfer`, `inventory`, `inspection`, `incident`, `certify`, `close`, and `return_to_service`—are intentional stress points, not routing evidence. Every implementation requires two positive discriminators and a nearest-rival negative discriminator. Any unresolved `same_goal`, `same_transition`, `true_equivalent`, `unsafe_alias`, or wrong-safety-envelope result blocks materialization.

## Draft acceptance conditions

- Exactly 12 domains, 12 hubs, 240 terminals, and 240 prospective one-to-one intents are proposed; every domain has exactly 7 `S` and 13 `C` terminals.
- The projected physical totals are exactly 191 domains, 3,118 functions, 2,900 terminals/intents, and 2,898 unique physical default terminals. The projected logical totals are 3,108 functions, 2,890 intents, and 2,888 unique logical default terminals if no new equivalence is found.
- Every terminal has a bilingual name and representative goal, explicit roles/assets/states at domain level, a nearest-domain boundary, and at least five official primary-source URL candidates explicitly marked unverified.
- Proposed domain and function IDs have zero exact collision with the permitted current domain/function inventory; prospective intent IDs have zero within-draft duplicate and await a later canonical-intent comparison. Proposed Korean/English function names have zero unresolved normalized duplicate within this draft.
- Implementation may begin only after source verification, all-existing-destination semantic comparison, jurisdiction refinement, and approval of the high-risk safety envelope. No implementation test threshold is relaxed by this plan.

## Audit limits

This document is an append-only planning artifact. It proves neither that a product exposes these destinations nor that a resolver can locate them, a source currently supports them, or a user has authority to act. It creates no source module, catalog record, fixture, provider path, package/resource identifier, accuracy result, or external side effect. Source retrieval and mapping, semantic/equivalence review, implementation, independently authored evaluation, and real-interface validation remain separate follow-on work.
