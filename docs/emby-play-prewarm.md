# Emby 播放预热器

`emby-play-prewarm` 是一个轻量 systemd 服务，用来缓解 CloudDrive2/团队盘冷片源第一次起播慢的问题。

它不接管 Emby 端口，不改 `8096`、`443`、反代或客户端播放地址。服务只监听 Emby 日志：当客户端真正点击播放并请求 `PlaybackInfo?IsPlayback=true` 时，后台提前读取该影片的头部和尾部 Range，让 CD2/网盘链路先热起来。

## 什么时候会生效

一键安装会默认安装并启动预热器。它可以在 CD2 和 Emby 还没完全配置好时先安装，因为它会等待 Emby 日志出现。

真正生效需要满足这些条件：

- Emby 容器已经运行。
- CD2 已经挂载好网盘，Emby 能读到 STRM 指向的实际媒体。
- 客户端真正点击播放，Emby 日志里出现 `PlaybackInfo?IsPlayback=true`。
- 该影片短时间内没有被预热过；同一部电影 4 分钟内默认只预热一次。

它对入口端口不挑。直连 `8096`、HTTPS `443`、Nginx 反代、BWG/BWGG 中转都可以触发，只要最终请求进入同一个 Emby。

## 适合解决

- 没看过的冷电影第一次起播要等 8-20 秒。
- 小幻/RodelPlayer 播放大 MKV 前会读头、读尾、再重新拉头，导致转圈。
- VPS 本机测试很快，但本地客户端第一次播放明显慢。

它不能完全消除播放器自身分析、代理/Mihomo、家庭宽带到 VPS 链路造成的延迟。

## 安装和使用

一键安装默认已执行，不需要额外手动安装。

如果要单独安装或重装：

```bash
sudo ./scripts/install-emby-play-prewarm.sh
```

也可以走统一入口：

```bash
sudo ./post-auth.sh play-prewarm
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

或：

```bash
systemctl status emby-play-prewarm.service --no-pager
```

查看实时日志：

```bash
journalctl -u emby-play-prewarm.service -f
```

卸载：

```bash
sudo ./scripts/install-emby-play-prewarm.sh uninstall
```

## 怎么检查有没有生效

先确认服务正在运行：

```bash
systemctl is-active emby-play-prewarm.service
```

输出应为：

```text
active
```

也可以跑总体验收：

```bash
sudo ./healthcheck.sh
```

其中应出现：

```text
[OK]   Emby 播放预热器
```

然后打开实时日志：

```bash
journalctl -u emby-play-prewarm.service -f
```

用 Emby、小幻、RodelPlayer 或其他客户端点击一部电影播放。看到类似下面两行，说明已经捕获到播放请求并开始预热：

```text
schedule item=564916 user=...
prewarm item=564916 container=mkv head={'status': 206, 'bytes': 8388608, ...} tail={'status': 206, 'bytes': 1048576, ...}
```

重点看 `prewarm item=...` 这一行：

- `head status=206` 表示文件头部 Range 预读成功。
- `head bytes=8388608` 表示默认头部 8 MiB 已读到。
- `tail status=206` 表示文件尾部 Range 预读成功。
- `tail bytes=1048576` 表示默认尾部 1 MiB 已读到。
- `seconds=...` 是本次预热耗时。

如果只有 `schedule item=...`，没有 `prewarm item=...`，等几秒再看；冷盘或大文件可能需要更久。

## 没看到预热日志怎么办

先看服务是否运行：

```bash
systemctl status emby-play-prewarm.service --no-pager
```

再确认 Emby 日志是否存在：

```bash
ls -lh /root/docker-compose/emby/config/logs/embyserver.txt
```

如果日志存在但点击播放后没有 `schedule item=...`，通常是：

- 客户端只是浏览详情页，没有真正点击播放。
- 客户端请求没有带 `IsPlayback=true`。
- 当前播放走的不是这台 Emby。
- Emby 日志级别或路径被改过。

如果出现 `prewarm failed`，看后面的错误：

- `401 Unauthorized`：Emby Token 无法使用，通常是日志里的 Token 被隐藏或配置里没有可用 Token。
- `404 Not Found`：媒体源路径或容器后缀不匹配。
- `timeout`：CD2/网盘冷启动或网络太慢。

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

修改环境变量后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart emby-play-prewarm.service
```

## 安全边界

- 脚本不包含账号、密码、OAuth 或 Emby Token。
- 运行时优先从 Emby 请求日志读取当前客户端 Token。
- 如果日志 Token 含不可见字符，会回退读取本机 EmbyStream 测试配置中的 token；没有该配置时只跳过预热。
- 不修改 Emby 数据库、媒体库、Nginx 或 CloudDrive2 配置。
