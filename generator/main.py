#!/usr/bin/env python3
"""
AC Track Generator — GUI Entry Point

Launch the graphical interface for building Assetto Corsa tracks
from real-world OpenStreetMap data.

Usage:
    python main.py
"""
import sys
from pathlib import Path

# Add generator root to path so imports work from any working directory
sys.path.insert(0, str(Path(__file__).parent))


def main() -> None:
    try:
        from ui.app_window import ACTrackGeneratorApp
    except ImportError as e:
        # Check for tkinter
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print("Error: tkinter is not installed. Please install it:")
            print("  Ubuntu/Debian: sudo apt-get install python3-tk")
            print("  Fedora:        sudo dnf install python3-tkinter")
            print("  Windows/macOS: tkinter is bundled with Python")
            print()
            print("Alternatively, use the CLI: python cli.py --help")
            sys.exit(1)
        raise

    app = ACTrackGeneratorApp()

    # Handle high-DPI displays
    try:
        app.tk.call("tk", "scaling", 1.5)
    except Exception:
        pass

    app.mainloop()


if __name__ == "__main__":
    main()
