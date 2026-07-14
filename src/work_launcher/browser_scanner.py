from __future__ import annotations

import configparser
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event


@dataclass(frozen=True)
class DiscoveredBrowserProfile:
    browser_type: str
    browser_name: str
    executable_path: str
    user_data_dir: str
    profile_directory: str
    profile_display_name: str
    is_default: bool = False
    status: str = "Valid"


@dataclass
class BrowserScanResult:
    browser_type: str
    browser_name: str
    executable_path: str = ""
    profiles: list[DiscoveredBrowserProfile] = field(default_factory=list)
    warning: str = ""


BROWSERS = {
    "chrome": ("Google Chrome", "Google/Chrome/Application/chrome.exe", "Google/Chrome/User Data"),
    "edge": ("Microsoft Edge", "Microsoft/Edge/Application/msedge.exe", "Microsoft/Edge/User Data"),
    "brave": ("Brave", "BraveSoftware/Brave-Browser/Application/brave.exe", "BraveSoftware/Brave-Browser/User Data"),
    "chromium": ("Chromium", "Chromium/Application/chrome.exe", "Chromium/User Data"),
    "vivaldi": ("Vivaldi", "Vivaldi/Application/vivaldi.exe", "Vivaldi/User Data"),
}


def _registry_executable(browser_type: str, registry=None) -> Path | None:
    # Chromium and Chrome commonly register the same chrome.exe App Paths name.
    # Treating Chrome's registration as Chromium creates a false installation.
    if browser_type == "chromium": return None
    if registry is None:
        try: import winreg as registry
        except ImportError: return None
    exe_names = {"chrome": "chrome.exe", "edge": "msedge.exe", "brave": "brave.exe", "vivaldi": "vivaldi.exe", "firefox": "firefox.exe"}
    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_names[browser_type]}"
    for hive in (getattr(registry, "HKEY_CURRENT_USER", None), getattr(registry, "HKEY_LOCAL_MACHINE", None)):
        if hive is None: continue
        try:
            with registry.OpenKey(hive, key_path) as key:
                value, _ = registry.QueryValueEx(key, None); path = Path(value)
                if path.is_file(): return path
        except (OSError, PermissionError): pass
    return None


def find_browser_executable(browser_type: str, env=None, registry=None, custom_path: str = "") -> Path | None:
    if custom_path:
        path = Path(custom_path); return path if path.is_file() else None
    env = os.environ if env is None else env
    if browser_type == "firefox": relative = "Mozilla Firefox/firefox.exe"
    else: relative = BROWSERS[browser_type][1]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if env.get(variable):
            candidate = Path(env[variable]) / Path(relative)
            try:
                if candidate.is_file(): return candidate
            except (OSError, PermissionError):
                logging.warning("Permission denied while checking a standard browser installation location")
    return _registry_executable(browser_type, registry)


def _friendly_names(user_data: Path) -> tuple[dict[str, str], str]:
    state = user_data / "Local State"
    if not state.is_file(): return {}, ""
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
        cache = data.get("profile", {}).get("info_cache", {})
        return {key: value.get("name", key) for key, value in cache.items() if isinstance(value, dict)}, data.get("profile", {}).get("last_used", "")
    except (OSError, PermissionError, json.JSONDecodeError, UnicodeError) as exc:
        logging.warning("Could not read non-sensitive browser profile metadata: %s", exc); return {}, ""


def scan_chromium_profiles(browser_type: str, executable: Path, env=None) -> list[DiscoveredBrowserProfile]:
    env = os.environ if env is None else env; local = env.get("LOCALAPPDATA")
    if not local: return []
    name, _, data_relative = BROWSERS[browser_type]; user_data = Path(local) / Path(data_relative)
    if not user_data.is_dir(): return []
    friendly, default_dir = _friendly_names(user_data); profiles = []
    try: children = list(user_data.iterdir())
    except (OSError, PermissionError): return []
    for folder in children:
        if not folder.is_dir() or not (folder.name == "Default" or folder.name == "Guest Profile" or (folder.name.startswith("Profile ") and folder.name[8:].isdigit())): continue
        # Preferences is only checked for existence; it is never opened.
        if not ((folder / "Preferences").is_file() or (folder / "Secure Preferences").is_file()): continue
        profiles.append(DiscoveredBrowserProfile(browser_type, name, str(executable), str(user_data), folder.name,
                                                 friendly.get(folder.name, folder.name), folder.name == default_dir or (not default_dir and folder.name == "Default")))
    return profiles


def scan_firefox_profiles(executable: Path, env=None) -> list[DiscoveredBrowserProfile]:
    env = os.environ if env is None else env; roaming = env.get("APPDATA")
    if not roaming: return []
    firefox_dir = Path(roaming) / "Mozilla" / "Firefox"; ini = firefox_dir / "profiles.ini"
    if not ini.is_file(): return []
    parser = configparser.ConfigParser()
    try: parser.read(ini, encoding="utf-8")
    except (OSError, PermissionError, configparser.Error, UnicodeError): return []
    profiles = []
    for section in parser.sections():
        if not section.lower().startswith("profile"): continue
        profile_name = parser.get(section, "Name", fallback=section)
        raw_path = parser.get(section, "Path", fallback="")
        relative = parser.getboolean(section, "IsRelative", fallback=True)
        path = firefox_dir / raw_path if relative else Path(raw_path)
        if path.is_dir():
            profiles.append(DiscoveredBrowserProfile("firefox", "Mozilla Firefox", str(executable), str(path.parent),
                profile_name, profile_name, parser.getboolean(section, "Default", fallback=False)))
    return profiles


def scan_browsers(env=None, registry=None, cancel_event: Event | None = None) -> list[BrowserScanResult]:
    env = os.environ if env is None else env; results = []
    for browser_type, (name, _, _) in BROWSERS.items():
        if cancel_event and cancel_event.is_set(): break
        try:
            executable = find_browser_executable(browser_type, env, registry)
            profiles = scan_chromium_profiles(browser_type, executable, env) if executable else []
            results.append(BrowserScanResult(browser_type, name, str(executable or ""), profiles, "" if executable else "Not found"))
        except (OSError, PermissionError) as exc: results.append(BrowserScanResult(browser_type, name, warning=f"Scan unavailable: {exc}"))
    if not cancel_event or not cancel_event.is_set():
        executable = find_browser_executable("firefox", env, registry)
        profiles = scan_firefox_profiles(executable, env) if executable else []
        results.append(BrowserScanResult("firefox", "Mozilla Firefox", str(executable or ""), profiles, "" if executable else "Not found"))
    return results
