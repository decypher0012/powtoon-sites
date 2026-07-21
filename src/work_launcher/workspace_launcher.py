from __future__ import annotations

import os
import socket
import subprocess
import time
import threading
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import AppConfig, ApplicationConfig, PresetConfig
from .launcher import WebsiteLauncher


@dataclass(frozen=True)
class WorkspaceLaunchResult:
    item: str
    kind: str
    success: bool
    status: str
    elapsed_seconds: float


def network_available(host: str = "1.1.1.1", port: int = 53, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def process_is_running(executable: Path, tasklist: Callable = subprocess.run) -> bool:
    if os.name != "nt":
        return False
    result = tasklist(
        ["tasklist", "/FI", f"IMAGENAME eq {executable.name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.returncode == 0 and executable.name.casefold() in result.stdout.casefold()


class WorkspaceLauncher:
    def __init__(self, config: AppConfig, website_launcher: WebsiteLauncher,
                 popen: Callable = subprocess.Popen, process_check: Callable = process_is_running,
                 system_open: Callable | None = None):
        self.config = config
        self.website_launcher = website_launcher
        self.popen = popen
        self.process_check = process_check
        self.system_open = system_open or getattr(os, "startfile", None)

    def launch_application(self, application: ApplicationConfig) -> WorkspaceLaunchResult:
        started = time.monotonic()
        path = Path(application.path).expanduser()
        try:
            if not application.enabled:
                return WorkspaceLaunchResult(application.name, "application", False, "disabled", 0)
            if not path.is_file():
                raise FileNotFoundError(f"Application was not found: {path}")
            if application.only_if_not_running and self.process_check(path):
                return WorkspaceLaunchResult(application.name, "application", True, "already running", time.monotonic() - started)
            working = Path(application.working_directory).expanduser() if application.working_directory else path.parent
            if not working.is_dir():
                raise FileNotFoundError(f"Working directory was not found: {working}")
            if path.suffix.casefold() in {".exe", ".com"}:
                self.popen([str(path), *application.arguments], cwd=str(working), shell=False)
            elif self.system_open and not application.arguments:
                self.system_open(str(path))
            else:
                raise ValueError("Documents require a Windows file association and cannot use arguments.")
            return WorkspaceLaunchResult(application.name, "application", True, "opened", time.monotonic() - started)
        except Exception as exc:
            return WorkspaceLaunchResult(application.name, "application", False, str(exc), time.monotonic() - started)

    def launch_preset(self, preset: PresetConfig, cancel_event: threading.Event | None = None,
                      confirm_item: Callable[[str], bool] | None = None) -> list[WorkspaceLaunchResult]:
        websites = {item.name: item for item in self.config.websites}
        applications = {item.name: item for item in self.config.applications}
        delay = self.config.settings.launch_delay_seconds if preset.launch_delay_seconds is None else preset.launch_delay_seconds
        results = []
        for index, reference in enumerate(preset.items):
            if cancel_event and cancel_event.is_set():
                results.append(WorkspaceLaunchResult(reference.split(":", 1)[1], "cancelled", False, "cancelled", 0)); break
            effective_delay = preset.item_delays.get(reference, delay)
            if index and effective_delay:
                if cancel_event and cancel_event.wait(effective_delay): break
                if not cancel_event: time.sleep(effective_delay)
            kind, name = reference.split(":", 1)
            rule = preset.item_rules.get(reference, {})
            if datetime.now().weekday() not in rule.get("weekdays", list(range(7))):
                results.append(WorkspaceLaunchResult(name, kind, True, "skipped by weekday rule", 0)); continue
            if rule.get("require_network") and not network_available(timeout=0.5):
                results.append(WorkspaceLaunchResult(name, kind, False, "network rule not satisfied", 0))
                if preset.stop_on_failure: break
                continue
            if preset.run_mode == "dry-run":
                results.append(WorkspaceLaunchResult(name, kind, True, "would open", 0)); continue
            if preset.run_mode == "step" and confirm_item and not confirm_item(name):
                results.append(WorkspaceLaunchResult(name, kind, False, "skipped by user", 0)); continue
            started = time.monotonic()
            if kind == "website":
                website = websites[name]
                result = self.website_launcher.open_website(website)
                results.append(WorkspaceLaunchResult(name, kind, result.success, result.message, time.monotonic() - started))
            else:
                results.append(self.launch_application(applications[name]))
            if preset.stop_on_failure and results and not results[-1].success:
                break
        return results
