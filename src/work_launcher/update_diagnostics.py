from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .constants import APP_NAME, UPDATE_GITHUB_OWNER, UPDATE_GITHUB_REPOSITORY
from .config import save_config
from .ui_style import apply_visual_style, style_text


class UpdateDiagnosticsDialog(tk.Toplevel):
    def __init__(self, master, snapshot: dict[str, object], config, config_path):
        super().__init__(master)
        self.title(f"{APP_NAME} Update Diagnostics")
        self.geometry("720x520")
        self.transient(master)
        self.grab_set()
        self.snapshot = snapshot
        self.config = config
        self.config_path = config_path
        self.palette = apply_visual_style(self, config.settings.visual_style)
        frame = ttk.Frame(self, padding=14, style="Card.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Update Diagnostics", style="Header.TLabel").pack(anchor="w")
        ttk.Label(frame, text="This view shows the active update source, the latest known release, and any recent error.", style="Card.TLabel").pack(anchor="w", pady=(4, 10))

        text = tk.Text(frame, height=20, wrap="word")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        style_text(text, self.palette)
        scrollbar.pack(side="right", fill="y")

        lines = [
            f"Provider: {snapshot['provider']}",
            f"Repository: {snapshot['owner']}/{snapshot['repository']}",
            f"Channel: {snapshot['channel']}",
            f"Policy: {snapshot['policy']}",
            f"Auto check: {'Yes' if snapshot['automatically_check'] else 'No'}",
            f"Auto download: {'Yes' if snapshot['automatically_download'] else 'No'}",
            f"Installation kind: {snapshot['installation_kind']}",
            f"Last checked: {snapshot['last_checked']}",
            f"Next check: {snapshot['next_check']}",
            f"Skipped version: {snapshot['skipped_version']}",
            f"Checked this session: {'Yes' if snapshot['checked_this_session'] else 'No'}",
            "",
            f"Latest version: {snapshot['latest_version']}",
            f"Latest release date: {snapshot['latest_release_date']}",
            f"Latest asset: {snapshot['latest_asset_name']} ({snapshot['latest_asset_kind']})",
            f"Latest asset size: {snapshot['latest_size']}",
            f"Latest SHA-256: {snapshot['latest_sha256']}",
            f"Latest asset URL: {snapshot['latest_asset_url']}",
            "",
            "Release notes:",
        ]
        notes = snapshot.get("latest_notes", [])
        if isinstance(notes, list) and notes:
            lines.extend(f"  - {note}" for note in notes)
        else:
            lines.append("  - None")
        lines.extend(["", f"Last error: {snapshot['last_error']}"])
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Copy Summary", command=lambda: self.copy_summary(text), style="Primary.TButton").pack(side="left")
        ttk.Button(buttons, text="Repair Update Settings", command=self.repair_update_settings).pack(side="left", padx=6)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

    def copy_summary(self, text: tk.Text) -> None:
        summary = text.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(summary)
        self.update()

    def repair_update_settings(self) -> None:
        updates = self.config.updates
        updates.provider = "github"
        updates.owner = UPDATE_GITHUB_OWNER
        updates.repository = UPDATE_GITHUB_REPOSITORY
        updates.last_checked = ""
        updates.skipped_version = ""
        save_config(self.config_path, self.config)
        messagebox.showinfo(APP_NAME, "Update settings were repaired.", parent=self)
        self.destroy()
