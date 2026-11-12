"""UI 设计令牌与全局样式表。

视觉语言：暖纸张 + 墨色 + 赭红。
- 内容区用暖白纸张，侧边栏用深墨色，形成清晰层级；
- 正文以高对比深墨色为主，辅助文字不低于 11px，避免旧版细小灰字；
- 图标统一为「墨线 + 单点实色」的双色几何风格。
"""

from __future__ import annotations

from PySide6.QtGui import QColor

# ============================================================
# 颜色
# ============================================================

BG = "#F2EEE5"
BG_1 = "#ECE6DA"
BG_2 = "#E5DDCE"

SIDEBAR = "#25231E"
SIDEBAR_2 = "#2E2B24"
SIDEBAR_LINE = "#3A362D"

SURFACE = "#FBF8F2"
SURFACE_2 = "#F6F1E7"
SURFACE_3 = "#EFE8DB"
SURFACE_HOVER = "#E8DFCF"
INPUT = "#FFFDF9"

BORDER = "#DED6C6"
BORDER_HI = "#CEC3AF"
BORDER_STRONG = "#B4A68D"

TEXT = "#26231D"
TEXT_2 = "#4A4439"
MUT = "#665F52"
DIM = "#7C7363"

BRAND = "#B44A2D"
BRAND_2 = "#D97757"
BRAND_3 = "#8C6A43"
PINK = "#9A4A5C"
CYAN = "#2E6F6A"
TEAL = "#39706B"
GREEN = "#5B7246"
AMBER = "#A66C1D"
ORANGE = "#A9552A"
ROSE = "#A94B3F"
RED = "#9E3B34"

C_COLOR = BRAND
D_COLOR = "#6D7551"
E_COLOR = TEAL

# 字体：正文优先 Segoe UI Variable Text + 微软雅黑；数字/路径用等宽，但不用它承载大段中文
UI_STACK = ("'Segoe UI Variable Text', 'Segoe UI', 'Microsoft YaHei UI', "
            "'Microsoft YaHei', 'PingFang SC', 'Noto Sans CJK SC', sans-serif")
MONO_STACK = ("'Cascadia Mono', 'JetBrains Mono', 'Consolas', "
              "'Microsoft YaHei UI', monospace")

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
    "brand": "#A8432A",
    "purple": "#7C5A36",
    "cyan": "#2E6F6A",
    "teal": "#39706B",
    "green": "#5B7246",
    "amber": "#96651C",
    "orange": "#A9552A",
    "rose": "#A94B3F",
    "red": "#9E3B34",
    "pink": "#9A4A5C",
    "muted": "#6F6759",
    "text": TEXT,
    "c": C_COLOR,
    "d": D_COLOR,
    "e": E_COLOR,
}

TONE_BG = {
    "brand": "rgba(180, 74, 45, 0.10)",
    "purple": "rgba(124, 90, 54, 0.10)",
    "cyan": "rgba(46, 111, 106, 0.10)",
    "teal": "rgba(57, 112, 107, 0.10)",
    "green": "rgba(91, 114, 70, 0.10)",
    "amber": "rgba(166, 108, 29, 0.10)",
    "orange": "rgba(169, 85, 42, 0.10)",
    "rose": "rgba(169, 75, 63, 0.10)",
    "red": "rgba(158, 59, 52, 0.10)",
    "pink": "rgba(154, 74, 92, 0.10)",
    "muted": "rgba(111, 103, 89, 0.08)",
    "text": "rgba(38, 35, 29, 0.06)",
}

TONE_BORDER = {
    "brand": "rgba(180, 74, 45, 0.28)",
    "purple": "rgba(124, 90, 54, 0.26)",
    "cyan": "rgba(46, 111, 106, 0.26)",
    "teal": "rgba(57, 112, 107, 0.26)",
    "green": "rgba(91, 114, 70, 0.26)",
    "amber": "rgba(166, 108, 29, 0.26)",
    "orange": "rgba(169, 85, 42, 0.26)",
    "rose": "rgba(169, 75, 63, 0.26)",
    "red": "rgba(158, 59, 52, 0.26)",
    "pink": "rgba(154, 74, 92, 0.26)",
    "muted": "rgba(111, 103, 89, 0.20)",
    "text": "rgba(38, 35, 29, 0.16)",
}


def tone_color(tone: str) -> str:
    return TONE_COLORS.get(tone, TONE_COLORS["brand"])


_chevron_cache: dict[str, str] = {}


def chevron_png(direction: str = "down", color: str = MUT) -> str:
    """生成 QSS 用的箭头 PNG。"""
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

def build_qss(font_size: int = 14, motion: bool = True) -> str:
    """生成全局样式表。"""
    f = max(14, int(font_size or 14))
    scale = f / 14.0
    arrow_down = chevron_png("down")
    arrow_up = chevron_png("up")

    def px(base: float) -> int:
        return max(12, int(round(base * scale)))

    return f"""
* {{
    font-family: {UI_STACK};
    font-size: {px(14)}px;
    color: {TEXT};
    outline: none;
    selection-background-color: {BRAND};
    selection-color: #FFF8F0;
}}

QMainWindow, QWidget#Root, QWidget#PageRoot {{ background: transparent; }}
QLabel {{ background: transparent; }}
QWidget#Transparent {{ background: transparent; }}

/* ================= 侧边栏 / 标题栏 ================= */
QFrame#Sidebar {{
    background: {SIDEBAR};
    border-right: 1px solid {SIDEBAR_LINE};
}}
QFrame#TitleBar {{
    background: rgba(248, 244, 236, 0.96);
    border-bottom: 1px solid {BORDER};
}}
QLabel#AppName {{
    color: #F7F0E4;
    font-size: {px(16)}px;
    font-weight: 700;
}}
QLabel#AppTag {{
    color: #A69C8C;
    font-size: {px(12)}px;
    font-weight: 500;
}}
QLabel#SidebarGroup {{
    color: #8F8575;
    font-size: {px(12)}px;
    font-weight: 600;
}}
QLabel#Breadcrumb {{
    color: {MUT};
    font-size: {px(13)}px;
}}
QLabel#BreadcrumbActive {{
    color: {TEXT};
    font-size: {px(13)}px;
    font-weight: 600;
}}

/* ================= 页面标题 ================= */
QLabel#PageTitle {{
    color: {TEXT};
    font-size: {px(30)}px;
    font-weight: 700;
}}
QLabel#PageSubtitle {{
    color: {MUT};
    font-size: {px(13)}px;
}}
QLabel#SectionTitle {{
    color: {TEXT};
    font-size: {px(17)}px;
    font-weight: 700;
}}
QLabel#SectionHint {{
    color: {MUT};
    font-size: {px(12)}px;
}}
QLabel#CardTitle {{
    color: {TEXT};
    font-size: {px(15)}px;
    font-weight: 600;
}}
QLabel#Label {{
    color: {MUT};
    font-size: {px(12)}px;
    font-weight: 600;
}}
QLabel#Value {{
    color: {TEXT};
    font-family: {MONO_STACK};
    font-size: {px(27)}px;
    font-weight: 700;
}}
QLabel#ValueSmall {{
    color: {TEXT};
    font-family: {MONO_STACK};
    font-size: {px(17)}px;
    font-weight: 700;
}}
QLabel#Mono {{
    color: {TEXT_2};
    font-family: {MONO_STACK};
    font-size: {px(12)}px;
}}
QLabel#MonoMuted {{
    color: {MUT};
    font-family: {MONO_STACK};
    font-size: {px(12)}px;
}}
QLabel#Body {{
    color: {TEXT_2};
    font-size: {px(14)}px;
}}
QLabel#Muted {{
    color: {MUT};
    font-size: {px(12)}px;
}}
QLabel#Dim {{
    color: {DIM};
    font-size: {px(12)}px;
}}
QLabel#ErrorText {{ color: {RED}; font-size: {px(12)}px; }}
QLabel#WarnText {{ color: {AMBER}; font-size: {px(12)}px; }}
QLabel#SuccessText {{ color: {GREEN}; font-size: {px(12)}px; }}

/* ================= 卡片 ================= */
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
QFrame#CardSoft {{
    background: {SURFACE_2};
    border: 1px solid #E3DAC9;
    border-radius: 14px;
}}
QFrame#CardInset {{
    background: {SURFACE_3};
    border: 1px solid #E0D7C5;
    border-radius: 12px;
}}
QFrame#Hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #FFF9EF,
        stop:0.55 #F9EFE2,
        stop:1 #F2E2D2);
    border: 1px solid #E4CDB8;
    border-radius: 20px;
}}
QFrame#Row {{
    background: {SURFACE};
    border: 1px solid #E1D8C6;
    border-radius: 12px;
}}
QFrame#Row:hover {{
    background: #F7F1E5;
    border: 1px solid #D2C6B1;
}}
QFrame#RowSelected {{
    background: #FAEAE3;
    border: 1px solid #D9A58F;
    border-radius: 12px;
}}
QFrame#DriveCard {{
    background: #FAF6EE;
    border: 1px solid #E1D8C6;
    border-radius: 14px;
}}
QFrame#DriveCard:hover {{
    background: #F5EEDF;
    border: 1px solid #D2C6B1;
}}
QFrame#DriveCard[selected="true"] {{
    background: #F9E9E1;
    border: 1px solid #C87C60;
}}
QFrame#SegContainer {{
    background: #F2ECDF;
    border: 1px solid #DED4C1;
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
QPushButton#SegBtn:hover {{ background: rgba(180, 74, 45, 0.07); color: {TEXT}; }}
QPushButton#SegBtn:checked {{
    background: #B44A2D;
    color: #FFF8F0;
}}
QFrame#Divider {{
    background: {BORDER};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QFrame#Note {{
    background: #F5EFE3;
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#NoteWarn {{
    background: #FBF1D9;
    border: 1px solid #E8CE96;
    border-radius: 12px;
}}
QFrame#NoteDanger {{
    background: #FAE8E4;
    border: 1px solid #E0B4A9;
    border-radius: 12px;
}}
QFrame#NoteSuccess {{
    background: #EFF1E6;
    border: 1px solid #CBD3B5;
    border-radius: 12px;
}}

/* ================= 按钮 ================= */
QPushButton {{
    background: #F3ECDF;
    border: 1px solid #DCD2C0;
    border-radius: 10px;
    padding: 9px 16px;
    color: {TEXT_2};
    font-size: {px(13)}px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #EBE2D2;
    border-color: {BORDER_STRONG};
    color: {TEXT};
}}
QPushButton:pressed {{ background: #E4D9C7; }}
QPushButton:disabled {{
    background: #F2EDE4;
    border-color: #E5DDD0;
    color: #A79D8C;
}}

QPushButton#Primary {{
    background: #B44A2D;
    border: 1px solid #9C3E27;
    color: #FFF8F0;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #A8432A; border-color: #893421; }}
QPushButton#Primary:pressed {{ background: #943A25; }}
QPushButton#Primary:disabled {{
    background: #DFD5C4;
    border-color: #D5CAB8;
    color: #928876;
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid #CFC5B2;
    color: {TEXT_2};
}}
QPushButton#Ghost:hover {{
    background: #F3EDE1;
    border-color: {BORDER_STRONG};
    color: {TEXT};
}}
QPushButton#Danger {{
    background: #FAE8E4;
    border: 1px solid #D9A79B;
    color: #9A3B31;
}}
QPushButton#Danger:hover {{ background: #F5D8D2; border-color: #C98F81; }}
QPushButton#Success {{
    background: #EFF1E6;
    border: 1px solid #C5CEAF;
    color: #4E653D;
}}
QPushButton#Success:hover {{ background: #E6EAD8; }}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {BRAND};
    padding: 4px 6px;
    font-weight: 600;
}}
QPushButton#Link:hover {{ color: #8E3420; text-decoration: underline; }}
QPushButton#IconBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 0;
}}
QPushButton#IconBtn:hover {{
    background: #F1EADF;
    border-color: {BORDER};
}}
QPushButton#RowAction {{
    background: #F7E7E0;
    border: 1px solid #E0B7A7;
    color: #9F3F27;
    padding: 7px 13px;
    border-radius: 9px;
    font-weight: 600;
}}
QPushButton#RowAction:hover {{
    background: #B44A2D;
    border-color: #9C3E27;
    color: #FFF8F0;
}}
QPushButton#RowWarn {{
    background: #FAF1DA;
    border: 1px solid #E3C98F;
    color: #8A5C14;
    padding: 7px 13px;
    border-radius: 9px;
    font-weight: 600;
}}
QPushButton#RowWarn:hover {{ background: #F4E5C2; }}
QPushButton#RowDanger {{
    background: #FAE8E4;
    border: 1px solid #E0B4A9;
    color: #9A3B31;
    padding: 7px 13px;
    border-radius: 9px;
    font-weight: 600;
}}
QPushButton#RowDanger:hover {{ background: #F5D8D2; }}
QPushButton#WindowBtn {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    color: #6D6559;
    font-size: {px(14)}px;
}}
QPushButton#WindowBtn:hover {{ background: #EDE5D8; color: {TEXT}; }}
QPushButton#CloseBtn {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    color: #6D6559;
    font-size: {px(14)}px;
}}
QPushButton#CloseBtn:hover {{ background: #A33A34; color: #FFF8F0; }}

/* ================= 输入 ================= */
QLineEdit, QSpinBox, QComboBox, QFontComboBox {{
    background: {INPUT};
    border: 1px solid #D8CFBE;
    border-radius: 10px;
    padding: 8px 11px;
    color: {TEXT};
    font-size: {px(13)}px;
    min-height: 20px;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QFontComboBox:focus {{
    border: 1px solid #B44A2D;
    background: #FFFFFF;
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: #A79D8C; }}
QLineEdit[error="true"] {{ border-color: #A33A34; }}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border; width: 20px; border: none; background: transparent;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: #F3EADB; }}
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
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid #D8CFBE;
    border-radius: 8px;
    selection-background-color: #B44A2D;
    selection-color: #FFF8F0;
    outline: 0;
    padding: 4px;
}}
QSlider {{ min-height: 24px; }}
QSlider::groove:horizontal {{
    height: 5px; background: #E6DECD; border-radius: 3px;
}}
QSlider::sub-page:horizontal {{
    background: #B44A2D;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #FFFDF9; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px;
    border: 2px solid #B44A2D;
}}
QSlider::handle:horizontal:hover {{ border-color: #8E3420; }}
QCheckBox {{ color: {TEXT_2}; font-size: {px(13)}px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    background: {INPUT}; border: 1px solid #CFC5B2;
}}
QCheckBox::indicator:checked {{ background: #B44A2D; border-color: #B44A2D; }}

/* ================= 滚动 ================= */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 3px 2px; }}
QScrollBar::handle:vertical {{
    background: #CFC5B2; border-radius: 4px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: #B6A991; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 3px; }}
QScrollBar::handle:horizontal {{
    background: #CFC5B2; border-radius: 4px; min-width: 36px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ================= 进度 ================= */
QProgressBar {{
    background: #E8DFCF;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #B44A2D, stop:1 #C08A2E);
    border-radius: 4px;
}}

/* ================= 文本 / 列表 ================= */
QTextEdit#LogBody, QPlainTextEdit {{
    background: #F7F1E5;
    border: 1px solid #DDD3C1;
    border-radius: 10px;
    color: {TEXT_2};
    font-family: {MONO_STACK};
    font-size: {px(12)}px;
    padding: 9px 11px;
    selection-background-color: {BRAND};
    selection-color: #FFF8F0;
}}
QListWidget {{ background: transparent; border: none; outline: 0; }}
QToolTip {{
    background: {SIDEBAR};
    color: #F7F0E4;
    border: 1px solid {SIDEBAR_LINE};
    border-radius: 8px;
    padding: 7px 10px;
    font-size: {px(12)}px;
}}

/* ================= 对话框 ================= */
QDialog#Dialog {{ background: #FBF8F2; border: 1px solid {BORDER_HI}; border-radius: 18px; }}
QFrame#DialogCard {{ background: transparent; border: none; }}
QFrame#ProgressCard {{
    background: #FCF9F3;
    border: 1px solid #D8CDBA;
    border-radius: 20px;
}}
QFrame#Toast {{
    background: #FFFCF6;
    border: 1px solid {BORDER_HI};
    border-radius: 12px;
}}
QLabel#ToastText {{ color: {TEXT}; font-size: {px(13)}px; font-weight: 600; }}

/* ================= 菜单 ================= */
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER_HI};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; color: {TEXT_2}; }}
QMenu::item:selected {{ background: #F1E7D9; color: {TEXT}; }}
"""
