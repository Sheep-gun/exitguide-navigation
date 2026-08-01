from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def main() -> None:
    assert_retention_misdirection()
    assert_preselected_paid_addon()
    assert_bundled_marketing_consent()
    assert_clean_choice_reduces_risk()
    print("dark pattern checks ok")


def assert_retention_misdirection() -> None:
    result = inspect(
        goal_id="cancel_subscription",
        title="구독을 해지하시겠어요?",
        elements=[
            element("discount_retention_button", "3개월 50% 할인받고 유지", prominence=3),
            element("pause_subscription_button", "일시중지", prominence=2),
            element("secondary_cancel_button", "계속 해지", prominence=1),
        ],
    )
    finding_types = {finding["type"] for finding in result["findings"]}
    assert result["overall_risk"] == "high"
    assert "retention_misdirection" in finding_types
    assert "asymmetric_prominence" in finding_types
    assert result["recommended_action"]["target_element_id"] == "secondary_cancel_button"


def assert_preselected_paid_addon() -> None:
    result = inspect(
        goal_id="buy_without_addons",
        title="결제 확인",
        elements=[
            element(
                "warranty_addon",
                "안심 보증 +2,900원",
                role="checkbox",
                default_selected=True,
                optional=True,
                monetary_impact=True,
                prominence=2,
            ),
            element("pay", "39,900원 결제", prominence=2),
        ],
    )
    assert result["overall_risk"] == "high"
    assert "preselected_cost" in {finding["type"] for finding in result["findings"]}
    assert result["recommended_action"]["target_element_id"] == "warranty_addon"


def assert_bundled_marketing_consent() -> None:
    result = inspect(
        goal_id="reject_marketing",
        title="약관 동의",
        elements=[
            element(
                "agree_all",
                "전체 동의 - 필수 약관 및 선택 마케팅 포함",
                role="checkbox",
                default_selected=True,
                optional=True,
                prominence=3,
            ),
            element("required_terms", "필수 이용약관 동의", role="checkbox"),
            element(
                "marketing",
                "선택 마케팅 정보 수신 동의",
                role="checkbox",
                default_selected=True,
                optional=True,
            ),
        ],
    )
    assert result["overall_risk"] == "high"
    assert "bundled_consent" in {finding["type"] for finding in result["findings"]}


def assert_clean_choice_reduces_risk() -> None:
    result = inspect(
        goal_id="buy_without_addons",
        title="결제 확인",
        elements=[
            element(
                "warranty_addon",
                "안심 보증 +2,900원",
                role="checkbox",
                default_selected=False,
                optional=True,
                monetary_impact=True,
            ),
            element("pay", "39,900원 결제", prominence=2),
        ],
    )
    assert result["overall_risk"] == "low"
    assert not result["findings"]


def inspect(goal_id: str, title: str, elements: list[dict]) -> dict:
    response = client.post(
        "/v1/dark-pattern/inspect",
        json={
            "request_id": "req_dark_pattern_test",
            "goal_id": goal_id,
            "screen_title": title,
            "screen_text": " ".join(item["text"] for item in elements),
            "elements": elements,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def element(
    element_id: str,
    text: str,
    *,
    role: str = "button",
    default_selected: bool = False,
    optional: bool = False,
    monetary_impact: bool = False,
    prominence: int = 1,
) -> dict:
    return {
        "id": element_id,
        "text": text,
        "role": role,
        "clickable": True,
        "prominence": prominence,
        "default_selected": default_selected,
        "optional": optional,
        "monetary_impact": monetary_impact,
    }


if __name__ == "__main__":
    main()
