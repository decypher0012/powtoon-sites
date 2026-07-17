from __future__ import annotations

import logging
import sys
import time
import tkinter as tk
import copy
import queue
import threading
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from urllib.parse import urlparse

from .config import AppConfig, WebsiteConfig, get_config_path, load_config, save_config
from .constants import APP_NAME, DEFAULT_MIN_WINDOW_HEIGHT, DEFAULT_MIN_WINDOW_WIDTH, UPDATE_GITHUB_OWNER, UPDATE_GITHUB_REPOSITORY, VISUAL_STYLES
from .launcher import WebsiteLauncher
from .logging_config import configure_logging
from .settings import reset_to_defaults, save_settings
from .startup import set_startup_enabled
from .browser_profiles import BrowserProfile, validate_profile
from .browser_discovery import discover_chrome
from .browser_launcher import BrowserLauncher
from .website_manager import (UndoHistory, add_website, bulk_update, create_timestamped_backup,
    delete_websites, duplicate_website, edit_website, export_json, import_websites,
    move_websites, preview_import, search_websites, validate_website)
from .website_manager import websites_for_group
from .detected_profiles_dialog import DetectedProfilesDialog
from .setup_wizard import SetupWizard
from .setup_service import should_run_setup
from .update_manager import UpdateManager
from .update_diagnostics import UpdateDiagnosticsDialog
from .update_ui import UpdateDialog
from .ui_style import apply_visual_style, style_canvas, style_listbox, style_text
from .version import __version__
from .update_status import consume_update_status
from .update_download import cleanup_stale_updates
from .profile_health import get_profile_health, stale_profile_warning, validate_profile_assignment


class WebsiteDialog(tk.Toplevel):
    def __init__(self, master, title: str, profiles, website: WebsiteConfig | None = None):
        super().__init__(master); self.title(title); self.transient(master); self.grab_set(); self.resizable(False, False)
        self.result = None; self.profiles = profiles; website = website or WebsiteConfig("", "", True, True)
        self.name_var = tk.StringVar(value=website.name); self.url_var = tk.StringVar(value=website.url)
        self.enabled_var = tk.BooleanVar(value=website.enabled); self.selected_var = tk.BooleanVar(value=website.selected)
        self.group_var = tk.StringVar(value=website.launch_group)
        self.profile_names = {profile.name: key for key, profile in profiles.items()}
        current = profiles.get(website.browser_profile); self.profile_var = tk.StringVar(value=current.name if current else "")
        frame = ttk.Frame(self, padding=14, style="Card.TFrame"); frame.pack(fill="both", expand=True)
        fields = (("Display Name", ttk.Entry(frame, textvariable=self.name_var, width=52)),
                  ("URL", ttk.Entry(frame, textvariable=self.url_var, width=52)),
                  ("Browser Profile", ttk.Combobox(frame, textvariable=self.profile_var, values=list(self.profile_names), state="readonly", width=49)),
                  ("Launch Group (Optional)", ttk.Combobox(frame, textvariable=self.group_var,
                    values=["", "Daily Work", "Morning", "Meetings", "Admin", "Google", "HubSpot", "Custom"], width=49)))
        for row, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=3); widget.grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(frame, text="Enabled", variable=self.enabled_var).grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(frame, text="Selected by Default", variable=self.selected_var).grid(row=5, column=1, sticky="w")
        self.error_var = tk.StringVar(); ttk.Label(frame, textvariable=self.error_var, foreground="#b00020", wraplength=420, style="Card.TLabel").grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
        buttons = ttk.Frame(frame); buttons.grid(row=7, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=3)
        ttk.Button(buttons, text="Save", command=self.accept, style="Primary.TButton").pack(side="right", padx=3)
        self.bind("<Escape>", lambda event: self.destroy()); self.bind("<Return>", lambda event: self.accept())
        fields[0][1].focus_set(); self.wait_visibility()

    def accept(self):
        profile = self.profile_names.get(self.profile_var.get())
        if not self.name_var.get().strip(): self.error_var.set("Display Name is required."); return
        parsed = urlparse(self.url_var.get().strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc: self.error_var.set("Enter a valid http:// or https:// URL."); return
        if not profile: self.error_var.set("Select an existing Browser Profile."); return
        try: validate_profile_assignment(AppConfig(browser_profiles=self.profiles), profile)
        except Exception as exc: self.error_var.set(f"Selected browser profile is unavailable: {exc}"); return
        self.result = WebsiteConfig(self.name_var.get().strip(), self.url_var.get().strip(), self.enabled_var.get(),
                                    self.selected_var.get(), profile, self.group_var.get().strip())
        self.destroy()


class SettingsWindow(tk.Toplevel):
    def __init__(self, master: "WorkLauncherApp") -> None:
        super().__init__(master)
        self.master_app = master
        self.original_config = copy.deepcopy(master.config)
        self.dirty_sections: set[str] = set()
        self.title(f"{APP_NAME} Settings")
        self.resizable(True, True)
        self.geometry(f"900x{min(900,max(600,self.winfo_screenheight()-100))}")
        self.transient(master)
        self.grab_set()
        self.undo_history = UndoHistory()
        self.visible_indices: list[int] = []
        self.bind("<Escape>", lambda event: self.destroy())
        self._palette = self.master_app.palette
        self._build()

    def _build(self) -> None:
        canvas=tk.Canvas(self,highlightthickness=0); style_canvas(canvas, self._palette); scrollbar=ttk.Scrollbar(self,orient="vertical",command=canvas.yview); canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right",fill="y"); canvas.pack(side="left",fill="both",expand=True)
        frame=ttk.Frame(canvas,padding=12); window=canvas.create_window((0,0),window=frame,anchor="nw")
        frame.bind("<Configure>",lambda event:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda event:canvas.itemconfigure(window,width=event.width))
        search = ttk.Frame(frame); search.pack(fill="x")
        ttk.Label(search, text="Search Websites").pack(side="left")
        self.search_var = tk.StringVar(); self.search_var.trace_add("write", lambda *_: self.refresh())
        ttk.Entry(search, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(8, 0))
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True, pady=(10, 10))
        self.listbox = tk.Listbox(list_frame, height=12, selectmode="extended")
        style_listbox(self.listbox, self._palette)
        self.listbox.pack(side="left", fill="both", expand=True)
        btns = ttk.Frame(list_frame)
        btns.pack(side="left", fill="y", padx=(10, 0))
        for text, command in (("Add Website", self.add_site), ("Edit Website", self.edit_site),
                              ("Delete Website(s)", self.delete_sites), ("Duplicate Website", self.duplicate_site),
                              ("Enable", self.enable_selected), ("Disable", self.disable_selected)):
            ttk.Button(btns, text=text, command=command).pack(fill="x", pady=2)
        ttk.Button(btns, text="Move Up", command=self.move_up).pack(fill="x", pady=2)
        ttk.Button(btns, text="Move Down", command=self.move_down).pack(fill="x", pady=2)
        ttk.Button(btns, text="Test Website", command=self.test_website).pack(fill="x", pady=(8, 2))
        ttk.Button(btns, text="Import Websites", command=self.import_sites).pack(fill="x", pady=2)
        ttk.Button(btns, text="Export Websites", command=self.export_sites).pack(fill="x", pady=2)
        ttk.Button(btns, text="Undo", command=self.undo).pack(fill="x", pady=(8, 2))
        ttk.Label(btns, text="Browser profile").pack(anchor="w", pady=(12, 2))
        self.site_profile_var = tk.StringVar()
        self.site_profile_combo = ttk.Combobox(btns, textvariable=self.site_profile_var, state="readonly", width=23)
        self.site_profile_combo.pack(fill="x")
        self.site_profile_combo.bind("<<ComboboxSelected>>", self.assign_site_profile)
        self.listbox.bind("<<ListboxSelect>>", self.on_site_selected)
        profiles = ttk.LabelFrame(frame, text="Browser Profiles", padding=8)
        profiles.pack(fill="x", pady=(0, 10))
        self.profile_list = tk.Listbox(profiles, height=4)
        style_listbox(self.profile_list, self._palette)
        self.profile_list.pack(side="left", fill="x", expand=True)
        self.profile_list.bind("<<ListboxSelect>>", self.on_profile_selected)
        profile_buttons = ttk.Frame(profiles)
        profile_buttons.pack(side="left", padx=(8, 0))
        for text, command in (("Add", self.add_profile), ("Edit", self.edit_profile),
                              ("Duplicate", self.duplicate_profile), ("Delete", self.delete_profile),
                              ("Remap", self.remap_profile),
                              ("Test Profile (opens tab)", self.test_profile),
                              ("Scan Browsers", self.scan_profiles), ("Rescan Profiles", self.scan_profiles),
                              ("Import Detected Profile", self.scan_profiles), ("Run Setup Wizard Again", self.run_setup_wizard)):
            ttk.Button(profile_buttons, text=text, command=command).pack(fill="x", pady=1)
        self.profile_status_var=tk.StringVar(value="Select a profile to view its availability and usage.")
        ttk.Label(frame,textvariable=self.profile_status_var,wraplength=820).pack(fill="x",pady=(0,8))
        form = ttk.Frame(frame)
        form.pack(fill="x")
        self.delay_var = tk.StringVar(value=str(self.master_app.config.settings.launch_delay_seconds))
        self.cooldown_var = tk.StringVar(value=str(self.master_app.config.settings.duplicate_launch_cooldown_seconds))
        ttk.Label(form, text="Launch delay seconds").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.delay_var, width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Duplicate cooldown seconds").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.cooldown_var, width=12).grid(row=1, column=1, sticky="w")
        self.theme_var = tk.StringVar(value=self.master_app.config.settings.theme)
        self.visual_style_var = tk.StringVar(value=self.master_app.config.settings.visual_style)
        ttk.Label(form, text="Theme").grid(row=2, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.theme_var, values=["system", "light", "dark"], state="readonly", width=10).grid(row=2, column=1, sticky="w")
        ttk.Label(form, text="Visual Style").grid(row=2, column=2, sticky="w", padx=(18, 0))
        ttk.Combobox(form, textvariable=self.visual_style_var, values=list(VISUAL_STYLES), state="readonly", width=12).grid(row=2, column=3, sticky="w")
        self.remember_var = tk.BooleanVar(value=self.master_app.config.settings.remember_window_position)
        self.startup_var = tk.BooleanVar(value=self.master_app.config.settings.launch_with_windows)
        ttk.Checkbutton(form, text="Remember window position", variable=self.remember_var).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Launch Work Launcher when Windows starts", variable=self.startup_var).grid(row=4, column=0, columnspan=2, sticky="w")
        updates = ttk.LabelFrame(frame, text="Updates", padding=8); updates.pack(fill="x", pady=(8, 0))
        self.update_channel_var=tk.StringVar(value=self.master_app.config.updates.channel); self.update_policy_var=tk.StringVar(value=self.master_app.config.updates.policy)
        self.update_install_var=tk.StringVar(value=self.master_app.config.updates.installation_kind)
        self.update_check_var=tk.BooleanVar(value=self.master_app.config.updates.automatically_check); self.update_download_var=tk.BooleanVar(value=self.master_app.config.updates.automatically_download)
        ttk.Label(updates,text=f"Current Version: {__version__}").grid(row=0,column=0,columnspan=2,sticky="w")
        self.latest_version_var=tk.StringVar(); self.last_checked_var=tk.StringVar(); self.refresh_update_status()
        ttk.Label(updates,textvariable=self.latest_version_var).grid(row=0,column=2,columnspan=2,sticky="w")
        ttk.Label(updates,textvariable=self.last_checked_var).grid(row=1,column=0,columnspan=4,sticky="w")
        ttk.Label(updates,text="Channel").grid(row=3,column=0,sticky="w"); ttk.Combobox(updates,textvariable=self.update_channel_var,values=["stable","beta"],state="readonly",width=10).grid(row=3,column=1,sticky="w")
        ttk.Label(updates,text="Policy").grid(row=3,column=2,sticky="w"); ttk.Combobox(updates,textvariable=self.update_policy_var,values=["notify","automatic","manual"],state="readonly",width=12).grid(row=3,column=3,sticky="w")
        ttk.Label(updates,text="Installation Type").grid(row=4,column=0,sticky="w"); ttk.Label(updates,textvariable=self.update_install_var).grid(row=4,column=1,sticky="w")
        ttk.Checkbutton(updates,text="Automatically check every 24 hours",variable=self.update_check_var).grid(row=5,column=0,columnspan=2,sticky="w")
        ttk.Checkbutton(updates,text="Automatically download updates",variable=self.update_download_var).grid(row=5,column=2,columnspan=2,sticky="w")
        ttk.Button(updates,text="Check Now",command=self.check_updates).grid(row=6,column=0,sticky="w",pady=3)
        ttk.Button(updates,text="View Release Notes",command=self.view_release_notes).grid(row=6,column=1,columnspan=2,sticky="w",pady=3)
        ttk.Button(updates,text="About",command=self.show_about).grid(row=6,column=3,sticky="e",pady=3)
        ttk.Button(updates,text="Clear Skipped Version",command=self.clear_skipped_version).grid(row=7,column=0,sticky="w",pady=3)
        ttk.Button(updates,text="Repair Update Settings",command=self.repair_update_settings).grid(row=7,column=1,sticky="w",pady=3)
        ttk.Button(updates,text="Update Diagnostics",command=self.show_update_diagnostics).grid(row=7,column=2,columnspan=2,sticky="w",pady=3)
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Restore Defaults", command=self.restore_defaults).pack(side="left")
        ttk.Button(actions, text="Save", command=self.save).pack(side="right")
        self.refresh_profiles()
        self.refresh()

    def _selected_index(self) -> int | None:
        sel = self.listbox.curselection()
        return self.visible_indices[sel[0]] if sel else None

    def _selected_indices(self) -> list[int]:
        return [self.visible_indices[index] for index in self.listbox.curselection()]

    def _persist_websites(self, destructive: bool = False) -> None:
        if destructive: create_timestamped_backup(self.master_app.config_path)
        save_config(self.master_app.config_path, self.master_app.config)
        self.master_app.refresh_ui(); self.refresh()

    def add_site(self) -> None:
        dialog = WebsiteDialog(self, "Add Website", self.master_app.config.browser_profiles); self.wait_window(dialog)
        if dialog.result:
            try:
                warnings = add_website(self.master_app.config, dialog.result); self._persist_websites()
                if warnings: messagebox.showwarning(APP_NAME, "\n".join(warnings), parent=self)
            except Exception as exc: messagebox.showerror(APP_NAME, str(exc), parent=self)

    def edit_site(self) -> None:
        idx = self._selected_index()
        if idx is None: return
        dialog = WebsiteDialog(self, "Edit Website", self.master_app.config.browser_profiles, self.master_app.config.websites[idx]); self.wait_window(dialog)
        if dialog.result:
            try:
                warnings = edit_website(self.master_app.config, idx, dialog.result); self._persist_websites(destructive=True)
                if warnings: messagebox.showwarning(APP_NAME, "\n".join(warnings), parent=self)
            except Exception as exc: messagebox.showerror(APP_NAME, str(exc), parent=self)

    def delete_sites(self) -> None:
        indices = self._selected_indices()
        if not indices: return
        names = [self.master_app.config.websites[index].name for index in indices]
        prompt = f'Delete website "{names[0]}"?' if len(names) == 1 else f"Delete {len(names)} selected websites?"
        if not messagebox.askyesno(APP_NAME, prompt, parent=self): return
        self.undo_history.remember(self.master_app.config); create_timestamped_backup(self.master_app.config_path)
        delete_websites(self.master_app.config, indices); self._persist_websites()

    def duplicate_site(self) -> None:
        idx = self._selected_index()
        if idx is not None: duplicate_website(self.master_app.config, idx); self._persist_websites()

    def enable_selected(self) -> None:
        indices = self._selected_indices()
        if indices: create_timestamped_backup(self.master_app.config_path); bulk_update(self.master_app.config, indices, enabled=True); self._persist_websites()

    def disable_selected(self) -> None:
        indices = self._selected_indices()
        if indices: create_timestamped_backup(self.master_app.config_path); bulk_update(self.master_app.config, indices, enabled=False); self._persist_websites()

    def move_up(self) -> None:
        selected = move_websites(self.master_app.config, self._selected_indices(), -1)
        if selected: create_timestamped_backup(self.master_app.config_path); self._persist_websites(); self.refresh(select_indices=selected)

    def move_down(self) -> None:
        selected = move_websites(self.master_app.config, self._selected_indices(), 1)
        if selected: create_timestamped_backup(self.master_app.config_path); self._persist_websites(); self.refresh(select_indices=selected)

    def restore_defaults(self) -> None:
        self.undo_history.remember(self.master_app.config)
        create_timestamped_backup(self.master_app.config_path)
        self.master_app.config = reset_to_defaults()
        self._persist_websites()

    def refresh(self, select: int | None = None, select_indices: list[int] | None = None) -> None:
        self.listbox.delete(0, "end")
        self.visible_indices = search_websites(self.master_app.config, self.search_var.get())
        for index in self.visible_indices:
            site = self.master_app.config.websites[index]; profile = self.master_app.config.browser_profiles.get(site.browser_profile)
            self.listbox.insert("end", f"{site.name} | {'Enabled' if site.enabled else 'Disabled'} | {profile.name if profile else site.browser_profile} | {site.url}")
        for target in select_indices or ([select] if select is not None else []):
            if target in self.visible_indices: self.listbox.selection_set(self.visible_indices.index(target))
        if select is not None: self.on_site_selected()

    def test_website(self) -> None:
        idx = self._selected_index()
        if idx is None: return
        self.master_app.set_status("Testing website..."); result = self.master_app.launcher.open_website(self.master_app.config.websites[idx])
        self.master_app.set_status("Website opened successfully." if result.success else "Unable to launch website.")

    def import_sites(self) -> None:
        path = filedialog.askopenfilename(title="Import Websites", filetypes=[("JSON", "*.json")], parent=self)
        if not path: return
        try:
            incoming = preview_import(Path(path), self.master_app.config)
            preview = "\n".join(f"• {site.name}" for site in incoming[:12])
            if len(incoming) > 12: preview += f"\n… and {len(incoming)-12} more"
            if not messagebox.askyesno(APP_NAME, f"Import preview ({len(incoming)} websites):\n\n{preview}\n\nContinue?", parent=self): return
            replace = messagebox.askyesno(APP_NAME, "Replace existing websites? Choose No to merge.", parent=self)
            skip_names = messagebox.askyesno(APP_NAME, "Skip duplicate display names?", parent=self)
            skip_urls = messagebox.askyesno(APP_NAME, "Skip duplicate URLs?", parent=self)
            self.undo_history.remember(self.master_app.config); create_timestamped_backup(self.master_app.config_path)
            count = import_websites(self.master_app.config, incoming, replace=replace, skip_duplicate_names=skip_names, skip_duplicate_urls=skip_urls)
            self._persist_websites(); messagebox.showinfo(APP_NAME, f"Imported {count} websites.", parent=self)
        except Exception as exc: messagebox.showerror(APP_NAME, f"Could not import websites: {exc}", parent=self)

    def export_sites(self) -> None:
        entire = messagebox.askyesno(APP_NAME, "Export the entire configuration? Choose No for websites only.", parent=self)
        path = filedialog.asksaveasfilename(title="Export JSON", defaultextension=".json", filetypes=[("JSON", "*.json")], parent=self)
        if path:
            try: export_json(Path(path), self.master_app.config, entire); messagebox.showinfo(APP_NAME, "Export complete.", parent=self)
            except Exception as exc: messagebox.showerror(APP_NAME, f"Could not export: {exc}", parent=self)

    def undo(self) -> None:
        if self.undo_history.undo(self.master_app.config): self._persist_websites(); self.master_app.set_status("Website change undone.")
        else: self.master_app.set_status("Nothing to undo.")

    def refresh_profiles(self) -> None:
        self.profile_list.delete(0, "end")
        self.profile_ids = list(self.master_app.config.browser_profiles)
        for key in self.profile_ids:
            profile = self.master_app.config.browser_profiles[key]
            health = get_profile_health(self.master_app.config, key)
            state = "Valid" if health.available else "Unavailable"
            detail = profile.profile_directory or profile.type
            self.profile_list.insert("end", f"{profile.name} [{state} — {detail}] ({key})")
        self.profile_labels = {self.master_app.config.browser_profiles[key].name: key for key in self.profile_ids}
        self.site_profile_combo.configure(values=list(self.profile_labels))

    def on_site_selected(self, event=None) -> None:
        idx = self._selected_index()
        if idx is not None:
            key = self.master_app.config.websites[idx].browser_profile
            profile = self.master_app.config.browser_profiles.get(key)
            self.site_profile_var.set(profile.name if profile else "")

    def assign_site_profile(self, event=None) -> None:
        indices = self._selected_indices()
        key = self.profile_labels.get(self.site_profile_var.get())
        if indices and key:
            try: validate_profile_assignment(self.master_app.config, key)
            except Exception as exc: messagebox.showerror(APP_NAME, f"Cannot assign an unavailable browser profile: {exc}", parent=self); return
            create_timestamped_backup(self.master_app.config_path)
            bulk_update(self.master_app.config, indices, browser_profile=key); self.dirty_sections.add("websites"); self._persist_websites()

    def _profile_index(self) -> int | None:
        selection = self.profile_list.curselection()
        return selection[0] if selection else None

    def on_profile_selected(self,event=None) -> None:
        idx=self._profile_index()
        if idx is None: return
        key=self.profile_ids[idx]; profile=self.master_app.config.browser_profiles[key]; health=get_profile_health(self.master_app.config,key)
        usage=f"Assigned to {len(health.referenced_websites)} website(s)" if health.referenced_websites else "Not assigned to any website"
        self.profile_status_var.set(f"{'Available' if health.available else 'Unavailable'} — {health.reason} — {usage}")

    def _edit_values(self, key: str, profile: BrowserProfile) -> tuple[str, BrowserProfile] | None:
        new_key = simpledialog.askstring(APP_NAME, "Profile ID", initialvalue=key, parent=self)
        if not new_key:
            return None
        name = simpledialog.askstring(APP_NAME, "Display name", initialvalue=profile.name, parent=self)
        browser_type = simpledialog.askstring(APP_NAME, "Browser type (system or chrome)", initialvalue=profile.type, parent=self)
        supported = {"system", "chrome", "edge", "brave", "chromium", "vivaldi", "firefox"}
        if not name or browser_type not in supported:
            messagebox.showerror(APP_NAME, "Name is required and type must be system, chrome, edge, brave, chromium, vivaldi, or firefox.", parent=self)
            return None
        executable, user_data, directory, fallback = "", "", "", False
        if browser_type != "system":
            executable = filedialog.askopenfilename(title="Select browser executable", filetypes=[("Programs", "*.exe")], parent=self)
            user_data = filedialog.askdirectory(title="Select Browser User Data directory", parent=self) or profile.user_data_dir
            directory = simpledialog.askstring(APP_NAME, "Profile Directory or Firefox Profile Name",
                                               initialvalue=profile.profile_directory, parent=self) or ""
            fallback = messagebox.askyesno(APP_NAME, "Allow explicit fallback to the Windows default browser if Chrome fails?", parent=self)
        result = BrowserProfile(name.strip(), browser_type, executable, user_data, directory, fallback)
        try: validate_profile(result, discover_chrome, require_files=result.type != "system")
        except Exception as exc: messagebox.showerror(APP_NAME, f"Browser profile is unavailable: {exc}", parent=self); return None
        return new_key.strip(), result

    def add_profile(self) -> None:
        result = self._edit_values("new-profile", BrowserProfile("New Browser Profile", "chrome"))
        if result:
            key, profile = result
            if key in self.master_app.config.browser_profiles:
                messagebox.showerror(APP_NAME, "That profile ID already exists.", parent=self); return
            self.master_app.config.browser_profiles[key] = profile
            self.dirty_sections.add("browser_profiles")
            self.refresh_profiles()

    def edit_profile(self) -> None:
        idx = self._profile_index()
        if idx is None: return
        old_key = self.profile_ids[idx]
        result = self._edit_values(old_key, self.master_app.config.browser_profiles[old_key])
        if not result: return
        key, profile = result
        if key != old_key and key in self.master_app.config.browser_profiles:
            messagebox.showerror(APP_NAME, "That profile ID already exists.", parent=self); return
        del self.master_app.config.browser_profiles[old_key]
        self.master_app.config.browser_profiles[key] = profile
        for site in self.master_app.config.websites:
            if site.browser_profile == old_key: site.browser_profile = key
        self.dirty_sections.update({"browser_profiles", "websites"})
        self.refresh_profiles()

    def duplicate_profile(self) -> None:
        idx = self._profile_index()
        if idx is None: return
        key = self.profile_ids[idx]
        result = self._edit_values(key + "-copy", self.master_app.config.browser_profiles[key])
        if result:
            new_key, profile = result
            if new_key in self.master_app.config.browser_profiles:
                messagebox.showerror(APP_NAME, "That profile ID already exists.", parent=self); return
            self.master_app.config.browser_profiles[new_key] = profile
            self.dirty_sections.add("browser_profiles")
            self.refresh_profiles()

    def delete_profile(self) -> None:
        idx = self._profile_index()
        if idx is None: return
        key = self.profile_ids[idx]
        used = [site.name for site in self.master_app.config.websites if site.browser_profile == key]
        if used:
            messagebox.showerror(APP_NAME, "Cannot delete an in-use profile. Reassign: " + ", ".join(used), parent=self); return
        del self.master_app.config.browser_profiles[key]
        self.dirty_sections.add("browser_profiles")
        self.refresh_profiles()

    def test_profile(self) -> None:
        idx = self._profile_index()
        if idx is None: return
        profile = self.master_app.config.browser_profiles[self.profile_ids[idx]]
        if not messagebox.askyesno(APP_NAME, "Open https://www.google.com/ in this browser profile?", parent=self): return
        try:
            BrowserLauncher().launch(profile, ["https://www.google.com/"], ["Browser profile test"])
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Browser profile test failed: {exc}", parent=self)

    def _save_update_fields(self):
        updates=self.master_app.config.updates
        updates.channel=self.update_channel_var.get(); updates.policy=self.update_policy_var.get(); updates.automatically_check=self.update_check_var.get(); updates.automatically_download=self.update_download_var.get()
        updates.installation_kind=self.master_app.update_manager.config.updates.installation_kind
        save_config(self.master_app.config_path,self.master_app.config)
        self.master_app.refresh_update_summary()
    def check_updates(self): self._save_update_fields(); self.master_app.check_for_updates(force=True)
    def view_release_notes(self):
        release=self.master_app.update_manager.latest
        if release: UpdateDialog(self.master_app,release,self.master_app.config,self.master_app.config_path)
        else: messagebox.showinfo(APP_NAME,"Check for updates first. No newer release is currently loaded.",parent=self)
    def show_about(self): messagebox.showinfo(f"About {APP_NAME}",f"{APP_NAME}\nVersion {__version__}",parent=self)
    def clear_skipped_version(self):
        self.master_app.config.updates.skipped_version=""; save_config(self.master_app.config_path,self.master_app.config); self.master_app.set_status("Skipped update version cleared.")
        self.refresh_update_status()
    def refresh_update_status(self):
        if not hasattr(self,"latest_version_var"): return
        snapshot=self.master_app.update_manager.snapshot()
        self.latest_version_var.set(f"Latest Version: {snapshot['latest_version']} ({snapshot['latest_release_date']})")
        self.last_checked_var.set(f"Last Checked: {snapshot['last_checked']} | Next Check: {snapshot['next_check']} | Error: {snapshot['last_error']}")

    def show_update_diagnostics(self):
        UpdateDiagnosticsDialog(self, self.master_app.update_manager.snapshot(), self.master_app.config, self.master_app.config_path)

    def repair_update_settings(self):
        if not messagebox.askyesno(APP_NAME, "Restore the built-in update settings and clear local update state?", parent=self): return
        self.master_app.config.updates.provider = "github"
        self.master_app.config.updates.owner = UPDATE_GITHUB_OWNER
        self.master_app.config.updates.repository = UPDATE_GITHUB_REPOSITORY
        self.master_app.config.updates.last_checked = ""
        self.master_app.config.updates.skipped_version = ""
        save_config(self.master_app.config_path, self.master_app.config)
        self.master_app.set_status("Update settings repaired.")
        self.master_app.refresh_update_summary()
        self.refresh_update_status()

    def scan_profiles(self) -> None:
        before=copy.deepcopy(self.master_app.config.browser_profiles)
        dialog=DetectedProfilesDialog(self,self.master_app.config,self.master_app.config_path,self.add_profile); self.wait_window(dialog)
        if before != self.master_app.config.browser_profiles: self.dirty_sections.add("browser_profiles")
        self.refresh_profiles()

    def remap_profile(self) -> None:
        idx=self._profile_index()
        if idx is None: return
        before=copy.deepcopy(self.master_app.config.browser_profiles)
        dialog=DetectedProfilesDialog(self,self.master_app.config,self.master_app.config_path,self.add_profile,self.profile_ids[idx]); self.wait_window(dialog)
        if before != self.master_app.config.browser_profiles: self.dirty_sections.add("browser_profiles")
        self.refresh_profiles(); self.master_app.launcher.browser_profiles=self.master_app.config.browser_profiles

    def run_setup_wizard(self) -> None:
        SetupWizard(self.master_app, self.master_app.config, self.master_app.config_path,
                    on_complete=lambda: (self.master_app.refresh_ui(), self.refresh_profiles()), manual_callback=self.add_profile)

    def save(self) -> None:
        try:
            delay=float(self.delay_var.get()); cooldown=float(self.cooldown_var.get())
            if delay < 0 or cooldown < 0: raise ValueError("Launch delay and duplicate cooldown cannot be negative.")
            original=self.original_config; config=self.master_app.config
            general_dirty=(delay != original.settings.launch_delay_seconds or cooldown != original.settings.duplicate_launch_cooldown_seconds
                or self.theme_var.get() != original.settings.theme or self.visual_style_var.get() != original.settings.visual_style
                or self.remember_var.get() != original.settings.remember_window_position)
            startup_dirty=self.startup_var.get() != original.settings.launch_with_windows
            update_values=(self.update_channel_var.get(),self.update_policy_var.get(),
                           self.update_check_var.get(),self.update_download_var.get())
            original_updates=(original.updates.channel,original.updates.policy,
                              original.updates.automatically_check,original.updates.automatically_download)
            updates_dirty=update_values != original_updates
            changed_profiles=[key for key,profile in config.browser_profiles.items()
                              if key not in original.browser_profiles or profile != original.browser_profiles[key]]
            for key in changed_profiles: validate_profile_assignment(config,key)
            if general_dirty: self.dirty_sections.add("general")
            if startup_dirty: self.dirty_sections.add("startup")
            if updates_dirty: self.dirty_sections.add("updates")
            if changed_profiles or set(original.browser_profiles)-set(config.browser_profiles): self.dirty_sections.add("browser_profiles")
            if general_dirty:
                config.settings.launch_delay_seconds=delay; config.settings.duplicate_launch_cooldown_seconds=cooldown
                config.settings.theme=self.theme_var.get(); config.settings.visual_style=self.visual_style_var.get()
                config.settings.remember_window_position=self.remember_var.get()
            if updates_dirty:
                (config.updates.channel,config.updates.policy,
                 config.updates.automatically_check,config.updates.automatically_download)=update_values
            previous_startup=config.settings.launch_with_windows
            if startup_dirty:
                try: set_startup_enabled(self.startup_var.get(),self.master_app.executable_path)
                except Exception as exc: raise RuntimeError(f"Windows startup could not be updated: {exc}") from exc
                config.settings.launch_with_windows=self.startup_var.get()
            try:
                if self.dirty_sections: save_settings(self.master_app.config_path,config)
            except Exception:
                if startup_dirty:
                    try: set_startup_enabled(previous_startup,self.master_app.executable_path)
                    except Exception: logging.error("Could not roll back the startup entry after a settings save failure")
                config.settings.launch_with_windows=previous_startup
                raise
            if hasattr(self.master_app, "apply_visual_style"):
                self.master_app.apply_visual_style(config.settings.visual_style)
            self.master_app.refresh_ui()
            self.master_app.launcher.browser_profiles = self.master_app.config.browser_profiles
            warning=stale_profile_warning(config)
            self.master_app.set_status("Settings saved." if self.dirty_sections else "No settings changes to save.")
            if warning: messagebox.showwarning(APP_NAME,"Settings saved.\n\nWarning:\n"+warning,parent=self)
            self.destroy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save settings: {exc}",parent=self)


class WorkLauncherApp(tk.Tk):
    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.minsize(DEFAULT_MIN_WINDOW_WIDTH, DEFAULT_MIN_WINDOW_HEIGHT)
        self.config_path = config_path or get_config_path()
        config_existed = self.config_path.exists()
        self.executable_path = Path(sys.executable)
        self.log_path = configure_logging()
        self.config, warnings = load_config(self.config_path)
        self.palette = apply_visual_style(self, self.config.settings.visual_style)
        cleanup_stale_updates()
        logging.info("Starting %s version %s", APP_NAME, __version__)
        self.launcher = WebsiteLauncher(browser_profiles=self.config.browser_profiles)
        self.update_manager = UpdateManager(self.config, self.config_path); self.update_events = queue.Queue()
        self.is_launching = False
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.center_first_launch()
        self.refresh_ui()
        for warning in warnings:
            self.set_status(warning)
            logging.warning(warning)
        if should_run_setup(self.config, config_existed): self.after(150, self.open_setup_wizard)
        elif self.update_manager.due(): self.after(500, self.check_for_updates)
        update_status=consume_update_status()
        if update_status: self.after(300,lambda status=update_status:self.show_update_result(status))
        self.after(0, self.refresh_update_summary)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12, style="Card.TFrame")
        root.pack(fill="both", expand=True)
        ttk.Label(root, text=APP_NAME, style="Header.TLabel").pack(anchor="w")
        self.open_all_button = ttk.Button(root, text="Open All Work Apps", command=self.open_all_work_apps, style="Primary.TButton")
        self.open_all_button.pack(fill="x", pady=(10, 8))
        body = ttk.Frame(root)
        body.pack(fill="both", expand=True)
        self.website_vars: list[tk.BooleanVar] = []
        list_frame = ttk.Frame(body)
        list_frame.pack(side="left", fill="both", expand=True)
        ttk.Label(list_frame, text="Websites").pack(anchor="w")
        self.website_container = ttk.Frame(list_frame)
        self.website_container.pack(fill="both", expand=True, pady=(6, 0))
        ctrl_frame = ttk.Frame(body)
        ctrl_frame.pack(side="right", fill="y", padx=(10, 0))
        self.open_selected_button = ttk.Button(ctrl_frame, text="Open Selected", command=self.open_selected, style="Primary.TButton")
        self.open_selected_button.pack(fill="x", pady=2)
        ttk.Label(ctrl_frame, text="Launch Group").pack(anchor="w", pady=(8, 1))
        self.launch_group_var = tk.StringVar(value="All Websites")
        self.launch_group_combo = ttk.Combobox(ctrl_frame, textvariable=self.launch_group_var, state="readonly", width=20)
        self.launch_group_combo.pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Launch Group", command=self.open_launch_group).pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Select All", command=self.select_all).pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Clear Selection", command=self.clear_selection).pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Settings", command=self.open_settings, style="Primary.TButton").pack(fill="x", pady=(10, 2))
        ttk.Button(ctrl_frame, text="Close", command=self.destroy).pack(fill="x", pady=2)
        update_box = ttk.LabelFrame(ctrl_frame, text="Update Status", padding=8)
        update_box.pack(fill="x", pady=(12, 0))
        self.update_summary_var = tk.StringVar(value="Latest version: Unknown")
        self.update_details_var = tk.StringVar(value="Last checked: Never")
        ttk.Label(update_box, textvariable=self.update_summary_var, wraplength=210).pack(anchor="w")
        ttk.Label(update_box, textvariable=self.update_details_var, wraplength=210, style="Muted.TLabel").pack(anchor="w", pady=(4, 6))
        ttk.Button(update_box, text="Check Now", command=lambda: self.check_for_updates(force=True), style="Primary.TButton").pack(fill="x", pady=1)
        ttk.Button(update_box, text="Release Notes", command=self.open_release_notes).pack(fill="x", pady=1)
        ttk.Button(update_box, text="Diagnostics", command=self.open_update_diagnostics).pack(fill="x", pady=1)
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(root, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", pady=(10, 0))
        self.bind_all("<Control-Shift-o>", lambda event: self.open_all_work_apps())
        self.bind_all("<Control-Return>", lambda event: self.open_selected())
        self.bind_all("<Control-comma>", lambda event: self.open_settings())
        self.bind_all("<Escape>", lambda event: self._escape_handler())
        self.bind_all("<Control-a>", lambda event: self.select_all())

    def _escape_handler(self) -> None:
        if self.winfo_exists():
            self.iconify()

    def refresh_ui(self) -> None:
        for child in self.website_container.winfo_children():
            child.destroy()
        self.website_vars.clear()
        for site in self.config.websites:
            row = ttk.Frame(self.website_container)
            row.pack(fill="x", pady=2)
            var = tk.BooleanVar(value=site.selected)
            self.website_vars.append(var)
            ttk.Checkbutton(row, text=site.name, variable=var).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text=f"Open {site.name}", command=lambda s=site: self.open_single(s)).pack(side="right")
        groups = sorted({site.launch_group for site in self.config.websites if site.launch_group}, key=str.casefold)
        self.launch_group_combo.configure(values=["All Websites", *groups])
        if self.launch_group_var.get() not in ["All Websites", *groups]: self.launch_group_var.set("All Websites")
        self.set_status("Ready.")

    def center_first_launch(self) -> None:
        self.update_idletasks()
        width = self.config.settings.window_width
        height = self.config.settings.window_height
        if self.config.settings.window_x is not None and self.config.settings.window_y is not None and self.config.settings.remember_window_position:
            self.geometry(f"{width}x{height}+{self.config.settings.window_x}+{self.config.settings.window_y}")
            return
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max((screen_w - width) // 2, 0)
        y = max((screen_h - height) // 2, 0)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def set_status(self, message: str) -> None:
        self.status.set(message)
        logging.info(message)

    def apply_visual_style(self, preset: str | None = None) -> None:
        self.palette = apply_visual_style(self, preset or self.config.settings.visual_style)

    def _selected_websites(self) -> list[WebsiteConfig]:
        selected = []
        for site, var in zip(self.config.websites, self.website_vars):
            site.selected = var.get()
            if site.selected and site.enabled:
                selected.append(site)
        save_config(self.config_path, self.config)
        return selected

    def select_all(self) -> None:
        for var in self.website_vars:
            var.set(True)
        self._selected_websites()
        self.set_status("All websites selected.")

    def clear_selection(self) -> None:
        for var in self.website_vars:
            var.set(False)
        self._selected_websites()
        self.set_status("Selection cleared.")

    def open_settings(self) -> None:
        SettingsWindow(self)

    def open_setup_wizard(self) -> None:
        SetupWizard(self, self.config, self.config_path, on_complete=self.refresh_ui)

    def show_update_result(self,status: dict) -> None:
        code=status.get("status","")
        messages={"update_installed":"Update installed successfully.","install_failed_previous_version_restored":"Update installation failed. The previous version was restored.",
                  "restart_failed_previous_version_restored":"The updated version could not restart. The previous version was restored and restarted.","update_failed":"The update could not be installed. Work Launcher remains available."}
        message=messages.get(code,"The previous update attempt did not complete."); self.set_status(message); self.refresh_update_summary()
        (messagebox.showinfo if code=="update_installed" else messagebox.showwarning)(APP_NAME,message,parent=self)

    def check_for_updates(self, force: bool = False) -> None:
        self.set_status("Checking for updates...")
        threading.Thread(target=self._update_worker,args=(force,),daemon=True).start(); self.after(100,self._poll_update)
    def _update_worker(self, force):
        try: self.update_events.put(("ok",self.update_manager.check(force=force)))
        except Exception as exc: self.update_events.put(("error",exc))
    def _poll_update(self):
        try: kind,value=self.update_events.get_nowait()
        except queue.Empty:
            if self.winfo_exists(): self.after(100,self._poll_update)
            return
        for child in self.winfo_children():
            if isinstance(child,SettingsWindow): child.refresh_update_status()
        if kind=="error":
            self.set_status(str(value))
            self.refresh_update_summary()
            return
        if value is None:
            self.set_status(f"Work Launcher {__version__} is up to date.")
            self.refresh_update_summary()
            return
        self.set_status(f"Version {value.version} is available.")
        self.refresh_update_summary()
        if value.mandatory or value.version != self.config.updates.skipped_version:
            dialog=UpdateDialog(self,value,self.config,self.config_path)
            if self.config.updates.policy=="automatic": dialog.after(200,lambda:dialog.download(True))
            elif self.config.updates.automatically_download: dialog.after(200,lambda:dialog.download(False))

    def refresh_update_summary(self) -> None:
        if not hasattr(self, "update_summary_var"):
            return
        snapshot = self.update_manager.snapshot()
        self.update_summary_var.set(f"Latest version: {snapshot['latest_version']} ({snapshot['channel']}, {snapshot['policy']})")
        self.update_details_var.set(f"Last checked: {snapshot['last_checked']} | Next check: {snapshot['next_check']} | Error: {snapshot['last_error']}")

    def open_release_notes(self) -> None:
        release = self.update_manager.latest
        if release:
            UpdateDialog(self, release, self.config, self.config_path)
            return
        messagebox.showinfo(APP_NAME, "Check for updates first. No newer release is currently loaded.", parent=self)

    def open_update_diagnostics(self) -> None:
        UpdateDiagnosticsDialog(self, self.update_manager.snapshot(), self.config, self.config_path)

    def open_single(self, website: WebsiteConfig) -> None:
        result = self.launcher.open_website(website)
        self.set_status(result.message)

    def _set_launch_controls(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.open_all_button.configure(state=state)
        self.open_selected_button.configure(state=state)

    def open_selected(self) -> None:
        if self.is_launching:
            self.set_status("Launch already in progress.")
            return
        websites = self._selected_websites()
        if not websites:
            self.set_status("No websites are selected.")
            return
        self._launch_sequence(websites)

    def open_launch_group(self) -> None:
        if self.is_launching:
            self.set_status("Launch already in progress."); return
        group = self.launch_group_var.get()
        websites = websites_for_group(self.config, group)
        if not websites: self.set_status(f"No enabled websites in launch group {group}."); return
        self._launch_sequence(websites)

    def open_all_work_apps(self) -> None:
        if self.is_launching:
            self.set_status("Open All Work Apps is temporarily disabled while launching.")
            return
        if not self.launcher.can_launch_all(self.config.settings.duplicate_launch_cooldown_seconds):
            self.set_status("Duplicate launch ignored during cooldown period.")
            return
        websites = [site for site in self.config.websites if site.enabled]
        self._launch_sequence(websites, all_launch=True)

    def _launch_sequence(self, websites: list[WebsiteConfig], all_launch: bool = False) -> None:
        self.is_launching = True
        self._set_launch_controls(False)
        if all_launch:
            self.launcher._last_launch_all = time.monotonic()
        self.set_status(f"Launching {len(websites)} websites...")
        failures=[]
        try:
            for index, website in enumerate(websites):
                if index > 0 and self.config.settings.launch_delay_seconds > 0:
                    self.after(int(self.config.settings.launch_delay_seconds * 1000))
                    self.update()
                result = self.launcher.open_website(website)
                self.set_status(result.message)
                if not result.success: failures.append(website.name)
            self.set_status("Launch complete." if not failures else "Launch complete. Skipped: " + ", ".join(failures))
        finally:
            self.is_launching = False
            self._set_launch_controls(True)

    def on_close(self) -> None:
        self.config.settings.window_width = self.winfo_width()
        self.config.settings.window_height = self.winfo_height()
        if self.config.settings.remember_window_position:
            self.config.settings.window_x = self.winfo_x()
            self.config.settings.window_y = self.winfo_y()
        save_config(self.config_path, self.config)
        self.destroy()


def main() -> int:
    app = WorkLauncherApp()
    app.mainloop()
    return 0
