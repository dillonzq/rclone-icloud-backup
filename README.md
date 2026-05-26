# iCloud Photos Backup — rclone + Telegram

[English](README.md) | [简体中文](README.zh-CN.md)

Lightweight Docker service for incremental iCloud Photos backup to local storage.
Uses [rclone's native iCloud backend](https://rclone.org/iclouddrive/).
Telegram bot handles 2FA re-auth and sends backup summaries.

## Quick Start

```bash
cp .env.example .env          # fill in your credentials
docker-compose up -d          # pull & start
```

With `INIT_AUTO=true` (set in `.env`), the bot sends a Telegram message to
kick off 2FA setup — no terminal access needed. Otherwise run manually:

```bash
docker-compose exec rclone-icloud-backup as-app-user rclone config
# Storage: iclouddrive → Service: photos → Name: icloudphotos
```

## How It Works

- **Backup** runs every 6 h → `rclone copy --ignore-existing` (new files only, never deletes)
- **Auth check** runs every hour → if expired, Telegram asks: "Re-auth? Yes/No"
- **2FA** handled entirely in Telegram — send the 6-digit code when prompted
- Both `PrimarySync` and `SharedSync-*` libraries are backed up by default
- First run lists all photos (slow), subsequent runs use rclone's metadata cache

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `APPLE_ID` | — | Apple ID email |
| `APPLE_PASSWORD` | — | Apple ID password — prefer `APPLE_PASSWORD_OBSCURED` |
| `APPLE_PASSWORD_OBSCURED` | — | Pre-obscured password (`rclone obscure PASS`). Use instead of `APPLE_PASSWORD` |
| `RCLONE_REMOTE` | `icloudphotos` | rclone remote name |
| `RCLONE_CONFIG_DIR` | `/config/rclone` | Directory for `rclone.conf` |
| `RCLONE_CACHE_DIR` | `/cache/rclone` | rclone metadata cache directory |
| `ICLOUD_SERVICE` | `photos` | `drive` or `photos` |
| `ICLOUD_REGION` | `global` | `global` or `chinamainland` (requires patched rclone) |
| `BACKUP_DIR` | `/data/backup` | Target directory inside container |
| `PUID` | `1000` | UID used to run the app after startup |
| `PGID` | `1000` | GID used to run the app after startup |
| `UMASK` | `022` | File creation mask for downloaded files |
| `CHOWN_RECURSIVE` | `false` | `true` = recursively chown mounts on startup; useful once for old root-owned files |
| `RCLONE_SOURCE` | — | iCloud path (empty = root with all libraries) |
| `INIT_AUTO` | `false` | `true` = auto-create config + trigger 2FA via Telegram |
| `SORT_BY_DATE` | `true` | `true` = organize into `YYYY/MM/DD/` folders |
| `DRY_RUN` | `false` | `true` = simulate only, no transfer |
| `MAX_TRANSFER` | — | Limit per run, e.g. `500M` (empty = unlimited) |
| `BACKUP_INTERVAL_HOURS` | `6` | Backup frequency |
| `AUTH_CHECK_INTERVAL_MINUTES` | `60` | Auth validation frequency |
| `FIRST_BACKUP_DELAY_MINUTES` | `5` | Delay before first backup |
| `TELEGRAM_BOT_TOKEN` | — | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | — | From [@userinfobot](https://t.me/userinfobot) |
| `TZ` | `Europe/Berlin` | Timezone |

## File Permissions

The container starts as root only long enough to create the mounted directories,
then runs the backup process as `PUID:PGID`. On Linux, get the host IDs with
`id -u` and `id -g`, then put the numeric values in `.env`:

```bash
PUID=1000
PGID=1000
```

If older runs already created root-owned files, set `CHOWN_RECURSIVE=true` once,
start the container, then set it back to `false` to avoid scanning large backups
on every start.

## Telegram Commands

| Command | Description |
|---|---|
| `/start` | Status overview |
| `/status` | Auth status + last backup |
| `/backup` | Trigger manual backup |
| `/reauth` | Start re-authentication |
| `/logs` | Last backup stats |

## 2FA Flow

1. Bot detects expired auth → "Re-authenticate? Yes / No"
2. You tap **Yes** → Bot starts `rclone config reconnect`
3. Bot asks for 2FA code
4. You send the 6-digit code (or `sms`)
5. Bot confirms success + triggers a backup

## Volumes

| Local Path | Container Path | Purpose |
|---|---|---|
| `./backup` | `/data/backup` | Downloaded photos & videos |
| `./rclone-config` | `/config/rclone` | rclone config (trust token, cookies) |
| `./rclone-cache` | `/cache/rclone` | Metadata cache |

## vs. docker-icloudpd

| | docker-icloudpd | rclone-icloud-backup |
|---|---|---|
| Backend | icloudpd (Python) | rclone (Go) |
| Auth | Cookie-based, fragile | SRP + trust token (official Apple protocol) |
| 2FA | Start only | Any time via Telegram |
| Re-auth | Manual re-login | One tap in Telegram |
| Size | ~500 MB | ~150 MB |

## Troubleshooting

- **"Access iCloud Data on the Web"** must be ON (iPhone → Settings → Apple Account → iCloud)
- **ADP enabled?** Supported. Approve on trusted device after 2FA.
- **Auth failing?** Send `/reauth` in Telegram or run `docker-compose exec rclone-icloud-backup as-app-user rclone config reconnect icloudphotos:`
- **Clear cache:** `rm -rf ./rclone-cache/*`
