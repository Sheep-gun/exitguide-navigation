from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
COLLECTOR_PATH = REPO_ROOT / "scripts" / "Collect-EmulatorObservations.py"
SPEC = importlib.util.spec_from_file_location("egl_emulator_observation_collector", COLLECTOR_PATH)
assert SPEC is not None and SPEC.loader is not None
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


SAMPLE_XML = b"""<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="root" class="android.widget.FrameLayout"
        package="com.example.app" clickable="false" enabled="true" scrollable="false"
        checkable="false" checked="false" password="false" selected="false"
        bounds="[0,0][1080,2400]">
    <node index="0" text="" resource-id="menu" class="android.view.View"
          package="com.example.app" clickable="true" enabled="true" scrollable="false"
          checkable="false" checked="false" password="false" selected="false"
          bounds="[20,100][1060,220]">
      <node index="0" text="Settings" resource-id="menu_label" class="android.widget.TextView"
            package="com.example.app" clickable="false" enabled="true" scrollable="false"
            checkable="false" checked="false" password="false" selected="false"
            bounds="[60,120][500,200]" />
    </node>
    <node index="1" text="" content-desc="Scrollable menu" resource-id="list"
          class="android.widget.ScrollView" package="com.example.app" clickable="false"
          enabled="true" scrollable="true" checkable="false" checked="false"
          password="false" selected="false" bounds="[0,220][1080,2200]" />
    <node index="2" text="secret@example.com" resource-id="email"
          class="android.widget.EditText" package="com.example.app" clickable="true"
          enabled="true" scrollable="false" checkable="false" checked="false"
          password="false" selected="false" bounds="[20,300][1060,440]" />
  </node>
</hierarchy>
"""


def _capture(xml: bytes = SAMPLE_XML, *, package: str = "com.example.app"):
    tree = collector.parse_ui_xml(xml)
    return collector.ScreenCapture(
        capture_id="capture-1",
        captured_at="2026-07-31T00:00:00.000Z",
        package=package,
        activity_name="MainActivity",
        app_version="1.2.3",
        locale="ko-KR",
        tree=tree,
        tree_path=Path("tree.xml"),
        screenshot_path=None,
        capture_ms=10.0,
        screenshot_sha256=None,
        tree_sha256="a" * 64,
    )


def _settings_element(capture):
    return next(element for element in capture.tree.elements if element.clickable and element.inferred_label == "Settings")


def _response(element, *, label: str = "Settings", action: str = "click", safe: bool = True):
    return {
        "status": "guided",
        "phase": "exploring",
        "screen_fingerprint": "us_1234567890abcdef",
        "automation": {
            "action": action,
            "safe_to_execute": safe,
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


def test_xml_parse_and_privacy_redaction() -> None:
    tree = collector.parse_ui_xml(SAMPLE_XML)
    assert tree.package == "com.example.app"
    assert tree.screen_signature.startswith("local_")
    settings = next(element for element in tree.elements if element.clickable and element.inferred_label == "Settings")
    assert settings.label == "Settings"
    assert settings.api_dict()["content_description"] == "Settings"
    assert tree.scroll_bounds == (0, 220, 1080, 2200)
    sensitive = next(element for element in tree.elements if element.resource_id == "email")
    assert sensitive.sensitive is True
    assert sensitive.api_dict()["text"] == "[REDACTED]"
    assert b"secret@example.com" not in tree.sanitized_xml
    assert b"[REDACTED]" in tree.sanitized_xml


def test_local_guard_allows_only_low_risk_navigation() -> None:
    capture = _capture()
    settings = _settings_element(capture)
    allowed = collector.assess_automation(
        _response(settings), capture, expected_package="com.example.app"
    )
    assert allowed.allowed is True
    assert allowed.reason == "low_risk_navigation"

    mismatch = _response(settings)
    mismatch["automation"]["selected_element_id"] = "different"
    assert collector.assess_automation(mismatch, capture, expected_package="com.example.app").reason == "selection_mismatch"

    unsafe_server = _response(settings, safe=False)
    assert collector.assess_automation(unsafe_server, capture, expected_package="com.example.app").reason == "server_did_not_authorize"

    external = _capture(package="com.android.chrome")
    assert collector.assess_automation(
        _response(_settings_element(external)), external, expected_package="com.example.app"
    ).reason == "external_package_boundary"


def test_final_login_captcha_and_input_controls_are_never_clicked() -> None:
    capture = _capture()
    settings = _settings_element(capture)
    final = collector.assess_automation(
        _response(settings, label="회원 탈퇴하기"), capture, expected_package="com.example.app"
    )
    assert final.allowed is False
    assert final.reason == "consequential_final_action"

    login = collector.assess_automation(
        _response(settings, label="로그인"), capture, expected_package="com.example.app"
    )
    assert login.allowed is False
    assert login.reason == "authentication_boundary"

    captcha_xml = SAMPLE_XML.replace(b"Settings", b"Verify you are human CAPTCHA")
    captcha_capture = _capture(captcha_xml)
    assert collector.screen_boundary(captcha_capture.tree) == "captcha_boundary"

    editable = next(element for element in capture.tree.elements if element.role == "text_field")
    edit_response = _response(editable, label="Email")
    blocked = collector.assess_automation(edit_response, capture, expected_package="com.example.app")
    assert blocked.allowed is False
    assert blocked.reason == "state_or_input_control"


def test_near_page_scroll_and_infinite_feed_guard() -> None:
    x1, y1, x2, y2 = collector.page_scroll_points((0, 200, 1080, 2200))
    assert x1 == x2 == 540
    assert y1 > y2
    assert y1 - y2 >= 1400

    menu_guard = collector.InfiniteFeedGuard(max_scrolls=2)
    menu_capture = _capture()
    first = menu_guard.assess_scroll(menu_capture.tree)
    assert first.allowed is True
    menu_guard.note_scroll(menu_capture.tree)
    repeated = menu_guard.assess_scroll(menu_capture.tree)
    assert repeated.allowed is False
    assert repeated.reason == "repeated_or_no_novel_content"

    feed_xml = SAMPLE_XML.replace(
        b"Settings", b"For you timeline posts from people you follow"
    )
    feed_tree = collector.parse_ui_xml(feed_xml)
    feed_guard = collector.InfiniteFeedGuard()
    assert feed_guard.classify(feed_tree) == "infinite_feed"
    assert feed_guard.assess_scroll(feed_tree).allowed is False


def test_budget_and_resume_state() -> None:
    budget = collector.ExplorationBudget(max_actions=2, max_seconds=60, max_backs=2)
    state = collector.ExplorationState(session_id="session", action_count=2)
    assert state.budget_reason(budget) == "action_budget_exhausted"
    payload = state.checkpoint_dict()
    payload["pending_action"] = {"action_type": "click"}
    resumed = collector.ExplorationState.from_checkpoint(payload, "fallback")
    assert resumed.session_id == "session"
    assert resumed.action_count == 2
    assert resumed.pending_action is None


class FakeAdbRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command, timeout, binary):
        del timeout, binary
        command = list(command)
        self.commands.append(command)
        joined = " ".join(command)
        if "exec-out cat" in joined:
            return SAMPLE_XML
        if "exec-out screencap -p" in joined:
            return b"\x89PNG\r\n\x1a\n" + b"fake"
        if "dumpsys window windows" in joined:
            return b"mCurrentFocus=Window{abc u0 com.example.app/.MainActivity}"
        if "dumpsys package" in joined:
            return b"versionName=1.2.3\n"
        if "getprop persist.sys.locale" in joined:
            return b"ko-KR\n"
        return b"UI hierchary dumped to: /sdcard/test.xml\n"


def test_adb_capture_is_paired_and_raw_evidence_is_not_retained() -> None:
    fake = FakeAdbRunner()
    adb = collector.AdbClient("adb", "emulator-5554", runner=fake)
    with tempfile.TemporaryDirectory() as temporary:
        app_directory = Path(temporary) / "app"
        app_directory.mkdir()
        capture = adb.capture_pair(app_directory, "paired", screenshot_policy="none")
        assert capture.package == "com.example.app"
        assert capture.activity_name == ".MainActivity"
        assert capture.tree_path.exists()
        assert capture.screenshot_path is None
        assert b"secret@example.com" not in capture.tree_path.read_bytes()
        assert not list(app_directory.rglob("source.png"))
        commands = [" ".join(command) for command in fake.commands]
        assert any("uiautomator dump" in command for command in commands)
        assert any("exec-out cat" in command for command in commands)
        assert any("exec-out screencap -p" in command for command in commands)


def test_api_client_uses_exact_observe_endpoint() -> None:
    calls = []

    def transport(url, payload, timeout):
        calls.append((url, payload, timeout))
        return {"status": "guided"}

    api = collector.ObserveApiClient("http://127.0.0.1:8010/", transport=transport)
    assert api.observe({"request_id": "one"}) == {"status": "guided"}
    assert calls[0][0] == "http://127.0.0.1:8010/v1/navigation/agent/observe"
    assert calls[0][1]["request_id"] == "one"


def test_append_only_sink_and_atomic_checkpoint() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        sink = collector.ObservationSink(
            root,
            "run-one",
            resume=False,
            manifest={"schema_version": 1, "run_id": "run-one"},
        )
        task = collector.CollectionTask("com.example.app", "Example", "test", "open settings")
        capture = _capture()
        sink.register_app(task, capture)
        goal_id = sink.register_goal(task)
        sink.append("observation", {"observation_id": "one", "screen_id": "screen-one"})
        sink.append("observation", {"observation_id": "two", "screen_id": "screen-two"})
        sink.append(
            "element",
            {"screen_id": "screen-one", "element_id": "element-one", "text": "Settings"},
        )
        sink.append(
            "transition",
            {
                "transition_id": "transition-one",
                "source_screen_id": "screen-one",
                "target_screen_id": "screen-two",
                "element_id": "element-one",
                "action_type": "click",
                "outcome": "navigated",
                "reversible": True,
            },
        )
        sink.append(
            "failure",
            {
                "failure_id": "failure-one",
                "app_package": task.app_package,
                "goal_id": goal_id,
                "goal_text": task.goal_text,
                "failure_type": "test_failure",
            },
        )
        sink.append(
            "metric",
            {
                "metric_id": "metric-one",
                "app_package": task.app_package,
                "goal_id": goal_id,
                "metric_type": "test_metric",
                "unsafe_auto_click_count": 0,
                "final_action_auto_click_count": 0,
            },
        )
        sink.append(
            "annotation",
            {
                "annotation_id": "annotation-one",
                "entity_type": "screen",
                "entity_id": "screen-one",
                "label": "screen_type",
                "value": "menu",
                "confidence": 1.0,
            },
        )
        records = [json.loads(line) for line in (sink.run_directory / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
        observation_ids = [
            record.get("observation_id") or record.get("payload", {}).get("observation_id")
            for record in records
            if record.get("record_type") in {None, "screens"}
        ]
        assert observation_ids == ["one", "two"]
        assert all(record["provenance"] == "emulator_observation" for record in records)
        connection = sqlite3.connect(sink.run_directory / "corpus.sqlite")
        try:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
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
            }
        finally:
            connection.close()
        assert all(count >= 1 for count in counts.values()), counts
        checkpoint = {"completed_task_ids": ["task-one"], "state": {"action_count": 2}}
        sink.checkpoint(checkpoint)
        assert sink.load_checkpoint() == checkpoint
        assert not list(sink.run_directory.glob("*.tmp"))
        resumed = collector.ObservationSink(
            root,
            "run-one",
            resume=True,
            manifest={"schema_version": 1, "run_id": "run-one"},
        )
        assert resumed.load_checkpoint() == checkpoint


class DryRunAdb:
    def __init__(self, capture) -> None:
        self.capture = capture
        self.actions: list[str] = []

    def launch(self, package, restart=True):
        self.actions.append(f"launch:{package}:{restart}")

    def capture_pair(self, app_directory, capture_id, screenshot_policy="redacted"):
        del screenshot_policy
        tree_path = Path(app_directory) / "trees" / f"{capture_id}.xml"
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        tree_path.write_bytes(self.capture.tree.sanitized_xml)
        return replace(self.capture, capture_id=capture_id, tree_path=tree_path)

    def tap(self, bounds):
        self.actions.append(f"tap:{bounds}")

    def page_scroll(self, bounds):
        self.actions.append(f"scroll:{bounds}")
        return (540, 2000, 540, 400)

    def back(self):
        self.actions.append("back")


def test_dry_run_calls_policy_but_never_touches_ui() -> None:
    capture = _capture()
    settings = _settings_element(capture)
    api_calls = []

    def transport(url, payload, timeout):
        del url, timeout
        api_calls.append(payload)
        return _response(settings)

    with tempfile.TemporaryDirectory() as temporary:
        sink = collector.ObservationSink(
            Path(temporary),
            "dry-run",
            resume=False,
            manifest={"schema_version": 1, "run_id": "dry-run"},
        )
        adb = DryRunAdb(capture)
        runner = collector.ExplorationRunner(
            adb,
            collector.ObserveApiClient("http://local", transport=transport),
            sink,
            collector.ExplorationBudget(settle_seconds=0),
            screenshot_policy="none",
            capture_only=False,
            dry_run=True,
            restart_app=False,
            launch_app=False,
        )
        task = collector.CollectionTask("com.example.app", "Example", "test", "open settings")
        assert runner.run_task(task) == "dry_run_complete"
        assert api_calls
        assert not any(action.startswith(("tap:", "scroll:", "back")) for action in adb.actions)
        metrics = (sink.run_directory / "metrics.jsonl").read_text(encoding="utf-8")
        assert "dry_run_would_execute" in metrics


def main() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"emulator observation collector checks ok ({len(tests)} tests)")


if __name__ == "__main__":
    main()
