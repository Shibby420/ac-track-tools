"""Download and stitch OpenStreetMap tile imagery for terrain texturing."""
from __future__ import annotations

import io
import math
import time
from typing import Optional

import requests
from PIL import Image

TILE_SERVER = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SIZE = 256  # pixels per OSM tile


def _lat_lon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lon to tile x,y at the given zoom level."""
    lat_r = math.radians(lat)
    n = 2 ** zoom
    tx = int((lon + 180) / 360 * n)
    ty = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return tx, ty


def _tile_top_left_latlon(tx: int, ty: int, zoom: int) -> tuple[float, float]:
    """Return the top-left (lat, lon) of a tile at the given zoom."""
    n = 2 ** zoom
    lon = tx / n * 360.0 - 180.0
    lat_r = math.atan(math.sinh(math.pi * (1 - 2 * ty / n)))
    lat = math.degrees(lat_r)
    return lat, lon


def fetch_satellite_texture(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    target_size: int = 1024,
    progress_cb=None,
) -> tuple[Optional[bytes], tuple[float, float, float, float]]:
    """
    Download OSM map tiles covering the bounding box and stitch into one PNG.

    Chooses a zoom level so tile count stays at most ~10x10 = 100 tiles.

    Returns:
        (png_bytes, (tile_min_lat, tile_min_lon, tile_max_lat, tile_max_lon))
        where the bounds describe the exact lat/lon coverage of the image.
        Returns (None, approx_bounds) if download fails.
    """
    # Pick zoom level keeping tile count manageable
    chosen_zoom = 12
    for zoom in range(16, 9, -1):
        tx_min, ty_max = _lat_lon_to_tile(min_lat, min_lon, zoom)
        tx_max, ty_min = _lat_lon_to_tile(max_lat, max_lon, zoom)
        tx_count = tx_max - tx_min + 1
        ty_count = ty_max - ty_min + 1
        if tx_count <= 10 and ty_count <= 10:
            chosen_zoom = zoom
            break

    zoom = chosen_zoom
    tx_min, ty_max = _lat_lon_to_tile(min_lat, min_lon, zoom)
    tx_max, ty_min = _lat_lon_to_tile(max_lat, max_lon, zoom)
    tx_count = tx_max - tx_min + 1
    ty_count = ty_max - ty_min + 1

    # Compute exact lat/lon bounds of the composite tile grid
    tile_max_lat, tile_min_lon = _tile_top_left_latlon(tx_min, ty_min, zoom)
    tile_min_lat, tile_max_lon = _tile_top_left_latlon(tx_max + 1, ty_max + 1, zoom)
    bounds = (tile_min_lat, tile_min_lon, tile_max_lat, tile_max_lon)

    if progress_cb:
        progress_cb(f"  Downloading {tx_count}x{ty_count} map tiles at zoom {zoom}...")

    composite = Image.new(
        "RGB",
        (tx_count * TILE_SIZE, ty_count * TILE_SIZE),
        (70, 105, 60),  # fallback green in case tiles fail
    )

    session = requests.Session()
    session.headers["User-Agent"] = "AC-Track-Generator/1.0 (assetto corsa track tool)"

    downloaded = 0
    total = tx_count * ty_count

    for row, ty in enumerate(range(ty_min, ty_max + 1)):
        for col, tx in enumerate(range(tx_min, tx_max + 1)):
            url = TILE_SERVER.format(z=zoom, x=tx, y=ty)
            try:
                resp = session.get(url, timeout=15)
                resp.raise_for_status()
                tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                composite.paste(tile_img, (col * TILE_SIZE, row * TILE_SIZE))
                downloaded += 1
                time.sleep(0.05)  # polite rate limiting for OSM servers
            except Exception:
                pass  # leave fallback color for failed tiles

        if progress_cb:
            done = (row + 1) * tx_count
            progress_cb(f"  Tiles: {min(done, total)}/{total}")

    if downloaded == 0:
        if progress_cb:
            progress_cb("  Warning: No map tiles downloaded, using solid color terrain.")
        return None, bounds

    # Resize to square target size
    composite = composite.resize((target_size, target_size), Image.LANCZOS)

    # Slightly boost saturation for better in-game appearance
    try:
        from PIL import ImageEnhance
        composite = ImageEnhance.Color(composite).enhance(1.3)
        composite = ImageEnhance.Contrast(composite).enhance(1.1)
    except Exception:
        pass

    buf = io.BytesIO()
    composite.save(buf, format="PNG", optimize=True)

    if progress_cb:
        size_kb = len(buf.getvalue()) // 1024
        progress_cb(f"  Satellite texture: {target_size}x{target_size}px ({size_kb}KB)")

    return buf.getvalue(), bounds
