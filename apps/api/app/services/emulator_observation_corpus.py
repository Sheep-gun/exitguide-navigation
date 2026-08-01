"""Append-only storage for evidence collected from the Android emulator.

The emulator corpus is deliberately separate from the canonical navigation
catalog.  SQLite is the authoritative event store and ``observations.jsonl``
is a reproducible, append-only mirror.  A partially written mirror is repaired
from SQLite when a run is resumed.

This module does not redact screenshots.  It only accepts evidence paths after
the collector explicitly attests that its privacy review succeeded.  Without
that attestation, the screen (and its elements) is stored as metadata only.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "1.0.0"
CORPUS_TYPE = "emulator-observation"
PROVENANCE = "emulator_observation"
ROUTE_LIFECYCLE = "shadow"

# Frozen baseline only.  Corpus records may propose shadow routes, but may not
# mutate or promote a catalog version.
CANONICAL_CATALOG_VERSION = "15.0.0"
CANONICAL_CATALOG_SHA256 = "e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24"
CANONICAL_EQUIVALENCE_SHA256 = "197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8"
CANONICAL_COUNTS = {"domains": 179, "physical_functions": 2866, "physical_intents": 2660}

DATABASE_FILENAME = "corpus.sqlite"
JSONL_FILENAME = "observations.jsonl"
MANIFEST_FILENAME = "manifest.json"
CHECKPOINT_FILENAME = "checkpoint.json"

RECORD_TABLES = (
    "apps",
    "runs",
    "screens",
    "elements",
    "transitions",
    "goals",
    "failures",
    "metrics",
    "annotations",
)

_ID_FIELDS = {
    "apps": "app_observation_id",
    "runs": "run_observation_id",
    "screens": "screen_id",
    "elements": "element_id",
    "transitions": "transition_id",
    "goals": "goal_id",
    "failures": "failure_id",
    "metrics": "metric_id",
    "annotations": "annotation_id",
}

# column -> (SQLite type, payload source key)
_TABLE_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "apps": {
        "app_package": ("TEXT", "app_package"),
        "app_name": ("TEXT", "app_name"),
        "app_version": ("TEXT", "app_version"),
        "locale": ("TEXT", "locale"),
        "install_source": ("TEXT", "install_source"),
        "store_url": ("TEXT", "store_url"),
    },
    "runs": {
        "device_id": ("TEXT", "device_id"),
        "avd_name": ("TEXT", "avd_name"),
        "api_base_url": ("TEXT", "api_base_url"),
        "lifecycle_event": ("TEXT", "lifecycle_event"),
        "resumed_from_sequence": ("INTEGER", "resumed_from_sequence"),
        "started_at": ("TEXT", "started_at"),
    },
    "screens": {
        "screen_id": ("TEXT", "screen_id"),
        "app_package": ("TEXT", "app_package"),
        "app_name": ("TEXT", "app_name"),
        "app_version": ("TEXT", "app_version"),
        "locale": ("TEXT", "locale"),
        "screen_signature": ("TEXT", "screen_signature"),
        "screenshot_path": ("TEXT", "screenshot_path"),
        "screenshot_sha256": ("TEXT", "screenshot_sha256"),
        "accessibility_tree_path": ("TEXT", "accessibility_tree_path"),
        "accessibility_tree_sha256": ("TEXT", "accessibility_tree_sha256"),
        "activity_name": ("TEXT", "activity_name"),
        "title_text": ("TEXT", "title_text"),
        "visible_texts_json": ("TEXT", "visible_texts"),
        "content_descriptions_json": ("TEXT", "content_descriptions"),
        "resource_ids_json": ("TEXT", "resource_ids"),
        "scrollable_regions_json": ("TEXT", "scrollable_regions"),
        "screen_type": ("TEXT", "screen_type"),
        "login_state": ("TEXT", "login_state"),
        "prerequisite": ("TEXT", "prerequisite"),
        "prerequisites_json": ("TEXT", "prerequisites"),
        "contains_personal_data": ("INTEGER", "contains_personal_data"),
        "evidence_mode": ("TEXT", "evidence_mode"),
        "privacy_verified": ("INTEGER", "privacy_verified"),
        "collected_at": ("TEXT", "collected_at"),
    },
    "elements": {
        "element_id": ("TEXT", "element_id"),
        "screen_id": ("TEXT", "screen_id"),
        "text": ("TEXT", "text"),
        "content_description": ("TEXT", "content_description"),
        "resource_id": ("TEXT", "resource_id"),
        "class_name": ("TEXT", "class_name"),
        "bounds_json": ("TEXT", "bounds"),
        "clickable": ("INTEGER", "clickable"),
        "enabled": ("INTEGER", "enabled"),
        "selected": ("INTEGER", "selected"),
        "icon_inference": ("TEXT", "icon_inference"),
        "inferred_icon_semantics_json": ("TEXT", "inferred_icon_semantics"),
        "semantic_function_id": ("TEXT", "semantic_function_id"),
        "synonyms_json": ("TEXT", "synonyms"),
        "expected_result": ("TEXT", "expected_result"),
        "expected_outcome": ("TEXT", "expected_outcome"),
        "risk_level": ("TEXT", "risk_level"),
        "is_final_action": ("INTEGER", "is_final_action"),
        "confidence": ("REAL", "confidence"),
        "evidence_json": ("TEXT", "evidence"),
        "evidence_mode": ("TEXT", "evidence_mode"),
        "privacy_verified": ("INTEGER", "privacy_verified"),
    },
    "transitions": {
        "transition_id": ("TEXT", "transition_id"),
        "source_screen_id": ("TEXT", "source_screen_id"),
        "target_screen_id": ("TEXT", "target_screen_id"),
        "element_id": ("TEXT", "element_id"),
        "ui_element_id": ("TEXT", "ui_element_id"),
        "action_type": ("TEXT", "action_type"),
        "selected_label": ("TEXT", "selected_label"),
        "auto_action_guard_json": ("TEXT", "auto_action_guard"),
        "action_coordinates_json": ("TEXT", "action_coordinates"),
        "coordinates_json": ("TEXT", "coordinates"),
        "scroll_direction": ("TEXT", "scroll_direction"),
        "scroll_distance": ("REAL", "scroll_distance"),
        "transition_time_ms": ("INTEGER", "transition_time_ms"),
        "success": ("INTEGER", "success"),
        "can_go_back": ("INTEGER", "can_go_back"),
        "back_available": ("INTEGER", "back_available"),
        "repeated_or_loop": ("INTEGER", "repeated_or_loop"),
        "is_loop": ("INTEGER", "is_loop"),
        "error_content": ("TEXT", "error_content"),
        "error_text": ("TEXT", "error_text"),
        "auto_executed": ("INTEGER", "auto_executed"),
        "is_final_action": ("INTEGER", "is_final_action"),
        "unsafe_action": ("INTEGER", "unsafe_action"),
    },
    "goals": {
        "goal_id": ("TEXT", "goal_id"),
        "app_package": ("TEXT", "app_package"),
        "goal_text": ("TEXT", "goal_text"),
        "canonical_goal_id": ("TEXT", "canonical_goal_id"),
        "standard_goal_id": ("TEXT", "standard_goal_id"),
        "semantic_function_id": ("TEXT", "semantic_function_id"),
        "terminal_candidate_screen_id": ("TEXT", "terminal_candidate_screen_id"),
        "terminal_candidate_element_id": ("TEXT", "terminal_candidate_element_id"),
        "terminal_confidence": ("REAL", "terminal_confidence"),
        "status": ("TEXT", "status"),
        "expected_terminal": ("TEXT", "expected_terminal"),
        "evidence_json": ("TEXT", "evidence"),
    },
    "failures": {
        "failure_id": ("TEXT", "failure_id"),
        "app_package": ("TEXT", "app_package"),
        "goal_id": ("TEXT", "goal_id"),
        "user_goal": ("TEXT", "user_goal"),
        "screen_id": ("TEXT", "screen_id"),
        "source_screen_id": ("TEXT", "source_screen_id"),
        "selected_candidate": ("TEXT", "selected_candidate"),
        "correct_candidate": ("TEXT", "correct_candidate"),
        "failure_reason": ("TEXT", "failure_reason"),
        "missing_synonym_or_rule": ("TEXT", "missing_synonym_or_rule"),
        "required_synonym_or_label": ("TEXT", "required_synonym_or_label"),
        "policy_correction": ("TEXT", "policy_correction"),
        "policy_change": ("TEXT", "policy_change"),
        "retry_result": ("TEXT", "retry_result"),
        "retest_result": ("TEXT", "retest_result"),
    },
    "metrics": {
        "metric_id": ("TEXT", "metric_id"),
        "app_package": ("TEXT", "app_package"),
        "goal_id": ("TEXT", "goal_id"),
        "metric_dimension": ("TEXT", "metric_dimension"),
        "destination_found_success": ("INTEGER", "destination_found_success"),
        "wrong_terminal_destination": ("INTEGER", "wrong_terminal_destination"),
        "exploration_time_ms": ("INTEGER", "exploration_time_ms"),
        "click_count": ("INTEGER", "click_count"),
        "scroll_count": ("INTEGER", "scroll_count"),
        "back_count": ("INTEGER", "back_count"),
        "repeat_screen_visit_count": ("INTEGER", "repeat_screen_visit_count"),
        "user_intervention_count": ("INTEGER", "user_intervention_count"),
        "unsafe_auto_click_count": ("INTEGER", "unsafe_auto_click_count"),
        "final_action_auto_click_count": ("INTEGER", "final_action_auto_click_count"),
        "graph_reuse_rate": ("REAL", "graph_reuse_rate"),
        "perception_clickable_recall": ("REAL", "perception_clickable_recall"),
        "perception_icon_text_link_accuracy": ("REAL", "perception_icon_text_link_accuracy"),
        "semantic_goal_match_accuracy": ("REAL", "semantic_goal_match_accuracy"),
        "semantic_disambiguation_accuracy": ("REAL", "semantic_disambiguation_accuracy"),
        "value": ("REAL", "value"),
    },
    "annotations": {
        "annotation_id": ("TEXT", "annotation_id"),
        "entity_type": ("TEXT", "entity_type"),
        "entity_id": ("TEXT", "entity_id"),
        "label": ("TEXT", "label"),
        "value_json": ("TEXT", "value"),
        "confidence": ("REAL", "confidence"),
        "reviewer": ("TEXT", "reviewer"),
        "status": ("TEXT", "status"),
    },
}

_SCREEN_PRIVATE_FIELDS = {
    "screenshot_path",
    "screenshot_sha256",
    "accessibility_tree_path",
    "accessibility_tree_sha256",
    "title_text",
    "visible_texts",
    "content_descriptions",
    "raw_accessibility_tree",
    "raw_ocr",
    "ocr_text",
    "screenshot_bytes",
}
_ELEMENT_PRIVATE_FIELDS = {"text", "content_description", "evidence", "raw_ocr", "ocr_text"}


class CorpusIntegrityError(RuntimeError):
    """Raised when an existing corpus or proposed record violates invariants."""


@dataclass(frozen=True)
class CorpusRecord:
    sequence: int
    event_id: str
    record_type: str
    record_id: str
    content_sha256: str
    payload: dict[str, Any]
    appended: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class EmulatorObservationCorpus:
    """A resumable run-local emulator observation corpus.

    ``output_directory`` must be dedicated to one ``run_id``.  Calling an
    append method again with the same record id and identical content is an
    idempotent retry; a conflicting retry fails closed.
    """

    def __init__(self, output_directory: Path | str, *, run_id: str, resume: bool = True) -> None:
        if not str(run_id).strip():
            raise ValueError("run_id must not be empty")
        self.output_directory = Path(output_directory).resolve()
        self.run_id = str(run_id).strip()
        self.database_path = self.output_directory / DATABASE_FILENAME
        self.jsonl_path = self.output_directory / JSONL_FILENAME
        self.manifest_path = self.output_directory / MANIFEST_FILENAME
        self.checkpoint_path = self.output_directory / CHECKPOINT_FILENAME
        self._lock = threading.RLock()
        self.output_directory.mkdir(parents=True, exist_ok=True)

        existing = self.manifest_path.exists() or self.database_path.exists() or self.jsonl_path.exists()
        if existing and not resume:
            raise FileExistsError(f"corpus already exists: {self.output_directory}")

        self._ensure_schema()
        self.jsonl_path.touch(exist_ok=True)
        if self.manifest_path.exists():
            self._validate_manifest(_read_json(self.manifest_path))
        self._validate_database_events()
        self._sync_jsonl_from_database()
        self._refresh_control_files(state=self.resume_state)

    @property
    def resume_state(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {}
        checkpoint = _read_json(self.checkpoint_path)
        self._validate_control_identity(checkpoint, "checkpoint")
        state = checkpoint.get("state", {})
        if not isinstance(state, dict):
            raise CorpusIntegrityError("checkpoint state must be an object")
        return dict(state)

    def save_checkpoint(self, state: Mapping[str, Any] | None = None) -> Path:
        with self._lock:
            self._refresh_control_files(state=dict(state or {}))
        return self.checkpoint_path

    def append_app(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("apps", payload, record_id=record_id)

    def append_run(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("runs", payload, record_id=record_id or self.run_id)

    def append_screen(
        self,
        payload: Mapping[str, Any],
        *,
        record_id: str | None = None,
        privacy_verified: bool | None = None,
    ) -> CorpusRecord:
        return self.append(
            "screens", payload, record_id=record_id, privacy_verified=privacy_verified
        )

    def append_element(
        self,
        payload: Mapping[str, Any],
        *,
        record_id: str | None = None,
        privacy_verified: bool | None = None,
    ) -> CorpusRecord:
        return self.append(
            "elements", payload, record_id=record_id, privacy_verified=privacy_verified
        )

    def append_transition(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("transitions", payload, record_id=record_id)

    def append_goal(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("goals", payload, record_id=record_id)

    def append_failure(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("failures", payload, record_id=record_id)

    def append_metric(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("metrics", payload, record_id=record_id)

    def append_annotation(self, payload: Mapping[str, Any], *, record_id: str | None = None) -> CorpusRecord:
        return self.append("annotations", payload, record_id=record_id)

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
                      provenance, route_lifecycle, canonical_catalog_version,
                      canonical_catalog_sha256, canonical_equivalence_sha256,
                      content_sha256, payload_json, envelope_json, event_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        event_id,
                        record_type,
                        record_id,
                        self.run_id,
                        recorded_at,
                        PROVENANCE,
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

    def counts(self) -> dict[str, int]:
        with self._connection() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in RECORD_TABLES
            }

    def verify_integrity(self) -> dict[str, Any]:
        """Verify event hashes, policy pins, mirror ordering, and artifact hashes."""
        errors: list[str] = []
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM event_log ORDER BY sequence").fetchall()
            for expected_sequence, row in enumerate(rows, start=1):
                if int(row["sequence"]) != expected_sequence:
                    errors.append(f"non-contiguous SQLite sequence at {expected_sequence}")
                try:
                    payload = json.loads(row["payload_json"])
                    envelope = json.loads(row["envelope_json"])
                except json.JSONDecodeError as exc:
                    errors.append(f"invalid JSON at sequence {row['sequence']}: {exc}")
                    continue
                if canonical_sha256(payload) != row["content_sha256"]:
                    errors.append(f"payload hash mismatch at sequence {row['sequence']}")
                claimed_event_hash = envelope.pop("event_sha256", None)
                if canonical_sha256(envelope) != claimed_event_hash or claimed_event_hash != row["event_sha256"]:
                    errors.append(f"event hash mismatch at sequence {row['sequence']}")
                if payload.get("provenance") != PROVENANCE:
                    errors.append(f"provenance mismatch at sequence {row['sequence']}")
                if payload.get("route_lifecycle") != ROUTE_LIFECYCLE:
                    errors.append(f"route lifecycle mismatch at sequence {row['sequence']}")
                if payload.get("canonical_catalog_version") != CANONICAL_CATALOG_VERSION:
                    errors.append(f"catalog version mismatch at sequence {row['sequence']}")
                if payload.get("canonical_catalog_sha256") != CANONICAL_CATALOG_SHA256:
                    errors.append(f"catalog hash mismatch at sequence {row['sequence']}")
                table_row = connection.execute(
                    f"SELECT content_sha256, payload_json FROM {row['record_type']} WHERE record_id = ?",
                    (row["record_id"],),
                ).fetchone()
                if table_row is None:
                    errors.append(f"missing typed row at sequence {row['sequence']}")
                elif (
                    table_row["content_sha256"] != row["content_sha256"]
                    or table_row["payload_json"] != row["payload_json"]
                ):
                    errors.append(f"typed row mismatch at sequence {row['sequence']}")

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
        expected_hashes = manifest.get("artifact_sha256", {})
        actual_hashes = {
            DATABASE_FILENAME: sha256_file(self.database_path),
            JSONL_FILENAME: sha256_file(self.jsonl_path),
        }
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
        normalized = _apply_field_aliases(record_type, normalized)
        fixed = {
            "run_id": self.run_id,
            "provenance": PROVENANCE,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
            "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
            "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "canonical_mutation_allowed": False,
        }
        for key, value in fixed.items():
            if key in normalized and normalized[key] != value:
                raise CorpusIntegrityError(f"record cannot override fixed {key}")
            normalized[key] = value

        if record_type == "screens":
            attested = normalized.get("privacy_verified") is True if privacy_verified is None else privacy_verified is True
            normalized = self._normalize_screen_privacy(normalized, attested)
        elif record_type == "elements":
            if privacy_verified is None:
                attested = self._screen_privacy_verified(str(normalized.get("screen_id", "")))
            else:
                attested = privacy_verified is True
            normalized = self._normalize_element_privacy(normalized, attested)
        if record_type == "transitions":
            if normalized.get("auto_executed") is True and (
                normalized.get("is_final_action") is True or normalized.get("unsafe_action") is True
            ):
                raise CorpusIntegrityError("unsafe or final consequential actions cannot be auto-executed")
        if record_type == "metrics":
            for key in ("unsafe_auto_click_count", "final_action_auto_click_count"):
                if int(normalized.get(key, 0) or 0) != 0:
                    raise CorpusIntegrityError(f"{key} must remain zero")
        return normalized

    def _normalize_screen_privacy(self, payload: dict[str, Any], attested: bool) -> dict[str, Any]:
        if not attested:
            visible = payload.get("visible_texts")
            descriptions = payload.get("content_descriptions")
            payload["visible_text_count"] = len(visible) if isinstance(visible, list) else 0
            payload["content_description_count"] = len(descriptions) if isinstance(descriptions, list) else 0
            for key in _SCREEN_PRIVATE_FIELDS:
                payload.pop(key, None)
            payload.update(
                {
                    "privacy_verified": False,
                    "evidence_mode": "metadata_only",
                    "screenshot_persisted": False,
                    "accessibility_tree_persisted": False,
                    "privacy_fallback_reason": "privacy_review_not_verified",
                }
            )
            return payload

        screenshot = self._verified_artifact(payload.get("screenshot_path"), "screenshot")
        tree = self._verified_artifact(payload.get("accessibility_tree_path"), "accessibility tree")
        if screenshot is None:
            # Privacy was reviewed, but there is still no screenshot evidence.
            payload.pop("screenshot_path", None)
            payload.pop("screenshot_sha256", None)
            payload["screenshot_persisted"] = False
        else:
            payload["screenshot_path"] = screenshot[0]
            payload["screenshot_sha256"] = screenshot[1]
            payload["screenshot_persisted"] = True
        if tree is None:
            payload.pop("accessibility_tree_path", None)
            payload.pop("accessibility_tree_sha256", None)
            payload["accessibility_tree_persisted"] = False
        else:
            payload["accessibility_tree_path"] = tree[0]
            payload["accessibility_tree_sha256"] = tree[1]
            payload["accessibility_tree_persisted"] = True
        payload["privacy_verified"] = True
        payload["evidence_mode"] = "verified_evidence" if screenshot is not None else "verified_metadata"
        return payload

    def _normalize_element_privacy(self, payload: dict[str, Any], attested: bool) -> dict[str, Any]:
        if not attested:
            for key in _ELEMENT_PRIVATE_FIELDS:
                payload.pop(key, None)
            payload.update(
                {
                    "privacy_verified": False,
                    "evidence_mode": "metadata_only",
                    "privacy_fallback_reason": "screen_privacy_review_not_verified",
                }
            )
        else:
            payload["privacy_verified"] = True
            payload.setdefault("evidence_mode", "verified_metadata")
        return payload

    def _verified_artifact(self, value: Any, label: str) -> tuple[str, str] | None:
        if value in (None, ""):
            return None
        path = Path(str(value)).resolve()
        if not path.is_file():
            raise CorpusIntegrityError(f"verified {label} does not exist: {path}")
        try:
            relative = path.relative_to(self.output_directory)
        except ValueError as exc:
            raise CorpusIntegrityError(
                f"verified {label} must be inside the run corpus directory"
            ) from exc
        return relative.as_posix(), sha256_file(path)

    def _screen_privacy_verified(self, screen_id: str) -> bool:
        if not screen_id:
            return False
        with self._connection() as connection:
            row = connection.execute(
                "SELECT privacy_verified FROM screens WHERE screen_id = ? ORDER BY event_sequence DESC LIMIT 1",
                (screen_id,),
            ).fetchone()
        return bool(row and row[0] == 1)

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
                """
                CREATE TABLE IF NOT EXISTS corpus_metadata (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
                """
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
                  provenance TEXT NOT NULL CHECK (provenance = 'emulator_observation'),
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
                "provenance TEXT NOT NULL CHECK (provenance = 'emulator_observation')",
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
                # Additive schema evolution keeps resumable research runs
                # readable when new independently-verifiable evidence fields
                # are introduced. Existing rows remain NULL and validators
                # decide whether a field is required for their run profile.
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
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_append_only_update
                    BEFORE UPDATE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END
                    """
                )
                connection.execute(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_append_only_delete
                    BEFORE DELETE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END
                    """
                )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS event_log_append_only_update
                BEFORE UPDATE ON event_log
                BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS event_log_append_only_delete
                BEFORE DELETE ON event_log
                BEGIN SELECT RAISE(ABORT, 'event_log is append-only'); END
                """
            )
            metadata = {
                "schema_version": SCHEMA_VERSION,
                "corpus_type": CORPUS_TYPE,
                "run_id": self.run_id,
                "provenance": PROVENANCE,
                "route_lifecycle": ROUTE_LIFECYCLE,
                "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
                "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
                "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
                "canonical_mutation_allowed": "false",
            }
            for key, value in metadata.items():
                connection.execute(
                    "INSERT OR IGNORE INTO corpus_metadata (key, value) VALUES (?, ?)",
                    (key, value),
                )
            connection.commit()
            actual = dict(connection.execute("SELECT key, value FROM corpus_metadata").fetchall())
            for key, value in metadata.items():
                if actual.get(key) != value:
                    raise CorpusIntegrityError(f"SQLite metadata mismatch for {key}")

    def _sync_jsonl_from_database(self) -> None:
        with self._lock:
            events = self._read_jsonl_events()
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT sequence, event_id, envelope_json FROM event_log ORDER BY sequence"
                ).fetchall()
            if len(events) > len(rows):
                raise CorpusIntegrityError("JSONL contains events absent from SQLite")
            for index, event in enumerate(events):
                row = rows[index]
                if event.get("sequence") != row["sequence"] or event.get("event_id") != row["event_id"]:
                    raise CorpusIntegrityError(f"JSONL diverges from SQLite at sequence {index + 1}")
                if _canonical_json(event) != row["envelope_json"]:
                    raise CorpusIntegrityError(f"JSONL content diverges from SQLite at sequence {index + 1}")
            for row in rows[len(events) :]:
                self._append_jsonl(row["envelope_json"])

    def _validate_database_events(self) -> None:
        """Validate authoritative rows before a resume can refresh control hashes."""
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM event_log ORDER BY sequence").fetchall()
            for expected_sequence, row in enumerate(rows, start=1):
                if int(row["sequence"]) != expected_sequence:
                    raise CorpusIntegrityError(
                        f"non-contiguous SQLite sequence at {expected_sequence}"
                    )
                if row["record_type"] not in RECORD_TABLES:
                    raise CorpusIntegrityError(
                        f"unknown record type at sequence {row['sequence']}"
                    )
                try:
                    payload = json.loads(row["payload_json"])
                    envelope = json.loads(row["envelope_json"])
                except json.JSONDecodeError as exc:
                    raise CorpusIntegrityError(
                        f"invalid SQLite JSON at sequence {row['sequence']}"
                    ) from exc
                if canonical_sha256(payload) != row["content_sha256"]:
                    raise CorpusIntegrityError(
                        f"SQLite payload hash mismatch at sequence {row['sequence']}"
                    )
                claimed_event_sha = envelope.pop("event_sha256", None)
                if (
                    canonical_sha256(envelope) != claimed_event_sha
                    or claimed_event_sha != row["event_sha256"]
                ):
                    raise CorpusIntegrityError(
                        f"SQLite event hash mismatch at sequence {row['sequence']}"
                    )
                typed = connection.execute(
                    f"SELECT content_sha256, payload_json FROM {row['record_type']} WHERE record_id = ?",
                    (row["record_id"],),
                ).fetchone()
                if typed is None or typed["content_sha256"] != row["content_sha256"] or typed["payload_json"] != row["payload_json"]:
                    raise CorpusIntegrityError(
                        f"SQLite typed row mismatch at sequence {row['sequence']}"
                    )
            typed_total = sum(
                int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in RECORD_TABLES
            )
            if typed_total != len(rows):
                raise CorpusIntegrityError(
                    f"SQLite typed/event count mismatch: {typed_total}/{len(rows)}"
                )

    def _append_jsonl(self, envelope_json: str) -> None:
        with self.jsonl_path.open("ab") as stream:
            stream.write(envelope_json.encode("utf-8") + b"\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _read_jsonl_events(self, errors: list[str] | None = None) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.jsonl_path.exists():
            return events
        with self.jsonl_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    claimed = event.pop("event_sha256", None)
                    actual = canonical_sha256(event)
                    event["event_sha256"] = claimed
                    if claimed != actual:
                        raise CorpusIntegrityError(f"JSONL event hash mismatch at line {line_number}")
                    events.append(event)
                except (json.JSONDecodeError, CorpusIntegrityError) as exc:
                    if errors is None:
                        raise CorpusIntegrityError(f"invalid JSONL at line {line_number}: {exc}") from exc
                    errors.append(f"invalid JSONL at line {line_number}: {exc}")
        return events

    def _refresh_control_files(self, *, state: Mapping[str, Any]) -> None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*), COALESCE(MAX(sequence), 0), MAX(event_id) FROM event_log"
            ).fetchone()
        event_count, last_sequence, last_event_id = int(row[0]), int(row[1]), row[2]
        artifact_hashes = {
            DATABASE_FILENAME: sha256_file(self.database_path),
            JSONL_FILENAME: sha256_file(self.jsonl_path),
        }
        now = _utc_now()
        created_at = now
        if self.manifest_path.exists():
            previous = _read_json(self.manifest_path)
            created_at = str(previous.get("created_at") or now)
        identity = {
            "schema_version": SCHEMA_VERSION,
            "corpus_type": CORPUS_TYPE,
            "run_id": self.run_id,
            "provenance": PROVENANCE,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
            "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
            "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "canonical_mutation_allowed": False,
        }
        checkpoint = dict(
            identity,
            checkpointed_at=now,
            last_sequence=last_sequence,
            last_event_id=last_event_id,
            event_count=event_count,
            artifact_sha256=artifact_hashes,
            state=_jsonable(dict(state)),
        )
        manifest = dict(
            identity,
            description="Run-local Android emulator UI observation corpus and shadow graph evidence.",
            created_at=created_at,
            updated_at=now,
            files={
                "database": DATABASE_FILENAME,
                "event_mirror": JSONL_FILENAME,
                "checkpoint": CHECKPOINT_FILENAME,
            },
            canonical_counts=CANONICAL_COUNTS,
            canonical_catalog={
                "version": CANONICAL_CATALOG_VERSION,
                "sha256": CANONICAL_CATALOG_SHA256,
                "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
                "domain_count": CANONICAL_COUNTS["domains"],
                "function_count": CANONICAL_COUNTS["physical_functions"],
                "terminal_function_count": CANONICAL_COUNTS["physical_intents"],
                "intent_count": CANONICAL_COUNTS["physical_intents"],
            },
            safety={
                "unsafe_auto_click_count": 0,
                "final_action_auto_click_count": 0,
            },
            immutable_policies={
                "canonical_replacement": "forbidden_without_explicit_approval",
                "candidate_route_lifecycle": ROUTE_LIFECYCLE,
                "final_consequential_action_owner": "user",
            },
            record_tables=list(RECORD_TABLES),
            event_count=event_count,
            last_sequence=last_sequence,
            artifact_sha256=artifact_hashes,
        )
        _atomic_write_json(self.checkpoint_path, checkpoint)
        _atomic_write_json(self.manifest_path, manifest)

    def _validate_control_identity(self, payload: Mapping[str, Any], label: str) -> None:
        expected = {
            "schema_version": SCHEMA_VERSION,
            "corpus_type": CORPUS_TYPE,
            "run_id": self.run_id,
            "provenance": PROVENANCE,
            "route_lifecycle": ROUTE_LIFECYCLE,
            "canonical_catalog_version": CANONICAL_CATALOG_VERSION,
            "canonical_catalog_sha256": CANONICAL_CATALOG_SHA256,
            "canonical_equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "canonical_mutation_allowed": False,
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise CorpusIntegrityError(f"{label} identity mismatch for {key}")

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
        expected_safety = {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }
        if manifest.get("safety") != expected_safety:
            raise CorpusIntegrityError("manifest safety invariant mismatch")

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


def _sqlite_value(value: Any, sql_type: str, serialize_json: bool) -> Any:
    if value is None:
        return None
    if serialize_json:
        return _canonical_json(value)
    if sql_type == "INTEGER" and isinstance(value, bool):
        return int(value)
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return _canonical_json(value)
    return value


def _apply_field_aliases(record_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep objective names and early collector names queryable side by side."""
    aliases: dict[str, tuple[tuple[str, str], ...]] = {
        "screens": (("prerequisite", "prerequisites"),),
        "elements": (
            ("icon_inference", "inferred_icon_semantics"),
            ("expected_result", "expected_outcome"),
        ),
        "transitions": (
            ("action_coordinates", "coordinates"),
            ("can_go_back", "back_available"),
            ("repeated_or_loop", "is_loop"),
            ("error_content", "error_text"),
        ),
        "goals": (("canonical_goal_id", "standard_goal_id"),),
        "failures": (
            ("missing_synonym_or_rule", "required_synonym_or_label"),
            ("policy_correction", "policy_change"),
            ("retry_result", "retest_result"),
        ),
    }
    for left, right in aliases.get(record_type, ()):
        if left in payload and right not in payload:
            payload[right] = (
                [payload[left]]
                if right in {"prerequisites", "inferred_icon_semantics"}
                else payload[left]
            )
        elif right in payload and left not in payload:
            value = payload[right]
            if left == "prerequisite" and isinstance(value, list):
                payload[left] = "; ".join(str(item) for item in value)
            elif left == "icon_inference" and isinstance(value, list):
                payload[left] = "; ".join(str(item) for item in value)
            else:
                payload[left] = value
    if record_type == "failures":
        if "goal_text" in payload and "user_goal" not in payload:
            payload["user_goal"] = payload["goal_text"]
        if "source_screen_id" in payload and "screen_id" not in payload:
            payload["screen_id"] = payload["source_screen_id"]
    return payload


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_jsonable(item) for item in value]
        return sorted(items, key=_canonical_json)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite float values are not valid corpus data")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusIntegrityError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CorpusIntegrityError(f"{path.name} must contain an object")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = (_canonical_json(payload) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 7:
                    raise
                # Windows indexers/real-time scanners can briefly hold the
                # destination between close and replace.  Preserve atomicity
                # while tolerating that bounded transient lock.
                time.sleep(0.04 * (attempt + 1))
    finally:
        if temporary.exists():
            temporary.unlink()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
