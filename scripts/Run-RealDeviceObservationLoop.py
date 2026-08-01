from __future__ import annotations

"""Restartable staged observation loop for the designated physical Android phone.

Every app version advances through four independently validated stages:
initial capture, neutral menu discovery, goal-candidate generation, and
goal-directed exploration.  A capture, an empty candidate set, or a model
prediction alone can never become graph coverage.  All evidence remains an
unreviewed shadow candidate pinned to frozen canonical V15.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.real_device_goal_candidates import (  # noqa: E402
    GOAL_CANDIDATE_POLICY_SHA256,
    GOAL_CANDIDATE_POLICY_VERSION,
)

DEFAULT_OBSERVATION_ROOT = REPO_ROOT / ".artifacts" / "navigation-observations"
EXPECTED_SERIAL = "R3CY204GDVE"
PROVENANCE = "real_device_observation_candidate"
REVIEW_STATUS = "unreviewed_candidate"
ROUTE_LIFECYCLE = "shadow"
CANONICAL_VERSION = "15.0.0"

DISCOVERY_SCRIPT = "Discover-RealDeviceApps.py"
COLLECTOR_SCRIPT = "Collect-RealDeviceObservations.py"
VALIDATOR_SCRIPT = "Validate-RealDeviceObservationCorpus.py"
GOAL_GENERATOR_SCRIPT = "Generate-RealDeviceGoalCandidates.py"
ARTIFACT_BUILDER_SCRIPT = "Build-RealDeviceFunctionGraphArtifacts.py"
FAMILY_MANIFEST = REPO_ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"
ALLOWED_PYTHON_SCRIPTS = frozenset(
    {
        DISCOVERY_SCRIPT,
        COLLECTOR_SCRIPT,
        VALIDATOR_SCRIPT,
        GOAL_GENERATOR_SCRIPT,
        ARTIFACT_BUILDER_SCRIPT,
    }
)

STAGE_INITIAL = "initial_capture"
STAGE_DISCOVERY = "neutral_menu_discovery"
STAGE_DIRECTED = "goal_directed_exploration"
COLLECTION_STAGES = frozenset({STAGE_INITIAL, STAGE_DISCOVERY, STAGE_DIRECTED})
STAGE_FLAG = {
    STAGE_INITIAL: "--capture-only",
    STAGE_DISCOVERY: "--discovery-explore",
}
EXPECTED_TERMINAL_STATUSES = {
    STAGE_INITIAL: frozenset({"captured"}),
    STAGE_DISCOVERY: frozenset(
        {"discovery_budget_complete", "discovery_frontier_exhausted"}
    ),
    STAGE_DIRECTED: frozenset({"destination_reached", "skipped_completed"}),
}
GOAL_STATES = frozenset(
    {"applicable", "not_applicable", "authentication_boundary", "unverified"}
)

VALIDATED = "VALIDATED.json"
QUARANTINED = "QUARANTINED.json"
VALIDATION_CORE_ARTIFACTS = (
    "manifest.json",
    "checkpoint.json",
    "corpus.sqlite",
    "graph-candidate.sqlite",
    "observations.jsonl",
    "screens.jsonl",
)
GOAL_ARTIFACT = "goal-candidates.json"
CURRENT_GOAL_ARTIFACT = (
    f"goal-candidates.{GOAL_CANDIDATE_POLICY_SHA256[:16]}.json"
)
RESEARCH_ARTIFACTS = (
    "common-menu-synonyms.json",
    "destination-candidates.jsonl",
    "manual-validation.json",
    "navigation-report.json",
)
CHECKPOINT = "checkpoint.json"
PROGRESS = "progress.jsonl"
FAILURES = "failures.jsonl"
METRICS = "metrics.jsonl"

HEARTBEAT_SECONDS = 45.0
KEEPALIVE_SECONDS = 120.0
PACKAGE_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")
MACHINE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,191}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class LoopError(RuntimeError):
    """Fail-closed orchestration error with a stable, non-sensitive code."""


class _ProcessLock:
    """Non-blocking OS lock shared by normal and offline loop executions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.descriptor: int | None = None

    def __enter__(self) -> "_ProcessLock":
        if self.path.exists() and self.path.is_symlink():
            raise LoopError("observation_loop_lock_invalid")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(self.path, flags, 0o600)
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"0")
                os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError) as error:
            if descriptor is not None:
                os.close(descriptor)
            raise LoopError("observation_loop_lock_unavailable") from error
        self.descriptor = descriptor
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        descriptor = self.descriptor
        self.descriptor = None
        if descriptor is None:
            return
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def __call__(
        self, command: Sequence[str], *, cwd: Path, timeout_seconds: float
    ) -> CommandResult: ...


Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]


@dataclass(frozen=True)
class WorkItem:
    action: str
    package: str
    version_key: str
    version_name: str | None
    version_code: str | None
    priority_rank: int
    sensitivity_categories: tuple[str, ...]
    sensitivity_handling: str
    snapshot_id: str
    snapshot_path: Path
    snapshot_sha256: str
    goal_artifact_path: Path | None = None
    goal_artifact_sha256: str | None = None

    @property
    def identity(self) -> str:
        return version_identity(self.package, self.version_key)


@dataclass(frozen=True)
class LoopOutcome:
    status: str
    rounds_completed: int
    boundary_sentence: str | None = None
    selected_identity: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(clock: Clock) -> str:
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path, code: str) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        raise LoopError(code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LoopError(code) from error
    if not isinstance(value, dict):
        raise LoopError(code)
    return value


def _command_json(output: str, code: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise LoopError(code)


def version_identity(package: str, version_key: str) -> str:
    if not PACKAGE_RE.fullmatch(package) or not version_key or len(version_key) > 300:
        raise LoopError("app_version_identity_invalid")
    return f"{package}@{version_key}"


def _policy_fingerprint(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "categories": sorted(str(value) for value in record.get("sensitivity_categories", [])),
                "handling": str(record.get("sensitivity_handling") or ""),
            }
        ).encode("utf-8")
    ).hexdigest()


def _goal_candidate_policy() -> dict[str, str]:
    return {
        "version": GOAL_CANDIDATE_POLICY_VERSION,
        "sha256": GOAL_CANDIDATE_POLICY_SHA256,
    }


def _goal_candidate_policy_status(value: object) -> str:
    """Classify a persisted policy without treating partial data as legacy."""

    if value is None:
        return "legacy_missing"
    if not isinstance(value, Mapping):
        return "tampered"
    if dict(value) == _goal_candidate_policy():
        return "current"
    return "tampered"


def coverage_stage(stage: Mapping[str, Any] | None) -> str:
    if not isinstance(stage, Mapping):
        return "initial_capture_pending"
    graph = stage.get("graph_coverage_validation")
    if isinstance(graph, Mapping) and graph.get("status") == "passed":
        return "graph_coverage_validated"
    directed = stage.get(STAGE_DIRECTED)
    if isinstance(directed, Mapping):
        if (directed.get("validation") or {}).get("status") == "passed":
            return "directed_validation_pending_graph_gate"
        if directed.get("status") in {"running", "boundary"}:
            return "goal_directed_exploration_running"
    candidates = stage.get("goal_candidates")
    if isinstance(candidates, Mapping) and candidates.get("status") == "passed":
        evidence = candidates.get("evidence")
        if isinstance(evidence, Mapping) and int(evidence.get("applicable", 0)) == 0:
            return "neutral_rediscovery_scheduled"
        return "goal_directed_exploration_pending"
    discovery = stage.get(STAGE_DISCOVERY)
    if isinstance(discovery, Mapping):
        if (discovery.get("validation") or {}).get("status") == "passed":
            return "goal_candidate_generation_pending"
        if discovery.get("status") in {"running", "boundary"}:
            return "neutral_menu_discovery_running"
    initial = stage.get(STAGE_INITIAL)
    if isinstance(initial, Mapping):
        if (initial.get("validation") or {}).get("status") == "passed":
            return "neutral_menu_discovery_pending"
        if initial.get("status") in {"running", "boundary"}:
            return "initial_capture_running"
    return "initial_capture_pending"


def is_graph_coverage_validated(stage: Mapping[str, Any] | None) -> bool:
    return coverage_stage(stage) == "graph_coverage_validated"


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "orchestrator": "Run-RealDeviceObservationLoop.py",
        "device_serial": EXPECTED_SERIAL,
        "provenance": PROVENANCE,
        "review_status": REVIEW_STATUS,
        "route_lifecycle": ROUTE_LIFECYCLE,
        "canonical": {
            "version": CANONICAL_VERSION,
            "policy_label": "V15_frozen",
            "mutation_allowed": False,
            "v16_v20_promotion": "forbidden",
            "v21": "research_only_noncanonical",
            "v22_plus": "forbidden",
        },
        "status": "ready",
        "next_round": 1,
        "active_task": None,
        "last_inventory": None,
        "stages": {},
        "counters": {
            "rounds": 0,
            "keepalive_cycles": 0,
            "initial_capture_passes": 0,
            "neutral_discovery_passes": 0,
            "goal_candidate_passes": 0,
            "directed_exploration_passes": 0,
            "graph_coverage_passes": 0,
            "boundary_stops": 0,
            "failures": 0,
        },
    }


def _validate_state(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = _default_state()
    stages = value.get("stages")
    counters = value.get("counters")
    active = value.get("active_task")
    if (
        value.get("schema_version") != 2
        or value.get("orchestrator") != expected["orchestrator"]
        or value.get("device_serial") != EXPECTED_SERIAL
        or value.get("provenance") != PROVENANCE
        or value.get("review_status") != REVIEW_STATUS
        or value.get("route_lifecycle") != ROUTE_LIFECYCLE
        or value.get("canonical") != expected["canonical"]
        or not isinstance(value.get("status"), str)
        or not value.get("status")
        or not isinstance(value.get("next_round"), int)
        or isinstance(value.get("next_round"), bool)
        or int(value["next_round"]) < 1
        or not isinstance(value.get("last_inventory"), (Mapping, type(None)))
        or not isinstance(stages, Mapping)
        or not isinstance(counters, Mapping)
        or active is not None and not isinstance(active, Mapping)
    ):
        raise LoopError("loop_checkpoint_invalid")
    expected_counter_keys = set(expected["counters"])
    if set(counters) != expected_counter_keys or any(
        not isinstance(counter, int) or isinstance(counter, bool) or counter < 0
        for counter in counters.values()
    ):
        raise LoopError("loop_checkpoint_invalid")
    validated_stages: dict[str, dict[str, Any]] = {}
    for identity, row in stages.items():
        if not isinstance(identity, str) or not isinstance(row, Mapping):
            raise LoopError("loop_checkpoint_invalid")
        package = row.get("package")
        version_key = row.get("version_key")
        if not isinstance(package, str) or not isinstance(version_key, str):
            raise LoopError("loop_checkpoint_invalid")
        try:
            computed_identity = version_identity(package, version_key)
        except LoopError as error:
            raise LoopError("loop_checkpoint_invalid") from error
        if identity != computed_identity:
            raise LoopError("loop_checkpoint_invalid")
        scheduler = row.get("scheduler")
        if scheduler is not None:
            if (
                not isinstance(scheduler, Mapping)
                or set(scheduler)
                != {
                    "first_seen_round",
                    "admission_lane",
                    "admission_reason",
                    "first_inventory_rank",
                    "last_selected_round",
                    "selection_count",
                }
                or scheduler.get("admission_lane") not in {"fresh", "backlog"}
                or not isinstance(scheduler.get("admission_reason"), str)
                or not scheduler.get("admission_reason")
                or any(
                    not isinstance(scheduler.get(field), int)
                    or isinstance(scheduler.get(field), bool)
                    or int(scheduler[field]) < minimum
                    for field, minimum in (
                        ("first_seen_round", 1),
                        ("first_inventory_rank", 1),
                        ("last_selected_round", 0),
                        ("selection_count", 0),
                    )
                )
            ):
                raise LoopError("loop_checkpoint_invalid")
        validated_stages[identity] = dict(row)
    validated_active: dict[str, Any] | None = None
    if isinstance(active, Mapping):
        package = active.get("package")
        version_key = active.get("version_key")
        identity = active.get("identity")
        action = active.get("stage")
        if (
            not isinstance(package, str)
            or not isinstance(version_key, str)
            or not isinstance(identity, str)
            or action not in COLLECTION_STAGES
        ):
            raise LoopError("loop_checkpoint_invalid")
        try:
            computed_identity = version_identity(package, version_key)
        except LoopError as error:
            raise LoopError("loop_checkpoint_invalid") from error
        stage = validated_stages.get(identity)
        if (
            identity != computed_identity
            or stage is None
            or stage.get("package") != package
            or stage.get("version_key") != version_key
        ):
            raise LoopError("loop_checkpoint_invalid")
        validated_active = dict(active)
    result = dict(value)
    result["stages"] = validated_stages
    result["counters"] = dict(counters)
    result["active_task"] = validated_active
    return result


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise LoopError("checkpoint_symlink_forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise LoopError("state_root_symlink_forbidden")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() and path.is_symlink():
        raise LoopError("ledger_symlink_forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (_canonical_json(value) + "\n").encode("utf-8")
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise LoopError("ledger_short_write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _boundary_sentence(status: str) -> str:
    reason = status.partition(":")[2].casefold()
    if "permission" in reason:
        return "권한 요청을 직접 처리한 뒤 같은 작업을 다시 실행해 주세요."
    if "captcha" in reason:
        return "CAPTCHA를 직접 완료한 뒤 같은 작업을 다시 실행해 주세요."
    if any(token in reason for token in ("biometric", "fingerprint", "face_auth")):
        return "생체인증을 직접 완료한 뒤 같은 작업을 다시 실행해 주세요."
    if "password" in reason:
        return "비밀번호를 직접 입력한 뒤 같은 작업을 다시 실행해 주세요."
    if any(token in reason for token in ("login", "sign_in", "auth")):
        return "로그인을 직접 완료한 뒤 같은 작업을 다시 실행해 주세요."
    if any(token in reason for token in ("external", "other_app", "package")):
        return "다른 앱으로 이동한 화면을 확인한 뒤 같은 작업을 다시 실행해 주세요."
    return "휴대폰에서 필요한 조작을 직접 완료한 뒤 같은 작업을 다시 실행해 주세요."


class SubprocessRunner:
    def __call__(
        self, command: Sequence[str], *, cwd: Path, timeout_seconds: float
    ) -> CommandResult:
        completed = subprocess.run(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class ObservationLoop:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        observation_root: Path = DEFAULT_OBSERVATION_ROOT,
        inventory_root: Path | None = None,
        state_root: Path | None = None,
        serial: str = EXPECTED_SERIAL,
        python_executable: str | Path = sys.executable,
        adb_executable: str | Path = "adb",
        api_base_url: str = "http://127.0.0.1:8010",
        family_manifest: Path = FAMILY_MANIFEST,
        build_research_artifacts: bool = False,
        refresh_rounds_without_applicable: int = 10,
        command_timeout_seconds: float = 600.0,
        poll_seconds: float = 120.0,
        runner: CommandRunner | None = None,
        clock: Clock = utc_now,
        sleeper: Sleeper = time.sleep,
        stop_requested: Callable[[], bool] | None = None,
        emit_heartbeats: bool = True,
    ) -> None:
        if serial != EXPECTED_SERIAL or "emulator" in serial.casefold():
            raise LoopError("exact_physical_serial_required")
        if command_timeout_seconds <= 0 or poll_seconds < 0 or refresh_rounds_without_applicable < 1:
            raise LoopError("loop_configuration_invalid")
        self.repo_root = Path(repo_root).resolve()
        self.observation_root = Path(observation_root).resolve()
        self.inventory_root = Path(inventory_root or self.observation_root / "device-inventory").resolve()
        self.state_root = Path(state_root or self.observation_root / "observation-loop").resolve()
        if not self.inventory_root.is_relative_to(self.observation_root) or not self.state_root.is_relative_to(self.observation_root):
            raise LoopError("artifact_roots_outside_observation_root")
        self.family_manifest = Path(family_manifest).resolve()
        if not self.family_manifest.is_file() or not self.family_manifest.is_relative_to(self.repo_root):
            raise LoopError("family_manifest_invalid")
        self.serial = serial
        self.python_executable = str(python_executable)
        self.adb_executable = str(adb_executable)
        self.api_base_url = api_base_url
        self.build_research_artifacts = build_research_artifacts
        self.refresh_rounds_without_applicable = refresh_rounds_without_applicable
        self.command_timeout_seconds = command_timeout_seconds
        self.poll_seconds = poll_seconds
        self.runner = runner or SubprocessRunner()
        self.clock = clock
        self.sleeper = sleeper
        self.stop_requested = stop_requested or (lambda: False)
        self.emit_heartbeats = emit_heartbeats
        self.checkpoint_path = self.state_root / CHECKPOINT
        self.progress_path = self.state_root / PROGRESS
        self.failure_path = self.state_root / FAILURES
        self.metric_path = self.state_root / METRICS
        self._keepalive_stop = threading.Event()
        self._keepalive_error: str | None = None
        self._keepalive_thread: threading.Thread | None = None
        for script in ALLOWED_PYTHON_SCRIPTS:
            if not (self.repo_root / "scripts" / script).is_file():
                raise LoopError(f"required_script_missing:{script}")
        self._state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return _default_state()
        return _validate_state(_json(self.checkpoint_path, "loop_checkpoint_invalid"))

    def _save(self, status: str) -> None:
        self._state["status"] = status
        self._state["updated_at"] = _iso(self.clock)
        _atomic_json(self.checkpoint_path, self._state)

    def _store_observation_path(self, path: Path) -> str:
        resolved = path.resolve()
        if not resolved.is_relative_to(self.observation_root):
            raise LoopError("observation_path_escape")
        return resolved.relative_to(self.observation_root).as_posix()

    def _restore_observation_path(self, stored: object) -> Path:
        value = Path(str(stored or ""))
        resolved = value.resolve() if value.is_absolute() else (self.observation_root / value).resolve()
        if not resolved.is_relative_to(self.observation_root):
            raise LoopError("observation_path_escape")
        return resolved

    def _event(self, event_type: str, **fields: Any) -> None:
        _append_jsonl(
            self.progress_path,
            {
                "schema_version": 2,
                "event_type": event_type,
                "at": _iso(self.clock),
                "round": int(self._state["next_round"]),
                "device_serial": EXPECTED_SERIAL,
                "provenance": PROVENANCE,
                **fields,
            },
        )

    def _failure(self, phase: str, code: str, identity: str | None = None, return_code: int | None = None) -> None:
        payload: dict[str, Any] = {
            "schema_version": 2,
            "event_type": "failure",
            "at": _iso(self.clock),
            "round": int(self._state["next_round"]),
            "device_serial": EXPECTED_SERIAL,
            "phase": phase,
            "error_code": code.split(":", 1)[0],
            "preserved": True,
        }
        if identity:
            payload["version_identity"] = identity
        if return_code is not None:
            payload["return_code"] = int(return_code)
        _append_jsonl(self.failure_path, payload)
        self._state["counters"]["failures"] += 1

    def _metric(self, outcome: str, started: float, identity: str | None = None, **fields: Any) -> None:
        payload: dict[str, Any] = {
            "schema_version": 2,
            "event_type": "round_metric",
            "at": _iso(self.clock),
            "round": int(self._state["next_round"]),
            "outcome": outcome,
            "elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
            "arbitrary_tap_count": 0,
            "install_delete_clear_logout_command_count": 0,
            **fields,
        }
        if identity:
            payload["version_identity"] = identity
        _append_jsonl(self.metric_path, payload)

    def _assert_command(self, command: Sequence[str]) -> None:
        values = tuple(str(value) for value in command)
        if not values:
            raise LoopError("empty_command_forbidden")
        if values[0] == self.python_executable:
            if len(values) < 2:
                raise LoopError("python_script_missing")
            script = Path(values[1])
            if script.name not in ALLOWED_PYTHON_SCRIPTS or script.resolve() != (self.repo_root / "scripts" / script.name).resolve():
                raise LoopError("python_script_not_allowlisted")
            lowered = {value.casefold() for value in values[2:]}
            if lowered & {"tap", "swipe", "install", "uninstall", "delete", "clear", "logout"}:
                raise LoopError("device_mutation_argument_forbidden")
            if script.name in {DISCOVERY_SCRIPT, COLLECTOR_SCRIPT}:
                if "--serial" not in values or values[values.index("--serial") + 1] != EXPECTED_SERIAL:
                    raise LoopError("exact_serial_argument_missing")
            if script.name == COLLECTOR_SCRIPT:
                modes = {flag for flag in ("--capture-only", "--discovery-explore", "--goal-candidates") if flag in values}
                if len(modes) != 1:
                    raise LoopError("collector_stage_mode_invalid")
                if "--capture-only" in modes:
                    for flag in ("--max-actions", "--max-scrolls", "--max-backs"):
                        if flag not in values or values[values.index(flag) + 1] != "0":
                            raise LoopError("capture_only_budget_invalid")
                if "--goal-candidates" in modes and "--family-manifest" not in values:
                    raise LoopError("directed_lineage_flags_missing")
            return
        if values[0] != self.adb_executable:
            raise LoopError("non_allowlisted_executable")
        allowed = {
            (self.adb_executable, "-s", EXPECTED_SERIAL, "get-state"),
            (self.adb_executable, "-s", EXPECTED_SERIAL, "shell", "getprop", "ro.serialno"),
            (self.adb_executable, "-s", EXPECTED_SERIAL, "shell", "getprop", "ro.kernel.qemu"),
            (self.adb_executable, "-s", EXPECTED_SERIAL, "shell", "svc", "power", "stayon", "usb"),
            (self.adb_executable, "-s", EXPECTED_SERIAL, "shell", "input", "keyevent", "KEYCODE_WAKEUP"),
        }
        if values not in allowed:
            raise LoopError("adb_command_not_keepalive_allowlisted")

    def _run_raw(self, command: Sequence[str], *, heartbeat: bool = True) -> CommandResult:
        self._assert_command(command)
        finished = threading.Event()
        phase = Path(str(command[1])).stem if command[0] == self.python_executable else "physical_keepalive"

        def emit() -> None:
            while not finished.wait(HEARTBEAT_SECONDS):
                self._event("heartbeat", phase=phase, status="command_running")
                if self.emit_heartbeats:
                    print(json.dumps({"event": "heartbeat", "phase": phase, "round": self._state["next_round"]}, sort_keys=True), flush=True)

        thread: threading.Thread | None = None
        if heartbeat:
            thread = threading.Thread(target=emit, name="observation-command-heartbeat", daemon=True)
            thread.start()
        try:
            return self.runner(
                tuple(str(value) for value in command),
                cwd=self.repo_root,
                timeout_seconds=self.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            raise LoopError("command_timeout") from error
        except OSError as error:
            raise LoopError("command_execution_failed") from error
        finally:
            finished.set()
            if thread:
                thread.join(timeout=1.0)

    def _adb(self, *arguments: str) -> CommandResult:
        result = self._run_raw((self.adb_executable, "-s", EXPECTED_SERIAL, *arguments), heartbeat=False)
        if result.returncode != 0:
            raise LoopError("physical_keepalive_command_failed")
        return result

    def _verify_device_and_restart_keepalive(self) -> None:
        if self._adb("get-state").stdout.strip() != "device":
            raise LoopError("physical_device_not_ready")
        if self._adb("shell", "getprop", "ro.serialno").stdout.strip() != EXPECTED_SERIAL:
            raise LoopError("physical_serial_mismatch")
        if self._adb("shell", "getprop", "ro.kernel.qemu").stdout.strip().casefold() in {"1", "true", "yes"}:
            raise LoopError("emulator_forbidden")
        self._adb("shell", "svc", "power", "stayon", "usb")
        self._adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        self._state["counters"]["keepalive_cycles"] += 1
        self._event("keepalive_verified", interval_seconds=KEEPALIVE_SECONDS)

    def _start_keepalive(self) -> None:
        self._verify_device_and_restart_keepalive()
        self._keepalive_stop.clear()
        self._keepalive_error = None

        def maintain() -> None:
            while not self._keepalive_stop.wait(KEEPALIVE_SECONDS):
                try:
                    self._adb("shell", "svc", "power", "stayon", "usb")
                    self._adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
                    self._state["counters"]["keepalive_cycles"] += 1
                    self._event("keepalive_refreshed", interval_seconds=KEEPALIVE_SECONDS)
                except LoopError as error:
                    self._keepalive_error = str(error).split(":", 1)[0]
                    return

        self._keepalive_thread = threading.Thread(target=maintain, name="physical-device-keepalive", daemon=True)
        self._keepalive_thread.start()

    def _stop_keepalive(self) -> None:
        self._keepalive_stop.set()
        if self._keepalive_thread:
            self._keepalive_thread.join(timeout=2.0)
        self._keepalive_thread = None

    def _check_keepalive(self) -> None:
        if self._keepalive_error:
            raise LoopError(self._keepalive_error)

    def _sleep(self) -> None:
        remaining = self.poll_seconds
        while remaining > 0:
            interval = min(HEARTBEAT_SECONDS, remaining)
            self.sleeper(interval)
            remaining -= interval
            self._check_keepalive()
            if remaining > 0:
                self._event("heartbeat", phase="poll_wait", status="waiting")
                if self.emit_heartbeats:
                    print(json.dumps({"event": "heartbeat", "phase": "poll_wait", "round": self._state["next_round"]}, sort_keys=True), flush=True)

    def _discover(self) -> tuple[dict[str, Any], Path]:
        result = self._run_raw(
            (
                self.python_executable,
                str(self.repo_root / "scripts" / DISCOVERY_SCRIPT),
                "--serial",
                EXPECTED_SERIAL,
                "--adb-path",
                self.adb_executable,
                "--output-root",
                str(self.inventory_root),
                "--observation-root",
                str(self.observation_root),
            )
        )
        if result.returncode != 0:
            raise LoopError("inventory_discovery_failed")
        report = _command_json(result.stdout, "inventory_discovery_output_invalid")
        path = Path(str(report.get("path") or "")).resolve()
        if not path.is_file() or path.is_symlink() or not path.is_relative_to(self.inventory_root):
            raise LoopError("inventory_snapshot_path_invalid")
        snapshot = _json(path, "inventory_snapshot_invalid")
        self._validate_snapshot(snapshot, path)
        return snapshot, path

    @staticmethod
    def _validate_snapshot(snapshot: Mapping[str, Any], path: Path) -> None:
        device = snapshot.get("device")
        catalog = snapshot.get("canonical_catalog")
        if (
            snapshot.get("schema_version") != 1
            or snapshot.get("provenance") != PROVENANCE
            or snapshot.get("dataset_role") != PROVENANCE
            or snapshot.get("review_status") != REVIEW_STATUS
            or snapshot.get("route_lifecycle") != ROUTE_LIFECYCLE
            or snapshot.get("canonical_catalog_mutation") is not False
            or not isinstance(catalog, Mapping)
            or str(catalog.get("version")) != CANONICAL_VERSION
            or not isinstance(device, Mapping)
            or device.get("serial") != EXPECTED_SERIAL
            or device.get("is_emulator") is not False
            or not isinstance(snapshot.get("included_apps"), list)
            or not isinstance(snapshot.get("prioritized_apps"), list)
        ):
            raise LoopError("inventory_snapshot_attestation_invalid")
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        if not MACHINE_ID_RE.fullmatch(snapshot_id) or path.name != f"inventory-{snapshot_id}.json":
            raise LoopError("inventory_snapshot_identity_invalid")
        included = {str(row.get("package")): row for row in snapshot["included_apps"] if isinstance(row, Mapping)}
        priorities = snapshot["prioritized_apps"]
        if len(included) != len(snapshot["included_apps"]) or len(priorities) != len(included):
            raise LoopError("inventory_snapshot_apps_invalid")
        seen_ranks: set[int] = set()
        seen_packages: set[str] = set()
        for priority in priorities:
            if not isinstance(priority, Mapping):
                raise LoopError("inventory_snapshot_priority_invalid")
            package = str(priority.get("package") or "")
            rank = priority.get("priority_rank")
            record = included.get(package)
            if record is None or not isinstance(rank, int) or rank < 1 or priority.get("version_key") != record.get("version_key"):
                raise LoopError("inventory_snapshot_priority_invalid")
            seen_ranks.add(rank)
            seen_packages.add(package)
        if seen_ranks != set(range(1, len(included) + 1)) or seen_packages != set(included):
            raise LoopError("inventory_snapshot_priority_invalid")

    def _snapshot_from_manifest(self, manifest: Mapping[str, Any]) -> Path | None:
        metadata = manifest.get("inventory_snapshot")
        if not isinstance(metadata, Mapping) or not isinstance(metadata.get("path"), str):
            return None
        if metadata.get("path_scope") == "observation_root_relative":
            path = (self.observation_root / str(metadata["path"])).resolve()
        elif metadata.get("path_scope") == "explicit_safe_file" and metadata.get("explicit_safe_file") is True:
            path = Path(str(metadata["path"])).resolve()
        else:
            return None
        if not path.is_file() or path.is_symlink() or not path.is_relative_to(self.inventory_root) or metadata.get("sha256") != _sha256(path):
            return None
        return path

    def _source_path_from_metadata(
        self,
        metadata: object,
        *,
        expected_path: Path,
        expected_sha256: str,
    ) -> Path | None:
        if not isinstance(metadata, Mapping) or metadata.get("sha256") != expected_sha256:
            return None
        scope = metadata.get("path_scope")
        stored = metadata.get("path")
        if not isinstance(stored, str):
            return None
        if scope == "observation_root_relative" and metadata.get("explicit_safe_file") is False:
            resolved = (self.observation_root / stored).resolve()
        elif scope == "repo_relative" and metadata.get("explicit_safe_file") is False:
            resolved = (self.repo_root / stored).resolve()
        elif scope == "explicit_safe_file" and metadata.get("explicit_safe_file") is True:
            resolved = Path(stored).resolve()
        else:
            return None
        expected = expected_path.resolve()
        if (
            resolved != expected
            or not resolved.is_file()
            or resolved.is_symlink()
            or _sha256(resolved) != expected_sha256
        ):
            return None
        return resolved

    def _trusted_manifest(
        self,
        run_dir: Path,
        *,
        expected_stage: str | None = None,
        expected_package: str | None = None,
        expected_snapshot_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not run_dir.is_dir() or run_dir.is_symlink():
            return None
        marker_path = run_dir / VALIDATED
        manifest_path = run_dir / "manifest.json"
        screens_path = run_dir / "screens.jsonl"
        if (run_dir / QUARANTINED).exists() or any(not path.is_file() or path.is_symlink() for path in (marker_path, manifest_path, screens_path)):
            return None
        try:
            marker = _json(marker_path, "marker_invalid")
            manifest = _json(manifest_path, "manifest_invalid")
        except LoopError:
            return None
        core_hashes = marker.get("core_artifact_sha256")
        core_paths = {name: run_dir / name for name in VALIDATION_CORE_ARTIFACTS}
        core_artifacts_valid = bool(
            isinstance(core_hashes, Mapping)
            and set(core_hashes) == set(core_paths)
            and all(
                path.is_file()
                and not path.is_symlink()
                and core_hashes.get(name) == _sha256(path)
                for name, path in core_paths.items()
            )
            and core_hashes.get("manifest.json") == marker.get("manifest_sha256")
            and core_hashes.get("screens.jsonl") == marker.get("screens_sha256")
        )
        runtime = manifest.get("runtime_attestation")
        device = runtime.get("device") if isinstance(runtime, Mapping) else None
        exitguide = runtime.get("exitguide") if isinstance(runtime, Mapping) else None
        api = runtime.get("api") if isinstance(runtime, Mapping) else None
        safety = manifest.get("safety")
        snapshot_metadata = manifest.get("inventory_snapshot")
        stage = str(manifest.get("exploration_stage") or "")
        expected_mode = "capture_only" if stage == STAGE_INITIAL else "safe_explore"
        if (
            marker.get("schema_version") != 1
            or marker.get("status") != "passed"
            or marker.get("validator") != VALIDATOR_SCRIPT
            or marker.get("run_id") != manifest.get("run_id")
            or marker.get("provenance") != PROVENANCE
            or marker.get("device_serial") != EXPECTED_SERIAL
            or marker.get("is_emulator") is not False
            or marker.get("manifest_sha256") != _sha256(manifest_path)
            or marker.get("screens_sha256") != _sha256(screens_path)
            or not core_artifacts_valid
            or manifest.get("provenance") != PROVENANCE
            or manifest.get("dataset_role") != PROVENANCE
            or manifest.get("review_status") != REVIEW_STATUS
            or manifest.get("route_lifecycle") != ROUTE_LIFECYCLE
            or manifest.get("validation_profile") != "dynamic_inventory"
            or manifest.get("status") != "completed"
            or manifest.get("is_emulator") is not False
            or manifest.get("device_serial") != EXPECTED_SERIAL
            or manifest.get("canonical_mutation_allowed") is not False
            or manifest.get("canonical_catalog_version") != CANONICAL_VERSION
            or manifest.get("raw_artifacts_persisted") is not False
            or stage not in COLLECTION_STAGES
            or manifest.get("collection_mode") != expected_mode
            or (expected_stage is not None and stage != expected_stage)
            or not isinstance(snapshot_metadata, Mapping)
            or (expected_snapshot_id is not None and snapshot_metadata.get("snapshot_id") != expected_snapshot_id)
            or not isinstance(safety, Mapping)
            or int(safety.get("unsafe_auto_click_count", -1)) != 0
            or int(safety.get("final_action_auto_click_count", -1)) != 0
            or not isinstance(device, Mapping)
            or device.get("serial") != EXPECTED_SERIAL
            or device.get("is_emulator") is not False
            or not isinstance(exitguide, Mapping)
            or exitguide.get("package") != "com.exitguide.ai"
            or exitguide.get("installed_for_user_0") is not True
            or exitguide.get("accessibility_enabled") is not True
            or exitguide.get("accessibility_component") != "com.exitguide.ai/com.exitguide.ai.overlay.ExitGuideAccessibilityService"
            or exitguide.get("overlay_appop") != "allow"
            or not isinstance(api, Mapping)
            or api.get("status") != "ok"
            or api.get("llm_provider") != "exaone"
            or api.get("provider_ready") is not True
        ):
            return None
        selected = manifest.get("selected_packages")
        if expected_package is not None and selected != [expected_package]:
            return None
        if self._snapshot_from_manifest(manifest) is None:
            return None
        if stage == STAGE_DIRECTED and not isinstance(manifest.get("goal_candidate_plan"), Mapping):
            return None
        if stage != STAGE_DIRECTED and manifest.get("goal_candidate_plan") is not None:
            return None
        return manifest

    def _goal_artifact_policy_status(self, artifact_path: Path) -> str:
        """Return current/legacy/tampered without validating or exposing semantics."""

        if (
            not artifact_path.is_file()
            or artifact_path.is_symlink()
            or not artifact_path.resolve().is_relative_to(self.observation_root)
        ):
            return "invalid"
        try:
            artifact = _json(artifact_path, "goal_artifact_invalid")
        except LoopError:
            return "invalid"
        artifact_status = _goal_candidate_policy_status(
            artifact.get("goal_candidate_policy")
        )
        evidence_policy = artifact.get("evidence_policy")
        if evidence_policy is None:
            evidence_status = "legacy_missing"
        elif isinstance(evidence_policy, Mapping):
            raw_version = evidence_policy.get("goal_candidate_policy_version")
            raw_sha = evidence_policy.get("goal_candidate_policy_sha256")
            evidence_status = _goal_candidate_policy_status(
                None
                if raw_version is None and raw_sha is None
                else {"version": raw_version, "sha256": raw_sha}
            )
        else:
            evidence_status = "tampered"
        apps = artifact.get("apps")
        if (
            isinstance(apps, list)
            and len(apps) == 1
            and isinstance(apps[0], Mapping)
        ):
            app_status = _goal_candidate_policy_status(
                apps[0].get("goal_candidate_policy")
            )
        else:
            app_status = "tampered"
        statuses = {artifact_status, evidence_status, app_status}
        if statuses == {"current"}:
            return "current"
        if statuses == {"legacy_missing"}:
            return "legacy_missing"
        return "tampered"

    def _mark_goal_candidates_stale(
        self,
        stage: dict[str, Any],
        *,
        identity: str,
        reason_code: str,
        detected_policy_status: str,
    ) -> None:
        candidates = stage.get("goal_candidates")
        if (
            isinstance(candidates, Mapping)
            and candidates.get("status") == "stale"
            and candidates.get("required_policy") == _goal_candidate_policy()
        ):
            return
        history = stage.get("goal_candidate_policy_history")
        if history is None:
            history_rows: list[dict[str, Any]] = []
        elif isinstance(history, list) and all(
            isinstance(row, Mapping) for row in history
        ):
            history_rows = [dict(row) for row in history]
        else:
            raise LoopError("goal_candidate_policy_history_invalid")
        preserved = {
            field: self._json_clone(stage[field])
            for field in (
                "goal_candidates",
                STAGE_DIRECTED,
                "graph_coverage_validation",
                "next_neutral_discovery_round",
                "research_artifacts",
            )
            if field in stage
        }
        history_rows.append(
            {
                "reason_code": reason_code,
                "detected_policy_status": detected_policy_status,
                "required_policy": _goal_candidate_policy(),
                "preserved_stage_records": preserved,
                "canonical_promotion_allowed": False,
            }
        )
        stage["goal_candidate_policy_history"] = history_rows
        previous = candidates if isinstance(candidates, Mapping) else {}
        stage["goal_candidates"] = {
            "status": "stale",
            "reason_code": reason_code,
            "detected_policy_status": detected_policy_status,
            "previous_path": previous.get("path"),
            "previous_sha256": previous.get("sha256"),
            "source_run_id": previous.get("source_run_id"),
            "required_policy": _goal_candidate_policy(),
            "canonical_promotion_allowed": False,
        }
        for field in (
            STAGE_DIRECTED,
            "graph_coverage_validation",
            "next_neutral_discovery_round",
            "research_artifacts",
        ):
            stage.pop(field, None)
        stage["coverage_stage"] = coverage_stage(stage)
        self._event(
            "goal_candidate_policy_stale",
            version_identity=identity,
            reason_code=reason_code,
            detected_policy_status=detected_policy_status,
            required_policy_version=GOAL_CANDIDATE_POLICY_VERSION,
            required_policy_sha256=GOAL_CANDIDATE_POLICY_SHA256,
            artifact_deleted=False,
            device_action_count=0,
            canonical_promotion_allowed=False,
        )

    def _passed_goal_candidate_policy_status(
        self, stage: Mapping[str, Any]
    ) -> str:
        candidates = stage.get("goal_candidates")
        if (
            not isinstance(candidates, Mapping)
            or candidates.get("status") != "passed"
        ):
            return "not_passed"
        stored_status = _goal_candidate_policy_status(
            candidates.get("goal_candidate_policy")
        )
        if stored_status != "current":
            return stored_status
        try:
            artifact_path = self._restore_observation_path(candidates.get("path"))
        except LoopError:
            return "invalid"
        return self._goal_artifact_policy_status(artifact_path)

    def _goal_evidence(
        self,
        artifact_path: Path,
        *,
        source_manifest: Mapping[str, Any],
        snapshot_path: Path,
        package: str,
    ) -> dict[str, Any] | None:
        try:
            artifact = _json(artifact_path, "goal_artifact_invalid")
        except LoopError:
            return None
        snapshot_metadata = source_manifest.get("inventory_snapshot")
        catalog = artifact.get("canonical_catalog")
        policy = artifact.get("version_policy")
        goal_policy = artifact.get("goal_candidate_policy")
        evidence_policy = artifact.get("evidence_policy")
        safety = artifact.get("safety")
        declared_hashes = artifact.get("source_sha256")
        if (
            artifact.get("schema_version") != 1
            or artifact.get("artifact_type") != "dynamic_real_device_goal_candidates"
            or artifact.get("source_run_id") != source_manifest.get("run_id")
            or not isinstance(snapshot_metadata, Mapping)
            or artifact.get("source_inventory_snapshot_id") != snapshot_metadata.get("snapshot_id")
            or artifact.get("provenance") != PROVENANCE
            or artifact.get("dataset_role") != PROVENANCE
            or artifact.get("review_status") != REVIEW_STATUS
            or artifact.get("route_lifecycle") != ROUTE_LIFECYCLE
            or artifact.get("serving_allowed") is not False
            or artifact.get("human_review_required") is not True
            or _goal_candidate_policy_status(goal_policy) != "current"
            or not isinstance(evidence_policy, Mapping)
            or evidence_policy.get("goal_candidate_policy_version")
            != GOAL_CANDIDATE_POLICY_VERSION
            or evidence_policy.get("goal_candidate_policy_sha256")
            != GOAL_CANDIDATE_POLICY_SHA256
            or not isinstance(catalog, Mapping)
            or catalog.get("version") != CANONICAL_VERSION
            or catalog.get("mutation_allowed") is not False
            or not isinstance(policy, Mapping)
            or policy.get("canonical") != "V15_frozen"
            or policy.get("v16_v20_promotion") != "forbidden"
            or policy.get("v21") != "research_only_noncanonical"
            or policy.get("v22_plus") != "forbidden"
            or not isinstance(safety, Mapping)
            or safety.get("unsafe_auto_click_count") != 0
            or safety.get("final_action_auto_click_count") != 0
            or safety.get("terminal_actions_owned_by_user") is not True
            or not isinstance(declared_hashes, Mapping)
        ):
            return None
        source_run = artifact_path.parent
        expected_sources = {
            "manifest": source_run / "manifest.json",
            "checkpoint": source_run / "checkpoint.json",
            "corpus": source_run / "corpus.sqlite",
            "graph": source_run / "graph-candidate.sqlite",
            "snapshot": snapshot_path,
            "family_manifest": self.family_manifest,
        }
        if set(declared_hashes) != set(expected_sources):
            return None
        for key, path in expected_sources.items():
            if not path.is_file() or path.is_symlink() or declared_hashes.get(key) != _sha256(path):
                return None
        apps = artifact.get("apps")
        counts = artifact.get("counts")
        if not isinstance(apps, list) or len(apps) != 1 or not isinstance(apps[0], Mapping) or apps[0].get("app_package") != package or not isinstance(counts, Mapping):
            return None
        if _goal_candidate_policy_status(
            apps[0].get("goal_candidate_policy")
        ) != "current":
            return None
        candidates = apps[0].get("goal_candidates")
        if not isinstance(candidates, list):
            return None
        state_counts = {state: 0 for state in GOAL_STATES}
        applicable_ids: list[str] = []
        applicable_families: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                return None
            state = str(candidate.get("applicability_state") or "")
            candidate_id = str(candidate.get("candidate_id") or "")
            family_id = str(candidate.get("family_id") or "")
            if state not in GOAL_STATES or not MACHINE_ID_RE.fullmatch(candidate_id) or candidate_id in seen or not re.fullmatch(r"[a-z][a-z0-9_]*", family_id):
                return None
            if candidate.get("final_action_auto_click_allowed") is not False or candidate.get("unsafe_action_auto_click_allowed") is not False:
                return None
            seen.add(candidate_id)
            state_counts[state] += 1
            if state == "applicable":
                applicable_ids.append(candidate_id)
                applicable_families.append(family_id)
        compact_counts = {key: value for key, value in state_counts.items() if value}
        if (
            counts.get("selected_app_count") != 1
            or counts.get("candidate_count") != len(candidates)
            or counts.get("applicability_states") != compact_counts
        ):
            return None
        return {
            **compact_counts,
            "candidate_count": len(candidates),
            "applicable_candidate_ids": applicable_ids,
            "applicable_family_ids": applicable_families,
            "artifact_sha256": _sha256(artifact_path),
            "source_run_id": str(source_manifest["run_id"]),
            "source_snapshot_id": str(snapshot_metadata["snapshot_id"]),
            "goal_candidate_policy_version": GOAL_CANDIDATE_POLICY_VERSION,
            "goal_candidate_policy_sha256": GOAL_CANDIDATE_POLICY_SHA256,
        }

    def _directed_complete(
        self,
        run_dir: Path,
        manifest: Mapping[str, Any],
        evidence: Mapping[str, Any],
        artifact_path: Path,
    ) -> bool:
        expected = set(str(value) for value in evidence.get("applicable_candidate_ids", []))
        if not expected:
            return False
        plan = manifest.get("goal_candidate_plan")
        snapshot_metadata = manifest.get("inventory_snapshot")
        compact_state_counts = {
            state: int(evidence.get(state, 0))
            for state in GOAL_STATES
            if int(evidence.get(state, 0)) > 0
        }
        artifact_sha = str(evidence.get("artifact_sha256") or "")
        family_sha = _sha256(self.family_manifest)
        if (
            not isinstance(plan, Mapping)
            or not isinstance(snapshot_metadata, Mapping)
            or snapshot_metadata.get("goal_candidate_plan") != plan
            or plan.get("source_run_id") != evidence.get("source_run_id")
            or plan.get("source_inventory_snapshot_id") != evidence.get("source_snapshot_id")
            or plan.get("state_counts") != compact_state_counts
            or int(plan.get("selected_candidate_count", -1)) != len(expected)
            or set(plan.get("selected_candidate_ids") or []) != expected
            or self._source_path_from_metadata(
                plan.get("artifact"),
                expected_path=artifact_path,
                expected_sha256=artifact_sha,
            ) is None
            or self._source_path_from_metadata(
                plan.get("family_manifest"),
                expected_path=self.family_manifest,
                expected_sha256=family_sha,
            ) is None
        ):
            return False
        selection = plan.get("selection")
        if not isinstance(selection, list) or {
            str(row.get("candidate_id") or "")
            for row in selection
            if isinstance(row, Mapping)
        } != expected:
            return False
        for row in selection:
            if (
                not isinstance(row, Mapping)
                or row.get("source_run_id") != evidence.get("source_run_id")
                or row.get("source_inventory_snapshot_id") != evidence.get("source_snapshot_id")
                or row.get("source_artifact_sha256") != artifact_sha
            ):
                return False
        tasks = manifest.get("tasks")
        if not isinstance(tasks, list) or set(str(task.get("candidate_id") or "") for task in tasks if isinstance(task, Mapping)) != expected:
            return False
        for task in tasks:
            if (
                not isinstance(task, Mapping)
                or task.get("source_run_id") != evidence.get("source_run_id")
                or task.get("source_inventory_snapshot_id") != evidence.get("source_snapshot_id")
                or task.get("source_artifact_sha256") != artifact_sha
            ):
                return False
        metrics_path = run_dir / "metrics.jsonl"
        if not metrics_path.is_file() or metrics_path.is_symlink():
            return False
        reached: set[str] = set()
        try:
            for line in metrics_path.read_text(encoding="utf-8").splitlines():
                value = json.loads(line)
                if not isinstance(value, Mapping) or value.get("metric_dimension") != "task_summary":
                    continue
                candidate_id = str(value.get("goal_candidate_id") or "")
                if (
                    candidate_id in expected
                    and value.get("terminal_status") == "destination_reached"
                    and value.get("candidate_destination_found") is True
                    and int(value.get("unsafe_auto_click_count", -1)) == 0
                    and int(value.get("final_action_auto_click_count", -1)) == 0
                ):
                    reached.add(candidate_id)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
            return False
        return reached == expected

    def _graph_lineage_valid(self, stage: Mapping[str, Any]) -> bool:
        pinned = self._pinned_snapshot(stage)
        candidates = stage.get("goal_candidates")
        discovery = stage.get(STAGE_DISCOVERY)
        directed = stage.get(STAGE_DIRECTED)
        graph = stage.get("graph_coverage_validation")
        if (
            pinned is None
            or not isinstance(candidates, Mapping)
            or candidates.get("status") != "passed"
            or not isinstance(discovery, Mapping)
            or (discovery.get("validation") or {}).get("status") != "passed"
            or not isinstance(directed, Mapping)
            or (directed.get("validation") or {}).get("status") != "passed"
            or not isinstance(graph, Mapping)
            or graph.get("status") != "passed"
        ):
            return False
        snapshot_path, snapshot_id, _snapshot_sha = pinned
        package = str(stage.get("package") or "")
        try:
            artifact_path = self._restore_observation_path(candidates.get("path"))
            discovery_run = self._restore_observation_path(discovery.get("run_directory"))
            directed_run = self._restore_observation_path(directed.get("run_directory"))
        except LoopError:
            return False
        source_manifest = self._trusted_manifest(
            discovery_run,
            expected_stage=STAGE_DISCOVERY,
            expected_package=package,
            expected_snapshot_id=snapshot_id,
        )
        evidence = (
            self._goal_evidence(
                artifact_path,
                source_manifest=source_manifest,
                snapshot_path=snapshot_path,
                package=package,
            )
            if source_manifest is not None
            else None
        )
        directed_manifest = self._trusted_manifest(
            directed_run,
            expected_stage=STAGE_DIRECTED,
            expected_package=package,
            expected_snapshot_id=snapshot_id,
        )
        return bool(
            evidence is not None
            and candidates.get("sha256") == evidence.get("artifact_sha256")
            and candidates.get("evidence") == evidence
            and directed_manifest is not None
            and self._directed_complete(
                directed_run,
                directed_manifest,
                evidence,
                artifact_path,
            )
            and graph.get("source_run_id") == directed.get("run_id")
            and set(graph.get("applicable_candidate_ids") or [])
            == set(evidence.get("applicable_candidate_ids") or [])
            and graph.get("canonical_promotion_allowed") is False
            and graph.get("route_lifecycle") == ROUTE_LIFECYCLE
        )

    def _ensure_stage(self, record: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        package = str(record["package"])
        version_key = str(record["version_key"])
        identity = version_identity(package, version_key)
        fingerprint = _policy_fingerprint(record)
        current = self._state["stages"].get(identity)
        if isinstance(current, Mapping) and current.get("policy_fingerprint") != fingerprint:
            self._failure("policy_lineage", "sensitivity_policy_changed", identity)
            current = None
        if not isinstance(current, Mapping):
            current = {
                "package": package,
                "version_key": version_key,
                "version_name": record.get("version_name"),
                "version_code": record.get("version_code"),
                "policy_fingerprint": fingerprint,
                "sensitivity_categories": sorted(str(value) for value in record.get("sensitivity_categories", [])),
                "sensitivity_handling": str(record.get("sensitivity_handling") or ""),
                "coverage_stage": "initial_capture_pending",
            }
            self._state["stages"][identity] = current
        return identity, current

    def _ensure_scheduler_metadata(
        self,
        stage: dict[str, Any],
        priority: Mapping[str, Any],
        record: Mapping[str, Any],
        *,
        current_round: int,
        legacy: bool,
    ) -> dict[str, Any]:
        scheduler = stage.get("scheduler")
        if isinstance(scheduler, Mapping):
            return dict(scheduler) if not isinstance(scheduler, dict) else scheduler
        change_status = str(record.get("change_status") or "unknown")
        observation_status = str(record.get("observation_status") or "unknown")
        scheduler = {
            "first_seen_round": 1 if legacy else current_round,
            "admission_lane": (
                "fresh" if change_status in {"new", "updated"} else "backlog"
            ),
            "admission_reason": f"{change_status}:{observation_status}",
            "first_inventory_rank": int(priority["priority_rank"]),
            "last_selected_round": 0,
            "selection_count": 0,
        }
        stage["scheduler"] = scheduler
        return scheduler

    def _mark_scheduler_selection(self, item: WorkItem, current_round: int) -> None:
        stage = self._state["stages"][item.identity]
        scheduler = stage.get("scheduler")
        if not isinstance(scheduler, dict):
            raise LoopError("scheduler_metadata_invalid")
        scheduler["last_selected_round"] = current_round
        scheduler["selection_count"] = int(scheduler["selection_count"]) + 1

    def _pinned_snapshot(self, stage: Mapping[str, Any]) -> tuple[Path, str, str] | None:
        initial = stage.get(STAGE_INITIAL)
        if not isinstance(initial, Mapping) or (initial.get("validation") or {}).get("status") != "passed":
            return None
        path = self._restore_observation_path(initial.get("snapshot_path"))
        sha = str(initial.get("snapshot_sha256") or "")
        snapshot_id = str(initial.get("snapshot_id") or "")
        if not path.is_file() or path.is_symlink() or not path.is_relative_to(self.inventory_root) or not SHA256_RE.fullmatch(sha) or _sha256(path) != sha:
            return None
        try:
            snapshot = _json(path, "inventory_snapshot_invalid")
            self._validate_snapshot(snapshot, path)
        except LoopError:
            return None
        package = str(stage.get("package") or "")
        version_key = str(stage.get("version_key") or "")
        matching = [
            row
            for row in snapshot.get("included_apps", [])
            if isinstance(row, Mapping) and row.get("package") == package
        ]
        if (
            snapshot.get("snapshot_id") != snapshot_id
            or len(matching) != 1
            or matching[0].get("version_key") != version_key
            or _policy_fingerprint(matching[0]) != stage.get("policy_fingerprint")
        ):
            return None
        try:
            run_dir = self._restore_observation_path(initial.get("run_directory"))
        except LoopError:
            return None
        if self._trusted_manifest(
            run_dir,
            expected_stage=STAGE_INITIAL,
            expected_package=package,
            expected_snapshot_id=snapshot_id,
        ) is None:
            return None
        return path, snapshot_id, sha

    def _work_from(
        self,
        action: str,
        record: Mapping[str, Any],
        priority_rank: int,
        snapshot_path: Path,
        snapshot_id: str,
        snapshot_sha: str,
        *,
        artifact_path: Path | None = None,
        artifact_sha: str | None = None,
    ) -> WorkItem:
        return WorkItem(
            action=action,
            package=str(record["package"]),
            version_key=str(record["version_key"]),
            version_name=str(record["version_name"]) if record.get("version_name") is not None else None,
            version_code=str(record["version_code"]) if record.get("version_code") is not None else None,
            priority_rank=priority_rank,
            sensitivity_categories=tuple(sorted(str(value) for value in record.get("sensitivity_categories", []))),
            sensitivity_handling=str(record.get("sensitivity_handling") or ""),
            snapshot_id=snapshot_id,
            snapshot_path=snapshot_path,
            snapshot_sha256=snapshot_sha,
            goal_artifact_path=artifact_path,
            goal_artifact_sha256=artifact_sha,
        )

    def _validated_active_work(
        self, included: Mapping[str, Mapping[str, Any]]
    ) -> WorkItem | None:
        """Return active work only when its complete pinned lineage is valid."""

        active = self._state.get("active_task")
        if not isinstance(active, Mapping):
            return None
        package = str(active.get("package") or "")
        version_key = str(active.get("version_key") or "")
        identity = str(active.get("identity") or "")
        try:
            computed_identity = version_identity(package, version_key)
        except LoopError:
            computed_identity = ""
        record = included.get(package)
        try:
            snapshot_path = self._restore_observation_path(active.get("snapshot_path"))
            artifact_path = self._restore_observation_path(active.get("goal_artifact_path")) if active.get("goal_artifact_path") else None
            pinned_snapshot = _json(snapshot_path, "inventory_snapshot_invalid")
            self._validate_snapshot(pinned_snapshot, snapshot_path)
        except LoopError:
            record = None
            snapshot_path = Path()
            artifact_path = None
            pinned_snapshot = {}
        pinned_records = [
            row
            for row in pinned_snapshot.get("included_apps", [])
            if isinstance(row, Mapping) and row.get("package") == package
        ]
        valid = (
            identity == computed_identity
            and active.get("stage") in COLLECTION_STAGES
            and record is not None
            and record.get("version_key") == version_key
            and _policy_fingerprint(record) == active.get("policy_fingerprint")
            and snapshot_path.is_file()
            and not snapshot_path.is_symlink()
            and _sha256(snapshot_path) == active.get("snapshot_sha256")
            and pinned_snapshot.get("snapshot_id") == active.get("snapshot_id")
            and len(pinned_records) == 1
            and pinned_records[0].get("version_key") == active.get("version_key")
            and _policy_fingerprint(pinned_records[0]) == active.get("policy_fingerprint")
        )
        stage_state = self._state["stages"].get(identity)
        valid = bool(
            valid
            and isinstance(stage_state, Mapping)
            and stage_state.get("package") == package
            and stage_state.get("version_key") == version_key
            and stage_state.get("policy_fingerprint")
            == active.get("policy_fingerprint")
        )
        if valid and active.get("stage") != STAGE_INITIAL:
            pinned = self._pinned_snapshot(stage_state) if isinstance(stage_state, Mapping) else None
            valid = bool(
                pinned
                and pinned[0] == snapshot_path
                and pinned[1] == active.get("snapshot_id")
                and pinned[2] == active.get("snapshot_sha256")
            )
        if valid and active.get("stage") == STAGE_DIRECTED:
            valid = (
                artifact_path is not None
                and artifact_path.is_file()
                and not artifact_path.is_symlink()
                and _sha256(artifact_path) == active.get("goal_artifact_sha256")
                and _sha256(self.family_manifest) == active.get("family_manifest_sha256")
            )
            candidates = stage_state.get("goal_candidates") if isinstance(stage_state, Mapping) else None
            discovery = stage_state.get(STAGE_DISCOVERY) if isinstance(stage_state, Mapping) else None
            if valid and isinstance(candidates, Mapping) and isinstance(discovery, Mapping):
                try:
                    source_run = self._restore_observation_path(discovery.get("run_directory"))
                except LoopError:
                    source_run = Path()
                source_manifest = self._trusted_manifest(
                    source_run,
                    expected_stage=STAGE_DISCOVERY,
                    expected_package=package,
                    expected_snapshot_id=str(active.get("snapshot_id") or ""),
                )
                evidence = (
                    self._goal_evidence(
                        artifact_path,
                        source_manifest=source_manifest,
                        snapshot_path=snapshot_path,
                        package=package,
                    )
                    if source_manifest is not None and artifact_path is not None
                    else None
                )
                valid = bool(
                    evidence
                    and candidates.get("sha256") == active.get("goal_artifact_sha256")
                    and candidates.get("source_run_id") == evidence.get("source_run_id")
                    and candidates.get("source_snapshot_id") == evidence.get("source_snapshot_id")
                )
            else:
                valid = False
        if not valid:
            return None
        return self._work_from(
            str(active["stage"]),
            record,
            int(active.get("priority_rank") or 1),
            snapshot_path,
            str(active["snapshot_id"]),
            str(active["snapshot_sha256"]),
            artifact_path=artifact_path,
            artifact_sha=str(active.get("goal_artifact_sha256") or "") or None,
        )

    def _active_work(self, included: Mapping[str, Mapping[str, Any]]) -> WorkItem | None:
        active = self._state.get("active_task")
        if not isinstance(active, Mapping):
            return None
        work = self._validated_active_work(included)
        if work is None:
            failed_identity = str(active.get("identity") or "") or None
            self._failure("active_lineage", "active_task_lineage_mismatch", failed_identity)
            self._state["active_task"] = None
            self._save("active_task_lineage_mismatch")
            raise LoopError("active_task_lineage_mismatch")
        return work

    def _next_work_for_priority(
        self,
        priority: Mapping[str, Any],
        record: Mapping[str, Any],
        snapshot: Mapping[str, Any],
        snapshot_path: Path,
        current_round: int,
    ) -> tuple[WorkItem | None, bool]:
        """Resolve one app's next stage without considering cross-app fairness."""

        identity, stage = self._ensure_stage(record)
        stage["coverage_stage"] = coverage_stage(stage)
        priority_rank = int(priority["priority_rank"])
        existing_candidates = stage.get("goal_candidates")
        if (
            isinstance(existing_candidates, Mapping)
            and existing_candidates.get("status") == "passed"
        ):
            stored_policy_status = _goal_candidate_policy_status(
                existing_candidates.get("goal_candidate_policy")
            )
            try:
                existing_artifact_path = self._restore_observation_path(
                    existing_candidates.get("path")
                )
                artifact_policy_status = self._goal_artifact_policy_status(
                    existing_artifact_path
                )
            except LoopError:
                artifact_policy_status = "invalid"
            if stored_policy_status != "current" or artifact_policy_status in {
                "legacy_missing",
                "tampered",
            }:
                stale_pinned = self._pinned_snapshot(stage)
                stale_discovery = stage.get(STAGE_DISCOVERY)
                if (
                    stale_pinned is None
                    or not isinstance(stale_discovery, Mapping)
                    or (stale_discovery.get("validation") or {}).get("status")
                    != "passed"
                ):
                    raise LoopError("goal_candidate_stale_discovery_lineage_invalid")
                detected_status = (
                    stored_policy_status
                    if stored_policy_status != "current"
                    else artifact_policy_status
                )
                reason_code = (
                    "goal_candidate_stage_policy_stale"
                    if stored_policy_status != "current"
                    else "goal_candidate_artifact_policy_stale"
                )
                self._mark_goal_candidates_stale(
                    stage,
                    identity=identity,
                    reason_code=reason_code,
                    detected_policy_status=detected_status,
                )
                return (
                    self._work_from(
                        "generate_goal_candidates",
                        record,
                        priority_rank,
                        *stale_pinned,
                    ),
                    False,
                )
        if is_graph_coverage_validated(stage):
            if not self._graph_lineage_valid(stage):
                previous_graph = stage.get("graph_coverage_validation")
                stage["graph_coverage_validation"] = {
                    "status": "failed_lineage_mismatch",
                    "reason_code": "graph_lineage_mismatch",
                    "previous_source_run_id": (
                        previous_graph.get("source_run_id")
                        if isinstance(previous_graph, Mapping)
                        else None
                    ),
                    "canonical_promotion_allowed": False,
                }
                directed_record = dict(stage.get(STAGE_DIRECTED) or {})
                directed_record["status"] = "failed"
                directed_record["validation"] = {
                    "status": "failed",
                    "error_code": "graph_lineage_mismatch",
                }
                stage[STAGE_DIRECTED] = directed_record
                stage["coverage_stage"] = coverage_stage(stage)
                raise LoopError("graph_lineage_mismatch")
            if (
                self.build_research_artifacts
                and (stage.get("research_artifacts") or {}).get("status") != "passed"
            ):
                pinned = self._pinned_snapshot(stage)
                directed = stage.get(STAGE_DIRECTED)
                if pinned and isinstance(directed, Mapping):
                    path = self._restore_observation_path(
                        (stage.get("goal_candidates") or {}).get("path")
                    )
                    return (
                        self._work_from(
                            "build_research_artifacts",
                            record,
                            priority_rank,
                            *pinned,
                            artifact_path=path,
                            artifact_sha=str(
                                (stage.get("goal_candidates") or {}).get("sha256")
                                or ""
                            ),
                        ),
                        False,
                    )
            return None, False
        pinned = self._pinned_snapshot(stage)
        if pinned is None:
            return (
                self._work_from(
                    STAGE_INITIAL,
                    record,
                    priority_rank,
                    snapshot_path,
                    str(snapshot["snapshot_id"]),
                    _sha256(snapshot_path),
                ),
                False,
            )
        pinned_path, pinned_id, pinned_sha = pinned
        discovery = stage.get(STAGE_DISCOVERY)
        if (
            not isinstance(discovery, Mapping)
            or (discovery.get("validation") or {}).get("status") != "passed"
        ):
            return (
                self._work_from(
                    STAGE_DISCOVERY,
                    record,
                    priority_rank,
                    pinned_path,
                    pinned_id,
                    pinned_sha,
                ),
                False,
            )
        candidates = stage.get("goal_candidates")
        if not isinstance(candidates, Mapping) or candidates.get("status") != "passed":
            return (
                self._work_from(
                    "generate_goal_candidates",
                    record,
                    priority_rank,
                    pinned_path,
                    pinned_id,
                    pinned_sha,
                ),
                False,
            )
        stored_policy_status = _goal_candidate_policy_status(
            candidates.get("goal_candidate_policy")
        )
        if stored_policy_status != "current":
            self._mark_goal_candidates_stale(
                stage,
                identity=identity,
                reason_code="goal_candidate_stage_policy_stale",
                detected_policy_status=stored_policy_status,
            )
            return (
                self._work_from(
                    "generate_goal_candidates",
                    record,
                    priority_rank,
                    pinned_path,
                    pinned_id,
                    pinned_sha,
                ),
                False,
            )
        evidence = candidates.get("evidence")
        if not isinstance(evidence, Mapping):
            raise LoopError("goal_candidate_evidence_missing")
        try:
            artifact_path = self._restore_observation_path(candidates.get("path"))
            source_run = self._restore_observation_path(discovery.get("run_directory"))
        except LoopError as error:
            raise LoopError("goal_candidate_lineage_mismatch") from error
        source_manifest = self._trusted_manifest(
            source_run,
            expected_stage=STAGE_DISCOVERY,
            expected_package=str(record["package"]),
            expected_snapshot_id=pinned_id,
        )
        current_evidence = (
            self._goal_evidence(
                artifact_path,
                source_manifest=source_manifest,
                snapshot_path=pinned_path,
                package=str(record["package"]),
            )
            if source_manifest is not None
            else None
        )
        if current_evidence is None:
            artifact_policy_status = self._goal_artifact_policy_status(
                artifact_path
            )
            if artifact_policy_status in {"legacy_missing", "tampered"}:
                self._mark_goal_candidates_stale(
                    stage,
                    identity=identity,
                    reason_code="goal_candidate_artifact_policy_stale",
                    detected_policy_status=artifact_policy_status,
                )
                return (
                    self._work_from(
                        "generate_goal_candidates",
                        record,
                        priority_rank,
                        pinned_path,
                        pinned_id,
                        pinned_sha,
                    ),
                    False,
                )
            raise LoopError("goal_candidate_lineage_mismatch")
        if (
            dict(evidence) != current_evidence
            or candidates.get("sha256") != current_evidence.get("artifact_sha256")
        ):
            raise LoopError("goal_candidate_lineage_mismatch")
        if int(evidence.get("applicable", 0)) == 0:
            if current_round >= int(
                stage.get("next_neutral_discovery_round") or current_round
            ):
                return (
                    self._work_from(
                        STAGE_DISCOVERY,
                        record,
                        priority_rank,
                        pinned_path,
                        pinned_id,
                        pinned_sha,
                    ),
                    False,
                )
            return None, True
        directed = stage.get(STAGE_DIRECTED)
        if (
            not isinstance(directed, Mapping)
            or (directed.get("validation") or {}).get("status") != "passed"
        ):
            return (
                self._work_from(
                    STAGE_DIRECTED,
                    record,
                    priority_rank,
                    pinned_path,
                    pinned_id,
                    pinned_sha,
                    artifact_path=artifact_path,
                    artifact_sha=str(candidates.get("sha256") or ""),
                ),
                False,
            )
        return None, False

    def _select(self, snapshot: Mapping[str, Any], snapshot_path: Path) -> WorkItem | None:
        included = {
            str(row["package"]): row
            for row in snapshot["included_apps"]
            if isinstance(row, Mapping)
        }
        active = self._active_work(included)
        if active:
            return active

        current_round = int(self._state["next_round"])
        existing_identities = set(self._state["stages"])
        entries = [
            (priority, included[str(priority["package"])])
            for priority in sorted(
                snapshot["prioritized_apps"],
                key=lambda row: int(row["priority_rank"]),
            )
        ]
        # Admit every visible version before choosing work. This preserves its
        # first-seen/newness evidence beyond the one inventory snapshot where
        # discovery reports it and gives lower-ranked apps persistent age.
        for priority, record in entries:
            identity, stage = self._ensure_stage(record)
            self._ensure_scheduler_metadata(
                stage,
                priority,
                record,
                current_round=current_round,
                legacy=identity in existing_identities,
            )

        def fairness_key(
            entry: tuple[Mapping[str, Any], Mapping[str, Any]],
        ) -> tuple[int, int, int, int, str]:
            priority, record = entry
            identity = version_identity(
                str(record["package"]), str(record["version_key"])
            )
            scheduler = self._state["stages"][identity]["scheduler"]
            return (
                int(scheduler["selection_count"]),
                int(scheduler["last_selected_round"]),
                int(scheduler["first_seen_round"]),
                int(priority["priority_rank"]),
                identity,
            )

        offline_entries = [
            (priority, record)
            for priority, record in entries
            if (
                (identity := version_identity(
                    str(record["package"]), str(record["version_key"])
                ))
                in existing_identities
                and (
                    coverage_stage(self._state["stages"].get(identity))
                    == "goal_candidate_generation_pending"
                    or self._passed_goal_candidate_policy_status(
                        self._state["stages"][identity]
                    )
                    in {"legacy_missing", "tampered"}
                )
            )
        ]
        deferred_identities: set[str] = set()

        def first_work(
            candidates: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
            *,
            required_action: str | None = None,
        ) -> WorkItem | None:
            for priority, record in candidates:
                work, deferred = self._next_work_for_priority(
                    priority,
                    record,
                    snapshot,
                    snapshot_path,
                    current_round,
                )
                if deferred:
                    deferred_identities.add(
                        version_identity(
                            str(record["package"]), str(record["version_key"])
                        )
                    )
                if work is not None and (
                    required_action is None or work.action == required_action
                ):
                    return work
            return None

        # Candidate generation is local, deterministic, and monotonic for a
        # validated discovery run. Drain this finite queue globally instead of
        # stranding it behind the inventory's unobserved-app rank ordering.
        offline = first_work(
            sorted(offline_entries, key=fairness_key),
            required_action="generate_goal_candidates",
        )
        if offline is not None:
            self._mark_scheduler_selection(offline, current_round)
            return offline

        started_entries = [
            entry
            for entry in entries
            if version_identity(
                str(entry[1]["package"]), str(entry[1]["version_key"])
            )
            in existing_identities
        ]
        inventory_entries = [
            entry
            for entry in entries
            if version_identity(
                str(entry[1]["package"]), str(entry[1]["version_key"])
            )
            not in existing_identities
        ]
        # Round parity is a persisted, restart-stable fairness cursor. When
        # both lanes contain work, each receives at least every other round;
        # priority_rank remains the deterministic order inside each lane.
        lanes = (
            (
                sorted(started_entries, key=fairness_key),
                sorted(inventory_entries, key=fairness_key),
            )
            if current_round % 2 == 0
            else (
                sorted(inventory_entries, key=fairness_key),
                sorted(started_entries, key=fairness_key),
            )
        )
        for lane in lanes:
            work = first_work(lane)
            if work is not None:
                self._mark_scheduler_selection(work, current_round)
                return work
        if deferred_identities:
            self._event(
                "neutral_rediscovery_wait",
                deferred_app_version_count=len(deferred_identities),
            )
        return None

    def _run_id(self, item: WorkItem) -> str:
        label = {STAGE_INITIAL: "capture", STAGE_DISCOVERY: "discovery", STAGE_DIRECTED: "directed"}.get(item.action, "research")
        stamp = re.sub(r"[^0-9]", "", _iso(self.clock))[:14]
        digest = hashlib.sha256(f"{item.identity}|{item.action}|{self._state['next_round']}".encode()).hexdigest()[:10]
        return f"physical-loop-{label}-{stamp}-{digest}"

    def _collection_command(self, item: WorkItem, run_id: str, resume: bool) -> list[str]:
        command = [
            self.python_executable,
            str(self.repo_root / "scripts" / COLLECTOR_SCRIPT),
            "--inventory-snapshot",
            str(item.snapshot_path),
            "--only-package",
            item.package,
            "--max-apps",
            "1",
            "--serial",
            EXPECTED_SERIAL,
            "--adb",
            self.adb_executable,
            "--api-base-url",
            self.api_base_url,
            "--output-root",
            str(self.observation_root),
            "--run-id",
            run_id,
            "--screenshot-policy",
            "none",
        ]
        if item.action == STAGE_INITIAL:
            command += ["--capture-only", "--max-actions", "0", "--max-scrolls", "0", "--max-backs", "0", "--max-screen-visits", "1"]
        elif item.action == STAGE_DISCOVERY:
            command += ["--discovery-explore"]
        elif item.action == STAGE_DIRECTED:
            if item.goal_artifact_path is None:
                raise LoopError("goal_artifact_missing_for_directed_stage")
            command += ["--goal-candidates", str(item.goal_artifact_path), "--family-manifest", str(self.family_manifest)]
        else:
            raise LoopError("collection_stage_invalid")
        if resume:
            command.append("--resume")
        return command

    @staticmethod
    def _manifest_task_ids(manifest: Mapping[str, Any]) -> set[str] | None:
        snapshot = manifest.get("inventory_snapshot")
        snapshot_tasks = (
            snapshot.get("selected_tasks") if isinstance(snapshot, Mapping) else None
        )
        task_sources = [snapshot_tasks]
        if manifest.get("tasks") is not None:
            task_sources.append(manifest.get("tasks"))
        expected: set[str] | None = None
        for rows in task_sources:
            if not isinstance(rows, list) or not rows:
                return None
            raw_task_ids = [
                row.get("task_id") for row in rows if isinstance(row, Mapping)
            ]
            if (
                len(raw_task_ids) != len(rows)
                or any(not isinstance(task_id, str) for task_id in raw_task_ids)
            ):
                return None
            task_ids = [str(task_id) for task_id in raw_task_ids]
            if (
                len(task_ids) != len(set(task_ids))
                or any(not MACHINE_ID_RE.fullmatch(task_id) for task_id in task_ids)
            ):
                return None
            current = set(task_ids)
            if expected is not None and current != expected:
                return None
            expected = current
        return expected

    def _trusted_completed_run(
        self,
        item: WorkItem,
        run_dir: Path,
    ) -> tuple[dict[str, Any], list[str]] | None:
        """Return an immutable validated completion without reopening its collector."""

        manifest = self._trusted_manifest(
            run_dir,
            expected_stage=item.action,
            expected_package=item.package,
            expected_snapshot_id=item.snapshot_id,
        )
        if manifest is None:
            return None
        try:
            checkpoint = _json(run_dir / "checkpoint.json", "checkpoint_invalid")
        except LoopError:
            return None
        state = checkpoint.get("state")
        completed = state.get("completed_task_ids") if isinstance(state, Mapping) else None
        statuses = state.get("statuses") if isinstance(state, Mapping) else None
        task_ids = self._manifest_task_ids(manifest)
        normalized_statuses = (
            {str(task_id): str(value) for task_id, value in statuses.items()}
            if isinstance(statuses, Mapping)
            else {}
        )
        if (
            checkpoint.get("run_id") != manifest.get("run_id")
            or checkpoint.get("status") != "completed"
            or checkpoint.get("exploration_stage") != item.action
            or task_ids is None
            or not isinstance(completed, list)
            or any(not isinstance(task_id, str) for task_id in completed)
            or len(completed) != len(set(completed))
            or set(str(task_id) for task_id in completed) != task_ids
            or not isinstance(statuses, Mapping)
            or len(normalized_statuses) != len(statuses)
            or set(normalized_statuses) != task_ids
        ):
            return None
        values = [normalized_statuses[task_id] for task_id in sorted(task_ids)]
        if (
            not values
            or any(value not in EXPECTED_TERMINAL_STATUSES[item.action] for value in values)
        ):
            return None
        rechecked = self._trusted_manifest(
            run_dir,
            expected_stage=item.action,
            expected_package=item.package,
            expected_snapshot_id=item.snapshot_id,
        )
        if rechecked != manifest:
            return None
        return manifest, values

    def _directed_collection_complete(
        self,
        item: WorkItem,
        stage: Mapping[str, Any],
        run_dir: Path,
        manifest: Mapping[str, Any],
    ) -> bool:
        candidates = stage.get("goal_candidates")
        evidence = candidates.get("evidence") if isinstance(candidates, Mapping) else None
        return bool(
            isinstance(evidence, Mapping)
            and item.goal_artifact_path is not None
            and self._directed_complete(
                run_dir,
                manifest,
                evidence,
                item.goal_artifact_path,
            )
        )

    def _finish_validated_collection(
        self,
        item: WorkItem,
        run_id: str,
        run_dir: Path,
        record: dict[str, Any],
        values: Sequence[str],
        *,
        adopted: bool,
    ) -> tuple[str, None]:
        stage = self._state["stages"][item.identity]
        record.pop("boundary_code", None)
        record["status"] = "passed"
        record["terminal_statuses"] = sorted(str(value) for value in values)
        record["validation"] = {
            "status": "passed",
            "marker_sha256": _sha256(run_dir / VALIDATED),
            "manifest_sha256": _sha256(run_dir / "manifest.json"),
        }
        stage[item.action] = record
        self._state["active_task"] = None
        if item.action == STAGE_INITIAL:
            self._state["counters"]["initial_capture_passes"] += 1
        elif item.action == STAGE_DISCOVERY:
            self._state["counters"]["neutral_discovery_passes"] += 1
            previous_candidates = stage.get("goal_candidates")
            previous_evidence = (
                previous_candidates.get("evidence")
                if isinstance(previous_candidates, Mapping)
                else None
            )
            if isinstance(previous_evidence, Mapping):
                history = list(stage.get("applicability_history") or [])
                history.append(
                    {
                        "source_run_id": previous_candidates.get("source_run_id"),
                        "artifact_sha256": previous_candidates.get("sha256"),
                        "applicable": int(previous_evidence.get("applicable", 0)),
                        "not_applicable": int(previous_evidence.get("not_applicable", 0)),
                        "authentication_boundary": int(
                            previous_evidence.get("authentication_boundary", 0)
                        ),
                        "unverified": int(previous_evidence.get("unverified", 0)),
                        "superseded_by_neutral_run_id": run_id,
                    }
                )
                stage["applicability_history"] = history
            stage.pop("goal_candidates", None)
            stage.pop(STAGE_DIRECTED, None)
            stage.pop("graph_coverage_validation", None)
            stage.pop("research_artifacts", None)
            stage["neutral_discovery_generation"] = int(
                stage.get("neutral_discovery_generation", 0)
            ) + 1
        else:
            self._state["counters"]["directed_exploration_passes"] += 1
            stage["graph_coverage_validation"] = {
                "status": "passed",
                "source_run_id": run_id,
                "applicable_candidate_ids": list(
                    (stage["goal_candidates"]["evidence"])["applicable_candidate_ids"]
                ),
                "human_review_required": True,
                "canonical_promotion_allowed": False,
                "route_lifecycle": ROUTE_LIFECYCLE,
            }
            self._state["counters"]["graph_coverage_passes"] += 1
        stage["coverage_stage"] = coverage_stage(stage)
        if adopted:
            self._event(
                "validated_collection_adopted",
                version_identity=item.identity,
                stage=item.action,
                run_id=run_id,
            )
        self._event(
            "collection_stage_validated",
            version_identity=item.identity,
            stage=item.action,
            run_id=run_id,
        )
        self._save(stage["coverage_stage"])
        return stage["coverage_stage"], None

    def _collect(self, item: WorkItem) -> tuple[str, str | None]:
        active = self._state.get("active_task")
        resume_lineage = isinstance(active, Mapping) and active.get("stage") == item.action
        run_id = str(active.get("run_id")) if resume_lineage else self._run_id(item)
        if not MACHINE_ID_RE.fullmatch(run_id):
            raise LoopError("run_id_invalid")
        run_dir = self.observation_root / run_id
        collector_resume = resume_lineage and run_dir.is_dir()
        stage = self._state["stages"][item.identity]
        record = dict(stage.get(item.action) or {})
        marker_path = run_dir / VALIDATED
        marker_present = marker_path.exists() or marker_path.is_symlink()
        if collector_resume and marker_present:
            adopted = self._trusted_completed_run(item, run_dir)
            if adopted is None:
                record["status"] = "failed"
                record["validation"] = {
                    "status": "failed",
                    "error_code": "validated_collection_adoption_invalid",
                }
                stage[item.action] = record
                stage["coverage_stage"] = coverage_stage(stage)
                self._state["active_task"] = None
                self._failure(
                    "validation",
                    "validated_collection_adoption_invalid",
                    item.identity,
                )
                self._save("validated_collection_adoption_invalid")
                raise LoopError("validated_collection_adoption_invalid")
            manifest, values = adopted
            if item.action == STAGE_DIRECTED and not self._directed_collection_complete(
                item,
                stage,
                run_dir,
                manifest,
            ):
                record["status"] = "failed"
                record["validation"] = {
                    "status": "failed",
                    "error_code": "directed_candidate_coverage_incomplete",
                }
                stage[item.action] = record
                stage["coverage_stage"] = coverage_stage(stage)
                self._state["active_task"] = None
                self._failure(
                    "directed_validation",
                    "directed_candidate_coverage_incomplete",
                    item.identity,
                )
                self._save("directed_candidate_coverage_incomplete")
                raise LoopError("directed_candidate_coverage_incomplete")
            return self._finish_validated_collection(
                item,
                run_id,
                run_dir,
                record,
                values,
                adopted=True,
            )
        record.update(
            {
                "status": "running",
                "run_id": run_id,
                "run_directory": self._store_observation_path(self.observation_root / run_id),
                "snapshot_id": item.snapshot_id,
                "snapshot_path": self._store_observation_path(item.snapshot_path),
                "snapshot_sha256": item.snapshot_sha256,
                "attempts": int(record.get("attempts", 0)) + (0 if resume_lineage else 1),
            }
        )
        if item.goal_artifact_path:
            record["goal_artifact_path"] = self._store_observation_path(item.goal_artifact_path)
            record["goal_artifact_sha256"] = item.goal_artifact_sha256
        stage[item.action] = record
        stage["coverage_stage"] = coverage_stage(stage)
        self._state["active_task"] = {
            "identity": item.identity,
            "stage": item.action,
            "package": item.package,
            "version_key": item.version_key,
            "policy_fingerprint": stage["policy_fingerprint"],
            "priority_rank": item.priority_rank,
            "run_id": run_id,
            "snapshot_id": item.snapshot_id,
            "snapshot_path": self._store_observation_path(item.snapshot_path),
            "snapshot_sha256": item.snapshot_sha256,
            "goal_artifact_path": self._store_observation_path(item.goal_artifact_path) if item.goal_artifact_path else None,
            "goal_artifact_sha256": item.goal_artifact_sha256,
            "family_manifest_sha256": _sha256(self.family_manifest) if item.action == STAGE_DIRECTED else None,
        }
        self._save(f"{item.action}_running")
        result = self._run_raw(self._collection_command(item, run_id, collector_resume))
        try:
            report = _command_json(result.stdout, "collector_output_invalid")
        except LoopError:
            report = {}
        statuses = report.get("statuses")
        values = [str(value) for value in statuses.values()] if isinstance(statuses, Mapping) else []
        boundary = next((value for value in values if value.startswith("boundary:")), None)
        if boundary:
            record["status"] = "boundary"
            record["boundary_code"] = boundary.partition(":")[2] or "user_action"
            self._state["counters"]["boundary_stops"] += 1
            self._save("user_action_boundary")
            return "boundary", boundary
        if result.returncode != 0 or report.get("status") == "failed" or any(value.startswith("failed:") for value in values):
            record["status"] = "failed"
            self._failure(item.action, "collector_failed", item.identity, result.returncode)
            self._save(f"{item.action}_failed_resumable")
            raise LoopError("collector_failed")
        if any(value.startswith("stopped:") for value in values):
            record["status"] = "stopped"
            self._failure(item.action, "collector_stopped", item.identity, result.returncode)
            self._save(f"{item.action}_stopped_resumable")
            raise LoopError("collector_stopped")
        if report.get("status") != "completed" or not values or any(value not in EXPECTED_TERMINAL_STATUSES[item.action] for value in values):
            record["status"] = "failed"
            self._failure(item.action, "collector_terminal_status_invalid", item.identity, result.returncode)
            self._state["active_task"] = None
            self._save(f"{item.action}_terminal_status_invalid")
            raise LoopError("collector_terminal_status_invalid")
        validation = self._run_raw(
            (
                self.python_executable,
                str(self.repo_root / "scripts" / VALIDATOR_SCRIPT),
                "--run-dir",
                str(run_dir),
                "--repo-root",
                str(self.repo_root),
                "--observation-root",
                str(self.observation_root),
                "--compact",
            )
        )
        try:
            validation_report = _command_json(validation.stdout, "validator_output_invalid")
        except LoopError:
            validation_report = {}
        manifest = self._trusted_manifest(
            run_dir,
            expected_stage=item.action,
            expected_package=item.package,
            expected_snapshot_id=item.snapshot_id,
        ) if validation.returncode == 0 and validation_report.get("ok") is True else None
        if manifest is None:
            record["status"] = "failed"
            record["validation"] = {"status": "failed", "error_code": "collection_validation_failed"}
            self._state["active_task"] = None
            self._failure("validation", "collection_validation_failed", item.identity, validation.returncode)
            self._save(f"{item.action}_validation_failed")
            raise LoopError("collection_validation_failed")
        if item.action == STAGE_DIRECTED:
            if not self._directed_collection_complete(
                item,
                stage,
                run_dir,
                manifest,
            ):
                record["status"] = "failed"
                record["validation"] = {"status": "failed", "error_code": "directed_candidate_coverage_incomplete"}
                self._state["active_task"] = None
                self._failure("directed_validation", "directed_candidate_coverage_incomplete", item.identity)
                self._save("directed_candidate_coverage_incomplete")
                raise LoopError("directed_candidate_coverage_incomplete")
        return self._finish_validated_collection(
            item,
            run_id,
            run_dir,
            record,
            values,
            adopted=False,
        )

    def _prepare_goal_candidates(
        self,
        item: WorkItem,
    ) -> tuple[Path, dict[str, Any] | None, int | None]:
        stage = self._state["stages"][item.identity]
        discovery = stage.get(STAGE_DISCOVERY)
        if not isinstance(discovery, Mapping) or (discovery.get("validation") or {}).get("status") != "passed":
            raise LoopError("validated_neutral_discovery_required")
        run_dir = self._restore_observation_path(discovery.get("run_directory"))
        source_manifest = self._trusted_manifest(
            run_dir,
            expected_stage=STAGE_DISCOVERY,
            expected_package=item.package,
            expected_snapshot_id=item.snapshot_id,
        )
        if source_manifest is None:
            raise LoopError("neutral_discovery_lineage_invalid")
        default_artifact_path = run_dir / GOAL_ARTIFACT
        current_artifact_path = run_dir / CURRENT_GOAL_ARTIFACT
        default_policy_status = self._goal_artifact_policy_status(
            default_artifact_path
        )
        artifact_path = (
            default_artifact_path
            if default_policy_status in {"current", "invalid"}
            and not current_artifact_path.exists()
            else current_artifact_path
        )
        result: CommandResult | None = None
        if artifact_path.exists():
            # A crash may occur after the generator's atomic publication but
            # before the loop checkpoint advances.  Reuse only a fully
            # hash-bound artifact; never overwrite or force an unknown file.
            evidence = self._goal_evidence(
                artifact_path,
                source_manifest=source_manifest,
                snapshot_path=item.snapshot_path,
                package=item.package,
            )
        else:
            command = [
                self.python_executable,
                str(self.repo_root / "scripts" / GOAL_GENERATOR_SCRIPT),
                "--run-dir",
                str(run_dir),
                "--inventory-snapshot",
                str(item.snapshot_path),
                "--repo-root",
                str(self.repo_root),
                "--observation-root",
                str(self.observation_root),
                "--family-manifest",
                str(self.family_manifest),
            ]
            if artifact_path != default_artifact_path:
                command += ["--output", str(artifact_path)]
            command.append("--compact")
            result = self._run_raw(tuple(command))
            try:
                report = _command_json(result.stdout, "goal_generator_output_invalid")
            except LoopError:
                report = {}
            evidence = self._goal_evidence(
                artifact_path,
                source_manifest=source_manifest,
                snapshot_path=item.snapshot_path,
                package=item.package,
            ) if result.returncode == 0 and report.get("ok") is True else None
        return (
            artifact_path,
            evidence,
            result.returncode if result is not None else None,
        )

    def _apply_goal_candidates(
        self,
        item: WorkItem,
        artifact_path: Path,
        evidence: Mapping[str, Any],
    ) -> str:
        expected_artifact_sha = str(evidence.get("artifact_sha256") or "")
        try:
            current_artifact_sha = (
                _sha256(artifact_path)
                if artifact_path.is_file() and not artifact_path.is_symlink()
                else ""
            )
        except OSError:
            current_artifact_sha = ""
        if (
            not SHA256_RE.fullmatch(expected_artifact_sha)
            or current_artifact_sha != expected_artifact_sha
        ):
            raise LoopError("goal_artifact_changed_after_validation")
        stage = self._state["stages"][item.identity]
        stage["goal_candidates"] = {
            "status": "passed",
            "path": self._store_observation_path(artifact_path),
            "sha256": expected_artifact_sha,
            "source_run_id": evidence["source_run_id"],
            "source_snapshot_id": evidence["source_snapshot_id"],
            "goal_candidate_policy": _goal_candidate_policy(),
            "evidence": dict(evidence),
        }
        self._state["counters"]["goal_candidate_passes"] += 1
        if int(evidence.get("applicable", 0)) == 0:
            stage["next_neutral_discovery_round"] = int(self._state["next_round"]) + self.refresh_rounds_without_applicable
            stage["graph_coverage_validation"] = {
                "status": "pending_more_neutral_evidence",
                "reason_code": "no_applicable_candidate",
                "applicability_evidence": {
                    key: int(evidence.get(key, 0))
                    for key in ("not_applicable", "authentication_boundary", "unverified")
                },
                "canonical_promotion_allowed": False,
            }
            outcome = "neutral_rediscovery_scheduled"
        else:
            stage.pop("next_neutral_discovery_round", None)
            outcome = "goal_directed_exploration_pending"
        stage["coverage_stage"] = coverage_stage(stage)
        return outcome

    def _record_goal_candidate_success(
        self,
        item: WorkItem,
        evidence: Mapping[str, Any],
    ) -> None:
        self._event(
            "goal_candidates_validated",
            version_identity=item.identity,
            applicable_count=int(evidence.get("applicable", 0)),
            not_applicable_count=int(evidence.get("not_applicable", 0)),
            authentication_boundary_count=int(evidence.get("authentication_boundary", 0)),
            unverified_count=int(evidence.get("unverified", 0)),
            graph_coverage_validated=False,
        )

    def _generate_candidates(self, item: WorkItem) -> str:
        stage = self._state["stages"][item.identity]
        artifact_path, evidence, return_code = self._prepare_goal_candidates(item)
        if evidence is None:
            stage["goal_candidates"] = {"status": "failed", "error_code": "goal_candidate_generation_or_lineage_failed"}
            self._failure(
                "goal_candidates",
                "goal_candidate_generation_or_lineage_failed",
                item.identity,
                return_code,
            )
            self._save("goal_candidate_generation_failed")
            raise LoopError("goal_candidate_generation_or_lineage_failed")
        outcome = self._apply_goal_candidates(item, artifact_path, evidence)
        self._record_goal_candidate_success(item, evidence)
        self._save(outcome)
        return outcome

    def _build_research(self, item: WorkItem) -> str:
        stage = self._state["stages"][item.identity]
        graph = stage.get("graph_coverage_validation")
        directed = stage.get(STAGE_DIRECTED)
        if not isinstance(graph, Mapping) or graph.get("status") != "passed" or not isinstance(directed, Mapping):
            raise LoopError("graph_validation_required_for_research")
        run_dir = self._restore_observation_path(directed.get("run_directory"))
        already_published = all(
            (run_dir / name).is_file() and not (run_dir / name).is_symlink()
            for name in RESEARCH_ARTIFACTS
        )
        result: CommandResult | None = None
        report: Mapping[str, Any] = {}
        if already_published:
            try:
                navigation_report = _json(
                    run_dir / "navigation-report.json",
                    "research_report_invalid",
                )
                already_published = (
                    navigation_report.get("source_run_id") == directed.get("run_id")
                    and navigation_report.get("provenance") == PROVENANCE
                    and navigation_report.get("route_lifecycle") == ROUTE_LIFECYCLE
                )
            except LoopError:
                already_published = False
        if not already_published and not any((run_dir / name).exists() for name in RESEARCH_ARTIFACTS):
            result = self._run_raw(
                (
                    self.python_executable,
                    str(self.repo_root / "scripts" / ARTIFACT_BUILDER_SCRIPT),
                    "--run-dir",
                    str(run_dir),
                    "--repo-root",
                    str(self.repo_root),
                    "--compact",
                )
            )
            try:
                report = _command_json(result.stdout, "research_builder_output_invalid")
            except LoopError:
                report = {}
        published = already_published or (
            result is not None
            and result.returncode == 0
            and report.get("ok") is True
            and all(
                (run_dir / name).is_file() and not (run_dir / name).is_symlink()
                for name in RESEARCH_ARTIFACTS
            )
        )
        if not published:
            stage["research_artifacts"] = {"status": "failed", "error_code": "research_artifact_build_failed"}
            self._failure(
                "research_artifacts",
                "research_artifact_build_failed",
                item.identity,
                result.returncode if result is not None else None,
            )
            self._save("research_artifact_build_failed")
            raise LoopError("research_artifact_build_failed")
        stage["research_artifacts"] = {
            "status": "passed",
            "source_run_id": str(directed.get("run_id")),
            "canonical_promotion": "not_recommended_until_human_review",
            "files": list(RESEARCH_ARTIFACTS),
        }
        self._event("research_artifacts_built", version_identity=item.identity)
        self._save("graph_coverage_validated")
        return "graph_coverage_validated"

    @staticmethod
    def _json_clone(value: Any) -> Any:
        return json.loads(_canonical_json(value))

    @staticmethod
    def _run_file_hashes(run_dir: Path) -> dict[str, str]:
        if not run_dir.is_dir() or run_dir.is_symlink():
            raise LoopError("active_boundary_run_invalid")
        hashes: dict[str, str] = {}
        for path in sorted(run_dir.rglob("*"), key=lambda value: value.as_posix()):
            if path.is_symlink():
                raise LoopError("active_boundary_run_symlink_forbidden")
            if path.is_file():
                hashes[path.relative_to(run_dir).as_posix()] = _sha256(path)
        return hashes

    def _offline_active_boundary_guard(self) -> dict[str, Any]:
        active = self._state.get("active_task")
        if not isinstance(active, Mapping) or self._state.get("status") != "user_action_boundary":
            raise LoopError("offline_pending_requires_active_boundary")
        identity = str(active.get("identity") or "")
        action = str(active.get("stage") or "")
        package = str(active.get("package") or "")
        version_key = str(active.get("version_key") or "")
        run_id = str(active.get("run_id") or "")
        try:
            computed_identity = version_identity(package, version_key)
        except LoopError as error:
            raise LoopError(
                "offline_pending_active_boundary_lineage_invalid"
            ) from error
        stage = self._state.get("stages", {}).get(identity)
        record = stage.get(action) if isinstance(stage, Mapping) else None
        boundary_code = str(record.get("boundary_code") or "") if isinstance(record, Mapping) else ""
        auth_tokens = ("auth", "login", "password", "biometric", "fingerprint", "face")
        if (
            action not in COLLECTION_STAGES
            or not PACKAGE_RE.fullmatch(package)
            or identity != computed_identity
            or not MACHINE_ID_RE.fullmatch(run_id)
            or not isinstance(stage, Mapping)
            or not isinstance(record, Mapping)
            or record.get("status") != "boundary"
            or not any(token in boundary_code.casefold() for token in auth_tokens)
            or record.get("run_id") != run_id
            or record.get("snapshot_id") != active.get("snapshot_id")
            or record.get("snapshot_path") != active.get("snapshot_path")
            or record.get("snapshot_sha256") != active.get("snapshot_sha256")
            or stage.get("package") != package
            or stage.get("version_key") != version_key
            or stage.get("policy_fingerprint") != active.get("policy_fingerprint")
            or (
                action == STAGE_DIRECTED
                and (
                    record.get("goal_artifact_path")
                    != active.get("goal_artifact_path")
                    or record.get("goal_artifact_sha256")
                    != active.get("goal_artifact_sha256")
                )
            )
        ):
            raise LoopError("offline_pending_active_boundary_lineage_invalid")
        snapshot_path = self._restore_observation_path(active.get("snapshot_path"))
        if (
            not snapshot_path.is_file()
            or snapshot_path.is_symlink()
            or not snapshot_path.is_relative_to(self.inventory_root)
            or _sha256(snapshot_path) != active.get("snapshot_sha256")
        ):
            raise LoopError("offline_pending_active_snapshot_invalid")
        snapshot = _json(snapshot_path, "offline_pending_active_snapshot_invalid")
        self._validate_snapshot(snapshot, snapshot_path)
        matches = [
            row
            for row in snapshot.get("included_apps", [])
            if isinstance(row, Mapping) and row.get("package") == package
        ]
        if (
            snapshot.get("snapshot_id") != active.get("snapshot_id")
            or len(matches) != 1
            or matches[0].get("version_key") != active.get("version_key")
            or _policy_fingerprint(matches[0]) != active.get("policy_fingerprint")
        ):
            raise LoopError("offline_pending_active_snapshot_lineage_invalid")
        active_work = self._validated_active_work({package: matches[0]})
        if (
            active_work is None
            or active_work.identity != identity
            or active_work.action != action
            or active_work.snapshot_path != snapshot_path
            or active_work.snapshot_sha256 != active.get("snapshot_sha256")
        ):
            raise LoopError("offline_pending_active_boundary_lineage_invalid")
        run_dir = self._restore_observation_path(record.get("run_directory"))
        if run_dir != self.observation_root / run_id:
            raise LoopError("offline_pending_active_run_lineage_invalid")
        return {
            "identity": identity,
            "active_task_canonical": _canonical_json(active),
            "active_stage_canonical": _canonical_json(stage),
            "run_dir": run_dir,
            "run_file_hashes": self._run_file_hashes(run_dir),
        }

    def _offline_guard_preserved(self, guard: Mapping[str, Any]) -> bool:
        """Re-read checkpoint and active evidence before making an audit claim."""

        previous_state = self._state
        try:
            if not self.checkpoint_path.is_file() or self.checkpoint_path.is_symlink():
                return False
            self._state = _validate_state(
                _json(self.checkpoint_path, "offline_pending_checkpoint_invalid")
            )
            current = self._offline_active_boundary_guard()
            return bool(
                current["identity"] == guard["identity"]
                and current["active_task_canonical"]
                == guard["active_task_canonical"]
                and current["active_stage_canonical"]
                == guard["active_stage_canonical"]
                and current["run_dir"] == guard["run_dir"]
                and current["run_file_hashes"] == guard["run_file_hashes"]
            )
        except (KeyError, LoopError, OSError):
            return False
        finally:
            self._state = previous_state

    def _select_offline_pending(self, active_identity: str) -> WorkItem | None:
        for priority_rank, identity in enumerate(sorted(self._state["stages"]), start=1):
            if identity == active_identity:
                continue
            stage = self._state["stages"][identity]
            discovery = stage.get(STAGE_DISCOVERY)
            candidates = stage.get("goal_candidates")
            if (
                not isinstance(discovery, Mapping)
                or (discovery.get("validation") or {}).get("status") != "passed"
                or (isinstance(candidates, Mapping) and candidates.get("status") == "passed")
                or stage.get("coverage_stage") != "goal_candidate_generation_pending"
                or coverage_stage(stage) != "goal_candidate_generation_pending"
                or any(
                    field in stage
                    for field in (
                        STAGE_DIRECTED,
                        "graph_coverage_validation",
                        "next_neutral_discovery_round",
                        "research_artifacts",
                    )
                )
            ):
                continue
            pinned = self._pinned_snapshot(stage)
            if pinned is None:
                raise LoopError("offline_pending_target_lineage_invalid")
            pinned_path, pinned_id, pinned_sha = pinned
            return self._work_from(
                "generate_goal_candidates",
                stage,
                priority_rank,
                pinned_path,
                pinned_id,
                pinned_sha,
            )
        return None

    def _offline_patch_allowed(
        self,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
        target_identity: str,
        artifact_path: Path,
        evidence: Mapping[str, Any],
    ) -> bool:
        previous = ObservationLoop._json_clone(before)
        current = ObservationLoop._json_clone(after)
        updated_at = current.get("updated_at")
        try:
            parsed_updated_at = datetime.fromisoformat(
                str(updated_at).replace("Z", "+00:00")
            )
        except ValueError:
            return False
        if not isinstance(updated_at, str) or not updated_at.endswith("Z") or parsed_updated_at.tzinfo is None:
            return False
        previous.pop("updated_at", None)
        current.pop("updated_at", None)
        previous_target = previous["stages"].pop(target_identity, None)
        current_target = current["stages"].pop(target_identity, None)
        if not isinstance(previous_target, Mapping) or not isinstance(current_target, Mapping):
            return False
        previous_counters = previous.pop("counters", None)
        current_counters = current.pop("counters", None)
        if not isinstance(previous_counters, Mapping) or not isinstance(current_counters, Mapping):
            return False
        previous_goal_passes = int(previous_counters.get("goal_candidate_passes", -1))
        current_goal_passes = int(current_counters.get("goal_candidate_passes", -1))
        previous_counters = dict(previous_counters)
        current_counters = dict(current_counters)
        previous_counters.pop("goal_candidate_passes", None)
        current_counters.pop("goal_candidate_passes", None)
        allowed_target_fields = {
            "goal_candidates",
            "coverage_stage",
            "next_neutral_discovery_round",
            "graph_coverage_validation",
        }
        previous_target = dict(previous_target)
        current_target = dict(current_target)
        previous_candidates = previous_target.get("goal_candidates")
        expected_goal_candidates = {
            "status": "passed",
            "path": self._store_observation_path(artifact_path),
            "sha256": evidence["artifact_sha256"],
            "source_run_id": evidence["source_run_id"],
            "source_snapshot_id": evidence["source_snapshot_id"],
            "goal_candidate_policy": _goal_candidate_policy(),
            "evidence": dict(evidence),
        }
        try:
            current_artifact_sha = _sha256(artifact_path)
        except OSError:
            return False
        if (
            previous_target.get("coverage_stage") != "goal_candidate_generation_pending"
            or coverage_stage(previous_target) != "goal_candidate_generation_pending"
            or (isinstance(previous_candidates, Mapping) and previous_candidates.get("status") == "passed")
            or current_target.get("goal_candidates") != expected_goal_candidates
            or current_artifact_sha != evidence.get("artifact_sha256")
            or current_target.get("coverage_stage") != coverage_stage(current_target)
        ):
            return False
        if int(evidence.get("applicable", 0)) == 0:
            expected_graph = {
                "status": "pending_more_neutral_evidence",
                "reason_code": "no_applicable_candidate",
                "applicability_evidence": {
                    key: int(evidence.get(key, 0))
                    for key in ("not_applicable", "authentication_boundary", "unverified")
                },
                "canonical_promotion_allowed": False,
            }
            if (
                current_target.get("coverage_stage") != "neutral_rediscovery_scheduled"
                or current_target.get("next_neutral_discovery_round")
                != int(before["next_round"]) + self.refresh_rounds_without_applicable
                or current_target.get("graph_coverage_validation") != expected_graph
            ):
                return False
        elif (
            current_target.get("coverage_stage") != "goal_directed_exploration_pending"
            or "next_neutral_discovery_round" in current_target
            or "graph_coverage_validation" in current_target
        ):
            return False
        for field in allowed_target_fields:
            previous_target.pop(field, None)
            current_target.pop(field, None)
        return bool(
            previous == current
            and previous_counters == current_counters
            and current_goal_passes == previous_goal_passes + 1
            and previous_target == current_target
        )

    def _offline_audit(
        self,
        event_type: str,
        started: float,
        *,
        identity: str | None,
        outcome: str,
        active_task_preserved: bool,
        **fields: Any,
    ) -> None:
        self._event(
            event_type,
            execution_mode="offline_pending",
            version_identity=identity,
            outcome=outcome,
            active_task_preserved=active_task_preserved,
            **fields,
        )
        self._metric(
            outcome,
            started,
            identity,
            execution_mode="offline_pending",
            active_task_preserved=active_task_preserved,
            device_command_count=0,
            collector_command_count=0,
            **fields,
        )

    def drain_offline_pending(self) -> LoopOutcome:
        with _ProcessLock(self.state_root / "observation-loop.lock"):
            self._state = self._load_state()
            return self._drain_offline_pending_locked()

    def _drain_offline_pending_locked(self) -> LoopOutcome:
        """Advance at most one non-active, validated goal-candidate stage offline."""

        started = time.monotonic()
        guard = self._offline_active_boundary_guard()
        base_state = self._json_clone(self._state)
        if (
            not self.checkpoint_path.is_file()
            or self.checkpoint_path.is_symlink()
        ):
            raise LoopError("offline_pending_checkpoint_invalid")
        checkpoint_sha = _sha256(self.checkpoint_path)
        item = self._select_offline_pending(str(guard["identity"]))
        if item is None:
            active_preserved = self._offline_guard_preserved(guard)
            if not active_preserved or _sha256(self.checkpoint_path) != checkpoint_sha:
                self._offline_audit(
                    "offline_pending_guard_failed",
                    started,
                    identity=None,
                    outcome="offline_pending_active_guard_changed",
                    active_task_preserved=active_preserved,
                    checkpoint_sha256=checkpoint_sha,
                )
                raise LoopError("offline_pending_active_guard_changed")
            self._offline_audit(
                "offline_pending_noop",
                started,
                identity=None,
                outcome="offline_pending_empty",
                active_task_preserved=True,
                checkpoint_sha256=checkpoint_sha,
            )
            return LoopOutcome("offline_pending_empty", 0)
        selected_preserved = self._offline_guard_preserved(guard)
        if not selected_preserved or _sha256(self.checkpoint_path) != checkpoint_sha:
            raise LoopError("offline_pending_active_guard_changed")
        self._offline_audit(
            "offline_pending_selected",
            started,
            identity=item.identity,
            outcome="offline_pending_selected",
            active_task_preserved=selected_preserved,
            action=item.action,
            checkpoint_sha256=checkpoint_sha,
        )
        try:
            artifact_path, evidence, _return_code = self._prepare_goal_candidates(item)
        except LoopError as error:
            self._state = base_state
            self._offline_audit(
                "offline_pending_failed",
                started,
                identity=item.identity,
                outcome="offline_pending_lineage_rejected",
                active_task_preserved=self._offline_guard_preserved(guard),
                action=item.action,
                error_code=str(error).split(":", 1)[0],
                checkpoint_sha256=checkpoint_sha,
            )
            raise
        if evidence is None:
            self._state = base_state
            self._offline_audit(
                "offline_pending_failed",
                started,
                identity=item.identity,
                outcome="offline_pending_generation_failed",
                active_task_preserved=self._offline_guard_preserved(guard),
                action=item.action,
                checkpoint_sha256=checkpoint_sha,
            )
            raise LoopError("offline_pending_generation_failed")
        if _sha256(self.checkpoint_path) != checkpoint_sha:
            self._state = base_state
            self._offline_audit(
                "offline_pending_cas_conflict",
                started,
                identity=item.identity,
                outcome="offline_pending_checkpoint_conflict",
                active_task_preserved=self._offline_guard_preserved(guard),
                action=item.action,
                checkpoint_sha256=checkpoint_sha,
            )
            raise LoopError("offline_pending_checkpoint_conflict")
        self._state = self._json_clone(base_state)
        try:
            offline_outcome = self._apply_goal_candidates(
                item, artifact_path, evidence
            )
        except LoopError as error:
            self._state = base_state
            self._offline_audit(
                "offline_pending_failed",
                started,
                identity=item.identity,
                outcome="offline_pending_artifact_rejected",
                active_task_preserved=self._offline_guard_preserved(guard),
                action=item.action,
                error_code=str(error).split(":", 1)[0],
                checkpoint_sha256=checkpoint_sha,
            )
            raise
        self._state["updated_at"] = _iso(self.clock)
        active_preserved = self._offline_guard_preserved(guard)
        if (
            not self._offline_patch_allowed(
                base_state,
                self._state,
                item.identity,
                artifact_path,
                evidence,
            )
            or not active_preserved
            or _sha256(self.checkpoint_path) != checkpoint_sha
        ):
            self._state = base_state
            self._offline_audit(
                "offline_pending_guard_failed",
                started,
                identity=item.identity,
                outcome="offline_pending_patch_rejected",
                active_task_preserved=active_preserved,
                action=item.action,
                checkpoint_sha256=checkpoint_sha,
            )
            raise LoopError("offline_pending_patch_rejected")
        try:
            _atomic_json(self.checkpoint_path, self._state)
        except (OSError, LoopError) as error:
            self._state = base_state
            self._offline_audit(
                "offline_pending_failed",
                started,
                identity=item.identity,
                outcome="offline_pending_checkpoint_write_failed",
                active_task_preserved=self._offline_guard_preserved(guard),
                action=item.action,
                error_code=type(error).__name__,
                checkpoint_sha256=checkpoint_sha,
            )
            raise
        applied_checkpoint_sha = _sha256(self.checkpoint_path)
        active_preserved = self._offline_guard_preserved(guard)
        if not active_preserved:
            self._offline_audit(
                "offline_pending_guard_failed",
                started,
                identity=item.identity,
                outcome="offline_pending_active_guard_changed_after_write",
                active_task_preserved=False,
                action=item.action,
                checkpoint_sha256=applied_checkpoint_sha,
                previous_checkpoint_sha256=checkpoint_sha,
            )
            raise LoopError("offline_pending_active_guard_changed_after_write")
        self._record_goal_candidate_success(item, evidence)
        self._offline_audit(
            "offline_pending_applied",
            started,
            identity=item.identity,
            outcome="offline_pending_applied",
            active_task_preserved=active_preserved,
            action=item.action,
            offline_outcome=offline_outcome,
            checkpoint_sha256=applied_checkpoint_sha,
            previous_checkpoint_sha256=checkpoint_sha,
        )
        return LoopOutcome(
            "offline_pending_applied",
            0,
            selected_identity=item.identity,
        )

    def _finish_round(self, outcome: str, started: float, identity: str | None) -> None:
        self._state["counters"]["rounds"] += 1
        self._metric(outcome, started, identity)
        self._state["next_round"] += 1
        self._save(outcome)

    def run(self, *, once: bool = False, max_rounds: int = 0) -> LoopOutcome:
        with _ProcessLock(self.state_root / "observation-loop.lock"):
            self._state = self._load_state()
            return self._run_locked(once=once, max_rounds=max_rounds)

    def _run_locked(self, *, once: bool = False, max_rounds: int = 0) -> LoopOutcome:
        if max_rounds < 0 or (once and max_rounds not in {0, 1}):
            raise LoopError("invalid_round_limit")
        limit = 1 if once else max_rounds
        completed = 0
        self._start_keepalive()
        try:
            while True:
                if self.stop_requested():
                    self._save("stopped_by_user")
                    return LoopOutcome("stopped_by_user", completed)
                if limit and completed >= limit:
                    return LoopOutcome("bounded_run_complete", completed)
                self._check_keepalive()
                started = time.monotonic()
                identity: str | None = None
                try:
                    self._save("discovering_inventory")
                    snapshot, snapshot_path = self._discover()
                    self._state["last_inventory"] = {
                        "snapshot_id": snapshot["snapshot_id"],
                        "path": self._store_observation_path(snapshot_path),
                        "sha256": _sha256(snapshot_path),
                        "included_app_count": len(snapshot["included_apps"]),
                    }
                    item = self._select(snapshot, snapshot_path)
                    if item is None:
                        outcome = "waiting_for_scheduled_neutral_discovery"
                    else:
                        identity = item.identity
                        self._event("work_selected", version_identity=identity, action=item.action, priority_rank=item.priority_rank, snapshot_id=item.snapshot_id)
                        if item.action in COLLECTION_STAGES:
                            outcome, boundary = self._collect(item)
                            if boundary:
                                self._metric("user_action_boundary", started, identity, stage=item.action)
                                return LoopOutcome("user_action_boundary", completed, _boundary_sentence(boundary), identity)
                        elif item.action == "generate_goal_candidates":
                            outcome = self._generate_candidates(item)
                        elif item.action == "build_research_artifacts":
                            outcome = self._build_research(item)
                        else:
                            raise LoopError("work_action_invalid")
                    self._finish_round(outcome, started, identity)
                    completed += 1
                    if limit and completed >= limit:
                        return LoopOutcome(outcome, completed, selected_identity=identity)
                    if item is None:
                        self._sleep()
                except KeyboardInterrupt:
                    self._save("stopped_by_user")
                    return LoopOutcome("stopped_by_user", completed, selected_identity=identity)
                except LoopError as error:
                    code = str(error).split(":", 1)[0]
                    if code not in {"collector_failed", "collector_stopped", "collection_validation_failed", "collector_terminal_status_invalid", "directed_candidate_coverage_incomplete", "goal_candidate_generation_or_lineage_failed", "research_artifact_build_failed", "active_task_lineage_mismatch", "validated_collection_adoption_invalid"}:
                        self._failure("orchestrator", code, identity)
                    self._finish_round("round_failed", started, identity)
                    completed += 1
                    if limit and completed >= limit:
                        return LoopOutcome("round_failed", completed, selected_identity=identity)
                    self._sleep()
        finally:
            self._stop_keepalive()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default=EXPECTED_SERIAL)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--observation-root", type=Path, default=DEFAULT_OBSERVATION_ROOT)
    parser.add_argument("--inventory-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--family-manifest", type=Path, default=FAMILY_MANIFEST)
    execution_mode = parser.add_mutually_exclusive_group()
    execution_mode.add_argument("--once", action="store_true")
    execution_mode.add_argument(
        "--drain-offline-pending",
        action="store_true",
        help="advance at most one validated non-active goal-candidate stage without device access",
    )
    parser.add_argument("--max-rounds", type=int, default=0, help="0 runs persistently until user stop")
    parser.add_argument("--poll-seconds", type=float, default=120.0)
    parser.add_argument("--command-timeout-seconds", type=float, default=600.0)
    parser.add_argument("--refresh-rounds-without-applicable", type=int, default=10)
    parser.add_argument("--build-research-artifacts", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.drain_offline_pending and args.max_rounds != 0:
            raise LoopError("offline_pending_round_limit_forbidden")
        observation_root = args.observation_root.resolve()
        loop = ObservationLoop(
            repo_root=args.repo_root,
            observation_root=observation_root,
            inventory_root=args.inventory_root or observation_root / "device-inventory",
            state_root=args.state_root or observation_root / "observation-loop",
            serial=args.serial,
            python_executable=args.python,
            adb_executable=args.adb,
            api_base_url=args.api_base_url,
            family_manifest=args.family_manifest,
            build_research_artifacts=args.build_research_artifacts,
            refresh_rounds_without_applicable=args.refresh_rounds_without_applicable,
            command_timeout_seconds=args.command_timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        outcome = (
            loop.drain_offline_pending()
            if args.drain_offline_pending
            else loop.run(once=args.once, max_rounds=args.max_rounds)
        )
    except LoopError as error:
        print(json.dumps({"ok": False, "error_code": str(error).split(":", 1)[0]}, ensure_ascii=False, sort_keys=True))
        return 2
    if outcome.boundary_sentence:
        print(outcome.boundary_sentence)
        return 3
    print(json.dumps({"ok": outcome.status != "round_failed", "status": outcome.status, "rounds_completed": outcome.rounds_completed, "selected_identity": outcome.selected_identity}, ensure_ascii=False, sort_keys=True))
    return 1 if outcome.status == "round_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
