# Rclone 多任务同步控制台

这个控制台用于把 Google 团队盘里的媒体元数据目录同步到本机固定目录。新版已经改成多任务模式，避免把整个 `/home` 当成同步目标。

## 重要安全规则

不要把同步目标设置成 `/home`。

原因是 `rclone sync` 是镜像同步，会删除目标端里“云端没有”的文件。如果目标是 `/home`，本地生成的 STRM、NFO、封面、挂载目录和其他应用数据都有被删除的风险。

现在程序只允许目标位于：

```text
/home/symedia_gd
/home/symedia_jav
```
推荐拆成两个任务：

| 任务 | 云端目录示例 | 本地目录 |
| --- | --- | --- |
| symedia_gd | `media/symedia_gd` | `/home/symedia_gd` |
| symedia_jav | `media/symedia_jav` | `/home/symedia_jav` |

这样每个任务只管理自己的目录，不会干涉 `/home` 下其他文件夹。

## 同步模式

- `copy`：增量复制，只新增或覆盖变化文件，不删除本地多余文件。默认推荐。
- `sync`：镜像同步，会删除本任务目标目录内云端没有的文件。只在确认目录完全对应时使用。

即使使用 `sync`，也只应该用于 `/home/symedia_gd` 或 `/home/symedia_jav` 这样的精确目录，不要用于 `/home`。

## 安装和访问

安装脚本会部署到：

```text
/root/docker-compose/rclone-sync/
```

服务名：

```text
rclone-sync-web.service
```

访问地址：

```text
http://VPS-IP:6096
```

默认账号和密码都是 `admin`。首次登录必须修改密码后才能继续使用。

## 使用步骤

1. 准备好 `/root/.config/rclone/rclone.conf`，里面应有 Google Drive 团队盘 remote。
2. 登录 6096 控制台。
3. 上传或确认 rclone 配置。
4. 分别配置 `symedia_gd` 和 `symedia_jav` 两个任务。
5. 本地目录分别填 `/home/symedia_gd`、`/home/symedia_jav`。
6. 首次建议使用 `copy` 模式跑一遍。
7. 确认文件和 Emby 入库都正常后，再决定是否启用定时同步。

## 运维命令

```bash
systemctl status rclone-sync-web
journalctl -u rclone-sync-web -n 100 --no-pager
tail -n 100 /root/docker-compose/rclone-sync/logs/sync.log
systemctl restart rclone-sync-web
systemctl stop rclone-sync-web
```

## 升级旧配置

旧版单任务配置会自动迁移成多任务配置。

如果旧配置目标是 `/home`，新版不会继续使用这个危险目标。请在控制台里分别配置：

```text
/home/symedia_gd
/home/symedia_jav
```
