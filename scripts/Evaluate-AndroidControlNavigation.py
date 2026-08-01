from __future__ import annotations

import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.config import Settings  # noqa: E402
from app.schemas import UniversalNavigationObserveRequest  # noqa: E402
from app.services.universal_navigation_agent import observe_universal_navigation  # noqa: E402
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository  # noqa: E402


def main() -> None:
    settings = Settings(navigation_agent_provider="exaone", navigation_agent_allow_fallback=True)
    if not settings.exaone_api_key or not settings.exaone_model:
        raise SystemExit("EXAONE_API_KEY and EXAONE_MODEL are required in the local .env")
    request = UniversalNavigationObserveRequest.model_validate(
        {
            "request_id": "android_control_youtube_regression",
            "session_id": "android_control_youtube_regression_session",
            "app_package": "com.synthetic.video",
            "app_version": "1.0",
            "locale": "ko-KR",
            "goal_text": "유튜브 프리미엄 구독을 해지하고 싶어",
            "screen": {
                "activity_name": "SyntheticVideoHome",
                "window_title": "홈",
                "elements": [
                    _element("home", "홈", [0, 2100, 200, 2240]),
                    _element("shorts", "Shorts", [200, 2100, 400, 2240]),
                    _element("subscriptions", "구독", [400, 2100, 600, 2240]),
                    _element("my_page", "내 페이지", [800, 2100, 1080, 2240]),
                ],
            },
        }
    )
    with TemporaryDirectory() as temporary_directory:
        repository = UniversalNavigationGraphRepository(Path(temporary_directory) / "evaluation.sqlite")
        started = time.perf_counter()
        response = observe_universal_navigation(request, settings=settings, repository=repository)
        elapsed = time.perf_counter() - started
    recommendation = response.recommendation
    selected = None if recommendation is None else recommendation.selected_element_id
    print(
        f"mode={response.decision_mode} selected={selected} "
        f"confidence={0 if recommendation is None else recommendation.confidence:.2f} latency={elapsed:.2f}s"
    )
    for warning in response.warnings:
        print(f"warning={warning}")
    if selected == "subscriptions":
        raise SystemExit("regression: content subscriptions tab was confused with billing management")
    if selected not in {"my_page", None}:
        raise SystemExit(f"unexpected navigation candidate: {selected}")


def _element(element_id: str, text: str, bounds: list[int]) -> dict[str, object]:
    return {
        "id": element_id,
        "parent_id": "bottom_navigation",
        "text": text,
        "view_id": f"com.synthetic.video:id/{element_id}",
        "role": "button",
        "clickable": True,
        "enabled": True,
        "visible": True,
        "bounds": bounds,
    }


if __name__ == "__main__":
    main()
