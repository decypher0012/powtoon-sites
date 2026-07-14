from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "WorkLauncher.iss"
MARKER = ROOT / "installer" / "install-mode.json"
EXPECTED_SOURCES = {
    r"..\dist\WorkLauncher.exe",
    r"..\dist\Updater.exe",
    "install-mode.json",
}
APP_ID = "7A07E62F-0C3A-45D2-91E8-4E5BE929A8D9"


def audit_installer_definition(script: Path = SCRIPT, marker: Path = MARKER) -> None:
    text = script.read_text(encoding="utf-8")
    normalized = text.lower()
    if f"appid={{{{{APP_ID.lower()}}}" not in normalized:
        raise RuntimeError("The installer AppId changed or is missing.")
    required = {
        "privilegesrequired=lowest",
        "allownoicons=yes",
        r"defaultdirname={localappdata}\programs\worklauncher",
        "architecturesallowed=x64compatible",
        "closeapplications=yes",
        "restartapplications=no",
    }
    missing = sorted(item for item in required if item not in normalized)
    if missing:
        raise RuntimeError(f"Installer safety directives are missing: {missing}")
    sources = set(re.findall(r'^Source:\s*"([^"]+)"', text, flags=re.MULTILINE))
    if sources != EXPECTED_SOURCES:
        raise RuntimeError(f"Unexpected installer file sources: {sorted(sources)}")
    prohibited = ("config.json", "work_launcher.log", "appdata\\worklauncher", "userprofile", ".env")
    if any(item in normalized for item in prohibited):
        raise RuntimeError("Installer definition references prohibited user or configuration data.")
    if "check: shouldlaunch" not in normalized or "'/nolaunch'" not in normalized:
        raise RuntimeError("Installer does not provide the deterministic no-launch switch.")
    if "#ifndef fileversion" not in normalized or "versioninfoversion={#fileversion}" not in normalized:
        raise RuntimeError("Installer does not use the build-derived numeric Windows file version.")
    if json.loads(marker.read_text(encoding="utf-8")) != {"mode": "inno-user"}:
        raise RuntimeError("Installer mode marker is invalid.")


if __name__ == "__main__":
    audit_installer_definition()
    print("Installer definition audit passed.")
