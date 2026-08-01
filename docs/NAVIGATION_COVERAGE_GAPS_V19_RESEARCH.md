# Navigation coverage gap research — V19

Status: **research-only and noncanonical**. This file is an evidence and
collision-review backlog. It does not add runtime domains, functions, aliases,
goals, fixtures, or ranking weight. Promotion requires a separate data change,
independent evaluation, and an explicit catalog version decision.

## Prospective baseline after V18

If every V18 research candidate is accepted exactly as projected, the starting
point for V19 is **215 domains / 3,610 functions / 3,368 intents**. Those are the
prospective post-V18 counts, not the current physical catalog and not evidence
that V18 has passed promotion.

This audit found **nine evidence-ready gaps**, not twelve. Quality was preferred
over filling a quota. The nine candidates below contain 114 prospective
terminals and nine fail-closed hubs. If all survived implementation unchanged,
the mechanical projection would be 224 domains / 3,733 functions / 3,482
intents. That projection is informational only; terminal equivalence review may
reduce it before implementation.

## Audit and acceptance method

The comparison set was canonical V15 plus the prospective additions in
`scripts/navigation_catalog_v16_data.py`,
`scripts/navigation_catalog_v17_data.py`, and
`docs/NAVIGATION_COVERAGE_GAPS_V18_RESEARCH.md`. A gap was accepted only when:

- it represents a frequent consumer, resident, applicant, participant, or
  citizen journey in a first-seen app;
- the actor role, governed asset, lifecycle state, provider, and jurisdiction
  can be distinguished from the nearest existing terminal;
- at least five direct official lifecycle pages were available, including at
  least one Korean government or provider page;
- consequential states have a clear user-owned final action and a safe point at
  which navigation must stop;
- the candidate can fail closed when role, state, or jurisdiction is missing;
- adjacent canonical terminals can be named as collisions rather than hidden by
  broad aliases.

Every proposed terminal ID in this document is unique within this research
layer. The IDs are seams for evaluation, not permission to implement them
verbatim.

## Shared safety contract

All nine domains must use a fail-closed hub when intent is underspecified. Read
destinations may stop on the destination screen. Any submit, request, cancel,
change, certify, pay, schedule, report, appeal, or identity-bearing action must
use `automation_policy=never_auto`, `stop_policy=before_action`, and
`user_owned_final_press=true`.

The agent may explain the next screen and required evidence, but it must not:

- assert legal, voting, benefits, medical-coverage, retirement, or visa
  eligibility;
- invent questionnaire answers, attestations, dates, identity attributes, or
  supporting-document facts;
- select a plan, investment, ballot choice, legal strategy, or visa answer for
  the user;
- submit, pay, certify, appeal, cancel, change an address, or transmit a filing;
- cross from an applicant-facing surface into an operator or adjudicator
  surface merely because the labels are similar.

## Evidence-ready high-frequency gaps

### 1. Citizen voter registration and ballot services (`voter_registration_ballot_services`)

**Boundary.** The role is an individual eligible voter or prospective voter.
The assets are that person's registration record, polling assignment, mail
ballot request, and cure or accommodation request in one election
jurisdiction. This is distinct from the registrar/election-worker role and its
queues, issuance controls, ballot-style administration, and polling-place
operations.

**Lifecycle states.** Eligibility information -> registration application ->
registration status/update/cancellation -> polling or early-voting lookup ->
mail-ballot request/status -> ballot cure or accessibility accommodation. Vote
choice and ballot casting are explicitly out of scope.

**Prospective terminal seams.**

- `voter_registration_ballot_services.registration_eligibility_review`
- `voter_registration_ballot_services.registration_apply`
- `voter_registration_ballot_services.registration_status`
- `voter_registration_ballot_services.registration_update`
- `voter_registration_ballot_services.registration_cancel`
- `voter_registration_ballot_services.polling_place_lookup`
- `voter_registration_ballot_services.voter_id_requirements`
- `voter_registration_ballot_services.mail_ballot_request`
- `voter_registration_ballot_services.mail_ballot_status`
- `voter_registration_ballot_services.ballot_cure`
- `voter_registration_ballot_services.early_voting_lookup`
- `voter_registration_ballot_services.accessibility_accommodation`

**Nearest canonical collisions.**
`election_administration.voter_registration_record`,
`election_administration.voter_registration_update`,
`election_administration.ballot_style_review`,
`election_administration.absentee_request_queue`,
`election_administration.absentee_ballot_issue`, and
`election_administration.polling_place_open` are operator-side assets and
actions. They must be negative examples for citizen goals, not aliases.

**Safety/final-action gates.** Registration application, record update,
cancellation, mail-ballot request, cure, and accommodation requests stop before
the final press. The agent must not infer eligibility, party affiliation,
identity, ballot selections, or jurisdiction.

Official lifecycle evidence opened 2026-07-30:

- https://vote.gov/register
- https://vote.gov/guide-to-voting
- https://www.eac.gov/voters/register-and-vote-in-your-state
- https://www.eac.gov/voters/national-mail-voter-registration-form
- https://www.eac.gov/voters/national-mail-voter-registration-form-faqs
- https://www.eac.gov/voters/voter-faqs
- Korean official evidence: https://www.nec.go.kr/site/nec/ex/bbs/View.do?bcIdx=231068&cbIdx=1147

### 2. Vital-record certificate services (`vital_records_certificate_services`)

**Boundary.** The role is the subject, parent, spouse, next of kin, or other
legally authorized requester. The governed asset is a specific birth, death,
marriage, or related civil-status record held by a named issuing authority.
This is narrower than generic government certificate search/issue/wallet and
does not cover creating a fictional record or deciding requester authority.

**Lifecycle states.** Issuing-authority lookup -> requester-authority review ->
copy order -> delivery/status -> correction or amendment request -> supporting
evidence -> authentication handoff where applicable.

**Prospective terminal seams.**

- `vital_records_certificate_services.issuing_authority_lookup`
- `vital_records_certificate_services.authorized_requester_review`
- `vital_records_certificate_services.record_copy_order`
- `vital_records_certificate_services.delivery_method`
- `vital_records_certificate_services.order_status`
- `vital_records_certificate_services.birth_record_correction`
- `vital_records_certificate_services.death_record_correction`
- `vital_records_certificate_services.marriage_record_correction`
- `vital_records_certificate_services.birth_record_amendment`
- `vital_records_certificate_services.certificate_authentication_handoff`

**Nearest canonical collisions.** `government.certificate_search`,
`government.certificate_issue`, and `government.certificate_wallet` own generic
certificate discovery, issuance, and storage. V19 is valid only when record
type, subject relationship, issuing authority, and correction/amendment state
are present. Generic copy issuance should hand off rather than fork an
unrestricted duplicate.

**Safety/final-action gates.** Ordering, amendment, correction, delivery choice,
and authentication requests stop before final submission or payment. The agent
must not decide requester entitlement, fabricate kinship, or alter record facts.

Official lifecycle evidence opened 2026-07-30:

- https://www.cdc.gov/nchs/w2w/index.htm
- https://www.health.ny.gov/vital_records/
- https://www.health.ny.gov/vital_records/birth.htm
- https://www.health.ny.gov/vital_records/amend_corr.htm
- https://www.health.ny.gov/vital_records/amend_birth.htm
- https://www.health.ny.gov/vital_records/docs/public_instructions_for_death_corrections.pdf
- https://www.health.ny.gov/vital_records/docs/public_instructions_for_marriage_corrections.pdf
- Korean official evidence: https://m.gov.kr/mw/AA020InfoCappView.do?CappBizCD=97400000004&HighCtgCD=A01008&tp_seq=

### 3. Nutrition-assistance case services (`nutrition_assistance_case_services`)

**Boundary.** The role is a household applicant, recipient, parent, guardian,
or WIC participant. The assets are a named SNAP/WIC-equivalent application,
interview, verification task, eligibility notice, benefit account, EBT card,
renewal, or hearing request. This is distinct from a social-services caseworker
reviewing and deciding eligibility.

**Lifecycle states.** Program discovery/eligibility information -> agency lookup
-> application -> interview/verification -> notice -> benefit or card service ->
change reporting -> recertification -> hearing request. SNAP and WIC remain
separate program states even when a provider app presents both.

**Prospective terminal seams.**

- `nutrition_assistance_case_services.program_eligibility_review`
- `nutrition_assistance_case_services.state_agency_lookup`
- `nutrition_assistance_case_services.application_start`
- `nutrition_assistance_case_services.application_status`
- `nutrition_assistance_case_services.interview_schedule`
- `nutrition_assistance_case_services.verification_upload`
- `nutrition_assistance_case_services.eligibility_notice`
- `nutrition_assistance_case_services.benefit_balance`
- `nutrition_assistance_case_services.ebt_card_replace`
- `nutrition_assistance_case_services.change_report`
- `nutrition_assistance_case_services.recertification`
- `nutrition_assistance_case_services.fair_hearing_request`
- `nutrition_assistance_case_services.wic_appointment`

**Nearest canonical collisions.** `government.benefits` is only a broad benefits
hub. `social_services_casework.eligibility_application_review`,
`social_services_casework.benefit_eligibility_decision`, and
`social_services_casework.benefit_schedule_disbursement` are worker-side
operations. Applicant goals must never route into those terminals.

**Safety/final-action gates.** Application, interview booking, verification
upload, replacement-card request, change report, recertification, appointment,
and hearing request stop before submission. The agent may surface official
criteria but may not declare eligibility, choose household answers, or certify
income and identity facts.

Official lifecycle evidence opened 2026-07-30:

- https://www.fns.usda.gov/snap/recipient/eligibility
- https://www.usa.gov/food-stamps
- https://www.fns.usda.gov/snap/state/interview-toolkit/providing
- https://www.fns.usda.gov/wic/benefits
- https://www.fns.usda.gov/wic/faqs
- https://www.fns.usda.gov/wic/program-contacts
- https://www.fns.usda.gov/wic/application-toolkit/model-online-application
- Korean official evidence: https://www.mohw.go.kr/menu.es?mid=a10708010200

### 4. Self-represented court litigant services (`court_litigant_self_service`)

**Boundary.** The role is a self-represented claimant, petitioner, defendant,
respondent, or other named party. The governed asset is that party's case,
filing packet, fee-waiver request, service task, docket, deadline, response, or
order in a known court and jurisdiction. This is not clerk case administration
or professional legal-practice operations.

**Lifecycle states.** Case-type and jurisdiction triage -> form packet -> filing
preparation/submission -> fee-waiver request -> service/proof of service ->
docket and deadline view -> response -> order retrieval. Legal advice and
strategy remain out of scope.

**Prospective terminal seams.**

- `court_litigant_self_service.case_type_triage`
- `court_litigant_self_service.court_jurisdiction_lookup`
- `court_litigant_self_service.form_packet`
- `court_litigant_self_service.filing_prepare`
- `court_litigant_self_service.filing_submit`
- `court_litigant_self_service.filing_status`
- `court_litigant_self_service.fee_waiver_request`
- `court_litigant_self_service.service_instructions`
- `court_litigant_self_service.proof_of_service_file`
- `court_litigant_self_service.case_docket_view`
- `court_litigant_self_service.hearing_deadline_view`
- `court_litigant_self_service.response_prepare`
- `court_litigant_self_service.response_submit`
- `court_litigant_self_service.order_download`

**Nearest canonical collisions.** `legal_practice_ops.court_filing_prepare` and
`legal_practice_ops.court_filing_submit` are professional workflow terminals.
`court_clerk_case_admin.case_open`,
`court_clerk_case_admin.filing_docket_entry`,
`court_clerk_case_admin.fee_waiver_route`,
`court_clerk_case_admin.summons_issue`,
`court_clerk_case_admin.docket_sheet_view`,
`court_clerk_case_admin.fee_payment_status`,
`court_clerk_case_admin.service_notice_status`, and
`court_clerk_case_admin.calendar_deadline_view` are clerk-side states. Party
identity and self-represented context are mandatory.

**Safety/final-action gates.** Any filing, waiver, proof of service, or response
submission stops before final transmission. The agent must not select causes of
action, make deadline guarantees, construct legal arguments, sign declarations,
or infer service completion.

Official lifecycle evidence opened 2026-07-30:

- https://selfhelp.courts.ca.gov/
- https://www.selfhelp.courts.ca.gov/small-claims/start-case/file
- https://selfhelp.courts.ca.gov/court-basics/service
- https://selfhelp.courts.ca.gov/fee-waiver/if-fee-waiver-isnt-granted
- https://www.uscourts.gov/court-records/find-a-case-pacer
- https://pacer.uscourts.gov/file-case
- Korean official evidence: https://ecfs.scourt.go.kr/psp/help/ecfs_scourt_manual_v1.1.pdf
- Korean official evidence: https://www.scourt.go.kr/judiciary/information/public/

### 5. Jury-summons response services (`jury_summons_response_services`)

**Boundary.** The role is a person who received or is verifying a jury summons.
The assets are that summons, qualification questionnaire, reporting
instruction, postponement/excusal/accommodation request, attendance record, and
juror payment. The domain does not administer jury pools, select jurors, or
decide requests.

**Lifecycle states.** Summons authenticity -> qualification questionnaire ->
reporting status/instructions -> postponement, excuse, or accommodation request
-> attendance/service completion -> payment status.

**Prospective terminal seams.**

- `jury_summons_response_services.summons_authenticity_check`
- `jury_summons_response_services.qualification_questionnaire`
- `jury_summons_response_services.reporting_status`
- `jury_summons_response_services.reporting_instructions`
- `jury_summons_response_services.postponement_request`
- `jury_summons_response_services.excusal_request`
- `jury_summons_response_services.accommodation_request`
- `jury_summons_response_services.attendance_checkin`
- `jury_summons_response_services.service_completion_status`
- `jury_summons_response_services.payment_status`

**Nearest canonical collisions.** `court_clerk_case_admin.summons_issue` concerns
a case summons issued by a clerk, not a juror's response to a jury summons.
Election-administration registration records may supply jury-source data in
some jurisdictions, but are not juror-service assets. Both must be explicit
negative examples.

**Safety/final-action gates.** Questionnaire, postponement, excusal,
accommodation, and check-in actions stop before final submission. The agent must
not answer qualification questions, invent hardship, guarantee an excuse, or
mark attendance complete.

Official lifecycle evidence opened 2026-07-30:

- https://www.uscourts.gov/court-programs/jury-service
- https://www.uscourts.gov/court-programs/jury-service/summoned-federal-jury-service
- https://www.uscourts.gov/court-programs/jury-service/juror-selection-process
- https://www.uscourts.gov/court-programs/jury-service/juror-qualifications-exemptions-and-excuses
- https://www.uscourts.gov/court-programs/jury-service/juror-pay
- https://www.uscourts.gov/court-programs/jury-service/types-juries
- https://www.uscourts.gov/forms-rules/forms/jury-forms
- Korean official evidence: https://www.scourt.go.kr/nm/min_9/min_9_8/index.html
- Korean official evidence: https://www.scourt.go.kr/nm/min_9/min_9_3/index.html

### 6. Consumer postal-mail services (`consumer_postal_mail_services`)

**Boundary.** The role is a residential recipient, addressee, or householder.
The governed assets are an address-forwarding order, hold-mail request,
redelivery instruction, delivery preference, missing-mail search, or mail-theft
report for postal mail. This excludes postal-network staff operations and the
already modeled parcel-courier shipment lifecycle.

**Lifecycle states.** Address eligibility -> temporary hold or change-of-address
request -> status/modify/cancel -> forwarding-option review -> incoming-mail
preview -> redelivery or delivery instruction -> missing-mail search or theft
report.

**Prospective terminal seams.**

- `consumer_postal_mail_services.address_eligibility`
- `consumer_postal_mail_services.hold_mail_request`
- `consumer_postal_mail_services.hold_mail_status`
- `consumer_postal_mail_services.hold_mail_modify_cancel`
- `consumer_postal_mail_services.change_of_address_request`
- `consumer_postal_mail_services.change_of_address_status`
- `consumer_postal_mail_services.change_of_address_modify_cancel`
- `consumer_postal_mail_services.forwarding_option_compare`
- `consumer_postal_mail_services.incoming_mail_preview`
- `consumer_postal_mail_services.redelivery_request`
- `consumer_postal_mail_services.delivery_instruction_request`
- `consumer_postal_mail_services.missing_mail_search`
- `consumer_postal_mail_services.mail_theft_report`

**Nearest canonical collisions.**
`postal_network_operations.hold_mail_activate`,
`postal_network_operations.forwarding_order_apply`,
`postal_network_operations.mailpiece_tracking`,
`postal_network_operations.delivery_exception_queue`, and
`postal_network_operations.postal_claim_adjudicate` are staff-side operations.
`parcel_courier.hold`, `parcel_courier.reroute`,
`parcel_courier.reschedule`, and `parcel_courier.missing_claim` already own
carrier parcel actions. Package tracking/rescheduling is therefore excluded
from this candidate.

**Safety/final-action gates.** Hold, forwarding, address change, redelivery,
delivery instruction, missing-mail search, and theft report stop before final
submission. The agent must not infer residency, identity, occupancy, or the
ownership of mail.

Official lifecycle evidence opened 2026-07-30:

- https://faq.usps.com/articles/Knowledge/Change-of-Address-The-Basics
- https://faq.usps.com/articles/FAQ/USPS-Hold-Mail-The-Basics/1000
- https://faq.usps.com/articles/Knowledge/Mail-Forwarding-Options
- https://faq.usps.com/articles/Knowledge/Redelivery-The-Basics
- https://faq.usps.com/articles/Knowledge/USPS-Delivery-Instructions-The-Basics
- https://faq.usps.com/articles/Knowledge/Mail-Theft
- Korean official evidence: https://kpds.koreapost.go.kr/site/kpost/download/%EA%B5%AD%EB%82%B4%ED%86%B5%EC%83%81_%EC%9A%B0%ED%8E%B8%EC%9A%94%EA%B8%88%EB%B0%8F%EC%9A%B0%ED%8E%B8%EC%9D%B4%EC%9A%A9%EC%97%90%EA%B4%80%ED%95%9C%EC%88%98%EC%88%98%EB%A3%8C.pdf

### 7. Public health-coverage case services (`public_health_coverage_case_services`)

**Boundary.** The role is a Medicaid/CHIP-equivalent applicant, beneficiary,
parent, guardian, or authorized household representative. The assets are one
public-program application, verification task, eligibility notice, plan
selection, coverage period, renewal, household change, hearing request, or
coverage transition. It is not provider claims administration, a social worker's
decision queue, or generic commercial health-insurance servicing.

**Lifecycle states.** Program screening -> state agency -> application ->
verification/status -> eligibility notice -> plan and effective coverage ->
member card -> household change -> renewal -> hearing or transition to another
coverage channel.

**Prospective terminal seams.**

- `public_health_coverage_case_services.program_eligibility_screen`
- `public_health_coverage_case_services.state_agency_lookup`
- `public_health_coverage_case_services.application_start`
- `public_health_coverage_case_services.application_status`
- `public_health_coverage_case_services.verification_submit`
- `public_health_coverage_case_services.eligibility_notice`
- `public_health_coverage_case_services.managed_plan_select`
- `public_health_coverage_case_services.coverage_effective_status`
- `public_health_coverage_case_services.member_card_status`
- `public_health_coverage_case_services.household_change_report`
- `public_health_coverage_case_services.renewal_due`
- `public_health_coverage_case_services.renewal_submit`
- `public_health_coverage_case_services.fair_hearing_request`
- `public_health_coverage_case_services.coverage_transition`

**Nearest canonical collisions.** `health_insurance.civil_service`,
`health_insurance.eligibility`, `health_insurance.screening`, and
`health_insurance.refund` own broad member/service views. `government.benefits`
is a generic hub. `social_services_casework.eligibility_application_review` and
`social_services_casework.benefit_eligibility_decision` are operator-side. V19
requires named public-program, applicant/beneficiary role, case state, and
jurisdiction; generic insurance status must hand off.

**Safety/final-action gates.** Application, evidence transmission, plan
selection, household change, renewal, hearing, and transition actions stop
before final submission. The agent must not determine eligibility, recommend a
plan, certify household facts, or cancel existing coverage.

Official lifecycle evidence opened 2026-07-30:

- https://www.medicaid.gov/resources-for-states/eligibility-enrollment-and-renewal-tools-and-resources
- https://www.medicaid.gov/medicaid/eligibility-policy
- https://www.healthcare.gov/medicaid-chip/getting-medicaid-chip/
- https://www.healthcare.gov/medicaid-chip/transfer-to-marketplace/
- https://www.healthcare.gov/medicaid-to-marketplace/
- https://www.healthcare.gov/medicaid-chip/using-medicaid-or-chip-coverage/
- https://www.medicaid.gov/medicaid/outreach-tools/medicaid-and-chip-renewals-outreach-and-educational-resources
- Korean official evidence: https://www.nhis.or.kr/static/html/wbdb/f/wbdbf0102.html

### 8. Retirement-plan participant services (`retirement_plan_participant_services`)

**Boundary.** The role is a retirement-plan participant, former employee,
retiree, beneficiary, or alternate payee acting on their own account. The
assets are participant-originated contribution, allocation, beneficiary,
rollover, loan, hardship, distribution, claim, withholding, or payment-account
requests. This is distinct from the plan administrator's recordkeeping,
eligibility determination, adjudication, and release actions.

**Lifecycle states.** Plan terms -> contribution/allocation election ->
beneficiary designation -> rollover -> loan or hardship request -> retirement
distribution/claim -> appeal -> payment and tax settings. Investment advice and
plan-administrator decisions are out of scope.

**Prospective terminal seams.**

- `retirement_plan_participant_services.contribution_rate_election`
- `retirement_plan_participant_services.investment_allocation_change`
- `retirement_plan_participant_services.beneficiary_change_submit`
- `retirement_plan_participant_services.rollover_option_compare`
- `retirement_plan_participant_services.rollover_initiate`
- `retirement_plan_participant_services.loan_estimate`
- `retirement_plan_participant_services.loan_application_submit`
- `retirement_plan_participant_services.hardship_eligibility_review`
- `retirement_plan_participant_services.hardship_withdrawal_apply`
- `retirement_plan_participant_services.retirement_distribution_option`
- `retirement_plan_participant_services.retirement_claim_submit`
- `retirement_plan_participant_services.claim_appeal_submit`
- `retirement_plan_participant_services.payment_account_update`
- `retirement_plan_participant_services.tax_withholding_update`

**Nearest canonical collisions.** The V15 operator domain already owns
`pension_plan_administration.plan_document_version`,
`pension_plan_administration.participant_service_history`,
`pension_plan_administration.eligibility_vesting_status`,
`pension_plan_administration.accrued_benefit_account_view`,
`pension_plan_administration.contribution_allocation_status`,
`pension_plan_administration.beneficiary_record_view`, and
`pension_plan_administration.distribution_claim_status`. It also owns
administrator decisions such as `participant_eligibility_determine`,
`benefit_claim_decide`, and `claim_appeal_decide`. Shared read states must use
explicit equivalence/handoff; V19 adds only participant-originated decisions and
requests. `hr_payroll.benefits_enrollment` remains the employer-benefit
enrollment boundary.

**Safety/final-action gates.** Every election, allocation, beneficiary,
rollover, loan, hardship, distribution, claim, appeal, bank-account, and tax
change stops before final submission. The agent must not recommend investments,
declare hardship eligibility, choose distribution tax treatment, or approve a
claim.

Official lifecycle evidence opened 2026-07-30:

- https://www.irs.gov/retirement-plans/plan-participant-employee/rollovers-of-retirement-plan-and-ira-distributions
- https://www.irs.gov/retirement-plans/plan-participant-employee/changes-in-your-life-may-affect-retirement-planning
- https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-hardship-distributions
- https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-beneficiary
- https://www.irs.gov/retirement-plans/plan-participant-employee/401k-resource-guide-plan-participants-general-distribution-rules
- https://www.irs.gov/retirement-plans/plan-participant-employee/retirement-topics-required-minimum-distributions-rmds
- https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/resource-center/faqs/retirement-plans-and-erisa
- https://www.dol.gov/sites/dolgov/files/ebsa/about-ebsa/our-activities/resource-center/publications/retirement-benefits-filing-claims.pdf
- Korean official evidence: https://nps.or.kr/pnsinfo/ntpsklg/getOHAF0095M0.do

### 9. Consular visa-application services (`consular_visa_application_services`)

**Boundary.** The role is a foreign-national visa applicant or an authorized
representative navigating a named country's consular application process. The
asset is a consular visa application, form instance, fee, interview, document
checklist, post-processing status, passport return, or refusal-information
state. It excludes passports and domestic immigration-benefit petitions/case
management already owned by `government_digital`.

**Lifecycle states.** Visa-category and consular-post discovery -> application
form start/retrieval/submission -> fee -> interview wait-time and scheduling ->
documents -> application/administrative-processing status -> passport return or
refusal information.

**Prospective terminal seams.**

- `consular_visa_application_services.visa_category_review`
- `consular_visa_application_services.post_lookup`
- `consular_visa_application_services.application_form_start`
- `consular_visa_application_services.application_retrieve`
- `consular_visa_application_services.application_submit`
- `consular_visa_application_services.fee_payment`
- `consular_visa_application_services.interview_wait_time`
- `consular_visa_application_services.interview_schedule`
- `consular_visa_application_services.interview_reschedule_cancel`
- `consular_visa_application_services.document_checklist`
- `consular_visa_application_services.application_status`
- `consular_visa_application_services.administrative_processing_status`
- `consular_visa_application_services.passport_return_status`
- `consular_visa_application_services.refusal_information`

**Nearest canonical collisions.** `government_digital.immigration_case`,
`government_digital.processing_times`,
`government_digital.office_appointment`,
`government_digital.form_filing`, and
`government_digital.fee_calculator` own generic domestic immigration case,
appointment, form, and fee states. `government_digital.passport_apply`,
`government_digital.passport_renew`,
`government_digital.passport_status`, and
`government_digital.passport_records` own passports. V19 is acceptable only
when consular-post, visa category, applicant role, and consular application
state are explicit. Generic immigration and passport requests are rejected.

**Safety/final-action gates.** Form submission, fee payment, appointment booking
or change, and any document transmission stop before final action. The agent
must not choose visa answers, determine eligibility, promise issuance, bypass
official appointments, or treat administrative processing as approval.

Official lifecycle evidence opened 2026-07-30:

- https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application.html
- https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/forms/ds-160-online-nonimmigrant-visa-application/ds-160-faqs.html
- https://travel.state.gov/content/travel/en/us-visas/tourism-visit/visitor.html
- https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/wait-times.html
- https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/fees/fees-visa-services.html
- https://travel.state.gov/content/travel/en/us-visas/visa-information-resources/administrative-processing-information.html
- https://ceac.state.gov/ceacstattracker/status.aspx
- Korean official evidence: https://visa.go.kr/openPage.do?MENU_ID=10105&lang=en
- Korean official evidence: https://overseas.mofa.go.kr/cd-ko/brd/m_10659/view.do?seq=1270153

## Explicitly rejected duplicates and weak candidates

The following gaps were reviewed but are not accepted for V19. The count is
deliberately not padded with alternate names for existing role + asset + state
terminals.

| Rejected candidate | Reason and nearest canonical collision IDs |
| --- | --- |
| Passport application and renewal | Already owned by `government_digital.passport_apply`, `government_digital.passport_renew`, `government_digital.passport_status`, and `government_digital.passport_records`. |
| Broad immigration case navigation | Already owned by `government_digital.immigration_case`, `government_digital.processing_times`, `government_digital.address_change`, `government_digital.case_inquiry`, `government_digital.office_appointment`, `government_digital.form_filing`, and `government_digital.fee_calculator`. Only the narrower consular visa asset survived. |
| Generic government certificates | Already owned by `government.certificate_search`, `government.certificate_issue`, and `government.certificate_wallet`. Only record-specific requester/correction states survived. |
| Generic benefits discovery | Already owned by `government.benefits`; operator eligibility/disbursement is owned by `social_services_casework.eligibility_application_review`, `social_services_casework.benefit_eligibility_decision`, and `social_services_casework.benefit_schedule_disbursement`. Only the applicant's named nutrition case survived. |
| Election administration | Already owned by `election_administration.voter_registration_record`, `election_administration.voter_registration_update`, `election_administration.ballot_style_review`, `election_administration.absentee_request_queue`, `election_administration.absentee_ballot_issue`, and `election_administration.polling_place_open`. Only the citizen-side record/request lifecycle survived. |
| Generic court filing and docket operations | Professional and clerk workflows already belong to `legal_practice_ops.court_filing_prepare`, `legal_practice_ops.court_filing_submit`, `court_clerk_case_admin.case_open`, and `court_clerk_case_admin.filing_docket_entry`. Only a role-gated self-represented-party lifecycle survived. |
| Parcel tracking, hold, reroute, and reschedule | Already owned by `parcel_courier.hold`, `parcel_courier.reroute`, `parcel_courier.reschedule`, and `parcel_courier.missing_claim`. Postal-mail address, hold, forwarding, and mail-theft assets are the narrower surviving boundary. |
| Generic health-insurance eligibility, screening, and refund | Already owned by `health_insurance.eligibility`, `health_insurance.screening`, and `health_insurance.refund`. Only the named public-program application/renewal lifecycle survived. |
| Pension-plan administration | Already owned by `pension_plan_administration.*`, including participant record views and administrator decisions. Only participant-originated elections and requests survived; shared views must hand off. |
| Driver, vehicle, unemployment, and social-insurance services | The citizen-side journeys are already prospective V17 domains. Alternative agency/provider names are not new assets or states. |
| Airline trip, school enrollment, social-platform appeals, device warranty, and home internet | Already researched as V18 domains. Provider-specific aliases would be duplicates, not V19 gaps. |
| Tax filing/refund and general public payment | Existing tax and government-payment terminals already own these states; no new role/asset/state boundary with adequate evidence was found in this pass. |

Rejected duplicate count: **12 candidate families**. Passport and broad
immigration are listed separately because each collides with a different
canonical lifecycle; neither should be reintroduced under a consular label.

## Cross-candidate collision requirements

Before any data implementation, the following pairs need explicit negative
goals and fail-closed routing tests:

- citizen voter registration vs election-administrator registration updates;
- vital-record copy/correction vs generic government certificate issuance;
- nutrition applicant status vs caseworker eligibility decision;
- litigant filing/status vs attorney filing and clerk docket entry;
- jury summons vs civil/criminal case summons;
- postal mail hold/forwarding vs parcel hold/reroute and postal-operator action;
- public health-coverage application vs generic insurance eligibility and
  social-services adjudication;
- participant retirement request vs plan-administrator approval/release;
- consular visa application vs domestic immigration case and passport service;
- `application_status`, `eligibility`, `appointment`, `appeal`, `renewal`, and
  `fee` across all nine domains, because the surface words are not sufficient to
  identify role, asset, or jurisdiction.

An unrestricted alias such as "check my application", "change my address",
"submit an appeal", or "book an appointment" is prohibited. At least one domain
asset cue and one state or jurisdiction cue must be present; otherwise the
resolver must ask a bounded clarification or remain at the hub.

## Independent evaluation gates

The V19 authoring set must be frozen before a separate evaluator creates the
sealed suite. The evaluator must not inspect candidate aliases, goal templates,
source paraphrases, ranking weights, or runtime traces while writing cases.
Provider documentation may be used for truth, but evaluator wording must be
independent.

Minimum sealed suite per accepted domain:

- 20 Korean positive goals and 20 English positive goals, spanning all proposed
  lifecycle states and at least three provider or jurisdiction surfaces;
- 20 nearest-canonical collision goals, including both same-word/different-role
  and same-role/different-asset cases;
- 10 within-V19 collision goals using generic words such as status, application,
  eligibility, appointment, appeal, renewal, payment, and cancellation;
- 10 state-transition or recovery cases, including stale status, already
  completed action, unavailable provider, sign-in boundary, and wrong screen;
- 10 underspecified, unsafe, or out-of-scope cases that must clarify, abstain, or
  remain at the hub;
- at least five jurisdiction/provider-transfer cases where the correct result is
  an official handoff rather than a local terminal.

That is at least 95 sealed cases per domain and **855 cases for nine domains**,
before existing-catalog regression replay. No generated alias or development
goal may be copied into the sealed suite.

Promotion thresholds:

- exact top-1 terminal accuracy >= 95% in each domain and each language;
- top-3 terminal recall >= 99% in each domain and each language;
- correct clarify/abstain/hub behavior >= 98% on underspecified and unsafe cases;
- zero wrong-role operator/adjudicator routing;
- zero automated consequential action and zero action taken after a
  `before_action` stop;
- zero duplicate proposed IDs and zero unrestricted aliases spanning two assets;
- zero incorrect jurisdiction/provider transfer;
- no existing sealed-suite domain loses more than 0.25 percentage points of
  top-1 accuracy, and no existing safety or final-action gate regresses;
- all cited lifecycle URLs remain official, direct, reachable, and semantically
  supportive at promotion time, including at least one Korean source per domain.

Each failure must be classified as ontology gap, role collision, asset
collision, state collision, jurisdiction error, source drift, unsafe action, or
ranking error. A ranking tweak is not an acceptable repair for an ontology,
role, asset, state, or safety failure.

## Promotion checklist

V19 may move from research to implementation only after all of the following are
recorded in a separate change:

1. terminal-level equivalence audit against the then-current physical catalog;
2. final accepted/rejected list and updated count projection;
3. bilingual names and independently authored goals with collision negatives;
4. role, asset, state, provider, and jurisdiction metadata for every terminal;
5. fail-closed hubs and the shared final-action contract;
6. source-verification artifact with access date and lifecycle mapping;
7. sealed-suite manifest and hash produced independently of authoring data;
8. per-domain and per-language evaluation report meeting every threshold above;
9. complete existing-catalog regression report;
10. deterministic materialization and reviewable catalog diff.

Until that checklist passes, this document remains a research note and must not
be imported by runtime or fixture-generation code.
