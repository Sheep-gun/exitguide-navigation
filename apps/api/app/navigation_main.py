from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.navigation_contracts import DecideRequest, DecideResponse, ObserveRequest, ObserveResponse
from app.services.navigation_decision_memory import NavigationDecisionMemory
from app.services.navigation_dataset_split import (
    DatasetSplitAccessError,
    NavigationDatasetSplitManifest,
)
from app.services.navigation_model_clients import (
    Exaone45VisionClient,
    FallbackNavigationPlannerResearchClient,
    NavigationPlannerResearchClient,
    OpenAICompatibleChatClient,
)
from app.services.navigation_public_prior import NavigationPublicPrior
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
    public_prior = None
    if settings.navigation_public_prior_enabled:
        if not settings.navigation_public_prior_db_path:
            raise RuntimeError(
                "NAVIGATION_PUBLIC_PRIOR_DB_PATH is required when public prior is enabled"
            )
        public_prior = NavigationPublicPrior(
            settings.navigation_public_prior_db_path,
            failure_db_path=settings.navigation_public_failure_db_path or None,
            task_db_path=settings.navigation_public_task_db_path or None,
            max_results=settings.navigation_public_prior_max_results,
        )
    dataset_split_manifest = (
        NavigationDatasetSplitManifest.load(settings.navigation_dataset_split_manifest_path)
        if settings.navigation_dataset_split_manifest_path
        else None
    )
    policy = AndroidWorldResearchPolicy(
        planner_model=FallbackNavigationPlannerResearchClient(
            primary=NavigationPlannerResearchClient(
                OpenAICompatibleChatClient(
                    api_key=settings.navigation_planner_api_key,
                    base_url=settings.navigation_planner_base_url,
                    model=settings.navigation_planner_model,
                    timeout_seconds=settings.navigation_planner_timeout_seconds,
                ),
                provider_name=settings.navigation_planner_provider,
            ),
            fallback=(
                NavigationPlannerResearchClient(
                    OpenAICompatibleChatClient(
                        api_key=settings.navigation_planner_api_key,
                        base_url=settings.navigation_planner_base_url,
                        model=settings.navigation_planner_fallback_model,
                        timeout_seconds=settings.navigation_planner_timeout_seconds,
                    ),
                    provider_name=settings.navigation_planner_fallback_provider,
                )
                if settings.navigation_planner_fallback_enabled
                else None
            ),
        ),
        exaone_vlm=Exaone45VisionClient(
            OpenAICompatibleChatClient(
                api_key=settings.exaone_vlm_api_key,
                base_url=settings.exaone_vlm_base_url,
                model=settings.exaone_vlm_model,
                team=settings.exaone_vlm_team,
                timeout_seconds=settings.exaone_vlm_timeout_seconds,
                chat_template_kwargs={"enable_thinking": False},
            )
        ),
        allow_model_fallback=settings.navigation_model_allow_fallback,
        max_verified_clicks=settings.navigation_verifier_max_clicks,
        reflection_confidence_threshold=settings.navigation_reflection_confidence_threshold,
        reflection_margin_threshold=settings.navigation_reflection_margin_threshold,
        planner_mode=settings.navigation_planner_mode,
        planner_score_threshold=settings.navigation_planner_score_threshold,
        planner_margin_threshold=settings.navigation_planner_margin_threshold,
        vlm_mode=settings.navigation_vlm_mode,
    )
    return NavigationRuntime(
        memory=memory,
        store=store,
        policy=policy,
        public_prior=public_prior,
        dataset_split_manifest=dataset_split_manifest,
        allow_locked_holdout=settings.navigation_allow_locked_holdout,
    )


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
        runtime = get_navigation_runtime()
        cached = runtime.store.cached_api_response("decide", request.request_id)
        if cached is not None:
            return DecideResponse.model_validate(cached)
        response = runtime.decide(request)
        runtime.store.cache_api_response(
            "decide", request.request_id, response.model_dump(mode="json")
        )
        return response
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="duplicate or invalid navigation decision") from error
    except DatasetSplitAccessError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/v1/navigation/observe", response_model=ObserveResponse)
def navigation_observe(request: ObserveRequest) -> ObserveResponse:
    try:
        runtime = get_navigation_runtime()
        cached = runtime.store.cached_api_response("observe", request.request_id)
        if cached is not None:
            return ObserveResponse.model_validate(cached)
        response = runtime.observe(request)
        runtime.store.cache_api_response(
            "observe", request.request_id, response.model_dump(mode="json")
        )
        return response
    except KeyError as error:
        raise HTTPException(status_code=404, detail="navigation decision was not found") from error
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="observation already recorded or invalid") from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/v1/navigation/sessions/{session_id}/episode")
def navigation_episode(session_id: str) -> dict[str, object]:
    """Inspect the complete candidate/action/outcome record for one session."""

    try:
        return get_navigation_runtime().store.interaction_episode(session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="navigation session was not found") from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.post("/v1/navigation/sessions/{session_id}/stop")
def navigation_stop_session(session_id: str) -> dict[str, object]:
    """Stop one executor session without treating cancellation as navigation failure."""

    try:
        session = get_navigation_runtime().stop_session(session_id)
        return {
            "session_id": session["session_id"],
            "status": session["status"],
        }
    except KeyError as error:
        raise HTTPException(status_code=404, detail="navigation session was not found") from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/v1/navigation/dataset-splits")
def navigation_dataset_splits() -> dict[str, object]:
    """Return the immutable runtime copy of the app-disjoint split manifest."""

    try:
        runtime = get_navigation_runtime()
        return {
            "policy": runtime.status()["dataset_split"],
            "entries": runtime.store.dataset_split_manifest(),
        }
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
