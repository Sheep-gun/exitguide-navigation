from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
EQUIVALENCE_PATH = ROOT / "fixtures" / "navigation" / "function-equivalence.v1.json"

RISK_RANK = {"low": 0, "medium": 1, "high": 2}
AUTOMATION_RANK = {"safe_navigation": 0, "never_auto": 1}
STOP_RANK = {"on_destination_screen": 0, "before_action": 1}


def _canonical_document_bytes(payload: dict[str, Any]) -> bytes:
    hash_payload = copy.deepcopy(payload)
    hash_payload["integrity"].pop("canonical_sha256")
    return json.dumps(
        hash_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reverse_object_order(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _reverse_object_order(value[key])
            for key in reversed(list(value))
        }
    if isinstance(value, list):
        return [_reverse_object_order(item) for item in value]
    return value


class NavigationFunctionEquivalenceUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.fixture = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
        cls.functions = {
            item["function_id"]: item for item in cls.catalog["functions"]
        }
        cls.intents = cls.catalog["intents"]
        cls.classes = cls.fixture["classes"]

    def test_scope_version_and_exact_class_shape(self) -> None:
        self.assertEqual(self.catalog["catalog_version"], "15.0.0")
        self.assertEqual(self.fixture["schema_version"], "1.0.0")
        self.assertEqual(self.fixture["equivalence_version"], "1.1.0")
        self.assertEqual(self.fixture["equivalence_kind"], "true_equivalent")
        self.assertEqual(self.fixture["provenance"]["catalog_version"], "15.0.0")
        self.assertEqual(
            self.fixture["provenance"]["v15_added_marker"],
            "v15_role_governed_operations",
        )
        self.assertEqual(
            self.fixture["provenance"]["v15_coverage_document"],
            "docs/NAVIGATION_COVERAGE_GAPS_V15.md",
        )
        self.assertEqual(len(self.classes), 10)
        self.assertEqual(
            sum(len(item["alias_function_ids"]) for item in self.classes),
            10,
        )
        self.assertEqual(
            {item["classification"] for item in self.classes},
            {"true_equivalent"},
        )
        for rejected_category in (
            "context_distinct",
            "parent_child",
            "parent-child",
            "unsafe_to_merge",
        ):
            self.assertNotIn(rejected_category, self.fixture)

        all_members: list[str] = []
        for item in self.classes:
            self.assertEqual(len(item["alias_function_ids"]), 1)
            members = [item["canonical_function_id"], *item["alias_function_ids"]]
            self.assertEqual(len(members), 2)
            self.assertNotIn(item["canonical_function_id"], item["alias_function_ids"])
            all_members.extend(members)
            self.assertTrue(item["rationale"].strip())
            self.assertTrue(item["evidence"]["semantic_basis"].strip())
            self.assertTrue(item["evidence"]["terminal_outcome"].strip())
            self.assertEqual(item["provenance"]["member_generation"], "pre_v13")

        self.assertEqual(len(all_members), 20)
        self.assertEqual(len(set(all_members)), 20, "equivalence classes must be disjoint")
        self.assertTrue(set(all_members).issubset(self.functions))

    def test_alias_graph_is_acyclic_and_resolves_to_declared_canonical(self) -> None:
        alias_to_canonical = {
            alias: item["canonical_function_id"]
            for item in self.classes
            for alias in item["alias_function_ids"]
        }
        declared_canonicals = {item["canonical_function_id"] for item in self.classes}
        self.assertTrue(declared_canonicals.isdisjoint(alias_to_canonical))

        for start in alias_to_canonical:
            current = start
            visited: set[str] = set()
            while current in alias_to_canonical:
                self.assertNotIn(current, visited, f"equivalence cycle from {start}")
                visited.add(current)
                current = alias_to_canonical[current]
            self.assertIn(current, declared_canonicals)

    def test_members_are_terminal_compatible_and_consumed_by_intent_routes(self) -> None:
        for item in self.classes:
            members = [item["canonical_function_id"], *item["alias_function_ids"]]
            terminal_values = {bool(self.functions[member]["terminal"]) for member in members}
            self.assertEqual(terminal_values, {True})

            recorded = {
                evidence["function_id"]: evidence
                for evidence in item["evidence"]["member_consumption"]
            }
            self.assertEqual(set(recorded), set(members))
            for member in members:
                consumers = [
                    intent
                    for intent in self.intents
                    if intent.get("terminal_function") == member
                ]
                self.assertEqual(len(consumers), 1, f"{member} default-terminal consumers")
                consumer = consumers[0]
                route_ids = [step["function_id"] for step in consumer.get("route", [])]
                self.assertTrue(route_ids)
                self.assertEqual(route_ids[-1], member)
                self.assertEqual(recorded[member]["intent_id"], consumer["intent_id"])
                self.assertEqual(
                    set(recorded[member]["uses"]),
                    {"default_terminal", "route_endpoint"},
                )

    def test_composite_safety_is_the_conservative_member_join(self) -> None:
        for item in self.classes:
            members = [item["canonical_function_id"], *item["alias_function_ids"]]
            member_rows = [self.functions[member] for member in members]
            expected_state = any(bool(row["state_changing"]) for row in member_rows)
            expected_risk = max(
                (row["risk_level"] for row in member_rows), key=RISK_RANK.__getitem__
            )
            expected_automation = max(
                (row["automation_policy"] for row in member_rows),
                key=AUTOMATION_RANK.__getitem__,
            )
            expected_stop = max(
                (row["stop_policy"] for row in member_rows), key=STOP_RANK.__getitem__
            )
            composite = item["composite_safety"]
            self.assertEqual(composite["state_changing"], expected_state)
            self.assertEqual(composite["risk_level"], expected_risk)
            self.assertEqual(composite["automation_policy"], expected_automation)
            self.assertEqual(composite["stop_policy"], expected_stop)

            boundary = composite["user_owned_boundary"]
            self.assertEqual(boundary["owner"], "user")
            self.assertEqual(boundary["stop_policy"], composite["stop_policy"])
            consuming_intent_ids = {
                evidence["intent_id"]
                for evidence in item["evidence"]["member_consumption"]
            }
            confirmation_required = any(
                intent.get("desired_state") == "user_confirmation_required"
                for intent in self.intents
                if intent["intent_id"] in consuming_intent_ids
            )
            self.assertEqual(boundary["confirmation_required"], confirmation_required)
            if confirmation_required:
                self.assertIn("user_confirmation_required", composite["preserved_constraints"])
                self.assertEqual(boundary["stop_policy"], "before_action")
            else:
                self.assertEqual(boundary["type"], "destination_screen")
                self.assertIn("navigation_only", composite["preserved_constraints"])

            for row in member_rows:
                self.assertGreaterEqual(
                    RISK_RANK[composite["risk_level"]], RISK_RANK[row["risk_level"]]
                )
                self.assertGreaterEqual(
                    AUTOMATION_RANK[composite["automation_policy"]],
                    AUTOMATION_RANK[row["automation_policy"]],
                )
                self.assertGreaterEqual(
                    STOP_RANK[composite["stop_policy"]], STOP_RANK[row["stop_policy"]]
                )
                self.assertGreaterEqual(
                    int(composite["state_changing"]), int(bool(row["state_changing"]))
                )

    def test_logical_counts(self) -> None:
        alias_to_canonical = {
            alias: item["canonical_function_id"]
            for item in self.classes
            for alias in item["alias_function_ids"]
        }
        canonicalize = lambda function_id: alias_to_canonical.get(function_id, function_id)

        physical_functions = len(self.functions)
        physical_intents = len(self.intents)
        physical_default_terminals = {
            intent["terminal_function"] for intent in self.intents
        }
        member_terminal_consumers = {
            member: {
                intent["intent_id"]
                for intent in self.intents
                if intent["terminal_function"] == member
            }
            for item in self.classes
            for member in [item["canonical_function_id"], *item["alias_function_ids"]]
        }
        intent_reduction = sum(
            len(
                set().union(
                    *(
                        member_terminal_consumers[member]
                        for member in [
                            item["canonical_function_id"],
                            *item["alias_function_ids"],
                        ]
                    )
                )
            )
            - 1
            for item in self.classes
        )
        logical_default_terminals = {
            canonicalize(intent["terminal_function"]) for intent in self.intents
        }

        self.assertEqual(physical_functions, 2866)
        self.assertEqual(physical_intents, 2660)
        self.assertEqual(len(physical_default_terminals), 2658)
        self.assertEqual(physical_functions - len(alias_to_canonical), 2856)
        self.assertEqual(physical_intents - intent_reduction, 2650)
        self.assertEqual(len(logical_default_terminals), 2648)
        self.assertEqual(
            self.fixture["audit_counts"],
            {
                "equivalence_alias_count": 10,
                "equivalence_class_count": 10,
                "logical_default_terminal_count": 2648,
                "logical_function_count": 2856,
                "logical_intent_count": 2650,
                "physical_default_terminal_count": 2658,
                "physical_function_count": 2866,
                "physical_intent_count": 2660,
                "v13_added_function_count": 252,
                "v14_added_function_count": 252,
                "v15_added_function_count": 252,
            },
        )

    def test_v13_v14_and_v15_added_functions_are_not_merged(self) -> None:
        members = {
            member
            for item in self.classes
            for member in [item["canonical_function_id"], *item["alias_function_ids"]]
        }
        added_by_generation = {
            generation: {
                function_id
                for function_id, row in self.functions.items()
                if self.fixture["provenance"][f"{generation}_added_marker"]
                in row.get("legacy_tags", [])
            }
            for generation in ("v13", "v14", "v15")
        }
        seen_added_ids: set[str] = set()
        for generation, added_ids in added_by_generation.items():
            self.assertEqual(
                len(added_ids),
                self.fixture["audit_counts"][f"{generation}_added_function_count"],
            )
            self.assertTrue(added_ids.isdisjoint(members))
            self.assertTrue(added_ids.isdisjoint(seen_added_ids))
            seen_added_ids.update(added_ids)

    def test_all_240_v15_terminals_remain_distinct_logical_destinations(self) -> None:
        marker = self.fixture["provenance"]["v15_added_marker"]
        v15_added = {
            function_id
            for function_id, row in self.functions.items()
            if marker in row.get("legacy_tags", [])
        }
        v15_terminals = {
            function_id
            for function_id in v15_added
            if bool(self.functions[function_id]["terminal"])
        }
        v15_hubs = v15_added - v15_terminals
        equivalence_members = {
            member
            for item in self.classes
            for member in [item["canonical_function_id"], *item["alias_function_ids"]]
        }
        alias_to_canonical = {
            alias: item["canonical_function_id"]
            for item in self.classes
            for alias in item["alias_function_ids"]
        }

        self.assertEqual(len(v15_added), 252)
        self.assertEqual(len(v15_terminals), 240)
        self.assertEqual(len(v15_hubs), 12)
        self.assertTrue(v15_added.isdisjoint(equivalence_members))
        self.assertTrue(v15_terminals.isdisjoint(alias_to_canonical))

        v15_terminal_consumers = {
            function_id: [
                intent
                for intent in self.intents
                if intent["terminal_function"] == function_id
            ]
            for function_id in v15_terminals
        }
        self.assertEqual(set(v15_terminal_consumers), v15_terminals)
        for function_id, consumers in v15_terminal_consumers.items():
            self.assertEqual(len(consumers), 1, function_id)
            self.assertTrue(consumers[0]["intent_id"].startswith("v15_"))
            self.assertEqual(consumers[0]["route"][-1]["function_id"], function_id)
            self.assertEqual(alias_to_canonical.get(function_id, function_id), function_id)

    def test_canonical_serialization_and_hash_are_deterministic(self) -> None:
        first = _canonical_document_bytes(self.fixture)
        second = _canonical_document_bytes(_reverse_object_order(self.fixture))
        self.assertEqual(first, second)
        digest = hashlib.sha256(first).hexdigest()
        self.assertEqual(self.fixture["integrity"]["hash_algorithm"], "sha256")
        self.assertEqual(self.fixture["integrity"]["canonical_sha256"], digest)


if __name__ == "__main__":
    unittest.main()
