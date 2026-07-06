"""PySide6 桌面 GUI 主模块。

原生窗口应用，复用 src.scanner / src.migrator / src.admin_ops 后端逻辑。
所有耗时操作在 QThread 工作线程中执行，UI 始终丝滑不卡顿。

公开入口：launch()
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QTimer,
    QSize,
    QPoint,
    QRect,
    QPropertyAnimation,
    QEasingCurve,
)
from PySide6.QtGui import (
    QIcon,
    QColor,
    QPainter,
    QBrush,
    QLinearGradient,
    QPainterPath,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QPixmap,
    QPen,
    QMouseEvent,
    QPaintEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QMessageBox,
    QSpacerItem,
)

from . import gui_styles as gs
from .logger import OperationLog, LEVEL_COLORS
from .scanner import scan_all, get_drive_info
from .migrator import migrate_dir, undo_junction, clean_temp
from .admin_ops import (
    generate_admin_bat,
    elevate_and_run,
    get_junction_target,
    read_admin_result,
)
from ._version import __version__


# ============================================================
# 后端工作线程
# ============================================================

class ScanWorker(QThread):
    """扫描工作线程。"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, threshold_mb: int = 100) -> None:
        super().__init__()
        self.threshold_mb = threshold_mb

    def run(self) -> None:
        try:
            result = scan_all(self.threshold_mb)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class MigrateWorker(QThread):
    """迁移工作线程。"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, source: str, dest: str, name: str) -> None:
        super().__init__()
        self.source = source
        self.dest = dest
        self.name = name

    def run(self) -> None:
        try:
            _, c_free, d_free = get_drive_info()
            result = migrate_dir(self.source, self.dest, self.name)
            result["cFreeGB"] = c_free
            result["dFreeGB"] = d_free
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class UndoWorker(QThread):
    """撤销迁移工作线程。"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, source: str, name: str) -> None:
        super().__init__()
        self.source = source
        self.name = name

    def run(self) -> None:
        try:
            _, c_free, d_free = get_drive_info()
            result = undo_junction(self.source, self.name)
            result["cFreeGB"] = c_free
            result["dFreeGB"] = d_free
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class CleanTempWorker(QThread):
    """清理 Temp 工作线程。"""
    finished = Signal(dict)
    error = Signal(str)

    def run(self) -> None:
        try:
            _, c_free, d_free = get_drive_info()
            result = clean_temp()
            result["cFreeGB"] = c_free
            result["dFreeGB"] = d_free
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class AdminMigrateWorker(QThread):
    """管理员迁移：生成 bat + 触发 UAC。"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, source: str, dest: str, name: str, size_mb: float) -> None:
        super().__init__()
        self.source = source
        self.dest = dest
        self.name = name
        self.size_mb = size_mb

    def run(self) -> None:
        try:
            bat_path, bat_name, result_file = generate_admin_bat(
                self.name, self.source, self.dest, self.size_mb, "migrate"
            )
            uac_ok = elevate_and_run(bat_path)
            self.finished.emit({
                "success": True,
                "uacTriggered": uac_ok,
                "scriptFile": bat_name,
                "scriptPath": bat_path,
                "resultFile": result_file,
                "name": self.name,
            })
        except Exception as exc:
            self.error.emit(str(exc))


class AdminUndoWorker(QThread):
    """管理员撤销：查 target → 生成 bat → 触发 UAC。"""
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, source: str, name: str, dest: str = "") -> None:
        super().__init__()
        self.source = source
        self.name = name
        self.dest = dest

    def run(self) -> None:
        try:
            dest = self.dest
            if not dest:
                target = get_junction_target(self.source)
                if target:
                    dest = target
            if not dest:
                self.error.emit("无法确定 Junction 目标路径")
                return
            bat_path, bat_name, result_file = generate_admin_bat(
                self.name, self.source, dest, 0, "undo"
            )
            uac_ok = elevate_and_run(bat_path)
            self.finished.emit({
                "success": True,
                "uacTriggered": uac_ok,
                "scriptFile": bat_name,
                "scriptPath": bat_path,
                "resultFile": result_file,
                "name": self.name,
            })
        except Exception as exc:
            self.error.emit(str(exc))


# ============================================================
# 自定义标题栏
# ============================================================

class TitleBar(QWidget):
    """无边框窗口的自定义标题栏，支持拖动移动 + 最小化/最大化/关闭。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setObjectName("TitleBar")

        self._parent = parent
        self._pressed = False
        self._press_pos = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(10)

        # Logo（渐变小方块）
        self.logo = QLabel()
        self.logo.setFixedSize(26, 26)
        self._draw_logo()
        layout.addWidget(self.logo)

        # 应用名
        self.title = QLabel("C盘瘦身助手")
        self.title.setObjectName("TitleAppName")
        layout.addWidget(self.title)

        # 版本号
        self.version = QLabel(f"v{__version__}")
        self.version.setObjectName("TitleVersion")
        layout.addWidget(self.version)

        layout.addStretch()

        # 窗口控制按钮
        self.btn_min = QPushButton("—")
        self.btn_min.setObjectName("BtnMin")
        self.btn_min.setFixedSize(36, 26)
        self.btn_min.setCursor(Qt.PointingHandCursor)
        self.btn_min.clicked.connect(self._parent.showMinimized)
        layout.addWidget(self.btn_min)

        self.btn_max = QPushButton("▢")
        self.btn_max.setObjectName("BtnMax")
        self.btn_max.setFixedSize(36, 26)
        self.btn_max.setCursor(Qt.PointingHandCursor)
        self.btn_max.clicked.connect(self._toggle_max)
        layout.addWidget(self.btn_max)

        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("BtnClose")
        self.btn_close.setFixedSize(36, 26)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self._parent.close)
        layout.addWidget(self.btn_close)

    def _draw_logo(self) -> None:
        """绘制渐变 Logo。"""
        pix = QPixmap(26, 26)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, 26, 26)
        grad.setColorAt(0, QColor(gs.BRAND))
        grad.setColorAt(1, QColor(gs.BRAND_2))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, 26, 26, 7, 7)
        # 中心字母 C
        p.setPen(QColor("white"))
        font = QFont("Segoe UI", 12, QFont.Bold)
        p.setFont(font)
        p.drawText(pix.rect(), Qt.AlignCenter, "C")
        p.end()
        self.logo.setPixmap(pix)

    def _toggle_max(self) -> None:
        if self._parent.isMaximized():
            self._parent.showNormal()
        else:
            self._parent.showMaximized()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._press_pos = event.globalPosition().toPoint() - self._parent.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pressed and (event.buttons() & Qt.LeftButton):
            if self._parent.isMaximized():
                # 最大化状态下拖动 → 先恢复再移动
                self._parent.showNormal()
                # 鼠标位置映射到恢复后的窗口
                self._press_pos = QPoint(self._parent.width() // 2, 22)
            self._parent.move(event.globalPosition().toPoint() - self._press_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._pressed = False
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._toggle_max()


# ============================================================
# 统计卡片
# ============================================================

class StatCard(QFrame):
    """概览统计卡片，支持数值滚动动画。"""

    def __init__(self, label: str, value: str = "0", color_class: str = "",
                 icon: str = "") -> None:
        super().__init__()
        self.setObjectName("StatCard")
        self.setFixedHeight(92)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 90))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        # 图标 + 标签行
        top = QHBoxLayout()
        top.setSpacing(6)
        if icon:
            ic = QLabel(icon)
            ic.setStyleSheet(f"font-size:16px;color:{gs.TEXT_MUT};")
            top.addWidget(ic)
        lbl = QLabel(label)
        lbl.setObjectName("StatLabel")
        top.addWidget(lbl)
        top.addStretch()
        layout.addLayout(top)

        # 数值
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        if color_class:
            self.value_label.setObjectName(color_class)
        layout.addWidget(self.value_label)

        self._current_value = 0.0

    def set_value_animated(self, target: float, suffix: str = "",
                           decimals: int = 1) -> None:
        """数值滚动动画。"""
        def _update(v: float) -> None:
            if decimals == 0:
                text = f"{int(round(v))}{suffix}"
            else:
                text = f"{v:.{decimals}f}{suffix}"
            self.value_label.setText(text)

        # 停掉上一次未完成的动画
        if hasattr(self, "_value_anim") and self._value_anim:
            self._value_anim.stop()
        self._value_anim = gs.animate_value(_update, 0.0, target, duration=900)


# ============================================================
# 目录卡片
# ============================================================

class DirCard(QFrame):
    """单个目录卡片，显示大小/路径/操作按钮。"""

    migrate_clicked = Signal(str, str, str, float)  # source, dest, name, sizeMB
    undo_clicked = Signal(str, str)                 # source, name
    admin_migrate_clicked = Signal(str, str, str, float)
    admin_undo_clicked = Signal(str, str)

    def __init__(self, item: dict[str, Any]) -> None:
        super().__init__()
        self.setObjectName("DirCard")
        self.item = item
        self.setCursor(Qt.PointingHandCursor)

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        name = item.get("name", "")
        size_mb = item.get("sizeMB", 0)
        path = item.get("path", "")
        dest = item.get("dest", "")
        zone = item.get("zone", "")
        needs_admin = item.get("needsAdmin", False)
        is_junction = item.get("isJunction", False)
        target = item.get("target", "")

        # 左侧：图标 + 名称 + 路径
        left = QVBoxLayout()
        left.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        nm = QLabel(name)
        nm.setObjectName("DirName")
        name_row.addWidget(nm)

        # 区域标签
        zone_label = QLabel(zone)
        zone_label.setObjectName("DirZone")
        name_row.addWidget(zone_label)

        if is_junction:
            tag = QLabel("✓ 已迁移")
            tag.setObjectName("JunctionTag")
            name_row.addWidget(tag)
        elif needs_admin:
            tag = QLabel("🔑 需管理员")
            tag.setObjectName("AdminTag")
            name_row.addWidget(tag)

        name_row.addStretch()
        left.addLayout(name_row)

        # 路径展示：已迁移显示 C→D 映射，可迁移显示 C 盘原路径
        if is_junction and target:
            # C盘路径 → D盘真实路径
            path_row = QHBoxLayout()
            path_row.setSpacing(6)
            c_label = QLabel(path)
            c_label.setObjectName("DirPath")
            arrow = QLabel("→")
            arrow.setStyleSheet(f"color:{gs.TEAL};font-size:11px;font-weight:bold;")
            d_label = QLabel(target)
            d_label.setObjectName("DirPath")
            d_label.setStyleSheet(f"color:{gs.TEAL};")
            path_row.addWidget(c_label)
            path_row.addWidget(arrow)
            path_row.addWidget(d_label)
            path_row.addStretch()
            left.addLayout(path_row)
        else:
            pt = QLabel(path)
            pt.setObjectName("DirPath")
            pt.setWordWrap(False)
            left.addWidget(pt)
        layout.addLayout(left, 1)

        # 右侧：大小 + 按钮
        right = QHBoxLayout()
        right.setSpacing(10)

        if is_junction:
            # 已迁移不显示大小，直接放撤销按钮
            btn = QPushButton("撤销迁移")
            btn.setObjectName("UndoBtn")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda: self.undo_clicked.emit(path, name)
            )
            right.addWidget(btn)
            if needs_admin:
                abtn = QPushButton("🔑 撤销")
                abtn.setObjectName("AdminBtn")
                abtn.setCursor(Qt.PointingHandCursor)
                abtn.clicked.connect(
                    lambda: self.admin_undo_clicked.emit(path, name)
                )
                right.addWidget(abtn)
        else:
            # 可迁移：显示大小 + 迁移按钮
            sz = QLabel(self._fmt_size(size_mb))
            sz.setObjectName("DirSize")
            right.addWidget(sz)

            btn_text = "🔑 管理员迁移" if needs_admin else "迁移到 D 盘"
            btn = QPushButton(btn_text)
            btn.setObjectName("AdminBtn" if needs_admin else "ActionBtn")
            btn.setCursor(Qt.PointingHandCursor)
            if needs_admin:
                btn.clicked.connect(
                    lambda: self.admin_migrate_clicked.emit(path, dest, name, size_mb)
                )
            else:
                btn.clicked.connect(
                    lambda: self.migrate_clicked.emit(path, dest, name, size_mb)
                )
            right.addWidget(btn)

        layout.addLayout(right)

    @staticmethod
    def _fmt_size(size_mb: float) -> str:
        """格式化大小：>=1024MB 显示 GB。"""
        if size_mb >= 1024:
            return f"{size_mb / 1024:.2f} GB"
        return f"{size_mb:.0f} MB"


# ============================================================
# Toast 通知
# ============================================================

class Toast(QFrame):
    """浮层 Toast 通知，自动消失。"""

    def __init__(self, text: str, kind: str = "info",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 颜色映射
        colors = {
            "success": (gs.GREEN, "✓"),
            "error": (gs.RED, "✕"),
            "warn": (gs.YELLOW, "⚠"),
            "info": (gs.BLUE, "ℹ"),
        }
        color, icon = colors.get(kind, colors["info"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        ic = QLabel(icon)
        ic.setObjectName("ToastIcon")
        ic.setStyleSheet(f"color:{color};font-size:16px;font-weight:bold;")
        layout.addWidget(ic)

        tx = QLabel(text)
        tx.setObjectName("ToastText")
        layout.addWidget(tx)

        self.adjustSize()

        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        # 入场动画
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.0)
        self.setGraphicsEffect(eff)
        self._opacity_eff = eff

        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._in_anim = anim

        # 3 秒后淡出消失
        QTimer.singleShot(3000, self._fade_out)

    def _fade_out(self) -> None:
        anim = QPropertyAnimation(self._opacity_eff, b"opacity", self)
        anim.setDuration(400)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.deleteLater)
        anim.start()
        self._out_anim = anim

    def show_at(self, parent: QWidget) -> None:
        """显示在父窗口顶部居中。"""
        parent_geo = parent.geometry()
        self.adjustSize()
        x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
        y = parent_geo.y() + 60
        self.move(x, y)
        self.show()
        self.raise_()


# ============================================================
# 加载遮罩
# ============================================================

class LoadingOverlay(QWidget):
    """半透明加载遮罩 + 旋转动画。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._angle = 0
        # _timer 必须在 hide() 调用前创建（hide 重写引用了 _timer）
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(14)

        self.spinner = QLabel()
        self.spinner.setFixedSize(40, 40)
        layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        self.text = QLabel("处理中...")
        self.text.setObjectName("LoadingText")
        self.text.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.text)

        self.hide()

    def set_text(self, text: str) -> None:
        self.text.setText(text)

    def show(self) -> None:
        self._angle = 0
        self._timer.start(40)
        super().show()
        self.raise_()

    def hide(self) -> None:  # type: ignore[override]
        if hasattr(self, "_timer") and self._timer:
            self._timer.stop()
        super().hide()

    def _rotate(self) -> None:
        self._angle = (self._angle + 12) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # 半透明背景
        p.fillRect(self.rect(), QColor(7, 11, 20, 160))

        # 绘制旋转环
        cx = self.width() // 2
        cy = self.height() // 2
        p.translate(cx, cy)
        p.rotate(self._angle)

        grad = QLinearGradient(-20, 0, 20, 0)
        grad.setColorAt(0, QColor(99, 102, 241, 0))
        grad.setColorAt(1, QColor(139, 92, 246, 255))
        pen = QPen(QBrush(grad), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawArc(-16, -16, 32, 32, 0, 270 * 16)


# ============================================================
# 可折叠区 / 操作日志面板
# ============================================================

class CollapsibleBox(QFrame):
    """通用可折叠容器：标题栏（点击折叠/展开）+ 内容控件。"""

    def __init__(self, title: str, content: QWidget,
                 parent: QWidget | None = None,
                 extra: list[QWidget] | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleBox")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QPushButton()
        header.setObjectName("CollapseHeader")
        header.setMinimumHeight(42)
        h = QHBoxLayout(header)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(8)
        self._arrow = QLabel("▼")
        self._arrow.setObjectName("CollapseArrow")
        h.addWidget(self._arrow)
        t = QLabel(title)
        t.setObjectName("SectionTitle")
        h.addWidget(t)
        for w in (extra or []):
            h.addWidget(w)
        h.addStretch()
        header.clicked.connect(self._toggle)
        outer.addWidget(header)

        self._content = content
        outer.addWidget(content)
        self._collapsed = False

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._arrow.setText("▶" if self._collapsed else "▼")


class LogPanel(CollapsibleBox):
    """操作日志面板：彩色折叠日志，订阅 OperationLog 实时刷新。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        self.body = QTextEdit()
        self.body.setObjectName("LogBody")
        self.body.setReadOnly(True)
        self.body.setMaximumHeight(200)

        self._count = QLabel("")
        self._count.setObjectName("SectionHint")
        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("GhostBtn")
        clear_btn.setCursor(Qt.PointingHandCursor)

        super().__init__("操作日志", self.body, parent=parent,
                         extra=[self._count, clear_btn])
        self.setObjectName("LogPanel")
        clear_btn.clicked.connect(self._clear)
        OperationLog().subscribe(self._append)

    @staticmethod
    def _escape(text: str) -> str:
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

    def _append(self, entry: dict[str, str]) -> None:
        color = LEVEL_COLORS.get(entry["level"], gs.TEXT)
        ts = entry["ts"]
        msg = self._escape(entry["msg"])
        self.body.append(f'<span style="color:{color}">[{ts}] {msg}</span>')
        self._count.setText(str(OperationLog().count))

    def _clear(self) -> None:
        self.body.clear()
        OperationLog().clear_memory()
        self._count.setText("0")


# ============================================================
# 主窗口
# ============================================================

class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("C盘瘦身助手")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.resize(960, 680)
        self.setMinimumSize(820, 560)

        # 应用 QSS
        self.setStyleSheet(gs.GLOBAL_QSS)

        # 工作线程引用（防 GC）
        self._workers: list[Any] = []
        self._scan_data: dict[str, Any] = {}
        self._toasts: list[Toast] = []
        self.oplog = OperationLog()

        # 中央容器
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 标题栏
        self.title_bar = TitleBar(self)
        root_layout.addWidget(self.title_bar)

        # 主体滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        self.scroll.setWidget(body)

        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 24)
        body_layout.setSpacing(16)

        # 1. 提示条
        self._build_notes(body_layout)

        # 2. 概览统计卡片
        self._build_overview(body_layout)

        # 3. 操作栏
        self._build_action_bar(body_layout)

        # 4. 扫描结果区
        self._build_results_section(body_layout)

        # 5. 操作日志面板（可折叠，落盘）
        self._build_log_panel(body_layout)

        body_layout.addStretch()

        root_layout.addWidget(self.scroll, 1)

        # 加载遮罩
        self.loading = LoadingOverlay(self)

        # 首次自动扫描
        QTimer.singleShot(400, self.do_scan)

    # ---------- UI 构建 ----------

    def _build_notes(self, parent_layout: QVBoxLayout) -> None:
        """安全提示条。"""
        notes = [
            ("warn", "⚠", "安全机制：只迁移超过 100MB 的目录，系统关键目录已自动排除。迁移前请关闭相关应用。"),
            ("admin", "🔑", "ProgramData / Program Files 需要管理员权限，会触发 UAC 弹窗，请在弹窗中点「是」。"),
        ]
        for kind, icon, text in notes:
            frame = QFrame()
            frame.setObjectName("Note")
            h = QHBoxLayout(frame)
            h.setContentsMargins(14, 10, 14, 10)
            h.setSpacing(10)
            ic = QLabel(icon)
            ic.setStyleSheet(f"font-size:16px;")
            h.addWidget(ic)
            tx = QLabel(text)
            tx.setObjectName(f"Note{'Warn' if kind=='warn' else 'Info'}Text")
            tx.setWordWrap(True)
            h.addWidget(tx, 1)
            parent_layout.addWidget(frame)

    def _build_overview(self, parent_layout: QVBoxLayout) -> None:
        """概览统计卡片栏。"""
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        t = QLabel("磁盘概览")
        t.setObjectName("SectionTitle")
        title_row.addWidget(t)
        hint = QLabel("实时统计 C / D 盘空间")
        hint.setObjectName("SectionHint")
        title_row.addWidget(hint)
        title_row.addStretch()
        parent_layout.addLayout(title_row)

        grid = QHBoxLayout()
        grid.setSpacing(12)

        self.card_c_free = StatCard("C盘可用", "0 GB", "StatValueGreen", "💾")
        self.card_d_free = StatCard("D盘可用", "0 GB", "StatValueBlue", "💽")
        self.card_released = StatCard("已释放", "0 GB", "StatValueTeal", "✨")
        self.card_potential = StatCard("可释放", "0 GB", "StatValueBrand", "🚀")
        self.card_temp = StatCard("Temp占用", "0 MB", "StatValueYellow", "🗑️")

        for card in [self.card_c_free, self.card_d_free, self.card_released,
                     self.card_potential, self.card_temp]:
            grid.addWidget(card, 1)

        parent_layout.addLayout(grid)

    def _build_action_bar(self, parent_layout: QVBoxLayout) -> None:
        """操作按钮栏。"""
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.btn_scan = QPushButton("🔄 重新扫描")
        self.btn_scan.setObjectName("GhostBtn")
        self.btn_scan.setCursor(Qt.PointingHandCursor)
        self.btn_scan.clicked.connect(self.do_scan)
        bar.addWidget(self.btn_scan)

        self.btn_clean_temp = QPushButton("🗑️ 清理 Temp")
        self.btn_clean_temp.setObjectName("PrimaryBtn")
        self.btn_clean_temp.setCursor(Qt.PointingHandCursor)
        self.btn_clean_temp.clicked.connect(self.do_clean_temp)
        bar.addWidget(self.btn_clean_temp)

        bar.addStretch()

        # 阈值显示
        self.threshold_label = QLabel("阈值: ≥100MB")
        self.threshold_label.setStyleSheet(f"color:{gs.TEXT_MUT};font-size:11px;")
        bar.addWidget(self.threshold_label)

        parent_layout.addLayout(bar)

    def _build_results_section(self, parent_layout: QVBoxLayout) -> None:
        """扫描结果区：分成「可迁移」和「已迁移」两个独立 section。"""
        # ===== Section 1: 可迁移目录 =====
        migrate_title = QHBoxLayout()
        migrate_title.setSpacing(10)
        self.migrate_dot = QLabel("●")
        self.migrate_dot.setStyleSheet(f"color:{gs.BRAND_2};font-size:14px;")
        migrate_title.addWidget(self.migrate_dot)
        self.migrate_title = QLabel("可迁移目录")
        self.migrate_title.setObjectName("SectionTitle")
        migrate_title.addWidget(self.migrate_title)
        self.migrate_count = QLabel("")
        self.migrate_count.setObjectName("SectionHint")
        migrate_title.addWidget(self.migrate_count)
        migrate_title.addStretch()
        parent_layout.addLayout(migrate_title)

        # 可迁移容器
        self.migrate_container = QVBoxLayout()
        self.migrate_container.setSpacing(8)
        parent_layout.addLayout(self.migrate_container)

        # 可迁移空状态
        self.migrate_empty = QFrame()
        self.migrate_empty.setStyleSheet("background:transparent;")
        me_layout = QVBoxLayout(self.migrate_empty)
        me_layout.setAlignment(Qt.AlignCenter)
        me_layout.setSpacing(10)
        me_ic = QLabel("🔍")
        me_ic.setObjectName("EmptyIcon")
        me_ic.setAlignment(Qt.AlignCenter)
        me_layout.addWidget(me_ic)
        me_tx = QLabel("正在扫描...")
        me_tx.setObjectName("EmptyText")
        me_tx.setAlignment(Qt.AlignCenter)
        me_layout.addWidget(me_tx)
        self.migrate_empty.setFixedHeight(140)
        parent_layout.addWidget(self.migrate_empty)

        # 间隔
        parent_layout.addSpacing(16)

        # ===== Section 2: 已迁移（Junction）—— 可折叠 =====
        junction_content = QWidget()
        jc_layout = QVBoxLayout(junction_content)
        jc_layout.setContentsMargins(0, 0, 0, 0)
        jc_layout.setSpacing(8)

        # 已迁移容器
        self.junction_container = QVBoxLayout()
        self.junction_container.setSpacing(8)
        jc_layout.addLayout(self.junction_container)

        # 已迁移空状态
        self.junction_empty = QFrame()
        self.junction_empty.setStyleSheet("background:transparent;")
        je_layout = QVBoxLayout(self.junction_empty)
        je_layout.setAlignment(Qt.AlignCenter)
        je_layout.setSpacing(8)
        je_ic = QLabel("📭")
        je_ic.setStyleSheet(f"font-size:32px;color:{gs.TEXT_DIM};")
        je_ic.setAlignment(Qt.AlignCenter)
        je_layout.addWidget(je_ic)
        je_tx = QLabel("还没有迁移过任何目录")
        je_tx.setStyleSheet(f"color:{gs.TEXT_DIM};font-size:12px;")
        je_tx.setAlignment(Qt.AlignCenter)
        je_layout.addWidget(je_tx)
        self.junction_empty.setFixedHeight(90)
        self.junction_empty.hide()  # 默认隐藏，扫描后按需显示
        jc_layout.addWidget(self.junction_empty)

        # 已迁移计数标签（传给 CollapsibleBox 的 extra）
        self.junction_count = QLabel("")
        self.junction_count.setObjectName("SectionHint")

        self.junction_box = CollapsibleBox(
            "已迁移到 D 盘", junction_content, extra=[self.junction_count]
        )
        parent_layout.addWidget(self.junction_box)

    # ---------- 业务逻辑 ----------

    def do_scan(self) -> None:
        """触发扫描。"""
        self._log("INFO", "开始全面扫描所有区域...")
        if not self._workers:
            self._set_loading(True, "正在扫描 C 盘...")

        self.btn_scan.setEnabled(False)
        self.migrate_count.setText("")
        self.junction_count.setText("")
        # 清空旧结果
        self._clear_results()

        worker = ScanWorker(threshold_mb=100)
        worker.finished.connect(self._on_scan_done)
        worker.error.connect(self._on_scan_error)
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.error.connect(lambda: self._workers.remove(worker))
        worker.start()

    def _on_scan_done(self, data: dict[str, Any]) -> None:
        """扫描完成。"""
        self._scan_data = data
        self._set_loading(False)
        self.btn_scan.setEnabled(True)

        big = data.get("bigDirs", [])
        junc = data.get("junctions", [])
        self._log("SUCCESS", f"扫描完成: {len(big)} 个可迁移, {len(junc)} 个已迁移")
        if data.get("tempSizeMB", 0) > 100:
            self._log("WARN", f"Temp 缓存占用 {self._fmt_size(data.get('tempSizeMB', 0))}，建议清理")

        # 更新统计卡片（数值动画）
        self.card_c_free.set_value_animated(data.get("cFreeGB", 0), " GB", 1)
        self.card_d_free.set_value_animated(data.get("dFreeGB", 0), " GB", 1)
        self.card_released.set_value_animated(data.get("releasedGB", 0), " GB", 2)
        self.card_potential.set_value_animated(data.get("potentialGB", 0), " GB", 2)
        self.card_temp.set_value_animated(data.get("tempSizeMB", 0), " MB", 0)

        # 渲染结果
        self._render_results(data)

    def _on_scan_error(self, err: str) -> None:
        self._set_loading(False)
        self.btn_scan.setEnabled(True)
        self._log("ERROR", f"扫描失败: {err}")
        self._show_toast(f"扫描失败: {err}", "error")
        self._clear_results()
        self._show_migrate_empty("扫描失败", "⚠️")

    def _render_results(self, data: dict[str, Any]) -> None:
        """渲染扫描结果：分两个 section 展示。"""
        self._clear_results()

        big_dirs = data.get("bigDirs", [])
        junctions = data.get("junctions", [])

        # ===== Section 1: 可迁移目录 =====
        if big_dirs:
            potential_gb = sum(d.get("sizeMB", 0) for d in big_dirs) / 1024
            self.migrate_count.setText(
                f"{len(big_dirs)} 项 · 可释放 {potential_gb:.1f} GB"
            )
            self.migrate_empty.hide()
            for i, item in enumerate(big_dirs):
                card = DirCard(item)
                card.migrate_clicked.connect(self._do_migrate)
                card.undo_clicked.connect(self._do_undo)
                card.admin_migrate_clicked.connect(self._do_admin_migrate)
                card.admin_undo_clicked.connect(self._do_admin_undo)
                self.migrate_container.addWidget(card)
                delay = min(i * 40, 600)
                gs.fade_in(card, duration=350, delay=delay)
        else:
            self.migrate_count.setText("0 项")
            self._show_migrate_empty("C 盘很干净，没有可迁移的大目录", "✓")

        # ===== Section 2: 已迁移（Junction）=====
        if junctions:
            released_gb = data.get("releasedGB", 0)
            self.junction_count.setText(
                f"{len(junctions)} 项 · 已释放 {released_gb:.1f} GB"
            )
            self.junction_empty.hide()
            for i, j in enumerate(junctions):
                item = {
                    "name": j.get("name", ""),
                    "path": j.get("source", ""),
                    "target": j.get("target", ""),
                    "zone": j.get("zone", ""),
                    "sizeMB": 0,
                    "isJunction": True,
                }
                card = DirCard(item)
                card.migrate_clicked.connect(self._do_migrate)
                card.undo_clicked.connect(self._do_undo)
                card.admin_migrate_clicked.connect(self._do_admin_migrate)
                card.admin_undo_clicked.connect(self._do_admin_undo)
                self.junction_container.addWidget(card)
                delay = min(i * 40, 600)
                gs.fade_in(card, duration=350, delay=delay)
        else:
            self.junction_count.setText("0 项")
            self.junction_empty.show()

    def _clear_results(self) -> None:
        """清空两个结果容器。"""
        for container in (self.migrate_container, self.junction_container):
            while container.count():
                item = container.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
        self.migrate_empty.show()
        # junction_empty 默认不显示，扫描后按需显示

    def _build_log_panel(self, parent_layout: QVBoxLayout) -> None:
        """构建操作日志面板（可折叠，订阅 OperationLog）。"""
        self.log_panel = LogPanel()
        parent_layout.addWidget(self.log_panel)

    def _log(self, level: str, msg: str) -> None:
        """记录一条操作日志（同时落盘 + 刷新面板）。"""
        self.oplog.log(level, msg)

    def _show_migrate_empty(self, text: str, icon: str = "🔍") -> None:
        """显示可迁移区的空状态。"""
        self.migrate_empty.show()
        labels = self.migrate_empty.findChildren(QLabel)
        if len(labels) >= 2:
            labels[0].setText(icon)
            labels[1].setText(text)

    # ---------- 迁移 / 撤销 ----------

    def _do_migrate(self, source: str, dest: str, name: str, size_mb: float) -> None:
        """普通迁移（确认弹窗 → 后台执行）。"""
        reply = QMessageBox.question(
            self, "确认迁移",
            f"即将迁移：\n{name}\n{self._fmt_size(size_mb)}\n\n"
            f"操作：复制到 D 盘 → 校验 → 删除原目录 → 创建 Junction。\n"
            f"请确保相关应用已关闭。继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._log("INFO", f"开始迁移: {name} ({self._fmt_size(size_mb)})")
        self._set_loading(True, f"正在迁移 {name}...")
        worker = MigrateWorker(source, dest, name)
        worker.finished.connect(lambda r: self._on_migrate_done(name, r))
        worker.error.connect(self._on_worker_error)
        self._workers.append(worker)
        worker.finished.connect(lambda: (self._workers.remove(worker), self._set_loading(False)))
        worker.error.connect(lambda: (self._workers.remove(worker), self._set_loading(False)))
        worker.start()

    def _on_migrate_done(self, name: str, result: dict[str, Any]) -> None:
        if result.get("success"):
            target = result.get("target", "")
            self._show_toast(f"✓ {name} 迁移成功", "success")
            self._log("SUCCESS", f"{name} 迁移成功 → {target}")
            for s in result.get("steps", []):
                self._log("INFO", f"  {s}")
            # 刷新磁盘信息
            if "cFreeGB" in result:
                self.card_c_free.set_value_animated(result["cFreeGB"], " GB", 1)
                self.card_d_free.set_value_animated(result["dFreeGB"], " GB", 1)
            QTimer.singleShot(800, self.do_scan)
        else:
            err = result.get("error", "未知错误")
            self._show_toast(f"迁移失败: {err}", "error")
            self._log("ERROR", f"{name} 迁移失败: {err}")
            if result.get("needsAdmin"):
                self._log("WARN", "需要管理员权限，请使用 🔑 Elevate 按钮")

    def _do_undo(self, source: str, name: str) -> None:
        """撤销迁移。"""
        reply = QMessageBox.question(
            self, "确认撤销",
            f"即将撤销迁移：\n{name}\n\n"
            f"操作：删除 Junction → 数据从 D 盘回迁到 C 盘。\n继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._log("INFO", f"开始撤销: {name}")
        self._set_loading(True, f"正在撤销 {name}...")
        worker = UndoWorker(source, name)
        worker.finished.connect(lambda r: self._on_undo_done(name, r))
        worker.error.connect(self._on_worker_error)
        self._workers.append(worker)
        worker.finished.connect(lambda: (self._workers.remove(worker), self._set_loading(False)))
        worker.error.connect(lambda: (self._workers.remove(worker), self._set_loading(False)))
        worker.start()

    def _on_undo_done(self, name: str, result: dict[str, Any]) -> None:
        if result.get("success"):
            self._show_toast(f"✓ {name} 已回迁到 C 盘", "success")
            self._log("SUCCESS", f"{name} 撤销成功，数据已回迁到 C 盘 ({self._fmt_size(result.get('sizeMB', 0))})")
            if "cFreeGB" in result:
                self.card_c_free.set_value_animated(result["cFreeGB"], " GB", 1)
                self.card_d_free.set_value_animated(result["dFreeGB"], " GB", 1)
            QTimer.singleShot(800, self.do_scan)
        else:
            err = result.get("error", "未知错误")
            self._show_toast(f"撤销失败: {err}", "error")
            self._log("ERROR", f"{name} 撤销失败: {err}")

    # ---------- 管理员操作 ----------

    def _do_admin_migrate(self, source: str, dest: str, name: str, size_mb: float) -> None:
        """管理员迁移：生成 bat + UAC。"""
        reply = QMessageBox.question(
            self, "管理员迁移",
            f"即将以管理员权限迁移：\n{name}\n{self._fmt_size(size_mb)}\n\n"
            f"会弹出 UAC 权限请求，请点「是」。\n"
            f"迁移脚本会打开一个 CMD 窗口执行，完成后请回到本程序查看结果。\n继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._log("INFO", f"请求管理员迁移: {name} ({self._fmt_size(size_mb)})")
        worker = AdminMigrateWorker(source, dest, name, size_mb)
        worker.finished.connect(self._on_admin_triggered)
        worker.error.connect(self._on_worker_error)
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.error.connect(lambda: self._workers.remove(worker))
        worker.start()
        self._set_loading(True, "正在生成管理员脚本...")

    def _do_admin_undo(self, source: str, name: str) -> None:
        """管理员撤销。"""
        reply = QMessageBox.question(
            self, "管理员撤销",
            f"即将以管理员权限撤销迁移：\n{name}\n\n"
            f"会弹出 UAC 权限请求，请点「是」。\n继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._log("INFO", f"请求管理员撤销: {name}")
        worker = AdminUndoWorker(source, name)
        worker.finished.connect(self._on_admin_triggered)
        worker.error.connect(self._on_worker_error)
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.error.connect(lambda: self._workers.remove(worker))
        worker.start()
        self._set_loading(True, "正在生成管理员脚本...")

    def _on_admin_triggered(self, result: dict[str, Any]) -> None:
        """UAC 已触发。"""
        self._set_loading(False)
        if result.get("uacTriggered"):
            name = result.get("name", "")
            self._show_toast(f"UAC 已弹出，请在权限窗口点「是」", "info")
            self._log("INFO", f"已请求 UAC 提权: {name}，请在权限窗口点「是」")
            # 提示用户检查结果
            self._show_admin_result_dialog(name, result.get("resultFile", ""))
        else:
            self._show_toast("UAC 触发失败，请手动以管理员运行脚本", "warn")
            self._log("WARN", f"UAC 自动触发失败: {name}，请手动以管理员运行脚本")

    def _show_admin_result_dialog(self, name: str, result_file: str) -> None:
        """显示管理员操作结果查询对话框。"""
        msg = QMessageBox(self)
        msg.setWindowTitle("等待管理员操作完成")
        msg.setText(
            f"管理员脚本已执行。\n\n"
            f"请在弹出的 CMD 窗口完成迁移操作。\n"
            f"操作完成后，点「查询结果」按钮检查是否成功。\n\n"
            f"脚本: {result_file}"
        )
        btn_query = msg.addButton("查询结果", QMessageBox.AcceptRole)
        msg.addButton("稍后", QMessageBox.RejectRole)
        msg.exec()

        if msg.clickedButton() == btn_query:
            self._query_admin_result(name)

    def _query_admin_result(self, name: str) -> None:
        """查询管理员脚本结果。"""
        result = read_admin_result(name)
        if result.get("pending"):
            self._show_toast("脚本还在执行中，请稍后再查询", "warn")
            self._log("WARN", f"{name} 管理员脚本还在执行中，请稍后再查询")
            return
        if result.get("success"):
            size_mb = result.get("sizeMB", 0)
            self._show_toast(f"✓ 管理员迁移成功！释放 {self._fmt_size(size_mb)}", "success")
            self._log("SUCCESS", f"{name} 管理员操作成功！释放 {self._fmt_size(size_mb)}")
            QTimer.singleShot(800, self.do_scan)
        else:
            err = result.get("error", "执行失败")
            self._show_toast(f"管理员操作失败: {err}", "error")
            self._log("ERROR", f"{name} 管理员操作失败: {err}")

    # ---------- Temp 清理 ----------

    def do_clean_temp(self) -> None:
        """清理 Temp 目录。"""
        reply = QMessageBox.question(
            self, "清理 Temp",
            f"将清理 C 盘 Temp 目录中超过 1 天的临时文件。\n继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._log("INFO", "开始清理 Temp 目录（超过 1 天的临时文件）...")
        self._set_loading(True, "正在清理 Temp...")
        self.btn_clean_temp.setEnabled(False)
        worker = CleanTempWorker()
        worker.finished.connect(self._on_clean_temp_done)
        worker.error.connect(self._on_worker_error)
        self._workers.append(worker)
        worker.finished.connect(lambda: (self._workers.remove(worker), self._set_loading(False), self.btn_clean_temp.setEnabled(True)))
        worker.error.connect(lambda: (self._workers.remove(worker), self._set_loading(False), self.btn_clean_temp.setEnabled(True)))
        worker.start()

    def _on_clean_temp_done(self, result: dict[str, Any]) -> None:
        cleaned = result.get("cleanedMB", 0)
        self._show_toast(f"✓ 已清理 Temp: {self._fmt_size(cleaned)}", "success")
        self._log("SUCCESS", f"Temp 清理完成: 释放 {self._fmt_size(cleaned)}")
        if "cFreeGB" in result:
            self.card_c_free.set_value_animated(result["cFreeGB"], " GB", 1)
        self.card_temp.set_value_animated(0, " MB", 0)

    # ---------- 辅助 ----------

    def _on_worker_error(self, err: str) -> None:
        self._set_loading(False)
        self.btn_scan.setEnabled(True)
        self.btn_clean_temp.setEnabled(True)
        self._show_toast(f"操作出错: {err}", "error")
        self._log("ERROR", f"操作出错: {err}")

    def _set_loading(self, on: bool, text: str = "") -> None:
        if on:
            self.loading.set_text(text)
            self.loading.resize(self.scroll.size())
            self.loading.show()
            self.loading.raise_()
        else:
            self.loading.hide()

    def _show_toast(self, text: str, kind: str = "info") -> None:
        toast = Toast(text, kind, self)
        toast.show_at(self)
        self._toasts.append(toast)

    @staticmethod
    def _fmt_size(size_mb: float) -> str:
        if size_mb >= 1024:
            return f"{size_mb / 1024:.2f} GB"
        return f"{size_mb:.0f} MB"

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.loading.resize(self.scroll.size())

    def closeEvent(self, event: Any) -> None:
        # 等待工作线程结束
        for w in self._workers:
            if w.isRunning():
                w.quit()
                w.wait(2000)
        super().closeEvent(event)


# ============================================================
# 入口
# ============================================================

def launch() -> int:
    """启动 GUI 应用，返回退出码。"""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("CDriveCleaner")
    app.setApplicationVersion(__version__)

    # 字体策略：优先 JetBrains Mono（等宽，数字对齐不抖动，极客感）
    # 中文自动 fallback 到 Microsoft YaHei UI。
    _setup_app_font(app)

    # 设置图标
    icon_path = _find_icon()
    if icon_path and os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    return app.exec()


def _setup_app_font(app: QApplication) -> None:
    """配置应用全局字体：JetBrains Mono 优先，雅黑兜底。

    查找顺序：
      1. 系统已注册的字体家族（QFontDatabase.families）
      2. 从用户字体目录加载 ttf（addApplicationFont）
      3. 回退 Microsoft YaHei UI
    """
    families = QFontDatabase.families()

    candidates = [
        "JetBrains Mono",
        "JetBrainsMono Nerd Font",
        "JetBrainsMono Nerd Font Mono",
        "Cascadia Mono",
        "Cascadia Code",
        "Consolas",
    ]

    chosen = next((f for f in candidates if f in families), None)

    # 系统没注册 → 尝试从用户字体目录加载 ttf
    if not chosen:
        chosen = _try_load_jetbrains_from_disk(candidates)

    if chosen:
        font = QFont(chosen, 10)
        font.setStyleHint(QFont.Monospace)
        font.setFamilies([chosen, "Microsoft YaHei UI", "Microsoft YaHei", "SimHei"])
        print(f"[font] 使用字体: {chosen}")
    else:
        font = QFont("Microsoft YaHei UI", 10)
        font.setStyleHint(QFont.SansSerif)
        print("[font] 未找到 JetBrains Mono，回退 Microsoft YaHei UI")

    app.setFont(font)


def _try_load_jetbrains_from_disk(candidates: list[str]) -> str | None:
    """从用户字体目录加载 JetBrains Mono ttf，返回匹配的家族名。"""
    user_font_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"
    )
    ttf_patterns = [
        "JetBrainsMono-Regular.ttf",
        "JetBrainsMono-Bold.ttf",
        "JetBrainsMono-Medium.ttf",
        "JetBrainsMonoNerdFont-Regular.ttf",
        "JetBrainsMonoNerdFontMono-Regular.ttf",
    ]

    loaded_any = False
    for name in ttf_patterns:
        ttf = os.path.join(user_font_dir, name)
        if os.path.exists(ttf):
            font_id = QFontDatabase.addApplicationFont(ttf)
            if font_id != -1:
                loaded_any = True
                print(f"[font] 已加载字体文件: {name}")

    if not loaded_any:
        return None

    families = QFontDatabase.families()
    return next((f for f in candidates if f in families), None)


def _find_icon() -> str:
    """查找应用图标路径。"""
    candidates = []
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(base, "assets", "CDriveCleaner.ico"),
            os.path.join(sys._MEIPASS, "assets", "CDriveCleaner.ico"),
        ]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(root, "assets", "CDriveCleaner.ico"),
            os.path.join(root, "assets", "CDriveCleaner.png"),
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""
