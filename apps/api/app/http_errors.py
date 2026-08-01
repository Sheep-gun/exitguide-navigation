import logging

from fastapi import HTTPException

from app.services.errors import ProviderUnavailableError
from app.services.goals import UnsupportedGoalError
from app.services.model_output import ModelOutputError
from app.services.uploads import UploadValidationError


SERVICE_EXCEPTIONS = (
    UnsupportedGoalError,
    UploadValidationError,
    ProviderUnavailableError,
    ModelOutputError,
    ValueError,
)

logger = logging.getLogger("exitguide.api")


def to_http_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, (UnsupportedGoalError, UploadValidationError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ProviderUnavailableError):
        logger.error("Provider unavailable: %s", exc)
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, ModelOutputError):
        logger.error("Model output error: %s", exc)
        return HTTPException(status_code=502, detail=str(exc))

    return HTTPException(status_code=500, detail="Unexpected API error.")
