from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .browser_profiles import BrowserProfile
from .browser_scanner import DiscoveredBrowserProfile
from .config import AppConfig, save_config
from .constants import WORK_PROFILE_ID
from .profile_health import validate_profile_assignment


def should_run_setup(config: AppConfig, config_existed: bool = True) -> bool:
    if not config_existed or not config.setup.completed: return True
    assigned = {website.browser_profile for website in config.websites}
    return not any(key in config.browser_profiles and config.browser_profiles[key].type != "system" for key in assigned)


def detected_profile_exists(config: AppConfig, detected: DiscoveredBrowserProfile) -> bool:
    def norm(value: str) -> str: return str(Path(value)).casefold() if value else ""
    return any(profile.type == detected.browser_type and norm(profile.executable_path) == norm(detected.executable_path)
               and norm(profile.user_data_dir) == norm(detected.user_data_dir)
               and profile.profile_directory.casefold() == detected.profile_directory.casefold()
               for profile in config.browser_profiles.values())


def unique_profile_id(config: AppConfig, detected: DiscoveredBrowserProfile) -> str:
    base = "-".join(detected.profile_display_name.lower().split()) or f"{detected.browser_type}-profile"
    base = "".join(character for character in base if character.isalnum() or character == "-").strip("-") or "browser-profile"
    candidate = base; number = 2
    while candidate in config.browser_profiles: candidate = f"{base}-{number}"; number += 1
    return candidate


def import_detected_profile(config: AppConfig, detected: DiscoveredBrowserProfile) -> str:
    if detected_profile_exists(config, detected):
        return next(key for key, value in config.browser_profiles.items()
                    if value.type == detected.browser_type and Path(value.executable_path) == Path(detected.executable_path)
                    and Path(value.user_data_dir) == Path(detected.user_data_dir)
                    and value.profile_directory.casefold() == detected.profile_directory.casefold())
    key = unique_profile_id(config, detected)
    config.browser_profiles[key] = BrowserProfile(detected.profile_display_name, detected.browser_type,
        detected.executable_path, detected.user_data_dir, detected.profile_directory, False,
        {"source": "automatic", "last_scanned": datetime.now().isoformat(timespec="seconds")})
    return key


def remap_detected_profile(config: AppConfig, profile_id: str, detected: DiscoveredBrowserProfile) -> str:
    if profile_id not in config.browser_profiles:
        raise ValueError(f"Unknown logical browser profile: {profile_id}")
    existing = config.browser_profiles[profile_id]
    config.browser_profiles[profile_id] = BrowserProfile(existing.name.replace(" (configure during setup)", ""), detected.browser_type,
        detected.executable_path, detected.user_data_dir, detected.profile_directory, existing.fallback_to_system_browser,
        {"source": "automatic", "last_scanned": datetime.now().isoformat(timespec="seconds")}, existing.extra)
    validate_profile_assignment(config, profile_id)
    return profile_id


def configure_setup_profile(config: AppConfig, detected: DiscoveredBrowserProfile) -> str:
    if WORK_PROFILE_ID in config.browser_profiles and any(site.browser_profile == WORK_PROFILE_ID for site in config.websites):
        return remap_detected_profile(config, WORK_PROFILE_ID, detected)
    return import_detected_profile(config, detected)


def assign_all_websites(config: AppConfig, profile_id: str) -> None:
    if profile_id not in config.browser_profiles: raise ValueError(f"Unknown browser profile: {profile_id}")
    for website in config.websites: website.browser_profile = profile_id


def assign_websites(config: AppConfig, assignments: dict[int, str]) -> None:
    for index, profile_id in assignments.items():
        if profile_id not in config.browser_profiles: raise ValueError(f"Unknown browser profile: {profile_id}")
        config.websites[index].browser_profile = profile_id


def complete_setup(path: Path, config: AppConfig) -> None:
    config.setup.completed = True; save_config(path, config)


def cancel_setup(path: Path, config: AppConfig) -> None:
    # Cancellation remains explicit, but uses the safe system browser for this session/configuration.
    for website in config.websites: website.browser_profile = "system-default"
    config.setup.completed = False; save_config(path, config)
