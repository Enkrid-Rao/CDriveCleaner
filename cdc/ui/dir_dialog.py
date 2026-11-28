"""目录选择器：沿用 2.3.3 的 QFileDialog 界面，只修「Junction 进不去」的问题。

2.3.3 用的是非原生 QFileDialog（ShowDirsOnly + ExistingFiles 凑多选），
用户喜欢这个界面与操作方式，所以这里保留它，只做两件事：

1. 重写 ``accept()``：确认时直接把选中的目录收进 ``picked``，而不是进入目录；
2. 修 QFileSystemModel 对 Junction 的缺陷：Junction 在列表里可见，
   但模型把它的子项当成 0 个，双击会「进不去」（这正是 2.3.4 重写 UI 的起因）。
   这里拦截双击 / 回车，遇到这种目录就用 ``setDirectory`` 直接切过去。
"""

from __future__ import annotations

import os

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QListView,
    QTreeView, QWidget,
)


class _JunctionNavigator(QObject):
    """让 QFileDialog 能进入 Junction（模型里子项为 0 的目录）。"""

    def __init__(self, dialog: "DirPickerDialog") -> None:
        super().__init__(dialog)
        self._dialog = dialog

    @staticmethod
    def _view_for(obj):
        """viewport 的事件对象 → 对应的视图控件。"""
        if hasattr(obj, "indexAt"):
            return obj
        parent = obj.parent() if hasattr(obj, "parent") else None
        return parent if parent is not None and hasattr(parent, "indexAt") else None

    def _path_from_index(self, view, index) -> str:
        """把视图里的 index 还原成真实路径（支持详情列表与树视图）。"""
        parts: list[str] = []
        root = view.rootIndex()
        current = index
        while current.isValid() and current != root:
            name = current.data()
            if isinstance(name, str) and name:
                parts.append(name)
            parent = current.parent()
            if parent == current:
                break
            current = parent
        if not parts:
            return ""
        base = self._dialog.directory().absolutePath()
        return os.path.join(base, *reversed(parts))

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        kind = event.type()
        if kind not in (QEvent.Type.MouseButtonDblClick, QEvent.Type.KeyPress):
            return False
        view = self._view_for(obj)
        if view is None:
            return False
        path = ""
        index = None
        if kind == QEvent.Type.MouseButtonDblClick:
            try:
                pos = event.position().toPoint()
            except AttributeError:
                pos = event.pos()
            index = view.indexAt(pos)
            if index.isValid():
                candidate = self._path_from_index(view, index)
                if candidate and os.path.isdir(candidate):
                    path = candidate
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            path = self._dialog._current_selected_dir()
        if not path:
            return False
        # 正常目录（模型里有子项）交给 QFileDialog；Junction 模型子项为 0，手动切换
        if index is not None and view.model() is not None and \
                view.model().rowCount(index) > 0:
            return False
        try:
            has_dirs = any(entry.is_dir(follow_symlinks=False)
                           for entry in os.scandir(path))
        except OSError:
            return False
        if not has_dirs:
            return False
        self._dialog.setDirectory(path)
        return True


class DirPickerDialog(QFileDialog):
    """可多选目录的 QFileDialog（外观与 2.3.3 一致）。"""

    def __init__(self, parent: QWidget | None, title: str,
                 start: str = "") -> None:
        super().__init__(parent, title)
        self.picked: list[str] = []
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setOption(QFileDialog.Option.ShowDirsOnly, True)
        self.setFileMode(QFileDialog.FileMode.ExistingFiles)
        if start:
            self.setDirectory(start)

        navigator = _JunctionNavigator(self)
        for view in self._views():
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            view.setToolTip("Ctrl / Shift + 单击可多选目录；双击进入目录")
            view.viewport().installEventFilter(navigator)
            view.installEventFilter(navigator)

        self._relabel()
        self._cheap_theme_fixes()

    # ---------- 内部 ----------

    def _views(self) -> list:
        views = list(self.findChildren(QListView)) + list(self.findChildren(QTreeView))
        # 侧栏与路径补全的列表不参与
        return [view for view in views if view.objectName() in ("listView", "treeView")]

    def _current_selected_dir(self) -> str:
        for path in self.selectedFiles():
            if os.path.isdir(path):
                return path
        return ""

    def _relabel(self) -> None:
        self.setLabelText(QFileDialog.DialogLabel.LookIn, "当前位置")
        self.setLabelText(QFileDialog.DialogLabel.FileName, "目录")
        self.setLabelText(QFileDialog.DialogLabel.FileType, "类型")
        self.setLabelText(QFileDialog.DialogLabel.Reject, "取消")
        for name in ("fileTypeLabel", "fileTypeCombo"):
            widget = self.findChild(QWidget, name)
            if widget is not None:
                widget.hide()

        box = self.findChild(QDialogButtonBox, "buttonBox")
        accept = None
        if box is not None:
            for button in box.buttons():
                if box.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
                    accept = button
                    break
        if accept is not None:
            accept.setObjectName("Primary")
            accept.setMinimumWidth(108)
            accept.style().unpolish(accept)
            accept.style().polish(accept)

            def relabel(*_args) -> None:
                # Qt 每次选择变化都会把按钮文字改回 "&Open"
                if accept.text() != "添加选中":
                    accept.setText("添加选中")

            self.directoryEntered.connect(relabel)
            for view in self._views():
                selection = view.selectionModel()
                if selection is not None:
                    selection.selectionChanged.connect(relabel)
                    selection.currentChanged.connect(relabel)
            relabel()

    def _cheap_theme_fixes(self) -> None:
        # 侧栏最宽条目决定最小宽度，避免 "My Computer" 被省略成 "My Com…"
        sidebar = self.findChild(QListView, "sidebar")
        if sidebar is not None and sidebar.model() is not None:
            model = sidebar.model()
            metrics = sidebar.fontMetrics()
            widest = max(
                (metrics.horizontalAdvance(model.index(row, 0).data(Qt.ItemDataRole.DisplayRole) or "")
                 for row in range(model.rowCount())),
                default=0,
            )
            if widest:
                sidebar.setMinimumWidth(widest + 56)

    # ---------- 确认 ----------

    def accept(self) -> None:  # noqa: N802
        paths = [path for path in self.selectedFiles() if os.path.isdir(path)]
        if not paths:
            return  # 什么都没选：保持打开，等用户选择或取消
        self.picked = paths
        QDialog.accept(self)  # 跳过 QFileDialog 的「进入目录」逻辑
