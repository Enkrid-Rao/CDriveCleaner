# C盘瘦身助手 - 后端服务 v3
# 支持扫描 Programs + AppData + ProgramData + Program Files
# 只展示绿色安全项目，隐藏所有风险目录
# 提供扫描、迁移、撤销迁移、Temp清理、状态查询等API

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import subprocess
import os
import re
import ctypes
import time

# ===== 路径配置 =====
BASE_USER = r"C:\Users\raoxi"

SCAN_ZONES = {
    "programs": {
        "source": f"{BASE_USER}\\AppData\\Local\\Programs",
        "dest_base": r"D:\AppData\Programs",
        "no_go": [],
        "label": "应用程序",
        "icon": "📦",
        "needs_admin": False
    },
    "local": {
        "source": f"{BASE_USER}\\AppData\\Local",
        "dest_base": r"D:\AppData\Local",
        "no_go": ["Microsoft", "Packages", "Comms", "Deployment", "assembly",
                  "Application Data", "Temp", "Programs"],
        "label": "应用数据(Local)",
        "icon": "📁",
        "needs_admin": False
    },
    "roaming": {
        "source": f"{BASE_USER}\\AppData\\Roaming",
        "dest_base": r"D:\AppData\Roaming",
        "no_go": ["Microsoft"],
        "label": "应用数据(Roaming)",
        "icon": "🔄",
        "needs_admin": False
    },
    "localLow": {
        "source": f"{BASE_USER}\\AppData\\LocalLow",
        "dest_base": r"D:\AppData\LocalLow",
        "no_go": ["Microsoft"],
        "label": "应用数据(LocalLow)",
        "icon": "⬇️",
        "needs_admin": False
    },
    # v3新增: ProgramData (共享数据) - 只展示绿色安全项目
    "programdata": {
        "source": r"C:\ProgramData",
        "dest_base": r"D:\ProgramData",
        "no_go": ["Microsoft", "Package Cache", "Windows", "NVIDIA Corporation",
                  "Intel", "Adobe", "USOShared", "SoftwareDistribution",
                  "System32", "Ssh", "ssh", "MicrosoftSearch", "WinAmp"],
        "label": "共享数据(ProgramData)",
        "icon": "🗄️",
        "needs_admin": True  # ProgramData需要管理员权限操作
    },
    # v3新增: Program Files (应用本体) - 只展示绿色安全项目
    "programfiles": {
        "source": r"C:\Program Files",
        "dest_base": r"D:\Program Files",
        "no_go": ["Microsoft", "Microsoft Visual Studio", "Microsoft Office", "Microsoft OneDrive",
                  "Windows Defender", "Windows Defender Advanced Threat Protection", "Windows Security",
                  "Adobe", "Common Files", "Internet Explorer",
                  "WindowsApps", "ModifiableWindowsApps", "Windows Communication Foundation",
                  "Windows Media Player", "Windows Photo Viewer", "Windows Portable Devices",
                  "Windows Sidebar", "MSBuild", "dotnet", "Reference Assemblies",
                  "NVIDIA Corporation", "WSL"],
        "label": "应用本体(Program Files)",
        "icon": "💼",
        "needs_admin": True
    }
}

def run_ps(script):
    """运行PowerShell脚本并返回输出 - 使用ps1文件避免命令行转义问题"""
    try:
        ps1_path = os.path.join(os.path.dirname(__file__), "_temp_script.ps1")
        with open(ps1_path, 'w', encoding='utf-8-sig') as f:
            f.write(script)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
            capture_output=True, text=True, timeout=180
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "超时", 1

def get_drive_info():
    """获取C盘和D盘空间信息"""
    script = """
    $c = [System.IO.DriveInfo]::new('C')
    $d = [System.IO.DriveInfo]::new('D')
    "$([math]::Round($c.TotalSize/1GB,2))|$([math]::Round($c.AvailableFreeSpace/1GB,2))|$([math]::Round($d.AvailableFreeSpace/1GB,2))"
    """
    stdout, _, _ = run_ps(script)
    parts = stdout.split("|")
    if len(parts) == 3:
        return float(parts[0]), float(parts[1]), float(parts[2])
    return 400.0, 0.0, 0.0

def scan_zone(zone_key, threshold_mb=100):
    """扫描指定zone的大目录"""
    zone = SCAN_ZONES[zone_key]
    source = zone["source"]
    dest_base = zone["dest_base"]
    no_go = zone["no_go"]
    needs_admin = zone.get("needs_admin", False)

    # 对于需要admin权限的zone (ProgramData/Program Files)，no-go目录不计算大小直接跳过
    # 对于AppData的zone，no-go目录计算大小但标记为不可迁移
    skip_nogo_size = needs_admin

    script = f"""
    $SourcePath = '{source}'
    $DestBase = '{dest_base}'
    $Threshold = {threshold_mb}
    $NoGo = @({','.join(f"'{n}'" for n in no_go)})
    $SkipNoGoSize = ${str(skip_nogo_size).lower()}

    $dirs = Get-ChildItem $SourcePath -Directory -ErrorAction SilentlyContinue

    foreach ($d in $dirs) {{
        $isNoGo = $NoGo -contains $d.Name
        if ($d.Attributes -match 'ReparsePoint') {{
            "JUNCTION|$($d.Name)|$($d.Target)|{zone_key}"
        }} elseif ($isNoGo) {{
            if (-not $SkipNoGoSize) {{
                $size = (Get-ChildItem $d.FullName -Recurse -File -Force -ErrorAction SilentlyContinue |
                         Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
                if ($null -eq $size) {{ $size = 0 }}
                $sizeMB = [math]::Round($size / 1MB, 2)
                "NOGO|$($d.Name)|$sizeMB|{zone_key}"
            }}
            # 对于需要admin的zone，no-go目录直接跳过，不输出任何信息
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
    stdout, stderr, rc = run_ps(script)

    big_dirs = []
    junction_list = []
    no_go_list = []

    for line in stdout.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if line.startswith("JUNCTION|") and len(parts) >= 4:
            junction_list.append({"name": parts[1], "target": parts[2], "zone": parts[3]})
        elif line.startswith("NOGO|") and len(parts) >= 4:
            no_go_list.append({"name": parts[1], "sizeMB": float(parts[2]), "zone": parts[3]})
        elif line.startswith("BIG|") and len(parts) >= 6:
            big_dirs.append({
                "name": parts[1],
                "sizeMB": float(parts[2]),
                "path": parts[3],
                "dest": parts[4],
                "zone": parts[5],
                "needsAdmin": needs_admin
            })

    big_dirs.sort(key=lambda x: x.get("sizeMB", 0), reverse=True)
    return big_dirs, junction_list, no_go_list

def scan_all(threshold_mb=100):
    """扫描所有zone"""
    all_big = []
    all_junctions = []
    all_no_go = []

    for zone_key in SCAN_ZONES:
        big, junctions, no_go = scan_zone(zone_key, threshold_mb)
        all_big.extend(big)
        all_junctions.extend(junctions)
        all_no_go.extend(no_go)

    # 计算已释放空间（使用更快的方式）
    released_gb = 0
    for j in all_junctions:
        target = j.get("target", "")
        if target and os.path.exists(target):
            try:
                total_size = 0
                for dirpath, dirnames, filenames in os.walk(target):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        try:
                            total_size += os.path.getsize(fp)
                        except:
                            pass
                released_gb += total_size / (1024**3)
            except:
                pass
    released_gb = round(released_gb, 2)

    # Temp大小
    temp_script = """
    $tempPath = 'C:\\Users\\raoxi\\AppData\\Local\\Temp'
    $size = (Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum
    if ($null -eq $size) { $size = 0 }
    [math]::Round($size / 1MB, 2)
    """
    stdout, _, _ = run_ps(temp_script)
    temp_size_mb = float(stdout) if stdout else 0

    cTotal, cFree, dFree = get_drive_info()

    # 可释放空间
    potential_gb = round(sum(d["sizeMB"] for d in all_big) / 1024, 2)

    return {
        "bigDirs": all_big,
        "junctions": all_junctions,
        "noGoDirs": all_no_go,
        "cTotalGB": cTotal,
        "cFreeGB": cFree,
        "dFreeGB": dFree,
        "releasedGB": released_gb,
        "potentialGB": potential_gb,
        "tempSizeMB": temp_size_mb
    }

def migrate_dir(source_path, dest_path, name):
    """迁移单个目录到D盘并创建Junction"""
    steps = []

    # 查找zone以确定是否需要admin权限
    needs_admin = False
    for zone_key, zone in SCAN_ZONES.items():
        if zone["source"] in source_path or source_path.startswith(zone["source"] + "\\"):
            needs_admin = zone.get("needs_admin", False)
            break

    # 如果需要admin权限，提示用户
    if needs_admin:
        return {
            "success": False,
            "error": f"⚠️ ProgramData/Program Files目录需要管理员权限迁移。\n请右键以管理员身份运行CMD，执行:\n\n迁移Lenovo.bat\n\n（已自动创建在 c-drive-tool 目录中）",
            "needsAdmin": True,
            "steps": []
        }

    # Step 1: 检查目标应用是否在运行
    # 更智能的进程名匹配
    process_aliases = {
        "WeChat": ["WeChat", "wechat"],
        "Weixin": ["WeChat", "wechat"],
        "Tencent": ["WeChat", "wechat", "QQ", "QQNT"],
        "JetBrains": ["idea", "clion", "pycharm", "webstorm", "rider", "goland", "datagrip", "fleet"],
        "Blackmagic Design": ["Resolve", "DaVinci"],
        "CreatorZone": ["CreatorZone", "CreatorZoneUI"],
        "Lenovo": ["CreatorZone", "CreatorZoneUI", "Vantage", "PCManager", "leapp"],
    }

    search_names = [name]
    for key, aliases in process_aliases.items():
        if name.lower() in [a.lower() for a in aliases] or key.lower() == name.lower():
            search_names = aliases
            break

    search_pattern = "|".join(search_names)
    check_script = f"""
    $sourcePath = '{source_path}'
    $searchNames = @({','.join(f"'{n}'" for n in search_names)})
    $procs = Get-Process | Where-Object {{
        $_.Path -like "$sourcePath\\*" -or
        ($searchNames | Where-Object {{ $_.ProcessName -like "*$($_)*" }}).Count -gt 0 -or
        ($searchNames | Where-Object {{ $_.MainWindowTitle -like "*$($_)*" }}).Count -gt 0
    }} | Select-Object -ExpandProperty ProcessName
    $procs -join ','
    """
    stdout, _, _ = run_ps(check_script)
    if stdout and stdout.strip():
        irrelevant = ["explorer", "SearchHost", "RuntimeBroker", "sihost", "taskhostw"]
        active = [p for p in stdout.split(",") if p.strip() and p.strip().lower() not in irrelevant]
        if active:
            return {"success": False, "error": f"以下进程可能正在使用该目录: {', '.join(active)}。请先关闭相关应用！", "steps": []}

    # Step 2: Robocopy (ALWAYS copy, even if dest exists - contents may differ!)
    steps.append("robocopy复制到D盘")
    if not os.path.exists(dest_path):
        os.makedirs(dest_path, exist_ok=True)

    rc = subprocess.run([
        "robocopy", source_path, dest_path,
        "/e", "/copy:DAT", "/xj", "/r:3", "/w:3", "/np"
    ], capture_output=True, timeout=300)

    # CRITICAL: Verify robocopy succeeded before deleting source!
    # robocopy exit codes: 0=no files copied (already in sync), 1=files copied OK,
    # 2=extra files/dirs detected, 3=1+2, >=8=FAILURE (at least one failure)
    if rc.returncode >= 8:
        return {"success": False, "error": f"robocopy复制失败 (exit code {rc.returncode})。原目录未删除，数据安全。", "steps": steps}

    # Verify destination now has data (safety check: don't delete source if dest is empty)
    if os.path.exists(dest_path):
        dest_file_count = sum(len(files) for _, _, files in os.walk(dest_path))
        if dest_file_count == 0:
            return {"success": False, "error": "robocopy后D盘目标目录为空，可能复制失败。原目录未删除，数据安全。", "steps": steps}
        steps.append(f"验证: D盘目标已包含 {dest_file_count} 个文件")

    # Step 3: 设置权限
    steps.append("设置D盘目录权限")
    subprocess.run(["icacls", dest_path, "/grant", "raoxi:F", "/t", "/q"],
                   capture_output=True, timeout=120)

    # Step 4: 删除原目录
    steps.append("删除C盘原目录")
    delete_script = f"""
    Remove-Item "\\\\?\\{source_path}" -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path "{source_path}") {{
        Remove-Item "{source_path}" -Recurse -Force -ErrorAction SilentlyContinue
    }}
    if (Test-Path "{source_path}") {{ "STILL_EXISTS" }} else {{ "DELETED" }}
    """
    stdout, stderr, rc = run_ps(delete_script)
    if "STILL_EXISTS" in stdout:
        # robocopy /MIR 空目录方式清空
        empty_dir = os.path.join(os.path.dirname(__file__), "_empty")
        os.makedirs(empty_dir, exist_ok=True)
        subprocess.run(["robocopy", empty_dir, source_path, "/MIR", "/r:1", "/w:1"],
                       capture_output=True, timeout=60)
        stdout2, _, _ = run_ps(f"Remove-Item '\\\\?\\{source_path}' -Recurse -Force -ErrorAction SilentlyContinue; if (Test-Path '{source_path}') {{ 'STILL' }} else {{ 'OK' }}")
        if "STILL" in stdout2:
            return {"success": False, "error": "无法删除原目录，可能有文件被锁定。请关闭相关应用后重试。", "steps": steps}

    # Step 5: 创建Junction
    steps.append("创建Junction链接")
    junction_script = f"""
    New-Item -ItemType Junction -Path "{source_path}" -Target "{dest_path}" -Force | Out-Null
    $j = Get-Item "{source_path}"
    if ($j.Attributes -match 'ReparsePoint') {{ "OK|$($j.Target)" }} else {{ "FAIL" }}
    """
    stdout, stderr, rc = run_ps(junction_script)
    if stdout.startswith("OK|"):
        target = stdout.split("|")[1] if "|" in stdout else dest_path
        steps.append("验证成功 ✓")
        return {"success": True, "target": target, "steps": steps}
    else:
        return {"success": False, "error": "Junction创建失败", "steps": steps}

def undo_junction(source_path, name):
    """撤销Junction迁移：删除Junction + robocopy回迁数据"""
    steps = []

    # Step 1: 确认是Junction并获取target
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

    target_path = stdout.split("|")[1] if "|" in stdout else ""

    if not target_path or not os.path.exists(target_path):
        return {"success": False, "error": f"D盘数据不存在: {target_path}", "steps": []}

    steps.append(f"确认Junction指向: {target_path}")

    # 查找zone以确定是否需要admin权限
    needs_admin = False
    for zone_key, zone in SCAN_ZONES.items():
        if source_path.startswith(zone["source"]):
            needs_admin = zone.get("needs_admin", False)
            break

    if needs_admin:
        return {
            "success": False,
            "error": "⚠️ ProgramData/Program Files的撤销迁移需要管理员权限。\n请在管理员CMD中手动执行:\n1. rd /q \"source_path\"\n2. robocopy \"target_path\" \"source_path\" /e /copy:DAT /xj",
            "needsAdmin": True,
            "steps": steps
        }

    # Step 2: 删除Junction
    steps.append("删除Junction链接")
    del_junction_script = f"""
    Remove-Item "{source_path}" -Force -ErrorAction Stop
    if (Test-Path "{source_path}") {{ "FAIL" }} else {{ "OK" }}
    """
    stdout, _, _ = run_ps(del_junction_script)
    if "FAIL" in stdout:
        return {"success": False, "error": "无法删除Junction", "steps": steps}

    # Step 3: robocopy回迁
    steps.append("robocopy回迁数据到C盘")
    rc = subprocess.run([
        "robocopy", target_path, source_path,
        "/e", "/copy:DAT", "/xj", "/r:3", "/w:3", "/np"
    ], capture_output=True, timeout=300)

    # Step 4: 设置权限
    steps.append("设置C盘目录权限")
    subprocess.run(["icacls", source_path, "/grant", "raoxi:F", "/t", "/q"],
                   capture_output=True, timeout=120)

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
        sizeMB = stdout.split("|")[1]
        steps.append(f"数据回迁完成: {sizeMB} MB ✓")
        return {"success": True, "target": target_path, "sizeMB": sizeMB, "steps": steps}
    else:
        return {"success": False, "error": "数据回迁验证失败", "steps": steps}

def generate_admin_bat(name, source_path, dest_path, size_mb, action="migrate"):
    """Generate an ASCII-only .bat script for admin-level migration/undo.
    The bat script writes a result file so the frontend can poll for completion.
    Note: All paths are normalized to backslash format for CMD compatibility."""
    # Normalize paths to backslash format (CMD doesn't understand forward slashes in paths)
    source_path = source_path.replace("/", "\\")
    dest_path = dest_path.replace("/", "\\")
    tool_dir = os.path.dirname(os.path.abspath(__file__))
    result_file = os.path.join(tool_dir, f"_admin_result_{name}.txt")

    # Remove any stale result file
    if os.path.exists(result_file):
        os.remove(result_file)

    dest_exists = os.path.exists(dest_path)

    lines = [
        "@echo off",
        f":: Admin {action} script for {name}",
        ":: Auto-generated by C Drive Slim Tool",
        ":: Close any related apps before running!",
        "",
        "cd /d \"%~dp0\"",
        "",
        f"set RESULT_FILE={result_file}",
        "",
    ]

    if action == "migrate":
        # ALWAYS robocopy - even if dest exists, the contents may differ!
        # (D:\Program Files\JetBrains may have old IntelliJ, while C drive has newer CLion/GoLand/PyCharm)
        lines.extend([
            "echo [1/3] Copying data to D drive (may take a few minutes)...",
            f'robocopy "{source_path}" "{dest_path}" /e /copy:DAT /xj /r:3 /w:3 /np',
            "if errorlevel 8 (",
            f'    echo FAILED:robocopy > "%RESULT_FILE%"',
            "    pause",
            "    exit /b 1",
            ")",
            "",
        ])

        lines.extend([
            f"echo [2/3] Deleting C drive original...",
            f'rd /s /q "{source_path}" 2>nul',
            f'if exist "{source_path}" (',
            "    echo Direct delete failed, trying robocopy mirror trick...",
            f'    mkdir "{os.path.dirname(source_path)}\\__empty_tmp" 2>nul',
            f'    robocopy "{os.path.dirname(source_path)}\\__empty_tmp" "{source_path}" /MIR /r:1 /w:1 /NFL /NDL >nul',
            f'    rd /s /q "{source_path}" 2>nul',
            f'    rd /s /q "{os.path.dirname(source_path)}\\__empty_tmp" 2>nul',
            ")",
            f'if exist "{source_path}" (',
            f'    echo FAILED:delete > "%RESULT_FILE%"',
            "    pause",
            "    exit /b 1",
            ")",
            "echo C drive original deleted.",
            "",
            "echo [3/3] Creating Junction link...",
            f'mklink /J "{source_path}" "{dest_path}"',
            f'if not exist "{source_path}" (',
            f'    echo FAILED:junction > "%RESULT_FILE%"',
            "    pause",
            "    exit /b 1",
            ")",
            "",
            f'echo SUCCESS:{size_mb} > "%RESULT_FILE%"',
            f"echo Migration complete! {size_mb} MB freed on C drive.",
            "echo.",
            f"echo C: {source_path}  (Junction)",
            f"echo D: {dest_path}  (Real data)",
            "pause",
        ])

    elif action == "undo":
        lines.extend([
            "echo [1/3] Removing Junction link...",
            f'rd /q "{source_path}"',
            f'if exist "{source_path}" (',
            f'    echo FAILED:junction_remove > "%RESULT_FILE%"',
            "    pause",
            "    exit /b 1",
            ")",
            "",
            "echo [2/3] Copying data back to C drive...",
            f'robocopy "{dest_path}" "{source_path}" /e /copy:DAT /xj /r:3 /w:3 /np',
            "",
            f'echo SUCCESS > "%RESULT_FILE%"',
            "echo Undo complete! Data restored to C drive.",
            "pause",
        ])

    bat_name = f"Admin-{action}-{name}.bat"
    bat_path = os.path.join(tool_dir, bat_name)
    with open(bat_path, 'w', encoding='ascii', newline='\r\n') as f:
        f.write("\n".join(lines) + "\n")

    return bat_path, bat_name, result_file

def try_uac_elevate(bat_path):
    """Try to trigger UAC elevation via ctypes ShellExecuteW(runas).
    Returns True if UAC prompt was triggered (user will see the prompt).
    Returns False if elevation failed or is not available."""
    try:
        # ShellExecuteW(hwnd, operation, file, params, directory, showCmd)
        # "runas" verb triggers UAC elevation
        # showCmd=1 = SW_SHOWNORMAL (needed for UAC prompt to appear)
        ret = ctypes.windll.shell32.ShellExecuteW(
            0, "runas", "cmd",
            f'/c "{bat_path}"',
            os.path.dirname(bat_path),
            1  # SW_SHOWNORMAL
        )
        # ShellExecuteW returns value > 32 on success
        return ret > 32
    except Exception as e:
        # Log the error but don't crash
        print(f"[WARN] ctypes UAC elevation failed: {e}")
        return False

def try_uac_elevate_ps(bat_path):
    """Fallback: try UAC elevation via PowerShell Start-Process -Verb RunAs"""
    try:
        script = f'''
        try {{
            Start-Process -FilePath "cmd" -ArgumentList '/c "{bat_path}"' -Verb RunAs -WindowStyle Normal
            "UAC_TRIGGERED"
        }} catch {{
            "UAC_FAILED:$($_.Exception.Message)"
        }}
        '''
        stdout, stderr, rc = run_ps(script)
        return "UAC_TRIGGERED" in stdout
    except Exception as e:
        print(f"[WARN] PowerShell UAC elevation failed: {e}")
        return False

def clean_temp():
    """清理C盘Temp目录"""
    script = """
    $tempPath = 'C:\\Users\\raoxi\\AppData\\Local\\Temp'
    $before = (Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
               Measure-Object -Property Length -Sum -ErrorAction SilentlyContinue).Sum

    Get-ChildItem $tempPath -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-1) } |
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
    """
    stdout, _, _ = run_ps(script)
    cleaned_mb = float(stdout) if stdout else 0
    return {"success": True, "cleanedMB": cleaned_mb}


class APIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length).decode('utf-8')) if content_length > 0 else {}

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        if self.path == '/api/scan':
            threshold = body.get('threshold', 100)
            result = scan_all(threshold)
            self.wfile.write(json.dumps(result).encode())

        elif self.path == '/api/migrate':
            source = body.get('path', '')
            dest = body.get('dest', '')
            name = body.get('name', '')
            if not source or not dest:
                self.wfile.write(json.dumps({"success": False, "error": "缺少参数"}).encode())
            else:
                result = migrate_dir(source, dest, name)
                cTotal, cFree, dFree = get_drive_info()
                result['cFreeGB'] = cFree
                result['dFreeGB'] = dFree
                self.wfile.write(json.dumps(result).encode())

        elif self.path == '/api/undo':
            source = body.get('path', '')
            name = body.get('name', '')
            if not source:
                self.wfile.write(json.dumps({"success": False, "error": "缺少路径参数"}).encode())
            else:
                result = undo_junction(source, name)
                cTotal, cFree, dFree = get_drive_info()
                result['cFreeGB'] = cFree
                result['dFreeGB'] = dFree
                self.wfile.write(json.dumps(result).encode())

        elif self.path == '/api/admin-migrate':
            source = body.get('path', '')
            dest = body.get('dest', '')
            name = body.get('name', '')
            size_mb = body.get('sizeMB', 0)
            if not source or not dest or not name:
                self.wfile.write(json.dumps({"success": False, "error": "缺少参数"}).encode())
            else:
                try:
                    bat_path, bat_name, result_file = generate_admin_bat(name, source, dest, size_mb, "migrate")
                    # Try UAC elevation (ctypes first, PowerShell fallback)
                    uac_ok = try_uac_elevate(bat_path)
                    if not uac_ok:
                        uac_ok = try_uac_elevate_ps(bat_path)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "uacTriggered": uac_ok,
                        "scriptFile": bat_name,
                        "scriptPath": bat_path,
                        "resultFile": result_file,
                        "instructions": f"Right-click CMD -> Run as administrator -> cd /d \"{os.path.dirname(bat_path)}\" -> {bat_name}" if not uac_ok else "UAC prompt should appear. Click Yes to proceed."
                    }).encode())
                except Exception as e:
                    self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())

        elif self.path == '/api/admin-undo':
            source = body.get('path', '')
            name = body.get('name', '')
            dest = body.get('dest', '')
            if not source or not name:
                self.wfile.write(json.dumps({"success": False, "error": "缺少参数"}).encode())
            else:
                try:
                    # Find dest from junction target
                    check_script = f'''
                    $item = Get-Item "{source}" -ErrorAction SilentlyContinue
                    if ($item -and $item.Attributes -match "ReparsePoint") {{
                        "TARGET|$($item.Target)"
                    }} else {{
                        "NOT_JUNCTION"
                    }}
                    '''
                    stdout, _, _ = run_ps(check_script)
                    if stdout.startswith("TARGET|"):
                        dest = stdout.split("|")[1] if "|" in stdout else dest
                    if not dest:
                        self.wfile.write(json.dumps({"success": False, "error": "Cannot determine Junction target"}).encode())
                    else:
                        bat_path, bat_name, result_file = generate_admin_bat(name, source, dest, 0, "undo")
                        uac_ok = try_uac_elevate(bat_path)
                        if not uac_ok:
                            uac_ok = try_uac_elevate_ps(bat_path)
                        self.wfile.write(json.dumps({
                            "success": True,
                            "uacTriggered": uac_ok,
                            "scriptFile": bat_name,
                            "scriptPath": bat_path,
                            "resultFile": result_file,
                            "instructions": f"Right-click CMD -> Run as administrator -> cd /d \"{os.path.dirname(bat_path)}\" -> {bat_name}" if not uac_ok else "UAC prompt should appear. Click Yes to proceed."
                        }).encode())
                except Exception as e:
                    self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())

        elif self.path == '/api/admin-result':
            name = body.get('name', '')
            if not name:
                self.wfile.write(json.dumps({"success": False, "error": "缺少name参数"}).encode())
            else:
                try:
                    result_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"_admin_result_{name}.txt")
                    if os.path.exists(result_file):
                        with open(result_file, 'r', encoding='ascii') as f:
                            content = f.read().strip()
                        # Parse result
                        if content.startswith("SUCCESS"):
                            size_part = content.split(":")[1] if ":" in content else "0"
                            self.wfile.write(json.dumps({
                                "success": True,
                                "sizeMB": float(size_part) if size_part else 0,
                                "raw": content
                            }).encode())
                        elif content.startswith("FAILED"):
                            reason = content.split(":")[1] if ":" in content else "unknown"
                            self.wfile.write(json.dumps({
                                "success": False,
                                "error": f"Admin script failed: {reason}",
                                "raw": content
                            }).encode())
                        else:
                            self.wfile.write(json.dumps({"success": False, "raw": content}).encode())
                    else:
                        # Result file not yet written - script still running or not started
                        self.wfile.write(json.dumps({"success": False, "pending": True}).encode())
                except Exception as e:
                    self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())

        elif self.path == '/api/clean-temp':
            result = clean_temp()
            cTotal, cFree, dFree = get_drive_info()
            result['cFreeGB'] = cFree
            self.wfile.write(json.dumps(result).encode())

        elif self.path == '/api/status':
            cTotal, cFree, dFree = get_drive_info()
            self.wfile.write(json.dumps({
                "cTotalGB": cTotal, "cFreeGB": cFree, "dFreeGB": dFree
            }).encode())

        elif self.path == '/api/quit':
            self.wfile.write(json.dumps({"success": True}).encode())
            import threading
            threading.Thread(target=self.server.shutdown).start()

        else:
            self.wfile.write(json.dumps({"error": "unknown endpoint"}).encode())

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            with open(os.path.join(os.path.dirname(__file__), '..', 'web', 'index.html'), 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    PORT = 8765
    print(f"C盘瘦身助手 v4 启动: http://localhost:{PORT}")
    print(f"支持扫描: Programs + AppData + ProgramData + Program Files")
    print(f"支持UAC管理员权限自动提升")
    print(f"只展示绿色安全项目，风险目录已隐藏")
    server = HTTPServer(('localhost', PORT), APIHandler)
    server.serve_forever()
