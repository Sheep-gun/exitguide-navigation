from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.navigation_contracts import (  # noqa: E402
    DecideRequest,
    NavigationCandidate,
    ObserveRequest,
    ScreenObservation,
)
from app.services.navigation_decision_memory import NavigationDecisionMemory  # noqa: E402
from app.services.navigation_model_clients import (  # noqa: E402
    Exaone45VisionClient,
    KExaoneResearchClient,
)
from app.services.navigation_research_policy import (  # noqa: E402
    AndroidWorldResearchPolicy,
    ReflectionTriggerPolicy,
)
from app.services.navigation_runtime import NavigationRuntime  # noqa: E402
from app.services.navigation_runtime_store import NavigationRuntimeStore  # noqa: E402


def _response(payload: dict[str, object]) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}


def _tool_response(name: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(payload, ensure_ascii=False),
                            },
                        }
                    ],
                }
            }
        ]
    }


class ScriptedKClient:
    configured = True

    def __init__(self) -> None:
        self.plan_calls = 0
        self.verifier_actions: list[str] = []

    def complete(self, *, messages, **_kwargs):
        system = str(messages[0]["content"])
        if "high-level planner" in system:
            assert _kwargs["tools"][0]["function"]["name"] == "submit_navigation_subgoal"
            self.plan_calls += 1
            assert "Do not choose an action" in system
            packet = json.loads(messages[1]["content"])
            assert "app_package" not in packet
            return _tool_response(
                "submit_navigation_subgoal",
                {
                    "stage": "hub_discovery",
                    "immediate_subgoal": "계정 또는 프로필 허브를 연다",
                    "expected_outcome": "계정 관리 메뉴가 보이는 화면",
                    "target_roles": ["account_hub", "profile_hub"],
                }
            )
        if "V-Droid-style verifier" in system:
            assert _kwargs["tools"][0]["function"]["name"] == "score_navigation_candidate"
            packet = json.loads(messages[1]["content"])
            action = packet["candidate_action"]
            if action["name"] == "click":
                key = f"click:{action['candidate_id']}"
            elif action["name"] == "scroll":
                key = f"scroll:{action['direction']}"
            else:
                key = action["name"]
            self.verifier_actions.append(key)
            scores = {
                "click:profile": 0.93,
                "click:search": 0.04,
                "scroll:down": 0.12,
                "wait_and_observe": 0.08,
                "stop_for_user": 0.02,
            }
            return _tool_response(
                "score_navigation_candidate",
                {
                    "helpful_probability": scores[key],
                    "expected_progress": "account hub" if key == "click:profile" else "unlikely",
                    "reason": f"scripted score for {key}",
                }
            )
        if "trajectory reflector" in system:
            return _response(
                {"outcome": "failed", "reason": "repeat loop", "recovery_hint": "back"}
            )
        if "global completion reflector" in system:
            return _response(
                {"outcome": "met", "reason": "signature met", "recovery_hint": "stop_for_user"}
            )
        raise AssertionError(system)


class ScriptedVisionClient:
    configured = True

    def __init__(self) -> None:
        self.perception_calls = 0
        self.reflection_calls = 0

    def complete(self, *, messages, **_kwargs):
        system = str(messages[0]["content"])
        if "visual perception module" in system:
            self.perception_calls += 1
            return _response(
                {
                    "semantic_summary": "홈 하단에 계정 진입점이 있는 화면",
                    "candidate_annotations": [
                        {"candidate_id": "profile", "icon_semantics": "사람 모양 프로필"},
                        {"candidate_id": "invented-id", "icon_semantics": "환각 후보"},
                    ],
                }
            )
        if "on-demand action reflector" in system:
            self.reflection_calls += 1
            return _response(
                {"outcome": "failed", "reason": "화면이 바뀌지 않음", "recovery_hint": "back"}
            )
        raise AssertionError(system)


def _load_migration_module():
    path = ROOT / "scripts" / "Migrate-NavigationDecisionDb.py"
    spec = importlib.util.spec_from_file_location("navigation_research_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_decision_db(path: Path) -> None:
    migration = _load_migration_module()
    connection = sqlite3.connect(path)
    connection.executescript((ROOT / "db" / "navigation_decision_v1.sql").read_text(encoding="utf-8"))
    migration.seed_database(connection, "b" * 64)
    connection.commit()
    connection.close()


def _screen() -> ScreenObservation:
    return ScreenObservation(
        window_title="홈",
        activity_name="android.view.View",
        candidates=[
            NavigationCandidate(candidate_id="profile", label="마이페이지", role="button"),
            NavigationCandidate(candidate_id="search", label="검색", role="button"),
        ],
    )


def main() -> None:
    k_transport = ScriptedKClient()
    vision_transport = ScriptedVisionClient()
    k_exaone = KExaoneResearchClient(k_transport)
    exaone_vlm = Exaone45VisionClient(vision_transport)
    policy = AndroidWorldResearchPolicy(
        k_exaone=k_exaone,
        exaone_vlm=exaone_vlm,
        allow_model_fallback=False,
        verifier_workers=2,
    )

    perceived = exaone_vlm.perceive(
        goal_text="회원 탈퇴 메뉴 찾기",
        screen=_screen(),
        screenshot_data_url="data:image/png;base64,AA==",
    )
    assert [item.candidate_id for item in perceived.screen.candidates] == ["profile", "search"]
    assert perceived.screen.candidates[0].icon_semantics == "사람 모양 프로필"

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        decision_db = root / "decision.sqlite"
        _build_decision_db(decision_db)
        runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(root / "runtime.sqlite"),
            policy=policy,
        )
        decision = runtime.decide(
            DecideRequest(
                request_id="research-1",
                app_package="heldout.app",
                goal_text="회원 탈퇴 메뉴를 찾아줘",
                screenshot_data_url="data:image/png;base64,AA==",
                screen=_screen(),
            )
        )
        assert decision.plan.source == "k_exaone"
        assert decision.action.name == "click" and decision.action.candidate_id == "profile"
        assert decision.perception_provider == "exaone_4_5"
        assert decision.verifier_provider == "k_exaone_verifier"
        assert k_transport.plan_calls == 1
        assert sorted(k_transport.verifier_actions) == sorted(
            ["click:profile", "click:search", "scroll:down", "wait_and_observe", "stop_for_user"]
        )

        observation = runtime.observe(
            ObserveRequest(
                request_id="research-observe-1",
                decision_id=decision.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                before_screenshot_data_url="data:image/png;base64,AA==",
                after_screenshot_data_url="data:image/png;base64,AA==",
                next_screen=_screen(),
            )
        )
        assert observation.reflection_level == "action"
        assert vision_transport.reflection_calls == 1
        assert observation.recovery_action is not None
        assert observation.recovery_action.name == "back"
        assert observation.knowledge_revision_queued is True

    trigger = ReflectionTriggerPolicy()
    level, _ = trigger.choose_level(
        outcome_type="navigated",
        execution_succeeded=True,
        action_confidence=0.9,
        reflection_on_demand=False,
        action_name="click",
        recent_history=[
            {"action_name": "click", "screen_fingerprint": "same", "progress_label": "advanced"},
            {"action_name": "click", "screen_fingerprint": "same", "progress_label": "unknown"},
        ],
    )
    assert level == "trajectory"
    level, _ = trigger.choose_level(
        outcome_type="destination_reached",
        execution_succeeded=True,
        action_confidence=0.9,
        reflection_on_demand=False,
        action_name="click",
        recent_history=[],
    )
    assert level == "global"
    print("navigation_research_architecture_unit: ok")


if __name__ == "__main__":
    main()
