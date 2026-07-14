from __future__ import annotations

from pathlib import Path
import os

APP_NAME = "Work Launcher"
APP_FILENAME = "WorkLauncher"
CONFIG_FILENAME = "config.json"
DEFAULT_LAUNCH_DELAY_SECONDS = 0.5
DEFAULT_DUPLICATE_LAUNCH_COOLDOWN_SECONDS = 5.0
DEFAULT_THEME = "system"
DEFAULT_MIN_WINDOW_WIDTH = 560
DEFAULT_MIN_WINDOW_HEIGHT = 520
DEFAULT_WINDOW_WIDTH = 760
DEFAULT_WINDOW_HEIGHT = 640
CONFIG_VERSION = 4
SYSTEM_PROFILE_ID = "system-default"
WORK_PROFILE_ID = "chrome-work"
DEFAULT_BROWSER_PROFILES = {
    SYSTEM_PROFILE_ID: {"name": "Windows Default Browser", "type": "system", "fallback_to_system_browser": False},
    WORK_PROFILE_ID: {
        "name": "Chrome Work (configure during setup)", "type": "system", "fallback_to_system_browser": False,
    },
}

DEFAULT_WEBSITES = [
    {
        "name": "Renewal Tracker Admin",
        "url": "https://www.renewals-tracker.powtoon.com/admin",
        "enabled": True,
        "selected": True,
        "browser_profile": WORK_PROFILE_ID,
    },
    {
        "name": "Gmail",
        "url": "https://mail.google.com/",
        "enabled": True,
        "selected": True,
        "browser_profile": WORK_PROFILE_ID,
    },
    {
        "name": "Google Calendar",
        "url": "https://calendar.google.com/",
        "enabled": True,
        "selected": True,
        "browser_profile": WORK_PROFILE_ID,
    },
    {
        "name": "Google Keep",
        "url": "https://keep.google.com/",
        "enabled": True,
        "selected": True,
        "browser_profile": WORK_PROFILE_ID,
    },
    {
        "name": "HubSpot Dashboard",
        "url": "https://app.hubspot.com/reports-dashboard/3444711/view/10170444",
        "enabled": True,
        "selected": True,
        "browser_profile": WORK_PROFILE_ID,
    },
    {
        "name": "Powtoon Okta",
        "url": "https://powtoon.okta.com/",
        "enabled": True,
        "selected": True,
        "browser_profile": WORK_PROFILE_ID,
    },
]


def app_data_dir() -> Path:
    return Path.home() / "AppData" / "Local" / APP_FILENAME
