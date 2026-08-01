# Navigation Coverage Gaps V17

Status: reviewed candidate source pack (not materialized into the canonical catalog)

Date: 2026-07-30

## Scope and acceptance contract

V17 adds twelve app-independent public-service and regulated-case domains that are not present in the exact V15 catalog or the prospective V16 layer. Each domain has one non-terminal hub and exactly nineteen terminal destinations. The layer therefore contains exactly 12 domains, 240 functions, 228 terminal functions, and 228 intents.

Every terminal has a terminal-specific bilingual name, bilingual representative goal, purpose, authorized-role cues, governed-asset cues, lifecycle-state cues, jurisdiction guard, and safety boundary. `S` means a sensitive or permission-limited read. `C` means a consequential state change. Both classes are `never_auto`, stop before the final action, and require the user to press the final control.

The layer is semantic only. Package names, resource IDs, coordinates, bounds, screenshots, recorded paths, fixed UI paths, pixels, and click sequences are forbidden. A wrong role, wrong record, wrong jurisdiction, wrong lifecycle state, disabled control, hold, permission denial, offline state, or stale data fails closed to the domain hub.

## Reviewed domain inventory

### 1. Unemployment insurance case services (`unemployment_insurance_case_services`)

Hub: 실업보험 청구 서비스 / Unemployment insurance claim services

Terminals (19): `claimant_dashboard`, `initial_claim_start`, `identity_verification`, `wage_employer_history_review`, `separation_fact_finding_response`, `employer_separation_response`, `evidence_upload`, `weekly_certification_submit`, `work_search_record`, `reemployment_service_status`, `claim_status`, `monetary_determination_review`, `eligibility_determination_review`, `payment_status`, `payment_method_update`, `tax_form_1099g_request`, `overpayment_notice_review`, `overpayment_waiver_request`, `determination_appeal_submit`.

Roles/assets/states: claimant, employer respondent, authorized representative; claim, wage record, separation record, certification week, determination, payment, overpayment; draft, identity pending, fact finding, certified, eligible or ineligible, paid, overpaid, appealed.

Jurisdiction and boundary: identified U.S. state UI program and claim period; never submit a claim, certification, response, waiver, payment change, or appeal automatically.

### 2. Social Security benefit services (`social_security_benefit_services`)

Hub: 사회보장 급여 서비스 / Social Security benefit services

Terminals (19): `earnings_record_review`, `benefit_estimate`, `retirement_application_start`, `disability_application_start`, `ssi_application_start`, `medicare_application_start`, `application_status`, `appeal_status`, `benefit_verification_letter`, `social_security_card_replace`, `name_correction_request`, `address_change`, `direct_deposit_update`, `beneficiary_change_report`, `representative_payee_status`, `continuing_disability_review`, `overpayment_notice_review`, `overpayment_waiver_request`, `decision_appeal_request`.

Roles/assets/states: beneficiary or applicant, representative payee, appointed representative; earnings record, benefit application, award, payment instruction, identity record, review, overpayment, appeal; estimated, draft, submitted, pending, awarded, suspended, overpaid, under review, appealed.

Jurisdiction and boundary: identified SSA record and applicable benefit program; never submit an application, correction, report, banking change, waiver, review, or appeal automatically.

### 3. Consumer credit reporting services (`consumer_credit_reporting_services`)

Hub: 소비자 신용정보 서비스 / Consumer credit reporting services

Terminals (19): `credit_report_request`, `credit_file_review`, `tradeline_detail_review`, `inquiry_review`, `adverse_action_notice_review`, `tradeline_dispute_create`, `dispute_evidence_upload`, `dispute_status`, `dispute_result_review`, `consumer_statement_add`, `security_freeze_status`, `security_freeze_place`, `security_freeze_lift`, `fraud_alert_status`, `fraud_alert_place`, `fraud_alert_remove`, `identity_theft_report_start`, `identity_theft_block_request`, `cfpb_complaint_submit`.

Roles/assets/states: consumer, identity-theft victim, authorized advocate; credit file, tradeline, inquiry, dispute, evidence, freeze, fraud alert, identity-theft report, complaint; available, disputed, investigating, resolved, frozen, thawed, alerted, blocked, submitted.

Jurisdiction and boundary: identified U.S. consumer and reporting record; never request disclosure, submit a dispute or complaint, or place, lift, or remove a protection automatically.

### 4. Driver and vehicle licensing services (`driver_vehicle_licensing_services`)

Hub: 운전면허·차량 등록 서비스 / Driver and vehicle licensing services

Terminals (19): `driver_license_status`, `driver_license_apply`, `driver_license_renew`, `driver_license_replace`, `real_id_upgrade`, `driver_record_request`, `driver_test_appointment`, `driver_address_change`, `vehicle_registration_status`, `vehicle_registration_start`, `vehicle_registration_renew`, `vehicle_registration_replace`, `vehicle_title_status`, `vehicle_title_transfer`, `vehicle_title_replace`, `transfer_release_of_liability`, `license_plate_order`, `suspension_reinstatement_status`, `reinstatement_fee_payment`.

Roles/assets/states: driver or applicant, registered owner, buyer or seller, authorized agent; driver license, driving record, appointment, registration, title, vehicle, plate, suspension, fee; eligible, expired, lost, scheduled, registered, transferred, suspended, reinstatement pending, paid.

Jurisdiction and boundary: identified state motor-vehicle agency, person, and vehicle; never apply, renew, transfer, release liability, order, schedule, pay, or reinstate automatically.

### 5. Disaster assistance case services (`disaster_assistance_case_services`)

Hub: 재난 지원 사건 서비스 / Disaster assistance case services

Terminals (19): `declared_area_eligibility_lookup`, `assistance_program_review`, `individual_assistance_application`, `application_status`, `identity_verification_status`, `identity_residency_evidence_upload`, `insurance_information_submit`, `home_occupancy_ownership_verify`, `home_inspection_schedule`, `inspection_status`, `inspection_accommodation_request`, `additional_information_request_review`, `additional_information_response`, `determination_letter_view`, `award_status`, `direct_deposit_update`, `temporary_housing_status`, `appeal_evidence_upload`, `decision_appeal_submit`.

Roles/assets/states: survivor or applicant, household member, authorized representative, inspector; disaster declaration, household case, damaged dwelling, identity evidence, insurance record, inspection, determination, award, housing assistance, appeal; eligible area, draft, submitted, verification pending, inspection pending, decided, awarded, denied, appealed.

Jurisdiction and boundary: identified FEMA-declared disaster, household, damaged dwelling, and assistance case; never submit an application, evidence, banking change, inspection request, response, or appeal automatically.

### 6. Veterans benefit claim services (`veterans_benefit_claim_services`)

Hub: 보훈 급여 청구 서비스 / Veterans benefit claim services

Terminals (19): `intent_to_file`, `claim_type_review`, `disability_claim_start`, `increase_claim_start`, `supplemental_claim_start`, `supporting_evidence_upload`, `claim_exam_status`, `claim_status`, `evidence_request_review`, `decision_letter_download`, `disability_rating_review`, `payment_history`, `direct_deposit_update`, `dependent_change_request`, `accredited_representative_manage`, `higher_level_review_submit`, `supplemental_review_submit`, `board_appeal_start`, `review_appeal_status`.

Roles/assets/states: veteran or claimant, dependent, accredited representative; intent, claim, condition, evidence, examination, rating decision, payment, dependent record, review, appeal; draft, filed, evidence gathering, examination pending, decided, rated, paid, review requested, appealed.

Jurisdiction and boundary: identified VA claimant, benefit, claim, and decision lane; never file, upload, change banking or dependents, appoint a representative, request review, or appeal automatically.

### 7. Wage and hour enforcement operations (`wage_hour_enforcement_ops`)

Hub: 임금·근로시간 집행 업무 / Wage and hour enforcement operations

Terminals (19): `worker_rights_scope_review`, `complaint_requirements_review`, `worker_complaint_prepare`, `worker_complaint_submit`, `complaint_evidence_upload`, `complaint_status`, `retaliation_report_submit`, `investigation_case_queue`, `employer_record_request`, `employer_record_upload`, `employee_interview_record`, `payroll_hours_compliance_review`, `minimum_wage_finding_record`, `overtime_finding_record`, `fmla_finding_record`, `child_labor_finding_record`, `back_wage_calculation`, `resolution_terms_review`, `resolution_payment_confirm`.

Roles/assets/states: worker or complainant, WHD investigator, employer respondent, authorized representative; complaint, evidence, investigation case, payroll and hours record, interview, finding, back-wage calculation, resolution; intake, submitted, investigating, records requested, finding drafted, resolved, payment pending, closed.

Jurisdiction and boundary: identified U.S. wage-and-hour law, workplace, worker, employer, and case; never submit a complaint or retaliation report, issue a record request or finding, or confirm resolution payment automatically.

### 8. Student financial aid services (`student_financial_aid_services`)

Hub: 연방 학자금 지원 서비스 / Student financial aid services

Terminals (19): `aid_dashboard`, `fafsa_start`, `contributor_invite`, `contributor_section_status`, `student_section_review`, `fafsa_review`, `fafsa_sign_submit`, `fafsa_status`, `submission_summary_review`, `fafsa_correction`, `school_recipient_update`, `federal_aid_history_review`, `loan_counseling_complete`, `master_promissory_note_sign`, `repayment_plan_compare`, `idr_application`, `loan_consolidation_application`, `pslf_form_submit`, `pslf_progress_review`.

Roles/assets/states: student or borrower, contributor, parent, authorized school official; FAFSA form, contributor section, aid history, loan, counseling, promissory note, repayment plan, IDR request, consolidation, PSLF form; draft, contributor pending, reviewed, signed, submitted, processed, corrected, in repayment, forgiveness review.

Jurisdiction and boundary: identified Federal Student Aid account, award year, loan, and authorized participant; never invite, sign, submit, correct, select a recipient, complete counseling, apply, consolidate, or certify automatically.

### 9. Child support case services (`child_support_case_services`)

Hub: 아동양육비 사건 서비스 / Child support case services

Terminals (19): `services_application`, `case_status`, `parentage_establishment_status`, `parentage_establishment_submit`, `support_order_view`, `payment_history`, `payment_route_lookup`, `income_withholding_status`, `employer_iwo_response`, `employer_termination_report`, `lump_sum_report`, `employment_change_report`, `medical_support_notice_status`, `order_modification_eligibility_review`, `order_modification_request`, `interstate_case_status`, `secure_document_exchange`, `arrears_balance_review`, `enforcement_action_review`.

Roles/assets/states: custodial or noncustodial parent, employer, caseworker, authorized representative; support case, parentage record, order, payment, withholding notice, employment record, medical-support notice, modification, interstate referral, arrears, enforcement action; application pending, established, ordered, paying, withholding active, modified, interstate, delinquent, enforcement active.

Jurisdiction and boundary: identified state or tribal child-support program, parties, employer, order, and case; never apply, establish parentage, respond to withholding, report employment or lump sums, exchange documents, or request modification automatically.

### 10. Public housing assistance services (`public_housing_assistance_services`)

Hub: 공공주택 지원 서비스 / Public housing assistance services

Terminals (19): `pha_locator`, `program_eligibility_review`, `waitlist_application`, `waitlist_status`, `applicant_contact_update`, `eligibility_evidence_upload`, `voucher_orientation_status`, `voucher_issue_status`, `voucher_search_extension_request`, `tenancy_approval_request`, `unit_inspection_status`, `inspection_deficiency_review`, `annual_recertification`, `income_household_change_report`, `rent_recalculation_request`, `reasonable_accommodation_request`, `portability_eligibility_review`, `portability_request`, `informal_review_hearing_request`.

Roles/assets/states: applicant or participant, household representative, landlord, PHA caseworker; waitlist application, household case, voucher, tenancy request, unit, inspection, income record, rent calculation, accommodation, portability transfer, hearing; waitlisted, eligible, voucher issued, searching, tenancy pending, inspection failed or passed, recertification due, transferred, hearing pending.

Jurisdiction and boundary: identified HUD program, administering PHA, household, voucher, and unit; never apply, upload evidence, change household facts, request tenancy, accommodation, portability, recalculation, extension, or hearing automatically.

### 11. Healthcare provider enrollment operations (`healthcare_provider_enrollment_ops`)

Hub: 의료공급자 등록 업무 / Healthcare provider enrollment operations

Terminals (19): `npi_status`, `npi_apply`, `npi_update`, `enrollment_eligibility_review`, `medicare_enrollment_start`, `enrollment_application_status`, `supporting_document_upload`, `application_fee_status`, `hardship_waiver_request`, `authorized_official_manage`, `staff_access_manage`, `practice_location_update`, `ownership_change_report`, `benefit_reassignment_review`, `benefit_reassignment_manage`, `revalidation_due_review`, `revalidation_submit`, `deactivation_status`, `enrollment_reactivate`.

Roles/assets/states: individual provider, organization provider, authorized official, delegated staff; NPI record, enrollment application, supporting document, fee, waiver, practice location, ownership record, benefit reassignment, revalidation, enrollment status; unregistered, draft, submitted, development requested, approved, revalidation due, deactivated, reactivation pending.

Jurisdiction and boundary: identified CMS enrollment jurisdiction, provider, NPI or TIN, enrollment record, and authorized official; never apply, update, upload, waive, delegate, report ownership, reassign benefits, revalidate, or reactivate automatically.

### 12. Professional license administration (`professional_license_administration`)

Hub: 전문직 면허 행정 / Professional license administration

Terminals (19): `profession_requirements_view`, `initial_license_application`, `education_credential_verification`, `experience_verification`, `exam_eligibility_status`, `supervised_practice_status`, `out_of_state_endorsement`, `limited_permit_application`, `application_status`, `public_license_verification`, `registration_status`, `registration_renewal`, `continuing_education_status`, `continuing_education_attestation`, `name_change_request`, `address_change`, `inactive_registration_request`, `registration_reactivate`, `disciplinary_action_review`.

Roles/assets/states: applicant, licensee, supervisor, credential verifier, board reviewer; profession, application, education credential, experience record, examination eligibility, supervision record, permit, license, registration, continuing education, disciplinary record; eligible, draft, verification pending, examination approved, permitted, licensed, active, expired, inactive, reactivation pending, disciplined.

Jurisdiction and boundary: identified state professional board, profession, person, license or application, and registration period; never apply, attest, renew, change identity data, request inactive status, endorse, permit, or reactivate automatically.

## Official primary-source registry

The implementation normalizes each HTTPS URL, seals the resulting source records, maps every terminal to at least one source in its domain, and rejects duplicate URLs, unapproved publishers, incomplete mappings, orphan records, or changed source-record hashes.

| Domain | Publisher | Official primary source |
|---|---|---|
| `unemployment_insurance_case_services` | U.S. Department of Labor | [UI application review and confirmation](https://www.dol.gov/agencies/eta/ui-modernization/customer-experience/improve-applications/review-and-confirmation-sections) |
| `unemployment_insurance_case_services` | U.S. Department of Labor | [Unemployment Insurance](https://www.dol.gov/agencies/eta/feature-unemployment) |
| `unemployment_insurance_case_services` | U.S. Department of Labor | [Unemployment Insurance modernization](https://www.dol.gov/agencies/eta/ui-modernization) |
| `unemployment_insurance_case_services` | U.S. Department of Labor | [Weekly certification](https://www.dol.gov/agencies/eta/ui-modernization/initial-application/weekly-certification) |
| `unemployment_insurance_case_services` | U.S. Department of Labor | [UI plain-language repository](https://www.dol.gov/agencies/eta/ui-modernization/use-plain-language/plain-language-repository) |
| `social_security_benefit_services` | Social Security Administration | [Apply for Social Security benefits](https://www.ssa.gov/apply) |
| `social_security_benefit_services` | Social Security Administration | [Appeal a decision](https://www.ssa.gov/disabilityssi/appeal.html) |
| `social_security_benefit_services` | Social Security Administration | [Online services](https://www.ssa.gov/onlineservices/) |
| `social_security_benefit_services` | Social Security Administration | [Repay overpaid benefits](https://www.ssa.gov/manage-benefits/resolve-overpayment/repay-overpaid-benefits) |
| `social_security_benefit_services` | Social Security Administration | [Request waiver of overpayment recovery](https://www.ssa.gov/forms/ssa-632.html) |
| `consumer_credit_reporting_services` | Consumer Financial Protection Bureau | [Dispute an error on a credit report](https://www.consumerfinance.gov/ask-cfpb/how-do-i-dispute-an-error-on-my-credit-report-en-314/) |
| `consumer_credit_reporting_services` | Consumer Financial Protection Bureau | [Identity theft response](https://www.consumerfinance.gov/ask-cfpb/what-do-i-do-if-i-think-i-have-been-a-victim-of-identity-theft-en-31/) |
| `consumer_credit_reporting_services` | Consumer Financial Protection Bureau | [Credit reports and scores](https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/) |
| `consumer_credit_reporting_services` | Consumer Financial Protection Bureau | [Credit and consumer reporting complaint notice](https://www.consumerfinance.gov/complaint/credit-and-consumer-reporting-complaint-notice/) |
| `consumer_credit_reporting_services` | Consumer Financial Protection Bureau | [Credit freezes and fraud alerts](https://www.consumerfinance.gov/archive/blog/free-credit-freezes-are-here/) |
| `driver_vehicle_licensing_services` | USA.gov | [State motor vehicle services](https://www.usa.gov/state-motor-vehicle-services) |
| `driver_vehicle_licensing_services` | California Department of Motor Vehicles | [DMV online services](https://www.dmv.ca.gov/portal/dmv-online/) |
| `driver_vehicle_licensing_services` | California Department of Motor Vehicles | [Driver license and identification](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/) |
| `driver_vehicle_licensing_services` | California Department of Motor Vehicles | [Vehicle registration](https://www.dmv.ca.gov/portal/vehicle-registration/) |
| `driver_vehicle_licensing_services` | California Department of Motor Vehicles | [Vehicle registration renewal](https://www.dmv.ca.gov/portal/vehicle-registration/vehicle-registration-renewal/) |
| `disaster_assistance_case_services` | Federal Emergency Management Agency | [Ways to apply for disaster assistance](https://www.fema.gov/node/4-ways-apply-disaster-assistance) |
| `disaster_assistance_case_services` | Federal Emergency Management Agency | [Individual Assistance Program and Policy Guide](https://www.fema.gov/sites/default/files/2020-07/fema_individual-assistance-program-policy-guide_2019.pdf) |
| `disaster_assistance_case_services` | Federal Emergency Management Agency | [Individual Assistance appeals](https://www.fema.gov/sites/default/files/documents/fema_ia-quick-reference_appeals.pdf) |
| `disaster_assistance_case_services` | Federal Emergency Management Agency | [What to expect after applying](https://www.fema.gov/print/pdf/node/662135) |
| `disaster_assistance_case_services` | Federal Emergency Management Agency | [Appealing FEMA's decision](https://www.fema.gov/print/pdf/node/689311) |
| `veterans_benefit_claim_services` | U.S. Department of Veterans Affairs | [How to file a VA disability claim](https://www.va.gov/disability/how-to-file-claim/) |
| `veterans_benefit_claim_services` | U.S. Department of Veterans Affairs | [Check claim or appeal status](https://www.va.gov/claim-or-appeal-status/) |
| `veterans_benefit_claim_services` | U.S. Department of Veterans Affairs | [Decision reviews and appeals](https://www.va.gov/decision-reviews/) |
| `veterans_benefit_claim_services` | U.S. Department of Veterans Affairs | [The VA claim process after filing](https://www.va.gov/disability/after-you-file-claim/) |
| `veterans_benefit_claim_services` | U.S. Department of Veterans Affairs | [Download VA benefit letters](https://www.va.gov/records/download-va-letters/) |
| `wage_hour_enforcement_ops` | U.S. Department of Labor | [How to file a complaint](https://www.dol.gov/agencies/whd/contact/complaints) |
| `wage_hour_enforcement_ops` | U.S. Department of Labor | [Handy Reference Guide to the FLSA](https://www.dol.gov/agencies/whd/compliance-assistance/handy-reference-guide-flsa) |
| `wage_hour_enforcement_ops` | U.S. Department of Labor | [Wage and Hour Division](https://www.dol.gov/agencies/whd) |
| `wage_hour_enforcement_ops` | U.S. Department of Labor | [Retaliation](https://www.dol.gov/agencies/whd/retaliation) |
| `wage_hour_enforcement_ops` | U.S. Department of Labor | [Payroll Audit Independent Determination questions](https://www.dol.gov/agencies/whd/paid/questions-and-answers) |
| `student_financial_aid_services` | Federal Student Aid | [FAFSA student steps](https://studentaid.gov/articles/fafsa-student-steps/) |
| `student_financial_aid_services` | Federal Student Aid | [FAFSA Submission Summary](https://studentaid.gov/articles/fafsa-submission-summary/) |
| `student_financial_aid_services` | Federal Student Aid | [Manage PSLF progress](https://studentaid.gov/articles/manage-your-pslf-progress/) |
| `student_financial_aid_services` | Federal Student Aid | [Repaying your federal student loans](https://studentaid.gov/sites/default/files/repaying-your-loans.pdf) |
| `student_financial_aid_services` | Federal Student Aid | [Direct Consolidation Loan Application and Promissory Note](https://studentaid.gov/app/api/repayment-forms/download-repayment-form?localeCode=en-us&searchType=library&shortName=consollink) |
| `child_support_case_services` | Office of Child Support Services | [Child Support Portal](https://ocsp.acf.hhs.gov/csp/) |
| `child_support_case_services` | Office of Child Support Services | [Employer Services](https://ocsp.acf.hhs.gov/csp/home/employer) |
| `child_support_case_services` | Office of Child Support Services | [Business Intelligence for Child Support](https://www.acf.hhs.gov/sites/default/files/documents/ocse/bics_co_brief.pdf) |
| `child_support_case_services` | Office of Child Support Services | [Intergovernmental Reference Guide state profile](https://ocsp.acf.hhs.gov/irg/profile/displayResults) |
| `child_support_case_services` | Office of Child Support Services | [State lump-sum reporting information](https://ocsp.acf.hhs.gov/irg/irgpdf.pdf?addrClassType=EMP&addrType=SLS&geoType=OGP&groupCode=EMP) |
| `public_housing_assistance_services` | U.S. Department of Housing and Urban Development | [Housing Choice Voucher Program](https://www.hud.gov/topics/housing_choice_voucher_program_section_8?sub5=DCB07A0C-605C-7109-253D-0BF1F57C98FD) |
| `public_housing_assistance_services` | U.S. Department of Housing and Urban Development | [Housing Choice Vouchers for tenants](https://www.hud.gov/helping-americans/housing-choice-vouchers-tenants) |
| `public_housing_assistance_services` | U.S. Department of Housing and Urban Development | [Voucher portability](https://www.hud.gov/helping-americans/housing-choice-vouchers-portability) |
| `public_housing_assistance_services` | U.S. Department of Housing and Urban Development | [Housing Choice Voucher Program Guidebook](https://www.hud.gov/helping-americans/housing-choice-vouchers-guidebook) |
| `public_housing_assistance_services` | U.S. Department of Housing and Urban Development | [Informal reviews and hearings](https://www.hud.gov/sites/documents/DOC_35626.PDF) |
| `healthcare_provider_enrollment_ops` | Centers for Medicare & Medicaid Services | [PECOS](https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/chain-ownership-system-pecos) |
| `healthcare_provider_enrollment_ops` | Centers for Medicare & Medicaid Services | [Revalidations](https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/revalidations) |
| `healthcare_provider_enrollment_ops` | Centers for Medicare & Medicaid Services | [Provider enrollment resources](https://www.cms.gov/Outreach-and-Education/Medicare-Learning-Network-MLN/MLNProducts/EnrollmentResources/provider-resources/provider-enrolment/Med-Prov-Enroll-MLN9658742.html) |
| `healthcare_provider_enrollment_ops` | Centers for Medicare & Medicaid Services | [Manage your enrollment](https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/chain-ownership-system-pecos/manage-your-enrollment) |
| `healthcare_provider_enrollment_ops` | Centers for Medicare & Medicaid Services | [Enrollment applications](https://www.cms.gov/medicare/enrollment-renewal/providers-suppliers/chain-ownership-system-pecos/enrollment-applications) |
| `healthcare_provider_enrollment_ops` | Centers for Medicare & Medicaid Services | [National Provider Identifier standard](https://www.cms.gov/medicare/regulations-guidance/administrative-simplification/national-provider-identifier-standard) |
| `professional_license_administration` | New York State Education Department | [Office of the Professions](https://www.op.nysed.gov/) |
| `professional_license_administration` | New York State Education Department | [General information and policies](https://www.op.nysed.gov/about/general-information-policies) |
| `professional_license_administration` | New York State Education Department | [Online registration renewal](https://www.op.nysed.gov/registration-renewal/online-registration-renewal) |
| `professional_license_administration` | New York State Education Department | [Online verification searches](https://www.op.nysed.gov/services/verifications/online-verification-searches) |
| `professional_license_administration` | New York State Education Department | [Written certification or verification of licensure](https://www.op.nysed.gov/verification-search/written-certification-or-verification-of-licensure) |

## Korean jurisdiction companions

The U.S. lifecycle records above remain jurisdiction-specific. The following Korean official services are registered separately and contribute only the Korean menu terms and terminal mappings that their pages directly support. They do not convert FAFSA into a Korean scholarship form, PECOS into a Korean provider record, or any other U.S.-specific record into a false universal equivalent.

| V17 domain | Korean official institution | Direct first-party evidence | Isolated menu terms |
|---|---|---|---|
| `unemployment_insurance_case_services` | 고용24 | [실업급여 신청절차](https://www.work24.go.kr/cm/c/f/1100/selecSystInfo.do?systClId=SC00000258&systCnntId=&systId=SI00000347) | 고용24, 실업급여, 수급자격 인정 신청, 실업인정 인터넷 신청, 고용보험 심사청구 |
| `social_security_benefit_services` | 국민연금공단 | [국민연금 전자민원 조회·신고·신청](https://www.nps.or.kr/comm/pop/getOHAH0077P2.do) | 내 국민연금 알아보기, 연금·일시금 청구, 연금 지급내역, 수급자 계좌번호 변경 |
| `consumer_credit_reporting_services` | 한국신용정보원 | [본인신용정보 열람서비스](https://www.credit4u.or.kr/) | 크레딧포유, 본인신용정보 열람, 신용정보 조회, 신용정보 등록현황 |
| `driver_vehicle_licensing_services` | 한국도로교통공단 | [운전면허증 발급 가이드](https://www.safedriving.or.kr/diGuide/selectDiGuide18.do) | 안전운전 통합민원, 적성검사·갱신, 분실 등 재발급, 운전면허증 발급 |
| `disaster_assistance_case_services` | 행정안전부 | [사유재산 피해신고](https://www.safekorea.go.kr/idsiSFK/neo/sfk/cs/pan/cdr/cdreaiBefore.html?menuSeq=157) | 국민재난안전포털, 사유재산 피해신고, 자연재난 선택, 피해신고 신규등록, 처리상태 |
| `veterans_benefit_claim_services` | 국가보훈부 | [나만의예우](https://pmp.mpva.go.kr/rt/tse/rtTseS001.do?mnuKeyVl=138) | 나만의예우, 나의지원내역, 보훈급여금, 민원신청 |
| `wage_hour_enforcement_ops` | 고용노동부 | [체불임금 해결 방법](https://labor.moel.go.kr/minwonSysInfo/wagesolway.do) | 노동포털, 진정서(임금체불, 기타 근로기준 분야), 나의민원, 체불임금 등 사업주 확인서 |
| `student_financial_aid_services` | 한국장학재단 | [장학금·학자금 서비스](https://www.kosaf.go.kr/) | 장학금신청, 신청서작성, 신청현황, 서류제출현황 |
| `child_support_case_services` | 양육비이행관리원 | [양육비 이행확보 지원 신청 방법](https://www.childsupport.or.kr/lay1/S1T10C12/contents.do) | 양육비 이행확보 지원신청, 제재조치 신청, 지원 신청 방법, 양육비 선지급 신청 |
| `public_housing_assistance_services` | 한국토지주택공사 | [LH청약플러스 임대가이드](https://apply.lh.or.kr/lhapply/cm/cntnts/cntntsView.do?cntntsId=1125&mi=1240) | LH청약플러스, 청약신청, 임대주택, 공고문, 신청자격 |
| `healthcare_provider_enrollment_ops` | 건강보험심사평가원 | [요양기관 현황신고](https://biz.hira.or.kr/contents/html/MP00000099.html) | 요양기관업무포털, 현황신고, 기호부여신청, 보건의료자원 통합신고포털, 현황신고·변경 |
| `professional_license_administration` | 한국산업인력공단 | [큐넷 온라인 도움말](https://www.q-net.or.kr/man001.do?gId=01&gSite=Q&id=man00701&step=7) | 큐넷, 원서접수, 자격증발급, 확인서발급, 합격자발표 |

## Explicit exclusions and collision guards

- Passport and immigration are already represented by `government_digital`; they are not duplicated.
- Generic public-benefit eligibility and casework are already represented by `social_services_casework`; V17 destinations require the named program record and jurisdiction.
- Workers compensation is already represented by insurance and occupational-safety domains; it is not duplicated.
- Generic identity, payments, documents, appointments, account settings, and appeals remain contextual primitives, not new V17 domains.
- No app-specific path, package, selector, screen coordinate, screenshot fingerprint, or recorded click sequence is accepted.
- Similar labels such as `application_status`, `appeal`, `direct_deposit_update`, `payment_history`, and `address_change` are resolved only when domain, authorized role, governed asset, jurisdiction, and lifecycle state are sufficiently explicit.

## Deterministic verification

`scripts/navigation_catalog_v17_data.py` pins this document by SHA-256, constructs the layer deterministically, validates exact counts and IDs, verifies every official-source record and terminal mapping, rejects V15/V16 collisions, emits semantic/collision/recovery/isolation probes, and fails closed on partial or tampered V17 materialization. The canonical catalog and previously generated artifacts remain untouched.
