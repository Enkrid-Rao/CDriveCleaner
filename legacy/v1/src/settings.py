"""设置窗口（GUI 编辑器）。

编辑 config.json 的可视化界面：
  - 通用：清理阈值、目标目录（完整根路径，如 D:\\ 或 D:\\Junctions）、Temp 保留天数、端口
  - 日志：日志保存目录
  - 外观：界面字体 + 字号（带实时预览，改动即生效，取消可还原）

设计：暗色玻璃拟态，左导航 + 右内容（QStackedWidget），与 MainWindow 同一套设计语言。
标题栏使用 setting.svg 作为图标。
布局完全响应式：窗口缩放 / 最大化时内容与卡片自适应，不再裁切在左上角。
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QLineEdit,
    QSpinBox,
    QComboBox,
    QFontComboBox,
    QSlider,
    QStackedWidget,
    QScrollArea,
    QFileDialog,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QApplication,
    QMessageBox,
)

from . import config, gui_styles as gs
from .logger import OperationLog
from ._version import __version__
from .window_resize import ResizableFrameless

# SVG 图标（带降级）
try:
    from PySide6.QtSvg import QSvgRenderer
    _HAS_SVG = True
except Exception:  # pragma: no cover
    _HAS_SVG = False


# ============================================================
# 设置窗口专属 QSS（追加在全局 QSS 之后，仅作用于设置控件）
# ============================================================

SETTINGS_QSS = """
/* ===== 窗口外框：可见粗边框（替代 1px 无边框观感）=====
   不再依赖 WS_THICKFRAME 那 1px 看不见的 sizing border，
   直接用 QSS 画一圈 2px 的可见边框，简单可靠、与暗色风格统一。
   WM_NCCALCSIZE 已不拦截，客户区由系统正确计算，输入框必可见。 */
QDialog#SettingsWindow {
    background: #0b1120;
    border: 2px solid rgba(125, 160, 255, 0.32);
}

/* ===== 输入框 ===== */
QLineEdit {
    background: rgba(11, 17, 32, 0.85);
    border: 1px solid rgba(125, 160, 255, 0.18);
    border-radius: 9px;
    padding: 7px 11px;
    color: #e6edf3;
    font-size: 13px;
    selection-background-color: #6366f1;
}
QLineEdit:focus { border: 1px solid #8b5cf6; }
QLineEdit:disabled { color: #5d6776; }

/* ===== 数值框 ===== */
QSpinBox {
    background: rgba(11, 17, 32, 0.85);
    border: 1px solid rgba(125, 160, 255, 0.18);
    border-radius: 9px;
    padding: 6px 10px;
    color: #e6edf3;
    font-size: 13px;
}
QSpinBox:focus { border: 1px solid #8b5cf6; }
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 18px;
    border: none;
    background: transparent;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: rgba(99,102,241,0.18); }

/* ===== 下拉框（含字体选择）===== */
QComboBox, QFontComboBox {
    background: rgba(11, 17, 32, 0.85);
    border: 1px solid rgba(125, 160, 255, 0.18);
    border-radius: 9px;
    padding: 6px 10px;
    color: #e6edf3;
    font-size: 13px;
}
QComboBox:focus, QFontComboBox:focus { border: 1px solid #8b5cf6; }
QComboBox::drop-down, QFontComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow, QFontComboBox::down-arrow {
    width: 0px;
    height: 0px;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #8b95a7;
    subcontrol-origin: drop-down;
    subcontrol-position: center;
}
QComboBox::down-arrow:hover, QFontComboBox::down-arrow:hover {
    border-top-color: #c7d2fe;
}
QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {
    background: #0f172a;
    color: #e6edf3;
    selection-background-color: #6366f1;
    border: 1px solid rgba(125, 160, 255, 0.28);
    outline: 0;
}

/* ===== 滑块（标准写法，单一 handle，不与原生样式叠加产生双圆点）===== */
QSlider {
    min-height: 22px;
}
QSlider::groove:horizontal {
    border: 1px solid rgba(125, 160, 255, 0.18);
    height: 6px;
    background: rgba(125, 160, 255, 0.12);
    border-radius: 3px;
    margin: 0;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #6366f1, stop:1 #8b5cf6);
    border: 1px solid rgba(125, 160, 255, 0.18);
    height: 6px;
    border-radius: 3px;
}
QSlider::add-page:horizontal {
    background: rgba(125, 160, 255, 0.12);
    border: 1px solid rgba(125, 160, 255, 0.18);
    height: 6px;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 #ffffff, stop:1 #c7d2fe);
    border: 2px solid #8b5cf6;
    width: 16px;
    height: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { border: 2px solid #6366f1; }

/* ===== 侧边导航 ===== */
QFrame#NavPanel {
    background: rgba(11, 17, 32, 0.55);
    border-right: 1px solid rgba(125, 160, 255, 0.12);
}
QPushButton#NavBtn {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 11px 14px;
    text-align: left;
    color: #8b97a7;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#NavBtn:hover { background: rgba(36, 48, 74, 0.7); color: #e6edf3; }
QPushButton#NavBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,102,241,0.30), stop:1 rgba(139,92,246,0.30));
    color: #ffffff;
    border: 1px solid rgba(139, 92, 246, 0.45);
}

/* ===== 设置行 ===== */
QFrame#SettingRow { background: transparent; }
QLabel#RowTitle { color: #e6edf3; font-size: 13px; font-weight: 600; }
QLabel#RowHint { color: #8b97a7; font-size: 11px; }
QLabel#RowPreview {
    color: #2dd4bf;
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
}
QLabel#RowWarn { color: #d29922; font-size: 11px; }
QLabel#RowError { color: #f85149; font-size: 11px; font-weight: 600; }

/* ===== 页头 ===== */
QLabel#PageTitle { color: #e6edf3; font-size: 17px; font-weight: 800; }
QLabel#PageHint { color: #8b97a7; font-size: 12px; }

/* ===== 字体预览卡 ===== */
QFrame#FontPreview {
    background: rgba(7, 11, 20, 0.6);
    border: 1px solid rgba(125, 160, 255, 0.18);
    border-radius: 12px;
}

/* ===== 底部栏 ===== */
QFrame#SettingsFooter {
    background: rgba(11, 17, 32, 0.6);
    border-top: 1px solid rgba(125, 160, 255, 0.12);
}
"""


def _svg_pixmap(path: str, size: int) -> QPixmap:
    """用 QSvgRenderer 把 SVG 渲染成指定尺寸的 QPixmap；不可用则返回空。"""
    if not _HAS_SVG or not path or not os.path.exists(path):
        return QPixmap()
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QPixmap()
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    renderer.render(p, pix.rect())
    p.end()
    return pix


# ============================================================
# 设置窗口
# ============================================================

class SettingsWindow(ResizableFrameless, QDialog):
    """设置窗口（模态对话框）。布局响应式，可缩放 / 最大化。"""

    settings_applied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SettingsWindow")
        self.setWindowTitle("设置")
        # 采用 Qt.Dialog：系统级模态对话框，事件循环由 exec() 托管，
        # 模态期间系统级屏蔽其他窗口输入 → 连点齿轮不会排队堆积（防锁死）。
        # 配合 FramelessWindowHint 去掉系统标题栏，自绘标题栏 + 无边框观感。
        # WS_THICKFRAME（四边缩放）由 ResizableFrameless.showEvent 幂等应用，
        # 不再在此处提前改原生样式（避免在 exec() 前干扰 Qt.Dialog 几何）。
        # 输入框可见性由 window_resize.WM_NCCALCSIZE 把客户区显式设为整窗保证。
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint
        )
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        # 默认尺寸更宽松；最小尺寸保证所有内容可见（配合滚动）
        self.resize(880, 640)
        self.setMinimumSize(560, 440)

        # 深拷贝当前配置作为草稿（取消时不落盘）
        self._draft: dict[str, Any] = json.loads(json.dumps(config.RAW_CONFIG))

        # 字体实时预览/还原
        app = QApplication.instance()
        self._orig_qss = app.styleSheet() if app else ""
        self._orig_font = app.font() if app else QFont()

        # 控件引用
        self._widgets: dict[str, Any] = {}

        # 标题栏拖拽
        self._drag_pos: QPoint | None = None

        self._build_ui()
        self._apply_qss(self._current_family(), self._current_size())
        self._center_on_parent()

    # ---------- 字体辅助 ----------

    def _current_family(self) -> str:
        fam, _ = gs.resolve_ui_font(
            self._draft.get("ui", {}).get("font_family", "") or "",
            self._draft.get("ui", {}).get("font_size", 0) or 0,
        )
        return fam

    def _current_size(self) -> int:
        _, size = gs.resolve_ui_font(
            self._draft.get("ui", {}).get("font_family", "") or "",
            self._draft.get("ui", {}).get("font_size", 0) or 0,
        )
        return size

    def _apply_qss(self, family: str, size: int) -> None:
        app = QApplication.instance()
        if app is None:
            return
        qss = gs.build_global_qss(family, size) + SETTINGS_QSS
        app.setStyleSheet(qss)
        app.setFont(QFont(family, size))

    # ---------- UI 构建 ----------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 注意：不再使用 QGraphicsDropShadowEffect（与 WS_THICKFRAME 冲突，
        # 会导致 Win32 绘制异常）。WS_THICKFRAME 已自带原生窗口阴影。

        # 标题栏
        root.addWidget(self._build_title_bar())

        # 主体：左导航 + 右内容
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_nav())
        body.addWidget(self._build_content(), 1)
        root.addLayout(body, 1)

        # 底部栏
        root.addWidget(self._build_footer())

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setObjectName("TitleBar")
        bar.setStyleSheet("background: transparent; border-bottom: 1px solid rgba(125,160,255,0.12);")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(10)

        # setting.svg 图标
        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        pix = _svg_pixmap(self._find_setting_icon(), 24)
        if pix.isNull():
            icon_label.setText("⚙")
            icon_label.setStyleSheet("font-size:18px;color:#8b5cf6;")
        else:
            icon_label.setPixmap(pix)
        layout.addWidget(icon_label)

        title = QLabel("设置")
        title.setObjectName("TitleAppName")
        title.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:700;")
        layout.addWidget(title)

        ver = QLabel(f"v{__version__}")
        ver.setObjectName("TitleVersion")
        ver.setStyleSheet("color:#5d6776;font-size:11px;font-weight:600;"
                          "font-family:'JetBrains Mono','Consolas',monospace;")
        layout.addWidget(ver)

        layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("BtnClose")
        close_btn.setFixedSize(34, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton#BtnClose{border:none;border-radius:6px;background:transparent;"
            "color:#8b97a7;font-size:12px;padding:4px;}"
            "QPushButton#BtnClose:hover{background:rgba(248,81,73,0.85);color:white;}"
        )
        close_btn.clicked.connect(self.reject)
        layout.addWidget(close_btn)
        return bar

    def _build_nav(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("NavPanel")
        panel.setFixedWidth(200)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(6)

        items = [
            ("general", "🧩", "通用"),
            ("logging", "📝", "日志"),
            ("appearance", "🎨", "外观"),
        ]
        self._nav_btns: dict[str, QPushButton] = {}
        for key, icon, label in items:
            btn = QPushButton(f"{icon}  {label}")
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._switch_page(k))
            self._nav_btns[key] = btn
            layout.addWidget(btn)

        layout.addStretch()
        self._nav_btns["general"].setChecked(True)
        return panel

    def _build_content(self) -> QWidget:
        self.stack = QStackedWidget()
        self.stack.setObjectName("SettingsStack")
        self.stack.setStyleSheet("background:transparent;border:none;")
        # 关键：让 stack 在 body 中横向 / 纵向撑满
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.stack.addWidget(self._page_general())
        self.stack.addWidget(self._page_logging())
        self.stack.addWidget(self._page_appearance())
        return self.stack

    def _switch_page(self, key: str) -> None:
        order = ["general", "logging", "appearance"]
        for k, btn in self._nav_btns.items():
            btn.setChecked(k == key)
        self.stack.setCurrentIndex(order.index(key))

    # ---------- 通用页 ----------

    def _page_general(self) -> QWidget:
        page = self._scroll_page("通用设置", "迁移阈值、目标位置与 Web 服务端口")
        card = self._card()
        card_layout = self._card_layout(card)

        # 清理阈值
        thr = self._draft.get("threshold_mb", 100)
        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 2048)
        slider.setSingleStep(10)
        slider.setValue(int(thr))
        slider.setMinimumWidth(240)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        spin = QSpinBox()
        spin.setRange(0, 2048)
        spin.setValue(int(thr))
        spin.setSuffix(" MB")
        spin.setFixedWidth(90)
        slider.valueChanged.connect(spin.setValue)
        spin.valueChanged.connect(slider.setValue)
        self._widgets["threshold"] = spin

        val_label = QLabel(f"{int(thr)} MB")
        val_label.setStyleSheet(f"color:{gs.BRAND_2};font-weight:700;"
                                f"font-family:'JetBrains Mono','Consolas',monospace;font-size:13px;")
        slider.valueChanged.connect(lambda v: val_label.setText(f"{v} MB"))
        # stretch=2：滑块在右侧区域自适应拉伸，窗口变宽时滑块随之变长
        thr_row = self._row("清理阈值", "仅展示 / 迁移超过该大小的目录。",
                            self._hbox([slider, val_label, spin]), stretch=2)
        card_layout.addWidget(thr_row)

        # 目标目录
        base = self._draft.get("target_base", "D:")
        base_edit = QLineEdit(base)
        base_edit.setPlaceholderText(r"例如 D:\ 或 D:\Junctions")
        base_edit.setMinimumWidth(240)
        base_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        base_edit.textChanged.connect(self._on_target_changed)
        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("GhostBtn")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(lambda: self._browse_dir(base_edit))
        self._widgets["target_base"] = base_edit

        preview = QLabel("")
        preview.setObjectName("RowPreview")
        preview.setWordWrap(True)
        self._widgets["target_preview"] = preview
        warn = QLabel("")
        warn.setObjectName("RowWarn")
        warn.setWordWrap(True)
        self._widgets["target_warn"] = warn
        err = QLabel("")
        err.setObjectName("RowError")
        err.setWordWrap(True)
        self._widgets["target_error"] = err

        target_row = self._row(
            "目标目录", "迁移数据的存放根路径。支持盘符或任意子目录。",
            self._vbox([self._hbox([base_edit, browse_btn]), preview, warn, err]))
        card_layout.addWidget(target_row)
        # 初始化预览/校验
        self._on_target_changed(base)

        # Temp 保留天数
        days = self._draft.get("temp_retention_days", 1)
        days_spin = QSpinBox()
        days_spin.setRange(0, 365)
        days_spin.setValue(int(days))
        days_spin.setSuffix(" 天")
        days_spin.setFixedWidth(100)
        self._widgets["temp_days"] = days_spin
        card_layout.addWidget(self._row(
            "临时文件保留天数", "清理 Temp 时，仅删除超过该天数的文件。0 表示全部清理。",
            days_spin))

        # 端口
        port = self._draft.get("port", 8765)
        port_spin = QSpinBox()
        port_spin.setRange(1, 65535)
        port_spin.setValue(int(port))
        port_spin.setFixedWidth(110)
        self._widgets["port"] = port_spin
        card_layout.addWidget(self._row(
            "Web 服务端口", "Web 服务模式（独立程序 CDriveCleaner_web）启动时使用的端口。", port_spin))

        page.content_layout.addWidget(card)
        page.content_layout.addStretch()
        return page

    # ---------- 日志页 ----------

    def _page_logging(self) -> QWidget:
        page = self._scroll_page("日志设置", "操作日志的保存位置")
        card = self._card()
        card_layout = self._card_layout(card)

        log_dir = self._draft.get("log_dir", "") or ""
        edit = QLineEdit(log_dir)
        edit.setPlaceholderText("留空则使用程序目录下 logs\\")
        edit.setMinimumWidth(260)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("GhostBtn")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.clicked.connect(lambda: self._browse_dir(edit, for_log=True))
        self._widgets["log_dir"] = edit

        resolved = QLabel("")
        resolved.setObjectName("RowPreview")
        resolved.setWordWrap(True)
        self._widgets["log_resolved"] = resolved
        self._update_log_resolved()

        card_layout.addWidget(self._row(
            "日志保存目录", "操作日志按天写入该目录。留空使用默认位置。",
            self._vbox([self._hbox([edit, browse_btn]), resolved])))
        edit.textChanged.connect(self._update_log_resolved)

        page.content_layout.addWidget(card)
        page.content_layout.addStretch()
        return page

    # ---------- 外观页 ----------

    def _page_appearance(self) -> QWidget:
        page = self._scroll_page("外观设置", "界面字体与字号（改动即时预览）")
        card = self._card()
        card_layout = self._card_layout(card)

        # 字体
        font_combo = QFontComboBox()
        font_combo.setMinimumWidth(280)
        font_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 前置「自动」项
        font_combo.insertItem(0, "自动（推荐 JetBrains Mono）")
        font_combo.setItemData(0, "")
        cur_family = self._draft.get("ui", {}).get("font_family", "") or ""
        if cur_family:
            idx = font_combo.findText(cur_family)
            font_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            font_combo.setCurrentIndex(0)
        self._widgets["font_combo"] = font_combo

        size_spin = QSpinBox()
        size_spin.setRange(9, 20)
        size_spin.setValue(self._current_size())
        size_spin.setSuffix(" px")
        size_spin.setFixedWidth(100)
        self._widgets["font_size"] = size_spin

        def _on_font_change() -> None:
            fam = self._selected_font_family()
            self._draft.setdefault("ui", {})["font_family"] = fam
            self._draft["ui"]["font_size"] = size_spin.value()
            self._apply_qss(self._effective_family(), size_spin.value())
            self._update_preview()

        font_combo.currentIndexChanged.connect(_on_font_change)
        size_spin.valueChanged.connect(_on_font_change)

        card_layout.addWidget(self._row(
            "界面字体", "推荐 JetBrains Mono（等宽、极客感、数字对齐不抖动）。", font_combo))
        card_layout.addWidget(self._row("字号", "基础字号，部分标题会更大。", size_spin))

        # 实时预览
        preview = QFrame()
        preview.setObjectName("FontPreview")
        pv_layout = QVBoxLayout(preview)
        pv_layout.setContentsMargins(16, 14, 16, 14)
        pv_layout.setSpacing(8)
        pv_title = QLabel("预览")
        pv_title.setObjectName("SectionHint")
        pv_sample = QLabel("磁盘概览  ·  C盘可用 128.4 GB  ·  可释放 12.8 GB")
        pv_sample.setObjectName("DirSize")
        pv_sample.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:700;")
        pv_layout.addWidget(pv_title)
        pv_layout.addWidget(pv_sample)
        self._widgets["font_preview"] = pv_sample
        card_layout.addWidget(preview)
        self._update_preview()

        page.content_layout.addWidget(card)
        page.content_layout.addStretch()
        return page

    # ---------- 底部栏 ----------

    def _build_footer(self) -> QWidget:
        footer = QFrame()
        footer.setObjectName("SettingsFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        hint = QLabel("改动即时生效预览，保存后写入 config.json 并热重载。")
        hint.setObjectName("SectionHint")
        layout.addWidget(hint)
        layout.addStretch()

        cancel = QPushButton("取消")
        cancel.setObjectName("GhostBtn")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

        save = QPushButton("保存并应用")
        save.setObjectName("PrimaryBtn")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._on_save)
        layout.addWidget(save)
        return footer

    # ---------- 辅助构件 ----------

    def _scroll_page(self, title: str, hint: str) -> QWidget:
        # page 持有 scroll，scroll 持有 inner；避免局部变量被 GC 导致 inner 被删除
        page = QWidget()
        # 关键：page 在 QStackedWidget 中必须 Expanding，否则窗口缩小内容被挤到左上角
        page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background:transparent;border:none;")

        inner = QWidget()
        # 关键：inner 撑满 viewport，内容随窗口宽度自适应
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        inner.setMinimumWidth(0)
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(20, 18, 20, 20)
        inner_layout.setSpacing(16)

        t = QLabel(title)
        t.setObjectName("PageTitle")
        h = QLabel(hint)
        h.setObjectName("PageHint")
        inner_layout.addWidget(t)
        inner_layout.addWidget(h)

        scroll.setWidget(inner)
        page_layout.addWidget(scroll)

        # 暴露内部布局供各页添加卡片
        page.content_layout = inner_layout
        return page

    def _card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def _card_layout(self, card: QFrame) -> QVBoxLayout:
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        return layout

    def _row(self, title: str, hint: str, control: QWidget, stretch: int = 0) -> QFrame:
        row = QFrame()
        row.setObjectName("SettingRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 6, 4, 6)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("RowTitle")
        h = QLabel(hint)
        h.setObjectName("RowHint")
        h.setWordWrap(True)
        left.addWidget(t)
        left.addWidget(h)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        # 当右侧需要拉伸（如滑块行）时，让控件 Expanding 填满
        sp = QSizePolicy.Expanding if stretch else QSizePolicy.Maximum
        control.setSizePolicy(sp, QSizePolicy.Preferred)
        if stretch:
            right.addWidget(control)
        else:
            right.addWidget(control, alignment=Qt.AlignRight)
        layout.addLayout(right, stretch)
        return row

    @staticmethod
    def _hbox(widgets: list[QWidget]) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for item in widgets:
            layout.addWidget(item)
        return w

    @staticmethod
    def _vbox(widgets: list[QWidget]) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for item in widgets:
            layout.addWidget(item)
        return w

    # ---------- 逻辑 ----------

    def _selected_font_family(self) -> str:
        combo = self._widgets["font_combo"]
        data = combo.itemData(combo.currentIndex())
        if data == "" or data is None:
            return ""
        return combo.currentFont().family()

    def _effective_family(self) -> str:
        fam = self._selected_font_family()
        if not fam:
            return gs.detect_font_family()
        return fam

    def _update_preview(self) -> None:
        preview = self._widgets.get("font_preview")
        if not preview:
            return
        fam = self._effective_family()
        size = self._widgets["font_size"].value()
        f = QFont(fam, size)
        preview.setFont(f)

    def _update_log_resolved(self) -> None:
        label = self._widgets.get("log_resolved")
        if not label:
            return
        raw = self._widgets["log_dir"].text().strip()
        if not raw:
            label.setText("当前：程序目录下的 logs\\")
        else:
            resolved = config._expand_path(raw, config._BASE_PLACEHOLDERS)
            label.setText(f"当前：{resolved}")

    def _on_target_changed(self, text: str) -> None:
        base = text.strip()
        preview = self._widgets["target_preview"]
        warn = self._widgets["target_warn"]
        err = self._widgets["target_error"]
        edit = self._widgets["target_base"]

        norm = config._normalize_base(base, config.RAW_CONFIG.get("target_drive", "D"))
        # 预览：举例一个真实存放路径
        example = f"{norm}\\AppData\\Local"
        preview.setText(f"实际存放路径示例：{example}")

        warn.setText("")
        err.setText("")
        edit.setStyleSheet("")  # 恢复默认（QSS 控制）
        self._target_valid = True

        if not base:
            err.setText("❌ 目标目录不能为空")
            self._target_valid = False
        elif norm[:1].upper() == "C" and (len(norm) < 2 or norm[1] == ":"):
            err.setText("❌ 不能把数据迁移到 C 盘（与源盘相同，无意义且有风险）")
            self._target_valid = False
        elif not (len(norm) >= 2 and norm[1] == ":" and norm[0].isalpha()) and not norm.startswith("\\\\"):
            err.setText("❌ 请输入绝对路径（如 D:\\ 或 D:\\Junctions）")
            self._target_valid = False
        elif norm[:1].upper() == "C":
            warn.setText("⚠️ 目标在 C 盘，建议改用其他盘（如 D:\\Junctions）")
            self._target_valid = False

    def _browse_dir(self, edit: QLineEdit, for_log: bool = False) -> None:
        start = edit.text().strip() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, "选择目录", start)
        if path:
            edit.setText(path)

    def _on_save(self) -> None:
        # 校验目标目录
        if not getattr(self, "_target_valid", True):
            QMessageBox.warning(self, "无法保存", "目标目录无效，请修正后再保存。")
            return

        # 写回草稿
        self._draft["threshold_mb"] = self._widgets["threshold"].value()
        self._draft["target_base"] = self._widgets["target_base"].text().strip()
        self._draft["temp_retention_days"] = self._widgets["temp_days"].value()
        self._draft["port"] = self._widgets["port"].value()
        self._draft["log_dir"] = self._widgets["log_dir"].text().strip()
        self._draft.setdefault("ui", {})
        self._draft["ui"]["font_family"] = self._selected_font_family()
        self._draft["ui"]["font_size"] = self._widgets["font_size"].value()

        # 落盘 + 热重载
        config.save_config(self._draft)
        config.reload_config()

        # 日志目录热切换
        OperationLog().reconfigure(self._draft["log_dir"])

        self.settings_applied.emit()
        self.accept()

    def reject(self) -> None:
        # 还原字体（取消不生效）
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(self._orig_qss)
            app.setFont(self._orig_font)
        super().reject()

    # ---------- 标题栏拖拽 / 双击最大化 ----------

    def _center_on_parent(self) -> None:
        parent = self.parent()
        if parent is None:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(geo.center() - self.rect().center())
            return
        pg = parent.geometry()
        self.move(pg.center() - self.rect().center())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and event.position().y() <= 48:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # 双击标题栏：最大化 / 还原
        if event.position().y() <= 48:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    @staticmethod
    def _find_setting_icon() -> str:
        candidates = []
        if getattr(sys, "frozen", False):
            base = os.path.dirname(sys.executable)
            candidates = [
                os.path.join(base, "assets", "setting.svg"),
                os.path.join(sys._MEIPASS, "assets", "setting.svg"),
            ]
        else:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidates = [os.path.join(root, "assets", "setting.svg")]
        for c in candidates:
            if os.path.exists(c):
                return c
        return ""
