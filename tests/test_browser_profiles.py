import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from work_launcher.browser_discovery import discover_chrome
from work_launcher.browser_launcher import BrowserLauncher, chrome_arguments
from work_launcher.browser_profiles import BrowserProfile, BrowserProfileError, validate_profile
from work_launcher.config import ConfigError, default_config, load_config, save_config, validate_config_data
from work_launcher.launcher import WebsiteLauncher
from work_launcher.settings import delete_browser_profile


class DiscoveryTests(unittest.TestCase):
    def _find(self, variable):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "Google/Chrome/Application/chrome.exe"
            exe.parent.mkdir(parents=True); exe.touch()
            self.assertEqual(discover_chrome({variable: tmp}), exe)

    def test_program_files(self): self._find("PROGRAMFILES")
    def test_program_files_x86(self): self._find("PROGRAMFILES(X86)")
    def test_local_app_data(self): self._find("LOCALAPPDATA")
    def test_missing_chrome(self): self.assertIsNone(discover_chrome({}))


class ProfileValidationTests(unittest.TestCase):
    def _tree(self):
        tmp = tempfile.TemporaryDirectory(); root = Path(tmp.name)
        exe = root / "Chrome App/chrome.exe"; exe.parent.mkdir(); exe.touch()
        data = root / "User Data"; (data / "Profile 4").mkdir(parents=True)
        return tmp, exe, data

    def test_explicit_executable_and_valid_directories(self):
        tmp, exe, data = self._tree()
        with tmp:
            profile = BrowserProfile("Work", "chrome", str(exe), str(data), "Profile 4")
            self.assertEqual(validate_profile(profile, require_files=True), exe)

    def test_missing_user_data(self):
        tmp, exe, data = self._tree()
        with tmp, self.assertRaisesRegex(BrowserProfileError, "User Data"):
            validate_profile(BrowserProfile("Work", "chrome", str(exe), str(data / "missing"), "Profile 4"), require_files=True)

    def test_missing_profile_directory(self):
        tmp, exe, data = self._tree()
        with tmp, self.assertRaisesRegex(BrowserProfileError, "Profile 9"):
            validate_profile(BrowserProfile("Work", "chrome", str(exe), str(data), "Profile 9"), require_files=True)

    def test_injection_and_arbitrary_directory_rejected(self):
        for directory in ("../Profile 4", "--incognito", "Profile 4\n--flag"):
            with self.subTest(directory=directory), self.assertRaises(BrowserProfileError):
                validate_profile(BrowserProfile("Work", "chrome", "", "x", directory), require_files=False)


class BrowserLaunchTests(unittest.TestCase):
    def setUp(self):
        self.profile = BrowserProfile("Chrome Work", "chrome", "", r"C:\Users\A B\User Data", "Profile 4")

    def test_argument_construction_spaces_and_separate_urls(self):
        args = chrome_arguments(Path(r"C:\Program Files\Chrome\chrome.exe"), self.profile, ["https://a.test", "https://b.test"])
        self.assertEqual(args[1], r"--user-data-dir=C:\Users\A B\User Data")
        self.assertEqual(args[-2:], ["https://a.test", "https://b.test"])

    def test_popen_shell_false(self):
        popen = Mock(); launcher = BrowserLauncher(popen=popen, discover=lambda: Path("chrome.exe"))
        with patch("work_launcher.browser_launcher.validate_profile", return_value=Path(r"C:\Chrome App\chrome.exe")):
            launcher.launch(self.profile, ["https://a.test"], ["A"])
        popen.assert_called_once(); self.assertFalse(popen.call_args.kwargs["shell"])

    def test_system_default(self):
        opened = []; BrowserLauncher(system_open=lambda url: opened.append(url) or True).launch(
            BrowserProfile("Default", "system"), ["https://a.test"], ["A"])
        self.assertEqual(opened, ["https://a.test"])

    def test_explicit_fallback_and_disabled_fallback(self):
        opened = []; profile = BrowserProfile("Work", "chrome", fallback_to_system_browser=True)
        BrowserLauncher(system_open=lambda url: opened.append(url) or True, discover=lambda: None).launch(profile, ["https://a.test"], ["A"])
        self.assertEqual(len(opened), 1)
        profile.fallback_to_system_browser = False
        with self.assertRaises(BrowserProfileError): BrowserLauncher(discover=lambda: None).launch(profile, ["https://a.test"], ["A"])

    def test_open_one_selected_all_and_mixed_are_mocked(self):
        config = default_config(); backend = Mock(); backend.launch.return_value = None
        launcher = WebsiteLauncher(browser_profiles=config.browser_profiles, browser_launcher=backend)
        self.assertTrue(launcher.open_website(config.websites[0]).success)
        self.assertEqual(len(launcher.open_selected(config.websites[:2])), 2)
        self.assertEqual(len(launcher.open_all(config.websites)), 6)
        config.websites[0].browser_profile = "system-default"
        launcher.open_selected(config.websites[:2])
        self.assertEqual(backend.launch.call_count, 11)


class MigrationTests(unittest.TestCase):
    def _legacy(self):
        return {"settings": {"theme": "dark"}, "websites": [{"name": "Custom", "url": "https://example.com", "selected": False}]}

    def test_migration_preserves_and_backs_up_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"; path.write_text(json.dumps(self._legacy()), encoding="utf-8")
            config, warnings = load_config(path)
            self.assertEqual(config.websites[0].name, "Custom"); self.assertFalse(config.websites[0].selected)
            self.assertIn("chrome-work", config.browser_profiles); self.assertTrue(Path(str(path) + ".bak").exists())
            self.assertTrue(warnings); _, second = load_config(path); self.assertFalse(any("migrated" in x for x in second))

    def test_migration_write_failure_retains_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"; original = json.dumps(self._legacy()); path.write_text(original, encoding="utf-8")
            with patch("work_launcher.config.write_config", side_effect=OSError("disk full")):
                config, warnings = load_config(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original); self.assertEqual(config.websites[0].name, "Custom")
            self.assertTrue(any("retained" in x for x in warnings))

    def test_defaults_assign_all_six_to_work(self):
        self.assertEqual([w.browser_profile for w in default_config().websites], ["chrome-work"] * 6)

    def test_assignment_persistence_and_invalid_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"; config = default_config(); config.websites[0].browser_profile = "system-default"
            save_config(path, config); loaded, _ = load_config(path); self.assertEqual(loaded.websites[0].browser_profile, "system-default")
        raw = {"browser_profiles": {"system-default": {"name": "Default", "type": "system"}},
               "websites": [{"name": "X", "url": "https://x.test", "browser_profile": "missing"}]}
        with self.assertRaises(ConfigError): validate_config_data(raw)

    def test_delete_in_use_prevented(self):
        with self.assertRaises(ConfigError): delete_browser_profile(default_config(), "chrome-work")
