"""
Date-sorted backup: download directly to YYYY/MM/DD/ folders
without a staging directory (safe for 2+ TB libraries).
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from .config import BACKUP_DIR, ICLOUD_SERVICE, RCLONE_REMOTE, RCLONE_SOURCE, MAX_TRANSFER, log

# How many parallel copyto transfers
PARALLEL_TRANSFERS = 8

SIZE_UNITS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "KI": 1024,
    "KIB": 1024,
    "M": 1024 ** 2,
    "MB": 1024 ** 2,
    "MI": 1024 ** 2,
    "MIB": 1024 ** 2,
    "G": 1024 ** 3,
    "GB": 1024 ** 3,
    "GI": 1024 ** 3,
    "GIB": 1024 ** 3,
    "T": 1024 ** 4,
    "TB": 1024 ** 4,
    "TI": 1024 ** 4,
    "TIB": 1024 ** 4,
    "P": 1024 ** 5,
    "PB": 1024 ** 5,
    "PI": 1024 ** 5,
    "PIB": 1024 ** 5,
}


def _parse_size_bytes(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None

    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z]*)", text)
    if not match:
        return None

    number, unit = match.groups()
    multiplier = SIZE_UNITS.get(unit.upper())
    if multiplier is None:
        return None
    return int(float(number) * multiplier)


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _has_valid_max_transfer() -> bool:
    return bool(MAX_TRANSFER) and _parse_size_bytes(MAX_TRANSFER) is not None


def _split_remote_path(path: str) -> tuple[str, str]:
    """Split an rclone path into parent and file name without touching encoded slashes."""
    if "/" not in path:
        return "", path
    parent, name = path.rsplit("/", 1)
    return parent, name


def _join_remote_path(root: str, path: str) -> str:
    root = root.strip("/")
    path = path.lstrip("/")
    if not root:
        return path
    if not path:
        return root
    return f"{root}/{path}"


def _should_retry_from_parent(stderr_text: str) -> bool:
    return (
        "directory not found" in stderr_text
        and "error reading source root directory" in stderr_text
    )


def _limit_tasks_by_max_transfer(
    tasks: list[tuple[str, str, int]],
) -> tuple[list[tuple[str, str, int]], bool, int, int]:
    max_bytes = _parse_size_bytes(MAX_TRANSFER)
    if not MAX_TRANSFER:
        return tasks, False, sum(max(0, size) for _, _, size in tasks), 0
    if max_bytes is None:
        log.warning("Invalid MAX_TRANSFER value %r; date-sorted backup will run without a limit", MAX_TRANSFER)
        return tasks, False, sum(max(0, size) for _, _, size in tasks), 0

    selected = []
    planned_bytes = 0
    deferred = 0

    for source, dest, size in tasks:
        size = max(0, int(size or 0))
        if planned_bytes + size > max_bytes:
            deferred += 1
            continue
        selected.append((source, dest, size))
        planned_bytes += size

    if deferred:
        log.info(
            "MAX_TRANSFER=%s selected %d/%d files for this run (%s planned, %s limit)",
            MAX_TRANSFER,
            len(selected),
            len(tasks),
            _format_bytes(planned_bytes),
            _format_bytes(max_bytes),
        )

    return selected, deferred > 0, planned_bytes, deferred


async def _copy_from_parent(source: str, dest: str) -> bool:
    """Retry a single-file copy by listing the parent directory and filtering the name."""
    parent, name = _split_remote_path(source)
    if not name:
        return False

    dest_path = Path(dest)
    proc = await asyncio.create_subprocess_exec(
        "rclone", "copy",
        f"{RCLONE_REMOTE}:{parent}",
        str(dest_path.parent),
        "--iclouddrive-service", ICLOUD_SERVICE,
        "--ignore-existing",
        "--files-from-raw", "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate(f"{name}\n".encode())
    if proc.returncode == 0:
        return dest_path.exists() and dest_path.stat().st_size > 0

    stderr_text = stderr.decode(errors="replace")
    if "max transfer limit reached" in stderr_text:
        raise MaxTransferReached()
    log.warning("parent copy fallback failed for %s: %s", source, stderr_text[:200])
    return False


async def _copyto(source: str, dest: str) -> bool:
    """Copy a single file via rclone copyto. Returns True on success."""
    proc = await asyncio.create_subprocess_exec(
        "rclone", "copyto",
        f"{RCLONE_REMOTE}:{source}",
        dest,
        "--iclouddrive-service", ICLOUD_SERVICE,
        "--ignore-existing",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode == 0:
        return True
    stderr_text = stderr.decode(errors="replace")
    if "max transfer limit reached" in stderr_text:
        raise MaxTransferReached()
    if _should_retry_from_parent(stderr_text):
        log.info("copyto path lookup failed for %s; retrying from parent directory", source)
        return await _copy_from_parent(source, dest)
    log.warning("copyto failed for %s: %s", source, stderr_text[:200])
    return False


class MaxTransferReached(Exception):
    pass


async def backup_by_date() -> tuple[int, int, str]:
    """
    Full date-sorted backup: list files with metadata, then copy
    new/changed files directly into YYYY/MM/DD/ folders.

    Returns (files_copied, errors, summary_suffix).
    """
    # 1. Get file listing with metadata
    log.info("Fetching file metadata for date-sorted backup...")
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
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        log.error("rclone lsjson timed out")
        return 0, 0, ""
    except Exception as e:
        log.error("rclone lsjson failed: %s", e)
        return 0, 0, ""

    entries = json.loads(stdout.decode())
    log.info("Got metadata for %d files", len(entries))

    # 2. Build transfer list: (source_path, dest_abs_path)
    tasks = []
    skipped = 0

    for entry in entries:
        path = entry.get("Path", "")
        size = entry.get("Size", 0)
        if not path:
            continue

        # Parse date
        added_raw = entry.get("Metadata", {}).get("added-time", "")
        try:
            added_raw = added_raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(added_raw)
        except (ValueError, TypeError):
            dt = datetime(2000, 1, 1)  # fallback

        dest_dir = Path(BACKUP_DIR) / f"{dt.year:04d}/{dt.month:02d}/{dt.day:02d}"
        dest_file = dest_dir / Path(path).name

        # Skip already existing files (incremental)
        if dest_file.exists() and dest_file.stat().st_size > 0:
            skipped += 1
            continue

        dest_dir.mkdir(parents=True, exist_ok=True)
        tasks.append((_join_remote_path(RCLONE_SOURCE, path), str(dest_file), size))

    log.info("%d new files to transfer, %d already present", len(tasks), skipped)

    if not tasks:
        return 0, 0, f" (all {skipped} files up to date)"

    tasks, max_limited, planned_bytes, deferred = _limit_tasks_by_max_transfer(tasks)

    if not tasks:
        suffix = f" (max-transfer limit reached; {deferred} files deferred)"
        if skipped:
            suffix += f"\n📁 {skipped} files already present"
        return 0, 0, suffix

    # 3. Parallel download with semaphore
    sem = asyncio.Semaphore(PARALLEL_TRANSFERS)
    copied = 0
    errors = 0
    total_bytes = 0
    max_reached = False

    async def transfer_one(source: str, dest: str, size: int):
        nonlocal copied, errors, total_bytes, max_reached
        async with sem:
            if max_reached:
                return
            try:
                ok = await _copyto(source, dest)
                if ok:
                    copied += 1
                    total_bytes += size
                else:
                    errors += 1
            except MaxTransferReached:
                max_reached = True

    await asyncio.gather(*[transfer_one(s, d, sz) for s, d, sz in tasks])

    # 4. Summary
    suffix = ""
    if max_reached or max_limited:
        suffix += f" (max-transfer limit reached; {deferred} files deferred)"
    suffix += f"\n📅 Sorted into {copied} files (YYYY/MM/DD)"
    if _has_valid_max_transfer():
        suffix += f"\n🚦 Planned transfer: {_format_bytes(planned_bytes)} / {MAX_TRANSFER}"
    if skipped:
        suffix += f"\n📁 {skipped} files already present"

    log.info("Date-sorted backup: %d copied, %d errors, %d skipped", copied, errors, skipped)
    return copied, errors, suffix
