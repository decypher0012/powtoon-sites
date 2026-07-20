from datetime import datetime
from unittest.mock import Mock

import pytest

from work_launcher.config import (ApplicationConfig, ConfigError, PresetConfig, ScheduleConfig,
                                  validate_config_data, config_to_dict)
from work_launcher.enterprise_policy import EnterprisePolicy, apply_policy
from work_launcher.launcher import LaunchResult
from work_launcher.scheduler import ScheduleState, due_schedules
from work_launcher.workspace_launcher import WorkspaceLauncher
from sample_data import populated_config


def test_configuration_requires_real_booleans_and_valid_workspace_references():
    data = config_to_dict(populated_config())
    data["websites"][0]["enabled"] = "false"
    with pytest.raises(ConfigError, match="true or false"):
        validate_config_data(data)
    data = config_to_dict(populated_config())
    data["presets"] = [{"name": "Morning", "items": ["website:Missing"]}]
    with pytest.raises(ConfigError, match="missing items"):
        validate_config_data(data)


def test_application_launch_uses_argument_list_without_shell(tmp_path):
    executable = tmp_path / "tool.exe"
    executable.write_bytes(b"test")
    config = populated_config()
    application = ApplicationConfig("Tool", str(executable), ["--safe", "value with spaces"])
    popen = Mock()
    launcher = WorkspaceLauncher(config, Mock(), popen=popen)
    result = launcher.launch_application(application)
    assert result.success
    popen.assert_called_once_with([str(executable), "--safe", "value with spaces"],
                                  cwd=str(tmp_path), shell=False)


def test_preset_preserves_mixed_item_order(tmp_path):
    executable = tmp_path / "tool.exe"
    executable.write_bytes(b"test")
    config = populated_config()
    config.applications = [ApplicationConfig("Tool", str(executable))]
    preset = PresetConfig("Morning", [f"website:{config.websites[0].name}", "application:Tool"], 0)
    website_launcher = Mock()
    website_launcher.open_website.return_value = LaunchResult(True, "opened")
    popen = Mock()
    results = WorkspaceLauncher(config, website_launcher, popen=popen).launch_preset(preset)
    assert [item.kind for item in results] == ["website", "application"]
    assert all(item.success for item in results)


def test_schedule_runs_once_per_day_and_respects_network():
    schedule = ScheduleConfig("Morning", "Preset", "09:30", [0], require_network=True)
    state: dict[str, ScheduleState] = {}
    now = datetime(2026, 7, 20, 9, 30)
    assert due_schedules([schedule], state, now, network_ok=False) == []
    assert due_schedules([schedule], state, now, network_ok=True) == [schedule]
    assert due_schedules([schedule], state, now, network_ok=True) == []


def test_enterprise_policy_removes_local_applications_when_disabled():
    config = populated_config()
    config.applications = [ApplicationConfig("Tool", "tool.exe")]
    config.presets = [PresetConfig("Preset", ["application:Tool"])]
    apply_policy(config, EnterprisePolicy(allow_applications=False))
    assert config.applications == []
    assert config.presets[0].items == []
