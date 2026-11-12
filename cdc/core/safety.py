"""安全红线：路径保护、空间预检、文件锁、目标目录占用标记。

所有会删除数据的操作都必须先通过这里的 preflight。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

from . import windows
from .models import (
    MODE_COPY, MODE_LINK, MODE_MOVE, OperationItem, PreflightResult,
)

MARKER_NAME = ".cdc-origin.json"
MIN_FREE_MARGIN = 512 * 1024 * 1024  # 删除/复制前额外留 512MB

# 任何情况下都不作为源目录的路径组件
PROTECTED_COMPONENTS = {
    "$recycle.bin", "system volume information", "recovery", "boot", "efi",
    "windows", "winsxs", "system32", "syswow64", "windowsapps", "wpSystem".lower(),
    "driverstore", "assembly", "servicing", "installer",
}
PROTECTED_LEAF_NAMES = {
    "ntuser.dat", "ntuser.dat.log1", "ntuser.dat.log2", "ntuser.ini",
    "pagefile.sys", "hiberfil.sys", "swapfile.sys", "bootmgr", "bcd",
    ".ssh", ".gnupg", "node_modules", ".git", ".svn",
}
SYSTEM_ROOT_VARS = ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)",
                    "ProgramData", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "TEMP", "TMP")


def _canon(path: str) -> str:
    try:
        return os.path.normcase(os.path.abspath(path)).rstrip("\\/")
    except (ValueError, OSError):
        return ""


def _same_or_child(child: str, parent: str) -> bool:
    return windows.path_within(child, parent)


def _system_protected_roots(config: Any = None) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for var in SYSTEM_ROOT_VARS:
        value = os.environ.get(var, "")
        if value and os.path.isabs(value):
            rows.append((_canon(value), f"系统目录 {value}"))
    if config is not None:
        rows.append((_canon(config.link_root), "迁移容器根目录"))
        rows.append((_canon(config.archive_root), "归档根目录"))
        try:
            from .. import paths
            rows.append((_canon(str(paths.data_dir())), "程序数据目录"))
        except Exception:
            pass
    return [(p, label) for p, label in rows if p]


def is_protected_path(path: str, config: Any = None,
                      *, allow_system_child: bool = True) -> tuple[bool, str]:
    """判断路径是否触碰系统/工具红线。

    ``allow_system_child=True`` 允许 System32 等目录的**子目录**（用于撤销迁移时
    恢复 Program Files 项目），但目录本身永远不行。
    """
    if not path:
        return True, "空路径"
    if not os.path.isabs(path):
        return True, "不是绝对路径"
    if path.startswith("\\\\"):
        return True, "暂不支持网络路径"
    if windows.is_drive_root(path):
        return True, "不能操作磁盘根目录"
    path_n = _canon(path)
    if len(path_n) <= 3:
        return True, "路径过短"

    for root, label in _system_protected_roots(config):
        if path_n == root:
            return True, f"这是{label}本身"
        if _same_or_child(path_n, root) and not allow_system_child:
            return True, f"位于{label}内"

    parts = [p.casefold() for p in path_n.split(os.sep) if p]
    leaf = parts[-1] if parts else ""
    if leaf in PROTECTED_LEAF_NAMES:
        return True, f"受保护的文件/目录：{leaf}"
    # 盘根下的系统目录（$Recycle.Bin / System Volume Information 等）
    if len(parts) >= 2 and parts[1] in {"$recycle.bin", "system volume information", "recovery"}:
        return True, "系统保留目录"
    # Windows / WindowsApps 等永远不作为源
    if len(parts) >= 2 and parts[1] == "windows":
        return True, "Windows 系统目录"
    if "windowsapps" in parts or "wpsystem" in parts:
        return True, "系统应用受保护目录"
    return False, ""


def check_zone_no_go(path: str, config: Any) -> tuple[bool, str]:
    zone = config.zone_for_path(path)
    if not zone:
        return False, ""
    name = os.path.basename(path.rstrip("\\/"))
    no_go = {str(x).casefold() for x in zone.get("no_go", [])}
    if name.casefold() in no_go:
        return True, f"该目录在「{zone.get('label', zone.get('key', ''))}」的受保护清单中"
    return False, ""


def read_origin(dest: str) -> dict[str, Any]:
    return windows.read_json(os.path.join(dest, MARKER_NAME), {}) or {}


def write_origin(dest: str, source: str, *, action: str, mode: str,
                 op_id: str, size_bytes: int) -> None:
    data = {
        "schema": 1,
        "source": os.path.abspath(source),
        "action": action,
        "mode": mode,
        "operation_id": op_id,
        "size_bytes": int(size_bytes),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "app": "CDriveCleaner",
    }
    windows.write_json_atomic(os.path.join(dest, MARKER_NAME), data)
    windows.set_file_hidden(os.path.join(dest, MARKER_NAME))


def origin_conflict(dest: str, source: str) -> str:
    """目标目录被占用时返回冲突说明；空目录 / 同源续传返回空字符串。"""
    if not os.path.lexists(dest):
        return ""
    if not os.path.isdir(dest):
        return "目标路径已存在且不是目录"
    try:
        entries = list(os.scandir(dest))
    except OSError as exc:
        return f"无法读取目标目录：{exc}"
    if not entries:
        return ""
    origin = read_origin(dest)
    if not origin:
        return "目标目录已有内容，且不是本工具创建的（缺少来源标记）"
    if _canon(origin.get("source", "")) != _canon(source):
        return f"目标目录属于另一个源目录：{origin.get('source')}"
    return ""


def _size_of(item: OperationItem) -> int:
    if item.size_bytes > 0:
        return item.size_bytes
    target = item.source
    if windows.is_link(item.source):
        target = windows.junction_target(item.source)
    if os.path.isdir(target) and not windows.is_link(target):
        try:
            return windows.directory_stats(target, collect_ext=False).bytes
        except Exception:
            return 0
    return 0


def _lock_rows(item: OperationItem, target: str, config: Any) -> list[dict[str, Any]]:
    if not config.check_locks:
        return []
    paths = []
    if os.path.isdir(target) and not windows.is_link(target):
        paths.append(target)
    source = item.source
    if windows.is_link(source):
        source = windows.junction_target(source)
    if os.path.isdir(source) and not windows.is_link(source):
        paths.append(source)
    rows: dict[int, dict[str, Any]] = {}
    for path in dict.fromkeys(paths):
        for row in windows.processes_using(path):
            rows[int(row.get("pid") or 0)] = row
    return [r for r in rows.values() if r.get("pid")]


def _space_check(dest_free: int, needed: int, label: str, result: PreflightResult) -> None:
    margin = max(MIN_FREE_MARGIN, int(needed * 0.03))
    if dest_free < needed + margin:
        result.add_error(
            f"{label}可用空间不足：需要约 {needed / 1024**3:.1f} GB + 余量，"
            f"当前仅 {dest_free / 1024**3:.1f} GB"
        )


def _locks_to_errors(rows: list[dict[str, Any]], result: PreflightResult) -> None:
    if not rows:
        return
    names = "、".join(f"{r.get('name') or '未知进程'}({r.get('pid')})" for r in rows[:5])
    result.locked_processes = rows
    result.add_error(f"目标正在被使用：{names}。请先关闭相关程序。")


# ============================================================
# 迁移预检
# ============================================================

def preflight_migrate(item: OperationItem, config: Any,
                      drives: list | None = None) -> PreflightResult:
    result = PreflightResult()
    src = os.path.abspath(item.source)
    dst = os.path.abspath(item.dest)
    result.requires_admin = bool(item.needs_admin)

    if not os.path.isdir(src):
        result.add_error("源目录不存在或不是目录")
        return result
    if windows.is_link(src):
        result.add_error("源目录已经是链接（可能已迁移）")
        return result
    protected, reason = is_protected_path(src, config)
    if protected:
        result.add_error(f"源目录受保护：{reason}")
    no_go, reason = check_zone_no_go(src, config)
    if no_go:
        result.add_error(reason)
    if not os.path.isabs(dst):
        result.add_error("目标路径不是绝对路径")
    if _same_or_child(dst, src) or _same_or_child(src, dst):
        result.add_error("源目录与目标目录互相包含")
    if _canon(dst) == _canon(src):
        result.add_error("源目录与目标目录相同")
    src_drive = windows.drive_of(src)
    dst_drive = windows.drive_of(dst)
    if not dst_drive:
        result.add_error("无法识别目标盘符")
    if src_drive and dst_drive and src_drive == dst_drive:
        result.add_error("源目录与目标目录在同一分区，迁移没有意义")
    if not os.path.isdir(os.path.dirname(dst)):
        # 允许自动创建，但盘符必须存在
        if not os.path.exists(dst_drive + ":\\"):
            result.add_error("目标盘不存在或未连接")

    size = _size_of(item)
    result.size_bytes = size
    free = windows.free_bytes(dst)
    result.dest_free_bytes = free
    _space_check(free, size, "目标盘", result)

    conflict = origin_conflict(dst, src)
    if conflict:
        result.add_error(conflict)
    if config.check_locks:
        rows = _lock_rows(item, src, config)
        _locks_to_errors(rows, result)

    if src_drive and dst_drive and src_drive != "C" and config.link_root:
        # 允许非 C 源，但 UI 只展示 C 盘；这里给警告
        result.warnings.append("源目录不在 C 盘，释放的是该分区空间")
    if dst_drive and src_drive and src_drive != dst_drive:
        try:
            src_drive_info = windows.get_drive(src_drive, drives)
            dst_drive_info = windows.get_drive(dst_drive, drives)
            if (src_drive_info and dst_drive_info and
                    src_drive_info.disk_number is not None and
                    src_drive_info.disk_number == dst_drive_info.disk_number):
                result.warnings.append("C 与目标分区位于同一块物理盘：只释放分区空间，不增加物理盘总容量")
        except Exception:
            pass
    return result


# ============================================================
# 归档预检
# ============================================================

def preflight_archive(item: OperationItem, config: Any,
                      drives: list | None = None) -> PreflightResult:
    result = PreflightResult()
    src = os.path.abspath(item.source)
    dst = os.path.abspath(item.dest)
    mode = item.mode or MODE_MOVE
    result.requires_admin = bool(item.needs_admin)

    if not os.path.isdir(src):
        result.add_error("源目录不存在或不是目录")
        return result
    is_link_source = windows.is_link(src)
    if is_link_source:
        target = windows.junction_target(src)
        if not target or not os.path.isdir(target):
            result.add_error("源目录是链接，但链接目标不存在")
            return result
    protected, reason = is_protected_path(src, config)
    if protected:
        result.add_error(f"源目录受保护：{reason}")
    if not os.path.isabs(dst):
        result.add_error("目标路径不是绝对路径")
    if _same_or_child(dst, src) or _same_or_child(src, dst):
        result.add_error("源目录与目标目录互相包含")
    if is_link_source:
        link_target = windows.junction_target(src)
        if link_target and (_same_or_child(dst, link_target)
                            or _same_or_child(link_target, dst)):
            result.add_error("归档目标与链接的真实目标互相包含")
    if _canon(dst) == _canon(src):
        result.add_error("源目录与目标目录相同")

    src_drive = windows.drive_of(src)
    dst_drive = windows.drive_of(dst)
    if not dst_drive:
        result.add_error("无法识别目标盘符")
    if src_drive and dst_drive and src_drive == dst_drive and mode != MODE_COPY:
        result.add_error("归档目标与源目录在同一分区，移动无法释放空间")
    if dst_drive:
        target_drive = windows.get_drive(dst_drive, drives)
        if target_drive is not None:
            if target_drive.is_system:
                result.add_error("不能把归档目标设为系统盘")
            if target_drive.drive_kind == 4:
                result.add_error("不支持网络路径作为归档目标")
            elif target_drive.is_usb and mode in (MODE_MOVE, MODE_LINK):
                result.warnings.append(
                    "目标是 USB 外置盘：归档后请保持磁盘连接；移动模式下拔盘将无法访问这些数据"
                )
        elif not os.path.exists(dst_drive + ":\\"):
            result.add_error("目标盘不存在或未连接")

    size = _size_of(item)
    result.size_bytes = size
    free = windows.free_bytes(dst)
    result.dest_free_bytes = free
    _space_check(free, size, "归档目标盘", result)
    if is_link_source:
        if mode == MODE_LINK:
            result.warnings.append("源目录是 Junction：归档后会保留原路径，并把链接改指到归档目标")
        elif mode == MODE_MOVE:
            result.warnings.append("源目录是 Junction：移动归档会删除链接与原目标，原路径将不再存在")

    conflict = origin_conflict(dst, src)
    if conflict:
        result.add_error(conflict)
    if mode in (MODE_MOVE, MODE_LINK) and config.check_locks:
        rows = _lock_rows(item, src, config)
        _locks_to_errors(rows, result)
    elif mode == MODE_COPY and config.check_locks:
        rows = _lock_rows(item, src, config)
        if rows:
            result.warnings.append("源目录有程序正在使用；仅复制模式通常不受影响")

    if mode == MODE_LINK:
        result.warnings.append("链接归档会在原位置留下 Junction；拔掉外置盘后该路径不可用")
    return result


# ============================================================
# 撤销 / 回迁预检
# ============================================================

def preflight_undo(item: OperationItem, config: Any,
                   drives: list | None = None) -> PreflightResult:
    result = PreflightResult()
    src = os.path.abspath(item.source)
    result.requires_admin = bool(item.needs_admin)
    if not os.path.lexists(src):
        result.add_error("原路径不存在，无法撤销")
        return result
    if not windows.is_link(src):
        result.add_error("原路径不是目录链接，无法撤销")
        return result
    target = windows.junction_target(src)
    if not target:
        result.add_error("无法读取链接目标")
        return result
    if not os.path.isdir(target):
        result.add_error(f"链接目标不存在：{target}")
        return result
    size = _size_of(item) or windows.directory_stats(target, collect_ext=False).bytes
    result.size_bytes = size
    free = windows.free_bytes(os.path.dirname(src))
    result.source_free_bytes = free
    _space_check(free, size, "C 盘", result)
    protected, reason = is_protected_path(src, config, allow_system_child=True)
    if protected:
        result.add_error(f"原路径受保护：{reason}")
    if config.check_locks:
        rows = _lock_rows(item, target, config)
        _locks_to_errors(rows, result)
    origin = read_origin(target)
    if not origin:
        result.warnings.append("目标目录没有本工具的来源标记：撤销后默认保留目标副本")
    return result


def preflight_link(item: OperationItem, config: Any,
                   drives: list | None = None) -> PreflightResult:
    result = PreflightResult()
    src = os.path.abspath(item.source)
    dst = os.path.abspath(item.dest)
    if not os.path.isdir(dst):
        result.add_error("链接目标不存在")
    if os.path.lexists(src) and not windows.is_link(src):
        result.add_error("原路径存在且不是链接，无法重链")
    if os.path.lexists(src) and windows.is_link(src):
        current = windows.junction_target(src)
        if _canon(current) == _canon(dst):
            result.add_error("链接已经指向该目标，无需修复")
    protected, reason = is_protected_path(src, config, allow_system_child=True)
    if protected:
        result.add_error(f"原路径受保护：{reason}")
    result.requires_admin = bool(item.needs_admin)
    return result


def preflight(item: OperationItem, config: Any,
              drives: list | None = None) -> PreflightResult:
    if item.action == "migrate":
        return preflight_migrate(item, config, drives)
    if item.action == "archive":
        return preflight_archive(item, config, drives)
    if item.action == "undo":
        return preflight_undo(item, config, drives)
    if item.action == "link":
        return preflight_link(item, config, drives)
    result = PreflightResult()
    result.add_error(f"未知操作：{item.action}")
    return result


def lock_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    names = []
    for row in rows[:6]:
        names.append(f"{row.get('name') or '未知'}({row.get('pid')})")
    return "、".join(names)
