from __future__ import annotations

import importlib.util
import json
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
from app.services.navigation_dataset_split import (  # noqa: E402
    DatasetSplitAccessError,
    NavigationDatasetSplitManifest,
)
from app.services.navigation_model_clients import (  # noqa: E402
    Exaone45VisionClient,
    NavigationPlannerResearchClient,
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
        planner_model=NavigationPlannerResearchClient(
            OpenAICompatibleChatClient(
                api_key="", base_url="https://example.invalid/v1", model="test-solar-pro3"
            ),
            provider_name="solar_pro3",
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
        assert disconnected.session_status == "active"

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

        safety_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "state-change-runtime.sqlite"),
            policy=_policy(),
        )
        state_changing = safety_runtime.decide(
            DecideRequest(
                request_id="request-state-change",
                app_package="evaluation.another.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=ScreenObservation(
                    window_title="계정 설정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="logout",
                            label="로그아웃",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert state_changing.action.name == "stop_for_user"

        logged_out = safety_runtime.decide(
            DecideRequest(
                request_id="request-auth-boundary",
                app_package="evaluation.another.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=ScreenObservation(
                    window_title="전체 메뉴",
                    activity_name="androidx.drawerlayout.widget.DrawerLayout",
                    candidates=[
                        NavigationCandidate(candidate_id="signup", label="회원가입", role="button"),
                        NavigationCandidate(candidate_id="login", label="로그인", role="button"),
                        NavigationCandidate(candidate_id="my-page", label="마이페이지", role="button"),
                    ],
                ),
            )
        )
        assert logged_out.action.name == "stop_for_user"
        assert logged_out.planner_provider == "python_authentication_boundary"
        assert logged_out.perception_provider == "structured_input_auth_boundary"
        logged_out_observation = safety_runtime.observe(
            ObserveRequest(
                request_id="request-auth-boundary-observe",
                decision_id=logged_out.decision_id,
                connectivity_status="observed",
                execution_succeeded=False,
                observed_signal="blocked",
                next_screen=ScreenObservation(
                    window_title="전체 메뉴",
                    activity_name="androidx.drawerlayout.widget.DrawerLayout",
                    candidates=[
                        NavigationCandidate(candidate_id="signup", label="회원가입", role="button"),
                        NavigationCandidate(candidate_id="login", label="로그인", role="button"),
                        NavigationCandidate(candidate_id="my-page", label="마이페이지", role="button"),
                    ],
                ),
            )
        )
        assert logged_out_observation.outcome_type == "login_required"
        assert safety_runtime.store.session(logged_out.session_id)["status"] == "stopped"

        auth_transition_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "auth-transition-runtime.sqlite"),
            policy=_policy(),
        )
        auth_entry = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-auth-entry",
                app_package="evaluation.auth.app",
                goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                screen=_account_screen(),
            )
        )
        auth_observation = auth_transition_runtime.observe(
            ObserveRequest(
                request_id="request-auth-observe",
                decision_id=auth_entry.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=ScreenObservation(
                    window_title="로그인",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(candidate_id="signup", label="회원가입", role="button"),
                        NavigationCandidate(candidate_id="login", label="로그인", role="button"),
                    ],
                ),
            )
        )
        assert auth_observation.outcome_type == "login_required"
        assert auth_observation.recovery_action is not None
        assert auth_observation.recovery_action.name == "stop_for_user"
        assert auth_observation.session_status == "stopped"

        signup_terminal = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-signup-terminal",
                app_package="evaluation.auth.app",
                goal_text="새 계정을 만들고 싶어",
                screen=ScreenObservation(
                    window_title="회원가입",
                    activity_name="android.webkit.WebView",
                    candidates=[
                        NavigationCandidate(candidate_id="email", label="이메일", role="input"),
                        NavigationCandidate(candidate_id="password", label="비밀번호", role="input"),
                        NavigationCandidate(candidate_id="create", label="가입하기", role="button"),
                    ],
                ),
            )
        )
        assert signup_terminal.action.name == "stop_for_user"
        assert signup_terminal.planner_provider == "python_terminal_boundary"
        assert signup_terminal.perception_provider == "structured_input_terminal_boundary"

        already_member = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-already-member",
                app_package="evaluation.membership.app",
                goal_text="유료 멤버십에 가입하고 싶어",
                screen=ScreenObservation(
                    window_title="계정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-status",
                            label="Premium 회원",
                            role="text",
                        ),
                        NavigationCandidate(
                            candidate_id="benefits",
                            label="Premium 혜택",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert already_member.action.name == "stop_for_user"
        assert already_member.planner_provider == "python_goal_already_satisfied"
        already_member_observation = auth_transition_runtime.observe(
            ObserveRequest(
                request_id="request-already-member-observe",
                decision_id=already_member.decision_id,
                connectivity_status="observed",
                execution_succeeded=False,
                next_screen=ScreenObservation(
                    window_title="계정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-status",
                            label="Premium 회원",
                            role="text",
                        ),
                        NavigationCandidate(
                            candidate_id="benefits",
                            label="Premium 혜택",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert already_member_observation.outcome_type == "blocked"
        assert already_member_observation.failure_class == "already_satisfied"
        assert already_member_observation.candidate_forbidden is False
        assert already_member_observation.session_status == "stopped"

        already_member_after_click = auth_transition_runtime.decide(
            DecideRequest(
                request_id="request-member-after-click",
                app_package="evaluation.membership.app",
                goal_text="유료 멤버십에 가입하고 싶어",
                screen=ScreenObservation(
                    window_title="홈",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="my-page",
                            label="내 페이지",
                            role="button",
                        )
                    ],
                ),
            )
        )
        assert already_member_after_click.action.name == "click"
        already_member_after_click_observation = auth_transition_runtime.observe(
            ObserveRequest(
                request_id="request-member-after-click-observe",
                decision_id=already_member_after_click.decision_id,
                connectivity_status="observed",
                execution_succeeded=True,
                next_screen=ScreenObservation(
                    window_title="계정",
                    activity_name="android.view.View",
                    candidates=[
                        NavigationCandidate(
                            candidate_id="membership-status",
                            label="Premium 회원",
                            role="text",
                        ),
                        NavigationCandidate(
                            candidate_id="benefits",
                            label="Premium 혜택",
                            role="button",
                        ),
                    ],
                ),
            )
        )
        assert already_member_after_click_observation.outcome_type == "blocked"
        assert already_member_after_click_observation.progress_label == "advanced"
        assert already_member_after_click_observation.failure_class == "already_satisfied"
        assert already_member_after_click_observation.candidate_forbidden is False
        assert already_member_after_click_observation.knowledge_revision_queued is False
        assert already_member_after_click_observation.session_status == "stopped"

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

        split_manifest = NavigationDatasetSplitManifest.load(
            ROOT / "db" / "navigation_dataset_split_v1.json"
        )
        split_runtime = NavigationRuntime(
            memory=NavigationDecisionMemory(decision_db),
            store=NavigationRuntimeStore(temporary_path / "split-runtime.sqlite"),
            policy=_policy(),
            dataset_split_manifest=split_manifest,
        )
        split_status = split_runtime.status()["dataset_split"]
        assert split_status["counts"]["locked_holdout"] == 3
        assert split_runtime.store.status()["schema_version"] == 3
        assert len(split_runtime.store.dataset_split_manifest()) == len(split_manifest.entries)
        try:
            split_runtime.decide(
                DecideRequest(
                    request_id="holdout-denied",
                    app_package="com.instagram.android",
                    goal_text="회원 탈퇴 메뉴를 찾고 싶어",
                    screen=_account_screen(),
                )
            )
        except DatasetSplitAccessError:
            pass
        else:
            raise AssertionError("locked holdout app was accepted during collection")

        legacy_runtime_path = temporary_path / "legacy-runtime-v2.sqlite"
        legacy_store = NavigationRuntimeStore(legacy_runtime_path)
        legacy_store.upsert_session(
            session_id="legacy-session",
            request_id="legacy-request",
            app_package="legacy.app",
            locale="ko-KR",
            goal_text="회원 탈퇴",
            goal_id="account.delete",
        )
        connection = sqlite3.connect(legacy_runtime_path)
        try:
            connection.execute("DROP TABLE navigation_dataset_split_manifest")
            connection.execute(
                "UPDATE navigation_runtime_metadata SET value='2' WHERE key='schema_version'"
            )
            connection.execute(
                "DELETE FROM navigation_runtime_metadata WHERE key LIKE 'dataset_split_manifest_%'"
            )
            connection.execute("PRAGMA user_version=2")
            connection.commit()
        finally:
            connection.close()
        upgraded_store = NavigationRuntimeStore(legacy_runtime_path)
        assert upgraded_store.status()["schema_version"] == 3
        assert upgraded_store.session("legacy-session") is not None

        previous = {key: os.environ.get(key) for key in (
            "NAVIGATION_DECISION_DB_PATH",
            "NAVIGATION_RUNTIME_DB_PATH",
            "NAVIGATION_DATASET_SPLIT_MANIFEST_PATH",
            "NAVIGATION_ALLOW_LOCKED_HOLDOUT",
        )}
        os.environ["NAVIGATION_DECISION_DB_PATH"] = str(decision_db)
        os.environ["NAVIGATION_RUNTIME_DB_PATH"] = str(temporary_path / "api-runtime.sqlite")
        os.environ["NAVIGATION_DATASET_SPLIT_MANIFEST_PATH"] = str(
            ROOT / "db" / "navigation_dataset_split_v1.json"
        )
        os.environ["NAVIGATION_ALLOW_LOCKED_HOLDOUT"] = "false"
        get_settings.cache_clear()
        from app import navigation_main  # noqa: E402

        navigation_main.get_navigation_runtime.cache_clear()
        with TestClient(navigation_main.app) as client:
            assert client.get("/health").status_code == 200
            status = client.get("/v1/navigation/status")
            assert status.status_code == 200 and status.json()["ready"] is True
            assert status.json()["research_models_ready"] is False
            assert status.json()["serving_mode"] == "decision_memory_fallback"
            assert status.json()["research_model_blockers"] == [
                "planner_model_endpoint_or_credentials_missing",
                "exaone_4_5_endpoint_or_credentials_missing",
            ]
            assert (
                status.json()["planner"]["structured_output"]
                == "hermes_tools_without_direct_action_execution"
            )
            split_response = client.get("/v1/navigation/dataset-splits")
            assert split_response.status_code == 200
            assert split_response.json()["policy"]["counts"]["locked_holdout"] == 3
            api_decision = client.post(
                "/v1/navigation/decide",
                json={
                    "request_id": "api-request",
                    "app_package": "com.coupang.mobile",
                    "goal_text": "회원 탈퇴",
                    "screen": _account_screen().model_dump(mode="json"),
                },
            )
            assert api_decision.status_code == 200
            assert api_decision.json()["action"]["candidate_id"] == "profile"
            holdout_decision = client.post(
                "/v1/navigation/decide",
                json={
                    "request_id": "api-holdout-denied",
                    "app_package": "com.openai.chatgpt",
                    "goal_text": "회원 탈퇴",
                    "screen": _account_screen().model_dump(mode="json"),
                },
            )
            assert holdout_decision.status_code == 403
            repeated_decision = client.post(
                "/v1/navigation/decide",
                json=json.loads(api_decision.request.content.decode("utf-8")),
            )
            assert repeated_decision.status_code == 200
            assert repeated_decision.json()["decision_id"] == api_decision.json()["decision_id"]
            api_observe_payload = {
                "request_id": "api-observe-request",
                "decision_id": api_decision.json()["decision_id"],
                "connectivity_status": "observed",
                "execution_succeeded": True,
                "next_screen": _account_screen().model_dump(mode="json"),
            }
            api_observation = client.post("/v1/navigation/observe", json=api_observe_payload)
            assert api_observation.status_code == 200
            repeated_observation = client.post(
                "/v1/navigation/observe", json=api_observe_payload
            )
            assert repeated_observation.status_code == 200
            assert repeated_observation.json() == api_observation.json()
            stop_response = client.post(
                f"/v1/navigation/sessions/{api_decision.json()['session_id']}/stop"
            )
            assert stop_response.status_code == 200
            assert stop_response.json()["status"] == "stopped"
            repeated_stop = client.post(
                f"/v1/navigation/sessions/{api_decision.json()['session_id']}/stop"
            )
            assert repeated_stop.status_code == 200
            assert repeated_stop.json() == stop_response.json()
            assert client.post("/v1/navigation/sessions/missing/stop").status_code == 404
            api_episode = client.get(
                f"/v1/navigation/sessions/{api_decision.json()['session_id']}/episode"
            )
            assert api_episode.status_code == 200
            assert api_episode.json()["candidate_set_status"] == "complete"
            assert len(api_episode.json()["steps"][0]["screen"]["before"]["candidates"]) == 2
            assert len(api_episode.json()["steps"][0]["screen"]["after"]["candidates"]) == 2
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
        assert runtime_status["screen_snapshots"] == 5
        assert runtime_status["screen_candidates"] == 9
        assert runtime_status["complete_steps"] == 2
        assert runtime_status["pending_knowledge_revisions"] == 1
        episode = runtime.store.interaction_episode(first.session_id)
        assert episode["candidate_set_status"] == "complete"
        assert len(episode["steps"]) == 2
        assert len(episode["steps"][0]["screen"]["before"]["candidates"]) == 2
        assert len(episode["steps"][0]["screen"]["after"]["candidates"]) == 2
        selected = [
            item
            for item in episode["steps"][0]["screen"]["before"]["candidates"]
            if item["selected"]
        ]
        assert [item["candidate_id"] for item in selected] == ["profile"]
        assert episode["steps"][1]["connectivity_status"] == "transport_error"
        assert "after" not in episode["steps"][1]["screen"]
    print("navigation_runtime_unit: ok")


if __name__ == "__main__":
    main()
