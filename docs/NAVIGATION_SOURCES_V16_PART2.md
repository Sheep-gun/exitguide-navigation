# Navigation V16 official-source verification — part 2

검증일: **2026-07-30**
검증 범위: `NAVIGATION_COVERAGE_GAPS_V16.md`의 도메인 **7~12**만 해당
검증 대상: 후보 URL 41개와, 접근 불가·의미 불충분 후보의 공식 대체 출처

## 1. 판정 기준과 한계

- 각 HTTPS URL을 실제로 열어 응답 여부, 리디렉션 후 최종 URL, 문서 본문을 확인했다.
- `accepted`는 현재 읽을 수 있고 해당 기관이 직접 운영·발행한 1차 출처이며, 제안된 role/asset/state/terminal 중 명시한 범위를 뒷받침한다는 뜻이다.
- `accepted (redirect)`는 원 URL이 같은 기관의 읽을 수 있는 최종 URL로 이동했고, 최종 문서가 필요한 범위를 뒷받침한다는 뜻이다. 합계에서는 `accepted`로 센다.
- `replaced`는 원 후보가 이 검증 환경에서 읽히지 않거나, 읽히더라도 도메인 terminal 근거로 의미가 부족하여, 읽을 수 있는 동급 이상의 공식 1차 출처로 교체했다는 뜻이다.
- `rejected`는 사용할 수 없고 공식 대체 출처도 확보하지 못한 경우다. 이번 범위에는 없다.
- `HTTP 200`은 검증기가 본문을 읽은 경우다. `403`, `502`, CAPTCHA, safe-open 차단, internal error는 **이 검증 실행에서 재현된 관찰값**이며 사이트가 모든 환경에서 영구적으로 중단됐다는 뜻은 아니다.
- 출처가 규제 의무나 업무 개념을 뒷받침한다고 해서 특정 제품 UI, 버튼, API 또는 자동 실행 terminal이 실제로 존재한다고 추정하지 않았다. 아래 source gap은 그 구분을 보존한다.
- 정규화 URL은 scheme/host 소문자화, 기본 포트 제거, fragment 제거, 중복 `/` 및 끝 `/` 정리, query parameter 정렬 방식으로 비교했다. 내용이 다른 경로는 별도 URL로 유지했다.

## 2. 전체 결과

| 도메인 | 원 후보 | accepted | replaced | rejected | 최종 usable 공식 출처 | 미해결 terminal/source-gap |
|---|---:|---:|---:|---:|---:|---:|
| 7. `wireless_spectrum_license_ops` | 6 | 0 | 6 | 0 | 6 | 4 |
| 8. `commercial_space_launch_licensing_ops` | 7 | 6 | 1 | 0 | 7 | 2 |
| 9. `radioactive_materials_license_ops` | 7 | 6 | 1 | 0 | 7 | 4 |
| 10. `hazardous_materials_transport_compliance` | 7 | 4 | 3 | 0 | 7 | 4 |
| 11. `firearms_dealer_compliance_ops` | 7 | 5 | 2 | 0 | 7 | 3 |
| 12. `commercial_vessel_safety_compliance` | 7 | 3 | 4 | 0 | 7 | 5 |
| **합계** | **41** | **24** | **17** | **0** | **41** | **22** |

최종 usable URL 41개를 위 방식으로 정규화한 결과, **중복 URL은 0개**다. `replaced` 행에서는 원 후보가 아니라 표에 기재한 대체 URL을 최종 usable 집합에 포함했다.

## 3. 도메인 7 — `wireless_spectrum_license_ops`

기관 범위: Federal Communications Commission(FCC). `fcc.gov`, `docs.fcc.gov`, `opendata.fcc.gov`, `consumercomplaints.fcc.gov`는 모두 FCC가 직접 운영하거나 FCC 문서를 직접 배포하는 1차 도메인이다.

| # | 검증일 | 원 후보와 접근 관찰 | 판정 및 최종 usable URL | 확인된 terminal ID 또는 scope |
|---:|---|---|---|---|
| 7-1 | 2026-07-30 | [FCC ULS](https://www.fcc.gov/wireless/universal-licensing-system) — 이 실행에서 HTTP 403, 본문 미확보 | **replaced** → [FCC Open Data: Universal Licensing System](https://opendata.fcc.gov/Wireless/FCC-Universal-Licensing-System-ULS-/x28i-i4z4/data), HTTP 200 | FCC가 ULS의 전자 신청, application purpose/service code, 제출 안내, application/license 검색과 위치·권역 표시 기능을 명시한다. `license_portfolio_status`, `authorized_frequency_location_view`, `application_status`, `new_license_application`, `application_submit`, `license_modification_apply`의 시스템·자산 범위 근거. 2017 메타데이터이므로 현재 기한 수치 근거로는 사용하지 않는다. |
| 7-2 | 2026-07-30 | [ULS online filing](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources/online-filing) — safe-open 단계에서 읽을 수 있는 본문 미확보 | **replaced** → [FCC Public Notice DA-22-65](https://docs.fcc.gov/public/attachments/DA-22-65A1.pdf), PDF 열람 성공 | 모든 wireless application의 전자 filing, renewal, construction notification, expiration/construction deadline 및 미이행 시 취소 가능성을 확인. `application_submit`, `renewal_application_submit`, `construction_notification_file`, `construction_deadline_status`, `buildout_compliance_status`. |
| 7-3 | 2026-07-30 | [47 CFR Part 1, eCFR](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-1) — `unblock.federalregister.gov` CAPTCHA로 이동, 규정 본문 미확보 | **replaced** → [FCC Public Notice DA-21-693](https://docs.fcc.gov/public/attachments/DA-21-693A1.pdf), PDF 열람 성공. 원 Part 1 전체와 동등한 대체는 아니며 V16에 필요한 STA 범위만 좁혀 채택 | STA 요청·승인, 장소·주파수, 180일 상태, 조건, 조정 및 간섭 조건을 확인. `special_temporary_authority_status`, `special_temporary_authority_request`, `interference_coordination_status`의 제한된 범위. |
| 7-4 | 2026-07-30 | [ULS renewing a license](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources/renewing-license-universal-licensing-system) — safe-open 단계에서 본문 미확보 | **replaced** → [FCC Public Notice DA-04-1408](https://docs.fcc.gov/public/attachments/DA-04-1408A1.pdf), PDF 열람 성공 | late renewal 및 ULS filing 절차를 확인. `renewal_application_submit`, `application_status`. 2004 문서이므로 현행 마감일 숫자나 현재 UI 레이블은 채택하지 않고 workflow vocabulary에만 사용. |
| 7-5 | 2026-07-30 | [ULS transferring control or assigning a license](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources/transferring-control-or-assigning-license) — safe-open 단계에서 본문 미확보 | **replaced** → [FCC Public Notice DA-20-567](https://docs.fcc.gov/public/attachments/DA-20-567A1.pdf), PDF 열람 성공 | 47 CFR §1.948, Forms 601/603, assignment/transfer of control과 승인 상태를 확인. `assignment_transfer_application`, `control_transfer_consent_request`, 관련 `license_portfolio_status`. |
| 7-6 | 2026-07-30 | [ULS resources](https://www.fcc.gov/wireless/support/universal-licensing-system-uls-resources) — safe-open 단계에서 본문 미확보 | **replaced** → [FCC Internet complaint issue descriptions](https://consumercomplaints.fcc.gov/hc/en-us/articles/115002206106-Internet-Form-Descriptions-of-Complaint-Issues), HTTP 200 | FCC complaint form에서 interference issue와 complaint 시작 경로를 확인. `interference_complaint_submit`의 소비자 complaint 범위. 면허인 간 기술 간섭 조정 절차 전체로 확대 해석하지 않는다. |

**도메인 결과:** usable 공식 출처 **6개**. 역할은 applicant/licensee, FCC licensing authority, complainant 범위로 확인되고, 자산은 application, license/call sign, location/frequency, construction/renewal deadline, STA, assignment/transfer 및 complaint다.

**미해결 source gap 4개:** `frequency_coordination_attach`, `buildout_certification_submit`, `license_cancellation_request`, `discontinuance_notice_file`. 현재 출처는 coordination/buildout/cancellation 개념을 일부 보여 주지만, 서로 다른 radio service에 공통인 독립 제출 terminal의 입력·상태·완료 의미까지 입증하지 않는다. service-specific FCC rule/form 출처가 추가되기 전에는 generic UI terminal로 materialize하지 않는다.

## 4. 도메인 8 — `commercial_space_launch_licensing_ops`

기관 범위: Federal Aviation Administration Office of Commercial Space Transportation(FAA AST)와 eCFR. 두 도메인 모두 미국 정부의 공식 1차 출처다.

| # | 검증일 | 원 후보와 접근 관찰 | 판정 및 최종 usable URL | 확인된 terminal ID 또는 scope |
|---:|---|---|---|---|
| 8-1 | 2026-07-30 | [FAA commercial space licenses](https://www.faa.gov/space/licenses) — HTTP 200, 최종 URL 동일 | **accepted** | FAA AST의 launch/reentry, launch/reentry site, safety approval 권한과 vehicle operator, payload review, financial responsibility 범위를 확인. `operator_license_profile`, `vehicle_site_configuration_view`, `license_application_create`, `launch_mission_authorization_request`의 상위 asset/authority scope. |
| 8-2 | 2026-07-30 | [FAA licensing process](https://www.faa.gov/space/licenses/licensing_process) — HTTP 200, 최종 URL 동일 | **accepted** | pre-application, application evaluation, issuance/denial, post-license compliance, modification 및 renewal 단계. `preapplication_consultation_record`, `application_review_status`, `license_application_submit`, `license_modification_request`. |
| 8-3 | 2026-07-30 | [FAA vehicle operator licenses and permits](https://www.faa.gov/space/licenses/operator_licenses_permits) — HTTP 200, 최종 URL 동일 | **accepted** | Part 450 operator license, checklist, pre-application, safety/environmental review. `safety_review_status`, `environmental_review_status`, `safety_analysis_submit`, `environmental_information_submit`, `license_application_create`. |
| 8-4 | 2026-07-30 | [FAA financial responsibility](https://www.faa.gov/space/licenses/financial_responsibility) — HTTP 200, 최종 URL 동일 | **accepted** | maximum probable loss, insurance/evidence 및 reciprocal waiver of claims. `financial_responsibility_status`, `financial_responsibility_evidence_submit`. |
| 8-5 | 2026-07-30 | [FAA compliance, enforcement and mishap](https://www.faa.gov/space/compliance_enforcement_mishap) — HTTP 200, 최종 URL 동일 | **accepted** | mission readiness와 pre-operational/operational/post-operational compliance, mishap 및 return-to-flight 자료 범위. `mishap_event_report_submit`, `return_to_flight_request`, `launch_readiness_certify`의 업무 개념. |
| 8-6 | 2026-07-30 | [14 CFR Part 450, eCFR](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-450) — `unblock.federalregister.gov` CAPTCHA로 이동, 규정 본문 미확보 | **replaced** → [FAA payload reviews](https://www.faa.gov/space/licenses/payload_reviews), HTTP 200 | 14 CFR 450.43 payload review, ownership/function, trajectory, hazardous material, orbit 및 site 정보. `payload_review_status`, `payload_review_submit`. |
| 8-7 | 2026-07-30 | [14 CFR Part 440, eCFR](https://www.ecfr.gov/current/title-14/chapter-III/subchapter-C/part-440) — HTTP 200, 최종 URL 동일 | **accepted** | `Financial Responsibility` 규정 본문. `financial_responsibility_status`, `financial_responsibility_evidence_submit`의 법적 asset/state scope와 waiver 관계. |

**도메인 결과:** usable 공식 출처 **7개**. 역할은 applicant/operator, payload owner, FAA reviewer 및 insurer/financial-responsibility participant로, 자산은 operator license, vehicle/site configuration, safety/payload/environmental review, financial evidence, mission compliance와 mishap case로 확인된다.

**미해결 source gap 2개:** `launch_mission_authorization_request`, `launch_readiness_certify`. 출처는 licensed mission과 readiness/compliance 활동은 뒷받침하지만, 모든 operator에게 공통인 별도의 “mission authorization request” 또는 “readiness certify” 제출 화면이 존재한다고 입증하지 않는다. 이 둘은 현 단계에서 workflow abstraction으로만 유지해야 한다.

## 5. 도메인 9 — `radioactive_materials_license_ops`

기관 범위: U.S. Nuclear Regulatory Commission(NRC)와 eCFR. 모두 공식 연방 1차 출처다.

| # | 검증일 | 원 후보와 접근 관찰 | 판정 및 최종 usable URL | 확인된 terminal ID 또는 scope |
|---:|---|---|---|---|
| 9-1 | 2026-07-30 | [NRC Web-Based Licensing](https://www.nrc.gov/security/byproduct/ismp/wbl) — HTTP 200, 최종 URL 동일 | **accepted** | initial application, amendment, renewal, termination, online Form 313와 processing status. `materials_license_profile`, `license_application_submit`, `license_amendment_request`, `license_termination_request`, `inspection_enforcement_status`의 licensing-system scope. |
| 9-2 | 2026-07-30 | [NRC Integrated Source Management Portfolio](https://www.nrc.gov/security/byproduct/ismp) — HTTP 200, 최종 URL 동일 | **accepted** | WBL, NSTS, LVS의 통합 관계와 licensing/source tracking 범위. `materials_license_profile`, `authorized_use_location_view`, `sealed_source_inventory_status`, `personnel_authorization_status`. |
| 9-3 | 2026-07-30 | [NSTS overview `.html`](https://www.nrc.gov/security/byproduct/ismp/nsts/overview.html) — NRC의 [확장자 없는 최종 URL](https://www.nrc.gov/security/byproduct/ismp/nsts/overview)로 이동, HTTP 200 | **accepted (redirect)** | Category 1/2 source를 manufacture부터 shipment receipt, decay, burial까지 추적하고 licensee/facility/source identity를 관리. `sealed_source_inventory_status`, `sealed_source_transfer_record`, `source_receipt_inventory_record`. |
| 9-4 | 2026-07-30 | [10 CFR Part 30, NRC collection](https://www.nrc.gov/reading-rm/doc-collections/cfr/part030/) — `unblock.federalregister.gov` CAPTCHA 경로로 이동, 본문 미확보 | **replaced** → [NRC materials licensing](https://www.nrc.gov/materials/miau/licensing), HTTP 200 | specific license의 possession/use, new/amendment/renewal, user·material use·transfer 변경, 역할·수량·시설·radiation protection. `authorized_use_location_view`, `radiation_safety_program_status`, `authorized_user_add_remove`, `possession_limit_change_request`, `license_amendment_request`. |
| 9-5 | 2026-07-30 | [10 CFR 20.2207](https://www.nrc.gov/reading-rm/doc-collections/cfr/part020/part020-2207.html) — [eCFR 10 CFR Part 20](https://www.ecfr.gov/current/title-10/chapter-I/part-20)으로 이동, HTTP 200 | **accepted (redirect)** | nationally tracked source transaction reports와 annual inventory reconciliation의 규정 scope. `sealed_source_transfer_record`, `source_receipt_inventory_record`, `annual_inventory_certify`, `lost_stolen_material_report`. 최종 URL이 section 단위가 아니므로 구현 시 §20.2207 문맥을 함께 보존해야 한다. |
| 9-6 | 2026-07-30 | [NSTS FAQs](https://www.nrc.gov/security/byproduct/ismp/nsts/faqs) — HTTP 200, 최종 URL 동일 | **accepted** | Category 1/2 identifier, licensee/facility/contact, transfer 및 annual inventory verification. `sealed_source_inventory_status`, `sealed_source_transfer_record`, `source_receipt_inventory_record`, `annual_inventory_certify`. |
| 9-7 | 2026-07-30 | [NRC event assessment](https://www.nrc.gov/about-nrc/regulatory/event-assess) — HTTP 200, 최종 URL 동일 | **accepted** | reportable event, NRC review와 notification의 상위 범위. `event_reporting_status`, `lost_stolen_material_report`, `medical_event_report_submit`의 event authority scope만 확인. |

**도메인 결과:** usable 공식 출처 **7개**. 역할은 licensee, authorized user/RSO, transferor/recipient와 NRC/Agreement State reviewer로, 자산은 materials license, authorized location/use, tracked source inventory/transaction, radiation program 및 reportable event다.

**미해결 source gap 4개:** `leak_test_result_certify`, `radioactive_material_shipment_authorize`, `medical_event_report_submit`, `decommissioning_plan_submit`. event assessment나 일반 licensing 출처만으로는 각각의 적용 대상, 제출 조건, 수신 기관과 완료 상태를 충분히 분리할 수 없다. `annual_inventory_certify`는 NSTS/§20.2207이 직접 뒷받침하므로 gap에 포함하지 않았지만, UI 레이블은 출처에서 추정하지 않는다.

## 6. 도메인 10 — `hazardous_materials_transport_compliance`

기관 범위: Pipeline and Hazardous Materials Safety Administration(PHMSA)와 eCFR. 모두 공식 연방 1차 출처다.

| # | 검증일 | 원 후보와 접근 관찰 | 판정 및 최종 usable URL | 확인된 terminal ID 또는 scope |
|---:|---|---|---|---|
| 10-1 | 2026-07-30 | [49 CFR Part 171](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-171) — HTTP 200, 최종 URL 동일 | **accepted** | applicability, classification, package, mark/label, shipping paper, emergency information, certification, offeror/carrier 및 incident reporting. `shipping_description_review`, `material_classification_record`, `shipping_paper_issue`, `carrier_acceptance_record`, `incident_initial_notice`, `incident_report_submit`. |
| 10-2 | 2026-07-30 | [49 CFR Part 172](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-172) — `unblock.federalregister.gov` CAPTCHA로 이동, 본문 미확보 | **replaced** → [PHMSA hazmat training modules](https://www.phmsa.dot.gov/training/hazmat/training-modules), HTTP 200 | Hazardous Materials Table, shipping papers, marking, labeling, placarding, packaging, modal/security/training 범위. `shipping_description_review`, `marking_label_placard_record`, `employee_training_certify`, `security_plan_status`. 2021 교육자료이며 HMR 자체를 대체하지 않는다는 PHMSA 경고를 보존한다. |
| 10-3 | 2026-07-30 | [49 CFR Part 173](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-173) — HTTP 200, 최종 URL 동일 | **accepted** | shipper와 packaging의 일반 요구 및 특정 물질별 packaging authorization. `packaging_authorization_view`, `package_selection_certify`, `material_classification_record`. |
| 10-4 | 2026-07-30 | [49 CFR Part 107](https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-A/part-107) — `unblock.federalregister.gov` CAPTCHA로 이동, 본문 미확보 | **replaced** → [PHMSA special permits overview](https://www.phmsa.dot.gov/hazmat/special-permits/special-permits-overview), HTTP 200 | special permit authority, application, status/search, renewal 및 emergency processing. `special_permit_status`, `special_permit_application_submit`. |
| 10-5 | 2026-07-30 | [PHMSA registration overview](https://www.phmsa.dot.gov/registration/registration-overview) — HTTP 200, 최종 URL 동일 | **accepted** | hazmat registration 대상과 registration process/status 범위. `hazmat_registration_status`, `hazmat_registration_submit`. |
| 10-6 | 2026-07-30 | [기존 PHMSA approvals/special permits URL](https://www.phmsa.dot.gov/approvals-and-permits/hazmat/special-permits) — 이 실행에서 internal error, 본문 미확보 | **replaced** → [PHMSA special permit applications](https://www.phmsa.dot.gov/hazmat/special-permits/special-permits-applications), HTTP 200 | online application, 신청 checklist와 examples. `special_permit_application_submit`, 관련 `special_permit_status`. |
| 10-7 | 2026-07-30 | [PHMSA incident reporting](https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-reporting) — HTTP 200, 최종 URL 동일 | **accepted** | hazmat incident reporting의 initial notice와 report 흐름. `incident_case_status`, `incident_initial_notice`, `incident_report_submit`. |

**도메인 결과:** usable 공식 출처 **7개**. 역할은 offeror/shipper, carrier, hazmat employer/employee, registrant, special-permit applicant 및 PHMSA reviewer로, 자산은 material classification, package, shipping communication, training/security record, registration, special permit와 incident case다.

**미해결 source gap 4개:** `route_plan_approve`, `carrier_acceptance_record`, `security_plan_approve`, `package_nonconformance_hold`. 규정·교육 출처는 관련 의무를 설명하지만 이 네 이름은 내부 operator workflow에 가까우며, 모든 운송 mode에 공통인 규제기관 제출/완료 terminal을 입증하지 않는다. mode와 material class별 규정 출처가 추가되기 전에는 내부 기록과 외부 제출을 분리해야 한다.

## 7. 도메인 11 — `firearms_dealer_compliance_ops`

기관 범위: Bureau of Alcohol, Tobacco, Firearms and Explosives(ATF), Federal Bureau of Investigation(FBI)와 eCFR. 최종 usable 집합은 읽을 수 있는 ATF/eCFR 1차 출처로 구성했다.

| # | 검증일 | 원 후보와 접근 관찰 | 판정 및 최종 usable URL | 확인된 terminal ID 또는 scope |
|---:|---|---|---|---|
| 11-1 | 2026-07-30 | [27 CFR Part 478](https://www.ecfr.gov/current/title-27/chapter-II/subchapter-B/part-478) — HTTP 200, 최종 URL 동일 | **accepted** | FFL licensing, records, transfer/background-check, reports, theft/loss 및 discontinued-business records의 법적 범위. 이 도메인의 role/asset/state 기준 출처. |
| 11-2 | 2026-07-30 | [ATF applications/eForms](https://www.atf.gov/firearms/applications-eforms) — [ATF eForms applications](https://www.atf.gov/firearms/forms/eforms-applications)로 이동해 HTTP 200이나, 본문은 주로 NFA eForms이며 dealer operations 전체 근거로 불충분 | **replaced** → [ATF resources for current licensees](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees), HTTP 200 | FFL renewal, expiration, license operation 및 current-licensee tools. `license_profile_status`, `license_renewal_submit`, `license_surrender_closeout`의 license-side scope. |
| 11-3 | 2026-07-30 | [ATF apply for a license](https://www.atf.gov/firearms/apply-license) — [최종 apply-for-a-license URL](https://www.atf.gov/firearms/tools-and-services-firearms-industry/apply-for-a-license)로 이동, HTTP 200 | **accepted (redirect)** | application, responsible person 및 background review. `license_application_submit`, `responsible_person_roster`, `responsible_person_update`. |
| 11-4 | 2026-07-30 | [FBI NICS](https://www.fbi.gov/how-we-can-help-you/more-fbi-services-and-information/nics) — 이 실행에서 internal error, 본문 미확보 | **replaced** → [ATF FFL quick-reference and best-practices guide](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/federal-firearms-licensee-quick-reference-and-best-practices-guide), HTTP 200 | NICS proceed/delayed/denied 상태, A&D records, Form 4473, multiple sales, trace, theft/loss, inspections, responsible persons, renewal와 discontinued records. `background_check_case_status`, `background_check_initiate`, `firearm_acquisition_record`, `transferee_identity_record`, `transfer_disposition_record`, `multiple_sale_report_submit`, `inspection_correction_status`. |
| 11-5 | 2026-07-30 | [ATF eTrace fact sheet](https://www.atf.gov/resource-center/fact-sheet/fact-sheet-etrace-internet-based-firearms-tracing-and-analysis) — [최종 eTrace fact-sheet URL](https://www.atf.gov/resource-center/fact-sheet/etrace-internet-based-firearms-tracing-and-analysis)로 이동, HTTP 200 | **accepted (redirect)** | 인터넷 기반 firearms trace request/analysis 범위. `trace_request_queue`, `trace_response_submit`. |
| 11-6 | 2026-07-30 | [ATF report firearms theft or loss](https://www.atf.gov/firearms/report-firearms-theft-or-loss) — [최종 current-licensees theft/loss URL](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/report-firearms-theft-or-loss)로 이동, HTTP 200 | **accepted (redirect)** | FFL의 theft/loss report 대상과 제출 흐름. `theft_loss_case_status`, `theft_loss_report_submit`. |
| 11-7 | 2026-07-30 | [ATF firearms forms](https://www.atf.gov/firearms/forms) — HTTP 200, 최종 URL 동일 | **accepted** | license, responsible person, acquisition/disposition, transfer, multiple sale, theft/loss와 records disposition에 쓰이는 공식 forms catalog. 관련 command terminal의 form-asset scope. |

**도메인 결과:** usable 공식 출처 **7개**. 역할은 applicant/licensee, responsible person, transferor/dealer, transferee, ATF/FBI reviewer로, 자산은 FFL, responsible-person roster, A&D inventory, Form 4473/NICS case, trace request, theft/loss case와 inspection record다.

**미해결 source gap 3개:** `inventory_discrepancy_record`, `inspection_correction_status`, `license_surrender_closeout`. 첫 두 이름은 내부 case-management abstraction에 가까우며 별도의 연방 submit terminal이 명확하지 않다. 마지막 이름은 license surrender와 out-of-business records transfer라는 서로 다른 행위를 한 terminal로 합친 형태이므로 분리 출처와 분리 terminal이 필요하다.

## 8. 도메인 12 — `commercial_vessel_safety_compliance`

기관 범위: U.S. Coast Guard(USCG)와 eCFR. `uscg.mil` 및 `dco.uscg.mil`/`dcms.uscg.mil`은 Coast Guard가 직접 운영하는 공식 1차 도메인이다.

| # | 검증일 | 원 후보와 접근 관찰 | 판정 및 최종 usable URL | 확인된 terminal ID 또는 scope |
|---:|---|---|---|---|
| 12-1 | 2026-07-30 | [USCG Homeport](https://homeport.uscg.mil/) — HTTP 502, 본문 미확보 | **replaced** → [USCG Commercial Vessel Compliance](https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/Commercial-Vessel-Compliance/), [최종 CG-CVC URL](https://www.dco.uscg.mil/CG-CVC/)로 이동해 HTTP 200 | commercial vessel policy, inspections, detentions, MARPOL, forms/resources. `vessel_certificate_profile`, `inspection_due_status`, `deficiency_detention_status`, `pollution_certificate_status`의 상위 scope. |
| 12-2 | 2026-07-30 | [46 CFR Part 2](https://www.ecfr.gov/current/title-46/chapter-I/subchapter-A/part-2) — `unblock.federalregister.gov` CAPTCHA로 이동, 본문 미확보 | **replaced** → [USCG Domestic Compliance — General](https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/Commercial-Vessel-Compliance/Domestic-Compliance-Division/General/), HTTP 200 | CG-3752 Application for Inspection 및 Continuous Synopsis Record의 owner/operator/security history 범위. `inspection_request_submit`, `vessel_certificate_profile`, `security_plan_submit`. |
| 12-3 | 2026-07-30 | [46 CFR Part 4](https://www.ecfr.gov/current/title-46/chapter-I/subchapter-A/part-4) — `unblock.federalregister.gov` CAPTCHA로 이동, 본문 미확보 | **replaced** → [USCG CG-2692 form family](https://www.dcms.uscg.mil/forms/smdsearch4081/2692/), HTTP 200 | current CG-2692 family와 marine casualty reporting asset. `casualty_case_status`, `marine_casualty_initial_report`, `marine_casualty_report_submit`. |
| 12-4 | 2026-07-30 | [46 CFR Part 15](https://www.ecfr.gov/current/title-46/chapter-I/subchapter-B/part-15) — HTTP 200, 최종 URL 동일 | **accepted** | owner/operator/master 책임, Certificate of Inspection의 minimum complement 및 credential/manning requirements. `crew_credential_manning_status`, `manning_exception_request`의 규정 scope. |
| 12-5 | 2026-07-30 | [33 CFR Part 160](https://www.ecfr.gov/current/title-33/chapter-I/subchapter-P/part-160) — HTTP 200, 최종 URL 동일 | **accepted** | ports/waterways safety와 dangerous condition 보고. `dangerous_condition_report`, 관련 `deficiency_detention_status`. |
| 12-6 | 2026-07-30 | [33 CFR Part 104](https://www.ecfr.gov/current/title-33/chapter-I/subchapter-H/part-104) — HTTP 200, 최종 URL 동일 | **accepted** | vessel security roles, assessments, plan과 drills. `security_plan_submit`, `safety_drill_record`, `safety_equipment_status`의 security/drill scope. |
| 12-7 | 2026-07-30 | [기존 USCG Inspections & Compliance URL](https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/) — 이 실행에서 internal error, 본문 미확보 | **replaced** → [USCG Commercial Vessel Compliance mission management](https://www.dco.uscg.mil/Our-Organization/Assistant-Commandant-for-Prevention-Policy-CG-5P/Inspections-Compliance-CG-5PC-/Commercial-Vessel-Compliance/CVCmms/), HTTP 200 | current mission-management forms/work instructions, inspections, equipment와 deficiencies. `inspection_due_status`, `safety_equipment_status`, `deficiency_record`, `corrective_action_submit`. |

**도메인 결과:** usable 공식 출처 **7개**. 역할은 vessel owner/operator/master, credentialed crew, company/vessel security officer와 USCG inspector로, 자산은 vessel certificate/COI, inspection, manning/credentials, safety/security equipment and plan, pollution certificate, deficiency/detention와 casualty case다.

**미해결 source gap 5개:** `certificate_endorsement_request`, `manning_exception_request`, `pollution_prevention_record`, `return_to_service_request`, `vessel_decommission_record`. 현재 출처는 관련 규제 영역을 보여 주지만 모든 commercial vessel class에 공통인 독립 신청/기록 terminal, 필수 입력과 완료 상태를 입증하지 않는다. vessel class, route, flag, inspected/uninspected status 및 MARPOL applicability별 공식 출처를 추가해야 한다.

## 9. 적용 결론

1. 도메인 7~12의 원 후보 41개는 모두 후보별로 판정했으며, 읽을 수 없거나 의미가 부족한 17개는 공식 1차 출처로 교체했다.
2. 최종 usable 공식 출처는 41개이고 정규화 URL 중복은 0개다.
3. 이 출처 집합은 role/asset/state ontology와 명시된 workflow scope를 제안하는 데 사용할 수 있지만, 미해결 terminal/source-gap 22개는 직접 실행 가능한 UI terminal로 승격하면 안 된다.
4. 오래된 FCC workflow 문서와 PHMSA 교육자료는 현재 숫자·기한·버튼명을 정하는 근거가 아니라 개념 및 workflow vocabulary 근거로만 제한한다.
5. 향후 보강 시에는 미해결 terminal마다 적용 서비스/면허/운송 mode/선박 class를 먼저 좁힌 뒤, 해당 기관의 현행 rule, form instruction 또는 system user guide로 terminal의 입력·상태·완료 의미를 각각 입증해야 한다.
