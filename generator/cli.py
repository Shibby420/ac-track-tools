#!/usr/bin/env python3
"""
AC Track Generator — Command Line Interface

Usage:
    python cli.py --location "Nurburgring, Germany" --output ./output
    python cli.py --location "Monaco" --radius 2.0 --output ./tracks
    python cli.py --coords 50.3356,6.9475 --output ./custom --radius 5.0
    python cli.py --import-track ./existing_track --output ./modified
    python cli.py --export-only ./track_folder  (re-export an existing build)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add generator root to path
sys.path.insert(0, str(Path(__file__).parent))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ac-track-generator",
        description="Generate Assetto Corsa tracks from real-world OpenStreetMap data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Location input (mutually exclusive)
    loc_group = parser.add_mutually_exclusive_group()
    loc_group.add_argument(
        "--location", "-l",
        metavar="NAME",
        help='Place name to search (e.g. "Nurburgring, Germany" or "Monaco")',
    )
    loc_group.add_argument(
        "--coords", "-c",
        metavar="LAT,LON",
        help="Coordinates to center the track on (e.g. 50.3356,6.9475)",
    )
    loc_group.add_argument(
        "--import-track",
        metavar="DIR",
        help="Import and re-export an existing AC track folder",
    )

    # Build options
    parser.add_argument(
        "--output", "-o",
        metavar="DIR",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--radius", "-r",
        type=float,
        default=3.0,
        metavar="KM",
        help="Area radius in km (default: 3.0)",
    )
    parser.add_argument(
        "--no-foliage",
        action="store_true",
        help="Skip tree/foliage generation",
    )
    parser.add_argument(
        "--no-signs",
        action="store_true",
        help="Skip road sign generation",
    )
    parser.add_argument(
        "--pitboxes",
        type=int,
        default=8,
        metavar="N",
        help="Number of pit boxes (default: 8)",
    )
    parser.add_argument(
        "--terrain-grid",
        type=int,
        default=64,
        metavar="N",
        help="Terrain grid resolution NxN (default: 64)",
    )
    parser.add_argument(
        "--flat-terrain",
        action="store_true",
        help="Use flat terrain (skip elevation API calls)",
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="List all generated files on success",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.location and not args.coords and not args.import_track:
        parser.print_help()
        print("\nError: You must specify --location, --coords, or --import-track", file=sys.stderr)
        return 1

    # Handle import-track (load existing AC track folder)
    if args.import_track:
        return _handle_import(args)

    # Build from location
    location = args.location or args.coords
    return _handle_build(location, args)


def _handle_build(location: str, args) -> int:
    """Run the track build pipeline."""
    from export.track_exporter import BuildOptions, build_track  # type: ignore

    options = BuildOptions(
        radius_km=args.radius,
        include_foliage=not args.no_foliage,
        include_signs=not args.no_signs,
        pitbox_count=args.pitboxes,
        terrain_grid=args.terrain_grid,
        output_dir=args.output,
    )

    print(f"Building track for: {location}")
    print(f"  Radius: {args.radius} km")
    print(f"  Foliage: {'Yes' if not args.no_foliage else 'No'}")
    print(f"  Signs: {'Yes' if not args.no_signs else 'No'}")
    print(f"  Output: {args.output}")
    print()

    result = build_track(
        location=location,
        options=options,
        progress_cb=lambda msg: print(f"  {msg}"),
    )

    print()
    if result.success:
        print(f"✓ Track built successfully!")
        print(f"  Output: {result.output_path}")
        if result.warnings:
            print(f"\nWarnings ({len(result.warnings)}):")
            for w in result.warnings:
                print(f"  ⚠ {w}")
        if args.list_files:
            print(f"\nGenerated files ({len(result.generated_files)}):")
            for f in result.generated_files:
                size = os.path.getsize(f) if os.path.exists(f) else 0
                print(f"  {f}  ({_format_size(size)})")
        print()
        print("To use in Assetto Corsa Content Manager:")
        print(f"  Copy '{result.output_path}' to your AC tracks folder:")
        print(f"  [AC install]/content/tracks/")
        return 0
    else:
        print("✗ Build failed!")
        for err in result.errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        return 1


def _handle_import(args) -> int:
    """Import an existing AC track folder and show its contents."""
    import_dir = Path(args.import_track)
    if not import_dir.exists():
        print(f"Error: Directory not found: {import_dir}", file=sys.stderr)
        return 1

    print(f"Importing track from: {import_dir}")

    # Check for key files
    checks = [
        (import_dir / "models.ini", "models.ini", True),
        (import_dir / "data" / "surfaces.ini", "data/surfaces.ini", True),
        (import_dir / "ui" / "ui_track.json", "ui/ui_track.json", True),
        (import_dir / "map.png", "map.png", False),
        (import_dir / "data" / "lighting.ini", "data/lighting.ini", False),
        (import_dir / "data" / "cameras.ini", "data/cameras.ini", False),
        (import_dir / "extension" / "ext_config.ini", "extension/ext_config.ini", False),
    ]

    print("\nTrack folder contents:")
    all_required_found = True
    for path, label, required in checks:
        exists = path.exists()
        if required and not exists:
            all_required_found = False
        status = "✓" if exists else ("✗ MISSING (required)" if required else "- not found")
        print(f"  {status}  {label}")

    # Show track metadata if ui_track.json exists
    ui_json = import_dir / "ui" / "ui_track.json"
    if ui_json.exists():
        import json
        try:
            with open(ui_json) as f:
                meta = json.load(f)
            print(f"\nTrack info:")
            print(f"  Name:    {meta.get('name', 'Unknown')}")
            print(f"  Country: {meta.get('country', 'Unknown')}")
            print(f"  Length:  {meta.get('length', 'Unknown')}")
            print(f"  Pits:    {meta.get('pitboxes', 'Unknown')}")
        except Exception:
            pass

    # List KN5 files
    kn5_files = list(import_dir.glob("*.kn5"))
    if kn5_files:
        print(f"\nKN5 models ({len(kn5_files)}):")
        for kn5 in kn5_files:
            size = os.path.getsize(kn5)
            print(f"  {kn5.name}  ({_format_size(size)})")

    if all_required_found:
        print("\n✓ Track folder looks valid and ready for AC Content Manager")
    else:
        print("\n⚠ Track folder is missing required files")

    return 0 if all_required_found else 1


def _format_size(size_bytes: int) -> str:
    """Format file size as human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


if __name__ == "__main__":
    sys.exit(main())
