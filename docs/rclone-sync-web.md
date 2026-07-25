# Rclone 单向同步控制台

控制台用于把另一台机器上传到 Google 团队盘的 STRM、NFO、封面、背景图和
字幕增量下载到本机固定目录。它不占用 CloudDrive2 的本地挂载数量，也不会
下载影片本体，除非源目录本身包含影片并且关闭了“只传元素文件”选项。

## 安装和访问

一键向导会自动安装 `rclone`、网页服务和 systemd 服务：

```text
http://VPS-IP:6096
```

默认账号、密码均为 `admin`。默认密码只能进入账号修改页，修改为至少 8 位
的新密码后才能使用同步功能。安装向导也允许直接输入自定义账号密码。

运行目录：

```text
/root/docker-compose/rclone-sync/
├── app.py
├── settings.json
├── state.json
└── logs/sync.log
```

敏感配置固定保存在：

```text
/root/.config/rclone/rclone.conf
```

网页不会显示配置中的 Token、Client Secret 或 Refresh Token，只会调用
`rclone listremotes` 读取 remote 名称。

## 使用步骤

1. 在另一台已完成 Google Drive OAuth 的电脑或 VPS 运行 `rclone config`。
2. 选择 Google Drive，并在向导中选择对应 Shared Drive/团队盘。
3. 把生成的 `/root/.config/rclone/rclone.conf` 下载到电脑。
4. 登录 6096 控制台，在“上传 rclone.conf”中上传。
5. 从下拉框选择 remote，点击“读取目录”浏览并选择备份目录。目录按名称排序并
   显示序号，可选每页 20、50、100 或全部，并可使用上一页、下一页和手动刷新。
   读取结果缓存 5 分钟，因此翻页不会反复扫描团队盘。
6. 填写本机目标，例如：

   ```text
   /home/symedia_gd
   ```

7. 首次保持“增量复制”，勾选“只传 STRM、NFO、图片和字幕”。
8. 点击“立即同步”，观察日志和本机剩余空间。
9. 验证目录、STRM 内容与 Emby 播放正常后，再启用定时同步。

## 同步语义

- `增量复制` 对应 `rclone copy`：新增和更新云端文件，但不删除本机文件。
  这是默认和推荐模式。
- `镜像同步` 对应 `rclone sync --delete-after`：让本地与云端完全一致，
  会删除本地多余文件。网页要求再次勾选确认，并设置最多删除 10000 个文件
  的安全上限。
- Google Drive 与 rclone 没有本控制台可用的秒级文件事件推送。因此这里的
  “实时更新”是轮询同步，默认每 10 分钟检查一次，可设置为 1～1440 分钟。

对于几十万小文件，控制台默认 `transfers=4`、`checkers=8`，并且不使用
`--fast-list`，避免低内存 VPS 一次把整个目录树装入内存。第一次扫描可能较慢，
后续只传发生变化的文件。

## STRM 路径要求

复制来的 STRM 必须指向本机可以访问的影片路径。例如：

```text
/CloudNAS/CloudDrive/GoogleDrive/zero/电影/影片.mkv
```

如果 STRM 写的是另一台 VPS 的域名、IP 或不同挂载路径，Emby 虽然能入库，
但无法播放，需要先批量转换成当前机器的路径。

## 运维命令

```bash
systemctl status rclone-sync-web
journalctl -u rclone-sync-web -n 100 --no-pager
tail -n 100 /root/docker-compose/rclone-sync/logs/sync.log
systemctl restart rclone-sync-web
```

如果 6096 暴露在公网，必须修改默认密码，并建议使用防火墙限制来源 IP 或放在
带 HTTPS 的反向代理后面。不要把 `rclone.conf` 提交到 GitHub。
