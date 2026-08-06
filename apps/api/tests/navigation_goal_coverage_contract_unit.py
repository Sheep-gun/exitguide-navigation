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
    assert report["successful_cells"] == 11
    assert report["terminal_cells"] == 19
    assert report["incomplete_cells"] == 36
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


if __name__ == "__main__":
    test_repository_goal_coverage_is_valid()
    test_goal_coverage_rejects_automatic_dangerous_action()
    test_every_current_app_is_a_collection_source()
    print("navigation goal coverage contract checks passed")
