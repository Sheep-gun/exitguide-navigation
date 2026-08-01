from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "Collect-RealDeviceObservations.py"
SPEC = importlib.util.spec_from_file_location("egl_real_device_collector", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


SAFE_XML = b"""<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="root" class="android.widget.FrameLayout"
        package="com.example.app" clickable="false" enabled="true" scrollable="false"
        checkable="false" checked="false" password="false" selected="false"
        bounds="[0,0][1080,2400]">
    <node index="0" text="Settings" resource-id="com.example.app:id/settings"
          class="android.widget.Button" package="com.example.app" clickable="true"
          enabled="true" scrollable="false" checkable="false" checked="false"
          password="false" selected="false" bounds="[20,120][1060,260]" />
    <node index="1" text="" content-desc="Menu list" resource-id="list"
          class="android.widget.ScrollView" package="com.example.app" clickable="false"
          enabled="true" scrollable="true" checkable="false" checked="false"
          password="false" selected="false" bounds="[0,260][1080,2200]" />
  </node>
</hierarchy>"""

SENSITIVE_XML = SAFE_XML.replace(
    b'<node index="0" text="Settings" resource-id="com.example.app:id/settings"',
    b'<node index="0" text="person@example.com" resource-id="com.example.app:id/email"',
).replace(b'class="android.widget.Button"', b'class="android.widget.EditText"', 1)

CONTEXT_SENSITIVE_XML = SAFE_XML.replace(
    b'text="Settings"',
    'text="Settings" content-desc="프로필 @sample_user" state-description="배송 주소를 확인하세요"'.encode(
        "utf-8"
    ),
    1,
)

STRUCTURAL_NUMERIC_ID_XML = SAFE_XML.replace(
    b'com.example.app:id/settings',
    b'com.example.app:id/task_a3645d76d16f6d51_01012345678',
)


class FakeRunner:
    def __init__(self, xml: bytes = SAFE_XML, *, qemu: str = "0") -> None:
        self.xml = xml
        self.qemu = qemu
        self.commands: list[list[str]] = []

    def __call__(self, command, timeout, binary):
        del timeout, binary
        command = list(command)
        self.commands.append(command)
        joined = " ".join(command)
        if joined.endswith("get-state"):
            return b"device\n"
        if "getprop sys.boot_completed" in joined:
            return b"1\n"
        if "getprop ro.kernel.qemu" in joined:
            return (self.qemu + "\n").encode()
        if "getprop ro.serialno" in joined:
            return (collector.EXPECTED_SERIAL + "\n").encode()
        if "getprop persist.sys.locale" in joined:
            return b"ko-KR\n"
        if "exec-out uiautomator dump /dev/tty" in joined:
            return b"UI hierarchy dumped\n" + self.xml + b"\ncomplete\n"
        if "exec-out screencap -p" in joined:
            raise AssertionError("default physical capture must not request a screenshot")
        if "dumpsys window windows" in joined:
            return b"mCurrentFocus=Window{abc u0 com.example.app/.MainActivity}"
        if "dumpsys package" in joined:
            return b"versionName=1.0.0\n"
        if "pm path" in joined:
            return b"package:/data/app/example/base.apk\n"
        return b""


def _capture(xml: bytes = SAFE_XML, package: str = "com.example.app"):
    tree = collector.base.parse_ui_xml(xml)
    return collector.ScreenCapture(
        capture_id="screen-one",
        captured_at="2026-07-31T00:00:00.000Z",
        package=package,
        activity_name=".MainActivity",
        app_version="1.0.0",
        locale="ko-KR",
        tree=tree,
        tree_path=Path("tree.xml"),
        screenshot_path=None,
        capture_ms=10.0,
        screenshot_sha256=None,
        tree_sha256="a" * 64,
    )


def _clickable(capture):
    return next(element for element in capture.tree.elements if element.clickable)


def _response(element, label="Settings", action="click"):
    return {
        "phase": "exploring",
        "screen_fingerprint": "us_1234567890abcdef",
        "automation": {
            "action": action,
            "safe_to_execute": True,
            "selected_element_id": element.element_id if element else None,
        },
        "recommendation": {
            "recommendation_id": "ur_1234567890abcdef",
            "selected_element_id": element.element_id if element else None,
            "selected_label": label,
            "risk_level": "low",
            "requires_user_confirmation": False,
        },
    }


def _graph_request(capture, *, request_id, transition=None):
    payload = {
        "request_id": request_id,
        "session_id": "physical_graph_unit_session",
        "app_package": "com.example.app",
        "app_version": capture.app_version,
        "locale": capture.locale,
        "goal_text": "Open settings",
        "operation_mode": "explore",
        "screen": collector.structured_screen_for_model(capture),
    }
    if transition is not None:
        payload["transition"] = transition
    return payload


def _graph_response(payload, *, recommendation=True, discovered_route=False):
    schemas, agent, graph = collector._graph_runtime()
    request = schemas.UniversalNavigationObserveRequest.model_validate(payload)
    candidates = agent.extract_navigation_candidates(request)
    fingerprint = graph.fingerprint_screen(request.app_package, request.screen)
    selected = candidates[0] if candidates else None
    recommendation_id = "ur_" + collector.stable_hash(
        {"request": request.request_id, "screen": fingerprint}, 16
    )
    recommendation_payload = None
    if recommendation:
        recommendation_payload = {
            "recommendation_id": recommendation_id,
            "selected_element_id": None if selected is None else selected.element_id,
            "selected_element_key": None if selected is None else selected.element_key,
            "selected_label": None if selected is None else selected.label,
            "target_function": "settings.open",
            "instruction": "Open Settings",
            "reason": "Deterministic unit fixture",
            "expected_next_screen": "Settings",
            "confidence": 0.9,
            "risk_level": "low",
            "requires_user_confirmation": False,
        }
    route_payload = None
    if discovered_route and selected is not None:
        route_payload = {
            "route_id": "global-route-unit",
            "target_function": "settings.open",
            "start_screen_fingerprint": fingerprint,
            "destination_screen_fingerprint": fingerprint,
            # Even an approved/global-looking input must enter this corpus as
            # a shadow/provisional candidate.
            "provisional": False,
            "lifecycle_status": "approved",
            "steps": [
                {
                    "ordinal": 0,
                    "from_screen_fingerprint": fingerprint,
                    "element_key": selected.element_key,
                    "label": selected.label,
                    "function_ids": ["settings.open"],
                    "expected_to_screen_fingerprint": fingerprint,
                    "terminal": True,
                    "confidence": 0.9,
                }
            ],
        }
    return {
        "request_id": request.request_id,
        "session_id": request.session_id,
        "status": "guided",
        "screen_fingerprint": fingerprint,
        "goal_interpretation": "Open application settings",
        "decision_mode": "deterministic_fallback",
        "phase": "guide",
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "recommendation": recommendation_payload,
        "graph_update": {
            "screen_created": True,
            "actions_created": len(candidates),
            "transition_recorded": payload.get("transition") is not None,
            "known_screen_count": 1,
            "known_transition_count": 0,
        },
        "automation": {
            "action": "none",
            "safe_to_execute": False,
            "reason": "unit fixture",
        },
        "discovered_route": route_payload,
        "warnings": [],
    }


def test_serial_and_physical_attestation_fail_closed() -> None:
    assert collector.validate_serial(collector.EXPECTED_SERIAL) == collector.EXPECTED_SERIAL
    for invalid in ("emulator-5554", "OTHER-PHONE", ""):
        try:
            collector.validate_serial(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"serial should be rejected: {invalid}")
    physical = collector.RealDeviceAdbClient("adb", runner=FakeRunner())
    physical.assert_ready()
    qemu = collector.RealDeviceAdbClient("adb", runner=FakeRunner(qemu="1"))
    try:
        qemu.assert_ready()
    except collector.AdbError:
        pass
    else:
        raise AssertionError("qemu device was accepted")


def test_install_delete_and_data_clear_commands_are_impossible() -> None:
    forbidden = (
        ("install", "app.apk"),
        ("uninstall", "com.example.app"),
        ("shell", "pm", "clear", "com.example.app"),
        ("shell", "pm", "uninstall", "com.example.app"),
        ("shell", "rm", "-f", "/sdcard/file"),
        ("shell", "content", "delete", "--uri", "content://x"),
    )
    for args in forbidden:
        try:
            collector.assert_non_destructive_adb_args(args)
        except collector.AdbError:
            pass
        else:
            raise AssertionError(f"destructive command accepted: {args}")
    collector.assert_non_destructive_adb_args(("shell", "input", "tap", "10", "20"))
    collector.assert_non_destructive_adb_args(("exec-out", "uiautomator", "dump", "/dev/tty"))


def test_accessibility_first_capture_keeps_no_raw_screenshot() -> None:
    fake = FakeRunner()
    adb = collector.RealDeviceAdbClient("adb", runner=fake)
    with tempfile.TemporaryDirectory() as temporary:
        app_dir = Path(temporary) / "app"
        app_dir.mkdir()
        capture = adb.capture_pair(app_dir, "one", screenshot_policy="none")
        assert capture.package == "com.example.app"
        assert capture.tree_path.exists()
        assert capture.screenshot_path is None
        commands = [" ".join(command) for command in fake.commands]
        assert any("exec-out uiautomator dump /dev/tty" in command for command in commands)
        assert not any("screencap" in command for command in commands)
        assert not any(" rm " in command or " install " in command or " uninstall " in command for command in commands)


def test_inventory_sensitive_capture_has_no_pre_recording_crash_window() -> None:
    canary = "SensitiveMenuCrashWindowCanary"
    xml = SAFE_XML.replace(b"Settings", canary.encode("utf-8"))
    fake = FakeRunner(xml)
    adb = collector.RealDeviceAdbClient("adb", runner=fake)
    original_writer = collector.atomic_write_bytes
    writes: list[Path] = []

    def forbidden_writer(path, payload):
        writes.append(Path(path))
        raise AssertionError("forced metadata-only capture attempted a disk write")

    collector.atomic_write_bytes = forbidden_writer
    try:
        with tempfile.TemporaryDirectory() as temporary:
            app_dir = Path(temporary) / "sensitive-app"
            app_dir.mkdir()
            capture = adb.capture_pair(
                app_dir,
                "sensitive-one",
                screenshot_policy="redacted",
                force_metadata_only=True,
            )
            # Simulate failure immediately after capture and before
            # `_record_capture` can run its defensive cleanup.
            try:
                raise RuntimeError("synthetic post-capture process failure")
            except RuntimeError:
                pass
            assert capture.tree_path.exists() is False
            assert capture.screenshot_path is None
            assert writes == []
            persisted = b"".join(
                path.read_bytes() for path in app_dir.rglob("*") if path.is_file()
            )
            assert canary.encode("utf-8") not in persisted
            commands = [" ".join(command) for command in fake.commands]
            assert not any("screencap" in command for command in commands)
    finally:
        collector.atomic_write_bytes = original_writer


def test_sensitive_screen_becomes_fully_redacted_metadata_only() -> None:
    tree = collector.base.parse_ui_xml(SENSITIVE_XML)
    privacy = collector.assess_privacy(tree)
    assert privacy.metadata_only is True
    derivative = collector.fully_redact_xml_text(tree.sanitized_xml)
    assert b"person@example.com" not in derivative
    root = collector.ET.fromstring(derivative)
    assert all(
        node.attrib.get(key) in {None, "", "[REDACTED]"}
        for node in root.iter("node")
        for key in ("text", "content-desc", "hint")
    )
    capture = _capture(SENSITIVE_XML)
    model_screen = collector.structured_screen_for_model(capture)
    assert model_screen["window_title"] == "[REDACTED]"
    assert all(
        element.get("text") in {None, "", "[REDACTED]"}
        and element.get("content_description") in {None, "", "[REDACTED]"}
        for element in model_screen["elements"]
    )
    assert "screenshot" not in model_screen and "screenshot_path" not in model_screen

    contextual_tree = collector.base.parse_ui_xml(CONTEXT_SENSITIVE_XML)
    contextual = collector.assess_privacy(contextual_tree)
    assert contextual.metadata_only is True
    assert "account_handle" in contextual.categories
    assert "location_or_address_context" in contextual.categories
    assert any("content_description:account_handle" in value for value in contextual.finding_contexts)
    assert any("state-description:location_or_address_context" in value for value in contextual.finding_contexts)
    contextual_derivative = collector.fully_redact_xml_text(contextual_tree.sanitized_xml)
    contextual_root = collector.ET.fromstring(contextual_derivative)
    assert all(
        node.attrib.get(key) in {None, "", collector.REDACTED}
        for node in contextual_root.iter("node")
        for key in collector.HUMAN_ACCESSIBILITY_XML_ATTRIBUTES
    )
    contextual_model = collector.structured_screen_for_model(_capture(CONTEXT_SENSITIVE_XML))
    assert contextual_model["window_title"] == collector.REDACTED
    assert all(
        not ({"text", "content_description", "view_id", "resource_id", "label", "inferred_label"} & set(element))
        for element in contextual_model["elements"]
    )

    # A phone-like sequence inside an opaque resource/element ID is structural
    # evidence, not human-facing PII.
    structural_tree = collector.base.parse_ui_xml(STRUCTURAL_NUMERIC_ID_XML)
    structural = collector.assess_privacy(structural_tree)
    assert structural.metadata_only is False, structural


def test_auth_permission_biometric_and_captcha_are_user_boundaries() -> None:
    cases = {
        "로그인": "authentication_boundary",
        "비밀번호": "authentication_boundary",
        "생체 인증": "authentication_boundary",
        "로봇이 아닙니다 CAPTCHA": "captcha_boundary",
        "권한 허용": "permission_boundary",
    }
    for label, expected in cases.items():
        xml = SAFE_XML.replace(b"Settings", label.encode("utf-8"))
        tree = collector.base.parse_ui_xml(xml)
        assert collector.user_boundary(tree, "com.example.app") == expected
    assert collector.user_boundary(_capture().tree, "com.android.permissioncontroller") == "permission_boundary"


def test_safe_menu_allowed_but_all_plain_final_actions_blocked() -> None:
    capture = _capture()
    element = _clickable(capture)
    allowed = collector.assess_physical_automation(
        _response(element, "Settings"), capture, expected_package="com.example.app"
    )
    assert allowed.allowed is True
    guard = collector.action_guard_for_decision(
        allowed, _response(element, "Settings")
    )
    assert guard.evidence() == {
        "policy_version": "egl-real-device-auto-action.v1",
        "evaluation_phase": "pre_execution",
        "action_type": "click",
        "allowed": True,
        "computed_final_or_consequential": False,
        "safe_menu_match": True,
        "reason": "physical_safe_menu_navigation",
    }
    for label in (
        "해지",
        "탈퇴",
        "삭제",
        "결제",
        "제출",
        "신청",
        "청구",
        "취소",
        "환불",
        "동의",
        "철회",
        "발급",
        "Submit",
        "Delete",
        "Cancel",
    ):
        decision = collector.assess_physical_automation(
            _response(element, label), capture, expected_package="com.example.app"
        )
        assert decision.allowed is False, label
        assert decision.reason in {"final_or_consequential_action", "consequential_final_action"}, (label, decision)
    assert collector.is_final_or_consequential("해지 안내") is False
    assert collector.is_final_or_consequential("구독 관리") is False
    assert collector.is_final_or_consequential("예약 조회") is False

    # A benign model label cannot launder a destructive source control.
    dangerous_xml = SAFE_XML.replace(b"Settings", b"Delete account")
    dangerous_capture = _capture(dangerous_xml)
    dangerous_element = _clickable(dangerous_capture)
    mismatch = collector.assess_physical_automation(
        _response(dangerous_element, "Account settings"),
        dangerous_capture,
        expected_package="com.example.app",
    )
    assert mismatch.allowed is False
    assert mismatch.reason == "final_or_consequential_action"


def test_unknown_click_feed_product_scroll_and_repeats_are_blocked() -> None:
    capture = _capture()
    unknown_xml = SAFE_XML.replace(b"Settings", b"Explore").replace(b"id/settings", b"id/discover")
    unknown_capture = _capture(unknown_xml)
    element = _clickable(unknown_capture)
    unknown = collector.assess_physical_automation(
        _response(element, "Explore"), unknown_capture, expected_package="com.example.app"
    )
    assert unknown.allowed is False
    assert unknown.reason == "not_a_safe_menu_or_setting"

    feed_tree = collector.base.parse_ui_xml(SAFE_XML.replace(b"Settings", b"For you timeline posts"))
    guard = collector.PhysicalScrollGuard(max_scrolls=3)
    assert guard.screen_type(feed_tree) == "infinite_feed"
    assert guard.assess(feed_tree).allowed is False

    product_tree = collector.base.parse_ui_xml(SAFE_XML.replace(b"Settings", "추천 상품 장바구니".encode("utf-8")))
    assert guard.screen_type(product_tree) == "product_list"
    assert guard.assess(product_tree).allowed is False

    safe_tree = capture.tree
    assert guard.assess(safe_tree).allowed is True
    guard.note(safe_tree)
    assert guard.assess(safe_tree).reason == "repeated_screen_after_scroll"
    x1, y1, x2, y2 = collector.page_scroll_points((0, 200, 1080, 2200))
    assert x1 == x2 == 540 and 1500 <= y1 - y2 <= 1650


def test_priority_goals_take_precedence_over_legacy_goals() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "apps.json"
        path.write_text(
            json.dumps(
                {
                    "apps": [
                        {
                            "app_package": "com.example.app",
                            "app_name": "Example",
                            "category": "test",
                            "priority_goals": ["설정 찾기", "고객센터 찾기"],
                            "goals": ["사용하면 안 되는 목표"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        args = argparse.Namespace(
            manifest=path,
            max_apps=0,
            max_goals_per_app=0,
            only_package=[],
        )
        tasks = collector.tasks_from_arguments(args)
        assert [task.goal_text for task in tasks] == ["설정 찾기", "고객센터 찾기"]


def test_manifest_only_package_filters_tasks_but_inventory_attests_every_app() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "apps.json"
        path.write_text(
            json.dumps(
                {
                    "apps": [
                        {"app_package": "com.example.one", "priority_goals": ["Open settings"]},
                        {"app_package": "com.example.two", "priority_goals": ["Open privacy"]},
                        {"app_package": "com.example.missing", "priority_goals": ["Open support"]},
                    ]
                }
            ),
            encoding="utf-8",
        )
        args = argparse.Namespace(
            manifest=path,
            max_apps=0,
            max_goals_per_app=0,
            only_package=["com.example.two", "com.example.two"],
        )
        tasks = collector.tasks_from_arguments(args)
        assert [task.app_package for task in tasks] == ["com.example.two"]
        rows = collector.inventory_status_rows(
            ["com.example.one", "com.example.two", "com.example.missing"],
            ["com.example.two"],
            lambda package: package != "com.example.missing",
        )
        assert rows == [
            {"app_package": "com.example.missing", "status": "skipped_missing"},
            {"app_package": "com.example.one", "status": "installed_not_selected"},
            {"app_package": "com.example.two", "status": "installed_observed"},
        ]
        args.only_package = ["com.example.unknown"]
        try:
            collector.tasks_from_arguments(args)
        except ValueError as error:
            assert "not present in manifest" in str(error)
        else:
            raise AssertionError("unknown --only-package was accepted")


def test_boundary_and_stopped_results_remain_resumable_until_explicit_completion() -> None:
    class CheckpointSink:
        def __init__(self) -> None:
            self.value = {
                "completed_task_ids": ["previous-task"],
                "current_task_id": "original",
                "state": {"action_count": 2, "screen_visits": {"screen": 1}},
            }

        def load_checkpoint(self):
            return dict(self.value)

        def checkpoint(self, value):
            self.value = dict(value)

    task = collector.CollectionTask(
        "com.example.app", "Example", "test", "Open account settings"
    )
    for status in (
        "boundary:authentication_boundary",
        "boundary:permission_boundary",
        "stopped:repeated_screen",
        "failed:observe_api_error",
    ):
        sink = CheckpointSink()
        completed = {"previous-task"}
        is_complete = collector.persist_task_result(
            sink, task, status, completed, {task.task_id: status}
        )
        assert is_complete is False
        assert task.task_id not in completed
        assert sink.value["current_task_id"] == task.task_id
        assert sink.value["current_task"]["app_package"] == task.app_package
        assert sink.value["state"]["action_count"] == 2

    for status in collector.COMPLETED_TASK_STATUSES:
        sink = CheckpointSink()
        completed = {"previous-task"}
        is_complete = collector.persist_task_result(
            sink, task, status, completed, {task.task_id: status}
        )
        assert is_complete is True
        assert task.task_id in completed
        assert sink.value["current_task_id"] is None
        assert sink.value["current_task"] is None

    capture_sink = CheckpointSink()
    capture_completed = {"previous-task"}
    capture_status = "boundary:authentication_boundary"
    assert collector.persist_task_result(
        capture_sink,
        task,
        capture_status,
        capture_completed,
        {task.task_id: capture_status},
        capture_boundary_terminal=True,
    ) is True
    assert task.task_id in capture_completed
    assert capture_sink.value["current_task_id"] is None
    assert capture_sink.value["task_status"] == capture_status


def test_latest_task_summary_statuses_prefers_latest_attempt() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "metrics.jsonl"
        path.write_text(
            "\n".join(
                json.dumps(row)
                for row in (
                    {
                        "metric_dimension": "task_summary",
                        "task_id": "task_a",
                        "attempt_number": 1,
                        "terminal_status": "failed:PermissionError",
                    },
                    {
                        "metric_dimension": "run_summary",
                        "task_id": "task_a",
                        "attempt_number": 99,
                        "terminal_status": "ignored",
                    },
                    {
                        "metric_dimension": "task_summary",
                        "task_id": "task_a",
                        "attempt_number": 2,
                        "terminal_status": "captured",
                    },
                )
            ),
            encoding="utf-8",
        )
        assert collector.latest_task_summary_statuses(path) == {
            "task_a": "captured"
        }


def test_corpus_manifest_contract_checkpoint_and_resume() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifest = {
            "schema_version": 1,
            "run_id": "physical-unit",
            "created_at": collector.utc_now(),
            "provenance": collector.PROVENANCE,
            "dataset_role": collector.DATASET_ROLE,
            "review_status": collector.REVIEW_STATUS,
            "route_lifecycle": collector.ROUTE_LIFECYCLE,
            "run_mode": "real_device_observation",
            "collection_mode": "capture_only",
            "validation_profile": "partial_research",
            "selected_packages": ["com.example.app"],
            "inventory_packages": ["com.example.app", "com.example.other"],
            "status": "collecting",
            "raw_artifacts_persisted": False,
            "device_serial": collector.EXPECTED_SERIAL,
            "app_statuses": [],
            "api_base_url": "http://127.0.0.1:8010",
        }
        sink = collector.RealObservationSink(root, "physical-unit", resume=False, manifest=manifest)
        task = collector.CollectionTask(
            "com.example.app", "Example", "test", "Open account settings"
        )
        sink.register_app_metadata(
            task, "1.0.0", "ko-KR", version_code="100"
        )
        goal_id = sink.register_goal(task)
        sink.set_app_status("com.example.app", "installed_observed")
        sink.set_app_status("com.example.other", "installed_not_selected")
        private_value = "private.person@example.com"
        sink.append(
            "screen",
            {
                "screen_id": "private-screen",
                "app_package": "com.example.app",
                "screen_signature": "private-signature",
                "privacy_verified": False,
                "visible_texts": [private_value],
                "resource_ids": [private_value],
            },
            record_id="private-screen",
            privacy_verified=False,
        )
        sink.append(
            "element",
            {
                "element_id": "private-element",
                "screen_id": "private-screen",
                "label": private_value,
                "inferred_label": private_value,
                "text": private_value,
                "resource_id": private_value,
                "expected_outcome": private_value,
                "inferred_icon_semantics": [private_value],
                "role": "button",
            },
            record_id="private-element",
            privacy_verified=False,
        )
        sink.checkpoint({"completed_task_ids": ["one"], "state": {"action_count": 1}})
        assert private_value not in (sink.run_directory / "elements.jsonl").read_text(encoding="utf-8")
        assert private_value not in (sink.run_directory / "screens.jsonl").read_text(encoding="utf-8")
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            screen_payload = json.loads(connection.execute("SELECT payload_json FROM screens").fetchone()[0])
            element_payload = json.loads(connection.execute("SELECT payload_json FROM elements").fetchone()[0])
        finally:
            connection.close()
        assert "resource_ids" not in screen_payload
        for key in (
            "text",
            "content_description",
            "label",
            "inferred_label",
            "resource_id",
            "expected_outcome",
            "inferred_icon_semantics",
        ):
            assert key not in element_payload
        assert sink.load_checkpoint()["completed_task_ids"] == ["one"]
        sink.finalize("incomplete")
        control = json.loads((sink.run_directory / "manifest.json").read_text(encoding="utf-8"))
        assert control["provenance"] == "real_device_observation_candidate"
        assert control["dataset_role"] == "real_device_observation_candidate"
        assert control["review_status"] == "unreviewed_candidate"
        assert control["route_lifecycle"] == "shadow"
        assert control["run_mode"] == "real_device_observation"
        assert control["status"] == "incomplete"
        assert control["raw_artifacts_persisted"] is False
        assert control["device_type"] in {"physical", "physical_android"}
        assert control["is_emulator"] is False
        assert control["device_serial"] == collector.EXPECTED_SERIAL
        assert control["app_statuses"] == [
            {"app_package": "com.example.app", "status": "installed_observed"},
            {"app_package": "com.example.other", "status": "installed_not_selected"},
        ]
        assert control["validation_profile"] == "partial_research"
        assert control["selected_packages"] == ["com.example.app"]
        assert control["inventory_packages"] == ["com.example.app", "com.example.other"]
        original_utc_now = collector.utc_now
        collector.utc_now = lambda: "2099-01-01T00:00:00.000Z"
        try:
            resumed = collector.RealObservationSink(
                root, "physical-unit", resume=True, manifest=manifest
            )
            assert resumed.load_checkpoint()["completed_task_ids"] == ["one"]
            before = {
                "apps": resumed.adapter.record_count("apps"),
                "goals": resumed.adapter.record_count("goals"),
            }
            resumed.register_app_metadata(
                task, "1.0.0", "ko-KR", version_code="100"
            )
            assert resumed.register_goal(task) == goal_id
            assert resumed.adapter.record_count("apps") == before["apps"]
            assert resumed.adapter.record_count("goals") == before["goals"]
        finally:
            collector.utc_now = original_utc_now


class CaptureOnlyAdb:
    def __init__(self, capture) -> None:
        self.capture = capture
        self.actions: list[str] = []

    def package_installed(self, package):
        return True

    def app_version(self, package):
        return "1.0"

    def locale(self):
        return "ko-KR"

    def launch(self, package):
        self.actions.append(f"launch:{package}")

    def capture_pair(
        self,
        app_directory,
        capture_id,
        screenshot_policy="none",
        force_metadata_only=False,
    ):
        del screenshot_policy
        tree_path = Path(app_directory) / "trees" / f"{capture_id}.xml"
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        if not force_metadata_only:
            tree_path.write_bytes(self.capture.tree.sanitized_xml)
        return replace(self.capture, capture_id=capture_id, tree_path=tree_path)

    def tap(self, bounds):
        self.actions.append(f"tap:{bounds}")

    def page_scroll(self, bounds):
        self.actions.append(f"scroll:{bounds}")
        return (540, 2000, 540, 400)

    def back(self):
        self.actions.append("back")


class SequenceAdb(CaptureOnlyAdb):
    def __init__(self, captures) -> None:
        super().__init__(captures[0])
        self.captures = list(captures)
        self.capture_index = 0

    def capture_pair(
        self,
        app_directory,
        capture_id,
        screenshot_policy="none",
        force_metadata_only=False,
    ):
        self.capture = self.captures[min(self.capture_index, len(self.captures) - 1)]
        self.capture_index += 1
        return super().capture_pair(
            app_directory,
            capture_id,
            screenshot_policy,
            force_metadata_only,
        )


class CrashAfterFirstCaptureAdb(CaptureOnlyAdb):
    def __init__(self, capture) -> None:
        super().__init__(capture)
        self.capture_count = 0

    def capture_pair(
        self,
        app_directory,
        capture_id,
        screenshot_policy="none",
        force_metadata_only=False,
    ):
        if self.capture_count:
            raise RuntimeError("synthetic process boundary")
        self.capture_count += 1
        return super().capture_pair(
            app_directory,
            capture_id,
            screenshot_policy,
            force_metadata_only,
        )


def test_safe_click_persists_pre_execution_guard_and_evidence_derived_counts() -> None:
    second_xml = SAFE_XML.replace(b"Settings", b"Account settings")
    calls = 0

    def transport(url, payload, timeout):
        nonlocal calls
        del url, timeout
        calls += 1
        if calls == 1:
            response = _graph_response(payload)
            selected = response["recommendation"]
            response["phase"] = "exploring"
            response["automation"] = {
                "action": "click",
                "safe_to_execute": True,
                "selected_element_id": selected["selected_element_id"],
                "reason": "safe menu fixture",
            }
            return response
        response = _graph_response(payload, recommendation=False)
        response["phase"] = "destination_reached"
        response["automation"] = {
            "action": "none",
            "safe_to_execute": False,
            "reason": "destination fixture",
        }
        return response

    with tempfile.TemporaryDirectory() as temporary:
        run_id = "safe-click-guard"
        sink = collector.RealObservationSink(
            Path(temporary),
            run_id,
            resume=False,
            manifest={
                "run_id": run_id,
                "created_at": collector.utc_now(),
                "api_base_url": "http://local",
                "run_mode": "real_device_observation",
                "collection_mode": "safe_explore",
                "app_statuses": [],
            },
        )
        adb = SequenceAdb((_capture(), _capture(second_xml)))
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient("http://local", transport=transport),
            sink,
            collector.ExplorationBudget(max_actions=3, settle_seconds=0),
            capture_only=False,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        task = collector.CollectionTask(
            "com.example.app", "Example", "test", "Open settings"
        )
        assert runner.run_task(task) == "destination_reached"
        assert len([value for value in adb.actions if value.startswith("tap:")]) == 1

        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            row = connection.execute(
                "SELECT element_id,selected_label,auto_action_guard_json,payload_json "
                "FROM transitions"
            ).fetchone()
        finally:
            connection.close()
        assert row is not None
        payload = json.loads(row[3])
        guard = payload["auto_action_guard"]
        assert row[0].startswith(payload["source_screen_id"] + ":adb_")
        assert json.loads(row[2]) == guard
        assert guard["evaluation_phase"] == "pre_execution"
        assert guard["computed_final_or_consequential"] is False
        assert guard["safe_menu_match"] is True
        assert guard["allowed"] is True
        assert payload["is_final_action"] is False
        assert payload["unsafe_action"] is False
        assert sink.action_safety_counts() == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }


def test_capture_only_never_calls_model_or_touches_ui() -> None:
    def forbidden_transport(url, payload, timeout):
        raise AssertionError((url, payload, timeout))

    with tempfile.TemporaryDirectory() as temporary:
        manifest = {
            "run_id": "capture-only",
            "created_at": collector.utc_now(),
            "api_base_url": "http://local",
            "run_mode": "real_device_observation",
            "collection_mode": "capture_only",
            "app_statuses": [],
        }
        sink = collector.RealObservationSink(Path(temporary), "capture-only", resume=False, manifest=manifest)
        adb = CaptureOnlyAdb(_capture())
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient("http://local", transport=forbidden_transport),
            sink,
            collector.ExplorationBudget(settle_seconds=0),
            capture_only=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        task = collector.CollectionTask("com.example.app", "Example", "test", "설정 찾기")
        assert runner.run_task(task) == "captured"
        assert not any(action.startswith(("tap:", "scroll:", "back")) for action in adb.actions)
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            row = connection.execute(
                "SELECT privacy_verified, evidence_mode, accessibility_tree_path, payload_json FROM screens"
            ).fetchone()
        finally:
            connection.close()
        assert row[0] == 1
        assert row[1] in {"verified_metadata", "verified_evidence", "verified_redacted"}
        assert row[2]
        assert json.loads(row[3])["evidence_retention"] == "redacted_derivative_only"
        graph_connection = sqlite3.connect(sink.run_directory / "graph-candidate.sqlite")
        try:
            graph_counts = {
                table: graph_connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "universal_screens",
                    "universal_actions",
                    "universal_transitions",
                    "universal_routes",
                    "universal_session_steps",
                )
            }
        finally:
            graph_connection.close()
        assert graph_counts["universal_screens"] == 1
        assert graph_counts["universal_actions"] >= 3  # Settings + scroll + system back
        assert graph_counts["universal_transitions"] == 0
        assert graph_counts["universal_routes"] == 0
        assert graph_counts["universal_session_steps"] == 0
        manifest_after_graph = json.loads((sink.run_directory / "manifest.json").read_text(encoding="utf-8"))
        graph_sha256 = collector.hashlib.sha256(
            (sink.run_directory / "graph-candidate.sqlite").read_bytes()
        ).hexdigest()
        assert manifest_after_graph["artifact_sha256"]["graph-candidate.sqlite"] == graph_sha256
        assert manifest_after_graph["safety"]["unsafe_auto_click_count"] == 0
        assert manifest_after_graph["safety"]["final_action_auto_click_count"] == 0


def test_capture_only_with_zero_action_scroll_and_back_budgets_still_captures_once() -> None:
    def forbidden_transport(url, payload, timeout):
        raise AssertionError((url, payload, timeout))

    with tempfile.TemporaryDirectory() as temporary:
        manifest = {
            "run_id": "capture-zero-budget",
            "created_at": collector.utc_now(),
            "api_base_url": "http://local",
            "run_mode": "real_device_observation",
            "collection_mode": "capture_only",
            "app_statuses": [],
        }
        sink = collector.RealObservationSink(
            Path(temporary),
            "capture-zero-budget",
            resume=False,
            manifest=manifest,
        )
        adb = CaptureOnlyAdb(_capture())
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient("http://local", transport=forbidden_transport),
            sink,
            collector.ExplorationBudget(
                max_actions=0,
                max_scrolls=0,
                max_backs=0,
                max_screen_visits=1,
                settle_seconds=0,
            ),
            capture_only=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        task = collector.CollectionTask(
            "com.example.app", "Example", "test", "Open settings"
        )
        assert runner.run_task(task) == "captured"
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            assert connection.execute("SELECT COUNT(*) FROM screens").fetchone()[0] == 1
        finally:
            connection.close()
        assert not any(action.startswith(("tap:", "scroll:", "back")) for action in adb.actions)


def test_capture_only_auth_boundary_resume_gets_one_fresh_capture_per_attempt() -> None:
    package = "com.netflix.mediaclient"
    authentication_xml = SAFE_XML.replace(
        b"com.example.app", package.encode("utf-8")
    ).replace(b"Settings", "로그인".encode("utf-8"))
    authenticated_xml = SAFE_XML.replace(
        b"com.example.app", package.encode("utf-8")
    ).replace(b"Settings", "계정 설정".encode("utf-8"))

    def forbidden_transport(url, payload, timeout):
        raise AssertionError((url, payload, timeout))

    with tempfile.TemporaryDirectory() as temporary:
        run_id = "netflix-auth-capture-resume"
        snapshot_id = "20260731T001109274Z-a244f3c98a"
        manifest = {
            "run_id": run_id,
            "created_at": collector.utc_now(),
            "api_base_url": "http://forbidden",
            "run_mode": "real_device_observation",
            "collection_mode": "capture_only",
            "app_statuses": [],
            "inventory_snapshot": {
                "snapshot_id": snapshot_id,
                "path": "device-inventory/inventory-netflix.json",
                "sha256": "a" * 64,
            },
        }
        sink = collector.RealObservationSink(
            Path(temporary), run_id, resume=False, manifest=manifest
        )
        budget = collector.ExplorationBudget(
            max_actions=0,
            max_scrolls=0,
            max_backs=0,
            max_screen_visits=1,
            settle_seconds=0,
        )
        task = collector.CollectionTask(
            package,
            "Netflix",
            collector.DYNAMIC_INVENTORY_PROFILE,
            collector.NEUTRAL_INVENTORY_GOAL,
        )
        first_adb = CaptureOnlyAdb(_capture(authentication_xml, package=package))
        first_runner = collector.PhysicalExplorationRunner(
            first_adb,
            collector.ObserveApiClient(
                "http://forbidden", transport=forbidden_transport
            ),
            sink,
            budget,
            capture_only=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        first_status = first_runner.run_task(task)
        assert first_status == "boundary:authentication_boundary"
        completed: set[str] = set()
        statuses = {task.task_id: first_status}
        assert (
            collector.persist_task_result(
                sink, task, first_status, completed, statuses
            )
            is False
        )
        boundary_checkpoint = sink.load_checkpoint()
        assert boundary_checkpoint["current_task_id"] == task.task_id
        assert boundary_checkpoint["state"]["action_count"] == 0
        assert len(boundary_checkpoint["state"]["screen_visits"]) == 1

        resumed_adb = CaptureOnlyAdb(_capture(authenticated_xml, package=package))
        resumed_runner = collector.PhysicalExplorationRunner(
            resumed_adb,
            collector.ObserveApiClient(
                "http://forbidden", transport=forbidden_transport
            ),
            sink,
            budget,
            capture_only=True,
            dry_run=False,
            launch_app=True,
            screenshot_policy="none",
        )
        resumed_status = resumed_runner.run_task(
            task, resume_state=boundary_checkpoint["state"]
        )
        assert resumed_status == "captured"
        statuses[task.task_id] = resumed_status
        assert (
            collector.persist_task_result(
                sink, task, resumed_status, completed, statuses
            )
            is True
        )
        assert completed == {task.task_id}
        assert sink.run_id == run_id
        assert task.task_id in sink.load_checkpoint()["completed_task_ids"]
        assert not any(
            action.startswith(("tap:", "scroll:", "back", "launch:"))
            for action in first_adb.actions + resumed_adb.actions
        )
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            assert connection.execute("SELECT COUNT(*) FROM screens").fetchone()[0] == 2
        finally:
            connection.close()
        failures = [
            json.loads(line)
            for line in (sink.run_directory / "failures.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        assert not any(
            row.get("failure_reason") == "action_budget_exhausted"
            for row in failures
        )
        persisted_manifest = json.loads(
            (sink.run_directory / "manifest.json").read_text(encoding="utf-8")
        )
        assert persisted_manifest["run_id"] == run_id
        assert persisted_manifest["inventory_snapshot"]["snapshot_id"] == snapshot_id


def test_capture_only_repeated_auth_screen_remains_user_boundary_on_resume() -> None:
    package = "com.netflix.mediaclient"
    authentication_xml = SAFE_XML.replace(
        b"com.example.app", package.encode("utf-8")
    ).replace(b"Settings", "로그인".encode("utf-8"))

    def forbidden_transport(url, payload, timeout):
        raise AssertionError((url, payload, timeout))

    with tempfile.TemporaryDirectory() as temporary:
        run_id = "netflix-auth-repeat-resume"
        sink = collector.RealObservationSink(
            Path(temporary),
            run_id,
            resume=False,
            manifest={
                "run_id": run_id,
                "created_at": collector.utc_now(),
                "api_base_url": "http://forbidden",
                "run_mode": "real_device_observation",
                "collection_mode": "capture_only",
                "app_statuses": [],
            },
        )
        budget = collector.ExplorationBudget(
            max_actions=0,
            max_scrolls=0,
            max_backs=0,
            max_screen_visits=1,
            settle_seconds=0,
        )
        task = collector.CollectionTask(
            package,
            "Netflix",
            collector.DYNAMIC_INVENTORY_PROFILE,
            collector.NEUTRAL_INVENTORY_GOAL,
        )

        def make_runner(adb):
            return collector.PhysicalExplorationRunner(
                adb,
                collector.ObserveApiClient(
                    "http://forbidden", transport=forbidden_transport
                ),
                sink,
                budget,
                capture_only=True,
                dry_run=False,
                launch_app=False,
                screenshot_policy="none",
            )

        first_adb = CaptureOnlyAdb(_capture(authentication_xml, package=package))
        assert make_runner(first_adb).run_task(task) == (
            "boundary:authentication_boundary"
        )
        first_checkpoint = sink.load_checkpoint()
        resumed_adb = CaptureOnlyAdb(_capture(authentication_xml, package=package))
        resumed_status = make_runner(resumed_adb).run_task(
            task, resume_state=first_checkpoint["state"]
        )
        assert resumed_status == "boundary:authentication_boundary"
        assert resumed_status != "stopped:repeated_screen"
        assert not any(
            action.startswith(("tap:", "scroll:", "back", "launch:"))
            for action in first_adb.actions + resumed_adb.actions
        )
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            assert connection.execute("SELECT COUNT(*) FROM screens").fetchone()[0] == 2
        finally:
            connection.close()
        failures = [
            json.loads(line)
            for line in (sink.run_directory / "failures.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        assert not any(
            row.get("failure_reason") in {
                "action_budget_exhausted",
                "repeated_screen",
            }
            for row in failures
        )


def test_observe_api_timeout_preserves_local_graph_and_records_failed_fallback_without_click() -> None:
    def unavailable_transport(url, payload, timeout):
        raise collector.ObserveApiError(f"timed out after {timeout}s")

    with tempfile.TemporaryDirectory() as temporary:
        manifest = {
            "run_id": "api-timeout-fallback",
            "created_at": collector.utc_now(),
            "api_base_url": "http://local",
            "run_mode": "real_device_observation",
            "collection_mode": "dry_run",
            "app_statuses": [],
        }
        sink = collector.RealObservationSink(
            Path(temporary),
            "api-timeout-fallback",
            resume=False,
            manifest=manifest,
        )
        adb = CaptureOnlyAdb(_capture())
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient("http://local", transport=unavailable_transport),
            sink,
            collector.ExplorationBudget(settle_seconds=0),
            capture_only=False,
            dry_run=True,
            launch_app=False,
            screenshot_policy="none",
        )
        task = collector.CollectionTask(
            "com.example.app", "Example", "test", "Open settings"
        )
        assert runner.run_task(task) == "failed:observe_api_error"
        assert not any(action.startswith(("tap:", "scroll:", "back")) for action in adb.actions)

        graph = sqlite3.connect(sink.run_directory / "graph-candidate.sqlite")
        try:
            assert graph.execute("SELECT COUNT(*) FROM universal_screens").fetchone()[0] == 1
            assert graph.execute("SELECT COUNT(*) FROM universal_actions").fetchone()[0] >= 3
            assert graph.execute("SELECT COUNT(*) FROM universal_transitions").fetchone()[0] == 0
        finally:
            graph.close()

        corpus = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            failure = json.loads(
                corpus.execute(
                    "SELECT payload_json FROM failures WHERE failure_reason='observe_api_error'"
                ).fetchone()[0]
            )
            metric = json.loads(
                corpus.execute(
                    "SELECT payload_json FROM metrics WHERE metric_dimension='provider_fallback'"
                ).fetchone()[0]
            )
        finally:
            corpus.close()
        assert failure["failure_reason"] == "observe_api_error"
        assert metric["provider_failure"] is True
        assert metric["fallback_used"] is True
        assert metric["fallback_mode"] == "deterministic_local_graph_mirror"
        assert metric["unsafe_auto_click_count"] == 0
        assert metric["final_action_auto_click_count"] == 0


def test_run_local_graph_mirrors_api_fingerprint_routes_and_all_navigation_edges() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = {
            "run_id": "graph-mirror",
            "created_at": collector.utc_now(),
            "api_base_url": "http://local",
            "run_mode": "real_device_observation",
            "collection_mode": "dry_run",
            "app_statuses": [],
        }
        sink = collector.RealObservationSink(Path(temporary), "graph-mirror", resume=False, manifest=manifest)

        first_capture = _capture()
        first_request = _graph_request(first_capture, request_id="graph-request-one")
        first_response = _graph_response(first_request, discovered_route=True)
        first_result = sink.mirror_graph_observation(first_request, api_response=first_response)
        assert first_result.screen_fingerprint == first_response["screen_fingerprint"]
        assert first_result.recommendation_recorded is True
        assert first_result.route_recorded is True

        selected_element_id = first_response["recommendation"]["selected_element_id"]
        recommendation_id = first_response["recommendation"]["recommendation_id"]
        transitions = [
            (selected_element_id, recommendation_id, "Profile"),
            ("__page_scroll__", None, "Privacy"),
            ("__back__", None, "Support"),
        ]
        from_fingerprint = first_result.screen_fingerprint
        for ordinal, (element_id, rec_id, next_label) in enumerate(transitions, 2):
            xml = SAFE_XML.replace(b"Settings", next_label.encode("utf-8"))
            capture = _capture(xml)
            capture = replace(capture, capture_id=f"screen-{ordinal}")
            transition = {
                "from_screen_fingerprint": from_fingerprint,
                "performed_element_id": element_id,
                "outcome": "navigated",
            }
            if rec_id:
                transition["recommendation_id"] = rec_id
            request = _graph_request(
                capture,
                request_id=f"graph-request-{ordinal}",
                transition=transition,
            )
            response = _graph_response(request, recommendation=False)
            result = sink.mirror_graph_observation(request, api_response=response)
            assert result.transition_recorded is True
            from_fingerprint = result.screen_fingerprint

        connection = sqlite3.connect(sink.run_directory / "graph-candidate.sqlite")
        try:
            route = connection.execute(
                "SELECT status, provisional FROM universal_routes"
            ).fetchone()
            edges = connection.execute(
                """
                SELECT action.last_element_id, transition.success_count, transition.failure_count
                FROM universal_transitions transition
                JOIN universal_actions action ON action.action_id = transition.action_id
                ORDER BY transition.first_seen_at, action.last_element_id
                """
            ).fetchall()
            seen_counts = connection.execute(
                "SELECT seen_count FROM universal_screens"
            ).fetchall()
        finally:
            connection.close()
        assert route == ("shadow", 1)
        assert {row[0] for row in edges} == {selected_element_id, "__page_scroll__", "__back__"}
        assert all(row[1:] == (1, 0) for row in edges)
        assert all(row[0] == 1 for row in seen_counts)


def test_graph_fingerprint_mismatch_fails_before_run_local_write() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        manifest = {
            "run_id": "graph-mismatch",
            "created_at": collector.utc_now(),
            "api_base_url": "http://local",
            "run_mode": "real_device_observation",
            "collection_mode": "dry_run",
            "app_statuses": [],
        }
        sink = collector.RealObservationSink(Path(temporary), "graph-mismatch", resume=False, manifest=manifest)
        request = _graph_request(_capture(), request_id="graph-mismatch-request")
        response = _graph_response(request)
        response["screen_fingerprint"] = "us_0000000000000000"
        try:
            sink.mirror_graph_observation(request, api_response=response)
        except collector.GraphMirrorError:
            pass
        else:
            raise AssertionError("API/run-local fingerprint mismatch was accepted")
        candidate_mismatch = _graph_response(request)
        candidate_mismatch["candidates"][0]["label"] = "Tampered candidate"
        try:
            sink.mirror_graph_observation(request, api_response=candidate_mismatch)
        except collector.GraphMirrorError:
            pass
        else:
            raise AssertionError("API/run-local candidate mismatch was accepted")
        connection = sqlite3.connect(sink.run_directory / "graph-candidate.sqlite")
        try:
            assert connection.execute("SELECT COUNT(*) FROM universal_screens").fetchone()[0] == 0
        finally:
            connection.close()


def _dynamic_snapshot_document() -> dict[str, object]:
    included = [
        {
            "package": "com.example.new",
            "launchable_activity": "com.example.new/.MainActivity",
            "version_name": "2.0",
            "version_code": "20",
            "version_key": "code:20|name:2.0",
            "included": True,
            "decision_reason_code": "user_facing_launchable",
            "sensitivity_categories": ["conversation_message"],
            "sensitivity_handling": "heightened_metadata_only",
            "change_status": "new",
            "observation_status": "unobserved_current_version",
        },
        {
            "package": "com.example.updated",
            "launchable_activity": "com.example.updated/.MainActivity",
            "version_name": "3.1",
            "version_code": "31",
            "version_key": "code:31|name:3.1",
            "included": True,
            "decision_reason_code": "user_facing_launchable",
            "sensitivity_categories": [],
            "sensitivity_handling": "standard_metadata_only",
            "change_status": "updated",
            "observation_status": "unobserved_current_version",
        },
    ]
    excluded = [
        {
            "package": "com.example.excluded",
            "launchable_activity": None,
            "version_name": "1.0",
            "version_code": "10",
            "version_key": "code:10|name:1.0",
            "included": False,
            "decision_reason_code": "non_launchable",
            "sensitivity_categories": [],
            "sensitivity_handling": "standard_metadata_only",
            "change_status": "unchanged",
            "observation_status": "unobserved_current_version",
        }
    ]
    return {
        "schema_version": 1,
        "snapshot_id": "inventory-unit-new-updated",
        "provenance": collector.PROVENANCE,
        "dataset_role": collector.DATASET_ROLE,
        "review_status": collector.REVIEW_STATUS,
        "route_lifecycle": collector.ROUTE_LIFECYCLE,
        "canonical_catalog_mutation": False,
        "canonical_catalog": collector.EXPECTED_INVENTORY_CANONICAL,
        "device": {
            "serial": collector.EXPECTED_SERIAL,
            "device_type": "physical_android",
            "is_emulator": False,
            "model": "synthetic",
            "android_version": "16",
            "locale": "ko-KR",
        },
        "discovered_at": "2026-07-31T00:00:00.000Z",
        "previous_snapshot_id": "inventory-unit-previous",
        "summary": {"included_apps": 2, "excluded_apps": 1},
        "included_apps": included,
        "excluded_apps": excluded,
        "removed_apps": [],
        "prioritized_apps": [
            {
                "priority_rank": 1,
                "package": "com.example.new",
                "version_key": "code:20|name:2.0",
                "change_status": "new",
                "observation_status": "unobserved_current_version",
                "priority_reason": "new_package",
                "sensitivity_categories": ["conversation_message"],
                "sensitivity_handling": "heightened_metadata_only",
            },
            {
                "priority_rank": 2,
                "package": "com.example.updated",
                "version_key": "code:31|name:3.1",
                "change_status": "updated",
                "observation_status": "unobserved_current_version",
                "priority_reason": "updated_version",
                "sensitivity_categories": [],
                "sensitivity_handling": "standard_metadata_only",
            },
        ],
    }


def test_dynamic_inventory_selects_new_updated_and_rejects_excluded_package() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "inventory.json"
        path.write_text(
            json.dumps(_dynamic_snapshot_document(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        snapshot = collector.load_dynamic_inventory_snapshot(path)
        tasks = collector.dynamic_inventory_tasks(snapshot)
        assert [task.app_package for task in tasks] == [
            "com.example.new",
            "com.example.updated",
        ]
        assert all(task.goal_text == collector.NEUTRAL_INVENTORY_GOAL for task in tasks)
        assert tasks[0].sensitivity_categories == ("conversation_message",)
        selected = collector.dynamic_inventory_tasks(
            snapshot, only_packages=["com.example.updated", "com.example.updated"]
        )
        assert [task.app_package for task in selected] == ["com.example.updated"]
        try:
            collector.dynamic_inventory_tasks(
                snapshot, only_packages=["com.example.excluded"]
            )
        except ValueError as error:
            assert "excluded inventory package" in str(error)
        else:
            raise AssertionError("excluded snapshot package was selectable")
        metadata = collector.dynamic_inventory_manifest_metadata(
            snapshot,
            observation_root=Path(temporary),
            run_id="dynamic-unit",
            selected_packages=["com.example.updated"],
        )
        assert len(metadata["included_inventory"]) == 2
        assert metadata["selected_packages"] == ["com.example.updated"]
        assert len(metadata["version_candidates"]) == 2


def test_inventory_snapshot_cli_is_mutually_exclusive_with_static_sources() -> None:
    parser = collector.build_parser()
    for arguments in (
        ["--inventory-snapshot", "inventory.json", "--manifest", "apps.json"],
        ["--inventory-snapshot", "inventory.json", "--package", "com.example.app"],
    ):
        try:
            parser.parse_args(arguments)
        except SystemExit:
            pass
        else:
            raise AssertionError("mutually exclusive inventory source arguments were accepted")


def test_dynamic_runtime_attestation_is_exact_and_fail_closed() -> None:
    expected_device = {
        "serial": collector.EXPECTED_SERIAL,
        "model": "SM-S936N",
        "android_version": "16",
        "locale": "ko-KR",
    }

    class RuntimeAdb:
        accessibility = collector.EXITGUIDE_ACCESSIBILITY_COMPONENT
        overlay = "SYSTEM_ALERT_WINDOW: allow"
        model = "SM-S936N"

        def shell(self, *args, timeout=0):
            del timeout
            responses = {
                ("getprop", "ro.serialno"): collector.EXPECTED_SERIAL,
                ("getprop", "ro.product.model"): self.model,
                ("getprop", "ro.build.version.release"): "16",
                (
                    "settings",
                    "get",
                    "secure",
                    "enabled_accessibility_services",
                ): self.accessibility,
                (
                    "cmd",
                    "appops",
                    "get",
                    collector.EXITGUIDE_PACKAGE,
                    "android:system_alert_window",
                ): self.overlay,
            }
            return responses[tuple(args)]

        def locale(self):
            return "ko-KR"

        def package_installed(self, package):
            return package == collector.EXITGUIDE_PACKAGE

    health_calls = []

    def health_transport(url, timeout):
        health_calls.append((url, timeout))
        return (
            {"status": "ok", "llm_provider": "exaone", "provider_ready": True}
            if url.endswith("/v1/status")
            else {"status": "ok"}
        )

    adb = RuntimeAdb()
    attestation = collector.collect_runtime_attestation(
        adb,
        expected_device=expected_device,
        api_base_url="https://api.example.test",
        health_transport=health_transport,
    )
    assert attestation["device"] == {
        **expected_device,
        "device_type": "physical_android",
        "is_emulator": False,
    }
    assert attestation["exitguide"]["accessibility_enabled"] is True
    assert attestation["exitguide"]["overlay_appop"] == "allow"
    assert attestation["api"] == {
        "health_path": "/health",
        "status": "ok",
        "provider_status_path": "/v1/status",
        "llm_provider": "exaone",
        "provider_ready": True,
    }
    assert health_calls == [
        ("https://api.example.test/health", 10.0),
        ("https://api.example.test/v1/status", 10.0),
    ]

    for mutation, error_text in (
        (lambda value: setattr(value, "model", "wrong-model"), "device metadata"),
        (lambda value: setattr(value, "accessibility", "null"), "accessibility"),
        (lambda value: setattr(value, "overlay", "SYSTEM_ALERT_WINDOW: ignore"), "overlay"),
    ):
        failing = RuntimeAdb()
        mutation(failing)
        try:
            collector.collect_runtime_attestation(
                failing,
                expected_device=expected_device,
                api_base_url="https://api.example.test",
                health_transport=health_transport,
            )
        except collector.AdbError as error:
            assert error_text in str(error)
        else:
            raise AssertionError(f"runtime attestation accepted {error_text} mismatch")

    try:
        collector.collect_runtime_attestation(
            RuntimeAdb(),
            expected_device=expected_device,
            api_base_url="https://api.example.test?token=secret",
            health_transport=health_transport,
        )
    except collector.ObserveApiError as error:
        assert "not safe" in str(error)
    else:
        raise AssertionError("runtime attestation accepted a credential-bearing URL")

    try:
        collector.collect_runtime_attestation(
            RuntimeAdb(),
            expected_device=expected_device,
            api_base_url="https://api.example.test",
            health_transport=lambda url, timeout: (
                {"status": "ok", "llm_provider": "mock", "provider_ready": True}
                if url.endswith("/v1/status")
                else {"status": "ok"}
            ),
        )
    except collector.ObserveApiError as error:
        assert "llm_provider=exaone" in str(error)
    else:
        raise AssertionError("runtime attestation accepted a non-EXAONE provider")


def test_sensitive_dynamic_categories_force_metadata_only_and_zero_api_transfer() -> None:
    cases = (
        ("com.openai.chatgpt", "conversation_message", "OrchidCanaryAlpha"),
        ("org.telegram.messenger", "conversation_message", "CobaltCanaryBeta"),
        ("com.dunamu.exchange", "finance", "QuartzCanaryGamma"),
        ("kr.co.station3.dabang", "real_estate_location", "MapleCanaryDelta"),
        ("com.samsung.android.shealth", "health_medical", "WillowCanaryZeta"),
        ("com.google.android.apps.photos", "personal_content", "SaffronCanaryEta"),
        ("com.example.auth", "auth_security", "NimbusCanaryEpsilon"),
    )
    for ordinal, (package, category, private_value) in enumerate(cases):
        first_xml = SAFE_XML.replace(b"com.example.app", package.encode("utf-8")).replace(
            b"Settings", private_value.encode("utf-8")
        )
        second_private_value = f"SensitiveBalanceBoundary{ordinal}"
        second_xml = SAFE_XML.replace(
            b"com.example.app", package.encode("utf-8")
        ).replace(
            b"Settings",
            f"잔액 {second_private_value}".encode("utf-8"),
        )
        capture = _capture(first_xml, package=package)
        task = collector.CollectionTask(
            package,
            package,
            collector.DYNAMIC_INVENTORY_PROFILE,
            collector.NEUTRAL_INVENTORY_GOAL,
            sensitivity_categories=(category,),
            sensitivity_handling="heightened_metadata_only",
        )
        forced = collector.apply_dynamic_sensitivity_policy(
            task, capture, collector.assess_privacy(capture.tree)
        )
        assert forced.metadata_only is True
        model_screen = collector.structured_screen_for_model(
            capture, force_metadata_only=True
        )
        assert private_value not in json.dumps(model_screen, ensure_ascii=False)
        with tempfile.TemporaryDirectory() as temporary:
            run_id = f"sensitive-dynamic-{ordinal}"
            sink = collector.RealObservationSink(
                Path(temporary),
                run_id,
                resume=False,
                manifest={
                    "run_id": run_id,
                    "created_at": collector.utc_now(),
                    "api_base_url": "http://forbidden",
                    "run_mode": "real_device_observation",
                    "collection_mode": "safe_explore",
                    "app_statuses": [],
                },
            )

            def forbidden_transport(url, payload, timeout):
                raise AssertionError((url, payload, timeout))

            runner = collector.PhysicalExplorationRunner(
                SequenceAdb((capture, _capture(second_xml, package=package))),
                collector.ObserveApiClient("http://forbidden", transport=forbidden_transport),
                sink,
                collector.ExplorationBudget(max_actions=3, settle_seconds=0),
                capture_only=False,
                discovery_explore=True,
                dry_run=False,
                launch_app=False,
                screenshot_policy="none",
            )
            status = runner.run_task(task)
            assert status.startswith("boundary:")
            assert status != "destination_reached"
            assert runner.adb.actions.count("back") == 0
            assert len(
                [value for value in runner.adb.actions if value.startswith("tap:")]
            ) == 1
            assert not any(
                value.startswith("scroll:") for value in runner.adb.actions
            )
            forbidden_bytes = (
                private_value.encode("utf-8"),
                second_private_value.encode("utf-8"),
            )
            for path in sink.run_directory.rglob("*"):
                if path.is_file():
                    payload = path.read_bytes()
                    assert all(value not in payload for value in forbidden_bytes), path
            connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
            try:
                screens = connection.execute(
                    "SELECT privacy_verified,evidence_mode,payload_json FROM screens"
                ).fetchall()
                metrics = [
                    payload
                    for (payload_json,) in connection.execute(
                        "SELECT payload_json FROM metrics WHERE metric_dimension='sensitive_local_policy'"
                    )
                    if (payload := json.loads(payload_json))
                ]
                transition = json.loads(
                    connection.execute("SELECT payload_json FROM transitions").fetchone()[0]
                )
            finally:
                connection.close()
            assert len(screens) == 2
            assert all(row[0] == 0 and row[1] == "metadata_only" for row in screens)
            assert all(
                json.loads(row[2])["forced_dynamic_metadata_only"] is True
                for row in screens
            )
            assert metrics and all(
                metric["external_api_transfer_count"] == 0 for metric in metrics
            )
            assert transition["selected_label"] == collector.SENSITIVE_GUARD_LABEL_BUCKET
            assert transition["sensitive_local_only"] is True
            assert transition["sensitive_local_decision"]["human_text_persisted"] is False
            assert transition["auto_action_guard"]["allowed"] is True
            assert sink.action_safety_counts() == {
                "unsafe_auto_click_count": 0,
                "final_action_auto_click_count": 0,
            }
            checkpoint = sink.load_checkpoint()
            assert checkpoint["state"]["external_api_transfer_count"] == 0
            assert checkpoint["state"]["pending_action"] is None
            assert checkpoint["state"]["scroll_novelty_label_sets"] == []
            assert not list(sink.run_directory.rglob("*.xml"))

    safe_task = collector.CollectionTask(
        "com.example.app",
        "Example",
        collector.DYNAMIC_INVENTORY_PROFILE,
        collector.NEUTRAL_INVENTORY_GOAL,
        sensitivity_categories=("finance",),
    )
    safe_capture = _capture()
    assert collector._verified_sensitive_menu_screen(safe_capture) is True
    assert collector.apply_dynamic_sensitivity_policy(
        safe_task, safe_capture, collector.assess_privacy(safe_capture.tree)
    ).metadata_only is True


def _dynamic_private_surface_xml(
    package: str,
    private_text: str,
    *,
    safe_gateway: bool = False,
    final_control: bool = False,
    editable: bool = False,
) -> bytes:
    controls: list[str] = []
    if safe_gateway:
        controls.append(
            f'''<node index="1" text="마이배민" resource-id="{package}:id/my_baemin"
                  class="android.widget.Button" package="{package}" clickable="true"
                  enabled="true" scrollable="false" checkable="false" checked="false"
                  password="false" selected="false" bounds="[20,300][1060,440]" />'''
        )
    if final_control:
        controls.append(
            f'''<node index="2" text="Delete account" resource-id="{package}:id/delete_account"
                  class="android.widget.Button" package="{package}" clickable="true"
                  enabled="true" scrollable="false" checkable="false" checked="false"
                  password="false" selected="false" bounds="[20,460][1060,600]" />'''
        )
    private_class = "android.widget.EditText" if editable else "android.widget.TextView"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="root" class="android.widget.FrameLayout"
        package="{package}" clickable="false" enabled="true" scrollable="false"
        checkable="false" checked="false" password="false" selected="false"
        bounds="[0,0][1080,2400]">
    <node index="0" text="{private_text}" resource-id="{package}:id/private_value"
          class="{private_class}" package="{package}" clickable="false"
          enabled="true" scrollable="false" checkable="false" checked="false"
          password="false" selected="false" bounds="[20,120][1060,260]" />
    {''.join(controls)}
  </node>
</hierarchy>'''.encode("utf-8")


def _privacy_local_test_sink(root: Path, run_id: str):
    return collector.RealObservationSink(
        root,
        run_id,
        resume=False,
        manifest={
            "run_id": run_id,
            "created_at": collector.utc_now(),
            "api_base_url": "http://forbidden",
            "run_mode": "real_device_observation",
            "collection_mode": "safe_explore",
            "app_statuses": [],
        },
    )


def test_runtime_postal_address_uses_zero_api_local_baemin_gateway() -> None:
    package = "com.sampleapp"
    first_address = "서울특별시 강남구 테헤란로 123"
    second_address = "서울특별시 송파구 올림픽로 300"
    gateway_label = "마이배민"
    first = _capture(
        _dynamic_private_surface_xml(
            package,
            first_address,
            safe_gateway=True,
            final_control=True,
        ),
        package=package,
    )
    second = _capture(
        _dynamic_private_surface_xml(package, second_address),
        package=package,
    )
    assert collector.assess_privacy(first.tree).metadata_only is True
    task = collector.CollectionTask(
        package,
        "Baemin privacy-local fixture",
        collector.DYNAMIC_INVENTORY_PROFILE,
        collector.NEUTRAL_INVENTORY_GOAL,
    )
    api_calls = 0

    def forbidden_transport(*_args):
        nonlocal api_calls
        api_calls += 1
        raise AssertionError("runtime-private screen crossed the external API boundary")

    with tempfile.TemporaryDirectory() as temporary:
        sink = _privacy_local_test_sink(Path(temporary), "runtime-postal-baemin")
        adb = SequenceAdb((first, second))
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient(
                "http://forbidden", transport=forbidden_transport
            ),
            sink,
            collector.ExplorationBudget(max_actions=3, settle_seconds=0),
            capture_only=False,
            discovery_explore=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        status = runner.run_task(task)
        assert status == "discovery_frontier_exhausted"
        assert api_calls == 0
        assert len([value for value in adb.actions if value.startswith("tap:")]) == 1
        assert not any(value.startswith("scroll:") for value in adb.actions)
        assert sink.action_safety_counts() == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }

        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            screens = [
                json.loads(row[0])
                for row in connection.execute("SELECT payload_json FROM screens")
            ]
            transitions = [
                json.loads(row[0])
                for row in connection.execute("SELECT payload_json FROM transitions")
            ]
            metrics = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT payload_json FROM metrics "
                    "WHERE metric_dimension='sensitive_local_policy'"
                )
            ]
        finally:
            connection.close()

        assert len(screens) == 2
        assert all(screen["privacy_verified"] is False for screen in screens)
        assert all(screen["evidence_mode"] == "metadata_only" for screen in screens)
        assert all(screen.get("accessibility_tree_path") is None for screen in screens)
        assert all(screen["forced_dynamic_metadata_only"] is False for screen in screens)
        assert len(transitions) == 1
        transition = transitions[0]
        assert transition["selected_label"] == collector.SENSITIVE_GUARD_LABEL_BUCKET
        assert transition["sensitive_local_only"] is True
        assert transition["is_final_action"] is False
        assert transition["unsafe_action"] is False
        selected = next(
            metric["local_decision"]
            for metric in metrics
            if metric.get("policy_event") == "sensitive_local_safe_menu_selected"
        )
        assert selected["matched_signal_ids"] == ["gateway.profile"]
        assert len(selected["semantic_commitment_sha256"]) == 64
        assert selected["human_text_persisted"] is False
        assert all(metric["external_api_transfer_count"] == 0 for metric in metrics)
        for path in sink.run_directory.rglob("*"):
            if not path.is_file():
                continue
            payload = path.read_bytes()
            assert first_address.encode("utf-8") not in payload, path
            assert second_address.encode("utf-8") not in payload, path
            assert gateway_label.encode("utf-8") not in payload, path
        assert not list(sink.run_directory.rglob("*.xml"))


def test_runtime_private_surface_without_safe_gateway_stops_zero_api() -> None:
    package = "com.sampleapp"
    private_text = "서울특별시 강남구 선릉로 456"
    capture = _capture(
        _dynamic_private_surface_xml(
            package,
            private_text,
            final_control=True,
        ),
        package=package,
    )
    calls = 0

    def forbidden_transport(*_args):
        nonlocal calls
        calls += 1
        raise AssertionError("runtime-private screen called API")

    task = collector.CollectionTask(
        package,
        "Private screen fixture",
        collector.DYNAMIC_INVENTORY_PROFILE,
        collector.NEUTRAL_INVENTORY_GOAL,
    )
    with tempfile.TemporaryDirectory() as temporary:
        sink = _privacy_local_test_sink(Path(temporary), "runtime-private-no-gateway")
        adb = CaptureOnlyAdb(capture)
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient("http://forbidden", transport=forbidden_transport),
            sink,
            collector.ExplorationBudget(max_actions=2, settle_seconds=0),
            capture_only=False,
            discovery_explore=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        assert runner.run_task(task) == "discovery_frontier_exhausted"
        assert calls == 0
        assert not any(value.startswith("tap:") for value in adb.actions)
        assert sink.action_safety_counts() == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }
        checkpoint = sink.load_checkpoint()
        assert checkpoint["state"]["external_api_transfer_count"] == 0
        for path in sink.run_directory.rglob("*"):
            if path.is_file():
                assert private_text.encode("utf-8") not in path.read_bytes(), path


def test_runtime_editable_private_surface_remains_local_user_boundary() -> None:
    package = "com.sampleapp"
    private_text = "SensitiveInputCanary"
    capture = _capture(
        _dynamic_private_surface_xml(
            package,
            private_text,
            safe_gateway=True,
            editable=True,
        ),
        package=package,
    )
    privacy = collector.assess_privacy(capture.tree)
    assert privacy.metadata_only is True
    assert "editable_field" in privacy.reasons
    assert collector.classify_sensitive_surface_boundary(
        capture.tree.elements
    ) == "authentication_or_input_boundary"
    task = collector.CollectionTask(
        package,
        "Editable boundary fixture",
        collector.DYNAMIC_INVENTORY_PROFILE,
        collector.NEUTRAL_INVENTORY_GOAL,
    )
    with tempfile.TemporaryDirectory() as temporary:
        sink = _privacy_local_test_sink(Path(temporary), "runtime-editable-boundary")
        adb = CaptureOnlyAdb(capture)
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient(
                "http://forbidden",
                transport=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("editable private screen called API")
                ),
            ),
            sink,
            collector.ExplorationBudget(max_actions=2, settle_seconds=0),
            capture_only=False,
            discovery_explore=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        assert runner.run_task(task) == "boundary:authentication_or_input_boundary"
        assert not any(value.startswith("tap:") for value in adb.actions)
        assert sink.action_safety_counts() == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }
        assert not list(sink.run_directory.rglob("*.xml"))
        for path in sink.run_directory.rglob("*"):
            if path.is_file():
                assert private_text.encode("utf-8") not in path.read_bytes(), path


def test_sensitive_insurance_goal_is_local_only_and_destination_is_user_boundary() -> None:
    package = "ni.mh.android.launcher"
    entry_canary = "InsuranceEntryCanary"
    detail_canary = "InsuranceDetailCanary"
    entry_xml = SAFE_XML.replace(b"com.example.app", package.encode()).replace(
        b"Settings", f"보험 계약 조회 {entry_canary}".encode("utf-8")
    )
    detail_xml = SAFE_XML.replace(b"com.example.app", package.encode()).replace(
        b"Settings", f"계약번호 {detail_canary}".encode("utf-8")
    )
    task = collector.CollectionTask(
        package,
        "NH농협손해보험",
        collector.DYNAMIC_INVENTORY_PROFILE,
        "보험 계약 조회",
        sensitivity_categories=("finance", "health_medical"),
        sensitivity_handling="heightened_metadata_only",
        candidate_id="goal_insurance_lookup_candidate",
        family_id="insurance_contract_lookup",
        terminal_policy="user_boundary",
        source_run_id="validated-source-run",
        source_inventory_snapshot_id="inventory-insurance",
        source_artifact_sha256="a" * 64,
    )
    api_calls = 0

    def forbidden_transport(*_args):
        nonlocal api_calls
        api_calls += 1
        raise AssertionError("sensitive insurance semantics crossed the API boundary")

    with tempfile.TemporaryDirectory() as temporary:
        run_id = "sensitive-insurance-lineage"
        sink = collector.RealObservationSink(
            Path(temporary),
            run_id,
            resume=False,
            manifest={
                "run_id": run_id,
                "created_at": collector.utc_now(),
                "api_base_url": "http://forbidden",
                "run_mode": "real_device_observation",
                "collection_mode": "safe_explore",
                "app_statuses": [],
            },
        )
        adb = SequenceAdb(
            (
                _capture(entry_xml, package=package),
                _capture(detail_xml, package=package),
            )
        )
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient("http://forbidden", transport=forbidden_transport),
            sink,
            collector.ExplorationBudget(max_actions=3, settle_seconds=0),
            capture_only=False,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        status = runner.run_task(task)
        assert status.startswith("boundary:")
        assert status != "destination_reached"
        assert api_calls == 0
        assert len([value for value in adb.actions if value.startswith("tap:")]) == 1
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            transition = json.loads(
                connection.execute("SELECT payload_json FROM transitions").fetchone()[0]
            )
            metrics = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT payload_json FROM metrics WHERE metric_dimension='sensitive_local_policy'"
                )
            ]
        finally:
            connection.close()
        decision = next(
            value["local_decision"]
            for value in metrics
            if value.get("local_decision")
        )
        assert decision["goal_family_id"] == "insurance_contract_lookup"
        assert decision["terminal_policy"] == "user_boundary"
        assert decision["matched_signal_ids"] == ["insurance.contract_lookup"]
        assert transition["goal_candidate_id"] == "goal_insurance_lookup_candidate"
        assert transition["goal_family_id"] == "insurance_contract_lookup"
        assert transition["selected_label"] == collector.SENSITIVE_GUARD_LABEL_BUCKET
        assert transition["is_final_action"] is False
        assert transition["unsafe_action"] is False
        assert sink.action_safety_counts() == {
            "unsafe_auto_click_count": 0,
            "final_action_auto_click_count": 0,
        }
        for path in sink.run_directory.rglob("*"):
            if path.is_file():
                payload = path.read_bytes()
                assert entry_canary.encode() not in payload, path
                assert detail_canary.encode() not in payload, path


def test_sensitive_pending_action_resumes_without_replay_or_raw_semantics() -> None:
    package = "kr.or.nhic"
    entry_canary = "SensitiveResumeEntryCanary"
    resume_canary = "SensitiveResumeDestinationCanary"
    entry_xml = SAFE_XML.replace(b"com.example.app", package.encode()).replace(
        b"Settings", f"보험 계약 조회 {entry_canary}".encode("utf-8")
    )
    destination_xml = SAFE_XML.replace(b"com.example.app", package.encode()).replace(
        b"Settings", f"계약번호 {resume_canary}".encode("utf-8")
    )
    task = collector.CollectionTask(
        package,
        "The건강보험",
        collector.DYNAMIC_INVENTORY_PROFILE,
        "보험 계약 조회",
        sensitivity_categories=("health_medical",),
        candidate_id="goal_resume_insurance",
        family_id="insurance_contract_lookup",
        terminal_policy="user_boundary",
    )
    with tempfile.TemporaryDirectory() as temporary:
        run_id = "sensitive-resume-no-replay"
        sink = collector.RealObservationSink(
            Path(temporary),
            run_id,
            resume=False,
            manifest={
                "run_id": run_id,
                "created_at": collector.utc_now(),
                "api_base_url": "http://forbidden",
                "run_mode": "real_device_observation",
                "collection_mode": "safe_explore",
                "app_statuses": [],
            },
        )
        first_adb = CrashAfterFirstCaptureAdb(_capture(entry_xml, package=package))
        first_runner = collector.PhysicalExplorationRunner(
            first_adb,
            collector.ObserveApiClient(
                "http://forbidden",
                transport=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("sensitive task called API")
                ),
            ),
            sink,
            collector.ExplorationBudget(max_actions=3, settle_seconds=0),
            capture_only=False,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        try:
            first_runner.run_task(task)
        except RuntimeError as error:
            assert str(error) == "synthetic process boundary"
        else:
            raise AssertionError("synthetic process boundary did not interrupt collection")
        checkpoint = sink.load_checkpoint()
        pending = checkpoint["state"]["pending_action"]
        assert pending["sensitive_local_only"] is True
        assert pending["selected_label"] == collector.SENSITIVE_GUARD_LABEL_BUCKET

        invalid_state = json.loads(json.dumps(checkpoint["state"]))
        invalid_state["pending_action"]["raw_accessibility_label"] = "ForbiddenResumeRaw"
        invalid = collector.restore_physical_exploration_state(
            invalid_state, "sensitive-fallback"
        )
        try:
            collector.validate_sensitive_resume_state(invalid)
        except ValueError as error:
            assert "raw or unknown fields" in str(error)
        else:
            raise AssertionError("sensitive resume accepted an unknown raw field")

        resume_adb = CaptureOnlyAdb(_capture(destination_xml, package=package))
        resumed_runner = collector.PhysicalExplorationRunner(
            resume_adb,
            collector.ObserveApiClient(
                "http://forbidden",
                transport=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("sensitive resume called API")
                ),
            ),
            sink,
            collector.ExplorationBudget(max_actions=3, settle_seconds=0),
            capture_only=True,
            dry_run=False,
            launch_app=True,
            screenshot_policy="none",
        )
        assert resumed_runner.run_task(task, resume_state=checkpoint["state"]) == "captured"
        assert not any(
            action.startswith(("tap:", "scroll:", "back", "launch:"))
            for action in resume_adb.actions
        )
        transitions = [
            json.loads(line)
            for line in (sink.run_directory / "transitions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        assert len(transitions) == 1
        assert transitions[0]["outcome"] == "unknown_after_process_boundary"
        assert transitions[0]["success"] is False
        assert sink.load_checkpoint()["state"]["pending_action"] is None
        for path in sink.run_directory.rglob("*"):
            if path.is_file():
                payload = path.read_bytes()
                assert entry_canary.encode() not in payload, path
                assert resume_canary.encode() not in payload, path


def _planned_goal(
    package: str,
    *,
    candidate_id: str,
    family_id: str,
    goal_text: str,
    rank: int,
    version_name: str,
    version_code: str,
    categories: tuple[str, ...] = (),
) -> object:
    return collector.PlannedGoal(
        app_package=package,
        version_name=version_name,
        version_code=version_code,
        version_key=f"code:{version_code}|name:{version_name}",
        sensitivity_categories=categories,
        sensitivity_handling=(
            "heightened_metadata_only" if categories else "standard_metadata_only"
        ),
        candidate_id=candidate_id,
        family_id=family_id,
        goal_text=goal_text,
        terminal_policy="navigation_only",
        rank=rank,
        confidence=0.9,
        source_run_id="source-run",
        source_inventory_snapshot_id="inventory-unit-new-updated",
    )


def test_goal_plans_join_in_inventory_priority_and_preserve_cli_limits() -> None:
    snapshot = _dynamic_snapshot_document()
    plan = collector.GoalTaskPlan(
        source_run_id="source-run",
        source_inventory_snapshot_id="inventory-unit-new-updated",
        source_artifact_sha256="a" * 64,
        applicable=(
            _planned_goal(
                "com.example.updated",
                candidate_id="candidate-updated",
                family_id="customer_support",
                goal_text="고객센터",
                rank=1,
                version_name="3.1",
                version_code="31",
            ),
            _planned_goal(
                "com.example.new",
                candidate_id="candidate-new",
                family_id="privacy_settings",
                goal_text="개인정보 설정",
                rank=1,
                version_name="2.0",
                version_code="20",
                categories=("conversation_message",),
            ),
        ),
        state_counts={"applicable": 2},
    )
    tasks = collector.dynamic_goal_tasks(snapshot, plan)
    assert [task.app_package for task in tasks] == [
        "com.example.new",
        "com.example.updated",
    ]
    assert [task.candidate_id for task in tasks] == [
        "candidate-new",
        "candidate-updated",
    ]
    assert all(task.source_artifact_sha256 == "a" * 64 for task in tasks)
    assert [task.app_package for task in collector.dynamic_goal_tasks(
        snapshot, plan, max_apps=1
    )] == ["com.example.new"]
    assert [task.app_package for task in collector.dynamic_goal_tasks(
        snapshot, plan, only_packages=["com.example.updated"]
    )] == ["com.example.updated"]

    parser = collector.build_parser()
    neutral_args = parser.parse_args(
        ["--inventory-snapshot", "inventory.json", "--capture-only"]
    )
    neutral_args._loaded_inventory_snapshot = snapshot
    assert all(
        task.goal_text == collector.NEUTRAL_INVENTORY_GOAL
        for task in collector.tasks_from_arguments(neutral_args)
    )
    discovery_args = parser.parse_args(
        ["--inventory-snapshot", "inventory.json", "--discovery-explore"]
    )
    discovery_args._loaded_inventory_snapshot = snapshot
    assert len(collector.tasks_from_arguments(discovery_args)) == 2

    for arguments, expected in (
        (["--inventory-snapshot", "inventory.json"], "requires --goal-candidates"),
        (
            [
                "--inventory-snapshot",
                "inventory.json",
                "--capture-only",
                "--goal-candidates",
                "goals.json",
                "--family-manifest",
                "families.json",
            ],
            "--capture-only rejects",
        ),
        (
            [
                "--inventory-snapshot",
                "inventory.json",
                "--discovery-explore",
                "--goal-candidates",
                "goals.json",
                "--family-manifest",
                "families.json",
            ],
            "mutually exclusive",
        ),
    ):
        args = parser.parse_args(arguments)
        args._loaded_inventory_snapshot = snapshot
        try:
            collector.tasks_from_arguments(args)
        except ValueError as error:
            assert expected in str(error)
        else:
            raise AssertionError(f"unsafe dynamic task mode accepted: {arguments}")

    calls: list[tuple[tuple[str, ...], int]] = []
    original = collector.plan_applicable_goals

    def fake_planner(*_args, only_packages=(), max_goals_per_app=0, **_kwargs):
        calls.append((tuple(only_packages), max_goals_per_app))
        return plan

    collector.plan_applicable_goals = fake_planner
    try:
        goal_args = parser.parse_args(
            [
                "--inventory-snapshot",
                "inventory.json",
                "--goal-candidates",
                "goals.json",
                "--family-manifest",
                "families.json",
                "--only-package",
                "com.example.updated",
                "--max-apps",
                "1",
                "--max-goals-per-app",
                "1",
            ]
        )
        goal_args._loaded_inventory_snapshot = snapshot
        selected = collector.tasks_from_arguments(goal_args)
    finally:
        collector.plan_applicable_goals = original
    assert calls == [(('com.example.updated',), 1)]
    assert [task.candidate_id for task in selected] == ["candidate-updated"]


def test_goal_lineage_is_in_manifest_goal_evidence_and_resume_contract() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        artifact = root / "goal-candidates.json"
        families = root / "families.json"
        artifact.write_bytes(b"goal-artifact")
        families.write_bytes(b"family-manifest")
        artifact_sha = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
        goal = _planned_goal(
            "com.example.updated",
            candidate_id="candidate-updated",
            family_id="customer_support",
            goal_text="고객센터",
            rank=1,
            version_name="3.1",
            version_code="31",
        )
        plan = collector.GoalTaskPlan(
            source_run_id="source-run",
            source_inventory_snapshot_id="inventory-unit-new-updated",
            source_artifact_sha256=artifact_sha,
            applicable=(goal,),
            state_counts={"applicable": 1, "unverified": 3},
        )
        snapshot_path = root / "device-inventory" / "inventory-goal-evidence.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(_dynamic_snapshot_document(), ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        snapshot = collector.load_dynamic_inventory_snapshot(snapshot_path)
        task = collector.dynamic_goal_tasks(snapshot, plan)[0]
        metadata = collector.dynamic_goal_plan_manifest_metadata(
            plan,
            artifact_path=artifact,
            family_manifest_path=families,
            observation_root=root,
            tasks=[task],
        )
        assert metadata["artifact"]["sha256"] == artifact_sha
        assert metadata["selected_candidate_ids"] == ["candidate-updated"]
        assert metadata["selection"][0]["terminal_policy"] == "navigation_only"

        inventory_metadata = collector.dynamic_inventory_manifest_metadata(
            snapshot,
            observation_root=root,
            run_id="goal-evidence",
            selected_packages=[task.app_package],
        )
        inventory_metadata.update(
            {
                "exploration_stage": collector.EXPLORATION_STAGE_GOAL_DIRECTED,
                "goal_candidate_plan": metadata,
                "selected_tasks": [
                    collector.asdict(task) | {"task_id": task.task_id}
                ],
            }
        )
        existing = {
            "validation_profile": collector.DYNAMIC_INVENTORY_PROFILE,
            "inventory_snapshot": inventory_metadata,
            "selected_packages": ["com.example.updated"],
            "inventory_packages": ["com.example.updated"],
            "exploration_stage": collector.EXPLORATION_STAGE_GOAL_DIRECTED,
            "goal_candidate_plan": metadata,
        }
        collector.validate_dynamic_resume_lineage(
            existing,
            inventory_snapshot_metadata=inventory_metadata,
            selected_packages=["com.example.updated"],
            inventory_packages=["com.example.updated"],
            exploration_stage=collector.EXPLORATION_STAGE_GOAL_DIRECTED,
            goal_candidate_plan=metadata,
        )
        # Persisting JSON converts dataclass tuple fields to arrays. Resume
        # compares the canonical JSON value, not Python tuple/list identity.
        persisted = json.loads(json.dumps(existing))
        collector.validate_dynamic_resume_lineage(
            persisted,
            inventory_snapshot_metadata=inventory_metadata,
            selected_packages=["com.example.updated"],
            inventory_packages=["com.example.updated"],
            exploration_stage=collector.EXPLORATION_STAGE_GOAL_DIRECTED,
            goal_candidate_plan=metadata,
        )
        tampered = json.loads(json.dumps(persisted))
        tampered["goal_candidate_plan"]["artifact"]["sha256"] = "0" * 64
        try:
            collector.validate_dynamic_resume_lineage(
                tampered,
                inventory_snapshot_metadata=inventory_metadata,
                selected_packages=["com.example.updated"],
                inventory_packages=["com.example.updated"],
                exploration_stage=collector.EXPLORATION_STAGE_GOAL_DIRECTED,
                goal_candidate_plan=metadata,
            )
        except ValueError as error:
            assert "lineage mismatch" in str(error)
        else:
            raise AssertionError("tampered goal artifact hash was accepted on resume")

        sink = collector.RealObservationSink(
            root,
            "goal-evidence",
            resume=False,
            manifest={
                "run_id": "goal-evidence",
                "created_at": collector.utc_now(),
                "api_base_url": "http://local",
                "collection_mode": "safe_explore",
                "validation_profile": collector.DYNAMIC_INVENTORY_PROFILE,
                "selected_packages": [task.app_package],
                "inventory_packages": sorted(
                    str(item["package"]) for item in snapshot["included_apps"]
                ),
                "inventory_snapshot": inventory_metadata,
                "exploration_stage": collector.EXPLORATION_STAGE_GOAL_DIRECTED,
                "goal_candidate_plan": metadata,
                "app_statuses": [],
            },
        )
        sink.register_goal(task)
        sink.finalize("completed")
        goal_row = json.loads(
            (sink.run_directory / "goals.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        evidence = goal_row["evidence"]
        assert evidence["candidate_id"] == "candidate-updated"
        assert evidence["family_id"] == "customer_support"
        assert evidence["source_run_id"] == "source-run"
        assert evidence["source_artifact_sha256"] == artifact_sha
        control = json.loads((sink.run_directory / "manifest.json").read_text(encoding="utf-8"))
        assert control["exploration_stage"] == collector.EXPLORATION_STAGE_GOAL_DIRECTED
        assert control["goal_candidate_plan"] == metadata


class _MemorySink:
    def __init__(self, root: Path) -> None:
        self.run_id = "memory-run"
        self.run_directory = root
        self.records: list[tuple[str, dict[str, object]]] = []
        self.checkpoint_state: dict[str, object] = {}

    def register_app_metadata(self, *_args, **_kwargs):
        return None

    def register_app(self, *_args, **_kwargs):
        return None

    def register_goal(self, task):
        return "goal_" + task.task_id

    def set_app_status(self, *_args, **_kwargs):
        return None

    def append(self, kind, payload, *, record_id, **_kwargs):
        del record_id
        self.records.append((kind, dict(payload)))

    def mirror_graph_observation(self, *_args, **_kwargs):
        return None

    def load_checkpoint(self):
        return dict(self.checkpoint_state)

    def checkpoint(self, value):
        self.checkpoint_state = dict(value)

    def action_safety_counts(self):
        return {"unsafe_auto_click_count": 0, "final_action_auto_click_count": 0}


def test_resume_closes_pending_as_unknown_without_replaying_and_restores_scroll_novelty() -> None:
    guard = collector.evaluate_auto_action_guard(
        "click",
        selected_label="Settings",
        element_labels=("Settings",),
        resource_id="com.example.app:id/settings",
    )
    assert guard.allowed is True
    pending = {
        "transition_id": "transition-before-restart",
        "source_screen_id": "screen-before-restart",
        "source_observation_id": "observation-before-restart",
        "app_package": "com.example.app",
        "goal_id": "goal-before-restart",
        "action_type": "click",
        "element_id": "screen-before-restart:adb_one",
        "ui_element_id": "adb_one",
        "selected_label": "Settings",
        "auto_action_guard": guard.evidence(),
        "local_from_signature": "old-signature",
        "server_from_fingerprint": "us_old",
        "performed_at_epoch_ms": 1.0,
    }
    resume_state = {
        "session_id": "physical-session",
        "action_count": 1,
        "scroll_count": 1,
        "back_count": 0,
        "screen_visits": {"old-signature": 1},
        "pending_action": pending,
        "external_api_transfer_count": 2,
        "scroll_novelty_label_sets": [["settings", "account"]],
    }
    restored = collector.restore_physical_exploration_state(
        resume_state, "fallback-session"
    )
    assert restored.pending_action["resumed_after_process_boundary"] is True
    assert restored.external_api_transfer_count == 2
    assert restored.scroll_novelty_label_sets == [{"settings", "account"}]

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sink = _MemorySink(root)
        adb = CaptureOnlyAdb(_capture())
        runner = collector.PhysicalExplorationRunner(
            adb,
            collector.ObserveApiClient(
                "http://forbidden",
                transport=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("capture-only called API")
                ),
            ),
            sink,
            collector.ExplorationBudget(max_actions=4, settle_seconds=0),
            capture_only=True,
            dry_run=False,
            launch_app=True,
            screenshot_policy="none",
        )
        task = collector.CollectionTask(
            "com.example.app", "Example", "test", "설정 찾기"
        )
        assert runner.run_task(task, resume_state=resume_state) == "captured"
        assert not any(action.startswith(("tap:", "scroll:", "back")) for action in adb.actions)
        assert not any(action.startswith("launch:") for action in adb.actions)
        transitions = [payload for kind, payload in sink.records if kind == "transition"]
        assert len(transitions) == 1
        assert transitions[0]["outcome"] == "unknown_after_process_boundary"
        assert transitions[0]["success"] is False
        assert sink.checkpoint_state["state"]["pending_action"] is None
        assert sink.checkpoint_state["state"]["scroll_novelty_label_sets"] == [
            ["account", "settings"]
        ]

    invalid = dict(resume_state)
    invalid["pending_action"] = {**pending, "auto_action_guard": {}}
    try:
        collector.restore_physical_exploration_state(invalid, "fallback")
    except ValueError as error:
        assert "guard evidence" in str(error)
    else:
        raise AssertionError("missing pending-action guard was accepted")


def test_neutral_discovery_budget_and_frontier_are_normal_completed_outcomes() -> None:
    task = collector.CollectionTask(
        "com.example.app", "Example", "dynamic_inventory", collector.NEUTRAL_INVENTORY_GOAL
    )
    with tempfile.TemporaryDirectory() as temporary:
        sink = _MemorySink(Path(temporary))
        runner = collector.PhysicalExplorationRunner(
            CaptureOnlyAdb(_capture()),
            collector.ObserveApiClient("http://unused"),
            sink,
            collector.ExplorationBudget(max_actions=1, settle_seconds=0),
            capture_only=False,
            discovery_explore=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        status = runner.run_task(
            task,
            resume_state={
                "session_id": "existing",
                "action_count": 1,
                "scroll_count": 0,
                "back_count": 0,
                "screen_visits": {"seen": 1},
            },
        )
        assert status == "discovery_budget_complete"
        assert status in collector.COMPLETED_TASK_STATUSES
        assert not any(kind == "failure" for kind, _ in sink.records)
        assert any(
            kind == "metric" and payload["metric_dimension"] == "neutral_discovery_coverage"
            for kind, payload in sink.records
        )

    def no_safe_transport(_url, payload, _timeout):
        return {
            "request_id": payload["request_id"],
            "session_id": payload["session_id"],
            "status": "no_safe_action",
            "screen_fingerprint": "us_fixture",
            "goal_interpretation": "neutral menu discovery",
            "decision_mode": "deterministic_fallback",
            "phase": "stopped",
            "candidates": [],
            "recommendation": None,
            "graph_update": {},
            "automation": {
                "action": "none",
                "safe_to_execute": False,
                "reason": "no safe action",
            },
            "warnings": [],
        }

    with tempfile.TemporaryDirectory() as temporary:
        sink = _MemorySink(Path(temporary))
        runner = collector.PhysicalExplorationRunner(
            CaptureOnlyAdb(_capture()),
            collector.ObserveApiClient("http://local", transport=no_safe_transport),
            sink,
            collector.ExplorationBudget(max_actions=3, settle_seconds=0),
            capture_only=False,
            discovery_explore=True,
            dry_run=False,
            launch_app=False,
            screenshot_policy="none",
        )
        assert runner.run_task(task) == "discovery_frontier_exhausted"
        assert not any(kind == "failure" for kind, _ in sink.records)


def test_neutral_discovery_uses_exact_local_gateway_when_model_selects_none() -> None:
    xml = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0"><node index="0" text="" resource-id="root"
 class="android.widget.FrameLayout" package="com.example.app" clickable="false"
 enabled="true" scrollable="false" checkable="false" checked="false"
 password="false" selected="false" bounds="[0,0][1080,2400]">
 <node index="0" text="" content-desc="Additional actions" resource-id=""
  class="android.widget.Button" package="com.example.app" clickable="true"
  enabled="true" scrollable="false" checkable="false" checked="false"
  password="false" selected="false" bounds="[900,100][1040,240]" />
 <node index="1" text="" content-desc="내 페이지" resource-id=""
  class="android.widget.Button" package="com.example.app" clickable="true"
  enabled="true" scrollable="false" checkable="false" checked="false"
  password="false" selected="false" bounds="[800,2200][1060,2380]" />
 <node index="2" text="" content-desc="Profile" resource-id="com.example.app:id/delete_account"
  class="android.widget.Button" package="com.example.app" clickable="true"
  enabled="true" scrollable="false" checkable="false" checked="false"
  password="false" selected="false" bounds="[20,300][500,440]" />
</node></hierarchy>""".encode("utf-8")
    capture = _capture(xml)
    elements = {element.content_description: element for element in capture.tree.elements}

    def candidate(description, key):
        element = elements[description]
        return {
            "element_id": element.element_id,
            "element_key": key,
            "label": description,
            "role": element.role,
            "risk_level": "low",
            "risk_reason": None,
        }

    response = {
        "request_id": "request-neutral-fallback",
        "session_id": "session-neutral-fallback",
        "status": "needs_user_input",
        "screen_fingerprint": "us_1234567890abcdef",
        "goal_interpretation": "neutral menu discovery",
        "decision_mode": "deterministic_fallback",
        "phase": "stopped",
        "candidates": [
            candidate("Additional actions", "ue_actions"),
            candidate("내 페이지", "ue_my_page"),
            candidate("Profile", "ue_delete_account"),
        ],
        "recommendation": {
            "recommendation_id": "ur_1111111111111111",
            "selected_element_id": None,
            "selected_element_key": None,
            "selected_label": None,
            "target_function": "",
            "instruction": "",
            "reason": "no confident candidate",
            "expected_next_screen": "",
            "confidence": 0.0,
            "risk_level": "low",
            "requires_user_confirmation": False,
        },
        "graph_update": {
            "screen_created": True,
            "actions_created": 3,
            "transition_recorded": False,
            "known_screen_count": 1,
            "known_transition_count": 0,
        },
        "automation": {
            "action": "none",
            "safe_to_execute": False,
            "reason": "confidence gate",
        },
        "warnings": [],
    }
    assert collector.user_boundary(capture.tree, capture.package) is None
    assert collector._neutral_gateway_score(elements["내 페이지"], "내 페이지") == 96
    assert collector._neutral_gateway_score(elements["Profile"], "Profile") == 0
    updated = collector.apply_neutral_discovery_fallback(response, capture)
    recommendation = updated["recommendation"]
    assert recommendation["selected_label"] == "내 페이지"
    assert recommendation["selected_element_id"] == elements["내 페이지"].element_id
    assert recommendation["selected_element_id"] != elements["Profile"].element_id
    assert updated["automation"]["action"] == "click"
    assert updated["automation"]["safe_to_execute"] is True
    assert updated["decision_mode"] == "deterministic_fallback"
    schemas, _, _ = collector._graph_runtime()
    schemas.UniversalNavigationObserveResponse.model_validate(updated)
    decision = collector.assess_physical_automation(
        updated, capture, expected_package="com.example.app"
    )
    assert decision.allowed is True
    assert decision.element == elements["내 페이지"]


def test_task_summary_uses_attempt_local_checkpoint_and_never_self_confirms() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        sink = _MemorySink(Path(temporary))
        task = collector.CollectionTask(
            "com.example.app",
            "Example",
            "dynamic_inventory",
            "구독 관리",
            candidate_id="candidate-one",
            family_id="subscription_manage",
            terminal_policy="navigation_only",
            source_run_id="source-run",
            source_inventory_snapshot_id="snapshot-one",
            source_artifact_sha256="a" * 64,
        )
        sink.checkpoint_state = {
            "current_task_id": task.task_id,
            "state": {
                "action_count": 4,
                "scroll_count": 1,
                "back_count": 1,
                "elapsed_seconds": 3.5,
                "screen_visits": {"a": 2},
                "external_api_transfer_count": 3,
            },
        }
        metric = collector.record_task_summary(
            sink, task, "destination_reached", attempt_number=2
        )
        assert metric["candidate_destination_found"] is True
        assert metric["human_confirmed_success"] is None
        assert metric["human_confirmed_false_positive"] is None
        assert "success_count" not in metric and "false_positive_count" not in metric
        assert metric["goal_candidate_id"] == "candidate-one"
        assert metric["goal_family_id"] == "subscription_manage"
        assert metric["external_api_transfer_count"] == 3
        assert metric["attempt_number"] == 2


def main() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"real-device observation collector checks ok ({len(tests)} tests)")


if __name__ == "__main__":
    main()
