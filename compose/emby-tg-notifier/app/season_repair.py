"""Authenticated repair agent for incorrectly flattened TV seasons.

Only sidecar metadata under SEASON_REPAIR_ROOT is touched.  Cloud media and
STRM contents are never modified.  Every apply operation creates a tar backup
and a reversible move manifest before the first rename.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tarfile
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/season-repair", tags=["season-repair"])

ROOT = Path(os.getenv("SEASON_REPAIR_ROOT", "/home/symedia_gd/tvshows"))
TOKEN_FILE = Path(os.getenv("SEASON_REPAIR_TOKEN_FILE", "/data/season_repair_token"))
STATE_DIR = Path(os.getenv("SEASON_REPAIR_STATE_DIR", "/data/season-repair"))
EP_RE = re.compile(r"(?i)S(?P<season>\d{1,3})E(?P<episode>\d{1,4})")
TMDB_RE = re.compile(r"(?i)\{tmdb-(\d+)\}")
ALLOWED_SUFFIXES = {".strm", ".nfo", ".jpg", ".jpeg", ".png", ".webp", ".srt", ".ass", ".ssa"}


def _token() -> str:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        value = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    TOKEN_FILE.write_text(value, encoding="utf-8")
    os.chmod(TOKEN_FILE, 0o600)
    return value


def _authorize(request: Request) -> None:
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {_token()}"
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid repair token")


def _inside_root(path: Path) -> Path:
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(status_code=400, detail="path outside repair root")
    return resolved


def _series_path(relative: str) -> Path:
    relative = str(relative or "").strip().replace("\\", "/").lstrip("/")
    if not relative or ".." in Path(relative).parts:
        raise HTTPException(status_code=400, detail="invalid series path")
    path = _inside_root(ROOT / relative)
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="series directory not found")
    return path


def _scan_series(path: Path) -> dict:
    episodes: dict[int, set[int]] = {}
    strm_count = 0
    for file in path.rglob("*.strm"):
        match = EP_RE.search(file.name)
        if not match:
            continue
        season = int(match.group("season"))
        episode = int(match.group("episode"))
        episodes.setdefault(season, set()).add(episode)
        strm_count += 1
    seasons = []
    for season, values in sorted(episodes.items()):
        ordered = sorted(values)
        missing = [n for n in range(ordered[0], ordered[-1] + 1) if n not in values] if ordered else []
        seasons.append({
            "season": season,
            "count": len(ordered),
            "min": ordered[0] if ordered else 0,
            "max": ordered[-1] if ordered else 0,
            "missing": missing[:100],
            "contiguous_from_one": ordered == list(range(1, len(ordered) + 1)),
        })
    tmdb = TMDB_RE.search(path.name)
    return {
        "series_rel": path.relative_to(ROOT.resolve()).as_posix(),
        "name": re.sub(r"\s*\{tmdb-\d+\}\s*$", "", path.name, flags=re.I),
        "tmdb_id": int(tmdb.group(1)) if tmdb else 0,
        "strm_count": strm_count,
        "seasons": seasons,
    }


def _series_dirs() -> list[Path]:
    if not ROOT.exists():
        return []
    found = []
    for path in ROOT.rglob("*"):
        if path.is_dir() and TMDB_RE.search(path.name):
            found.append(path)
    return found


@router.post("/scan")
async def scan(request: Request):
    _authorize(request)
    rows = [_scan_series(path) for path in _series_dirs()]
    return {"root": str(ROOT), "series": [row for row in rows if row["strm_count"]]}


def _target_name(name: str, source_season: int, absolute_episode: int,
                 target_season: int, target_episode: int) -> str:
    pattern = re.compile(rf"(?i)S0*{source_season}E0*{absolute_episode}(?!\d)")
    updated, count = pattern.subn(f"S{target_season:02d}E{target_episode:02d}", name, count=1)
    if not count:
        raise HTTPException(status_code=409, detail=f"unable to rename {name}")
    updated = re.sub(rf"第\s*{absolute_episode}\s*集", f"第{target_episode}集", updated, count=1)
    return updated


def _build_exact_plan(series: Path, official_counts: list[int]) -> list[tuple[Path, Path]]:
    official_counts = [int(x) for x in official_counts if int(x) > 0]
    if len(official_counts) < 2:
        raise HTTPException(status_code=409, detail="official season list is incomplete")
    scanned = _scan_series(series)
    if len(scanned["seasons"]) != 1:
        raise HTTPException(status_code=409, detail="exact repair requires one flattened source season")
    source = scanned["seasons"][0]
    total = sum(official_counts)
    if not source["contiguous_from_one"] or source["count"] != total:
        raise HTTPException(status_code=409, detail="episode total does not exactly match TMDB; manual review required")
    source_season = source["season"]
    mapping = {}
    absolute = 1
    for season, count in enumerate(official_counts, start=1):
        for episode in range(1, count + 1):
            mapping[absolute] = (season, episode)
            absolute += 1
    moves = []
    matched_strm_count = 0
    for path in series.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        match = EP_RE.search(path.name)
        if not match or int(match.group("season")) != source_season:
            continue
        old_episode = int(match.group("episode"))
        if old_episode not in mapping:
            continue
        if path.suffix.lower() == ".strm":
            matched_strm_count += 1
        target_season, target_episode = mapping[old_episode]
        target_dir = series / f"Season {target_season}"
        target = target_dir / _target_name(path.name, source_season, old_episode, target_season, target_episode)
        if target == path:
            continue
        moves.append((_inside_root(path), _inside_root(target)))
    if matched_strm_count != total:
        raise HTTPException(status_code=409, detail="STRM files changed during scan; run scan again")
    destinations = [dst for _, dst in moves]
    if len(destinations) != len(set(destinations)):
        raise HTTPException(status_code=409, detail="destination collision in repair plan")
    for source_path, target_path in moves:
        if target_path.exists() and target_path != source_path:
            raise HTTPException(status_code=409, detail=f"destination already exists: {target_path.name}")
    return moves


@router.post("/apply-exact")
async def apply_exact(request: Request):
    _authorize(request)
    body = await request.json()
    series = _series_path(body.get("series_rel", ""))
    counts = body.get("official_counts") or []
    moves = _build_exact_plan(series, counts)
    if body.get("preview", True):
        return {
            "preview": True,
            "move_count": len(moves),
            "strm_count": sum(1 for src, _ in moves if src.suffix.lower() == ".strm"),
            "examples": [{"from": a.name, "to": b.name} for a, b in moves[:12]],
        }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    action_id = f"{int(time.time())}-{secrets.token_hex(4)}"
    backup_dir = STATE_DIR / "backups"
    manifest_dir = STATE_DIR / "manifests"
    backup_dir.mkdir(exist_ok=True)
    manifest_dir.mkdir(exist_ok=True)
    backup = backup_dir / f"{action_id}.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        archive.add(series, arcname=series.name)
    manifest = {
        "action_id": action_id,
        "series_rel": series.relative_to(ROOT.resolve()).as_posix(),
        "backup": str(backup),
        "created_at": time.time(),
        "moves": [{"from": str(a), "to": str(b)} for a, b in moves],
    }
    manifest_path = manifest_dir / f"{action_id}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    completed = []
    try:
        for source_path, target_path in moves:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.rename(target_path)
            completed.append((source_path, target_path))
    except Exception as exc:
        for source_path, target_path in reversed(completed):
            if target_path.exists() and not source_path.exists():
                source_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.rename(source_path)
        raise HTTPException(status_code=500, detail=f"repair rolled back: {exc}")
    return {"ok": True, "action_id": action_id, "move_count": len(moves), "backup": str(backup)}


@router.post("/undo/{action_id}")
async def undo(action_id: str, request: Request):
    _authorize(request)
    if not re.fullmatch(r"\d+-[0-9a-f]{8}", action_id):
        raise HTTPException(status_code=400, detail="invalid action id")
    manifest_path = STATE_DIR / "manifests" / f"{action_id}.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="repair action not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    moves = [(_inside_root(Path(item["from"])), _inside_root(Path(item["to"]))) for item in manifest["moves"]]
    for source_path, target_path in moves:
        if source_path.exists() or not target_path.exists():
            raise HTTPException(status_code=409, detail="library changed after repair; refusing automatic undo")
    for source_path, target_path in reversed(moves):
        source_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.rename(source_path)
    manifest_path.rename(manifest_path.with_suffix(".undone.json"))
    return {"ok": True, "action_id": action_id, "restored": len(moves)}
