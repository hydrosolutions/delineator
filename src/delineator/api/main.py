"""
FastAPI application factory and app instance.

The create_app() factory allows configuration injection for testing,
while the module-level `app` instance is used for uvicorn.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from delineator.api.exceptions import register_exception_handlers
from delineator.api.routes import router


def _get_cors_origins() -> list[str]:
    """
    Get CORS allowed origins from environment variable or defaults.

    Reads from DELINEATOR_CORS_ORIGINS environment variable (comma-separated).
    If not set, returns default localhost origins for development.

    Returns:
        List of allowed origin URLs.
    """
    env_origins = os.getenv("DELINEATOR_CORS_ORIGINS")
    if env_origins:
        return [origin.strip() for origin in env_origins.split(",")]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance ready to serve requests.
    """
    application = FastAPI(
        title="Delineator API",
        description="Watershed delineation service using MERIT-Hydro data",
        version="0.1.0",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(router)

    return application


# Module-level app instance for uvicorn
app = create_app()
