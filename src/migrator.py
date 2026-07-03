"""目录迁移与撤销逻辑。

核心流程：robocopy 复制 → 校验 → 删原目录 → 创建 Junction。
撤销流程：删 Junction → robocopy 回迁 → 校验。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .config import SCAN_ZONES, CURRENT_USER, TEMP_DIR, TEMP_RETENTION_DAYS
from .powershell import run_ps, _NO_WINDOW
from .scanner import get_drive_info

# 进程名别名映射：迁移前检查目标应用是否在运行
PROCESS_ALIASES: dict[str, list[str]] = {
    "WeChat": ["WeChat", "wechat"],
    "Weixin": ["WeChat", "wechat"],
    "Tencent": ["WeChat", "wechat", "QQ", "QQNT"],
    "JetBrains": ["idea", "clion", "pycharm", "webstorm", "rider", "goland", "datagrip", "fleet"],
    "Blackmagic Design": ["Resolve", "DaVinci"],
    "CreatorZone": ["CreatorZone", "CreatorZoneUI"],
    "Lenovo": ["CreatorZone", "CreatorZoneUI", "Vantage", "PCManager", "leapp"],
}

# 不相关的系统进程，检查时忽略
IRRELEVANT_PROCESSES = {"explorer", "searchhost", "runtimebroker", "sihost", "taskhostw"}


def _find_zone_for_path(source_path: str) -> dict[str, Any] | None:
    """根据路径查找所属 zone 配置。"""
    for zone in SCAN_ZONES.values():
        zone_source = zone["source"]
        if source_path.startswith(zone_source + "\\") or source_path == zone_source:
            return zone
    return None


def _check_process_running(source_path: str, name: str) -> list[str]:
    """检查目标应用是否在运行，返回活跃进程名列表。"""
    search_names = [name]
    for key, aliases in PROCESS_ALIASES.items():
        if name.lower() in [a.lower() for a in aliases] or key.lower() == name.lower():
            search_names = aliases
            break

    search_items = ",".join(f"'{n}'" for n in search_names)
    check_script = f"""
    $sourcePath = '{source_path}'
    $searchNames = @({search_items})
    $procs = Get-Process | Where-Object {{
        $_.Path -like "$sourcePath\\*" -or
        ($searchNames | Where-Object {{ $_.ProcessName -like "*$($_)*" }}).Count -gt 0 -or
        ($searchNames | Where-Object {{ $_.MainWindowTitle -like "*$($_)*" }}).Count -gt 0
    }} | Select-Object -ExpandProperty ProcessName
    $procs -join ','
    """
    stdout, _, _ = run_ps(check_script)
    if not stdout or not stdout.strip():
        return []

    active = [
        p for p in stdout.split(",")
        if p.strip() and p.strip().lower() not in IRRELEVANT_PROCESSES
    ]
    return active


def _robocopy(source: str, dest: str, extra_args: list[str] | None = None) -> int:
    """执行 robocopy，返回退出码。

    robocopy 退出码：
      0 = 无文件复制（已同步）
      1 = 文件已复制
      2 = 检测到额外文件/目录
      3 = 1+2
      >=8 = 失败
    """
    cmd = ["robocopy", source, dest, "/e", "/copy:DAT", "/xj", "/r:3", "/w:3", "/np"]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, timeout=300,
                            creationflags=_NO_WINDOW)
    return result.returncode


def _delete_directory(source_path: str) -> bool:
    """删除目录，返回是否成功。

    先尝试 PowerShell Remove-Item，失败则用 robocopy /MIR 空目录方式清空。
    """
    delete_script = f"""
    Remove-Item "\\\\?\\{source_path}" -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path "{source_path}") {{
        Remove-Item "{source_path}" -Recurse -Force -ErrorAction SilentlyContinue
    }}
    if (Test-Path "{source_path}") {{ "STILL_EXISTS" }} else {{ "DELETED" }}
    """
    stdout, _, _ = run_ps(delete_script)
    if "STILL_EXISTS" not in stdout:
        return True

    # robocopy /MIR 空目录方式清空
    empty_dir = Path(__file__).resolve().parent / "_empty"
    empty_dir.mkdir(exist_ok=True)
    subprocess.run(
        ["robocopy", str(empty_dir), source_path, "/MIR", "/r:1", "/w:1"],
        capture_output=True, timeout=60,
        creationflags=_NO_WINDOW,
    )
    stdout2, _, _ = run_ps(
        f"Remove-Item '\\\\?\\{source_path}' -Recurse -Force -ErrorAction SilentlyContinue; "
        f"if (Test-Path '{source_path}') {{ 'STILL' }} else {{ 'OK' }}"
    )
    return "STILL" not in stdout2


def _create_junction(source_path: str, dest_path: str) -> str | None:
    """创建 Junction，成功返回 target 路径，失败返回 None。"""
    junction_script = f"""
    New-Item -ItemType Junction -Path "{source_path}" -Target "{dest_path}" -Force | Out-Null
    $j = Get-Item "{source_path}"
    if ($j.Attributes -match 'ReparsePoint') {{ "OK|$($j.Target)" }} else {{ "FAIL" }}
    """
    stdout, _, _ = run_ps(junction_script)
    if stdout.startswith("OK|"):
        return stdout.split("|", 1)[1] if "|" in stdout else dest_path
    return None


def migrate_dir(source_path: str, dest_path: str, name: str) -> dict[str, Any]:
    """迁移单个目录到 D 盘并创建 Junction。

    流程：检查进程 → robocopy 复制 → 校验 → 设置权限 → 删原目录 → 创建 Junction。
    """
    steps: list[str] = []

    # 查找 zone 判断是否需要 admin 权限
    zone = _find_zone_for_path(source_path)
    needs_admin = zone.get("needs_admin", False) if zone else False

    if needs_admin:
        return {
            "success": False,
            "error": "⚠️ ProgramData/Program Files 目录需要管理员权限迁移，请使用 🔑 Elevate 按钮。",
            "needsAdmin": True,
            "steps": [],
        }

    # Step 1: 检查进程
    active_procs = _check_process_running(source_path, name)
    if active_procs:
        return {
            "success": False,
            "error": f"以下进程可能正在使用该目录: {', '.join(active_procs)}。请先关闭相关应用！",
            "steps": [],
        }

    # Step 2: robocopy 复制（始终执行，即使 dest 已存在——内容可能不同）
    steps.append("robocopy复制到D盘")
    if not os.path.exists(dest_path):
        os.makedirs(dest_path, exist_ok=True)

    rc = _robocopy(source_path, dest_path)
    if rc >= 8:
        return {
            "success": False,
            "error": f"robocopy复制失败 (exit code {rc})。原目录未删除，数据安全。",
            "steps": steps,
        }

    # Step 3: 校验目标目录非空
    if os.path.exists(dest_path):
        dest_file_count = sum(len(files) for _, _, files in os.walk(dest_path))
        if dest_file_count == 0:
            return {
                "success": False,
                "error": "robocopy后D盘目标目录为空，可能复制失败。原目录未删除，数据安全。",
                "steps": steps,
            }
        steps.append(f"验证: D盘目标已包含 {dest_file_count} 个文件")

    # Step 4: 设置权限
    steps.append("设置D盘目录权限")
    subprocess.run(
        ["icacls", dest_path, "/grant", f"{CURRENT_USER}:F", "/t", "/q"],
        capture_output=True, timeout=120,
        creationflags=_NO_WINDOW,
    )

    # Step 5: 删除原目录
    steps.append("删除C盘原目录")
    if not _delete_directory(source_path):
        return {
            "success": False,
            "error": "无法删除原目录，可能有文件被锁定。请关闭相关应用后重试。",
            "steps": steps,
        }

    # Step 6: 创建 Junction
    steps.append("创建Junction链接")
    target = _create_junction(source_path, dest_path)
    if target:
        steps.append("验证成功 ✓")
        return {"success": True, "target": target, "steps": steps}
    else:
        return {"success": False, "error": "Junction创建失败", "steps": steps}


def undo_junction(source_path: str, name: str) -> dict[str, Any]:
    """撤销 Junction 迁移：删除 Junction + robocopy 回迁数据。"""
    steps: list[str] = []

    # Step 1: 确认是 Junction 并获取 target
    check_script = f"""
    $item = Get-Item "{source_path}" -ErrorAction SilentlyContinue
    if ($item -and $item.Attributes -match 'ReparsePoint') {{
        "IS_JUNCTION|$($item.Target)"
    }} else {{
        "NOT_JUNCTION"
    }}
    """
    stdout, _, _ = run_ps(check_script)
    if not stdout.startswith("IS_JUNCTION|"):
        return {"success": False, "error": "该路径不是Junction，无法撤销", "steps": []}

    target_path = stdout.split("|", 1)[1] if "|" in stdout else ""
    if not target_path or not os.path.exists(target_path):
        return {"success": False, "error": f"D盘数据不存在: {target_path}", "steps": []}

    steps.append(f"确认Junction指向: {target_path}")

    # 查找 zone 判断是否需要 admin
    zone = _find_zone_for_path(source_path)
    needs_admin = zone.get("needs_admin", False) if zone else False
    if needs_admin:
        return {
            "success": False,
            "error": "⚠️ ProgramData/Program Files 的撤销迁移需要管理员权限，请使用 🔑 Elevate 按钮。",
            "needsAdmin": True,
            "steps": steps,
        }

    # Step 2: 删除 Junction
    steps.append("删除Junction链接")
    del_script = f"""
    Remove-Item "{source_path}" -Force -ErrorAction Stop
    if (Test-Path "{source_path}") {{ "FAIL" }} else {{ "OK" }}
    """
    stdout, _, _ = run_ps(del_script)
    if "FAIL" in stdout:
        return {"success": False, "error": "无法删除Junction", "steps": steps}

    # Step 3: robocopy 回迁
    steps.append("robocopy回迁数据到C盘")
    rc = _robocopy(target_path, source_path)
    if rc >= 8:
        return {
            "success": False,
            "error": f"robocopy回迁失败 (exit code {rc})。D盘数据仍在，可重试。",
            "steps": steps,
        }

    # Step 4: 设置权限
    steps.append("设置C盘目录权限")
    subprocess.run(
        ["icacls", source_path, "/grant", f"{CURRENT_USER}:F", "/t", "/q"],
        capture_output=True, timeout=120,
        creationflags=_NO_WINDOW,
    )

    # Step 5: 验证
    steps.append("验证C盘数据完整")
    verify_script = f"""
    if (Test-Path "{source_path}") {{
        $size = (Get-ChildItem "{source_path}" -Recurse -File -Force -ErrorAction SilentlyContinue |
                 Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
        if ($null -eq $size) {{ $size = 0 }}
        "VERIFY_OK|$([math]::Round($size/1MB,2))"
    }} else {{
        "VERIFY_FAIL"
    }}
    """
    stdout, _, _ = run_ps(verify_script)
    if stdout.startswith("VERIFY_OK|"):
        size_mb = stdout.split("|", 1)[1]
        steps.append(f"数据回迁完成: {size_mb} MB ✓")
        return {"success": True, "target": target_path, "sizeMB": size_mb, "steps": steps}
    else:
        return {"success": False, "error": "数据回迁验证失败", "steps": steps}


def clean_temp() -> dict[str, Any]:
    """清理 C 盘 Temp 目录中超过指定天数的临时文件。"""
    script = """
    $tempPath = '__TEMP_DIR__'
    $retentionDays = __RETENTION_DAYS__
    $before = (Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
               Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum

    Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$retentionDays) } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    Get-ChildItem $tempPath -Directory -Force -ErrorAction SilentlyContinue |
        Where-Object { (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue).Count -eq 0 } |
        Remove-Item -Force -Recurse -ErrorAction SilentlyContinue

    $after = (Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
              Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
    if ($null -eq $before) { $before = 0 }
    if ($null -eq $after) { $after = 0 }
    $cleanedMB = [math]::Round(($before - $after) / 1MB, 2)
    "$cleanedMB"
    """.replace("__TEMP_DIR__", TEMP_DIR).replace("__RETENTION_DAYS__", str(TEMP_RETENTION_DAYS))

    stdout, _, _ = run_ps(script)
    try:
        cleaned_mb = float(stdout) if stdout else 0.0
    except ValueError:
        cleaned_mb = 0.0
    return {"success": True, "cleanedMB": cleaned_mb}
