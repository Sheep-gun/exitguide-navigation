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


CASES = [
    ("구독을 해지하고 싶어", [("membership", "구매 항목 및 멤버십"), ("settings", "설정"), ("help", "고객센터")], "membership"),
    ("구독을 해지하고 싶어", [("premium", "Premium 멤버십"), ("history", "구매 내역")], "premium"),
    ("구독을 해지하고 싶어", [("deactivate", "비활성화"), ("billing", "결제 수단")], "deactivate"),
    ("마케팅 알림을 끄고 싶어", [("settings", "설정"), ("help", "도움말"), ("profile", "프로필")], "settings"),
    ("마케팅 알림을 끄고 싶어", [("notifications", "알림"), ("privacy", "개인정보"), ("account", "계정")], "notifications"),
    ("마케팅 알림을 끄고 싶어", [("marketing", "마케팅 정보 수신"), ("service", "서비스 알림")], "marketing"),
    ("계정을 삭제하고 싶어", [("account", "계정"), ("privacy", "개인정보"), ("notifications", "알림")], "account"),
    ("계정을 삭제하고 싶어", [("delete", "계정 삭제"), ("logout", "로그아웃"), ("security", "보안")], "delete"),
    ("결제를 환불하고 싶어", [("orders", "주문 및 결제"), ("support", "고객센터"), ("account", "계정")], "orders"),
    ("결제를 환불하고 싶어", [("purchase", "최근 구매 내역"), ("help", "도움말"), ("settings", "설정")], "purchase"),
]


def main() -> None:
    settings = Settings(navigation_agent_provider="exaone", navigation_agent_allow_fallback=True)
    if not settings.exaone_api_key or not settings.exaone_model:
        raise SystemExit("EXAONE_API_KEY and EXAONE_MODEL are required in the local .env")

    expected_matches = 0
    valid_candidates = 0
    exaone_decisions = 0
    durations: list[float] = []
    with TemporaryDirectory() as temporary_directory:
        repository = UniversalNavigationGraphRepository(Path(temporary_directory) / "live-evaluation.sqlite")
        for index, (goal_text, buttons, expected_id) in enumerate(CASES):
            request = UniversalNavigationObserveRequest.model_validate(
                {
                    "request_id": f"live_evaluation_{index}",
                    "session_id": f"live_evaluation_session_{index}",
                    "app_package": f"com.live.synthetic.unknown{index}",
                    "goal_text": goal_text,
                    "screen": {
                        "activity_name": "UnknownActivity",
                        "elements": [
                            {"id": element_id, "text": label, "role": "button", "clickable": True}
                            for element_id, label in buttons
                        ],
                    },
                }
            )
            started = time.perf_counter()
            response = observe_universal_navigation(request, settings=settings, repository=repository)
            durations.append(time.perf_counter() - started)
            selected_id = None if response.recommendation is None else response.recommendation.selected_element_id
            candidate_ids = {candidate.element_id for candidate in response.candidates}
            valid_candidates += selected_id in candidate_ids
            expected_matches += selected_id == expected_id
            exaone_decisions += response.decision_mode == "exaone"
            print(
                f"{index + 1:02d} mode={response.decision_mode:<22} "
                f"expected={expected_id:<13} selected={str(selected_id):<13} "
                f"latency={durations[-1]:.2f}s"
            )

    total = len(CASES)
    print(
        "summary "
        f"expected_accuracy={expected_matches}/{total} ({expected_matches / total:.0%}) "
        f"candidate_validity={valid_candidates}/{total} ({valid_candidates / total:.0%}) "
        f"exaone_mode={exaone_decisions}/{total} ({exaone_decisions / total:.0%}) "
        f"mean_latency={sum(durations) / total:.2f}s"
    )


if __name__ == "__main__":
    main()
