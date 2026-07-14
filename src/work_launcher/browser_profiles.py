from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from pathlib import Path


class BrowserProfileError(ValueError):
    pass


@dataclass
class BrowserProfile:
    name: str
    type: str
    executable_path: str = ""
    user_data_dir: str = ""
    profile_directory: str = ""
    fallback_to_system_browser: bool = False
    discovery: dict[str, str] = field(default_factory=dict)
    extra: dict = field(default_factory=dict, repr=False)


def validate_safe_value(value: str, label: str) -> None:
    if any(char in value for char in ("\n", "\r", "\0")):
        raise BrowserProfileError(f"{label} contains an invalid control character.")


def validate_profile(profile: BrowserProfile, discover=None, require_files: bool = True) -> Path | None:
    for value, label in ((profile.name, "Profile name"), (profile.executable_path, "Executable path"),
                         (profile.user_data_dir, "User Data directory"), (profile.profile_directory, "Profile Directory")):
        validate_safe_value(value, label)
    if profile.type == "system":
        return None
    chromium_types = {"chrome", "edge", "brave", "chromium", "vivaldi"}
    if profile.type == "firefox":
        executable = Path(profile.executable_path).expanduser() if profile.executable_path else None
        if not profile.profile_directory or profile.profile_directory.startswith("-"):
            raise BrowserProfileError("Firefox Profile Name is required.")
        if require_files and (executable is None or not executable.is_file()):
            raise BrowserProfileError("Mozilla Firefox could not be found. Select firefox.exe in Browser Profiles settings.")
        return executable
    if profile.type not in chromium_types:
        raise BrowserProfileError(f"Unsupported browser type: {profile.type}")
    directory = profile.profile_directory
    if not directory or Path(directory).name != directory or directory in {".", ".."} or directory.startswith("-"):
        raise BrowserProfileError("Profile Directory must be a folder name such as 'Profile 4'.")
    executable = Path(profile.executable_path).expanduser() if profile.executable_path else (discover() if discover else None)
    if require_files:
        if executable is None or not executable.is_file():
            raise BrowserProfileError("Google Chrome could not be found. Select chrome.exe in Browser Profiles settings.")
        user_data = Path(profile.user_data_dir).expanduser()
        if not user_data.is_dir():
            raise BrowserProfileError(f"Chrome User Data directory was not found:\n{user_data}")
        if not (user_data / directory).is_dir():
            raise BrowserProfileError(f"Chrome profile {directory} was not found under:\n{user_data}")
    return executable
