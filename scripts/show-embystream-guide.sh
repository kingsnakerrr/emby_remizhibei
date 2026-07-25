#!/usr/bin/env bash
set -Eeuo pipefail

server_ip="${1:-VPS-IP}"

cat <<EOF

================ EmbyStream 可选备用线路 ================

作用：
  EmbyStream 不生成、不复制、不同步 STRM/NFO/封面，也不建立第二套媒体库。
  它复用 Symedia 已生成并由 Emby 扫描入库的媒体路径。
  客户端通过 60001 访问时，EmbyStream 代理 Emby，并把匹配
  /CloudNAS/CloudDrive/GoogleDrive/zero/... 的播放请求改由 Google Drive API 读取。
  直接访问 8096 仍然是原 CD2 路线；60001 才是 EmbyStream 备用路线。

准备：
  1. Emby 后台 -> 高级 -> API 密钥，创建并复制 EMBY_TOKEN。
  2. 从共享云端硬盘网址或 Google Drive API 获取 GOOGLE_DRIVE_ID。
     共享盘网址常见格式：https://drive.google.com/drive/folders/共享盘ID
  3. 打开 Google Cloud Console：
     https://console.cloud.google.com/
  4. 新建或选择 EmbyStream 项目，启用 Google Drive API：
     https://console.cloud.google.com/apis/library/drive.googleapis.com
  5. Google Auth Platform -> 品牌塑造，填写应用名和联系邮箱。
  6. Google Auth Platform -> 目标对象：
     - User type 选择 External；
     - 测试阶段把团队盘账号加入 Test users；
     - 长期使用建议 Publish app 攓为 In production，避免 Testing 模式
       下 Drive refresh token 固定约 7 天失效。
  7. Google Auth Platform -> 数据访问，授权只读范围：
     https://www.googleapis.com/auth/drive.readonly

推荐方式：Web application + OAuth 2.0 Playground
  1. Google Auth Platform -> 客户端 -> 创建客户端。
  2. 类型选择 Web application，名称可填 EmbyStream Playground。
  3. 已获授权的重定向 URI 必须精确填写：
     https://developers.google.com/oauthplayground
  4. 保存，复制 Client ID 和 Client Secret。
  5. 打开：
     https://developers.google.com/oauthplayground/
  6. 右上角齿轮：
     - 勾选 Use your own OAuth credentials；
     - 填入同一组 Web Client ID / Client Secret；
     - Access type 选择 Offline；
     - Prompt 选择 Consent。
  7. Step 1 的 Input your own scopes 输入：
     https://www.googleapis.com/auth/drive.readonly
     点击 Authorize APIs，登录能访问团队盘的账号并允许。
  8. Step 2 点击 Exchange authorization code for tokens。
  9. 私下复制 Access token 和 Refresh token。不要截图、不要发给别人。
     Client ID 必须与第 4 步相同；HTTP 200 表示交换成功。

替代方式：Desktop app + EmbyStream 官方 CLI
  1. 在 Google Auth Platform 创建 Desktop app 客户端。
  2. 在有浏览器且能接收 localhost 回调的同一台电脑运行：
     embystream auth google --client-id "CLIENT_ID" --secret "CLIENT_SECRET"
  3. 无图形界面只可加 --no-browser；它仍需要 localhost 回调。
     因此纯 VPS 容易卡在回调，当前安装器推荐上面的 Playground 方式。
  4. Desktop app 与 Web application 是两套不同凭据：
     Refresh token 必须和生成它的 Client ID/Secret 配套，不能混用。

把最终值写入（权限必须保持 600）：
  /root/docker-compose/embystream/.env.private

格式：
  EMBY_TOKEN=Emby后台创建的API密钥
  GOOGLE_CLIENT_ID=Web客户端ID
  GOOGLE_CLIENT_SECRET=Web客户端密钥
  GOOGLE_DRIVE_ID=共享盘ID
  GOOGLE_ACCESS_TOKEN=Playground生成的AccessToken
  GOOGLE_REFRESH_TOKEN=Playground生成的RefreshToken
  PUBLIC_BASE_URL=http://${server_ip}

保存后执行：
  sudo /root/docker-compose/emby-stack-installer/post-auth.sh embystream
  sudo /root/docker-compose/emby-stack-installer/healthcheck.sh

验收标准：
  [OK] EmbyStream 服务、Google OAuth 和刷新调度器

  若检测到 google_drive_refresh_scheduler_due 毫秒级循环，安装器会自动停止
  EmbyStream，避免占满 CPU；此时 8096 的 CD2 主线路仍可正常使用。

使用：
  原 CD2 主线路：http://${server_ip}:8096
  EmbyStream 备用入口：http://${server_ip}:60001
  后端 60002 只供本机/反代使用，不作为 Emby 客户端地址。

安全：
  .env.private、Client Secret、Access Token、Refresh Token 禁止上传 GitHub。
  Access Token 短期过期是正常的，EmbyStream 会用 Refresh Token 自动刷新。

详细文档：
  https://github.com/kingsnakerrr/emby_remizhibei/blob/main/docs/embystream-optional.md
===========================================================
EOF
