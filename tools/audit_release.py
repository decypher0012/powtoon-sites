from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"src"))
from work_launcher.github_updates import validate_release_metadata

ALLOWED={"WorkLauncher.exe","Updater.exe","SHA256SUMS.txt","release.json","WorkLauncher-Setup.exe"}
PROHIBITED_NAMES={"config.json",".env","cookies","history","login data","web data"}
TOKEN_PATTERNS=[re.compile(pattern,re.I) for pattern in (rb"ghp_[A-Za-z0-9]{20,}",rb"github_token\s*=",rb"C:\\Users\\decyp",rb"X:\\powtoon-sites")]
for local_value in (os.environ.get("USERPROFILE",""),str(ROOT)):
    if local_value: TOKEN_PATTERNS.append(re.compile(re.escape(local_value.encode("utf-8")),re.I))


def digest(path: Path) -> str:
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): value.update(chunk)
    return value.hexdigest()


def audit(dist: Path) -> None:
    files=[item for item in dist.iterdir() if item.is_file()]
    names={item.name for item in files}; required={"WorkLauncher.exe","Updater.exe","SHA256SUMS.txt","release.json"}
    if not required<=names: raise RuntimeError(f"Missing release files: {sorted(required-names)}")
    if names-ALLOWED: raise RuntimeError(f"Unexpected release files: {sorted(names-ALLOWED)}")
    if any(item.name.lower() in PROHIBITED_NAMES for item in files): raise RuntimeError("Release contains a prohibited file name.")
    for item in files:
        data=item.read_bytes()
        for pattern in TOKEN_PATTERNS:
            if pattern.search(data): raise RuntimeError(f"Release contains a prohibited personal path or credential pattern in {item.name}.")
    metadata=json.loads((dist/"release.json").read_text(encoding="utf-8")); assets={name:{"size":(dist/name).stat().st_size} for name in names}
    validate_release_metadata(metadata,channel=metadata.get("channel",""),tag_name=f"v{metadata.get('version','')}",assets=assets)
    sums={}
    for line in (dist/"SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        checksum,name=line.split(maxsplit=1); name=name.lstrip("* ")
        if name in sums: raise RuntimeError("Duplicate checksum asset name.")
        sums[name]=checksum.lower()
    expected={name for name in names if name.lower().endswith(".exe")}
    if set(sums)!=expected: raise RuntimeError("Checksum manifest and executable assets differ.")
    for name in expected:
        if not re.fullmatch(r"[0-9a-f]{64}",sums[name]) or digest(dist/name)!=sums[name]: raise RuntimeError(f"Checksum failed for {name}.")
    for kind,name in metadata["download"].items():
        if metadata["sha256"][kind]!=sums[name] or metadata["size"][kind]!=(dist/name).stat().st_size: raise RuntimeError(f"Metadata disagrees for {name}.")


if __name__=="__main__":
    audit(ROOT/"dist"); print("Release content audit passed.")
