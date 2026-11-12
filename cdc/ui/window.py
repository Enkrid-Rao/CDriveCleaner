"""主窗口：暖纸张画布、深墨侧边栏、标题栏、页面栈与全局进度。"""

from __future__ import annotations

import os
import random
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QLinearGradient, QPainter, QPaintEvent, QRadialGradient,
    QShortcut, QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from ..version import __version__
from . import icons, theme
from .frameless import ResizableFrameless
from .pages.archive import ArchivePage
from .pages.dashboard import DashboardPage
from .pages.history import HistoryPage
from .pages.links import LinksPage
from .pages.settings import SettingsPage
from .pages.slimming import SlimmingPage
from .state import AppState
from .widgets import ConfirmDialog, Pill, ProgressOverlay, Toast, label


PAGE_TITLES = {
    "dashboard": "总览",
    "slimming": "C 盘瘦身",
    "archive": "冷数据归档",
    "links": "链接管理",
    "history": "操作记录",
    "settings": "设置",
}


class PaperBackground(QWidget):
    """暖纸张画布：微光 + 纸纤维颗粒，预渲染避免重绘。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cache = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._cache = None

    def _render(self) -> None:
        from PySide6.QtGui import QPixmap
        dpr = self.devicePixelRatioF() or 1.0
        w, h = max(1, self.width()), max(1, self.height())
        pix = QPixmap(int(w * dpr), int(h * dpr))
        pix.setDevicePixelRatio(dpr)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(0, 0, w, h, QColor(theme.BG))

        # 左上暖光
        g1 = QRadialGradient(w * 0.20, h * 0.06, max(w, h) * 0.78)
        g1.setColorAt(0.0, QColor(255, 250, 240, 150))
        g1.setColorAt(0.55, QColor(255, 250, 240, 40))
        g1.setColorAt(1.0, QColor(255, 250, 240, 0))
        p.fillRect(QRectF(0, 0, w, h), g1)

        # 右下鼠尾草色
        g2 = QRadialGradient(w * 0.92, h * 0.96, max(w, h) * 0.58)
        g2.setColorAt(0.0, QColor(109, 117, 81, 30))
        g2.setColorAt(1.0, QColor(109, 117, 81, 0))
        p.fillRect(QRectF(0, 0, w, h), g2)

        # 右上赭红余温
        g3 = QRadialGradient(w * 0.96, h * 0.02, max(w, h) * 0.42)
        g3.setColorAt(0.0, QColor(180, 74, 45, 16))
        g3.setColorAt(1.0, QColor(180, 74, 45, 0))
        p.fillRect(QRectF(0, 0, w, h), g3)

        # 纸纤维颗粒（固定种子，画面稳定）
        rng = random.Random(20261112)
        p.setPen(Qt.NoPen)
        for _ in range(min(5200, int(w * h / 420))):
            x = rng.uniform(0, w)
            y = rng.uniform(0, h)
            alpha = rng.randint(4, 12)
            p.setBrush(QColor(92, 77, 56, alpha))
            size = rng.choice((1, 1, 1, 2))
            p.drawRect(QRectF(x, y, size, size))

        # 极轻的边缘压暗，让内容区有纸张厚度
        g4 = QLinearGradient(0, 0, 0, h)
        g4.setColorAt(0.0, QColor(80, 65, 45, 12))
        g4.setColorAt(0.18, QColor(80, 65, 45, 0))
        g4.setColorAt(0.84, QColor(80, 65, 45, 0))
        g4.setColorAt(1.0, QColor(80, 65, 45, 16))
        p.fillRect(QRectF(0, 0, w, h), g4)
        p.end()
        self._cache = pix

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._cache is None:
            self._render()
        p = QPainter(self)
        if self._cache is not None:
            p.drawPixmap(0, 0, self._cache)
        p.end()


class TitleBar(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.window_ref = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(52)
        self._drag = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 0, 0)
        layout.setSpacing(10)
        self.page_title = QLabel("总览")
        self.page_title.setObjectName("BreadcrumbActive")
        layout.addWidget(self.page_title)
        self.page_hint = QLabel("")
        self.page_hint.setObjectName("Breadcrumb")
        layout.addWidget(self.page_hint)
        layout.addStretch()

        self.activity = Pill("扫描中", "brand")
        self.activity.hide()
        layout.addWidget(self.activity)
        self.perm_pill = Pill("标准权限", "muted")
        self.perm_pill.setToolTip("ProgramData / Program Files 迁移时会按需请求 UAC")
        layout.addWidget(self.perm_pill)
        layout.addSpacing(4)
        self.btn_min = QPushButton("−")
        self.btn_min.setObjectName("WindowBtn")
        self.btn_min.setFixedSize(44, 32)
        self.btn_min.setCursor(Qt.PointingHandCursor)
        self.btn_min.clicked.connect(window.showMinimized)
        layout.addWidget(self.btn_min)
        self.btn_max = QPushButton("□")
        self.btn_max.setObjectName("WindowBtn")
        self.btn_max.setFixedSize(44, 32)
        self.btn_max.setCursor(Qt.PointingHandCursor)
        self.btn_max.clicked.connect(self._toggle_max)
        layout.addWidget(self.btn_max)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.setFixedSize(46, 32)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(window.close)
        layout.addWidget(self.btn_close)

    def set_page(self, key: str) -> None:
        self.page_title.setText(PAGE_TITLES.get(key, key))
        self.page_hint.setText("/  CDriveCleaner")

    def set_admin(self, admin: bool) -> None:
        self.perm_pill.setText("管理员" if admin else "标准权限")
        self.perm_pill.set_tone("green" if admin else "muted")

    def set_activity(self, text: str = "") -> None:
        if text:
            self.activity.setText(text)
            self.activity.show()
        else:
            self.activity.hide()

    def _toggle_max(self) -> None:
        if self.window_ref.isMaximized():
            self.window_ref.showNormal()
        else:
            self.window_ref.showMaximized()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.window_ref.pos()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            if self.window_ref.isMaximized():
                self.window_ref.showNormal()
                self._drag = QPoint(self.window_ref.width() // 2, 26)
            self.window_ref.move(event.globalPosition().toPoint() - self._drag)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._toggle_max()


class MainWindow(ResizableFrameless, QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self.state = state
        self.setWindowTitle("CDriveCleaner")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(1120, 720)
        width, height = state.config.window_size
        self.resize(width, height)
        self.setWindowIcon(QIcon(icons.logo_pixmap(128)))

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.background = PaperBackground(root)
        self.background.setGeometry(self.rect())
        self.background.lower()
        from .widgets import Sidebar
        self.sidebar = Sidebar()
        outer.addWidget(self.sidebar)

        right = QWidget()
        right.setObjectName("Transparent")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.titlebar = TitleBar(self)
        right_layout.addWidget(self.titlebar)
        self.stack = QStackedWidget()
        self.stack.setObjectName("PageRoot")
        right_layout.addWidget(self.stack, 1)
        outer.addWidget(right, 1)

        self.pages = {
            "dashboard": DashboardPage(state),
            "slimming": SlimmingPage(state),
            "archive": ArchivePage(state),
            "links": LinksPage(state),
            "history": HistoryPage(state),
            "settings": SettingsPage(state),
        }
        for key, page in self.pages.items():
            self.stack.addWidget(page)
        self._page_order = ["dashboard", "slimming", "archive", "links", "history", "settings"]
        self.current_page = "dashboard"

        self.overlay = ProgressOverlay(self)
        self._active_toast = None

        self.sidebar.navigate.connect(self.navigate)
        self.state.navigate.connect(self.navigate)
        self.state.drives_changed.connect(self._on_drives)
        self.state.toast.connect(lambda text, kind: Toast.show_message(self, text, kind))
        self.state.operation_started.connect(self._on_operation_started)
        self.state.operation_progress.connect(self.overlay.update_progress)
        self.state.operation_finished.connect(self._on_operation_finished)
        self.state.operation_failed.connect(self._on_operation_failed)
        self.state.operation_busy.connect(self._on_busy)
        self.state.config_changed.connect(self._apply_style)
        self.state.scan_started.connect(lambda: self.titlebar.set_activity("扫描中"))
        self.state.scan_finished.connect(lambda _r: self.titlebar.set_activity(""))
        self.state.scan_failed.connect(lambda _e: self.titlebar.set_activity(""))
        self.state.analysis_started.connect(lambda: self.titlebar.set_activity("分析中"))
        self.state.analysis_finished.connect(lambda _r: self.titlebar.set_activity(""))
        self.state.analysis_failed.connect(lambda _e: self.titlebar.set_activity(""))
        self.overlay.cancel_requested.connect(self.state.cancel_operation)

        self._setup_shortcuts()
        self.titlebar.set_admin(state.is_admin)
        drive = state.c_drive()
        if drive:
            self.sidebar.set_drive(drive)
        start = state.config.last_page if state.config.last_page in self.pages else "dashboard"
        self.navigate(start, refresh=True)
        self._center()

    # ---------- 布局 ----------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.background.setGeometry(self.rect())
        self.overlay.resize_to_parent()
        self.background.lower()

    def _center(self) -> None:
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self.move(geo.center() - self.rect().center())

    def _setup_shortcuts(self) -> None:
        for i, key in enumerate(self._page_order[:6], start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            shortcut.activated.connect(lambda k=key: self.navigate(k))
        QShortcut(QKeySequence("F5"), self).activated.connect(self._refresh_current)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

    def _refresh_current(self) -> None:
        page = self.pages.get(self.current_page)
        if hasattr(page, "refresh"):
            page.refresh()
        if self.current_page in ("dashboard", "slimming", "links"):
            self.state.start_scan()

    def _focus_search(self) -> None:
        page = self.pages.get(self.current_page)
        search = getattr(page, "search", None)
        if search is not None:
            search.setFocus()
            search.selectAll()

    def navigate(self, key: str, refresh: bool = False) -> None:
        if key not in self.pages:
            key = "dashboard"
        self.current_page = key
        self.stack.setCurrentWidget(self.pages[key])
        self.sidebar.set_active(key)
        self.titlebar.set_page(key)
        page = self.pages[key]
        if refresh and hasattr(page, "refresh"):
            page.refresh()

    # ---------- 状态 ----------

    def _on_drives(self, drives: list) -> None:
        from ..core import windows
        drive = windows.get_drive("C", drives)
        if drive:
            self.sidebar.set_drive(drive)
        self.titlebar.set_admin(windows.is_admin())

    def _on_operation_started(self, title: str, subtitle: str, count: int,
                              steps: Any) -> None:
        self.titlebar.set_activity("处理中")
        icon_name = "archive"
        if "迁移" in title:
            icon_name = "sparkles"
        elif "撤销" in title:
            icon_name = "undo"
        elif "回迁" in title:
            icon_name = "download"
        elif "清理" in title:
            icon_name = "trash"
        self.overlay.show_operation(title, subtitle, count,
                                    list(steps) if steps else None, icon_name)

    def _on_operation_finished(self, results: list) -> None:
        self.overlay.finish()
        self.titlebar.set_activity("")
        ok = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]
        total = sum(r.bytes_total for r in ok)
        from ..core.models import human_bytes
        if len(results) == 1:
            r = results[0]
            if r.ok:
                Toast.show_message(
                    self, f"完成 · {r.action} {r.name} · {human_bytes(r.bytes_total)}",
                    "success")
            else:
                Toast.show_message(self, f"失败 · {r.error[:160]}", "error")
        else:
            Toast.show_message(
                self, f"完成 {len(ok)} 项，{len(failed)} 项失败 · "
                      f"释放 {human_bytes(total)}", "success" if not failed else "warn")
            if failed:
                lines = "\n".join(f"· {r.name}：{r.error[:160]}" for r in failed[:6])
                ConfirmDialog.show_info(
                    self, "部分操作未完成",
                    "失败项不会删除源数据，详细原因如下。",
                    lines, icon_name="alert", tone="rose")

    def _on_operation_failed(self, error: str) -> None:
        self.overlay.finish()
        self.titlebar.set_activity("")
        Toast.show_message(self, f"操作失败：{error}", "error")

    def _on_busy(self, busy: bool) -> None:
        self.titlebar.perm_pill.setEnabled(not busy)

    def _apply_style(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        cfg = self.state.config
        app.setStyleSheet(theme.build_qss(cfg.font_size, cfg.motion))
        theme.set_motion(cfg.motion)
        self.titlebar.set_admin(self.state.is_admin)

    # ---------- 关闭 ----------

    def closeEvent(self, event) -> None:
        if self.state.busy:
            ok = ConfirmDialog.ask(
                self, "操作正在进行",
                "现在退出会请求取消当前操作；已校验的数据不会丢失。确定退出？",
                "退出", tone="rose", note="取消可能发生在复制或校验阶段，源数据不会被删除。",
                note_tone="warn", require_check=True, icon_name="alert")
            if not ok:
                event.ignore()
                return
            self.state.cancel_operation()
        self.state.save_window_state(self.current_page, self.width(), self.height())
        self.state.shutdown()
        super().closeEvent(event)
