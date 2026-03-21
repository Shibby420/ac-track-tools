"""Core mesh data structures shared across all geometry builders."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Mesh:
    """A single 3D mesh with per-vertex data and triangle indices."""

    name: str
    vertices: np.ndarray  # shape (N, 3) float32 - XYZ positions
    normals: np.ndarray   # shape (N, 3) float32 - normalized normals
    uvs: np.ndarray       # shape (N, 2) float32 - UV coordinates
    tangents: np.ndarray  # shape (N, 3) float32 - tangent vectors
    indices: np.ndarray   # shape (M,) uint32 - triangle indices (M divisible by 3)
    material_name: str = "ROAD"
    ac_surface: str = "1ROAD"  # AC surface prefix for naming convention


def compute_normals(vertices: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Compute smooth per-vertex normals from triangle data."""
    normals = np.zeros_like(vertices)
    v0 = vertices[indices[0::3]]
    v1 = vertices[indices[1::3]]
    v2 = vertices[indices[2::3]]

    face_normals = np.cross(v1 - v0, v2 - v0)
    # Normalize face normals
    lengths = np.linalg.norm(face_normals, axis=1, keepdims=True)
    lengths = np.where(lengths == 0, 1, lengths)
    face_normals /= lengths

    # Accumulate face normals to vertices
    np.add.at(normals, indices[0::3], face_normals)
    np.add.at(normals, indices[1::3], face_normals)
    np.add.at(normals, indices[2::3], face_normals)

    # Normalize per-vertex
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths = np.where(lengths == 0, 1, lengths)
    normals /= lengths

    return normals.astype(np.float32)


def compute_tangents(
    vertices: np.ndarray,
    normals: np.ndarray,
    uvs: np.ndarray,
    indices: np.ndarray,
) -> np.ndarray:
    """Compute per-vertex tangents using UV-based method."""
    tangents = np.zeros_like(vertices)

    i0, i1, i2 = indices[0::3], indices[1::3], indices[2::3]
    v0, v1, v2 = vertices[i0], vertices[i1], vertices[i2]
    uv0, uv1, uv2 = uvs[i0], uvs[i1], uvs[i2]

    dp1 = v1 - v0
    dp2 = v2 - v0
    duv1 = uv1 - uv0
    duv2 = uv2 - uv0

    det = duv1[:, 0] * duv2[:, 1] - duv1[:, 1] * duv2[:, 0]
    det = np.where(det == 0, 1e-8, det)

    face_tangents = (dp1 * duv2[:, 1:2] - dp2 * duv1[:, 1:2]) / det[:, np.newaxis]

    np.add.at(tangents, i0, face_tangents)
    np.add.at(tangents, i1, face_tangents)
    np.add.at(tangents, i2, face_tangents)

    # Gram-Schmidt orthogonalize against normals
    dot = np.sum(tangents * normals, axis=1, keepdims=True)
    tangents = tangents - dot * normals

    lengths = np.linalg.norm(tangents, axis=1, keepdims=True)
    lengths = np.where(lengths == 0, 1, lengths)
    tangents /= lengths

    return tangents.astype(np.float32)


def make_mesh(
    name: str,
    vertices: np.ndarray,
    indices: np.ndarray,
    uvs: np.ndarray | None = None,
    material_name: str = "ROAD",
    ac_surface: str = "1ROAD",
) -> Mesh:
    """Build a Mesh with computed normals and tangents."""
    verts = np.array(vertices, dtype=np.float32)
    idxs = np.array(indices, dtype=np.uint32)

    if uvs is None:
        uvs_arr = np.zeros((len(verts), 2), dtype=np.float32)
    else:
        uvs_arr = np.array(uvs, dtype=np.float32)

    normals = compute_normals(verts, idxs)
    tangents = compute_tangents(verts, normals, uvs_arr, idxs)

    return Mesh(
        name=name,
        vertices=verts,
        normals=normals,
        uvs=uvs_arr,
        tangents=tangents,
        indices=idxs,
        material_name=material_name,
        ac_surface=ac_surface,
    )
