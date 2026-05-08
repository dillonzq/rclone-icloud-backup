"""
Post-backup reorganization: move files into YYYY/MM/DD/ folders
based on iCloud Photos ``added-time`` metadata.
"""

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .config import BACKUP_DIR, ICLOUD_SERVICE, RCLONE_REMOTE, RCLONE_SOURCE, log

STAGING_DIR = Path(BACKUP_DIR) / ".staging"


def reorganize_by_date() -> tuple[int, int]:
    """
    List all files via rclone lsjson --metadata, then move them
    from the staging directory into ``YYYY/MM/DD/filename``
    under BACKUP_DIR.

    Returns (moved, errors).
    """
    if not STAGING_DIR.exists():
        log.info("No staging directory – nothing to reorganize")
        return 0, 0

    log.info("Fetching metadata for date-based reorganization...")

    # 1. Get file listing with metadata from rclone
    args = [
        "rclone", "lsjson",
        f"{RCLONE_REMOTE}:{RCLONE_SOURCE}",
        "--iclouddrive-service", ICLOUD_SERVICE,
        "--metadata",
        "--recursive",
        "--files-only",
        "--no-mimetype",
    ]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutError:
        log.error("rclone lsjson timed out")
        return 0, 0
    except Exception as e:
        log.error("rclone lsjson failed: %s", e)
        return 0, 0

    if proc.returncode != 0:
        log.error("rclone lsjson failed: %s", proc.stderr[:500])
        return 0, 0

    try:
        entries = json.loads(proc.stdout)
    except json.JSONDecodeError:
        log.error("Failed to parse rclone lsjson output")
        return 0, 0

    log.info("Got metadata for %d files", len(entries))

    # 2. Build mapping: staging_path → YYYY/MM/DD/filename
    moved = 0
    errors = 0

    for entry in entries:
        path = entry.get("Path", "")
        if not path:
            continue

        staging_file = STAGING_DIR / path
        if not staging_file.exists():
            continue  # wasn't downloaded (e.g. --max-transfer limit)

        # Parse added-time
        added_raw = entry.get("Metadata", {}).get("added-time", "")
        try:
            # RFC 3339: "2006-01-02T15:04:05Z" or "2006-01-02T15:04:05+00:00"
            added_raw = added_raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(added_raw)
        except (ValueError, TypeError):
            # Fall back to file mtime
            mtime = staging_file.stat().st_mtime
            dt = datetime.fromtimestamp(mtime)

        date_dir = f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}"
        dest_dir = Path(BACKUP_DIR) / date_dir
        dest_file = dest_dir / staging_file.name

        # Skip if destination already exists (incremental safety)
        if dest_file.exists():
            staging_file.unlink()  # remove staging copy
            continue

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging_file), str(dest_file))
            moved += 1
        except Exception as e:
            log.error("Failed to move %s: %s", staging_file, e)
            errors += 1

    # 3. Clean up empty staging directories
    _remove_empty_dirs(STAGING_DIR)

    log.info("Reorganization done: %d moved, %d errors", moved, errors)
    return moved, errors


def _remove_empty_dirs(root: Path):
    """Recursively remove empty directories under root."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirpath == str(root):
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
        except OSError:
            pass
