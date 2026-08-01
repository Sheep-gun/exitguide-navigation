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

VERSIONS = {
    18: {
        "fixture_path": REPO_ROOT / "fixtures" / "navigation" / "db-gym" / "independent-public-case-v18.v1.json",
        "source_path": REPO_ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V18_RESEARCH.md",
        "fixture_sha256": "10bdad769164b0c3429a9d74deb58fcd0e3eaa8d156628202fe0e28251fc63df",
        "source_sha256": "cca4aac49ad2811dfb1d55e059628c7261723becec6fd27536a648fddf9f5c13",
        "domains": 12,
        "semantic_seams": 240,
        "cases": 240,
        "steps": 960,
        "locales": Counter({"ko-KR": 120, "en-US": 120}),
        "boundaries": Counter({
            "normal_progress": 24,
            "wrong_role": 24,
            "wrong_record": 24,
            "wrong_state": 24,
            "wrong_provider_jurisdiction": 24,
            "loading": 24,
            "offline": 24,
            "error": 24,
            "relogin": 24,
            "stop_before_action": 24,
        }),
        "safety_classes": Counter({"S": 166, "C": 74}),
    },
    19: {
        "fixture_path": REPO_ROOT / "fixtures" / "navigation" / "db-gym" / "independent-public-case-v19.v1.json",
        "source_path": REPO_ROOT / "docs" / "NAVIGATION_COVERAGE_GAPS_V19_RESEARCH.md",
        "fixture_sha256": "b8f6da0bb04a60c30b554af50421bb80fec3976b1d53b913dbe9d92282f94fd2",
        "source_sha256": "f5997e4728a3131b995d2796a9b61cc943aeaf66d82d1e1ee3b5da811dc27d6b",
        "domains": 9,
        "semantic_seams": 114,
        "cases": 114,
        "steps": 456,
        "locales": Counter({"ko-KR": 57, "en-US": 57}),
        "boundaries": Counter({
            "normal_progress": 16,
            "wrong_role": 16,
            "wrong_record": 15,
            "wrong_state": 13,
            "wrong_provider_jurisdiction": 9,
            "loading": 9,
            "offline": 9,
            "error": 9,
            "relogin": 9,
            "stop_before_action": 9,
        }),
        "safety_classes": Counter({"S": 61, "C": 53}),
    },
}

BOUNDARIES = {
    "normal_progress",
    "wrong_role",
    "wrong_record",
    "wrong_state",
    "wrong_provider_jurisdiction",
    "loading",
    "offline",
    "error",
    "relogin",
    "stop_before_action",
}
FAIL_CLOSED_BOUNDARIES = {
    "wrong_role",
    "wrong_record",
    "wrong_state",
    "wrong_provider_jurisdiction",
    "offline",
    "error",
    "relogin",
}
EXPECTED_STAGE_ORDER = [
    "domain_gateway",
    "context_guard",
    "semantic_route",
    "safety_boundary",
]
FORBIDDEN_RUNTIME_KEYS = {
    "activity_name",
    "android_version",
    "app_package",
    "bounds",
    "click_sequence",
    "coordinate",
    "coordinates",
    "device_model",
    "fixed_ui_path",
    "function_id",
    "package_name",
    "pixel",
    "pixels",
    "recorded_path",
    "resource_id",
    "resource_ids",
    "runtime_function_id",
    "screenshot",
    "screenshot_hash",
    "terminal_id",
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_utf8(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise AssertionError(f"UTF-8 BOM is prohibited: {path}")
    text = raw.decode("utf-8", errors="strict")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise AssertionError(f"fixture root must be an object: {path}")
    return value


def _source_sections(source_path: Path) -> dict[str, str]:
    text = source_path.read_text(encoding="utf-8")
    heading = re.compile(r"(?m)^###\s+\d+\..*\(`([a-z0-9_]+)`\)\s*$")
    matches = list(heading.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.start():end]
    return sections


def _v19_source_semantics(source_path: Path) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for domain_id, section in _source_sections(source_path).items():
        semantic_keys = tuple(
            value
            for value in re.findall(r"(?m)^- `([a-z0-9_]+\.[a-z0-9_]+)`$", section)
            if value.startswith(domain_id + ".")
        )
        if semantic_keys:
            result[domain_id] = semantic_keys
    return result


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


class NavigationPublicCaseV18V19FixtureUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixtures = {
            version: _load_json_utf8(config["fixture_path"])
            for version, config in VERSIONS.items()
        }

    def test_fixed_source_and_fixture_sha256(self) -> None:
        for version, config in VERSIONS.items():
            with self.subTest(version=version):
                fixture = self.fixtures[version]
                self.assertEqual(_sha256(config["source_path"]), config["source_sha256"])
                self.assertEqual(_sha256(config["fixture_path"]), config["fixture_sha256"])
                self.assertEqual(
                    fixture["provenance"]["source_document_sha256"],
                    config["source_sha256"],
                )

    def test_static_schema_and_exact_counts(self) -> None:
        required_case_keys = {
            "case_id",
            "case_semantic_id",
            "domain_id",
            "expected_semantic_key",
            "source_semantic_phrase",
            "destination_name",
            "goal_text",
            "locale",
            "user_state",
            "authorized_role",
            "governed_asset",
            "lifecycle_state",
            "provider_jurisdiction",
            "official_provider_surface_url",
            "boundary_kind",
            "safety_class",
            "final_action_policy",
            "source_kind",
            "provenance",
            "tuning_allowed",
            "official_evidence_urls",
            "tags",
            "steps",
        }
        for version, config in VERSIONS.items():
            fixture = self.fixtures[version]
            cases = fixture["cases"]
            contract = fixture["coverage_contract"]
            with self.subTest(version=version):
                self.assertEqual(fixture["schema_version"], 3)
                self.assertEqual(fixture["fixture_version"], f"{version}.1.0")
                self.assertEqual(fixture["split"], f"independent_public_case_v{version}_semantic")
                self.assertIs(fixture["frozen"], True)
                self.assertIs(fixture["catalog_derived"], False)
                self.assertIs(fixture["runtime_bound"], False)
                self.assertIs(fixture["semantic_adapter_required"], True)
                self.assertIs(fixture["tuning_allowed"], False)
                self.assertEqual(len(fixture["domain_manifest"]), config["domains"])
                self.assertEqual(len(cases), config["cases"])
                self.assertEqual(sum(len(case["steps"]) for case in cases), config["steps"])
                self.assertEqual(contract["domains"], config["domains"])
                self.assertEqual(contract["semantic_seams"], config["semantic_seams"])
                self.assertEqual(contract["cases"], config["cases"])
                self.assertEqual(contract["steps"], config["steps"])
                self.assertEqual(contract["all_final_actions"], "no_click_stop_before_action_user_owned")
                for case in cases:
                    self.assertTrue(required_case_keys.issubset(case), case.get("case_id"))
                    self.assertEqual(len(case["steps"]), 4)
                    self.assertEqual([step["stage"] for step in case["steps"]], EXPECTED_STAGE_ORDER)
                    self.assertGreaterEqual(len(case["goal_text"]), 400)

    def test_independent_semantic_manifest_and_v19_source_seams(self) -> None:
        for version, config in VERSIONS.items():
            fixture = self.fixtures[version]
            source_sections = _source_sections(config["source_path"])
            manifest = fixture["domain_manifest"]
            manifest_domains = [item["domain_id"] for item in manifest]
            with self.subTest(version=version):
                self.assertEqual(len(manifest_domains), len(set(manifest_domains)))
                self.assertEqual(set(manifest_domains), set(source_sections))
                self.assertEqual(
                    sum(len(item["expected_semantic_keys"]) for item in manifest),
                    config["semantic_seams"],
                )
                if version == 18:
                    self.assertTrue(all(len(item["expected_semantic_keys"]) == 20 for item in manifest))
                    source_text = config["source_path"].read_text(encoding="utf-8")
                    self.assertIn("each contributes twenty terminals plus one fail-closed hub", source_text)
                else:
                    expected = _v19_source_semantics(config["source_path"])
                    actual = {
                        item["domain_id"]: tuple(item["expected_semantic_keys"])
                        for item in manifest
                    }
                    self.assertEqual(actual, expected)
                    self.assertEqual(sum(map(len, expected.values())), 114)

    def test_every_semantic_seam_is_covered_once_and_ids_are_unique(self) -> None:
        for version, fixture in self.fixtures.items():
            cases = fixture["cases"]
            expected_keys = [
                semantic_key
                for item in fixture["domain_manifest"]
                for semantic_key in item["expected_semantic_keys"]
            ]
            actual_keys = [case["expected_semantic_key"] for case in cases]
            with self.subTest(version=version):
                self.assertEqual(actual_keys, expected_keys)
                self.assertEqual(len(actual_keys), len(set(actual_keys)))
                for key in ("case_id", "case_semantic_id", "goal_text"):
                    values = [case[key] for case in cases]
                    self.assertEqual(len(values), len(set(values)), key)
                for index, case in enumerate(cases, start=1):
                    domain_id = case["domain_id"]
                    semantic_key = case["expected_semantic_key"]
                    self.assertTrue(semantic_key.startswith(domain_id + "."))
                    suffix = semantic_key.split(".", 1)[1]
                    self.assertEqual(case["case_id"], f"indpubv{version}_{index:03d}_{domain_id}_{suffix}")
                    self.assertEqual(case["case_semantic_id"], f"v{version}_{domain_id}_{suffix}")
                    self.assertEqual(case["steps"][0]["expected"]["semantic_key"], f"{domain_id}.hub")
                    self.assertEqual(case["steps"][1]["expected"]["semantic_key"], f"{domain_id}.hub")
                    self.assertEqual(case["steps"][2]["expected"]["semantic_key"], semantic_key)
                    self.assertEqual(case["steps"][3]["expected"]["semantic_key"], semantic_key)

    def test_bilingual_balance_and_utf8_content(self) -> None:
        for version, config in VERSIONS.items():
            fixture = self.fixtures[version]
            cases = fixture["cases"]
            raw = config["fixture_path"].read_bytes()
            with self.subTest(version=version):
                self.assertIn("독립".encode("utf-8"), raw)
                self.assertNotIn(b"\\u" + b"b3c5", raw.lower())
                self.assertEqual(Counter(case["locale"] for case in cases), config["locales"])
                self.assertEqual(Counter(fixture["coverage_contract"]["locales"]), config["locales"])
                for case in cases:
                    self.assertRegex(case["destination_name"]["ko"], r"[가-힣]")
                    self.assertRegex(case["destination_name"]["en"], r"[A-Za-z]")
                    self.assertTrue(case["authorized_role"])
                    self.assertTrue(case["governed_asset"])
                    self.assertTrue(case["lifecycle_state"])
                    self.assertTrue(case["provider_jurisdiction"])
                    if case["locale"] == "ko-KR":
                        self.assertRegex(case["goal_text"], r"[가-힣]")
                    else:
                        self.assertNotRegex(case["goal_text"], r"[가-힣]")
                        self.assertRegex(case["goal_text"], r"[A-Za-z]")

    def test_boundary_distribution_and_guard_behavior(self) -> None:
        for version, config in VERSIONS.items():
            fixture = self.fixtures[version]
            cases = fixture["cases"]
            by_domain: dict[str, Counter[str]] = defaultdict(Counter)
            for case in cases:
                by_domain[case["domain_id"]][case["boundary_kind"]] += 1
            with self.subTest(version=version):
                self.assertEqual(Counter(case["boundary_kind"] for case in cases), config["boundaries"])
                self.assertEqual(Counter(fixture["coverage_contract"]["boundary_kinds"]), config["boundaries"])
                self.assertEqual(set(by_domain), {item["domain_id"] for item in fixture["domain_manifest"]})
                for domain_id, counts in by_domain.items():
                    self.assertEqual(set(counts), BOUNDARIES, domain_id)
                    if version == 18:
                        self.assertEqual(set(counts.values()), {2}, domain_id)

                for case in cases:
                    guard = case["steps"][1]
                    boundary = case["boundary_kind"]
                    if boundary in FAIL_CLOSED_BOUNDARIES:
                        self.assertEqual(guard["expected"]["action"], "no_click")
                        self.assertEqual(guard["expected"]["outcome"], "fail_closed_to_domain_gateway")
                    elif boundary == "loading":
                        self.assertEqual(guard["expected"]["action"], "no_click")
                        self.assertEqual(guard["expected"]["outcome"], "hold_at_domain_gateway")
                    else:
                        self.assertEqual(guard["expected"]["action"], "click")

    def test_all_sensitive_or_consequential_controls_are_user_owned(self) -> None:
        for version, config in VERSIONS.items():
            fixture = self.fixtures[version]
            cases = fixture["cases"]
            with self.subTest(version=version):
                self.assertEqual(Counter(case["safety_class"] for case in cases), config["safety_classes"])
                self.assertEqual(Counter(fixture["coverage_contract"]["safety_classes"]), config["safety_classes"])
                for case in cases:
                    self.assertIn(case["safety_class"], {"S", "C"})
                    self.assertEqual(case["final_action_policy"], "stop_before_action")
                    final = case["steps"][3]
                    self.assertEqual(final["expected"]["action"], "no_click")
                    self.assertIsNone(final["expected"]["label"])
                    self.assertIs(final["expected"]["stop_before_action"], True)
                    self.assertEqual(final["expected"]["final_control_owner"], "user")
                    dangerous = [element for element in final["elements"] if element["dangerous"]]
                    self.assertEqual(len(dangerous), 1)
                    self.assertTrue(dangerous[0]["clickable"])
                    self.assertTrue(dangerous[0]["enabled"])

    def test_official_sources_are_directly_traceable_to_each_domain_section(self) -> None:
        for version, config in VERSIONS.items():
            fixture = self.fixtures[version]
            source_sections = _source_sections(config["source_path"])
            manifest_by_domain = {item["domain_id"]: item for item in fixture["domain_manifest"]}
            cases_by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for case in fixture["cases"]:
                cases_by_domain[case["domain_id"]].append(case)
            with self.subTest(version=version):
                for domain_id, manifest in manifest_by_domain.items():
                    urls = manifest["official_evidence_urls"]
                    self.assertGreaterEqual(len(urls), 5, domain_id)
                    self.assertEqual(len(urls), len(set(urls)), domain_id)
                    self.assertTrue(all(url.startswith("https://") for url in urls), domain_id)
                    self.assertTrue(all(url in source_sections[domain_id] for url in urls), domain_id)
                    for case in cases_by_domain[domain_id]:
                        self.assertEqual(case["official_evidence_urls"], urls)
                        self.assertIn(case["official_provider_surface_url"], urls)
                        self.assertIn(case["official_provider_surface_url"], case["goal_text"])
                for domain_id, domain_cases in cases_by_domain.items():
                    self.assertEqual(
                        {case["official_provider_surface_url"] for case in domain_cases},
                        set(manifest_by_domain[domain_id]["official_evidence_urls"]),
                        domain_id,
                    )

    def test_blindness_contract_and_no_runtime_bindings(self) -> None:
        for version, fixture in self.fixtures.items():
            provenance = fixture["provenance"]
            policy = fixture["authoring_policy"]
            with self.subTest(version=version):
                self.assertIs(provenance["catalog_or_runtime_implementation_inspected"], False)
                self.assertIs(provenance["runtime_evaluation_used"], False)
                self.assertIs(provenance["sealed_failure_or_goal_data_used"], False)
                self.assertIs(provenance["fixed_ui_paths_used"], False)
                self.assertIs(policy["independent_of_runtime"], True)
                self.assertIs(policy["implementation_ids_are_not_expected_outputs"], True)
                self.assertIs(policy["adapter_must_be_frozen_before_runtime_evaluation"], True)
                self.assertIs(policy["final_controls_remain_user_owned"], True)
                self.assertTrue(all(case["tuning_allowed"] is False for case in fixture["cases"]))
                keys = {
                    value
                    for value in _walk(fixture)
                    if isinstance(value, str) and value in FORBIDDEN_RUNTIME_KEYS
                }
                self.assertFalse(keys, f"runtime-bound or UI-path keys present: {sorted(keys)}")

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
