from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "Discover-RealDeviceApps.py"
SPEC = importlib.util.spec_from_file_location("egl_real_device_app_discovery", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
discovery = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = discovery
SPEC.loader.exec_module(discovery)


class FakeAdbRunner:
    def __init__(self, *, qemu: str = "0") -> None:
        self.qemu = qemu
        self.commands: list[list[str]] = []
        self.packages = [
            "com.ahnlab.v3mobileplus",
            "com.binance.dev",
            "com.chbreeze.jikbang4a",
            "com.comento.app",
            "com.dunamu.exchange",
            "com.example.authenticator",
            "com.example.bank",
            "com.example.chat",
            "com.example.general",
            "com.example.maps",
            "com.exitguide.ai",
            "com.github.standardadb",
            "com.instagram.barcelona",
            "com.kakao.taxi",
            "com.netflix.mediaclient",
            "com.nhn.android.nbooks",
            "com.openai.chatgpt",
            "com.petsbe.android.petsbemall",
            "com.sec.android.app.shealth",
            "com.sktelecom.nugu",
            "com.service.noui",
            "com.towneers.www",
            "com.vendor.keyboard",
            "com.vendor.languagepack.ko",
            "com.vendor.launcher",
            "com.vendor.packageinstaller",
            "com.vendor.watchplugin",
            "com.vendor.webview",
            "ctrip.english",
            "kr.co.aladin.third_shop",
            "kr.co.station3.dabang",
            "org.telegram.messenger",
            "org.thoughtcrime.securesms",
            "ni.mh.android.launcher",
        ]

    def __call__(self, command, timeout):
        assert timeout > 0
        values = list(command)
        self.commands.append(values)
        assert values[:3] == ["adb", "-s", discovery.EXPECTED_SERIAL]
        args = tuple(values[3:])
        if args == ("get-state",):
            return b"device\n"
        if args == ("shell", "getprop", "ro.serialno"):
            return f"{discovery.EXPECTED_SERIAL}\n".encode()
        if args == ("shell", "getprop", "ro.kernel.qemu"):
            return f"{self.qemu}\n".encode()
        if args == ("shell", "getprop", "ro.product.model"):
            return "SM-S911N\n"
        if args == ("shell", "getprop", "ro.build.version.release"):
            return "16\n"
        if args == ("shell", "getprop", "persist.sys.locale"):
            return "ko-KR\n"
        if args == ("shell", "pm", "list", "packages", "-3", "--user", "0"):
            return "\n".join(f"package:{package}" for package in reversed(self.packages))
        if args == (
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
            components = [
                "com.google.android.youtube/.app.honeycomb.Shell$HomeActivity",
                "com.android.settings/.Settings",
            ]
            for package in self.packages:
                if package == "com.service.noui":
                    continue
                components.append(f"{package}/.MainActivity")
            return "\n".join(
                [f"{len(components)} activities found:"]
                + [f"  Activity #{index}:\n    {component}" for index, component in enumerate(components)]
            )
        if args[:4] == ("shell", "cmd", "package", "resolve-activity"):
            package = args[-1]
            assert args[-2] == "-p"
            category = args[args.index("-c") + 1]
            if category == "android.intent.category.HOME":
                if package == "com.vendor.launcher":
                    return f"{package}/.RealHomeActivity\n"
                return "No activity found\n"
            if package == "com.service.noui":
                return "No activity found\n"
            special_activities = {
                "com.ahnlab.v3mobileplus": ".mainwebview.SplashActivity",
                "com.binance.dev": "com.eaas.launcher.activities.main.MainActivity",
                "com.kakao.taxi": "com.kakao.t.presentation.launcher.LauncherActivity",
                "com.netflix.mediaclient": ".ui.launch.UIWebViewActivity",
                "com.nhn.android.nbooks": "com.naver.series.home.EntranceActivity",
                "com.petsbe.android.petsbemall": ".ic_launcher",
                "com.sec.android.app.shealth": "com.samsung.android.app.shealth.home.HomeMainActivity",
                "com.towneers.www": ".launcher.LauncherActivity",
                "ctrip.english": "com.ctrip.ibu.myctrip.main.module.home.IBUHomeActivity",
                "ni.mh.android.launcher": ".WebviewActivity",
            }
            activity = special_activities.get(package, ".MainActivity")
            return f"priority=0 preferredOrder=0\n{package}/{activity}\n"
        if args[:3] == ("shell", "dumpsys", "package"):
            package = args[-1]
            versions = {
                "com.example.bank": ("5.4.1", "541"),
                "com.example.chat": ("12.0.0", "1200"),
            }
            name, code = versions.get(package, ("1.0.0", "100"))
            system = package in {"com.google.android.youtube", "com.android.settings"}
            code_path = f"/product/app/{package}" if system else f"/data/app/{package}"
            flags = "HAS_CODE SYSTEM" if system else "HAS_CODE ALLOW_CLEAR_USER_DATA"
            return (
                f"Packages:\n  Package [{package}]\n"
                f"    codePath={code_path}\n"
                f"    versionCode={code} minSdk=26 targetSdk=35\n"
                f"    versionName={name}\n"
                f"    flags=[ {flags} ]\n"
            )
        raise AssertionError(f"unexpected mock ADB command: {args!r}")


def app_record(
    package: str,
    *,
    version_name: str = "1.0.0",
    version_code: str = "100",
    included: bool = True,
):
    launchable = f"{package}/.MainActivity" if included else None
    categories = discovery.sensitivity_categories(package, launchable)
    return {
        "package": package,
        "launchable_activity": launchable,
        "version_name": version_name,
        "version_code": version_code,
        "version_key": discovery.make_version_key(version_name, version_code),
        "package_flags": ["HAS_CODE"],
        "is_system_app": False,
        "code_location": "data",
        "included": included,
        "decision_reason_code": "user_facing_launchable" if included else "non_launchable",
        "decision_reason": "fixture record",
        "sensitivity_categories": categories,
        "sensitivity_handling": (
            "heightened_metadata_only" if categories else "standard_metadata_only"
        ),
    }


def device_metadata():
    return {
        "serial": discovery.EXPECTED_SERIAL,
        "device_type": "physical_android",
        "is_emulator": False,
        "model": "SM-S911N",
        "android_version": "16",
        "locale": "ko-KR",
    }


class RealDeviceAppDiscoveryUnit(unittest.TestCase):
    def test_requires_exact_serial_and_rejects_emulator(self):
        with self.assertRaises(discovery.InventoryDiscoveryError):
            discovery.ReadOnlyAdbClient(serial="OTHER", runner=FakeAdbRunner())
        with self.assertRaises(discovery.InventoryDiscoveryError):
            discovery.ReadOnlyAdbClient(serial="emulator-5554", runner=FakeAdbRunner())

        runner = FakeAdbRunner(qemu="1")
        client = discovery.ReadOnlyAdbClient(runner=runner)
        with self.assertRaises(discovery.InventoryDiscoveryError):
            client.verify_physical_device()
        self.assertTrue(runner.commands)
        self.assertTrue(
            all(command[1:3] == ["-s", discovery.EXPECTED_SERIAL] for command in runner.commands)
        )

    def test_collects_user_zero_metadata_without_mutation_or_launch(self):
        runner = FakeAdbRunner()
        client = discovery.ReadOnlyAdbClient(runner=runner)
        client.verify_physical_device()
        self.assertEqual(
            client.device_metadata(),
            device_metadata(),
        )
        records = discovery.collect_current_records(client)

        expected_inventory_command = [
            "adb",
            "-s",
            discovery.EXPECTED_SERIAL,
            "shell",
            "pm",
            "list",
            "packages",
            "-3",
            "--user",
            "0",
        ]
        self.assertIn(expected_inventory_command, runner.commands)
        expected_launcher_query = [
            "adb",
            "-s",
            discovery.EXPECTED_SERIAL,
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
        ]
        self.assertIn(expected_launcher_query, runner.commands)
        self.assertEqual(
            [record["package"] for record in records],
            sorted(
                set(runner.packages)
                | {"com.google.android.youtube", "com.android.settings"},
                key=str.casefold,
            ),
        )

        bank = next(record for record in records if record["package"] == "com.example.bank")
        self.assertEqual(bank["version_name"], "5.4.1")
        self.assertEqual(bank["version_code"], "541")
        self.assertEqual(bank["version_key"], "code:541|name:5.4.1")
        self.assertEqual(bank["launchable_activity"], "com.example.bank/.MainActivity")
        self.assertIsNone(bank["home_handler_activity"])
        self.assertEqual(bank["package_flags"], ["ALLOW_CLEAR_USER_DATA", "HAS_CODE"])
        self.assertFalse(bank["is_system_app"])
        self.assertEqual(bank["code_location"], "data")

        forbidden_tokens = {
            "install",
            "uninstall",
            "delete",
            "rm",
            "clear",
            "force-stop",
            "monkey",
            "input",
            "tap",
            "swipe",
        }
        for command in runner.commands:
            args = command[3:]
            self.assertFalse(forbidden_tokens.intersection(args), command)
            self.assertNotEqual(args[:3], ["shell", "am", "start"])
            self.assertNotEqual(args[:3], ["shell", "cmd", "activity"])

        command_count = len(runner.commands)
        with self.assertRaises(discovery.InventoryDiscoveryError):
            client.run("shell", "am", "start", "com.example.bank/.MainActivity")
        with self.assertRaises(discovery.InventoryDiscoveryError):
            client.run("shell", "pm", "clear", "com.example.bank")
        self.assertEqual(len(runner.commands), command_count, "rejected commands must not reach runner")

    def test_filters_non_service_apps_and_marks_sensitive_metadata(self):
        records = discovery.collect_current_records(
            discovery.ReadOnlyAdbClient(runner=FakeAdbRunner())
        )
        by_package = {record["package"]: record for record in records}
        expected_exclusions = {
            "com.android.settings": "system_os_component",
            "com.exitguide.ai": "exitguide_self",
            "com.github.standardadb": "non_service_developer_tool",
            "com.service.noui": "non_launchable",
            "com.vendor.keyboard": "keyboard_or_input_method",
            "com.vendor.languagepack.ko": "language_pack",
            "com.vendor.launcher": "launcher",
            "com.vendor.packageinstaller": "installer_or_permission_controller",
            "com.vendor.watchplugin": "accessory_or_helper",
            "com.vendor.webview": "non_service_infrastructure",
        }
        for package, reason_code in expected_exclusions.items():
            self.assertFalse(by_package[package]["included"], package)
            self.assertEqual(by_package[package]["decision_reason_code"], reason_code)
            self.assertTrue(by_package[package]["decision_reason"])

        for package in (
            "com.ahnlab.v3mobileplus",
            "com.binance.dev",
            "com.chbreeze.jikbang4a",
            "com.binance.dev",
            "com.comento.app",
            "com.dunamu.exchange",
            "com.example.authenticator",
            "com.example.bank",
            "com.example.chat",
            "com.example.general",
            "com.example.maps",
            "com.instagram.barcelona",
            "com.kakao.taxi",
            "com.netflix.mediaclient",
            "com.nhn.android.nbooks",
            "com.openai.chatgpt",
            "com.petsbe.android.petsbemall",
            "com.sec.android.app.shealth",
            "com.sktelecom.nugu",
            "com.towneers.www",
            "ctrip.english",
            "kr.co.aladin.third_shop",
            "kr.co.station3.dabang",
            "org.telegram.messenger",
            "org.thoughtcrime.securesms",
            "ni.mh.android.launcher",
            "com.google.android.youtube",
        ):
            self.assertTrue(by_package[package]["included"], package)

        youtube = by_package["com.google.android.youtube"]
        self.assertTrue(youtube["is_system_app"])
        self.assertTrue(youtube["preinstalled_user_service_candidate"])
        self.assertEqual(youtube["discovery_sources"], ["launcher_activity"])
        self.assertEqual(
            youtube["launchable_activity"],
            "com.google.android.youtube/.app.honeycomb.Shell$HomeActivity",
        )

        self.assertEqual(
            by_package["com.vendor.launcher"]["home_handler_activity"],
            "com.vendor.launcher/.RealHomeActivity",
        )
        for package in (
            "com.binance.dev",
            "com.kakao.taxi",
            "com.netflix.mediaclient",
            "com.towneers.www",
            "ni.mh.android.launcher",
        ):
            self.assertIsNone(by_package[package]["home_handler_activity"], package)

        self.assertEqual(
            by_package["com.example.chat"]["sensitivity_categories"],
            ["conversation_message"],
        )
        self.assertEqual(by_package["com.example.bank"]["sensitivity_categories"], ["finance"])
        self.assertEqual(
            by_package["com.example.maps"]["sensitivity_categories"],
            ["real_estate_location"],
        )
        self.assertEqual(
            by_package["com.example.authenticator"]["sensitivity_categories"],
            ["auth_security"],
        )
        self.assertEqual(by_package["com.example.general"]["sensitivity_categories"], [])
        expected_target_classification = {
            "com.instagram.barcelona": ["conversation_message"],
            "kr.co.station3.dabang": ["real_estate_location"],
            "com.openai.chatgpt": ["conversation_message"],
            "org.telegram.messenger": ["conversation_message"],
            "com.chbreeze.jikbang4a": ["real_estate_location"],
            "org.thoughtcrime.securesms": ["conversation_message"],
            "com.kakao.taxi": ["real_estate_location"],
            "ni.mh.android.launcher": ["finance", "health_medical"],
            "com.sec.android.app.shealth": ["health_medical"],
            "com.sktelecom.nugu": [],
            "com.comento.app": [],
            "kr.co.aladin.third_shop": [],
            "com.dunamu.exchange": ["finance"],
            "com.binance.dev": ["finance"],
        }
        for package, categories in expected_target_classification.items():
            self.assertEqual(by_package[package]["sensitivity_categories"], categories, package)

        self.assertEqual(
            discovery.sensitivity_categories("com.kakao.talk", ".MainActivity"),
            ["conversation_message"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.microsoft.office.outlook", ".MainActivity"),
            ["personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.google.android.apps.docs", ".MainActivity"),
            ["personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.android.chrome", ".MainActivity"),
            ["personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.android.vending", ".AssetBrowserActivity"),
            ["finance", "personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories(
                "com.samsung.knox.securefolder", ".SecureFolderShortcutActivity"
            ),
            ["personal_content", "auth_security"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.google.android.apps.bard", ".MainActivity"),
            ["conversation_message", "personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.samsung.android.spay", ".MainActivity"),
            ["finance"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.microsoft.office.excel", ".MainActivity"),
            ["personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.sec.android.app.sbrowser", ".MainActivity"),
            ["personal_content"],
        )
        self.assertEqual(
            discovery.sensitivity_categories("com.samsung.android.app.find", ".MainActivity"),
            ["real_estate_location"],
        )

    def test_deterministic_diff_and_priority_order(self):
        previous = {
            "snapshot_id": "previous-one",
            "included_apps": [
                app_record("com.example.bank", version_name="1.0.0", version_code="100"),
                app_record("com.example.chat"),
                app_record("com.example.other"),
                app_record("com.example.removed"),
            ],
            "excluded_apps": [app_record("com.vendor.launcher", included=False)],
        }
        current = [
            app_record("com.example.other"),
            app_record("com.example.new"),
            app_record("com.example.chat"),
            app_record("com.example.bank", version_name="2.0.0", version_code="200"),
            app_record("com.vendor.launcher", included=False),
        ]
        observed = {
            discovery.observation_identity(
                "com.example.chat", discovery.make_version_key("1.0.0", "100")
            )
        }
        kwargs = {
            "device": device_metadata(),
            "discovered_at": "2026-07-31T08:00:00.000Z",
            "previous_snapshot": previous,
            "observed_versions": observed,
            "snapshot_id": "snapshot-fixed",
        }
        first = discovery.build_snapshot(current, **kwargs)
        second = discovery.build_snapshot(list(reversed(current)), **kwargs)
        self.assertEqual(first, second, "input package order must not affect the snapshot")

        by_package = {
            record["package"]: record
            for record in first["included_apps"] + first["excluded_apps"]
        }
        self.assertEqual(by_package["com.example.new"]["change_status"], "new")
        self.assertEqual(by_package["com.example.bank"]["change_status"], "updated")
        self.assertEqual(by_package["com.example.other"]["change_status"], "unchanged")
        self.assertEqual(by_package["com.example.chat"]["change_status"], "unchanged")
        self.assertEqual(
            by_package["com.example.chat"]["observation_status"],
            "observed_current_version",
        )
        self.assertEqual(
            by_package["com.example.other"]["observation_status"],
            "unobserved_current_version",
        )
        self.assertEqual(first["removed_apps"][0]["package"], "com.example.removed")
        self.assertEqual(
            first["removed_apps"][0]["change_status"], "removed_against_previous"
        )
        self.assertEqual(
            [record["package"] for record in first["prioritized_apps"]],
            [
                "com.example.new",
                "com.example.bank",
                "com.example.other",
                "com.example.chat",
            ],
        )
        self.assertEqual(first["previous_snapshot_id"], "previous-one")
        self.assertEqual(first["provenance"], discovery.PROVENANCE)
        self.assertEqual(first["review_status"], "unreviewed_candidate")
        self.assertEqual(first["route_lifecycle"], "shadow")
        self.assertFalse(first["canonical_catalog_mutation"])
        self.assertEqual(
            first["canonical_catalog"],
            {
                "version": discovery.CANONICAL_CATALOG_VERSION,
                "sha256": discovery.CANONICAL_CATALOG_SHA256,
                "equivalence_sha256": discovery.CANONICAL_EQUIVALENCE_SHA256,
                "counts": discovery.CANONICAL_COUNTS,
            },
        )
        self.assertFalse(first["collection_policy"]["stores_human_content"])
        self.assertFalse(first["sensitivity_policy"]["human_content_collected"])
        self.assertEqual(
            first["sensitivity_policy"]["categories"],
            [category for category, _pattern in discovery._SENSITIVITY_RULES],
        )
        encoded = json.dumps(first, ensure_ascii=False)
        for forbidden_field in (
            "message_text",
            "conversation_text",
            "screen_text",
            "account_identifier",
            "raw_dumpsys",
        ):
            self.assertNotIn(forbidden_field, encoded)

    def test_priority_targets_lead_equally_unobserved_long_tail(self):
        records = [
            app_record("com.zzz.longtail"),
            app_record("com.netflix.mediaclient"),
            app_record("com.aaa.longtail"),
            app_record("com.coupang.mobile"),
        ]
        snapshot = discovery.build_snapshot(
            records,
            device=device_metadata(),
            discovered_at="2026-07-31T08:30:00.000Z",
            previous_snapshot={"included_apps": records, "excluded_apps": []},
            snapshot_id="priority-targets",
        )
        self.assertEqual(
            [item["package"] for item in snapshot["prioritized_apps"]],
            [
                "com.netflix.mediaclient",
                "com.coupang.mobile",
                "com.aaa.longtail",
                "com.zzz.longtail",
            ],
        )
        self.assertEqual(
            snapshot["prioritized_apps"][0]["priority_reason"],
            "priority_target_current_version_unobserved",
        )

    def test_atomic_write_is_resume_safe_and_previous_selection_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            first_snapshot = discovery.build_snapshot(
                [app_record("com.example.one")],
                device=device_metadata(),
                discovered_at="2026-07-31T08:00:00.000Z",
                snapshot_id="snapshot-one",
            )
            first_write = discovery.write_snapshot_atomic(first_snapshot, output_root)
            self.assertFalse(first_write.resumed_existing)
            self.assertTrue(first_write.path.is_file())
            self.assertTrue(first_write.path.read_bytes().endswith(b"\n"))
            self.assertFalse(list(output_root.glob("*.tmp")))
            self.assertFalse(list(output_root.glob(".*.tmp")))

            resumed = discovery.write_snapshot_atomic(first_snapshot, output_root)
            self.assertTrue(resumed.resumed_existing)
            original_bytes = first_write.path.read_bytes()
            collision = json.loads(json.dumps(first_snapshot))
            collision["summary"]["included_apps"] = 999
            with self.assertRaises(discovery.InventoryDiscoveryError):
                discovery.write_snapshot_atomic(collision, output_root)
            self.assertEqual(first_write.path.read_bytes(), original_bytes)

            later_snapshot = discovery.build_snapshot(
                [app_record("com.example.two")],
                device=device_metadata(),
                discovered_at="2026-07-31T09:00:00.000Z",
                previous_snapshot=first_snapshot,
                snapshot_id="snapshot-two",
            )
            discovery.write_snapshot_atomic(later_snapshot, output_root)
            selected = discovery.load_previous_snapshot(output_root)
            self.assertIsNotNone(selected)
            self.assertEqual(selected["snapshot_id"], "snapshot-two")
            selected_excluding_later = discovery.load_previous_snapshot(
                output_root, exclude_snapshot_id="snapshot-two"
            )
            self.assertIsNotNone(selected_excluding_later)
            self.assertEqual(selected_excluding_later["snapshot_id"], "snapshot-one")

    def test_observed_versions_require_hash_bound_validated_physical_screen(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)

            def write_run(
                name: str,
                *,
                provenance: str = discovery.PROVENANCE,
                serial: str = discovery.EXPECTED_SERIAL,
                is_emulator: bool = False,
                collection_mode: str = "safe_explore",
                marker: bool = True,
                quarantine: bool = False,
                tamper_after_marker: bool = False,
            ) -> Path:
                run = root / name
                run.mkdir()
                manifest = {
                    "run_id": name,
                    "provenance": provenance,
                    "dataset_role": provenance,
                    "device_serial": serial,
                    "is_emulator": is_emulator,
                    "collection_mode": collection_mode,
                    "status": "completed",
                    "canonical_catalog_version": discovery.CANONICAL_CATALOG_VERSION,
                    "canonical_catalog_sha256": discovery.CANONICAL_CATALOG_SHA256,
                    "canonical_equivalence_sha256": discovery.CANONICAL_EQUIVALENCE_SHA256,
                }
                manifest_path = run / "manifest.json"
                screens_path = run / "screens.jsonl"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                screens_path.write_text(
                    json.dumps(
                        {
                            "app_package": "com.example.validated",
                            "app_version": "7.1.0",
                            "screen_id": f"screen-{name}",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                if marker:
                    marker_payload = {
                        "schema_version": 1,
                        "status": "passed",
                        "validator": "Validate-RealDeviceObservationCorpus.py",
                        "run_id": name,
                        "provenance": discovery.PROVENANCE,
                        "device_serial": discovery.EXPECTED_SERIAL,
                        "is_emulator": False,
                        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                        "screens_sha256": hashlib.sha256(screens_path.read_bytes()).hexdigest(),
                    }
                    (run / discovery.VALIDATION_MARKER_NAME).write_text(
                        json.dumps(marker_payload), encoding="utf-8"
                    )
                if tamper_after_marker:
                    screens_path.write_text(
                        screens_path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8"
                    )
                if quarantine:
                    (run / "QUARANTINED.json").write_text("{}\n", encoding="utf-8")
                return run

            write_run("valid")
            write_run("unvalidated", marker=False)
            write_run("emulator", provenance="emulator_observation", is_emulator=True)
            write_run("wrong-serial", serial="OTHER")
            write_run("capture-only", collection_mode="capture_only")
            write_run("dry-run", collection_mode="dry_run")
            write_run("quarantined", quarantine=True)
            write_run("tampered", tamper_after_marker=True)

            identities = discovery.load_observed_versions(root)
            self.assertEqual(
                identities,
                {
                    discovery.observation_identity(
                        "com.example.validated",
                        discovery.make_version_key("7.1.0", None),
                    ),
                    "com.example.validated@name:7.1.0",
                },
            )


if __name__ == "__main__":
    unittest.main()
