from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig, config_to_dict, validate_config_data


@dataclass(frozen=True)
class RepairIssue:
    kind: str
    name: str
    detail: str


def find_repair_issues(config: AppConfig) -> list[RepairIssue]:
    issues = []
    for profile_id, profile in config.browser_profiles.items():
        if profile.type != "system" and (not profile.executable_path or not Path(profile.executable_path).is_file()):
            issues.append(RepairIssue("profile", profile.name, f"Browser executable is unavailable ({profile_id})"))
    for site in config.websites:
        if site.browser_profile not in config.browser_profiles: issues.append(RepairIssue("profile", site.name, "Missing browser profile"))
        if site.icon_path and not site.icon_path.startswith("builtin:") and not Path(site.icon_path).is_file(): issues.append(RepairIssue("icon", site.name, "Custom icon is missing"))
    for app in config.applications:
        if not Path(app.path).expanduser().is_file(): issues.append(RepairIssue("application", app.name, "Application or document is missing"))
    valid = {f"website:{v.name}" for v in config.websites} | {f"application:{v.name}" for v in config.applications}
    for preset in config.presets:
        for reference in preset.items:
            if reference not in valid: issues.append(RepairIssue("preset", preset.name, f"Missing item: {reference}"))
    return issues


def export_transfer(config: AppConfig, path: Path) -> None:
    payload = {"format": "work-launcher-transfer-v1", "config": config_to_dict(config)}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def import_transfer(path: Path) -> tuple[AppConfig, list[RepairIssue]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != "work-launcher-transfer-v1": raise ValueError("Not a Work Launcher transfer package")
    config = validate_config_data(data["config"])
    return config, find_repair_issues(config)


def verify_organization_package(path: Path, public_key_path: Path) -> dict:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    envelope = json.loads(path.read_text(encoding="utf-8"))
    payload = base64.b64decode(envelope["payload"], validate=True); signature = base64.b64decode(envelope["signature"], validate=True)
    key = serialization.load_pem_public_key(public_key_path.read_bytes())
    key.verify(signature, payload, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())
    data = json.loads(payload.decode("utf-8"))
    if data.get("format") != "work-launcher-organization-v1": raise ValueError("Unsupported organization package")
    return data


def public_key_fingerprint(public_key_path: Path) -> str:
    from cryptography.hazmat.primitives import serialization
    key = serialization.load_pem_public_key(public_key_path.read_bytes())
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def merge_organization_package(config: AppConfig, package: dict) -> AppConfig:
    result = copy.deepcopy(config); incoming = validate_config_data(package["config"])
    existing_sites = {item.name.casefold() for item in result.websites}
    result.websites.extend(item for item in incoming.websites if item.name.casefold() not in existing_sites)
    existing_apps = {item.name.casefold() for item in result.applications}
    result.applications.extend(item for item in incoming.applications if item.name.casefold() not in existing_apps)
    existing_presets = {item.name.casefold() for item in result.presets}
    result.presets.extend(item for item in incoming.presets if item.name.casefold() not in existing_presets)
    existing_schedules = {item.name.casefold() for item in result.schedules}
    result.schedules.extend(item for item in incoming.schedules if item.name.casefold() not in existing_schedules)
    for key, profile in incoming.browser_profiles.items(): result.browser_profiles.setdefault(key, profile)
    return result


def stage_rollback(current_executable: Path, updates_root: Path) -> tuple[Path, str, int]:
    backup = current_executable.with_suffix(current_executable.suffix + ".bak")
    if not backup.is_file(): raise FileNotFoundError("No previous portable version backup is available.")
    updates_root.mkdir(parents=True, exist_ok=True); target = updates_root / "WorkLauncher-rollback.exe"
    shutil.copy2(backup, target); content = target.read_bytes()
    return target, hashlib.sha256(content).hexdigest(), len(content)
