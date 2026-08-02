from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ocr_provider: str = "mock"
    llm_provider: str = "mock"
    navigation_agent_provider: str = "mock"
    # Production navigation is model-owned. If K-EXAONE cannot return a valid
    # Hermes action, fail closed instead of silently issuing a heuristic click.
    navigation_agent_allow_fallback: bool = False
    navigation_agent_timeout_seconds: float = 10.0
    navigation_graph_db_path: str = ""
    navigation_function_db_path: str = ""
    navigation_function_catalog_path: str = ""
    navigation_exploration_timeout_seconds: int = 55
    navigation_exploration_max_actions: int = 16
    navigation_exploration_max_depth: int = 9
    android_control_index_path: str = ".artifacts/android-control/navigation-examples.sqlite"
    android_control_retrieval_top_k: int = 5
    navigation_gold_retrieval_enabled: bool = True
    navigation_gold_retrieval_top_k: int = 5
    navigation_policy_reranker_path: str = ""
    navigation_policy_reranker_max_candidates: int = 5
    navigation_policy_reranker_decisive_score: float = 0.62
    navigation_policy_reranker_decisive_margin: float = 0.07
    navigation_agent_min_confidence: float = 0.55
    navigation_agent_min_candidate_margin: float = 0.07
    navigation_verified_route_replay_enabled: bool = False
    navigation_vlm_enabled: bool = True
    navigation_vlm_base_url: str = "http://127.0.0.1:8000/v1"
    navigation_vlm_model: str = "EXAONE-4.5-33B"
    navigation_vlm_timeout_seconds: float = 20.0
    navigation_vlm_cache_path: str = ".artifacts/navigation-vlm/cache.sqlite"
    max_upload_bytes: int = 8_000_000
    allowed_image_content_types: str = "image/jpeg,image/png,image/webp"
    naver_clova_ocr_url: str = ""
    naver_clova_ocr_secret: str = ""
    hyperclova_api_key: str = ""
    hyperclova_model: str = ""
    google_api_key: str = ""
    google_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model: str = "gemini-3-flash-preview"
    upstage_api_key: str = ""
    upstage_model: str = "solar-pro"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4.1-mini"
    exaone_api_key: str = ""
    exaone_base_url: str = "https://api.friendli.ai/serverless/v1"
    exaone_model: str = "LGAI-EXAONE/K-EXAONE-236B-A23B"
    exaone_team: str = ""
    ai_provider_timeout_seconds: float = 30.0
    exaone_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
