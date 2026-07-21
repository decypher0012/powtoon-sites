from pathlib import Path
from unittest.mock import Mock

from work_launcher.backup_center import create_backup, inspect_backup
from work_launcher.bookmark_import import parse_bookmarks
from work_launcher.config import WebsiteConfig, config_to_dict, default_config
from work_launcher.windows_tasks import sync_tasks, task_name
from work_launcher.config import ApplicationConfig, PresetConfig, ScheduleConfig
from work_launcher.productivity_tools import export_transfer, find_repair_issues, import_transfer, verify_organization_package
from work_launcher.launcher import LaunchResult
from work_launcher.workspace_launcher import WorkspaceLauncher


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


def test_windows_tasks_remove_obsolete_owned_tasks():
    runner = Mock()
    runner.side_effect = [Mock(returncode=0, stdout='"\\WorkLauncher-old","N/A"\n', stderr=""),
                          Mock(returncode=0, stdout="", stderr=""), Mock(returncode=0, stdout="", stderr="")]
    schedule = ScheduleConfig("Morning", "Preset", "09:00", [0])
    assert sync_tasks([schedule], Path("C:/WorkLauncher.exe"), runner) == []
    assert runner.call_args_list[1].args[0][:3] == ["schtasks", "/Delete", "/F"]


def test_dry_run_does_not_open_items():
    config = default_config(); config.websites.append(WebsiteConfig("Docs", "https://example.com", browser_profile="system-default"))
    website_launcher = Mock(); preset = PresetConfig("Preview", ["website:Docs"], run_mode="dry-run")
    results = WorkspaceLauncher(config, website_launcher).launch_preset(preset)
    assert results[0].status == "would open"
    website_launcher.open_website.assert_not_called()


def test_transfer_reports_machine_specific_missing_application(tmp_path):
    config = default_config(); config.applications.append(ApplicationConfig("Missing", str(tmp_path / "missing.exe")))
    path = tmp_path / "transfer.json"; export_transfer(config, path)
    restored, issues = import_transfer(path)
    assert restored.applications[0].name == "Missing"
    assert any(issue.kind == "application" for issue in issues)


def test_signed_organization_package_verifies(tmp_path):
    import base64, json
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = json.dumps({"format": "work-launcher-organization-v1", "config": config_to_dict(default_config())}).encode()
    signature = key.sign(payload, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    package = tmp_path / "org.json"; public = tmp_path / "public.pem"
    package.write_text(json.dumps({"payload": base64.b64encode(payload).decode(), "signature": base64.b64encode(signature).decode()}), encoding="utf-8")
    public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    assert verify_organization_package(package, public)["format"] == "work-launcher-organization-v1"
