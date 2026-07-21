import json
import os
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import pytest

from work_launcher.app import SettingsWindow, WorkLauncherApp
from work_launcher.config import WebsiteConfig, config_to_dict, default_config, load_config, write_config
from work_launcher.diagnostics_bundle import create_diagnostics_bundle


def make_config(path: Path, count: int = 0):
    config = default_config(); config.setup.completed = True
    config.websites = [WebsiteConfig(f"Site {index}", f"https://example.com/{index}", browser_profile="system-default")
                       for index in range(count)]
    write_config(path, config); return config


def test_interrupted_valid_configuration_write_is_recovered(tmp_path):
    path = tmp_path / "config.json"; config = make_config(path)
    config.settings.theme = "dark"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config_to_dict(config)), encoding="utf-8")
    future = time.time() + 2
    os.utime(temporary, (future, future))
    loaded, warnings = load_config(path)
    assert loaded.settings.theme == "dark"
    assert any("interrupted" in value for value in warnings)


def test_diagnostics_bundle_excludes_urls_and_application_paths(tmp_path):
    config = default_config(); config.websites.append(WebsiteConfig("Secret", "https://secret.example/path", browser_profile="system-default"))
    bundle = create_diagnostics_bundle(config, tmp_path / "diagnostics.zip")
    import zipfile
    with zipfile.ZipFile(bundle) as archive: summary = archive.read("summary.json").decode()
    assert "secret.example" not in summary
    assert '"websites": 1' in summary


def test_dashboard_paginates_and_collapses_navigation(tmp_path):
    path = tmp_path / "config.json"; make_config(path, 120)
    try: app = WorkLauncherApp(path, safe_mode=True)
    except tk.TclError: pytest.skip("Tk is unavailable")
    try:
        app.update(); assert len(app.displayed_websites) == 50
        app.change_website_page(1); assert app.website_page == 1 and len(app.displayed_websites) == 50
        app.geometry("900x700"); app.update(); assert app.sidebar.winfo_width() == 64
    finally: app.destroy()


def test_settings_uses_categorized_notebook(tmp_path):
    path = tmp_path / "config.json"; make_config(path)
    try: app = WorkLauncherApp(path, safe_mode=True)
    except tk.TclError: pytest.skip("Tk is unavailable")
    try:
        app.update(); settings = SettingsWindow(app); app.update()
        notebook = next(child for child in settings.winfo_children() if isinstance(child, ttk.Notebook))
        assert [notebook.tab(tab, "text") for tab in notebook.tabs()] == ["Websites", "Browser Profiles", "General", "Updates"]
        settings.destroy()
    finally: app.destroy()
