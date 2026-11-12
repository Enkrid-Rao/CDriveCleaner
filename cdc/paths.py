"""运行路径：源码 / 安装版 / 便携版三种形态。

数据目录规则
------------
- 环境变量 ``CDC_DATA_DIR`` 优先（测试与高级用户）。
- 便携版（exe 同级存在 ``portable.flag``）→ ``<程序目录>\\data``。
- 安装版（PyInstaller frozen）→ ``%LOCALAPPDATA%\\CDriveCleaner``。
- 源码运行 → 仓库根目录（兼容旧版 ``config.json`` 与 ``logs/``）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CDriveCleaner"
PORTABLE_MARKER = "portable.flag"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    """exe 所在目录；源码运行时为仓库根目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """只读资源目录（打包后为 PyInstaller 解包目录）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def is_portable() -> bool:
    if os.environ.get("CDC_PORTABLE") == "1":
        return True
    return (executable_dir() / PORTABLE_MARKER).is_file()


def data_dir() -> Path:
    override = os.environ.get("CDC_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if is_frozen():
        if is_portable():
            return executable_dir() / "data"
        local = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(local) / APP_NAME
    return Path(__file__).resolve().parent.parent


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    # 源码形态且仓库根已有 config.json → 沿用（v1 兼容）
    custom = os.environ.get("CDC_CONFIG", "").strip()
    if custom:
        return Path(custom).expanduser()
    return data_dir() / "config.json"


def logs_dir() -> Path:
    return ensure_dir(data_dir() / "logs")


def audit_path() -> Path:
    return ensure_dir(data_dir() / "state") / "audit.jsonl"


def manifests_dir() -> Path:
    return ensure_dir(data_dir() / "state" / "manifests")


def backups_dir() -> Path:
    return ensure_dir(data_dir() / "state" / "backups")


def cache_dir() -> Path:
    return ensure_dir(data_dir() / "state" / "cache")


def jobs_dir() -> Path:
    return ensure_dir(data_dir() / "state" / "jobs")


def crash_log_path() -> Path:
    return logs_dir() / "crash.log"


def asset_path(*parts: str) -> Path:
    """定位打包资源（图标等）。"""
    direct = resource_dir().joinpath(*parts)
    if direct.exists():
        return direct
    return executable_dir().joinpath(*parts)


def is_source_checkout() -> bool:
    return not is_frozen()


def app_label() -> str:
    return "便携版" if is_portable() else ("安装版" if is_frozen() else "源码模式")
