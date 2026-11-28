from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests import base  # noqa: E402  (设置 CDC_DATA_DIR)
from PySide6.QtCore import QItemSelectionModel, Qt  # noqa: E402
from PySide6.QtGui import QColor, QPalette  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QListView  # noqa: E402

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

    def test_confirm_dialog_supports_multiple_options(self):
        """归档确认框要能同时提供「压缩 / 校验 / 删除原目录」三个勾选项。"""
        from cdc.ui.widgets import ConfirmDialog
        dialog = ConfirmDialog(None, "归档 1 个目录？", "移动归档",
                               options=["压缩成 zip", "归档后校验", "删除原目录"],
                               options_checked=[True, False, True])
        try:
            self.assertEqual(len(dialog.option_checks), 3)
            self.assertEqual([c.isChecked() for c in dialog.option_checks],
                             [True, False, True])
        finally:
            dialog.close()

    def _wait_list_rows(self, dialog) -> tuple:
        """等 QFileSystemModel 异步加载完当前目录，返回 (view, model)。"""
        import time

        view = dialog.findChild(QListView, "listView")
        self.assertIsNotNone(view, "找不到主列表视图")
        model = view.model()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            self.app.processEvents()
            root = view.rootIndex()
            if root.isValid() and model.rowCount(root) > 0:
                break
            time.sleep(0.02)
        return view, model

    def test_dir_dialog_lists_dirs_and_accepts(self):
        """还原 2.3.3 的 QFileDialog 选择器：列出目录、可多选、确认返回选中的目录。"""
        tree_root, _extra = base.temp_tree("picker_old")
        for name in ("alpha", "beta", "gamma"):
            (tree_root / name).mkdir()

        state = AppState()
        window = MainWindow(state)
        window.show()
        self.app.processEvents()
        dialog = window.pages["archive"]._dir_dialog(str(tree_root))
        try:
            dialog.show()
            view, model = self._wait_list_rows(dialog)
            root = view.rootIndex()
            names = [model.index(row, 0, root).data()
                     for row in range(model.rowCount(root))]
            for want in ("alpha", "beta", "gamma"):
                self.assertIn(want, names)
            self.assertEqual(dialog.windowTitle(), "选择要归档的目录（可多选）")

            selection = view.selectionModel()
            flags = (QItemSelectionModel.SelectionFlag.Select
                     | QItemSelectionModel.SelectionFlag.Rows)
            for row in range(model.rowCount(root)):
                index = model.index(row, 0, root)
                if index.data() in ("alpha", "beta"):
                    selection.select(index, flags)
            dialog.accept()
            self.assertEqual(len(dialog.picked), 2)
            picked = {os.path.normcase(os.path.normpath(path)) for path in dialog.picked}
            self.assertIn(os.path.normcase(os.path.normpath(str(tree_root / "alpha"))), picked)
            self.assertIn(os.path.normcase(os.path.normpath(str(tree_root / "beta"))), picked)
        finally:
            dialog.close()
            window.close()
            state.shutdown()
            base.cleanup(tree_root)

    def test_dir_dialog_can_enter_junction(self):
        """回归：QFileSystemModel 把 Junction 的子项算成 0；双击必须仍能进入。"""
        tree_root, _extra = base.temp_tree("picker_junction")
        target = tree_root / "target"
        (target / "inner").mkdir(parents=True)
        ok, err = windows.create_junction(str(tree_root / "linked"), str(target))
        self.assertTrue(ok, err)

        state = AppState()
        window = MainWindow(state)
        window.show()
        self.app.processEvents()
        dialog = window.pages["archive"]._dir_dialog(str(tree_root))
        try:
            dialog.show()
            view, model = self._wait_list_rows(dialog)
            root = view.rootIndex()
            linked = None
            for row in range(model.rowCount(root)):
                index = model.index(row, 0, root)
                if index.data() == "linked":
                    linked = index
                    break
            self.assertIsNotNone(linked, "列表里看不到 Junction")
            # Qt 的已知缺陷：Junction 在模型里子项为 0
            self.assertEqual(model.rowCount(linked), 0)

            view.scrollTo(linked)
            self.app.processEvents()
            QTest.mouseDClick(view.viewport(), Qt.LeftButton, Qt.NoModifier,
                              view.visualRect(linked).center())
            for _ in range(40):
                self.app.processEvents()
            self.assertEqual(os.path.normcase(dialog.directory().absolutePath()),
                             os.path.normcase(str(tree_root / "linked")))
            root = view.rootIndex()
            inner = [model.index(row, 0, root).data()
                     for row in range(model.rowCount(root))]
            self.assertIn("inner", inner)
        finally:
            dialog.close()
            window.close()
            state.shutdown()
            base.cleanup(tree_root)



if __name__ == "__main__":
    unittest.main()
