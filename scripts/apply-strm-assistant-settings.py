#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


BASE = Path(
    "/root/docker-compose/emby/config/plugins/configurations"
)
MAIN = BASE / "Strm Assistant.json"
MEDIA = BASE / "Strm Assistant_MediaInfoExtractOptions.json"
METADATA = BASE / "Strm Assistant_MetadataEnhanceOptions.json"
EXPERIENCE = BASE / "Strm Assistant_ExperienceEnhanceOptions.json"
TASK = Path(
    "/root/docker-compose/emby/config/config/ScheduledTasks/"
    "f84e5d98-9aa8-a8b6-ab1a-3a8c0848faab1.js"
)


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(
            f"未找到 {path.name}。请先安装并授权神医助手 PRO 3.0.0.48，"
            "重启 Emby，让插件创建初始配置。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


for required in (MAIN, MEDIA, METADATA, EXPERIENCE):
    load(required)

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = (
    Path("/root/docker-compose/emby/config/backups")
    / f"before-strm-assistant-auto-config-{timestamp}"
)
backup.mkdir(parents=True, mode=0o700)

was_running = (
    subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "emby"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    == "true"
)
if was_running:
    subprocess.run(["docker", "stop", "emby"], check=True)

try:
    for path in (MAIN, MEDIA, METADATA, EXPERIENCE):
        shutil.copy2(path, backup / path.name)

    main = load(MAIN)
    main.setdefault("GeneralOptions", {}).update(
        {
            "CatchupMode": False,
            "CatchupTaskScope": "MediaInfo,EpisodeRefresh",
            "CatchupMinimumDelaySeconds": 10,
            "MaxConcurrentCount": 1,
            "CooldownDurationSeconds": 0,
            "Tier2MaxConcurrentCount": 1,
        }
    )
    main.setdefault("ModOptions", {}).update(
        {
            "EnhanceChineseSearch": True,
            "SearchScope": "Movie,Series,Person",
            "SearchTuningPreferences": "ExcludeOriginalTitle",
        }
    )
    main.setdefault("NetworkOptions", {}).update(
        {
            "LocalDiscoveryUrl": "",
            "EnableProxyServer": False,
            "ProxyServerUrl": "",
            "ProxyMode": "Whitelist",
            "IgnoreCertificateValidation": False,
        }
    )
    main.setdefault("AboutOptions", {})["DebugMode"] = False
    save(MAIN, main)

    media = load(MEDIA)
    media.update(
        {
            "LibraryScope": "",
            "IncludeExtra": True,
            "EnableImageCapture": False,
            "ImageCapturePosition": 10,
            "ImageCapturePostProcessMode": "None",
            "MediaInfoExcludeMediaContainers": "MpegTs,Ts,M2Ts",
            "ImageCaptureExcludeMediaContainers": "MpegTs,Ts,M2Ts",
            "VideoThumbnailExcludeMediaContainers": "MpegTs,Ts,M2Ts",
            "MediaInfoExcludeKeywords": "",
            "VideoThumbnailExcludeKeywords": "",
            "MediaInfoExtractionTimeoutMs": 60000,
            "ExclusiveExtract": True,
            "ExclusiveControlFeatures": "IgnoreFileChange",
            "PersistMediaInfoMode": "Default",
            "MediaInfoJsonRootFolder": "/config/mediainfo-json",
            "CustomProbePath": "",
            "CustomEncoderPath": "",
        }
    )
    save(MEDIA, media)

    metadata = load(METADATA)
    metadata.update(
        {
            "ChineseMovieDb": False,
            "FallbackLanguages": "zh-sg",
            "ChineseTvdb": False,
            "TvdbFallbackLanguages": "zhtw,yue",
            "BlockNonFallbackLanguage": False,
            "ClearTagline": True,
            "PreferTraditionalChinese": False,
            "MovieDbEpisodeGroup": False,
            "EnableMovieDbEpisodeGroupExtendedInfo": True,
            "LocalEpisodeGroup": False,
            "EnhanceMovieDbPerson": True,
            "PreferOriginalPoster": False,
            "PinyinSortName": False,
            "EnhanceNfoMetadata": True,
            "AltMovieDbConfig": False,
            "EnableDoubanAssistScraping": False,
        }
    )
    metadata.setdefault("MetadataRefreshOptions", {}).update(
        {
            "EpisodeRefreshLookbackDays": 365,
            "RatingUpdateLookbackDays": 365,
        }
    )
    metadata.setdefault("MetadataBuildOptions", {}).update(
        {
            "MetadataCacheMode": "None",
            "MetadataCacheRootFolder": "",
        }
    )
    save(METADATA, metadata)

    experience = load(EXPERIENCE)
    experience.update(
        {
            "EnhanceNotificationSystem": False,
            "EnableDeepDelete": True,
            "OptimizeSubtitle": True,
            "MarkPreviousEpisodesPlayed": False,
            "SuppressPluginUpdates": " MovieDb,Tvdb",
            "MergeMultiVersion": True,
            "MergeMoviesPreference": "GlobalScope",
            "MergeSeriesPreference": "LibraryScope",
            "FolderVideoGroupingLimit": 8,
            "BeautifyMultiVersion": False,
            "MultiVersionDisplayPreference": "MediaInfo",
            "MultiVersionReorderPreference": "SystemDefault",
            "LibraryScopePlayProgress": True,
        }
    )
    save(EXPERIENCE, experience)

    TASK.parent.mkdir(parents=True, exist_ok=True)
    TASK.write_text(
        '[{"Type":"DailyTrigger","TimeOfDayTicks":72000000000,'
        '"MaxRuntimeTicks":180000000000}]',
        encoding="utf-8",
    )
finally:
    if was_running:
        subprocess.run(["docker", "start", "emby"], check=True)

print(f"神医助手播放相关优化已应用。修改前备份：{backup}")
print("追更已关闭，并发 1/1，截图关闭，MediaInfo 持久化已开启。")

