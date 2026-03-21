"""Road mesh generation from OSM way data."""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh
from .osm_fetcher import OSMWay, get_road_width, get_road_speed

MAX_KN5_VERTICES = 65536


def build_road_meshes(
    roads: list[OSMWay],
    area: TrackArea,
    elevation: ElevationMap,
    progress_cb=None,
) -> list[Mesh]:
    """
    Generate 3D ribbon meshes for all roads.

    Each road way becomes a flat ribbon mesh with the road's width,
    following the elevation of the terrain.

    Returns list of Mesh objects.
    """
    if progress_cb:
        progress_cb(f"Building {len(roads)} road meshes...")

    meshes: list[Mesh] = []
    road_index = 0

    for way in roads:
        if len(way.nodes) < 2:
            continue

        road_meshes = _build_road_ribbon(way, area, elevation, road_index)
        meshes.extend(road_meshes)
        road_index += len(road_meshes)

    return meshes


def _build_road_ribbon(
    way: OSMWay,
    area: TrackArea,
    elevation: ElevationMap,
    start_index: int,
) -> list[Mesh]:
    """Build road ribbon mesh(es) for a single OSM way."""
    width = get_road_width(way)
    half_w = width / 2.0

    highway_type = way.tags.get("highway", "residential")

    # Surface/material based on road type
    if highway_type in ("motorway", "trunk", "primary"):
        ac_surface = "1ROAD"
        mat_name = "ROAD_primary"
    elif highway_type in ("secondary", "tertiary"):
        ac_surface = "1ROAD"
        mat_name = "ROAD_secondary"
    else:
        ac_surface = "1ROAD"
        mat_name = "ROAD_local"

    # Collect centerline points in local coordinates with elevation
    centerline: list[tuple[float, float, float]] = []
    for node in way.nodes:
        x, z = area.to_local(node.lat, node.lon)
        y = elevation.get_elevation(node.lat, node.lon)
        centerline.append((x, y, z))

    if len(centerline) < 2:
        return []

    # Build ribbon geometry
    vertices: list[list[float]] = []
    uvs: list[list[float]] = []
    indices: list[int] = []

    total_dist = 0.0
    texture_scale = 1.0 / max(width, 1.0)  # UV repeats every 'width' meters along road

    for i, (cx, cy, cz) in enumerate(centerline):
        # Calculate road direction at this point
        if i == 0:
            nx, nz = _road_direction(centerline[0], centerline[1])
        elif i == len(centerline) - 1:
            nx, nz = _road_direction(centerline[-2], centerline[-1])
        else:
            # Average direction from prev and next segment
            nx1, nz1 = _road_direction(centerline[i - 1], centerline[i])
            nx2, nz2 = _road_direction(centerline[i], centerline[i + 1])
            nx = (nx1 + nx2) / 2
            nz = (nz1 + nz2) / 2
            length = math.sqrt(nx * nx + nz * nz)
            if length > 0:
                nx /= length
                nz /= length

        # Perpendicular (right side)
        px, pz = nz, -nx

        # Left and right edge points
        lx, lz = cx - px * half_w, cz - pz * half_w
        rx, rz = cx + px * half_w, cz + pz * half_w

        # Elevation at edges (sample terrain)
        ly = cy  # Use centerline elevation for simplicity
        ry = cy

        # Add two vertices (left, right)
        v_base = len(vertices)
        vertices.append([lx, ly, lz])
        vertices.append([rx, ry, rz])

        # UV: U=0 left edge, U=1 right edge; V=distance along road
        uvs.append([0.0, total_dist * texture_scale])
        uvs.append([1.0, total_dist * texture_scale])

        # Accumulate distance for UV
        if i < len(centerline) - 1:
            dx = centerline[i + 1][0] - cx
            dz = centerline[i + 1][2] - cz
            total_dist += math.sqrt(dx * dx + dz * dz)

        # Add quad (two triangles) between this segment and the previous
        if i > 0:
            v0 = v_base - 2  # prev left
            v1 = v_base - 1  # prev right
            v2 = v_base      # curr left
            v3 = v_base + 1  # curr right
            indices.extend([v0, v2, v1, v1, v2, v3])

    if not vertices or not indices:
        return []

    road_name = f"{ac_surface}_{way.tags.get('name', f'road_{way.id}').replace(' ', '_')}"

    # Split into chunks if vertex count exceeds KN5 limit
    return _split_mesh_if_needed(road_name, vertices, indices, uvs, mat_name, ac_surface)


def _road_direction(
    p0: tuple[float, float, float], p1: tuple[float, float, float]
) -> tuple[float, float]:
    """Get normalized XZ direction from p0 to p1."""
    dx = p1[0] - p0[0]
    dz = p1[2] - p0[2]
    length = math.sqrt(dx * dx + dz * dz)
    if length < 1e-6:
        return (0.0, 1.0)
    return (dx / length, dz / length)


def _split_mesh_if_needed(
    name: str,
    vertices: list,
    indices: list,
    uvs: list,
    material_name: str,
    ac_surface: str,
) -> list[Mesh]:
    """Split mesh into chunks under the KN5 65536 vertex limit."""
    if len(vertices) <= MAX_KN5_VERTICES:
        return [make_mesh(name, vertices, indices, uvs, material_name, ac_surface)]

    meshes = []
    chunk_idx = 0
    i = 0

    while i < len(indices):
        chunk_verts: dict[int, int] = {}
        chunk_v: list[list[float]] = []
        chunk_uv: list[list[float]] = []
        chunk_i: list[int] = []

        while i < len(indices) and len(chunk_verts) < MAX_KN5_VERTICES - 6:
            tri = indices[i:i+3]
            if len(tri) < 3:
                break
            for old_idx in tri:
                if old_idx not in chunk_verts:
                    chunk_verts[old_idx] = len(chunk_v)
                    chunk_v.append(vertices[old_idx])
                    chunk_uv.append(uvs[old_idx])
                chunk_i.append(chunk_verts[old_idx])
            i += 3

        if chunk_v:
            meshes.append(make_mesh(
                f"{name}_{chunk_idx}",
                chunk_v,
                chunk_i,
                chunk_uv,
                material_name,
                ac_surface,
            ))
            chunk_idx += 1

    return meshes
