"""PyInstaller 构建包装器。

解决 Git for Windows 的 uname.exe 导致 platform.system() 误报 CYGWIN 的问题。
在运行 PyInstaller 前强制修正 platform 模块的返回值。

用法:
    python build_helper.py                # 构建全部（gui + web）
    python build_helper.py --target gui   # 仅构建桌面 GUI（CDriveCleaner.exe）
    python build_helper.py --target web   # 仅构建 Web 服务（CDriveCleaner_web.exe）
"""

import argparse
import platform
import shutil
import socket
from pathlib import Path

# 先获取 hostname（避免递归）
_hostname = socket.gethostname()

# 构造固定的 uname_result（Python 3.11 的 uname_result 不含 processor 参数）
_fixed_uname = platform.uname_result(
    system='Windows',
    node=_hostname,
    release='10',
    version='10.0.22631',
    machine='AMD64',
)

# 强制覆盖 platform 模块的函数
platform.system = lambda: 'Windows'
platform.uname = lambda: _fixed_uname
platform.node = lambda: _hostname
platform.release = lambda: '10'
platform.version = lambda: '10.0.22631'
platform.machine = lambda: 'AMD64'
platform.processor = lambda: 'Intel64 Family 6 Model 183 Stepping 1, GenuineIntel'

SPECS = {
    "gui": "CDriveCleaner.spec",
    "web": "CDriveCleaner_web.spec",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 CDriveCleaner 可执行程序")
    parser.add_argument(
        "--target",
        choices=["gui", "web", "all"],
        default="all",
        help="构建目标：gui=桌面 GUI，web=Web 服务，all=两者（默认）",
    )
    args = parser.parse_args()

    specs = [SPECS["gui"], SPECS["web"]] if args.target == "all" else [SPECS[args.target]]

    # 现在启动 PyInstaller
    from PyInstaller.__main__ import run

    for spec in specs:
        print(f"\n========== 构建 {spec} ==========")
        run([spec, "--noconfirm"])

    # 构建完成后，把 config.json 复制到 dist/，让两个 exe 共享同一份配置
    dist_dir = Path("dist")
    if dist_dir.exists():
        shutil.copy("config.json", dist_dir / "config.json")
        print(f"\n已复制 config.json -> {dist_dir / 'config.json'}（GUI 与 Web 共享）")


if __name__ == "__main__":
    main()
