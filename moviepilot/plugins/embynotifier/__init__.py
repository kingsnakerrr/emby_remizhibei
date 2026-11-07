from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.plugins import _PluginBase


class EmbyNotifier(_PluginBase):
    plugin_name = "Emby 入库通知"
    plugin_desc = "查看同机 Emby Telegram 通知服务，并进入独立通知控制台。"
    plugin_version = "1.0.1"
    plugin_author = "kingsnakerrr"
    author_url = "https://github.com/kingsnakerrr/emby_remizhibei"
    plugin_config_prefix = "embynotifier_"
    plugin_order = 30
    auth_level = 1

    _console_url = "http://takehost.222321.xyz:8787"
    _database = Path("/emby-notifier-data/app.db")

    def init_plugin(self, config=None):
        config = config or {}
        self._console_url = str(config.get("console_url") or self._console_url).rstrip("/")

    def get_state(self) -> bool:
        return True

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 12}, "content": [
                    {"component": "VTextField", "props": {
                        "model": "console_url", "label": "通知控制台地址",
                        "placeholder": "http://takehost.222321.xyz:8787",
                    }},
                ]},
                {"component": "VCol", "props": {"cols": 12}, "content": [
                    {"component": "VAlert", "props": {"type": "info", "variant": "tonal"},
                     "text": "通知核心是同机独立容器；MoviePilot 插件只负责显示状态和打开控制台，MP 更新不会删除通知数据库。"},
                ]},
            ]}],
        }], {"console_url": self._console_url}

    def _service_online(self) -> tuple[bool, str]:
        try:
            request = Request("http://127.0.0.1:8787/", method="GET")
            with urlopen(request, timeout=3) as response:
                return response.status in (200, 302, 303), f"HTTP {response.status}"
        except (OSError, URLError) as error:
            return False, str(error)

    def _summary(self) -> dict:
        result = {"servers": 0, "routes": 0, "enabled": 0, "disabled": 0, "error": ""}
        try:
            connection = sqlite3.connect(f"file:{self._database}?mode=ro", uri=True)
            result["servers"] = connection.execute("SELECT COUNT(*) FROM servers").fetchone()[0]
            result["routes"] = connection.execute("SELECT COUNT(*) FROM routes").fetchone()[0]
            result["enabled"] = connection.execute("SELECT COUNT(*) FROM routes WHERE enabled=1").fetchone()[0]
            result["disabled"] = result["routes"] - result["enabled"]
            connection.close()
        except Exception as error:
            result["error"] = str(error)
        return result

    def get_page(self) -> List[dict]:
        online, detail = self._service_online()
        summary = self._summary()
        cards = [
            ("服务状态", "运行中" if online else "未连接", "success" if online else "error"),
            ("Emby 服务器", str(summary["servers"]), "primary"),
            ("已启用任务", str(summary["enabled"]), "success"),
            ("已停用任务", str(summary["disabled"]), "warning"),
        ]
        return [{"component": "div", "content": [
            {"component": "VAlert", "props": {
                "type": "success" if online else "error", "variant": "tonal", "class": "mb-4",
            }, "text": ("通知服务已在 takehost 独立运行。" if online else f"通知服务无法访问：{detail}")},
            {"component": "VRow", "props": {"class": "mb-3"}, "content": [
                {"component": "VCol", "props": {"cols": 12, "sm": 6, "md": 3}, "content": [
                    {"component": "VCard", "props": {"variant": "tonal", "color": color}, "content": [
                        {"component": "VCardSubtitle", "text": label},
                        {"component": "VCardTitle", "text": value},
                    ]},
                ]} for label, value, color in cards
            ]},
            {"component": "VCard", "props": {"variant": "outlined"}, "content": [
                {"component": "VCardTitle", "text": "管理入口"},
                {"component": "VCardText", "content": [
                    {"component": "div", "props": {"class": "mb-3"},
                     "text": "媒体库任务的启用、停用、频道和 Bot 设置仍在独立控制台完成。切换期间请避免新旧两端同时启用同一个媒体库。"},
                    {"component": "VBtn", "props": {
                        "href": self._console_url, "target": "_blank", "color": "primary",
                        "prepend-icon": "mdi-open-in-new",
                    }, "text": "打开 Emby 通知控制台"},
                ]},
            ]},
            *([{"component": "VAlert", "props": {"type": "warning", "variant": "tonal", "class": "mt-3"},
                "text": f"无法读取通知数据库：{summary['error']}"}] if summary["error"] else []),
        ]}]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    @staticmethod
    def get_api() -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        return []

    def stop_service(self):
        pass
