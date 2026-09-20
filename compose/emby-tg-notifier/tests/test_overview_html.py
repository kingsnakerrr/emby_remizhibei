import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


TEMP = tempfile.TemporaryDirectory()
os.environ["SESSION_SECRET_FILE"] = str(Path(TEMP.name) / "secret")
spec = importlib.util.spec_from_file_location(
    "notifier_overview_test",
    Path(__file__).resolve().parents[1] / "app/main.py",
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class OverviewHtmlTests(unittest.TestCase):
    def test_br_tags_become_paragraphs(self):
        item = {
            "Overview": "第一段<br><br> 第二段<br/>第三行<BR /> <b>结尾</b>",
        }

        overview = m._notification_overview(item)

        self.assertEqual(overview, "第一段\n\n第二段\n第三行\n结尾")
        self.assertNotIn("<br", overview.lower())

    def test_html_entities_and_block_tags_are_cleaned(self):
        item = {
            "Overview": "<p>A &amp; B</p><div>内容</div><ul><li>一</li><li>二</li></ul>",
        }

        self.assertEqual(m._notification_overview(item), "A & B\n内容\n• 一\n• 二")

    def test_sidecar_poster_is_used_before_emby_image(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "CJOD-536.strm"
            media.write_text("https://example.invalid/video", encoding="utf-8")
            expected = b"\xff\xd8\xff" + b"poster-data"
            (Path(folder) / "poster.jpg").write_bytes(expected)

            self.assertEqual(m._read_sidecar_poster({"Path": str(media)}), expected)

    def test_invalid_sidecar_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "CJOD-536.strm"
            media.write_text("https://example.invalid/video", encoding="utf-8")
            (Path(folder) / "poster.jpg").write_text("not a jpeg", encoding="utf-8")

            self.assertIsNone(m._read_sidecar_poster({"Path": str(media)}))


if __name__ == "__main__":
    unittest.main()
