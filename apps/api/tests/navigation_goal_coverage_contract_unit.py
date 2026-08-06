from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "Validate-NavigationGoalCoverage.py"
SPEC = importlib.util.spec_from_file_location("goal_coverage_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_repository_goal_coverage_is_valid() -> None:
    report = MODULE.validate_coverage(
        MODULE.DEFAULT_COVERAGE,
        MODULE.DEFAULT_SCHEMA,
        MODULE.DEFAULT_SPLITS,
    )
    assert report["apps"] == 11
    assert report["goals_per_app"] == 5
    assert report["coverage_cells"] == 55
    assert report["successful_cells"] == 13
    assert report["terminal_cells"] == 24
    assert report["incomplete_cells"] == 31
    assert report["split_counts"] == {"collection": 11}
    assert report["dangerous_action_auto_executed"] == 0


def test_goal_coverage_rejects_automatic_dangerous_action() -> None:
    payload = json.loads(MODULE.DEFAULT_COVERAGE.read_text(encoding="utf-8"))
    payload["apps"][0]["goals"][0]["dangerous_action_auto_executed"] = True
    with tempfile.TemporaryDirectory() as temporary:
        coverage = Path(temporary) / "coverage.json"
        coverage.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            MODULE.validate_coverage(coverage, MODULE.DEFAULT_SCHEMA, MODULE.DEFAULT_SPLITS)
        except ValueError as error:
            assert "False was expected" in str(error)
        else:
            raise AssertionError("dangerous automatic action must be rejected")


def test_every_current_app_is_a_collection_source() -> None:
    payload = json.loads(MODULE.DEFAULT_COVERAGE.read_text(encoding="utf-8"))
    manifest = json.loads(MODULE.DEFAULT_SPLITS.read_text(encoding="utf-8"))
    assert {app["split"] for app in payload["apps"]} == {"collection"}
    assert {entry["split"] for entry in manifest["entries"]} == {"collection"}
    assert len(payload["apps"]) == len(manifest["entries"]) == 11


def test_app_specific_evidence_is_owned_by_the_matching_package() -> None:
    payload = json.loads(MODULE.DEFAULT_COVERAGE.read_text(encoding="utf-8"))
    evidence_owners = {
        "docs/evidence/jejuair-": "com.parksmt.jejuair.android16",
        "docs/evidence/x-": "com.twitter.android",
    }
    for app in payload["apps"]:
        for goal in app["goals"]:
            for reference in goal["evidence_refs"]:
                for prefix, expected_package in evidence_owners.items():
                    if reference.startswith(prefix):
                        assert app["app_package"] == expected_package, (
                            reference,
                            app["app_package"],
                            expected_package,
                        )


if __name__ == "__main__":
    test_repository_goal_coverage_is_valid()
    test_goal_coverage_rejects_automatic_dangerous_action()
    test_every_current_app_is_a_collection_source()
    test_app_specific_evidence_is_owned_by_the_matching_package()
    print("navigation goal coverage contract checks passed")
