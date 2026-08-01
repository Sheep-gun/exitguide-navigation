from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.http_errors import SERVICE_EXCEPTIONS, to_http_exception
from app.schemas import (
    AnalysisResponse,
    DemoAnalysisRequest,
    FlowAnalysisRequest,
    FlowAnalysisResponse,
    PromptPreviewRequest,
    PromptPreviewResponse,
)
from app.services.analysis import analyze_screenshot
from app.services.flow import analyze_demo_flow, analyze_uploaded_flow
from app.services.prompt_preview import build_demo_prompt_preview
from app.services.provider_runtime import RuntimeProviderOptions
from app.services.scenarios import get_demo_scenario
from app.services.uploads import validate_uploaded_screenshot

router = APIRouter(tags=["analysis"])


@router.post("/v1/prompt/demo", response_model=PromptPreviewResponse)
def prompt_demo(request: PromptPreviewRequest) -> PromptPreviewResponse:
    try:
        return build_demo_prompt_preview(
            goal_id=request.goal_id,
            scenario_id=request.scenario_id,
            goal_text=request.goal_text,
            infer_goal=request.infer_goal,
        )
    except SERVICE_EXCEPTIONS as exc:
        raise to_http_exception(exc) from exc


@router.post("/v1/analyze", response_model=AnalysisResponse)
async def analyze(
    provider_id: str | None = Form(None),
    provider_api_key: str | None = Form(None),
    provider_model: str | None = Form(None),
    provider_base_url: str | None = Form(None),
    goal_id: str | None = Form(None),
    goal_text: str | None = Form(None),
    infer_goal: bool = Form(False),
    screenshot: UploadFile = File(...),
) -> AnalysisResponse:
    settings = get_settings()
    image_bytes = await screenshot.read()
    try:
        validate_uploaded_screenshot(
            image_bytes=image_bytes,
            content_type=screenshot.content_type,
            max_upload_bytes=settings.max_upload_bytes,
            allowed_content_types=settings.allowed_image_content_types,
        )
        return analyze_screenshot(
            goal_id=goal_id,
            image_bytes=image_bytes,
            filename=screenshot.filename,
            analysis_mode="upload",
            goal_text=goal_text,
            infer_goal=infer_goal,
            provider_options=_provider_options_from_values(
                provider_id=provider_id,
                provider_api_key=provider_api_key,
                provider_model=provider_model,
                provider_base_url=provider_base_url,
            ),
        )
    except SERVICE_EXCEPTIONS as exc:
        raise to_http_exception(exc) from exc


@router.post("/v1/analyze/demo", response_model=AnalysisResponse)
def analyze_demo(request: DemoAnalysisRequest) -> AnalysisResponse:
    try:
        scenario = get_demo_scenario(request.scenario_id)
        return analyze_screenshot(
            goal_id=request.goal_id,
            image_bytes=b"demo scenario",
            filename=scenario.fixture_filename,
            analysis_mode="demo",
            goal_text=request.goal_text,
            infer_goal=request.infer_goal,
            provider_options=_provider_options_from_request(request),
        )
    except SERVICE_EXCEPTIONS as exc:
        raise to_http_exception(exc) from exc


@router.post("/v1/analyze/flow", response_model=FlowAnalysisResponse)
def analyze_flow(request: FlowAnalysisRequest) -> FlowAnalysisResponse:
    try:
        return analyze_demo_flow(
            goal_id=request.goal_id,
            scenario_ids=request.scenario_ids,
            goal_text=request.goal_text,
            infer_goal=request.infer_goal,
            provider_options=_provider_options_from_request(request),
        )
    except SERVICE_EXCEPTIONS as exc:
        raise to_http_exception(exc) from exc


@router.post("/v1/analyze/flow/upload", response_model=FlowAnalysisResponse)
async def analyze_upload_flow(
    provider_id: str | None = Form(None),
    provider_api_key: str | None = Form(None),
    provider_model: str | None = Form(None),
    provider_base_url: str | None = Form(None),
    goal_id: str | None = Form(None),
    goal_text: str | None = Form(None),
    infer_goal: bool = Form(False),
    screenshots: list[UploadFile] = File(...),
) -> FlowAnalysisResponse:
    settings = get_settings()

    if not 2 <= len(screenshots) <= 6:
        raise HTTPException(status_code=400, detail="Upload between 2 and 6 screenshots for a flow.")

    try:
        uploads: list[tuple[bytes, str | None]] = []
        for screenshot in screenshots:
            image_bytes = await screenshot.read()
            validate_uploaded_screenshot(
                image_bytes=image_bytes,
                content_type=screenshot.content_type,
                max_upload_bytes=settings.max_upload_bytes,
                allowed_content_types=settings.allowed_image_content_types,
            )
            uploads.append((image_bytes, screenshot.filename))

        return analyze_uploaded_flow(
            goal_id=goal_id,
            uploads=uploads,
            goal_text=goal_text,
            infer_goal=infer_goal,
            provider_options=_provider_options_from_values(
                provider_id=provider_id,
                provider_api_key=provider_api_key,
                provider_model=provider_model,
                provider_base_url=provider_base_url,
            ),
        )
    except SERVICE_EXCEPTIONS as exc:
        raise to_http_exception(exc) from exc


def _provider_options_from_request(request: DemoAnalysisRequest | FlowAnalysisRequest | PromptPreviewRequest) -> RuntimeProviderOptions:
    return _provider_options_from_values(
        provider_id=request.provider_id,
        provider_api_key=request.provider_api_key,
        provider_model=request.provider_model,
        provider_base_url=request.provider_base_url,
    )


def _provider_options_from_values(
    provider_id: str | None,
    provider_api_key: str | None,
    provider_model: str | None,
    provider_base_url: str | None,
) -> RuntimeProviderOptions:
    return RuntimeProviderOptions(
        provider_id=provider_id,
        api_key=provider_api_key,
        model=provider_model,
        base_url=provider_base_url,
    )
