from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import Body

from app.core.config import settings
from app.plugins import _PluginBase


class TVSeasonPreflight(_PluginBase):
    plugin_name = "入库前动漫自动分季"
    plugin_desc = "管理并查看下载完成后、移动上传前的绝对集数自动分季引擎。"
    plugin_icon = "tv.png"
    plugin_version = "0.2.0"
    plugin_author = "kingsnakerrr"
    author_url = "https://github.com/kingsnakerrr/emby_remizhibei"
    plugin_config_prefix = "tvseasonpreflight_"
    plugin_order = 29
    auth_level = 1

    _enabled = True
    _log_limit = 50
    _marker = "absolute_episode_map: Dict[int, Tuple[int, int]] = {}"
    _transfer_path = Path("/app/app/chain/transfer.py")
    _disabled_path = Path(str(settings.CONFIG_PATH)) / "tvseasonpreflight.disabled"

    def init_plugin(self, config=None):
        config = config or {}
        self._enabled = bool(config.get("enabled", True))
        self._log_limit = max(10, min(200, int(config.get("log_limit") or 50)))

    def get_state(self) -> bool:
        return True

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{"component": "VRow", "content": [
                {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                    {"component": "VSwitch", "props": {"model": "enabled", "label": "显示管理插件"}}
                ]},
                {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                    {"component": "VTextField", "props": {"model": "log_limit", "label": "最多显示日志", "type": "number"}}
                ]},
                {"component": "VCol", "props": {"cols": 12}, "content": [
                    {"component": "VAlert", "props": {"type": "info", "variant": "tonal"},
                     "text": "这个插件是管理界面；实际分季必须在 MoviePilot 整理目标路径生成前执行，因此引擎安装在 transfer.py。"}
                ]},
            ]}],
        }], {"enabled": True, "log_limit": 50}

    def _installed(self) -> bool:
        try:
            return self._marker in self._transfer_path.read_text(encoding="utf-8")
        except Exception:
            return False

    @staticmethod
    def _log_files() -> list[Path]:
        root = Path(str(settings.CONFIG_PATH)) / "logs"
        files = [root / "moviepilot.log"]
        files.extend(root / f"moviepilot.log.{number}" for number in range(1, 11))
        return [path for path in files if path.is_file()]

    def _events(self) -> list[dict]:
        rows = []
        date_pattern = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        for path in self._log_files():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                if "已严格核验绝对集数全集包" not in line and "疑似绝对集数包" not in line:
                    continue
                date_match = date_pattern.search(line)
                message = line.rsplit(" - ", 1)[-1].strip()
                rows.append({
                    "date": date_match.group(0) if date_match else "时间未知",
                    "status": "success" if "已严格核验" in message else "skipped",
                    "message": message,
                })
        rows.sort(key=lambda item: item["date"], reverse=True)
        return rows[:self._log_limit]

    def _engine_enabled(self) -> bool:
        return self._installed() and not self._disabled_path.exists()

    def ui_status(self):
        installed = self._installed()
        events = self._events()
        success = [item for item in events if item["status"] == "success"]
        skipped = [item for item in events if item["status"] == "skipped"]
        return {
            "success": True,
            "data": {
                "installed": installed,
                "enabled": installed and not self._disabled_path.exists(),
                "success_count": len(success),
                "skipped_count": len(skipped),
                "success_logs": success,
                "skipped_logs": skipped,
                "flow": "下载完成 → 收集整包 → 核对 TMDB → 生成正确分季目标路径 → 移动/上传",
                "path_mode": "自动使用 MoviePilot 当前任务的源路径和目标路径，无需单独设置目录。",
            },
        }

    def toggle(self, payload: dict = Body(default={})):
        enabled = bool(payload.get("enabled", True))
        if not self._installed():
            return {"success": False, "message": "未检测到入库前自动分季引擎。"}
        if enabled:
            self._disabled_path.unlink(missing_ok=True)
        else:
            self._disabled_path.write_text("disabled by TVSeasonPreflight\n", encoding="utf-8")
        return {
            "success": True,
            "message": f"入库前自动分季已{'启用' if enabled else '停用'}。新整理任务立即生效。",
            "data": self.ui_status()["data"],
        }

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    def get_page(self) -> List[dict]:
        installed = self._installed()
        events = self._events()
        success = [item for item in events if item["status"] == "success"]
        skipped = [item for item in events if item["status"] == "skipped"]

        def cards(items: list[dict], color: str) -> list[dict]:
            return [{
                "component": "VCard", "props": {"variant": "outlined", "class": "mb-2", "color": color},
                "content": [
                    {"component": "VCardSubtitle", "text": item["date"]},
                    {"component": "VCardText", "text": item["message"]},
                ],
            } for item in items] or [{"component": "VAlert", "props": {"type": "info", "variant": "tonal"}, "text": "暂无记录"}]

        return [{"component": "div", "content": [
            {"component": "VAlert", "props": {
                "type": "success" if installed else "error", "variant": "tonal", "class": "mb-3"
            }, "text": ("入库前自动分季引擎已安装并启用。" if installed else
                         "未检测到入库前自动分季引擎；请重新运行仓库补丁安装脚本。")},
            {"component": "VCard", "props": {"variant": "tonal", "class": "mb-3"}, "content": [
                {"component": "VCardTitle", "text": "执行位置"},
                {"component": "VCardText", "content": [
                    {"component": "div", "text": "下载完成 → 收集整包 → 核对 TMDB → 生成分季目标路径 → 移动/上传"},
                    {"component": "div", "text": "不会原地重命名做种文件；总数不符、缺集、重复或已有多季时自动跳过。"},
                    {"component": "div", "text": f"引擎文件：{self._transfer_path}"},
                ]},
            ]},
            {"component": "VRow", "props": {"class": "mb-3"}, "content": [
                {"component": "VCol", "props": {"cols": 6}, "content": [
                    {"component": "VCard", "props": {"variant": "outlined", "color": "success"}, "content": [
                        {"component": "VCardTitle", "text": str(len(success))},
                        {"component": "VCardSubtitle", "text": "自动分季成功"},
                    ]}
                ]},
                {"component": "VCol", "props": {"cols": 6}, "content": [
                    {"component": "VCard", "props": {"variant": "outlined", "color": "warning"}, "content": [
                        {"component": "VCardTitle", "text": str(len(skipped))},
                        {"component": "VCardSubtitle", "text": "安全跳过"},
                    ]}
                ]},
            ]},
            {"component": "VExpansionPanels", "props": {"variant": "accordion"}, "content": [
                {"component": "VExpansionPanel", "content": [
                    {"component": "VExpansionPanelTitle", "props": {"color": "success"},
                     "text": f"成功日志（{len(success)}）"},
                    {"component": "VExpansionPanelText", "content": cards(success, "success")},
                ]},
                {"component": "VExpansionPanel", "content": [
                    {"component": "VExpansionPanelTitle", "props": {"color": "warning"},
                     "text": f"跳过日志（{len(skipped)}）"},
                    {"component": "VExpansionPanelText", "content": cards(skipped, "warning")},
                ]},
            ]},
        ]}]

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/ui_status", "endpoint": self.ui_status, "methods": ["POST"],
             "auth": "bear", "summary": "获取入库前分季状态"},
            {"path": "/toggle", "endpoint": self.toggle, "methods": ["POST"],
             "auth": "bear", "summary": "启用或停用入库前分季"},
        ]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        return []

    def stop_service(self):
        pass
