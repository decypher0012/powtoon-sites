from __future__ import annotations

import threading
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from .browser_launcher import BrowserLauncher
from .browser_profiles import BrowserProfile
from .browser_scanner import scan_browsers
from .config import save_config
from .setup_service import detected_profile_exists, import_detected_profile
from .manual_profile_dialog import ManualProfileDialog


class DetectedProfilesDialog(tk.Toplevel):
    def __init__(self, master, config, config_path, manual_callback=None):
        super().__init__(master); self.title("Detected Browser Profiles"); self.geometry("900x480"); self.transient(master); self.grab_set()
        self.config, self.config_path, self.manual_callback = config, config_path, manual_callback; self.profiles = []; self.generation = 0; self.scan_queue = queue.Queue(); self.pending_scans = 0
        ttk.Label(self, text="Work Launcher only detects browser installation and profile names. It does not read passwords, cookies, browsing history, or website content.", wraplength=850).pack(anchor="w", padx=12, pady=10)
        columns = ("browser", "name", "directory", "default", "status", "added")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="extended")
        for column, label, width in (("browser","Browser",140),("name","Profile Name",180),("directory","Profile Directory",140),("default","Default",70),("status","Status",90),("added","Already Added",110)):
            self.tree.heading(column, text=label); self.tree.column(column, width=width)
        self.tree.pack(fill="both", expand=True, padx=12)
        self.status = tk.StringVar(value="Ready to scan."); ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=12, pady=4)
        buttons = ttk.Frame(self); buttons.pack(fill="x", padx=12, pady=10)
        for text, command in (("Add Selected", self.add_selected), ("Test Selected", self.test_selected), ("Rescan", self.rescan),
                              ("Configure Manually", self.configure_manual), ("Close", self.destroy)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=3)
        self.bind("<Escape>", lambda event: self.destroy()); self.rescan()

    def rescan(self):
        self.generation += 1; self.pending_scans += 1; generation = self.generation; self.status.set("Scanning installed browsers and profiles...")
        threading.Thread(target=self._scan_worker, args=(generation,), daemon=True).start()
        self.after(50, self._poll_scan)

    def _scan_worker(self, generation):
        self.scan_queue.put((generation, scan_browsers()))

    def _poll_scan(self):
        try: generation, results = self.scan_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists() and self.pending_scans: self.after(50, self._poll_scan)
            return
        self.pending_scans = max(0, self.pending_scans - 1)
        self._show_results(generation, results)

    def _show_results(self, generation, results):
        if generation != self.generation or not self.winfo_exists(): return
        self.tree.delete(*self.tree.get_children()); self.profiles = [profile for result in results for profile in result.profiles]
        for index, profile in enumerate(self.profiles):
            self.tree.insert("", "end", iid=str(index), values=(profile.browser_name, profile.profile_display_name, profile.profile_directory,
                "Yes" if profile.is_default else "", profile.status, "Yes" if detected_profile_exists(self.config, profile) else "No"))
        installed = sum(bool(result.executable_path) for result in results)
        self.status.set(f"Scan complete: {installed} browsers installed, {len(self.profiles)} profiles detected.")

    def _selected(self): return [self.profiles[int(item)] for item in self.tree.selection()]

    def add_selected(self):
        selected = self._selected()
        if not selected: return
        added = 0
        for profile in selected:
            if not detected_profile_exists(self.config, profile): import_detected_profile(self.config, profile); added += 1
        save_config(self.config_path, self.config); self.status.set(f"Added {added} detected profiles."); self.rescan()

    def test_selected(self):
        selected = self._selected()
        if len(selected) != 1: messagebox.showinfo(self.title(), "Select one profile to test.", parent=self); return
        item = selected[0]
        profile = BrowserProfile(item.profile_display_name, item.browser_type, item.executable_path, item.user_data_dir, item.profile_directory)
        try: BrowserLauncher().launch(profile, ["https://www.google.com/"], ["Detected profile test"]); self.status.set("Test page opened successfully.")
        except Exception as exc: messagebox.showerror(self.title(), f"Unable to test profile: {exc}", parent=self)

    def configure_manual(self):
        if self.manual_callback: self.manual_callback(); return
        dialog = ManualProfileDialog(self); self.wait_window(dialog)
        if dialog.result:
            base = "-".join(dialog.result.name.lower().split()) or "manual-profile"; key = base; number = 2
            while key in self.config.browser_profiles: key = f"{base}-{number}"; number += 1
            self.config.browser_profiles[key] = dialog.result; save_config(self.config_path, self.config); self.status.set(f"Added {dialog.result.name}.")
