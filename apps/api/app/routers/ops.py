from fastapi import APIRouter

from app.config import get_settings
from app.schemas import ApiProviderOption, ApiStatus, DemoQualityResponse, DemoReadinessResponse
from app.services.demo_quality import build_demo_quality
from app.services.provider_readiness import provider_readiness
from app.services.provider_runtime import SUPPORTED_RUNTIME_PROVIDERS, provider_defaults
from app.services.readiness import build_demo_readiness

router = APIRouter(tags=["ops"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/v1/status", response_model=ApiStatus)
def status() -> ApiStatus:
    settings = get_settings()
    ready, notes = provider_readiness(settings)
    return ApiStatus(
        status="ok",
        ocr_provider=settings.ocr_provider,
        llm_provider=settings.llm_provider,
        provider_ready=ready,
        provider_notes=notes,
        supported_ai_providers=list(SUPPORTED_RUNTIME_PROVIDERS),
    )


@router.get("/v1/providers", response_model=list[ApiProviderOption])
def providers() -> list[ApiProviderOption]:
    return [ApiProviderOption(**item) for item in provider_defaults(get_settings())]


@router.get("/v1/readiness", response_model=DemoReadinessResponse)
def readiness() -> DemoReadinessResponse:
    return build_demo_readiness(get_settings())


@router.get("/v1/demo-quality", response_model=DemoQualityResponse)
def demo_quality() -> DemoQualityResponse:
    return build_demo_quality(get_settings())
