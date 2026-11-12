"""CDriveCleaner - 用 NTFS Junction 把 C 盘大目录无损迁移到 D 盘。

桌面 GUI 版入口（PySide6）。
Web 服务模式是独立程序 CDriveCleaner_web（见 src/web_main.py），二者分开打包。
"""

from __future__ import annotations

from ._version import __version__


def main() -> None:
    """启动 CDriveCleaner 桌面 GUI。"""
    _launch_gui()


def _launch_gui() -> None:
    """启动 PySide6 桌面 GUI。"""
    from .gui import launch

    print(f"CDriveCleaner v{__version__} - 桌面 GUI 模式")
    raise SystemExit(launch())


if __name__ == "__main__":
    main()
