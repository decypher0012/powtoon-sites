import tempfile
import unittest
import json
from pathlib import Path

from work_launcher.config import config_to_dict, default_config, load_config, save_config, validate_config_data
from work_launcher.constants import CONFIG_VERSION
from sample_data import populated_config


class ConfigTests(unittest.TestCase):
    def test_default_configuration_has_no_bundled_websites_or_presets(self):
        config = default_config()
        self.assertEqual(config.websites, [])
        self.assertEqual(config.presets, [])
        self.assertNotEqual(config.browser_profiles["chrome-work"].profile_directory,"Profile 4")
        self.assertEqual(config.browser_profiles["chrome-work"].type,"system")
        example=json.loads((Path(__file__).parents[1]/"config.example.json").read_text(encoding="utf-8"))
        self.assertEqual(example["websites"], [])
        self.assertEqual(example["presets"], [])
        self.assertFalse(any(profile.get("profile_directory")=="Profile 4" for profile in example["browser_profiles"].values()))

    def test_defaults_contain_no_company_specific_urls(self):
        serialized = json.dumps(config_to_dict(default_config())["websites"]).casefold()
        for value in ("powtoon", "hubspot", "okta", "gmail"):
            self.assertNotIn(value, serialized)

    def test_missing_config_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config, warnings = load_config(path)
            self.assertEqual(config.websites, [])
            self.assertEqual(config.updates.owner, "decypher0012")
            self.assertEqual(config.updates.repository, "powtoon-sites")
            self.assertTrue(path.exists())
            self.assertTrue(warnings)

    def test_release_repository_is_built_in_and_repairs_old_values(self):
        raw = config_to_dict(default_config())
        raw["updates"]["owner"] = ""
        raw["updates"]["repository"] = ""
        config = validate_config_data(raw)
        self.assertEqual(config.updates.owner, "decypher0012")
        self.assertEqual(config.updates.repository, "powtoon-sites")

    def test_invalid_json_handling(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{broken", encoding="utf-8")
            config, warnings = load_config(path)
            self.assertEqual(config.websites, [])
            self.assertTrue(any("repaired" in item.lower() for item in warnings))

    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError):
            validate_config_data({"websites": [{"name": "Bad", "url": "ftp://example.com"}]})

    def test_enabled_and_disabled_websites(self):
        config = populated_config()
        config.websites[0].enabled = False
        self.assertFalse(config.websites[0].enabled)

    def test_ordering(self):
        config = populated_config()
        config.websites.reverse()
        self.assertEqual(config.websites[0].name, "Identity")

    def test_selected_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = populated_config()
            config.websites[1].selected = False
            save_config(path, config)
            loaded, _ = load_config(path)
            self.assertFalse(loaded.websites[1].selected)

    def test_migration_from_every_prior_version_is_idempotent_and_preserves_data(self):
        for version in range(1, CONFIG_VERSION):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"config.json"; raw=config_to_dict(populated_config()); raw["config_version"]=version
                raw["settings"]["theme"]="dark"; raw["websites"][0]["selected"]=False
                if version==1: raw.pop("browser_profiles",None); [site.pop("browser_profile",None) for site in raw["websites"]]
                if version<2: raw.pop("setup",None)
                raw.pop("updates",None)
                path.write_text(json.dumps(raw),encoding="utf-8"); config,warnings=load_config(path)
                self.assertEqual(config.config_version,CONFIG_VERSION); self.assertEqual(config.settings.theme,"dark"); self.assertFalse(config.websites[0].selected)
                self.assertTrue(Path(str(path)+".bak").exists()); self.assertTrue(any("migrated" in item for item in warnings))
                _,second=load_config(path); self.assertFalse(any("migrated" in item for item in second))

    def test_unknown_fields_survive_load_save_and_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"config.json"; raw=config_to_dict(populated_config()); raw["config_version"]=3
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

    def test_current_existing_configuration_preserves_user_websites(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            original = populated_config()
            save_config(path, original)
            loaded, warnings = load_config(path)
            self.assertEqual([site.name for site in loaded.websites], [site.name for site in original.websites])
            self.assertFalse(any("migrated" in warning for warning in warnings))
