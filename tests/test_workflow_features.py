from datetime import datetime

import pytest

from work_launcher.config import ApplicationConfig, ConfigError, PresetConfig, config_to_dict, validate_config_data
from work_launcher.global_hotkey import parse_hotkey
from work_launcher.workflow_features import preset_readiness, preset_templates, recent_and_frequent, record_launch, resolve_chain
from sample_data import populated_config


def test_new_preset_controls_round_trip():
    config = populated_config()
    config.presets = [PresetConfig(
        "Focus", ["website:Admin"], pinned=True, hotkey="Ctrl+Alt+F",
        focus_minutes=25, item_rules={"website:Admin": {
            "require_network": True, "weekdays": list(range(7)), "start_time": "08:00", "end_time": "18:00",
        }},
    )]
    loaded = validate_config_data(config_to_dict(config))
    assert loaded.presets[0].pinned
    assert loaded.presets[0].hotkey == "Ctrl+Alt+F"
    assert loaded.presets[0].focus_minutes == 25


def test_invalid_chain_and_focus_are_rejected():
    config = populated_config()
    raw = config_to_dict(config)
    raw["presets"] = [{"name": "One", "items": ["website:Admin"], "chain_next": "Missing"}]
    with pytest.raises(ConfigError, match="chains to missing"):
        validate_config_data(raw)
    raw["presets"][0]["chain_next"] = ""
    raw["presets"][0]["focus_minutes"] = 900
    with pytest.raises(ConfigError, match="focus_minutes"):
        validate_config_data(raw)
    raw["presets"] = [
        {"name": "One", "items": ["website:Admin"], "chain_next": "Two"},
        {"name": "Two", "items": ["website:Gmail"], "chain_next": "One"},
    ]
    with pytest.raises(ConfigError, match="cycle"):
        validate_config_data(raw)


def test_usage_recency_frequency_and_templates():
    config = populated_config()
    record_launch(config, "website:Admin", datetime(2026, 7, 20, 8, 0).astimezone())
    record_launch(config, "website:Gmail", datetime(2026, 7, 20, 9, 0).astimezone())
    record_launch(config, "website:Admin", datetime(2026, 7, 20, 10, 0).astimezone())
    recent, frequent = recent_and_frequent(config)
    assert recent[0] == "website:Admin"
    assert frequent[0] == "website:Admin"
    assert any(item.name == "Morning Setup" and item.pinned for item in preset_templates(config))


def test_readiness_and_chain_resolution(tmp_path):
    config = populated_config()
    executable = tmp_path / "tool.exe"; executable.write_bytes(b"x")
    config.applications = [ApplicationConfig("Tool", str(executable))]
    first = PresetConfig("First", ["application:Tool"], chain_next="Second")
    second = PresetConfig("Second", ["website:Admin"])
    config.presets = [first, second]
    rows = preset_readiness(config, first, network_check=lambda: False)
    assert all(row.ready for row in rows)
    assert [item.name for item in resolve_chain(config, first)] == ["First", "Second"]


def test_hotkey_parser():
    modifiers, key = parse_hotkey("Ctrl+Shift+F2")
    assert modifiers and key
    with pytest.raises(ValueError):
        parse_hotkey("F2")
