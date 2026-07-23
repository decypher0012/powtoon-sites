from __future__ import annotations

import tkinter as tk
import shlex
import copy
import json
from tkinter import filedialog, messagebox, simpledialog, ttk

from .config import (ApplicationConfig, PresetConfig, ScheduleConfig, config_to_dict,
                     save_config, validate_config_data)
from .windows_tasks import sync_tasks
from .ui_style import style_listbox
from .global_hotkey import parse_hotkey
from .workflow_features import preset_templates


class PresetEditor(tk.Toplevel):
    def __init__(self, master, choices, preset=None):
        super().__init__(master); self.title("Visual Workspace Builder"); self.geometry("900x620")
        self.transient(master); self.grab_set(); self.result = None; self.choices = choices
        self.name_var = tk.StringVar(value=preset.name if preset else "")
        self.mode_var = tk.StringVar(value=preset.run_mode if preset else "normal")
        self.stop_var = tk.BooleanVar(value=preset.stop_on_failure if preset else False)
        self.pinned_var = tk.BooleanVar(value=preset.pinned if preset else False)
        self.hotkey_var = tk.StringVar(value=preset.hotkey if preset else "")
        self.chain_var = tk.StringVar(value=preset.chain_next if preset else "")
        self.focus_var = tk.IntVar(value=preset.focus_minutes if preset else 0)
        self.close_on_end_var = tk.BooleanVar(value=preset.close_on_end if preset else False)
        self.windows_focus_var = tk.BooleanVar(value=preset.windows_focus if preset else False)
        self.notification_profile_var = tk.StringVar(value=preset.notification_profile if preset else "normal")
        self.work_start_var = tk.StringVar(value=preset.work_hours_start if preset else "")
        self.work_end_var = tk.StringVar(value=preset.work_hours_end if preset else "")
        self.parameters = copy.deepcopy(preset.parameters) if preset else []
        self.bootstrap_packages = list(preset.bootstrap_packages) if preset else []
        self.actions = copy.deepcopy(preset.actions) if preset else []
        self.browser_session = list(preset.browser_session) if preset else []
        self.window_layout = copy.deepcopy(preset.window_layout) if preset else {}
        top = ttk.Frame(self, padding=12); top.pack(fill="x")
        ttk.Label(top, text="Preset name").pack(side="left"); ttk.Entry(top, textvariable=self.name_var, width=28).pack(side="left", padx=6)
        ttk.Label(top, text="Run mode").pack(side="left", padx=(14, 4))
        ttk.Combobox(top, textvariable=self.mode_var, values=["normal", "dry-run", "step"], state="readonly", width=10).pack(side="left")
        ttk.Checkbutton(top, text="Stop after a failure", variable=self.stop_var).pack(side="left", padx=14)
        advanced = ttk.LabelFrame(self, text="Optional workflow controls", padding=8); advanced.pack(fill="x", padx=12)
        ttk.Checkbutton(advanced, text="Pin to dashboard", variable=self.pinned_var).grid(row=0, column=0, sticky="w")
        ttk.Label(advanced, text="Hotkey").grid(row=0, column=1, padx=(14, 4))
        ttk.Entry(advanced, textvariable=self.hotkey_var, width=16).grid(row=0, column=2)
        ttk.Label(advanced, text="Chain next").grid(row=0, column=3, padx=(14, 4))
        ttk.Entry(advanced, textvariable=self.chain_var, width=16).grid(row=0, column=4)
        ttk.Label(advanced, text="Focus minutes").grid(row=0, column=5, padx=(14, 4))
        ttk.Spinbox(advanced, from_=0, to=480, textvariable=self.focus_var, width=6).grid(row=0, column=6)
        ttk.Label(advanced, text="Example: Ctrl+Alt+M. A blank chain ends the sequence.",
                  style="Muted.TLabel").grid(row=1, column=0, columnspan=7, sticky="w", pady=(5, 0))
        ttk.Checkbutton(advanced, text="Close launched apps when ending", variable=self.close_on_end_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Checkbutton(advanced, text="Open Windows Focus", variable=self.windows_focus_var).grid(row=2, column=2, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Label(advanced, text="Work hours").grid(row=2, column=4, sticky="e")
        ttk.Entry(advanced, textvariable=self.work_start_var, width=6).grid(row=2, column=5)
        ttk.Entry(advanced, textvariable=self.work_end_var, width=6).grid(row=2, column=6)
        ttk.Button(advanced, text="Advanced lifecycle…", command=self.lifecycle).grid(row=3, column=0, columnspan=2, sticky="w", pady=(7, 0))
        ttk.Label(advanced, text="Notifications").grid(row=3, column=2, sticky="e", pady=(7, 0))
        ttk.Combobox(advanced, textvariable=self.notification_profile_var,
                     values=["normal", "focus", "silent"], state="readonly", width=9).grid(row=3, column=3, sticky="w", pady=(7, 0))
        body = ttk.Frame(self, padding=12); body.pack(fill="both", expand=True)
        self.available = tk.Listbox(body); self.available.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(body); controls.pack(side="left", padx=8)
        ttk.Button(controls, text="Add →", command=self.add).pack(fill="x", pady=3)
        ttk.Button(controls, text="← Remove", command=self.remove).pack(fill="x", pady=3)
        ttk.Button(controls, text="Move Up", command=lambda: self.move(-1)).pack(fill="x", pady=(20, 3))
        ttk.Button(controls, text="Move Down", command=lambda: self.move(1)).pack(fill="x", pady=3)
        ttk.Button(controls, text="Item Delay", command=self.delay).pack(fill="x", pady=(20, 3))
        ttk.Button(controls, text="Item Rules", command=self.rules).pack(fill="x", pady=3)
        self.selected = tk.Listbox(body); self.selected.pack(side="left", fill="both", expand=True)
        style_listbox(self.available, master.master_app.palette if hasattr(master, "master_app") else master.palette)
        style_listbox(self.selected, master.master_app.palette if hasattr(master, "master_app") else master.palette)
        for value in choices: self.available.insert("end", value)
        self.delays = dict(preset.item_delays) if preset else {}
        self.item_rules = copy.deepcopy(preset.item_rules) if preset else {}
        for value in (preset.items if preset else []): self.selected.insert("end", value)
        footer = ttk.Frame(self, padding=12); footer.pack(fill="x")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save Workspace", command=self.accept, style="Primary.TButton").pack(side="right", padx=6)

    def add(self):
        for index in self.available.curselection():
            value = self.available.get(index)
            if value not in self.selected.get(0, "end"): self.selected.insert("end", value)
    def remove(self):
        for index in reversed(self.selected.curselection()): self.selected.delete(index)
    def move(self, direction):
        if not self.selected.curselection(): return
        index = self.selected.curselection()[0]; target = index + direction
        if not 0 <= target < self.selected.size(): return
        value = self.selected.get(index); self.selected.delete(index); self.selected.insert(target, value); self.selected.selection_set(target)
    def delay(self):
        if not self.selected.curselection(): return
        value = self.selected.get(self.selected.curselection()[0])
        seconds = simpledialog.askfloat("Item Delay", "Seconds to wait before this item:", initialvalue=self.delays.get(value, 0), minvalue=0, parent=self)
        if seconds is not None: self.delays[value] = seconds
    def rules(self):
        if not self.selected.curselection(): return
        value = self.selected.get(self.selected.curselection()[0]); current = self.item_rules.get(value, {})
        require_network = messagebox.askyesno("Item Rules", "Require basic network connectivity for this item?", parent=self)
        weekdays = simpledialog.askstring("Item Rules", "Allowed weekdays (0=Mon … 6=Sun), comma separated:",
                                          initialvalue=",".join(map(str, current.get("weekdays", range(7)))), parent=self)
        try: parsed = list(dict.fromkeys(int(day.strip()) for day in (weekdays or "").split(",") if day.strip()))
        except ValueError: messagebox.showerror(self.title(), "Weekdays must be numbers from 0 through 6.", parent=self); return
        if not parsed or any(day not in range(7) for day in parsed): messagebox.showerror(self.title(), "Select at least one valid weekday.", parent=self); return
        start_time = simpledialog.askstring("Item Rules", "Optional earliest time (HH:MM):",
                                            initialvalue=current.get("start_time", ""), parent=self)
        end_time = simpledialog.askstring("Item Rules", "Optional latest time (HH:MM):",
                                          initialvalue=current.get("end_time", ""), parent=self)
        for clock in (start_time, end_time):
            if clock:
                try:
                    hour, minute = (int(part) for part in clock.split(":"))
                    if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError
                except ValueError:
                    messagebox.showerror(self.title(), "Times must use HH:MM.", parent=self); return
        self.item_rules[value] = {"require_network": require_network, "weekdays": parsed,
                                  "start_time": start_time or "", "end_time": end_time or ""}
    def lifecycle(self):
        packages = simpledialog.askstring("Machine Bootstrap", "WinGet package IDs, comma separated:",
                                          initialvalue=", ".join(self.bootstrap_packages), parent=self)
        if packages is not None:
            self.bootstrap_packages = [value.strip() for value in packages.split(",") if value.strip()]
        parameters = simpledialog.askstring(
            "Runtime Parameters", 'JSON list, e.g. [{"name":"client","prompt":"Client name","secret":false}]:',
            initialvalue=json.dumps(self.parameters), parent=self)
        if parameters is not None:
            try:
                parsed = json.loads(parameters)
                if not isinstance(parsed, list): raise ValueError("Expected a JSON list.")
                self.parameters = parsed
            except Exception as exc: messagebox.showerror(self.title(), f"Invalid parameters: {exc}", parent=self); return
        actions = simpledialog.askstring(
            "Approved Actions", 'JSON list of open_uri, terminal, rdp, or command actions:',
            initialvalue=json.dumps(self.actions), parent=self)
        if actions is not None:
            try:
                parsed = json.loads(actions)
                if not isinstance(parsed, list): raise ValueError("Expected a JSON list.")
                self.actions = parsed
            except Exception as exc: messagebox.showerror(self.title(), f"Invalid actions: {exc}", parent=self)
    def accept(self):
        name, items = self.name_var.get().strip(), list(self.selected.get(0, "end"))
        if not name or not items: messagebox.showerror(self.title(), "Enter a name and add at least one item.", parent=self); return
        try:
            focus_minutes = self.focus_var.get()
            if self.hotkey_var.get().strip(): parse_hotkey(self.hotkey_var.get().strip())
            if not 0 <= focus_minutes <= 480: raise ValueError("Focus minutes must be between 0 and 480.")
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror(self.title(), str(exc), parent=self); return
        self.result = PresetConfig(name, items, run_mode=self.mode_var.get(), stop_on_failure=self.stop_var.get(),
                                   item_delays={key: value for key, value in self.delays.items() if key in items},
                                   item_rules={key: value for key, value in self.item_rules.items() if key in items},
                                   pinned=self.pinned_var.get(), hotkey=self.hotkey_var.get().strip(),
                                   chain_next=self.chain_var.get().strip(), focus_minutes=focus_minutes,
                                   window_layout=self.window_layout, browser_session=self.browser_session,
                                   parameters=self.parameters, bootstrap_packages=self.bootstrap_packages,
                                   actions=self.actions, close_on_end=self.close_on_end_var.get(),
                                   windows_focus=self.windows_focus_var.get(),
                                   notification_profile=self.notification_profile_var.get(),
                                   work_hours_start=self.work_start_var.get().strip(),
                                   work_hours_end=self.work_end_var.get().strip())
        self.destroy()


class ScheduleEditor(tk.Toplevel):
    DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    def __init__(self, master, presets, schedule=None):
        super().__init__(master); self.title("Advanced Schedule"); self.transient(master); self.grab_set(); self.result = None
        self.name = tk.StringVar(value=schedule.name if schedule else ""); self.preset = tk.StringVar(value=schedule.preset if schedule else presets[0])
        self.clock = tk.StringVar(value=schedule.time if schedule else "09:00"); self.confirm = tk.IntVar(value=schedule.confirm_seconds if schedule else 10)
        self.network = tk.BooleanVar(value=schedule.require_network if schedule else False); self.enabled = tk.BooleanVar(value=schedule.enabled if schedule else True)
        frame = ttk.Frame(self, padding=14); frame.pack(fill="both", expand=True)
        for row, (label, widget) in enumerate((("Name", ttk.Entry(frame, textvariable=self.name)), ("Preset", ttk.Combobox(frame, textvariable=self.preset, values=presets, state="readonly")), ("Time (HH:MM)", ttk.Entry(frame, textvariable=self.clock)), ("Confirmation seconds", ttk.Spinbox(frame, from_=0, to=300, textvariable=self.confirm)))):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=3); widget.grid(row=row, column=1, sticky="ew", pady=3)
        current = schedule.weekdays if schedule else list(range(5)); self.days = []
        days = ttk.Frame(frame); days.grid(row=4, column=0, columnspan=2, sticky="w", pady=8)
        for index, label in enumerate(self.DAYS):
            var = tk.BooleanVar(value=index in current); self.days.append(var); ttk.Checkbutton(days, text=label, variable=var).pack(side="left")
        ttk.Checkbutton(frame, text="Require network", variable=self.network).grid(row=5, column=0, sticky="w")
        ttk.Checkbutton(frame, text="Enabled", variable=self.enabled).grid(row=5, column=1, sticky="w")
        ttk.Button(frame, text="Save", command=self.accept, style="Primary.TButton").grid(row=6, column=1, sticky="e", pady=10)
    def accept(self):
        weekdays = [index for index, value in enumerate(self.days) if value.get()]
        if not self.name.get().strip() or not weekdays: messagebox.showerror(self.title(), "Name and at least one weekday are required.", parent=self); return
        self.result = ScheduleConfig(self.name.get().strip(), self.preset.get(), self.clock.get().strip(), weekdays,
                                     self.enabled.get(), self.confirm.get(), self.network.get())
        self.destroy()


class WorkspaceManager(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("Presets, Applications, and Schedules")
        self.geometry("900x620")
        header = ttk.Frame(self, padding=(18, 16, 18, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Workspace studio", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Build launch sequences, register local tools, and control recurring routines.", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
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
        ttk.Button(footer, text="Add Templates", command=self.add_templates).pack(side="left", padx=5)
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
        style_listbox(value, self.master_app.palette)
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
        winget_id = simpledialog.askstring("Application", "Optional WinGet package ID for machine bootstrap:", parent=self) or ""
        close_on_end = messagebox.askyesno("Application", "Allow Work Launcher to close this app when ending its workspace?", parent=self)
        self.master_app.config.applications.append(
            ApplicationConfig(name.strip(), path, arguments, working.strip(), only_if_not_running=only_once,
                              winget_id=winget_id.strip(), close_on_end=close_on_end)
        )
        self._save()

    def add_preset(self):
        choices = ([f"website:{item.name}" for item in self.master_app.config.websites]
                   + [f"application:{item.name}" for item in self.master_app.config.applications])
        if not choices:
            messagebox.showwarning(self.title(), "Add a website or application first.", parent=self)
            return
        dialog = PresetEditor(self, choices); self.wait_window(dialog)
        if dialog.result:
            if any(item.name.casefold() == dialog.result.name.casefold() for item in self.master_app.config.presets):
                messagebox.showerror(self.title(), "A preset with that name already exists.", parent=self); return
            self.master_app.config.presets.append(dialog.result); self._save()

    def add_templates(self):
        existing = {item.name.casefold() for item in self.master_app.config.presets}
        additions = [item for item in preset_templates(self.master_app.config)
                     if item.items and item.name.casefold() not in existing]
        if not additions:
            messagebox.showinfo(self.title(), "No applicable new templates are available.", parent=self)
            return
        self.master_app.config.presets.extend(additions)
        self._save()
        messagebox.showinfo(self.title(), f"Added {len(additions)} starter presets.", parent=self)

    def add_schedule(self):
        if not self.master_app.config.presets:
            messagebox.showwarning(self.title(), "Create a preset first.", parent=self)
            return
        dialog = ScheduleEditor(self, [item.name for item in self.master_app.config.presets]); self.wait_window(dialog)
        if dialog.result:
            self.master_app.config.schedules.append(dialog.result)
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
                    for preset in self.master_app.config.presets:
                        if preset.chain_next == item.name:
                            preset.chain_next = ""
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
        snapshot = copy.deepcopy(self.master_app.config)
        if collection is self.master_app.config.applications:
            name = simpledialog.askstring("Edit Application", "Display name:", initialvalue=item.name, parent=self)
            if not name: return
            if any(other is not item and other.name.casefold() == name.strip().casefold() for other in collection):
                messagebox.showerror(self.title(), "That name is already in use.", parent=self); return
            item.name = name.strip()
            path = simpledialog.askstring("Edit Application", "Path:", initialvalue=item.path, parent=self)
            raw = simpledialog.askstring("Edit Application", "Arguments:", initialvalue=shlex.join(item.arguments), parent=self)
            if path: item.path = path.strip()
            if raw is not None: item.arguments = shlex.split(raw)
            winget_id = simpledialog.askstring("Edit Application", "WinGet package ID:",
                                               initialvalue=item.winget_id, parent=self)
            if winget_id is not None: item.winget_id = winget_id.strip()
            old_ref, new_ref = f"application:{old_name}", f"application:{item.name}"
            for preset in self.master_app.config.presets:
                preset.items = [new_ref if value == old_ref else value for value in preset.items]
        elif collection is self.master_app.config.presets:
            choices = ([f"website:{value.name}" for value in self.master_app.config.websites]
                       + [f"application:{value.name}" for value in self.master_app.config.applications])
            dialog = PresetEditor(self, choices, item); self.wait_window(dialog)
            if not dialog.result: return
            if any(other is not item and other.name.casefold() == dialog.result.name.casefold() for other in collection):
                messagebox.showerror(self.title(), "That name is already in use.", parent=self); return
            item.name, item.items, item.run_mode = dialog.result.name, dialog.result.items, dialog.result.run_mode
            item.stop_on_failure, item.item_delays = dialog.result.stop_on_failure, dialog.result.item_delays
            item.item_rules = dialog.result.item_rules
            item.pinned, item.hotkey = dialog.result.pinned, dialog.result.hotkey
            item.chain_next, item.focus_minutes = dialog.result.chain_next, dialog.result.focus_minutes
            item.window_layout, item.browser_session = dialog.result.window_layout, dialog.result.browser_session
            item.parameters, item.bootstrap_packages = dialog.result.parameters, dialog.result.bootstrap_packages
            item.actions, item.close_on_end = dialog.result.actions, dialog.result.close_on_end
            item.windows_focus = dialog.result.windows_focus
            item.notification_profile = dialog.result.notification_profile
            item.work_hours_start, item.work_hours_end = dialog.result.work_hours_start, dialog.result.work_hours_end
            for schedule in self.master_app.config.schedules:
                if schedule.preset == old_name: schedule.preset = item.name
            for other in self.master_app.config.presets:
                if other.chain_next == old_name: other.chain_next = item.name
        else:
            dialog = ScheduleEditor(self, [value.name for value in self.master_app.config.presets], item); self.wait_window(dialog)
            if not dialog.result: return
            if any(other is not item and other.name.casefold() == dialog.result.name.casefold() for other in collection):
                messagebox.showerror(self.title(), "That name is already in use.", parent=self); return
            item.name, item.preset, item.time, item.weekdays = dialog.result.name, dialog.result.preset, dialog.result.time, dialog.result.weekdays
            item.enabled, item.confirm_seconds, item.require_network = dialog.result.enabled, dialog.result.confirm_seconds, dialog.result.require_network
        try: self._save()
        except Exception as exc:
            self.master_app.config = snapshot
            self.master_app.workspace_launcher.config = snapshot
            self.master_app.launcher.browser_profiles = snapshot.browser_profiles
            self.refresh()
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
