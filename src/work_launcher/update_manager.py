from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import AppConfig, save_config
from .github_updates import GitHubReleaseClient
from .installation import installation_kind
from .update_models import ReleaseInfo, is_newer, parse_version
from .version import __version__


class UpdateManager:
    def __init__(self, config: AppConfig, config_path: Path, client: GitHubReleaseClient | None = None):
        self.config, self.config_path, self.client = config, config_path, client or GitHubReleaseClient(); self.checked_this_session = False; self.latest: ReleaseInfo | None = None; self.last_error: str = ""
        self.config.updates.installation_kind = installation_kind()

    def due(self, now: datetime | None = None) -> bool:
        if not self.config.updates.owner.strip() or not self.config.updates.repository.strip(): return False
        if not self.config.updates.automatically_check or self.config.updates.policy == "manual": return False
        if self.checked_this_session: return False
        if not self.config.updates.last_checked: return True
        try: previous = datetime.fromisoformat(self.config.updates.last_checked)
        except ValueError: return True
        now = now or datetime.now(timezone.utc)
        if previous.tzinfo is None: previous = previous.replace(tzinfo=timezone.utc)
        return now - previous >= timedelta(hours=24)

    def check(self, force: bool = False) -> ReleaseInfo | None:
        if self.checked_this_session and not force: return self.latest
        logging.info("Checking GitHub releases: channel=%s", self.config.updates.channel)
        try:
            self.last_error = ""
            release = self.client.check(self.config.updates.owner, self.config.updates.repository, self.config.updates.channel, self.config.updates.installation_kind)
            if parse_version(__version__) < parse_version(release.minimum_supported_version): release=replace(release,mandatory=True)
            self.checked_this_session = True; self.latest = release
            self.config.updates.last_checked = datetime.now(timezone.utc).isoformat(timespec="seconds"); save_config(self.config_path, self.config)
            if is_newer(release.version, __version__): logging.info("New version detected: %s", release.version); return release
            logging.info("Work Launcher is up to date: %s", __version__); return None
        except Exception as exc:
            self.last_error = str(exc)
            raise

    def snapshot(self) -> dict[str, object]:
        release = self.latest
        last_checked = self.config.updates.last_checked or "Never"
        next_check = "Manual"
        if self.config.updates.policy != "manual" and self.config.updates.automatically_check:
            if not self.config.updates.last_checked:
                next_check = "Due now"
            else:
                try:
                    previous = datetime.fromisoformat(self.config.updates.last_checked)
                    if previous.tzinfo is None: previous = previous.replace(tzinfo=timezone.utc)
                    due_at = previous + timedelta(hours=24)
                    now = datetime.now(timezone.utc)
                    next_check = "Due now" if now >= due_at else f"Due {due_at.isoformat(timespec='seconds')}"
                except ValueError:
                    next_check = "Due now"
        return {
            "provider": self.config.updates.provider,
            "owner": self.config.updates.owner,
            "repository": self.config.updates.repository,
            "channel": self.config.updates.channel,
            "policy": self.config.updates.policy,
            "automatically_check": self.config.updates.automatically_check,
            "automatically_download": self.config.updates.automatically_download,
            "installation_kind": self.config.updates.installation_kind,
            "last_checked": last_checked,
            "next_check": next_check,
            "skipped_version": self.config.updates.skipped_version or "None",
            "checked_this_session": self.checked_this_session,
            "latest_version": release.version if release else "Unknown",
            "latest_release_date": release.release_date if release else "Unknown",
            "latest_mandatory": release.mandatory if release else False,
            "latest_asset_kind": release.asset_kind if release else "Unknown",
            "latest_asset_name": release.asset_name if release else "Unknown",
            "latest_asset_url": release.asset_url if release else "Unknown",
            "latest_sha256": release.sha256 if release else "Unknown",
            "latest_size": release.size if release else 0,
            "latest_notes": list(release.release_notes) if release else [],
            "last_error": self.last_error or "None",
        }
