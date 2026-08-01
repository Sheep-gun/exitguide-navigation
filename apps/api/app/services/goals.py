GOAL_LABELS = {
    "protect_user_intent": "원치 않는 유도 피하기",
    "cancel_subscription": "구독 해지하기",
    "cancel_trial": "무료 체험 해지하기",
    "buy_without_addons": "추가 비용 없이 결제하기",
    "reject_marketing": "선택 마케팅 동의 거절하기",
    "delete_account": "계정 탈퇴하기",
}

GOAL_DESCRIPTIONS = {
    "protect_user_intent": "해지 방해, 추가 결제, 선택 동의, 탈퇴 방해를 한 번에 확인합니다.",
    "cancel_subscription": "구독 해지가 실제로 진행되는 선택지를 확인합니다.",
    "cancel_trial": "자동 결제 시점과 체험 해지 버튼이 숨어 있는지 확인합니다.",
    "buy_without_addons": "결제 전 선택된 부가 상품과 추가 비용을 확인합니다.",
    "reject_marketing": "필수 약관과 선택 마케팅 동의를 분리해 확인합니다.",
    "delete_account": "탈퇴 진행 경로와 데이터 안내를 함께 확인합니다.",
}


class UnsupportedGoalError(ValueError):
    pass


def normalize_goal_id(goal_id: str) -> str:
    normalized = goal_id.strip()
    if normalized not in GOAL_LABELS:
        raise UnsupportedGoalError(f"Unsupported goal_id: {goal_id}")
    return normalized


def get_goal_label(goal_id: str) -> str:
    return GOAL_LABELS[normalize_goal_id(goal_id)]
