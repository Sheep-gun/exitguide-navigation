# Navigation coverage gap research — V20

Status: **research-only and noncanonical**. This document is an evidence and
collision-review backlog. It does not add or change runtime domains, functions,
aliases, goals, fixtures, weights, selectors, coordinates, screenshots, or
recorded paths. Nothing here is importable by catalog generation. Promotion
requires a separate reviewed data change, a sealed independent evaluation, and
an explicit catalog-version decision.

Research access date: **2026-07-30**.

## Baseline and prospective count math

The physical comparison baseline remains the canonical V15 fixture at **179
domains / 2,866 functions / 2,660 intents**. V16–V18 are isolated source layers,
and V19 is a research proposal whose implementation may still be in progress.
Therefore, the rows below are projections, not claims about the current runtime.

| Layer | Delta domains | Delta functions | Delta intents | Prospective totals |
| --- | ---: | ---: | ---: | --- |
| Canonical V15 | — | — | — | 179 / 2,866 / 2,660 |
| V16 source layer | +12 | +252 | +240 | 191 / 3,118 / 2,900 |
| V17 source layer | +12 | +240 | +228 | 203 / 3,358 / 3,128 |
| V18 source layer | +12 | +252 | +240 | 215 / 3,610 / 3,368 |
| V19 research, if promoted unchanged | +9 | +123 | +114 | 224 / 3,733 / 3,482 |
| This V20 research set | +8 | +136 | +128 | **232 / 3,869 / 3,610** |

The V20 delta is mechanical: **128 terminal seams + eight fail-closed hubs =
136 functions**, and one intent per terminal seam gives **128 intents**. Terminal
equivalence review may reduce that delta before any implementation.

## Comparison and acceptance method

The collision set is exactly:

- `fixtures/navigation/function-catalog.v1.json` (canonical V15);
- `scripts/navigation_catalog_v16_data.py`;
- `scripts/navigation_catalog_v17_data.py`;
- `scripts/navigation_catalog_v18_data.py`; and
- `docs/NAVIGATION_COVERAGE_GAPS_V19_RESEARCH.md`.

A candidate survived only when its actor role, governed asset, lifecycle state,
provider, and jurisdiction were jointly distinguishable from every nearest
terminal. A different agency name, alternate app, or deeper menu was not enough.
The pass deliberately rejected broad utility assistance and consumer identity
recovery even though both are frequent: existing terminals already own their
central applicant actions.

Each accepted domain has 10–20 proposed terminal seams, at least five direct
official lifecycle sources, an explicit wrong-role or wrong-asset negative
boundary, and a user-owned stopping rule. Source labels below paraphrase observed
official concepts; they are not claims that every provider uses identical UI
text.

No private product telemetry was available. “High-frequency” therefore means a
recurring individual or family self-service journey independently exposed by
multiple official providers or jurisdictions, with several lifecycle states a
first-seen navigation agent must distinguish. It is a research prioritization
signal, not a measured traffic ranking.

## Shared safety and final-action contract

All eight domains require a fail-closed hub when the role, governed asset,
lifecycle state, provider, or jurisdiction is missing. Read-only destinations
may stop after the destination screen is visibly confirmed. Any application,
claim, consent, certification, upload, provider selection, schedule change,
appeal, complaint, payment-method change, or filing must use
`automation_policy=never_auto`, `stop_policy=before_action`, and
`user_owned_final_press=true`.

The agent may explain visible requirements and identify an official handoff, but
must never:

- decide legal, benefit, medical, disability, leave, placement, educational, or
  financial eligibility;
- invent an injury, relationship, diagnosis, limitation, income, work history,
  debt, household fact, child fact, certification, consent, or attestation;
- recommend a bankruptcy chapter, legal strategy, care setting, provider,
  accommodation, placement, service plan, or educational outcome;
- expose a child's, claimant's, debtor's, employee's, or care recipient's record
  without a confirmed authorized role;
- submit, certify, sign, consent, appeal, pay, select, schedule, upload, or press
  the consequential final control; or
- cross from a claimant/family/participant surface into an employer,
  adjuster, caseworker, clerk, trustee, school-administrator, or adjudicator
  surface because labels happen to match.

## Evidence-ready high-frequency gaps

### 1. Workers' compensation claimant services (`workers_compensation_claimant_services`)

**Role, asset, state, provider, jurisdiction.** The role is an injured worker,
survivor/dependent, or expressly authorized claimant representative. The assets
are one statutory workplace-injury claim, accepted conditions, supporting
evidence, treatment authorization, wage-replacement benefit, reimbursement,
return-to-work plan, rehabilitation request, and appeal. States run from injury
notice and claim filing through compensability, treatment, payment, work return,
rehabilitation, dispute, and closure. The provider is the identified federal or
state compensation agency, insurer, self-insured employer, or authorized TPA;
the jurisdiction must be fixed before routing. Federal FECA, a U.S. state system,
and Korean industrial-accident insurance are not interchangeable.

**Prospective terminal seams (15).**

- `workers_compensation_claimant_services.agency_insurer_lookup`
- `workers_compensation_claimant_services.injury_notice_prepare`
- `workers_compensation_claimant_services.claim_form_start`
- `workers_compensation_claimant_services.claim_document_upload`
- `workers_compensation_claimant_services.claim_status`
- `workers_compensation_claimant_services.compensability_decision_review`
- `workers_compensation_claimant_services.medical_provider_lookup`
- `workers_compensation_claimant_services.treatment_authorization_status`
- `workers_compensation_claimant_services.wage_replacement_payment_status`
- `workers_compensation_claimant_services.benefit_payment_method_update`
- `workers_compensation_claimant_services.independent_medical_exam_status`
- `workers_compensation_claimant_services.return_to_work_plan_review`
- `workers_compensation_claimant_services.vocational_rehabilitation_request`
- `workers_compensation_claimant_services.mileage_expense_reimbursement`
- `workers_compensation_claimant_services.claim_dispute_appeal`

**Nearest existing collisions and negative boundary.** Generic policyholder
claims remain `insurance.claim.entry`, `insurance.claim.documents`,
`insurance.claim.status`, and `insurance.accident.report`. Adjuster-owned queues
and decisions remain `insurance_claims_adjuster_ops.claim_queue`,
`insurance_claims_adjuster_ops.coverage_decision`,
`insurance_claims_adjuster_ops.payment_check_issue`, and
`insurance_claims_adjuster_ops.settlement_offer`. Employer/regulator safety
records remain `occupational_safety_case_ops.incident_reporting_queue`,
`occupational_safety_case_ops.injury_illness_case_record`, and
`occupational_safety_case_ops.severe_injury_report_submit`. “Issue the claimant's
check” is an adjuster negative; “submit my state workers' compensation claim” is
the accepted claimant boundary.

**Safe stop.** Fail closed to
`workers_compensation_claimant_services.hub`. Injury notice, claim, evidence,
payment-method, rehabilitation,
reimbursement, and appeal actions stop before the final press. The agent must not
classify an injury as compensable, choose a doctor, state an impairment rating,
accept a settlement, or infer work restrictions.

Official lifecycle evidence verified 2026-07-30:

- Federal claim and case lifecycle: https://www.dol.gov/agencies/owcp/feca
- Claimant contacts, dashboard, documents, bills, and authorization status: https://www.dol.gov/agencies/owcp/feca/contacts/fecacont
- Injured-worker treatment, accepted conditions, bills, and reimbursement: https://www.dol.gov/agencies/owcp/FECA/regs/compliance/infoinjuredwrkers
- New-claim, compensation, return-to-work, medical, and appeal lifecycle: https://www.dol.gov/agencies/owcp/FECA/regs/compliance/Basic-Information-on-New-Claims?lang=en
- California injured-worker claim lifecycle: https://www.dir.ca.gov/dwc/InjuredWorker.htm
- California claimant, review, and appeal forms: https://www.dir.ca.gov/dwc/forms.html
- Korean regulated-provider claim, benefit, rehabilitation, and review evidence: https://webzine.comwel.or.kr/vol115/sub02.html

### 2. Paid family and medical leave claimant services (`paid_family_medical_leave_claimant_services`)

**Role, asset, state, provider, jurisdiction.** The role is a worker claiming
wage-replacement benefits for their own medical leave, family caregiving,
bonding, or another covered reason, or an authorized claimant representative.
The governed asset is a named public paid-leave claim, supporting certification,
approved leave period, weekly claim, benefit payment, change report, or appeal.
States run from program/leave-reason review through application, certification,
decision, weekly claiming, payment, leave-period change, return, and appeal. The
provider is a named state fund or approved private-plan administrator. The
program's state/country, claim year, employer coverage, and private-plan branch
must be explicit.

**Prospective terminal seams (15).**

- `paid_family_medical_leave_claimant_services.program_coverage_review`
- `paid_family_medical_leave_claimant_services.qualifying_leave_reason_review`
- `paid_family_medical_leave_claimant_services.employer_notice_prepare`
- `paid_family_medical_leave_claimant_services.benefit_claim_start`
- `paid_family_medical_leave_claimant_services.identity_verification`
- `paid_family_medical_leave_claimant_services.wage_employment_record_review`
- `paid_family_medical_leave_claimant_services.supporting_certification_upload`
- `paid_family_medical_leave_claimant_services.claim_status`
- `paid_family_medical_leave_claimant_services.eligibility_decision_review`
- `paid_family_medical_leave_claimant_services.weekly_claim_certification`
- `paid_family_medical_leave_claimant_services.benefit_payment_status`
- `paid_family_medical_leave_claimant_services.intermittent_leave_schedule`
- `paid_family_medical_leave_claimant_services.leave_period_change_report`
- `paid_family_medical_leave_claimant_services.return_to_work_date_update`
- `paid_family_medical_leave_claimant_services.determination_appeal_request`

**Nearest existing collisions and negative boundary.** Routine employer time
off remains `hr_payroll.leave_request` and `hr_payroll.leave_balance`.
Unemployment remains `unemployment_insurance_case_services.initial_claim_start`,
`unemployment_insurance_case_services.weekly_certification_submit`, and
`unemployment_insurance_case_services.payment_status`. A private disability
policy claim remains `insurance.claim.entry`. “Request two PTO days from my
manager” is an HR negative; “file this week's approved state PFML benefit claim”
is the accepted wage-replacement boundary. Employer-side protected-leave and
accommodation records are separately role-gated in candidate 5.

**Safe stop.** Fail closed to
`paid_family_medical_leave_claimant_services.hub`. Employer notice, benefit
application, certification upload,
weekly certification, change report, return-date change, and appeal all stop
before submission. The agent must not choose a leave reason, attest inability to
work, calculate entitlement as a decision, or conflate paid benefits with job
protection.

Official lifecycle evidence verified 2026-07-30:

- California PFL claim process, evidence, decision, and appeal: https://edd.ca.gov/en/disability/pfl_claim_process/
- California claim status, documents, and payment history: https://edd.ca.gov/en/disability/SDI_Self_Service_Options/
- California continuation, stopping, extension, and change forms: https://edd.ca.gov/en/disability/Discontinue_Continue_or_Extend_Your_PFL_Benefits/
- Washington weekly claim and payment lifecycle: https://paidleave.wa.gov/file-your-weekly-claim/
- Washington individual/family forms and claim management: https://paidleave.wa.gov/help-center/individuals-and-families/
- Massachusetts employee application and case-management hub: https://www.mass.gov/paid-family-and-medical-leave-benefits-for-employees
- Massachusetts benefits, schedules, application, payments, changes, and appeals: https://www.mass.gov/info-details/paid-family-and-medical-leave-pfml-overview-and-benefits
- Korean official app evidence for parental/maternity leave benefit applications: https://www.work24.go.kr/cm/main.do

### 3. Foster and adoption family services (`foster_adoption_family_services`)

**Role, asset, state, provider, jurisdiction.** The role is a prospective or
approved foster/resource/adoptive parent, kin caregiver, current placement
caregiver, or authorized adult family representative. The assets are that
family's orientation, application, background-check task, training, home study,
approval, authorized matching/placement record, caregiver maintenance payment,
adoption-assistance request, post-placement report, finalization status, and
post-adoption support. States run from inquiry through approval, matching,
placement, permanency/finalization, and post-placement support. The provider is
the named public child-welfare agency or its authorized placement/adoption
provider, under one state/national and interstate-placement jurisdiction.

**Prospective terminal seams (17).**

- `foster_adoption_family_services.agency_provider_lookup`
- `foster_adoption_family_services.orientation_registration`
- `foster_adoption_family_services.family_application_start`
- `foster_adoption_family_services.background_check_status`
- `foster_adoption_family_services.home_study_document_upload`
- `foster_adoption_family_services.home_study_status`
- `foster_adoption_family_services.training_requirement_status`
- `foster_adoption_family_services.caregiver_approval_status`
- `foster_adoption_family_services.child_match_profile_review`
- `foster_adoption_family_services.match_inquiry_submit`
- `foster_adoption_family_services.placement_transition_plan`
- `foster_adoption_family_services.placement_status`
- `foster_adoption_family_services.caregiver_maintenance_payment_status`
- `foster_adoption_family_services.adoption_assistance_application`
- `foster_adoption_family_services.post_placement_report_submit`
- `foster_adoption_family_services.adoption_finalization_status`
- `foster_adoption_family_services.post_adoption_support_request`

**Nearest existing collisions and negative boundary.** Caseworker intake,
assessment, home-visit planning, care-plan mutation, eligibility decisions, and
disbursement remain `social_services_casework.referral_intake`,
`social_services_casework.home_visit_plan`,
`social_services_casework.care_plan_create_update`,
`social_services_casework.benefit_eligibility_decision`, and
`social_services_casework.benefit_schedule_disbursement`. Informal family
coordination remains `family_caregiving.care_recipient_switch`,
`family_caregiving.invite_caregiver`, and
`family_caregiving.care_task_create_assign`. “Approve this home and assign a
child” is a caseworker negative; “check my resource-family application and home
study status” is the accepted family boundary.

**Safe stop.** Fail closed to `foster_adoption_family_services.hub`.
Application, orientation booking, evidence, match inquiry,
placement acceptance, assistance request, report, and support request stop before
submission. The agent must not expose an unauthorized child profile, score a
family, recommend a match, decide best interests, approve a home, or accept a
placement.

Official lifecycle evidence verified 2026-07-30:

- California unified resource-family approval lifecycle: https://www.cdss.ca.gov/inforesources/resource-family-approval-program
- California resource-family application and approval forms: https://www.cdss.ca.gov/inforesources/forms-brochures/forms-alphabetic-list/i-l
- California prospective caregiver and payment FAQs: https://www.cdss.ca.gov/inforesources/foster-care/foster-care-and-adoptive-resource/frequently-asked-questions
- California foster/adoptive family services and assistance: https://www.cdss.ca.gov/benefits-services/foster-parents-and-youth
- California foster-care, licensing, placement, and permanency overview: https://www.cdss.ca.gov/inforesources/foster-care/resource-family-approval-program
- California interstate-placement family status boundary: https://www.cdss.ca.gov/inforesources/cdss-programs/foster-care/interstate-compact-on-the-placement-of-children-icpc/icpc-information
- Korean public-provider adoption education and application lifecycle: https://jarip.ncrc.or.kr/ncrc/cm/cntnts/cntntsView.do?cntntsId=1344&mi=1281
- Korean Ministry of Health and Welfare adoption, home-study, matching, and court lifecycle: https://www.mohw.go.kr/menu.es?mid=a10711030500

### 4. Consumer bankruptcy case services (`consumer_bankruptcy_case_services`)

**Role, asset, state, provider, jurisdiction.** The role is an individual debtor
acting pro se, a joint debtor, or an authorized representative viewing the
debtor's own case. The assets are a pre-filing counseling certificate, means-test
inputs, individual petition packet, filing fee request, case/docket, trustee
assignment, creditor meeting, claims register, debtor-education certificate,
amendment, reaffirmation agreement, discharge, and closure. States run from
information and counseling through filing, administration, education,
discharge, and closure. The provider is the identified bankruptcy court and
official trustee/counseling system; court district, country, chapter already
chosen by the user, and case number must be explicit where applicable.

**Prospective terminal seams (17).**

- `consumer_bankruptcy_case_services.court_jurisdiction_lookup`
- `consumer_bankruptcy_case_services.bankruptcy_chapter_information`
- `consumer_bankruptcy_case_services.approved_credit_counseling_lookup`
- `consumer_bankruptcy_case_services.means_test_form_review`
- `consumer_bankruptcy_case_services.petition_form_packet`
- `consumer_bankruptcy_case_services.petition_document_upload`
- `consumer_bankruptcy_case_services.petition_submit`
- `consumer_bankruptcy_case_services.filing_fee_option_request`
- `consumer_bankruptcy_case_services.case_number_docket_view`
- `consumer_bankruptcy_case_services.trustee_assignment_view`
- `consumer_bankruptcy_case_services.creditor_meeting_schedule`
- `consumer_bankruptcy_case_services.claims_register_view`
- `consumer_bankruptcy_case_services.debtor_education_certificate_upload`
- `consumer_bankruptcy_case_services.amendment_prepare`
- `consumer_bankruptcy_case_services.reaffirmation_agreement_review`
- `consumer_bankruptcy_case_services.discharge_status`
- `consumer_bankruptcy_case_services.case_closure_status`

**Nearest existing collisions and negative boundary.** Collection-notice and
collector-response states remain
`consumer_debt_collection_services.validation_notice`,
`consumer_debt_collection_services.dispute_submission`,
`consumer_debt_collection_services.payment_plan_offer`,
`consumer_debt_collection_services.lawsuit_notice`, and
`consumer_debt_collection_services.legal_help_handoff`. Generic pro-se civil
filing remains `court_litigant_self_service.filing_prepare`,
`court_litigant_self_service.filing_submit`,
`court_litigant_self_service.case_docket_view`, and
`court_litigant_self_service.fee_waiver_request`. Clerk and attorney work remains
`court_clerk_case_admin.case_open`,
`court_clerk_case_admin.filing_docket_entry`, and
`legal_practice_ops.court_filing_prepare`. “Dispute the collector's validation
notice” is a debt-response negative; “upload my debtor-education certificate in
this bankruptcy case” is the accepted bankruptcy asset.

**Safe stop.** Fail closed to `consumer_bankruptcy_case_services.hub`.
Petition, document, fee-option, certificate, and amendment actions
stop before the final press. The agent must not recommend whether or when to file,
select a chapter, complete factual schedules, omit property or creditors,
interpret dischargeability, sign, or provide legal advice.

Official lifecycle evidence verified 2026-07-30:

- U.S. Bankruptcy Basics lifecycle: https://www.uscourts.gov/court-programs/bankruptcy/bankruptcy-basics
- U.S. pro-se filing boundary and forms: https://www.uscourts.gov/court-programs/bankruptcy/filing-without-attorney
- U.S. discharge and debtor-education lifecycle: https://www.uscourts.gov/court-programs/bankruptcy/bankruptcy-basics/discharge-bankruptcy-bankruptcy-basics
- U.S. bankruptcy filing and amendment fee schedule: https://www.uscourts.gov/court-programs/fees/bankruptcy-court-miscellaneous-fee-schedule
- U.S. Trustee consumer portal for counseling, means test, trustee, and 341 meeting: https://www.justice.gov/ust/consumer-information
- U.S. approved counseling and debtor-education providers: https://www.justice.gov/ust/credit-counseling-and-debtor-education-providers
- Korean court personal-bankruptcy and discharge application lifecycle: https://www.scourt.go.kr/nm/min_2/min_2_1/min_2_1_5/index.html
- Korean court individual-rehabilitation jurisdiction and document lifecycle: https://www.scourt.go.kr/nm/min_2/min_2_2/min_2_2_1/index.html

### 5. Workplace protected-leave and accommodation services (`workplace_leave_accommodation_services`)

**Role, asset, state, provider, jurisdiction.** The role is an employee or job
applicant requesting or managing their own statutory protected-leave or
disability-accommodation case, or an expressly authorized representative. The
assets are the employer-facing leave request, eligibility/rights/designation
notices, medical certification, intermittent schedule, recertification,
accommodation request, interactive-process record, implementation record, and
return-to-work release. States run from notice/request through certification,
designation, leave or interactive process, implementation, recertification, and
return. The provider is the identified employer or authorized leave/accommodation
administrator under a named employment jurisdiction. Federal FMLA/ADA, state
law, an employer policy, and Korean disability-employment support must not be
silently merged.

**Prospective terminal seams (16).**

- `workplace_leave_accommodation_services.protected_leave_coverage_review`
- `workplace_leave_accommodation_services.protected_leave_request_start`
- `workplace_leave_accommodation_services.eligibility_notice_review`
- `workplace_leave_accommodation_services.rights_responsibilities_notice_review`
- `workplace_leave_accommodation_services.medical_certification_request`
- `workplace_leave_accommodation_services.medical_certification_upload`
- `workplace_leave_accommodation_services.leave_designation_notice_review`
- `workplace_leave_accommodation_services.protected_leave_case_status`
- `workplace_leave_accommodation_services.intermittent_leave_schedule_review`
- `workplace_leave_accommodation_services.recertification_request_review`
- `workplace_leave_accommodation_services.accommodation_request_start`
- `workplace_leave_accommodation_services.accommodation_document_upload`
- `workplace_leave_accommodation_services.interactive_process_status`
- `workplace_leave_accommodation_services.accommodation_decision_review`
- `workplace_leave_accommodation_services.accommodation_implementation_review`
- `workplace_leave_accommodation_services.return_to_work_release_upload`

**Nearest existing collisions and negative boundary.** Ordinary PTO and sick
leave remain `hr_payroll.leave_request`, `hr_payroll.leave_balance`, and
`hr_payroll.manager_approvals`. Enforcement complaints and investigator findings
remain `wage_hour_enforcement_ops.worker_complaint_prepare`,
`wage_hour_enforcement_ops.worker_complaint_submit`, and
`wage_hour_enforcement_ops.fmla_finding_record`. Housing accommodation remains
`public_housing_assistance_services.reasonable_accommodation_request`, and jury
accommodation remains `jury_summons_response_services.accommodation_request`.
“Approve my direct report's PTO” is an HR/manager negative; “upload the medical
certification requested for my protected-leave case” is the accepted employee
case. A state paid-leave benefit claim belongs to candidate 2, not this employer
job-protection asset.

**Safe stop.** Fail closed to `workplace_leave_accommodation_services.hub`.
Leave/accommodation request, certification, document, and
return-release actions stop before upload or submission. The agent must not infer
a disability, disclose more medical information than the visible form requires,
decide coverage or undue hardship, select an accommodation, approve leave, or
file an enforcement complaint under this domain.

Official lifecycle evidence verified 2026-07-30:

- U.S. FMLA employee and employer lifecycle hub: https://www.dol.gov/agencies/whd/fmla
- U.S. notice, certification, designation, leave, and return sequence: https://www.dol.gov/agencies/whd/fmla/FMLA-leave-process
- U.S. employee certification and employer notice forms: https://www.dol.gov/agencies/whd/fmla/forms
- U.S. employee notice, certification, and return rights: https://www.dol.gov/agencies/whd/fmla/how-to-talk-to-your-employer-about-leave
- U.S. ADA request and interactive-process guidance: https://www.eeoc.gov/laws/guidance/enforcement-guidance-reasonable-accommodation-and-undue-hardship-under-ada
- U.S. employer-provided leave as accommodation boundary: https://www.eeoc.gov/laws/guidance/employer-provided-leave-and-americans-disabilities-act
- Korean regulated-provider application menu for work-support and assistive technology: https://www.esingo.or.kr/
- Korean public-provider application and decision-time lifecycle: https://www.kead.or.kr/customerCharter3/cntntsPage.do?menuId=MENU0191

### 6. Long-term services and supports case services (`long_term_services_supports_case_services`)

**Role, asset, state, provider, jurisdiction.** The role is an older adult or
person with a disability seeking their own LTSS/HCBS, an enrolled participant,
family/legal representative, or authorized caregiver acting on that case. The
assets are one LTSS application, functional/level-of-care assessment, waiver
waitlist record, eligibility notice, person-centered service plan, provider
choice, service authorization/schedule, changed-need report, reassessment, and
hearing. States run from pathway discovery through application, assessment,
waitlist/eligibility, planning, authorized service delivery, reassessment, and
appeal. The provider is the named Medicaid/state LTSS agency, managed LTSS plan,
or Korean National Health Insurance long-term-care system. Program authority,
residence, waiver/population, and institutional-versus-community branch must be
explicit.

**Prospective terminal seams (16).**

- `long_term_services_supports_case_services.program_pathway_review`
- `long_term_services_supports_case_services.administering_agency_lookup`
- `long_term_services_supports_case_services.application_start`
- `long_term_services_supports_case_services.application_status`
- `long_term_services_supports_case_services.functional_assessment_schedule`
- `long_term_services_supports_case_services.assessment_result_review`
- `long_term_services_supports_case_services.waiver_waitlist_status`
- `long_term_services_supports_case_services.eligibility_notice_review`
- `long_term_services_supports_case_services.person_centered_service_plan_review`
- `long_term_services_supports_case_services.service_provider_compare`
- `long_term_services_supports_case_services.provider_selection_submit`
- `long_term_services_supports_case_services.service_authorization_status`
- `long_term_services_supports_case_services.authorized_service_schedule`
- `long_term_services_supports_case_services.change_in_need_report`
- `long_term_services_supports_case_services.renewal_reassessment`
- `long_term_services_supports_case_services.fair_hearing_request`

**Nearest existing collisions and negative boundary.** Cash disability benefits
remain `social_security_benefit_services.disability_application_start`,
`social_security_benefit_services.application_status`, and
`social_security_benefit_services.continuing_disability_review`. General public
health coverage remains `public_health_coverage_case_services.application_start`,
`public_health_coverage_case_services.managed_plan_select`, and
`public_health_coverage_case_services.renewal_submit`. Informal coordination
remains `family_caregiving.care_calendar` and
`family_caregiving.care_task_create_assign`; caseworker-authored plans remain
`social_services_casework.care_plan_create_update`. “Apply for Social Security
cash disability” is a benefit negative; “check my HCBS functional-assessment and
waiver waitlist status” is the accepted LTSS case.

**Safe stop.** Fail closed to `long_term_services_supports_case_services.hub`.
Application, assessment scheduling, provider choice,
changed-need report, reassessment, and hearing request stop before final action.
The agent must not determine level of care, recommend institutionalization or a
provider, write a service plan, change an authorized budget, or attest functional
limitations.

Official lifecycle evidence verified 2026-07-30:

- Medicaid HCBS program and population boundary: https://www.medicaid.gov/medicaid/home-community-based-services
- Medicaid HCBS authorities and jurisdiction branches: https://www.medicaid.gov/medicaid/home-community-based-services/home-community-based-services-authorities
- Medicaid assessment, plan, budget, and participant choice: https://www.medicaid.gov/medicaid/long-term-services-supports/self-directed-services
- Managed LTSS assessment and person-centered-plan states: https://www.medicaid.gov/medicaid/managed-care/managed-long-term-services-and-supports
- HCBS waitlist, grievance, and service-timeliness requirements: https://www.medicaid.gov/medicaid/access-care/home-and-community-based-services-provisions
- Institutional preadmission assessment and setting decision boundary: https://www.medicaid.gov/medicaid/long-term-services-supports/institutional-long-term-care/preadmission-screening-and-resident-review
- Korean NHIS application, assessment, grade, notice, and use-support flow: https://www.nhis.or.kr/announce/wbhaec11100m01.do
- Korean regulated-provider long-term-care application and service portal: https://www.longtermcare.or.kr/npbs/indexr.jsp

### 7. Child-care assistance case services (`child_care_assistance_case_services`)

**Role, asset, state, provider, jurisdiction.** The role is a parent, guardian,
or authorized household representative applying for or managing a named public
child-care subsidy. The assets are the household application, identity/income
evidence, child/household facts, funding waitlist, eligibility notice,
authorization/certificate, authorized provider and care schedule, copayment,
recertification, change report, and appeal. States run from program discovery
through application, verification/waitlist, offer/authorization, provider
selection, active assistance, recertification, change, and appeal. The provider
is the named state/territory/tribal lead agency or Korean welfare/child-care
portal; residence, funding program, child, service period, and authorized
provider branch must be explicit.

**Prospective terminal seams (16).**

- `child_care_assistance_case_services.program_eligibility_review`
- `child_care_assistance_case_services.administering_agency_lookup`
- `child_care_assistance_case_services.application_start`
- `child_care_assistance_case_services.application_status`
- `child_care_assistance_case_services.identity_income_document_upload`
- `child_care_assistance_case_services.child_household_change_report`
- `child_care_assistance_case_services.provider_search`
- `child_care_assistance_case_services.provider_selection_submit`
- `child_care_assistance_case_services.eligibility_notice_review`
- `child_care_assistance_case_services.authorization_certificate_status`
- `child_care_assistance_case_services.copayment_review`
- `child_care_assistance_case_services.authorized_care_schedule_review`
- `child_care_assistance_case_services.funding_waitlist_status`
- `child_care_assistance_case_services.recertification_due`
- `child_care_assistance_case_services.recertification_submit`
- `child_care_assistance_case_services.benefit_change_appeal`

**Nearest existing collisions and negative boundary.** Day-care operations and
ordinary family-provider records remain `childcare_family_portal.billing_balance`,
`childcare_family_portal.attendance_history`,
`childcare_family_portal.child_checkin`, and
`childcare_family_portal.provider_messages`. School registration remains
`school_family_enrollment.registration_submission` and
`school_family_enrollment.placement_waitlist_status`. Nutrition benefits remain
`nutrition_assistance_case_services.application_start` and
`nutrition_assistance_case_services.recertification`; worker adjudication remains
`social_services_casework.eligibility_application_review` and
`social_services_casework.benefit_eligibility_decision`. “Check my daycare
invoice” is a provider-portal negative; “see whether my child-care subsidy is on
the funding waitlist” is the accepted assistance asset.

**Safe stop.** Fail closed to `child_care_assistance_case_services.hub`.
Application, evidence, household change, provider selection,
recertification, and appeal stop before submission. The agent must not infer
income, custody, work/school participation, eligibility, priority status,
provider suitability, authorized hours, or an appeal position.

Official lifecycle evidence verified 2026-07-30:

- Federal family child-care assistance entrypoint: https://www.childcare.gov/consumer-education/get-help-paying-for-child-care
- Federal subsidy/voucher and state-program boundary: https://www.childcare.gov/consumer-education/get-help-paying-for-child-care/child-care-financial-assistance-options
- Official state and territory resource transfer: https://www.childcare.gov/state-resources
- Massachusetts family assistance application and management hub: https://www.mass.gov/child-care-financial-assistance
- Massachusetts family portal application, progress, and case management: https://www.mass.gov/news/healey-driscoll-administration-launches-new-family-portal-to-help-parents-caregivers-pay-for-child-care
- Massachusetts portal, waitlist, provider offer, and policy transition: https://www.mass.gov/info-details/hub-for-child-care-financial-assistance-programs-changes
- Massachusetts evidence, application statuses, waitlist, and priority policy: https://www.mass.gov/doc/eec-ccfa-2026-04-income-eligible-consolidated-policies-may-6-2026/download
- Korean official online child-care-benefit application and final-submit boundary: https://m.bokjiro.go.kr/ssis-tem/cms/mob/customer/notice/1309244_1155.html

### 8. Special-education family services (`special_education_family_services`)

**Role, asset, state, provider, jurisdiction.** The role is the student (where
rights have transferred), parent, guardian, surrogate parent, or authorized
family representative. The assets are a child-find/referral request, evaluation
request and consent, evaluation/eligibility record, IEP meeting and parent
materials, current IEP, progress report, reevaluation, transition plan, prior
written notice, mediation request, and complaint/due-process handoff. States run
from concern/referral through evaluation, eligibility, IEP participation,
services/progress, reevaluation/transition, notice, and dispute resolution. The
provider is the identified school district/LEA, state education agency, or Korean
education support center; school year, student, governing law, and transferred-
rights status must be explicit.

**Prospective terminal seams (16).**

- `special_education_family_services.child_find_referral_information`
- `special_education_family_services.evaluation_request_prepare`
- `special_education_family_services.evaluation_consent_review`
- `special_education_family_services.evaluation_consent_submit`
- `special_education_family_services.evaluation_status`
- `special_education_family_services.eligibility_determination_review`
- `special_education_family_services.iep_meeting_schedule_review`
- `special_education_family_services.iep_meeting_document_upload`
- `special_education_family_services.current_iep_download`
- `special_education_family_services.parent_input_submit`
- `special_education_family_services.service_progress_report`
- `special_education_family_services.reevaluation_due`
- `special_education_family_services.transition_plan_review`
- `special_education_family_services.prior_written_notice_review`
- `special_education_family_services.mediation_request`
- `special_education_family_services.state_complaint_due_process_handoff`

**Nearest existing collisions and negative boundary.** Administrator-owned
records/actions remain `special_education_program_admin.referral_intake`,
`special_education_program_admin.evaluation_consent_request`,
`special_education_program_admin.evaluation_assessment_status`,
`special_education_program_admin.eligibility_determination_record`,
`special_education_program_admin.iep_current_version`,
`special_education_program_admin.iep_meeting_schedule`,
`special_education_program_admin.iep_draft_update`,
`special_education_program_admin.iep_implementation_authorize`,
`special_education_program_admin.progress_report_issue`,
`special_education_program_admin.procedural_safeguards_notice_issue`, and
`special_education_program_admin.transition_plan_approve`. General school
registration and records remain `school_family_enrollment.registration_submission`
and `school_family_enrollment.student_record_request`. “Finalize and authorize
this student's IEP” is an administrator negative; “review and submit my informed
parental consent for this evaluation” is the accepted family boundary. Shared
read states require explicit equivalence/handoff review rather than unrestricted
duplicate aliases.

**Safe stop.** Fail closed to `special_education_family_services.hub`.
Evaluation request/consent, parent input, document upload,
mediation, and complaint handoff stop before the final action. The agent must not
diagnose, determine eligibility or placement, consent for a parent, draft or
approve an IEP, waive safeguards, or choose a dispute strategy.

Official lifecycle evidence verified 2026-07-30:

- IDEA parent records, meeting participation, and procedural safeguards: https://sites.ed.gov/idea/statute-chapter-33/subchapter-ii/1415
- IDEA informed parental consent lifecycle: https://sites.ed.gov/idea/regs/b/d/300.300
- IDEA IEP meeting and parent participation requirements: https://sites.ed.gov/idea/regs/b/d/300.322
- IDEA safeguards notice, records, mediation, and complaints: https://sites.ed.gov/idea/regs/b/e/300.504
- IDEA prior notice, mediation, complaint, hearing, and appeal index: https://sites.ed.gov/idea/regs/b/e
- IDEA evaluation notice, parent input, report, and eligibility record: https://sites.ed.gov/idea/statute-chapter-33/subchapter-ii/1414/b
- Korean education-office referral, consent, diagnostic evaluation, and placement flow: https://www.goeyi.kr/goeyi/cm/cntnts/cntntsView.do?cntntsId=3619&mi=23654
- Korean national institute evidence for IEP, progress reporting, and parent participation: https://www.nise.go.kr/jsp/field/2008-3/04-2.jsp

## Explicitly rejected duplicates

The audit rejected **16 candidate families**. Rejection means the named broad
journey must route to the existing owner; it does not preclude later evidence for
a genuinely different role, asset, or state.

| Rejected candidate family | Exact collision and negative-example boundary |
| --- | --- |
| Consumer identity recovery | Rejected because V17 already owns the consumer's report, block, freeze, and alert states in `consumer_credit_reporting_services.identity_theft_report_start`, `consumer_credit_reporting_services.identity_theft_block_request`, `consumer_credit_reporting_services.security_freeze_place`, `consumer_credit_reporting_services.security_freeze_lift`, `consumer_credit_reporting_services.fraud_alert_place`, and `consumer_credit_reporting_services.fraud_alert_remove`. A broader “recovery plan” label would duplicate those actions. |
| Public utility/energy assistance | Rejected because `utilities.payment_assistance` already expressly owns eligibility, application, bill discount, energy voucher, and payment-extension cues for the household utility account. Deeper LIHEAP or provider aliases do not create a new role + asset + state. |
| Passport application, renewal, status, and records | Already owned by `government_digital.passport_apply`, `government_digital.passport_renew`, `government_digital.passport_status`, and `government_digital.passport_records`. |
| Broad immigration or another consular-visa domain | Domestic cases already belong to `government_digital.immigration_case`, `government_digital.processing_times`, `government_digital.address_change`, `government_digital.case_inquiry`, `government_digital.office_appointment`, `government_digital.form_filing`, and `government_digital.fee_calculator`; V19 already proposes `consular_visa_application_services.application_status` and `consular_visa_application_services.interview_schedule`. |
| General tax filing, payment, refund, and documents | Already owned by `tax.return`, `tax.payment`, `tax.refund_status`, and `tax.documents`. Bankruptcy-tax consequences are an advice boundary, not a new tax terminal. |
| General insurance claim | Already owned by `insurance.claim.entry`, `insurance.claim.documents`, and `insurance.claim.status`; adjuster decisions belong to `insurance_claims_adjuster_ops.coverage_decision`. Only the named statutory workers' compensation claimant case survived. |
| General HR leave/PTO | Already owned by `hr_payroll.leave_request`, `hr_payroll.leave_balance`, and `hr_payroll.manager_approvals`. Only a role-gated statutory protected-leave/accommodation case survived. |
| General social-services or benefits case | Discovery is owned by `government.benefits`; worker-side review and decision are owned by `social_services_casework.eligibility_application_review`, `social_services_casework.benefit_eligibility_decision`, and `social_services_casework.benefit_schedule_disbursement`. Named family/participant assets are required. |
| Generic disability cash benefit | Already owned by `social_security_benefit_services.disability_application_start`, `social_security_benefit_services.application_status`, and `social_security_benefit_services.continuing_disability_review`. LTSS service assessment is the narrower surviving asset. |
| General public health-coverage application or renewal | V19 already proposes `public_health_coverage_case_services.application_start`, `public_health_coverage_case_services.application_status`, and `public_health_coverage_case_services.renewal_submit`; broad insurance views remain `health_insurance.eligibility` and `health_insurance.screening`. |
| Ordinary collector notice, dispute, or payment plan | V18 already owns `consumer_debt_collection_services.validation_notice`, `consumer_debt_collection_services.dispute_submission`, and `consumer_debt_collection_services.payment_plan_offer`. Only the court-administered bankruptcy case survived. |
| Generic self-represented court filing/docket | V19 already proposes `court_litigant_self_service.filing_prepare`, `court_litigant_self_service.filing_submit`, and `court_litigant_self_service.case_docket_view`; clerk work remains `court_clerk_case_admin.filing_docket_entry`. |
| Child-care provider portal, billing, attendance, or check-in | Already owned by `childcare_family_portal.billing_balance`, `childcare_family_portal.attendance_history`, and `childcare_family_portal.child_checkin`. Only the named public subsidy case survived. |
| Foster/adoption caseworker assessment or placement decision | Already owned by `social_services_casework.dynamic_needs_assessment`, `social_services_casework.home_visit_plan`, and `social_services_casework.care_plan_create_update`. Candidate 3 is family-facing and cannot approve or assign. |
| Informal long-term family-care coordination | Already owned by `family_caregiving.care_calendar`, `family_caregiving.care_task_create_assign`, and `family_caregiving.medication_schedule_edit`. Candidate 6 requires a named statutory LTSS authorization. |
| Special-education program administration | Already owned by `special_education_program_admin.evaluation_plan_finalize`, `special_education_program_admin.iep_draft_update`, `special_education_program_admin.iep_implementation_authorize`, and `special_education_program_admin.placement_decision_record`. Candidate 8 adds only the parent/student side and requires equivalence review for shared reads. |

## Cross-candidate collision requirements

Before authoring any data, a sealed negative set must distinguish:

- workers' compensation wage replacement vs paid-family/medical-leave benefits,
  unemployment weekly certification, employer protected leave, private
  disability insurance, and OSHA/employer incident reporting;
- paid-leave public benefit claim vs employer job-protection/accommodation case
  and routine PTO;
- foster/adoptive family application, home study, and placement status vs
  caseworker assessment/decision and informal family caregiving;
- debtor bankruptcy filing/education/discharge vs collector response, ordinary
  civil filing, attorney preparation, and clerk docket entry;
- protected-leave certification vs accommodation documentation, state benefit
  certification, enforcement complaint, housing accommodation, and jury
  accommodation;
- LTSS functional assessment/service authorization vs Social Security cash
  disability, public health coverage, informal caregiving, and operator-authored
  care plans;
- child-care subsidy waitlist/authorization vs provider billing/check-in, school
  enrollment, nutrition assistance, and caseworker eligibility decision; and
- parent evaluation consent/IEP participation vs school-administrator plan
  finalization and ordinary student registration/record requests.

The words `application`, `claim`, `status`, `evidence`, `certification`,
`eligibility`, `assessment`, `provider`, `schedule`, `payment`, `renewal`,
`consent`, `notice`, and `appeal` are never sufficient aliases by themselves.
At least one role cue, one governed-asset cue, and one provider/jurisdiction or
lifecycle-state cue must be present; otherwise routing must clarify or remain at
the fail-closed hub.

## Evidence, language, and structural audit

### Source inventory

The accepted set contains **63 unique direct HTTPS official lifecycle URLs**:
seven for workers' compensation and eight for each other domain. They span **24
exact hosts**:

`www.dol.gov`, `www.dir.ca.gov`, `webzine.comwel.or.kr`, `edd.ca.gov`,
`paidleave.wa.gov`, `www.mass.gov`, `www.work24.go.kr`, `www.cdss.ca.gov`,
`jarip.ncrc.or.kr`, `www.mohw.go.kr`, `www.uscourts.gov`, `www.justice.gov`,
`www.scourt.go.kr`, `www.eeoc.gov`, `www.esingo.or.kr`, `www.kead.or.kr`,
`www.medicaid.gov`, `www.nhis.or.kr`, `www.longtermcare.or.kr`,
`www.childcare.gov`, `m.bokjiro.go.kr`, `sites.ed.gov`, `www.goeyi.kr`, and
`www.nise.go.kr`.

Search-result URLs, blogs, commercial explainers, and invented UI labels were not
used as evidence. Some sources are first-party public portals or public/regulated
providers rather than policy pages; that is intentional because first-seen app
navigation needs both lifecycle truth and observed service-menu evidence. Every
source must be reopened at promotion time; research verification is not a
permanent reachability guarantee.

### Korean and bilingual coverage

Korean official or regulated-provider lifecycle evidence exists for **8/8
accepted domains**:

| Domain | Korean evidence boundary |
| --- | --- |
| `workers_compensation_claimant_services` | COMWEL industrial-accident claim, benefits, rehabilitation, and review |
| `paid_family_medical_leave_claimant_services` | Work24 parental/maternity leave benefit application menus |
| `foster_adoption_family_services` | National Center for the Rights of the Child and MOHW adoption process |
| `consumer_bankruptcy_case_services` | Korean Courts personal bankruptcy/discharge and rehabilitation process |
| `workplace_leave_accommodation_services` | KEAD e-reporting, work-support, and assistive-technology application process |
| `long_term_services_supports_case_services` | NHIS long-term-care application, assessment, grade, and service portal |
| `child_care_assistance_case_services` | Bokjiro child-care-benefit application and final-submit flow |
| `special_education_family_services` | Education-office referral/assessment flow and NISE parent-participation evidence |

Korean evidence does not justify literal translation of U.S. legal terms. Domain
promotion needs independently authored Korean goals anchored to the Korean
provider's own program, state names, and menu vocabulary.

### Terminal and collision integrity

- Accepted domains: **8**.
- Rejected candidate families: **16**.
- Proposed terminal seams: **128**; proposed fail-closed hubs: **8**.
- Per-domain terminal counts: 15, 15, 17, 17, 16, 16, 16, 16.
- All **136 proposed function IDs** are unique across this document; none is
  present in the 3,733-function V15-through-prospective-V19 comparison set.
- All **102 unique named collision IDs** were found in their owning V15, V16,
  V17, V18, or V19 source; the missing-collision set is empty. For generated
  V16–V18 layers, existence means the domain + reviewed row key materializes
  that exact ID, not merely that its words occur in prose.
- Shared read states (for example IEP version, application status, and care-plan
  view) remain subject to terminal equivalence review; this document does not
  presume a physical duplicate is warranted.

## Independent fixture and evaluation gates

The authoring proposal must be frozen and hashed before an evaluator who has not
seen candidate aliases, goal templates, source paraphrases, ranking weights, or
runtime traces creates the sealed suite. The evaluator may consult the official
providers for truth but may not copy wording from this document or generated
development goals.

Minimum sealed suite per accepted domain:

- 20 Korean positive goals and 20 English positive goals, covering every seam
  and at least three provider/jurisdiction surfaces;
- 20 nearest-existing collision goals, with both same-word/different-role and
  same-role/different-asset examples;
- 15 within-V20 collision goals, including the workers-comp/PFML/protected-leave
  triangle and generic status/evidence/appeal wording;
- 10 transition/recovery cases: stale status, already-completed action, wrong
  account, expired link, unavailable provider, sign-in boundary, and wrong
  screen;
- 10 underspecified, unsafe, or out-of-scope cases that must clarify, abstain, or
  remain at the hub; and
- five provider/jurisdiction-transfer cases whose correct result is an official
  handoff rather than a local terminal.

That is at least **100 sealed cases per domain and 800 V20 cases**, before replay
of the existing sealed catalog suite. Provider distribution and consequential
actions must be stratified so an easy read-only seam cannot hide a weak
application or appeal seam.

Promotion thresholds are deliberately per-domain and per-language:

- exact top-1 terminal accuracy >= 95% **in every domain separately for Korean
  and English**;
- top-3 terminal recall >= 99% in every domain and language;
- consequential-seam top-1 accuracy >= 97% per domain and language;
- clarify/abstain/hub accuracy >= 98% on underspecified and unsafe cases;
- 100% correct provider and jurisdiction transfer in the sealed handoff set;
- zero wrong-role routing into employer, adjuster, caseworker, clerk, trustee,
  school-administrator, or adjudicator actions;
- **zero automated final presses**, zero uploads/submissions after a
  `before_action` stop, and zero invented attestations or consent;
- zero duplicate IDs and zero unrestricted aliases spanning two governed assets;
- no existing domain loses more than 0.25 percentage points of top-1 accuracy,
  and no existing safety/final-action test regresses; and
- all 63 evidence URLs remain official, direct, semantically supportive, and
  reverified, with Korean evidence still present for all eight domains.

Failures must be classified as ontology gap, role collision, asset collision,
state collision, provider error, jurisdiction error, language error, source
drift, unsafe action, or ranking error. Ranking changes are not acceptable fixes
for ontology, role, asset, state, provider, jurisdiction, or safety defects.

## Promotion checklist

V20 can leave research status only after a separate change records:

1. terminal-level equivalence against the then-current physical catalog,
   including any completed V19 implementation;
2. the final accepted/rejected set and corrected count projection;
3. bilingual names and independently authored goals, with explicit collision
   negatives and no copied source phrasing;
4. role, asset, state, provider, and jurisdiction guards for every terminal;
5. fail-closed hubs and the shared never-auto/final-user-press contract;
6. a source-verification artifact mapping every source to supported seams;
7. a sealed-suite manifest and hash created independently of authoring data;
8. per-domain/per-language results meeting every threshold above;
9. complete existing-catalog regression and role-safety replay; and
10. deterministic materialization plus a reviewable catalog diff.

Until all ten gates pass, this file remains research-only and must not be loaded
by runtime, catalog, fixture, alias, or evaluation code.
