import json
import tempfile
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest

from work_launcher.browser_launcher import BrowserLauncher, firefox_arguments
from work_launcher.browser_profiles import BrowserProfile, BrowserProfileError, validate_profile
from work_launcher.browser_scanner import (BROWSERS, DiscoveredBrowserProfile, find_browser_executable,
    scan_browsers, scan_chromium_profiles, scan_firefox_profiles)
from work_launcher.config import default_config, load_config
from work_launcher.setup_service import (assign_all_websites, assign_websites, cancel_setup, complete_setup,
    detected_profile_exists, import_detected_profile, should_run_setup)


@pytest.mark.parametrize("browser_type,variable", [
    ("chrome", "PROGRAMFILES"), ("edge", "PROGRAMFILES(X86)"), ("brave", "LOCALAPPDATA"),
    ("vivaldi", "PROGRAMFILES"), ("chromium", "LOCALAPPDATA")])
def test_chromium_family_installation_detection(browser_type, variable):
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / Path(BROWSERS[browser_type][1]); exe.parent.mkdir(parents=True); exe.touch()
        assert find_browser_executable(browser_type, {variable: tmp}) == exe


def test_firefox_installation_and_browser_not_installed():
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "Mozilla Firefox/firefox.exe"; exe.parent.mkdir(); exe.touch()
        assert find_browser_executable("firefox", {"PROGRAMFILES": tmp}) == exe
    assert find_browser_executable("firefox", {}, registry=Mock(OpenKey=Mock(side_effect=OSError))) is None


def test_custom_executable_path():
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "portable.exe"; exe.touch()
        assert find_browser_executable("chrome", {}, custom_path=str(exe)) == exe


def chromium_tree(browser_type="chrome", local_state=True, corrupt=False):
    tmp = tempfile.TemporaryDirectory(); local = Path(tmp.name); data = local / Path(BROWSERS[browser_type][2]); data.mkdir(parents=True)
    for folder in ("Default", "Profile 4", "Random Folder"):
        target = data / folder; target.mkdir(); (target / "Preferences").touch()
    if local_state:
        content = "{broken" if corrupt else json.dumps({"profile": {"last_used": "Profile 4", "info_cache": {"Default": {"name": "Personal"}, "Profile 4": {"name": "Powtoon Work"}}}})
        (data / "Local State").write_text(content, encoding="utf-8")
    exe = local / "browser.exe"; exe.touch()
    return tmp, local, exe


@pytest.mark.parametrize("browser_type", ["chrome", "edge", "brave"])
def test_default_numbered_friendly_and_browser_specific_profiles(browser_type):
    tmp, local, exe = chromium_tree(browser_type)
    with tmp:
        profiles = scan_chromium_profiles(browser_type, exe, {"LOCALAPPDATA": str(local)})
        assert [item.profile_directory for item in profiles] == ["Default", "Profile 4"]
        assert [item.profile_display_name for item in profiles] == ["Personal", "Powtoon Work"]
        assert profiles[1].is_default


@pytest.mark.parametrize("local_state,corrupt", [(False, False), (True, True)])
def test_missing_or_corrupt_chromium_metadata_falls_back(local_state, corrupt):
    tmp, local, exe = chromium_tree(local_state=local_state, corrupt=corrupt)
    with tmp:
        profiles = scan_chromium_profiles("chrome", exe, {"LOCALAPPDATA": str(local)})
        assert profiles[0].profile_display_name == "Default"


def write_firefox(tmp, relative=True, empty=False):
    roaming = Path(tmp); root = roaming / "Mozilla/Firefox"; root.mkdir(parents=True)
    if empty: (root / "profiles.ini").write_text("", encoding="utf-8"); return roaming, root, None
    profile = root / "Profiles/abc.work" if relative else Path(tmp) / "absolute-profile"; profile.mkdir(parents=True)
    path_value = "Profiles/abc.work" if relative else str(profile)
    (root / "profiles.ini").write_text(f"[Profile0]\nName=Powtoon Work\nIsRelative={1 if relative else 0}\nPath={path_value}\nDefault=1\n", encoding="utf-8")
    return roaming, root, profile


@pytest.mark.parametrize("relative", [True, False])
def test_firefox_profiles_relative_absolute_and_default(relative):
    with tempfile.TemporaryDirectory() as tmp:
        roaming, _, profile = write_firefox(tmp, relative); exe = Path(tmp) / "firefox.exe"; exe.touch()
        found = scan_firefox_profiles(exe, {"APPDATA": str(roaming)})
        assert found[0].profile_display_name == "Powtoon Work"; assert found[0].is_default; assert found[0].profile_directory == "Powtoon Work"


def test_empty_firefox_config_and_permission_denied(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        roaming, _, _ = write_firefox(tmp, empty=True); exe = Path(tmp) / "firefox.exe"; exe.touch()
        assert scan_firefox_profiles(exe, {"APPDATA": str(roaming)}) == []
    monkeypatch.setattr(Path, "is_file", lambda self: (_ for _ in ()).throw(PermissionError("denied")))
    assert find_browser_executable("chrome", {"PROGRAMFILES": "X"}, registry=Mock(OpenKey=Mock(side_effect=OSError))) is None


def test_scan_cancellation_and_rescan_behavior():
    cancel = Event(); cancel.set(); assert scan_browsers({}, registry=Mock(OpenKey=Mock(side_effect=OSError)), cancel_event=cancel) == []
    first = scan_browsers({}, registry=Mock(OpenKey=Mock(side_effect=OSError)))
    second = scan_browsers({}, registry=Mock(OpenKey=Mock(side_effect=OSError)))
    assert len(first) == len(second) == 6


def detected():
    return DiscoveredBrowserProfile("chrome", "Google Chrome", r"C:\Chrome\chrome.exe", r"C:\User Data", "Profile 4", "Work")


def test_duplicate_existing_import_and_persistence():
    config = default_config(); item = detected(); key = import_detected_profile(config, item)
    assert detected_profile_exists(config, item); assert import_detected_profile(config, item) == key
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"; complete_setup(path, config); loaded, _ = load_config(path)
        assert key in loaded.browser_profiles; assert loaded.browser_profiles[key].discovery["source"] == "automatic"


def test_first_run_completion_cancellation_and_assignment():
    config = default_config(); assert should_run_setup(config, False); assert should_run_setup(config, True)
    key = import_detected_profile(config, detected()); assign_all_websites(config, key); config.setup.completed = True
    assert not should_run_setup(config, True); assert {site.browser_profile for site in config.websites} == {key}
    assign_websites(config, {0: "system-default", 1: key}); assert config.websites[0].browser_profile == "system-default"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"; cancel_setup(path, config); assert not config.setup.completed
        assert {site.browser_profile for site in config.websites} == {"system-default"}


def test_firefox_launch_arguments_and_no_shell():
    profile = BrowserProfile("Firefox Work", "firefox", r"C:\Firefox\firefox.exe", "", "Powtoon Work")
    args = firefox_arguments(Path(profile.executable_path), profile, ["https://example.com"])
    assert args[-4:] == ["-P", "Powtoon Work", "-no-remote", "https://example.com"]
    popen = Mock(); launcher = BrowserLauncher(popen=popen)
    from unittest.mock import patch
    with patch("work_launcher.browser_launcher.validate_profile", return_value=Path(profile.executable_path)):
        launcher.launch(profile, ["https://example.com"], ["Test"])
    assert popen.call_args.kwargs["shell"] is False


def test_stale_profile_detection():
    with pytest.raises(BrowserProfileError):
        validate_profile(BrowserProfile("Stale", "edge", r"C:\missing.exe", r"C:\missing", "Default"), require_files=True)
