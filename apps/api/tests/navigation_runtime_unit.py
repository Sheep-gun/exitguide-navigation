from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import get_settings  # noqa: E402
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
    OpenAICompatibleChatClient,
)
from app.services.navigation_research_policy import AndroidWorldResearchPolicy  # noqa: E402
from app.services.navigation_runtime import NavigationRuntime  # noqa: E402
from app.services.navigation_runtime_store import NavigationRuntimeStore  # noqa: E402


def _load_migration_module():
    path = ROOT / "scripts" / "Migrate-NavigationDecisionDb.py"
    spec = importlib.util.spec_from_file_location("navigation_decision_migration_runtime", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_decision_db(path: Path) -> None:
    migration = _load_migration_module()
    connection = sqlite3.connect(path)
    connection.executescript((ROOT / "db" / "navigation_decision_v1.sql").read_text(encoding="utf-8"))
    migration.seed_database(connection, "a" * 64)
    connection.commit()
    connection.close()


def _policy() -> AndroidWorldResearchPolicy:
    return AndroidWorldResearchPolicy(
        k_exaone=KExaoneResearchClient(
            OpenAICompatibleChatClient(
                api_key="", base_url="https://example.invalid/v1", model="test-k-exaone"
            )
        ),
        exaone_vlm=Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key="", base_url="", model="test-exaone-4.5"
            )
        ),
        allow_model_fallback=True,
    )


def _account_screen() -> ScreenObservation:
    return ScreenObservation(
        window_title="홈",
        activity_name="android.view.View",
        navigation_depth=0,
        candidates=[
            NavigationCandidate(
                candidate_id="profile",
                label="마이페이지",
                role="button",
                icon_semantics="프로필 사람 아이콘",
                nearby_text="내 정보와 설정",
                position_bucket="bottom",
            ),
            NavigationCandidate(candidate_id="search", label="검색", role="button"),
        ],
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        decision_db = temporary_path / "decision.sqlite"
        runtime_db = temporary_path / "runtime.sqlite"
        _build_decision_db(decision_db)
        runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(runtime_db),
            policy=_policy(),
        )
        first = runtime.decide(
            DecideRequest(
                request_id="request-1",
                app_package="evaluation.unseen.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=_account_screen(),
            )
        )
        assert first.goal.status == "recognized"
        assert first.action.name == "click" and first.action.candidate_id == "profile"
        assert first.evidence_case_ids == []

        no_change = runtime.observe(
            ObserveRequest(
                request_id="request-1-observe",
                decision_id=first.decision_id,
                connectivity_status="observed",
                next_screen=_account_screen(),
            )
        )
        assert no_change.outcome_type == "no_change"
        assert no_change.candidate_forbidden is True
        assert no_change.knowledge_revision_queued is True

        retry = runtime.decide(
            DecideRequest(
                request_id="request-2",
                session_id=first.session_id,
                app_package="evaluation.unseen.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                step_ordinal=1,
                screen=_account_screen(),
            )
        )
        assert retry.action.candidate_id != "profile"
        assert any(value.candidate_id == "profile" and value.forbidden for value in retry.candidate_values)

        disconnected = runtime.observe(
            ObserveRequest(
                request_id="request-2-observe",
                decision_id=retry.decision_id,
                connectivity_status="transport_error",
            )
        )
        assert disconnected.outcome_type == "unknown"
        assert disconnected.state_changed is None
        assert disconnected.candidate_forbidden is False
        assert disconnected.knowledge_revision_queued is False
        assert disconnected.recovery_action is not None
        assert disconnected.recovery_action.name == "wait_and_observe"

        dangerous = runtime.decide(
            DecideRequest(
                request_id="request-3",
                app_package="evaluation.another.app",
                goal_text="멤버십을 해지하고 싶어",
                screen=ScreenObservation(
                    window_title="멤버십 결제 해지",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="confirm-cancel",
                            label="해지 확정",
                            role="button",
                            risk_level="high",
                        )
                    ],
                ),
            )
        )
        assert dangerous.action.name == "stop_for_user"

        out_of_scope = runtime.decide(
            DecideRequest(
                request_id="request-4",
                app_package="evaluation.another.app",
                goal_text="오늘 날씨를 알려줘",
                screen=_account_screen(),
            )
        )
        assert out_of_scope.goal.status == "out_of_scope"
        assert out_of_scope.action.name == "stop_for_user"

        try:
            NavigationCandidate(candidate_id="bad", label="버튼", x=100, y=200)
        except ValidationError:
            pass
        else:
            raise AssertionError("coordinate fields were accepted")

        previous = {key: os.environ.get(key) for key in (
            "NAVIGATION_DECISION_DB_PATH",
            "NAVIGATION_RUNTIME_DB_PATH",
        )}
        os.environ["NAVIGATION_DECISION_DB_PATH"] = str(decision_db)
        os.environ["NAVIGATION_RUNTIME_DB_PATH"] = str(temporary_path / "api-runtime.sqlite")
        get_settings.cache_clear()
        from app import navigation_main  # noqa: E402

        navigation_main.get_navigation_runtime.cache_clear()
        with TestClient(navigation_main.app) as client:
            assert client.get("/health").status_code == 200
            status = client.get("/v1/navigation/status")
            assert status.status_code == 200 and status.json()["ready"] is True
            assert status.json()["research_models_ready"] is False
            assert (
                status.json()["planner"]["structured_output"]
                == "hermes_tools_without_direct_action_execution"
            )
            api_decision = client.post(
                "/v1/navigation/decide",
                json={
                    "request_id": "api-request",
                    "app_package": "evaluation.api.app",
                    "goal_text": "회원 탈퇴",
                    "screen": _account_screen().model_dump(mode="json"),
                },
            )
            assert api_decision.status_code == 200
            assert api_decision.json()["action"]["candidate_id"] == "profile"
        navigation_main.get_navigation_runtime.cache_clear()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

        runtime_status = runtime.store.status()
        assert runtime_status["decisions"] == 4
        assert runtime_status["observations"] == 2
        assert runtime_status["pending_knowledge_revisions"] == 1
    print("navigation_runtime_unit: ok")


if __name__ == "__main__":
    main()
