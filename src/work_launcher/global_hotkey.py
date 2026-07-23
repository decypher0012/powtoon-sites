from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Callable


KEY_CODES = {chr(code): code for code in range(ord("A"), ord("Z") + 1)}
KEY_CODES.update({str(value): ord(str(value)) for value in range(10)})
KEY_CODES.update({f"F{value}": 0x6F + value for value in range(1, 13)})
MODIFIERS = {"ALT": 0x0001, "CTRL": 0x0002, "SHIFT": 0x0004, "WIN": 0x0008}


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = [part.strip().upper() for part in value.split("+") if part.strip()]
    if len(parts) < 2 or parts[-1] not in KEY_CODES:
        raise ValueError("Use a shortcut such as Ctrl+Alt+M or Ctrl+Shift+F2.")
    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError(f"Unsupported hotkey modifier: {part}")
        modifiers |= MODIFIERS[part]
    return modifiers, KEY_CODES[parts[-1]]


class GlobalHotkey:
    HOTKEY_ID = 0x574C

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.thread: threading.Thread | None = None
        self.thread_id = 0

    def start(self) -> bool:
        if self.thread or not hasattr(ctypes, "windll"):
            return False
        ready = threading.Event()
        result = {"ok": False}
        def run():
            kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
            self.thread_id = kernel32.GetCurrentThreadId()
            result["ok"] = bool(user32.RegisterHotKey(None, self.HOTKEY_ID, 0x0001 | 0x0002, 0x20))
            ready.set()
            if not result["ok"]:
                return
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam == self.HOTKEY_ID:
                    self.callback()
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
        self.thread = threading.Thread(target=run, name="work-launcher-hotkey", daemon=True)
        self.thread.start(); ready.wait(2)
        if not result["ok"]: self.thread = None
        return result["ok"]

    def stop(self) -> None:
        if self.thread_id and hasattr(ctypes, "windll"):
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        self.thread = None


class PresetHotkeys:
    def __init__(self, callbacks: dict[str, Callable[[], None]]):
        self.callbacks = callbacks
        self.thread: threading.Thread | None = None
        self.thread_id = 0
        self.failures: list[str] = []

    def start(self) -> bool:
        if self.thread or not hasattr(ctypes, "windll") or not self.callbacks:
            return False
        ready = threading.Event()
        def run():
            kernel32, user32 = ctypes.windll.kernel32, ctypes.windll.user32
            self.thread_id = kernel32.GetCurrentThreadId()
            registered: dict[int, Callable[[], None]] = {}
            for offset, (shortcut, callback) in enumerate(self.callbacks.items(), start=1):
                try:
                    modifiers, key = parse_hotkey(shortcut)
                except ValueError:
                    self.failures.append(shortcut); continue
                hotkey_id = GlobalHotkey.HOTKEY_ID + offset
                if user32.RegisterHotKey(None, hotkey_id, modifiers, key):
                    registered[hotkey_id] = callback
                else:
                    self.failures.append(shortcut)
            ready.set()
            msg = ctypes.wintypes.MSG()
            while registered and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                callback = registered.get(msg.wParam) if msg.message == 0x0312 else None
                if callback:
                    callback()
            for hotkey_id in registered:
                user32.UnregisterHotKey(None, hotkey_id)
        self.thread = threading.Thread(target=run, name="work-launcher-preset-hotkeys", daemon=True)
        self.thread.start(); ready.wait(2)
        return bool(self.thread and len(self.failures) < len(self.callbacks))

    def stop(self) -> None:
        if self.thread_id and hasattr(ctypes, "windll"):
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        self.thread = None
