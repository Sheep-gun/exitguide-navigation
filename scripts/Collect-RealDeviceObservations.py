#!/usr/bin/env python3
"""Safely collect candidate navigation evidence from the designated phone.

This collector is intentionally stricter than the emulator collector:

* only the designated physical device ``R3CY204GDVE`` is accepted;
* app installation, uninstallation, data clearing, and filesystem deletion are
  rejected before an ADB command can run;
* Accessibility/UIAutomator structure is captured before any optional image;
* raw screenshots are never persisted or included in an API request;
* authentication, permission, identity, CAPTCHA, and consequential controls
  are user boundaries; and
* only low-risk menu/settings navigation can be executed automatically.

Evidence is always an unreviewed ``real_device_observation_candidate`` with a
shadow lifecycle. It never mutates or promotes the canonical V15 catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
BASE_COLLECTOR_PATH = REPO_ROOT / "scripts" / "Collect-EmulatorObservations.py"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".artifacts" / "navigation-observations"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8010"
EXPECTED_SERIAL = "R3CY204GDVE"
PROVENANCE = "real_device_observation_candidate"
DATASET_ROLE = PROVENANCE
REVIEW_STATUS = "unreviewed_candidate"
ROUTE_LIFECYCLE = "shadow"
AVD_NAME = "physical_android_device"
COMPLETED_TASK_STATUSES = frozenset(
    {
        "skipped_missing",
        "captured",
        "destination_reached",
        "dry_run_complete",
        "discovery_budget_complete",
        "discovery_frontier_exhausted",
    }
)
EXITGUIDE_PACKAGE = "com.exitguide.ai"
EXITGUIDE_ACCESSIBILITY_COMPONENT = (
    "com.exitguide.ai/com.exitguide.ai.overlay.ExitGuideAccessibilityService"
)
EXITGUIDE_ACCESSIBILITY_COMPONENT_SHORT = (
    "com.exitguide.ai/.overlay.ExitGuideAccessibilityService"
)


def _load_base_collector():
    module_name = "egl_emulator_collector_for_real_device"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, BASE_COLLECTOR_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load base collector: {BASE_COLLECTOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


base = _load_base_collector()

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.real_device_privacy import (  # noqa: E402
    REDACTED,
    classify_human_text,
)
from app.services.real_device_action_safety import (  # noqa: E402
    AutoActionGuardDecision,
    evaluate_auto_action_guard,
    guard_evidence_matches,
    is_final_or_consequential_label,
    is_safe_menu_or_settings_action,
)
from app.services.real_device_goal_task_planner import (  # noqa: E402
    GoalTaskPlan,
    GoalTaskPlanningError,
    PlannedGoal,
    plan_applicable_goals,
)
from app.services.real_device_task_metrics import (  # noqa: E402
    build_task_summary_metric,
)
from app.services.real_device_sensitive_navigation import (  # noqa: E402
    NEUTRAL_DISCOVERY_FAMILY as SENSITIVE_NEUTRAL_DISCOVERY_FAMILY,
    PERSISTED_GUARD_LABEL_BUCKET as SENSITIVE_GUARD_LABEL_BUCKET,
    SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES,
    SensitiveLocalDecision,
    choose_sensitive_local_menu_action,
    classify_sensitive_surface_boundary,
    collect_sensitive_local_goal_signal_evidence,
)

UiElement = base.UiElement
ParsedUiTree = base.ParsedUiTree
ScreenCapture = base.ScreenCapture
ObserveApiClient = base.ObserveApiClient
ObserveApiError = base.ObserveApiError
SafetyDecision = base.SafetyDecision
ExplorationBudget = base.ExplorationBudget
ExplorationState = base.ExplorationState
AdbError = base.AdbError

NEUTRAL_INVENTORY_GOAL = "앱 기능 메뉴 및 설정 진입점 조사"
DYNAMIC_INVENTORY_PROFILE = "dynamic_inventory"
EXPLORATION_STAGE_INITIAL_CAPTURE = "initial_capture"
EXPLORATION_STAGE_NEUTRAL_DISCOVERY = "neutral_menu_discovery"
EXPLORATION_STAGE_GOAL_DIRECTED = "goal_directed_exploration"
DEFAULT_GOAL_FAMILY_MANIFEST = (
    REPO_ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"
)
SNAPSHOT_PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
SNAPSHOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EXPECTED_INVENTORY_CANONICAL = {
    "version": "15.0.0",
    "sha256": "e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24",
    "equivalence_sha256": "197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8",
    "counts": {
        "domains": 179,
        "functions": 2866,
        "terminal_functions": 2660,
        "intents": 2660,
    },
}
SENSITIVE_DYNAMIC_CATEGORIES = frozenset(
    {
        "conversation_message",
        "finance",
        "health_medical",
        "personal_content",
        "real_estate_location",
        "auth_security",
    }
)
SENSITIVE_SAFE_MENU_TERMS = (
    "settings",
    "setting",
    "account settings",
    "privacy settings",
    "subscription settings",
    "설정",
    "계정 설정",
    "개인정보 설정",
    "구독 관리",
    "멤버십 관리",
)
SENSITIVE_CONTENT_SURFACE_TERMS = (
    "message",
    "conversation",
    "chat",
    "timeline",
    "feed",
    "portfolio",
    "balance",
    "transaction",
    "property listing",
    "delivery address",
    "메시지",
    "대화",
    "채팅",
    "피드",
    "잔액",
    "자산",
    "거래내역",
    "매물",
    "배송지",
)


@dataclass(frozen=True)
class CollectionTask:
    app_package: str
    app_name: str
    category: str
    goal_text: str
    sensitivity_categories: tuple[str, ...] = ()
    sensitivity_handling: str = ""
    version_name: str | None = None
    version_code: str | None = None
    version_key: str = ""
    change_status: str = ""
    observation_status: str = ""
    priority_rank: int | None = None
    priority_reason: str = ""
    candidate_id: str = ""
    family_id: str = ""
    terminal_policy: str = ""
    source_run_id: str = ""
    source_inventory_snapshot_id: str = ""
    confidence: float | None = None
    candidate_rank: int | None = None
    source_artifact_sha256: str = ""

    @property
    def task_id(self) -> str:
        identity = asdict(self)
        # Preserve the identity of legacy/static and neutral capture-only tasks.
        # Goal-planning lineage becomes part of the identity only when present.
        for key in (
            "candidate_id",
            "family_id",
            "terminal_policy",
            "source_run_id",
            "source_inventory_snapshot_id",
            "confidence",
            "candidate_rank",
            "source_artifact_sha256",
        ):
            if identity.get(key) in (None, ""):
                identity.pop(key, None)
        return f"task_{stable_hash(identity, 16)}"


class GraphMirrorError(RuntimeError):
    """Raised when run-local graph evidence cannot be mirrored safely."""


@dataclass(frozen=True)
class GraphMirrorResult:
    screen_fingerprint: str
    actions_created: int
    transition_recorded: bool
    recommendation_recorded: bool
    route_recorded: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def clean_text(value: object) -> str:
    return base.clean_text(value)


def normalized(value: object) -> str:
    return base.normalized_label(value)


def stable_hash(value: object, length: int = 20) -> str:
    return base.stable_hash(value, length)


def _snapshot_version_key(version_name: object, version_code: object) -> str:
    name = clean_text(version_name) or "unknown"
    code = clean_text(version_code) or "unknown"
    return f"code:{code}|name:{name}"


def _snapshot_record(record: Mapping[str, object], *, included: bool) -> dict[str, object]:
    package = clean_text(record.get("package"))
    if not SNAPSHOT_PACKAGE_RE.fullmatch(package):
        raise ValueError("inventory snapshot contains an invalid package identifier")
    if record.get("included") is not included:
        raise ValueError("inventory snapshot inclusion flag disagrees with its list")
    version_name = clean_text(record.get("version_name")) or None
    version_code = clean_text(record.get("version_code")) or None
    expected_version_key = _snapshot_version_key(version_name, version_code)
    if clean_text(record.get("version_key")) != expected_version_key:
        raise ValueError("inventory snapshot contains an inconsistent version key")
    raw_categories = record.get("sensitivity_categories")
    if not isinstance(raw_categories, list) or any(
        not isinstance(value, str) or not clean_text(value) for value in raw_categories
    ):
        raise ValueError("inventory snapshot sensitivity categories must be a string list")
    categories = sorted({clean_text(value) for value in raw_categories})
    if len(categories) != len(raw_categories):
        raise ValueError("inventory snapshot sensitivity categories must be unique")
    return {
        "package": package,
        "launchable_activity": clean_text(record.get("launchable_activity")) or None,
        "version_name": version_name,
        "version_code": version_code,
        "version_key": expected_version_key,
        "included": included,
        "decision_reason_code": clean_text(record.get("decision_reason_code")),
        "sensitivity_categories": categories,
        "sensitivity_handling": clean_text(record.get("sensitivity_handling")),
        "change_status": clean_text(record.get("change_status")),
        "observation_status": clean_text(record.get("observation_status")),
    }


def load_dynamic_inventory_snapshot(path: Path | str) -> dict[str, object]:
    source_path = Path(path).expanduser().resolve(strict=True)
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError("--inventory-snapshot must be an explicit regular JSON file")
    payload_bytes = source_path.read_bytes()
    try:
        document = json.loads(payload_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("inventory snapshot is not valid UTF-8 JSON") from error
    if not isinstance(document, Mapping) or document.get("schema_version") != 1:
        raise ValueError("inventory snapshot must be a schema_version=1 object")
    for field, expected in (
        ("provenance", PROVENANCE),
        ("dataset_role", DATASET_ROLE),
        ("review_status", REVIEW_STATUS),
        ("route_lifecycle", ROUTE_LIFECYCLE),
    ):
        if document.get(field) != expected:
            raise ValueError(f"inventory snapshot has invalid {field}")
    if document.get("canonical_catalog_mutation") is not False:
        raise ValueError("inventory snapshot may not mutate V15")
    if document.get("canonical_catalog") != EXPECTED_INVENTORY_CANONICAL:
        raise ValueError("inventory snapshot does not pin the exact frozen V15 catalog")
    snapshot_id = clean_text(document.get("snapshot_id"))
    if not SNAPSHOT_ID_RE.fullmatch(snapshot_id):
        raise ValueError("inventory snapshot_id is missing or unsafe")
    device = document.get("device")
    if not isinstance(device, Mapping):
        raise ValueError("inventory snapshot device attestation is required")
    if (
        clean_text(device.get("serial")) != EXPECTED_SERIAL
        or device.get("is_emulator") is not False
        or clean_text(device.get("device_type"))
        not in {"physical", "physical_android", "physical_device", "android_physical"}
    ):
        raise ValueError("inventory snapshot device attestation is invalid")

    included_raw = document.get("included_apps")
    excluded_raw = document.get("excluded_apps")
    prioritized_raw = document.get("prioritized_apps")
    if not isinstance(included_raw, list) or not included_raw:
        raise ValueError("inventory snapshot requires non-empty included_apps")
    if not isinstance(excluded_raw, list) or not isinstance(prioritized_raw, list):
        raise ValueError("inventory snapshot app inventories must be lists")
    included = [
        _snapshot_record(item, included=True)
        for item in included_raw
        if isinstance(item, Mapping)
    ]
    excluded = [
        _snapshot_record(item, included=False)
        for item in excluded_raw
        if isinstance(item, Mapping)
    ]
    if len(included) != len(included_raw) or len(excluded) != len(excluded_raw):
        raise ValueError("inventory snapshot app records must be objects")
    included_by_package = {str(item["package"]): item for item in included}
    excluded_by_package = {str(item["package"]): item for item in excluded}
    if len(included_by_package) != len(included) or len(excluded_by_package) != len(excluded):
        raise ValueError("inventory snapshot package lists must be unique")
    if set(included_by_package) & set(excluded_by_package):
        raise ValueError("inventory snapshot included/excluded packages overlap")

    priority_records: list[dict[str, object]] = []
    for item in prioritized_raw:
        if not isinstance(item, Mapping):
            raise ValueError("inventory snapshot prioritized_apps must contain objects")
        package = clean_text(item.get("package"))
        rank = item.get("priority_rank")
        if package not in included_by_package or not isinstance(rank, int) or rank < 1:
            raise ValueError("inventory snapshot contains an invalid prioritized app")
        source = included_by_package[package]
        if clean_text(item.get("version_key")) != source["version_key"]:
            raise ValueError("inventory snapshot prioritized app version mismatch")
        priority_records.append(
            {
                "priority_rank": rank,
                "package": package,
                "version_key": source["version_key"],
                "change_status": clean_text(item.get("change_status")),
                "observation_status": clean_text(item.get("observation_status")),
                "priority_reason": clean_text(item.get("priority_reason")),
                "sensitivity_categories": list(source["sensitivity_categories"]),
                "sensitivity_handling": source["sensitivity_handling"],
            }
        )
    priority_packages = [str(item["package"]) for item in priority_records]
    if (
        set(priority_packages) != set(included_by_package)
        or len(priority_packages) != len(set(priority_packages))
        or sorted(int(item["priority_rank"]) for item in priority_records)
        != list(range(1, len(included) + 1))
    ):
        raise ValueError("inventory snapshot priority list must exactly rank included apps")
    priority_records.sort(key=lambda item: (int(item["priority_rank"]), str(item["package"])))

    summary = document.get("summary")
    if not isinstance(summary, Mapping) or (
        summary.get("included_apps") != len(included)
        or summary.get("excluded_apps") != len(excluded)
    ):
        raise ValueError("inventory snapshot summary does not match app lists")
    return {
        "source_path": source_path,
        "sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "snapshot_id": snapshot_id,
        "device": dict(device),
        "included_apps": sorted(included, key=lambda item: str(item["package"])),
        "excluded_apps": sorted(excluded, key=lambda item: str(item["package"])),
        "prioritized_apps": priority_records,
        "discovered_at": clean_text(document.get("discovered_at")),
        "previous_snapshot_id": clean_text(document.get("previous_snapshot_id")) or None,
    }


def dynamic_inventory_tasks(
    snapshot: Mapping[str, object],
    *,
    only_packages: Sequence[str] = (),
    max_apps: int = 0,
) -> list[CollectionTask]:
    included = {
        str(item["package"]): item
        for item in snapshot.get("included_apps", [])
        if isinstance(item, Mapping)
    }
    excluded = {
        str(item["package"])
        for item in snapshot.get("excluded_apps", [])
        if isinstance(item, Mapping)
    }
    requested = {clean_text(value) for value in only_packages if clean_text(value)}
    if requested & excluded:
        raise ValueError("--only-package selects an excluded inventory package")
    unknown = requested - set(included)
    if unknown:
        raise ValueError("--only-package is not present in included inventory")
    tasks: list[CollectionTask] = []
    for priority in snapshot.get("prioritized_apps", []):
        if not isinstance(priority, Mapping):
            continue
        package = str(priority["package"])
        if requested and package not in requested:
            continue
        record = included[package]
        categories = tuple(str(value) for value in record["sensitivity_categories"])
        tasks.append(
            CollectionTask(
                app_package=package,
                app_name=package,
                category=DYNAMIC_INVENTORY_PROFILE,
                goal_text=NEUTRAL_INVENTORY_GOAL,
                sensitivity_categories=categories,
                sensitivity_handling=str(record["sensitivity_handling"]),
                version_name=record["version_name"] if isinstance(record["version_name"], str) else None,
                version_code=record["version_code"] if isinstance(record["version_code"], str) else None,
                version_key=str(record["version_key"]),
                change_status=str(record["change_status"]),
                observation_status=str(record["observation_status"]),
                priority_rank=int(priority["priority_rank"]),
                priority_reason=str(priority["priority_reason"]),
            )
        )
    return tasks[: max_apps or None]


def dynamic_goal_tasks(
    snapshot: Mapping[str, object],
    plan: GoalTaskPlan,
    *,
    only_packages: Sequence[str] = (),
    max_apps: int = 0,
) -> list[CollectionTask]:
    """Join attested applicable goals to apps in inventory-priority order."""

    neutral_tasks = dynamic_inventory_tasks(
        snapshot,
        only_packages=only_packages,
        max_apps=0,
    )
    goals_by_package: dict[str, list[PlannedGoal]] = {}
    for goal in plan.applicable:
        goals_by_package.setdefault(goal.app_package, []).append(goal)
    for goals in goals_by_package.values():
        goals.sort(key=lambda item: (item.rank, item.family_id, item.candidate_id))

    result: list[CollectionTask] = []
    selected_app_count = 0
    for neutral in neutral_tasks:
        planned = goals_by_package.get(neutral.app_package, [])
        if not planned:
            continue
        if max_apps and selected_app_count >= max_apps:
            break
        selected_app_count += 1
        for goal in planned:
            # plan_applicable_goals independently checked the exact package
            # version, sensitivity policy, V15 governance, source hashes, and
            # VALIDATED marker.  Keep all of that lineage in the task itself.
            result.append(
                replace(
                    neutral,
                    goal_text=goal.goal_text,
                    sensitivity_categories=goal.sensitivity_categories,
                    sensitivity_handling=goal.sensitivity_handling,
                    version_name=goal.version_name,
                    version_code=goal.version_code,
                    version_key=goal.version_key,
                    candidate_id=goal.candidate_id,
                    family_id=goal.family_id,
                    terminal_policy=goal.terminal_policy,
                    source_run_id=goal.source_run_id,
                    source_inventory_snapshot_id=goal.source_inventory_snapshot_id,
                    confidence=goal.confidence,
                    candidate_rank=goal.rank,
                    source_artifact_sha256=plan.source_artifact_sha256,
                )
            )
    return result


def _source_path_metadata(path: Path | str, observation_root: Path) -> dict[str, object]:
    source_path = Path(path).expanduser().resolve(strict=True)
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError("goal planning source must be an explicit regular file")
    for root, scope in (
        (observation_root.resolve(), "observation_root_relative"),
        (REPO_ROOT.resolve(), "repo_relative"),
    ):
        try:
            stored_path = source_path.relative_to(root).as_posix()
        except ValueError:
            continue
        return {
            "path": stored_path,
            "path_scope": scope,
            "explicit_safe_file": False,
        }
    return {
        "path": str(source_path),
        "path_scope": "explicit_safe_file",
        "explicit_safe_file": True,
    }


def dynamic_goal_plan_manifest_metadata(
    plan: GoalTaskPlan,
    *,
    artifact_path: Path | str,
    family_manifest_path: Path | str,
    observation_root: Path,
    tasks: Sequence[CollectionTask],
) -> dict[str, object]:
    """Build immutable source/selection lineage retained in manifest metadata."""

    artifact_path = Path(artifact_path).expanduser().resolve(strict=True)
    family_manifest_path = Path(family_manifest_path).expanduser().resolve(strict=True)
    artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    if artifact_sha256 != plan.source_artifact_sha256:
        raise ValueError("goal candidate artifact changed after planning")
    selection = [
        {
            "task_id": task.task_id,
            "app_package": task.app_package,
            "version_key": task.version_key,
            "candidate_id": task.candidate_id,
            "family_id": task.family_id,
            "terminal_policy": task.terminal_policy,
            "source_run_id": task.source_run_id,
            "source_inventory_snapshot_id": task.source_inventory_snapshot_id,
            "confidence": task.confidence,
            "candidate_rank": task.candidate_rank,
            "source_artifact_sha256": task.source_artifact_sha256,
        }
        for task in tasks
    ]
    return {
        "artifact": {
            **_source_path_metadata(artifact_path, observation_root),
            "sha256": artifact_sha256,
        },
        "family_manifest": {
            **_source_path_metadata(family_manifest_path, observation_root),
            "sha256": hashlib.sha256(family_manifest_path.read_bytes()).hexdigest(),
        },
        "source_run_id": plan.source_run_id,
        "source_inventory_snapshot_id": plan.source_inventory_snapshot_id,
        "state_counts": dict(plan.state_counts),
        "selected_candidate_count": len(selection),
        "selected_candidate_ids": [str(item["candidate_id"]) for item in selection],
        "selection_sha256": stable_hash(selection, 64),
        "selection": selection,
    }


def dynamic_inventory_manifest_metadata(
    snapshot: Mapping[str, object],
    *,
    observation_root: Path,
    run_id: str,
    selected_packages: Sequence[str],
) -> dict[str, object]:
    source_path = Path(snapshot["source_path"]).resolve(strict=True)
    root = observation_root.resolve()
    try:
        stored_path = source_path.relative_to(root).as_posix()
        path_scope = "observation_root_relative"
        explicit_safe_file = False
    except ValueError:
        stored_path = str(source_path)
        path_scope = "explicit_safe_file"
        explicit_safe_file = True
    included = [dict(item) for item in snapshot["included_apps"]]
    excluded = [dict(item) for item in snapshot["excluded_apps"]]
    exclusion_counts = Counter(str(item["decision_reason_code"]) for item in excluded)
    version_candidates = [
        {
            "app_package": item["package"],
            "version_name": item["version_name"],
            "version_code": item["version_code"],
            "version_key": item["version_key"],
            "candidate_id": "version_"
            + stable_hash(
                {
                    "run_id": run_id,
                    "app_package": item["package"],
                    "version_name": item["version_name"],
                    "version_code": item["version_code"],
                },
                24,
            ),
        }
        for item in included
    ]
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "path": stored_path,
        "path_scope": path_scope,
        "explicit_safe_file": explicit_safe_file,
        "sha256": snapshot["sha256"],
        "device": dict(snapshot["device"]),
        "discovered_at": snapshot["discovered_at"],
        "previous_snapshot_id": snapshot["previous_snapshot_id"],
        "included_inventory": included,
        "prioritized_apps": [dict(item) for item in snapshot["prioritized_apps"]],
        "exclusions_summary": {
            "excluded_app_count": len(excluded),
            "reason_counts": dict(sorted(exclusion_counts.items())),
            "package_set_sha256": stable_hash(
                sorted(str(item["package"]) for item in excluded), 64
            ),
        },
        "selected_packages": sorted(set(selected_packages)),
        "version_candidates": version_candidates,
    }


RuntimeHealthTransport = Callable[[str, float], Mapping[str, object]]


def _http_health_transport(url: str, timeout: float) -> Mapping[str, object]:
    request = urllib_request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except (urllib_error.URLError, TimeoutError) as error:
        raise ObserveApiError(f"health API unavailable: {error}") from error
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObserveApiError("health API returned invalid JSON") from error
    if not isinstance(payload, Mapping):
        raise ObserveApiError("health API response is not an object")
    return payload


def collect_runtime_attestation(
    adb: "RealDeviceAdbClient",
    *,
    expected_device: Mapping[str, object],
    api_base_url: str,
    health_transport: RuntimeHealthTransport | None = None,
) -> dict[str, object]:
    """Fail closed on the exact physical runtime before creating a run."""

    expected = {
        "serial": clean_text(expected_device.get("serial")),
        "model": clean_text(expected_device.get("model")),
        "android_version": clean_text(expected_device.get("android_version")),
        "locale": clean_text(expected_device.get("locale")),
    }
    if not all(expected.values()) or expected["serial"] != EXPECTED_SERIAL:
        raise AdbError("runtime attestation requires exact snapshot device metadata")
    actual = {
        "serial": clean_text(adb.shell("getprop", "ro.serialno", timeout=10)),
        "model": clean_text(adb.shell("getprop", "ro.product.model", timeout=10)),
        "android_version": clean_text(
            adb.shell("getprop", "ro.build.version.release", timeout=10)
        ),
        "locale": clean_text(adb.locale()),
    }
    mismatches = [key for key in expected if actual[key] != expected[key]]
    if mismatches:
        raise AdbError(
            "runtime device metadata differs from the inventory snapshot: "
            + ",".join(sorted(mismatches))
        )
    if not adb.package_installed(EXITGUIDE_PACKAGE):
        raise AdbError("ExitGuide package is not installed for user 0")
    enabled_raw = adb.shell(
        "settings", "get", "secure", "enabled_accessibility_services", timeout=10
    )
    enabled_components = {
        clean_text(value) for value in enabled_raw.split(":") if clean_text(value)
    }
    if not (
        {
            EXITGUIDE_ACCESSIBILITY_COMPONENT,
            EXITGUIDE_ACCESSIBILITY_COMPONENT_SHORT,
        }
        & enabled_components
    ):
        raise AdbError("ExitGuide accessibility service is not enabled")
    overlay_raw = adb.shell(
        "cmd",
        "appops",
        "get",
        EXITGUIDE_PACKAGE,
        "android:system_alert_window",
        timeout=15,
    )
    if not re.search(
        r"(?:SYSTEM_ALERT_WINDOW|android:system_alert_window)\s*:\s*allow\b",
        overlay_raw,
        flags=re.IGNORECASE,
    ):
        raise AdbError("ExitGuide overlay app-op is not allow")

    parsed = urllib_parse.urlsplit(clean_text(api_base_url).rstrip("/"))
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ObserveApiError("API base URL is not safe for runtime attestation")
    base_path = parsed.path.rstrip("/")
    health_path = f"{base_path}/health" if base_path else "/health"
    health_url = urllib_parse.urlunsplit(
        (parsed.scheme, parsed.netloc, health_path, "", "")
    )
    transport = health_transport or _http_health_transport
    health = transport(health_url, 10.0)
    if clean_text(health.get("status")).casefold() != "ok":
        raise ObserveApiError("API /health did not return status=ok")
    status_path = f"{base_path}/v1/status" if base_path else "/v1/status"
    status_url = urllib_parse.urlunsplit(
        (parsed.scheme, parsed.netloc, status_path, "", "")
    )
    provider_status = transport(status_url, 10.0)
    if (
        clean_text(provider_status.get("status")).casefold() != "ok"
        or clean_text(provider_status.get("llm_provider")).casefold() != "exaone"
        or provider_status.get("provider_ready") is not True
    ):
        raise ObserveApiError(
            "API /v1/status must attest llm_provider=exaone and provider_ready=true"
        )
    return {
        "schema_version": 1,
        "checked_at": utc_now(),
        "device": {
            **actual,
            "device_type": "physical_android",
            "is_emulator": False,
        },
        "exitguide": {
            "package": EXITGUIDE_PACKAGE,
            "installed_for_user_0": True,
            "accessibility_component": EXITGUIDE_ACCESSIBILITY_COMPONENT,
            "accessibility_enabled": True,
            "overlay_appop": "allow",
        },
        "api": {
            "health_path": health_path,
            "status": "ok",
            "provider_status_path": status_path,
            "llm_provider": "exaone",
            "provider_ready": True,
        },
    }


def append_jsonl(path: Path, payload: Mapping[str, object]) -> None:
    base.append_jsonl(path, payload)


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    base.atomic_write_json(path, payload)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    # Keep the temporary filename short. The repository and run-id paths are
    # already long on Windows, and appending the full evidence filename plus a
    # UUID can exceed the legacy MAX_PATH boundary.
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".tmp-{uuid.uuid4().hex[:12]}"
    temporary.write_bytes(payload)
    os.replace(temporary, path)


EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
LONG_ID_RE = re.compile(r"(?<!\d)\d{6,}(?!\d)")

# UIAutomator normally emits ``text`` and ``content-desc``.  OEM and newer
# Accessibility bridges can additionally expose the other names below.  On a
# metadata-only screen every human-facing attribute is removed, rather than
# relying on a short list of PII regular expressions.
HUMAN_ACCESSIBILITY_XML_ATTRIBUTES = frozenset(
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

CAPTCHA_TERMS = (
    "captcha",
    "recaptcha",
    "로봇이 아닙니다",
    "보안 문자",
    "자동입력 방지",
    "사람인지 확인",
    "verify you are human",
)
PERMISSION_TERMS = (
    "권한 허용",
    "앱 사용 중에만",
    "이번만 허용",
    "허용 안 함",
    "allow while using",
    "only this time",
    "don't allow",
    "permission required",
)
AUTH_TERMS = (
    "로그인",
    "회원가입",
    "비밀번호",
    "인증번호",
    "일회용 비밀번호",
    "본인인증",
    "본인 인증",
    "휴대폰 인증",
    "공동인증서",
    "금융인증서",
    "생체인증",
    "생체 인증",
    "지문 인증",
    "얼굴 인증",
    "sign in",
    "log in",
    "sign up",
    "password",
    "passcode",
    "verification code",
    "verify identity",
    "biometric",
    "fingerprint",
    "face recognition",
)
SENSITIVE_CONTEXT_TERMS = (
    "주민등록번호",
    "생년월일",
    "휴대폰 번호",
    "전화번호",
    "이메일 주소",
    "집 주소",
    "배송지",
    "계좌번호",
    "카드번호",
    "보험계약번호",
    "주문번호",
    "내 프로필",
    "내 정보",
    "개인정보",
    "resident registration",
    "date of birth",
    "phone number",
    "email address",
    "shipping address",
    "account number",
    "card number",
)
SAFE_MENU_TERMS = (
    "메뉴",
    "설정",
    "관리",
    "조회",
    "내역",
    "안내",
    "도움말",
    "고객센터",
    "마이페이지",
    "내 페이지",
    "프로필",
    "계정",
    "개인정보",
    "알림",
    "보안",
    "구독",
    "멤버십",
    "더보기",
    "전체",
    "settings",
    "manage",
    "details",
    "history",
    "help",
    "support",
    "profile",
    "account",
    "privacy",
    "notifications",
    "security",
    "subscriptions",
    "membership",
    "more",
    "menu",
)
FEED_TERMS = (
    "for you",
    "following",
    "timeline",
    "news feed",
    "shorts",
    "reels",
    "추천 피드",
    "팔로잉",
    "타임라인",
    "게시물",
    "홈 피드",
)
PRODUCT_LIST_TERMS = (
    "장바구니",
    "상품 목록",
    "추천 상품",
    "구매하기",
    "원 배송",
    "원 무료배송",
    "add to cart",
    "product list",
    "recommended products",
    "shop now",
    "free shipping",
)
SYSTEM_BOUNDARY_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.settings",
    "com.google.android.gms",
    "com.samsung.android.biometrics.app.setting",
}


def validate_serial(serial: str) -> str:
    serial = clean_text(serial)
    if serial.casefold().startswith("emulator-"):
        raise ValueError("emulator serials are forbidden for physical-device collection")
    if serial != EXPECTED_SERIAL:
        raise ValueError(f"physical-device serial must be exactly {EXPECTED_SERIAL}")
    return serial


DESTRUCTIVE_TOP_LEVEL = {
    "install",
    "install-multiple",
    "install-multi-package",
    "uninstall",
    "sync",
}
DESTRUCTIVE_SHELL_SEQUENCES = (
    ("pm", "clear"),
    ("pm", "uninstall"),
    ("pm", "install"),
    ("cmd", "package", "uninstall"),
    ("cmd", "package", "install-existing"),
    ("rm",),
    ("rmdir",),
    ("unlink",),
    ("content", "delete"),
    ("settings", "delete"),
    ("recovery", "--wipe_data"),
)


def assert_non_destructive_adb_args(args: Sequence[str]) -> None:
    lowered = tuple(clean_text(value).casefold() for value in args)
    if not lowered:
        raise AdbError("empty ADB command")
    if lowered[0] in DESTRUCTIVE_TOP_LEVEL:
        raise AdbError(f"forbidden physical-device ADB command: {lowered[0]}")
    shell = lowered[1:] if lowered[0] in {"shell", "exec-out"} else ()
    for sequence in DESTRUCTIVE_SHELL_SEQUENCES:
        if shell[: len(sequence)] == sequence:
            raise AdbError(f"forbidden physical-device shell command: {' '.join(sequence)}")


class RealDeviceAdbClient(base.AdbClient):
    def __init__(
        self,
        executable: str | Path,
        serial: str = EXPECTED_SERIAL,
        *,
        runner: Callable[[Sequence[str], float, bool], bytes] | None = None,
    ) -> None:
        super().__init__(executable, validate_serial(serial), runner=runner)

    def run(self, args: Sequence[str], *, timeout: float = 30.0, binary: bool = False) -> bytes:
        assert_non_destructive_adb_args(args)
        return super().run(args, timeout=timeout, binary=binary)

    def assert_ready(self) -> None:
        super().assert_ready()
        qemu = self.shell("getprop", "ro.kernel.qemu", timeout=10)
        if qemu == "1":
            raise AdbError("the selected device reports ro.kernel.qemu=1")
        serial_property = self.shell("getprop", "ro.serialno", timeout=10)
        if serial_property and serial_property != EXPECTED_SERIAL:
            raise AdbError(f"device serial property mismatch: {serial_property}")

    def package_installed(self, package: str) -> bool:
        # `pm path` exits with code 1 for an absent package on this Samsung
        # Android 16 build. `pm list packages --user 0 <exact>` keeps absence a
        # normal, auditable result and avoids accidentally querying Secure
        # Folder user 150.
        output = self.shell("pm", "list", "packages", "--user", "0", package, timeout=15)
        expected = f"package:{package}"
        return expected in {line.strip() for line in output.splitlines()}

    def launch(self, package: str, *, restart: bool = False) -> None:
        del restart
        if not self.package_installed(package):
            raise AdbError(f"package is not installed on the designated phone: {package}")
        output = self.shell(
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout=30,
        )
        if "No activities found" in output:
            raise AdbError(f"no launchable activity for {package}")

    def app_version_details(self, package: str) -> dict[str, str | None]:
        output = self.shell("dumpsys", "package", package, timeout=20)
        version_name_match = re.search(r"(?m)^\s*versionName=([^\s]+)", output)
        version_code_match = re.search(r"(?m)^\s*versionCode=(\d+)", output)
        return {
            "version_name": (
                clean_text(version_name_match.group(1))[:120]
                if version_name_match
                else None
            ),
            "version_code": version_code_match.group(1) if version_code_match else None,
        }

    def app_version(self, package: str) -> str:
        return clean_text(self.app_version_details(package).get("version_name"))

    def capture_pair(
        self,
        app_directory: Path,
        capture_id: str,
        *,
        screenshot_policy: str = "none",
        force_metadata_only: bool = False,
    ) -> ScreenCapture:
        """Capture Accessibility structure first; never persist a raw image.

        ``force_metadata_only`` is decided from the inventory task *before*
        UIAutomator is read.  This is intentionally earlier than content-based
        privacy classification: a crash between capture and corpus recording
        must not leave a sensitive app's Accessibility strings on disk.
        """

        started = time.perf_counter()
        tree_directory = app_directory / "trees"
        screen_directory = app_directory / "screens"
        tree_directory.mkdir(parents=True, exist_ok=True)
        screen_directory.mkdir(parents=True, exist_ok=True)

        raw_xml: bytes | None = None
        last_dump_error: Exception | None = None
        for attempt in range(3):
            try:
                dump_output = self.exec_out("uiautomator", "dump", "/dev/tty", timeout=35)
                raw_xml = extract_uiautomator_xml(dump_output)
                break
            except (AdbError, ET.ParseError) as error:
                last_dump_error = error
                if attempt < 2:
                    time.sleep(0.45)
        if raw_xml is None:
            raise AdbError(f"UIAutomator hierarchy unavailable after 3 attempts: {last_dump_error}")
        tree = base.parse_ui_xml(raw_xml)
        focus_package, activity = self.current_window()
        package = focus_package or tree.package
        assessment = assess_privacy(tree)

        tree_path = tree_directory / f"{capture_id}.sanitized.xml"
        metadata_only = bool(force_metadata_only or assessment.metadata_only)
        derivative_xml = (
            fully_redact_xml_text(tree.sanitized_xml)
            if metadata_only
            else tree.sanitized_xml
        )
        # Metadata-only means no UI evidence file is retained. The fully
        # redacted bytes are hashed only for local repeat detection and then
        # discarded with the in-memory capture.
        if not metadata_only:
            atomic_write_bytes(tree_path, derivative_xml)
        screenshot_path: Path | None = None
        screenshot_sha256: str | None = None
        if screenshot_policy == "redacted":
            if not metadata_only:
                # The image is captured only after Accessibility parsing. It stays
                # in memory, is redacted in memory, and is never sent to the API.
                raw_png = self.exec_out("screencap", "-p", timeout=25)
                redacted_png = redact_png_in_memory(
                    raw_png, screenshot_redaction_bounds(tree)
                )
                if redacted_png is not None:
                    screenshot_path = screen_directory / f"{capture_id}.png"
                    atomic_write_bytes(screenshot_path, redacted_png)
                    screenshot_sha256 = hashlib.sha256(redacted_png).hexdigest()
        elif screenshot_policy != "none":
            raise ValueError(f"unsupported screenshot policy: {screenshot_policy}")

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return ScreenCapture(
            capture_id=capture_id,
            captured_at=utc_now(),
            package=package,
            activity_name=activity,
            app_version=self.app_version(package) if package else "",
            locale=self.locale(),
            tree=tree,
            tree_path=tree_path,
            screenshot_path=screenshot_path,
            capture_ms=elapsed_ms,
            screenshot_sha256=screenshot_sha256,
            tree_sha256=hashlib.sha256(derivative_xml).hexdigest(),
        )


def extract_uiautomator_xml(output: bytes) -> bytes:
    start = output.find(b"<?xml")
    if start < 0:
        start = output.find(b"<hierarchy")
    end = output.rfind(b"</hierarchy>")
    if start < 0 or end < start:
        raise AdbError("UIAutomator /dev/tty output did not contain a complete hierarchy")
    xml_data = output[start : end + len(b"</hierarchy>")]
    ET.fromstring(xml_data)
    return xml_data


def redact_png_in_memory(
    raw_png: bytes,
    bounds: Sequence[tuple[int, int, int, int]],
) -> bytes | None:
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        return None
    source = io.BytesIO(raw_png)
    destination = io.BytesIO()
    with Image.open(source) as image:
        image.load()
        draw = ImageDraw.Draw(image)
        for left, top, right, bottom in bounds:
            draw.rectangle((left, top, right, bottom), fill=(36, 39, 46))
        image.save(destination, format="PNG", optimize=True)
    return destination.getvalue()


def screenshot_redaction_bounds(tree: ParsedUiTree) -> tuple[tuple[int, int, int, int], ...]:
    """Mask every labelled region so a persisted derivative contains layout only."""

    return tuple(
        element.bounds
        for element in tree.elements
        if element.bounds and (element.text or element.content_description or element.inferred_label)
    )


def fully_redact_xml_text(xml_data: bytes) -> bytes:
    root = ET.fromstring(xml_data)
    for node in root.iter("node"):
        for key in HUMAN_ACCESSIBILITY_XML_ATTRIBUTES:
            if node.attrib.get(key):
                node.attrib[key] = REDACTED
        node.attrib["exitguide-metadata-only"] = "true"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


@dataclass(frozen=True)
class PrivacyAssessment:
    metadata_only: bool
    reasons: tuple[str, ...]
    categories: tuple[str, ...] = ()
    finding_contexts: tuple[str, ...] = ()


def accessibility_human_values(tree: ParsedUiTree) -> tuple[tuple[str, str, object], ...]:
    """Return every human-facing Accessibility value with a stable field path.

    Structural identifiers are deliberately not treated as human text here.
    They are still scanned for embedded secrets by the shared classifier when
    the corpus is validated.
    """

    values: list[tuple[str, str, object]] = []
    for index, element in enumerate(tree.elements):
        prefix = f"elements[{index}]"
        values.extend(
            (
                ("text", f"{prefix}.text", element.text),
                (
                    "content_description",
                    f"{prefix}.content_description",
                    element.content_description,
                ),
                ("inferred_label", f"{prefix}.inferred_label", element.inferred_label),
                # Structural IDs are scanned only for embedded credentials by
                # the shared classifier; numeric ID fragments remain exempt.
                ("resource_id", f"{prefix}.resource_id", element.resource_id),
            )
        )
    # Include OEM/newer Accessibility attributes that the inherited parser
    # does not project onto UiElement.  The XML here is already an in-memory
    # sanitized derivative; it is never persisted for metadata-only screens.
    try:
        root = ET.fromstring(tree.sanitized_xml)
    except ET.ParseError:
        root = None
    if root is not None:
        for index, node in enumerate(root.iter("node")):
            for key in HUMAN_ACCESSIBILITY_XML_ATTRIBUTES:
                value = node.attrib.get(key)
                if value:
                    values.append((key, f"accessibility_xml.nodes[{index}].{key}", value))
    return tuple(values)


def assess_privacy(tree: ParsedUiTree) -> PrivacyAssessment:
    reasons: set[str] = set()
    categories: set[str] = set()
    contexts: set[str] = set()

    for field_name, path, value in accessibility_human_values(tree):
        finding = classify_human_text(value, field_name=field_name, path=path)
        for category in finding.categories:
            categories.add(category)
            contexts.add(f"{path}:{category}")

    for index, element in enumerate(tree.elements):
        prefix = f"elements[{index}]"
        if element.password:
            reasons.add("password_field")
            categories.add("authentication_data")
            contexts.add(f"{prefix}.password:authentication_data")
        if element.role == "text_field":
            # Editable fields can contain values that are not exposed through
            # text/content-desc on every Android build.  Fail closed.
            reasons.add("editable_field")
            contexts.add(f"{prefix}.role:editable_field")
        # ``UiElement.sensitive`` in the inherited parser also considers a
        # resource ID.  Do not let an opaque numeric structural ID become a PII
        # false positive; the human fields above and explicit flags remain the
        # authoritative decision inputs.
        human_value = " ".join(
            value
            for value in (element.text, element.content_description, element.inferred_label)
            if value
        )
        inherited_human_sensitive = bool(
            element.password
            or element.role == "text_field"
            or EMAIL_RE.search(human_value)
            or PHONE_RE.search(human_value)
            or LONG_ID_RE.search(human_value)
        )
        if element.sensitive and inherited_human_sensitive:
            reasons.add("sensitive_element")
            contexts.add(f"{prefix}.sensitive:sensitive_element")

    if categories:
        reasons.add("shared_classifier_sensitive_content")
    return PrivacyAssessment(
        metadata_only=bool(reasons),
        reasons=tuple(sorted(reasons)),
        categories=tuple(sorted(categories)),
        finding_contexts=tuple(sorted(contexts)),
    )


def _verified_sensitive_menu_screen(capture: ScreenCapture) -> bool:
    title = normalized(capture.title)
    activity = normalized(capture.activity_name)
    if not any(
        term in title or term in activity for term in SENSITIVE_SAFE_MENU_TERMS
    ):
        return False
    combined = normalized(" ".join(capture.tree.visible_labels))
    if any(term in combined for term in SENSITIVE_CONTENT_SURFACE_TERMS):
        return False
    if any(element.password or element.role == "text_field" for element in capture.tree.elements):
        return False
    return any(
        element.clickable
        and any(term in normalized(element.label) for term in SAFE_MENU_TERMS)
        for element in capture.tree.elements
    )


def apply_dynamic_sensitivity_policy(
    task: CollectionTask,
    capture: ScreenCapture,
    assessment: PrivacyAssessment,
) -> PrivacyAssessment:
    del capture
    sensitive_categories = sorted(set(task.sensitivity_categories))
    if not sensitive_categories:
        return assessment
    return PrivacyAssessment(
        metadata_only=True,
        reasons=tuple(sorted(set(assessment.reasons) | {"dynamic_sensitive_surface_default"})),
        categories=tuple(sorted(set(assessment.categories) | set(sensitive_categories))),
        finding_contexts=assessment.finding_contexts,
    )


def user_boundary(tree: ParsedUiTree, package: str) -> str | None:
    text = normalized(" ".join(tree.visible_labels))
    if package in SYSTEM_BOUNDARY_PACKAGES:
        if "permission" in package or any(term in text for term in PERMISSION_TERMS):
            return "permission_boundary"
        if "biometric" in package:
            return "biometric_boundary"
        return "system_boundary"
    if any(term in text for term in CAPTCHA_TERMS):
        return "captcha_boundary"
    if any(element.password for element in tree.elements):
        return "password_boundary"
    if any(term in text for term in PERMISSION_TERMS):
        return "permission_boundary"
    if any(term in text for term in AUTH_TERMS):
        return "authentication_boundary"
    return None


def is_final_or_consequential(label: str) -> bool:
    """Compatibility wrapper around the shared pure action classifier."""

    return is_final_or_consequential_label(label)


def is_safe_menu_element(element: UiElement, selected_label: str) -> bool:
    return is_safe_menu_or_settings_action(
        selected_label=selected_label,
        element_labels=(
            element.label,
            element.text,
            element.content_description,
            element.inferred_label,
        ),
        resource_id=element.resource_id,
    )


def action_guard_for_decision(
    decision: SafetyDecision,
    response: Mapping[str, object],
) -> AutoActionGuardDecision:
    """Compute label-free guard evidence immediately before device dispatch."""

    recommendation = response.get("recommendation")
    selected_label = (
        clean_text(recommendation.get("selected_label"))
        if isinstance(recommendation, Mapping)
        else ""
    )
    element = decision.element
    return evaluate_auto_action_guard(
        decision.action,
        selected_label=selected_label,
        element_labels=(
            element.label if element else "",
            element.text if element else "",
            element.content_description if element else "",
            element.inferred_label if element else "",
        ),
        resource_id=element.resource_id if element else "",
    )


_NEUTRAL_GATEWAY_EXACT_SCORES: dict[str, int] = {
    "설정": 100,
    "settings": 100,
    "setting": 100,
    "내 페이지": 96,
    "마이페이지": 96,
    "my page": 96,
    "profile": 94,
    "프로필": 94,
    "계정": 92,
    "account": 92,
    "전체 메뉴": 88,
    "메뉴": 86,
    "menu": 86,
    "더보기": 82,
    "more": 82,
    "고객센터": 78,
    "도움말": 76,
    "support": 76,
    "help": 74,
}
_NEUTRAL_CONTENT_MENU_TERMS = (
    "작업 메뉴",
    "추가 작업",
    "동영상 재생",
    "video playback",
    "post actions",
    "item actions",
)


def _neutral_gateway_score(element: UiElement, candidate_label: object) -> int:
    """Rank an unambiguous menu/settings gateway using transient UI data."""

    label = clean_text(candidate_label or element.label)
    normalized_label = normalized(label)
    if (
        not normalized_label
        or element.selected
        or not element.clickable
        or not element.enabled
        or not element.visible
        or element.bounds is None
        or element.checkable
        or element.password
        or element.role in {"text_field", "checkbox", "switch", "radio_button"}
        or any(term in normalized_label for term in _NEUTRAL_CONTENT_MENU_TERMS)
    ):
        return 0
    guard = evaluate_auto_action_guard(
        "click",
        selected_label=label,
        element_labels=(
            element.label,
            element.text,
            element.content_description,
            element.inferred_label,
        ),
        resource_id=element.resource_id,
    )
    if not guard.allowed:
        return 0
    if normalized_label in _NEUTRAL_GATEWAY_EXACT_SCORES:
        return _NEUTRAL_GATEWAY_EXACT_SCORES[normalized_label]
    # Resource-only icons remain useful when Android omits a visible label.
    resource = normalized(element.resource_id).replace("-", "_")
    resource_parts = {
        part for part in re.split(r"[^a-z0-9_]+", resource) if part
    }
    expanded = set(resource_parts)
    for part in resource_parts:
        expanded.update(value for value in part.split("_") if value)
    resource_scores = {
        "settings": 98,
        "setting": 98,
        "profile": 93,
        "mypage": 93,
        "account": 90,
        "navigation": 84,
        "drawer": 84,
        "menu": 82,
        "more": 78,
        "support": 74,
        "help": 72,
    }
    return max((score for token, score in resource_scores.items() if token in expanded), default=0)


def apply_neutral_discovery_fallback(
    response: Mapping[str, object],
    capture: ScreenCapture,
) -> dict[str, object]:
    """Select an exact safe gateway when the model returns no next action.

    K-EXAONE is reserved for ambiguous menu meaning.  Exact settings/profile/
    menu gateways are deterministic, and their selection is still checked by
    the shared pre-dispatch guard plus the API/local candidate equality gate.
    """

    result = dict(response)
    automation = response.get("automation")
    recommendation = response.get("recommendation")
    selected = (
        clean_text(recommendation.get("selected_element_id"))
        if isinstance(recommendation, Mapping)
        else ""
    )
    action = (
        clean_text(automation.get("action")).casefold()
        if isinstance(automation, Mapping)
        else "none"
    )
    if selected and action not in {"", "none", "stop"}:
        return result
    if user_boundary(capture.tree, capture.package):
        return result

    element_by_id = {element.element_id: element for element in capture.tree.elements}
    ranked: list[tuple[int, str, Mapping[str, object], UiElement]] = []
    candidates = response.get("candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            element_id = clean_text(candidate.get("element_id"))
            element = element_by_id.get(element_id)
            if element is None or clean_text(candidate.get("risk_level")) != "low":
                continue
            score = _neutral_gateway_score(element, candidate.get("label"))
            if score:
                ranked.append((score, element_id, candidate, element))
    if not ranked:
        return result
    ranked.sort(key=lambda row: (-row[0], row[1]))
    score, element_id, candidate, element = ranked[0]
    label = clean_text(candidate.get("label") or element.label)
    element_key = clean_text(candidate.get("element_key"))
    recommendation_id = "ur_" + stable_hash(
        {
            "request_id": clean_text(response.get("request_id")),
            "screen": clean_text(response.get("screen_fingerprint")),
            "element_id": element_id,
            "mode": "neutral_gateway",
        },
        16,
    )
    base_recommendation = (
        dict(recommendation) if isinstance(recommendation, Mapping) else {}
    )
    base_recommendation.update(
        {
            "recommendation_id": recommendation_id,
            "selected_element_id": element_id,
            "selected_element_key": element_key,
            "selected_label": label,
            "target_function": "neutral_safe_gateway_discovery",
            "instruction": f"{label} 메뉴를 엽니다.",
            "reason": "정확히 일치하는 안전한 메뉴·설정 진입점입니다.",
            "expected_next_screen": "메뉴 또는 설정 화면",
            "confidence": min(0.99, score / 100.0),
            "risk_level": "low",
            "requires_user_confirmation": False,
        }
    )
    base_automation = dict(automation) if isinstance(automation, Mapping) else {}
    base_automation.update(
        {
            "action": "click",
            "safe_to_execute": True,
            "selected_element_id": element_id,
            "selected_element_key": element_key,
            "selected_label": label,
            "reason": "deterministic_local_neutral_gateway",
        }
    )
    warnings = list(response.get("warnings") or [])
    warnings.append("정확히 일치하는 메뉴 진입점을 로컬 규칙으로 선택했습니다.")
    result.update(
        {
            "status": "guided",
            "phase": "exploring",
            "decision_mode": "deterministic_fallback",
            "recommendation": base_recommendation,
            "automation": base_automation,
            "performance": None,
            "warnings": warnings,
        }
    )
    return result


def is_sensitive_local_task(task: CollectionTask) -> bool:
    """Any inventory sensitivity category forces the zero-API local policy."""

    return bool(tuple(value for value in task.sensitivity_categories if clean_text(value)))


def sensitive_persisted_action_guard(
    decision: SensitiveLocalDecision,
) -> AutoActionGuardDecision:
    """Recompute the shared guard from a non-human persisted policy bucket.

    The transient screen labels are used by ``choose_sensitive_local_menu_action``
    immediately before dispatch.  Their raw values are never written.  This
    second decision has exactly the same safety truth table while remaining
    independently recomputable from the stored transition.
    """

    guard = evaluate_auto_action_guard(
        "click",
        selected_label=SENSITIVE_GUARD_LABEL_BUCKET,
        element_labels=(),
        resource_id="",
    )
    if (
        decision.action_guard is None
        or not decision.allowed
        or not guard.allowed
        or guard.evidence() != decision.action_guard.evidence()
    ):
        raise ValueError("sensitive local decision guard attestation mismatch")
    return guard


def validate_sensitive_resume_state(state: ExplorationState) -> None:
    """Reject legacy/leaky sensitive checkpoints and never replay an action."""

    if int(getattr(state, "external_api_transfer_count", 0) or 0) != 0:
        raise ValueError("sensitive local resume has nonzero external API transfers")
    if getattr(state, "scroll_novelty_label_sets", []):
        raise ValueError("sensitive local resume contains persisted screen semantics")
    pending = state.pending_action
    if pending is None:
        return
    allowed_pending_keys = {
        "transition_id",
        "source_screen_id",
        "source_observation_id",
        "app_package",
        "goal_id",
        "goal_candidate_id",
        "goal_family_id",
        "action_type",
        "element_id",
        "ui_element_id",
        "selected_label",
        "auto_action_guard",
        "sensitive_local_only",
        "sensitive_local_decision",
        "sensitive_goal_destination_boundary_after_navigation",
        "external_api_transfer_count",
        "local_from_signature",
        "server_from_fingerprint",
        "performed_at",
        "performed_at_epoch_ms",
        "action_execution_ms",
        "coordinates",
        "can_go_back",
        "repeated_or_loop",
        "resumed_after_process_boundary",
    }
    if not set(pending).issubset(allowed_pending_keys):
        raise ValueError("sensitive local resume pending action contains raw or unknown fields")
    if (
        pending.get("sensitive_local_only") is not True
        or clean_text(pending.get("action_type")).casefold() != "click"
        or clean_text(pending.get("selected_label")) != SENSITIVE_GUARD_LABEL_BUCKET
        or int(pending.get("external_api_transfer_count") or 0) != 0
    ):
        raise ValueError("sensitive local resume pending action is not privacy-safe")
    evidence = pending.get("sensitive_local_decision")
    if not isinstance(evidence, Mapping):
        raise ValueError("sensitive local resume lacks local decision evidence")
    allowed_evidence_keys = {
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
    if set(evidence) != allowed_evidence_keys:
        raise ValueError("sensitive local resume decision evidence shape is invalid")
    commitment = clean_text(evidence.get("semantic_commitment_sha256"))
    signal_ids = evidence.get("matched_signal_ids")
    if (
        evidence.get("human_text_persisted") is not False
        or int(evidence.get("external_api_transfer_count") or 0) != 0
        or clean_text(evidence.get("persisted_guard_label_bucket"))
        != SENSITIVE_GUARD_LABEL_BUCKET
        or not re.fullmatch(r"[0-9a-f]{64}", commitment)
        or not isinstance(signal_ids, list)
        or any(
            not isinstance(value, str)
            or not re.fullmatch(r"[a-z][a-z0-9_.]*", value)
            for value in signal_ids
        )
    ):
        raise ValueError("sensitive local resume decision evidence is invalid")
    recomputed = evaluate_auto_action_guard(
        "click",
        selected_label=SENSITIVE_GUARD_LABEL_BUCKET,
        element_labels=(),
        resource_id="",
    )
    if (
        not guard_evidence_matches(pending.get("auto_action_guard"), recomputed)
        or evidence.get("action_guard") != recomputed.evidence()
    ):
        raise ValueError("sensitive local resume guard evidence is invalid")


def restore_physical_exploration_state(
    resume_state: Mapping[str, object] | None,
    fallback_session_id: str,
) -> ExplorationState:
    """Restore physical-only evidence without ever replaying an input action."""

    payload = resume_state or {}
    state = (
        ExplorationState.from_checkpoint(payload, fallback_session_id)
        if resume_state
        else ExplorationState(session_id=fallback_session_id)
    )
    state.external_api_transfer_count = int(
        payload.get("external_api_transfer_count") or 0
    )
    raw_label_sets = payload.get("scroll_novelty_label_sets") or []
    if not isinstance(raw_label_sets, list) or any(
        not isinstance(row, list)
        or any(not isinstance(value, str) for value in row)
        for row in raw_label_sets
    ):
        raise ValueError("resume scroll novelty state is invalid")
    state.scroll_novelty_label_sets = [
        set(clean_text(value) for value in row if clean_text(value))
        for row in raw_label_sets[-3:]
    ]

    pending = payload.get("pending_action")
    if pending is None:
        state.pending_action = None
        return state
    if not isinstance(pending, Mapping):
        raise ValueError("resume pending action is invalid")
    guard = pending.get("auto_action_guard")
    if not isinstance(guard, Mapping):
        raise ValueError("resume pending action lacks guard evidence")
    action_type = clean_text(pending.get("action_type")).casefold()
    try:
        reconstructed = AutoActionGuardDecision(
            action_type=clean_text(guard.get("action_type")).casefold(),
            allowed=guard.get("allowed") is True,
            computed_final_or_consequential=(
                guard.get("computed_final_or_consequential") is True
            ),
            safe_menu_match=guard.get("safe_menu_match") is True,
            reason=clean_text(guard.get("reason")),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("resume pending action guard evidence is invalid") from error
    if (
        action_type not in {"click", "scroll_forward", "back"}
        or reconstructed.action_type != action_type
        or not reconstructed.allowed
        or reconstructed.computed_final_or_consequential
        or not guard_evidence_matches(guard, reconstructed)
    ):
        raise ValueError("resume pending action guard evidence is invalid")
    # This marker forces an unknown transition outcome after the next capture.
    # No dispatcher consumes pending_action, so the prior tap/swipe/back is
    # never replayed after a process boundary.
    state.pending_action = {
        **dict(pending),
        "resumed_after_process_boundary": True,
    }
    return state


def assess_physical_automation(
    response: Mapping[str, object],
    capture: ScreenCapture,
    *,
    expected_package: str,
) -> SafetyDecision:
    boundary = user_boundary(capture.tree, capture.package)
    if boundary:
        automation = response.get("automation")
        action = clean_text(automation.get("action")) if isinstance(automation, Mapping) else "none"
        return SafetyDecision(False, action or "none", boundary)
    decision = base.assess_automation(response, capture, expected_package=expected_package)
    if not decision.allowed:
        return decision
    if decision.action != "click":
        return decision
    if decision.element is None:
        return SafetyDecision(False, decision.action, "missing_local_element")
    recommendation = response.get("recommendation")
    selected_label = (
        clean_text(recommendation.get("selected_label"))
        if isinstance(recommendation, Mapping)
        else decision.element.label
    )
    guard = evaluate_auto_action_guard(
        "click",
        selected_label=selected_label,
        element_labels=(
            decision.element.label,
            decision.element.text,
            decision.element.content_description,
            decision.element.inferred_label,
        ),
        resource_id=decision.element.resource_id,
    )
    return SafetyDecision(
        guard.allowed,
        "click",
        guard.reason,
        decision.element,
    )


@dataclass
class PhysicalScrollGuard:
    max_scrolls: int
    scroll_count: int = 0
    previous_label_sets: list[set[str]] = field(default_factory=list)

    def screen_type(self, tree: ParsedUiTree) -> str:
        labels = [normalized(label) for label in tree.visible_labels]
        combined = " ".join(labels)
        menu_hits = sum(term in combined for term in SAFE_MENU_TERMS)
        if any(term in combined for term in FEED_TERMS) and menu_hits <= 1:
            return "infinite_feed"
        currency_rows = sum(bool(re.search(r"(?:₩|\$|€|\b\d{1,3}(?:,\d{3})+\s*원)", label)) for label in labels)
        if any(term in combined for term in PRODUCT_LIST_TERMS) or currency_rows >= 3:
            return "product_list"
        return "menu"

    def assess(self, tree: ParsedUiTree) -> SafetyDecision:
        kind = self.screen_type(tree)
        if kind in {"infinite_feed", "product_list"}:
            return SafetyDecision(False, "scroll_forward", f"excluded_{kind}")
        if self.scroll_count >= self.max_scrolls:
            return SafetyDecision(False, "scroll_forward", "scroll_budget_exhausted")
        current = {normalized(label) for label in tree.visible_labels if clean_text(label)}
        if self.previous_label_sets:
            previous = self.previous_label_sets[-1]
            similarity = len(current & previous) / max(1, len(current | previous))
            novelty = len(current - previous)
            if similarity >= 0.90 or novelty <= 1:
                return SafetyDecision(False, "scroll_forward", "repeated_screen_after_scroll")
        return SafetyDecision(True, "scroll_forward", "physical_page_scroll")

    def note(self, tree: ParsedUiTree) -> None:
        self.previous_label_sets.append({normalized(label) for label in tree.visible_labels if clean_text(label)})
        self.previous_label_sets = self.previous_label_sets[-3:]
        self.scroll_count += 1


def page_scroll_points(bounds: tuple[int, int, int, int] | None) -> tuple[int, int, int, int]:
    # The shared implementation moves about 78% of the visible scroll region.
    return base.page_scroll_points(bounds)


def structured_screen_for_model(
    capture: ScreenCapture, *, force_metadata_only: bool = False
) -> dict[str, object]:
    """Return redacted Accessibility structure only—never image bytes/path."""

    payload = capture.api_screen()
    payload.pop("screenshot", None)
    payload.pop("screenshot_path", None)
    privacy = assess_privacy(capture.tree)
    metadata_only = privacy.metadata_only or force_metadata_only
    if metadata_only:
        payload["window_title"] = REDACTED
    for element in payload.get("elements", []):
        if not isinstance(element, dict):
            continue
        if metadata_only:
            # Geometry, role and stable local element ID are sufficient to
            # preserve a metadata-only observation.  No semantic or
            # resource-derived label may cross the API boundary.
            for key in (
                "text",
                "content_description",
                "view_id",
                "resource_id",
                "label",
                "inferred_label",
                "hint",
                "value",
            ):
                element.pop(key, None)
            continue
        for key in ("text", "content_description"):
            value = clean_text(element.get(key))
            finding = classify_human_text(
                value,
                field_name=key,
                path=f"screen.elements.{key}",
            )
            if finding.metadata_only:
                element[key] = REDACTED
    return payload


def _graph_runtime():
    """Load the existing graph engine without invoking an LLM or API."""

    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))
    schemas = importlib.import_module("app.schemas")
    agent = importlib.import_module("app.services.universal_navigation_agent")
    graph = importlib.import_module("app.services.universal_navigation_graph")
    return schemas, agent, graph


def _transport_candidates(request: object) -> list[object]:
    """Represent local scroll/back controls as graph actions, never automation approval."""

    schemas, _, graph = _graph_runtime()
    candidates: list[object] = []
    screen = getattr(request, "screen")
    screen_fingerprint = graph.fingerprint_screen(getattr(request, "app_package"), screen)
    if any(
        bool(getattr(element, "visible", False))
        and bool(getattr(element, "enabled", False))
        and bool(getattr(element, "scrollable", False))
        for element in screen.elements
    ):
        candidates.append(
            schemas.UniversalNavigationCandidate(
                element_id="__page_scroll__",
                element_key="ue_" + stable_hash(
                    {"screen": screen_fingerprint, "action": "physical_page_scroll"}, 16
                ),
                label="next menu page",
                role="synthetic_navigation",
                risk_level="low",
                risk_reason="local_navigation_transport_only",
            )
        )
    candidates.append(
        schemas.UniversalNavigationCandidate(
            element_id="__back__",
            element_key="ue_" + stable_hash(
                {"screen": screen_fingerprint, "action": "physical_system_back"}, 16
            ),
            label="back",
            role="synthetic_navigation",
            risk_level="low",
            risk_reason="local_navigation_transport_only",
        )
    )
    return candidates


def _merge_graph_candidates(*candidate_groups: Sequence[object]) -> list[object]:
    merged: list[object] = []
    seen_element_ids: set[str] = set()
    seen_element_keys: set[str] = set()
    for candidates in candidate_groups:
        for candidate in candidates:
            element_id = clean_text(getattr(candidate, "element_id", ""))
            element_key_value = clean_text(getattr(candidate, "element_key", ""))
            if not element_id or not element_key_value:
                continue
            if element_id in seen_element_ids or element_key_value in seen_element_keys:
                continue
            seen_element_ids.add(element_id)
            seen_element_keys.add(element_key_value)
            merged.append(candidate)
    return merged


class RealCorpusAdapter:
    def __init__(
        self,
        run_directory: Path,
        run_id: str,
        *,
        resume: bool,
        collection_mode: str = "capture_only",
        validation_profile: str = "full_cohort",
        selected_packages: Sequence[str] = (),
        inventory_packages: Sequence[str] = (),
        inventory_snapshot: Mapping[str, object] | None = None,
        runtime_attestation: Mapping[str, object] | None = None,
        exploration_stage: str = EXPLORATION_STAGE_INITIAL_CAPTURE,
        goal_candidate_plan: Mapping[str, object] | None = None,
        tasks: Sequence[Mapping[str, object]] = (),
    ) -> None:
        self.instance: object | None = None
        self.run_directory = run_directory
        self.collection_mode = clean_text(collection_mode).casefold()
        self.validation_profile = clean_text(validation_profile).casefold() or "full_cohort"
        self.selected_packages = tuple(sorted({clean_text(value) for value in selected_packages if clean_text(value)}))
        self.inventory_packages = tuple(sorted({clean_text(value) for value in inventory_packages if clean_text(value)}))
        self.inventory_snapshot = dict(inventory_snapshot) if inventory_snapshot is not None else None
        self.runtime_attestation = (
            dict(runtime_attestation) if runtime_attestation is not None else None
        )
        self.exploration_stage = clean_text(exploration_stage).casefold()
        self.goal_candidate_plan = (
            dict(goal_candidate_plan) if goal_candidate_plan is not None else None
        )
        self.tasks = tuple(dict(task) for task in tasks)
        if str(API_ROOT) not in sys.path:
            sys.path.insert(0, str(API_ROOT))
        try:
            module = importlib.import_module("app.services.real_device_observation_corpus")
        except (ImportError, ModuleNotFoundError):
            return
        constructor = getattr(module, "RealDeviceObservationCorpus", None)
        if constructor is None:
            return
        self.instance = constructor(run_directory, run_id=run_id, resume=resume)

    @property
    def available(self) -> bool:
        return self.instance is not None

    def append(
        self,
        kind: str,
        payload: Mapping[str, object],
        *,
        record_id: str,
        privacy_verified: bool | None = None,
    ) -> Mapping[str, object] | None:
        if self.instance is None:
            return None
        method = getattr(self.instance, f"append_{kind}")
        adapted = dict(payload)
        if kind == "screen":
            for key in ("screenshot_path", "accessibility_tree_path"):
                value = adapted.get(key)
                if value:
                    candidate = Path(str(value))
                    adapted[key] = str(
                        candidate if candidate.is_absolute() else self.run_directory / candidate
                    )
        kwargs: dict[str, object] = {"record_id": record_id}
        if kind in {"screen", "element"}:
            kwargs["privacy_verified"] = privacy_verified is True
        result = method(adapted, **kwargs)
        normalized = getattr(result, "payload", None)
        return dict(normalized) if isinstance(normalized, Mapping) else None

    def export_typed_jsonl(self, files: Mapping[str, str]) -> bool:
        """Regenerate per-table mirrors from normalized SQLite payloads."""
        if self.instance is None:
            return False
        database_path = Path(getattr(self.instance, "database_path"))
        table_to_file = {
            "runs": files["run"],
            "apps": files["app"],
            "screens": files["screen"],
            "elements": files["element"],
            "transitions": files["transition"],
            "goals": files["goal"],
            "failures": files["failure"],
            "metrics": files["metric"],
            "annotations": files["annotation"],
        }
        grouped: dict[str, list[str]] = {table: [] for table in table_to_file}
        connection = sqlite3.connect(database_path)
        try:
            for record_type, payload_json in connection.execute(
                "SELECT record_type, payload_json FROM event_log ORDER BY sequence"
            ):
                record_type = str(record_type)
                if record_type in grouped:
                    grouped[record_type].append(str(payload_json))
        finally:
            connection.close()
        for table, filename in table_to_file.items():
            data = "".join(f"{line}\n" for line in grouped[table]).encode("utf-8")
            atomic_write_bytes(self.run_directory / filename, data)
        return True

    def save_checkpoint(self, state: Mapping[str, object]) -> bool:
        if self.instance is None:
            return False
        self.instance.save_checkpoint(dict(state))
        return True

    def load_checkpoint(self) -> dict[str, object] | None:
        if self.instance is None:
            return None
        state = self.instance.resume_state
        return dict(state) if isinstance(state, Mapping) else {}

    def record_count(self, kind: str) -> int:
        if self.instance is None:
            return 0
        method = getattr(self.instance, "counts", None)
        if method is None:
            return 0
        values = method()
        if not isinstance(values, Mapping):
            return 0
        plural = kind if kind.endswith("s") else f"{kind}s"
        return int(values.get(plural, values.get(kind, 0)) or 0)

    def record_ids(self, kind: str) -> set[str]:
        """Return persisted IDs so a resumed collector does not re-append them.

        Stable records such as app/version metadata and goals include a
        collection timestamp in their normalized payload. Reconstructing those
        payloads during resume would therefore look like a conflicting append
        even though their stable identity is unchanged. Restore the in-memory
        registration sets from SQLite instead.
        """

        if self.instance is None:
            return set()
        database_path = Path(getattr(self.instance, "database_path"))
        plural = kind if kind.endswith("s") else f"{kind}s"
        connection = sqlite3.connect(database_path)
        try:
            rows = connection.execute(
                "SELECT record_id FROM event_log WHERE record_type = ? ORDER BY sequence",
                (plural,),
            ).fetchall()
        finally:
            connection.close()
        return {clean_text(row[0]) for row in rows if clean_text(row[0])}

    def action_safety_counts(self) -> dict[str, int]:
        if self.instance is None:
            element_payloads: dict[str, Mapping[str, object]] = {}
            element_path = self.run_directory / "elements.jsonl"
            if element_path.is_file():
                for line in element_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if isinstance(value, Mapping):
                        element_payloads[clean_text(value.get("element_id"))] = value
            unsafe = 0
            final = 0
            transition_path = self.run_directory / "transitions.jsonl"
            if transition_path.is_file():
                for line in transition_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, Mapping) or value.get("auto_executed") is not True:
                        continue
                    if clean_text(value.get("action_type")).casefold() != "click":
                        continue
                    element_id = clean_text(value.get("element_id"))
                    element_exists = element_id in element_payloads
                    element = element_payloads.get(element_id, {})
                    decision = evaluate_auto_action_guard(
                        "click",
                        selected_label=value.get("selected_label", ""),
                        element_labels=tuple(
                            element.get(key, "")
                            for key in (
                                "label",
                                "text",
                                "content_description",
                                "inferred_label",
                            )
                        ),
                        resource_id=element.get("resource_id", ""),
                    )
                    if decision.computed_final_or_consequential:
                        final += 1
                    if (
                        not decision.allowed
                        or not guard_evidence_matches(
                            value.get("auto_action_guard"), decision
                        )
                        or not element_exists
                        or value.get("is_final_action")
                        is not decision.computed_final_or_consequential
                        or value.get("unsafe_action") is not (not decision.allowed)
                    ):
                        unsafe += 1
            return {
                "unsafe_auto_click_count": unsafe,
                "final_action_auto_click_count": final,
            }
        method = getattr(self.instance, "action_safety_counts", None)
        if method is None:
            raise RuntimeError("real-device corpus lacks evidence-derived safety counters")
        values = method()
        if not isinstance(values, Mapping):
            raise RuntimeError("real-device corpus returned invalid safety counters")
        return {
            "unsafe_auto_click_count": int(values.get("unsafe_auto_click_count", 0) or 0),
            "final_action_auto_click_count": int(
                values.get("final_action_auto_click_count", 0) or 0
            ),
        }

    def update_control_metadata(self, *, status: str, app_statuses: Sequence[Mapping[str, str]]) -> bool:
        if self.instance is None:
            return False
        method = getattr(self.instance, "update_control_metadata", None)
        if method is None:
            return False
        method(
            status=status,
            app_statuses=[dict(item) for item in app_statuses],
            device_type="physical_android",
            is_emulator=False,
            device_serial=EXPECTED_SERIAL,
            collection_mode=self.collection_mode,
            validation_profile=self.validation_profile,
            selected_packages=list(self.selected_packages),
            inventory_packages=list(self.inventory_packages),
            inventory_snapshot=self.inventory_snapshot,
            runtime_attestation=self.runtime_attestation,
            exploration_stage=self.exploration_stage,
            goal_candidate_plan=self.goal_candidate_plan,
            tasks=list(self.tasks),
        )
        return True

    @property
    def graph_repository(self) -> object:
        if self.instance is None:
            raise GraphMirrorError("real-device corpus graph repository is unavailable")
        repository = getattr(self.instance, "graph_repository", None)
        if repository is None:
            raise GraphMirrorError("real-device corpus does not expose graph_repository")
        return repository

    def refresh_after_graph_write(self) -> None:
        if self.instance is None:
            raise GraphMirrorError("real-device corpus graph refresh is unavailable")
        refresh = getattr(self.instance, "refresh_after_graph_write", None)
        if refresh is None:
            raise GraphMirrorError("real-device corpus does not expose graph hash refresh")
        try:
            refresh()
        except Exception as error:
            raise GraphMirrorError(f"graph hash/control-file refresh failed: {error}") from error


class RealObservationSink:
    FILES = {
        "run": "runs.jsonl",
        "app": "apps.jsonl",
        "screen": "screens.jsonl",
        "element": "elements.jsonl",
        "transition": "transitions.jsonl",
        "goal": "goals.jsonl",
        "failure": "failures.jsonl",
        "metric": "metrics.jsonl",
        "annotation": "annotations.jsonl",
    }

    def __init__(
        self,
        output_root: Path,
        run_id: str,
        *,
        resume: bool,
        manifest: Mapping[str, object],
    ) -> None:
        self.run_id = run_id
        self.run_directory = output_root / run_id
        self.run_directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.run_directory / "manifest.json"
        self.checkpoint_path = self.run_directory / "checkpoint.json"
        existing = self.manifest_path.exists() or (self.run_directory / "corpus.sqlite").exists()
        if existing and not resume:
            raise FileExistsError(f"run exists; use --resume: {self.run_directory}")
        self.adapter = RealCorpusAdapter(
            self.run_directory,
            run_id,
            resume=resume,
            collection_mode=clean_text(manifest.get("collection_mode")) or "capture_only",
            validation_profile=clean_text(manifest.get("validation_profile")) or "full_cohort",
            selected_packages=(
                manifest.get("selected_packages")
                if isinstance(manifest.get("selected_packages"), Sequence)
                and not isinstance(manifest.get("selected_packages"), (str, bytes))
                else ()
            ),
            inventory_packages=(
                manifest.get("inventory_packages")
                if isinstance(manifest.get("inventory_packages"), Sequence)
                and not isinstance(manifest.get("inventory_packages"), (str, bytes))
                else ()
            ),
            inventory_snapshot=(
                manifest.get("inventory_snapshot")
                if isinstance(manifest.get("inventory_snapshot"), Mapping)
                else None
            ),
            runtime_attestation=(
                manifest.get("runtime_attestation")
                if isinstance(manifest.get("runtime_attestation"), Mapping)
                else None
            ),
            exploration_stage=(
                clean_text(manifest.get("exploration_stage"))
                or EXPLORATION_STAGE_INITIAL_CAPTURE
            ),
            goal_candidate_plan=(
                manifest.get("goal_candidate_plan")
                if isinstance(manifest.get("goal_candidate_plan"), Mapping)
                else None
            ),
            tasks=(
                manifest.get("tasks")
                if isinstance(manifest.get("tasks"), Sequence)
                and not isinstance(manifest.get("tasks"), (str, bytes))
                else ()
            ),
        )
        self.manifest = dict(manifest)
        self.app_statuses: dict[str, str] = {
            clean_text(item.get("app_package")): clean_text(item.get("status"))
            for item in self.manifest.get("app_statuses", [])
            if isinstance(item, Mapping)
        }
        if not self.adapter.available:
            if self.manifest_path.exists():
                existing_manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self.manifest = {**existing_manifest, **self.manifest}
            self._write_fallback_manifest("collecting")
        self.adapter.update_control_metadata(status="collecting", app_statuses=self._app_status_rows())
        self._registered_apps: set[str] = self.adapter.record_ids("app") if resume else set()
        self._registered_goals: set[str] = self.adapter.record_ids("goal") if resume else set()
        if resume and not self.adapter.available:
            self._registered_apps.update(
                self._record_ids_from_typed_jsonl(self.FILES["app"], "app_observation_id")
            )
            self._registered_goals.update(
                self._record_ids_from_typed_jsonl(self.FILES["goal"], "goal_id")
            )
        lifecycle_id = run_id if not resume else f"{run_id}:resume:{utc_now()}"
        if not (resume and self.adapter.record_count("runs") > 0):
            self.append(
                "run",
                {
                    "run_observation_id": lifecycle_id,
                    "device_id": EXPECTED_SERIAL,
                    "avd_name": AVD_NAME,
                    "api_base_url": manifest.get("api_base_url"),
                    "lifecycle_event": "start",
                    "started_at": manifest.get("created_at"),
                },
                record_id=lifecycle_id,
            )

    def _record_ids_from_typed_jsonl(self, filename: str, identifier: str) -> set[str]:
        path = self.run_directory / filename
        if not path.is_file():
            return set()
        record_ids: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            if isinstance(value, Mapping):
                record_id = clean_text(value.get(identifier))
                if record_id:
                    record_ids.add(record_id)
        return record_ids

    def _app_status_rows(self) -> list[dict[str, str]]:
        return [
            {"app_package": package, "status": status}
            for package, status in sorted(self.app_statuses.items())
        ]

    def _write_fallback_manifest(self, status: str) -> None:
        payload = {
            **self.manifest,
            "provenance": PROVENANCE,
            "dataset_role": DATASET_ROLE,
            "review_status": REVIEW_STATUS,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "raw_artifacts_persisted": False,
            "status": status,
            "app_statuses": self._app_status_rows(),
            "updated_at": utc_now(),
        }
        atomic_write_json(self.manifest_path, payload)

    def append(
        self,
        kind: str,
        payload: Mapping[str, object],
        *,
        record_id: str,
        privacy_verified: bool | None = None,
    ) -> None:
        record = {
            **dict(payload),
            "run_id": self.run_id,
            "provenance": PROVENANCE,
            "dataset_role": DATASET_ROLE,
            "review_status": REVIEW_STATUS,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_mutation_allowed": False,
            "raw_artifacts_persisted": False,
            "recorded_at": utc_now(),
        }
        mirrored = self.adapter.append(
            kind,
            record,
            record_id=record_id,
            privacy_verified=privacy_verified,
        )
        if self.adapter.available and mirrored is not None:
            append_jsonl(self.run_directory / self.FILES[kind], mirrored)
        elif not self.adapter.available:
            append_jsonl(self.run_directory / self.FILES[kind], record)

    def set_app_status(self, app_package: str, status: str) -> None:
        if status not in {"installed_observed", "installed_not_selected", "skipped_missing"}:
            raise ValueError(f"invalid app status: {status}")
        self.app_statuses[app_package] = status
        if not self.adapter.update_control_metadata(status="collecting", app_statuses=self._app_status_rows()):
            self._write_fallback_manifest("collecting")

    def finalize(self, status: str) -> None:
        if status not in {"completed", "incomplete", "failed"}:
            raise ValueError(f"invalid run status: {status}")
        if not self.adapter.update_control_metadata(status=status, app_statuses=self._app_status_rows()):
            self._write_fallback_manifest(status)
        self.adapter.export_typed_jsonl(self.FILES)

    def action_safety_counts(self) -> dict[str, int]:
        """Read counters recomputed from persisted transition evidence."""

        return self.adapter.action_safety_counts()

    def register_app(self, task: CollectionTask, capture: ScreenCapture) -> None:
        self.register_app_metadata(task, capture.app_version, capture.locale)

    def register_app_metadata(
        self,
        task: CollectionTask,
        app_version: str,
        locale: str,
        version_code: str | None = None,
    ) -> None:
        record_id = f"app_{stable_hash({'package': task.app_package, 'version': app_version, 'locale': locale})}"
        if record_id in self._registered_apps:
            return
        self.append(
            "app",
            {
                "app_observation_id": record_id,
                "app_package": task.app_package,
                "app_name": task.app_name,
                "app_version": app_version,
                "version_name": app_version or None,
                "version_code": version_code,
                "version_key": _snapshot_version_key(app_version, version_code),
                "version_candidate_id": "version_"
                + stable_hash(
                    {
                        "run_id": self.run_id,
                        "app_package": task.app_package,
                        "version_name": app_version or None,
                        "version_code": version_code,
                    },
                    24,
                ),
                "sensitivity_categories": list(task.sensitivity_categories),
                "sensitivity_handling": task.sensitivity_handling or None,
                "locale": locale,
                "install_source": "preinstalled_on_user_device",
                "store_url": None,
            },
            record_id=record_id,
        )
        self._registered_apps.add(record_id)

    def register_goal(self, task: CollectionTask) -> str:
        identity: dict[str, object] = {
            "package": task.app_package,
            "goal": task.goal_text,
        }
        if task.candidate_id:
            identity["candidate_id"] = task.candidate_id
        goal_id = f"goal_{stable_hash(identity, 20)}"
        if goal_id not in self._registered_goals:
            self.append(
                "goal",
                {
                    "goal_id": goal_id,
                    "app_package": task.app_package,
                    "goal_text": task.goal_text,
                    "status": "unreviewed_candidate",
                    "terminal_confidence": 0.0,
                    "evidence": {
                        "source": PROVENANCE,
                        "task_id": task.task_id,
                        "sensitivity_categories": list(task.sensitivity_categories),
                        "sensitivity_handling": task.sensitivity_handling or None,
                        "version_key": task.version_key or None,
                        "candidate_id": task.candidate_id or None,
                        "family_id": task.family_id or None,
                        "terminal_policy": task.terminal_policy or None,
                        "source_run_id": task.source_run_id or None,
                        "source_inventory_snapshot_id": (
                            task.source_inventory_snapshot_id or None
                        ),
                        "confidence": task.confidence,
                        "candidate_rank": task.candidate_rank,
                        "source_artifact_sha256": (
                            task.source_artifact_sha256 or None
                        ),
                    },
                },
                record_id=goal_id,
            )
            self._registered_goals.add(goal_id)
        return goal_id

    def checkpoint(self, state: Mapping[str, object]) -> None:
        if not self.adapter.save_checkpoint(state):
            atomic_write_json(self.checkpoint_path, dict(state))
        self.adapter.export_typed_jsonl(self.FILES)

    def load_checkpoint(self) -> dict[str, object]:
        state = self.adapter.load_checkpoint()
        if state is not None:
            return state
        if not self.checkpoint_path.exists():
            return {}
        payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}

    def mirror_graph_observation(
        self,
        request_payload: Mapping[str, object],
        *,
        api_response: Mapping[str, object] | None,
    ) -> GraphMirrorResult:
        """Mirror one sanitized observation into this run's shadow graph.

        ``api_response=None`` is the capture-only path. It deliberately uses
        only the deterministic local candidate extractor and cannot make a
        network/model call.
        """

        if not self.adapter.available:
            raise GraphMirrorError("run-local graph mirroring requires the typed corpus service")
        schemas, agent, graph = _graph_runtime()
        try:
            request = schemas.UniversalNavigationObserveRequest.model_validate(dict(request_payload))
        except Exception as error:
            raise GraphMirrorError(f"invalid sanitized observe request: {error}") from error

        expected_fingerprint = graph.fingerprint_screen(request.app_package, request.screen)
        response = None
        if api_response is not None:
            try:
                response = schemas.UniversalNavigationObserveResponse.model_validate(dict(api_response))
            except Exception as error:
                raise GraphMirrorError(f"invalid observe API response: {error}") from error
            if response.request_id != request.request_id or response.session_id != request.session_id:
                raise GraphMirrorError("observe response request/session identity mismatch")
            if response.screen_fingerprint != expected_fingerprint:
                raise GraphMirrorError(
                    "API/global screen fingerprint does not match the run-local sanitized request"
                )

        # The public candidate extractor is deterministic and performs no
        # provider call. It remains the write source in both modes; API
        # candidates are only an equality-checked attestation of what the
        # global service saw.
        model_candidates = list(agent.extract_navigation_candidates(request))
        if response is not None:
            candidate_fields = (
                "element_id",
                "element_key",
                "label",
                "role",
                "risk_level",
                "risk_reason",
            )
            local_candidate_map = {
                candidate.element_id: tuple(getattr(candidate, field) for field in candidate_fields)
                for candidate in model_candidates
            }
            response_candidate_map = {
                candidate.element_id: tuple(getattr(candidate, field) for field in candidate_fields)
                for candidate in response.candidates
            }
            if response_candidate_map != local_candidate_map:
                raise GraphMirrorError("API/global candidates do not match deterministic local candidates")
            if response.recommendation is not None and response.recommendation.selected_element_id:
                selected = next(
                    (
                        candidate
                        for candidate in model_candidates
                        if candidate.element_id == response.recommendation.selected_element_id
                    ),
                    None,
                )
                if selected is None:
                    raise GraphMirrorError("API recommendation selected a non-local candidate")
                if (
                    response.recommendation.selected_element_key != selected.element_key
                    or response.recommendation.selected_label != selected.label
                    or response.recommendation.risk_level != selected.risk_level
                ):
                    raise GraphMirrorError("API recommendation candidate metadata diverged locally")
        candidates = _merge_graph_candidates(model_candidates, _transport_candidates(request))
        repository = self.adapter.graph_repository
        try:
            observation = repository.observe(request, candidates)
        except Exception as error:
            raise GraphMirrorError(f"run-local graph observation failed: {error}") from error
        if observation.screen_fingerprint != expected_fingerprint:
            raise GraphMirrorError("run-local graph returned a non-deterministic screen fingerprint")
        if response is not None and observation.screen_fingerprint != response.screen_fingerprint:
            raise GraphMirrorError("run-local and API/global graph fingerprints diverged")

        recommendation_recorded = False
        route_recorded = False
        try:
            if response is not None and response.recommendation is not None:
                recommendation = response.recommendation
                stored_action = observation.actions_by_element_id.get(
                    recommendation.selected_element_id or ""
                )
                repository.record_recommendation(
                    recommendation_id=recommendation.recommendation_id,
                    session_id=request.session_id,
                    app_package=request.app_package,
                    app_version=request.app_version,
                    locale=request.locale,
                    goal_text=request.goal_text,
                    goal_interpretation=response.goal_interpretation,
                    target_function=recommendation.target_function,
                    decision_mode=response.decision_mode,
                    screen_fingerprint=observation.screen_fingerprint,
                    action_id=None if stored_action is None else stored_action.action_id,
                    confidence=recommendation.confidence,
                )
                recommendation_recorded = True
            if response is not None and response.discovered_route is not None:
                discovered = response.discovered_route
                step_confidences = [float(step.confidence) for step in discovered.steps]
                confidence = (
                    float(response.recommendation.confidence)
                    if response.recommendation is not None
                    else sum(step_confidences) / len(step_confidences)
                    if step_confidences
                    else 0.0
                )
                stored_route = repository.save_route(
                    app_package=request.app_package,
                    app_version=request.app_version,
                    locale=request.locale,
                    goal_text=request.goal_text,
                    target_function=discovered.target_function,
                    start_screen_fingerprint=discovered.start_screen_fingerprint,
                    destination_screen_fingerprint=discovered.destination_screen_fingerprint,
                    steps=[step.model_dump(mode="json") for step in discovered.steps],
                    confidence=confidence,
                    provisional=True,
                )
                if stored_route.lifecycle_status != "shadow" or not stored_route.provisional:
                    raise GraphMirrorError("mirrored route escaped shadow/provisional lifecycle")
                route_recorded = True
        except GraphMirrorError:
            # ``observe`` may already have committed a candidate screen/action.
            # Keep manifest/checkpoint hashes truthful even when a later
            # recommendation/route invariant fails.
            self.adapter.refresh_after_graph_write()
            raise
        except Exception as error:
            self.adapter.refresh_after_graph_write()
            raise GraphMirrorError(f"run-local recommendation/route mirror failed: {error}") from error
        self.adapter.refresh_after_graph_write()

        return GraphMirrorResult(
            screen_fingerprint=observation.screen_fingerprint,
            actions_created=observation.actions_created,
            transition_recorded=observation.transition_recorded,
            recommendation_recorded=recommendation_recorded,
            route_recorded=route_recorded,
        )


class PhysicalExplorationRunner:
    def __init__(
        self,
        adb: RealDeviceAdbClient,
        api: ObserveApiClient,
        sink: RealObservationSink,
        budget: ExplorationBudget,
        *,
        capture_only: bool,
        dry_run: bool,
        launch_app: bool,
        screenshot_policy: str,
        discovery_explore: bool = False,
    ) -> None:
        self.adb = adb
        self.api = api
        self.sink = sink
        self.budget = budget
        self.capture_only = capture_only
        self.discovery_explore = discovery_explore
        self.dry_run = dry_run
        self.launch_app = launch_app
        self.screenshot_policy = screenshot_policy

    def run_task(self, task: CollectionTask, *, resume_state: Mapping[str, object] | None = None) -> str:
        if not self.adb.package_installed(task.app_package):
            self.sink.set_app_status(task.app_package, "skipped_missing")
            return "skipped_missing"
        version_details_method = getattr(self.adb, "app_version_details", None)
        if callable(version_details_method):
            version_details = version_details_method(task.app_package)
            live_version_name = clean_text(version_details.get("version_name"))
            live_version_code = clean_text(version_details.get("version_code")) or None
        else:
            live_version_name = self.adb.app_version(task.app_package)
            live_version_code = None
        if task.version_name and live_version_name != task.version_name:
            raise AdbError("installed version_name differs from inventory snapshot")
        if task.version_code and live_version_code != task.version_code:
            raise AdbError("installed version_code differs from inventory snapshot")
        self.sink.register_app_metadata(
            task,
            live_version_name,
            self.adb.locale(),
            version_code=live_version_code,
        )
        goal_id = self.sink.register_goal(task)
        self.sink.set_app_status(task.app_package, "installed_observed")
        session_id = f"physical_{stable_hash({'task': task.task_id, 'run': self.sink.run_id}, 18)}"
        state = restore_physical_exploration_state(resume_state, session_id)
        if is_sensitive_local_task(task):
            validate_sensitive_resume_state(state)
        # Resume in-place so the first post-boundary capture can close any
        # pending transition as unknown. Relaunching here would destroy that
        # evidence and could strand a user-completed authentication boundary.
        if self.launch_app and not resume_state:
            self.adb.launch(task.app_package)
            time.sleep(self.budget.settle_seconds)
        scroll_guard = PhysicalScrollGuard(
            self.budget.max_scrolls,
            scroll_count=state.scroll_count,
            previous_label_sets=list(state.scroll_novelty_label_sets),
        )
        app_directory = self.sink.run_directory / "apps" / base.slug(task.app_package)
        app_directory.mkdir(parents=True, exist_ok=True)
        captured_this_attempt = False

        while True:
            # Evidence-only capture must always observe the current screen once,
            # even when every action budget is intentionally zero.  Budgets
            # constrain interaction; they must not suppress the initial read.
            # Capture-only performs exactly one evidence read and then returns
            # either ``captured`` or a user boundary.  A resumed authentication
            # task must receive that one fresh read even though its persisted
            # state already contains the pre-auth screen and its action budget
            # is intentionally zero.
            budget_reason = (
                None
                if self.capture_only and not captured_this_attempt
                else state.budget_reason(self.budget)
            )
            if budget_reason:
                if self.discovery_explore:
                    return self._complete_discovery(
                        task,
                        goal_id,
                        state,
                        status="discovery_budget_complete",
                        reason=budget_reason,
                    )
                self._failure(task, goal_id, budget_reason, "Physical exploration budget ended safely.")
                self._checkpoint(task, state, f"stopped:{budget_reason}")
                return f"stopped:{budget_reason}"
            capture_id = f"{task.task_id}-{state.action_count:03d}-{uuid.uuid4().hex[:8]}"
            capture = self.adb.capture_pair(
                app_directory,
                capture_id,
                screenshot_policy=self.screenshot_policy,
                # Inventory sensitivity is authoritative from the first byte
                # of capture. Do not rely on detecting private words after a
                # derivative has already been written.
                force_metadata_only=is_sensitive_local_task(task),
            )
            # App metadata was read from the requested package before launch.
            # Do not let a browser/identity-provider boundary replace it with
            # the foreground external app's version.
            capture = replace(capture, app_version=live_version_name)
            captured_this_attempt = True
            local_signature = capture.tree.screen_signature
            state.screen_visits[local_signature] = state.screen_visits.get(local_signature, 0) + 1
            screen_id = capture.capture_id
            observation_id = f"physical_obs_{stable_hash({'task': task.task_id, 'capture': screen_id}, 20)}"
            transient_privacy = assess_privacy(capture.tree)
            privacy = apply_dynamic_sensitivity_policy(
                task,
                capture,
                transient_privacy,
            )
            if capture.package != task.app_package:
                privacy = PrivacyAssessment(
                    metadata_only=True,
                    reasons=tuple(
                        sorted(set(privacy.reasons) | {"external_app_boundary"})
                    ),
                    categories=privacy.categories,
                    finding_contexts=privacy.finding_contexts,
                )
            # A screen discovered to be metadata-only at runtime is just as
            # private as one classified from the package inventory. Route
            # both through the deterministic local policy; otherwise an
            # address/profile screen would send an empty semantic payload to
            # the external planner and could never discover a safe gateway.
            privacy_local_surface = privacy.metadata_only
            self._record_capture(task, goal_id, state, capture, observation_id, privacy)

            api_transition: dict[str, object] | None = None
            graph_transition: dict[str, object] | None = None
            resolved_pending: dict[str, object] | None = None
            if state.pending_action:
                pending = state.pending_action
                resolved_pending = dict(pending)
                persisted_guard = pending.get("auto_action_guard")
                if not isinstance(persisted_guard, Mapping):
                    self._failure(
                        task,
                        goal_id,
                        "auto_action_guard_missing",
                        "A previously dispatched action lacks pre-execution guard evidence.",
                        screen_id,
                    )
                    self._checkpoint(task, state, "stopped:auto_action_guard_missing")
                    return "stopped:auto_action_guard_missing"
                resumed_after_boundary = (
                    pending.get("resumed_after_process_boundary") is True
                )
                changed = local_signature != clean_text(pending.get("local_from_signature"))
                outcome = (
                    "unknown_after_process_boundary"
                    if resumed_after_boundary
                    else "navigated"
                    if changed
                    else "no_change"
                )
                resolved_pending["resolved_outcome"] = outcome
                transition = {
                    **pending,
                    "target_screen_id": screen_id,
                    "target_observation_id": observation_id,
                    "outcome": outcome,
                    "success": changed if not resumed_after_boundary else False,
                    "transition_time_ms": max(
                        0.0,
                        time.time() * 1000.0 - float(pending.get("performed_at_epoch_ms") or 0.0),
                    ),
                    "auto_executed": True,
                    "is_final_action": bool(
                        pending.get("auto_action_guard", {}).get(
                            "computed_final_or_consequential", True
                        )
                        if isinstance(pending.get("auto_action_guard"), Mapping)
                        else True
                    ),
                    "unsafe_action": not bool(
                        pending.get("auto_action_guard", {}).get("allowed", False)
                        if isinstance(pending.get("auto_action_guard"), Mapping)
                        else False
                    ),
                }
                self.sink.append(
                    "transition",
                    transition,
                    record_id=clean_text(transition["transition_id"]),
                )
                if pending.get("server_from_fingerprint") and not resumed_after_boundary:
                    graph_transition = {
                        "from_screen_fingerprint": pending["server_from_fingerprint"],
                        "performed_element_id": pending.get("ui_element_id")
                        or pending.get("element_id"),
                        "outcome": outcome,
                    }
                    if pending.get("action_type") == "click" and pending.get("recommendation_id"):
                        graph_transition["recommendation_id"] = pending["recommendation_id"]
                    # Preserve the public API's existing click-only transition
                    # contract. The run-local candidate graph additionally
                    # captures scroll/back edges through deterministic pseudo
                    # actions that were stored on the source screen.
                    if pending.get("action_type") == "click":
                        api_transition = dict(graph_transition)
                state.pending_action = None

            # Repetition constrains autonomous exploration, not the single
            # evidence read performed by capture-only.  In particular, an
            # uncleared authentication screen must remain a user boundary on
            # resume rather than being mislabeled as a repeated-screen stop.
            if (
                not self.capture_only
                and state.screen_visits[local_signature] > self.budget.max_screen_visits
            ):
                if self.discovery_explore:
                    return self._complete_discovery(
                        task,
                        goal_id,
                        state,
                        status="discovery_frontier_exhausted",
                        reason="repeated_screen",
                        screen_id=screen_id,
                    )
                self._failure(task, goal_id, "repeated_screen", "Repeated-screen guard stopped navigation.", screen_id)
                self._checkpoint(task, state, "stopped:repeated_screen")
                return "stopped:repeated_screen"
            if capture.package != task.app_package:
                reason = "system_boundary" if capture.package in SYSTEM_BOUNDARY_PACKAGES else "external_app_boundary"
                self._failure(task, goal_id, reason, f"Observed package: {capture.package}", screen_id)
                self._checkpoint(task, state, f"boundary:{reason}")
                return f"boundary:{reason}"
            boundary = user_boundary(capture.tree, capture.package)
            if boundary and not privacy_local_surface:
                self._failure(task, goal_id, boundary, "User action is required at this boundary.", screen_id)
                self._checkpoint(task, state, f"boundary:{boundary}")
                return f"boundary:{boundary}"
            request_payload: dict[str, object] = {
                "request_id": f"physical_req_{uuid.uuid4().hex[:18]}",
                "session_id": state.session_id,
                "app_package": task.app_package,
                "app_version": capture.app_version,
                "locale": capture.locale,
                "goal_text": task.goal_text,
                "operation_mode": "explore",
                "screen": structured_screen_for_model(
                    capture,
                    force_metadata_only=privacy_local_surface,
                ),
                "client_timing": {
                    "measurement_source": "real_device",
                    "exploration_elapsed_ms": min(3_600_000.0, state.elapsed_seconds * 1000.0),
                    "screen_capture_ms": min(300_000.0, capture.capture_ms),
                    "action_execution_ms": 0.0,
                    "ui_settle_ms": min(300_000.0, self.budget.settle_seconds * 1000.0),
                    "external_wait_ms": 0.0,
                },
            }
            if api_transition:
                request_payload["transition"] = api_transition
            graph_request_payload = dict(request_payload)
            if graph_transition:
                graph_request_payload["transition"] = graph_transition
            if privacy_local_surface:
                sensitive_status = self._handle_sensitive_local_capture(
                    task=task,
                    goal_id=goal_id,
                    state=state,
                    capture=capture,
                    screen_id=screen_id,
                    observation_id=observation_id,
                    graph_request_payload=graph_request_payload,
                    transient_privacy=transient_privacy,
                    effective_privacy=privacy,
                    generic_boundary=boundary,
                    resolved_pending=resolved_pending,
                )
                if sensitive_status == "continue":
                    continue
                return sensitive_status
            if self.capture_only:
                try:
                    self.sink.mirror_graph_observation(
                        graph_request_payload,
                        api_response=None,
                    )
                except GraphMirrorError as error:
                    self._failure(task, goal_id, "graph_mirror_error", str(error), screen_id)
                    self._checkpoint(task, state, "failed:graph_mirror_error")
                    return "failed:graph_mirror_error"
                self._checkpoint(task, state, "captured")
                return "captured"
            api_started = time.perf_counter()
            # Count the sanitized observe request at the transfer boundary,
            # including provider/API failures. Capture-only and forced local
            # metadata-only paths never reach this line and remain zero.
            state.external_api_transfer_count += 1
            try:
                response = self.api.observe(request_payload)
            except ObserveApiError as error:
                api_ms = (time.perf_counter() - api_started) * 1000.0
                # The remote/provider failure must not discard the sanitized
                # local observation. Mirror deterministic screen/action
                # candidates, record the outage, and stop before any UI input.
                try:
                    self.sink.mirror_graph_observation(
                        graph_request_payload,
                        api_response=None,
                    )
                except GraphMirrorError as graph_error:
                    self._failure(
                        task,
                        goal_id,
                        "graph_mirror_error",
                        f"API failure ({error}); local fallback also failed ({graph_error})",
                        screen_id,
                    )
                    self._checkpoint(task, state, "failed:graph_mirror_error")
                    return "failed:graph_mirror_error"
                self._failure(task, goal_id, "observe_api_error", str(error), screen_id)
                metric_id = f"metric_{uuid.uuid4().hex[:20]}"
                self.sink.append(
                    "metric",
                    {
                        "metric_id": metric_id,
                        "app_package": task.app_package,
                        "goal_id": goal_id,
                        "metric_dimension": "provider_fallback",
                        "exploration_time_ms": state.elapsed_seconds * 1000.0,
                        "click_count": state.action_count - state.scroll_count - state.back_count,
                        "scroll_count": state.scroll_count,
                        "back_count": state.back_count,
                        "repeat_screen_visit_count": sum(
                            max(0, count - 1) for count in state.screen_visits.values()
                        ),
                        "user_intervention_count": 0,
                        **self.sink.action_safety_counts(),
                        "api_ms": api_ms,
                        "provider_failure": True,
                        "fallback_used": True,
                        "fallback_mode": "deterministic_local_graph_mirror",
                        "failure_reason": "observe_api_error",
                    },
                    record_id=metric_id,
                )
                self._checkpoint(task, state, "failed:observe_api_error")
                return "failed:observe_api_error"
            api_ms = (time.perf_counter() - api_started) * 1000.0
            if self.discovery_explore:
                response = apply_neutral_discovery_fallback(response, capture)
            try:
                self.sink.mirror_graph_observation(
                    graph_request_payload,
                    api_response=response,
                )
            except GraphMirrorError as error:
                self._failure(task, goal_id, "graph_mirror_error", str(error), screen_id)
                self._checkpoint(task, state, "failed:graph_mirror_error")
                return "failed:graph_mirror_error"
            metric_id = f"metric_{uuid.uuid4().hex[:20]}"
            self.sink.append(
                "metric",
                {
                    "metric_id": metric_id,
                    "app_package": task.app_package,
                    "goal_id": goal_id,
                    "metric_dimension": "policy",
                    "exploration_time_ms": state.elapsed_seconds * 1000.0,
                    "click_count": state.action_count - state.scroll_count - state.back_count,
                    "scroll_count": state.scroll_count,
                    "back_count": state.back_count,
                    "repeat_screen_visit_count": sum(max(0, count - 1) for count in state.screen_visits.values()),
                    "user_intervention_count": 0,
                    **self.sink.action_safety_counts(),
                    "api_ms": api_ms,
                    "phase": response.get("phase"),
                    "decision_mode": response.get("decision_mode"),
                },
                record_id=metric_id,
            )

            decision = assess_physical_automation(response, capture, expected_package=task.app_package)
            if decision.allowed and decision.action == "scroll_forward":
                decision = scroll_guard.assess(capture.tree)
            if not decision.allowed:
                phase = clean_text(response.get("phase"))
                if phase == "destination_reached":
                    self._checkpoint(task, state, "destination_reached")
                    return "destination_reached"
                if self.discovery_explore:
                    response_automation = response.get("automation")
                    response_action = (
                        clean_text(response_automation.get("action")).casefold()
                        if isinstance(response_automation, Mapping)
                        else "none"
                    )
                    frontier_reason = (
                        "no_safe_action"
                        if response_action in {"", "none", "stop"}
                        and decision.action in {"none", "stop"}
                        else decision.reason
                        if decision.reason
                        in {"repeated_screen_after_scroll", "scroll_budget_exhausted"}
                        else None
                    )
                    if frontier_reason:
                        return self._complete_discovery(
                            task,
                            goal_id,
                            state,
                            status="discovery_frontier_exhausted",
                            reason=frontier_reason,
                            screen_id=screen_id,
                        )
                self._failure(task, goal_id, decision.reason, "Local physical-device guard stopped automation.", screen_id)
                self._checkpoint(task, state, f"stopped:{decision.reason}")
                return f"stopped:{decision.reason}"
            if self.dry_run:
                self._checkpoint(task, state, "dry_run_complete")
                return "dry_run_complete"

            # Recompute the guard at the last possible moment before an input
            # command.  The label-free evidence is copied into the pending
            # transition so the validator can independently reclassify it.
            action_guard = action_guard_for_decision(decision, response)
            if not action_guard.allowed:
                self._failure(
                    task,
                    goal_id,
                    action_guard.reason,
                    "Pre-execution physical-device guard stopped automation.",
                    screen_id,
                )
                self._checkpoint(task, state, f"stopped:{action_guard.reason}")
                return f"stopped:{action_guard.reason}"

            action_started = time.perf_counter()
            metadata: dict[str, object] = {}
            if decision.action == "click" and decision.element and decision.element.bounds:
                self.adb.tap(decision.element.bounds)
                ui_element_id = decision.element.element_id
                element_id: str | None = f"{screen_id}:{ui_element_id}"
                metadata["coordinates"] = list(decision.element.bounds)
            elif decision.action == "scroll_forward":
                coordinates = self.adb.page_scroll(capture.tree.scroll_bounds)
                ui_element_id = "__page_scroll__"
                element_id = None
                state.scroll_count += 1
                scroll_guard.note(capture.tree)
                state.scroll_novelty_label_sets = list(
                    scroll_guard.previous_label_sets
                )
                metadata.update(
                    {
                        "coordinates": list(coordinates),
                        "scroll_direction": "forward",
                        "scroll_distance": abs(coordinates[1] - coordinates[3]),
                    }
                )
            elif decision.action == "back":
                self.adb.back()
                ui_element_id = "__back__"
                element_id = None
                state.back_count += 1
            else:
                self._failure(task, goal_id, "dispatch_mismatch", "No safe dispatcher matched.", screen_id)
                return "failed:dispatch_mismatch"

            state.action_count += 1
            recommendation = response.get("recommendation")
            recommendation = recommendation if isinstance(recommendation, Mapping) else {}
            state.pending_action = {
                "transition_id": f"physical_tr_{uuid.uuid4().hex[:18]}",
                "source_screen_id": screen_id,
                "source_observation_id": observation_id,
                "app_package": task.app_package,
                "goal_id": goal_id,
                "action_type": decision.action,
                "element_id": element_id,
                "ui_element_id": ui_element_id,
                "recommendation_id": clean_text(recommendation.get("recommendation_id")),
                "selected_label": clean_text(recommendation.get("selected_label")),
                "auto_action_guard": action_guard.evidence(),
                "local_from_signature": local_signature,
                "server_from_fingerprint": clean_text(response.get("screen_fingerprint")),
                "performed_at": utc_now(),
                "performed_at_epoch_ms": time.time() * 1000.0,
                "action_execution_ms": (time.perf_counter() - action_started) * 1000.0,
                "can_go_back": True,
                "repeated_or_loop": False,
                **metadata,
            }
            self._checkpoint(task, state, "running")
            time.sleep(self.budget.settle_seconds)

    def _record_sensitive_local_metric(
        self,
        task: CollectionTask,
        goal_id: str,
        state: ExplorationState,
        *,
        screen_id: str,
        policy_event: str,
        decision: SensitiveLocalDecision | None = None,
        boundary_kind: str | None = None,
        sensitivity_categories: Sequence[str] | None = None,
    ) -> None:
        """Persist only enums, opaque IDs, hashes, and guard buckets."""

        metric_id = f"metric_sensitive_{stable_hash({'task': task.task_id, 'screen': screen_id, 'event': policy_event, 'actions': state.action_count}, 20)}"
        self.sink.append(
            "metric",
            {
                "metric_id": metric_id,
                "app_package": task.app_package,
                "goal_id": goal_id,
                "goal_candidate_id": task.candidate_id or None,
                "goal_family_id": task.family_id or None,
                "metric_dimension": "sensitive_local_policy",
                "policy_event": policy_event,
                "screen_id": screen_id,
                "exploration_time_ms": state.elapsed_seconds * 1000.0,
                "click_count": state.action_count - state.scroll_count - state.back_count,
                "scroll_count": state.scroll_count,
                "back_count": state.back_count,
                "repeat_screen_visit_count": sum(
                    max(0, count - 1) for count in state.screen_visits.values()
                ),
                "user_intervention_count": 1 if boundary_kind else 0,
                **self.sink.action_safety_counts(),
                "external_api_transfer_count": 0,
                "sensitivity_categories": sorted(
                    {
                        clean_text(value)
                        for value in (
                            sensitivity_categories
                            if sensitivity_categories is not None
                            else task.sensitivity_categories
                        )
                        if clean_text(value)
                    }
                ),
                "fallback_mode": "deterministic_local_transient_accessibility",
                "boundary_kind": boundary_kind,
                "local_decision": decision.evidence() if decision else None,
                "human_text_persisted": False,
            },
            record_id=metric_id,
        )

    def _record_sensitive_goal_signals(
        self,
        task: CollectionTask,
        goal_id: str,
        *,
        screen_id: str,
        capture: ScreenCapture,
    ) -> int:
        evidences = collect_sensitive_local_goal_signal_evidence(
            capture.tree.elements
        )
        for evidence in evidences:
            payload = evidence.evidence()
            metric_id = "metric_sensitive_signal_" + stable_hash(
                {
                    "task": task.task_id,
                    "screen": screen_id,
                    "family": evidence.family_id,
                    "element": evidence.element_id,
                    "commitment": evidence.semantic_commitment_sha256,
                },
                20,
            )
            self.sink.append(
                "metric",
                {
                    "metric_id": metric_id,
                    "metric_dimension": "sensitive_local_goal_signal",
                    "policy_event": "label_free_goal_signal_observed",
                    "app_package": task.app_package,
                    "goal_id": goal_id,
                    "screen_id": screen_id,
                    "local_signal_evidence": payload,
                    "external_api_transfer_count": 0,
                    "human_text_persisted": False,
                },
                record_id=metric_id,
            )
        return len(evidences)

    def _handle_sensitive_local_capture(
        self,
        *,
        task: CollectionTask,
        goal_id: str,
        state: ExplorationState,
        capture: ScreenCapture,
        screen_id: str,
        observation_id: str,
        graph_request_payload: Mapping[str, object],
        transient_privacy: PrivacyAssessment,
        effective_privacy: PrivacyAssessment,
        generic_boundary: str | None,
        resolved_pending: Mapping[str, object] | None,
    ) -> str:
        """Run one zero-API, metadata-only sensitive-app exploration step."""

        del observation_id
        if int(getattr(state, "external_api_transfer_count", 0) or 0) != 0:
            raise ValueError("sensitive local task attempted an external API transfer")
        try:
            graph_result = self.sink.mirror_graph_observation(
                graph_request_payload,
                api_response=None,
            )
        except GraphMirrorError as error:
            self._failure(task, goal_id, "graph_mirror_error", str(error), screen_id)
            self._checkpoint(task, state, "failed:graph_mirror_error")
            return "failed:graph_mirror_error"

        # Capture-only remains evidence-only.  The screen's boundary flags and
        # metadata-only mode are already stored, with zero screen semantics.
        if self.capture_only:
            self._record_sensitive_local_metric(
                task,
                goal_id,
                state,
                screen_id=screen_id,
                policy_event="dynamic_sensitive_metadata_only_capture",
                sensitivity_categories=effective_privacy.categories,
            )
            self._checkpoint(task, state, "captured")
            return "captured"

        boundary_kind = generic_boundary
        # Metadata-only is a data-handling mode, not by itself a user
        # boundary. A postal address may coexist with a harmless profile or
        # settings gateway. Keep fail-closed boundaries for actual editable
        # and authentication controls, then let the local classifier protect
        # financial/personal content surfaces.
        if boundary_kind is None and {
            "password_field",
            "editable_field",
        }.intersection(transient_privacy.reasons):
            boundary_kind = "authentication_or_input_boundary"
        if boundary_kind is None:
            boundary_kind = classify_sensitive_surface_boundary(capture.tree.elements)
        if (
            boundary_kind is None
            and resolved_pending is not None
            and resolved_pending.get(
                "sensitive_goal_destination_boundary_after_navigation"
            )
            is True
        ):
            outcome = clean_text(resolved_pending.get("resolved_outcome"))
            boundary_kind = (
                "sensitive_goal_destination_user_boundary"
                if outcome in {"navigated", "unknown_after_process_boundary"}
                else "sensitive_goal_entry_no_change"
            )
        if boundary_kind:
            is_user_boundary = boundary_kind != "sensitive_goal_entry_no_change"
            self._record_sensitive_local_metric(
                task,
                goal_id,
                state,
                screen_id=screen_id,
                policy_event=(
                    "sensitive_local_user_boundary"
                    if is_user_boundary
                    else "sensitive_local_no_change"
                ),
                boundary_kind=boundary_kind if is_user_boundary else None,
                sensitivity_categories=effective_privacy.categories,
            )
            self._failure(
                task,
                goal_id,
                boundary_kind,
                "Sensitive content remains local and requires user handling."
                if is_user_boundary
                else "The safe goal entry did not change the screen.",
                screen_id,
            )
            status = (
                f"boundary:{boundary_kind}"
                if is_user_boundary
                else f"stopped:{boundary_kind}"
            )
            self._checkpoint(task, state, status)
            return status

        # Safe menu surfaces may reveal governed goal labels.  Persist only
        # their allowlisted signal IDs plus opaque source commitments so the
        # later goal generator can work despite metadata-only storage.
        self._record_sensitive_goal_signals(
            task,
            goal_id,
            screen_id=screen_id,
            capture=capture,
        )

        family_id = task.family_id or SENSITIVE_NEUTRAL_DISCOVERY_FAMILY
        decision = choose_sensitive_local_menu_action(
            capture.tree.elements,
            goal_family_id=family_id,
        )
        if decision.boundary_kind:
            self._record_sensitive_local_metric(
                task,
                goal_id,
                state,
                screen_id=screen_id,
                policy_event="sensitive_local_goal_entry_boundary",
                decision=decision,
                boundary_kind=decision.boundary_kind,
                sensitivity_categories=effective_privacy.categories,
            )
            self._failure(
                task,
                goal_id,
                decision.boundary_kind,
                "The located sensitive goal entry is user-owned.",
                screen_id,
            )
            status = f"boundary:{decision.boundary_kind}"
            self._checkpoint(task, state, status)
            return status

        if not decision.allowed:
            self._record_sensitive_local_metric(
                task,
                goal_id,
                state,
                screen_id=screen_id,
                policy_event="sensitive_local_frontier_exhausted",
                decision=decision,
                sensitivity_categories=effective_privacy.categories,
            )
            if self.discovery_explore and decision.reason == "no_safe_local_menu_candidate":
                return self._complete_discovery(
                    task,
                    goal_id,
                    state,
                    status="discovery_frontier_exhausted",
                    reason="no_safe_local_menu_candidate",
                    screen_id=screen_id,
                )
            self._failure(
                task,
                goal_id,
                decision.reason,
                "No local-only safe menu action was available.",
                screen_id,
            )
            status = f"stopped:{decision.reason}"
            self._checkpoint(task, state, status)
            return status

        self._record_sensitive_local_metric(
            task,
            goal_id,
            state,
            screen_id=screen_id,
            policy_event="sensitive_local_safe_menu_selected",
            decision=decision,
            sensitivity_categories=effective_privacy.categories,
        )
        if self.dry_run:
            self._checkpoint(task, state, "dry_run_complete")
            return "dry_run_complete"

        # Re-evaluate both the local selector and the shared action guard at
        # the last possible point before dispatch.  No model/network call can
        # occur between this decision and the tap.
        fresh_decision = choose_sensitive_local_menu_action(
            capture.tree.elements,
            goal_family_id=family_id,
        )
        if fresh_decision.evidence() != decision.evidence():
            self._failure(
                task,
                goal_id,
                "sensitive_local_decision_drift",
                "The local decision changed before dispatch.",
                screen_id,
            )
            self._checkpoint(task, state, "stopped:sensitive_local_decision_drift")
            return "stopped:sensitive_local_decision_drift"
        action_guard = sensitive_persisted_action_guard(fresh_decision)
        element = next(
            (
                value
                for value in capture.tree.elements
                if value.element_id == fresh_decision.element_id
            ),
            None,
        )
        if (
            element is None
            or not element.bounds
            or not element.clickable
            or not element.enabled
            or not element.visible
            or element.checkable
            or element.password
            or element.role == "text_field"
        ):
            self._failure(
                task,
                goal_id,
                "sensitive_local_element_invalid",
                "The selected local element failed the final structural gate.",
                screen_id,
            )
            self._checkpoint(task, state, "stopped:sensitive_local_element_invalid")
            return "stopped:sensitive_local_element_invalid"

        action_started = time.perf_counter()
        self.adb.tap(element.bounds)
        state.action_count += 1
        direct_goal_gateway = fresh_decision.score_bucket == "direct_goal_signal"
        state.pending_action = {
            "transition_id": f"physical_tr_{uuid.uuid4().hex[:18]}",
            "source_screen_id": screen_id,
            "source_observation_id": f"physical_obs_{stable_hash({'task': task.task_id, 'capture': screen_id}, 20)}",
            "app_package": task.app_package,
            "goal_id": goal_id,
            "goal_candidate_id": task.candidate_id or None,
            "goal_family_id": task.family_id or None,
            "action_type": "click",
            "element_id": f"{screen_id}:{element.element_id}",
            "ui_element_id": element.element_id,
            # This is a fixed policy bucket, never a copied Accessibility label.
            "selected_label": SENSITIVE_GUARD_LABEL_BUCKET,
            "auto_action_guard": action_guard.evidence(),
            "sensitive_local_only": True,
            "sensitive_local_decision": fresh_decision.evidence(),
            "sensitive_goal_destination_boundary_after_navigation": bool(
                direct_goal_gateway
                and (
                    fresh_decision.terminal_policy == "user_boundary"
                    or task.family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
                )
            ),
            "external_api_transfer_count": 0,
            "local_from_signature": capture.tree.screen_signature,
            "server_from_fingerprint": graph_result.screen_fingerprint,
            "performed_at": utc_now(),
            "performed_at_epoch_ms": time.time() * 1000.0,
            "action_execution_ms": (time.perf_counter() - action_started) * 1000.0,
            "coordinates": list(element.bounds),
            "can_go_back": True,
            "repeated_or_loop": False,
        }
        self._checkpoint(task, state, "running")
        time.sleep(self.budget.settle_seconds)
        return "continue"

    def _complete_discovery(
        self,
        task: CollectionTask,
        goal_id: str,
        state: ExplorationState,
        *,
        status: str,
        reason: str,
        screen_id: str | None = None,
    ) -> str:
        """Record bounded neutral coverage without misclassifying it as failure."""

        if status not in {"discovery_budget_complete", "discovery_frontier_exhausted"}:
            raise ValueError("invalid discovery completion status")
        metric_id = f"metric_discovery_{stable_hash({'task': task.task_id, 'status': status, 'reason': reason, 'actions': state.action_count}, 20)}"
        self.sink.append(
            "metric",
            {
                "metric_id": metric_id,
                "metric_dimension": "neutral_discovery_coverage",
                "app_package": task.app_package,
                "goal_id": goal_id,
                "screen_id": screen_id,
                "coverage_outcome": status,
                "coverage_reason": reason,
                "exploration_time_ms": state.elapsed_seconds * 1000.0,
                "click_count": state.action_count - state.scroll_count - state.back_count,
                "scroll_count": state.scroll_count,
                "back_count": state.back_count,
                "repeat_screen_visit_count": sum(
                    max(0, count - 1) for count in state.screen_visits.values()
                ),
                "external_api_transfer_count": int(
                    getattr(state, "external_api_transfer_count", 0) or 0
                ),
                **self.sink.action_safety_counts(),
            },
            record_id=metric_id,
        )
        self._checkpoint(task, state, status)
        return status

    def _record_capture(
        self,
        task: CollectionTask,
        goal_id: str,
        state: ExplorationState,
        capture: ScreenCapture,
        observation_id: str,
        privacy: PrivacyAssessment,
    ) -> None:
        if privacy.metadata_only:
            # UIAutomator and masked-image derivatives can still contain
            # unknown private strings on dynamically sensitive screens.  They
            # are needed only for this in-memory decision and are discarded
            # before any checkpoint/manifest is written.
            run_root = self.sink.run_directory.resolve()
            for artifact in (capture.tree_path, capture.screenshot_path):
                if artifact is None:
                    continue
                candidate = Path(artifact).resolve()
                if not candidate.is_relative_to(run_root):
                    raise ValueError(
                        "metadata-only derivative escaped the observation run"
                    )
                candidate.unlink(missing_ok=True)
        tree_path = (
            None
            if privacy.metadata_only
            else capture.tree_path.relative_to(self.sink.run_directory).as_posix()
        )
        screenshot_path = (
            capture.screenshot_path.relative_to(self.sink.run_directory).as_posix()
            if capture.screenshot_path and not privacy.metadata_only
            else None
        )
        record = {
            "screen_id": capture.capture_id,
            "observation_id": observation_id,
            "app_package": task.app_package,
            "app_name": task.app_name,
            "app_version": capture.app_version,
            "locale": capture.locale,
            "goal_id": goal_id,
            "goal_text": task.goal_text,
            "screen_signature": capture.tree.screen_signature,
            "screenshot_path": screenshot_path,
            "screenshot_sha256": capture.screenshot_sha256,
            "accessibility_tree_path": tree_path,
            "accessibility_tree_sha256": capture.tree_sha256,
            "activity_name": None if privacy.metadata_only else capture.activity_name,
            "title_text": None if privacy.metadata_only else capture.title,
            "visible_texts": [] if privacy.metadata_only else list(capture.tree.visible_labels),
            "content_descriptions": (
                []
                if privacy.metadata_only
                else [
                    element.content_description
                    for element in capture.tree.elements
                    if element.content_description and not element.sensitive
                ]
            ),
            # Resource IDs are structural, but the navigation agent derives
            # semantic labels from them.  Metadata-only screens therefore do
            # not retain this screen-level semantic source.
            "resource_ids": (
                []
                if privacy.metadata_only
                else sorted(
                    {element.resource_id for element in capture.tree.elements if element.resource_id}
                )
            ),
            "scrollable_regions": [list(capture.tree.scroll_bounds)] if capture.tree.scroll_bounds else [],
            "screen_type": PhysicalScrollGuard(self.budget.max_scrolls).screen_type(capture.tree),
            "login_state": "boundary" if user_boundary(capture.tree, capture.package) else "unknown",
            "prerequisites": [],
            "contains_personal_data": privacy.metadata_only,
            "collection_sensitivity_categories": list(task.sensitivity_categories),
            "detected_sensitivity_categories": list(privacy.categories),
            "sensitivity_handling": task.sensitivity_handling or None,
            "forced_dynamic_metadata_only": (
                "dynamic_sensitive_surface_default" in privacy.reasons
            ),
            "privacy_verified": not privacy.metadata_only,
            "privacy_fallback_reason": ",".join(privacy.reasons) if privacy.reasons else None,
            "evidence_mode": "metadata_only" if privacy.metadata_only else "verified_redacted",
            # tree_path always references a sanitized or fully-redacted
            # derivative; raw UIAutomator XML is never written.
            "accessibility_tree_redacted": True,
            "screenshot_redacted": capture.screenshot_path is not None,
            "collected_at": capture.captured_at,
            "raw_artifacts_persisted": False,
        }
        self.sink.append(
            "screen",
            record,
            record_id=capture.capture_id,
            privacy_verified=not privacy.metadata_only,
        )
        for element in capture.tree.elements:
            local_id = element.element_id
            element_record_id = f"{capture.capture_id}:{local_id}"
            payload = {
                **element.corpus_dict(),
                "element_id": element_record_id,
                "ui_element_id": local_id,
                "screen_id": capture.capture_id,
                "semantic_function_id": None,
                "synonyms": [],
                "expected_result": None,
                "risk_level": "blocked" if element.sensitive or element.checkable else "unclassified",
                "is_final_action": is_final_or_consequential(element.label),
                "confidence": 0.0,
                "evidence": {"source": "live_physical_uiautomator", "observation_id": observation_id},
            }
            if privacy.metadata_only:
                for key in (
                    "text",
                    "content_description",
                    "resource_id",
                    "inferred_label",
                    "label",
                    "semantic_function_id",
                    "synonyms",
                    "expected_result",
                    "expected_outcome",
                    "evidence",
                    "checked",
                    "selected",
                    "class_name",
                ):
                    payload.pop(key, None)
            self.sink.append(
                "element",
                payload,
                record_id=element_record_id,
                privacy_verified=not privacy.metadata_only,
            )
        annotation_id = f"annotation_{stable_hash({'screen': capture.capture_id, 'privacy': privacy.reasons}, 20)}"
        self.sink.append(
            "annotation",
            {
                "annotation_id": annotation_id,
                "entity_type": "screen",
                "entity_id": capture.capture_id,
                "label": "privacy_collection_mode",
                "value": {
                    "mode": "metadata_only" if privacy.metadata_only else "verified_accessibility",
                    "reasons": list(privacy.reasons),
                    "categories": list(privacy.categories),
                    "finding_contexts": list(privacy.finding_contexts),
                },
                "confidence": 1.0,
                "reviewer": "deterministic_physical_collector",
                "status": REVIEW_STATUS,
            },
            record_id=annotation_id,
        )

    def _failure(
        self,
        task: CollectionTask,
        goal_id: str,
        reason: str,
        detail: str,
        screen_id: str | None = None,
    ) -> None:
        failure_id = f"failure_{uuid.uuid4().hex[:20]}"
        self.sink.append(
            "failure",
            {
                "failure_id": failure_id,
                "app_package": task.app_package,
                "goal_id": goal_id,
                "user_goal": task.goal_text,
                "screen_id": screen_id,
                "failure_reason": reason,
                "cause": detail,
                "retry_result": "not_attempted",
            },
            record_id=failure_id,
        )

    def _checkpoint(self, task: CollectionTask, state: ExplorationState, status: str) -> None:
        existing = self.sink.load_checkpoint()
        completed = list(existing.get("completed_task_ids") or [])
        if is_sensitive_local_task(task):
            if int(getattr(state, "external_api_transfer_count", 0) or 0) != 0:
                raise ValueError("sensitive checkpoint cannot record an external API transfer")
            # Sensitive local exploration never scrolls automatically, so raw
            # novelty labels must not cross the in-memory boundary.
            state.scroll_novelty_label_sets = []
        state_payload = state.checkpoint_dict()
        state_payload["external_api_transfer_count"] = int(
            getattr(state, "external_api_transfer_count", 0) or 0
        )
        state_payload["scroll_novelty_label_sets"] = [
            sorted(clean_text(value) for value in row if clean_text(value))
            for row in getattr(state, "scroll_novelty_label_sets", [])[-3:]
        ]
        self.sink.checkpoint(
            {
                **existing,
                "completed_task_ids": completed,
                "current_task_id": task.task_id,
                "current_task": asdict(task),
                "task_status": status,
                "state": state_payload,
                "updated_at": utc_now(),
            }
        )


def find_adb(explicit: str | None) -> str:
    return base.find_adb(explicit)


def tasks_from_arguments(args: argparse.Namespace) -> list[CollectionTask]:
    goal_candidates = getattr(args, "goal_candidates", None)
    family_manifest = getattr(args, "family_manifest", None)
    discovery_explore = bool(getattr(args, "discovery_explore", False))
    if goal_candidates and not getattr(args, "inventory_snapshot", None):
        raise ValueError("--goal-candidates is only valid with --inventory-snapshot")
    if discovery_explore and not getattr(args, "inventory_snapshot", None):
        raise ValueError("--discovery-explore is only valid with --inventory-snapshot")
    if discovery_explore and goal_candidates:
        raise ValueError("--discovery-explore and --goal-candidates are mutually exclusive")
    if family_manifest and not goal_candidates:
        raise ValueError("--family-manifest requires --goal-candidates")
    if getattr(args, "inventory_snapshot", None):
        if any(
            clean_text(getattr(args, field, None))
            for field in ("package", "goal", "app_name", "category")
        ) or getattr(args, "manifest", None):
            raise ValueError(
                "--inventory-snapshot is mutually exclusive with static manifest/direct package arguments"
            )
        snapshot = getattr(args, "_loaded_inventory_snapshot", None)
        if not isinstance(snapshot, Mapping):
            snapshot = load_dynamic_inventory_snapshot(args.inventory_snapshot)
        if bool(getattr(args, "capture_only", False)):
            if goal_candidates or discovery_explore:
                raise ValueError(
                    "--capture-only rejects --goal-candidates and --discovery-explore"
                )
            return dynamic_inventory_tasks(
                snapshot,
                only_packages=getattr(args, "only_package", None) or [],
                max_apps=int(getattr(args, "max_apps", 0) or 0),
            )
        if discovery_explore:
            return dynamic_inventory_tasks(
                snapshot,
                only_packages=getattr(args, "only_package", None) or [],
                max_apps=int(getattr(args, "max_apps", 0) or 0),
            )
        if not goal_candidates:
            raise ValueError(
                "dynamic safe exploration requires --goal-candidates; use --capture-only for a neutral initial capture"
            )
        if not family_manifest:
            raise ValueError("--goal-candidates requires --family-manifest")
        try:
            plan = plan_applicable_goals(
                goal_candidates,
                args.inventory_snapshot,
                family_manifest,
                only_packages=getattr(args, "only_package", None) or [],
                max_goals_per_app=int(getattr(args, "max_goals_per_app", 0) or 0),
            )
        except GoalTaskPlanningError:
            raise
        args._loaded_goal_task_plan = plan
        return dynamic_goal_tasks(
            snapshot,
            plan,
            only_packages=getattr(args, "only_package", None) or [],
            max_apps=int(getattr(args, "max_apps", 0) or 0),
        )
    if args.manifest:
        document = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
        apps = document.get("apps") if isinstance(document, Mapping) else None
        if not isinstance(apps, list):
            raise ValueError("manifest must contain an apps array")
        only_packages = {
            clean_text(value)
            for value in (getattr(args, "only_package", None) or [])
            if clean_text(value)
        }
        manifest_packages = {
            clean_text(app.get("app_package"))
            for app in apps
            if isinstance(app, Mapping) and clean_text(app.get("app_package"))
        }
        unknown = sorted(only_packages - manifest_packages)
        if unknown:
            raise ValueError(f"--only-package is not present in manifest: {unknown}")
        selected_apps = [
            app
            for app in apps
            if isinstance(app, Mapping)
            and (not only_packages or clean_text(app.get("app_package")) in only_packages)
        ]
        tasks: list[CollectionTask] = []
        for app in selected_apps[: args.max_apps or None]:
            goals = app.get("priority_goals")
            if not isinstance(goals, list):
                goals = app.get("goals") if isinstance(app.get("goals"), list) else []
            for goal in goals[: args.max_goals_per_app or None]:
                task = CollectionTask(
                    app_package=clean_text(app.get("app_package")),
                    app_name=clean_text(app.get("app_name")) or clean_text(app.get("app_package")),
                    category=clean_text(app.get("category")) or "unknown",
                    goal_text=clean_text(goal),
                )
                if task.app_package and task.goal_text:
                    tasks.append(task)
        return tasks
    if getattr(args, "only_package", None):
        raise ValueError("--only-package requires --manifest or --inventory-snapshot")
    if not args.package or not args.goal:
        raise ValueError(
            "--package and --goal are required unless --manifest or --inventory-snapshot is used"
        )
    return [
        CollectionTask(
            app_package=clean_text(args.package),
            app_name=clean_text(args.app_name) or clean_text(args.package),
            category=clean_text(args.category) or "unknown",
            goal_text=clean_text(args.goal),
        )
    ]


def inventory_status_rows(
    inventory_packages: Sequence[str],
    selected_packages: Sequence[str],
    package_installed: Callable[[str], bool],
) -> list[dict[str, str]]:
    """Return an auditable status for every inventory package.

    ``installed_not_selected`` is deliberately distinct from observed evidence:
    it attests presence without suggesting the collector inspected the app.
    """

    inventory = sorted({clean_text(value) for value in inventory_packages if clean_text(value)})
    selected = {clean_text(value) for value in selected_packages if clean_text(value)}
    if not selected.issubset(inventory):
        raise ValueError("selected packages must be a subset of the attested inventory")
    rows: list[dict[str, str]] = []
    for package in inventory:
        installed = package_installed(package)
        status = (
            "skipped_missing"
            if not installed
            else "installed_observed"
            if package in selected
            else "installed_not_selected"
        )
        rows.append({"app_package": package, "status": status})
    return rows


def persist_task_result(
    sink: RealObservationSink,
    task: CollectionTask,
    status: str,
    completed: set[str],
    statuses: Mapping[str, str],
    *,
    capture_boundary_terminal: bool = False,
) -> bool:
    """Checkpoint one task without consuming a resumable boundary/failure.

    The runner writes the current task and exploration state before returning
    a boundary/stopped/failed status.  Preserve that state so ``--resume``
    continues the same app and goal after user intervention.
    """

    is_complete = status in COMPLETED_TASK_STATUSES or (
        capture_boundary_terminal and status.startswith("boundary:")
    )
    existing = sink.load_checkpoint()
    if is_complete:
        completed.add(task.task_id)
        payload: dict[str, object] = {
            **existing,
            "completed_task_ids": sorted(completed),
            "current_task_id": None,
            "current_task": None,
            "state": {},
            "task_status": status,
            "statuses": dict(statuses),
            "updated_at": utc_now(),
        }
    else:
        payload = {
            **existing,
            "completed_task_ids": sorted(completed),
            "current_task_id": task.task_id,
            "current_task": asdict(task),
            "task_status": status,
            "statuses": dict(statuses),
            "updated_at": utc_now(),
        }
    sink.checkpoint(payload)
    return is_complete


def record_task_summary(
    sink: RealObservationSink,
    task: CollectionTask,
    status: str,
    *,
    attempt_number: int,
) -> dict[str, object]:
    """Append one attempt-local summary without claiming model-assessed success."""

    checkpoint = sink.load_checkpoint()
    state = (
        checkpoint.get("state")
        if checkpoint.get("current_task_id") == task.task_id
        and isinstance(checkpoint.get("state"), Mapping)
        else {}
    )
    normalized_state = {
        "action_count": int(state.get("action_count") or 0),
        "scroll_count": int(state.get("scroll_count") or 0),
        "back_count": int(state.get("back_count") or 0),
        "elapsed_seconds": float(state.get("elapsed_seconds") or 0.0),
        "screen_visits": (
            dict(state.get("screen_visits"))
            if isinstance(state.get("screen_visits"), Mapping)
            else {}
        ),
    }
    safety = sink.action_safety_counts()
    goal_id = sink.register_goal(task)
    payload = build_task_summary_metric(
        task_id=task.task_id,
        app_package=task.app_package,
        goal_id=goal_id,
        terminal_status=status,
        state=normalized_state,
        attempt_number=attempt_number,
        goal_candidate_id=task.candidate_id or None,
        goal_family_id=task.family_id or None,
        terminal_policy=task.terminal_policy or None,
        external_api_transfer_count=int(
            state.get("external_api_transfer_count") or 0
        ),
        unsafe_auto_click_count=safety["unsafe_auto_click_count"],
        final_action_auto_click_count=safety["final_action_auto_click_count"],
        human_confirmed_success=None,
        human_confirmed_false_positive=None,
    )
    metric_id = f"metric_task_{stable_hash({'task': task.task_id, 'attempt': attempt_number}, 20)}"
    payload["metric_id"] = metric_id
    payload["source_goal_run_id"] = task.source_run_id or None
    payload["source_inventory_snapshot_id"] = (
        task.source_inventory_snapshot_id or None
    )
    payload["source_goal_artifact_sha256"] = task.source_artifact_sha256 or None
    sink.append("metric", payload, record_id=metric_id)
    return payload


def latest_task_summary_statuses(metrics_path: Path) -> dict[str, str]:
    """Recover the latest attempted status for each task from typed mirrors."""

    latest: dict[str, tuple[int, str]] = {}
    if not metrics_path.is_file():
        return {}
    for line in metrics_path.read_text(encoding="utf-8").splitlines():
        try:
            metric = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(metric, Mapping) or metric.get("metric_dimension") != "task_summary":
            continue
        task_id = clean_text(metric.get("task_id"))
        status = clean_text(metric.get("terminal_status"))
        attempt = metric.get("attempt_number")
        if (
            not task_id
            or not status
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt < 1
        ):
            continue
        previous = latest.get(task_id)
        if previous is None or attempt >= previous[0]:
            latest[task_id] = (attempt, status)
    return {task_id: value[1] for task_id, value in latest.items()}


def validate_dynamic_resume_lineage(
    existing_manifest: Mapping[str, object],
    *,
    inventory_snapshot_metadata: Mapping[str, object],
    selected_packages: Sequence[str],
    inventory_packages: Sequence[str],
    exploration_stage: str,
    goal_candidate_plan: Mapping[str, object] | None,
) -> None:
    """Reject resume when source hashes or the exact goal selection drift."""

    def json_equivalent(left: object, right: object) -> bool:
        try:
            return json.dumps(
                left,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ) == json.dumps(
                right,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError):
            return False

    if (
        existing_manifest.get("validation_profile") != DYNAMIC_INVENTORY_PROFILE
        or not json_equivalent(
            existing_manifest.get("inventory_snapshot"),
            dict(inventory_snapshot_metadata),
        )
        or existing_manifest.get("selected_packages") != list(selected_packages)
        or existing_manifest.get("inventory_packages") != list(inventory_packages)
        or existing_manifest.get("exploration_stage") != exploration_stage
        or not json_equivalent(
            existing_manifest.get("goal_candidate_plan"),
            dict(goal_candidate_plan) if goal_candidate_plan is not None else None,
        )
    ):
        raise ValueError("dynamic inventory resume lineage mismatch")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    task_source = parser.add_mutually_exclusive_group()
    task_source.add_argument("--package")
    task_source.add_argument("--manifest", type=Path)
    task_source.add_argument("--inventory-snapshot", type=Path)
    parser.add_argument(
        "--goal-candidates",
        type=Path,
        help="validated dynamic goal-candidate artifact for safe exploration",
    )
    parser.add_argument(
        "--family-manifest",
        type=Path,
        help=(
            "exact goal-family manifest hashed by --goal-candidates "
            f"(normally {DEFAULT_GOAL_FAMILY_MANIFEST})"
        ),
    )
    parser.add_argument("--app-name")
    parser.add_argument("--category")
    parser.add_argument("--goal")
    parser.add_argument(
        "--only-package",
        action="append",
        default=[],
        help="repeatable static/dynamic inventory selector; the full source inventory is still attested",
    )
    parser.add_argument("--max-apps", type=int, default=0)
    parser.add_argument("--max-goals-per-app", type=int, default=0)
    parser.add_argument("--serial", default=EXPECTED_SERIAL)
    parser.add_argument("--adb")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument(
        "--discovery-explore",
        action="store_true",
        help="bounded neutral menu/settings graph discovery before goal planning",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--screenshot-policy", choices=("none", "redacted"), default="none")
    parser.add_argument("--max-actions", type=int, default=24)
    parser.add_argument("--max-seconds", type=float, default=75.0)
    parser.add_argument("--max-scrolls", type=int, default=4)
    parser.add_argument("--max-backs", type=int, default=6)
    parser.add_argument("--max-screen-visits", type=int, default=2)
    parser.add_argument("--settle-seconds", type=float, default=1.5)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validate_serial(args.serial)
    if args.resume and not args.run_id:
        raise SystemExit("--resume requires --run-id")
    if min(
        args.max_actions,
        args.max_scrolls,
        args.max_backs,
        args.max_screen_visits,
        args.max_apps,
        args.max_goals_per_app,
    ) < 0:
        raise SystemExit("budgets must be non-negative")
    inventory_snapshot: dict[str, object] | None = None
    if args.inventory_snapshot:
        try:
            inventory_snapshot = load_dynamic_inventory_snapshot(args.inventory_snapshot)
        except (OSError, ValueError) as error:
            raise SystemExit(str(error)) from error
        args._loaded_inventory_snapshot = inventory_snapshot
    try:
        tasks = tasks_from_arguments(args)
    except (OSError, ValueError, GoalTaskPlanningError) as error:
        raise SystemExit(str(error)) from error
    if not tasks:
        raise SystemExit("no physical-device tasks were selected")
    run_id = args.run_id or f"physical-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    collection_mode = "capture_only" if args.capture_only else "dry_run" if args.dry_run else "safe_explore"
    exploration_stage = (
        EXPLORATION_STAGE_INITIAL_CAPTURE
        if args.capture_only
        else EXPLORATION_STAGE_NEUTRAL_DISCOVERY
        if args.discovery_explore
        else EXPLORATION_STAGE_GOAL_DIRECTED
    )
    inventory_packages: list[str] = []
    if args.manifest:
        manifest_document = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
        manifest_apps = manifest_document.get("apps") if isinstance(manifest_document, Mapping) else None
        if not isinstance(manifest_apps, list):
            raise SystemExit("manifest must contain an apps array")
        inventory_packages = sorted(
            {
                clean_text(app.get("app_package"))
                for app in manifest_apps
                if isinstance(app, Mapping) and clean_text(app.get("app_package"))
            }
        )
    selected_packages = sorted({task.app_package for task in tasks})
    inventory_snapshot_metadata: dict[str, object] | None = None
    goal_task_plan: GoalTaskPlan | None = getattr(args, "_loaded_goal_task_plan", None)
    if inventory_snapshot is not None:
        # Re-read immediately before creating the run so a replaced snapshot
        # cannot silently change after task planning.
        snapshot_recheck = load_dynamic_inventory_snapshot(args.inventory_snapshot)
        if snapshot_recheck["sha256"] != inventory_snapshot["sha256"]:
            raise SystemExit("inventory snapshot changed during task planning")
        inventory_packages = sorted(
            str(item["package"])
            for item in inventory_snapshot["included_apps"]
            if isinstance(item, Mapping)
        )
        validation_profile = DYNAMIC_INVENTORY_PROFILE
        inventory_snapshot_metadata = dynamic_inventory_manifest_metadata(
            inventory_snapshot,
            observation_root=args.output_root.resolve(),
            run_id=run_id,
            selected_packages=selected_packages,
        )
        inventory_snapshot_metadata["selected_tasks"] = [
            asdict(task) | {"task_id": task.task_id} for task in tasks
        ]
        inventory_snapshot_metadata["exploration_stage"] = exploration_stage
        if goal_task_plan is not None:
            try:
                # Re-run every planner gate immediately before run creation.
                # This detects replacement of the artifact, snapshot, family
                # manifest, source corpus, or VALIDATED marker after selection.
                rechecked_plan = plan_applicable_goals(
                    args.goal_candidates,
                    args.inventory_snapshot,
                    args.family_manifest,
                    only_packages=args.only_package,
                    max_goals_per_app=args.max_goals_per_app,
                )
            except (OSError, ValueError, GoalTaskPlanningError) as error:
                raise SystemExit(f"goal task lineage recheck failed: {error}") from error
            if rechecked_plan != goal_task_plan:
                raise SystemExit("goal task selection changed during task planning")
            inventory_snapshot_metadata["goal_candidate_plan"] = (
                dynamic_goal_plan_manifest_metadata(
                    goal_task_plan,
                    artifact_path=args.goal_candidates,
                    family_manifest_path=args.family_manifest,
                    observation_root=args.output_root.resolve(),
                    tasks=tasks,
                )
            )
    else:
        partial_research = bool(args.manifest) and set(selected_packages) != set(inventory_packages)
        validation_profile = "partial_research" if partial_research else "full_cohort"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": utc_now(),
        "provenance": PROVENANCE,
        "dataset_role": DATASET_ROLE,
        "review_status": REVIEW_STATUS,
        "route_lifecycle": ROUTE_LIFECYCLE,
        "run_mode": "real_device_observation",
        "collection_mode": collection_mode,
        "exploration_stage": exploration_stage,
        "validation_profile": validation_profile,
        "selected_packages": selected_packages,
        "inventory_packages": inventory_packages,
        "inventory_snapshot": inventory_snapshot_metadata,
        "goal_candidate_plan": (
            inventory_snapshot_metadata.get("goal_candidate_plan")
            if isinstance(inventory_snapshot_metadata, Mapping)
            else None
        ),
        "runtime_attestation": None,
        "status": "collecting",
        "raw_artifacts_persisted": False,
        "device_serial": EXPECTED_SERIAL,
        "serial": EXPECTED_SERIAL,
        "device_type": "physical",
        "is_emulator": False,
        "physical_device_required": True,
        "api_base_url": args.api_base_url,
        "app_statuses": [],
        "canonical_mutation_allowed": False,
        "tasks": [asdict(task) | {"task_id": task.task_id} for task in tasks],
        "safety": {
            # This bootstrap value is replaced by the corpus service's
            # evidence-derived count as soon as the run is initialized.
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            "install_or_delete_command_count": 0,
            "raw_screenshot_external_transfer_count": 0,
        },
    }
    if args.resume and inventory_snapshot_metadata is not None:
        existing_manifest_path = args.output_root.resolve() / run_id / "manifest.json"
        if not existing_manifest_path.is_file():
            raise SystemExit("dynamic inventory resume requires an existing manifest")
        existing_manifest = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        if not isinstance(existing_manifest, Mapping):
            raise SystemExit("dynamic inventory resume lineage mismatch")
        try:
            validate_dynamic_resume_lineage(
                existing_manifest,
                inventory_snapshot_metadata=inventory_snapshot_metadata,
                selected_packages=selected_packages,
                inventory_packages=inventory_packages,
                exploration_stage=exploration_stage,
                goal_candidate_plan=(
                    inventory_snapshot_metadata.get("goal_candidate_plan")
                    if isinstance(
                        inventory_snapshot_metadata.get("goal_candidate_plan"),
                        Mapping,
                    )
                    else None
                ),
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
    adb = RealDeviceAdbClient(find_adb(args.adb), args.serial)
    adb.assert_ready()
    if inventory_snapshot is not None:
        try:
            manifest["runtime_attestation"] = collect_runtime_attestation(
                adb,
                expected_device=inventory_snapshot["device"],
                api_base_url=args.api_base_url,
            )
        except (AdbError, ObserveApiError, OSError, ValueError) as error:
            raise SystemExit(f"runtime attestation failed: {error}") from error
    # Attest the complete manifest cohort before launching anything, so a
    # later boundary or failure still leaves an auditable installed/missing
    # inventory in manifest.json. Installed apps outside a partial run are
    # explicitly recorded as not selected and never represented as observed.
    inventory_to_attest = inventory_packages or selected_packages
    inventory_rows = inventory_status_rows(
        inventory_to_attest,
        selected_packages,
        adb.package_installed,
    )
    if inventory_snapshot_metadata is not None and any(
        row["status"] == "skipped_missing" for row in inventory_rows
    ):
        raise SystemExit("dynamic inventory snapshot is stale: an included package is not installed")
    manifest["app_statuses"] = inventory_rows
    sink = RealObservationSink(
        args.output_root.resolve(), run_id, resume=args.resume, manifest=manifest
    )
    for row in inventory_rows:
        package = row["app_package"]
        package_status = row["status"]
        sink.set_app_status(package, package_status)
        print(f"[physical] inventory package={package} status={package_status}", flush=True)
    runner = PhysicalExplorationRunner(
        adb,
        ObserveApiClient(args.api_base_url),
        sink,
        ExplorationBudget(
            max_actions=args.max_actions,
            max_seconds=args.max_seconds,
            max_scrolls=args.max_scrolls,
            max_backs=args.max_backs,
            max_screen_visits=args.max_screen_visits,
            settle_seconds=args.settle_seconds,
        ),
        capture_only=args.capture_only,
        discovery_explore=args.discovery_explore,
        dry_run=args.dry_run,
        launch_app=not args.no_launch,
        screenshot_policy=args.screenshot_policy,
    )
    checkpoint = sink.load_checkpoint() if args.resume else {}
    completed = set(checkpoint.get("completed_task_ids") or [])
    raw_attempt_numbers = checkpoint.get("task_attempt_numbers") or {}
    task_attempt_numbers: dict[str, int] = (
        {
            clean_text(key): int(value)
            for key, value in raw_attempt_numbers.items()
            if clean_text(key) and int(value) >= 0
        }
        if isinstance(raw_attempt_numbers, Mapping)
        else {}
    )
    prior_statuses = checkpoint.get("statuses") or {}
    statuses: dict[str, str] = (
        {
            clean_text(key): clean_text(value)
            for key, value in prior_statuses.items()
            if clean_text(key) and clean_text(value)
        }
        if isinstance(prior_statuses, Mapping)
        else {}
    )
    if args.resume:
        # A prior resume used to overwrite terminal evidence with the display-
        # only value ``skipped_completed``.  Recover authoritative attempt
        # outcomes before deciding the final run status.
        statuses.update(
            latest_task_summary_statuses(sink.run_directory / "metrics.jsonl")
        )
    failed = False
    boundary_seen = False
    for task in tasks:
        if task.task_id in completed:
            statuses.setdefault(task.task_id, "skipped_completed")
            print(
                f"[physical] skip app={task.app_name} package={task.app_package} "
                f"goal={task.goal_text} status=skipped_completed",
                flush=True,
            )
            continue
        attempt_number = task_attempt_numbers.get(task.task_id, 0) + 1
        task_attempt_numbers[task.task_id] = attempt_number
        attempt_checkpoint = sink.load_checkpoint()
        sink.checkpoint(
            {
                **attempt_checkpoint,
                "task_attempt_numbers": dict(sorted(task_attempt_numbers.items())),
                "updated_at": utc_now(),
            }
        )
        print(
            f"[physical] start app={task.app_name} package={task.app_package} "
            f"goal={task.goal_text}",
            flush=True,
        )
        resume_state = (
            checkpoint.get("state")
            if checkpoint.get("current_task_id") == task.task_id and isinstance(checkpoint.get("state"), Mapping)
            else None
        )
        try:
            status = runner.run_task(task, resume_state=resume_state)
        except (AdbError, ET.ParseError, ValueError, OSError) as error:
            goal_id = sink.register_goal(task)
            runner._failure(
                task,
                goal_id,
                "collector_exception",
                f"{type(error).__name__}: collector operation failed",
            )
            status = f"failed:{type(error).__name__}"
        statuses[task.task_id] = status
        print(
            f"[physical] done app={task.app_name} package={task.app_package} "
            f"goal={task.goal_text} status={status}",
            flush=True,
        )
        record_task_summary(
            sink,
            task,
            status,
            attempt_number=attempt_number,
        )
        failed = failed or status.startswith("failed:")
        boundary_seen = boundary_seen or status.startswith(("boundary:", "stopped:"))
        task_completed = persist_task_result(
            sink,
            task,
            status,
            completed,
            statuses,
            capture_boundary_terminal=(
                args.capture_only and status.startswith("boundary:")
            ),
        )
        if not task_completed:
            # A boundary, budget stop, or failure keeps this exact task as the
            # resumable checkpoint.  Do not launch a later app and silently
            # strand the user-intervention state behind it.
            break
    failed = any(value.startswith("failed:") for value in statuses.values())
    boundary_seen = any(
        value.startswith(("boundary:", "stopped:")) for value in statuses.values()
    )
    all_tasks_complete = {task.task_id for task in tasks}.issubset(completed)
    if all_tasks_complete:
        final_checkpoint = sink.load_checkpoint()
        sink.checkpoint(
            {
                **final_checkpoint,
                "completed_task_ids": sorted(completed),
                "current_task_id": None,
                "current_task": None,
                "state": {},
                "statuses": dict(statuses),
                "updated_at": utc_now(),
            }
        )
    final_status = (
        "failed"
        if failed
        else "completed"
        if args.capture_only and all_tasks_complete
        else "incomplete"
        if boundary_seen
        else "completed"
    )
    sink.finalize(final_status)
    metric_id = f"metric_run_{stable_hash({'run': run_id, 'statuses': statuses}, 20)}"
    sink.append(
        "metric",
        {
            "metric_id": metric_id,
            "metric_dimension": "run_summary",
            "destination_found_success": sum(value == "destination_reached" for value in statuses.values()),
            "user_intervention_count": sum(value.startswith("boundary:") for value in statuses.values()),
            **sink.action_safety_counts(),
            "status_counts": dict(Counter(statuses.values())),
        },
        record_id=metric_id,
    )
    # The metric append may refresh the service-owned control files; restore
    # the final runtime status afterwards.
    sink.finalize(final_status)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "run_directory": str(sink.run_directory),
                "status": final_status,
                "statuses": statuses,
            },
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
