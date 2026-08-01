from __future__ import annotations

"""Generate dynamic per-app goal candidates from a validated physical run.

The source run and its exact inventory snapshot are opened read-only.  Only
verified-redacted Accessibility semantics are eligible for deterministic goal
matching; metadata-only screens contribute boundary state and counts only.
"""

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.emulator_observation_corpus import (  # noqa: E402
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_EQUIVALENCE_SHA256,
)
from app.services.real_device_goal_candidates import (  # noqa: E402
    AppEvidence,
    CANONICAL_VERSION,
    FAMILY_SIGNALS,
    GOAL_CANDIDATE_POLICY_SHA256,
    GOAL_CANDIDATE_POLICY_VERSION,
    LocalSignalEvidence,
    PROVENANCE,
    REVIEW_STATUS,
    ROUTE_LIFECYCLE,
    SENSITIVE_LOCAL_POLICY_VERSION,
    SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES,
    SENSITIVE_SAFE_FAMILIES,
    SemanticValue,
    canonical_sha256,
    family_definitions,
    generate_app_candidate_set,
    goal_candidate_policy_attestation,
)
from app.services.real_device_action_safety import (  # noqa: E402
    ACTION_GUARD_EVALUATION_PHASE,
    ACTION_GUARD_POLICY_VERSION,
)
from app.services.real_device_privacy import classify_human_text  # noqa: E402


VALIDATOR_PATH = ROOT / "scripts" / "Validate-RealDeviceObservationCorpus.py"
DEFAULT_OBSERVATION_ROOT = ROOT / ".artifacts" / "navigation-observations"
DEFAULT_FAMILY_MANIFEST = (
    ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"
)
OUTPUT_FILENAME = "goal-candidates.json"
EXPECTED_SERIAL = "R3CY204GDVE"
VALIDATION_ATTESTATION_FILENAME = "VALIDATED.json"
CORE_ARTIFACT_FILENAMES = (
    "manifest.json",
    "checkpoint.json",
    "corpus.sqlite",
    "graph-candidate.sqlite",
    "observations.jsonl",
    "screens.jsonl",
)
SAFE_EVIDENCE_MODES = frozenset(
    {"verified_redacted", "redacted", "verified_evidence", "verified_metadata"}
)
MACHINE_ID_RE = re.compile(r"[A-Za-z0-9_.:+|/-]{1,300}")
PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")

SCREEN_SEMANTIC_FIELDS = (
    "title_text",
    "visible_texts",
    "content_descriptions",
    "resource_ids",
)
METADATA_ONLY_SCREEN_FORBIDDEN_FIELDS = SCREEN_SEMANTIC_FIELDS + (
    "prerequisite",
    "prerequisites",
    "screenshot_path",
    "accessibility_tree_path",
)
ELEMENT_SEMANTIC_FIELDS = (
    "text",
    "content_description",
    "inferred_label",
    "label",
    "resource_id",
)
METADATA_ONLY_ELEMENT_FORBIDDEN_FIELDS = ELEMENT_SEMANTIC_FIELDS + (
    "semantic_function_id",
    "synonyms",
    "expected_result",
    "expected_outcome",
    "evidence",
)
LOCAL_SIGNAL_EVIDENCE_FIELDS = frozenset(
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
ACTION_GUARD_FIELDS = frozenset(
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
SENSITIVE_SIGNAL_METRIC_REQUIRED_FIELDS = frozenset(
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
SENSITIVE_SIGNAL_METRIC_ALLOWED_FIELDS = (
    SENSITIVE_SIGNAL_METRIC_REQUIRED_FIELDS
    | {
        "run_id",
        "provenance",
        "dataset_role",
        "review_status",
        "route_lifecycle",
        "canonical_mutation_allowed",
        "raw_artifacts_persisted",
        "recorded_at",
    }
)


class GoalCandidateBuildError(RuntimeError):
    """A fail-closed eligibility, integrity, or privacy rejection."""


def _load_validator_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "exitguide_real_device_goal_candidate_validator", VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise GoalCandidateBuildError("validator_unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_run(
    run_directory: Path,
    *,
    repo_root: Path,
    app_manifest_path: Path,
    observation_root: Path,
) -> Mapping[str, Any]:
    validator = _load_validator_module()
    return validator.validate_corpus(
        run_directory,
        repo_root=repo_root,
        app_manifest_path=app_manifest_path,
        observation_root=observation_root,
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GoalCandidateBuildError("source_json_invalid") from error
    if not isinstance(value, dict):
        raise GoalCandidateBuildError("source_json_shape_invalid")
    return value


def _validated_core_artifact_hashes(
    run_directory: Path, expected_run_id: str
) -> dict[str, str]:
    """Verify the validator's immutable core-source attestation."""

    marker_path = run_directory / VALIDATION_ATTESTATION_FILENAME
    if not marker_path.is_file() or marker_path.is_symlink():
        raise GoalCandidateBuildError("validation_attestation_invalid")
    marker = _json_file(marker_path)
    declared = marker.get("core_artifact_sha256")
    if (
        marker.get("schema_version") != 1
        or marker.get("status") != "passed"
        or marker.get("run_id") != expected_run_id
        or marker.get("provenance") != PROVENANCE
        or marker.get("device_serial") != EXPECTED_SERIAL
        or marker.get("is_emulator") is not False
        or not isinstance(declared, Mapping)
        or set(declared) != set(CORE_ARTIFACT_FILENAMES)
        or marker.get("manifest_sha256") != declared.get("manifest.json")
        or marker.get("screens_sha256") != declared.get("screens.jsonl")
    ):
        raise GoalCandidateBuildError("validation_attestation_invalid")
    verified: dict[str, str] = {}
    for filename in CORE_ARTIFACT_FILENAMES:
        path = run_directory / filename
        expected = declared.get(filename)
        if (
            not path.is_file()
            or path.is_symlink()
            or not isinstance(expected, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected)
            or _sha256_file(path) != expected
        ):
            raise GoalCandidateBuildError("validation_attestation_invalid")
        verified[filename] = expected
    return verified


def _nonempty(value: Any) -> bool:
    if value is None or value is False or value == "":
        return False
    if isinstance(value, (list, tuple, set, frozenset, dict)):
        return bool(value)
    return True


def _machine_id(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not MACHINE_ID_RE.fullmatch(text):
        raise GoalCandidateBuildError(f"{field}_invalid")
    return text


def _version_key(version_name: Any, version_code: Any) -> str:
    name = str(version_name).strip() if version_name not in {None, ""} else "unknown"
    code = str(version_code).strip() if version_code not in {None, ""} else "unknown"
    return f"code:{code}|name:{name}"


def _snapshot_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GoalCandidateBuildError("inventory_record_invalid")
    package = str(value.get("package") or "").strip()
    if not PACKAGE_RE.fullmatch(package) or value.get("included") is not True:
        raise GoalCandidateBuildError("inventory_record_invalid")
    raw_categories = value.get("sensitivity_categories")
    if (
        not isinstance(raw_categories, list)
        or any(
            not isinstance(item, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]*", item)
            for item in raw_categories
        )
        or len(raw_categories) != len(set(raw_categories))
    ):
        raise GoalCandidateBuildError("inventory_sensitivity_invalid")
    version_name = str(value.get("version_name") or "").strip() or None
    version_code = str(value.get("version_code") or "").strip() or None
    expected_key = _version_key(version_name, version_code)
    if str(value.get("version_key") or "") != expected_key:
        raise GoalCandidateBuildError("inventory_version_key_invalid")
    for field_name, field_value in (
        ("version_name", version_name),
        ("version_code", version_code),
    ):
        if field_value is None:
            continue
        # Package version metadata is structural.  The classifier still blocks
        # embedded secrets in structural contexts while avoiding phone-number
        # false positives on numeric version codes.
        finding = classify_human_text(
            field_value, field_name=field_name, structural=True
        )
        if finding.metadata_only:
            raise GoalCandidateBuildError("inventory_version_privacy_rejected")
    return {
        "package": package,
        "version_name": version_name,
        "version_code": version_code,
        "version_key": expected_key,
        "sensitivity_categories": tuple(sorted(raw_categories)),
    }


def _resolve_pinned_snapshot(
    manifest: Mapping[str, Any], observation_root: Path
) -> Path:
    metadata = manifest.get("inventory_snapshot")
    if not isinstance(metadata, Mapping):
        raise GoalCandidateBuildError("inventory_snapshot_pin_missing")
    raw_path = metadata.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise GoalCandidateBuildError("inventory_snapshot_pin_invalid")
    candidate = Path(raw_path)
    scope = str(metadata.get("path_scope") or "")
    if scope == "observation_root_relative":
        if candidate.is_absolute():
            raise GoalCandidateBuildError("inventory_snapshot_pin_invalid")
        unresolved = observation_root / candidate
        if unresolved.is_symlink():
            raise GoalCandidateBuildError("inventory_snapshot_unavailable")
        resolved = unresolved.resolve()
        if not resolved.is_relative_to(observation_root.resolve()):
            raise GoalCandidateBuildError("inventory_snapshot_pin_escape")
    elif scope == "explicit_safe_file":
        if not candidate.is_absolute() or metadata.get("explicit_safe_file") is not True:
            raise GoalCandidateBuildError("inventory_snapshot_pin_invalid")
        if candidate.is_symlink():
            raise GoalCandidateBuildError("inventory_snapshot_unavailable")
        resolved = candidate.resolve()
    else:
        raise GoalCandidateBuildError("inventory_snapshot_pin_scope_invalid")
    if not resolved.is_file() or resolved.is_symlink():
        raise GoalCandidateBuildError("inventory_snapshot_unavailable")
    return resolved


def _validate_source_identity(
    manifest: Mapping[str, Any], snapshot: Mapping[str, Any], snapshot_path: Path
) -> tuple[str, list[str], dict[str, dict[str, Any]]]:
    if manifest.get("validation_profile") != "dynamic_inventory":
        raise GoalCandidateBuildError("dynamic_inventory_profile_required")
    if manifest.get("status") != "completed":
        raise GoalCandidateBuildError("completed_run_required")
    if (
        manifest.get("provenance") != PROVENANCE
        or manifest.get("dataset_role") != PROVENANCE
        or manifest.get("review_status") != REVIEW_STATUS
        or manifest.get("route_lifecycle") != ROUTE_LIFECYCLE
        or manifest.get("canonical_mutation_allowed") is not False
    ):
        raise GoalCandidateBuildError("run_governance_invalid")
    if (
        str(manifest.get("canonical_catalog_version")) != CANONICAL_CATALOG_VERSION
        or CANONICAL_VERSION != CANONICAL_CATALOG_VERSION
        or manifest.get("canonical_catalog_sha256") != CANONICAL_CATALOG_SHA256
        or manifest.get("canonical_equivalence_sha256") != CANONICAL_EQUIVALENCE_SHA256
    ):
        raise GoalCandidateBuildError("v15_pin_invalid")
    policy = manifest.get("version_policy")
    if not isinstance(policy, Mapping) or (
        policy.get("canonical") != "V15_frozen"
        or policy.get("v16_v20_promotion") != "forbidden"
        or policy.get("v21") != "research_only_noncanonical"
        or policy.get("v22_plus") != "forbidden"
    ):
        raise GoalCandidateBuildError("version_policy_invalid")
    safety = manifest.get("safety")
    if not isinstance(safety, Mapping) or (
        int(safety.get("unsafe_auto_click_count", -1)) != 0
        or int(safety.get("final_action_auto_click_count", -1)) != 0
    ):
        raise GoalCandidateBuildError("source_safety_invariant_invalid")
    if (
        manifest.get("is_emulator") is not False
        or str(manifest.get("device_serial") or "") != EXPECTED_SERIAL
        or str(manifest.get("device_type") or "")
        not in {"physical_android", "physical_device", "android_physical", "physical"}
    ):
        raise GoalCandidateBuildError("physical_device_attestation_invalid")
    if manifest.get("raw_artifacts_persisted") is not False:
        raise GoalCandidateBuildError("raw_artifact_attestation_invalid")
    run_id = _machine_id(manifest.get("run_id"), "run_id")

    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("provenance") != PROVENANCE
        or snapshot.get("dataset_role") != PROVENANCE
        or snapshot.get("review_status") != REVIEW_STATUS
        or snapshot.get("route_lifecycle") != ROUTE_LIFECYCLE
        or snapshot.get("canonical_catalog_mutation") is not False
    ):
        raise GoalCandidateBuildError("snapshot_governance_invalid")
    snapshot_device = snapshot.get("device")
    if not isinstance(snapshot_device, Mapping) or (
        str(snapshot_device.get("serial") or "") != EXPECTED_SERIAL
        or snapshot_device.get("is_emulator") is not False
        or str(snapshot_device.get("device_type") or "")
        not in {"physical_android", "physical_device", "android_physical", "physical"}
    ):
        raise GoalCandidateBuildError("snapshot_device_attestation_invalid")
    snapshot_catalog = snapshot.get("canonical_catalog")
    if not isinstance(snapshot_catalog, Mapping) or (
        str(snapshot_catalog.get("version")) != CANONICAL_CATALOG_VERSION
        or snapshot_catalog.get("sha256") != CANONICAL_CATALOG_SHA256
        or snapshot_catalog.get("equivalence_sha256")
        != CANONICAL_EQUIVALENCE_SHA256
    ):
        raise GoalCandidateBuildError("snapshot_v15_pin_invalid")
    snapshot_id = _machine_id(snapshot.get("snapshot_id"), "snapshot_id")
    metadata = manifest["inventory_snapshot"]
    if metadata.get("snapshot_id") != snapshot_id:
        raise GoalCandidateBuildError("snapshot_id_mismatch")
    actual_snapshot_hash = _sha256_file(snapshot_path)
    if metadata.get("sha256") != actual_snapshot_hash:
        raise GoalCandidateBuildError("snapshot_hash_mismatch")

    raw_apps = snapshot.get("included_apps")
    if not isinstance(raw_apps, list) or not raw_apps:
        raise GoalCandidateBuildError("inventory_empty_or_invalid")
    records = [_snapshot_record(value) for value in raw_apps]
    by_package = {record["package"]: record for record in records}
    if len(by_package) != len(records):
        raise GoalCandidateBuildError("inventory_package_duplicate")
    raw_selected = manifest.get("selected_packages")
    if (
        not isinstance(raw_selected, list)
        or not raw_selected
        or any(not isinstance(value, str) or not value.strip() for value in raw_selected)
    ):
        raise GoalCandidateBuildError("selected_packages_invalid")
    selected = sorted(set(raw_selected))
    if len(selected) != len(raw_selected) or not set(selected).issubset(by_package):
        raise GoalCandidateBuildError("selected_inventory_mismatch")

    pinned_inventory = metadata.get("included_inventory")
    if not isinstance(pinned_inventory, list):
        raise GoalCandidateBuildError("manifest_exact_inventory_missing")
    pinned_records = [_snapshot_record(value) for value in pinned_inventory]
    pinned_by_package = {record["package"]: record for record in pinned_records}
    if pinned_by_package != by_package:
        raise GoalCandidateBuildError("manifest_exact_inventory_mismatch")
    return run_id, selected, by_package


def _privacy_safe_semantic(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "[REDACTED]":
        return None
    finding = classify_human_text(text, field_name=field, path=f"source.{field}")
    if finding.metadata_only:
        categories = ",".join(finding.categories) or "private_text"
        raise GoalCandidateBuildError(f"verified_source_privacy_rejected:{categories}")
    return text[:500]


def _payload_rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    try:
        rows = connection.execute(
            f'SELECT payload_json FROM "{table}" ORDER BY event_sequence'
        ).fetchall()
    except sqlite3.Error as error:
        raise GoalCandidateBuildError(f"source_table_invalid:{table}") from error
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(str(row[0]))
        except json.JSONDecodeError as error:
            raise GoalCandidateBuildError(f"source_payload_invalid:{table}") from error
        if not isinstance(payload, dict):
            raise GoalCandidateBuildError(f"source_payload_invalid:{table}")
        result.append(payload)
    return result


def _sequenced_payload_rows(
    connection: sqlite3.Connection, table: str
) -> list[tuple[int, dict[str, Any]]]:
    try:
        rows = connection.execute(
            f'SELECT event_sequence, payload_json FROM "{table}" ORDER BY event_sequence'
        ).fetchall()
    except sqlite3.Error as error:
        raise GoalCandidateBuildError(f"source_table_invalid:{table}") from error
    result: list[tuple[int, dict[str, Any]]] = []
    previous = 0
    for raw_sequence, raw_payload in rows:
        if type(raw_sequence) is not int or raw_sequence <= previous:
            raise GoalCandidateBuildError(f"source_event_sequence_invalid:{table}")
        previous = raw_sequence
        try:
            payload = json.loads(str(raw_payload))
        except json.JSONDecodeError as error:
            raise GoalCandidateBuildError(f"source_payload_invalid:{table}") from error
        if not isinstance(payload, dict):
            raise GoalCandidateBuildError(f"source_payload_invalid:{table}")
        result.append((raw_sequence, payload))
    return result


def _add_semantic_values(
    target: list[SemanticValue],
    value: Any,
    *,
    screen_id: str,
    element_id: str | None,
    field: str,
) -> None:
    values = value if isinstance(value, list) else [value]
    for raw in values:
        text = _privacy_safe_semantic(raw, field=field)
        if text is None:
            continue
        target.append(
            SemanticValue(
                value=text,
                screen_id=screen_id,
                element_id=element_id,
                field=field,
            )
        )


def _validated_local_signal_evidence(
    value: Any,
    *,
    package: str,
    screen_id: str,
    metadata_element_ids: Mapping[str, set[str]],
    source_metric_id: str,
    source_event_sequence: int,
    source_metric_payload_sha256: str,
) -> LocalSignalEvidence:
    if not isinstance(value, Mapping) or set(value) != LOCAL_SIGNAL_EVIDENCE_FIELDS:
        raise GoalCandidateBuildError("sensitive_local_signal_shape_invalid")
    if (
        value.get("policy_version") != SENSITIVE_LOCAL_POLICY_VERSION
        or value.get("decision_source")
        != "deterministic_local_transient_accessibility"
        or value.get("external_api_transfer_count") != 0
        or value.get("human_text_persisted") is not False
    ):
        raise GoalCandidateBuildError("sensitive_local_signal_policy_invalid")
    family_id = str(value.get("family_id") or "").strip()
    if family_id not in SENSITIVE_SAFE_FAMILIES or family_id not in FAMILY_SIGNALS:
        raise GoalCandidateBuildError("sensitive_local_signal_family_invalid")
    raw_signal_ids = value.get("matched_signal_ids")
    allowed_signal_ids = {
        signal.signal_id for signal in FAMILY_SIGNALS[family_id]
    }
    if (
        not isinstance(raw_signal_ids, list)
        or not raw_signal_ids
        or any(not isinstance(item, str) for item in raw_signal_ids)
        or raw_signal_ids != sorted(set(raw_signal_ids))
        or not set(raw_signal_ids).issubset(allowed_signal_ids)
    ):
        raise GoalCandidateBuildError("sensitive_local_signal_allowlist_invalid")
    element_id = str(value.get("selected_element_id") or "").strip()
    if (
        not re.fullmatch(r"adb_[0-9a-f]{8,64}", element_id)
        or element_id not in metadata_element_ids.get(screen_id, set())
    ):
        raise GoalCandidateBuildError("sensitive_local_signal_element_invalid")
    commitment = str(value.get("semantic_commitment_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", commitment):
        raise GoalCandidateBuildError("sensitive_local_signal_commitment_invalid")
    terminal_policy = str(value.get("terminal_policy") or "")
    expected_terminal = (
        "user_boundary"
        if family_id in SENSITIVE_LOCAL_USER_BOUNDARY_FAMILIES
        else "manifest_governed"
    )
    if terminal_policy != expected_terminal:
        raise GoalCandidateBuildError("sensitive_local_signal_terminal_invalid")
    control_bucket = str(value.get("control_bucket") or "")
    if control_bucket not in {"clickable", "checkable", "password", "text_field"}:
        raise GoalCandidateBuildError("sensitive_local_signal_control_invalid")
    guard = value.get("action_guard")
    if not isinstance(guard, Mapping) or set(guard) != ACTION_GUARD_FIELDS:
        raise GoalCandidateBuildError("sensitive_local_signal_guard_invalid")
    allowed = guard.get("allowed")
    final = guard.get("computed_final_or_consequential")
    safe_menu = guard.get("safe_menu_match")
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
        or value.get("auto_navigation_allowed")
        is not (allowed and control_bucket == "clickable")
    ):
        raise GoalCandidateBuildError("sensitive_local_signal_guard_invalid")
    return LocalSignalEvidence(
        family_id=family_id,
        signal_ids=tuple(raw_signal_ids),
        screen_id=screen_id,
        element_id=element_id,
        semantic_commitment_sha256=commitment,
        policy_version=SENSITIVE_LOCAL_POLICY_VERSION,
        source_metric_id=source_metric_id,
        source_event_sequence=source_event_sequence,
        source_metric_payload_sha256=source_metric_payload_sha256,
        action_guard_sha256=canonical_sha256(dict(guard)),
        terminal_policy=terminal_policy,
        control_bucket=control_bucket,
        auto_navigation_allowed=bool(value.get("auto_navigation_allowed")),
    )


def _extract_evidence(
    corpus_path: Path,
    selected_packages: Sequence[str],
    inventory: Mapping[str, Mapping[str, Any]],
) -> list[AppEvidence]:
    try:
        connection = sqlite3.connect(f"file:{corpus_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as error:
        raise GoalCandidateBuildError("corpus_read_only_open_failed") from error
    try:
        screens = _payload_rows(connection, "screens")
        elements = _payload_rows(connection, "elements")
        metric_rows = _sequenced_payload_rows(connection, "metrics")
    finally:
        connection.close()

    selected_set = set(selected_packages)
    semantics: dict[str, list[SemanticValue]] = defaultdict(list)
    verified_screens: dict[str, list[str]] = defaultdict(list)
    metadata_screens: dict[str, list[str]] = defaultdict(list)
    auth_screens: dict[str, list[str]] = defaultdict(list)
    local_signal_evidence: dict[str, list[LocalSignalEvidence]] = defaultdict(list)
    screen_mode: dict[str, tuple[str, str]] = {}
    metadata_element_ids: dict[str, set[str]] = defaultdict(set)

    for screen in screens:
        package = str(screen.get("app_package") or "").strip()
        screen_id = _machine_id(screen.get("screen_id"), "screen_id")
        if package not in selected_set:
            raise GoalCandidateBuildError("corpus_contains_unselected_screen")
        mode = str(screen.get("evidence_mode") or "").casefold()
        privacy_verified = screen.get("privacy_verified") is True
        metadata_only = mode == "metadata_only" or not privacy_verified
        if str(screen.get("login_state") or "").casefold() == "boundary":
            auth_screens[package].append(screen_id)
        if metadata_only:
            if any(_nonempty(screen.get(field)) for field in METADATA_ONLY_SCREEN_FORBIDDEN_FIELDS):
                raise GoalCandidateBuildError("metadata_only_screen_semantic_leak")
            metadata_screens[package].append(screen_id)
            screen_mode[screen_id] = (package, "metadata_only")
            continue
        if (
            mode not in SAFE_EVIDENCE_MODES
            or screen.get("contains_personal_data") is True
            or screen.get("accessibility_tree_redacted") is not True
            or screen.get("raw_artifacts_persisted") is not False
        ):
            raise GoalCandidateBuildError("screen_not_verified_redacted")
        verified_screens[package].append(screen_id)
        screen_mode[screen_id] = (package, "verified_redacted")
        for field in SCREEN_SEMANTIC_FIELDS:
            _add_semantic_values(
                semantics[package],
                screen.get(field),
                screen_id=screen_id,
                element_id=None,
                field=field,
            )

    for element in elements:
        screen_id = str(element.get("screen_id") or "").strip()
        mode_record = screen_mode.get(screen_id)
        if mode_record is None:
            raise GoalCandidateBuildError("element_screen_reference_invalid")
        package, screen_evidence_mode = mode_record
        element_id = _machine_id(element.get("element_id"), "element_id")
        element_mode = str(element.get("evidence_mode") or "").casefold()
        if screen_evidence_mode == "metadata_only":
            if any(_nonempty(element.get(field)) for field in METADATA_ONLY_ELEMENT_FORBIDDEN_FIELDS):
                raise GoalCandidateBuildError("metadata_only_element_semantic_leak")
            local_element_id = str(element.get("ui_element_id") or "").strip()
            if not re.fullmatch(r"adb_[0-9a-f]{8,64}", local_element_id):
                raise GoalCandidateBuildError("metadata_only_element_local_id_invalid")
            if not element_id.endswith(":" + local_element_id):
                raise GoalCandidateBuildError("metadata_only_element_local_id_mismatch")
            metadata_element_ids[screen_id].add(local_element_id)
            continue
        if element.get("privacy_verified") is not True or element_mode not in SAFE_EVIDENCE_MODES:
            raise GoalCandidateBuildError("element_not_verified_redacted")
        if (
            element.get("password") is True
            or element.get("sensitive") is True
            or "edittext" in str(element.get("class_name") or "").casefold()
        ):
            if screen_id not in auth_screens[package]:
                auth_screens[package].append(screen_id)
            continue
        # Privacy redaction is intentionally broader than authentication.  A
        # personalized title, message preview, or media card must not leak
        # into semantic inference, but its presence alone does not turn the
        # whole screen into a login wall.
        if element.get("privacy_redacted") is True:
            continue
        for field in ELEMENT_SEMANTIC_FIELDS:
            _add_semantic_values(
                semantics[package],
                element.get(field),
                screen_id=screen_id,
                element_id=element_id,
                field=field,
            )

    for source_event_sequence, metric in metric_rows:
        if str(metric.get("metric_dimension") or "") != "sensitive_local_goal_signal":
            continue
        metric_fields = set(metric)
        if (
            not SENSITIVE_SIGNAL_METRIC_REQUIRED_FIELDS.issubset(metric_fields)
            or not metric_fields.issubset(SENSITIVE_SIGNAL_METRIC_ALLOWED_FIELDS)
        ):
            raise GoalCandidateBuildError("sensitive_local_signal_metric_shape_invalid")
        source_metric_id = _machine_id(
            metric.get("metric_id"), "sensitive_local_signal_metric_id_invalid"
        )
        _machine_id(metric.get("goal_id"), "sensitive_local_signal_goal_id_invalid")
        package = str(metric.get("app_package") or "").strip()
        screen_id = _machine_id(metric.get("screen_id"), "screen_id")
        mode_record = screen_mode.get(screen_id)
        if (
            package not in selected_set
            or mode_record != (package, "metadata_only")
            or not inventory[package]["sensitivity_categories"]
        ):
            raise GoalCandidateBuildError("sensitive_local_signal_source_invalid")
        if (
            metric.get("policy_event") != "label_free_goal_signal_observed"
            or metric.get("external_api_transfer_count") != 0
            or metric.get("human_text_persisted") is not False
        ):
            raise GoalCandidateBuildError("sensitive_local_signal_metric_invalid")
        local_signal_evidence[package].append(
            _validated_local_signal_evidence(
                metric.get("local_signal_evidence"),
                package=package,
                screen_id=screen_id,
                metadata_element_ids=metadata_element_ids,
                source_metric_id=source_metric_id,
                source_event_sequence=source_event_sequence,
                source_metric_payload_sha256=canonical_sha256(metric),
            )
        )

    evidence: list[AppEvidence] = []
    for package in selected_packages:
        record = inventory[package]
        # Deduplicate without retaining or emitting the source string elsewhere.
        unique: dict[tuple[str, str, str | None, str], SemanticValue] = {}
        for value in semantics[package]:
            key = (value.value, value.screen_id, value.element_id, value.field)
            unique[key] = value
        evidence.append(
            AppEvidence(
                app_package=package,
                version_name=record["version_name"],
                version_code=record["version_code"],
                version_key=record["version_key"],
                sensitivity_categories=tuple(record["sensitivity_categories"]),
                semantic_values=tuple(unique.values()),
                verified_redacted_screen_ids=tuple(sorted(set(verified_screens[package]))),
                metadata_only_screen_ids=tuple(sorted(set(metadata_screens[package]))),
                authentication_boundary_screen_ids=tuple(sorted(set(auth_screens[package]))),
                local_signal_evidence=tuple(
                    sorted(
                        {
                            (
                                row.family_id,
                                row.signal_ids,
                                row.screen_id,
                                row.element_id,
                                row.semantic_commitment_sha256,
                                row.policy_version,
                                row.source_metric_id,
                                row.source_event_sequence,
                                row.source_metric_payload_sha256,
                                row.action_guard_sha256,
                                row.terminal_policy,
                                row.control_bucket,
                                row.auto_navigation_allowed,
                            ): row
                            for row in local_signal_evidence[package]
                        }.values(),
                        key=lambda row: (
                            row.family_id,
                            row.screen_id,
                            row.element_id,
                            row.semantic_commitment_sha256,
                            row.source_event_sequence,
                            row.source_metric_id,
                        ),
                    )
                ),
            )
        )
    return evidence


def _reject_quarantine(run_directory: Path) -> None:
    marker = run_directory / "QUARANTINED.json"
    if marker.exists():
        raise GoalCandidateBuildError("source_run_quarantined")


def _load_optional_reranker(specification: str | None) -> Callable[[Mapping[str, Any]], Mapping[str, Any]] | None:
    if not specification:
        return None
    if ":" not in specification:
        raise GoalCandidateBuildError("reranker_spec_invalid")
    module_name, function_name = specification.rsplit(":", 1)
    if not module_name or not function_name:
        raise GoalCandidateBuildError("reranker_spec_invalid")
    try:
        function = getattr(importlib.import_module(module_name), function_name)
    except (ImportError, AttributeError) as error:
        raise GoalCandidateBuildError("reranker_unavailable") from error
    if not callable(function):
        raise GoalCandidateBuildError("reranker_not_callable")
    return function


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        with temporary.open("xb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate_goal_candidates(
    run_directory: Path | str,
    inventory_snapshot_path: Path | str,
    *,
    repo_root: Path | str = ROOT,
    observation_root: Path | str = DEFAULT_OBSERVATION_ROOT,
    family_manifest_path: Path | str = DEFAULT_FAMILY_MANIFEST,
    output_path: Path | str | None = None,
    overwrite: bool = False,
    hermes_reranker: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    unresolved_run_directory = Path(run_directory).expanduser()
    unresolved_snapshot_path = Path(inventory_snapshot_path).expanduser()
    if unresolved_run_directory.is_symlink() or unresolved_snapshot_path.is_symlink():
        raise GoalCandidateBuildError("symlink_source_forbidden")
    run_directory = unresolved_run_directory.resolve()
    inventory_snapshot_path = unresolved_snapshot_path.resolve()
    repo_root = Path(repo_root).expanduser().resolve()
    observation_root = Path(observation_root).expanduser().resolve()
    family_manifest_path = Path(family_manifest_path).expanduser().resolve()
    unresolved_output_path = (
        Path(output_path).expanduser()
        if output_path is not None
        else run_directory / OUTPUT_FILENAME
    )
    if unresolved_output_path.is_symlink():
        raise GoalCandidateBuildError("output_source_collision")
    output_path = unresolved_output_path.resolve()
    if not run_directory.is_dir() or run_directory.is_symlink():
        raise GoalCandidateBuildError("run_directory_invalid")
    _reject_quarantine(run_directory)
    required_paths = {
        "manifest": run_directory / "manifest.json",
        "checkpoint": run_directory / "checkpoint.json",
        "corpus": run_directory / "corpus.sqlite",
        "graph": run_directory / "graph-candidate.sqlite",
        "snapshot": inventory_snapshot_path,
        "family_manifest": family_manifest_path,
    }
    for label, path in required_paths.items():
        if not path.is_file() or path.is_symlink():
            raise GoalCandidateBuildError(f"required_source_missing:{label}")
    if not output_path.is_relative_to(run_directory):
        raise GoalCandidateBuildError("output_must_be_inside_run_directory")
    if output_path in set(required_paths.values()) or output_path.is_symlink():
        raise GoalCandidateBuildError("output_source_collision")
    if output_path.exists() and not overwrite:
        raise GoalCandidateBuildError("output_exists_without_force")

    validation = _validate_run(
        run_directory,
        repo_root=repo_root,
        app_manifest_path=family_manifest_path,
        observation_root=observation_root,
    )
    if not validation.get("ok"):
        codes = sorted(
            {
                str(item.get("code") or "validation_error")
                for item in validation.get("errors", [])
                if isinstance(item, Mapping)
            }
        )
        raise GoalCandidateBuildError(
            "validated_dynamic_run_required:" + ",".join(codes or ["validation_error"])
        )

    manifest = _json_file(required_paths["manifest"])
    pinned_snapshot_path = _resolve_pinned_snapshot(manifest, observation_root)
    if pinned_snapshot_path != inventory_snapshot_path:
        raise GoalCandidateBuildError("exact_inventory_snapshot_required")
    snapshot = _json_file(inventory_snapshot_path)
    run_id, selected_packages, inventory = _validate_source_identity(
        manifest, snapshot, inventory_snapshot_path
    )
    validated_core_hashes_before = _validated_core_artifact_hashes(
        run_directory, run_id
    )
    family_manifest = _json_file(family_manifest_path)
    families = family_definitions(family_manifest)

    source_hashes_before = {
        label: _sha256_file(path) for label, path in sorted(required_paths.items())
    }
    for label, filename in (
        ("manifest", "manifest.json"),
        ("checkpoint", "checkpoint.json"),
        ("corpus", "corpus.sqlite"),
        ("graph", "graph-candidate.sqlite"),
    ):
        if source_hashes_before[label] != validated_core_hashes_before[filename]:
            raise GoalCandidateBuildError("validation_attestation_source_mismatch")
    evidence = _extract_evidence(
        required_paths["corpus"], selected_packages, inventory
    )
    app_results = [
        generate_app_candidate_set(
            app_evidence,
            families,
            hermes_reranker=hermes_reranker,
        )
        for app_evidence in evidence
    ]
    state_counts = Counter(
        candidate["applicability_state"]
        for app in app_results
        for candidate in app["goal_candidates"]
    )
    reranker_metrics = Counter()
    for app in app_results:
        metric = app["hermes_k_exaone"]
        reranker_metrics["eligible_ambiguity_app_count"] += int(
            metric["eligible_ambiguity"]
        )
        reranker_metrics["attempted_app_count"] += int(metric["attempted"])
        reranker_metrics["used_app_count"] += int(metric["used"])
        reranker_metrics["deterministic_fallback_app_count"] += int(
            metric["deterministic_fallback_used"]
        )

    payload = {
        "schema_version": 1,
        "artifact_type": "dynamic_real_device_goal_candidates",
        "generator": "Generate-RealDeviceGoalCandidates.py",
        "source_run_id": run_id,
        "source_inventory_snapshot_id": snapshot["snapshot_id"],
        "source_sha256": source_hashes_before,
        "provenance": PROVENANCE,
        "dataset_role": PROVENANCE,
        "review_status": REVIEW_STATUS,
        "review_lifecycle": "candidate",
        "route_lifecycle": ROUTE_LIFECYCLE,
        "serving_allowed": False,
        "human_review_required": True,
        "goal_candidate_policy": goal_candidate_policy_attestation(),
        "canonical_catalog": {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "mutation_allowed": False,
        },
        "version_policy": {
            "canonical": "V15_frozen",
            "v16_v20_promotion": "forbidden",
            "v21": "research_only_noncanonical",
            "v22_plus": "forbidden",
        },
        "safety": {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            "terminal_actions_owned_by_user": True,
        },
        "evidence_policy": {
            "goal_candidate_policy_version": GOAL_CANDIDATE_POLICY_VERSION,
            "goal_candidate_policy_sha256": GOAL_CANDIDATE_POLICY_SHA256,
            "semantic_source": "verified_redacted_accessibility_or_validated_label_free_local_signal_ids",
            "metadata_only_semantics_used": 0,
            "sensitive_local_policy_version": SENSITIVE_LOCAL_POLICY_VERSION,
            "raw_xml_read": False,
            "raw_screenshot_read": False,
            "sensitive_scope_restriction": "settings_account_subscription_support_only",
        },
        "counts": {
            "inventory_app_count": len(inventory),
            "selected_app_count": len(selected_packages),
            "candidate_count": sum(len(app["goal_candidates"]) for app in app_results),
            "applicability_states": dict(sorted(state_counts.items())),
        },
        "hermes_k_exaone_metrics": dict(sorted(reranker_metrics.items())),
        "apps": app_results,
    }

    # The artifact intentionally contains no source menu strings.  This guard
    # catches accidental output regressions before publication.
    serialized = _canonical_json(payload)
    if any(
        key in serialized
        for key in (
            '"visible_texts"',
            '"content_descriptions"',
            '"title_text"',
            '"goal_text"',
            '"user_goal"',
            '"screenshot_path"',
            '"accessibility_tree_path"',
        )
    ):
        raise GoalCandidateBuildError("output_semantic_leak")

    source_hashes_after = {
        label: _sha256_file(path) for label, path in sorted(required_paths.items())
    }
    validated_core_hashes_after = _validated_core_artifact_hashes(
        run_directory, run_id
    )
    if (
        source_hashes_after != source_hashes_before
        or validated_core_hashes_after != validated_core_hashes_before
    ):
        raise GoalCandidateBuildError("source_changed_during_generation")
    _atomic_write_json(output_path, payload)
    return {
        "ok": True,
        "output_path": str(output_path),
        "output_sha256": _sha256_file(output_path),
        "source_run_id": run_id,
        "selected_app_count": len(selected_packages),
        "candidate_count": payload["counts"]["candidate_count"],
        "applicability_states": payload["counts"]["applicability_states"],
        "hermes_k_exaone_metrics": payload["hermes_k_exaone_metrics"],
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--inventory-snapshot", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--observation-root", type=Path, default=DEFAULT_OBSERVATION_ROOT)
    parser.add_argument("--family-manifest", type=Path, default=DEFAULT_FAMILY_MANIFEST)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--hermes-reranker",
        help="Optional Python module:function K-EXAONE Hermes adapter.",
    )
    parser.add_argument("--compact", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        reranker = _load_optional_reranker(args.hermes_reranker)
        result = generate_goal_candidates(
            args.run_dir,
            args.inventory_snapshot,
            repo_root=args.repo_root,
            observation_root=args.observation_root,
            family_manifest_path=args.family_manifest,
            output_path=args.output,
            overwrite=args.force,
            hermes_reranker=reranker,
        )
        exit_code = 0
    except (GoalCandidateBuildError, OSError, ValueError) as error:
        result = {"ok": False, "error_code": str(error).split(":", 1)[0]}
        exit_code = 1
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=True,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
