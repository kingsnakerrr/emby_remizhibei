# Emby 双播放线路（同一实例）

这套方案只运行一个 Emby。账号、用户、数据库、插件、媒体库、观看记录和续播
进度完全共用，不会产生第二套 Emby 数据。

## 线路结构

- 主线路：标准 HTTPS 域名；Emby 容器把原 CD2 媒体路径覆盖为 rclone VFS
  挂载，因此媒体读取走 rclone。
- CD2 备用线路：同一域名的 `8443` HTTPS 端口；Nginx 仍把登录、API、插件、
  WebSocket 和进度请求交给同一个 Emby，只把 `original` 原画直播放请求转给
  CD2 网关。
- CD2 网关通过 ItemId 只读查询 Emby `library.db`，读取 `.strm` 中的 CD2 路径，
  校验现有 Emby Token 后支持 HTTP Range 播放。
- CD2 不可用或目标不属于允许目录时，Nginx 自动回退主 Emby/rclone。

## 文件

- `compose/emby.yml`：唯一 Emby 的基础配置。
- `compose/emby-dual-playback.override.yml`：rclone 主线路覆盖和 CD2 网关。
- `compose/cd2-playback-gateway/`：CD2 原画播放网关源码。
- `templates/nginx/emby-cd2-backup-8443.conf`：备用 HTTPS 端口模板。

服务器部署时可把基础 Compose 和 override 合并成一个写有中文说明的
`/root/docker-compose/emby/docker-compose.yml`。证书域名和路径必须替换为实际值。

## 限制

备用线路当前只拦截 Emby 的 `original` 原画直播放请求。转码、HLS 以及无法识别的
请求仍由主 Emby/rclone 处理。这样可以保证同一套插件和播放记录，同时避免维护
第二个 Emby。

## 验证

```bash
curl -fsS https://emby.example.com:8443/cd2-health
docker compose -f /root/docker-compose/emby/docker-compose.yml ps
docker logs --tail 50 emby-cd2-playback-gateway
```

带有效 Emby 凭据和 `Range` 的原画请求应返回 `206`，并包含：

```text
X-Playback-Source: cd2
X-Emby-Playback-Line: cd2-backup
```

无凭据访问视频应返回 `401`。不要把 Emby Token、API Key 或 OAuth 配置提交到仓库。
