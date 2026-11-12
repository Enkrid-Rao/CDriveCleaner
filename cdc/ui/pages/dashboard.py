"""总览页：C 盘健康度、三盘布局、建议与最近操作。"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ... import paths
from ...core import windows
from ...core.models import (
    ACTION_CLEAN, TIER_RECOMMEND, TIER_STRONG, OperationItem, human_bytes,
)
from .. import theme
from ..widgets import (
    ConfirmDialog, DriveCard, EmptyState, Gauge, GlassCard, IconButton, IconTile,
    PageHeader, Pill, ScrollPage, StatTile, UsageBar, clear_layout, label,
)
from .base import (
    ACTION_ICONS, action_icon_button, card_header, fmt_size, fmt_time, ghost_button,
    note_frame, open_path, primary_button, status_pill,
)


class DashboardPage(ScrollPage):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent, margins=(30, 22, 30, 30), spacing=18)
        self.state = state
        self._build()
        state.drives_changed.connect(self._on_drives)
        state.scan_finished.connect(lambda _r: self.refresh())
        state.scan_progress.connect(self._on_scan_progress)
        state.analysis_finished.connect(lambda _r: self.refresh())
        state.history_changed.connect(self.refresh)
        state.operation_busy.connect(self._on_busy)

    # ---------- 构建 ----------

    def _build(self) -> None:
        self.btn_scan = primary_button("开始扫描", "refresh")
        self.btn_scan.clicked.connect(self._scan)
        self.btn_archive = ghost_button("冷数据归档", "archive")
        self.btn_archive.clicked.connect(lambda: self.state.navigate.emit("archive"))
        self.header = PageHeader(
            "总览",
            "看清每一块盘的空间，再决定搬什么、搬到哪。",
            [self.btn_archive, self.btn_scan],
        )
        self.add(self.header)

        # Hero
        hero = QFrame()
        hero.setObjectName("Hero")
        hero.setMinimumHeight(192)
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(28, 22, 22, 22)
        hl.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(7)
        top = QHBoxLayout()
        top.setSpacing(9)
        self.health_pill = Pill("空间健康", "green")
        top.addWidget(self.health_pill)
        top.addWidget(label("系统盘 C:", "Mono"))
        top.addStretch()
        left.addLayout(top)

        free_row = QHBoxLayout()
        free_row.setSpacing(8)
        free_row.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.hero_free = QLabel("—")
        self.hero_free.setStyleSheet(
            f"color:{theme.TEXT};font-family:'Cascadia Mono';"
            "font-size:38px;font-weight:800;"
        )
        unit = QLabel("GB")
        unit.setStyleSheet(
            f"color:{theme.MUT};font-size:13px;font-weight:600;margin-bottom:8px;"
        )
        unit2 = QLabel("可用")
        unit2.setStyleSheet(f"color:{theme.MUT};font-size:12px;margin-bottom:9px;")
        free_row.addWidget(self.hero_free)
        free_row.addWidget(unit)
        free_row.addSpacing(3)
        free_row.addWidget(unit2)
        left.addLayout(free_row)
        self.hero_used = label("—", "Muted")
        left.addWidget(self.hero_used)
        self.hero_bar = UsageBar(0, "c", 7)
        self.hero_bar.setMaximumWidth(420)
        left.addWidget(self.hero_bar)
        left.addSpacing(4)
        actions = QHBoxLayout()
        actions.setSpacing(9)
        self.btn_hero_scan = primary_button("扫描 C 盘", "search")
        self.btn_hero_scan.clicked.connect(self._scan)
        self.btn_hero_archive = ghost_button("分析冷数据", "archive")
        self.btn_hero_archive.clicked.connect(lambda: self.state.navigate.emit("archive"))
        actions.addWidget(self.btn_hero_scan)
        actions.addWidget(self.btn_hero_archive)
        actions.addStretch()
        left.addLayout(actions)
        hl.addLayout(left, 1)

        self.gauge = Gauge(174, "c")
        hl.addWidget(self.gauge, alignment=Qt.AlignRight | Qt.AlignVCenter)
        self.add(hero)

        # 统计卡
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_potential = StatTile("sparkles", "可迁移", "—", "", "brand")
        self.stat_released = StatTile("link", "已迁移", "—", "", "purple")
        self.stat_cold = StatTile("archive", "冷数据可归档", "—", "", "teal")
        self.stat_temp = StatTile("trash", "Temp 占用", "—", "", "amber")
        for tile in (self.stat_potential, self.stat_released,
                     self.stat_cold, self.stat_temp):
            stats.addWidget(tile, 1)
        self.add_layout(stats)

        # 中部：存储布局 + 建议
        middle = QHBoxLayout()
        middle.setSpacing(14)
        self.storage_card = GlassCard(20, 12)
        self.storage_refresh = IconButton("refresh", "刷新磁盘信息",
                                          parent=self.storage_card)
        self.storage_head = card_header(
            "存储布局", "物理盘与分区", [self.storage_refresh])
        self.storage_refresh.clicked.connect(self._refresh_drives)
        self.storage_card.add(self.storage_head)
        self.drive_row = QHBoxLayout()
        self.drive_row.setSpacing(10)
        self.storage_card.add_layout(self.drive_row)
        self.storage_note_holder = QVBoxLayout()
        self.storage_card.add_layout(self.storage_note_holder)
        middle.addWidget(self.storage_card, 3)

        self.suggest_card = GlassCard(20, 10)
        self.suggest_card.add(card_header("建议操作", "按收益与风险排序"))
        self.suggest_box = QVBoxLayout()
        self.suggest_box.setSpacing(8)
        self.suggest_card.add_layout(self.suggest_box)
        self.suggest_card.body.addStretch()
        middle.addWidget(self.suggest_card, 2)
        self.add_layout(middle)

        # 最近操作
        self.recent_card = GlassCard(20, 10)
        more = QPushButton("查看全部")
        more.setObjectName("Link")
        more.setCursor(Qt.PointingHandCursor)
        more.clicked.connect(lambda: self.state.navigate.emit("history"))
        self.recent_card.add(card_header("最近操作", "结构化审计记录", [more]))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(7)
        self.recent_card.add_layout(self.recent_box)
        self.add(self.recent_card)
        self.add_stretch()

    # ---------- 刷新 ----------

    def refresh(self) -> None:
        self._update_hero()
        self._update_stats()
        self._update_drives()
        self._update_suggestions()
        self._update_recent()

    def _on_drives(self, _drives: list) -> None:
        self._update_hero()
        self._update_drives()

    def _on_scan_progress(self, progress: Any) -> None:
        self.btn_scan.setEnabled(False)
        self.btn_hero_scan.setEnabled(False)
        self.btn_hero_scan.setText(progress.message or "正在扫描…")

    def _on_busy(self, busy: bool) -> None:
        if not busy and not self.state.scanning:
            self.btn_scan.setEnabled(True)
            self.btn_hero_scan.setEnabled(True)
            self.btn_hero_scan.setText("扫描 C 盘")
        elif not busy:
            self.btn_scan.setEnabled(True)

    def _scan(self) -> None:
        self.state.start_scan()
        self.btn_hero_scan.setText("正在扫描…")

    def _refresh_drives(self) -> None:
        self.state.refresh_drives(force=True)

    def _update_hero(self) -> None:
        drive = self.state.c_drive()
        if drive is None:
            self.hero_free.setText("—")
            self.hero_used.setText("无法读取 C 盘信息")
            self.health_pill.set_text("未知")
            self.health_pill.set_tone("muted")
            return
        free_gb = drive.free_bytes / 1024 ** 3
        self.hero_free.setText(f"{free_gb:.1f}")
        used_pct = drive.used_ratio * 100
        self.hero_used.setText(
            f"已用 {human_bytes(drive.used_bytes)} / {human_bytes(drive.total_bytes)}"
            f"  ·  占用 {used_pct:.1f}%"
        )
        self.hero_bar.set_value(drive.used_ratio, animate=True)
        self.gauge.set_data(drive.used_ratio, f"{used_pct:.0f}%", "C 盘已使用")
        if drive.free_ratio < 0.08:
            self.health_pill.set_text("空间告急")
            self.health_pill.set_tone("rose")
        elif drive.free_ratio < 0.15:
            self.health_pill.set_text("空间偏紧")
            self.health_pill.set_tone("amber")
        else:
            self.health_pill.set_text("空间健康")
            self.health_pill.set_tone("green")

    def _update_stats(self) -> None:
        scan = self.state.scan
        analysis = self.state.analysis
        self.stat_potential.set_value(
            human_bytes(scan.potential_bytes),
            f"{len(scan.items)} 个目录 · {scan.scanned_at[-8:-3] if scan.scanned_at else '未扫描'}",
        )
        self.stat_released.set_value(
            human_bytes(scan.released_bytes),
            f"{len(scan.junctions)} 个链接 · 已迁出 C 盘",
        )
        recommended = [c for c in analysis.candidates
                       if c.tier in (TIER_STRONG, TIER_RECOMMEND)]
        self.stat_cold.set_value(
            human_bytes(analysis.total_recommended_bytes),
            f"{len(recommended)} 个候选 · 可转到机械盘",
        )
        self.stat_temp.set_value(
            human_bytes(scan.temp_bytes),
            f"保留 {self.state.config.temp_retention_days} 天",
        )

    def _update_drives(self) -> None:
        clear_layout(self.drive_row)
        drives = self.state.drives
        for drive in drives[:4]:
            card = DriveCard(drive)
            self.drive_row.addWidget(card, 1)
        # 说明
        clear_layout(self.storage_note_holder)
        note = self._storage_note(drives)
        if note:
            self.storage_note_holder.addWidget(note_frame(note[0], note[1], note[2]))

    def _storage_note(self, drives: list) -> tuple[str, str, str] | None:
        mapping = {d.letter.upper(): d for d in drives}
        c = mapping.get("C")
        d = mapping.get("D")
        if c and d and c.disk_number is not None and c.disk_number == d.disk_number:
            model = c.physical_name or c.model or "同一块物理盘"
            return (f"C 与 D 位于同一块物理盘（{model}）。迁移只释放分区空间，"
                    f"不会增加这块盘的总容量；真正的增量空间在机械盘。", "warn", "alert")
        usb = [x for x in drives if x.is_usb and not x.is_system]
        if usb:
            letters = "、".join(f"{x.letter}:" for x in usb)
            return (f"{letters} 是外置磁盘：适合归档冷数据，但拔盘后路径不可用，"
                    f"不要把正在运行的程序链接到它。", "info", "info")
        return None

    # ---------- 建议 ----------

    def _clear_layout(self, layout) -> None:
        clear_layout(layout)

    def _update_suggestions(self) -> None:
        self._clear_layout(self.suggest_box)
        scan = self.state.scan
        analysis = self.state.analysis
        rows: list[tuple[str, str, str, str, Any]] = []
        if not scan.scanned_at:
            rows.append(("search", "先扫描 C 盘", "找出可以迁移的大目录，量化可释放空间。",
                         "开始扫描", self._scan))
        else:
            if scan.items:
                rows.append((
                    "sparkles", f"迁移 {len(scan.items)} 个可迁移目录",
                    f"预计释放 {human_bytes(scan.potential_bytes)}，原路径保持不变。",
                    "去瘦身", lambda: self.state.navigate.emit("slimming")))
            if scan.temp_bytes > 300 * 1024 ** 2:
                rows.append((
                    "trash", "清理临时文件",
                    f"Temp 当前占用 {human_bytes(scan.temp_bytes)}，清理后立即释放。",
                    "立即清理", self._clean_temp))
        recommended = [c for c in analysis.candidates
                       if c.tier in (TIER_STRONG, TIER_RECOMMEND)]
        if recommended:
            rows.append((
                "archive", f"归档 {len(recommended)} 个冷数据目录",
                f"可把 {human_bytes(analysis.total_recommended_bytes)} 移到机械盘。",
                "去归档", lambda: self.state.navigate.emit("archive")))
        elif not analysis.scanned_at:
            rows.append((
                "archive", "分析冷数据",
                "按 IO 特征找出适合机械盘的电影、镜像、安装包。",
                "开始分析", lambda: self.state.navigate.emit("archive")))
        if scan.junctions:
            broken = sum(1 for j in scan.junctions if j.broken)
            rows.append((
                "link", f"管理 {len(scan.junctions)} 个目录链接",
                ("有 %d 个链接目标缺失。" % broken) if broken else "全部链接正常。",
                "去管理", lambda: self.state.navigate.emit("links")))
        if not rows:
            rows.append(("check", "当前没有需要处理的项目",
                         "定期回来扫描一次即可。", "重新扫描", self._scan))
        for icon_name, title, hint, action_text, callback in rows[:4]:
            row = QFrame()
            row.setObjectName("Row")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 9, 10, 9)
            layout.setSpacing(10)
            layout.addWidget(IconTile(icon_name, "brand", 32, 15))
            text_box = QVBoxLayout()
            text_box.setSpacing(1)
            t = label(title, "Body")
            t.setStyleSheet(f"color:{theme.TEXT};font-weight:600;")
            text_box.addWidget(t)
            text_box.addWidget(label(hint, "Dim", wrap=True))
            layout.addLayout(text_box, 1)
            btn = QPushButton(action_text)
            btn.setObjectName("Link")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(callback)
            layout.addWidget(btn)
            self.suggest_box.addWidget(row)

    def _clean_temp(self) -> None:
        days = self.state.config.temp_retention_days
        ok = ConfirmDialog.ask(
            self.window(), "清理临时文件",
            f"将删除 %TEMP% 中超过 {days} 天的文件，正在被使用的文件会自动跳过。",
            "开始清理", tone="amber", icon_name="trash",
            details=f"临时目录：{os.environ.get('TEMP', '')}\n不会删除最近 {days} 天内的文件。",
            note="清理不可撤销，但临时文件通常可重新生成。",
        )
        if not ok:
            return
        item = OperationItem(action=ACTION_CLEAN, source=os.environ.get("TEMP", ""),
                             name="Temp 清理", extra={"clean": "temp"})
        self.state.start_operation([item])

    # ---------- 最近操作 ----------

    def _update_recent(self) -> None:
        self._clear_layout(self.recent_box)
        records = self.state.history(5)
        if not records:
            self.recent_box.addWidget(EmptyState(
                "history", "还没有操作记录",
                "完成一次迁移或归档后，这里会出现可追溯的审计记录。"))
            return
        for record in records:
            row = QFrame()
            row.setObjectName("Row")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(10, 8, 12, 8)
            layout.setSpacing(10)
            layout.addWidget(action_icon_button(record.action))
            text_box = QVBoxLayout()
            text_box.setSpacing(1)
            title = QLabel(f"{record.action_label} · {record.name}")
            title.setStyleSheet(f"color:{theme.TEXT};font-size:12px;font-weight:600;")
            text_box.addWidget(title)
            path = record.dest if record.action in ("archive", "migrate") else record.source
            sub = QLabel(f"{fmt_time(record.ts)}  ·  {fmt_size(record.bytes_moved)}")
            sub.setStyleSheet(f"color:{theme.DIM};font-size:12px;")
            text_box.addWidget(sub)
            layout.addLayout(text_box, 1)
            layout.addWidget(status_pill(record.status))
            self.recent_box.addWidget(row)
