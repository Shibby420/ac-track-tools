"""
Track export orchestrator.

Coordinates the full pipeline:
  location → OSM data → elevation → geometry → KN5 + configs + images
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure generator root is on the path for absolute imports
_GEN_ROOT = str(Path(__file__).parent.parent)
if _GEN_ROOT not in sys.path:
    sys.path.insert(0, _GEN_ROOT)


@dataclass
class BuildOptions:
    radius_km: float = 3.0
    include_foliage: bool = True
    include_signs: bool = True
    include_buildings: bool = False
    elevation_resolution: int = 32
    terrain_grid: int = 64
    pitbox_count: int = 8
    output_dir: str = "./output"


@dataclass
class BuildResult:
    success: bool
    track_name: str = ""
    output_path: str = ""
    generated_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_track(
    location: str,
    options: BuildOptions | None = None,
    progress_cb=None,
) -> BuildResult:
    """
    Full pipeline: fetch data, build geometry, export AC track.

    Args:
        location: Place name (e.g. "Monza, Italy") or "lat,lon" string
        options: Build configuration
        progress_cb: Optional callback(message: str) for progress updates

    Returns:
        BuildResult with success flag and file list
    """
    if options is None:
        options = BuildOptions()

    def _progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    result = BuildResult(success=False)

    try:
        # ── 1. Resolve location ─────────────────────────────────────────
        _progress(f"[1/7] Resolving location: {location}...")
        from core.location import get_track_area
        area = get_track_area(location, options.radius_km)
        result.track_name = area.name
        _progress(f"  Area: {area.width_m:.0f}m × {area.height_m:.0f}m @ ({area.center_lat:.4f}, {area.center_lon:.4f})")

        # ── 2. Fetch OSM data ────────────────────────────────────────────
        _progress("[2/7] Fetching OpenStreetMap data...")
        try:
            from core.osm_fetcher import fetch_osm_data
            osm = fetch_osm_data(area, progress_cb=_progress)
            _progress(f"  Found: {len(osm.roads)} roads, {len(osm.forests)} forests, {len(osm.trees)} trees, {len(osm.traffic_signs)} signs")
        except Exception as e:
            result.warnings.append(f"OSM API unavailable ({e}), using offline route data")
            _progress(f"  OSM API blocked — using offline/synthetic road data")
            from core.offline_data import make_synthetic_osm
            osm = make_synthetic_osm(area, route_key=location)
            _progress(f"  Synthetic data: {len(osm.roads)} road(s), {len(osm.trees)} trees")

        if not osm.roads:
            result.errors.append("No roads found. Try a different location or larger radius.")
            return result

        # ── 3. Fetch elevation ───────────────────────────────────────────
        _progress("[3/7] Fetching elevation data...")
        try:
            from core.elevation import fetch_elevation
            elevation = fetch_elevation(area, resolution=options.elevation_resolution, progress_cb=_progress)
        except Exception as e:
            result.warnings.append(f"Elevation fetch failed ({e}), using flat terrain")
            from core.elevation import make_flat_elevation
            elevation = make_flat_elevation(area)

        # ── 4. Build geometry ────────────────────────────────────────────
        _progress("[4/7] Building road geometry...")
        from core.road_builder import build_road_meshes
        road_meshes = build_road_meshes(osm.roads, area, elevation, progress_cb=_progress)
        _progress(f"  Generated {len(road_meshes)} road mesh(es)")

        _progress("[4/7] Building terrain...")
        from core.terrain_builder import build_terrain_mesh
        terrain_mesh = build_terrain_mesh(area, elevation, options.terrain_grid, progress_cb=_progress)

        foliage_meshes = []
        if options.include_foliage and (osm.forests or osm.trees):
            _progress("[4/7] Placing foliage...")
            from core.foliage_builder import build_foliage_meshes
            foliage_meshes = build_foliage_meshes(osm, area, elevation, progress_cb=_progress)
            _progress(f"  Placed {len(foliage_meshes)} tree mesh(es)")

        sign_meshes = []
        if options.include_signs and osm.traffic_signs:
            _progress("[4/7] Placing road signs...")
            from core.sign_builder import build_sign_meshes
            sign_meshes = build_sign_meshes(osm.traffic_signs, area, elevation, progress_cb=_progress)
            _progress(f"  Placed {len(sign_meshes)} sign mesh(es)")

        # ── 5. Assemble scene ────────────────────────────────────────────
        _progress("[5/7] Assembling scene...")
        from core.scene import assemble_scene
        scene = assemble_scene(
            track_name=area.name,
            area=area,
            osm=osm,
            road_meshes=road_meshes,
            terrain_mesh=terrain_mesh,
            foliage_meshes=foliage_meshes,
            sign_meshes=sign_meshes,
            progress_cb=_progress,
        )
        scene.pitbox_count = options.pitbox_count
        total_meshes = len(scene.meshes)
        total_markers = len(scene.markers)
        _progress(f"  Scene: {total_meshes} meshes, {total_markers} markers, {scene.track_length_m:.0f}m track length")

        # ── 6. Export KN5 + configs ──────────────────────────────────────
        track_output = str(Path(options.output_dir) / _sanitize_name(area.name))
        _progress(f"[6/7] Exporting to: {track_output}")

        from export.config_writer import write_all_configs
        config_files = write_all_configs(scene, track_output)
        result.generated_files.extend(config_files)

        _progress("  Exporting KN5...")
        from export.scene_to_kn5 import convert_scene_to_kn5
        kn5_result = convert_scene_to_kn5(scene, track_output)
        if kn5_result.get("warnings"):
            result.warnings.extend(kn5_result["warnings"])
        if kn5_result.get("filepath"):
            result.generated_files.append(kn5_result["filepath"])
        if kn5_result.get("status") == "error":
            result.errors.extend(kn5_result.get("warnings", ["KN5 export failed"]))
            return result

        # ── 7. Generate map images ───────────────────────────────────────
        _progress("[7/7] Generating map images...")
        try:
            from export.image_writer import generate_map_images
            img_files = generate_map_images(scene, track_output, progress_cb=_progress)
            result.generated_files.extend(img_files)
        except Exception as e:
            result.warnings.append(f"Image generation failed: {e}")

        result.success = True
        result.output_path = track_output
        _progress(f"Done! Track built: {track_output}")

    except Exception as e:
        import traceback
        result.errors.append(f"Build failed: {e}")
        result.errors.append(traceback.format_exc())

    return result


def _sanitize_name(name: str) -> str:
    result = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return result.strip("_") or "track"
