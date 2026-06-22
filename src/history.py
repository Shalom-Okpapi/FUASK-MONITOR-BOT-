"""Persists monitor state across GitHub Actions runs."""
import json
import os
import tempfile
from dataclasses import dataclass, asdict, field
from typing import List, Optional

HISTORY_PATH = "data/status_history.json"


@dataclass
class State:
    pages_down: List[str] = field(default_factory=list)
    pages_slow_alerted: List[str] = field(default_factory=list)
    last_heartbeat_at: Optional[str] = None


def load_state(path: str = HISTORY_PATH) -> State:
    if not os.path.exists(path):
        return State()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Filter out any fields that don't exist in the current State dataclass.
    # This means old state files (saved before a code change) load cleanly
    # instead of crashing with "unexpected keyword argument".
    valid_fields = {f.name for f in State.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return State(**filtered)


def save_state(state: State, path: str = HISTORY_PATH) -> None:
    dir_name = os.path.dirname(path) or "."
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
