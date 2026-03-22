"""Convert ACScene to KN5 data structures and export."""
from __future__ import annotations

import io
import random
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

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


# Fallback solid colours for materials that don't get a procedural texture
MATERIAL_COLORS: dict[str, tuple[int, int, int]] = {
    "ROAD_primary":       (72, 72, 76),
    "ROAD_secondary":     (80, 78, 75),
    "ROAD_local":         (88, 85, 82),
    "GRASS":              (62, 105, 52),
    "TREE":               (38, 88, 38),
    "SIGN_STOP":          (210, 25, 25),
    "SIGN_GIVE_WAY":      (195, 55, 15),
    "SIGN_TRAFFIC_LIGHT": (45, 45, 45),
    "SIGN_SPEED":         (235, 235, 235),
    "SIGN_GENERIC":       (175, 175, 95),
    "SIGN_POST":          (140, 140, 140),
    "GUARDRAIL":          (185, 185, 190),
    "BUILDING_WALL":      (195, 185, 165),
    "BUILDING_ROOF":      (90, 80, 75),
    "MARKING_WHITE":      (240, 240, 240),
    "MARKING_YELLOW":     (240, 200, 30),
}

# Materials that use a procedurally-generated texture rather than a solid colour
PROCEDURAL_MATERIALS = {
    "ROAD_primary", "ROAD_secondary", "ROAD_local",
    "GUARDRAIL",
    "BUILDING_WALL", "BUILDING_ROOF",
    "MARKING_WHITE", "MARKING_YELLOW",
}


def convert_scene_to_kn5(
    scene: ACScene,
    output_dir: str,
    satellite_texture: Optional[bytes] = None,
) -> dict:
    """
    Convert ACScene meshes to KN5 format and export.

    Args:
        scene: The assembled track scene.
        output_dir: Directory to write the .kn5 file into.
        satellite_texture: Optional PNG bytes for the terrain/grass texture.

    Returns:
        dict with 'status', 'warnings', 'filepath'.
    """
    track_filename = _sanitize_name(scene.track_name)
    kn5_path = str(Path(output_dir) / f"{track_filename}.kn5")

    material_names: list[str] = _collect_material_names(scene.meshes)
    textures = _build_textures(material_names, satellite_texture)
    materials = _build_materials(material_names)

    mat_index: dict[str, int] = {m.name: i for i, m in enumerate(materials)}

    root = KN5ContainerNode(name="TrackRoot")
    for mesh in scene.meshes:
        kn5_node = _mesh_to_kn5_node(mesh, mat_index)
        root.children.append(kn5_node)

    result = export_kn5(kn5_path, textures, materials, root)
    result["filepath"] = kn5_path
    return result


# ── Texture builders ──────────────────────────────────────────────────────────

def _collect_material_names(meshes: list[Mesh]) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for mesh in meshes:
        if mesh.material_name not in seen:
            seen.add(mesh.material_name)
            names.append(mesh.material_name)
    return names


def _build_textures(
    material_names: list[str],
    satellite_texture: Optional[bytes],
) -> list[KN5Texture]:
    textures: list[KN5Texture] = []
    seen: set[str] = set()

    for mat_name in material_names:
        tex_name = f"{mat_name}_diffuse.png"
        if tex_name in seen:
            continue
        seen.add(tex_name)

        if mat_name == "GRASS" and satellite_texture:
            # Use real satellite/map imagery for terrain
            png_data = satellite_texture
        elif mat_name in ("ROAD_primary", "ROAD_secondary", "ROAD_local"):
            png_data = _make_asphalt_texture()
        elif mat_name == "GUARDRAIL":
            png_data = _make_guardrail_texture()
        elif mat_name in ("BUILDING_WALL",):
            png_data = _make_wall_texture()
        elif mat_name == "BUILDING_ROOF":
            png_data = _make_roof_texture()
        elif mat_name == "MARKING_WHITE":
            png_data = _make_solid_png((240, 240, 240), 8)
        elif mat_name == "MARKING_YELLOW":
            png_data = _make_solid_png((240, 200, 30), 8)
        elif mat_name == "TREE":
            png_data = _make_tree_texture()
        else:
            color = MATERIAL_COLORS.get(mat_name, (150, 150, 150))
            png_data = _make_solid_png(color)

        textures.append(KN5Texture(name=tex_name, data=png_data))

    return textures


def _build_materials(material_names: list[str]) -> list[KN5Material]:
    materials: list[KN5Material] = []

    for mat_name in material_names:
        tex_name = f"{mat_name}_diffuse.png"
        is_tree = mat_name == "TREE"
        is_marking = mat_name in ("MARKING_WHITE", "MARKING_YELLOW")
        is_transparent = is_tree

        shader = "ksTree" if is_tree else "ksPerPixel"

        if is_marking:
            props = [
                KN5ShaderProperty("ksDiffuse",    value_a=0.95),
                KN5ShaderProperty("ksAmbient",    value_a=0.5),
                KN5ShaderProperty("ksSpecular",   value_a=0.05),
                KN5ShaderProperty("ksSpecularEXP", value_a=5.0),
            ]
        elif mat_name.startswith("ROAD_"):
            props = [
                KN5ShaderProperty("ksDiffuse",    value_a=0.65),
                KN5ShaderProperty("ksAmbient",    value_a=0.35),
                KN5ShaderProperty("ksSpecular",   value_a=0.15),
                KN5ShaderProperty("ksSpecularEXP", value_a=30.0),
            ]
        elif mat_name == "GUARDRAIL":
            props = [
                KN5ShaderProperty("ksDiffuse",    value_a=0.5),
                KN5ShaderProperty("ksAmbient",    value_a=0.4),
                KN5ShaderProperty("ksSpecular",   value_a=0.6),
                KN5ShaderProperty("ksSpecularEXP", value_a=60.0),
            ]
        elif mat_name in ("BUILDING_WALL", "BUILDING_ROOF"):
            props = [
                KN5ShaderProperty("ksDiffuse",    value_a=0.7),
                KN5ShaderProperty("ksAmbient",    value_a=0.4),
                KN5ShaderProperty("ksSpecular",   value_a=0.05),
                KN5ShaderProperty("ksSpecularEXP", value_a=10.0),
            ]
        else:
            props = [
                KN5ShaderProperty("ksDiffuse",    value_a=0.6),
                KN5ShaderProperty("ksAmbient",    value_a=0.4),
                KN5ShaderProperty("ksSpecular",   value_a=0.1),
                KN5ShaderProperty("ksSpecularEXP", value_a=20.0),
            ]

        mat = KN5Material(
            name=mat_name,
            shader=shader,
            alpha_blend=1 if is_transparent else 0,
            alpha_tested=is_transparent,
            depth_mode=0,
            properties=props,
            textures={"txDiffuse": tex_name},
        )
        materials.append(mat)

    return materials


def _mesh_to_kn5_node(mesh: Mesh, mat_index: dict[str, int]) -> KN5MeshNode:
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


# ── Procedural texture generators ────────────────────────────────────────────

def _make_solid_png(color: tuple[int, int, int], size: int = 4) -> bytes:
    """Create a tiny solid-colour PNG."""
    img = Image.new("RGB", (size, size), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_asphalt_texture(size: int = 256) -> bytes:
    """
    Generate a tileable asphalt texture: dark gray with subtle grain/noise.
    """
    rng = random.Random(42)
    base_color = (68, 68, 72)

    img = Image.new("RGB", (size, size), base_color)
    draw = ImageDraw.Draw(img)

    # Add aggregate grain (lighter/darker specks)
    for _ in range(size * size // 3):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        shade = rng.randint(-18, 18)
        c = tuple(max(0, min(255, base_color[i] + shade)) for i in range(3))
        draw.point((x, y), fill=c)

    # Slight blur for cohesion
    img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_guardrail_texture(size: int = 64) -> bytes:
    """Silver brushed-metal look for guardrails."""
    rng = random.Random(7)
    img = Image.new("RGB", (size, size), (175, 180, 185))
    draw = ImageDraw.Draw(img)

    # Horizontal brush streaks
    for y in range(size):
        shade = rng.randint(-20, 20)
        base = 178 + shade
        c = (
            max(0, min(255, base - 3)),
            max(0, min(255, base)),
            max(0, min(255, base + 5)),
        )
        draw.line([(0, y), (size - 1, y)], fill=c)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_wall_texture(size: int = 128) -> bytes:
    """Simple brick/render wall texture."""
    rng = random.Random(13)
    # Light plaster/render base
    img = Image.new("RGB", (size, size), (195, 185, 168))
    draw = ImageDraw.Draw(img)

    brick_h = size // 8
    brick_w = size // 4

    for row in range(9):
        y0 = row * brick_h
        offset = (brick_w // 2) if row % 2 else 0
        for col in range(-1, 6):
            x0 = col * brick_w + offset
            shade = rng.randint(-12, 12)
            base = (
                max(0, min(255, 190 + shade)),
                max(0, min(255, 178 + shade)),
                max(0, min(255, 158 + shade)),
            )
            draw.rectangle(
                [x0 + 1, y0 + 1, x0 + brick_w - 2, y0 + brick_h - 2],
                fill=base,
            )

    # Mortar lines already show through as the base colour
    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_roof_texture(size: int = 64) -> bytes:
    """Dark flat-roof texture."""
    rng = random.Random(99)
    img = Image.new("RGB", (size, size), (80, 72, 68))
    draw = ImageDraw.Draw(img)

    for _ in range(size * size // 4):
        x = rng.randint(0, size - 1)
        y = rng.randint(0, size - 1)
        shade = rng.randint(-10, 10)
        c = (max(0, min(255, 80 + shade)), max(0, min(255, 72 + shade)), max(0, min(255, 68 + shade)))
        draw.point((x, y), fill=c)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_tree_texture(size: int = 64) -> bytes:
    """
    Simple hand-crafted tree billboard sprite: circular canopy over trunk.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Trunk
    trunk_w = size // 8
    trunk_h = size // 3
    tx0 = size // 2 - trunk_w // 2
    tx1 = size // 2 + trunk_w // 2
    ty0 = size - trunk_h
    draw.rectangle([tx0, ty0, tx1, size - 1], fill=(100, 70, 40, 255))

    # Canopy layers (darker inside → lighter outside)
    for radius, shade in [(size // 2 - 2, (30, 80, 30)), (size // 3, (45, 110, 40)), (size // 4, (60, 130, 50))]:
        cx, cy = size // 2, size // 2 - size // 8
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=shade + (220,),
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _sanitize_name(name: str) -> str:
    result = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return result.strip("_") or "track"
