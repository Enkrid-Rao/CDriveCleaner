"""字体与 Qt 应用级字体设置。"""

from __future__ import annotations

from PySide6.QtGui import QFont


def apply_font(app, ui_family: str, mono_family: str, size: int = 13) -> None:
    font = QFont(ui_family, size)
    font.setStyleHint(QFont.SansSerif)
    font.setFamilies([ui_family, "Microsoft YaHei UI", "Microsoft YaHei",
                      "Segoe UI", "PingFang SC"])
    app.setFont(font)
