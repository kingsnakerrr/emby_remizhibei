# MoviePilot 旧媒体季度修复助手

## 工作位置

修复发生在媒体已经上传并生成 STRM 之后：

`下载完成 -> MoviePilot 整理/上传 -> 修复助手扫描 -> 人工确认 -> 暂停 Symedia -> CloudDrive2 网盘真文件分季/改名 -> 删除并重建本地 STRM/NFO/图片 -> 恢复 Symedia -> Emby 重扫`

扫描与安全判断始终以 CloudDrive2 网盘真实视频为准，不以本地 STRM 为准。这样旧版曾经只修改本地 STRM 的项目仍会再次被发现并完成根治。

它不会介入正在下载或搬运的源文件。只处理已经完整进入 `symedia_gd/tvshows` 的项目；执行期间暂停 Symedia，避免“一边移动一边生成 STRM”的竞争问题。

## 安全边界

自动修复必须同时满足：

1. 只有一个源季度；
2. 集数严格为 `E01..EN`，无缺集、无重复；
3. `N` 与 TMDB 所有正常季度集数总和完全一致；
4. 网盘视频数量也与 TMDB 总数完全一致；
5. 目标文件不存在，不会覆盖任何已有文件。

任何一项不满足都标为黄色，只允许查看，不允许自动修复。宝可梦这类“发行分部与 TMDB 季度体系不同、总集数也不一致”的资源属于黄色项目，必须先建立人工边界规则。

## 部署组成

- MoviePilot 插件：`moviepilot/plugins/tvseasonrepair`
- MoviePilot 挂载示例：`moviepilot/docker-compose.season-repair.example.yml`
- Emby 本地修复端：`compose/emby-tg-notifier/app/season_repair.py`
- 修复端数据：通知程序的 `data/season-repair/`，包含压缩备份和可回滚移动清单
- 通讯密钥：通知程序的 `data/season_repair_token`，权限为 `0600`，不要提交到 GitHub

MoviePilot 插件页提供：

1. 扫描现有媒体库；
2. 单项只预览；
3. 单项修复；
4. 批量预览全部绿色项目；
5. 批量修复全部绿色项目；
6. 按动作号回滚。

实际修复前必须先完成同一项目的只读预览；预览授权 30 分钟后失效。批量修复同样必须先执行“预览全部绿色项目”，避免误触后直接改动网盘。

首次扫描需要读取所有剧集的 TMDB 季度数据，耗时约几十秒。数据会缓存，后续扫描会明显更快。
