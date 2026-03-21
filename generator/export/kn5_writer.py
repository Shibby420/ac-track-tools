"""
Standalone KN5 binary format writer.

Adapted from lib/kn5/kn5_writer.py — pure Python, no Blender dependency.
Implements the KN5 format: header + textures + materials + node hierarchy.
"""
from __future__ import annotations

import io
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

import numpy as np

KN5_HEADER = b"sc6969"
KN5_VERSION = 5
MAX_VERTICES = 65536

# Node type IDs
NODE_TRANSFORM = 1
NODE_MESH = 2
NODE_SKINNED_MESH = 3

# Alpha blend modes
ALPHA_OPAQUE = 0
ALPHA_BLEND = 1
ALPHA_COVERAGE = 2

# Depth modes
DEPTH_NORMAL = 0
DEPTH_NO_WRITE = 1
DEPTH_OFF = 2

ENCODING = "utf-8"


# ─────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────

@dataclass
class KN5Texture:
    name: str
    data: bytes  # PNG or DDS bytes


@dataclass
class KN5ShaderProperty:
    name: str
    value_a: float = 0.0
    value_b: tuple[float, float] = (0.0, 0.0)
    value_c: tuple[float, float, float] = (0.0, 0.0, 0.0)
    value_d: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class KN5Material:
    name: str
    shader: str = "ksPerPixel"
    alpha_blend: int = ALPHA_OPAQUE
    alpha_tested: bool = False
    depth_mode: int = DEPTH_NORMAL
    properties: list[KN5ShaderProperty] = field(default_factory=list)
    textures: dict[str, str] = field(default_factory=dict)  # slot_name -> texture_name


@dataclass
class KN5MeshNode:
    name: str
    vertices: np.ndarray   # (N, 3) float32
    normals: np.ndarray    # (N, 3) float32
    uvs: np.ndarray        # (N, 2) float32
    tangents: np.ndarray   # (N, 3) float32
    indices: np.ndarray    # (M,) uint32
    material_id: int = 0
    cast_shadows: bool = True
    visible: bool = True
    transparent: bool = False
    renderable: bool = True
    lod_in: float = 0.0
    lod_out: float = 10000.0
    layer: int = 0


@dataclass
class KN5ContainerNode:
    name: str
    children: list = field(default_factory=list)  # KN5MeshNode | KN5ContainerNode
    matrix: list[float] = field(default_factory=lambda: [
        1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1
    ])


# ─────────────────────────────────────────────────
# Binary writer
# ─────────────────────────────────────────────────

class BinaryWriter:
    """Low-level binary format writer."""

    def __init__(self, file: BinaryIO):
        self.f = file

    def write_string(self, s: str) -> None:
        b = s.encode(ENCODING)
        self.write_uint(len(b))
        self.f.write(b)

    def write_blob(self, data: bytes) -> None:
        self.write_uint(len(data))
        self.f.write(data)

    def write_uint(self, v: int) -> None:
        self.f.write(struct.pack("I", v))

    def write_int(self, v: int) -> None:
        self.f.write(struct.pack("i", v))

    def write_ushort(self, v: int) -> None:
        self.f.write(struct.pack("H", v))

    def write_byte(self, v: int) -> None:
        self.f.write(struct.pack("B", v))

    def write_bool(self, v: bool) -> None:
        self.f.write(struct.pack("?", v))

    def write_float(self, v: float) -> None:
        self.f.write(struct.pack("f", v))

    def write_vec2(self, v: tuple) -> None:
        self.f.write(struct.pack("2f", *v))

    def write_vec3(self, v: tuple) -> None:
        self.f.write(struct.pack("3f", *v))

    def write_vec4(self, v: tuple) -> None:
        self.f.write(struct.pack("4f", *v))

    def write_matrix(self, m: list[float]) -> None:
        """Write 4x4 matrix in column-major order from row-major list."""
        m4 = [m[i*4:i*4+4] for i in range(4)]
        for col in range(4):
            for row in range(4):
                self.write_float(m4[row][col])


# ─────────────────────────────────────────────────
# KN5 file writer
# ─────────────────────────────────────────────────

class KN5Writer:
    """Writes a complete KN5 file from provided scene data."""

    def __init__(self, file: BinaryIO):
        self.f = file
        self.bw = BinaryWriter(file)

    def write(
        self,
        textures: list[KN5Texture],
        materials: list[KN5Material],
        root: KN5ContainerNode,
    ) -> list[str]:
        """
        Write complete KN5 file.

        Returns list of warning messages.
        """
        warnings: list[str] = []

        # Header
        self.f.write(KN5_HEADER)
        self.bw.write_uint(KN5_VERSION)

        # Textures
        self.bw.write_int(len(textures))
        for tex in textures:
            self._write_texture(tex)

        # Materials
        self.bw.write_int(len(materials))
        for mat in materials:
            self._write_material(mat)

        # Node hierarchy
        self._write_root(root, warnings)

        return warnings

    def _write_texture(self, tex: KN5Texture) -> None:
        self.bw.write_int(1)  # active
        self.bw.write_string(tex.name)
        self.bw.write_blob(tex.data)

    def _write_material(self, mat: KN5Material) -> None:
        self.bw.write_string(mat.name)
        self.bw.write_string(mat.shader)
        self.bw.write_byte(mat.alpha_blend)
        self.bw.write_bool(mat.alpha_tested)
        self.bw.write_int(mat.depth_mode)

        # Shader properties
        self.bw.write_uint(len(mat.properties))
        for prop in mat.properties:
            self.bw.write_string(prop.name)
            self.bw.write_float(prop.value_a)
            self.bw.write_vec2(prop.value_b)
            self.bw.write_vec3(prop.value_c)
            self.bw.write_vec4(prop.value_d)

        # Texture slots
        self.bw.write_uint(len(mat.textures))
        for slot_idx, (slot_name, tex_name) in enumerate(mat.textures.items()):
            self.bw.write_string(slot_name)
            self.bw.write_uint(slot_idx)
            self.bw.write_string(tex_name)

    def _write_root(self, root: KN5ContainerNode, warnings: list[str]) -> None:
        """Write root container node."""
        self.bw.write_uint(NODE_TRANSFORM)
        self.bw.write_string(root.name)
        self.bw.write_uint(len(root.children))
        self.bw.write_bool(True)
        self.bw.write_matrix(root.matrix)

        for child in root.children:
            self._write_node(child, warnings)

    def _write_node(self, node, warnings: list[str]) -> None:
        if isinstance(node, KN5ContainerNode):
            self._write_container(node, warnings)
        elif isinstance(node, KN5MeshNode):
            self._write_mesh(node, warnings)

    def _write_container(self, node: KN5ContainerNode, warnings: list[str]) -> None:
        self.bw.write_uint(NODE_TRANSFORM)
        self.bw.write_string(node.name)
        self.bw.write_uint(len(node.children))
        self.bw.write_bool(True)
        self.bw.write_matrix(node.matrix)
        for child in node.children:
            self._write_node(child, warnings)

    def _write_mesh(self, node: KN5MeshNode, warnings: list[str]) -> None:
        if len(node.vertices) > MAX_VERTICES:
            warnings.append(
                f"Mesh '{node.name}' has {len(node.vertices)} vertices (max {MAX_VERTICES})"
            )

        self.bw.write_uint(NODE_MESH)
        self.bw.write_string(node.name)
        self.bw.write_uint(0)  # child count
        self.bw.write_bool(True)
        self.bw.write_bool(node.cast_shadows)
        self.bw.write_bool(node.visible)
        self.bw.write_bool(node.transparent)

        # Vertices
        vcount = len(node.vertices)
        self.bw.write_uint(vcount)
        for i in range(vcount):
            # Convert Blender Z-up to AC Y-up: (X, Y, Z) → (X, Z, -Y)
            vx, vy, vz = float(node.vertices[i][0]), float(node.vertices[i][1]), float(node.vertices[i][2])
            self.bw.write_vec3((vx, vz, -vy))

            nx, ny, nz = float(node.normals[i][0]), float(node.normals[i][1]), float(node.normals[i][2])
            self.bw.write_vec3((nx, nz, -ny))

            self.bw.write_vec2((float(node.uvs[i][0]), float(node.uvs[i][1])))

            tx, ty, tz = float(node.tangents[i][0]), float(node.tangents[i][1]), float(node.tangents[i][2])
            self.bw.write_vec3((tx, tz, -ty))

        # Indices
        icount = len(node.indices)
        self.bw.write_uint(icount)
        for idx in node.indices:
            self.bw.write_ushort(int(idx))

        # Material ID
        self.bw.write_uint(node.material_id)

        # Node properties
        self.bw.write_uint(node.layer)
        self.bw.write_float(node.lod_in)
        self.bw.write_float(node.lod_out)

        # Bounding sphere
        self._write_bounding_sphere(node.vertices)

        self.bw.write_bool(node.renderable)

    def _write_bounding_sphere(self, vertices: np.ndarray) -> None:
        if len(vertices) == 0:
            self.bw.write_vec3((0.0, 0.0, 0.0))
            self.bw.write_float(0.0)
            return

        min_v = vertices.min(axis=0)
        max_v = vertices.max(axis=0)
        center = (min_v + max_v) / 2
        radius = float(np.linalg.norm(max_v - center)) * 2

        cx, cy, cz = float(center[0]), float(center[1]), float(center[2])
        self.bw.write_vec3((cx, cz, -cy))  # Y-up conversion
        self.bw.write_float(radius)


# ─────────────────────────────────────────────────
# Public export function
# ─────────────────────────────────────────────────

def export_kn5(
    filepath: str,
    textures: list[KN5Texture],
    materials: list[KN5Material],
    root: KN5ContainerNode,
) -> dict[str, object]:
    """
    Export scene data to a KN5 file.

    Args:
        filepath: Output .kn5 file path
        textures: List of KN5Texture
        materials: List of KN5Material
        root: Root KN5ContainerNode containing the scene hierarchy

    Returns:
        dict with 'status' ('success' or 'error') and 'warnings' list
    """
    warnings: list[str] = []
    output_file = None
    try:
        output_file = open(filepath, "wb")
        writer = KN5Writer(output_file)
        warnings = writer.write(textures, materials, root)
        return {"status": "success", "warnings": warnings}
    except Exception as e:
        import traceback
        warnings.append(f"KN5 export failed: {e}")
        warnings.append(traceback.format_exc())
        try:
            Path(filepath).unlink(missing_ok=True)
        except OSError:
            pass
        return {"status": "error", "warnings": warnings}
    finally:
        if output_file:
            output_file.close()
