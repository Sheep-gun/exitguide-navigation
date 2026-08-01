# Navigation V16 official-source gap closure — part 2B

- 검증일: **2026-07-30**
- 대상: `NAVIGATION_SOURCES_V16_PART2.md`의 도메인 10~12에 남은 terminal/source-gap **12개**
- 허용 출처: PHMSA·FMCSA·ATF·USCG가 직접 운영하거나 발행한 공식 1차 출처만 사용
- 비대상: 구현 코드, 독립 fixture·정답·실패·평가 결과

## 1. 판정 기준

- `resolved`: 공식 출처가 terminal에 필요한 role, asset, 적용 jurisdiction, 핵심 state와 transition을 직접 뒷받침한다. 제품 UI 존재 여부는 별도로 기록하며, UI가 없다는 이유만으로 온톨로지 근거를 부정하지 않는다.
- `partially_resolved`: 공식 출처가 자산·의무·일부 상태 전이는 뒷받침하지만, terminal 이름이 암시하는 승인·기록·종결 전이를 직접 입증하지 못하거나 특정 운송 mode·선박 class·지역에만 적용된다. **현재 이름 그대로 범용 terminal로 승격하지 않는다.**
- `unresolved`: 공식 1차 출처에서 role/asset/state/transition 중 핵심 요소를 확인하지 못했다.
- 제품 UI 근거와 온톨로지 근거를 분리했다. 규정이나 업무 절차가 존재하더라도 특정 앱 버튼·API·자동 실행 기능의 존재를 추정하지 않았다.
- URL 정규화는 scheme·host 소문자화, fragment 제거, query 제거, root가 아닌 경로의 말단 `/` 제거 기준으로 수행했다.

## 2. 상태별 총계

| 도메인 | 대상 | resolved | partially_resolved | unresolved |
|---|---:|---:|---:|---:|
| `hazardous_materials_transport_compliance` | 4 | 1 | 3 | 0 |
| `firearms_dealer_compliance_ops` | 3 | 1 | 2 | 0 |
| `commercial_vessel_safety_compliance` | 5 | 3 | 2 | 0 |
| **합계** | **12** | **5** | **7** | **0** |

`partially_resolved` 7개는 source gap이 완전히 닫힌 것이 아니다. 이름을 좁히거나 terminal을 분리하고, 적용 범위별 추가 출처가 생기기 전까지 직접 실행 가능한 범용 UI terminal로 materialize하지 않는다.

## 3. 도메인 10 — `hazardous_materials_transport_compliance`

### 3.1 `route_plan_approve` — partially_resolved

- **공식 URL:** [FMCSA — What are carriers required to do to obtain and keep a Hazardous Materials Safety Permit?](https://www.fmcsa.dot.gov/regulations/hazardous-materials/what-are-carriers-required-do-obtain-and-keep-hazardous-materials)
- **접근 관찰:** 공식 FMCSA HTML 본문을 직접 열어 읽었다. 본문은 hazardous-materials safety permit 보유 carrier가 Class 7 운송에는 49 CFR 397.101의 written route plan을, explosives 운송에는 Part 397.19의 route plan을 갖춰야 한다고 명시한다.
- **온톨로지 근거:** role은 hazmat motor carrier와 vehicle operator, asset은 written route plan, 관련 상태는 `route_plan_required`·`route_plan_maintained`, jurisdiction은 미국 고속도로의 해당 Class 7 및 explosives 운송이다. 출처가 뒷받침하는 transition은 `permit_scope_identified -> route_plan_developed_and_maintained`이다.
- **제품 UI 존재:** 특정 FMCSA/PHMSA 제품에서 “Approve route plan” 버튼·API·승인 큐가 존재한다는 근거는 없다.
- **제한:** 출처는 carrier의 계획 작성·보유 의무를 입증하지만 별도의 규제기관 승인이나 내부 승인 transition을 입증하지 않는다. 범용 `route_plan_approve` 대신 적용 물질별 `route_plan_prepare` 또는 `route_plan_maintain`으로 이름을 좁힐 때만 강한 근거가 된다.

### 3.2 `carrier_acceptance_record` — partially_resolved

- **공식 URL:** [PHMSA Interpretation Response #22-0123](https://www.phmsa.dot.gov/regulations/title49/interp/22-0123)
- **접근 관찰:** 공식 PHMSA HTML 해석서 본문을 직접 열어 읽었다. 본문은 offeror가 package를 carrier가 인수할 때까지 운송 가능한 상태로 유지해야 하고, carrier는 운송 가능한 상태가 아닌 package를 accept할 수 없다고 명시한다.
- **온톨로지 근거:** role은 offeror/shipper와 carrier, asset은 completed hazmat package, 상태는 `in_shipper_possession`·`condition_for_shipment`·`accepted_by_carrier` 또는 `acceptance_blocked`, jurisdiction은 49 CFR Parts 171~180이 적용되는 미국 상업 운송이다. 확인된 transition은 `package_offered -> carrier_condition_check -> accepted_or_rejected`이다.
- **제품 UI 존재:** 별도의 carrier acceptance record 화면, 공통 전자서식 또는 PHMSA 제출 API의 존재는 확인되지 않았다.
- **제한:** accept/reject 판단은 직접 뒷받침되지만 그 판단을 독립된 `carrier_acceptance_record` 자산으로 저장해야 한다는 근거는 없다. 운송 mode별 실제 shipping paper·manifest·acceptance 서식과 분리해 모델링해야 한다.

### 3.3 `security_plan_approve` — partially_resolved

- **공식 URL:** [PHMSA Interpretation Response #10-0083](https://www.phmsa.dot.gov/regulations/title49/interp/10-0083)
- **접근 관찰:** 공식 PHMSA HTML 해석서 본문을 직접 열어 읽었다. 49 CFR 172.800(b) 적용 대상 offeror/carrier가 personnel, unauthorized access, en-route security를 포함한 security plan을 보유·구현해야 하며, 사고 중 보관·이적 상황에도 책임 당사자의 plan이 이어질 수 있음을 확인했다.
- **온톨로지 근거:** role은 covered hazmat offeror/carrier와 사고 현장의 responsible party, asset은 written transportation security plan, 상태는 `plan_required`·`implemented`·`active_during_transport_or_incident`·`responsibility_transferred`, jurisdiction은 49 CFR Part 172 Subpart I 적용 운송이다. 출처가 뒷받침하는 transition은 `covered_activity -> plan_implemented -> plan_applied_or_responsibility_transferred`이다.
- **제품 UI 존재:** regulator approval 화면이나 공통 “Approve security plan” 버튼·API의 존재는 확인되지 않았다.
- **제한:** 출처는 plan의 적용·구현을 입증하지만 승인 주체, 승인 요청, 승인 완료 상태를 입증하지 않는다. `security_plan_implement` 또는 `security_plan_review`로 좁히지 않는 한 부분 해결로 유지한다.

### 3.4 `package_nonconformance_hold` — resolved

- **공식 URL:** [PHMSA — Procedure for Removal of Nonconforming Hazardous Materials Packagings from Service](https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/docs/technical-resources/56346/remoproc.pdf)
- **접근 관찰:** PHMSA가 호스팅하는 5쪽 공식 PDF를 직접 열어 읽었다. nonconforming packaging이 식별되면 enforcement office가 자료를 수집하고 hazard/risk를 평가하며, imminent hazard이면 alleged violator에게 즉시 service에서 제거하도록 요구하고 lesser hazard에도 교정·제거·retrofit 등의 조치를 선택한다고 명시한다.
- **온톨로지 근거:** role은 PHMSA hazardous-materials enforcement/technical/legal office와 alleged violator·packaging holder, asset은 suspect/nonconforming packaging과 assessment evidence, 상태는 `suspected_nonconforming`·`risk_assessment_pending`·`imminent_or_lesser_hazard`·`removed_from_service`·`corrective_action_required`, jurisdiction은 미국 hazardous-materials packaging enforcement다. transition은 `nonconformance_identified -> risk_assessed -> use_blocked_or_corrective_action`으로 명확하다.
- **제품 UI 존재:** 특정 제품 UI나 버튼은 입증되지 않았다. 이 출처는 규제·업무 상태 전이의 근거다.
- **제한:** 문서는 오래된 집행 절차이며 현재 PHMSA 사이트에서 계속 제공되지만, operator 내부 시스템의 필드나 화면을 규정하지 않는다. `hold`는 제품 버튼이 아니라 `remove from service/use blocked` 상태로 해석해야 한다.

## 4. 도메인 11 — `firearms_dealer_compliance_ops`

### 4.1 `inventory_discrepancy_record` — partially_resolved

- **공식 URL:** [ATF — Report Firearms Theft or Loss](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/report-firearms-theft-or-loss)
- **접근 관찰:** 공식 ATF HTML 본문을 직접 열어 읽었다. FFL inventory에서 firearm이 account되지 않으면 범죄 증거가 없고 recordkeeping error일 수 있음을 관계 기관에 알리고, discovery 후 48시간 이내 전화·서면 보고와 ATF Form 3310.11 제출을 해야 한다고 명시한다.
- **온톨로지 근거:** role은 FFL, local law enforcement, ATF Stolen Firearms Program/NTC, asset은 firearm inventory item·A&D record·Form 3310.11, 상태는 `unaccounted_during_inventory`·`cause_unknown`·`theft_or_loss_report_required`·`reported`, jurisdiction은 미국 FFL의 27 CFR 478.39a 적용 inventory다. transition은 `discrepancy_detected -> reconcile_or_classify -> unresolved_missing_item_reported`다.
- **제품 UI 존재:** 전화·서면·form 제출 절차는 확인됐지만 독립된 “inventory discrepancy record” 제품 화면은 확인되지 않았다.
- **제한:** 출처는 모든 inventory discrepancy가 아니라 reconcile되지 않은 missing/lost firearm만 직접 다룬다. 일반 수량 오류, serial mismatch, 잘못된 A&D entry를 하나의 terminal로 묶을 수 없으므로 `unaccounted_firearm_report`로 좁히거나 discrepancy 유형별로 분리해야 한다.

### 4.2 `inspection_correction_status` — resolved

- **공식 URL:** [ATF — Firearms Compliance Inspections](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/compliance-inspections)
- **접근 관찰:** 공식 ATF HTML 본문을 직접 열어 읽었다. IOI가 violation/discrepancy를 FFL에게 알리고 final Report of Violations를 검토하며, FFL response와 이미 수행한 corrective action을 기록하고 signed report 사본을 제공한다고 명시한다. 이후 상태는 report, warning letter, warning conference 또는 revocation 절차 등으로 나뉜다.
- **온톨로지 근거:** role은 ATF IOI와 FFL/licensee, asset은 inventory·A&D record·ATF forms·signed Report of Violations·corrective action, 상태는 `inspection_in_progress`·`finding_disclosed`·`licensee_response_documented`·`corrective_action_taken`·`warning_or_revocation_path`, jurisdiction은 미국 FFL의 federal firearms compliance inspection이다. transition은 `finding -> response_and_correction_documented -> inspection_disposition`으로 직접 확인된다.
- **제품 UI 존재:** physical 또는 digital signed report 사본의 존재는 확인되지만, 실시간 status dashboard·버튼·API는 확인되지 않았다.
- **제한:** terminal은 case-management 상태 조회로 구현할 수 있으나, 출처가 보장하는 것은 검사 보고서와 처분 lifecycle이지 특정 전자 시스템의 상태 코드가 아니다.

### 4.3 `license_surrender_closeout` — partially_resolved

- **공식 URL:** [ATF — Discontinue Being a Federal Firearms Licensee (FFL)](https://www.atf.gov/firearms/tools-and-services-firearms-industry/current-licensees/firearms/discontinue-being-a-federal-firearms-licensee-ffl)
- **접근 관찰:** 공식 ATF HTML 본문을 직접 열어 읽었다. FFL이 business를 discontinue하면 firearms transaction records를 NTC로 보내거나 local ATF office에 전달해야 하며, 대상에는 A&D books, computer printouts, Forms 4473, theft/loss reports, multiple-sale reports와 Brady forms가 포함된다.
- **온톨로지 근거:** role은 discontinuing FFL과 NTC/local ATF office, asset은 FFL business record set, 상태는 `business_discontinued`·`records_pending_transfer`·`records_delivered`, jurisdiction은 미국 federal firearms licensee의 out-of-business records 처리다. 확인된 transition은 `business_discontinued -> records_surrendered_to_NTC_or_ATF`다.
- **제품 UI 존재:** 우편 또는 office delivery 절차는 확인되지만 이 페이지는 license surrender 자체를 실행하는 온라인 UI나 하나의 closeout transaction을 제시하지 않는다.
- **제한:** terminal 이름은 `license surrender`와 `out-of-business records closeout`을 결합한다. 출처는 후자만 직접 뒷받침하므로 `license_termination`과 `out_of_business_records_transfer`를 분리하기 전에는 부분 해결이다.

## 5. 도메인 12 — `commercial_vessel_safety_compliance`

### 5.1 `certificate_endorsement_request` — resolved

- **공식 URL:** [USCG Form CG-1258 — Application for Certificate of Documentation / Redocumentation](https://www.dco.uscg.mil/Portals/9/DCO%20Documents/NVDC/Forms/CG-1258_11_30_2026.pdf)
- **접근 관찰:** USCG가 호스팅하는 4쪽 fillable PDF를 query 없는 URL로 직접 열어 읽었다. Form CG-1258은 purpose of application, sought endorsement, primary service, managing owner, ownership/citizenship 자료를 수집하며, filing만으로 requested documentation/changes가 승인되는 것은 아니라고 명시한다. 표시된 만료일은 2026-11-30이다.
- **온톨로지 근거:** role은 vessel managing owner/owner와 NVDC reviewer, asset은 Certificate of Documentation와 recreational/coastwise/fishery/registry endorsement application, 상태는 `draft`·`filed`·`eligibility_review`·`issued_or_denied`, jurisdiction은 46 CFR Part 67에 따른 미국 vessel documentation과 eligible trade endorsement다. transition은 `current_or_undocumented_vessel -> endorsement_application_filed -> eligibility_decision`이다.
- **제품 UI 존재:** 공식 fillable form artifact는 존재한다. 다만 이것이 모바일 앱 버튼이나 자동 승인 API를 뜻하지 않으며, 현재 제출 채널은 별도 NVDC 안내를 따라야 한다.
- **제한:** 이 근거는 Certificate of Documentation의 trade endorsement다. Certificate of Inspection endorsement나 merchant mariner credential endorsement와 혼합하면 안 된다.

### 5.2 `manning_exception_request` — partially_resolved

- **공식 URL:** [USCG Sector Honolulu Work Instruction 31(2) — Reduced Manning Criteria for Dive and Snorkel Operations](https://www.pacificarea.uscg.mil/Portals/8/District%2014/SectHono/docs/WI%2031%282%29%20-%20Reduced%20Manning%20Criteria%20for%20Dive%20and%20Snorkel.pdf)
- **접근 관찰:** USCG가 호스팅하는 6쪽 공식 PDF를 직접 열어 읽었다. Sector Honolulu inspection zone의 certificated small passenger vessel이 dive/snorkel 활동 중 reduced-manning COI endorsement를 새로 요청하거나 유지하려면 attending Marine Inspector에게 equivalent level of safety를 입증해야 하고, OCMI가 재량으로 승인·제거할 수 있음을 확인했다.
- **온톨로지 근거:** role은 small-passenger-vessel operator, attending Marine Inspector와 OCMI, asset은 COI reduced-manning endorsement와 safety evidence, 상태는 `full_manning_required`·`request_pending`·`equivalent_safety_review`·`endorsement_active_or_removed`, jurisdiction은 **Sector Honolulu의 inspected small passenger dive/snorkel vessels**다. transition은 `new_request -> safety_review -> OCMI_endorsement_decision`이다.
- **제품 UI 존재:** request 접수 버튼·공통 온라인 서식·API는 출처에서 확인되지 않았다.
- **제한:** 정확한 exception lifecycle은 확인됐지만 전국의 모든 commercial vessel class에 일반화할 수 없다. 범용 terminal로 쓰려면 vessel class·operation·OCMI zone을 guard로 강제하고, 다른 class에는 별도 national/sector authority가 필요하다.

### 5.3 `pollution_prevention_record` — resolved

- **공식 URL:** [USCG — Accepted Electronic Record Books](https://www.dco.uscg.mil/Accepted-Electronic-Record-Books/)
- **접근 관찰:** 공식 USCG HTML 본문을 직접 열어 읽었다. U.S.-flag vessel이 MARPOL electronic record book을 사용하려면 Coast Guard가 인정한 Declaration이 필요하고, 현재 인정 목록에는 Oil Record Book Parts I/II, Cargo Record Book, Garbage Record Book, ozone-depleting-substances record, fuel-oil-changeover 및 engine-parameter record 등이 명시돼 있다.
- **온톨로지 근거:** role은 U.S.-flag vessel owner/operator, authorized classification society와 USCG assessor, asset은 MARPOL pollution-prevention electronic record book과 Declaration, 상태는 `record_book_required`·`product_assessed`·`declaration_obtained`·`record_book_in_use`, jurisdiction은 해당 MARPOL regulation이 적용되는 U.S.-flag vessels다. transition은 `record_requirement_identified -> accepted_product_selected -> declaration_issued -> operational_entries_maintained`다.
- **제품 UI 존재:** 실제 전자 record-book 제품군의 존재가 공식 목록으로 확인된다. 다만 USCG가 특정 제품의 화면·버튼 구조를 보증하거나 운영하는 것은 아니다.
- **제한:** `pollution_prevention_record`는 상위 범주다. 실제 terminal은 `oil_record_book_entry`, `garbage_record_book_entry`, `cargo_record_book_entry`처럼 MARPOL annex와 record type별로 나눠야 하며 applicability guard가 필수다.

### 5.4 `return_to_service_request` — resolved

- **공식 URL:** [USCG CVC-WI-018(2) — Laid Up and Inactive Commercial Vessel Guidance](https://www.dco.uscg.mil/Portals/9/DCO%20Documents/5p/CG-5PC/CG-CVC/CVC_MMS/CVC-WI-018%282%29.pdf)
- **접근 관찰:** USCG가 호스팅하는 11쪽 공식 PDF를 직접 열어 읽었다. surrendered COI를 가진 laid-up U.S. vessel의 owner/managing operator가 service 복귀를 원하면 Form CG-3752를 local OCMI에 제출하고 Marine Inspector attendance를 예약해야 하며, expired inspection을 끝내고 새 COI를 받아야 한다. foreign-flag vessel도 local OCMI 통지와 필요한 PSC/COC exam을 마쳐야 복귀할 수 있다.
- **온톨로지 근거:** role은 vessel owner/managing operator, local OCMI, Marine Inspector 및 해당 시 Flag Administration/RO, asset은 laid-up status letter·surrendered COI/COC·CG-3752·inspection/exam evidence, 상태는 `laid_up`·`reactivation_requested`·`inspection_pending`·`recertified`·`returned_to_service`, jurisdiction은 USCG 관할의 laid-up U.S. inspected vessels와 미국 수역의 적용 foreign vessels다. transition은 `laid_up -> application_and_examination -> new_COI_or_COC -> return_to_service`로 직접 확인된다.
- **제품 UI 존재:** CG-3752와 OCMI scheduling 절차는 확인되지만 단일 온라인 return-to-service 버튼·API는 확인되지 않았다.
- **제한:** 일반적인 temporary outage나 단순 deficiency 해소 후 재운항이 아니라 **laid-up/COI surrendered** 맥락의 복귀 terminal이다. 이 guard를 생략하면 과도한 일반화가 된다.

### 5.5 `vessel_decommission_record` — partially_resolved

- **공식 URL:** [USCG National Vessel Documentation Center — Expanded Online Ordering](https://www.dco.uscg.mil/Our-Organization/Deputy-for-Operations-Policy-and-Capabilities-DCO-D/National-Vessel-Documentation-Center/NationalVesselDocumentationCenter-OtherLinks/)
- **접근 관찰:** 공식 USCG HTML 본문을 직접 열어 읽었다. NVDC eStorefront의 현재 서비스 목록에 `Request a Deletion Letter`가 있고, Certificate of Documentation의 initial/replacement/reinstatement/exchange/return 및 commercial/registry endorsement renewal도 전자 신청 대상으로 열거돼 있다.
- **온톨로지 근거:** role은 documented vessel owner/authorized customer와 NVDC, asset은 Certificate of Documentation와 deletion-letter request, 상태는 `actively_documented`·`deletion_requested`·`deletion_letter_available`, jurisdiction은 미국 NVDC vessel-documentation registry다. 확인된 transition은 `documented_vessel -> deletion_request -> documentation_removed_or_evidenced`다.
- **제품 UI 존재:** 공식 eStorefront에서 deletion-letter request 제품이 존재한다고 확인된다. 공개 페이지는 실제 인증 후 입력 필드·완료 상태까지 보여 주지는 않는다.
- **제한:** documentation deletion은 physical decommissioning, lay-up, scrapping, flag deletion 또는 COI surrender와 동일하지 않다. 따라서 `vessel_decommission_record`를 그대로 resolved 처리할 수 없으며 `vessel_documentation_deletion_request`로 좁히거나 decommission 의미별 terminal을 분리해야 한다.

## 6. URL 정규화·중복 감사

- terminal별 대표 URL: **12개**
- 정규화 후 고유 URL: **12개**
- 정규화 중복: **0개**
- query가 붙어 있던 CG-1258 검색 결과는 query 없는 공식 PDF URL로 다시 열어 확인한 뒤 기록했다.
- 과거 검색 색인에는 남아 있으나 직접 열기에서 404였던 NVDC `DELETION FROM DOCUMENTATION 03-2025/09-2025` PDF URL은 usable URL에서 제외했다.

## 7. 적용 결론

1. 즉시 온톨로지 materialization 후보는 `package_nonconformance_hold`, `inspection_correction_status`, `certificate_endorsement_request`, `pollution_prevention_record`, `return_to_service_request` 5개다. 각 terminal에도 위 제한·jurisdiction guard를 그대로 보존해야 한다.
2. `route_plan_approve`, `carrier_acceptance_record`, `security_plan_approve`, `inventory_discrepancy_record`, `license_surrender_closeout`, `manning_exception_request`, `vessel_decommission_record` 7개는 일부 근거만 확보됐다. 이름을 좁히거나 복합 terminal을 분리하기 전에는 실행 terminal로 승격하지 않는다.
3. 공식 출처가 UI를 직접 입증한 것은 CG-1258 fillable form, MARPOL electronic record-book 제품군, NVDC eStorefront의 deletion-letter product 정도다. 나머지는 업무·규제 lifecycle 근거이며 앱 버튼·API 존재를 추정하지 않는다.
4. 모든 final action은 사용자 소유로 유지한다. 출처가 제출·승인·서비스 복귀 절차를 설명하더라도 자동 제출·자동 승인·자동 최종 클릭 권한을 부여하지 않는다.
