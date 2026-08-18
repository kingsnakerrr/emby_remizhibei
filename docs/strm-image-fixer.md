# Emby STRM 图片补齐器

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
`clearlogo.png` 或对应版本图片，就会补齐：

- 文件夹级 `poster.jpg`、`fanart.jpg`、`clearlogo.png`
- 每个 `.strm` 文件对应的 `*-poster.jpg`、`*-fanart.jpg`、`*-clearlogo.png`

它不会下载图片，不会覆盖已有图片，也不会修改 STRM、NFO 或视频文件。

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
COPY|/home/symedia_gd/movies/.../poster.jpg|/home/symedia_gd/movies/.../电影名 - 2160p...-poster.jpg
changed=12
```

如果输出 `changed=0`，说明当前没有缺少同名图片的 STRM。

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
