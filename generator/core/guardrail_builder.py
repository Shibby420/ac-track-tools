"""Guardrail mesh generation along road edges for motorways and primary roads."""
from __future__ import annotations

import math

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh
from .osm_fetcher import OSMWay, get_road_width

# Road types that get guardrails
GUARDRAIL_HIGHWAY_TYPES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
}

BEAM_HEIGHT = 0.72       # height of beam center above ground (m)
BEAM_THICKNESS = 0.07    # beam vertical thickness (m)
BEAM_DEPTH = 0.18        # beam horizontal depth (W-profile approximation)
POST_HEIGHT = 0.85       # total post height (m)
POST_WIDTH = 0.10        # post cross-section width (m)
POST_INTERVAL = 4.0      # meters between posts
ROAD_EDGE_OFFSET = 0.5   # meters outside road edge


def build_guardrail_meshes(
    roads: list[OSMWay],
    area: TrackArea,
    elevation: ElevationMap,
    progress_cb=None,
) -> list[Mesh]:
    """
    Generate guardrail meshes along both edges of qualifying roads.

    Produces W-beam guardrails with posts every POST_INTERVAL meters.
    """
    if progress_cb:
        progress_cb("Building guardrails...")

    meshes: list[Mesh] = []

    for way in roads:
        if way.tags.get("highway", "") not in GUARDRAIL_HIGHWAY_TYPES:
            continue
        if len(way.nodes) < 2:
            continue

        width = get_road_width(way)
        half_w = width / 2.0 + ROAD_EDGE_OFFSET

        centerline: list[tuple[float, float, float]] = []
        for node in way.nodes:
            x, z = area.to_local(node.lat, node.lon)
            y = elevation.get_elevation(node.lat, node.lon)
            centerline.append((x, y, z))

        for side, label in [(-1, "L"), (1, "R")]:
            edge = _offset_centerline(centerline, half_w * side)
            beam = _build_beam(f"GUARDRAIL_{way.id}_{label}_beam", edge)
            posts = _build_posts(f"GUARDRAIL_{way.id}_{label}_post", edge)
            if beam:
                meshes.append(beam)
            meshes.extend(posts)

    if progress_cb:
        progress_cb(f"  Built {len(meshes)} guardrail mesh(es)")

    return meshes


def _offset_centerline(
    centerline: list[tuple[float, float, float]],
    offset: float,
) -> list[tuple[float, float, float]]:
    """Offset centerline laterally by offset meters (positive = right)."""
    result = []
    n = len(centerline)

    for i, (cx, cy, cz) in enumerate(centerline):
        if i == 0:
            dx, dz = centerline[1][0] - cx, centerline[1][2] - cz
        elif i == n - 1:
            dx, dz = cx - centerline[-2][0], cz - centerline[-2][2]
        else:
            dx = centerline[i + 1][0] - centerline[i - 1][0]
            dz = centerline[i + 1][2] - centerline[i - 1][2]

        ln = math.sqrt(dx * dx + dz * dz) or 1e-6
        # Perpendicular (right = +offset direction)
        nx, nz = dz / ln, -dx / ln
        result.append((cx + nx * offset, cy, cz + nz * offset))

    return result


def _build_beam(
    name: str,
    edge_pts: list[tuple[float, float, float]],
) -> Mesh | None:
    """Build a continuous horizontal beam strip along the edge."""
    if len(edge_pts) < 2:
        return None

    h_lo = BEAM_HEIGHT - BEAM_THICKNESS / 2
    h_hi = BEAM_HEIGHT + BEAM_THICKNESS / 2

    verts: list[list[float]] = []
    uvs: list[list[float]] = []
    indices: list[int] = []
    dist = 0.0

    for i, (x, y, z) in enumerate(edge_pts):
        uv_v = dist * 0.05
        verts.append([x, y + h_lo, z])
        verts.append([x, y + h_hi, z])
        uvs.append([0.0, uv_v])
        uvs.append([1.0, uv_v])

        if i > 0:
            px, py, pz = edge_pts[i - 1]
            dist += math.sqrt((x - px) ** 2 + (z - pz) ** 2)
            v0 = (i - 1) * 2
            v1 = v0 + 1
            v2 = i * 2
            v3 = v2 + 1
            # Front face + back face
            indices.extend([v0, v2, v1, v1, v2, v3])
            indices.extend([v1, v2, v0, v3, v2, v1])

    if not verts or not indices:
        return None

    return make_mesh(name, verts, indices, uvs, material_name="GUARDRAIL", ac_surface="1WALL")


def _build_posts(
    name: str,
    edge_pts: list[tuple[float, float, float]],
) -> list[Mesh]:
    """Place rectangular posts along the edge at POST_INTERVAL spacing."""
    meshes: list[Mesh] = []
    dist_acc = 0.0
    last_post_dist = -POST_INTERVAL  # ensure first post is placed right away

    for i, (x, y, z) in enumerate(edge_pts):
        if i > 0:
            px, py, pz = edge_pts[i - 1]
            dist_acc += math.sqrt((x - px) ** 2 + (z - pz) ** 2)

        if dist_acc - last_post_dist >= POST_INTERVAL:
            last_post_dist = dist_acc
            r = POST_WIDTH / 2.0
            h = POST_HEIGHT

            verts = [
                [x - r, y,     z - r],
                [x + r, y,     z - r],
                [x + r, y,     z + r],
                [x - r, y,     z + r],
                [x - r, y + h, z - r],
                [x + r, y + h, z - r],
                [x + r, y + h, z + r],
                [x - r, y + h, z + r],
            ]
            uvs = [
                [0.0, 1.0], [1.0, 1.0], [1.0, 1.0], [0.0, 1.0],
                [0.0, 0.0], [1.0, 0.0], [1.0, 0.0], [0.0, 0.0],
            ]
            idx = [
                0, 1, 5, 0, 5, 4,  # front
                1, 2, 6, 1, 6, 5,  # right
                2, 3, 7, 2, 7, 6,  # back
                3, 0, 4, 3, 4, 7,  # left
                4, 5, 6, 4, 6, 7,  # top
            ]
            meshes.append(make_mesh(
                f"{name}_{i}",
                verts, idx, uvs,
                material_name="GUARDRAIL",
                ac_surface="1WALL",
            ))

    return meshes
