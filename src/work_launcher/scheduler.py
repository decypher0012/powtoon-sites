from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .config import ScheduleConfig


@dataclass
class ScheduleState:
    last_run_key: str = ""


def due_schedules(schedules: list[ScheduleConfig], state: dict[str, ScheduleState],
                  now: datetime | None = None, network_ok: bool = True) -> list[ScheduleConfig]:
    now = now or datetime.now()
    clock = now.strftime("%H:%M")
    date_key = now.strftime("%Y-%m-%d")
    due = []
    for schedule in schedules:
        schedule_state = state.setdefault(schedule.name, ScheduleState())
        if schedule.last_run_date and not schedule_state.last_run_key:
            schedule_state.last_run_key = schedule.last_run_date
        if (schedule.enabled and now.weekday() in schedule.weekdays and schedule.time == clock
                and schedule_state.last_run_key != date_key and (network_ok or not schedule.require_network)):
            schedule_state.last_run_key = date_key
            schedule.last_run_date = date_key
            due.append(schedule)
    return due
