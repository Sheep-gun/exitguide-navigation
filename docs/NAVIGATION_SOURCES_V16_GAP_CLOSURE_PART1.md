# Navigation V16 official-source gap closure — Part 1

Verification date: **2026-07-30**
Scope: the **6 source-gap categories / 7 terminals** identified in `NAVIGATION_SOURCES_V16_PART1.md`
Evidence policy: official first-party agency publications, current SEC forms and Commission rule releases, and the official U.S. CFR repository only

## Scope boundary and status rules

This closure audit is limited to the following terminals:

1. `occupational_safety_case_ops.safety_program_audit_status`
2. `food_manufacturing_recall_ops.product_complaint_signal_queue`
3. `public_company_sec_reporting_ops.filing_calendar`
4. `public_company_sec_reporting_ops.disclosure_controls_status`
5. `public_company_sec_reporting_ops.beneficial_ownership_report_file`
6. `public_company_sec_reporting_ops.insider_transaction_report_file`
7. `public_company_sec_reporting_ops.confidential_treatment_request`

No independent fixture, answer, failure, evaluation, or implementation surface was inspected. No product UI, package identifier, coordinate, menu path, or final-click authority is inferred from these sources.

Status meanings:

- `resolved`: current official evidence is sufficient to define the terminal's role, governed asset, lifecycle state, jurisdiction guard, and consequential transition. This does **not** mean a literal product screen exists.
- `partially_resolved`: official evidence supports a narrower ontology, but the terminal name or intended role still permits an unsupported broader interpretation.
- `unresolved`: the minimum ontology cannot be supported without speculation.

## Exact closure summary

| Gap category | Terminal count | `resolved` | `partially_resolved` | `unresolved` | Result |
|---|---:|---:|---:|---:|---|
| OSHA safety-program evaluation | 1 | 1 | 0 | 0 | Internal employer-program status is supportable; an OSHA enforcement case or mandatory audit is not. |
| FDA human-food complaint signals | 1 | 0 | 1 | 0 | FDA/HFP surveillance is supportable; a generic manufacturer complaint queue is not. |
| SEC filing calendar | 1 | 1 | 0 | 0 | Due state must be derived from filer class, form, period/event, and exceptions. |
| SEC disclosure controls | 1 | 1 | 0 | 0 | Management evaluation and disclosed effectiveness state are supportable. |
| SEC ownership reporting | 2 | 2 | 0 | 0 | Schedule 13D/G and Forms 3/4/5 require separate role and trigger guards. |
| SEC confidential treatment | 1 | 1 | 0 | 0 | Resolved only for the traditional Rule 406/24b-2 application branch. |
| **Total** | **7** | **6** | **1** | **0** | **All seven have official evidence; one remains intentionally narrow/partial.** |

## 1. `occupational_safety_case_ops.safety_program_audit_status`

**Status: `resolved` for internal employer-program ontology; not an OSHA enforcement-case terminal.**

Official source:

- [OSHA — Safety Management: Program Evaluation and Improvement](https://www.osha.gov/safety-management/program-evaluation)

Observed access on 2026-07-30:

- Direct HTTPS HTML retrieval succeeded on `osha.gov`.
- The page states that an established safety and health program should be evaluated initially and periodically, at least annually; employers, managers, supervisors, and workers participate; performance indicators and audit results are reviewed; shortcomings lead to corrective action and later monitoring.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | Employer is accountable; management/supervisors coordinate; workers participate in evaluation and improvement. |
| Asset | A workplace safety and health **program**, its core elements, goals, indicators, inspection/incident information, audit findings, and corrective actions. |
| State | `not_yet_evaluated`, `evaluation_due`, `evaluation_in_progress`, `operating_as_intended`, `shortcomings_identified`, `corrective_action_in_progress`, `monitoring_after_change`. These are ontology labels derived from the explicitly described lifecycle, not quoted UI labels. |
| Jurisdiction | OSHA Recommended Practices for covered U.S. workplaces. This is guidance, not a universal federal audit mandate; State Plan or industry-specific requirements need separate guards. |
| Transition | Establish program → initial verification → periodic/at-least-annual evaluation → identify shortcomings/opportunities → correct → monitor results. Changes in process/equipment, serious incidents, property damage, or increased safety complaints may trigger another evaluation. |

Evidence sufficiency and limits:

- The official page closes the earlier actor/asset/state boundary gap if the terminal is explicitly modeled as an **employer's internal program-evaluation status**.
- It does not establish a federal OSHA inspection case, citation state, certification, mandated audit frequency for every employer, or a government approval transition.
- No literal “audit status” button, dashboard, or third-party product workflow was observed. Product UI existence remains unverified.

## 2. `food_manufacturing_recall_ops.product_complaint_signal_queue`

**Status: `partially_resolved`.**

Official sources:

- [FDA — Human Foods Complaint System (HFCS)](https://www.fda.gov/food/compliance-enforcement-food/human-foods-complaint-system-hfcs)
- [FDA — What Happens When a Problem is Reported?](https://www.fda.gov/safety/questions-and-answers-problem-reporting/what-happens-when-problem-reported)

Observed access on 2026-07-30:

- Both `fda.gov` HTTPS pages returned direct HTML.
- HFCS is identified as an FDA database for adverse-event and product-complaint reports involving foods and dietary supplements. Reports are evaluated by Human Foods Program clinical reviewers to detect potential safety concerns; a potential concern leads to further evaluation and may lead to regulatory action, public communication, or market removal.
- FDA's problem-reporting page describes case seriousness assessment, jurisdiction screening, immediate investigation versus later facility-inspection follow-up, nationwide tracking, sample/lot investigation, and possible recall.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | FDA Human Foods Program clinical reviewer and FDA investigator; reporters include consumers, health professionals, industry, and mandatory dietary-supplement reporters. |
| Asset | HFCS complaint/adverse-event case, suspect/concomitant food or dietary-supplement product, report ID, reported symptoms/outcomes, manufacturer/facility, lot/sample, and follow-up information. |
| State | `received`, `coded_or_case_recorded`, `clinical_review`, `potential_safety_concern`, `further_evaluation`, `immediate_investigation`, `inspection_follow_up`, `regulatory_or_communication_action`, `no_causal_determination`. The last state is essential because inclusion in HFCS does not establish causation. |
| Jurisdiction | FDA-regulated foods and dietary supplements in the United States. Reports outside FDA jurisdiction route to another federal, state, or local authority. Mandatory manufacturer reporting described by HFCS is limited to qualifying serious dietary-supplement adverse events; ordinary food complaints are not thereby made mandatory. |
| Transition | Report received → jurisdiction/seriousness evaluation → clinical review → potential signal or no established signal → further evaluation/investigation → possible regulatory action, public communication, inspection follow-up, or recall. |

Evidence sufficiency and limits:

- The sources support a real **FDA/HFP internal safety-surveillance case flow** and therefore a complaint-signal destination at the ontology level.
- They do not prove a literal queue screen, queue ordering algorithm, button label, or public navigation surface.
- They also do not support generalizing this terminal to every food manufacturer's internal complaint-management system. If the catalog intends a manufacturer/quality-control role rather than FDA/HFP, it still needs a distinct authority and should remain out of materialization. Because the present terminal name does not encode that role boundary, the closure remains `partially_resolved`.

## 3. `public_company_sec_reporting_ops.filing_calendar`

**Status: `resolved` as a derived compliance state, not a static calendar screen.**

Official sources:

- [SEC — Form 10-K](https://www.sec.gov/files/form10-k.pdf)
- [SEC — Form 10-Q](https://www.sec.gov/files/form10-q.pdf)
- [SEC — Form 8-K](https://www.sec.gov/files/form8-k.pdf)

Observed access on 2026-07-30:

- All three current `sec.gov` PDFs were directly retrievable.
- Form 10-K identifies annual-report jurisdiction under Exchange Act Sections 13 or 15(d) and specifies 60 days for large accelerated filers, 75 days for accelerated filers, and 90 days for other registrants after fiscal year-end.
- Form 10-Q specifies 40 days after quarter-end for accelerated and large accelerated filers and 45 days for other registrants for the first three fiscal quarters.
- Form 8-K identifies event-based items and, unless otherwise specified, requires filing or furnishing within four business days after the triggering event, with form-specific exceptions.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | Exchange Act registrant/filer; filing responsibility is conditioned by the applicable form and filer classification. |
| Asset | Fiscal year/quarter, report form, reportable event, filer classification, calculated due date, filing or furnishing status, and applicable exception/extension. |
| State | `not_applicable`, `future`, `due_soon`, `due_today`, `submitted`, `late`, `extension_or_exception_pending`. These are calculated status labels; sources supply the legal inputs and deadlines. |
| Jurisdiction | U.S. Exchange Act reporting under Sections 13 or 15(d). Foreign private issuers, transition reports, asset-backed issuers, weekend/holiday handling, Form 12b-25 relief, and form-item exceptions require separate guards rather than a universal date. |
| Transition | Determine filer/form/event applicability → compute due date from period end or trigger → monitor due state → file/furnish or enter an authorized exception/extension path → accepted/late state. |

Evidence sufficiency and limits:

- The three current form instructions supply the minimum role, asset, timing, and transition inputs for a reliable calendar ontology.
- A single stored deadline is unsafe. The terminal must compute state from filer class, form, period/event, holidays, amendments, and exceptions.
- The sources do not establish a universal SEC “filing calendar” UI or guarantee that a private compliance product exposes the same status labels.

## 4. `public_company_sec_reporting_ops.disclosure_controls_status`

**Status: `resolved`.**

Official sources:

- [SEC Commission final rule — Certification of Disclosure in Companies' Quarterly and Annual Reports](https://www.sec.gov/files/rules/final/33-8124_0.htm)
- [SEC Commission final rule — Management's Report on Internal Control Over Financial Reporting and Certification of Disclosure](https://www.sec.gov/files/rules/final/33-8238.htm)

Observed access on 2026-07-30:

- Both `sec.gov` Commission rule-release HTML pages returned directly.
- The first release identifies issuers subject to Exchange Act Sections 13(a) or 15(d), assigns supervision and participation to principal executive and financial officers, and requires periodic evaluation of disclosure controls and procedures.
- The second release requires disclosure of those officers' conclusions about effectiveness as of the end of the report period, documentation supporting management's assessment, disclosure of material weaknesses for internal-control scope, and disclosure of materially affecting changes.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | Issuer management with participation/supervision of principal executive and principal financial officers or equivalent persons; certifying officers disclose conclusions. |
| Asset | Disclosure controls and procedures, information required in Exchange Act reports, evaluation evidence, effectiveness conclusion, and relevant control changes. Internal control over financial reporting is related but must remain a distinct asset. |
| State | `evaluation_due`, `evaluation_in_progress`, `effective`, `not_effective`, `change_under_review`, `material_change_identified`, `conclusion_disclosed`. Do not merge “material weakness” from internal-control reporting into disclosure-controls status without an explicit relationship. |
| Jurisdiction | Issuers filing reports under Exchange Act Sections 13(a) or 15(d), subject to the applicable form and issuer exclusions. |
| Transition | Maintain controls → management/officer evaluation for the reporting period → effectiveness conclusion → disclose conclusion in the periodic report → record material changes and support the assessment. |

Evidence sufficiency and limits:

- The rule releases establish the responsible roles, controlled asset, evaluation lifecycle, and effective/not-effective disclosure outcome.
- They do not prescribe one evaluation method or prove any vendor dashboard, status chip, or workflow screen.
- The terminal must distinguish disclosure controls from internal control over financial reporting even when one product presents them together.

## 5. `public_company_sec_reporting_ops.beneficial_ownership_report_file`

**Status: `resolved`, with mandatory Schedule 13D/13G role and intent guards.**

Official sources:

- [SEC Commission final rule — Modernization of Beneficial Ownership Reporting](https://www.sec.gov/files/rules/final/2023/33-11253.pdf)
- [SEC Division of Corporation Finance — Exchange Act Sections 13(d), 13(g), and Regulation 13D-G interpretations](https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/exchange-act-sections-13d-13g-regulation-13d-g-beneficial-ownership-reporting)

Observed access on 2026-07-30:

- The Commission's 295-page final-rule PDF and the current SEC interpretation page both returned directly.
- The rule release identifies covered classes, the greater-than-5% trigger, Schedule 13D and 13G filer categories, control intent, initial and amendment triggers, and revised deadlines. The current SEC interpretation page includes July 2025 updates and confirms, among other things, the five-business-day Schedule 13D deadline measured from the trade date in the described acquisition case.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | Beneficial owner/reporting person; Schedule 13D filer; qualified institutional investor, exempt investor, or passive investor eligible for a Schedule 13G branch. |
| Asset | Beneficial ownership percentage of a covered Section 12 class, voting/investment power, acquisition or involuntary change, control intent, filer category, Schedule 13D/13G, and amendment facts. |
| State | `below_threshold`, `threshold_crossed`, `form_type_determination`, `initial_due`, `filed`, `material_change`, `amendment_due`, `eligibility_lost_or_switched`, `reporting_ended`. |
| Jurisdiction | Exchange Act Sections 13(d) and 13(g), Regulation 13D-G, and a covered class registered under Section 12. Filer category and control intent are jurisdictional guards, not synonyms. |
| Transition | Cross covered threshold or otherwise incur obligation → determine 13D versus eligible 13G branch → calculate category-specific deadline → file → monitor material/threshold changes → amend, switch branch when permitted, or end reporting when the governing threshold/state allows. |

Evidence sufficiency and limits:

- The primary Commission release supplies the operative actor, threshold, intent, form, timing, and amendment transitions; the current first-party interpretation resolves edge-case meaning without replacing the rule.
- The terminal must not route solely from “more than 5%.” Control intent, acquisition circumstances, institutional/passive/exempt status, class registration, and current ownership state affect the proper branch.
- No fixed EDGAR menu path or final submission authorization is established.

## 6. `public_company_sec_reporting_ops.insider_transaction_report_file`

**Status: `resolved`, including the current 2026 foreign-private-issuer boundary.**

Official sources:

- [SEC — Form 3, March 2026 revision](https://www.sec.gov/files/form3.pdf)
- [SEC — Form 4, March 2026 revision](https://www.sec.gov/files/form4.pdf)
- [SEC — Form 5, March 2026 revision](https://www.sec.gov/files/form5.pdf)
- [SEC Commission final rule — Holding Foreign Insiders Accountable Act Disclosure](https://www.sec.gov/files/rules/final/2026/34-104903.pdf)

Observed access on 2026-07-30:

- All four current `sec.gov` PDFs were directly retrievable.
- Form 3 identifies directors, officers, qualifying greater-than-10% holders and other specified reporting persons, holdings assets, initial/amendment state, EDGAR submission, and a general 10-day initial deadline. Its March 2026 instructions include directors and officers of foreign private issuers while excluding the foreign-private-issuer 10% holder branch described in the form.
- Form 4 identifies changes in direct/indirect beneficial ownership, transaction dates/codes, derivative and non-derivative securities, and the end of the second business day following the executed transaction as the general deadline.
- Form 5 identifies annual/deferred reporting and a deadline on or before the 45th day after issuer fiscal year-end.
- The 2026 Commission final rule supplies the current foreign-private-issuer jurisdiction changes and form amendments.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | Director, officer, qualifying 10% beneficial owner, and other persons specifically covered by Form 3 instructions; current foreign-private-issuer officers/directors require the 2026 guard. |
| Asset | Issuer equity security, direct/indirect beneficial ownership, derivative security, initial holding, executed transaction, transaction code, year-end holding, amendment, and reporting-person status. |
| State | `reporting_person_event`, `form3_due_or_filed`, `transaction_triggered`, `form4_due_or_filed`, `deferred_or_annual_item`, `form5_due_or_filed`, `amendment_needed`, `exited_with_residual_obligation`. |
| Jurisdiction | Exchange Act Section 16(a), Section 12-registered classes, applicable Investment Company Act reporting, and the 2026 foreign-private-issuer amendments/exemptions. Form selection and exemptions require separate guards. |
| Transition | Become reporting person → Form 3 initial statement → execute/reportable ownership change → Form 4 → defer only eligible items to Form 5 → year-end Form 5 if required; amendments and post-exit residual obligations remain possible. |

Evidence sufficiency and limits:

- The current forms are direct filing instruments and contain the fields, actors, assets, timing, amendments, EDGAR destination, and lifecycle needed for this terminal.
- `beneficial_ownership_report_file` and `insider_transaction_report_file` must not be treated as aliases: the former is the Section 13(d)/(g) Schedule 13D/G regime; the latter is the Section 16 Forms 3/4/5 regime.
- The forms do not prove a fixed coordinate, menu path, or that an end user is authorized to sign for a reporting person.

## 7. `public_company_sec_reporting_ops.confidential_treatment_request`

**Status: `resolved` only when narrowed to the traditional Rule 406 / Rule 24b-2 application branch.**

Official sources:

- [GovInfo CFR 2025 — 17 CFR 230.406](https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol3/pdf/CFR-2025-title17-vol3-sec230-406.pdf)
- [GovInfo CFR 2025 — 17 CFR 240.24b-2](https://www.govinfo.gov/content/pkg/CFR-2025-title17-vol4/pdf/CFR-2025-title17-vol4-sec240-24b-2.pdf)
- [SEC Division of Corporation Finance — Confidential Treatment Applications under Rules 406 and 24b-2](https://www.sec.gov/rules-regulations/staff-guidance/disclosure-guidance/corpfinconfidential-treatment-applicationshtm)

Observed access on 2026-07-30:

- The official GovInfo Rule 406 PDF returned directly and exposed the written-objection, confidential portion, pending, grant, denial, withdrawal/release, revocation, review, and final-disposition lifecycle.
- The official GovInfo Rule 24b-2 section was retrieved with its CFR text through the government search surface. A subsequent direct fetch encountered a cache miss; the current normalized official PDF URL and section content were nevertheless established. The rule text identifies the objection/application contents, pending nondisclosure, sustain/disallow/revoke states, Commission review, and later public release.
- The SEC guidance page returned direct HTML, was last updated in 2024, distinguishes Securities Act Rule 406 from Exchange Act Rule 24b-2, describes applications typically involving material-contract exhibits, lists required application components, and explains grant/denial/expiration-extension paths. It expressly states that it is staff guidance rather than law, so the two CFR rules remain the authority.

Supported ontology:

| Dimension | Supported value boundary |
|---|---|
| Role | Person/company submitting filed information; applicant/objector; SEC Office of the Secretary; reviewing Division/Commission; exchange identification applies in the Rule 24b-2 branch. |
| Asset | Required filing, confidential portion/unredacted exhibit, redacted public exhibit, FOIA exemption analysis, requested duration, materiality/investor-protection explanation, consent, exchange list, application, and order. |
| State | `draft_application`, `submitted_pending`, `granted`, `denied`, `review_requested`, `withdrawn`, `expiring`, `extension_requested`, `revoked`, `public_release_due`, `finally_disposed`. |
| Jurisdiction | Rule 406 for information required in Securities Act filings; Rule 24b-2 for information filed under the Exchange Act. Supplemental information uses a different route, and modern redacted-exhibit rules may allow omission without a traditional application. |
| Transition | Select correct legal branch → file redacted material and separate confidential application materials → pending nondisclosure → grant or denial → possible review/withdrawal/public release → expiration, extension, reconsideration, or revocation. |

Evidence sufficiency and limits:

- The two rules provide exact actor, asset, application, pending, decision, review, release, and revocation semantics. The guidance supplies current operational distinctions without being treated as the source of legal authority.
- The terminal must ask which request type applies. It must not route every redacted exhibit, supplemental submission, Rule 83 request, or other confidentiality claim into Rule 406/24b-2.
- The traditional application flow includes paper/separate-material requirements in the cited sources; it is not evidence of a universal online “submit confidential treatment” screen.

## Product UI versus ontology conclusion

| Terminal | Ontology evidence | Literal product UI evidence |
|---|---|---|
| `safety_program_audit_status` | Sufficient only as internal employer program evaluation. | None; no OSHA case-status button or generic product dashboard proved. |
| `product_complaint_signal_queue` | Sufficient for FDA/HFP complaint surveillance, but not a generic manufacturer queue. | None; no public HFCS analyst queue or queue-ranking UI proved. |
| `filing_calendar` | Sufficient as a computed compliance state. | None; no universal calendar screen proved. |
| `disclosure_controls_status` | Sufficient for evaluation and disclosed conclusion. | None; no vendor status interface proved. |
| `beneficial_ownership_report_file` | Sufficient for Schedule 13D/G routing. | EDGAR is the filing destination, but no fixed menu path/coordinate is proved. |
| `insider_transaction_report_file` | Sufficient for Forms 3/4/5 routing. | EDGAR is the filing destination, but no fixed menu path/coordinate is proved. |
| `confidential_treatment_request` | Sufficient for the narrowed Rule 406/24b-2 branch. | No universal online workflow; cited procedures include separate/paper materials. |

## Normalized URL duplicate audit

Normalization rule: lowercase scheme and host; force HTTPS; remove default ports and fragments; preserve path and query semantics; remove a trailing slash only when it denotes the same resource.

- Terminal-to-source references: **17**
- Normalized official URLs: **17**
- Unique normalized URLs: **17**
- Duplicate references: **0**
- Cross-terminal URL reuse: **0**
- Retrieval outcomes: **16 direct successful page/PDF retrievals**, **1 official section retrieved through government search with a later direct-fetch cache miss** (`17 CFR 240.24b-2`)

Host distribution after normalization:

| Official host | Unique URLs |
|---|---:|
| `osha.gov` | 1 |
| `fda.gov` | 2 |
| `sec.gov` | 12 |
| `govinfo.gov` | 2 |
| **Total** | **17** |

## Materialization guard recommendation

Source closure alone is not permission to materialize an unsafe route. If these terminals are later admitted, retain the following guards:

- `safety_program_audit_status`: label as internal/voluntary program evaluation, never as an OSHA approval or mandatory universal audit.
- `product_complaint_signal_queue`: require `role=FDA_HFP_reviewer` or redesign/rename; do not expose as a generic manufacturer queue on the present evidence.
- `filing_calendar`: calculate from filer, form, period/event, and exception inputs; do not store one universal deadline.
- `disclosure_controls_status`: keep disclosure controls separate from internal control over financial reporting.
- `beneficial_ownership_report_file`: require Section 13(d)/(g) threshold, class, acquisition, filer-category, and control-intent guards.
- `insider_transaction_report_file`: require Section 16 role, issuer/class, form-trigger, current foreign-private-issuer, and exemption guards.
- `confidential_treatment_request`: require an explicit Rule 406 or Rule 24b-2 branch and distinguish modern redacted-exhibit and Rule 83 procedures.

The official sources establish domain ontology and provenance only. They do not authorize automated final filing, signing, certification, submission, or disclosure decisions.
