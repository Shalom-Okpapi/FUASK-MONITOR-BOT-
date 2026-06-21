"""Persists monitor state across GitHub Actions runs.

Runners are ephemeral — nothing survives in memory between scheduled runs —
so state (current status, consecutive failure count, whether a latency
alert has already fired) lives in a JSON file that the workflow commits
back to the repo after every run. Writes are atomic (write-to-temp +
os.replace) so a crash mid-write can never corrupt the file.
"""
import json
import os
import tempfile
from dataclasses import dataclass, asdict
from typing import Optional

HISTORY_PATH = "data/status_history.json"


@dataclass
class State:
    last_status: str  # "up" | "down" | "unknown"
    consecutive_failures: int
    last_latency_alert_sent: bool
    # ISO timestamp of the last "all good" heartbeat sent, or None if one
    # has never been sent yet. Optional with a default so old state files
    # (saved before this field existed) still load without errors.
    last_heartbeat_at: Optional[str] = None


def load_state(path: str = HISTORY_PATH) -> State:
    if not os.path.exists(path):
        return State(last_status="unknown", consecutive_failures=0,
                     last_latency_alert_sent=False)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return State(**data)


def save_state(state: State, path: str = HISTORY_PATH) -> None:
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)
        os.replace(tmp_path, path)  # atomic on POSIX and Windows
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
