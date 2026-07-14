from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .config import AppConfig, ConfigError, WebsiteConfig, config_to_dict, save_config, validate_config_data


class WebsiteValidationError(ConfigError):
    pass


def validate_website(website: WebsiteConfig, config: AppConfig, editing_index: int | None = None) -> list[str]:
    if not website.name.strip():
        raise WebsiteValidationError("Display Name is required.")
    # Reuse the complete configuration parser for URL/profile validation.
    probe = copy.deepcopy(config)
    if editing_index is None:
        probe.websites.append(website)
    else:
        probe.websites[editing_index] = website
    validate_config_data(config_to_dict(probe))
    warnings: list[str] = []
    others = [site for index, site in enumerate(config.websites) if index != editing_index]
    if any(site.name.casefold() == website.name.casefold() for site in others):
        warnings.append(f'A website named "{website.name}" already exists.')
    if any(site.url == website.url for site in others):
        warnings.append("Another website uses this URL. Duplicate URLs are allowed.")
    return warnings


def add_website(config: AppConfig, website: WebsiteConfig) -> list[str]:
    warnings = validate_website(website, config)
    config.websites.append(website)
    return warnings


def edit_website(config: AppConfig, index: int, website: WebsiteConfig) -> list[str]:
    warnings = validate_website(website, config, index)
    config.websites[index] = website
    return warnings


def duplicate_website(config: AppConfig, index: int) -> WebsiteConfig:
    duplicate = copy.deepcopy(config.websites[index])
    base = f"{duplicate.name} (Copy)"
    duplicate.name = base
    number = 2
    names = {site.name.casefold() for site in config.websites}
    while duplicate.name.casefold() in names:
        duplicate.name = f"{base} {number}"; number += 1
    config.websites.insert(index + 1, duplicate)
    return duplicate


def delete_websites(config: AppConfig, indices: Iterable[int]) -> list[WebsiteConfig]:
    selected = sorted(set(indices))
    removed = [copy.deepcopy(config.websites[index]) for index in selected]
    for index in reversed(selected):
        del config.websites[index]
    return removed


def move_websites(config: AppConfig, indices: Iterable[int], direction: int) -> list[int]:
    selected = sorted(set(indices))
    if not selected or direction not in {-1, 1}:
        return selected
    if direction < 0 and selected[0] == 0 or direction > 0 and selected[-1] == len(config.websites) - 1:
        return selected
    block = [config.websites[index] for index in selected]
    remaining = [site for index, site in enumerate(config.websites) if index not in selected]
    insertion = selected[0] + direction
    config.websites = remaining[:insertion] + block + remaining[insertion:]
    return list(range(insertion, insertion + len(block)))


def bulk_update(config: AppConfig, indices: Iterable[int], *, enabled: bool | None = None,
                browser_profile: str | None = None) -> None:
    if browser_profile is not None and browser_profile not in config.browser_profiles:
        raise WebsiteValidationError(f"Unknown browser profile: {browser_profile}")
    for index in set(indices):
        if enabled is not None: config.websites[index].enabled = enabled
        if browser_profile is not None: config.websites[index].browser_profile = browser_profile


def search_websites(config: AppConfig, query: str) -> list[int]:
    needle = query.strip().casefold()
    if not needle: return list(range(len(config.websites)))
    result = []
    for index, site in enumerate(config.websites):
        profile = config.browser_profiles.get(site.browser_profile)
        haystack = " ".join((site.name, site.url, site.browser_profile, profile.name if profile else "")).casefold()
        if needle in haystack: result.append(index)
    return result


def websites_for_group(config: AppConfig, group: str) -> list[WebsiteConfig]:
    return [site for site in config.websites if site.enabled and (group == "All Websites" or site.launch_group == group)]


def create_timestamped_backup(path: Path, keep: int = 10, now: datetime | None = None) -> Path | None:
    if not path.exists(): return None
    now = now or datetime.now()
    backup = path.with_name(f"config-{now:%Y-%m-%d-%H%M%S-%f}.json")
    backup.write_bytes(path.read_bytes())
    backups = sorted(path.parent.glob("config-????-??-??-??????-??????.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old in backups[keep:]: old.unlink()
    return backup


def export_json(path: Path, config: AppConfig, entire_config: bool) -> None:
    data = config_to_dict(config) if entire_config else {"websites": [vars(site) for site in config.websites]}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def preview_import(path: Path, config: AppConfig) -> list[WebsiteConfig]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list): data = {"websites": data}
    if not isinstance(data, dict) or not isinstance(data.get("websites"), list):
        raise WebsiteValidationError("Import JSON must contain a websites list.")
    probe = config_to_dict(config); probe["websites"] = data["websites"]
    return validate_config_data(probe).websites


def import_websites(config: AppConfig, incoming: list[WebsiteConfig], *, replace: bool = False,
                    skip_duplicate_names: bool = False, skip_duplicate_urls: bool = False) -> int:
    target = [] if replace else list(config.websites)
    added = 0
    for website in incoming:
        if skip_duplicate_names and any(site.name.casefold() == website.name.casefold() for site in target): continue
        if skip_duplicate_urls and any(site.url == website.url for site in target): continue
        validate_website(website, AppConfig(config.config_version, config.settings, config.browser_profiles, target))
        target.append(copy.deepcopy(website)); added += 1
    config.websites = target
    return added


class UndoHistory:
    def __init__(self): self._items: list[list[WebsiteConfig]] = []
    def remember(self, config: AppConfig) -> None: self._items.append(copy.deepcopy(config.websites))
    def undo(self, config: AppConfig) -> bool:
        if not self._items: return False
        config.websites = self._items.pop(); return True
