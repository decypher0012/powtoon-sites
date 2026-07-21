from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from .config import ScheduleConfig


def task_name(schedule: ScheduleConfig) -> str:
    digest = hashlib.sha256(schedule.name.encode("utf-8")).hexdigest()[:12]
    return f"WorkLauncher-{digest}"


def sync_tasks(schedules: list[ScheduleConfig], executable: Path, runner=subprocess.run) -> list[str]:
    """Create per-user wake-up tasks. In-app logic remains the source of truth and asks for confirmation."""
    errors = []
    for schedule in schedules:
        if not schedule.enabled:
            continue
        days = ",".join(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")[day] for day in schedule.weekdays)
        command = ["schtasks", "/Create", "/F", "/TN", task_name(schedule), "/SC", "WEEKLY",
                   "/D", days, "/ST", schedule.time, "/TR", f'"{executable}"']
        result = runner(command, capture_output=True, text=True, check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            errors.append(f"{schedule.name}: {(result.stderr or result.stdout).strip()}")
    return errors
