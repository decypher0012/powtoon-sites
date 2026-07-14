from __future__ import annotations

import logging
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path

from .config import AppConfig, WebsiteConfig, load_config, save_config
from .constants import APP_NAME, DEFAULT_MIN_WINDOW_HEIGHT, DEFAULT_MIN_WINDOW_WIDTH
from .launcher import WebsiteLauncher
from .logging_config import configure_logging
from .settings import reset_to_defaults, save_settings
from .startup import set_startup_enabled
from .browser_profiles import BrowserProfile, validate_profile
from .browser_discovery import discover_chrome
from .browser_launcher import BrowserLauncher


class SettingsWindow(tk.Toplevel):
    def __init__(self, master: "WorkLauncherApp") -> None:
        super().__init__(master)
        self.master_app = master
        self.title(f"{APP_NAME} Settings")
        self.resizable(True, True)
        self.geometry("720x680")
        self.transient(master)
        self.grab_set()
        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Websites are primarily edited in config.json.").pack(anchor="w")
        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True, pady=(10, 10))
        self.listbox = tk.Listbox(list_frame, height=10)
        self.listbox.pack(side="left", fill="both", expand=True)
        for site in self.master_app.config.websites:
            self.listbox.insert("end", f"{site.name} ({'enabled' if site.enabled else 'disabled'})")
        btns = ttk.Frame(list_frame)
        btns.pack(side="left", fill="y", padx=(10, 0))
        ttk.Button(btns, text="Enable", command=self.enable_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="Disable", command=self.disable_selected).pack(fill="x", pady=2)
        ttk.Button(btns, text="Move Up", command=self.move_up).pack(fill="x", pady=2)
        ttk.Button(btns, text="Move Down", command=self.move_down).pack(fill="x", pady=2)
        ttk.Label(btns, text="Browser profile").pack(anchor="w", pady=(12, 2))
        self.site_profile_var = tk.StringVar()
        self.site_profile_combo = ttk.Combobox(btns, textvariable=self.site_profile_var, state="readonly", width=23)
        self.site_profile_combo.pack(fill="x")
        self.site_profile_combo.bind("<<ComboboxSelected>>", self.assign_site_profile)
        self.listbox.bind("<<ListboxSelect>>", self.on_site_selected)
        profiles = ttk.LabelFrame(frame, text="Browser Profiles", padding=8)
        profiles.pack(fill="x", pady=(0, 10))
        self.profile_list = tk.Listbox(profiles, height=4)
        self.profile_list.pack(side="left", fill="x", expand=True)
        profile_buttons = ttk.Frame(profiles)
        profile_buttons.pack(side="left", padx=(8, 0))
        for text, command in (("Add", self.add_profile), ("Edit", self.edit_profile),
                              ("Duplicate", self.duplicate_profile), ("Delete", self.delete_profile),
                              ("Test Profile (opens tab)", self.test_profile)):
            ttk.Button(profile_buttons, text=text, command=command).pack(fill="x", pady=1)
        form = ttk.Frame(frame)
        form.pack(fill="x")
        self.delay_var = tk.StringVar(value=str(self.master_app.config.settings.launch_delay_seconds))
        self.cooldown_var = tk.StringVar(value=str(self.master_app.config.settings.duplicate_launch_cooldown_seconds))
        ttk.Label(form, text="Launch delay seconds").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.delay_var, width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Duplicate cooldown seconds").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.cooldown_var, width=12).grid(row=1, column=1, sticky="w")
        self.theme_var = tk.StringVar(value=self.master_app.config.settings.theme)
        ttk.Label(form, text="Theme").grid(row=2, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.theme_var, values=["system", "light", "dark"], state="readonly", width=10).grid(row=2, column=1, sticky="w")
        self.remember_var = tk.BooleanVar(value=self.master_app.config.settings.remember_window_position)
        self.startup_var = tk.BooleanVar(value=self.master_app.config.settings.launch_with_windows)
        ttk.Checkbutton(form, text="Remember window position", variable=self.remember_var).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(form, text="Launch Work Launcher when Windows starts", variable=self.startup_var).grid(row=4, column=0, columnspan=2, sticky="w")
        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(14, 0))
        ttk.Button(actions, text="Restore Defaults", command=self.restore_defaults).pack(side="left")
        ttk.Button(actions, text="Save", command=self.save).pack(side="right")
        self.refresh_profiles()

    def _selected_index(self) -> int | None:
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def enable_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self.master_app.config.websites[idx].enabled = True
        self.refresh()

    def disable_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        self.master_app.config.websites[idx].enabled = False
        self.refresh()

    def move_up(self) -> None:
        idx = self._selected_index()
        if idx is None or idx == 0:
            return
        items = self.master_app.config.websites
        items[idx - 1], items[idx] = items[idx], items[idx - 1]
        self.refresh(select=idx - 1)

    def move_down(self) -> None:
        idx = self._selected_index()
        if idx is None or idx >= len(self.master_app.config.websites) - 1:
            return
        items = self.master_app.config.websites
        items[idx + 1], items[idx] = items[idx], items[idx + 1]
        self.refresh(select=idx + 1)

    def restore_defaults(self) -> None:
        self.master_app.config = reset_to_defaults()
        self.refresh()

    def refresh(self, select: int | None = None) -> None:
        self.listbox.delete(0, "end")
        for site in self.master_app.config.websites:
            self.listbox.insert("end", f"{site.name} ({'enabled' if site.enabled else 'disabled'})")
        if select is not None:
            self.listbox.selection_set(select)
            self.on_site_selected()

    def refresh_profiles(self) -> None:
        self.profile_list.delete(0, "end")
        self.profile_ids = list(self.master_app.config.browser_profiles)
        for key in self.profile_ids:
            profile = self.master_app.config.browser_profiles[key]
            self.profile_list.insert("end", f"{profile.name} [{profile.type}] ({key})")
        self.profile_labels = {self.master_app.config.browser_profiles[key].name: key for key in self.profile_ids}
        self.site_profile_combo.configure(values=list(self.profile_labels))

    def on_site_selected(self, event=None) -> None:
        idx = self._selected_index()
        if idx is not None:
            key = self.master_app.config.websites[idx].browser_profile
            profile = self.master_app.config.browser_profiles.get(key)
            self.site_profile_var.set(profile.name if profile else "")

    def assign_site_profile(self, event=None) -> None:
        idx = self._selected_index()
        key = self.profile_labels.get(self.site_profile_var.get())
        if idx is not None and key:
            self.master_app.config.websites[idx].browser_profile = key

    def _profile_index(self) -> int | None:
        selection = self.profile_list.curselection()
        return selection[0] if selection else None

    def _edit_values(self, key: str, profile: BrowserProfile) -> tuple[str, BrowserProfile] | None:
        new_key = simpledialog.askstring(APP_NAME, "Profile ID", initialvalue=key, parent=self)
        if not new_key:
            return None
        name = simpledialog.askstring(APP_NAME, "Display name", initialvalue=profile.name, parent=self)
        browser_type = simpledialog.askstring(APP_NAME, "Browser type (system or chrome)", initialvalue=profile.type, parent=self)
        if not name or browser_type not in {"system", "chrome"}:
            messagebox.showerror(APP_NAME, "Name is required and type must be system or chrome.", parent=self)
            return None
        executable, user_data, directory, fallback = "", "", "", False
        if browser_type == "chrome":
            executable = filedialog.askopenfilename(title="Select chrome.exe (Cancel for automatic discovery)",
                                                     filetypes=[("Chrome executable", "chrome.exe"), ("Programs", "*.exe")], parent=self)
            user_data = filedialog.askdirectory(title="Select Chrome User Data directory", parent=self) or profile.user_data_dir
            directory = simpledialog.askstring(APP_NAME, "Chrome Profile Directory (for example Profile 4)",
                                               initialvalue=profile.profile_directory, parent=self) or ""
            fallback = messagebox.askyesno(APP_NAME, "Allow explicit fallback to the Windows default browser if Chrome fails?", parent=self)
        return new_key.strip(), BrowserProfile(name.strip(), browser_type, executable, user_data, directory, fallback)

    def add_profile(self) -> None:
        result = self._edit_values("new-profile", BrowserProfile("New Browser Profile", "chrome"))
        if result:
            key, profile = result
            if key in self.master_app.config.browser_profiles:
                messagebox.showerror(APP_NAME, "That profile ID already exists.", parent=self); return
            self.master_app.config.browser_profiles[key] = profile
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
            self.refresh_profiles()

    def delete_profile(self) -> None:
        idx = self._profile_index()
        if idx is None: return
        key = self.profile_ids[idx]
        used = [site.name for site in self.master_app.config.websites if site.browser_profile == key]
        if used:
            messagebox.showerror(APP_NAME, "Cannot delete an in-use profile. Reassign: " + ", ".join(used), parent=self); return
        del self.master_app.config.browser_profiles[key]
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

    def save(self) -> None:
        try:
            self.master_app.config.settings.launch_delay_seconds = float(self.delay_var.get())
            self.master_app.config.settings.duplicate_launch_cooldown_seconds = float(self.cooldown_var.get())
            self.master_app.config.settings.theme = self.theme_var.get()
            self.master_app.config.settings.remember_window_position = self.remember_var.get()
            self.master_app.config.settings.launch_with_windows = self.startup_var.get()
            for profile in self.master_app.config.browser_profiles.values():
                validate_profile(profile, discover_chrome, require_files=profile.type == "chrome")
            save_settings(self.master_app.config_path, self.master_app.config)
            set_startup_enabled(self.startup_var.get(), self.master_app.executable_path)
            self.master_app.refresh_ui()
            self.master_app.launcher.browser_profiles = self.master_app.config.browser_profiles
            self.master_app.set_status("Settings saved.")
            self.destroy()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save settings: {exc}")


class WorkLauncherApp(tk.Tk):
    def __init__(self, config_path: Path | None = None) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.minsize(DEFAULT_MIN_WINDOW_WIDTH, DEFAULT_MIN_WINDOW_HEIGHT)
        self.config_path = config_path or Path.home() / "AppData" / "Roaming" / "WorkLauncher" / "config.json"
        self.executable_path = Path(sys.executable)
        self.log_path = configure_logging()
        self.config, warnings = load_config(self.config_path)
        self.launcher = WebsiteLauncher(browser_profiles=self.config.browser_profiles)
        self.is_launching = False
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._build()
        self.center_first_launch()
        self.refresh_ui()
        for warning in warnings:
            self.set_status(warning)
            logging.warning(warning)

    def _build(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.open_all_button = ttk.Button(root, text="Open All Work Apps", command=self.open_all_work_apps)
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
        self.open_selected_button = ttk.Button(ctrl_frame, text="Open Selected", command=self.open_selected)
        self.open_selected_button.pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Select All", command=self.select_all).pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Clear Selection", command=self.clear_selection).pack(fill="x", pady=2)
        ttk.Button(ctrl_frame, text="Settings", command=self.open_settings).pack(fill="x", pady=(10, 2))
        ttk.Button(ctrl_frame, text="Close", command=self.destroy).pack(fill="x", pady=2)
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
        try:
            for index, website in enumerate(websites):
                if index > 0 and self.config.settings.launch_delay_seconds > 0:
                    self.after(int(self.config.settings.launch_delay_seconds * 1000))
                    self.update()
                result = self.launcher.open_website(website)
                self.set_status(result.message)
            self.set_status("Launch complete.")
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
