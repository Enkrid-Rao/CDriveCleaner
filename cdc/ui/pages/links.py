"""链接管理页：查看所有 Junction，撤销迁移、移除死链。"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ...core.models import (
    ACTION_UNDO, ACTION_UNLINK, JunctionInfo, OperationItem, human_bytes,
)
from .. import theme
from ..widgets import (
    ConfirmDialog, ElidedLabel, EmptyState, GlassCard, IconButton, IconTile,
    PageHeader, Pill, SearchField, ScrollPage, StatTile, clear_layout, label,
)
from .base import (
    card_header, fmt_size, fmt_time, ghost_button, note_frame, open_path,
    primary_button,
)


class LinkRow(QFrame):
    undo = Signal(object)
    unlink = Signal(object)
    open_requested = Signal(str)

    def __init__(self, info: JunctionInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info
        self.setObjectName("Row")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 12, 10)
        layout.setSpacing(11)
        layout.addWidget(IconTile("link", "teal" if not info.broken else "rose", 36, 17),
                         alignment=Qt.AlignTop)
        center = QVBoxLayout()
        center.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(7)
        name = QLabel(info.name)
        name.setStyleSheet(f"color:{theme.TEXT};font-size:13px;font-weight:600;")
        top.addWidget(name)
        top.addWidget(Pill(info.zone_label or "其他", "muted"))
        if info.broken:
            top.addWidget(Pill("目标缺失", "rose"))
        elif info.target_on_usb:
            top.addWidget(Pill("外置盘", "amber"))
        else:
            top.addWidget(Pill("正常", "green"))
        if not info.mine:
            top.addWidget(Pill("手工创建", "muted"))
        top.addStretch()
        center.addLayout(top)
        source = ElidedLabel(f"{info.path}", "MonoMuted")
        center.addWidget(source)
        target = ElidedLabel(f"→  {info.target or '（无法读取目标）'}", "Mono")
        target.setStyleSheet(
            f"color:{theme.TEAL if not info.broken else theme.RED};font-size:10px;"
        )
        center.addWidget(target)
        layout.addLayout(center, 1)

        right = QVBoxLayout()
        right.setSpacing(3)
        size = QLabel(fmt_size(info.size_bytes) if info.size_bytes else "—")
        size.setStyleSheet(
            f"color:{theme.TEXT};font-family:'JetBrains Mono';font-size:13px;font-weight:700;"
        )
        size.setAlignment(Qt.AlignRight)
        right.addWidget(size)
        files = label(f"{info.file_count:,} 文件" if info.file_count else "大小未统计", "Dim")
        files.setAlignment(Qt.AlignRight)
        right.addWidget(files)
        layout.addLayout(right)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        open_btn = IconButton("external", "打开位置")
        open_btn.clicked.connect(lambda: self.open_requested.emit(
            info.path if os.path.exists(info.path) else os.path.dirname(info.path)))
        actions.addWidget(open_btn)
        if info.broken:
            dead = QPushButton("移除死链")
            dead.setObjectName("RowDanger")
            dead.setCursor(Qt.PointingHandCursor)
            dead.clicked.connect(lambda: self.unlink.emit(info))
            actions.addWidget(dead)
        else:
            undo_btn = QPushButton("撤销迁移")
            undo_btn.setObjectName("RowAction")
            undo_btn.setCursor(Qt.PointingHandCursor)
            undo_btn.clicked.connect(lambda: self.undo.emit(info))
            actions.addWidget(undo_btn)
        layout.addLayout(actions)


class LinksPage(ScrollPage):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent, margins=(30, 22, 30, 30), spacing=16)
        self.state = state
        self._rows: list[LinkRow] = []
        self._all: list[JunctionInfo] = []
        self._build()
        state.scan_finished.connect(self.refresh)
        state.drives_changed.connect(lambda _d: self.refresh())
        state.history_changed.connect(self.refresh)

    def _build(self) -> None:
        self.btn_scan = primary_button("扫描链接", "refresh")
        self.btn_scan.clicked.connect(self.state.start_scan)
        self.add(PageHeader(
            "链接管理",
            "所有由 Junction 接管的目录。撤销会把数据回迁，并删除链接。",
            [self.btn_scan],
        ))
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_total = StatTile("link", "链接总数", "—", "", "teal")
        self.stat_size = StatTile("drive", "目标占用", "—", "", "purple")
        self.stat_broken = StatTile("alert", "目标缺失", "—", "", "rose")
        self.stat_usb = StatTile("server", "外置盘目标", "—", "", "amber")
        for tile in (self.stat_total, self.stat_size, self.stat_broken, self.stat_usb):
            stats.addWidget(tile, 1)
        self.add_layout(stats)

        card = GlassCard(16, 12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(9)
        self.search = SearchField("搜索链接名或路径…")
        self.search.textChanged.connect(lambda _t: self._render())
        toolbar.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItem("全部链接", "all")
        self.filter.addItem("正常", "ok")
        self.filter.addItem("目标缺失", "broken")
        self.filter.addItem("外置盘目标", "usb")
        self.filter.currentIndexChanged.connect(lambda _i: self._render())
        toolbar.addWidget(self.filter)
        self.btn_open_root = ghost_button("打开迁移容器", "external")
        self.btn_open_root.clicked.connect(
            lambda: open_path(self.state.config.link_root))
        toolbar.addWidget(self.btn_open_root)
        card.add_layout(toolbar)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        card.add_layout(self.rows_box)
        self.empty = EmptyState(
            "link", "还没有目录链接",
            "先在「C 盘瘦身」中迁移一个目录，或点击扫描读取现有 Junction。",
            primary_button("扫描 C 盘", "refresh"),
        )
        self.empty.action_widget.clicked.connect(self.state.start_scan)
        card.add(self.empty)
        self.add(card)
        self.add(note_frame(
            "Junction 是 NTFS 目录链接：删除链接本身不会删除目标数据。"
            "撤销迁移会先把数据回迁到 C 盘并校验，成功后才删除迁移副本。",
            "info", "info"))
        self.add_stretch()
        self.refresh()

    def refresh(self) -> None:
        scan = self.state.scan
        self._all = list(scan.junctions)
        total_size = sum(j.size_bytes for j in self._all)
        broken = sum(1 for j in self._all if j.broken)
        usb = sum(1 for j in self._all if j.target_on_usb)
        self.stat_total.set_value(str(len(self._all)),
                                  f"上次扫描 {fmt_time(scan.scanned_at)}" if scan.scanned_at else "尚未扫描")
        self.stat_size.set_value(human_bytes(total_size), "C 盘已释放")
        self.stat_broken.set_value(str(broken), "需要清理或修复")
        self.stat_usb.set_value(str(usb), "拔盘后路径不可用")
        self._render()

    def _render(self) -> None:
        clear_layout(self.rows_box)
        self._rows = []
        text = self.search.text().strip().lower()
        mode = self.filter.currentData()
        rows = []
        for info in self._all:
            if mode == "ok" and info.broken:
                continue
            if mode == "broken" and not info.broken:
                continue
            if mode == "usb" and not info.target_on_usb:
                continue
            if text and text not in info.name.lower() and text not in info.path.lower() \
                    and text not in (info.target or "").lower():
                continue
            rows.append(info)
        if not rows:
            self.empty.show()
            return
        self.empty.hide()
        for info in rows:
            row = LinkRow(info)
            row.undo.connect(self._undo)
            row.unlink.connect(self._unlink)
            row.open_requested.connect(open_path)
            self.rows_box.addWidget(row)
            self._rows.append(row)

    def _undo(self, info: JunctionInfo) -> None:
        ok = ConfirmDialog.ask(
            self.window(),
            f"撤销「{info.name}」的迁移？",
            f"数据会从 {info.target} 回迁到 C 盘原路径，然后删除链接与迁移副本。",
            "开始回迁",
            tone="amber",
            details=(f"原路径：{info.path}\n目标：{info.target}\n"
                     f"大小：{fmt_size(info.size_bytes)}"),
            note=("C 盘可用空间必须大于该目录体积。回迁校验失败会自动恢复链接。"),
            note_tone="warn",
            require_check=True,
            icon_name="undo",
        )
        if not ok:
            return
        item = OperationItem(
            action=ACTION_UNDO, source=info.path, dest=info.target,
            name=info.name, size_bytes=info.size_bytes, file_count=info.file_count,
            needs_admin=info.needs_admin, extra={"delete_target": True},
        )
        self.state.start_operation([item])

    def _unlink(self, info: JunctionInfo) -> None:
        ok = ConfirmDialog.ask(
            self.window(),
            f"移除失效链接「{info.name}」？",
            "只会删除链接本体，不会触碰任何目标数据。",
            "移除链接",
            tone="rose",
            details=f"链接：{info.path}\n目标（不存在）：{info.target}",
            note="移除后该路径消失；如果目标盘只是暂时未连接，请先接上磁盘再操作。",
            note_tone="danger",
            require_check=True,
            icon_name="x",
        )
        if not ok:
            return
        item = OperationItem(action=ACTION_UNLINK, source=info.path,
                             dest=info.target, name=info.name,
                             needs_admin=info.needs_admin)
        self.state.start_operation([item])
