from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .constants import APP_FILENAME


def get_log_dir() -> Path:
    local = Path.home() / "AppData" / "Local"
    return local / APP_FILENAME / "logs"


def configure_logging() -> Path:
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "work_launcher.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = RotatingFileHandler(log_path, maxBytes=512_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    root.addHandler(handler)
    return log_path

