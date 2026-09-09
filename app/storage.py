"""JSON-file persistence layer.

Every piece of mutable state lives in a small JSON file so the bot survives a
restart and so the whole thing stays trivially testable (point ``Storage`` at a
tmp dir).  All writes are atomic (write temp file + ``os.replace``).
"""

import json
import os
import tempfile
import threading
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# File names --------------------------------------------------------------
SCHEDULE_FILE = "schedule.json"          # read-only weekly template
CONFIG_FILE = "config.json"              # poll time + editable per-day menu
DISHES_FILE = "dishes.json"              # global dish database
HISTORY_FILE = "orders_history.json"     # per-user order history (ISO dates)
POLL_STATE_FILE = "poll_state.json"      # live custom polls + votes
DM_USERS_FILE = "dm_users.json"          # users who started the bot in DM


class Storage:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = base_dir or REPO_ROOT
        os.makedirs(self.base_dir, exist_ok=True)
        self._lock = threading.RLock()

    # -- low level ------------------------------------------------------
    def _path(self, name: str) -> str:
        return os.path.join(self.base_dir, name)

    def _read(self, name: str, default: Any) -> Any:
        path = self._path(name)
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return default

    def _write(self, name: str, data: Any) -> None:
        with self._lock:
            fd, tmp = tempfile.mkstemp(dir=self.base_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self._path(name))
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    # -- schedule (template, read only) ------------------------------
    def load_schedule(self) -> list:
        return self._read(SCHEDULE_FILE, [])

    # -- config (poll time + per-day menu) --------------------------
    def load_config(self) -> dict:
        return self._read(CONFIG_FILE, {})

    def save_config(self, cfg: dict) -> None:
        self._write(CONFIG_FILE, cfg)

    # -- dishes ------------------------------------------------------
    def load_dishes(self) -> dict:
        return self._read(DISHES_FILE, {})

    def save_dishes(self, dishes: dict) -> None:
        self._write(DISHES_FILE, dishes)

    # -- order history --------------------------------------------
    def load_history(self) -> dict:
        return self._read(HISTORY_FILE, {})

    def save_history(self, history: dict) -> None:
        self._write(HISTORY_FILE, history)

    # -- live poll state ----------------------------------------
    def load_poll_state(self) -> dict:
        return self._read(POLL_STATE_FILE, {})

    def save_poll_state(self, state: dict) -> None:
        self._write(POLL_STATE_FILE, state)

    # -- DM users ----------------------------------------------
    def load_dm_users(self) -> dict:
        return self._read(DM_USERS_FILE, {})

    def save_dm_users(self, users: dict) -> None:
        self._write(DM_USERS_FILE, users)
