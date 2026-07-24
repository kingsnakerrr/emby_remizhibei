# Emby 团队盘一键安装器

这是为 Ubuntu/Debian VPS 准备的 Emby 团队盘播放环境安装器，用于部署并恢复：

- CloudDrive2 挂载 Google 团队盘；
- Symedia 生成 STRM/NFO 等本地媒体元素；
- Emby 扫描入库并直连播放；
- EmbyStream 通过 Google Drive API 提供另一条读取线路；
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

- 执行 `apt update` 和安全的常规 `apt upgrade`；
- 安装 curl、证书、Python、SQLite、jq、age、Nginx、FUSE 等依赖；
- 从 Docker 官方仓库安装 Docker Engine、Buildx 和 Compose v2；
- 启动交互式安装向导。

安装器只支持 Ubuntu/Debian。内核升级需要重启时只会提示，不会自动重启。
这个 raw 一行命令要求仓库可读取；建议公开的仓库只放无密码安装器，
实际账号、OAuth、License 和神医授权继续放在加密配置备份中。

## 软件来源

| 组件 | 安装来源 | 说明 |
| --- | --- | --- |
| Docker/Compose | Docker 官方 apt 仓库 | 安装 Engine、Buildx、Compose v2 |
| CloudDrive2 | `cloudnas/clouddrive2` | 固定当前验证过的镜像摘要 |
| Emby | `amilys/embyserver` | 与当前神医环境兼容的第三方定制镜像，不是 Emby 官方镜像 |
| Symedia | `shenxianmq/symedia` | 固定当前验证过的项目镜像摘要 |
| EmbyStream | `PiliPili-Team/EmbyStream` GitHub Release | 固定版本并校验 SHA512 |

固定摘要是为了避免 `latest` 更新后配置或插件突然不兼容。

把当前播放架构恢复到固定路径：

```text
/root/docker-compose/
├── clouddrive2
├── emby
├── embystream
└── symedia
```

同时创建：

```text
/CloudNAS/CloudDrive
/home/fufu
/home/fufu2
/home/test
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
- 创建 Symedia、Emby、EmbyStream 的目录、容器/服务骨架。
- 固定 Symedia 为当前服务器已验证的镜像摘要，避免 `latest` 漂移。
- 安装 EmbyStream v0.0.43 并校验官方 SHA512。
- 在神医助手已安装后，一键应用播放相关设置和凌晨任务。
- 检查挂载传播、路径、服务和敏感文件。
- 可选生成不包含媒体数据的 `age` 加密配置备份。

## 必须手动完成

1. CD2 第一次登录。
2. 在 CD2 添加 Google Drive，目录名必须设为 `/GoogleDrive`。
3. Google 团队盘 `zero` 必须能在 `/GoogleDrive/zero` 中看到。
4. Emby 第一次创建管理员，或恢复加密的完整 `/config`。
5. Symedia License 和需要登录的第三方服务。
6. 神医助手 PRO 插件程序和授权；仓库不分发 PRO DLL。
7. EmbyStream 的 Emby Token 和 Google OAuth。

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
6. 安装并授权神医助手 PRO 3.0.0.48，重启 Emby。
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

10. 配置 EmbyStream OAuth 后运行：

    ```bash
    sudo ./post-auth.sh embystream
    ```

11. 验收：

    ```bash
   sudo ./healthcheck.sh
   ```

## 神医助手导入

商业插件 DLL 和授权文件不要明文提交 Git，即使仓库是 Private。备份脚本生成的
配置恢复包会通过 `age` 加密保存 `plugins/StrmAssistantPro.dll`、授权文件和神医 JSON，
使用 `setup-wizard.sh --restore` 时会自动恢复，无需再次导入。

全新安装时可在 VPS 准备：

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
