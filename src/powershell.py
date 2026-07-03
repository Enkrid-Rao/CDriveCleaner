"""PowerShell 执行辅助函数。

所有需要调用 PowerShell 的模块共用此函数，
统一管理脚本文件生成与执行。

Windows 上 subprocess 默认会弹控制台窗口，GUI 模式下尤其碍眼。
这里统一用 CREATE_NO_WINDOW 标志隐藏所有子进程窗口。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Windows 隐藏子进程窗口的标志位
# CREATE_NO_WINDOW = 0x08000000，Python 3.7+ 已内置为 subprocess.CREATE_NO_WINDOW
# 这里做兼容兜底，防止某些环境取不到
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _get_script_dir() -> Path:
    """获取临时脚本存放目录，兼容源码运行和 PyInstaller 打包。

    - 源码运行：src/ 目录
    - 打包运行：exe 同级目录（临时 ps1 放在 exe 旁边）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_SCRIPT_DIR = _get_script_dir()
_TEMP_PS1 = _SCRIPT_DIR / "_temp_script.ps1"


def run_ps(script: str) -> tuple[str, str, int]:
    """运行 PowerShell 脚本并返回 (stdout, stderr, returncode)。

    使用 ps1 文件而非命令行参数，避免转义问题。
    脚本以 utf-8-sig 编码写入（PowerShell 需要 BOM）。
    子进程窗口已隐藏，GUI 模式下不会弹黑窗。
    """
    try:
        _TEMP_PS1.write_text(script, encoding="utf-8-sig")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(_TEMP_PS1)],
            capture_output=True, text=True, timeout=180,
            creationflags=_NO_WINDOW,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "超时", 1
    except Exception as exc:
        return "", str(exc), 1


def run_ps_raw(script: str, timeout: int = 180) -> tuple[str, str, int]:
    """运行 PowerShell 脚本，可自定义超时时间。子进程窗口已隐藏。"""
    try:
        _TEMP_PS1.write_text(script, encoding="utf-8-sig")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(_TEMP_PS1)],
            capture_output=True, text=True, timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "超时", 1
    except Exception as exc:
        return "", str(exc), 1
