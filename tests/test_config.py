import tempfile
import unittest
from pathlib import Path

from work_launcher.config import default_config, load_config, save_config, validate_config_data


class ConfigTests(unittest.TestCase):
    def test_default_website_configuration(self):
        config = default_config()
        self.assertEqual(len(config.websites), 6)

    def test_all_required_urls(self):
        urls = [w.url for w in default_config().websites]
        self.assertIn("https://www.renewals-tracker.powtoon.com/admin", urls)
        self.assertIn("https://mail.google.com/", urls)
        self.assertIn("https://calendar.google.com/", urls)
        self.assertIn("https://keep.google.com/", urls)
        self.assertIn("https://app.hubspot.com/reports-dashboard/3444711/view/10170444", urls)
        self.assertIn("https://powtoon.okta.com/", urls)

    def test_missing_config_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config, warnings = load_config(path)
            self.assertEqual(len(config.websites), 6)
            self.assertTrue(path.exists())
            self.assertTrue(warnings)

    def test_invalid_json_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            config, warnings = load_config(path)
            self.assertEqual(len(config.websites), 6)
            self.assertTrue(any("repaired" in item.lower() for item in warnings))

    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError):
            validate_config_data({"websites": [{"name": "Bad", "url": "ftp://example.com"}]})

    def test_enabled_and_disabled_websites(self):
        config = default_config()
        config.websites[0].enabled = False
        self.assertFalse(config.websites[0].enabled)

    def test_ordering(self):
        config = default_config()
        config.websites.reverse()
        self.assertEqual(config.websites[0].name, "Powtoon Okta")

    def test_selected_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = default_config()
            config.websites[1].selected = False
            save_config(path, config)
            loaded, _ = load_config(path)
            self.assertFalse(loaded.websites[1].selected)
