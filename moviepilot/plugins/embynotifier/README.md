# Emby 入库通知 MoviePilot 管理插件

该插件在 MoviePilot 插件页显示同机 `emby-tg-notifier` 服务状态、通知任务数量和控制台入口。

通知核心、SQLite 数据库和 Telegram Bot 运行在独立 Docker 容器中，不依赖 MoviePilot 进程。媒体库任务的启用、停用及频道设置在独立控制台完成。
