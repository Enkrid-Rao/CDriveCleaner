"""配置加载与路径解析。

从 config.json 读取配置，展开占位符（{USERPROFILE} / {TEMP} / {TARGET_BASE} 等），
提供运行时常量供其他模块使用。

设计要点
--------
- ``RAW_CONFIG``  : 原始配置（占位符保持原样，例如 ``{TARGET_BASE}\\AppData\\Local``）。
                    GUI 编辑器直接读写它，保存时原样落盘。
- ``CONFIG``      : 展开后的配置（占位符已替换为真实路径），供运行时逻辑使用。
- ``SCAN_ZONES`` 等 : 模块级运行时常量。**reload_config() 会以 in-place 方式更新它们，
                    因此 ``from .config import SCAN_ZONES`` 的调用方也能看到新值**，
                    无需重启进程。

目标路径 ``target_base``
-----------------------
早期版本只支持 ``target_drive``（盘符，如 ``"D"``）。为支持「自定义根路径」
（如 ``D:\\`` 或 ``D:\\Junctions``），新增 ``target_base`` 字段，表示迁移数据的
**完整存放根路径**。zone 的 ``dest_base`` 统一使用 ``{TARGET_BASE}`` 占位符。
旧配置里的 ``{TARGET_DRIVE}`` 会在加载时自动迁移为 ``{TARGET_BASE}``。
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

# 占位符映射表（基础环境变量）
_BASE_PLACEHOLDERS = {
    "{USERPROFILE}": BASE_USER,
    "{TEMP}": TEMP_DIR,
    "{USERNAME}": CURRENT_USER,
}


# ============================================================
# 默认配置（与 config.json 内容一致）
# ============================================================

def _default_config() -> dict[str, Any]:
    """首次运行时生成默认配置。

    target_base 默认 ``"D:\\_CDrive"``（迁移容器，1:1 仿 C 盘结构）。
    zone 的 dest_base 统一使用 ``{TARGET_BASE}`` 占位符，
    并按 C 盘原路径组织（如 ``{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Local``）。
    """
    return {
        "version": "1.0",
        "port": 8765,
        "threshold_mb": 100,
        "target_drive": "D",
        "target_base": "D:\\_CDrive",
        "temp_retention_days": 1,
        "log_dir": "",
        "ui": {
            "font_family": "",
            "font_size": 0,
        },
        "zones": {
            "userhome": {
                "source": "{USERPROFILE}",
                "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}",
                "no_go": [
                    "AppData", "Documents", "Downloads", "Desktop", "Pictures", "Videos",
                    "Music", "OneDrive", "Contacts", "Favorites", "Links", "Saved Games",
                    "Searches", "3D Objects", "NetHood", "PrintHood", "Recent", "SendTo",
                    "Templates", "「开始」菜单", "Application Data", "Local Settings",
                    "My Documents", "Cookies", "History", "IntelGraphicsProfiles",
                    "MicrosoftEdgeBackups", ".ssh", ".gnupg",
                    "NTUSER.DAT", "ntuser.dat", "NTUSER.DAT.LOG1", "NTUSER.DAT.LOG2",
                    "ntuser.ini", "WorkBuddy AI",
                ],
                "label": "用户主目录",
                "icon": "🏠",
                "needs_admin": False,
                "skip_nogo_size": True,
            },
            "programs": {
                "source": "{USERPROFILE}\\AppData\\Local\\Programs",
                "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Local\\Programs",
                "no_go": [],
                "label": "应用程序",
                "icon": "📦",
                "needs_admin": False,
            },
            "local": {
                "source": "{USERPROFILE}\\AppData\\Local",
                "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Local",
                "no_go": ["Microsoft", "Packages", "Comms", "Deployment", "assembly",
                          "Application Data", "Temp", "Programs"],
                "label": "应用数据(Local)",
                "icon": "📁",
                "needs_admin": False,
            },
            "roaming": {
                "source": "{USERPROFILE}\\AppData\\Roaming",
                "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\Roaming",
                "no_go": ["Microsoft"],
                "label": "应用数据(Roaming)",
                "icon": "🔄",
                "needs_admin": False,
            },
            "localLow": {
                "source": "{USERPROFILE}\\AppData\\LocalLow",
                "dest_base": "{TARGET_BASE}\\Users\\{USERNAME}\\AppData\\LocalLow",
                "no_go": ["Microsoft"],
                "label": "应用数据(LocalLow)",
                "icon": "⬇️",
                "needs_admin": False,
            },
            "programdata": {
                "source": "C:\\ProgramData",
                "dest_base": "{TARGET_BASE}\\ProgramData",
                "no_go": ["Microsoft", "Package Cache", "Windows", "NVIDIA Corporation",
                          "Intel", "Adobe", "USOShared", "SoftwareDistribution",
                          "System32", "Ssh", "ssh", "MicrosoftSearch", "WinAmp"],
                "label": "共享数据(ProgramData)",
                "icon": "🗄️",
                "needs_admin": True,
            },
            "programfiles": {
                "source": "C:\\Program Files",
                "dest_base": "{TARGET_BASE}\\Program Files",
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


# ============================================================
# 路径工具
# ============================================================

def _normalize_base(raw_base: str, raw_drive: str) -> str:
    """规范化目标根路径。

    返回不带结尾反斜杠的绝对路径，例如 ``"D:\\Junctions"`` 或 ``"D:"``。
    - 优先用 ``raw_base``（完整根路径）。
    - 若为空，从 ``raw_drive``（盘符，如 ``"D"``）推导为 ``"D:"``。
    - 非法路径（非绝对）回退到 ``raw_drive`` 推导值。
    """
    base = (raw_base or "").strip()
    if not base:
        drive = (raw_drive or "D").strip()
        if not drive.endswith(":"):
            drive = drive + ":"
        return drive

    base = base.replace("/", "\\")
    base = base.rstrip("\\")

    # 必须是带盘符的绝对路径（如 D:\... / D:）或 UNC 路径（\\server\share）
    is_drive = len(base) >= 2 and base[1] == ":" and base[0].isalpha()
    is_unc = base.startswith("\\\\")
    if not (is_drive or is_unc):
        drive = (raw_drive or "D").strip()
        if not drive.endswith(":"):
            drive = drive + ":"
        return drive
    return base


def _expand_path(raw: str, placeholders: dict[str, str]) -> str:
    """展开路径中的占位符。"""
    result = raw
    for token, value in placeholders.items():
        result = result.replace(token, value)
    return result


def _build_placeholders(cfg: dict[str, Any]) -> dict[str, str]:
    """根据当前配置构建占位符表（含 TARGET_BASE / TARGET_DRIVE）。"""
    target_base = _normalize_base(cfg.get("target_base", ""), cfg.get("target_drive", "D"))
    drive_letter = target_base[0].upper() + ":"  # 如 "D:"

    ph = dict(_BASE_PLACEHOLDERS)
    ph["{TARGET_BASE}"] = target_base
    ph["{TARGET_DRIVE}"] = drive_letter
    return ph


def _expand_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """展开配置中所有 zone 的路径占位符（返回原 dict，in-place 修改）。"""
    placeholders = _build_placeholders(cfg)
    zones = cfg.get("zones", {})
    for zone_key, zone in zones.items():
        if "source" in zone:
            zone["source"] = _expand_path(zone["source"], placeholders)
        if "dest_base" in zone:
            zone["dest_base"] = _expand_path(zone["dest_base"], placeholders)
    return cfg


# ============================================================
# 加载 / 保存 / 热重载
# ============================================================

def _migrate_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """迁移旧配置到新 schema（in-memory，不写盘）。

    - 缺 ``target_base`` → 由 ``target_drive`` 推导。
    - zone 的 ``dest_base`` 里残留的 ``{TARGET_DRIVE}`` → ``{TARGET_BASE}``。
    - 缺 ``ui`` / ``log_dir`` → 补默认值。
    """
    if "target_base" not in raw:
        raw["target_base"] = _normalize_base("", raw.get("target_drive", "D"))

    # zones: 旧占位符迁移
    for zone in raw.get("zones", {}).values():
        db = zone.get("dest_base", "")
        if "{TARGET_DRIVE}" in db:
            zone["dest_base"] = db.replace("{TARGET_DRIVE}", "{TARGET_BASE}")

    if "ui" not in raw or not isinstance(raw.get("ui"), dict):
        raw["ui"] = {"font_family": "", "font_size": 0}
    raw["ui"].setdefault("font_family", "")
    raw["ui"].setdefault("font_size", 0)

    raw.setdefault("log_dir", "")
    return raw


def load_raw_config() -> dict[str, Any]:
    """加载原始配置（占位符保持原样）。

    文件不存在 → 生成默认配置并写盘；文件损坏 → 回退默认。
    加载后会执行迁移（旧配置兼容）。
    """
    global RAW_CONFIG

    if not CONFIG_PATH.exists():
        print(f"[config] 首次运行，生成默认配置: {CONFIG_PATH}")
        default = _default_config()
        CONFIG_PATH.write_text(
            json.dumps(default, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        RAW_CONFIG = default
        return default

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[config] 配置文件损坏，回退默认配置: {exc}")
        RAW_CONFIG = _default_config()
        return RAW_CONFIG

    raw = _migrate_raw(raw)
    RAW_CONFIG = raw
    return raw


def save_config(raw: dict[str, Any]) -> None:
    """把原始配置（含占位符）写回 config.json。"""
    CONFIG_PATH.write_text(
        json.dumps(raw, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def reload_config() -> dict[str, Any]:
    """重新从磁盘加载配置，并 **in-place** 更新所有运行时常量。

    因为 SCAN_ZONES 等以 in-place 方式更新，调用方即使用了
    ``from .config import SCAN_ZONES`` 也能立即看到新值。
    """
    global RAW_CONFIG, CONFIG, SCAN_ZONES, PORT
    global DEFAULT_THRESHOLD_MB, TEMP_RETENTION_DAYS, TARGET_BASE, TARGET_DRIVE

    raw = load_raw_config()
    expanded = _expand_config(_deep_copy(raw))

    # in-place 更新 SCAN_ZONES（保持对象引用，调用方可见）
    SCAN_ZONES.clear()
    SCAN_ZONES.update(expanded.get("zones", {}))

    CONFIG = expanded
    PORT = expanded.get("port", 8765)
    DEFAULT_THRESHOLD_MB = expanded.get("threshold_mb", 100)
    TEMP_RETENTION_DAYS = expanded.get("temp_retention_days", 1)

    tb = _normalize_base(raw.get("target_base", ""), raw.get("target_drive", "D"))
    TARGET_BASE = tb
    TARGET_DRIVE = tb[0].upper() + ":"

    return expanded


def _deep_copy(d: Any) -> Any:
    """简单深拷贝（避免修改 RAW_CONFIG）。"""
    return json.loads(json.dumps(d))


def get_effective_log_dir() -> str:
    """返回解析后的日志目录；空字符串表示使用默认（项目 logs/）。"""
    raw = RAW_CONFIG.get("log_dir", "") or ""
    if not raw.strip():
        return ""
    return _expand_path(raw, _BASE_PLACEHOLDERS)


def get_ui_font() -> tuple[str, int]:
    """返回 (字体家族, 字号)。空家族 / 0 字号表示「自动」。"""
    ui = RAW_CONFIG.get("ui", {}) or {}
    return (ui.get("font_family", "") or "", int(ui.get("font_size", 0) or 0))


# ============================================================
# 模块加载时初始化运行时常量
# ============================================================

RAW_CONFIG: dict[str, Any] = load_raw_config()
CONFIG: dict[str, Any] = _expand_config(_deep_copy(RAW_CONFIG))

SCAN_ZONES: dict[str, dict[str, Any]] = CONFIG.get("zones", {})
PORT: int = CONFIG.get("port", 8765)
DEFAULT_THRESHOLD_MB: int = CONFIG.get("threshold_mb", 100)
TEMP_RETENTION_DAYS: int = CONFIG.get("temp_retention_days", 1)

_TARGET_BASE = _normalize_base(RAW_CONFIG.get("target_base", ""), RAW_CONFIG.get("target_drive", "D"))
TARGET_BASE: str = _TARGET_BASE
TARGET_DRIVE: str = _TARGET_BASE[0].upper() + ":"

# 目录大小计算后端：
#   "auto"       → 优先 Everything CLI（es.exe，走 NTFS 索引，0.1~0.3s/目录）
#   "powershell" → 强制 PowerShell 递归（慢，但不依赖 Everything 索引，绝对精确）
SIZE_BACKEND: str = (RAW_CONFIG.get("size_backend") or "auto").strip().lower()
