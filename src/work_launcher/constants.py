from __future__ import annotations

from pathlib import Path
import os

APP_NAME = "Work Launcher"
APP_FILENAME = "WorkLauncher"
CONFIG_FILENAME = "config.json"
DEFAULT_LAUNCH_DELAY_SECONDS = 0.5
DEFAULT_DUPLICATE_LAUNCH_COOLDOWN_SECONDS = 5.0
DEFAULT_THEME = "system"
DEFAULT_VISUAL_STYLE = "enterprise"
DEFAULT_MIN_WINDOW_WIDTH = 560
DEFAULT_MIN_WINDOW_HEIGHT = 520
DEFAULT_WINDOW_WIDTH = 760
DEFAULT_WINDOW_HEIGHT = 640
CONFIG_VERSION = 6
UPDATE_GITHUB_OWNER = "decypher0012"
UPDATE_GITHUB_REPOSITORY = "powtoon-sites"
VISUAL_STYLES = ("enterprise", "dark", "friendly")
SYSTEM_PROFILE_ID = "system-default"
WORK_PROFILE_ID = "chrome-work"
DEFAULT_BROWSER_PROFILES = {
    SYSTEM_PROFILE_ID: {"name": "Windows Default Browser", "type": "system", "fallback_to_system_browser": False},
    WORK_PROFILE_ID: {
        "name": "Chrome Work (configure during setup)", "type": "system", "fallback_to_system_browser": False,
    },
}

DEFAULT_WEBSITES = []


def app_data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_FILENAME
