from __future__ import annotations

import hashlib
import json
import sys
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from work_launcher.version import __version__


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): value.update(chunk)
    return value.hexdigest()


def main() -> int:
    dist = ROOT / "dist"; app = dist / "WorkLauncher.exe"; updater = dist / "Updater.exe"
    if not app.is_file() or not updater.is_file(): raise SystemExit("Both executables must exist before generating release metadata.")
    app_hash, updater_hash = digest(app), digest(updater); setup = dist / "WorkLauncher-Setup.exe"
    sums = f"{app_hash}  WorkLauncher.exe\n{updater_hash}  Updater.exe\n"
    if setup.is_file(): sums += f"{digest(setup)}  WorkLauncher-Setup.exe\n"
    (dist / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    channel=os.environ.get("RELEASE_CHANNEL","stable").lower()
    if channel not in {"stable","beta"}: raise SystemExit("RELEASE_CHANNEL must be stable or beta")
    release_date=os.environ.get("RELEASE_DATE",date.today().isoformat())
    try: date.fromisoformat(release_date)
    except ValueError: raise SystemExit("RELEASE_DATE must be YYYY-MM-DD")
    metadata = {"version": __version__, "release_date": release_date, "channel": channel, "minimum_supported_version": "1.0.0", "mandatory": False,
        "download": {"portable": "WorkLauncher.exe"}, "size": {"portable": app.stat().st_size}, "sha256": {"portable": app_hash},
        "release_notes": ["See the GitHub Release notes for changes in this version."]}
    if setup.is_file(): metadata["download"]["installer"] = setup.name; metadata["size"]["installer"] = setup.stat().st_size; metadata["sha256"]["installer"] = digest(setup)
    (dist / "release.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__": raise SystemExit(main())
