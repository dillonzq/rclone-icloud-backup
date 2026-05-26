# syntax=docker/dockerfile:1.7

ARG GO_VERSION=1.25
ARG RCLONE_REPOSITORY=https://github.com/rclone/rclone.git
ARG RCLONE_VERSION=v1.74.2
ARG RCLONE_PATCH_URLS=https://github.com/rclone/rclone/pull/9399.patch

FROM --platform=$BUILDPLATFORM golang:${GO_VERSION}-alpine AS rclone-builder

ARG RCLONE_REPOSITORY
ARG RCLONE_VERSION
ARG RCLONE_PATCH_URLS
ARG TARGETOS
ARG TARGETARCH

RUN apk add --no-cache ca-certificates curl git patch

WORKDIR /src/rclone

RUN git init \
    && git remote add origin "$RCLONE_REPOSITORY" \
    && git fetch --depth 1 origin "$RCLONE_VERSION" \
    && git checkout --detach FETCH_HEAD \
    && patch_urls="$(printf '%s' "$RCLONE_PATCH_URLS" | tr ',;' '  ')" \
    && patch_index=0 \
    && for patch_url in $patch_urls; do \
        patch_index=$((patch_index + 1)); \
        curl -fsSL "$patch_url" -o "/tmp/rclone-${patch_index}.patch"; \
        patch -p1 < "/tmp/rclone-${patch_index}.patch"; \
    done \
    && mkdir -p /out \
    && CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
        go build -trimpath -ldflags "-s -w" -o /out/rclone .

FROM python:3.12-alpine

ARG RCLONE_VERSION
ARG RCLONE_PATCH_URLS

LABEL org.opencontainers.image.title="iCloud Backup via rclone"
LABEL org.opencontainers.image.description="Backup iCloud Photos to local storage using rclone with Telegram notifications and 2FA"
LABEL org.opencontainers.image.source="https://github.com/dillonzq/rclone-icloud-backup"
LABEL org.opencontainers.image.rclone.version="${RCLONE_VERSION}"
LABEL org.opencontainers.image.rclone.patch-urls="${RCLONE_PATCH_URLS}"

# Install runtime dependencies
RUN apk add --no-cache \
    tzdata \
    ca-certificates \
    bash \
    su-exec

COPY --from=rclone-builder /out/rclone /usr/local/bin/rclone

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
    ICLOUD_REGION=global \
    XDG_CACHE_HOME=/cache

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "scripts.main"]
