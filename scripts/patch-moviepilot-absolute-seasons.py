#!/usr/bin/env python3
"""Patch MoviePilot transfer.py to safely split exact absolute-number TV packs."""

import argparse
import py_compile
import shutil
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path


MARKER = "absolute_episode_map: Dict[int, Tuple[int, int]] = {}"
TOGGLE_GUARD = 'Path("/config/tvseasonpreflight.disabled").exists()'
CONFLICT_MARKER = "absolute_episode_conflict: Optional[str] = None"
MEDIA_SERVER_IMPORT = "from app.db.mediaserver_oper import MediaServerOper"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def _patch_source_base(text: str) -> str:
    if MEDIA_SERVER_IMPORT not in text:
        text = replace_once(
            text,
            "from app.db.downloadhistory_oper import DownloadHistoryOper\n",
            "from app.db.downloadhistory_oper import DownloadHistoryOper\n"
            f"{MEDIA_SERVER_IMPORT}\n",
            "media server import",
        )

    if MARKER in text:
        if TOGGLE_GUARD not in text:
            text = replace_once(
                text,
                "            nonlocal absolute_episode_map\n"
                "            if not mediainfo or mediainfo.type != MediaType.TV:\n",
                "            nonlocal absolute_episode_map\n"
                "            if Path(\"/config/tvseasonpreflight.disabled\").exists():\n"
                "                return\n"
                "            if not mediainfo or mediainfo.type != MediaType.TV:\n",
                "runtime toggle guard",
            )
        if CONFLICT_MARKER not in text:
            text = replace_once(
                text,
                f"        {MARKER}\n",
                f"        {MARKER}\n"
                "        absolute_episode_conflict: Optional[str] = None\n",
                "existing-library conflict state",
            )
            text = replace_once(
                text,
                "            nonlocal absolute_episode_map\n"
                "            if Path(\"/config/tvseasonpreflight.disabled\").exists():\n",
                "            nonlocal absolute_episode_map, absolute_episode_conflict\n"
                "            if Path(\"/config/tvseasonpreflight.disabled\").exists():\n",
                "existing-library conflict nonlocal",
            )
            text = replace_once(
                text,
                "            mapping: Dict[int, Tuple[int, int]] = {}\n",
                "            existing_item = MediaServerOper().exists(\n"
                "                tmdbid=int(tmdb_id), mtype=MediaType.TV.value\n"
                "            )\n"
                "            existing_history = TransferHistoryOper().get_by_type_tmdbid(\n"
                "                tmdbid=int(tmdb_id), mtype=MediaType.TV.value\n"
                "            )\n"
                "            if existing_item or (existing_history and existing_history.status):\n"
                "                absolute_episode_conflict = (\n"
                "                    f\"{mediainfo.title_year} 已存在于媒体库；为避免新旧两套季集叠加，\"\n"
                "                    \"已阻止本次绝对集数全集整理。请先使用旧媒体季度修复助手处理现有媒体。\"\n"
                "                )\n"
                "                logger.warning(absolute_episode_conflict)\n"
                "                return\n\n"
                "            mapping: Dict[int, Tuple[int, int]] = {}\n",
                "existing-library guard",
            )
            text = replace_once(
                text,
                "        _prepare_absolute_episode_remap(file_items)\n\n"
                "        planned_file_count = len(file_items)\n",
                "        _prepare_absolute_episode_remap(file_items)\n"
                "        if absolute_episode_conflict:\n"
                "            return False, absolute_episode_conflict\n\n"
                "        planned_file_count = len(file_items)\n",
                "existing-library conflict abort",
            )
        return text

    text = replace_once(
        text,
        "        matched_episode_format_template = False\n",
        "        matched_episode_format_template = False\n"
        "        # Exact full-series packs may use S01E001..S01E291 absolute numbering.\n"
        "        # Keep ordinary and uncertain transfers unchanged.\n"
        "        absolute_episode_map: Dict[int, Tuple[int, int]] = {}\n"
        "        absolute_episode_conflict: Optional[str] = None\n",
        "state marker",
    )
    text = replace_once(
        text,
        "                return built_meta\n"
        "            return _apply_meta_overrides(built_meta, source_path)\n",
        "                return _apply_absolute_episode_remap(built_meta)\n"
        "            return _apply_absolute_episode_remap(\n"
        "                _apply_meta_overrides(built_meta, source_path)\n"
        "            )\n",
        "metadata return",
    )

    helper = textwrap.dedent(
        '''
        def _apply_absolute_episode_remap(
                current_meta: Optional[MetaBase]
        ) -> Optional[MetaBase]:
            if not current_meta or not absolute_episode_map:
                return current_meta
            if current_meta.begin_season != 1:
                return current_meta
            begin_episode = current_meta.begin_episode
            end_episode = current_meta.end_episode
            if begin_episode not in absolute_episode_map:
                return current_meta
            mapped_season, mapped_episode = absolute_episode_map[begin_episode]
            if end_episode is not None and end_episode != begin_episode:
                mapped_end = absolute_episode_map.get(end_episode)
                if not mapped_end or mapped_end[0] != mapped_season:
                    return current_meta
                current_meta.end_episode = mapped_end[1]
            current_meta.begin_season = mapped_season
            current_meta.begin_episode = mapped_episode
            return current_meta

        def _prepare_absolute_episode_remap(
                planned_items: List[Tuple[FileItem, bool]]
        ) -> None:
            """Enable remapping only after an exact TMDB-total match."""
            nonlocal absolute_episode_map, absolute_episode_conflict
            if Path("/config/tvseasonpreflight.disabled").exists():
                return
            if not mediainfo or mediainfo.type != MediaType.TV:
                return
            tmdb_id = getattr(mediainfo, "tmdb_id", None)
            if not tmdb_id:
                return

            absolute_episodes: List[int] = []
            for candidate_item, is_bluray_dir in planned_items:
                if is_bluray_dir or not self.__is_media_file(candidate_item):
                    continue
                candidate_meta = MetaInfoPath(Path(candidate_item.path))
                if (
                        not candidate_meta
                        or candidate_meta.begin_season != 1
                        or candidate_meta.begin_episode is None
                        or candidate_meta.end_episode not in (
                            None, candidate_meta.begin_episode
                        )
                ):
                    return
                absolute_episodes.append(int(candidate_meta.begin_episode))

            if len(absolute_episodes) < 40 or max(absolute_episodes, default=0) < 40:
                return
            if sorted(absolute_episodes) != list(
                    range(1, len(absolute_episodes) + 1)
            ):
                logger.warning(
                    f"{mediainfo.title_year} 疑似绝对集数包，但集数不连续或有重复；"
                    "为避免误改，保持原命名。"
                )
                return

            try:
                tmdb_seasons = TmdbChain().tmdb_seasons(int(tmdb_id)) or []
                season_counts = {
                    int(item.season_number): int(item.episode_count or 0)
                    for item in tmdb_seasons
                    if int(item.season_number or 0) > 0
                    and int(item.episode_count or 0) > 0
                }
            except Exception as err:
                logger.warning(
                    f"{mediainfo.title_year} 获取 TMDB 分季数据失败，"
                    f"不执行绝对集数转换：{type(err).__name__}: {err}"
                )
                return

            if (
                    len(season_counts) < 2
                    or sorted(season_counts) != list(
                        range(1, len(season_counts) + 1)
                    )
                    or sum(season_counts.values()) != len(absolute_episodes)
                    or max(absolute_episodes) <= season_counts.get(1, 0)
            ):
                logger.warning(
                    f"{mediainfo.title_year} 疑似绝对集数包，但文件总数 "
                    f"{len(absolute_episodes)} 与 TMDB 正式季度合计 "
                    f"{sum(season_counts.values())} 不一致；为避免误改，保持原命名。"
                )
                return

            existing_item = MediaServerOper().exists(
                tmdbid=int(tmdb_id), mtype=MediaType.TV.value
            )
            existing_history = TransferHistoryOper().get_by_type_tmdbid(
                tmdbid=int(tmdb_id), mtype=MediaType.TV.value
            )
            if existing_item or (existing_history and existing_history.status):
                absolute_episode_conflict = (
                    f"{mediainfo.title_year} 已存在于媒体库；为避免新旧两套季集叠加，"
                    "已阻止本次绝对集数全集整理。请先使用旧媒体季度修复助手处理现有媒体。"
                )
                logger.warning(absolute_episode_conflict)
                return

            mapping: Dict[int, Tuple[int, int]] = {}
            absolute_number = 1
            for season_number in sorted(season_counts):
                for episode_number in range(1, season_counts[season_number] + 1):
                    mapping[absolute_number] = (season_number, episode_number)
                    absolute_number += 1
            absolute_episode_map = mapping
            logger.warning(
                f"{mediainfo.title_year} 已严格核验绝对集数全集包："
                f"{len(mapping)} 集，将按 TMDB {len(season_counts)} 季自动分季命名。"
            )
        '''
    ).strip("\n")
    helper = textwrap.indent(helper, "        ") + "\n\n"
    text = replace_once(
        text,
        "            return current_meta\n\n"
        "        def _is_allowed_transfer_item",
        "            return current_meta\n\n" + helper +
        "        def _is_allowed_transfer_item",
        "helper insertion",
    )
    text = replace_once(
        text,
        "        file_items, inherited_meta_map = _plan_file_items(file_items)\n",
        "        file_items, inherited_meta_map = _plan_file_items(file_items)\n"
        "        _prepare_absolute_episode_remap(file_items)\n"
        "        if absolute_episode_conflict:\n"
        "            return False, absolute_episode_conflict\n",
        "activation",
    )
    return text


def patch_source(text: str) -> str:
    text = _patch_source_base(text)
    marker = "# Reject verified incomplete duplicate identities before generating paths."
    if marker not in text:
        anchor = "            absolute_episodes: List[int] = []\n"
        guard = '''            # Reject verified incomplete duplicate identities before generating paths.
            if int(tmdb_id) == 291141:
                absolute_episode_conflict = (
                    f"{mediainfo.title_year} 命中残缺重复 TMDB 条目 291141；"
                    "已阻止本次绝对集数全集整理。请重新识别为 TMDB 19389 第3季，"
                    "对应38集；不会按错误条目继续入库。"
                )
                logger.warning(absolute_episode_conflict)
                return

'''
        text = replace_once(text, anchor, guard + anchor, "duplicate identity guard")
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        default="/opt/docker-compose/moviepilot/overrides/transfer.py",
    )
    parser.add_argument("--container", default="moviepilot-v2")
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    target = Path(args.target).resolve(strict=True)
    original = target.read_text(encoding="utf-8")
    patched = patch_source(original)
    if patched == original:
        print("already installed")
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(f"{target.name}.before-absolute-seasons-{stamp}")
    shutil.copy2(target, backup)
    temporary = target.with_name(f".{target.name}.absolute-seasons.tmp")
    temporary.write_text(patched, encoding="utf-8", newline="\n")
    py_compile.compile(str(temporary), doraise=True)
    temporary.replace(target)
    print(f"installed; backup: {backup}")
    if args.restart:
        subprocess.run(["docker", "restart", args.container], check=True)


if __name__ == "__main__":
    main()
