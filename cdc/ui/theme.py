"""UI 设计令牌与全局样式表。

视觉语言：深色「极光玻璃」——墨蓝底、低对比边框、青紫渐变品牌色；
C / D / E 三块盘各有固定语义色，所有页面复用，形成空间认知。
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# ============================================================
# 颜色
# ============================================================

BG = "#060910"
BG_1 = "#090E19"
BG_2 = "#0D1422"
SIDEBAR = "rgba(8, 12, 21, 0.94)"
SURFACE = "rgba(18, 25, 41, 0.78)"
SURFACE_2 = "rgba(23, 32, 52, 0.88)"
SURFACE_3 = "rgba(30, 41, 65, 0.92)"
SURFACE_HOVER = "rgba(38, 52, 82, 0.98)"
INPUT = "rgba(10, 16, 28, 0.92)"

BORDER = "rgba(255, 255, 255, 0.072)"
BORDER_HI = "rgba(255, 255, 255, 0.145)"
BORDER_STRONG = "rgba(255, 255, 255, 0.22)"

TEXT = "#EEF2F9"
TEXT_2 = "#C3CCDB"
MUT = "#8E9BB0"
DIM = "#5C687C"

BRAND = "#6D5EF8"
BRAND_2 = "#38BDF8"
BRAND_3 = "#A78BFA"
PINK = "#F472B6"
CYAN = "#22D3EE"
TEAL = "#2DD4BF"
GREEN = "#34D399"
AMBER = "#FBBF24"
ORANGE = "#FB923C"
ROSE = "#FB7185"
RED = "#F87171"

C_COLOR = ROSE
D_COLOR = "#A78BFA"
E_COLOR = TEAL

# 字体栈：拉丁字符优先 JetBrains Mono（数字/路径不抖），中文回退微软雅黑
UI_STACK = ("'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', "
            "'PingFang SC', 'Noto Sans CJK SC', sans-serif")
MONO_STACK = ("'JetBrains Mono', 'Cascadia Code', 'Cascadia Mono', 'Consolas', "
              "'Microsoft YaHei UI', monospace")

# 运行时动画开关（设置页可关）
MOTION = True


def set_motion(enabled: bool) -> None:
    global MOTION
    MOTION = bool(enabled)


def qcolor(hex_color: str, alpha: int | None = None) -> QColor:
    c = QColor(hex_color)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


TONE_COLORS = {
    "brand": BRAND_2,
    "purple": BRAND_3,
    "cyan": CYAN,
    "teal": TEAL,
    "green": GREEN,
    "amber": AMBER,
    "orange": ORANGE,
    "rose": ROSE,
    "red": RED,
    "pink": PINK,
    "muted": MUT,
    "text": TEXT,
    "c": C_COLOR,
    "d": D_COLOR,
    "e": E_COLOR,
}
TONE_BG = {
    "brand": "rgba(56, 189, 248, 0.13)",
    "purple": "rgba(167, 139, 250, 0.13)",
    "cyan": "rgba(34, 211, 238, 0.12)",
    "teal": "rgba(45, 212, 191, 0.12)",
    "green": "rgba(52, 211, 153, 0.12)",
    "amber": "rgba(251, 191, 36, 0.12)",
    "orange": "rgba(251, 146, 60, 0.12)",
    "rose": "rgba(251, 113, 133, 0.12)",
    "red": "rgba(248, 113, 113, 0.12)",
    "pink": "rgba(244, 114, 182, 0.12)",
    "muted": "rgba(142, 155, 176, 0.10)",
    "text": "rgba(238, 242, 249, 0.08)",
}

TONE_BORDER = {
    "brand": "rgba(56, 189, 248, 0.32)",
    "purple": "rgba(167, 139, 250, 0.32)",
    "cyan": "rgba(34, 211, 238, 0.30)",
    "teal": "rgba(45, 212, 191, 0.30)",
    "green": "rgba(52, 211, 153, 0.30)",
    "amber": "rgba(251, 191, 36, 0.30)",
    "orange": "rgba(251, 146, 60, 0.30)",
    "rose": "rgba(251, 113, 133, 0.30)",
    "red": "rgba(248, 113, 113, 0.30)",
    "pink": "rgba(244, 114, 182, 0.30)",
    "muted": "rgba(142, 155, 176, 0.22)",
    "text": "rgba(238, 242, 249, 0.18)",
}


def tone_color(tone: str) -> str:
    return TONE_COLORS.get(tone, TONE_COLORS["brand"])


_chevron_cache: dict[str, str] = {}


def chevron_png(direction: str = "down", color: str = MUT) -> str:
    """生成 QSS 用的箭头 PNG（QSS 无法直接画三角形）。"""
    key = f"{direction}-{color}"
    if key in _chevron_cache:
        return _chevron_cache[key]
    try:
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QGuiApplication, QPainter, QPen, QPixmap
        from .. import paths
        if QGuiApplication.instance() is None:
            return ""
        pix = QPixmap(11, 11)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(color), 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        if direction == "up":
            p.drawLine(QPointF(2.5, 7.0), QPointF(5.5, 4.0))
            p.drawLine(QPointF(5.5, 4.0), QPointF(8.5, 7.0))
        elif direction == "plus":
            p.drawLine(QPointF(2.5, 5.5), QPointF(8.5, 5.5))
            p.drawLine(QPointF(5.5, 2.5), QPointF(5.5, 8.5))
        elif direction == "minus":
            p.drawLine(QPointF(2.5, 5.5), QPointF(8.5, 5.5))
        else:
            p.drawLine(QPointF(2.5, 4.0), QPointF(5.5, 7.0))
            p.drawLine(QPointF(5.5, 7.0), QPointF(8.5, 4.0))
        p.end()
        path = paths.cache_dir() / f"chevron-{direction}.png"
        pix.save(str(path), "PNG")
        url = path.as_posix()
        _chevron_cache[key] = url
        return url
    except Exception:
        return ""


# ============================================================
# QSS
# ============================================================

def build_qss(font_size: int = 13, motion: bool = True) -> str:
    """生成全局样式表。font_size 会等比缩放主要字号。"""
    f = max(10, int(font_size or 13))
    scale = f / 13.0
    arrow_down = chevron_png("down")
    arrow_up = chevron_png("up")

    def px(base: float) -> int:
        return max(9, int(round(base * scale)))

    return f"""
* {{
    font-family: {UI_STACK};
    font-size: {px(13)}px;
    color: {TEXT};
    outline: none;
    selection-background-color: {BRAND};
    selection-color: #ffffff;
}}

QMainWindow, QWidget#Root, QWidget#PageRoot {{
    background: transparent;
}}

QLabel {{ background: transparent; }}
QWidget#Transparent {{ background: transparent; }}

/* ================= 侧边栏 / 标题栏 ================= */
QFrame#Sidebar {{
    background: {SIDEBAR};
    border-right: 1px solid {BORDER};
}}
QFrame#TitleBar {{
    background: rgba(6, 9, 16, 0.55);
    border-bottom: 1px solid {BORDER};
}}
QLabel#AppName {{
    color: {TEXT};
    font-size: {px(16)}px;
    font-weight: 800;
}}
QLabel#AppTag {{
    color: {DIM};
    font-size: {px(10)}px;
    font-weight: 600;
}}
QLabel#SidebarGroup {{
    color: {DIM};
    font-size: {px(10)}px;
    font-weight: 700;
}}
QLabel#Breadcrumb {{
    color: {MUT};
    font-size: {px(12)}px;
}}
QLabel#BreadcrumbActive {{
    color: {TEXT_2};
    font-size: {px(12)}px;
    font-weight: 600;
}}

/* ================= 页面标题 ================= */
QLabel#PageTitle {{
    color: {TEXT};
    font-size: {px(26)}px;
    font-weight: 800;
}}
QLabel#PageSubtitle {{
    color: {MUT};
    font-size: {px(12)}px;
}}
QLabel#SectionTitle {{
    color: {TEXT};
    font-size: {px(15)}px;
    font-weight: 700;
}}
QLabel#SectionHint {{
    color: {MUT};
    font-size: {px(11)}px;
}}
QLabel#CardTitle {{
    color: {TEXT};
    font-size: {px(14)}px;
    font-weight: 700;
}}
QLabel#Label {{
    color: {MUT};
    font-size: {px(11)}px;
    font-weight: 600;
}}
QLabel#Value {{
    color: {TEXT};
    font-family: {MONO_STACK};
    font-size: {px(24)}px;
    font-weight: 700;
}}
QLabel#ValueSmall {{
    color: {TEXT};
    font-family: {MONO_STACK};
    font-size: {px(15)}px;
    font-weight: 700;
}}
QLabel#Mono {{
    color: {TEXT_2};
    font-family: {MONO_STACK};
    font-size: {px(11)}px;
}}
QLabel#MonoMuted {{
    color: {DIM};
    font-family: {MONO_STACK};
    font-size: {px(10)}px;
}}
QLabel#Body {{
    color: {TEXT_2};
    font-size: {px(12)}px;
}}
QLabel#Muted {{
    color: {MUT};
    font-size: {px(11)}px;
}}
QLabel#Dim {{
    color: {DIM};
    font-size: {px(10)}px;
}}
QLabel#ErrorText {{ color: {RED}; font-size: {px(11)}px; }}
QLabel#WarnText {{ color: {AMBER}; font-size: {px(11)}px; }}
QLabel#SuccessText {{ color: {GREEN}; font-size: {px(11)}px; }}

/* ================= 卡片 ================= */
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#CardSoft {{
    background: rgba(17, 24, 39, 0.58);
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#CardInset {{
    background: rgba(10, 15, 26, 0.62);
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(41, 33, 92, 0.92),
        stop:0.45 rgba(20, 30, 58, 0.94),
        stop:1 rgba(11, 25, 40, 0.96));
    border: 1px solid rgba(124, 108, 255, 0.28);
    border-radius: 20px;
}}
QFrame#Row {{
    background: rgba(17, 24, 39, 0.52);
    border: 1px solid {BORDER};
    border-radius: 13px;
}}
QFrame#Row:hover {{
    background: rgba(26, 36, 58, 0.74);
    border: 1px solid {BORDER_HI};
}}
QFrame#RowSelected {{
    background: rgba(35, 42, 72, 0.82);
    border: 1px solid rgba(124, 108, 255, 0.46);
    border-radius: 13px;
}}
QFrame#DriveCard {{
    background: rgba(17, 24, 39, 0.54);
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#DriveCard:hover {{
    background: rgba(25, 34, 55, 0.72);
    border: 1px solid {BORDER_HI};
}}
QFrame#DriveCard[selected="true"] {{
    background: rgba(38, 42, 82, 0.82);
    border: 1px solid rgba(124, 108, 255, 0.66);
}}
QFrame#SegContainer {{
    background: rgba(8, 13, 23, 0.7);
    border: 1px solid {BORDER};
    border-radius: 11px;
}}
QPushButton#SegBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 7px 14px;
    color: {MUT};
    font-weight: 600;
}}
QPushButton#SegBtn:hover {{ background: rgba(255, 255, 255, 0.05); color: {TEXT_2}; }}
QPushButton#SegBtn:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(109, 94, 248, 0.85), stop:1 rgba(56, 189, 248, 0.75));
    color: #ffffff;
}}
QFrame#Divider {{
    background: {BORDER};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QFrame#Note {{
    background: rgba(20, 28, 46, 0.66);
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#NoteWarn {{
    background: rgba(251, 191, 36, 0.075);
    border: 1px solid rgba(251, 191, 36, 0.22);
    border-radius: 12px;
}}
QFrame#NoteDanger {{
    background: rgba(248, 113, 113, 0.075);
    border: 1px solid rgba(248, 113, 113, 0.22);
    border-radius: 12px;
}}
QFrame#NoteSuccess {{
    background: rgba(52, 211, 153, 0.07);
    border: 1px solid rgba(52, 211, 153, 0.22);
    border-radius: 12px;
}}

/* ================= 按钮 ================= */
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    color: {TEXT_2};
    font-size: {px(12)}px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {SURFACE_3};
    border-color: {BORDER_HI};
    color: {TEXT};
}}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{
    background: rgba(18, 25, 41, 0.35);
    border-color: rgba(255, 255, 255, 0.04);
    color: {DIM};
}}

QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {BRAND}, stop:1 {BRAND_2});
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: #ffffff;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #7C6DFF, stop:1 #5CCBFA);
}}
QPushButton#Primary:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #5A4CE0, stop:1 #2F9BC7);
}}
QPushButton#Primary:disabled {{
    background: rgba(45, 55, 80, 0.7);
    border-color: transparent;
    color: {DIM};
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {BORDER_HI};
    color: {TEXT_2};
}}
QPushButton#Ghost:hover {{
    background: rgba(255, 255, 255, 0.045);
    border-color: {BORDER_STRONG};
    color: {TEXT};
}}
QPushButton#Danger {{
    background: rgba(248, 113, 113, 0.10);
    border: 1px solid rgba(248, 113, 113, 0.30);
    color: {RED};
}}
QPushButton#Danger:hover {{
    background: rgba(248, 113, 113, 0.18);
    border-color: rgba(248, 113, 113, 0.55);
}}
QPushButton#Success {{
    background: rgba(52, 211, 153, 0.12);
    border: 1px solid rgba(52, 211, 153, 0.30);
    color: {GREEN};
}}
QPushButton#Success:hover {{ background: rgba(52, 211, 153, 0.20); }}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {BRAND_2};
    padding: 4px 6px;
    font-weight: 600;
}}
QPushButton#Link:hover {{ color: #7DD3FC; text-decoration: underline; }}
QPushButton#IconBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 0;
}}
QPushButton#IconBtn:hover {{
    background: rgba(255, 255, 255, 0.06);
    border-color: {BORDER};
}}
QPushButton#RowAction {{
    background: rgba(109, 94, 248, 0.12);
    border: 1px solid rgba(109, 94, 248, 0.30);
    color: #C7C2FF;
    padding: 6px 12px;
    border-radius: 9px;
    font-weight: 700;
}}
QPushButton#RowAction:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BRAND}, stop:1 #4F8CF7);
    border-color: transparent;
    color: #fff;
}}
QPushButton#RowWarn {{
    background: rgba(251, 191, 36, 0.10);
    border: 1px solid rgba(251, 191, 36, 0.28);
    color: {AMBER};
    padding: 6px 12px;
    border-radius: 9px;
    font-weight: 700;
}}
QPushButton#RowWarn:hover {{ background: rgba(251, 191, 36, 0.2); }}
QPushButton#RowDanger {{
    background: rgba(248, 113, 113, 0.08);
    border: 1px solid rgba(248, 113, 113, 0.24);
    color: {RED};
    padding: 6px 12px;
    border-radius: 9px;
    font-weight: 700;
}}
QPushButton#RowDanger:hover {{ background: rgba(248, 113, 113, 0.18); }}
QPushButton#WindowBtn {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    color: {MUT};
    font-size: {px(13)}px;
}}
QPushButton#WindowBtn:hover {{ background: rgba(255, 255, 255, 0.07); color: {TEXT}; }}
QPushButton#CloseBtn {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    color: {MUT};
    font-size: {px(13)}px;
}}
QPushButton#CloseBtn:hover {{ background: #C42B1C; color: #ffffff; }}

/* ================= 输入 ================= */
QLineEdit, QSpinBox, QComboBox, QFontComboBox {{
    background: {INPUT};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 7px 11px;
    color: {TEXT};
    font-size: {px(12)}px;
    min-height: 18px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QFontComboBox:focus {{
    border: 1px solid rgba(109, 94, 248, 0.72);
    background: rgba(13, 20, 35, 0.98);
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {DIM}; }}
QLineEdit[error="true"] {{ border-color: rgba(248, 113, 113, 0.7); }}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: 18px; border: none; background: transparent;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: rgba(109,94,248,0.16); }}
QSpinBox::up-arrow {{
    image: url("{arrow_up}"); width: 9px; height: 9px;
    subcontrol-position: center;
}}
QSpinBox::down-arrow {{
    image: url("{arrow_down}"); width: 9px; height: 9px;
    subcontrol-position: center;
}}
QComboBox::drop-down, QFontComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: top right;
    width: 26px; border: none; background: transparent;
}}
QComboBox::down-arrow, QFontComboBox::down-arrow {{
    image: url("{arrow_down}"); width: 11px; height: 11px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
    margin-right: 9px;
}}
QComboBox QAbstractItemView, QFontComboBox QAbstractItemView {{
    background: {BG_2};
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    border-radius: 8px;
    selection-background-color: {BRAND};
    selection-color: #fff;
    outline: 0;
    padding: 4px;
}}
QSlider {{ min-height: 24px; }}
QSlider::groove:horizontal {{
    height: 5px; background: rgba(255,255,255,0.09); border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BRAND}, stop:1 {BRAND_2});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #ffffff; width: 15px; height: 15px;
    margin: -5px 0; border-radius: 7px;
    border: 2px solid {BRAND_2};
}}
QSlider::handle:horizontal:hover {{ border-color: #fff; }}
QCheckBox {{ color: {TEXT_2}; font-size: {px(12)}px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    background: {INPUT}; border: 1px solid {BORDER_HI};
}}
QCheckBox::indicator:checked {{ background: {BRAND}; border-color: {BRAND}; }}

/* ================= 滚动 ================= */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 9px; margin: 3px 2px;
}}
QScrollBar::handle:vertical {{
    background: rgba(255, 255, 255, 0.13); border-radius: 4px; min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.26); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px 3px; }}
QScrollBar::handle:horizontal {{
    background: rgba(255, 255, 255, 0.13); border-radius: 4px; min-width: 34px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ================= 进度 ================= */
QProgressBar {{
    background: rgba(255, 255, 255, 0.075);
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BRAND}, stop:0.55 {BRAND_3}, stop:1 {BRAND_2});
    border-radius: 4px;
}}

/* ================= 文本 / 列表 ================= */
QTextEdit#LogBody, QPlainTextEdit {{
    background: rgba(7, 11, 20, 0.86);
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT_2};
    font-family: {MONO_STACK};
    font-size: {px(11)}px;
    padding: 8px 10px;
    selection-background-color: {BRAND};
}}
QListWidget {{
    background: transparent; border: none; outline: 0;
}}
QToolTip {{
    background: #141C2C;
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    border-radius: 8px;
    padding: 6px 9px;
    font-size: {px(11)}px;
}}

/* ================= 对话框 ================= */
QDialog#Dialog {{
    background: #0B111D;
    border: 1px solid {BORDER_HI};
    border-radius: 18px;
}}
QFrame#DialogCard {{ background: transparent; border: none; }}
QFrame#ProgressCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #111A2B, stop:1 #0A101C);
    border: 1px solid {BORDER_HI};
    border-radius: 20px;
}}
QFrame#Toast {{
    background: #131C2D;
    border: 1px solid {BORDER_HI};
    border-radius: 12px;
}}
QLabel#ToastText {{ color: {TEXT}; font-size: {px(12)}px; font-weight: 600; }}

/* ================= 日历 / 杂项 ================= */
QMenu {{
    background: {BG_2};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; color: {TEXT_2}; }}
QMenu::item:selected {{ background: {SURFACE_3}; color: {TEXT}; }}
"""
