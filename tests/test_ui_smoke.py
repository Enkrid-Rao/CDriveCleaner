from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import base  # noqa: E402,F401  (设置 CDC_DATA_DIR)
from PySide6.QtWidgets import QApplication  # noqa: E402

from cdc.app import ensure_fonts  # noqa: E402
from cdc.ui import theme  # noqa: E402
from cdc.ui.state import AppState  # noqa: E402
from cdc.ui.window import MainWindow  # noqa: E402


class UISmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        ensure_fonts()

    def test_main_window_pages(self):
        state = AppState()
        self.app.setStyleSheet(theme.build_qss(13, False))
        window = MainWindow(state)
        window.resize(1280, 820)
        window.show()
        self.app.processEvents()
        expected = {"dashboard", "slimming", "archive", "links", "history", "settings"}
        self.assertEqual(set(window.pages), expected)
        for key in expected:
            window.navigate(key, refresh=True)
            self.app.processEvents()
            self.assertIs(window.stack.currentWidget(), window.pages[key])
        window.close()
        state.shutdown()


if __name__ == "__main__":
    unittest.main()
