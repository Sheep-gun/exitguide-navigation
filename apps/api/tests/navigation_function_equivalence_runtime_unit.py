from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.services.navigation_function_catalog import (
    CatalogValidationError,
    DEFAULT_CATALOG_PATH,
    NEVER_AUTO_STOP_POLICIES,
    NavigationFunctionCatalog,
    _cached_catalog,
    _catalog_source_fingerprint,
    validate_equivalence_payload,
)


EQUIVALENCE_PATH = DEFAULT_CATALOG_PATH.with_name("function-equivalence.v1.json")


def _minimal_catalog_payload() -> dict[str, object]:
    def function(function_id: str, *, terminal: bool) -> dict[str, object]:
        return {
            "function_id": function_id,
            "domain": "test",
            "name_ko": function_id,
            "name_en": function_id,
            "description": function_id,
            "risk_level": "low",
            "automation_policy": "safe_navigation",
            "terminal": terminal,
            "state_changing": False,
            "stop_policy": "on_destination_screen" if terminal else "continue",
            "aliases": {"en-US": [function_id, "merge route"]},
            "positive_context": [],
            "negative_context": [],
        }

    return {
        "catalog_version": "equivalence-runtime-test",
        "functions": [
            function("test.gateway", terminal=False),
            function("test.canonical", terminal=True),
            function("test.alias", terminal=True),
        ],
        "intents": [
            {
                "intent_id": "raw_alias_intent",
                "terminal_function": "test.alias",
                "patterns": ["merge route"],
                "route": [
                    {"function_id": "test.gateway", "weight": 0.4},
                    {"function_id": "test.canonical", "weight": 0.6},
                    {"function_id": "test.alias", "weight": 0.9},
                ],
                "avoid_functions": ["test.alias", "test.canonical"],
            }
        ],
    }


def _minimal_equivalence_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "equivalence_version": "test",
        "equivalence_kind": "true_equivalent",
        "classes": [
            {
                "canonical_function_id": "test.canonical",
                "alias_function_ids": ["test.alias"],
                "classification": "true_equivalent",
                "composite_safety": {
                    "risk_level": "low",
                    "automation_policy": "safe_navigation",
                    "state_changing": False,
                    "stop_policy": "on_destination_screen",
                },
            }
        ],
    }


def _assert_production_classes(catalog: NavigationFunctionCatalog) -> None:
    payload = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    assert len(payload["classes"]) == 10
    for equivalence_class in payload["classes"]:
        canonical = equivalence_class["canonical_function_id"]
        members = [canonical, *equivalence_class["alias_function_ids"]]
        safety = equivalence_class["composite_safety"]

        logical = catalog.function(canonical)
        assert logical is not None
        assert logical.function_id == canonical
        assert logical.canonical_function_id == canonical
        assert logical.risk_level == safety["risk_level"]
        assert logical.automation_policy == safety["automation_policy"]
        assert logical.state_changing is safety["state_changing"]
        assert logical.stop_policy == safety["stop_policy"]
        if logical.state_changing or logical.risk_level == "high":
            assert logical.automation_policy == "never_auto"
        if logical.state_changing:
            assert logical.stop_policy in NEVER_AUTO_STOP_POLICIES

        for member in members:
            raw = catalog.raw_function(member)
            assert raw is not None
            assert raw.function_id == member
            assert raw.raw_function_id == member
            assert raw.canonical_function_id == canonical
            assert catalog.function(member) == logical
            assert catalog.canonical_function(member) == logical

        label = catalog.raw_function(members[-1]).name_en
        matches = catalog.match_candidate(label=label, limit=100, locale="en-US")
        projected = [match for match in matches if match.function_id == canonical]
        assert len(projected) == 1
        assert projected[0].matched_function_id in members
        assert projected[0].canonical_function_id == canonical
        assert projected[0].automation_policy == safety["automation_policy"]
        assert projected[0].state_changing is safety["state_changing"]


def _assert_original_intent_then_projection(catalog: NavigationFunctionCatalog) -> None:
    source = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    equivalence = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    intents = {intent["terminal_function"]: intent for intent in source["intents"]}
    for equivalence_class in equivalence["classes"]:
        canonical = equivalence_class["canonical_function_id"]
        raw_terminal = equivalence_class["alias_function_ids"][0]
        source_intent = intents[raw_terminal]
        plan = catalog.plan_goal(source_intent["patterns"][0])
        assert plan.intent == source_intent["intent_id"]
        assert plan.raw_terminal_function == raw_terminal
        assert plan.terminal_function == canonical
        assert plan.canonical_terminal_function == canonical
        route_ids = [function_id for function_id, _ in plan.preferred_functions]
        assert route_ids[-1] == canonical
        assert len(route_ids) == len(set(route_ids))
        assert canonical not in plan.avoid_functions


def _assert_v15_terminals_are_not_equivalence_members(
    catalog: NavigationFunctionCatalog,
) -> None:
    source = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    equivalence = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    marker = equivalence["provenance"]["v15_added_marker"]
    v15_rows = [
        item
        for item in source["functions"]
        if marker in item.get("legacy_tags", [])
    ]
    v15_terminals = {
        item["function_id"] for item in v15_rows if bool(item["terminal"])
    }
    v15_hubs = {
        item["function_id"] for item in v15_rows if not bool(item["terminal"])
    }
    equivalence_members = {
        member
        for equivalence_class in equivalence["classes"]
        for member in [
            equivalence_class["canonical_function_id"],
            *equivalence_class["alias_function_ids"],
        ]
    }
    intents_by_terminal: dict[str, list[dict[str, object]]] = {}
    for intent in source["intents"]:
        intents_by_terminal.setdefault(intent["terminal_function"], []).append(intent)

    assert len(v15_rows) == 252
    assert len(v15_terminals) == 240
    assert len(v15_hubs) == 12
    assert v15_terminals.isdisjoint(equivalence_members)
    for function_id in v15_terminals:
        raw = catalog.raw_function(function_id)
        logical = catalog.function(function_id)
        canonical = catalog.canonical_function(function_id)
        assert raw is not None
        assert logical is not None
        assert canonical is not None
        assert raw.function_id == function_id
        assert raw.raw_function_id == function_id
        assert raw.canonical_function_id == function_id
        assert logical.function_id == function_id
        assert canonical.function_id == function_id
        assert logical == raw
        consumers = intents_by_terminal.get(function_id, [])
        assert len(consumers) == 1
        assert str(consumers[0]["intent_id"]).startswith("v15_")
        assert consumers[0]["route"][-1]["function_id"] == function_id


def _assert_non_equivalent_retrieval_unchanged(
    catalog: NavigationFunctionCatalog,
    database_path: Path,
) -> None:
    without_equivalence = NavigationFunctionCatalog(
        database_path,
        DEFAULT_CATALOG_PATH,
        equivalence_path=database_path.with_name("missing-equivalence.json"),
    )
    for goal in ("로그인하고 싶어", "Change language to Korean"):
        logical = catalog.plan_goal(goal)
        physical = without_equivalence.plan_goal(goal)
        assert (
            logical.intent,
            logical.terminal_function,
            logical.preferred_functions,
            logical.avoid_functions,
            logical.confidence,
        ) == (
            physical.intent,
            physical.terminal_function,
            physical.preferred_functions,
            physical.avoid_functions,
            physical.confidence,
        )
    kwargs = {
        "label": "Payments and subscriptions",
        "nearby_text": "Account Settings Payment method",
        "position": "middle",
    }
    logical_matches = catalog.match_candidate(**kwargs)
    physical_matches = without_equivalence.match_candidate(**kwargs)
    assert [(item.function_id, item.score) for item in logical_matches] == [
        (item.function_id, item.score) for item in physical_matches
    ]


def _assert_validator(catalog: NavigationFunctionCatalog) -> None:
    payload = json.loads(EQUIVALENCE_PATH.read_text(encoding="utf-8"))
    validate_equivalence_payload(payload, catalog._functions)

    unsafe = deepcopy(payload)
    unsafe.pop("integrity", None)
    unsafe["classes"][1]["composite_safety"]["automation_policy"] = "safe_navigation"
    try:
        validate_equivalence_payload(unsafe, catalog._functions)
    except CatalogValidationError as error:
        assert "weakens member automation_policy" in str(error)
        assert "preserve never_auto" in str(error)
    else:
        raise AssertionError("a weakened never_auto boundary must be rejected")

    cyclic = deepcopy(payload)
    cyclic.pop("integrity", None)
    first = cyclic["classes"][0]["canonical_function_id"]
    second = cyclic["classes"][1]["canonical_function_id"]
    cyclic["classes"][0]["alias_function_ids"] = [second]
    cyclic["classes"][1]["alias_function_ids"] = [first]
    try:
        validate_equivalence_payload(cyclic, catalog._functions)
    except CatalogValidationError as error:
        assert "multiple equivalence classes" in str(error)
        assert "contain a cycle" in str(error)
    else:
        raise AssertionError("overlapping cyclic classes must be rejected")


def _assert_route_and_revision_runtime(temporary_directory: str) -> None:
    root = Path(temporary_directory)
    catalog_path = root / "function-catalog.v1.json"
    equivalence_path = root / "function-equivalence.v1.json"
    database_path = root / "catalog.sqlite"
    catalog_path.write_text(
        json.dumps(_minimal_catalog_payload(), ensure_ascii=False),
        encoding="utf-8",
    )
    equivalence_path.write_text(
        json.dumps(_minimal_equivalence_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    first_fingerprint = _catalog_source_fingerprint(catalog_path)
    first = _cached_catalog(str(database_path), str(catalog_path), first_fingerprint)
    equivalence_path.write_text(
        equivalence_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    second_fingerprint = _catalog_source_fingerprint(catalog_path)
    second = _cached_catalog(str(database_path), str(catalog_path), second_fingerprint)
    assert first_fingerprint != second_fingerprint
    assert first is not second
    assert first.stats()["catalog_fingerprint"] != second.stats()["catalog_fingerprint"]
    assert first.stats()["catalog_sha256"] != second.stats()["catalog_sha256"]

    plan = second.plan_goal("merge route")
    assert plan.intent == "raw_alias_intent"
    assert plan.raw_terminal_function == "test.alias"
    assert plan.terminal_function == "test.canonical"
    assert plan.preferred_functions == (
        ("test.gateway", 0.4),
        ("test.canonical", 0.9),
    )
    assert plan.avoid_functions == ()


def _assert_source_fingerprint_reads_unchanged_catalog_once(
    temporary_directory: str,
) -> None:
    catalog_path = Path(temporary_directory) / "fingerprint-source.json"
    equivalence_path = catalog_path.with_name("function-equivalence.v1.json")
    catalog_content = b'{"revision":1}'
    equivalence_content = b'{"equivalence_revision":1}'
    catalog_path.write_bytes(catalog_content)
    equivalence_path.write_bytes(equivalence_content)
    tracked_paths = {catalog_path.resolve(), equivalence_path.resolve()}
    original_read_bytes = Path.read_bytes
    read_counts = {path: 0 for path in tracked_paths}

    def counted_read_bytes(path: Path) -> bytes:
        resolved_path = path.resolve()
        if resolved_path in read_counts:
            read_counts[resolved_path] += 1
        return original_read_bytes(path)

    with patch.object(Path, "read_bytes", counted_read_bytes):
        first = _catalog_source_fingerprint(catalog_path)
        unchanged = _catalog_source_fingerprint(catalog_path)
        expected = hashlib.sha256(
            catalog_content + b"\0equivalence\0" + equivalence_content
        ).hexdigest()
        assert first == expected
        assert unchanged == first
        assert set(read_counts.values()) == {1}

        equivalence_path.write_bytes(b'{"equivalence_revision":2,"changed":true}')
        equivalence_changed = _catalog_source_fingerprint(catalog_path)
        assert equivalence_changed != first
        assert set(read_counts.values()) == {2}

        catalog_path.write_bytes(b'{"revision":2,"changed":true}')
        changed = _catalog_source_fingerprint(catalog_path)
        assert changed != equivalence_changed
        assert set(read_counts.values()) == {3}

    missing_path = Path(temporary_directory) / "missing" / "catalog.json"
    missing_fingerprint = _catalog_source_fingerprint(missing_path)
    expected_missing_fingerprint = hashlib.sha256(
        f"missing:{missing_path.resolve()}".encode("utf-8")
    ).hexdigest()
    assert missing_fingerprint == expected_missing_fingerprint


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        _assert_source_fingerprint_reads_unchanged_catalog_once(temporary_directory)
        database_path = Path(temporary_directory) / "production.sqlite"
        catalog = NavigationFunctionCatalog(database_path)
        stats = catalog.stats()
        assert stats["physical_function_count"] == 2866
        assert stats["logical_function_count"] == 2856
        assert stats["physical_intent_count"] == 2660
        assert stats["logical_intent_count"] == 2650
        assert stats["physical_default_terminal_count"] == 2658
        assert stats["logical_default_terminal_count"] == 2648
        assert stats["equivalence_class_count"] == 10
        assert stats["equivalence_alias_count"] == 10
        assert len(str(stats["catalog_fingerprint"])) == 64
        assert len(str(stats["equivalence_sha256"])) == 64

        _assert_production_classes(catalog)
        _assert_original_intent_then_projection(catalog)
        _assert_v15_terminals_are_not_equivalence_members(catalog)
        _assert_non_equivalent_retrieval_unchanged(catalog, database_path)
        _assert_validator(catalog)
        _assert_route_and_revision_runtime(temporary_directory)

    print("navigation function equivalence runtime checks ok")


if __name__ == "__main__":
    main()
