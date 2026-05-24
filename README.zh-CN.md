# iCloud Photos Backup — rclone + Telegram

[English](README.md) | [简体中文](README.zh-CN.md)

一个轻量级 Docker 服务，用于将 iCloud 照片增量备份到本地存储。
项目使用 [rclone 原生 iCloud 后端](https://rclone.org/iclouddrive/)。
Telegram 机器人负责 2FA 重新认证，并发送备份结果摘要。

## 快速开始

```bash
cp .env.example .env          # 填写你的账号和配置
docker-compose up -d          # 构建并启动
```

设置 `INIT_AUTO=true` 后，机器人会通过 Telegram 发送消息来触发 2FA 初始化，无需进入终端。
如果需要手动初始化，可以运行：

```bash
docker-compose exec rclone-icloud-backup as-app-user rclone config
# Storage: iclouddrive -> Service: photos -> Name: icloudphotos
```

## 工作方式

- **备份任务** 默认每 6 小时运行一次，使用 `rclone copy --ignore-existing`，只下载新增文件，不会删除本地文件
- **认证检查** 默认每小时运行一次，如果认证过期，Telegram 会询问是否重新认证
- **2FA** 完全通过 Telegram 处理，收到验证码后直接发送 6 位数字即可
- 默认备份 `PrimarySync` 和 `SharedSync-*` 照片库
- 首次运行会列出所有照片，可能较慢；后续运行会使用 rclone 元数据缓存

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APPLE_ID` | - | Apple ID 邮箱 |
| `APPLE_PASSWORD` | - | Apple ID 密码，建议优先使用 `APPLE_PASSWORD_OBSCURED` |
| `APPLE_PASSWORD_OBSCURED` | - | 预先混淆后的密码，通过 `rclone obscure PASS` 生成 |
| `RCLONE_REMOTE` | `icloudphotos` | rclone remote 名称 |
| `RCLONE_CONFIG_DIR` | `/config/rclone` | `rclone.conf` 所在目录 |
| `RCLONE_CACHE_DIR` | `/cache/rclone` | rclone 元数据缓存目录 |
| `ICLOUD_SERVICE` | `photos` | `drive` 或 `photos` |
| `BACKUP_DIR` | `/data/backup` | 容器内的备份目标目录 |
| `PUID` | `1000` | 应用启动后使用的 UID |
| `PGID` | `1000` | 应用启动后使用的 GID |
| `UMASK` | `022` | 下载文件的创建权限掩码 |
| `CHOWN_RECURSIVE` | `false` | 设置为 `true` 时，启动时递归修复挂载目录所有权，适合处理旧的 root-owned 文件 |
| `RCLONE_SOURCE` | - | iCloud 源路径，留空表示从根目录备份所有照片库 |
| `INIT_AUTO` | `false` | `true` 表示自动创建 rclone 配置并通过 Telegram 触发 2FA |
| `SORT_BY_DATE` | `true` | `true` 表示按 `YYYY/MM/DD/` 目录整理照片 |
| `DRY_RUN` | `false` | `true` 表示仅模拟运行，不实际下载 |
| `MAX_TRANSFER` | - | 单次运行传输上限，例如 `500M`，留空表示不限制 |
| `BACKUP_INTERVAL_HOURS` | `6` | 备份间隔，单位小时 |
| `AUTH_CHECK_INTERVAL_MINUTES` | `60` | 认证检查间隔，单位分钟 |
| `FIRST_BACKUP_DELAY_MINUTES` | `5` | 启动后首次备份延迟，单位分钟 |
| `TELEGRAM_BOT_TOKEN` | - | 从 [@BotFather](https://t.me/BotFather) 获取 |
| `TELEGRAM_CHAT_ID` | - | 从 [@userinfobot](https://t.me/userinfobot) 获取 |
| `TZ` | `Europe/Berlin` | 时区 |

## 文件权限

容器启动时会先以 root 身份创建和准备挂载目录，然后切换到 `PUID:PGID` 运行备份进程。
在 Linux 上，建议用宿主机拥有备份目录的用户 ID：

```bash
id -u
id -g
```

然后把得到的数字写入 `.env`：

```bash
PUID=1000
PGID=1000
```

如果旧版本已经生成了 root 拥有的文件，可以临时设置：

```bash
CHOWN_RECURSIVE=true
```

启动容器修复一次权限后，再改回 `false`，避免每次启动都扫描大型备份目录。

## Telegram 命令

| 命令 | 说明 |
|---|---|
| `/start` | 查看状态概览 |
| `/status` | 查看认证状态和上次备份信息 |
| `/backup` | 手动触发备份 |
| `/reauth` | 开始重新认证 |
| `/logs` | 查看最近一次备份统计 |

## 2FA 流程

1. 机器人检测到认证过期后，会询问是否重新认证
2. 点击 **Yes** 后，机器人启动 `rclone config reconnect`
3. 机器人提示需要 2FA 验证码
4. 发送 6 位 Apple 2FA 验证码，或发送 `sms`
5. 机器人确认认证成功，并触发一次备份

## 挂载目录

| 本地路径 | 容器路径 | 用途 |
|---|---|---|
| `./backup` | `/data/backup` | 下载的照片和视频 |
| `./rclone-config` | `/config/rclone` | rclone 配置，包含 trust token、cookies 和密码 |
| `./rclone-cache` | `/cache/rclone` | 元数据缓存 |

## 与 docker-icloudpd 对比

| | docker-icloudpd | rclone-icloud-backup |
|---|---|---|
| 后端 | icloudpd (Python) | rclone (Go) |
| 认证 | 基于 Cookie，较脆弱 | SRP + trust token，使用 Apple 官方协议 |
| 2FA | 主要在启动时处理 | 可随时通过 Telegram 处理 |
| 重新认证 | 通常需要手动登录 | Telegram 一键触发 |
| 镜像体积 | 约 500 MB | 约 150 MB |

## 故障排查

- **Access iCloud Data on the Web** 必须开启：iPhone -> 设置 -> Apple Account -> iCloud
- **开启 ADP？** 支持。2FA 后需要在受信任设备上批准
- **认证失败？** 在 Telegram 发送 `/reauth`，或运行 `docker-compose exec rclone-icloud-backup as-app-user rclone config reconnect icloudphotos:`
- **清理缓存：** `rm -rf ./rclone-cache/*`
