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

    def test_routes_prefer_remembered_proxy_for_download(self):
        with mock.patch.object(updater, "load_state",
                               return_value={"download_proxy": "http://127.0.0.1:7899"}), \
                mock.patch.object(updater, "_env_proxy", return_value=""):
            routes = updater._routes(download=True)
        names = [name for name, _opener in routes]
        self.assertEqual(names[0], "http://127.0.0.1:7899")
        self.assertEqual(names[-1], "direct")
        self.assertEqual(len(names), len(set(names)))

    def test_check_routes_start_direct(self):
        with mock.patch.object(updater, "load_state", return_value={}), \
                mock.patch.object(updater, "_env_proxy", return_value=""):
            routes = updater._routes(download=False)
        self.assertEqual(routes[0][0], "direct")

    def test_download_asset_from_local_server(self):
        import hashlib
        import http.server
        import tempfile
        import threading
        from pathlib import Path

        payload = b"hello-cdc" * 2000
        digest = hashlib.sha256(payload).hexdigest()

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            asset = updater.UpdateAsset(
                name="setup.exe",
                url=f"http://127.0.0.1:{server.server_port}/setup.exe",
                size=len(payload), digest=digest)
            dest = Path(tempfile.mkdtemp(prefix="cdc_dl_"))
            with mock.patch.object(updater, "_routes",
                                   return_value=[("direct", updater._direct_opener())]):
                path = updater.download_asset(asset, dest)
            self.assertEqual(Path(path).read_bytes(), payload)
        finally:
            server.shutdown()
            server.server_close()

    def test_download_requires_digest(self):
        import tempfile

        asset = updater.UpdateAsset(name="x.exe", url="http://127.0.0.1:1/x.exe",
                                    size=0, digest="")
        with self.assertRaises(RuntimeError):
            updater.download_asset(asset, tempfile.mkdtemp(prefix="cdc_dl_"))


if __name__ == "__main__":
    unittest.main()
