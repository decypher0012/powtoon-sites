from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .session_report import reports_dir
from .ui_style import style_listbox, style_text


class SelectionDialog(tk.Toplevel):
    def __init__(self, master, title, labels):
        super().__init__(master); self.title(title); self.geometry("650x500"); self.transient(master); self.grab_set(); self.result = None
        ttk.Label(self, text="Select the items to import:", padding=12).pack(anchor="w")
        self.box = tk.Listbox(self, selectmode="extended"); self.box.pack(fill="both", expand=True, padx=12)
        style_listbox(self.box, master.palette)
        for label in labels: self.box.insert("end", label)
        self.box.selection_set(0, "end")
        buttons = ttk.Frame(self, padding=12); buttons.pack(fill="x")
        ttk.Button(buttons, text="Select All", command=lambda: self.box.selection_set(0, "end")).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Continue", command=self.accept, style="Primary.TButton").pack(side="right", padx=5)
    def accept(self): self.result = list(self.box.curselection()); self.destroy()


class SessionHistoryDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master); self.title("Launch History"); self.geometry("760x460"); self.transient(master)
        self.files: list[Path] = []
        frame = ttk.Frame(self, padding=12); frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(frame, width=45); self.listbox.pack(side="left", fill="both", expand=True)
        self.details = tk.Text(frame, width=52, state="disabled", wrap="word"); self.details.pack(side="left", fill="both", expand=True, padx=(10, 0))
        style_listbox(self.listbox, master.palette); style_text(self.details, master.palette)
        self.listbox.bind("<<ListboxSelect>>", self.show_selected)
        buttons = ttk.Frame(self); buttons.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(buttons, text="Delete Selected", command=self.delete_selected).pack(side="left")
        ttk.Button(buttons, text="Clear History", command=self.clear).pack(side="left", padx=5)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        self.refresh()

    def refresh(self):
        self.files = sorted(reports_dir().glob("session-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        self.listbox.delete(0, "end")
        for path in self.files:
            try:
                data = json.loads(path.read_text(encoding="utf-8")); failed = sum(not row["success"] for row in data["results"])
                self.listbox.insert("end", f"{data['started_at']} — {data['preset']} — {failed} failed")
            except Exception: self.listbox.insert("end", f"{path.name} — unreadable")

    def show_selected(self, _event=None):
        if not self.listbox.curselection(): return
        path = self.files[self.listbox.curselection()[0]]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            lines = [f"Preset: {data['preset']}", f"Started: {data['started_at']}", ""]
            lines += [f"{'✓' if row['success'] else '✗'} {row['item']}: {row['status']}" for row in data["results"]]
            value = "\n".join(lines)
        except Exception as exc: value = f"Could not read report: {exc}"
        self.details.configure(state="normal"); self.details.delete("1.0", "end"); self.details.insert("1.0", value); self.details.configure(state="disabled")

    def delete_selected(self):
        if self.listbox.curselection(): self.files[self.listbox.curselection()[0]].unlink(missing_ok=True); self.refresh()

    def clear(self):
        if messagebox.askyesno("Launch History", "Delete all launch reports?", parent=self):
            for path in self.files: path.unlink(missing_ok=True)
            self.refresh()


class LaunchResultsDialog(tk.Toplevel):
    def __init__(self, master, preset, results, retry):
        super().__init__(master); self.title(f"Launch Results — {preset.name}"); self.geometry("620x380"); self.transient(master)
        tree = ttk.Treeview(self, columns=("status", "detail"), show="headings")
        tree.heading("status", text="Result"); tree.heading("detail", text="Item / details")
        tree.column("status", width=90, anchor="center"); tree.column("detail", width=480)
        tree.pack(fill="both", expand=True, padx=12, pady=12)
        failed = []
        for row in results:
            tree.insert("", "end", values=("Opened" if row.success else "Failed", f"{row.item} — {row.status}"))
            if not row.success: failed.append(row.item)
        buttons = ttk.Frame(self); buttons.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(buttons, text="Retry Failed", command=lambda: (self.destroy(), retry(failed)),
                   state="normal" if failed else "disabled").pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
