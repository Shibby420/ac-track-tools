"""AC track config file generation: surfaces.ini, lighting.ini, ui_track.json, etc."""
from __future__ import annotations

import json
import os
from pathlib import Path

import sys
from pathlib import Path

_GEN_ROOT = str(Path(__file__).parent.parent)
if _GEN_ROOT not in sys.path:
    sys.path.insert(0, _GEN_ROOT)

from core.scene import ACScene  # type: ignore


def write_all_configs(scene: ACScene, output_dir: str) -> list[str]:
    """
    Write all AC track config files to output_dir.

    Creates the complete folder structure required by Assetto Corsa
    Content Manager.

    Returns list of generated file paths.
    """
    created: list[str] = []
    track_dir = Path(output_dir)

    data_dir = track_dir / "data"
    ui_dir = track_dir / "ui"
    ext_dir = track_dir / "extension"

    for d in (track_dir, data_dir, ui_dir, ext_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ui_track.json
    path = ui_dir / "ui_track.json"
    _write_json(path, _build_ui_track(scene))
    created.append(str(path))

    # surfaces.ini
    path = data_dir / "surfaces.ini"
    _write_ini(path, _build_surfaces_ini())
    created.append(str(path))

    # lighting.ini
    path = data_dir / "lighting.ini"
    _write_ini(path, _build_lighting_ini())
    created.append(str(path))

    # audio_sources.ini (empty placeholder)
    path = data_dir / "audio_sources.ini"
    path.write_text("; No audio sources configured\n")
    created.append(str(path))

    # cameras.ini
    path = data_dir / "cameras.ini"
    _write_ini(path, _build_cameras_ini(scene))
    created.append(str(path))

    # models.ini
    path = track_dir / "models.ini"
    track_filename = _sanitize_name(scene.track_name)
    _write_ini(path, {"MODEL_0": {
        "FILE": f"{track_filename}.kn5",
        "POSITION": "0,0,0",
        "ROTATION": "0,0,0",
    }})
    created.append(str(path))

    # extension/ext_config.ini
    path = ext_dir / "ext_config.ini"
    _write_ini(path, _build_ext_config())
    created.append(str(path))

    return created


def _build_ui_track(scene: ACScene) -> dict:
    """Build ui_track.json content."""
    length_km = scene.track_length_m / 1000.0
    return {
        "name": scene.track_name,
        "description": f"Auto-generated from OpenStreetMap data for {scene.area.name}",
        "tags": ["generated", "openstreetmap", "ac-track-generator"],
        "geotags": [f"{scene.area.center_lat:.6f},{scene.area.center_lon:.6f}"],
        "country": scene.country or "",
        "city": scene.city or "",
        "length": f"{length_km:.2f} km" if length_km > 0 else "Unknown",
        "width": f"{scene.track_width_m:.0f}",
        "pitboxes": scene.pitbox_count,
        "run": "0",
        "author": "AC Track Generator",
    }


def _build_surfaces_ini() -> dict:
    """Build surfaces.ini with standard AC surface definitions."""
    return {
        "SURFACE_0": {
            "KEY": "ROAD",
            "FRICTION": "0.98",
            "DAMPING": "0.0",
            "WAV": "road",
            "WAV_PITCH": "0.0",
            "FF_EFFECT": "None",
            "DIRT_ADDITIVE": "0.0",
            "IS_VALID_TRACK": "1",
            "BLACK_FLAG_TIME": "0",
            "SIN_HEIGHT": "0.0",
            "SIN_LENGTH": "0.0",
            "IS_PITLANE": "0",
            "VIBRATION_GAIN": "0.0",
            "VIBRATION_LENGTH": "0.0",
        },
        "SURFACE_1": {
            "KEY": "KERB",
            "FRICTION": "0.8",
            "DAMPING": "0.0",
            "WAV": "kerb",
            "WAV_PITCH": "0.0",
            "FF_EFFECT": "None",
            "DIRT_ADDITIVE": "0.0",
            "IS_VALID_TRACK": "1",
            "BLACK_FLAG_TIME": "0",
            "SIN_HEIGHT": "0.03",
            "SIN_LENGTH": "0.5",
            "IS_PITLANE": "0",
            "VIBRATION_GAIN": "0.0",
            "VIBRATION_LENGTH": "0.0",
        },
        "SURFACE_2": {
            "KEY": "GRASS",
            "FRICTION": "0.6",
            "DAMPING": "0.1",
            "WAV": "grass",
            "WAV_PITCH": "0.0",
            "FF_EFFECT": "None",
            "DIRT_ADDITIVE": "0.1",
            "IS_VALID_TRACK": "0",
            "BLACK_FLAG_TIME": "0",
            "SIN_HEIGHT": "0.02",
            "SIN_LENGTH": "0.3",
            "IS_PITLANE": "0",
            "VIBRATION_GAIN": "0.0",
            "VIBRATION_LENGTH": "0.0",
        },
        "SURFACE_3": {
            "KEY": "SAND",
            "FRICTION": "0.5",
            "DAMPING": "0.2",
            "WAV": "sand",
            "WAV_PITCH": "0.0",
            "FF_EFFECT": "None",
            "DIRT_ADDITIVE": "0.3",
            "IS_VALID_TRACK": "0",
            "BLACK_FLAG_TIME": "0",
            "SIN_HEIGHT": "0.0",
            "SIN_LENGTH": "0.0",
            "IS_PITLANE": "0",
            "VIBRATION_GAIN": "0.0",
            "VIBRATION_LENGTH": "0.0",
        },
    }


def _build_lighting_ini() -> dict:
    """Build lighting.ini with default sun settings."""
    return {
        "DEFAULT": {
            "SUN_PITCH_ANGLE": "40",
            "SUN_HEADING_ANGLE": "0",
        }
    }


def _build_cameras_ini(scene: ACScene) -> dict:
    """Build cameras.ini with one default overview camera."""
    # Position camera above the start position looking forward
    cam_x, cam_y, cam_z = 0.0, 50.0, -30.0

    # Try to place near the first start marker
    for marker in scene.markers:
        if marker.name.startswith("AC_START_"):
            cam_x = marker.position[0]
            cam_y = marker.position[1] + 50.0
            cam_z = marker.position[2] - 30.0
            break

    return {
        "CAM_0": {
            "POSITION": f"{cam_x:.2f},{cam_y:.2f},{cam_z:.2f}",
            "TARGET": f"{cam_x:.2f},0.00,{cam_z + 50.0:.2f}",
            "FOV": "60",
            "NEAR": "1.0",
            "FAR": "10000.0",
            "ACTIVE": "1",
        }
    }


def _build_ext_config() -> dict:
    """Build extension/ext_config.ini with global lighting settings."""
    return {
        "LIGHTING": {
            "AMBIENT_MULT": "1.0",
            "LIT_MULT": "1.0",
            "SPECULAR_MULT": "1.0",
            "CAR_LIGHTS_LIT_MULT": "1.0",
        }
    }


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _write_ini(path: Path, data: dict) -> None:
    """Write a dict of dicts to INI format."""
    lines: list[str] = []
    for section, values in data.items():
        lines.append(f"[{section}]")
        if isinstance(values, dict):
            for key, value in values.items():
                lines.append(f"{key}={value}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _sanitize_name(name: str) -> str:
    """Sanitize track name for use as filename."""
    result = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return result.strip("_") or "track"
