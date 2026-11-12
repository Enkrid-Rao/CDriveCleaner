from __future__ import annotations

import os
import unittest
from unittest import mock

from tests import base
from cdc.core import windows
from cdc.core.config import load_config
from cdc.core.models import MODE_COPY, MODE_LINK, MODE_MOVE, OperationItem
from cdc.core.operations import (
    AuditLog, OperationContext, archive_item, clean_temp, migrate_item,
    restore_archive, undo_item, unlink_item,
)


class OperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = load_config()
        cls.drives = windows.list_drives(force=True)
        cls.cfg.check_locks = False
        cls.cfg.delete_after_undo = True

    def setUp(self):
        self.d, self.e = base.temp_tree("ops")
        self.audit = AuditLog(str(base.data_root() / "state" / f"audit_{self._testMethodName}.jsonl"))
        self.ctx = OperationContext(config=self.cfg, audit=self.audit,
                                    drives=self.drives, progress=None)

    def tearDown(self):
        base.cleanup(self.d, self.e)

    def _source(self, name="src", size=200_000):
        src = self.d / name
        (src / "sub").mkdir(parents=True)
        (src / "a.txt").write_text("hello" * 1000)
        (src / "sub" / "b.bin").write_bytes(os.urandom(size))
        return src

    def test_migrate_and_undo(self):
        src = self._source()
        outside = self.d / "outside"
        outside.mkdir()
        (outside / "x.txt").write_text("outside")
        windows.create_junction(str(src / "linked"), str(outside))
        dst = self.e / "migrated"
        item = OperationItem(action="migrate", source=str(src), dest=str(dst),
                             name="src", size_bytes=windows.directory_size(str(src)))
        result = migrate_item(item, self.ctx)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.verified)
        self.assertTrue(windows.is_junction(str(src)))
        self.assertEqual(os.path.normcase(windows.junction_target(str(src))),
                         os.path.normcase(str(dst)))
        self.assertTrue((dst / "a.txt").exists())
        self.assertTrue((outside / "x.txt").exists())
        records = self.audit.read()
        self.assertTrue(records and records[0].action == "migrate")
        self.assertTrue(records[0].success)

        undo = OperationItem(action="undo", source=str(src), dest=str(dst),
                             name="src", extra={"delete_target": True})
        result2 = undo_item(undo, self.ctx)
        self.assertTrue(result2.ok, result2.error)
        self.assertTrue(result2.verified)
        self.assertFalse(windows.is_junction(str(src)))
        self.assertTrue((src / "a.txt").exists())
        self.assertFalse((src / ".cdc-origin.json").exists())
        self.assertFalse(dst.exists())

    def test_archive_move_and_restore(self):
        src = self._source("videos")
        dst = self.e / "archive"
        item = OperationItem(action="archive", source=str(src), dest=str(dst),
                             name="videos", mode=MODE_MOVE,
                             size_bytes=windows.directory_size(str(src)))
        result = archive_item(item, self.ctx)
        self.assertTrue(result.ok, result.error)
        # 移动归档保留源目录骨架，只清空内容
        self.assertTrue(src.exists())
        self.assertTrue((src / "sub").exists())
        self.assertEqual(list((src / "sub").iterdir()), [])
        self.assertFalse((src / "a.txt").exists())
        self.assertTrue((dst / "a.txt").exists())
        restore = OperationItem(action="restore", source=str(src), dest=str(dst),
                                name="videos")
        result2 = restore_archive(restore, self.ctx)
        self.assertTrue(result2.ok, result2.error)
        self.assertTrue((src / "a.txt").exists())
        self.assertFalse(dst.exists())

    def test_archive_copy_keeps_source(self):
        src = self._source("copy_src")
        dst = self.e / "copy_dst"
        result = archive_item(OperationItem(
            action="archive", source=str(src), dest=str(dst), name="copy_src",
            mode=MODE_COPY, size_bytes=windows.directory_size(str(src))), self.ctx)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(src.exists())
        self.assertTrue((dst / "a.txt").exists())

    def test_archive_link_and_undo(self):
        src = self._source("link_src")
        dst = self.e / "link_dst"
        result = archive_item(OperationItem(
            action="archive", source=str(src), dest=str(dst), name="link_src",
            mode=MODE_LINK, size_bytes=windows.directory_size(str(src))), self.ctx)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(windows.is_junction(str(src)))
        undo = OperationItem(action="undo", source=str(src), dest=str(dst),
                             name="link_src", extra={"delete_target": True})
        result2 = undo_item(undo, self.ctx)
        self.assertTrue(result2.ok, result2.error)
        self.assertTrue((src / "a.txt").exists())
        self.assertFalse(dst.exists())

    def test_clean_temp_respects_retention(self):
        temp = self.d / "faketemp"
        temp.mkdir()
        old = temp / "old.tmp"
        old.write_text("old")
        new = temp / "new.tmp"
        new.write_text("new")
        old_time = 10 * 86400
        os.utime(old, (old.stat().st_atime, old.stat().st_mtime - old_time))
        with mock.patch.dict(os.environ, {"TEMP": str(temp)}):
            result = clean_temp(self.ctx, retention_days=1)
        self.assertTrue(result.ok)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_linked_source_archive_updates_junction(self):
        target = self.d / "target"
        (target / "sub").mkdir(parents=True)
        (target / "a.mp4").write_bytes(os.urandom(100_000))
        (target / "sub" / "b.mkv").write_bytes(os.urandom(50_000))
        source = self.d / "linked"
        ok, err = windows.create_junction(str(source), str(target))
        self.assertTrue(ok, err)
        dest = self.e / "archive_linked"
        item = OperationItem(
            action="archive", source=str(source), dest=str(dest),
            name="linked", mode=MODE_LINK, size_bytes=150_000,
            extra={"junction_source": True, "old_target": str(target)},
        )
        result = archive_item(item, self.ctx)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(windows.is_junction(str(source)))
        self.assertEqual(os.path.normcase(windows.junction_target(str(source))),
                         os.path.normcase(str(dest)))
        self.assertFalse(target.exists())
        self.assertTrue((dest / "a.mp4").exists())

    def test_unlink_only_removes_link(self):
        target = self.d / "unlink_target"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        source = self.d / "unlink_source"
        ok, err = windows.create_junction(str(source), str(target))
        self.assertTrue(ok, err)
        result = unlink_item(OperationItem(action="unlink", source=str(source),
                                           dest=str(target), name="unlink"), self.ctx)
        self.assertTrue(result.ok, result.error)
        self.assertFalse(source.exists())
        self.assertTrue((target / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
