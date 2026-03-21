"""Terrain elevation data fetching and interpolation."""
from __future__ import annotations

import math

import numpy as np
import requests

from .location import TrackArea


OPEN_ELEVATION_URL = "https://api.open-elevation.com/api/v1/lookup"
MAX_POINTS_PER_REQUEST = 512


class ElevationMap:
    """Grid-based elevation data with bilinear interpolation."""

    def __init__(
        self,
        grid: np.ndarray,
        min_lat: float,
        min_lon: float,
        max_lat: float,
        max_lon: float,
    ):
        self.grid = grid  # shape: (rows, cols)
        self.min_lat = min_lat
        self.min_lon = min_lon
        self.max_lat = max_lat
        self.max_lon = max_lon
        self.rows, self.cols = grid.shape

    def get_elevation(self, lat: float, lon: float) -> float:
        """Get interpolated elevation at a specific lat/lon."""
        # Normalize to 0..1
        u = (lon - self.min_lon) / (self.max_lon - self.min_lon)
        v = (lat - self.min_lat) / (self.max_lat - self.min_lat)
        u = max(0.0, min(1.0, u))
        v = max(0.0, min(1.0, v))

        # Map to grid indices
        col_f = u * (self.cols - 1)
        row_f = v * (self.rows - 1)
        col0, row0 = int(col_f), int(row_f)
        col1 = min(col0 + 1, self.cols - 1)
        row1 = min(row0 + 1, self.rows - 1)

        dc, dr = col_f - col0, row_f - row0

        # Bilinear interpolation
        e00 = self.grid[row0, col0]
        e01 = self.grid[row0, col1]
        e10 = self.grid[row1, col0]
        e11 = self.grid[row1, col1]

        return float(
            e00 * (1 - dc) * (1 - dr)
            + e01 * dc * (1 - dr)
            + e10 * (1 - dc) * dr
            + e11 * dc * dr
        )


def fetch_elevation(area: TrackArea, resolution: int = 32, progress_cb=None) -> ElevationMap:
    """
    Fetch elevation data for the area and return an ElevationMap.

    Args:
        area: Geographic bounding box
        resolution: Grid resolution (NxN grid of elevation samples)
        progress_cb: Optional progress callback

    Returns:
        ElevationMap with bilinear interpolation
    """
    if progress_cb:
        progress_cb("Fetching elevation data...")

    lats = np.linspace(area.min_lat, area.max_lat, resolution)
    lons = np.linspace(area.min_lon, area.max_lon, resolution)

    # Build list of (lat, lon) query points
    points = [
        {"latitude": float(lat), "longitude": float(lon)}
        for lat in lats
        for lon in lons
    ]

    elevations = _fetch_elevation_points(points)

    grid = np.array(elevations, dtype=np.float32).reshape(resolution, resolution)

    return ElevationMap(
        grid=grid,
        min_lat=area.min_lat,
        min_lon=area.min_lon,
        max_lat=area.max_lat,
        max_lon=area.max_lon,
    )


def _fetch_elevation_points(points: list[dict]) -> list[float]:
    """Fetch elevations for a list of {latitude, longitude} dicts."""
    elevations = []

    # Batch requests to avoid hitting API limits
    for i in range(0, len(points), MAX_POINTS_PER_REQUEST):
        batch = points[i : i + MAX_POINTS_PER_REQUEST]
        batch_elevations = _fetch_batch(batch)
        elevations.extend(batch_elevations)

    return elevations


def _fetch_batch(points: list[dict]) -> list[float]:
    """Fetch elevations for a batch of points."""
    try:
        response = requests.post(
            OPEN_ELEVATION_URL,
            json={"locations": points},
            timeout=30,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AC-Track-Generator/1.0",
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return [r.get("elevation", 0.0) for r in results]
    except Exception:
        # Fall back to zero elevation if API fails
        return [0.0] * len(points)


def make_flat_elevation(area: TrackArea) -> ElevationMap:
    """Create a flat (zero elevation) map as fallback."""
    grid = np.zeros((4, 4), dtype=np.float32)
    return ElevationMap(
        grid=grid,
        min_lat=area.min_lat,
        min_lon=area.min_lon,
        max_lat=area.max_lat,
        max_lon=area.max_lon,
    )
