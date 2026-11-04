import tempfile
import unittest
from pathlib import Path

from app import season_repair as repair


class SeasonRepairTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
