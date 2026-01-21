"""
Tests for CORS middleware configuration.

Verifies cross-origin request handling including preflight requests,
allowed/disallowed origins, and environment variable configuration.
"""

import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from delineator.api.main import _get_cors_origins, create_app


class TestCORSMiddleware:
    """Tests for CORS middleware behavior."""

    def test_preflight_request_returns_cors_headers(self) -> None:
        """OPTIONS preflight request returns correct CORS headers."""
        app = create_app()
        client = TestClient(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" in response.headers
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

        # Verify allowed methods include GET, POST, DELETE
        allowed_methods = response.headers.get("Access-Control-Allow-Methods", "")
        assert "GET" in allowed_methods
        assert "POST" in allowed_methods
        assert "DELETE" in allowed_methods

    def test_allowed_origin_receives_cors_header(self) -> None:
        """Allowed origin receives Access-Control-Allow-Origin header."""
        app = create_app()
        client = TestClient(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )

        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" in response.headers
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

    def test_unauthorized_origin_no_cors_header(self) -> None:
        """Unauthorized origin does not receive CORS headers."""
        app = create_app()
        client = TestClient(app)

        response = client.get(
            "/health",
            headers={"Origin": "http://unauthorized.com"},
        )

        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers


class TestGetCorsOrigins:
    """Tests for _get_cors_origins() helper function."""

    def test_returns_defaults_when_env_var_not_set(self) -> None:
        """Returns default localhost origins when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            origins = _get_cors_origins()
            assert origins == ["http://localhost:3000", "http://127.0.0.1:3000"]

    def test_parses_comma_separated_env_var(self) -> None:
        """Parses comma-separated origins from environment variable."""
        with patch.dict(
            os.environ,
            {"DELINEATOR_CORS_ORIGINS": "https://app.example.com, https://staging.example.com"},
        ):
            origins = _get_cors_origins()
            assert origins == ["https://app.example.com", "https://staging.example.com"]
