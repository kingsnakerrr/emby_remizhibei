# Emby STRM 图片和元素补齐监控

多版本 STRM 媒体库里，Emby 有时会按视频文件名前缀寻找本地图片：

```text
电影名 (2026) - 2160p...strm
电影名 (2026) - 2160p...-poster.jpg
电影名 (2026) - 2160p...-fanart.jpg
电影名 (2026) - 2160p...-clearlogo.png
```

如果同一文件夹里只有 `poster.jpg`，或者只有 1080p 版本的
`*-poster.jpg`，2160p 版本就可能在 Emby 前端显示空封面。

本工具会定时扫描：

```text
/home/symedia_gd/movies
/home/symedia_rclone_zero/movies
```

只要同一电影文件夹内已经存在任意可用的 `poster.jpg`、`fanart.jpg`、
`backdrop.jpg`、`landscape.jpg`、`clearlogo.png` 或对应版本图片，就会补齐：

- 文件夹级 `poster.jpg`、`fanart.jpg`、`backdrop.jpg`、`landscape.jpg`、`clearlogo.png`
- 每个 `.strm` 文件对应的 `*-poster.jpg`、`*-fanart.jpg`、`*-backdrop.jpg`、`*-landscape.jpg`、`*-clearlogo.png`

如果 Emby 数据库中发现某个项目缺少封面、背景图、NFO 或简介，它会调用 Emby API
触发该项目刷新元数据和图片。实际下载和刮削仍由 Emby 自己完成，遵循媒体库语言、
刮削器和 NFO 保存设置。

它不会覆盖已有图片，也不会修改 STRM 或视频文件。

## 安装

```bash
sudo ./scripts/install-emby-strm-image-fixer.sh
```

一键安装器会默认安装本工具。服务名：

```text
emby-fix-strm-images.service
emby-fix-strm-images.timer
```

默认开机 5 分钟后运行一次，之后每 30 分钟运行一次。

“启动定时轮询”指启用这个 systemd timer，让它按间隔自动检查勾选媒体库；它不是
实时文件监听。控制台里的“只检查缺失/未扫过”会立即跑一次轻量检查；“全局媒体库
扫描”只会让勾选媒体库内所有项目重新请求 Emby 刷新，耗时和 API 请求都更多。

## 手动运行

```bash
sudo ./scripts/install-emby-strm-image-fixer.sh run
```

查看状态：

```bash
sudo ./scripts/install-emby-strm-image-fixer.sh status
```

查看日志：

```bash
journalctl -u emby-fix-strm-images.service -n 100 --no-pager
```

看到类似下面内容表示补齐成功：

```text
RUN|image_metadata|mode=missing|roots=/home/symedia_gd/movies,/home/symedia_rclone_zero/movies
COPY_OK|/home/symedia_gd/movies/.../poster.jpg|/home/symedia_gd/movies/.../电影名 - 2160p...-poster.jpg
REFRESH_OK|12345|/home/symedia_gd/movies/.../电影名.strm
SUMMARY|image_metadata|roots=2|folders_scanned=1200|strm_folders=1000|copy_needed=12|copy_success=12|copy_missing_source=0|copy_failed=0|refresh_checked=1000|refresh_needed=3|refresh_success=3|refresh_failed=0|mode=missing
changed=12 refreshed=3 missing_source=0 failed=0 mode=missing
```

如果输出 `changed=0 refreshed=0`，说明当前没有缺少同名图片或需要 Emby 刷新的项目。
如果没有可复制的源图，会输出 `MISSING_SOURCE|copy|...`；如果有真正失败，会输出
`FAIL|copy|...` 或 `FAIL|refresh|...`，后面会列出具体路径和原因。

## 让 Emby 立即显示

补齐图片后，Emby 通常会通过实时监控发现文件变化。若前端仍未显示，可以在
Emby 中对对应影片执行：

```text
刷新元数据 -> 搜索缺失的元数据
```

或整库扫描一次。已存在的错误缓存可能需要客户端刷新页面或清理图片缓存。

## 卸载

```bash
sudo ./scripts/install-emby-strm-image-fixer.sh uninstall
```
