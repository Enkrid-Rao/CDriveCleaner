from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import base  # noqa: E402  (设置 CDC_DATA_DIR)
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cdc.app import ensure_fonts  # noqa: E402
from cdc.core.models import LAYOUT_FLAT, LAYOUT_MIRROR, ArchiveCandidate  # noqa: E402
from cdc.ui import theme  # noqa: E402
from cdc.ui.state import AppState  # noqa: E402
from cdc.core import windows  # noqa: E402
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

    def test_archive_dest_follows_layout(self):
        state = AppState()
        window = MainWindow(state)
        page = window.pages["archive"]
        try:
            cand = ArchiveCandidate(name="Downloads", path=r"C:\Users\raoxi\Downloads",
                                    size_bytes=1, file_count=0,
                                    newest_ts=0.0, oldest_ts=0.0)
            page.layout_pick.set_value(LAYOUT_MIRROR)
            mirror = page._dest_for(cand)
            self.assertTrue(mirror.endswith(r"C\Users\raoxi\Downloads"), mirror)
            page.layout_pick.set_value(LAYOUT_FLAT)
            flat = page._dest_for(cand)
            self.assertTrue(flat.endswith("Downloads"), flat)
            self.assertNotEqual(os.path.normcase(mirror), os.path.normcase(flat))
        finally:
            window.close()
            state.shutdown()

    def test_dark_system_still_renders_light(self):
        """系统深色模式下也必须拿到浅底 + 深字（曾经导致目录选择框黑底黑字）。"""
        dark = QPalette(QColor("#1e1e1e"))
        dark.setColor(QPalette.ColorRole.Base, QColor("#2d2d2d"))
        dark.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
        dark.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        self.app.setPalette(dark)
        try:
            theme.apply_app_theme(self.app)
            palette = self.app.palette()
            self.assertGreater(palette.window().color().lightness(), 200)
            self.assertGreater(palette.base().color().lightness(), 200)
            self.assertLess(palette.text().color().lightness(), 80)
        finally:
            theme.apply_app_theme(self.app)

    def test_dir_picker_lists_hidden_and_junction_dirs(self):
        """回归：选择器进入 Junction / 隐藏目录时必须能列出子目录。"""
        tree_root, _extra = base.temp_tree("picker")
        (tree_root / ".hidden_dir" / "sub").mkdir(parents=True)
        (tree_root / "plain").mkdir()
        target = tree_root / "target"
        (target / "inner").mkdir(parents=True)
        ok, err = windows.create_junction(str(tree_root / "linked"), str(target))
        self.assertTrue(ok, err)

        state = AppState()
        self.app.setStyleSheet(theme.build_qss(13, False))
        window = MainWindow(state)
        window.show()
        self.app.processEvents()
        dialog = window.pages["archive"]._dir_dialog(str(tree_root))
        try:
            tree = dialog.tree
            names = [tree.topLevelItem(i).text(0).replace("  →", "")
                     for i in range(tree.topLevelItemCount())]
            self.assertIn(".hidden_dir", names)
            self.assertIn("plain", names)
            self.assertIn("linked", names)
            self.assertEqual(dialog.btn_ok.text(), "添加选中")
            self.assertEqual(dialog.btn_ok.objectName(), "Primary")

            linked = next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount())
                          if tree.topLevelItem(i).text(0).startswith("linked"))
            linked.setExpanded(True)
            self.app.processEvents()
            inner = [linked.child(i).text(0) for i in range(linked.childCount())]
            self.assertIn("inner", inner)

            linked.setCheckState(0, Qt.CheckState.Checked)
            self.app.processEvents()
            dialog._accept()
            self.assertEqual(dialog.picked, [str(tree_root / "linked")])
        finally:
            dialog.close()
            window.close()
            state.shutdown()
            base.cleanup(tree_root)


if __name__ == "__main__":
    unittest.main()
