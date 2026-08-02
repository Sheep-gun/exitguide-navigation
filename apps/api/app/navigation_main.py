from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.navigation_contracts import DecideRequest, DecideResponse, ObserveRequest, ObserveResponse
from app.services.navigation_decision_memory import NavigationDecisionMemory
from app.services.navigation_model_clients import (
    Exaone45VisionClient,
    KExaoneResearchClient,
    OpenAICompatibleChatClient,
)
from app.services.navigation_research_policy import AndroidWorldResearchPolicy
from app.services.navigation_runtime import NavigationRuntime
from app.services.navigation_runtime_store import NavigationRuntimeStore


app = FastAPI(
    title="ExitGuide Navigation Decision API",
    version="0.1.0",
    description=(
        "Navigation-only API. It reads the decision-memory DB and writes unverified "
        "runtime observations to a separate promotion-gated SQLite database."
    ),
)


def _configured_paths() -> tuple[Path | None, Path]:
    settings = get_settings()
    decision_path = (
        Path(settings.navigation_decision_db_path).expanduser().resolve()
        if settings.navigation_decision_db_path
        else None
    )
    runtime_path = Path(settings.navigation_runtime_db_path).expanduser().resolve()
    return decision_path, runtime_path


@lru_cache(maxsize=1)
def get_navigation_runtime() -> NavigationRuntime:
    settings = get_settings()
    decision_path, runtime_path = _configured_paths()
    if decision_path is None:
        raise RuntimeError("NAVIGATION_DECISION_DB_PATH is not configured")
    memory = NavigationDecisionMemory(decision_path, read_only=True)
    store = NavigationRuntimeStore(runtime_path)
    policy = AndroidWorldResearchPolicy(
        k_exaone=KExaoneResearchClient(
            OpenAICompatibleChatClient(
                api_key=settings.exaone_api_key,
                base_url=settings.exaone_base_url,
                model=settings.exaone_model,
                team=settings.exaone_team,
                timeout_seconds=settings.navigation_planner_timeout_seconds,
            )
        ),
        exaone_vlm=Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key=settings.exaone_vlm_api_key,
                base_url=settings.exaone_vlm_base_url,
                model=settings.exaone_vlm_model,
                team=settings.exaone_vlm_team,
                timeout_seconds=settings.exaone_vlm_timeout_seconds,
            )
        ),
        allow_model_fallback=settings.navigation_model_allow_fallback,
        max_verified_clicks=settings.navigation_verifier_max_clicks,
        verifier_workers=settings.navigation_verifier_workers,
        reflection_confidence_threshold=settings.navigation_reflection_confidence_threshold,
        reflection_margin_threshold=settings.navigation_reflection_margin_threshold,
    )
    return NavigationRuntime(memory=memory, store=store, policy=policy)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": "exitguide-navigation"}


@app.get("/v1/navigation/status")
def navigation_status() -> dict[str, object]:
    decision_path, _ = _configured_paths()
    if decision_path is None or not decision_path.is_file():
        return {
            "ready": False,
            "reason": "navigation_decision_db_not_configured_or_missing",
        }
    try:
        return get_navigation_runtime().status()
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        return {"ready": False, "reason": str(error)}


@app.post("/v1/navigation/decide", response_model=DecideResponse)
def navigation_decide(request: DecideRequest) -> DecideResponse:
    try:
        return get_navigation_runtime().decide(request)
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="duplicate or invalid navigation decision") from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/v1/navigation/observe", response_model=ObserveResponse)
def navigation_observe(request: ObserveRequest) -> ObserveResponse:
    try:
        return get_navigation_runtime().observe(request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="navigation decision was not found") from error
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="observation already recorded or invalid") from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
