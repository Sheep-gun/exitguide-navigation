from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[3]
INSTALLER_PATH = REPO_ROOT / "scripts" / "Install-EmulatorObservationApps.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("exitguide_emulator_installer", INSTALLER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_compose_duplicate_is_one_action(module) -> None:
    xml = """<?xml version='1.0'?>
    <hierarchy>
      <node text='' content-desc='Install' enabled='true' bounds='[10,20][110,70]'>
        <node text='Install' content-desc='' enabled='true' bounds='[10,20][110,70]' />
      </node>
    </hierarchy>"""
    actions = module.visible_actions(xml, module.INSTALL_LABELS)
    assert len(actions) == 1
    assert actions[0].center == (60, 45)


def check_identity_boundary_is_fail_closed(module) -> None:
    adult_verification = "\uc131\uc778 \uc778\uc99d"
    phone = "\ud734\ub300\uc804\ud654"
    xml = f"""<?xml version='1.0'?>
    <hierarchy>
      <node text='{adult_verification}' class='android.widget.TextView' enabled='true' bounds='[0,0][200,50]' />
      <node text='' hint='{phone}' class='android.widget.EditText' enabled='true' bounds='[0,60][200,120]' />
    </hierarchy>"""
    assert module.identity_boundary(xml) == "authentication_or_identity_boundary"


def check_manifest_governance(module) -> None:
    with TemporaryDirectory(prefix="exitguide-installer-unit-") as directory:
        root = Path(directory)
        valid = root / "valid.json"
        valid.write_text(
            json.dumps(
                {
                    "dataset_role": "emulator_observation_candidate",
                    "canonical_catalog_mutation": False,
                    "safety_policy": {"install_free_apps_only": True},
                    "apps": [
                        {
                            "app_name": "Example",
                            "app_package": "com.example.safe",
                            "install_mode": "play_store",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        apps = module.load_apps(valid, set())
        assert [item["app_package"] for item in apps] == ["com.example.safe"]

        unsafe = root / "unsafe.json"
        payload = json.loads(valid.read_text(encoding="utf-8"))
        payload["canonical_catalog_mutation"] = True
        unsafe.write_text(json.dumps(payload), encoding="utf-8")
        try:
            module.load_apps(unsafe, set())
        except ValueError as error:
            assert "canonical" in str(error)
        else:
            raise AssertionError("canonical mutation manifest must be rejected")


def main() -> None:
    module = load_installer()
    check_compose_duplicate_is_one_action(module)
    check_identity_boundary_is_fail_closed(module)
    check_manifest_governance(module)
    print("emulator observation installer checks ok")


if __name__ == "__main__":
    main()
