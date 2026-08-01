"""Fail-closed planning of physical-device exploration tasks.

The goal-candidate generator intentionally emits a non-serving research
artifact.  This module is the narrow bridge that turns *applicable* candidates
from one validated capture into safe exploration plans for the same package
version.  It never promotes routes, and it never makes unverified or boundary
candidates executable.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.services.emulator_observation_corpus import (
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_EQUIVALENCE_SHA256,
)
from app.services.real_device_goal_candidates import (
    AUTH_PUBLIC_FAMILIES,
    BASE_PRIORITY,
    FAMILY_SIGNALS,
    GOAL_CANDIDATE_POLICY_SHA256,
    GOAL_CANDIDATE_POLICY_VERSION,
    SENSITIVE_LOCAL_POLICY_VERSION,
    SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES,
    SENSITIVE_SAFE_FAMILIES,
)
from app.services.real_device_action_safety import (
    ACTION_GUARD_EVALUATION_PHASE,
    ACTION_GUARD_POLICY_VERSION,
)


PROVENANCE = "real_device_observation_candidate"
REVIEW_STATUS = "unreviewed_candidate"
ROUTE_LIFECYCLE = "shadow"
EXPECTED_SERIAL = "R3CY204GDVE"
CORE_ARTIFACT_FILENAMES = (
    "manifest.json",
    "checkpoint.json",
    "corpus.sqlite",
    "graph-candidate.sqlite",
    "observations.jsonl",
    "screens.jsonl",
)
PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
MACHINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
TERMINAL_POLICIES = frozenset(
    {"navigation_only", "user_boundary", "user_final_action", "mixed_user_owned"}
)
APPLICABILITY_STATES = frozenset(
    {"applicable", "not_applicable", "authentication_boundary", "unverified"}
)
_METADATA_SCREEN_FORBIDDEN = (
    "title_text",
    "visible_texts",
    "content_descriptions",
    "resource_ids",
    "prerequisite",
    "prerequisites",
    "screenshot_path",
    "accessibility_tree_path",
)
_METADATA_ELEMENT_FORBIDDEN = (
    "text",
    "content_description",
    "inferred_label",
    "label",
    "resource_id",
    "semantic_function_id",
    "synonyms",
    "expected_result",
    "expected_outcome",
    "evidence",
)
_LOCAL_SIGNAL_FIELDS = frozenset(
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
_GUARD_FIELDS = frozenset(
    {
        "policy_version",
        "evaluation_phase",
        "action_type",
        "allowed",
        "computed_final_or_consequential",
        "safe_menu_match",
        "reason",
    }
)
_SIGNAL_METRIC_REQUIRED = frozenset(
    {
        "metric_id",
        "metric_dimension",
        "policy_event",
        "app_package",
        "goal_id",
        "screen_id",
        "local_signal_evidence",
        "external_api_transfer_count",
        "human_text_persisted",
    }
)
_SIGNAL_METRIC_ALLOWED = _SIGNAL_METRIC_REQUIRED | {
    "run_id",
    "provenance",
    "dataset_role",
    "review_status",
    "route_lifecycle",
    "canonical_mutation_allowed",
    "raw_artifacts_persisted",
    "recorded_at",
}


class GoalTaskPlanningError(ValueError):
    """The candidate artifact cannot safely drive physical exploration."""


@dataclass(frozen=True)
class PlannedGoal:
    app_package: str
    version_name: str | None
    version_code: str | None
    version_key: str
    sensitivity_categories: tuple[str, ...]
    sensitivity_handling: str
    candidate_id: str
    family_id: str
    goal_text: str
    terminal_policy: str
    rank: int
    confidence: float
    source_run_id: str
    source_inventory_snapshot_id: str


@dataclass(frozen=True)
class GoalTaskPlan:
    source_run_id: str
    source_inventory_snapshot_id: str
    source_artifact_sha256: str
    applicable: tuple[PlannedGoal, ...]
    state_counts: Mapping[str, int]


def _json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoalTaskPlanningError(code) from error
    if not isinstance(value, dict):
        raise GoalTaskPlanningError(code)
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _machine_id(value: object, code: str) -> str:
    text = str(value or "").strip()
    if not MACHINE_ID_RE.fullmatch(text):
        raise GoalTaskPlanningError(code)
    return text


def _governance(
    value: Mapping[str, Any],
    *,
    serving_field: bool = False,
    require_dataset_role: bool = True,
) -> bool:
    valid = (
        value.get("provenance") == PROVENANCE
        and value.get("review_status") == REVIEW_STATUS
        and value.get("route_lifecycle") == ROUTE_LIFECYCLE
    )
    if require_dataset_role:
        valid = valid and value.get("dataset_role") == PROVENANCE
    if serving_field:
        valid = valid and value.get("serving_allowed") is False
    return valid


def _catalog_is_frozen(value: object) -> bool:
    return isinstance(value, Mapping) and (
        str(value.get("version")) == CANONICAL_CATALOG_VERSION
        and value.get("sha256") == CANONICAL_CATALOG_SHA256
        and value.get("equivalence_sha256") == CANONICAL_EQUIVALENCE_SHA256
        and value.get("mutation_allowed") is False
    )


def _load_family_labels(path: Path) -> dict[str, tuple[str, str]]:
    document = _json(path, "family_manifest_invalid")
    result: dict[str, tuple[str, str]] = {}
    rows: list[object] = []
    for key in ("required_goal_families", "supplemental_goal_families"):
        value = document.get(key)
        if not isinstance(value, list):
            raise GoalTaskPlanningError("family_manifest_invalid")
        rows.extend(value)
    for row in rows:
        if not isinstance(row, Mapping):
            raise GoalTaskPlanningError("family_manifest_invalid")
        family_id = str(row.get("family_id") or "").strip()
        label = str(row.get("label_ko") or "").strip()
        terminal_policy = str(row.get("terminal_policy") or "").strip()
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]*", family_id)
            or not label
            or terminal_policy not in TERMINAL_POLICIES
            or family_id in result
        ):
            raise GoalTaskPlanningError("family_manifest_invalid")
        result[family_id] = (label, terminal_policy)
    return result


def _inventory_records(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows = snapshot.get("included_apps")
    if not isinstance(rows, list) or not rows:
        raise GoalTaskPlanningError("inventory_apps_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise GoalTaskPlanningError("inventory_apps_invalid")
        package = str(row.get("package") or "").strip()
        categories = row.get("sensitivity_categories")
        if (
            not PACKAGE_RE.fullmatch(package)
            or row.get("included") is not True
            or not isinstance(categories, list)
            or any(not isinstance(item, str) for item in categories)
            or package in result
        ):
            raise GoalTaskPlanningError("inventory_apps_invalid")
        version_name = str(row.get("version_name") or "").strip() or None
        version_code = str(row.get("version_code") or "").strip() or None
        expected_key = f"code:{version_code or 'unknown'}|name:{version_name or 'unknown'}"
        if row.get("version_key") != expected_key:
            raise GoalTaskPlanningError("inventory_version_invalid")
        result[package] = {
            "version_name": version_name,
            "version_code": version_code,
            "version_key": expected_key,
            "sensitivity_categories": tuple(sorted(set(categories))),
            "sensitivity_handling": str(row.get("sensitivity_handling") or ""),
        }
    return result


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _nonempty(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _sqlite_payload_rows(
    connection: sqlite3.Connection, table: str
) -> list[tuple[int, dict[str, Any]]]:
    try:
        rows = connection.execute(
            f'SELECT event_sequence, payload_json FROM "{table}" ORDER BY event_sequence'
        ).fetchall()
    except sqlite3.Error as error:
        raise GoalTaskPlanningError(f"sensitive_replay_table_invalid:{table}") from error
    result: list[tuple[int, dict[str, Any]]] = []
    previous = 0
    for raw_sequence, raw_payload in rows:
        if type(raw_sequence) is not int or raw_sequence <= previous:
            raise GoalTaskPlanningError(
                f"sensitive_replay_event_sequence_invalid:{table}"
            )
        previous = raw_sequence
        try:
            payload = json.loads(str(raw_payload))
        except json.JSONDecodeError as error:
            raise GoalTaskPlanningError(
                f"sensitive_replay_payload_invalid:{table}"
            ) from error
        if not isinstance(payload, dict):
            raise GoalTaskPlanningError(f"sensitive_replay_payload_invalid:{table}")
        result.append((raw_sequence, payload))
    return result


def _replay_sensitive_evidence(
    corpus_path: Path,
    inventory: Mapping[str, Mapping[str, Any]],
    families: Mapping[str, tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """Independently replay label-free events from the hashed source corpus."""

    sensitive_packages = {
        package
        for package, record in inventory.items()
        if tuple(record.get("sensitivity_categories") or ())
    }
    if not sensitive_packages:
        return {}
    try:
        connection = sqlite3.connect(
            f"file:{corpus_path.resolve().as_posix()}?mode=ro", uri=True
        )
    except sqlite3.Error as error:
        raise GoalTaskPlanningError("sensitive_replay_corpus_open_failed") from error
    try:
        screens = _sqlite_payload_rows(connection, "screens")
        elements = _sqlite_payload_rows(connection, "elements")
        metrics = _sqlite_payload_rows(connection, "metrics")
    finally:
        connection.close()

    screen_package: dict[str, str] = {}
    auth_boundary: dict[str, bool] = {package: False for package in sensitive_packages}
    for _sequence, screen in screens:
        package = str(screen.get("app_package") or "").strip()
        if package not in sensitive_packages:
            continue
        screen_id = _machine_id(screen.get("screen_id"), "sensitive_replay_screen_invalid")
        if screen_id in screen_package:
            raise GoalTaskPlanningError("sensitive_replay_screen_duplicate")
        if (
            str(screen.get("evidence_mode") or "").casefold() != "metadata_only"
            or screen.get("privacy_verified") is not False
            or any(_nonempty(screen.get(field)) for field in _METADATA_SCREEN_FORBIDDEN)
        ):
            raise GoalTaskPlanningError("sensitive_replay_screen_not_metadata_only")
        screen_package[screen_id] = package
        auth_boundary[package] = auth_boundary[package] or (
            str(screen.get("login_state") or "").casefold() == "boundary"
        )

    local_elements: dict[str, set[str]] = {screen_id: set() for screen_id in screen_package}
    for _sequence, element in elements:
        screen_id = str(element.get("screen_id") or "").strip()
        if screen_id not in screen_package:
            continue
        local_id = str(element.get("ui_element_id") or "").strip()
        record_id = str(element.get("element_id") or "").strip()
        bounds = element.get("bounds")
        if (
            not re.fullmatch(r"adb_[0-9a-f]{8,64}", local_id)
            or record_id != f"{screen_id}:{local_id}"
            or any(_nonempty(element.get(field)) for field in _METADATA_ELEMENT_FORBIDDEN)
            or element.get("privacy_verified") is not False
            or str(element.get("evidence_mode") or "").casefold() != "metadata_only"
            or element.get("clickable") is not True
            or element.get("enabled") is not True
            or element.get("visible") is not True
            or not isinstance(bounds, list)
            or len(bounds) != 4
            or any(type(value) is not int for value in bounds)
        ):
            raise GoalTaskPlanningError("sensitive_replay_element_invalid")
        local_elements[screen_id].add(local_id)

    refs_by_package: dict[str, list[dict[str, Any]]] = {
        package: [] for package in sensitive_packages
    }
    for event_sequence, metric in metrics:
        if str(metric.get("metric_dimension") or "") != "sensitive_local_goal_signal":
            continue
        fields = set(metric)
        if (
            not _SIGNAL_METRIC_REQUIRED.issubset(fields)
            or not fields.issubset(_SIGNAL_METRIC_ALLOWED)
            or metric.get("policy_event") != "label_free_goal_signal_observed"
            or metric.get("external_api_transfer_count") != 0
            or metric.get("human_text_persisted") is not False
        ):
            raise GoalTaskPlanningError("sensitive_replay_metric_invalid")
        package = str(metric.get("app_package") or "").strip()
        screen_id = _machine_id(
            metric.get("screen_id"), "sensitive_replay_metric_screen_invalid"
        )
        metric_id = _machine_id(
            metric.get("metric_id"), "sensitive_replay_metric_id_invalid"
        )
        _machine_id(metric.get("goal_id"), "sensitive_replay_goal_id_invalid")
        if package not in sensitive_packages or screen_package.get(screen_id) != package:
            raise GoalTaskPlanningError("sensitive_replay_metric_source_invalid")
        evidence = metric.get("local_signal_evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != _LOCAL_SIGNAL_FIELDS:
            raise GoalTaskPlanningError("sensitive_replay_evidence_shape_invalid")
        if (
            evidence.get("policy_version") != SENSITIVE_LOCAL_POLICY_VERSION
            or evidence.get("decision_source")
            != "deterministic_local_transient_accessibility"
            or evidence.get("external_api_transfer_count") != 0
            or evidence.get("human_text_persisted") is not False
        ):
            raise GoalTaskPlanningError("sensitive_replay_evidence_policy_invalid")
        family_id = str(evidence.get("family_id") or "").strip()
        signal_ids = evidence.get("matched_signal_ids")
        allowed_signal_ids = {
            signal.signal_id for signal in FAMILY_SIGNALS.get(family_id, ())
        }
        if (
            family_id not in families
            or family_id not in SENSITIVE_SAFE_FAMILIES
            or not isinstance(signal_ids, list)
            or not signal_ids
            or any(not isinstance(value, str) for value in signal_ids)
            or signal_ids != sorted(set(signal_ids))
            or not set(signal_ids).issubset(allowed_signal_ids)
        ):
            raise GoalTaskPlanningError("sensitive_replay_signal_allowlist_invalid")
        element_id = str(evidence.get("selected_element_id") or "").strip()
        commitment = str(evidence.get("semantic_commitment_sha256") or "")
        expected_terminal = (
            "user_boundary"
            if family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
            else "manifest_governed"
        )
        control_bucket = str(evidence.get("control_bucket") or "")
        if (
            element_id not in local_elements.get(screen_id, set())
            or not re.fullmatch(r"[0-9a-f]{64}", commitment)
            or evidence.get("terminal_policy") != expected_terminal
            or control_bucket
            not in {"clickable", "checkable", "password", "text_field"}
        ):
            raise GoalTaskPlanningError("sensitive_replay_source_commitment_invalid")
        guard = evidence.get("action_guard")
        if not isinstance(guard, Mapping) or set(guard) != _GUARD_FIELDS:
            raise GoalTaskPlanningError("sensitive_replay_guard_invalid")
        allowed = guard.get("allowed")
        final = guard.get("computed_final_or_consequential")
        safe_menu = guard.get("safe_menu_match")
        expected_auto = bool(allowed and control_bucket == "clickable")
        if (
            guard.get("policy_version") != ACTION_GUARD_POLICY_VERSION
            or guard.get("evaluation_phase") != ACTION_GUARD_EVALUATION_PHASE
            or guard.get("action_type") != "click"
            or type(allowed) is not bool
            or type(final) is not bool
            or type(safe_menu) is not bool
            or not isinstance(guard.get("reason"), str)
            or (allowed and (final or not safe_menu or guard.get("reason") != "physical_safe_menu_navigation"))
            or (final and (allowed or guard.get("reason") != "final_or_consequential_action"))
            or (
                not allowed
                and not final
                and guard.get("reason") != "not_a_safe_menu_or_setting"
            )
            or evidence.get("auto_navigation_allowed") is not expected_auto
        ):
            raise GoalTaskPlanningError("sensitive_replay_guard_invalid")
        refs_by_package[package].append(
            {
                "source_metric_id": metric_id,
                "source_event_sequence": event_sequence,
                "source_metric_payload_sha256": _canonical_sha256(metric),
                "source_screen_id": screen_id,
                "source_element_id": element_id,
                "policy_version": SENSITIVE_LOCAL_POLICY_VERSION,
                "family_id": family_id,
                "signal_ids": list(signal_ids),
                "semantic_commitment_sha256": commitment,
                "action_guard_sha256": _canonical_sha256(dict(guard)),
                "terminal_policy": expected_terminal,
                "control_bucket": control_bucket,
                "auto_navigation_allowed": expected_auto,
            }
        )

    result: dict[str, dict[str, Any]] = {}
    for package in sorted(sensitive_packages):
        refs = sorted(
            refs_by_package[package],
            key=lambda value: (
                int(value["source_event_sequence"]),
                str(value["source_metric_id"]),
                str(value["family_id"]),
                str(value["source_element_id"]),
            ),
        )
        event_refs = [
            {
                "source_metric_id": value["source_metric_id"],
                "source_event_sequence": value["source_event_sequence"],
                "source_metric_payload_sha256": value[
                    "source_metric_payload_sha256"
                ],
            }
            for value in refs
        ]
        result[package] = {
            "refs": refs,
            "auth_boundary": auth_boundary[package],
            "attestation": {
                "schema_version": 1,
                "policy_version": SENSITIVE_LOCAL_POLICY_VERSION,
                "source_event_count": len(refs),
                "ordered_event_refs": event_refs,
                "evidence_root_sha256": _canonical_sha256(refs),
                "external_api_transfer_count": 0,
                "human_text_persisted": False,
            },
        }
    return result


def _expected_sensitive_candidates(
    *,
    package: str,
    version_key: str,
    families: Mapping[str, tuple[str, str]],
    replay: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    refs = list(replay.get("refs") or [])
    auth_boundary = replay.get("auth_boundary") is True
    expected: dict[str, dict[str, Any]] = {}
    for family_id, (_label, manifest_terminal) in families.items():
        family_refs = [value for value in refs if value.get("family_id") == family_id]
        family_refs.sort(
            key=lambda value: (
                int(value["source_event_sequence"]),
                str(value["source_metric_id"]),
                str(value["source_element_id"]),
            )
        )
        allowed_weights = {
            signal.signal_id: signal.weight
            for signal in FAMILY_SIGNALS.get(family_id, ())
        }
        signal_ids = sorted(
            {
                signal_id
                for value in family_refs
                for signal_id in value.get("signal_ids", [])
            }
        )
        if family_id not in SENSITIVE_SAFE_FAMILIES:
            state = "unverified"
            confidence = 0.0
            restriction = "sensitive_scope_forbidden"
            family_refs = []
            signal_ids = []
        elif family_refs:
            state = "applicable"
            confidence = min(1.0, max(allowed_weights[value] for value in signal_ids))
            restriction = None
        elif auth_boundary and family_id not in AUTH_PUBLIC_FAMILIES:
            state = "authentication_boundary"
            confidence = 1.0
            restriction = "authentication_required"
        else:
            state = "unverified"
            confidence = 0.0
            restriction = "metadata_only_no_semantic_inference"
        terminal_policy = (
            "user_boundary"
            if family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
            else manifest_terminal
        )
        expected[family_id] = {
            "candidate_id": "goal_"
            + _canonical_sha256(
                {
                    "package": package,
                    "version_key": version_key,
                    "family_id": family_id,
                }
            )[:24],
            "applicability_state": state,
            "confidence": round(confidence, 4),
            "terminal_policy": terminal_policy,
            "terminal_action_owner": (
                "user"
                if terminal_policy
                in {"user_boundary", "user_final_action", "mixed_user_owned"}
                else "navigation_only"
            ),
            "evidence_signal_ids": signal_ids,
            "source_screen_ids": sorted(
                {str(value["source_screen_id"]) for value in family_refs}
            ),
            "source_element_ids": sorted(
                {str(value["source_element_id"]) for value in family_refs}
            ),
            "local_signal_evidence_count": len(family_refs),
            "sensitive_evidence_refs": family_refs,
            "evidence_source_mode": (
                "sensitive_local_signal_ids" if family_refs else "none"
            ),
            "restriction_reason_code": restriction,
        }
    state_order = {
        "applicable": 0,
        "authentication_boundary": 1,
        "not_applicable": 2,
        "unverified": 3,
    }
    ordered = sorted(
        expected,
        key=lambda family_id: (
            state_order[expected[family_id]["applicability_state"]],
            -float(expected[family_id]["confidence"]),
            BASE_PRIORITY.get(family_id, 10_000),
            family_id,
        ),
    )
    for rank, family_id in enumerate(ordered, 1):
        expected[family_id]["rank"] = rank
    return expected


def _verify_source_hashes(
    artifact: Mapping[str, Any],
    *,
    run_directory: Path,
    inventory_snapshot_path: Path,
    family_manifest_path: Path,
) -> None:
    expected_paths = {
        "manifest": run_directory / "manifest.json",
        "checkpoint": run_directory / "checkpoint.json",
        "corpus": run_directory / "corpus.sqlite",
        "graph": run_directory / "graph-candidate.sqlite",
        "snapshot": inventory_snapshot_path,
        "family_manifest": family_manifest_path,
    }
    declared = artifact.get("source_sha256")
    if not isinstance(declared, Mapping) or set(declared) != set(expected_paths):
        raise GoalTaskPlanningError("source_hash_manifest_invalid")
    for label, path in expected_paths.items():
        if not path.is_file() or path.is_symlink():
            raise GoalTaskPlanningError(f"source_missing:{label}")
        if declared.get(label) != _sha256(path):
            raise GoalTaskPlanningError(f"source_hash_mismatch:{label}")


def _verify_validated_marker(
    run_directory: Path,
    source_run_id: str,
    artifact_source_hashes: object,
) -> None:
    marker_path = run_directory / "VALIDATED.json"
    marker = _json(marker_path, "validated_marker_missing_or_invalid")
    core_hashes = marker.get("core_artifact_sha256")
    if (
        marker.get("schema_version") != 1
        or marker.get("status") != "passed"
        or marker.get("run_id") != source_run_id
        or marker.get("provenance") != PROVENANCE
        or marker.get("device_serial") != EXPECTED_SERIAL
        or marker.get("is_emulator") is not False
        or not isinstance(core_hashes, Mapping)
        or set(core_hashes) != set(CORE_ARTIFACT_FILENAMES)
        or marker.get("manifest_sha256") != core_hashes.get("manifest.json")
        or marker.get("screens_sha256") != core_hashes.get("screens.jsonl")
        or not isinstance(artifact_source_hashes, Mapping)
    ):
        raise GoalTaskPlanningError("validated_marker_mismatch")
    for filename in CORE_ARTIFACT_FILENAMES:
        path = run_directory / filename
        expected = core_hashes.get(filename)
        if (
            not path.is_file()
            or path.is_symlink()
            or not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or _sha256(path) != expected
        ):
            raise GoalTaskPlanningError("validated_marker_mismatch")
    for artifact_label, filename in (
        ("manifest", "manifest.json"),
        ("checkpoint", "checkpoint.json"),
        ("corpus", "corpus.sqlite"),
        ("graph", "graph-candidate.sqlite"),
    ):
        if artifact_source_hashes.get(artifact_label) != core_hashes[filename]:
            raise GoalTaskPlanningError("validated_marker_source_mismatch")


def plan_applicable_goals(
    artifact_path: Path | str,
    inventory_snapshot_path: Path | str,
    family_manifest_path: Path | str,
    *,
    only_packages: Sequence[str] = (),
    max_goals_per_app: int = 0,
) -> GoalTaskPlan:
    """Return only independently attested, applicable goal plans.

    The candidate artifact must live inside its source run.  Every hashed
    source and the validator marker are rechecked, so copying a candidate file
    beside another run or editing any source fails closed.
    """

    artifact_path = Path(artifact_path).expanduser()
    inventory_snapshot_path = Path(inventory_snapshot_path).expanduser()
    family_manifest_path = Path(family_manifest_path).expanduser()
    for path in (artifact_path, inventory_snapshot_path, family_manifest_path):
        if path.is_symlink():
            raise GoalTaskPlanningError("symlink_source_forbidden")
    artifact_path = artifact_path.resolve()
    inventory_snapshot_path = inventory_snapshot_path.resolve()
    family_manifest_path = family_manifest_path.resolve()
    if not artifact_path.is_file():
        raise GoalTaskPlanningError("goal_artifact_missing")
    run_directory = artifact_path.parent
    if not run_directory.is_dir() or run_directory.is_symlink():
        raise GoalTaskPlanningError("source_run_invalid")

    artifact = _json(artifact_path, "goal_artifact_invalid")
    required_goal_policy = {
        "version": GOAL_CANDIDATE_POLICY_VERSION,
        "sha256": GOAL_CANDIDATE_POLICY_SHA256,
    }
    if (
        artifact.get("schema_version") != 1
        or artifact.get("artifact_type") != "dynamic_real_device_goal_candidates"
        or not _governance(artifact, serving_field=True)
        or artifact.get("human_review_required") is not True
        or not _catalog_is_frozen(artifact.get("canonical_catalog"))
        or artifact.get("goal_candidate_policy") != required_goal_policy
    ):
        raise GoalTaskPlanningError("goal_artifact_governance_invalid")
    policy = artifact.get("version_policy")
    if not isinstance(policy, Mapping) or (
        policy.get("canonical") != "V15_frozen"
        or policy.get("v16_v20_promotion") != "forbidden"
        or policy.get("v21") != "research_only_noncanonical"
        or policy.get("v22_plus") != "forbidden"
    ):
        raise GoalTaskPlanningError("goal_artifact_version_policy_invalid")
    safety = artifact.get("safety")
    if not isinstance(safety, Mapping) or (
        int(safety.get("unsafe_auto_click_count", -1)) != 0
        or int(safety.get("final_action_auto_click_count", -1)) != 0
        or safety.get("terminal_actions_owned_by_user") is not True
    ):
        raise GoalTaskPlanningError("goal_artifact_safety_invalid")

    source_run_id = _machine_id(artifact.get("source_run_id"), "source_run_id_invalid")
    snapshot_id = _machine_id(
        artifact.get("source_inventory_snapshot_id"),
        "source_inventory_snapshot_id_invalid",
    )
    _verify_source_hashes(
        artifact,
        run_directory=run_directory,
        inventory_snapshot_path=inventory_snapshot_path,
        family_manifest_path=family_manifest_path,
    )
    _verify_validated_marker(
        run_directory,
        source_run_id,
        artifact.get("source_sha256"),
    )

    manifest = _json(run_directory / "manifest.json", "source_manifest_invalid")
    snapshot = _json(inventory_snapshot_path, "inventory_snapshot_invalid")
    if (
        manifest.get("run_id") != source_run_id
        or manifest.get("status") != "completed"
        or manifest.get("validation_profile") != "dynamic_inventory"
        or manifest.get("collection_mode") not in {"capture_only", "safe_explore"}
        or not _governance(manifest)
        or manifest.get("canonical_mutation_allowed") is not False
        or manifest.get("is_emulator") is not False
        or manifest.get("device_serial") != EXPECTED_SERIAL
    ):
        raise GoalTaskPlanningError("source_manifest_governance_invalid")
    manifest_safety = manifest.get("safety")
    if not isinstance(manifest_safety, Mapping) or (
        int(manifest_safety.get("unsafe_auto_click_count", -1)) != 0
        or int(manifest_safety.get("final_action_auto_click_count", -1)) != 0
    ):
        raise GoalTaskPlanningError("source_manifest_safety_invalid")
    if (
        snapshot.get("snapshot_id") != snapshot_id
        or snapshot.get("schema_version") != 1
        or not _governance(snapshot)
        or snapshot.get("canonical_catalog_mutation") is not False
        or not isinstance(snapshot.get("device"), Mapping)
        or snapshot["device"].get("serial") != EXPECTED_SERIAL
        or snapshot["device"].get("is_emulator") is not False
    ):
        raise GoalTaskPlanningError("inventory_snapshot_governance_invalid")
    snapshot_catalog = snapshot.get("canonical_catalog")
    if not isinstance(snapshot_catalog, Mapping) or (
        str(snapshot_catalog.get("version")) != CANONICAL_CATALOG_VERSION
        or snapshot_catalog.get("sha256") != CANONICAL_CATALOG_SHA256
        or snapshot_catalog.get("equivalence_sha256") != CANONICAL_EQUIVALENCE_SHA256
    ):
        raise GoalTaskPlanningError("inventory_snapshot_catalog_invalid")

    inventory = _inventory_records(snapshot)
    raw_selected_packages = manifest.get("selected_packages")
    if not isinstance(raw_selected_packages, list) or not raw_selected_packages:
        raise GoalTaskPlanningError("source_manifest_selected_packages_invalid")
    selected_packages = {
        str(value).strip() for value in raw_selected_packages if str(value).strip()
    }
    if (
        len(selected_packages) != len(raw_selected_packages)
        or raw_selected_packages != sorted(selected_packages)
        or any(not PACKAGE_RE.fullmatch(package) for package in selected_packages)
        or not selected_packages.issubset(inventory)
    ):
        raise GoalTaskPlanningError("source_manifest_selected_packages_invalid")
    selected_inventory = {
        package: inventory[package] for package in sorted(selected_packages)
    }
    families = _load_family_labels(family_manifest_path)
    has_sensitive_apps = any(
        tuple(record["sensitivity_categories"])
        for record in selected_inventory.values()
    )
    evidence_policy = artifact.get("evidence_policy")
    if not isinstance(evidence_policy, Mapping) or (
        evidence_policy.get("goal_candidate_policy_version")
        != GOAL_CANDIDATE_POLICY_VERSION
        or evidence_policy.get("goal_candidate_policy_sha256")
        != GOAL_CANDIDATE_POLICY_SHA256
    ):
        raise GoalTaskPlanningError("goal_artifact_policy_stale")
    if has_sensitive_apps:
        if (
            evidence_policy.get("metadata_only_semantics_used") != 0
            or evidence_policy.get("sensitive_local_policy_version")
            != SENSITIVE_LOCAL_POLICY_VERSION
            or evidence_policy.get("raw_xml_read") is not False
            or evidence_policy.get("raw_screenshot_read") is not False
        ):
            raise GoalTaskPlanningError("sensitive_evidence_policy_invalid")
    sensitive_replay = _replay_sensitive_evidence(
        run_directory / "corpus.sqlite", selected_inventory, families
    )
    requested = {str(value).strip() for value in only_packages if str(value).strip()}
    if not requested.issubset(selected_packages):
        raise GoalTaskPlanningError("requested_package_outside_inventory")

    raw_apps = artifact.get("apps")
    if not isinstance(raw_apps, list) or not raw_apps:
        raise GoalTaskPlanningError("goal_artifact_apps_invalid")
    state_counts: dict[str, int] = {}
    plans: list[PlannedGoal] = []
    seen_packages: set[str] = set()
    seen_candidates: set[str] = set()
    for app in raw_apps:
        if not isinstance(app, Mapping):
            raise GoalTaskPlanningError("goal_artifact_apps_invalid")
        package = str(app.get("app_package") or "").strip()
        if package not in selected_packages or package in seen_packages:
            raise GoalTaskPlanningError("goal_artifact_app_inventory_mismatch")
        seen_packages.add(package)
        inv = inventory[package]
        categories = tuple(sorted(app.get("sensitivity_categories") or ()))
        if (
            app.get("version_name") != inv["version_name"]
            or app.get("version_code") != inv["version_code"]
            or app.get("version_key") != inv["version_key"]
            or categories != inv["sensitivity_categories"]
            or app.get("goal_candidate_policy") != required_goal_policy
            or not _governance(
                app, serving_field=True, require_dataset_role=False
            )
        ):
            raise GoalTaskPlanningError("goal_artifact_app_version_or_governance_mismatch")
        expected_sensitive: dict[str, dict[str, Any]] | None = None
        if categories:
            replay = sensitive_replay.get(package)
            hermes = app.get("hermes_k_exaone")
            if (
                not isinstance(replay, Mapping)
                or app.get("sensitive_scope_policy_applied") is not True
                or app.get("sensitive_evidence_attestation")
                != replay.get("attestation")
                or not isinstance(hermes, Mapping)
                or hermes.get("attempted") is not False
                or hermes.get("used") is not False
                or hermes.get("external_api_transfer_count") != 0
                or hermes.get("raw_menu_semantics_sent") is not False
                or hermes.get("request_semantics") != "none_sensitive_local_only"
            ):
                raise GoalTaskPlanningError("sensitive_evidence_attestation_mismatch")
            expected_sensitive = _expected_sensitive_candidates(
                package=package,
                version_key=inv["version_key"],
                families=families,
                replay=replay,
            )
        elif app.get("sensitive_evidence_attestation") is not None:
            raise GoalTaskPlanningError("nonsensitive_evidence_attestation_forbidden")
        candidates = app.get("goal_candidates")
        if not isinstance(candidates, list) or app.get("human_review_required") is not True:
            raise GoalTaskPlanningError("goal_candidate_list_invalid")
        applicable_for_app: list[PlannedGoal] = []
        seen_families: set[str] = set()
        seen_ranks: set[int] = set()
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise GoalTaskPlanningError("goal_candidate_invalid")
            state = str(candidate.get("applicability_state") or "")
            if state not in APPLICABILITY_STATES:
                raise GoalTaskPlanningError("goal_candidate_state_invalid")
            state_counts[state] = state_counts.get(state, 0) + 1
            candidate_id = _machine_id(
                candidate.get("candidate_id"), "goal_candidate_id_invalid"
            )
            if candidate_id in seen_candidates:
                raise GoalTaskPlanningError("goal_candidate_duplicate")
            seen_candidates.add(candidate_id)
            family_id = str(candidate.get("family_id") or "").strip()
            if family_id not in families or family_id in seen_families:
                raise GoalTaskPlanningError("goal_candidate_family_unknown")
            seen_families.add(family_id)
            if expected_sensitive is not None:
                expected = expected_sensitive[family_id]
                exact_fields = (
                    "candidate_id",
                    "applicability_state",
                    "confidence",
                    "terminal_policy",
                    "terminal_action_owner",
                    "evidence_signal_ids",
                    "source_screen_ids",
                    "source_element_ids",
                    "local_signal_evidence_count",
                    "sensitive_evidence_refs",
                    "evidence_source_mode",
                    "restriction_reason_code",
                    "rank",
                )
                if any(candidate.get(field) != expected[field] for field in exact_fields):
                    raise GoalTaskPlanningError(
                        "sensitive_candidate_replay_mismatch"
                    )
            label, expected_terminal = families[family_id]
            if categories and family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES:
                expected_terminal = "user_boundary"
            terminal_policy = str(candidate.get("terminal_policy") or "")
            if (
                terminal_policy != expected_terminal
                or candidate.get("final_action_auto_click_allowed") is not False
                or candidate.get("unsafe_action_auto_click_allowed") is not False
                or not _governance(
                    candidate, serving_field=True, require_dataset_role=False
                )
                or candidate.get("human_review_required") is not True
            ):
                raise GoalTaskPlanningError("goal_candidate_safety_or_governance_invalid")
            if state != "applicable":
                continue
            if categories and family_id not in SENSITIVE_SAFE_FAMILIES:
                raise GoalTaskPlanningError("sensitive_applicable_family_forbidden")
            rank = candidate.get("rank")
            confidence = candidate.get("confidence")
            if (
                not isinstance(rank, int)
                or isinstance(rank, bool)
                or rank < 1
                or rank in seen_ranks
                or not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise GoalTaskPlanningError("goal_candidate_rank_or_confidence_invalid")
            seen_ranks.add(rank)
            if requested and package not in requested:
                continue
            applicable_for_app.append(
                PlannedGoal(
                    app_package=package,
                    version_name=inv["version_name"],
                    version_code=inv["version_code"],
                    version_key=inv["version_key"],
                    sensitivity_categories=categories,
                    sensitivity_handling=inv["sensitivity_handling"],
                    candidate_id=candidate_id,
                    family_id=family_id,
                    goal_text=label,
                    terminal_policy=terminal_policy,
                    rank=rank,
                    confidence=float(confidence),
                    source_run_id=source_run_id,
                    source_inventory_snapshot_id=snapshot_id,
                )
            )
        applicable_for_app.sort(key=lambda item: (item.rank, item.family_id))
        if seen_families != set(families):
            raise GoalTaskPlanningError("goal_candidate_family_set_mismatch")
        plans.extend(applicable_for_app[: max_goals_per_app or None])

    declared_counts = artifact.get("counts")
    if seen_packages != selected_packages:
        raise GoalTaskPlanningError("goal_artifact_app_set_mismatch")
    if not isinstance(declared_counts, Mapping) or (
        int(declared_counts.get("inventory_app_count", -1)) != len(inventory)
        or int(declared_counts.get("selected_app_count", -1)) != len(raw_apps)
        or int(declared_counts.get("candidate_count", -1)) != sum(state_counts.values())
        or dict(declared_counts.get("applicability_states") or {}) != state_counts
    ):
        raise GoalTaskPlanningError("goal_artifact_counts_mismatch")
    if not plans:
        raise GoalTaskPlanningError("no_applicable_goal_candidates")
    plans.sort(key=lambda item: (item.app_package, item.rank, item.family_id))
    return GoalTaskPlan(
        source_run_id=source_run_id,
        source_inventory_snapshot_id=snapshot_id,
        source_artifact_sha256=_sha256(artifact_path),
        applicable=tuple(plans),
        state_counts=dict(sorted(state_counts.items())),
    )
