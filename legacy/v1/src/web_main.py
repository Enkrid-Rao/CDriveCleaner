"""CDriveCleaner_web - 仅 Web 服务模式入口（独立程序）。

与桌面 GUI（CDriveCleaner）完全分开打包：
  - 不依赖 PySide6，体积小（仅标准库 + 业务模块）；
  - 启动后浏览器访问 http://localhost:PORT 使用 Web UI；
  - 这是一个带终端窗口的控制台程序，可按 Ctrl+C 关闭。
"""

from __future__ import annotations

from . import config
from ._version import __version__


def main() -> None:
    """启动 HTTP Web 服务（阻塞，直到 Ctrl+C）。"""
    from .web_api import create_server

    print(f"CDriveCleaner_web v{__version__} - Web 模式: http://localhost:{config.PORT}")
    print(f"迁移容器: {config.TARGET_BASE}")
    print(f"扫描区域: {' + '.join(z.get('label', k) for k, z in config.SCAN_ZONES.items())}")
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
