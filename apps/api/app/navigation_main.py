from __future__ import annotations

import sqlite3
import secrets
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse

from app.config import get_settings
from app.navigation_contracts import (
    ConfirmNavigationActionRequest,
    DecideRequest,
    DecideResponse,
    ObserveRequest,
    ObserveResponse,
    StopSessionRequest,
)
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
from app.services.navigation_agent_rules import NavigationAgentRuleStore
from app.services.navigation_extensions import ExtensionMode, NavigationExtensionRuntime
from app.services.navigation_public_prior import NavigationPublicPrior
from app.services.navigation_research_policy import AndroidWorldResearchPolicy
from app.services.navigation_runtime import NavigationRuntime
from app.services.navigation_runtime_store import NavigationRuntimeStore
from app.services.navigation_review import (
    NavigationHumanReviewRequest,
    NavigationReviewStore,
)


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
def get_navigation_review_store() -> NavigationReviewStore:
    settings = get_settings()
    _, runtime_path = _configured_paths()
    review_path = (
        Path(settings.navigation_review_db_path).expanduser().resolve()
        if settings.navigation_review_db_path
        else runtime_path.with_name("navigation-human-review-v1.sqlite")
    )
    return NavigationReviewStore(runtime_path, review_path)


@lru_cache(maxsize=1)
def get_navigation_runtime() -> NavigationRuntime:
    settings = get_settings()
    decision_path, runtime_path = _configured_paths()
    if decision_path is None:
        raise RuntimeError("NAVIGATION_DECISION_DB_PATH is not configured")
    memory = NavigationDecisionMemory(decision_path, read_only=True)
    store = NavigationRuntimeStore(
        runtime_path,
        server_release_id=settings.navigation_server_release_id,
        screen_artifact_dir=(
            settings.navigation_screen_artifact_dir or None
        ),
    )
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
    agent_rules = None
    if settings.navigation_codex_rule_retrieval_mode != "off":
        if not settings.navigation_agent_rule_index_path:
            raise RuntimeError(
                "NAVIGATION_AGENT_RULE_INDEX_PATH is required when Codex rule retrieval is enabled"
            )
        agent_rules = NavigationAgentRuleStore(
            settings.navigation_agent_rule_index_path,
            mode=settings.navigation_codex_rule_retrieval_mode,
        )
    policy = AndroidWorldResearchPolicy(
        planner_model=FallbackNavigationPlannerResearchClient(
            primary=NavigationPlannerResearchClient(
                OpenAICompatibleChatClient(
                    api_key=settings.navigation_planner_api_key,
                    base_url=settings.navigation_planner_base_url,
                    model=settings.navigation_planner_model,
                    timeout_seconds=settings.navigation_planner_timeout_seconds,
                    reasoning_effort=settings.navigation_planner_reasoning_effort,
                    telemetry_name=settings.navigation_planner_provider,
                ),
                provider_name=settings.navigation_planner_provider,
                step_evaluation_max_tokens=settings.navigation_planner_step_max_tokens,
            ),
            fallback=(
                NavigationPlannerResearchClient(
                    OpenAICompatibleChatClient(
                        api_key=settings.navigation_planner_api_key,
                        base_url=settings.navigation_planner_base_url,
                        model=settings.navigation_planner_fallback_model,
                        timeout_seconds=settings.navigation_planner_timeout_seconds,
                        reasoning_effort=settings.navigation_planner_reasoning_effort,
                        telemetry_name=settings.navigation_planner_fallback_provider,
                    ),
                    provider_name=settings.navigation_planner_fallback_provider,
                    step_evaluation_max_tokens=settings.navigation_planner_step_max_tokens,
                )
                if settings.navigation_planner_fallback_enabled
                else None
            ),
            failover_on_timeout=settings.navigation_planner_failover_on_timeout,
            failover_on_invalid_output=(
                settings.navigation_planner_failover_on_invalid_output
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
        planner_schema_retry_enabled=settings.navigation_planner_schema_retry_enabled,
        vlm_mode=settings.navigation_vlm_mode,
    )
    extension = None
    extension_mode = ExtensionMode(settings.navigation_extension_mode)
    if extension_mode != ExtensionMode.OFF:
        required_paths = {
            "NAVIGATION_PROCEDURE_CATALOG_PATH": settings.navigation_procedure_catalog_path,
            "NAVIGATION_SAFETY_POLICY_PATH": settings.navigation_safety_policy_path,
        }
        missing = [name for name, value in required_paths.items() if not value]
        if missing:
            raise RuntimeError("navigation extension paths are missing: " + ", ".join(missing))
        extension = NavigationExtensionRuntime.from_paths(
            mode=extension_mode,
            procedure_catalog_path=settings.navigation_procedure_catalog_path,
            policy_path=settings.navigation_safety_policy_path,
            extension_db_path=settings.navigation_extension_db_path,
        )
    return NavigationRuntime(
        memory=memory,
        store=store,
        policy=policy,
        public_prior=public_prior,
        dataset_split_manifest=dataset_split_manifest,
        allow_locked_holdout=settings.navigation_allow_locked_holdout,
        extension=extension,
        agent_rules=agent_rules,
        goal_fast_path_confidence=settings.navigation_goal_fast_path_confidence,
    )


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "service": "exitguide-navigation"}


@app.get("/review", include_in_schema=False)
@app.get("/review/", include_in_schema=False)
def navigation_review_page() -> FileResponse:
    page = Path(__file__).resolve().parent / "static" / "navigation_review" / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=503, detail="navigation review UI is not installed")
    return FileResponse(page)


@app.get("/v1/navigation/review/status")
def navigation_review_status(
    reviewer: str = Query(default="human", min_length=1, max_length=80),
) -> dict[str, object]:
    try:
        return get_navigation_review_store().status(reviewer=reviewer)
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/v1/navigation/review/queue")
def navigation_review_queue(
    reviewer: str = Query(default="human", min_length=1, max_length=80),
    queue: str = Query(default="priority"),
    review_status: str = Query(default="unreviewed"),
    query: str = Query(default="", max_length=200),
    limit: int = Query(default=80, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    try:
        return get_navigation_review_store().list_queue(
            reviewer=reviewer,
            queue=queue,
            review_status=review_status,
            query=query,
            limit=limit,
            offset=offset,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, RuntimeError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/v1/navigation/review/decisions/{decision_id}")
def navigation_review_detail(
    decision_id: str,
    reviewer: str = Query(default="human", min_length=1, max_length=80),
) -> dict[str, object]:
    try:
        return get_navigation_review_store().detail(decision_id, reviewer=reviewer)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="navigation decision was not found") from error
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.put("/v1/navigation/review/decisions/{decision_id}")
def navigation_save_review(
    decision_id: str,
    request: NavigationHumanReviewRequest,
) -> dict[str, object]:
    try:
        return get_navigation_review_store().save_review(decision_id, request)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="navigation decision was not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OSError, RuntimeError, sqlite3.Error) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


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


@app.post("/v1/navigation/confirmations/{confirmation_id}")
def navigation_confirm_action(
    confirmation_id: str,
    request: ConfirmNavigationActionRequest,
    confirmation_key: str = Header(default="", alias="X-ExitGuide-Confirmation-Key"),
) -> dict[str, object]:
    settings = get_settings()
    expected_key = settings.navigation_confirmation_api_key
    if not expected_key:
        raise HTTPException(status_code=503, detail="native confirmation is not configured")
    if not secrets.compare_digest(confirmation_key, expected_key):
        raise HTTPException(status_code=403, detail="invalid native confirmation credential")
    runtime = get_navigation_runtime()
    if runtime.extension is None:
        raise HTTPException(status_code=409, detail="navigation extension is disabled")
    try:
        runtime.extension.store.confirm_challenge(
            confirmation_id,
            source="native_ui",
            session_id=request.session_id,
            action=request.action.model_dump(mode="json", exclude_none=True),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="confirmation challenge was not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"confirmation_id": confirmation_id, "status": "confirmed"}


@app.get("/v1/navigation/extension/metrics")
def navigation_extension_metrics() -> dict[str, object]:
    runtime = get_navigation_runtime()
    if runtime.extension is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "mode": runtime.extension.mode.value,
        "store": runtime.extension.store.status(),
        "metrics": runtime.extension.store.summary(),
    }


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
def navigation_stop_session(
    session_id: str,
    request: StopSessionRequest | None = None,
) -> dict[str, object]:
    """Stop one executor session without treating cancellation as navigation failure."""

    try:
        payload = request or StopSessionRequest()
        session = get_navigation_runtime().stop_session(
            session_id,
            terminal_reason=payload.terminal_reason,
            handoff_reason=payload.handoff_reason,
        )
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
