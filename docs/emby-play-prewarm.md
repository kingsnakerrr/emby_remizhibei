# Emby 播放预热器

`emby-play-prewarm` 是一个轻量 systemd 服务，用来缓解 CloudDrive2/团队盘冷片源第一次起播慢的问题。

它不接管 Emby 端口，不改 `8096`、`443`、反代或客户端播放地址。服务只监听 Emby 日志：当客户端真正点击播放并请求 `PlaybackInfo?IsPlayback=true` 时，后台提前读取该影片的头部和尾部 Range，让 CD2/网盘链路先热起来。

## 适合解决

- 没看过的冷电影第一次起播要等 8-20 秒。
- 小幻/RodelPlayer 播放大 MKV 前会读头、读尾、再重新拉头，导致转圈。
- VPS 本机测试很快，但本地客户端第一次播放明显慢。

它不能完全消除播放器自身分析、代理/Mihomo、家庭宽带到 VPS 链路造成的延迟。

## 安装

```bash
sudo ./scripts/install-emby-play-prewarm.sh
```

安装后会创建：

```text
/root/docker-compose/emby-play-prewarm/emby_play_prewarm.py
/etc/systemd/system/emby-play-prewarm.service
```

查看状态：

```bash
sudo ./scripts/install-emby-play-prewarm.sh status
```

查看日志：

```bash
journalctl -u emby-play-prewarm.service -f
```

卸载：

```bash
sudo ./scripts/install-emby-play-prewarm.sh uninstall
```

## 默认预热策略

- 只处理 `IsPlayback=true` 的真实播放请求。
- 每部电影每个 Token 4 分钟内只预热一次。
- 预读文件头部 8 MiB。
- 预读文件尾部 1 MiB。
- 最多 2 个后台预热线程。

可以通过 systemd 环境变量覆盖：

```ini
Environment=EMBY_PREWARM_HEAD_BYTES=8388608
Environment=EMBY_PREWARM_TAIL_BYTES=1048576
Environment=EMBY_PREWARM_COOLDOWN_SECONDS=240
Environment=EMBY_PREWARM_MAX_WORKERS=2
```

## 安全边界

- 脚本不包含账号、密码、OAuth 或 Emby Token。
- 运行时优先从 Emby 请求日志读取当前客户端 Token。
- 如果日志 Token 含不可见字符，会回退读取本机 EmbyStream 测试配置中的 token；没有该配置时只跳过预热。
- 不修改 Emby 数据库、媒体库、Nginx 或 CloudDrive2 配置。

## 验证

点击一部未看过电影后，日志中出现类似内容即表示生效：

```text
schedule item=564916 user=...
prewarm item=564916 container=mkv head={'status': 206, 'bytes': 8388608, ...} tail={'status': 206, 'bytes': 1048576, ...}
```
