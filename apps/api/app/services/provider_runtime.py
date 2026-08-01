from dataclasses import dataclass

from app.config import Settings


SUPPORTED_RUNTIME_PROVIDERS = ("server", "google", "gpt", "exaone")
GEMINI_PREVIEW_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


@dataclass(frozen=True)
class RuntimeProviderOptions:
    provider_id: str | None = None
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None


@dataclass(frozen=True)
class RuntimeProvider:
    settings: Settings
    ocr_provider: str
    llm_provider: str
    provider_id: str


def resolve_runtime_provider(settings: Settings, options: RuntimeProviderOptions | None = None) -> RuntimeProvider:
    options = options or RuntimeProviderOptions()
    provider_id = (options.provider_id or "server").strip().lower()
    # Internal-only deterministic path for readiness/quality calibration. The
    # public request schemas do not expose "mock" as a selectable provider.
    if provider_id == "mock":
        return RuntimeProvider(
            settings=settings.model_copy(update={"ocr_provider": "mock", "llm_provider": "mock"}),
            ocr_provider="mock",
            llm_provider="mock",
            provider_id="mock",
        )
    if provider_id in {"", "server"}:
        return RuntimeProvider(
            settings=settings,
            ocr_provider=settings.ocr_provider,
            llm_provider=settings.llm_provider,
            provider_id="server",
        )

    if provider_id == "google":
        gemini_model = (options.model or settings.gemini_model).strip()
        return RuntimeProvider(
            settings=settings.model_copy(
                update={
                    "google_api_key": options.api_key or settings.google_api_key,
                    "gemini_model": gemini_model,
                    "google_base_url": normalize_google_base_url(
                        model=gemini_model,
                        base_url=options.base_url or settings.google_base_url,
                    ),
                }
            ),
            ocr_provider="gemini_vision",
            llm_provider="gemini",
            provider_id="google",
        )

    if provider_id == "gpt":
        return RuntimeProvider(
            settings=settings.model_copy(
                update={
                    "openai_api_key": options.api_key or settings.openai_api_key,
                    "openai_model": options.model or settings.openai_model,
                    "openai_base_url": options.base_url or settings.openai_base_url,
                }
            ),
            ocr_provider="openai_vision",
            llm_provider="openai",
            provider_id="gpt",
        )

    if provider_id == "exaone":
        return RuntimeProvider(
            settings=settings.model_copy(
                update={
                    "exaone_api_key": options.api_key or settings.exaone_api_key,
                    "exaone_model": options.model or settings.exaone_model,
                    "exaone_base_url": options.base_url or settings.exaone_base_url,
                }
            ),
            ocr_provider="exaone_vision",
            llm_provider="exaone",
            provider_id="exaone",
        )

    raise ValueError(f"Unsupported AI provider: {provider_id}")


def normalize_google_base_url(model: str, base_url: str) -> str:
    normalized = (base_url or GEMINI_PREVIEW_BASE_URL).strip().rstrip("/")
    if not normalized:
        return GEMINI_PREVIEW_BASE_URL
    if _requires_gemini_beta_api(model) and normalized.endswith("/v1"):
        return f"{normalized.removesuffix('/v1')}/v1beta"
    return normalized


def _requires_gemini_beta_api(model: str) -> bool:
    normalized = model.strip().lower()
    return normalized.startswith("gemini-3-") or "preview" in normalized


def provider_defaults(settings: Settings) -> list[dict[str, str | bool]]:
    return [
        {
            "id": "server",
            "label": "서버 기본값",
            "model": "",
            "base_url": "",
            "ready": True,
        },
        {
            "id": "google",
            "label": "Google Gemini",
            "model": settings.gemini_model,
            "base_url": settings.google_base_url,
            "ready": bool(settings.google_api_key),
        },
        {
            "id": "gpt",
            "label": "OpenAI GPT",
            "model": settings.openai_model,
            "base_url": settings.openai_base_url,
            "ready": bool(settings.openai_api_key),
        },
        {
            "id": "exaone",
            "label": "EXAONE",
            "model": settings.exaone_model,
            "base_url": settings.exaone_base_url,
            "ready": bool(settings.exaone_api_key),
        },
    ]
