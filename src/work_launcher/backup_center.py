from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from .config import AppConfig, config_to_dict, validate_config_data


def create_backup(config: AppConfig, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(config_to_dict(config), indent=2) + "\n", encoding="utf-8")
    return destination


def automatic_backup(config_path: Path, backup_dir: Path, keep: int = 10) -> Path | None:
    if not config_path.is_file():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"config-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    shutil.copy2(config_path, target)
    for old in sorted(backup_dir.glob("config-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]:
        old.unlink()
    return target


def inspect_backup(path: Path) -> tuple[AppConfig, str]:
    config = validate_config_data(json.loads(path.read_text(encoding="utf-8")))
    summary = (f"{len(config.websites)} websites, {len(config.applications)} applications, "
               f"{len(config.presets)} presets, {len(config.schedules)} schedules")
    return config, summary
