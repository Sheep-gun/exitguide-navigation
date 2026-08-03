from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Navigation DB redesign settings only.

    The models never receive database credentials. The API reads the validated
    decision-memory SQLite file and sends a bounded evidence packet to the
    configured Solar Pro 4 planner and EXAONE 4.5 vision endpoints.
    """

    navigation_decision_db_path: str = ""
    navigation_runtime_db_path: str = ".artifacts/navigation-runtime-v1.sqlite"
    navigation_dataset_split_manifest_path: str = ""
    navigation_allow_locked_holdout: bool = False
    navigation_planner_timeout_seconds: float = 30.0
    navigation_model_allow_fallback: bool = True
    navigation_verifier_max_clicks: int = 12
    navigation_reflection_confidence_threshold: float = 0.45
    navigation_reflection_margin_threshold: float = 0.08
    navigation_planner_mode: str = "selective"
    navigation_planner_score_threshold: float = 0.90
    navigation_planner_margin_threshold: float = 0.25
    navigation_vlm_mode: str = "selective"

    navigation_planner_provider: str = "solar_pro4"
    navigation_planner_api_key: str = ""
    navigation_planner_base_url: str = "https://api.upstage.ai/v1"
    navigation_planner_model: str = "solar-pro4"
    navigation_planner_fallback_enabled: bool = True
    navigation_planner_fallback_provider: str = "solar_pro3"
    navigation_planner_fallback_model: str = "solar-pro3"

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
