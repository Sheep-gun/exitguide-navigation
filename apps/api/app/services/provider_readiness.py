from app.config import Settings


def provider_readiness(settings: Settings) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ocr_ready = _ocr_ready(settings, notes)
    llm_ready = _llm_ready(settings, notes)
    return ocr_ready and llm_ready, notes


def _ocr_ready(settings: Settings, notes: list[str]) -> bool:
    if settings.ocr_provider == "mock":
        notes.append("Mock OCR이 결정적 데모용으로 활성화되어 있습니다.")
        return True

    if settings.ocr_provider == "naver_clova_ocr":
        missing = _missing_env_vars(
            [
                ("NAVER_CLOVA_OCR_URL", settings.naver_clova_ocr_url),
                ("NAVER_CLOVA_OCR_SECRET", settings.naver_clova_ocr_secret),
            ]
        )
        if missing:
            notes.append(f"NAVER CLOVA OCR 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("NAVER CLOVA OCR 자격 정보는 있으나 HTTP 클라이언트 연결은 아직 대기 중입니다.")
        return False

    if settings.ocr_provider == "gemini_vision":
        missing = _missing_env_vars(
            [
                ("GOOGLE_API_KEY", settings.google_api_key),
                ("GEMINI_MODEL", settings.gemini_model),
            ]
        )
        if missing:
            notes.append(f"Gemini vision OCR 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("Gemini vision OCR 원격 정보가 준비되어 있습니다.")
        return True

    if settings.ocr_provider == "openai_vision":
        missing = _missing_env_vars(
            [
                ("OPENAI_API_KEY", settings.openai_api_key),
                ("OPENAI_MODEL", settings.openai_model),
            ]
        )
        if missing:
            notes.append(f"OpenAI vision OCR 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("OpenAI vision OCR 원격 정보가 준비되어 있습니다.")
        return True

    if settings.ocr_provider == "exaone_vision":
        missing = _missing_env_vars(
            [
                ("EXAONE_API_KEY", settings.exaone_api_key),
                ("EXAONE_MODEL", settings.exaone_model),
            ]
        )
        if missing:
            notes.append(f"EXAONE vision OCR 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("EXAONE vision OCR 자격 정보가 준비되어 있습니다.")
        return True

    notes.append(f"OCR provider '{settings.ocr_provider}'는 아직 지원되지 않습니다.")
    return False


def _llm_ready(settings: Settings, notes: list[str]) -> bool:
    if settings.llm_provider == "mock":
        notes.append("Mock LLM 판정이 통제된 데모용으로 활성화되어 있습니다.")
        return True

    if settings.llm_provider == "hyperclova":
        missing = _missing_env_vars(
            [
                ("HYPERCLOVA_API_KEY", settings.hyperclova_api_key),
                ("HYPERCLOVA_MODEL", settings.hyperclova_model),
            ]
        )
        if missing:
            notes.append(f"HyperCLOVA 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("HyperCLOVA 자격 정보는 있으나 HTTP 클라이언트 연결은 아직 대기 중입니다.")
        return False

    if settings.llm_provider == "upstage":
        missing = _missing_env_vars(
            [
                ("UPSTAGE_API_KEY", settings.upstage_api_key),
                ("UPSTAGE_MODEL", settings.upstage_model),
            ]
        )
        if missing:
            notes.append(f"Upstage 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("Upstage 자격 정보는 있으나 HTTP 클라이언트 연결은 아직 대기 중입니다.")
        return False

    if settings.llm_provider == "gemini":
        missing = _missing_env_vars(
            [
                ("GOOGLE_API_KEY", settings.google_api_key),
                ("GEMINI_MODEL", settings.gemini_model),
            ]
        )
        if missing:
            notes.append(f"Gemini 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("Gemini LLM 원격 정보가 준비되어 있습니다.")
        return True

    if settings.llm_provider == "openai":
        missing = _missing_env_vars(
            [
                ("OPENAI_API_KEY", settings.openai_api_key),
                ("OPENAI_MODEL", settings.openai_model),
            ]
        )
        if missing:
            notes.append(f"OpenAI 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("OpenAI LLM 원격 정보가 준비되어 있습니다.")
        return True

    if settings.llm_provider == "exaone":
        missing = _missing_env_vars(
            [
                ("EXAONE_API_KEY", settings.exaone_api_key),
                ("EXAONE_MODEL", settings.exaone_model),
            ]
        )
        if missing:
            notes.append(f"EXAONE 환경 변수가 없습니다: {', '.join(missing)}.")
            return False
        notes.append("EXAONE LLM 자격 정보가 준비되어 있습니다.")
        return True

    notes.append(f"LLM provider '{settings.llm_provider}'는 아직 지원되지 않습니다.")
    return False


def _missing_env_vars(items: list[tuple[str, str]]) -> list[str]:
    return [name for name, value in items if not value]
