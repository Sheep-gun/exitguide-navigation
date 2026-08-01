from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "Run-RealDeviceObservationLoop.py"
SPEC = importlib.util.spec_from_file_location("egl_real_device_observation_loop", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
loop_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = loop_module
SPEC.loader.exec_module(loop_module)

PACKAGE = "com.netflix.mediaclient"
VERSION_KEY = "code:123|name:1.2.3"
IDENTITY = f"{PACKAGE}@{VERSION_KEY}"
NEXT_PACKAGE = "com.google.android.youtube"
NEXT_VERSION_KEY = "code:456|name:4.5.6"
NEXT_IDENTITY = f"{NEXT_PACKAGE}@{NEXT_VERSION_KEY}"
BAEMIN_PACKAGE = "com.sampleapp"
BAEMIN_VERSION_KEY = "code:789|name:7.8.9"
BAEMIN_IDENTITY = f"{BAEMIN_PACKAGE}@{BAEMIN_VERSION_KEY}"
NEW_PACKAGE = "com.example.newapp"
NEW_VERSION_KEY = "code:999|name:9.9.9"
NEW_IDENTITY = f"{NEW_PACKAGE}@{NEW_VERSION_KEY}"
FAMILY_MANIFEST = REPO_ROOT / "fixtures" / "navigation" / "real-device-observation-apps.v1.json"


class StepClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 31, 1, 2, 3, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(milliseconds=1)
        return current


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _script_name(command: Sequence[str]) -> str | None:
    if command and command[0] == "adb":
        return None
    return Path(command[1]).name if len(command) > 1 else None


class FakePipelineRunner:
    """Filesystem-real fake for the staged collector/generator contract."""

    def __init__(
        self,
        *,
        applicability_batches: Sequence[Sequence[str]] = (("applicable",),),
        boundary_once_stages: Iterable[str] = (),
        discovery_terminal: str = "discovery_budget_complete",
        readiness_failure: str | None = None,
        corrupt_directed_lineage: bool = False,
        crash_before_collect_stage: str | None = None,
        include_next_app: bool = False,
        include_scheduler_apps: bool = False,
        boundary_code: str = "password_boundary",
    ) -> None:
        self.applicability_batches = [tuple(batch) for batch in applicability_batches]
        self.boundary_once_stages = set(boundary_once_stages)
        self.discovery_terminal = discovery_terminal
        self.readiness_failure = readiness_failure
        self.corrupt_directed_lineage = corrupt_directed_lineage
        self.crash_before_collect_stage = crash_before_collect_stage
        self.include_next_app = include_next_app
        self.include_scheduler_apps = include_scheduler_apps
        self.boundary_code = boundary_code
        self.commands: list[tuple[str, ...]] = []
        self.discovery_count = 0
        self.generator_count = 0
        self.builder_count = 0
        self.boundary_emitted: set[str] = set()
        self.on_generate: Callable[[], None] | None = None

    @staticmethod
    def _arg(command: Sequence[str], name: str) -> str:
        index = list(command).index(name)
        return str(command[index + 1])

    @staticmethod
    def _stage(command: Sequence[str]) -> str:
        if "--capture-only" in command:
            return loop_module.STAGE_INITIAL
        if "--discovery-explore" in command:
            return loop_module.STAGE_DISCOVERY
        if "--goal-candidates" in command:
            return loop_module.STAGE_DIRECTED
        raise AssertionError(f"collector mode missing: {command}")

    def __call__(self, command, *, cwd, timeout_seconds):
        assert Path(cwd).resolve() == REPO_ROOT.resolve()
        assert timeout_seconds > 0
        values = tuple(str(item) for item in command)
        self.commands.append(values)
        if values[0] == "adb":
            return self._adb(values)
        script = Path(values[1]).name
        if script == loop_module.DISCOVERY_SCRIPT:
            return self._discover(values)
        if script == loop_module.COLLECTOR_SCRIPT:
            return self._collect(values)
        if script == loop_module.VALIDATOR_SCRIPT:
            return self._validate(values)
        if script == loop_module.GOAL_GENERATOR_SCRIPT:
            return self._generate(values)
        if script == loop_module.ARTIFACT_BUILDER_SCRIPT:
            return self._build(values)
        raise AssertionError(f"unexpected pipeline command: {values}")

    @staticmethod
    def _adb(command: Sequence[str]):
        assert tuple(command[:3]) == ("adb", "-s", loop_module.EXPECTED_SERIAL)
        suffix = tuple(command[3:])
        if suffix == ("get-state",):
            output = "device\n"
        elif suffix == ("shell", "getprop", "ro.serialno"):
            output = f"{loop_module.EXPECTED_SERIAL}\n"
        elif suffix == ("shell", "getprop", "ro.kernel.qemu"):
            output = "0\n"
        elif suffix in {
            ("shell", "svc", "power", "stayon", "usb"),
            ("shell", "input", "keyevent", "KEYCODE_WAKEUP"),
        }:
            output = ""
        else:
            raise AssertionError(f"non-keepalive adb command: {command}")
        return loop_module.CommandResult(0, output)

    def _discover(self, command: Sequence[str]):
        self.discovery_count += 1
        output_root = Path(self._arg(command, "--output-root"))
        output_root.mkdir(parents=True, exist_ok=True)
        snapshot_id = f"20260731T0102{self.discovery_count:02d}000Z-a244f3c98a"
        snapshot_path = output_root / f"inventory-{snapshot_id}.json"
        app = {
            "package": PACKAGE,
            "version_name": "1.2.3",
            "version_code": "123",
            "version_key": VERSION_KEY,
            "included": True,
            "observation_status": "unobserved_current_version",
            "change_status": "unchanged",
            "sensitivity_categories": [],
            "sensitivity_handling": "standard_metadata_only",
        }
        included_apps = [app]
        prioritized_apps = [
            {
                "package": PACKAGE,
                "version_key": VERSION_KEY,
                "priority_rank": 1,
            }
        ]
        if self.include_next_app:
            included_apps.append(
                {
                    **app,
                    "package": NEXT_PACKAGE,
                    "version_name": "4.5.6",
                    "version_code": "456",
                    "version_key": NEXT_VERSION_KEY,
                }
            )
            prioritized_apps.append(
                {
                    "package": NEXT_PACKAGE,
                    "version_key": NEXT_VERSION_KEY,
                    "priority_rank": 2,
                }
            )
        if self.include_scheduler_apps:
            def app_record(package: str, version_name: str, version_code: str, version_key: str):
                return {
                    **app,
                    "package": package,
                    "version_name": version_name,
                    "version_code": version_code,
                    "version_key": version_key,
                }

            included_apps = [
                app_record(NEW_PACKAGE, "9.9.9", "999", NEW_VERSION_KEY),
                app,
                app_record(BAEMIN_PACKAGE, "7.8.9", "789", BAEMIN_VERSION_KEY),
            ]
            prioritized_apps = [
                {"package": NEW_PACKAGE, "version_key": NEW_VERSION_KEY, "priority_rank": 1},
                {"package": PACKAGE, "version_key": VERSION_KEY, "priority_rank": 2},
                {"package": BAEMIN_PACKAGE, "version_key": BAEMIN_VERSION_KEY, "priority_rank": 3},
            ]
        snapshot = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "provenance": loop_module.PROVENANCE,
            "dataset_role": loop_module.PROVENANCE,
            "review_status": loop_module.REVIEW_STATUS,
            "route_lifecycle": loop_module.ROUTE_LIFECYCLE,
            "canonical_catalog_mutation": False,
            "canonical_catalog": {"version": loop_module.CANONICAL_VERSION},
            "device": {
                "serial": loop_module.EXPECTED_SERIAL,
                "is_emulator": False,
                "device_type": "physical_android",
            },
            "included_apps": included_apps,
            "prioritized_apps": prioritized_apps,
        }
        _write_json(snapshot_path, snapshot)
        return loop_module.CommandResult(
            0,
            json.dumps({"snapshot_id": snapshot_id, "path": str(snapshot_path)}),
        )

    def _collect(self, command: Sequence[str]):
        stage = self._stage(command)
        crash_key = f"crash:{stage}"
        if (
            self.crash_before_collect_stage == stage
            and crash_key not in self.boundary_emitted
        ):
            self.boundary_emitted.add(crash_key)
            raise OSError("simulated process launch interruption")
        run_id = self._arg(command, "--run-id")
        observation_root = Path(self._arg(command, "--output-root"))
        run_dir = observation_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = Path(self._arg(command, "--inventory-snapshot"))
        snapshot = _read_json(snapshot_path)
        selected_package = self._arg(command, "--only-package")
        selected_apps = [
            app
            for app in snapshot["included_apps"]
            if app["package"] == selected_package
        ]
        assert len(selected_apps) == 1
        selected_app = selected_apps[0]
        selected_version_key = str(selected_app["version_key"])
        goal_artifact_path = (
            Path(self._arg(command, "--goal-candidates"))
            if stage == loop_module.STAGE_DIRECTED
            else None
        )
        applicable_ids: list[str] = []
        if goal_artifact_path is not None:
            artifact = _read_json(goal_artifact_path)
            applicable_ids = [
                str(candidate["candidate_id"])
                for candidate in artifact["apps"][0]["goal_candidates"]
                if candidate["applicability_state"] == "applicable"
            ]

        accessibility_enabled = self.readiness_failure != "accessibility"
        overlay_appop = "deny" if self.readiness_failure == "overlay" else "allow"
        provider_ready = self.readiness_failure != "api"
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "run_id": run_id,
            "provenance": loop_module.PROVENANCE,
            "dataset_role": loop_module.PROVENANCE,
            "review_status": loop_module.REVIEW_STATUS,
            "route_lifecycle": loop_module.ROUTE_LIFECYCLE,
            "device_serial": loop_module.EXPECTED_SERIAL,
            "is_emulator": False,
            "validation_profile": "dynamic_inventory",
            "collection_mode": "capture_only" if stage == loop_module.STAGE_INITIAL else "safe_explore",
            "exploration_stage": stage,
            "status": "completed",
            "raw_artifacts_persisted": False,
            "canonical_catalog_version": loop_module.CANONICAL_VERSION,
            "canonical_mutation_allowed": False,
            "selected_packages": [selected_package],
            "safety": {
                "unsafe_auto_click_count": 0,
                "final_action_auto_click_count": 0,
            },
            "runtime_attestation": {
                "device": {
                    "serial": loop_module.EXPECTED_SERIAL,
                    "is_emulator": False,
                },
                "exitguide": {
                    "package": "com.exitguide.ai",
                    "installed_for_user_0": True,
                    "accessibility_component": "com.exitguide.ai/com.exitguide.ai.overlay.ExitGuideAccessibilityService",
                    "accessibility_enabled": accessibility_enabled,
                    "overlay_appop": overlay_appop,
                },
                "api": {
                    "status": "ok" if provider_ready else "unavailable",
                    "llm_provider": "exaone",
                    "provider_ready": provider_ready,
                },
            },
            "inventory_snapshot": {
                "snapshot_id": snapshot["snapshot_id"],
                "path": snapshot_path.relative_to(observation_root).as_posix(),
                "path_scope": "observation_root_relative",
                "explicit_safe_file": False,
                "sha256": _sha256(snapshot_path),
                "selected_tasks": [],
            },
        }
        if stage == loop_module.STAGE_DIRECTED:
            assert goal_artifact_path is not None
            family_path = Path(self._arg(command, "--family-manifest"))
            goal_artifact = _read_json(goal_artifact_path)
            selection = [
                {
                    "task_id": f"task-{candidate_id}",
                    "app_package": selected_package,
                    "version_key": selected_version_key,
                    "candidate_id": candidate_id,
                    "family_id": "subscription_manage",
                    "terminal_policy": "navigation_only",
                    "source_run_id": goal_artifact["source_run_id"],
                    "source_inventory_snapshot_id": goal_artifact[
                        "source_inventory_snapshot_id"
                    ],
                    "confidence": 1.0,
                    "candidate_rank": 1,
                    "source_artifact_sha256": _sha256(goal_artifact_path),
                }
                for candidate_id in applicable_ids
            ]
            goal_plan = {
                "artifact": {
                    "path": goal_artifact_path.relative_to(observation_root).as_posix(),
                    "path_scope": "observation_root_relative",
                    "explicit_safe_file": False,
                    "sha256": _sha256(goal_artifact_path),
                },
                "family_manifest": {
                    "path": family_path.relative_to(REPO_ROOT).as_posix(),
                    "path_scope": "repo_relative",
                    "explicit_safe_file": False,
                    "sha256": _sha256(family_path),
                },
                "source_run_id": goal_artifact["source_run_id"],
                "source_inventory_snapshot_id": goal_artifact[
                    "source_inventory_snapshot_id"
                ],
                "state_counts": goal_artifact["counts"]["applicability_states"],
                "selected_candidate_count": len(applicable_ids),
                "selected_candidate_ids": applicable_ids,
                "selection_sha256": "0" * 64,
                "selection": selection,
            }
            if self.corrupt_directed_lineage:
                goal_plan["artifact"]["sha256"] = "f" * 64
            manifest["goal_candidate_plan"] = goal_plan
            manifest["inventory_snapshot"]["goal_candidate_plan"] = goal_plan
        if stage == loop_module.STAGE_INITIAL:
            tasks = [
                {
                    "task_id": f"task-capture-{selected_package}",
                    "app_package": selected_package,
                    "version_key": selected_version_key,
                }
            ]
        elif stage == loop_module.STAGE_DISCOVERY:
            tasks = [
                {
                    "task_id": f"task-discovery-{selected_package}",
                    "app_package": selected_package,
                    "version_key": selected_version_key,
                }
            ]
        else:
            tasks = selection
        manifest["tasks"] = tasks
        manifest["inventory_snapshot"]["selected_tasks"] = tasks

        if stage in self.boundary_once_stages and stage not in self.boundary_emitted:
            self.boundary_emitted.add(stage)
            status = "incomplete"
            statuses = {tasks[0]["task_id"]: f"boundary:{self.boundary_code}"}
        elif stage == loop_module.STAGE_INITIAL:
            status = "completed"
            statuses = {tasks[0]["task_id"]: "captured"}
        elif stage == loop_module.STAGE_DISCOVERY:
            status = "completed"
            statuses = {tasks[0]["task_id"]: self.discovery_terminal}
        else:
            assert applicable_ids
            status = "completed"
            statuses = {
                str(task["task_id"]): "destination_reached" for task in tasks
            }
        manifest["status"] = status
        _write_json(run_dir / "manifest.json", manifest)
        (run_dir / "screens.jsonl").write_text("", encoding="utf-8")
        (run_dir / "observations.jsonl").write_text("", encoding="utf-8")
        _write_json(
            run_dir / "checkpoint.json",
            {
                "run_id": run_id,
                "status": status,
                "exploration_stage": stage,
                "state": {
                    "completed_task_ids": sorted(statuses) if status == "completed" else [],
                    "current_task_id": None if status == "completed" else tasks[0]["task_id"],
                    "current_task": None if status == "completed" else tasks[0],
                    "statuses": statuses,
                    "task_attempt_numbers": {
                        str(task["task_id"]): 1 for task in tasks
                    },
                },
            },
        )
        (run_dir / "corpus.sqlite").write_bytes(f"corpus:{run_id}".encode())
        (run_dir / "graph-candidate.sqlite").write_bytes(f"graph:{run_id}".encode())

        if stage == loop_module.STAGE_DIRECTED:
            rows = [
                {
                    "metric_dimension": "task_summary",
                    "goal_candidate_id": candidate_id,
                    "terminal_status": "destination_reached",
                    "candidate_destination_found": True,
                    "unsafe_auto_click_count": 0,
                    "final_action_auto_click_count": 0,
                }
                for candidate_id in applicable_ids
            ]
            (run_dir / "metrics.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
        else:
            (run_dir / "metrics.jsonl").write_text("", encoding="utf-8")

        return loop_module.CommandResult(
            0,
            json.dumps(
                {
                    "run_id": run_id,
                    "run_directory": str(run_dir),
                    "status": status,
                    "statuses": statuses,
                }
            ),
        )

    def _validate(self, command: Sequence[str]):
        run_dir = Path(self._arg(command, "--run-dir"))
        manifest_path = run_dir / "manifest.json"
        screens_path = run_dir / "screens.jsonl"
        manifest = _read_json(manifest_path)
        marker = {
            "schema_version": 1,
            "status": "passed",
            "validator": loop_module.VALIDATOR_SCRIPT,
            "run_id": manifest["run_id"],
            "provenance": loop_module.PROVENANCE,
            "device_serial": loop_module.EXPECTED_SERIAL,
            "is_emulator": False,
            "manifest_sha256": _sha256(manifest_path),
            "screens_sha256": _sha256(screens_path),
            "core_artifact_sha256": {
                name: _sha256(run_dir / name)
                for name in loop_module.VALIDATION_CORE_ARTIFACTS
            },
        }
        _write_json(run_dir / loop_module.VALIDATED, marker)
        return loop_module.CommandResult(0, json.dumps({"ok": True}))

    def _generate(self, command: Sequence[str]):
        run_dir = Path(self._arg(command, "--run-dir"))
        snapshot_path = Path(self._arg(command, "--inventory-snapshot"))
        family_path = Path(self._arg(command, "--family-manifest"))
        manifest = _read_json(run_dir / "manifest.json")
        selected_packages = manifest["selected_packages"]
        assert isinstance(selected_packages, list) and len(selected_packages) == 1
        selected_package = str(selected_packages[0])
        batch_index = min(self.generator_count, len(self.applicability_batches) - 1)
        states = self.applicability_batches[batch_index]
        self.generator_count += 1
        candidates = [
            {
                "candidate_id": f"goal-candidate-{index:03d}",
                "family_id": "subscription_manage" if index == 1 else f"generic_family_{index}",
                "applicability_state": state,
                "final_action_auto_click_allowed": False,
                "unsafe_action_auto_click_allowed": False,
            }
            for index, state in enumerate(states, start=1)
        ]
        counts_by_state = {
            state: sum(1 for value in states if value == state)
            for state in loop_module.GOAL_STATES
            if any(value == state for value in states)
        }
        artifact = {
            "schema_version": 1,
            "artifact_type": "dynamic_real_device_goal_candidates",
            "source_run_id": manifest["run_id"],
            "source_inventory_snapshot_id": manifest["inventory_snapshot"]["snapshot_id"],
            "provenance": loop_module.PROVENANCE,
            "dataset_role": loop_module.PROVENANCE,
            "review_status": loop_module.REVIEW_STATUS,
            "route_lifecycle": loop_module.ROUTE_LIFECYCLE,
            "serving_allowed": False,
            "human_review_required": True,
            "goal_candidate_policy": loop_module._goal_candidate_policy(),
            "canonical_catalog": {
                "version": loop_module.CANONICAL_VERSION,
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
                "goal_candidate_policy_version": loop_module.GOAL_CANDIDATE_POLICY_VERSION,
                "goal_candidate_policy_sha256": loop_module.GOAL_CANDIDATE_POLICY_SHA256,
            },
            "source_sha256": {
                "manifest": _sha256(run_dir / "manifest.json"),
                "checkpoint": _sha256(run_dir / "checkpoint.json"),
                "corpus": _sha256(run_dir / "corpus.sqlite"),
                "graph": _sha256(run_dir / "graph-candidate.sqlite"),
                "snapshot": _sha256(snapshot_path),
                "family_manifest": _sha256(family_path),
            },
            "apps": [
                {
                    "app_package": selected_package,
                    "goal_candidate_policy": loop_module._goal_candidate_policy(),
                    "goal_candidates": candidates,
                }
            ],
            "counts": {
                "selected_app_count": 1,
                "candidate_count": len(candidates),
                "applicability_states": counts_by_state,
            },
        }
        artifact_path = (
            Path(self._arg(command, "--output"))
            if "--output" in command
            else run_dir / loop_module.GOAL_ARTIFACT
        )
        _write_json(artifact_path, artifact)
        if self.on_generate is not None:
            self.on_generate()
        return loop_module.CommandResult(
            0,
            json.dumps(
                {
                    "ok": True,
                    "candidate_count": len(candidates),
                    "output_path": str(artifact_path),
                }
            ),
        )

    def _build(self, command: Sequence[str]):
        self.builder_count += 1
        run_dir = Path(self._arg(command, "--run-dir"))
        manifest = _read_json(run_dir / "manifest.json")
        for name in loop_module.RESEARCH_ARTIFACTS:
            path = run_dir / name
            if name == "navigation-report.json":
                _write_json(
                    path,
                    {
                        "source_run_id": manifest["run_id"],
                        "provenance": loop_module.PROVENANCE,
                        "route_lifecycle": loop_module.ROUTE_LIFECYCLE,
                    },
                )
            elif path.suffix == ".jsonl":
                path.write_text("", encoding="utf-8")
            else:
                _write_json(path, {})
        return loop_module.CommandResult(0, json.dumps({"ok": True}))


def _make_loop(root: Path, runner: FakePipelineRunner, **kwargs: Any):
    observation_root = root / "observations"
    return loop_module.ObservationLoop(
        repo_root=REPO_ROOT,
        observation_root=observation_root,
        inventory_root=observation_root / "device-inventory",
        state_root=observation_root / "observation-loop",
        serial=loop_module.EXPECTED_SERIAL,
        python_executable=sys.executable,
        adb_executable="adb",
        runner=runner,
        clock=StepClock(),
        sleeper=lambda _seconds: None,
        poll_seconds=0,
        emit_heartbeats=False,
        **kwargs,
    )


def _run_once(root: Path, runner: FakePipelineRunner, **kwargs: Any):
    loop = _make_loop(root, runner, **kwargs)
    return loop, loop.run(once=True)


def _checkpoint(loop) -> dict[str, Any]:
    return _read_json(loop.checkpoint_path)


def _stage(loop) -> dict[str, Any]:
    checkpoint = _checkpoint(loop)
    assert list(checkpoint["stages"]) == [IDENTITY]
    return checkpoint["stages"][IDENTITY]


def _pipeline_commands(runner: FakePipelineRunner, script: str) -> list[tuple[str, ...]]:
    return [command for command in runner.commands if _script_name(command) == script]


def _seed_validated_pending_app(
    loop,
    runner: FakePipelineRunner,
    *,
    snapshot_path: Path,
    package: str,
    priority_rank: int,
) -> str:
    """Prepare one app's validated discovery lineage without loop/device calls."""

    state = _checkpoint(loop)
    snapshot = _read_json(snapshot_path)
    matching = [
        app for app in snapshot["included_apps"] if app["package"] == package
    ]
    assert len(matching) == 1
    app = matching[0]
    version_key = str(app["version_key"])
    identity = loop_module.version_identity(package, version_key)
    snapshot_sha = _sha256(snapshot_path)
    next_stage: dict[str, Any] = {
        "package": package,
        "version_key": version_key,
        "version_name": app["version_name"],
        "version_code": app["version_code"],
        "policy_fingerprint": loop_module._policy_fingerprint(app),
        "sensitivity_categories": list(app["sensitivity_categories"]),
        "sensitivity_handling": app["sensitivity_handling"],
        "coverage_stage": "initial_capture_pending",
    }
    for action, run_id in (
        (loop_module.STAGE_INITIAL, f"seed-{priority_rank}-initial"),
        (loop_module.STAGE_DISCOVERY, f"seed-{priority_rank}-discovery"),
    ):
        item = loop._work_from(
            action,
            app,
            priority_rank,
            snapshot_path,
            str(snapshot["snapshot_id"]),
            snapshot_sha,
        )
        report = json.loads(
            runner._collect(loop._collection_command(item, run_id, False)).stdout
        )
        assert report["status"] == "completed"
        run_dir = Path(report["run_directory"])
        validation = runner._validate(
            (
                sys.executable,
                str(REPO_ROOT / "scripts" / loop_module.VALIDATOR_SCRIPT),
                "--run-dir",
                str(run_dir),
            )
        )
        assert validation.returncode == 0
        record = {
            "status": "passed",
            "run_id": run_id,
            "run_directory": loop._store_observation_path(run_dir),
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_path": loop._store_observation_path(snapshot_path),
            "snapshot_sha256": snapshot_sha,
            "attempts": 1,
            "terminal_statuses": sorted(str(value) for value in report["statuses"].values()),
            "validation": {
                "status": "passed",
                "marker_sha256": _sha256(run_dir / loop_module.VALIDATED),
                "manifest_sha256": _sha256(run_dir / "manifest.json"),
            },
        }
        next_stage[action] = record
        next_stage["coverage_stage"] = loop_module.coverage_stage(next_stage)
    next_stage["neutral_discovery_generation"] = 1
    assert next_stage["coverage_stage"] == "goal_candidate_generation_pending"
    state["stages"][identity] = next_stage
    state["counters"]["initial_capture_passes"] += 1
    state["counters"]["neutral_discovery_passes"] += 1
    _write_json(loop.checkpoint_path, state)
    return identity


def _seed_validated_pending_second_app(loop, runner: FakePipelineRunner) -> None:
    """Prepare YouTube's validated discovery lineage without loop/device calls."""

    state = _checkpoint(loop)
    active = state["active_task"]
    assert active["package"] == PACKAGE
    snapshot_path = Path(active["snapshot_path"])
    if not snapshot_path.is_absolute():
        snapshot_path = loop.observation_root / snapshot_path
    identity = _seed_validated_pending_app(
        loop,
        runner,
        snapshot_path=snapshot_path,
        package=NEXT_PACKAGE,
        priority_rank=2,
    )
    assert identity == NEXT_IDENTITY


def _advance_to_graph(root: Path, runner: FakePipelineRunner, **kwargs: Any):
    statuses = [
        "neutral_menu_discovery_pending",
        "goal_candidate_generation_pending",
        "goal_directed_exploration_pending",
        "graph_coverage_validated",
    ]
    loop = None
    for expected in statuses:
        loop, outcome = _run_once(root, runner, **kwargs)
        assert outcome.status == expected, (outcome, expected)
    assert loop is not None
    return loop


def assert_staged_pipeline_requires_all_validated_stages() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()

        first_loop, first = _run_once(root, runner)
        assert first.status == "neutral_menu_discovery_pending"
        first_stage = _stage(first_loop)
        assert first_stage["initial_capture"]["validation"]["status"] == "passed"
        assert first_stage["coverage_stage"] == "neutral_menu_discovery_pending"
        assert not loop_module.is_graph_coverage_validated(first_stage)
        assert "graph_coverage_validation" not in first_stage

        second_loop, second = _run_once(root, runner)
        assert second.status == "goal_candidate_generation_pending"
        assert _stage(second_loop)["neutral_menu_discovery"]["validation"]["status"] == "passed"

        third_loop, third = _run_once(root, runner)
        assert third.status == "goal_directed_exploration_pending"
        evidence = _stage(third_loop)["goal_candidates"]["evidence"]
        assert evidence["applicable"] == 1
        assert evidence["applicable_candidate_ids"] == ["goal-candidate-001"]

        fourth_loop, fourth = _run_once(root, runner)
        assert fourth.status == "graph_coverage_validated"
        stage = _stage(fourth_loop)
        assert stage["goal_directed_exploration"]["validation"]["status"] == "passed"
        assert stage["graph_coverage_validation"]["status"] == "passed"
        assert loop_module.is_graph_coverage_validated(stage)

        collectors = _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        assert len(collectors) == 3
        run_ids = [command[command.index("--run-id") + 1] for command in collectors]
        assert len(set(run_ids)) == 3
        assert "--capture-only" in collectors[0]
        assert "--discovery-explore" in collectors[1]
        assert "--goal-candidates" in collectors[2]
        assert collectors[2][collectors[2].index("--family-manifest") + 1] == str(FAMILY_MANIFEST)
        pinned_snapshots = [
            command[command.index("--inventory-snapshot") + 1]
            for command in collectors
        ]
        assert len(set(pinned_snapshots)) == 1
        for collector in collectors:
            index = runner.commands.index(collector)
            assert _script_name(runner.commands[index + 1]) == loop_module.VALIDATOR_SCRIPT

        directed_manifest = _read_json(
            root / "observations" / run_ids[2] / "manifest.json"
        )
        goal_path = Path(collectors[2][collectors[2].index("--goal-candidates") + 1])
        assert directed_manifest["goal_candidate_plan"]["artifact"]["sha256"] == _sha256(goal_path)
        assert directed_manifest["goal_candidate_plan"]["selected_candidate_ids"] == [
            "goal-candidate-001"
        ]


def assert_each_collection_stage_resumes_exact_lineage() -> None:
    prefixes = {
        loop_module.STAGE_INITIAL: 0,
        loop_module.STAGE_DISCOVERY: 1,
        loop_module.STAGE_DIRECTED: 3,
    }
    expected_after_resume = {
        loop_module.STAGE_INITIAL: "neutral_menu_discovery_pending",
        loop_module.STAGE_DISCOVERY: "goal_candidate_generation_pending",
        loop_module.STAGE_DIRECTED: "graph_coverage_validated",
    }
    for boundary_stage, prefix_rounds in prefixes.items():
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FakePipelineRunner(boundary_once_stages={boundary_stage})
            for _ in range(prefix_rounds):
                _run_once(root, runner)
            boundary_loop, boundary = _run_once(root, runner)
            assert boundary.status == "user_action_boundary"
            assert boundary.rounds_completed == 0
            assert boundary.selected_identity == IDENTITY
            assert boundary.boundary_sentence == "비밀번호를 직접 입력한 뒤 같은 작업을 다시 실행해 주세요."
            assert boundary.boundary_sentence.count(".") == 1
            assert any("가" <= character <= "힣" for character in boundary.boundary_sentence)
            active = _checkpoint(boundary_loop)["active_task"]
            assert active["stage"] == boundary_stage
            run_id = active["run_id"]
            snapshot_sha = active["snapshot_sha256"]
            artifact_sha = active.get("goal_artifact_sha256")

            resumed_loop, resumed = _run_once(root, runner)
            assert resumed.status == expected_after_resume[boundary_stage]
            collectors = _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
            resume_command = collectors[-1]
            assert "--resume" in resume_command
            assert resume_command[resume_command.index("--run-id") + 1] == run_id
            assert resume_command[resume_command.index("--only-package") + 1] == active["package"]
            assert resume_command[resume_command.index("--max-apps") + 1] == "1"
            assert _sha256(Path(resume_command[resume_command.index("--inventory-snapshot") + 1])) == snapshot_sha
            if boundary_stage == loop_module.STAGE_DIRECTED:
                goal_path = Path(resume_command[resume_command.index("--goal-candidates") + 1])
                assert _sha256(goal_path) == artifact_sha
            assert _checkpoint(resumed_loop)["active_task"] is None


def assert_initial_authentication_boundary_cannot_skip_to_next_app() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        assert boundary.boundary_sentence == (
            "로그인을 직접 완료한 뒤 같은 작업을 다시 실행해 주세요."
        )
        active = _checkpoint(boundary_loop)["active_task"]
        assert active["stage"] == loop_module.STAGE_INITIAL
        assert active["package"] == PACKAGE
        assert active["identity"] == IDENTITY
        run_id = active["run_id"]
        snapshot_path = Path(active["snapshot_path"])
        if not snapshot_path.is_absolute():
            snapshot_path = boundary_loop.observation_root / snapshot_path
        snapshot_sha = active["snapshot_sha256"]
        assert _sha256(snapshot_path) == snapshot_sha

        resumed_loop, resumed = _run_once(root, runner)
        assert resumed.status == "neutral_menu_discovery_pending"
        collectors = _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        assert len(collectors) == 2
        first_command, resume_command = collectors
        assert "--resume" not in first_command
        assert "--resume" in resume_command
        assert resume_command[resume_command.index("--run-id") + 1] == run_id
        assert resume_command[resume_command.index("--only-package") + 1] == PACKAGE
        assert resume_command[resume_command.index("--only-package") + 1] != NEXT_PACKAGE
        assert resume_command[resume_command.index("--max-apps") + 1] == "1"
        assert Path(
            resume_command[resume_command.index("--inventory-snapshot") + 1]
        ).resolve() == snapshot_path.resolve()
        assert _sha256(
            Path(resume_command[resume_command.index("--inventory-snapshot") + 1])
        ) == snapshot_sha
        checkpoint = _checkpoint(resumed_loop)
        assert checkpoint["active_task"] is None
        assert set(checkpoint["stages"]) == {IDENTITY, NEXT_IDENTITY}
        assert checkpoint["stages"][IDENTITY][loop_module.STAGE_INITIAL]["status"] == "passed"
        assert (
            checkpoint["stages"][NEXT_IDENTITY]["coverage_stage"]
            == "initial_capture_pending"
        )
        assert loop_module.STAGE_INITIAL not in checkpoint["stages"][NEXT_IDENTITY]


def assert_stage_aware_scheduler_drains_offline_and_bounds_multi_app_progress() -> None:
    """New inventory cannot strand validated Netflix/Baemin pipelines."""

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(include_scheduler_apps=True)
        setup_loop = _make_loop(root, runner)
        snapshot, snapshot_path = setup_loop._discover()
        setup_loop._state["last_inventory"] = {
            "snapshot_id": snapshot["snapshot_id"],
            "path": setup_loop._store_observation_path(snapshot_path),
            "sha256": _sha256(snapshot_path),
            "included_app_count": len(snapshot["included_apps"]),
        }
        setup_loop._save("ready")
        assert _seed_validated_pending_app(
            setup_loop,
            runner,
            snapshot_path=snapshot_path,
            package=PACKAGE,
            priority_rank=2,
        ) == IDENTITY
        assert _seed_validated_pending_app(
            setup_loop,
            runner,
            snapshot_path=snapshot_path,
            package=BAEMIN_PACKAGE,
            priority_rank=3,
        ) == BAEMIN_IDENTITY
        assert NEW_IDENTITY not in _checkpoint(setup_loop)["stages"]

        selected: list[str | None] = []
        outcomes: list[str] = []
        for _round in range(8):
            command_offset = len(runner.commands)
            loop, outcome = _run_once(root, runner)
            selected.append(outcome.selected_identity)
            outcomes.append(outcome.status)
            round_commands = runner.commands[command_offset:]
            primary = [
                command
                for command in round_commands
                if _script_name(command)
                in {
                    loop_module.COLLECTOR_SCRIPT,
                    loop_module.GOAL_GENERATOR_SCRIPT,
                    loop_module.ARTIFACT_BUILDER_SCRIPT,
                }
            ]
            assert len(primary) == 1, primary

        assert selected == [
            IDENTITY,
            BAEMIN_IDENTITY,
            NEW_IDENTITY,
            IDENTITY,
            BAEMIN_IDENTITY,
            NEW_IDENTITY,
            NEW_IDENTITY,
            NEW_IDENTITY,
        ]
        assert outcomes[:2] == [
            "goal_directed_exploration_pending",
            "goal_directed_exploration_pending",
        ]
        assert outcomes[2] == "neutral_menu_discovery_pending"
        assert outcomes[3:5] == [
            "graph_coverage_validated",
            "graph_coverage_validated",
        ]
        assert outcomes[5:] == [
            "goal_candidate_generation_pending",
            "goal_directed_exploration_pending",
            "graph_coverage_validated",
        ]
        checkpoint = _checkpoint(loop)
        assert checkpoint["counters"]["rounds"] == 8
        for identity in (NEW_IDENTITY, IDENTITY, BAEMIN_IDENTITY):
            graph = checkpoint["stages"][identity]["graph_coverage_validation"]
            assert graph["status"] == "passed"
            assert graph["canonical_promotion_allowed"] is False
        assert checkpoint["canonical"]["mutation_allowed"] is False


def assert_offline_pending_drains_one_nonactive_app_without_device_access() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        _seed_validated_pending_second_app(boundary_loop, runner)

        loop = _make_loop(root, runner)
        before = _checkpoint(loop)
        active_identity = str(before["active_task"]["identity"])
        assert active_identity == IDENTITY
        active_stage_before = loop_module._canonical_json(
            before["stages"][active_identity]
        )
        active_task_before = loop_module._canonical_json(before["active_task"])
        active_run = loop._restore_observation_path(
            before["stages"][active_identity][loop_module.STAGE_INITIAL][
                "run_directory"
            ]
        )
        active_run_hashes = loop._run_file_hashes(active_run)
        command_offset = len(runner.commands)

        outcome = loop.drain_offline_pending()
        assert outcome.status == "offline_pending_applied"
        assert outcome.rounds_completed == 0
        assert outcome.selected_identity == NEXT_IDENTITY
        drain_commands = runner.commands[command_offset:]
        assert len(drain_commands) == 1
        assert _script_name(drain_commands[0]) == loop_module.GOAL_GENERATOR_SCRIPT
        assert "--hermes-reranker" not in drain_commands[0]
        assert not any(command[0] == "adb" for command in drain_commands)
        assert not any(
            _script_name(command)
            in {
                loop_module.DISCOVERY_SCRIPT,
                loop_module.COLLECTOR_SCRIPT,
                loop_module.VALIDATOR_SCRIPT,
                loop_module.ARTIFACT_BUILDER_SCRIPT,
            }
            for command in drain_commands
        )

        after = _checkpoint(loop)
        assert after["status"] == "user_action_boundary"
        assert loop_module._canonical_json(after["active_task"]) == active_task_before
        assert (
            loop_module._canonical_json(after["stages"][active_identity])
            == active_stage_before
        )
        assert loop._run_file_hashes(active_run) == active_run_hashes
        for key in (
            "schema_version",
            "orchestrator",
            "device_serial",
            "provenance",
            "review_status",
            "route_lifecycle",
            "canonical",
            "next_round",
            "last_inventory",
        ):
            assert after[key] == before[key], key
        for counter, previous in before["counters"].items():
            expected = previous + 1 if counter == "goal_candidate_passes" else previous
            assert after["counters"][counter] == expected, counter
        youtube = after["stages"][NEXT_IDENTITY]
        assert youtube["goal_candidates"]["status"] == "passed"
        assert youtube["goal_candidates"]["evidence"]["applicable"] == 1
        assert youtube["coverage_stage"] == "goal_directed_exploration_pending"
        assert youtube["goal_candidates"]["evidence"]["source_run_id"] == (
            youtube[loop_module.STAGE_DISCOVERY]["run_id"]
        )
        progress = [
            json.loads(line)
            for line in loop.progress_path.read_text(encoding="utf-8").splitlines()
        ]
        metrics = [
            json.loads(line)
            for line in loop.metric_path.read_text(encoding="utf-8").splitlines()
        ]
        assert progress[-1]["event_type"] == "offline_pending_applied"
        assert progress[-1]["execution_mode"] == "offline_pending"
        assert metrics[-1]["execution_mode"] == "offline_pending"
        assert metrics[-1]["device_command_count"] == 0
        assert metrics[-1]["collector_command_count"] == 0

        checkpoint_bytes = loop.checkpoint_path.read_bytes()
        command_offset = len(runner.commands)
        empty = _make_loop(root, runner).drain_offline_pending()
        assert empty.status == "offline_pending_empty"
        assert loop.checkpoint_path.read_bytes() == checkpoint_bytes
        assert runner.commands[command_offset:] == []

        collectors_before_resume = len(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        )
        resumed_loop, resumed = _run_once(root, runner)
        assert resumed.status == "neutral_menu_discovery_pending"
        collectors = _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        assert len(collectors) == collectors_before_resume + 1
        resume_command = collectors[-1]
        assert "--resume" in resume_command
        assert resume_command[resume_command.index("--only-package") + 1] == PACKAGE
        assert resume_command[resume_command.index("--only-package") + 1] != NEXT_PACKAGE
        assert (
            resume_command[resume_command.index("--run-id") + 1]
            == before["active_task"]["run_id"]
        )
        assert _checkpoint(resumed_loop)["active_task"] is None


def assert_offline_pending_tamper_and_cas_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, _boundary = _run_once(root, runner)
        _seed_validated_pending_second_app(boundary_loop, runner)
        checkpoint = _checkpoint(boundary_loop)
        discovery_run = boundary_loop._restore_observation_path(
            checkpoint["stages"][NEXT_IDENTITY][loop_module.STAGE_DISCOVERY][
                "run_directory"
            ]
        )
        manifest_path = discovery_run / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest["post_validation_tamper"] = True
        _write_json(manifest_path, manifest)
        checkpoint_bytes = boundary_loop.checkpoint_path.read_bytes()
        command_offset = len(runner.commands)
        try:
            _make_loop(root, runner).drain_offline_pending()
        except loop_module.LoopError as error:
            assert str(error) == "neutral_discovery_lineage_invalid"
        else:
            raise AssertionError("tampered discovery was accepted by offline drain")
        assert boundary_loop.checkpoint_path.read_bytes() == checkpoint_bytes
        assert runner.commands[command_offset:] == []

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, _boundary = _run_once(root, runner)
        _seed_validated_pending_second_app(boundary_loop, runner)
        original = _checkpoint(boundary_loop)

        def conflict() -> None:
            concurrent = _read_json(boundary_loop.checkpoint_path)
            concurrent["updated_at"] = "2030-01-01T00:00:00Z"
            _write_json(boundary_loop.checkpoint_path, concurrent)

        runner.on_generate = conflict
        try:
            _make_loop(root, runner).drain_offline_pending()
        except loop_module.LoopError as error:
            assert str(error) == "offline_pending_checkpoint_conflict"
        else:
            raise AssertionError("checkpoint CAS conflict was not rejected")
        conflicted = _checkpoint(boundary_loop)
        assert conflicted["updated_at"] == "2030-01-01T00:00:00Z"
        assert conflicted["active_task"] == original["active_task"]
        assert "goal_candidates" not in conflicted["stages"][NEXT_IDENTITY]
        generator_count = runner.generator_count
        runner.on_generate = None
        _write_json(boundary_loop.checkpoint_path, original)
        adopted = _make_loop(root, runner).drain_offline_pending()
        assert adopted.status == "offline_pending_applied"
        assert runner.generator_count == generator_count


def assert_checkpoint_validation_rejects_silent_normalization() -> None:
    malformed_states: list[tuple[str, dict[str, Any]]] = []

    non_mapping_stage = loop_module._default_state()
    non_mapping_stage["stages"]["invalid@stage"] = []
    malformed_states.append(("non_mapping_stage", non_mapping_stage))

    unknown_counter = loop_module._default_state()
    unknown_counter["counters"]["unknown_counter"] = 0
    malformed_states.append(("unknown_counter", unknown_counter))

    missing_counter = loop_module._default_state()
    missing_counter["counters"].pop("failures")
    malformed_states.append(("missing_counter", missing_counter))

    boolean_counter = loop_module._default_state()
    boolean_counter["counters"]["rounds"] = True
    malformed_states.append(("boolean_counter", boolean_counter))

    negative_counter = loop_module._default_state()
    negative_counter["counters"]["rounds"] = -1
    malformed_states.append(("negative_counter", negative_counter))

    malformed_scheduler = loop_module._default_state()
    malformed_scheduler["stages"][IDENTITY] = {
        "package": PACKAGE,
        "version_key": VERSION_KEY,
        "scheduler": {
            "first_seen_round": 1,
            "admission_lane": "fresh",
            "admission_reason": "new:unobserved_current_version",
            "first_inventory_rank": 1,
            "last_selected_round": -1,
            "selection_count": 0,
        },
    }
    malformed_states.append(("malformed_scheduler", malformed_scheduler))

    for name, value in malformed_states:
        try:
            loop_module._validate_state(value)
        except loop_module.LoopError as error:
            assert str(error) == "loop_checkpoint_invalid", (name, error)
        else:
            raise AssertionError(f"malformed checkpoint was silently normalized: {name}")


def assert_live_checkpoint_shape_remains_compatible_if_present() -> None:
    live_checkpoint = (
        REPO_ROOT
        / ".artifacts"
        / "navigation-observations"
        / "observation-loop"
        / loop_module.CHECKPOINT
    )
    if not live_checkpoint.is_file() or live_checkpoint.is_symlink():
        return
    value = _read_json(live_checkpoint)
    validated = loop_module._validate_state(value)
    assert loop_module._canonical_json(validated) == loop_module._canonical_json(value)


def assert_offline_pending_rejects_active_identity_key_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        _seed_validated_pending_second_app(boundary_loop, runner)

        checkpoint = _checkpoint(boundary_loop)
        forged_identity = f"{PACKAGE}@forged-version-key"
        checkpoint["stages"][forged_identity] = checkpoint["stages"].pop(IDENTITY)
        checkpoint["active_task"]["identity"] = forged_identity
        _write_json(boundary_loop.checkpoint_path, checkpoint)
        checkpoint_bytes = boundary_loop.checkpoint_path.read_bytes()
        command_offset = len(runner.commands)

        try:
            _make_loop(root, runner).drain_offline_pending()
        except loop_module.LoopError as error:
            assert str(error) == "loop_checkpoint_invalid"
        else:
            raise AssertionError("active identity/stage-key mismatch reached offline drain")
        assert boundary_loop.checkpoint_path.read_bytes() == checkpoint_bytes
        assert runner.commands[command_offset:] == []


def assert_offline_pending_rejects_goal_artifact_changed_after_validation() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        _seed_validated_pending_second_app(boundary_loop, runner)

        checkpoint = _checkpoint(boundary_loop)
        target = checkpoint["stages"][NEXT_IDENTITY]
        discovery = target[loop_module.STAGE_DISCOVERY]
        discovery_run = boundary_loop._restore_observation_path(
            discovery["run_directory"]
        )
        snapshot_path = boundary_loop._restore_observation_path(
            discovery["snapshot_path"]
        )
        generated = runner._generate(
            (
                sys.executable,
                str(REPO_ROOT / "scripts" / loop_module.GOAL_GENERATOR_SCRIPT),
                "--run-dir",
                str(discovery_run),
                "--inventory-snapshot",
                str(snapshot_path),
                "--family-manifest",
                str(FAMILY_MANIFEST),
            )
        )
        assert generated.returncode == 0

        loop = _make_loop(root, runner)
        original_prepare = loop._prepare_goal_candidates

        def prepare_then_tamper(item):
            artifact_path, evidence, return_code = original_prepare(item)
            assert evidence is not None
            validated_sha = str(evidence["artifact_sha256"])
            artifact = _read_json(artifact_path)
            artifact["post_validation_tamper"] = True
            _write_json(artifact_path, artifact)
            assert _sha256(artifact_path) != validated_sha
            return artifact_path, evidence, return_code

        loop._prepare_goal_candidates = prepare_then_tamper
        checkpoint_bytes = loop.checkpoint_path.read_bytes()
        command_offset = len(runner.commands)
        try:
            loop.drain_offline_pending()
        except loop_module.LoopError as error:
            assert str(error) == "goal_artifact_changed_after_validation"
        else:
            raise AssertionError("post-validation goal artifact mutation was committed")
        assert loop.checkpoint_path.read_bytes() == checkpoint_bytes
        assert runner.commands[command_offset:] == []


def assert_offline_mode_cli_and_shared_lock_are_exclusive() -> None:
    parser = loop_module.build_parser()
    with redirect_stderr(io.StringIO()):
        try:
            parser.parse_args(["--once", "--drain-offline-pending"])
        except SystemExit as error:
            assert error.code == 2
        else:
            raise AssertionError("offline drain and normal once mode were both accepted")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_INITIAL},
            include_next_app=True,
            boundary_code="authentication_boundary",
        )
        boundary_loop, _boundary = _run_once(root, runner)
        _seed_validated_pending_second_app(boundary_loop, runner)
        command_offset = len(runner.commands)
        lock_path = boundary_loop.state_root / "observation-loop.lock"
        with loop_module._ProcessLock(lock_path):
            try:
                _make_loop(root, runner).drain_offline_pending()
            except loop_module.LoopError as error:
                assert str(error) == "observation_loop_lock_unavailable"
            else:
                raise AssertionError("offline drain ignored the normal-process lock")
        assert runner.commands[command_offset:] == []


def _complete_active_run_outside_loop(
    runner: FakePipelineRunner,
    active: Mapping[str, Any],
) -> Path:
    run_id = str(active["run_id"])
    command = next(
        command
        for command in reversed(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        )
        if command[command.index("--run-id") + 1] == run_id
    )
    resumed_command = command if "--resume" in command else (*command, "--resume")
    report = json.loads(runner._collect(resumed_command).stdout)
    assert report["status"] == "completed"
    run_dir = Path(str(report["run_directory"]))
    # The production corpus service persists selected tasks under the pinned
    # inventory snapshot and does not retain the collector's top-level copy.
    manifest_path = run_dir / "manifest.json"
    manifest = _read_json(manifest_path)
    manifest.pop("tasks", None)
    _write_json(manifest_path, manifest)
    validation = runner._validate(
        (
            sys.executable,
            str(REPO_ROOT / "scripts" / loop_module.VALIDATOR_SCRIPT),
            "--run-dir",
            str(run_dir),
        )
    )
    assert validation.returncode == 0
    return run_dir


def assert_validated_external_completion_is_adopted_without_retry() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_DISCOVERY}
        )
        _run_once(root, runner)
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        active = _checkpoint(boundary_loop)["active_task"]
        assert active["stage"] == loop_module.STAGE_DISCOVERY
        run_dir = _complete_active_run_outside_loop(runner, active)
        core_hashes = {
            name: _sha256(run_dir / name)
            for name in loop_module.VALIDATION_CORE_ARTIFACTS
        }
        marker_hash = _sha256(run_dir / loop_module.VALIDATED)
        collector_count = len(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        )
        validator_count = len(
            _pipeline_commands(runner, loop_module.VALIDATOR_SCRIPT)
        )

        adopted_loop, adopted = _run_once(root, runner)
        assert adopted.status == "goal_candidate_generation_pending"
        assert len(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        ) == collector_count
        assert len(
            _pipeline_commands(runner, loop_module.VALIDATOR_SCRIPT)
        ) == validator_count
        checkpoint = _checkpoint(adopted_loop)
        assert checkpoint["active_task"] is None
        assert checkpoint["counters"]["neutral_discovery_passes"] == 1
        stage = _stage(adopted_loop)
        discovery = stage[loop_module.STAGE_DISCOVERY]
        assert discovery["run_id"] == active["run_id"]
        assert discovery["status"] == "passed"
        assert discovery["terminal_statuses"] == ["discovery_budget_complete"]
        assert discovery["validation"]["status"] == "passed"
        assert stage["neutral_discovery_generation"] == 1
        assert stage["coverage_stage"] == "goal_candidate_generation_pending"
        assert {
            name: _sha256(run_dir / name)
            for name in loop_module.VALIDATION_CORE_ARTIFACTS
        } == core_hashes
        assert _sha256(run_dir / loop_module.VALIDATED) == marker_hash
        progress = [
            json.loads(line)
            for line in adopted_loop.progress_path.read_text(encoding="utf-8").splitlines()
        ]
        assert any(
            event.get("event_type") == "validated_collection_adopted"
            and event.get("run_id") == active["run_id"]
            for event in progress
        )


def assert_tampered_external_completion_fails_closed_without_retry() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            boundary_once_stages={loop_module.STAGE_DISCOVERY}
        )
        _run_once(root, runner)
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        active = _checkpoint(boundary_loop)["active_task"]
        run_dir = _complete_active_run_outside_loop(runner, active)
        checkpoint_path = run_dir / "checkpoint.json"
        checkpoint_path.write_text(
            checkpoint_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )
        tampered_checkpoint = checkpoint_path.read_bytes()
        collector_count = len(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        )

        failed_loop, failed = _run_once(root, runner)
        assert failed.status == "round_failed"
        assert len(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        ) == collector_count
        assert checkpoint_path.read_bytes() == tampered_checkpoint
        checkpoint = _checkpoint(failed_loop)
        assert checkpoint["active_task"] is None
        assert checkpoint["counters"]["neutral_discovery_passes"] == 0
        stage = _stage(failed_loop)
        assert stage[loop_module.STAGE_DISCOVERY]["validation"] == {
            "status": "failed",
            "error_code": "validated_collection_adoption_invalid",
        }
        failures = [
            json.loads(line)
            for line in failed_loop.failure_path.read_text(encoding="utf-8").splitlines()
        ]
        assert failures[-1]["error_code"] == "validated_collection_adoption_invalid"


def assert_prelaunch_crash_reuses_run_without_false_resume_flag() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            crash_before_collect_stage=loop_module.STAGE_INITIAL
        )
        first_loop, first = _run_once(root, runner)
        assert first.status == "round_failed"
        active = _checkpoint(first_loop)["active_task"]
        run_id = active["run_id"]
        assert not (root / "observations" / run_id).exists()

        resumed_loop, resumed = _run_once(root, runner)
        assert resumed.status == "neutral_menu_discovery_pending"
        collectors = _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        assert len(collectors) == 2
        assert all(command[command.index("--run-id") + 1] == run_id for command in collectors)
        assert all("--resume" not in command for command in collectors)
        assert _checkpoint(resumed_loop)["active_task"] is None


def assert_no_applicable_candidate_is_evidence_not_completion() -> None:
    states = ("unverified", "not_applicable", "authentication_boundary")
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(
            applicability_batches=(states,),
            discovery_terminal="discovery_frontier_exhausted",
        )
        for expected in (
            "neutral_menu_discovery_pending",
            "goal_candidate_generation_pending",
            "neutral_rediscovery_scheduled",
        ):
            loop, outcome = _run_once(
                root,
                runner,
                refresh_rounds_without_applicable=2,
            )
            assert outcome.status == expected
        stage = _stage(loop)
        evidence = stage["goal_candidates"]["evidence"]
        assert evidence.get("applicable", 0) == 0
        assert evidence["unverified"] == 1
        assert evidence["not_applicable"] == 1
        assert evidence["authentication_boundary"] == 1
        assert stage["graph_coverage_validation"] == {
            "status": "pending_more_neutral_evidence",
            "reason_code": "no_applicable_candidate",
            "applicability_evidence": {
                "not_applicable": 1,
                "authentication_boundary": 1,
                "unverified": 1,
            },
            "canonical_promotion_allowed": False,
        }
        assert not loop_module.is_graph_coverage_validated(stage)
        assert not _pipeline_commands(runner, loop_module.GOAL_GENERATOR_SCRIPT)[0][-1:] == ("--force",)
        assert not any(
            "--goal-candidates" in command
            for command in _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        )

        wait_loop, waiting = _run_once(
            root,
            runner,
            refresh_rounds_without_applicable=2,
        )
        assert waiting.status == "waiting_for_scheduled_neutral_discovery"
        assert not loop_module.is_graph_coverage_validated(_stage(wait_loop))

        refresh_loop, refreshed = _run_once(
            root,
            runner,
            refresh_rounds_without_applicable=2,
        )
        assert refreshed.status == "goal_candidate_generation_pending"
        refreshed_stage = _stage(refresh_loop)
        history = refreshed_stage["applicability_history"]
        assert history[-1]["applicable"] == 0
        assert history[-1]["unverified"] == 1
        assert history[-1]["not_applicable"] == 1
        assert history[-1]["authentication_boundary"] == 1
        assert "goal_candidates" not in refreshed_stage
        assert "graph_coverage_validation" not in refreshed_stage


def assert_active_lineage_mismatch_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(boundary_once_stages={loop_module.STAGE_DIRECTED})
        for _ in range(3):
            _run_once(root, runner)
        boundary_loop, boundary = _run_once(root, runner)
        assert boundary.status == "user_action_boundary"
        active = _checkpoint(boundary_loop)["active_task"]
        artifact_path = root / "observations" / active["goal_artifact_path"]
        artifact_path.write_text(
            artifact_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
        )
        collector_count = len(_pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT))

        failed_loop, failed = _run_once(root, runner)
        assert failed.status == "round_failed"
        assert len(_pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)) == collector_count
        checkpoint = _checkpoint(failed_loop)
        assert checkpoint["active_task"] is None
        assert checkpoint["counters"]["graph_coverage_passes"] == 0
        failures = [
            json.loads(line)
            for line in failed_loop.failure_path.read_text(encoding="utf-8").splitlines()
        ]
        assert failures[-1]["error_code"] == "active_task_lineage_mismatch"


def assert_directed_manifest_lineage_mismatch_never_reaches_graph_gate() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner(corrupt_directed_lineage=True)
        for _ in range(3):
            _run_once(root, runner)
        loop, outcome = _run_once(root, runner)
        assert outcome.status == "round_failed"
        stage = _stage(loop)
        assert stage["goal_directed_exploration"]["validation"] == {
            "status": "failed",
            "error_code": "directed_candidate_coverage_incomplete",
        }
        assert "graph_coverage_validation" not in stage
        assert _checkpoint(loop)["counters"]["graph_coverage_passes"] == 0


def assert_post_validation_tamper_demotes_and_rebuilds_graph() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        graph_loop = _advance_to_graph(root, runner)
        stage = _stage(graph_loop)
        original_run_id = stage["goal_directed_exploration"]["run_id"]
        run_dir = root / "observations" / stage["goal_directed_exploration"]["run_directory"]
        (run_dir / "metrics.jsonl").write_text("", encoding="utf-8")

        failed_loop, failed = _run_once(root, runner)
        assert failed.status == "round_failed"
        failed_stage = _stage(failed_loop)
        assert failed_stage["graph_coverage_validation"]["status"] == "failed_lineage_mismatch"
        assert failed_stage["goal_directed_exploration"]["validation"]["status"] == "failed"
        assert not loop_module.is_graph_coverage_validated(failed_stage)

        rebuilt_loop, rebuilt = _run_once(root, runner)
        assert rebuilt.status == "graph_coverage_validated"
        rebuilt_stage = _stage(rebuilt_loop)
        assert rebuilt_stage["goal_directed_exploration"]["run_id"] != original_run_id
        assert loop_module.is_graph_coverage_validated(rebuilt_stage)


def assert_core_attestation_tamper_demotes_before_collection() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        graph_loop = _advance_to_graph(root, runner)
        stage = _stage(graph_loop)
        run_dir = (
            root
            / "observations"
            / stage["goal_directed_exploration"]["run_directory"]
        )
        corpus_path = run_dir / "corpus.sqlite"
        corpus_path.write_bytes(corpus_path.read_bytes() + b"tampered")
        collector_count = len(
            _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
        )

        failed_loop, failed = _run_once(root, runner)
        assert failed.status == "round_failed"
        assert len(_pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)) == collector_count
        failed_stage = _stage(failed_loop)
        assert failed_stage["graph_coverage_validation"]["status"] == "failed_lineage_mismatch"
        assert failed_stage["goal_directed_exploration"]["validation"]["status"] == "failed"
        assert not loop_module.is_graph_coverage_validated(failed_stage)


def assert_generator_publication_is_crash_recoverable() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        loop = None
        for _ in range(3):
            loop, _ = _run_once(root, runner)
        assert loop is not None and runner.generator_count == 1
        checkpoint = _checkpoint(loop)
        stage = checkpoint["stages"][IDENTITY]
        artifact_path = root / "observations" / stage["goal_candidates"]["path"]
        artifact_sha = _sha256(artifact_path)
        stage.pop("goal_candidates")
        stage["coverage_stage"] = "goal_candidate_generation_pending"
        _write_json(loop.checkpoint_path, checkpoint)

        recovered_loop, recovered = _run_once(root, runner)
        assert recovered.status == "goal_directed_exploration_pending"
        assert runner.generator_count == 1
        assert _stage(recovered_loop)["goal_candidates"]["sha256"] == artifact_sha


def _advance_to_current_goal_candidates(
    root: Path, runner: FakePipelineRunner
) -> tuple[Any, Path]:
    loop = None
    for _ in range(3):
        loop, _ = _run_once(root, runner)
    assert loop is not None
    stage = _stage(loop)
    artifact_path = root / "observations" / stage["goal_candidates"]["path"]
    assert stage["goal_candidates"]["goal_candidate_policy"] == (
        loop_module._goal_candidate_policy()
    )
    return loop, artifact_path


def _select_and_generate_without_device(loop, runner: FakePipelineRunner) -> str:
    checkpoint = _checkpoint(loop)
    snapshot_path = (
        loop.observation_root / checkpoint["last_inventory"]["path"]
    ).resolve()
    snapshot = _read_json(snapshot_path)
    runner.commands.clear()
    item = loop._select(snapshot, snapshot_path)
    assert item is not None and item.action == "generate_goal_candidates"
    outcome = loop._generate_candidates(item)
    assert not any(command[0] == "adb" for command in runner.commands)
    assert not _pipeline_commands(runner, loop_module.DISCOVERY_SCRIPT)
    assert not _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT)
    return outcome


def assert_legacy_goal_policy_requeues_and_regenerates_once_without_deletion() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        loop, artifact_path = _advance_to_current_goal_candidates(root, runner)
        artifact = _read_json(artifact_path)
        artifact.pop("goal_candidate_policy")
        artifact["evidence_policy"].pop("goal_candidate_policy_version")
        artifact["evidence_policy"].pop("goal_candidate_policy_sha256")
        artifact["apps"][0].pop("goal_candidate_policy")
        _write_json(artifact_path, artifact)
        legacy_bytes = artifact_path.read_bytes()
        legacy_sha = _sha256(artifact_path)
        checkpoint = _checkpoint(loop)
        candidates = checkpoint["stages"][IDENTITY]["goal_candidates"]
        candidates.pop("goal_candidate_policy")
        candidates["sha256"] = legacy_sha
        candidates["evidence"]["artifact_sha256"] = legacy_sha
        candidates["evidence"].pop("goal_candidate_policy_version")
        candidates["evidence"].pop("goal_candidate_policy_sha256")
        _write_json(loop.checkpoint_path, checkpoint)

        resumed = _make_loop(root, runner)
        assert _select_and_generate_without_device(resumed, runner) == (
            "goal_directed_exploration_pending"
        )
        assert runner.generator_count == 2
        assert artifact_path.read_bytes() == legacy_bytes
        current_path = artifact_path.parent / loop_module.CURRENT_GOAL_ARTIFACT
        assert current_path.is_file() and current_path != artifact_path
        generators = _pipeline_commands(runner, loop_module.GOAL_GENERATOR_SCRIPT)
        assert len(generators) == 1
        assert generators[0][generators[0].index("--output") + 1] == str(current_path)
        assert "--force" not in generators[0]
        stage = _stage(resumed)
        assert stage["goal_candidates"]["goal_candidate_policy"] == (
            loop_module._goal_candidate_policy()
        )
        assert stage["goal_candidates"]["path"].endswith(
            loop_module.CURRENT_GOAL_ARTIFACT
        )
        history = stage["goal_candidate_policy_history"]
        assert len(history) == 1
        assert history[0]["detected_policy_status"] == "legacy_missing"
        assert history[0]["canonical_promotion_allowed"] is False
        assert "goal_directed_exploration" not in stage


def assert_current_goal_policy_is_idempotently_reused() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        loop, artifact_path = _advance_to_current_goal_candidates(root, runner)
        artifact_sha = _sha256(artifact_path)
        checkpoint = _checkpoint(loop)
        stage = checkpoint["stages"][IDENTITY]
        stage.pop("goal_candidates")
        stage["coverage_stage"] = "goal_candidate_generation_pending"
        _write_json(loop.checkpoint_path, checkpoint)

        resumed = _make_loop(root, runner)
        assert _select_and_generate_without_device(resumed, runner) == (
            "goal_directed_exploration_pending"
        )
        assert runner.generator_count == 1
        assert not _pipeline_commands(runner, loop_module.GOAL_GENERATOR_SCRIPT)
        candidates = _stage(resumed)["goal_candidates"]
        assert candidates["sha256"] == artifact_sha
        assert candidates["goal_candidate_policy"] == (
            loop_module._goal_candidate_policy()
        )


def assert_tampered_goal_policy_requeues_fail_closed_without_trust() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        loop, artifact_path = _advance_to_current_goal_candidates(root, runner)
        artifact = _read_json(artifact_path)
        artifact["goal_candidate_policy"]["sha256"] = "f" * 64
        _write_json(artifact_path, artifact)
        tampered_bytes = artifact_path.read_bytes()
        tampered_sha = _sha256(artifact_path)
        checkpoint = _checkpoint(loop)
        candidates = checkpoint["stages"][IDENTITY]["goal_candidates"]
        candidates["sha256"] = tampered_sha
        candidates["evidence"]["artifact_sha256"] = tampered_sha
        _write_json(loop.checkpoint_path, checkpoint)

        resumed = _make_loop(root, runner)
        assert _select_and_generate_without_device(resumed, runner) == (
            "goal_directed_exploration_pending"
        )
        assert artifact_path.read_bytes() == tampered_bytes
        stage = _stage(resumed)
        assert stage["goal_candidates"]["path"].endswith(
            loop_module.CURRENT_GOAL_ARTIFACT
        )
        assert stage["goal_candidate_policy_history"][0][
            "detected_policy_status"
        ] == "tampered"
        assert stage["goal_candidates"]["evidence"][
            "goal_candidate_policy_sha256"
        ] == loop_module.GOAL_CANDIDATE_POLICY_SHA256


def assert_runtime_readiness_gates_fail_closed() -> None:
    for failure in ("accessibility", "overlay", "api"):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FakePipelineRunner(readiness_failure=failure)
            loop, outcome = _run_once(root, runner)
            assert outcome.status == "round_failed"
            stage = _stage(loop)
            assert stage["initial_capture"]["validation"] == {
                "status": "failed",
                "error_code": "collection_validation_failed",
            }
            assert not loop_module.is_graph_coverage_validated(stage)
            assert _checkpoint(loop)["counters"]["graph_coverage_passes"] == 0


def assert_optional_research_is_post_graph_and_unpromoted() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        graph_loop = _advance_to_graph(root, runner, build_research_artifacts=True)
        assert runner.builder_count == 0
        research_loop, outcome = _run_once(
            root,
            runner,
            build_research_artifacts=True,
        )
        assert outcome.status == "graph_coverage_validated"
        assert runner.builder_count == 1
        stage = _stage(research_loop)
        assert stage["research_artifacts"]["status"] == "passed"
        assert stage["research_artifacts"]["canonical_promotion"] == "not_recommended_until_human_review"
        assert stage["graph_coverage_validation"]["status"] == "passed"
        assert _stage(graph_loop)["graph_coverage_validation"]["canonical_promotion_allowed"] is False


def assert_keepalive_and_command_surface_are_exactly_bounded() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        runner = FakePipelineRunner()
        _advance_to_graph(root, runner)
        adb_commands = [command for command in runner.commands if command[0] == "adb"]
        allowed_suffixes = {
            ("get-state",),
            ("shell", "getprop", "ro.serialno"),
            ("shell", "getprop", "ro.kernel.qemu"),
            ("shell", "svc", "power", "stayon", "usb"),
            ("shell", "input", "keyevent", "KEYCODE_WAKEUP"),
        }
        assert adb_commands
        assert all(tuple(command[:3]) == ("adb", "-s", loop_module.EXPECTED_SERIAL) for command in adb_commands)
        assert {tuple(command[3:]) for command in adb_commands} == allowed_suffixes
        assert sum(tuple(command[3:]) == ("shell", "svc", "power", "stayon", "usb") for command in adb_commands) >= 4
        assert sum(tuple(command[3:]) == ("shell", "input", "keyevent", "KEYCODE_WAKEUP") for command in adb_commands) >= 4

        forbidden = {"tap", "swipe", "install", "uninstall", "delete", "clear", "logout"}
        assert all(not (set(token.casefold() for token in command) & forbidden) for command in runner.commands)
        for command in _pipeline_commands(runner, loop_module.COLLECTOR_SCRIPT):
            assert command[command.index("--serial") + 1] == loop_module.EXPECTED_SERIAL

        parser = loop_module.build_parser()
        defaults = parser.parse_args([])
        assert defaults.once is False and defaults.max_rounds == 0
        assert defaults.serial == loop_module.EXPECTED_SERIAL


def assert_poll_heartbeat_chunks_are_bounded() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        waits: list[float] = []
        root = Path(temporary)
        runner = FakePipelineRunner()
        observation_root = root / "observations"
        loop = loop_module.ObservationLoop(
            repo_root=REPO_ROOT,
            observation_root=observation_root,
            inventory_root=observation_root / "device-inventory",
            state_root=observation_root / "observation-loop",
            serial=loop_module.EXPECTED_SERIAL,
            python_executable=sys.executable,
            adb_executable="adb",
            runner=runner,
            clock=StepClock(),
            sleeper=waits.append,
            poll_seconds=100,
            emit_heartbeats=False,
        )
        loop._sleep()
        assert waits == [45.0, 45.0, 10.0]
        assert max(waits) < 60


def assert_exact_physical_serial_is_mandatory() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for serial in ("emulator-5554", "R3CY204GDVF"):
            try:
                loop_module.ObservationLoop(
                    repo_root=REPO_ROOT,
                    observation_root=root / "observations",
                    inventory_root=root / "observations" / "device-inventory",
                    state_root=root / "observations" / "observation-loop",
                    serial=serial,
                    runner=FakePipelineRunner(),
                )
            except loop_module.LoopError as error:
                assert str(error) == "exact_physical_serial_required"
            else:
                raise AssertionError("non-designated physical serial unexpectedly accepted")


def main() -> None:
    assert_staged_pipeline_requires_all_validated_stages()
    assert_each_collection_stage_resumes_exact_lineage()
    assert_initial_authentication_boundary_cannot_skip_to_next_app()
    assert_stage_aware_scheduler_drains_offline_and_bounds_multi_app_progress()
    assert_offline_pending_drains_one_nonactive_app_without_device_access()
    assert_offline_pending_tamper_and_cas_fail_closed()
    assert_checkpoint_validation_rejects_silent_normalization()
    assert_live_checkpoint_shape_remains_compatible_if_present()
    assert_offline_pending_rejects_active_identity_key_mismatch()
    assert_offline_pending_rejects_goal_artifact_changed_after_validation()
    assert_offline_mode_cli_and_shared_lock_are_exclusive()
    assert_validated_external_completion_is_adopted_without_retry()
    assert_tampered_external_completion_fails_closed_without_retry()
    assert_prelaunch_crash_reuses_run_without_false_resume_flag()
    assert_no_applicable_candidate_is_evidence_not_completion()
    assert_active_lineage_mismatch_fails_closed()
    assert_directed_manifest_lineage_mismatch_never_reaches_graph_gate()
    assert_post_validation_tamper_demotes_and_rebuilds_graph()
    assert_core_attestation_tamper_demotes_before_collection()
    assert_generator_publication_is_crash_recoverable()
    assert_legacy_goal_policy_requeues_and_regenerates_once_without_deletion()
    assert_current_goal_policy_is_idempotently_reused()
    assert_tampered_goal_policy_requeues_fail_closed_without_trust()
    assert_runtime_readiness_gates_fail_closed()
    assert_optional_research_is_post_graph_and_unpromoted()
    assert_keepalive_and_command_surface_are_exactly_bounded()
    assert_poll_heartbeat_chunks_are_bounded()
    assert_exact_physical_serial_is_mandatory()
    print("Real-device staged observation loop checks ok")


if __name__ == "__main__":
    main()
