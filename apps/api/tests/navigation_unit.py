from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def main() -> None:
    assert_route_catalog()
    assert_goal_text_and_semantic_button_match()
    assert_reanchors_to_known_later_state()
    assert_failed_element_is_not_recommended_again()
    assert_failed_meaning_is_not_recommended_again()
    assert_unknown_screen_requests_safe_recovery()
    assert_retry_limit_stops_guessing()
    assert_final_confirmation_includes_terms_hint()
    assert_specific_target_breaks_sparse_screen_tie()
    assert_completion_is_detected()
    assert_unknown_route_is_explicit()
    print("navigation checks ok")


def assert_route_catalog() -> None:
    response = client.get("/v1/navigation/routes")
    assert response.status_code == 200
    payload = response.json()
    assert payload["route_count"] == 1
    assert payload["routes"][0]["route_id"] == "egl_stream_android_cancel_subscription_ko_v1"
    assert payload["routes"][0]["state_count"] == 6


def assert_goal_text_and_semantic_button_match() -> None:
    elements = [
        element("title", "계정", False, "heading"),
        element("profile", "프로필", False),
        element("settings", "설정", False),
        element("membership", "멤버십 및 구매", True, "button"),
    ]
    result = guide(elements, goal_id=None, goal_text="자동결제를 해제하고 싶어")
    assert result["status"] == "guided"
    assert result["navigation_state"] == "on_route"
    assert result["current_state_id"] == "profile_home"
    assert result["target_element_id"] == "membership"
    assert "멤버십 및 구매" in result["instruction"]
    assert result["target_element_id"] in {item["id"] for item in elements}


def assert_reanchors_to_known_later_state() -> None:
    elements = [
        element("offer", "혜택을 유지해 보세요", False, "heading"),
        element("pause", "일시중지", True, "button"),
        element("continue", "계속 해지", True, "button"),
    ]
    result = guide(elements, last_state="profile_home")
    assert result["navigation_state"] == "reanchored"
    assert result["current_state_id"] == "retention_offer"
    assert result["target_element_id"] == "continue"
    assert "일시중지" in result["warning"]
    assert result["dark_pattern"]["overall_risk"] in {"medium", "high"}
    assert "retention_misdirection" in {finding["type"] for finding in result["dark_pattern"]["findings"]}


def assert_failed_element_is_not_recommended_again() -> None:
    elements = [
        element("offer", "혜택과 일시중지", False, "heading"),
        element("failed", "계속 해지", True, "button"),
        element("alternate", "해지 계속", True, "button"),
    ]
    result = guide(elements, failed_ids=["failed"], retry_count=1)
    assert result["target_element_id"] == "alternate"


def assert_failed_meaning_is_not_recommended_again() -> None:
    elements = [
        element("offer", "혜택과 일시중지", False, "heading"),
        element("continue", "계속 해지", True, "button"),
    ]
    result = guide(
        elements,
        failed_meanings=["continue_cancellation"],
        retry_count=1,
    )
    assert result["status"] == "needs_review"
    assert result["target_element_id"] is None


def assert_unknown_screen_requests_safe_recovery() -> None:
    result = guide(
        [
            element("help", "고객센터", False, "heading"),
            element("faq", "자주 묻는 질문", True, "button"),
        ],
        last_state="membership_home",
    )
    assert result["navigation_state"] == "recovery_required"
    assert result["target_element_id"] is None
    assert result["recovery"]["type"] == "back"
    assert result["requires_user_confirmation"] is True


def assert_retry_limit_stops_guessing() -> None:
    result = guide(
        [element("title", "멤버십 관리", False, "heading"), element("cancel", "비활성화", True, "button")],
        retry_count=2,
    )
    assert result["status"] == "needs_review"
    assert result["navigation_state"] == "needs_review"
    assert result["recovery"]["type"] == "stop"


def assert_final_confirmation_includes_terms_hint() -> None:
    elements = [
        element("title", "해지 확인", False, "heading"),
        element("date", "이용 종료일 8월 10일", False),
        element("billing", "다음 결제 없음", False),
        element("confirm", "Premium 해지", True, "button"),
    ]
    result = guide(elements, last_state="retention_offer")
    assert result["current_state_id"] == "cancel_confirmation"
    assert result["target_element_id"] == "confirm"
    assert result["requires_user_confirmation"] is True
    assert result["terms_hint"] is not None
    assert result["terms_hint"]["evidence"][0]["document_id"] == "seed_streaming_subscription_terms"


def assert_specific_target_breaks_sparse_screen_tie() -> None:
    result = guide(
        [element("confirm", "Premium 해지", True, "button")],
        last_state="retention_offer",
    )
    assert result["current_state_id"] == "cancel_confirmation"
    assert result["target_element_id"] == "confirm"


def assert_completion_is_detected() -> None:
    result = guide(
        [
            element("title", "해지 완료", False, "heading"),
            element("billing", "다음 결제 없음", False),
            element("status", "멤버십 종료", False),
        ],
        last_state="cancel_confirmation",
    )
    assert result["status"] == "goal_completed"
    assert result["navigation_state"] == "completed"
    assert result["target_element_id"] is None


def assert_unknown_route_is_explicit() -> None:
    payload = request_payload([element("title", "계정", False, "heading")])
    payload["app_package"] = "com.unknown.app"
    response = client.post("/v1/navigation/guide", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "route_not_found"


def guide(
    elements: list[dict],
    *,
    goal_id: str | None = "cancel_subscription",
    goal_text: str | None = None,
    last_state: str | None = None,
    failed_ids: list[str] | None = None,
    failed_meanings: list[str] | None = None,
    retry_count: int = 0,
) -> dict:
    payload = request_payload(elements)
    payload["goal_id"] = goal_id
    payload["goal_text"] = goal_text
    payload["session"] = {
        "last_confirmed_state_id": last_state,
        "failed_element_ids": failed_ids or [],
        "failed_candidate_meanings": failed_meanings or [],
        "retry_count": retry_count,
    }
    response = client.post("/v1/navigation/guide", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def request_payload(elements: list[dict]) -> dict:
    return {
        "request_id": "req_navigation_test",
        "app_package": "lab.exitguide.stream.demo",
        "app_version": "1.0.0",
        "platform": "android",
        "locale": "ko-KR",
        "goal_id": "cancel_subscription",
        "goal_text": None,
        "session": {
            "last_confirmed_state_id": None,
            "failed_element_ids": [],
            "failed_candidate_meanings": [],
            "retry_count": 0,
        },
        "screen_elements": elements,
    }


def element(element_id: str, text: str, clickable: bool, role: str = "text") -> dict:
    return {
        "id": element_id,
        "text": text,
        "content_description": None,
        "view_id": f"lab.exitguide.stream.demo:id/{element_id}",
        "role": role,
        "clickable": clickable,
        "bounds": [24, 100, 980, 180],
    }


if __name__ == "__main__":
    main()
