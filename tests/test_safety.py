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


class ArchiveModeTests(unittest.TestCase):
    """冷数据归档 = 剪切：普通目录不允许「链接归档」，只有 Junction 源可以改指。"""

    def setUp(self):
        self.d, self.e = base.temp_tree("shell")
        self.home = self.d / "home"
        self.downloads = self.home / "Downloads"
        self.media = self.home / "Media"
        for path in (self.downloads, self.media):
            path.mkdir(parents=True, exist_ok=True)
            (path / "a.bin").write_bytes(b"x" * 4096)
        self.cfg = load_config()
        self.cfg.link_root = str(self.d / "links")
        self.cfg.archive_root = str(self.e / "archive")
        self.cfg.zones = {"userhome": {
            "source": str(self.home),
            "dest_base": str(self.d / "links" / "home"),
            "no_go": ["Downloads", "Desktop", "Documents"],
            "label": "用户主目录",
            "needs_admin": False,
        }}

    def tearDown(self):
        base.cleanup(self.d, self.e)

    def _item(self, source, mode):
        return OperationItem(action="archive", source=str(source),
                             dest=str(self.e / "archive" / source.name),
                             size_bytes=4096, mode=mode)

    def test_link_archive_rejected_for_regular_dir(self):
        result = safety.preflight_archive(self._item(self.downloads, "link"),
                                          self.cfg, windows.list_drives())
        self.assertFalse(result.ok)
        self.assertTrue(any("不会在原位置保留链接" in err for err in result.errors),
                        result.errors)

    def test_link_archive_rejected_even_for_ordinary_folder(self):
        result = safety.preflight_archive(self._item(self.media, "link"),
                                          self.cfg, windows.list_drives())
        self.assertFalse(result.ok)

    def test_move_archive_still_allowed_for_downloads(self):
        result = safety.preflight_archive(self._item(self.downloads, "move"),
                                          self.cfg, windows.list_drives())
        self.assertTrue(result.ok, result.errors)

    def test_link_archive_allowed_for_existing_junction(self):
        target = self.d / "app_target"
        target.mkdir(exist_ok=True)
        (target / "app.bin").write_bytes(b"x" * 1024)
        link = self.home / "LinkedApp"
        ok, err = windows.create_junction(str(link), str(target))
        self.assertTrue(ok, err)
        result = safety.preflight_archive(self._item(link, "link"),
                                          self.cfg, windows.list_drives())
        self.assertTrue(result.ok, result.errors)

    def test_preflight_blocks_when_junction_is_locked(self):
        """移动归档要删链接，被占用时预检就该拦住，而不是复制完几个 GB 才失败。"""
        target = self.d / "locked_target"
        target.mkdir(exist_ok=True)
        (target / "app.bin").write_bytes(b"x" * 1024)
        link = self.home / "LockedApp"
        ok, err = windows.create_junction(str(link), str(target))
        self.assertTrue(ok, err)

        kernel32, handle = base.lock_dir(str(link))
        try:
            result = safety.preflight_archive(self._item(link, "move"),
                                              self.cfg, windows.list_drives())
        finally:
            base.unlock_dir(kernel32, handle)
        self.assertFalse(result.ok)
        self.assertTrue(any("删不掉" in error for error in result.errors),
                        result.errors)


if __name__ == "__main__":
    unittest.main()
