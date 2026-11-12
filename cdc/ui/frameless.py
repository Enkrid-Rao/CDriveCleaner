"""无边框窗口的四边/四角缩放（Win32 canonical 方案）。

与 v1 相同思路：showEvent 附加 WS_THICKFRAME，nativeEvent 处理命中测试；
WM_NCCALCSIZE 不拦截，避免客户区与 Qt 布局错位。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes.wintypes import MSG, POINT

from PySide6.QtGui import QCursor

GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WM_GETMINMAXINFO = 0x0024
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", POINT), ("ptMaxSize", POINT),
                ("ptMaxPosition", POINT), ("ptMinTrackSize", POINT),
                ("ptMaxTrackSize", POINT)]


def _is_win() -> bool:
    return sys.platform == "win32"


class ResizableFrameless:
    BORDER: int = 7

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        if _is_win():
            self._apply_thickframe()

    def _apply_thickframe(self) -> None:
        try:
            hwnd = int(self.winId())
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
            needed = WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
            if style & needed == needed:
                return
            style |= needed
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE,
            )
        except Exception:
            pass

    @staticmethod
    def _hit_test(x: int, y: int, w: int, h: int, border: int) -> int:
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

    def nativeEvent(self, eventType, message):  # noqa: N802
        if not _is_win():
            return super().nativeEvent(eventType, message)
        if eventType == b"windows_generic_MSG":
            msg = MSG.from_address(int(message))
            if msg.message == WM_GETMINMAXINFO:
                info = _MINMAXINFO.from_address(msg.lParam)
                info.ptMinTrackSize.x = self.minimumWidth() or 1080
                info.ptMinTrackSize.y = self.minimumHeight() or 700
                return True, 0
            if msg.message == WM_NCHITTEST and not self.isMaximized():
                pos = QCursor.pos()
                g = self.frameGeometry()
                hit = self._hit_test(pos.x() - g.x(), pos.y() - g.y(),
                                     g.width(), g.height(), self.BORDER)
                if hit != HTCLIENT:
                    return True, hit
        return super().nativeEvent(eventType, message)
