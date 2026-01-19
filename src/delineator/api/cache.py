"""
SQLite-based cache for watershed delineation results.

This module provides a persistent cache for watershed delineation API responses,
storing results in a SQLite database to avoid redundant computation for the same
coordinates. The cache is keyed by rounded lat/lng coordinates.
"""

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from delineator.api.models import DelineateResponse


class WatershedCache:
    """SQLite-based cache for watershed delineation results."""

    def __init__(self, db_path: Path | None = None) -> None:
        """
        Initialize the cache.

        Args:
            db_path: Path to SQLite database file. If None, uses
                     DELINEATOR_CACHE_DB env var (default: ./cache/watersheds.db)
        """
        if db_path is None:
            default_path = os.getenv("DELINEATOR_CACHE_DB", "./cache/watersheds.db")
            db_path = Path(default_path)
        else:
            db_path = Path(db_path)

        # Create parent directories if they don't exist
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watershed_cache (
                    cache_key TEXT PRIMARY KEY,
                    gauge_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    lat REAL NOT NULL,
                    lng REAL NOT NULL,
                    area_km2 REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_watershed_cache_gauge_id
                ON watershed_cache(gauge_id)
            """)
            conn.commit()

    def _make_cache_key(self, lat: float, lng: float) -> str:
        """
        Generate a cache key from coordinates.

        Args:
            lat: Latitude in decimal degrees
            lng: Longitude in decimal degrees

        Returns:
            Cache key string in format "lat,lng" with 6 decimal places
        """
        return f"{round(lat, 6):.6f},{round(lng, 6):.6f}"

    def get(self, lat: float, lng: float) -> DelineateResponse | None:
        """
        Retrieve a cached watershed delineation result.

        Args:
            lat: Latitude in decimal degrees
            lng: Longitude in decimal degrees

        Returns:
            DelineateResponse if found in cache, None otherwise
        """
        cache_key = self._make_cache_key(lat, lng)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT response_json FROM watershed_cache WHERE cache_key = ?",
                (cache_key,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        response_json = row[0]
        return DelineateResponse.model_validate_json(response_json)

    def put(self, lat: float, lng: float, gauge_id: str, response: DelineateResponse) -> None:
        """
        Store a watershed delineation result in the cache.

        Args:
            lat: Latitude in decimal degrees
            lng: Longitude in decimal degrees
            gauge_id: Unique identifier for the gauge
            response: DelineateResponse to cache
        """
        cache_key = self._make_cache_key(lat, lng)
        response_json = response.model_dump_json()
        created_at = datetime.now(UTC).isoformat()
        area_km2 = response.watershed.properties.area_km2

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO watershed_cache
                (cache_key, gauge_id, response_json, created_at, lat, lng, area_km2)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cache_key, gauge_id, response_json, created_at, lat, lng, area_km2),
            )
            conn.commit()

    def delete_by_gauge_id(self, gauge_id: str) -> int:
        """
        Delete all cached entries for a given gauge ID.

        Args:
            gauge_id: Unique identifier for the gauge

        Returns:
            Number of rows deleted
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM watershed_cache WHERE gauge_id = ?",
                (gauge_id,),
            )
            conn.commit()
            return cursor.rowcount

    def stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache_size (number of entries)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM watershed_cache")
            count = cursor.fetchone()[0]

        return {"cache_size": count}
