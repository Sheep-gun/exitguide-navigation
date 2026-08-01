from app.config import get_settings
from app.schemas import AnalysisMode, AnalysisResponse
from app.services.goal_resolution import DEFAULT_GOAL_ID, resolve_goal_context
from app.services.goals import GOAL_LABELS, normalize_goal_id
from app.services.llm import get_llm_provider
from app.services.ocr import get_ocr_provider
from app.services.provider_runtime import RuntimeProviderOptions, resolve_runtime_provider
from app.services.rules import build_response_parts
from app.services.trace import stable_trace_id


def analyze_screenshot(
    goal_id: str | None,
    image_bytes: bytes,
    filename: str | None = None,
    analysis_mode: AnalysisMode = "upload",
    goal_text: str | None = None,
    infer_goal: bool = False,
    provider_options: RuntimeProviderOptions | None = None,
) -> AnalysisResponse:
    settings = get_settings()
    runtime = resolve_runtime_provider(settings, provider_options)
    ocr_goal_id = _ocr_goal_id(goal_id)
    ocr_provider_name = "mock" if analysis_mode == "demo" else runtime.ocr_provider
    screen = get_ocr_provider(ocr_provider_name, runtime.settings).extract(
        image_bytes=image_bytes,
        filename=filename,
        goal_id=ocr_goal_id,
    )
    goal_context = resolve_goal_context(
        goal_id=goal_id,
        goal_text=goal_text,
        screen=screen,
        infer_goal=infer_goal,
    )
    judgments = get_llm_provider(runtime.llm_provider, runtime.settings).judge_elements(
        goal_id=goal_context.llm_goal_id,
        goal_label=goal_context.label,
        screen=screen,
    )
    response_parts = build_response_parts(goal_label=goal_context.label, judgments=judgments)
    return AnalysisResponse(
        analysis_id=stable_trace_id(
            "an",
            [
                goal_context.id,
                goal_context.label,
                goal_context.llm_goal_id,
                screen.title,
                analysis_mode,
                response_parts.overall_risk,
                *(element.id for element in response_parts.elements),
            ],
        ),
        goal_id=goal_context.id,
        goal_label=goal_context.label,
        screen_title=screen.title,
        analysis_mode=analysis_mode,
        overall_risk=response_parts.overall_risk,
        alignment_score=response_parts.alignment_score,
        risk_counts=response_parts.risk_counts,
        summary=response_parts.summary,
        elements=response_parts.elements,
        recommended_action=response_parts.recommended_action,
        proof_card=response_parts.proof_card,
    )


def _ocr_goal_id(goal_id: str | None) -> str:
    if goal_id and goal_id.strip() in GOAL_LABELS:
        return normalize_goal_id(goal_id)
    return DEFAULT_GOAL_ID
