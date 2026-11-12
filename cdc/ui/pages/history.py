"""操作记录页：审计时间线、回迁 / 撤销、导出。"""

from __future__ import annotations

import csv
import json
import os
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ...core import applog, windows
from ...core.models import (
    ACTION_ARCHIVE, ACTION_LINK, ACTION_MIGRATE, ACTION_RESTORE, ACTION_UNDO,
    ACTION_UNLINK, MODE_COPY, OperationItem, OperationRecord, human_bytes,
)
from .. import theme
from ..widgets import (
    ConfirmDialog, ElidedLabel, EmptyState, GlassCard, IconButton, IconTile,
    InfoDialog, PageHeader, Pill, SearchField, ScrollPage, StatTile,
    clear_layout, label,
)
from .base import (
    ACTION_ICONS, action_icon_button, card_header, fmt_size, fmt_time,
    ghost_button, open_path, primary_button, status_pill,
)


class HistoryRow(QFrame):
    def __init__(self, record: OperationRecord, page: "HistoryPage") -> None:
        super().__init__()
        self.record = record
        self.page = page
        self.setObjectName("Row")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 12, 10)
        layout.setSpacing(11)
        layout.addWidget(action_icon_button(record.action), alignment=Qt.AlignTop)
        center = QVBoxLayout()
        center.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(7)
        title = QLabel(f"{record.action_label} · {record.name}")
        title.setStyleSheet(f"color:{theme.TEXT};font-size:13px;font-weight:600;")
        top.addWidget(title)
        top.addWidget(status_pill(record.status))
        if record.verified and record.status == "success":
            top.addWidget(Pill("已校验", "green"))
        if record.needs_admin:
            top.addWidget(Pill("管理员", "amber"))
        top.addStretch()
        center.addLayout(top)
        source = ElidedLabel(record.source, "MonoMuted")
        center.addWidget(source)
        if record.dest:
            dest = ElidedLabel(f"→  {record.dest}", "Mono")
            dest.setStyleSheet(f"color:{theme.DIM};font-size:12px;")
            center.addWidget(dest)
        meta = QLabel(
            f"{fmt_time(record.ts, short=False)}  ·  {fmt_size(record.bytes_moved)}"
            f"  ·  {record.duration_s:.1f}s"
            + (f"  ·  {record.mode_label}"
               if record.action in (ACTION_ARCHIVE, ACTION_RESTORE) else "")
        )
        meta.setStyleSheet(f"color:{theme.DIM};font-size:12px;")
        center.addWidget(meta)
        if record.error:
            error = QLabel(record.error)
            error.setStyleSheet(f"color:{theme.RED};font-size:12px;")
            error.setWordWrap(True)
            center.addWidget(error)
        layout.addLayout(center, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        detail = IconButton("info", "详情")
        detail.clicked.connect(self._show_detail)
        actions.addWidget(detail)
        if record.dest and os.path.exists(record.dest):
            open_btn = IconButton("external", "打开目标")
            open_btn.clicked.connect(lambda: open_path(record.dest))
            actions.addWidget(open_btn)
        undo_text = self._undo_text()
        if undo_text:
            btn = QPushButton(undo_text)
            btn.setObjectName("RowAction" if undo_text == "撤销迁移" else "RowWarn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._undo)
            actions.addWidget(btn)
        layout.addLayout(actions)

    def _undo_text(self) -> str:
        r = self.record
        if r.status != "success":
            return ""
        if r.action == ACTION_MIGRATE:
            if windows.is_junction(r.source):
                target = windows.junction_target(r.source)
                if target and os.path.isdir(target):
                    return "撤销迁移"
            return ""
        if r.action == ACTION_ARCHIVE and r.mode in ("move", "link"):
            if r.extra.get("junction_source"):
                return ""
            if os.path.isdir(r.dest):
                if not os.path.exists(r.source) or windows.is_junction(r.source):
                    return "回迁"
                if os.path.isdir(r.source) and \
                        windows.directory_stats(r.source, collect_ext=False).files == 0:
                    return "回迁"
        return ""

    def _undo(self) -> None:
        r = self.record
        if r.action == ACTION_MIGRATE:
            item = OperationItem(action=ACTION_UNDO, source=r.source, dest=r.dest,
                                 name=r.name, size_bytes=r.bytes_moved,
                                 needs_admin=r.needs_admin,
                                 extra={"delete_target": True})
            title = "撤销迁移"
            note = "数据从目标盘回迁到原路径；校验通过后会删除迁移副本。"
        else:
            item = OperationItem(action=ACTION_RESTORE, source=r.source, dest=r.dest,
                                 name=r.name, size_bytes=r.bytes_moved,
                                 needs_admin=False)
            title = "回迁归档"
            note = "数据从归档盘复制回原路径；校验通过后会删除归档副本。"
        ok = ConfirmDialog.ask(
            self.window(), f"{title}「{r.name}」？",
            f"将移动 {fmt_size(r.bytes_moved)} 数据。", title,
            tone="amber",
            details=f"源：{r.source}\n目标：{r.dest}",
            note=note, note_tone="warn", require_check=True,
            icon_name="undo" if r.action == ACTION_MIGRATE else "download",
        )
        if ok:
            self.page.state.start_operation([item])

    def _show_detail(self) -> None:
        body = json.dumps(self.record.to_dict(), ensure_ascii=False, indent=2)
        InfoDialog(self.window(), "操作详情", body).exec()


class HistoryPage(ScrollPage):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent, margins=(30, 22, 30, 30), spacing=16)
        self.state = state
        self._all: list[OperationRecord] = []
        self._build()
        state.history_changed.connect(self.refresh)
        state.operation_finished.connect(lambda _r: self.refresh())

    def _build(self) -> None:
        self.btn_export = ghost_button("导出 CSV", "download")
        self.btn_export.clicked.connect(self._export)
        self.btn_refresh = ghost_button("刷新", "refresh")
        self.btn_refresh.clicked.connect(self.refresh)
        self.add(PageHeader(
            "操作记录",
            "每一次迁移、归档、撤销与清理都有可追溯的审计记录。",
            [self.btn_export, self.btn_refresh],
        ))
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat_freed = StatTile("zap", "累计释放", "—", "", "brand")
        self.stat_migrate = StatTile("sparkles", "迁移成功", "—", "", "purple")
        self.stat_archive = StatTile("archive", "归档成功", "—", "", "teal")
        self.stat_failed = StatTile("alert", "失败 / 回滚", "—", "", "rose")
        for tile in (self.stat_freed, self.stat_migrate,
                     self.stat_archive, self.stat_failed):
            stats.addWidget(tile, 1)
        self.add_layout(stats)

        card = GlassCard(16, 12)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(9)
        self.search = SearchField("搜索目录名或路径…")
        self.search.textChanged.connect(lambda _t: self._render())
        toolbar.addWidget(self.search, 1)
        self.filter_action = QComboBox()
        self.filter_action.addItem("全部操作", "")
        for key, text in [("migrate", "迁移"), ("undo", "撤销"),
                          ("archive", "归档"), ("restore", "回迁"),
                          ("clean", "清理"), ("unlink", "移除链接")]:
            self.filter_action.addItem(text, key)
        self.filter_action.currentIndexChanged.connect(lambda _i: self._render())
        toolbar.addWidget(self.filter_action)
        self.filter_status = QComboBox()
        self.filter_status.addItem("全部状态", "")
        self.filter_status.addItem("成功", "success")
        self.filter_status.addItem("失败", "failed")
        self.filter_status.addItem("回滚", "rolled_back")
        self.filter_status.currentIndexChanged.connect(lambda _i: self._render())
        toolbar.addWidget(self.filter_status)
        card.add_layout(toolbar)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        card.add_layout(self.rows_box)
        self.empty = EmptyState(
            "history", "还没有操作记录",
            "完成一次迁移或归档后，审计记录会出现在这里；可随时撤销或回迁。")
        card.add(self.empty)
        self.add(card)
        audit_card = GlassCard(16, 6, "CardSoft")
        audit_head = QHBoxLayout()
        audit_head.addWidget(IconTile("database", "purple", 30, 15))
        audit_head.addWidget(label("审计文件", "Body"))
        audit_head.addWidget(label("JSONL · 每次操作追加一行", "Muted"))
        audit_head.addStretch()
        open_btn = ghost_button("打开目录", "external")
        open_btn.clicked.connect(lambda: open_path(str(self.state.audit.path)))
        audit_head.addWidget(open_btn)
        audit_card.add_layout(audit_head)
        audit_card.add(ElidedLabel(str(self.state.audit.path), "MonoMuted"))
        self.add(audit_card)

        log_card = GlassCard(16, 8, "CardSoft")
        log_head = QHBoxLayout()
        log_head.addWidget(IconTile("file-archive", "brand", 30, 15))
        log_head.addWidget(label("运行日志", "Body"))
        log_head.addWidget(label("按天写入 logs/", "Muted"))
        log_head.addStretch()
        refresh_log = ghost_button("刷新", "refresh")
        refresh_log.clicked.connect(self._reload_log)
        log_head.addWidget(refresh_log)
        open_log = ghost_button("打开目录", "external")
        open_log.clicked.connect(lambda: open_path(applog.log_path()))
        log_head.addWidget(open_log)
        log_card.add_layout(log_head)
        from PySide6.QtWidgets import QTextEdit
        self.log_body = QTextEdit()
        self.log_body.setObjectName("LogBody")
        self.log_body.setReadOnly(True)
        self.log_body.setFixedHeight(150)
        log_card.add(self.log_body)
        self.add(log_card)
        self._reload_log()
        self.add_stretch()
        self.refresh()

    def _reload_log(self) -> None:
        body = getattr(self, "log_body", None)
        if body is not None:
            body.setPlainText(applog.tail(200))
            body.verticalScrollBar().setValue(body.verticalScrollBar().maximum())

    def refresh(self) -> None:
        self._all = self.state.history()
        success = [r for r in self._all if r.status == "success"]
        freed = sum(r.bytes_moved for r in success)
        migrate = sum(1 for r in success if r.action == ACTION_MIGRATE)
        archive = sum(1 for r in success if r.action == ACTION_ARCHIVE)
        failed = sum(1 for r in self._all if r.status in ("failed", "rolled_back"))
        self.stat_freed.set_value(human_bytes(freed), f"{len(success)} 次成功操作")
        self.stat_migrate.set_value(str(migrate), "Junction 接管")
        self.stat_archive.set_value(str(archive), "冷数据归档")
        self.stat_failed.set_value(str(failed), "可在详情中查看原因")
        self._render()

    def _render(self) -> None:
        clear_layout(self.rows_box)
        text = self.search.text().strip().lower()
        action = self.filter_action.currentData()
        status = self.filter_status.currentData()
        rows = []
        for record in self._all:
            if action and record.action != action:
                continue
            if status and record.status != status:
                continue
            if text and text not in record.name.lower() \
                    and text not in record.source.lower() \
                    and text not in (record.dest or "").lower():
                continue
            rows.append(record)
        if not rows:
            self.empty.show()
            return
        self.empty.hide()
        for record in rows:
            self.rows_box.addWidget(HistoryRow(record, self))

    def _export(self) -> None:
        if not self._all:
            self.state.toast.emit("没有可导出的记录", "warn")
            return
        default = os.path.join(str(self.state.config.path.parent), "cdrivecleaner-history.csv")
        path, _ = QFileDialog.getSaveFileName(
            self.window(), "导出操作记录", default, "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["时间", "操作", "状态", "名称", "源路径", "目标路径",
                                 "模式", "字节", "文件数", "耗时(s)", "已校验", "错误"])
                for r in self._all:
                    writer.writerow([r.ts, r.action_label, r.status, r.name,
                                     r.source, r.dest, r.mode_label, r.bytes_moved,
                                     r.files, r.duration_s,
                                     "是" if r.verified else "否", r.error])
            self.state.toast.emit(f"已导出 {len(self._all)} 条记录", "success")
            open_path(os.path.dirname(path))
        except OSError as exc:
            self.state.toast.emit(f"导出失败：{exc}", "error")
