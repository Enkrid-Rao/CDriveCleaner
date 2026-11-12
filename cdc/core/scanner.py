"""磁盘扫描与冷数据分析。

两个入口：
- ``scan_zones``     C 盘可迁移目录 + 已存在链接 + 受保护目录
- ``analyze_cold``   按 IO 特征给冷数据候选分级（机械盘归档用）

两者都不修改文件系统，只读。
"""

from __future__ import annotations

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterable

from . import windows
from .models import (
    AnalysisResult, ArchiveCandidate, JunctionInfo, Progress, ScanItem, ScanResult,
    TIER_OPTIONAL, TIER_RECOMMEND, TIER_SKIP, TIER_STRONG, human_bytes,
)
from .safety import is_protected_path

ProgressCb = Callable[[Progress], None] | None
CancelCb = Callable[[], bool] | None

_ES_CANDIDATES = [
    r"D:\Program Files\Everything\es.exe",
    r"C:\Program Files\Everything\es.exe",
    r"C:\Program Files (x86)\Everything\es.exe",
]

# Windows 自带的兼容性链接（Application Data / Cookies / 「开始」菜单 …）
# 它们不是用户迁移出来的，展示在链接管理里只会造成噪音。
SYSTEM_LINK_NAMES = {
    "application data", "local settings", "cookies", "history", "my documents",
    "recent", "sendto", "templates", "桌面", "desktop", "documents",
    "「开始」菜单", "开始菜单", "start menu", "favorites",
}


def find_everything() -> str:
    found = shutil.which("es.exe") or shutil.which("es")
    if found:
        return found
    for candidate in _ES_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate
    return ""


_ES_PATH = find_everything()
# Everything 索引可能不完整（未索引的盘 / 过期索引），默认用原生扫描保证准确；
# 需要速度的用户可设置 CDC_SIZE_BACKEND=everything。
_USE_ES = os.environ.get("CDC_SIZE_BACKEND", "native").strip().lower() == "everything"


def _size_es(path: str) -> int | None:
    if not _ES_PATH or not _USE_ES:
        return None
    try:
        import subprocess
        result = subprocess.run(
            [_ES_PATH, "-path", path, "-size", "/a-d", "-no-header",
             "-no-digit-grouping"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, creationflags=windows.NO_WINDOW,
        )
    except Exception:
        return None
    if result.returncode not in (0, 1):
        return None
    total = 0
    parsed = 0
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            total += int(parts[0])
            parsed += 1
    # 没有结果不代表空目录（可能是索引缺失），交给原生扫描
    if parsed == 0:
        return None
    return total


def _measure(path: str, cancel: CancelCb = None) -> windows.DirStats:
    size = _size_es(path)
    if size is not None:
        return windows.DirStats(bytes=size)
    return windows.directory_stats(path, cancel=cancel, collect_ext=False)


def _measure_many(paths: list[str], cancel: CancelCb = None,
                  workers: int = 6) -> dict[str, windows.DirStats]:
    if not paths:
        return {}
    out: dict[str, windows.DirStats] = {}
    unique = list(dict.fromkeys(paths))
    if len(unique) == 1:
        return {unique[0]: _measure(unique[0], cancel)}
    with ThreadPoolExecutor(max_workers=min(workers, len(unique))) as pool:
        futures = {pool.submit(_measure, path, cancel): path for path in unique}
        for future in as_completed(futures):
            path = futures[future]
            try:
                out[path] = future.result()
            except Exception:
                out[path] = windows.DirStats()
    return out


def _emit(cb: ProgressCb, **kwargs: Any) -> None:
    if cb:
        try:
            cb(Progress(**kwargs))
        except Exception:
            pass


# ============================================================
# C 盘扫描
# ============================================================

def scan_zones(config: Any, drives: list | None = None,
               progress: ProgressCb = None, cancel: CancelCb = None) -> ScanResult:
    started = time.time()
    result = ScanResult(scanned_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                        backend="everything" if _USE_ES else "native")
    zones = list(config.zones.items())
    tasks: list[tuple[str, str, windows.DirEntryInfo, dict[str, Any]]] = []
    links: list[tuple[str, dict[str, Any], windows.DirEntryInfo]] = []
    protected: list[tuple[str, dict[str, Any], windows.DirEntryInfo, bool]] = []

    total_zones = max(1, len(zones))
    for zi, (zone_key, zone) in enumerate(zones):
        if cancel and cancel():
            break
        source = zone.get("source", "")
        if not source or not os.path.isdir(source):
            result.errors.append(f"区域不存在：{zone_key} {source}")
            continue
        _emit(progress, phase="枚举目录", percent=(zi / total_zones) * 35,
              message=f"读取 {zone.get('label', zone_key)}…",
              detail=source)
        entries = windows.child_directories(source)
        no_go = {str(x).casefold() for x in zone.get("no_go", [])}
        skip_nogo_size = bool(zone.get("skip_nogo_size")) or bool(zone.get("needs_admin"))
        for entry in entries:
            if entry.is_link:
                links.append((zone_key, zone, entry))
            elif entry.name.casefold() in no_go:
                protected.append((zone_key, zone, entry, skip_nogo_size))
            else:
                tasks.append((zone_key, zone, entry, {}))

    # 统一测量：可迁移目录 + 需要显示大小的受保护目录 + 链接目标
    measure_paths: list[str] = [t[2].path for t in tasks]
    measure_paths += [p[2].path for p in protected if not p[3]]
    link_targets: dict[str, str] = {}
    visible_links: list[tuple[str, dict[str, Any], windows.DirEntryInfo]] = []
    for zone_key, zone, entry in links:
        target = windows.junction_target(entry.path)
        if target and not config.is_managed_target(target):
            source = zone.get("source", "")
            system_name = entry.name.casefold() in SYSTEM_LINK_NAMES
            inside = (source and (windows.path_within(target, source)
                                  or windows.path_within(source, target)))
            if system_name or inside:
                continue
        visible_links.append((zone_key, zone, entry))
        link_targets[entry.path] = target
        if target and os.path.isdir(target):
            measure_paths.append(target)
    links = visible_links
    measure_paths = list(dict.fromkeys(measure_paths))
    total_measure = max(1, len(measure_paths))
    measured: dict[str, windows.DirStats] = {}
    done = 0
    # 分批提交，便于实时进度
    batch = 48
    for start in range(0, len(measure_paths), batch):
        if cancel and cancel():
            break
        chunk = measure_paths[start:start + batch]
        chunk_result = _measure_many(chunk, cancel)
        measured.update(chunk_result)
        done += len(chunk)
        _emit(progress, phase="统计大小", percent=35 + (done / total_measure) * 55,
              message=f"已统计 {done}/{len(measure_paths)} 个目录",
              detail=chunk[-1] if chunk else "")

    for zone_key, zone, entry, _extra in tasks:
        stats = measured.get(entry.path) or windows.DirStats()
        size_bytes = stats.bytes
        if size_bytes < config.threshold_bytes:
            continue
        result.items.append(ScanItem(
            name=entry.name,
            path=entry.path,
            size_bytes=size_bytes,
            zone_key=zone_key,
            zone_label=str(zone.get("label", zone_key)),
            dest_path=os.path.join(zone.get("dest_base", ""), entry.name),
            needs_admin=bool(zone.get("needs_admin")),
            file_count=stats.files,
            newest_ts=stats.newest,
        ))

    for zone_key, zone, entry, skip in protected:
        stats = windows.DirStats() if skip else (measured.get(entry.path) or windows.DirStats())
        result.protected_items.append(ScanItem(
            name=entry.name, path=entry.path, size_bytes=stats.bytes,
            zone_key=zone_key, zone_label=str(zone.get("label", zone_key)),
            dest_path="", needs_admin=bool(zone.get("needs_admin")),
            file_count=stats.files, newest_ts=stats.newest,
            protected=True, protected_reason="受保护目录",
        ))

    for zone_key, zone, entry in links:
        target = link_targets.get(entry.path, "")
        stats = measured.get(target) if target else None
        drive_letter = windows.drive_of(target)
        drive = windows.get_drive(drive_letter, drives) if drive_letter else None
        target_exists = bool(target) and os.path.isdir(target)
        origin = {}
        if target_exists:
            origin = windows.read_json(os.path.join(target, ".cdc-origin.json"), {}) or {}
        mine = bool(target) and (
            config.is_managed_target(target)
            or (origin.get("app") == "CDriveCleaner"
                and os.path.normcase(origin.get("source", "")) ==
                os.path.normcase(entry.path))
        )
        result.junctions.append(JunctionInfo(
            name=entry.name,
            path=entry.path,
            target=target,
            zone_key=zone_key,
            zone_label=str(zone.get("label", zone_key)),
            size_bytes=(stats.bytes if stats else 0),
            file_count=(stats.files if stats else 0),
            needs_admin=bool(zone.get("needs_admin")),
            target_exists=target_exists,
            target_on_usb=bool(drive and drive.is_usb),
            target_drive=drive_letter,
            mine=mine,
            broken=not target_exists,
            origin=origin,
        ))

    for item in result.items:
        protected_flag, reason = is_protected_path(item.path, config)
        if protected_flag:
            item.protected = True
            item.protected_reason = reason

    result.items.sort(key=lambda x: x.size_bytes, reverse=True)
    result.junctions.sort(key=lambda x: x.size_bytes, reverse=True)
    result.protected_items.sort(key=lambda x: x.size_bytes, reverse=True)
    result.potential_bytes = sum(i.size_bytes for i in result.items if not i.protected)
    result.released_bytes = sum(j.size_bytes for j in result.junctions)
    _emit(progress, phase="统计临时文件", percent=93, message="统计 Temp 占用…")
    result.temp_bytes = windows.directory_size(
        os.environ.get("TEMP", os.path.join(os.environ.get("USERPROFILE", ""),
                                           "AppData", "Local", "Temp")),
        cancel=cancel,
    )
    result.duration_s = round(time.time() - started, 2)
    _emit(progress, phase="完成", percent=100,
          message=f"扫描完成：{len(result.items)} 个可迁移目录",
          detail=f"耗时 {result.duration_s:.1f}s")
    return result


# ============================================================
# 冷数据分析
# ============================================================

SKIP_DIR_NAMES = {
    "appdata", "application data", "local settings", "$recycle.bin",
    "system volume information", "recovery", "perflogs", "windows", "windowsapps",
    "program files", "program files (x86)", "programdata", "config.msi",
    "package cache", "wpsystem", "temp", "cache", "caches", "onedrivetemp",
    "node_modules", ".git", ".svn", ".hg", ".cache", ".npm", ".gradle", ".m2",
    ".nuget", ".cargo", ".rustup", ".conda", "pkgs", "site-packages",
    "intelgraphicsprofiles", "microsoftedgebackups", "contacts", "favorites",
    "links", "saved games", "searches", "3d objects", "nethood", "printhood",
    "recent", "sendto", "templates", "cookies", "history", "onedrive",
    "documents and settings", "desktop", "workbuddy ai",
}
SKIP_IF_SMALL = {
    "downloads": 1024 ** 3,
    "videos": 1024 ** 3,
    "pictures": 2 * 1024 ** 3,
    "music": 1024 ** 3,
    "documents": 2 * 1024 ** 3,
}
CHAT_NAMES = {"xwechat", "xwechat_files", "tencent files", "wechat files",
              "wechat", "qq", "qqnt", "telegram desktop", "dingtalk"}
CODE_NAMES = {"projects", "repos", "repositories", "workspace", "workspaces",
              "src", "source", "code", "developer", "git"}


def default_archive_roots(config: Any) -> list[tuple[str, str]]:
    """返回 (路径, 显示名) 列表，默认 C 用户目录 + D 盘根。"""
    roots: list[tuple[str, str]] = []
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    if os.path.isdir(home):
        roots.append((home, "用户目录"))
    d_root = "D:\\"
    if os.path.isdir(d_root) and not os.path.normcase(d_root).startswith(os.path.normcase(home)):
        roots.append((d_root, "D 盘"))
    return roots


def _is_excluded_candidate(path: str, name: str, config: Any,
                           roots: list[str]) -> bool:
    lower = name.casefold()
    if lower in SKIP_DIR_NAMES:
        return True
    if windows.is_link(path):
        return True
    protected, _reason = is_protected_path(path, config)
    if protected:
        return True
    for special in (config.link_root, config.archive_root):
        if special and windows.path_within(path, special):
            return True
    # 自身就是扫描根时不作为候选
    for root in roots:
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(root)):
            return True
    return False


def _candidate_stats(path: str, cancel: CancelCb) -> windows.DirStats:
    return windows.directory_stats(path, cancel=cancel, collect_ext=True)


def classify_cold(name: str, stats: windows.DirStats, *,
                  size_min_bytes: int, source_drive: str = "C") -> tuple[str, int, str, list[str]]:
    """根据扩展名构成 / 文件年龄给冷数据分级。返回 (tier, score, reason, warnings)。"""
    size = stats.bytes
    if size <= 0:
        return TIER_SKIP, 0, "空目录或无法读取", []
    if size < size_min_bytes:
        return TIER_SKIP, 0, f"小于 {human_bytes(size_min_bytes, precision=0)}", []
    total = sum(stats.ext_bytes.values()) or 1
    ratios = {k: v / total for k, v in stats.ext_bytes.items()}
    lower = name.casefold()
    warnings: list[str] = []
    age_days = int((time.time() - stats.newest) / 86400) if stats.newest else 0

    if any(chat in lower for chat in CHAT_NAMES):
        return (TIER_SKIP, 10, "聊天/数据库目录：高频随机读写，机械盘会明显变慢", [])

    if lower in (".android", "android", "avd", ".emulator"):
        return (TIER_OPTIONAL, 45,
                "Android 模拟器 / 镜像目录：不跑模拟器时是冷数据，运行时随机 IO 很多",
                ["运行模拟器前请先回迁或确保机械盘在线"])

    if any(name in lower for name in (
            "google", "microsoft", "adobe", "jetbrains", "chrome", "edge",
            "firefox", "tencent", "wechat", "weixin", "code", "discord",
            "spotify", "steam", "battle.net", "epicgames", "nvidia",
            "openharmony", "huawei", "miktex", "bionic", "blackmagic")):
        return (TIER_SKIP, 22,
                "应用数据 / 程序目录：属于高频随机读写，适合留在 SSD", [])

    avg_file = size / max(1, stats.files)
    if stats.files > 4000 and avg_file < 256 * 1024 and ratios.get("code", 0) + ratios.get("other", 0) > 0.45:
        return (TIER_SKIP, 20, f"小文件很多（{stats.files:,} 个，平均 {human_bytes(avg_file)}），机械盘随机 IO 慢", [])
    if lower in CODE_NAMES or ratios.get("code", 0) > 0.55:
        return (TIER_SKIP, 25, "代码/版本库目录：小文件随机读写多，不建议放机械盘", [])
    if any(x in lower for x in ("node_modules", ".git", ".venv", "venv")):
        return (TIER_SKIP, 15, "开发依赖目录：文件碎、可重建", [])

    if ratios.get("video", 0) >= 0.55 and size >= 1024 ** 3:
        return (TIER_STRONG, 94, "视频为主，顺序读取，机械盘非常适合", [])
    if ratios.get("iso", 0) >= 0.40 and size >= 700 * 1024 ** 2:
        return (TIER_STRONG, 92, "镜像/虚拟磁盘，读一次就归档", [])
    if ratios.get("installer", 0) >= 0.50 and size >= 500 * 1024 ** 2:
        return (TIER_STRONG, 88, "安装包/应用包，装完即弃", [])
    if ratios.get("model", 0) >= 0.50 and size >= 2 * 1024 ** 3:
        return (TIER_RECOMMEND, 86, "模型权重文件，读取以顺序大块为主", [])
    if ratios.get("archive", 0) >= 0.55 and size >= 1024 ** 3:
        return (TIER_RECOMMEND, 82, "压缩包/归档文件，适合冷存储", [])
    if ratios.get("image", 0) >= 0.55 and size >= 2 * 1024 ** 3:
        return (TIER_RECOMMEND, 78, "图片素材为主，适合机械盘", [])
    if lower in ("downloads", "download", "下载") and size >= SKIP_IF_SMALL["downloads"]:
        return (TIER_RECOMMEND, 84, "下载缓冲目录：消耗品多，归档后可随时回看", ["移动后下载器需要重新指定保存位置"] if lower else [])
    if age_days >= 180 and size >= 2 * 1024 ** 3 and ratios.get("video", 0) + ratios.get("archive", 0) + ratios.get("image", 0) + ratios.get("document", 0) >= 0.45:
        return (TIER_RECOMMEND, 76, f"最近 {age_days} 天没有修改，属于冷数据", [])
    if any(x in lower for x in ("backup", "backups", "备份", "archive", "归档")) and size >= 1024 ** 3:
        return (TIER_RECOMMEND, 80, "备份/归档目录，适合冷存储", [])
    if ratios.get("document", 0) >= 0.60 and size >= 3 * 1024 ** 3:
        return (TIER_RECOMMEND, 72, "文档资料为主，读取频率低", [])
    if size >= 5 * 1024 ** 3 and ratios.get("video", 0) + ratios.get("archive", 0) + ratios.get("iso", 0) >= 0.35:
        return (TIER_OPTIONAL, 58, "体积较大，含部分冷数据；建议人工确认", [])
    if size >= 10 * 1024 ** 3:
        return (TIER_OPTIONAL, 48, "体积很大但构成混合，建议打开确认后再归档", [])
    return (TIER_SKIP, 30, "活跃数据或体积不足，暂不建议归档", [])


def analyze_cold(
    config: Any,
    roots: Iterable[tuple[str, str]] | None = None,
    *,
    drives: list | None = None,
    progress: ProgressCb = None,
    cancel: CancelCb = None,
    min_size_bytes: int | None = None,
) -> AnalysisResult:
    started = time.time()
    root_list = list(roots) if roots else default_archive_roots(config)
    min_size = min_size_bytes if min_size_bytes is not None else config.archive_min_bytes
    result = AnalysisResult(scanned_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                            roots=[r[0] for r in root_list])

    candidates: list[tuple[str, str, windows.DirEntryInfo]] = []
    for root, _label in root_list:
        if not os.path.isdir(root):
            result.errors.append(f"目录不存在：{root}")
            continue
        for entry in windows.child_directories(root):
            if entry.is_link:
                continue
            if _is_excluded_candidate(entry.path, entry.name, config,
                                      [r[0] for r in root_list]):
                continue
            candidates.append((root, _label, entry))

    total = max(1, len(candidates))
    _emit(progress, phase="枚举候选", percent=5,
          message=f"发现 {len(candidates)} 个目录，开始统计…")
    stats_map: dict[str, windows.DirStats] = {}
    batch = 12
    for start in range(0, len(candidates), batch):
        if cancel and cancel():
            break
        chunk = candidates[start:start + batch]
        with ThreadPoolExecutor(max_workers=min(6, len(chunk))) as pool:
            futures = {pool.submit(_candidate_stats, entry.path, cancel): entry
                       for _root, _label, entry in chunk}
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    stats_map[entry.path] = future.result()
                except Exception as exc:
                    stats_map[entry.path] = windows.DirStats(errors=[str(exc)])
        done = min(len(candidates), start + batch)
        _emit(progress, phase="统计冷数据", percent=5 + done / total * 85,
              message=f"已分析 {done}/{len(candidates)} 个目录",
              detail=chunk[-1][2].name if chunk else "")

    for root, label, entry in candidates:
        stats = stats_map.get(entry.path) or windows.DirStats()
        drive = windows.drive_of(entry.path)
        tier, score, reason, warnings = classify_cold(
            entry.name, stats, size_min_bytes=min_size, source_drive=drive)
        if tier == TIER_SKIP and stats.bytes < min_size:
            continue
        # 目标路径：archive_root\C\Users\me\Downloads
        try:
            drive_root = drive + ":\\"
            rel = os.path.relpath(entry.path, drive_root)
            if rel.startswith(".."):
                rel = entry.name
        except (ValueError, OSError):
            rel = entry.name
        dest = os.path.join(config.archive_root, drive, rel)
        cand = ArchiveCandidate(
            name=entry.name,
            path=entry.path,
            size_bytes=stats.bytes,
            file_count=stats.files,
            newest_ts=stats.newest,
            oldest_ts=stats.oldest,
            ext_bytes=dict(stats.ext_bytes),
            tier=tier,
            score=score,
            reason=reason,
            dest_path=dest,
            source_drive=drive,
            warnings=warnings,
            source_root=root,
        )
        if stats.errors:
            cand.warnings.append(f"{len(stats.errors)} 个文件无法读取（可能被占用）")
        result.candidates.append(cand)

    # ---- 已通过 Junction 迁到其他盘的目录：可再次归档到机械盘并更新链接 ----
    _emit(progress, phase="检查已迁移目录", percent=92,
          message="检查已迁移到其他盘的冷数据…")
    linked_rows: list[tuple[str, str, windows.DirEntryInfo, str, dict[str, Any]]] = []
    for zone_key, zone in config.zones.items():
        # 冷数据只从「用户主目录 / D 盘根」这类内容目录找；
        # AppData、Program Files 里的链接属于应用数据，不适合按冷数据归档。
        if zone_key != "userhome":
            continue
        source = zone.get("source", "")
        if not source or not os.path.isdir(source):
            continue
        for entry in windows.child_directories(source):
            if not entry.is_link:
                continue
            if entry.name.casefold() in SYSTEM_LINK_NAMES:
                continue
            target = windows.junction_target(entry.path)
            if not target or not os.path.isdir(target):
                continue
            if not config.is_managed_target(target):
                continue
            linked_rows.append((zone_key, zone.get("label", zone_key), entry,
                                target, zone))

    linked_stats: dict[str, windows.DirStats] = {}
    batch = 10
    for start in range(0, len(linked_rows), batch):
        if cancel and cancel():
            break
        chunk = linked_rows[start:start + batch]
        with ThreadPoolExecutor(max_workers=min(5, len(chunk))) as pool:
            futures = {pool.submit(_candidate_stats, row[3], cancel): row
                       for row in chunk}
            for future in as_completed(futures):
                row = futures[future]
                try:
                    linked_stats[row[0] + "|" + row[2].path] = future.result()
                except Exception:
                    linked_stats[row[0] + "|" + row[2].path] = windows.DirStats()

    for zone_key, zone_label, entry, target, zone in linked_rows:
        stats = linked_stats.get(zone_key + "|" + entry.path) or windows.DirStats()
        drive = windows.drive_of(entry.path)
        tier, score, reason, warnings = classify_cold(
            entry.name, stats, size_min_bytes=min_size, source_drive=drive)
        if tier == TIER_SKIP and stats.bytes < min_size:
            continue
        try:
            rel = os.path.relpath(entry.path, drive + ":\\")
            if rel.startswith(".."):
                rel = entry.name
        except (ValueError, OSError):
            rel = entry.name
        dest = os.path.join(config.archive_root, drive, rel)
        cand = ArchiveCandidate(
            name=entry.name,
            path=entry.path,
            size_bytes=stats.bytes,
            file_count=stats.files,
            newest_ts=stats.newest,
            oldest_ts=stats.oldest,
            ext_bytes=dict(stats.ext_bytes),
            tier=tier,
            score=max(0, score - 2),
            reason=reason + " · 已通过 Junction 存放在其他盘，归档后会更新链接",
            dest_path=dest,
            source_drive=drive,
            is_junction=True,
            needs_admin=bool(zone.get("needs_admin")),
            target_path=target,
            warnings=list(warnings) + [
                "源路径是 Junction：归档保留原路径，并把链接改指到机械盘"],
            source_root=zone.get("source", ""),
        )
        if stats.errors:
            cand.warnings.append(f"{len(stats.errors)} 个文件无法读取（可能被占用）")
        result.candidates.append(cand)

    order = {TIER_STRONG: 0, TIER_RECOMMEND: 1, TIER_OPTIONAL: 2, TIER_SKIP: 3}
    result.candidates.sort(key=lambda c: (order.get(c.tier, 9), -c.size_bytes))
    result.total_recommended_bytes = sum(
        c.size_bytes for c in result.candidates if c.tier in (TIER_STRONG, TIER_RECOMMEND))
    result.duration_s = round(time.time() - started, 2)
    _emit(progress, phase="完成", percent=100,
          message=f"分析完成：{len([c for c in result.candidates if c.tier in (TIER_STRONG, TIER_RECOMMEND)])} 个推荐归档",
          detail=f"耗时 {result.duration_s:.1f}s")
    return result
