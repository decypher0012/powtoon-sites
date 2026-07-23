from __future__ import annotations

import ctypes
import ctypes.wintypes
import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig, ApplicationConfig, PresetConfig, WebsiteConfig


@dataclass(frozen=True)
class CapturedWindow:
    title: str
    executable: str
    x: int
    y: int
    width: int
    height: int


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _protect(value: str, decrypt: bool = False) -> str:
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        return value
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buffer = ctypes.create_string_buffer(raw)
    source, target = _Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), _Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if decrypt:
        ok = function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target))
    else:
        ok = function(ctypes.byref(source), "Work Launcher", None, None, None, 0, ctypes.byref(target))
    if not ok: raise OSError("Windows could not protect the secret.")
    try:
        result = ctypes.string_at(target.data, target.size)
        return result.decode("utf-8") if decrypt else base64.b64encode(result).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


class SecretStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, str]:
        if not self.path.is_file(): return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {key: _protect(value, True) for key, value in raw.items()}

    def save(self, values: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({key: _protect(value) for key, value in values.items()}, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


def capture_windows() -> list[CapturedWindow]:
    if os.name != "nt" or not hasattr(ctypes, "windll"):
        return []
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    rows: list[CapturedWindow] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) <= 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return True
        try:
            size = ctypes.wintypes.DWORD(32768)
            path_buffer = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path_buffer, ctypes.byref(size)):
                rows.append(CapturedWindow(title_buffer.value, path_buffer.value, rect.left, rect.top,
                                           rect.right - rect.left, rect.bottom - rect.top))
        finally:
            kernel32.CloseHandle(handle)
        return True
    user32.EnumWindows(callback_type(visit), 0)
    return rows


def create_captured_preset(config: AppConfig, name: str, windows: list[CapturedWindow]) -> PresetConfig:
    references, layout = [], {}
    existing = {app.path.casefold(): app for app in config.applications}
    for window in windows:
        if Path(window.executable).name.casefold() == "worklauncher.exe":
            continue
        app = existing.get(window.executable.casefold())
        if not app:
            base = Path(window.executable).stem
            display = base
            suffix = 2
            names = {value.name.casefold() for value in config.applications}
            while display.casefold() in names:
                display = f"{base} {suffix}"; suffix += 1
            app = ApplicationConfig(display, window.executable, only_if_not_running=True)
            config.applications.append(app); existing[window.executable.casefold()] = app
        reference = f"application:{app.name}"
        if reference not in references:
            references.append(reference)
        layout[app.name] = {"x": window.x, "y": window.y, "width": window.width, "height": window.height}
    return PresetConfig(name=name, items=references, window_layout=layout, pinned=True)


def restore_window_layout(layout: dict[str, dict[str, int]], windows: list[CapturedWindow] | None = None) -> int:
    if os.name != "nt" or not hasattr(ctypes, "windll") or not layout:
        return 0
    user32, moved = ctypes.windll.user32, {"count": 0}
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd): return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1); user32.GetWindowTextW(hwnd, title, len(title))
        for name, rect in layout.items():
            if name.casefold() in title.value.casefold():
                user32.MoveWindow(hwnd, rect["x"], rect["y"], max(rect["width"], 100), max(rect["height"], 100), True)
                moved["count"] += 1; break
        return True
    user32.EnumWindows(callback_type(visit), 0)
    return moved["count"]


PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*)\}")


def substitute(value: str, parameters: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda match: parameters.get(match.group(1), match.group(0)), value)


def parameter_names(preset: PresetConfig) -> list[str]:
    names = [str(value.get("name", "")).strip() for value in preset.parameters]
    return list(dict.fromkeys(value for value in names if value))


def apply_parameters(config: AppConfig, preset: PresetConfig, values: dict[str, str]) -> tuple[AppConfig, PresetConfig]:
    import copy
    copied, result = copy.deepcopy(config), copy.deepcopy(preset)
    for site in copied.websites:
        site.url, site.name = substitute(site.url, values), substitute(site.name, values)
    for app in copied.applications:
        app.path = substitute(app.path, values)
        app.arguments = [substitute(value, values) for value in app.arguments]
        app.working_directory = substitute(app.working_directory, values)
    result.browser_session = [substitute(value, values) for value in result.browser_session]
    result.actions = [{key: substitute(value, values) if isinstance(value, str) else value
                       for key, value in action.items()} for action in result.actions]
    return copied, result


def import_browser_session(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("tabs", raw) if isinstance(raw, dict) else raw
    if not isinstance(entries, list): raise ValueError("Browser session must contain a tabs list.")
    urls = []
    for entry in entries:
        url = entry.get("url", "") if isinstance(entry, dict) else entry
        if isinstance(url, str) and url.startswith(("https://", "http://")): urls.append(url)
    return list(dict.fromkeys(urls))


def winget_missing(package_ids: list[str], runner: Callable = subprocess.run) -> list[str]:
    missing = []
    for package_id in package_ids:
        try:
            result = runner(["winget", "list", "--id", package_id, "--exact", "--disable-interactivity"],
                            capture_output=True, text=True, check=False)
        except OSError:
            return list(package_ids)
        if result.returncode != 0: missing.append(package_id)
    return missing


def install_winget(package_ids: list[str], runner: Callable = subprocess.run) -> list[str]:
    failed = []
    for package_id in package_ids:
        try:
            result = runner(["winget", "install", "--id", package_id, "--exact", "--interactive"],
                            check=False)
        except OSError:
            return list(package_ids)
        if result.returncode != 0: failed.append(package_id)
    return failed


ALLOWED_ACTIONS = {"open_uri", "terminal", "rdp", "command"}


def run_actions(actions: list[dict[str, Any]], popen: Callable = subprocess.Popen) -> list[str]:
    failures = []
    for action in actions:
        kind = action.get("type", "")
        try:
            if kind not in ALLOWED_ACTIONS: raise ValueError(f"Unsupported action type: {kind}")
            if kind == "open_uri":
                uri = str(action.get("uri", ""))
                if not uri.startswith(("https://", "http://", "ms-settings:", "ms-clock:")): raise ValueError("URI is not allowed")
                os.startfile(uri)
            elif kind == "terminal":
                popen(["wt.exe", *list(action.get("arguments", []))], shell=False)
            elif kind == "rdp":
                host = str(action.get("host", ""))
                if not re.fullmatch(r"[A-Za-z0-9.-]+", host): raise ValueError("Invalid RDP host")
                popen(["mstsc.exe", f"/v:{host}"], shell=False)
            else:
                executable = str(action.get("executable", ""))
                if not Path(executable).is_file(): raise FileNotFoundError(executable)
                popen([executable, *list(action.get("arguments", []))], shell=False)
        except Exception as exc:
            failures.append(f"{kind}: {exc}")
    return failures


def within_work_hours(preset: PresetConfig, now: datetime | None = None) -> bool:
    if not preset.work_hours_start and not preset.work_hours_end: return True
    clock = (now or datetime.now()).strftime("%H:%M")
    return (not preset.work_hours_start or clock >= preset.work_hours_start) and (
        not preset.work_hours_end or clock <= preset.work_hours_end)
