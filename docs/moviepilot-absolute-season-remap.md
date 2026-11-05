# MoviePilot 动漫绝对集数自动分季

用于修复整部动漫种子把全部剧集写成 `S01E001...S01E291`，导致 Emby 只显示一季的问题。

安装或更新：

```bash
python3 scripts/patch-moviepilot-absolute-seasons.py --restart
```

补丁目标为 `/opt/docker-compose/moviepilot/overrides/transfer.py`，安装前会自动备份。

MoviePilot 插件页同时安装“入库前动漫自动分季”管理插件，用于查看引擎状态、规则、成功日志和安全跳过日志。管理插件负责可视化和维护；真正的路径转换仍在整理引擎中执行，保证时机早于移动上传。

插件页的开关会直接控制整理引擎。关闭后新整理任务跳过自动分季，重新打开立即恢复。源路径和目标路径均取自 MoviePilot 当前整理任务，不需要单独配置目录。

程序只在以下条件全部满足时自动转换：

1. MoviePilot 已识别为电视剧并取得可靠 TMDB ID；
2. 所有视频都标成 S01，且绝对集号从 1 连续到结尾；
3. 没有缺集、重复集或跨季多集文件；
4. 文件总数与 TMDB 的正式季度（不含特别篇 S00）总数完全相等；
5. TMDB 至少有两季，且季度编号连续。

任一条件不满足时只写警告日志，不改文件名。原始下载文件不会被重命名；补丁只影响 MoviePilot 整理后的目标命名、STRM 和 NFO 季集号。

## 实际执行时机

补丁位于 MoviePilot 的整理链路，不是下载器插件：

```text
下载完成 -> MoviePilot 收集整包文件 -> 严格核对 TMDB 季数与总集数
         -> 生成分季后的目标路径 -> 移动/上传 -> Symedia/Emby 入库
```

因此它会在写入网盘前完成分季。它不在 qBittorrent 下载目录里原地改名，不会一边改做种文件一边搬运。当前部署通过只读挂载把宿主机
`/opt/docker-compose/moviepilot/overrides/transfer.py` 覆盖到容器内
`/app/app/chain/transfer.py`；更新 MoviePilot 后重新运行安装脚本即可检查并补装。

运行日志出现以下内容表示补丁已经参与了自动入库：

```text
已严格核验绝对集数全集包：N 集，将按 TMDB M 季自动分季命名。
```

《龙珠Z》TMDB 12971 的验证结果为 291 集：

```text
S01 39 / S02 35 / S03 33 / S04 32 / S05 26
S06 29 / S07 25 / S08 34 / S09 38
```

因此绝对集 `E40` 会变为 `S02E01`，`E74` 会变为 `S02E35`。
