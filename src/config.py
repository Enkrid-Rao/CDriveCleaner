"""配置加载与路径解析。

从 config.json 读取配置，展开占位符（{USERPROFILE} / {TEMP}），
提供运行时常量供其他模块使用。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# ===== 运行时环境变量 =====
BASE_USER = os.getenv("USERPROFILE") or os.path.expanduser("~")
TEMP_DIR = os.getenv("TEMP") or os.path.join(BASE_USER, "AppData", "Local", "Temp")
CURRENT_USER = os.getenv("USERNAME") or "Everyone"


def _get_project_root() -> Path:
    """获取项目根目录，兼容源码运行和 PyInstaller 打包。

    - 源码运行：config.py 的上两级
    - 打包运行：exe 所在目录（onefile 模式下 config.json 应在 exe 旁边）
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _get_project_root()
CONFIG_PATH = PROJECT_ROOT / "config.json"

# 占位符映射表
_PLACEHOLDERS = {
    "{USERPROFILE}": BASE_USER,
    "{TEMP}": TEMP_DIR,
    "{USERNAME}": CURRENT_USER,
}


def _expand_path(raw: str, placeholders: dict[str, str] | None = None) -> str:
    """展开路径中的占位符。"""
    ph = placeholders if placeholders is not None else _PLACEHOLDERS
    result = raw
    for token, value in ph.items():
        result = result.replace(token, value)
    return result

def _default_config() -> dict[str, Any]:
    """首次运行时生成默认配置（与 config.json 内容一致）。"""
    return {
        "version": "1.0",
        "port": 8765,
        "threshold_mb": 100,
        "target_drive": "D",
        "temp_retention_days": 1,
        "zones": {
            "programs": {
                "source": "{USERPROFILE}\\AppData\\Local\\Programs",
                "dest_base": "{TARGET_DRIVE}\\AppData\\Programs",
                "no_go": [],
                "label": "应用程序",
                "icon": "📦",
                "needs_admin": False,
            },
            "local": {
                "source": "{USERPROFILE}\\AppData\\Local",
                "dest_base": "{TARGET_DRIVE}\\AppData\\Local",
                "no_go": ["Microsoft", "Packages", "Comms", "Deployment", "assembly",
                          "Application Data", "Temp", "Programs"],
                "label": "应用数据(Local)",
                "icon": "📁",
                "needs_admin": False,
            },
            "roaming": {
                "source": "{USERPROFILE}\\AppData\\Roaming",
                "dest_base": "{TARGET_DRIVE}\\AppData\\Roaming",
                "no_go": ["Microsoft"],
                "label": "应用数据(Roaming)",
                "icon": "🔄",
                "needs_admin": False,
            },
            "localLow": {
                "source": "{USERPROFILE}\\AppData\\LocalLow",
                "dest_base": "{TARGET_DRIVE}\\AppData\\LocalLow",
                "no_go": ["Microsoft"],
                "label": "应用数据(LocalLow)",
                "icon": "⬇️",
                "needs_admin": False,
            },
            "programdata": {
                "source": "C:\\ProgramData",
                "dest_base": "{TARGET_DRIVE}\\ProgramData",
                "no_go": ["Microsoft", "Package Cache", "Windows", "NVIDIA Corporation",
                          "Intel", "Adobe", "USOShared", "SoftwareDistribution",
                          "System32", "Ssh", "ssh", "MicrosoftSearch", "WinAmp"],
                "label": "共享数据(ProgramData)",
                "icon": "🗄️",
                "needs_admin": True,
            },
            "programfiles": {
                "source": "C:\\Program Files",
                "dest_base": "{TARGET_DRIVE}\\Program Files",
                "no_go": ["Microsoft", "Microsoft Visual Studio", "Microsoft Office", "Microsoft OneDrive",
                          "Windows Defender", "Windows Defender Advanced Threat Protection", "Windows Security",
                          "Adobe", "Common Files", "Internet Explorer",
                          "WindowsApps", "ModifiableWindowsApps", "Windows Communication Foundation",
                          "Windows Media Player", "Windows Photo Viewer", "Windows Portable Devices",
                          "Windows Sidebar", "MSBuild", "dotnet", "Reference Assemblies",
                          "NVIDIA Corporation", "WSL"],
                "label": "应用本体(Program Files)",
                "icon": "💼",
                "needs_admin": True,
            },
        },
    }


def load_config() -> dict[str, Any]:
    """加载配置文件。

    如果 config.json 不存在，则生成默认配置并写入磁盘。
    读取后展开所有 zone 的 source/dest_base 占位符。
    """
    if not CONFIG_PATH.exists():
        print(f"[config] 首次运行，生成默认配置: {CONFIG_PATH}")
        default = _default_config()
        CONFIG_PATH.write_text(
            json.dumps(default, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return _expand_config(default)

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[config] 配置文件损坏，回退默认配置: {exc}")
        return _expand_config(_default_config())

    return _expand_config(raw)


def _expand_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """展开配置中所有 zone 的路径占位符。"""
    # 动态读取 target_drive，合并到占位符表
    # target_drive 在 config.json 里是 "D"（不带冒号），展开成 Windows 盘符
    # 必须带冒号 "D:"，否则 dest_base 会变成相对路径 "D\AppData\Local"，
    # 被 robocopy 相对工作目录解析，数据错误落进 exe 同级 D\ 子文件夹。
    target_drive = cfg.get("target_drive", "D")
    if not target_drive.endswith(":"):
        target_drive = target_drive + ":"
    placeholders = dict(_PLACEHOLDERS)
    placeholders["{TARGET_DRIVE}"] = target_drive

    zones = cfg.get("zones", {})
    for zone_key, zone in zones.items():
        if "source" in zone:
            zone["source"] = _expand_path(zone["source"], placeholders)
        if "dest_base" in zone:
            zone["dest_base"] = _expand_path(zone["dest_base"], placeholders)
    return cfg


# 模块加载时即读取配置，供其他模块直接 import
CONFIG = load_config()
SCAN_ZONES: dict[str, dict[str, Any]] = CONFIG.get("zones", {})
PORT: int = CONFIG.get("port", 8765)
DEFAULT_THRESHOLD_MB: int = CONFIG.get("threshold_mb", 100)
TEMP_RETENTION_DAYS: int = CONFIG.get("temp_retention_days", 1)
