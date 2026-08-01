from dataclasses import dataclass


@dataclass(frozen=True)
class DemoFlow:
    id: str
    label: str
    description: str
    goal_id: str
    scenario_ids: list[str]


DEMO_FLOWS = {
    "subscription_cancel_path": DemoFlow(
        id="subscription_cancel_path",
        label="해지 흐름 점검",
        description="유지 유도 화면과 최종 해지 확인 화면을 비교합니다.",
        goal_id="protect_user_intent",
        scenario_ids=["subscription_cancel", "subscription_confirmation"],
    ),
    "trial_cancel_path": DemoFlow(
        id="trial_cancel_path",
        label="체험 해지 흐름",
        description="자동 결제 압박 화면과 해지 완료 화면을 비교합니다.",
        goal_id="protect_user_intent",
        scenario_ids=["trial_renewal", "trial_success"],
    ),
    "addon_risk_contrast": DemoFlow(
        id="addon_risk_contrast",
        label="부가 비용 비교",
        description="기본 선택된 부가 상품 결제와 깨끗한 결제를 비교합니다.",
        goal_id="protect_user_intent",
        scenario_ids=["checkout_addons", "checkout_clean"],
    ),
    "account_delete_path": DemoFlow(
        id="account_delete_path",
        label="탈퇴 흐름 점검",
        description="계정 유지 유도 화면과 최종 탈퇴 확인 화면을 비교합니다.",
        goal_id="protect_user_intent",
        scenario_ids=["account_deletion", "account_deletion_confirmation"],
    ),
}
