"""自绘的目录树选择器（可多选，替代 QFileDialog）。

为什么不用 QFileDialog：
- 非原生 QFileDialog 在「目录模式 + 多选」下，确认按钮会变成导航；
- 遇到 Junction / 隐藏目录 / 无权限目录时，列表可能直接空掉或不可进入；
- 我们还需要标注 Junction、显示隐藏目录、以及把「当前目录」本身加进来。

这里用 QTreeWidget + os.scandir 自己枚举，行为完全可控：
展开时才列子目录，权限错误给一行提示，确认按钮只做「收下选中项」。
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core import windows

HIDDEN = 0x2


def _iter_dirs(path: str):
    """列出一级子目录，返回 (名称, 完整路径, 是否链接, 是否隐藏)。"""
    rows = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    attrs = entry.stat(follow_symlinks=False).st_file_attributes
                    rows.append((entry.name, entry.path, entry.is_junction(),
                                 bool(attrs & HIDDEN)))
                except OSError:
                    continue
    except OSError:
        return []
    rows.sort(key=lambda row: (row[0].casefold()))
    return rows


class DirPickerDialog(QDialog):
    """目录树多选对话框：勾选目录 → 确定 → 结果在 ``picked``。"""

    def __init__(self, parent: QWidget | None = None, start: str = "",
                 title: str = "选择要归档的目录（可多选）") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.picked: list[str] = []
        self._current = ""
        self.resize(760, 580)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(9)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.up = QPushButton("上一级")
        self.up.setObjectName("Ghost")
        self.up.clicked.connect(self._go_up)
        bar.addWidget(self.up)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"输入路径后回车，例如 C:\Users\你\.lmstudio")
        self.path_edit.returnPressed.connect(self._go_path)
        bar.addWidget(self.path_edit, 1)
        self.go = QPushButton("转到")
        self.go.setObjectName("Ghost")
        self.go.clicked.connect(self._go_path)
        bar.addWidget(self.go)
        layout.addLayout(bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setAnimated(False)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree.itemChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.tree, 1)

        hint = QLabel(
            "勾选要归档的目录（可多选）；双击展开。Junction 会标「→」，隐藏目录显示为灰色。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        footer = QHBoxLayout()
        footer.addWidget(QLabel(""), 1)
        self.btn_current = QPushButton("添加当前目录")
        self.btn_current.setObjectName("Ghost")
        self.btn_current.clicked.connect(self._add_current)
        footer.addWidget(self.btn_current)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton("添加选中")
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.setMinimumWidth(120)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._accept)
        footer.addWidget(self.btn_ok)
        layout.addLayout(footer)

        start_dir = start if start and os.path.isdir(start) else os.environ.get(
            "USERPROFILE", "C:\\")
        self.set_current(start_dir)

    # ---------- 导航 ----------

    def set_current(self, path: str) -> None:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            path = os.path.dirname(path) or "C:\\"
        self._current = path
        self.path_edit.setText(path)
        self.tree.clear()
        self._fill(None, path)
        self._update_buttons()

    def _fill(self, parent: QTreeWidgetItem | None, path: str) -> None:
        rows = _iter_dirs(path)
        container = self.tree.invisibleRootItem() if parent is None else parent
        if not rows:
            text = "(这个目录没有子目录)" if parent is None else "(没有子目录)"
            placeholder = QTreeWidgetItem([text])
            placeholder.setFlags(Qt.ItemIsEnabled)
            container.addChild(placeholder)
            return
        for name, full, is_link, hidden in rows:
            label = name + ("  →" if is_link else "")
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.UserRole, full)
            item.setData(0, Qt.UserRole + 1, 0)  # 0 = 子项尚未展开
            tip = full
            if is_link:
                target = windows.junction_target(full)
                tip = f"{full}\n链接目标：{target}（可展开浏览）"
            item.setToolTip(0, tip)
            if hidden:
                item.setForeground(0, self.palette().mid())
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            dummy = QTreeWidgetItem([""])
            dummy.setFlags(Qt.ItemIsEnabled)
            item.addChild(dummy)  # 占位，保证有展开箭头
            container.addChild(item)

    def _on_expanded(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, Qt.UserRole)
        if not path or item.data(0, Qt.UserRole + 1):
            return
        item.setData(0, Qt.UserRole + 1, 1)
        item.takeChildren()
        self._fill(item, path)

    def _on_double_clicked(self, item: QTreeWidgetItem) -> None:
        path = item.data(0, Qt.UserRole)
        if path:
            item.setExpanded(not item.isExpanded())

    def _go_up(self) -> None:
        parent = os.path.dirname(self._current.rstrip("\\/")) or "C:\\"
        self.set_current(parent)

    def _go_path(self) -> None:
        text = self.path_edit.text().strip().strip('"')
        if text:
            self.set_current(text)

    # ---------- 选择 ----------

    def _checked(self) -> list[str]:
        rows: list[str] = []
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            path = item.data(0, Qt.UserRole)
            if path and item.checkState(0) == Qt.CheckState.Checked:
                rows.append(path)
            stack.extend(item.child(i) for i in range(item.childCount()))
        return rows

    def _update_buttons(self) -> None:
        count = len(self._checked())
        self.btn_ok.setText(f"添加选中（{count}）" if count else "添加选中")
        self.btn_ok.setEnabled(True)

    def _add_current(self) -> None:
        self.picked = [self._current]
        self.accept()

    def _accept(self) -> None:
        rows = self._checked()
        if not rows:
            # 没勾选时，退而求其次：有高亮项就用高亮项
            item = self.tree.currentItem()
            path = item.data(0, Qt.UserRole) if item is not None else ""
            if path and os.path.isdir(path):
                rows = [path]
        if not rows:
            return
        self.picked = rows
        self.accept()
