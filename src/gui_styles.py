"""GUI 样式与动画辅助。

设计语言：暗色玻璃拟态 + 渐变品牌色，强调丝滑过渡。
- QSS 样式表集中管理，类似 CSS 的设计令牌思路。
- 动画辅助函数封装 QPropertyAnimation 的常用模式。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QTimer,
    QVariantAnimation,
    QPoint,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


# ============================================================
# 设计令牌 (Design Tokens)
# ============================================================

# 背景层
BG_0 = "#070b14"
BG_1 = "#0b1120"
BG_2 = "#0f172a"

# 玻璃表面（半透明）
SURFACE = "rgba(22, 30, 48, 0.72)"
SURFACE_2 = "rgba(28, 38, 60, 0.80)"
SURFACE_3 = "rgba(36, 48, 74, 0.85)"
SURFACE_HOVER = "rgba(46, 60, 92, 0.90)"

# 边框
BORDER = "rgba(125, 160, 255, 0.12)"
BORDER_HI = "rgba(125, 160, 255, 0.28)"

# 文字
TEXT = "#e6edf3"
TEXT_MUT = "#8b97a7"
TEXT_DIM = "#5d6776"

# 品牌与语义色
BRAND = "#6366f1"
BRAND_2 = "#8b5cf6"
BRAND_3 = "#ec4899"
GREEN = "#3fb950"
YELLOW = "#d29922"
RED = "#f85149"
BLUE = "#58a6ff"
TEAL = "#2dd4bf"
PURPLE = "#bc8cff"


# ============================================================
# QSS 样式表
# ============================================================

GLOBAL_QSS = f"""
* {{
    font-family: 'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Cascadia Mono',
                 'Microsoft YaHei UI', 'Microsoft YaHei', monospace;
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}

/* ===== 主窗口 ===== */
QMainWindow, QWidget#Root {{
    background: qlineargradient(x1:0, y1:0, x2:0.6, y2:1,
        stop:0 {BG_0}, stop:0.5 {BG_1}, stop:1 {BG_2});
}}

/* ===== 自定义标题栏 ===== */
QWidget#TitleBar {{
    background: transparent;
    border-bottom: 1px solid {BORDER};
}}

QLabel#TitleAppName {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#TitleVersion {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    font-family: 'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Cascadia Mono', monospace;
}}

QPushButton#BtnClose, QPushButton#BtnMin, QPushButton#BtnMax {{
    border: none;
    border-radius: 6px;
    background: transparent;
    color: {TEXT_MUT};
    font-size: 12px;
    padding: 4px;
}}
QPushButton#BtnClose:hover {{ background: rgba(248, 81, 73, 0.85); color: white; }}
QPushButton#BtnMin:hover, QPushButton#BtnMax:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; }}

/* ===== 玻璃卡片 ===== */
QFrame#Card, QFrame#StatCard, QFrame#DirCard {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#StatCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {SURFACE_2}, stop:1 {SURFACE});
}}

QLabel#SectionTitle {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 700;
}}
QLabel#SectionHint {{
    color: {TEXT_MUT};
    font-size: 12px;
}}

/* ===== 统计卡片数值 ===== */
QLabel#StatValue {{
    color: {TEXT};
    font-size: 22px;
    font-weight: 800;
    font-family: 'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Cascadia Mono', monospace;
}}
QLabel#StatLabel {{
    color: {TEXT_MUT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QLabel#StatValueBrand {{ color: {BRAND_2}; }}
QLabel#StatValueGreen {{ color: {GREEN}; }}
QLabel#StatValueYellow {{ color: {YELLOW}; }}
QLabel#StatValueBlue {{ color: {BLUE}; }}
QLabel#StatValueTeal {{ color: {TEAL}; }}

/* ===== 目录卡片 ===== */
QLabel#DirIcon {{
    font-size: 22px;
}}
QLabel#DirName {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#DirPath {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-family: 'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Cascadia Mono', monospace;
}}
QLabel#DirSize {{
    color: {BRAND_2};
    font-size: 13px;
    font-weight: 700;
    font-family: 'JetBrains Mono', 'JetBrainsMono Nerd Font', 'Cascadia Mono', monospace;
}}
QLabel#DirZone {{
    color: {TEXT_MUT};
    font-size: 10px;
    font-weight: 600;
    background: {SURFACE_3};
    padding: 2px 8px;
    border-radius: 8px;
}}
QLabel#JunctionTag {{
    color: {TEAL};
    font-size: 10px;
    font-weight: 700;
    background: rgba(45, 212, 191, 0.14);
    border: 1px solid rgba(45, 212, 191, 0.35);
    padding: 2px 8px;
    border-radius: 8px;
}}
QLabel#AdminTag {{
    color: {YELLOW};
    font-size: 10px;
    font-weight: 700;
    background: rgba(210, 153, 34, 0.14);
    border: 1px solid rgba(210, 153, 34, 0.35);
    padding: 2px 8px;
    border-radius: 8px;
}}

/* ===== 按钮 ===== */
QPushButton {{
    border: none;
    border-radius: 9px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
    color: {TEXT};
    background: {SURFACE_3};
}}
QPushButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton:pressed {{ background: {SURFACE_2}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: {SURFACE}; }}

QPushButton#PrimaryBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {BRAND}, stop:1 {BRAND_2});
    color: white;
    border: none;
}}
QPushButton#PrimaryBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #7c7df5, stop:1 #a78bfa);
}}
QPushButton#PrimaryBtn:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #5558e0, stop:1 #7c3aed);
}}
QPushButton#PrimaryBtn:disabled {{
    background: {SURFACE_3};
    color: {TEXT_DIM};
}}

QPushButton#GhostBtn {{
    background: transparent;
    border: 1px solid {BORDER_HI};
    color: {TEXT};
}}
QPushButton#GhostBtn:hover {{
    background: {SURFACE_3};
    border-color: {BRAND};
}}

QPushButton#DangerBtn {{
    background: transparent;
    border: 1px solid rgba(248, 81, 73, 0.4);
    color: {RED};
}}
QPushButton#DangerBtn:hover {{
    background: rgba(248, 81, 73, 0.15);
    border-color: {RED};
}}

QPushButton#ActionBtn {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(99,102,241,0.25), stop:1 rgba(139,92,246,0.25));
    border: 1px solid rgba(99,102,241,0.45);
    color: #c7d2fe;
    font-weight: 700;
    padding: 6px 14px;
}}
QPushButton#ActionBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BRAND}, stop:1 {BRAND_2});
    color: white;
    border-color: {BRAND_2};
}}

QPushButton#UndoBtn {{
    background: rgba(45, 212, 191, 0.14);
    border: 1px solid rgba(45, 212, 191, 0.4);
    color: {TEAL};
    font-weight: 700;
    padding: 6px 14px;
}}
QPushButton#UndoBtn:hover {{
    background: {TEAL};
    color: {BG_0};
}}

QPushButton#AdminBtn {{
    background: rgba(210, 153, 34, 0.14);
    border: 1px solid rgba(210, 153, 34, 0.4);
    color: {YELLOW};
    font-weight: 700;
    padding: 6px 14px;
}}
QPushButton#AdminBtn:hover {{
    background: {YELLOW};
    color: {BG_0};
}}

/* ===== 滚动区域 ===== */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_HI};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BRAND};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_HI};
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {BRAND};
}}

/* ===== 进度条 ===== */
QProgressBar {{
    background: {SURFACE_3};
    border: none;
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BRAND}, stop:0.5 {BRAND_2}, stop:1 {BRAND_3});
    border-radius: 6px;
}}

/* ===== Toast ===== */
QFrame#Toast {{
    background: {SURFACE_HOVER};
    border: 1px solid {BORDER_HI};
    border-radius: 12px;
}}
QLabel#ToastText {{
    color: {TEXT};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#ToastIcon {{
    font-size: 16px;
}}

/* ===== 空状态 ===== */
QLabel#EmptyIcon {{
    font-size: 48px;
    color: {TEXT_DIM};
}}
QLabel#EmptyText {{
    color: {TEXT_MUT};
    font-size: 13px;
}}

/* ===== 加载指示 ===== */
QLabel#LoadingText {{
    color: {TEXT_MUT};
    font-size: 12px;
}}

/* ===== 提示条 ===== */
QFrame#Note {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#NoteWarnText {{ color: {YELLOW}; }}
QLabel#NoteInfoText {{ color: {BLUE}; }}
QLabel#NoteDangerText {{ color: {RED}; }}
"""


# ============================================================
# 动画辅助函数
# ============================================================

def fade_in(widget: QWidget, duration: int = 300, delay: int = 0) -> QPropertyAnimation:
    """淡入动画。返回 animation 对象（需保持引用否则被回收）。"""
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    eff.setOpacity(0.0)

    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    if delay > 0:
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start()
    # 保存引用防 GC
    if not hasattr(widget, "_fade_anims"):
        widget._fade_anims = []
    widget._fade_anims.append(anim)
    return anim


def slide_up(widget: QWidget, duration: int = 400, delay: int = 0,
             distance: int = 24) -> None:
    """向上滑入 + 淡入组合动画。"""
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    eff.setOpacity(0.0)

    orig_pos = widget.pos()
    start_pos = QPoint(orig_pos.x(), orig_pos.y() + distance)

    def _run() -> None:
        widget.move(start_pos)
        # 位置动画
        pos_anim = QPropertyAnimation(widget, b"pos", widget)
        pos_anim.setDuration(duration)
        pos_anim.setStartValue(start_pos)
        pos_anim.setEndValue(orig_pos)
        pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # 透明度动画
        op_anim = QPropertyAnimation(eff, b"opacity", widget)
        op_anim.setDuration(duration)
        op_anim.setStartValue(0.0)
        op_anim.setEndValue(1.0)
        op_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        pos_anim.start()
        op_anim.start()
        # 保存引用防 GC
        widget._slide_anims = (pos_anim, op_anim)

    if delay > 0:
        QTimer.singleShot(delay, _run)
    else:
        _run()


def animate_value(callback, start: float, end: float,
                  duration: int = 800, delay: int = 0) -> QVariantAnimation:
    """数值滚动动画。callback 接收当前 float 值。

    用 QVariantAnimation，无需 QObject property 绑定，更简单可靠。
    返回的 animation 需调用方保持引用（StatCard 已存到实例属性）。
    """
    anim = QVariantAnimation()
    anim.setDuration(duration)
    anim.setStartValue(float(start))
    anim.setEndValue(float(end))
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(callback)

    if delay > 0:
        QTimer.singleShot(delay, anim.start)
    else:
        anim.start()
    return anim


def pulse_widget(widget: QWidget, duration: int = 1000) -> QPropertyAnimation:
    """呼吸光晕动画（用于品牌 Logo / 重要提示）。"""
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)

    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setKeyValueAt(0.5, 0.6)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.InOutSine)
    anim.setLoopCount(-1)
    anim.start()
    return anim


def button_press_feedback(widget: QWidget) -> None:
    """按钮点击缩放反馈（快速 scale down → up）。"""
    orig = widget.size()
    anim = QPropertyAnimation(widget, b"size", widget)
    anim.setDuration(150)
    anim.setStartValue(orig)
    anim.setKeyValueAt(0.5, orig.scaled(int(orig.width() * 0.95), int(orig.height() * 0.95)))
    anim.setEndValue(orig)
    anim.setEasingCurve(QEasingCurve.Type.OutBack)
    anim.start()
    widget._press_anim = anim  # 防回收
