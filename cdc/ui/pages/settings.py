"""设置页：路径、安全、外观与数据位置。"""

from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QSpinBox, QVBoxLayout,
    QWidget,
)

from ... import paths
from ...core import windows
from ...core.models import MODE_COPY, MODE_LINK, MODE_MOVE
from ...version import __version__
from .. import theme
from ..widgets import (
    Check, FormRow, GlassCard, IconTile, PageHeader, PathPicker, ScrollPage,
    SegmentedControl, Toggle, label,
)
from .base import card_header, ghost_button, note_frame, open_path, primary_button


class SettingsPage(ScrollPage):
    def __init__(self, state, parent: QWidget | None = None) -> None:
        super().__init__(parent, margins=(30, 22, 30, 30), spacing=16)
        self.state = state
        self._build()
        state.config_changed.connect(self._reload_fields)

    def _build(self) -> None:
        self.btn_save = primary_button("保存设置", "save")
        self.btn_save.clicked.connect(self._save)
        self.add(PageHeader(
            "设置",
            "配置迁移容器、归档盘、安全策略与界面。保存后立即生效。",
            [self.btn_save],
        ))
        self.error_label = label("", "ErrorText", wrap=True)
        self.error_label.hide()
        self.add(self.error_label)

        # 存储与迁移
        storage = GlassCard(18, 6)
        storage.add(card_header("存储与迁移", "C 盘瘦身的目标位置与扫描阈值"))
        self.link_root = PathPicker(self.state.config.link_root,
                                    r"例如 D:\_CDrive")
        storage.add(FormRow("迁移容器根路径", "C 盘目录迁移后实际存放的位置。"
                            "必须是非 C 盘的绝对路径。", self.link_root, stretch=True))
        self.threshold = QSpinBox()
        self.threshold.setRange(10, 10240)
        self.threshold.setSuffix(" MB")
        self.threshold.setValue(self.state.config.threshold_mb)
        self.threshold.setFixedWidth(130)
        storage.add(FormRow("扫描阈值", "只展示超过该体积的目录；调低会更全但更慢。",
                            self.threshold))
        self.temp_days = QSpinBox()
        self.temp_days.setRange(0, 365)
        self.temp_days.setSuffix(" 天")
        self.temp_days.setValue(self.state.config.temp_retention_days)
        self.temp_days.setFixedWidth(110)
        storage.add(FormRow("临时文件保留", "清理 Temp 时只删除超过该天数的文件；0 表示全部。",
                            self.temp_days))
        self.add(storage)

        # 冷数据归档
        archive = GlassCard(18, 6)
        archive.add(card_header("冷数据归档", "机械盘 / 外置盘与默认归档方式"))
        self.archive_root = PathPicker(self.state.config.archive_root,
                                       r"例如 E:\ColdStore")
        archive.add(FormRow("默认归档路径", "选中的目录会按目录名放到该路径下（同级）。",
                            self.archive_root, stretch=True))
        self.archive_min = QSpinBox()
        self.archive_min.setRange(50, 51200)
        self.archive_min.setSuffix(" MB")
        self.archive_min.setValue(self.state.config.archive_min_mb)
        self.archive_min.setFixedWidth(130)
        archive.add(FormRow("最小归档体积", "低于该体积的目录不进入冷数据候选。",
                            self.archive_min))
        self.default_mode = SegmentedControl(
            [(MODE_MOVE, "移动归档"), (MODE_LINK, "链接归档"), (MODE_COPY, "仅复制")],
            self.state.config.default_mode,
        )
        archive.add(FormRow("默认归档方式", "移动最省空间；链接保留原路径；复制只备份。",
                            self.default_mode))
        self.strict_verify = Check("严格校验（SHA256）")
        self.strict_verify.setChecked(self.state.config.strict_verify)
        archive.add(FormRow("校验强度", "开启后逐文件计算哈希，更稳但明显更慢。",
                            self.strict_verify))
        self.delete_after_undo = Check("撤销迁移后删除目标副本")
        self.delete_after_undo.setChecked(self.state.config.delete_after_undo)
        archive.add(FormRow("撤销行为", "关闭则回迁后保留目标副本（会占用两份空间）。",
                            self.delete_after_undo))
        self.add(archive)

        # 安全
        safety = GlassCard(18, 6)
        safety.add(card_header("安全与进程", "迁移前后的保护策略"))
        self.check_locks = Toggle(self.state.config.check_locks)
        safety.add(FormRow("检测文件占用", "使用 Windows Restart Manager 检测正在使用目录的程序。",
                           self.check_locks))
        self.confirm_high = Toggle(self.state.config.confirm_high_risk)
        safety.add(FormRow("高风险二次确认", "批量/管理员/删除类操作必须勾选确认。",
                           self.confirm_high))
        self.keep_manifests = QSpinBox()
        self.keep_manifests.setRange(5, 365)
        self.keep_manifests.setSuffix(" 份")
        self.keep_manifests.setValue(int(self.state.config.raw.get(
            "safety", {}).get("keep_manifests", 30) or 30))
        self.keep_manifests.setFixedWidth(110)
        safety.add(FormRow("保留校验清单", "每次操作的文件清单用于回溯；超出数量后自动清理。",
                           self.keep_manifests))
        self.add(safety)

        # 外观
        appearance = GlassCard(18, 6)
        appearance.add(card_header("外观", "字号与动效"))
        font_row = QWidget()
        font_layout = QHBoxLayout(font_row)
        font_layout.setContentsMargins(0, 0, 0, 0)
        font_layout.setSpacing(10)
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(14, 20)
        self.font_slider.setValue(self.state.config.font_size)
        self.font_slider.setFixedWidth(220)
        self.font_value = QLabel(f"{self.state.config.font_size} px")
        self.font_value.setStyleSheet(
            f"color:{theme.BRAND_2};font-family:'Cascadia Mono';font-weight:700;"
        )
        self.font_slider.valueChanged.connect(
            lambda v: self.font_value.setText(f"{v} px"))
        font_layout.addWidget(self.font_slider)
        font_layout.addWidget(self.font_value)
        font_layout.addStretch()
        appearance.add(FormRow("界面字号", "影响全局文字与按钮尺寸。", font_row, stretch=True))
        self.motion = Toggle(self.state.config.motion)
        appearance.add(FormRow("界面动画", "关闭可减少动效，低配机器更流畅。", self.motion))
        self.add(appearance)

        # 数据与关于
        data = GlassCard(18, 8)
        data.add(card_header("数据与关于", f"CDriveCleaner v{__version__} · MIT License"))
        grid = QHBoxLayout()
        grid.setSpacing(10)
        for title, path, icon_name in [
            ("程序数据目录", str(paths.data_dir()), "folder"),
            ("配置与审计", str(self.state.config.path.parent), "database"),
            ("日志目录", str(paths.logs_dir()), "file-archive"),
        ]:
            card = QFrame()
            card.setObjectName("CardInset")
            box = QVBoxLayout(card)
            box.setContentsMargins(12, 10, 12, 10)
            box.setSpacing(4)
            head = QHBoxLayout()
            head.addWidget(IconTile(icon_name, "brand", 26, 13))
            head.addWidget(label(title, "Label"))
            head.addStretch()
            btn = QPushButton("打开")
            btn.setObjectName("Link")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, p=path: open_path(p))
            head.addWidget(btn)
            box.addLayout(head)
            value = QLabel(path)
            value.setWordWrap(True)
            value.setStyleSheet(f"color:{theme.MUT};font-size:12px;")
            box.addWidget(value)
            grid.addWidget(card, 1)
        data.add_layout(grid)

        info = QHBoxLayout()
        info.setSpacing(10)
        info.addWidget(label(f"版本 {__version__}  ·  {paths.app_label()}", "Muted"))
        info.addStretch()
        github = QPushButton("GitHub 项目主页")
        github.setObjectName("Ghost")
        github.setCursor(Qt.PointingHandCursor)
        github.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/Enkrid-Rao/CDriveCleaner")))
        info.addWidget(github)
        self.add(data)
        data.body.addLayout(info)
        self.add(note_frame(
            "本工具会移动文件并修改目录链接。虽然内置清单校验、失败回滚与审计，"
            "仍建议在重要操作前备份；ProgramData / Program Files 会触发 UAC。",
            "warn", "shield"))
        self.add_stretch()

    def _reload_fields(self) -> None:
        cfg = self.state.config
        self.link_root.set_text(cfg.link_root)
        self.archive_root.set_text(cfg.archive_root)
        self.threshold.setValue(cfg.threshold_mb)
        self.temp_days.setValue(cfg.temp_retention_days)
        self.archive_min.setValue(cfg.archive_min_mb)
        self.default_mode.set_value(cfg.default_mode)
        self.strict_verify.setChecked(cfg.strict_verify)
        self.check_locks.setChecked(cfg.check_locks)
        self.confirm_high.setChecked(cfg.confirm_high_risk)
        self.delete_after_undo.setChecked(cfg.delete_after_undo)
        self.font_slider.setValue(cfg.font_size)
        self.font_value.setText(f"{cfg.font_size} px")
        self.motion.setChecked(cfg.motion)

    def _save(self) -> None:
        cfg = self.state.config
        link = os.path.normpath(self.link_root.text().strip())
        archive = os.path.normpath(self.archive_root.text().strip())
        errors = []
        if not (len(link) >= 3 and link[1] == ":"):
            errors.append("迁移容器必须是带盘符的绝对路径。")
        elif link[:1].upper() == "C":
            errors.append("迁移容器不能在 C 盘（源盘）。")
        if not (len(archive) >= 3 and archive[1] == ":"):
            errors.append("默认归档路径必须是带盘符的绝对路径。")
        elif archive[:1].upper() == "C":
            errors.append("默认归档路径不能在系统盘 C。")
        if link.casefold() == archive.casefold():
            errors.append("迁移容器与默认归档路径不能相同。")
        if errors:
            self.error_label.setText("  ".join(errors))
            self.error_label.show()
            return
        self.error_label.hide()
        cfg.link_root = link
        cfg.archive_root = archive
        cfg.threshold_mb = self.threshold.value()
        cfg.temp_retention_days = self.temp_days.value()
        cfg.archive_min_mb = self.archive_min.value()
        cfg.default_mode = self.default_mode.value()
        cfg.strict_verify = self.strict_verify.isChecked()
        cfg.check_locks = self.check_locks.isChecked()
        cfg.confirm_high_risk = self.confirm_high.isChecked()
        cfg.delete_after_undo = self.delete_after_undo.isChecked()
        cfg.font_size = self.font_slider.value()
        cfg.motion = self.motion.isChecked()
        cfg.raw.setdefault("safety", {})["keep_manifests"] = self.keep_manifests.value()
        try:
            cfg.save()
        except OSError as exc:
            self.error_label.setText(f"保存失败：{exc}")
            self.error_label.show()
            return
        theme.set_motion(cfg.motion)
        self.state.apply_config(cfg)
