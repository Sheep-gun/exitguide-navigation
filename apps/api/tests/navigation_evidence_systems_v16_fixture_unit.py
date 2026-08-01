from __future__ import annotations

import ast
import difflib
import hashlib
import importlib
import json
import re
import sys
import unicodedata
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "fixtures/navigation/db-gym/independent-evidence-systems-v16.json"
)
COVERAGE_PATH = REPO_ROOT / "docs/NAVIGATION_COVERAGE_GAPS_V16.md"
REFINEMENT_PATH = REPO_ROOT / "docs/NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md"
SOURCE_MODULE_PATH = REPO_ROOT / "scripts/navigation_catalog_v16_data.py"
CANONICAL_CATALOG_PATH = REPO_ROOT / "fixtures/navigation/function-catalog.v1.json"

EXPECTED_SLICES = {
    "positive_ko": 240,
    "positive_en": 240,
    "prior_catalog_collision": 240,
    "within_v16_collision": 120,
    "underspecified_unsafe_abstention": 120,
}
EXPECTED_PROJECTION = {
    "domains": 191,
    "physical_functions": 3118,
    "physical_terminal_functions": 2900,
    "physical_intents": 2900,
    "v16_append_domains": 12,
    "v16_append_functions": 252,
    "v16_append_terminals": 240,
    "v16_append_intents": 240,
}
EXPECTED_DOMAINS = [
    "controlled_substance_compliance_ops",
    "medical_device_regulatory_ops",
    "occupational_safety_case_ops",
    "food_manufacturing_recall_ops",
    "government_contract_administration",
    "public_company_sec_reporting_ops",
    "wireless_spectrum_license_ops",
    "commercial_space_launch_licensing_ops",
    "radioactive_materials_license_ops",
    "hazardous_materials_transport_compliance",
    "firearms_dealer_compliance_ops",
    "commercial_vessel_safety_compliance",
]
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

HANGUL_RE = re.compile(r"[가-힣]")
INTERNAL_ID_RE = re.compile(r"\b[a-z][a-z0-9_]+[.][a-z][a-z0-9_]+\b")
COORDINATE_RE = re.compile(
    r"(?:[(]\s*[0-9]{1,4}\s*,\s*[0-9]{1,4}\s*[)]|"
    r"\b(?:coordinate|pixel|screenshot-derived|screenshot label)\b)",
    re.IGNORECASE,
)
FIXED_PATH_RE = re.compile(
    r"(?:[A-Za-z]:\\|/(?:data|android|ios|system)/|"
    r"\b(?:tap|click)\b.{0,40}(?:then|menu|settings))",
    re.IGNORECASE,
)
MARKDOWN_ROW_RE = re.compile(
    r"^[|] ([SC]) [|] " + chr(96) + r"([^" + chr(96) + r"]+)"
    + chr(96)
    + r" [|] .*? [|] (.*?) / ([^|]+?) [|]$",
    re.MULTILINE,
)
REFINEMENT_GOAL_RE = re.compile(
    r"^- \*\*목표:\*\* (.*?) / (.*?)$", re.MULTILINE
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise AssertionError(f"expected object in {path}")
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _word_tokens(value: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return frozenset(re.findall(r"[a-z0-9]+|[가-힣]+", normalized))


def _walk_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_strings(item)


def _prior_identifier_projection(
    catalog: dict[str, Any],
    v16_domains: set[str],
) -> dict[str, Any]:
    functions = [
        {
            "function_id": item["function_id"],
            "domain": item["domain"],
            "terminal": bool(item["terminal"]),
        }
        for item in catalog["functions"]
        if item["domain"] not in v16_domains
    ]
    intents = [
        item["intent_id"]
        for item in catalog["intents"]
        if str(item.get("terminal_function", "")).split(".", 1)[0]
        not in v16_domains
        and not str(item["intent_id"]).startswith("v16_")
    ]
    return {
        "functions": sorted(functions, key=lambda item: item["function_id"]),
        "intents": sorted(intents),
    }


class NavigationEvidenceSystemsV16FixtureUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_json(FIXTURE_PATH)
        cls.metadata = cls.fixture["metadata"]
        cls.cases = cls.fixture["cases"]
        cls.catalog = _load_json(CANONICAL_CATALOG_PATH)

        scripts_path = str(REPO_ROOT / "scripts")
        if scripts_path not in sys.path:
            sys.path.insert(0, scripts_path)
        source = importlib.import_module("navigation_catalog_v16_data")
        cls.final_id_to_class = {
            function_id: source.REVIEWED_FEATURE_BY_ID[function_id].classification
            for function_id in source.FINAL_TERMINAL_IDS
        }
        cls.source_domains = set(source.REQUIRED_DOMAINS)
        cls.v16_ids = set(cls.final_id_to_class)
        cls.v16_domains = set(EXPECTED_DOMAINS)
        cls.prior_projection = _prior_identifier_projection(
            cls.catalog,
            cls.v16_domains,
        )
        cls.prior_functions = cls.prior_projection["functions"]
        cls.prior_terminal_ids = {
            item["function_id"]
            for item in cls.prior_functions
            if item["terminal"]
        }

    def test_frozen_schema_counts_and_two_level_seal(self) -> None:
        self.assertTrue(self.metadata["frozen"])
        self.assertTrue(self.metadata["sealed"])
        self.assertFalse(self.metadata["tuning_allowed"])
        self.assertEqual(
            self.metadata["schema_version"],
            "16.0.0-independent-evaluation.1",
        )
        self.assertEqual(self.metadata["catalog_target_version"], "16.0.0")
        self.assertEqual(self.metadata["slice_contract"], EXPECTED_SLICES)
        self.assertEqual(self.metadata["projection"], EXPECTED_PROJECTION)
        self.assertEqual(len(self.cases), 960)
        self.assertEqual(
            Counter(case["slice"] for case in self.cases),
            Counter(EXPECTED_SLICES),
        )

        cases_digest = hashlib.sha256(
            _canonical_json(self.cases)
        ).hexdigest()
        self.assertEqual(
            self.metadata["cases_payload_sha256"],
            cases_digest,
        )

        payload = dict(self.fixture)
        seal = payload.pop("canonical_json_sha256")
        self.assertRegex(seal, r"^[0-9a-f]{64}$")
        self.assertEqual(
            seal,
            hashlib.sha256(_canonical_json(payload)).hexdigest(),
        )

    def test_authorship_inputs_are_pinned_and_narrow(self) -> None:
        authorship = self.metadata["authorship"]
        self.assertTrue(authorship["declared_independent"])
        allowed = authorship["allowed_inputs"]
        self.assertEqual(
            [item["artifact"] for item in allowed],
            [
                "docs/NAVIGATION_COVERAGE_GAPS_V16.md",
                "docs/NAVIGATION_COVERAGE_GAPS_V16_REFINEMENT.md",
                "scripts/navigation_catalog_v16_data.py",
                "fixtures/navigation/function-catalog.v1.json",
            ],
        )
        self.assertEqual(
            allowed[0]["sha256"],
            hashlib.sha256(COVERAGE_PATH.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            allowed[1]["sha256"],
            hashlib.sha256(REFINEMENT_PATH.read_bytes()).hexdigest(),
        )
        id_class_projection = sorted(
            [
                [function_id, terminal_class]
                for function_id, terminal_class in self.final_id_to_class.items()
            ]
        )
        id_class_digest = hashlib.sha256(
            _canonical_json(id_class_projection)
        ).hexdigest()
        self.assertEqual(allowed[2]["final_id_class_sha256"], id_class_digest)
        self.assertEqual(
            self.metadata["identifier_contract"]["final_id_class_sha256"],
            id_class_digest,
        )
        self.assertEqual(allowed[3]["catalog_version_at_authoring"], "15.0.0")
        self.assertEqual(
            allowed[3]["identifier_projection_sha256"],
            hashlib.sha256(
                _canonical_json(self.prior_projection)
            ).hexdigest(),
        )
        self.assertEqual(
            set(authorship["excluded_inputs"]),
            {
                "V16 alias tables",
                "V16 intent patterns",
                "V16 goal rules",
                "representative goals",
                "generated prose records",
                "resolver outputs",
                "independent failure reports",
            },
        )

    def test_test_code_accesses_only_exported_id_and_class_surface(self) -> None:
        source_text = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(source_text)
        forbidden_attributes = {
            "V16_FUNCTIONS",
            "V16_INTENTS",
            "GROUPS",
            "aliases",
            "patterns",
            "goal_rules",
            "positive_context",
            "negative_context",
            "representative_goals",
            "collision_probes",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, forbidden_attributes)
        self.assertNotIn("navigation_" + "goal_prose", source_text)
        self.assertNotIn("independent_" + "accuracy", source_text)

    def test_exact_final_ids_classes_domains_and_projection(self) -> None:
        self.assertEqual(len(self.v16_ids), 240)
        self.assertEqual(self.source_domains, self.v16_domains)
        self.assertEqual(
            self.metadata["identifier_contract"]["v16_domains"],
            EXPECTED_DOMAINS,
        )
        self.assertEqual(
            Counter(self.final_id_to_class.values()),
            {"S": 84, "C": 156},
        )
        self.assertEqual(
            Counter(
                function_id.split(".", 1)[0]
                for function_id in self.v16_ids
            ),
            Counter({domain: 20 for domain in EXPECTED_DOMAINS}),
        )
        for domain in EXPECTED_DOMAINS:
            domain_classes = [
                terminal_class
                for function_id, terminal_class in self.final_id_to_class.items()
                if function_id.startswith(domain + ".")
            ]
            self.assertEqual(Counter(domain_classes), {"S": 7, "C": 13})

        self.assertEqual(len(self.prior_functions), 2866)
        self.assertEqual(len(self.prior_terminal_ids), 2660)
        self.assertEqual(len(self.prior_projection["intents"]), 2660)
        self.assertEqual(
            len({item["domain"] for item in self.prior_functions}),
            179,
        )
        prospective_hubs = {domain + ".hub" for domain in EXPECTED_DOMAINS}
        prospective_functions = self.v16_ids | prospective_hubs
        prospective_intents = {
            "v16_" + function_id.replace(".", "_")
            for function_id in self.v16_ids
        }
        prior_function_ids = {
            item["function_id"] for item in self.prior_functions
        }
        self.assertTrue(prior_function_ids.isdisjoint(prospective_functions))
        self.assertEqual(len(prior_function_ids | prospective_functions), 3118)
        self.assertEqual(
            len(self.prior_terminal_ids | self.v16_ids),
            2900,
        )
        self.assertEqual(
            len(set(self.prior_projection["intents"]) | prospective_intents),
            2900,
        )

    def test_positive_pairs_cover_every_terminal_exactly_twice(self) -> None:
        positives = [
            case
            for case in self.cases
            if case["slice"] in {"positive_ko", "positive_en"}
        ]
        self.assertEqual(
            Counter(case["expected"]["function_id"] for case in positives),
            Counter({function_id: 2 for function_id in self.v16_ids}),
        )
        ko_by_id = {
            case["pair_key"]: case
            for case in positives
            if case["slice"] == "positive_ko"
        }
        en_by_id = {
            case["pair_key"]: case
            for case in positives
            if case["slice"] == "positive_en"
        }
        self.assertEqual(set(ko_by_id), self.v16_ids)
        self.assertEqual(set(en_by_id), self.v16_ids)
        for function_id in self.v16_ids:
            ko = ko_by_id[function_id]
            en = en_by_id[function_id]
            self.assertEqual(ko["locale"], "ko")
            self.assertEqual(en["locale"], "en")
            self.assertTrue(HANGUL_RE.search(ko["goal"]), function_id)
            self.assertFalse(HANGUL_RE.search(en["goal"]), function_id)
            self.assertEqual(
                ko["surface"]["scenario_axis"],
                "operational_reconciliation",
            )
            self.assertEqual(
                en["surface"]["scenario_axis"],
                "evidence_audit",
            )
            self.assertNotEqual(_normalize(ko["goal"]), _normalize(en["goal"]))
            for case in (ko, en):
                expected = case["expected"]
                self.assertEqual(expected["decision"], "route")
                self.assertEqual(expected["function_id"], function_id)
                self.assertEqual(
                    expected["domain"],
                    function_id.split(".", 1)[0],
                )
                self.assertEqual(
                    expected["terminal_class"],
                    self.final_id_to_class[function_id],
                )
                self.assertEqual(expected["acceptable_top3"], [function_id])

    def test_cases_are_disjoint_locale_balanced_and_never_tuning_data(self) -> None:
        expected_ids = [
            f"v16-independent-{index:04d}"
            for index in range(1, 961)
        ]
        self.assertEqual([case["case_id"] for case in self.cases], expected_ids)
        self.assertEqual(len({case["case_id"] for case in self.cases}), 960)
        normalized_goals = [_normalize(case["goal"]) for case in self.cases]
        self.assertEqual(len(set(normalized_goals)), 960)
        self.assertTrue(all(case["tuning_allowed"] is False for case in self.cases))
        for case in self.cases:
            if case["slice"].startswith("positive_"):
                self.assertIsNotNone(case["pair_key"])
            else:
                self.assertIsNone(case["pair_key"])
        for slice_name, per_locale in {
            "prior_catalog_collision": 120,
            "within_v16_collision": 60,
            "underspecified_unsafe_abstention": 60,
        }.items():
            selected = [
                case for case in self.cases if case["slice"] == slice_name
            ]
            self.assertEqual(
                Counter(case["locale"] for case in selected),
                {"ko": per_locale, "en": per_locale},
            )
        self.assertEqual(
            self.metadata["evaluation_contract"],
            {
                "sealed": True,
                "tuning_allowed": False,
                "may_train_on_cases": False,
                "may_inspect_failure_text_during_tuning": False,
            },
        )

    def test_prior_generation_collision_slice_is_exact(self) -> None:
        prior = [
            case
            for case in self.cases
            if case["slice"] == "prior_catalog_collision"
        ]
        target_ids = {case["expected"]["function_id"] for case in prior}
        self.assertEqual(len(target_ids), 240)
        self.assertTrue(target_ids <= self.prior_terminal_ids)
        self.assertTrue(target_ids.isdisjoint(self.v16_ids))
        self.assertEqual(
            Counter(case["expected"]["decoy_domain"] for case in prior),
            Counter({domain: 20 for domain in EXPECTED_DOMAINS}),
        )
        for domain in EXPECTED_DOMAINS:
            selected = [
                case
                for case in prior
                if case["expected"]["decoy_domain"] == domain
            ]
            self.assertEqual(
                Counter(case["locale"] for case in selected),
                {"ko": 10, "en": 10},
            )
        for case in prior:
            expected = case["expected"]
            self.assertEqual(expected["decision"], "route")
            self.assertIn(expected["decoy_function_id"], self.v16_ids)
            self.assertEqual(
                expected["decoy_function_id"].split(".", 1)[0],
                expected["decoy_domain"],
            )
            self.assertEqual(
                expected["function_id"].split(".", 1)[0],
                expected["domain"],
            )

    def test_within_v16_collision_slice_is_exact(self) -> None:
        within = [
            case
            for case in self.cases
            if case["slice"] == "within_v16_collision"
        ]
        target_ids = {case["expected"]["function_id"] for case in within}
        self.assertEqual(len(target_ids), 120)
        self.assertTrue(target_ids <= self.v16_ids)
        self.assertEqual(
            Counter(case["expected"]["domain"] for case in within),
            Counter({domain: 10 for domain in EXPECTED_DOMAINS}),
        )
        self.assertEqual(
            Counter(case["expected"]["decoy_domain"] for case in within),
            Counter({domain: 10 for domain in EXPECTED_DOMAINS}),
        )
        self.assertEqual(
            Counter(case["expected"]["terminal_class"] for case in within),
            {"S": 60, "C": 60},
        )
        for domain in EXPECTED_DOMAINS:
            selected = [
                case
                for case in within
                if case["expected"]["domain"] == domain
            ]
            self.assertEqual(
                Counter(case["locale"] for case in selected),
                {"ko": 5, "en": 5},
            )
        for case in within:
            expected = case["expected"]
            self.assertIn(expected["decoy_function_id"], self.v16_ids)
            self.assertNotEqual(expected["domain"], expected["decoy_domain"])
            self.assertTrue(expected["shared_surface"])

    def test_underspecified_cases_cover_every_guard_and_abstain(self) -> None:
        unsafe = [
            case
            for case in self.cases
            if case["slice"] == "underspecified_unsafe_abstention"
        ]
        consequential_ids = {
            function_id
            for function_id, terminal_class in self.final_id_to_class.items()
            if terminal_class == "C"
        }
        for domain in EXPECTED_DOMAINS:
            selected = [
                case
                for case in unsafe
                if case["expected"]["safe_fallback_domain"] == domain
            ]
            self.assertEqual(len(selected), 10)
            self.assertEqual(
                Counter(case["locale"] for case in selected),
                {"ko": 5, "en": 5},
            )
            self.assertEqual(
                {case["expected"]["reason"] for case in selected},
                UNSAFE_REASONS,
            )
            self.assertEqual(
                {case["surface"]["missing"][0] for case in selected},
                UNSAFE_REASONS,
            )
            self.assertEqual(
                len(
                    {
                        case["expected"]["unsafe_candidate_id"]
                        for case in selected
                    }
                ),
                10,
            )
            for case in selected:
                expected = case["expected"]
                reason = expected["reason"]
                self.assertEqual(expected["decision"], "abstain")
                self.assertIsNone(expected["domain"])
                self.assertIsNone(expected["function_id"])
                self.assertIsNone(expected["terminal_class"])
                self.assertEqual(expected["acceptable_top3"], [])
                self.assertIn(
                    expected["unsafe_candidate_id"],
                    consequential_ids,
                )
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

    def test_screen_state_and_action_evidence_is_structurally_rich(self) -> None:
        required_surface = {
            "role",
            "asset",
            "state",
            "jurisdiction",
            "recovery",
            "decoy",
            "missing",
            "scenario_axis",
        }
        required_evidence = {"screen_cues", "state_trace", "action_cues"}
        for case in self.cases:
            self.assertEqual(set(case["surface"]), required_surface)
            self.assertEqual(set(case["evidence"]), required_evidence)
            self.assertTrue(case["surface"]["decoy"])
            self.assertIsInstance(case["surface"]["missing"], list)
            for field in required_evidence:
                values = case["evidence"][field]
                self.assertEqual(len(values), 3, f"{case['case_id']}/{field}")
                self.assertTrue(
                    all(isinstance(value, str) and value.strip() for value in values)
                )
            if case["expected"]["decision"] == "route":
                self.assertEqual(case["surface"]["missing"], [])
                for field in (
                    "role",
                    "asset",
                    "state",
                    "jurisdiction",
                    "recovery",
                    "decoy",
                ):
                    self.assertTrue(case["surface"][field])
                self.assertEqual(
                    case["evidence"]["state_trace"],
                    case["surface"]["state"].split(" → "),
                )

        positives = [
            case for case in self.cases if case["slice"].startswith("positive_")
        ]
        for domain in EXPECTED_DOMAINS:
            selected = [
                case
                for case in positives
                if case["expected"]["domain"] == domain
            ]
            self.assertGreaterEqual(
                len({case["surface"]["role"] for case in selected}),
                20,
            )
            self.assertEqual(
                len({case["surface"]["asset"] for case in selected}),
                40,
            )
            self.assertGreaterEqual(
                len({case["surface"]["state"] for case in selected}),
                16,
            )
            self.assertGreaterEqual(
                len({case["surface"]["recovery"] for case in selected}),
                20,
            )

    def test_final_action_is_always_user_owned_and_never_automated(self) -> None:
        self.assertEqual(
            self.metadata["terminal_contract"],
            {
                "sensitive_read_only": 84,
                "consequential": 156,
                "risk_level": "high",
                "automation_policy": "never_auto",
                "stop_policy": "before_action",
                "user_owned_final_press": True,
                "dangerous_expected_clicks": 0,
                "automated_final_presses": 0,
            },
        )
        for case in self.cases:
            expected = case["expected"]
            self.assertEqual(expected["dangerous_clicks"], 0)
            self.assertEqual(expected["automated_final_presses"], 0)
            self.assertEqual(expected["terminal_press_owner"], "user")
            if expected["function_id"] in self.v16_ids:
                self.assertEqual(expected["stop_policy"], "before_action")
            else:
                self.assertEqual(expected["stop_policy"], "navigation_only")

    def test_no_representative_goal_or_catalog_phrase_copy(self) -> None:
        coverage_text = COVERAGE_PATH.read_text(encoding="utf-8")
        refinement_text = REFINEMENT_PATH.read_text(encoding="utf-8")
        reviewed_goals: list[str] = []
        for match in MARKDOWN_ROW_RE.finditer(coverage_text):
            reviewed_goals.extend([match.group(2).strip(), match.group(3).strip()])
        for match in REFINEMENT_GOAL_RE.finditer(refinement_text):
            reviewed_goals.extend([match.group(1).strip(), match.group(2).strip()])
        self.assertGreaterEqual(len(reviewed_goals), 480)

        production_texts: list[str] = []
        for function in self.catalog["functions"]:
            for field in (
                "name_ko",
                "name_en",
                "description",
                "aliases",
                "positive_context",
                "negative_context",
            ):
                production_texts.extend(_walk_strings(function.get(field)))
        for intent in self.catalog["intents"]:
            for field in ("patterns", "goal_rules"):
                production_texts.extend(_walk_strings(intent.get(field)))

        reviewed_norm = {
            _normalize(value) for value in reviewed_goals if _normalize(value)
        }
        production_norm = {
            _normalize(value)
            for value in production_texts
            if len(_normalize(value)) >= 4
        }
        reviewed_long = [
            value for value in reviewed_norm if len(value) >= 16
        ]
        production_long = [
            value for value in production_norm if len(value) >= 40
        ]
        source_token_sets: list[tuple[frozenset[str], str]] = []
        token_index: dict[str, set[int]] = defaultdict(set)
        seen_token_sets: set[frozenset[str]] = set()
        for value in reviewed_goals + production_texts:
            tokens = _word_tokens(value)
            if len(tokens) < 5 or tokens in seen_token_sets:
                continue
            seen_token_sets.add(tokens)
            index = len(source_token_sets)
            source_token_sets.append((tokens, value))
            for token in tokens:
                token_index[token].add(index)

        for case in self.cases:
            goal = case["goal"]
            normalized_goal = _normalize(goal)
            self.assertNotIn(normalized_goal, reviewed_norm, case["case_id"])
            self.assertNotIn(normalized_goal, production_norm, case["case_id"])
            self.assertFalse(
                any(value in normalized_goal for value in reviewed_long),
                f"{case['case_id']} embeds a reviewed representative goal",
            )
            self.assertFalse(
                any(value in normalized_goal for value in production_long),
                f"{case['case_id']} embeds a long production phrase",
            )

            goal_tokens = _word_tokens(goal)
            shared_counts: Counter[int] = Counter()
            for token in goal_tokens:
                shared_counts.update(token_index.get(token, ()))
            for source_index, shared_count in shared_counts.items():
                source_tokens, source_value = source_token_sets[source_index]
                union_size = len(goal_tokens) + len(source_tokens) - shared_count
                if union_size <= 0:
                    continue
                jaccard = shared_count / union_size
                if jaccard < 0.72:
                    continue
                ratio = difflib.SequenceMatcher(
                    None,
                    normalized_goal,
                    _normalize(source_value),
                    autojunk=False,
                ).ratio()
                self.assertLess(
                    ratio,
                    0.88,
                    f"{case['case_id']} near-copies a source phrase",
                )

    def test_no_internal_identifier_coordinate_or_fixed_path_leakage(self) -> None:
        for case in self.cases:
            values = [case["goal"]]
            values.extend(
                value
                for key, value in case["surface"].items()
                if key != "missing" and value is not None
            )
            values.extend(_walk_strings(case["evidence"]))
            for value in values:
                self.assertIsNone(
                    INTERNAL_ID_RE.search(value),
                    f"{case['case_id']} leaks an internal identifier",
                )
                self.assertIsNone(
                    COORDINATE_RE.search(value),
                    f"{case['case_id']} leaks coordinate evidence",
                )
                self.assertIsNone(
                    FIXED_PATH_RE.search(value),
                    f"{case['case_id']} contains a fixed click path",
                )


if __name__ == "__main__":
    unittest.main()
