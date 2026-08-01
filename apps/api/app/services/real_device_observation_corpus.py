"""Candidate-only observation corpus for physical Android devices.

Physical-device observations are useful evidence, but they are not human gold.
This store keeps them separate from emulator observations and from the frozen
canonical V15 catalog.  Candidate routes remain shadow/provisional until an
external, explicit human-review workflow promotes them elsewhere.

Runtime evidence belongs under an ignored artifact directory.  This module
never copies raw screenshots or raw accessibility XML into repository fixtures;
unverified evidence falls back to metadata-only storage.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from app.services.emulator_observation_corpus import (
    CANONICAL_CATALOG_SHA256,
    CANONICAL_CATALOG_VERSION,
    CANONICAL_COUNTS,
    CANONICAL_EQUIVALENCE_SHA256,
    CHECKPOINT_FILENAME,
    DATABASE_FILENAME,
    JSONL_FILENAME,
    MANIFEST_FILENAME,
    RECORD_TABLES,
    SCHEMA_VERSION,
    CorpusIntegrityError,
    CorpusRecord,
    EmulatorObservationCorpus,
    _ID_FIELDS,
    _TABLE_FIELDS,
    _apply_field_aliases,
    _atomic_write_json,
    _canonical_json,
    _jsonable,
    _read_json,
    _sqlite_value,
    _utc_now,
    canonical_sha256,
    sha256_file,
)
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository
from app.services.real_device_action_safety import (
    evaluate_auto_action_guard,
    guard_evidence_matches,
)


CORPUS_TYPE = "real-device-observation-candidate"
PROVENANCE = "real_device_observation_candidate"
DATASET_ROLE = PROVENANCE
ROUTE_LIFECYCLE = "shadow"
REVIEW_LIFECYCLE = "candidate"
REVIEW_STATUS = "unreviewed_candidate"
RUN_MODE = "real_device_observation"
GRAPH_DATABASE_FILENAME = "graph-candidate.sqlite"

ALLOWED_RUN_STATUSES = frozenset({"collecting", "completed", "incomplete", "failed"})
ALLOWED_APP_STATUSES = frozenset(
    {"installed_observed", "installed_not_selected", "skipped_missing"}
)
ALLOWED_COLLECTION_MODES = frozenset({"capture_only", "dry_run", "safe_explore"})
ALLOWED_VALIDATION_PROFILES = frozenset(
    {"full_cohort", "partial_research", "dynamic_inventory"}
)
ALLOWED_EXPLORATION_STAGES = frozenset(
    {"initial_capture", "neutral_menu_discovery", "goal_directed_exploration"}
)
EXPLORATION_STAGE_INITIAL_CAPTURE = "initial_capture"
EXPLORATION_STAGE_NEUTRAL_DISCOVERY = "neutral_menu_discovery"
EXPLORATION_STAGE_GOAL_DIRECTED = "goal_directed_exploration"
NEUTRAL_INVENTORY_GOAL = "앱 기능 메뉴 및 설정 진입점 조사"
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
FORBIDDEN_GOLD_VALUES = frozenset({"real_device_gold", "human_gold", "approved_gold"})


def _validate_stage_lineage(payload: Mapping[str, Any], label: str) -> None:
    """Reject mixed neutral/directed control metadata before it reaches disk."""

    stage = payload.get("exploration_stage")
    if stage not in ALLOWED_EXPLORATION_STAGES:
        raise CorpusIntegrityError(f"{label} exploration stage mismatch")
    validation_profile = payload.get("validation_profile", "full_cohort")
    plan = payload.get("goal_candidate_plan")
    snapshot = payload.get("inventory_snapshot")
    if validation_profile != "dynamic_inventory":
        if stage != EXPLORATION_STAGE_INITIAL_CAPTURE or plan is not None:
            raise CorpusIntegrityError(f"{label} non-dynamic stage/plan mismatch")
        return
    if not isinstance(snapshot, Mapping):
        raise CorpusIntegrityError(f"{label} dynamic stage lacks inventory metadata")
    if snapshot.get("exploration_stage") != stage:
        raise CorpusIntegrityError(f"{label} inventory exploration stage mismatch")
    if snapshot.get("goal_candidate_plan") != plan:
        raise CorpusIntegrityError(f"{label} inventory goal plan mismatch")
    tasks = snapshot.get("selected_tasks")
    if not isinstance(tasks, list) or not tasks:
        raise CorpusIntegrityError(f"{label} dynamic stage lacks selected tasks")
    collection_mode = payload.get("collection_mode")
    if stage == EXPLORATION_STAGE_INITIAL_CAPTURE:
        if collection_mode not in {"capture_only", "dry_run"} or plan is not None:
            raise CorpusIntegrityError(f"{label} initial capture mode/plan mismatch")
    elif stage == EXPLORATION_STAGE_NEUTRAL_DISCOVERY:
        if collection_mode != "safe_explore" or plan is not None:
            raise CorpusIntegrityError(f"{label} neutral discovery mode/plan mismatch")
    else:
        if collection_mode != "safe_explore" or not isinstance(plan, Mapping):
            raise CorpusIntegrityError(f"{label} directed exploration mode/plan mismatch")

    if stage != EXPLORATION_STAGE_GOAL_DIRECTED:
        for task in tasks:
            if (
                not isinstance(task, Mapping)
                or task.get("goal_text") != NEUTRAL_INVENTORY_GOAL
                or any(task.get(field) not in (None, "") for field in GOAL_LINEAGE_FIELDS)
            ):
                raise CorpusIntegrityError(f"{label} neutral task lineage mismatch")
        return

    expected_keys = {
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
    if set(plan) != expected_keys:
        raise CorpusIntegrityError(f"{label} directed plan shape mismatch")
    artifact = plan.get("artifact")
    if not isinstance(artifact, Mapping) or not isinstance(artifact.get("sha256"), str):
        raise CorpusIntegrityError(f"{label} directed artifact pin mismatch")
    selection = []
    for task in tasks:
        if not isinstance(task, Mapping) or any(
            task.get(field) in (None, "") for field in GOAL_LINEAGE_FIELDS
        ):
            raise CorpusIntegrityError(f"{label} directed task lineage mismatch")
        if task.get("source_artifact_sha256") != artifact.get("sha256"):
            raise CorpusIntegrityError(f"{label} directed task artifact mismatch")
        selection.append(
            {
                "task_id": task.get("task_id"),
                "app_package": task.get("app_package"),
                "version_key": task.get("version_key"),
                "candidate_id": task.get("candidate_id"),
                "family_id": task.get("family_id"),
                "terminal_policy": task.get("terminal_policy"),
                "source_run_id": task.get("source_run_id"),
                "source_inventory_snapshot_id": task.get(
                    "source_inventory_snapshot_id"
                ),
                "confidence": task.get("confidence"),
                "candidate_rank": task.get("candidate_rank"),
                "source_artifact_sha256": task.get("source_artifact_sha256"),
            }
        )
    if (
        plan.get("selection") != selection
        or plan.get("selected_candidate_count") != len(selection)
        or plan.get("selected_candidate_ids")
        != [item["candidate_id"] for item in selection]
        or plan.get("selection_sha256") != canonical_sha256(selection)
    ):
        raise CorpusIntegrityError(f"{label} directed selection mismatch")


def _element_guard_inputs(payload: Mapping[str, Any]) -> tuple[tuple[object, ...], object]:
    labels = tuple(
        payload.get(key, "")
        for key in ("label", "text", "content_description", "inferred_label")
    )
    return labels, payload.get("resource_id", "")


def _evidence_derived_action_counts(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    """Derive safety counters from stored transitions and source elements."""

    element_payloads: dict[str, dict[str, Any]] = {}
    for element_id, payload_json in connection.execute(
        "SELECT element_id, payload_json FROM elements"
    ):
        try:
            payload = json.loads(str(payload_json))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        element_payloads[str(element_id)] = payload if isinstance(payload, dict) else {}

    unsafe = 0
    final = 0
    for (payload_json,) in connection.execute(
        "SELECT payload_json FROM transitions ORDER BY event_sequence"
    ):
        try:
            payload = json.loads(str(payload_json))
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict) or payload.get("auto_executed") is not True:
            continue
        if str(payload.get("action_type") or "").strip().casefold() != "click":
            continue
        element_id = str(payload.get("element_id") or "")
        element_exists = element_id in element_payloads
        element = element_payloads.get(element_id, {})
        labels, resource_id = _element_guard_inputs(element)
        decision = evaluate_auto_action_guard(
            "click",
            selected_label=payload.get("selected_label", ""),
            element_labels=labels,
            resource_id=resource_id,
        )
        if decision.computed_final_or_consequential:
            final += 1
        declared_final = payload.get("is_final_action")
        declared_unsafe = payload.get("unsafe_action")
        guard_valid = guard_evidence_matches(payload.get("auto_action_guard"), decision)
        if (
            not decision.allowed
            or not guard_valid
            or not element_exists
            or declared_final is not decision.computed_final_or_consequential
            or declared_unsafe is not (not decision.allowed)
        ):
            unsafe += 1
    return {
        "unsafe_auto_click_count": unsafe,
        "final_action_auto_click_count": final,
    }


class RealDeviceObservationCorpus(EmulatorObservationCorpus):
    """Append-only, resumable physical-device candidate evidence store."""

    def __init__(self, output_directory: Path | str, *, run_id: str, resume: bool = True) -> None:
        if not str(run_id).strip():
            raise ValueError("run_id must not be empty")
        self.output_directory = Path(output_directory).resolve()
        self.run_id = str(run_id).strip()
        self.database_path = self.output_directory / DATABASE_FILENAME
        self.graph_database_path = self.output_directory / GRAPH_DATABASE_FILENAME
        self.jsonl_path = self.output_directory / JSONL_FILENAME
        self.manifest_path = self.output_directory / MANIFEST_FILENAME
        self.checkpoint_path = self.output_directory / CHECKPOINT_FILENAME
        self._lock = threading.RLock()
        self._control_status = "collecting"
        self._control_app_statuses: dict[str, str] = {}
        self._device_type = "physical_android"
        self._is_emulator = False
        self._device_serial = ""
        self._collection_mode = "capture_only"
        self._validation_profile = "full_cohort"
        self._selected_packages: tuple[str, ...] = ()
        self._inventory_packages: tuple[str, ...] = ()
        self._inventory_snapshot: dict[str, Any] | None = None
        self._runtime_attestation: dict[str, Any] | None = None
        self._exploration_stage = "initial_capture"
        self._goal_candidate_plan: dict[str, Any] | None = None
        self._selected_tasks: list[dict[str, Any]] = []
        self.output_directory.mkdir(parents=True, exist_ok=True)

        existing = any(
            path.exists()
            for path in (
                self.manifest_path,
                self.database_path,
                self.graph_database_path,
                self.jsonl_path,
            )
        )
        if existing and not resume:
            raise FileExistsError(f"corpus already exists: {self.output_directory}")

        self._ensure_schema()
        self._ensure_graph_schema()
        self.jsonl_path.touch(exist_ok=True)
        if self.manifest_path.exists():
            existing_manifest = _read_json(self.manifest_path)
            self._validate_manifest(existing_manifest)
            self._control_status = str(existing_manifest["status"])
            self._control_app_statuses = {
                str(entry["app_package"]): str(entry["status"])
                for entry in existing_manifest["app_statuses"]
            }
            self._device_type = str(existing_manifest.get("device_type") or "physical_android")
            self._is_emulator = existing_manifest.get("is_emulator") is True
            self._device_serial = str(existing_manifest.get("device_serial") or "")
            self._collection_mode = str(existing_manifest.get("collection_mode") or "capture_only")
            self._validation_profile = str(
                existing_manifest.get("validation_profile") or "full_cohort"
            )
            self._selected_packages = tuple(
                sorted({str(value).strip() for value in existing_manifest.get("selected_packages", []) if str(value).strip()})
            )
            self._inventory_packages = tuple(
                sorted({str(value).strip() for value in existing_manifest.get("inventory_packages", []) if str(value).strip()})
            )
            existing_snapshot = existing_manifest.get("inventory_snapshot")
            self._inventory_snapshot = (
                dict(existing_snapshot) if isinstance(existing_snapshot, Mapping) else None
            )
            existing_runtime = existing_manifest.get("runtime_attestation")
            self._runtime_attestation = (
                dict(existing_runtime) if isinstance(existing_runtime, Mapping) else None
            )
            self._exploration_stage = str(
                existing_manifest.get("exploration_stage") or "initial_capture"
            )
            existing_goal_plan = existing_manifest.get("goal_candidate_plan")
            self._goal_candidate_plan = (
                dict(existing_goal_plan)
                if isinstance(existing_goal_plan, Mapping)
                else None
            )
            existing_tasks = existing_manifest.get("tasks")
            self._selected_tasks = (
                [dict(task) for task in existing_tasks if isinstance(task, Mapping)]
                if isinstance(existing_tasks, list)
                else []
            )
        self._validate_database_events()
        self._validate_graph_candidate()
        self._sync_jsonl_from_database()
        self._refresh_control_files(state=self.resume_state)

    @property
    def resume_state(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {}
        checkpoint = _read_json(self.checkpoint_path)
        self._validate_control_identity(checkpoint, "checkpoint")
        if self.manifest_path.exists():
            manifest = _read_json(self.manifest_path)
            for field in (
                "validation_profile",
                "collection_mode",
                "selected_packages",
                "inventory_packages",
                "inventory_snapshot",
                "runtime_attestation",
                "exploration_stage",
                "goal_candidate_plan",
                "tasks",
            ):
                if checkpoint.get(field) != manifest.get(field):
                    raise CorpusIntegrityError(
                        f"checkpoint/manifest control mismatch for {field}"
                    )
        state = checkpoint.get("state", {})
        if not isinstance(state, dict):
            raise CorpusIntegrityError("checkpoint state must be an object")
        return dict(state)

    @property
    def graph_repository(self) -> UniversalNavigationGraphRepository:
        """Return the existing graph engine, constrained by shadow triggers."""
        return UniversalNavigationGraphRepository(self.graph_database_path)

    def refresh_after_graph_write(self) -> Path:
        """Re-hash graph-candidate.sqlite after an engine observation/route write."""
        self._validate_graph_candidate()
        return self.save_checkpoint(self.resume_state)

    def action_safety_counts(self) -> dict[str, int]:
        """Return evidence-derived automatic-click safety counters."""

        with self._connection() as connection:
            return _evidence_derived_action_counts(connection)

    def update_control_metadata(
        self,
        *,
        status: str | None = None,
        app_statuses: list[Mapping[str, str]] | None = None,
        device_type: str | None = None,
        is_emulator: bool | None = None,
        device_serial: str | None = None,
        collection_mode: str | None = None,
        validation_profile: str | None = None,
        selected_packages: list[str] | tuple[str, ...] | None = None,
        inventory_packages: list[str] | tuple[str, ...] | None = None,
        inventory_snapshot: Mapping[str, Any] | None = None,
        runtime_attestation: Mapping[str, Any] | None = None,
        exploration_stage: str | None = None,
        goal_candidate_plan: Mapping[str, Any] | None = None,
        tasks: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | None = None,
    ) -> Path:
        """Update atomic run control state without rewriting observation rows."""
        with self._lock:
            checkpoint_state = self.resume_state
            if status is not None:
                if status not in ALLOWED_RUN_STATUSES:
                    raise CorpusIntegrityError(f"unsupported run status: {status}")
                self._control_status = status
                checkpoint_state["run_status"] = status
            if app_statuses is not None:
                updated: dict[str, str] = {}
                for entry in app_statuses:
                    app_package = str(entry.get("app_package") or "").strip()
                    app_status = str(entry.get("status") or "").strip()
                    if not app_package or app_status not in ALLOWED_APP_STATUSES:
                        raise CorpusIntegrityError("invalid app control status")
                    updated[app_package] = app_status
                self._control_app_statuses = updated
            if device_type is not None:
                if device_type not in {"physical_android", "physical_device", "android_physical", "physical"}:
                    raise CorpusIntegrityError("device_type must identify a physical Android device")
                self._device_type = device_type
            if is_emulator is not None:
                if is_emulator is not False:
                    raise CorpusIntegrityError("a real-device corpus cannot attest an emulator")
                self._is_emulator = False
            if device_serial is not None:
                serial = str(device_serial).strip()
                if serial.casefold().startswith("emulator-"):
                    raise CorpusIntegrityError("emulator serial is forbidden in a real-device corpus")
                self._device_serial = serial
            if collection_mode is not None:
                normalized_mode = str(collection_mode).strip().casefold()
                if normalized_mode not in ALLOWED_COLLECTION_MODES:
                    raise CorpusIntegrityError(f"unsupported collection mode: {collection_mode}")
                self._collection_mode = normalized_mode
            if validation_profile is not None:
                normalized_profile = str(validation_profile).strip().casefold()
                if normalized_profile not in ALLOWED_VALIDATION_PROFILES:
                    raise CorpusIntegrityError(
                        f"unsupported validation profile: {validation_profile}"
                    )
                self._validation_profile = normalized_profile
            if selected_packages is not None:
                normalized_selected = tuple(
                    sorted({str(value).strip() for value in selected_packages if str(value).strip()})
                )
                self._selected_packages = normalized_selected
            if inventory_packages is not None:
                normalized_inventory = tuple(
                    sorted({str(value).strip() for value in inventory_packages if str(value).strip()})
                )
                self._inventory_packages = normalized_inventory
            if inventory_snapshot is not None:
                normalized_snapshot = _jsonable(dict(inventory_snapshot))
                if not isinstance(normalized_snapshot, dict):
                    raise CorpusIntegrityError("inventory snapshot metadata must be an object")
                self._inventory_snapshot = normalized_snapshot
            if runtime_attestation is not None:
                normalized_runtime = _jsonable(dict(runtime_attestation))
                if not isinstance(normalized_runtime, dict):
                    raise CorpusIntegrityError("runtime attestation metadata must be an object")
                self._runtime_attestation = normalized_runtime
            if exploration_stage is not None:
                normalized_stage = str(exploration_stage).strip().casefold()
                if normalized_stage not in ALLOWED_EXPLORATION_STAGES:
                    raise CorpusIntegrityError("unsupported exploration stage")
                self._exploration_stage = normalized_stage
            if goal_candidate_plan is not None:
                normalized_plan = _jsonable(dict(goal_candidate_plan))
                if not isinstance(normalized_plan, dict):
                    raise CorpusIntegrityError("goal candidate plan must be an object")
                self._goal_candidate_plan = normalized_plan
            if tasks is not None:
                normalized_tasks = _jsonable([dict(task) for task in tasks])
                if not isinstance(normalized_tasks, list) or any(
                    not isinstance(task, dict) for task in normalized_tasks
                ):
                    raise CorpusIntegrityError("selected tasks must be an array of objects")
                self._selected_tasks = normalized_tasks
            if self._inventory_packages and not set(self._selected_packages).issubset(
                self._inventory_packages
            ):
                raise CorpusIntegrityError("selected packages must be a subset of inventory packages")
            if self._validation_profile == "partial_research" and not self._selected_packages:
                raise CorpusIntegrityError("partial_research requires selected packages")
            if self._validation_profile == "dynamic_inventory":
                if not self._selected_packages or not self._inventory_packages:
                    raise CorpusIntegrityError(
                        "dynamic_inventory requires selected and inventory packages"
                    )
                if not isinstance(self._inventory_snapshot, Mapping):
                    raise CorpusIntegrityError(
                        "dynamic_inventory requires inventory snapshot metadata"
                    )
                snapshot_inventory = self._inventory_snapshot.get("included_inventory")
                if not isinstance(snapshot_inventory, list):
                    raise CorpusIntegrityError(
                        "dynamic inventory snapshot must include exact inventory"
                    )
                snapshot_packages = {
                    str(item.get("package") or "").strip()
                    for item in snapshot_inventory
                    if isinstance(item, Mapping) and str(item.get("package") or "").strip()
                }
                if snapshot_packages != set(self._inventory_packages):
                    raise CorpusIntegrityError(
                        "dynamic inventory packages differ from snapshot metadata"
                    )
            _validate_stage_lineage(
                {
                    "validation_profile": self._validation_profile,
                    "collection_mode": self._collection_mode,
                    "exploration_stage": self._exploration_stage,
                    "goal_candidate_plan": self._goal_candidate_plan,
                    "inventory_snapshot": self._inventory_snapshot,
                },
                "control update",
            )
            self._refresh_control_files(state=checkpoint_state)
        return self.manifest_path

    def append(
        self,
        record_type: str,
        payload: Mapping[str, Any],
        *,
        record_id: str | None = None,
        privacy_verified: bool | None = None,
    ) -> CorpusRecord:
        if record_type not in RECORD_TABLES:
            raise ValueError(f"unsupported record type: {record_type}")
        with self._lock:
            normalized = self._normalize_payload(record_type, payload, privacy_verified)
            identifier_field = _ID_FIELDS[record_type]
            if record_id is None:
                record_id = str(normalized.get(identifier_field, "")).strip() or str(uuid.uuid4())
            record_id = str(record_id).strip()
            if not record_id:
                raise ValueError("record_id must not be empty")
            existing_identifier = str(normalized.get(identifier_field, "")).strip()
            if existing_identifier and existing_identifier != record_id:
                raise CorpusIntegrityError(
                    f"{identifier_field} does not match record_id for {record_type}/{record_id}"
                )
            normalized.setdefault(identifier_field, record_id)
            content_sha256 = canonical_sha256(normalized)

            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT sequence, event_id, content_sha256, payload_json
                    FROM event_log WHERE record_type = ? AND record_id = ?
                    """,
                    (record_type, record_id),
                ).fetchone()
                if existing is not None:
                    if existing["content_sha256"] != content_sha256:
                        raise CorpusIntegrityError(
                            f"conflicting append for {record_type}/{record_id}"
                        )
                    connection.rollback()
                    self._sync_jsonl_from_database()
                    return CorpusRecord(
                        sequence=int(existing["sequence"]),
                        event_id=str(existing["event_id"]),
                        record_type=record_type,
                        record_id=record_id,
                        content_sha256=content_sha256,
                        payload=json.loads(existing["payload_json"]),
                        appended=False,
                    )

                sequence = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM event_log"
                    ).fetchone()[0]
                )
                recorded_at = _utc_now()
                event_id = hashlib.sha256(
                    f"{self.run_id}\0{record_type}\0{record_id}\0{content_sha256}".encode("utf-8")
                ).hexdigest()
                envelope_without_hash = {
                    "sequence": sequence,
                    "event_id": event_id,
                    "record_type": record_type,
                    "record_id": record_id,
                    "run_id": self.run_id,
                    "recorded_at": recorded_at,
                    "provenance": PROVENANCE,
                    "dataset_role": DATASET_ROLE,
                    "review_status": REVIEW_STATUS,
                    "review_lifecycle": REVIEW_LIFECYCLE,
                    "route_lifecycle": ROUTE_LIFECYCLE,
                    "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
                    "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
                    "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
                    "content_sha256": content_sha256,
                    "payload": normalized,
                }
                event_sha256 = canonical_sha256(envelope_without_hash)
                envelope = dict(envelope_without_hash, event_sha256=event_sha256)
                payload_json = _canonical_json(normalized)
                envelope_json = _canonical_json(envelope)

                connection.execute(
                    """
                    INSERT INTO event_log (
                      sequence, event_id, record_type, record_id, run_id, recorded_at,
                      provenance, dataset_role, review_status, review_lifecycle,
                      route_lifecycle, canonical_catalog_version,
                      canonical_catalog_sha256, canonical_equivalence_sha256,
                      content_sha256, payload_json, envelope_json, event_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        event_id,
                        record_type,
                        record_id,
                        self.run_id,
                        recorded_at,
                        PROVENANCE,
                        DATASET_ROLE,
                        REVIEW_STATUS,
                        REVIEW_LIFECYCLE,
                        ROUTE_LIFECYCLE,
                        CANONICAL_CATALOG_VERSION,
                        CANONICAL_CATALOG_SHA256,
                        CANONICAL_EQUIVALENCE_SHA256,
                        content_sha256,
                        payload_json,
                        envelope_json,
                        event_sha256,
                    ),
                )
                self._insert_record_row(
                    connection,
                    record_type=record_type,
                    record_id=record_id,
                    sequence=sequence,
                    recorded_at=recorded_at,
                    payload=normalized,
                    payload_json=payload_json,
                    content_sha256=content_sha256,
                )
                connection.commit()

            self._append_jsonl(envelope_json)
            self._refresh_control_files(state=self.resume_state)
            return CorpusRecord(
                sequence=sequence,
                event_id=event_id,
                record_type=record_type,
                record_id=record_id,
                content_sha256=content_sha256,
                payload=normalized,
                appended=True,
            )

    def verify_integrity(self) -> dict[str, Any]:
        errors: list[str] = []
        try:
            self._validate_database_events()
        except CorpusIntegrityError as exc:
            errors.append(str(exc))
        try:
            self._validate_graph_candidate()
        except CorpusIntegrityError as exc:
            errors.append(str(exc))

        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM event_log ORDER BY sequence").fetchall()
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid payload JSON at sequence {row['sequence']}: {exc}")
                    continue
                if payload.get("provenance") != PROVENANCE:
                    errors.append(f"provenance mismatch at sequence {row['sequence']}")
                if payload.get("dataset_role") != DATASET_ROLE:
                    errors.append(f"dataset role mismatch at sequence {row['sequence']}")
                if payload.get("review_status") != REVIEW_STATUS:
                    errors.append(f"review status mismatch at sequence {row['sequence']}")
                if payload.get("review_lifecycle") != REVIEW_LIFECYCLE:
                    errors.append(f"review lifecycle mismatch at sequence {row['sequence']}")
                if payload.get("route_lifecycle") != ROUTE_LIFECYCLE:
                    errors.append(f"route lifecycle mismatch at sequence {row['sequence']}")
                if _contains_forbidden_gold(payload):
                    errors.append(f"unreviewed gold claim at sequence {row['sequence']}")

        jsonl_events = self._read_jsonl_events(errors)
        if len(jsonl_events) != len(rows):
            errors.append(f"JSONL/SQLite count mismatch: {len(jsonl_events)}/{len(rows)}")
        else:
            for row, event in zip(rows, jsonl_events):
                if event.get("event_id") != row["event_id"]:
                    errors.append(f"JSONL event mismatch at sequence {row['sequence']}")
                if event.get("event_sha256") != row["event_sha256"]:
                    errors.append(f"JSONL event hash differs from SQLite at sequence {row['sequence']}")

        manifest = _read_json(self.manifest_path)
        try:
            self._validate_manifest(manifest)
        except CorpusIntegrityError as exc:
            errors.append(str(exc))
        actual_hashes = {
            DATABASE_FILENAME: sha256_file(self.database_path),
            JSONL_FILENAME: sha256_file(self.jsonl_path),
            GRAPH_DATABASE_FILENAME: sha256_file(self.graph_database_path),
        }
        expected_hashes = manifest.get("artifact_sha256", {})
        for filename, actual_hash in actual_hashes.items():
            if expected_hashes.get(filename) != actual_hash:
                errors.append(f"artifact hash mismatch: {filename}")
        return {
            "ok": not errors,
            "errors": errors,
            "run_id": self.run_id,
            "event_count": len(rows),
            "counts": self.counts(),
            "artifact_sha256": actual_hashes,
            "provenance": PROVENANCE,
            "dataset_role": DATASET_ROLE,
            "review_status": REVIEW_STATUS,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
        }

    def _normalize_payload(
        self,
        record_type: str,
        payload: Mapping[str, Any],
        privacy_verified: bool | None,
    ) -> dict[str, Any]:
        normalized = _jsonable(dict(payload))
        if not isinstance(normalized, dict):
            raise TypeError("payload must be an object")
        if _contains_forbidden_gold(normalized):
            raise CorpusIntegrityError("candidate corpus cannot claim real_device_gold or human_gold")
        _reject_catalog_promotion(normalized)
        normalized = _apply_field_aliases(record_type, normalized)
        fixed = {
            "run_id": self.run_id,
            "provenance": PROVENANCE,
            "dataset_role": DATASET_ROLE,
            "review_status": REVIEW_STATUS,
            "review_lifecycle": REVIEW_LIFECYCLE,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
            "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
            "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "canonical_mutation_allowed": False,
            "raw_artifacts_persisted": False,
            "git_eligible": False,
        }
        for key, value in fixed.items():
            if key in normalized and normalized[key] != value:
                raise CorpusIntegrityError(f"record cannot override fixed {key}")
            normalized[key] = value

        if record_type == "apps":
            status = str(normalized.get("status") or "installed_observed")
            if status not in ALLOWED_APP_STATUSES:
                raise CorpusIntegrityError(f"unsupported app observation status: {status}")
            normalized["status"] = status
        if record_type == "screens":
            attested = (
                normalized.get("privacy_verified") is True
                if privacy_verified is None
                else privacy_verified is True
            )
            normalized = self._normalize_real_device_screen_privacy(normalized, attested)
        elif record_type == "elements":
            if privacy_verified is None:
                attested = self._screen_privacy_verified(str(normalized.get("screen_id", "")))
            else:
                attested = privacy_verified is True
            normalized = self._normalize_element_privacy(normalized, attested)
        if record_type == "transitions":
            if normalized.get("auto_executed") is True and (
                normalized.get("is_final_action") is True
                or normalized.get("unsafe_action") is True
            ):
                raise CorpusIntegrityError(
                    "unsafe or final consequential actions cannot be auto-executed"
                )
        if record_type == "metrics":
            for key in ("unsafe_auto_click_count", "final_action_auto_click_count"):
                if int(normalized.get(key, 0) or 0) != 0:
                    raise CorpusIntegrityError(f"{key} must remain zero")
        return normalized

    def _normalize_real_device_screen_privacy(
        self, payload: dict[str, Any], attested: bool
    ) -> dict[str, Any]:
        screenshot_present = bool(payload.get("screenshot_path"))
        tree_present = bool(payload.get("accessibility_tree_path"))
        screenshot_safe = not screenshot_present or payload.get("screenshot_redacted") is True
        tree_safe = not tree_present or payload.get("accessibility_tree_redacted") is True
        if not attested or not screenshot_safe or not tree_safe:
            fallback = self._normalize_screen_privacy(payload, False)
            # Resource IDs are structural evidence, but downstream navigation
            # code intentionally derives human labels from them.  A
            # metadata-only screen cannot retain that semantic side channel.
            fallback.pop("resource_ids", None)
            fallback["raw_artifacts_persisted"] = False
            fallback["git_eligible"] = False
            fallback["evidence_retention"] = "metadata_only"
            if attested and (not screenshot_safe or not tree_safe):
                fallback["privacy_fallback_reason"] = "redacted_derivative_not_attested"
            return fallback
        normalized = self._normalize_screen_privacy(payload, True)
        if normalized.get("accessibility_tree_path") or normalized.get("screenshot_path"):
            normalized["evidence_mode"] = "verified_redacted"
        normalized["raw_artifacts_persisted"] = False
        normalized["git_eligible"] = False
        normalized["evidence_retention"] = "redacted_derivative_only"
        return normalized

    def _normalize_element_privacy(
        self, payload: dict[str, Any], attested: bool
    ) -> dict[str, Any]:
        normalized = super()._normalize_element_privacy(payload, attested)
        if not attested:
            # A metadata-only screen may contain names or identifiers that do
            # not match a known regex. Retain geometry and control state only.
            for key in (
                "label",
                "inferred_label",
                "resource_id",
                "view_id",
                "synonyms",
                "expected_result",
                "expected_outcome",
                "inferred_icon_semantics",
                "icon_inference",
                "semantic_function_id",
            ):
                normalized.pop(key, None)
        return normalized

    def _insert_record_row(
        self,
        connection: sqlite3.Connection,
        *,
        record_type: str,
        record_id: str,
        sequence: int,
        recorded_at: str,
        payload: dict[str, Any],
        payload_json: str,
        content_sha256: str,
    ) -> None:
        fixed_columns = [
            "record_id",
            "event_sequence",
            "run_id",
            "recorded_at",
            "provenance",
            "dataset_role",
            "review_status",
            "review_lifecycle",
            "route_lifecycle",
            "canonical_catalog_version",
            "canonical_catalog_sha256",
            "canonical_equivalence_sha256",
            "payload_json",
            "content_sha256",
        ]
        values: list[Any] = [
            record_id,
            sequence,
            self.run_id,
            recorded_at,
            PROVENANCE,
            DATASET_ROLE,
            REVIEW_STATUS,
            REVIEW_LIFECYCLE,
            ROUTE_LIFECYCLE,
            CANONICAL_CATALOG_VERSION,
            CANONICAL_CATALOG_SHA256,
            CANONICAL_EQUIVALENCE_SHA256,
            payload_json,
            content_sha256,
        ]
        for column, (sql_type, source_key) in _TABLE_FIELDS[record_type].items():
            fixed_columns.append(column)
            values.append(_sqlite_value(payload.get(source_key), sql_type, column.endswith("_json")))
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f"INSERT INTO {record_type} ({', '.join(fixed_columns)}) VALUES ({placeholders})",
            values,
        )

    def _ensure_schema(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS corpus_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS event_log (
                  sequence INTEGER PRIMARY KEY,
                  event_id TEXT NOT NULL UNIQUE,
                  record_type TEXT NOT NULL,
                  record_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  recorded_at TEXT NOT NULL,
                  provenance TEXT NOT NULL CHECK (provenance = 'real_device_observation_candidate'),
                  dataset_role TEXT NOT NULL CHECK (dataset_role = 'real_device_observation_candidate'),
                  review_status TEXT NOT NULL CHECK (review_status = 'unreviewed_candidate'),
                  review_lifecycle TEXT NOT NULL CHECK (review_lifecycle = 'candidate'),
                  route_lifecycle TEXT NOT NULL CHECK (route_lifecycle = 'shadow'),
                  canonical_catalog_version TEXT NOT NULL,
                  canonical_catalog_sha256 TEXT NOT NULL,
                  canonical_equivalence_sha256 TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  envelope_json TEXT NOT NULL,
                  event_sha256 TEXT NOT NULL,
                  UNIQUE(record_type, record_id)
                )
                """
            )
            common = [
                "record_id TEXT PRIMARY KEY",
                "event_sequence INTEGER NOT NULL UNIQUE",
                "run_id TEXT NOT NULL",
                "recorded_at TEXT NOT NULL",
                "provenance TEXT NOT NULL CHECK (provenance = 'real_device_observation_candidate')",
                "dataset_role TEXT NOT NULL CHECK (dataset_role = 'real_device_observation_candidate')",
                "review_status TEXT NOT NULL CHECK (review_status = 'unreviewed_candidate')",
                "review_lifecycle TEXT NOT NULL CHECK (review_lifecycle = 'candidate')",
                "route_lifecycle TEXT NOT NULL CHECK (route_lifecycle = 'shadow')",
                "canonical_catalog_version TEXT NOT NULL",
                "canonical_catalog_sha256 TEXT NOT NULL",
                "canonical_equivalence_sha256 TEXT NOT NULL",
                "payload_json TEXT NOT NULL",
                "content_sha256 TEXT NOT NULL",
            ]
            for table in RECORD_TABLES:
                custom = [f"{name} {spec[0]}" for name, spec in _TABLE_FIELDS[table].items()]
                connection.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(common + custom)}, "
                    "FOREIGN KEY(event_sequence) REFERENCES event_log(sequence))"
                )
                existing_columns = {
                    str(row[1])
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                for name, (sql_type, _) in _TABLE_FIELDS[table].items():
                    if name not in existing_columns:
                        connection.execute(
                            f'ALTER TABLE "{table}" ADD COLUMN "{name}" {sql_type}'
                        )
                connection.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{table}_run_id ON {table}(run_id)"
                )
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_append_only_{operation.casefold()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END
                        """
                    )
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS event_log_append_only_{operation.casefold()}
                    BEFORE {operation} ON event_log
                    BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END
                    """
                )
            metadata = self._fixed_identity(sqlite_values=True)
            for key, value in metadata.items():
                connection.execute(
                    "INSERT OR IGNORE INTO corpus_metadata (key, value) VALUES (?, ?)",
                    (key, str(value).casefold() if isinstance(value, bool) else str(value)),
                )
            connection.commit()
            actual = dict(connection.execute("SELECT key, value FROM corpus_metadata").fetchall())
            for key, value in metadata.items():
                expected = str(value).casefold() if isinstance(value, bool) else str(value)
                if actual.get(key) != expected:
                    raise CorpusIntegrityError(f"SQLite metadata mismatch for {key}")

    def _ensure_graph_schema(self) -> None:
        UniversalNavigationGraphRepository(self.graph_database_path)
        connection = sqlite3.connect(self.graph_database_path)
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS real_device_candidate_metadata (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS real_device_routes_shadow_insert
                BEFORE INSERT ON universal_routes
                WHEN NEW.status <> 'shadow' OR NEW.provisional <> 1
                BEGIN SELECT RAISE(ABORT, 'physical-device candidate routes must remain shadow'); END;
                CREATE TRIGGER IF NOT EXISTS real_device_routes_shadow_update
                BEFORE UPDATE ON universal_routes
                WHEN NEW.status <> 'shadow' OR NEW.provisional <> 1
                BEGIN SELECT RAISE(ABORT, 'physical-device candidate routes must remain shadow'); END;
                """
            )
            metadata = {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "provenance": PROVENANCE,
                "dataset_role": DATASET_ROLE,
                "review_status": REVIEW_STATUS,
                "review_lifecycle": REVIEW_LIFECYCLE,
                "route_lifecycle": ROUTE_LIFECYCLE,
                "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
                "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
                "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            }
            for key, value in metadata.items():
                connection.execute(
                    "INSERT OR IGNORE INTO real_device_candidate_metadata (key, value) VALUES (?, ?)",
                    (key, value),
                )
            connection.commit()
            actual = dict(
                connection.execute("SELECT key, value FROM real_device_candidate_metadata")
            )
            for key, value in metadata.items():
                if actual.get(key) != value:
                    raise CorpusIntegrityError(f"graph metadata mismatch for {key}")
        finally:
            connection.close()

    def _validate_graph_candidate(self) -> None:
        connection = sqlite3.connect(self.graph_database_path)
        try:
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "universal_routes" not in tables or "real_device_candidate_metadata" not in tables:
                raise CorpusIntegrityError("graph candidate schema is incomplete")
            invalid_routes = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM universal_routes
                    WHERE status <> 'shadow' OR provisional <> 1
                    """
                ).fetchone()[0]
            )
            if invalid_routes:
                raise CorpusIntegrityError("graph candidate contains non-shadow routes")
            metadata = dict(
                connection.execute("SELECT key, value FROM real_device_candidate_metadata")
            )
            expected = {
                "run_id": self.run_id,
                "provenance": PROVENANCE,
                "dataset_role": DATASET_ROLE,
                "review_status": REVIEW_STATUS,
                "review_lifecycle": REVIEW_LIFECYCLE,
                "route_lifecycle": ROUTE_LIFECYCLE,
                "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
                "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
                "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            }
            for key, value in expected.items():
                if metadata.get(key) != value:
                    raise CorpusIntegrityError(f"graph metadata mismatch for {key}")
        finally:
            connection.close()

    def _refresh_control_files(self, *, state: Mapping[str, Any]) -> None:
        run_status = str(state.get("run_status") or self._control_status)
        if run_status not in ALLOWED_RUN_STATUSES:
            raise CorpusIntegrityError(f"unsupported run status: {run_status}")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*), COALESCE(MAX(sequence), 0),
                       (SELECT event_id FROM event_log ORDER BY sequence DESC LIMIT 1)
                FROM event_log
                """
            ).fetchone()
            app_rows = connection.execute(
                "SELECT app_package, payload_json FROM apps ORDER BY app_package, event_sequence"
            ).fetchall()
            safety_counts = _evidence_derived_action_counts(connection)
        event_count, last_sequence, last_event_id = int(row[0]), int(row[1]), row[2]
        statuses = dict(self._control_app_statuses)
        for app_row in app_rows:
            app_package = str(app_row["app_package"] or "").strip()
            if not app_package:
                continue
            payload = json.loads(app_row["payload_json"])
            status = str(payload.get("status") or "installed_observed")
            if status not in ALLOWED_APP_STATUSES:
                raise CorpusIntegrityError(f"unsupported app observation status: {status}")
            statuses[app_package] = status
        app_statuses = [
            {"app_package": app_package, "status": status}
            for app_package, status in sorted(statuses.items())
        ]
        self._control_status = run_status
        self._control_app_statuses = statuses
        artifact_hashes = {
            DATABASE_FILENAME: sha256_file(self.database_path),
            JSONL_FILENAME: sha256_file(self.jsonl_path),
            GRAPH_DATABASE_FILENAME: sha256_file(self.graph_database_path),
        }
        now = _utc_now()
        created_at = now
        if self.manifest_path.exists():
            created_at = str(_read_json(self.manifest_path).get("created_at") or now)
        identity = self._fixed_identity()
        checkpoint = dict(
            identity,
            run_mode=RUN_MODE,
            collection_mode=self._collection_mode,
            validation_profile=self._validation_profile,
            selected_packages=list(self._selected_packages),
            inventory_packages=list(self._inventory_packages),
            inventory_snapshot=self._inventory_snapshot,
            runtime_attestation=self._runtime_attestation,
            exploration_stage=self._exploration_stage,
            goal_candidate_plan=self._goal_candidate_plan,
            tasks=self._selected_tasks,
            status=run_status,
            device_type=self._device_type,
            is_emulator=self._is_emulator,
            device_serial=self._device_serial,
            serial=self._device_serial,
            raw_artifacts_persisted=False,
            app_statuses=app_statuses,
            checkpointed_at=now,
            last_sequence=last_sequence,
            last_event_id=last_event_id,
            event_count=event_count,
            artifact_sha256=artifact_hashes,
            safety=safety_counts,
            state=_jsonable(dict(state)),
        )
        manifest = dict(
            identity,
            description="Unreviewed physical-device observations and shadow graph candidates.",
            run_mode=RUN_MODE,
            collection_mode=self._collection_mode,
            validation_profile=self._validation_profile,
            selected_packages=list(self._selected_packages),
            inventory_packages=list(self._inventory_packages),
            inventory_snapshot=self._inventory_snapshot,
            runtime_attestation=self._runtime_attestation,
            exploration_stage=self._exploration_stage,
            goal_candidate_plan=self._goal_candidate_plan,
            tasks=self._selected_tasks,
            status=run_status,
            device_type=self._device_type,
            is_emulator=self._is_emulator,
            device_serial=self._device_serial,
            serial=self._device_serial,
            device={
                "type": self._device_type,
                "is_emulator": self._is_emulator,
                "serial": self._device_serial,
            },
            raw_artifacts_persisted=False,
            git_eligible=False,
            app_statuses=app_statuses,
            created_at=created_at,
            updated_at=now,
            files={
                "database": DATABASE_FILENAME,
                "graph_candidate": GRAPH_DATABASE_FILENAME,
                "event_mirror": JSONL_FILENAME,
                "checkpoint": CHECKPOINT_FILENAME,
            },
            canonical_catalog={
                "version": CANONICAL_CATALOG_VERSION,
                "sha256": CANONICAL_CATALOG_SHA256,
                "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
                "domain_count": CANONICAL_COUNTS["domains"],
                "function_count": CANONICAL_COUNTS["physical_functions"],
                "terminal_function_count": CANONICAL_COUNTS["physical_intents"],
                "intent_count": CANONICAL_COUNTS["physical_intents"],
            },
            safety=safety_counts,
            version_policy={
                "canonical": "V15_frozen",
                "v16_v20_promotion": "forbidden",
                "v21": "research_only_noncanonical",
                "v22_plus": "forbidden",
            },
            graph_candidate={
                "provenance": PROVENANCE,
                "review_lifecycle": REVIEW_LIFECYCLE,
                "route_lifecycle": ROUTE_LIFECYCLE,
                "serving_allowed": False,
                "promotion_allowed": False,
            },
            record_tables=list(RECORD_TABLES),
            event_count=event_count,
            last_sequence=last_sequence,
            artifact_sha256=artifact_hashes,
        )
        _atomic_write_json(self.checkpoint_path, checkpoint)
        _atomic_write_json(self.manifest_path, manifest)

    def _fixed_identity(self, *, sqlite_values: bool = False) -> dict[str, Any]:
        values: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "corpus_type": CORPUS_TYPE,
            "run_id": self.run_id,
            "provenance": PROVENANCE,
            "dataset_role": DATASET_ROLE,
            "review_status": REVIEW_STATUS,
            "review_lifecycle": REVIEW_LIFECYCLE,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
            "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
            "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "canonical_mutation_allowed": False,
        }
        return values

    def _validate_control_identity(self, payload: Mapping[str, Any], label: str) -> None:
        for key, value in self._fixed_identity().items():
            if payload.get(key) != value:
                raise CorpusIntegrityError(f"{label} identity mismatch for {key}")
        if payload.get("run_mode") != RUN_MODE:
            raise CorpusIntegrityError(f"{label} run mode mismatch")
        if payload.get("collection_mode") not in ALLOWED_COLLECTION_MODES:
            raise CorpusIntegrityError(f"{label} collection mode mismatch")
        exploration_stage = payload.get("exploration_stage")
        if exploration_stage not in ALLOWED_EXPLORATION_STAGES:
            raise CorpusIntegrityError(f"{label} exploration stage mismatch")
        goal_candidate_plan = payload.get("goal_candidate_plan")
        if goal_candidate_plan is not None and not isinstance(goal_candidate_plan, Mapping):
            raise CorpusIntegrityError(f"{label} goal candidate plan mismatch")
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list) or any(
            not isinstance(task, Mapping) for task in tasks
        ):
            raise CorpusIntegrityError(f"{label} selected tasks mismatch")
        validation_profile = payload.get("validation_profile", "full_cohort")
        if validation_profile not in ALLOWED_VALIDATION_PROFILES:
            raise CorpusIntegrityError(f"{label} validation profile mismatch")
        selected_packages = payload.get("selected_packages", [])
        inventory_packages = payload.get("inventory_packages", [])
        if not isinstance(selected_packages, list) or not isinstance(inventory_packages, list):
            raise CorpusIntegrityError(f"{label} package selections must be lists")
        selected = {str(value).strip() for value in selected_packages if str(value).strip()}
        inventory = {str(value).strip() for value in inventory_packages if str(value).strip()}
        if len(selected) != len(selected_packages) or len(inventory) != len(inventory_packages):
            raise CorpusIntegrityError(f"{label} package selections must be unique and non-empty")
        if inventory and not selected.issubset(inventory):
            raise CorpusIntegrityError(f"{label} selected packages are outside inventory")
        if validation_profile == "partial_research" and not selected:
            raise CorpusIntegrityError(f"{label} partial_research requires selected packages")
        inventory_snapshot = payload.get("inventory_snapshot")
        if validation_profile == "dynamic_inventory":
            if not selected or not inventory or not isinstance(inventory_snapshot, Mapping):
                raise CorpusIntegrityError(
                    f"{label} dynamic_inventory requires selection and snapshot metadata"
                )
            included = inventory_snapshot.get("included_inventory")
            if not isinstance(included, list):
                raise CorpusIntegrityError(
                    f"{label} dynamic inventory lacks included_inventory"
                )
            included_packages = {
                str(item.get("package") or "").strip()
                for item in included
                if isinstance(item, Mapping) and str(item.get("package") or "").strip()
            }
            if included_packages != inventory:
                raise CorpusIntegrityError(
                    f"{label} dynamic inventory package mismatch"
                )
        _validate_stage_lineage(payload, label)
        if payload.get("raw_artifacts_persisted") is not False:
            raise CorpusIntegrityError(f"{label} may not claim raw artifacts were persisted")
        if payload.get("device_type") not in {
            "physical_android",
            "physical_device",
            "android_physical",
            "physical",
        }:
            raise CorpusIntegrityError(f"{label} device type is not physical Android")
        if payload.get("is_emulator") is not False:
            raise CorpusIntegrityError(f"{label} cannot attest an emulator")
        if str(payload.get("device_serial") or "").casefold().startswith("emulator-"):
            raise CorpusIntegrityError(f"{label} contains an emulator serial")
        status = payload.get("status")
        if status not in ALLOWED_RUN_STATUSES:
            raise CorpusIntegrityError(f"{label} run status mismatch")
        app_statuses = payload.get("app_statuses")
        if not isinstance(app_statuses, list):
            raise CorpusIntegrityError(f"{label} app_statuses must be a list")
        for entry in app_statuses:
            if not isinstance(entry, Mapping) or entry.get("status") not in ALLOWED_APP_STATUSES:
                raise CorpusIntegrityError(f"{label} contains an invalid app status")

    def _validate_manifest(self, manifest: Mapping[str, Any]) -> None:
        self._validate_control_identity(manifest, "manifest")
        if manifest.get("record_tables") != list(RECORD_TABLES):
            raise CorpusIntegrityError("manifest record table list mismatch")
        expected_catalog = {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "domain_count": CANONICAL_COUNTS["domains"],
            "function_count": CANONICAL_COUNTS["physical_functions"],
            "terminal_function_count": CANONICAL_COUNTS["physical_intents"],
            "intent_count": CANONICAL_COUNTS["physical_intents"],
        }
        if manifest.get("canonical_catalog") != expected_catalog:
            raise CorpusIntegrityError("manifest canonical catalog metadata mismatch")
        if manifest.get("safety") != {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }:
            raise CorpusIntegrityError("manifest safety invariant mismatch")
        policy = manifest.get("version_policy", {})
        if not isinstance(policy, Mapping) or (
            policy.get("v16_v20_promotion") != "forbidden"
            or policy.get("v21") != "research_only_noncanonical"
            or policy.get("v22_plus") != "forbidden"
        ):
            raise CorpusIntegrityError("manifest catalog version policy mismatch")


def _contains_forbidden_gold(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_contains_forbidden_gold(key) or _contains_forbidden_gold(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_forbidden_gold(item) for item in value)
    return isinstance(value, str) and value.strip().casefold() in FORBIDDEN_GOLD_VALUES


def _reject_catalog_promotion(payload: Mapping[str, Any]) -> None:
    governed_keys = {
        "proposed_catalog_version",
        "promoted_catalog_version",
        "target_catalog_version",
        "candidate_catalog_version",
    }
    for key in governed_keys:
        if key not in payload or payload[key] in (None, "", CANONICAL_CATALOG_VERSION, "V15", "v15"):
            continue
        raise CorpusIntegrityError(
            f"physical-device candidates cannot promote or implement catalog version via {key}"
        )
