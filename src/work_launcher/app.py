from __future__ import annotations

import logging
import json
import sys
import time
import tkinter as tk
import copy
import queue
import threading
import os
import subprocess
from datetime import datetime
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from urllib.parse import urlparse

from .config import AppConfig, WebsiteConfig, get_config_path, load_config, save_config, validate_config_data
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
from .command_palette import CommandPalette
from .enterprise_policy import apply_policy, load_policy
from .health_checks import check_url
from .scheduler import ScheduleState, due_schedules
from .session_report import create_session, save_session
from .tray import TrayController
from .workspace_dialogs import WorkspaceManager
from .workspace_launcher import WorkspaceLauncher, network_available
from .single_instance import AlreadyRunningError, SingleInstance
from .constants import app_data_dir
from .bookmark_import import parse_bookmarks
from .backup_center import create_backup, automatic_backup, inspect_backup
from .global_hotkey import GlobalHotkey
from .notifications import notify
from .utility_dialogs import LaunchResultsDialog, SelectionDialog, SessionHistoryDialog
from .productivity_tools import (export_transfer, find_repair_issues, import_transfer,
                                 merge_organization_package, stage_rollback, verify_organization_package)
from .update_download import updates_dir


class WebsiteDialog(tk.Toplevel):
    def __init__(self, master, title: str, profiles, website: WebsiteConfig | None = None):
        super().__init__(master); self.title(title); self.transient(master); self.grab_set(); self.resizable(False, False)
        self.result = None; self.profiles = profiles; website = website or WebsiteConfig("", "", True, True)
        self.name_var = tk.StringVar(value=website.name); self.url_var = tk.StringVar(value=website.url)
        self.enabled_var = tk.BooleanVar(value=website.enabled); self.selected_var = tk.BooleanVar(value=website.selected)
        self.group_var = tk.StringVar(value=website.launch_group)
        self.favorite_var = tk.BooleanVar(value=website.favorite)
        self.tags_var = tk.StringVar(value=", ".join(website.tags))
        self.icon_var = tk.StringVar(value=website.icon_path)
        self.profile_names = {profile.name: key for key, profile in profiles.items()}
        current = profiles.get(website.browser_profile); self.profile_var = tk.StringVar(value=current.name if current else "")
        frame = ttk.Frame(self, padding=14, style="Card.TFrame"); frame.pack(fill="both", expand=True)
        fields = (("Display Name", ttk.Entry(frame, textvariable=self.name_var, width=52)),
                  ("URL", ttk.Entry(frame, textvariable=self.url_var, width=52)),
                  ("Browser Profile", ttk.Combobox(frame, textvariable=self.profile_var, values=list(self.profile_names), state="readonly", width=49)),
                  ("Launch Group (Optional)", ttk.Combobox(frame, textvariable=self.group_var,
                    values=["", "Daily Work", "Morning", "Meetings", "Admin", "Research", "Custom"], width=49)),
                  ("Tags (comma separated)", ttk.Entry(frame, textvariable=self.tags_var, width=52)))
        fields += (("Local Icon (Optional)", ttk.Entry(frame, textvariable=self.icon_var, width=52)),)
        for row, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=3); widget.grid(row=row, column=1, sticky="ew", pady=3)
        icon_actions = ttk.Frame(frame); icon_actions.grid(row=5, column=2, padx=4)
        ttk.Button(icon_actions, text="Browse", command=self.choose_icon).pack()
        ttk.Button(icon_actions, text="Library", command=self.choose_builtin_icon).pack(pady=2)
        ttk.Checkbutton(frame, text="Enabled", variable=self.enabled_var).grid(row=6, column=1, sticky="w")
        ttk.Checkbutton(frame, text="Selected by Default", variable=self.selected_var).grid(row=7, column=1, sticky="w")
        ttk.Checkbutton(frame, text="Favorite", variable=self.favorite_var).grid(row=8, column=1, sticky="w")
        self.error_var = tk.StringVar(); ttk.Label(frame, textvariable=self.error_var, foreground="#b00020", wraplength=420, style="Card.TLabel").grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
        buttons = ttk.Frame(frame); buttons.grid(row=10, column=0, columnspan=2, sticky="e")
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
        tags = list(dict.fromkeys(value.strip() for value in self.tags_var.get().split(",") if value.strip()))
        self.result = WebsiteConfig(name=self.name_var.get().strip(), url=self.url_var.get().strip(),
                                    enabled=self.enabled_var.get(), selected=self.selected_var.get(),
                                    browser_profile=profile, launch_group=self.group_var.get().strip(),
                                    favorite=self.favorite_var.get(), tags=tags, icon_path=self.icon_var.get().strip())
        self.destroy()

    def choose_icon(self):
        value = filedialog.askopenfilename(parent=self, title="Choose Website Icon",
                                           filetypes=[("Images", "*.png;*.gif;*.jpg;*.jpeg;*.ico")])
        if value: self.icon_var.set(value)

    def choose_builtin_icon(self):
        value = simpledialog.askstring("Icon Library", "Choose: work, web, admin, meeting, document", parent=self)
        if value and value.casefold() in {"work", "web", "admin", "meeting", "document"}: self.icon_var.set("builtin:" + value.casefold())


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
        self.tray_var = tk.BooleanVar(value=self.master_app.config.settings.minimize_to_tray)
        self.startup_var = tk.BooleanVar(value=self.master_app.config.settings.launch_with_windows)
        self.hotkey_var = tk.BooleanVar(value=self.master_app.config.settings.global_hotkey)
        self.notifications_var = tk.BooleanVar(value=self.master_app.config.settings.notifications)
        ttk.Checkbutton(form, text="Remember window position", variable=self.remember_var).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Minimize to notification area when closed", variable=self.tray_var).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Launch Work Launcher when Windows starts", variable=self.startup_var).grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Global shortcut: Ctrl+Alt+Space", variable=self.hotkey_var).grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Enable launch notifications", variable=self.notifications_var).grid(row=7, column=0, columnspan=2, sticky="w")
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
            tray_var = getattr(self, "tray_var", None)
            tray_enabled = tray_var.get() if tray_var is not None else self.master_app.config.settings.minimize_to_tray
            hotkey_var = getattr(self, "hotkey_var", None)
            hotkey_enabled = hotkey_var.get() if hotkey_var is not None else self.master_app.config.settings.global_hotkey
            notifications_var = getattr(self, "notifications_var", None)
            notifications_enabled = (notifications_var.get() if notifications_var is not None
                                     else self.master_app.config.settings.notifications)
            delay=float(self.delay_var.get()); cooldown=float(self.cooldown_var.get())
            if delay < 0 or cooldown < 0: raise ValueError("Launch delay and duplicate cooldown cannot be negative.")
            original=self.original_config; config=self.master_app.config
            general_dirty=(delay != original.settings.launch_delay_seconds or cooldown != original.settings.duplicate_launch_cooldown_seconds
                or self.theme_var.get() != original.settings.theme or self.visual_style_var.get() != original.settings.visual_style
                or self.remember_var.get() != original.settings.remember_window_position
                or tray_enabled != original.settings.minimize_to_tray
                or hotkey_enabled != original.settings.global_hotkey
                or notifications_enabled != original.settings.notifications)
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
                config.settings.minimize_to_tray=tray_enabled
                config.settings.global_hotkey=hotkey_enabled
                config.settings.notifications=notifications_enabled
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
        try:
            apply_policy(self.config, load_policy())
        except Exception as exc:
            warnings.append(f"Enterprise policy could not be applied: {exc}")
        self.palette = apply_visual_style(self, self.config.settings.visual_style)
        cleanup_stale_updates()
        logging.info("Starting %s version %s", APP_NAME, __version__)
        self.launcher = WebsiteLauncher(browser_profiles=self.config.browser_profiles)
        self.workspace_launcher = WorkspaceLauncher(self.config, self.launcher)
        self.update_manager = UpdateManager(self.config, self.config_path); self.update_events = queue.Queue()
        self.schedule_state: dict[str, ScheduleState] = {}
        self.tray: TrayController | None = None
        self.hotkey: GlobalHotkey | None = None
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
        self.after(1000, self._schedule_tick)
        if self.config.settings.minimize_to_tray:
            self.after(0, self._ensure_tray)
        automatic_backup(self.config_path, app_data_dir() / "Backups")
        if self.config.settings.global_hotkey:
            self.hotkey = GlobalHotkey(lambda: self.after(0, self._show_from_tray))
            if not self.hotkey.start(): warnings.append("The Ctrl+Alt+Space global shortcut is already in use.")

    def _build(self) -> None:
        self.shell = ttk.Frame(self)
        self.shell.pack(fill="both", expand=True)
        self.sidebar = ttk.Frame(self.shell, padding=(14, 22), style="Sidebar.TFrame")
        ttk.Label(self.sidebar, text="WORK", style="SidebarBrand.TLabel").pack(anchor="w", padx=8)
        ttk.Label(self.sidebar, text="LAUNCHER", style="Sidebar.TLabel").pack(anchor="w", padx=8, pady=(0, 28))
        ttk.Button(self.sidebar, text="Dashboard", command=lambda: self.website_canvas.yview_moveto(0), style="NavPrimary.TButton").pack(fill="x", pady=2)
        ttk.Button(self.sidebar, text="Workspaces", command=self.open_workspace_manager, style="Nav.TButton").pack(fill="x", pady=2)
        ttk.Button(self.sidebar, text="Launch history", command=self.open_session_history, style="Nav.TButton").pack(fill="x", pady=2)
        ttk.Button(self.sidebar, text="Repair center", command=self.open_repair_center, style="Nav.TButton").pack(fill="x", pady=2)
        ttk.Button(self.sidebar, text="Settings", command=self.open_settings, style="Nav.TButton").pack(fill="x", pady=2)
        ttk.Label(self.sidebar, text="Ctrl+K  Command palette", style="Sidebar.TLabel", wraplength=145).pack(side="bottom", anchor="w", padx=8, pady=8)
        self.dashboard = ttk.Frame(self.shell, padding=24, style="Card.TFrame")
        self.shell.bind("<Configure>", self._resize_dashboard)

        header = ttk.Frame(self.dashboard, style="Card.TFrame")
        header.pack(fill="x")
        title_box = ttk.Frame(header, style="Card.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="WORKSPACE CONTROL", style="Eyebrow.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Good to see you", style="DashboardHeader.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(
            title_box,
            text="Everything you need to start a focused work session.",
            style="DashboardSubtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        header_actions = ttk.Frame(header, style="Card.TFrame")
        header_actions.pack(side="right")
        self.update_summary_var = tk.StringVar(value="Updates: not checked")
        self.update_details_var = tk.StringVar(value="Last checked: Never")
        ttk.Button(
            header_actions,
            textvariable=self.update_summary_var,
            command=self.open_update_diagnostics,
            style="Update.TButton",
        ).pack(side="left", padx=(0, 4))
        tools = ttk.Menubutton(header_actions, text="Tools", style="Secondary.TButton")
        tools_menu = tk.Menu(tools, tearoff=False)
        tools_menu.add_command(label="Manage Workspaces", command=self.open_workspace_manager)
        tools_menu.add_command(label="Launch History", command=self.open_session_history)
        tools_menu.add_command(label="Import Browser Bookmarks", command=self.import_bookmarks)
        tools_menu.add_command(label="Backup Configuration", command=self.backup_configuration)
        tools_menu.add_command(label="Restore Configuration", command=self.restore_configuration)
        tools_menu.add_command(label="Configuration Transfer", command=self.configuration_transfer)
        tools_menu.add_command(label="Repair Center", command=self.open_repair_center)
        tools_menu.add_command(label="Import Signed Organization Package", command=self.import_organization_package)
        tools_menu.add_command(label="Restore Previous Portable Version", command=self.rollback_previous_version)
        tools_menu.add_command(label="Check Website Health", command=self.check_website_health)
        tools_menu.add_command(label="Check for Updates", command=lambda: self.check_for_updates(force=True))
        tools_menu.add_command(label="Release Notes", command=self.open_release_notes)
        tools_menu.add_command(label="Update Diagnostics", command=self.open_update_diagnostics)
        tools_menu.add_separator()
        tools_menu.add_command(label="Settings", command=self.open_settings)
        tools_menu.add_command(label="Close", command=self.on_close)
        tools.configure(menu=tools_menu)
        tools.pack(side="left")

        stats = ttk.Frame(self.dashboard, style="Card.TFrame")
        stats.pack(fill="x", pady=(18, 4))
        self.website_count_var = tk.StringVar(value="0")
        self.preset_count_var = tk.StringVar(value="0")
        self.schedule_count_var = tk.StringVar(value="0")
        for label, variable in (("ACTIVE WEBSITES", self.website_count_var), ("WORKSPACE PRESETS", self.preset_count_var),
                                ("ENABLED SCHEDULES", self.schedule_count_var)):
            card = ttk.Frame(stats, padding=(16, 10), style="Surface.TFrame"); card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ttk.Label(card, textvariable=variable, style="StatValue.TLabel").pack(anchor="w")
            ttk.Label(card, text=label, style="StatLabel.TLabel").pack(anchor="w")

        toolbar = ttk.Frame(self.dashboard, padding=(0, 14, 0, 8), style="Card.TFrame")
        toolbar.pack(fill="x")
        self.open_selected_button = ttk.Button(
            toolbar, text="Open Selected", command=self.open_selected, style="Primary.TButton"
        )
        self.open_selected_button.pack(side="left")
        self.open_all_button = ttk.Button(
            toolbar, text="Open All", command=self.open_all_work_apps, style="Secondary.TButton"
        )
        self.open_all_button.pack(side="left", padx=(8, 18))

        self.search_var = tk.StringVar()
        ttk.Label(toolbar, text="Find", style="Card.TLabel").pack(side="left", padx=(0, 5))
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=28)
        search.pack(side="left", fill="x", expand=True)
        self.search_var.trace_add("write", lambda *_args: self.refresh_ui())

        controls = ttk.Frame(self.dashboard, padding=(0, 0, 0, 12), style="Card.TFrame")
        controls.pack(fill="x")

        self.launch_group_var = tk.StringVar(value="All Websites")
        ttk.Label(controls, text="Launch group", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.launch_group_combo = ttk.Combobox(
            controls, textvariable=self.launch_group_var, state="readonly", width=13
        )
        self.launch_group_combo.pack(side="left")
        self.launch_group_button = ttk.Button(
            controls, text="Launch", command=self.open_launch_group, style="Compact.TButton"
        )
        self.launch_group_button.pack(side="left", padx=(5, 12))

        self.preset_var = tk.StringVar()
        ttk.Label(controls, text="Workspace preset", style="Card.TLabel").pack(side="left", padx=(0, 5))
        self.preset_combo = ttk.Combobox(controls, textvariable=self.preset_var, state="readonly", width=13)
        self.preset_combo.pack(side="left")
        self.launch_preset_button = ttk.Button(
            controls, text="Launch", command=self.launch_selected_preset, style="Compact.TButton"
        )
        self.launch_preset_button.pack(side="left", padx=(5, 0))

        self.filter_var = tk.StringVar(value="All")
        ttk.Label(controls, text="View", style="Card.TLabel").pack(side="left", padx=(12, 5))
        self.filter_combo = ttk.Combobox(controls, textvariable=self.filter_var, state="readonly", width=10,
                                         values=["All", "Favorites", "Enabled", "Disabled"])
        self.filter_combo.pack(side="left"); self.filter_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_ui())

        self.website_vars: list[tk.BooleanVar] = []
        self.displayed_websites: list[WebsiteConfig] = []
        self.site_icons = []
        list_card = ttk.Frame(self.dashboard, padding=14, style="Row.TFrame")
        list_card.pack(fill="both", expand=True)
        list_header = ttk.Frame(list_card, style="Card.TFrame")
        list_header.pack(fill="x", pady=(0, 10))
        ttk.Label(list_header, text="Your websites", style="CardSection.TLabel").pack(side="left")
        self.selection_summary_var = tk.StringVar(value="0 selected")
        ttk.Label(list_header, textvariable=self.selection_summary_var, style="DashboardSubtitle.TLabel").pack(side="left", padx=10)
        ttk.Button(list_header, text="Add website", command=self.add_first_website, style="Compact.TButton").pack(side="right")
        ttk.Button(list_header, text="Manage", command=self.open_settings, style="Compact.TButton").pack(side="right", padx=5)
        ttk.Button(list_header, text="Clear", command=self.clear_selection, style="Compact.TButton").pack(side="right")
        ttk.Button(list_header, text="Select all", command=self.select_all, style="Compact.TButton").pack(side="right", padx=5)

        scroll_host = ttk.Frame(list_card, style="Card.TFrame")
        scroll_host.pack(fill="both", expand=True)
        self.website_canvas = tk.Canvas(scroll_host, highlightthickness=0, bd=0, bg=self.palette["card"])
        website_scrollbar = ttk.Scrollbar(scroll_host, orient="vertical", command=self.website_canvas.yview)
        self.website_canvas.configure(yscrollcommand=website_scrollbar.set)
        website_scrollbar.pack(side="right", fill="y")
        self.website_canvas.pack(side="left", fill="both", expand=True)
        self.website_container = ttk.Frame(self.website_canvas, style="Card.TFrame")
        self.website_window = self.website_canvas.create_window((0, 0), window=self.website_container, anchor="nw")
        self.website_container.bind(
            "<Configure>",
            lambda _event: self.website_canvas.configure(scrollregion=self.website_canvas.bbox("all")),
        )
        self.website_canvas.bind(
            "<Configure>",
            lambda event: self.website_canvas.itemconfigure(self.website_window, width=event.width),
        )
        self.website_canvas.bind("<Enter>", lambda _event: self.bind_all("<MouseWheel>", self._scroll_websites))
        self.website_canvas.bind("<Leave>", lambda _event: self.unbind_all("<MouseWheel>"))

        footer = ttk.Frame(self.dashboard, padding=(0, 12, 0, 0), style="Card.TFrame")
        footer.pack(fill="x")
        self.status = tk.StringVar(value="Ready.")
        ttk.Label(footer, textvariable=self.status, style="Footer.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Label(footer, text=f"Version {__version__}", style="Footer.TLabel").pack(side="right")
        ttk.Label(footer, text="Ctrl+K commands", style="Footer.TLabel").pack(side="right", padx=14)
        self.bind_all("<Control-Shift-o>", lambda event: self.open_all_work_apps())
        self.bind_all("<Control-Return>", lambda event: self.open_selected())
        self.bind_all("<Control-comma>", lambda event: self.open_settings())
        self.bind_all("<Escape>", lambda event: self._escape_handler())
        self.bind_all("<Control-a>", lambda event: self.select_all())
        self.bind_all("<Control-k>", lambda event: self.open_command_palette())

    def _resize_dashboard(self, event) -> None:
        sidebar_width = 184 if event.width >= 980 else 156
        margin = 16 if event.width >= 980 else 8
        self.sidebar.place(x=0, y=0, width=sidebar_width, height=event.height)
        available = max(event.width - sidebar_width - (margin * 2), 620)
        width = min(available, 1180)
        x = sidebar_width + margin + max((available - width) // 2, 0)
        self.dashboard.place(x=x, y=margin, width=width, height=max(event.height - margin * 2, 560))

    def _scroll_websites(self, event) -> None:
        self.website_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _escape_handler(self) -> None:
        if self.winfo_exists():
            self.iconify()

    def refresh_ui(self) -> None:
        for child in self.website_container.winfo_children():
            child.destroy()
        self.website_vars.clear()
        self.site_icons.clear()
        if not self.config.websites:
            empty = ttk.Frame(self.website_container, padding=36, style="Card.TFrame")
            empty.pack(fill="both", expand=True)
            ttk.Label(empty, text="No websites configured", style="DashboardHeader.TLabel").pack(pady=(28, 8))
            ttk.Label(
                empty,
                text="Add your first website or import an existing Work Launcher configuration.",
                style="DashboardSubtitle.TLabel",
                wraplength=460,
            ).pack(pady=(0, 16))
            actions = ttk.Frame(empty, style="Card.TFrame")
            actions.pack()
            ttk.Button(actions, text="Add Website", command=self.add_first_website,
                       style="Primary.TButton").pack(side="left", padx=4)
            ttk.Button(actions, text="Import Configuration", command=self.import_configuration,
                       style="Secondary.TButton").pack(side="left", padx=4)
        filter_value = self.filter_var.get() if hasattr(self, "filter_var") else "All"
        query = self.search_var.get().strip().casefold() if hasattr(self, "search_var") else ""
        tags = sorted({tag for site in self.config.websites for tag in site.tags}, key=str.casefold)
        if hasattr(self, "filter_combo"): self.filter_combo.configure(values=["All", "Favorites", "Enabled", "Disabled", *[f"Tag: {tag}" for tag in tags]])
        self.displayed_websites = [site for site in self.config.websites if
            (filter_value == "All" or filter_value == "Favorites" and site.favorite or
             filter_value == "Enabled" and site.enabled or filter_value == "Disabled" and not site.enabled or
             filter_value.startswith("Tag: ") and filter_value[5:] in site.tags)
            and (not query or query in " ".join((site.name, site.url, site.launch_group, *site.tags)).casefold())]
        if self.config.websites and not self.displayed_websites:
            empty = ttk.Frame(self.website_container, padding=32, style="Card.TFrame"); empty.pack(fill="both", expand=True)
            ttk.Label(empty, text="No matching websites", style="CardSection.TLabel").pack(pady=(20, 6))
            ttk.Label(empty, text="Try a different search or view filter.", style="DashboardSubtitle.TLabel").pack()
        for site in self.displayed_websites:
            row = ttk.Frame(self.website_container, padding=(12, 9), style="Row.TFrame")
            row.pack(fill="x", pady=(0, 7))
            var = tk.BooleanVar(value=site.selected)
            self.website_vars.append(var)
            ttk.Checkbutton(
                row, variable=var, command=self._selection_changed, style="Card.TCheckbutton"
            ).pack(side="left", padx=(0, 8))
            if site.icon_path.startswith("builtin:"):
                try:
                    from PIL import Image, ImageDraw, ImageTk
                    colors = {"work": "#246b9e", "web": "#16835d", "admin": "#a55b17", "meeting": "#7048a8", "document": "#596579"}
                    image = Image.new("RGBA", (24, 24), colors.get(site.icon_path[8:], "#246b9e")); draw = ImageDraw.Draw(image)
                    draw.ellipse((7, 7, 17, 17), outline="white", width=2); icon = ImageTk.PhotoImage(image)
                    self.site_icons.append(icon); ttk.Label(row, image=icon, style="Card.TLabel").pack(side="left", padx=(0, 8))
                except Exception: pass
            elif site.icon_path and Path(site.icon_path).is_file():
                try:
                    from PIL import Image, ImageTk
                    icon = ImageTk.PhotoImage(Image.open(site.icon_path).convert("RGBA").resize((24, 24)))
                    self.site_icons.append(icon); ttk.Label(row, image=icon, style="Card.TLabel").pack(side="left", padx=(0, 8))
                except Exception: pass
            details = ttk.Frame(row, style="Card.TFrame")
            details.pack(side="left", fill="x", expand=True)
            ttk.Label(details, text=("Favorite · " if site.favorite else "") + site.name, style="RowTitle.TLabel").pack(anchor="w")
            profile = self.config.browser_profiles.get(site.browser_profile)
            metadata = [profile.name if profile else site.browser_profile]
            if site.launch_group:
                metadata.append(site.launch_group)
            if site.tags:
                metadata.append(", ".join(site.tags))
            if not site.enabled:
                metadata.append("Disabled")
            ttk.Label(details, text="  ·  ".join(metadata), style="RowMeta.TLabel").pack(anchor="w", pady=(2, 0))
            menu_button = ttk.Menubutton(row, text="More", style="Compact.TButton")
            item_menu = tk.Menu(menu_button, tearoff=False)
            item_menu.add_command(label="Open", command=lambda s=site: self.open_single(s))
            item_menu.add_command(
                label="Disable" if site.enabled else "Enable",
                command=lambda s=site: self.toggle_website(s),
            )
            item_menu.add_command(label="Edit in Settings", command=self.open_settings)
            item_menu.add_command(label="Remove Favorite" if site.favorite else "Add to Favorites",
                                  command=lambda s=site: self.toggle_favorite(s))
            item_menu.add_separator()
            item_menu.add_command(label="Delete", command=lambda s=site: self.delete_website(s))
            menu_button.configure(menu=item_menu)
            menu_button.pack(side="right", padx=(6, 0))
            ttk.Button(
                row, text="Open", command=lambda s=site: self.open_single(s), style="Compact.TButton"
            ).pack(side="right")
        groups = sorted({site.launch_group for site in self.config.websites if site.launch_group}, key=str.casefold)
        self.launch_group_combo.configure(values=["All Websites", *groups])
        if self.launch_group_var.get() not in ["All Websites", *groups]: self.launch_group_var.set("All Websites")
        has_websites = bool(self.config.websites)
        if hasattr(self, "website_count_var"):
            self.website_count_var.set(str(sum(site.enabled for site in self.config.websites)))
            self.preset_count_var.set(str(len(self.config.presets)))
            self.schedule_count_var.set(str(sum(schedule.enabled for schedule in self.config.schedules)))
        self.open_all_button.configure(state="normal" if has_websites else "disabled")
        self.open_selected_button.configure(state="normal" if has_websites else "disabled")
        self.launch_group_button.configure(state="normal" if has_websites else "disabled")
        self.refresh_preset_controls()
        self._selection_changed()
        self.set_status("Ready." if has_websites else "No websites configured. Add or import websites to begin.")

    def _selection_changed(self) -> None:
        selected = sum(var.get() for site, var in zip(self.displayed_websites, self.website_vars) if site.enabled)
        self.selection_summary_var.set(f"{selected} selected")
        self.open_selected_button.configure(state="normal" if selected else "disabled")

    def toggle_website(self, website: WebsiteConfig) -> None:
        website.enabled = not website.enabled
        save_config(self.config_path, self.config)
        self.refresh_ui()

    def toggle_favorite(self, website: WebsiteConfig) -> None:
        website.favorite = not website.favorite; save_config(self.config_path, self.config); self.refresh_ui()

    def delete_website(self, website: WebsiteConfig) -> None:
        if not messagebox.askyesno(APP_NAME, f'Delete "{website.name}"?', parent=self):
            return
        index = self.config.websites.index(website)
        create_timestamped_backup(self.config_path)
        delete_websites(self.config, [index])
        save_config(self.config_path, self.config)
        self.refresh_ui()

    def add_first_website(self) -> None:
        dialog = WebsiteDialog(self, "Add Website", self.config.browser_profiles)
        self.wait_window(dialog)
        if not dialog.result:
            return
        try:
            warnings = add_website(self.config, dialog.result)
            save_config(self.config_path, self.config)
            self.refresh_ui()
            if warnings:
                messagebox.showwarning(APP_NAME, "\n".join(warnings), parent=self)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not add website: {exc}", parent=self)

    def import_configuration(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Work Launcher Configuration",
            filetypes=[("JSON configuration", "*.json")],
            parent=self,
        )
        if not path:
            return
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            imported_config = validate_config_data(raw) if isinstance(raw, dict) and "browser_profiles" in raw else None
            incoming = imported_config.websites if imported_config else preview_import(Path(path), self.config)
            preview = "\n".join(f"• {site.name}" for site in incoming[:12])
            if len(incoming) > 12:
                preview += f"\n… and {len(incoming) - 12} more"
            if not messagebox.askyesno(
                APP_NAME,
                f"Import preview ({len(incoming)} websites):\n\n{preview or 'No websites'}\n\nContinue?",
                parent=self,
            ):
                return
            replace = bool(self.config.websites) and messagebox.askyesno(
                APP_NAME, "Replace existing websites? Choose No to merge.", parent=self
            )
            if imported_config:
                for profile_id, profile in imported_config.browser_profiles.items():
                    self.config.browser_profiles.setdefault(profile_id, copy.deepcopy(profile))
            count = import_websites(
                self.config,
                incoming,
                replace=replace,
                skip_duplicate_names=True,
                skip_duplicate_urls=True,
            )
            if imported_config and (replace or not self.config.applications):
                self.config.applications = copy.deepcopy(imported_config.applications)
                self.config.presets = copy.deepcopy(imported_config.presets)
                self.config.schedules = copy.deepcopy(imported_config.schedules)
            save_config(self.config_path, self.config)
            self.refresh_ui()
            messagebox.showinfo(APP_NAME, f"Imported {count} websites.", parent=self)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not import configuration: {exc}", parent=self)

    def refresh_preset_controls(self) -> None:
        names = [preset.name for preset in self.config.presets]
        if hasattr(self, "preset_combo"):
            self.preset_combo.configure(values=names)
            if self.preset_var.get() not in names:
                self.preset_var.set(names[0] if names else "")
            self.launch_preset_button.configure(state="normal" if names else "disabled")
        if self.tray:
            self.tray.stop()
            self.tray = None
            self._ensure_tray()

    def open_workspace_manager(self) -> None:
        WorkspaceManager(self)

    def launch_selected_preset(self) -> None:
        name = self.preset_var.get()
        preset = next((item for item in self.config.presets if item.name == name), None)
        if preset is None:
            self.set_status("Select a workspace preset.")
            return
        self.launch_preset(preset)

    def launch_preset(self, preset) -> None:
        started = datetime.now().astimezone()
        cancel_event = threading.Event()
        progress = tk.Toplevel(self); progress.title(f"Launching — {preset.name}"); progress.transient(self)
        progress.geometry("430x150"); progress.protocol("WM_DELETE_WINDOW", cancel_event.set)
        progress_var = tk.StringVar(value=f"Preparing {len(preset.items)} items…")
        ttk.Label(progress, textvariable=progress_var, padding=18, wraplength=390).pack(fill="x")
        ttk.Button(progress, text="Cancel Remaining", command=cancel_event.set).pack(pady=8)
        completed = queue.Queue()
        def confirm_item(name):
            response, ready = {"value": False}, threading.Event()
            def ask(): response["value"] = messagebox.askyesno(APP_NAME, f'Open "{name}"?', parent=progress); ready.set()
            self.after(0, ask); ready.wait(); return response["value"]
        def worker():
            completed.put(self.workspace_launcher.launch_preset(preset, cancel_event, confirm_item))
        threading.Thread(target=worker, name="workspace-launch", daemon=True).start()
        def poll():
            try: results = completed.get_nowait()
            except queue.Empty:
                progress_var.set("Cancellation requested…" if cancel_event.is_set() else "Launching workspace items…")
                progress.after(100, poll); return
            if progress.winfo_exists(): progress.destroy()
            self._finish_preset_launch(preset, started, results)
        poll()

    def _finish_preset_launch(self, preset, started, results) -> None:
        session = create_session(preset.name, started, results)
        report = save_session(session)
        failed = [item.item for item in results if not item.success]
        self.set_status(f"Preset {preset.name} complete. Report: {report.name}" if not failed
                        else f"Preset {preset.name} complete. Failed: {', '.join(failed)}")
        LaunchResultsDialog(self, preset, results, lambda names: self.retry_preset_items(preset, names))
        if self.config.settings.notifications:
            if not (self.tray and self.tray.notify(self.status.get())):
                notify(APP_NAME, self.status.get())

    def retry_preset_items(self, preset, names) -> None:
        retry = copy.deepcopy(preset)
        retry.items = [value for value in preset.items if value.split(":", 1)[1] in names]
        if retry.items: self.launch_preset(retry)

    def open_session_history(self) -> None:
        SessionHistoryDialog(self)

    def backup_configuration(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title="Backup Configuration", defaultextension=".json",
                                            filetypes=[("JSON configuration", "*.json")])
        if path:
            create_backup(self.config, Path(path)); messagebox.showinfo(APP_NAME, "Configuration backup created.", parent=self)

    def restore_configuration(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Restore Configuration",
                                          filetypes=[("JSON configuration", "*.json")])
        if not path: return
        try:
            restored, summary = inspect_backup(Path(path))
            if not messagebox.askyesno(APP_NAME, f"Restore this backup?\n\n{summary}\n\nThe current configuration will be backed up first.", parent=self): return
            automatic_backup(self.config_path, app_data_dir() / "Backups")
            self.config = restored; save_config(self.config_path, self.config)
            self.launcher.browser_profiles = self.config.browser_profiles
            self.workspace_launcher.config = self.config; self.refresh_ui()
        except Exception as exc: messagebox.showerror(APP_NAME, f"Could not restore backup: {exc}", parent=self)

    def import_bookmarks(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Import Browser Bookmark Export",
                                          filetypes=[("Bookmark HTML", "*.html;*.htm")])
        if not path: return
        try:
            bookmarks = parse_bookmarks(Path(path)); existing = {item.url.casefold() for item in self.config.websites}
            incoming = [item for item in bookmarks if item.url.casefold() not in existing]
            if not incoming: messagebox.showinfo(APP_NAME, "No new HTTP/HTTPS bookmarks were found.", parent=self); return
            dialog = SelectionDialog(self, "Select Bookmarks", [f"{item.name} — {item.url}" for item in incoming]); self.wait_window(dialog)
            if dialog.result is None: return
            incoming = [incoming[index] for index in dialog.result]
            if not incoming: return
            profile = next(iter(self.config.browser_profiles))
            self.config.websites.extend(WebsiteConfig(item.name, item.url, browser_profile=profile, tags=["Imported"])
                                        for item in incoming)
            save_config(self.config_path, self.config); self.refresh_ui()
        except Exception as exc: messagebox.showerror(APP_NAME, f"Could not import bookmarks: {exc}", parent=self)

    def configuration_transfer(self) -> None:
        if messagebox.askyesno(APP_NAME, "Export this PC's configuration? Choose No to import a transfer package.", parent=self):
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", filetypes=[("Transfer package", "*.json")])
            if path: export_transfer(self.config, Path(path)); messagebox.showinfo(APP_NAME, "Transfer package created.", parent=self)
            return
        path = filedialog.askopenfilename(parent=self, filetypes=[("Transfer package", "*.json")])
        if not path: return
        try:
            config, issues = import_transfer(Path(path)); summary = f"Import configuration with {len(issues)} machine-specific item(s) needing repair?"
            if messagebox.askyesno(APP_NAME, summary, parent=self):
                automatic_backup(self.config_path, app_data_dir() / "Backups"); self.config = config
                save_config(self.config_path, config); self.launcher.browser_profiles = config.browser_profiles
                self.workspace_launcher.config = config; self.refresh_ui(); self.open_repair_center()
        except Exception as exc: messagebox.showerror(APP_NAME, f"Transfer failed: {exc}", parent=self)

    def open_repair_center(self) -> None:
        issues = find_repair_issues(self.config)
        if not issues: messagebox.showinfo("Repair Center", "No broken applications, icons, profiles, or preset items were found.", parent=self); return
        details = "\n".join(f"• {item.kind}: {item.name} — {item.detail}" for item in issues[:30])
        changed = False
        if any(item.kind == "application" for item in issues) and messagebox.askyesno(
                "Repair Center", details + "\n\nLocate missing applications and documents now?", parent=self):
            for application in self.config.applications:
                if not Path(application.path).expanduser().is_file():
                    replacement = filedialog.askopenfilename(parent=self, title=f"Locate {application.name}")
                    if replacement: application.path = replacement; changed = True
        if any(item.kind == "icon" for item in issues) and messagebox.askyesno(
                "Repair Center", "Clear references to missing custom icons?", parent=self):
            for site in self.config.websites:
                if site.icon_path and not site.icon_path.startswith("builtin:") and not Path(site.icon_path).is_file(): site.icon_path = ""; changed = True
        if changed: save_config(self.config_path, self.config); self.refresh_ui()
        remaining = find_repair_issues(self.config)
        if any(item.kind == "profile" for item in remaining) and messagebox.askyesno(
                "Repair Center", "One or more browser profiles remain unavailable. Open Settings to remap them?", parent=self):
            self.open_settings()
        elif remaining: messagebox.showwarning("Repair Center", "Some items still need attention.\n\n" + "\n".join(f"• {i.kind}: {i.name}" for i in remaining), parent=self)

    def import_organization_package(self) -> None:
        package = filedialog.askopenfilename(parent=self, title="Signed Organization Package", filetypes=[("JSON package", "*.json")])
        if not package: return
        public_key = filedialog.askopenfilename(parent=self, title="Organization Public Key", filetypes=[("PEM public key", "*.pem")])
        if not public_key: return
        try:
            verified = verify_organization_package(Path(package), Path(public_key))
            if not messagebox.askyesno(APP_NAME, "The package signature is valid. Import its approved configuration?", parent=self): return
            automatic_backup(self.config_path, app_data_dir() / "Backups"); self.config = merge_organization_package(self.config, verified)
            if "policy" in verified:
                policy_path = self.config_path.parent / "organization-policy.json"
                policy_temp = policy_path.with_suffix(".json.tmp")
                policy_temp.write_text(json.dumps(verified["policy"], indent=2) + "\n", encoding="utf-8")
                os.replace(policy_temp, policy_path)
                apply_policy(self.config, load_policy(policy_path))
            save_config(self.config_path, self.config); self.workspace_launcher.config = self.config; self.refresh_ui()
        except Exception as exc: messagebox.showerror(APP_NAME, f"Package signature or contents are invalid: {exc}", parent=self)

    def rollback_previous_version(self) -> None:
        if not getattr(sys, "frozen", False): messagebox.showinfo(APP_NAME, "Rollback is available in the packaged portable application.", parent=self); return
        if self.config.updates.installation_kind != "portable": messagebox.showinfo(APP_NAME, "Installed copies should rerun a previous trusted installer.", parent=self); return
        if not messagebox.askyesno(APP_NAME, "Restore the verified local backup of the previous portable version?", parent=self): return
        try:
            current = Path(sys.executable); staged, digest, size = stage_rollback(current, updates_dir())
            updater = current.with_name("Updater.exe")
            if not updater.is_file(): raise FileNotFoundError("Updater.exe was not found beside WorkLauncher.exe.")
            ready = updates_dir() / f"rollback-{os.getpid()}.ready"; ready.unlink(missing_ok=True)
            subprocess.Popen([str(updater), "--current", str(current), "--download", str(staged), "--sha256", digest,
                              "--size", str(size), "--parent-pid", str(os.getpid()), "--ready-file", str(ready)], shell=False)
            self.after(800, self.quit_application)
        except Exception as exc: messagebox.showerror(APP_NAME, f"Rollback could not start: {exc}", parent=self)

    def open_command_palette(self) -> None:
        commands = {
            "Open all work apps": self.open_all_work_apps,
            "Add website": self.add_first_website,
            "Import configuration": self.import_configuration,
            "Open settings": self.open_settings,
            "Manage workspaces": self.open_workspace_manager,
            "Check for updates": lambda: self.check_for_updates(force=True),
            "Check website health": self.check_website_health,
        }
        commands.update({f"Launch preset: {preset.name}": lambda value=preset: self.launch_preset(value)
                         for preset in self.config.presets})
        commands.update({f"Open website: {website.name}": lambda value=website: self.open_single(value)
                         for website in self.config.websites})
        CommandPalette(self, commands)

    def check_website_health(self) -> None:
        self.set_status("Checking configured website origins...")
        def worker():
            results = [check_url(item.url) for item in self.config.websites if item.enabled]
            self.after(0, lambda: self._show_health_results(results))
        threading.Thread(target=worker, daemon=True).start()

    def _show_health_results(self, results) -> None:
        failures = [f"{item.origin}: {item.status}" for item in results if not item.reachable]
        message = "All configured website origins are reachable." if not failures else "\n".join(failures)
        self.set_status(message.replace("\n", "; "))
        messagebox.showinfo(APP_NAME, message, parent=self)

    def _schedule_tick(self) -> None:
        if not self.winfo_exists():
            return
        online = network_available(timeout=0.25) if any(item.require_network for item in self.config.schedules) else True
        due = due_schedules(self.config.schedules, self.schedule_state, network_ok=online)
        if due:
            save_config(self.config_path, self.config)
        for schedule in due:
            preset = next((item for item in self.config.presets if item.name == schedule.preset), None)
            if preset:
                self._confirm_scheduled_launch(schedule, preset)
        self.after(15000, self._schedule_tick)

    def _confirm_scheduled_launch(self, schedule, preset) -> None:
        if self.config.settings.notifications:
            if not (self.tray and self.tray.notify(f'{preset.name} is ready. Open Work Launcher to launch, snooze, or cancel.', "Scheduled Workspace")):
                notify("Scheduled Workspace", f"{preset.name} is ready")
        if schedule.confirm_seconds == 0:
            self.launch_preset(preset)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Scheduled Workspace")
        dialog.transient(self)
        dialog.grab_set()
        remaining = tk.IntVar(value=schedule.confirm_seconds)
        ttk.Label(dialog, text=f'Scheduled preset "{preset.name}" is ready.', padding=14).pack()
        label = ttk.Label(dialog, padding=(14, 0, 14, 10))
        label.pack()
        buttons = ttk.Frame(dialog, padding=14)
        buttons.pack(fill="x")
        cancelled = {"value": False}
        def cancel():
            cancelled["value"] = True
            dialog.destroy()
        def launch():
            if dialog.winfo_exists():
                dialog.destroy()
            self.launch_preset(preset)
        def snooze():
            cancelled["value"] = True; dialog.destroy()
            self.set_status(f'Scheduled preset "{preset.name}" snoozed for 5 minutes.')
            self.after(5 * 60 * 1000, lambda: self._confirm_scheduled_launch(schedule, preset))
        ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
        ttk.Button(buttons, text="Snooze 5 min", command=snooze).pack(side="right", padx=5)
        ttk.Button(buttons, text="Launch Now", command=launch, style="Primary.TButton").pack(side="right", padx=5)
        dialog.protocol("WM_DELETE_WINDOW", cancel)
        def tick():
            if cancelled["value"] or not dialog.winfo_exists():
                return
            label.configure(text=f"Launching automatically in {remaining.get()} seconds.")
            if remaining.get() <= 0:
                launch()
                return
            remaining.set(remaining.get() - 1)
            dialog.after(1000, tick)
        tick()

    def _ensure_tray(self) -> None:
        if self.tray:
            return
        callbacks = {preset.name: lambda value=preset: self.after(0, lambda: self.launch_preset(value))
                     for preset in self.config.presets}
        self.tray = TrayController(
            lambda: self.after(0, self._show_from_tray),
            callbacks,
            lambda: self.after(0, lambda: self.check_for_updates(force=True)),
            lambda: self.after(0, self.quit_application),
        )
        try:
            self.tray.start()
        except Exception as exc:
            logging.warning("System tray unavailable: %s", exc)
            self.tray = None

    def _show_from_tray(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_application(self) -> None:
        if self.hotkey: self.hotkey.stop(); self.hotkey = None
        if self.tray:
            self.tray.stop()
            self.tray = None
        self._save_window_state()
        self.destroy()

    def center_first_launch(self) -> None:
        self.update_idletasks()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(max(self.config.settings.window_width, DEFAULT_MIN_WINDOW_WIDTH), max(screen_w - 80, DEFAULT_MIN_WINDOW_WIDTH))
        height = min(max(self.config.settings.window_height, DEFAULT_MIN_WINDOW_HEIGHT), max(screen_h - 100, DEFAULT_MIN_WINDOW_HEIGHT))
        if (
            self.config.settings.window_x is not None
            and self.config.settings.window_y is not None
            and self.config.settings.remember_window_position
        ):
            saved_x = self.config.settings.window_x
            saved_y = self.config.settings.window_y
            if saved_x < screen_w - 80 and saved_y < screen_h - 80 and saved_x + width > 80 and saved_y + height > 80:
                self.geometry(f"{width}x{height}+{saved_x}+{saved_y}")
            else:
                self.geometry(f"{width}x{height}+{max((screen_w - width) // 2, 0)}+{max((screen_h - height) // 2, 0)}")
        else:
            x = max((screen_w - width) // 2, 0)
            y = max((screen_h - height) // 2, 0)
            self.geometry(f"{width}x{height}+{x}+{y}")
        if self.config.settings.window_maximized:
            self.after_idle(lambda: self.state("zoomed"))

    def set_status(self, message: str) -> None:
        self.status.set(message)
        logging.info(message)

    def apply_visual_style(self, preset: str | None = None) -> None:
        self.palette = apply_visual_style(self, preset or self.config.settings.visual_style)

    def _selected_websites(self) -> list[WebsiteConfig]:
        selected = []
        for site, var in zip(self.displayed_websites, self.website_vars):
            site.selected = var.get()
            if site.selected and site.enabled:
                selected.append(site)
        save_config(self.config_path, self.config)
        return selected

    def select_all(self) -> None:
        for site, var in zip(self.displayed_websites, self.website_vars):
            var.set(site.enabled)
        self._selected_websites()
        self._selection_changed()
        self.set_status("All websites selected.")

    def clear_selection(self) -> None:
        for var in self.website_vars:
            var.set(False)
        self._selected_websites()
        self._selection_changed()
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
        latest = snapshot["latest_version"]
        if snapshot["last_error"] not in ("", "None", None):
            summary = "Updates unavailable"
        elif latest in ("", "Unknown", None):
            summary = "Updates: not checked"
        elif latest == __version__:
            summary = f"✓ Up to date · v{__version__}"
        else:
            summary = f"Update v{latest} available"
        self.update_summary_var.set(summary)
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
        has_websites = any(site.enabled for site in self.config.websites)
        has_selection = any(site.enabled and var.get() for site, var in zip(self.displayed_websites, self.website_vars))
        self.open_all_button.configure(state="normal" if enabled and has_websites else "disabled")
        self.open_selected_button.configure(state="normal" if enabled and has_selection else "disabled")
        self.launch_group_button.configure(state="normal" if enabled and has_websites else "disabled")
        self.launch_preset_button.configure(state="normal" if enabled and bool(self.config.presets) else "disabled")

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
        if self.config.settings.minimize_to_tray:
            self._ensure_tray()
            self.withdraw()
            return
        self.quit_application()

    def _save_window_state(self) -> None:
        maximized = self.state() == "zoomed"
        self.config.settings.window_maximized = maximized
        if not maximized:
            self.config.settings.window_width = self.winfo_width()
            self.config.settings.window_height = self.winfo_height()
            if self.config.settings.remember_window_position:
                self.config.settings.window_x = self.winfo_x()
                self.config.settings.window_y = self.winfo_y()
        save_config(self.config_path, self.config)


def main() -> int:
    lock = SingleInstance(app_data_dir() / "work-launcher.lock")
    try:
        lock.acquire()
    except AlreadyRunningError:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, "Work Launcher is already running.", APP_NAME, 0x40)
        except Exception:
            pass
        return 1
    try:
        app = WorkLauncherApp()
        app.mainloop()
    finally:
        lock.release()
    return 0
