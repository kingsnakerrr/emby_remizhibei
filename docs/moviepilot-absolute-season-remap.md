# MoviePilot 动漫绝对集数自动分季

用于修复整部动漫种子把全部剧集写成 `S01E001...S01E291`，导致 Emby 只显示一季的问题。

安装或更新：

```bash
python3 scripts/patch-moviepilot-absolute-seasons.py --restart
```

补丁目标为 `/opt/docker-compose/moviepilot/overrides/transfer.py`，安装前会自动备份。

程序只在以下条件全部满足时自动转换：

1. MoviePilot 已识别为电视剧并取得可靠 TMDB ID；
2. 所有视频都标成 S01，且绝对集号从 1 连续到结尾；
3. 没有缺集、重复集或跨季多集文件；
4. 文件总数与 TMDB 的正式季度（不含特别篇 S00）总数完全相等；
5. TMDB 至少有两季，且季度编号连续。

任一条件不满足时只写警告日志，不改文件名。原始下载文件不会被重命名；补丁只影响 MoviePilot 整理后的目标命名、STRM 和 NFO 季集号。

《龙珠Z》TMDB 12971 的验证结果为 291 集：

```text
S01 39 / S02 35 / S03 33 / S04 32 / S05 26
S06 29 / S07 25 / S08 34 / S09 38
```

因此绝对集 `E40` 会变为 `S02E01`，`E74` 会变为 `S02E35`。
