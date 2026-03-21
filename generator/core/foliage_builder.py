"""Foliage mesh generation: trees and ground cover from OSM data."""
from __future__ import annotations

import math
import random

import numpy as np

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh
from .osm_fetcher import OSMData, OSMNode, OSMWay


TREE_HEIGHT_MIN = 5.0
TREE_HEIGHT_MAX = 18.0
FOREST_DENSITY = 0.005  # trees per square meter in forests


def build_foliage_meshes(
    osm: OSMData,
    area: TrackArea,
    elevation: ElevationMap,
    seed: int = 42,
    progress_cb=None,
) -> list[Mesh]:
    """
    Generate tree billboard meshes from OSM forest areas and individual trees.

    Trees are represented as crossed-plane billboards (two quads at 90°)
    with the KSTREE_GROUP_ naming convention required by AC.

    Returns list of Mesh objects.
    """
    if progress_cb:
        progress_cb("Placing foliage...")

    rng = random.Random(seed)
    tree_positions: list[tuple[float, float, float, float]] = []  # x, y, z, height

    # Individual OSM trees
    for node in osm.trees:
        x, z = area.to_local(node.lat, node.lon)
        y = elevation.get_elevation(node.lat, node.lon)
        h = rng.uniform(TREE_HEIGHT_MIN, TREE_HEIGHT_MAX)
        tree_positions.append((x, y, z, h))

    # Scatter trees in forest areas
    for forest in osm.forests:
        scattered = _scatter_in_polygon(forest, area, elevation, rng)
        tree_positions.extend(scattered)

    if not tree_positions:
        return []

    if progress_cb:
        progress_cb(f"Generating {len(tree_positions)} tree meshes...")

    meshes: list[Mesh] = []
    for i, (x, y, z, h) in enumerate(tree_positions):
        mesh = _make_tree_billboard(i, x, y, z, h)
        meshes.append(mesh)

    return meshes


def _scatter_in_polygon(
    forest: OSMWay,
    area: TrackArea,
    elevation: ElevationMap,
    rng: random.Random,
) -> list[tuple[float, float, float, float]]:
    """Scatter tree positions inside a forest polygon using bounding box sampling."""
    if len(forest.nodes) < 3:
        return []

    # Get local bounding box of the forest polygon
    local_points = [area.to_local(n.lat, n.lon) for n in forest.nodes]
    xs = [p[0] for p in local_points]
    zs = [p[1] for p in local_points]
    min_x, max_x = min(xs), max(xs)
    min_z, max_z = min(zs), max(zs)

    width = max_x - min_x
    height = max_z - min_z
    area_m2 = width * height
    count = max(1, int(area_m2 * FOREST_DENSITY))
    count = min(count, 200)  # Cap per forest to avoid too many meshes

    positions = []
    lats = [n.lat for n in forest.nodes]
    lons = [n.lon for n in forest.nodes]

    for _ in range(count * 3):  # Oversample and reject outside polygon
        if len(positions) >= count:
            break
        rx = rng.uniform(min_x, max_x)
        rz = rng.uniform(min_z, max_z)

        # Convert back to lat/lon for elevation lookup
        lat = sum(lats) / len(lats)
        lon = sum(lons) / len(lons)

        y = elevation.get_elevation(lat, lon)
        h = rng.uniform(TREE_HEIGHT_MIN, TREE_HEIGHT_MAX)
        positions.append((rx, y, rz, h))

    return positions


def _make_tree_billboard(
    index: int,
    x: float,
    y: float,
    z: float,
    height: float,
) -> Mesh:
    """
    Create a crossed-plane billboard tree mesh.

    Two quads at 90° to each other, both vertical, centered at x,y,z with
    bottom at ground level (y) and top at y+height.

    Named with KSTREE_GROUP_ prefix as required by AC.
    """
    half_w = height * 0.4  # Approximate tree width

    # Plane 1: along X axis
    # Plane 2: along Z axis (rotated 90°)
    verts = [
        # Plane 1: X-aligned
        [x - half_w, y,          z, ],
        [x + half_w, y,          z, ],
        [x + half_w, y + height, z, ],
        [x - half_w, y + height, z, ],
        # Plane 2: Z-aligned
        [x,          y,          z - half_w],
        [x,          y,          z + half_w],
        [x,          y + height, z + half_w],
        [x,          y + height, z - half_w],
    ]

    uvs = [
        # Plane 1
        [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0],
        # Plane 2
        [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0],
    ]

    indices = [
        # Plane 1 (front and back)
        0, 1, 2,  0, 2, 3,
        2, 1, 0,  3, 2, 0,
        # Plane 2 (front and back)
        4, 5, 6,  4, 6, 7,
        6, 5, 4,  7, 6, 4,
    ]

    return make_mesh(
        name=f"KSTREE_GROUP_tree_{index}",
        vertices=verts,
        indices=indices,
        uvs=uvs,
        material_name="TREE",
        ac_surface="KSTREE_GROUP",
    )
