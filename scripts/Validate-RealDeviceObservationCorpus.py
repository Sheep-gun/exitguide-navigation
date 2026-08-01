from __future__ import annotations

"""Fail-closed validator for physical-device observation candidates.

Physical-device observations are deliberately non-canonical research evidence.
This validator accepts either an evidence-only capture or a completed
exploration candidate, but never promotes either one to the frozen V15 catalog.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
DEFAULT_MANIFEST = ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"
DEFAULT_OBSERVATION_ROOT = ROOT / ".artifacts" / "navigation-observations"
BASE_VALIDATOR_PATH = ROOT / "scripts" / "Validate-EmulatorObservationCorpus.py"
VALIDATION_ATTESTATION_FILENAME = "VALIDATED.json"
VALIDATION_CORE_ARTIFACTS = (
    "manifest.json",
    "checkpoint.json",
    "corpus.sqlite",
    "graph-candidate.sqlite",
    "observations.jsonl",
    "screens.jsonl",
)


def _load_base_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exitguide_emulator_observation_validator_base",
        BASE_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to import shared validation helpers from {BASE_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base_validator()

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.real_device_privacy import classify_human_text  # noqa: E402
from app.services.real_device_action_safety import (  # noqa: E402
    ACTION_GUARD_EVALUATION_PHASE,
    ACTION_GUARD_POLICY_VERSION,
    AutoActionGuardDecision,
    evaluate_auto_action_guard,
    guard_evidence_matches,
)
from app.services.real_device_goal_task_planner import (  # noqa: E402
    GoalTaskPlanningError,
    plan_applicable_goals,
)
from app.services.real_device_sensitive_navigation import (  # noqa: E402
    LOCAL_POLICY_VERSION as SENSITIVE_LOCAL_POLICY_VERSION,
    PERSISTED_GUARD_LABEL_BUCKET as SENSITIVE_GUARD_LABEL_BUCKET,
)
from app.services.universal_navigation_graph import fingerprint_goal  # noqa: E402

EXPECTED_PROVENANCE = "real_device_observation_candidate"
EXPECTED_REVIEW_STATUS = "unreviewed_candidate"
ALLOWED_LIFECYCLES = frozenset({"shadow", "candidate"})
ALLOWED_APP_STATUSES = frozenset(
    {"installed_observed", "installed_not_selected", "skipped_missing"}
)
FULL_COHORT_APP_STATUSES = frozenset({"installed_observed", "skipped_missing"})
ALLOWED_VALIDATION_PROFILES = frozenset(
    {"full_cohort", "partial_research", "dynamic_inventory"}
)
CAPTURE_PROFILES = frozenset({"capture_only", "in_progress"})
COMPLETED_PROFILES = frozenset({"completed", "completed_exploration"})
COLLECTOR_CAPTURE_MODES = frozenset({"capture_only", "dry_run"})
COLLECTOR_EXPLORE_MODES = frozenset({"safe_explore", "real_device_observation"})
COLLECTING_STATUSES = frozenset({"running", "collecting", "incomplete", "failed"})
COMPLETED_STATUSES = frozenset({"completed", "completed_with_boundaries"})
EXPLORATION_STAGE_INITIAL_CAPTURE = "initial_capture"
EXPLORATION_STAGE_NEUTRAL_DISCOVERY = "neutral_menu_discovery"
EXPLORATION_STAGE_GOAL_DIRECTED = "goal_directed_exploration"
ALLOWED_EXPLORATION_STAGES = frozenset(
    {
        EXPLORATION_STAGE_INITIAL_CAPTURE,
        EXPLORATION_STAGE_NEUTRAL_DISCOVERY,
        EXPLORATION_STAGE_GOAL_DIRECTED,
    }
)
DISCOVERY_TERMINAL_STATUSES = frozenset(
    {"discovery_budget_complete", "discovery_frontier_exhausted"}
)
GOAL_LINEAGE_FIELDS = (
    "candidate_id",
    "family_id",
    "terminal_policy",
    "source_run_id",
    "source_inventory_snapshot_id",
    "confidence",
    "candidate_rank",
    "source_artifact_sha256",
)
REAL_DEVICE_AUXILIARY_METRIC_DIMENSIONS = frozenset(
    {
        "task_summary",
        "neutral_discovery_coverage",
        "sensitive_local_policy",
        "sensitive_local_goal_signal",
    }
)
SENSITIVE_LOCAL_METRIC_DIMENSIONS = frozenset(
    {"sensitive_local_policy", "sensitive_local_goal_signal"}
)
SENSITIVE_LOCAL_POLICY_EVENTS = frozenset(
    {
        "dynamic_sensitive_metadata_only_capture",
        "sensitive_local_user_boundary",
        "sensitive_local_no_change",
        "sensitive_local_goal_entry_boundary",
        "sensitive_local_frontier_exhausted",
        "sensitive_local_safe_menu_selected",
    }
)
SENSITIVE_LOCAL_DECISION_EVENTS = frozenset(
    {
        "sensitive_local_goal_entry_boundary",
        "sensitive_local_frontier_exhausted",
        "sensitive_local_safe_menu_selected",
    }
)
SENSITIVE_LOCAL_DECISION_KEYS = frozenset(
    {
        "policy_version",
        "decision_source",
        "action",
        "reason",
        "candidate_count",
        "score_bucket",
        "goal_family_id",
        "terminal_policy",
        "matched_signal_ids",
        "selected_element_id",
        "semantic_commitment_sha256",
        "boundary_kind",
        "persisted_guard_label_bucket",
        "external_api_transfer_count",
        "human_text_persisted",
        "action_guard",
    }
)
SENSITIVE_LOCAL_SIGNAL_KEYS = frozenset(
    {
        "policy_version",
        "decision_source",
        "family_id",
        "matched_signal_ids",
        "selected_element_id",
        "semantic_commitment_sha256",
        "terminal_policy",
        "control_bucket",
        "auto_navigation_allowed",
        "action_guard",
        "external_api_transfer_count",
        "human_text_persisted",
    }
)
SENSITIVE_HUMAN_SEMANTIC_FIELDS = frozenset(
    {
        "text",
        "label",
        "title",
        "window_title",
        "selected_label",
        "raw_label",
        "visible_texts",
        "content_description",
        "inferred_label",
        "hint",
        "value",
        "resource_id",
        "resource_ids",
        "resource_ids_json",
        "view_id",
    }
)
EXPECTED_APPS: tuple[tuple[str, str], ...] = (
    ("YouTube", "com.google.android.youtube"),
    ("Netflix", "com.netflix.mediaclient"),
    ("배민", "com.sampleapp"),
    ("Coupang", "com.coupang.mobile"),
    ("제주항공", "com.parksmt.jejuair.android16"),
    ("X", "com.twitter.android"),
    ("Toss", "viva.republica.toss"),
    ("NH손보", "ni.mh.android.launcher"),
    ("정부24", "kr.go.minwon.m"),
    ("The건강보험", "kr.or.nhic"),
    ("MyKT", "com.ktshow.cs"),
    ("Naver", "com.nhn.android.search"),
    ("당근", "com.towneers.www"),
    ("Instagram", "com.instagram.android"),
)
EXPECTED_PACKAGE_TO_NAME = {package: name for name, package in EXPECTED_APPS}
EXPECTED_PACKAGES = frozenset(EXPECTED_PACKAGE_TO_NAME)
NEUTRAL_INVENTORY_GOAL = "앱 기능 메뉴 및 설정 진입점 조사"
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_INVENTORY_CANONICAL = {
    "version": BASE.EXPECTED_CATALOG_VERSION,
    "sha256": BASE.EXPECTED_CATALOG_SHA256,
    "equivalence_sha256": BASE.EXPECTED_EQUIVALENCE_SHA256,
    "counts": {
        "domains": BASE.EXPECTED_DOMAIN_COUNT,
        "functions": BASE.EXPECTED_FUNCTION_COUNT,
        "terminal_functions": BASE.EXPECTED_TERMINAL_FUNCTION_COUNT,
        "intents": BASE.EXPECTED_INTENT_COUNT,
    },
}
EXPECTED_CANONICAL = {
    "version": BASE.EXPECTED_CATALOG_VERSION,
    "sha256": BASE.EXPECTED_CATALOG_SHA256,
    "equivalence_sha256": BASE.EXPECTED_EQUIVALENCE_SHA256,
    "domain_count": BASE.EXPECTED_DOMAIN_COUNT,
    "function_count": BASE.EXPECTED_FUNCTION_COUNT,
    "terminal_function_count": BASE.EXPECTED_TERMINAL_FUNCTION_COUNT,
    "intent_count": BASE.EXPECTED_INTENT_COUNT,
}
REQUIRED_TABLES = frozenset((*BASE.REQUIRED_TABLES, "event_log"))
RAW_ARTIFACT_SUFFIXES = frozenset({".xml", ".uix", ".png", ".jpg", ".jpeg", ".webp"})
RAW_PATH_MARKERS = frozenset({"raw", "unredacted", "original", "uncensored", "unmasked"})
GOLD_WORDS = frozenset({"gold", "approved", "trusted", "canonical", "promoted", "active"})
PRIVACY_TEXT_SUFFIXES = frozenset({".json", ".jsonl", ".xml", ".txt", ".md", ".csv", ".tsv"})
XML_HUMAN_ATTRIBUTES = frozenset(
    {
        "text",
        "content-desc",
        "hint",
        "tooltip-text",
        "pane-title",
        "state-description",
        "error",
        "label",
        "accessibility-label",
        "accessibility-hint",
        "accessibility-value",
        "value",
    }
)
XML_STRUCTURAL_ATTRIBUTES = frozenset(
    {
        "resource-id",
        "class",
        "package",
        "index",
        "bounds",
        "checkable",
        "checked",
        "clickable",
        "enabled",
        "focusable",
        "focused",
        "scrollable",
        "long-clickable",
        "password",
        "selected",
        "visible-to-user",
    }
)
JSON_STRUCTURAL_FIELDS = frozenset(
    {
        "app_package",
        "package",
        "launchable_activity",
        "version_name",
        "version_code",
        "version_key",
        "candidate_id",
        "snapshot_id",
        "previous_snapshot_id",
        "task_id",
        "completed_task_ids",
        "screen_id",
        "element_id",
        "ui_element_id",
        "parent_id",
        "event_id",
        "record_id",
        "last_element_id",
        "goal_id",
        "run_id",
        "resource_id",
        "resource_ids",
        "resource_ids_json",
        "element_key",
        "reasons",
        "finding_contexts",
        "detected_sensitivity_categories",
        "collection_sensitivity_categories",
        "accessibility_tree_path",
        "screenshot_path",
        "tree_path",
        "artifact_path",
        "inventory_snapshot_path",
        "activity_name",
        "app_key",
        "screen_fingerprint",
        "status",
        "change_status",
        "observation_status",
        "decision_reason_code",
        "auto_action_guard",
        "policy_version",
        "evaluation_phase",
        "computed_final_or_consequential",
        "safe_menu_match",
        "sensitivity_handling",
        "sensitivity_categories",
        "coordinates",
        "action_coordinates",
        "scroll_direction",
        "scroll_distance",
        "scrollable_regions",
        "scrollable_region",
        "scroll_bounds",
        "screen_bounds",
        "window_bounds",
        "display_bounds",
        "structural_bounds",
        "bounds",
    }
)

# The collector targets a 78% page swipe. Integer coordinate rounding, window
# insets, and vendor Accessibility bounds justify a narrow 72--85% acceptance
# band, while still rejecting half-page and nearly full-page/overshooting
# gestures. This is evidence validation, not a recommendation-time heuristic.
AUTO_SCROLL_MIN_REGION_RATIO = 0.72
AUTO_SCROLL_MAX_REGION_RATIO = 0.85
AUTO_SCROLL_DISTANCE_TOLERANCE_PX = 1.0
AUTO_SCROLL_MAX_HORIZONTAL_DRIFT_RATIO = 0.05


def _finding(code: str, message: str, location: str = "") -> dict[str, str]:
    return BASE._finding(code, message, location)


def _load_json(path: Path) -> Any:
    return BASE._load_json(path)


def _sha256(path: Path) -> str:
    return BASE._sha256(path)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _report_jsonable(value: Any) -> Any:
    """Normalize validator diagnostics without leaking internal set types."""

    if isinstance(value, Mapping):
        return {
            str(key): _report_jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        normalized = [_report_jsonable(item) for item in value]
        return sorted(normalized, key=_canonical_json)
    if isinstance(value, (list, tuple)):
        return [_report_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _write_validation_attestation(run_dir: Path, report: Mapping[str, Any]) -> Path:
    """Persist a content-free, hash-bound marker only after a passing validation."""

    if report.get("ok") is not True:
        raise ValueError("cannot attest a failed validation")
    core_paths = {name: run_dir / name for name in VALIDATION_CORE_ARTIFACTS}
    if any(not path.is_file() or path.is_symlink() for path in core_paths.values()):
        raise ValueError("validation attestation requires all non-symlink core artifacts")
    manifest_path = core_paths["manifest.json"]
    screens_path = core_paths["screens.jsonl"]
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, Mapping):
        raise ValueError("validation attestation requires an object manifest")
    payload = {
        "schema_version": 1,
        "status": "passed",
        "validator": "Validate-RealDeviceObservationCorpus.py",
        "run_id": str(manifest.get("run_id") or ""),
        "provenance": EXPECTED_PROVENANCE,
        "device_serial": str(
            manifest.get("device_serial") or manifest.get("serial") or ""
        ),
        "is_emulator": False,
        "manifest_sha256": _sha256(manifest_path),
        "screens_sha256": _sha256(screens_path),
        "core_artifact_sha256": {
            name: _sha256(path) for name, path in sorted(core_paths.items())
        },
    }
    path = run_dir / VALIDATION_ATTESTATION_FILENAME
    temporary = run_dir / f".{VALIDATION_ATTESTATION_FILENAME}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _inventory_version_key(version_name: object, version_code: object) -> str:
    name = str(version_name).strip() if version_name not in {None, ""} else "unknown"
    code = str(version_code).strip() if version_code not in {None, ""} else "unknown"
    return f"code:{code}|name:{name}"


def _normalized_inventory_record(
    value: Any, *, included: bool
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    package = str(value.get("package") or "").strip()
    categories = value.get("sensitivity_categories")
    if (
        not PACKAGE_RE.fullmatch(package)
        or value.get("included") is not included
        or not isinstance(categories, list)
        or any(not isinstance(item, str) or not item.strip() for item in categories)
        or len(categories) != len(set(categories))
    ):
        return None
    version_name = str(value.get("version_name") or "").strip() or None
    version_code = str(value.get("version_code") or "").strip() or None
    version_key = _inventory_version_key(version_name, version_code)
    if str(value.get("version_key") or "").strip() != version_key:
        return None
    return {
        "package": package,
        "launchable_activity": str(value.get("launchable_activity") or "").strip() or None,
        "version_name": version_name,
        "version_code": version_code,
        "version_key": version_key,
        "included": included,
        "decision_reason_code": str(value.get("decision_reason_code") or "").strip(),
        "sensitivity_categories": sorted(categories),
        "sensitivity_handling": str(value.get("sensitivity_handling") or "").strip(),
        "change_status": str(value.get("change_status") or "").strip(),
        "observation_status": str(value.get("observation_status") or "").strip(),
    }


def _resolve_pinned_source_file(
    metadata: object,
    *,
    observation_root: Path,
    repo_root: Path,
    label: str,
) -> Path:
    """Resolve one collector-pinned source without permitting path escape/symlinks."""

    if not isinstance(metadata, Mapping):
        raise ValueError(f"{label}_metadata_invalid")
    raw_path = metadata.get("path")
    scope = str(metadata.get("path_scope") or "")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"{label}_path_invalid")
    candidate = Path(raw_path)
    if scope == "observation_root_relative":
        if candidate.is_absolute() or metadata.get("explicit_safe_file") is not False:
            raise ValueError(f"{label}_path_invalid")
        root = observation_root.expanduser().resolve()
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"{label}_path_escape")
    elif scope == "repo_relative":
        if candidate.is_absolute() or metadata.get("explicit_safe_file") is not False:
            raise ValueError(f"{label}_path_invalid")
        root = repo_root.expanduser().resolve()
        resolved = (root / candidate).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f"{label}_path_escape")
    elif scope == "explicit_safe_file":
        if not candidate.is_absolute() or metadata.get("explicit_safe_file") is not True:
            raise ValueError(f"{label}_path_invalid")
        resolved = candidate.expanduser().resolve()
    else:
        raise ValueError(f"{label}_path_scope_invalid")
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"{label}_missing_or_symlink")
    declared_sha256 = metadata.get("sha256")
    if not isinstance(declared_sha256, str) or declared_sha256 != _sha256(resolved):
        raise ValueError(f"{label}_sha256_mismatch")
    return resolved


def _task_id(task: Mapping[str, Any]) -> str:
    """Recompute the collector's stable task identity from persisted task fields."""

    identity = {
        key: task.get(key)
        for key in (
            "app_package",
            "app_name",
            "category",
            "goal_text",
            "sensitivity_categories",
            "sensitivity_handling",
            "version_name",
            "version_code",
            "version_key",
            "change_status",
            "observation_status",
            "priority_rank",
            "priority_reason",
            *GOAL_LINEAGE_FIELDS,
        )
    }
    for key in GOAL_LINEAGE_FIELDS:
        if identity.get(key) in (None, ""):
            identity.pop(key, None)
    return f"task_{_json_hash(identity)[:16]}"


def _goal_id(task: Mapping[str, Any]) -> str:
    identity: dict[str, Any] = {
        "package": task.get("app_package"),
        "goal": task.get("goal_text"),
    }
    if task.get("candidate_id"):
        identity["candidate_id"] = task.get("candidate_id")
    return f"goal_{_json_hash(identity)[:20]}"


def _validate_static_goal_tasks(
    raw_tasks: object,
    *,
    selected_packages: set[str],
    manifest_path: Path,
    errors: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Bind manifest-declared research goals to a non-dynamic capture run.

    These tasks are research hypotheses, not destination labels.  They may be
    used to prove that a real app/goal pair was observed, but they carry no
    candidate lineage and cannot promote a route.
    """

    # Older capture-only stores predate explicit task manifests.  Preserve
    # their validation behavior; new collector runs always declare tasks and
    # are bound strictly below.
    if raw_tasks is None or raw_tasks == []:
        return []
    if not isinstance(raw_tasks, list):
        errors.append(
            _finding(
                "static_selected_tasks_invalid",
                "non-dynamic research capture requires manifest tasks",
                str(manifest_path),
            )
        )
        return []
    normalized_tasks: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    for raw_task in raw_tasks:
        if not isinstance(raw_task, Mapping):
            normalized = None
        else:
            normalized = dict(raw_task)
            task_id = str(normalized.get("task_id") or "")
            package = str(normalized.get("app_package") or "")
            goal_text = str(normalized.get("goal_text") or "").strip()
            normalized = (
                normalized
                if task_id
                and task_id == _task_id(normalized)
                and task_id not in seen_task_ids
                and package in selected_packages
                and goal_text
                and all(
                    normalized.get(field) in (None, "")
                    for field in GOAL_LINEAGE_FIELDS
                )
                else None
            )
        if normalized is None:
            errors.append(
                _finding(
                    "static_selected_tasks_invalid",
                    "static task identity, package, goal, or candidate lineage is invalid",
                    str(manifest_path),
                )
            )
            continue
        seen_task_ids.add(str(normalized["task_id"]))
        normalized_tasks.append(normalized)
    covered_packages = {
        str(task.get("app_package") or "") for task in normalized_tasks
    }
    if covered_packages != selected_packages:
        errors.append(
            _finding(
                "static_selected_task_coverage",
                "static tasks must cover every selected package",
                str(manifest_path),
            )
        )
    return normalized_tasks


def _normalized_task(
    task: object,
    *,
    source: Mapping[str, Any],
    priority: Mapping[str, Any],
    directed: bool,
) -> dict[str, Any] | None:
    if not isinstance(task, Mapping):
        return None
    normalized = {
        "app_package": str(task.get("app_package") or ""),
        "app_name": str(task.get("app_name") or ""),
        "category": str(task.get("category") or ""),
        "goal_text": str(task.get("goal_text") or ""),
        "sensitivity_categories": task.get("sensitivity_categories"),
        "sensitivity_handling": str(task.get("sensitivity_handling") or ""),
        "version_name": task.get("version_name"),
        "version_code": task.get("version_code"),
        "version_key": str(task.get("version_key") or ""),
        "change_status": str(task.get("change_status") or ""),
        "observation_status": str(task.get("observation_status") or ""),
        "priority_rank": task.get("priority_rank"),
        "priority_reason": str(task.get("priority_reason") or ""),
        "candidate_id": str(task.get("candidate_id") or ""),
        "family_id": str(task.get("family_id") or ""),
        "terminal_policy": str(task.get("terminal_policy") or ""),
        "source_run_id": str(task.get("source_run_id") or ""),
        "source_inventory_snapshot_id": str(
            task.get("source_inventory_snapshot_id") or ""
        ),
        "confidence": task.get("confidence"),
        "candidate_rank": task.get("candidate_rank"),
        "source_artifact_sha256": str(task.get("source_artifact_sha256") or ""),
    }
    expected_base = {
        "app_package": source.get("package"),
        "app_name": source.get("package"),
        "category": "dynamic_inventory",
        "sensitivity_categories": source.get("sensitivity_categories"),
        "sensitivity_handling": source.get("sensitivity_handling"),
        "version_name": source.get("version_name"),
        "version_code": source.get("version_code"),
        "version_key": source.get("version_key"),
        "change_status": source.get("change_status"),
        "observation_status": source.get("observation_status"),
        "priority_rank": priority.get("priority_rank"),
        "priority_reason": priority.get("priority_reason"),
    }
    if any(normalized.get(key) != value for key, value in expected_base.items()):
        return None
    if not directed:
        if normalized["goal_text"] != NEUTRAL_INVENTORY_GOAL:
            return None
        if any(normalized.get(key) not in (None, "") for key in GOAL_LINEAGE_FIELDS):
            return None
    declared_task_id = str(task.get("task_id") or "")
    if declared_task_id != _task_id(normalized):
        return None
    normalized["task_id"] = declared_task_id
    return normalized


def _validate_runtime_attestation(
    manifest: Mapping[str, Any],
    *,
    snapshot_device: Mapping[str, Any],
    manifest_path: Path,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    runtime = manifest.get("runtime_attestation")
    valid = isinstance(runtime, Mapping) and runtime.get("schema_version") == 1
    if not valid:
        errors.append(
            _finding(
                "runtime_attestation_missing",
                "dynamic inventory requires a pre-collection runtime attestation",
                str(manifest_path),
            )
        )
        return
    checked_at = str(runtime.get("checked_at") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3,6})?Z", checked_at):
        valid = False
    expected_device = {
        "serial": str(snapshot_device.get("serial") or ""),
        "model": str(snapshot_device.get("model") or ""),
        "android_version": str(snapshot_device.get("android_version") or ""),
        "locale": str(snapshot_device.get("locale") or ""),
        "device_type": "physical_android",
        "is_emulator": False,
    }
    expected_exitguide = {
        "package": "com.exitguide.ai",
        "installed_for_user_0": True,
        "accessibility_component": (
            "com.exitguide.ai/com.exitguide.ai.overlay.ExitGuideAccessibilityService"
        ),
        "accessibility_enabled": True,
        "overlay_appop": "allow",
    }
    api = runtime.get("api")
    api_valid = (
        isinstance(api, Mapping)
        and str(api.get("health_path") or "").startswith("/")
        and str(api.get("health_path") or "").endswith("/health")
        and api.get("status") == "ok"
        and str(api.get("provider_status_path") or "").startswith("/")
        and str(api.get("provider_status_path") or "").endswith("/v1/status")
        and api.get("llm_provider") == "exaone"
        and api.get("provider_ready") is True
        and set(api) == {
            "health_path",
            "status",
            "provider_status_path",
            "llm_provider",
            "provider_ready",
        }
    )
    if (
        runtime.get("device") != expected_device
        or runtime.get("exitguide") != expected_exitguide
        or not api_valid
        or set(runtime) != {"schema_version", "checked_at", "device", "exitguide", "api"}
    ):
        valid = False
    if not valid:
        errors.append(
            _finding(
                "runtime_attestation_invalid",
                "runtime device, accessibility, overlay, API health, and EXAONE readiness must match exactly",
                str(manifest_path),
            )
        )
    checks["runtime_attestation"] = {
        "valid": valid,
        "device_serial": expected_device["serial"],
        "device_model": expected_device["model"],
        "android_version": expected_device["android_version"],
        "locale": expected_device["locale"],
        "accessibility_enabled": bool(
            isinstance(runtime.get("exitguide"), Mapping)
            and runtime["exitguide"].get("accessibility_enabled") is True
        ),
        "overlay_appop_allow": bool(
            isinstance(runtime.get("exitguide"), Mapping)
            and runtime["exitguide"].get("overlay_appop") == "allow"
        ),
        "exaone_provider_ready": bool(
            isinstance(api, Mapping)
            and api.get("llm_provider") == "exaone"
            and api.get("provider_ready") is True
        ),
    }


def _validate_directed_goal_plan(
    plan_metadata: object,
    *,
    task_rows: object,
    snapshot_path: Path,
    included_by_package: Mapping[str, Mapping[str, Any]],
    priority_by_package: Mapping[str, Mapping[str, Any]],
    selected_packages: set[str],
    observation_root: Path,
    repo_root: Path,
    manifest_path: Path,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> list[dict[str, Any]]:
    """Re-run every planner gate and bind its applicable candidates to tasks."""

    if not isinstance(plan_metadata, Mapping):
        errors.append(
            _finding(
                "goal_candidate_plan_missing",
                "goal-directed exploration requires goal_candidate_plan",
                str(manifest_path),
            )
        )
        return []
    expected_plan_keys = {
        "artifact",
        "family_manifest",
        "source_run_id",
        "source_inventory_snapshot_id",
        "state_counts",
        "selected_candidate_count",
        "selected_candidate_ids",
        "selection_sha256",
        "selection",
    }
    if set(plan_metadata) != expected_plan_keys:
        errors.append(
            _finding(
                "goal_candidate_plan_shape",
                "goal_candidate_plan fields must match the collector schema exactly",
                str(manifest_path),
            )
        )
        return []
    try:
        artifact_path = _resolve_pinned_source_file(
            plan_metadata.get("artifact"),
            observation_root=observation_root,
            repo_root=repo_root,
            label="goal_candidate_artifact",
        )
        family_path = _resolve_pinned_source_file(
            plan_metadata.get("family_manifest"),
            observation_root=observation_root,
            repo_root=repo_root,
            label="goal_family_manifest",
        )
        recomputed = plan_applicable_goals(
            artifact_path,
            snapshot_path,
            family_path,
            only_packages=sorted(selected_packages),
            max_goals_per_app=0,
        )
    except (OSError, ValueError, GoalTaskPlanningError) as error:
        errors.append(
            _finding(
                "goal_candidate_plan_source_invalid",
                f"goal planner gates rejected the pinned source: {error}",
                str(manifest_path),
            )
        )
        return []

    if (
        plan_metadata.get("source_run_id") != recomputed.source_run_id
        or plan_metadata.get("source_inventory_snapshot_id")
        != recomputed.source_inventory_snapshot_id
        or plan_metadata.get("state_counts") != dict(recomputed.state_counts)
    ):
        errors.append(
            _finding(
                "goal_candidate_plan_lineage_mismatch",
                "source run/snapshot/state counts differ from the revalidated artifact",
                str(manifest_path),
            )
        )

    if not isinstance(task_rows, list) or not task_rows:
        errors.append(
            _finding(
                "inventory_selected_tasks_invalid",
                "goal-directed exploration requires selected tasks",
                str(manifest_path),
            )
        )
        return []
    planned_by_id = {item.candidate_id: item for item in recomputed.applicable}
    normalized_tasks: list[dict[str, Any]] = []
    seen_task_ids: set[str] = set()
    seen_candidate_ids: set[str] = set()
    for raw_task in task_rows:
        package = str(raw_task.get("app_package") or "") if isinstance(raw_task, Mapping) else ""
        source = included_by_package.get(package)
        priority = priority_by_package.get(package)
        normalized = (
            _normalized_task(
                raw_task,
                source=source,
                priority=priority,
                directed=True,
            )
            if source is not None and priority is not None
            else None
        )
        if normalized is None:
            errors.append(
                _finding(
                    "inventory_selected_tasks_invalid",
                    "goal-directed task base/version/priority identity is invalid",
                    str(manifest_path),
                )
            )
            continue
        candidate_id = normalized["candidate_id"]
        planned = planned_by_id.get(candidate_id)
        expected_lineage = {
            "app_package": planned.app_package if planned else None,
            "goal_text": planned.goal_text if planned else None,
            "candidate_id": planned.candidate_id if planned else None,
            "family_id": planned.family_id if planned else None,
            "terminal_policy": planned.terminal_policy if planned else None,
            "source_run_id": planned.source_run_id if planned else None,
            "source_inventory_snapshot_id": (
                planned.source_inventory_snapshot_id if planned else None
            ),
            "confidence": planned.confidence if planned else None,
            "candidate_rank": planned.rank if planned else None,
            "source_artifact_sha256": recomputed.source_artifact_sha256,
        }
        if (
            planned is None
            or any(normalized.get(key) != value for key, value in expected_lineage.items())
            or normalized["task_id"] in seen_task_ids
            or candidate_id in seen_candidate_ids
        ):
            errors.append(
                _finding(
                    "goal_candidate_task_lineage_mismatch",
                    "task does not identify one unique revalidated applicable candidate",
                    str(manifest_path),
                )
            )
            continue
        seen_task_ids.add(normalized["task_id"])
        seen_candidate_ids.add(candidate_id)
        normalized_tasks.append(normalized)

    selection = plan_metadata.get("selection")
    expected_selection = [
        {
            "task_id": task["task_id"],
            "app_package": task["app_package"],
            "version_key": task["version_key"],
            "candidate_id": task["candidate_id"],
            "family_id": task["family_id"],
            "terminal_policy": task["terminal_policy"],
            "source_run_id": task["source_run_id"],
            "source_inventory_snapshot_id": task["source_inventory_snapshot_id"],
            "confidence": task["confidence"],
            "candidate_rank": task["candidate_rank"],
            "source_artifact_sha256": task["source_artifact_sha256"],
        }
        for task in normalized_tasks
    ]
    if (
        selection != expected_selection
        or plan_metadata.get("selected_candidate_count") != len(expected_selection)
        or plan_metadata.get("selected_candidate_ids")
        != [item["candidate_id"] for item in expected_selection]
        or plan_metadata.get("selection_sha256") != _json_hash(expected_selection)
        or {task["app_package"] for task in normalized_tasks} != selected_packages
    ):
        errors.append(
            _finding(
                "goal_candidate_selection_mismatch",
                "goal plan selection, task order, hash, and selected packages must match exactly",
                str(manifest_path),
            )
        )
    checks["goal_candidate_plan"] = {
        "source_run_id": recomputed.source_run_id,
        "source_inventory_snapshot_id": recomputed.source_inventory_snapshot_id,
        "source_artifact_sha256": recomputed.source_artifact_sha256,
        "revalidated_applicable_count": len(recomputed.applicable),
        "selected_candidate_count": len(normalized_tasks),
        "selection_sha256": _json_hash(expected_selection),
    }
    return normalized_tasks


def _validate_dynamic_inventory_metadata(
    manifest: Mapping[str, Any],
    *,
    manifest_path: Path,
    observation_root: Path,
    repo_root: Path,
    selected_packages: set[str],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "included_packages": set(),
        "excluded_packages": set(),
        "versions": {},
        "sensitivity_categories": {},
        "selected_tasks": [],
        "exploration_stage": manifest.get("exploration_stage"),
        "goal_candidate_plan": None,
    }
    metadata = manifest.get("inventory_snapshot")
    if not isinstance(metadata, Mapping):
        errors.append(
            _finding(
                "dynamic_inventory_metadata_missing",
                "dynamic_inventory requires inventory_snapshot metadata",
                str(manifest_path),
            )
        )
        return result
    stage = manifest.get("exploration_stage")
    if metadata.get("exploration_stage") != stage:
        errors.append(
            _finding(
                "inventory_exploration_stage_mismatch",
                "inventory snapshot metadata stage differs from the run manifest",
                str(manifest_path),
            )
        )
    embedded_plan = metadata.get("goal_candidate_plan")
    manifest_plan = manifest.get("goal_candidate_plan")
    if embedded_plan != manifest_plan:
        errors.append(
            _finding(
                "goal_candidate_plan_control_mismatch",
                "manifest and inventory goal_candidate_plan must be identical",
                str(manifest_path),
            )
        )
    collection_mode = str(manifest.get("collection_mode") or "")
    if stage == EXPLORATION_STAGE_INITIAL_CAPTURE:
        if collection_mode not in COLLECTOR_CAPTURE_MODES or manifest_plan is not None:
            errors.append(
                _finding(
                    "exploration_stage_mode_mismatch",
                    "initial_capture requires capture-only mode and no goal plan",
                    str(manifest_path),
                )
            )
    elif stage == EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
        if collection_mode != "safe_explore" or manifest_plan is not None:
            errors.append(
                _finding(
                    "exploration_stage_mode_mismatch",
                    "neutral discovery requires safe_explore and no goal plan",
                    str(manifest_path),
                )
            )
    elif stage == EXPLORATION_STAGE_GOAL_DIRECTED:
        if collection_mode != "safe_explore" or not isinstance(manifest_plan, Mapping):
            errors.append(
                _finding(
                    "exploration_stage_mode_mismatch",
                    "goal-directed exploration requires safe_explore and a goal plan",
                    str(manifest_path),
                )
            )
    raw_path = metadata.get("path")
    path_scope = str(metadata.get("path_scope") or "")
    if not isinstance(raw_path, str) or not raw_path.strip():
        errors.append(
            _finding("inventory_snapshot_path_invalid", "snapshot path is missing", str(manifest_path))
        )
        return result
    candidate = Path(raw_path)
    root = observation_root.expanduser().resolve()
    if path_scope == "observation_root_relative":
        if candidate.is_absolute():
            errors.append(
                _finding(
                    "inventory_snapshot_path_invalid",
                    "relative snapshot scope cannot use an absolute path",
                    str(manifest_path),
                )
            )
            return result
        snapshot_path = (root / candidate).resolve()
        if not snapshot_path.is_relative_to(root):
            errors.append(
                _finding(
                    "inventory_snapshot_path_escape",
                    "snapshot path escapes the observation root",
                    str(manifest_path),
                )
            )
            return result
    elif path_scope == "explicit_safe_file":
        snapshot_path = candidate.expanduser().resolve()
        if (
            not candidate.is_absolute()
            or metadata.get("explicit_safe_file") is not True
            or candidate.is_symlink()
        ):
            errors.append(
                _finding(
                    "inventory_snapshot_path_invalid",
                    "external snapshot must be an explicitly attested regular file",
                    str(manifest_path),
                )
            )
            return result
    else:
        errors.append(
            _finding(
                "inventory_snapshot_path_scope_invalid",
                "snapshot path scope is unsupported",
                str(manifest_path),
            )
        )
        return result
    if not snapshot_path.is_file():
        errors.append(
            _finding("inventory_snapshot_missing", "inventory snapshot file is missing", str(manifest_path))
        )
        return result
    actual_sha256 = _sha256(snapshot_path)
    checks["inventory_snapshot_sha256"] = actual_sha256
    if metadata.get("sha256") != actual_sha256:
        errors.append(
            _finding(
                "inventory_snapshot_sha256_mismatch",
                "inventory snapshot hash differs from the manifest pin",
                str(manifest_path),
            )
        )
        return result
    try:
        snapshot = _load_json(snapshot_path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(
            _finding(
                "inventory_snapshot_parse_error",
                "inventory snapshot is not valid JSON",
                str(manifest_path),
            )
        )
        return result
    if not isinstance(snapshot, Mapping) or snapshot.get("schema_version") != 1:
        errors.append(
            _finding(
                "inventory_snapshot_shape",
                "inventory snapshot must be a schema_version=1 object",
                str(manifest_path),
            )
        )
        return result
    governance_valid = all(
        snapshot.get(field) == expected
        for field, expected in (
            ("provenance", EXPECTED_PROVENANCE),
            ("dataset_role", EXPECTED_PROVENANCE),
            ("review_status", EXPECTED_REVIEW_STATUS),
            ("route_lifecycle", "shadow"),
        )
    )
    if (
        not governance_valid
        or snapshot.get("canonical_catalog_mutation") is not False
        or snapshot.get("canonical_catalog") != EXPECTED_INVENTORY_CANONICAL
    ):
        errors.append(
            _finding(
                "inventory_snapshot_governance_mismatch",
                "inventory snapshot governance/V15 pins are invalid",
                str(manifest_path),
            )
        )
    device = snapshot.get("device")
    manifest_serial = str(_first(manifest, "device_serial", "device.serial") or "")
    if (
        not isinstance(device, Mapping)
        or str(device.get("serial") or "") != manifest_serial
        or device.get("is_emulator") is not False
        or str(device.get("device_type") or "")
        not in {"physical", "physical_android", "physical_device", "android_physical"}
        or metadata.get("device") != device
    ):
        errors.append(
            _finding(
                "inventory_snapshot_device_mismatch",
                "snapshot and run physical-device attestations differ",
                str(manifest_path),
            )
        )
    if isinstance(device, Mapping):
        _validate_runtime_attestation(
            manifest,
            snapshot_device=device,
            manifest_path=manifest_path,
            errors=errors,
            checks=checks,
        )
    if metadata.get("snapshot_id") != snapshot.get("snapshot_id"):
        errors.append(
            _finding(
                "inventory_snapshot_id_mismatch",
                "snapshot_id differs from manifest metadata",
                str(manifest_path),
            )
        )

    included_raw = snapshot.get("included_apps")
    excluded_raw = snapshot.get("excluded_apps")
    prioritized_raw = snapshot.get("prioritized_apps")
    if not isinstance(included_raw, list) or not isinstance(excluded_raw, list):
        errors.append(
            _finding(
                "inventory_snapshot_apps_invalid",
                "snapshot included/excluded app lists are invalid",
                str(manifest_path),
            )
        )
        return result
    included = [_normalized_inventory_record(item, included=True) for item in included_raw]
    excluded = [_normalized_inventory_record(item, included=False) for item in excluded_raw]
    if any(item is None for item in included + excluded) or not included:
        errors.append(
            _finding(
                "inventory_snapshot_apps_invalid",
                "snapshot contains malformed app records",
                str(manifest_path),
            )
        )
        return result
    included_rows = [dict(item) for item in included if item is not None]
    excluded_rows = [dict(item) for item in excluded if item is not None]
    included_packages = {str(item["package"]) for item in included_rows}
    excluded_packages = {str(item["package"]) for item in excluded_rows}
    if (
        len(included_packages) != len(included_rows)
        or len(excluded_packages) != len(excluded_rows)
        or included_packages & excluded_packages
    ):
        errors.append(
            _finding(
                "inventory_snapshot_package_set_invalid",
                "snapshot package sets are duplicate or overlapping",
                str(manifest_path),
            )
        )
        return result
    normalized_included = sorted(included_rows, key=lambda item: str(item["package"]))
    if metadata.get("included_inventory") != normalized_included:
        errors.append(
            _finding(
                "inventory_manifest_exact_inventory_mismatch",
                "manifest included inventory differs from the pinned snapshot",
                str(manifest_path),
            )
        )
    if not isinstance(prioritized_raw, list):
        errors.append(
            _finding(
                "inventory_snapshot_priority_invalid",
                "snapshot prioritized_apps is invalid",
                str(manifest_path),
            )
        )
        prioritized_raw = []
    normalized_priority: list[dict[str, Any]] = []
    included_by_package = {str(item["package"]): item for item in normalized_included}
    for item in prioritized_raw:
        if not isinstance(item, Mapping):
            continue
        package = str(item.get("package") or "")
        source = included_by_package.get(package)
        rank = item.get("priority_rank")
        if source is None or not isinstance(rank, int):
            continue
        normalized_priority.append(
            {
                "priority_rank": rank,
                "package": package,
                "version_key": source["version_key"],
                "change_status": str(item.get("change_status") or ""),
                "observation_status": str(item.get("observation_status") or ""),
                "priority_reason": str(item.get("priority_reason") or ""),
                "sensitivity_categories": list(source["sensitivity_categories"]),
                "sensitivity_handling": source["sensitivity_handling"],
            }
        )
    normalized_priority.sort(key=lambda item: (item["priority_rank"], item["package"]))
    if (
        {item["package"] for item in normalized_priority} != included_packages
        or [item["priority_rank"] for item in normalized_priority]
        != list(range(1, len(normalized_priority) + 1))
        or metadata.get("prioritized_apps") != normalized_priority
    ):
        errors.append(
            _finding(
                "inventory_snapshot_priority_invalid",
                "priority list must exactly rank the included inventory",
                str(manifest_path),
            )
        )
    exclusion_counts = Counter(str(item["decision_reason_code"]) for item in excluded_rows)
    expected_exclusions = {
        "excluded_app_count": len(excluded_rows),
        "reason_counts": dict(sorted(exclusion_counts.items())),
        "package_set_sha256": _json_hash(sorted(excluded_packages)),
    }
    if metadata.get("exclusions_summary") != expected_exclusions:
        errors.append(
            _finding(
                "inventory_exclusion_summary_mismatch",
                "manifest exclusion summary differs from snapshot",
                str(manifest_path),
            )
        )
    if metadata.get("selected_packages") != sorted(selected_packages):
        errors.append(
            _finding(
                "inventory_selected_packages_mismatch",
                "snapshot metadata selection differs from run selection",
                str(manifest_path),
            )
        )
    run_id = str(manifest.get("run_id") or "")
    expected_candidates = [
        {
            "app_package": item["package"],
            "version_name": item["version_name"],
            "version_code": item["version_code"],
            "version_key": item["version_key"],
            "candidate_id": "version_"
            + _json_hash(
                {
                    "run_id": run_id,
                    "app_package": item["package"],
                    "version_name": item["version_name"],
                    "version_code": item["version_code"],
                }
            )[:24],
        }
        for item in normalized_included
    ]
    if metadata.get("version_candidates") != expected_candidates:
        errors.append(
            _finding(
                "inventory_version_candidates_mismatch",
                "run/version candidate lineage is inconsistent",
                str(manifest_path),
            )
        )
    task_rows = metadata.get("selected_tasks")
    priority_by_package = {
        str(item["package"]): item for item in normalized_priority
    }
    normalized_tasks: list[dict[str, Any]] = []
    if stage == EXPLORATION_STAGE_GOAL_DIRECTED:
        normalized_tasks = _validate_directed_goal_plan(
            manifest_plan,
            task_rows=task_rows,
            snapshot_path=snapshot_path,
            included_by_package=included_by_package,
            priority_by_package=priority_by_package,
            selected_packages=selected_packages,
            observation_root=observation_root,
            repo_root=repo_root,
            manifest_path=manifest_path,
            errors=errors,
            checks=checks,
        )
    elif isinstance(task_rows, list):
        for task in task_rows:
            package = str(task.get("app_package") or "") if isinstance(task, Mapping) else ""
            source = included_by_package.get(package)
            priority = priority_by_package.get(package)
            normalized = (
                _normalized_task(
                    task,
                    source=source,
                    priority=priority,
                    directed=False,
                )
                if source is not None and priority is not None
                else None
            )
            if normalized is None:
                errors.append(
                    _finding(
                        "inventory_selected_tasks_invalid",
                        "neutral task metadata is not exactly snapshot-derived",
                        str(manifest_path),
                    )
                )
                continue
            normalized_tasks.append(normalized)
        task_packages = {task["app_package"] for task in normalized_tasks}
        if (
            task_packages != selected_packages
            or len(normalized_tasks) != len(selected_packages)
            or len({task["task_id"] for task in normalized_tasks}) != len(normalized_tasks)
        ):
            errors.append(
                _finding(
                    "inventory_selected_tasks_invalid",
                    "neutral dynamic tasks must exactly cover selected packages once",
                    str(manifest_path),
                )
            )
    else:
        errors.append(
            _finding(
                "inventory_selected_tasks_invalid",
                "dynamic inventory selected_tasks is required",
                str(manifest_path),
            )
        )
    summary = snapshot.get("summary")
    if not isinstance(summary, Mapping) or (
        summary.get("included_apps") != len(included_packages)
        or summary.get("excluded_apps") != len(excluded_packages)
    ):
        errors.append(
            _finding(
                "inventory_snapshot_summary_mismatch",
                "snapshot summary disagrees with exact inventory",
                str(manifest_path),
            )
        )
    result.update(
        {
            "included_packages": included_packages,
            "excluded_packages": excluded_packages,
            "versions": {
                str(item["package"]): {
                    "version_name": item["version_name"],
                    "version_code": item["version_code"],
                    "version_key": item["version_key"],
                    "candidate_id": expected_candidates[index]["candidate_id"],
                }
                for index, item in enumerate(normalized_included)
            },
            "sensitivity_categories": {
                str(item["package"]): list(item["sensitivity_categories"])
                for item in normalized_included
            },
            "selected_tasks": normalized_tasks,
            "exploration_stage": stage,
            "goal_candidate_plan": manifest_plan,
            "snapshot_path": snapshot_path,
        }
    )
    checks["dynamic_inventory"] = {
        "snapshot_id": metadata.get("snapshot_id"),
        "included_count": len(included_packages),
        "excluded_count": len(excluded_packages),
        "selected_count": len(selected_packages),
    }
    return result


def _as_bool(value: Any) -> bool:
    return BASE._is_truthy(value)


def _first(mapping: Mapping[str, Any], *paths: str) -> Any:
    return BASE._nested(mapping, *paths)


def _parse_jsonl(path: Path, errors: list[dict[str, str]]) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    if not path.is_file():
        return records
    try:
        with path.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    errors.append(
                        _finding("jsonl_parse_error", f"line {line_number}: {error}", str(path))
                    )
                    continue
                if not isinstance(value, Mapping):
                    errors.append(
                        _finding("jsonl_shape", f"line {line_number} must be an object", str(path))
                    )
                    continue
                records.append(value)
    except (OSError, UnicodeError) as error:
        errors.append(_finding("jsonl_read_error", str(error), str(path)))
    return records


def _validate_app_manifest(
    path: Path, errors: list[dict[str, str]], checks: dict[str, Any]
) -> Mapping[str, Any]:
    if not path.is_file():
        errors.append(_finding("app_manifest_missing", "physical-device app manifest is required", str(path)))
        return {}
    try:
        payload = _load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(_finding("app_manifest_parse_error", str(error), str(path)))
        return {}
    if not isinstance(payload, Mapping):
        errors.append(_finding("app_manifest_shape", "app manifest must be an object", str(path)))
        return {}

    for field, expected in (
        ("dataset_role", EXPECTED_PROVENANCE),
        ("provenance", EXPECTED_PROVENANCE),
        ("review_status", EXPECTED_REVIEW_STATUS),
        ("route_lifecycle", "shadow"),
    ):
        if payload.get(field) != expected:
            errors.append(
                _finding("app_manifest_governance", f"{field} must be {expected!r}", str(path))
            )
    if payload.get("canonical_catalog_mutation") is not False:
        errors.append(_finding("canonical_mutation_enabled", "app manifest cannot mutate V15", str(path)))
    canonical = payload.get("canonical_catalog")
    if not isinstance(canonical, Mapping) or dict(canonical) != EXPECTED_CANONICAL:
        errors.append(
            _finding("app_manifest_canonical_mismatch", "app manifest must pin the exact frozen V15 catalog", str(path))
        )

    policy = payload.get("collection_policy")
    if not isinstance(policy, Mapping):
        errors.append(_finding("app_manifest_policy_missing", "collection_policy is required", str(path)))
    else:
        required_policy = {
            "device_type": "physical_android",
            "installed_apps_only": True,
            "missing_app_status": "skipped_missing",
            "raw_xml_persisted": False,
            "raw_screenshot_persisted": False,
            "never_execute_unsafe_action": True,
            "never_execute_final_action": True,
            "gold_promotion_allowed": False,
        }
        for field, expected in required_policy.items():
            if policy.get(field) != expected:
                errors.append(
                    _finding("app_manifest_policy", f"collection_policy.{field} must be {expected!r}", str(path))
                )
        statuses = set(str(item) for item in policy.get("allowed_observation_statuses", []))
        if statuses != ALLOWED_APP_STATUSES:
            errors.append(
                _finding("app_manifest_status_policy", f"allowed statuses must be {sorted(ALLOWED_APP_STATUSES)}", str(path))
            )

    apps = payload.get("apps")
    observed: list[tuple[str, str]] = []
    if isinstance(apps, list):
        for item in apps:
            if isinstance(item, Mapping):
                observed.append((str(item.get("app_name", "")), str(item.get("app_package", ""))))
    checks["app_manifest_app_count"] = len(observed)
    if len(observed) != len(EXPECTED_APPS) or len({package for _, package in observed}) != len(EXPECTED_APPS):
        errors.append(_finding("app_manifest_cardinality", "app manifest must contain exactly 14 unique packages", str(path)))
    if set(observed) != set(EXPECTED_APPS):
        errors.append(
            _finding("app_manifest_apps_mismatch", "app manifest names/packages do not match the physical-device cohort", str(path))
        )
    return payload


def _validate_run_manifest(
    path: Path,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    observation_root: Path = DEFAULT_OBSERVATION_ROOT,
    repo_root: Path = ROOT,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    if not path.is_file():
        errors.append(_finding("manifest_missing", "manifest.json is required", str(path)))
        return {}, {}
    try:
        manifest = _load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(_finding("manifest_parse_error", str(error), str(path)))
        return {}, {}
    if not isinstance(manifest, Mapping):
        errors.append(_finding("manifest_shape", "manifest must be a JSON object", str(path)))
        return {}, {}

    if manifest.get("provenance") != EXPECTED_PROVENANCE:
        errors.append(_finding("invalid_provenance", f"provenance must be exactly {EXPECTED_PROVENANCE!r}", str(path)))
    if manifest.get("dataset_role", EXPECTED_PROVENANCE) != EXPECTED_PROVENANCE:
        errors.append(_finding("invalid_dataset_role", f"dataset_role must be {EXPECTED_PROVENANCE!r}", str(path)))
    if manifest.get("review_status") != EXPECTED_REVIEW_STATUS:
        errors.append(_finding("unreviewed_gold_forbidden", f"review_status must be {EXPECTED_REVIEW_STATUS!r}", str(path)))
    lifecycle = str(manifest.get("route_lifecycle", ""))
    if lifecycle not in ALLOWED_LIFECYCLES:
        errors.append(_finding("route_not_candidate", f"lifecycle must be shadow/candidate, got {lifecycle!r}", str(path)))
    mutation_value = _first(manifest, "canonical_catalog_mutation", "canonical_mutation_allowed")
    if mutation_value is not False:
        errors.append(_finding("canonical_mutation_enabled", "physical observations cannot mutate V15", str(path)))
    canonical = manifest.get("canonical_catalog")
    if not isinstance(canonical, Mapping) or dict(canonical) != EXPECTED_CANONICAL:
        errors.append(_finding("manifest_canonical_mismatch", "manifest must pin the exact frozen V15 catalog", str(path)))

    collection_mode = str(manifest.get("collection_mode", "")).strip().casefold()
    exploration_stage = manifest.get("exploration_stage")
    if exploration_stage not in ALLOWED_EXPLORATION_STAGES:
        errors.append(
            _finding(
                "exploration_stage_invalid",
                f"exploration_stage must be exactly one of {sorted(ALLOWED_EXPLORATION_STAGES)}",
                str(path),
            )
        )
        exploration_stage = ""
    raw_validation_profile = str(manifest.get("validation_profile", "")).strip().casefold()
    legacy_behavior_profiles = CAPTURE_PROFILES | COMPLETED_PROFILES | COLLECTOR_CAPTURE_MODES | COLLECTOR_EXPLORE_MODES
    if not raw_validation_profile:
        cohort_profile = "full_cohort"
    elif raw_validation_profile in ALLOWED_VALIDATION_PROFILES:
        cohort_profile = raw_validation_profile
    elif raw_validation_profile in legacy_behavior_profiles:
        # Older research runs used validation_profile for the run state.  They
        # remain strict full-cohort validations; this is not a partial bypass.
        cohort_profile = "full_cohort"
    else:
        cohort_profile = ""
        errors.append(
            _finding(
                "validation_profile_invalid",
                f"validation_profile must be one of {sorted(ALLOWED_VALIDATION_PROFILES)}",
                str(path),
            )
        )
    mode = str(_first(manifest, "run_mode", "mode") or "").strip().casefold()
    if raw_validation_profile in legacy_behavior_profiles:
        mode = raw_validation_profile
    status = str(manifest.get("status", mode)).strip().casefold()
    if collection_mode in COLLECTOR_CAPTURE_MODES:
        profile_name = "capture_only"
    elif (
        mode in COMPLETED_PROFILES
        or status in COMPLETED_PROFILES
        or status in COMPLETED_STATUSES
    ):
        profile_name = "completed_exploration"
    elif mode in COLLECTOR_CAPTURE_MODES:
        profile_name = "capture_only"
    elif (
        mode in CAPTURE_PROFILES
        or mode in COLLECTOR_EXPLORE_MODES
        or status in CAPTURE_PROFILES
        or status in COLLECTING_STATUSES
    ):
        profile_name = "capture_only" if mode == "capture_only" or status == "capture_only" else "in_progress"
    else:
        profile_name = ""
        errors.append(
            _finding(
                "validation_profile_missing",
                "validation_profile/run_mode/status must identify capture_only, in_progress, or completed_exploration",
                str(path),
            )
        )

    device_type = str(_first(manifest, "device_type", "device.type", "device.device_type") or "")
    is_emulator = _first(manifest, "is_emulator", "device.is_emulator")
    serial = str(_first(manifest, "device_serial", "device.serial") or "")
    if device_type and device_type not in {"physical", "physical_android", "physical_device", "android_physical"}:
        errors.append(_finding("physical_device_attestation_invalid", f"invalid physical device type: {device_type!r}", str(path)))
    if is_emulator is not None and _as_bool(is_emulator):
        errors.append(_finding("emulator_run_forbidden", "physical corpus cannot be captured on an emulator", str(path)))
    if serial.casefold().startswith("emulator-"):
        errors.append(_finding("emulator_serial_forbidden", f"emulator serial is not physical: {serial}", str(path)))

    evidence = manifest.get("evidence_policy", {})
    if not isinstance(evidence, Mapping):
        evidence = {}
    raw_aggregate = manifest.get("raw_artifacts_persisted")
    raw_xml = _first(manifest, "raw_xml_persisted", "evidence_policy.raw_xml_persisted")
    raw_screenshot = _first(manifest, "raw_screenshot_persisted", "evidence_policy.raw_screenshot_persisted")
    raw_policy_valid = raw_aggregate is False or (raw_xml is False and raw_screenshot is False)
    if not raw_policy_valid:
        errors.append(
            _finding("raw_artifact_policy", "raw_xml_persisted and raw_screenshot_persisted must both be false", str(path))
        )
    evidence_mode = str(_first(manifest, "evidence_policy.mode", "evidence_mode") or "").casefold()
    if evidence_mode and evidence_mode not in {"redacted_or_metadata_only", "redacted", "metadata_only", "verified_redacted"}:
        errors.append(_finding("evidence_policy_invalid", "evidence must be redacted or metadata-only", str(path)))

    for metric_name in ("unsafe_auto_click_count", "final_action_auto_click_count"):
        value = _first(manifest, f"safety.{metric_name}", f"metrics.{metric_name}", metric_name)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = -1.0
        if numeric != 0:
            errors.append(_finding("manifest_safety_metric_nonzero", f"{metric_name} must be 0", str(path)))

    manifest_text = _canonical_json(manifest).casefold()
    if re.search(r'"(?:promotion|promote|gold_promotion|canonical_write)[^"\\]*"\s*:\s*(?:true|1|"(?:gold|approved|active|canonical)")', manifest_text):
        errors.append(_finding("promotion_forbidden", "unreviewed physical observations cannot request promotion", str(path)))
    proposed = str(_first(manifest, "proposed_catalog_version", "target_catalog_version", "promotion.catalog_version") or "")
    match = re.search(r"(?:^|\D)(1[6-9]|20)(?:\D|$)", proposed)
    if match:
        errors.append(_finding("v16_v20_promotion_forbidden", f"catalog promotion to V{match.group(1)} is forbidden", str(path)))
    if re.search(r"(?:^|\D)(?:2[2-9]|[3-9]\d)(?:\D|$)", proposed):
        errors.append(_finding("v22_promotion_forbidden", "V22+ promotion is forbidden", str(path)))

    selected_packages = _normalize_package_list(manifest.get("selected_packages"))
    inventory_packages = _normalize_package_list(manifest.get("inventory_packages"))
    raw_selected = manifest.get("selected_packages")
    raw_inventory = manifest.get("inventory_packages")
    for label, raw, normalized_packages in (
        ("selected_packages", raw_selected, selected_packages),
        ("inventory_packages", raw_inventory, inventory_packages),
    ):
        if raw is not None and (
            not isinstance(raw, list)
            or len(raw) != len(normalized_packages)
            or any(not str(value).strip() for value in raw)
        ):
            errors.append(
                _finding(
                    "package_selection_shape",
                    f"{label} must be a unique non-empty-string list",
                    str(path),
                )
            )
    dynamic_inventory: dict[str, Any] = {}
    if cohort_profile == "dynamic_inventory":
        dynamic_inventory = _validate_dynamic_inventory_metadata(
            manifest,
            manifest_path=path,
            observation_root=observation_root,
            repo_root=repo_root,
            selected_packages=selected_packages,
            errors=errors,
            checks=checks,
        )
        dynamic_packages = set(dynamic_inventory.get("included_packages", set()))
        if inventory_packages != dynamic_packages:
            errors.append(
                _finding(
                    "dynamic_inventory_coverage",
                    "inventory_packages must exactly match snapshot included apps",
                    str(path),
                )
            )
        if not selected_packages or not selected_packages.issubset(dynamic_packages):
            errors.append(
                _finding(
                    "dynamic_selection_invalid",
                    "selected_packages must be a non-empty subset of included apps",
                    str(path),
                )
            )
    elif cohort_profile == "partial_research":
        if inventory_packages != EXPECTED_PACKAGES:
            errors.append(
                _finding(
                    "partial_inventory_coverage",
                    "partial_research must attest the exact 14-package manifest cohort",
                    str(path),
                )
            )
        if not selected_packages or not selected_packages < EXPECTED_PACKAGES:
            errors.append(
                _finding(
                    "partial_selection_invalid",
                    "partial_research selected_packages must be a non-empty proper subset of the 14-package cohort",
                    str(path),
                )
            )
    elif cohort_profile == "full_cohort":
        if inventory_packages and inventory_packages != EXPECTED_PACKAGES:
            errors.append(
                _finding(
                    "full_inventory_coverage",
                    "full_cohort inventory_packages must contain the exact 14-package cohort",
                    str(path),
                )
            )

    if cohort_profile != "dynamic_inventory" and (
        exploration_stage != EXPLORATION_STAGE_INITIAL_CAPTURE
        or manifest.get("goal_candidate_plan") is not None
    ):
        errors.append(
            _finding(
                "exploration_stage_profile_mismatch",
                "non-dynamic legacy cohorts may only use initial_capture without a goal plan",
                str(path),
            )
        )
        if selected_packages and selected_packages != EXPECTED_PACKAGES:
            errors.append(
                _finding(
                    "full_selection_coverage",
                    "full_cohort selected_packages must contain the exact 14-package cohort",
                    str(path),
                )
            )

    statuses = _normalize_app_statuses(manifest.get("app_statuses"))
    checks["app_status_count"] = len(statuses)
    raw_statuses = manifest.get("app_statuses")
    expected_status_packages = (
        set(dynamic_inventory.get("included_packages", set()))
        if cohort_profile == "dynamic_inventory"
        else set(EXPECTED_PACKAGES)
    )
    if isinstance(raw_statuses, list):
        raw_packages = [
            str(item.get("app_package", item.get("package", "")))
            for item in raw_statuses
            if isinstance(item, Mapping)
        ]
        if len(raw_statuses) != len(expected_status_packages) or len(raw_packages) != len(set(raw_packages)):
            errors.append(
                _finding(
                    "app_status_cardinality",
                    "app_statuses must contain exactly one entry for each profile inventory app",
                    str(path),
                )
            )
    if set(statuses) != expected_status_packages:
        errors.append(
            _finding(
                "app_status_coverage",
                "app_statuses do not exactly cover the validation profile inventory",
                str(path),
            )
        )
    for package, item in statuses.items():
        state = str(item.get("status", ""))
        if state not in ALLOWED_APP_STATUSES:
            errors.append(_finding("invalid_app_status", f"{package} has invalid status {state!r}", str(path)))
        if cohort_profile == "full_cohort" and state not in FULL_COHORT_APP_STATUSES:
            errors.append(
                _finding(
                    "full_cohort_partial_status_forbidden",
                    f"full_cohort cannot use {state!r} for {package}",
                    str(path),
                )
            )
    if cohort_profile == "dynamic_inventory":
        for package in sorted(selected_packages):
            if str(statuses.get(package, {}).get("status", "")) != "installed_observed":
                errors.append(
                    _finding(
                        "selected_package_missing_evidence",
                        "selected dynamic package must be installed_observed",
                        str(path),
                    )
                )
        for package in sorted(expected_status_packages - selected_packages):
            if str(statuses.get(package, {}).get("status", "")) != "installed_not_selected":
                errors.append(
                    _finding(
                        "unselected_package_status_invalid",
                        "unselected included package must be installed_not_selected",
                        str(path),
                    )
                )
    elif cohort_profile == "partial_research":
        for package in sorted(selected_packages):
            state = str(statuses.get(package, {}).get("status", ""))
            if state != "installed_observed":
                errors.append(
                    _finding(
                        "selected_package_missing_evidence",
                        f"selected package {package} must be installed and observed, got {state!r}",
                        str(path),
                    )
                )
        for package in sorted(EXPECTED_PACKAGES - selected_packages):
            state = str(statuses.get(package, {}).get("status", ""))
            if state not in {"installed_not_selected", "skipped_missing"}:
                errors.append(
                    _finding(
                        "unselected_package_status_invalid",
                        f"unselected package {package} must be installed_not_selected or skipped_missing, got {state!r}",
                        str(path),
                    )
                )
    installed = {package for package, item in statuses.items() if item.get("status") == "installed_observed"}
    not_selected = {package for package, item in statuses.items() if item.get("status") == "installed_not_selected"}
    skipped = {package for package, item in statuses.items() if item.get("status") == "skipped_missing"}
    selected_tasks = (
        list(dynamic_inventory.get("selected_tasks", []))
        if cohort_profile == "dynamic_inventory"
        else _validate_static_goal_tasks(
            manifest.get("tasks"),
            selected_packages=selected_packages,
            manifest_path=path,
            errors=errors,
        )
    )
    profile = {
        "name": profile_name,
        "cohort_profile": cohort_profile,
        "partial_research": cohort_profile == "partial_research",
        "dynamic_inventory": cohort_profile == "dynamic_inventory",
        "capture_only": profile_name in {"capture_only", "in_progress"},
        "in_progress": profile_name == "in_progress",
        "completed": profile_name == "completed_exploration",
        "installed_packages": installed,
        "selected_packages": selected_packages,
        "inventory_packages": inventory_packages,
        "required_evidence_packages": (
            selected_packages
            if cohort_profile in {"partial_research", "dynamic_inventory"}
            else installed
        ),
        "not_selected_packages": not_selected,
        "skipped_packages": skipped,
        "run_id": str(manifest.get("run_id", "")),
        "route_lifecycle": lifecycle,
        "excluded_packages": set(dynamic_inventory.get("excluded_packages", set())),
        "inventory_versions": dict(dynamic_inventory.get("versions", {})),
        "inventory_sensitivity_categories": dict(
            dynamic_inventory.get("sensitivity_categories", {})
        ),
        "exploration_stage": exploration_stage,
        "selected_tasks": selected_tasks,
        "goal_candidate_plan": dynamic_inventory.get("goal_candidate_plan"),
        "run_status": status,
        "collection_mode": collection_mode,
    }
    checks["run_profile"] = {
        **profile,
        "installed_packages": sorted(installed),
        "selected_packages": sorted(selected_packages),
        "inventory_packages": sorted(inventory_packages),
        "required_evidence_packages": sorted(
            selected_packages
            if cohort_profile in {"partial_research", "dynamic_inventory"}
            else installed
        ),
        "not_selected_packages": sorted(not_selected),
        "skipped_packages": sorted(skipped),
    }
    return manifest, profile


def _normalize_app_statuses(value: Any) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if isinstance(value, Mapping):
        iterable: Iterable[tuple[Any, Any]] = value.items()
        for package_value, raw in iterable:
            package = str(package_value)
            if isinstance(raw, Mapping):
                result[package] = {
                    "status": str(raw.get("status", "")),
                    "reason": str(raw.get("reason", raw.get("skip_reason", ""))),
                }
            else:
                result[package] = {"status": str(raw), "reason": "not installed" if str(raw) == "skipped_missing" else ""}
    elif isinstance(value, list):
        for raw in value:
            if not isinstance(raw, Mapping):
                continue
            package = str(raw.get("app_package", raw.get("package", "")))
            if not package or package in result:
                continue
            result[package] = {
                "status": str(raw.get("status", "")),
                "reason": str(raw.get("reason", raw.get("skip_reason", ""))),
            }
    return result


def _normalize_package_list(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _validate_schema(
    connection: sqlite3.Connection,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> dict[str, set[str]]:
    columns = BASE._validate_schema(connection, errors, checks, db_path)
    tables = BASE._sqlite_tables(connection)
    if "event_log" not in tables:
        errors.append(_finding("event_log_missing", "physical corpus requires a durable event_log", str(db_path)))
    else:
        event_columns = BASE._columns(connection, "event_log")
        columns["event_log"] = event_columns
        required_groups = (
            ("event_id",),
            ("sequence", "sequence_no", "seq"),
            ("event_type", "record_type", "type"),
            ("payload_json", "payload"),
            ("content_sha256", "payload_sha256"),
            ("event_sha256",),
        )
        missing = ["/".join(group) for group in required_groups if not any(item in event_columns for item in group)]
        if missing:
            errors.append(_finding("event_log_columns", "event_log missing: " + ", ".join(missing), str(db_path)))
    return columns


def _validate_corpus_rows(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> dict[str, set[str]]:
    tables = BASE._sqlite_tables(connection)
    foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    checks["sqlite_foreign_key_errors"] = len(foreign_keys)
    if foreign_keys:
        errors.append(_finding("foreign_key_violation", f"{len(foreign_keys)} SQLite FK violations", str(db_path)))

    references = (
        ("screen_run", "SELECT COUNT(*) FROM screens s LEFT JOIN runs r ON r.run_id=s.run_id WHERE r.run_id IS NULL"),
        ("screen_app", "SELECT COUNT(*) FROM screens s LEFT JOIN apps a ON a.app_package=s.app_package WHERE a.app_package IS NULL"),
        ("element_screen", "SELECT COUNT(*) FROM elements e LEFT JOIN screens s ON s.screen_id=e.screen_id WHERE s.screen_id IS NULL"),
        ("transition_run", "SELECT COUNT(*) FROM transitions t LEFT JOIN runs r ON r.run_id=t.run_id WHERE r.run_id IS NULL"),
        ("transition_source", "SELECT COUNT(*) FROM transitions t LEFT JOIN screens s ON s.screen_id=t.source_screen_id WHERE s.screen_id IS NULL"),
        ("transition_target", "SELECT COUNT(*) FROM transitions t LEFT JOIN screens s ON s.screen_id=t.target_screen_id WHERE t.target_screen_id IS NOT NULL AND TRIM(t.target_screen_id)<>'' AND s.screen_id IS NULL"),
        ("transition_element", "SELECT COUNT(*) FROM transitions t LEFT JOIN elements e ON e.element_id=t.element_id WHERE t.element_id IS NOT NULL AND TRIM(t.element_id)<>'' AND e.element_id IS NULL"),
        ("transition_element_owner", "SELECT COUNT(*) FROM transitions t JOIN elements e ON e.element_id=t.element_id WHERE e.screen_id<>t.source_screen_id"),
        ("goal_run", "SELECT COUNT(*) FROM goals g LEFT JOIN runs r ON r.run_id=g.run_id WHERE r.run_id IS NULL"),
        ("goal_app", "SELECT COUNT(*) FROM goals g LEFT JOIN apps a ON a.app_package=g.app_package WHERE a.app_package IS NULL"),
        ("goal_screen", "SELECT COUNT(*) FROM goals g LEFT JOIN screens s ON s.screen_id=g.terminal_candidate_screen_id WHERE g.terminal_candidate_screen_id IS NOT NULL AND TRIM(g.terminal_candidate_screen_id)<>'' AND s.screen_id IS NULL"),
        ("goal_element", "SELECT COUNT(*) FROM goals g LEFT JOIN elements e ON e.element_id=g.terminal_candidate_element_id WHERE g.terminal_candidate_element_id IS NOT NULL AND TRIM(g.terminal_candidate_element_id)<>'' AND e.element_id IS NULL"),
        ("failure_run", "SELECT COUNT(*) FROM failures f LEFT JOIN runs r ON r.run_id=f.run_id WHERE r.run_id IS NULL"),
        ("failure_screen", "SELECT COUNT(*) FROM failures f LEFT JOIN screens s ON s.screen_id=f.screen_id WHERE f.screen_id IS NOT NULL AND TRIM(f.screen_id)<>'' AND s.screen_id IS NULL"),
        ("metric_run", "SELECT COUNT(*) FROM metrics m LEFT JOIN runs r ON r.run_id=m.run_id WHERE r.run_id IS NULL"),
        ("annotation_run", "SELECT COUNT(*) FROM annotations a LEFT JOIN runs r ON r.run_id=a.run_id WHERE r.run_id IS NULL"),
    )
    if BASE.REQUIRED_TABLES.issubset(tables):
        for label, query in references:
            count = int(BASE._scalar(connection, query) or 0)
            checks[f"reference_{label}"] = count
            if count:
                errors.append(_finding("referential_integrity", f"{label} has {count} invalid row(s)", str(db_path)))

    if "event_log" in tables:
        event_columns = BASE._columns(connection, "event_log")
        if {"sequence", "record_type", "record_id"}.issubset(event_columns):
            allowed_types_sql = ",".join("?" for _ in BASE.REQUIRED_TABLES)
            invalid_types = int(
                BASE._scalar(
                    connection,
                    f"SELECT COUNT(*) FROM event_log WHERE record_type NOT IN ({allowed_types_sql})",
                    tuple(sorted(BASE.REQUIRED_TABLES)),
                )
                or 0
            )
            checks["event_log_invalid_record_types"] = invalid_types
            if invalid_types:
                errors.append(
                    _finding(
                        "event_log_referential_integrity",
                        f"event_log has {invalid_types} unsupported record_type row(s)",
                        str(db_path),
                    )
                )
            for table in sorted(BASE.REQUIRED_TABLES & tables):
                table_columns = BASE._columns(connection, table)
                if not {"record_id", "event_sequence"}.issubset(table_columns):
                    continue
                broken_typed = int(
                    BASE._scalar(
                        connection,
                        f'SELECT COUNT(*) FROM "{table}" t LEFT JOIN event_log e '
                        "ON e.sequence=t.event_sequence AND e.record_type=? AND e.record_id=t.record_id "
                        "WHERE e.sequence IS NULL",
                        (table,),
                    )
                    or 0
                )
                orphan_events = int(
                    BASE._scalar(
                        connection,
                        f'SELECT COUNT(*) FROM event_log e LEFT JOIN "{table}" t '
                        "ON t.event_sequence=e.sequence AND t.record_id=e.record_id "
                        "WHERE e.record_type=? AND t.record_id IS NULL",
                        (table,),
                    )
                    or 0
                )
                checks[f"event_log_{table}_typed_reference"] = broken_typed + orphan_events
                if broken_typed or orphan_events:
                    errors.append(
                        _finding(
                            "event_log_referential_integrity",
                            f"{table}: typed_rows_without_event={broken_typed}, events_without_typed_row={orphan_events}",
                            str(db_path),
                        )
                    )

    for table, identifier in (
        ("apps", "app_package"), ("runs", "run_id"), ("screens", "screen_id"),
        ("elements", "element_id"), ("transitions", "transition_id"), ("goals", "goal_id"),
        ("failures", "failure_id"), ("metrics", "metric_id"), ("annotations", "annotation_id"),
        ("event_log", "event_id"),
    ):
        if table not in tables or identifier not in BASE._columns(connection, table):
            continue
        invalid = int(BASE._scalar(connection, f'SELECT COUNT(*) FROM "{table}" WHERE "{identifier}" IS NULL OR TRIM(CAST("{identifier}" AS TEXT))=""') or 0)
        duplicate = int(BASE._scalar(connection, f'SELECT COUNT(*) FROM (SELECT "{identifier}" FROM "{table}" GROUP BY "{identifier}" HAVING COUNT(*)>1)') or 0)
        if invalid or duplicate:
            errors.append(_finding("invalid_identifier", f"{table}.{identifier}: empty={invalid}, duplicate={duplicate}", str(db_path)))

    package_rows: dict[str, set[str]] = {}
    for table in ("apps", "screens", "goals", "failures", "metrics"):
        if table not in tables or "app_package" not in BASE._columns(connection, table):
            continue
        packages = {str(row[0]) for row in connection.execute(f'SELECT DISTINCT app_package FROM "{table}" WHERE app_package IS NOT NULL')}
        package_rows[table] = packages
        invalid = sorted(packages - set(profile.get("installed_packages", set())))
        if invalid:
            errors.append(_finding("uninstalled_app_observed", f"{table} contains non-installed/skipped packages: {invalid}", str(db_path)))
    checks["corpus_app_packages"] = {table: sorted(values) for table, values in package_rows.items()}

    apps_in_db = package_rows.get("apps", set())
    screens_in_db = package_rows.get("screens", set())
    if profile.get("partial_research") or profile.get("dynamic_inventory"):
        required_packages = set(profile.get("required_evidence_packages", set()))
        for package in sorted(required_packages):
            missing_tables: list[str] = []
            if package not in apps_in_db:
                missing_tables.append("apps")
            if package not in screens_in_db:
                missing_tables.append("screens")
            if "goals" not in tables or not int(
                BASE._scalar(
                    connection,
                    "SELECT COUNT(*) FROM goals WHERE app_package=?",
                    (package,),
                )
                or 0
            ):
                missing_tables.append("goals")
            if (
                "elements" not in tables
                or "screens" not in tables
                or not int(
                    BASE._scalar(
                        connection,
                        "SELECT COUNT(*) FROM elements e JOIN screens s ON s.screen_id=e.screen_id "
                        "WHERE s.app_package=?",
                        (package,),
                    )
                    or 0
                )
            ):
                missing_tables.append("elements")
            if missing_tables:
                errors.append(
                    _finding(
                        "selected_package_missing_evidence",
                        f"selected package {package} lacks deep evidence in {missing_tables}",
                        str(db_path),
                    )
                )
    if profile.get("dynamic_inventory"):
        excluded_packages = set(profile.get("excluded_packages", set()))
        observed_packages = set().union(*package_rows.values()) if package_rows else set()
        if observed_packages & excluded_packages:
            errors.append(
                _finding(
                    "excluded_inventory_package_observed",
                    "excluded inventory packages cannot have corpus observations",
                    str(db_path),
                )
            )
        versions = profile.get("inventory_versions", {})
        version_checks: dict[str, Any] = {}
        for package in sorted(profile.get("selected_packages", set())):
            expected = versions.get(package, {}) if isinstance(versions, Mapping) else {}
            expected_name = expected.get("version_name") if isinstance(expected, Mapping) else None
            expected_code = expected.get("version_code") if isinstance(expected, Mapping) else None
            expected_candidate = expected.get("candidate_id") if isinstance(expected, Mapping) else None
            app_rows = connection.execute(
                "SELECT app_version,payload_json FROM apps WHERE app_package=?",
                (package,),
            ).fetchall()
            app_valid = bool(app_rows)
            for app_version, payload_json in app_rows:
                try:
                    payload = json.loads(str(payload_json))
                except json.JSONDecodeError:
                    payload = {}
                if expected_name and str(app_version or "") != str(expected_name):
                    app_valid = False
                if expected_code and str(payload.get("version_code") or "") != str(expected_code):
                    app_valid = False
                if expected_candidate and payload.get("version_candidate_id") != expected_candidate:
                    app_valid = False
            screen_versions = {
                str(row[0] or "")
                for row in connection.execute(
                    "SELECT DISTINCT app_version FROM screens WHERE app_package=?",
                    (package,),
                )
            }
            if expected_name and screen_versions != {str(expected_name)}:
                app_valid = False
            goal_texts = {
                str(row[0] or "")
                for row in connection.execute(
                    "SELECT goal_text FROM goals WHERE app_package=?",
                    (package,),
                )
            }
            stage = profile.get("exploration_stage")
            if stage == EXPLORATION_STAGE_GOAL_DIRECTED:
                expected_goal_texts = {
                    str(task.get("goal_text") or "")
                    for task in profile.get("selected_tasks", [])
                    if task.get("app_package") == package
                }
                goal_code = "directed_goal_lineage_mismatch"
                goal_message = "SQLite goals must exactly match selected directed tasks"
            else:
                expected_goal_texts = {NEUTRAL_INVENTORY_GOAL}
                goal_code = "dynamic_goal_not_neutral"
                goal_message = "neutral stages may only persist the neutral discovery goal"
            if goal_texts != expected_goal_texts:
                errors.append(
                    _finding(
                        goal_code,
                        goal_message,
                        str(db_path),
                    )
                )
            version_checks[package] = {
                "app_rows": len(app_rows),
                "screen_version_count": len(screen_versions),
                "valid": app_valid,
            }
            if not app_valid:
                errors.append(
                    _finding(
                        "dynamic_inventory_version_mismatch",
                        "captured app/screen version differs from the pinned snapshot candidate",
                        str(db_path),
                    )
                )
        checks["dynamic_inventory_versions"] = version_checks

        sensitivity_by_package = profile.get("inventory_sensitivity_categories", {})
        sensitive_checks: dict[str, Any] = {}
        if isinstance(sensitivity_by_package, Mapping):
            for package in sorted(profile.get("selected_packages", set())):
                categories = sensitivity_by_package.get(package, [])
                if not isinstance(categories, list) or not categories:
                    continue
                invalid_screens = int(
                    BASE._scalar(
                        connection,
                        "SELECT COUNT(*) FROM screens WHERE app_package=? "
                        "AND (LOWER(COALESCE(evidence_mode,''))<>'metadata_only' "
                        "OR COALESCE(privacy_verified,0)<>0)",
                        (package,),
                    )
                    or 0
                )
                invalid_elements = int(
                    BASE._scalar(
                        connection,
                        "SELECT COUNT(*) FROM elements e JOIN screens s ON s.screen_id=e.screen_id "
                        "WHERE s.app_package=? "
                        "AND (LOWER(COALESCE(e.evidence_mode,''))<>'metadata_only' "
                        "OR COALESCE(e.privacy_verified,0)<>0)",
                        (package,),
                    )
                    or 0
                )
                metric_payloads: list[dict[str, Any]] = []
                for (payload_json,) in connection.execute(
                    "SELECT payload_json FROM metrics WHERE app_package=?",
                    (package,),
                ):
                    try:
                        payload = json.loads(str(payload_json))
                    except json.JSONDecodeError:
                        payload = {}
                    if isinstance(payload, dict):
                        metric_payloads.append(payload)
                policy_metrics = [
                    payload
                    for payload in metric_payloads
                    if payload.get("metric_dimension") == "sensitive_local_policy"
                    and payload.get("policy_event")
                    in SENSITIVE_LOCAL_POLICY_EVENTS
                ]
                transfer_values = [
                    payload.get("external_api_transfer_count")
                    for payload in metric_payloads
                    if "external_api_transfer_count" in payload
                ]
                transfer_zero = bool(policy_metrics) and bool(transfer_values)
                for value in transfer_values:
                    try:
                        transfer_zero = transfer_zero and float(value) == 0.0
                    except (TypeError, ValueError):
                        transfer_zero = False
                if invalid_screens or invalid_elements:
                    errors.append(
                        _finding(
                            "dynamic_sensitive_evidence_policy_violation",
                            "sensitive dynamic packages require metadata-only screens and elements",
                            str(db_path),
                        )
                    )
                if not policy_metrics:
                    errors.append(
                        _finding(
                            "dynamic_sensitive_api_attestation_missing",
                            "sensitive dynamic packages require a zero-transfer policy metric",
                            str(db_path),
                        )
                    )
                elif not transfer_zero:
                    errors.append(
                        _finding(
                            "dynamic_sensitive_api_transfer_nonzero",
                            "sensitive dynamic packages must attest external_api_transfer_count=0",
                            str(db_path),
                        )
                    )
                sensitive_checks[package] = {
                    "sensitivity_categories": sorted(str(value) for value in categories),
                    "invalid_metadata_only_screens": invalid_screens,
                    "invalid_metadata_only_elements": invalid_elements,
                    "zero_transfer_policy_metrics": len(policy_metrics),
                    "external_api_transfer_count_zero": transfer_zero,
                }
        checks["dynamic_sensitive_policy"] = sensitive_checks
    if profile.get("completed"):
        for package in sorted(profile.get("installed_packages", set())):
            if package not in apps_in_db or package not in screens_in_db:
                errors.append(_finding("installed_app_not_observed", f"completed run lacks rows/screens for {package}", str(db_path)))

    row_counts = {
        table: int(BASE._scalar(connection, f'SELECT COUNT(*) FROM "{table}"') or 0)
        for table in sorted(REQUIRED_TABLES & tables)
    }
    checks["corpus_row_counts"] = row_counts
    if row_counts.get("runs", 0) != 1:
        errors.append(_finding("run_row_count", "corpus must contain exactly one run row", str(db_path)))
    if profile.get("installed_packages"):
        required = ["apps", "screens", "elements"]
        if profile.get("completed"):
            required.extend(["goals", "metrics", "event_log"])
            if profile.get("exploration_stage") != EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
                required.append("transitions")
        for table in required:
            if row_counts.get(table, 0) == 0:
                errors.append(_finding("required_corpus_empty", f"{profile.get('name')} requires non-empty {table}", str(db_path)))

    run_id = str(profile.get("run_id", ""))
    if "runs" in tables:
        run_rows = connection.execute("SELECT * FROM runs").fetchall()
        run_columns = [str(item[0]) for item in connection.execute("SELECT name FROM pragma_table_info('runs')")]
        for row in run_rows:
            values = dict(zip(run_columns, row))
            if str(values.get("run_id", "")) != run_id:
                errors.append(_finding("run_id_mismatch", "SQLite run_id differs from manifest", str(db_path)))

    for table, table_columns in columns.items():
        if table not in tables:
            continue
        if "provenance" in table_columns:
            values = {str(row[0]) for row in connection.execute(f'SELECT DISTINCT provenance FROM "{table}"')}
            if values and values != {EXPECTED_PROVENANCE}:
                errors.append(_finding("record_governance_mismatch", f"{table}.provenance={sorted(values)}", str(db_path)))
        for column, expected in (
            ("dataset_role", EXPECTED_PROVENANCE),
            ("review_status", EXPECTED_REVIEW_STATUS),
            ("review_lifecycle", "candidate"),
        ):
            if column in table_columns:
                values = {str(row[0]) for row in connection.execute(f'SELECT DISTINCT "{column}" FROM "{table}"')}
                if values and values != {expected}:
                    errors.append(
                        _finding(
                            "record_governance_mismatch",
                            f"{table}.{column} must contain only {expected!r}, got {sorted(values)}",
                            str(db_path),
                        )
                    )
        lifecycle_col = BASE._pick(table_columns, "route_lifecycle", "route_status", "lifecycle_status")
        if lifecycle_col:
            values = {str(row[0]) for row in connection.execute(f'SELECT DISTINCT "{lifecycle_col}" FROM "{table}"')}
            if values - ALLOWED_LIFECYCLES:
                errors.append(_finding("route_not_candidate", f"{table}.{lifecycle_col}={sorted(values)}", str(db_path)))
        governed = {
            "canonical_catalog_version": BASE.EXPECTED_CATALOG_VERSION,
            "canonical_catalog_sha256": BASE.EXPECTED_CATALOG_SHA256,
            "canonical_equivalence_sha256": BASE.EXPECTED_EQUIVALENCE_SHA256,
        }
        for column, expected in governed.items():
            if column in table_columns:
                values = {str(row[0]) for row in connection.execute(f'SELECT DISTINCT "{column}" FROM "{table}"')}
                if values and values != {expected}:
                    errors.append(_finding("record_governance_mismatch", f"{table}.{column} must be {expected}", str(db_path)))

    if "corpus_metadata" in tables:
        metadata = dict(connection.execute("SELECT key, value FROM corpus_metadata"))
        expected_metadata = {
            "run_id": str(profile.get("run_id", "")),
            "provenance": EXPECTED_PROVENANCE,
            "dataset_role": EXPECTED_PROVENANCE,
            "review_status": EXPECTED_REVIEW_STATUS,
            "review_lifecycle": "candidate",
            "route_lifecycle": "shadow",
            "canonical_catalog_version": BASE.EXPECTED_CATALOG_VERSION,
            "canonical_catalog_sha256": BASE.EXPECTED_CATALOG_SHA256,
            "canonical_equivalence_sha256": BASE.EXPECTED_EQUIVALENCE_SHA256,
            "canonical_mutation_allowed": "false",
        }
        for key, expected in expected_metadata.items():
            if str(metadata.get(key, "")) != expected:
                errors.append(
                    _finding("corpus_metadata_mismatch", f"corpus_metadata.{key} must be {expected!r}", str(db_path))
                )
    return package_rows


def _typed_payloads(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    if table not in BASE._sqlite_tables(connection):
        return []
    rows: list[dict[str, Any]] = []
    for (raw_payload,) in connection.execute(
        f'SELECT payload_json FROM "{table}" ORDER BY event_sequence'
    ):
        try:
            payload = json.loads(str(raw_payload))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _contains_sensitive_human_semantics(value: object) -> bool:
    """Reject human-facing UI fields even when their value is not PII-like."""

    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().casefold().replace("-", "_")
            if (
                key in SENSITIVE_HUMAN_SEMANTIC_FIELDS
                and item not in (None, "", [], {})
            ):
                return True
            if _contains_sensitive_human_semantics(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_sensitive_human_semantics(item) for item in value)
    return False


def _sensitive_guard_shape_valid(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected_keys = {
        "policy_version",
        "evaluation_phase",
        "action_type",
        "allowed",
        "computed_final_or_consequential",
        "safe_menu_match",
        "reason",
    }
    if set(value) != expected_keys:
        return False
    allowed = value.get("allowed")
    final = value.get("computed_final_or_consequential")
    safe_menu = value.get("safe_menu_match")
    if any(type(item) is not bool for item in (allowed, final, safe_menu)):
        return False
    if (
        value.get("policy_version") != ACTION_GUARD_POLICY_VERSION
        or value.get("evaluation_phase") != ACTION_GUARD_EVALUATION_PHASE
        or value.get("action_type") != "click"
    ):
        return False
    expected_reason = (
        "physical_safe_menu_navigation"
        if allowed
        else "final_or_consequential_action"
        if final
        else "not_a_safe_menu_or_setting"
    )
    return bool(
        value.get("reason") == expected_reason
        and not (allowed and (final or not safe_menu))
        and not (final and allowed)
        and not (not final and not allowed and safe_menu)
    )


def _machine_string_list(value: object) -> bool:
    return bool(
        isinstance(value, list)
        and value == sorted(set(value))
        and all(
            isinstance(item, str)
            and re.fullmatch(r"[a-z][a-z0-9_.]*", item)
            for item in value
        )
    )


def _sensitive_local_decision_valid(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != SENSITIVE_LOCAL_DECISION_KEYS:
        return False
    action = value.get("action")
    reason = value.get("reason")
    candidate_count = value.get("candidate_count")
    element_id = value.get("selected_element_id")
    commitment = value.get("semantic_commitment_sha256")
    guard = value.get("action_guard")
    if (
        value.get("policy_version") != SENSITIVE_LOCAL_POLICY_VERSION
        or value.get("decision_source")
        != "deterministic_local_transient_accessibility"
        or action not in {"click", "stop"}
        or reason
        not in {
            "safe_local_menu_candidate",
            "sensitive_goal_entry_user_boundary",
            "no_safe_local_menu_candidate",
        }
        or type(candidate_count) is not int
        or candidate_count < 0
        or value.get("score_bucket")
        not in {
            None,
            "direct_goal_signal",
            "structural_gateway",
            "generic_safe_gateway",
        }
        or not isinstance(value.get("goal_family_id"), str)
        or not re.fullmatch(r"[a-z][a-z0-9_]*", value["goal_family_id"])
        or not isinstance(value.get("terminal_policy"), str)
        or not value.get("terminal_policy")
        or not _machine_string_list(value.get("matched_signal_ids"))
        or type(value.get("external_api_transfer_count")) is not int
        or value.get("external_api_transfer_count") != 0
        or value.get("human_text_persisted") is not False
    ):
        return False
    if element_id is not None and (
        not isinstance(element_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", element_id)
    ):
        return False
    if commitment is not None and (
        not isinstance(commitment, str) or not SHA256_RE.fullmatch(commitment)
    ):
        return False
    if action == "click":
        expected_guard = evaluate_auto_action_guard(
            "click", selected_label=SENSITIVE_GUARD_LABEL_BUCKET
        )
        return bool(
            reason == "safe_local_menu_candidate"
            and candidate_count >= 1
            and element_id is not None
            and commitment is not None
            and value.get("persisted_guard_label_bucket")
            == SENSITIVE_GUARD_LABEL_BUCKET
            and guard_evidence_matches(guard, expected_guard)
            and value.get("boundary_kind") is None
        )
    return bool(
        value.get("persisted_guard_label_bucket") is None
        and (guard is None or _sensitive_guard_shape_valid(guard))
        and (
            reason == "no_safe_local_menu_candidate"
            or value.get("boundary_kind") == "sensitive_goal_entry_user_boundary"
        )
    )


def _sensitive_local_signal_valid(value: object) -> bool:
    if not isinstance(value, Mapping) or set(value) != SENSITIVE_LOCAL_SIGNAL_KEYS:
        return False
    guard = value.get("action_guard")
    auto_allowed = value.get("auto_navigation_allowed")
    return bool(
        value.get("policy_version") == SENSITIVE_LOCAL_POLICY_VERSION
        and value.get("decision_source")
        == "deterministic_local_transient_accessibility"
        and isinstance(value.get("family_id"), str)
        and re.fullmatch(r"[a-z][a-z0-9_]*", value["family_id"])
        and _machine_string_list(value.get("matched_signal_ids"))
        and isinstance(value.get("selected_element_id"), str)
        and re.fullmatch(
            r"[A-Za-z0-9_.:-]{1,256}", value["selected_element_id"]
        )
        and isinstance(value.get("semantic_commitment_sha256"), str)
        and SHA256_RE.fullmatch(value["semantic_commitment_sha256"])
        and isinstance(value.get("terminal_policy"), str)
        and bool(value.get("terminal_policy"))
        and value.get("control_bucket")
        in {"clickable", "checkable", "text_field", "password"}
        and type(auto_allowed) is bool
        and _sensitive_guard_shape_valid(guard)
        and auto_allowed
        is bool(guard.get("allowed") and value.get("control_bucket") == "clickable")
        and type(value.get("external_api_transfer_count")) is int
        and value.get("external_api_transfer_count") == 0
        and value.get("human_text_persisted") is False
    )


def _validate_sensitive_local_metrics(
    connection: sqlite3.Connection,
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    """Validate the collector's label-free, zero-transfer sensitive metrics."""

    metrics = _typed_payloads(connection, "metrics")
    local_metrics = [
        metric
        for metric in metrics
        if metric.get("metric_dimension") in SENSITIVE_LOCAL_METRIC_DIMENSIONS
    ]
    sensitivity = profile.get("inventory_sensitivity_categories", {})
    sensitive_packages = {
        str(package): tuple(sorted(str(item) for item in categories))
        for package, categories in sensitivity.items()
        if isinstance(sensitivity, Mapping)
        and isinstance(categories, list)
        and categories
    }
    for screen in _typed_payloads(connection, "screens"):
        package = str(screen.get("app_package") or "")
        categories = tuple(
            sorted(
                {
                    str(category)
                    for category in screen.get(
                        "detected_sensitivity_categories", []
                    )
                    if str(category)
                }
            )
        )
        if package and screen.get("contains_personal_data") is True and categories:
            sensitive_packages[package] = tuple(
                sorted(set(sensitive_packages.get(package, ())) | set(categories))
            )
    tasks = [dict(task) for task in profile.get("selected_tasks", [])]
    task_by_goal = {_goal_id(task): task for task in tasks}
    valid_count = 0
    invalid_count = 0
    for metric in local_metrics:
        dimension = str(metric.get("metric_dimension") or "")
        package = str(metric.get("app_package") or "")
        goal_id = str(metric.get("goal_id") or "")
        task = task_by_goal.get(goal_id)
        invalid = bool(
            package not in sensitive_packages
            or task is None
            or task.get("app_package") != package
            or type(metric.get("external_api_transfer_count")) is not int
            or metric.get("external_api_transfer_count") != 0
            or metric.get("human_text_persisted") is not False
            or _contains_sensitive_human_semantics(metric)
        )
        if dimension == "sensitive_local_policy":
            event = str(metric.get("policy_event") or "")
            decision = metric.get("local_decision")
            invalid = invalid or bool(
                event not in SENSITIVE_LOCAL_POLICY_EVENTS
                or metric.get("fallback_mode")
                != "deterministic_local_transient_accessibility"
                or tuple(sorted(metric.get("sensitivity_categories") or []))
                != sensitive_packages.get(package, ())
                or metric.get("goal_candidate_id")
                != ((task.get("candidate_id") or None) if task else None)
                or metric.get("goal_family_id")
                != ((task.get("family_id") or None) if task else None)
                or (
                    event in SENSITIVE_LOCAL_DECISION_EVENTS
                    and not _sensitive_local_decision_valid(decision)
                )
                or (
                    event not in SENSITIVE_LOCAL_DECISION_EVENTS
                    and decision is not None
                )
            )
        elif dimension == "sensitive_local_goal_signal":
            invalid = invalid or bool(
                metric.get("policy_event") != "label_free_goal_signal_observed"
                or not _sensitive_local_signal_valid(
                    metric.get("local_signal_evidence")
                )
            )
        if invalid:
            invalid_count += 1
            errors.append(
                _finding(
                    "sensitive_local_metric_invalid",
                    "sensitive local metrics must be label-free, selected-goal-bound, and attest zero API transfer",
                    str(db_path),
                )
            )
        else:
            valid_count += 1
    if local_metrics and not sensitive_packages:
        errors.append(
            _finding(
                "sensitive_local_metric_unscoped",
                "sensitive local metrics require a sensitivity-classified dynamic package",
                str(db_path),
            )
        )
    checks["sensitive_local_metrics"] = {
        "count": len(local_metrics),
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "dimensions": sorted(
            {str(metric.get("metric_dimension") or "") for metric in local_metrics}
        ),
    }


def _validate_goal_and_terminal_lineage(
    connection: sqlite3.Connection,
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    """Bind selected tasks to goals and attempt-local terminal metrics."""

    if not profile.get("dynamic_inventory"):
        return
    stage = profile.get("exploration_stage")
    tasks = [dict(task) for task in profile.get("selected_tasks", [])]
    task_by_id = {str(task.get("task_id") or ""): task for task in tasks}
    goal_payloads = _typed_payloads(connection, "goals")
    metric_payloads = _typed_payloads(connection, "metrics")

    if stage in {
        EXPLORATION_STAGE_INITIAL_CAPTURE,
        EXPLORATION_STAGE_NEUTRAL_DISCOVERY,
    }:
        expected_neutral_goal_ids = {_goal_id(task) for task in tasks}
        actual_neutral_goal_ids = {
            str(goal.get("goal_id") or "") for goal in goal_payloads
        }
        if (
            actual_neutral_goal_ids != expected_neutral_goal_ids
            or len(goal_payloads) != len(expected_neutral_goal_ids)
        ):
            errors.append(
                _finding(
                    "neutral_goal_lineage_violation",
                    "neutral SQLite goals must exactly cover selected tasks",
                    str(db_path),
                )
            )
        for goal in goal_payloads:
            evidence = goal.get("evidence")
            if (
                str(goal.get("goal_text", goal.get("user_goal", "")))
                != NEUTRAL_INVENTORY_GOAL
                or (
                    isinstance(evidence, Mapping)
                    and any(evidence.get(field) not in (None, "") for field in GOAL_LINEAGE_FIELDS)
                )
            ):
                errors.append(
                    _finding(
                        "neutral_goal_lineage_violation",
                        "neutral stages cannot persist candidate-directed goal lineage",
                        str(db_path),
                    )
                )
    elif stage == EXPLORATION_STAGE_GOAL_DIRECTED:
        expected_goals = {_goal_id(task): task for task in tasks}
        actual_goals = {
            str(goal.get("goal_id") or ""): goal for goal in goal_payloads
        }
        if set(actual_goals) != set(expected_goals) or len(actual_goals) != len(goal_payloads):
            errors.append(
                _finding(
                    "directed_goal_lineage_mismatch",
                    "SQLite goal IDs must exactly cover the selected candidate tasks",
                    str(db_path),
                )
            )
        for goal_id, task in expected_goals.items():
            goal = actual_goals.get(goal_id)
            evidence = goal.get("evidence") if isinstance(goal, Mapping) else None
            expected_evidence = {
                "task_id": task["task_id"],
                "version_key": task["version_key"],
                "candidate_id": task["candidate_id"],
                "family_id": task["family_id"],
                "terminal_policy": task["terminal_policy"],
                "source_run_id": task["source_run_id"],
                "source_inventory_snapshot_id": task[
                    "source_inventory_snapshot_id"
                ],
                "confidence": task["confidence"],
                "candidate_rank": task["candidate_rank"],
                "source_artifact_sha256": task["source_artifact_sha256"],
            }
            if (
                not isinstance(goal, Mapping)
                or goal.get("app_package") != task["app_package"]
                or goal.get("goal_text", goal.get("user_goal")) != task["goal_text"]
                or goal.get("status") != EXPECTED_REVIEW_STATUS
                or float(goal.get("terminal_confidence") or 0.0) != 0.0
                or not isinstance(evidence, Mapping)
                or any(evidence.get(key) != value for key, value in expected_evidence.items())
            ):
                errors.append(
                    _finding(
                        "directed_goal_lineage_mismatch",
                        f"SQLite goal {goal_id!r} differs from its selected task lineage",
                        str(db_path),
                    )
                )

    summaries = [
        row for row in metric_payloads if row.get("metric_dimension") == "task_summary"
    ]
    summaries_by_task: dict[str, list[dict[str, Any]]] = {}
    for summary in summaries:
        task_id = str(summary.get("task_id") or "")
        task = task_by_id.get(task_id)
        summaries_by_task.setdefault(task_id, []).append(summary)
        status = str(summary.get("terminal_status") or "")
        expected_goal_id = _goal_id(task) if task is not None else ""
        expected_completion = (
            "candidate_destination_found"
            if status == "destination_reached"
            else status
            if status in DISCOVERY_TERMINAL_STATUSES
            else None
        )
        common_invalid = (
            task is None
            or summary.get("app_package") != task.get("app_package")
            or summary.get("goal_id") != expected_goal_id
            or not isinstance(summary.get("attempt_number"), int)
            or isinstance(summary.get("attempt_number"), bool)
            or int(summary.get("attempt_number") or 0) < 1
            or summary.get("attempt_count") != 1
            or summary.get("human_confirmed_success") is not None
            or summary.get("human_confirmed_false_positive") is not None
            or "success_count" in summary
            or "false_positive_count" in summary
        )
        if (
            stage != EXPLORATION_STAGE_NEUTRAL_DISCOVERY
            and status in DISCOVERY_TERMINAL_STATUSES
        ):
            common_invalid = True
        if stage == EXPLORATION_STAGE_GOAL_DIRECTED and task is not None:
            common_invalid = common_invalid or any(
                summary.get(key) != value
                for key, value in {
                    "goal_candidate_id": task["candidate_id"],
                    "goal_family_id": task["family_id"],
                    "terminal_policy": task["terminal_policy"],
                    "source_goal_run_id": task["source_run_id"],
                    "source_inventory_snapshot_id": task[
                        "source_inventory_snapshot_id"
                    ],
                    "source_goal_artifact_sha256": task[
                        "source_artifact_sha256"
                    ],
                }.items()
            )
            if status in DISCOVERY_TERMINAL_STATUSES:
                common_invalid = True
            if status == "destination_reached" and (
                summary.get("candidate_destination_found") is not True
                or summary.get("completion_class") != expected_completion
            ):
                common_invalid = True
            if status != "destination_reached" and summary.get(
                "candidate_destination_found"
            ) is not False:
                common_invalid = True
        elif stage == EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
            neutral_completion = (
                status
                if status in DISCOVERY_TERMINAL_STATUSES
                else "user_boundary"
                if status.startswith("boundary:")
                else "safe_stop"
                if status.startswith("stopped:")
                else "failed"
                if status.startswith("failed:")
                else None
            )
            if (
                neutral_completion is None
                or summary.get("completion_class") != neutral_completion
                or summary.get("candidate_destination_found") is not False
                or summary.get("goal_candidate_id") is not None
                or summary.get("goal_family_id") is not None
                or summary.get("terminal_policy") is not None
            ):
                common_invalid = True
        if common_invalid:
            errors.append(
                _finding(
                    "task_summary_lineage_invalid",
                    "task summary is not an attempt-local, non-self-confirming selected-task result",
                    str(db_path),
                )
            )

    for task_id, rows in summaries_by_task.items():
        attempts = [row.get("attempt_number") for row in rows]
        if len(attempts) != len(set(attempts)):
            errors.append(
                _finding(
                    "task_summary_attempt_duplicate",
                    f"task {task_id!r} contains duplicate attempt summaries",
                    str(db_path),
                )
            )

    neutral_terminal_summaries: list[dict[str, Any]] = []
    if stage == EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
        for task_id, task in task_by_id.items():
            rows = summaries_by_task.get(task_id, [])
            terminal_rows = [
                row
                for row in rows
                if str(row.get("terminal_status") or "") in DISCOVERY_TERMINAL_STATUSES
            ]
            latest = max(
                rows,
                key=lambda row: int(row.get("attempt_number") or 0),
                default=None,
            )
            if profile.get("completed") and (
                len(terminal_rows) != 1
                or latest is None
                or latest not in terminal_rows
            ):
                errors.append(
                    _finding(
                        "discovery_terminal_attempt_invalid",
                        f"completed neutral task {task_id!r} must end in exactly one latest bounded-discovery terminal attempt",
                        str(db_path),
                    )
                )
            neutral_terminal_summaries.extend(terminal_rows)

    if profile.get("completed") and stage in {
        EXPLORATION_STAGE_NEUTRAL_DISCOVERY,
        EXPLORATION_STAGE_GOAL_DIRECTED,
    }:
        missing = sorted(set(task_by_id) - set(summaries_by_task))
        if missing:
            errors.append(
                _finding(
                    "task_summary_missing",
                    f"completed staged run lacks task summaries: {missing}",
                    str(db_path),
                )
            )

    if stage == EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
        coverage_rows = [
            row
            for row in metric_payloads
            if row.get("metric_dimension") == "neutral_discovery_coverage"
        ]
        coverage_pairs = {
            (str(row.get("goal_id") or ""), str(row.get("coverage_outcome") or ""))
            for row in coverage_rows
        }
        for summary in neutral_terminal_summaries:
            pair = (
                str(summary.get("goal_id") or ""),
                str(summary.get("terminal_status") or ""),
            )
            if pair not in coverage_pairs:
                errors.append(
                    _finding(
                        "discovery_terminal_evidence_missing",
                        "bounded discovery terminal requires matching neutral coverage evidence",
                        str(db_path),
                    )
                )
        false_success = any(
            bool(row.get("candidate_destination_found"))
            or bool(row.get("destination_found_success"))
            or bool(row.get("success_count"))
            for row in metric_payloads
        )
        if false_success:
            errors.append(
                _finding(
                    "discovery_success_claim_forbidden",
                    "bounded discovery outcomes cannot claim route/destination success",
                    str(db_path),
                )
            )
        checks["neutral_discovery_completion"] = {
            "task_summary_count": len(summaries),
            "coverage_metric_count": len(coverage_rows),
            "successful_route_coverage": False,
        }
    else:
        misplaced_discovery_rows = [
            row
            for row in metric_payloads
            if row.get("metric_dimension") == "neutral_discovery_coverage"
            or row.get("terminal_status") in DISCOVERY_TERMINAL_STATUSES
        ]
        if misplaced_discovery_rows:
            errors.append(
                _finding(
                    "discovery_terminal_stage_misuse",
                    "discovery completion evidence is only valid in neutral_menu_discovery",
                    str(db_path),
                )
            )

    if stage == EXPLORATION_STAGE_GOAL_DIRECTED:
        policy_destination_goal_ids = {
            str(row.get("goal_id") or "")
            for row in metric_payloads
            if row.get("phase") == "destination_reached"
        }
        latest_status: dict[str, str] = {}
        for task_id, rows in summaries_by_task.items():
            latest = max(rows, key=lambda row: int(row.get("attempt_number") or 0))
            latest_status[task_id] = str(latest.get("terminal_status") or "")
        verified = {
            task_id: (
                latest_status.get(task_id) == "destination_reached"
                and _goal_id(task) in policy_destination_goal_ids
            )
            for task_id, task in task_by_id.items()
        }
        if profile.get("completed") and (not verified or not all(verified.values())):
            errors.append(
                _finding(
                    "directed_destination_evidence_missing",
                    "completed directed tasks require destination response evidence",
                    str(db_path),
                )
            )
        checks["directed_goal_destination_evidence"] = verified

    checks["task_summary_attempts"] = {
        task_id: sorted(
            int(row.get("attempt_number") or 0) for row in rows
        )
        for task_id, rows in sorted(summaries_by_task.items())
    }


def _strict_guard_evidence_matches(
    value: object,
    expected: Mapping[str, object],
) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(expected):
        return False
    for key, expected_value in expected.items():
        actual = value.get(key)
        if isinstance(expected_value, bool):
            if type(actual) is not bool or actual is not expected_value:
                return False
        elif type(actual) is not type(expected_value) or actual != expected_value:
            return False
    return True


def _finite_coordinate(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _coordinate_quad(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        return None
    coordinates = tuple(_finite_coordinate(item) for item in value)
    if any(item is None for item in coordinates):
        return None
    return tuple(float(item) for item in coordinates)  # type: ignore[arg-type,return-value]


def _rectangle(value: object) -> tuple[float, float, float, float] | None:
    if isinstance(value, Mapping):
        if not {"left", "top", "right", "bottom"}.issubset(value):
            return None
        value = [value["left"], value["top"], value["right"], value["bottom"]]
    rectangle = _coordinate_quad(value)
    if rectangle is None:
        return None
    left, top, right, bottom = rectangle
    if right <= left or bottom <= top:
        return None
    return rectangle


def _rectangles(value: object) -> tuple[tuple[float, float, float, float], ...] | None:
    """Parse either one structural rectangle or a list of rectangles.

    An empty list is valid evidence that Accessibility exposed no scrollable
    region. Invalid members fail the complete evidence set closed instead of
    being silently ignored.
    """

    direct = _rectangle(value)
    if direct is not None:
        return (direct,)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    parsed: list[tuple[float, float, float, float]] = []
    for item in value:
        rectangle = _rectangle(item)
        if rectangle is None:
            return None
        parsed.append(rectangle)
    return tuple(parsed)


def _json_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _coordinate_sets_match(
    left: Sequence[float],
    right: Sequence[float],
    *,
    tolerance: float = 1e-6,
) -> bool:
    return len(left) == len(right) and all(
        math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=tolerance)
        for a, b in zip(left, right)
    )


def _rectangle_sets_match(
    left: Sequence[Sequence[float]],
    right: Sequence[Sequence[float]],
) -> bool:
    return len(left) == len(right) and all(
        _coordinate_sets_match(a, b) for a, b in zip(left, right)
    )


def _structural_regions_from_screen(
    payload: Mapping[str, Any],
) -> tuple[tuple[float, float, float, float], ...] | None:
    for key in (
        "structural_bounds",
        "screen_bounds",
        "window_bounds",
        "display_bounds",
        "scroll_bounds",
        "scrollable_region",
    ):
        if key not in payload:
            continue
        return _rectangles(payload.get(key))
    return ()


def _validate_auto_scroll_distances(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    """Fail closed unless each automatic forward swipe is a proven page swipe.

    The check is deliberately independent of the collector and the persisted
    action guard. It reconciles typed SQLite columns with the immutable payload,
    then measures the actual gesture against the source screen's Accessibility
    scroll region. A root structural bound is accepted only when Accessibility
    did not expose a scrollable region.
    """

    checks["auto_scroll_target_region_ratio"] = {
        "minimum": AUTO_SCROLL_MIN_REGION_RATIO,
        "maximum": AUTO_SCROLL_MAX_REGION_RATIO,
        "target": 0.78,
    }
    checks["auto_scroll_transition_count"] = 0
    checks["auto_scroll_validated_count"] = 0
    checks["auto_scroll_failure_counts"] = {}
    if "transitions" not in columns:
        return

    screen_rows: dict[str, tuple[object, Mapping[str, Any]]] = {}
    if "screens" in columns:
        for screen_id, typed_regions_json, payload_json in connection.execute(
            "SELECT screen_id, scrollable_regions_json, payload_json FROM screens"
        ):
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError):
                payload = {}
            screen_rows[str(screen_id)] = (
                _json_value(typed_regions_json),
                payload if isinstance(payload, Mapping) else {},
            )

    # A persisted root/container bound is a structural fallback only. We do not
    # synthesize a region by unioning arbitrary controls because that could make
    # a short or overshooting swipe appear valid.
    structural_element_regions: dict[str, list[tuple[float, float, float, float]]] = {}
    if "elements" in columns:
        for typed_screen_id, typed_bounds_json, payload_json in connection.execute(
            "SELECT screen_id, bounds_json, payload_json FROM elements"
        ):
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, Mapping):
                continue
            payload_screen_id = str(payload.get("screen_id") or "")
            screen_id = str(typed_screen_id or "")
            if not screen_id or payload_screen_id != screen_id:
                continue
            if payload.get("parent_id") not in (None, ""):
                continue
            typed_bounds = _rectangle(_json_value(typed_bounds_json))
            payload_bounds = _rectangle(payload.get("bounds"))
            if (
                typed_bounds is None
                or payload_bounds is None
                or not _coordinate_sets_match(typed_bounds, payload_bounds)
            ):
                continue
            structural_element_regions.setdefault(screen_id, []).append(typed_bounds)

    failure_counts: Counter[str] = Counter()
    auto_scroll_count = 0
    validated_count = 0

    rows = connection.execute(
        "SELECT transition_id, source_screen_id, action_type, auto_executed, "
        "coordinates_json, scroll_direction, scroll_distance, payload_json "
        "FROM transitions ORDER BY event_sequence"
    ).fetchall()
    for (
        transition_id,
        typed_source_screen_id,
        typed_action,
        typed_auto,
        typed_coordinates_json,
        typed_direction,
        typed_distance,
        payload_json,
    ) in rows:
        try:
            payload = json.loads(str(payload_json))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, Mapping):
            payload = {}

        typed_is_scroll = str(typed_action or "").strip().casefold() == "scroll_forward"
        payload_is_scroll = str(payload.get("action_type") or "").strip().casefold() == "scroll_forward"
        typed_is_auto = int(typed_auto or 0) == 1
        payload_is_auto = payload.get("auto_executed") is True
        if not ((typed_is_scroll and typed_is_auto) or (payload_is_scroll and payload_is_auto)):
            continue

        auto_scroll_count += 1
        location = f"{db_path}:transition/{transition_id}"
        transition_errors_before = len(errors)

        if not (typed_is_scroll and payload_is_scroll and typed_is_auto and payload_is_auto):
            code = "auto_scroll_declaration_inconsistent"
            failure_counts[code] += 1
            errors.append(
                _finding(
                    code,
                    "typed and payload declarations must both identify an automatic scroll_forward",
                    location,
                )
            )

        typed_coordinates = _coordinate_quad(_json_value(typed_coordinates_json))
        payload_coordinates = _coordinate_quad(payload.get("coordinates"))
        coordinates: tuple[float, float, float, float] | None = None
        if typed_coordinates is None or payload_coordinates is None:
            code = "auto_scroll_coordinates_missing_or_invalid"
            failure_counts[code] += 1
            errors.append(
                _finding(code, "automatic forward scroll requires four finite gesture coordinates", location)
            )
        elif not _coordinate_sets_match(typed_coordinates, payload_coordinates):
            code = "auto_scroll_coordinate_evidence_inconsistent"
            failure_counts[code] += 1
            errors.append(
                _finding(code, "typed and payload gesture coordinates disagree", location)
            )
        else:
            coordinates = typed_coordinates

        direction = str(typed_direction or "").strip().casefold()
        payload_direction = str(payload.get("scroll_direction") or "").strip().casefold()
        if direction != "forward" or payload_direction != "forward":
            code = "auto_scroll_direction_invalid"
            failure_counts[code] += 1
            errors.append(
                _finding(code, "scroll_forward requires matching forward direction evidence", location)
            )

        typed_distance_number = _finite_coordinate(typed_distance)
        payload_distance_number = _finite_coordinate(payload.get("scroll_distance"))
        if (
            typed_distance_number is None
            or payload_distance_number is None
            or typed_distance_number <= 0
            or payload_distance_number <= 0
        ):
            code = "auto_scroll_distance_missing_or_invalid"
            failure_counts[code] += 1
            errors.append(
                _finding(code, "automatic forward scroll requires a positive finite declared distance", location)
            )
        elif not math.isclose(
            typed_distance_number,
            payload_distance_number,
            rel_tol=0.0,
            abs_tol=AUTO_SCROLL_DISTANCE_TOLERANCE_PX,
        ):
            code = "auto_scroll_distance_evidence_inconsistent"
            failure_counts[code] += 1
            errors.append(_finding(code, "typed and payload scroll distances disagree", location))

        if coordinates is not None:
            start_x, start_y, end_x, end_y = coordinates
            coordinate_distance = start_y - end_y
            if coordinate_distance <= 0:
                code = "auto_scroll_direction_invalid"
                failure_counts[code] += 1
                errors.append(
                    _finding(code, "forward scrolling requires an upward finger gesture", location)
                )
            elif (
                typed_distance_number is not None
                and payload_distance_number is not None
                and (
                    not math.isclose(
                        typed_distance_number,
                        coordinate_distance,
                        rel_tol=0.0,
                        abs_tol=AUTO_SCROLL_DISTANCE_TOLERANCE_PX,
                    )
                    or not math.isclose(
                        payload_distance_number,
                        coordinate_distance,
                        rel_tol=0.0,
                        abs_tol=AUTO_SCROLL_DISTANCE_TOLERANCE_PX,
                    )
                )
            ):
                code = "auto_scroll_distance_inconsistent"
                failure_counts[code] += 1
                errors.append(
                    _finding(code, "declared scroll distance disagrees with coordinate delta", location)
                )

        typed_source = str(typed_source_screen_id or "")
        payload_source = str(payload.get("source_screen_id") or "")
        source_screen_id = typed_source if typed_source == payload_source else ""
        if not source_screen_id or source_screen_id not in screen_rows:
            code = "auto_scroll_source_screen_missing"
            failure_counts[code] += 1
            errors.append(
                _finding(code, "automatic forward scroll lacks matching source-screen evidence", location)
            )
        elif coordinates is not None:
            typed_regions_value, screen_payload = screen_rows[source_screen_id]
            typed_regions = _rectangles(typed_regions_value)
            payload_regions = _rectangles(screen_payload.get("scrollable_regions"))
            regions: tuple[tuple[float, float, float, float], ...] | None = None
            if (
                typed_regions is None
                or payload_regions is None
                or not _rectangle_sets_match(typed_regions, payload_regions)
            ):
                code = "auto_scroll_region_evidence_inconsistent"
                failure_counts[code] += 1
                errors.append(
                    _finding(code, "typed and payload source-screen scroll regions disagree", location)
                )
            elif typed_regions:
                regions = typed_regions
            else:
                explicit_structural = _structural_regions_from_screen(screen_payload)
                if explicit_structural is None:
                    code = "auto_scroll_region_evidence_inconsistent"
                    failure_counts[code] += 1
                    errors.append(
                        _finding(code, "source-screen structural bounds are malformed", location)
                    )
                elif explicit_structural:
                    regions = explicit_structural
                else:
                    roots = structural_element_regions.get(source_screen_id, [])
                    regions = tuple(roots) if roots else None

            if regions is None or not regions:
                code = "auto_scroll_region_evidence_missing"
                failure_counts[code] += 1
                errors.append(
                    _finding(
                        code,
                        "automatic forward scroll lacks a scrollable region or root structural bound",
                        location,
                    )
                )
            else:
                start_x, start_y, end_x, end_y = coordinates
                containing = [
                    region
                    for region in regions
                    if region[0] <= start_x <= region[2]
                    and region[0] <= end_x <= region[2]
                    and region[1] <= start_y <= region[3]
                    and region[1] <= end_y <= region[3]
                ]
                if not containing:
                    code = "auto_scroll_coordinates_outside_region"
                    failure_counts[code] += 1
                    errors.append(
                        _finding(code, "gesture endpoints fall outside the proven source scroll region", location)
                    )
                else:
                    vertical_distance = start_y - end_y
                    valid_page_region = False
                    for left, top, right, bottom in containing:
                        width = right - left
                        height = bottom - top
                        horizontal_drift = abs(start_x - end_x)
                        ratio = vertical_distance / height
                        if (
                            vertical_distance > 0
                            and horizontal_drift <= max(2.0, width * AUTO_SCROLL_MAX_HORIZONTAL_DRIFT_RATIO)
                            and AUTO_SCROLL_MIN_REGION_RATIO <= ratio <= AUTO_SCROLL_MAX_REGION_RATIO
                        ):
                            valid_page_region = True
                            break
                    if not valid_page_region:
                        code = "auto_scroll_not_near_page"
                        failure_counts[code] += 1
                        errors.append(
                            _finding(
                                code,
                                "gesture must be a near-page vertical scroll within 72--85% of the source region",
                                location,
                            )
                        )

        if len(errors) == transition_errors_before:
            validated_count += 1

    checks["auto_scroll_transition_count"] = auto_scroll_count
    checks["auto_scroll_validated_count"] = validated_count
    checks["auto_scroll_failure_counts"] = dict(sorted(failure_counts.items()))


def _validate_auto_action_guards(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    manifest: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    """Independently reclassify every persisted automatic transition."""

    if "transitions" not in columns:
        checks["auto_action_guard_transition_count"] = 0
        checks["auto_action_guard_attested_count"] = 0
        checks["recomputed_unsafe_auto_click_count"] = 0
        checks["recomputed_final_action_auto_click_count"] = 0
        return

    element_payloads: dict[str, dict[str, Any]] = {}
    if "elements" in columns:
        for element_id, payload_json in connection.execute(
            "SELECT element_id, payload_json FROM elements"
        ):
            try:
                payload = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError):
                payload = {}
            element_payloads[str(element_id)] = payload if isinstance(payload, dict) else {}

    auto_count = 0
    attested_count = 0
    click_count = 0
    recomputed_unsafe = 0
    recomputed_final = 0
    failure_counts: Counter[str] = Counter()

    transition_columns = columns.get("transitions", set())
    selected_columns = (
        "transition_id",
        "action_type",
        "element_id",
        "auto_executed",
        "is_final_action",
        "unsafe_action",
        "selected_label",
        "auto_action_guard_json",
        "payload_json",
    )
    select_sql = ", ".join(
        column if column in transition_columns else f"NULL AS {column}"
        for column in selected_columns
    )
    order_sql = " ORDER BY event_sequence" if "event_sequence" in transition_columns else ""
    rows = connection.execute(
        f"SELECT {select_sql} FROM transitions{order_sql}"
    ).fetchall()
    for (
        transition_id,
        typed_action,
        typed_element_id,
        typed_auto,
        typed_final,
        typed_unsafe,
        typed_selected_label,
        typed_guard_json,
        payload_json,
    ) in rows:
        try:
            payload = json.loads(str(payload_json))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload_auto = payload.get("auto_executed")
        if int(typed_auto or 0) != 1 and payload_auto is not True:
            continue
        auto_count += 1
        transition_location = f"{db_path}:transition/{transition_id}"
        if int(typed_auto or 0) != 1 or payload_auto is not True:
            failure_counts["auto_action_declaration_inconsistent"] += 1
            errors.append(
                _finding(
                    "auto_action_declaration_inconsistent",
                    "typed and payload auto_executed declarations disagree",
                    transition_location,
                )
            )

        action = str(payload.get("action_type") or typed_action or "").strip().casefold()
        if action == "click":
            click_count += 1
        element_id = str(payload.get("element_id") or typed_element_id or "")
        element = element_payloads.get(element_id, {})
        element_labels = tuple(
            element.get(key, "")
            for key in ("label", "text", "content_description", "inferred_label")
        )
        decision = evaluate_auto_action_guard(
            action,
            selected_label=payload.get("selected_label", ""),
            element_labels=element_labels,
            resource_id=element.get("resource_id", ""),
        )
        expected_guard = decision.evidence()
        guard = payload.get("auto_action_guard")
        try:
            typed_guard = json.loads(str(typed_guard_json))
        except (TypeError, json.JSONDecodeError):
            typed_guard = None
        guard_valid = (
            _strict_guard_evidence_matches(guard, expected_guard)
            and _strict_guard_evidence_matches(typed_guard, expected_guard)
            and str(typed_selected_label or "")
            == str(payload.get("selected_label") or "")
        )
        if guard_valid:
            attested_count += 1
        else:
            failure_counts["auto_action_guard_missing_or_inconsistent"] += 1
            errors.append(
                _finding(
                    "auto_action_guard_missing_or_inconsistent",
                    "automatic transition lacks exact pre-execution guard attestation",
                    transition_location,
                )
            )

        if isinstance(guard, Mapping):
            if guard.get("policy_version") != ACTION_GUARD_POLICY_VERSION:
                failure_counts["auto_action_guard_policy_version"] += 1
                errors.append(
                    _finding(
                        "auto_action_guard_policy_version",
                        "automatic transition uses an unsupported guard policy version",
                        transition_location,
                    )
                )
            if guard.get("evaluation_phase") != ACTION_GUARD_EVALUATION_PHASE:
                failure_counts["auto_action_guard_not_pre_execution"] += 1
                errors.append(
                    _finding(
                        "auto_action_guard_not_pre_execution",
                        "automatic transition guard was not attested pre-execution",
                        transition_location,
                    )
                )

        declared_final = payload.get("is_final_action")
        declared_unsafe = payload.get("unsafe_action")
        expected_unsafe = not decision.allowed
        declaration_consistent = (
            type(declared_final) is bool
            and declared_final is decision.computed_final_or_consequential
            and type(declared_unsafe) is bool
            and declared_unsafe is expected_unsafe
            and int(typed_final or 0) == int(decision.computed_final_or_consequential)
            and int(typed_unsafe or 0) == int(expected_unsafe)
        )
        if not declaration_consistent:
            failure_counts["auto_action_classification_inconsistent"] += 1
            errors.append(
                _finding(
                    "auto_action_classification_inconsistent",
                    "declared final/unsafe flags disagree with independent recomputation",
                    transition_location,
                )
            )

        if action == "click":
            if not element:
                failure_counts["auto_click_source_element_missing"] += 1
                errors.append(
                    _finding(
                        "auto_click_source_element_missing",
                        "automatic click lacks its source UI element evidence",
                        transition_location,
                    )
                )
            if decision.computed_final_or_consequential:
                recomputed_final += 1
                failure_counts["final_action_auto_click_recomputed"] += 1
                errors.append(
                    _finding(
                        "final_action_auto_click_recomputed",
                        "automatic click independently classifies as final/consequential",
                        transition_location,
                    )
                )
            if not decision.safe_menu_match:
                failure_counts["auto_click_not_safe_menu"] += 1
                errors.append(
                    _finding(
                        "auto_click_not_safe_menu",
                        "automatic click is not independently classified as menu/settings navigation",
                        transition_location,
                    )
                )
            if (
                not decision.allowed
                or not guard_valid
                or not declaration_consistent
                or not element
            ):
                recomputed_unsafe += 1
        elif not decision.allowed or not guard_valid or not declaration_consistent:
            failure_counts["unsafe_auto_transition_recomputed"] += 1
            errors.append(
                _finding(
                    "unsafe_auto_transition_recomputed",
                    "automatic non-click transition failed independent guard verification",
                    transition_location,
                )
            )

    checks["auto_action_guard_policy_version"] = ACTION_GUARD_POLICY_VERSION
    checks["auto_action_guard_transition_count"] = auto_count
    checks["auto_action_guard_attested_count"] = attested_count
    checks["auto_executed_click_count"] = click_count
    checks["recomputed_unsafe_auto_click_count"] = recomputed_unsafe
    checks["recomputed_final_action_auto_click_count"] = recomputed_final
    checks["auto_action_guard_failure_counts"] = dict(sorted(failure_counts.items()))

    expected_counts = {
        "unsafe_auto_click_count": recomputed_unsafe,
        "final_action_auto_click_count": recomputed_final,
    }
    safety = manifest.get("safety")
    for name, expected in expected_counts.items():
        value = safety.get(name) if isinstance(safety, Mapping) else None
        if type(value) is not int or value != expected:
            errors.append(
                _finding(
                    "manifest_safety_metric_not_evidence_derived",
                    f"manifest {name} does not equal independently recomputed evidence count",
                    str(db_path.parent / "manifest.json"),
                )
            )

    if "metrics" in columns:
        for metric_id, payload_json in connection.execute(
            "SELECT metric_id, payload_json FROM metrics"
        ):
            try:
                metric = json.loads(str(payload_json))
            except (TypeError, json.JSONDecodeError):
                metric = {}
            if not isinstance(metric, dict) or metric.get("metric_dimension") != "run_summary":
                continue
            for name, expected in expected_counts.items():
                value = metric.get(name)
                if type(value) is not int or value != expected:
                    errors.append(
                        _finding(
                            "summary_safety_metric_not_evidence_derived",
                            f"run summary {name} does not equal recomputed evidence count",
                            f"{db_path}:metric/{metric_id}",
                        )
                    )


def _validate_safety(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    manifest: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
    db_path: Path,
) -> None:
    BASE._validate_safety(connection, columns, manifest, errors, checks, db_path)
    _validate_auto_action_guards(connection, columns, manifest, errors, checks, db_path)
    _validate_auto_scroll_distances(connection, columns, errors, checks, db_path)
    metric_error_start = len(errors)
    BASE._validate_metrics(connection, columns, errors, checks, db_path)
    metric_columns = columns.get("metrics", set())
    dimension_column = BASE._pick(
        metric_columns,
        "metric_dimension",
        "dimension",
        "stage",
    )
    if dimension_column:
        supplied_dimensions = {
            str(row[0]).strip().casefold()
            for row in connection.execute(
                f'SELECT DISTINCT "{dimension_column}" FROM metrics '
                f'WHERE "{dimension_column}" IS NOT NULL'
            )
        }
        allowed_dimensions = {
            "perception",
            "semantics",
            "policy",
            "run_summary",
            *REAL_DEVICE_AUXILIARY_METRIC_DIMENSIONS,
        }
        if supplied_dimensions <= allowed_dimensions:
            errors[metric_error_start:] = [
                finding
                for finding in errors[metric_error_start:]
                if finding.get("code") != "invalid_metric_dimension"
            ]


def _safe_field_component(value: object) -> str:
    """Keep validation locations useful without echoing a sensitive JSON key."""

    text = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", text):
        return "<field>"
    finding = classify_human_text(text, field_name="json_key", path="json.key")
    return "<field>" if finding.metadata_only else text


def _json_scalar_is_structural(field_name: str, path: str) -> bool | None:
    normalized_field = field_name.strip().casefold()
    normalized_path = path.casefold()
    if normalized_field == "value" and re.search(
        r"(?:^|[.:])[a-z0-9_]*metadata\.value(?:\[|$)",
        normalized_path,
    ):
        # Key/value control tables contain run IDs, hashes, policy enums, and
        # version strings. Embedded credentials are still detected by the
        # classifier before its structural exemption is applied.
        return True
    if (
        normalized_field in JSON_STRUCTURAL_FIELDS
        or normalized_field == "sha256"
        or normalized_field.endswith("_ms")
        or normalized_field.endswith("_sha256")
    ):
        return True
    if any(
        marker in normalized_path
        for marker in (
            ".inventory_snapshot.",
            ".inventory_packages[",
            ".selected_packages[",
            ".app_statuses[",
            ".version_candidates[",
            ".auto_action_guard.",
        )
    ):
        return True
    # ``None`` lets the shared classifier apply its own structural field/path
    # registry. Passing False would incorrectly force generated IDs through
    # phone/payment-card/resident-ID regexes.
    return None


def _iter_json_scalars(
    value: Any,
    *,
    path: str,
    field_name: str = "",
) -> Iterable[tuple[str, str, object]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            safe_key = _safe_field_component(key)
            child_path = f"{path}.{safe_key}" if path else safe_key
            yield from _iter_json_scalars(
                child,
                path=child_path,
                field_name=str(key),
            )
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            yield from _iter_json_scalars(
                child,
                path=f"{path}[{index}]",
                field_name=field_name,
            )
        return
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        yield field_name, path, value


def _iter_file_privacy_values(path: Path) -> Iterable[tuple[str, str, object, bool | None]]:
    suffix = path.suffix.casefold()
    if suffix == ".jsonl":
        try:
            with path.open("r", encoding="utf-8", errors="replace") as source:
                for line_number, raw_line in enumerate(source, 1):
                    if not raw_line.strip():
                        continue
                    try:
                        value = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    for field_name, value_path, scalar in _iter_json_scalars(
                        value,
                        path=f"line[{line_number}]",
                    ):
                        yield (
                            field_name,
                            value_path,
                            scalar,
                            _json_scalar_is_structural(field_name, value_path),
                        )
        except OSError:
            return
        return
    if suffix == ".json":
        try:
            value = _load_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return
        for field_name, value_path, scalar in _iter_json_scalars(value, path="json"):
            yield (
                field_name,
                value_path,
                scalar,
                _json_scalar_is_structural(field_name, value_path),
            )
        return
    if suffix == ".xml":
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            return
        for index, element in enumerate(root.iter()):
            if element.text and element.text.strip():
                yield "text", f"xml[{index}].text", element.text, False
            for key, value in element.attrib.items():
                if not value:
                    continue
                structural = key in XML_STRUCTURAL_ATTRIBUTES or key not in XML_HUMAN_ATTRIBUTES
                yield key, f"xml[{index}].{_safe_field_component(key)}", value, structural
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if suffix in {".csv", ".tsv"}:
        for location, value in BASE._iter_delimited_human_content(path):
            yield "human_content", location, value, False
    elif text:
        yield "document_text", "document", text, False


def _iter_sqlite_privacy_values(
    connection: sqlite3.Connection,
) -> Iterable[tuple[str, str, object, bool | None]]:
    for table in sorted(BASE._sqlite_tables(connection)):
        safe_table = _safe_field_component(table)
        for column in BASE._text_columns(connection, table):
            safe_column = _safe_field_component(column)
            query = f'SELECT rowid, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
            try:
                rows = connection.execute(query)
                row_mode = "rowid"
            except sqlite3.OperationalError:
                rows = connection.execute(f'SELECT "{column}" FROM "{table}"')
                row_mode = "index"
            for index, row in enumerate(rows):
                row_identifier, value = (row[0], row[1]) if row_mode == "rowid" else (index, row[0])
                if not isinstance(value, str) or not value:
                    continue
                location = f"{safe_table}.{safe_column}[{row_mode}={row_identifier}]"
                if (
                    column.endswith("_json")
                    or column in BASE.JSON_CONTAINER_COLUMNS
                    or value.lstrip().startswith(("{", "["))
                ):
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError:
                        yield column, location, value, None
                        continue
                    for field_name, value_path, scalar in _iter_json_scalars(
                        decoded,
                        path=location,
                        field_name=column,
                    ):
                        yield (
                            field_name,
                            value_path,
                            scalar,
                            _json_scalar_is_structural(field_name, value_path),
                        )
                else:
                    yield (
                        column,
                        location,
                        value,
                        _json_scalar_is_structural(column, location),
                    )


def _validate_shared_privacy_classifier(
    run_dir: Path,
    connection: sqlite3.Connection,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    """Scan persisted human content with the same classifier as collection.

    Findings contain category and structural location only.  The matched value
    is never retained in the report or printed by the CLI.
    """

    findings: set[tuple[str, str]] = set()
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in PRIVACY_TEXT_SUFFIXES:
            continue
        relative = path.relative_to(run_dir).as_posix()
        try:
            raw_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            errors.append(_finding("evidence_read_error", str(error), str(path)))
            continue
        # Keep the established secret detector as an independent, whole-file
        # gate.  Integrating the shared classifier must never weaken it.
        if BASE._secret_matches(raw_text):
            findings.add((relative, "secret"))
        for field_name, value_path, value, structural in _iter_file_privacy_values(path):
            finding = classify_human_text(
                value,
                field_name=field_name,
                path=value_path,
                structural=structural,
            )
            for category in finding.categories:
                findings.add((f"{relative}:{value_path}", category))

    def scan_database(database: sqlite3.Connection, database_label: str) -> None:
        for field_name, value_path, value, structural in _iter_sqlite_privacy_values(database):
            finding = classify_human_text(
                value,
                field_name=field_name,
                path=value_path,
                structural=structural,
            )
            for category in finding.categories:
                findings.add((f"{database_label}:{value_path}", category))
            # Preserve the legacy whole-value secret gate for non-JSON columns.
            if isinstance(value, str) and BASE._secret_matches(value):
                findings.add((f"{database_label}:{value_path}", "secret"))

    scan_database(connection, "corpus.sqlite")
    corpus_path = (run_dir / "corpus.sqlite").resolve()
    for database_path in sorted(run_dir.rglob("*.sqlite")):
        if database_path.resolve() == corpus_path:
            continue
        relative = database_path.relative_to(run_dir).as_posix()
        try:
            database = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
            try:
                scan_database(database, relative)
            finally:
                database.close()
        except sqlite3.Error as error:
            errors.append(_finding("privacy_sqlite_error", str(error), relative))

    ordered = sorted(findings)
    category_counts: dict[str, int] = {}
    for _, category in ordered:
        category_counts[category] = category_counts.get(category, 0) + 1
    checks["sensitive_data_findings"] = len(ordered)
    checks["sensitive_data_categories"] = category_counts
    for location, category in ordered[:100]:
        errors.append(
            _finding(
                "sensitive_data_detected",
                f"persisted corpus contains sensitive category: {category}",
                location,
            )
        )
    if len(ordered) > 100:
        errors.append(
            _finding(
                "sensitive_data_detected",
                f"{len(ordered) - 100} additional sensitive findings suppressed",
                str(run_dir),
            )
        )


def _validate_evidence(
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    run_dir: Path,
    repo_root: Path,
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    run_resolved = run_dir.resolve()
    evidence_paths: set[Path] = set()
    if "screens" in columns:
        screen_columns = columns["screens"]
        for column in ("screenshot_path", "accessibility_tree_path", "ui_tree_path"):
            if column not in screen_columns:
                continue
            for (value,) in connection.execute(f'SELECT "{column}" FROM screens WHERE "{column}" IS NOT NULL AND TRIM("{column}")<>\'\''):
                raw = str(value)
                candidate = Path(raw)
                resolved = candidate.resolve() if candidate.is_absolute() else (run_dir / candidate).resolve()
                try:
                    resolved.relative_to(run_resolved)
                except ValueError:
                    errors.append(_finding("evidence_path_escape", f"evidence escapes run: {raw}", str(run_dir)))
                    continue
                evidence_paths.add(resolved)
                if not resolved.is_file():
                    errors.append(_finding("missing_evidence", f"missing evidence: {raw}", str(run_dir)))
                tokens = {token for token in re.split(r"[^a-z0-9]+", resolved.as_posix().casefold()) if token}
                if resolved.suffix.casefold() in RAW_ARTIFACT_SUFFIXES and tokens & RAW_PATH_MARKERS:
                    errors.append(_finding("raw_artifact_forbidden", f"raw/unredacted artifact is forbidden: {raw}", str(run_dir)))

        path_columns = [
            column
            for column in ("screenshot_path", "accessibility_tree_path", "ui_tree_path")
            if column in screen_columns
        ]
        evidence_mode_column = BASE._pick(screen_columns, "evidence_mode")
        privacy_column = BASE._pick(screen_columns, "privacy_verified")
        if path_columns:
            select_columns = ["screen_id", *path_columns]
            if evidence_mode_column:
                select_columns.append(evidence_mode_column)
            if privacy_column:
                select_columns.append(privacy_column)
            for row in connection.execute(
                "SELECT " + ",".join(f'"{column}"' for column in select_columns) + " FROM screens"
            ):
                values = dict(zip(select_columns, row))
                for column in path_columns:
                    raw = str(values.get(column) or "").strip()
                    if not raw or Path(raw).suffix.casefold() not in RAW_ARTIFACT_SUFFIXES:
                        continue
                    basename_tokens = {
                        token
                        for token in re.split(r"[^a-z0-9]+", Path(raw).name.casefold())
                        if token
                    }
                    derivative_attested = bool(
                        basename_tokens & {"redacted", "masked", "sanitized"}
                        and evidence_mode_column
                        and str(values.get(evidence_mode_column, "")).casefold()
                        in {"verified_evidence", "verified_redacted", "redacted"}
                        and privacy_column
                        and _as_bool(values.get(privacy_column))
                    )
                    if not derivative_attested:
                        errors.append(
                            _finding(
                                "unattested_binary_or_xml_evidence",
                                f"screen {values.get('screen_id')} {column} is not an attested redacted derivative",
                                str(run_dir),
                            )
                        )

    tracked: set[str] = set()
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=True,
            capture_output=True,
            timeout=15,
        )
        tracked = {item.decode("utf-8", errors="replace").replace("\\", "/") for item in result.stdout.split(b"\0") if item}
    except (OSError, subprocess.SubprocessError):
        checks["git_tracking_check"] = "unavailable"
    tracked_evidence: list[str] = []
    for evidence in evidence_paths:
        try:
            relative = evidence.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            continue
        if relative in tracked:
            tracked_evidence.append(relative)
    checks["tracked_evidence"] = tracked_evidence
    if tracked_evidence:
        errors.append(_finding("evidence_tracked_by_git", f"evidence must not be committed: {tracked_evidence}", str(repo_root)))

    for path in run_dir.rglob("*"):
        if not path.is_file():
            continue
        tokens = {token for token in re.split(r"[^a-z0-9]+", path.as_posix().casefold()) if token}
        if path.suffix.casefold() in RAW_ARTIFACT_SUFFIXES and tokens & RAW_PATH_MARKERS:
            errors.append(_finding("raw_artifact_forbidden", f"raw/unredacted artifact is forbidden: {path.name}", str(path)))

    _validate_shared_privacy_classifier(run_dir, connection, errors, checks)


def _validate_resume(
    run_dir: Path,
    connection: sqlite3.Connection,
    columns: Mapping[str, set[str]],
    manifest: Mapping[str, Any],
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    checkpoint_path = run_dir / "checkpoint.json"
    observations_path = run_dir / "observations.jsonl"
    if not checkpoint_path.is_file():
        errors.append(_finding("checkpoint_missing", "checkpoint.json is required for resumability", str(checkpoint_path)))
        return
    try:
        checkpoint = _load_json(checkpoint_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        errors.append(_finding("checkpoint_parse_error", str(error), str(checkpoint_path)))
        return
    if not isinstance(checkpoint, Mapping):
        errors.append(_finding("checkpoint_shape", "checkpoint must be an object", str(checkpoint_path)))
        return

    expected_checkpoint = {
        "run_id": profile.get("run_id"),
        "provenance": EXPECTED_PROVENANCE,
        "dataset_role": EXPECTED_PROVENANCE,
        "review_status": EXPECTED_REVIEW_STATUS,
        "review_lifecycle": "candidate",
        "canonical_catalog_version": BASE.EXPECTED_CATALOG_VERSION,
        "canonical_catalog_sha256": BASE.EXPECTED_CATALOG_SHA256,
        "canonical_equivalence_sha256": BASE.EXPECTED_EQUIVALENCE_SHA256,
    }
    for field, expected in expected_checkpoint.items():
        if checkpoint.get(field) != expected:
            errors.append(_finding("checkpoint_governance_mismatch", f"checkpoint.{field} must be {expected!r}", str(checkpoint_path)))
    if str(checkpoint.get("route_lifecycle", "")) not in ALLOWED_LIFECYCLES:
        errors.append(_finding("checkpoint_governance_mismatch", "checkpoint lifecycle must be shadow/candidate", str(checkpoint_path)))
    if checkpoint.get("canonical_mutation_allowed") is not False:
        errors.append(_finding("checkpoint_canonical_mutation", "checkpoint cannot allow canonical mutation", str(checkpoint_path)))

    records = _parse_jsonl(observations_path, errors)
    if not observations_path.is_file():
        errors.append(_finding("observations_missing", "observations.jsonl is required", str(observations_path)))
    event_columns = columns.get("event_log", set())
    if not event_columns:
        return
    id_col = BASE._pick(event_columns, "event_id")
    seq_col = BASE._pick(event_columns, "sequence", "sequence_no", "seq")
    payload_col = BASE._pick(event_columns, "payload_json", "payload")
    content_col = BASE._pick(event_columns, "content_sha256", "payload_sha256")
    event_hash_col = BASE._pick(event_columns, "event_sha256")
    envelope_col = BASE._pick(event_columns, "envelope_json", "event_json")
    if not all((id_col, seq_col, payload_col, content_col, event_hash_col)):
        return
    selected = [id_col, seq_col, payload_col, content_col, event_hash_col]
    if envelope_col:
        selected.append(envelope_col)
    db_rows = connection.execute(
        "SELECT " + ",".join(f'"{column}"' for column in selected) + f' FROM event_log ORDER BY "{seq_col}"'
    ).fetchall()
    db_events = [dict(zip(selected, row)) for row in db_rows]
    sequences = [int(item[seq_col]) for item in db_events]
    expected_sequences = list(range(1, len(db_events) + 1))
    if sequences != expected_sequences:
        errors.append(_finding("resume_sequence_gap", f"event sequence must be contiguous from 1; got {sequences}", str(run_dir / "corpus.sqlite")))
    ids = [str(item[id_col]) for item in db_events]
    if len(ids) != len(set(ids)):
        errors.append(_finding("resume_duplicate_event", "event IDs must be unique", str(run_dir / "corpus.sqlite")))

    for row in db_events:
        try:
            payload = json.loads(str(row[payload_col])) if isinstance(row[payload_col], str) else row[payload_col]
        except json.JSONDecodeError:
            errors.append(_finding("event_payload_parse", f"invalid payload for {row[id_col]}", str(run_dir / "corpus.sqlite")))
            continue
        expected_content = _json_hash(payload)
        if str(row[content_col]) != expected_content:
            errors.append(_finding("content_hash_mismatch", f"event {row[id_col]} payload hash mismatch", str(run_dir / "corpus.sqlite")))
        if envelope_col and row.get(envelope_col):
            try:
                envelope = json.loads(str(row[envelope_col]))
            except json.JSONDecodeError:
                errors.append(_finding("event_envelope_parse", f"invalid envelope for {row[id_col]}", str(run_dir / "corpus.sqlite")))
                continue
            if isinstance(envelope, Mapping):
                hash_input = {key: value for key, value in envelope.items() if key != "event_sha256"}
                if str(row[event_hash_col]) != _json_hash(hash_input):
                    errors.append(_finding("event_hash_mismatch", f"event {row[id_col]} envelope hash mismatch", str(run_dir / "corpus.sqlite")))

    jsonl_ids = [str(record.get("event_id", "")) for record in records]
    jsonl_sequences = [record.get("sequence", record.get("sequence_no", record.get("seq"))) for record in records]
    if jsonl_ids != ids or jsonl_sequences != sequences:
        errors.append(_finding("observation_log_divergence", "observations.jsonl does not match SQLite event_log order/IDs", str(observations_path)))
    for index, record in enumerate(records):
        if index >= len(db_events):
            break
        if record.get("content_sha256") != db_events[index][content_col] or record.get("event_sha256") != db_events[index][event_hash_col]:
            errors.append(_finding("observation_log_hash_divergence", f"JSONL event {index + 1} hashes differ from SQLite", str(observations_path)))

    expected_count = len(db_events)
    if checkpoint.get("event_count") != expected_count:
        errors.append(_finding("checkpoint_event_count", f"checkpoint event_count must be {expected_count}", str(checkpoint_path)))
    expected_last_sequence = sequences[-1] if sequences else 0
    expected_last_id = ids[-1] if ids else None
    if checkpoint.get("last_sequence") != expected_last_sequence:
        errors.append(_finding("checkpoint_last_sequence", f"checkpoint last_sequence must be {expected_last_sequence}", str(checkpoint_path)))
    if checkpoint.get("last_event_id") != expected_last_id:
        errors.append(_finding("checkpoint_last_event_id", f"checkpoint last_event_id must be {expected_last_id!r}", str(checkpoint_path)))
    artifact_hashes = checkpoint.get("artifact_sha256", {})
    if not isinstance(artifact_hashes, Mapping):
        artifact_hashes = {}
    manifest_hashes = manifest.get("artifact_sha256", {})
    if not isinstance(manifest_hashes, Mapping):
        manifest_hashes = {}
    if dict(artifact_hashes) != dict(manifest_hashes):
        errors.append(
            _finding(
                "control_artifact_hash_mismatch",
                "manifest and checkpoint artifact_sha256 maps must be identical",
                str(checkpoint_path),
            )
        )
    declared_hash = checkpoint.get("observations_sha256", artifact_hashes.get("observations.jsonl"))
    if declared_hash != (_sha256(observations_path) if observations_path.is_file() else None):
        errors.append(_finding("checkpoint_artifact_hash", "checkpoint observations_sha256 mismatch", str(checkpoint_path)))
    for filename in ("corpus.sqlite", "graph-candidate.sqlite"):
        artifact_path = run_dir / filename
        if filename in artifact_hashes and artifact_path.is_file() and artifact_hashes[filename] != _sha256(artifact_path):
            errors.append(_finding("checkpoint_artifact_hash", f"checkpoint hash mismatch for {filename}", str(checkpoint_path)))
    if checkpoint.get("status") != manifest.get("status"):
        errors.append(_finding("checkpoint_status_mismatch", "checkpoint status differs from manifest", str(checkpoint_path)))
    if checkpoint.get("app_statuses") != manifest.get("app_statuses"):
        errors.append(_finding("checkpoint_app_status_mismatch", "checkpoint app_statuses differ from manifest", str(checkpoint_path)))
    for field in (
        "validation_profile",
        "selected_packages",
        "inventory_packages",
        "inventory_snapshot",
        "runtime_attestation",
        "exploration_stage",
        "goal_candidate_plan",
        "safety",
    ):
        checkpoint_value = checkpoint.get(field, "full_cohort" if field == "validation_profile" else [])
        manifest_value = manifest.get(field, "full_cohort" if field == "validation_profile" else [])
        if checkpoint_value != manifest_value:
            errors.append(
                _finding(
                    "checkpoint_selection_mismatch",
                    f"checkpoint {field} differs from manifest",
                    str(checkpoint_path),
                )
            )

    state = checkpoint.get("state")
    if not isinstance(state, Mapping):
        errors.append(
            _finding(
                "checkpoint_state_invalid",
                "checkpoint state must be an object",
                str(checkpoint_path),
            )
        )
        return
    selected_tasks = [dict(task) for task in profile.get("selected_tasks", [])]
    task_by_id = {str(task.get("task_id") or ""): task for task in selected_tasks}
    current_task_id = state.get("current_task_id")
    current_task = state.get("current_task")
    if current_task_id is None:
        if current_task is not None:
            errors.append(
                _finding(
                    "checkpoint_current_task_mismatch",
                    "current_task must be null when current_task_id is null",
                    str(checkpoint_path),
                )
            )
    else:
        expected_task = task_by_id.get(str(current_task_id))
        comparable_fields = tuple(
            key for key in expected_task or {} if key != "task_id"
        )
        if (
            expected_task is None
            or not isinstance(current_task, Mapping)
            or any(current_task.get(key) != expected_task.get(key) for key in comparable_fields)
        ):
            errors.append(
                _finding(
                    "checkpoint_current_task_mismatch",
                    "current task must exactly match one selected manifest task",
                    str(checkpoint_path),
                )
            )

    completed_ids = state.get("completed_task_ids") or []
    statuses = state.get("statuses") or {}
    attempts = state.get("task_attempt_numbers") or {}
    if (
        not isinstance(completed_ids, list)
        or len(completed_ids) != len(set(completed_ids))
        or not set(completed_ids).issubset(task_by_id)
        or not isinstance(statuses, Mapping)
        or not set(str(key) for key in statuses).issubset(task_by_id)
        or not isinstance(attempts, Mapping)
        or not set(str(key) for key in attempts).issubset(task_by_id)
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in attempts.values()
        )
    ):
        errors.append(
            _finding(
                "checkpoint_task_attempt_lineage_invalid",
                "checkpoint task IDs, statuses, and attempt counters must be selected-task bound",
                str(checkpoint_path),
            )
        )
    summary_attempts: dict[str, list[int]] = {}
    summary_statuses: dict[str, dict[int, str]] = {}
    for metric in _typed_payloads(connection, "metrics"):
        if metric.get("metric_dimension") != "task_summary":
            continue
        task_id = str(metric.get("task_id") or "")
        attempt = metric.get("attempt_number")
        if isinstance(attempt, int) and not isinstance(attempt, bool):
            summary_attempts.setdefault(task_id, []).append(attempt)
            summary_statuses.setdefault(task_id, {})[attempt] = str(
                metric.get("terminal_status") or ""
            )
    for task_id, values in summary_attempts.items():
        checkpoint_attempt = attempts.get(task_id) if isinstance(attempts, Mapping) else None
        if (
            not isinstance(checkpoint_attempt, int)
            or checkpoint_attempt < max(values)
            or (task_id in completed_ids and checkpoint_attempt != max(values))
        ):
            errors.append(
                _finding(
                    "checkpoint_task_attempt_lineage_invalid",
                    f"task {task_id!r} checkpoint attempt does not cover terminal summaries",
                    str(checkpoint_path),
                )
            )
    for task_id in completed_ids if isinstance(completed_ids, list) else []:
        attempt = attempts.get(task_id) if isinstance(attempts, Mapping) else None
        terminal_status = (
            summary_statuses.get(task_id, {}).get(attempt)
            if isinstance(attempt, int)
            else None
        )
        if terminal_status is None or statuses.get(task_id) != terminal_status:
            errors.append(
                _finding(
                    "checkpoint_task_status_mismatch",
                    f"completed task {task_id!r} status differs from its final attempt summary",
                    str(checkpoint_path),
                )
            )
    if profile.get("completed") and profile.get("exploration_stage") in {
        EXPLORATION_STAGE_NEUTRAL_DISCOVERY,
        EXPLORATION_STAGE_GOAL_DIRECTED,
    }:
        if set(completed_ids) != set(task_by_id) or set(statuses) != set(task_by_id):
            errors.append(
                _finding(
                    "checkpoint_completed_task_mismatch",
                    "completed staged run must checkpoint every selected task and status",
                    str(checkpoint_path),
                )
            )

    pending = state.get("pending_action")
    if pending is not None:
        valid_pending = isinstance(pending, Mapping)
        guard = pending.get("auto_action_guard") if isinstance(pending, Mapping) else None
        action_type = str(pending.get("action_type") or "") if isinstance(pending, Mapping) else ""
        reconstructed: AutoActionGuardDecision | None = None
        if isinstance(guard, Mapping):
            try:
                reconstructed = AutoActionGuardDecision(
                    action_type=str(guard.get("action_type") or ""),
                    allowed=guard.get("allowed") is True,
                    computed_final_or_consequential=(
                        guard.get("computed_final_or_consequential") is True
                    ),
                    safe_menu_match=guard.get("safe_menu_match") is True,
                    reason=str(guard.get("reason") or ""),
                )
            except (TypeError, ValueError):
                reconstructed = None
        valid_pending = bool(
            valid_pending
            and current_task_id in task_by_id
            and action_type in {"click", "scroll_forward", "back"}
            and reconstructed is not None
            and reconstructed.action_type == action_type
            and reconstructed.allowed
            and not reconstructed.computed_final_or_consequential
            and guard_evidence_matches(guard, reconstructed)
            and not profile.get("completed")
        )
        if not valid_pending:
            errors.append(
                _finding(
                    "checkpoint_pending_action_invalid",
                    "pending action must retain an allowed non-final guard and current task",
                    str(checkpoint_path),
                )
            )

    boundary_transitions = 0
    for transition in _typed_payloads(connection, "transitions"):
        outcome = str(transition.get("outcome") or "")
        resumed = transition.get("resumed_after_process_boundary") is True
        if outcome == "unknown_after_process_boundary" or resumed:
            boundary_transitions += 1
            guard = transition.get("auto_action_guard")
            if (
                outcome != "unknown_after_process_boundary"
                or not resumed
                or transition.get("success") is not False
                or transition.get("auto_executed") is not True
                or not str(transition.get("source_screen_id") or "")
                or not str(transition.get("target_screen_id") or "")
                or not isinstance(guard, Mapping)
                or guard.get("allowed") is not True
                or guard.get("computed_final_or_consequential") is not False
            ):
                errors.append(
                    _finding(
                        "process_boundary_transition_invalid",
                        "resumed pending input must close once as an unsuccessful unknown transition",
                        str(db_path),
                    )
                )
    checks["process_boundary_unknown_transition_count"] = boundary_transitions


def _known_ids(connection: sqlite3.Connection) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for table, column in (
        ("apps", "app_package"), ("screens", "screen_id"), ("elements", "element_id"),
        ("transitions", "transition_id"), ("goals", "goal_id"), ("failures", "failure_id"),
        ("metrics", "metric_id"), ("event_log", "event_id"),
    ):
        if table in BASE._sqlite_tables(connection) and column in BASE._columns(connection, table):
            result[column] = {str(row[0]) for row in connection.execute(f'SELECT "{column}" FROM "{table}"')}
    return result


def _validate_jsonl_references(
    run_dir: Path,
    known: Mapping[str, set[str]],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    file_to_id = {
        "elements.jsonl": "element_id", "transitions.jsonl": "transition_id",
        "failures.jsonl": "failure_id", "metrics.jsonl": "metric_id",
    }
    for filename, identifier in file_to_id.items():
        path = run_dir / filename
        if not path.is_file():
            continue
        records = _parse_jsonl(path, errors)
        invalid = [str(item.get(identifier, "")) for item in records if str(item.get(identifier, "")) not in known.get(identifier, set())]
        checks[f"{filename}_records"] = len(records)
        if invalid:
            errors.append(_finding("jsonl_referential_integrity", f"{filename} unknown {identifier}: {invalid}", str(path)))


def _validate_graph(
    run_dir: Path,
    connection: sqlite3.Connection,
    profile: Mapping[str, Any],
    errors: list[dict[str, str]],
    checks: dict[str, Any],
) -> None:
    graph_path = run_dir / "graph-candidate.sqlite"
    graph_jsonl_path = run_dir / "graph-candidate.jsonl"
    if not graph_path.is_file():
        checks["graph_candidate_present"] = False
        if (
            profile.get("partial_research")
            or profile.get("dynamic_inventory")
            or (profile.get("completed") and profile.get("installed_packages"))
        ):
            errors.append(_finding("graph_candidate_missing", "completed exploration requires graph-candidate.sqlite", str(graph_path)))
        if graph_jsonl_path.is_file():
            errors.append(_finding("graph_pair_incomplete", "graph JSONL exists without SQLite", str(graph_jsonl_path)))
        return
    checks["graph_candidate_present"] = True
    try:
        graph = sqlite3.connect(f"file:{graph_path.as_posix()}?mode=ro", uri=True)
        try:
            fk = list(graph.execute("PRAGMA foreign_key_check"))
            if fk:
                errors.append(_finding("graph_foreign_key_violation", f"graph has {len(fk)} FK violations", str(graph_path)))
            tables = BASE._sqlite_tables(graph)
            if profile.get("partial_research") or profile.get("dynamic_inventory"):
                graph_required_tables = {
                    "universal_apps",
                    "universal_screens",
                    "universal_actions",
                }
                missing_graph_tables = sorted(graph_required_tables - tables)
                if missing_graph_tables:
                    errors.append(
                        _finding(
                            "partial_graph_schema_missing",
                            f"partial_research graph lacks tables: {missing_graph_tables}",
                            str(graph_path),
                        )
                    )
                else:
                    graph_packages = {
                        str(row[0])
                        for row in graph.execute("SELECT DISTINCT app_package FROM universal_apps")
                    }
                    selected_packages = set(profile.get("selected_packages", set()))
                    unexpected = sorted(graph_packages - selected_packages)
                    if unexpected:
                        errors.append(
                            _finding(
                                "partial_graph_unselected_app",
                                f"partial graph contains unselected packages: {unexpected}",
                                str(graph_path),
                            )
                        )
                    latest_task_attempts: dict[str, tuple[int, str, str]] = {}
                    for metric in _typed_payloads(connection, "metrics"):
                        if metric.get("metric_dimension") != "task_summary":
                            continue
                        task_id = str(metric.get("task_id") or "")
                        app_package = str(metric.get("app_package") or "")
                        terminal_status = str(metric.get("terminal_status") or "")
                        attempt = metric.get("attempt_number")
                        if (
                            task_id
                            and app_package
                            and terminal_status
                            and isinstance(attempt, int)
                            and not isinstance(attempt, bool)
                        ):
                            previous = latest_task_attempts.get(task_id)
                            if previous is None or attempt >= previous[0]:
                                latest_task_attempts[task_id] = (
                                    attempt,
                                    app_package,
                                    terminal_status,
                                )
                    statuses_by_package: dict[str, list[str]] = defaultdict(list)
                    for _, app_package, terminal_status in latest_task_attempts.values():
                        statuses_by_package[app_package].append(terminal_status)
                    boundary_only_packages = {
                        package
                        for package, package_statuses in statuses_by_package.items()
                        if package_statuses
                        and all(
                            item.startswith(("boundary:", "stopped:"))
                            for item in package_statuses
                        )
                    }
                    checks["graph_boundary_only_packages"] = sorted(
                        boundary_only_packages
                    )
                    graph_evidence: dict[str, dict[str, int]] = {}
                    for package in sorted(selected_packages):
                        row = graph.execute(
                            """
                            SELECT COUNT(DISTINCT s.screen_fingerprint),
                                   COUNT(DISTINCT action.action_id)
                            FROM universal_apps app
                            LEFT JOIN universal_screens s ON s.app_key=app.app_key
                            LEFT JOIN universal_actions action
                              ON action.screen_fingerprint=s.screen_fingerprint
                            WHERE app.app_package=?
                            """,
                            (package,),
                        ).fetchone()
                        screen_count = int(row[0] or 0)
                        action_count = int(row[1] or 0)
                        graph_evidence[package] = {
                            "screens": screen_count,
                            "actions": action_count,
                        }
                        require_actions = (
                            profile.get("exploration_stage")
                            != EXPLORATION_STAGE_NEUTRAL_DISCOVERY
                        )
                        boundary_only_capture = bool(
                            profile.get("capture_only")
                            and package in boundary_only_packages
                        )
                        if not boundary_only_capture and (
                            screen_count == 0
                            or (require_actions and action_count == 0)
                        ):
                            errors.append(
                                _finding(
                                    "selected_package_missing_graph_evidence",
                                    f"selected package {package} graph screens={screen_count}, actions={action_count}",
                                    str(graph_path),
                                )
                            )
                    checks["partial_graph_evidence"] = graph_evidence
                    if profile.get("dynamic_inventory"):
                        excluded = set(profile.get("excluded_packages", set()))
                        if graph_packages & excluded:
                            errors.append(
                                _finding(
                                    "excluded_inventory_package_in_graph",
                                    "excluded inventory packages cannot have graph evidence",
                                    str(graph_path),
                                )
                            )
            route_table = "universal_routes" if "universal_routes" in tables else "routes" if "routes" in tables else ""
            if not route_table:
                errors.append(_finding("graph_routes_missing", "graph must contain routes/universal_routes", str(graph_path)))
                return
            columns = BASE._columns(graph, route_table)
            route_id_col = BASE._pick(columns, "route_id", "id")
            lifecycle_col = BASE._pick(columns, "status", "route_lifecycle", "lifecycle_status")
            if not route_id_col or not lifecycle_col:
                errors.append(_finding("graph_route_columns", "graph routes need ID and lifecycle/status", str(graph_path)))
                return
            rows = graph.execute(f'SELECT "{route_id_col}","{lifecycle_col}"' + (',provisional' if 'provisional' in columns else '') + f' FROM "{route_table}"').fetchall()
            graph_route_ids = {str(row[0]) for row in rows}
            checks["graph_route_count"] = len(rows)
            if profile.get("capture_only") and rows:
                errors.append(
                    _finding(
                        "capture_only_graph_not_empty",
                        "capture-only validation permits a graph schema shell but no candidate routes",
                        str(graph_path),
                    )
                )
            if (
                profile.get("completed")
                and profile.get("installed_packages")
                and profile.get("exploration_stage")
                != EXPLORATION_STAGE_NEUTRAL_DISCOVERY
                and not rows
            ):
                errors.append(_finding("graph_routes_empty", "completed exploration requires candidate routes", str(graph_path)))
            for row in rows:
                lifecycle = str(row[1]).casefold()
                if lifecycle not in ALLOWED_LIFECYCLES or lifecycle in GOLD_WORDS:
                    errors.append(_finding("graph_route_not_candidate", f"route {row[0]} status={row[1]!r}", str(graph_path)))
                if "provisional" in columns and not _as_bool(row[2]):
                    errors.append(_finding("graph_route_not_provisional", f"route {row[0]} must remain provisional", str(graph_path)))
            known_screen_ids = _known_ids(connection).get("screen_id", set())
            for column in ("source_screen_id", "target_screen_id", "screen_id"):
                if column not in columns:
                    continue
                unknown = {str(row[0]) for row in graph.execute(f'SELECT DISTINCT "{column}" FROM "{route_table}" WHERE "{column}" IS NOT NULL AND TRIM("{column}")<>\'\'')} - known_screen_ids
                if unknown:
                    errors.append(_finding("graph_referential_integrity", f"graph unknown {column}: {sorted(unknown)}", str(graph_path)))
            if "app_package" in columns:
                packages = {str(row[0]) for row in graph.execute(f'SELECT DISTINCT app_package FROM "{route_table}"')}
                invalid = packages - set(profile.get("installed_packages", set()))
                if invalid:
                    errors.append(_finding("graph_uninstalled_app", f"graph contains skipped packages: {sorted(invalid)}", str(graph_path)))
            elif "app_key" in columns and "universal_apps" in tables:
                packages = {
                    str(row[0])
                    for row in graph.execute(
                        f'SELECT DISTINCT a.app_package FROM "{route_table}" r '
                        "JOIN universal_apps a ON a.app_key=r.app_key"
                    )
                }
                invalid = packages - set(profile.get("installed_packages", set()))
                if invalid:
                    errors.append(
                        _finding(
                            "graph_uninstalled_app",
                            f"graph contains skipped packages: {sorted(invalid)}",
                            str(graph_path),
                        )
                    )
            if profile.get("exploration_stage") == EXPLORATION_STAGE_GOAL_DIRECTED:
                route_goal_pairs: set[tuple[str, str]] = set()
                if "goal_key" in columns:
                    if "app_package" in columns:
                        route_goal_pairs = {
                            (str(row[0]), str(row[1]))
                            for row in graph.execute(
                                f'SELECT DISTINCT app_package,goal_key FROM "{route_table}"'
                            )
                        }
                    elif "app_key" in columns and "universal_apps" in tables:
                        route_goal_pairs = {
                            (str(row[0]), str(row[1]))
                            for row in graph.execute(
                                f'SELECT DISTINCT a.app_package,r.goal_key FROM "{route_table}" r '
                                "JOIN universal_apps a ON a.app_key=r.app_key"
                            )
                        }
                expected_pairs = {
                    (
                        str(task.get("app_package") or ""),
                        fingerprint_goal(str(task.get("goal_text") or "")),
                    )
                    for task in profile.get("selected_tasks", [])
                }
                unexpected_pairs = route_goal_pairs - expected_pairs
                missing_pairs = expected_pairs - route_goal_pairs
                if unexpected_pairs:
                    errors.append(
                        _finding(
                            "directed_graph_goal_lineage_mismatch",
                            f"graph contains routes for non-selected goals: {sorted(unexpected_pairs)}",
                            str(graph_path),
                        )
                    )
                if profile.get("completed") and missing_pairs:
                    errors.append(
                        _finding(
                            "directed_graph_route_evidence_missing",
                            f"completed directed goals lack shadow routes: {sorted(missing_pairs)}",
                            str(graph_path),
                        )
                    )
                checks["directed_graph_route_evidence"] = {
                    "expected": sorted(expected_pairs),
                    "observed": sorted(route_goal_pairs),
                    "complete": not missing_pairs,
                }
            elif profile.get("exploration_stage") == EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
                checks["neutral_discovery_graph_completion_attested"] = False

            if "real_device_candidate_metadata" not in tables:
                errors.append(
                    _finding(
                        "graph_candidate_metadata_missing",
                        "physical graph requires real_device_candidate_metadata",
                        str(graph_path),
                    )
                )
            else:
                metadata = dict(graph.execute("SELECT key, value FROM real_device_candidate_metadata"))
                expected_metadata = {
                    "run_id": str(profile.get("run_id", "")),
                    "provenance": EXPECTED_PROVENANCE,
                    "dataset_role": EXPECTED_PROVENANCE,
                    "review_status": EXPECTED_REVIEW_STATUS,
                    "review_lifecycle": "candidate",
                    "route_lifecycle": "shadow",
                    "canonical_catalog_version": BASE.EXPECTED_CATALOG_VERSION,
                    "canonical_catalog_sha256": BASE.EXPECTED_CATALOG_SHA256,
                    "canonical_equivalence_sha256": BASE.EXPECTED_EQUIVALENCE_SHA256,
                }
                for key, expected in expected_metadata.items():
                    if str(metadata.get(key, "")) != expected:
                        errors.append(
                            _finding(
                                "graph_metadata_mismatch",
                                f"graph metadata {key} must be {expected!r}",
                                str(graph_path),
                            )
                        )
        finally:
            graph.close()
    except sqlite3.Error as error:
        errors.append(_finding("graph_sqlite_error", str(error), str(graph_path)))
        return

    if not graph_jsonl_path.is_file():
        checks["graph_jsonl_present"] = False
        return
    checks["graph_jsonl_present"] = True
    records = _parse_jsonl(graph_jsonl_path, errors)
    jsonl_ids = {str(item.get("route_id", item.get("id", ""))) for item in records}
    if jsonl_ids != graph_route_ids:
        errors.append(_finding("graph_jsonl_divergence", "graph JSONL route IDs differ from SQLite", str(graph_jsonl_path)))
    for item in records:
        lifecycle = str(item.get("status", item.get("route_lifecycle", ""))).casefold()
        if lifecycle not in ALLOWED_LIFECYCLES:
            errors.append(_finding("graph_route_not_candidate", f"JSONL route status={lifecycle!r}", str(graph_jsonl_path)))


def _validate_git_secret_boundary(
    repo_root: Path, app_manifest_path: Path, errors: list[dict[str, str]], checks: dict[str, Any]
) -> None:
    candidates = [app_manifest_path, Path(__file__).resolve()]
    secret_findings: list[str] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label in BASE._secret_matches(text):
            secret_findings.append(f"{path.name}:{label}")
    checks["git_secret_findings"] = secret_findings
    if secret_findings:
        errors.append(_finding("git_secret_detected", f"secret-like content found in physical validator assets: {secret_findings}", str(repo_root)))


def validate_corpus(
    run_dir: Path | str,
    *,
    repo_root: Path | str = ROOT,
    app_manifest_path: Path | str = DEFAULT_MANIFEST,
    observation_root: Path | str = DEFAULT_OBSERVATION_ROOT,
) -> dict[str, Any]:
    run_dir = Path(run_dir).expanduser().resolve()
    repo_root = Path(repo_root).expanduser().resolve()
    app_manifest_path = Path(app_manifest_path).expanduser().resolve()
    observation_root = Path(observation_root).expanduser().resolve()
    errors: list[dict[str, str]] = []
    checks: dict[str, Any] = {}

    BASE._validate_canonical(repo_root, errors, checks)
    BASE._validate_version_governance(repo_root, errors, checks)
    manifest, profile = _validate_run_manifest(
        run_dir / "manifest.json",
        errors,
        checks,
        observation_root,
        repo_root,
    )
    if not profile.get("dynamic_inventory"):
        _validate_app_manifest(app_manifest_path, errors, checks)
        _validate_git_secret_boundary(repo_root, app_manifest_path, errors, checks)
    else:
        checks["static_app_manifest_not_applied"] = True

    db_path = run_dir / "corpus.sqlite"
    if not db_path.is_file():
        errors.append(_finding("corpus_missing", "corpus.sqlite is required", str(db_path)))
    else:
        try:
            connection = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
            try:
                columns = _validate_schema(connection, errors, checks, db_path)
                _validate_corpus_rows(connection, columns, profile, errors, checks, db_path)
                _validate_goal_and_terminal_lineage(
                    connection, profile, errors, checks, db_path
                )
                _validate_sensitive_local_metrics(
                    connection, profile, errors, checks, db_path
                )
                _validate_safety(connection, columns, manifest, errors, checks, db_path)
                _validate_evidence(connection, columns, run_dir, repo_root, errors, checks)
                _validate_resume(run_dir, connection, columns, manifest, profile, errors, checks)
                _validate_jsonl_references(run_dir, _known_ids(connection), errors, checks)
                _validate_graph(run_dir, connection, profile, errors, checks)
            finally:
                connection.close()
        except sqlite3.Error as error:
            errors.append(_finding("corpus_sqlite_error", str(error), str(db_path)))

    report = {
        "schema_version": 1,
        "validator": "real_device_observation_corpus",
        "run_dir": str(run_dir),
        "ok": not errors,
        "error_count": len(errors),
        "errors": errors,
        "checks": checks,
    }
    return _report_jsonable(report)


def _latest_run(root: Path) -> Path:
    candidates = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
    ) if root.is_dir() else []
    if not candidates:
        raise FileNotFoundError(f"no real-device observation run under {root}")
    return candidates[-1]


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--app-manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--observation-root", type=Path, default=DEFAULT_OBSERVATION_ROOT)
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    run_dir: Path | None = None
    try:
        run_dir = (args.run_dir or _latest_run(args.observation_root)).expanduser().resolve()
        attestation_path = run_dir / VALIDATION_ATTESTATION_FILENAME
        # A previous pass must never survive a new failed/tampered validation.
        attestation_path.unlink(missing_ok=True)
        report = validate_corpus(
            run_dir,
            repo_root=args.repo_root,
            app_manifest_path=args.app_manifest,
            observation_root=args.observation_root,
        )
        if report.get("ok") is True:
            try:
                written = _write_validation_attestation(run_dir, report)
                report.setdefault("checks", {})["validation_attestation"] = {
                    "path": written.name,
                    "sha256": _sha256(written),
                }
            except (OSError, ValueError, TypeError) as error:
                attestation_path.unlink(missing_ok=True)
                report["ok"] = False
                report["error_count"] = int(report.get("error_count", 0)) + 1
                report.setdefault("errors", []).append(
                    _finding(
                        "validation_attestation_write_failed",
                        str(error),
                        str(run_dir),
                    )
                )
    except (OSError, ValueError) as error:
        if run_dir is not None:
            (run_dir / VALIDATION_ATTESTATION_FILENAME).unlink(missing_ok=True)
        report = {
            "schema_version": 1,
            "validator": "real_device_observation_corpus",
            "ok": False,
            "error_count": 1,
            "errors": [_finding("validator_input_error", str(error))],
            "checks": {},
        }
    print(json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
