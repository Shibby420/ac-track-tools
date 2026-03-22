"""Building mesh generation from OSM building footprint data."""
from __future__ import annotations

import math
import random

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh
from .osm_fetcher import OSMWay

DEFAULT_FLOOR_HEIGHT = 3.2   # meters per storey
DEFAULT_FLOORS = 2           # default storeys when tags absent
MAX_BUILDINGS = 1500         # cap to avoid excessive mesh count


def build_building_meshes(
    buildings: list[OSMWay],
    area: TrackArea,
    elevation: ElevationMap,
    seed: int = 77,
    progress_cb=None,
) -> list[Mesh]:
    """
    Extrude OSM building footprints into 3D box meshes (walls + flat roof).

    Uses building:levels or height tags when available; otherwise randomises
    between 1 and DEFAULT_FLOORS storeys for variety.
    """
    if progress_cb:
        progress_cb(f"Building {min(len(buildings), MAX_BUILDINGS)} structures...")

    rng = random.Random(seed)
    meshes: list[Mesh] = []

    for way in buildings[:MAX_BUILDINGS]:
        nodes = way.nodes
        if len(nodes) < 3:
            continue

        height = _get_height(way, rng)

        # Build footprint in local XZ, collect ground elevation
        footprint: list[tuple[float, float]] = []
        ground_y = 0.0
        for node in nodes:
            x, z = area.to_local(node.lat, node.lon)
            footprint.append((x, z))
            ground_y = elevation.get_elevation(node.lat, node.lon)

        # Remove duplicate closing vertex if present
        if len(footprint) > 1 and footprint[0] == footprint[-1]:
            footprint = footprint[:-1]

        if len(footprint) < 3:
            continue

        wall = _make_walls(f"BUILDING_{way.id}", footprint, ground_y, height)
        roof = _make_roof(f"BUILDING_ROOF_{way.id}", footprint, ground_y + height)
        if wall:
            meshes.append(wall)
        if roof:
            meshes.append(roof)

    if progress_cb:
        progress_cb(f"  Built {len(meshes) // 2} building(s) ({len(meshes)} meshes)")

    return meshes


def _get_height(way: OSMWay, rng: random.Random) -> float:
    """Determine building height from OSM tags with fallback randomisation."""
    if "height" in way.tags:
        try:
            return float(way.tags["height"].replace("m", "").strip())
        except ValueError:
            pass

    if "building:levels" in way.tags:
        try:
            levels = float(way.tags["building:levels"])
            return max(1.0, levels) * DEFAULT_FLOOR_HEIGHT
        except ValueError:
            pass

    # Vary between 1 and DEFAULT_FLOORS storeys
    floors = rng.randint(1, DEFAULT_FLOORS + 1)
    return floors * DEFAULT_FLOOR_HEIGHT


def _make_walls(
    name: str,
    footprint: list[tuple[float, float]],
    ground_y: float,
    height: float,
) -> Mesh | None:
    """Build quad walls for every edge of the footprint polygon."""
    if len(footprint) < 2:
        return None

    verts: list[list[float]] = []
    uvs: list[list[float]] = []
    indices: list[int] = []
    n = len(footprint)
    uv_x = 0.0

    for i in range(n):
        x0, z0 = footprint[i]
        x1, z1 = footprint[(i + 1) % n]
        seg_len = math.sqrt((x1 - x0) ** 2 + (z1 - z0) ** 2)
        uv_x_next = uv_x + seg_len / max(height, 0.1)

        v = len(verts)
        verts += [
            [x0, ground_y,          z0],
            [x1, ground_y,          z1],
            [x1, ground_y + height, z1],
            [x0, ground_y + height, z0],
        ]
        uvs += [
            [uv_x,      1.0],
            [uv_x_next, 1.0],
            [uv_x_next, 0.0],
            [uv_x,      0.0],
        ]
        # Front + back faces
        indices += [v, v + 1, v + 2, v, v + 2, v + 3]
        indices += [v + 2, v + 1, v, v + 3, v + 2, v]
        uv_x = uv_x_next

    if not verts:
        return None

    return make_mesh(name, verts, indices, uvs, material_name="BUILDING_WALL", ac_surface="1WALL")


def _make_roof(
    name: str,
    footprint: list[tuple[float, float]],
    roof_y: float,
) -> Mesh | None:
    """Build a flat roof using fan triangulation from the centroid."""
    if len(footprint) < 3:
        return None

    cx = sum(p[0] for p in footprint) / len(footprint)
    cz = sum(p[1] for p in footprint) / len(footprint)

    verts: list[list[float]] = [[cx, roof_y, cz]]
    uvs: list[list[float]] = [[0.5, 0.5]]

    for x, z in footprint:
        verts.append([x, roof_y, z])
        uvs.append([(x - cx) / 20.0 + 0.5, (z - cz) / 20.0 + 0.5])

    indices: list[int] = []
    n = len(footprint)
    for i in range(n):
        a = 1 + i
        b = 1 + (i + 1) % n
        indices += [0, a, b, b, a, 0]

    if not indices:
        return None

    return make_mesh(name, verts, indices, uvs, material_name="BUILDING_ROOF", ac_surface="1WALL")
