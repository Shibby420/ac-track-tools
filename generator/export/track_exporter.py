"""
Track export orchestrator.

Coordinates the full pipeline:
  location → OSM data → elevation → satellite texture → geometry → KN5 + configs + images
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
    include_buildings: bool = True
    include_guardrails: bool = True
    include_markings: bool = True
    include_satellite: bool = True
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
        _progress(f"[1/8] Resolving location: {location}...")
        from core.location import get_track_area
        area = get_track_area(location, options.radius_km)
        result.track_name = area.name
        _progress(f"  Area: {area.width_m:.0f}m × {area.height_m:.0f}m @ ({area.center_lat:.4f}, {area.center_lon:.4f})")

        # ── 2. Fetch OSM data ────────────────────────────────────────────
        _progress("[2/8] Fetching OpenStreetMap data...")
        try:
            from core.osm_fetcher import fetch_osm_data
            osm = fetch_osm_data(area, progress_cb=_progress)
            _progress(
                f"  Found: {len(osm.roads)} roads, {len(osm.forests)} forests, "
                f"{len(osm.trees)} trees, {len(osm.buildings)} buildings, "
                f"{len(osm.traffic_signs)} signs"
            )
        except Exception as e:
            result.warnings.append(f"OSM API unavailable ({e}), using offline route data")
            _progress("  OSM API blocked — using offline/synthetic road data")
            from core.offline_data import make_synthetic_osm
            osm = make_synthetic_osm(area, route_key=location)
            _progress(f"  Synthetic data: {len(osm.roads)} road(s), {len(osm.trees)} trees")

        if not osm.roads:
            result.errors.append("No roads found. Try a different location or larger radius.")
            return result

        # ── 3. Fetch elevation ───────────────────────────────────────────
        _progress("[3/8] Fetching elevation data...")
        try:
            from core.elevation import fetch_elevation
            elevation = fetch_elevation(area, resolution=options.elevation_resolution, progress_cb=_progress)
        except Exception as e:
            result.warnings.append(f"Elevation fetch failed ({e}), using flat terrain")
            from core.elevation import make_flat_elevation
            elevation = make_flat_elevation(area)

        # ── 4. Download satellite texture ────────────────────────────────
        satellite_texture = None
        satellite_bounds = None

        if options.include_satellite:
            _progress("[4/8] Downloading satellite map texture...")
            try:
                from core.satellite import fetch_satellite_texture
                sat_data, sat_bounds = fetch_satellite_texture(
                    area.min_lat, area.min_lon,
                    area.max_lat, area.max_lon,
                    target_size=1024,
                    progress_cb=_progress,
                )
                if sat_data:
                    satellite_texture = sat_data
                    satellite_bounds = sat_bounds
                    _progress("  Satellite texture downloaded successfully.")
                else:
                    result.warnings.append("Satellite texture unavailable, using solid colour terrain.")
                    _progress("  Using fallback solid colour terrain.")
            except Exception as e:
                result.warnings.append(f"Satellite download failed ({e}), using solid colour.")
                _progress(f"  Satellite download error: {e}")
        else:
            _progress("[4/8] Skipping satellite texture (disabled).")

        # ── 5. Build geometry ────────────────────────────────────────────
        _progress("[5/8] Building road geometry...")
        from core.road_builder import build_road_meshes
        road_meshes = build_road_meshes(osm.roads, area, elevation, progress_cb=_progress)
        _progress(f"  Generated {len(road_meshes)} road mesh(es)")

        _progress("[5/8] Building terrain...")
        from core.terrain_builder import build_terrain_mesh
        terrain_mesh = build_terrain_mesh(
            area, elevation, options.terrain_grid,
            progress_cb=_progress,
            satellite_bounds=satellite_bounds,
        )

        foliage_meshes = []
        if options.include_foliage and (osm.forests or osm.trees):
            _progress("[5/8] Placing foliage...")
            from core.foliage_builder import build_foliage_meshes
            foliage_meshes = build_foliage_meshes(osm, area, elevation, progress_cb=_progress)
            _progress(f"  Placed {len(foliage_meshes)} tree mesh(es)")

        sign_meshes = []
        if options.include_signs and osm.traffic_signs:
            _progress("[5/8] Placing road signs...")
            from core.sign_builder import build_sign_meshes
            sign_meshes = build_sign_meshes(osm.traffic_signs, area, elevation, progress_cb=_progress)
            _progress(f"  Placed {len(sign_meshes)} sign mesh(es)")

        marking_meshes = []
        if options.include_markings:
            _progress("[5/8] Building road markings...")
            from core.markings_builder import build_marking_meshes
            marking_meshes = build_marking_meshes(osm.roads, area, elevation, progress_cb=_progress)

        guardrail_meshes = []
        if options.include_guardrails:
            _progress("[5/8] Building guardrails...")
            from core.guardrail_builder import build_guardrail_meshes
            guardrail_meshes = build_guardrail_meshes(osm.roads, area, elevation, progress_cb=_progress)

        building_meshes = []
        if options.include_buildings and osm.buildings:
            _progress("[5/8] Building structures...")
            from core.building_builder import build_building_meshes
            building_meshes = build_building_meshes(osm.buildings, area, elevation, progress_cb=_progress)

        # ── 6. Assemble scene ────────────────────────────────────────────
        _progress("[6/8] Assembling scene...")
        from core.scene import assemble_scene
        scene = assemble_scene(
            track_name=area.name,
            area=area,
            osm=osm,
            road_meshes=road_meshes,
            terrain_mesh=terrain_mesh,
            foliage_meshes=foliage_meshes,
            sign_meshes=sign_meshes,
            building_meshes=building_meshes,
            guardrail_meshes=guardrail_meshes,
            marking_meshes=marking_meshes,
            progress_cb=_progress,
        )
        scene.pitbox_count = options.pitbox_count
        _progress(
            f"  Scene: {len(scene.meshes)} meshes, {len(scene.markers)} markers, "
            f"{scene.track_length_m:.0f}m track length"
        )

        # ── 7. Export KN5 + configs ──────────────────────────────────────
        track_output = str(Path(options.output_dir) / _sanitize_name(area.name))
        _progress(f"[7/8] Exporting to: {track_output}")

        from export.config_writer import write_all_configs
        config_files = write_all_configs(scene, track_output)
        result.generated_files.extend(config_files)

        _progress("  Exporting KN5...")
        from export.scene_to_kn5 import convert_scene_to_kn5
        kn5_result = convert_scene_to_kn5(scene, track_output, satellite_texture=satellite_texture)
        if kn5_result.get("warnings"):
            result.warnings.extend(kn5_result["warnings"])
        if kn5_result.get("filepath"):
            result.generated_files.append(kn5_result["filepath"])
        if kn5_result.get("status") == "error":
            result.errors.extend(kn5_result.get("warnings", ["KN5 export failed"]))
            return result

        # ── 8. Generate map images ───────────────────────────────────────
        _progress("[8/8] Generating map images...")
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
