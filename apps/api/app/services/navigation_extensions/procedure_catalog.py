from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .models import ProcedureDefinition, ProcedureSelection, ProcedureStep
from .predicates import PredicateError, all_conditions


SCHEMA_SQL = """
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE procedures (
    procedure_id TEXT PRIMARY KEY,
    primary_goal_id TEXT NOT NULL,
    compatible_goal_ids_json TEXT NOT NULL,
    capability_id TEXT,
    app_package TEXT,
    compatible_app_versions_json TEXT NOT NULL,
    locales_json TEXT NOT NULL,
    execution_mode TEXT NOT NULL,
    validation_count INTEGER NOT NULL CHECK (validation_count >= 0),
    fast_path_min_validation_count INTEGER NOT NULL CHECK (fast_path_min_validation_count >= 1),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    parameter_schema_json TEXT NOT NULL,
    default_parameters_json TEXT NOT NULL,
    entry_conditions_json TEXT NOT NULL,
    completion_conditions_json TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    status TEXT NOT NULL,
    generation_id TEXT NOT NULL
);

CREATE TABLE procedure_steps (
    procedure_id TEXT NOT NULL REFERENCES procedures(procedure_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    immediate_subgoal TEXT NOT NULL,
    expected_concept_id TEXT,
    preferred_role_id TEXT,
    transition_id TEXT,
    preconditions_json TEXT NOT NULL,
    completion_check_json TEXT NOT NULL,
    fallback_policy_json TEXT NOT NULL,
    PRIMARY KEY (procedure_id, ordinal)
);

CREATE INDEX procedure_goal_idx ON procedures(primary_goal_id, status);
CREATE INDEX procedure_app_idx ON procedures(app_package, status);
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _require_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _validate_parameters(schema: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
    if schema.get("type", "object") != "object":
        raise ValueError("procedure parameter_schema must describe an object")
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, Mapping) or not isinstance(required, list):
        raise ValueError("invalid procedure parameter_schema")
    missing = [name for name in required if name not in parameters]
    if missing:
        raise ValueError(f"missing procedure parameters: {', '.join(sorted(missing))}")
    if schema.get("additionalProperties") is False:
        unexpected = set(parameters) - set(properties)
        if unexpected:
            raise ValueError(f"unexpected procedure parameters: {', '.join(sorted(unexpected))}")
    expected_types = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": Mapping,
        "array": list,
    }
    for name, value in parameters.items():
        definition = properties.get(name)
        if not isinstance(definition, Mapping):
            continue
        type_name = definition.get("type")
        if type_name in expected_types and not isinstance(value, expected_types[type_name]):
            raise ValueError(f"procedure parameter {name} must be {type_name}")
        choices = definition.get("enum")
        if isinstance(choices, list) and value not in choices:
            raise ValueError(f"procedure parameter {name} is outside its enum")


def _validate_packet(packet: Mapping[str, Any]) -> None:
    if packet.get("schema_version") != "1.0":
        raise ValueError("procedure packet schema_version must be 1.0")
    _require_text(packet, "generation_id")
    procedures = packet.get("procedures")
    if not isinstance(procedures, list):
        raise ValueError("procedures must be a list")
    seen: set[str] = set()
    for procedure in procedures:
        if not isinstance(procedure, Mapping):
            raise ValueError("procedure must be an object")
        procedure_id = _require_text(procedure, "procedure_id")
        if procedure_id in seen:
            raise ValueError(f"duplicate procedure_id: {procedure_id}")
        seen.add(procedure_id)
        _require_text(procedure, "primary_goal_id")
        _require_text(procedure, "name")
        status = _require_text(procedure, "status")
        if status not in {"draft", "validated", "active", "retired"}:
            raise ValueError(f"invalid procedure status: {status}")
        confidence = procedure.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise ValueError(f"invalid procedure confidence: {procedure_id}")
        execution_mode = str(procedure.get("execution_mode", "hint_only"))
        if execution_mode not in {"hint_only", "deterministic_fast_path"}:
            raise ValueError(f"invalid procedure execution_mode: {procedure_id}")
        versions = procedure.get("compatible_app_versions", [])
        locales = procedure.get("locales", [])
        if not isinstance(versions, list) or not all(
            isinstance(value, str) and value.strip() for value in versions
        ):
            raise ValueError(f"invalid compatible_app_versions: {procedure_id}")
        if not isinstance(locales, list) or not all(
            isinstance(value, str) and value.strip() for value in locales
        ):
            raise ValueError(f"invalid locales: {procedure_id}")
        validation_count = procedure.get("validation_count", 0)
        minimum = procedure.get("fast_path_min_validation_count", 3)
        if not isinstance(validation_count, int) or validation_count < 0:
            raise ValueError(f"invalid validation_count: {procedure_id}")
        if not isinstance(minimum, int) or minimum < 1:
            raise ValueError(f"invalid fast_path_min_validation_count: {procedure_id}")
        if execution_mode == "deterministic_fast_path" and not procedure.get("app_package"):
            raise ValueError(f"deterministic fast path must be app-scoped: {procedure_id}")
        schema = procedure.get("parameter_schema", {"type": "object"})
        defaults = procedure.get("default_parameters", {})
        if not isinstance(schema, Mapping) or not isinstance(defaults, Mapping):
            raise ValueError(f"invalid parameter metadata: {procedure_id}")
        _validate_parameters(schema, defaults)
        steps = procedure.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"procedure must contain steps: {procedure_id}")
        ordinals = []
        for step in steps:
            if not isinstance(step, Mapping):
                raise ValueError(f"procedure step must be an object: {procedure_id}")
            ordinal = step.get("ordinal")
            if not isinstance(ordinal, int) or ordinal < 0:
                raise ValueError(f"invalid procedure step ordinal: {procedure_id}")
            ordinals.append(ordinal)
            _require_text(step, "immediate_subgoal")
        if sorted(ordinals) != list(range(len(ordinals))):
            raise ValueError(f"procedure step ordinals must be contiguous: {procedure_id}")


def build_procedure_catalog(packet_path: str | Path, output_path: str | Path) -> Path:
    packet_path = Path(packet_path)
    output_path = Path(output_path)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if not isinstance(packet, Mapping):
        raise ValueError("procedure packet must be an object")
    _validate_packet(packet)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".tmp", dir=output_path.parent
    )
    os.close(handle)
    temporary_path = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.executescript(SCHEMA_SQL)
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                ("schema_version", str(packet["schema_version"])),
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                ("generation_id", str(packet["generation_id"])),
            )
            for procedure in packet["procedures"]:
                primary_goal_id = str(procedure["primary_goal_id"])
                compatible = procedure.get("compatible_goal_ids", [primary_goal_id])
                if not isinstance(compatible, list) or not all(
                    isinstance(value, str) and value for value in compatible
                ):
                    raise ValueError("compatible_goal_ids must contain strings")
                if primary_goal_id not in compatible:
                    compatible = [primary_goal_id, *compatible]
                connection.execute(
                    """
                    INSERT INTO procedures(
                        procedure_id, primary_goal_id, compatible_goal_ids_json,
                        capability_id, app_package, compatible_app_versions_json,
                        locales_json, execution_mode, validation_count,
                        fast_path_min_validation_count, name, description,
                        parameter_schema_json, default_parameters_json,
                        entry_conditions_json, completion_conditions_json,
                        confidence, status, generation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        procedure["procedure_id"],
                        primary_goal_id,
                        _json(sorted(set(compatible))),
                        procedure.get("capability_id"),
                        procedure.get("app_package"),
                        _json(procedure.get("compatible_app_versions", [])),
                        _json(procedure.get("locales", [])),
                        procedure.get("execution_mode", "hint_only"),
                        int(procedure.get("validation_count", 0)),
                        int(procedure.get("fast_path_min_validation_count", 3)),
                        procedure["name"],
                        procedure.get("description", ""),
                        _json(procedure.get("parameter_schema", {"type": "object"})),
                        _json(procedure.get("default_parameters", {})),
                        _json(procedure.get("entry_conditions", [])),
                        _json(procedure.get("completion_conditions", [])),
                        float(procedure["confidence"]),
                        procedure["status"],
                        packet["generation_id"],
                    ),
                )
                for step in procedure["steps"]:
                    connection.execute(
                        """
                        INSERT INTO procedure_steps(
                            procedure_id, ordinal, immediate_subgoal,
                            expected_concept_id, preferred_role_id, transition_id,
                            preconditions_json, completion_check_json,
                            fallback_policy_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            procedure["procedure_id"],
                            step["ordinal"],
                            step["immediate_subgoal"],
                            step.get("expected_concept_id"),
                            step.get("preferred_role_id"),
                            step.get("transition_id"),
                            _json(step.get("preconditions", [])),
                            _json(step.get("completion_check", {})),
                            _json(step.get("fallback_policy", {})),
                        ),
                    )
            connection.commit()
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise ValueError("procedure catalog integrity check failed")
        finally:
            connection.close()
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return output_path


class ProcedureCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)

    def _connect(self) -> sqlite3.Connection:
        uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def metadata(self) -> dict[str, str]:
        with self._connection() as connection:
            return {
                str(row["key"]): str(row["value"])
                for row in connection.execute("SELECT key, value FROM metadata")
            }

    def select(
        self,
        *,
        goal_id: str,
        app_package: str,
        app_version: str = "",
        locale: str = "ko-KR",
        facts: Mapping[str, Any],
        parameters: Mapping[str, Any] | None = None,
        statuses: Sequence[str] = ("active",),
    ) -> ProcedureSelection | None:
        if not statuses:
            return None
        placeholders = ",".join("?" for _ in statuses)
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM procedures WHERE status IN ({placeholders})",
                tuple(statuses),
            ).fetchall()

        selections: list[ProcedureSelection] = []
        for row in rows:
            compatible_goal_ids = tuple(json.loads(row["compatible_goal_ids_json"]))
            if goal_id not in compatible_goal_ids:
                continue
            scoped_app = row["app_package"]
            if scoped_app and scoped_app != app_package:
                continue
            versions = tuple(json.loads(row["compatible_app_versions_json"]))
            locales = tuple(json.loads(row["locales_json"]))
            if versions and not _matches_scope(app_version, versions):
                continue
            if locales and not _matches_scope(locale, locales):
                continue
            entry_conditions = tuple(json.loads(row["entry_conditions_json"]))
            try:
                if not all_conditions(entry_conditions, facts):
                    continue
            except PredicateError:
                continue
            schema = json.loads(row["parameter_schema_json"])
            bound = dict(json.loads(row["default_parameters_json"]))
            bound.update(parameters or {})
            try:
                _validate_parameters(schema, bound)
            except ValueError:
                continue
            procedure = self.get(str(row["procedure_id"]))
            score = float(row["confidence"])
            if row["primary_goal_id"] == goal_id:
                score += 0.04
            if scoped_app == app_package and scoped_app:
                score += 0.08
            if versions:
                score += 0.03
            if locales:
                score += 0.02
            score += min(0.04, len(entry_conditions) * 0.01)
            reason = "primary_goal" if row["primary_goal_id"] == goal_id else "compatible_goal"
            if scoped_app:
                reason += "+app_scoped"
            selections.append(
                ProcedureSelection(
                    procedure=procedure,
                    parameters=bound,
                    score=min(score, 1.0),
                    reason=reason,
                )
            )
        if not selections:
            return None
        selections.sort(key=lambda item: (-item.score, item.procedure.procedure_id))
        return selections[0]

    def get(self, procedure_id: str) -> ProcedureDefinition:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM procedures WHERE procedure_id = ?", (procedure_id,)
            ).fetchone()
            if row is None:
                raise KeyError(procedure_id)
            step_rows = connection.execute(
                "SELECT * FROM procedure_steps WHERE procedure_id = ? ORDER BY ordinal",
                (procedure_id,),
            ).fetchall()
        steps = tuple(
            ProcedureStep(
                ordinal=int(step["ordinal"]),
                immediate_subgoal=str(step["immediate_subgoal"]),
                expected_concept_id=step["expected_concept_id"],
                preferred_role_id=step["preferred_role_id"],
                transition_id=step["transition_id"],
                preconditions=tuple(json.loads(step["preconditions_json"])),
                completion_check=json.loads(step["completion_check_json"]),
                fallback_policy=json.loads(step["fallback_policy_json"]),
            )
            for step in step_rows
        )
        return ProcedureDefinition(
            procedure_id=str(row["procedure_id"]),
            primary_goal_id=str(row["primary_goal_id"]),
            compatible_goal_ids=tuple(json.loads(row["compatible_goal_ids_json"])),
            capability_id=row["capability_id"],
            app_package=row["app_package"],
            compatible_app_versions=tuple(json.loads(row["compatible_app_versions_json"])),
            locales=tuple(json.loads(row["locales_json"])),
            execution_mode=str(row["execution_mode"]),
            validation_count=int(row["validation_count"]),
            fast_path_min_validation_count=int(row["fast_path_min_validation_count"]),
            name=str(row["name"]),
            description=str(row["description"]),
            parameter_schema=json.loads(row["parameter_schema_json"]),
            default_parameters=json.loads(row["default_parameters_json"]),
            entry_conditions=tuple(json.loads(row["entry_conditions_json"])),
            completion_conditions=tuple(json.loads(row["completion_conditions_json"])),
            steps=steps,
            confidence=float(row["confidence"]),
            status=str(row["status"]),
            generation_id=str(row["generation_id"]),
        )

    def all(self, *, statuses: Iterable[str] | None = None) -> tuple[ProcedureDefinition, ...]:
        with self._connection() as connection:
            if statuses is None:
                rows = connection.execute(
                    "SELECT procedure_id FROM procedures ORDER BY procedure_id"
                ).fetchall()
            else:
                values = tuple(statuses)
                if not values:
                    return ()
                placeholders = ",".join("?" for _ in values)
                rows = connection.execute(
                    f"SELECT procedure_id FROM procedures WHERE status IN ({placeholders}) "
                    "ORDER BY procedure_id",
                    values,
                ).fetchall()
        return tuple(self.get(str(row["procedure_id"])) for row in rows)


def procedure_fast_path_eligibility(
    procedure: ProcedureDefinition,
    *,
    app_package: str,
    app_version: str,
    locale: str,
) -> tuple[bool, str]:
    if procedure.status != "active":
        return False, "procedure_not_active"
    if procedure.execution_mode != "deterministic_fast_path":
        return False, "hint_only"
    if not procedure.app_package or procedure.app_package != app_package:
        return False, "app_scope_mismatch"
    if not procedure.compatible_app_versions:
        return False, "app_version_scope_missing"
    if not _matches_scope(app_version, procedure.compatible_app_versions):
        return False, "app_version_scope_mismatch"
    if not procedure.locales or not _matches_scope(locale, procedure.locales):
        return False, "locale_scope_mismatch"
    if procedure.validation_count < procedure.fast_path_min_validation_count:
        return False, "insufficient_validations"
    return True, "validated_exact_scope"


def _matches_scope(value: str, patterns: Sequence[str]) -> bool:
    normalized = value.strip().casefold()
    return bool(normalized) and any(
        fnmatchcase(normalized, pattern.strip().casefold()) for pattern in patterns
    )
