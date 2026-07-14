from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .config import AppConfig, WebsiteConfig, save_config
from .config import ConfigError


def set_website_enabled(config: AppConfig, name: str, enabled: bool) -> None:
    for website in config.websites:
        if website.name == name:
            website.enabled = enabled
            break


def set_website_order(config: AppConfig, ordered_names: list[str]) -> None:
    mapping = {w.name: w for w in config.websites}
    config.websites = [mapping[name] for name in ordered_names if name in mapping]


def update_selected(config: AppConfig, selected_names: set[str]) -> None:
    for website in config.websites:
        website.selected = website.name in selected_names


def reset_to_defaults() -> AppConfig:
    from .config import default_config

    return default_config()


def save_settings(path: Path, config: AppConfig) -> None:
    save_config(path, config)


def delete_browser_profile(config: AppConfig, profile_id: str) -> None:
    used = [website.name for website in config.websites if website.browser_profile == profile_id]
    if used:
        raise ConfigError("Cannot delete an in-use browser profile: " + ", ".join(used))
    if profile_id not in config.browser_profiles:
        raise ConfigError(f"Unknown browser profile: {profile_id}")
    del config.browser_profiles[profile_id]
