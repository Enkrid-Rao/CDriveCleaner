"""CDriveCleaner - 用 NTFS Junction 把 C 盘大目录无损迁移到 D 盘。

入口模块，支持双模式启动：
  默认      → PySide6 原生桌面 GUI
  --web     → 旧版 HTTP 服务（浏览器访问 localhost:PORT）
"""

from __future__ import annotations

import sys

from .config import PORT
from ._version import __version__


def main() -> None:
    """启动 CDriveCleaner。

    命令行参数：
      --web    使用旧版 HTTP Web 服务模式
      --gui    强制使用 GUI 模式（默认）
    """
    args = sys.argv[1:]
    use_web = "--web" in args or "--server" in args

    if use_web:
        _launch_web()
    else:
        _launch_gui()


def _launch_gui() -> None:
    """启动 PySide6 桌面 GUI。"""
    try:
        from .gui import launch
    except ImportError as exc:
        print(f"[GUI] 无法加载桌面界面（缺少 PySide6）: {exc}")
        print("[GUI] 回退到 Web 模式。安装 PySide6 可启用桌面版: pip install PySide6")
        print(f"[GUI] Web 模式启动: http://localhost:{PORT}")
        _launch_web()
        return

    print(f"CDriveCleaner v{__version__} - 桌面 GUI 模式")
    raise SystemExit(launch())


def _launch_web() -> None:
    """启动 HTTP Web 服务。"""
    from .web_api import create_server

    print(f"CDriveCleaner v{__version__} - Web 模式: http://localhost:{PORT}")
    print("支持扫描: Programs + AppData + ProgramData + Program Files")
    print("支持 UAC 管理员权限自动提升")
    print("只展示绿色安全项目，风险目录已隐藏")
    print("按 Ctrl+C 关闭服务")

    server = create_server()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
