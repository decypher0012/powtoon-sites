from datetime import datetime
from unittest.mock import Mock

from work_launcher.config import ApplicationConfig, PresetConfig, config_to_dict, validate_config_data
from work_launcher.workspace_lifecycle import (
    CapturedWindow, apply_parameters, create_captured_preset, import_browser_session,
    run_actions, substitute, winget_missing, within_work_hours,
)
from sample_data import populated_config


def test_capture_creates_apps_layout_and_preset():
    config = populated_config()
    windows = [CapturedWindow("Editor - Project", r"C:\Tools\Editor.exe", 10, 20, 900, 700)]
    preset = create_captured_preset(config, "Project", windows)
    assert preset.items == ["application:Editor"]
    assert preset.window_layout["Editor"]["width"] == 900
    assert config.applications[0].only_if_not_running


def test_lifecycle_fields_round_trip():
    config = populated_config()
    config.applications = [ApplicationConfig("Editor", r"C:\Editor.exe", winget_id="Vendor.Editor", close_on_end=True)]
    config.presets = [PresetConfig(
        "Project", ["application:Editor"], window_layout={"Editor": {"x": 1, "y": 2, "width": 3, "height": 4}},
        browser_session=["https://example.com"], parameters=[{"name": "client", "secret": False}],
        bootstrap_packages=["Vendor.Editor"], actions=[{"type": "open_uri", "uri": "https://example.com"}],
        close_on_end=True, windows_focus=True, notification_profile="focus",
        work_hours_start="08:00", work_hours_end="18:00",
    )]
    loaded = validate_config_data(config_to_dict(config))
    assert loaded.presets[0].windows_focus
    assert loaded.presets[0].notification_profile == "focus"
    assert loaded.applications[0].winget_id == "Vendor.Editor"


def test_parameters_apply_without_mutating_source():
    config = populated_config()
    config.websites[0].url = "https://example.com/{client}"
    preset = PresetConfig("Client", ["website:Admin"], browser_session=["https://example.com/{client}"])
    copied, resolved = apply_parameters(config, preset, {"client": "acme"})
    assert copied.websites[0].url.endswith("/acme")
    assert resolved.browser_session[0].endswith("/acme")
    assert "{client}" in config.websites[0].url
    assert substitute("{missing}", {}) == "{missing}"


def test_browser_session_import_and_work_hours(tmp_path):
    path = tmp_path / "session.json"
    path.write_text('{"tabs":[{"url":"https://one.test"},{"url":"chrome://settings"},{"url":"https://one.test"}]}')
    assert import_browser_session(path) == ["https://one.test"]
    preset = PresetConfig("Work", work_hours_start="08:00", work_hours_end="17:00")
    assert within_work_hours(preset, datetime(2026, 1, 1, 12, 0))
    assert not within_work_hours(preset, datetime(2026, 1, 1, 20, 0))


def test_winget_and_actions_are_bounded():
    runner = Mock()
    runner.return_value.returncode = 1
    assert winget_missing(["Vendor.App"], runner) == ["Vendor.App"]
    popen = Mock()
    executable = __file__
    assert run_actions([{"type": "command", "executable": executable, "arguments": ["--help"]}], popen) == []
    popen.assert_called_once_with([executable, "--help"], shell=False)
    assert run_actions([{"type": "unknown"}], popen)[0].startswith("unknown:")
