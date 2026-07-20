from __future__ import annotations

import tkinter as tk
import shlex
from tkinter import filedialog, messagebox, simpledialog, ttk

from .config import (ApplicationConfig, PresetConfig, ScheduleConfig, config_to_dict,
                     save_config, validate_config_data)


class WorkspaceManager(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Presets, Applications, and Schedules")
        self.geometry("720x520")
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        self.preset_list = self._page(notebook, "Presets")
        self.application_list = self._page(notebook, "Applications")
        self.schedule_list = self._page(notebook, "Schedules")
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="Add Preset", command=self.add_preset).pack(side="left")
        ttk.Button(footer, text="Add Application", command=self.add_application).pack(side="left", padx=5)
        ttk.Button(footer, text="Add Schedule", command=self.add_schedule).pack(side="left")
        ttk.Button(footer, text="Delete Selected", command=self.delete_selected).pack(side="left", padx=5)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self.refresh()

    def _page(self, notebook, title):
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)
        value = tk.Listbox(frame)
        value.pack(fill="both", expand=True)
        return value

    def refresh(self):
        for box in (self.preset_list, self.application_list, self.schedule_list):
            box.delete(0, "end")
        for item in self.master_app.config.presets:
            self.preset_list.insert("end", f"{item.name} — {len(item.items)} items")
        for item in self.master_app.config.applications:
            self.application_list.insert("end", f"{item.name} — {item.path}")
        for item in self.master_app.config.schedules:
            self.schedule_list.insert("end", f"{item.name} — {item.time} → {item.preset}")

    def _save(self):
        validate_config_data(config_to_dict(self.master_app.config))
        save_config(self.master_app.config_path, self.master_app.config)
        self.master_app.refresh_preset_controls()
        self.refresh()

    def add_application(self):
        path = filedialog.askopenfilename(parent=self, title="Choose an application or document")
        if not path:
            return
        name = simpledialog.askstring("Application", "Display name:", parent=self)
        if not name:
            return
        if any(item.name.casefold() == name.strip().casefold() for item in self.master_app.config.applications):
            messagebox.showerror(self.title(), "An application with that name already exists.", parent=self)
            return
        raw_arguments = simpledialog.askstring("Application", "Optional arguments:", parent=self) or ""
        working = simpledialog.askstring("Application", "Optional working directory:", parent=self) or ""
        try:
            arguments = shlex.split(raw_arguments)
        except ValueError as exc:
            messagebox.showerror(self.title(), f"Invalid arguments: {exc}", parent=self)
            return
        only_once = messagebox.askyesno("Application", "Skip this application when it is already running?", parent=self)
        self.master_app.config.applications.append(
            ApplicationConfig(name.strip(), path, arguments, working.strip(), only_if_not_running=only_once)
        )
        self._save()

    def add_preset(self):
        name = simpledialog.askstring("Preset", "Preset name:", parent=self)
        if not name:
            return
        if any(item.name.casefold() == name.strip().casefold() for item in self.master_app.config.presets):
            messagebox.showerror(self.title(), "A preset with that name already exists.", parent=self)
            return
        choices = ([f"website:{item.name}" for item in self.master_app.config.websites]
                   + [f"application:{item.name}" for item in self.master_app.config.applications])
        if not choices:
            messagebox.showwarning(self.title(), "Add a website or application first.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Select preset items")
        box = tk.Listbox(dialog, selectmode="extended", width=70, height=18)
        box.pack(padx=12, pady=12)
        for value in choices:
            box.insert("end", value)
        def accept():
            selected = [choices[index] for index in box.curselection()]
            if selected:
                self.master_app.config.presets.append(PresetConfig(name.strip(), selected))
                self._save()
                dialog.destroy()
        ttk.Button(dialog, text="Create Preset", command=accept).pack(pady=(0, 12))

    def add_schedule(self):
        if not self.master_app.config.presets:
            messagebox.showwarning(self.title(), "Create a preset first.", parent=self)
            return
        name = simpledialog.askstring("Schedule", "Schedule name:", parent=self)
        preset = simpledialog.askstring("Schedule", "Exact preset name:", parent=self,
                                        initialvalue=self.master_app.config.presets[0].name)
        clock = simpledialog.askstring("Schedule", "Time (HH:MM, 24-hour):", parent=self, initialvalue="09:00")
        if name and preset and clock:
            self.master_app.config.schedules.append(ScheduleConfig(name.strip(), preset.strip(), clock.strip()))
            try:
                self._save()
            except Exception as exc:
                self.master_app.config.schedules.pop()
                messagebox.showerror(self.title(), str(exc), parent=self)

    def delete_selected(self):
        targets = ((self.preset_list, self.master_app.config.presets),
                   (self.application_list, self.master_app.config.applications),
                   (self.schedule_list, self.master_app.config.schedules))
        for box, collection in targets:
            selected = box.curselection()
            if selected:
                item = collection[selected[0]]
                if collection is self.master_app.config.applications:
                    reference = f"application:{item.name}"
                    for preset in self.master_app.config.presets:
                        preset.items = [value for value in preset.items if value != reference]
                elif collection is self.master_app.config.presets:
                    self.master_app.config.schedules = [
                        schedule for schedule in self.master_app.config.schedules if schedule.preset != item.name
                    ]
                del collection[selected[0]]
                self._save()
                return
