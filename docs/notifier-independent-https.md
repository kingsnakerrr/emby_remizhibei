# 入库通知控制台独立 HTTPS 域名

Chrome Cookie 不按端口隔离。同一主机名上的 `:8787` 控制台可能与其他服务共享
同名 Cookie，因此推荐为通知控制台分配独立主机名，并仅通过 Nginx HTTPS 访问。

生产部署要点：

- DNS 为独立主机名解析到 VPS；
- Nginx `443` 反向代理 `127.0.0.1:8787`；
- Compose 端口改为 `127.0.0.1:8787:8787`，不再直接暴露公网；
- 设置 `SESSION_HTTPS_ONLY=1`，让登录 Cookie 只通过 HTTPS 发送；
- 控制台中的“通知程序公网地址”改为独立 HTTPS 地址；
- SSL 证书交给 Certbot 定时续期。

示例环境配置：

```yaml
ports:
  - "127.0.0.1:8787:8787"
environment:
  - SESSION_HTTPS_ONLY=1
```

不要把管理员密码、Bot Token、Emby API Key 或会话密钥提交到 GitHub。
