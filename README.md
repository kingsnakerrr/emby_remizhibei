# Emby 团队盘一键安装器

这是为 Ubuntu/Debian VPS 准备的 Emby 团队盘播放环境安装器，用于部署并恢复：

- CloudDrive2 挂载 Google 团队盘；
- Symedia 生成 STRM/NFO 等本地媒体元素；
- Emby 扫描入库并直连播放；
- Emby 播放预热器自动预读冷片源头尾，缓解第一次起播慢；
- Emby STRM 图片补齐器自动补齐多版本 STRM 缺失的本地封面；
- Emby STRM 中文标题监控按中文文件夹名自动修正刮削后残留的英文标题；
- EmbyStream 作为最后按需安装的可选备用线路，通过 Google Drive API 读取；
- Rclone 网页控制台把另一团队盘中的 STRM/NFO/图片单向增量同步到本地；
- 神医助手在用户自行安装和授权后应用已验证的播放相关设置。

仓库只包含安装代码和无密码优化模板，不包含影片、STRM、NFO、封面、账号、
OAuth Token、License、神医商业插件或授权文件。

## 一行安装

```bash
curl -fsSL https://raw.githubusercontent.com/kingsnakerrr/emby_remizhibei/main/install.sh \
  -o install.sh && sudo bash install.sh
```

单文件 `install.sh` 会从 GitHub 下载完整安装器到
`/root/docker-compose/emby-stack-installer`，随后自动：

- 执行 `apt update`，但不升级内核、GRUB或整套系统；
- 安装 curl、证书、Python、SQLite、jq、age、Nginx、FUSE 等依赖；
- 从 Docker 官方仓库安装 Docker Engine、Buildx 和 Compose v2；
- 启动交互式安装向导。

安装器只支持 Ubuntu/Debian。业务安装器默认不执行 `apt upgrade`，因为部分
云厂商使用定制启动盘，升级 `grub-pc` 可能找不到原设备并导致 `dpkg` 中断。
如果上次安装已经遇到这种情况，重新运行同一条命令会自动修复未完成的
`grub-pc/dpkg` 状态后继续。完整日志保存在：

```text
/var/log/emby-stack-installer.log
```

如确实需要同时升级整套系统，可显式执行：

```bash
EMBY_STACK_FULL_UPGRADE=1 sudo -E bash install.sh
```

云主机建议先做快照，并优先使用厂商提供的系统升级方式。
这个 raw 一行命令要求仓库可读取；建议公开的仓库只放无密码安装器，
实际账号、OAuth、License 和神医授权继续放在加密配置备份中。

## 软件来源

| 组件 | 安装来源 | 说明 |
| --- | --- | --- |
| Docker/Compose | Docker 官方 apt 仓库 | 安装 Engine、Buildx、Compose v2 |
| CloudDrive2 | `cloudnas/clouddrive2` | 固定当前验证过的镜像摘要 |
| Emby | `amilys/embyserver` | 与当前神医环境兼容的第三方定制镜像，不是 Emby 官方镜像 |
| Emby 播放预热器 | 本仓库 `scripts/install-emby-play-prewarm.sh` | 默认安装为 systemd 服务，播放时预读 CD2 媒体头尾 Range |
| Emby STRM 图片补齐器 | 本仓库 `scripts/install-emby-strm-image-fixer.sh` | 默认安装为 systemd timer，补齐多版本 STRM 缺失的本地图片名 |
| Emby STRM 中文标题监控 | 本仓库 `scripts/fix-emby-strm-chinese-titles.sh` | 默认安装为 systemd timer，备份数据库后修正残留英文标题 |
| Symedia | `shenxianmq/symedia` | 固定当前验证过的项目镜像摘要 |
| EmbyStream | 上游 v0.0.43 + 本仓库刷新调度补丁 | GitHub Actions 可复现构建，固定版本并校验 SHA512 |
| Rclone 同步控制台 | Debian/Ubuntu 的 `rclone`、`python3-flask` | 本仓库网页服务，端口 6096 |

固定摘要是为了避免 `latest` 更新后配置或插件突然不兼容。

把当前播放架构恢复到固定路径：

```text
/root/docker-compose/
├── clouddrive2
├── emby
├── emby-tools
├── emby-play-prewarm
├── embystream
├── rclone-sync
└── symedia
```

同时创建：

```text
/CloudNAS/CloudDrive
/home/symedia_gd
/home/symedia_jav
```

## 能自动完成

- 安装/检查 Docker、Compose、Python、SQLite、curl、age。
- 创建全部固定目录和 Docker Compose 文件。
- 使用当前验证过的 CD2 1.0.12、Emby 4.9.1.80 镜像摘要。
- 预先设置 CD2 挂载点 `/CloudNAS/CloudDrive`。
- 预设 CD2 系统优化参数。
- 用户在 CD2 添加 `/GoogleDrive` 后，一键应用下载器和磁盘缓存参数。
- 创建 Symedia、Emby 的固定目录和容器；选择备用线路时再创建 EmbyStream 服务。
- 默认安装 Emby 播放预热器；CD2、Emby 和媒体库准备好后自动生效。
- 固定 Symedia 为当前服务器已验证的镜像摘要，避免 `latest` 漂移。
- 用户在向导最后选择后才安装 EmbyStream v0.0.43-p1，并校验本仓库发布包 SHA512。p1 修复 OAuth 失败时刷新调度器忙循环导致的 CPU 和日志暴涨。
- 在神医助手已安装后，一键应用播放相关设置和凌晨任务。
- 默认安装 STRM 图片补齐器，每 30 分钟补齐多版本 STRM 的 `*-poster/fanart/clearlogo`。
- 默认安装 STRM 中文标题监控，每 15 分钟纠正刮削后残留的英文展示标题。
- 安装 Rclone 和 6096 网页控制台，支持上传并验证 `rclone.conf`、浏览远程目录、手动和定时单向同步。
- 检查挂载传播、路径、服务和敏感文件。
- 可选生成不包含媒体数据的 `age` 加密配置备份。

## 必须手动完成

1. CD2 第一次登录。
2. 在 CD2 添加 Google Drive，目录名必须设为 `/GoogleDrive`。
3. Google 团队盘 `zero` 必须能在 `/GoogleDrive/zero` 中看到。
4. Emby 第一次创建管理员，或恢复加密的完整 `/config`。
5. Symedia License 和需要登录的第三方服务。
6. 神医助手 PRO 插件程序和授权；仓库不分发 PRO DLL。
7. 可选 EmbyStream 的 Emby Token 和 Google OAuth；跳过不影响主线路。
8. 在 6096 控制台上传 `rclone.conf`，选择备份团队盘目录和本地目标目录。

账号、OAuth、License 不能写进 GitHub，即使仓库是私有的。

## 全新安装

```bash
git clone https://github.com/kingsnakerrr/emby_remizhibei.git
cd emby_remizhibei
chmod +x install.sh setup-wizard.sh post-auth.sh healthcheck.sh scripts/*.sh
sudo ./setup-wizard.sh
```

`setup-wizard.sh` 是交互式一键安装入口。它会自动安装软件、创建路径并写入
优化配置；遇到必须通过网页完成的 CD2/Google 授权、Emby 初始化时会暂停。
Symedia License 使用隐藏输入，不会写入终端历史。安装器不会索取或保存
Google、CD2、Emby 的登录密码。

安装结束后：

1. 打开 `http://VPS-IP:19798`。
2. 登录 CD2，添加 Google Drive，名称设为 `/GoogleDrive`。
3. 确认后台能看到 `/GoogleDrive/zero`。
4. 运行：

   ```bash
   sudo ./post-auth.sh cd2
   ```

5. 打开 `http://VPS-IP:8096` 完成 Emby 初始化。
6. 安装并授权神医助手 PRO（兼容 3.0.0.49 单文件配置及旧版多文件配置），重启 Emby。
7. 运行：

   ```bash
   sudo ./post-auth.sh strm-assistant
   ```

8. 在 `/root/docker-compose/symedia/.env` 填写：

   ```text
   SYMEDIA_LICENSE_KEY=自己的License
   ```

9. 启动 Symedia：

   ```bash
   cd /root/docker-compose/symedia
   docker compose up -d
   ```

10. 打开 `http://VPS-IP:6096` 配置团队盘元素文件同步。默认账号和密码均为
    `admin`，首次登录必须修改。详细说明见
    [Rclone 单向同步控制台](docs/rclone-sync-web.md)。

11. EmbyStream 是可选备用线路。完整的 Web application、OAuth Playground、
    Desktop app 和 SSH 教程见
    [EmbyStream 可选备用线路](docs/embystream-optional.md)。选择安装后配置 OAuth 并运行：

    ```bash
    sudo ./scripts/install-embystream.sh
    sudo ./scripts/show-embystream-guide.sh VPS-IP
    sudo ./post-auth.sh embystream
    ```

12. 验收：

    ```bash
   sudo ./healthcheck.sh
   ```

## Emby 播放预热器

一键安装会默认安装并启动 `emby-play-prewarm.service`。它可以先于 CD2 授权和 Emby 媒体库配置安装；没有播放日志时只会等待，不会影响正式播放。

它的作用是监听 Emby 的真实播放请求：客户端点击播放并触发 `PlaybackInfo?IsPlayback=true` 后，后台提前读取该影片的头部 32 MiB 和尾部 4 MiB，让 rclone/CD2/团队盘冷片源先热起来。直连 `8096`、HTTPS `443`、Nginx 反代、BWG/BWGG 中转都能触发，只要最终请求进入同一台 Emby。

检查服务是否运行：

```bash
systemctl is-active emby-play-prewarm.service
```

输出 `active` 表示服务正在运行。也可以用总体验收：

```bash
sudo ./healthcheck.sh
```

其中应看到：

```text
[OK]   Emby 播放预热器
```

检查预热是否真的生效：

```bash
journalctl -u emby-play-prewarm.service -f
```

然后用 Emby、小幻、RodelPlayer 或其他客户端点击一部电影播放。看到类似下面内容表示已经捕获并预热成功：

```text
schedule item=564916 user=...
prewarm item=564916 container=mkv head={'status': 206, 'bytes': 33554432, ...} tail={'status': 206, 'bytes': 4194304, ...}
```

其中 `head status=206` 和 `tail status=206` 表示头尾 Range 都读成功。完整说明见
[Emby 播放预热器](docs/emby-play-prewarm.md)。

手动重装或卸载：

```bash
sudo ./post-auth.sh play-prewarm
sudo ./scripts/install-emby-play-prewarm.sh uninstall
```

## Emby STRM 图片补齐器

一键安装会默认安装并启用 `emby-fix-strm-images.timer`。它用于修复多版本 STRM
常见的空封面问题：同一电影文件夹里 1080p 有 `*-poster.jpg`，但 2160p 缺少
对应 `*-poster.jpg` 时，Emby 可能只给其中一个版本显示封面。

补齐器默认只扫描：

```text
/home/symedia_gd/movies
/home/symedia_rclone_zero/movies
```

它只复制同一电影文件夹里已有的 `poster.jpg`、`fanart.jpg`、`clearlogo.png`
或其他版本图片，不下载、不覆盖、不改 STRM/NFO/视频。

检查是否运行：

```bash
systemctl is-active emby-fix-strm-images.timer
```

手动运行一次：

```bash
sudo ./scripts/install-emby-strm-image-fixer.sh run
```

查看日志：

```bash
journalctl -u emby-fix-strm-images.service -n 100 --no-pager
```

看到 `COPY|...` 表示补齐了图片；看到 `changed=0` 表示当前没有缺图。完整说明见
[Emby STRM 图片补齐器](docs/strm-image-fixer.md)。

手动重装或卸载：

```bash
sudo ./post-auth.sh strm-image-fixer
sudo ./scripts/install-emby-strm-image-fixer.sh uninstall
```

## Emby STRM 中文标题监控

如果文件夹已经是中文名，但 Emby 海报墙仍显示 `Rebel Ridge`、
`Spider-Man: No Way Home` 这类英文标题，通常是 NFO 或 Emby 数据库里保留了旧标题。
普通刷新元数据有时不会覆盖它。

安装自动监控：

```bash
sudo ./post-auth.sh strm-title-fixer
```

先预览：

```bash
sudo ./scripts/fix-emby-strm-chinese-titles.sh dry-run
```

手动修一次：

```bash
sudo ./post-auth.sh strm-title-fixer apply
```

监控每 15 分钟预检一次；只有发现英文标题时才会短暂停止 Emby，备份 `library.db`，
再按 STRM 所在电影文件夹的中文名修正 `Name` 和 `SortName`。完整说明见
[Emby STRM 中文标题监控](docs/strm-title-fixer.md)。

## 神医助手导入

商业插件 DLL 和授权文件不要明文提交 Git，即使仓库是 Private。备份脚本生成的
配置恢复包会通过 `age` 加密保存 `plugins/StrmAssistantPro.dll`、授权文件和神医 JSON，
使用 `setup-wizard.sh --restore` 时会自动恢复，无需再次导入。

如果已经用文件管理器直接上传到 Emby 最终目录：

```text
/root/docker-compose/emby/config/plugins/
├── StrmAssistantPro.dll
└── configurations/
    ├── 授权ID文件
    └── 授权文件.lic
```

直接重新运行一键安装命令即可。向导会自动识别这些文件，备份现有插件、修正权限、
重启 Emby 并应用神医助手优化，不再要求使用中转目录。已经完成的 CD2 授权和 Emby
首次初始化也会自动跳过，适合 SSH 断线后继续。

全新安装也可以先在 VPS 中转目录准备：

```text
/root/strm-assistant-import/
├── StrmAssistantPro.dll
└── configurations/
    ├── 授权ID文件
    └── 授权文件.lic
```

一键向导会询问是否导入；也可以稍后执行：

```bash
sudo ./scripts/install-strm-assistant-local.sh /root/strm-assistant-import
sudo ./post-auth.sh strm-assistant
```

脚本会停止 Emby、备份旧 DLL、复制插件和授权文件、重启 Emby，然后由
`post-auth.sh` 写入已经验证过的神医优化设置。授权如果绑定旧机器，仍需在
插件页面按发行方规则重新激活。

## 配置恢复模式

配置恢复会包含 Emby 数据库/设置、神医 JSON、CD2 登录、Symedia 配置和
EmbyStream OAuth，因此只允许保存 `age` 加密后的文件。

Symedia 的原配置不是单个配置文件。恢复包会一起保存：

- `/root/docker-compose/symedia/config/config.yaml`
- `/root/docker-compose/symedia/config/category.yaml`
- `/root/docker-compose/symedia/config/.secret_key`
- `/root/docker-compose/symedia/config/symedia.db`

其中 `.secret_key`、数据库和 YAML 必须来自同一次停机快照。只恢复
`config.yaml` 会丢失任务历史、媒体记录，并可能无法解密已保存的账号字段。

旧服务器：

```bash
sudo ./scripts/backup-encrypted.sh /root/emby-stack-backup
```

脚本会提示输入加密密码，并把大文件切成小于 GitHub Release 单文件上限的分片。
把 `*.age.part-*` 放到私有 Release 或其他私有存储，不要提交到此公开仓库的
Git 历史。

备份保留 CD2 登录、Emby 数据库和设置、神医配置、Symedia
YAML/密钥/数据库及 EmbyStream OAuth，但明确不包含：

- `/home` 下的 STRM、NFO、封面和其他已生成媒体元素；
- Emby 的 `metadata` 海报目录和 `mediainfo-json`；
- CD2 文件缓冲缓存；
- 各程序日志、转码临时文件和可重建缓存。

恢复后固定目录仍会自动创建。Symedia 可以重新生成 STRM/NFO/封面，Emby
重新扫描并按需要补齐海报；不会从 GitHub 下载或恢复任何影片文件。

新服务器：

```bash
sudo ./setup-wizard.sh --restore /path/to/backup-parts-directory
```

这条命令会先安装 Docker、Compose、Python、SQLite 和 `age`，随后直接恢复原配置，
不启动一套空白 Symedia 覆盖原状态。恢复后会检查 Symedia 关键文件和 SQLite 数据库，
再按 CD2 → Symedia/Emby → EmbyStream 的顺序启动。

## CD2 自动配置的边界

挂载点可以在登录前写入 `/Config/config.toml`，所以安装器能提前设置 `/CloudNAS/CloudDrive`。

Google 账号本身不能在没有登录/授权的情况下创建。用户完成登录并添加 `/GoogleDrive` 后，`post-auth.sh cd2` 会：

- 停止 CD2；
- 备份现有配置；
- 保留 Google 登录字段；
- 把 `/GoogleDrive` 下载参数改为 `8 / 1024 / 4096 / 256`；
- 设置目录缓存 3600 秒、持久化、读取超时 90 秒；
- 对 `/GoogleDrive/zero/media` 显式关闭整文件磁盘缓存；
- 重新启动并验证挂载。

## 安全规则

- 此仓库故意设为 Public，只放无密码安装代码，便于使用 raw 一行安装。
- 真实配置备份必须经过 `age` 强密码加密，并优先存放到私有 Release 或私有存储。
- 不要提交 `/root/docker-compose/*/config` 的真实副本。
- 不要提交 `.env.private`、OAuth JSON、Token、License、Emby 数据库。
- 建议开启 GitHub Secret Scanning。
- 管理端口 19798、60002 不应直接对全网开放。
## Rclone 多任务同步注意事项

Rclone 同步控制台已经改为多任务模式。不要把同步目标设置为 `/home`，因为 `rclone sync` 会删除目标端中云端没有的文件，可能误删本地生成的 STRM、NFO、封面、挂载目录和其他应用数据。

推荐拆成两个独立任务：

| 任务 | 云端目录示例 | 本地目录 |
| --- | --- | --- |
| symedia_gd | `media/symedia_gd` | `/home/symedia_gd` |
| symedia_jav | `media/symedia_jav` | `/home/symedia_jav` |

新版控制台会拒绝 `/home` 作为同步目标，只允许 `/home/symedia_gd` 和 `/home/symedia_jav` 及其子目录。
