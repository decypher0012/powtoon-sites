from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .config import save_config
from .update_download import download_release, download_updater, updates_dir
from .update_models import ReleaseInfo
from .ui_style import apply_visual_style, style_text
from .version import __version__


class UpdateDialog(tk.Toplevel):
    def __init__(self, master, release: ReleaseInfo, config, config_path):
        super().__init__(master)
        self.title("Work Launcher Update")
        self.geometry("570x470")
        self.transient(master)
        self.grab_set()
        self.release = release
        self.config = config
        self.config_path = config_path
        self.cancel_event = threading.Event()
        self.events = queue.Queue()
        self.started = 0.0
        self.downloading = False
        self.install_after_download = True
        self.last_download_path: Path | None = None
        self.palette = apply_visual_style(self, config.settings.visual_style)

        frame = ttk.Frame(self, padding=16, style="Card.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Version {release.version} is available.", style="Header.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"Current: {__version__}\nAvailable: {release.version}\nReleased: {release.release_date}", style="Card.TLabel").pack(anchor="w", pady=8)
        ttk.Label(frame, text="Changes:").pack(anchor="w")
        notes = tk.Text(frame, height=10, wrap="word")
        notes.pack(fill="both", expand=True)
        style_text(notes, self.palette)
        note_lines = [f"- {note}" for note in release.release_notes] or ["No release notes provided."]
        notes.insert("1.0", "\n".join(note_lines))
        notes.configure(state="disabled")

        self.progress = ttk.Progressbar(frame, maximum=100)
        self.progress.pack(fill="x", pady=(10, 2))
        self.status = tk.StringVar(value="Ready to download.")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        self.download_button = ttk.Button(buttons, text="Download Update", command=self.download, style="Primary.TButton")
        self.download_button.pack(side="left")
        self.cancel_button = ttk.Button(buttons, text="Cancel Download", command=self.cancel_download, state="disabled")
        self.cancel_button.pack(side="left", padx=5)
        self.skip_button = ttk.Button(buttons, text="Skip", command=self.skip, state="disabled" if release.mandatory else "normal")
        self.skip_button.pack(side="right")
        self.remind_button = ttk.Button(buttons, text="Remind Me Later", command=self.close_dialog)
        self.remind_button.pack(side="right", padx=5)
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

    def download(self, install_after_download: bool = True):
        if self.downloading:
            return
        self.install_after_download = install_after_download
        self.downloading = True
        self.cancel_event = threading.Event()
        self.download_button.configure(state="disabled", text="Download Update")
        self.cancel_button.configure(state="normal")
        self.remind_button.configure(state="disabled")
        self.started = time.monotonic()
        self.progress["value"] = 0
        self.status.set("Downloading update...")
        threading.Thread(target=self._worker, daemon=True).start()
        self.after(75, self._poll)

    def _worker(self):
        try:
            path = download_release(
                self.release,
                progress=lambda done, total: self.events.put(("progress", done, total)),
                cancel_event=self.cancel_event,
            )
            updater = download_updater(self.release) if self.release.asset_kind == "portable" else None
            self.events.put(("complete", path, updater))
        except Exception as exc:
            self.events.put(("error", exc))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, done, total = event
                    elapsed = max(time.monotonic() - self.started, 0.01)
                    speed = done / elapsed
                    remaining = (total - done) / speed if total and speed else 0
                    if total:
                        self.progress["value"] = done * 100 / total
                    self.status.set(f"{done/1048576:.1f} / {total/1048576:.1f} MB - {speed/1048576:.1f} MB/s - {remaining:.0f}s remaining")
                elif event[0] == "complete":
                    self.downloading = False
                    self.last_download_path = event[1]
                    if self.install_after_download:
                        self._install(event[1], event[2])
                    else:
                        path = event[1]
                        self.status.set("Update downloaded and verified. Ready to install.")
                        self.cancel_button.configure(state="disabled")
                        self.remind_button.configure(state="normal")
                        self.download_button.configure(text="Install Update", state="normal", command=lambda: self._install(path, event[2]))
                    return
                else:
                    self.downloading = False
                    self.status.set(str(event[1]))
                    self.download_button.configure(text="Retry Download", state="normal", command=lambda: self.download(self.install_after_download))
                    self.cancel_button.configure(state="disabled")
                    self.remind_button.configure(state="normal")
                    return
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(75, self._poll)

    def cancel_download(self):
        self.cancel_event.set()
        self.status.set("Cancelling download...")

    def close_dialog(self):
        if self.downloading:
            return
        self.destroy()

    def skip(self):
        self.config.updates.skipped_version = self.release.version
        save_config(self.config_path, self.config)
        self.destroy()

    def _install(self, path: Path, downloaded_updater: Path | None = None):
        updater = downloaded_updater or (Path(sys.executable).with_name("Updater.exe") if getattr(sys, "frozen", False) else Path.cwd() / "dist" / "Updater.exe")
        current = Path(sys.executable) if getattr(sys, "frozen", False) else Path.cwd() / "dist" / "WorkLauncher.exe"
        if not updater.is_file():
            messagebox.showerror(self.title(), "Updater.exe was not found beside WorkLauncher.exe.", parent=self)
            return
        ready = updates_dir() / f"updater-{os.getpid()}.ready"
        ready.unlink(missing_ok=True)
        args = [
            str(updater),
            "--current",
            str(current),
            "--download",
            str(path),
            "--sha256",
            self.release.sha256,
            "--size",
            str(self.release.size),
            "--parent-pid",
            str(os.getpid()),
            "--ready-file",
            str(ready),
        ]
        if self.release.asset_kind == "installer":
            args.append("--installer")
        try:
            process = subprocess.Popen(args, shell=False)
            self.status.set("Preparing verified updater...")
            self._ready_deadline = time.monotonic() + 30
            self.after(100, lambda: self._wait_updater_ready(process, ready))
        except OSError as exc:
            messagebox.showerror(self.title(), f"Unable to start Updater.exe: {exc}", parent=self)

    def _wait_updater_ready(self, process, ready: Path):
        if ready.exists():
            self.status.set("Installing update and restarting...")
            self.master.destroy()
            return
        if process.poll() is not None:
            messagebox.showerror(self.title(), "Updater could not validate the running application. The update was not installed.", parent=self)
            return
        if time.monotonic() >= self._ready_deadline:
            process.terminate()
            messagebox.showerror(self.title(), "Updater preparation timed out. The update was not installed.", parent=self)
            return
        self.after(100, lambda: self._wait_updater_ready(process, ready))
