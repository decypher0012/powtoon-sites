from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Callable


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
