"""Generate map.png, outline.png, and preview.png for AC track."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import sys
from pathlib import Path

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

    # Generate map.png (overhead road drawing, black on transparent)
    map_img = _draw_overhead_map(scene.osm, area, MAP_RESOLUTION, MAP_RESOLUTION)
    map_path = track_dir / "map.png"
    map_img.save(str(map_path), "PNG")
    created.append(str(map_path))

    # Generate outline.png (512x512 downscaled version of map)
    outline_img = map_img.resize((OUTLINE_RESOLUTION, OUTLINE_RESOLUTION), Image.LANCZOS)
    outline_path = ui_dir / "outline.png"
    outline_img.save(str(outline_path), "PNG")
    created.append(str(outline_path))

    # Generate preview.png (colored overhead view for track selection screen)
    preview_img = _draw_preview(scene.osm, area, PREVIEW_RESOLUTION[0], PREVIEW_RESOLUTION[1])
    preview_path = ui_dir / "preview.png"
    preview_img.save(str(preview_path), "PNG")
    created.append(str(preview_path))

    return created


def _draw_overhead_map(
    osm: OSMData,
    area: TrackArea,
    width: int,
    height: int,
) -> Image.Image:
    """
    Draw overhead road map: white roads on transparent background.
    Standard AC map.png format.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for way in osm.roads:
        if len(way.nodes) < 2:
            continue

        # Convert nodes to pixel coordinates
        pixels = [_latlon_to_pixel(n.lat, n.lon, area, width, height) for n in way.nodes]

        # Road line width based on road type (thicker for main roads)
        highway = way.tags.get("highway", "residential")
        line_width = _road_line_width(highway, width, area)

        # Draw white road
        for i in range(len(pixels) - 1):
            draw.line([pixels[i], pixels[i + 1]], fill=(255, 255, 255, 255), width=line_width)

    # Slight blur for smoother look
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    return img


def _draw_preview(
    osm: OSMData,
    area: TrackArea,
    width: int,
    height: int,
) -> Image.Image:
    """
    Draw colored preview image for track selection screen.
    Green terrain, grey roads, dark green forests.
    """
    img = Image.new("RGB", (width, height), (60, 100, 50))  # Green background
    draw = ImageDraw.Draw(img)

    # Draw forest areas
    for forest in osm.forests:
        if len(forest.nodes) < 3:
            continue
        pixels = [_latlon_to_pixel(n.lat, n.lon, area, width, height) for n in forest.nodes]
        draw.polygon(pixels, fill=(30, 80, 30))

    # Draw roads
    for way in osm.roads:
        if len(way.nodes) < 2:
            continue
        pixels = [_latlon_to_pixel(n.lat, n.lon, area, width, height) for n in way.nodes]
        highway = way.tags.get("highway", "residential")
        road_color = _road_color(highway)
        line_width = _road_line_width(highway, width, area)

        for i in range(len(pixels) - 1):
            draw.line([pixels[i], pixels[i + 1]], fill=road_color, width=line_width)

    return img


def _latlon_to_pixel(
    lat: float, lon: float, area: TrackArea, width: int, height: int
) -> tuple[int, int]:
    """Convert lat/lon to pixel coordinates for image drawing."""
    u = (lon - area.min_lon) / (area.max_lon - area.min_lon)
    v = 1.0 - (lat - area.min_lat) / (area.max_lat - area.min_lat)  # Flip Y
    u = max(0.0, min(1.0, u))
    v = max(0.0, min(1.0, v))
    return (int(u * width), int(v * height))


def _road_line_width(highway: str, image_width: int, area: TrackArea) -> int:
    """Scale road line width relative to image and area size."""
    base_widths = {
        "motorway": 6, "trunk": 5, "primary": 4,
        "secondary": 3, "tertiary": 3,
        "residential": 2, "unclassified": 2,
        "service": 1, "track": 1,
    }
    base = base_widths.get(highway, 2)
    # Scale up for smaller areas
    scale = max(1.0, 3.0 / area.radius_km)
    return max(1, int(base * scale))


def _road_color(highway: str) -> tuple[int, int, int]:
    """Get road color by type."""
    colors = {
        "motorway": (200, 150, 50),
        "trunk": (210, 160, 60),
        "primary": (180, 140, 60),
        "secondary": (160, 160, 100),
    }
    return colors.get(highway, (130, 130, 130))  # Default grey
