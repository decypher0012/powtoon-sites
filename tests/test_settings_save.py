import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from work_launcher.app import SettingsWindow
from work_launcher.browser_profiles import BrowserProfile
from work_launcher.config import default_config
from sample_data import populated_config


class Var:
    def __init__(self,value): self.value=value
    def get(self): return self.value


def settings_window(config, path, executable):
    window=object.__new__(SettingsWindow);window.original_config=copy.deepcopy(config);window.dirty_sections=set();window.destroy=Mock()
    window.master_app=SimpleNamespace(config=config,config_path=path,executable_path=executable,refresh_ui=Mock(),
        launcher=SimpleNamespace(browser_profiles=config.browser_profiles),set_status=Mock())
    window.delay_var=Var(str(config.settings.launch_delay_seconds));window.cooldown_var=Var(str(config.settings.duplicate_launch_cooldown_seconds))
    window.theme_var=Var(config.settings.theme);window.remember_var=Var(config.settings.remember_window_position);window.startup_var=Var(config.settings.launch_with_windows)
    window.visual_style_var=Var(config.settings.visual_style)
    window.update_channel_var=Var(config.updates.channel)
    window.update_policy_var=Var(config.updates.policy);window.update_check_var=Var(config.updates.automatically_check);window.update_download_var=Var(config.updates.automatically_download)
    return window


def stale_config(referenced=False):
    config=populated_config();config.browser_profiles["chrome-work"]=BrowserProfile("Chrome Work","chrome",r"C:\Chrome\chrome.exe",r"C:\User Data","Profile 4")
    for site in config.websites: site.browser_profile="chrome-work" if referenced else "system-default"
    return config


@pytest.mark.parametrize("referenced",[False,True])
def test_startup_save_succeeds_with_unrelated_stale_profile_and_warns(referenced):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);exe=root/"WorkLauncher.exe";exe.touch();window=settings_window(stale_config(referenced),root/"config.json",exe);window.startup_var=Var(True)
        with patch("work_launcher.app.set_startup_enabled") as startup,patch("work_launcher.app.save_settings") as save,patch("work_launcher.app.messagebox.showwarning") as warning,patch("work_launcher.app.messagebox.showerror") as error:
            SettingsWindow.save(window)
        startup.assert_called_once_with(True,exe);save.assert_called_once();error.assert_not_called();warning.assert_called_once()
        assert window.master_app.config.settings.launch_with_windows is True


@pytest.mark.parametrize("section",["theme","delay","updates"])
def test_unrelated_section_save_is_independent_of_stale_profile(section):
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);exe=root/"WorkLauncher.exe";exe.touch();window=settings_window(stale_config(),root/"config.json",exe)
        if section=="theme": window.theme_var=Var("dark")
        elif section=="delay": window.delay_var=Var("1.25")
        else: window.update_policy_var=Var("manual")
        with patch("work_launcher.app.save_settings") as save,patch("work_launcher.app.messagebox.showwarning"),patch("work_launcher.app.messagebox.showerror") as error:
            SettingsWindow.save(window)
        save.assert_called_once();error.assert_not_called()


def test_no_change_save_does_not_rewrite_configuration_even_with_stale_profile():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);exe=root/"WorkLauncher.exe";exe.touch();window=settings_window(stale_config(),root/"config.json",exe)
        with patch("work_launcher.app.save_settings") as save,patch("work_launcher.app.set_startup_enabled") as startup,patch("work_launcher.app.messagebox.showwarning"),patch("work_launcher.app.messagebox.showerror") as error:
            SettingsWindow.save(window)
        save.assert_not_called();startup.assert_not_called();error.assert_not_called()


def test_changed_invalid_browser_profile_remains_blocking():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);exe=root/"WorkLauncher.exe";exe.touch();config=default_config();window=settings_window(config,root/"config.json",exe)
        config.browser_profiles["chrome-work"]=BrowserProfile("Broken","chrome",r"C:\missing\chrome.exe",r"C:\missing","Profile 9")
        with patch("work_launcher.app.save_settings") as save,patch("work_launcher.app.messagebox.showerror") as error:
            SettingsWindow.save(window)
        save.assert_not_called();error.assert_called_once()


def test_startup_failure_is_specific_and_does_not_save_preference():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);exe=root/"WorkLauncher.exe";exe.touch();config=stale_config();window=settings_window(config,root/"config.json",exe);window.startup_var=Var(True)
        with patch("work_launcher.app.set_startup_enabled",side_effect=OSError("denied")),patch("work_launcher.app.save_settings") as save,patch("work_launcher.app.messagebox.showerror") as error:
            SettingsWindow.save(window)
        save.assert_not_called();assert config.settings.launch_with_windows is False;assert "Windows startup" in error.call_args.args[1]


def test_exact_post_wizard_duplicate_state_does_not_block_startup_save():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);exe=root/"WorkLauncher.exe";exe.touch();browser=root/"chrome.exe";browser.touch();data=root/"User Data";(data/"Profile 2").mkdir(parents=True)
        config=stale_config();config.browser_profiles["powtoon"]=BrowserProfile("Powtoon","chrome",str(browser),str(data),"Profile 2")
        for site in config.websites: site.browser_profile="powtoon"
        config.setup.completed=True;window=settings_window(config,root/"config.json",exe);window.startup_var=Var(True)
        with patch("work_launcher.app.set_startup_enabled") as startup,patch("work_launcher.app.save_settings") as save,patch("work_launcher.app.messagebox.showwarning") as warning,patch("work_launcher.app.messagebox.showerror") as error:
            SettingsWindow.save(window)
        startup.assert_called_once();save.assert_called_once();error.assert_not_called();warning.assert_called_once()
        assert {site.browser_profile for site in config.websites}=={"powtoon"};assert "chrome-work" in config.browser_profiles
