"""Generate map.png, outline.png, and preview.png for AC track."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import sys

_GEN_ROOT = str(Path(__file__).parent.parent)
if _GEN_ROOT not in sys.path:
    sys.path.insert(0, _GEN_ROOT)

from core.location import TrackArea  # type: ignore
from core.osm_fetcher import OSMData  # type: ignore
from core.scene import ACScene  # type: ignore


MAP_RESOLUTION = 2048
OUTLINE_RESOLUTION = 512
PREVIEW_RESOLUTION = (1920, 1080)


def generate_map_images(
    scene: ACScene,
    output_dir: str,
    progress_cb=None,
) -> list[str]:
    """
    Generate map.png, ui/outline.png, and ui/preview.png.

    Returns list of generated file paths.
    """
    created: list[str] = []
    area = scene.area

    if progress_cb:
        progress_cb("Generating track map images...")

    track_dir = Path(output_dir)
    ui_dir = track_dir / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)

    # Compute tight bounding box around actual road geometry for better framing
    road_bounds = _compute_road_bounds(scene.osm, area)

    # Generate map.png (overhead road drawing, white on transparent — AC standard)
    map_img = _draw_overhead_map(scene.osm, road_bounds, MAP_RESOLUTION, MAP_RESOLUTION)
    map_path = track_dir / "map.png"
    map_img.save(str(map_path), "PNG")
    created.append(str(map_path))

    # Generate outline.png (512x512 downscaled version of map)
    outline_img = map_img.resize((OUTLINE_RESOLUTION, OUTLINE_RESOLUTION), Image.LANCZOS)
    outline_path = ui_dir / "outline.png"
    outline_img.save(str(outline_path), "PNG")
    created.append(str(outline_path))

    # Generate preview.png (colored overhead view for track selection screen)
    preview_img = _draw_preview(scene.osm, road_bounds, PREVIEW_RESOLUTION[0], PREVIEW_RESOLUTION[1])
    preview_path = ui_dir / "preview.png"
    preview_img.save(str(preview_path), "PNG")
    created.append(str(preview_path))

    return created


def _compute_road_bounds(osm: OSMData, area: TrackArea) -> dict:
    """
    Compute tight bounding box of all road nodes, with 8% padding.
    Falls back to area bounds if no roads.
    """
    all_lats = []
    all_lons = []
    for way in osm.roads:
        for n in way.nodes:
            all_lats.append(n.lat)
            all_lons.append(n.lon)

    if not all_lats:
        return {
            "min_lat": area.min_lat, "max_lat": area.max_lat,
            "min_lon": area.min_lon, "max_lon": area.max_lon,
        }

    min_lat, max_lat = min(all_lats), max(all_lats)
    min_lon, max_lon = min(all_lons), max(all_lons)

    # Add 8% padding on each side
    pad_lat = (max_lat - min_lat) * 0.08 + 0.001
    pad_lon = (max_lon - min_lon) * 0.08 + 0.001

    return {
        "min_lat": min_lat - pad_lat,
        "max_lat": max_lat + pad_lat,
        "min_lon": min_lon - pad_lon,
        "max_lon": max_lon + pad_lon,
    }


def _draw_overhead_map(
    osm: OSMData,
    bounds: dict,
    width: int,
    height: int,
) -> Image.Image:
    """
    Draw overhead road map: white roads on transparent background.
    Standard AC map.png format.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    span_km = _bounds_span_km(bounds)

    for way in osm.roads:
        if len(way.nodes) < 2:
            continue

        pixels = [_latlon_to_pixel(n.lat, n.lon, bounds, width, height) for n in way.nodes]
        highway = way.tags.get("highway", "residential")
        lw = _road_px(highway, width, span_km)

        # Draw a slightly wider dark shadow first for edge definition
        if lw >= 2:
            for i in range(len(pixels) - 1):
                draw.line([pixels[i], pixels[i + 1]], fill=(140, 140, 140, 180), width=lw + 6)

        # Draw white road on top
        for i in range(len(pixels) - 1):
            draw.line([pixels[i], pixels[i + 1]], fill=(255, 255, 255, 255), width=lw)

    img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
    return img


def _draw_preview(
    osm: OSMData,
    bounds: dict,
    width: int,
    height: int,
) -> Image.Image:
    """
    Draw colored preview image for track selection screen.
    Dark terrain, bright roads for clear contrast.
    """
    # Dark forest green background
    img = Image.new("RGB", (width, height), (28, 58, 28))
    draw = ImageDraw.Draw(img)

    span_km = _bounds_span_km(bounds)

    # Draw forest areas as slightly lighter patches
    for forest in osm.forests:
        if len(forest.nodes) < 3:
            continue
        pixels = [_latlon_to_pixel(n.lat, n.lon, bounds, width, height) for n in forest.nodes]
        draw.polygon(pixels, fill=(38, 75, 38))

    # Draw road shadow (dark outline) first
    for way in osm.roads:
        if len(way.nodes) < 2:
            continue
        pixels = [_latlon_to_pixel(n.lat, n.lon, bounds, width, height) for n in way.nodes]
        highway = way.tags.get("highway", "residential")
        lw = _road_px(highway, width, span_km)
        shadow_color = (15, 15, 15)
        for i in range(len(pixels) - 1):
            draw.line([pixels[i], pixels[i + 1]], fill=shadow_color, width=lw + 8)

    # Draw road surface
    for way in osm.roads:
        if len(way.nodes) < 2:
            continue
        pixels = [_latlon_to_pixel(n.lat, n.lon, bounds, width, height) for n in way.nodes]
        highway = way.tags.get("highway", "residential")
        road_color = _road_color(highway)
        lw = _road_px(highway, width, span_km)
        for i in range(len(pixels) - 1):
            draw.line([pixels[i], pixels[i + 1]], fill=road_color, width=lw)

    # Draw center line (white dashes for main roads)
    for way in osm.roads:
        if len(way.nodes) < 2:
            continue
        highway = way.tags.get("highway", "residential")
        if highway not in ("motorway", "trunk", "primary"):
            continue
        pixels = [_latlon_to_pixel(n.lat, n.lon, bounds, width, height) for n in way.nodes]
        lw = max(1, _road_px(highway, width, span_km) // 5)
        for i in range(0, len(pixels) - 1, 2):
            draw.line([pixels[i], pixels[i + 1]], fill=(255, 255, 220, 200), width=lw)

    # Slight blur for a polished look
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

    # Add vignette effect (darken corners)
    _apply_vignette(img, width, height)

    return img


def _apply_vignette(img: Image.Image, width: int, height: int) -> None:
    """Darken the edges with a smooth radial vignette."""
    import numpy as np
    cx, cy = width / 2.0, height / 2.0
    # Normalized distance from center (0=center, 1=corner)
    ys, xs = np.mgrid[0:height, 0:width]
    dx = (xs - cx) / cx
    dy = (ys - cy) / cy
    dist = np.sqrt(dx ** 2 + dy ** 2)
    # Vignette strength: 0 in center, up to 0.65 at corners
    strength = np.clip((dist - 0.5) / 0.7, 0.0, 1.0) ** 1.8
    alpha = (strength * 165).astype(np.uint8)
    vignette = Image.fromarray(alpha, mode="L")
    black = Image.new("RGB", (width, height), (0, 0, 0))
    img.paste(black, mask=vignette)


def _latlon_to_pixel(
    lat: float, lon: float, bounds: dict, width: int, height: int
) -> tuple[int, int]:
    """Convert lat/lon to pixel coordinates using tight road bounds."""
    span_lon = bounds["max_lon"] - bounds["min_lon"]
    span_lat = bounds["max_lat"] - bounds["min_lat"]
    u = (lon - bounds["min_lon"]) / span_lon if span_lon else 0.5
    v = 1.0 - (lat - bounds["min_lat"]) / span_lat if span_lat else 0.5
    u = max(0.0, min(1.0, u))
    v = max(0.0, min(1.0, v))
    return (int(u * (width - 1)), int(v * (height - 1)))


def _bounds_span_km(bounds: dict) -> float:
    """Return the approximate larger dimension of bounds in km."""
    span_lat_km = (bounds["max_lat"] - bounds["min_lat"]) * 111.32
    mid_lat = (bounds["min_lat"] + bounds["max_lat"]) / 2
    span_lon_km = (bounds["max_lon"] - bounds["min_lon"]) * 111.32 * math.cos(math.radians(mid_lat))
    return max(span_lat_km, span_lon_km)


def _road_px(highway: str, image_width: int, span_km: float) -> int:
    """
    Compute line width in pixels for a road type.

    Blends physical scale with a visual minimum so roads are always
    clearly readable at any zoom level.
    """
    road_width_m = {
        "motorway": 22, "trunk": 18, "primary": 14,
        "secondary": 10, "tertiary": 8,
        "residential": 6, "unclassified": 6,
        "service": 4, "track": 5,
    }.get(highway, 6)

    # Physical pixel width at this map scale
    px_physical = road_width_m * image_width / max(span_km * 1000, 1)

    # Visual minimum — roads must dominate the image at any scale
    # These are calibrated for 2048px; scaled proportionally for other sizes
    visual_min = {
        "motorway": 48, "trunk": 40, "primary": 34,
        "secondary": 26, "tertiary": 20,
        "residential": 16, "unclassified": 16,
        "service": 10, "track": 14,
    }.get(highway, 14)
    visual_min = int(visual_min * image_width / 2048)

    return max(visual_min, min(120, int(px_physical)))


def _road_color(highway: str) -> tuple[int, int, int]:
    """Get road surface color by type."""
    colors = {
        "motorway": (210, 185, 110),
        "trunk":    (205, 175, 100),
        "primary":  (195, 170, 95),
        "secondary":(155, 150, 105),
        "tertiary": (130, 130, 100),
    }
    return colors.get(highway, (110, 110, 110))
