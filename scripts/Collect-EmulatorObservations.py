#!/usr/bin/env python3
"""Collect privacy-safe Android emulator observations for ExitGuide Navigation.

The collector deliberately sits outside the Android application.  It pairs a
UIAutomator tree with a screenshot, submits the *structured* UI tree to the
existing universal-navigation API, and executes only low-risk navigation that
passes a second local safety check.  Final or consequential controls always
remain user-owned.

Typical single-goal run::

    python scripts/Collect-EmulatorObservations.py \
      --package com.google.android.youtube \
      --app-name YouTube \
      --goal "YouTube Premium 구독 관리 화면 찾기"

Capture without calling the API or touching the UI::

    python scripts/Collect-EmulatorObservations.py \
      --package com.google.android.youtube --goal "설정 화면 찾기" \
      --capture-only

The generated run is append-only and resumable under
``.artifacts/navigation-observations/<run-id>``.  It is emulator-observation
evidence only; this script never promotes a canonical catalog or route.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / ".artifacts" / "navigation-observations"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_SERIAL = "emulator-5554"
OBSERVATION_PROVENANCE = "emulator_observation"

_BOUND_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?82[- ]?)?0?1[016789][- ]?\d{3,4}[- ]?\d{4}(?!\d)")
_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{6,}(?!\d)")
_SPACE_RE = re.compile(r"\s+")

CAPTCHA_TERMS = (
    "captcha",
    "recaptcha",
    "로봇이 아닙니다",
    "로봇이 아님",
    "보안 문자",
    "자동입력 방지",
    "사람인지 확인",
    "verify you are human",
    "human verification",
)
AUTH_INPUT_TERMS = (
    "password",
    "passcode",
    "one-time code",
    "verification code",
    "비밀번호",
    "암호",
    "인증번호",
    "인증 코드",
    "otp",
)
AUTH_ACTION_TERMS = (
    "로그인",
    "로그 인",
    "sign in",
    "log in",
    "본인인증",
    "본인 인증",
    "휴대폰 인증",
    "verify identity",
    "authenticate",
)
CONSEQUENTIAL_ACTION_PATTERNS = (
    r"(?:회원|계정).{0,8}(?:탈퇴|삭제)(?:하기|확정|완료)?$",
    r"(?:구독|멤버십|무료\s*체험).{0,8}(?:해지|취소)(?:하기|확정|완료)?$",
    r"(?:자동\s*결제).{0,8}(?:해제|중지)(?:하기|확정|완료)?$",
    r"(?:결제|구매|주문|예약|신청|청구|송금|이체|출금)(?:하기|확정|완료|제출|실행)$",
    r"(?:삭제|탈퇴|해지|취소|환불|제출|동의|철회|발급|청구)(?:하기|확정|완료)$",
    r"^(?:pay|buy|purchase|order|book|reserve|submit|send|transfer|withdraw)(?: now)?$",
    r"(?:delete|close|deactivate) (?:my )?(?:account|profile)(?: now)?$",
    r"(?:cancel|end) (?:my )?(?:subscription|membership|trial)(?: now)?$",
    r"confirm (?:payment|purchase|order|booking|deletion|cancellation|withdrawal)$",
    r"accept(?: and continue)?$",
)
CONSEQUENTIAL_ACTION_RES = tuple(re.compile(pattern, re.IGNORECASE) for pattern in CONSEQUENTIAL_ACTION_PATTERNS)
SYSTEM_BOUNDARY_PACKAGES = {
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.settings",
    "com.google.android.gms",
}
FEED_TERMS = (
    "for you",
    "following",
    "timeline",
    "news feed",
    "shorts",
    "reels",
    "추천 피드",
    "팔로잉",
    "타임라인",
    "게시물",
    "홈 피드",
)
MENU_TERMS = (
    "설정",
    "계정",
    "마이",
    "내 정보",
    "고객센터",
    "도움말",
    "구독",
    "결제 관리",
    "privacy",
    "settings",
    "account",
    "profile",
    "help",
    "support",
    "membership",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def clean_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).replace("\ufeff", "")
    return _SPACE_RE.sub(" ", text).strip()


def normalized_label(value: object) -> str:
    return clean_text(value).casefold()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_hash(value: object, length: int = 20) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:length]


def slug(value: str, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", clean_text(value)).strip("-._")
    return (cleaned[:80] or fallback).lower()


def bool_attr(value: object, default: bool = False) -> bool:
    text = normalized_label(value)
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return default


def parse_bounds(value: str | None) -> tuple[int, int, int, int] | None:
    match = _BOUND_RE.fullmatch(clean_text(value))
    if not match:
        return None
    left, top, right, bottom = (int(part) for part in match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def append_jsonl(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


@dataclass(frozen=True)
class UiElement:
    element_id: str
    parent_id: str | None
    text: str
    content_description: str
    resource_id: str
    class_name: str
    package: str
    bounds: tuple[int, int, int, int] | None
    clickable: bool
    enabled: bool
    visible: bool
    scrollable: bool
    checkable: bool
    checked: bool | None
    selected: bool
    password: bool
    inferred_label: str = ""

    @property
    def label(self) -> str:
        return clean_text(self.text or self.content_description or self.inferred_label or self.resource_id)

    @property
    def role(self) -> str:
        class_name = self.class_name.casefold()
        if "edittext" in class_name:
            return "text_field"
        if "checkbox" in class_name:
            return "checkbox"
        if "switch" in class_name or "toggle" in class_name:
            return "switch"
        if "radiobutton" in class_name:
            return "radio_button"
        if "button" in class_name or self.clickable:
            return "button"
        if "image" in class_name:
            return "image"
        if "text" in class_name:
            return "text"
        if self.scrollable:
            return "scroll_view"
        return "unknown"

    @property
    def sensitive(self) -> bool:
        combined = " ".join((self.text, self.content_description, self.resource_id, self.class_name))
        return bool(
            self.password
            or "edittext" in self.class_name.casefold()
            or _EMAIL_RE.search(combined)
            or _PHONE_RE.search(combined)
            or _LONG_NUMBER_RE.search(combined)
        )

    def api_dict(self) -> dict[str, object]:
        content_description = self.content_description
        if not content_description and self.clickable:
            content_description = self.inferred_label
        payload: dict[str, object] = {
            "id": self.element_id,
            "role": self.role,
            "clickable": self.clickable,
            "enabled": self.enabled,
            "visible": self.visible,
            "scrollable": self.scrollable,
            "checkable": self.checkable,
            "selected": self.selected,
            "password": self.password,
        }
        if self.parent_id:
            payload["parent_id"] = self.parent_id
        if self.text:
            payload["text"] = "[REDACTED]" if self.sensitive else self.text[:500]
        if content_description:
            payload["content_description"] = "[REDACTED]" if self.sensitive else content_description[:500]
        if self.resource_id:
            payload["view_id"] = self.resource_id[:500]
        if self.checkable:
            payload["checked"] = self.checked
        if self.bounds:
            payload["bounds"] = list(self.bounds)
        return payload

    def corpus_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["bounds"] = list(self.bounds) if self.bounds else None
        payload["role"] = self.role
        payload["label"] = "[REDACTED]" if self.sensitive else self.label
        payload["text"] = "[REDACTED]" if self.sensitive else self.text
        payload["content_description"] = "[REDACTED]" if self.sensitive else self.content_description
        payload["privacy_redacted"] = self.sensitive
        return payload


@dataclass(frozen=True)
class ParsedUiTree:
    elements: tuple[UiElement, ...]
    package: str
    screen_signature: str
    visible_labels: tuple[str, ...]
    scroll_bounds: tuple[int, int, int, int] | None
    sensitive_bounds: tuple[tuple[int, int, int, int], ...]
    sanitized_xml: bytes


def _descendant_labels(node: ET.Element, limit: int = 4) -> str:
    labels: list[str] = []
    for descendant in node.iter("node"):
        if descendant is node:
            continue
        label = clean_text(descendant.attrib.get("text") or descendant.attrib.get("content-desc"))
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= limit:
            break
    return " · ".join(labels)[:500]


def parse_ui_xml(xml_data: bytes | str, *, element_limit: int = 500) -> ParsedUiTree:
    """Parse a UIAutomator dump into stable API elements and redacted XML."""

    raw = xml_data.encode("utf-8") if isinstance(xml_data, str) else xml_data
    root = ET.fromstring(raw)
    candidates: list[tuple[ET.Element, str | None, str, int]] = []
    element_by_node: dict[int, str] = {}

    def walk(node: ET.Element, parent_id: str | None, ordinal: int) -> None:
        if node.tag != "node":
            for child_index, child in enumerate(list(node)):
                walk(child, parent_id, child_index)
            return
        attrs = node.attrib
        identity = {
            "parent": parent_id,
            "resource": clean_text(attrs.get("resource-id")),
            "class": clean_text(attrs.get("class")),
            "bounds": clean_text(attrs.get("bounds")),
            "text": clean_text(attrs.get("text"))[:120],
            "description": clean_text(attrs.get("content-desc"))[:120],
            "index": clean_text(attrs.get("index")),
            "ordinal": ordinal,
        }
        element_id = f"adb_{stable_hash(identity)}"
        element_by_node[id(node)] = element_id
        priority = 0
        if bool_attr(attrs.get("clickable")) or bool_attr(attrs.get("scrollable")):
            priority += 100
        if clean_text(attrs.get("text")) or clean_text(attrs.get("content-desc")):
            priority += 40
        if clean_text(attrs.get("resource-id")):
            priority += 20
        if bool_attr(attrs.get("visible-to-user"), default=True):
            priority += 10
        candidates.append((node, parent_id, element_id, priority))
        for child_index, child in enumerate(list(node)):
            walk(child, element_id, child_index)

    walk(root, None, 0)
    if not candidates:
        raise ValueError("UIAutomator tree contains no nodes")

    # Keep interactive and labelled nodes first, while retaining document order
    # inside each priority tier. Parent links to omitted nodes are removed below.
    selected = sorted(enumerate(candidates), key=lambda item: (-item[1][3], item[0]))[:element_limit]
    selected.sort(key=lambda item: item[0])
    retained_ids = {item[1][2] for item in selected}
    elements: list[UiElement] = []
    packages: Counter[str] = Counter()
    sensitive_bounds: list[tuple[int, int, int, int]] = []
    scroll_bounds: list[tuple[int, int, int, int]] = []

    for _, (node, parent_id, element_id, _) in selected:
        attrs = node.attrib
        bounds = parse_bounds(attrs.get("bounds"))
        package = clean_text(attrs.get("package"))
        if package:
            packages[package] += 1
        checked = bool_attr(attrs.get("checked")) if bool_attr(attrs.get("checkable")) else None
        element = UiElement(
            element_id=element_id,
            parent_id=parent_id if parent_id in retained_ids else None,
            text=clean_text(attrs.get("text")),
            content_description=clean_text(attrs.get("content-desc")),
            resource_id=clean_text(attrs.get("resource-id")),
            class_name=clean_text(attrs.get("class")),
            package=package,
            bounds=bounds,
            clickable=bool_attr(attrs.get("clickable")),
            enabled=bool_attr(attrs.get("enabled"), default=True),
            visible=bool_attr(attrs.get("visible-to-user"), default=True),
            scrollable=bool_attr(attrs.get("scrollable")),
            checkable=bool_attr(attrs.get("checkable")),
            checked=checked,
            selected=bool_attr(attrs.get("selected")),
            password=bool_attr(attrs.get("password")),
            inferred_label=_descendant_labels(node),
        )
        elements.append(element)
        if element.sensitive and bounds:
            sensitive_bounds.append(bounds)
        if element.scrollable and bounds:
            scroll_bounds.append(bounds)

    # Redact tree attributes before persistence. Raw XML is never retained.
    for node in root.iter("node"):
        combined = " ".join(
            clean_text(node.attrib.get(key)) for key in ("text", "content-desc", "hint", "resource-id", "class")
        )
        sensitive = (
            bool_attr(node.attrib.get("password"))
            or "edittext" in clean_text(node.attrib.get("class")).casefold()
            or bool(_EMAIL_RE.search(combined) or _PHONE_RE.search(combined) or _LONG_NUMBER_RE.search(combined))
        )
        if sensitive:
            for key in ("text", "content-desc", "hint"):
                if key in node.attrib and node.attrib[key]:
                    node.attrib[key] = "[REDACTED]"
            node.attrib["exitguide-redacted"] = "true"

    visible_labels = tuple(
        element.label for element in elements if element.visible and element.label and not element.sensitive
    )
    package = packages.most_common(1)[0][0] if packages else ""
    signature_payload = [
        {
            "resource": element.resource_id,
            "class": element.class_name,
            "label": normalized_label("[REDACTED]" if element.sensitive else element.label),
            "bounds": element.bounds,
            "clickable": element.clickable,
            "scrollable": element.scrollable,
        }
        for element in elements
        if element.visible
    ]
    signature = f"local_{stable_hash({'package': package, 'elements': signature_payload}, 16)}"
    largest_scroll = max(
        scroll_bounds,
        key=lambda bounds: (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]),
        default=None,
    )
    return ParsedUiTree(
        elements=tuple(elements),
        package=package,
        screen_signature=signature,
        visible_labels=visible_labels,
        scroll_bounds=largest_scroll,
        sensitive_bounds=tuple(sensitive_bounds),
        sanitized_xml=ET.tostring(root, encoding="utf-8", xml_declaration=True),
    )


@dataclass(frozen=True)
class ScreenCapture:
    capture_id: str
    captured_at: str
    package: str
    activity_name: str
    app_version: str
    locale: str
    tree: ParsedUiTree
    tree_path: Path
    screenshot_path: Path | None
    capture_ms: float
    screenshot_sha256: str | None
    tree_sha256: str

    @property
    def title(self) -> str:
        for element in self.tree.elements:
            if element.visible and element.label and not element.sensitive:
                return element.label[:300]
        return self.activity_name[:300]

    def api_screen(self) -> dict[str, object]:
        elements = [element.api_dict() for element in self.tree.elements if element.visible]
        if not elements:
            elements = [{"id": "empty_root", "role": "unknown", "visible": True}]
        return {
            "activity_name": self.activity_name[:300],
            "window_title": self.title,
            "event_type": "emulator_observation",
            "captured_at": self.captured_at,
            "elements": elements[:500],
        }


CommandRunner = Callable[[Sequence[str], float, bool], bytes]


class AdbError(RuntimeError):
    pass


class AdbClient:
    def __init__(
        self,
        executable: str | Path,
        serial: str,
        *,
        runner: CommandRunner | None = None,
    ) -> None:
        self.executable = str(executable)
        self.serial = serial
        self._runner = runner or self._subprocess_runner

    @staticmethod
    def _subprocess_runner(command: Sequence[str], timeout: float, binary: bool) -> bytes:
        del binary  # subprocess always captures bytes; callers decode explicitly.
        try:
            result = subprocess.run(
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AdbError(f"ADB command failed to start: {error}") from error
        if result.returncode != 0:
            error_text = result.stderr.decode("utf-8", errors="replace").strip()
            raise AdbError(f"ADB exited {result.returncode}: {error_text[:500]}")
        return result.stdout

    def run(self, args: Sequence[str], *, timeout: float = 30.0, binary: bool = False) -> bytes:
        command = [self.executable, "-s", self.serial, *args]
        return self._runner(command, timeout, binary)

    def shell(self, *args: str, timeout: float = 30.0) -> str:
        return self.run(["shell", *args], timeout=timeout).decode("utf-8", errors="replace").strip()

    def exec_out(self, *args: str, timeout: float = 30.0) -> bytes:
        return self.run(["exec-out", *args], timeout=timeout, binary=True)

    def assert_ready(self) -> None:
        output = self.run(["get-state"], timeout=10).decode("utf-8", errors="replace").strip()
        if output != "device":
            raise AdbError(f"ADB device {self.serial!r} is not ready: {output!r}")
        boot = self.shell("getprop", "sys.boot_completed", timeout=10)
        if boot != "1":
            raise AdbError(f"ADB device {self.serial!r} has not completed boot")

    def package_installed(self, package: str) -> bool:
        return bool(self.shell("pm", "path", package, timeout=15))

    def launch(self, package: str, *, restart: bool = True) -> None:
        if not self.package_installed(package):
            raise AdbError(f"package is not installed: {package}")
        if restart:
            self.shell("am", "force-stop", package, timeout=15)
        output = self.shell(
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
            timeout=30,
        )
        if "No activities found" in output:
            raise AdbError(f"no launchable activity for {package}")

    def current_window(self) -> tuple[str, str]:
        output = self.shell("dumpsys", "window", "windows", timeout=20)
        patterns = (
            r"mCurrentFocus=Window\{[^}]*\s([A-Za-z0-9_.]+)/(?:[A-Za-z0-9_.$]+)",
            r"mFocusedApp=.*?\s([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)",
        )
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                component_match = re.search(r"([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)", match.group(0))
                if component_match:
                    return component_match.group(1), component_match.group(2)
        activity_output = self.shell("dumpsys", "activity", "activities", timeout=20)
        match = re.search(
            r"(?:topResumedActivity|mResumedActivity)(?:=|:).*?\s"
            r"([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)",
            activity_output,
            re.DOTALL,
        )
        return (match.group(1), match.group(2)) if match else ("", "")

    def app_version(self, package: str) -> str:
        output = self.shell("dumpsys", "package", package, timeout=20)
        match = re.search(r"\bversionName=([^\s]+)", output)
        return clean_text(match.group(1))[:120] if match else ""

    def locale(self) -> str:
        locale = self.shell("getprop", "persist.sys.locale", timeout=10)
        if not locale:
            locale = self.shell("getprop", "ro.product.locale", timeout=10)
        return clean_text(locale or "ko-KR")[:40]

    def tap(self, bounds: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = bounds
        self.shell("input", "tap", str((left + right) // 2), str((top + bottom) // 2), timeout=15)

    def page_scroll(self, bounds: tuple[int, int, int, int] | None) -> tuple[int, int, int, int]:
        start_x, start_y, end_x, end_y = page_scroll_points(bounds)
        self.shell(
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            "420",
            timeout=15,
        )
        return start_x, start_y, end_x, end_y

    def back(self) -> None:
        self.shell("input", "keyevent", "KEYCODE_BACK", timeout=15)

    def capture_pair(
        self,
        app_directory: Path,
        capture_id: str,
        *,
        screenshot_policy: str = "redacted",
    ) -> ScreenCapture:
        """Capture tree + screenshot and commit only after both are valid.

        UIAutomator and screencap cannot be truly simultaneous over ADB.  This
        method makes them an indivisible evidence pair instead: neither final
        artifact is visible until both commands and parsing have succeeded.
        """

        started = time.perf_counter()
        screen_directory = app_directory / "screens"
        tree_directory = app_directory / "trees"
        screen_directory.mkdir(parents=True, exist_ok=True)
        tree_directory.mkdir(parents=True, exist_ok=True)
        remote_path = f"/sdcard/egl-observation-{uuid.uuid4().hex}.xml"
        with tempfile.TemporaryDirectory(prefix="egl-capture-", dir=str(app_directory)) as temporary_name:
            temporary = Path(temporary_name)
            try:
                self.shell("uiautomator", "dump", remote_path, timeout=30)
                raw_xml = self.exec_out("cat", remote_path, timeout=20)
                raw_png = self.exec_out("screencap", "-p", timeout=20)
            finally:
                try:
                    self.shell("rm", "-f", remote_path, timeout=10)
                except AdbError:
                    pass
            if not raw_xml.lstrip().startswith(b"<?xml") and b"<hierarchy" not in raw_xml[:500]:
                raise AdbError("UIAutomator returned invalid XML")
            if not raw_png.startswith(b"\x89PNG\r\n\x1a\n"):
                raise AdbError("screencap returned invalid PNG")
            parsed = parse_ui_xml(raw_xml)
            focus_package, activity = self.current_window()
            package = focus_package or parsed.package
            captured_at = utc_now()
            tree_path = tree_directory / f"{capture_id}.xml"
            screenshot_path: Path | None = None
            screenshot_hash: str | None = None
            atomic_write_bytes(tree_path, parsed.sanitized_xml)
            try:
                if screenshot_policy == "redacted":
                    redacted = _redact_png(raw_png, parsed.sensitive_bounds, temporary)
                    if redacted is not None:
                        screenshot_path = screen_directory / f"{capture_id}.png"
                        atomic_write_bytes(screenshot_path, redacted)
                        screenshot_hash = sha256_bytes(redacted)
                elif screenshot_policy != "none":
                    raise ValueError(f"unsupported screenshot policy: {screenshot_policy}")
            except Exception:
                # Privacy wins over completeness.  Tree evidence remains valid;
                # an unredacted screenshot is never retained on failure.
                screenshot_path = None
                screenshot_hash = None
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return ScreenCapture(
                capture_id=capture_id,
                captured_at=captured_at,
                package=package,
                activity_name=activity,
                app_version=self.app_version(package) if package else "",
                locale=self.locale(),
                tree=parsed,
                tree_path=tree_path,
                screenshot_path=screenshot_path,
                capture_ms=elapsed_ms,
                screenshot_sha256=screenshot_hash,
                tree_sha256=sha256_bytes(parsed.sanitized_xml),
            )


def _redact_png(
    raw_png: bytes,
    sensitive_bounds: Sequence[tuple[int, int, int, int]],
    temporary_directory: Path,
) -> bytes | None:
    """Return a redacted PNG, or None when a safe renderer is unavailable."""

    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        return None
    source = temporary_directory / "source.png"
    destination = temporary_directory / "redacted.png"
    source.write_bytes(raw_png)
    with Image.open(source) as image:
        image.load()
        draw = ImageDraw.Draw(image)
        for left, top, right, bottom in sensitive_bounds:
            draw.rectangle((left, top, right, bottom), fill=(36, 39, 46))
        image.save(destination, format="PNG", optimize=True)
    return destination.read_bytes()


def page_scroll_points(
    bounds: tuple[int, int, int, int] | None,
    *,
    fallback_width: int = 1080,
    fallback_height: int = 2400,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds or (0, 120, fallback_width, fallback_height - 160)
    height = max(1, bottom - top)
    center_x = (left + right) // 2
    # Move roughly 78% of the visible scroll region.  A small overlap preserves
    # context while avoiding the slow half-page behavior of short swipes.
    start_y = bottom - max(8, int(height * 0.08))
    end_y = top + max(8, int(height * 0.14))
    if start_y <= end_y:
        start_y, end_y = bottom - 1, top + 1
    return center_x, start_y, center_x, end_y


class ObserveApiError(RuntimeError):
    pass


ApiTransport = Callable[[str, Mapping[str, object], float], Mapping[str, object]]


class ObserveApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 50.0,
        transport: ApiTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport = transport or self._http_transport

    @staticmethod
    def _http_transport(url: str, payload: Mapping[str, object], timeout: float) -> Mapping[str, object]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_body = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise ObserveApiError(f"observe API HTTP {error.code}: {detail[:1000]}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise ObserveApiError(f"observe API unavailable: {error}") from error
        try:
            decoded = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ObserveApiError("observe API returned invalid JSON") from error
        if not isinstance(decoded, dict):
            raise ObserveApiError("observe API response is not an object")
        return decoded

    def observe(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._transport(
            f"{self.base_url}/v1/navigation/agent/observe",
            payload,
            self.timeout_seconds,
        )


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    action: str
    reason: str
    element: UiElement | None = None


def screen_boundary(tree: ParsedUiTree) -> str | None:
    combined = normalized_label(" ".join(tree.visible_labels))
    if any(term in combined for term in CAPTCHA_TERMS):
        return "captcha_boundary"
    if any(element.password for element in tree.elements):
        return "authentication_boundary"
    editable_labels = " ".join(
        normalized_label(element.label)
        for element in tree.elements
        if element.role == "text_field" or element.password
    )
    if editable_labels and any(term in editable_labels for term in AUTH_INPUT_TERMS):
        return "authentication_boundary"
    return None


def is_consequential_label(label: str) -> bool:
    normalized = normalized_label(label).strip(" .!?:")
    return any(pattern.search(normalized) for pattern in CONSEQUENTIAL_ACTION_RES)


def assess_automation(
    response: Mapping[str, object],
    capture: ScreenCapture,
    *,
    expected_package: str,
) -> SafetyDecision:
    """Apply a fail-closed local guard independently of the API policy."""

    automation = response.get("automation")
    recommendation = response.get("recommendation")
    phase = clean_text(response.get("phase"))
    if not isinstance(automation, Mapping):
        return SafetyDecision(False, "none", "missing_automation")
    action = clean_text(automation.get("action") or "none")
    if action in {"none", "stop"}:
        return SafetyDecision(False, action, f"server_{action}")
    if action not in {"click", "scroll_forward", "back"}:
        return SafetyDecision(False, action, "unsupported_action")
    if not bool(automation.get("safe_to_execute", False)):
        return SafetyDecision(False, action, "server_did_not_authorize")
    if capture.package != expected_package:
        reason = "system_boundary" if capture.package in SYSTEM_BOUNDARY_PACKAGES else "external_package_boundary"
        return SafetyDecision(False, action, reason)
    boundary = screen_boundary(capture.tree)
    if boundary:
        return SafetyDecision(False, action, boundary)
    if phase in {"destination_reached", "guiding", "stopped"}:
        return SafetyDecision(False, action, "terminal_phase")
    if action == "back":
        if phase not in {"exploring", "returning_to_start"}:
            return SafetyDecision(False, action, "back_outside_exploration")
        return SafetyDecision(True, action, "low_risk_back")
    if action == "scroll_forward":
        if phase != "exploring":
            return SafetyDecision(False, action, "scroll_outside_exploration")
        return SafetyDecision(True, action, "low_risk_scroll")
    if phase != "exploring" or not isinstance(recommendation, Mapping):
        return SafetyDecision(False, action, "click_outside_exploration")
    element_id = clean_text(automation.get("selected_element_id"))
    recommendation_id = clean_text(recommendation.get("selected_element_id"))
    if not element_id or element_id != recommendation_id:
        return SafetyDecision(False, action, "selection_mismatch")
    if clean_text(recommendation.get("risk_level") or "blocked") != "low":
        return SafetyDecision(False, action, "non_low_risk")
    if bool(recommendation.get("requires_user_confirmation", True)):
        return SafetyDecision(False, action, "user_confirmation_required")
    element = next((candidate for candidate in capture.tree.elements if candidate.element_id == element_id), None)
    if element is None:
        return SafetyDecision(False, action, "element_not_found")
    if not element.clickable or not element.enabled or not element.visible or element.bounds is None:
        return SafetyDecision(False, action, "element_not_actionable", element)
    if element.checkable or element.password or element.role in {"text_field", "checkbox", "switch", "radio_button"}:
        return SafetyDecision(False, action, "state_or_input_control", element)
    label = clean_text(recommendation.get("selected_label") or element.label)
    normalized = normalized_label(label)
    if any(term in normalized for term in CAPTCHA_TERMS):
        return SafetyDecision(False, action, "captcha_boundary", element)
    if any(term == normalized or normalized.startswith(f"{term} ") for term in AUTH_ACTION_TERMS):
        return SafetyDecision(False, action, "authentication_boundary", element)
    if is_consequential_label(label):
        return SafetyDecision(False, action, "consequential_final_action", element)
    return SafetyDecision(True, action, "low_risk_navigation", element)


@dataclass
class InfiniteFeedGuard:
    max_scrolls: int = 5
    previous_label_sets: list[set[str]] = field(default_factory=list)
    scroll_count: int = 0

    def classify(self, tree: ParsedUiTree) -> str:
        labels = [normalized_label(label) for label in tree.visible_labels]
        combined = " ".join(labels)
        feed_hits = sum(term in combined for term in FEED_TERMS)
        menu_hits = sum(term in combined for term in MENU_TERMS)
        long_cards = sum(len(label) >= 80 for label in labels)
        clickable_count = sum(element.clickable for element in tree.elements if element.visible)
        if feed_hits >= 1 and menu_hits == 0:
            return "infinite_feed"
        if long_cards >= 4 and clickable_count >= 6 and menu_hits <= 1:
            return "content_list"
        return "menu"

    def assess_scroll(self, tree: ParsedUiTree) -> SafetyDecision:
        screen_type = self.classify(tree)
        if screen_type in {"infinite_feed", "content_list"}:
            return SafetyDecision(False, "scroll_forward", f"excluded_{screen_type}")
        if self.scroll_count >= self.max_scrolls:
            return SafetyDecision(False, "scroll_forward", "scroll_budget_exhausted")
        current = {
            normalized_label(label)
            for label in tree.visible_labels
            if clean_text(label) and not _LONG_NUMBER_RE.search(label)
        }
        if self.previous_label_sets:
            previous = self.previous_label_sets[-1]
            union = current | previous
            similarity = len(current & previous) / max(1, len(union))
            novelty = len(current - previous)
            if similarity >= 0.92 or novelty <= 1:
                return SafetyDecision(False, "scroll_forward", "repeated_or_no_novel_content")
        return SafetyDecision(True, "scroll_forward", "menu_page_scroll")

    def note_scroll(self, tree: ParsedUiTree) -> None:
        self.previous_label_sets.append(
            {normalized_label(label) for label in tree.visible_labels if clean_text(label)}
        )
        self.previous_label_sets = self.previous_label_sets[-3:]
        self.scroll_count += 1


@dataclass(frozen=True)
class ExplorationBudget:
    max_actions: int = 30
    max_seconds: float = 60.0
    max_scrolls: int = 5
    max_backs: int = 8
    max_screen_visits: int = 3
    settle_seconds: float = 1.2


@dataclass
class ExplorationState:
    session_id: str
    action_count: int = 0
    scroll_count: int = 0
    back_count: int = 0
    unsafe_click_count: int = 0
    elapsed_before_resume_seconds: float = 0.0
    screen_visits: dict[str, int] = field(default_factory=dict)
    pending_action: dict[str, object] | None = None
    started_monotonic: float = field(default_factory=time.monotonic)

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_before_resume_seconds + (time.monotonic() - self.started_monotonic)

    def budget_reason(self, budget: ExplorationBudget) -> str | None:
        if self.action_count >= budget.max_actions:
            return "action_budget_exhausted"
        if self.elapsed_seconds >= budget.max_seconds:
            return "time_budget_exhausted"
        if self.back_count >= budget.max_backs:
            return "back_budget_exhausted"
        return None

    def checkpoint_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "action_count": self.action_count,
            "scroll_count": self.scroll_count,
            "back_count": self.back_count,
            "unsafe_click_count": self.unsafe_click_count,
            "elapsed_seconds": self.elapsed_seconds,
            "screen_visits": dict(self.screen_visits),
            # A process boundary invalidates an in-flight transition.  Keeping
            # it for evidence is fine, but it is never replayed into the API.
            "pending_action": self.pending_action,
        }

    @classmethod
    def from_checkpoint(cls, payload: Mapping[str, object], fallback_session_id: str) -> "ExplorationState":
        visits = payload.get("screen_visits")
        return cls(
            session_id=clean_text(payload.get("session_id")) or fallback_session_id,
            action_count=int(payload.get("action_count") or 0),
            scroll_count=int(payload.get("scroll_count") or 0),
            back_count=int(payload.get("back_count") or 0),
            unsafe_click_count=int(payload.get("unsafe_click_count") or 0),
            elapsed_before_resume_seconds=float(payload.get("elapsed_seconds") or 0.0),
            screen_visits={str(key): int(value) for key, value in visits.items()} if isinstance(visits, Mapping) else {},
            pending_action=None,
        )


class OptionalCorpusAdapter:
    """Best-effort bridge to the richer corpus service when it is installed.

    The collector's JSONL evidence remains authoritative for crash recovery;
    this adapter never turns an optional schema/API mismatch into data loss.
    """

    def __init__(self, run_directory: Path, run_id: str, *, resume: bool) -> None:
        self.instance: object | None = None
        if str(API_ROOT) not in sys.path:
            sys.path.insert(0, str(API_ROOT))
        try:
            module = importlib.import_module("app.services.emulator_observation_corpus")
        except (ImportError, ModuleNotFoundError):
            return
        for name in ("EmulatorObservationCorpus", "ObservationCorpus", "CorpusStore"):
            constructor = getattr(module, name, None)
            if constructor is None:
                continue
            for args, kwargs in (
                ((run_directory,), {"run_id": run_id, "resume": resume}),
                ((run_directory,), {"run_id": run_id}),
                ((run_directory,), {}),
                ((), {"run_directory": run_directory, "run_id": run_id}),
            ):
                try:
                    self.instance = constructor(*args, **kwargs)
                    return
                except Exception:
                    continue
        for name in ("open_run", "create_run"):
            factory = getattr(module, name, None)
            if factory is None:
                continue
            try:
                self.instance = factory(run_directory=run_directory, run_id=run_id)
                return
            except Exception:
                continue

    @property
    def available(self) -> bool:
        return self.instance is not None

    def append(self, kind: str, payload: Mapping[str, object], run_directory: Path) -> bool:
        if self.instance is None:
            return False
        method_name = {
            "app": "append_app",
            "run": "append_run",
            "observation": "append_screen",
            "element": "append_element",
            "transition": "append_transition",
            "goal": "append_goal",
            "failure": "append_failure",
            "metric": "append_metric",
            "annotation": "append_annotation",
        }[kind]
        method = getattr(self.instance, method_name, None)
        if method is None:
            return False
        adapted = dict(payload)
        record_id: str
        kwargs: dict[str, object] = {}
        if kind == "run":
            record_id = clean_text(adapted.get("run_observation_id")) or clean_text(adapted.get("run_id"))
            adapted["run_observation_id"] = record_id
            adapted.pop("recorded_at", None)
        elif kind == "app":
            record_id = clean_text(adapted.get("app_observation_id")) or f"app_{stable_hash(adapted)}"
            adapted["app_observation_id"] = record_id
            adapted.pop("recorded_at", None)
        elif kind == "observation":
            record_id = clean_text(adapted.get("screen_id")) or f"screen_{stable_hash(adapted)}"
            adapted["screen_id"] = record_id
            for path_key in ("screenshot_path", "accessibility_tree_path"):
                value = adapted.get(path_key)
                if value:
                    candidate = Path(str(value))
                    adapted[path_key] = str(candidate if candidate.is_absolute() else run_directory / candidate)
            adapted["contains_personal_data"] = bool(adapted.get("contains_personal_information"))
            adapted["scrollable_regions"] = (
                [adapted["scrollable_bounds"]] if adapted.get("scrollable_bounds") else []
            )
            adapted["collected_at"] = adapted.get("captured_at")
            # Both artifacts were redacted before their atomic publication.  A
            # missing screenshot is explicitly allowed as verified metadata.
            adapted["privacy_verified"] = True
            kwargs["privacy_verified"] = True
        elif kind == "element":
            local_id = clean_text(adapted.get("element_id")) or "unknown"
            screen_id = clean_text(adapted.get("screen_id")) or clean_text(adapted.get("observation_id"))
            record_id = f"{screen_id}:{local_id}"
            adapted["ui_element_id"] = local_id
            adapted["element_id"] = record_id
            kwargs["privacy_verified"] = True
        elif kind == "transition":
            record_id = clean_text(adapted.get("transition_id")) or f"transition_{stable_hash(adapted)}"
            adapted["transition_id"] = record_id
            adapted["source_screen_id"] = adapted.get("source_screen_id") or adapted.get("source_observation_id")
            adapted["target_screen_id"] = adapted.get("target_screen_id") or adapted.get("target_observation_id")
            adapted["action_coordinates"] = adapted.get("coordinates")
            adapted["transition_time_ms"] = adapted.get("transition_ms")
            adapted["success"] = adapted.get("outcome") == "navigated"
            adapted["can_go_back"] = bool(adapted.get("reversible"))
            adapted["repeated_or_loop"] = bool(adapted.get("loop_detected"))
            adapted["auto_executed"] = True
            adapted["is_final_action"] = False
            adapted["unsafe_action"] = False
        elif kind == "goal":
            record_id = clean_text(adapted.get("goal_id")) or f"goal_{stable_hash(adapted)}"
            adapted["goal_id"] = record_id
            adapted.pop("recorded_at", None)
        elif kind == "failure":
            record_id = clean_text(adapted.get("failure_id")) or f"failure_{stable_hash(adapted)}"
            adapted["failure_id"] = record_id
            adapted["app_package"] = adapted.get("app_package") or ""
            adapted["user_goal"] = adapted.get("goal_text")
            adapted["failure_reason"] = adapted.get("failure_type")
        elif kind == "metric":
            record_id = clean_text(adapted.get("metric_id")) or f"metric_{stable_hash(adapted)}"
            adapted["metric_id"] = record_id
            adapted["metric_dimension"] = adapted.get("metric_type")
            adapted["exploration_time_ms"] = adapted.get("elapsed_ms")
            adapted["click_count"] = adapted.get("action_count")
            adapted["unsafe_auto_click_count"] = 0
            adapted["final_action_auto_click_count"] = 0
        else:
            record_id = clean_text(adapted.get("annotation_id")) or f"annotation_{stable_hash(adapted)}"
            adapted["annotation_id"] = record_id
        try:
            method(adapted, record_id=record_id, **kwargs)
            return True
        except Exception:
            # Optional mirror failure is intentionally non-fatal.  The caller
            # always persisted the same record to append-only JSONL first.
            return False

    def save_checkpoint(self, state: Mapping[str, object]) -> bool:
        if self.instance is None:
            return False
        method = getattr(self.instance, "save_checkpoint", None)
        if method is None:
            return False
        try:
            method(dict(state))
            return True
        except Exception:
            return False

    def load_checkpoint(self) -> dict[str, object] | None:
        if self.instance is None:
            return None
        try:
            state = getattr(self.instance, "resume_state")
            return dict(state) if isinstance(state, Mapping) else {}
        except Exception:
            return None


class ObservationSink:
    FILES = {
        "app": "apps.jsonl",
        "run": "runs.jsonl",
        "observation": "observations.jsonl",
        "element": "elements.jsonl",
        "transition": "transitions.jsonl",
        "goal": "goals.jsonl",
        "failure": "failures.jsonl",
        "metric": "metrics.jsonl",
        "annotation": "annotations.jsonl",
    }

    def __init__(self, output_root: Path, run_id: str, *, resume: bool, manifest: Mapping[str, object]) -> None:
        self.run_id = run_id
        self._registered_apps: set[str] = set()
        self._registered_goals: set[str] = set()
        self.run_directory = output_root / run_id
        self.run_directory.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = self.run_directory / "checkpoint.json"
        self.manifest_path = self.run_directory / "manifest.json"
        corpus_exists = self.manifest_path.exists() or (self.run_directory / "corpus.sqlite").exists()
        if corpus_exists and not resume:
            raise FileExistsError(f"run already exists; pass --resume: {self.run_directory}")
        self.adapter = OptionalCorpusAdapter(self.run_directory, run_id, resume=resume)
        if self.adapter.available:
            # The corpus service owns the integrity-pinned manifest and
            # checkpoint. Collector configuration is supplemental metadata.
            collector_manifest = self.run_directory / "collector-manifest.json"
            if not collector_manifest.exists():
                atomic_write_json(collector_manifest, dict(manifest))
        elif not self.manifest_path.exists():
            atomic_write_json(self.manifest_path, dict(manifest))
        lifecycle = "resume" if resume else "start"
        self.append(
            "run",
            {
                "run_observation_id": run_id if not resume else f"{run_id}:resume:{utc_now()}",
                "device_id": manifest.get("device_serial"),
                "avd_name": manifest.get("avd_name", "EGL_Universal_Play_API36"),
                "api_base_url": manifest.get("api_base_url"),
                "lifecycle_event": lifecycle,
                "resumed_from_sequence": None,
                "started_at": manifest.get("created_at"),
            },
        )

    def append(self, kind: str, payload: Mapping[str, object]) -> None:
        record = {
            "schema_version": 1,
            "provenance": OBSERVATION_PROVENANCE,
            "run_id": self.run_id,
            "recorded_at": utc_now(),
            **dict(payload),
        }
        mirrored = self.adapter.append(kind, record, self.run_directory)
        # The corpus service owns observations.jsonl.  Other files are useful
        # compact per-type mirrors for inspection and remain rebuildable from
        # corpus.sqlite.  Without the service all five JSONL files are the
        # crash-safe fallback store.
        if self.adapter.available and kind == "observation":
            if not mirrored:
                append_jsonl(self.run_directory / "collector-observations-fallback.jsonl", record)
        else:
            append_jsonl(self.run_directory / self.FILES[kind], record)

    def register_app(self, task: "CollectionTask", capture: ScreenCapture) -> None:
        record_id = f"app_{stable_hash({'package': task.app_package, 'version': capture.app_version, 'locale': capture.locale})}"
        if record_id in self._registered_apps:
            return
        self.append(
            "app",
            {
                "app_observation_id": record_id,
                "app_package": task.app_package,
                "app_name": task.app_name,
                "app_version": capture.app_version,
                "locale": capture.locale,
                "install_source": "google_play_or_system",
                "store_url": None,
            },
        )
        self._registered_apps.add(record_id)

    def register_goal(self, task: "CollectionTask") -> str:
        goal_id = f"goal_{stable_hash({'package': task.app_package, 'goal': task.goal_text}, 20)}"
        if goal_id not in self._registered_goals:
            self.append(
                "goal",
                {
                    "goal_id": goal_id,
                    "app_package": task.app_package,
                    "goal_text": task.goal_text,
                    "canonical_goal_id": None,
                    "standard_goal_id": None,
                    "semantic_function_id": None,
                    "terminal_candidate_screen_id": None,
                    "terminal_candidate_element_id": None,
                    "terminal_confidence": 0.0,
                    "status": "candidate",
                    "expected_terminal": None,
                    "evidence": {"source": OBSERVATION_PROVENANCE, "task_id": task.task_id},
                },
            )
            self._registered_goals.add(goal_id)
        return goal_id

    def checkpoint(self, payload: Mapping[str, object]) -> None:
        if not self.adapter.save_checkpoint(payload):
            atomic_write_json(self.checkpoint_path, dict(payload))

    def load_checkpoint(self) -> dict[str, object]:
        adapted = self.adapter.load_checkpoint()
        if adapted is not None:
            return adapted
        if not self.checkpoint_path.exists():
            return {}
        decoded = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        return decoded if isinstance(decoded, dict) else {}


@dataclass(frozen=True)
class CollectionTask:
    app_package: str
    app_name: str
    category: str
    goal_text: str

    @property
    def task_id(self) -> str:
        return f"task_{stable_hash(asdict(self), 16)}"


class ExplorationRunner:
    def __init__(
        self,
        adb: AdbClient,
        api: ObserveApiClient,
        sink: ObservationSink,
        budget: ExplorationBudget,
        *,
        screenshot_policy: str,
        capture_only: bool,
        dry_run: bool,
        restart_app: bool,
        launch_app: bool,
    ) -> None:
        self.adb = adb
        self.api = api
        self.sink = sink
        self.budget = budget
        self.screenshot_policy = screenshot_policy
        self.capture_only = capture_only
        self.dry_run = dry_run
        self.restart_app = restart_app
        self.launch_app = launch_app

    def run_task(self, task: CollectionTask, *, resume_state: Mapping[str, object] | None = None) -> str:
        goal_id = self.sink.register_goal(task)
        session_id = f"emu_{stable_hash({'task': task.task_id, 'run': self.sink.run_id}, 18)}"
        state = (
            ExplorationState.from_checkpoint(resume_state or {}, session_id)
            if resume_state
            else ExplorationState(session_id=session_id)
        )
        feed_guard = InfiniteFeedGuard(max_scrolls=self.budget.max_scrolls)
        feed_guard.scroll_count = state.scroll_count
        app_directory = self.sink.run_directory / "apps" / slug(task.app_package)
        app_directory.mkdir(parents=True, exist_ok=True)
        if self.launch_app:
            self.adb.launch(task.app_package, restart=self.restart_app)
            time.sleep(self.budget.settle_seconds)

        status = "incomplete"
        while True:
            budget_reason = state.budget_reason(self.budget)
            if budget_reason:
                status = self._stop(task, state, budget_reason, "exploration_budget")
                break
            capture_id = f"{task.task_id}-{state.action_count:03d}-{uuid.uuid4().hex[:8]}"
            capture = self.adb.capture_pair(
                app_directory,
                capture_id,
                screenshot_policy=self.screenshot_policy,
            )
            state.screen_visits[capture.tree.screen_signature] = state.screen_visits.get(capture.tree.screen_signature, 0) + 1
            observation_id = f"obs_{stable_hash({'task': task.task_id, 'capture': capture.capture_id}, 20)}"
            self._record_capture(task, state, capture, observation_id)

            pending = state.pending_action
            api_transition: dict[str, object] | None = None
            if pending is not None:
                changed = capture.tree.screen_signature != clean_text(pending.get("local_from_signature"))
                outcome = "navigated" if changed else "no_change"
                transition_record = {
                    **pending,
                    "target_observation_id": observation_id,
                    "target_screen_id": capture.capture_id,
                    "target_local_screen_signature": capture.tree.screen_signature,
                    "outcome": outcome,
                    "transition_ms": max(0.0, time.time() * 1000.0 - float(pending.get("performed_at_epoch_ms") or 0.0)),
                }
                self.sink.append("transition", transition_record)
                if pending.get("action_type") == "click" and pending.get("server_from_fingerprint"):
                    api_transition = {
                        "from_screen_fingerprint": pending["server_from_fingerprint"],
                        "performed_element_id": pending["element_id"],
                        "outcome": outcome,
                    }
                    if pending.get("recommendation_id"):
                        api_transition["recommendation_id"] = pending["recommendation_id"]
                state.pending_action = None

            if state.screen_visits[capture.tree.screen_signature] > self.budget.max_screen_visits:
                status = self._stop(task, state, "screen_visit_loop", "repeated_screen")
                break
            if capture.package != task.app_package:
                reason = "system_boundary" if capture.package in SYSTEM_BOUNDARY_PACKAGES else "external_package_boundary"
                status = self._stop(task, state, reason, "package_boundary", capture=capture)
                break
            boundary = screen_boundary(capture.tree)
            if boundary:
                status = self._stop(task, state, boundary, "user_input_required", capture=capture)
                break
            if self.capture_only:
                status = "captured"
                self._checkpoint(task, state, status)
                break

            request_id = f"req_{uuid.uuid4().hex[:20]}"
            request_payload: dict[str, object] = {
                "request_id": request_id,
                "session_id": state.session_id,
                "app_package": task.app_package,
                "app_version": capture.app_version,
                "locale": capture.locale,
                "goal_text": task.goal_text,
                "operation_mode": "explore",
                "screen": capture.api_screen(),
                "client_timing": {
                    "measurement_source": "real_device",
                    "exploration_elapsed_ms": min(3_600_000.0, state.elapsed_seconds * 1000.0),
                    "screen_capture_ms": min(300_000.0, capture.capture_ms),
                    "action_execution_ms": 0.0,
                    "ui_settle_ms": min(300_000.0, self.budget.settle_seconds * 1000.0),
                    "external_wait_ms": 0.0,
                },
            }
            if api_transition:
                request_payload["transition"] = api_transition
            api_started = time.perf_counter()
            try:
                response = self.api.observe(request_payload)
            except ObserveApiError as error:
                status = self._stop(task, state, "observe_api_error", "api", detail=str(error), capture=capture)
                break
            api_ms = (time.perf_counter() - api_started) * 1000.0
            self.sink.append(
                "metric",
                {
                    "task_id": task.task_id,
                    "goal_id": goal_id,
                    "session_id": state.session_id,
                    "observation_id": observation_id,
                    "metric_type": "observe_stage",
                    "api_ms": api_ms,
                    "capture_ms": capture.capture_ms,
                    "elapsed_ms": state.elapsed_seconds * 1000.0,
                    "action_count": state.action_count,
                    "scroll_count": state.scroll_count,
                    "back_count": state.back_count,
                    "unsafe_click_count": state.unsafe_click_count,
                    "response_status": response.get("status"),
                    "phase": response.get("phase"),
                    "decision_mode": response.get("decision_mode"),
                    "screen_fingerprint": response.get("screen_fingerprint"),
                },
            )
            decision = assess_automation(response, capture, expected_package=task.app_package)
            if decision.action == "scroll_forward" and decision.allowed:
                decision = feed_guard.assess_scroll(capture.tree)
            if not decision.allowed:
                # A rejected click is a blocked proposal, not an executed
                # unsafe click. The latter invariant must remain exactly zero.
                phase = clean_text(response.get("phase"))
                terminal_status = "destination_reached" if phase == "destination_reached" else "safe_stop"
                self.sink.append(
                    "failure" if terminal_status != "destination_reached" else "metric",
                    {
                        "task_id": task.task_id,
                        "app_package": task.app_package,
                        "goal_id": goal_id,
                        "session_id": state.session_id,
                        "observation_id": observation_id,
                        "failure_type" if terminal_status != "destination_reached" else "metric_type": decision.reason,
                        "goal_text": task.goal_text,
                        "selected_candidates": response.get("candidates", []),
                        "correct_candidate": None,
                        "retry_result": "not_attempted",
                        "automation_action": decision.action,
                        "server_phase": phase,
                    },
                )
                status = terminal_status
                self._checkpoint(task, state, status)
                break
            if self.dry_run:
                self.sink.append(
                    "metric",
                    {
                        "task_id": task.task_id,
                        "app_package": task.app_package,
                        "goal_id": goal_id,
                        "session_id": state.session_id,
                        "observation_id": observation_id,
                        "metric_type": "dry_run_would_execute",
                        "action": decision.action,
                        "element_id": decision.element.element_id if decision.element else None,
                        "safety_reason": decision.reason,
                    },
                )
                status = "dry_run_complete"
                self._checkpoint(task, state, status)
                break

            action_started = time.perf_counter()
            action_metadata: dict[str, object] = {}
            if decision.action == "click" and decision.element and decision.element.bounds:
                self.adb.tap(decision.element.bounds)
                action_metadata["coordinates"] = list(decision.element.bounds)
                element_id = decision.element.element_id
            elif decision.action == "scroll_forward":
                coordinates = self.adb.page_scroll(capture.tree.scroll_bounds)
                feed_guard.note_scroll(capture.tree)
                state.scroll_count += 1
                action_metadata.update(
                    {
                        "coordinates": list(coordinates),
                        "scroll_direction": "forward",
                        "scroll_distance": abs(coordinates[1] - coordinates[3]),
                    }
                )
                element_id = clean_text(
                    (response.get("automation") or {}).get("selected_element_id")
                    if isinstance(response.get("automation"), Mapping)
                    else ""
                ) or "__page_scroll__"
            elif decision.action == "back":
                self.adb.back()
                state.back_count += 1
                element_id = "__back__"
            else:
                status = self._stop(task, state, "local_dispatch_mismatch", "collector")
                break
            action_ms = (time.perf_counter() - action_started) * 1000.0
            state.action_count += 1
            recommendation = response.get("recommendation") if isinstance(response.get("recommendation"), Mapping) else {}
            state.pending_action = {
                "transition_id": f"tr_{uuid.uuid4().hex[:20]}",
                "task_id": task.task_id,
                "app_package": task.app_package,
                "goal_id": goal_id,
                "session_id": state.session_id,
                "source_observation_id": observation_id,
                "source_screen_id": capture.capture_id,
                "local_from_signature": capture.tree.screen_signature,
                "server_from_fingerprint": clean_text(response.get("screen_fingerprint")),
                "action_type": decision.action,
                "element_id": element_id,
                "recommendation_id": clean_text(recommendation.get("recommendation_id")),
                "selected_label": clean_text(recommendation.get("selected_label")),
                "action_execution_ms": action_ms,
                "performed_at": utc_now(),
                "performed_at_epoch_ms": time.time() * 1000.0,
                "safe_to_execute": True,
                "local_guard_reason": decision.reason,
                "reversible": decision.action in {"click", "scroll_forward", "back"},
                "loop_detected": False,
                **action_metadata,
            }
            self._checkpoint(task, state, "running")
            time.sleep(self.budget.settle_seconds)
        return status

    def _record_capture(
        self,
        task: CollectionTask,
        state: ExplorationState,
        capture: ScreenCapture,
        observation_id: str,
    ) -> None:
        self.sink.register_app(task, capture)
        goal_id = self.sink.register_goal(task)
        relative_tree = capture.tree_path.relative_to(self.sink.run_directory).as_posix()
        relative_screenshot = (
            capture.screenshot_path.relative_to(self.sink.run_directory).as_posix()
            if capture.screenshot_path
            else None
        )
        self.sink.append(
            "observation",
            {
                "observation_id": observation_id,
                "task_id": task.task_id,
                "goal_id": goal_id,
                "session_id": state.session_id,
                "app_package": task.app_package,
                "observed_package": capture.package,
                "app_name": task.app_name,
                "category": task.category,
                "app_version": capture.app_version,
                "locale": capture.locale,
                "goal_text": task.goal_text,
                "screen_id": capture.capture_id,
                "screen_signature": capture.tree.screen_signature,
                "screenshot_path": relative_screenshot,
                "accessibility_tree_path": relative_tree,
                "activity_name": capture.activity_name,
                "title_text": capture.title,
                "visible_texts": list(capture.tree.visible_labels),
                "content_descriptions": [
                    element.content_description
                    for element in capture.tree.elements
                    if element.content_description and not element.sensitive
                ],
                "resource_ids": sorted({element.resource_id for element in capture.tree.elements if element.resource_id}),
                "scrollable_bounds": list(capture.tree.scroll_bounds) if capture.tree.scroll_bounds else None,
                "screen_type": InfiniteFeedGuard().classify(capture.tree),
                "login_prerequisite": screen_boundary(capture.tree) == "authentication_boundary",
                "contains_personal_information": bool(capture.tree.sensitive_bounds),
                "captured_at": capture.captured_at,
                "capture_ms": capture.capture_ms,
                "tree_sha256": capture.tree_sha256,
                "screenshot_sha256": capture.screenshot_sha256,
                "privacy_policy": "redacted_or_metadata_only",
            },
        )
        for element in capture.tree.elements:
            self.sink.append(
                "element",
                {
                    "observation_id": observation_id,
                    "screen_id": capture.capture_id,
                    "task_id": task.task_id,
                    "goal_id": goal_id,
                    **element.corpus_dict(),
                    "semantic_function_id": None,
                    "synonyms": [],
                    "expected_result": None,
                    "risk_level": "blocked" if element.sensitive or element.checkable else "unclassified",
                    "is_final_action": is_consequential_label(element.label),
                    "confidence": 0.0,
                    "evidence": "uiautomator_live_emulator",
                },
            )
        self.sink.append(
            "annotation",
            {
                "annotation_id": f"ann_{stable_hash({'screen': capture.capture_id, 'label': 'screen_type'}, 20)}",
                "entity_type": "screen",
                "entity_id": capture.capture_id,
                "label": "screen_type",
                "value": InfiniteFeedGuard().classify(capture.tree),
                "confidence": 0.75,
                "reviewer": "deterministic_collector",
                "status": "candidate",
                "app_package": task.app_package,
                "goal_id": goal_id,
            },
        )

    def _stop(
        self,
        task: CollectionTask,
        state: ExplorationState,
        reason: str,
        source: str,
        *,
        detail: str = "",
        capture: ScreenCapture | None = None,
    ) -> str:
        self.sink.append(
            "failure",
            {
                "task_id": task.task_id,
                "app_package": task.app_package,
                "goal_id": self.sink.register_goal(task),
                "session_id": state.session_id,
                "failure_type": reason,
                "failure_source": source,
                "goal_text": task.goal_text,
                "screen_signature": capture.tree.screen_signature if capture else None,
                "selected_candidates": [],
                "correct_candidate": None,
                "cause": detail or reason,
                "required_synonym_or_label": None,
                "policy_correction": None,
                "retry_result": "not_attempted",
            },
        )
        self._checkpoint(task, state, "stopped")
        return f"stopped:{reason}"

    def _checkpoint(self, task: CollectionTask, state: ExplorationState, status: str) -> None:
        existing = self.sink.load_checkpoint()
        completed = list(existing.get("completed_task_ids") or [])
        payload = {
            "schema_version": 1,
            "run_id": self.sink.run_id,
            "updated_at": utc_now(),
            "completed_task_ids": completed,
            "current_task_id": task.task_id,
            "current_task": asdict(task),
            "task_status": status,
            "state": state.checkpoint_dict(),
        }
        self.sink.checkpoint(payload)


def find_adb(explicit: str | None) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if path.exists():
            return str(path)
        resolved = shutil.which(explicit)
        if resolved:
            return resolved
        raise FileNotFoundError(f"ADB executable not found: {explicit}")
    candidates = [
        shutil.which("adb"),
        os.environ.get("ANDROID_HOME") and str(Path(os.environ["ANDROID_HOME"]) / "platform-tools" / "adb.exe"),
        str(Path.home() / "ExitGuideAndroidSdk" / "platform-tools" / "adb.exe"),
        str(REPO_ROOT / ".tools" / "android-sdk" / "platform-tools" / "adb.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise FileNotFoundError("ADB was not found; pass --adb or set ANDROID_HOME")


def tasks_from_arguments(args: argparse.Namespace) -> list[CollectionTask]:
    if args.manifest:
        document = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
        apps = document.get("apps") if isinstance(document, dict) else None
        if not isinstance(apps, list):
            raise ValueError("manifest must contain an apps array")
        tasks: list[CollectionTask] = []
        for app in apps[: args.max_apps or None]:
            if not isinstance(app, Mapping):
                continue
            goals = app.get("goals") if isinstance(app.get("goals"), list) else []
            for goal in goals[: args.max_goals_per_app or None]:
                tasks.append(
                    CollectionTask(
                        app_package=clean_text(app.get("app_package")),
                        app_name=clean_text(app.get("app_name")) or clean_text(app.get("app_package")),
                        category=clean_text(app.get("category")) or "unknown",
                        goal_text=clean_text(goal),
                    )
                )
        return [task for task in tasks if task.app_package and task.goal_text]
    if not args.package or not args.goal:
        raise ValueError("--package and --goal are required unless --manifest is used")
    return [
        CollectionTask(
            app_package=args.package,
            app_name=args.app_name or args.package,
            category=args.category or "unknown",
            goal_text=args.goal,
        )
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", help="Android package for a single task")
    parser.add_argument("--app-name", help="Human-readable app name")
    parser.add_argument("--category", help="App category")
    parser.add_argument("--goal", help="User goal for a single task")
    parser.add_argument("--manifest", type=Path, help="App/goal manifest JSON")
    parser.add_argument("--max-apps", type=int, default=0)
    parser.add_argument("--max-goals-per-app", type=int, default=0)
    parser.add_argument("--serial", default=DEFAULT_SERIAL)
    parser.add_argument("--adb", help="Path to adb executable")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--capture-only", action="store_true", help="Capture one screen per task; do not call API")
    parser.add_argument("--dry-run", action="store_true", help="Call API and safety guard; never touch UI")
    parser.add_argument("--no-launch", action="store_true", help="Do not launch or restart the target app")
    parser.add_argument("--keep-app-state", action="store_true", help="Launch without force-stopping first")
    parser.add_argument("--screenshot-policy", choices=("redacted", "none"), default="redacted")
    parser.add_argument("--max-actions", type=int, default=30)
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--max-scrolls", type=int, default=5)
    parser.add_argument("--max-backs", type=int, default=8)
    parser.add_argument("--max-screen-visits", type=int, default=3)
    parser.add_argument("--settle-seconds", type=float, default=1.2)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if min(args.max_actions, args.max_scrolls, args.max_backs, args.max_screen_visits) < 0:
        raise SystemExit("budgets must be non-negative")
    tasks = tasks_from_arguments(args)
    if not tasks:
        raise SystemExit("no collection tasks were selected")
    run_id = args.run_id or f"emu-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    if args.resume and not args.run_id:
        raise SystemExit("--resume requires --run-id")
    adb_path = find_adb(args.adb)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": utc_now(),
        "provenance": OBSERVATION_PROVENANCE,
        "dataset_role": "app_graph_candidate",
        "canonical_catalog_mutation": False,
        "canonical_route_mutation": False,
        "device_serial": args.serial,
        "api_base_url": args.api_base_url,
        "capture_only": args.capture_only,
        "dry_run": args.dry_run,
        "screenshot_policy": args.screenshot_policy,
        "task_count": len(tasks),
        "tasks": [asdict(task) | {"task_id": task.task_id} for task in tasks],
        "safety_policy": {
            "local_fail_closed_guard": True,
            "never_click_final_or_consequential": True,
            "stop_at_authentication_or_captcha": True,
            "stop_at_package_boundary": True,
            "exclude_infinite_feeds": True,
            "unsafe_click_target": 0,
        },
    }
    sink = ObservationSink(args.output_root.resolve(), run_id, resume=args.resume, manifest=manifest)
    adb = AdbClient(adb_path, args.serial)
    adb.assert_ready()
    api = ObserveApiClient(args.api_base_url)
    budget = ExplorationBudget(
        max_actions=args.max_actions,
        max_seconds=args.max_seconds,
        max_scrolls=args.max_scrolls,
        max_backs=args.max_backs,
        max_screen_visits=args.max_screen_visits,
        settle_seconds=args.settle_seconds,
    )
    runner = ExplorationRunner(
        adb,
        api,
        sink,
        budget,
        screenshot_policy=args.screenshot_policy,
        capture_only=args.capture_only,
        dry_run=args.dry_run,
        restart_app=not args.keep_app_state,
        launch_app=not args.no_launch,
    )
    checkpoint = sink.load_checkpoint() if args.resume else {}
    completed = set(checkpoint.get("completed_task_ids") or [])
    statuses: dict[str, str] = {}
    for task in tasks:
        if task.task_id in completed:
            statuses[task.task_id] = "skipped_completed"
            continue
        resume_state = None
        if checkpoint.get("current_task_id") == task.task_id and isinstance(checkpoint.get("state"), Mapping):
            resume_state = checkpoint["state"]
        try:
            status = runner.run_task(task, resume_state=resume_state)
        except (AdbError, ET.ParseError, ValueError, OSError) as error:
            sink.append(
                "failure",
                {
                    "task_id": task.task_id,
                    "failure_type": "collector_exception",
                    "failure_source": "collector",
                    "goal_text": task.goal_text,
                    "cause": f"{type(error).__name__}: {error}",
                    "retry_result": "not_attempted",
                },
            )
            status = f"failed:{type(error).__name__}"
        statuses[task.task_id] = status
        # A safe stop or capture is a completed observation task.  A crash/API
        # failure remains resumable and is intentionally not marked complete.
        if not status.startswith("failed:") and "observe_api_error" not in status:
            completed.add(task.task_id)
        sink.checkpoint(
            {
                "schema_version": 1,
                "run_id": run_id,
                "updated_at": utc_now(),
                "completed_task_ids": sorted(completed),
                "current_task_id": None,
                "task_status": status,
                "statuses": statuses,
            }
        )
    summary = Counter(statuses.values())
    sink.append(
        "metric",
        {
            "metric_type": "run_summary",
            "task_count": len(tasks),
            "completed_task_count": len(completed),
            "status_counts": dict(summary),
            "unsafe_click_count": 0,
        },
    )
    print(json.dumps({"run_id": run_id, "run_directory": str(sink.run_directory), "statuses": statuses}, ensure_ascii=False))
    return 0 if not any(status.startswith("failed:") for status in statuses.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
