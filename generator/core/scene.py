"""Scene assembly: combines all meshes into a complete AC track scene."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .location import TrackArea
from .mesh import Mesh
from .osm_fetcher import OSMData, OSMWay


@dataclass
class TrackMarker:
    """Represents a track logic object (start, pitbox, time gate, etc.)."""

    name: str
    position: tuple[float, float, float]  # XYZ in local space
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)  # Euler XYZ in radians


@dataclass
class ACScene:
    """Complete AC track scene ready for export."""

    track_name: str
    area: TrackArea
    osm: OSMData

    meshes: list[Mesh] = field(default_factory=list)
    markers: list[TrackMarker] = field(default_factory=list)

    # Track metadata
    track_length_m: float = 0.0
    track_width_m: float = 6.0
    pitbox_count: int = 8
    country: str = ""
    city: str = ""

    def add_mesh(self, mesh: Mesh) -> None:
        self.meshes.append(mesh)

    def add_meshes(self, meshes: list[Mesh]) -> None:
        self.meshes.extend(meshes)

    def add_marker(self, marker: TrackMarker) -> None:
        self.markers.append(marker)


def assemble_scene(
    track_name: str,
    area: TrackArea,
    osm: OSMData,
    road_meshes: list[Mesh],
    terrain_mesh: Mesh,
    foliage_meshes: list[Mesh],
    sign_meshes: list[Mesh],
    progress_cb=None,
) -> ACScene:
    """
    Assemble all meshes and compute track metadata.

    Identifies start/finish positions and places track markers.
    """
    if progress_cb:
        progress_cb("Assembling track scene...")

    scene = ACScene(
        track_name=track_name,
        area=area,
        osm=osm,
    )

    # Add all geometry
    scene.add_meshes(road_meshes)
    scene.add_mesh(terrain_mesh)
    scene.add_meshes(foliage_meshes)
    scene.add_meshes(sign_meshes)

    # Calculate track length from longest road
    main_road = _find_main_road(osm, area)
    if main_road:
        scene.track_length_m = _calculate_road_length(main_road, area)
        scene.track_width_m = _get_typical_width(main_road)

    # Place track markers
    _place_track_markers(scene, main_road, area, progress_cb)

    # Country/city from area name
    parts = area.name.split(",")
    if len(parts) >= 2:
        scene.city = parts[0].strip()
        scene.country = parts[-1].strip()
    else:
        scene.city = area.name
        scene.country = ""

    return scene


def _find_main_road(osm: OSMData, area: TrackArea) -> OSMWay | None:
    """Find the longest/most significant road to use as the main track path."""
    if not osm.roads:
        return None

    best_way = None
    best_length = 0.0

    for way in osm.roads:
        length = _calculate_road_length(way, area)
        if length > best_length:
            best_length = length
            best_way = way

    return best_way


def _calculate_road_length(way: OSMWay, area: TrackArea) -> float:
    """Calculate road length in meters."""
    total = 0.0
    for i in range(len(way.nodes) - 1):
        x0, z0 = area.to_local(way.nodes[i].lat, way.nodes[i].lon)
        x1, z1 = area.to_local(way.nodes[i + 1].lat, way.nodes[i + 1].lon)
        dx, dz = x1 - x0, z1 - z0
        total += math.sqrt(dx * dx + dz * dz)
    return total


def _get_typical_width(way: OSMWay) -> float:
    """Get typical road width from tags."""
    from .osm_fetcher import get_road_width
    return get_road_width(way)


def _place_track_markers(
    scene: ACScene,
    main_road: OSMWay | None,
    area: TrackArea,
    progress_cb=None,
) -> None:
    """Place AC track logic markers: starts, pitboxes, time gates."""
    if not main_road or len(main_road.nodes) < 2:
        # Default markers at origin if no road data
        scene.add_marker(TrackMarker("AC_START_0", (0.0, 0.0, 10.0), (0.0, 0.0, 0.0)))
        for i in range(scene.pitbox_count):
            scene.add_marker(TrackMarker(f"AC_PIT_{i}", (float(i * 6 - 20), 0.0, -10.0), (0.0, math.pi, 0.0)))
        return

    # Place start position at beginning of main road
    start_node = main_road.nodes[0]
    sx, sz = area.to_local(start_node.lat, start_node.lon)

    # Calculate heading direction at start
    next_node = main_road.nodes[1]
    nx, nz = area.to_local(next_node.lat, next_node.lon)
    heading = math.atan2(nx - sx, nz - sz)

    scene.add_marker(TrackMarker(
        "AC_START_0",
        (sx, 0.0, sz),
        (0.0, heading, 0.0),
    ))

    if progress_cb:
        progress_cb("Placing pit boxes...")

    # Place hotlap start same as regular start
    scene.add_marker(TrackMarker(
        "AC_HOTLAP_START_0",
        (sx + 2.0, 0.0, sz),
        (0.0, heading, 0.0),
    ))

    # Find a straight section for pit lane (roughly 1/4 into the road)
    pit_start_idx = max(1, len(main_road.nodes) // 4)
    pit_node = main_road.nodes[pit_start_idx]
    px, pz = area.to_local(pit_node.lat, pit_node.lon)

    # Get perpendicular direction for pit row offset
    if pit_start_idx + 1 < len(main_road.nodes):
        pnext = main_road.nodes[pit_start_idx + 1]
        pnx, pnz = area.to_local(pnext.lat, pnext.lon)
        road_heading = math.atan2(pnx - px, pnz - pz)
    else:
        road_heading = heading

    # Pit row perpendicular to road
    perp_heading = road_heading + math.pi / 2
    perp_x = math.sin(perp_heading)
    perp_z = math.cos(perp_heading)

    n_pits = scene.pitbox_count
    for i in range(n_pits):
        offset = (i - n_pits / 2) * 6.5  # 6.5m spacing per pitbox
        pit_x = px + perp_x * (8.0 + offset)  # 8m from road edge
        pit_z = pz + perp_z * (8.0 + offset)
        scene.add_marker(TrackMarker(
            f"AC_PIT_{i}",
            (pit_x, 0.0, pit_z),
            (0.0, road_heading + math.pi, 0.0),
        ))

    # Time gate at roughly halfway through the track
    mid_idx = len(main_road.nodes) // 2
    mid_node = main_road.nodes[mid_idx]
    mx, mz = area.to_local(mid_node.lat, mid_node.lon)

    if mid_idx + 1 < len(main_road.nodes):
        mnext = main_road.nodes[mid_idx + 1]
        mnx, mnz = area.to_local(mnext.lat, mnext.lon)
        gate_heading = math.atan2(mnx - mx, mnz - mz)
    else:
        gate_heading = heading

    # Gate perpendicular offset
    gate_perp_x = math.sin(gate_heading + math.pi / 2)
    gate_perp_z = math.cos(gate_heading + math.pi / 2)
    gate_half_w = 8.0

    scene.add_marker(TrackMarker(
        "AC_TIME_0_L",
        (mx - gate_perp_x * gate_half_w, 0.0, mz - gate_perp_z * gate_half_w),
    ))
    scene.add_marker(TrackMarker(
        "AC_TIME_0_R",
        (mx + gate_perp_x * gate_half_w, 0.0, mz + gate_perp_z * gate_half_w),
    ))
