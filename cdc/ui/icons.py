"""矢量图标与品牌 Logo（全部代码绘制，无外部图片依赖）。"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from . import theme

_PATHS: dict[str, str] = {
    "dashboard": ('<rect x="3" y="3" width="7" height="9" rx="1.5"/>'
                  '<rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                  '<rect x="14" y="12" width="7" height="9" rx="1.5"/>'
                  '<rect x="3" y="16" width="7" height="5" rx="1.5"/>'),
    "sparkles": ('<path d="m12 3-1.9 5.8L4 10.7l6.1 1.9L12 18l1.9-5.4L20 10.7l-6.1-1.9z"/>'
                 '<path d="M5 3v4M3 5h4M19 17v4M17 19h4"/>'),
    "archive": ('<rect x="3" y="3" width="18" height="5" rx="1.5"/>'
                '<path d="M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8"/>'
                '<path d="M10 12h4"/>'),
    "link": ('<path d="M10 13a5 5 0 0 0 7.07 0l2.83-2.83a5 5 0 0 0-7.07-7.07L11 4.93"/>'
             '<path d="M14 11a5 5 0 0 0-7.07 0L4.1 13.83a5 5 0 0 0 7.07 7.07L13 19.07"/>'),
    "history": ('<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>'
                '<path d="M12 7v5l3 2"/>'),
    "settings": ('<circle cx="12" cy="12" r="3"/>'
                 '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>'),
    "home": ('<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
             '<path d="M9 22V12h6v10"/>'),
    "folder": ('<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>'),
    "package": ('<path d="m7.5 4.27 9 5.15"/>'
                '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
                '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'),
    "database": ('<ellipse cx="12" cy="5" rx="9" ry="3"/>'
                 '<path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>'),
    "refresh": ('<path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
                '<path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>'
                '<path d="M16 16h5v5"/>'),
    "layers": ('<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>'
               '<path d="m22 12.18-9.17 4.16a2 2 0 0 1-1.66 0L2 12.18"/>'
               '<path d="m22 17.18-9.17 4.16a2 2 0 0 1-1.66 0L2 17.18"/>'),
    "briefcase": ('<rect x="2" y="7" width="20" height="14" rx="2"/>'
                  '<path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>'),
    "drive": ('<line x1="22" y1="12" x2="2" y2="12"/>'
              '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
              '<line x1="6" y1="16" x2="6.01" y2="16"/><line x1="10" y1="16" x2="10.01" y2="16"/>'),
    "shield": ('<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'),
    "search": ('<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>'),
    "play": ('<polygon points="6 3 20 12 6 21 6 3"/>'),
    "pause": ('<rect x="6" y="4" width="4" height="16" rx="1"/>'
              '<rect x="14" y="4" width="4" height="16" rx="1"/>'),
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "alert": ('<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
              '<path d="M12 9v4"/><path d="M12 17h.01"/>'),
    "trash": ('<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
              '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
    "external": ('<path d="M15 3h6v6"/><path d="M10 14 21 3"/>'
                 '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'),
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "undo": ('<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>'),
    "download": ('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
                 '<path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>'),
    "clock": ('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    "filter": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "more": ('<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
             '<circle cx="5" cy="12" r="1"/>'),
    "info": ('<circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/>'
             '<path d="M12 8h.01"/>'),
    "cpu": ('<rect x="6" y="6" width="12" height="12" rx="2"/>'
            '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>'),
    "image": ('<rect x="3" y="3" width="18" height="18" rx="2"/>'
              '<circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>'),
    "film": ('<rect x="2" y="2" width="20" height="20" rx="2.5"/>'
             '<path d="M7 2v20M17 2v20M2 12h20M2 7h5M2 17h5M17 17h5M17 7h5"/>'),
    "file-archive": ('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
                     '<path d="M14 2v6h6"/><path d="M10 12h4M10 16h4"/>'),
    "server": ('<rect x="2" y="2" width="20" height="8" rx="2"/>'
               '<rect x="2" y="14" width="20" height="8" rx="2"/>'
               '<path d="M6 6h.01M6 18h.01"/>'),
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "lock": ('<rect x="3" y="11" width="18" height="11" rx="2"/>'
             '<path d="M7 11V7a5 5 0 0 1 10 0v4"/>'),
    "user": ('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>'
             '<circle cx="12" cy="7" r="4"/>'),
    "grid": ('<rect x="3" y="3" width="7" height="7" rx="1.5"/>'
             '<rect x="14" y="3" width="7" height="7" rx="1.5"/>'
             '<rect x="3" y="14" width="7" height="7" rx="1.5"/>'
             '<rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
    "sliders": ('<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3"/>'
                '<path d="M1 14h6M9 8h6M17 16h6"/>'),
    "save": ('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
             '<path d="M17 21v-8H7v8M7 3v5h8"/>'),
    "square": '<rect x="5" y="5" width="14" height="14" rx="1.5"/>',
    "copy": ('<rect x="9" y="9" width="13" height="13" rx="2"/>'
             '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
    "arrow-up-right": '<path d="M7 17 17 7"/><path d="M7 7h10v10"/>',
    "dot": '<circle cx="12" cy="12" r="4"/>',
    "loader": ('<path d="M21 12a9 9 0 1 1-6.2-8.5"/>'),
}


def _svg(name: str, color: str, stroke: float) -> str:
    body = _PATHS.get(name, _PATHS["dot"])
    fill = "none"
    if name in ("play", "filter", "zap", "dot"):
        fill = color
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="{fill}" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


@lru_cache(maxsize=512)
def icon_pixmap(name: str, color: str = theme.TEXT_2, size: int = 18,
                stroke: float = 1.8) -> QPixmap:
    svg = _svg(name, color, stroke)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    dpr = 2
    pix = QPixmap(int(size * dpr), int(size * dpr))
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def icon(name: str, color: str = theme.TEXT_2, size: int = 18,
         stroke: float = 1.8) -> QIcon:
    return QIcon(icon_pixmap(name, color, size, stroke))


@lru_cache(maxsize=32)
def logo_pixmap(size: int = 36) -> QPixmap:
    """品牌标记：青紫渐变圆角方块 + C 形环 + 青色光点。"""
    dpr = 2
    px = int(size * dpr)
    pix = QPixmap(px, px)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(1.5 * dpr, 1.5 * dpr, px - 3 * dpr, px - 3 * dpr)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#7C6CFF"))
    grad.setColorAt(0.55, QColor("#5B7CFA"))
    grad.setColorAt(1.0, QColor("#2DD4BF"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(rect, px * 0.28, px * 0.28)

    # C 形环
    pen = QPen(QColor(255, 255, 255, 235))
    pen.setWidthF(px * 0.085)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    ring = rect.adjusted(px * 0.24, px * 0.24, -px * 0.24, -px * 0.24)
    p.drawArc(ring, 42 * 16, 282 * 16)

    # 光点（C 的开口处）
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#A5F3FC"))
    dot = px * 0.075
    cx = rect.right() - px * 0.22
    cy = rect.center().y()
    p.drawEllipse(QRectF(cx - dot, cy - dot, dot * 2, dot * 2))
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def clear_cache() -> None:
    icon_pixmap.cache_clear()
    logo_pixmap.cache_clear()
