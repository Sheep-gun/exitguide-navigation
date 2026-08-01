from app.schemas import (
    DarkPatternFinding,
    DarkPatternInspectRequest,
    DarkPatternInspectResponse,
    RiskLevel,
)
from app.services.goals import GOAL_LABELS, get_goal_label
from app.services.llm import MockLlmProvider
from app.services.rules import build_response_parts
from app.services.types import ExtractedElement, ExtractedScreen


RISK_RANK: dict[RiskLevel, int] = {"low": 0, "medium": 1, "high": 2}


def inspect_dark_pattern(request: DarkPatternInspectRequest) -> DarkPatternInspectResponse:
    goal_id = _resolve_goal_id(request.goal_id, request.goal_text)
    goal_label = get_goal_label(goal_id)
    extracted_elements = [
        ExtractedElement(
            id=element.id,
            label=element.text,
            element_type=element.role,
            prominence=element.prominence,
            default_selected=element.default_selected,
            monetary_impact=element.monetary_impact,
            optional=element.optional,
        )
        for element in request.elements
    ]
    screen = ExtractedScreen(
        title=request.screen_title,
        text=request.screen_text,
        elements=extracted_elements,
    )
    judgments = MockLlmProvider().judge_elements(
        goal_id=goal_id,
        goal_label=goal_label,
        screen=screen,
    )
    parts = build_response_parts(goal_label=goal_label, judgments=judgments)
    findings = _detect_findings(goal_id, extracted_elements, parts.elements)
    finding_risk = max((finding.severity for finding in findings), key=RISK_RANK.get, default="low")
    overall_risk = max((parts.overall_risk, finding_risk), key=RISK_RANK.get)
    pattern_penalty = sum(24 if finding.severity == "high" else 10 for finding in findings)
    alignment_score = min(parts.alignment_score, max(0, 100 - pattern_penalty))
    summary = (
        f"사용자 목적을 방해할 수 있는 다크패턴 {len(findings)}개를 확인했습니다."
        if findings
        else "현재 화면에서 뚜렷한 다크패턴은 확인되지 않았습니다."
    )
    return DarkPatternInspectResponse(
        request_id=request.request_id,
        goal_id=goal_id,
        goal_label=goal_label,
        screen_title=request.screen_title,
        overall_risk=overall_risk,
        alignment_score=alignment_score,
        summary=summary,
        findings=findings,
        elements=parts.elements,
        recommended_action=parts.recommended_action,
        proof_card=parts.proof_card,
    )


def _resolve_goal_id(goal_id: str | None, goal_text: str | None) -> str:
    if goal_id and goal_id.strip() in GOAL_LABELS:
        return goal_id.strip()
    source = "".join((goal_text or "").lower().split())
    if any(token in source for token in ("구독해지", "자동결제", "멤버십해지", "cancel")):
        return "cancel_subscription"
    if any(token in source for token in ("마케팅", "광고알림", "수신동의", "프로모션")):
        return "reject_marketing"
    if any(token in source for token in ("추가비용", "부가상품", "원치않는결제")):
        return "buy_without_addons"
    if any(token in source for token in ("회원탈퇴", "계정삭제", "deleteaccount")):
        return "delete_account"
    return "protect_user_intent"


def _detect_findings(goal_id: str, source_elements: list[ExtractedElement], judged_elements) -> list[DarkPatternFinding]:
    findings: list[DarkPatternFinding] = []
    judged_by_id = {element.id: element for element in judged_elements}

    if goal_id in {"cancel_subscription", "cancel_trial", "protect_user_intent"}:
        for element in source_elements:
            label = element.label.lower()
            if any(token in label for token in ("일시중지", "유지", "할인받고", "계속 이용", "혜택 유지")):
                findings.append(
                    DarkPatternFinding(
                        type="retention_misdirection",
                        label="해지 대신 유지 유도",
                        severity="high" if element.prominence >= 3 else "medium",
                        element_id=element.id,
                        evidence=element.label,
                        explanation="해지를 원하는 사용자에게 일시중지·할인·유지 선택을 더 매력적으로 제시합니다.",
                    )
                )

    for element in source_elements:
        if element.default_selected and element.optional and element.monetary_impact:
            findings.append(
                DarkPatternFinding(
                    type="preselected_cost",
                    label="유료 부가상품 기본 선택",
                    severity="high",
                    element_id=element.id,
                    evidence=element.label,
                    explanation="사용자가 직접 고르지 않은 선택 상품이 결제 금액에 포함될 수 있습니다.",
                )
            )

    if goal_id in {"reject_marketing", "protect_user_intent"}:
        for element in source_elements:
            label = element.label.lower()
            bundled = "전체 동의" in label and any(token in label for token in ("선택", "마케팅", "광고"))
            selected_optional = element.default_selected and element.optional and any(
                token in label for token in ("마케팅", "광고", "프로모션", "수신")
            )
            if bundled or selected_optional:
                findings.append(
                    DarkPatternFinding(
                        type="bundled_consent",
                        label="필수·선택 동의 묶음",
                        severity="high" if element.default_selected or element.prominence >= 3 else "medium",
                        element_id=element.id,
                        evidence=element.label,
                        explanation="필수 약관과 선택 마케팅 동의가 함께 선택되도록 구성되어 있습니다.",
                    )
                )

    supporting = [
        source
        for source in source_elements
        if judged_by_id.get(source.id) and judged_by_id[source.id].direction == "supports_goal"
    ]
    conflicting = [
        source
        for source in source_elements
        if judged_by_id.get(source.id) and judged_by_id[source.id].direction == "conflicts_with_goal"
    ]
    if supporting and conflicting:
        safest = min(supporting, key=lambda item: item.prominence)
        strongest_conflict = max(conflicting, key=lambda item: item.prominence)
        if strongest_conflict.prominence > safest.prominence:
            findings.append(
                DarkPatternFinding(
                    type="asymmetric_prominence",
                    label="목적 반대 선택지 강조",
                    severity="high" if strongest_conflict.prominence >= 3 else "medium",
                    element_id=strongest_conflict.id,
                    evidence=f"{strongest_conflict.label} 강조도 {strongest_conflict.prominence} / {safest.label} 강조도 {safest.prominence}",
                    explanation="사용자 목적과 반대되는 선택지가 올바른 선택지보다 더 강하게 강조되어 있습니다.",
                )
            )

    unique: dict[tuple[str, str], DarkPatternFinding] = {}
    for finding in findings:
        unique[(finding.type, finding.element_id)] = finding
    return list(unique.values())
