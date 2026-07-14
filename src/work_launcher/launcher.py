from __future__ import annotations

import logging
import time
import webbrowser
from dataclasses import dataclass
from typing import Callable

from .config import WebsiteConfig
from .browser_launcher import BrowserLauncher
from .browser_profiles import BrowserProfile


@dataclass
class LaunchResult:
    success: bool
    message: str


class WebsiteLauncher:
    def __init__(self, browser_open: Callable[[str], bool] | None = None,
                 browser_profiles: dict[str, BrowserProfile] | None = None,
                 browser_launcher: BrowserLauncher | None = None) -> None:
        if browser_profiles is None and browser_open is not None:
            self.browser_profiles = {
                "system-default": BrowserProfile("Windows Default Browser", "system"),
                "chrome-work": BrowserProfile("Test Browser", "system"),
            }
        else:
            self.browser_profiles = browser_profiles or {"system-default": BrowserProfile("Windows Default Browser", "system")}
        self.browser_launcher = browser_launcher or BrowserLauncher(system_open=browser_open or webbrowser.open_new_tab)
        self._last_launch_all = 0.0

    def open_website(self, website: WebsiteConfig) -> LaunchResult:
        if not website.enabled:
            return LaunchResult(False, f"{website.name} is disabled.")
        try:
            profile = self.browser_profiles.get(website.browser_profile)
            if profile is None:
                raise ValueError(f"Unknown browser profile: {website.browser_profile}")
            logging.info("Opening website: %s profile=%s type=%s", website.name, profile.name, profile.type)
            self.browser_launcher.launch(profile, [website.url], [website.name])
            return LaunchResult(True, f"Opened {website.name}.")
        except Exception as exc:
            logging.exception("Failed to open website %s", website.name)
            return LaunchResult(False, f"Failed to open {website.name}: {exc}")

    def open_selected(self, websites: list[WebsiteConfig], delay_seconds: float = 0.0) -> list[LaunchResult]:
        results: list[LaunchResult] = []
        for index, website in enumerate(websites):
            if index > 0 and delay_seconds > 0:
                time.sleep(delay_seconds)
            results.append(self.open_website(website))
        return results

    def open_all(self, websites: list[WebsiteConfig], delay_seconds: float = 0.0) -> list[LaunchResult]:
        now = time.monotonic()
        self._last_launch_all = now
        return self.open_selected([w for w in websites if w.enabled], delay_seconds=delay_seconds)

    def can_launch_all(self, cooldown_seconds: float) -> bool:
        return (time.monotonic() - self._last_launch_all) >= cooldown_seconds
