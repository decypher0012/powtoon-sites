from __future__ import annotations

import threading
import queue
import tkinter as tk
from tkinter import messagebox, ttk

from .browser_launcher import BrowserLauncher
from .browser_profiles import BrowserProfile
from .browser_scanner import scan_browsers
from .setup_service import cancel_setup, complete_setup, configure_setup_profile, import_detected_profile
from .profile_health import validate_profile_assignment
from .manual_profile_dialog import ManualProfileDialog
from .browser_scanner import DiscoveredBrowserProfile


class SetupWizard(tk.Toplevel):
    def __init__(self, master, config, config_path, on_complete=None, manual_callback=None):
        super().__init__(master); self.title("Work Launcher Setup"); self.geometry("720x560"); self.transient(master); self.grab_set()
        self.config, self.config_path, self.on_complete, self.manual_callback = config, config_path, on_complete, manual_callback
        self.step = 0; self.results = []; self.profiles = []; self.selected_profile = None; self.manual_profile_key = None; self.site_vars = []; self.scan_queue = queue.Queue(); self.pending_scans = 0
        self.body = ttk.Frame(self, padding=18); self.body.pack(fill="both", expand=True)
        self.nav = ttk.Frame(self, padding=10); self.nav.pack(fill="x")
        self.back_button = ttk.Button(self.nav, text="Back", command=self.back); self.back_button.pack(side="left")
        self.cancel_button = ttk.Button(self.nav, text="Cancel", command=self.cancel); self.cancel_button.pack(side="right", padx=4)
        self.next_button = ttk.Button(self.nav, text="Next", command=self.next); self.next_button.pack(side="right", padx=4)
        self.bind("<Escape>", lambda event: self.cancel()); self.show_step()

    def clear(self):
        for child in self.body.winfo_children(): child.destroy()

    def show_step(self):
        self.clear(); self.back_button.configure(state="normal" if self.step else "disabled"); self.next_button.configure(text="Finish" if self.step == 4 else "Next")
        [self.welcome, self.scan_page, self.select_page, self.assign_page, self.review_page, self.complete_page][self.step]()

    def welcome(self):
        ttk.Label(self.body, text="Welcome to Work Launcher", font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(20, 15))
        ttk.Label(self.body, text="Work Launcher can open your work websites using the browser profile you already use for work.", wraplength=620).pack(anchor="w")
        ttk.Label(self.body, text="Work Launcher only detects browser installation and profile names.\nIt does not read passwords, cookies, browsing history, or website content.", wraplength=620).pack(anchor="w", pady=25)

    def scan_page(self):
        ttk.Label(self.body, text="Scan Browsers", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.scan_status = tk.StringVar(value="Scanning installed browsers and profiles..."); ttk.Label(self.body, textvariable=self.scan_status).pack(anchor="w", pady=10)
        self.scan_list = tk.Listbox(self.body, height=14); self.scan_list.pack(fill="both", expand=True)
        ttk.Button(self.body, text="Rescan", command=self.start_scan).pack(anchor="e", pady=8); self.start_scan()

    def start_scan(self):
        generation = getattr(self, "scan_generation", 0) + 1; self.scan_generation = generation; self.pending_scans += 1
        if hasattr(self, "scan_status"): self.scan_status.set("Scanning installed browsers and profiles...")
        threading.Thread(target=self._worker, args=(generation,), daemon=True).start()
        self.after(50, self._poll_scan)

    def _worker(self, generation):
        try: self.scan_queue.put((generation, scan_browsers(), None))
        except Exception as exc: self.scan_queue.put((generation, [], type(exc).__name__))

    def _poll_scan(self):
        try: generation, results, error = self.scan_queue.get_nowait()
        except queue.Empty:
            if self.winfo_exists() and self.pending_scans: self.after(50, self._poll_scan)
            return
        self.pending_scans = max(0, self.pending_scans - 1)
        if error:
            if hasattr(self,"scan_status"): self.scan_status.set("Browser scan failed. Use Configure Manually or try Rescan.")
            return
        self._scan_done(generation, results)

    def _scan_done(self, generation, results):
        if generation != self.scan_generation or not self.winfo_exists(): return
        self.results = results; self.profiles = [profile for result in results for profile in result.profiles]
        if hasattr(self, "scan_list"):
            self.scan_list.delete(0, "end")
            for result in results: self.scan_list.insert("end", f"{result.browser_name} — {'Installed' if result.executable_path else 'Not found'} — {len(result.profiles)} profiles{(' — ' + result.warning) if result.warning else ''}")
            self.scan_status.set("Scan complete.")

    def select_page(self):
        ttk.Label(self.body, text="Select Work Browser Profile", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.profile_choice = tk.IntVar(value=0 if self.profiles else -1)
        canvas = ttk.Frame(self.body); canvas.pack(fill="both", expand=True, pady=10)
        for index, profile in enumerate(self.profiles):
            ttk.Radiobutton(canvas, variable=self.profile_choice, value=index,
                text=f"{profile.browser_name} — {profile.profile_display_name}  [{profile.profile_directory}]{'  Default' if profile.is_default else ''}").pack(anchor="w", pady=2)
        if not self.profiles: ttk.Label(canvas, text="No profiles detected. Rescan or configure a browser manually.").pack(anchor="w")
        actions = ttk.Frame(self.body); actions.pack(fill="x")
        ttk.Button(actions, text="Configure Manually", command=self.configure_manual).pack(side="left")
        ttk.Button(actions, text="Rescan", command=lambda: self._go_scan()).pack(side="left", padx=5)

    def assign_page(self):
        ttk.Label(self.body, text="Assign Websites", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(self.body, text="Checked websites will use the selected work profile. Unchecked websites will use Windows Default Browser.").pack(anchor="w", pady=8)
        self.site_vars = []
        for website in self.config.websites:
            var = tk.BooleanVar(value=True); self.site_vars.append(var); ttk.Checkbutton(self.body, text=website.name, variable=var).pack(anchor="w")

    def review_page(self):
        profile = self.selected_profile
        assigned = sum(variable.get() for variable in self.site_vars)
        ttk.Label(self.body, text="Review", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(self.body, text=f"Browser: {profile.browser_name}\n\nProfile: {profile.profile_display_name} — {profile.profile_directory}\n\nWebsites assigned: {assigned}").pack(anchor="w", pady=15)
        ttk.Button(self.body, text="Test Profile (opens Google)", command=self.test_profile).pack(anchor="w")

    def complete_page(self):
        ttk.Label(self.body, text="Setup complete.", font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=20)
        ttk.Label(self.body, text=f"Your work websites are now configured to open in:\n{self.selected_profile.browser_name} — {self.selected_profile.profile_display_name}").pack(anchor="w")
        self.next_button.configure(text="Finish")

    def next(self):
        if self.step == 1 and not self.results: messagebox.showinfo(self.title(), "Wait for scanning to complete.", parent=self); return
        if self.step == 2:
            choice = self.profile_choice.get()
            if choice < 0 or choice >= len(self.profiles): messagebox.showerror(self.title(), "Select or manually configure a work profile.", parent=self); return
            self.selected_profile = self.profiles[choice]
            candidate = BrowserProfile(self.selected_profile.profile_display_name, self.selected_profile.browser_type,
                self.selected_profile.executable_path, self.selected_profile.user_data_dir, self.selected_profile.profile_directory)
            try: validate_profile_assignment_for_setup(candidate)
            except Exception as exc: messagebox.showerror(self.title(), f"The selected profile is unavailable: {exc}", parent=self); return
        if self.step == 3:
            key = self.manual_profile_key or configure_setup_profile(self.config, self.selected_profile)
            for index, website in enumerate(self.config.websites): website.browser_profile = key if self.site_vars[index].get() else "system-default"
        if self.step == 4:
            try:
                for profile_id in {website.browser_profile for website in self.config.websites}: validate_profile_assignment(self.config, profile_id)
                complete_setup(self.config_path, self.config)
            except Exception as exc: messagebox.showerror(self.title(),f"Setup cannot be completed: {exc}",parent=self); return
        if self.step == 5:
            if self.on_complete: self.on_complete()
            self.destroy(); return
        self.step += 1; self.show_step()

    def back(self):
        if self.step: self.step -= 1; self.show_step()

    def _go_scan(self): self.step = 1; self.show_step()
    def configure_manual(self):
        if self.manual_callback: self.manual_callback(); return
        dialog = ManualProfileDialog(self); self.wait_window(dialog)
        if dialog.result:
            profile = dialog.result
            base = "-".join(profile.name.lower().split()) or "manual-profile"; key = base; number = 2
            while key in self.config.browser_profiles: key = f"{base}-{number}"; number += 1
            profile.discovery = {"source": "manual"}; self.config.browser_profiles[key] = profile; self.manual_profile_key = key
            self.selected_profile = DiscoveredBrowserProfile(profile.type, profile.name, profile.executable_path,
                profile.user_data_dir, profile.profile_directory, profile.name)
            self.step = 3; self.show_step()
    def cancel(self):
        if messagebox.askyesno(self.title(), "Cancel setup and use the Windows default browser where safe?", parent=self):
            cancel_setup(self.config_path, self.config); self.destroy()
    def test_profile(self):
        item = self.selected_profile; profile = BrowserProfile(item.profile_display_name, item.browser_type, item.executable_path, item.user_data_dir, item.profile_directory)
        try: BrowserLauncher().launch(profile, ["https://www.google.com/"], ["Setup profile test"])
        except Exception as exc: messagebox.showerror(self.title(), f"Unable to test profile: {exc}", parent=self)


def validate_profile_assignment_for_setup(profile: BrowserProfile) -> None:
    from .browser_profiles import validate_profile
    validate_profile(profile, require_files=profile.type != "system")
