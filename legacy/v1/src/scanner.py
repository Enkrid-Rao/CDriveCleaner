"""磁盘扫描逻辑。

扫描 C 盘各区域的大目录、已存在的 Junction、以及受保护的 no-go 目录。

目录大小计算优先使用 Everything 的 CLI（es.exe）：
  - 走 NTFS 索引，单目录查询 0.1~0.3s（PowerShell 递归要 2s+）
  - 未安装 Everything 时自动回退到 PowerShell 递归
"""

from __future__ import annotations

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import config
from .powershell import run_ps

# Everything CLI 的常见位置
_ES_CANDIDATES = [
    r"D:\Program Files\Everything\es.exe",
    r"C:\Program Files\Everything\es.exe",
    r"C:\Program Files (x86)\Everything\es.exe",
]


def _find_es() -> str | None:
    """查找 Everything CLI（es.exe），找不到返回 None。"""
    for p in _ES_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


_ES_PATH = _find_es()
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _dir_size_es(es: str, path: str) -> int | None:
    """用 es.exe 计算目录总大小（字节）。失败返回 None。

    只列文件（/a-d）、禁止千位分隔符（-no-digit-grouping），
    输出形如 "  1234567  C:\\path\\file"，本地求和。
    """
    try:
        r = subprocess.run(
            [es, "-path", path, "-size", "/a-d", "-no-header", "-no-digit-grouping"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180, creationflags=_NO_WINDOW,
        )
    except Exception:
        return None
    if r.returncode not in (0, 1):   # es.exe 无结果时返回 1
        return None
    total = 0
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            total += int(parts[0])
    return total


def _dir_size(path: str) -> int:
    """计算目录大小（字节）。

    后端由 config.SIZE_BACKEND 决定：
      - "auto"（默认）：优先 es.exe（Everything，0.1~0.3s），失败回退 PowerShell
      - "powershell"  ：强制 PowerShell 递归（慢但绝对精确，不依赖 Everything 索引）
    """
    if config.SIZE_BACKEND != "powershell" and _ES_PATH:
        size = _dir_size_es(_ES_PATH, path)
        if size is not None:
            return size
    script = (
        f"$p = '{path}'\n"
        "$s = (Get-ChildItem $p -Recurse -File -Force -ErrorAction SilentlyContinue | "
        "Measure-Object -Property Length -Sum).Sum\n"
        "if ($null -eq $s) { $s = 0 }\n"
        "[long]$s\n"
    )
    stdout, _, _ = run_ps(script, timeout=600)
    try:
        return int(float(stdout.strip()))
    except (ValueError, TypeError):
        return 0


def get_drive_info() -> tuple[float, float, float]:
    """获取 C 盘总容量、C 盘可用、D 盘可用（单位 GB）。"""
    script = """
    $c = [System.IO.DriveInfo]::new('C')
    $d = [System.IO.DriveInfo]::new('D')
    "$([math]::Round($c.TotalSize/1GB,2))|$([math]::Round($c.AvailableFreeSpace/1GB,2))|$([math]::Round($d.AvailableFreeSpace/1GB,2))"
    """
    stdout, _, _ = run_ps(script, timeout=30)
    parts = stdout.split("|")
    if len(parts) == 3:
        try:
            return float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            pass
    return 400.0, 0.0, 0.0


def scan_zone(zone_key: str, threshold_mb: int = 100) -> tuple[list[dict], list[dict], list[dict]]:
    """扫描指定 zone 的大目录。

    返回 (big_dirs, junction_list, no_go_list)。
    - big_dirs: 超过阈值的安全可迁移目录
    - junction_list: 已存在的 Junction（含 source 完整路径）
    - no_go_list: 受保护目录（不迁移，仅展示大小）

    说明：先一次性列举一级目录（-Force 含隐藏目录，如 .lmstudio），
    再用 es.exe 逐个算大小 —— 比原来"PowerShell 一次算完所有目录"快得多。
    """
    zone = config.SCAN_ZONES[zone_key]
    source = zone["source"]
    dest_base = zone["dest_base"]
    no_go = zone["no_go"]
    needs_admin = zone.get("needs_admin", False)

    # admin zone 的 no-go 目录不计算大小直接跳过；
    # 非 admin zone 的 no-go 目录计算大小但标记不可迁移。
    # zone 也可用 "skip_nogo_size": true 显式跳过（如 userhome，其 no_go 含 AppData 等超大目录）。
    skip_nogo_size = needs_admin or zone.get("skip_nogo_size", False)

    # ① 列举一级目录（含隐藏目录）
    list_script = (
        f"$SourcePath = '{source}'\n"
        "Get-ChildItem $SourcePath -Directory -Force -ErrorAction SilentlyContinue | ForEach-Object {\n"
        "  $kind = if ($_.Attributes -match 'ReparsePoint') { 'LINK' } else { 'DIR' }\n"
        "  \"$kind|$($_.Name)|$($_.Target)\"\n"
        "}\n"
    )
    stdout, _, _ = run_ps(list_script, timeout=120)

    entries: list[tuple[str, str, str]] = []
    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 2:
            kind, name = parts[0], parts[1]
            target = parts[2] if len(parts) > 2 else ""
            entries.append((kind, name, target))

    big_dirs: list[dict[str, Any]] = []
    junction_list: list[dict[str, Any]] = []
    no_go_list: list[dict[str, Any]] = []

    # 先筛出需要算大小的目录，并行计算（es.exe 独立子进程，线程池有效）
    todo: list[str] = []
    for kind, name, _target in entries:
        if kind == "LINK":
            continue
        if name in no_go and skip_nogo_size:
            continue
        todo.append(os.path.join(source, name))
    sizes = dict(zip(todo, _dir_size_many(todo)))

    for kind, name, target in entries:
        full = os.path.join(source, name)

        # ① 已是 Junction
        if kind == "LINK":
            junction_list.append({
                "name": name, "target": target,
                "zone": zone_key, "source": full,
            })
            continue

        # ② no_go 目录
        if name in no_go:
            if not skip_nogo_size:
                no_go_list.append({
                    "name": name,
                    "sizeMB": round(sizes.get(full, 0) / 1024 / 1024, 2),
                    "zone": zone_key,
                })
            continue

        # ③ 普通目录：超阈值则列出
        size_mb = sizes.get(full, 0) / 1024 / 1024
        if size_mb >= threshold_mb:
            big_dirs.append({
                "name": name,
                "sizeMB": round(size_mb, 2),
                "path": full,
                "dest": dest_base + "\\" + name,
                "zone": zone_key,
                "needsAdmin": needs_admin,
            })

    big_dirs.sort(key=lambda x: x.get("sizeMB", 0), reverse=True)
    return big_dirs, junction_list, no_go_list


def _dir_size_many(paths: list[str], workers: int = 8) -> list[int]:
    """并行计算多个目录的大小（es.exe 是独立子进程，线程池有效）。"""
    if not paths:
        return []
    if len(paths) == 1:
        return [_dir_size(paths[0])]
    with ThreadPoolExecutor(max_workers=min(workers, len(paths))) as ex:
        return list(ex.map(_dir_size, paths))


def _calc_released_gb(junctions: list[dict]) -> float:
    """计算已释放空间（遍历 Junction 目标目录统计大小）。并行加速。"""
    targets = [j.get("target", "") for j in junctions]
    targets = [t for t in targets if t and os.path.exists(t)]
    if not targets:
        return 0.0
    return round(sum(_dir_size_many(targets)) / (1024**3), 2)


def _get_temp_size_mb() -> float:
    """获取 Temp 目录大小（MB）。"""
    return round(_dir_size(config.TEMP_DIR) / 1024 / 1024, 2)


def scan_all(threshold_mb: int = 100) -> dict[str, Any]:
    """扫描所有 zone，返回完整的扫描结果。"""
    all_big: list[dict[str, Any]] = []
    all_junctions: list[dict[str, Any]] = []
    all_no_go: list[dict[str, Any]] = []

    for zone_key in config.SCAN_ZONES:
        big, junctions, no_go = scan_zone(zone_key, threshold_mb)
        all_big.extend(big)
        all_junctions.extend(junctions)
        all_no_go.extend(no_go)

    released_gb = _calc_released_gb(all_junctions)
    temp_size_mb = _get_temp_size_mb()
    c_total, c_free, d_free = get_drive_info()
    potential_gb = round(sum(d["sizeMB"] for d in all_big) / 1024, 2)

    return {
        "bigDirs": all_big,
        "junctions": all_junctions,
        "noGoDirs": all_no_go,
        "cTotalGB": c_total,
        "cFreeGB": c_free,
        "dFreeGB": d_free,
        "releasedGB": released_gb,
        "potentialGB": potential_gb,
        "tempSizeMB": temp_size_mb,
        "backend": "everything" if _ES_PATH else "powershell",
    }
