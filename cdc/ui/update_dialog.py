"""自动更新 UI：发现新版本横幅与下载/安装对话框。"""

from __future__ import annotations

import os
import threading
from typing import Any

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from .. import paths
from ..core import updater
from ..core.models import human_bytes
from . import theme
from .widgets import IconTile, add_shadow, label


def _notes_text(body: str) -> str:
    # 只展示正文精彩段落，避免整个 release 过长
    text = (body or "").strip()
    if len(text) > 6000:
        text = text[:6000] + "\n\n…（完整内容见发布页）"
    return text


class UpdateBanner(QFrame):
    view_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("UpdateBanner")
        self.setFixedHeight(46)
        self.setStyleSheet(
            "QFrame#UpdateBanner { background:#F9E9E1; "
            "border-bottom:1px solid #E2BFAF; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 7, 14, 7)
        layout.setSpacing(10)
        layout.addWidget(IconTile("download", "brand", 30, 15))
        self.text = QLabel("发现新版本")
        self.text.setStyleSheet(
            f"color:{theme.TEXT};font-size:13px;font-weight:600;")
        layout.addWidget(self.text)
        self.sub = QLabel("")
        self.sub.setStyleSheet(f"color:{theme.MUT};font-size:12px;")
        layout.addWidget(self.sub)
        layout.addStretch()
        view = QPushButton("查看更新")
        view.setObjectName("Primary")
        view.setCursor(Qt.PointingHandCursor)
        view.clicked.connect(self.view_requested.emit)
        layout.addWidget(view)
        later = QPushButton("稍后")
        later.setObjectName("Ghost")
        later.setCursor(Qt.PointingHandCursor)
        later.clicked.connect(self.dismissed.emit)
        layout.addWidget(later)
        close = QPushButton("✕")
        close.setObjectName("IconBtn")
        close.setFixedSize(28, 28)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.dismissed.emit)
        layout.addWidget(close)
        self.hide()

    def set_info(self, info: Any) -> None:
        self.text.setText(f"发现新版本 v{info.version}")
        self.sub.setText(f"当前 v{info.current_version} · 点击查看更新内容")


class DownloadWorker(QThread):
    progress = Signal(int, int)
    result_ready = Signal(str)
    failed = Signal(str)

    def __init__(self, info: Any) -> None:
        super().__init__()
        self.info = info
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        try:
            asset = self.info.asset()
            if asset is None:
                self.failed.emit("没有可下载的更新包")
                return
            dest_dir = paths.data_dir() / "updates"
            path = updater.download_asset(
                asset, dest_dir,
                progress=lambda done, total: self.progress.emit(done, total),
                cancel=self._cancel.is_set,
            )
            self.result_ready.emit(path)
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDialog(QDialog):
    def __init__(self, parent: QWidget | None, info: Any) -> None:
        super().__init__(parent)
        self.info = info
        self.downloaded = ""
        self.worker: DownloadWorker | None = None
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("DialogInner")
        card.setStyleSheet(
            f"QFrame#DialogInner {{ background:{theme.SURFACE}; "
            f"border:1px solid {theme.BORDER_HI}; border-radius:18px; }}"
        )
        card.setFixedWidth(680)
        add_shadow(card, 40, 14, 70)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(13)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(IconTile("download", "brand", 44, 21), alignment=Qt.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(3)
        title = label(f"发现新版本 v{info.version}", "CardTitle")
        title.setStyleSheet(f"color:{theme.TEXT};font-size:18px;font-weight:700;")
        text_box.addWidget(title)
        text_box.addWidget(label(
            f"当前 v{info.current_version}  ·  {info.published_at[:10] or '新版本'}", "Muted"))
        head.addLayout(text_box, 1)
        close = QPushButton("✕")
        close.setObjectName("IconBtn")
        close.setFixedSize(30, 30)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.reject)
        head.addWidget(close, alignment=Qt.AlignTop)
        layout.addLayout(head)

        notes = QTextBrowser()
        notes.setObjectName("LogBody")
        notes.setReadOnly(True)
        notes.setFixedHeight(230)
        try:
            notes.setMarkdown(_notes_text(info.body))
        except Exception:
            notes.setPlainText(_notes_text(info.body))
        layout.addWidget(notes)

        meta = QHBoxLayout()
        asset = info.asset()
        if asset:
            meta.addWidget(label(
                f"更新包：{asset.name}  ·  {human_bytes(asset.size)}", "Muted"))
        else:
            meta.addWidget(label(
                "当前为源码模式，更新不会自动替换；请打开发布页下载。", "Muted"))
        meta.addStretch()
        page = QPushButton("打开发布页")
        page.setObjectName("Link")
        page.setCursor(Qt.PointingHandCursor)
        page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(info.page_url)))
        meta.addWidget(page)
        layout.addLayout(meta)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label("", "Muted")
        layout.addWidget(self.status)

        footer = QHBoxLayout()
        footer.addStretch()
        self.later = QPushButton("稍后")
        self.later.setObjectName("Ghost")
        self.later.setCursor(Qt.PointingHandCursor)
        self.later.clicked.connect(self.reject)
        footer.addWidget(self.later)
        self.action = QPushButton(
            "打开发布页" if not info.installable else "下载更新")
        self.action.setObjectName("Primary")
        self.action.setMinimumWidth(132)
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self._action)
        footer.addWidget(self.action)
        layout.addLayout(footer)

        self.adjustSize()
        if parent:
            self.move(parent.frameGeometry().center() - self.rect().center())

    def _action(self) -> None:
        if not self.info.installable:
            QDesktopServices.openUrl(QUrl(self.info.page_url))
            return
        if self.downloaded:
            self._install()
            return
        self._download()

    def _download(self) -> None:
        self.action.setEnabled(False)
        self.action.setText("下载中…")
        self.later.setEnabled(False)
        self.progress.show()
        self.status.setText("正在下载更新…")
        worker = DownloadWorker(self.info)
        worker.progress.connect(self._on_progress)
        worker.result_ready.connect(self._on_downloaded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(worker.deleteLater)
        self.worker = worker
        worker.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setValue(min(99, int(done * 100 / total)))
            self.status.setText(
                f"正在下载 {human_bytes(done)} / {human_bytes(total)}")
        else:
            self.progress.setRange(0, 0)

    def _on_downloaded(self, path: str) -> None:
        self.worker = None
        self.downloaded = path
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.status.setText("下载完成，SHA256 校验通过。")
        self.action.setEnabled(True)
        self.action.setText("安装并重启")
        self.later.setEnabled(True)
        self.later.setText("取消")

    def _on_failed(self, error: str) -> None:
        self.worker = None
        self.progress.hide()
        self.status.setText(f"更新失败：{error}")
        self.action.setEnabled(True)
        self.action.setText("重试")
        self.later.setEnabled(True)

    def _install(self) -> None:
        ok, error = updater.apply_update(self.info, self.downloaded)
        if not ok:
            self.status.setText(f"安装失败：{error}")
            return
        QApplication.quit()

    def reject(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("正在取消下载…")
            return
        super().reject()


def show_update_dialog(parent: QWidget | None, info: Any) -> None:
    dialog = UpdateDialog(parent, info)
    dialog.exec()
