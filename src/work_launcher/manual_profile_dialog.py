from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from .browser_profiles import BrowserProfile, validate_profile


class ManualProfileDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master); self.title("Configure Browser Manually"); self.transient(master); self.grab_set(); self.resizable(False, False); self.result = None
        frame = ttk.Frame(self, padding=14); frame.pack(fill="both", expand=True)
        self.name = tk.StringVar(); self.kind = tk.StringVar(value="chrome"); self.executable = tk.StringVar(); self.data = tk.StringVar(); self.profile = tk.StringVar(); self.fallback = tk.BooleanVar()
        rows = (("Friendly Name", self.name), ("Browser Type", self.kind), ("Browser Executable", self.executable),
                ("User Data Directory", self.data), ("Profile Directory or Profile Name", self.profile))
        for row, (label, variable) in enumerate(rows):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
            if row == 1: widget = ttk.Combobox(frame, textvariable=variable, state="readonly", values=["chrome","edge","brave","chromium","vivaldi","firefox"], width=43)
            else: widget = ttk.Entry(frame, textvariable=variable, width=46)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            if row == 2: ttk.Button(frame, text="Browse", command=self.browse_executable).grid(row=row, column=2, padx=4)
            if row == 3: ttk.Button(frame, text="Browse", command=self.browse_data).grid(row=row, column=2, padx=4)
        ttk.Checkbutton(frame, text="Fallback to Windows Default Browser", variable=self.fallback).grid(row=5, column=1, sticky="w")
        self.error = tk.StringVar(); ttk.Label(frame, textvariable=self.error, foreground="#b00020", wraplength=430).grid(row=6, column=0, columnspan=3, sticky="w", pady=6)
        buttons = ttk.Frame(frame); buttons.grid(row=7, column=0, columnspan=3, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=3); ttk.Button(buttons, text="Save", command=self.save).pack(side="right", padx=3)
        self.bind("<Escape>", lambda event: self.destroy()); self.bind("<Return>", lambda event: self.save())

    def browse_executable(self):
        value = filedialog.askopenfilename(parent=self, filetypes=[("Programs", "*.exe")]);
        if value: self.executable.set(value)
    def browse_data(self):
        value = filedialog.askdirectory(parent=self)
        if value: self.data.set(value)
    def save(self):
        candidate = BrowserProfile(self.name.get().strip(), self.kind.get(), self.executable.get().strip(), self.data.get().strip(), self.profile.get().strip(), self.fallback.get())
        try:
            if not candidate.name: raise ValueError("Friendly Name is required.")
            validate_profile(candidate, require_files=True); self.result = candidate; self.destroy()
        except Exception as exc: self.error.set(str(exc))
