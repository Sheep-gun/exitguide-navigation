from __future__ import annotations

import re
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "Keep-RealDeviceAwake.ps1"


def _function_body(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^function\s+{re.escape(name)}\s*\{{(.*?)(?=^function\s+|^\$CycleCount\s*=)",
        source,
    )
    assert match is not None, f"missing function: {name}"
    return match.group(1)


def _run_with_fake_adb(state: str) -> tuple[dict[str, object], list[str]]:
    powershell = shutil.which("powershell")
    assert powershell is not None

    with tempfile.TemporaryDirectory(prefix="egl-keepalive-test-") as temp_dir_value:
        temp_dir = Path(temp_dir_value)
        fake_adb = temp_dir / "fake-adb.cmd"
        audit_log = temp_dir / "audit.jsonl"
        call_log = temp_dir / "calls.txt"
        fake_adb.write_text(
            "\r\n".join(
                (
                    "@echo off",
                    "if /I \"%1\"==\"devices\" (",
                    "  echo List of devices attached",
                    "  if /I \"%FAKE_ADB_STATE%\"==\"adb_error\" exit /b 1",
                    "  if /I \"%FAKE_ADB_STATE%\"==\"disconnected\" exit /b 0",
                    "  echo R3CY204GDVE %FAKE_ADB_STATE%",
                    "  exit /b 0",
                    ")",
                    "if /I \"%1\"==\"-s\" (",
                    "  >> \"%FAKE_ADB_CALL_LOG%\" echo %*",
                    "  exit /b 0",
                    ")",
                    "exit /b 1",
                    "",
                )
            ),
            encoding="ascii",
        )
        environment = os.environ.copy()
        environment["FAKE_ADB_STATE"] = state
        environment["FAKE_ADB_CALL_LOG"] = str(call_log)
        subprocess.run(
            (
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT_PATH),
                "-Adb",
                str(fake_adb),
                "-AuditLogPath",
                str(audit_log),
                "-MaxCycles",
                "1",
            ),
            cwd=REPO_ROOT,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        records = [
            json.loads(line)
            for line in audit_log.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        assert len(records) == 1
        calls = call_log.read_text(encoding="ascii").splitlines() if call_log.exists() else []
        return records[0], calls


def main() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8-sig")

    assert '$ExpectedSerial = "R3CY204GDVE"' in source
    assert '$AuditTargetClass = "system_top_safe"' in source
    assert ".artifacts\\runtime\\real-device-keepalive.jsonl" in source
    assert "[ValidateRange(60, 300)]" in source
    assert "[ValidateRange(0, 31)]" in source

    state_body = _function_body(source, "Get-ExpectedDeviceState")
    assert '& $Adb devices' in state_body
    assert '$Parts[0] -cne $ExpectedSerial' in state_body
    assert '"offline" { return "offline" }' in state_body
    assert '"unauthorized" { return "unauthorized" }' in state_body
    assert state_body.count('return "disconnected"') >= 3
    assert ".Trim()" not in re.search(
        r"(?m)^\s*\$State\s*=.*$", source
    ).group(0)

    loop_body = source[source.index("$CycleCount = 0") :]
    device_branch = re.search(
        r'(?ms)if \(\$State -eq "device"\) \{(.*?)^\s*\}', loop_body
    )
    assert device_branch is not None
    assert "stayon" in device_branch.group(1)
    assert "KEYCODE_WAKEUP" in device_branch.group(1)
    assert '"tap"' in device_branch.group(1)
    assert "Invoke-AdbKeepAliveStep" not in loop_body[: device_branch.start()]
    assert "$CycleStartedAt = [DateTimeOffset]::UtcNow" in loop_body
    assert "$ElapsedMilliseconds" in loop_body
    assert "$RemainingMilliseconds" in loop_body
    assert "Start-Sleep -Milliseconds $RemainingMilliseconds" in loop_body
    assert "Start-Sleep -Seconds $IntervalSeconds" not in loop_body

    audit_body = _function_body(source, "Write-KeepAliveAuditRecord")
    required_fields = {
        "timestamp_utc",
        "device_state",
        "input_attempted",
        "stay_awake_succeeded",
        "wake_succeeded",
        "safe_tap_succeeded",
        "target_class",
    }
    for field in required_fields:
        assert re.search(rf"(?m)^\s*{field}\s*=", audit_body), field

    forbidden_audit_tokens = {
        "SafeTouchX",
        "SafeTouchY",
        "$Serial",
        "package_name",
        "screen",
        "resource_id",
    }
    record_literal = re.search(
        r"(?ms)\$Record\s*=\s*\[ordered\]@\{(.*?)^\s*\}", audit_body
    )
    assert record_literal is not None
    for token in forbidden_audit_tokens:
        assert token not in record_literal.group(1), token

    connected, connected_calls = _run_with_fake_adb("device")
    assert connected["device_state"] == "device"
    assert connected["input_attempted"] is True
    assert connected["stay_awake_succeeded"] is True
    assert connected["wake_succeeded"] is True
    assert connected["safe_tap_succeeded"] is True
    assert connected["target_class"] == "system_top_safe"
    assert len(connected_calls) == 3
    assert any("shell svc power stayon usb" in call for call in connected_calls)
    assert any("shell input keyevent KEYCODE_WAKEUP" in call for call in connected_calls)
    assert any("shell input tap" in call for call in connected_calls)

    for unavailable_state in ("offline", "unauthorized", "disconnected", "adb_error"):
        unavailable, unavailable_calls = _run_with_fake_adb(unavailable_state)
        expected_state = unavailable_state if unavailable_state in {"offline", "unauthorized"} else "disconnected"
        assert unavailable["device_state"] == expected_state
        assert unavailable["input_attempted"] is False
        assert unavailable["stay_awake_succeeded"] is False
        assert unavailable["wake_succeeded"] is False
        assert unavailable["safe_tap_succeeded"] is False
        assert unavailable["target_class"] == "system_top_safe"
        assert unavailable_calls == []

    serialized_audit = json.dumps(connected, ensure_ascii=False, sort_keys=True)
    for forbidden_value in ("R3CY204GDVE", "720", '"8"', "SafeTouchX", "SafeTouchY"):
        assert forbidden_value not in serialized_audit

    print("Keep-RealDeviceAwake safety and fake-ADB behavior checks passed.")


if __name__ == "__main__":
    main()
