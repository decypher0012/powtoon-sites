from __future__ import annotations

import logging
import os
from pathlib import Path


def discover_chrome(env: dict[str, str] | None = None) -> Path | None:
    env = os.environ if env is None else env
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = env.get(variable)
        if root:
            candidate = Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.is_file():
                logging.info("Chrome discovery succeeded via %s", variable)
                return candidate
    logging.error("Chrome discovery failed in standard installation locations")
    return None
