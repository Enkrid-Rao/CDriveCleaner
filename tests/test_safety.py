from __future__ import annotations

import os
import unittest

from tests import base
from cdc.core import safety, windows
from cdc.core.config import load_config
from cdc.core.models import OperationItem


class SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d, cls.e = base.temp_tree("safety")
        cls.cfg = load_config()
        cls.cfg.link_root = str(cls.d / "links")
        cls.cfg.archive_root = str(cls.e / "archive")

    @classmethod
    def tearDownClass(cls):
        base.cleanup(cls.d, cls.e)

    def test_protected_roots(self):
        protected, _ = safety.is_protected_path("C:\\")
        self.assertTrue(protected)
        protected, _ = safety.is_protected_path("C:\\Windows")
        self.assertTrue(protected)
        protected, _ = safety.is_protected_path("C:\\$Recycle.Bin")
        self.assertTrue(protected)
        protected, _ = safety.is_protected_path("D:\\Projects\\CDriveCleaner\\cdc")
        self.assertFalse(protected)

    def test_origin_conflict(self):
        src = self.d / "src1"
        dst = self.e / "dst1"
        src.mkdir(parents=True, exist_ok=True)
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "file.txt").write_text("x")
        self.assertTrue(safety.origin_conflict(str(dst), str(src)))
        safety.write_origin(str(dst), str(src), action="archive", mode="move",
                            op_id="x", size_bytes=1)
        self.assertEqual(safety.origin_conflict(str(dst), str(src)), "")
        other = self.d / "src2"
        other.mkdir(exist_ok=True)
        self.assertTrue(safety.origin_conflict(str(dst), str(other)))

    def test_preflight_rejects_same_partition(self):
        src = self.d / "same"
        src.mkdir(exist_ok=True)
        (src / "a.txt").write_text("x")
        item = OperationItem(action="migrate", source=str(src),
                             dest=str(self.d / "dest"), size_bytes=1)
        result = safety.preflight_migrate(item, self.cfg, windows.list_drives())
        self.assertFalse(result.ok)

    def test_preflight_rejects_root(self):
        item = OperationItem(action="archive", source="C:\\",
                             dest=str(self.e / "x"), size_bytes=1)
        result = safety.preflight_archive(item, self.cfg, windows.list_drives())
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
