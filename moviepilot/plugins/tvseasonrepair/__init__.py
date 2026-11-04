from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Any, Dict, List, Tuple

import httpx
from fastapi import Body

from app.chain.tmdb import TmdbChain
from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase


class TVSeasonRepair(_PluginBase):
    plugin_name = "旧媒体季度修复助手"
    plugin_desc = "从网盘源文件根治错误季度，并重建 Symedia/Emby 元数据。"
    plugin_icon = "tv.png"
    plugin_version = "0.1.0"
    plugin_author = "kingsnakerrr"
    author_url = "https://github.com/kingsnakerrr/emby_remizhibei"
    plugin_config_prefix = "tvseasonrepair_"
    plugin_order = 30
    auth_level = 1

    _enabled = False
    _agent_url = ""
    _agent_token = ""

    def init_plugin(self, config=None):
        config = config or {}
        self._enabled = bool(config.get("enabled", True))
        self._agent_url = str(config.get("agent_url") or "https://notify.rmzb.de").rstrip("/")
        self._agent_token = str(config.get("agent_token") or "").strip()

    def get_state(self) -> bool:
        return self._enabled

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [
                    {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [
                        {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}
                    ]},
                    {"component": "VCol", "props": {"cols": 12, "md": 9}, "content": [
                        {"component": "VTextField", "props": {"model": "agent_url", "label": "修复端地址"}}
                    ]},
                    {"component": "VCol", "props": {"cols": 12}, "content": [
                        {"component": "VTextField", "props": {"model": "agent_token", "label": "修复端密钥", "type": "password"}}
                    ]},
                    {"component": "VCol", "props": {"cols": 12}, "content": [
                        {"component": "VAlert", "props": {"type": "info", "variant": "tonal"},
                         "text": "先在 CloudDrive2 网盘内按季度移动并改名真实视频，再重建 STRM/NFO/图片。只有集数与 TMDB 完全吻合的绿色项目才能执行。"}
                    ]},
                ],
            }],
        }], {"enabled": True, "agent_url": "https://notify.rmzb.de", "agent_token": ""}

    def _post(self, path: str, payload: dict | None = None) -> dict:
        if not self._agent_token:
            raise RuntimeError("请先填写修复端密钥")
        response = httpx.post(
            f"{self._agent_url}/season-repair/{path.lstrip('/')}",
            headers={"Authorization": f"Bearer {self._agent_token}"},
            json=payload or {}, timeout=1800,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _official_counts(tmdb_id: int) -> list[int]:
        seasons = TmdbChain().tmdb_seasons(int(tmdb_id)) or []
        indexed = {
            int(item.season_number): int(item.episode_count or 0)
            for item in seasons
            if int(item.season_number or 0) > 0 and int(item.episode_count or 0) > 0
        }
        if not indexed or sorted(indexed) != list(range(1, len(indexed) + 1)):
            return []
        return [indexed[n] for n in range(1, len(indexed) + 1)]

    def scan(self, _: dict = Body(default={})):
        try:
            raw = self._post("scan")
            source_rows = raw.get("series") or []
            count_cache = self.get_data("tmdb_season_counts") or {}
            missing_ids = sorted({
                int(row.get("tmdb_id") or 0) for row in source_rows
                if int(row.get("tmdb_id") or 0) and str(int(row.get("tmdb_id") or 0)) not in count_cache
            })
            # The first full-library scan can contain hundreds of titles.  A
            # small worker pool avoids a several-minute serial TMDB walk while
            # staying well below an aggressive request fan-out.
            with ThreadPoolExecutor(max_workers=6) as pool:
                futures = {pool.submit(self._official_counts, tmdb_id): tmdb_id for tmdb_id in missing_ids}
                for future in as_completed(futures):
                    tmdb_id = futures[future]
                    try:
                        counts = future.result()
                        if counts:
                            count_cache[str(tmdb_id)] = counts
                    except Exception as err:
                        logger.warning(f"季度修复：TMDB {tmdb_id} 查询失败：{err}")
            self.save_data("tmdb_season_counts", count_cache)
            results = []
            for row in source_rows:
                tmdb_id = int(row.get("tmdb_id") or 0)
                if not tmdb_id:
                    continue
                official = count_cache.get(str(tmdb_id)) or []
                if not official:
                    continue
                seasons = row.get("seasons") or []
                suspicious = []
                for item in seasons:
                    number = int(item.get("season") or 0)
                    maximum = int(item.get("max") or 0)
                    if number < 1 or number > len(official):
                        suspicious.append(f"S{number:02d} 不在 TMDB 季度范围")
                    elif maximum > official[number - 1]:
                        suspicious.append(f"S{number:02d} 到 E{maximum}，TMDB 只有 {official[number - 1]} 集")
                if not suspicious:
                    continue
                safe = (
                    len(seasons) == 1
                    and bool(seasons[0].get("contiguous_from_one"))
                    and int(seasons[0].get("count") or 0) == sum(official)
                    and len(official) > 1
                )
                row["official_counts"] = official
                row["official_summary"] = "、".join(f"S{i:02d}:{count}" for i, count in enumerate(official, 1))
                row["safe"] = safe
                row["reason"] = "；".join(suspicious)
                row["current_summary"] = "、".join(
                    f"S{int(x['season']):02d}:{int(x['count'])}集(E{int(x['min'])}-E{int(x['max'])})"
                    for x in seasons
                )
                results.append(row)
            results.sort(key=lambda item: (not item["safe"], item["name"]))
            self.save_data("scan_results", results)
            self.save_data("last_message", f"扫描完成：发现 {len(results)} 部异常，{sum(1 for x in results if x['safe'])} 部可安全修复。")
            return {"success": True, "message": self.get_data("last_message"), "count": len(results)}
        except Exception as err:
            message = f"扫描失败：{type(err).__name__}: {err}"
            self.save_data("last_message", message)
            logger.error(message)
            return {"success": False, "message": message}

    def apply(self, payload: dict = Body(default={})):
        key = str(payload.get("series_rel") or "")
        execute = bool(payload.get("execute", False))
        rows = self.get_data("scan_results") or []
        row = next((x for x in rows if x.get("series_rel") == key), None)
        if not row or not row.get("safe"):
            return {"success": False, "message": "该项目不是绿色安全项目，拒绝自动修改。"}
        approvals = self.get_data("preview_approvals") or {}
        if execute and time.time() - float(approvals.get(key) or 0) > 1800:
            return {"success": False, "message": "请先点“只预览”；预览成功后 30 分钟内才能执行网盘修复。"}
        try:
            result = self._post("apply-exact", {
                "series_rel": key,
                "official_counts": row["official_counts"],
                "preview": not execute,
            })
            if execute:
                actions = self.get_data("actions") or []
                actions.insert(0, {"name": row["name"], "action_id": result["action_id"]})
                self.save_data("actions", actions[:30])
                approvals.pop(key, None)
                self.save_data("preview_approvals", approvals)
                self.save_data("scan_results", [item for item in rows if item.get("series_rel") != key])
                message = f"已根治 {row['name']}：移动 {result['video_move_count']} 个网盘视频并重建本地元素，动作号 {result['action_id']}。{result.get('refresh_message', '')}"
            else:
                approvals[key] = time.time()
                self.save_data("preview_approvals", approvals)
                message = f"预览通过：{row['name']} 将移动 {result['video_move_count']} 个网盘视频、{result['metadata_move_count']} 个网盘元数据文件，然后重建本地元素。"
            self.save_data("last_message", message)
            return {"success": True, "message": message, "data": result}
        except Exception as err:
            message = f"操作失败：{type(err).__name__}: {err}"
            self.save_data("last_message", message)
            return {"success": False, "message": message}

    def batch(self, payload: dict = Body(default={})):
        execute = bool(payload.get("execute", False))
        rows = [x for x in (self.get_data("scan_results") or []) if x.get("safe")]
        approvals = self.get_data("preview_approvals") or {}
        done, failed = [], []
        for row in rows:
            if execute and time.time() - float(approvals.get(row["series_rel"]) or 0) > 1800:
                failed.append(f"{row['name']}: 尚未预览或预览已超过 30 分钟")
                continue
            try:
                result = self._post("apply-exact", {
                    "series_rel": row["series_rel"], "official_counts": row["official_counts"],
                    "preview": not execute,
                })
                done.append({"row": row, "result": result})
                if not execute:
                    approvals[row["series_rel"]] = time.time()
            except Exception as err:
                failed.append(f"{row['name']}: {err}")
        if not execute:
            self.save_data("preview_approvals", approvals)
        if execute and done:
            actions = self.get_data("actions") or []
            for item in done:
                actions.insert(0, {"name": item["row"]["name"], "action_id": item["result"]["action_id"]})
                approvals.pop(item["row"]["series_rel"], None)
            self.save_data("actions", actions[:30])
            completed_keys = {item["row"]["series_rel"] for item in done}
            self.save_data("scan_results", [item for item in (self.get_data("scan_results") or []) if item.get("series_rel") not in completed_keys])
            self.save_data("preview_approvals", approvals)
        mode = "修复" if execute else "预览"
        message = f"批量{mode}完成：成功 {len(done)}，失败 {len(failed)}。"
        self.save_data("last_message", message + ((" " + "；".join(failed[:3])) if failed else ""))
        return {"success": not failed, "message": self.get_data("last_message")}

    def undo(self, payload: dict = Body(default={})):
        action_id = str(payload.get("action_id") or "")
        try:
            result = self._post(f"undo/{action_id}")
            self.save_data("last_message", f"已回滚动作 {action_id}，恢复 {result['restored']} 个文件。")
            return {"success": True, "message": self.get_data("last_message")}
        except Exception as err:
            message = f"回滚失败：{type(err).__name__}: {err}"
            self.save_data("last_message", message)
            return {"success": False, "message": message}

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/scan", "endpoint": self.scan, "methods": ["POST"], "summary": "扫描季度异常"},
            {"path": "/apply", "endpoint": self.apply, "methods": ["POST"], "summary": "预览或修复单项"},
            {"path": "/batch", "endpoint": self.batch, "methods": ["POST"], "summary": "预览或修复全部安全项"},
            {"path": "/undo", "endpoint": self.undo, "methods": ["POST"], "summary": "回滚修复"},
        ]

    @staticmethod
    def _button(text: str, path: str, params: dict, color: str = "primary") -> dict:
        return {
            "component": "VBtn",
            "props": {"variant": "tonal", "color": color, "class": "mr-2 mb-2"},
            "text": text,
            "events": {"click": {"api": f"plugin/TVSeasonRepair/{path}?apikey={settings.API_TOKEN}", "method": "post", "params": params}},
        }

    def get_page(self) -> List[dict]:
        rows = self.get_data("scan_results") or []
        message = self.get_data("last_message") or "先点击扫描；扫描不会修改任何文件。"
        content = [
            {"component": "VAlert", "props": {"type": "info", "variant": "tonal", "class": "mb-4"}, "text": message},
            {"component": "div", "props": {"class": "mb-4"}, "content": [
                self._button("扫描现有媒体库", "scan", {}),
                self._button("预览全部绿色项目", "batch", {"execute": False}, "info"),
                self._button("批量修复全部绿色项目", "batch", {"execute": True}, "success"),
            ]},
        ]
        for row in rows:
            color = "success" if row.get("safe") else "warning"
            label = "可安全修复" if row.get("safe") else "需人工核对"
            card = {
                "component": "VCard", "props": {"variant": "tonal", "class": "mb-3"},
                "content": [
                    {"component": "VCardTitle", "text": f"{row['name']}  (TMDB {row['tmdb_id']})"},
                    {"component": "VCardSubtitle", "text": label},
                    {"component": "VCardText", "content": [
                        {"component": "div", "text": f"当前：{row['current_summary']}"},
                        {"component": "div", "text": f"TMDB：{row['official_summary']}"},
                        {"component": "div", "props": {"class": f"text-{color}"}, "text": f"判断：{row['reason']}"},
                    ]},
                ],
            }
            if row.get("safe"):
                card["content"].append({"component": "VCardActions", "content": [
                    self._button("只预览", "apply", {"series_rel": row["series_rel"], "execute": False}, "info"),
                    self._button("修复这一部", "apply", {"series_rel": row["series_rel"], "execute": True}, "success"),
                ]})
            content.append(card)
        actions = self.get_data("actions") or []
        if actions:
            content.append({"component": "VDivider", "props": {"class": "my-4"}})
            content.append({"component": "h3", "text": "最近修复（可回滚）"})
            for action in actions[:10]:
                content.append({"component": "div", "props": {"class": "d-flex align-center mb-2"}, "content": [
                    {"component": "span", "props": {"class": "mr-3"}, "text": f"{action['name']} · {action['action_id']}"},
                    self._button("回滚", "undo", {"action_id": action["action_id"]}, "error"),
                ]})
        return [{"component": "div", "content": content}]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def stop_service(self):
        pass
