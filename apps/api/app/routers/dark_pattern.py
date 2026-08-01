from fastapi import APIRouter

from app.schemas import DarkPatternInspectRequest, DarkPatternInspectResponse
from app.services.dark_pattern import inspect_dark_pattern


router = APIRouter(tags=["dark-pattern"])


@router.post("/v1/dark-pattern/inspect", response_model=DarkPatternInspectResponse)
def dark_pattern_inspect(request: DarkPatternInspectRequest) -> DarkPatternInspectResponse:
    return inspect_dark_pattern(request)
