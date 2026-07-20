from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class HealthResult:
    origin: str
    reachable: bool
    status: str
    elapsed_seconds: float


def check_url(url: str, timeout: float = 5.0, opener=None) -> HealthResult:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    started = time.monotonic()
    request = urllib.request.Request(origin, method="HEAD", headers={"User-Agent": "WorkLauncher-HealthCheck"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=timeout) as response:
            code = getattr(response, "status", 200)
            return HealthResult(origin, code < 500, f"HTTP {code}", time.monotonic() - started)
    except urllib.error.HTTPError as exc:
        return HealthResult(origin, exc.code < 500, f"HTTP {exc.code}", time.monotonic() - started)
    except ssl.SSLError:
        return HealthResult(origin, False, "certificate failure", time.monotonic() - started)
    except urllib.error.URLError as exc:
        reason = "DNS or connection failure"
        if isinstance(exc.reason, TimeoutError):
            reason = "timed out"
        return HealthResult(origin, False, reason, time.monotonic() - started)
    except TimeoutError:
        return HealthResult(origin, False, "timed out", time.monotonic() - started)
