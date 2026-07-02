"""DiskJunction - 用 NTFS Junction 把 C 盘大目录无损迁移到 D 盘。

入口模块，启动 HTTP 服务。
"""

from __future__ import annotations

from .config import PORT


def main() -> None:
    """启动 DiskJunction HTTP 服务。"""
    # 延迟导入，避免循环依赖
    from .web_api import create_server

    print(f"DiskJunction 启动: http://localhost:{PORT}")
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
