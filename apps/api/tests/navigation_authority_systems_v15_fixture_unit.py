from __future__ import annotations

import ast
import hashlib
import json
import re
import unicodedata
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "fixtures/navigation/db-gym/independent-authority-systems-v15.json"
COVERAGE_PATH = REPO_ROOT / "docs/NAVIGATION_COVERAGE_GAPS_V15.md"
CANONICAL_CATALOG_PATH = REPO_ROOT / "fixtures/navigation/function-catalog.v1.json"

EXPECTED_SLICES = {
    "positive_ko": 240,
    "positive_en": 240,
    "prior_catalog_collision": 240,
    "within_v15_collision": 120,
    "underspecified_unsafe_abstention": 120,
}

EXPECTED_PROJECTION = {
    "domains": 179,
    "physical_functions": 2866,
    "physical_terminal_functions": 2660,
    "physical_intents": 2660,
    "v15_append_domains": 12,
    "v15_append_functions": 252,
    "v15_append_terminals": 240,
    "v15_append_intents": 240,
}

EXPECTED_V15_DOMAINS = [
    "airport_airside_operations",
    "federal_records_disposition_ops",
    "doj_foia_case_processing",
    "dam_safety_operations",
    "nlrb_representation_case_ops",
    "special_education_program_admin",
    "pension_plan_administration",
    "campaign_finance_compliance",
    "export_control_authorization_ops",
    "broadcast_station_compliance",
    "app_store_release_management",
    "domain_registration_operations",
]

PRIOR_RIVAL_DOMAINS = {
    "airport_airside_operations": {
        "air_traffic_control_ops",
        "aviation_maintenance_ops",
        "emergency_response_operations",
    },
    "federal_records_disposition_ops": {
        "documents_cloud",
        "legal_practice_ops",
        "museum_collections_ops",
        "privacy",
    },
    "doj_foia_case_processing": {
        "customer_support_agent",
        "legal_practice_ops",
        "privacy",
        "court_clerk_case_admin",
    },
    "dam_safety_operations": {
        "water_wastewater_plant_ops",
        "power_generation_plant_ops",
        "utility_grid_field_ops",
    },
    "nlrb_representation_case_ops": {
        "court_clerk_case_admin",
        "election_administration",
        "hr_payroll",
        "legal_practice_ops",
    },
    "special_education_program_admin": {
        "education",
        "classroom_instructor_ops",
        "higher_education_student_admin",
        "social_services_casework",
    },
    "pension_plan_administration": {
        "hr_payroll",
        "finance_long_tail",
        "retail_banking",
        "business_accounting",
    },
    "campaign_finance_compliance": {
        "election_administration",
        "crowdfunding_donations",
        "business_accounting",
    },
    "export_control_authorization_ops": {
        "freight_forwarding_customs_ops",
        "financial_crime_compliance_ops",
        "procurement_supplier_ops",
    },
    "broadcast_station_compliance": {
        "content",
        "marketing",
        "emergency_communications_dispatch",
    },
    "app_store_release_management": {
        "app_store",
        "code_repository",
        "workspace_administration",
    },
    "domain_registration_operations": {
        "browser_web",
        "credential_vault",
        "subscription",
        "workspace_administration",
    },
}

UNSAFE_REASONS = {
    "missing_authority",
    "missing_asset_identity",
    "missing_jurisdiction",
    "missing_lifecycle_state",
    "missing_required_approval",
    "missing_consent",
    "pending_dual_review",
    "stale_or_offline_data",
    "active_legal_safety_quality_hold",
    "disabled_control_or_interlock",
}

DOC_ROW_RE = re.compile(
    r"^\| ([SC]) \| `([^`]+)` \| (.*?) / ([^|]+?) \| (.*?) / ([^|]+?) \|$",
    re.MULTILINE,
)
HANGUL_RE = re.compile(r"[가-힣]")
PACKAGE_OR_RESOURCE_ID_RE = re.compile(
    r"(?:\b(?:package|resource)[ _-]?id\b|\b[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}\b)",
    re.IGNORECASE,
)
FIXED_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\|/(?:data|android|ios|system)/|\b(?:tap|click|press)\b.{0,50}(?:then|>|→)|\b(?:menu|settings)\s*(?:>|→|/)\s*)",
    re.IGNORECASE,
)
COORDINATE_OR_SCREENSHOT_RE = re.compile(
    r"(?:\(\s*\d{1,4}\s*,\s*\d{1,4}\s*\)|\b(?:coordinate|pixel|screenshot-derived|screenshot label)\b)",
    re.IGNORECASE,
)
PROHIBITED_AUTHORING_ARTIFACT_RE = re.compile(
    r"(?:navigation[_-]?catalog[_-]?v15(?:[_-]?data)?|"
    r"\b(?:function|intent)[_-]?id\b|"
    r"\b(?:positive|negative)[_-]?context\b|"
    r"\bgoal[_ -]?rules?\b|"
    r"\b(?:alias|pattern)[_-]?(?:table|builder|generator)\b|"
    r"\bcollision[_ -]?probes?\b|"
    r"\bindependent[_ -]?(?:failure|accuracy)[_ -]?reports?\b)",
    re.IGNORECASE,
)
SOURCE_SENTENCE_LEAD_RE = re.compile(r"^(?:show|open|take me to)\b", re.IGNORECASE)
SOURCE_SENTENCE_KO_END_RE = re.compile(r"(?:보여|열어|가|확인해)\s*줘\s*$")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise AssertionError(f"expected object in {path}")
    return value


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in value if character.isalnum())


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _coverage_rows() -> list[dict[str, str]]:
    text = COVERAGE_PATH.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    for match in DOC_ROW_RE.finditer(text):
        function_id = match.group(2)
        rows.append(
            {
                "terminal_class": match.group(1),
                "function_id": function_id,
                "domain": function_id.split(".", 1)[0],
                "name_ko": match.group(3).strip(),
                "name_en": match.group(4).strip(),
                "source_goal_ko": match.group(5).strip(),
                "source_goal_en": match.group(6).strip(),
            }
        )
    return rows


class NavigationAuthoritySystemsV15FixtureUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_json(FIXTURE_PATH)
        cls.metadata = cls.fixture["metadata"]
        cls.cases = cls.fixture["cases"]
        cls.coverage_text = COVERAGE_PATH.read_text(encoding="utf-8")
        cls.doc_rows = _coverage_rows()
        cls.doc_by_id = {row["function_id"]: row for row in cls.doc_rows}

        # This deliberately projects only canonical identifiers and terminal/domain flags.
        # It never reads aliases, patterns, rules, sources, descriptions, or names.
        canonical = _load_json(CANONICAL_CATALOG_PATH)
        cls.catalog_version = canonical["catalog_version"]
        cls.canonical_functions = [
            {
                "function_id": item["function_id"],
                "domain": item["domain"],
                "terminal": bool(item["terminal"]),
            }
            for item in canonical["functions"]
        ]
        cls.canonical_intent_ids = [item["intent_id"] for item in canonical["intents"]]

    def test_frozen_schema_counts_and_canonical_seal(self) -> None:
        self.assertTrue(self.metadata["frozen"])
        self.assertEqual(self.metadata["schema_version"], "15.0.0-independent-evaluation.1")
        self.assertEqual(self.metadata["catalog_target_version"], "15.0.0")
        self.assertEqual(self.metadata["slice_contract"], EXPECTED_SLICES)
        self.assertEqual(self.metadata["projection"], EXPECTED_PROJECTION)
        self.assertEqual(len(self.cases), 960)
        self.assertEqual(Counter(case["slice"] for case in self.cases), Counter(EXPECTED_SLICES))

        payload = dict(self.fixture)
        seal = payload.pop("canonical_json_sha256")
        self.assertRegex(seal, r"^[0-9a-f]{64}$")
        recomputed = hashlib.sha256(_canonical_json(payload)).hexdigest()
        self.assertEqual(seal, recomputed)

    def test_authorship_boundary_is_exact_and_self_policing(self) -> None:
        authorship = self.metadata["authorship"]
        self.assertTrue(authorship["declared_independent"])
        self.assertEqual(
            [item["artifact"] for item in authorship["allowed_inputs"]],
            [
                "docs/NAVIGATION_COVERAGE_GAPS_V15.md",
                "fixtures/navigation/function-catalog.v1.json",
            ],
        )
        self.assertEqual(
            authorship["allowed_inputs"][1]["scope"],
            "function and intent identifiers only for prior-catalog rivals and collision checks",
        )
        expected_doc_sha = hashlib.sha256(COVERAGE_PATH.read_bytes()).hexdigest()
        self.assertEqual(authorship["allowed_inputs"][0]["sha256"], expected_doc_sha)
        self.assertEqual(authorship["allowed_inputs"][1]["catalog_version"], "14.0.0")
        self.assertEqual(
            set(authorship["excluded_inputs"]),
            {
                "catalog implementation modules",
                "alias and pattern tables",
                "goal-rule builders",
                "source paraphrase records",
                "probe definitions",
                "independent failure reports",
            },
        )

        # AST inspection catches an accidental future import/path read without importing any
        # implementation module itself. The guard is defined entirely by artifact-name patterns.
        source = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_module = re.compile(
            r"(?:^|\.)(?:navigation_catalog_v15(?:_data)?|navigation_catalog_v15_(?:aliases|patterns|rules|probes))(?:\.|$)"
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIsNone(forbidden_module.search(alias.name), alias.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertIsNone(forbidden_module.search(node.module or ""), node.module)
            elif isinstance(node, ast.Call) and node.args:
                called_name = ""
                if isinstance(node.func, ast.Name):
                    called_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    called_name = node.func.attr
                if called_name in {"open", "Path", "read_text", "read_bytes"}:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        self.assertIsNone(forbidden_module.search(first.value), first.value)

    def test_exact_document_ids_classes_and_domain_shape(self) -> None:
        self.assertEqual(len(self.doc_rows), 240)
        self.assertEqual(len(self.doc_by_id), 240)
        self.assertEqual(
            list(dict.fromkeys(row["domain"] for row in self.doc_rows)),
            EXPECTED_V15_DOMAINS,
        )
        self.assertEqual(
            self.metadata["identifier_contract"]["v15_domains"],
            EXPECTED_V15_DOMAINS,
        )

        for domain in EXPECTED_V15_DOMAINS:
            domain_rows = [row for row in self.doc_rows if row["domain"] == domain]
            self.assertEqual(len(domain_rows), 20, domain)
            self.assertEqual(Counter(row["terminal_class"] for row in domain_rows), {"S": 7, "C": 13})

        positives = [
            case
            for case in self.cases
            if case["slice"] in {"positive_ko", "positive_en"}
        ]
        self.assertEqual(Counter(case["expected"]["function_id"] for case in positives), Counter({item: 2 for item in self.doc_by_id}))
        for case in positives:
            expected = case["expected"]
            row = self.doc_by_id[expected["function_id"]]
            self.assertEqual(expected["domain"], row["domain"])
            self.assertEqual(expected["terminal_class"], row["terminal_class"])
            self.assertEqual(expected["decision"], "route")
            self.assertEqual(expected["acceptable_top3"], [expected["function_id"]])

        within = [case for case in self.cases if case["slice"] == "within_v15_collision"]
        for case in within:
            expected = case["expected"]
            row = self.doc_by_id[expected["function_id"]]
            self.assertEqual(expected["domain"], row["domain"])
            self.assertEqual(expected["terminal_class"], row["terminal_class"])
            self.assertIn(expected["decoy_function_id"], self.doc_by_id)
            self.assertEqual(
                expected["decoy_domain"],
                self.doc_by_id[expected["decoy_function_id"]]["domain"],
            )

    def test_future_v15_exact_projection_without_requiring_materialization(self) -> None:
        proposed_terminal_ids = set(self.doc_by_id)
        proposed_hub_ids = {f"{domain}.hub" for domain in EXPECTED_V15_DOMAINS}
        proposed_function_ids = proposed_terminal_ids | proposed_hub_ids
        proposed_intent_ids = {
            f"v15_{function_id.replace('.', '_')}" for function_id in proposed_terminal_ids
        }
        self.assertEqual(len(proposed_function_ids), 252)
        self.assertEqual(len(proposed_intent_ids), 240)

        all_function_ids = {item["function_id"] for item in self.canonical_functions}
        all_terminal_ids = {
            item["function_id"] for item in self.canonical_functions if item["terminal"]
        }
        all_intent_ids = set(self.canonical_intent_ids)

        if self.catalog_version == "14.0.0":
            baseline_function_ids = all_function_ids
            baseline_terminal_ids = all_terminal_ids
            baseline_intent_ids = all_intent_ids
            self.assertEqual(len(self.canonical_functions), 2614)
            self.assertEqual(len(all_terminal_ids), 2420)
            self.assertEqual(len(self.canonical_intent_ids), 2420)
            self.assertEqual({item["domain"] for item in self.canonical_functions}.__len__(), 167)
        elif self.catalog_version == "15.0.0":
            self.assertEqual(len(self.canonical_functions), 2866)
            self.assertEqual(len(all_terminal_ids), 2660)
            self.assertEqual(len(self.canonical_intent_ids), 2660)
            self.assertTrue(proposed_function_ids <= all_function_ids)
            self.assertTrue(proposed_terminal_ids <= all_terminal_ids)
            self.assertTrue(proposed_intent_ids <= all_intent_ids)
            baseline_function_ids = all_function_ids - proposed_function_ids
            baseline_terminal_ids = all_terminal_ids - proposed_terminal_ids
            baseline_intent_ids = all_intent_ids - proposed_intent_ids
        else:
            self.fail(f"expected canonical 14.0.0 baseline or 15.0.0 materialization, got {self.catalog_version}")

        self.assertEqual(len(baseline_function_ids), 2614)
        self.assertEqual(len(baseline_terminal_ids), 2420)
        self.assertEqual(len(baseline_intent_ids), 2420)
        self.assertTrue(baseline_function_ids.isdisjoint(proposed_function_ids))
        self.assertTrue(baseline_intent_ids.isdisjoint(proposed_intent_ids))
        self.assertEqual(len(baseline_function_ids | proposed_function_ids), 2866)
        self.assertEqual(len(baseline_terminal_ids | proposed_terminal_ids), 2660)
        self.assertEqual(len(baseline_intent_ids | proposed_intent_ids), 2660)

    def test_bilingual_pairs_are_independently_scenario_written(self) -> None:
        positive_ko = {
            case["pair_key"]: case for case in self.cases if case["slice"] == "positive_ko"
        }
        positive_en = {
            case["pair_key"]: case for case in self.cases if case["slice"] == "positive_en"
        }
        self.assertEqual(set(positive_ko), set(self.doc_by_id))
        self.assertEqual(set(positive_en), set(self.doc_by_id))

        normalized_goals = [_normalize(case["goal"]) for case in self.cases]
        self.assertEqual(len(set(normalized_goals)), 960)
        for function_id in self.doc_by_id:
            ko = positive_ko[function_id]
            en = positive_en[function_id]
            self.assertEqual(ko["locale"], "ko")
            self.assertEqual(en["locale"], "en")
            self.assertTrue(HANGUL_RE.search(ko["goal"]), function_id)
            self.assertFalse(HANGUL_RE.search(en["goal"]), function_id)
            self.assertEqual(ko["surface"]["scenario_axis"], "operational_recovery")
            self.assertEqual(en["surface"]["scenario_axis"], "evidence_audit")
            self.assertNotEqual(ko["surface"]["scenario_axis"], en["surface"]["scenario_axis"])
            self.assertNotEqual(_normalize(ko["goal"]), _normalize(en["goal"]))
            self.assertNotEqual(_normalize(ko["goal"]), _normalize(self.doc_by_id[function_id]["source_goal_ko"]))
            self.assertNotEqual(_normalize(en["goal"]), _normalize(self.doc_by_id[function_id]["source_goal_en"]))
            self.assertNotEqual(_normalize(ko["goal"]), _normalize(self.doc_by_id[function_id]["name_ko"]))
            self.assertNotEqual(_normalize(en["goal"]), _normalize(self.doc_by_id[function_id]["name_en"]))

        # English/Korean locale balance is exact in each non-positive slice too.
        for slice_name, per_locale in {
            "prior_catalog_collision": 120,
            "within_v15_collision": 60,
            "underspecified_unsafe_abstention": 60,
        }.items():
            cases = [case for case in self.cases if case["slice"] == slice_name]
            self.assertEqual(Counter(case["locale"] for case in cases), {"ko": per_locale, "en": per_locale})

    def test_case_disjointness_and_collision_balance(self) -> None:
        expected_case_ids = [f"v15-independent-{index:04d}" for index in range(1, 961)]
        self.assertEqual([case["case_id"] for case in self.cases], expected_case_ids)
        self.assertEqual(len({case["case_id"] for case in self.cases}), 960)
        for case in self.cases:
            if case["slice"].startswith("positive_"):
                self.assertIsNotNone(case["pair_key"])
            else:
                self.assertIsNone(case["pair_key"])

        baseline_terminal_ids = {
            item["function_id"]
            for item in self.canonical_functions
            if item["terminal"] and item["function_id"] not in self.doc_by_id
        }
        prior = [case for case in self.cases if case["slice"] == "prior_catalog_collision"]
        prior_target_ids = [case["expected"]["function_id"] for case in prior]
        self.assertEqual(len(set(prior_target_ids)), 240)
        self.assertTrue(set(prior_target_ids) <= baseline_terminal_ids)
        self.assertTrue(set(prior_target_ids).isdisjoint(self.doc_by_id))

        for decoy_domain in EXPECTED_V15_DOMAINS:
            domain_cases = [case for case in prior if case["expected"]["decoy_domain"] == decoy_domain]
            self.assertEqual(len(domain_cases), 20)
            self.assertEqual(Counter(case["locale"] for case in domain_cases), {"ko": 10, "en": 10})
            counts = Counter(case["expected"]["domain"] for case in domain_cases)
            self.assertEqual(set(counts), PRIOR_RIVAL_DOMAINS[decoy_domain])
            if decoy_domain == "broadcast_station_compliance":
                self.assertEqual(counts["marketing"], 1)
                self.assertLessEqual(abs(counts["content"] - counts["emergency_communications_dispatch"]), 1)
            else:
                self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
            for case in domain_cases:
                self.assertIn(case["expected"]["decoy_function_id"], self.doc_by_id)
                self.assertEqual(
                    self.doc_by_id[case["expected"]["decoy_function_id"]]["domain"],
                    decoy_domain,
                )

        within = [case for case in self.cases if case["slice"] == "within_v15_collision"]
        self.assertEqual(len({case["expected"]["function_id"] for case in within}), 120)
        self.assertEqual(Counter(case["expected"]["domain"] for case in within), Counter({domain: 10 for domain in EXPECTED_V15_DOMAINS}))
        self.assertEqual(Counter(case["expected"]["terminal_class"] for case in within), {"S": 57, "C": 63})
        for decoy_domain in EXPECTED_V15_DOMAINS:
            domain_cases = [case for case in within if case["expected"]["decoy_domain"] == decoy_domain]
            self.assertEqual(len(domain_cases), 10)
            self.assertEqual(Counter(case["locale"] for case in domain_cases), {"ko": 5, "en": 5})
            self.assertEqual(len({case["expected"]["domain"] for case in domain_cases}), 10)
            self.assertEqual(len({case["expected"]["decoy_function_id"] for case in domain_cases}), 10)
            for case in domain_cases:
                self.assertNotEqual(case["expected"]["domain"], decoy_domain)
                self.assertTrue(case["expected"]["shared_surface"])

    def test_role_asset_state_recovery_and_decoy_surfaces_are_rich(self) -> None:
        required_surface_fields = {
            "role",
            "asset",
            "state",
            "jurisdiction",
            "recovery",
            "decoy",
            "missing",
            "scenario_axis",
        }
        for case in self.cases:
            self.assertEqual(set(case["surface"]), required_surface_fields, case["case_id"])
            self.assertIsInstance(case["surface"]["missing"], list)
            self.assertTrue(case["surface"]["decoy"])

        fully_specified = [
            case
            for case in self.cases
            if case["slice"]
            in {"positive_ko", "positive_en", "prior_catalog_collision", "within_v15_collision"}
        ]
        for case in fully_specified:
            for field in ("role", "asset", "state", "jurisdiction", "recovery", "decoy"):
                self.assertTrue(case["surface"][field], f"{case['case_id']} lacks {field}")
            self.assertEqual(case["surface"]["missing"], [])

        positives = [case for case in self.cases if case["slice"].startswith("positive_")]
        for domain in EXPECTED_V15_DOMAINS:
            domain_cases = [case for case in positives if case["expected"]["domain"] == domain]
            for field, minimum in {
                "role": 6,
                "asset": 8,
                "state": 6,
                "jurisdiction": 4,
                "recovery": 8,
                "decoy": 6,
            }.items():
                self.assertGreaterEqual(len({case["surface"][field] for case in domain_cases}), minimum, f"{domain}/{field}")

    def test_underspecified_cases_abstain_for_every_guard(self) -> None:
        unsafe = [
            case
            for case in self.cases
            if case["slice"] == "underspecified_unsafe_abstention"
        ]
        consequential_ids = {
            row["function_id"]
            for row in self.doc_rows
            if row["terminal_class"] == "C"
        }
        self.assertEqual(len(consequential_ids), 156)
        for domain in EXPECTED_V15_DOMAINS:
            domain_cases = [
                case
                for case in unsafe
                if case["expected"]["safe_fallback_domain"] == domain
            ]
            self.assertEqual(len(domain_cases), 10)
            self.assertEqual(Counter(case["locale"] for case in domain_cases), {"ko": 5, "en": 5})
            self.assertEqual(
                {case["surface"]["missing"][0] for case in domain_cases},
                UNSAFE_REASONS,
            )
            self.assertEqual(len({case["expected"]["unsafe_candidate_id"] for case in domain_cases}), 10)
            for case in domain_cases:
                expected = case["expected"]
                reason = case["surface"]["missing"][0]
                self.assertEqual(expected["decision"], "abstain")
                self.assertIsNone(expected["function_id"])
                self.assertIsNone(expected["domain"])
                self.assertIsNone(expected["terminal_class"])
                self.assertEqual(expected["acceptable_top3"], [])
                self.assertEqual(expected["unsafe_candidate_class"], "C")
                self.assertIn(expected["unsafe_candidate_id"], consequential_ids)
                self.assertEqual(self.doc_by_id[expected["unsafe_candidate_id"]]["domain"], domain)
                if reason == "missing_authority":
                    self.assertIsNone(case["surface"]["role"])
                elif reason == "missing_asset_identity":
                    self.assertIsNone(case["surface"]["asset"])
                elif reason == "missing_jurisdiction":
                    self.assertIsNone(case["surface"]["jurisdiction"])
                elif reason == "missing_lifecycle_state":
                    self.assertIsNone(case["surface"]["state"])
                else:
                    self.assertIsNone(case["surface"]["recovery"])

    def test_final_action_safety_has_zero_dangerous_expected_clicks(self) -> None:
        contract = self.metadata["terminal_contract"]
        self.assertEqual(
            contract,
            {
                "sensitive_read_only": 84,
                "consequential": 156,
                "risk_level": "high",
                "automation_policy": "never_auto",
                "stop_policy": "before_action",
                "user_owned_final_press": True,
                "dangerous_expected_clicks": 0,
            },
        )
        for case in self.cases:
            expected = case["expected"]
            self.assertEqual(expected["dangerous_clicks"], 0, case["case_id"])
            self.assertEqual(expected["automated_final_presses"], 0, case["case_id"])
            self.assertEqual(expected["terminal_press_owner"], "user", case["case_id"])
            if expected["function_id"] in self.doc_by_id:
                self.assertEqual(expected["stop_policy"], "before_action")
            else:
                self.assertEqual(expected["stop_policy"], "navigation_only")

        routed_consequential = [
            case
            for case in self.cases
            if case["expected"]["function_id"] in self.doc_by_id
            and case["expected"]["terminal_class"] == "C"
        ]
        self.assertGreater(len(routed_consequential), 0)
        self.assertTrue(all(case["expected"]["dangerous_clicks"] == 0 for case in routed_consequential))

    def test_no_source_generator_phrase_or_ui_artifact_leakage(self) -> None:
        source_sentences = {
            _normalize(row[field])
            for row in self.doc_rows
            for field in ("source_goal_ko", "source_goal_en")
        }
        self.assertEqual(len(source_sentences), 480)

        for case in self.cases:
            goal = case["goal"]
            normalized_goal = _normalize(goal)
            self.assertNotIn(normalized_goal, source_sentences, case["case_id"])
            for source_sentence in source_sentences:
                self.assertFalse(
                    len(source_sentence) >= 12 and source_sentence in normalized_goal,
                    f"{case['case_id']} contains a document representative sentence",
                )
            self.assertIsNone(SOURCE_SENTENCE_LEAD_RE.search(goal.strip()), case["case_id"])
            self.assertIsNone(SOURCE_SENTENCE_KO_END_RE.search(goal.strip()), case["case_id"])
            self.assertIsNone(PACKAGE_OR_RESOURCE_ID_RE.search(goal), case["case_id"])
            self.assertIsNone(FIXED_PATH_RE.search(goal), case["case_id"])
            self.assertIsNone(COORDINATE_OR_SCREENSHOT_RE.search(goal), case["case_id"])
            self.assertIsNone(PROHIBITED_AUTHORING_ARTIFACT_RE.search(goal), case["case_id"])
            for key, value in case["surface"].items():
                if key == "missing" or value is None:
                    continue
                self.assertIsInstance(value, str)
                self.assertIsNone(PACKAGE_OR_RESOURCE_ID_RE.search(value), f"{case['case_id']}/{key}")
                self.assertIsNone(FIXED_PATH_RE.search(value), f"{case['case_id']}/{key}")
                self.assertIsNone(COORDINATE_OR_SCREENSHOT_RE.search(value), f"{case['case_id']}/{key}")
                self.assertIsNone(PROHIBITED_AUTHORING_ARTIFACT_RE.search(value), f"{case['case_id']}/{key}")


if __name__ == "__main__":
    unittest.main()
