from __future__ import annotations

import hashlib
import os
import urllib.error
import urllib.request
import urllib.parse
import ssl
import time
from pathlib import Path
from threading import Event
from typing import Callable

from .update_models import ReleaseInfo, UpdateCancelled, UpdateIntegrityError, UpdateNetworkError
from .github_updates import ALLOWED_REDIRECT_HOSTS

DOWNLOAD_TIMEOUT_SECONDS = 30


def updates_dir() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "WorkLauncher" / "Updates"
    root.mkdir(parents=True, exist_ok=True); return root


def cleanup_stale_updates(root: Path | None = None, max_age_days: int = 7) -> int:
    root=(root or updates_dir()).resolve(); cutoff=time.time()-max_age_days*86400; removed=0
    if not root.is_dir(): return 0
    for pattern in ("WorkLauncher-*.exe.part","WorkLauncher-*.exe"):
        for item in root.glob(pattern):
            try:
                if item.is_file() and item.resolve().parent==root and item.stat().st_mtime<cutoff: item.unlink(); removed+=1
            except OSError: pass
    return removed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def verify_download(path: Path, expected_sha256: str, expected_size: int = 0) -> None:
    if not path.is_file(): raise UpdateIntegrityError("Downloaded update file is missing.")
    if expected_size and path.stat().st_size != expected_size: raise UpdateIntegrityError("Downloaded update size does not match the release asset.")
    if sha256_file(path).lower() != expected_sha256.lower(): raise UpdateIntegrityError("Downloaded update failed SHA-256 verification.")


def download_release(release: ReleaseInfo, destination: Path | None = None, progress: Callable[[int, int], None] | None = None,
                     cancel_event: Event | None = None, opener: Callable | None = None) -> Path:
    default_name = f"WorkLauncher-Setup-{release.version}.exe" if release.asset_kind == "installer" else f"WorkLauncher-{release.version}.exe"
    opener = opener or urllib.request.urlopen; destination = destination or (updates_dir() / default_name)
    temporary = destination.with_suffix(destination.suffix + ".part"); destination.parent.mkdir(parents=True, exist_ok=True)
    parsed=urllib.parse.urlparse(release.asset_url)
    if parsed.scheme!="https" or parsed.hostname!="github.com": raise UpdateNetworkError("Update downloads require the configured GitHub HTTPS release asset.")
    request = urllib.request.Request(release.asset_url, headers={"User-Agent": "WorkLauncher-Updater"})
    try:
        with opener(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, temporary.open("wb") as output:
            final_url=response.geturl() if hasattr(response,"geturl") else release.asset_url; final=urllib.parse.urlparse(final_url)
            if final.scheme!="https" or final.hostname not in ALLOWED_REDIRECT_HOSTS: raise UpdateNetworkError("Update download redirected to an insecure or untrusted destination.")
            try: total=int(response.headers.get("Content-Length",release.size or 0))
            except (TypeError,ValueError) as exc: raise UpdateIntegrityError("Download Content-Length is invalid.") from exc
            downloaded = 0
            if total and total != release.size: raise UpdateIntegrityError("Download Content-Length does not match release metadata.")
            while True:
                if cancel_event and cancel_event.is_set(): raise UpdateCancelled("Update download cancelled.")
                chunk = response.read(128 * 1024)
                if not chunk: break
                output.write(chunk); downloaded += len(chunk)
                if progress: progress(downloaded, total)
        verify_download(temporary, release.sha256, release.size or total); os.replace(temporary, destination); return destination
    except UpdateCancelled:
        temporary.unlink(missing_ok=True); raise
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        temporary.unlink(missing_ok=True); raise UpdateNetworkError("Unable to download the update.") from exc
    except Exception:
        temporary.unlink(missing_ok=True); raise
