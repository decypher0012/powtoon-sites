from __future__ import annotations

import subprocess


def notify(title: str, message: str) -> bool:
    """Show a best-effort native Windows message without exposing URLs or secrets."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBeep(0x40)
        # A tray balloon requires a persistent icon; sound plus in-app status is the safe fallback.
        return True
    except Exception:
        return False
