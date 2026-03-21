"""Location resolution: geocode place names to coordinates and compute bounding boxes."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import requests


@dataclass
class TrackArea:
    name: str
    center_lat: float
    center_lon: float
    radius_km: float
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    @property
    def width_m(self) -> float:
        return (self.max_lon - self.min_lon) * 111320 * math.cos(math.radians(self.center_lat))

    @property
    def height_m(self) -> float:
        return (self.max_lat - self.min_lat) * 111320

    def to_local(self, lat: float, lon: float) -> tuple[float, float]:
        """Convert lat/lon to local XZ coordinates in meters (Y=0 flat)."""
        x = (lon - self.center_lon) * 111320 * math.cos(math.radians(self.center_lat))
        z = (lat - self.center_lat) * 111320
        return (x, z)


def geocode(location_name: str) -> tuple[float, float] | None:
    """Resolve a place name to (lat, lon) using Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": location_name,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "AC-Track-Generator/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        results = response.json()
        if results:
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception as e:
        raise RuntimeError(f"Geocoding failed for '{location_name}': {e}") from e
    return None



# Fallback coordinates for known locations when geocoding API is unavailable
_KNOWN_COORDS: dict[str, tuple[float, float]] = {
    "palisades": (41.0811, -73.9733),       # Center of full route (Fort Lee → Bear Mt)
    "palisades interstate": (41.0811, -73.9733),
    "palisades parkway": (41.0811, -73.9733),
    "bear mountain": (41.3148, -73.9528),
    "nurburgring": (50.3356, 6.9475),
    "monaco": (43.7384, 7.4246),
    "silverstone": (52.0786, -1.0169),
    "monza": (45.6156, 9.2811),
    "spa": (50.4372, 5.9714),
    "laguna seca": (36.5841, -121.7547),
    "suzuka": (34.8431, 136.5407),
    "le mans": (47.9497, 0.2081),
    "interlagos": (-23.7036, -46.6997),
    "zandvoort": (52.3888, 4.5409),
    "imola": (44.3439, 11.7167),
    "barcelona": (41.5700, 2.2611),
}


def get_track_area(location: str, radius_km: float = 3.0) -> TrackArea:
    """
    Resolve a location name or 'lat,lon' string to a TrackArea.

    Args:
        location: Place name like 'Nurburgring' or coordinates '50.335,6.947'
        radius_km: Radius of the area to capture

    Returns:
        TrackArea with bounding box
    """
    # Try parsing as coordinates first
    if "," in location:
        parts = location.split(",")
        if len(parts) == 2:
            try:
                lat, lon = float(parts[0].strip()), float(parts[1].strip())
                return _make_area("Custom", lat, lon, radius_km)
            except ValueError:
                pass

    # Check known fallback coords first (for offline use)
    loc_lower = location.lower()
    for key, (lat, lon) in _KNOWN_COORDS.items():
        if key in loc_lower or loc_lower in key:
            return _make_area(location, lat, lon, radius_km)

    # Geocode by name
    try:
        result = geocode(location)
        if result:
            lat, lon = result
            return _make_area(location, lat, lon, radius_km)
    except RuntimeError:
        pass

    raise RuntimeError(
        f"Could not find location: '{location}'\n"
        "Tip: Use --coords LAT,LON to specify coordinates directly.\n"
        "Example: --coords 40.9587,-73.9890"
    )


def _make_area(name: str, lat: float, lon: float, radius_km: float) -> TrackArea:
    """Build TrackArea from center coordinates and radius."""
    # 1 degree lat ≈ 111,320m; 1 degree lon ≈ 111,320m * cos(lat)
    delta_lat = radius_km / 111.32
    delta_lon = radius_km / (111.32 * math.cos(math.radians(lat)))
    return TrackArea(
        name=name,
        center_lat=lat,
        center_lon=lon,
        radius_km=radius_km,
        min_lat=lat - delta_lat,
        min_lon=lon - delta_lon,
        max_lat=lat + delta_lat,
        max_lon=lon + delta_lon,
    )
