import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from work_launcher.config import WebsiteConfig, default_config, load_config, save_config
from work_launcher.website_manager import (UndoHistory, WebsiteValidationError, add_website, bulk_update,
    create_timestamped_backup, delete_websites, duplicate_website, edit_website, export_json,
    import_websites, move_websites, preview_import, search_websites, validate_website, websites_for_group)


def site(name="Example", url="https://example.com", group=""):
    return WebsiteConfig(name, url, True, True, "chrome-work", group)


def test_add_edit_delete_duplicate():
    config = default_config(); original = len(config.websites)
    add_website(config, site()); assert len(config.websites) == original + 1
    edit_website(config, original, site("Edited", "https://edited.example")); assert config.websites[-1].name == "Edited"
    copy = duplicate_website(config, original); assert copy.name == "Edited (Copy)"; assert copy.url == "https://edited.example"
    removed = delete_websites(config, [original, original + 1]); assert len(removed) == 2; assert len(config.websites) == original


def test_validation_errors_and_duplicate_warnings():
    config = default_config()
    with pytest.raises(WebsiteValidationError): validate_website(site("", "https://x.test"), config)
    with pytest.raises(ValueError): validate_website(site("Bad", "file:///bad"), config)
    with pytest.raises(ValueError): validate_website(WebsiteConfig("Bad", "https://x.test", browser_profile="missing"), config)
    warnings = validate_website(site(config.websites[0].name, config.websites[0].url), config)
    assert len(warnings) == 2


def test_search_name_url_and_browser_profile():
    config = default_config()
    assert search_websites(config, "Gmail") == [1]
    assert search_websites(config, "keep.google") == [3]
    assert len(search_websites(config, "Chrome Work")) == 6
    assert len(search_websites(config, "")) == 6


def test_multi_selection_bulk_assignment_and_enable():
    config = default_config(); bulk_update(config, [0, 2, 4], enabled=False, browser_profile="system-default")
    assert [config.websites[i].enabled for i in [0, 2, 4]] == [False] * 3
    assert [config.websites[i].browser_profile for i in [0, 2, 4]] == ["system-default"] * 3


def test_move_selected_together():
    config = default_config(); names = [w.name for w in config.websites]
    selected = move_websites(config, [1, 2], 1)
    assert selected == [2, 3]; assert [w.name for w in config.websites][2:4] == names[1:3]
    selected = move_websites(config, selected, -1); assert selected == [1, 2]


def test_undo_delete_and_replace():
    config = default_config(); history = UndoHistory(); history.remember(config)
    delete_websites(config, [0, 1]); assert len(config.websites) == 4
    assert history.undo(config); assert len(config.websites) == 6; assert not history.undo(config)
    history.remember(config); import_websites(config, [site()], replace=True); assert len(config.websites) == 1
    history.undo(config); assert len(config.websites) == 6


def test_import_merge_replace_and_duplicate_options():
    config = default_config(); incoming = [site("Gmail", "https://new.test"), site("New", config.websites[0].url), site()]
    count = import_websites(config, incoming, skip_duplicate_names=True, skip_duplicate_urls=True)
    assert count == 1; assert config.websites[-1].name == "Example"
    count = import_websites(config, [site("Only")], replace=True); assert count == 1; assert len(config.websites) == 1


def test_import_preview_current_format_and_export_modes():
    config = default_config()
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "import.json"; source.write_text(json.dumps({"websites": [vars(site())]}), encoding="utf-8")
        assert preview_import(source, config)[0].name == "Example"
        websites = Path(tmp) / "websites.json"; export_json(websites, config, False)
        assert set(json.loads(websites.read_text())["websites"][0]) >= {"name", "launch_group"}
        entire = Path(tmp) / "config.json"; export_json(entire, config, True)
        assert "browser_profiles" in json.loads(entire.read_text())


def test_timestamped_backup_creation_and_retention():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"; path.write_text("working", encoding="utf-8")
        base = datetime(2026, 7, 14, 14, 35)
        for offset in range(12): create_timestamped_backup(path, keep=10, now=base + timedelta(seconds=offset))
        backups = list(Path(tmp).glob("config-*.json")); assert len(backups) == 10
        assert all(item.read_text(encoding="utf-8") == "working" for item in backups)


def test_launch_groups_and_dynamic_configuration_persistence():
    config = default_config(); config.websites[0].launch_group = "Admin"; config.websites[1].launch_group = "Google"
    config.websites[2].launch_group = "Google"; config.websites[2].enabled = False
    assert [w.name for w in websites_for_group(config, "Google")] == ["Gmail"]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"; add_website(config, site("Runtime Website", "https://runtime.test", "Custom")); save_config(path, config)
        loaded, _ = load_config(path); assert loaded.websites[-1].name == "Runtime Website"; assert loaded.websites[-1].launch_group == "Custom"
