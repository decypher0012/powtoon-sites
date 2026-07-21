from __future__ import annotations

import json
import platform
import zipfile
from pathlib import Path

from .config import AppConfig
from .version import __version__


def sanitized_summary(config: AppConfig) -> dict:
    return {
        "version": __version__,
        "platform": platform.platform(),
        "config_version": config.config_version,
        "counts": {"websites": len(config.websites), "applications": len(config.applications),
                   "presets": len(config.presets), "schedules": len(config.schedules)},
        "settings": {"theme": config.settings.theme, "visual_style": config.settings.visual_style,
                     "tray": config.settings.minimize_to_tray, "startup": config.settings.launch_with_windows},
        "browser_profiles": [{"id": key, "name": value.name, "type": value.type}
                             for key, value in config.browser_profiles.items()],
    }


def create_diagnostics_bundle(config: AppConfig, destination: Path, log_path: Path | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.json", json.dumps(sanitized_summary(config), indent=2) + "\n")
        if log_path and log_path.is_file():
            # Logs are already sanitized by the app; bound the exported tail to avoid oversized bundles.
            archive.writestr("recent.log", log_path.read_bytes()[-512_000:])
    return destination
