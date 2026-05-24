FROM python:3.12-alpine

LABEL org.opencontainers.image.title="iCloud Backup via rclone"
LABEL org.opencontainers.image.description="Backup iCloud Photos to local storage using rclone with Telegram notifications and 2FA"
LABEL org.opencontainers.image.source="https://github.com/pcace/rclone-icloud-backup"

# Install rclone and dependencies
RUN apk add --no-cache \
    curl \
    unzip \
    tzdata \
    ca-certificates \
    bash \
    su-exec \
    && curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip \
    && unzip rclone-current-linux-amd64.zip \
    && cd rclone-*-linux-amd64 \
    && cp rclone /usr/local/bin/ \
    && chmod +x /usr/local/bin/rclone \
    && cd / \
    && rm -rf rclone-current-linux-amd64.zip rclone-*-linux-amd64

WORKDIR /app

# Install Python dependencies
COPY scripts/requirements.txt ./scripts/
RUN pip install --no-cache-dir -r scripts/requirements.txt

# Copy scripts
COPY scripts/ /app/scripts/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Create directories
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && ln -s /usr/local/bin/docker-entrypoint.sh /usr/local/bin/as-app-user \
    && chown -R root:root /app \
    && find /app -type d -exec chmod 755 {} + \
    && find /app -type f -exec chmod 644 {} + \
    && mkdir -p /data/backup /config/rclone /cache/rclone /home/appuser

VOLUME ["/data/backup", "/config/rclone", "/cache/rclone"]

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PUID=1000 \
    PGID=1000 \
    UMASK=022 \
    BACKUP_DIR=/data/backup \
    RCLONE_CONFIG_DIR=/config/rclone \
    RCLONE_CONFIG=/config/rclone/rclone.conf \
    RCLONE_CACHE_DIR=/cache/rclone \
    XDG_CACHE_HOME=/cache

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "scripts.main"]
