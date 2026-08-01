from app.schemas import AnalysisResponse, FlowAnalysisResponse, ProofCard, RiskBreakdown, RiskLevel
from app.services.analysis import analyze_screenshot
from app.services.provider_runtime import RuntimeProviderOptions
from app.services.scenarios import get_demo_scenario
from app.services.trace import stable_trace_id


def analyze_demo_flow(
    goal_id: str | None,
    scenario_ids: list[str],
    goal_text: str | None = None,
    infer_goal: bool = False,
    provider_options: RuntimeProviderOptions | None = None,
) -> FlowAnalysisResponse:
    _validate_flow_length(len(scenario_ids))
    analyses = [
        analyze_screenshot(
            goal_id=goal_id,
            image_bytes=b"demo flow scenario",
            filename=get_demo_scenario(scenario_id).fixture_filename,
            analysis_mode="demo",
            goal_text=goal_text,
            infer_goal=infer_goal,
            provider_options=provider_options,
        )
        for scenario_id in scenario_ids
    ]

    return build_flow_response(analyses=analyses)


def analyze_uploaded_flow(
    goal_id: str | None,
    uploads: list[tuple[bytes, str | None]],
    goal_text: str | None = None,
    infer_goal: bool = False,
    provider_options: RuntimeProviderOptions | None = None,
) -> FlowAnalysisResponse:
    _validate_flow_length(len(uploads))
    analyses = [
        analyze_screenshot(
            goal_id=goal_id,
            image_bytes=image_bytes,
            filename=filename,
            analysis_mode="upload",
            goal_text=goal_text,
            infer_goal=infer_goal,
            provider_options=provider_options,
        )
        for image_bytes, filename in uploads
    ]

    return build_flow_response(analyses=analyses)


def build_flow_response(analyses: list[AnalysisResponse]) -> FlowAnalysisResponse:
    _validate_flow_length(len(analyses))
    flow_goal_id = analyses[0].goal_id
    flow_goal_label = analyses[0].goal_label
    overall_risk = _overall_flow_risk(analyses)
    alignment_score = min((analysis.alignment_score for analysis in analyses), default=100)
    risk_counts = _flow_risk_counts(analyses)
    risk_path = [analysis.overall_risk for analysis in analyses]
    highest_risk_screen_number = _highest_risk_screen_number(analyses)
    proof_card = _flow_proof_card(goal_label=flow_goal_label, analyses=analyses)

    return FlowAnalysisResponse(
        flow_id=stable_trace_id("fl", [flow_goal_id, flow_goal_label, *(analysis.analysis_id for analysis in analyses)]),
        goal_id=flow_goal_id,
        goal_label=flow_goal_label,
        overall_risk=overall_risk,
        alignment_score=alignment_score,
        screen_count=len(analyses),
        highest_risk_screen_number=highest_risk_screen_number,
        risk_counts=risk_counts,
        risk_path=risk_path,
        summary=_flow_summary(overall_risk=overall_risk, analyses=analyses),
        screens=analyses,
        proof_card=proof_card,
    )


def _validate_flow_length(screen_count: int) -> None:
    if not 2 <= screen_count <= 6:
        raise ValueError("흐름 분석은 2-6개 화면으로 실행하세요.")


def _overall_flow_risk(analyses: list[AnalysisResponse]) -> RiskLevel:
    if any(analysis.overall_risk == "high" for analysis in analyses):
        return "high"
    if any(analysis.overall_risk == "medium" for analysis in analyses):
        return "medium"
    return "low"


def _highest_risk_screen_number(analyses: list[AnalysisResponse]) -> int | None:
    if not analyses:
        return None

    risk_rank = {"low": 0, "medium": 1, "high": 2}
    highest_index = max(
        range(len(analyses)),
        key=lambda index: risk_rank[analyses[index].overall_risk],
    )
    return highest_index + 1


def _flow_risk_counts(analyses: list[AnalysisResponse]) -> RiskBreakdown:
    return RiskBreakdown(
        low=sum(analysis.risk_counts.low for analysis in analyses),
        medium=sum(analysis.risk_counts.medium for analysis in analyses),
        high=sum(analysis.risk_counts.high for analysis in analyses),
    )


def _flow_summary(overall_risk: RiskLevel, analyses: list[AnalysisResponse]) -> str:
    screen_count = len(analyses)
    if len(analyses) >= 2 and analyses[0].overall_risk != analyses[-1].overall_risk:
        return (
            f"{screen_count}개 화면에서 위험도가 {analyses[0].overall_risk}에서 {analyses[-1].overall_risk}로 변했습니다. "
            "계속하기 전 가장 위험한 단계를 확인하세요."
        )
    if overall_risk == "high":
        return f"이 흐름의 {screen_count}개 화면에서 고위험 목표 충돌이 확인되었습니다."
    if overall_risk == "medium":
        return f"이 흐름의 {screen_count}개 화면 중 확인이 필요한 선택지가 있습니다."
    return f"{screen_count}개 화면 전체에서 강한 목표 충돌은 확인되지 않았습니다."


def _flow_proof_card(goal_label: str, analyses: list[AnalysisResponse]) -> ProofCard:
    evidence: list[str] = []
    for analysis in analyses:
        evidence.extend(f"{analysis.screen_title}: {item}" for item in analysis.proof_card.key_evidence[:2])

    return ProofCard(
        goal=goal_label,
        summary=_flow_summary(_overall_flow_risk(analyses), analyses),
        key_evidence=evidence[:6] or ["현재 흐름에서 선택 목표와 강하게 충돌하는 요소는 확인되지 않았습니다."],
        disclaimer="이 결과는 화면 흐름 기준의 이용 안내이며 법적 판단이 아닙니다.",
    )
