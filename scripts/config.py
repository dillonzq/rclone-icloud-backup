"""
Configuration from environment variables and shared constants.
"""

import logging
import os
import sys
from pathlib import Path

# ---- Apple / iCloud ----
APPLE_ID = os.environ.get("APPLE_ID", "")
APPLE_PASSWORD = os.environ.get("APPLE_PASSWORD", "")
APPLE_PASSWORD_OBSCURED = os.environ.get("APPLE_PASSWORD_OBSCURED", "")

RCLONE_REMOTE = os.environ.get("RCLONE_REMOTE", "icloudphotos")
ICLOUD_SERVICE = os.environ.get("ICLOUD_SERVICE", "photos")

# ---- Backup ----
BACKUP_DIR = os.environ.get("BACKUP_DIR", "/data/backup")
RCLONE_SOURCE = os.environ.get("RCLONE_SOURCE", "")  # default "" = root with all libraries
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")
MAX_TRANSFER = os.environ.get("MAX_TRANSFER", "")  # e.g. "500M", "1G"
INIT_AUTO = os.environ.get("INIT_AUTO", "false").lower() in ("true", "1", "yes")
SORT_BY_DATE = os.environ.get("SORT_BY_DATE", "true").lower() in ("true", "1", "yes")

# ---- Scheduling ----
BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "6"))
AUTH_CHECK_INTERVAL_MINUTES = int(os.environ.get("AUTH_CHECK_INTERVAL_MINUTES", "60"))
FIRST_BACKUP_DELAY_MINUTES = int(os.environ.get("FIRST_BACKUP_DELAY_MINUTES", "5"))

# ---- Telegram ----
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---- Paths ----
RCLONE_CONFIG_DIR = Path(os.environ.get("RCLONE_CONFIG_DIR", "/config/rclone"))
RCLONE_CONFIG_FILE = Path(os.environ.get("RCLONE_CONFIG", str(RCLONE_CONFIG_DIR / "rclone.conf")))
RCLONE_CONFIG_DIR = RCLONE_CONFIG_FILE.parent
STATE_FILE = Path(os.environ.get("STATE_FILE", str(Path(BACKUP_DIR) / ".icloud-bkp-state.json")))

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("icloud-bkp")
