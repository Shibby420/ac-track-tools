"""
Assetto Corsa track installer.

Detects the AC installation directory and copies the built track
folder into the content/tracks/ directory.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


# Common AC install paths by platform
_AC_SEARCH_PATHS_WINDOWS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\assettocorsa",
    r"C:\Program Files\Steam\steamapps\common\assettocorsa",
    r"D:\Steam\steamapps\common\assettocorsa",
    r"D:\SteamLibrary\steamapps\common\assettocorsa",
    r"E:\Steam\steamapps\common\assettocorsa",
    r"E:\SteamLibrary\steamapps\common\assettocorsa",
    r"C:\Games\assettocorsa",
    r"D:\Games\assettocorsa",
]

_AC_SEARCH_PATHS_LINUX = [
    os.path.expanduser("~/.steam/steam/steamapps/common/assettocorsa"),
    os.path.expanduser("~/.local/share/Steam/steamapps/common/assettocorsa"),
    "/home/user/.steam/steam/steamapps/common/assettocorsa",
    "/opt/steam/steamapps/common/assettocorsa",
]

_AC_SEARCH_PATHS_MAC = [
    os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/assettocorsa"),
]


def find_ac_install() -> str | None:
    """
    Search common locations for an Assetto Corsa installation.

    Returns the AC root directory path, or None if not found.
    """
    if sys.platform == "win32":
        paths = _AC_SEARCH_PATHS_WINDOWS
        # Also check Steam registry on Windows
        registry_path = _get_ac_from_registry()
        if registry_path:
            paths = [registry_path] + paths
    elif sys.platform == "darwin":
        paths = _AC_SEARCH_PATHS_MAC
    else:
        paths = _AC_SEARCH_PATHS_LINUX

    for path in paths:
        if path and _is_valid_ac_install(path):
            return path

    return None


def get_tracks_directory(ac_install: str) -> str:
    """Return the tracks directory for an AC install."""
    return str(Path(ac_install) / "content" / "tracks")


def install_track(track_folder: str, ac_install: str | None = None) -> dict[str, object]:
    """
    Install a built track into the AC tracks directory.

    Args:
        track_folder: Path to the built track folder
        ac_install: AC install root (auto-detected if None)

    Returns:
        dict with 'success', 'install_path', 'message'
    """
    if ac_install is None:
        ac_install = find_ac_install()
        if ac_install is None:
            return {
                "success": False,
                "install_path": None,
                "message": (
                    "Could not find Assetto Corsa installation.\n"
                    "Use --install-dir to specify your AC install path.\n"
                    "Example: --install-dir 'C:\\Games\\assettocorsa'"
                ),
            }

    if not _is_valid_ac_install(ac_install):
        return {
            "success": False,
            "install_path": None,
            "message": f"Not a valid AC installation: {ac_install}",
        }

    tracks_dir = get_tracks_directory(ac_install)
    track_name = Path(track_folder).name
    dest = Path(tracks_dir) / track_name

    try:
        # Remove existing installation if present
        if dest.exists():
            shutil.rmtree(dest)

        shutil.copytree(track_folder, str(dest))

        return {
            "success": True,
            "install_path": str(dest),
            "message": (
                f"Track installed successfully!\n"
                f"  From: {track_folder}\n"
                f"  To:   {dest}\n\n"
                f"Launch Assetto Corsa or Content Manager to play."
            ),
        }
    except PermissionError:
        return {
            "success": False,
            "install_path": None,
            "message": (
                f"Permission denied writing to {tracks_dir}.\n"
                "Try running as administrator (Windows) or with sudo (Linux/Mac)."
            ),
        }
    except Exception as e:
        return {
            "success": False,
            "install_path": None,
            "message": f"Install failed: {e}",
        }


def _is_valid_ac_install(path: str) -> bool:
    """Check if a path looks like an AC installation."""
    ac_path = Path(path)
    # AC install should have content/tracks and either acs.exe or acs.sh
    has_tracks = (ac_path / "content" / "tracks").exists()
    has_exe = (
        (ac_path / "acs.exe").exists()
        or (ac_path / "acs.sh").exists()
        or (ac_path / "AssettoCorsa.exe").exists()
        or (ac_path / "launcher" / "AssettoCorsa.exe").exists()
        or (ac_path / "content").exists()  # Minimal check for CM-only setups
    )
    return has_tracks or has_exe


def _get_ac_from_registry() -> str | None:
    """Read AC install path from Windows registry (Steam)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam",
        )
        steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
        winreg.CloseKey(key)
        ac_path = Path(steam_path) / "steamapps" / "common" / "assettocorsa"
        if ac_path.exists():
            return str(ac_path)
    except Exception:
        pass
    return None
