import unittest

from work_launcher.browser_profiles import BrowserProfile
from work_launcher.browser_launcher import BrowserLauncher
from work_launcher.launcher import WebsiteLauncher
from sample_data import populated_config


class LauncherTests(unittest.TestCase):
    def test_open_one_website(self):
        calls = []
        launcher = WebsiteLauncher(browser_open=lambda url: calls.append(url) or True)
        result = launcher.open_website(populated_config().websites[0])
        self.assertTrue(result.success)
        self.assertEqual(len(calls), 1)

    def test_open_selected_websites(self):
        calls = []
        launcher = WebsiteLauncher(browser_open=lambda url: calls.append(url) or True)
        config = populated_config()
        launcher.open_selected(config.websites[:2])
        self.assertEqual(len(calls), 2)

    def test_open_all_websites(self):
        calls = []
        launcher = WebsiteLauncher(browser_open=lambda url: calls.append(url) or True)
        config = populated_config()
        launcher.open_all(config.websites)
        self.assertEqual(len(calls), 6)

    def test_browser_failure_handling(self):
        launcher = WebsiteLauncher(browser_open=lambda url: False)
        result = launcher.open_website(populated_config().websites[0])
        self.assertFalse(result.success)

    def test_duplicate_cooldown(self):
        launcher = WebsiteLauncher(browser_open=lambda url: True)
        self.assertTrue(launcher.can_launch_all(0))

    def test_mixed_profile_validity_launches_valid_and_skips_invalid_without_fallback(self):
        config=populated_config();calls=[]
        config.browser_profiles["bad"]=BrowserProfile("Unavailable","chrome",r"C:\missing\chrome.exe",r"C:\missing","Profile 9",False)
        config.websites[0].browser_profile="system-default";config.websites[1].browser_profile="bad"
        launcher=WebsiteLauncher(browser_profiles=config.browser_profiles,browser_launcher=BrowserLauncher(system_open=lambda url:calls.append(url) or True))
        results=launcher.open_selected(config.websites[:2])
        self.assertTrue(results[0].success);self.assertFalse(results[1].success);self.assertEqual(calls,[config.websites[0].url])
