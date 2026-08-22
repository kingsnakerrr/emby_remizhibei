# Emby Telegram Notifier Multi v2

## 主要逻辑

- 顶部一个页面 = 一台 Emby 服务器
- 每台 Emby 有独立：
  - 页面名称
  - Emby 地址
  - API Key
  - 媒体库
  - 通知任务
  - 随机 Webhook 地址
- Telegram Bot：
  - 有一个“默认通知 Bot”
  - 每台 Emby 也可以单独填写自己的 Bot Token
  - 单独填写后优先使用该服务器自己的 Bot
- 同一台 Emby 的多个通知任务共用该台服务器的一条 Webhook
- 不同 Emby 服务器必须使用各自页面生成的不同 Webhook

## 初次登录

首次部署的初始账号为 `admin`，初始密码为 `admin`。登录后请立即在“登录设置”里修改。

新版密码逻辑使用带随机盐的 PBKDF2-SHA256，并兼容 v2 旧密码哈希自动迁移。修改密码必须输入当前密码，并确认两次新密码；修改成功后会退出当前会话并要求重新登录。

## 启动

```bash
docker compose up -d --build
```

访问：

```text
http://服务器IP:8787
```

## Webhook 地址为什么自动生成

程序会根据你当前浏览器打开控制页时使用的域名/IP/端口生成，例如：

```text
https://emby-notify.example.com/webhook/emby/2/RANDOM_LONG_SECRET
```

如果前面有 Nginx / Caddy / Cloudflare，需正确传递：

- X-Forwarded-Proto
- X-Forwarded-Host

Docker 已开启 proxy headers。

## Emby 中怎么设置

每台 Emby：

1. 打开该服务器页面
2. 复制“当前服务器 Webhook”
3. 到该台 Emby 的 Webhooks / 通知中添加
4. 只勾“媒体库 → 已添加新媒体 / New Media Added”

不需要为每个媒体库创建不同 Webhook。

## 安全

Webhook 使用每台服务器独立的随机 32 字节 secret，URL 中是约 43 个 URL-safe 随机字符。
页面还提供“重新生成随机 Webhook 地址”按钮，重新生成后旧地址立即失效。

随机 URL 能有效降低被扫描误触发的概率，但不等于完整鉴权。
建议：
- 控制面板不要直接裸露公网，最好放 Nginx/Caddy/Cloudflare Access 后面
- 修改默认 admin/admin
- 尽量使用 HTTPS


## 浏览器密码管理器

登录表单和修改密码表单使用标准字段语义：

- `autocomplete="username"`
- `autocomplete="current-password"`
- `autocomplete="new-password"`

这能让 Chrome / Edge 等浏览器正确识别登录和修改密码流程。浏览器是否弹出“保存/更新密码”仍受浏览器自己的密码管理设置、HTTPS/站点策略等影响，但本项目已按常规 Web 登录表单处理。


## v4：本机 Emby 容器检测与地址提示

控制页会尝试读取本机 Docker 容器列表，并识别可能的 Emby 容器。

如果检测到 Emby 容器，会显示：

```text
http://<Emby容器名>:8096
```

并提供“填入”按钮。

只有当 Emby 容器和 `emby-tg-notifier` 容器处于同一个 Docker network 时，容器名访问才可靠。

为了实现自动检测，`docker-compose.yml` 默认挂载：

```text
/var/run/docker.sock:/var/run/docker.sock
```

这让应用能够读取 Docker 容器元数据。若你不需要自动检测，可以删除这行，手动填写 Emby 地址。

### Webhook 两种地址

页面会同时显示：

1. 本机 Docker 内网地址
   `http://emby-tg-notifier:8787/webhook/...`
2. 当前页面公网 IP / 域名地址
   `https://你的域名/webhook/...`

同机且同 Docker 网络时优先使用第 1 个；否则使用第 2 个。


## v5：本机 Emby 一键联网

v5 不再要求用户手工执行：

```bash
docker network create emby-notify-net
docker network connect emby-notify-net emby
docker network connect emby-notify-net emby-tg-notifier
```

新逻辑：

1. 通知程序每次启动时自动检查并创建 `emby-notify-net`
2. 自动把 `emby-tg-notifier` 自己加入该网络
3. 页面检测到本机 Emby 容器但尚未共享网络时，显示“一键连接本机 Emby”
4. 点击后自动把选中的 Emby 容器加入 `emby-notify-net`
5. 程序从通知容器内部测试 `http://<Emby容器名>:8096`
6. 测试成功后自动保存 Emby 地址

这样即使以后删除并重新创建通知容器，通知程序启动时也会自动把自己重新接回 `emby-notify-net`。

> 自动联网功能依赖 `/var/run/docker.sock` 挂载。Docker socket 权限很高，只建议在你自己信任的 VPS 上使用。


## v6：修复 Emby Webhook 测试 BadRequest

Emby Webhook 可以使用 `application/json` 或 `multipart/form-data`。

此前版本只按 JSON 读取请求，因此当 Emby 选择 `multipart/form-data` 时，“发送测试通知”可能得到 `BadRequest`。

v6 同时支持：

- `application/json`
- `multipart/form-data`（JSON 通常位于 `data` 字段）
- 对部分不规范 multipart 请求增加原始 body JSON 兜底解析

另外，Emby 的 `system.webhooktest` 测试事件会明确返回 HTTP 200，但不会发送 Telegram 通知。


## v7：Webhook 测试反馈 + 保存不刷新

### Emby 测试通知
v7 正式识别 Emby 4.9 的测试事件：

```text
system.notificationtest
```

也兼容 `system.webhooktest`。

控制页新增“最近 Webhook”状态，约每 3 秒自动刷新，显示：

- 最近事件
- Emby 服务器名称
- 接收时间
- 处理结果
- Telegram 发送数量

每台 Emby 页面还可勾选：

```text
Emby“发送测试通知”时同步发送 Telegram 测试消息
```

开启后，Emby 点击“发送测试通知”时，会向该服务器所有已启用任务中的频道发送测试成功消息；相同频道去重，只发送一次。

### 保存按钮不再清空其它输入
以下操作改为页面内 AJAX 保存，不再整页刷新：

- 保存此服务器
- 保存通知 Telegram Bot
- 只修改登录账号（不改密码）

因此其它区域尚未保存的输入不会被清空。

修改密码仍保留标准 HTML 表单提交并成功后退出登录，以继续兼容 Chrome/Edge 的密码管理器识别。提交前会暂存其它非密码输入，重新登录后继续保留。

对于刷新媒体库、添加任务、Telegram 测试等仍需要页面重新载入的操作，v7 会使用浏览器 `sessionStorage` 暂存当前页面其它未保存输入，并在载入后自动恢复。

## v8：入库质量、文件大小与电视剧格式

通知会尽量从 Emby 的完整 Item / MediaSources / MediaStreams 与文件路径中读取技术信息。
如果 Webhook 自身字段不完整，程序会再通过 Emby API 获取完整媒体信息。

示例电影：

```text
🌟 质量：BluRay REMUX 1080p DTS-HD MA 5.1
💾 大小：35.7G
```

质量识别目前包含常见的 BluRay、REMUX、WEB-DL、WEBRip、HDTV、DVD、2160p/1080p/720p、DV、HDR，以及 DTS-HD MA、DTS-HD、TrueHD、DTS、E-AC-3、AC-3、FLAC、AAC 和声道数。

电视剧单集显示示例：

```text
🎬 剧名
📺 TVshow · S01季 · E03集 · 单集标题
🏷 类型：TVshow
🌟 质量：WEB-DL 1080p E-AC-3 5.1
💾 大小：2.4G
```

## v9：修复 .strm 质量 / 大小获取

v9 修复了 v8 对 Emby `library.new` 的媒体技术信息补全逻辑。

对于 `.strm`，Webhook 通常只包含条目本身，普通 Item 查询也可能返回 `Size: 0`、`MediaStreams: []`。v9 会按以下顺序自动补全：

1. Webhook 自带的 `MediaSources/MediaStreams`
2. `/Users/{UserId}/Items/{ItemId}`
3. `/Items/{ItemId}/PlaybackInfo?UserId={UserId}`

其中 PlaybackInfo 可解析 `.strm` 指向的真实 MP4/MKV，并获取：

- 文件大小
- 2160p / 1080p / 720p
- H264 / HEVC / AV1 / VP9
- SDR / HDR / Dolby Vision（Emby 有数据时）
- AAC / AC-3 / E-AC-3 / DTS / DTS-HD / DTS-HD MA / TrueHD / FLAC
- 2.0 / 5.1 / 7.1 声道

例如：

```text
🏷 类型：Movie
🌟 质量：1080p H264 SDR AAC 2.0
💾 大小：4.8G
```

电视剧 Episode 继续显示：

```text
🏷 类型：TVshow
📺 TVshow · S02季 · E05集 · 单集标题
```

v9 会自动遍历该 Emby API 可见的用户，找到能读取当前 Item 的用户，因此无需在控制面板额外填写 UserId。

## v10
- 修复 HTTP 管理页面下“复制本地地址 / 复制公网地址”按钮无效的问题。
- HTTPS/安全上下文优先使用 Clipboard API；普通 HTTP 页面自动回退到传统复制方式。
- 复制成功后按钮显示“✓ 已复制”；若浏览器仍拦截，则自动选中文本并提示按 Ctrl+C。
