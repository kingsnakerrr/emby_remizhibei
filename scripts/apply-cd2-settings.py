#!/usr/bin/env python3
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


CONFIG = Path("/root/docker-compose/clouddrive2/config")
CLOUD_DATA = CONFIG / "cloudapidata.json"
SYSTEM_SETTINGS = CONFIG / "systemsettings.json"
FILE_PROPERTIES = CONFIG / "fileproperties.sqlite"
TARGET_CLOUD = "/GoogleDrive"
MEDIA_ROOT = "/GoogleDrive/zero/media"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=check, text=True)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


if not CLOUD_DATA.exists():
    sys.exit(
        "未找到 cloudapidata.json。请先登录 CD2，并添加名为 /GoogleDrive 的 Google Drive。"
    )

clouds = load_json(CLOUD_DATA)
target = next(
    (item for item in clouds if item.get("dir_name") == TARGET_CLOUD),
    None,
)
if target is None:
    available = ", ".join(item.get("dir_name", "?") for item in clouds)
    sys.exit(
        f"没有找到 {TARGET_CLOUD}。当前云盘：{available}。"
        "请在 CD2 中把实际媒体账号命名为 /GoogleDrive。"
    )

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup_dir = (
    Path("/root/docker-compose/clouddrive2/backups")
    / f"before-auto-tuning-{timestamp}"
)
backup_dir.mkdir(parents=True, mode=0o700)

was_running = (
    subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "cd2"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    == "true"
)
if was_running:
    run("docker", "stop", "cd2")

try:
    for path in (CLOUD_DATA, SYSTEM_SETTINGS, FILE_PROPERTIES):
        if path.exists():
            shutil.copy2(path, backup_dir / path.name)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, backup_dir / sidecar.name)

    clouds = load_json(CLOUD_DATA)
    target = next(
        item for item in clouds if item.get("dir_name") == TARGET_CLOUD
    )
    downloader = target.setdefault("downloader_config", {})
    downloader.update(
        {
            "max_download_threads": 8,
            "min_read_length_kb": 1024,
            "default_read_length_kb": 4096,
            "max_buffer_pool_size_mb": 256,
            "max_queries_per_second": 9.0,
            "force_ipv4": False,
            "api_proxy": None,
            "data_proxy": None,
            "max_upload_threads": 1,
            "use_http_download": False,
            "support_direct_link": False,
            "file_buffer_disk_cache_enabled": False,
            "file_buffer_disk_cache_max_file_size": 0,
            "use_multithread_downloader_for_copy": False,
        }
    )
    target["file_buffer_disk_cache_enabled"] = False
    target["file_buffer_disk_cache_max_file_size"] = 0
    write_json(CLOUD_DATA, clouds)

    settings = load_json(SYSTEM_SETTINGS) if SYSTEM_SETTINGS.exists() else {}
    settings.update(
        {
            "dir_cache_ttl_secs": 3600,
            "max_preprocess_tasks": 2,
            "max_process_tasks": 2,
            "read_downloader_timeout_secs": 90,
            "dir_cache_persistence": True,
            "max_download_speed_kbyps": 0.0,
            "max_upload_speed_kbyps": 0.0,
            "file_log_level": "Error",
            "terminal_log_level": "Error",
            "file_buffer_disk_cache_max_bytes": 21474836480,
            "file_buffer_disk_cache_eviction_strategy": "Lru",
        }
    )
    write_json(SYSTEM_SETTINGS, settings)

    connection = sqlite3.connect(FILE_PROPERTIES)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS disk_cache_folders (
                path TEXT NOT NULL PRIMARY KEY,
                rules_json TEXT NOT NULL DEFAULT '{}',
                updated_at INTEGER NOT NULL
            )
            """
        )
        rules = json.dumps(
            {
                "enabled": False,
                "max_file_size": 0,
                "min_file_size": 104857600,
                "extension_filter_mode": "Include",
                "extensions": ["mkv", "mp4", "ts", "m2ts", "avi", "mov"],
            },
            separators=(",", ":"),
        )
        connection.execute(
            """
            INSERT INTO disk_cache_folders(path, rules_json, updated_at)
            VALUES (?, ?, unixepoch())
            ON CONFLICT(path) DO UPDATE SET
                rules_json=excluded.rules_json,
                updated_at=excluded.updated_at
            """,
            (MEDIA_ROOT, rules),
        )
        connection.commit()
    finally:
        connection.close()
finally:
    if was_running:
        run("docker", "start", "cd2")

print(f"CD2 优化参数已应用。修改前备份：{backup_dir}")
print("请等待挂载恢复后运行 ./healthcheck.sh。")

