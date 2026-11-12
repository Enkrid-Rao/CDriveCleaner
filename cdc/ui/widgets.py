"""可复用 UI 组件：卡片、导航、仪表、进度、确认弹窗、Toast。"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRectF, QSize, Qt,
    QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap, QMouseEvent, QPaintEvent, QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QDialog, QFrame,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)

from . import icons, theme


# ============================================================
# 基础工具
# ============================================================

def hbox(*widgets: QWidget, spacing: int = 8,
         margins: tuple[int, int, int, int] = (0, 0, 0, 0),
         stretch_last: bool = False) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    if stretch_last:
        layout.addStretch()
    return layout


def vbox(*widgets: QWidget, spacing: int = 8,
         margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return layout


def label(text: str = "", object_name: str = "Body",
          wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(object_name)
    lbl.setWordWrap(wrap)
    return lbl


def add_shadow(widget: QWidget, blur: int = 28, y: int = 8,
               alpha: int = 110) -> None:
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(0, 0, 0, alpha))
    shadow.setOffset(0, y)
    widget.setGraphicsEffect(shadow)


def hline() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Divider")
    frame.setFixedHeight(1)
    return frame


def clear_layout(layout) -> None:
    """立即移出并删除布局内控件（deleteLater 延迟会让新旧内容重叠）。"""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
            continue
        child = item.layout()
        if child is not None:
            clear_layout(child)


class ElidedLabel(QLabel):
    """按可用宽度省略中间/末尾的路径文本。"""

    def __init__(self, text: str = "", object_name: str = "Mono",
                 mode: Qt.TextElideMode = Qt.ElideMiddle) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setText(text)

    def set_full_text(self, text: str) -> None:
        self._full = text or ""
        self._refresh()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        metrics = QFontMetrics(self.font())
        width = max(20, self.width() - 2)
        super().setText(metrics.elidedText(self._full, self._mode, width))
        self.setToolTip(self._full)


class Pill(QLabel):
    """小标签：区域 / 状态 / 介质类型。"""

    def __init__(self, text: str = "", tone: str = "muted",
                 icon_name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self._tone = tone
        self._icon = icon_name
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        color = theme.tone_color(tone)
        bg = theme.TONE_BG.get(tone, theme.TONE_BG["muted"])
        border = theme.TONE_BORDER.get(tone, theme.TONE_BORDER["muted"])
        self.setStyleSheet(
            f"QLabel#Pill {{ color:{color}; background:{bg}; "
            f"border:1px solid {border}; border-radius:8px; "
            f"padding:2px 8px; font-size:10px; font-weight:700; }}"
        )

    def set_text(self, text: str) -> None:
        self.setText(text)


class Check(QAbstractButton):
    """自绘复选框（比 QCheckBox 的 indicator 更可控）。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.valueChanged.connect(self._set_hover)

    def _set_hover(self, value: Any) -> None:
        self._hover = float(value)
        self.update()

    def enterEvent(self, event: QEvent) -> None:
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._animate(0.0)
        super().leaveEvent(event)

    def _animate(self, target: float) -> None:
        if not theme.MOTION:
            self._hover = target
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        width = 22 + (metrics.horizontalAdvance(self.text()) + 8 if self.text() else 0)
        return QSize(max(22, width), 22)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, (self.height() - 18) / 2, 18, 18)
        if self.isChecked():
            grad = QLinearGradient(box.topLeft(), box.bottomRight())
            grad.setColorAt(0, QColor(theme.BRAND))
            grad.setColorAt(1, QColor(theme.BRAND_2))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        else:
            p.setBrush(QColor(10, 16, 28, 230))
            p.setPen(QPen(QColor(255, 255, 255, 40 + int(40 * self._hover)), 1))
        p.drawRoundedRect(box, 5.5, 5.5)
        if self.isChecked():
            pen = QPen(QColor(255, 255, 255), 2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            path = QPainterPath()
            path.moveTo(5.0, 10.8)
            path.lineTo(8.8, 14.2)
            path.lineTo(14.6, 6.4)
            p.drawPath(path)
        if self.text():
            p.setPen(QColor(theme.TEXT_2))
            p.setFont(self.font())
            p.drawText(QRectF(26, 0, self.width() - 26, self.height()),
                       Qt.AlignVCenter | Qt.AlignLeft, self.text())
        p.end()


class IconTile(QWidget):
    """圆角底色 + 矢量图标的小方块。"""

    def __init__(self, icon_name: str, tone: str = "brand", size: int = 38,
                 icon_size: int = 18, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon_name
        self._tone = tone
        self._icon_size = icon_size
        self.setFixedSize(size, size)

    def set_icon(self, name: str) -> None:
        self._icon = name
        self.update()

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.setBrush(QColor(theme.tone_color(self._tone)))
        p.setOpacity(0.13)
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        p.setOpacity(1.0)
        pix = icons.icon_pixmap(self._icon, theme.tone_color(self._tone),
                                self._icon_size)
        target = QRectF((self.width() - self._icon_size) / 2,
                        (self.height() - self._icon_size) / 2,
                        self._icon_size, self._icon_size)
        p.drawPixmap(target.toRect(), pix)
        p.end()


class GlassCard(QFrame):
    def __init__(self, padding: int = 18, spacing: int = 12,
                 object_name: str = "Card", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(spacing)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout: Any, stretch: int = 0) -> Any:
        self.body.addLayout(layout, stretch)
        return layout


class SectionHeader(QWidget):
    def __init__(self, title: str, hint: str = "",
                 actions: Iterable[QWidget] = ()) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        text_box.addWidget(label(title, "SectionTitle"))
        if hint:
            text_box.addWidget(label(hint, "SectionHint"))
        layout.addLayout(text_box)
        layout.addStretch()
        for action in actions:
            layout.addWidget(action)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str,
                 actions: Iterable[QWidget] = ()) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(14)
        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        text_box.addWidget(label(title, "PageTitle"))
        text_box.addWidget(label(subtitle, "PageSubtitle"))
        layout.addLayout(text_box)
        layout.addStretch()
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(8)
        for action in actions:
            self.action_layout.addWidget(action)
        layout.addLayout(self.action_layout)

    def add_action(self, widget: QWidget) -> None:
        self.action_layout.addWidget(widget)


class ScrollPage(QWidget):
    """带滚动内容区的页面容器。"""

    def __init__(self, parent: QWidget | None = None,
                 margins: tuple[int, int, int, int] = (30, 24, 30, 30),
                 spacing: int = 18) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QScrollArea
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("PageRoot")
        self.content = QVBoxLayout(inner)
        self.content.setContentsMargins(*margins)
        self.content.setSpacing(spacing)
        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)
        self.inner = inner

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.content.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout: Any, stretch: int = 0) -> Any:
        self.content.addLayout(layout, stretch)
        return layout

    def add_stretch(self) -> None:
        self.content.addStretch()


class SearchField(QLineEdit):
    def __init__(self, placeholder: str = "搜索…",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(180)
        self.addAction(icons.icon("search", theme.MUT, 15),
                       QLineEdit.LeadingPosition)
        self.setStyleSheet(
            f"QLineEdit {{ background:{theme.INPUT}; border:1px solid {theme.BORDER_HI}; "
            f"border-radius:10px; padding:7px 10px 7px 4px; color:{theme.TEXT}; }}"
            f"QLineEdit:focus {{ border:1px solid rgba(109,94,248,0.7); }}"
        )


class SegmentedControl(QFrame):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]],
                 value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SegContainer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._buttons: dict[str, QPushButton] = {}
        from PySide6.QtWidgets import QButtonGroup
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, text in options:
            btn = QPushButton(text)
            btn.setObjectName("SegBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._select(k))
            self._group.addButton(btn)
            layout.addWidget(btn)
            self._buttons[key] = btn
        self.set_value(value or (options[0][0] if options else ""))

    def _select(self, key: str) -> None:
        self.set_value(key)
        self.changed.emit(key)

    def set_value(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is None:
            return
        btn.setChecked(True)

    def value(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return ""


class Toggle(QAbstractButton):
    """开关控件。"""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 24)
        self._pos = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._on_toggle)

    def _set_pos(self, value: Any) -> None:
        self._pos = float(value)
        self.update()

    def _on_toggle(self, checked: bool) -> None:
        if not theme.MOTION:
            self._pos = 1.0 if checked else 0.0
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:
        return QSize(42, 24)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(1, 3, self.width() - 2, self.height() - 6)
        if self.isChecked():
            grad = QLinearGradient(track.topLeft(), track.topRight())
            grad.setColorAt(0, QColor(theme.BRAND))
            grad.setColorAt(1, QColor(theme.BRAND_2))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
        else:
            p.setBrush(QColor(255, 255, 255, 22))
            p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        x = track.left() + 3 + self._pos * (track.width() - track.height())
        knob = QRectF(x, track.top() + 2, track.height() - 4, track.height() - 4)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(knob)
        p.end()


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str = "",
                 color: str = theme.MUT, size: int = 30,
                 icon_size: int = 16, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("IconBtn")
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(icons.icon(icon_name, color, icon_size))
        self.setIconSize(QSize(icon_size, icon_size))
        if tooltip:
            self.setToolTip(tooltip)


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, subtitle: str,
                 action: QWidget | None = None, tone: str = "muted") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 34, 20, 34)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)
        tile = IconTile(icon_name, tone, 62, 28)
        layout.addWidget(tile, alignment=Qt.AlignCenter)
        t = label(title, "CardTitle")
        t.setAlignment(Qt.AlignCenter)
        layout.addWidget(t)
        s = label(subtitle, "Muted", wrap=True)
        s.setAlignment(Qt.AlignCenter)
        s.setMaximumWidth(440)
        layout.addWidget(s, alignment=Qt.AlignCenter)
        self.title_label = t
        self.subtitle_label = s
        self.action_widget = action
        if action is not None:
            layout.addSpacing(6)
            layout.addWidget(action, alignment=Qt.AlignCenter)


# ============================================================
# 数据可视化
# ============================================================

def drive_tone(letter: str) -> str:
    letter = (letter or "").upper()[:1]
    return {"C": "c", "D": "d", "E": "e"}.get(letter, "brand")


class UsageBar(QWidget):
    """圆角使用率条，按语义色渐变。"""

    def __init__(self, value: float = 0.0, tone: str = "brand",
                 height: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = max(0.0, min(1.0, value))
        self._tone = tone
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, value: Any) -> None:
        self._value = float(value)
        self.update()

    def set_value(self, value: float, animate: bool = False) -> None:
        value = max(0.0, min(1.0, float(value or 0)))
        if animate and theme.MOTION:
            self._anim.stop()
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(value)
            self._anim.start()
        else:
            self._value = value
            self.update()

    def value(self) -> float:
        return self._value

    def _colors(self) -> tuple[QColor, QColor]:
        tone = self._tone
        if tone == "c":
            return QColor(theme.GREEN), QColor(theme.ROSE) if self._value > 0.82 else QColor(theme.AMBER)
        if tone == "d":
            return QColor(theme.BRAND_3), QColor(theme.BRAND_2)
        if tone == "e":
            return QColor(theme.TEAL), QColor(theme.CYAN)
        if tone == "green":
            return QColor(theme.GREEN), QColor(theme.TEAL)
        if tone == "amber":
            return QColor(theme.AMBER), QColor(theme.ORANGE)
        return QColor(theme.BRAND), QColor(theme.BRAND_2)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        radius = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 20))
        p.drawRoundedRect(rect, radius, radius)
        if self._value <= 0.001:
            return
        width = max(self.height(), rect.width() * self._value)
        fill = QRectF(0, 0, width, self.height())
        c1, c2 = self._colors()
        grad = QLinearGradient(fill.topLeft(), fill.topRight())
        grad.setColorAt(0, c1)
        grad.setColorAt(1, c2)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(fill, radius, radius)
        p.end()


class Gauge(QWidget):
    """环形空间仪表。"""

    def __init__(self, size: int = 170, tone: str = "c",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._tone = tone
        self._top = "0%"
        self._caption = "已使用"
        self.setFixedSize(size, size)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, value: Any) -> None:
        self._value = float(value)
        self.update()

    def set_data(self, ratio: float, top: str | None = None,
                 caption: str | None = None, animate: bool = True) -> None:
        ratio = max(0.0, min(1.0, float(ratio or 0)))
        if top is not None:
            self._top = top
        if caption is not None:
            self._caption = caption
        if animate and theme.MOTION:
            self._anim.stop()
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(ratio)
            self._anim.start()
        else:
            self._value = ratio
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        rect = QRectF(14, 14, side - 28, side - 28)
        start = 225 * 16
        span = 270 * 16
        # 轨道
        pen = QPen(QColor(255, 255, 255, 20), 11)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, start, span)
        # 进度
        value_span = int(span * self._value)
        if value_span > 0:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0, QColor(theme.GREEN))
            grad.setColorAt(0.55, QColor(theme.AMBER))
            grad.setColorAt(1, QColor(theme.ROSE))
            pen = QPen(QBrush(grad), 11)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, start, value_span)
            # 端点光晕
            angle = math.radians(225 + 270 * self._value)
            cx = rect.center().x() + (rect.width() / 2) * math.cos(angle)
            cy = rect.center().y() - (rect.height() / 2) * math.sin(angle)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))
        # 中心文字
        p.setPen(QColor(theme.TEXT))
        font = QFont("JetBrains Mono", 24)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, side * 0.30, side, side * 0.26),
                   Qt.AlignCenter, self._top)
        p.setPen(QColor(theme.MUT))
        font2 = QFont("Microsoft YaHei UI", 9)
        p.setFont(font2)
        p.drawText(QRectF(0, side * 0.53, side, 22),
                   Qt.AlignCenter, self._caption)
        p.end()


class StatTile(QFrame):
    def __init__(self, icon_name: str, title: str, value: str = "—",
                 hint: str = "", tone: str = "brand",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardSoft")
        self.setMinimumHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        self.tile = IconTile(icon_name, tone, 38, 18)
        layout.addWidget(self.tile, alignment=Qt.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(3)
        self.title_label = label(title, "Label")
        self.value_label = label(value, "ValueSmall")
        self.hint_label = label(hint, "Dim")
        box.addWidget(self.title_label)
        box.addWidget(self.value_label)
        box.addWidget(self.hint_label)
        box.addStretch()
        layout.addLayout(box, 1)

    def set_value(self, text: str, hint: str | None = None) -> None:
        self.value_label.setText(text)
        if hint is not None:
            self.hint_label.setText(hint)

    def set_tone(self, tone: str) -> None:
        self.tile.set_tone(tone)


class DriveCard(QFrame):
    clicked = Signal(str)

    def __init__(self, drive: Any, selectable: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.drive = drive
        self.selectable = selectable
        self.setObjectName("DriveCard")
        self.setProperty("selected", False)
        self.setMinimumHeight(126)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        if selectable:
            self.setCursor(Qt.PointingHandCursor)
        tone = drive_tone(drive.letter)
        color = theme.tone_color(tone)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(9)
        badge = QLabel(drive.letter)
        badge.setFixedSize(30, 30)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"background:{theme.TONE_BG.get(tone, theme.TONE_BG['brand'])};"
            f"color:{color};border:1px solid {theme.TONE_BORDER.get(tone, theme.BORDER_HI)};"
            "border-radius:9px;font-family:'JetBrains Mono';font-size:14px;font-weight:800;"
        )
        top.addWidget(badge)
        name_box = QVBoxLayout()
        name_box.setSpacing(0)
        name = QLabel(drive.label or f"{drive.letter} 盘")
        name.setStyleSheet(f"color:{theme.TEXT};font-size:12px;font-weight:700;")
        media = QLabel(drive.media_label)
        media.setStyleSheet(f"color:{theme.DIM};font-size:9px;")
        name_box.addWidget(name)
        name_box.addWidget(media)
        top.addLayout(name_box)
        top.addStretch()
        pct = QLabel(f"{int(round(drive.used_ratio * 100))}%")
        pct.setStyleSheet(
            f"color:{color};font-family:'JetBrains Mono';font-size:12px;font-weight:700;"
        )
        top.addWidget(pct)
        self.check_badge = QLabel()
        self.check_badge.setPixmap(icons.icon_pixmap("check", color, 14))
        self.check_badge.setFixedSize(16, 16)
        self.check_badge.hide()
        top.addWidget(self.check_badge)
        layout.addLayout(top)

        free_gb = drive.free_bytes / 1024 ** 3
        total_gb = drive.total_bytes / 1024 ** 3
        self.free_label = QLabel(f"{free_gb:.1f} GB")
        self.free_label.setStyleSheet(
            f"color:{theme.TEXT};font-family:'JetBrains Mono';font-size:18px;font-weight:700;"
        )
        layout.addWidget(self.free_label)
        self.bar = UsageBar(drive.used_ratio, tone, 7)
        layout.addWidget(self.bar)
        self.caption = QLabel(f"可用 · 总容量 {total_gb:.0f} GB")
        self.caption.setStyleSheet(f"color:{theme.DIM};font-size:9px;")
        layout.addWidget(self.caption)
        self.setToolTip(f"{drive.root}\n{drive.model or drive.media_label}")

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        self.style().unpolish(self)
        self.style().polish(self)
        if hasattr(self, "check_badge"):
            self.check_badge.setVisible(bool(selected))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.selectable and event.button() == Qt.LeftButton:
            self.clicked.emit(self.drive.letter)
        super().mousePressEvent(event)


class DriveMiniCard(QFrame):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardInset")
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 11)
        layout.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.letter = QLabel("C")
        self.letter.setStyleSheet(
            f"color:{theme.ROSE};font-family:'JetBrains Mono';font-size:11px;"
            "font-weight:800;background:rgba(251,113,133,0.12);"
            "border:1px solid rgba(251,113,133,0.25);border-radius:6px;padding:1px 6px;"
        )
        top.addWidget(self.letter)
        self.title = QLabel("系统盘")
        self.title.setStyleSheet(f"color:{theme.MUT};font-size:10px;")
        top.addWidget(self.title)
        top.addStretch()
        self.pct = QLabel("—")
        self.pct.setStyleSheet(
            f"color:{theme.TEXT_2};font-family:'JetBrains Mono';font-size:10px;font-weight:700;"
        )
        top.addWidget(self.pct)
        layout.addLayout(top)
        self.free = QLabel("—")
        self.free.setStyleSheet(
            f"color:{theme.TEXT};font-family:'JetBrains Mono';font-size:15px;font-weight:700;"
        )
        layout.addWidget(self.free)
        self.bar = UsageBar(0, "c", 5)
        layout.addWidget(self.bar)
        self.caption = QLabel("可用空间")
        self.caption.setStyleSheet(f"color:{theme.DIM};font-size:9px;")
        layout.addWidget(self.caption)

    def update_drive(self, drive: Any) -> None:
        if drive is None:
            return
        self.letter.setText(drive.letter)
        self.title.setText("系统盘" if drive.is_system else "数据盘")
        self.pct.setText(f"{int(round(drive.used_ratio * 100))}%")
        self.free.setText(f"{drive.free_bytes / 1024 ** 3:.1f} GB")
        self.bar.set_value(drive.used_ratio, animate=True)
        self.caption.setText(f"可用 · 共 {drive.total_bytes / 1024 ** 3:.0f} GB")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ============================================================
# 侧边栏
# ============================================================

class NavButton(QAbstractButton):
    def __init__(self, key: str, icon_name: str, text: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.icon_name = icon_name
        self._text = text
        self._active = False
        self._hover = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setFixedHeight(43)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(130)
        self._anim.valueChanged.connect(self._on_hover)
        self.clicked.connect(lambda: self.set_active(True))

    def _on_hover(self, value: Any) -> None:
        self._hover = float(value)
        self.update()

    def enterEvent(self, event: QEvent) -> None:
        self._hover_anim(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._hover_anim(0.0)
        super().leaveEvent(event)

    def _hover_anim(self, target: float) -> None:
        if not theme.MOTION:
            self._hover = target
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(190, 43)

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 1, self.width(), self.height() - 2)
        if self._active:
            grad = QLinearGradient(rect.topLeft(), rect.topRight())
            grad.setColorAt(0, QColor(109, 94, 248, 58))
            grad.setColorAt(1, QColor(56, 189, 248, 10))
            p.setBrush(QBrush(grad))
            p.setPen(QPen(QColor(124, 108, 255, 70), 1))
            p.drawRoundedRect(rect, 10, 10)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.BRAND_2))
            p.drawRoundedRect(QRectF(0, self.height() / 2 - 9, 3, 18), 1.5, 1.5)
        elif self._hover > 0.01:
            p.setBrush(QColor(255, 255, 255, int(12 * self._hover)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, 10, 10)
        color = theme.TEXT if self._active else (
            theme.TEXT_2 if self._hover > 0.4 else theme.MUT)
        pix = icons.icon_pixmap(self.icon_name, color, 18)
        p.drawPixmap(QRectF(14, (self.height() - 18) / 2, 18, 18).toRect(), pix)
        font = QFont("Microsoft YaHei UI", 11)
        font.setWeight(QFont.Medium if self._active else QFont.Normal)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(44, 0, self.width() - 50, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.end()


class Sidebar(QFrame):
    navigate = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 16, 13, 14)
        layout.setSpacing(6)

        # Logo
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 2, 4, 10)
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(36))
        logo.setFixedSize(36, 36)
        brand.addWidget(logo)
        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        name = QLabel("CDriveCleaner")
        name.setObjectName("AppName")
        tag = QLabel("C 盘瘦身 · 冷数据归档")
        tag.setObjectName("AppTag")
        text_box.addWidget(name)
        text_box.addWidget(tag)
        brand.addLayout(text_box)
        layout.addLayout(brand)

        self._buttons: dict[str, NavButton] = {}
        layout.addWidget(self._group_label("空间"))
        for key, icon_name, text in [
            ("dashboard", "dashboard", "总览"),
            ("slimming", "sparkles", "C 盘瘦身"),
            ("archive", "archive", "冷数据归档"),
        ]:
            self._add_nav(layout, key, icon_name, text)

        layout.addSpacing(10)
        layout.addWidget(self._group_label("系统"))
        for key, icon_name, text in [
            ("links", "link", "链接管理"),
            ("history", "history", "操作记录"),
            ("settings", "sliders", "设置"),
        ]:
            self._add_nav(layout, key, icon_name, text)

        layout.addStretch()
        self.mini = DriveMiniCard()
        self.mini.clicked.connect(lambda: self.navigate.emit("dashboard"))
        layout.addWidget(self.mini)
        layout.addSpacing(4)
        from ..version import __version__
        version = QLabel(f"v{__version__}  ·  MIT License")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet(f"color:{theme.DIM};font-size:9px;")
        layout.addWidget(version)

    @staticmethod
    def _group_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SidebarGroup")
        lbl.setContentsMargins(14, 4, 0, 2)
        return lbl

    def _add_nav(self, layout: QVBoxLayout, key: str, icon_name: str,
                 text: str) -> None:
        btn = NavButton(key, icon_name, text)
        btn.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
        layout.addWidget(btn)
        self._buttons[key] = btn

    def set_active(self, key: str) -> None:
        for name, btn in self._buttons.items():
            btn.set_active(name == key)

    def set_drive(self, drive: Any) -> None:
        self.mini.update_drive(drive)


# ============================================================
# Toast
# ============================================================

class Toast(QFrame):
    def __init__(self, text: str, kind: str = "info",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        colors = {
            "success": (theme.GREEN, "check"),
            "error": (theme.RED, "x"),
            "warn": (theme.AMBER, "alert"),
            "info": (theme.BRAND_2, "info"),
        }
        color, icon_name = colors.get(kind, colors["info"])
        self.setStyleSheet(
            f"QFrame#Toast {{ background:#131C2D; border:1px solid {color}; "
            "border-radius:12px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 16, 11)
        layout.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.icon_pixmap(icon_name, color, 17))
        ic.setFixedSize(18, 18)
        layout.addWidget(ic)
        tx = QLabel(text)
        tx.setObjectName("ToastText")
        tx.setWordWrap(True)
        metrics = QFontMetrics(tx.font())
        width = max(360, min(620, metrics.horizontalAdvance(text) + 92))
        self.setFixedWidth(width)
        tx.setMaximumWidth(width - 62)
        layout.addWidget(tx)
        self.adjustSize()

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._in = QPropertyAnimation(self._effect, b"opacity", self)
        self._in.setDuration(220)
        self._in.setStartValue(0.0)
        self._in.setEndValue(1.0)
        self._in.setEasingCurve(QEasingCurve.OutCubic)
        self._in.start()
        QTimer.singleShot(3400, self._fade_out)

    def _fade_out(self) -> None:
        self._out = QPropertyAnimation(self._effect, b"opacity", self)
        self._out.setDuration(300)
        self._out.setStartValue(self._effect.opacity())
        self._out.setEndValue(0.0)
        self._out.finished.connect(self.deleteLater)
        self._out.start()

    def show_at(self, parent: QWidget) -> None:
        self.adjustSize()
        sidebar = getattr(parent, "sidebar", None)
        offset = sidebar.width() if sidebar is not None else 0
        content_width = max(320, parent.width() - offset)
        x = offset + max(12, (content_width - self.width()) // 2)
        self.move(x, 78)
        self.show()
        self.raise_()

    @classmethod
    def show_message(cls, parent: QWidget, text: str,
                     kind: str = "info") -> "Toast":
        old = getattr(parent, "_active_toast", None)
        if old is not None:
            try:
                old.deleteLater()
            except RuntimeError:
                pass
        toast = cls(text, kind, parent)
        parent._active_toast = toast  # type: ignore[attr-defined]
        toast.show_at(parent)
        return toast


# ============================================================
# 进度
# ============================================================

class Stepper(QWidget):
    def __init__(self, steps: list[str] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.steps = steps or ["准备", "复制", "校验", "完成"]
        self.current = 0
        self.setFixedHeight(46)

    def set_current(self, index: int) -> None:
        index = max(0, min(len(self.steps) - 1, index))
        if index != self.current:
            self.current = index
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.steps)
        if n == 0:
            return
        margin = 24
        width = self.width() - margin * 2
        step = width / max(1, n - 1) if n > 1 else 0
        centers = [margin + i * step for i in range(n)]
        y = 13
        p.setPen(QPen(QColor(255, 255, 255, 28), 2))
        p.drawLine(int(centers[0]), y, int(centers[-1]), y)
        if self.current > 0:
            p.setPen(QPen(QColor(theme.BRAND_2), 2))
            p.drawLine(int(centers[0]), y, int(centers[self.current]), y)
        for i, (cx, text) in enumerate(zip(centers, self.steps)):
            if i < self.current:
                color = QColor(theme.BRAND_2)
                filled = True
            elif i == self.current:
                color = QColor(theme.BRAND)
                filled = True
            else:
                color = QColor(255, 255, 255, 34)
                filled = False
            p.setPen(QPen(color, 2))
            p.setBrush(color if filled else QColor(13, 20, 34))
            p.drawEllipse(QRectF(cx - 7, y - 7, 14, 14))
            if i < self.current:
                p.setPen(QPen(QColor(255, 255, 255), 1.8))
                p.drawLine(int(cx - 3), int(y), int(cx - 1), int(y + 3))
                p.drawLine(int(cx - 1), int(y + 3), int(cx + 4), int(y - 4))
            p.setPen(QColor(theme.TEXT if i <= self.current else theme.DIM))
            font = QFont("Microsoft YaHei UI", 9)
            font.setWeight(QFont.DemiBold if i == self.current else QFont.Normal)
            p.setFont(font)
            p.drawText(QRectF(cx - 50, y + 12, 100, 18),
                       Qt.AlignHCenter | Qt.AlignTop, text)
        p.end()


class ProgressOverlay(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 40, 40, 40)
        outer.setAlignment(Qt.AlignCenter)
        self.card = QFrame()
        self.card.setObjectName("ProgressCard")
        self.card.setFixedWidth(640)
        add_shadow(self.card, 48, 18, 150)
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(13)
        self.tile = IconTile("archive", "brand", 44, 21)
        head.addWidget(self.tile)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.title = label("正在处理…", "CardTitle")
        self.subtitle = label("请稍候", "Muted")
        text_box.addWidget(self.title)
        text_box.addWidget(self.subtitle)
        head.addLayout(text_box, 1)
        self.item_pill = Pill("1 / 1", "brand")
        head.addWidget(self.item_pill, alignment=Qt.AlignTop)
        layout.addLayout(head)

        self.stepper = Stepper()
        layout.addWidget(self.stepper)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(9)
        layout.addWidget(self.bar)

        percent_row = QHBoxLayout()
        self.percent = label("0%", "ValueSmall")
        self.percent.setStyleSheet(
            f"color:{theme.BRAND_2};font-family:'JetBrains Mono';"
            "font-size:20px;font-weight:700;"
        )
        percent_row.addWidget(self.percent)
        percent_row.addStretch()
        self.bytes_label = label("—", "MonoMuted")
        percent_row.addWidget(self.bytes_label)
        layout.addLayout(percent_row)

        stats = QHBoxLayout()
        stats.setSpacing(22)
        self.speed_label = label("速度 —", "MonoMuted")
        self.eta_label = label("剩余 —", "MonoMuted")
        self.phase_label = label("阶段 —", "MonoMuted")
        stats.addWidget(self.speed_label)
        stats.addWidget(self.eta_label)
        stats.addWidget(self.phase_label)
        stats.addStretch()
        layout.addLayout(stats)

        self.detail = ElidedLabel("", "Dim")
        layout.addWidget(self.detail)

        footer = QHBoxLayout()
        self.hint = label("操作过程中请不要移动或关闭源目录。", "Dim")
        footer.addWidget(self.hint)
        footer.addStretch()
        self.cancel_btn = QPushButton("取消操作")
        self.cancel_btn.setObjectName("Ghost")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel)
        footer.addWidget(self.cancel_btn)
        layout.addLayout(footer)

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("正在取消…")
        self.hint.setText("将在当前文件/校验步骤结束后停止，源数据不会被删除。")
        self.cancel_requested.emit()

    def show_operation(self, title: str, subtitle: str, item_count: int = 1,
                       steps: list[str] | None = None,
                       icon_name: str = "archive") -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)
        self.tile.set_icon(icon_name)
        self.item_pill.setText(f"1 / {max(1, item_count)}")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.percent.setText("0%")
        self.bytes_label.setText("—")
        self.speed_label.setText("速度 —")
        self.eta_label.setText("剩余 —")
        self.phase_label.setText("阶段 准备")
        self.detail.set_full_text("")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("取消操作")
        self.hint.setText("操作过程中请不要移动或关闭源目录。")
        self.stepper.steps = steps or ["准备", "复制", "校验", "完成"]
        self.stepper.set_current(0)
        self.resize_to_parent()
        self.show()
        self.raise_()

    def resize_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent:
            self.setGeometry(0, 0, parent.width(), parent.height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.resize_to_parent()

    def paintEvent(self, event: QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(4, 7, 13, 205))
        p.end()

    def update_progress(self, progress: Any) -> None:
        from ..core.models import human_bytes, human_duration
        phase = getattr(progress, "phase", "") or "处理中"
        pct = float(getattr(progress, "percent", 0) or 0)
        msg = getattr(progress, "message", "") or phase
        self.subtitle.setText(msg)
        self.phase_label.setText(f"阶段 {phase}")
        index = 0
        if pct >= 99 or phase in ("完成",):
            index = 3
        elif any(k in phase for k in ("校验", "设置权限", "删除", "释放", "回滚", "移除")):
            index = 2
        elif any(k in phase for k in ("复制", "移动", "扫描", "生成清单", "统计")):
            index = 1
        self.stepper.set_current(index)
        item_index = int(getattr(progress, "item_index", 0) or 0)
        item_count = int(getattr(progress, "item_count", 1) or 1)
        if item_index:
            self.item_pill.setText(f"{item_index} / {item_count}")
        total = int(getattr(progress, "bytes_total", 0) or 0)
        done = int(getattr(progress, "bytes_done", 0) or 0)
        if total > 0:
            self.bytes_label.setText(f"{human_bytes(done)} / {human_bytes(total)}")
        elif pct <= 0:
            self.bytes_label.setText("—")
        speed = float(getattr(progress, "speed_bps", 0) or 0)
        if speed > 0:
            self.speed_label.setText(f"速度 {human_bytes(speed)}/s")
        eta = float(getattr(progress, "eta_s", 0) or 0)
        if eta > 0:
            self.eta_label.setText(f"剩余 {human_duration(eta)}")
        self.detail.set_full_text(getattr(progress, "detail", "") or "")
        if pct <= 0 and total <= 0:
            self.bar.setRange(0, 0)
            self.percent.setText("…")
        else:
            self.bar.setRange(0, 100)
            value = max(0, min(100, int(round(pct))))
            self.bar.setValue(value)
            self.percent.setText(f"{value}%")

    def finish(self) -> None:
        self.hide()


# ============================================================
# 确认弹窗
# ============================================================

class ConfirmDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, message: str,
                 confirm_text: str = "确认", tone: str = "brand",
                 details: str = "", note: str = "", note_tone: str = "warn",
                 require_check: bool = False, icon_name: str = "alert",
                 cancel_text: str = "取消") -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self._drag: QPoint | None = None
        self._result_ok = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("DialogInner")
        card.setStyleSheet(
            f"QFrame#DialogInner {{ background:#0C1321; border:1px solid {theme.BORDER_HI}; "
            "border-radius:18px; }"
        )
        card.setFixedWidth(580)
        add_shadow(card, 46, 16, 160)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(IconTile(icon_name, tone, 42, 20), alignment=Qt.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        t = label(title, "CardTitle")
        t.setStyleSheet(f"color:{theme.TEXT};font-size:17px;font-weight:800;")
        text_box.addWidget(t)
        text_box.addWidget(label(message, "Muted", wrap=True))
        head.addLayout(text_box, 1)
        layout.addLayout(head)

        if details:
            box = QFrame()
            box.setObjectName("CardInset")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(12, 10, 12, 10)
            box_layout.setSpacing(4)
            detail_label = label(details, "Mono")
            detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            detail_label.setWordWrap(True)
            box_layout.addWidget(detail_label)
            layout.addWidget(box)

        if note:
            note_frame = QFrame()
            note_frame.setObjectName(
                "NoteDanger" if note_tone == "danger" else
                "NoteSuccess" if note_tone == "success" else "NoteWarn")
            note_layout = QHBoxLayout(note_frame)
            note_layout.setContentsMargins(12, 10, 12, 10)
            note_layout.setSpacing(9)
            color = theme.RED if note_tone == "danger" else (
                theme.GREEN if note_tone == "success" else theme.AMBER)
            ni = QLabel()
            ni.setPixmap(icons.icon_pixmap("alert", color, 16))
            ni.setFixedSize(17, 17)
            note_layout.addWidget(ni, alignment=Qt.AlignTop)
            note_label = label(note, "WarnText" if note_tone != "danger" else "ErrorText",
                              wrap=True)
            note_layout.addWidget(note_label, 1)
            layout.addWidget(note_frame)

        self.check: Check | None = None
        if require_check:
            self.check = Check("我已了解上述风险，确认继续")
            layout.addWidget(self.check)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel = QPushButton(cancel_text)
        cancel.setObjectName("Ghost")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.confirm = QPushButton(confirm_text)
        self.confirm.setObjectName("Danger" if tone in ("rose", "red", "danger") else "Primary")
        self.confirm.setCursor(Qt.PointingHandCursor)
        self.confirm.setMinimumWidth(118)
        self.confirm.clicked.connect(self._accept)
        if self.check is not None:
            self.confirm.setEnabled(False)
            self.check.toggled.connect(self.confirm.setEnabled)
        footer.addWidget(self.confirm)
        layout.addLayout(footer)

        self.adjustSize()
        self._center(parent)

    def _accept(self) -> None:
        self._result_ok = True
        self.accept()

    def _center(self, parent: QWidget | None) -> None:
        if parent is None:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.move(geo.center() - self.rect().center())
            return
        geo = parent.frameGeometry()
        self.move(geo.center() - self.rect().center())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and event.position().y() < 74:
            self._drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag = None

    @classmethod
    def ask(cls, parent: QWidget | None, title: str, message: str,
            confirm_text: str = "确认", **kwargs: Any) -> bool:
        dialog = cls(parent, title, message, confirm_text, **kwargs)
        return dialog.exec() == QDialog.Accepted

    @classmethod
    def show_info(cls, parent: QWidget | None, title: str, message: str,
                  details: str = "", icon_name: str = "info",
                  tone: str = "brand") -> None:
        dialog = cls(parent, title, message, "知道了", tone=tone,
                     details=details, icon_name=icon_name)
        dialog.confirm.clicked.disconnect()
        dialog.confirm.clicked.connect(dialog.accept)
        dialog.exec()


class InfoDialog(QDialog):
    """可滚动详情弹窗（历史记录详情）。"""

    def __init__(self, parent: QWidget | None, title: str, body: str) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        card = QFrame()
        card.setObjectName("DialogInner")
        card.setStyleSheet(
            f"QFrame#DialogInner {{ background:#0C1321; border:1px solid {theme.BORDER_HI}; "
            "border-radius:18px; }"
        )
        card.setFixedSize(720, 520)
        add_shadow(card, 46, 16, 160)
        outer.addWidget(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(IconTile("history", "purple", 38, 18))
        head.addWidget(label(title, "CardTitle"))
        head.addStretch()
        close = IconButton("x", "关闭")
        close.clicked.connect(self.accept)
        head.addWidget(close)
        layout.addLayout(head)
        from PySide6.QtWidgets import QTextEdit
        text = QTextEdit()
        text.setObjectName("LogBody")
        text.setReadOnly(True)
        text.setPlainText(body)
        layout.addWidget(text, 1)
        footer = QHBoxLayout()
        footer.addStretch()
        ok = QPushButton("关闭")
        ok.setObjectName("Primary")
        ok.clicked.connect(self.accept)
        footer.addWidget(ok)
        layout.addLayout(footer)
        self.resize(780, 600)
        if parent:
            geo = parent.frameGeometry()
            self.move(geo.center() - self.rect().center())


# ============================================================
# 表单 / 路径选择
# ============================================================

class FormRow(QWidget):
    def __init__(self, title: str, hint: str, control: QWidget,
                 stretch: bool = False) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(18)
        left = QWidget()
        left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        left_box = QVBoxLayout(left)
        left_box.setContentsMargins(0, 0, 0, 0)
        left_box.setSpacing(3)
        left_box.addWidget(label(title, "Body"))
        if hint:
            h = label(hint, "Muted", wrap=True)
            h.setMaximumWidth(460)
            left_box.addWidget(h)
        left_box.addStretch()
        layout.addWidget(left, 1)
        control.setSizePolicy(
            QSizePolicy.Expanding if stretch else QSizePolicy.Maximum,
            QSizePolicy.Preferred)
        if stretch:
            layout.addWidget(control, 1)
        else:
            layout.addWidget(control, 0, Qt.AlignRight | Qt.AlignVCenter)


class PathPicker(QWidget):
    changed = Signal(str)

    def __init__(self, path: str = "", placeholder: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.edit = QLineEdit(path)
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        layout.addWidget(self.edit, 1)
        browse = QPushButton("浏览…")
        browse.setObjectName("Ghost")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        layout.addWidget(browse)

    def _browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        start = self.edit.text().strip() or "D:\\"
        path = QFileDialog.getExistingDirectory(self, "选择目录", start)
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, text: str) -> None:
        self.edit.setText(text)


