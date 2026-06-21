"""Performs the HTTP health check against the monitored URL."""
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import requests

# Some servers reject requests with no User-Agent (403), which would
# otherwise be misread as a real outage. A normal browser-like UA avoids
# that false positive.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FUASK-Monitor-Bot/1.0; "
        "+https://github.com/)"
    )
}


@dataclass
class CheckResult:
    timestamp: str
    ok: bool
    status_code: Optional[int]
    latency_ms: Optional[float]
    error: Optional[str]


def _single_attempt(url: str, timeout_seconds: float) -> CheckResult:
    timestamp = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    try:
        response = requests.get(
            url, timeout=timeout_seconds, allow_redirects=True, headers=DEFAULT_HEADERS
        )
        latency_ms = (time.monotonic() - start) * 1000
        ok = 200 <= response.status_code < 400
        return CheckResult(
            timestamp=timestamp,
            ok=ok,
            status_code=response.status_code,
            latency_ms=round(latency_ms, 1),
            error=None,
        )
    except requests.exceptions.Timeout:
        return CheckResult(timestamp, False, None, None, "timeout")
    except requests.exceptions.RequestException as exc:
        # Keep this to the exception type only — full exception text can
        # sometimes echo back request internals, and this is fine for an
        # uptime alert ("connection_error" is all the IT team needs).
        return CheckResult(timestamp, False, None, None, type(exc).__name__)


def check_url(
    url: str,
    timeout_seconds: float,
    retries: int = 1,
    retry_delay_seconds: float = 3.0,
) -> CheckResult:
    """Runs one check, retrying on failure before giving up.

    With alerts now firing on the very first confirmed failure (no more
    waiting for multiple 5-minute cycles), a single dropped packet would
    otherwise look identical to a real outage. This retries within the
    *same* run — a few seconds, not minutes — so a genuine one-off blip
    gets filtered out, while a real outage still gets reported on this
    same cycle, not the next one.
    """
    attempts = retries + 1
    result = None
    for attempt in range(attempts):
        result = _single_attempt(url, timeout_seconds)
        if result.ok:
            return result
        if attempt < attempts - 1:
            time.sleep(retry_delay_seconds)
    return result
