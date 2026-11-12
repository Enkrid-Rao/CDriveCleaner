from __future__ import annotations

import os
import unittest

from tests import base
from cdc.core import jobs, windows
from cdc.core.models import ACTION_ARCHIVE, MODE_COPY, OperationItem


class JobTests(unittest.TestCase):
    def setUp(self):
        self.d, self.e = base.temp_tree("jobs")

    def tearDown(self):
        base.cleanup(self.d, self.e)

    def test_elevated_job_protocol(self):
        src = self.d / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello" * 500)
        dest = self.e / "dest"
        files = jobs.create_job([
            OperationItem(action=ACTION_ARCHIVE, source=str(src), dest=str(dest),
                          name="job", mode=MODE_COPY,
                          size_bytes=windows.directory_size(str(src)))
        ], action=ACTION_ARCHIVE)
        code = jobs.run_elevated_job(files.job)
        self.assertEqual(code, 0)
        result = jobs.read_result(files)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "success")
        self.assertTrue((dest / "a.txt").exists())
        self.assertTrue(src.exists())
        progress = jobs.read_progress(files)
        self.assertEqual(progress["percent"], 100.0)


if __name__ == "__main__":
    unittest.main()
