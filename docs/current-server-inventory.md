# Hostdzire Emby 服务器现状

盘点日期：2026-10-24（Asia/Shanghai）。本文不记录密码、Token、API Key、
OAuth、License 或 Telegram 管理员 ID。

## 正在运行的主要程序

| 程序 | 运行方式 | 安装/数据目录 | 用途 |
| --- | --- | --- | --- |
| Emby | Docker `amilys/embyserver` | `/root/docker-compose/emby` | 媒体库、播放记录、插件宿主 |
| CloudDrive2 | Docker `cloudnas/clouddrive2` | `/root/docker-compose/clouddrive2` | Google Drive 挂载到 `/CloudNAS/CloudDrive` |
| Symedia | Docker `shenxianmq/symedia` | `/root/docker-compose/symedia` | 归档、刮削、STRM/NFO/图片生成 |
| Emby TG notifier | Docker 本地构建 | `/root/docker-compose/emby_rukutongzhi` | 入库通知、TG 绑定、SenPlayer/PotPlayer 点播 |
| Nginx + Certbot | systemd | `/etc/nginx`、`/etc/letsencrypt` | Emby HTTPS 与证书自动续期 |

Emby 正式入口为 `https://emby.rmzb.de`，Let's Encrypt 证书由 Certbot 自动续期。
`8096` 只绑定 `127.0.0.1` 供 Nginx 使用；旧 `hdz.222321.xyz` 的 Emby HTTPS
入口只跳转到新域名。证书私钥只允许进入 `age` 加密备份，不能提交 Git。

## Emby 插件

- Strm Assistant Pro：播放体验、媒体信息提取与 STRM 优化；商业 DLL/授权不入库。
- Emby Webhooks：Webhook 通知。
- MBBackup：Emby 配置备份。
- MovieDb、TVDB、OMDb、Fanart、MusicBrainz、NFO Metadata。
- OpenSubtitles、DLNA、Cinema Mode、M3U Tuner、XmlTV、Guide Data。
- Blu-ray/DVD Mounter、Studio Images。

## 自定义补丁与自动优化

### Emby 播放预热

`emby-play-prewarm.service` 监听真实 PlaybackInfo 请求，预读片头、片尾和续播位置
附近的 Range，降低团队盘冷文件第一次起播等待。代码由
`scripts/install-emby-play-prewarm.sh` 安装。

### Emby 元数据守护

`emby-metadata-guard.timer` 每 15 分钟运行：

- 只处理目录名明确包含中文标题、年份和 TMDB ID 的电影 NFO；
- 修复“中文文件夹但 NFO title 仍为英文”；
- 修改前备份 NFO；
- 请求 Emby 重新读取修改项；
- 审计 Movie/Series 缺封面、TMDB、简介和年份的项目。

它不猜测没有中文依据的英文文件夹，也不会给缺海报项目乱套图片。

### Symedia CD2 归档自动重试

`symedia-archive-retry.service` 每 60 秒检查失败历史：

- 目标存在且大小一致：把 Symedia 假失败自动恢复为成功；
- 源存在、目标不存在：调用 CD2 API 安全重试，最多三次；
- 两边都有同尺寸文件：确认成功但保留源副本；
- 两边都不存在或缺媒体身份：保留失败，禁止伪造成功。

同时关闭了使用 API Token 时持续返回 `PERMISSION_DENIED` 的 CD2 PushMessage
监听，并统一实际目录名为 `symedia_gd`。

### CD2 删除缓存刷新

Root cron 在每小时 `02,17,32,47` 分执行浅层目录缓存刷新。它解决团队盘外部删除
后，CD2/Symedia 因目录缓存仍看到旧文件的问题。日志保留 14 天。

### Emby 近期入库刷新

`emby-refresh.timer` 每约 5 分钟执行 `/root/scripts/shuaxinyuansu.sh`，检查最近 60 分钟
入库项目并强制刷新元数据。公开版本不保存 Emby API Key，而是运行时读取环境变量或
Emby 本机最新的有效令牌。

## 监控

- Komari Agent：`komari-agent.service`。
- Sysmon 与 Sysmon Guard：`sysmon.service`、`sysmon-guard.timer`。
- SystemLog：`systemlog.service`。

这些服务需要各自监控面板的私密凭据，因此只记录名称，不进入公开一键安装。

## 已删除且不应恢复

- 5 个哪吒 Agent。
- CD2 60005 预热代理。
- FastSTRM。
- OpenList 及其 Range/串流代理。
- HTML5 Speedtest 与 Ookla 残留。

## GitHub 与加密备份边界

GitHub 保存无密码安装器、Compose、补丁源码和说明。以下内容只进入
`scripts/backup-encrypted.sh` 生成的 `age` 加密包：

- Emby 配置、数据库和商业插件授权；
- CD2 登录/OAuth；
- Symedia License、密钥、数据库和任务；
- TG Bot Token、绑定数据和管理员配置；
- rclone 配置；
- Nginx 证书私钥。

媒体文件、可重建缓存、日志、Emby 海报缓存不进入配置备份。
