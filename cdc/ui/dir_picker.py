"""自绘的目录选择器（可多选，替代 QFileDialog）。

为什么不用 QFileDialog：
- 非原生 QFileDialog 在「目录模式 + 多选」下，确认按钮会变成导航；
- 遇到 Junction / 隐藏目录 / 无权限目录时，列表可能直接空掉或不可进入；
- 我们还需要标注 Junction、显示隐藏目录、以及把「当前目录」本身加进来。

界面分三块：左侧「快速访问 + 磁盘」、右侧路径栏 + 目录树、底部操作区。
展开时才列子目录，权限错误不影响其它项，确认按钮只做「收下选中项」。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..core import windows
from . import icons, theme
from .widgets import IconTile, add_shadow, label

HIDDEN = 0x2
_LAST_DIR = ""

NAV_STYLE = f"""
QPushButton {{
    text-align: left;
    padding: 7px 10px;
    border: 1px solid transparent;
    border-radius: 9px;
    background: transparent;
    color: {theme.TEXT};
    font-size: 13px;
}}
QPushButton:hover {{
    background: {theme.SURFACE_HOVER};
    border-color: {theme.BORDER};
}}
QPushButton:pressed {{
    background: {theme.BORDER};
}}
"""


def _check_image_url() -> str:
    """生成/复用勾选状态的白色对勾图标，供 QSS 使用。"""
    try:
        base = Path(tempfile.gettempdir()) / "CDriveCleaner"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "check-indicator.png"
        if not path.exists():
            icons.icon_pixmap("check", "#FFFFFF", 12).save(str(path), "PNG")
        return str(path).replace("\\", "/")
    except OSError:
        return ""


def last_dir() -> str:
    """上一次选择器停留/确认过的目录（没有则空串）。"""
    return _LAST_DIR


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


def _nav_button(parent: QWidget, icon_name: str, text: str,
                tooltip: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(NAV_STYLE)
    btn.setIcon(QIcon(icons.icon_pixmap(icon_name, theme.MUT, 16)))
    btn.setIconSize(QSize(16, 16))
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setParent(parent)
    return btn


class _DirTree(QTreeWidget):
    """目录树：补齐文件管理器里习惯的键盘 / 修饰键选择。"""

    def __init__(self, dialog: "DirPickerDialog") -> None:
        super().__init__()
        self._dialog = dialog

    def keyPressEvent(self, event) -> None:  # noqa: N802
        mods = event.modifiers()
        if mods & Qt.ControlModifier and event.key() == Qt.Key_A:
            if mods & Qt.ShiftModifier:
                self._dialog.clear_all_checks()
            else:
                self._dialog.check_all_visible()
            event.accept()
            return
        if event.key() == Qt.Key_Space:
            item = self.currentItem()
            if item is not None and item.data(0, Qt.UserRole):
                self._dialog.toggle_item(item)
                event.accept()
                return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint()
            item = self.itemAt(pos)
            mods = event.modifiers()
            if item is not None and item.data(0, Qt.UserRole):
                if mods & Qt.ShiftModifier:
                    self._dialog.check_range(item)
                    event.accept()
                    return
                if mods & Qt.ControlModifier:
                    self._dialog.toggle_item(item)
                    event.accept()
                    return
                self._dialog._anchor = item
        super().mousePressEvent(event)


class DirPickerDialog(QDialog):
    """目录树多选对话框：勾选目录 → 确定 → 结果在 ``picked``。"""

    def __init__(self, parent: QWidget | None = None, start: str = "",
                 title: str = "选择要归档的目录（可多选）",
                 subtitle: str = "勾选目录后点右下角「添加选中」；双击展开，Junction 会标 →。",
                 quick: list[tuple[str, str, str]] | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.picked: list[str] = []
        self._selected: dict[str, str] = {}   # normcase(path) -> 原始 path，跨目录保留
        self._current = ""
        self._quick = list(quick or [])
        self._filling = False
        self._anchor = None
        self.resize(960, 660)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        card = QFrame()
        card.setObjectName("DialogInner")
        card.setStyleSheet(
            f"QFrame#DialogInner {{ background:{theme.SURFACE}; "
            f"border:1px solid {theme.BORDER_HI}; border-radius:18px; }}"
        )
        add_shadow(card, 40, 14, 80)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        # ---------- 标题 ----------
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(IconTile("folder", "teal", 44, 21), alignment=Qt.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"color:{theme.TEXT};font-size:18px;font-weight:700;")
        text_box.addWidget(title_label)
        text_box.addWidget(label(subtitle, "Muted", wrap=True))
        head.addLayout(text_box, 1)
        layout.addLayout(head)

        # ---------- 主体 ----------
        body = QHBoxLayout()
        body.setSpacing(14)
        body.addWidget(self._build_sidebar(), 0)

        right = QVBoxLayout()
        right.setSpacing(9)
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_up = QPushButton("上一级")
        self.btn_up.setObjectName("Ghost")
        self.btn_up.setCursor(Qt.PointingHandCursor)
        self.btn_up.clicked.connect(self._go_up)
        bar.addWidget(self.btn_up)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"输入路径后回车，例如 D:\Projects")
        self.path_edit.returnPressed.connect(self._go_path)
        bar.addWidget(self.path_edit, 1)
        self.btn_go = QPushButton("转到")
        self.btn_go.setObjectName("Ghost")
        self.btn_go.setCursor(Qt.PointingHandCursor)
        self.btn_go.clicked.connect(self._go_path)
        bar.addWidget(self.btn_go)
        right.addLayout(bar)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.btn_all = QPushButton("全选")
        self.btn_all.setObjectName("Link")
        self.btn_all.setCursor(Qt.PointingHandCursor)
        self.btn_all.setToolTip("勾选当前列表里的全部目录（Ctrl+A）")
        self.btn_all.clicked.connect(self.check_all_visible)
        self.btn_invert = QPushButton("反选")
        self.btn_invert.setObjectName("Link")
        self.btn_invert.setCursor(Qt.PointingHandCursor)
        self.btn_invert.setToolTip("把当前列表的勾选状态反过来")
        self.btn_invert.clicked.connect(self.invert_visible)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("Link")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setToolTip("清空所有已勾选目录（Ctrl+Shift+A）")
        self.btn_clear.clicked.connect(self.clear_all_checks)
        for btn in (self.btn_all, self.btn_invert, self.btn_clear):
            tools.addWidget(btn)
        tools.addStretch()
        tools.addWidget(label("Ctrl+A 全选 · Shift 连选 · 空格勾选", "Dim"))
        right.addLayout(tools)

        self.tree = _DirTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setIndentation(18)
        self.tree.setIconSize(QSize(18, 18))
        check_url = _check_image_url()
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {theme.INPUT};
                border: 1px solid {theme.BORDER};
                border-radius: 12px;
                padding: 6px;
                outline: 0;
                font-size: 13px;
            }}
            QTreeView::indicator, QTreeWidget::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {theme.BORDER_STRONG};
                border-radius: 4px;
                background: {theme.INPUT};
            }}
            QTreeView::indicator:checked, QTreeWidget::indicator:checked {{
                background: {theme.BRAND};
                border-color: {theme.BRAND};
                image: url("{check_url}");
            }}
            QTreeView::indicator:hover, QTreeWidget::indicator:hover {{
                border-color: {theme.BRAND};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme.BORDER_HI};
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {theme.BORDER_STRONG}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QTreeWidget::item {{
                height: 32px;
                border-radius: 8px;
                padding-left: 2px;
                color: {theme.TEXT};
            }}
            QTreeWidget::item:hover {{ background: {theme.SURFACE_HOVER}; }}
            QTreeWidget::item:selected {{
                background: {theme.SURFACE_HOVER};
                color: {theme.TEXT};
            }}
        """)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemDoubleClicked.connect(self._on_double_clicked)
        self.tree.itemChanged.connect(self._on_item_changed)
        right.addWidget(self.tree, 1)

        hint = label("勾选目录（可多选，切换目录后已勾选的不会丢）；双击展开一级。"
                     "Junction 标 →，隐藏目录灰色显示。",
                     "Muted", wrap=True)
        right.addWidget(hint)
        body.addLayout(right, 1)
        layout.addLayout(body, 1)

        # ---------- 底部 ----------
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.btn_current = QPushButton("添加当前目录")
        self.btn_current.setObjectName("Ghost")
        self.btn_current.setCursor(Qt.PointingHandCursor)
        self.btn_current.clicked.connect(self._add_current)
        footer.addWidget(self.btn_current)
        footer.addStretch()
        self.selected_label = label("已选 0 项", "Muted")
        footer.addWidget(self.selected_label)
        footer.addSpacing(6)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)
        self.btn_ok = QPushButton("添加选中")
        self.btn_ok.setObjectName("Primary")
        self.btn_ok.setMinimumWidth(132)
        self.btn_ok.setCursor(Qt.PointingHandCursor)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._accept)
        footer.addWidget(self.btn_ok)
        layout.addLayout(footer)

        start_dir = start if start and os.path.isdir(start) else (last_dir() or os.environ.get(
            "USERPROFILE", "C:\\"))
        self.set_current(start_dir)

    # ---------- 侧栏 ----------

    def _build_sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("CardInset")
        side.setFixedWidth(206)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(3)

        title = QLabel("快速访问")
        title.setStyleSheet(
            f"color:{theme.DIM};font-size:11px;font-weight:700;letter-spacing:1px;")
        layout.addWidget(title)
        layout.addSpacing(2)

        home = os.path.expanduser("~")
        seen: set[str] = set()

        def add_nav(icon_name: str, text: str, path: str, tip: str = "") -> None:
            key = os.path.normcase(os.path.abspath(path))
            if key in seen or not os.path.isdir(path):
                return
            seen.add(key)
            btn = _nav_button(side, icon_name, text, tip or path)
            btn.clicked.connect(lambda _=False, p=path: self.set_current(p))
            layout.addWidget(btn)

        add_nav("user", "用户目录", home)
        for name in ("Desktop", "Downloads", "Documents"):
            add_nav("folder", {"Desktop": "桌面", "Downloads": "下载",
                               "Documents": "文档"}[name],
                    os.path.join(home, name))
        for icon_name, text, path in self._quick:
            add_nav(icon_name, text, path)

        layout.addSpacing(10)
        drives_title = QLabel("磁盘")
        drives_title.setStyleSheet(
            f"color:{theme.DIM};font-size:11px;font-weight:700;letter-spacing:1px;")
        layout.addWidget(drives_title)
        layout.addSpacing(2)

        try:
            drives = windows.list_drives()
        except Exception:  # noqa: BLE001
            drives = []
        for drive in drives:
            if not os.path.isdir(drive.root):
                continue
            try:
                free = windows.free_bytes(drive.root)
            except OSError:
                free = drive.free_bytes
            tip = (f"{drive.root}  可用 {free / 1024 ** 3:.1f} GB"
                   f" / {drive.total_bytes / 1024 ** 3:.1f} GB"
                   + (f"\n{drive.label}" if drive.label else ""))
            btn = _nav_button(side, "drive", f"{drive.letter}:  "
                                            f"{drive.label or drive.media_type}", tip)
            btn.clicked.connect(lambda _=False, p=drive.root: self.set_current(p))
            layout.addWidget(btn)
        layout.addStretch()
        return side

    # ---------- 导航 ----------

    def set_current(self, path: str) -> None:
        global _LAST_DIR
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            path = os.path.dirname(path) or "C:\\"
        self._current = path
        _LAST_DIR = path
        self.path_edit.setText(path)
        self.tree.clear()
        self._fill(None, path)
        self._update_buttons()

    def _fill(self, parent: QTreeWidgetItem | None, path: str) -> None:
        rows = _iter_dirs(path)
        container = self.tree.invisibleRootItem() if parent is None else parent
        if not rows:
            text = "（这个目录没有子目录）" if parent is None else "（没有子目录）"
            placeholder = QTreeWidgetItem([text])
            placeholder.setFlags(Qt.ItemIsEnabled)
            placeholder.setForeground(0, QColor(theme.DIM))
            container.addChild(placeholder)
            return
        folder_icon = QIcon(icons.icon_pixmap("folder", theme.DIM, 18))
        link_icon = QIcon(icons.icon_pixmap("link", theme.CYAN, 18))
        self._filling = True
        for name, full, is_link, hidden in rows:
            label_text = name + ("   →" if is_link else "")
            item = QTreeWidgetItem([label_text])
            item.setData(0, Qt.UserRole, full)
            item.setData(0, Qt.UserRole + 1, 0)  # 0 = 子项尚未展开
            item.setIcon(0, link_icon if is_link else folder_icon)
            tip = full
            if is_link:
                target = windows.junction_target(full)
                tip = f"{full}\n链接目标：{target}（可展开浏览）"
            item.setToolTip(0, tip)
            if hidden:
                item.setForeground(0, QColor(theme.DIM))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            checked = os.path.normcase(os.path.abspath(full)) in self._selected
            item.setCheckState(0, Qt.CheckState.Checked if checked
                              else Qt.CheckState.Unchecked)
            dummy = QTreeWidgetItem([""])
            dummy.setFlags(Qt.ItemIsEnabled)
            item.addChild(dummy)  # 占位，保证有展开箭头
            container.addChild(item)
        self._filling = False

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

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if self._filling:
            return
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self._selected[self._key(path)] = path
        else:
            self._selected.pop(self._key(path), None)
        self._update_buttons()

    def _set_checked(self, item: QTreeWidgetItem, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        if item.checkState(0) == state:
            return
        if self._filling:
            item.setCheckState(0, state)
            return
        item.setCheckState(0, state)

    def toggle_item(self, item: QTreeWidgetItem) -> None:
        """空格 / Ctrl+点击：切换单个目录的勾选。"""
        checking = item.checkState(0) != Qt.CheckState.Checked
        self._set_checked(item, checking)
        self._anchor = item

    def _visible_items(self) -> list[QTreeWidgetItem]:
        items: list[QTreeWidgetItem] = []

        def walk(parent: QTreeWidgetItem) -> None:
            for index in range(parent.childCount()):
                child = parent.child(index)
                if child.data(0, Qt.UserRole):
                    items.append(child)
                walk(child)

        walk(self.tree.invisibleRootItem())
        return items

    def check_all_visible(self) -> None:
        """Ctrl+A / 全选：勾选当前列表里所有已加载的目录。"""
        for item in self._visible_items():
            self._set_checked(item, True)
        self._update_buttons()

    def clear_all_checks(self) -> None:
        """Ctrl+Shift+A / 清空：清空全部已勾选目录（含其它目录里勾的）。"""
        self._selected.clear()
        for item in self._visible_items():
            self._set_checked(item, False)
        self._update_buttons()

    def invert_visible(self) -> None:
        for item in self._visible_items():
            self._set_checked(item, item.checkState(0) != Qt.CheckState.Checked)
        self._update_buttons()

    def check_range(self, item: QTreeWidgetItem) -> None:
        """Shift+点击：从上一个点击项连选到这一项。"""
        items = self._visible_items()
        anchor = self._anchor if self._anchor in items else None
        if anchor is None:
            self.toggle_item(item)
            return
        start = items.index(anchor)
        end = items.index(item)
        lo, hi = (start, end) if start <= end else (end, start)
        for row in items[lo:hi + 1]:
            self._set_checked(row, True)
        self._anchor = item
        self._update_buttons()

    def _checked(self) -> list[str]:
        return list(self._selected.values())

    def _update_buttons(self) -> None:
        count = len(self._selected)
        self.btn_ok.setText(f"添加选中（{count}）" if count else "添加选中")
        self.btn_ok.setEnabled(True)
        self.selected_label.setText(f"已选 {count} 项" if count else "已选 0 项")
        self.btn_clear.setEnabled(count > 0)

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
