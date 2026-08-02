from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Navigation DB redesign settings only.

    The models never receive database credentials. The API reads the validated
    decision-memory SQLite file and sends a bounded evidence packet to the
    configured K-EXAONE and EXAONE 4.5 endpoints.
    """

    navigation_decision_db_path: str = ""
    navigation_runtime_db_path: str = ".artifacts/navigation-runtime-v1.sqlite"
    navigation_planner_timeout_seconds: float = 30.0
    navigation_model_allow_fallback: bool = True
    navigation_verifier_max_clicks: int = 12
    navigation_verifier_workers: int = 4
    navigation_reflection_confidence_threshold: float = 0.45
    navigation_reflection_margin_threshold: float = 0.08

    exaone_api_key: str = ""
    exaone_base_url: str = "https://api.friendli.ai/serverless/v1"
    exaone_model: str = "LGAI-EXAONE/K-EXAONE-236B-A23B"
    exaone_team: str = ""

    exaone_vlm_api_key: str = ""
    exaone_vlm_base_url: str = ""
    exaone_vlm_model: str = "LGAI-EXAONE/EXAONE-4.5-33B"
    exaone_vlm_team: str = ""
    exaone_vlm_timeout_seconds: float = 45.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
