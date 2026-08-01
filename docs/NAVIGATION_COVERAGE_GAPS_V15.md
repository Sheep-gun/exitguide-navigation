# Navigation ontology coverage gap audit — v15

Audit date: 2026-07-30
Baseline: canonical v14 catalog `14.0.0`, **167 domains, 2,614 physical functions, 2,420 physical terminal functions, and 2,420 physical intents**. The function-equivalence overlay reduces that same payload to **2,604 logical functions, 2,410 logical intents, and 2,408 unique logical default-terminal destinations**. This audit treated `function-catalog.v1.json`, `scripts/navigation_catalog_v3_data.py` through `navigation_catalog_v14_data.py`, `NAVIGATION_COVERAGE_GAPS_V5.md` through `V14.md`, and the reviewed function-equivalence groups as the complete prior set. It did not inspect or create an independent evaluation fixture.

## Decision and exact projection

V15 should add the following 12 role-governed domains. Each has a governed asset, lifecycle, authority boundary, and user consequence that is absent from v3–v14. The proposal is exactly **252 physical functions** (**12 hubs + 240 terminals**) and **240 one-to-one intents**. No proposed terminal is intended to join an existing equivalence class.

| Priority | Proposed domain ID | Terminals | Functions with hub | Intents | Sensitive read-only (`S`) | Consequential (`C`) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `airport_airside_operations` | 20 | 21 | 20 | 7 | 13 |
| 2 | `federal_records_disposition_ops` | 20 | 21 | 20 | 7 | 13 |
| 3 | `doj_foia_case_processing` | 20 | 21 | 20 | 7 | 13 |
| 4 | `dam_safety_operations` | 20 | 21 | 20 | 7 | 13 |
| 5 | `nlrb_representation_case_ops` | 20 | 21 | 20 | 7 | 13 |
| 6 | `special_education_program_admin` | 20 | 21 | 20 | 7 | 13 |
| 7 | `pension_plan_administration` | 20 | 21 | 20 | 7 | 13 |
| 8 | `campaign_finance_compliance` | 20 | 21 | 20 | 7 | 13 |
| 9 | `export_control_authorization_ops` | 20 | 21 | 20 | 7 | 13 |
| 10 | `broadcast_station_compliance` | 20 | 21 | 20 | 7 | 13 |
| 11 | `app_store_release_management` | 20 | 21 | 20 | 7 | 13 |
| 12 | `domain_registration_operations` | 20 | 21 | 20 | 7 | 13 |
| **Total** | **12 domains** | **240** | **252** | **240** | **84** | **156** |

Exact count arithmetic if the pack is accepted unchanged:

| View | v14 baseline | V15 append | Projected v15 |
|---|---:|---:|---:|
| Domains | 167 | +12 | **179** |
| Physical functions | 2,614 | +252 | **2,866** |
| Physical terminal functions | 2,420 | +240 | **2,660** |
| Physical intents | 2,420 | +240 | **2,660** |
| Logical functions after known equivalence collapse | 2,604 | +252 | **2,856** |
| Logical intents after known equivalence collapse | 2,410 | +240 | **2,650** |
| Unique logical default-terminal destinations | 2,408 | +240 | **2,648** |

The logical projections are acceptance conditions, not assumptions to waive later. If implementation finds any new `true_equivalent` relation, V15 must remove or redesign that proposed terminal and restore these exact append-only counts before merge.

## Common ID, bilingual naming, and safety contract

- Hub ID: `<domain>.hub`; terminal function ID: `<domain>.<terminal_key>`; intent ID: `v15_<domain>_<terminal_key>`.
- Every row below is normative for the Korean and English function name and for one representative Korean and English goal. Implementations may add aliases, but may not replace the governed asset or lifecycle consequence.
- A terminal may resolve only after at least two of `authorized role`, `governed asset`, `jurisdiction/facility`, and `lifecycle state` are present. Every `C` terminal requires role, asset, and current state.
- All 12 hubs are `risk_level=low`, `state_changing=false`, `automation_policy=safe_navigation`, and stop on the hub screen.
- All 240 terminals are `risk_level=high`, `automation_policy=never_auto`, `stop_policy=before_action`, and `user_owned_final_press=true`. The 84 `S` terminals are sensitive reads with `state_changing=false`; the 156 `C` terminals have `state_changing=true`.
- Wrong role, wrong person or asset, missing jurisdiction, stale/offline data, missing consent, pending dual review, legal/safety/quality hold, disabled control, interlock, or emergency override causes abstention or a stop at the domain hub.
- Names describe conceptual destinations. They are not package names, provider labels, resource IDs, coordinates, screenshots, or fixed click paths.

## 1. Airport airside operations (`airport_airside_operations`)

Hub: `airport_airside_operations.hub` — 공항 에어사이드 운영 / Airport airside operations

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `airport_airside_operations.airport_certificate_status` | 공항 인증 상태 / Airport certificate status | 공항 인증서 상태를 확인해 줘 / Show the airport certificate status |
| S | `airport_airside_operations.certification_manual_review` | 공항 인증 매뉴얼 검토 / Certification manual review | 현재 승인된 공항 인증 매뉴얼을 열어 줘 / Open the current approved airport certification manual |
| S | `airport_airside_operations.movement_area_condition_queue` | 이동지역 상태 작업함 / Movement-area condition queue | 활주로와 유도로 상태 작업함을 보여 줘 / Show the runway and taxiway condition queue |
| S | `airport_airside_operations.pavement_condition_status` | 포장 상태 조회 / Pavement condition status | 이동지역 포장 결함 상태를 확인해 줘 / Show movement-area pavement defect status |
| S | `airport_airside_operations.lighting_marking_sign_status` | 등화·표지·표식 상태 / Lighting, marking, and sign status | 에어사이드 등화와 표지 상태를 보여 줘 / Show airside lighting and sign status |
| S | `airport_airside_operations.wildlife_hazard_plan_status` | 야생동물 위험계획 상태 / Wildlife-hazard plan status | 야생동물 위험평가와 관리계획 상태를 열어 줘 / Open the wildlife assessment and management-plan status |
| S | `airport_airside_operations.arff_readiness_status` | 항공기 구조소방 준비 상태 / ARFF readiness status | 항공기 구조소방 준비 상태를 확인해 줘 / Show aircraft rescue and firefighting readiness |
| C | `airport_airside_operations.daily_self_inspection_record` | 일일 자체점검 기록 / Daily self-inspection record | 오늘 에어사이드 자체점검을 기록하러 가 줘 / Take me to record today's airside self-inspection |
| C | `airport_airside_operations.discrepancy_risk_classify` | 결함 위험도 분류 / Discrepancy risk classification | 발견한 공항 결함의 위험도를 분류하는 곳으로 가 줘 / Take me to classify the airport discrepancy risk |
| C | `airport_airside_operations.foreign_object_debris_report` | 외부물질 잔해 보고 / Foreign-object-debris report | 이동지역 FOD를 보고하는 화면을 열어 줘 / Open the movement-area FOD reporting screen |
| C | `airport_airside_operations.runway_condition_code_issue` | 활주로 상태코드 발행 / Runway-condition-code issue | 오염 활주로 상태코드를 발행하는 곳으로 가 줘 / Take me to issue the contaminated-runway condition code |
| C | `airport_airside_operations.snow_ice_control_plan_activate` | 제설·제빙 계획 활성화 / Snow-and-ice control-plan activation | 공항 제설·제빙 계획 활성화 화면으로 가 줘 / Take me to activate the airport snow-and-ice control plan |
| C | `airport_airside_operations.wildlife_strike_report` | 야생동물 충돌 보고 / Wildlife-strike report | 항공기 야생동물 충돌을 보고하러 가 줘 / Take me to report the aircraft wildlife strike |
| C | `airport_airside_operations.wildlife_mitigation_record` | 야생동물 완화조치 기록 / Wildlife-mitigation record | 에어사이드 야생동물 완화조치를 기록해 둘 화면을 열어 줘 / Open the screen to record airside wildlife mitigation |
| C | `airport_airside_operations.lighting_signage_outage_record` | 등화·표지 장애 기록 / Lighting-and-signage outage record | 활주로 등화 장애를 기록하는 곳으로 가 줘 / Take me to record the runway-light outage |
| C | `airport_airside_operations.movement_area_work_closure_request` | 이동지역 작업폐쇄 요청 / Movement-area work-closure request | 유도로 작업구역 폐쇄를 요청하는 화면으로 가 줘 / Take me to request the taxiway work-area closure |
| C | `airport_airside_operations.construction_safety_phase_approve` | 공사 안전단계 승인 / Construction safety-phase approval | 에어사이드 공사 안전단계를 승인하는 곳으로 가 줘 / Take me to the airside construction safety-phase approval |
| C | `airport_airside_operations.vehicle_access_permit_issue` | 에어사이드 차량출입 허가 발급 / Airside vehicle-access permit issue | 이동지역 차량출입 허가를 발급하는 화면을 열어 줘 / Open the movement-area vehicle permit issue screen |
| C | `airport_airside_operations.arff_drill_readiness_certify` | 구조소방 훈련 준비 인증 / ARFF drill-readiness certification | ARFF 훈련 준비 상태를 인증하는 곳으로 가 줘 / Take me to certify ARFF drill readiness |
| C | `airport_airside_operations.airport_emergency_plan_activate` | 공항 비상계획 활성화 / Airport emergency-plan activation | 해당 공항 비상계획 활성화 화면으로 가 줘 / Take me to the airport emergency-plan activation screen |

Roles/assets/states: airport operations manager, airport certification specialist, airfield inspector, wildlife coordinator, and ARFF chief; airport certificate/manual, runway, taxiway, pavement, lighting/signage, FOD, wildlife plan, response capability; `compliant/deficient/corrected`, `open/restricted/closed`, `dry/contaminated`, and `ready/degraded/activated`.

Boundary and collision guard: this domain owns the airport operator's certified movement area. It excludes aircraft maintenance (`aviation_maintenance_ops`), flightcrew duty (`airline_crew_operations`), ATC clearance and NOTAM control (`air_traffic_control_ops`), and field incident command (`emergency_response_operations`). A bare “runway,” “inspection,” “closure,” or “emergency” must not select it.

Primary-source seed pack:

1. eCFR, [14 CFR Part 139 — Certification of Airports](https://www.ecfr.gov/current/title-14/chapter-I/subchapter-G/part-139).
2. FAA, [AC 150/5200-18D — Airport Safety Self-Inspection](https://www.faa.gov/airports/resources/advisory_circulars/index.cfm/go/document.current/documentnumber/150_5200-18).
3. FAA, [Takeoff and Landing Performance Assessment for airport operators](https://www.faa.gov/about/initiatives/talpa).
4. FAA, [Wildlife Regulations, Guidance, and Resources](https://www.faa.gov/airports/airport_safety/wildlife/resources).
5. FAA, [AC 150/5370-2G — Operational Safety on Airports During Construction](https://www.faa.gov/airports/resources/advisory_circulars/index.cfm/go/document.current/documentNumber/150_5370-2).
6. FAA, [AC 150/5210-20A — Ground Vehicle Operations to Include Taxiing or Towing an Aircraft on Airports](https://www.faa.gov/airports/resources/advisory_circulars/index.cfm/go/document.current/documentNumber/150_5210-20/).
7. FAA, [AC 150/5200-31C — Airport Emergency Plan](https://www.faa.gov/airports/resources/advisory_circulars/index.cfm/go/document.current/documentNumber/150_5200-31).
8. FAA, [AC 150/5210-17C — Programs for Training of Aircraft Rescue and Firefighting Personnel](https://www.faa.gov/airports/resources/advisory_circulars/index.cfm/go/document.current/documentNumber/150_5210-17).

Terminal evidence map: sources 1–2 support `airport_airside_operations.airport_certificate_status`, `airport_airside_operations.certification_manual_review`, `airport_airside_operations.movement_area_condition_queue`, `airport_airside_operations.pavement_condition_status`, `airport_airside_operations.lighting_marking_sign_status`, `airport_airside_operations.daily_self_inspection_record`, `airport_airside_operations.discrepancy_risk_classify`, `airport_airside_operations.foreign_object_debris_report`, and `airport_airside_operations.lighting_signage_outage_record`; sources 1 and 3 support `airport_airside_operations.runway_condition_code_issue` and `airport_airside_operations.snow_ice_control_plan_activate`; sources 1 and 4 support `airport_airside_operations.wildlife_hazard_plan_status`, `airport_airside_operations.wildlife_strike_report`, and `airport_airside_operations.wildlife_mitigation_record`; source 5 supports `airport_airside_operations.movement_area_work_closure_request` and `airport_airside_operations.construction_safety_phase_approve`; sources 1 and 6 support `airport_airside_operations.vehicle_access_permit_issue`; sources 1, 7, and 8 support `airport_airside_operations.arff_readiness_status`, `airport_airside_operations.arff_drill_readiness_certify`, and `airport_airside_operations.airport_emergency_plan_activate`. The cited Part 139 duties and active FAA circulars identify the certificate holder/airport operator, authorized inspection, construction, vehicle, wildlife, and ARFF roles and the compliant→deficient→corrected, open→restricted/closed, dry→contaminated→coded, and ready→degraded→activated transitions.

## 2. Federal records disposition operations (`federal_records_disposition_ops`)

Hub: `federal_records_disposition_ops.hub` — 연방기록 처분 운영 / Federal records disposition operations

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `federal_records_disposition_ops.records_series_inventory` | 기록시리즈 목록 / Records-series inventory | 이 기관의 기록시리즈와 책임 부서를 보여 줘 / Show this agency's records series and responsible offices |
| S | `federal_records_disposition_ops.approved_disposition_authority` | 승인 처분권한 조회 / Approved disposition-authority view | 이 기록시리즈에 적용되는 NARA 승인 처분권한을 열어 줘 / Open the NARA-approved disposition authority for this records series |
| S | `federal_records_disposition_ops.unscheduled_records_queue` | 처분일정 미승인 기록 작업함 / Unscheduled-records queue | 아직 승인된 처분일정이 없는 기록을 보여 줘 / Show records that do not yet have an approved disposition schedule |
| S | `federal_records_disposition_ops.retention_cutoff_status` | 보존기간·기산 상태 / Retention-and-cutoff status | 이 기록의 기산일과 보존기간 진행 상태를 보여 줘 / Show the cutoff date and retention progress for this record set |
| S | `federal_records_disposition_ops.disposition_hold_status` | 기록 처분중지 상태 / Records-disposition hold status | 이 기록시리즈의 소송·조사 처분중지 상태를 확인해 줘 / Show litigation or investigation disposition holds on this records series |
| S | `federal_records_disposition_ops.temporary_disposition_eligibility` | 임시기록 처분적격 상태 / Temporary-record disposition eligibility | 이 임시기록이 승인된 폐기일에 도달했는지 보여 줘 / Show whether these temporary records reached their approved disposal date |
| S | `federal_records_disposition_ops.permanent_transfer_status` | 영구기록 이관 상태 / Permanent-record transfer status | 이 영구기록의 NARA 이관과 법적 보관권 상태를 보여 줘 / Show the NARA transfer and legal-custody status for these permanent records |
| C | `federal_records_disposition_ops.records_schedule_create` | 기록 처분일정 생성 / Records-schedule creation | 미승인 기록시리즈의 처분일정 초안을 만드는 화면으로 가 줘 / Take me to create a disposition-schedule draft for the unscheduled series |
| C | `federal_records_disposition_ops.schedule_item_update` | 처분일정 항목 갱신 / Schedule-item update | 기록시리즈의 보존·처분 항목을 갱신하는 곳으로 가 줘 / Take me to update the retention and disposition item for this records series |
| C | `federal_records_disposition_ops.records_schedule_submit` | 기록 처분일정 제출 / Records-schedule submission | 기관 기록관이 검토한 처분일정을 NARA에 제출하는 화면으로 가 줘 / Take me to submit the agency-records-officer-reviewed schedule to NARA |
| C | `federal_records_disposition_ops.schedule_revision_submit` | 처분일정 개정 제출 / Schedule-revision submission | 기존 처분권한의 개정안을 NARA에 제출하는 곳으로 가 줘 / Take me to submit the revision of the existing disposition authority to NARA |
| C | `federal_records_disposition_ops.file_cutoff_record` | 파일 기산종료 기록 / File-cutoff record | 닫힌 파일 집합의 보존기간 기산을 시작하도록 기록해 줘 / Take me to record cutoff and start retention for the closed file set |
| C | `federal_records_disposition_ops.disposition_hold_apply` | 기록 처분중지 적용 / Disposition-hold application | 법무 승인을 받은 소송보존 중지를 이 기록에 적용하는 화면으로 가 줘 / Take me to apply the counsel-approved litigation hold to these records |
| C | `federal_records_disposition_ops.disposition_hold_release` | 기록 처분중지 해제 / Disposition-hold release | 법무 해제 승인을 확인하고 이 기록의 처분중지를 해제하는 곳으로 가 줘 / Take me to release the records hold after confirming counsel authorization |
| C | `federal_records_disposition_ops.temporary_disposition_approve` | 임시기록 처분 승인 / Temporary-record disposition approval | 승인 일정과 보존중지 여부를 검증한 임시기록 처분을 승인하는 화면으로 가 줘 / Take me to approve disposal after validating the schedule and absence of a hold |
| C | `federal_records_disposition_ops.temporary_records_destroy_certify` | 임시기록 파기 인증 / Temporary-record destruction certification | 승인된 임시기록 파기 완료를 인증하는 곳으로 가 줘 / Take me to certify completed destruction of the authorized temporary records |
| C | `federal_records_disposition_ops.permanent_transfer_offer_create` | 영구기록 이관제안 생성 / Permanent-record transfer-offer creation | 이관적격 영구기록의 NARA 이관제안을 만드는 화면으로 가 줘 / Take me to create the NARA transfer offer for eligible permanent records |
| C | `federal_records_disposition_ops.transfer_restriction_record` | 영구기록 이용제한 기록 / Transfer-restriction record | 영구기록 이관서에 법정 이용제한과 근거를 기록하는 곳으로 가 줘 / Take me to record statutory access restrictions and their basis on the transfer |
| C | `federal_records_disposition_ops.legal_custody_transfer_accept` | NARA 법적 보관권 이관 수락 / NARA legal-custody transfer acceptance | NARA 인수 권한자가 영구기록 수령을 확인하고 법적 보관권 이관을 수락하는 화면으로 가 줘 / Take me to the NARA official's acceptance of receipt and legal-custody transfer |
| C | `federal_records_disposition_ops.unauthorized_disposition_report` | 무단 기록처분 보고 / Unauthorized-records-disposition report | 분실·무단파기 의심 기록을 기관 기록관과 NARA에 보고하는 화면으로 가 줘 / Take me to report suspected loss or unauthorized destruction to the agency records officer and NARA |

Roles/assets/states: senior agency official for records management, agency records officer, records liaison, records custodian, agency counsel, NARA appraiser, and NARA accessioning official; Federal record, records series/system, file cutoff, disposition schedule/item, legal or investigation hold, temporary-record disposal batch, permanent-record transfer offer, and transfer restriction; `identified/unscheduled/draft/submitted/approved/superseded`, `active/cutoff/retention-running/eligible/held/released/destroyed`, `offer-draft/submitted/accepted/custody-transferred`, and `suspected/reported/resolved`.

Boundary and collision guard: this domain governs disposition authority for Federal agency records under NARA jurisdiction. It excludes ordinary cloud-file deletion (`documents_cloud`), litigation-work-product review (`legal_practice_ops`), museum collection accession (`museum_collections_ops`), and consumer privacy deletion (`privacy`). `record`, `file`, `hold`, `schedule`, `transfer`, and `delete` require a Federal agency, a records series, a NARA-approved or pending disposition authority, and its current retention/hold/transfer state.

Primary-source seed pack:

1. eCFR, [36 CFR Part 1222 — Creation and Maintenance of Federal Records](https://www.ecfr.gov/current/title-36/chapter-XII/subchapter-B/part-1222).
2. eCFR, [36 CFR Part 1224 — Records Disposition Programs](https://www.ecfr.gov/current/title-36/chapter-XII/subchapter-B/part-1224).
3. eCFR, [36 CFR Part 1225 — Scheduling Records](https://www.ecfr.gov/current/title-36/chapter-XII/subchapter-B/part-1225).
4. eCFR, [36 CFR Part 1226 — Implementing Disposition](https://www.ecfr.gov/current/title-36/chapter-XII/subchapter-B/part-1226).
5. eCFR, [36 CFR Part 1230 — Unlawful or Accidental Removal, Defacing, Alteration, or Destruction of Records](https://www.ecfr.gov/current/title-36/chapter-XII/subchapter-B/part-1230).
6. eCFR, [36 CFR Part 1235 — Transfer of Records to the National Archives of the United States](https://www.ecfr.gov/current/title-36/chapter-XII/subchapter-B/part-1235).
7. National Archives, [Guide to the Inventory, Scheduling, and Disposition of Federal Records](https://www.archives.gov/records-mgmt/scheduling).
8. National Archives, [Accessioning Guidance and Policy](https://www.archives.gov/records-mgmt/accessioning).

Terminal evidence map: sources 1–2 support `federal_records_disposition_ops.records_series_inventory`; sources 2–4 and 7 support `federal_records_disposition_ops.approved_disposition_authority`, `federal_records_disposition_ops.unscheduled_records_queue`, `federal_records_disposition_ops.retention_cutoff_status`, `federal_records_disposition_ops.disposition_hold_status`, `federal_records_disposition_ops.temporary_disposition_eligibility`, `federal_records_disposition_ops.records_schedule_create`, `federal_records_disposition_ops.schedule_item_update`, `federal_records_disposition_ops.records_schedule_submit`, `federal_records_disposition_ops.schedule_revision_submit`, `federal_records_disposition_ops.file_cutoff_record`, `federal_records_disposition_ops.disposition_hold_apply`, `federal_records_disposition_ops.disposition_hold_release`, `federal_records_disposition_ops.temporary_disposition_approve`, and `federal_records_disposition_ops.temporary_records_destroy_certify`; source 5 supports `federal_records_disposition_ops.unauthorized_disposition_report`; sources 6 and 8 support `federal_records_disposition_ops.permanent_transfer_status`, `federal_records_disposition_ops.permanent_transfer_offer_create`, `federal_records_disposition_ops.transfer_restriction_record`, and `federal_records_disposition_ops.legal_custody_transfer_accept`. The mapped provisions assign agency-records-officer, counsel, Archivist/NARA-appraiser, and NARA-accepting-official authority and distinguish unscheduled→submitted→approved, active→cutoff→eligible, unheld→held→released, eligible→destroyed, and offered→accepted→custody-transferred states.

## 3. DOJ FOIA case processing (`doj_foia_case_processing`)

Hub: `doj_foia_case_processing.hub` — 법무부 FOIA 사건처리 / DOJ FOIA case processing

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `doj_foia_case_processing.request_intake_queue` | FOIA 요청 접수 작업함 / FOIA-request intake queue | 새로 도착한 DOJ FOIA 요청 작업함을 보여 줘 / Show the newly received DOJ FOIA-request queue |
| S | `doj_foia_case_processing.request_case_status` | FOIA 요청 사건상태 / FOIA-request case status | 이 DOJ FOIA 요청의 추적번호와 처리단계를 보여 줘 / Show the tracking number and processing stage for this DOJ FOIA request |
| S | `doj_foia_case_processing.scope_fee_status` | 요청범위·수수료 상태 / Request-scope and fee status | 확정된 검색범위와 요청자 수수료 범주를 열어 줘 / Open the settled search scope and requester fee category |
| S | `doj_foia_case_processing.expedited_processing_status` | 신속처리 상태 / Expedited-processing status | 이 요청의 신속처리 결정과 전용 트랙 상태를 보여 줘 / Show the expedited-processing decision and priority-track status |
| S | `doj_foia_case_processing.search_task_status` | 보유기록 검색작업 상태 / Responsive-record search-task status | 보유 부서별 FOIA 검색작업 완료 상태를 보여 줘 / Show completion status of each custodial FOIA search task |
| S | `doj_foia_case_processing.consultation_referral_status` | 협의·이송 상태 / Consultation-and-referral status | 다른 부서·기관으로 보낸 기록 협의와 이송 상태를 보여 줘 / Show consultation and referral status for records sent to other components or agencies |
| S | `doj_foia_case_processing.disclosure_review_status` | 공개검토 상태 / Disclosure-review status | 응답기록의 예외적용·분리가능성 검토 상태를 열어 줘 / Open exemption and reasonably-segregable review status for the responsive records |
| C | `doj_foia_case_processing.request_log_assign` | FOIA 요청 등록·배정 / FOIA-request logging and assignment | 유효한 요청에 추적번호를 부여하고 처리담당자를 배정하는 화면으로 가 줘 / Take me to assign a tracking number and processor to the valid request |
| C | `doj_foia_case_processing.scope_clarification_issue` | 요청범위 보완요청 발송 / Scope-clarification issuance | 합리적 검색이 가능하도록 요청자에게 범위 보완요청을 보내는 곳으로 가 줘 / Take me to issue a clarification request so the records can be reasonably searched |
| C | `doj_foia_case_processing.fee_category_determine` | FOIA 수수료범주 결정 / FOIA fee-category determination | 요청자의 상업·교육·보도·기타 수수료범주를 결정하는 화면으로 가 줘 / Take me to determine the requester's commercial, educational, news-media, or other fee category |
| C | `doj_foia_case_processing.fee_waiver_decide` | FOIA 수수료면제 결정 / FOIA fee-waiver decision | 공익과 상업적 이해 기준으로 수수료면제를 승인 또는 거절하는 곳으로 가 줘 / Take me to grant or deny the fee waiver under public-interest and commercial-interest criteria |
| C | `doj_foia_case_processing.expedited_processing_decide` | 신속처리 결정 / Expedited-processing decision | 권한자가 인증된 긴급성 근거로 신속처리를 승인 또는 거절하는 화면으로 가 줘 / Take me to the authorized grant-or-deny decision on certified expedition grounds |
| C | `doj_foia_case_processing.search_task_issue` | 보유부서 검색작업 발행 / Custodial search-task issuance | 확정된 범위와 기준일로 보유부서에 기록검색 작업을 발행하는 곳으로 가 줘 / Take me to issue the custodial record search with the settled scope and cutoff date |
| C | `doj_foia_case_processing.consultation_initiate` | 타기관 공개협의 개시 / Disclosure consultation initiation | 타 부서 정보가 포함된 기록의 공개의견 협의를 개시하는 화면으로 가 줘 / Take me to initiate disclosure consultation for a record containing another component's information |
| C | `doj_foia_case_processing.record_referral_transfer` | FOIA 기록 이송 / FOIA-record referral transfer | 원 생성기관에 응답책임을 이송하고 요청자에게 통지하는 곳으로 가 줘 / Take me to transfer response responsibility to the originating agency and notify the requester |
| C | `doj_foia_case_processing.submitter_notice_issue` | 기밀 상업정보 제출자통지 / Confidential-commercial-information submitter notice | 공개 가능성이 있는 기밀 상업정보의 제출자에게 통지하는 화면으로 가 줘 / Take me to notify the submitter that confidential commercial information may be disclosed |
| C | `doj_foia_case_processing.exemption_redaction_apply` | FOIA 예외·삭제 적용 / FOIA exemption-and-redaction application | 공개검토자가 승인한 예외조항과 삭제표시를 응답기록에 적용하는 곳으로 가 줘 / Take me to apply reviewer-approved exemptions and deletion markings to responsive records |
| C | `doj_foia_case_processing.disclosure_release_authorize` | FOIA 공개응답 방출승인 / FOIA disclosure-release authorization | 구성기관 장 또는 위임자가 전부·부분공개 응답 방출을 승인하는 화면으로 가 줘 / Take me to the component head or designee's authorization to release the full or partial response |
| C | `doj_foia_case_processing.adverse_determination_issue` | FOIA 불리결정 발행 / FOIA adverse-determination issuance | 권한자 서명과 예외·이의제기 근거를 포함한 불리결정을 발행하는 곳으로 가 줘 / Take me to issue the authorized adverse determination with exemption and appeal grounds |
| C | `doj_foia_case_processing.administrative_appeal_decide` | FOIA 행정이의 결정 / FOIA administrative-appeal decision | OIP 권한자가 기한 내 행정이의를 인용·기각·부분인용하는 화면으로 가 줘 / Take me to the OIP-authorized grant, denial, or partial grant of the timely administrative appeal |

Roles/assets/states: DOJ component head or designee, component FOIA officer, FOIA processor, records custodian, disclosure reviewer, fee-waiver decision maker, submitter-notice coordinator, and Office of Information Policy appeal adjudicator; FOIA request/tracking number, requester and fee category, scope/cutoff date, search task, responsive record, consultation/referral, exemption/redaction, release package, adverse determination, and administrative appeal; `received/perfected/clarification-pending/assigned`, `simple/complex/expedited`, `search-open/search-complete`, `consultation-pending/referred/returned`, `review-pending/full-grant/partial-grant/denied/released`, and `appeal-pending/affirmed/remanded/modified/closed`.

Boundary and collision guard: this domain is the DOJ component/OIP processing lifecycle under 28 CFR Part 16. It excludes generic customer tickets (`customer_support_agent`), litigation discovery (`legal_practice_ops`), court-file access (`court_clerk_case_admin`), and personal privacy-setting changes (`privacy`). `request`, `case`, `search`, `fee`, `review`, `release`, and `appeal` require a DOJ FOIA tracking number, responsible component, authorized FOIA role, and current statutory processing state.

Primary-source seed pack:

1. eCFR, [28 CFR Part 16 Subpart A — Procedures for Disclosure of Records Under the Freedom of Information Act](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A).
2. eCFR, [28 CFR § 16.3 — Requirements for Making Requests](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.3).
3. eCFR, [28 CFR § 16.4 — Responsibility for Responding to Requests](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.4).
4. eCFR, [28 CFR § 16.5 — Timing of Responses to Requests](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.5).
5. eCFR, [28 CFR § 16.6 — Responses to Requests](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.6).
6. eCFR, [28 CFR § 16.7 — Confidential Commercial Information](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.7).
7. eCFR, [28 CFR § 16.8 — Administrative Appeals](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.8).
8. eCFR, [28 CFR § 16.10 — Fees](https://www.ecfr.gov/current/title-28/chapter-I/part-16/subpart-A/section-16.10).

Terminal evidence map: sources 1–2 and 5 support `doj_foia_case_processing.request_intake_queue`, `doj_foia_case_processing.request_case_status`, `doj_foia_case_processing.request_log_assign`, and `doj_foia_case_processing.scope_clarification_issue`; sources 4 and 8 support `doj_foia_case_processing.scope_fee_status`, `doj_foia_case_processing.expedited_processing_status`, `doj_foia_case_processing.fee_category_determine`, `doj_foia_case_processing.fee_waiver_decide`, and `doj_foia_case_processing.expedited_processing_decide`; source 3 supports `doj_foia_case_processing.search_task_status`, `doj_foia_case_processing.consultation_referral_status`, `doj_foia_case_processing.search_task_issue`, `doj_foia_case_processing.consultation_initiate`, and `doj_foia_case_processing.record_referral_transfer`; sources 3 and 5 support `doj_foia_case_processing.disclosure_review_status`, `doj_foia_case_processing.exemption_redaction_apply`, `doj_foia_case_processing.disclosure_release_authorize`, and `doj_foia_case_processing.adverse_determination_issue`; source 6 supports `doj_foia_case_processing.submitter_notice_issue`; source 7 supports `doj_foia_case_processing.administrative_appeal_decide`. Those provisions expressly identify the component head/designee and OIP appeal authority and the received→perfected, ordinary→expedited, open→complete, consultation→referral, review→release/denial, and appeal→affirm/remand/modify transitions.

## 4. Dam-safety operations (`dam_safety_operations`)

Hub: `dam_safety_operations.hub` — 댐 안전운영 / Dam-safety operations

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `dam_safety_operations.hazard_classification_view` | 댐 위험등급 조회 / Dam hazard-classification view | 이 댐의 위험잠재등급을 보여 줘 / Show this dam's hazard-potential classification |
| S | `dam_safety_operations.reservoir_level_trend` | 저수위 추세 / Reservoir-level trend | 저수지 수위와 급변 추세를 열어 줘 / Open the reservoir level and rapid-change trend |
| S | `dam_safety_operations.instrumentation_health_status` | 계측기 건전성 상태 / Instrumentation-health status | 댐 안전계측기 건전성 상태를 확인해 줘 / Show dam-safety instrumentation health |
| S | `dam_safety_operations.seepage_deformation_trend` | 누수·변형 추세 / Seepage-and-deformation trend | 누수와 변형 관측 추세를 보여 줘 / Show the seepage and deformation trend |
| S | `dam_safety_operations.spillway_gate_status` | 여수로·수문 상태 / Spillway-and-gate status | 여수로와 방류수문 상태를 확인해 줘 / Show spillway and release-gate status |
| S | `dam_safety_operations.surveillance_inspection_queue` | 순찰·점검 작업함 / Surveillance-inspection queue | 기한이 도래한 댐 안전점검을 보여 줘 / Show due dam-safety surveillance inspections |
| S | `dam_safety_operations.eap_readiness_status` | 비상조치계획 준비 상태 / EAP readiness status | 이 댐 비상조치계획의 준비 상태를 열어 줘 / Open this dam's emergency-action-plan readiness |
| C | `dam_safety_operations.surveillance_inspection_record` | 안전순찰 점검 기록 / Safety-surveillance inspection record | 오늘 댐 안전순찰을 기록하는 곳으로 가 줘 / Take me to record today's dam-safety surveillance |
| C | `dam_safety_operations.instrument_reading_certify` | 안전계측값 인증 / Instrument-reading certification | 검토한 댐 계측값을 인증하는 화면으로 가 줘 / Take me to certify the reviewed dam instrument readings |
| C | `dam_safety_operations.anomalous_condition_classify` | 이상상태 분류 / Anomalous-condition classification | 비정상 누수의 안전등급을 분류하는 곳으로 가 줘 / Take me to classify the abnormal seepage condition |
| C | `dam_safety_operations.reservoir_restriction_issue` | 저수지 운용제한 발행 / Reservoir-operating restriction issue | 안전을 위한 저수위 운용제한을 발행하는 화면으로 가 줘 / Take me to issue the safety reservoir restriction |
| C | `dam_safety_operations.gate_operation_authorize` | 방류수문 조작 승인 / Release-gate operation authorization | 해당 방류수문 조작 승인 화면을 열어 줘 / Open the release-gate operation authorization |
| C | `dam_safety_operations.safety_isolation_issue` | 안전 격리 발행 / Safety-isolation issue | 댐 부속설비 안전격리를 발행하는 곳으로 가 줘 / Take me to issue the dam-appurtenance safety isolation |
| C | `dam_safety_operations.corrective_action_approve` | 시정조치 승인 / Corrective-action approval | 댐 안전 시정조치를 승인하는 화면으로 가 줘 / Take me to approve the dam-safety corrective action |
| C | `dam_safety_operations.risk_reduction_measure_record` | 위험저감조치 기록 / Risk-reduction-measure record | 임시 위험저감조치를 기록하는 곳으로 가 줘 / Take me to record the interim risk-reduction measure |
| C | `dam_safety_operations.eap_emergency_level_declare` | EAP 비상단계 선언 / EAP emergency-level declaration | 이 댐의 EAP 비상단계를 선언하는 화면으로 가 줘 / Take me to declare this dam's EAP emergency level |
| C | `dam_safety_operations.warning_system_activate` | 경보체계 활성화 / Warning-system activation | 댐 하류 경보체계를 활성화하는 곳으로 가 줘 / Take me to activate the downstream warning system |
| C | `dam_safety_operations.downstream_notification_release` | 하류기관 통보 발신 / Downstream notification release | 하류 비상기관 통보를 발신하는 화면으로 가 줘 / Take me to release the downstream emergency notification |
| C | `dam_safety_operations.safety_incident_report_submit` | 댐 안전사건 보고 제출 / Dam-safety incident-report submission | 규제기관에 댐 안전사건을 보고하는 곳으로 가 줘 / Take me to submit the dam-safety incident report |
| C | `dam_safety_operations.return_to_normal_authorize` | 정상단계 복귀 승인 / Return-to-normal authorization | EAP 정상단계 복귀 승인 화면으로 가 줘 / Take me to authorize EAP return to normal |

Roles/assets/states: dam-safety engineer, owner/operator, instrumentation engineer, independent consultant, emergency coordinator, and regulator liaison; dam/project works, reservoir, spillway/gate, embankment, instrumentation point, potential failure mode, EAP and inundation area; `normal/advisory/watch/emergency`, `stable/anomalous/unsafe`, `open/restricted/isolated`, and `identified/mitigated/closed`.

Boundary and collision guard: this is structural and public-safety control of a dam and impoundment. It excludes treatment-process control (`water_wastewater_plant_ops`), generating-unit dispatch (`power_generation_plant_ops`), distribution switching (`utility_grid_field_ops`), and responder resource command (`emergency_response_operations`). A bare “gate,” “level,” “inspection,” “isolation,” or “incident” must abstain.

Primary-source seed pack:

1. eCFR, [18 CFR Part 12 — Safety of Water Power Projects and Project Works](https://www.ecfr.gov/current/title-18/chapter-I/subchapter-B/part-12).
2. FERC, [Dam Safety and Inspections](https://www.ferc.gov/dam-safety-and-inspections).
3. FERC, [Emergency Action Plan Program](https://www.ferc.gov/emergency-action-plan-eap-program).
4. FEMA, [Federal Guidelines for Dam Safety](https://www.fema.gov/sites/default/files/documents/fema_rm-federal-guidelines-for-dam-safety.pdf).
5. FERC, [Engineering Guidelines for the Evaluation of Hydropower Projects](https://www.ferc.gov/industries-data/hydropower/dam-safety-and-inspections/eng-guidelines).
6. FERC, [Engineering Guidelines Chapter 9 — Instrumentation and Monitoring](https://www.ferc.gov/sites/default/files/2020-04/chap9.pdf).
7. FERC, [Engineering Guidelines Chapter 14 — Dam Safety Performance Monitoring Program](https://www.ferc.gov/sites/default/files/2020-04/chap14.pdf).
8. FERC, [Engineering Guidelines Chapter 6 — Emergency Action Plans](https://www.ferc.gov/sites/default/files/2020-04/chap6.pdf).
9. FERC, [Testing and Reporting on Spillway Gate Operations](https://www.ferc.gov/sites/default/files/2020-04/spillway-gate-information.pdf).
10. Bureau of Reclamation, [Standing Operating Procedures Guide for Dams, Reservoirs, and Power Facilities](https://www.usbr.gov/assetmanagement/docs/SOPGuidelines-Jun2001.pdf).

Terminal evidence map: sources 1–2 and 4 support `dam_safety_operations.hazard_classification_view`, `dam_safety_operations.surveillance_inspection_queue`, `dam_safety_operations.safety_isolation_issue`, `dam_safety_operations.corrective_action_approve`, and `dam_safety_operations.safety_incident_report_submit`; sources 5–7 support `dam_safety_operations.reservoir_level_trend`, `dam_safety_operations.instrumentation_health_status`, `dam_safety_operations.seepage_deformation_trend`, `dam_safety_operations.surveillance_inspection_record`, `dam_safety_operations.instrument_reading_certify`, `dam_safety_operations.anomalous_condition_classify`, and `dam_safety_operations.risk_reduction_measure_record`; sources 7, 9, and 10 support `dam_safety_operations.spillway_gate_status`, `dam_safety_operations.reservoir_restriction_issue`, and `dam_safety_operations.gate_operation_authorize`; sources 3, 5, and 8 support `dam_safety_operations.eap_readiness_status`, `dam_safety_operations.eap_emergency_level_declare`, `dam_safety_operations.warning_system_activate`, `dam_safety_operations.downstream_notification_release`, and `dam_safety_operations.return_to_normal_authorize`. The mapped regulations and operating/EAP manuals identify licensee, dam-safety engineer, operator, independent consultant, and emergency-coordinator authority and the stable→anomalous→unsafe, normal→restricted/isolated, and normal→advisory/watch/emergency→return-to-normal transitions; source 10 is limited to Bureau of Reclamation assets and does not establish authority for a FERC or non-Federal dam.

## 5. NLRB representation-case operations (`nlrb_representation_case_ops`)

Hub: `nlrb_representation_case_ops.hub` — NLRB 노동대표 선거사건 운영 / NLRB representation-case operations

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `nlrb_representation_case_ops.petition_case_queue` | 노동대표 청원 사건함 / Representation-petition case queue | 해당 NLRB 지역사무소의 새 대표권 청원 사건을 보여 줘 / Show new representation petitions for this NLRB Regional Office |
| S | `nlrb_representation_case_ops.case_party_profile` | 대표권 사건 당사자 프로필 / Representation-case party profile | 이 사건의 사용자·청원인·노동조합과 송달대표를 열어 줘 / Open the employer, petitioner, labor organizations, and service representatives for this case |
| S | `nlrb_representation_case_ops.bargaining_unit_scope_view` | 교섭단위 범위 조회 / Bargaining-unit scope view | 청원된 교섭단위의 시설·직무·인원 범위를 보여 줘 / Show the facilities, classifications, and headcount in the petitioned-for unit |
| S | `nlrb_representation_case_ops.showing_interest_status` | 노동자 관심표시 상태 / Showing-of-interest status | 대외 비공개 상태로 검증된 관심표시 충족 여부만 보여 줘 / Show only whether the confidential showing of interest was administratively sufficient |
| S | `nlrb_representation_case_ops.hearing_schedule_status` | 선거전 심문 일정상태 / Pre-election hearing schedule status | 이 사건의 심문통지·위치·일정 상태를 보여 줘 / Show notice, location, and schedule status for this case's hearing |
| S | `nlrb_representation_case_ops.election_arrangement_status` | 노동대표 선거준비 상태 / Representation-election arrangement status | 합의 또는 결정된 선거 방식·일시·장소와 유권자명부 상태를 보여 줘 / Show the agreed or directed election method, time, place, and voter-list status |
| S | `nlrb_representation_case_ops.tally_objection_status` | 개표·이의·인증 상태 / Tally, objection, and certification status | 개표결과와 이의·도전표·인증 처리 상태를 보여 줘 / Show the tally and the status of objections, challenged ballots, and certification |
| C | `nlrb_representation_case_ops.petition_docket` | 노동대표 청원 접수등재 / Representation-petition docketing | 서명·송달이 확인된 RC 청원을 해당 NLRB 지역사무소에 등재하는 화면으로 가 줘 / Take me to docket the signed and served RC petition in the proper NLRB Region |
| C | `nlrb_representation_case_ops.petition_amendment_record` | 대표권 청원 정정기록 / Representation-petition amendment record | 청원인의 검증된 교섭단위 정정을 사건에 기록하는 곳으로 가 줘 / Take me to record the petitioner's verified bargaining-unit amendment |
| C | `nlrb_representation_case_ops.petition_withdrawal_approve` | 대표권 청원 철회승인 / Representation-petition withdrawal approval | 지역국장 또는 위원회 권한으로 청원 철회와 사건종결을 승인하는 화면으로 가 줘 / Take me to the Regional Director or Board approval of petition withdrawal and case closure |
| C | `nlrb_representation_case_ops.regional_investigation_assign` | 지역 조사관 배정 / Regional-investigation assignment | 지역국장 권한으로 청원 조사를 수행할 Board agent를 배정하는 곳으로 가 줘 / Take me to the Regional Director's assignment of a Board agent to investigate the petition |
| C | `nlrb_representation_case_ops.bargaining_unit_stipulation_record` | 교섭단위 합의기록 / Bargaining-unit stipulation record | 당사자가 합의한 적정 교섭단위와 선거자격 기준을 기록하는 화면으로 가 줘 / Take me to record the parties' stipulated appropriate unit and voter-eligibility criteria |
| C | `nlrb_representation_case_ops.hearing_notice_issue` | 선거전 심문통지 발행 / Pre-election hearing-notice issuance | 지역국장이 조사 후 심문통지와 청원통지를 당사자에게 발행하는 곳으로 가 줘 / Take me to the Regional Director's issuance of the hearing and petition notices after investigation |
| C | `nlrb_representation_case_ops.pre_election_decision_issue` | 선거전 결정 발행 / Pre-election decision issuance | 심문기록으로 대표문제와 교섭단위를 결정하고 선거를 명하는 화면으로 가 줘 / Take me to issue the record-based decision on the representation question and direction of election |
| C | `nlrb_representation_case_ops.election_agreement_approve` | 대표권 선거합의 승인 / Representation-election agreement approval | 지역국장이 당사자의 선거합의서를 승인하는 화면으로 가 줘 / Take me to the Regional Director's approval of the parties' election agreement |
| C | `nlrb_representation_case_ops.voter_list_submit` | 선거 유권자명부 제출 / Election voter-list submission | 사용자 권한자가 결정된 기한과 형식으로 최종 유권자명부를 제출하는 곳으로 가 줘 / Take me to the authorized employer submission of the final voter list in the required time and format |
| C | `nlrb_representation_case_ops.election_schedule_authorize` | 노동대표 선거일정 확정 / Representation-election scheduling authorization | 지역국장이 선거 방식·일시·장소와 투표자격 기준을 확정하는 화면으로 가 줘 / Take me to the Regional Director's authorization of election method, time, place, and eligibility rules |
| C | `nlrb_representation_case_ops.challenged_ballot_record` | 도전표 기록 / Challenged-ballot record | Board agent가 유권자 자격 이의를 도전표로 기록하는 화면으로 가 줘 / Take me to the Board agent's record of a voter-eligibility challenge and challenged ballot |
| C | `nlrb_representation_case_ops.election_objection_intake` | 선거이의 접수 / Election-objection intake | 기한 내 제출된 선거진행·결과 영향 이의와 증거제안을 접수하는 곳으로 가 줘 / Take me to intake timely objections to election conduct or results with the supporting offer of proof |
| C | `nlrb_representation_case_ops.certification_issue` | 노동대표 선거결과 인증 발행 / Representation-election certification issuance | 주요 도전표와 이의를 해결한 후 지역국장이 대표자 또는 선거결과 인증을 발행하는 화면으로 가 줘 / Take me to the Regional Director's certification after resolving determinative challenges and objections |

Roles/assets/states: Regional Director, hearing officer, Board agent/field examiner, election supervisor, authorized employer representative, petitioner representative, and labor-organization representative; representation petition/case, parties and service record, showing of interest, bargaining unit, hearing notice/record, election agreement or direction, voter list, ballot/challenge, tally, objection, and certification; `filed/amended/withdrawal-pending/withdrawn/dismissed`, `investigating/hearing/decision-issued`, `stipulated/directed/election-scheduled`, `voter-listed/challenged/resolved`, and `tally-issued/objection-pending/certified/set-aside/closed`.

Boundary and collision guard: this domain governs NLRB Section 9 representation petitions and employee-representation elections. It excludes public-election ballot administration (`election_administration`), court docketing (`court_clerk_case_admin`), employment self-service (`hr_payroll`), and litigation matter management (`legal_practice_ops`). `petition`, `party`, `hearing`, `election`, `voter`, `objection`, and `certification` require an NLRB Region/case number, a petitioned bargaining unit, an authorized Board or party role, and the current representation-case stage.

Primary-source seed pack:

1. eCFR, [29 CFR Part 102 Subpart D — Procedure for Questions Concerning Representation](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D).
2. eCFR, [29 CFR § 102.60 — Petitions](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D/section-102.60).
3. eCFR, [29 CFR § 102.61 — Contents of Representation Petitions](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D/section-102.61).
4. eCFR, [29 CFR § 102.62 — Election Agreements](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D/section-102.62).
5. eCFR, [29 CFR § 102.63 — Regional Investigation, Hearing Notice, and Statement of Position](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D/section-102.63).
6. eCFR, [29 CFR § 102.67 — Proceedings Before the Regional Director](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D/section-102.67).
7. eCFR, [29 CFR § 102.69 — Election Procedure, Tally, Objections, and Certification](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-I/part-102/subpart-D/section-102.69).
8. National Labor Relations Board, [Casehandling Manual Part Two — Representation Proceedings (July 2026)](https://www.nlrb.gov/sites/default/files/attachments/pages/node-174/chm-part-ii-representation-casehandling-manual.pdf).
9. National Labor Relations Board, [Representation (R) Case Fillable Forms](https://www.nlrb.gov/guidance/fillable-forms).

Terminal evidence map: sources 1–3, 8, and 9 support `nlrb_representation_case_ops.petition_case_queue`, `nlrb_representation_case_ops.case_party_profile`, `nlrb_representation_case_ops.bargaining_unit_scope_view`, `nlrb_representation_case_ops.showing_interest_status`, `nlrb_representation_case_ops.petition_docket`, `nlrb_representation_case_ops.petition_amendment_record`, and `nlrb_representation_case_ops.petition_withdrawal_approve`; sources 5, 6, and 8 support `nlrb_representation_case_ops.hearing_schedule_status`, `nlrb_representation_case_ops.regional_investigation_assign`, `nlrb_representation_case_ops.hearing_notice_issue`, and `nlrb_representation_case_ops.pre_election_decision_issue`; sources 4, 6, 8, and 9 support `nlrb_representation_case_ops.election_arrangement_status`, `nlrb_representation_case_ops.bargaining_unit_stipulation_record`, `nlrb_representation_case_ops.election_agreement_approve`, `nlrb_representation_case_ops.voter_list_submit`, and `nlrb_representation_case_ops.election_schedule_authorize`; sources 7–9 support `nlrb_representation_case_ops.tally_objection_status`, `nlrb_representation_case_ops.challenged_ballot_record`, `nlrb_representation_case_ops.election_objection_intake`, and `nlrb_representation_case_ops.certification_issue`. Those materials identify the Regional Director, hearing officer, Board agent, and party-filer authority and the filed→amended/withdrawn, investigation→hearing→decision, agreed/directed→scheduled, cast→challenged→resolved, and tally→objection→certification transitions.

## 6. Special-education program administration (`special_education_program_admin`)

Hub: `special_education_program_admin.hub` — 특수교육 프로그램 행정 / Special-education program administration

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `special_education_program_admin.referral_child_find_queue` | 의뢰·아동찾기 작업함 / Referral-and-child-find queue | 특수교육 의뢰와 아동찾기 작업함을 보여 줘 / Show the special-education referral and child-find queue |
| S | `special_education_program_admin.student_program_profile` | 학생 특수교육 프로필 / Student special-education profile | 이 학생의 특수교육 프로그램 프로필을 열어 줘 / Open this student's special-education program profile |
| S | `special_education_program_admin.evaluation_consent_status` | 평가동의 상태 / Evaluation-consent status | 초기평가 부모동의 상태를 확인해 줘 / Show parental-consent status for the initial evaluation |
| S | `special_education_program_admin.evaluation_assessment_status` | 평가·검사 상태 / Evaluation-and-assessment status | 학생 평가와 검사 완료 상태를 보여 줘 / Show completion status of the student's evaluations and assessments |
| S | `special_education_program_admin.eligibility_status` | 특수교육 적격성 상태 / Special-education eligibility status | 이 학생의 IDEA 적격성 상태를 열어 줘 / Open this student's IDEA eligibility status |
| S | `special_education_program_admin.iep_current_version` | 현행 개별화교육계획 / Current IEP version | 현재 시행 중인 IEP를 보여 줘 / Show the currently implemented IEP |
| S | `special_education_program_admin.service_placement_schedule` | 서비스·배치 일정 / Service-and-placement schedule | IEP 서비스와 교육배치 일정을 열어 줘 / Open the IEP service and educational-placement schedule |
| C | `special_education_program_admin.referral_intake` | 특수교육 의뢰접수 / Special-education referral intake | 특수교육 평가의뢰를 접수하는 화면으로 가 줘 / Take me to intake the special-education evaluation referral |
| C | `special_education_program_admin.evaluation_consent_request` | 평가동의 요청 / Evaluation-consent request | 초기평가 부모동의를 요청하는 곳으로 가 줘 / Take me to request parental consent for initial evaluation |
| C | `special_education_program_admin.evaluation_plan_finalize` | 평가계획 확정 / Evaluation-plan finalization | 다영역 평가계획을 확정하는 화면을 열어 줘 / Open the multidisciplinary evaluation-plan finalization |
| C | `special_education_program_admin.eligibility_determination_record` | 적격성 결정 기록 / Eligibility-determination record | IEP 팀의 적격성 결정을 기록하는 곳으로 가 줘 / Take me to record the IEP team's eligibility determination |
| C | `special_education_program_admin.iep_meeting_schedule` | IEP 회의 일정확정 / IEP-meeting scheduling | 학부모 참여 IEP 회의를 확정하는 화면으로 가 줘 / Take me to schedule the parent-participation IEP meeting |
| C | `special_education_program_admin.iep_draft_update` | IEP 초안 갱신 / IEP-draft update | 학생의 현행수준·목표·서비스 IEP 초안을 갱신하는 곳으로 가 줘 / Take me to update the student's present levels, goals, and services draft |
| C | `special_education_program_admin.placement_decision_record` | 교육배치 결정 기록 / Educational-placement decision record | 최소제한환경 배치결정을 기록하는 화면으로 가 줘 / Take me to record the least-restrictive-environment placement decision |
| C | `special_education_program_admin.iep_implementation_authorize` | IEP 시행 승인 / IEP implementation authorization | 최종 IEP 시행 승인 화면을 열어 줘 / Open the final IEP implementation authorization |
| C | `special_education_program_admin.progress_report_issue` | IEP 진도보고 발행 / IEP progress-report issue | IEP 목표 진도보고를 발행하는 곳으로 가 줘 / Take me to issue the IEP goal progress report |
| C | `special_education_program_admin.reevaluation_decision` | 재평가 결정 / Reevaluation decision | 학생 재평가 필요 여부를 결정하는 화면으로 가 줘 / Take me to decide whether the student requires reevaluation |
| C | `special_education_program_admin.transition_plan_approve` | 전환계획 승인 / Transition-plan approval | 중등 이후 전환계획 승인 화면을 열어 줘 / Open the postsecondary transition-plan approval |
| C | `special_education_program_admin.manifestation_determination_record` | 장애관련성 판단 기록 / Manifestation-determination record | 징계 전 장애관련성 판단을 기록하는 곳으로 가 줘 / Take me to record the pre-discipline manifestation determination |
| C | `special_education_program_admin.procedural_safeguards_notice_issue` | 절차상 보호통지 발행 / Procedural-safeguards notice issue | 학부모에게 절차상 보호통지를 발행하는 화면으로 가 줘 / Take me to issue the procedural-safeguards notice to the parent |

Roles/assets/states: special-education administrator, case manager, school psychologist, evaluator, IEP team member, related-service provider, and authorized parent/guardian participant; student, referral, consent, evaluation, eligibility record, IEP version, service, placement, notice; `referred/consent-pending/evaluating`, `eligible/ineligible`, `draft/reviewed/accepted/implemented/revised`, and `annual-review/reevaluation/transition/dispute`.

Boundary and collision guard: this is the IDEA-governed evaluation-to-IEP lifecycle for a specific school-age student. It excludes generic learning content (`education`), instructor assignments and grades (`classroom_instructor_ops`), higher-education registrar records, and social-benefit casework. `student`, `evaluation`, `plan`, `meeting`, `progress`, or `placement` alone is insufficient.

Primary-source seed pack:

1. eCFR, [34 CFR Part 300 — Assistance to States for the Education of Children with Disabilities](https://www.ecfr.gov/current/title-34/subtitle-B/chapter-III/part-300).
2. U.S. Department of Education IDEA, [20 U.S.C. §1414 — Evaluations, eligibility determinations, IEPs, and placements](https://sites.ed.gov/idea/statute-chapter-33/subchapter-ii/1414).
3. U.S. Department of Education IDEA, [Part B Subpart D — Evaluations, Eligibility, IEPs, and Placements](https://sites.ed.gov/idea/regs/b/d).
4. U.S. Department of Education IDEA, [Part B Subpart E — Procedural Safeguards](https://sites.ed.gov/idea/regs/b/e).
5. U.S. Department of Education IDEA, [34 CFR § 300.111 — Child Find](https://sites.ed.gov/idea/regs/b/b/300.111).
6. U.S. Department of Education IDEA, [34 CFR § 300.300 — Parental Consent](https://sites.ed.gov/idea/regs/b/d/300.300).
7. U.S. Department of Education IDEA, [34 CFR § 300.301 — Initial Evaluations](https://sites.ed.gov/idea/regs/b/d/300.301).
8. U.S. Department of Education IDEA, [34 CFR § 300.305 — Additional Requirements for Evaluations and Reevaluations](https://sites.ed.gov/idea/regs/b/d/300.305).
9. U.S. Department of Education IDEA, [34 CFR § 300.306 — Determination of Eligibility](https://sites.ed.gov/idea/regs/b/d/300.306).
10. U.S. Department of Education IDEA, [34 CFR § 300.320 — Definition of Individualized Education Program](https://sites.ed.gov/idea/regs/b/d/300.320).
11. U.S. Department of Education IDEA, [34 CFR § 300.322 — Parent Participation](https://sites.ed.gov/idea/regs/b/d/300.322).
12. U.S. Department of Education IDEA, [34 CFR § 300.323 — When IEPs Must Be in Effect](https://sites.ed.gov/idea/regs/b/d/300.323).
13. U.S. Department of Education IDEA, [34 CFR § 300.324 — Development, Review, and Revision of IEP](https://sites.ed.gov/idea/regs/b/d/300.324).
14. U.S. Department of Education IDEA, [34 CFR § 300.116 — Placements](https://sites.ed.gov/idea/regs/b/b/300.116).
15. U.S. Department of Education IDEA, [34 CFR § 300.503 — Prior Notice by the Public Agency](https://sites.ed.gov/idea/regs/b/e/300.503).
16. U.S. Department of Education IDEA, [34 CFR § 300.504 — Procedural Safeguards Notice](https://sites.ed.gov/idea/regs/b/e/300.504).
17. U.S. Department of Education IDEA, [34 CFR § 300.530 — Authority of School Personnel](https://sites.ed.gov/idea/regs/b/e/300.530).

Terminal evidence map: sources 1–5 and 7 support `special_education_program_admin.referral_child_find_queue`, `special_education_program_admin.student_program_profile`, and `special_education_program_admin.referral_intake`; sources 3, 6–8 support `special_education_program_admin.evaluation_consent_status`, `special_education_program_admin.evaluation_assessment_status`, `special_education_program_admin.evaluation_consent_request`, `special_education_program_admin.evaluation_plan_finalize`, and `special_education_program_admin.reevaluation_decision`; sources 2–3 and 9 support `special_education_program_admin.eligibility_status` and `special_education_program_admin.eligibility_determination_record`; sources 2–3 and 10–13 support `special_education_program_admin.iep_current_version`, `special_education_program_admin.service_placement_schedule`, `special_education_program_admin.iep_meeting_schedule`, `special_education_program_admin.iep_draft_update`, `special_education_program_admin.iep_implementation_authorize`, `special_education_program_admin.progress_report_issue`, and `special_education_program_admin.transition_plan_approve`; sources 2–3 and 14 support `special_education_program_admin.placement_decision_record`; sources 4 and 17 support `special_education_program_admin.manifestation_determination_record`; sources 4, 15, and 16 support `special_education_program_admin.procedural_safeguards_notice_issue`. These provisions identify the public agency, evaluation group, IEP Team, school personnel, and parent-participant authority and the referred→consent-pending→evaluating, eligible/ineligible, draft→reviewed→implemented→revised, annual-review/reevaluation, and discipline→manifestation-determination transitions.

## 7. Pension-plan administration (`pension_plan_administration`)

Hub: `pension_plan_administration.hub` — 연금제도 운영행정 / Pension-plan administration

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `pension_plan_administration.plan_document_version` | 연금규약 버전 / Pension-plan document version | 현재 적용되는 연금규약 버전을 열어 줘 / Open the currently governing pension-plan document version |
| S | `pension_plan_administration.participant_service_history` | 가입자 근속이력 / Participant service history | 이 가입자의 연금 근속인정 이력을 보여 줘 / Show this participant's pension service-credit history |
| S | `pension_plan_administration.eligibility_vesting_status` | 가입·가득권 상태 / Eligibility-and-vesting status | 가입자의 연금 가입자격과 가득권 상태를 확인해 줘 / Show the participant's plan eligibility and vesting status |
| S | `pension_plan_administration.accrued_benefit_account_view` | 적립계정·발생급여 조회 / Account-and-accrued-benefit view | 이 가입자의 적립계정 또는 발생급여를 보여 줘 / Show this participant's account or accrued benefit |
| S | `pension_plan_administration.contribution_allocation_status` | 기여금 배분 상태 / Contribution-allocation status | 이번 기여금 배분 처리 상태를 확인해 줘 / Show processing status of this contribution allocation |
| S | `pension_plan_administration.beneficiary_record_view` | 수익자 지정 조회 / Beneficiary-record view | 현재 연금 수익자 지정기록을 열어 줘 / Open the current pension beneficiary record |
| S | `pension_plan_administration.distribution_claim_status` | 급여청구·지급 상태 / Distribution-claim status | 이 퇴직급여 청구의 심사와 지급 상태를 보여 줘 / Show adjudication and payment status of this retirement-benefit claim |
| C | `pension_plan_administration.participant_eligibility_determine` | 가입자격 결정 / Participant-eligibility determination | 제도 규약에 따라 가입자격을 결정하는 화면으로 가 줘 / Take me to determine plan eligibility under the governing terms |
| C | `pension_plan_administration.service_credit_adjust` | 근속인정 조정 / Service-credit adjustment | 검증된 연금 근속기간을 조정하는 곳으로 가 줘 / Take me to adjust the verified pension service credit |
| C | `pension_plan_administration.beneficiary_designation_record` | 수익자 지정 기록 / Beneficiary-designation record | 검증된 연금 수익자 지정을 기록하는 화면으로 가 줘 / Take me to record the verified pension beneficiary designation |
| C | `pension_plan_administration.contribution_allocation_post` | 기여금 배분 반영 / Contribution-allocation posting | 검증된 가입자 기여금 배분을 반영하는 곳으로 가 줘 / Take me to post the verified participant contribution allocation |
| C | `pension_plan_administration.rollover_acceptance_record` | 이전금 수락 기록 / Rollover-acceptance record | 적격 이전금 수락을 기록하는 화면으로 가 줘 / Take me to record acceptance of the eligible rollover |
| C | `pension_plan_administration.participant_loan_decide` | 가입자 대출 결정 / Participant-loan decision | 연금 가입자 대출 결정을 내리는 화면으로 가 줘 / Take me to the pension participant-loan decision |
| C | `pension_plan_administration.hardship_distribution_decide` | 곤란사유 인출 결정 / Hardship-distribution decision | 곤란사유 인출 청구를 결정하는 곳으로 가 줘 / Take me to decide the hardship-distribution claim |
| C | `pension_plan_administration.qdro_qualification_decide` | 적격가사관계명령 판단 / QDRO qualification decision | 가사관계명령의 QDRO 적격성을 판단하는 화면으로 가 줘 / Take me to determine whether the domestic-relations order is qualified |
| C | `pension_plan_administration.retirement_benefit_commence` | 퇴직급여 개시 / Retirement-benefit commencement | 승인된 퇴직급여 개시 화면으로 가 줘 / Take me to commence the approved retirement benefit |
| C | `pension_plan_administration.rmd_distribution_release` | 최소의무인출 지급방출 / Required-minimum-distribution release | 기한이 된 RMD 지급방출 화면을 열어 줘 / Open the due required-minimum-distribution release |
| C | `pension_plan_administration.benefit_claim_decide` | 급여청구 결정 / Benefit-claim decision | 연금 급여청구의 승인 또는 거절 결정 화면으로 가 줘 / Take me to decide approval or denial of the pension claim |
| C | `pension_plan_administration.claim_appeal_decide` | 급여청구 이의심사 결정 / Claim-appeal decision | 불리한 연금결정의 이의심사 화면으로 가 줘 / Take me to decide the appeal of the adverse pension determination |
| C | `pension_plan_administration.form_5500_submit` | Form 5500 제출 / Form 5500 submission | 연금제도 연차보고서 Form 5500 제출 화면으로 가 줘 / Take me to submit the pension plan's Form 5500 annual report |

Roles/assets/states: plan administrator, recordkeeper, benefits adjudicator, trustee, authorized payroll feed reviewer, QDRO reviewer, and filing officer; governing plan, participant, service credit, account/accrued benefit, contribution, beneficiary, loan, order, distribution, claim/appeal, annual filing; `eligible/ineligible`, `unvested/partially/fully vested`, `pending/approved/denied/appealed/paid`, and `open/frozen/terminated`.

Boundary and collision guard: this domain owns institutional administration under a specific retirement-plan document. It excludes employee self-service benefits enrollment (`hr_payroll`), personal investments and orders (`finance_long_tail`), ordinary banking transfers, and business-accounting journals. `benefit`, `account`, `loan`, `payment`, `contribution`, or `claim` needs plan/participant/ERISA state.

Primary-source seed pack:

1. eCFR, [29 CFR §2560.503-1 — Claims procedure](https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XXV/subchapter-G/part-2560/section-2560.503-1).
2. U.S. Department of Labor EBSA, [Reporting and Disclosure Guide for Employee Benefit Plans](https://www.dol.gov/sites/dolgov/files/EBSA/about-ebsa/our-activities/resource-center/publications/reporting-annual-disclosure.pdf).
3. Internal Revenue Service, [Retirement Plan Operation and Maintenance](https://www.irs.gov/retirement-plans/retirement-plan-operation-and-maintenance).
4. Internal Revenue Service, [Types of Retirement Plan Benefits](https://www.irs.gov/retirement-plans/types-of-retirement-plan-benefits).
5. Internal Revenue Service, [Retirement Topics — Vesting](https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-vesting).
6. Internal Revenue Service, [Retirement Topics — Beneficiary](https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-beneficiary).
7. Internal Revenue Service, [Rollovers of Retirement Plan and IRA Distributions](https://www.irs.gov/retirement-plans/plan-participant-employee/rollovers-of-retirement-plan-and-ira-distributions).
8. Internal Revenue Service, [Retirement Plans FAQs Regarding Loans](https://www.irs.gov/retirement-plans/retirement-plans-faqs-regarding-loans).
9. Internal Revenue Service, [Retirement Plans FAQs Regarding Hardship Distributions](https://www.irs.gov/retirement-plans/retirement-plans-faqs-regarding-hardship-distributions).
10. U.S. Department of Labor EBSA, [Qualified Domestic Relations Orders: An Overview](https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/resource-center/publications/qdros-chapter-1).
11. Internal Revenue Service, [Retirement Plan and IRA Required Minimum Distributions FAQs](https://www.irs.gov/retirement-plans/retirement-plan-and-ira-required-minimum-distributions-faqs).
12. U.S. Department of Labor EBSA, [Form 5500 Series](https://www.dol.gov/agencies/ebsa/employers-and-advisers/plan-administration-and-compliance/reporting-and-filing/form-5500).

Terminal evidence map: sources 2–5 support `pension_plan_administration.plan_document_version`, `pension_plan_administration.participant_service_history`, `pension_plan_administration.eligibility_vesting_status`, `pension_plan_administration.accrued_benefit_account_view`, `pension_plan_administration.contribution_allocation_status`, `pension_plan_administration.participant_eligibility_determine`, `pension_plan_administration.service_credit_adjust`, and `pension_plan_administration.contribution_allocation_post`; source 6 supports `pension_plan_administration.beneficiary_record_view` and `pension_plan_administration.beneficiary_designation_record`; source 7 supports `pension_plan_administration.rollover_acceptance_record`; source 8 supports `pension_plan_administration.participant_loan_decide`; source 9 supports `pension_plan_administration.hardship_distribution_decide`; source 10 supports `pension_plan_administration.qdro_qualification_decide`; source 11 supports `pension_plan_administration.rmd_distribution_release`; sources 1 and 4 support `pension_plan_administration.distribution_claim_status`, `pension_plan_administration.retirement_benefit_commence`, `pension_plan_administration.benefit_claim_decide`, and `pension_plan_administration.claim_appeal_decide`; sources 2 and 12 support `pension_plan_administration.form_5500_submit`. The cited regulations and agency instructions identify the plan administrator, claims fiduciary, QDRO decision maker, participant/beneficiary, and electronic filing signer and the eligible/ineligible, unvested→vested, pending→approved/denied→appealed/paid, rollover offered→accepted, and annual-report draft→signed→filed transitions; plan terms remain controlling where the IRS materials say a feature is optional.

## 8. Campaign-finance compliance (`campaign_finance_compliance`)

Hub: `campaign_finance_compliance.hub` — 선거운동 재정준법 / Campaign-finance compliance

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `campaign_finance_compliance.committee_registration_status` | 정치위원회 등록상태 / Political-committee registration status | 이 위원회의 FEC 등록상태를 보여 줘 / Show this committee's FEC registration status |
| S | `campaign_finance_compliance.candidate_committee_relationship` | 후보자·위원회 관계 / Candidate-and-committee relationship | 후보자와 승인위원회 관계를 확인해 줘 / Show the candidate and authorized-committee relationship |
| S | `campaign_finance_compliance.reporting_calendar` | 선거재정보고 일정 / Campaign-finance reporting calendar | 이 위원회의 다음 보고기한을 보여 줘 / Show this committee's next reporting deadline |
| S | `campaign_finance_compliance.cash_on_hand_ledger` | 보유현금 원장 / Cash-on-hand ledger | 보고기간 시작과 종료 보유현금을 열어 줘 / Open beginning and ending cash on hand for the reporting period |
| S | `campaign_finance_compliance.receipt_disbursement_journal` | 수입·지출 분개장 / Receipt-and-disbursement journal | 이번 보고기간 수입과 지출 분개를 보여 줘 / Show receipt and disbursement entries for this reporting period |
| S | `campaign_finance_compliance.debt_obligation_schedule` | 채무·의무 명세 / Debt-and-obligation schedule | 위원회의 미결 채무와 의무 명세를 열어 줘 / Open the committee's outstanding debts and obligations |
| S | `campaign_finance_compliance.filing_notice_status` | 제출·보완통지 상태 / Filing-and-notice status | FEC 보고서 접수와 보완통지 상태를 확인해 줘 / Show FEC report receipt and compliance-notice status |
| C | `campaign_finance_compliance.statement_organization_file` | 조직신고서 제출 / Statement-of-organization filing | 위원회 조직신고서를 제출하는 화면으로 가 줘 / Take me to file the committee's statement of organization |
| C | `campaign_finance_compliance.candidate_designation_file` | 후보자 위원회 지정 제출 / Candidate-committee designation filing | 후보자의 주선거운동위원회 지정을 제출하는 곳으로 가 줘 / Take me to file the candidate's principal-campaign-committee designation |
| C | `campaign_finance_compliance.contribution_receipt_classify` | 기부수입 분류 / Contribution-receipt classification | 이 기부수입의 보고범주를 분류하는 화면으로 가 줘 / Take me to classify the reporting category for this contribution receipt |
| C | `campaign_finance_compliance.earmarked_transfer_record` | 지정기부 전달기록 / Earmarked-transfer record | 지정기부의 중개·전달을 기록하는 곳으로 가 줘 / Take me to record the conduit and transfer of the earmarked contribution |
| C | `campaign_finance_compliance.contribution_attribution_resolve` | 기부 귀속조정 / Contribution-attribution resolution | 공동기부의 재귀속 또는 재지정을 처리하는 화면으로 가 줘 / Take me to resolve reattribution or redesignation of the joint contribution |
| C | `campaign_finance_compliance.contribution_refund_record` | 초과·금지기부 환급 기록 / Impermissible-contribution refund record | 초과 또는 금지 기부의 환급을 기록하는 곳으로 가 줘 / Take me to record refund of the excessive or prohibited contribution |
| C | `campaign_finance_compliance.disbursement_classify` | 선거지출 분류 / Campaign-disbursement classification | 이 위원회 지출의 보고범주를 분류하는 화면으로 가 줘 / Take me to classify this committee disbursement for reporting |
| C | `campaign_finance_compliance.independent_expenditure_report` | 독립지출 보고 / Independent-expenditure report | 독립지출 보고서를 작성하는 화면으로 가 줘 / Take me to prepare the independent-expenditure report |
| C | `campaign_finance_compliance.electioneering_communication_report` | 선거운동통신 보고 / Electioneering-communication report | 보고대상 선거운동통신을 제출하는 곳으로 가 줘 / Take me to file the reportable electioneering communication |
| C | `campaign_finance_compliance.debt_schedule_update` | 채무명세 갱신 / Debt-schedule update | 미결 채무명세를 갱신하는 화면으로 가 줘 / Take me to update the outstanding-debt schedule |
| C | `campaign_finance_compliance.bank_reconciliation_certify` | 선거계좌 조정 인증 / Campaign-account reconciliation certification | 보고서와 선거계좌 조정을 인증하는 곳으로 가 줘 / Take me to certify reconciliation of the report and campaign account |
| C | `campaign_finance_compliance.periodic_report_submit` | 정기 재정보고 제출 / Periodic campaign-finance report submission | 위원회 정기 재정보고서를 제출하는 화면으로 가 줘 / Take me to submit the committee's periodic finance report |
| C | `campaign_finance_compliance.report_amendment_file` | 재정보고 정정본 제출 / Campaign-finance report amendment filing | 기존 FEC 보고서 정정본을 제출하는 곳으로 가 줘 / Take me to file an amendment to the existing FEC report |

Roles/assets/states: committee treasurer, assistant treasurer, compliance analyst, authorized candidate agent, and electronic filer; candidate, committee, FEC ID, bank account, receipt, disbursement, debt, schedule, periodic report, amendment and notice; `unregistered/registered/terminated`, `draft/validated/submitted/accepted/amendment-required`, and `permissible/excessive/prohibited/refunded`.

Boundary and collision guard: this is committee disclosure and compliance, not ballot administration (`election_administration`), consumer donations (`crowdfunding_donations`), or ordinary bookkeeping (`business_accounting`). `candidate`, `committee`, `receipt`, `report`, `debt`, and `file` require FEC jurisdiction, committee role, reporting period, and transaction classification.

Primary-source seed pack:

1. eCFR, [Title 11 Chapter I — Federal Election Commission](https://www.ecfr.gov/current/title-11/chapter-I).
2. Federal Election Commission, [House, Senate, and Presidential Candidate Committee Registration](https://www.fec.gov/help-candidates-and-committees/registering-candidate/house-senate-presidential-candidate-committee-registration/).
3. Federal Election Commission, [Electronic Filing Overview](https://www.fec.gov/help-candidates-and-committees/filing-reports/electronic-filing/).
4. Federal Election Commission, [Campaign Guide for Congressional Candidates](https://www.fec.gov/resources/cms-content/documents/policy-guidance/candgui.pdf).
5. eCFR, [11 CFR Part 102 — Registration, Organization, and Recordkeeping by Political Committees](https://www.ecfr.gov/current/title-11/chapter-I/subchapter-A/part-102).
6. eCFR, [11 CFR Part 104 — Reports by Political Committees and Other Persons](https://www.ecfr.gov/current/title-11/chapter-I/subchapter-A/part-104).
7. eCFR, [11 CFR Part 110 — Contribution and Expenditure Limitations and Prohibitions](https://www.ecfr.gov/current/title-11/chapter-I/subchapter-A/part-110).
8. Federal Election Commission, [Dates and Deadlines](https://www.fec.gov/help-candidates-and-committees/dates-and-deadlines/).
9. Federal Election Commission, [Filing Candidate Reports](https://www.fec.gov/help-candidates-and-committees/filing-reports/).
10. Federal Election Commission, [Making Independent Expenditures](https://www.fec.gov/help-candidates-and-committees/making-independent-expenditures/).
11. Federal Election Commission, [Registration and Reporting Forms](https://www.fec.gov/help-candidates-and-committees/forms/).

Terminal evidence map: sources 1–2, 5, and 11 support `campaign_finance_compliance.committee_registration_status`, `campaign_finance_compliance.candidate_committee_relationship`, `campaign_finance_compliance.statement_organization_file`, and `campaign_finance_compliance.candidate_designation_file`; sources 6, 8, and 9 support `campaign_finance_compliance.reporting_calendar` and `campaign_finance_compliance.filing_notice_status`; sources 4, 6, 9, and 11 support `campaign_finance_compliance.cash_on_hand_ledger`, `campaign_finance_compliance.receipt_disbursement_journal`, `campaign_finance_compliance.debt_obligation_schedule`, `campaign_finance_compliance.disbursement_classify`, `campaign_finance_compliance.debt_schedule_update`, `campaign_finance_compliance.bank_reconciliation_certify`, `campaign_finance_compliance.periodic_report_submit`, and `campaign_finance_compliance.report_amendment_file`; sources 4, 6, 7, and 9 support `campaign_finance_compliance.contribution_receipt_classify`, `campaign_finance_compliance.earmarked_transfer_record`, `campaign_finance_compliance.contribution_attribution_resolve`, and `campaign_finance_compliance.contribution_refund_record`; sources 6, 8, 10, and 11 support `campaign_finance_compliance.independent_expenditure_report` and `campaign_finance_compliance.electioneering_communication_report`. These provisions identify the committee treasurer/authorized filer and candidate-agent authority and the unregistered→registered→terminated, permissible→excessive/prohibited→refunded, draft→validated→submitted→accepted/amendment-required, and debt-open→updated→settled transitions.

## 9. Export-control authorization operations (`export_control_authorization_ops`)

Hub: `export_control_authorization_ops.hub` — 수출통제 허가운영 / Export-control authorization operations

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `export_control_authorization_ops.ear_scope_review` | EAR 적용범위 검토 / EAR-scope review | 이 품목이 EAR 적용대상인지 검토하는 화면을 열어 줘 / Open the review of whether this item is subject to the EAR |
| S | `export_control_authorization_ops.item_eccn_classification` | 품목 ECCN 분류 / Item ECCN classification | 이 소프트웨어의 ECCN 분류를 보여 줘 / Show the ECCN classification for this software |
| S | `export_control_authorization_ops.country_chart_control_status` | 국가별 통제상태 / Country-chart control status | 목적국에 적용되는 통제사유를 확인해 줘 / Show the reasons for control applicable to the destination country |
| S | `export_control_authorization_ops.end_use_end_user_review` | 최종용도·최종사용자 검토 / End-use and end-user review | 이 거래의 최종용도와 최종사용자 검토를 열어 줘 / Open the end-use and end-user review for this transaction |
| S | `export_control_authorization_ops.license_exception_eligibility` | 허가예외 적격성 / License-exception eligibility | 해당 EAR 허가예외의 적격조건을 보여 줘 / Show eligibility conditions for the EAR license exception |
| S | `export_control_authorization_ops.license_proviso_view` | 허가조건·단서 조회 / License-condition and proviso view | 발급된 수출허가의 조건과 단서를 열어 줘 / Open conditions and provisos on the issued export license |
| S | `export_control_authorization_ops.application_case_status` | 허가신청 사건상태 / License-application case status | SNAP-R 허가신청 심사상태를 확인해 줘 / Show adjudication status of the SNAP-R license application |
| C | `export_control_authorization_ops.classification_request_create` | 공식 품목분류 요청 생성 / Official-classification request creation | BIS 공식 품목분류 요청을 만드는 화면으로 가 줘 / Take me to create a BIS official-classification request |
| C | `export_control_authorization_ops.license_application_create` | 수출허가 신청 생성 / Export-license application creation | 새 EAR 수출허가 신청을 만드는 곳으로 가 줘 / Take me to create a new EAR export-license application |
| C | `export_control_authorization_ops.application_parties_update` | 신청 당사자 갱신 / Application-party update | 신청서의 신청인·최종수하인·최종사용자를 갱신하는 화면으로 가 줘 / Take me to update applicant, ultimate consignee, and end user |
| C | `export_control_authorization_ops.supporting_document_attach` | 허가 근거문서 첨부 / License-support document attachment | 최종사용자 확인서를 허가신청에 첨부하는 곳으로 가 줘 / Take me to attach the end-user statement to the license application |
| C | `export_control_authorization_ops.application_submit` | 수출허가 신청 제출 / Export-license application submission | 검증된 SNAP-R 수출허가 신청을 제출하는 화면으로 가 줘 / Take me to submit the validated SNAP-R export-license application |
| C | `export_control_authorization_ops.deemed_export_access_request` | 간주수출 접근허가 요청 / Deemed-export access request | 외국인 기술접근에 대한 간주수출 허가 요청 화면으로 가 줘 / Take me to request deemed-export authorization for foreign-person access |
| C | `export_control_authorization_ops.reexport_transfer_request` | 재수출·국내이전 허가 요청 / Reexport-or-transfer authorization request | 재수출 또는 국내이전 허가를 요청하는 곳으로 가 줘 / Take me to request authorization for reexport or in-country transfer |
| C | `export_control_authorization_ops.license_amendment_request` | 수출허가 변경 요청 / Export-license amendment request | 발급된 수출허가 변경을 요청하는 화면으로 가 줘 / Take me to request amendment of the issued export license |
| C | `export_control_authorization_ops.license_exception_use_record` | 허가예외 사용기록 / License-exception use record | 이 거래의 허가예외 사용근거를 기록하는 곳으로 가 줘 / Take me to record the license-exception basis for this transaction |
| C | `export_control_authorization_ops.license_proviso_accept` | 허가조건 수락 / License-proviso acceptance | 발급된 허가조건과 단서를 수락하는 화면으로 가 줘 / Take me to acknowledge the issued license conditions and provisos |
| C | `export_control_authorization_ops.application_withdraw` | 허가신청 철회 / License-application withdrawal | 진행 중인 수출허가 신청 철회 화면으로 가 줘 / Take me to withdraw the pending export-license application |
| C | `export_control_authorization_ops.recordkeeping_certify` | 수출통제 기록보존 인증 / Export-control recordkeeping certification | 이 허가거래의 기록보존 완결을 인증하는 곳으로 가 줘 / Take me to certify recordkeeping completion for this authorized transaction |
| C | `export_control_authorization_ops.voluntary_disclosure_submit` | 자진신고 제출 / Voluntary self-disclosure submission | 잠재적 EAR 위반 자진신고 제출 화면으로 가 줘 / Take me to submit the potential EAR-violation voluntary disclosure |

Roles/assets/states: empowered official, export-compliance officer, classifier, technology-control reviewer, license applicant, and records custodian; commodity/software/technology, ECCN, destination, end use/end user, transaction parties, exception, application, license/proviso, disclosure; `not-subject/EAR99/ECCN-controlled`, `draft/returned/submitted/in-review/approved/denied/withdrawn`, and `valid/expired/suspended/amended`.

Boundary and collision guard: this domain owns BIS authorization under the EAR. It excludes cargo customs declarations (`freight_forwarding_customs_ops`), sanctions-hit disposition (`financial_crime_compliance_ops`), and supplier purchase approval (`procurement_supplier_ops`). `classification`, `party`, `screening`, `license`, `transfer`, and `submit` require EAR/item/end-use/destination context; sanctions screening alone must remain in its prior domain.

Primary-source seed pack:

1. Bureau of Industry and Security, [EAR Table of Contents](https://www.bis.gov/regulations/ear/table-of-contents).
2. Bureau of Industry and Security, [About Licensing](https://www.bis.gov/licensing).
3. Bureau of Industry and Security, [EAR Part 748 — Applications, Classification Requests, and Advisory Opinions](https://www.bis.gov/regulations/ear/748).
4. Bureau of Industry and Security, [SNAP-R Frequently Asked Questions](https://snapr.bis.gov/help/SNAPR-FAQ.pdf).
5. eCFR, [15 CFR Part 734 — Scope of the Export Administration Regulations](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-734).
6. eCFR, [15 CFR Part 738 — Commerce Control List Overview and the Country Chart](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-738).
7. eCFR, [15 CFR Part 740 — License Exceptions](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-740).
8. eCFR, [15 CFR Part 744 — Control Policy: End-User and End-Use Based](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-744).
9. eCFR, [15 CFR Part 750 — Application Processing, Issuance, and Denial](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-750).
10. eCFR, [15 CFR Part 762 — Recordkeeping](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-762).
11. eCFR, [15 CFR 764.5 — Voluntary Self-Disclosure](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-764/section-764.5).

Terminal evidence map: sources 1 and 5 support `export_control_authorization_ops.ear_scope_review`; sources 1, 3, and 6 support `export_control_authorization_ops.item_eccn_classification`, `export_control_authorization_ops.country_chart_control_status`, and `export_control_authorization_ops.classification_request_create`; sources 5 and 8 support `export_control_authorization_ops.end_use_end_user_review`, `export_control_authorization_ops.deemed_export_access_request`, and `export_control_authorization_ops.reexport_transfer_request`; source 7 supports `export_control_authorization_ops.license_exception_eligibility` and `export_control_authorization_ops.license_exception_use_record`; sources 2–4 and 9 support `export_control_authorization_ops.license_proviso_view`, `export_control_authorization_ops.application_case_status`, `export_control_authorization_ops.license_application_create`, `export_control_authorization_ops.application_parties_update`, `export_control_authorization_ops.supporting_document_attach`, `export_control_authorization_ops.application_submit`, `export_control_authorization_ops.license_amendment_request`, `export_control_authorization_ops.license_proviso_accept`, and `export_control_authorization_ops.application_withdraw`; source 10 supports `export_control_authorization_ops.recordkeeping_certify`; source 11 supports `export_control_authorization_ops.voluntary_disclosure_submit`. These provisions distinguish the applicant, empowered official, technology-control reviewer, and BIS adjudicator, and support the not-subject/EAR99/ECCN-controlled, draft→submitted→returned/in-review→approved/denied/withdrawn, valid→amended/expired/suspended, exception-unrecorded→documented, records-open→certified, and suspected-violation→disclosed transitions.

## 10. Broadcast-station compliance (`broadcast_station_compliance`)

Hub: `broadcast_station_compliance.hub` — 방송국 면허·준법운영 / Broadcast-station licensing and compliance

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `broadcast_station_compliance.station_license_profile` | 방송국 면허 프로필 / Broadcast-station license profile | 이 방송국의 FCC 면허 프로필을 보여 줘 / Show this station's FCC license profile |
| S | `broadcast_station_compliance.authorized_facility_parameters` | 허가 시설제원 / Authorized facility parameters | 허가된 주파수·출력·송신시설 제원을 열어 줘 / Open authorized frequency, power, and transmitter parameters |
| S | `broadcast_station_compliance.operating_schedule_status` | 방송운영 일정상태 / Broadcast operating-schedule status | 면허상 방송운영 일정과 정파 상태를 보여 줘 / Show the licensed operating schedule and off-air status |
| S | `broadcast_station_compliance.public_file_completeness` | 공개검사파일 완결성 / Public-inspection-file completeness | 온라인 공개검사파일의 누락 항목을 확인해 줘 / Show missing items in the online public inspection file |
| S | `broadcast_station_compliance.political_file_inventory` | 정치방송파일 목록 / Political-file inventory | 이 방송국 정치방송파일 목록을 열어 줘 / Open this station's political-file inventory |
| S | `broadcast_station_compliance.eas_equipment_test_status` | EAS 장비·시험 상태 / EAS equipment-and-test status | EAS 장비 준비와 시험 상태를 보여 줘 / Show EAS equipment readiness and test status |
| S | `broadcast_station_compliance.station_log_compliance_review` | 방송국 운용일지 준법검토 / Station-log compliance review | 필수 방송국 운용일지의 준법상태를 열어 줘 / Open compliance status of required station logs |
| C | `broadcast_station_compliance.issues_programs_list_upload` | 지역현안 프로그램 목록 업로드 / Issues-programs-list upload | 분기별 지역현안 프로그램 목록 업로드 화면으로 가 줘 / Take me to upload the quarterly issues/programs list |
| C | `broadcast_station_compliance.political_file_order_upload` | 정치광고 주문 업로드 / Political-order upload | 정치광고 주문과 처분내역을 공개파일에 올리는 곳으로 가 줘 / Take me to upload the political-ad order and disposition to the public file |
| C | `broadcast_station_compliance.ownership_report_file` | 방송국 소유현황 보고 / Broadcast-ownership report filing | 방송국 소유현황 보고서를 제출하는 화면으로 가 줘 / Take me to file the broadcast ownership report |
| C | `broadcast_station_compliance.license_renewal_submit` | 방송면허 갱신 제출 / Broadcast-license renewal submission | 방송국 면허갱신 신청 제출 화면으로 가 줘 / Take me to submit the station license-renewal application |
| C | `broadcast_station_compliance.assignment_transfer_application` | 면허 양도·지배권이전 신청 / Assignment-or-transfer application | 방송면허 양도 또는 지배권이전 신청 화면으로 가 줘 / Take me to the broadcast assignment or transfer-of-control application |
| C | `broadcast_station_compliance.special_temporary_authority_request` | 특별임시허가 요청 / Special-temporary-authority request | 임시 기술운영을 위한 STA 요청 화면으로 가 줘 / Take me to request special temporary authority for technical operation |
| C | `broadcast_station_compliance.silent_operation_notice` | 방송중단 통지·승인요청 / Silent-operation notice or request | 장기 방송중단 통지 또는 승인을 제출하는 곳으로 가 줘 / Take me to file the extended-silence notice or authority request |
| C | `broadcast_station_compliance.eas_test_log_record` | EAS 시험로그 기록 / EAS-test log record | 방송국 EAS 시험수신·송출 로그를 기록하는 화면으로 가 줘 / Take me to record the station's EAS test reception and transmission |
| C | `broadcast_station_compliance.eas_participant_filing_submit` | EAS 참가자 보고 제출 / EAS-participant filing submission | EAS 참가자 시험보고를 제출하는 곳으로 가 줘 / Take me to submit the EAS participant test filing |
| C | `broadcast_station_compliance.childrens_programming_report` | 아동프로그램 보고 / Children's-programming report | 텔레비전 아동프로그램 보고서를 제출하는 화면으로 가 줘 / Take me to file the television children's-programming report |
| C | `broadcast_station_compliance.eeo_public_file_upload` | EEO 공개파일 업로드 / EEO public-file upload | 방송국 EEO 공개파일 보고서를 업로드하는 곳으로 가 줘 / Take me to upload the station's EEO public-file report |
| C | `broadcast_station_compliance.facility_change_application` | 방송시설 변경신청 / Broadcast-facility change application | 허가 주파수·출력·안테나 변경신청 화면으로 가 줘 / Take me to apply for the frequency, power, or antenna change |
| C | `broadcast_station_compliance.operation_resume_notice` | 방송재개 통지 / Broadcast-operation resumption notice | 정파 후 방송재개 통지를 제출하는 곳으로 가 줘 / Take me to file notice that station operation resumed after silence |

Roles/assets/states: licensee responsible official, station manager, chief operator, broadcast engineer, public-file administrator, political-file custodian, and EAS coordinator; station/facility ID, license, technical authorization, operating schedule, public-file item, political order, EAS equipment/test, LMS filing; `licensed/pending renewal/expired`, `on-air/silent/temporary authority/resumed`, and `draft/filed/accepted/deficient/amended`.

Boundary and collision guard: this is FCC-regulated station licensing and required records. It excludes ordinary content publishing, public-safety call dispatch, marketing campaigns, and weather/news consumption. `station`, `program`, `file`, `alert`, `report`, and `publish` require licensee/service-class/facility and FCC filing context.

Primary-source seed pack:

1. eCFR, [47 CFR Part 73 — Radio Broadcast Services](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73).
2. eCFR, [47 CFR Part 11 — Emergency Alert System](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-11).
3. Federal Communications Commission, [Online Public Inspection Files](https://publicfiles.fcc.gov/).
4. Federal Communications Commission Media Bureau, [Licensing and Management System Help Center](https://www.fcc.gov/media/radio/lms-help-center).
5. eCFR, [47 CFR 73.3526 — Online Public Inspection File of Commercial Stations](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.3526).
6. eCFR, [47 CFR 73.3615 — Ownership Reports](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.3615).
7. eCFR, [47 CFR 73.3539 — Application for Renewal of License](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.3539).
8. eCFR, [47 CFR 73.3540 — Application for Voluntary Assignment or Transfer of Control](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.3540).
9. eCFR, [47 CFR 73.1635 — Special Temporary Authorizations](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.1635).
10. eCFR, [47 CFR 73.1740 — Minimum Operating Schedule](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.1740).
11. eCFR, [47 CFR 73.2080 — Equal Employment Opportunities](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-C/part-73/subpart-H/section-73.2080).

Terminal evidence map: sources 1, 4, and 7–10 support `broadcast_station_compliance.station_license_profile`, `broadcast_station_compliance.authorized_facility_parameters`, and `broadcast_station_compliance.operating_schedule_status`; sources 3 and 5 support `broadcast_station_compliance.public_file_completeness`, `broadcast_station_compliance.political_file_inventory`, `broadcast_station_compliance.issues_programs_list_upload`, `broadcast_station_compliance.political_file_order_upload`, and `broadcast_station_compliance.childrens_programming_report`; sources 1, 2, and 10 support `broadcast_station_compliance.eas_equipment_test_status`, `broadcast_station_compliance.station_log_compliance_review`, `broadcast_station_compliance.eas_test_log_record`, and `broadcast_station_compliance.eas_participant_filing_submit`; source 6 supports `broadcast_station_compliance.ownership_report_file`; source 7 supports `broadcast_station_compliance.license_renewal_submit`; source 8 supports `broadcast_station_compliance.assignment_transfer_application`; source 9 supports `broadcast_station_compliance.special_temporary_authority_request`; source 10 supports `broadcast_station_compliance.silent_operation_notice` and `broadcast_station_compliance.operation_resume_notice`; source 11 supports `broadcast_station_compliance.eeo_public_file_upload`; and sources 1 and 4 support `broadcast_station_compliance.facility_change_application`. These provisions identify the licensee responsible official, chief operator, public-file custodian, engineer, and EAS coordinator and support licensed→renewal-pending, authorized→modified/STA, on-air→silent→resumed, file-missing→uploaded/complete, draft→filed→accepted/deficient, and EAS-test-due→logged/reported transitions; station class and commercial/noncommercial applicability remain explicit.

## 11. App-store release management (`app_store_release_management`)

Hub: `app_store_release_management.hub` — 앱스토어 개발자 배포관리 / App-store developer release management

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `app_store_release_management.app_record_status` | 개발자 앱 레코드 상태 / Developer app-record status | 개발자 콘솔의 앱 레코드 상태를 보여 줘 / Show the app-record status in the developer console |
| S | `app_store_release_management.build_processing_status` | 빌드 처리 상태 / Build-processing status | 업로드한 앱 빌드 처리 상태를 확인해 줘 / Show processing status of the uploaded app build |
| S | `app_store_release_management.review_submission_status` | 심사제출 상태 / Review-submission status | 앱 심사제출의 현재 상태를 보여 줘 / Show the current app-review submission status |
| S | `app_store_release_management.release_track_status` | 배포트랙 상태 / Release-track status | 테스트와 프로덕션 배포트랙 상태를 열어 줘 / Open testing and production release-track status |
| S | `app_store_release_management.policy_issue_status` | 정책문제 상태 / Policy-issue status | 앱의 거절 또는 정책문제 상태를 확인해 줘 / Show rejection or policy-issue status for the app |
| S | `app_store_release_management.crash_anr_dashboard` | 비정상종료·ANR 대시보드 / Crash-and-ANR dashboard | 현재 릴리스의 비정상종료와 ANR을 보여 줘 / Show crashes and ANRs for the current release |
| S | `app_store_release_management.publishing_history` | 앱 배포이력 / App-publishing history | 이 앱의 심사와 배포이력을 열어 줘 / Open this app's review and publishing history |
| C | `app_store_release_management.app_record_create` | 개발자 앱 레코드 생성 / Developer app-record creation | 새 앱스토어 개발자 앱 레코드를 만드는 화면으로 가 줘 / Take me to create a new developer app record |
| C | `app_store_release_management.store_listing_update` | 스토어 등록정보 갱신 / Store-listing update | 앱 설명과 스크린샷 등록정보를 갱신하는 곳으로 가 줘 / Take me to update the app description and screenshot listing |
| C | `app_store_release_management.review_access_instructions_update` | 심사용 접근안내 갱신 / Review-access-instructions update | 앱 심사용 로그인과 접근안내를 갱신하는 화면으로 가 줘 / Take me to update login and access instructions for app review |
| C | `app_store_release_management.build_attach_to_version` | 버전에 빌드 연결 / Attach build to version | 처리 완료된 빌드를 이 앱 버전에 연결하는 곳으로 가 줘 / Take me to attach the processed build to this app version |
| C | `app_store_release_management.test_track_assign` | 테스트트랙 배정 / Test-track assignment | 새 빌드를 폐쇄 테스트트랙에 배정하는 화면으로 가 줘 / Take me to assign the new build to the closed-test track |
| C | `app_store_release_management.review_submission_create` | 앱심사 제출 생성 / App-review submission creation | 준비된 앱 버전을 심사에 제출하는 화면으로 가 줘 / Take me to submit the ready app version for review |
| C | `app_store_release_management.review_submission_withdraw` | 앱심사 제출 철회 / App-review submission withdrawal | 대기 중인 앱 심사제출을 철회하는 곳으로 가 줘 / Take me to withdraw the pending app-review submission |
| C | `app_store_release_management.managed_release_schedule` | 관리형 배포 일정설정 / Managed-release scheduling | 승인 후 수동배포 일정을 설정하는 화면으로 가 줘 / Take me to schedule managed publication after approval |
| C | `app_store_release_management.production_rollout_start` | 프로덕션 배포 시작 / Production-rollout start | 승인된 앱 버전의 프로덕션 배포 시작 화면으로 가 줘 / Take me to start production rollout of the approved version |
| C | `app_store_release_management.staged_rollout_increase` | 단계적 배포비율 확대 / Staged-rollout increase | 단계적 배포 대상을 다음 비율로 확대하는 곳으로 가 줘 / Take me to increase the staged rollout to the next percentage |
| C | `app_store_release_management.rollout_halt` | 앱 배포중단 / App-rollout halt | 문제 있는 앱 버전의 배포를 중단하는 화면으로 가 줘 / Take me to halt rollout of the problematic app version |
| C | `app_store_release_management.app_update_publish` | 앱 업데이트 게시 / App-update publication | 심사 통과한 앱 업데이트를 게시하는 곳으로 가 줘 / Take me to publish the approved app update |
| C | `app_store_release_management.app_unpublish` | 앱 게시해제 / App unpublishing | 신규 사용자 대상 앱 게시를 해제하는 화면으로 가 줘 / Take me to unpublish the app for new users |

Roles/assets/states: account holder, app manager, release manager, developer, tester administrator, and policy/compliance owner; developer account, app record, platform/version, build, review submission, release track, store listing, policy issue, rollout; `draft/build-processing/ready-for-review/in-review/accepted/rejected`, `testing/staged/production/halted`, and `published/unpublished`.

Boundary and collision guard: this is developer-side store submission and rollout. It excludes consumer app-store updates/refunds (`app_store`), repository merge/review (`code_repository`), generic workspace roles, and advertising campaigns. `app`, `build`, `review`, `release`, `publish`, and `update` require developer account plus store version/submission/track state.

Primary-source seed pack:

1. Apple Developer, [Overview of Submitting for Review](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/overview-of-submitting-for-review).
2. Apple Developer, [App and Submission Statuses](https://developer.apple.com/help/app-store-connect/reference/app-information/app-and-submission-statuses).
3. Google Play Console Help, [Publish Your App](https://support.google.com/googleplay/android-developer/answer/9859751?hl=en-EN).
4. Google Play Console Help, [Update or Unpublish Your App](https://support.google.com/googleplay/android-developer/answer/9859350?hl=en).
5. Apple Developer, [Add a New App](https://developer.apple.com/help/app-store-connect/create-an-app-record/add-a-new-app).
6. Apple Developer, [Upload Builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds).
7. Apple Developer, [Choose a Build to Submit](https://developer.apple.com/help/app-store-connect/manage-builds/choose-a-build-to-submit).
8. Apple Developer, [Release a Version Update in Phases](https://developer.apple.com/help/app-store-connect/update-your-app/release-a-version-update-in-phases).
9. Apple Developer, [Role Permissions](https://developer.apple.com/help/app-store-connect/reference/account-management/role-permissions).
10. Google Play Console Help, [Create and Set Up Your App](https://support.google.com/googleplay/android-developer/answer/9859152?hl=en).
11. Google Play Console Help, [Prepare and Roll Out a Release](https://support.google.com/googleplay/android-developer/answer/9859348/prepare-and-roll-out-a-release?hl=en-GB).
12. Google Play Console Help, [Release App Updates with Staged Rollouts](https://support.google.com/googleplay/android-developer/answer/6346149?hl=en).
13. Google Play Console Help, [Monitor Your App's Technical Quality with Android Vitals](https://support.google.com/googleplay/android-developer/answer/9844486?hl=en).
14. Google Play Console Help, [Add Developer Account Users and Manage Permissions](https://support.google.com/googleplay/android-developer/answer/9844686?hl=en).
15. Apple Developer, [View App Status History](https://developer.apple.com/help/app-store-connect/manage-your-apps-availability/view-app-status-history).

Terminal evidence map: sources 2, 5, 9, 10, 14, and 15 support `app_store_release_management.app_record_status`, `app_store_release_management.app_record_create`, and `app_store_release_management.publishing_history`; sources 2, 6, and 7 support `app_store_release_management.build_processing_status` and `app_store_release_management.build_attach_to_version`; sources 1–4, 9–11, and 14 support `app_store_release_management.review_submission_status`, `app_store_release_management.release_track_status`, `app_store_release_management.policy_issue_status`, `app_store_release_management.store_listing_update`, `app_store_release_management.review_access_instructions_update`, `app_store_release_management.test_track_assign`, `app_store_release_management.review_submission_create`, `app_store_release_management.review_submission_withdraw`, `app_store_release_management.managed_release_schedule`, `app_store_release_management.production_rollout_start`, `app_store_release_management.app_update_publish`, and `app_store_release_management.app_unpublish`; sources 8, 9, 12, and 14 support `app_store_release_management.staged_rollout_increase` and `app_store_release_management.rollout_halt`; source 13 supports `app_store_release_management.crash_anr_dashboard`. These first-party pages bind each action to the account-holder/admin/app-manager or corresponding Play permission and support record-absent→draft, uploaded→processing→ready, draft→submitted→in-review→accepted/rejected/withdrawn, testing→staged→production/halted, rollout-percentage→increased, and published→unpublished transitions. Apple and Google rules apply only inside their respective developer organizations; neither provider's role evidence is generalized to the other.

## 12. Domain-registration operations (`domain_registration_operations`)

Hub: `domain_registration_operations.hub` — 도메인 등록운영 / Domain-registration operations

| Class | Terminal function ID | 기능명 / Function name | 대표 intent / Representative intent |
|:---:|---|---|---|
| S | `domain_registration_operations.portfolio_expiry_status` | 등록도메인·만료 상태 / Domain-portfolio and expiry status | 등록한 도메인과 만료일을 보여 줘 / Show registered domains and their expiration dates |
| S | `domain_registration_operations.registration_data_view` | 도메인 등록정보 조회 / Domain-registration data view | 이 도메인의 현재 등록정보를 열어 줘 / Open current registration data for this domain |
| S | `domain_registration_operations.nameserver_delegation_view` | 네임서버 위임 조회 / Nameserver-delegation view | 이 등록도메인의 네임서버 위임을 보여 줘 / Show nameserver delegation for this registered domain |
| S | `domain_registration_operations.epp_status_view` | EPP 상태코드 조회 / EPP-status view | 이 도메인의 EPP 상태코드를 설명해 줘 / Show the EPP status codes for this domain |
| S | `domain_registration_operations.transfer_status` | 등록기관 이전 상태 / Registrar-transfer status | 도메인 등록기관 이전 진행 상태를 보여 줘 / Show progress of the inter-registrar domain transfer |
| S | `domain_registration_operations.renewal_status` | 도메인 갱신 상태 / Domain-renewal status | 이 도메인의 갱신과 유예기간 상태를 확인해 줘 / Show renewal and grace-period status for this domain |
| S | `domain_registration_operations.security_lock_status` | 등록 잠금 상태 / Registration-lock status | 이 도메인의 이전·수정·삭제 잠금 상태를 보여 줘 / Show transfer, update, and delete lock status for this domain |
| C | `domain_registration_operations.registration_create` | 도메인 등록 생성 / Domain-registration creation | 사용 가능한 도메인을 등록하는 화면으로 가 줘 / Take me to register the available domain name |
| C | `domain_registration_operations.registrant_contact_verify` | 등록자 연락처 검증 / Registrant-contact verification | 도메인 등록자 연락처 검증 화면으로 가 줘 / Take me to verify the domain registrant contact details |
| C | `domain_registration_operations.registrant_contact_update` | 등록자 연락처 변경 / Registrant-contact update | 등록도메인의 등록자 연락처를 변경하는 곳으로 가 줘 / Take me to update registrant contact data for the domain |
| C | `domain_registration_operations.nameserver_update` | 등록도메인 네임서버 변경 / Registered-domain nameserver update | 이 도메인의 권한 네임서버를 변경하는 화면으로 가 줘 / Take me to update authoritative nameservers for this domain |
| C | `domain_registration_operations.host_object_update` | 등록기관 호스트객체 변경 / Registrar host-object update | 이 도메인의 글루 호스트객체를 변경하는 곳으로 가 줘 / Take me to update the glue host object for this domain |
| C | `domain_registration_operations.auth_info_generate` | 이전 인증코드 생성 / Transfer AuthInfo generation | 도메인 이전용 AuthInfo 코드를 생성하는 화면으로 가 줘 / Take me to generate the AuthInfo code for domain transfer |
| C | `domain_registration_operations.transfer_lock_change` | 이전잠금 변경 / Transfer-lock change | 이 도메인의 등록기관 이전잠금을 변경하는 곳으로 가 줘 / Take me to change the inter-registrar transfer lock |
| C | `domain_registration_operations.transfer_initiate` | 등록기관 이전 개시 / Registrar-transfer initiation | 새 등록기관으로 도메인 이전을 개시하는 화면으로 가 줘 / Take me to initiate transfer of the domain to a new registrar |
| C | `domain_registration_operations.transfer_approve_reject` | 도메인 이전 승인·거절 / Domain-transfer approval or rejection | 대기 중인 도메인 이전을 승인하거나 거절하는 화면으로 가 줘 / Take me to approve or reject the pending domain transfer |
| C | `domain_registration_operations.registration_renew` | 도메인 등록기간 갱신 / Domain-registration renewal | 이 도메인의 등록기간을 갱신하는 곳으로 가 줘 / Take me to renew the registration term for this domain |
| C | `domain_registration_operations.auto_renew_change` | 자동갱신 설정변경 / Auto-renew setting change | 도메인 자동갱신 설정을 변경하는 화면으로 가 줘 / Take me to change the domain auto-renew setting |
| C | `domain_registration_operations.redemption_restore_request` | 상환유예 도메인 복구요청 / Redemption-period restore request | 상환유예 상태 도메인 복구를 요청하는 곳으로 가 줘 / Take me to request restoration of the domain in redemption period |
| C | `domain_registration_operations.registration_delete` | 도메인 등록삭제 / Domain-registration deletion | 이 도메인 등록삭제 화면으로 가 줘 / Take me to the domain-registration deletion screen |

Roles/assets/states: registrant, authorized administrative contact, registrar account owner, domain portfolio manager, and transfer approver; registered name, registrant/contact object, nameserver/host object, EPP status, AuthInfo, transfer, renewal/grace/redemption period; `available/registered/expired/redemption/pending-delete`, `locked/unlocked`, `transfer-pending/approved/rejected/completed`, and `verified/unverified`.

Boundary and collision guard: this is the registrar/registry lifecycle of a registered name. It excludes browser bookmarks/history (`browser_web`), vault credentials (`credential_vault`), generic subscription billing, and workspace account administration. It also does not manage DNS resource records. `domain`, `contact`, `renew`, `lock`, `transfer`, and `delete` require a registered name plus registrar/EPP state.

Primary-source seed pack:

1. RFC Editor, [RFC 5731 — EPP Domain Name Mapping](https://www.rfc-editor.org/rfc/rfc5731.html).
2. ICANN, [Domain Name Transfers](https://www.icann.org/en/contracted-parties/accredited-registrars/resources/domain-name-transfers).
3. ICANN, [EPP Status Codes List](https://www.icann.org/resources/pages/epp-status-codes-list-2014-06-18-en).
4. ICANN, [Registrants' Benefits and Responsibilities](https://www.icann.org/resources/pages/benefits-2013-09-16-en).
5. RFC Editor, [RFC 5730 — Extensible Provisioning Protocol](https://www.rfc-editor.org/rfc/rfc5730.html).
6. RFC Editor, [RFC 5732 — EPP Host Mapping](https://www.rfc-editor.org/rfc/rfc5732.html).
7. ICANN, [Transfer Policy](https://www.icann.org/en/contracted-parties/accredited-registrars/resources/domain-name-transfers/policy).
8. ICANN, [Registration Data Policy](https://www.icann.org/en/contracted-parties/consensus-policies/registration-data-policy).
9. ICANN, [Registration Data Reminder Policy](https://www.icann.org/en/contracted-parties/consensus-policies/registration-data-reminder-policy/registration-data-reminder-policy-21-02-2024-en).
10. ICANN, [Expired Registration Recovery Policy](https://www.icann.org/en/contracted-parties/consensus-policies/expired-registration-recovery-policy/expired-registration-recovery-policy-21-02-2024-en).
11. Cloudflare Registrar, [Renew Domains](https://developers.cloudflare.com/registrar/account-options/renew-domains/).

Terminal evidence map: sources 1, 3, 5, 8, and 10 support `domain_registration_operations.portfolio_expiry_status`, `domain_registration_operations.registration_data_view`, `domain_registration_operations.epp_status_view`, `domain_registration_operations.renewal_status`, and `domain_registration_operations.security_lock_status`; sources 1 and 6 support `domain_registration_operations.nameserver_delegation_view`, `domain_registration_operations.nameserver_update`, and `domain_registration_operations.host_object_update`; sources 1, 4, 5, and 8 support `domain_registration_operations.registration_create`; sources 4, 8, and 9 support `domain_registration_operations.registrant_contact_verify` and `domain_registration_operations.registrant_contact_update`; sources 1–3 and 7 support `domain_registration_operations.transfer_status`, `domain_registration_operations.auth_info_generate`, `domain_registration_operations.transfer_lock_change`, `domain_registration_operations.transfer_initiate`, and `domain_registration_operations.transfer_approve_reject`; sources 1, 5, and 10 support `domain_registration_operations.registration_renew`, `domain_registration_operations.redemption_restore_request`, and `domain_registration_operations.registration_delete`; source 11 supports `domain_registration_operations.auto_renew_change` only for a Cloudflare Registrar-managed name. These standards and policies distinguish registrant, sponsoring/gaining/losing registrar, registry, and authorized account roles and support available→registered, unverified→verified/updated, unlocked→locked, transfer-pending→approved/rejected/completed, active→expired→redemption→restored/pending-delete, and renewal-off→on transitions. ICANN consensus-policy claims are limited to applicable gTLD contracted parties, while registrar-specific controls must abstain outside the identified registrar.

## Primary-source pack contract

The lists above define **exactly 131 source slots**, distributed across sections 1–12 as **8, 8, 8, 10, 9, 17, 12, 11, 11, 11, 15, and 11**. Every domain has at least four independently scoped authoritative primary-source URLs; the larger packs are required where authority, asset, and transition evidence spans distinct provisions or provider workflows. They are seed artifacts for implementation, not a claim that retrieval, hashing, or machine-readable terminal mappings have already been materialized.

Implementation must enforce all of the following:

1. Each source record stores `source_id`, publisher, exact title, canonical URL, retrieval timestamp, collection date, HTTP status, final URL, MIME type, `official_primary` evidence level, verification method/status, content SHA-256 when bytes are retrievable, jurisdiction, supported roles/assets/states, and explicit `terminal_ids`.
2. Every terminal cites at least one accepted source. The union of each domain's accepted source mappings equals its exact 20-terminal set, and each `C` terminal cites a source that supports the actor's authority and the proposed state transition—not only shared vocabulary.
3. A source may support several terminals, but there are no orphan sources or unmapped terminals. Multiple URLs from one publisher may be accepted only when they are independently scoped authoritative artifacts rather than duplicate renderings of one page.
4. Regulations, official manuals, official program instructions, formal standards, and first-party platform operating documentation are eligible. Search-result pages, press coverage, community posts, screenshots, reseller instructions, copied manuals, and independent-evaluation data are ineligible. Apple/Google product documentation is eligible here only as first-party authority for their own developer-store lifecycle.
5. URL identity is computed after lowercasing scheme/host, removing a default port, normalizing dot segments, retaining a meaningful query string, and dropping fragments. The 131 planned canonical URL strings must remain **131 normalized unique HTTPS URLs**, both globally and per domain.
6. Redirects are recorded; a replacement is allowed only for a primary artifact with equal or greater authority and scope. Replacements may not reduce the applicable per-domain count or the 131-total count and must be rechecked for normalized uniqueness.
7. Jurisdiction is explicit. U.S. federal materials do not silently establish a non-U.S., state, local, tribal, school-district, airport, dam, plan, station, registrar, store, or other regulated-program authority. The resolver abstains when the controlling jurisdiction or organization cannot be established.

## Append-only and function-equivalence audit

The proposal deliberately avoids every reviewed `true_equivalent` class in the v14 equivalence overlay: cart, conversation mute/archive/delete, emergency contacts, government office appointment, SOS, laboratory results, safety check, and emergency profile. It also adds no synonym of the reviewed parent-child groups (menu/drawer, default-app setting, login entry/action, permission management/action, return entry/action, help/FAQ, spam report/action, content-rating scope) or unsafe-to-merge groups (cancel/refund, login challenge/MFA setting, contact upload/sync, location-sharing scope, purchase request/approval, government login/identity proofing, and game/family content sharing).

Exact-ID uniqueness is necessary but not sufficient. Before any V15 materialization, build semantic signatures of `authorized actor + governed asset + jurisdiction/facility + lifecycle state or transition + real-world consequence` for all existing and proposed terminals. A V15 row must be removed or redesigned if an existing terminal has the same signature, even when its ID, Korean wording, English wording, or provider differs.

The current mechanical comparison against canonical v14 found **zero intersections** for the 12 proposed domain IDs, 252 proposed function IDs, and 240 generated intent IDs. Unicode NFKC plus case, punctuation, symbol, and spacing normalization also found zero exact collisions among the 480 bilingual function-name strings and zero exact collisions between the 480 bilingual representative-goal strings and existing intent patterns. Three proposed terminals produce three generic suffix-only pairs with prior IDs—`reporting_calendar`, `transfer_status`, and `referral_intake`. They remain separate only because the domain guards above require different authorities, assets, and lifecycle states; the independent collision set must exercise every pair.

The hardest mandatory contrast sets are:

| V15 domain | Nearest prior domains | Required non-equivalence boundary |
|---|---|---|
| `airport_airside_operations` | `air_traffic_control_ops`, `aviation_maintenance_ops`, `emergency_response_operations` | airport operator + certified movement-area asset, not flight clearance, aircraft maintenance, or incident command |
| `federal_records_disposition_ops` | `documents_cloud`, `legal_practice_ops`, `museum_collections_ops`, `privacy` | federal records series + NARA-approved disposition authority/cutoff/hold/transfer state, not document editing, matter files, collection accession, or privacy-request handling |
| `doj_foia_case_processing` | `customer_support_agent`, `legal_practice_ops`, `privacy`, `court_clerk_case_admin` | DOJ FOIA request + component case, search/referral/exemption/release/appeal state, not support tickets, legal-matter workflow, generic data-subject requests, or court dockets |
| `dam_safety_operations` | `water_wastewater_plant_ops`, `power_generation_plant_ops`, `utility_grid_field_ops` | dam/project works + impoundment safety or EAP state, not water treatment, generating-unit dispatch, or grid restoration |
| `nlrb_representation_case_ops` | `court_clerk_case_admin`, `election_administration`, `hr_payroll`, `legal_practice_ops` | NLRB representation petition + bargaining-unit/showing-of-interest/hearing/election/certification state, not court filing, public-election administration, workforce payroll, or private matter management |
| `special_education_program_admin` | `education`, `classroom_instructor_ops`, `higher_education_student_admin`, `social_services_casework` | IDEA student + evaluation/eligibility/IEP/placement state, not learning content, grading, registrar work, or public benefits |
| `pension_plan_administration` | `hr_payroll`, `finance_long_tail`, `retail_banking`, `business_accounting` | governed retirement plan + participant rights/claims/filings, not employee self-service, investing, banking, or a company ledger |
| `campaign_finance_compliance` | `election_administration`, `crowdfunding_donations`, `business_accounting` | regulated committee + FEC reporting period/schedule, not ballots, consumer giving, or ordinary bookkeeping |
| `export_control_authorization_ops` | `freight_forwarding_customs_ops`, `financial_crime_compliance_ops`, `procurement_supplier_ops` | EAR item/ECCN + destination/end use + BIS authorization, not customs entry, sanctions case, or purchasing |
| `broadcast_station_compliance` | `content`, `marketing`, `emergency_communications_dispatch` | FCC licensee/facility + service-class filing, not content creation, advertising, or emergency dispatch |
| `app_store_release_management` | `app_store`, `code_repository`, `workspace_administration` | developer-store app version/build/submission/track state, not consumer installs/refunds, source merge, or generic membership |
| `domain_registration_operations` | `browser_web`, `credential_vault`, `subscription`, `workspace_administration` | registered name + registrar/EPP lifecycle, not browsing, passwords, recurring billing, DNS records, or workspace accounts |

Implementation validation must:

- compare exact domain/function/intent IDs against the canonical v14 payload and fail on any intersection;
- normalize all Korean/English names, aliases, patterns, context, and negative context with Unicode NFKC, case folding, punctuation/spacing normalization, conservative stemming, and reviewed synonym expansion;
- compare every proposed signature with all physical and logical existing destinations, including alias member IDs;
- require at least two positive discriminators and one nearest-rival negative discriminator for every shared verb or noun;
- run bidirectional retrieval probes so V15 goals do not steal v1–v14 goals and prior goals do not falsely capture V15;
- emit a machine-readable report per proposed terminal with exact-match, normalized phrase, semantic-neighbor, equivalence-class, role/asset/state, and decision fields;
- accept only with zero unresolved `same_goal`, `same_transition`, `true_equivalent`, `unsafe_alias`, or wrong-safety-envelope findings.

## Independent evaluation design

The frozen V15 evaluation set must be written after the catalog and source mappings are frozen by a reviewer who cannot inspect generator aliases, goal rules, source paraphrases, or collision probes. It is never imported by a source module. The exact evaluation design is **960 cases**:

| Slice | Cases | Construction |
|---|---:|---|
| Positive Korean goals | 240 | One independently written Korean goal per terminal |
| Positive English goals | 240 | One independently written English goal per terminal; not a translation of the Korean item |
| Prior-catalog collision goals | 240 | Twenty nearest-rival v1–v14 goals per proposed domain |
| Within-V15 collision goals | 120 | Ten goals per domain whose shared noun/verb points elsewhere without role/asset/state |
| Underspecified or unsafe abstention goals | 120 | Ten per domain missing authority, asset identity, jurisdiction, lifecycle state, or required approval |
| **Total** | **960** | **480 positive routing + 360 collision + 120 abstention** |

No case may contain a package name, resource ID, coordinate, fixed click path, screenshot-derived label, exact catalog alias sentence, or copied source sentence. Report top-1/top-3 by locale, domain, and class; abstention accuracy; v1–v14 regression; unsafe cross-domain routing; and final-action safety.

## Implementation acceptance criteria

V15 is accepted only when all of the following hold:

- The canonical append is exactly 12 domains, 252 physical functions, 240 terminal functions, and 240 intents. Physical totals are exactly **179 domains, 2,866 functions, 2,660 terminal functions, and 2,660 intents**.
- The known equivalence overlay remains unchanged for prior IDs and gains no V15 member. Logical totals are exactly **2,856 functions, 2,650 intents, and 2,648 unique default-terminal destinations**.
- Every domain has exactly one low-risk hub, 7 `S` terminals, 13 `C` terminals, and 20 one-to-one intents. V15 therefore has exactly 12 safe-navigation hubs, 84 high-risk read-only terminals, and 156 high-risk state-changing terminals.
- Every terminal has bilingual function names, bilingual representative intents, positive and negative context, role hints, state cues, risk cues, and a two-step conceptual route ending at its own terminal ID.
- All 240 terminals are `high + never_auto + before_action + user_owned_final_press`; all and only the 156 `C` rows are state-changing. There is no alternate final action through voice, keyboard, deep link, retry, or accessibility action.
- Exactly 131 accepted primary-source records exist with the section 1–12 distribution 8/8/8/10/9/17/12/11/11/11/15/11, and their normalized canonical URLs are all HTTPS and globally unique. Every source is mapped, every terminal is supported, and every consequential transition has authority-specific evidence.
- Exact domain/function/intent collision count is zero. The semantic/equivalence report has zero unresolved findings, and existing function/intent records remain byte-for-byte unchanged except for permitted append-only catalog metadata and version fields.
- Independent positives achieve top-1 at least 94% overall in each locale, top-1 at least 85% in every domain/class/locale cell, and top-3 at least 98.5% overall.
- At least 98% of the 360 collision goals retain their intended prior or V15 rival; V15 false capture of prior goals is at most 2% overall and at most 5% per domain.
- At least 95% of unsafe/underspecified cases abstain or stop at the correct hub. No underspecified goal resolves to a `C` terminal, and there are zero wrong-asset, wrong-role, wrong-jurisdiction, bypass, or automated-final-action cases.
- The full catalog-quality, bilingual alias, semantic-equivalence, independent-coverage, robustness, performance, deterministic-build, and idempotence suites pass without relaxing an existing threshold. Two clean materializations produce identical payload hashes.

## Audit limits

This document is an append-only source-level coverage plan. It does not prove that a particular product exposes any listed destination, that the resolver can locate it in a first-seen UI, or that a real user has authority to perform the operation. It creates no source module, catalog row, fixture, app path, or accuracy claim. Retrieval and hashing of the 131 sources, jurisdiction-specific refinement, implementation, semantic collision probes, sealed evaluation authoring, and real-device validation remain separate follow-on work.
