"""Road sign mesh generation from OSM traffic sign data."""
from __future__ import annotations

import math

import numpy as np

from .elevation import ElevationMap
from .location import TrackArea
from .mesh import Mesh, make_mesh
from .osm_fetcher import OSMNode


SIGN_POST_HEIGHT = 2.2   # meters above ground
SIGN_POST_RADIUS = 0.05  # meters
SIGN_SIZE = 0.5          # meters (sign face size)


def build_sign_meshes(
    traffic_signs: list[OSMNode],
    area: TrackArea,
    elevation: ElevationMap,
    progress_cb=None,
) -> list[Mesh]:
    """
    Generate 3D sign meshes from OSM traffic sign nodes.

    Each sign gets a vertical post + face geometry. Different sign types
    get different face shapes (octagon for stop, triangle for give-way, etc.)

    Returns list of Mesh objects.
    """
    if progress_cb:
        progress_cb(f"Placing {len(traffic_signs)} road signs...")

    meshes: list[Mesh] = []
    for i, node in enumerate(traffic_signs):
        x, z = area.to_local(node.lat, node.lon)
        y = elevation.get_elevation(node.lat, node.lon)
        sign_type = _classify_sign(node)
        sign_meshes = _make_sign(i, x, y, z, sign_type)
        meshes.extend(sign_meshes)

    return meshes


def _classify_sign(node: OSMNode) -> str:
    """Classify sign type from OSM tags."""
    tags = node.tags
    if tags.get("highway") == "stop":
        return "stop"
    if tags.get("highway") == "give_way":
        return "give_way"
    if tags.get("highway") == "traffic_signals":
        return "traffic_light"
    traffic_sign = tags.get("traffic_sign", "")
    if "stop" in traffic_sign.lower():
        return "stop"
    if "give_way" in traffic_sign.lower() or "yield" in traffic_sign.lower():
        return "give_way"
    if "speed" in traffic_sign.lower():
        return "speed_limit"
    return "generic"


def _make_sign(
    index: int, x: float, y: float, z: float, sign_type: str
) -> list[Mesh]:
    """Create sign post + face mesh(es) for a single sign."""
    meshes = []

    # Vertical post (thin rectangular box)
    post = _make_post(f"sign_post_{index}", x, y, z)
    meshes.append(post)

    # Sign face at top of post
    face_y = y + SIGN_POST_HEIGHT - SIGN_SIZE / 2
    face = _make_sign_face(f"sign_face_{sign_type}_{index}", x, face_y, z, sign_type)
    meshes.append(face)

    return meshes


def _make_post(name: str, x: float, y: float, z: float) -> Mesh:
    """Create a simple vertical cylinder post as a thin rectangular prism."""
    r = SIGN_POST_RADIUS
    h = SIGN_POST_HEIGHT

    # 4-sided post
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

    indices = [
        0, 1, 5,  0, 5, 4,  # front
        1, 2, 6,  1, 6, 5,  # right
        2, 3, 7,  2, 7, 6,  # back
        3, 0, 4,  3, 4, 7,  # left
        4, 5, 6,  4, 6, 7,  # top
    ]

    return make_mesh(name, verts, indices, uvs, material_name="SIGN_POST", ac_surface="1ROAD")


def _make_sign_face(
    name: str, x: float, y: float, z: float, sign_type: str
) -> Mesh:
    """Create a sign face billboard facing +Z direction."""
    s = SIGN_SIZE / 2

    # Simple quad facing +Z
    verts = [
        [x - s, y - s, z],
        [x + s, y - s, z],
        [x + s, y + s, z],
        [x - s, y + s, z],
    ]

    uvs = [
        [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0],
    ]

    indices = [0, 1, 2, 0, 2, 3, 2, 1, 0, 3, 2, 0]  # Both sides

    # Material name based on sign type for texture mapping
    mat_name = {
        "stop": "SIGN_STOP",
        "give_way": "SIGN_GIVE_WAY",
        "traffic_light": "SIGN_TRAFFIC_LIGHT",
        "speed_limit": "SIGN_SPEED",
        "generic": "SIGN_GENERIC",
    }.get(sign_type, "SIGN_GENERIC")

    return make_mesh(name, verts, indices, uvs, material_name=mat_name, ac_surface="1ROAD")
