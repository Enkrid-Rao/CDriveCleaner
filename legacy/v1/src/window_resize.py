"""无边框窗口边缘/四角拖拽缩放（canonical Win32 方案）。

MainWindow 与 SettingsWindow 都是 ``Qt.FramelessWindowHint``，在 Windows 下等价于
``WS_POPUP``（无厚边框），因此原生只能靠标题栏移动 + 最大化，无法自由缩放。

本混入类采用业界标准做法（参考 PsinaDev/pyside-frameless + Microsoft WM_NCHITTEST 文档）：

1. ``showEvent`` 给窗口加 ``WS_THICKFRAME`` 等窗口样式 → 让 OS 原生支持
   **四边 + 四角** 缩放与 Aero 贴边（Snap）。这是"只能左右缩放"的根治手段
   （纯 ``WM_NCHITTEST`` 在 ``WS_POPUP`` 下四角缩放会被 OS 忽略）。

2. ``WM_NCCALCSIZE`` 返回 0 → 去掉可见边框，但保留 sizing border 与阴影，
   外观仍是无边框玻璃风。

3. ``WM_NCHITTEST`` 用 ``QCursor.pos()``（Qt **逻辑像素**）相对
   ``frameGeometry().topLeft()``（**逻辑像素**）计算命中区。
   两者处于同一坐标空间，``BORDER`` 即真实逻辑像素 → 在 100% / 125% / 150% / 175%
   等任意 DPI 下命中区**视觉大小一致**，不写死任何设备的缩放比。

仅 Windows 生效；其他平台（含 offscreen 测试）直接走基类实现。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes.wintypes import MSG, POINT

from PySide6.QtGui import QCursor

# ---- Win32 窗口样式常量 ----
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000

# ---- Win32 消息常量 ----
WM_NCCALCSIZE = 0x0083
WM_GETMINMAXINFO = 0x0024
WM_NCHITTEST = 0x0084

# ---- 命中区域常量 ----
HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# ---- SetWindowPos 标志 ----
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

# MINMAXINFO 结构（用于 WM_GETMINMAXINFO 兜底最小尺寸）
class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", POINT),
        ("ptMaxSize", POINT),
        ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT),
        ("ptMaxTrackSize", POINT),
    ]


# NCCALCSIZE_PARAMS（用于 WM_NCCALCSIZE 时精确控制客户区）
class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [
        ("rgrc", _RECT * 3),       # [0]=新客户区  [1]=原窗口rect  [2]=原客户区
        ("lppos", ctypes.c_void_p),
    ]


def _is_win() -> bool:
    return sys.platform == "win32"


class ResizableFrameless:
    """混入类：为无边框窗口添加四边/四角自由缩放。

    使用方式：``class MyWindow(ResizableFrameless, QMainWindow):``
    须放在 Qt 窗口基类之前，以便 ``super().nativeEvent`` / ``super().showEvent``
    落到基类实现。对调用方完全透明，无需额外代码。
    """

    #: 边缘命中带宽（逻辑像素）。任意 DPI 下视觉大小一致。
    BORDER: int = 8

    # ---------- 让 OS 提供原生 sizing border ----------
    def showEvent(self, event):  # noqa: N802  (Qt 命名)
        super().showEvent(event)
        if _is_win():
            self._apply_thickframe()

    def _apply_thickframe(self) -> None:
        """给窗口附加 WS_THICKFRAME，使 OS 支持四边/四角缩放与 Aero Snap。

        幂等：若样式位已齐全则直接返回，避免重复触发 SWP_FRAMECHANGED ->
        WM_NCCALCSIZE 在 show/exec 过程中再次打乱 Qt 的 client 区域与布局。
        """
        try:
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
            needed = WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
            if style & needed == needed:
                return  # 已经应用过，跳过
            style |= needed
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
            # 通知 OS 样式已变，触发边框重算
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
        except Exception:
            # 非 Windows / winId 不可用 / 调用失败 → 退回逻辑仍由 nativeEvent 处理
            pass

    # ---------- 命中测试（纯函数，便于单测） ----------
    @staticmethod
    def _hit_test(x: int, y: int, w: int, h: int, border: int) -> int:
        """返回给定相对坐标命中的区域常量（HT*）。"""
        left = x < border
        right = x > w - border
        top = y < border
        bottom = y > h - border
        if top and left:
            return HTTOPLEFT
        if top and right:
            return HTTOPRIGHT
        if bottom and left:
            return HTBOTTOMLEFT
        if bottom and right:
            return HTBOTTOMRIGHT
        if left:
            return HTLEFT
        if right:
            return HTRIGHT
        if top:
            return HTTOP
        if bottom:
            return HTBOTTOM
        return HTCLIENT

    # ---------- 消息拦截 ----------
    def nativeEvent(self, eventType, message):  # noqa: N802  (Qt 命名)
        if not _is_win():
            return super().nativeEvent(eventType, message)

        # PySide6 实机中 eventType 为 bytes（QByteArray）
        if eventType == b"windows_generic_MSG":
            msg = MSG.from_address(int(message))

            # 1) 不再拦截 WM_NCCALCSIZE（关键修复）
            #    曾尝试在此返回 0（或把 rgrc[0] 设为整窗）以"去边框"，
            #    但改写客户区会让系统认知的客户区与 Qt 基于无边框自绘的整窗布局
            #    不一致 → 内容被推出可见区（输入框全无 / 只剩左上角）。
            #    权威资料（winsoft666/Qt-FramelessWindow）也指出 Hook WM_NCCALCSIZE
            #    是无边框方案的已知 bug 温床，作者因此转投纯 Qt 方案。
            #    故让 WM_NCCALCSIZE 走系统默认：WS_THICKFRAME 自带极细边框，
            #    客户区由系统正确计算，内容必然可见（无标题栏 + 1px 细边框观感）。

            # 2) 兜底最小拖拽尺寸（读取 Qt 已设的 minimumSize）
            if msg.message == WM_GETMINMAXINFO:
                info = _MINMAXINFO.from_address(msg.lParam)
                info.ptMinTrackSize.x = self.minimumWidth() or 560
                info.ptMinTrackSize.y = self.minimumHeight() or 440
                return True, 0

            # 3) 命中测试：使用 Qt 逻辑像素坐标，DPI 通用
            if msg.message == WM_NCHITTEST and not self.isMaximized():
                pos = QCursor.pos()          # 逻辑像素（屏幕坐标）
                g = self.frameGeometry()     # 逻辑像素（屏幕坐标）
                x = pos.x() - g.x()
                y = pos.y() - g.y()
                hit = self._hit_test(x, y, g.width(), g.height(), self.BORDER)
                if hit != HTCLIENT:
                    return True, hit

        return super().nativeEvent(eventType, message)
