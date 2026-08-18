# Emby STRM 中文标题修复器

有些影片的文件夹已经是中文名，例如：

```text
/home/symedia_rclone_zero/movies/欧美电影/逆岭 (2024) {tmdb-646097}/
```

但 NFO 或 Emby 数据库里的 `Name` / `SortName` 仍可能保留英文：

```text
Rebel Ridge
Spider-Man: No Way Home
Resident Evil: Welcome to Raccoon City
```

这种情况下，普通“刷新元数据”不一定会覆盖旧标题，前端就会继续显示英文。

本工具会按 STRM 所在电影文件夹提取中文片名，然后：

- 修正同名 `.nfo` 里的 `<title>` 和 `<sorttitle>`；
- 停止 Emby；
- 备份 `/root/docker-compose/emby/config/data/library.db`；
- 修正 Emby 数据库中对应 STRM 条目的 `Name` 和 `SortName`；
- 启动 Emby。

它不会修改 `OriginalTitle`，所以英文/原始标题仍会保留在数据库里。

## 预览

```bash
sudo ./scripts/fix-emby-strm-chinese-titles.sh dry-run
```

看到 `WOULD_FIX` 表示会被修复，但不会改文件、不会停 Emby。

## 执行修复

```bash
sudo ./scripts/fix-emby-strm-chinese-titles.sh
```

或显式执行：

```bash
sudo ./scripts/fix-emby-strm-chinese-titles.sh apply
```

执行前会停止 Emby 几秒钟，避免直接写运行中的 SQLite 数据库。备份文件会保存到：

```text
/root/metadata-fix-backups/
```

## 什么时候用

- 文件夹中文，但 Emby 海报墙标题显示英文；
- NFO 已经被改成中文，Emby 刷新后仍不变；
- 多版本 STRM 入库后部分版本显示英文标题。

如果影片本身没有中文译名，或文件夹名也是英文，本工具不会改。
