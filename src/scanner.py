"""磁盘扫描逻辑。

扫描 C 盘各区域的大目录、已存在的 Junction、以及受保护的 no-go 目录。
"""

from __future__ import annotations

import os
from typing import Any

from .config import SCAN_ZONES, TEMP_DIR, TEMP_RETENTION_DAYS
from .powershell import run_ps


def get_drive_info() -> tuple[float, float, float]:
    """获取 C 盘总容量、C 盘可用、D 盘可用（单位 GB）。"""
    script = """
    $c = [System.IO.DriveInfo]::new('C')
    $d = [System.IO.DriveInfo]::new('D')
    "$([math]::Round($c.TotalSize/1GB,2))|$([math]::Round($c.AvailableFreeSpace/1GB,2))|$([math]::Round($d.AvailableFreeSpace/1GB,2))"
    """
    stdout, _, _ = run_ps(script)
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
    """
    zone = SCAN_ZONES[zone_key]
    source = zone["source"]
    dest_base = zone["dest_base"]
    no_go = zone["no_go"]
    needs_admin = zone.get("needs_admin", False)

    # admin zone 的 no-go 目录不计算大小直接跳过；
    # 非 admin zone 的 no-go 目录计算大小但标记不可迁移
    skip_nogo_size = needs_admin

    # 注意：PowerShell 脚本中用 {{ }} 转义大括号（f-string 要求）
    no_go_items = ",".join(f"'{n}'" for n in no_go)
    script = f"""
    $SourcePath = '{source}'
    $DestBase = '{dest_base}'
    $Threshold = {threshold_mb}
    $NoGo = @({no_go_items})
    $SkipNoGoSize = ${str(skip_nogo_size).lower()}

    $dirs = Get-ChildItem $SourcePath -Directory -ErrorAction SilentlyContinue

    foreach ($d in $dirs) {{
        $isNoGo = $NoGo -contains $d.Name
        if ($d.Attributes -match 'ReparsePoint') {{
            "JUNCTION|$($d.Name)|$($d.Target)|{zone_key}|$($d.FullName)"
        }} elseif ($isNoGo) {{
            if (-not $SkipNoGoSize) {{
                $size = (Get-ChildItem $d.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
                         Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                if ($null -eq $size) {{ $size = 0 }}
                $sizeMB = [math]::Round($size / 1MB, 2)
                "NOGO|$($d.Name)|$sizeMB|{zone_key}"
            }}
        }} else {{
            $size = (Get-ChildItem $d.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
                     Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
            if ($null -eq $size) {{ $size = 0 }}
            $sizeMB = [math]::Round($size / 1MB, 2)
            if ($sizeMB -ge $Threshold) {{
                "BIG|$($d.Name)|$sizeMB|$($d.FullName)|$DestBase\\$($d.Name)|{zone_key}"
            }}
        }}
    }}
    """
    stdout, _, _ = run_ps(script)

    big_dirs: list[dict[str, Any]] = []
    junction_list: list[dict[str, Any]] = []
    no_go_list: list[dict[str, Any]] = []

    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if line.startswith("JUNCTION|") and len(parts) >= 5:
            junction_list.append({
                "name": parts[1],
                "target": parts[2],
                "zone": parts[3],
                "source": parts[4],
            })
        elif line.startswith("NOGO|") and len(parts) >= 4:
            no_go_list.append({
                "name": parts[1],
                "sizeMB": float(parts[2]),
                "zone": parts[3],
            })
        elif line.startswith("BIG|") and len(parts) >= 6:
            big_dirs.append({
                "name": parts[1],
                "sizeMB": float(parts[2]),
                "path": parts[3],
                "dest": parts[4],
                "zone": parts[5],
                "needsAdmin": needs_admin,
            })

    big_dirs.sort(key=lambda x: x.get("sizeMB", 0), reverse=True)
    return big_dirs, junction_list, no_go_list


def _calc_released_gb(junctions: list[dict]) -> float:
    """计算已释放空间（遍历 Junction 目标目录统计大小）。"""
    released_gb = 0.0
    for j in junctions:
        target = j.get("target", "")
        if target and os.path.exists(target):
            try:
                total_size = 0
                for dirpath, _dirnames, filenames in os.walk(target):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total_size += os.path.getsize(fp)
                        except OSError:
                            pass
                released_gb += total_size / (1024**3)
            except OSError:
                pass
    return round(released_gb, 2)


def _get_temp_size_mb() -> float:
    """获取 Temp 目录大小（MB）。"""
    # 用占位符避免 f-string 与 PowerShell {} 冲突
    script = """
    $tempPath = '__TEMP_DIR__'
    $size = (Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
    if ($null -eq $size) { $size = 0 }
    [math]::Round($size / 1MB, 2)
    """.replace("__TEMP_DIR__", TEMP_DIR)
    stdout, _, _ = run_ps(script)
    try:
        return float(stdout) if stdout else 0.0
    except ValueError:
        return 0.0


def scan_all(threshold_mb: int = 100) -> dict[str, Any]:
    """扫描所有 zone，返回完整的扫描结果。"""
    all_big: list[dict[str, Any]] = []
    all_junctions: list[dict[str, Any]] = []
    all_no_go: list[dict[str, Any]] = []

    for zone_key in SCAN_ZONES:
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
    }
