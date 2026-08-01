from dataclasses import dataclass

from app.services.goals import GOAL_LABELS, normalize_goal_id
from app.services.types import ExtractedScreen


DEFAULT_GOAL_ID = "protect_user_intent"


@dataclass(frozen=True)
class GoalContext:
    id: str
    label: str
    llm_goal_id: str
    inferred: bool = False


def resolve_goal_context(
    goal_id: str | None,
    goal_text: str | None,
    screen: ExtractedScreen | None = None,
    infer_goal: bool = False,
) -> GoalContext:
    cleaned_goal = _clean_goal_text(goal_text)
    if cleaned_goal:
        inferred_id = infer_goal_id_from_text(cleaned_goal) or DEFAULT_GOAL_ID
        return GoalContext(
            id="custom_goal",
            label=cleaned_goal,
            llm_goal_id=inferred_id,
            inferred=inferred_id != DEFAULT_GOAL_ID,
        )

    if infer_goal and screen is not None:
        inferred_id = infer_goal_id_from_screen(screen) or DEFAULT_GOAL_ID
        return GoalContext(
            id=inferred_id,
            label=GOAL_LABELS[inferred_id],
            llm_goal_id=inferred_id,
            inferred=True,
        )

    normalized = normalize_goal_id(goal_id or DEFAULT_GOAL_ID)
    return GoalContext(
        id=normalized,
        label=GOAL_LABELS[normalized],
        llm_goal_id=normalized,
        inferred=False,
    )


def infer_goal_id_from_text(goal_text: str) -> str | None:
    source = goal_text.lower()
    if _contains_any(
        source,
        (
            "마케팅",
            "광고",
            "선택 동의",
            "약관",
            "동의",
            "알림",
            "문자",
            "푸시",
            "혜택",
            "제3자",
            "개인정보 제공",
            "consent",
            "terms",
            "marketing",
        ),
    ):
        return "reject_marketing"
    if _contains_any(source, ("추가 비용", "부가", "결제", "보험", "배송", "보증", "addon", "checkout", "pay")):
        return "buy_without_addons"
    if _contains_any(source, ("무료 체험", "체험", "trial", "자동 결제", "갱신")):
        return "cancel_trial"
    if _contains_any(source, ("탈퇴", "계정 삭제", "회원 탈퇴", "delete account", "withdraw")):
        return "delete_account"
    if _contains_any(source, ("구독", "해지", "취소", "cancel", "subscription")):
        return "cancel_subscription"
    return None


def infer_goal_id_from_screen(screen: ExtractedScreen) -> str | None:
    source = " ".join([screen.title, screen.text, *(element.label for element in screen.elements)]).lower()
    if _contains_any(source, ("마케팅", "광고", "선택 동의", "전체 동의", "약관", "consent", "marketing", "agree")):
        return "reject_marketing"
    if _contains_any(source, ("배송 보험", "연장 보증", "추가", "결제", "주문", "pay", "checkout", "addon")):
        return "buy_without_addons"
    if _contains_any(source, ("무료 체험", "체험", "자동 결제", "갱신", "trial", "renews")):
        return "cancel_trial"
    if _contains_any(source, ("탈퇴", "계정 삭제", "계정 유지", "delete account", "account deletion")):
        return "delete_account"
    if _contains_any(source, ("구독", "해지", "혜택 유지", "cancel", "subscription")):
        return "cancel_subscription"
    return None


def _clean_goal_text(goal_text: str | None) -> str:
    return " ".join((goal_text or "").strip().split())[:160]


def _contains_any(source: str, needles: tuple[str, ...]) -> bool:
    return any(needle in source for needle in needles)
