import tempfile
import unittest
import json
from pathlib import Path

from work_launcher.config import config_to_dict, default_config, load_config, save_config, validate_config_data


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

    def test_migration_from_every_prior_version_is_idempotent_and_preserves_data(self):
        for version in (1, 2, 3):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"config.json"; raw=config_to_dict(default_config()); raw["config_version"]=version
                raw["settings"]["theme"]="dark"; raw["websites"][0]["selected"]=False
                if version==1: raw.pop("browser_profiles",None); [site.pop("browser_profile",None) for site in raw["websites"]]
                if version<2: raw.pop("setup",None)
                raw.pop("updates",None)
                path.write_text(json.dumps(raw),encoding="utf-8"); config,warnings=load_config(path)
                self.assertEqual(config.config_version,4); self.assertEqual(config.settings.theme,"dark"); self.assertFalse(config.websites[0].selected)
                self.assertTrue(Path(str(path)+".bak").exists()); self.assertTrue(any("migrated" in item for item in warnings))
                _,second=load_config(path); self.assertFalse(any("migrated" in item for item in second))

    def test_unknown_fields_survive_load_save_and_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"config.json"; raw=config_to_dict(default_config()); raw["config_version"]=3
            raw["future_root"]={"keep":True}; raw["settings"]["future_setting"]=7; raw["browser_profiles"]["system-default"]["future_profile"]="yes"
            raw["websites"][0]["future_website"]=[1,2]; raw["setup"]["future_setup"]="keep"; raw["updates"]["future_update"]="keep"
            path.write_text(json.dumps(raw),encoding="utf-8"); config,_=load_config(path); save_config(path,config); saved=json.loads(path.read_text())
            self.assertEqual(saved["future_root"],{"keep":True}); self.assertEqual(saved["settings"]["future_setting"],7)
            self.assertEqual(saved["browser_profiles"]["system-default"]["future_profile"],"yes"); self.assertEqual(saved["websites"][0]["future_website"],[1,2])
            self.assertEqual(saved["setup"]["future_setup"],"keep"); self.assertEqual(saved["updates"]["future_update"],"keep")

    def test_partially_migrated_configuration_preserves_websites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"config.json"; raw={"config_version":3,"settings":{"theme":"light"},"websites":[{"name":"Kept","url":"https://example.com"}]}
            path.write_text(json.dumps(raw),encoding="utf-8"); config,_=load_config(path)
            self.assertEqual(config.websites[0].name,"Kept"); self.assertIn("chrome-work",config.browser_profiles)
