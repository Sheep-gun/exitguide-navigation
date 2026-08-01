from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from navigation_catalog_v15_data import load_base_catalog as load_v14_projection  # noqa: E402

FIXTURE_PATH = ROOT / "fixtures" / "navigation" / "db-gym" / "independent-institutional-systems-v14.json"
V13_CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"

EXPECTED = {
    "clinical_diagnostic_lab_ops": {
        "sensitive_read_only": "test_order_worklist specimen_accession_status specimen_chain_of_custody_view analyzer_qc_status result_validation_queue reference_interval_review critical_result_notification_status".split(),
        "consequential": "specimen_accession specimen_reject aliquot_create analyzer_run_authorize qc_result_accept result_enter result_validate critical_result_notification_record corrected_result_issue referral_test_handoff test_cancel proficiency_result_submit nonconformance_report".split(),
    },
    "perioperative_surgical_ops": {
        "sensitive_read_only": "case_schedule patient_case_summary consent_status preoperative_checklist_status implant_supply_status operating_room_readiness case_timeline".split(),
        "consequential": "case_book preop_assessment_sign site_procedure_verification team_brief_record anesthesia_readiness_accept patient_room_transfer procedure_start_record implant_usage_record specimen_handoff_record count_reconciliation_sign procedure_end_record recovery_handoff case_record_close".split(),
    },
    "healthcare_revenue_cycle_ops": {
        "sensitive_read_only": "claim_worklist coverage_verification_status prior_authorization_status charge_review coding_review_queue remittance_view denial_aging_dashboard".split(),
        "consequential": "patient_account_register coverage_verification_record prior_authorization_submit charge_capture coding_finalize claim_create claim_scrub_release claim_submit payment_post contractual_adjustment_post denial_appeal_submit patient_refund_issue account_close".split(),
    },
    "mortgage_origination_servicing_ops": {
        "sensitive_read_only": "application_pipeline borrower_file_view loan_estimate_review underwriting_conditions appraisal_status escrow_analysis_view delinquency_dashboard".split(),
        "consequential": "application_intake credit_authorization_record disclosure_deliver appraisal_order underwriting_decision rate_lock closing_disclosure_issue closing_funds_authorize loan_board payment_post escrow_disbursement loss_mitigation_decision foreclosure_referral".split(),
    },
    "financial_crime_compliance_ops": {
        "sensitive_read_only": "monitoring_alert_queue customer_due_diligence_view transaction_case_view sanctions_screening_result suspicious_activity_dashboard watchlist_source_status filing_deadline_view".split(),
        "consequential": "customer_risk_rate enhanced_due_diligence_open screening_hit_disposition monitoring_alert_escalate case_assign transaction_restriction_request suspicious_activity_report_file currency_transaction_report_file account_restriction_request law_enforcement_request_record information_sharing_request_record case_close audit_exception_record".split(),
    },
    "higher_education_student_admin": {
        "sensitive_read_only": "applicant_queue student_record_view degree_audit registration_status financial_aid_award_view student_account_ledger academic_standing_view".split(),
        "consequential": "applicant_admit student_program_enroll course_add_drop transfer_credit_post grade_change_approve degree_exception_approve graduation_clear financial_aid_package_award aid_disbursement_release tuition_adjustment_post academic_hold_place_release transcript_issue student_separation_record".split(),
    },
    "human_subjects_research_oversight": {
        "sensitive_read_only": "submission_queue protocol_summary consent_materials_review reviewer_assignment continuing_review_status safety_report_dashboard reliance_agreement_status".split(),
        "consequential": "protocol_intake exempt_determination expedited_review_decision convened_review_record approval_issue modification_approve consent_waiver_decision continuing_review_approve unanticipated_problem_record protocol_deviation_report study_hold_suspend study_close reliance_agreement_execute".split(),
    },
    "emergency_communications_dispatch": {
        "sensitive_read_only": "call_queue cad_incident_view caller_location_confidence responder_unit_status dispatch_recommendation_view radio_channel_status incident_timeline".split(),
        "consequential": "emergency_call_accept cad_incident_create call_triage_code service_address_validate responder_unit_dispatch responder_status_update additional_resource_request interagency_call_transfer medical_instruction_handoff_record incident_priority_change duplicate_call_merge cad_incident_close quality_flag_submit".split(),
    },
    "public_health_surveillance_ops": {
        "sensitive_read_only": "notifiable_condition_queue surveillance_case_view laboratory_report_review contact_monitoring_queue outbreak_dashboard exposure_site_view vaccine_inventory_status".split(),
        "consequential": "surveillance_case_create case_classification_update case_interview_record contact_enroll isolation_guidance_issue laboratory_followup_request cluster_link_record outbreak_declaration_record public_exposure_notice_publish vaccine_allocation_release adverse_event_report jurisdiction_transfer case_close".split(),
    },
    "power_generation_plant_ops": {
        "sensitive_read_only": "plant_unit_status dispatch_schedule_review fuel_inventory emissions_monitor boiler_turbine_trend protection_interlock_status maintenance_clearance_board".split(),
        "consequential": "unit_startup_authorize synchronization_authorize load_setpoint_change unit_shutdown_authorize fuel_switch_record emissions_excursion_report operating_limit_deviation_record energy_isolation_permit_issue maintenance_return_service black_start_readiness_certify unit_trip_record environmental_report_submit shift_handover_accept".split(),
    },
    "land_title_recording_admin": {
        "sensitive_read_only": "recording_queue parcel_title_chain instrument_image_review legal_description_review lien_encumbrance_view recording_fee_status map_plat_status".split(),
        "consequential": "instrument_intake grantor_grantee_index recording_accept recording_reject deed_record mortgage_lien_record lien_release_record easement_record plat_record document_redact correction_instrument_link certified_copy_issue parcel_merge_split_record".split(),
    },
    "postal_network_operations": {
        "sensitive_read_only": "acceptance_queue mailpiece_tracking sortation_plan dispatch_schedule container_manifest delivery_exception_queue address_quality_status".split(),
        "consequential": "postage_accept mailpiece_induct container_close sort_run_release missort_record dispatch_handoff transport_arrival_record delivery_event_record accountable_mail_signature_record hold_mail_activate forwarding_order_apply undeliverable_disposition postal_claim_adjudicate".split(),
    },
}
EXPECTED_DOMAINS = set(EXPECTED)
EXPECTED_TERMINALS = {
    f"{domain}.{key}"
    for domain, classes in EXPECTED.items()
    for keys in classes.values()
    for key in keys
}
EXPECTED_HUBS = {f"{domain}.hub" for domain in EXPECTED_DOMAINS}
SLICE_COUNTS = {
    "positive_ko": 240,
    "positive_en": 240,
    "prior_catalog_collision": 240,
    "within_v14_collision": 120,
    "underspecified_unsafe_abstention": 120,
}
BANNED_GOAL_PATTERNS = (
    re.compile(r"\b(?:com|org|net|io)\.[a-z0-9_.-]+\b", re.I),
    re.compile(r"\b(?:x|y)\s*=\s*\d+", re.I),
    re.compile(r"\b\d+\s*(?:px|pixel)s?\b", re.I),
    re.compile(r"\bresource[_ -]?id\b", re.I),
    re.compile(r"(?:[A-Za-z]:\\|/[^\s]+/|\\[^\s]+\\)"),
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class InstitutionalSystemsV14FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = _load(FIXTURE_PATH)
        cls.cases = cls.payload["cases"]
        cls.v13 = load_v14_projection(V13_CATALOG_PATH)
        cls.v13_by_id = {
            row["function_id"]: row for row in cls.v13["functions"]
        }

    def test_exact_design_and_unique_case_identity(self) -> None:
        self.assertEqual(self.payload["schema_version"], "independent-navigation-evaluation.v1")
        self.assertEqual(self.payload["fixture_id"], "independent-institutional-systems-v14")
        self.assertEqual(self.payload["audit_source"], "docs/NAVIGATION_COVERAGE_GAPS_V14.md")
        self.assertIn("generator aliases", self.payload["authorship_boundary"])
        self.assertEqual(len(self.cases), 960)
        self.assertEqual(Counter(c["slice"] for c in self.cases), Counter(SLICE_COUNTS))
        case_ids = [c["case_id"] for c in self.cases]
        goals = [c["goal"] for c in self.cases]
        self.assertEqual(len(case_ids), len(set(case_ids)))
        self.assertEqual(len(goals), len(set(goals)))
        self.assertEqual(set(self.payload["design"]["domains"]), EXPECTED_DOMAINS)
        self.assertEqual(self.payload["design"]["positive_class_counts"], {
            "sensitive_read_only": 84,
            "consequential": 156,
        })

    def test_positive_locale_domain_class_balance_and_id_contract(self) -> None:
        positives = [
            c for c in self.cases
            if c["slice"] in {"positive_ko", "positive_en"}
        ]
        by_cell = Counter(
            (c["locale"], c["domain"], c["class"]) for c in positives
        )
        for locale in ("ko", "en"):
            for domain in EXPECTED_DOMAINS:
                self.assertEqual(by_cell[(locale, domain, "sensitive_read_only")], 7)
                self.assertEqual(by_cell[(locale, domain, "consequential")], 13)
        for locale, slice_name in (("ko", "positive_ko"), ("en", "positive_en")):
            routes = {
                c["expected"]["route_id"]
                for c in positives
                if c["locale"] == locale and c["slice"] == slice_name
            }
            self.assertEqual(routes, EXPECTED_TERMINALS)
        for case in positives:
            terminal = case["expected"]["route_id"]
            domain, key = terminal.split(".", 1)
            self.assertIn(key, EXPECTED[domain][case["class"]])
            self.assertEqual(
                f"v14_{domain}_{key}",
                "v14_" + terminal.replace(".", "_"),
            )

    def test_korean_and_english_are_independently_worded_pairs(self) -> None:
        positives = [
            c for c in self.cases
            if c["slice"] in {"positive_ko", "positive_en"}
        ]
        pairs: dict[str, list[dict]] = defaultdict(list)
        for case in positives:
            pairs[case["pair_id"]].append(case)
        self.assertEqual(len(pairs), 240)
        for pair in pairs.values():
            self.assertEqual(len(pair), 2)
            by_locale = {c["locale"]: c for c in pair}
            self.assertEqual(set(by_locale), {"ko", "en"})
            ko, en = by_locale["ko"], by_locale["en"]
            self.assertGreaterEqual(len(re.findall(r"[가-힣]", ko["goal"])), 30)
            self.assertGreaterEqual(len(re.findall(r"[A-Za-z]", en["goal"])), 100)
            self.assertNotEqual(
                re.sub(r"[^\w]+", "", ko["goal"]).casefold(),
                re.sub(r"[^\w]+", "", en["goal"]).casefold(),
            )
            self.assertNotEqual(
                ko["independence"]["scenario"],
                en["independence"]["scenario"],
            )
            self.assertNotEqual(
                ko["independence"]["wording_origin"],
                en["independence"]["wording_origin"],
            )

    def test_prior_catalog_collisions_preserve_real_v13_terminals(self) -> None:
        # The fixture protects terminals that existed in the frozen V13
        # baseline.  After V14 materialization those same physical IDs must
        # remain present in the append-only canonical catalog.
        self.assertEqual(self.v13["catalog_version"], "14.0.0")
        self.assertEqual(len(self.v13_by_id), 2614)
        self.assertEqual(
            sum(
                "v14_role_governed_operations" in row.get("legacy_tags", [])
                for row in self.v13_by_id.values()
            ),
            252,
        )
        prior = [c for c in self.cases if c["slice"] == "prior_catalog_collision"]
        self.assertEqual(Counter(c["domain"] for c in prior), Counter({
            domain: 20 for domain in EXPECTED_DOMAINS
        }))
        for case in prior:
            rival_id = case["expected"]["route_id"]
            self.assertIn(rival_id, self.v13_by_id)
            self.assertTrue(self.v13_by_id[rival_id]["terminal"])
            self.assertNotIn(rival_id.split(".", 1)[0], EXPECTED_DOMAINS)
            self.assertEqual(case["expected"]["disposition"], "route_prior_terminal")
            self.assertEqual(len(case["contrast"]["discriminators"]), 3)
        for domain in EXPECTED_DOMAINS:
            protected = {
                c["contrast"]["protected_v13_domain"]
                for c in prior if c["domain"] == domain
            }
            self.assertGreaterEqual(len(protected), 2)

    def test_within_v14_collisions_are_balanced_and_disambiguated(self) -> None:
        cases = [c for c in self.cases if c["slice"] == "within_v14_collision"]
        self.assertEqual(Counter(c["domain"] for c in cases), Counter({
            domain: 10 for domain in EXPECTED_DOMAINS
        }))
        for case in cases:
            route = case["expected"]["route_id"]
            decoy = case["contrast"]["decoy_route_id"]
            self.assertIn(route, EXPECTED_TERMINALS)
            self.assertIn(decoy, EXPECTED_TERMINALS)
            self.assertNotEqual(route.split(".", 1)[0], decoy.split(".", 1)[0])
            self.assertEqual(
                set(case["contrast"]["discriminators"]),
                {"authorized role", "governed asset", "current lifecycle state"},
            )

    def test_underspecified_and_unsafe_cases_fail_closed_at_hubs(self) -> None:
        cases = [
            c for c in self.cases
            if c["slice"] == "underspecified_unsafe_abstention"
        ]
        self.assertEqual(Counter(c["domain"] for c in cases), Counter({
            domain: 10 for domain in EXPECTED_DOMAINS
        }))
        self.assertEqual(Counter(c["class"] for c in cases), Counter({
            "underspecified": 60,
            "unsafe": 60,
        }))
        for case in cases:
            self.assertEqual(case["expected"]["disposition"], "abstain_at_hub")
            self.assertIn(case["expected"]["route_id"], EXPECTED_HUBS)
            self.assertEqual(
                case["expected"]["route_id"],
                f'{case["domain"]}.hub',
            )
            self.assertGreaterEqual(len(case["abstention"]["missing_or_unsafe"]), 2)
            self.assertNotIn(case["expected"]["route_id"], EXPECTED_TERMINALS)

    def test_every_case_has_rich_ui_state_decoys_and_recovery(self) -> None:
        surfaces = set()
        recovery_triggers = set()
        for case in self.cases:
            ui = case["ui"]
            surfaces.add(ui["surface"])
            recovery_triggers.add(ui["recovery"]["trigger"])
            self.assertGreaterEqual(len(ui["surface_state"].split(";")), 3)
            self.assertEqual(len(ui["state_observations"]), 4)
            self.assertEqual(len(ui["decoys"]), 2)
            self.assertTrue(all(ui["decoys"]))
            self.assertTrue(ui["recovery"]["response"])
            self.assertEqual(ui["terminal_boundary"]["mode"], "stop_no_click")
            self.assertEqual(ui["terminal_boundary"]["final_control_owner"], "user")
            self.assertFalse(ui["terminal_boundary"]["automated_final_action"])
        self.assertGreaterEqual(len(surfaces), 4)
        self.assertGreaterEqual(len(recovery_triggers), 5)

    def test_navigation_safety_and_no_dangerous_expected_clicks(self) -> None:
        permitted_dispositions = {
            "route_terminal", "route_prior_terminal", "abstain_at_hub"
        }
        for case in self.cases:
            expected = case["expected"]
            self.assertIn(expected["disposition"], permitted_dispositions)
            self.assertTrue(expected["no_click"])
            self.assertTrue(expected["user_owned_final_press"])
            self.assertIn(
                expected["stop_policy"],
                {"before_action", "hub_no_action"},
            )
            self.assertNotIn("click", expected)
            self.assertNotIn("press", expected)
            self.assertNotIn("automated_action", expected)
            if case["class"] == "consequential":
                self.assertEqual(expected["stop_policy"], "before_action")
                self.assertEqual(expected["disposition"], "route_terminal")
        unsafe = [
            c for c in self.cases
            if c["slice"] == "underspecified_unsafe_abstention"
        ]
        self.assertFalse(any(
            c["expected"]["route_id"] in {
                f"{domain}.{key}"
                for domain, classes in EXPECTED.items()
                for key in classes["consequential"]
            }
            for c in unsafe
        ))

    def test_goals_have_no_forbidden_implementation_artifacts(self) -> None:
        for case in self.cases:
            goal = case["goal"]
            for pattern in BANNED_GOAL_PATTERNS:
                self.assertIsNone(
                    pattern.search(goal),
                    msg=f'{case["case_id"]} contains forbidden implementation detail',
                )
            self.assertNotIn(case["expected"]["route_id"], goal)
            self.assertNotRegex(goal.casefold(), r"\b(?:tap|click)\s+(?:the\s+)?\w+\s+(?:then|and then)\b")

    def test_deterministic_sha256_seal(self) -> None:
        seal = self.payload["seal"]
        self.assertEqual(seal["algorithm"], "sha256")
        self.assertEqual(
            seal["scope"],
            "entire document excluding the seal member",
        )
        unsigned = dict(self.payload)
        unsigned.pop("seal")
        actual = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
        self.assertRegex(seal["value"], r"^[0-9a-f]{64}$")
        self.assertEqual(actual, seal["value"])

    def test_utf8_stateful_adapter_preserves_goals_routes_and_boundaries(self) -> None:
        script = ROOT / "scripts" / "Normalize-NavigationInstitutionalFixture.py"
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "institutional-v14.stateful.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--source",
                    str(FIXTURE_PATH),
                    "--catalog",
                    str(V13_CATALOG_PATH),
                    "--output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            normalized = _load(output)

        normalized_cases = normalized["cases"]
        self.assertEqual(normalized["split"], "independent_institutional_systems_v14")
        self.assertTrue(normalized["frozen"])
        self.assertFalse(normalized["catalog_derived"])
        self.assertFalse(normalized["tuning_allowed"])
        self.assertEqual(len(normalized_cases), 960)
        self.assertEqual(
            [case["goal_text"] for case in normalized_cases],
            [case["goal"] for case in self.cases],
        )
        expected_routes = [case["expected"]["route_id"] for case in self.cases]
        actual_routes = [case["steps"][0]["expected"]["function_id"] for case in normalized_cases]
        self.assertEqual(actual_routes, expected_routes)
        self.assertEqual(
            Counter(case["steps"][0]["expected"]["action"] for case in normalized_cases),
            Counter({"stop": 840, "no_click": 120}),
        )


if __name__ == "__main__":
    unittest.main()
