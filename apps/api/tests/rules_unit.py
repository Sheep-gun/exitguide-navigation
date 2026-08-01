from app.services.rules import build_response_parts
from app.services.trace import stable_trace_id
from app.services.types import ElementJudgment, ExtractedElement


def main() -> None:
    high_conflict = ElementJudgment(
        element=ExtractedElement(
            id="addon",
            label="Shipping insurance +2,900 KRW",
            element_type="checkbox",
            default_selected=True,
            monetary_impact=True,
            optional=True,
        ),
        direction="conflicts_with_goal",
        reason="This optional item is selected by default and may add cost.",
    )
    supporting = ElementJudgment(
        element=ExtractedElement(
            id="pay",
            label="Pay now",
            element_type="button",
        ),
        direction="supports_goal",
        reason="Payment is available after optional add-ons are unchecked.",
    )
    high_parts = build_response_parts(
        goal_label="Buy without extra charges",
        judgments=[high_conflict, supporting],
    )
    assert high_parts.overall_risk == "high"
    assert high_parts.alignment_score == 68
    assert high_parts.risk_counts.high == 1
    assert high_parts.recommended_action.target_element_id == "pay"
    assert "기본 선택" in high_parts.elements[0].signals
    assert "금액 영향" in high_parts.elements[0].signals

    medium_check = ElementJudgment(
        element=ExtractedElement(
            id="optional",
            label="Optional reminder",
            element_type="checkbox",
            default_selected=True,
            optional=True,
        ),
        direction="needs_check",
        reason="Optional state should be checked before continuing.",
    )
    medium_parts = build_response_parts(goal_label="Review optional setting", judgments=[medium_check])
    assert medium_parts.overall_risk == "medium"
    assert medium_parts.alignment_score == 86
    assert medium_parts.risk_counts.medium == 1
    assert medium_parts.recommended_action.target_element_id == "optional"
    assert "주의" in medium_parts.recommended_action.title

    terms_check = ElementJudgment(
        element=ExtractedElement(
            id="terms",
            label="약관 동의 내용",
            element_type="content",
        ),
        direction="conflicts_with_goal",
        reason="사용자의 목표와 맞지 않을 수 있는 약관 동의 내용입니다.",
    )
    terms_parts = build_response_parts(goal_label="가입성 약관 확인", judgments=[terms_check])
    assert terms_parts.overall_risk == "medium"
    assert terms_parts.recommended_action.target_element_id == "terms"

    optional_terms = ElementJudgment(
        element=ExtractedElement(
            id="optional_terms",
            label="(선택) 광고성 정보 수신 동의",
            element_type="checkbox",
            default_selected=True,
            optional=True,
        ),
        direction="needs_check",
        reason="Model only marked this as needs_check.",
    )
    optional_terms_parts = build_response_parts(
        goal_label="선택 마케팅 동의 거절하기",
        judgments=[optional_terms],
    )
    assert optional_terms_parts.overall_risk == "high"
    assert optional_terms_parts.elements[0].direction == "conflicts_with_goal"
    assert optional_terms_parts.recommended_action.target_element_id == "optional_terms"

    selected_optional_terms = ElementJudgment(
        element=ExtractedElement(
            id="agree_all",
            label="전체 동의 - 필수 약관 및 선택 마케팅 수신 포함",
            element_type="checkbox",
            prominence=3,
            default_selected=True,
            optional=True,
        ),
        direction="needs_check",
        reason="Model only marked this as needs_check.",
    )
    selected_optional_terms_parts = build_response_parts(
        goal_label="선택 마케팅 동의 거절하기",
        judgments=[selected_optional_terms],
    )
    assert selected_optional_terms_parts.overall_risk == "high"
    assert selected_optional_terms_parts.elements[0].direction == "conflicts_with_goal"

    bundled_button = ElementJudgment(
        element=ExtractedElement(
            id="agree_continue",
            label="동의하고 계속하기 - 선택 마케팅 정보 수신 포함",
            element_type="button",
            prominence=3,
            optional=True,
        ),
        direction="needs_check",
        reason="Model only marked this as needs_check.",
    )
    bundled_button_parts = build_response_parts(
        goal_label="선택 마케팅 동의 거절하기",
        judgments=[bundled_button],
    )
    assert bundled_button_parts.overall_risk == "high"
    assert bundled_button_parts.elements[0].direction == "conflicts_with_goal"

    low_parts = build_response_parts(goal_label="Delete account", judgments=[supporting])
    assert low_parts.overall_risk == "low"
    assert low_parts.alignment_score == 100
    assert low_parts.recommended_action.target_element_id == "pay"

    trace_id = stable_trace_id("an", ["goal", "screen", "high"])
    assert trace_id.startswith("an_")
    assert len(trace_id) == 15
    assert trace_id == stable_trace_id("an", ["goal", "screen", "high"])
    assert trace_id != stable_trace_id("an", ["goal", "high", "screen"])

    print("api unit checks ok")


if __name__ == "__main__":
    main()
