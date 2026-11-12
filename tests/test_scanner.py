from __future__ import annotations

import os
import unittest

from tests import base
from cdc.core import scanner, windows
from cdc.core.config import load_config
from cdc.core.models import TIER_RECOMMEND, TIER_SKIP, TIER_STRONG


class ClassifyTests(unittest.TestCase):
    def _stats(self, **ext):
        stats = windows.DirStats()
        stats.ext_bytes = {k: v for k, v in ext.items()}
        stats.bytes = sum(stats.ext_bytes.values())
        stats.files = 10
        return stats

    def test_video_is_strong(self):
        stats = self._stats(video=3 * 1024 ** 3)
        tier, score, reason, _ = scanner.classify_cold(
            "Videos", stats, size_min_bytes=100 * 1024 ** 2)
        self.assertEqual(tier, TIER_STRONG)
        self.assertGreaterEqual(score, 90)
        self.assertIn("视频", reason)

    def test_code_is_skipped(self):
        stats = self._stats(code=500 * 1024 ** 2, other=10 * 1024 ** 2)
        tier, _score, _reason, _ = scanner.classify_cold(
            "Projects", stats, size_min_bytes=100 * 1024 ** 2)
        self.assertEqual(tier, TIER_SKIP)

    def test_chat_is_skipped(self):
        stats = self._stats(other=5 * 1024 ** 3)
        tier, _score, reason, _ = scanner.classify_cold(
            "xwechat_files", stats, size_min_bytes=100 * 1024 ** 2)
        self.assertEqual(tier, TIER_SKIP)
        self.assertIn("聊天", reason)

    def test_small_is_skipped(self):
        stats = self._stats(video=10 * 1024 ** 2)
        tier, _score, _reason, _ = scanner.classify_cold(
            "clip", stats, size_min_bytes=100 * 1024 ** 2)
        self.assertEqual(tier, TIER_SKIP)


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_es = scanner._ES_PATH
        scanner._ES_PATH = ""

    @classmethod
    def tearDownClass(cls):
        scanner._ES_PATH = cls._old_es

    def setUp(self):
        self.d, self.e = base.temp_tree("scan")
        self.cfg = load_config()
        self.cfg.threshold_mb = 1
        self.cfg.archive_root = str(self.e / "archive")
        self.zone = self.d / "zone"
        (self.zone / "Big").mkdir(parents=True)
        (self.zone / "Big" / "f.bin").write_bytes(os.urandom(3_000_000))
        (self.zone / "Protected").mkdir()
        (self.zone / "Protected" / "p.bin").write_bytes(os.urandom(2_000_000))
        target = self.d / "target"
        target.mkdir()
        (target / "old.mkv").write_bytes(os.urandom(2_000_000))
        windows.create_junction(str(self.zone / "Linked"), str(target))
        self.cfg.zones = {"test": {
            "source": str(self.zone), "dest_base": str(self.d / "dest"),
            "no_go": ["Protected"], "label": "测试区", "needs_admin": False,
        }}

    def tearDown(self):
        base.cleanup(self.d, self.e)

    def test_scan_zones(self):
        result = scanner.scan_zones(self.cfg, drives=windows.list_drives())
        self.assertEqual([i.name for i in result.items], ["Big"])
        self.assertEqual(result.items[0].size_bytes, 3_000_000)
        self.assertEqual([j.name for j in result.junctions], ["Linked"])
        self.assertTrue(result.junctions[0].target_exists)
        self.assertEqual([p.name for p in result.protected_items], ["Protected"])
        self.assertGreater(result.potential_bytes, 0)

    def test_analyze_cold_candidates(self):
        media = self.zone / "Videos"
        media.mkdir()
        (media / "a.mp4").write_bytes(os.urandom(2_000_000))
        self.cfg.zones = {}
        result = scanner.analyze_cold(self.cfg, roots=[(str(self.zone), "测试")],
                                      min_size_bytes=100_000)
        names = {c.name for c in result.candidates}
        self.assertIn("Videos", names)
        cand = next(c for c in result.candidates if c.name == "Videos")
        self.assertTrue(cand.dest_path.startswith(str(self.e / "archive")))
        self.assertEqual(os.path.basename(cand.dest_path), "Videos")


if __name__ == "__main__":
    unittest.main()
