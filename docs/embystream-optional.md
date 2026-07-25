# EmbyStream 可选备用线路

EmbyStream 是本项目最后安装的可选组件。跳过它不会影响
CloudDrive2、Symedia、Emby 和神医助手主线路。

安装器使用 `embystream-v0.0.43-p1`：它基于上游 v0.0.43
提交 `43cb11f6cbc24806116f203e6860ce31d6a4df09`，只加入本仓库中可审计的
OAuth 刷新调度器退避和最小休眠补丁。发布包由 GitHub Actions 从固定上游
提交可复现构建并生成 SHA512，避免无效 OAuth 令牌触发毫秒级循环、CPU
打满和日志暴涨。

## 它如何工作

EmbyStream **不会**同步团队盘，也不会生成 STRM、NFO、封面或第二套 Emby
媒体库。现有数据流是：

1. CD2 提供 `/CloudNAS/CloudDrive/GoogleDrive/zero` 目录；
2. Symedia 根据这个目录生成本地 STRM/NFO/图片；
3. Emby 扫描 Symedia 的输出并保存媒体源路径；
4. 客户端通过 EmbyStream 的 `60001` 前端访问 Emby；
5. EmbyStream 代理 Emby API，并在播放时识别匹配
   `/CloudNAS/CloudDrive/GoogleDrive/zero/...` 的媒体路径；
6. 匹配后由 `60002` 后端使用 Google Drive API 按 Range 读取视频。

因此：

- `http://VPS-IP:8096` 是原来的 CD2 播放入口；
- `http://VPS-IP:60001` 才是 EmbyStream 备用入口；
- `60002` 是内部后端，不应作为客户端 Emby 地址；
- 不会自动复制媒体，也不会随影片数量不断占用电影等量空间；
- 它需要现有 Emby 媒体项中的路径与配置的匹配规则一致；
- CD2/Symedia 负责目录发现和入库，EmbyStream负责播放阶段换路。

## 一、Google Cloud 准备

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)。
2. 新建或选择一个项目，例如 `EmbyStream`。
3. 打开
   [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
   并点击启用。
4. 进入 `Google Auth Platform -> 品牌塑造`，填写：
   - 应用名称：`EmbyStream`
   - 用户支持邮箱：自己的邮箱
   - 开发者联系邮箱：自己的邮箱
5. 进入 `目标对象`：
   - 用户类型选择 `External`；
   - Testing 阶段把实际访问团队盘的账号加入 `Test users`；
   - 长期使用建议点击 `Publish app`，确认状态为 `In production`。
6. 进入 `数据访问`，加入只读范围：

   ```text
   https://www.googleapis.com/auth/drive.readonly
   ```

Testing 状态下，包含 Drive 范围的离线 Refresh Token 通常会在 7 天后过期。
个人自用发布到 Production 不等于完成 Google 验证，授权时仍可能看到未验证警告。

## 二、推荐：Web application + OAuth Playground

### 创建 Web 客户端

1. 进入 `Google Auth Platform -> 客户端`。
2. 点击创建客户端，类型选 `Web application`。
3. 名称可填 `EmbyStream Playground`。
4. 在“已获授权的重定向 URI”精确添加：

   ```text
   https://developers.google.com/oauthplayground
   ```

5. 保存并复制 Client ID、Client Secret。

名称只用于识别，不影响 OAuth。Client ID 可以显示，Client Secret 不能公开。

### 生成 Token

1. 打开 [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)。
2. 点击右上角齿轮：
   - 勾选 `Use your own OAuth credentials`；
   - 填入上一步同一组 Client ID 和 Client Secret；
   - `Access type` 选择 `Offline`；
   - `Prompt` 选择 `Consent`。
3. 在 Step 1 底部 `Input your own scopes` 输入：

   ```text
   https://www.googleapis.com/auth/drive.readonly
   ```

4. 点击 `Authorize APIs`，登录能访问团队盘的账号，点击继续/允许。
5. 返回后展开 Step 2，点击
   `Exchange authorization code for tokens`。
6. 确认交换返回 HTTP 200，然后复制 Access Token 和 Refresh Token。

Token 必须与生成它的 Client ID/Client Secret 配套，不能混用不同项目或不同客户端。
不要截图 Token 页面。若已经公开，立即废弃并重新生成。

## 三、替代：Desktop app + 官方 CLI

官方 `embystream auth google` 使用 installed-app OAuth：

1. 在 Google Auth Platform 创建 `Desktop app` 客户端。
2. 在安装了 EmbyStream、具有浏览器且能接收 localhost 回调的同一台电脑运行：

   ```bash
   embystream auth google \
     --client-id "DESKTOP_CLIENT_ID" \
     --secret "DESKTOP_CLIENT_SECRET"
   ```

3. `--no-browser` 只是不自动打开浏览器，仍然依赖 localhost 回调。纯 VPS
   通常不适合这个方法，除非额外配置 SSH 端口转发。

Desktop app 与 Web application 是两种独立方式，任选一种即可。当前一键安装器使用
`.env.private` 接收 Token，推荐 OAuth Playground 方式。

## 四、VPS 配置

先安装可选组件：

```bash
sudo /root/docker-compose/emby-stack-installer/scripts/install-embystream.sh
```

编辑：

```text
/root/docker-compose/embystream/.env.private
```

填写：

```dotenv
EMBY_TOKEN=Emby后台创建的API密钥
GOOGLE_CLIENT_ID=Web客户端ID
GOOGLE_CLIENT_SECRET=Web客户端密钥
GOOGLE_DRIVE_ID=共享盘ID
GOOGLE_ACCESS_TOKEN=AccessToken
GOOGLE_REFRESH_TOKEN=RefreshToken
PUBLIC_BASE_URL=http://你的VPS域名或IP
```

`EMBYSTREAM_ENCIPHER_KEY` 和 `EMBYSTREAM_ENCIPHER_IV` 留空即可，配置脚本会生成并持久化。

应用并检查：

```bash
sudo /root/docker-compose/emby-stack-installer/post-auth.sh embystream
sudo /root/docker-compose/emby-stack-installer/healthcheck.sh
```

看到下面这行即通过：

```text
[OK] EmbyStream 服务、Google OAuth 和刷新调度器
```

安装器还会观察启动后的日志。如果 v0.0.43 出现
`google_drive_refresh_scheduler_due` 毫秒级循环，会自动停止 EmbyStream，
避免单核长期满载和日志持续增长。此时继续使用 8096 主线路，等待上游修复，
不要用反复重启掩盖问题。

## 五、客户端使用与回退

- 添加服务器 `http://VPS-IP:60001`：走 EmbyStream Google API 备用线路；
- 保留 `http://VPS-IP:8096`：走原 CD2 主线路；
- 两个入口连接同一个 Emby 数据库、同一用户和同一媒体库，无需重新扫描；
- 如果 EmbyStream 故障，改回 8096 即可，不影响原库。

## 六、安全

- `.env.private` 权限应为 `0600`；
- 不要把 Client Secret 或 Token 上传 GitHub；
- Access Token 约一小时过期属于正常现象；
- EmbyStream 会使用 Refresh Token 自动更新 Access Token；
- Refresh Token 被撤销、客户端凭据更换或账号权限变化后需要重新授权。
