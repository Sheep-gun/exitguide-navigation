from dataclasses import dataclass


@dataclass(frozen=True)
class DemoScenario:
    id: str
    label: str
    description: str
    recommended_goal_id: str
    fixture_filename: str


DEMO_SCENARIOS = {
    "subscription_cancel": DemoScenario(
        id="subscription_cancel",
        label="구독 해지 방해",
        description="해지 진행 버튼보다 유지 혜택을 더 강하게 보여주는 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="subscription-cancel-retention.png",
    ),
    "subscription_confirmation": DemoScenario(
        id="subscription_confirmation",
        label="구독 해지 완료 확인",
        description="다음 결제 없음이 명확하게 보이는 낮은 위험 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="subscription-cancel-confirmation.png",
    ),
    "trial_renewal": DemoScenario(
        id="trial_renewal",
        label="무료 체험 자동 결제",
        description="곧 결제될 금액과 체험 연장 유도가 함께 있는 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="trial-renewal-warning.png",
    ),
    "trial_success": DemoScenario(
        id="trial_success",
        label="무료 체험 해지 완료",
        description="체험 해지와 다음 결제 없음이 확인되는 낮은 위험 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="trial-cancel-success.png",
    ),
    "checkout_addons": DemoScenario(
        id="checkout_addons",
        label="결제 부가 상품",
        description="선택 부가 상품이 기본 선택된 결제 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="checkout-preselected-addon.png",
    ),
    "checkout_clean": DemoScenario(
        id="checkout_clean",
        label="깨끗한 결제",
        description="선택 부가 상품이 보이지만 기본 선택되지 않은 낮은 위험 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="checkout-no-preselected-addon.png",
    ),
    "marketing_consent": DemoScenario(
        id="marketing_consent",
        label="마케팅 동의 묶음",
        description="전체 동의에 선택 마케팅 동의가 섞여 있는 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="marketing-consent-optional.png",
    ),
    "required_terms_only": DemoScenario(
        id="required_terms_only",
        label="필수 약관만 있는 화면",
        description="선택 마케팅 동의 없이 필수 약관만 확인되는 낮은 위험 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="consent-required-only.png",
    ),
    "account_deletion": DemoScenario(
        id="account_deletion",
        label="계정 탈퇴 방해",
        description="탈퇴 진행보다 계정 유지 버튼을 더 강하게 보여주는 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="account-delete-retention.png",
    ),
    "account_deletion_confirmation": DemoScenario(
        id="account_deletion_confirmation",
        label="계정 탈퇴 완료 확인",
        description="탈퇴 완료와 데이터 안내가 명확한 낮은 위험 화면입니다.",
        recommended_goal_id="protect_user_intent",
        fixture_filename="account-delete-confirmation.png",
    ),
}


def get_demo_scenario(scenario_id: str) -> DemoScenario:
    try:
        return DEMO_SCENARIOS[scenario_id]
    except KeyError as exc:
        raise ValueError(f"지원되지 않는 데모 시나리오입니다: {scenario_id}") from exc
