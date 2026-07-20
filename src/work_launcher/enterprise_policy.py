from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .config import AppConfig, ConfigError, WebsiteConfig


@dataclass(frozen=True)
class EnterprisePolicy:
    required_websites: tuple[WebsiteConfig, ...] = ()
    allowed_domains: tuple[str, ...] = ()
    allow_applications: bool = True
    locked_update_channel: str = ""


def default_policy_path() -> Path:
    root = Path(os.environ.get("PROGRAMDATA", Path.home() / "AppData" / "Local")) / "WorkLauncher"
    return root / "policy.json"


def load_policy(path: Path | None = None) -> EnterprisePolicy:
    path = path or default_policy_path()
    if not path.is_file():
        return EnterprisePolicy()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("Enterprise policy must contain an object")
    domains = data.get("allowed_domains", [])
    if not isinstance(domains, list) or not all(isinstance(value, str) and value for value in domains):
        raise ConfigError("policy.allowed_domains must be a list of host names")
    websites = []
    for item in data.get("required_websites", []):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("url"), str):
            raise ConfigError("policy.required_websites entries require name and url")
        websites.append(WebsiteConfig(item["name"], item["url"], browser_profile=item.get("browser_profile", "system-default")))
    channel = data.get("locked_update_channel", "")
    if channel not in {"", "stable", "beta"}:
        raise ConfigError("policy.locked_update_channel must be stable, beta, or empty")
    if type(data.get("allow_applications", True)) is not bool:
        raise ConfigError("policy.allow_applications must be true or false")
    return EnterprisePolicy(tuple(websites), tuple(value.casefold() for value in domains),
                            data.get("allow_applications", True), channel)


def apply_policy(config: AppConfig, policy: EnterprisePolicy) -> AppConfig:
    existing = {item.name.casefold() for item in config.websites}
    for website in policy.required_websites:
        if website.name.casefold() not in existing:
            config.websites.append(website)
    if policy.allowed_domains:
        invalid = [item.name for item in config.websites
                   if (urlparse(item.url).hostname or "").casefold() not in policy.allowed_domains]
        if invalid:
            raise ConfigError("Websites outside enterprise allowed domains: " + ", ".join(invalid))
    if not policy.allow_applications:
        config.applications.clear()
        for preset in config.presets:
            preset.items = [item for item in preset.items if not item.startswith("application:")]
    if policy.locked_update_channel:
        config.updates.channel = policy.locked_update_channel
    return config
