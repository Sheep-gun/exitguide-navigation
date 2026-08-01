#!/usr/bin/env python3
"""Safely install the tracked emulator-observation app batch from Google Play.

The installer deliberately avoids fixed coordinates. It opens the app's exact
Play Store package page, verifies that Play Store owns the foreground window,
and clicks only a visible accessibility node whose label is exactly one of the
allow-listed free install/update actions. Authentication, payment, consent,
and error dialogs are never handled automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PLAY_STORE_PACKAGE = "com.android.vending"
INSTALL_LABELS = frozenset({"Install", "설치"})
UPDATE_LABELS = frozenset({"Update", "업데이트"})
READY_LABELS = frozenset({"Open", "열기", "Play", "실행"})
BUSY_LABELS = frozenset({"Cancel", "취소", "Pending", "대기 중", "Installing", "설치 중"})
RESTART_LABELS = frozenset({"Restart", "다시 시작"})
BOUNDARY_TERMS = (
    "성인 인증",
    "본인 인증",
    "휴대전화 인증",
    "verify your age",
    "adult verification",
    "complete account setup",
    "payment method",
    "captcha",
)
BOUNDS_RE = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")
PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")


@dataclass(frozen=True)
class UiAction:
    label: str
    bounds: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, executable: Path, serial: str) -> None:
        self.executable = executable
        self.serial = serial

    def run(self, *args: str, timeout: float = 30.0, check: bool = True) -> str:
        command = [str(self.executable), "-s", self.serial, *args]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if check and completed.returncode != 0:
            raise AdbError(f"adb exited {completed.returncode}: {compact(output)}")
        return output.strip()

    def is_installed(self, package: str) -> bool:
        output = self.run("shell", "pm", "path", package, check=False)
        return output.startswith("package:")

    def foreground_package(self) -> str:
        output = self.run("shell", "dumpsys", "activity", "activities", timeout=15)
        for line in output.splitlines():
            if "mResumedActivity" not in line and "topResumedActivity" not in line:
                continue
            match = re.search(r"\s([A-Za-z0-9_.]+)/", line)
            if match:
                return match.group(1)
        output = self.run("shell", "dumpsys", "window", "windows", timeout=15)
        for line in output.splitlines():
            if "mCurrentFocus" not in line and "mFocusedApp" not in line:
                continue
            match = re.search(r"\s([A-Za-z0-9_.]+)/", line)
            if match:
                return match.group(1)
        return ""

    def open_store_page(self, package: str) -> None:
        self.run(
            "shell",
            "am",
            "start",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            f"market://details?id={package}",
            PLAY_STORE_PACKAGE,
            timeout=20,
        )

    def dump_ui(self) -> str:
        output = self.run("exec-out", "uiautomator", "dump", "/dev/tty", timeout=20)
        start = output.find("<?xml")
        end = output.rfind("</hierarchy>")
        if start < 0 or end < 0:
            raise AdbError(f"uiautomator did not return XML: {compact(output)}")
        return output[start : end + len("</hierarchy>")]

    def tap(self, action: UiAction) -> None:
        x, y = action.center
        self.run("shell", "input", "tap", str(x), str(y), timeout=10)


def compact(value: str, limit: int = 240) -> str:
    return " ".join(value.split())[:limit]


def parse_bounds(value: str) -> tuple[int, int, int, int] | None:
    match = BOUNDS_RE.match(value or "")
    if not match:
        return None
    bounds = tuple(int(part) for part in match.groups())
    left, top, right, bottom = bounds
    if right <= left or bottom <= top:
        return None
    return bounds


def visible_actions(xml_text: str, labels: Iterable[str]) -> list[UiAction]:
    accepted = set(labels)
    root = ET.fromstring(xml_text)
    actions: list[UiAction] = []
    seen: set[tuple[str, tuple[int, int, int, int]]] = set()
    for node in root.iter("node"):
        text = (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()
        if text not in accepted:
            continue
        if node.attrib.get("enabled", "true") != "true":
            continue
        bounds = parse_bounds(node.attrib.get("bounds", ""))
        if bounds is None:
            continue
        key = (text, bounds)
        # Compose commonly exposes the same semantic label on a parent and its
        # TextView child. They describe one control, not an ambiguous choice.
        if key in seen:
            continue
        seen.add(key)
        actions.append(UiAction(label=text, bounds=bounds))
    return actions


def identity_boundary(xml_text: str) -> str | None:
    """Detect a boundary without retaining any field value from the screen."""

    root = ET.fromstring(xml_text)
    normalized_terms: list[str] = []
    has_editable = False
    for node in root.iter("node"):
        class_name = (node.attrib.get("class") or "").lower()
        if class_name.endswith("edittext") or node.attrib.get("password") == "true":
            has_editable = True
        for attribute in ("text", "content-desc", "hint"):
            value = (node.attrib.get(attribute) or "").strip().lower()
            if value:
                normalized_terms.append(value)
    combined = "\n".join(normalized_terms)
    if any(term in combined for term in BOUNDARY_TERMS):
        return "authentication_or_identity_boundary"
    if has_editable and any(term in combined for term in ("이름", "생일", "전화", "name", "birth", "phone")):
        return "personal_identity_input_boundary"
    return None


def load_apps(manifest_path: Path, selected_packages: set[str]) -> list[dict[str, object]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("dataset_role") != "emulator_observation_candidate":
        raise ValueError("manifest dataset_role must be emulator_observation_candidate")
    if payload.get("canonical_catalog_mutation") is not False:
        raise ValueError("installer refuses manifests that permit canonical mutation")
    safety = payload.get("safety_policy") or {}
    if safety.get("install_free_apps_only") is not True:
        raise ValueError("manifest must explicitly restrict installation to free apps")
    apps = []
    for app in payload.get("apps", []):
        package = str(app.get("app_package", ""))
        if not PACKAGE_RE.fullmatch(package):
            raise ValueError(f"invalid package in manifest: {package!r}")
        if selected_packages and package not in selected_packages:
            continue
        apps.append(app)
    return apps


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def wait_for_store(adb: Adb, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if adb.foreground_package() == PLAY_STORE_PACKAGE:
            return True
        time.sleep(0.5)
    return False


def install_one(adb: Adb, app: dict[str, object], *, allow_update: bool, timeout: float) -> dict[str, object]:
    package = str(app["app_package"])
    installed_before = adb.is_installed(package)
    started = time.monotonic()
    result: dict[str, object] = {
        "app_name": app.get("app_name", package),
        "app_package": package,
        "installed_before": installed_before,
        "status": "pending",
        "boundary": None,
    }
    if installed_before and not allow_update:
        result["status"] = "already_installed"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result

    adb.open_store_page(package)
    if not wait_for_store(adb, 15):
        result["status"] = "blocked"
        result["boundary"] = "play_store_not_foreground"
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        return result

    deadline = time.monotonic() + timeout
    clicked = False
    last_labels: list[str] = []
    foreground_misses = 0
    restart_attempts = 0
    while time.monotonic() < deadline:
        if adb.is_installed(package) and clicked:
            result["status"] = "installed"
            break
        foreground = adb.foreground_package()
        if foreground != PLAY_STORE_PACKAGE:
            foreground_misses += 1
            if foreground and foreground_misses >= 3:
                result["status"] = "blocked"
                result["boundary"] = f"unexpected_foreground_package:{foreground}"
                break
            time.sleep(0.75)
            continue
        foreground_misses = 0
        try:
            xml_text = adb.dump_ui()
        except (AdbError, ET.ParseError) as exc:
            result["last_error"] = compact(str(exc))
            time.sleep(1)
            continue

        boundary = identity_boundary(xml_text)
        if boundary:
            result["status"] = "blocked"
            result["boundary"] = boundary
            break

        restart_actions = visible_actions(xml_text, RESTART_LABELS)
        if restart_actions and restart_attempts == 0:
            if len(restart_actions) != 1:
                result["status"] = "blocked"
                result["boundary"] = "ambiguous_play_store_restart_controls"
                break
            adb.tap(restart_actions[0])
            restart_attempts += 1
            time.sleep(3)
            adb.open_store_page(package)
            if not wait_for_store(adb, 15):
                result["status"] = "blocked"
                result["boundary"] = "play_store_restart_failed"
                break
            continue

        ready = visible_actions(xml_text, READY_LABELS)
        if ready and adb.is_installed(package):
            result["status"] = "already_installed" if installed_before and not clicked else "installed"
            break

        allowed = set(INSTALL_LABELS)
        if allow_update:
            allowed.update(UPDATE_LABELS)
        install_actions = visible_actions(xml_text, allowed)
        if install_actions and not clicked:
            # Ambiguity is a safety failure: never guess between multiple controls.
            if len(install_actions) != 1:
                result["status"] = "blocked"
                result["boundary"] = "ambiguous_install_controls"
                break
            adb.tap(install_actions[0])
            clicked = True
            result["clicked_label"] = install_actions[0].label
            result["clicked_bounds"] = list(install_actions[0].bounds)
            time.sleep(1)
            continue

        busy = visible_actions(xml_text, BUSY_LABELS)
        last_labels = [item.label for item in busy + ready + install_actions]
        # When no exact safe action is visible, leave authentication, consent,
        # country availability, and device-compatibility screens to a human.
        if not clicked and not busy:
            result["status"] = "blocked"
            result["boundary"] = "no_exact_free_install_control"
            break
        time.sleep(1.5)
    else:
        result["status"] = "timeout"
        result["boundary"] = "install_timeout"

    result["installed_after"] = adb.is_installed(package)
    result["last_visible_safe_labels"] = last_labels
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    return result


def default_adb() -> Path:
    configured = os.environ.get("ADB", "").strip()
    if configured:
        return Path(configured)
    return Path.home() / "ExitGuideAndroidSdk" / "platform-tools" / "adb.exe"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    repo_root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--manifest",
        type=Path,
        default=repo_root / "fixtures" / "navigation" / "emulator-observation-apps.v1.json",
    )
    parser.add_argument("--adb", type=Path, default=default_adb())
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--package", action="append", default=[], help="Install only this package; repeatable")
    parser.add_argument("--max-apps", type=int, default=0)
    parser.add_argument("--allow-update", action="store_true")
    parser.add_argument("--install-timeout", type=float, default=180.0)
    parser.add_argument(
        "--report",
        type=Path,
        default=repo_root / ".artifacts" / "navigation-observations" / "install-latest.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.adb.is_file():
        raise SystemExit(f"adb executable not found: {args.adb}")
    selected = set(args.package)
    apps = load_apps(args.manifest, selected)
    if args.max_apps > 0:
        apps = apps[: args.max_apps]
    adb = Adb(args.adb, args.serial)
    device_state = adb.run("get-state", timeout=10)
    if device_state.strip() != "device":
        raise SystemExit(f"ADB device is not ready: {device_state}")

    report: dict[str, object] = {
        "schema_version": 1,
        "provenance": "emulator_observation",
        "canonical_catalog_mutation": False,
        "serial": args.serial,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
    }
    atomic_json(args.report, report)
    for index, app in enumerate(apps, start=1):
        name = str(app.get("app_name", app["app_package"]))
        print(f"[{index}/{len(apps)}] {name} ({app['app_package']})", flush=True)
        try:
            result = install_one(adb, app, allow_update=args.allow_update, timeout=args.install_timeout)
        except (AdbError, subprocess.TimeoutExpired, ET.ParseError) as exc:
            result = {
                "app_name": name,
                "app_package": app["app_package"],
                "status": "failed",
                "boundary": "installer_error",
                "error": compact(str(exc)),
            }
        report["results"].append(result)
        atomic_json(args.report, report)
        print(f"  -> {result['status']} ({result.get('boundary') or 'ok'})", flush=True)

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    results = report["results"]
    report["summary"] = {
        "app_count": len(results),
        "installed_or_present": sum(
            item.get("status") in {"installed", "already_installed"} for item in results
        ),
        "blocked": sum(item.get("status") == "blocked" for item in results),
        "failed": sum(item.get("status") in {"failed", "timeout"} for item in results),
    }
    atomic_json(args.report, report)
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
