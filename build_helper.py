"""PyInstaller 构建包装器。

解决 Git for Windows 的 uname.exe 导致 platform.system() 误报 CYGWIN 的问题。
在运行 PyInstaller 前强制修正 platform 模块的返回值。
"""

import platform
import socket

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

# 现在启动 PyInstaller
from PyInstaller.__main__ import run
run(['CDriveCleaner.spec', '--noconfirm'])
