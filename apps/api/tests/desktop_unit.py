from fastapi.testclient import TestClient

from app.desktop import app


def main() -> None:
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}

    page = client.get("/navigation.html")
    assert page.status_code == 200
    assert "EGL Navigation MVP" in page.text
    assert "/v1/navigation/guide" in page.text

    dark_page = client.get("/dark-pattern.html")
    assert dark_page.status_code == 200
    assert "EGL Dark Pattern MVP" in dark_page.text
    assert "/v1/dark-pattern/inspect" in dark_page.text

    route_catalog = client.get("/v1/navigation/routes").json()
    assert route_catalog["route_count"] == 1

    response = client.post(
        "/v1/navigation/guide",
        json={
            "request_id": "req_desktop_test",
            "app_package": "lab.exitguide.stream.demo",
            "app_version": "1.0.0",
            "platform": "android",
            "locale": "ko-KR",
            "goal_id": "cancel_subscription",
            "session": {
                "last_confirmed_state_id": None,
                "failed_element_ids": [],
                "failed_candidate_meanings": [],
                "retry_count": 0,
            },
            "screen_elements": [
                {"id": "title", "text": "계정", "role": "heading", "clickable": False},
                {"id": "profile", "text": "프로필", "role": "text", "clickable": False},
                {"id": "settings", "text": "설정", "role": "text", "clickable": False},
                {"id": "target", "text": "구매 항목 및 멤버십", "role": "button", "clickable": True},
            ],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["target_element_id"] == "target"
    assert response.json()["dark_pattern"]["overall_risk"] == "low"
    print("desktop bundle checks ok")


if __name__ == "__main__":
    main()
