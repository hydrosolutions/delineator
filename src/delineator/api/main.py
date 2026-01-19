"""
FastAPI application factory and app instance.

The create_app() factory allows configuration injection for testing,
while the module-level `app` instance is used for uvicorn.
"""

from fastapi import FastAPI


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

    return application


# Module-level app instance for uvicorn
app = create_app()
