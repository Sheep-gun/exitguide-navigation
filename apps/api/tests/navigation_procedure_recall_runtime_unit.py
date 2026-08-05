from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

from app.navigation_contracts import DecideRequest, NavigationCandidate, ScreenObservation
from app.services.navigation_decision_memory import NavigationDecisionMemory
from app.services.navigation_extensions import (
    ExtensionMode,
    NavigationExtensionRuntime,
    build_procedure_catalog,
)
from app.services.navigation_research_policy import AndroidWorldResearchPolicy
from app.services.navigation_runtime import NavigationRuntime, _unambiguous_db_goal_phrase
from app.services.navigation_runtime_store import NavigationRuntimeStore


def find_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "apps" / "api").is_dir() and (parent / "fixtures").is_dir():
            return parent
    raise RuntimeError("ExitGuide Navigation repository root was not found")


ROOT = find_root()
SEED_PATH = ROOT / "fixtures" / "navigation-extensions" / "procedures.v1.json"
POLICY_PATH = ROOT / "contracts" / "navigation-safety-rules.v1.json"
ARCHITECTURE_TEST = ROOT / "apps" / "api" / "tests" / "navigation_research_architecture_unit.py"
PROFILE_MIGRATOR = ROOT / "scripts" / "Migrate-NavigationExperienceProfile.py"


class ForbiddenPlanner:
    configured = True
    name = "forbidden_planner"
    active_name = "forbidden_planner"
    fallback_name = None
    fallback_configured = False

    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, name: str):
        if name.startswith(("classify", "plan", "verify", "reflect")):
            def forbidden_call(**_kwargs):
                self.calls += 1
                raise AssertionError(f"planner model must not be called: {name}")

            return forbidden_call
        raise AttributeError(name)


class DisabledVision:
    configured = False
    name = "disabled_vision"


def build_decision_db(path: Path) -> None:
    spec = importlib.util.spec_from_file_location("navigation_architecture_fixture", ARCHITECTURE_TEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    legacy_path = path.with_name("legacy-decision.sqlite")
    module._build_decision_db(legacy_path)
    migration_spec = importlib.util.spec_from_file_location(
        "navigation_profile_migrator", PROFILE_MIGRATOR
    )
    assert migration_spec is not None and migration_spec.loader is not None
    migrator = importlib.util.module_from_spec(migration_spec)
    migration_spec.loader.exec_module(migrator)
    migrator.migrate(legacy_path, path)


def build_active_catalog(root: Path) -> Path:
    packet = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    procedure = packet["procedures"][0]
    packet["procedures"] = [procedure]
    procedure.update(
        {
            "procedure_id": "example.account_hub.fast.v1",
            "status": "active",
            "app_package": "example.app",
            "compatible_app_versions": ["1.2.*"],
            "locales": ["ko-KR"],
            "execution_mode": "deterministic_fast_path",
            "validation_count": 3,
            "fast_path_min_validation_count": 3,
        }
    )
    packet_path = root / "active-procedures.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    catalog_path = root / "active-procedures.sqlite"
    build_procedure_catalog(packet_path, catalog_path)
    return catalog_path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="exitguide-procedure-runtime-") as raw:
        root = Path(raw)
        decision_db = root / "decision.sqlite"
        build_decision_db(decision_db)
        planner = ForbiddenPlanner()
        policy = AndroidWorldResearchPolicy(
            planner_model=planner,
            exaone_vlm=DisabledVision(),
            allow_model_fallback=False,
            planner_mode="selective",
            vlm_mode="disabled",
        )
        extension = NavigationExtensionRuntime.from_paths(
            mode=ExtensionMode.ENFORCE,
            procedure_catalog_path=build_active_catalog(root),
            policy_path=POLICY_PATH,
            extension_db_path=root / "extension.sqlite",
        )
        memory = NavigationDecisionMemory(decision_db)
        assert _unambiguous_db_goal_phrase(
            memory=memory,
            goal_text="구독 해지",
            locale="ko-KR",
            goal_id="membership.cancel",
        )
        assert not _unambiguous_db_goal_phrase(
            memory=memory,
            goal_text="구독 해지와 회원 탈퇴 중 하나",
            locale="ko-KR",
            goal_id="membership.cancel",
        )
        runtime = NavigationRuntime(
            memory=memory,
            store=NavigationRuntimeStore(root / "runtime.sqlite"),
            policy=policy,
            extension=extension,
            goal_fast_path_confidence=0.92,
        )
        response = runtime.decide(
            DecideRequest(
                request_id="procedure-fast-path-1",
                app_package="example.app",
                app_version="1.2.9",
                locale="ko-KR",
                goal_text="구독 해지",
                screen=ScreenObservation(
                    window_title="홈",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="profile",
                            label="마이페이지",
                            role="button",
                        ),
                        NavigationCandidate(
                            candidate_id="search",
                            label="검색",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert response.goal.provider == "python_high_confidence_goal_phrase"
        assert response.action.name == "click"
        assert response.action.candidate_id == "profile"
        assert response.procedure_id == "example.account_hub.fast.v1"
        assert response.procedure_fast_path_eligible is True
        assert response.procedure_fast_path_used is True
        assert planner.calls == 0
    print("N100 Procedure Recall runtime check passed: zero planner calls")


if __name__ == "__main__":
    main()
