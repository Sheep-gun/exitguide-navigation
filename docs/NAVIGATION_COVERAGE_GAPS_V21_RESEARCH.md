# Navigation coverage gap research — V21

Status: **research-only and noncanonical**. This file is a source-backed
ontology and collision proposal. It adds no runtime domain, function, intent,
alias, goal, fixture, score, selector, coordinate, screenshot, or recorded
path. Nothing in this document is importable by catalog generation. Promotion
requires a separate reviewed data change, an independently authored sealed
fixture, a full regression run, and an explicit catalog-version decision.

Research access date: **2026-07-30**.

## Baseline and prospective count math

The comparison baseline for this research is the complete prospective V20
payload: **232 domains / 3,869 physical functions / 3,610 physical terminal
functions and intents**. This is a projection, not a claim that V20 is already
canonical or deployed.

| Layer | Delta domains | Delta functions | Delta intents | Prospective totals |
| --- | ---: | ---: | ---: | --- |
| Prospective V20 | — | — | — | 232 / 3,869 / 3,610 |
| Accepted V21 research set | +6 | +106 | +100 | **238 / 3,975 / 3,710** |

The V21 delta is mechanical: **100 terminal seams + six explicit fail-closed
hubs = 106 functions**, with one intent per terminal seam. Per-domain terminal
counts are 16, 18, 16, 18, 16, and 16. Terminal equivalence review may reduce
the delta before implementation; a reduced domain must be rejected if fewer
than 14 genuinely distinct terminals remain.

## Research and collision method

The duplicate audit used only the canonical V15 physical catalog and the
prospective V17–V20 source/data layers and research documents. The V16 sealed
evaluator, sealed goals, failure reports, and all `TEMP` artifacts were not
opened. V16-derived identifiers were checked only where they are already
materialized in the V15 catalog or named by later public research layers.

A seam was retained only if **role + governed asset + lifecycle state +
provider + jurisdiction** jointly distinguish it from every nearest existing
terminal. A different agency name, provider app, page title, or deeper menu is
not enough. Generic words such as `application`, `status`, `notice`, `claim`,
`payment`, `appeal`, `document`, `eligibility`, and `appointment` never select a
V21 terminal by themselves.

No private telemetry was used. “High-frequency” means that an official source
publishes recurring self-service lifecycle states and an official program
dataset, report, or portal demonstrates material public use. It is an
evidence-derived prioritization signal, not a traffic ranking.

## Shared fail-closed and final-action contract

Every accepted domain has a `.hub` that is selected whenever any boundary is
missing or contradictory. Read-only seams marked `S` may stop after the exact
destination and governed record are visibly confirmed. Consequential seams
marked `C` require:

- `automation_policy=never_auto`;
- `stop_policy=before_action`; and
- `user_owned_final_press=true`.

The agent may navigate, explain visible requirements, and expose an official
handoff. It must never decide eligibility, invent household/medical/legal/
financial facts, impersonate a representative, sign or attest, upload evidence,
choose a provider or plan for the user, submit a request, schedule or cancel an
appointment, pay, appeal, or press the final consequential control.

## Initial candidate audit and disposition

The requested starting families were audited before looking for replacements.

| Candidate | Disposition | Exact owner or boundary |
| --- | --- | --- |
| Passport application, renewal, status, and records | Reject | `government_digital.passport_apply`, `government_digital.passport_renew`, `government_digital.passport_status`, and `government_digital.passport_records` already own the complete family. |
| Veterans benefits | Reject | V17 already owns the claimant lifecycle in `veterans_benefit_claim_services`, including claim, evidence, examination, decision, payment, review, and appeal. |
| Social Security and disability | Reject | V17 already owns `social_security_benefit_services.disability_application_start`, `social_security_benefit_services.application_status`, `social_security_benefit_services.continuing_disability_review`, and related payment/appeal states. |
| Federal student aid and student loans | Reject | V17 already owns FAFSA, aid history, counseling, promissory note, repayment, IDR, consolidation, and PSLF in `student_financial_aid_services`. |
| Disaster assistance | Reject | V17 already owns application, identity/residency evidence, inspection, award, and appeal in `disaster_assistance_case_services`. |
| Public housing and vouchers | Reject | V17 already owns waitlist, voucher, tenancy approval, inspection, recertification, accommodation, portability, and hearing in `public_housing_assistance_services`. |
| Unemployment insurance | Reject | V17 already owns initial claim, fact finding, evidence, weekly certification, determination, payment, overpayment, and appeal in `unemployment_insurance_case_services`. |
| Broad immigration or consular services | Reject broad family; retain narrow post-filing USCIS candidate | Domestic generic routing already belongs to `government_digital.immigration_case`, `government_digital.processing_times`, `government_digital.address_change`, `government_digital.case_inquiry`, `government_digital.office_appointment`, `government_digital.form_filing`, and `government_digital.fee_calculator`; consular visa work belongs to V19 `consular_visa_application_services`. Only receipt/notice-driven USCIS post-filing actions survive below. |

## Accepted evidence-ready domains

### 1. USCIS post-filing case services (`uscis_post_filing_case_services`)

This domain begins only after USCIS has accepted a filing and issued a receipt
or case-linked notice. It does not own choosing a form, filing an initial form,
calculating fees, general case status, changing an address, checking processing
times, booking an ordinary office appointment, a Department of State consular
case, EOIR proceedings, or passport work.

| Boundary | Required discriminator |
| --- | --- |
| Role | applicant, petitioner, beneficiary with permitted access, or formally authorized representative |
| Asset | USCIS receipt number, named post-filing notice, evidence response, appointment notice, decision notice, or secure document delivery case |
| State | receipt issued; notice issued; response requested; appointment scheduled; decision issued; document mailed/not received |
| Provider | USCIS online account, USCIS Contact Center, ASC, field office, or named USCIS service center |
| Jurisdiction | U.S. domestic USCIS case; never DOS consular, EOIR court, passport, or Korean immigration by label similarity |

**Fail-closed hub.** `uscis_post_filing_case_services.hub` requires the role,
receipt/notice asset, post-filing state, USCIS provider, and U.S. jurisdiction.
Missing receipt or notice context routes to the existing generic owner or asks a
clarifying question.

| # | Prospective terminal ID | S/C | Korean / English destination |
| ---: | --- | :---: | --- |
| 1 | `uscis_post_filing_case_services.receipt_notice_review` | S | 접수 통지서 검토 / Receipt notice review |
| 2 | `uscis_post_filing_case_services.online_account_case_link` | C | 온라인 계정에 사건 연결 / Link a case to an online account |
| 3 | `uscis_post_filing_case_services.biometrics_notice_review` | S | 생체정보 채취 통지 검토 / Biometrics notice review |
| 4 | `uscis_post_filing_case_services.biometrics_reschedule_request` | C | 생체정보 일정 변경 요청 / Biometrics reschedule request |
| 5 | `uscis_post_filing_case_services.evidence_request_review` | S | 추가증거 요청 검토 / Evidence-request review |
| 6 | `uscis_post_filing_case_services.evidence_response_submit` | C | 추가증거 응답 제출 / Evidence-response submission |
| 7 | `uscis_post_filing_case_services.interview_notice_review` | S | 면접 통지 검토 / Interview notice review |
| 8 | `uscis_post_filing_case_services.interview_reschedule_request` | C | 면접 일정 변경 요청 / Interview reschedule request |
| 9 | `uscis_post_filing_case_services.appointment_accommodation_request` | C | 예약 편의지원 요청 / Appointment accommodation request |
| 10 | `uscis_post_filing_case_services.case_transfer_notice_review` | S | 사건 이관 통지 검토 / Case-transfer notice review |
| 11 | `uscis_post_filing_case_services.expedite_request_submit` | C | 신속처리 요청 제출 / Expedite-request submission |
| 12 | `uscis_post_filing_case_services.premium_processing_request` | C | 프리미엄 처리 요청 / Premium-processing request |
| 13 | `uscis_post_filing_case_services.representative_appearance_status` | S | 대리인 등록 상태 / Representative appearance status |
| 14 | `uscis_post_filing_case_services.medical_exam_document_status` | S | 이민 신체검사 서류 상태 / Immigration medical-exam document status |
| 15 | `uscis_post_filing_case_services.decision_notice_review` | S | 결정 통지서 검토 / Decision notice review |
| 16 | `uscis_post_filing_case_services.secure_document_non_delivery_inquiry` | C | 보안문서 미수령 문의 / Secure-document non-delivery inquiry |

S/C balance: **8 S / 8 C**. Every C seam stops before link, reschedule,
response, request, upload, or inquiry submission. A motion, appeal, withdrawal,
or legal-strategy choice remains out of scope until separately evidenced.

**Nearest collisions and mandatory handoffs.** General case/status language
stays with `government_digital.immigration_case`; outside-normal-time questions
stay with `government_digital.case_inquiry` and
`government_digital.processing_times`; address changes stay with
`government_digital.address_change`; initial forms and fees stay with
`government_digital.form_filing` and `government_digital.fee_calculator`;
generic appointments stay with `government_digital.office_appointment`.
Consular status/interview/passport return stays with
`consular_visa_application_services.application_status`,
`consular_visa_application_services.interview_schedule`, and
`consular_visa_application_services.passport_return_status`.

Official lifecycle evidence retrieved 2026-07-30:

- USCIS Contact Center, indexed official lifecycle page: <https://www.uscis.gov/contactcenter>
- USCIS e-Request non-delivery page, indexed official service page: <https://egov.uscis.gov/e-request/ndn>
- USCIS online-account legal terms, official JavaScript shell and indexed terms covering document and notice exchange: <https://myaccount.uscis.gov/legal-terms>
- USCIS ASC appointment-rescheduling policy update, official PDF rendered: <https://www.uscis.gov/sites/default/files/document/policy-manual-updates/20230706-ASCAppointments.pdf>
- USCIS expedite policy update, official PDF rendered: <https://www.uscis.gov/sites/default/files/document/policy-manual-updates/20240321-ExpediteRequests.pdf>
- USCIS immigration and citizenship data library, official page rendered: <https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data?items_per_page=100&page=0>
- Korean Immigration Service, official portal rendered; separate Korean jurisdiction: <https://www.moj.go.kr/immigration/index.do>
- Korean Immigration Contact Center and result/jurisdiction information, official page rendered: <https://moj.go.kr/immigration/1530/subview.do>
- HiKorea visit/electronic-service description, official page rendered: <https://www.moj.go.kr/immigration/1515/subview.do>

**Evidence-derived frequency and bilingual rule.** USCIS publishes all-form
receipts, approvals, denials, pending cases, and RFE datasets, so post-filing
notice handling is recurrent at program scale. Korean goals must describe the
U.S. USCIS object with Korean language when targeting this domain. Korean
immigration-service menus are a separate provider/jurisdiction branch and are
evidence for bilingual vocabulary, never aliases to a USCIS receipt.

### 2. Medicare beneficiary case services (`medicare_beneficiary_case_services`)

This is a beneficiary-facing Medicare lifecycle after or around entitlement:
coverage, card, Original Medicare claims, plan enrollment/change, drug coverage
decisions, appeals/grievances, premiums, IRMAA, and coordination of benefits.
Provider enrollment is expressly excluded.

| Boundary | Required discriminator |
| --- | --- |
| Role | Medicare beneficiary, authorized representative, or authorized payer for the beneficiary premium |
| Asset | Medicare entitlement/coverage, card, MSN, Original Medicare claim, MA/Part D plan election, premium/IRMAA notice, or coordination record |
| State | eligible/enrolled/effective; claim processed; plan election open; determination/appeal pending; premium due/paid; coordination incomplete |
| Provider | Medicare.gov/CMS, Social Security for initial Part A/B or IRMAA branch, or a named MA/Part D plan |
| Jurisdiction | U.S. Medicare; Medicaid/public-health coverage and Korean NHIS remain separate |

**Fail-closed hub.** `medicare_beneficiary_case_services.hub` requires a
beneficiary role, a Medicare-specific asset, the current lifecycle state, the
responsible provider, and U.S. jurisdiction. “Apply for Medicare” hands off to
`social_security_benefit_services.medicare_application_start` rather than
creating a duplicate initial-application terminal.

| # | Prospective terminal ID | S/C | Korean / English destination |
| ---: | --- | :---: | --- |
| 1 | `medicare_beneficiary_case_services.entitlement_enrollment_period_review` | S | 자격·가입기간 검토 / Entitlement and enrollment-period review |
| 2 | `medicare_beneficiary_case_services.coverage_effective_status` | S | 보장 효력 상태 / Coverage effective status |
| 3 | `medicare_beneficiary_case_services.medicare_card_replace` | C | 메디케어 카드 재발급 / Medicare card replacement |
| 4 | `medicare_beneficiary_case_services.original_medicare_claim_status` | S | 오리지널 메디케어 청구 상태 / Original Medicare claim status |
| 5 | `medicare_beneficiary_case_services.medicare_summary_notice_review` | S | 메디케어 요약 통지 검토 / Medicare Summary Notice review |
| 6 | `medicare_beneficiary_case_services.plan_compare` | S | 메디케어 플랜 비교 / Medicare plan comparison |
| 7 | `medicare_beneficiary_case_services.medicare_advantage_plan_enroll` | C | 메디케어 어드밴티지 가입 / Medicare Advantage enrollment |
| 8 | `medicare_beneficiary_case_services.part_d_plan_enroll` | C | Part D 플랜 가입 / Part D plan enrollment |
| 9 | `medicare_beneficiary_case_services.plan_switch_or_drop` | C | 플랜 변경 또는 탈퇴 / Plan switch or drop |
| 10 | `medicare_beneficiary_case_services.drug_coverage_determination_request` | C | 약제 보장결정 요청 / Drug coverage-determination request |
| 11 | `medicare_beneficiary_case_services.original_medicare_appeal_submit` | C | 오리지널 메디케어 이의제기 / Original Medicare appeal |
| 12 | `medicare_beneficiary_case_services.plan_appeal_submit` | C | 플랜 이의제기 / Plan appeal |
| 13 | `medicare_beneficiary_case_services.plan_grievance_submit` | C | 플랜 고충 제출 / Plan grievance |
| 14 | `medicare_beneficiary_case_services.premium_bill_review` | S | 보험료 고지 검토 / Premium bill review |
| 15 | `medicare_beneficiary_case_services.easy_pay_manage` | C | Medicare Easy Pay 관리 / Medicare Easy Pay management |
| 16 | `medicare_beneficiary_case_services.irmaa_notice_review` | S | IRMAA 통지 검토 / IRMAA notice review |
| 17 | `medicare_beneficiary_case_services.irmaa_reconsideration_request` | C | IRMAA 재심 요청 / IRMAA reconsideration request |
| 18 | `medicare_beneficiary_case_services.coordination_of_benefits_update` | C | 급여 조정 정보 변경 / Coordination-of-benefits update |

S/C balance: **7 S / 11 C**. Plan selection is navigation and comparison only;
the agent cannot recommend a plan or make an election.

**Nearest collisions and mandatory handoffs.** Initial Part A/B application
belongs to `social_security_benefit_services.medicare_application_start`.
Medicaid/public coverage belongs to
`public_health_coverage_case_services.program_eligibility_screen`,
`public_health_coverage_case_services.managed_plan_select`,
`public_health_coverage_case_services.coverage_effective_status`,
`public_health_coverage_case_services.member_card_status`, and
`public_health_coverage_case_services.fair_hearing_request`. Generic coverage
views stay with `health_insurance.eligibility` and
`health_insurance.screening`; policyholder claim upload/status stays with
`insurance.claim.documents` and `insurance.claim.status`; generic recurring
payments stay with `billing.autopay`.

Official lifecycle evidence retrieved 2026-07-30:

- CMS Original Medicare enrollment, official page rendered: <https://www.cms.gov/medicare/enrollment-renewal/original-part-a-b>
- CMS managed-care eligibility/enrollment, official page rendered: <https://www.cms.gov/medicare/enrollment-renewal/managed-care-eligibility-enrollment>
- Medicare joining/switching/dropping a plan, official page rendered: <https://www.medicare.gov/basics/get-started-with-medicare/get-more-coverage/joining-a-plan>
- Medicare claim-status and MSN route, official page rendered: <https://www.medicare.gov/providers-services/claims-appeals-complaints/claims/check-status>
- Medicare appeal lifecycle, official page rendered: <https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals>
- Medicare drug-plan coverage decisions and appeals, official page rendered: <https://www.medicare.gov/providers-services/claims-appeals-complaints/appeals/drug-plans>
- Medicare beneficiary rights, appeal, grievance, and coverage-determination page rendered: <https://www.medicare.gov/basics/your-medicare-rights/your-rights>
- Medicare card replacement, official page rendered: <https://www.medicare.gov/basics/get-started-with-medicare/using-medicare/your-medicare-card>
- Medicare Easy Pay, official page rendered: <https://www.medicare.gov/basics/costs/pay-premiums/medicare-easy-pay>
- SSA IRMAA lower/reconsideration route, official page rendered: <https://www.ssa.gov/medicare/lower-irmaa>
- Medicare coordination of benefits, official page rendered: <https://www.medicare.gov/health-drug-plans/coordination>
- CMS beneficiary-enrollment summary statistics, updated June 2026 and rendered: <https://data.cms.gov/summary-statistics-on-beneficiary-enrollment/>
- Korean NHIS out-of-pocket-cap refund application, official page rendered; separate jurisdiction: <https://www.nhis.or.kr/static/html/wbma/c/wbmac0209.html>
- Korean NHIS appeal statistics, official page rendered: <https://www.nhis.or.kr/announce/wbhaec11411m01.do>

**Evidence-derived frequency and bilingual rule.** CMS publishes current
beneficiary-enrollment statistics, and its consumer portal exposes recurring
claim, plan, appeal, card, and premium lifecycles. Korean NHIS terms inform
Korean phrasing only after provider/jurisdiction classification; they must not
be translated into a U.S. Medicare plan election.

### 3. Lifeline communications benefit services (`lifeline_communications_benefit_services`)

This domain owns the U.S. federal Lifeline consumer journey across the National
Verifier and a participating phone/internet company. It does not own a normal
mobile plan, carrier bill/autopay, generic government-benefit discovery, or a
general utility-payment-assistance application.

| Boundary | Required discriminator |
| --- | --- |
| Role | applicant/subscriber, household representative, survivor applicant, or authorized consumer helper |
| Asset | Lifeline National Verifier application, household worksheet, eligibility evidence, subscriber benefit, transfer, recertification, or de-enrollment notice |
| State | qualification unknown; application pending; qualified; provider enrollment pending; active; recertification due; de-enrolled; reapplying |
| Provider | USAC/National Verifier for qualification and recertification; named participating carrier for service enrollment/transfer activation |
| Jurisdiction | U.S. Lifeline; Korean telecom-fee reduction is a separate program/jurisdiction |

**Fail-closed hub.** `lifeline_communications_benefit_services.hub` requires a
Lifeline cue, applicant/subscriber role, program asset/state, responsible
provider lane, and U.S. jurisdiction. Qualification and carrier activation may
not be collapsed into one provider step.

| # | Prospective terminal ID | S/C | Korean / English destination |
| ---: | --- | :---: | --- |
| 1 | `lifeline_communications_benefit_services.program_eligibility_review` | S | Lifeline 자격 검토 / Lifeline eligibility review |
| 2 | `lifeline_communications_benefit_services.national_verifier_application_start` | C | National Verifier 신청 시작 / National Verifier application start |
| 3 | `lifeline_communications_benefit_services.application_status` | S | Lifeline 신청 상태 / Lifeline application status |
| 4 | `lifeline_communications_benefit_services.supporting_document_requirements` | S | 증빙서류 요건 / Supporting-document requirements |
| 5 | `lifeline_communications_benefit_services.supporting_document_submit` | C | 증빙서류 제출 / Supporting-document submission |
| 6 | `lifeline_communications_benefit_services.household_worksheet_review` | S | 가구 확인서 검토 / Household worksheet review |
| 7 | `lifeline_communications_benefit_services.household_worksheet_submit` | C | 가구 확인서 제출 / Household worksheet submission |
| 8 | `lifeline_communications_benefit_services.participating_company_lookup` | S | 참여 통신사 찾기 / Participating-company lookup |
| 9 | `lifeline_communications_benefit_services.participating_company_enrollment` | C | 참여 통신사 서비스 등록 / Participating-company enrollment |
| 10 | `lifeline_communications_benefit_services.benefit_transfer_request` | C | Lifeline 혜택 이전 / Lifeline benefit transfer request |
| 11 | `lifeline_communications_benefit_services.recertification_due` | S | 재인증 기한 확인 / Recertification due review |
| 12 | `lifeline_communications_benefit_services.recertification_submit` | C | Lifeline 재인증 제출 / Lifeline recertification submission |
| 13 | `lifeline_communications_benefit_services.subscriber_information_change` | C | 가입자 정보 변경 / Subscriber-information change |
| 14 | `lifeline_communications_benefit_services.continued_eligibility_response` | C | 계속 자격 확인 응답 / Continued-eligibility response |
| 15 | `lifeline_communications_benefit_services.de_enrollment_notice_review` | S | 혜택 종료 통지 검토 / De-enrollment notice review |
| 16 | `lifeline_communications_benefit_services.benefit_reapply` | C | Lifeline 재신청 / Lifeline reapplication |

S/C balance: **7 S / 9 C**. The agent cannot infer household composition,
income, program participation, survivor status, or continued eligibility.

**Nearest collisions and mandatory handoffs.** Ordinary carrier service and
billing remain `telecom.data_plan`, `telecom.bill`, and `telecom.autopay`.
General bill relief remains `utilities.payment_assistance`; generic benefit
discovery remains `government.benefits`. A carrier plan change without a
Lifeline transfer/activation asset must never enter this domain.

Official lifecycle evidence retrieved 2026-07-30:

- Lifeline qualification, 2026 criteria and evidence, official support page rendered: <https://www.lifelinesupport.org/how-to-qualify/>
- Lifeline application sequence, official support page rendered: <https://www.lifelinesupport.org/how-to-apply/>
- Lifeline recertification, official support page rendered: <https://www.lifelinesupport.org/recertify/>
- Lifeline de-enrollment/reapplication, official support page rendered: <https://www.lifelinesupport.org/my-service-was-turned-off/>
- USAC National Verifier, official page rendered: <https://www.usac.org/lifeline/national-verifier/>
- USAC National Verifier recertification, official page rendered: <https://www.usac.org/lifeline/national-verifier/recertification/>
- USAC program participation/subscriber data, official page rendered: <https://www.usac.org/lifeline/resources/program-data/>
- USAC current program announcements, official page rendered: <https://www.usac.org/lifeline/resources/announcements/>
- Official online-application instructions, PDF rendered: <https://www.lifelinesupport.org/wp-content/uploads/Lifeline-Online-Application-Instructions_English.pdf>
- Korean Bokjiro mobile-communications fee reduction, official page rendered; separate jurisdiction: <https://www.bokjiro.go.kr/ssis-tbu/twataa/wlfareInfo/moveTWAT52011M.do?wlfareInfoId=WLF00003257>
- Korean Bokjiro application-channel notice, official page rendered: <https://www.bokjiro.go.kr/ssis-tbu/cms/pc/news/promotion/1305828_1118.html>

**Evidence-derived frequency and bilingual rule.** USAC publishes subscriber
and quarterly program data and recurring recertification system notices. Korean
goals require separate program names and channels; “통신비 감면” alone must
clarify U.S. Lifeline versus the Korean benefit.

### 4. ADA paratransit rider services (`ada_paratransit_rider_services`)

This is the rider-facing complementary paratransit lifecycle: functional
eligibility, assessment, determination/appeal, rider/visitor status, booking,
arrival, no-show suspension, and service complaint. It is not fixed-route
planning, ordinary accessible ride-hailing, medical transport authorization, or
transit-agency operator administration.

| Boundary | Required discriminator |
| --- | --- |
| Role | applicant/rider, authorized representative, personal care attendant for the rider, or eligible visitor |
| Asset | paratransit eligibility case, functional assessment, eligibility determination, rider ID, visitor request, reserved trip, suspension notice, or complaint |
| State | applying; assessment due; presumptively/conditionally/unconditionally eligible; denied/appealed; certified; trip booked; suspended |
| Provider | named public transit agency or its contracted paratransit operator |
| Jurisdiction | agency service area and applicable ADA program; Korean mobility-call services are separate local programs |

**Fail-closed hub.** `ada_paratransit_rider_services.hub` requires a rider role,
a paratransit eligibility/trip asset, its state, named agency/provider, and
service-area jurisdiction. Disability diagnosis alone is insufficient, and the
agent cannot decide functional eligibility.

| # | Prospective terminal ID | S/C | Korean / English destination |
| ---: | --- | :---: | --- |
| 1 | `ada_paratransit_rider_services.service_area_lookup` | S | 서비스 지역 확인 / Service-area lookup |
| 2 | `ada_paratransit_rider_services.eligibility_requirements_review` | S | 이용자격 요건 검토 / Eligibility-requirements review |
| 3 | `ada_paratransit_rider_services.eligibility_application_start` | C | 이용자격 신청 시작 / Eligibility application start |
| 4 | `ada_paratransit_rider_services.functional_assessment_schedule` | C | 기능평가 일정 예약 / Functional-assessment scheduling |
| 5 | `ada_paratransit_rider_services.application_status` | S | 자격 신청 상태 / Eligibility application status |
| 6 | `ada_paratransit_rider_services.presumptive_eligibility_status` | S | 잠정 이용자격 상태 / Presumptive-eligibility status |
| 7 | `ada_paratransit_rider_services.eligibility_determination_review` | S | 이용자격 결정 검토 / Eligibility-determination review |
| 8 | `ada_paratransit_rider_services.conditional_eligibility_review` | S | 조건부 이용자격 검토 / Conditional-eligibility review |
| 9 | `ada_paratransit_rider_services.eligibility_appeal_submit` | C | 이용자격 이의제기 / Eligibility appeal submission |
| 10 | `ada_paratransit_rider_services.recertification_due` | S | 재인증 기한 확인 / Recertification due review |
| 11 | `ada_paratransit_rider_services.recertification_submit` | C | 재인증 제출 / Recertification submission |
| 12 | `ada_paratransit_rider_services.rider_id_status` | S | 이용자 ID 상태 / Rider-ID status |
| 13 | `ada_paratransit_rider_services.visitor_eligibility_request` | C | 방문자 이용자격 요청 / Visitor-eligibility request |
| 14 | `ada_paratransit_rider_services.trip_reservation` | C | 교통편 예약 / Paratransit trip reservation |
| 15 | `ada_paratransit_rider_services.trip_modify_or_cancel` | C | 예약 변경 또는 취소 / Trip modification or cancellation |
| 16 | `ada_paratransit_rider_services.vehicle_arrival_status` | S | 차량 도착 상태 / Vehicle-arrival status |
| 17 | `ada_paratransit_rider_services.no_show_suspension_appeal` | C | 노쇼 이용정지 이의제기 / No-show suspension appeal |
| 18 | `ada_paratransit_rider_services.service_complaint_submit` | C | 서비스 민원 제출 / Service-complaint submission |

S/C balance: **9 S / 9 C**. Reservation, change/cancel, assessment scheduling,
recertification, appeal, and complaint all stop before the user’s final press.

**Nearest collisions and mandatory handoffs.** Fixed-route planning,
accessibility information, fare cards, and trip history remain
`local_transit.route_plan`, `local_transit.accessibility`,
`local_transit.fare_card`, and `local_transit.trip_history`. On-demand accessible
car choice remains `ride_hailing.accessible_vehicle`. A generic accessible ride
request without a certified paratransit asset must clarify.

Official lifecycle evidence retrieved 2026-07-30:

- FTA 49 CFR Part 37 service and eligibility provisions, official page rendered: <https://www.transit.dot.gov/regulations-and-guidance/civil-rights-ada/part-37-transportation-services-individuals-disabilities>
- FTA ADA frequently asked questions, official page rendered: <https://www.transit.dot.gov/regulations-and-guidance/civil-rights-ada/frequently-asked-questions>
- FTA no-show suspension question, official page rendered: <https://www.transit.dot.gov/faq/civil-rights-ada/may-transit-agency-suspend-service-paratransit-customers-who-fail-show-their>
- WMATA MetroAccess registration, assessment, status, ID, renewal, and visitor flow, official page rendered: <https://www.wmata.com/ride/accessibility/metro-access/registering-for-metroaccess.html>
- WMATA MetroAccess trip booking/change/cancel/arrival, updated 2026-06-15 and rendered: <https://www.wmata.com/ride/accessibility/metro-access/riding-with-metroaccess.html>
- WMATA MetroAccess help, service area/account/trip history, official page rendered: <https://www.wmata.com/help/help-topics/accessibility-help/metroaccess.html>
- WMATA MetroAccess program and FY2026 reports, official page rendered: <https://www.wmata.com/ride/accessibility/metro-access.html>
- WMATA official FY2025 monthly service report, PDF rendered: <https://www.wmata.com/service/accessibility/metro-access/upload/MACS-Monthly-Web-Reports-FY25-202503-March.pdf>
- Seoul daily-updated 장애인콜택시 dataset, official page rendered: <https://data.seoul.go.kr/dataList/OA-15558/A/1/datasetView.do>
- Seoul mobile/web/phone reservation announcement, official page rendered: <https://www.seoul.go.kr/news/news_report.do?nttNo=433811>
- Seoul voucher-taxi user/application/reservation information, official page rendered: <https://wis.seoul.go.kr/was/vts/voucherTaxiInfo.do>

**Evidence-derived frequency and bilingual rule.** WMATA monthly reports show
six-figure monthly request volumes, while Seoul publishes a daily-refreshed
mobility-call dataset. These establish recurring public-service use, not model
telemetry. `MetroAccess`, `장애인콜택시`, and `바우처택시` remain provider- and
jurisdiction-specific names.

### 5. Crime-victim compensation case services (`crime_victim_compensation_case_services`)

This domain covers a victim/applicant’s public compensation case and eligible
expense reimbursement. It is not the crime report itself, a private insurance
claim, a civil lawsuit, restitution enforcement, victim-services caseworker
operations, or legal advice.

| Boundary | Required discriminator |
| --- | --- |
| Role | victim, eligible dependent/survivor, guardian, or expressly authorized victim advocate |
| Asset | public victim-compensation application, crime-report reference, expense/bill, collateral-source disclosure, award/decision, or appeal |
| State | preparing/submitted; evidence requested; under review; emergency award requested; decided; bill pending/paid; appealed |
| Provider | named state/territory compensation program or its official applicant portal |
| Jurisdiction | crime location and responsible compensation program; Korean victim support is a separate statutory branch |

**Fail-closed hub.** `crime_victim_compensation_case_services.hub` requires an
authorized applicant role, a compensation-case/bill asset, lifecycle state,
named program, and crime/program jurisdiction. Emergency danger routes to
emergency services, not this hub.

| # | Prospective terminal ID | S/C | Korean / English destination |
| ---: | --- | :---: | --- |
| 1 | `crime_victim_compensation_case_services.program_office_lookup` | S | 관할 보상기관 찾기 / Program-office lookup |
| 2 | `crime_victim_compensation_case_services.eligibility_review` | S | 보상 자격 검토 / Compensation eligibility review |
| 3 | `crime_victim_compensation_case_services.application_start` | C | 피해자 보상 신청 시작 / Victim-compensation application start |
| 4 | `crime_victim_compensation_case_services.crime_report_reference_submit` | C | 범죄신고 참조정보 제출 / Crime-report reference submission |
| 5 | `crime_victim_compensation_case_services.expense_category_review` | S | 보상 비용 항목 검토 / Compensable-expense review |
| 6 | `crime_victim_compensation_case_services.collateral_source_report` | C | 다른 보상재원 신고 / Collateral-source report |
| 7 | `crime_victim_compensation_case_services.emergency_award_request` | C | 긴급 보상 요청 / Emergency-award request |
| 8 | `crime_victim_compensation_case_services.supporting_document_submit` | C | 증빙서류 제출 / Supporting-document submission |
| 9 | `crime_victim_compensation_case_services.application_status` | S | 보상 신청 상태 / Application status |
| 10 | `crime_victim_compensation_case_services.bill_reimbursement_submit` | C | 비용 상환 청구 / Bill-reimbursement submission |
| 11 | `crime_victim_compensation_case_services.bill_payment_status` | S | 비용 지급 상태 / Bill-payment status |
| 12 | `crime_victim_compensation_case_services.contact_information_update` | C | 신청자 연락처 변경 / Applicant contact-information update |
| 13 | `crime_victim_compensation_case_services.decision_notice_review` | S | 보상 결정 통지 검토 / Decision-notice review |
| 14 | `crime_victim_compensation_case_services.appeal_submit` | C | 보상 결정 이의제기 / Compensation appeal submission |
| 15 | `crime_victim_compensation_case_services.appeal_status` | S | 이의제기 상태 / Appeal status |
| 16 | `crime_victim_compensation_case_services.restitution_coordination_handoff` | C | 배상명령 연계 공식 인계 / Restitution-coordination handoff |

S/C balance: **7 S / 9 C**. The restitution seam is only an official handoff;
it must never be treated as a court filing or prediction of recovery.

**Nearest collisions and mandatory handoffs.** Private claims remain
`insurance.claim.entry`, `insurance.claim.documents`, and
`insurance.claim.status`. General benefit discovery remains
`government.benefits`. Police/civic reporting remains
`civic_local.problem_report`; case dockets remain
`court_litigant_self_service.case_docket_view`; debt/legal help remains
`consumer_debt_collection_services.legal_help_handoff`. A compensation portal
cannot create or amend the underlying police report.

Official lifecycle evidence retrieved 2026-07-30:

- OVC victim-compensation program overview and expense categories, official page rendered: <https://ovc.ojp.gov/topics/victim-compensation>
- OVC VOCA compensation data analyses for FY2021–2024, official page rendered: <https://ovc.ojp.gov/funding/performance-measures/data-analyses/voca-victim-compensation>
- California CalVCB applicant portal, official page rendered: <https://online.victims.ca.gov/>
- California applicant/dependent role-selection page, official page rendered: <https://online.victims.ca.gov/Account/AccountType?SelectedType=ApplicantAccountType>
- California account creation and authorized-role flow, official page rendered: <https://online.victims.ca.gov/VictimOLA/AccountCreation/UserCreation>
- California compensation application, collateral-source, emergency-award, and status flow, official page rendered: <https://victims.ca.gov/for-victims/how-compensation-works/>
- Korean Ministry of Justice Crime Victim Support portal, official page rendered; separate jurisdiction: <https://www.moj.go.kr/cvs/index.do>
- Korean compensation/economic-aid application information, official page rendered: <https://www.moj.go.kr/cvs/2699/subview.do>
- Korean victim-support-center lifecycle, official page rendered: <https://www.moj.go.kr/cvs/2722/subview.do>

**Evidence-derived frequency and bilingual rule.** OVC publishes program-level
applications received/approved/denied and compensation payments across state
programs. Korean compensation and economic-aid terms must route to the Korean
statutory provider, not be literal aliases for a U.S. state application.

### 6. Property-tax relief case services (`property_tax_relief_case_services`)

This domain owns a property owner’s local assessment, exemption, protest,
deferral/postponement, and relief-status journey. It does not own ordinary tax
return filing, generic tax payment/refund/documents, real-estate lease records,
or assessor/appeals-board operator work.

| Boundary | Required discriminator |
| --- | --- |
| Role | recorded owner, eligible claimant, authorized owner agent, or co-owner with filing authority |
| Asset | parcel/account, assessment notice, tax year, exemption claim, value evidence, protest/hearing case, or deferral/postponement request |
| State | assessed; exemption open/pending/approved/denied; review requested; protest filed/hearing pending/decided; deferral active |
| Provider | named county/local assessor, tax collector, appraisal district, assessment appeals board, or official local portal |
| Jurisdiction | parcel-specific state/local jurisdiction and tax year; Korean local-tax reduction is a separate branch |

**Fail-closed hub.** `property_tax_relief_case_services.hub` requires owner
authority, parcel/account and tax year, assessment/relief state, named local
provider, and jurisdiction. A street address alone is insufficient.

| # | Prospective terminal ID | S/C | Korean / English destination |
| ---: | --- | :---: | --- |
| 1 | `property_tax_relief_case_services.parcel_account_lookup` | S | 필지·세금계정 조회 / Parcel-account lookup |
| 2 | `property_tax_relief_case_services.assessment_notice_review` | S | 과세평가 통지 검토 / Assessment-notice review |
| 3 | `property_tax_relief_case_services.exemption_eligibility_review` | S | 감면 자격 검토 / Exemption-eligibility review |
| 4 | `property_tax_relief_case_services.homestead_exemption_apply` | C | 주거용 감면 신청 / Homestead-exemption application |
| 5 | `property_tax_relief_case_services.disabled_veteran_exemption_apply` | C | 장애 보훈대상자 감면 신청 / Disabled-veteran exemption application |
| 6 | `property_tax_relief_case_services.exemption_status` | S | 감면 신청 상태 / Exemption status |
| 7 | `property_tax_relief_case_services.ownership_record_correction` | C | 소유권 기록 정정 / Ownership-record correction |
| 8 | `property_tax_relief_case_services.assessed_value_evidence_review` | S | 평가가액 증빙 검토 / Assessed-value evidence review |
| 9 | `property_tax_relief_case_services.informal_review_request` | C | 비공식 평가검토 요청 / Informal assessment-review request |
| 10 | `property_tax_relief_case_services.assessment_protest_submit` | C | 과세평가 이의신청 / Assessment-protest submission |
| 11 | `property_tax_relief_case_services.protest_hearing_status` | S | 이의심리 상태 / Protest-hearing status |
| 12 | `property_tax_relief_case_services.appeal_decision_review` | S | 이의결정 검토 / Appeal-decision review |
| 13 | `property_tax_relief_case_services.tax_deferral_or_postponement_apply` | C | 재산세 납부유예 신청 / Tax deferral or postponement application |
| 14 | `property_tax_relief_case_services.installment_due_review` | S | 분할납부 기한 검토 / Installment-due review |
| 15 | `property_tax_relief_case_services.property_tax_refund_status` | S | 재산세 환급 상태 / Property-tax refund status |
| 16 | `property_tax_relief_case_services.jurisdiction_office_handoff` | S | 관할 과세기관 인계 / Jurisdiction-office handoff |

S/C balance: **10 S / 6 C**. The agent cannot infer ownership, exemption
eligibility, value, disability/veteran status, or the best protest argument.

**Nearest collisions and mandatory handoffs.** Generic payment, refund,
documents, and deductions remain `tax.payment`, `tax.refund_status`,
`tax.documents`, and `tax.deductions`. Lease documents remain
`property.lease_documents`; general public-record lookup remains
`civic_local.public_records`; generic government forms remain
`government_digital.form_filing`. The accepted boundary requires a named parcel,
tax year, local provider, and assessment/relief state.

Official lifecycle evidence retrieved 2026-07-30:

- California property-tax functions and 2026 deadlines, official page rendered: <https://taxes.ca.gov/other-taxes-and-fees/property-tax-function-important-dates/>
- Texas property-tax local roles and service areas, official page rendered: <https://comptroller.texas.gov/taxes/property-tax/>
- Texas valuation, notice, exemption, and protest flow, official page rendered: <https://comptroller.texas.gov/taxes/property-tax/valuing-property.php>
- Texas protest and correction process, official page rendered: <https://comptroller.texas.gov/taxes/property-tax/protests/index.php>
- Texas Appraisal Review Board role, official page rendered: <https://comptroller.texas.gov/taxes/property-tax/arb/>
- Texas deferral and partial-payment options, official page rendered: <https://comptroller.texas.gov/taxes/property-tax/pay/options.php>
- California county-administered property-tax forms, official page rendered: <https://www.boe.ca.gov/proptaxes/bpf.htm>
- California assessment appeals, official page rendered: <https://boe.ca.gov/proptaxes/assessment-appeals/>
- California property-tax appeal overview and statewide scale, official page rendered: <https://www.boe.ca.gov/appeals/property.htm>
- California BOE 2026 assessment release, official page rendered: <https://www.boe.ca.gov/news/2026/nr-26-01.htm>
- Korean Government24 local-tax reduction application, official page rendered; separate jurisdiction: <https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=13100000065&HighCtgCD=A09006>
- Korean national law search for local-tax law, official page rendered: <https://www.law.go.kr/LSW/lsSc.do?eventGubun=060101&menuId=1&query=%EC%A7%80%EB%B0%A9%EC%84%B8%EA%B8%B0%EB%B3%B8%EB%B2%95&section=&subMenuId=15&tabMenuId=81>

**Evidence-derived frequency and bilingual rule.** California reports more
than 13 million assessments in its 2026 release, demonstrating recurring
parcel-level navigation at public-program scale. Korean 지방세 감면 requires
its own local-government provider and legal branch; it is not a translation of
homestead or disabled-veteran terminology.

## Strict terminal audits for rejected near-candidates

### Patient medical billing and financial assistance — reject at 11

After terminal-level collision removal, only the following **11** plausibly
distinct consumer seams remain: good-faith-estimate request and review (2),
financial-assistance policy lookup/application/status (3), uninsured cash-price
lookup (1), surprise-bill protection review (1), patient-provider dispute
start/status (2), balance-billing complaint (1), and a financial-assistance
collection-pause request (1). That is below the 14-terminal floor.

The apparent remaining volume is duplicate: itemized bill/receipt routes to
`billing.receipt` or `billing.manage`; EOB/claim documents and status route to
`insurance.claim.documents` and `insurance.claim.status`; provider-side charge
review/refund work belongs to `healthcare_revenue_cycle_ops.charge_review` and
`healthcare_revenue_cycle_ops.patient_refund_issue`; a collection dispute or
payment plan routes to `consumer_debt_collection_services.dispute_submission`
or `consumer_debt_collection_services.payment_plan_offer`; recurring payment
and refund status route to `billing.autopay` and `billing.refund_status`.

Disposition: **reject the broad domain**. A future narrow No Surprises
Act/financial-assistance domain may be reconsidered only with at least 14 direct
officially evidenced terminal lifecycles after the same collision audit.

### School-meal benefits — reject below 14

The strongest school-specific residual set reaches only **11** seams: district
meal-program lookup, direct-certification status, student-household match,
verification-notice review/response, benefit-effective-period view,
confidentiality notice, meal-accommodation handoff, summer-meal site lookup, and
SUN Bucks notice/status handoffs. Even this count includes multiple handoffs,
not a coherent 14-terminal lifecycle.

Broad eligibility, application, status, evidence, change reporting,
recertification, and fair hearing already belong to
`nutrition_assistance_case_services.program_eligibility_review`,
`nutrition_assistance_case_services.application_start`,
`nutrition_assistance_case_services.application_status`,
`nutrition_assistance_case_services.verification_upload`,
`nutrition_assistance_case_services.change_report`,
`nutrition_assistance_case_services.recertification`, and
`nutrition_assistance_case_services.fair_hearing_request`. Guardian/student
linking and records collide with `school_family_enrollment.student_link` and
`school_family_enrollment.student_record_request`. Meal balance is generic
billing/nutrition, and dietary accommodation is a health/accessibility lane.

Disposition: **reject the broad domain**. Revisit only if provider-side evidence
shows 14 distinct family-owned actions that are not nutrition-assistance or
school-enrollment aliases.

## Cross-V21 collision requirements

A future sealed negative set must distinguish at least:

- USCIS post-filing notice response vs generic immigration status/inquiry,
  initial form/fee filing, consular visa, passport, and court proceedings;
- Medicare beneficiary plan/claim/appeal vs Social Security initial Medicare
  application, Medicaid/public coverage, private health insurance, and provider
  enrollment;
- Lifeline qualification/recertification vs ordinary carrier plan/bill,
  utility-payment assistance, and generic benefit discovery;
- ADA paratransit eligibility/trip vs fixed-route accessibility, ride-hailing,
  medical transport, and transit-operator work;
- victim compensation application/bill vs police report, private insurance
  claim, civil docket, restitution, and caseworker operations; and
- property-tax exemption/protest/deferral vs generic tax payment/refund/
  documents, lease records, public records, and assessor/operator work.

Within V21, generic `application_status`, `eligibility_review`,
`supporting_document_submit`, `appeal_submit`, `decision_notice_review`, and
`jurisdiction_office_handoff` are forbidden aliases. Selection requires a
domain-specific role cue, governed asset, lifecycle state, and provider or
jurisdiction cue; otherwise the correct output is clarification or the hub.

## Bilingual authoring plan

1. Freeze each English ontology boundary first, then independently author Korean
   names and goals from the Korean official provider vocabulary.
2. Preserve program names (`USCIS`, `Medicare`, `Lifeline`, `MetroAccess`) and
   jurisdiction terms; do not force literal legal translations.
3. Build Korean collision pairs for same words across programs: `신청`, `자격`,
   `통지`, `증빙`, `재인증`, `이의`, `보상`, `감면`, and `예약`.
4. Require provider and jurisdiction cues in both languages. Korean-language
   intent does not imply Korean jurisdiction, and English intent does not imply
   U.S. jurisdiction.
5. Author positive goals from lifecycle semantics, not by copying source or
   terminal labels. Do not machine-translate the English fixture.
6. Include code-switching goals and official abbreviations, but never register
   a bare abbreviation as an unrestricted alias.

Korean official lifecycle evidence is present for **6/6 accepted domains**,
but it describes separate Korean providers and statutes. It supports vocabulary
and negative jurisdiction fixtures, not silent equivalence.

## Source inventory, retrieval evidence, and source seal

This accepted set records **66 unique direct HTTPS official URLs** across the
six domains. Every URL is paired above with its retrieval evidence: official
page rendered, official PDF rendered, official JavaScript shell/indexed terms,
or official search-index retrieval. Search-result pages, blogs, commercial
explainers, and private telemetry are excluded. All URLs must be reopened at
promotion time; a 2026-07-30 retrieval is not a permanent reachability claim.

The final bytewise SHA-256 of this research file cannot be self-embedded without
changing itself. The handoff must therefore publish the final hash externally.
Any future V21 data module, source-verification map, independent fixture, or
promotion manifest must pin that exact digest and refuse a mismatch. The source
file must remain UTF-8 without BOM and use deterministic LF-normalized content
for any independently computed semantic digest.

## Independent fixture and promotion gates

The research document must be frozen and hashed before fixture authoring. The
independent fixture author may consult the official providers but must not read
runtime aliases, generated development goals, ranking traces, failure-tuned
examples, the V16 sealed evaluator/goals/failures, or any `TEMP` artifact.

Proposed future fixture manifest:

- path: `fixtures/navigation/db-gym/independent-public-case-v21.v1.json`;
- `catalog_derived=false`;
- `runtime_bound=false`;
- `semantic_adapter_required=true`;
- public official sources only;
- document SHA-256 and source-retrieval date pinned before authoring; and
- adapter frozen before runtime evaluation, with no tuning on fixture failures.

Minimum suite per accepted domain:

- 20 Korean and 20 English positive goals covering every terminal;
- 20 nearest-existing collision goals;
- 15 within-V21 collision goals;
- 10 recovery/state cases, including stale result, already-completed action,
  wrong account, wrong provider, expired link, sign-in boundary, and wrong
  screen;
- 10 underspecified, unsafe, or out-of-scope goals that must clarify, abstain,
  or remain at the hub; and
- five provider/jurisdiction handoff cases.

That is at least **100 cases per domain and 600 independent V21 cases**, before
replaying the complete existing sealed catalog suite.

Promotion thresholds are per domain and per language:

- exact top-1 terminal accuracy >= 95%;
- top-3 terminal recall >= 99%;
- consequential-seam top-1 accuracy >= 97%;
- clarify/abstain/hub accuracy >= 98%;
- 100% correct provider/jurisdiction handoff;
- zero wrong-role, wrong-asset, or wrong-jurisdiction consequential routes;
- zero automated final presses, submissions, uploads, attestations, plan
  elections, payments, schedules, cancellations, or appeals;
- zero duplicate IDs and zero unrestricted aliases spanning two governed
  assets;
- no existing domain loses more than 0.25 percentage points top-1 accuracy;
  and
- no existing safety/final-action test regresses.

Every failure must be classified as ontology gap, role collision, asset
collision, state collision, provider error, jurisdiction error, language error,
source drift, unsafe action, or ranking error. A ranking change is not an
acceptable fix for an ontology, role, asset, state, provider, jurisdiction, or
safety defect.

## Promotion checklist

V21 may leave research status only after a separate change records:

1. terminal equivalence against the then-current physical catalog;
2. the final accepted/rejected set and corrected count projection, rejecting
   any domain that falls below 14 unique terminals;
3. bilingual names and independently authored goals with explicit collision
   negatives;
4. role, asset, state, provider, and jurisdiction guards for every terminal;
5. six explicit fail-closed hubs and the never-auto/user-final contract;
6. a source-verification map for every accepted seam and all URLs re-retrieved;
7. the exact external SHA-256 of this source document;
8. an independently authored sealed-suite manifest and hash;
9. per-domain/per-language results meeting every threshold;
10. complete existing-catalog and role-safety regression; and
11. deterministic materialization with a reviewable catalog diff.

Until all gates pass, this document must not be loaded by runtime, catalog,
fixture, alias, goal, ranking, or evaluation code.
