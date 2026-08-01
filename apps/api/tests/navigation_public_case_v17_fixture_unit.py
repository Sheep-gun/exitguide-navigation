from __future__ import annotations

import ast
import hashlib
import json
import re
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "fixtures"
    / "navigation"
    / "db-gym"
    / "independent-public-case-v17.v1.json"
)
SOURCE_PATH = REPO_ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V17.md"

EXPECTED_FIXTURE_SHA256 = "014efca401177aedb3e0ef147883ddbc5826f7d181582ee23628e42240c91563"
EXPECTED_SOURCE_SHA256 = "82fb912cd020188890ab2002438fd16be7bad5581432af3e8123b4b44339ca4b"
EXPECTED_DOMAIN_COUNT = 12
EXPECTED_TERMINAL_COUNT = 228
EXPECTED_CASE_COUNT = 228
EXPECTED_STEP_COUNT = 912
EXPECTED_LOCALES = Counter({"ko-KR": 114, "en-US": 114})
EXPECTED_BOUNDARIES = Counter(
    {
        "normal_progress": 36,
        "wrong_role": 24,
        "wrong_record": 24,
        "wrong_jurisdiction": 24,
        "loading": 24,
        "offline": 24,
        "error": 24,
        "relogin": 24,
        "stop_before_action": 24,
    }
)
EXPECTED_BOUNDARIES_PER_DOMAIN = Counter(
    {
        "normal_progress": 3,
        "wrong_role": 2,
        "wrong_record": 2,
        "wrong_jurisdiction": 2,
        "loading": 2,
        "offline": 2,
        "error": 2,
        "relogin": 2,
        "stop_before_action": 2,
    }
)
FAIL_CLOSED_BOUNDARIES = {
    "wrong_role",
    "wrong_record",
    "wrong_jurisdiction",
    "offline",
    "error",
    "relogin",
}
ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "ast",
    "collections",
    "hashlib",
    "json",
    "pathlib",
    "re",
    "typing",
    "unittest",
}
FORBIDDEN_SEMANTIC_KEYS = {
    "activity_name",
    "android_version",
    "app_package",
    "bounds",
    "click_sequence",
    "coordinate",
    "coordinates",
    "device_model",
    "fixed_ui_path",
    "package_name",
    "pixel",
    "pixels",
    "recorded_path",
    "resource_id",
    "resource_ids",
    "screenshot",
    "screenshot_hash",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_fixture() -> dict[str, Any]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise AssertionError("fixture root must be an object")
    return value


def _source_terminals() -> dict[str, tuple[str, ...]]:
    """Read the SHA-pinned public source pack without importing runtime modules."""
    text = SOURCE_PATH.read_text(encoding="utf-8")
    domains: dict[str, tuple[str, ...]] = {}
    current_domain: str | None = None
    heading = re.compile(r"^###\s+\d+\..*\(`([a-z0-9_]+)`\)\s*$")
    for line in text.splitlines():
        match = heading.match(line)
        if match:
            current_domain = match.group(1)
            continue
        if current_domain and line.startswith("Terminals (19):"):
            terminal_ids = tuple(re.findall(r"`([a-z0-9_]+)`", line))
            if current_domain in domains:
                raise AssertionError(f"duplicate source domain: {current_domain}")
            domains[current_domain] = terminal_ids
            current_domain = None
    return domains


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


class NavigationPublicCaseV17FixtureUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = _load_fixture()
        cls.cases = cls.fixture["cases"]
        cls.source_terminals = _source_terminals()

    def test_fixed_fixture_and_source_sha256(self) -> None:
        self.assertEqual(_sha256(FIXTURE_PATH), EXPECTED_FIXTURE_SHA256)
        self.assertEqual(_sha256(SOURCE_PATH), EXPECTED_SOURCE_SHA256)
        self.assertEqual(
            self.fixture["provenance"]["source_document_sha256"],
            EXPECTED_SOURCE_SHA256,
        )

    def test_static_schema_contract(self) -> None:
        fixture = self.fixture
        self.assertEqual(fixture["schema_version"], 2)
        self.assertEqual(fixture["fixture_version"], "17.1.0")
        self.assertEqual(fixture["split"], "independent_public_case_v17")
        self.assertIs(fixture["frozen"], True)
        self.assertIs(fixture["catalog_derived"], False)
        self.assertIs(fixture["tuning_allowed"], False)
        self.assertEqual(len(self.cases), EXPECTED_CASE_COUNT)

        required_case_keys = {
            "case_id",
            "intent_id",
            "domain_id",
            "terminal_id",
            "function_id",
            "destination_name",
            "goal_text",
            "locale",
            "user_state",
            "authorized_role",
            "governed_asset",
            "lifecycle_state",
            "jurisdiction",
            "boundary_kind",
            "safety_class",
            "final_action_policy",
            "source_kind",
            "provenance",
            "tuning_allowed",
            "tags",
            "steps",
        }
        expected_stage_order = [
            "domain_gateway",
            "context_guard",
            "semantic_route",
            "safety_boundary",
        ]
        for case in self.cases:
            self.assertTrue(required_case_keys.issubset(case), case.get("case_id"))
            self.assertIsInstance(case["goal_text"], str)
            self.assertGreaterEqual(len(case["goal_text"]), 140)
            self.assertEqual(case["source_kind"], "fixed_independent_public_case")
            self.assertEqual(case["provenance"], "independent_public_case_v17_authoring")
            self.assertIs(case["tuning_allowed"], False)
            self.assertEqual(len(case["steps"]), 4)
            self.assertEqual(
                [step["stage"] for step in case["steps"]],
                expected_stage_order,
                case["case_id"],
            )
            for step in case["steps"]:
                self.assertIsInstance(step["elements"], list)
                self.assertTrue(step["elements"])
                self.assertIn("action", step["expected"])
                self.assertIn("function_id", step["expected"])

        self.assertEqual(
            sum(len(case["steps"]) for case in self.cases),
            EXPECTED_STEP_COUNT,
        )
        contract = fixture["coverage_contract"]
        self.assertEqual(contract["domains"], EXPECTED_DOMAIN_COUNT)
        self.assertEqual(contract["terminals"], EXPECTED_TERMINAL_COUNT)
        self.assertEqual(contract["intents"], EXPECTED_TERMINAL_COUNT)
        self.assertEqual(contract["cases"], EXPECTED_CASE_COUNT)
        self.assertEqual(contract["steps"], EXPECTED_STEP_COUNT)

    def test_ids_are_unique_and_structurally_bound(self) -> None:
        for key in ("case_id", "intent_id", "function_id"):
            values = [case[key] for case in self.cases]
            self.assertEqual(len(values), len(set(values)), key)

        for index, case in enumerate(self.cases, start=1):
            domain_id = case["domain_id"]
            terminal_id = case["terminal_id"]
            function_id = f"{domain_id}.{terminal_id}"
            self.assertEqual(case["function_id"], function_id)
            self.assertEqual(case["intent_id"], f"v17_{domain_id}_{terminal_id}")
            self.assertEqual(
                case["case_id"],
                f"indpubv17_{index:03d}_{domain_id}_{terminal_id}",
            )
            self.assertEqual(case["steps"][0]["expected"]["function_id"], f"{domain_id}.hub")
            self.assertEqual(case["steps"][1]["expected"]["function_id"], f"{domain_id}.hub")
            self.assertEqual(case["steps"][2]["expected"]["function_id"], function_id)
            self.assertEqual(case["steps"][3]["expected"]["function_id"], function_id)

    def test_all_228_source_terminals_are_covered_exactly_once(self) -> None:
        self.assertEqual(len(self.source_terminals), EXPECTED_DOMAIN_COUNT)
        self.assertTrue(
            all(len(terminals) == 19 for terminals in self.source_terminals.values())
        )
        self.assertEqual(
            sum(len(terminals) for terminals in self.source_terminals.values()),
            EXPECTED_TERMINAL_COUNT,
        )

        manifest = {
            item["domain_id"]: tuple(item["terminal_ids"])
            for item in self.fixture["domain_manifest"]
        }
        self.assertEqual(manifest, self.source_terminals)

        actual: dict[str, list[str]] = defaultdict(list)
        for case in self.cases:
            actual[case["domain_id"]].append(case["terminal_id"])
        self.assertEqual(
            {domain: tuple(terminals) for domain, terminals in actual.items()},
            self.source_terminals,
        )

    def test_domain_and_boundary_balance(self) -> None:
        per_domain = Counter(case["domain_id"] for case in self.cases)
        self.assertEqual(set(per_domain), set(self.source_terminals))
        self.assertTrue(all(count == 19 for count in per_domain.values()))

        observed_boundaries = Counter(case["boundary_kind"] for case in self.cases)
        self.assertEqual(observed_boundaries, EXPECTED_BOUNDARIES)

        by_domain: dict[str, Counter[str]] = defaultdict(Counter)
        for case in self.cases:
            by_domain[case["domain_id"]][case["boundary_kind"]] += 1
        self.assertEqual(set(by_domain), set(self.source_terminals))
        for domain_id, counts in by_domain.items():
            self.assertEqual(counts, EXPECTED_BOUNDARIES_PER_DOMAIN, domain_id)

        contract = self.fixture["coverage_contract"]
        self.assertEqual(Counter(contract["boundary_kinds"]), EXPECTED_BOUNDARIES)
        self.assertEqual(
            Counter(contract["required_boundary_kinds_per_domain"]),
            EXPECTED_BOUNDARIES_PER_DOMAIN,
        )

    def test_korean_english_balance_and_bilingual_names(self) -> None:
        locale_counts = Counter(case["locale"] for case in self.cases)
        self.assertEqual(locale_counts, EXPECTED_LOCALES)
        self.assertEqual(
            Counter(self.fixture["coverage_contract"]["locales"]),
            EXPECTED_LOCALES,
        )

        by_domain: dict[str, Counter[str]] = defaultdict(Counter)
        for case in self.cases:
            by_domain[case["domain_id"]][case["locale"]] += 1
            names = case["destination_name"]
            self.assertRegex(names["ko"], r"[가-힣]")
            self.assertRegex(names["en"], r"[A-Za-z]")
            if case["locale"] == "ko-KR":
                self.assertRegex(case["goal_text"], r"[가-힣]")
            else:
                self.assertNotRegex(case["goal_text"], r"[가-힣]")
                self.assertRegex(case["goal_text"], r"[A-Za-z]")
        for domain_id, counts in by_domain.items():
            self.assertEqual(set(counts.values()), {9, 10}, domain_id)

    def test_safety_policy_and_fail_closed_guards(self) -> None:
        safety_counts = Counter(case["safety_class"] for case in self.cases)
        self.assertEqual(set(safety_counts), {"S", "C"})
        self.assertEqual(
            Counter(self.fixture["coverage_contract"]["safety_classes"]),
            safety_counts,
        )

        for case in self.cases:
            function_id = case["function_id"]
            self.assertEqual(case["final_action_policy"], "stop_before_action")
            guard = case["steps"][1]
            route = case["steps"][2]
            final = case["steps"][3]

            if case["boundary_kind"] in FAIL_CLOSED_BOUNDARIES:
                self.assertEqual(guard["expected"]["action"], "no_click")
                self.assertEqual(
                    guard["expected"]["outcome"],
                    "fail_closed_to_domain_hub",
                )
            elif case["boundary_kind"] == "loading":
                self.assertEqual(guard["expected"]["action"], "no_click")
                self.assertEqual(guard["expected"]["outcome"], "hold_at_domain_hub")
            else:
                self.assertEqual(guard["expected"]["action"], "click")

            self.assertEqual(route["expected"]["action"], "click")
            self.assertEqual(route["expected"]["function_id"], function_id)
            self.assertEqual(final["stage"], "safety_boundary")
            self.assertEqual(final["expected"]["action"], "no_click")
            self.assertIsNone(final["expected"]["label"])
            self.assertEqual(final["expected"]["function_id"], function_id)
            self.assertIs(final["expected"]["stop_before_action"], True)
            self.assertEqual(final["expected"]["final_control_owner"], "user")
            dangerous = [element for element in final["elements"] if element["dangerous"]]
            self.assertEqual(len(dangerous), 1)
            self.assertTrue(dangerous[0]["clickable"])
            self.assertTrue(dangerous[0]["enabled"])

    def test_semantic_only_and_no_runtime_imports(self) -> None:
        keys = {
            value
            for value in _walk(self.fixture)
            if isinstance(value, str) and value in FORBIDDEN_SEMANTIC_KEYS
        }
        self.assertFalse(keys, f"forbidden semantic keys present: {sorted(keys)}")
        self.assertIs(self.fixture["provenance"]["prohibited_inputs_used"], False)
        self.assertIs(self.fixture["provenance"]["runtime_evaluation_used"], False)

        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported_roots.issubset(ALLOWED_IMPORT_ROOTS),
            f"runtime or project import detected: {sorted(imported_roots - ALLOWED_IMPORT_ROOTS)}",
        )


if __name__ == "__main__":
    unittest.main()
