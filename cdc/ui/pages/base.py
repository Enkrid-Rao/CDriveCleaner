"""页面公共工具。"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core import windows
from ...core.models import (
    ACTION_ARCHIVE, ACTION_CLEAN, ACTION_LABELS, ACTION_LINK, ACTION_MIGRATE,
    ACTION_RESTORE, ACTION_UNDO, human_bytes,
)
from .. import icons, theme
from ..widgets import ElidedLabel, IconTile, Pill, label


ACTION_ICONS = {
    ACTION_MIGRATE: ("sparkles", "brand"),
    ACTION_UNDO: ("undo", "amber"),
    ACTION_ARCHIVE: ("archive", "teal"),
    ACTION_RESTORE: ("download", "cyan"),
    ACTION_LINK: ("link", "purple"),
    ACTION_CLEAN: ("trash", "muted"),
}

ACTION_TONES = {
    "success": "green",
    "failed": "rose",
    "rolled_back": "amber",
    "canceled": "muted",
}


def fmt_size(value: int | float) -> str:
    return human_bytes(value or 0)


def fmt_time(ts: str, short: bool = True) -> str:
    try:
        dt = _dt.datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return ts or "—"
    now = _dt.datetime.now()
    if dt.date() == now.date():
        return f"今天 {dt:%H:%M}"
    if dt.year == now.year:
        return f"{dt:%m-%d %H:%M}" if short else f"{dt:%Y-%m-%d %H:%M}"
    return f"{dt:%Y-%m-%d %H:%M}"


def status_pill(status: str) -> Pill:
    tone = ACTION_TONES.get(status, "muted")
    text = {"success": "成功", "failed": "失败", "rolled_back": "已回滚",
            "canceled": "已取消"}.get(status, status)
    return Pill(text, tone)


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def primary_button(text: str, icon_name: str = "") -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Primary")
    btn.setCursor(Qt.PointingHandCursor)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, "#ffffff", 15))
    return btn


def ghost_button(text: str, icon_name: str = "", color: str = theme.TEXT_2) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Ghost")
    btn.setCursor(Qt.PointingHandCursor)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, color, 15))
    return btn


def action_icon_button(action: str) -> IconTile:
    icon_name, tone = ACTION_ICONS.get(action, ("dot", "muted"))
    return IconTile(icon_name, tone, 32, 15)


def open_path(path: str) -> None:
    if path and os.path.exists(path):
        windows.open_in_explorer(path)


def card_header(title: str, hint: str = "",
                actions: list[QWidget] | None = None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(2, 0, 2, 0)
    layout.setSpacing(10)
    box = QVBoxLayout()
    box.setSpacing(2)
    box.addWidget(label(title, "CardTitle"))
    if hint:
        box.addWidget(label(hint, "Muted"))
    layout.addLayout(box)
    layout.addStretch()
    for action in actions or []:
        layout.addWidget(action)
    return row


def stat_pill(text: str, tone: str = "muted") -> Pill:
    return Pill(text, tone)


def drive_badge(letter: str, tone: str | None = None) -> QLabel:
    tone = tone or {"C": "c", "D": "d", "E": "e"}.get(letter.upper()[:1], "brand")
    color = theme.tone_color(tone)
    badge = QLabel(letter.upper()[:1])
    badge.setFixedSize(30, 30)
    badge.setAlignment(Qt.AlignCenter)
    badge.setStyleSheet(
        f"background:{theme.TONE_BG.get(tone, theme.TONE_BG['brand'])};"
        f"color:{color};border:1px solid {theme.TONE_BORDER.get(tone, theme.BORDER_HI)};"
        "border-radius:9px;font-family:'JetBrains Mono';font-size:13px;font-weight:800;"
    )
    return badge


def note_frame(text: str, tone: str = "info", icon_name: str = "info") -> QFrame:
    color = {"warn": theme.AMBER, "danger": theme.RED,
             "success": theme.GREEN}.get(tone, theme.BRAND_2)
    frame = QFrame()
    frame.setObjectName({"warn": "NoteWarn", "danger": "NoteDanger",
                         "success": "NoteSuccess"}.get(tone, "Note"))
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(9)
    icon = QLabel()
    icon.setPixmap(icons.icon_pixmap(icon_name, color, 16))
    icon.setFixedSize(17, 17)
    layout.addWidget(icon, alignment=Qt.AlignTop)
    text_label = label(text, "WarnText" if tone == "warn" else
                       "ErrorText" if tone == "danger" else
                       "SuccessText" if tone == "success" else "Body", wrap=True)
    layout.addWidget(text_label, 1)
    return frame


def empty_label(text: str) -> QLabel:
    lbl = label(text, "Muted")
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setContentsMargins(0, 20, 0, 20)
    return lbl
