---
module: api
description: HTTP API for watershed delineation, providing REST endpoints for the Virtual-Gauges frontend to request watershed boundaries with persistent caching.
---

## Files

- `__init__.py` - Module exports (app, create_app)
- `main.py` - FastAPI application factory and app instance

## Key Interfaces

- `create_app()` - Factory function returning configured FastAPI application
- `app` - Module-level FastAPI instance for uvicorn
