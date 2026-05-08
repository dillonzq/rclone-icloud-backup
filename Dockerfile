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

# Create directories
RUN mkdir -p /data/backup /root/.config/rclone /root/.cache/rclone

VOLUME ["/data/backup", "/root/.config/rclone"]

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "scripts.main"]
