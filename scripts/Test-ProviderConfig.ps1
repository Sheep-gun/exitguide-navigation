$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "apps/api/.venv/Scripts/python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
  throw "API virtual environment was not found. Run .\scripts\Bootstrap-Windows.ps1 first."
}

$Script = @'
from pathlib import Path
import sys

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root / "apps" / "api"))

from app.config import Settings
from app.services.provider_readiness import provider_readiness

env_text = (repo_root / ".env.example").read_text(encoding="utf-8")
providers_text = (repo_root / "docs" / "PROVIDERS.md").read_text(encoding="utf-8")

required_env_vars = [
    "MAX_UPLOAD_BYTES",
    "ALLOWED_IMAGE_CONTENT_TYPES",
    "OCR_PROVIDER",
    "NAVER_CLOVA_OCR_URL",
    "NAVER_CLOVA_OCR_SECRET",
    "LLM_PROVIDER",
    "HYPERCLOVA_API_KEY",
    "HYPERCLOVA_MODEL",
    "GOOGLE_API_KEY",
    "GOOGLE_BASE_URL",
    "GEMINI_MODEL",
    "UPSTAGE_API_KEY",
    "UPSTAGE_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "EXAONE_API_KEY",
    "EXAONE_BASE_URL",
    "EXAONE_MODEL",
    "EXAONE_TEAM",
    "AI_PROVIDER_TIMEOUT_SECONDS",
    "EXAONE_TIMEOUT_SECONDS",
]

failures: list[str] = []
for env_var in required_env_vars:
    if f"{env_var}=" not in env_text:
        failures.append(f".env.example is missing {env_var}")

for token in ["mock", "naver_clova_ocr", "gemini_vision", "gemini", "openai_vision", "openai", "hyperclova", "upstage", "exaone_vision", "exaone", "provider_ready", "provider_notes"]:
    if token not in providers_text:
        failures.append(f"docs/PROVIDERS.md is missing {token}")

provider_cases = [
    (
        Settings(ocr_provider="naver_clova_ocr", llm_provider="mock", naver_clova_ocr_url="", naver_clova_ocr_secret=""),
        ["NAVER_CLOVA_OCR_URL", "NAVER_CLOVA_OCR_SECRET"],
    ),
    (
        Settings(ocr_provider="mock", llm_provider="hyperclova", hyperclova_api_key="", hyperclova_model=""),
        ["HYPERCLOVA_API_KEY", "HYPERCLOVA_MODEL"],
    ),
    (
        Settings(ocr_provider="gemini_vision", llm_provider="mock", google_api_key="", gemini_model="gemini-3-flash-preview"),
        ["GOOGLE_API_KEY"],
    ),
    (
        Settings(ocr_provider="openai_vision", llm_provider="mock", openai_api_key="", openai_model="gpt-4.1-mini"),
        ["OPENAI_API_KEY"],
    ),
    (
        Settings(ocr_provider="mock", llm_provider="upstage", upstage_api_key="", upstage_model="solar-pro"),
        ["UPSTAGE_API_KEY"],
    ),
    (
        Settings(ocr_provider="mock", llm_provider="gemini", google_api_key="", gemini_model="gemini-3-flash-preview"),
        ["GOOGLE_API_KEY"],
    ),
    (
        Settings(ocr_provider="mock", llm_provider="openai", openai_api_key="", openai_model="gpt-4.1-mini"),
        ["OPENAI_API_KEY"],
    ),
    (
        Settings(ocr_provider="exaone_vision", llm_provider="mock", exaone_api_key="", exaone_model=""),
        ["EXAONE_API_KEY", "EXAONE_MODEL"],
    ),
    (
        Settings(ocr_provider="mock", llm_provider="exaone", exaone_api_key="", exaone_model=""),
        ["EXAONE_API_KEY", "EXAONE_MODEL"],
    ),
]

for settings, expected_missing in provider_cases:
    ready, notes = provider_readiness(settings)
    rendered_notes = " ".join(notes)
    if ready:
        failures.append(f"{settings.ocr_provider}/{settings.llm_provider} should not be ready without client wiring")
    for env_var in expected_missing:
        if env_var not in rendered_notes:
            failures.append(f"provider readiness notes should mention {env_var}")

if failures:
    raise SystemExit("\n".join(failures))

print("Provider config checks passed.")
'@

$Script | & $Python - $RepoRoot
if ($LASTEXITCODE -ne 0) {
  throw "Provider config checks failed with exit code $LASTEXITCODE"
}
