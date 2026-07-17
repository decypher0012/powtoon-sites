from __future__ import annotations

import json
import shutil
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .constants import (
    APP_FILENAME,
    CONFIG_FILENAME,
    DEFAULT_DUPLICATE_LAUNCH_COOLDOWN_SECONDS,
    DEFAULT_LAUNCH_DELAY_SECONDS,
    DEFAULT_THEME,
    DEFAULT_WEBSITES,
    DEFAULT_BROWSER_PROFILES, CONFIG_VERSION, WORK_PROFILE_ID,
    UPDATE_GITHUB_OWNER, UPDATE_GITHUB_REPOSITORY,
)
from .browser_profiles import BrowserProfile, BrowserProfileError, validate_profile


@dataclass
class WebsiteConfig:
    name: str
    url: str
    enabled: bool = True
    selected: bool = True
    browser_profile: str = WORK_PROFILE_ID
    launch_group: str = ""
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AppSettings:
    launch_delay_seconds: float = DEFAULT_LAUNCH_DELAY_SECONDS
    duplicate_launch_cooldown_seconds: float = DEFAULT_DUPLICATE_LAUNCH_COOLDOWN_SECONDS
    theme: str = DEFAULT_THEME
    remember_window_position: bool = True
    minimize_to_tray: bool = False
    launch_with_windows: bool = False
    window_width: int = 760
    window_height: int = 640
    window_x: int | None = None
    window_y: int | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class SetupConfig:
    completed: bool = False
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class UpdateConfig:
    provider: str = "github"
    owner: str = UPDATE_GITHUB_OWNER
    repository: str = UPDATE_GITHUB_REPOSITORY
    channel: str = "stable"
    policy: str = "notify"
    automatically_check: bool = True
    automatically_download: bool = False
    last_checked: str = ""
    skipped_version: str = ""
    installation_kind: str = "portable"
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AppConfig:
    config_version: int = CONFIG_VERSION
    settings: AppSettings = field(default_factory=AppSettings)
    browser_profiles: dict[str, BrowserProfile] = field(default_factory=dict)
    websites: list[WebsiteConfig] = field(default_factory=list)
    setup: SetupConfig = field(default_factory=SetupConfig)
    updates: UpdateConfig = field(default_factory=UpdateConfig)
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


class ConfigError(ValueError):
    pass


def get_config_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_FILENAME


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILENAME


def default_config() -> AppConfig:
    return AppConfig(
        settings=AppSettings(),
        browser_profiles={key: BrowserProfile(**value) for key, value in DEFAULT_BROWSER_PROFILES.items()},
        websites=[WebsiteConfig(**item) for item in DEFAULT_WEBSITES],
        setup=SetupConfig(completed=False),
        updates=UpdateConfig(),
    )


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError(f"Unsupported or invalid URL: {url}")


def _parse_settings(data: dict[str, Any]) -> AppSettings:
    if not isinstance(data,dict): raise ConfigError("settings must be an object")
    settings = AppSettings()
    known=set(AppSettings.__dataclass_fields__)-{"extra"}
    for field_name in known:
        if field_name in data:
            setattr(settings, field_name, data[field_name])
    settings.extra={key:value for key,value in data.items() if key not in known}
    if settings.theme not in {"system", "light", "dark"}:
        raise ConfigError("settings.theme must be one of: system, light, dark")
    if not isinstance(settings.launch_delay_seconds,(int,float)) or isinstance(settings.launch_delay_seconds,bool): raise ConfigError("settings.launch_delay_seconds must be numeric")
    if not isinstance(settings.duplicate_launch_cooldown_seconds,(int,float)) or isinstance(settings.duplicate_launch_cooldown_seconds,bool): raise ConfigError("settings.duplicate_launch_cooldown_seconds must be numeric")
    if settings.launch_delay_seconds < 0:
        raise ConfigError("settings.launch_delay_seconds must be >= 0")
    if settings.duplicate_launch_cooldown_seconds < 0:
        raise ConfigError("settings.duplicate_launch_cooldown_seconds must be >= 0")
    return settings


def _parse_websites(items: Any) -> list[WebsiteConfig]:
    if not isinstance(items, list):
        raise ConfigError("websites must be a list")
    websites: list[WebsiteConfig] = []
    for item in items:
        if not isinstance(item, dict):
            raise ConfigError("each website must be an object")
        name = item.get("name")
        url = item.get("url")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("website.name must be a non-empty string")
        if not isinstance(url, str):
            raise ConfigError(f"website.url must be a string for {name}")
        _validate_url(url)
        websites.append(
            WebsiteConfig(
                name=name.strip(),
                url=url.strip(),
                enabled=bool(item.get("enabled", True)),
                selected=bool(item.get("selected", False)),
                browser_profile=str(item.get("browser_profile", WORK_PROFILE_ID)),
                launch_group=str(item.get("launch_group", "")).strip(),
                extra={key:value for key,value in item.items() if key not in WebsiteConfig.__dataclass_fields__},
            )
        )
    return websites


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    def serialized(value):
        data={name:getattr(value,name) for name in value.__dataclass_fields__ if name!="extra"}
        return {**value.extra,**data}
    result={
        "config_version": config.config_version,
        "settings": serialized(config.settings),
        "browser_profiles": {key: serialized(value) for key, value in config.browser_profiles.items()},
        "websites": [serialized(item) for item in config.websites],
        "setup": serialized(config.setup),
        "updates": serialized(config.updates),
    }
    return {**config.extra,**result}


def validate_config_data(data: Any) -> AppConfig:
    if not isinstance(data, dict):
        raise ConfigError("Configuration root must be an object")
    settings = _parse_settings(data.get("settings", {}))
    raw_profiles = data.get("browser_profiles", DEFAULT_BROWSER_PROFILES)
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ConfigError("browser_profiles must be a non-empty object")
    profiles: dict[str, BrowserProfile] = {}
    for key, item in raw_profiles.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(item, dict):
            raise ConfigError("Each browser profile must have a non-empty ID and object value")
        try:
            known=set(BrowserProfile.__dataclass_fields__)-{"extra"}
            profiles[key] = BrowserProfile(**{name:item[name] for name in known if name in item},extra={name:value for name,value in item.items() if name not in known})
            validate_profile(profiles[key], require_files=False)
        except (TypeError, BrowserProfileError) as exc:
            raise ConfigError(f"Invalid browser profile {key}: {exc}") from exc
    websites = _parse_websites(data.get("websites", []))
    for website in websites:
        if website.browser_profile not in profiles:
            raise ConfigError(f"Website {website.name} references missing browser profile: {website.browser_profile}")
    setup_data = data.get("setup", {})
    if not isinstance(setup_data,dict) or type(setup_data.get("completed",False)) is not bool: raise ConfigError("setup.completed must be true or false")
    setup = SetupConfig(completed=setup_data.get("completed",False),extra={key:value for key,value in setup_data.items() if key!="completed"})
    updates_data = data.get("updates", {})
    updates = UpdateConfig()
    if isinstance(updates_data, dict):
        known_updates=set(UpdateConfig.__dataclass_fields__)-{"extra"}
        for field_name in known_updates:
            if field_name in updates_data: setattr(updates, field_name, updates_data[field_name])
        updates.extra={key:value for key,value in updates_data.items() if key not in known_updates}
    else: raise ConfigError("updates must be an object")
    if updates.provider!="github" or not isinstance(updates.owner,str) or not isinstance(updates.repository,str): raise ConfigError("updates provider/owner/repository are invalid")
    # The release source is part of the application, not a user preference.
    # This also repairs older installations whose update fields were left blank.
    updates.owner = UPDATE_GITHUB_OWNER
    updates.repository = UPDATE_GITHUB_REPOSITORY
    if type(updates.automatically_check) is not bool or type(updates.automatically_download) is not bool: raise ConfigError("update automation settings must be true or false")
    if not isinstance(updates.last_checked,str) or not isinstance(updates.skipped_version,str): raise ConfigError("update status fields must be text")
    if updates.channel not in {"stable", "beta"}: raise ConfigError("updates.channel must be stable or beta")
    if updates.policy not in {"notify", "automatic", "manual"}: raise ConfigError("updates.policy must be notify, automatic, or manual")
    if updates.installation_kind not in {"portable", "installer"}: raise ConfigError("updates.installation_kind must be portable or installer")
    try: config_version=int(data.get("config_version",CONFIG_VERSION))
    except (TypeError,ValueError) as exc: raise ConfigError("config_version must be an integer") from exc
    return AppConfig(config_version=config_version, settings=settings,
                     browser_profiles=profiles,websites=websites,setup=setup,updates=updates,
                     extra={key:value for key,value in data.items() if key not in {"config_version","settings","browser_profiles","websites","setup","updates"}})


def write_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(config_to_dict(config), indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def backup_config(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)
    return backup


def load_config(path: Path | None = None) -> tuple[AppConfig, list[str]]:
    path = path or get_config_path()
    warnings: list[str] = []
    if not path.exists():
        config = default_config()
        write_config(path, config)
        warnings.append("Created default configuration.")
        return config, warnings
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigError("Configuration root must be an object")
        try: version=int(raw.get("config_version",1))
        except (TypeError,ValueError) as exc: raise ConfigError("config_version must be an integer") from exc
        if version < CONFIG_VERSION:
            migrated = dict(raw)
            migrated["config_version"] = CONFIG_VERSION
            migrated["browser_profiles"] = migrated.get("browser_profiles") or DEFAULT_BROWSER_PROFILES
            migrated["websites"] = [dict(site, browser_profile=site.get("browser_profile", WORK_PROFILE_ID))
                                    for site in migrated.get("websites", [])]
            # Existing installations have already selected profiles; do not force a wizard after upgrade.
            migrated["setup"] = migrated.get("setup") or {"completed": version >= 2}
            migrated["updates"] = migrated.get("updates") or config_to_dict(default_config())["updates"]
            config = validate_config_data(migrated)
            backup = backup_config(path)
            try:
                write_config(path, config)
            except OSError as exc:
                logging.error("Configuration migration failed; original retained: %s",type(exc).__name__)
                warnings.append("Configuration migration could not be saved; the original file was retained.")
                return config, warnings
            warnings.append(f"Configuration migrated to version {CONFIG_VERSION}.")
            if backup:
                warnings.append(f"Pre-migration configuration backed up to {backup.name}")
            logging.info("Configuration migration succeeded: version %s", CONFIG_VERSION)
            return config, warnings
        return validate_config_data(raw), warnings
    except (json.JSONDecodeError, ConfigError) as exc:
        backup = backup_config(path)
        default = default_config()
        write_config(path, default)
        warnings.append(f"Configuration repaired from invalid file: {exc}")
        if backup:
            warnings.append(f"Original configuration backed up to {backup.name}")
        return default, warnings


def save_config(path: Path, config: AppConfig) -> None:
    write_config(path, config)
