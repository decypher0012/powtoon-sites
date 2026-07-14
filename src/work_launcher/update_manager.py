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
        self.config, self.config_path, self.client = config, config_path, client or GitHubReleaseClient(); self.checked_this_session = False; self.latest: ReleaseInfo | None = None
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
        release = self.client.check(self.config.updates.owner, self.config.updates.repository, self.config.updates.channel, self.config.updates.installation_kind)
        if parse_version(__version__) < parse_version(release.minimum_supported_version): release=replace(release,mandatory=True)
        self.checked_this_session = True; self.latest = release
        self.config.updates.last_checked = datetime.now(timezone.utc).isoformat(timespec="seconds"); save_config(self.config_path, self.config)
        if is_newer(release.version, __version__): logging.info("New version detected: %s", release.version); return release
        logging.info("Work Launcher is up to date: %s", __version__); return None
