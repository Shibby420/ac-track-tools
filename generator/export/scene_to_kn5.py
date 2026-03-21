"""Convert ACScene to KN5 data structures and export."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

import sys
from pathlib import Path

_GEN_ROOT = str(Path(__file__).parent.parent)
if _GEN_ROOT not in sys.path:
    sys.path.insert(0, _GEN_ROOT)

from core.mesh import Mesh  # type: ignore
from core.scene import ACScene  # type: ignore
from export.kn5_writer import (  # type: ignore
    KN5ContainerNode,
    KN5Material,
    KN5MeshNode,
    KN5ShaderProperty,
    KN5Texture,
    export_kn5,
)


# Default solid-color textures for different material types
MATERIAL_COLORS: dict[str, tuple[int, int, int]] = {
    "ROAD_primary": (80, 80, 85),
    "ROAD_secondary": (90, 88, 85),
    "ROAD_local": (95, 93, 90),
    "GRASS": (60, 100, 50),
    "TREE": (40, 90, 40),
    "SIGN_STOP": (220, 30, 30),
    "SIGN_GIVE_WAY": (200, 60, 20),
    "SIGN_TRAFFIC_LIGHT": (50, 50, 50),
    "SIGN_SPEED": (240, 240, 240),
    "SIGN_GENERIC": (180, 180, 100),
    "SIGN_POST": (150, 150, 150),
}


def convert_scene_to_kn5(scene: ACScene, output_dir: str) -> dict:
    """
    Convert ACScene meshes to KN5 format and export.

    Generates solid-color textures for each material type.

    Returns dict with 'status', 'warnings', 'filepath'.
    """
    track_filename = _sanitize_name(scene.track_name)
    kn5_path = str(Path(output_dir) / f"{track_filename}.kn5")

    # Build material and texture lists
    material_names: list[str] = _collect_material_names(scene.meshes)
    textures = _build_textures(material_names)
    materials = _build_materials(material_names)

    # Build material name → index map
    mat_index: dict[str, int] = {m.name: i for i, m in enumerate(materials)}

    # Build KN5 node hierarchy
    root = KN5ContainerNode(name="TrackRoot")
    for mesh in scene.meshes:
        kn5_node = _mesh_to_kn5_node(mesh, mat_index)
        root.children.append(kn5_node)

    # Export
    result = export_kn5(kn5_path, textures, materials, root)
    result["filepath"] = kn5_path
    return result


def _collect_material_names(meshes: list[Mesh]) -> list[str]:
    """Collect unique material names from all meshes."""
    seen: set[str] = set()
    names: list[str] = []
    for mesh in meshes:
        if mesh.material_name not in seen:
            seen.add(mesh.material_name)
            names.append(mesh.material_name)
    return names


def _build_textures(material_names: list[str]) -> list[KN5Texture]:
    """Build 1x1 pixel PNG textures for each material."""
    textures: list[KN5Texture] = []
    seen: set[str] = set()

    for mat_name in material_names:
        tex_name = f"{mat_name}_diffuse.png"
        if tex_name in seen:
            continue
        seen.add(tex_name)

        color = MATERIAL_COLORS.get(mat_name, (150, 150, 150))
        png_data = _make_solid_png(color)
        textures.append(KN5Texture(name=tex_name, data=png_data))

    return textures


def _build_materials(material_names: list[str]) -> list[KN5Material]:
    """Build KN5 materials for each material name."""
    materials: list[KN5Material] = []

    for mat_name in material_names:
        tex_name = f"{mat_name}_diffuse.png"
        is_tree = mat_name == "TREE"

        shader = "ksTree" if is_tree else "ksPerPixel"

        props = [
            KN5ShaderProperty("ksDiffuse", value_a=0.6),
            KN5ShaderProperty("ksAmbient", value_a=0.4),
            KN5ShaderProperty("ksSpecular", value_a=0.1),
            KN5ShaderProperty("ksSpecularEXP", value_a=20.0),
        ]

        mat = KN5Material(
            name=mat_name,
            shader=shader,
            alpha_blend=1 if is_tree else 0,
            alpha_tested=is_tree,
            depth_mode=0,
            properties=props,
            textures={"txDiffuse": tex_name},
        )
        materials.append(mat)

    return materials


def _mesh_to_kn5_node(mesh: Mesh, mat_index: dict[str, int]) -> KN5MeshNode:
    """Convert a Mesh to a KN5MeshNode."""
    mid = mat_index.get(mesh.material_name, 0)
    return KN5MeshNode(
        name=mesh.name,
        vertices=mesh.vertices,
        normals=mesh.normals,
        uvs=mesh.uvs,
        tangents=mesh.tangents,
        indices=mesh.indices,
        material_id=mid,
        cast_shadows=True,
        visible=True,
        transparent=False,
        renderable=True,
        lod_in=0.0,
        lod_out=10000.0,
        layer=0,
    )


def _make_solid_png(color: tuple[int, int, int], size: int = 4) -> bytes:
    """Create a tiny solid-color PNG image and return its bytes."""
    img = Image.new("RGB", (size, size), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _sanitize_name(name: str) -> str:
    """Sanitize name for use as filename."""
    result = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return result.strip("_") or "track"
