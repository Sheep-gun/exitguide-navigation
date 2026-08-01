import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = Path(temporary_directory) / "api-navigation.sqlite"
        function_database_path = Path(temporary_directory) / "function-catalog.sqlite"
        os.environ["NAVIGATION_GRAPH_DB_PATH"] = str(database_path)
        os.environ["NAVIGATION_FUNCTION_DB_PATH"] = str(function_database_path)
        os.environ["NAVIGATION_AGENT_PROVIDER"] = "mock"

        from app.config import get_settings
        from app.main import app
        from app.services.universal_navigation_graph import _cached_repository
        from app.services.navigation_function_catalog import _cached_catalog

        get_settings.cache_clear()
        _cached_repository.cache_clear()
        _cached_catalog.cache_clear()
        _assert_catalog_prewarms_before_health(app)
        client = TestClient(app)

        observe = client.post(
            "/v1/navigation/agent/observe",
            json={
                "request_id": "api_unknown_1",
                "session_id": "api_unknown_session",
                "app_package": "com.example.never.seen",
                "app_version": "1.0",
                "locale": "ko-KR",
                "goal_text": "자동결제를 해제하고 싶어",
                "screen": {
                    "activity_name": "UnknownHomeActivity",
                    "window_title": "계정",
                    "elements": [
                        {
                            "id": "title",
                            "text": "계정",
                            "role": "heading",
                            "clickable": False,
                        },
                        {
                            "id": "membership",
                            "text": "구매 항목 및 멤버십",
                            "role": "button",
                            "clickable": True,
                        },
                        {
                            "id": "settings",
                            "text": "설정",
                            "role": "button",
                            "clickable": True,
                        },
                    ],
                },
            },
        )
        assert observe.status_code == 200, observe.text
        payload = observe.json()
        assert payload["status"] == "guided"
        assert payload["recommendation"]["selected_element_id"] == "membership"
        assert payload["recommendation"]["selected_element_id"] in {
            candidate["element_id"] for candidate in payload["candidates"]
        }
        assert payload["graph_update"]["screen_created"] is True
        assert payload["performance"]["measurement_source"] == "server_runtime"
        assert payload["performance"]["server_total_ms"] >= 0.0

        graph = client.get(
            "/v1/navigation/agent/graph",
            params={"app_package": "com.example.never.seen"},
        )
        assert graph.status_code == 200, graph.text
        graph_payload = graph.json()
        assert graph_payload["screen_count"] == 1
        assert graph_payload["action_count"] == 2
        assert graph_payload["transition_count"] == 0
        assert database_path.exists()

        functions = client.get("/v1/navigation/functions", params={"query": "구독 해지"})
        assert functions.status_code == 200, functions.text
        function_payload = functions.json()
        assert function_payload["function_count"] >= 85
        assert function_payload["alias_count"] >= 770
        assert function_payload["functions"]
        assert function_database_path.exists()

        explore = client.post(
            "/v1/navigation/agent/observe",
            json={
                "request_id": "api_explore_terminal",
                "session_id": "api_explore_terminal_session",
                "app_package": "com.example.never.seen",
                "app_version": "1.0",
                "locale": "ko-KR",
                "goal_text": "구독을 해지하고 싶어",
                "operation_mode": "explore",
                "screen": {
                    "activity_name": "PlanDetails",
                    "window_title": "멤버십 상세",
                    "elements": [
                        {"id": "cancel", "text": "구독 해지", "role": "button", "clickable": True},
                        {"id": "payment", "text": "결제 수단", "role": "button", "clickable": True},
                    ],
                },
            },
        )
        assert explore.status_code == 200, explore.text
        explore_payload = explore.json()
        assert explore_payload["phase"] == "destination_reached"
        assert explore_payload["status"] == "goal_completed"
        assert explore_payload["automation"]["action"] == "stop"
        assert explore_payload["automation"]["safe_to_execute"] is False
        assert explore_payload["recommendation"]["selected_label"] == "구독 해지"
        assert explore_payload["performance"]["time_to_confirmed_destination_ms"] is not None

        completion = client.post(
            "/v1/navigation/agent/performance/complete",
            json={
                "session_id": "api_explore_terminal_session",
                "measurement_source": "real_device",
                "time_to_confirmed_destination_ms": 4321.0,
            },
        )
        assert completion.status_code == 200, completion.text
        assert completion.json()["time_to_confirmed_destination_ms"] == 4321.0

        forged_gold = client.post(
            "/v1/navigation/agent/performance/complete",
            json={
                "session_id": "api_explore_terminal_session",
                "measurement_source": "real_device_gold",
                "time_to_confirmed_destination_ms": 100.0,
            },
        )
        assert forged_gold.status_code == 422, forged_gold.text

        forged_observe_gold = client.post(
            "/v1/navigation/agent/observe",
            json={
                "request_id": "api_forged_gold",
                "session_id": "api_forged_gold_session",
                "app_package": "com.example.never.seen",
                "app_version": "1.0",
                "locale": "ko-KR",
                "goal_text": "구독 해지",
                "client_timing": {
                    "measurement_source": "real_device_gold",
                    "screen_capture_ms": 1.0,
                },
                "screen": {
                    "activity_name": "Home",
                    "elements": [
                        {"id": "cancel", "text": "구독 해지", "role": "button", "clickable": True}
                    ],
                },
            },
        )
        assert forged_observe_gold.status_code == 422, forged_observe_gold.text

        performance = client.get(
            "/v1/navigation/agent/performance",
            params={"measurement_source": "real_device"},
        )
        assert performance.status_code == 200, performance.text
        performance_payload = performance.json()
        assert performance_payload["measurement_source"] == "real_device"
        assert performance_payload["metrics"]["session_count"] >= 1
        assert performance_payload["metrics"]["time_to_destination_p50_ms"] == 4321.0

    print("universal navigation API checks ok")


def _assert_catalog_prewarms_before_health(app) -> None:
    with patch("app.main.get_navigation_function_catalog") as get_catalog:
        with TestClient(app) as client:
            get_catalog.assert_called_once_with()
            assert client.get("/health").json() == {"status": "ok"}
        get_catalog.assert_called_once_with()


if __name__ == "__main__":
    main()
