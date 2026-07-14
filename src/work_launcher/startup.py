from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .constants import APP_FILENAME


@dataclass
class StartupState:
    enabled: bool
    path: Path


def get_startup_dir() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def get_startup_entry_path() -> Path:
    return get_startup_dir() / f"{APP_FILENAME}.cmd"


def startup_enabled() -> bool:
    return get_startup_entry_path().exists()


def set_startup_enabled(enabled: bool, executable_path: Path) -> StartupState:
    entry = get_startup_entry_path()
    entry.parent.mkdir(parents=True, exist_ok=True)
    if enabled:
        executable_path=executable_path.resolve()
        if not executable_path.is_file(): raise OSError("The Work Launcher executable does not exist at the current location.")
        temporary=entry.with_suffix(entry.suffix+".tmp")
        temporary.write_text(f'@echo off\r\nstart "" "{executable_path}"\r\n', encoding="utf-8")
        os.replace(temporary,entry)
    elif entry.exists():
        entry.unlink()
    return StartupState(enabled=enabled, path=entry)


def open_startup_folder() -> None:
    subprocess.Popen(["explorer", str(get_startup_dir())])
