"""PowerShell 执行辅助函数。

所有需要调用 PowerShell 的模块共用此函数，
统一管理脚本文件生成与执行。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# 临时 ps1 脚本存放路径（与 config.py 同目录）
_SCRIPT_DIR = Path(__file__).resolve().parent
_TEMP_PS1 = _SCRIPT_DIR / "_temp_script.ps1"


def run_ps(script: str) -> tuple[str, str, int]:
    """运行 PowerShell 脚本并返回 (stdout, stderr, returncode)。

    使用 ps1 文件而非命令行参数，避免转义问题。
    脚本以 utf-8-sig 编码写入（PowerShell 需要 BOM）。
    """
    try:
        _TEMP_PS1.write_text(script, encoding="utf-8-sig")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(_TEMP_PS1)],
            capture_output=True, text=True, timeout=180,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "超时", 1
    except Exception as exc:
        return "", str(exc), 1


def run_ps_raw(script: str, timeout: int = 180) -> tuple[str, str, int]:
    """运行 PowerShell 脚本，可自定义超时时间。"""
    try:
        _TEMP_PS1.write_text(script, encoding="utf-8-sig")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(_TEMP_PS1)],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "超时", 1
    except Exception as exc:
        return "", str(exc), 1
