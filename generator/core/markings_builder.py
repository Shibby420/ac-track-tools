"""Road marking mesh generation: edge lines, center lines, dashed dividers."""
from __future__ import annotations

import math

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh
from .osm_fetcher import OSMWay, get_road_width

MARKING_Y_OFFSET = 0.025   # metres above road to avoid z-fighting
EDGE_LINE_WIDTH = 0.20     # metres
CENTER_LINE_WIDTH = 0.12   # metres
DASH_LENGTH = 3.0          # metres per dash segment
GAP_LENGTH = 3.0           # metres per gap between dashes
DOUBLE_LINE_SEP = 0.22     # metres between double yellow lines


def build_marking_meshes(
    roads: list[OSMWay],
    area: TrackArea,
    elevation: ElevationMap,
    progress_cb=None,
) -> list[Mesh]:
    """
    Generate road marking meshes for all roads.

    White solid edge lines on both sides.
    Yellow double-solid center for divided highways.
    Yellow dashed center for two-way roads.
    White solid center for one-way roads.
    """
    if progress_cb:
        progress_cb("Building road markings...")

    meshes: list[Mesh] = []

    for way in roads:
        if len(way.nodes) < 2:
            continue

        highway = way.tags.get("highway", "residential")
        width = get_road_width(way)
        half_w = width / 2.0
        oneway = way.tags.get("oneway") in ("yes", "1", "true")

        # Build centerline with Y offset
        cl: list[tuple[float, float, float]] = []
        for node in way.nodes:
            x, z = area.to_local(node.lat, node.lon)
            y = elevation.get_elevation(node.lat, node.lon) + MARKING_Y_OFFSET
            cl.append((x, y, z))

        # ── Edge lines (white solid) ─────────────────────────────────────
        for side_off in [
            -(half_w - EDGE_LINE_WIDTH * 0.5),
             (half_w - EDGE_LINE_WIDTH * 0.5),
        ]:
            pts = _offset_cl(cl, side_off)
            m = _solid_strip(f"MARK_EDGE_{way.id}_{side_off:.2f}", pts, EDGE_LINE_WIDTH, "MARKING_WHITE")
            if m:
                meshes.append(m)

        # ── Center markings ──────────────────────────────────────────────
        if highway in ("motorway", "trunk", "primary", "secondary"):
            # Double solid yellow
            for off in (-DOUBLE_LINE_SEP / 2, DOUBLE_LINE_SEP / 2):
                pts = _offset_cl(cl, off)
                m = _solid_strip(f"MARK_CTR_{way.id}_{off:.3f}", pts, CENTER_LINE_WIDTH, "MARKING_YELLOW")
                if m:
                    meshes.append(m)
        elif oneway:
            # Solid white
            m = _solid_strip(f"MARK_CTR_{way.id}", cl, CENTER_LINE_WIDTH, "MARKING_WHITE")
            if m:
                meshes.append(m)
        else:
            # Dashed yellow
            meshes.extend(
                _dashed_strip(f"MARK_CTR_{way.id}", cl, CENTER_LINE_WIDTH, "MARKING_YELLOW")
            )

    if progress_cb:
        progress_cb(f"  Built {len(meshes)} marking mesh(es)")

    return meshes


# ── Helpers ──────────────────────────────────────────────────────────────────

def _offset_cl(
    pts: list[tuple[float, float, float]],
    offset: float,
) -> list[tuple[float, float, float]]:
    """Laterally offset a polyline by `offset` metres (positive = right)."""
    result: list[tuple[float, float, float]] = []
    n = len(pts)

    for i, (cx, cy, cz) in enumerate(pts):
        if i == 0:
            dx, dz = pts[1][0] - cx, pts[1][2] - cz
        elif i == n - 1:
            dx, dz = cx - pts[-2][0], cz - pts[-2][2]
        else:
            dx = pts[i + 1][0] - pts[i - 1][0]
            dz = pts[i + 1][2] - pts[i - 1][2]

        ln = math.sqrt(dx * dx + dz * dz) or 1e-6
        nx, nz = dz / ln, -dx / ln  # right-hand perpendicular
        result.append((cx + nx * offset, cy, cz + nz * offset))

    return result


def _solid_strip(
    name: str,
    cl: list[tuple[float, float, float]],
    width: float,
    material: str,
) -> Mesh | None:
    """Build a solid ribbon strip along the centreline."""
    if len(cl) < 2:
        return None

    half_w = width / 2.0
    verts: list[list[float]] = []
    uvs: list[list[float]] = []
    indices: list[int] = []
    dist = 0.0
    n = len(cl)

    for i, (cx, cy, cz) in enumerate(cl):
        if i == 0:
            dx, dz = cl[1][0] - cx, cl[1][2] - cz
        elif i == n - 1:
            dx, dz = cx - cl[-2][0], cz - cl[-2][2]
        else:
            dx = cl[i + 1][0] - cl[i - 1][0]
            dz = cl[i + 1][2] - cl[i - 1][2]

        ln = math.sqrt(dx * dx + dz * dz) or 1e-6
        px, pz = dz / ln, -dx / ln

        v = len(verts)
        verts.append([cx - px * half_w, cy, cz - pz * half_w])
        verts.append([cx + px * half_w, cy, cz + pz * half_w])
        uvs.append([0.0, dist])
        uvs.append([1.0, dist])

        if i > 0:
            seg = math.sqrt((cx - cl[i - 1][0]) ** 2 + (cz - cl[i - 1][2]) ** 2)
            dist += seg
            v0, v1, v2, v3 = v - 2, v - 1, v, v + 1
            indices.extend([v0, v2, v1, v1, v2, v3])
            indices.extend([v1, v2, v0, v3, v2, v1])

    if not verts or len(indices) < 3:
        return None

    return make_mesh(name, verts, indices, uvs, material_name=material, ac_surface="1ROAD")


def _dashed_strip(
    name: str,
    cl: list[tuple[float, float, float]],
    width: float,
    material: str,
) -> list[Mesh]:
    """Build a dashed line as individual solid quad segments."""
    meshes: list[Mesh] = []
    n = len(cl)
    if n < 2:
        return meshes

    # Cumulative distances along centreline
    dists: list[float] = [0.0]
    for i in range(1, n):
        dx = cl[i][0] - cl[i - 1][0]
        dz = cl[i][2] - cl[i - 1][2]
        dists.append(dists[-1] + math.sqrt(dx * dx + dz * dz))

    total = dists[-1]
    cycle = DASH_LENGTH + GAP_LENGTH
    dash_idx = 0
    t = 0.0

    while t < total:
        t_end = min(t + DASH_LENGTH, total)

        # Collect centreline points that fall within [t, t_end]
        dash_pts: list[tuple[float, float, float]] = []
        for i, d in enumerate(dists):
            if d >= t - 1e-3 and d <= t_end + 1e-3:
                dash_pts.append(cl[i])

        if len(dash_pts) >= 2:
            m = _solid_strip(f"{name}_d{dash_idx}", dash_pts, width, material)
            if m:
                meshes.append(m)

        dash_idx += 1
        t += cycle

    return meshes
