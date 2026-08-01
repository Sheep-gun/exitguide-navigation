from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import Settings
from app.schemas import UniversalNavigationObserveRequest
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


CASES = [
    (
        "구독을 해지하고 싶어",
        [("membership", "구매 항목 및 멤버십"), ("settings", "설정"), ("help", "고객센터")],
        "membership",
    ),
    (
        "구독을 해지하고 싶어",
        [("premium", "Premium 멤버십"), ("history", "구매 내역")],
        "premium",
    ),
    (
        "구독을 해지하고 싶어",
        [("deactivate", "비활성화"), ("billing", "결제 수단")],
        "deactivate",
    ),
    (
        "마케팅 알림을 끄고 싶어",
        [("settings", "설정"), ("help", "도움말"), ("profile", "프로필")],
        "settings",
    ),
    (
        "마케팅 알림을 끄고 싶어",
        [("notifications", "알림"), ("privacy", "개인정보"), ("account", "계정")],
        "notifications",
    ),
    (
        "마케팅 알림을 끄고 싶어",
        [("marketing", "마케팅 정보 수신"), ("service", "서비스 알림")],
        "marketing",
    ),
    (
        "계정을 삭제하고 싶어",
        [("account", "계정"), ("privacy", "개인정보"), ("notifications", "알림")],
        "account",
    ),
    (
        "계정을 삭제하고 싶어",
        [("delete", "계정 삭제"), ("logout", "로그아웃"), ("security", "보안")],
        "delete",
    ),
    (
        "결제를 환불하고 싶어",
        [("orders", "주문 및 결제"), ("support", "고객센터"), ("account", "계정")],
        "orders",
    ),
    (
        "결제를 환불하고 싶어",
        [("purchase", "최근 구매 내역"), ("help", "도움말"), ("settings", "설정")],
        "purchase",
    ),
]


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        repository = UniversalNavigationGraphRepository(Path(temporary_directory) / "benchmark.sqlite")
        settings = Settings(navigation_agent_provider="mock")
        passed = 0
        for index, (goal_text, buttons, expected_id) in enumerate(CASES):
            request = UniversalNavigationObserveRequest.model_validate(
                {
                    "request_id": f"benchmark_{index}",
                    "session_id": f"benchmark_session_{index}",
                    "app_package": f"com.synthetic.unknown{index}",
                    "goal_text": goal_text,
                    "screen": {
                        "activity_name": "UnknownActivity",
                        "elements": [
                            {
                                "id": element_id,
                                "text": label,
                                "role": "button",
                                "clickable": True,
                            }
                            for element_id, label in buttons
                        ],
                    },
                }
            )
            response = observe_universal_navigation(request, settings=settings, repository=repository)
            recommendation = response.recommendation
            selected_id = None if recommendation is None else recommendation.selected_element_id
            candidate_ids = {candidate.element_id for candidate in response.candidates}
            assert selected_id is None or selected_id in candidate_ids
            passed += selected_id == expected_id

        accuracy = passed / len(CASES)
        assert accuracy >= 0.8, f"synthetic fallback accuracy {accuracy:.0%} ({passed}/{len(CASES)})"
        print(f"universal navigation benchmark ok: {passed}/{len(CASES)} ({accuracy:.0%})")


if __name__ == "__main__":
    main()
