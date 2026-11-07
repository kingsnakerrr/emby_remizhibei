import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path

from app import season_repair as repair


class SeasonRepairTest(unittest.TestCase):
    def test_quarantine_rejects_local_and_library_paths(self):
        with patch.dict(os.environ, {'SEASON_REPAIR_COMMON_ROOT': '/cloud-media'}):
            for value in ['/home/symedia_gd/tvshows_error', '/cloud-media',
                          '/cloud-media/symedia_gd/tvshows/error', '/cloud-media/symedia_gd']:
                with self.assertRaises(repair.HTTPException):
                    repair._quarantine_root(value)
            self.assertEqual(str(repair._quarantine_root('/cloud-media/symedia_gd/tvshows_error')),
                             '/cloud-media/symedia_gd/tvshows_error')
            self.assertEqual(repair._quarantine_root(''), repair.QUARANTINE_ROOT)

    def test_common_mount_move_and_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            common = Path(folder)
            source = common / 'symedia_gd/tvshows/test.mkv'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'test')
            a = repair.CLOUD_ROOT / 'test.mkv'
            b = repair.QUARANTINE_ROOT / 'test.mkv'
            with patch.dict(os.environ, {'SEASON_REPAIR_COMMON_ROOT': folder}):
                repair._move_cloud(a, b)
                self.assertFalse(source.exists())
                self.assertEqual((common / 'quarantine/season-overlay/test.mkv').read_bytes(), b'test')
                repair._move_cloud(b, a)
                self.assertEqual(source.read_bytes(), b'test')

    def test_notification_suppression_matches_series_and_path(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            old_root = repair.ROOT
            old_state = repair.STATE_DIR
            old_file = repair.SUPPRESSION_FILE
            repair.ROOT = base / "local"
            repair.STATE_DIR = base / "state"
            repair.SUPPRESSION_FILE = repair.STATE_DIR / "notification_suppressions.json"
            series = repair.ROOT / "日漫" / "测试动画 (2020) {tmdb-1}"
            series.mkdir(parents=True)
            try:
                repair._register_notification_suppression(series, 600)
                self.assertTrue(repair.notification_suppressed({"SeriesName": "测试动画"}))
                self.assertTrue(repair.notification_suppressed({"Path": str(series / "Season 2" / "x.strm")}))
                self.assertFalse(repair.notification_suppressed({"SeriesName": "另一部动画"}))
            finally:
                repair.ROOT = old_root
                repair.STATE_DIR = old_state
                repair.SUPPRESSION_FILE = old_file

    def test_cloud_plan_and_local_rebuild(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            local_root = base / "local"
            cloud_root = base / "cloud"
            relative = Path("anime") / "Test Show (2020) {tmdb-1}"
            local_series = local_root / relative
            cloud_series = cloud_root / relative
            (local_series / "Season 1").mkdir(parents=True)
            (cloud_series / "Season 1").mkdir(parents=True)

            old_root = repair.ROOT
            old_cloud = repair.CLOUD_ROOT
            old_prefix = repair.CLOUD_STRM_PREFIX
            repair.ROOT = local_root
            repair.CLOUD_ROOT = cloud_root
            repair.CLOUD_STRM_PREFIX = Path("/CloudNAS/CloudDrive/test/tvshows")
            try:
                for episode in range(1, 6):
                    name = f"Test.Show.S01E{episode:02d}.第{episode}集"
                    (local_series / "Season 1" / f"{name}.strm").write_text(
                        f"/old/{name}.mkv", encoding="utf-8"
                    )
                    (cloud_series / "Season 1" / f"{name}.mkv").write_bytes(b"video")

                moves = repair._build_exact_plan(local_series, cloud_series, [2, 3])
                self.assertEqual(3, len(moves))
                for source, target in moves:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source.rename(target)

                repair._rebuild_local_series(local_series, cloud_series)
                strms = list(local_series.rglob("*.strm"))
                self.assertEqual(5, len(strms))
                target = local_series / "Season 2" / "Test.Show.S02E01.第1集.strm"
                self.assertTrue(target.exists())
                self.assertEqual(
                    "/CloudNAS/CloudDrive/test/tvshows/anime/"
                    "Test Show (2020) {tmdb-1}/Season 2/Test.Show.S02E01.第1集.mkv",
                    target.read_text(encoding="utf-8"),
                )

                for source, target in reversed(moves):
                    source.parent.mkdir(parents=True, exist_ok=True)
                    target.rename(source)
                self.assertEqual(5, len(list((cloud_series / "Season 1").glob("*.mkv"))))
            finally:
                repair.ROOT = old_root
                repair.CLOUD_ROOT = old_cloud
                repair.CLOUD_STRM_PREFIX = old_prefix

    def test_overlay_cleanup_quarantines_only_surplus_files(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            cloud_root = base / "cloud"
            quarantine_root = base / "quarantine"
            cloud_series = cloud_root / "anime" / "Overlay (2020) {tmdb-2}"
            (cloud_series / "Season 1").mkdir(parents=True)
            (cloud_series / "Season 2").mkdir(parents=True)

            old_cloud = repair.CLOUD_ROOT
            old_quarantine = repair.QUARANTINE_ROOT
            repair.CLOUD_ROOT = cloud_root
            repair.QUARANTINE_ROOT = quarantine_root
            try:
                for season, count in ((1, 2), (2, 3)):
                    for episode in range(1, count + 1):
                        (cloud_series / f"Season {season}" /
                         f"Overlay.S{season:02d}E{episode:02d}.mkv").write_bytes(b"correct")
                for episode in (3, 4):
                    stem = f"Overlay.S01E{episode:02d}.old"
                    (cloud_series / "Season 1" / f"{stem}.mkv").write_bytes(b"stale")
                    (cloud_series / "Season 1" / f"{stem}-thumb.jpg").write_bytes(b"image")

                moves = repair._build_overlay_cleanup_plan(
                    cloud_series, [2, 3], "test-action"
                )
                self.assertEqual(4, len(moves))
                self.assertEqual(2, sum(src.suffix == ".mkv" for src, _ in moves))
                self.assertTrue(all(str(dst).startswith(str(quarantine_root)) for _, dst in moves))
                self.assertTrue(all("E03" in src.name or "E04" in src.name for src, _ in moves))
            finally:
                repair.CLOUD_ROOT = old_cloud
                repair.QUARANTINE_ROOT = old_quarantine

    def test_overlay_local_cleanup_preserves_unrelated_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            cloud_series = base / "cloud" / "Overlay (2020) {tmdb-2}"
            local_series = base / "local" / "Overlay (2020) {tmdb-2}"
            cloud_season = cloud_series / "Season 1"
            local_season = local_series / "Season 1"
            cloud_season.mkdir(parents=True)
            local_season.mkdir(parents=True)

            source = cloud_season / "Overlay.S01E03.old.mkv"
            source.write_bytes(b"surplus")
            (local_series / "poster.jpg").write_bytes(b"poster")
            (local_season / "Overlay.S01E01-thumb.jpg").write_bytes(b"valid")
            (local_season / "Overlay.S01E03.old.strm").write_text("old", encoding="utf-8")
            (local_season / "Overlay.S01E03.old-thumb.jpg").write_bytes(b"old")

            removed = repair._cleanup_local_overlay(
                local_series,
                cloud_series,
                [(source, base / "quarantine" / source.name)],
            )

            self.assertEqual(2, removed)
            self.assertTrue((local_series / "poster.jpg").exists())
            self.assertTrue((local_season / "Overlay.S01E01-thumb.jpg").exists())
            self.assertFalse((local_season / "Overlay.S01E03.old.strm").exists())
            self.assertFalse((local_season / "Overlay.S01E03.old-thumb.jpg").exists())

    def test_overlay_cleanup_refuses_ambiguous_valid_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            cloud_root = base / "cloud"
            quarantine_root = base / "quarantine"
            cloud_series = cloud_root / "anime" / "Ambiguous (2020) {tmdb-3}"
            (cloud_series / "Season 1").mkdir(parents=True)
            (cloud_series / "Season 2").mkdir(parents=True)

            old_cloud = repair.CLOUD_ROOT
            old_quarantine = repair.QUARANTINE_ROOT
            repair.CLOUD_ROOT = cloud_root
            repair.QUARANTINE_ROOT = quarantine_root
            try:
                for season, count in ((1, 2), (2, 2)):
                    for episode in range(1, count + 1):
                        (cloud_series / f"Season {season}" /
                         f"Show.S{season:02d}E{episode:02d}.mkv").write_bytes(b"correct")
                (cloud_series / "Season 2" / "Show.S02E02.old-copy.mkv").write_bytes(b"ambiguous")
                (cloud_series / "Season 2" / "Show.S02E03.old-copy.mkv").write_bytes(b"surplus")

                with self.assertRaises(repair.HTTPException) as raised:
                    repair._build_overlay_cleanup_plan(
                        cloud_series, [2, 2], "test-ambiguous"
                    )
                self.assertEqual(409, raised.exception.status_code)
                self.assertIn("multiple files claim valid episodes", raised.exception.detail)
            finally:
                repair.CLOUD_ROOT = old_cloud
                repair.QUARANTINE_ROOT = old_quarantine


if __name__ == "__main__":
    unittest.main()
