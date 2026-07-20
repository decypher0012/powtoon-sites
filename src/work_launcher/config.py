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
    DEFAULT_VISUAL_STYLE,
    DEFAULT_WEBSITES,
    DEFAULT_BROWSER_PROFILES, CONFIG_VERSION, WORK_PROFILE_ID,
    UPDATE_GITHUB_OWNER, UPDATE_GITHUB_REPOSITORY, VISUAL_STYLES,
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
class ApplicationConfig:
    name: str
    path: str
    arguments: list[str] = field(default_factory=list)
    working_directory: str = ""
    enabled: bool = True
    launch_group: str = ""
    only_if_not_running: bool = False
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class PresetConfig:
    name: str
    items: list[str] = field(default_factory=list)
    launch_delay_seconds: float | None = None
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ScheduleConfig:
    name: str
    preset: str
    time: str
    weekdays: list[int] = field(default_factory=lambda: list(range(5)))
    enabled: bool = True
    confirm_seconds: int = 10
    require_network: bool = False
    last_run_date: str = ""
    extra: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AppSettings:
    launch_delay_seconds: float = DEFAULT_LAUNCH_DELAY_SECONDS
    duplicate_launch_cooldown_seconds: float = DEFAULT_DUPLICATE_LAUNCH_COOLDOWN_SECONDS
    theme: str = DEFAULT_THEME
    visual_style: str = DEFAULT_VISUAL_STYLE
    remember_window_position: bool = True
    minimize_to_tray: bool = False
    launch_with_windows: bool = False
    window_width: int = 1080
    window_height: int = 760
    window_x: int | None = None
    window_y: int | None = None
    window_maximized: bool = False
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
    applications: list[ApplicationConfig] = field(default_factory=list)
    presets: list[PresetConfig] = field(default_factory=list)
    schedules: list[ScheduleConfig] = field(default_factory=list)
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
    websites = [WebsiteConfig(**item) for item in DEFAULT_WEBSITES]
    return AppConfig(
        settings=AppSettings(),
        browser_profiles={key: BrowserProfile(**value) for key, value in DEFAULT_BROWSER_PROFILES.items()},
        websites=websites,
        presets=[],
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
    if settings.visual_style not in VISUAL_STYLES:
        raise ConfigError(f"settings.visual_style must be one of: {', '.join(VISUAL_STYLES)}")
    if not isinstance(settings.launch_delay_seconds,(int,float)) or isinstance(settings.launch_delay_seconds,bool): raise ConfigError("settings.launch_delay_seconds must be numeric")
    if not isinstance(settings.duplicate_launch_cooldown_seconds,(int,float)) or isinstance(settings.duplicate_launch_cooldown_seconds,bool): raise ConfigError("settings.duplicate_launch_cooldown_seconds must be numeric")
    if settings.launch_delay_seconds < 0:
        raise ConfigError("settings.launch_delay_seconds must be >= 0")
    if settings.duplicate_launch_cooldown_seconds < 0:
        raise ConfigError("settings.duplicate_launch_cooldown_seconds must be >= 0")
    for name in ("remember_window_position", "minimize_to_tray", "launch_with_windows", "window_maximized"):
        if type(getattr(settings, name)) is not bool:
            raise ConfigError(f"settings.{name} must be true or false")
    for name in ("window_width", "window_height"):
        value = getattr(settings, name)
        if type(value) is not int or not 320 <= value <= 10000:
            raise ConfigError(f"settings.{name} must be an integer between 320 and 10000")
    for name in ("window_x", "window_y"):
        value = getattr(settings, name)
        if value is not None and type(value) is not int:
            raise ConfigError(f"settings.{name} must be an integer or null")
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
        enabled = item.get("enabled", True)
        selected = item.get("selected", False)
        if type(enabled) is not bool or type(selected) is not bool:
            raise ConfigError(f"website enabled/selected values must be true or false for {name}")
        websites.append(
            WebsiteConfig(
                name=name.strip(),
                url=url.strip(),
                enabled=enabled,
                selected=selected,
                browser_profile=str(item.get("browser_profile", WORK_PROFILE_ID)),
                launch_group=str(item.get("launch_group", "")).strip(),
                extra={key:value for key,value in item.items() if key not in WebsiteConfig.__dataclass_fields__},
            )
        )
    return websites


def _parse_applications(items: Any) -> list[ApplicationConfig]:
    if not isinstance(items, list):
        raise ConfigError("applications must be a list")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ConfigError("each application must be an object")
        name, path = item.get("name"), item.get("path")
        arguments = item.get("arguments", [])
        if not isinstance(name, str) or not name.strip() or not isinstance(path, str) or not path.strip():
            raise ConfigError("application name and path must be non-empty text")
        if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
            raise ConfigError(f"application.arguments must be a list of strings for {name}")
        for boolean_name in ("enabled", "only_if_not_running"):
            if type(item.get(boolean_name, boolean_name == "enabled")) is not bool:
                raise ConfigError(f"application.{boolean_name} must be true or false for {name}")
        result.append(ApplicationConfig(
            name=name.strip(), path=path.strip(), arguments=arguments,
            working_directory=str(item.get("working_directory", "")).strip(),
            enabled=item.get("enabled", True),
            launch_group=str(item.get("launch_group", "")).strip(),
            only_if_not_running=item.get("only_if_not_running", False),
            extra={key: value for key, value in item.items() if key not in ApplicationConfig.__dataclass_fields__},
        ))
    return result


def _parse_presets(items: Any, websites: list[WebsiteConfig], applications: list[ApplicationConfig]) -> list[PresetConfig]:
    if not isinstance(items, list):
        raise ConfigError("presets must be a list")
    valid = {f"website:{item.name}" for item in websites} | {f"application:{item.name}" for item in applications}
    result = []
    names = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ConfigError("each preset must have a non-empty name")
        name = item["name"].strip()
        if name.casefold() in names:
            raise ConfigError(f"duplicate preset name: {name}")
        names.add(name.casefold())
        references = item.get("items", [])
        if not isinstance(references, list) or not all(isinstance(value, str) for value in references):
            raise ConfigError(f"preset.items must be a list of strings for {name}")
        missing = [value for value in references if value not in valid]
        if missing:
            raise ConfigError(f"preset {name} references missing items: {', '.join(missing)}")
        delay = item.get("launch_delay_seconds")
        if delay is not None and (not isinstance(delay, (int, float)) or isinstance(delay, bool) or delay < 0):
            raise ConfigError(f"preset.launch_delay_seconds must be non-negative or null for {name}")
        result.append(PresetConfig(name, references, delay,
            {key: value for key, value in item.items() if key not in PresetConfig.__dataclass_fields__}))
    return result


def _parse_schedules(items: Any, presets: list[PresetConfig]) -> list[ScheduleConfig]:
    if not isinstance(items, list):
        raise ConfigError("schedules must be a list")
    preset_names = {item.name for item in presets}
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ConfigError("each schedule must be an object")
        name, preset, clock = item.get("name"), item.get("preset"), item.get("time")
        if not all(isinstance(value, str) and value.strip() for value in (name, preset, clock)):
            raise ConfigError("schedule name, preset, and time must be non-empty text")
        if preset not in preset_names:
            raise ConfigError(f"schedule {name} references missing preset: {preset}")
        try:
            hour, minute = (int(value) for value in clock.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError
        except (ValueError, AttributeError):
            raise ConfigError(f"schedule.time must be HH:MM for {name}") from None
        weekdays = item.get("weekdays", list(range(5)))
        if not isinstance(weekdays, list) or not weekdays or any(type(day) is not int or day not in range(7) for day in weekdays):
            raise ConfigError(f"schedule.weekdays must contain weekday numbers 0-6 for {name}")
        for boolean_name in ("enabled", "require_network"):
            if type(item.get(boolean_name, boolean_name == "enabled")) is not bool:
                raise ConfigError(f"schedule.{boolean_name} must be true or false for {name}")
        confirm = item.get("confirm_seconds", 10)
        if type(confirm) is not int or not 0 <= confirm <= 300:
            raise ConfigError(f"schedule.confirm_seconds must be between 0 and 300 for {name}")
        last_run_date = item.get("last_run_date", "")
        if not isinstance(last_run_date, str):
            raise ConfigError(f"schedule.last_run_date must be text for {name}")
        result.append(ScheduleConfig(name.strip(), preset, clock, weekdays, item.get("enabled", True),
            confirm, item.get("require_network", False), last_run_date,
            {key: value for key, value in item.items() if key not in ScheduleConfig.__dataclass_fields__}))
    return result


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    def serialized(value):
        data={name:getattr(value,name) for name in value.__dataclass_fields__ if name!="extra"}
        return {**value.extra,**data}
    result={
        "config_version": config.config_version,
        "settings": serialized(config.settings),
        "browser_profiles": {key: serialized(value) for key, value in config.browser_profiles.items()},
        "websites": [serialized(item) for item in config.websites],
        "applications": [serialized(item) for item in config.applications],
        "presets": [serialized(item) for item in config.presets],
        "schedules": [serialized(item) for item in config.schedules],
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
    applications = _parse_applications(data.get("applications", []))
    presets = _parse_presets(data.get("presets", []), websites, applications)
    schedules = _parse_schedules(data.get("schedules", []), presets)
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
    if config_version > CONFIG_VERSION:
        raise ConfigError(f"Configuration version {config_version} is newer than this application supports")
    return AppConfig(config_version=config_version, settings=settings,
                     browser_profiles=profiles,websites=websites,applications=applications,presets=presets,schedules=schedules,
                     setup=setup,updates=updates,
                     extra={key:value for key,value in data.items() if key not in {"config_version","settings","browser_profiles","websites","applications","presets","schedules","setup","updates"}})


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
            migrated.setdefault("applications", [])
            migrated.setdefault("presets", [{
                "name": "All Work Apps",
                "items": [f"website:{item.get('name', '')}" for item in migrated.get("websites", []) if item.get("name")],
            }])
            migrated.setdefault("schedules", [])
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
