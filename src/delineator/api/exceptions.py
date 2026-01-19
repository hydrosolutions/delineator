"""
Exception handling for the delineator API.

This module defines custom exceptions and exception handlers for the FastAPI
application. It maps various error conditions to structured JSON responses
with appropriate HTTP status codes and error codes.
"""

from enum import Enum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from delineator.api.models import ErrorResponse
from delineator.core.delineate import DelineationError


class APIErrorCode(str, Enum):
    """Error codes for API responses."""

    INVALID_COORDINATES = "INVALID_COORDINATES"
    NO_RIVER_FOUND = "NO_RIVER_FOUND"
    NO_DATA_AVAILABLE = "NO_DATA_AVAILABLE"
    DELINEATION_FAILED = "DELINEATION_FAILED"
    WATERSHED_NOT_FOUND = "WATERSHED_NOT_FOUND"


class APIException(Exception):
    """Custom exception for API errors with structured response."""

    def __init__(
        self,
        error_code: APIErrorCode,
        message: str,
        http_status: int = 500,
        gauge_id: str = "",
    ) -> None:
        """
        Initialize API exception.

        Args:
            error_code: Error code enum value
            message: Human-readable error message
            http_status: HTTP status code to return
            gauge_id: Optional gauge ID associated with the error
        """
        self.error_code = error_code
        self.message = message
        self.http_status = http_status
        self.gauge_id = gauge_id
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers on the FastAPI app.

    This function registers handlers for:
    - Pydantic RequestValidationError (validation failures)
    - APIException (custom API errors)
    - DelineationError (core delineation failures)
    - FileNotFoundError (missing data files)

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """
        Handle Pydantic validation errors.

        Maps validation failures to 400 Bad Request with INVALID_COORDINATES error code.
        """
        # Extract validation error details
        error_details = "; ".join([f"{err['loc'][-1]}: {err['msg']}" for err in exc.errors()])

        error_response = ErrorResponse(
            gauge_id="",
            status="error",
            error_code=APIErrorCode.INVALID_COORDINATES.value,
            error_message=f"Validation error: {error_details}",
        )

        return JSONResponse(
            status_code=400,
            content=error_response.model_dump(),
        )

    @app.exception_handler(APIException)
    async def api_exception_handler(
        request: Request,
        exc: APIException,
    ) -> JSONResponse:
        """
        Handle custom APIException errors.

        Uses the error_code, message, and http_status from the exception.
        """
        error_response = ErrorResponse(
            gauge_id=exc.gauge_id,
            status="error",
            error_code=exc.error_code.value,
            error_message=exc.message,
        )

        return JSONResponse(
            status_code=exc.http_status,
            content=error_response.model_dump(),
        )

    @app.exception_handler(DelineationError)
    async def delineation_exception_handler(
        request: Request,
        exc: DelineationError,
    ) -> JSONResponse:
        """
        Handle DelineationError from core delineation logic.

        Maps to different error codes based on the error message:
        - "does not fall within any unit catchment" -> 404 NO_RIVER_FOUND
        - Other errors -> 500 DELINEATION_FAILED
        """
        error_message = str(exc)

        if "does not fall within any unit catchment" in error_message:
            error_code = APIErrorCode.NO_RIVER_FOUND
            http_status = 404
        else:
            error_code = APIErrorCode.DELINEATION_FAILED
            http_status = 500

        error_response = ErrorResponse(
            gauge_id="",
            status="error",
            error_code=error_code.value,
            error_message=error_message,
        )

        return JSONResponse(
            status_code=http_status,
            content=error_response.model_dump(),
        )

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_exception_handler(
        request: Request,
        exc: FileNotFoundError,
    ) -> JSONResponse:
        """
        Handle FileNotFoundError for missing data files.

        Maps to 404 NO_DATA_AVAILABLE error code.
        """
        error_response = ErrorResponse(
            gauge_id="",
            status="error",
            error_code=APIErrorCode.NO_DATA_AVAILABLE.value,
            error_message=str(exc),
        )

        return JSONResponse(
            status_code=404,
            content=error_response.model_dump(),
        )
