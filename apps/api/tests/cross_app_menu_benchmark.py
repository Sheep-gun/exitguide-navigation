import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_PATH = ROOT / "fixtures" / "navigation" / "cross-app-menu-benchmark.v1.json"


def main() -> None:
    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]
    failures: list[str] = []
    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        settings = Settings(
            navigation_agent_provider="mock",
            navigation_function_db_path=str(root / "functions.sqlite"),
            navigation_exploration_timeout_seconds=55,
            navigation_exploration_max_actions=16,
            navigation_exploration_max_depth=9,
        )
        repository = UniversalNavigationGraphRepository(root / "graph.sqlite")
        for index, case in enumerate(cases):
            request = UniversalNavigationObserveRequest.model_validate(
                {
                    "request_id": f"cross-app-menu-{index}",
                    "session_id": f"cross-app-menu-session-{index}",
                    "app_package": f"com.synthetic.crossapp{index}",
                    "app_version": "1.0",
                    "locale": "ko-KR",
                    "goal_text": case["goal_text"],
                    "operation_mode": "explore",
                    "screen": {
                        "activity_name": "SyntheticActivity",
                        "window_title": case["screen_title"],
                        "elements": [
                            {
                                "id": f"button-{button_index}",
                                "text": label,
                                "role": "button",
                                "clickable": True,
                                "enabled": True,
                                "visible": True,
                                "bounds": [20, 200 + button_index * 140, 1060, 320 + button_index * 140],
                            }
                            for button_index, label in enumerate(case["buttons"])
                        ],
                    },
                }
            )
            response = observe_universal_navigation(request, settings=settings, repository=repository)
            actual_label = response.automation.selected_label
            actual_action = response.automation.action
            if actual_label != case["expected_label"] or actual_action != case["expected_action"]:
                failures.append(
                    f"{case['id']}: expected {case['expected_action']} {case['expected_label']!r}, "
                    f"got {actual_action} {actual_label!r} "
                    f"phase={response.phase} target={response.goal_interpretation!r} warnings={response.warnings!r}"
                )

    if failures:
        raise AssertionError("cross-app menu benchmark failures:\n" + "\n".join(failures))
    print(f"cross-app menu benchmark ok: {len(cases)}/{len(cases)} (100%)")


if __name__ == "__main__":
    main()
