from __future__ import annotations

import logging
import subprocess
import webbrowser
from urllib.parse import urlparse

from .browser_discovery import discover_chrome
from .browser_profiles import BrowserProfile, BrowserProfileError, validate_profile


def sanitized_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def chrome_arguments(executable, profile: BrowserProfile, urls: list[str]) -> list[str]:
    return [str(executable), f"--user-data-dir={profile.user_data_dir}",
            f"--profile-directory={profile.profile_directory}", *urls]


def firefox_arguments(executable, profile: BrowserProfile, urls: list[str]) -> list[str]:
    return [str(executable), "-P", profile.profile_directory, "-no-remote", *urls]


class BrowserLauncher:
    def __init__(self, popen=subprocess.Popen, system_open=webbrowser.open_new_tab, discover=discover_chrome):
        self.popen, self.system_open, self.discover = popen, system_open, discover

    def launch(self, profile: BrowserProfile, urls: list[str], website_names: list[str]) -> None:
        if profile.type == "system":
            for url in urls:
                if not self.system_open(url):
                    raise BrowserProfileError("Windows default browser reported a launch failure.")
            return
        try:
            executable = validate_profile(profile, self.discover, require_files=True)
            args = firefox_arguments(executable, profile, urls) if profile.type == "firefox" else chrome_arguments(executable, profile, urls)
            self.popen(args, shell=False)
            for name, url in zip(website_names, urls):
                logging.info("Launch succeeded: website=%s origin=%s profile=%s type=%s", name, sanitized_origin(url), profile.name, profile.type)
        except Exception:
            logging.error("Launch failed: websites=%s profile=%s type=%s", ", ".join(website_names), profile.name, profile.type)
            if profile.fallback_to_system_browser:
                logging.warning("Using explicitly enabled system-browser fallback for profile %s", profile.name)
                for url in urls:
                    if not self.system_open(url):
                        raise BrowserProfileError("Chrome and the fallback browser both failed.")
                return
            raise
