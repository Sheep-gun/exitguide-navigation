from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COVERAGE = ROOT / "db" / "navigation_goal_coverage_v1.json"
DEFAULT_SCHEMA = ROOT / "db" / "navigation_goal_coverage_v1.schema.json"
DEFAULT_SPLITS = ROOT / "db" / "navigation_coverage_split_v1.json"
SUCCESS_STATUSES = {"destination_reached", "safe_boundary_reached"}
FINAL_STATUSES = {
    "destination_reached",
    "safe_boundary_reached",
    "not_supported",
    "not_testable",
}
EXPECTED_SPLIT_COUNTS = {"collection": 7, "locked_holdout": 3, "validation": 1}


def validate_coverage(
    coverage_path: Path,
    schema_path: Path,
    split_manifest_path: Path,
) -> dict[str, Any]:
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    splits = json.loads(split_manifest_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(coverage),
        key=lambda item: list(item.path),
    )
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "$"
        raise ValueError(f"coverage contract error at {location}: {first.message}")

    split_by_package = {
        str(entry["app_package"]): str(entry["split"])
        for entry in splits.get("entries", [])
    }
    goal_order = list(coverage["goal_order"])
    seen_apps: set[str] = set()
    successful_cells = 0
    terminal_cells = 0
    split_counts = {key: 0 for key in EXPECTED_SPLIT_COUNTS}
    manifest_packages = set(split_by_package)
    for app in coverage["apps"]:
        package = str(app["app_package"])
        if package in seen_apps:
            raise ValueError(f"duplicate app coverage: {package}")
        seen_apps.add(package)
        if split_by_package.get(package) != app["split"]:
            raise ValueError(f"coverage split differs from manifest for {package}")
        split_counts[str(app["split"])] += 1
        if [entry["goal_id"] for entry in app["goals"]] != goal_order:
            raise ValueError(f"goal coverage must follow goal_order for {package}")
        if app["split"] == "locked_holdout" and any(
            entry["status"] != "not_explored" for entry in app["goals"]
        ) and not (
            coverage["collection_frozen_at"]
            and coverage["holdout_evaluation_started_at"]
        ):
            raise ValueError(
                f"locked holdout cannot be evaluated before collection freeze: {package}"
            )
        for entry in app["goals"]:
            status = str(entry["status"])
            if status in FINAL_STATUSES:
                terminal_cells += 1
                if entry["evidence_level"] != "real_device_verified":
                    raise ValueError("terminal coverage requires real_device_verified evidence")
                if not entry["evidence_refs"] or not entry["last_observed_at"]:
                    raise ValueError("terminal coverage requires evidence and observation time")
                if not entry["notes"].strip():
                    raise ValueError("terminal coverage requires an evidence summary")
            if status in SUCCESS_STATUSES:
                successful_cells += 1
            if status == "not_testable" and entry["blocking_issue"] not in {
                "account_state",
                "region_policy",
                "service_policy",
                "login_required",
                "permission_required",
            }:
                raise ValueError("not_testable requires a durable account or policy blocker")
            if status == "not_supported" and entry["blocking_issue"] is not None:
                raise ValueError("not_supported cannot be caused by an environment blocker")
            if status == "not_explored" and (
                entry["evidence_level"] != "none" or entry["evidence_refs"]
            ):
                raise ValueError("not_explored coverage cannot carry evidence")
            if entry["dangerous_action_auto_executed"] is not False:
                raise ValueError("dangerous actions must never be auto-executed")

    if seen_apps != manifest_packages:
        missing = sorted(manifest_packages - seen_apps)
        unexpected = sorted(seen_apps - manifest_packages)
        raise ValueError(f"coverage app set differs from manifest: missing={missing}, unexpected={unexpected}")
    if split_counts != EXPECTED_SPLIT_COUNTS:
        raise ValueError(
            f"coverage split counts must be {EXPECTED_SPLIT_COUNTS}, got {split_counts}"
        )

    coverage_cells = len(seen_apps) * len(goal_order)

    return {
        "valid": True,
        "apps": len(seen_apps),
        "goals_per_app": len(goal_order),
        "coverage_cells": coverage_cells,
        "successful_cells": successful_cells,
        "terminal_cells": terminal_cells,
        "incomplete_cells": coverage_cells - terminal_cells,
        "split_counts": split_counts,
        "dangerous_action_auto_executed": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Navigation goal coverage.")
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    arguments = parser.parse_args()
    report = validate_coverage(
        arguments.coverage.resolve(),
        arguments.schema.resolve(),
        arguments.splits.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
