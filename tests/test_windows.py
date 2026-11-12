from __future__ import annotations

import os
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
