"""Windows 底层能力：PowerShell、磁盘、Junction、复制、文件锁、安全删除。

本模块刻意 **不导入** ``cdc.core.config``，避免循环依赖；配置通过参数传入。
所有子进程都使用 CREATE_NO_WINDOW，GUI 模式不会闪黑窗。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_SYSTEM_DRIVE = (os.environ.get("SystemDrive") or "C:").rstrip(":\\/").upper()

# 这些进程是系统外壳 / 索引，占用目录时通常不应阻止迁移
SHELL_PROCESSES = {
    "explorer", "searchhost", "searchindexer", "runtimebroker", "sihost",
    "taskhostw", "dllhost", "startmenuexperiencehost", "shellexperiencehost",
    "textinputhost", "applicationframehost", "backgroundtaskhost",
    "securityhealthsystray", "widgets", "lockapp", "useroobebroker",
}


# ============================================================
# PowerShell / 子进程
# ============================================================

@dataclass
class PSResult:
    stdout: str = ""
    stderr: str = ""
    code: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.error


_ps_lock = threading.Lock()
_ps_counter = 0


def _ps_script_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "CDriveCleaner" / "ps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_ps(script: str, timeout: int = 300) -> PSResult:
    """通过临时 .ps1 执行 PowerShell，统一 UTF-8 输出。"""
    global _ps_counter
    if not IS_WINDOWS:
        return PSResult(error="仅支持 Windows")
    with _ps_lock:
        _ps_counter += 1
        idx = _ps_counter
    path = _ps_script_dir() / f"cdc_{os.getpid()}_{idx}.ps1"
    try:
        path.write_text(
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
            "$ErrorActionPreference = 'Continue'\n" + script,
            encoding="utf-8-sig",
        )
        result = subprocess.run(
            ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(path)],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
        )
        return PSResult(
            stdout=(result.stdout or "").strip(),
            stderr=(result.stderr or "").strip(),
            code=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return PSResult(stderr="PowerShell 超时", code=1, error=f"执行超时（{timeout}s）")
    except Exception as exc:  # pragma: no cover - 极端环境
        return PSResult(stderr=str(exc), code=1, error=str(exc))
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def run_cmd(args: list[str] | str, timeout: int = 120) -> PSResult:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
            shell=isinstance(args, str),
        )
        return PSResult(stdout=(result.stdout or "").strip(),
                        stderr=(result.stderr or "").strip(),
                        code=result.returncode)
    except subprocess.TimeoutExpired:
        return PSResult(stderr="命令超时", code=1, error="超时")
    except Exception as exc:
        return PSResult(stderr=str(exc), code=1, error=str(exc))


def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ============================================================
# 磁盘枚举
# ============================================================

_drives_cache: tuple[float, list] | None = None
_drives_lock = threading.Lock()

_DRIVE_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$sys = ($env:SystemDrive).Substring(0,1).ToUpper()
$vols = Get-CimInstance Win32_LogicalDisk | Where-Object { $_.DriveType -in 2,3 }
$map = @{}
try {
  Get-Partition | Where-Object { $_.DriveLetter } | ForEach-Object {
    $letter = [string][char]$_.DriveLetter
    $dn = $_.DiskNumber
    $pd = Get-PhysicalDisk -DeviceNumber $dn
    if ($pd) {
      $map[$letter] = @{
        number = [int]$dn
        name = [string]$pd.FriendlyName
        media = [string]$pd.MediaType
        bus = [string]$pd.BusType
      }
    } else {
      $map[$letter] = @{ number = [int]$dn; name = ''; media = ''; bus = '' }
    }
  }
} catch { }
$out = @()
foreach ($v in $vols) {
  $letter = $v.DeviceID.Substring(0,1).ToUpper()
  $m = $map[$letter]
  $out += [ordered]@{
    letter = $letter
    label = [string]$v.VolumeName
    total = [int64]$v.Size
    free = [int64]$v.FreeSpace
    fs = [string]$v.FileSystem
    kind = [int]$v.DriveType
    disk_number = if ($m) { [int]$m.number } else { $null }
    physical_name = if ($m) { [string]$m.name } else { '' }
    media = if ($m) { [string]$m.media } else { '' }
    bus = if ($m) { [string]$m.bus } else { '' }
    system = ($letter -eq $sys)
  }
}
$out | ConvertTo-Json -Compress -Depth 4
"""


def list_drives(force: bool = False, cache_seconds: float = 15.0) -> list:
    """枚举本地磁盘（含物理盘型号 / 介质类型）。结果短期缓存。"""
    global _drives_cache
    from .models import DriveInfo

    with _drives_lock:
        if (not force and _drives_cache and
                time.time() - _drives_cache[0] < cache_seconds):
            return isinstance(_drives_cache[1], list) and _drives_cache[1] or []
        drives: list[DriveInfo] = []
        res = run_ps(_DRIVE_SCRIPT, timeout=25)
        raw: list[dict[str, Any]] = []
        if res.ok and res.stdout:
            try:
                parsed = json.loads(res.stdout)
                raw = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                raw = []

        if not raw:
            # 兜底：只枚举盘符与容量
            for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
                root = f"{letter}:\\"
                if os.path.exists(root):
                    try:
                        usage = shutil.disk_usage(root)
                    except OSError:
                        continue
                    raw.append({
                        "letter": letter, "label": "", "total": usage.total,
                        "free": usage.free, "fs": "NTFS", "kind": 3,
                        "disk_number": None, "physical_name": "", "media": "",
                        "bus": "", "system": letter == _SYSTEM_DRIVE[:1],
                    })

        for item in raw:
            letter = str(item.get("letter") or "").upper()[:1]
            if not letter:
                continue
            media = str(item.get("media") or "").strip()
            bus = str(item.get("bus") or "").strip()
            kind = int(item.get("kind") or 3)
            drive = DriveInfo(
                letter=letter,
                root=f"{letter}:\\",
                label=str(item.get("label") or ""),
                total_bytes=int(item.get("total") or 0),
                free_bytes=int(item.get("free") or 0),
                filesystem=str(item.get("fs") or ""),
                media_type=media or "Unknown",
                bus_type=bus,
                model=str(item.get("physical_name") or ""),
                drive_kind=kind,
                disk_number=item.get("disk_number"),
                physical_name=str(item.get("physical_name") or ""),
                is_system=bool(item.get("system")) or letter == _SYSTEM_DRIVE[:1],
                is_removable=kind == 2,
            )
            drives.append(drive)

        drives.sort(key=lambda d: d.letter)
        _drives_cache = (time.time(), drives)
        return list(drives)


def get_drive(letter: str, drives: list | None = None) -> Any | None:
    letter = (letter or "").upper().rstrip(":\\/")[:1]
    for drive in (drives if drives is not None else list_drives()):
        if drive.letter == letter:
            return drive
    return None


def drive_of(path: str) -> str:
    try:
        drive, _ = os.path.splitdrive(os.path.abspath(path))
        return drive.rstrip(":").upper()
    except (ValueError, OSError):
        return ""


def free_bytes(path: str) -> int:
    """路径所在卷的可用字节；路径不存在则向上找最近存在的父目录。"""
    probe = os.path.abspath(path)
    for _ in range(30):
        try:
            return shutil.disk_usage(probe).free
        except OSError:
            parent = os.path.dirname(probe)
            if not parent or parent == probe:
                break
            probe = parent
    return 0


def volume_total_bytes(path: str) -> int:
    probe = os.path.abspath(path)
    for _ in range(30):
        try:
            return shutil.disk_usage(probe).total
        except OSError:
            parent = os.path.dirname(probe)
            if not parent or parent == probe:
                break
            probe = parent
    return 0


# ============================================================
# Junction / 路径
# ============================================================

def is_junction(path: str) -> bool:
    try:
        checker = getattr(os.path, "isjunction", None)
        if checker is not None:
            return bool(checker(path))
    except (OSError, ValueError):
        pass
    try:
        return bool(os.lstat(path).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except (OSError, AttributeError):
        return False


def is_link(path: str) -> bool:
    return is_junction(path) or os.path.islink(path)


def normalize_target(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("\\\\?\\"):
        text = text[4:]
    if text.startswith("\\??\\"):
        text = text[4:]
    if text.startswith("UNC\\"):
        text = "\\\\" + text[4:]
    return os.path.normpath(text) if text else ""


def junction_target(path: str) -> str:
    """读取目录链接目标；非链接返回空字符串。"""
    if not os.path.lexists(path):
        return ""
    if is_junction(path) or os.path.islink(path):
        try:
            return normalize_target(os.readlink(path))
        except OSError:
            pass
        res = run_ps(
            f'$i=Get-Item -LiteralPath {ps_quote(path)} -Force; '
            'if ($i.Attributes -match "ReparsePoint") { $i.Target } '
            'else { "" }', timeout=20)
        if res.stdout:
            first = res.stdout.splitlines()[0].strip()
            return normalize_target(first)
    return ""


def ps_quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def path_within(child: str, parent: str) -> bool:
    """child 是否位于 parent 内（含自身）。大小写不敏感、兼容尾斜杠。"""
    try:
        c = os.path.normcase(os.path.abspath(child)).rstrip("\\/")
        p = os.path.normcase(os.path.abspath(parent)).rstrip("\\/")
        if not c or not p:
            return False
        if c == p:
            return True
        return c.startswith(p + os.sep)
    except (ValueError, OSError):
        return False


def is_drive_root(path: str) -> bool:
    try:
        drive, tail = os.path.splitdrive(os.path.abspath(path))
        return bool(drive) and tail.strip("\\/") == ""
    except (ValueError, OSError):
        return False


@dataclass
class DirEntryInfo:
    name: str
    path: str
    is_dir: bool
    is_link: bool
    is_junction: bool
    target: str = ""
    error: str = ""


def scandir_entries(path: str) -> list[DirEntryInfo]:
    rows: list[DirEntryInfo] = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    junction = entry.is_junction()
                    link = junction or entry.is_symlink()
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    junction = link = is_dir = False
                rows.append(DirEntryInfo(
                    name=entry.name,
                    path=entry.path,
                    is_dir=is_dir,
                    is_link=link,
                    is_junction=junction,
                ))
    except OSError:
        return []
    rows.sort(key=lambda r: r.name.lower())
    return rows


def child_directories(path: str) -> list[DirEntryInfo]:
    return [e for e in scandir_entries(path) if e.is_dir]


# ============================================================
# 目录统计
# ============================================================

_EXT_GROUPS: dict[str, set[str]] = {
    "video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
              ".ts", ".m2ts", ".mpg", ".mpeg", ".rmvb", ".3gp", ".vob", ".prproj",
              ".veg", ".fcpxml", ".braw", ".r3d"},
    "audio": {".mp3", ".flac", ".wav", ".aac", ".m4a", ".ogg", ".wma", ".ape", ".aiff"},
    "image": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff",
              ".raw", ".cr2", ".nef", ".arw", ".dng", ".psd", ".ai", ".svg"},
    "iso": {".iso", ".img", ".vhd", ".vhdx", ".vmdk", ".ova", ".qcow2", ".e01", ".dd"},
    "installer": {".exe", ".msi", ".msix", ".appx", ".apk", ".ipa", ".dmg", ".pkg",
                  ".deb", ".rpm", ".msu"},
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst", ".cab",
                ".tgz", ".tbz", ".lz4", ".001"},
    "document": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt",
                 ".md", ".epub", ".mobi", ".azw3", ".djvu", ".chm", ".one"},
    "code": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h", ".hpp",
             ".cs", ".go", ".rs", ".rb", ".php", ".vue", ".html", ".css", ".scss",
             ".json", ".xml", ".yaml", ".yml", ".sql", ".sh", ".ps1", ".ipynb"},
    "model": {".ckpt", ".safetensors", ".bin", ".pt", ".pth", ".onnx", ".gguf",
              ".ggml", ".h5", ".pb", ".tflite", ".msgpack"},
    "backup": {".bak", ".backup", ".old", ".orig", ".gho", ".wim", ".swm", ".spf"},
}


def ext_group(ext: str) -> str:
    ext = ext.lower()
    for group, exts in _EXT_GROUPS.items():
        if ext in exts:
            return group
    return "other"


@dataclass
class DirStats:
    bytes: int = 0
    files: int = 0
    newest: float = 0.0
    oldest: float = 0.0
    ext_bytes: dict[str, int] = field(default_factory=dict)
    links: int = 0
    errors: list[str] = field(default_factory=list)
    truncated: bool = False


def directory_stats(
    root: str,
    *,
    cancel: Callable[[], bool] | None = None,
    on_file: Callable[[int, int], None] | None = None,
    collect_ext: bool = True,
    follow_links: bool = False,
) -> DirStats:
    """统计目录（不进入 Junction/Symlink，防止重复统计与误删）。"""
    stats = DirStats()
    if not os.path.isdir(root):
        return stats
    if is_link(root) and not follow_links:
        stats.links = 1
        return stats
    stack = [root]
    seen = 0
    while stack:
        if cancel and cancel():
            stats.errors.append("已取消")
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_junction() or entry.is_symlink():
                            stats.links += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        st = entry.stat(follow_symlinks=False)
                        size = int(st.st_size)
                        stats.bytes += size
                        stats.files += 1
                        mtime = float(st.st_mtime)
                        if mtime > stats.newest:
                            stats.newest = mtime
                        if stats.oldest == 0 or mtime < stats.oldest:
                            stats.oldest = mtime
                        if collect_ext:
                            group = ext_group(os.path.splitext(entry.name)[1])
                            stats.ext_bytes[group] = stats.ext_bytes.get(group, 0) + size
                        seen += 1
                        if on_file and seen % 400 == 0:
                            on_file(seen, stats.bytes)
                    except OSError as exc:
                        if len(stats.errors) < 20:
                            stats.errors.append(f"{entry.path}: {exc}")
        except OSError as exc:
            if len(stats.errors) < 20:
                stats.errors.append(f"{current}: {exc}")
    return stats


def directory_size(path: str, cancel: Callable[[], bool] | None = None) -> int:
    return directory_stats(path, cancel=cancel, collect_ext=False).bytes


def iter_files(
    root: str,
    *,
    cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
):
    """迭代目录下所有普通文件 (绝对路径, 大小, mtime_ns)，不进入链接。"""
    if not os.path.isdir(root):
        return
    stack = [root]
    count = 0
    total = 0
    while stack:
        if cancel and cancel():
            return
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_junction() or entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                            continue
                        st = entry.stat(follow_symlinks=False)
                        count += 1
                        total += int(st.st_size)
                        if on_progress and count % 1000 == 0:
                            on_progress(count, total)
                        yield entry.path, int(st.st_size), int(st.st_mtime_ns)
                    except OSError:
                        continue
        except OSError:
            continue


def sample_files(root: str, limit: int = 48) -> list[str]:
    """为 Restart Manager 采样文件：每个一级子目录取一个 + 最新的文件。"""
    if os.path.isfile(root):
        return [root]
    picked: list[str] = []
    newest: list[tuple[float, str]] = []
    try:
        with os.scandir(root) as it:
            for entry in it:
                if len(picked) >= limit:
                    break
                try:
                    if entry.is_junction() or entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        picked.append(entry.path)
                        st = entry.stat(follow_symlinks=False)
                        newest.append((float(st.st_mtime), entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        try:
                            with os.scandir(entry.path) as sub_it:
                                for sub in sub_it:
                                    if len(picked) >= limit:
                                        break
                                    try:
                                        if sub.is_file(follow_symlinks=False):
                                            picked.append(sub.path)
                                            st = sub.stat(follow_symlinks=False)
                                            newest.append((float(st.st_mtime), sub.path))
                                            break
                                    except OSError:
                                        continue
                        except OSError:
                            continue
                except OSError:
                    continue
    except OSError:
        return picked
    newest.sort(reverse=True)
    for _ts, path in newest[: max(0, limit - len(picked))]:
        if path not in picked:
            picked.append(path)
    return picked[:limit]


# ============================================================
# 安全删除
# ============================================================

@dataclass
class DeleteReport:
    ok: bool = True
    files: int = 0
    bytes: int = 0
    errors: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        if len(self.errors) < 30:
            self.errors.append(msg)


def _force_writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        try:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x80)
        except Exception:
            pass


def remove_link(path: str) -> bool:
    """只删除链接本身，绝不触碰目标数据。"""
    try:
        if is_junction(path):
            os.rmdir(path)
        elif os.path.islink(path):
            os.unlink(path)
        elif os.path.isdir(path):
            os.rmdir(path)
        elif os.path.exists(path):
            os.unlink(path)
        return not os.path.lexists(path)
    except OSError:
        # 回退到 cmd rd（不带 /s，不会递归目标）
        if os.path.isdir(path) and is_junction(path):
            res = run_cmd(f'cmd /c rd "{path}"', timeout=30)
            return res.code == 0 and not os.path.lexists(path)
        return not os.path.lexists(path)


def safe_delete_tree(
    root: str,
    *,
    cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> DeleteReport:
    """安全递归删除：遇到 Junction/Symlink 只删链接，不进入目标。

    相比 ``shutil.rmtree`` / ``Remove-Item -Recurse``，这是本工具处理迁移目录的
    唯一删除入口——后者在旧版 Windows 上会跟随重解析点，可能误删迁移目标里的数据。
    """
    report = DeleteReport()
    if not os.path.lexists(root):
        return report
    if is_link(root):
        ok = remove_link(root)
        report.ok = ok
        if not ok:
            report.add(f"无法删除链接: {root}")
        return report

    stack: list[tuple[str, bool]] = [(root, False)]
    counter = 0
    while stack:
        if cancel and cancel():
            report.ok = False
            report.add("已取消")
            break
        path, visited = stack.pop()
        if visited:
            try:
                _force_writable(path)
                os.rmdir(path)
            except OSError as exc:
                report.ok = False
                report.add(f"{path}: {exc}")
            continue

        if os.path.islink(path) or is_junction(path):
            if not remove_link(path):
                report.ok = False
                report.add(f"无法删除链接: {path}")
            continue

        stack.append((path, True))
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_junction() or entry.is_symlink():
                            if not remove_link(entry.path):
                                report.ok = False
                                report.add(f"无法删除链接: {entry.path}")
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append((entry.path, False))
                        else:
                            st = entry.stat(follow_symlinks=False)
                            _force_writable(entry.path)
                            os.unlink(entry.path)
                            report.files += 1
                            report.bytes += int(st.st_size)
                            counter += 1
                            if on_progress and counter % 300 == 0:
                                on_progress(report.files, report.bytes)
                    except OSError as exc:
                        report.ok = False
                        report.add(f"{entry.path}: {exc}")
        except OSError as exc:
            report.ok = False
            report.add(f"{path}: {exc}")
    report.ok = report.ok and not os.path.lexists(root)
    return report


# ============================================================
# robocopy
# ============================================================

@dataclass
class CopyResult:
    code: int = 0
    ok: bool = False
    canceled: bool = False
    output: str = ""
    duration_s: float = 0.0
    bytes_done: int = 0

    @property
    def error(self) -> str:
        if self.canceled:
            return "用户已取消"
        if self.ok:
            return ""
        return f"robocopy 失败（退出码 {self.code}）"


def robocopy_copy(
    source: str,
    dest: str,
    *,
    total_bytes: int = 0,
    cancel: Callable[[], bool] | None = None,
    on_progress: Callable[[int, int, float], None] | None = None,
    mirror: bool = True,
    threads: int = 8,
    exclude_marker: bool = False,
) -> CopyResult:
    """robocopy 复制，轮询目标大小给出真实进度。

    退出码 0-7 视为成功（>=8 才是错误）。``/XJ`` 永远开启，避免跟随 Junction。
    """
    os.makedirs(dest, exist_ok=True)
    log_path = Path(tempfile.gettempdir()) / "CDriveCleaner" / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / f"robocopy_{os.getpid()}_{int(time.time()*1000)}.log"
    cmd = [
        "robocopy", source, dest,
        "/MIR" if mirror else "/E",
        "/XJ", "/COPY:DAT", "/DCOPY:DAT",
        "/R:2", "/W:2", f"/MT:{max(1, threads)}",
        "/NP", "/NFL", "/NDL", "/NJH", "/NJS",
        f"/LOG:{log_file}",
    ]
    if exclude_marker:
        cmd.extend(["/XF", ".cdc-origin.json"])
    started = time.time()
    result = CopyResult()
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW,
        )
    except Exception as exc:
        return CopyResult(code=-1, ok=False, output=str(exc),
                          duration_s=time.time() - started)

    last_poll = 0.0
    last_bytes = 0
    last_time = started
    try:
        while proc.poll() is None:
            if cancel and cancel():
                proc.kill()
                result.canceled = True
                break
            now = time.time()
            if on_progress and now - last_poll >= 2.0:
                last_poll = now
                try:
                    done = directory_size(dest, cancel=lambda: False)
                except Exception:
                    done = last_bytes
                dt = max(0.001, now - last_time)
                speed = max(0.0, (done - last_bytes) / dt)
                if speed > 0:
                    last_bytes, last_time = done, now
                on_progress(done, total_bytes, speed)
            time.sleep(0.35)
        result.code = proc.wait()
    finally:
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
    result.duration_s = time.time() - started
    result.ok = (not result.canceled) and 0 <= result.code < 8
    try:
        result.output = log_file.read_text(encoding="utf-8", errors="replace")[-6000:]
    except OSError:
        result.output = ""
    try:
        log_file.unlink(missing_ok=True)
    except OSError:
        pass
    if on_progress and result.ok:
        try:
            result.bytes_done = directory_size(dest, cancel=lambda: False)
        except Exception:
            result.bytes_done = 0
        on_progress(result.bytes_done, total_bytes or result.bytes_done, 0.0)
    return result


# ============================================================
# Junction 创建
# ============================================================

def create_junction(source: str, target: str) -> tuple[bool, str]:
    """在 source 创建指向 target 的 Junction。返回 (成功, 错误)。"""
    source = os.path.abspath(source)
    target = os.path.abspath(target)
    if os.path.lexists(source):
        return False, "源路径已存在，无法创建链接"
    if not os.path.isdir(target):
        return False, "链接目标不存在"
    parent = os.path.dirname(source)
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        return False, f"创建父目录失败: {exc}"
    if '"' in source or '"' in target:
        return False, "路径包含引号，拒绝执行"
    res = run_cmd(f'cmd /c mklink /J "{source}" "{target}"', timeout=60)
    if res.code != 0:
        return False, (res.stdout or res.stderr or "mklink 失败").strip()
    actual = junction_target(source)
    if not actual:
        return False, "链接创建后无法验证"
    if os.path.normcase(actual).rstrip("\\/") != os.path.normcase(target).rstrip("\\/"):
        return False, f"链接目标不一致: {actual}"
    return True, ""


# ============================================================
# 进程 / 文件锁检测
# ============================================================

CCH_RM_MAX_APP_NAME = 255
CCH_RM_MAX_SVC_NAME = 63
ERROR_MORE_DATA = 234


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


class _RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [("dwProcessId", wt.DWORD), ("ProcessStartTime", _FILETIME)]


class _RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", _RM_UNIQUE_PROCESS),
        ("strAppName", wt.WCHAR * (CCH_RM_MAX_APP_NAME + 1)),
        ("strServiceShortName", wt.WCHAR * (CCH_RM_MAX_SVC_NAME + 1)),
        ("ApplicationType", wt.DWORD),
        ("AppStatus", wt.ULONG),
        ("TSSessionId", wt.DWORD),
        ("bRestartable", wt.BOOL),
    ]


_rm_lock = threading.Lock()
_rm_ready = False
_rm_error = ""


def _load_rm() -> Any:
    global _rm_ready, _rm_error
    if _rm_ready:
        return ctypes.windll.RstrtMgr
    if _rm_error:
        return None
    try:
        rm = ctypes.WinDLL("RstrtMgr")
        rm.RmStartSession.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, wt.LPWSTR]
        rm.RmStartSession.restype = wt.DWORD
        rm.RmRegisterResources.argtypes = [
            wt.DWORD, wt.UINT, ctypes.POINTER(wt.LPCWSTR), wt.UINT,
            ctypes.c_void_p, wt.UINT, ctypes.c_void_p,
        ]
        rm.RmRegisterResources.restype = wt.DWORD
        rm.RmGetList.argtypes = [
            wt.DWORD, ctypes.POINTER(wt.UINT), ctypes.POINTER(wt.UINT),
            ctypes.POINTER(_RM_PROCESS_INFO), ctypes.POINTER(wt.ULONG),
        ]
        rm.RmGetList.restype = wt.DWORD
        rm.RmEndSession.argtypes = [wt.DWORD]
        rm.RmEndSession.restype = wt.DWORD
        _rm_ready = True
        return rm
    except Exception as exc:
        _rm_error = str(exc)
        return None


def _restart_manager_lockers(files: list[str]) -> list[dict[str, Any]]:
    if not IS_WINDOWS or not files:
        return []
    with _rm_lock:
        rm = _load_rm()
        if rm is None:
            return []
        handle = wt.DWORD(0)
        key = ctypes.create_unicode_buffer(128)
        if rm.RmStartSession(ctypes.byref(handle), 0, key) != 0:
            return []
        try:
            arr = (ctypes.c_wchar_p * len(files))(*[ctypes.c_wchar_p(f) for f in files])
            if rm.RmRegisterResources(handle, len(files), arr, 0, None, 0, None) != 0:
                return []
            needed = wt.UINT(0)
            count = wt.UINT(0)
            reasons = wt.ULONG(0)
            rc = rm.RmGetList(handle, ctypes.byref(needed), ctypes.byref(count),
                              None, ctypes.byref(reasons))
            if rc != ERROR_MORE_DATA or needed.value == 0:
                return []
            infos = (_RM_PROCESS_INFO * needed.value)()
            count = wt.UINT(needed.value)
            rc = rm.RmGetList(handle, ctypes.byref(needed), ctypes.byref(count),
                              infos, ctypes.byref(reasons))
            if rc != 0:
                return []
            out = []
            for i in range(count.value):
                info = infos[i]
                name = (info.strAppName or "").strip()
                out.append({
                    "pid": int(info.Process.dwProcessId),
                    "name": name,
                    "exe": "",
                    "method": "restart-manager",
                })
            return out
        except Exception:
            return []
        finally:
            try:
                rm.RmEndSession(handle)
            except Exception:
                pass


def processes_using(path: str, *, sample_limit: int = 48) -> list[dict[str, Any]]:
    """检测正在使用 path 的进程（Restart Manager + 可执行文件路径）。

    返回 ``[{pid, name, exe, method}]``，已过滤系统外壳进程与自身。
    """
    if not IS_WINDOWS:
        return []
    found: dict[int, dict[str, Any]] = {}
    files = sample_files(path, sample_limit)
    for row in _restart_manager_lockers(files):
        name = (row.get("name") or "").lower()
        if name in SHELL_PROCESSES:
            continue
        found[row["pid"]] = row

    # 从源目录内启动的进程（Restart Manager 采样不一定覆盖）
    script = (
        f"$root = {ps_quote(os.path.abspath(path))}\n"
        "Get-Process | Where-Object { $_.Path -and "
        "$_.Path.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase) } | "
        "Select-Object Id,ProcessName,Path | ConvertTo-Json -Compress\n"
    )
    res = run_ps(script, timeout=20)
    if res.stdout:
        try:
            raw = json.loads(res.stdout)
            rows = raw if isinstance(raw, list) else [raw]
            for item in rows:
                pid = int(item.get("Id") or 0)
                name = str(item.get("ProcessName") or "")
                if not pid or name.lower() in SHELL_PROCESSES or pid == os.getpid():
                    continue
                found.setdefault(pid, {
                    "pid": pid, "name": name,
                    "exe": str(item.get("Path") or ""),
                    "method": "process-path",
                })
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    self_pid = os.getpid()
    return [row for pid, row in found.items() if pid != self_pid]


# ============================================================
# 其它
# ============================================================

def open_in_explorer(path: str, select: bool = False) -> None:
    try:
        if select and os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        pass


def shell_reveal(path: str) -> None:
    open_in_explorer(path, select=True)


def write_json_atomic(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def set_file_hidden(path: str) -> None:
    if not IS_WINDOWS:
        return
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs != -1:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs | 0x2)
    except Exception:
        pass


def unique_path(base: str) -> str:
    """路径冲突时追加 -2 / -3 …"""
    if not os.path.lexists(base):
        return base
    root, ext = os.path.splitext(base)
    for i in range(2, 1000):
        candidate = f"{root}-{i}{ext}"
        if not os.path.lexists(candidate):
            return candidate
    return f"{base}-{int(time.time())}"


def elapsed_text(start: float) -> str:
    secs = max(0, int(time.time() - start))
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m{secs % 60:02d}s"
