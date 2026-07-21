from pathlib import Path
from unittest.mock import Mock

from work_launcher.backup_center import create_backup, inspect_backup
from work_launcher.bookmark_import import parse_bookmarks
from work_launcher.config import WebsiteConfig, default_config
from work_launcher.windows_tasks import sync_tasks
from work_launcher.config import ScheduleConfig


def test_bookmark_import_accepts_http_and_deduplicates(tmp_path):
    path = tmp_path / "bookmarks.html"
    path.write_text('<A HREF="https://example.com">Example</A><A HREF="javascript:x">Bad</A>'
                    '<A HREF="https://example.com">Duplicate</A>', encoding="utf-8")
    assert parse_bookmarks(path) == [parse_bookmarks(path)[0]]
    assert parse_bookmarks(path)[0].name == "Example"


def test_backup_round_trip_preserves_tags_and_favorite(tmp_path):
    config = default_config()
    config.websites.append(WebsiteConfig("Docs", "https://example.com", browser_profile="system-default",
                                         favorite=True, tags=["Daily", "Docs"]))
    path = create_backup(config, tmp_path / "backup.json")
    restored, summary = inspect_backup(path)
    assert restored.websites[0].favorite
    assert restored.websites[0].tags == ["Daily", "Docs"]
    assert "1 websites" in summary


def test_windows_tasks_use_argument_list():
    runner = Mock(); runner.return_value.returncode = 0
    runner.return_value.stderr = runner.return_value.stdout = ""
    errors = sync_tasks([ScheduleConfig("Morning", "Preset", "09:00", [0, 2])], Path("C:/App/WorkLauncher.exe"), runner)
    assert errors == []
    command = runner.call_args.args[0]
    assert command[:3] == ["schtasks", "/Create", "/F"]
    assert "MON,WED" in command
