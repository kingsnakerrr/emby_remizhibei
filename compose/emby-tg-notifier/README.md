# Emby Telegram Notifier Multi v15.9 · JAV频道点播

## v15.9（本节优先于后续历史说明）

Windows PotPlayer 现在只保留“后台配对后直接播放”一种方式。频道点击播放时只向在线、已配对的电脑发送任务；电脑离线或未配对时明确提示，不再生成 Chrome/Edge 中转播放按钮。

安装包只有一个 `Install.cmd`，不再区分方法1和方法2。首次安装在 Telegram 私聊发送 `/pc` 完成配对；升级会保留原配对和播放器路径。

电脑端改用隐藏启动器和守护进程：Windows 登录后无 CMD 窗口运行，接收进程异常退出会在约3秒后自动重启。安装目录仍为 `%LOCALAPPDATA%\JAV-Channel-Player`。

旧 `/ps`、`/pp` 浏览器播放入口不再提供 PotPlayer 播放；旧浏览器协议关联会在升级安装时删除。

## v15.7（历史说明）

下载包包含“方法1.浏览器打开不常驻”“方法2.安装后台常驻软件”两个文件夹，各有 Install.cmd、Uninstall.cmd 和 `运行Install.cmd安装.txt`。
软件在Windows应用列表中显示为“JAV频道点播”，支持卸载、同方法覆盖升级保留配对、切换方法和RePair重新配对。
方法1只在播放期间读取并回传位置；方法2为当前用户添加登录启动和托盘接收程序，/pc配对后频道点击直达在线空闲电脑，/pc_off撤销。离线退回方法1，不积压离线播放。
仅按点击TG用户的已绑定Emby ID授权，开始及回写时实时查询Emby用户，拒绝删除/停用/禁止播放/绑定变更；不以昵称匹配、不按管理员身份写观看记录。
两种方法都读取续播，每约10秒及退出时回写Emby UserData（最近播放、PlayCount、PlaybackPositionTicks、Played）；95%后退出标记已播放。
不是原生Emby客户端会话，不保证控制台正在播放或Playback Reporting插件时长统计。关闭时使用最近有效采样，约0.5秒误差，离线/断电可能丢失最后一段未上传进度。
现有v15.6纯跳转/ SenPlayer路由保留，新PotPlayer按钮使用/ps及hdz-potplayer-sync协议，用户需要安装新组件。
后台任务仅在方法2存在；方法1仍有“播放期间同步进程”，不可称为播放时完全无后台任务。
安装包不含凭据；配对凭据DPAPI加密，服务端只存设备令牌哈希。但媒体流仍携带原服务器API Key，HTTP不加密，不能当作完整凭据隔离方案。
安装/更新前关闭本组件正在播放的影片；更新保留settings.xml。卸载只删除本机组件及其授权，不动Emby data和TG账号绑定。
升级部署需复制app/main.py、app/potplayer_sync.py及app/downloads安装包，保留data和Compose，然后重建服务。新增pp_*表，不删旧表。
构建安装包：PowerShell执行build-packages.ps1。Python测试使用模拟Emby和临时数据库；另有真实本地PotPlayer静音测试媒体验证读取位置，不能替代用户服务器上的实播验收。

进度读取接口参考：https://github.com/kjtsune/embyToLocalPlayer/blob/main/utils/players.py
PotPlayer命令行以安装目录CmdLine64.txt为准（/new、/seek、/title）。Emby字段参考官方UserData API。

当前 v15.9 验证：57 项 Python 测试通过；Windows 脚本语法与不安全 URL 检查通过；本机覆盖安装保留配对、旧浏览器协议移除、隐藏 watchdog 杀进程后自动重启均已实测。未向真实用户的 Emby 写入测试观看记录。
构建脚本包含中文目录名，请使用PowerShell 7运行；安装组件兼容Windows PowerShell 5.1。

## v15.6.1 安装包下载

PotPlayer 私聊播放按钮下增加“首次加载 PotPlayer 插件（下载安装包）”。
下载包附带 `运行Install.cmd安装.txt`，说明安装、卸载和隐私边界。
组件是浏览器跳转所用的 Windows 协议关联，不是浏览器扩展；无后台常驻、开机启动、计划任务或服务。
固定下载路由 `/downloads/potplayer-browser-launcher.zip` 仅提供公开安装文件，不含用户凭据，独立于一次性播放凭证。
升级时必须同时部署 `app/main.py` 与 `app/downloads/potplayer-browser-launcher.zip` 并重新构建镜像。
保留原消息约 10 秒清理逻辑，安装完后重新从频道获取播放按钮。

## v15.6 PotPlayer（以本节为准）

- 启用 TG 账号绑定后，新 JAV 电影通知增加「PotPlayer 播放」，保留 SenPlayer。
- 频道仅包含 callback_data；机器人私聊发送 5 分钟有效、一次性播放按钮，约 10 秒删除，点击后提前排队删除。
- 未开启绑定时不显示 PotPlayer，不提供频道公开直链回退。旧频道消息不会自动增加按钮。
- PotPlayer 是普通 URL 播放，不是原生 Emby Item 播放。本版不读取/回写 PotPlayer 进度，不附加退出网页回调；SenPlayer 设置不变。

### 第一次使用

1. 服务器备份原目录，覆盖程序文件，保留 `data` 和自定义 `docker-compose.yml`，执行 `docker compose up -d --build`。
2. 在要播放的 Windows 电脑安装 PotPlayer，然后双击本包 `windows-potplayer/Install.cmd`。找不到安装位置时选择 PotPlayer 主程序。
3. 注册工具仅为当前 Windows 用户注册本程序的 `hdz-potplayer://`，不覆盖已有 `potplayer://`，不需管理员权限。处理器复制到 `%LOCALAPPDATA%/HDZ-PotPlayer`，原安装包可以移走。
4. 通知控制台启用 TG 绑定并配置机器人、公网地址；私聊机器人绑定 Emby 账号。
5. 从新 JAV 通知点击「PotPlayer 播放」，到机器人私聊点「打开 PotPlayer」。首次浏览器可能询问是否允许打开外部应用，需要确认；不能保证完全不经过浏览器。

卸载协议：PowerShell 运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\windows-potplayer\Uninstall.ps1`。不会卸载 PotPlayer。
每台电脑/每个 Windows 用户首次都需要注册一次；本包不会自行操作你的注册表。

### 隐私与测试边界

频道和私聊消息不包含 Emby 主机、媒体直链或 API Key，但私聊按钮本身是短期持有者凭证，删除消息不等于他人保存的链接立即失效。
播放器最终仍收到带服务器 API Key 的 Emby 视频 URL（与原 SenPlayer 相同）；Base64 只是协议传输编码，不是加密。浏览器跳转/播放器历史可能保留地址。本版不是完整凭据隔离方案，不应向不可信用户开放。
PotPlayer 通过当前绑定校验后直连 Emby，不要求 Windows 挂载 CD2；Windows 必须能访问配置的视频地址。
Windows 协议处理器只接受 HTTP(S) 地址，不使用 `cmd /c` 或脚本表达式执行传入内容。
本地自动测试使用模拟 Telegram/Emby；未完成真实服务器、TG 和 PotPlayer 联合实播验证。
验证结果：27 项 Python 测试通过；Windows PowerShell 5.1 下 13 项处理器地址校验通过，安装/卸载脚本语法检查通过；测试未改动注册表或启动真实播放器。

以下为历史说明；其中“仅 SenPlayer”描述只适用于 v15.5。

## v15.5

移除新增的 Emby 播放按钮及功能，恢复 v15.1 的 SenPlayer 播放逻辑。不包含 Scriptable。
保留管理员 ID、机器人 Token、TG 绑定、绑定成功提示、消息删除队列和退出进度回写开关。
v15.3/v15.4 的旧 Emby 链接返回 410，旧频道 Emby 回调按钮只提示功能已移除，不创建播放凭证、不调用 Emby 播放。
保留已有数据库和绑定数据，包括不再使用的 Emby 凭证表；不进行破坏性数据库回退。

升级：备份原目录，覆盖程序文件，保留原 data 和自定义 docker-compose.yml，在原目录执行 `docker compose up -d --build`。
新发出的 JAV 通知只带 SenPlayer 按钮。以前已发到频道的消息不会自动编辑，旧 Emby 按钮会失效。
本版仅撤销 Emby 按钮方案，不宣称修复 SenPlayer 退出返回 Safari 的客户端行为。

以下为保留的 v15.1 使用说明。

## v15.1 试用说明（后文旧版本说明以此处为准）

- 所有三个 SenPlayer 入口遵守退出进度回写开关；关闭时不附加 x-success。
- 无论是否启用退出回写，都读取已配置/已绑定用户的 Emby 已有进度续播。
- 关闭回写不代表能记录本次退出位置，也不保证 iOS 不会返回启动播放前的浏览器。
- Telegram 私聊播放消息与 /start、/help 命令约 10 秒后删除；点击播放时提前排队删除。删除网络请求不再阻塞播放器启动。
- 删除队列存入原 SQLite 数据库，重启后继续；失败最多尝试 6 次。Token 被删除/更换、Telegram 拒绝请求时可能仍无法删除，日志会记录结果。
- 播放凭证有效期独立延长为 5 分钟，仍为一次性凭证；消息仍约 10 秒删除。
- 无效/缺失/负数/非有限播放位置不再按 0 秒覆盖续播记录；关闭回写时旧回调不再写入。
- /bindings 按当前机器人和该管理员负责的服务器过滤结果。
- 保留机器人 Token、管理员 ID 输入和按服务器名称生成的绑定成功提示。

### 升级试用

1. 在原部署目录备份 data 目录及已有程序文件。
2. 将本压缩包解压覆盖原程序文件，保留原 data 和自定义 docker-compose.yml。
3. 在原部署目录运行 `docker compose up -d --build`。
4. 控制台各服务器取消勾选“退出时回写 SenPlayer 播放进度”并保存。已有开启设置不会自动改变。
5. 重新点击频道播放按钮，测试退出、10 秒删除及已有进度续播；升级前已经打开的播放器仍可能持有旧回调。
6. 删除异常时查看 `docker compose logs --tail=200 emby-tg-notifier` 中的 `[TG cleanup]`。

### 范围与验证

这是播放/清理稳定性修正版，未重做媒体鉴权。媒体直链仍携带原有服务器 API Key，现有绑定校验不等于完整的 Emby 用户播放权限校验；不要将本版当作凭据隔离修复版。
没有接入真实 Telegram、Emby 或 iPhone。自动测试使用临时 SQLite 和模拟 API，运行方式：安装 requirements.txt 后执行 `python -m unittest discover -s tests -v`。
回退时停止容器、恢复备份的程序及 data，再重新构建启动。

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
\n\n## v11：JAV NFO 女优与类型识别\n\n- 对 `/home/symedia_jav/`、`/media/jav/` 等 JAV 路径自动显示 `类型：JAV`。\n- 优先读取影片同目录、同名 `.nfo`。\n- 女优优先读取所有 `<actor><name>...</name></actor>`，自动去重，并排除 `<director>` 中同名人员。\n- NFO 没有有效演员时，按目录结构 `.../<女优>/<番号>/<番号>.strm` 回退识别女优。\n- 文件夹明确写“多人”时显示“多人”；仍无法识别则显示“未知”。\n- JAV 类型从 NFO `<tag>` 读取，最多显示前 4 个有效影片标签，并过滤 4K/分辨率、番号/厂牌代码、女优名、系列/片商/发行等元数据。\n- 示例：`类型：JAV，熟女人妻、母亲、中出、巨乳`。\n- 多女优全部显示。若文字过长超过 Telegram 图片 caption 限制，会先发海报，再发送完整文字，避免发送失败。\n- `docker-compose.yml` 新增 `/home/symedia_jav:/home/symedia_jav:ro`，只读访问 NFO，不会修改 Symedia 文件。\n
## v12：Telegram → SenPlayer 播放（实验）

- 每台 Emby 页面新增两个可修改地址：
  - SenPlayer 使用的 Emby 外网地址
  - 通知程序公网地址
- 保存后，新的 Telegram 入库通知会出现 `▶️ SenPlayer 播放` 按钮。
- 按钮先打开通知程序的签名跳转页，再尝试使用：
  - `SenPlayer://x-callback-url/play?url=...`
- Telegram 按钮本身不包含 Emby API Key。
- `/senplayer-media/...` 会校验签名后 307 跳转到 Emby 静态流地址。
- 如果 Emby 地址使用 Docker 内网名（如 `http://emby:8096`），SenPlayer 外网地址必须改成 iPhone 可访问的公网 IP / 域名。
- 这是实验功能，主要用于确认 iOS Telegram → SenPlayer URL Scheme 的唤起和播放兼容性。

## v12.1：SenPlayer 302 直跳实验

- Telegram 的 `▶️ SenPlayer 播放` 仍先访问通知程序的 HTTPS/HTTP 链接。
- `/senplayer/...` 不再返回中转 HTML 页面，也不等待 JavaScript。
- 服务器立即返回 HTTP 302 到 `SenPlayer://x-callback-url/play?...`。
- 目的：减少 iOS 中浏览器中转页的加载和闪现时间。
- 如果 iOS/Telegram 对 HTTP 302 → 自定义 URL Scheme 有限制，可回退到 v12 的 HTML + JS 方式。

## v13：SenPlayer 续播 / Emby 进度回写（实验）

SenPlayer 6.1.1/6.1.2 起的更新记录说明，URL Scheme 播放支持传入播放时间，并在退出播放时返回当前播放时间。v13 利用这一能力补上外部 URL 播放与 Emby 用户进度之间的桥接。

每台 Emby 的 SenPlayer 设置新增“SenPlayer 进度同步 Emby 用户”。填写 SenPlayer 当前使用的 Emby 用户名或 UserId（例如 `test_jav`），不需要填写密码。

播放流程：

1. 点击 Telegram 的“SenPlayer 播放”。
2. 通知程序读取指定 Emby 用户在该 Item 的 `PlaybackPositionTicks`。
3. 通过 SenPlayer URL Scheme 的 `position` 参数从上次位置起播。
4. 同时传入 `x-success` 回调。
5. SenPlayer 退出播放后将当前位置回传给通知程序。
6. 通知程序调用 Emby `/Users/{UserId}/Items/{ItemId}/UserData` 更新 `PlaybackPositionTicks`；播放完成或达到 90% 时标记已播放。

说明：这是基于 SenPlayer 6.1.x URL Scheme 新能力的实验实现。若 SenPlayer 某版本的回调字段名称有变化，v13 会同时兼容 `position/time/currentTime/playbackTime/progress` 几种常见字段。退出 SenPlayer 后 iOS 可能会短暂打开回调网页，这是 x-callback-url 的工作方式。


## v13.1：SenPlayer 按钮仅用于 JAV

- 只有识别为 `JAV` 的入库通知显示 `▶️ SenPlayer 播放`。
- 普通 `Movie` 通知不显示 SenPlayer 按钮。
- `TVshow / Episode / Season` 通知不显示 SenPlayer 按钮。
- 其它 v13 功能保持不变。

## v13.2：TV 剧集批量入库自动合并

此功能只针对 Emby `Episode`，不会改变 Movie 或 JAV 通知。

- 每个单集入库时仍立即发送正常 Telegram 通知。
- 同一 Emby、同一通知任务、同一剧集、同一季，在静默窗口内继续入库的新 Episode 会归到同一批。
- 每新增一集都会重新计算静默时间，默认 30 分钟，可在服务器设置页修改（1-1440 分钟）。
- 静默时间结束时：
  - 只有 1 集：保留原单集通知，不做任何处理。
  - 2 集及以上：尝试删除本批所有临时单集通知，然后发送一条新的“Emby 批量入库完成”通知，因此 Telegram 会产生一条新的最终提醒。
- 连续集会显示为 `E01-E25`；不连续集会显示为 `E01-E03、E05-E06、E09`。
- 合并通知使用最后入库一集的海报/质量信息，并累加本批所有剧集文件大小。
- 批次记录保存到 SQLite，因此容器重启后待合并批次仍可继续处理。

注意：Telegram 删除旧消息需要 Bot 在目标群组/频道具备删除消息权限；若删除失败，最终合并通知仍会尝试发送。


## v14：Telegram 用户绑定 Emby + 按点击者同步进度

- 仅 JAV 通知使用个性化播放按钮；Movie / TVshow 不显示 SenPlayer 按钮。
- 频道按钮改为 Telegram callback，机器人可以拿到实际点击者的 Telegram User ID。
- 用户私聊同一个通知 Bot，发送 `/start`：绑定、取消绑定、查看绑定。
- 绑定流程：选择 Emby（多服务器时）→ 输入 Emby 账号 → 输入 Emby 密码。密码只用于 `/Users/AuthenticateByName` 即时验证，不写入数据库；程序会尝试删除密码消息。
- 数据库只保存 `Telegram User ID ↔ Emby User ID/用户名`。
- 已绑定用户点频道播放按钮后，Bot 会私聊发送一个“打开 SenPlayer”按钮；该链接带该 TG 用户的签名。SenPlayer 读取该 Emby 用户的续播位置，退出后回写该用户。
- 未绑定用户点击频道播放按钮时，会提示先打开 Bot 完成绑定。
- 管理后台可为每台 Emby 开启绑定功能并填写 Bot ID；Bot Token 继续使用已有通知 Bot Token。
- 管理员 Telegram ID 支持多个，管理员同样需要绑定；可用 `/bindings` 查看最近绑定。

### Telegram 限制说明

Telegram 的 callback 按钮能告诉 Bot“谁点击了”，但 callback 不能直接跳转任意 SenPlayer 自定义 Scheme。因此个性化模式需要两次点击：频道里的“SenPlayer 播放” → Bot 私聊 → “打开 SenPlayer”。这是为了准确绑定播放进度到点击者自己的 Emby 账号。


## v14.1
- 移除 TG 用户绑定区域中多余的“TG 机器人 ID”手工输入。
- 用户绑定自动复用实际发送该服务器入库通知的 Bot Token：服务器独立 Bot 优先，否则使用默认通知 Bot。
- 管理员 Telegram ID 继续在“通知 Telegram Bot”区域设置；管理员可使用 `/bindings`。
- 保留旧数据库字段仅用于升级兼容，v14.1 不再依赖该字段。


## v14.2
- TG 绑定区域新增“绑定 Emby 机器人 Token（可选）”和“绑定机器人管理员 Telegram ID”。
- 绑定 Bot Token 留空时直接使用当前通知 Bot；填写独立 Token 时，该 Bot 同时负责本服务器通知，保证频道 callback 能识别点击者。
- 移除手工填写机器人 ID；Bot ID 由 Telegram getMe 自动识别。
- `/start` 菜单文案简化，只展示绑定、取消绑定、查看绑定等操作。
- 绑定成功消息使用管理页的服务器页面名称，例如：`绑定“惹咪之北影视服_HDZ”成功，愉快的屌之北吧。`
- 管理员 ID 改为每台 Emby 独立设置，管理员可使用 `/bindings`。

## v14.5：播放后自动清理 TG 私聊播放按钮

- 保持 v14.4 的播放架构：频道按钮先校验 TG 用户绑定，机器人私聊发送一次性 `/sp/<token>` 播放入口，通知程序只做鉴权和 302 跳转，视频仍由 SenPlayer 直连 Emby/CD2，不经过 8787 转发。
- 机器人发送“▶️ 打开 SenPlayer”私聊消息后，会把该消息的 `chat_id/message_id` 关联到一次性播放票据。
- 当用户真正点击“▶️ 打开 SenPlayer”、`/sp/<token>` 第一次被消费时，程序会立即删除这条机器人私聊播放消息，然后继续跳转 SenPlayer。
- 删除失败不会影响播放；一次性 token 仍保持短时有效、首次使用后失效。
- SenPlayer 退出后的进度回调仍按原逻辑写回对应绑定的 Emby 用户。由于 SenPlayer 的 x-callback 会打开 HTTP 回调地址，iOS 仍可能短暂切到 Safari；v14.5 主要解决 TG 私聊里播放按钮越积越多的问题。

## v14.6：绑定成功后自动清理 TG 绑定聊天记录

- 用户通过 `/start` / 绑定菜单输入 Emby 账号、密码完成绑定后，自动删除本次绑定过程中产生的聊天记录：绑定提示、用户账号消息、密码提示、密码消息，以及失败后重试产生的错误提示。
- 最终只保留绑定成功确认消息。
- 密码仍然只用于当次 Emby 验证，不写入数据库。
- 播放按钮点击后的私聊播放消息自动删除逻辑继续保留。

## v14.7：Telegram 私聊自动清理

- `/start` / `/help` 触发的绑定菜单，10 秒未操作自动删除。
- 点击绑定菜单按钮后，菜单消息立即删除；多服务器选择菜单同样如此。
- Emby 账号/密码验证失败时，清理本次失败绑定过程中的账号、提示等记录；失败提示本身 10 秒后自动删除。
- `/cancel` 会清理当前绑定过程消息，取消提示 10 秒后自动删除。
- 从频道点击 JAV 播放后，Bot 私聊发送的“打开 SenPlayer”消息与按钮仅保留 10 秒；10 秒不点击会自动删除，同时一次性播放票据也在 10 秒后失效。
- 若在 10 秒内点击“打开 SenPlayer”，消息会在播放入口被打开时立即删除。
- 以上只影响 Bot 私聊临时消息，不影响频道入库通知和已保存的 Emby/TG 绑定关系。

## v14.8：修复 Telegram 10 秒自动清理

修复 v14.7 中临时消息的延迟删除任务可能在 10 秒前被 Python 回收，导致消息一直保留的问题。

现在：

- 私聊 `/start` / `/help` 后，用户发送的命令消息 10 秒后删除；机器人弹出的绑定菜单也在 10 秒后删除。
- 绑定菜单/服务器选择菜单一旦点击，菜单消息立即删除。
- 从频道点击 JAV 的 SenPlayer 播放后，机器人私聊中的“打开 SenPlayer”消息：
  - 10 秒内没有点击：自动删除；一次性播放凭证同时失效。
  - 10 秒内点击：`/sp/...` 被打开时立即删除该私聊播放消息，然后 302 跳转 SenPlayer。
- Telegram `deleteMessage` 失败不再静默吞掉；Docker 日志会打印 `[TG cleanup]`，便于继续排查 Bot 权限或 Token 问题。
- 删除播放消息时会尝试当前服务器可能使用的通知 Bot / 绑定 Bot Token，避免切换独立 Bot 后因 Token 不匹配导致删不掉。


## v14.9：修复 Telegram 临时消息 10 秒自动删除

修复 v14.7/v14.8 的实际代码错误：延迟删除函数被定义成 `async def`，但多个调用点采用 fire-and-forget 方式直接调用，导致协程根本没有执行，所以 `/start` 菜单和 SenPlayer 私聊播放按钮不会按 10 秒自动删除。

v14.9 将该调度函数改为同步调度器，内部再创建受强引用保护的 asyncio 后台任务：

- `/start` / `/help` 用户命令：10 秒后删除；
- `/start` 弹出的绑定菜单：10 秒不操作自动删除；
- 菜单按钮点下后仍立即删除菜单；
- 频道点击 JAV 后私聊生成的“打开 SenPlayer”消息：10 秒不点自动删除；
- 10 秒内点击 SenPlayer：`/sp/` 路由会立即删除对应私聊播放消息；
- 删除失败会在 Docker 日志打印 `[TG cleanup]`，方便继续定位 Bot API 权限或 Token 问题。
