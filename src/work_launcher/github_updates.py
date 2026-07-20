from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Callable

from .update_models import ReleaseInfo, UpdateMetadataError, UpdateNetworkError, parse_version

API_TIMEOUT_SECONDS = 15
ALLOWED_REDIRECT_HOSTS = {"api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")
TOP_LEVEL_FIELDS = {"version","release_date","channel","minimum_supported_version","mandatory","download","size","sha256","release_notes"}
ASSET_NAMES = {"portable":"WorkLauncher.exe","installer":"WorkLauncher-Setup.exe"}


def _require_exact_keys(value: dict, required: set[str], allowed: set[str], label: str) -> None:
    missing=required-set(value); extra=set(value)-allowed
    if missing: raise UpdateMetadataError(f"{label} is missing required fields: {', '.join(sorted(missing))}")
    if extra: raise UpdateMetadataError(f"{label} contains unsupported fields: {', '.join(sorted(extra))}")


def validate_release_metadata(metadata, *, channel: str, tag_name: str, assets: dict[str,dict]) -> tuple[str,str,str,int]:
    if not isinstance(metadata,dict): raise UpdateMetadataError("release.json must contain an object.")
    _require_exact_keys(metadata,TOP_LEVEL_FIELDS,TOP_LEVEL_FIELDS,"release.json")
    if not all(isinstance(metadata[key],str) for key in ("version","release_date","channel","minimum_supported_version")):
        raise UpdateMetadataError("Version, release date, channel, and minimum version must be text.")
    if metadata["version"].startswith("v") or metadata["minimum_supported_version"].startswith("v"): raise UpdateMetadataError("release.json versions must not include a v prefix.")
    version=parse_version(metadata["version"]); minimum=parse_version(metadata["minimum_supported_version"])
    if minimum>version: raise UpdateMetadataError("minimum_supported_version cannot exceed the release version.")
    try: date.fromisoformat(metadata["release_date"])
    except ValueError as exc: raise UpdateMetadataError("release_date must be YYYY-MM-DD.") from exc
    if metadata["channel"] not in {"stable","beta"} or (channel=="stable" and metadata["channel"]!="stable"): raise UpdateMetadataError("release.json channel does not match the selected channel.")
    if channel=="stable" and version.prerelease: raise UpdateMetadataError("Stable releases cannot use prerelease versions.")
    if tag_name != f"v{metadata['version']}": raise UpdateMetadataError("GitHub tag and release.json version do not match.")
    if type(metadata["mandatory"]) is not bool: raise UpdateMetadataError("mandatory must be true or false.")
    for name in ("download","size","sha256"):
        if not isinstance(metadata[name],dict): raise UpdateMetadataError(f"{name} must be an object.")
        _require_exact_keys(metadata[name],{"portable"},{"portable","installer"},name)
    if set(metadata["download"]) != set(metadata["size"]) or set(metadata["download"]) != set(metadata["sha256"]):
        raise UpdateMetadataError("download, size, and sha256 entries must have identical release types.")
    for kind,asset_name in metadata["download"].items():
        if type(asset_name) is not str or asset_name != ASSET_NAMES[kind]: raise UpdateMetadataError(f"Unsafe or unsupported {kind} asset name.")
        if asset_name not in assets: raise UpdateMetadataError(f"Release is missing {asset_name}.")
        size=metadata["size"][kind]; checksum=metadata["sha256"][kind]
        if type(size) is not int or size <= 0 or size != assets[asset_name].get("size"): raise UpdateMetadataError(f"{asset_name} size does not match GitHub metadata.")
        if type(checksum) is not str or not re.fullmatch(r"[0-9a-f]{64}",checksum): raise UpdateMetadataError(f"{asset_name} has an invalid SHA-256 value.")
    notes=metadata["release_notes"]
    if not isinstance(notes,list) or len(notes)>100 or not all(isinstance(note,str) and len(note)<=2000 for note in notes): raise UpdateMetadataError("release_notes must be a bounded list of text entries.")
    return metadata["version"],metadata["minimum_supported_version"],metadata["channel"],len(notes)


class GitHubReleaseClient:
    def __init__(self, opener: Callable | None = None, api_base: str = "https://api.github.com"):
        self.opener=opener or urllib.request.urlopen; self.api_base=api_base.rstrip("/")

    def _get(self,url: str) -> bytes:
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme!="https" or parsed.hostname not in ALLOWED_REDIRECT_HOSTS: raise UpdateMetadataError("Update URL uses an untrusted host or insecure scheme.")
        request=urllib.request.Request(url,headers={"Accept":"application/vnd.github+json","User-Agent":"WorkLauncher/1 UpdateClient"})
        try:
            with self.opener(request,timeout=API_TIMEOUT_SECONDS) as response:
                final_url=response.geturl() if hasattr(response,"geturl") else url; final=urllib.parse.urlparse(final_url)
                if final.scheme!="https" or final.hostname not in ALLOWED_REDIRECT_HOSTS: raise UpdateNetworkError("GitHub redirected to an insecure or untrusted destination.")
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {403,429}: raise UpdateNetworkError("GitHub rate limit reached. Try again later.") from exc
            if exc.code==404: raise UpdateNetworkError("No GitHub release was found.") from exc
            raise UpdateNetworkError(f"GitHub returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError,TimeoutError,ssl.SSLError,OSError) as exc: raise UpdateNetworkError("Unable to check for updates. Please verify your Internet connection.") from exc

    def _json(self,url: str):
        try: return json.loads(self._get(url).decode("utf-8"))
        except (json.JSONDecodeError,UnicodeError) as exc: raise UpdateMetadataError("GitHub returned invalid JSON metadata.") from exc

    def _release_asset_url(self,owner: str,repository: str,asset: dict) -> str:
        url=asset.get("browser_download_url","")
        prefix=f"https://github.com/{owner}/{repository}/releases/download/"
        if not isinstance(url,str) or not url.startswith(prefix): raise UpdateMetadataError("Release asset URL does not belong to the configured repository.")
        return url

    def check(self,owner: str,repository: str,channel: str="stable",installation_kind: str="portable") -> ReleaseInfo:
        if not REPOSITORY_PART.fullmatch(owner) or not REPOSITORY_PART.fullmatch(repository): raise UpdateMetadataError("Configure a valid GitHub owner and repository in Settings.")
        root=f"{self.api_base}/repos/{owner}/{repository}/releases"
        if channel=="stable": release=self._json(root+"/latest")
        elif channel=="beta":
            releases=[]; page=1
            while True:
                batch=self._json(root+f"?per_page=100&page={page}")
                if not isinstance(batch,list): raise UpdateMetadataError("Invalid GitHub releases response.")
                releases.extend(batch)
                if len(batch)<100: break
                page+=1
                if page>10: raise UpdateMetadataError("Too many GitHub release pages.")
            candidates=[]
            for item in releases:
                if not isinstance(item,dict) or item.get("draft"): continue
                try: candidates.append((parse_version(str(item.get("tag_name",""))),item))
                except UpdateMetadataError: continue
            if not candidates: raise UpdateMetadataError("No release is available for this channel.")
            release=max(candidates,key=lambda pair:pair[0])[1]
        else: raise UpdateMetadataError("Unsupported update channel.")
        if not isinstance(release,dict) or release.get("draft"): raise UpdateMetadataError("Draft releases cannot be installed.")
        raw_assets=release.get("assets",[])
        if not isinstance(raw_assets,list): raise UpdateMetadataError("GitHub release assets must be a list.")
        names=[item.get("name") for item in raw_assets if isinstance(item,dict)]
        if len(names)!=len(set(names)): raise UpdateMetadataError("GitHub release contains duplicate asset names.")
        assets={item.get("name"):item for item in raw_assets if isinstance(item,dict) and isinstance(item.get("name"),str)}
        if "release.json" not in assets or "SHA256SUMS.txt" not in assets or "Updater.exe" not in assets:
            raise UpdateMetadataError("Release is missing release.json, SHA256SUMS.txt, or Updater.exe.")
        metadata=self._json(self._release_asset_url(owner,repository,assets["release.json"]))
        version,minimum,_,_=validate_release_metadata(metadata,channel=channel,tag_name=str(release.get("tag_name","")),assets=assets)
        if installation_kind not in {"portable", "installer"}: raise UpdateMetadataError("Unsupported installation type.")
        if installation_kind not in metadata["download"]:
            raise UpdateMetadataError(f"This release does not contain the required {installation_kind} update asset.")
        selected_kind=installation_kind
        asset_name=metadata["download"][selected_kind]; expected=metadata["sha256"][selected_kind].lower(); expected_size=metadata["size"][selected_kind]
        try: sums=self._get(self._release_asset_url(owner,repository,assets["SHA256SUMS.txt"])).decode("utf-8",errors="strict")
        except UnicodeError as exc: raise UpdateMetadataError("SHA256SUMS.txt is not valid UTF-8 text.") from exc
        entries={};
        for line in sums.splitlines():
            parts=line.split(maxsplit=1)
            if len(parts)!=2 or not re.fullmatch(r"[0-9a-fA-F]{64}",parts[0]): continue
            name=parts[1].lstrip("* ")
            if name in entries: raise UpdateMetadataError("SHA256SUMS.txt contains duplicate asset names.")
            entries[name]=parts[0].lower()
        if entries.get(asset_name)!=expected: raise UpdateMetadataError("release.json and SHA256SUMS.txt do not agree.")
        updater_checksum = entries.get("Updater.exe", "")
        updater_size = assets["Updater.exe"].get("size")
        if not re.fullmatch(r"[0-9a-f]{64}", updater_checksum) or type(updater_size) is not int or updater_size <= 0:
            raise UpdateMetadataError("Updater.exe is missing valid checksum or size metadata.")
        asset_url=self._release_asset_url(owner,repository,assets[asset_name])
        updater_url=self._release_asset_url(owner,repository,assets["Updater.exe"])
        return ReleaseInfo(version,metadata["release_date"],minimum,metadata["mandatory"],asset_name,asset_url,expected,expected_size,
            tuple(metadata["release_notes"]),str(release.get("html_url","")),selected_kind,
            "Updater.exe", updater_url, updater_checksum, updater_size)
