"""Terrain mesh generation from elevation data."""
from __future__ import annotations

import numpy as np

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh


def build_terrain_mesh(
    area: TrackArea,
    elevation: ElevationMap,
    grid_resolution: int = 64,
    progress_cb=None,
) -> Mesh:
    """
    Generate a terrain grid mesh for the entire area.

    Creates a subdivided plane where each vertex samples elevation from the
    ElevationMap. UV coordinates tile across the terrain.

    Args:
        area: Geographic bounding box
        elevation: Elevation data with interpolation
        grid_resolution: Number of grid cells per axis (64x64 = 4096 quads)
        progress_cb: Optional progress callback

    Returns:
        A single Mesh representing the terrain
    """
    if progress_cb:
        progress_cb("Building terrain mesh...")

    cols = grid_resolution + 1
    rows = grid_resolution + 1

    vertices: list[list[float]] = []
    uvs: list[list[float]] = []
    indices: list[int] = []

    uv_scale = 0.1  # UV tiling scale (adjust for texture density)

    for row in range(rows):
        v_frac = row / grid_resolution
        lat = area.min_lat + v_frac * (area.max_lat - area.min_lat)
        z = (v_frac - 0.5) * area.height_m

        for col in range(cols):
            u_frac = col / grid_resolution
            lon = area.min_lon + u_frac * (area.max_lon - area.min_lon)
            x = (u_frac - 0.5) * area.width_m
            y = elevation.get_elevation(lat, lon)

            vertices.append([x, y, z])
            uvs.append([x * uv_scale, z * uv_scale])

    # Build quad indices
    for row in range(grid_resolution):
        for col in range(grid_resolution):
            v0 = row * cols + col
            v1 = row * cols + col + 1
            v2 = (row + 1) * cols + col
            v3 = (row + 1) * cols + col + 1
            # Two triangles per quad
            indices.extend([v0, v2, v1, v1, v2, v3])

    return make_mesh(
        name="1GRASS_terrain",
        vertices=vertices,
        indices=indices,
        uvs=uvs,
        material_name="GRASS",
        ac_surface="1GRASS",
    )
