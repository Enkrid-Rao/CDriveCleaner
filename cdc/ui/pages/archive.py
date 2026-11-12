"""冷数据归档页：识别冷数据、选择机械盘、移动 / 链接 / 复制。"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QListView, QProgressBar, QPushButton,
    QScrollArea, QSpinBox, QTreeView, QVBoxLayout, QWidget,
)

from ...core import windows
from ...core.models import (
    ACTION_ARCHIVE, MODE_COPY, MODE_LABELS, MODE_LINK, MODE_MOVE,
    TIER_LABELS, TIER_OPTIONAL, TIER_RECOMMEND, TIER_SKIP, TIER_STRONG,
    ArchiveCandidate, OperationItem, human_bytes,
)
from .. import theme
from ..widgets import (
    Check, ConfirmDialog, DriveCard, ElidedLabel, EmptyState, GlassCard,
    IconButton, IconTile, PageHeader, PathPicker, Pill, ScrollPage,
    SegmentedControl, clear_layout, label,
)
from .base import (
    card_header, fmt_size, fmt_time, ghost_button, note_frame, open_path,
    primary_button,
)


EXT_LABELS = {
    "video": "视频", "audio": "音频", "image": "图片", "iso": "镜像",
    "installer": "安装包", "archive": "压缩包", "document": "文档",
    "code": "代码", "model": "模型", "backup": "备份", "other": "其他",
}
TIER_TONES = {
    TIER_STRONG: "green", TIER_RECOMMEND: "teal",
    TIER_OPTIONAL: "amber", TIER_SKIP: "muted",
}
TIER_ICONS = {
    TIER_STRONG: "check", TIER_RECOMMEND: "archive",
    TIER_OPTIONAL: "info", TIER_SKIP: "x",
}


def _category_icon(candidate: ArchiveCandidate) -> tuple[str, str]:
    exts = candidate.ext_bytes or {}
    top = max(exts, key=exts.get) if exts else "other"
    return {
        "video": ("film", "purple"),
        "image": ("image", "pink"),
        "iso": ("server", "cyan"),
        "installer": ("package", "amber"),
        "archive": ("file-archive", "orange"),
        "model": ("cpu", "brand"),
        "document": ("folder", "teal"),
        "audio": ("film", "pink"),
    }.get(top, ("folder", "muted"))


class ArchiveRow(QFrame):
    toggled = Signal(str, bool)
    archive = Signal(object)
    open_requested = Signal(str)

    def __init__(self, candidate: ArchiveCandidate, dest_path: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self.dest_path = dest_path or candidate.dest_path
        self.setObjectName("Row")
        self.setProperty("selected", False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 12, 10)
        layout.setSpacing(11)

        self.check = Check()
        self.check.toggled.connect(self._on_check)
        layout.addWidget(self.check, alignment=Qt.AlignVCenter)
        icon_name, tone = _category_icon(candidate)
        layout.addWidget(IconTile(icon_name, tone, 36, 17), alignment=Qt.AlignTop)

        center = QVBoxLayout()
        center.setSpacing(3)
        top = QHBoxLayout()
        top.setSpacing(7)
        name = QLabel(candidate.name)
        name.setStyleSheet(f"color:{theme.TEXT};font-size:13px;font-weight:600;")
        top.addWidget(name)
        top.addWidget(Pill(candidate.tier_label, TIER_TONES.get(candidate.tier, "muted")))
        top.addWidget(Pill(f"{candidate.source_drive}:", {"C": "c", "D": "d"}.get(
            candidate.source_drive, "muted")))
        if candidate.is_junction:
            linked = Pill("已链接", "purple")
            linked.setToolTip(f"当前指向：{candidate.target_path}")
            top.addWidget(linked)
        top.addStretch()
        center.addLayout(top)
        reason = QLabel(candidate.reason)
        reason.setStyleSheet(f"color:{theme.TEXT_2};font-size:12px;")
        center.addWidget(reason)
        chips = QHBoxLayout()
        chips.setSpacing(4)
        for ext, ratio in candidate.top_exts(3):
            chips.addWidget(Pill(f"{EXT_LABELS.get(ext, ext)} {ratio:.0%}", "muted"))
        if candidate.age_days:
            chips.addWidget(Pill(f"{candidate.age_days} 天未改", "muted"))
        if candidate.file_count:
            chips.addWidget(Pill(f"{candidate.file_count:,} 文件", "muted"))
        chips.addStretch()
        center.addLayout(chips)
        path = ElidedLabel(candidate.path, "MonoMuted")
        center.addWidget(path)
        layout.addLayout(center, 1)

        right = QVBoxLayout()
        right.setSpacing(3)
        size = QLabel(fmt_size(candidate.size_bytes))
        size.setStyleSheet(
            f"color:{theme.TEXT};font-family:'Cascadia Mono';font-size:14px;font-weight:700;"
        )
        size.setAlignment(Qt.AlignRight)
        right.addWidget(size)
        dest = QLabel(f"→ {self.dest_path}")
        dest.setStyleSheet(f"color:{theme.DIM};font-size:12px;")
        dest.setAlignment(Qt.AlignRight)
        dest.setMaximumWidth(260)
        dest.setToolTip(self.dest_path)
        right.addWidget(dest)
        layout.addLayout(right)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        open_btn = IconButton("external", "打开目录")
        open_btn.clicked.connect(lambda: self.open_requested.emit(candidate.path))
        actions.addWidget(open_btn)
        self.btn = QPushButton("归档")
        self.btn.setObjectName("RowAction")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(lambda: self.archive.emit(candidate))
        if candidate.tier == TIER_SKIP:
            self.btn.setEnabled(False)
            self.check.setEnabled(False)
        actions.addWidget(self.btn)
        layout.addLayout(actions)

    def _on_check(self, checked: bool) -> None:
        self.setProperty("selected", checked)
        self.style().unpolish(self)
        self.style().polish(self)
        self.toggled.emit(self.candidate.path, checked)

    def set_checked(self, checked: bool) -> None:
        self.check.setChecked(checked)


class ArchivePage(QWidget):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.selected: dict[str, ArchiveCandidate] = {}
        self._rows: list[ArchiveRow] = []
        self.dest_drive: str = ""
        self.custom_dirs: list[str] = []
        self._build()
        state.analysis_started.connect(self._on_analysis_started)
        state.analysis_progress.connect(self._on_analysis_progress)
        state.analysis_finished.connect(self._on_analysis_finished)
        state.analysis_failed.connect(self._on_analysis_failed)
        state.drives_changed.connect(lambda _d: self._refresh_drives())

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

        self.btn_analyze = primary_button("分析冷数据", "search")
        self.btn_analyze.clicked.connect(self._analyze)
        self.btn_open_root = ghost_button("打开归档目录", "external")
        self.btn_open_root.clicked.connect(lambda: open_path(self._archive_root()))
        content.addWidget(PageHeader(
            "冷数据归档",
            "把“读写一两次”的电影、镜像、安装包放到机械盘，给 SSD 腾出空间。",
            [self.btn_open_root, self.btn_analyze],
        ))

        # 顶部：目标盘 + 方案
        top = QHBoxLayout()
        top.setSpacing(14)
        self.dest_card = GlassCard(18, 11)
        self.dest_card.add(card_header(
            "归档到", "选中的目录会按目录名放到该路径下，同级排列"))
        self.drive_row = QHBoxLayout()
        self.drive_row.setSpacing(9)
        self.dest_card.add_layout(self.drive_row)
        root_row = QHBoxLayout()
        root_row.setSpacing(9)
        root_row.addWidget(label("目标路径", "Label"))
        self.root_picker = PathPicker(self._archive_root(), r"例如 E:\ 或 E:\ColdStore")
        self.root_picker.changed.connect(self._on_root_changed)
        root_row.addWidget(self.root_picker, 1)
        self.dest_card.add_layout(root_row)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_row.addWidget(label("归档方式", "Label"))
        self.mode = SegmentedControl(
            [(MODE_MOVE, "移动归档"), (MODE_LINK, "链接归档"), (MODE_COPY, "仅复制")],
            self.state.config.default_mode,
        )
        self.mode.changed.connect(self._on_mode)
        mode_row.addWidget(self.mode)
        mode_row.addStretch()
        self.strict_check = Check("严格校验（SHA256，较慢）")
        self.strict_check.setChecked(self.state.config.strict_verify)
        mode_row.addWidget(self.strict_check)
        self.dest_card.add_layout(mode_row)
        self.mode_note = QLabel("")
        self.mode_note.setObjectName("Muted")
        self.mode_note.setWordWrap(True)
        self.dest_card.add(self.mode_note)
        top.addWidget(self.dest_card, 3)

        self.plan_card = GlassCard(18, 10)
        self.plan_card.add(card_header("本次归档", "选择候选后生成执行计划"))
        self.plan_value = QLabel("0 B")
        self.plan_value.setStyleSheet(
            f"color:{theme.TEXT};font-family:'Cascadia Mono';"
            "font-size:26px;font-weight:800;"
        )
        self.plan_card.add(self.plan_value)
        self.plan_hint = label("勾选下方候选目录", "Muted")
        self.plan_card.add(self.plan_hint)
        self.plan_bar = QProgressBar()
        self.plan_bar.setRange(0, 1000)
        self.plan_bar.setValue(0)
        self.plan_bar.setFixedHeight(7)
        self.plan_card.add(self.plan_bar)
        self.plan_free = label("目标可用 —", "MonoMuted")
        self.plan_card.add(self.plan_free)
        self.plan_after = label("归档后可用 —", "MonoMuted")
        self.plan_card.add(self.plan_after)
        self.plan_card.body.addStretch()
        self.btn_start = primary_button("开始归档", "archive")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._archive_selected)
        self.plan_card.add(self.btn_start)
        top.addWidget(self.plan_card, 2)
        content.addLayout(top)

        # 分析范围
        scan_card = GlassCard(14, 8, "CardSoft")
        scan_row = QHBoxLayout()
        scan_row.setSpacing(12)
        scan_row.addWidget(IconTile("filter", "brand", 34, 16))
        scan_row.addWidget(label("扫描范围", "Label"))
        self.root_c = Check("C 用户目录")
        self.root_c.setChecked(True)
        self.root_d = Check("D 盘根目录")
        self.root_d.setChecked(True)
        scan_row.addWidget(self.root_c)
        scan_row.addWidget(self.root_d)
        scan_row.addStretch()
        scan_row.addWidget(label("最小", "Muted"))
        self.min_size = QSpinBox()
        self.min_size.setRange(50, 51200)
        self.min_size.setValue(max(50, int(self.state.config.archive_min_mb)))
        self.min_size.setSuffix(" MB")
        self.min_size.setFixedWidth(110)
        scan_row.addWidget(self.min_size)
        self.analysis_state = label("尚未分析", "Muted")
        scan_row.addWidget(self.analysis_state)
        self.analysis_bar = QProgressBar()
        self.analysis_bar.setRange(0, 100)
        self.analysis_bar.setFixedWidth(150)
        self.analysis_bar.setFixedHeight(6)
        self.analysis_bar.hide()
        scan_row.addWidget(self.analysis_bar)
        self.btn_cancel_analysis = QPushButton("取消")
        self.btn_cancel_analysis.setObjectName("Link")
        self.btn_cancel_analysis.clicked.connect(self.state.cancel_analysis)
        self.btn_cancel_analysis.hide()
        scan_row.addWidget(self.btn_cancel_analysis)
        scan_card.add_layout(scan_row)

        custom_row = QHBoxLayout()
        custom_row.setSpacing(9)
        custom_row.addWidget(IconTile("folder", "amber", 30, 15))
        custom_row.addWidget(label("自定义目录（可多选）", "Label"))
        self.custom_label = ElidedLabel("未选择", "Muted")
        self.custom_label.setMinimumWidth(180)
        custom_row.addWidget(self.custom_label, 1)
        self.btn_clear_custom = QPushButton("清除")
        self.btn_clear_custom.setObjectName("Link")
        self.btn_clear_custom.setCursor(Qt.PointingHandCursor)
        self.btn_clear_custom.clicked.connect(self._clear_custom_root)
        self.btn_clear_custom.setEnabled(False)
        custom_row.addWidget(self.btn_clear_custom)
        self.btn_pick_custom = ghost_button("选择目录", "folder")
        self.btn_pick_custom.clicked.connect(self._pick_custom_root)
        custom_row.addWidget(self.btn_pick_custom)
        self.btn_direct_custom = primary_button("归档所选目录", "archive")
        self.btn_direct_custom.setEnabled(False)
        self.btn_direct_custom.clicked.connect(self._archive_custom_direct)
        custom_row.addWidget(self.btn_direct_custom)
        scan_card.add_layout(custom_row)
        content.addWidget(scan_card)

        # 候选列表
        self.list_card = GlassCard(12, 8, "Card")
        self.list_head = card_header("冷数据候选", "按推荐等级与体积排序")
        self.show_skipped = Check("显示不建议项")
        self.show_skipped.toggled.connect(lambda _c: self._render())
        self.list_head.layout().addWidget(self.show_skipped)
        self.list_card.add(self.list_head)
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(6)
        self.list_card.add_layout(self.rows_box)
        self.empty = EmptyState(
            "archive", "看看哪些数据可以搬去机械盘",
            "会按扩展名、文件大小、最后修改时间判断 IO 特征；"
            "代码仓库、聊天数据库、浏览器缓存不会被推荐。",
            primary_button("开始分析", "search"),
        )
        self.empty.action_widget.clicked.connect(self._analyze)
        self.list_card.add(self.empty)
        content.addWidget(self.list_card)

        guide = GlassCard(18, 12, "CardSoft")
        guide.add(card_header("冷数据判据", "按 IO 模式，而不是按文件大小"))
        cols = QHBoxLayout()
        cols.setSpacing(12)
        for tone, icon_name, title, text in [
            ("green", "check", "适合机械盘",
             "电影 / 录屏 / 课程视频、ISO 与虚拟机镜像、安装包、压缩归档、照片素材、"
             "长期不动的资料。顺序读取，机械盘完全够用。"),
            ("rose", "x", "不建议机械盘",
             "聊天数据库、浏览器缓存、IDE 索引、代码仓库与 node_modules。"
             "小文件高频随机读写是机械盘最弱的地方。"),
            ("amber", "alert", "外置盘注意",
             "拔盘后目标路径会消失。移动归档的数据需要接上磁盘才能访问；"
             "链接归档更不能指向会拔掉的盘。"),
        ]:
            box = QFrame()
            box.setObjectName("CardInset")
            b = QVBoxLayout(box)
            b.setContentsMargins(14, 12, 14, 12)
            b.setSpacing(5)
            head = QHBoxLayout()
            head.setSpacing(8)
            head.addWidget(IconTile(icon_name, tone, 30, 15))
            head.addWidget(label(title, "Body"))
            head.addStretch()
            b.addLayout(head)
            b.addWidget(label(text, "Muted", wrap=True))
            cols.addWidget(box, 1)
        guide.add_layout(cols)
        content.addWidget(guide)

        content.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # 批量栏
        self.batch = QFrame()
        self.batch.setObjectName("BatchBar")
        self.batch.setFixedHeight(64)
        batch_layout = QHBoxLayout(self.batch)
        batch_layout.setContentsMargins(22, 10, 22, 10)
        batch_layout.setSpacing(12)
        batch_layout.addWidget(IconTile("archive", "teal", 34, 16))
        self.batch_text = label("已选 0 项", "Body")
        self.batch_text.setStyleSheet(f"color:{theme.TEXT};font-weight:600;")
        self.batch_size = label("", "MonoMuted")
        batch_layout.addWidget(self.batch_text)
        batch_layout.addWidget(self.batch_size)
        batch_layout.addStretch()
        clear = ghost_button("清除选择")
        clear.clicked.connect(self._clear_selection)
        batch_layout.addWidget(clear)
        self.btn_batch = primary_button("归档所选", "archive")
        self.btn_batch.clicked.connect(self._archive_selected)
        batch_layout.addWidget(self.btn_batch)
        self.batch.hide()
        outer.addWidget(self.batch)
        self.batch.setStyleSheet(
            "QFrame#BatchBar { background:#FBF8F2; "
            "border-top:1px solid #DCD3C2; }"
        )

        self._init_destination()
        self._on_mode(self.mode.value())
        self.refresh()

    # ---------- 目标盘 ----------

    def _archive_root(self) -> str:
        text = self.root_picker.text() if hasattr(self, "root_picker") else ""
        return text or self.state.config.archive_root

    def _init_destination(self) -> None:
        root = self.state.config.archive_root
        letter = (root[:1] if len(root) >= 2 and root[1] == ":" else "").upper()
        candidates = {d.letter.upper() for d in self.state.archive_drives()}
        self.dest_drive = letter if letter in candidates else (
            self.state.archive_drives()[0].letter if self.state.archive_drives() else "")
        self._render_drives()
        if self.dest_drive and letter not in candidates:
            self.root_picker.set_text(f"{self.dest_drive}:\\ColdStore")
        self._update_plan()

    def _refresh_drives(self) -> None:
        self._render_drives()
        self._update_plan()

    def _render_drives(self) -> None:
        clear_layout(self.drive_row)
        drives = self.state.archive_drives()
        if not drives:
            self.drive_row.addWidget(note_frame(
                "未检测到可用的非系统盘。请连接机械盘后刷新。", "warn", "alert"), 1)
            self.btn_start.setEnabled(False)
            self.btn_analyze.setEnabled(False)
            return
        for drive in drives[:3]:
            card = DriveCard(drive, selectable=True)
            card.set_selected(drive.letter.upper() == self.dest_drive)
            card.clicked.connect(self._select_drive)
            self.drive_row.addWidget(card, 1)
        self.btn_analyze.setEnabled(True)

    def _select_drive(self, letter: str) -> None:
        self.dest_drive = letter.upper()
        current = self.root_picker.text()
        if not current or current[:1].upper() != letter.upper():
            self.root_picker.set_text(f"{letter}:\\ColdStore")
        self._render_drives()
        self._update_plan()

    def _on_root_changed(self, text: str) -> None:
        letter = text.strip()[:1].upper()
        if len(text.strip()) >= 2 and text.strip()[1] == ":":
            candidates = {d.letter.upper() for d in self.state.archive_drives()}
            if letter in candidates and letter != self.dest_drive:
                self.dest_drive = letter
                self._render_drives()
        self._update_plan()
        if self.state.analysis.candidates:
            self._render()

    def _on_mode(self, mode: str) -> None:
        if mode == MODE_LINK:
            text = "复制并校验后清空源内容，再在原位置建立 Junction；程序仍按原路径访问。"
            tone = "warn"
        elif mode == MODE_COPY:
            text = "只复制并校验，源目录保留；适合先备份、暂不释放空间。"
            tone = "info"
        else:
            text = "复制并校验后清空源目录内容，保留目录结构与空子目录；空间立即释放。"
            tone = "success"
        self.mode_note.setText(text)
        self.mode_note.setStyleSheet(
            f"color:{theme.GREEN if tone == 'success' else theme.AMBER if tone == 'warn' else theme.MUT};"
            "font-size:12px;"
        )
        self._update_plan()

    def _update_plan(self) -> None:
        selected = list(self.selected.values())
        total = sum(c.size_bytes for c in selected)
        self.plan_value.setText(human_bytes(total))
        linked_count = sum(1 for c in selected if c.is_junction)
        if selected:
            mode_text = (MODE_LABELS.get(MODE_LINK, "链接归档")
                         if linked_count == len(selected)
                         else MODE_LABELS.get(self.mode.value(), ""))
            hint = f"{len(selected)} 个目录"
            if linked_count:
                hint += f" · 其中 {linked_count} 个已链接（保留原路径）"
            hint += f" · {mode_text}"
        else:
            hint = "勾选下方候选目录"
        self.plan_hint.setText(hint)
        root = self._archive_root()
        free = 0
        if self.dest_drive:
            drive = next((d for d in self.state.drives
                          if d.letter.upper() == self.dest_drive), None)
            free = drive.free_bytes if drive else 0
        self.plan_free.setText(f"目标可用 {human_bytes(free)}")
        self.plan_after.setText(
            f"归档后可用 {human_bytes(max(0, free - total))}"
            if total else "归档后可用 —")
        ratio = min(1.0, total / free) if free else 0
        self.plan_bar.setValue(int(ratio * 1000))
        self.btn_start.setEnabled(bool(selected) and bool(root) and free > total)
        self.btn_batch.setEnabled(bool(selected))

    # ---------- 分析 ----------

    def _roots(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        home = os.environ.get("USERPROFILE", "")
        if self.root_c.isChecked() and home and os.path.isdir(home):
            rows.append((home, "C 用户目录"))
        if self.root_d.isChecked() and os.path.isdir("D:\\"):
            rows.append(("D:\\", "D 盘根目录"))
        for path in self.custom_dirs:
            if os.path.isdir(path):
                rows.append((path, os.path.basename(path.rstrip("\\/")) or "自定义目录"))
        return rows

    def _pick_custom_root(self) -> None:
        start = self.custom_dirs[-1] if self.custom_dirs else (self._archive_root() or "D:\\")
        dialog = QFileDialog(self.window(), "选择要归档的目录（可多选）")
        dialog.setOption(QFileDialog.DontUseNativeDialog, True)
        dialog.setOption(QFileDialog.ShowDirsOnly, True)
        dialog.setFileMode(QFileDialog.ExistingFiles)
        dialog.setDirectory(start)
        for view in list(dialog.findChildren(QListView)) + list(dialog.findChildren(QTreeView)):
            view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        if not dialog.exec():
            return
        paths = [os.path.normpath(p) for p in dialog.selectedFiles()
                 if os.path.isdir(p)]
        if not paths:
            self.state.toast.emit("没有选中目录", "warn")
            return
        existing = {os.path.normcase(p) for p in self.custom_dirs}
        for path in paths:
            if os.path.normcase(path) == os.path.normcase(self._archive_root()):
                continue
            if os.path.normcase(path) not in existing:
                self.custom_dirs.append(path)
                existing.add(os.path.normcase(path))
        self._refresh_custom_label()
        self.analysis_state.setText("已选择自定义目录，可分析或归档")

    def _refresh_custom_label(self) -> None:
        if not self.custom_dirs:
            self.custom_label.set_full_text("未选择")
            self.custom_label.setToolTip("")
            self.btn_clear_custom.setEnabled(False)
            self.btn_direct_custom.setEnabled(False)
            return
        names = "、".join(os.path.basename(p.rstrip("\\/")) or p
                         for p in self.custom_dirs)
        self.custom_label.set_full_text(f"已选 {len(self.custom_dirs)} 个：{names}")
        self.custom_label.setToolTip("\n".join(self.custom_dirs))
        self.btn_clear_custom.setEnabled(True)
        self.btn_direct_custom.setEnabled(True)

    def _clear_custom_root(self) -> None:
        self.custom_dirs.clear()
        self._refresh_custom_label()

    def _dest_for_path(self, path: str) -> str:
        return os.path.join(self._archive_root(),
                            os.path.basename(path.rstrip("\\/")) or path)

    def _duplicate_dests(self, items: list[OperationItem]) -> list[str]:
        seen: dict[str, str] = {}
        dupes: list[str] = []
        for item in items:
            key = os.path.normcase(os.path.abspath(item.dest))
            if key in seen:
                dupes.append(f"{os.path.basename(item.source)} → {item.dest}")
            else:
                seen[key] = item.source
        return dupes

    def _archive_custom_direct(self) -> None:
        if not self.custom_dirs:
            self.state.toast.emit("请先选择目录（可多选）", "warn")
            return
        items: list[OperationItem] = []
        total = 0
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for path in self.custom_dirs:
                if not os.path.isdir(path):
                    continue
                is_link = windows.is_link(path)
                target = windows.junction_target(path) if is_link else ""
                stat_root = target if is_link and target else path
                size = windows.directory_stats(stat_root, collect_ext=False).bytes
                mode = MODE_LINK if is_link else self.mode.value()
                extra = {"junction_source": True, "old_target": target} if is_link else {}
                item = OperationItem(
                    action=ACTION_ARCHIVE,
                    source=path,
                    dest=self._dest_for_path(path),
                    name=os.path.basename(path.rstrip("\\/")) or path,
                    size_bytes=size,
                    mode=mode,
                    needs_admin=self.state.config.needs_admin_for(path),
                    extra=extra,
                )
                items.append(item)
                total += size
        finally:
            QApplication.restoreOverrideCursor()
        if not items:
            self.state.toast.emit("没有可归档的目录", "warn")
            return
        dupes = self._duplicate_dests(items)
        if dupes:
            ConfirmDialog.show_info(
                self.window(), "目录名冲突",
                "多个目录会归档到同一个目标路径，请改名或分批处理。",
                "\n".join(dupes[:8]), icon_name="alert", tone="rose")
            return
        mode = self.mode.value()
        note = {
            MODE_MOVE: "复制并校验后清空每个源目录的内容，但保留目录结构与空子目录。",
            MODE_LINK: "复制并校验后清空内容，并在原位置建立 Junction。",
            MODE_COPY: "仅复制并校验，源目录保留。",
        }.get(mode, "")
        lines = "\n".join(f"· {i.name}  {fmt_size(i.size_bytes)} → {i.dest}"
                          for i in items[:8])
        if len(items) > 8:
            lines += f"\n… 另有 {len(items) - 8} 个"
        ok = ConfirmDialog.ask(
            self.window(),
            f"归档 {len(items)} 个目录？" if len(items) > 1 else f"归档「{items[0].name}」？",
            f"{MODE_LABELS.get(mode, '')} · 共 {human_bytes(total)} → {self._archive_root()}",
            "开始归档",
            tone="teal",
            details=lines,
            note=note,
            note_tone="warn" if mode == MODE_LINK else "success",
            require_check=True,
            icon_name="archive",
        )
        if ok:
            self.state.start_operation(items)

    def _analyze(self) -> None:
        roots = self._roots()
        if not roots:
            self.state.toast.emit("请至少选择一个扫描范围", "warn")
            return
        self.state.config.archive_min_mb = self.min_size.value()
        try:
            self.state.config.save()
        except Exception:
            pass
        self.selected.clear()
        self.state.start_analysis(roots)

    def _on_analysis_started(self) -> None:
        self.btn_analyze.setEnabled(False)
        self.analysis_bar.show()
        self.analysis_bar.setValue(0)
        self.btn_cancel_analysis.show()
        self.analysis_state.setText("正在分析…")

    def _on_analysis_progress(self, progress: Any) -> None:
        self.analysis_bar.setValue(int(progress.percent))
        self.analysis_state.setText(progress.message or progress.phase)

    def _on_analysis_finished(self, result: Any) -> None:
        self.btn_analyze.setEnabled(True)
        self.analysis_bar.hide()
        self.btn_cancel_analysis.hide()
        self.analysis_state.setText(
            f"上次分析 {fmt_time(result.scanned_at)} · {len(result.candidates)} 个目录")
        self.selected.clear()
        self.refresh()

    def _on_analysis_failed(self, error: str) -> None:
        self.btn_analyze.setEnabled(True)
        self.analysis_bar.hide()
        self.btn_cancel_analysis.hide()
        self.analysis_state.setText(f"分析失败：{error}")
        self.state.toast.emit(f"分析失败：{error}", "error")

    # ---------- 渲染 ----------

    def refresh(self) -> None:
        analysis = self.state.analysis
        if analysis.scanned_at:
            self.analysis_state.setText(
                f"上次分析 {fmt_time(analysis.scanned_at)} · {len(analysis.candidates)} 个目录")
        self._render()
        self._update_plan()

    def _clear_rows(self) -> None:
        clear_layout(self.rows_box)
        self._rows = []

    def _render(self) -> None:
        self._clear_rows()
        candidates = list(self.state.analysis.candidates)
        if not candidates:
            self.empty.show()
            self._update_plan()
            return
        self.empty.hide()
        show_skipped = self.show_skipped.isChecked()
        grouped: dict[str, list[ArchiveCandidate]] = {}
        for cand in candidates:
            if cand.tier == TIER_SKIP and not show_skipped:
                continue
            grouped.setdefault(cand.tier, []).append(cand)
        order = [TIER_STRONG, TIER_RECOMMEND, TIER_OPTIONAL, TIER_SKIP]
        any_row = False
        for tier in order:
            rows = grouped.get(tier, [])
            if not rows:
                continue
            any_row = True
            header = QHBoxLayout()
            header.setContentsMargins(4, 6, 4, 1)
            header.addWidget(IconTile(TIER_ICONS.get(tier, "dot"),
                                      TIER_TONES.get(tier, "muted"), 24, 13))
            header.addWidget(label(TIER_LABELS.get(tier, tier), "CardTitle"))
            header.addWidget(label(f"{len(rows)} 个目录 · "
                                   f"{human_bytes(sum(c.size_bytes for c in rows))}", "Muted"))
            header.addStretch()
            self.rows_box.addLayout(header)
            for cand in rows:
                row = ArchiveRow(cand, self._dest_for(cand))
                row.toggled.connect(self._on_row_toggled)
                row.archive.connect(self._archive_one)
                row.open_requested.connect(open_path)
                if cand.path in self.selected:
                    row.set_checked(True)
                self.rows_box.addWidget(row)
                self._rows.append(row)
        if not any_row:
            self.rows_box.addWidget(EmptyState(
                "check", "没有达到推荐阈值的冷数据",
                "当前选择的范围很干净。可以降低最小体积或换一个扫描范围。"))

    # ---------- 选择 / 执行 ----------

    def _on_row_toggled(self, path: str, checked: bool) -> None:
        cand = next((c for c in self.state.analysis.candidates if c.path == path), None)
        if checked and cand:
            self.selected[path] = cand
        else:
            self.selected.pop(path, None)
        self._update_batch()
        self._update_plan()

    def _update_batch(self) -> None:
        count = len(self.selected)
        self.batch.setVisible(count > 0)
        if count:
            total = sum(c.size_bytes for c in self.selected.values())
            self.batch_text.setText(f"已选 {count} 项")
            self.batch_size.setText(f"共 {human_bytes(total)}")
        self.btn_start.setEnabled(bool(count) and self._can_start())

    def _can_start(self) -> bool:
        total = sum(c.size_bytes for c in self.selected.values())
        drive = next((d for d in self.state.drives
                      if d.letter.upper() == self.dest_drive), None)
        free = drive.free_bytes if drive else 0
        return bool(self.selected) and bool(self._archive_root()) and free > total

    def _clear_selection(self) -> None:
        self.selected.clear()
        for row in self._rows:
            row.set_checked(False)
        self._update_batch()
        self._update_plan()

    def _dest_for(self, cand: ArchiveCandidate) -> str:
        return os.path.join(self._archive_root(), cand.name)

    def _make_items(self, candidates: list[ArchiveCandidate]) -> list[OperationItem]:
        mode = self.mode.value()
        strict = self.strict_check.isChecked()
        rows = []
        for cand in candidates:
            linked = bool(cand.is_junction)
            item_mode = MODE_LINK if linked else mode
            extra = {}
            if linked:
                extra = {"junction_source": True, "old_target": cand.target_path}
            rows.append(OperationItem(
                action=ACTION_ARCHIVE,
                source=cand.path,
                dest=self._dest_for(cand),
                name=cand.name,
                size_bytes=cand.size_bytes,
                file_count=cand.file_count,
                needs_admin=bool(cand.needs_admin or
                                 self.state.config.needs_admin_for(cand.path)),
                mode=item_mode,
                strict_verify=strict,
                extra=extra,
            ))
        return rows

    def _archive_one(self, cand: ArchiveCandidate) -> None:
        self._confirm_and_run([cand])

    def _archive_selected(self) -> None:
        self._confirm_and_run(list(self.selected.values()))

    def _confirm_and_run(self, candidates: list[ArchiveCandidate]) -> None:
        if not candidates:
            return
        items = self._make_items(candidates)
        dupes = self._duplicate_dests(items)
        if dupes:
            ConfirmDialog.show_info(
                self.window(), "目录名冲突",
                "多个目录会归档到同一个目标路径，请改名或分批处理。",
                "\n".join(dupes[:8]), icon_name="alert", tone="rose")
            return
        total = sum(c.size_bytes for c in candidates)
        mode = self.mode.value()
        root = self._archive_root()
        names = "\n".join(f"· {c.name}  {fmt_size(c.size_bytes)} → {i.dest}"
                          for c, i in zip(candidates[:6], items[:6]))
        if len(candidates) > 6:
            names += f"\n… 另有 {len(candidates) - 6} 项"
        drive = next((d for d in self.state.drives
                      if d.letter.upper() == self.dest_drive), None)
        note = {
            MODE_MOVE: "校验通过后清空源目录内容，但保留目录结构；源路径仍然存在。",
            MODE_LINK: "校验后清空源内容并建立 Junction；若目标是外置盘，拔盘后原路径不可用。",
            MODE_COPY: "仅复制，源目录保留，不会释放空间。",
        }.get(mode, "")
        if drive and drive.is_usb:
            note += " 目标是 USB 外置盘，归档完成后请保持连接。"
        linked = [c for c in candidates if c.is_junction]
        if linked:
            note += (f" 其中 {len(linked)} 个目录已通过 Junction 存放在其他盘："
                     "归档会保留原路径，并把链接改指到归档目标。")
        mode_text = (MODE_LABELS.get(MODE_LINK, "链接归档")
                     if linked and len(linked) == len(candidates)
                     else MODE_LABELS.get(mode, ""))
        ok = ConfirmDialog.ask(
            self.window(),
            f"归档 {len(candidates)} 个目录？" if len(candidates) > 1 else
            f"归档「{candidates[0].name}」？",
            f"{mode_text} · 共 {human_bytes(total)} → {root}",
            "开始归档",
            tone="teal",
            details=names + f"\n\n目标路径：{root}",
            note=note,
            note_tone="warn" if (drive and drive.is_usb) or mode == MODE_LINK or bool(linked)
            else "success",
            require_check=len(candidates) > 1 or mode != MODE_COPY or bool(linked),
            icon_name="archive",
        )
        if not ok:
            return
        if self.state.start_operation(items):
            self._clear_selection()
