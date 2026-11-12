from __future__ import annotations

import unittest
from unittest import mock

from tests import base  # noqa: F401
from cdc.core import updater


def fake_release(version="2.2.0"):
    return {
        "tag_name": f"v{version}",
        "name": f"CDriveCleaner v{version}",
        "body": "release notes",
        "html_url": "https://example.invalid/release",
        "published_at": "2026-11-12T00:00:00Z",
        "assets": [
            {"name": f"CDriveCleaner-Setup-v{version}.exe",
             "browser_download_url": "https://example.invalid/setup.exe",
             "size": 100, "digest": "sha256:" + "a" * 64},
            {"name": f"CDriveCleaner-Portable-v{version}.zip",
             "browser_download_url": "https://example.invalid/portable.zip",
             "size": 200, "digest": "sha256:" + "b" * 64},
        ],
    }


class UpdaterTests(unittest.TestCase):
    def test_version_compare(self):
        self.assertTrue(updater.is_newer("v2.2.0", "2.1.0"))
        self.assertTrue(updater.is_newer("2.1.1", "2.1.0"))
        self.assertFalse(updater.is_newer("v2.1.0", "2.1.0"))
        self.assertFalse(updater.is_newer("v2.0.9", "2.1.0"))

    def test_asset_selection(self):
        with mock.patch.object(updater.paths, "is_source_checkout", return_value=False):
            installed = updater.parse_release(fake_release(), "2.1.0", portable=False)
            portable = updater.parse_release(fake_release(), "2.1.0", portable=True)
        self.assertTrue(installed.installable)
        self.assertTrue(installed.asset().name.endswith(".exe"))
        self.assertTrue(portable.installable)
        self.assertTrue(portable.asset().name.endswith(".zip"))

    def test_no_update_for_same_version(self):
        self.assertIsNone(updater.parse_release(fake_release("2.1.0"), "2.1.0"))

    def test_digest_value(self):
        self.assertEqual(updater._digest_value("sha256:" + "A" * 64), "a" * 64)


if __name__ == "__main__":
    unittest.main()
