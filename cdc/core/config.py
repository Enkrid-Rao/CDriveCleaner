"""v2 配置：schema、占位符、v1 迁移、保存与备份。

配置只描述「数据放哪、什么能碰、界面长什么样」，不包含任何业务逻辑。
旧的 v1 config.json 会在内存中自动升级；首次保存时才写回 v2（并备份旧文件）。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import paths
from .models import MODE_MOVE

SCHEMA_VERSION = 2
APP_SECTION = "storage"

_BASE_PLACEHOLDERS = {
    "{USERPROFILE}": os.environ.get("USERPROFILE") or os.path.expanduser("~"),
    "{USERNAME}": os.environ.get("USERNAME") or "User",
    "{TEMP}": os.environ.get("TEMP") or os.path.join(
        os.environ.get("USERPROFILE") or os.path.expanduser("~"), "AppData", "Local", "Temp"),
}


# ============================================================
# 默认区域（与 v1 语义一致；UI 里按 kind 分组配色）
# ============================================================

def _default_zones() -> dict[str, dict[str, Any]]:
    return {
        "userhome": {
            "source": "{USERPROFILE}",
            "dest_base": "{LINK_ROOT}\\Users\\{USERNAME}",
            "no_go": [
                "AppData", "Documents", "Downloads", "Desktop", "Pictures", "Videos",
                "Music", "OneDrive", "Contacts", "Favorites", "Links", "Saved Games",
                "Searches", "3D Objects", "NetHood", "PrintHood", "Recent", "SendTo",
                "Templates", "「开始」菜单", "Application Data", "Local Settings",
                "My Documents", "Cookies", "History", "IntelGraphicsProfiles",
                "MicrosoftEdgeBackups", ".ssh", ".gnupg", "NTUSER.DAT", "ntuser.dat",
                "NTUSER.DAT.LOG1", "NTUSER.DAT.LOG2", "ntuser.ini", "WorkBuddy AI",
            ],
            "label": "用户主目录",
            "icon": "home",
            "kind": "user",
            "needs_admin": False,
            "skip_nogo_size": True,
        },
        "programs": {
            "source": "{USERPROFILE}\\AppData\\Local\\Programs",
            "dest_base": "{LINK_ROOT}\\Users\\{USERNAME}\\AppData\\Local\\Programs",
            "no_go": [],
            "label": "应用程序",
            "icon": "package",
            "kind": "program",
            "needs_admin": False,
        },
        "local": {
            "source": "{USERPROFILE}\\AppData\\Local",
            "dest_base": "{LINK_ROOT}\\Users\\{USERNAME}\\AppData\\Local",
            "no_go": ["Microsoft", "Packages", "Comms", "Deployment", "assembly",
                      "Application Data", "Temp", "Programs"],
            "label": "应用数据 · Local",
            "icon": "folder",
            "kind": "user",
            "needs_admin": False,
        },
        "roaming": {
            "source": "{USERPROFILE}\\AppData\\Roaming",
            "dest_base": "{LINK_ROOT}\\Users\\{USERNAME}\\AppData\\Roaming",
            "no_go": ["Microsoft"],
            "label": "应用数据 · Roaming",
            "icon": "refresh",
            "kind": "user",
            "needs_admin": False,
        },
        "localLow": {
            "source": "{USERPROFILE}\\AppData\\LocalLow",
            "dest_base": "{LINK_ROOT}\\Users\\{USERNAME}\\AppData\\LocalLow",
            "no_go": ["Microsoft"],
            "label": "应用数据 · LocalLow",
            "icon": "layers",
            "kind": "user",
            "needs_admin": False,
        },
        "programdata": {
            "source": "C:\\ProgramData",
            "dest_base": "{LINK_ROOT}\\ProgramData",
            "no_go": ["Microsoft", "Package Cache", "Windows", "NVIDIA Corporation",
                      "Intel", "Adobe", "USOShared", "SoftwareDistribution",
                      "System32", "Ssh", "ssh", "MicrosoftSearch", "WinAmp"],
            "label": "共享数据 · ProgramData",
            "icon": "database",
            "kind": "system",
            "needs_admin": True,
        },
        "programfiles": {
            "source": "C:\\Program Files",
            "dest_base": "{LINK_ROOT}\\Program Files",
            "no_go": ["Microsoft", "Microsoft Visual Studio", "Microsoft Office",
                      "Microsoft OneDrive", "Windows Defender",
                      "Windows Defender Advanced Threat Protection", "Windows Security",
                      "Adobe", "Common Files", "Internet Explorer", "WindowsApps",
                      "ModifiableWindowsApps", "Windows Communication Foundation",
                      "Windows Media Player", "Windows Photo Viewer",
                      "Windows Portable Devices", "Windows Sidebar", "MSBuild", "dotnet",
                      "Reference Assemblies", "NVIDIA Corporation", "WSL"],
            "label": "应用本体 · Program Files",
            "icon": "briefcase",
            "kind": "system",
            "needs_admin": True,
        },
    }


# ============================================================
# 默认配置 / 目标盘推断
# ============================================================

def _probe_drives() -> list[Any]:
    if os.environ.get("CDC_NO_PROBE") == "1":
        return []
    try:
        from .windows import list_drives
        return list_drives(cache_seconds=30)
    except Exception:
        return []


def _default_link_root() -> str:
    known = Path("D:/_CDrive")
    if known.exists():
        return r"D:\_CDrive"
    drives = [d for d in _probe_drives() if not d.is_system and d.drive_kind == 3]
    drives.sort(key=lambda d: d.free_bytes, reverse=True)
    if drives:
        return f"{drives[0].letter}:\\_CDrive"
    return r"D:\_CDrive"


def _default_archive_root() -> str:
    drives = [d for d in _probe_drives() if not d.is_system and d.drive_kind != 4]
    preferred = [d for d in drives if d.is_hdd or d.is_usb]
    pool = preferred or drives
    pool.sort(key=lambda d: (d.is_hdd, d.free_bytes), reverse=True)
    if pool:
        return f"{pool[0].letter}:\\ColdStore"
    return r"D:\ColdStore"


def _default_config() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "storage": {
            "link_root": _default_link_root(),
            "archive_root": _default_archive_root(),
            "threshold_mb": 100,
            "archive_min_mb": 200,
            "temp_retention_days": 1,
            "default_mode": MODE_MOVE,
        },
        "safety": {
            "check_locks": True,
            "strict_verify": False,
            "confirm_high_risk": True,
            "keep_manifests": 30,
            "delete_after_undo": True,
        },
        "appearance": {
            "font_size": 14,
            "motion": True,
            "density": "cozy",
        },
        "logging": {
            "dir": "",
            "keep_days": 30,
        },
        "ui": {
            "last_page": "dashboard",
            "window": {"width": 1280, "height": 820},
        },
        "zones": _default_zones(),
    }


# ============================================================
# 工具函数
# ============================================================

def _deep_copy(obj: Any) -> Any:
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _deep_merge(base: dict, override: dict) -> dict:
    result = _deep_copy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = _deep_copy(value)
    return result


def _norm(path: str) -> str:
    text = (path or "").strip().replace("/", "\\")
    if not text:
        return ""
    text = os.path.expandvars(os.path.expanduser(text))
    text = text.rstrip("\\")
    if len(text) == 2 and text[1] == ":":
        text += "\\"
    return text


def _is_abs(path: str) -> bool:
    if not path:
        return False
    if path.startswith("\\\\"):
        return True
    return len(path) >= 3 and path[1] == ":" and path[0].isalpha() and path[2] in "\\/"


def expand_path(raw: str, placeholders: dict[str, str]) -> str:
    text = raw or ""
    for token, value in placeholders.items():
        text = text.replace(token, value)
    return text


def _legacy_migrate(raw: dict[str, Any]) -> dict[str, Any]:
    """v1 → v2（内存）。保留未知键，避免丢用户自定义项。"""
    cfg = _default_config()
    cfg["zones"] = _deep_copy(raw.get("zones") or cfg["zones"])
    # 区域字段补齐 / 旧字段兼容
    for key, zone in cfg["zones"].items():
        zone.setdefault("label", key)
        zone.setdefault("icon", "folder")
        zone.setdefault("kind", "user")
        zone.setdefault("needs_admin", False)
        zone.setdefault("no_go", [])
        if "dest_base" in zone:
            zone["dest_base"] = (zone["dest_base"]
                                 .replace("{TARGET_BASE}", "{LINK_ROOT}")
                                 .replace("{TARGET_DRIVE}", "{LINK_ROOT}"))
    cfg["storage"]["link_root"] = _norm(
        raw.get("target_base")
        or (str(raw.get("target_drive") or "D").rstrip(":") + ":\\_CDrive")
    )
    cfg["storage"]["threshold_mb"] = int(raw.get("threshold_mb", 100) or 100)
    cfg["storage"]["archive_min_mb"] = int(raw.get("archive_min_mb", 200) or 200)
    cfg["storage"]["archive_root"] = _norm(raw.get("archive_root") or _default_archive_root())

    days = raw.get("temp_retention_days")
    if days is not None:
        cfg["storage"]["temp_retention_days"] = int(days)

    old_ui = raw.get("ui") or {}
    if old_ui.get("font_size"):
        cfg["appearance"]["font_size"] = int(old_ui["font_size"])
    if raw.get("log_dir"):
        cfg["logging"]["dir"] = str(raw["log_dir"])
    if raw.get("size_backend"):
        cfg.setdefault("advanced", {})["size_backend"] = raw["size_backend"]
    if raw.get("port"):
        cfg.setdefault("advanced", {})["legacy_port"] = raw["port"]
    # 保留旧版自定义键（如 zones 之外的配置）
    for key in ("zones", "target_base", "target_drive", "threshold_mb",
                "temp_retention_days", "ui", "log_dir", "version", "port",
                "size_backend", "archive_root", "archive_min_mb"):
        raw.pop(key, None)
    for key, value in raw.items():
        cfg.setdefault(key, _deep_copy(value))
    return cfg


def _strip_legacy_keys(cfg: dict[str, Any]) -> dict[str, Any]:
    for key in ("target_base", "target_drive", "threshold_mb", "temp_retention_days",
                "port", "log_dir", "size_backend", "ui", "_load_warning"):
        cfg.pop(key, None)
    return cfg


def _upgrade(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        version = int(str(raw.get("version") or "1").split(".")[0])
    except (TypeError, ValueError):
        version = 1
    if version >= SCHEMA_VERSION and isinstance(raw.get("storage"), dict):
        cfg = _deep_merge(_default_config(), raw)
        # 区域以用户配置为准（_deep_merge 会合并 dict，可能把默认 zone 混进来）
        cfg["zones"] = _deep_copy(raw.get("zones") or cfg["zones"])
        for key, zone in cfg["zones"].items():
            zone.setdefault("label", key)
            zone.setdefault("icon", "folder")
            zone.setdefault("kind", "user")
            zone.setdefault("needs_admin", False)
            zone.setdefault("no_go", [])
            zone["dest_base"] = (zone.get("dest_base", "")
                                 .replace("{TARGET_BASE}", "{LINK_ROOT}")
                                 .replace("{TARGET_DRIVE}", "{LINK_ROOT}"))
        cfg["version"] = SCHEMA_VERSION
        return _strip_legacy_keys(cfg)
    cfg = _legacy_migrate(copy.deepcopy(raw))
    cfg["version"] = SCHEMA_VERSION
    return _strip_legacy_keys(cfg)


# ============================================================
# Config 对象
# ============================================================

@dataclass
class Config:
    raw: dict[str, Any]
    path: Path
    link_root: str = ""
    archive_root: str = ""
    threshold_mb: int = 100
    archive_min_mb: int = 200
    temp_retention_days: int = 1
    default_mode: str = MODE_MOVE
    strict_verify: bool = False
    check_locks: bool = True
    confirm_high_risk: bool = True
    delete_after_undo: bool = True
    font_size: int = 14
    motion: bool = True
    density: str = "cozy"
    log_dir: str = ""
    keep_days: int = 30
    last_page: str = "dashboard"
    window_size: tuple[int, int] = (1280, 820)
    zones: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    # ---------- 访问器 ----------

    @property
    def threshold_bytes(self) -> int:
        return max(0, self.threshold_mb) * 1024 * 1024

    @property
    def archive_min_bytes(self) -> int:
        return max(0, self.archive_min_mb) * 1024 * 1024

    def zone(self, key: str) -> dict[str, Any]:
        return self.zones.get(key, {})

    def zone_list(self) -> list[dict[str, Any]]:
        rows = []
        for key, zone in self.zones.items():
            row = dict(zone)
            row["key"] = key
            rows.append(row)
        return rows

    def zone_for_path(self, path: str) -> dict[str, Any]:
        from .windows import path_within
        best: dict[str, Any] = {}
        best_len = -1
        for key, zone in self.zones.items():
            source = zone.get("source", "")
            if source and path_within(path, source):
                if len(source) > best_len:
                    best = dict(zone, key=key)
                    best_len = len(source)
        return best

    def needs_admin_for(self, path: str) -> bool:
        return bool(self.zone_for_path(path).get("needs_admin"))

    def is_no_go_name(self, path: str, name: str) -> bool:
        zone = self.zone_for_path(path)
        no_go = {str(x).casefold() for x in zone.get("no_go", [])}
        return name.casefold() in no_go

    def is_managed_target(self, path: str) -> bool:
        from .windows import path_within
        return bool(self.link_root) and path_within(path, self.link_root)

    def storage_dict(self) -> dict[str, Any]:
        return {
            "link_root": self.link_root,
            "archive_root": self.archive_root,
            "threshold_mb": self.threshold_mb,
            "archive_min_mb": self.archive_min_mb,
        }

    # ---------- 保存 ----------

    def to_raw(self) -> dict[str, Any]:
        raw = _deep_copy(self.raw)
        raw["version"] = SCHEMA_VERSION
        raw.setdefault("storage", {})
        raw["storage"].update({
            "link_root": self.link_root,
            "archive_root": self.archive_root,
            "threshold_mb": self.threshold_mb,
            "archive_min_mb": self.archive_min_mb,
            "temp_retention_days": self.temp_retention_days,
            "default_mode": self.default_mode,
        })
        raw.setdefault("safety", {})
        raw["safety"].update({
            "check_locks": self.check_locks,
            "strict_verify": self.strict_verify,
            "confirm_high_risk": self.confirm_high_risk,
            "keep_manifests": int(raw.get("safety", {}).get("keep_manifests", 30)),
            "delete_after_undo": self.delete_after_undo,
        })
        raw.setdefault("appearance", {})
        raw["appearance"].update({
            "font_size": self.font_size,
            "motion": self.motion,
            "density": self.density,
        })
        raw.setdefault("logging", {})
        raw["logging"]["dir"] = self.log_dir
        raw["logging"]["keep_days"] = self.keep_days
        raw.setdefault("ui", {})
        raw["ui"]["last_page"] = self.last_page
        raw["ui"]["window"] = {"width": self.window_size[0], "height": self.window_size[1]}
        raw["zones"] = _deep_copy(self.raw.get("zones") or _default_zones())
        return raw

    def save(self, backup: bool = True) -> None:
        if backup and self.path.exists():
            try:
                backups = paths.backups_dir()
                stamp = time.strftime("%Y%m%d-%H%M%S")
                shutil.copy2(self.path, backups / f"config-{stamp}.json")
                files = sorted(backups.glob("config-*.json"))
                for old in files[:-10]:
                    old.unlink(missing_ok=True)
            except OSError:
                pass
        data = self.to_raw()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        self.raw = data


# ============================================================
# 加载
# ============================================================

def _placeholders(cfg: dict[str, Any]) -> dict[str, str]:
    storage = cfg.get("storage", {})
    link_root = _norm(storage.get("link_root", "")) or _default_link_root()
    archive_root = _norm(storage.get("archive_root", "")) or _default_archive_root()
    ph = dict(_BASE_PLACEHOLDERS)
    ph["{LINK_ROOT}"] = link_root
    ph["{TARGET_BASE}"] = link_root
    ph["{TARGET_DRIVE}"] = (link_root[:2] if _is_abs(link_root) else "D:")
    ph["{ARCHIVE_ROOT}"] = archive_root
    return ph


def _resolve_zones(raw: dict[str, Any], ph: dict[str, str]) -> dict[str, dict[str, Any]]:
    zones: dict[str, dict[str, Any]] = {}
    for key, zone in (raw.get("zones") or {}).items():
        if not isinstance(zone, dict):
            continue
        resolved = _deep_copy(zone)
        resolved["source"] = _norm(expand_path(str(zone.get("source", "")), ph))
        resolved["dest_base"] = _norm(expand_path(str(zone.get("dest_base", "")), ph))
        zones[key] = resolved
    return zones


def load_config(path: str | Path | None = None, *, create: bool = True) -> Config:
    cfg_path = Path(path) if path else paths.config_path()
    # 安装版 / 便携版首次运行：如果程序目录旁边有 v1 的 config.json，先继承过来
    if not cfg_path.exists():
        legacy = paths.executable_dir() / "config.json"
        try:
            if (legacy.exists() and legacy.resolve() != cfg_path.resolve()):
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy, cfg_path)
        except OSError:
            pass
    raw: dict[str, Any]
    if cfg_path.exists():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("配置根节点不是对象")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            broken = cfg_path.with_name(cfg_path.name + f".broken-{int(time.time())}")
            try:
                cfg_path.replace(broken)
            except OSError:
                pass
            raw = _default_config()
            raw.setdefault("_load_warning", f"配置损坏，已重置：{exc}")
    else:
        raw = _default_config()
        if create:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    upgraded = _upgrade(raw)
    # 旧默认名 CDriveArchive 容易误解为“只归档 C 盘数据”；
    # 新名 ColdStore 与源盘无关。旧目录不存在时自动换成新默认。
    storage_up = upgraded.setdefault("storage", {})
    old_archive = _norm(storage_up.get("archive_root", ""))
    if old_archive and os.path.basename(old_archive).casefold() == "cdrivearchive" \
            and not os.path.exists(old_archive):
        storage_up["archive_root"] = os.path.join(
            os.path.dirname(old_archive), "ColdStore")
    ph = _placeholders(upgraded)
    zones = _resolve_zones(upgraded, ph)
    storage = upgraded.get("storage", {})
    safety = upgraded.get("safety", {})
    appearance = upgraded.get("appearance", {})
    logging_cfg = upgraded.get("logging", {})
    ui = upgraded.get("ui", {})
    win = ui.get("window", {}) if isinstance(ui.get("window"), dict) else {}
    warnings: list[str] = []
    if raw.get("_load_warning"):
        warnings.append(str(raw["_load_warning"]))

    link_root = ph["{LINK_ROOT}"]
    archive_root = ph["{ARCHIVE_ROOT}"]
    if not _is_abs(link_root):
        warnings.append("迁移根路径不是绝对路径，已回退到 D:\\_CDrive")
        link_root = r"D:\_CDrive"
    if not _is_abs(archive_root):
        warnings.append("归档根路径不是绝对路径，已回退到 E:\\ColdStore")
        archive_root = r"E:\ColdStore"

    try:
        font_size = max(14, min(20, int(appearance.get("font_size", 14) or 14)))
    except (TypeError, ValueError):
        font_size = 14
    try:
        width = max(1080, min(2560, int(win.get("width", 1280) or 1280)))
        height = max(700, min(1600, int(win.get("height", 820) or 820)))
    except (TypeError, ValueError):
        width, height = 1280, 820

    return Config(
        raw=upgraded,
        path=cfg_path,
        link_root=link_root,
        archive_root=archive_root,
        threshold_mb=int(storage.get("threshold_mb", 100) or 100),
        archive_min_mb=int(storage.get("archive_min_mb", 200) or 200),
        temp_retention_days=int(storage.get("temp_retention_days", 1) or 1),
        default_mode=str(storage.get("default_mode") or MODE_MOVE),
        strict_verify=bool(safety.get("strict_verify", False)),
        check_locks=bool(safety.get("check_locks", True)),
        confirm_high_risk=bool(safety.get("confirm_high_risk", True)),
        delete_after_undo=bool(safety.get("delete_after_undo", True)),
        font_size=font_size,
        motion=bool(appearance.get("motion", True)),
        density=str(appearance.get("density") or "cozy"),
        log_dir=str(logging_cfg.get("dir") or ""),
        keep_days=int(logging_cfg.get("keep_days", 30) or 30),
        last_page=str(ui.get("last_page") or "dashboard"),
        window_size=(width, height),
        zones=zones,
        warnings=warnings,
    )


def default_config_dict() -> dict[str, Any]:
    return _default_config()
