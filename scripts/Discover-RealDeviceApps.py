#!/usr/bin/env python3
"""Build a read-only inventory of user-facing apps on the designated phone.

The inventory is discovery metadata, not navigation evidence.  It is always an
unreviewed, shadow ``real_device_observation_candidate`` and cannot mutate the
frozen V15 catalog.  Only package metadata is retained; raw ``dumpsys`` output,
screens, accessibility trees, account data, and other human content are never
written.

This script deliberately has no install, delete, clear-data, force-stop,
launch, tap, or swipe capability.  Every ADB command passes through a compact
allowlist before an injected runner can execute it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = (
    REPO_ROOT / ".artifacts" / "navigation-observations" / "device-inventory"
)
DEFAULT_OBSERVATION_ROOT = REPO_ROOT / ".artifacts" / "navigation-observations"

EXPECTED_SERIAL = "R3CY204GDVE"
EXITGUIDE_PACKAGES = frozenset({"com.exitguide.ai"})
PROVENANCE = "real_device_observation_candidate"
DATASET_ROLE = PROVENANCE
REVIEW_STATUS = "unreviewed_candidate"
ROUTE_LIFECYCLE = "shadow"
VALIDATION_MARKER_NAME = "VALIDATED.json"

# User-selected launch cohort. New/updated versions still lead each cycle;
# among equally unobserved versions these packages receive deterministic
# attention before the long-tail inventory.
PRIORITY_TARGET_PACKAGES = (
    "com.google.android.youtube",
    "com.netflix.mediaclient",
    "com.sampleapp",
    "com.coupang.mobile",
    "com.parksmt.jejuair.android16",
    "com.twitter.android",
    "viva.republica.toss",
    "ni.mh.android.launcher",
    "kr.go.minwon.m",
    "kr.or.nhic",
    "kr.or.nhiq",
    "com.ktshow.cs",
    "com.nhn.android.search",
    "com.towneers.www",
    "com.instagram.android",
)
PRIORITY_TARGET_RANK = {
    package: rank for rank, package in enumerate(PRIORITY_TARGET_PACKAGES)
}

CANONICAL_CATALOG_VERSION = "15.0.0"
CANONICAL_CATALOG_SHA256 = (
    "e0eeef03195a48ec8172421926d08c30823bc678c72ea72082bb513dbec36e24"
)
CANONICAL_EQUIVALENCE_SHA256 = (
    "197aa0253c0353e439a6679a3597efed25297c44c554a15c0402a30f077ab2e8"
)
CANONICAL_COUNTS = {
    "domains": 179,
    "functions": 2866,
    "terminal_functions": 2660,
    "intents": 2660,
}

PACKAGE_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
COMPONENT_RE = re.compile(r"([A-Za-z0-9_.]+)/(\.?[A-Za-z0-9_.$]+)")
VERSION_NAME_RE = re.compile(r"(?m)^\s*versionName=([^\s]+)")
VERSION_CODE_RE = re.compile(r"(?m)^\s*versionCode=(\d+)")
FLAGS_RE = re.compile(r"(?m)^\s*(?:pkgFlags|flags)=\[([^\]]*)\]")
CODE_PATH_RE = re.compile(r"(?m)^\s*codePath=([^\s]+)")


class InventoryDiscoveryError(RuntimeError):
    """Raised when safe inventory discovery cannot continue."""


Runner = Callable[[Sequence[str], float], bytes | str]


@dataclass(frozen=True)
class SnapshotWriteResult:
    path: Path
    resumed_existing: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _default_runner(command: Sequence[str], timeout: float) -> bytes:
    completed = subprocess.run(
        list(command),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise InventoryDiscoveryError(
            f"read-only ADB command failed ({completed.returncode}): {stderr or 'no stderr'}"
        )
    return completed.stdout


def _decode(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").replace("\r\n", "\n").strip()
    return str(value).replace("\r\n", "\n").strip()


def _validate_package(package: str) -> str:
    value = str(package).strip()
    if not PACKAGE_RE.fullmatch(value):
        raise InventoryDiscoveryError(f"invalid Android package identifier: {value!r}")
    return value


class ReadOnlyAdbClient:
    """Small ADB facade whose command surface cannot mutate or launch apps."""

    _GETPROPS = frozenset(
        {
            "ro.serialno",
            "ro.kernel.qemu",
            "ro.product.model",
            "ro.build.version.release",
            "persist.sys.locale",
            "ro.product.locale",
        }
    )

    def __init__(
        self,
        *,
        serial: str = EXPECTED_SERIAL,
        adb_path: str = "adb",
        runner: Runner | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        serial = str(serial).strip()
        if serial != EXPECTED_SERIAL:
            raise InventoryDiscoveryError(
                f"only exact designated serial {EXPECTED_SERIAL!r} is allowed"
            )
        if "emulator" in serial.casefold() or serial.casefold().startswith("localhost:"):
            raise InventoryDiscoveryError("emulator and TCP pseudo-serial targets are forbidden")
        if not str(adb_path).strip():
            raise InventoryDiscoveryError("adb_path must not be empty")
        if timeout_seconds <= 0:
            raise InventoryDiscoveryError("timeout_seconds must be positive")
        self.serial = serial
        self.adb_path = str(adb_path)
        self.runner = runner or _default_runner
        self.timeout_seconds = float(timeout_seconds)

    @staticmethod
    def _assert_allowed(args: Sequence[str]) -> None:
        values = tuple(str(item) for item in args)
        if values == ("get-state",):
            return
        if len(values) == 3 and values[:2] == ("shell", "getprop"):
            if values[2] in ReadOnlyAdbClient._GETPROPS:
                return
        if values == ("shell", "pm", "list", "packages", "-3", "--user", "0"):
            return
        if values == (
            "shell",
            "cmd",
            "package",
            "query-activities",
            "--brief",
            "--user",
            "0",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        ):
            return
        if len(values) == 4 and values[:3] == ("shell", "dumpsys", "package"):
            _validate_package(values[3])
            return
        resolve_prefix = (
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "--user",
            "0",
            "-a",
            "android.intent.action.MAIN",
            "-c",
        )
        allowed_categories = {
            "android.intent.category.LAUNCHER",
            "android.intent.category.HOME",
        }
        if (
            len(values) == len(resolve_prefix) + 3
            and values[: len(resolve_prefix)] == resolve_prefix
            and values[len(resolve_prefix)] in allowed_categories
            and values[len(resolve_prefix) + 1] == "-p"
        ):
            _validate_package(values[-1])
            return
        raise InventoryDiscoveryError(
            "ADB command rejected by read-only inventory allowlist: " + " ".join(values)
        )

    def run(self, *args: str) -> str:
        self._assert_allowed(args)
        command = [self.adb_path, "-s", self.serial, *args]
        return _decode(self.runner(command, self.timeout_seconds))

    def getprop(self, name: str) -> str:
        return self.run("shell", "getprop", name)

    def verify_physical_device(self) -> None:
        if self.run("get-state") != "device":
            raise InventoryDiscoveryError("designated device is not in the ADB device state")
        reported_serial = self.getprop("ro.serialno")
        if reported_serial and reported_serial != EXPECTED_SERIAL:
            raise InventoryDiscoveryError(
                f"device reported unexpected serial {reported_serial!r}; refusing discovery"
            )
        qemu = self.getprop("ro.kernel.qemu").casefold()
        if qemu not in {"", "0", "false", "no"}:
            raise InventoryDiscoveryError("emulator-like ro.kernel.qemu value detected")

    def device_metadata(self) -> dict[str, object]:
        locale = self.getprop("persist.sys.locale") or self.getprop("ro.product.locale")
        return {
            "serial": EXPECTED_SERIAL,
            "device_type": "physical_android",
            "is_emulator": False,
            "model": self.getprop("ro.product.model") or "unknown",
            "android_version": self.getprop("ro.build.version.release") or "unknown",
            "locale": locale or "unknown",
        }

    def third_party_packages(self) -> list[str]:
        output = self.run("shell", "pm", "list", "packages", "-3", "--user", "0")
        packages: set[str] = set()
        for line in output.splitlines():
            value = line.strip()
            if not value.startswith("package:"):
                continue
            package = value[len("package:") :].strip()
            packages.add(_validate_package(package))
        return sorted(packages, key=str.casefold)

    def launcher_activities(self) -> dict[str, str]:
        """Return installed user-facing launch targets without launching them.

        ``pm list packages -3`` omits preloaded services such as YouTube on
        Samsung phones.  The launcher query supplies the missing installed
        user-facing candidates while still avoiding arbitrary system package
        enumeration.  Multiple activities for one package are collapsed
        deterministically.
        """

        output = self.run(
            "shell",
            "cmd",
            "package",
            "query-activities",
            "--brief",
            "--user",
            "0",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        )
        activities: dict[str, set[str]] = {}
        for component_package, activity in COMPONENT_RE.findall(output):
            package = _validate_package(component_package)
            activities.setdefault(package, set()).add(f"{package}/{activity}")
        return {
            package: sorted(components, key=str.casefold)[0]
            for package, components in sorted(activities.items(), key=lambda item: item[0].casefold())
        }

    def _resolve_main_activity(self, package: str, category: str) -> str | None:
        package = _validate_package(package)
        if category not in {
            "android.intent.category.LAUNCHER",
            "android.intent.category.HOME",
        }:
            raise InventoryDiscoveryError(f"unsupported intent category: {category}")
        output = self.run(
            "shell",
            "cmd",
            "package",
            "resolve-activity",
            "--brief",
            "--user",
            "0",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            category,
            "-p",
            package,
        )
        if not output or "no activity found" in output.casefold():
            return None
        matches = COMPONENT_RE.findall(output)
        if not matches:
            return None
        component_package, activity = matches[-1]
        return f"{component_package}/{activity}"

    def resolve_launcher_activity(self, package: str) -> str | None:
        return self._resolve_main_activity(package, "android.intent.category.LAUNCHER")

    def resolve_home_activity(self, package: str) -> str | None:
        """Resolve HOME for this exact package without launching anything."""

        return self._resolve_main_activity(package, "android.intent.category.HOME")

    def package_metadata(self, package: str) -> dict[str, object]:
        package = _validate_package(package)
        output = self.run("shell", "dumpsys", "package", package)
        version_name_match = VERSION_NAME_RE.search(output)
        version_code_match = VERSION_CODE_RE.search(output)
        code_path_match = CODE_PATH_RE.search(output)
        flags: set[str] = set()
        for match in FLAGS_RE.finditer(output):
            flags.update(token for token in re.split(r"[\s,]+", match.group(1).strip()) if token)
        code_path = code_path_match.group(1) if code_path_match else None
        is_system = bool(
            {"SYSTEM", "UPDATED_SYSTEM_APP"}.intersection(flags)
            or (code_path and code_path.startswith(("/system/", "/product/", "/vendor/")))
        )
        version_name = version_name_match.group(1) if version_name_match else None
        if version_name in {"null", "None", ""}:
            version_name = None
        version_code = version_code_match.group(1) if version_code_match else None
        return {
            "version_name": version_name,
            "version_code": version_code,
            "package_flags": sorted(flags),
            "is_system_app": is_system,
            "code_location": _code_location(code_path),
        }


def _code_location(code_path: str | None) -> str:
    if not code_path:
        return "unknown"
    if code_path.startswith("/data/"):
        return "data"
    if code_path.startswith("/system/"):
        return "system"
    if code_path.startswith("/product/"):
        return "product"
    if code_path.startswith("/vendor/"):
        return "vendor"
    return "other"


_EXCLUSION_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "non_service_developer_tool",
        "ADB, developer, or device-control utility, not a target service app",
        re.compile(
            r"(?:standardadb|adbtools?|adbshell|wirelessadb|(?:^|[._])ladb(?:[._/]|$)|"
            r"developeroptions|devicecontrol)",
            re.I,
        ),
    ),
    (
        "keyboard_or_input_method",
        "keyboard or input-method component, not a target service app",
        re.compile(r"(?:keyboard|inputmethod|swiftkey|gboard|(?:^|[._])ime(?:[._/]|$))", re.I),
    ),
    (
        "installer_or_permission_controller",
        "installer or permission-controller component",
        re.compile(r"(?:packageinstaller|permissioncontroller|(?:^|[._])installer(?:[._/]|$))", re.I),
    ),
    (
        "language_pack",
        "language, locale, or speech resource pack",
        re.compile(r"(?:languagepack|langpack|localepack|speechservices|(?:^|[._])lang(?:[._/]|$))", re.I),
    ),
    (
        "accessory_or_helper",
        "accessory, companion, plug-in, or helper component",
        re.compile(r"(?:wearable|watchplugin|watchmanager|(?:^|[._])(accessory|companion|helper|plugin)(?:[._/]|$))", re.I),
    ),
    (
        "non_service_infrastructure",
        "runtime, provider, setup, rendering, or other non-service infrastructure",
        re.compile(
            r"(?:webview|trichrome|setupwizard|printservice|devicepolicy|systemui|"
            r"(?:^|[._])(provider|wallpaper|screensaver)(?:[._/]|$)|"
            r"^com\.google\.android\.(?:gms|gsf)(?:[._/]|$))",
            re.I,
        ),
    ),
    (
        "system_os_component",
        "OS-owned settings, telephony, messaging, camera, or shell component",
        re.compile(
            r"^(?:com\.android\.(?:settings|contacts|camera|dialer|phone|messaging|mms|"
            r"documentsui|emergency|systemui)|"
            r"com\.samsung\.android\.(?:app\.contacts|dialer|messaging|camera|bixby|"
            r"honeyboard|inCallUI|smartmirroring|securefolder))",
            re.I,
        ),
    ),
)


_SENSITIVITY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "conversation_message",
        re.compile(
            r"(?:messag|messenger|telegram|whatsapp|discord|kakaotalk|kakao\.talk|chatgpt|"
            r"google\.android\.apps\.(?:bard|tachyon)|lguplus\.aicallagent|"
            r"securesms|instagram\.barcelona|"
            r"(?:^|[._])(chat|slack|teams|line|signal)(?:[._/]|$))",
            re.I,
        ),
    ),
    (
        "finance",
        re.compile(
            r"(?:bank|banking|securities|insurance|finance|fintech|crypto|exchange|binance|"
            r"shinhan|woori|upbit|dunamu|kakaobank|kbank|ibk|nonghyup|nhallone|shcard|"
            r"ni\.mh\.android\.launcher|com\.android\.vending|"
            r"lguplus\.(?:appstore|mobile\.cs)|sec\.android\.app\.samsungapps|"
            r"samsung\.android\.spay|"
            r"(?:^|[._])(bank|pay|card|toss|hana|nh|kb)(?:[._/]|$))",
            re.I,
        ),
    ),
    (
        "real_estate_location",
        re.compile(
            r"(?:realestate|zigbang|jikbang|dabang|navigation|location|"
            r"samsung\.android\.app\.find|lguplus\.navi|"
            r"(?:^|[._])(map|maps|land|taxi|property)(?:[._/]|$))",
            re.I,
        ),
    ),
    (
        "health_medical",
        re.compile(
            r"(?:health|healthcare|shealth|medical|medicine|hospital|clinic|doctor|"
            r"pharmacy|nhic|nhiq|ni\.mh\.android\.launcher)",
            re.I,
        ),
    ),
    (
        "personal_content",
        re.compile(
            r"(?:onedrive|skydrive|dropbox|meganz|mega\.privacy|google\.android\.apps\.docs|"
            r"google\.android\.gm|google\.android\.googlequicksearchbox|outlook|"
            r"com\.android\.(?:chrome|vending)|samsung\.android\.app\.(?:sketchbook|"
            r"notes|reminder)|samsung\.android\.calendar|samsung\.knox\.securefolder|"
            r"sec\.android\.(?:app\.(?:camera|myfiles|sbrowser|voicenote)|easyMover|gallery3d)|"
            r"google\.android\.apps\.(?:bard|tachyon)|lguplus\.aicallagent|"
            r"microsoft\.office\.(?:excel|officehubrow|powerpoint|word)|"
            r"infraware\.office|marc\.files|"
            r"(?:^|[._])(cloud|drive|mail|email|notes?|"
            r"photos?|gallery|myfiles|filemanager)(?:[._/]|$))",
            re.I,
        ),
    ),
    (
        "auth_security",
        re.compile(
            r"(?:security|authenticator|verification|protector|vaccine|certificate|securefolder|"
            r"(?:^|[._])(auth|otp|pass|safe|cert)(?:[._/]|$))",
            re.I,
        ),
    ),
)


def inclusion_decision(
    package: str,
    launchable_activity: str | None,
    home_activity: str | None = None,
) -> tuple[bool, str, str]:
    package = _validate_package(package)
    if package in EXITGUIDE_PACKAGES or any(
        package.startswith(f"{base}.") for base in EXITGUIDE_PACKAGES
    ):
        return False, "exitguide_self", "ExitGuide itself is excluded from target discovery"
    if home_activity:
        return (
            False,
            "launcher",
            "package explicitly resolves android.intent.category.HOME for user 0",
        )
    for reason_code, reason, pattern in _EXCLUSION_RULES:
        # Entry activity class names such as LauncherActivity, HomeActivity,
        # UIWebViewActivity, and ic_launcher are common in ordinary apps and
        # are never exclusion evidence.  Generic rules inspect package names
        # only; launcher status requires the exact HOME query above.
        if pattern.search(package):
            return False, reason_code, reason
    if not launchable_activity:
        return False, "non_launchable", "no user-facing launcher activity resolved for user 0"
    return True, "user_facing_launchable", "user-installed app has a launcher activity for user 0"


def sensitivity_categories(package: str, launchable_activity: str | None) -> list[str]:
    searchable = f"{package}/{launchable_activity or ''}"
    return [category for category, pattern in _SENSITIVITY_RULES if pattern.search(searchable)]


def make_version_key(version_name: object, version_code: object) -> str:
    name = str(version_name).strip() if version_name not in {None, ""} else "unknown"
    code = str(version_code).strip() if version_code not in {None, ""} else "unknown"
    return f"code:{code}|name:{name}"


def collect_current_records(client: ReadOnlyAdbClient) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    third_party_packages = set(client.third_party_packages())
    launcher_activities = client.launcher_activities()
    candidate_packages = third_party_packages | set(launcher_activities)
    for package in sorted(candidate_packages, key=str.casefold):
        launchable_activity = launcher_activities.get(package)
        if launchable_activity is None:
            launchable_activity = client.resolve_launcher_activity(package)
        home_activity = client.resolve_home_activity(package)
        metadata = client.package_metadata(package)
        included, reason_code, reason = inclusion_decision(
            package, launchable_activity, home_activity
        )
        categories = sensitivity_categories(package, launchable_activity)
        record = {
            "package": package,
            "launchable_activity": launchable_activity,
            "home_handler_activity": home_activity,
            "discovery_sources": [
                source
                for source, present in (
                    ("third_party_package", package in third_party_packages),
                    ("launcher_activity", package in launcher_activities),
                )
                if present
            ],
            **metadata,
            "preinstalled_user_service_candidate": bool(
                metadata.get("is_system_app") and package in launcher_activities
            ),
            "version_key": make_version_key(
                metadata.get("version_name"), metadata.get("version_code")
            ),
            "included": included,
            "decision_reason_code": reason_code,
            "decision_reason": reason,
            "sensitivity_categories": categories,
            "sensitivity_handling": (
                "heightened_metadata_only" if categories else "standard_metadata_only"
            ),
        }
        records.append(record)
    return sorted(records, key=lambda item: str(item["package"]).casefold())


def observation_identity(package: object, version_key: object) -> str:
    return f"{str(package).strip()}@{str(version_key).strip()}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_physical_run_files(run_directory: Path) -> tuple[Path, Path] | None:
    """Return trusted manifest/screen files for a validation-attested run.

    A mere app ledger is not proof that a physical screen was observed.  The
    marker is deliberately hash-bound to both the manifest and screen ledger;
    quarantine, emulator provenance, dry runs, and post-validation mutation
    all fail closed.
    """

    if run_directory.is_symlink() or (run_directory / "QUARANTINED.json").exists():
        return None
    marker_path = run_directory / VALIDATION_MARKER_NAME
    manifest_path = run_directory / "manifest.json"
    screens_path = run_directory / "screens.jsonl"
    for path in (marker_path, manifest_path, screens_path):
        if not path.is_file() or path.is_symlink():
            return None
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(marker, Mapping) or not isinstance(manifest, Mapping):
        return None
    run_id = str(manifest.get("run_id") or "")
    if (
        marker.get("schema_version") != 1
        or marker.get("status") != "passed"
        or marker.get("validator") != "Validate-RealDeviceObservationCorpus.py"
        or marker.get("run_id") != run_id
        or marker.get("provenance") != PROVENANCE
        or marker.get("device_serial") != EXPECTED_SERIAL
        or marker.get("is_emulator") is not False
        or marker.get("manifest_sha256") != _sha256_file(manifest_path)
        or marker.get("screens_sha256") != _sha256_file(screens_path)
    ):
        return None
    if (
        manifest.get("run_id") != run_id
        or manifest.get("provenance") != PROVENANCE
        or manifest.get("dataset_role") != DATASET_ROLE
        or manifest.get("device_serial") != EXPECTED_SERIAL
        or manifest.get("is_emulator") is not False
        # A validated first-screen capture is an initial seed, not proof that
        # the app's function graph was explored. Only a validated safe-explore
        # run can move a version out of the unobserved priority cohort.
        or manifest.get("collection_mode") != "safe_explore"
        or manifest.get("status") not in {"completed", "incomplete"}
        or manifest.get("canonical_catalog_version") != CANONICAL_CATALOG_VERSION
        or manifest.get("canonical_catalog_sha256") != CANONICAL_CATALOG_SHA256
        or manifest.get("canonical_equivalence_sha256") != CANONICAL_EQUIVALENCE_SHA256
    ):
        return None
    return manifest_path, screens_path


def load_observed_versions(observation_root: Path) -> set[str]:
    """Read version evidence only from validated physical screen ledgers."""

    identities: set[str] = set()
    if not observation_root.exists():
        return identities
    for run_directory in sorted(
        (path for path in observation_root.iterdir() if path.is_dir()),
        key=lambda item: str(item),
    ):
        trusted = _validated_physical_run_files(run_directory)
        if trusted is None:
            continue
        _manifest_path, path = trusted
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            try:
                payload = json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, Mapping):
                continue
            package = payload.get("app_package") or payload.get("package")
            if not isinstance(package, str) or not PACKAGE_RE.fullmatch(package):
                continue
            version_name = payload.get("app_version") or payload.get("version_name")
            version_code = payload.get("version_code")
            if version_name or version_code:
                identities.add(
                    observation_identity(package, make_version_key(version_name, version_code))
                )
            if version_name:
                identities.add(f"{package}@name:{str(version_name).strip()}")
    return identities


def _was_observed(record: Mapping[str, object], observed_versions: set[str]) -> bool:
    identity = observation_identity(record["package"], record["version_key"])
    name_identity = f"{record['package']}@name:{record.get('version_name') or 'unknown'}"
    return identity in observed_versions or name_identity in observed_versions


def _prior_records(previous_snapshot: Mapping[str, object] | None) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    if not previous_snapshot:
        return records
    for field in ("included_apps", "excluded_apps"):
        values = previous_snapshot.get(field, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, Mapping):
                continue
            package = item.get("package")
            if isinstance(package, str) and PACKAGE_RE.fullmatch(package):
                records[package] = dict(item)
    return records


def _snapshot_id_from(discovered_at: str, device: Mapping[str, object]) -> str:
    timestamp = re.sub(r"[^0-9A-Za-z]+", "", discovered_at)[:24] or "unknown-time"
    digest = hashlib.sha256(_canonical_json(device).encode("utf-8")).hexdigest()[:10]
    return f"{timestamp}-{digest}"


def build_snapshot(
    current_records: Sequence[Mapping[str, object]],
    *,
    device: Mapping[str, object],
    discovered_at: str,
    previous_snapshot: Mapping[str, object] | None = None,
    observed_versions: Iterable[str] = (),
    snapshot_id: str | None = None,
) -> dict[str, object]:
    if device.get("serial") != EXPECTED_SERIAL or device.get("is_emulator") is not False:
        raise InventoryDiscoveryError("snapshot device must be the designated physical phone")
    if not str(discovered_at).strip():
        raise InventoryDiscoveryError("discovered_at must not be empty")
    observed = set(observed_versions)
    prior = _prior_records(previous_snapshot)
    current_packages: set[str] = set()
    included_apps: list[dict[str, object]] = []
    excluded_apps: list[dict[str, object]] = []

    for source in sorted(current_records, key=lambda item: str(item.get("package", "")).casefold()):
        record = dict(source)
        package = _validate_package(str(record.get("package", "")))
        if package in current_packages:
            raise InventoryDiscoveryError(f"duplicate current package record: {package}")
        current_packages.add(package)
        if "version_key" not in record:
            record["version_key"] = make_version_key(
                record.get("version_name"), record.get("version_code")
            )
        previous = prior.get(package)
        if previous is None:
            change_status = "new"
        elif previous.get("version_key") != record.get("version_key"):
            change_status = "updated"
        else:
            change_status = "unchanged"
        record["change_status"] = change_status
        record["observation_status"] = (
            "observed_current_version" if _was_observed(record, observed) else "unobserved_current_version"
        )
        if record.get("included") is True:
            included_apps.append(record)
        else:
            excluded_apps.append(record)

    removed_apps: list[dict[str, object]] = []
    for package in sorted(set(prior) - current_packages, key=str.casefold):
        previous = prior[package]
        removed_apps.append(
            {
                "package": package,
                "version_name": previous.get("version_name"),
                "version_code": previous.get("version_code"),
                "version_key": previous.get("version_key"),
                "previously_included": previous.get("included") is True,
                "change_status": "removed_against_previous",
            }
        )

    def priority_key(record: Mapping[str, object]) -> tuple[int, int, int, str]:
        status = record.get("change_status")
        observation_status = record.get("observation_status")
        if status == "new":
            group = 0
        elif status == "updated":
            group = 1
        elif observation_status == "unobserved_current_version":
            group = 2
        else:
            group = 3
        package = str(record["package"])
        target_rank = PRIORITY_TARGET_RANK.get(package)
        return (
            group,
            0 if target_rank is not None else 1,
            target_rank if target_rank is not None else len(PRIORITY_TARGET_RANK),
            package.casefold(),
        )

    prioritized_apps: list[dict[str, object]] = []
    for rank, record in enumerate(sorted(included_apps, key=priority_key), start=1):
        if record["change_status"] == "new":
            reason = "new_package"
        elif record["change_status"] == "updated":
            reason = "updated_version"
        elif record["observation_status"] == "unobserved_current_version":
            reason = (
                "priority_target_current_version_unobserved"
                if record["package"] in PRIORITY_TARGET_RANK
                else "current_version_unobserved"
            )
        else:
            reason = "unchanged_observed"
        prioritized_apps.append(
            {
                "priority_rank": rank,
                "package": record["package"],
                "version_key": record["version_key"],
                "change_status": record["change_status"],
                "observation_status": record["observation_status"],
                "priority_reason": reason,
                "sensitivity_categories": list(record.get("sensitivity_categories", [])),
                "sensitivity_handling": record.get("sensitivity_handling"),
            }
        )

    chosen_snapshot_id = snapshot_id or _snapshot_id_from(discovered_at, device)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", chosen_snapshot_id):
        raise InventoryDiscoveryError("snapshot_id contains unsafe filename characters")
    summary = {
        "discovered_packages": len(current_packages),
        "included_apps": len(included_apps),
        "excluded_apps": len(excluded_apps),
        "new": sum(item["change_status"] == "new" for item in included_apps + excluded_apps),
        "updated": sum(item["change_status"] == "updated" for item in included_apps + excluded_apps),
        "unchanged": sum(item["change_status"] == "unchanged" for item in included_apps + excluded_apps),
        "removed_against_previous": len(removed_apps),
        "unobserved_included_apps": sum(
            item["observation_status"] == "unobserved_current_version" for item in included_apps
        ),
    }
    return {
        "schema_version": 1,
        "snapshot_id": chosen_snapshot_id,
        "provenance": PROVENANCE,
        "dataset_role": DATASET_ROLE,
        "review_status": REVIEW_STATUS,
        "route_lifecycle": ROUTE_LIFECYCLE,
        "canonical_catalog_mutation": False,
        "canonical_catalog": {
            "version": CANONICAL_CATALOG_VERSION,
            "sha256": CANONICAL_CATALOG_SHA256,
            "equivalence_sha256": CANONICAL_EQUIVALENCE_SHA256,
            "counts": dict(CANONICAL_COUNTS),
        },
        "device": dict(device),
        "discovered_at": discovered_at,
        "previous_snapshot_id": (
            previous_snapshot.get("snapshot_id") if previous_snapshot else None
        ),
        "collection_policy": {
            "package_commands": [
                "adb -s <exact-serial> shell pm list packages -3 --user 0",
                "adb -s <exact-serial> shell cmd package query-activities --brief --user 0 -a android.intent.action.MAIN -c android.intent.category.LAUNCHER",
            ],
            "read_only": True,
            "launches_apps": False,
            "mutates_device": False,
            "content_scope": "package_metadata_only",
            "stores_human_content": False,
            "raw_adb_output_persisted": False,
        },
        "sensitivity_policy": {
            "categories": [category for category, _pattern in _SENSITIVITY_RULES],
            "classification_source": "package_and_launcher_component_names_only",
            "human_content_collected": False,
        },
        "summary": summary,
        "included_apps": included_apps,
        "excluded_apps": excluded_apps,
        "removed_apps": removed_apps,
        "prioritized_apps": prioritized_apps,
    }


def _snapshot_files(output_root: Path) -> list[Path]:
    if not output_root.exists():
        return []
    return sorted(output_root.glob("inventory-*.json"), key=lambda item: item.name)


def load_previous_snapshot(
    output_root: Path, *, exclude_snapshot_id: str | None = None
) -> dict[str, object] | None:
    candidates: list[tuple[str, str, dict[str, object]]] = []
    for path in _snapshot_files(output_root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        snapshot_id = str(payload.get("snapshot_id", ""))
        if exclude_snapshot_id and snapshot_id == exclude_snapshot_id:
            continue
        if payload.get("provenance") != PROVENANCE:
            continue
        if payload.get("device", {}).get("serial") != EXPECTED_SERIAL:
            continue
        candidates.append((str(payload.get("discovered_at", "")), snapshot_id, payload))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2]


def write_snapshot_atomic(snapshot: Mapping[str, object], output_root: Path) -> SnapshotWriteResult:
    snapshot_id = str(snapshot.get("snapshot_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", snapshot_id):
        raise InventoryDiscoveryError("snapshot has no safe snapshot_id")
    if snapshot.get("device", {}).get("serial") != EXPECTED_SERIAL:
        raise InventoryDiscoveryError("refusing to write snapshot for another device")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / f"inventory-{snapshot_id}.json"
    encoded = (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if destination.exists():
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InventoryDiscoveryError(
                f"existing snapshot cannot be resumed safely: {destination}"
            ) from error
        if _canonical_json(existing) != _canonical_json(snapshot):
            raise InventoryDiscoveryError(
                f"snapshot id collision with different content: {snapshot_id}"
            )
        return SnapshotWriteResult(destination, True)

    temporary = output_root / f".{destination.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists():
            existing = json.loads(destination.read_text(encoding="utf-8"))
            if _canonical_json(existing) != _canonical_json(snapshot):
                raise InventoryDiscoveryError(
                    f"snapshot id collision with different content: {snapshot_id}"
                )
            return SnapshotWriteResult(destination, True)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return SnapshotWriteResult(destination, False)


def discover(
    client: ReadOnlyAdbClient,
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    observation_root: Path = DEFAULT_OBSERVATION_ROOT,
    discovered_at: str | None = None,
    snapshot_id: str | None = None,
) -> tuple[dict[str, object], SnapshotWriteResult]:
    client.verify_physical_device()
    device = client.device_metadata()
    timestamp = discovered_at or utc_now()
    effective_snapshot_id = snapshot_id or _snapshot_id_from(timestamp, device)
    previous = load_previous_snapshot(output_root, exclude_snapshot_id=effective_snapshot_id)
    records = collect_current_records(client)
    snapshot = build_snapshot(
        records,
        device=device,
        discovered_at=timestamp,
        previous_snapshot=previous,
        observed_versions=load_observed_versions(observation_root),
        snapshot_id=effective_snapshot_id,
    )
    return snapshot, write_snapshot_atomic(snapshot, output_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover user-facing apps on the designated physical phone without launching them."
    )
    parser.add_argument("--serial", default=EXPECTED_SERIAL)
    parser.add_argument("--adb-path", default="adb")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--observation-root", type=Path, default=DEFAULT_OBSERVATION_ROOT)
    parser.add_argument("--snapshot-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        client = ReadOnlyAdbClient(
            serial=args.serial,
            adb_path=args.adb_path,
            timeout_seconds=args.timeout_seconds,
        )
        snapshot, result = discover(
            client,
            output_root=args.output_root.resolve(),
            observation_root=args.observation_root.resolve(),
            snapshot_id=args.snapshot_id,
        )
    except (InventoryDiscoveryError, OSError, subprocess.SubprocessError) as error:
        print(f"inventory discovery failed: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "snapshot_id": snapshot["snapshot_id"],
                "path": str(result.path),
                "resumed_existing": result.resumed_existing,
                "summary": snapshot["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
