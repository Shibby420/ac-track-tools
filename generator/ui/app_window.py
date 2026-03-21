"""Main tkinter GUI window for AC Track Generator."""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


class ACTrackGeneratorApp(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("AC Track Generator")
        self.geometry("800x650")
        self.resizable(True, True)
        self.configure(bg="#2b2b2b")

        self._build_thread: threading.Thread | None = None
        self._setup_ui()

    # ─────────────────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#2b2b2b")
        style.configure("TLabel", background="#2b2b2b", foreground="#cccccc")
        style.configure("TButton", background="#444444", foreground="#ffffff")
        style.configure("Accent.TButton", background="#0066cc", foreground="#ffffff")
        style.configure("TCheckbutton", background="#2b2b2b", foreground="#cccccc")
        style.configure("TEntry", fieldbackground="#3c3c3c", foreground="#ffffff")
        style.configure("TLabelframe", background="#2b2b2b", foreground="#aaaaaa")
        style.configure("TLabelframe.Label", background="#2b2b2b", foreground="#aaaaaa")
        style.configure("TProgressbar", troughcolor="#444444", background="#0066cc")

        main_frame = ttk.Frame(self, padding="12 12 12 12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self._build_header(main_frame)
        self._build_location_section(main_frame)
        self._build_options_section(main_frame)
        self._build_output_section(main_frame)
        self._build_import_section(main_frame)
        self._build_action_section(main_frame)
        self._build_log_section(main_frame)

    def _build_header(self, parent) -> None:
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(
            header,
            text="AC Track Generator",
            font=("Arial", 16, "bold"),
            foreground="#ffffff",
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Build real-world tracks for Assetto Corsa",
            font=("Arial", 9),
            foreground="#888888",
        ).pack(side=tk.LEFT, padx=(10, 0))

    def _build_location_section(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Location", padding="8 4 8 8")
        frame.pack(fill=tk.X, pady=(0, 8))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Place name or lat,lon:").pack(side=tk.LEFT)

        self.location_var = tk.StringVar(value="")
        loc_entry = ttk.Entry(row, textvariable=self.location_var, width=40)
        loc_entry.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        loc_entry.bind("<Return>", lambda e: self._start_build())

        examples = ttk.Frame(frame)
        examples.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(
            examples,
            text='Examples: "Nurburgring, Germany"  ·  "Monaco"  ·  "Silverstone, UK"  ·  "50.3356,6.9475"',
            foreground="#666666",
            font=("Arial", 8),
        ).pack(side=tk.LEFT)

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row2, text="Area radius (km):").pack(side=tk.LEFT)
        self.radius_var = tk.DoubleVar(value=3.0)
        radius_spin = tk.Spinbox(
            row2,
            from_=0.5,
            to=20.0,
            increment=0.5,
            textvariable=self.radius_var,
            width=6,
            bg="#3c3c3c",
            fg="#ffffff",
            insertbackground="#ffffff",
        )
        radius_spin.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(row2, text="(larger = more area, longer build time)", foreground="#666666").pack(side=tk.LEFT, padx=(8, 0))

    def _build_options_section(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Build Options", padding="8 4 8 8")
        frame.pack(fill=tk.X, pady=(0, 8))

        col1 = ttk.Frame(frame)
        col1.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        col2 = ttk.Frame(frame)
        col2.pack(side=tk.LEFT, fill=tk.Y)

        self.foliage_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(col1, text="Include trees & foliage", variable=self.foliage_var).pack(anchor=tk.W)

        self.signs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(col1, text="Include road signs", variable=self.signs_var).pack(anchor=tk.W)

        self.flat_terrain_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(col1, text="Flat terrain (skip elevation API)", variable=self.flat_terrain_var).pack(anchor=tk.W)

        pitrow = ttk.Frame(col2)
        pitrow.pack(anchor=tk.W, pady=(0, 4))
        ttk.Label(pitrow, text="Pit boxes:").pack(side=tk.LEFT)
        self.pitboxes_var = tk.IntVar(value=8)
        tk.Spinbox(
            pitrow,
            from_=1,
            to=50,
            textvariable=self.pitboxes_var,
            width=4,
            bg="#3c3c3c",
            fg="#ffffff",
            insertbackground="#ffffff",
        ).pack(side=tk.LEFT, padx=(6, 0))

        gridrow = ttk.Frame(col2)
        gridrow.pack(anchor=tk.W)
        ttk.Label(gridrow, text="Terrain detail:").pack(side=tk.LEFT)
        self.terrain_var = tk.IntVar(value=64)
        terrain_combo = ttk.Combobox(
            gridrow,
            textvariable=self.terrain_var,
            values=[32, 64, 128],
            width=6,
            state="readonly",
        )
        terrain_combo.pack(side=tk.LEFT, padx=(6, 0))

    def _build_output_section(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Output", padding="8 4 8 8")
        frame.pack(fill=tk.X, pady=(0, 8))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X)

        self.output_var = tk.StringVar(value=str(Path.home() / "ac_tracks"))
        ttk.Entry(row, textvariable=self.output_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse…", command=self._browse_output).pack(side=tk.LEFT, padx=(6, 0))

    def _build_import_section(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Import Existing Track", padding="8 4 8 8")
        frame.pack(fill=tk.X, pady=(0, 8))

        row = ttk.Frame(frame)
        row.pack(fill=tk.X)
        ttk.Label(row, text="AC track folder:", foreground="#999999").pack(side=tk.LEFT)

        self.import_var = tk.StringVar(value="")
        ttk.Entry(row, textvariable=self.import_var, width=40).pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        ttk.Button(row, text="Browse…", command=self._browse_import).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Inspect", command=self._inspect_import).pack(side=tk.LEFT, padx=(6, 0))

    def _build_action_section(self, parent) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 8))

        self.build_btn = ttk.Button(
            frame,
            text="Build Track",
            command=self._start_build,
            style="Accent.TButton",
        )
        self.build_btn.pack(side=tk.LEFT)

        self.cancel_btn = ttk.Button(
            frame,
            text="Cancel",
            command=self._cancel_build,
            state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(
            frame,
            text="Open Output Folder",
            command=self._open_output,
        ).pack(side=tk.LEFT, padx=(8, 0))

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            frame,
            variable=self.progress_var,
            maximum=100,
            length=200,
            mode="indeterminate",
        )
        self.progress_bar.pack(side=tk.LEFT, padx=(16, 0))

        self.status_label = ttk.Label(frame, text="Ready", foreground="#888888")
        self.status_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_log_section(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Build Log", padding="4 4 4 4")
        frame.pack(fill=tk.BOTH, expand=True)

        self.log = scrolledtext.ScrolledText(
            frame,
            height=10,
            bg="#1e1e1e",
            fg="#cccccc",
            font=("Courier", 9),
            insertbackground="#ffffff",
            wrap=tk.WORD,
        )
        self.log.pack(fill=tk.BOTH, expand=True)
        self.log.config(state=tk.DISABLED)

    # ─────────────────────────────────────────────────────────────────────
    # Actions
    # ─────────────────────────────────────────────────────────────────────

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Select Output Directory")
        if folder:
            self.output_var.set(folder)

    def _browse_import(self) -> None:
        folder = filedialog.askdirectory(title="Select AC Track Folder to Import")
        if folder:
            self.import_var.set(folder)

    def _open_output(self) -> None:
        output = self.output_var.get()
        if output and os.path.exists(output):
            if sys.platform == "win32":
                os.startfile(output)
            elif sys.platform == "darwin":
                os.system(f'open "{output}"')
            else:
                os.system(f'xdg-open "{output}"')
        else:
            messagebox.showinfo("Not found", f"Output directory does not exist yet:\n{output}")

    def _inspect_import(self) -> None:
        import_dir = self.import_var.get()
        if not import_dir or not os.path.exists(import_dir):
            messagebox.showerror("Error", "Please select an existing AC track folder.")
            return

        self._log_clear()
        self._log(f"Inspecting: {import_dir}\n")

        checks = [
            ("models.ini", os.path.join(import_dir, "models.ini"), True),
            ("data/surfaces.ini", os.path.join(import_dir, "data", "surfaces.ini"), True),
            ("ui/ui_track.json", os.path.join(import_dir, "ui", "ui_track.json"), True),
            ("map.png", os.path.join(import_dir, "map.png"), False),
            ("data/lighting.ini", os.path.join(import_dir, "data", "lighting.ini"), False),
            ("data/cameras.ini", os.path.join(import_dir, "data", "cameras.ini"), False),
            ("extension/ext_config.ini", os.path.join(import_dir, "extension", "ext_config.ini"), False),
        ]

        all_ok = True
        for label, path, required in checks:
            exists = os.path.exists(path)
            if required and not exists:
                all_ok = False
            icon = "✓" if exists else ("✗ MISSING (required)" if required else "- not found")
            self._log(f"  {icon}  {label}\n")

        # Show track metadata
        ui_json = os.path.join(import_dir, "ui", "ui_track.json")
        if os.path.exists(ui_json):
            import json
            try:
                with open(ui_json) as f:
                    meta = json.load(f)
                self._log(f"\nTrack: {meta.get('name', 'Unknown')}\n")
                self._log(f"Country: {meta.get('country', '')}, City: {meta.get('city', '')}\n")
                self._log(f"Length: {meta.get('length', 'Unknown')}, Pits: {meta.get('pitboxes', '?')}\n")
            except Exception:
                pass

        kn5_files = list(Path(import_dir).glob("*.kn5"))
        if kn5_files:
            self._log(f"\nKN5 files ({len(kn5_files)}):\n")
            for kn5 in kn5_files:
                self._log(f"  {kn5.name}\n")

        self._log(f"\n{'✓ Track folder looks valid' if all_ok else '⚠ Missing required files'}\n")

    def _start_build(self) -> None:
        location = self.location_var.get().strip()
        if not location:
            messagebox.showerror("Error", "Please enter a location name or coordinates.")
            return

        if self._build_thread and self._build_thread.is_alive():
            messagebox.showinfo("Busy", "A build is already in progress.")
            return

        self.build_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.progress_bar.start(10)
        self.status_label.config(text="Building...", foreground="#ffcc00")
        self._log_clear()
        self._log(f"Starting build for: {location}\n\n")

        self._build_thread = threading.Thread(
            target=self._run_build,
            args=(location,),
            daemon=True,
        )
        self._build_thread.start()

    def _cancel_build(self) -> None:
        # Threads can't be force-stopped cleanly in Python,
        # but we can signal and the user can restart
        messagebox.showinfo(
            "Cancel",
            "The current build step will finish, then the build will stop.\n"
            "Close and reopen the app if needed."
        )

    def _run_build(self, location: str) -> None:
        """Run build in background thread."""
        try:
            gen_root = str(Path(__file__).parent.parent)
            if gen_root not in sys.path:
                sys.path.insert(0, gen_root)
            from export.track_exporter import BuildOptions, build_track  # type: ignore

            options = BuildOptions(
                radius_km=self.radius_var.get(),
                include_foliage=self.foliage_var.get(),
                include_signs=self.signs_var.get(),
                pitbox_count=self.pitboxes_var.get(),
                terrain_grid=self.terrain_var.get(),
                output_dir=self.output_var.get(),
            )

            result = build_track(
                location=location,
                options=options,
                progress_cb=lambda msg: self.after(0, lambda m=msg: self._log(m + "\n")),
            )

            self.after(0, lambda: self._build_complete(result))

        except Exception as e:
            import traceback
            err = traceback.format_exc()
            self.after(0, lambda: self._build_failed(str(e), err))

    def _build_complete(self, result) -> None:
        """Called on main thread when build finishes."""
        self.build_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.progress_var.set(0)

        if result.success:
            self.status_label.config(text="Done!", foreground="#44cc44")
            self._log(f"\n✓ Build complete!\n")
            self._log(f"Output: {result.output_path}\n")
            if result.warnings:
                self._log(f"\nWarnings ({len(result.warnings)}):\n")
                for w in result.warnings:
                    self._log(f"  ⚠ {w}\n")
            self._log(f"\nGenerated {len(result.generated_files)} files.\n")
            messagebox.showinfo(
                "Build Complete",
                f"Track built successfully!\n\nOutput: {result.output_path}\n\n"
                f"Copy to:\n[AC install]/content/tracks/"
            )
        else:
            self.status_label.config(text="Failed", foreground="#cc4444")
            self._log(f"\n✗ Build failed!\n")
            for err in result.errors:
                self._log(f"ERROR: {err}\n")
            messagebox.showerror("Build Failed", "\n".join(result.errors[:3]))

    def _build_failed(self, msg: str, trace: str) -> None:
        """Called on main thread when build throws an exception."""
        self.build_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.progress_bar.stop()
        self.status_label.config(text="Error", foreground="#cc4444")
        self._log(f"\n✗ Error: {msg}\n{trace}\n")
        messagebox.showerror("Error", f"Build error:\n{msg}")

    # ─────────────────────────────────────────────────────────────────────
    # Log helpers
    # ─────────────────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.insert(tk.END, text)
        self.log.see(tk.END)
        self.log.config(state=tk.DISABLED)

    def _log_clear(self) -> None:
        self.log.config(state=tk.NORMAL)
        self.log.delete(1.0, tk.END)
        self.log.config(state=tk.DISABLED)
