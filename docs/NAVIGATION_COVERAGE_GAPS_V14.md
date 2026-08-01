# Navigation ontology coverage gap audit — v14

Audit date: 2026-07-30
Baseline: materialized v13 catalog `13.0.0`, **155 domains, 2,362 functions, 2,180 terminal functions, and 2,180 intents**. The audit treated `function-catalog.v1.json`, the v3–v13 source modules, and `NAVIGATION_COVERAGE_GAPS_V5.md` through `V13.md` as the complete prior set. It did not read, derive from, or create an independent evaluation fixture.

## Decision

The next expansion should add the following 12 role-governed domains. They cover common institutional workflows that are not represented by a v13 domain with the same role, governed asset, lifecycle, and safety boundary. The proposal is exactly **252 functions** (**12 low-risk hubs + 240 high-risk terminals**) and **240 intents**. If accepted unchanged, v14 will total **167 domains, 2,614 functions, 2,420 terminal functions, and 2,420 intents**.

| Priority | Proposed domain ID | Terminal functions | Functions including hub | Intents | Sensitive read-only (`S`) | Consequential (`C`) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | `clinical_diagnostic_lab_ops` | 20 | 21 | 20 | 7 | 13 |
| 2 | `perioperative_surgical_ops` | 20 | 21 | 20 | 7 | 13 |
| 3 | `healthcare_revenue_cycle_ops` | 20 | 21 | 20 | 7 | 13 |
| 4 | `mortgage_origination_servicing_ops` | 20 | 21 | 20 | 7 | 13 |
| 5 | `financial_crime_compliance_ops` | 20 | 21 | 20 | 7 | 13 |
| 6 | `higher_education_student_admin` | 20 | 21 | 20 | 7 | 13 |
| 7 | `human_subjects_research_oversight` | 20 | 21 | 20 | 7 | 13 |
| 8 | `emergency_communications_dispatch` | 20 | 21 | 20 | 7 | 13 |
| 9 | `public_health_surveillance_ops` | 20 | 21 | 20 | 7 | 13 |
| 10 | `power_generation_plant_ops` | 20 | 21 | 20 | 7 | 13 |
| 11 | `land_title_recording_admin` | 20 | 21 | 20 | 7 | 13 |
| 12 | `postal_network_operations` | 20 | 21 | 20 | 7 | 13 |
| **Total** | **12 domains** | **240** | **252** | **240** | **84** | **156** |

Risk accounting is exact: the 12 hubs are `risk_level=low`, `state_changing=false`, and `automation_policy=safe_navigation`; all 240 terminals are `risk_level=high`, `automation_policy=never_auto`, `stop_policy=before_action`, and `user_owned_final_press=true`. The 84 `S` terminals are sensitive read-only destinations with `state_changing=false`; the 156 `C` terminals change a record, authorization, dispatch, financial position, legal status, or physical-world operational state and have `state_changing=true`. No v14 terminal is low or medium risk.

## Exact proposed surface

ID contract:

- Hub: `<domain>.hub`.
- Terminal: `<domain>.<terminal_key>`.
- Intent: `v14_<domain>_<terminal_key>`.
- Each terminal key below creates exactly one terminal function and exactly one intent. The two lists under every domain contain 7 `S` and 13 `C` keys, respectively.
- Names are conceptual destinations, not package names, resource IDs, coordinates, pixels, or fixed click sequences.

### 1. Clinical diagnostic laboratory operations (`clinical_diagnostic_lab_ops`)

New boundary: diagnostic test order → patient specimen/accession → method and quality-control state → verified or corrected patient result. This is not `laboratory_research_ops`, whose governed object is a research experiment/sample, or `clinical_care_team_ops`, which consumes results but does not operate the diagnostic laboratory lifecycle.

- `S` (7): `test_order_worklist`, `specimen_accession_status`, `specimen_chain_of_custody_view`, `analyzer_qc_status`, `result_validation_queue`, `reference_interval_review`, `critical_result_notification_status`.
- `C` (13): `specimen_accession`, `specimen_reject`, `aliquot_create`, `analyzer_run_authorize`, `qc_result_accept`, `result_enter`, `result_validate`, `critical_result_notification_record`, `corrected_result_issue`, `referral_test_handoff`, `test_cancel`, `proficiency_result_submit`, `nonconformance_report`.
- Required discriminators: patient/specimen or accession ID, ordered analyte/method, laboratory role, and pre-analytic/analytic/post-analytic state. Generic “result,” “sample,” or “approve” must not select this domain.

### 2. Perioperative surgical operations (`perioperative_surgical_ops`)

New boundary: scheduled surgical case → consent/site/procedure verification → operating-room readiness and intraoperative record → recovery handoff. This excludes general charting in `clinical_care_team_ops`, treatment-course control in `radiation_therapy_ops`, and equipment maintenance.

- `S` (7): `case_schedule`, `patient_case_summary`, `consent_status`, `preoperative_checklist_status`, `implant_supply_status`, `operating_room_readiness`, `case_timeline`.
- `C` (13): `case_book`, `preop_assessment_sign`, `site_procedure_verification`, `team_brief_record`, `anesthesia_readiness_accept`, `patient_room_transfer`, `procedure_start_record`, `implant_usage_record`, `specimen_handoff_record`, `count_reconciliation_sign`, `procedure_end_record`, `recovery_handoff`, `case_record_close`.
- Required discriminators: surgical patient/case, procedure and laterality/site, room/team role, and pre-op/intra-op/recovery state. “Case,” “schedule,” or “handoff” alone is insufficient.

### 3. Healthcare revenue-cycle operations (`healthcare_revenue_cycle_ops`)

New boundary: provider encounter and coverage → authorization/charge/code → healthcare claim/remittance/denial → patient-account closure. It is distinct from consumer `billing`, general `business_accounting`, payer-side `insurance_claims_adjuster_ops`, and clinical ordering.

- `S` (7): `claim_worklist`, `coverage_verification_status`, `prior_authorization_status`, `charge_review`, `coding_review_queue`, `remittance_view`, `denial_aging_dashboard`.
- `C` (13): `patient_account_register`, `coverage_verification_record`, `prior_authorization_submit`, `charge_capture`, `coding_finalize`, `claim_create`, `claim_scrub_release`, `claim_submit`, `payment_post`, `contractual_adjustment_post`, `denial_appeal_submit`, `patient_refund_issue`, `account_close`.
- Required discriminators: provider-side patient account/encounter, payer/plan, service code or charge, and authorization/claim/remittance/denial state. A generic invoice, insurance claim, or payment must route elsewhere.

### 4. Mortgage origination and servicing (`mortgage_origination_servicing_ops`)

New boundary: identified borrower and secured property → disclosure/appraisal/underwriting/closing → boarded loan, escrow, delinquency, and loss mitigation. Existing `finance_long_tail` exposes consumer loan goals but not a lender/servicer-controlled mortgage file lifecycle.

- `S` (7): `application_pipeline`, `borrower_file_view`, `loan_estimate_review`, `underwriting_conditions`, `appraisal_status`, `escrow_analysis_view`, `delinquency_dashboard`.
- `C` (13): `application_intake`, `credit_authorization_record`, `disclosure_deliver`, `appraisal_order`, `underwriting_decision`, `rate_lock`, `closing_disclosure_issue`, `closing_funds_authorize`, `loan_board`, `payment_post`, `escrow_disbursement`, `loss_mitigation_decision`, `foreclosure_referral`.
- Required discriminators: borrower, collateral property, loan/file ID, lender or servicer role, and origination/closing/servicing/default state. Generic eligibility, repayment, rent, or property search is excluded.

### 5. Financial-crime compliance operations (`financial_crime_compliance_ops`)

New boundary: customer/transaction screening or monitoring alert → compliance investigation → regulatory filing, restriction request, or controlled closure. This is not `cybersecurity_soc_ops`, card security, fraud self-reporting, or an insurer fraud referral.

- `S` (7): `monitoring_alert_queue`, `customer_due_diligence_view`, `transaction_case_view`, `sanctions_screening_result`, `suspicious_activity_dashboard`, `watchlist_source_status`, `filing_deadline_view`.
- `C` (13): `customer_risk_rate`, `enhanced_due_diligence_open`, `screening_hit_disposition`, `monitoring_alert_escalate`, `case_assign`, `transaction_restriction_request`, `suspicious_activity_report_file`, `currency_transaction_report_file`, `account_restriction_request`, `law_enforcement_request_record`, `information_sharing_request_record`, `case_close`, `audit_exception_record`.
- Required discriminators: regulated institution/compliance role, customer or transaction, alert/watchlist basis, and review/filing/restriction state. A generic “alert,” “case,” “block,” or “report fraud” must abstain or route to its existing domain.

### 6. Higher-education student administration (`higher_education_student_admin`)

New boundary: applicant → institutional student record/program → registration, academic progress, aid, transcript, graduation, or separation. It excludes learning content in `education`, instructor course work in `classroom_instructor_ops`, and HR applicant workflows.

- `S` (7): `applicant_queue`, `student_record_view`, `degree_audit`, `registration_status`, `financial_aid_award_view`, `student_account_ledger`, `academic_standing_view`.
- `C` (13): `applicant_admit`, `student_program_enroll`, `course_add_drop`, `transfer_credit_post`, `grade_change_approve`, `degree_exception_approve`, `graduation_clear`, `financial_aid_package_award`, `aid_disbursement_release`, `tuition_adjustment_post`, `academic_hold_place_release`, `transcript_issue`, `student_separation_record`.
- Required discriminators: institution, student/applicant, academic program or term, registrar/aid role, and admissions/enrollment/award/completion state. “Course,” “grade,” or “application” alone is not enough.

### 7. Human-subjects research oversight (`human_subjects_research_oversight`)

New boundary: research protocol and investigator → IRB determination/review → approval, modification, safety oversight, reliance, suspension, or closure. This differs from study-site execution in `clinical_trial_site_ops`, sponsor/grant administration, and laboratory notebook review.

- `S` (7): `submission_queue`, `protocol_summary`, `consent_materials_review`, `reviewer_assignment`, `continuing_review_status`, `safety_report_dashboard`, `reliance_agreement_status`.
- `C` (13): `protocol_intake`, `exempt_determination`, `expedited_review_decision`, `convened_review_record`, `approval_issue`, `modification_approve`, `consent_waiver_decision`, `continuing_review_approve`, `unanticipated_problem_record`, `protocol_deviation_report`, `study_hold_suspend`, `study_close`, `reliance_agreement_execute`.
- Required discriminators: oversight body/reviewer role, protocol, investigator/site, human-subjects category, and submitted/reviewed/approved/suspended/closed state. Generic protocol approval must not match.

### 8. Emergency communications and dispatch (`emergency_communications_dispatch`)

New boundary: incoming emergency communication → caller/location/priority validation → CAD incident and responder-unit dispatch → communications handoff and call closure. It precedes and remains separate from field command in `emergency_response_operations` and IT alerting in `incident_oncall`.

- `S` (7): `call_queue`, `cad_incident_view`, `caller_location_confidence`, `responder_unit_status`, `dispatch_recommendation_view`, `radio_channel_status`, `incident_timeline`.
- `C` (13): `emergency_call_accept`, `cad_incident_create`, `call_triage_code`, `service_address_validate`, `responder_unit_dispatch`, `responder_status_update`, `additional_resource_request`, `interagency_call_transfer`, `medical_instruction_handoff_record`, `incident_priority_change`, `duplicate_call_merge`, `cad_incident_close`, `quality_flag_submit`.
- Required discriminators: public-safety answering point/dispatcher role, caller/call ID, validated location, CAD incident, responding discipline/unit, and queued/dispatched/en-route/closed state. The agent never invents or delivers emergency medical instructions; it may only navigate to an authorized protocol or record/handoff destination and stop.

### 9. Public-health surveillance operations (`public_health_surveillance_ops`)

New boundary: reportable condition or laboratory report → jurisdictional case/contact investigation → cluster/outbreak action, notice, transfer, and closure. This excludes bedside care, individual social-service casework, and incident-command resource operations.

- `S` (7): `notifiable_condition_queue`, `surveillance_case_view`, `laboratory_report_review`, `contact_monitoring_queue`, `outbreak_dashboard`, `exposure_site_view`, `vaccine_inventory_status`.
- `C` (13): `surveillance_case_create`, `case_classification_update`, `case_interview_record`, `contact_enroll`, `isolation_guidance_issue`, `laboratory_followup_request`, `cluster_link_record`, `outbreak_declaration_record`, `public_exposure_notice_publish`, `vaccine_allocation_release`, `adverse_event_report`, `jurisdiction_transfer`, `case_close`.
- Required discriminators: public-health jurisdiction/role, reportable condition, case/contact or cluster, and suspected/probable/confirmed/linked/closed state. Generic patient results, safety incidents, news, or notifications do not qualify.

### 10. Non-nuclear power-generation plant operations (`power_generation_plant_ops`)

New boundary: generating unit and fuel/steam/turbine process → dispatch, synchronization, load, emissions, clearance, trip, and shift control. This is separate from distribution restoration in `utility_grid_field_ops`, nuclear safety in `nuclear_plant_operations`, and generic maintenance work orders.

- `S` (7): `plant_unit_status`, `dispatch_schedule_review`, `fuel_inventory`, `emissions_monitor`, `boiler_turbine_trend`, `protection_interlock_status`, `maintenance_clearance_board`.
- `C` (13): `unit_startup_authorize`, `synchronization_authorize`, `load_setpoint_change`, `unit_shutdown_authorize`, `fuel_switch_record`, `emissions_excursion_report`, `operating_limit_deviation_record`, `energy_isolation_permit_issue`, `maintenance_return_service`, `black_start_readiness_certify`, `unit_trip_record`, `environmental_report_submit`, `shift_handover_accept`.
- Required discriminators: plant/generating unit, control-room role, fuel or thermodynamic process, grid synchronization/load state, and clearance/operating-limit state. “Outage,” “switch,” “unit,” or “start” alone must not match.

### 11. Land-title recording administration (`land_title_recording_admin`)

New boundary: submitted legal instrument → parcel/legal description and grantor-grantee index → acceptance/rejection and authoritative recording/certification. It is distinct from property search/leasing, building permitting, court docketing, and probate case administration.

- `S` (7): `recording_queue`, `parcel_title_chain`, `instrument_image_review`, `legal_description_review`, `lien_encumbrance_view`, `recording_fee_status`, `map_plat_status`.
- `C` (13): `instrument_intake`, `grantor_grantee_index`, `recording_accept`, `recording_reject`, `deed_record`, `mortgage_lien_record`, `lien_release_record`, `easement_record`, `plat_record`, `document_redact`, `correction_instrument_link`, `certified_copy_issue`, `parcel_merge_split_record`.
- Required discriminators: recorder/registrar jurisdiction, parcel or legal description, instrument type/parties, and received/indexed/recorded/rejected/corrected state. A generic document, property, filing, lien, or map is insufficient.

### 12. Postal-network operations (`postal_network_operations`)

New boundary: accepted mailpiece and postage → induction/container/sortation/transport → accountable delivery, forwarding, undeliverable disposition, or claim decision. This is broader than recipient controls in `parcel_courier`, customs forwarding, warehouse fulfillment, and gig last-mile delivery.

- `S` (7): `acceptance_queue`, `mailpiece_tracking`, `sortation_plan`, `dispatch_schedule`, `container_manifest`, `delivery_exception_queue`, `address_quality_status`.
- `C` (13): `postage_accept`, `mailpiece_induct`, `container_close`, `sort_run_release`, `missort_record`, `dispatch_handoff`, `transport_arrival_record`, `delivery_event_record`, `accountable_mail_signature_record`, `hold_mail_activate`, `forwarding_order_apply`, `undeliverable_disposition`, `postal_claim_adjudicate`.
- Required discriminators: postal operator role, mail class/postage, mailpiece or handling-unit identifier, processing facility/route, and accepted/inducted/sorted/dispatched/delivered/undeliverable state. A consumer tracking, reroute, carrier handoff, or warehouse pick goal remains in its existing domain.

## Primary-source plan

Implementation must pin **exactly 48 primary-source slots: four independently identified official artifacts per domain**. A slot may be a regulation, official operating manual, official data standard, or first-party program guide. Secondary explainers, vendor help centers, search snippets, app screenshots, and independent evaluation data are ineligible. Each stored source record must include publisher, exact title, canonical URL, retrieval timestamp, HTTP status, content hash where retrievable, supported roles/assets/states, and the terminal IDs it supports.

| Domain | Four planned official source families |
|---|---|
| `clinical_diagnostic_lab_ops` | CMS CLIA program guidance; eCFR 42 CFR Part 493; CDC laboratory quality/CLIAC material; FDA laboratory test and reporting requirements |
| `perioperative_surgical_ops` | eCFR hospital surgical-service conditions; CMS State Operations Manual surgical guidance; CDC NHSN surgical-site material; FDA UDI/implant traceability material |
| `healthcare_revenue_cycle_ops` | CMS HIPAA administrative simplification; eCFR 45 CFR Part 162; CMS Medicare Claims Processing Manual; CMS remittance/appeal and prior-authorization program specifications |
| `mortgage_origination_servicing_ops` | CFPB Regulation X; CFPB Regulation Z; CFPB mortgage servicing/loss-mitigation guidance; an official Fannie Mae or Freddie Mac selling/servicing guide |
| `financial_crime_compliance_ops` | FinCEN Bank Secrecy Act material; eCFR Title 31 reporting rules; OFAC sanctions compliance guidance; FFIEC BSA/AML Examination Manual |
| `higher_education_student_admin` | U.S. Department of Education FERPA material; Federal Student Aid Handbook; Common Origination and Disbursement technical reference; NSLDS enrollment/aid reporting guidance |
| `human_subjects_research_oversight` | HHS OHRP 45 CFR 46 material; FDA 21 CFR Parts 50 and 56; OHRP single-IRB/reliance guidance; FDA safety-reporting and continuing-review guidance |
| `emergency_communications_dispatch` | National 911 Program resources; FCC 911/location rules; FEMA NIMS communications/resource guidance; NHTSA EMS communications/dispatch guidance |
| `public_health_surveillance_ops` | CDC NNDSS program guidance; CDC national case definitions; CDC outbreak investigation guidance; eCFR communicable-disease reporting/control authority relevant to the scoped jurisdiction |
| `power_generation_plant_ops` | FERC reliability/operations material; NERC reliability standards; EPA power-sector emissions reporting rules; EIA power-plant operations and fuel reporting instructions |
| `land_title_recording_admin` | BLM land-records/MLRS guidance; eCFR public-land record rules; one state or territorial recorder's official instrument/indexing rules; that jurisdiction's official plat and certified-copy rules |
| `postal_network_operations` | USPS Domestic Mail Manual; USPS Postal Operations Manual; USPS Publication 32 terminology; USPS official accountable-mail, forwarding, and claims manuals |

Source acceptance is jurisdiction-aware. A federal source cannot silently stand in for a state recorder, local public-health office, institution-specific registrar, or non-U.S. regime. Terminals whose authority varies by jurisdiction must carry an explicit jurisdiction qualifier, and the resolver must abstain when it is missing. Implementation may replace a planned source family only with a primary authority of equal or higher specificity; it may not reduce the four-slot count.

## Safety policy

1. **Navigation only.** The agent identifies and explains the destination, then stops before the final control. It never submits, signs, approves, validates, dispatches, releases, records, posts, files, closes, changes a setpoint, or performs an equivalent voice/keyboard action.
2. **All terminals are user-owned.** `never_auto + before_action + user_owned_final_press` is invariant for all 240 terminals, including the 84 read-only destinations. A read-only screen can expose clinical, education, financial, law-enforcement, or public-health data and is therefore high risk.
3. **Identity and scope checks.** Before recommending a terminal, resolve at least two of `authorized role`, `governed asset`, `jurisdiction/facility`, and `lifecycle state`; all consequential destinations require role plus asset plus current state. Do not infer authority from a visible button.
4. **Fail closed.** Stop at the hub on wrong or ambiguous person, patient, borrower, student, protocol, call, incident, jurisdiction, parcel, account, instrument, mailpiece, plant, or operational unit; also stop on stale/offline data, missing consent, missing approval, hold, lock, interlock, emergency control, permission denial, or disabled/unavailable controls.
5. **No operational advice.** Navigation output must not become diagnosis, treatment, dispatch triage, investment/credit/legal advice, sanctions disposition, emergency instruction, plant operating instruction, or a substitute for a regulated professional's judgment.
6. **Least disclosure.** Goal resolution and telemetry must avoid copying protected health, student, financial, investigative, caller-location, or title-record data beyond the minimum discriminator. Logs use synthetic or redacted identifiers.
7. **No bypass.** Never select an alternate control to evade dual review, segregation of duties, legal/clinical/quality hold, dispatch protocol, safety interlock, jurisdictional restriction, or unavailable state.

## Duplication and collision audit

The proposed IDs were checked against all 2,362 v13 function IDs and 2,180 v13 intent IDs. The exact-string audit result is **0 function-ID collisions, 0 intent-ID collisions, and 0 domain-ID collisions**. Exact uniqueness is necessary but not sufficient; implementation must repeat the following audit after materialization:

1. Normalize every existing and proposed Korean/English name, alias, pattern, and positive/negative context using Unicode normalization, case folding, punctuation removal, token singularization, and controlled synonym expansion.
2. Build a semantic signature for every terminal: `actor role + governed asset + lifecycle transition/state + jurisdiction/facility + consequence`. Reject a v14 terminal if a v13 terminal has the same actor, asset, state/transition, and consequence even when the words differ.
3. Compare every proposal against the nearest existing domain named in its section. Shared verbs such as `approve`, `issue`, `release`, `record`, `dispatch`, `close`, `case`, `claim`, `result`, `order`, `unit`, `hold`, and `status` require two independent domain discriminators in positive context and the nearest rival in negative context.
4. Run bidirectional retrieval probes: each v14 goal against v13+v14, and each nearest v13 goal against v13+v14. A proposal fails if it steals a prior goal, resolves from a bare shared noun/verb, or depends on an app/vendor name.
5. Produce a machine-readable collision report keyed by proposed terminal ID with exact-match, token-overlap, nearest-neighbor, and role-asset-state findings. Acceptance requires no unresolved `same_goal`, `same_transition`, or `unsafe_alias` finding.
6. Recompute catalog counts and ID sets from the built payload rather than trusting constants. The source document hash must be pinned before generation; evaluation artifacts must not be imported by the generator.

The hardest planned contrast families are: diagnostic specimen vs research sample vs blood component; surgical case vs court/insurance/public-health case; provider claim vs insurer claim; mortgage payment vs rent/general loan repayment; sanctions alert vs SOC/on-call alert; student application vs job/property/benefit application; IRB approval vs trial-site/grant/lab approval; CAD dispatch vs field-response/utility/gig dispatch; surveillance case vs care/social-service case; generating unit vs nuclear/grid/UI unit; recording instrument vs court filing/document; and postal induction/handoff vs warehouse/courier/freight handoff.

## Independent evaluation design

The v14 evaluation set must be authored and sealed by a reviewer who cannot inspect generator aliases, patterns, collision probes, or source-code constants. It is created only after the catalog is frozen and is never imported by a source module. The exact design is **960 cases**:

| Slice | Cases | Construction |
|---|---:|---|
| Positive Korean goals | 240 | One independently written Korean goal per terminal |
| Positive English goals | 240 | One independently written English goal per terminal; not a translation of the Korean item |
| Prior-catalog collision goals | 240 | Twenty nearest-rival v13 goals per proposed domain, balanced across the contrast families above |
| Within-v14 collision goals | 120 | Ten goals per domain whose shared verb/noun targets another v14 domain unless role/asset/state is used |
| Underspecified/unsafe abstention goals | 120 | Ten per domain with a missing identity, role, asset, jurisdiction, current state, or required authority |
| **Total** | **960** | **480 positive routing + 360 collision + 120 abstention** |

The evaluator reports top-1 and top-3 routing by locale/domain/class, abstention accuracy, v13 regression, unsafe cross-domain routing, and safety metadata. No case may contain a package name, resource ID, coordinate, screenshot-derived label, fixed click path, exact catalog alias sentence, or official-source sentence copied verbatim.

## Implementation acceptance criteria

V14 is accepted only when all of the following are true:

- The payload adds exactly 12 domains, 252 functions, and 240 intents; totals become exactly 167 domains, 2,614 functions, and 2,420 intents/terminal functions.
- Every domain has one low-risk hub, exactly 7 `S` terminals, exactly 13 `C` terminals, and exactly 20 one-to-one intent mappings. There are exactly 12 low-risk new hubs, 84 high-risk read-only terminals, and 156 high-risk state-changing terminals.
- All 240 terminal functions have `risk_level=high`, `automation_policy=never_auto`, `stop_policy=before_action`, and `user_owned_final_press=true`; all 156 `C` functions have `state_changing=true`, all 84 `S` functions have `state_changing=false`, and no terminal has a safe-navigation path through a final action.
- Exactly 48 accepted primary-source records are pinned, four per domain, with complete provenance and role/asset/state coverage. Every terminal cites at least one accepted source; every `C` terminal cites a source that supports its authority and lifecycle transition, not merely domain vocabulary.
- Exact uniqueness is 100%; the semantic duplication report has zero unresolved `same_goal`, `same_transition`, or `unsafe_alias` findings; and all prior catalog functions/intents remain byte-for-byte unchanged except for permitted catalog-version and append-only metadata.
- Independent positives achieve **top-1 ≥ 94% overall in each locale**, **top-1 ≥ 85% in every domain/class/locale cell**, and **top-3 ≥ 98.5% overall**. No cell may be omitted because of zero support.
- At least **98%** of the 360 collision goals retain their intended prior/v14 rival; v14 false capture of prior-catalog goals is **≤ 2% overall and ≤ 5% per domain**.
- At least **95%** of the 120 underspecified/unsafe cases abstain or stop at the correct hub. There are **zero** cases where an underspecified goal resolves to a `C` terminal, **zero** automated final actions, and **zero** wrong-person/wrong-asset/wrong-jurisdiction consequential recommendations.
- The full existing catalog-quality, alias, goal-robustness, independent-coverage, and performance suites pass without relaxing thresholds. Generation is deterministic from the pinned audit and primary-source metadata, and two clean builds produce identical function/intent payload hashes.

## Audit limits

This document establishes a source-level coverage plan, not proof that any particular app exposes these destinations or that the resolver can find them on a real screen. It intentionally creates no fixture and makes no claim about independent accuracy. Product/vendor UI research, jurisdiction-specific source collection, implementation, source hashing, collision-probe generation, sealed evaluation authoring, and real-device validation remain separate follow-on work.
