from collections import Counter
from dataclasses import dataclass

from app.schemas import ProofCard, RecommendedAction, RiskBreakdown, RiskLevel, UiElement
from app.services.types import ElementJudgment, ExtractedElement


@dataclass(frozen=True)
class ResponseParts:
    overall_risk: RiskLevel
    alignment_score: int
    risk_counts: RiskBreakdown
    summary: str
    elements: list[UiElement]
    recommended_action: RecommendedAction
    proof_card: ProofCard


def build_response_parts(goal_label: str, judgments: list[ElementJudgment]) -> ResponseParts:
    ui_elements = [_to_ui_element(_apply_goal_overrides(goal_label, judgment)) for judgment in judgments]
    risk_counts = Counter(element.risk_level for element in ui_elements)
    risk_breakdown = RiskBreakdown(
        low=risk_counts["low"],
        medium=risk_counts["medium"],
        high=risk_counts["high"],
    )
    overall_risk = _overall_risk(risk_counts)
    alignment_score = _alignment_score(risk_breakdown)
    recommendation = _recommended_action(ui_elements)
    proof_card = _proof_card(goal_label, ui_elements, recommendation)
    summary = _summary(overall_risk, risk_counts)
    return ResponseParts(
        overall_risk=overall_risk,
        alignment_score=alignment_score,
        risk_counts=risk_breakdown,
        summary=summary,
        elements=ui_elements,
        recommended_action=recommendation,
        proof_card=proof_card,
    )


def _to_ui_element(judgment: ElementJudgment) -> UiElement:
    risk_level = _risk_for(judgment)
    return UiElement(
        id=judgment.element.id,
        label=judgment.element.label,
        element_type=judgment.element.element_type,
        direction=judgment.direction,
        risk_level=risk_level,
        reason=judgment.reason,
        signals=_signals_for(judgment),
    )


def _apply_goal_overrides(goal_label: str, judgment: ElementJudgment) -> ElementJudgment:
    element = judgment.element
    goal_source = goal_label.lower()

    if _is_optional_consent_goal(goal_source) and _is_conflicting_optional_consent(element):
        return ElementJudgment(
            element=element,
            direction="conflicts_with_goal",
            reason="선택 약관이나 마케팅 동의를 피하려면 이 항목을 해제하거나 필수 항목만 남겨야 합니다.",
        )

    return judgment


def _risk_for(judgment: ElementJudgment) -> RiskLevel:
    element = judgment.element
    if judgment.direction == "conflicts_with_goal":
        if element.monetary_impact or element.default_selected or element.prominence >= 3:
            return "high"
        return "medium"
    if judgment.direction == "needs_check":
        if element.default_selected and element.optional:
            return "medium"
        if element.monetary_impact and not element.optional:
            return "medium"
    return "low"


def _signals_for(judgment: ElementJudgment) -> list[str]:
    element = judgment.element
    signals: list[str] = []
    if element.prominence >= 3:
        signals.append("강조됨")
    if element.default_selected:
        signals.append("기본 선택")
    if element.monetary_impact:
        signals.append("금액 영향")
    if element.optional:
        signals.append("선택 항목")
    if judgment.direction == "conflicts_with_goal":
        signals.append("목표와 충돌")
    if judgment.direction == "supports_goal":
        signals.append("목표에 부합")
    return signals


def _overall_risk(risk_counts: Counter) -> RiskLevel:
    if risk_counts["high"]:
        return "high"
    if risk_counts["medium"]:
        return "medium"
    return "low"


def _alignment_score(risk_breakdown: RiskBreakdown) -> int:
    penalty = risk_breakdown.high * 32 + risk_breakdown.medium * 14
    return max(0, 100 - penalty)


def _recommended_action(elements: list[UiElement]) -> RecommendedAction:
    supporting = next((element for element in elements if element.direction == "supports_goal"), None)
    high_risk_elements = [element for element in elements if element.risk_level == "high"]
    high_risk = high_risk_elements[0] if high_risk_elements else None
    medium_risk_elements = [element for element in elements if element.risk_level == "medium"]

    if supporting:
        avoid_count = len(high_risk_elements)
        avoid_clause = (
            f", 목표와 충돌하는 고위험 선택지 {avoid_count}개는 피하세요"
            if avoid_count
            else ""
        )
        return RecommendedAction(
            title="목표에 맞는 선택지를 우선 확인하세요",
            description=f"'{supporting.label}' 선택지를 우선 확인하세요{avoid_clause}.",
            target_element_id=supporting.id,
        )

    if high_risk:
        labels = ", ".join(element.label for element in high_risk_elements[:2])
        remaining = len(high_risk_elements) - 2
        suffix = f" 외 {remaining}개" if remaining > 0 else ""
        return RecommendedAction(
            title="고위험 선택지를 먼저 해제하세요",
            description=f"계속하기 전에 '{labels}{suffix}' 항목을 확인하거나 해제하세요.",
            target_element_id=high_risk.id,
        )

    if medium_risk_elements:
        labels = ", ".join(element.label for element in medium_risk_elements[:2])
        remaining = len(medium_risk_elements) - 2
        suffix = f" 외 {remaining}개" if remaining > 0 else ""
        return RecommendedAction(
            title="주의 항목을 먼저 확인하세요",
            description=f"'{labels}{suffix}' 항목이 목표와 맞는지 확인한 뒤 진행하세요.",
            target_element_id=medium_risk_elements[0].id,
        )

    return RecommendedAction(
        title="화면을 확인한 뒤 진행하세요",
        description="현재 화면에서 목표와 강하게 충돌하는 행동은 뚜렷하게 보이지 않습니다.",
        target_element_id=None,
    )


def _proof_card(goal_label: str, elements: list[UiElement], recommendation: RecommendedAction) -> ProofCard:
    evidence = [
        f"{element.label}: {element.reason}"
        for element in elements
        if element.direction in {"conflicts_with_goal", "supports_goal"} or element.risk_level in {"high", "medium"}
    ][:4]
    if not evidence:
        evidence = ["현재 화면에서 선택 목표와 강하게 충돌하는 요소는 확인되지 않았습니다."]
    return ProofCard(
        goal=goal_label,
        summary=recommendation.description,
        key_evidence=evidence,
        disclaimer="이 결과는 선택 목표에 맞춘 안내이며 법적 판단이 아닙니다.",
    )


def _summary(overall_risk: RiskLevel, risk_counts: Counter) -> str:
    if overall_risk == "high":
        return f"목표와 충돌하는 고위험 요소가 {risk_counts['high']}개 보입니다."
    if overall_risk == "medium":
        return "계속하기 전에 확인해야 할 선택지가 있습니다."
    return "선택 목표와 강하게 충돌하는 요소는 보이지 않습니다."


def _is_optional_consent_goal(goal_source: str) -> bool:
    return any(
        token in goal_source
        for token in (
            "약관",
            "동의",
            "마케팅",
            "광고",
            "혜택",
            "알림",
            "문자",
            "푸시",
            "프로모션",
            "consent",
            "terms",
            "marketing",
            "privacy",
            "promotion",
        )
    )


def _is_conflicting_optional_consent(element: ExtractedElement) -> bool:
    source = element.label.lower()
    optional_signal = (
        element.optional
        or "(선택)" in source
        or "[선택]" in source
        or "선택사항" in source
        or "선택 항목" in source
        or "선택 정보" in source
    )
    consent_signal = any(
        token in source
        for token in (
            "마케팅",
            "광고",
            "혜택",
            "알림",
            "문자",
            "sms",
            "푸시",
            "push",
            "이메일",
            "프로모션",
            "이벤트",
            "제3자",
            "제휴사",
            "개인정보 제공",
            "위치 기반",
            "맞춤형 광고",
            "동의하고 계속",
            "전체 동의",
        )
    )
    bundled_action = element.element_type == "button" and optional_signal and consent_signal
    selected_optional = optional_signal and element.default_selected
    agree_all_with_optional = "전체 동의" in source and (optional_signal or consent_signal)
    return selected_optional or agree_all_with_optional or bundled_action
