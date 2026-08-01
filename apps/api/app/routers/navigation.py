from fastapi import APIRouter, HTTPException, Query

from app.schemas import (
    NavigationGoldRecordingCompleteRequest,
    NavigationGoldRecordingResponse,
    NavigationGoldRecordingReviewRequest,
    NavigationFunctionCatalogResponse,
    NavigationGuideRequest,
    NavigationGuideResponse,
    NavigationRouteCatalog,
    UniversalNavigationGraphResponse,
    UniversalNavigationCompletionTiming,
    UniversalNavigationObserveRequest,
    UniversalNavigationObserveResponse,
)
from app.services.navigation import guide_navigation, load_navigation_route_catalog
from app.services.universal_navigation_agent import observe_universal_navigation
from app.services.navigation_function_catalog import get_navigation_function_catalog
from app.services.universal_navigation_graph import get_universal_navigation_repository


router = APIRouter(tags=["navigation"])


@router.get("/v1/navigation/routes", response_model=NavigationRouteCatalog)
def navigation_routes() -> NavigationRouteCatalog:
    return load_navigation_route_catalog()


@router.post("/v1/navigation/guide", response_model=NavigationGuideResponse)
def navigation_guide(request: NavigationGuideRequest) -> NavigationGuideResponse:
    return guide_navigation(request)


@router.post("/v1/navigation/agent/observe", response_model=UniversalNavigationObserveResponse)
def universal_navigation_observe(request: UniversalNavigationObserveRequest) -> UniversalNavigationObserveResponse:
    return observe_universal_navigation(request)


@router.get(
    "/v1/navigation/gold/recordings/{recording_id}",
    response_model=NavigationGoldRecordingResponse,
)
def navigation_gold_recording(recording_id: str) -> NavigationGoldRecordingResponse:
    repository = get_universal_navigation_repository()
    try:
        return NavigationGoldRecordingResponse(**repository.gold_recording(recording_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Gold recording was not found.") from error


@router.post(
    "/v1/navigation/gold/recordings/{recording_id}/complete",
    response_model=NavigationGoldRecordingResponse,
)
def navigation_gold_recording_complete(
    recording_id: str,
    request: NavigationGoldRecordingCompleteRequest,
) -> NavigationGoldRecordingResponse:
    repository = get_universal_navigation_repository()
    try:
        result = repository.complete_gold_recording(
            recording_id,
            destination_correct=request.destination_correct,
            safe_stop=request.safe_stop,
            reviewer=request.reviewer,
            notes=request.notes,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Gold recording was not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return NavigationGoldRecordingResponse(**result)


@router.post(
    "/v1/navigation/gold/recordings/{recording_id}/review",
    response_model=NavigationGoldRecordingResponse,
)
def navigation_gold_recording_review(
    recording_id: str,
    request: NavigationGoldRecordingReviewRequest,
) -> NavigationGoldRecordingResponse:
    repository = get_universal_navigation_repository()
    try:
        result = repository.review_gold_recording(
            recording_id,
            decision=request.decision,
            reviewer=request.reviewer,
            notes=request.notes,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Gold recording was not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return NavigationGoldRecordingResponse(**result)


@router.post(
    "/v1/navigation/gold/recordings/{recording_id}/cancel",
    response_model=NavigationGoldRecordingResponse,
)
def navigation_gold_recording_cancel(recording_id: str) -> NavigationGoldRecordingResponse:
    repository = get_universal_navigation_repository()
    try:
        return NavigationGoldRecordingResponse(**repository.cancel_gold_recording(recording_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Gold recording was not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/v1/navigation/agent/graph", response_model=UniversalNavigationGraphResponse)
def universal_navigation_graph(
    app_package: str = Query(min_length=1, max_length=240),
) -> UniversalNavigationGraphResponse:
    return get_universal_navigation_repository().snapshot(app_package)


@router.get("/v1/navigation/agent/performance")
def universal_navigation_performance(measurement_source: str = "real_device") -> dict[str, object]:
    allowed = {"server_runtime", "synthetic", "real_device", "real_device_gold"}
    if measurement_source not in allowed:
        measurement_source = "real_device"
    repository = get_universal_navigation_repository()
    return {
        "measurement_source": measurement_source,
        "metrics": repository.performance.summary(measurement_source=measurement_source),
        "real_device_baseline": measurement_source in {"real_device", "real_device_gold"},
    }


@router.post("/v1/navigation/agent/performance/complete")
def universal_navigation_performance_complete(
    request: UniversalNavigationCompletionTiming,
) -> dict[str, object]:
    repository = get_universal_navigation_repository()
    try:
        session = repository.performance.record_client_completion(
            session_id=request.session_id,
            time_to_confirmed_destination_ms=request.time_to_confirmed_destination_ms,
            measurement_source="real_device",
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "status": "recorded",
        "session_id": request.session_id,
        "measurement_source": "real_device",
        "time_to_confirmed_destination_ms": session["time_to_destination_ms"],
    }


@router.get("/v1/navigation/functions", response_model=NavigationFunctionCatalogResponse)
def navigation_functions(query: str = "", limit: int = 50) -> NavigationFunctionCatalogResponse:
    catalog = get_navigation_function_catalog()
    return NavigationFunctionCatalogResponse(
        **catalog.stats(),
        functions=catalog.search(query, limit=max(1, min(limit, 100))),
    )
