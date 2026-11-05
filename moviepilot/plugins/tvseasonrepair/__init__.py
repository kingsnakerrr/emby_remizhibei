from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
from typing import Any, Dict, List, Tuple
import uuid

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
    plugin_version = "0.4.0"
    plugin_author = "kingsnakerrr"
    author_url = "https://github.com/kingsnakerrr/emby_remizhibei"
    plugin_config_prefix = "tvseasonrepair_"
    plugin_order = 30
    auth_level = 1

    _enabled = False
    _agent_url = ""
    _agent_token = ""
    _data_lock = threading.RLock()
    _repair_lock = threading.Lock()

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

    def _jobs(self) -> list[dict]:
        return self.get_data("repair_jobs") or []

    @staticmethod
    def _now() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S")

    def _set_headline(self, message: str) -> str:
        value = f"[{self._now()}] {message}"
        self.save_data("last_message", value)
        return value

    def _append_operation(self, kind: str, status: str, title: str,
                          detail: str = "", **extra) -> dict:
        with self._data_lock:
            rows = self.get_data("operation_logs") or []
            row = {
                "id": uuid.uuid4().hex[:12],
                "kind": kind,
                "status": status,
                "title": title,
                "detail": detail,
                "started_at": self._now(),
                "finished_at": "",
                "duration_seconds": None,
                "started_ts": time.time(),
                **extra,
            }
            rows.insert(0, row)
            self.save_data("operation_logs", rows[:100])
            return row

    def _finish_operation(self, operation_id: str, status: str,
                          detail: str = "", **extra) -> None:
        with self._data_lock:
            rows = self.get_data("operation_logs") or []
            target = next((item for item in rows if item.get("id") == operation_id), None)
            if not target:
                return
            finished_ts = time.time()
            target.update(status=status, detail=detail,
                          finished_at=self._now(),
                          duration_seconds=round(finished_ts - float(target.get("started_ts") or finished_ts), 2),
                          **extra)
            self.save_data("operation_logs", rows[:100])

    def _update_job(self, job_id: str, **changes) -> dict | None:
        with self._data_lock:
            jobs = self._jobs()
            target = next((item for item in jobs if item.get("id") == job_id), None)
            if not target:
                return None
            now = self._now()
            status = changes.get("status")
            if status in {"previewing", "running"} and not target.get("started_at"):
                target["started_at"] = now
                target["started_ts"] = time.time()
            if status in {"success", "failed"}:
                target["finished_at"] = now
                started_ts = float(target.get("started_ts") or time.time())
                target["duration_seconds"] = round(time.time() - started_ts, 2)
            target.update(changes)
            target["updated_at"] = now
            self.save_data("repair_jobs", jobs[:50])
            return target

    def _queue_job(self, row: dict) -> tuple[dict, bool]:
        with self._data_lock:
            jobs = self._jobs()
            active = next((item for item in jobs if item.get("series_rel") == row["series_rel"]
                           and item.get("status") in {"queued", "previewing", "running"}), None)
            if active:
                return active, False
            now = self._now()
            job = {
                "id": uuid.uuid4().hex[:12],
                "name": row["name"],
                "series_rel": row["series_rel"],
                "status": "queued",
                "message": "已加入队列，等待执行。",
                "created_at": now,
                "updated_at": now,
            }
            jobs.insert(0, job)
            self.save_data("repair_jobs", jobs[:50])
            return job, True

    def _run_repair_job(self, job_id: str, key: str) -> None:
        with self._repair_lock:
            row = None
            try:
                rows = self.get_data("scan_results") or []
                row = next((item for item in rows if item.get("series_rel") == key), None)
                if not row or not row.get("safe"):
                    raise RuntimeError("项目已不在绿色安全列表，请重新扫描后再试")
                self._update_job(job_id, status="previewing", message="正在重新预览网盘文件和季度方案。")
                preview = self._post("apply-exact", {
                    "series_rel": key,
                    "official_counts": row["official_counts"],
                    "preview": True,
                })
                self._update_job(
                    job_id,
                    status="running",
                    message=(f"预览通过，正在整理 {preview['video_move_count']} 个视频、"
                             f"{preview['metadata_move_count']} 个元数据文件。"),
                )
                result = self._post("apply-exact", {
                    "series_rel": key,
                    "official_counts": row["official_counts"],
                    "preview": False,
                })
                with self._data_lock:
                    actions = self.get_data("actions") or []
                    actions.insert(0, {"name": row["name"], "action_id": result["action_id"],
                                       "mode": result.get("mode"), "finished_at": self._now()})
                    self.save_data("actions", actions[:30])
                    approvals = self.get_data("preview_approvals") or {}
                    approvals.pop(key, None)
                    self.save_data("preview_approvals", approvals)
                    current_rows = self.get_data("scan_results") or []
                    self.save_data("scan_results", [item for item in current_rows
                                                     if item.get("series_rel") != key])
                message = (f"成功整理：移动 {result['video_move_count']} 个网盘视频并重建本地元素。"
                           f"动作号 {result['action_id']}。{result.get('refresh_message', '')}")
                self._update_job(job_id, status="success", message=message,
                                 action_id=result["action_id"])
                self._set_headline(f"修复成功：{row['name']}，移动 {result['video_move_count']} 个视频。")
            except Exception as err:
                message = f"整理失败：{type(err).__name__}: {err}"
                self._update_job(job_id, status="failed", message=message)
                name = row.get("name", key) if row else key
                self._set_headline(f"修复失败：{name}。{type(err).__name__}")
                logger.error(f"季度修复任务 {job_id} 失败：{err}")

    def _start_job(self, job: dict) -> None:
        thread = threading.Thread(
            target=self._run_repair_job,
            args=(job["id"], job["series_rel"]),
            name=f"tv-season-repair-{job['id']}",
            daemon=True,
        )
        thread.start()

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
        operation = self._append_operation("scan", "running", "扫描现有媒体库",
                                           "正在读取本地 STRM 索引并核对 TMDB 季度。")
        try:
            raw = self._post("scan")
            source_rows = raw.get("series") or []
            count_cache = self.get_data("tmdb_season_counts") or {}
            missing_ids = sorted({
                int(row.get("tmdb_id") or 0) for row in source_rows
                if int(row.get("tmdb_id") or 0) and str(int(row.get("tmdb_id") or 0)) not in count_cache
                and len(row.get("seasons") or []) == 1
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
            skipped_existing_multiseason = 0
            for row in source_rows:
                tmdb_id = int(row.get("tmdb_id") or 0)
                if not tmdb_id:
                    continue
                seasons = row.get("seasons") or []
                if len(seasons) != 1:
                    skipped_existing_multiseason += 1
                    continue
                official = count_cache.get(str(tmdb_id)) or []
                if not official:
                    continue
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
                    bool(seasons[0].get("contiguous_from_one"))
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
            safe_count = sum(1 for x in results if x["safe"])
            detail = (f"扫描完成：发现 {len(results)} 部单季压平候选，{safe_count} 部可安全修复；"
                      f"跳过 {skipped_existing_multiseason} 部已存在多季的媒体。"
                      f"候选：{'、'.join(item['name'] for item in results) or '无'}")
            self._finish_operation(operation["id"], "success", detail,
                                   candidate_count=len(results), safe_count=safe_count,
                                   skipped_count=skipped_existing_multiseason)
            self._set_headline(
                f"扫描完成：候选 {len(results)}，可安全修复 {safe_count}，"
                f"跳过已有多季 {skipped_existing_multiseason}。"
            )
            return {"success": True, "message": self.get_data("last_message"), "count": len(results)}
        except Exception as err:
            message = f"扫描失败：{type(err).__name__}: {err}"
            self._finish_operation(operation["id"], "failed", message)
            self._set_headline(f"扫描失败：{type(err).__name__}。")
            logger.error(message)
            return {"success": False, "message": message}

    def apply(self, payload: dict = Body(default={})):
        key = str(payload.get("series_rel") or "")
        execute = bool(payload.get("execute", False))
        rows = self.get_data("scan_results") or []
        row = next((x for x in rows if x.get("series_rel") == key), None)
        if not row or not row.get("safe"):
            return {"success": False, "message": "该项目不是绿色安全项目，拒绝自动修改。"}
        if execute:
            job, created = self._queue_job(row)
            if created:
                self._start_job(job)
                message = f"已提交后台整理：{row['name']}。关闭再打开插件页可查看实时状态。"
            else:
                message = f"{row['name']} 已在任务队列中，请勿重复点击。"
            self._set_headline(message)
            return {"success": True, "message": message, "job_id": job["id"]}
        approvals = self.get_data("preview_approvals") or {}
        operation = self._append_operation("preview", "running", f"预览：{row['name']}",
                                           "正在核验网盘真文件和目标季度路径。")
        try:
            result = self._post("apply-exact", {
                "series_rel": key,
                "official_counts": row["official_counts"],
                "preview": not execute,
            })
            if execute:
                actions = self.get_data("actions") or []
                actions.insert(0, {"name": row["name"], "action_id": result["action_id"], "mode": result.get("mode")})
                self.save_data("actions", actions[:30])
                approvals.pop(key, None)
                self.save_data("preview_approvals", approvals)
                self.save_data("scan_results", [item for item in rows if item.get("series_rel") != key])
                message = f"已根治 {row['name']}：移动 {result['video_move_count']} 个网盘视频并重建本地元素，动作号 {result['action_id']}。{result.get('refresh_message', '')}"
            else:
                approvals[key] = time.time()
                self.save_data("preview_approvals", approvals)
                message = f"预览通过：{row['name']} 将移动 {result['video_move_count']} 个网盘视频、{result['metadata_move_count']} 个网盘元数据文件，然后重建本地元素。"
            self._finish_operation(operation["id"], "success", message)
            self._set_headline(message)
            return {"success": True, "message": message, "data": result}
        except Exception as err:
            message = f"操作失败：{type(err).__name__}: {err}"
            self._finish_operation(operation["id"], "failed", message)
            self._set_headline(f"预览失败：{row['name']}，{type(err).__name__}。")
            return {"success": False, "message": message}

    def batch(self, payload: dict = Body(default={})):
        execute = bool(payload.get("execute", False))
        rows = [x for x in (self.get_data("scan_results") or []) if x.get("safe")]
        if execute:
            queued = []
            for row in rows:
                job, created = self._queue_job(row)
                if created:
                    self._start_job(job)
                    queued.append(job)
            message = f"已提交 {len(queued)} 个后台整理任务；任务会逐个执行，请勿重复点击。"
            self._set_headline(message)
            return {"success": True, "message": message,
                    "job_ids": [item["id"] for item in queued]}
        operation = self._append_operation(
            "batch-preview", "running", "批量预览绿色项目",
            f"正在逐项核验 {len(rows)} 部媒体的网盘文件和季度方案。",
        )
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
                actions.insert(0, {"name": item["row"]["name"], "action_id": item["result"]["action_id"], "mode": item["result"].get("mode")})
                approvals.pop(item["row"]["series_rel"], None)
            self.save_data("actions", actions[:30])
            completed_keys = {item["row"]["series_rel"] for item in done}
            self.save_data("scan_results", [item for item in (self.get_data("scan_results") or []) if item.get("series_rel") not in completed_keys])
            self.save_data("preview_approvals", approvals)
        mode = "修复" if execute else "预览"
        message = f"批量{mode}完成：成功 {len(done)}，失败 {len(failed)}。"
        detail = message + ((" " + "；".join(failed)) if failed else "")
        self._finish_operation(
            operation["id"], "failed" if failed else "success", detail,
            success_count=len(done), failed_count=len(failed),
        )
        self._set_headline(message + ((" " + "；".join(failed[:3])) if failed else ""))
        return {"success": not failed, "message": self.get_data("last_message")}

    def undo(self, payload: dict = Body(default={})):
        action_id = str(payload.get("action_id") or "")
        operation = self._append_operation("undo", "running", f"回滚：{action_id}",
                                           "正在恢复网盘文件和本地元素。")
        try:
            result = self._post(f"undo/{action_id}")
            message = f"已回滚动作 {action_id}，恢复 {result['restored']} 个文件。"
            self._finish_operation(operation["id"], "success", message)
            self._set_headline(message)
            return {"success": True, "message": self.get_data("last_message")}
        except Exception as err:
            message = f"回滚失败：{type(err).__name__}: {err}"
            self._finish_operation(operation["id"], "failed", message)
            self._set_headline(f"回滚失败：{action_id}，{type(err).__name__}。")
            return {"success": False, "message": message}

    def ui_status(self):
        rows = self.get_data("scan_results") or []
        jobs = self._jobs()
        operations = self.get_data("operation_logs") or []
        actions = self.get_data("actions") or []
        active_states = {"queued", "previewing", "running"}
        active = [item for item in jobs if item.get("status") in active_states]
        success_jobs = [item for item in jobs if item.get("status") == "success"]
        failed_jobs = [item for item in jobs if item.get("status") == "failed"]
        scan_logs = [item for item in operations if item.get("kind") == "scan"]
        other_logs = [item for item in operations if item.get("kind") != "scan"]
        return {
            "success": True,
            "data": {
                "headline": self.get_data("last_message") or "尚未执行扫描。",
                "summary": {
                    "candidate_count": len(rows),
                    "safe_count": sum(1 for item in rows if item.get("safe")),
                    "active_count": len(active),
                    "success_count": len(success_jobs),
                    "failed_count": len(failed_jobs),
                    "log_count": len(operations),
                    "rollback_count": len(actions),
                },
                "scan_results": rows,
                "active_jobs": active,
                "success_jobs": success_jobs,
                "failed_jobs": failed_jobs,
                "scan_logs": scan_logs,
                "other_logs": other_logs,
                "actions": actions,
            },
        }

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/ui_status", "endpoint": self.ui_status, "methods": ["POST"], "auth": "bear",
             "summary": "获取季度修复界面状态"},
            {"path": "/scan", "endpoint": self.scan, "methods": ["POST"], "auth": "bear", "summary": "扫描季度异常"},
            {"path": "/apply", "endpoint": self.apply, "methods": ["POST"], "auth": "bear", "summary": "预览或修复单项"},
            {"path": "/batch", "endpoint": self.batch, "methods": ["POST"], "auth": "bear", "summary": "预览或修复全部安全项"},
            {"path": "/undo", "endpoint": self.undo, "methods": ["POST"], "auth": "bear", "summary": "回滚修复"},
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
        jobs = self._jobs()
        operations = self.get_data("operation_logs") or []
        actions = [item for item in (self.get_data("actions") or []) if item.get("mode") == "cloud-root-v2"]
        message = self.get_data("last_message") or f"[{self._now()}] 尚未扫描；扫描不会修改任何文件。"

        def detail_card(title: str, lines: list[str], color: str = "default") -> dict:
            return {
                "component": "VCard",
                "props": {"variant": "outlined", "class": "mb-2", "color": color},
                "content": [
                    {"component": "VCardTitle", "props": {"class": "text-subtitle-1"}, "text": title},
                    {"component": "VCardText", "props": {"class": "pt-1"}, "content": [
                        {"component": "div", "props": {"class": "mb-1"}, "text": line}
                        for line in lines if line
                    ]},
                ],
            }

        def panel(title: str, items: list[dict], color: str = "primary") -> dict:
            body = items or [{"component": "VAlert", "props": {"type": "info", "variant": "tonal"},
                              "text": "暂无记录"}]
            return {
                "component": "VExpansionPanel",
                "content": [
                    {"component": "VExpansionPanelTitle", "props": {"color": color},
                     "text": f"{title}（{len(items)}）"},
                    {"component": "VExpansionPanelText", "content": body},
                ],
            }

        content = [
            {"component": "VAlert", "props": {"type": "info", "variant": "tonal", "class": "mb-3"},
             "text": message},
            {"component": "div", "props": {"class": "mb-4"}, "content": [
                self._button("扫描现有媒体库", "scan", {}),
                self._button("预览全部绿色项目", "batch", {"execute": False}, "info"),
                self._button("确认批量修复（耗时）", "batch", {"execute": True}, "success"),
            ]},
            {"component": "VRow", "props": {"class": "mb-3"}, "content": [
                {"component": "VCol", "props": {"cols": 6, "md": 3}, "content": [
                    detail_card("扫描候选", [f"{len(rows)} 部", f"安全：{sum(1 for x in rows if x.get('safe'))} 部"], "info")
                ]},
                {"component": "VCol", "props": {"cols": 6, "md": 3}, "content": [
                    detail_card("处理中", [f"{sum(1 for x in jobs if x.get('status') in {'queued', 'previewing', 'running'})} 个任务"], "primary")
                ]},
                {"component": "VCol", "props": {"cols": 6, "md": 3}, "content": [
                    detail_card("成功 / 失败", [
                        f"成功 {sum(1 for x in jobs if x.get('status') == 'success')}",
                        f"失败 {sum(1 for x in jobs if x.get('status') == 'failed')}",
                    ], "success")
                ]},
                {"component": "VCol", "props": {"cols": 6, "md": 3}, "content": [
                    detail_card("日志 / 回滚", [f"日志 {len(operations)} 条", f"可回滚 {len(actions)} 条"], "warning")
                ]},
            ]},
        ]

        candidate_cards = []
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
                    self._button("确认修复（勿重复点）", "apply", {"series_rel": row["series_rel"], "execute": True}, "success"),
                ]})
            candidate_cards.append(card)

        scan_logs = [detail_card(
            item.get("title", "扫描"),
            [f"开始：{item.get('started_at') or '-'}",
             f"结束：{item.get('finished_at') or '进行中'}",
             f"耗时：{item.get('duration_seconds') if item.get('duration_seconds') is not None else '-'} 秒",
             f"结果：{item.get('detail') or '-'}"],
            "success" if item.get("status") == "success" else ("error" if item.get("status") == "failed" else "info")
        ) for item in operations if item.get("kind") == "scan"]

        def job_cards(statuses: set[str]) -> list[dict]:
            labels = {"queued": "排队中", "previewing": "正在预览", "running": "整理中",
                      "success": "成功整理", "failed": "整理失败"}
            return [detail_card(
                f"{job.get('name', '未知项目')} · {labels.get(job.get('status'), job.get('status', '未知'))}",
                [f"任务：{job.get('id')}", f"创建：{job.get('created_at') or '-'}",
                 f"开始：{job.get('started_at') or '-'}", f"结束：{job.get('finished_at') or '进行中'}",
                 f"耗时：{job.get('duration_seconds') if job.get('duration_seconds') is not None else '-'} 秒",
                 f"结果：{job.get('message') or '-'}"],
                "success" if job.get("status") == "success" else ("error" if job.get("status") == "failed" else "info")
            ) for job in jobs if job.get("status") in statuses]

        rollback_cards = []
        for action in actions[:30]:
            card = detail_card(
                action.get("name", "未知项目"),
                [f"完成：{action.get('finished_at') or '旧记录无时间'}", f"动作号：{action.get('action_id')}"],
                "warning",
            )
            card["content"].append({"component": "VCardActions", "content": [
                self._button("回滚", "undo", {"action_id": action["action_id"]}, "error")
            ]})
            rollback_cards.append(card)

        other_logs = [detail_card(
            item.get("title", "操作"),
            [f"类型：{item.get('kind')}", f"开始：{item.get('started_at') or '-'}",
             f"结束：{item.get('finished_at') or '进行中'}",
             f"耗时：{item.get('duration_seconds') if item.get('duration_seconds') is not None else '-'} 秒",
             f"结果：{item.get('detail') or '-'}"],
            "success" if item.get("status") == "success" else ("error" if item.get("status") == "failed" else "info")
        ) for item in operations if item.get("kind") != "scan"]

        content.append({
            "component": "VExpansionPanels",
            "props": {"variant": "accordion", "class": "mb-4"},
            "content": [
                panel("扫描结果", candidate_cards, "info"),
                panel("扫描日志", scan_logs, "info"),
                panel("处理中", job_cards({"queued", "previewing", "running"}), "primary"),
                panel("成功记录", job_cards({"success"}), "success"),
                panel("失败记录", job_cards({"failed"}), "error"),
                panel("预览与回滚日志", other_logs, "warning"),
                panel("最近修复（可回滚）", rollback_cards, "warning"),
            ],
        })
        return [{"component": "div", "content": content}]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def stop_service(self):
        pass
