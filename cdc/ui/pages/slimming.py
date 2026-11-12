"""C 盘瘦身页：扫描、筛选、批量 Junction 迁移。"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ...core.models import (
    ACTION_MIGRATE, MODE_MOVE, OperationItem, ScanItem, human_bytes,
)
from .. import theme
from ..widgets import (
    Check, ConfirmDialog, ElidedLabel, EmptyState, GlassCard, IconButton,
    IconTile, PageHeader, Pill, SearchField, UsageBar, clear_layout, label,
)
from .base import (
    card_header, fmt_size, fmt_time, ghost_button, note_frame, open_path,
    primary_button,
)


class ScanRow(QFrame):
    toggled = Signal(str, bool)
    migrate = Signal(object)
    open_requested = Signal(str)

    def __init__(self, item: ScanItem, max_size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.setObjectName("Row")
        self.setProperty("selected", False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 12, 10)
        layout.setSpacing(11)

        self.check = Check()
        self.check.toggled.connect(self._on_check)
        layout.addWidget(self.check, alignment=Qt.AlignVCenter)

        icon_name = {
            "userhome": "home", "programs": "package", "local": "folder",
            "roaming": "refresh", "localLow": "layers",
            "programdata": "database", "programfiles": "briefcase",
        }.get(item.zone_key, "folder")
        layout.addWidget(IconTile(icon_name, "brand", 36, 17), alignment=Qt.AlignTop)

        center = QVBoxLayout()
        center.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(7)
        name = QLabel(item.name)
        name.setStyleSheet(f"color:{theme.TEXT};font-size:13px;font-weight:600;")
        top.addWidget(name)
        top.addWidget(Pill(item.zone_label, "muted"))
        if item.needs_admin:
            top.addWidget(Pill("需管理员", "amber"))
        if item.protected:
            top.addWidget(Pill("受保护", "rose"))
        top.addStretch()
        center.addLayout(top)
        path = ElidedLabel(item.path, "MonoMuted")
        center.addWidget(path)
        bar_row = QHBoxLayout()
        bar_row.setSpacing(8)
        bar = UsageBar(item.size_bytes / max(1, max_size), "brand", 5)
        bar.setMaximumWidth(210)
        bar_row.addWidget(bar)
        count = label(f"{item.file_count:,} 个文件", "Dim")
        bar_row.addWidget(count)
        bar_row.addStretch()
        center.addLayout(bar_row)
        layout.addLayout(center, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        size = QLabel(fmt_size(item.size_bytes))
        size.setStyleSheet(
            f"color:{theme.TEXT};font-family:'JetBrains Mono';font-size:14px;font-weight:700;"
        )
        size.setAlignment(Qt.AlignRight)
        right.addWidget(size)
        hint = label("可释放", "Dim")
        hint.setAlignment(Qt.AlignRight)
        right.addWidget(hint)
        layout.addLayout(right)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        open_btn = IconButton("external", "打开目录")
        open_btn.clicked.connect(lambda: self.open_requested.emit(item.path))
        actions.addWidget(open_btn)
        self.btn = QPushButton("需管理员" if item.needs_admin else "迁移")
        self.btn.setObjectName("RowWarn" if item.needs_admin else "RowAction")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.migrate.emit(item))
        actions.addWidget(self.btn)
        layout.addLayout(actions)

    def _on_check(self, checked: bool) -> None:
        self.setProperty("selected", checked)
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.emit(self.item.path, checked)

    def set_checked(self, checked: bool) -> None:
        self.check.setChecked(checked)


class SlimmingPage(QWidget):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.selected: dict[str, ScanItem] = {}
        self._rows: list[ScanRow] = []
        self._all_items: list[ScanItem] = []
        self._build()
        state.scan_started.connect(self._on_scan_started)
        state.scan_progress.connect(self._on_scan_progress)
        state.scan_finished.connect(self._on_scan_finished)
        state.scan_failed.connect(self._on_scan_failed)

    # ---------- 构建 ----------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll = scroll
        inner = QWidget()
        inner.setObjectName("PageRoot")
        content = QVBoxLayout(inner)
        content.setContentsMargins(30, 22, 30, 24)
        content.setSpacing(16)

        self.btn_scan = primary_button("扫描 C 盘", "refresh")
        self.btn_scan.clicked.connect(self._scan)
        content.addWidget(PageHeader(
            "C 盘瘦身",
            "把大目录搬到其他盘，用 Junction 让原路径继续可用。",
            [self.btn_scan],
        ))

        # 工具栏
        toolbar = GlassCard(14, 10, "CardSoft")
        self.toolbar = toolbar
        row = QHBoxLayout()
        row.setSpacing(9)
        self.btn_rescan = ghost_button("重新扫描", "refresh")
        self.btn_rescan.clicked.connect(self._scan)
        row.addWidget(self.btn_rescan)
        self.scan_state = label("尚未扫描", "Muted")
        row.addWidget(self.scan_state)
        self.scan_bar = QProgressBar()
        self.scan_bar.setRange(0, 100)
        self.scan_bar.setValue(0)
        self.scan_bar.setFixedWidth(170)
        self.scan_bar.setFixedHeight(6)
        self.scan_bar.hide()
        row.addWidget(self.scan_bar)
        self.btn_cancel_scan = QPushButton("取消")
        self.btn_cancel_scan.setObjectName("Link")
        self.btn_cancel_scan.setCursor(Qt.PointingHandCursor)
        self.btn_cancel_scan.clicked.connect(self.state.cancel_scan)
        self.btn_cancel_scan.hide()
        row.addWidget(self.btn_cancel_scan)
        row.addStretch()

        self.threshold = QComboBox()
        for mb in (50, 100, 250, 500, 1024):
            self.threshold.addItem(f"≥ {mb} MB" if mb < 1024 else "≥ 1 GB", mb)
        idx = self.threshold.findData(self.state.config.threshold_mb)
        self.threshold.setCurrentIndex(max(0, idx))
        self.threshold.currentIndexChanged.connect(self._on_threshold)
        row.addWidget(self.threshold)

        self.zone_filter = QComboBox()
        self.zone_filter.addItem("全部区域", "")
        self.zone_filter.currentIndexChanged.connect(lambda _i: self._render())
        row.addWidget(self.zone_filter)

        self.search = SearchField("搜索目录名或路径…")
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(lambda _t: self._render())
        row.addWidget(self.search)
        self.check_all = Check("全选")
        self.check_all.toggled.connect(self._on_check_all)
        row.addWidget(self.check_all)
        toolbar.add_layout(row)
        content.addWidget(toolbar)

        # 摘要
        self.summary = QFrame()
        self.summary.setObjectName("CardInset")
        summary_layout = QHBoxLayout(self.summary)
        summary_layout.setContentsMargins(14, 9, 14, 9)
        summary_layout.setSpacing(14)
        self.summary_items = label("0 个可迁移目录", "Body")
        self.summary_size = label("预计释放 0 B", "MonoMuted")
        self.summary_links = label("", "MonoMuted")
        summary_layout.addWidget(self.summary_items)
        summary_layout.addWidget(self.summary_size)
        summary_layout.addStretch()
        summary_layout.addWidget(self.summary_links)
        self.summary.hide()
        content.addWidget(self.summary)

        # 结果列表
        self.list_card = GlassCard(12, 8, "Card")
        self.list_head = card_header("可迁移目录", "按体积从大到小")
        self.list_card.add(self.list_head)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        self.list_card.add_layout(self.rows_box)
        self.empty = EmptyState(
            "sparkles", "先扫描一次 C 盘",
            "找出超过阈值的目录，迁移后原路径不变，随时可以撤销。",
            ghost_button("开始扫描", "refresh"),
        )
        self.empty.action_widget.clicked.connect(self._scan)
        self.list_card.add(self.empty)
        content.addWidget(self.list_card)

        # 受保护目录
        self.protected_card = GlassCard(14, 8, "CardSoft")
        prot_head = QHBoxLayout()
        prot_head.addWidget(label("受保护目录", "CardTitle"))
        prot_head.addWidget(label("系统/工具自动排除，不会迁移", "Muted"))
        prot_head.addStretch()
        self.btn_protected = QPushButton("展开")
        self.btn_protected.setObjectName("Link")
        self.btn_protected.setCursor(Qt.PointingHandCursor)
        self.btn_protected.clicked.connect(self._toggle_protected)
        prot_head.addWidget(self.btn_protected)
        self.protected_card.add_layout(prot_head)
        self.protected_box = QVBoxLayout()
        self.protected_box.setSpacing(5)
        self.protected_card.add_layout(self.protected_box)
        self.protected_card.hide()
        content.addWidget(self.protected_card)

        # 已迁移提示
        self.links_card = GlassCard(14, 8, "CardSoft")
        links_row = QHBoxLayout()
        links_row.addWidget(IconTile("link", "teal", 34, 16))
        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.links_title = label("已迁移目录", "Body")
        self.links_title.setStyleSheet(f"color:{theme.TEXT};font-weight:600;")
        self.links_hint = label("—", "Muted")
        text_box.addWidget(self.links_title)
        text_box.addWidget(self.links_hint)
        links_row.addLayout(text_box)
        links_row.addStretch()
        go_links = ghost_button("链接管理", "arrow-right")
        go_links.clicked.connect(lambda: self.state.navigate.emit("links"))
        links_row.addWidget(go_links)
        self.links_card.add_layout(links_row)
        self.links_card.hide()
        content.addWidget(self.links_card)

        # 原理与安全
        how = GlassCard(18, 12, "CardSoft")
        how.add(card_header("迁移原理", "为什么原路径还能继续用"))
        steps = QHBoxLayout()
        steps.setSpacing(12)
        for num, title, text, icon_name in [
            ("01", "复制", "用 robocopy 把目录完整复制到迁移容器。", "copy"),
            ("02", "校验", "逐文件比对路径、大小与数量，不一致绝不删源。", "shield"),
            ("03", "链接", "删除原目录并建立 Junction，应用无感知。", "link"),
        ]:
            box = QFrame()
            box.setObjectName("CardInset")
            b = QVBoxLayout(box)
            b.setContentsMargins(14, 12, 14, 12)
            b.setSpacing(5)
            top = QHBoxLayout()
            top.setSpacing(8)
            top.addWidget(IconTile(icon_name, "brand", 30, 15))
            top.addWidget(label(num, "MonoMuted"))
            top.addWidget(label(title, "Body"))
            top.addStretch()
            b.addLayout(top)
            hint = label(text, "Muted", wrap=True)
            b.addWidget(hint)
            steps.addWidget(box, 1)
        how.add_layout(steps)
        how.add(note_frame(
            "C 与 D 若在同一块物理盘，迁移只改变分区占用，不增加物理盘总容量；"
            "真正的增量空间来自机械盘归档。", "warn", "alert"))
        content.addWidget(how)

        content.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # 批量操作栏
        self.batch = QFrame()
        self.batch.setObjectName("BatchBar")
        self.batch.setFixedHeight(64)
        batch_layout = QHBoxLayout(self.batch)
        batch_layout.setContentsMargins(22, 10, 22, 10)
        batch_layout.setSpacing(12)
        batch_layout.addWidget(IconTile("sparkles", "brand", 34, 16))
        self.batch_text = label("已选 0 项", "Body")
        self.batch_text.setStyleSheet(f"color:{theme.TEXT};font-weight:600;")
        self.batch_size = label("", "MonoMuted")
        batch_layout.addWidget(self.batch_text)
        batch_layout.addWidget(self.batch_size)
        batch_layout.addStretch()
        clear = ghost_button("清除选择")
        clear.clicked.connect(self._clear_selection)
        batch_layout.addWidget(clear)
        self.btn_migrate_selected = primary_button("迁移所选", "arrow-right")
        self.btn_migrate_selected.clicked.connect(self._migrate_selected)
        batch_layout.addWidget(self.btn_migrate_selected)
        self.batch.hide()
        outer.addWidget(self.batch)
        self.batch.setStyleSheet(
            f"QFrame#BatchBar {{ background:rgba(9,14,24,0.97); "
            f"border-top:1px solid {theme.BORDER_HI}; }}"
        )
        self.refresh()

    # ---------- 扫描 ----------

    def _scan(self) -> None:
        self.selected.clear()
        self.state.start_scan()

    def _on_scan_started(self) -> None:
        self.btn_scan.setEnabled(False)
        self.btn_rescan.setEnabled(False)
        self.scan_bar.show()
        self.scan_bar.setValue(0)
        self.btn_cancel_scan.show()
        self.scan_state.setText("正在扫描…")

    def _on_scan_progress(self, progress: Any) -> None:
        self.scan_bar.setValue(int(progress.percent))
        self.scan_state.setText(progress.message or progress.phase)

    def _on_scan_finished(self, result: Any) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_rescan.setEnabled(True)
        self.scan_bar.hide()
        self.btn_cancel_scan.hide()
        self.scan_state.setText(f"上次扫描 {fmt_time(result.scanned_at)} · {result.duration_s:.1f}s")
        self._populate_zones()
        self.refresh()

    def _on_scan_failed(self, error: str) -> None:
        self.btn_scan.setEnabled(True)
        self.btn_rescan.setEnabled(True)
        self.scan_bar.hide()
        self.btn_cancel_scan.hide()
        self.scan_state.setText(f"扫描失败：{error}")
        self.state.toast.emit(f"扫描失败：{error}", "error")

    def _populate_zones(self) -> None:
        current = self.zone_filter.currentData()
        self.zone_filter.blockSignals(True)
        self.zone_filter.clear()
        self.zone_filter.addItem("全部区域", "")
        seen = set()
        for item in self.state.scan.items:
            if item.zone_key not in seen:
                seen.add(item.zone_key)
                self.zone_filter.addItem(item.zone_label, item.zone_key)
        idx = self.zone_filter.findData(current)
        self.zone_filter.setCurrentIndex(max(0, idx))
        self.zone_filter.blockSignals(False)

    # ---------- 渲染 ----------

    def refresh(self) -> None:
        scan = self.state.scan
        self._all_items = list(scan.items)
        if scan.scanned_at:
            self.scan_state.setText(f"上次扫描 {fmt_time(scan.scanned_at)} · {scan.duration_s:.1f}s")
        self._render()
        self._render_protected()
        # 链接提示
        if scan.junctions:
            self.links_card.show()
            self.links_title.setText(f"已迁移 {len(scan.junctions)} 个目录")
            self.links_hint.setText(
                f"目标占用 {human_bytes(scan.released_bytes)} · "
                f"{'有链接目标缺失' if any(j.broken for j in scan.junctions) else '全部正常'}"
            )
        else:
            self.links_card.hide()
        self._update_batch()

    def _filtered(self) -> list[ScanItem]:
        text = self.search.text().strip().lower()
        zone = self.zone_filter.currentData()
        rows = []
        for item in self._all_items:
            if item.protected:
                continue
            if zone and item.zone_key != zone:
                continue
            if text and text not in item.name.lower() and text not in item.path.lower():
                continue
            rows.append(item)
        return rows

    def _clear_rows(self) -> None:
        clear_layout(self.rows_box)
        self._rows = []

    def _render(self) -> None:
        self._clear_rows()
        items = self._filtered()
        if not items:
            self.empty.show()
            self.list_card.show()
            self.summary.hide()
            self._update_summary(len(items))
            return
        self.empty.hide()
        max_size = max(i.size_bytes for i in items)
        for item in items:
            row = ScanRow(item, max_size)
            row.toggled.connect(self._on_row_toggled)
            row.migrate.connect(self._migrate_one)
            row.open_requested.connect(open_path)
            if item.path in self.selected:
                row.set_checked(True)
            self.rows_box.addWidget(row)
            self._rows.append(row)
        self.summary.show()
        self._update_summary(len(items))

    def _update_summary(self, count: int) -> None:
        scan = self.state.scan
        self.summary_items.setText(f"{count} 个可迁移目录")
        total = sum(i.size_bytes for i in self._filtered())
        self.summary_size.setText(f"预计释放 {human_bytes(total)}")
        if scan.junctions:
            self.summary_links.setText(
                f"已迁移 {len(scan.junctions)} 项 · 释放 {human_bytes(scan.released_bytes)}")
        else:
            self.summary_links.setText("")

    def _render_protected(self) -> None:
        clear_layout(self.protected_box)
        items = self.state.scan.protected_items
        if not items:
            self.protected_card.hide()
            return
        self.protected_card.show()
        for item in items[:20]:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(2, 3, 2, 3)
            layout.setSpacing(9)
            layout.addWidget(Pill(item.zone_label, "muted"))
            name = QLabel(item.name)
            name.setStyleSheet(f"color:{theme.TEXT_2};font-size:11px;")
            layout.addWidget(name)
            layout.addStretch()
            size = QLabel(fmt_size(item.size_bytes) if item.size_bytes else "—")
            size.setStyleSheet(f"color:{theme.DIM};font-family:'JetBrains Mono';font-size:10px;")
            layout.addWidget(size)
            self.protected_box.addWidget(row)

    def _toggle_protected(self) -> None:
        visible = self.protected_box.itemAt(0).widget().isVisible() if self.protected_box.count() else False
        for i in range(self.protected_box.count()):
            w = self.protected_box.itemAt(i).widget()
            if w:
                w.setVisible(not visible)
        self.btn_protected.setText("收起" if not visible else "展开")

    # ---------- 选择 ----------

    def _on_row_toggled(self, path: str, checked: bool) -> None:
        item = next((i for i in self._all_items if i.path == path), None)
        if checked and item:
            self.selected[path] = item
        else:
            self.selected.pop(path, None)
        self._update_batch()

    def _on_check_all(self, checked: bool) -> None:
        for row in self._rows:
            row.set_checked(checked)
        if not checked:
            self.selected.clear()
            self._update_batch()

    def _update_batch(self) -> None:
        count = len(self.selected)
        self.batch.setVisible(count > 0)
        if count:
            total = sum(i.size_bytes for i in self.selected.values())
            self.batch_text.setText(f"已选 {count} 项")
            self.batch_size.setText(f"共 {human_bytes(total)}")

    def _clear_selection(self) -> None:
        self.selected.clear()
        for row in self._rows:
            row.set_checked(False)
        self.check_all.setChecked(False)
        self._update_batch()

    def _on_threshold(self, _index: int | None = None) -> None:
        mb = int(self.threshold.currentData() or 100)
        if mb == self.state.config.threshold_mb:
            return
        self.state.config.threshold_mb = mb
        try:
            self.state.config.save()
        except Exception:
            pass
        if self.state.scan.scanned_at:
            self.state.start_scan()

    # ---------- 迁移 ----------

    def _make_items(self, items: list[ScanItem]) -> list[OperationItem]:
        rows = []
        for item in items:
            rows.append(OperationItem(
                action=ACTION_MIGRATE,
                source=item.path,
                dest=item.dest_path,
                name=item.name,
                size_bytes=item.size_bytes,
                file_count=item.file_count,
                zone_key=item.zone_key,
                needs_admin=item.needs_admin,
                mode=MODE_MOVE,
            ))
        return rows

    def _migrate_one(self, item: ScanItem) -> None:
        self._confirm_and_run([item])

    def _migrate_selected(self) -> None:
        self._confirm_and_run(list(self.selected.values()))

    def _confirm_and_run(self, items: list[ScanItem]) -> None:
        if not items:
            return
        total = sum(i.size_bytes for i in items)
        admin = any(i.needs_admin for i in items)
        names = "\n".join(f"· {i.name}  {fmt_size(i.size_bytes)}" for i in items[:6])
        if len(items) > 6:
            names += f"\n… 另有 {len(items) - 6} 项"
        ok = ConfirmDialog.ask(
            self.window(),
            f"迁移 {len(items)} 个目录？" if len(items) > 1 else f"迁移「{items[0].name}」？",
            f"复制到迁移容器后建立 Junction，原路径保持不变。预计释放 {human_bytes(total)}。",
            "开始迁移",
            tone="brand",
            details=names + f"\n\n目标根路径：{self.state.config.link_root}",
            note=("需要管理员权限：会先弹出 UAC，输入管理员凭据后整批执行。"
                  if admin else "迁移前请关闭相关应用；链接创建失败会自动回拷数据。"),
            note_tone="warn" if admin else "success",
            require_check=len(items) > 1 or admin,
            icon_name="sparkles",
        )
        if not ok:
            return
        if self.state.start_operation(self._make_items(items)):
            self._clear_selection()
