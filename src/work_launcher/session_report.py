from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .workspace_launcher import WorkspaceLaunchResult


@dataclass(frozen=True)
class LaunchSession:
    preset: str
    started_at: str
    finished_at: str
    results: tuple[WorkspaceLaunchResult, ...]


def reports_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "WorkLauncher" / "Reports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_session(preset: str, started: datetime, results: list[WorkspaceLaunchResult]) -> LaunchSession:
    return LaunchSession(preset, started.astimezone(timezone.utc).isoformat(timespec="seconds"),
                         datetime.now(timezone.utc).isoformat(timespec="seconds"), tuple(results))


def save_session(session: LaunchSession, root: Path | None = None, keep: int = 50) -> Path:
    root = root or reports_dir()
    root.mkdir(parents=True, exist_ok=True)
    stamp = session.started_at.replace(":", "").replace("+", "-")
    path = root / f"session-{stamp}.json"
    path.write_text(json.dumps(asdict(session), indent=2) + "\n", encoding="utf-8")
    for old in sorted(root.glob("session-*.json"), key=lambda value: value.stat().st_mtime, reverse=True)[keep:]:
        old.unlink(missing_ok=True)
    return path
