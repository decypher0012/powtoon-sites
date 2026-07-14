from __future__ import annotations

from dataclasses import dataclass
import re
from functools import total_ordering


class UpdateError(RuntimeError): pass
class UpdateNetworkError(UpdateError): pass
class UpdateMetadataError(UpdateError): pass
class UpdateIntegrityError(UpdateError): pass
class UpdateCancelled(UpdateError): pass


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    release_date: str
    minimum_supported_version: str
    mandatory: bool
    asset_name: str
    asset_url: str
    sha256: str
    size: int
    release_notes: tuple[str, ...]
    html_url: str = ""
    asset_kind: str = "portable"


SEMVER = re.compile(r"^(?:v)?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")


@total_ordering
@dataclass(frozen=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    def __lt__(self, other):
        if not isinstance(other, SemanticVersion): return NotImplemented
        core_self, core_other = (self.major,self.minor,self.patch), (other.major,other.minor,other.patch)
        if core_self != core_other: return core_self < core_other
        if not self.prerelease: return False
        if not other.prerelease: return True
        for left,right in zip(self.prerelease,other.prerelease):
            if left == right: continue
            left_num,right_num=left.isdigit(),right.isdigit()
            if left_num and right_num: return int(left)<int(right)
            if left_num != right_num: return left_num
            return left<right
        return len(self.prerelease)<len(other.prerelease)


def parse_version(value: str) -> SemanticVersion:
    match=SEMVER.fullmatch(value.strip())
    if not match: raise UpdateMetadataError(f"Invalid semantic version: {value}")
    prerelease=tuple(match.group(4).split(".")) if match.group(4) else ()
    if any(part.isdigit() and len(part)>1 and part.startswith("0") for part in prerelease): raise UpdateMetadataError(f"Invalid semantic version: {value}")
    return SemanticVersion(int(match.group(1)),int(match.group(2)),int(match.group(3)),prerelease)


def version_tuple(value: str) -> tuple[int, int, int]:
    version=parse_version(value); return version.major,version.minor,version.patch


def is_newer(candidate: str, current: str) -> bool: return parse_version(candidate) > parse_version(current)
