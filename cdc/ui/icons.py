"""新版图标系统：墨线 + 单点实色（duotone seal）几何图标。

统一 24×24 网格、1.8px 圆头描边；每个主图标只保留一个实色点缀，
与暖纸张 / 墨色 / 赭红的界面层级一致。
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from . import theme

_PATHS: dict[str, str] = {
    "dashboard": (
        '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/>'
        '<rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/>'
        '<rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/>'
        '<rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" fill="{a}" stroke="none"/>'
    ),
    "grid": (
        '<circle cx="5" cy="5" r="1.6"/><circle cx="12" cy="5" r="1.6"/>'
        '<circle cx="19" cy="5" r="1.6"/><circle cx="5" cy="12" r="1.6"/>'
        '<circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>'
        '<circle cx="5" cy="19" r="1.6"/><circle cx="12" cy="19" r="1.6"/>'
        '<circle cx="19" cy="19" r="1.6" fill="{a}" stroke="none"/>'
    ),
    "sparkles": (
        '<path d="M3.5 7A2.5 2.5 0 0 1 6 4.5h3l2 2.5h7A2.5 2.5 0 0 1 20.5 9.5v7A2.5 2.5 0 0 1 18 19H6a2.5 2.5 0 0 1-2.5-2.5z"/>'
        '<path d="M12 10v5"/><path d="m9.4 12.6 2.6 2.6 2.6-2.6"/>'
        '<circle cx="12" cy="18" r="1.2" fill="{a}" stroke="none"/>'
    ),
    "archive": (
        '<rect x="3" y="4" width="18" height="5" rx="1.5"/>'
        '<path d="M5 9v8.5A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5V9"/>'
        '<rect x="10" y="12.5" width="4" height="2.6" rx="1.3" fill="{a}" stroke="none"/>'
    ),
    "link": (
        '<path d="M9.5 14.5 7.8 16.2a4 4 0 0 1-5.6-5.6l2.6-2.6a4 4 0 0 1 5.6 0"/>'
        '<path d="m14.5 9.5 1.7-1.7a4 4 0 0 1 5.6 5.6l-2.6 2.6a4 4 0 0 1-5.6 0"/>'
        '<circle cx="12" cy="12" r="2" fill="{a}" stroke="none"/>'
    ),
    "history": (
        '<circle cx="12" cy="12" r="8.5"/>'
        '<path d="M12 7.5v5l3.2 1.9"/>'
        '<circle cx="12" cy="12" r="1.6" fill="{a}" stroke="none"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="8.5"/>'
        '<path d="M12 7.5v5l3.2 1.9"/>'
    ),
    "settings": (
        '<path d="M3 6h7M14 6h7M3 12h3M10 12h11M3 18h11M18 18h3"/>'
        '<circle cx="12" cy="6" r="2" fill="{a}" stroke="{a}"/>'
        '<circle cx="8" cy="12" r="2" fill="{a}" stroke="{a}"/>'
        '<circle cx="16" cy="18" r="2" fill="{a}" stroke="{a}"/>'
    ),
    "sliders": (
        '<path d="M4 21v-6M4 9V3M12 21v-8M12 7V3M20 21v-4M20 11V3"/>'
        '<path d="M1.5 13h5M9.5 9h5M17.5 15h5"/>'
        '<circle cx="4" cy="15" r="1.8" fill="{a}" stroke="none"/>'
        '<circle cx="12" cy="11" r="1.8" fill="{a}" stroke="none"/>'
        '<circle cx="20" cy="17" r="1.8" fill="{a}" stroke="none"/>'
    ),
    "home": (
        '<path d="m3.5 10 8.5-7 8.5 7v9a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>'
        '<path d="M9.5 21v-6h5v6"/>'
        '<rect x="10.8" y="16" width="2.4" height="2.4" rx="0.8" fill="{a}" stroke="none"/>'
    ),
    "folder": (
        '<path d="M3.5 6.5A2.5 2.5 0 0 1 6 4h3l2 2.5h7A2.5 2.5 0 0 1 20.5 9v7.5A2.5 2.5 0 0 1 18 19H6a2.5 2.5 0 0 1-2.5-2.5z"/>'
        '<rect x="6.5" y="11" width="4.2" height="2.6" rx="1.3" fill="{a}" stroke="none"/>'
    ),
    "package": (
        '<path d="M20.5 8.2v7.6a2 2 0 0 1-1 1.7l-6.5 3.7a2 2 0 0 1-2 0l-6.5-3.7a2 2 0 0 1-1-1.7V8.2a2 2 0 0 1 1-1.7l6.5-3.7a2 2 0 0 1 2 0l6.5 3.7a2 2 0 0 1 1 1.7z"/>'
        '<path d="m4 7 8 4.6L20 7"/><path d="M12 21.2V11.6"/>'
        '<rect x="9.5" y="13.8" width="5" height="2.6" rx="1.3" fill="{a}" stroke="none"/>'
    ),
    "database": (
        '<ellipse cx="12" cy="6" rx="7.5" ry="3"/>'
        '<path d="M4.5 6v12c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3V6"/>'
        '<path d="M4.5 12c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3"/>'
        '<rect x="9" y="10.7" width="6" height="2.6" rx="1.3" fill="{a}" stroke="none"/>'
    ),
    "refresh": (
        '<path d="M20.5 12a8.5 8.5 0 0 1-14.5 6l-3-3"/>'
        '<path d="M3 20.5v-5.5h5.5"/>'
        '<path d="M3.5 12A8.5 8.5 0 0 1 18 6l3 3"/>'
        '<path d="M21 3.5V9h-5.5"/>'
        '<circle cx="12" cy="12" r="2" fill="{a}" stroke="none"/>'
    ),
    "layers": (
        '<path d="m12 3 9 4.5-9 4.5-9-4.5z" fill="{a}" stroke="none"/>'
        '<path d="m12 3 9 4.5-9 4.5-9-4.5z"/>'
        '<path d="m3 12 9 4.5 9-4.5"/>'
        '<path d="m3 16.5 9 4.5 9-4.5"/>'
    ),
    "briefcase": (
        '<rect x="3" y="7.5" width="18" height="12.5" rx="2.5"/>'
        '<path d="M8.5 7.5V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v1.5"/>'
        '<rect x="9.8" y="12" width="4.4" height="3" rx="1.2" fill="{a}" stroke="none"/>'
    ),
    "drive": (
        '<rect x="3" y="5" width="18" height="14" rx="2.5"/>'
        '<path d="M3 13.5h18"/>'
        '<circle cx="7" cy="16.6" r="1.2" fill="{a}" stroke="none"/>'
        '<path d="M11 16.6h6"/>'
    ),
    "shield": (
        '<path d="M12 3 20 6v5.5c0 4.5-3.4 7.7-8 9-4.6-1.3-8-4.5-8-9V6z"/>'
        '<path d="m8.3 12 2.4 2.4 5-5.2" stroke="{a}"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="6.5"/>'
        '<path d="m16 16 4.5 4.5"/>'
        '<circle cx="11" cy="11" r="2" fill="{a}" stroke="none"/>'
    ),
    "play": '<path d="M8 5.5v13l10-6.5z" fill="{a}" stroke="{a}"/>',
    "pause": (
        '<rect x="7" y="5" width="3.4" height="14" rx="1.2" fill="{a}" stroke="{a}"/>'
        '<rect x="13.6" y="5" width="3.4" height="14" rx="1.2" fill="{a}" stroke="{a}"/>'
    ),
    "check": '<path d="M4 12.5 9.5 18 20 6.5" stroke-width="2.3"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18" stroke-width="2.1"/>',
    "alert": (
        '<path d="M12 3.5 21 19.5H3z"/>'
        '<path d="M12 9v4.5"/>'
        '<circle cx="12" cy="17" r="1.2" fill="{a}" stroke="none"/>'
    ),
    "trash": (
        '<path d="M4 7h16"/>'
        '<path d="M9 7V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v2"/>'
        '<path d="m6 7 1 12a2 2 0 0 0 2 1.8h6a2 2 0 0 0 2-1.8l1-12"/>'
        '<rect x="10" y="11" width="4" height="5" rx="1" fill="{a}" stroke="none"/>'
    ),
    "external": (
        '<path d="M14 4h6v6"/><path d="M20 4 11 13"/>'
        '<path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>'
        '<circle cx="20" cy="4" r="1.6" fill="{a}" stroke="none"/>'
    ),
    "arrow-right": (
        '<path d="M4 12h15"/><path d="m13 6 6 6-6 6"/>'
        '<circle cx="4" cy="12" r="1.4" fill="{a}" stroke="none"/>'
    ),
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "undo": (
        '<path d="M8.5 5 3 10l5.5 5"/>'
        '<path d="M3 10h10a6 6 0 0 1 0 12h-2"/>'
        '<circle cx="8.5" cy="5" r="1.4" fill="{a}" stroke="none"/>'
    ),
    "download": (
        '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/>'
        '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>'
        '<rect x="10" y="17" width="4" height="2.4" rx="1.2" fill="{a}" stroke="none"/>'
    ),
    "filter": (
        '<path d="M3.5 5h17l-6.5 7.5V20l-4-2v-5.5z"/>'
        '<circle cx="12" cy="9" r="1.5" fill="{a}" stroke="none"/>'
    ),
    "plus": '<path d="M12 5v14M5 12h14" stroke-width="2.1"/>',
    "minus": '<path d="M5 12h14" stroke-width="2.1"/>',
    "more": (
        '<circle cx="5" cy="12" r="1.6" fill="{a}" stroke="none"/>'
        '<circle cx="12" cy="12" r="1.6" fill="{a}" stroke="none"/>'
        '<circle cx="19" cy="12" r="1.6" fill="{a}" stroke="none"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="8.5"/>'
        '<path d="M12 11v5"/>'
        '<circle cx="12" cy="8" r="1.2" fill="{a}" stroke="none"/>'
    ),
    "cpu": (
        '<rect x="6" y="6" width="12" height="12" rx="2"/>'
        '<path d="M9.5 2v4M14.5 2v4M9.5 18v4M14.5 18v4M2 9.5h4M2 14.5h4M18 9.5h4M18 14.5h4"/>'
        '<rect x="10" y="10" width="4" height="4" rx="1" fill="{a}" stroke="none"/>'
    ),
    "image": (
        '<rect x="3" y="3" width="18" height="18" rx="2.5"/>'
        '<circle cx="9" cy="9" r="2" fill="{a}" stroke="none"/>'
        '<path d="m21 15-3.4-3.4a2 2 0 0 0-2.8 0L6 21"/>'
    ),
    "film": (
        '<rect x="2.5" y="3" width="19" height="18" rx="2.5"/>'
        '<path d="M7 3v18M17 3v18M2.5 12h19M2.5 7h4.5M2.5 17h4.5M17 17h4.5M17 7h4.5"/>'
        '<rect x="9.5" y="9.5" width="5" height="5" rx="1" fill="{a}" stroke="none"/>'
    ),
    "file-archive": (
        '<path d="M14 2.5H6A2 2 0 0 0 4 4.5v15A2 2 0 0 0 6 21.5h12a2 2 0 0 0 2-2V8.5z"/>'
        '<path d="M14 2.5v6h6"/>'
        '<path d="M10 11h4M10 15h4"/>'
        '<rect x="10" y="12.6" width="4" height="1.8" rx="0.9" fill="{a}" stroke="none"/>'
    ),
    "server": (
        '<rect x="2.5" y="3" width="19" height="7.5" rx="2"/>'
        '<rect x="2.5" y="13.5" width="19" height="7.5" rx="2"/>'
        '<circle cx="6.5" cy="6.8" r="1.2" fill="{a}" stroke="none"/>'
        '<circle cx="6.5" cy="17.2" r="1.2" fill="{a}" stroke="none"/>'
        '<path d="M11 6.8h6M11 17.2h6"/>'
    ),
    "zap": '<path d="M13 2.5 4 14h7l-1 7.5L20 10h-7z" fill="{a}" stroke="{a}"/>',
    "lock": (
        '<rect x="4" y="10.5" width="16" height="10.5" rx="2.5"/>'
        '<path d="M7.5 10.5V7a4.5 4.5 0 0 1 9 0v3.5"/>'
        '<circle cx="12" cy="15.5" r="1.8" fill="{a}" stroke="none"/>'
    ),
    "user": (
        '<circle cx="12" cy="7.5" r="4"/>'
        '<path d="M4 21v-2a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v2"/>'
        '<circle cx="12" cy="7.5" r="1.5" fill="{a}" stroke="none"/>'
    ),
    "save": (
        '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>'
        '<path d="M7 3v6h8V3"/>'
        '<rect x="8" y="14" width="8" height="6" rx="1" fill="{a}" stroke="none"/>'
    ),
    "square": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "copy": (
        '<rect x="8.5" y="8.5" width="12" height="12" rx="2"/>'
        '<rect x="3.5" y="3.5" width="12" height="12" rx="2" fill="{a}" stroke="none"/>'
        '<rect x="3.5" y="3.5" width="12" height="12" rx="2"/>'
    ),
    "arrow-up-right": (
        '<path d="M7 17 17 7"/><path d="M8 7h9v9"/>'
        '<circle cx="19" cy="5" r="1.4" fill="{a}" stroke="none"/>'
    ),
    "dot": '<circle cx="12" cy="12" r="4" fill="{a}" stroke="none"/>',
    "loader": '<path d="M21 12a9 9 0 1 1-6.2-8.5"/>',
}

# 同形别名
_PATHS["overview"] = _PATHS["dashboard"]
_PATHS["slimming"] = _PATHS["sparkles"]


def _svg(name: str, color: str, accent: str, stroke: float) -> str:
    body = _PATHS.get(name, _PATHS["dot"]).replace("{a}", accent)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


@lru_cache(maxsize=1024)
def icon_pixmap(name: str, color: str = theme.TEXT_2, size: int = 18,
                accent: str | None = None, stroke: float = 1.8) -> QPixmap:
    accent = accent or color
    svg = _svg(name, color, accent, stroke)
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
         accent: str | None = None, stroke: float = 1.8) -> QIcon:
    return QIcon(icon_pixmap(name, color, size, accent, stroke))


@lru_cache(maxsize=32)
def logo_pixmap(size: int = 36) -> QPixmap:
    """品牌标记：赭红底色 + 奶油色 C 形环 + 橄榄色光点。"""
    dpr = 2
    px = int(size * dpr)
    pix = QPixmap(px, px)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(1.5 * dpr, 1.5 * dpr, px - 3 * dpr, px - 3 * dpr)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor("#C25B3B"))
    grad.setColorAt(0.55, QColor("#B44A2D"))
    grad.setColorAt(1.0, QColor("#943A25"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(rect, px * 0.27, px * 0.27)

    # 内侧高光
    p.setBrush(QColor(255, 248, 240, 18))
    p.drawRoundedRect(rect.adjusted(px * 0.06, px * 0.06, -px * 0.06, -px * 0.06),
                      px * 0.23, px * 0.23)

    # 奶油色 C 形环
    pen = QPen(QColor("#FFF6E9"))
    pen.setWidthF(px * 0.088)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    ring = rect.adjusted(px * 0.25, px * 0.25, -px * 0.25, -px * 0.25)
    p.drawArc(ring, 42 * 16, 282 * 16)

    # 橄榄色光点（C 的开口处）
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#C6C79A"))
    dot = px * 0.078
    cx = rect.right() - px * 0.22
    cy = rect.center().y()
    p.drawEllipse(QRectF(cx - dot, cy - dot, dot * 2, dot * 2))
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def clear_cache() -> None:
    icon_pixmap.cache_clear()
    logo_pixmap.cache_clear()
