from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests import base
from cdc.core import windows


class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.d, self.e = base.temp_tree("win")

    def tearDown(self):
        base.cleanup(self.d, self.e)

    def test_junction_roundtrip_and_safe_delete(self):
        target = self.d / "target"
        target.mkdir()
        (target / "keep.txt").write_text("must survive")
        link = self.d / "link"
        ok, err = windows.create_junction(str(link), str(target))
        self.assertTrue(ok, err)
        self.assertTrue(windows.is_junction(str(link)))
        self.assertEqual(os.path.normcase(windows.junction_target(str(link))),
                         os.path.normcase(str(target)))
        # 安全删除链接所在目录：链接被删除，目标数据必须完好
        container = self.d / "container"
        container.mkdir()
        windows.create_junction(str(container / "inner"), str(target))
        report = windows.safe_delete_tree(str(container))
        self.assertTrue(report.ok, report.errors)
        self.assertFalse((container / "inner").exists())
        self.assertTrue((target / "keep.txt").exists())

    def test_safe_delete_tree_does_not_follow_junction(self):
        target = self.d / "victim"
        target.mkdir()
        (target / "data.bin").write_bytes(b"x" * 1024)
        victim = self.d / "victim_dir"
        victim.mkdir()
        (victim / "real.txt").write_text("real")
        windows.create_junction(str(victim / "link"), str(target))
        report = windows.safe_delete_tree(str(victim))
        self.assertTrue(report.ok, report.errors)
        self.assertFalse(victim.exists())
        self.assertTrue((target / "data.bin").exists())

    def test_stats_skip_junction(self):
        target = self.d / "big"
        target.mkdir()
        (target / "f.bin").write_bytes(b"y" * 4096)
        root = self.d / "root"
        root.mkdir()
        (root / "a.bin").write_bytes(b"z" * 1024)
        windows.create_junction(str(root / "linked"), str(target))
        stats = windows.directory_stats(str(root))
        self.assertEqual(stats.files, 1)
        self.assertEqual(stats.bytes, 1024)
        self.assertEqual(stats.links, 1)

    def test_clear_keep_structure(self):
        root = self.d / "keep"
        (root / "a" / "b").mkdir(parents=True)
        (root / "top.txt").write_text("top")
        (root / "a" / "b" / "deep.bin").write_bytes(b"1" * 1024)
        target = self.d / "keep_target"
        target.mkdir()
        (target / "safe.txt").write_text("safe")
        windows.create_junction(str(root / "a" / "linked"), str(target))
        report = windows.clear_tree_keep_structure(str(root))
        self.assertTrue(report.ok, report.errors)
        self.assertTrue((root / "a" / "b").is_dir())
        self.assertTrue((root / "a" / "linked").is_dir())
        self.assertEqual(list((root / "a" / "b").iterdir()), [])
        self.assertTrue((target / "safe.txt").exists())

    def test_can_delete_regular_dir(self):
        plain = self.d / "plain"
        plain.mkdir()
        deletable, why = windows.can_delete(str(plain))
        self.assertTrue(deletable, why)

    def test_remove_link_reports_blocking_handle(self):
        target = self.d / "lock_target"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        link = self.d / "lock_link"
        ok, err = windows.create_junction(str(link), str(target))
        self.assertTrue(ok, err)

        kernel32, handle = base.lock_dir(str(link))
        try:
            deletable, why = windows.can_delete(str(link))
            self.assertFalse(deletable)
            self.assertIn("占用", why)

            ok2, why2 = windows.remove_link_ex(str(link), attempts=1)
            self.assertFalse(ok2)
            self.assertTrue(why2)
            self.assertTrue(windows.is_junction(str(link)))
        finally:
            base.unlock_dir(kernel32, handle)

        ok3, why3 = windows.remove_link_ex(str(link))
        self.assertTrue(ok3, why3)
        self.assertFalse(os.path.lexists(str(link)))
        self.assertTrue((target / "keep.txt").exists())

    def test_remove_link_clears_readonly(self):
        """带只读属性的 junction 必须先清属性才能删（WinError 5 的来源）。"""
        target = self.d / "ro_target"
        target.mkdir()
        (target / "keep.txt").write_text("keep")
        link = self.d / "ro_link"
        ok, err = windows.create_junction(str(link), str(target))
        self.assertTrue(ok, err)
        self.assertTrue(base.set_link_readonly(str(link)))
        self.assertTrue(os.lstat(str(link)).st_file_attributes & 0x1)

        ok2, why2 = windows.remove_link_ex(str(link), attempts=1)
        self.assertTrue(ok2, why2)
        self.assertFalse(os.path.lexists(str(link)))
        self.assertTrue((target / "keep.txt").exists())

    def test_retarget_junction_in_place(self):
        """改指应该就地改写重解析点，只读的链接也能改。"""
        first = self.d / "rt_first"
        second = self.d / "rt_second"
        for path, name in ((first, "a.txt"), (second, "b.txt")):
            path.mkdir()
            (path / name).write_text(name)
        link = self.d / "rt_link"
        ok, err = windows.create_junction(str(link), str(first))
        self.assertTrue(ok, err)
        self.assertTrue(base.set_link_readonly(str(link)))

        ok2, why2 = windows.retarget_junction(str(link), str(second))
        self.assertTrue(ok2, why2)
        self.assertEqual(os.path.normcase(windows.junction_target(str(link))),
                         os.path.normcase(str(second)))
        self.assertTrue((link / "b.txt").exists())
        self.assertTrue((first / "a.txt").exists())

    def test_delete_entry_clears_readonly_file(self):
        target = self.d / "ro_file.txt"
        target.write_text("x")
        os.chmod(target, stat.S_IREAD)
        ok, why = windows.delete_entry(str(target))
        self.assertTrue(ok, why)
        self.assertFalse(target.exists())

    def test_restart_manager_detects_lock(self):
        target = self.d / "locked"
        target.mkdir()
        file = target / "locked.txt"
        file.write_text("x" * 100)
        code = (
            "import time;"
            f"f=open(r'{file}','r+');f.write('y');print('ready',flush=True);"
            "time.sleep(6)"
        )
        proc = subprocess.Popen([sys.executable, "-c", code],
                                stdout=subprocess.PIPE, text=True)
        try:
            proc.stdout.readline()
            time.sleep(0.4)
            rows = windows.processes_using(str(target))
            self.assertTrue(any(int(r.get("pid", 0)) == proc.pid for r in rows),
                            rows)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            try:
                proc.stdout.close()
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
