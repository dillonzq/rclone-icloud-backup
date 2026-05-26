#!/bin/sh
set -e

APP_USER="${APP_USER:-appuser}"
APP_GROUP="${APP_GROUP:-appgroup}"
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
UMASK="${UMASK:-022}"
CHOWN_RECURSIVE="${CHOWN_RECURSIVE:-false}"

is_uint() {
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
        *) return 0 ;;
    esac
}

is_true() {
    case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|y) return 0 ;;
        *) return 1 ;;
    esac
}

validate_ids() {
    if ! is_uint "$PUID"; then
        echo "PUID must be a numeric uid, got: $PUID" >&2
        exit 1
    fi
    if ! is_uint "$PGID"; then
        echo "PGID must be a numeric gid, got: $PGID" >&2
        exit 1
    fi
}

setup_paths() {
    BACKUP_DIR="${BACKUP_DIR:-/data/backup}"
    RCLONE_CONFIG_DIR="${RCLONE_CONFIG_DIR:-/config/rclone}"
    RCLONE_CONFIG="${RCLONE_CONFIG:-${RCLONE_CONFIG_DIR}/rclone.conf}"
    RCLONE_CACHE_DIR="${RCLONE_CACHE_DIR:-/cache/rclone}"
    ICLOUD_REGION="${ICLOUD_REGION:-global}"
    RCLONE_ICLOUDDRIVE_REGION="${RCLONE_ICLOUDDRIVE_REGION:-$ICLOUD_REGION}"
    XDG_CACHE_HOME="${XDG_CACHE_HOME:-/cache}"

    if [ "$PUID" = "0" ]; then
        HOME="${HOME:-/root}"
    else
        HOME="${HOME:-/home/${APP_USER}}"
    fi

    export BACKUP_DIR RCLONE_CONFIG_DIR RCLONE_CONFIG RCLONE_CACHE_DIR ICLOUD_REGION RCLONE_ICLOUDDRIVE_REGION XDG_CACHE_HOME HOME
}

ensure_user_group() {
    if [ "$PUID" = "0" ]; then
        return
    fi

    group_name="$(getent group "$PGID" 2>/dev/null | cut -d: -f1 || true)"
    if [ -z "$group_name" ]; then
        group_name="$APP_GROUP"
        if getent group "$group_name" >/dev/null 2>&1; then
            group_name="${APP_GROUP}_${PGID}"
        fi
        addgroup -g "$PGID" "$group_name"
    fi

    user_name="$(getent passwd "$PUID" 2>/dev/null | cut -d: -f1 || true)"
    if [ -z "$user_name" ]; then
        user_name="$APP_USER"
        if getent passwd "$user_name" >/dev/null 2>&1; then
            user_name="${APP_USER}_${PUID}"
        fi
        adduser -D -H -u "$PUID" -G "$group_name" -s /sbin/nologin "$user_name"
    fi
}

prepare_dirs() {
    rclone_config_parent="$(dirname "$RCLONE_CONFIG")"
    mkdir -p "$BACKUP_DIR" "$RCLONE_CONFIG_DIR" "$rclone_config_parent" "$RCLONE_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME"

    if [ "$(id -u)" != "0" ]; then
        return
    fi

    if is_true "$CHOWN_RECURSIVE"; then
        chown -R "$PUID:$PGID" "$BACKUP_DIR" "$RCLONE_CONFIG_DIR" "$rclone_config_parent" "$RCLONE_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME" || true
    else
        chown "$PUID:$PGID" "$BACKUP_DIR" "$RCLONE_CONFIG_DIR" "$rclone_config_parent" "$RCLONE_CACHE_DIR" "$XDG_CACHE_HOME" "$HOME" || true
    fi
}

run_as_configured_user() {
    if [ "$(id -u)" = "0" ] && [ "$PUID" != "0" ]; then
        exec su-exec "$PUID:$PGID" "$@"
    fi

    exec "$@"
}

validate_ids
setup_paths
umask "$UMASK"

if [ "$(id -u)" = "0" ]; then
    ensure_user_group
fi

if [ "$(basename "$0")" = "as-app-user" ]; then
    run_as_configured_user "$@"
fi

prepare_dirs
run_as_configured_user "$@"
