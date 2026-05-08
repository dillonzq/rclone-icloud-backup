"""
Persistent application state stored as JSON on disk.
"""

import json

from .config import STATE_FILE, log


class AppState:
    """Application state persisted to disk."""

    def __init__(self):
        self.data = {
            "last_backup": None,
            "last_backup_files": 0,
            "last_backup_errors": 0,
            "auth_valid": None,
            "last_auth_check": None,
            "pending_2fa": False,
        }
        self._load()

    def _load(self):
        if STATE_FILE.exists():
            try:
                self.data.update(json.loads(STATE_FILE.read_text()))
            except Exception:
                pass

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.data, indent=2))

    def set_pending_2fa(self, value: bool):
        self.data["pending_2fa"] = value
        self.save()

    @property
    def pending_2fa(self) -> bool:
        return self.data.get("pending_2fa", False)


# Singleton instance – import this wherever state is needed
state = AppState()
