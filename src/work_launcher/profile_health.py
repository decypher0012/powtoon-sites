from __future__ import annotations

from dataclasses import dataclass

from .browser_profiles import BrowserProfile, validate_profile
from .config import AppConfig


@dataclass(frozen=True)
class ProfileHealth:
    profile_id: str
    available: bool
    reason: str
    referenced_websites: tuple[str, ...]


def get_profile_health(config: AppConfig, profile_id: str) -> ProfileHealth:
    profile = config.browser_profiles[profile_id]
    websites = tuple(site.name for site in config.websites if site.browser_profile == profile_id)
    try:
        validate_profile(profile, require_files=profile.type != "system")
        return ProfileHealth(profile_id, True, "Available", websites)
    except Exception as exc:
        return ProfileHealth(profile_id, False, str(exc), websites)


def profile_health_map(config: AppConfig) -> dict[str, ProfileHealth]:
    return {profile_id: get_profile_health(config, profile_id) for profile_id in config.browser_profiles}


def stale_profile_warning(config: AppConfig) -> str:
    unavailable = [health for health in profile_health_map(config).values() if not health.available]
    if not unavailable:
        return ""
    lines = []
    for health in unavailable:
        profile = config.browser_profiles[health.profile_id]
        if health.referenced_websites:
            lines.append(f"{profile.name} is unavailable and is assigned to {len(health.referenced_websites)} website(s): "
                         + ", ".join(health.referenced_websites))
        else:
            lines.append(f"{profile.name} is unavailable but is not assigned to any website.")
    return "\n".join(lines)


def validate_profile_assignment(config: AppConfig, profile_id: str) -> None:
    if profile_id not in config.browser_profiles:
        raise ValueError(f"Unknown browser profile: {profile_id}")
    profile = config.browser_profiles[profile_id]
    validate_profile(profile, require_files=profile.type != "system")
