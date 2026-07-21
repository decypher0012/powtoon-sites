from __future__ import annotations

import tkinter as tk
import shlex
import copy
from tkinter import filedialog, messagebox, simpledialog, ttk

from .config import (ApplicationConfig, PresetConfig, ScheduleConfig, config_to_dict,
                     save_config, validate_config_data)
from .windows_tasks import sync_tasks


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
        for box in (self.preset_list, self.application_list, self.schedule_list):
            box.bind("<Double-Button-1>", lambda _event: self.edit_selected())
            box.bind("<Return>", lambda _event: self.edit_selected())
            box.bind("<Delete>", lambda _event: self.delete_selected())
        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(footer, text="Add Preset", command=self.add_preset).pack(side="left")
        ttk.Button(footer, text="Add Application", command=self.add_application).pack(side="left", padx=5)
        ttk.Button(footer, text="Add Schedule", command=self.add_schedule).pack(side="left")
        ttk.Button(footer, text="Edit", command=self.edit_selected).pack(side="left", padx=(12, 5))
        ttk.Button(footer, text="Duplicate", command=self.duplicate_selected).pack(side="left")
        ttk.Button(footer, text="Enable/Disable", command=self.toggle_selected).pack(side="left", padx=5)
        ttk.Button(footer, text="Move Up", command=lambda: self.move_selected(-1)).pack(side="left")
        ttk.Button(footer, text="Move Down", command=lambda: self.move_selected(1)).pack(side="left", padx=5)
        ttk.Button(footer, text="Delete Selected", command=self.delete_selected).pack(side="left", padx=5)
        ttk.Button(footer, text="Sync Windows Tasks", command=self.sync_windows_tasks).pack(side="left", padx=5)
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self.refresh()
        self.preset_list.focus_set()

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

    def _selection(self):
        for box, collection in ((self.preset_list, self.master_app.config.presets),
                                (self.application_list, self.master_app.config.applications),
                                (self.schedule_list, self.master_app.config.schedules)):
            selected = box.curselection()
            if selected:
                index = selected[0]
                return box, collection, index, collection[index]
        return None

    def edit_selected(self):
        selected = self._selection()
        if not selected:
            return
        _box, collection, _index, item = selected
        old_name = item.name
        name = simpledialog.askstring("Edit", "Display name:", initialvalue=item.name, parent=self)
        if not name:
            return
        if any(other is not item and other.name.casefold() == name.strip().casefold() for other in collection):
            messagebox.showerror(self.title(), "That name is already in use.", parent=self); return
        snapshot = copy.deepcopy(self.master_app.config)
        item.name = name.strip()
        if collection is self.master_app.config.applications:
            path = simpledialog.askstring("Edit Application", "Path:", initialvalue=item.path, parent=self)
            raw = simpledialog.askstring("Edit Application", "Arguments:", initialvalue=shlex.join(item.arguments), parent=self)
            if path: item.path = path.strip()
            if raw is not None: item.arguments = shlex.split(raw)
            old_ref, new_ref = f"application:{old_name}", f"application:{item.name}"
            for preset in self.master_app.config.presets:
                preset.items = [new_ref if value == old_ref else value for value in preset.items]
        elif collection is self.master_app.config.presets:
            delay = simpledialog.askfloat("Edit Preset", "Delay between items (seconds):",
                                          initialvalue=item.launch_delay_seconds or 0, minvalue=0, parent=self)
            if delay is not None: item.launch_delay_seconds = delay
            for schedule in self.master_app.config.schedules:
                if schedule.preset == old_name: schedule.preset = item.name
        else:
            preset = simpledialog.askstring("Edit Schedule", "Preset:", initialvalue=item.preset, parent=self)
            clock = simpledialog.askstring("Edit Schedule", "Time (HH:MM):", initialvalue=item.time, parent=self)
            if preset: item.preset = preset.strip()
            if clock: item.time = clock.strip()
        try: self._save()
        except Exception as exc:
            self.master_app.config = snapshot
            messagebox.showerror(self.title(), str(exc), parent=self)

    def duplicate_selected(self):
        selected = self._selection()
        if not selected: return
        _box, collection, index, item = selected
        duplicate = copy.deepcopy(item); base = f"{item.name} (Copy)"; duplicate.name = base; number = 2
        names = {value.name.casefold() for value in collection}
        while duplicate.name.casefold() in names:
            duplicate.name = f"{base} {number}"; number += 1
        if collection is self.master_app.config.schedules: duplicate.last_run_date = ""
        collection.insert(index + 1, duplicate); self._save()

    def toggle_selected(self):
        selected = self._selection()
        if not selected: return
        _box, collection, _index, item = selected
        if collection is self.master_app.config.presets:
            messagebox.showinfo(self.title(), "Presets do not have an enabled setting.", parent=self); return
        item.enabled = not item.enabled; self._save()

    def move_selected(self, direction):
        selected = self._selection()
        if not selected: return
        box, collection, index, _item = selected; target = index + direction
        if not 0 <= target < len(collection): return
        collection[index], collection[target] = collection[target], collection[index]
        self._save(); box.selection_set(target); box.see(target)

    def sync_windows_tasks(self):
        errors = sync_tasks(self.master_app.config.schedules, self.master_app.executable_path)
        if errors: messagebox.showerror(self.title(), "Some tasks could not be created:\n\n" + "\n".join(errors), parent=self)
        else: messagebox.showinfo(self.title(), "Windows tasks synchronized. Scheduled routines can now wake Work Launcher.", parent=self)
