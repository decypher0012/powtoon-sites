from __future__ import annotations

import json
import sys
from pathlib import Path


INSTALL_MARKER = "install-mode.json"
INSTALLER_MODE = "inno-user"


def executable_directory(executable: Path | None = None) -> Path:
    if executable is not None:
        return executable.resolve().parent
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def installation_kind(executable: Path | None = None) -> str:
    marker = executable_directory(executable) / INSTALL_MARKER
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "portable"
    return "installer" if data == {"mode": INSTALLER_MODE} else "portable"
