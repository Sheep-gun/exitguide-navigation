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
    assert report["successful_cells"] == 6
    assert report["terminal_cells"] == 10
    assert report["incomplete_cells"] == 45
    assert report["split_counts"] == {
        "collection": 7,
        "locked_holdout": 3,
        "validation": 1,
    }
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


def test_goal_coverage_rejects_holdout_evaluation_before_collection_freeze() -> None:
    payload = json.loads(MODULE.DEFAULT_COVERAGE.read_text(encoding="utf-8"))
    holdout = next(app for app in payload["apps"] if app["split"] == "locked_holdout")
    holdout["goals"][0].update(
        {
            "status": "not_testable",
            "display_status_ko": "현재 계정에서 검증 불가",
            "evidence_level": "real_device_verified",
            "evidence_refs": ["runtime:test"],
            "last_observed_at": "2026-08-04T09:00:00+09:00",
            "blocking_issue": "account_state",
            "notes": "holdout must remain sealed until collection is frozen",
        }
    )
    with tempfile.TemporaryDirectory() as temporary:
        coverage = Path(temporary) / "coverage.json"
        coverage.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            MODULE.validate_coverage(coverage, MODULE.DEFAULT_SCHEMA, MODULE.DEFAULT_SPLITS)
        except ValueError as error:
            assert "before collection freeze" in str(error)
        else:
            raise AssertionError("locked holdout must remain sealed before collection freeze")


if __name__ == "__main__":
    test_repository_goal_coverage_is_valid()
    test_goal_coverage_rejects_automatic_dangerous_action()
    test_goal_coverage_rejects_holdout_evaluation_before_collection_freeze()
    print("navigation goal coverage contract checks passed")
