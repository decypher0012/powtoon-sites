from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .browser_profiles import validate_profile
from .config import AppConfig, PresetConfig
from .workspace_launcher import network_available


@dataclass(frozen=True)
class ReadinessItem:
    name: str
    ready: bool
    detail: str


def preset_readiness(
    config: AppConfig,
    preset: PresetConfig,
    network_check: Callable[[], bool] = network_available,
) -> list[ReadinessItem]:
    websites = {item.name: item for item in config.websites}
    applications = {item.name: item for item in config.applications}
    needs_network = any(
        reference.startswith("website:") or preset.item_rules.get(reference, {}).get("require_network")
        for reference in preset.items
    )
    network_ready = not needs_network or network_check()
    rows = [ReadinessItem("Network", network_ready,
                          "Available" if network_ready else "Required but unavailable")]
    checked_profiles: set[str] = set()
    for reference in preset.items:
        kind, name = reference.split(":", 1)
        if kind == "application":
            app = applications.get(name)
            ready = bool(app and app.enabled and Path(app.path).expanduser().is_file())
            rows.append(ReadinessItem(name, ready, "Application is available" if ready else "Application is missing or disabled"))
        else:
            site = websites.get(name)
            if not site:
                rows.append(ReadinessItem(name, False, "Website is missing"))
                continue
            profile_id = site.browser_profile
            if profile_id in checked_profiles:
                continue
            checked_profiles.add(profile_id)
            profile = config.browser_profiles.get(profile_id)
            try:
                if profile:
                    validate_profile(profile, require_files=True)
                else:
                    raise ValueError("missing profile")
                rows.append(ReadinessItem(profile.name, True, "Browser profile is available"))
            except Exception:
                rows.append(ReadinessItem(profile.name if profile else profile_id, False, "Browser profile is unavailable"))
    return rows


def record_launch(config: AppConfig, key: str, now: datetime | None = None) -> None:
    now = now or datetime.now().astimezone()
    value = config.settings.launch_usage.setdefault(key, {"count": 0, "last": ""})
    value["count"] = int(value.get("count", 0)) + 1
    value["last"] = now.isoformat(timespec="seconds")


def recent_and_frequent(config: AppConfig, limit: int = 5) -> tuple[list[str], list[str]]:
    usage = config.settings.launch_usage
    recent = sorted(usage, key=lambda key: str(usage[key].get("last", "")), reverse=True)[:limit]
    frequent = sorted(usage, key=lambda key: (int(usage[key].get("count", 0)), str(usage[key].get("last", ""))),
                      reverse=True)[:limit]
    return recent, frequent


def preset_templates(config: AppConfig) -> list[PresetConfig]:
    websites = [f"website:{item.name}" for item in config.websites if item.enabled]
    applications = [f"application:{item.name}" for item in config.applications if item.enabled]
    first_sites = websites[:4]
    return [
        PresetConfig("Morning Setup", [*first_sites, *applications[:2]], focus_minutes=50, pinned=True),
        PresetConfig("Meeting Mode", websites[:2], focus_minutes=30),
        PresetConfig("Research", websites[:4], focus_minutes=45),
        PresetConfig("End of Day", applications[:2], run_mode="step"),
    ]


def resolve_chain(config: AppConfig, first: PresetConfig, maximum: int = 20) -> list[PresetConfig]:
    by_name = {preset.name: preset for preset in config.presets}
    result, seen, current = [], set(), first
    while current and len(result) < maximum:
        if current.name in seen:
            raise ValueError(f'Preset chain contains a cycle at "{current.name}".')
        result.append(current)
        seen.add(current.name)
        current = by_name.get(current.chain_next) if current.chain_next else None
    return result
