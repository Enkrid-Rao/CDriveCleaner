"""Everything 索引加速模块的单元测试（不依赖本机真的装 Everything）。"""

from __future__ import annotations

import os
import unittest
from unittest import mock

from tests import base  # noqa: F401  (设置 CDC_DATA_DIR / 测试环境)

from cdc.core import everything


class ParserTests(unittest.TestCase):
    def test_parses_size_and_iso_date(self):
        text = (
            "107,374,182,400 2026-10-12 21:10:09 E:\\Forensic\\Images\\a.e01\n"
            "           822 2023-12-29 4:19:10  C:\\Users\\me\\Downloads\\x.txt\n"
        )
        rows = everything._parse_rows(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].size, 107_374_182_400)
        self.assertGreater(rows[0].modified, 0)
        self.assertEqual(rows[1].size, 822)

    def test_parses_slash_date_and_skips_dirs(self):
        text = (
            "           640 2024/01/02 03:04 C:\\Users\\me\\a.txt\n"
            "<DIR>          C:\\Users\\me\\sub\n"
        )
        rows = everything._parse_rows(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].path, r"C:\Users\me\a.txt")
        self.assertGreater(rows[0].modified, 0)

    def test_ignores_garbage_lines(self):
        self.assertEqual(everything._parse_rows("ES 1.1.0\n\n"), [])


class SubdirStatsTests(unittest.TestCase):
    def test_buckets_by_first_level_dir(self):
        rows = [
            everything.IndexedFile(r"C:\Users\me\Downloads\a.zip", 100, 0.0),
            everything.IndexedFile(r"C:\Users\me\Downloads\sub\b.zip", 50, 0.0),
            everything.IndexedFile(r"C:\Users\me\Downloads\c.txt", 10, 0.0),
            everything.IndexedFile(r"C:\Users\me\Documents\d.pdf", 30, 0.0),
            everything.IndexedFile(r"C:\Users\me\root.txt", 5, 0.0),
        ]
        with mock.patch.object(everything, "query_files", return_value=rows):
            buckets = everything.subdir_stats(r"C:\Users\me")
        self.assertEqual(set(buckets), {"downloads", "documents"})
        downloads = buckets["downloads"]
        self.assertEqual(downloads.files, 3)
        self.assertEqual(downloads.bytes, 160)
        self.assertEqual(downloads.ext_bytes["zip"], 150)
        self.assertEqual(downloads.ext_bytes["txt"], 10)

    def test_dir_stats_matches_expected(self):
        rows = [
            everything.IndexedFile(r"C:\x\a.bin", 100, 2000.0),
            everything.IndexedFile(r"C:\x\b.bin", 200, 3000.0),
        ]
        with mock.patch.object(everything, "query_files", return_value=rows):
            stats = everything.dir_stats(r"C:\x")
        self.assertEqual((stats.files, stats.bytes), (2, 300))
        self.assertEqual(stats.newest, 3000.0)
        self.assertEqual(stats.oldest, 2000.0)


class AvailabilityTests(unittest.TestCase):
    def test_env_var_disables(self):
        everything.refresh()
        with mock.patch.dict(os.environ, {"CDC_NO_EVERYTHING": "1"}):
            everything.refresh()
            self.assertFalse(everything.available())
        everything.refresh()

    def test_missing_cli_raises(self):
        everything.refresh()
        with mock.patch.dict(os.environ, {"CDC_NO_EVERYTHING": "1"}):
            everything.refresh()
            with self.assertRaises(everything.EverythingError):
                everything.query_files(r"C:\Users")
        everything.refresh()


if __name__ == "__main__":
    unittest.main()
