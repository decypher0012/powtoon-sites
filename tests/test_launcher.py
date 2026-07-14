import unittest

from work_launcher.config import default_config
from work_launcher.launcher import WebsiteLauncher


class LauncherTests(unittest.TestCase):
    def test_open_one_website(self):
        calls = []
        launcher = WebsiteLauncher(browser_open=lambda url: calls.append(url) or True)
        result = launcher.open_website(default_config().websites[0])
        self.assertTrue(result.success)
        self.assertEqual(len(calls), 1)

    def test_open_selected_websites(self):
        calls = []
        launcher = WebsiteLauncher(browser_open=lambda url: calls.append(url) or True)
        config = default_config()
        launcher.open_selected(config.websites[:2])
        self.assertEqual(len(calls), 2)

    def test_open_all_websites(self):
        calls = []
        launcher = WebsiteLauncher(browser_open=lambda url: calls.append(url) or True)
        config = default_config()
        launcher.open_all(config.websites)
        self.assertEqual(len(calls), 6)

    def test_browser_failure_handling(self):
        launcher = WebsiteLauncher(browser_open=lambda url: False)
        result = launcher.open_website(default_config().websites[0])
        self.assertFalse(result.success)

    def test_duplicate_cooldown(self):
        launcher = WebsiteLauncher(browser_open=lambda url: True)
        self.assertTrue(launcher.can_launch_all(0))

